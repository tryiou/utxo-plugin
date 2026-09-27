"""Red-green tests for startup self-heal + serve-time tripwire.

Covers two CONFIRMED bugs and the new compaction policy:

- ``delete_lock_files`` used CWD-relative paths that can never hit
  (CWD is ``/app/plugins``, data lives under
  ``/app/plugins/utxoplugin-<COIN>/``).
- ``compact_history`` dropped DB handles without closing them
  (bare ``del db`` / early return), self-locking the DB for the
  serve phase (live ``RocksIOError: ... utxo/LOCK``).
- Threshold/resume decision table + flush-time tripwire: the
  uint16 flush-id overflow crash at 65,536 must be pre-empted at
  55,000 on every path, regardless of ``SKIP_COMPACT``.
"""
import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from electrumx.server.db import DB as UpstreamDB

import main
from server.compact_policy import (
    COMPACT_EXIT_CODE,
    CompactRestartRequested,
    DEFAULT_THRESHOLD,
    ENVVAR,
    parse_threshold,
    should_compact,
)
from server.db import Database


class ParseThresholdTests(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.pop(ENVVAR, None)

    def tearDown(self):
        if self._old is None:
            os.environ.pop(ENVVAR, None)
        else:
            os.environ[ENVVAR] = self._old

    def test_default_when_unset(self):
        self.assertEqual(parse_threshold(), 55000)
        self.assertEqual(parse_threshold(), DEFAULT_THRESHOLD)

    def test_default_when_empty(self):
        self.assertEqual(parse_threshold(''), 55000)
        self.assertEqual(parse_threshold('   '), 55000)

    def test_env_override(self):
        os.environ[ENVVAR] = '1000'
        self.assertEqual(parse_threshold(), 1000)

    def test_explicit_arg(self):
        self.assertEqual(parse_threshold('12345'), 12345)

    def test_invalid_exits(self):
        for bad in ('nope', '-5', '0', '3.5'):
            with self.assertRaises(SystemExit, msg=bad):
                parse_threshold(bad)

    def test_invalid_env_exits(self):
        os.environ[ENVVAR] = 'bogus'
        with self.assertRaises(SystemExit):
            parse_threshold()


class ShouldCompactTests(unittest.TestCase):
    def test_first_sync_never_compacts(self):
        for first_sync in (True, None):
            do, reason = should_compact(first_sync, 'false', 60000, -1,
                                        DEFAULT_THRESHOLD)
            self.assertEqual((do, reason), (False, 'first-sync'))

    def test_unconditional_legacy_path(self):
        do, reason = should_compact(False, 'false', 10, -1,
                                    DEFAULT_THRESHOLD)
        self.assertEqual((do, reason), (True, 'unconditional'))

    def test_resume_beats_skip(self):
        # Interrupted compaction + SKIP_COMPACT=true must resume:
        # serving now would cancel it and lose the progress.
        do, reason = should_compact(False, 'true', 10, 0,
                                    DEFAULT_THRESHOLD)
        self.assertEqual((do, reason), (True, 'resume'))

    def test_threshold_heals_despite_skip(self):
        do, reason = should_compact(False, 'true', 55000, -1,
                                    DEFAULT_THRESHOLD)
        self.assertEqual((do, reason), (True, 'threshold'))

    def test_threshold_boundary(self):
        do, _ = should_compact(False, 'true', 54999, -1,
                               DEFAULT_THRESHOLD)
        self.assertFalse(do)
        do, _ = should_compact(False, 'true', 55001, -1,
                               DEFAULT_THRESHOLD)
        self.assertTrue(do)

    def test_below_threshold_skips(self):
        do, reason = should_compact(False, 'true', 1067, -1,
                                    DEFAULT_THRESHOLD)
        self.assertEqual((do, reason), (False, 'below-threshold'))


class FakeHistory:
    def __init__(self, flush_count):
        self.flush_count = flush_count
        self.close_called = False

    def close_db(self):
        self.close_called = True


class FakeUtxoDb:
    def __init__(self):
        self.close_called = False

    def close(self):
        self.close_called = True


def _bare_database(first_sync=False, flush_count=0, threshold=55000):
    db = Database.__new__(Database)
    db.first_sync = first_sync
    db.history = FakeHistory(flush_count)
    db.utxo_db = FakeUtxoDb()
    db.compact_threshold = threshold
    return db


class TripwireTests(unittest.TestCase):
    def test_trips_at_threshold(self):
        db = _bare_database(first_sync=False, flush_count=55000)
        with patch.object(UpstreamDB, 'flush_dbs', return_value=None):
            with self.assertRaises(CompactRestartRequested):
                db.flush_dbs(None, True, None)

    def test_trips_above_threshold(self):
        db = _bare_database(first_sync=False, flush_count=65535)
        with patch.object(UpstreamDB, 'flush_dbs', return_value=None):
            with self.assertRaises(CompactRestartRequested):
                db.flush_dbs(None, True, None)

    def test_quiet_below_threshold(self):
        db = _bare_database(first_sync=False, flush_count=54999)
        with patch.object(UpstreamDB, 'flush_dbs', return_value=None):
            db.flush_dbs(None, True, None)  # must not raise

    def test_quiet_during_first_sync(self):
        for first_sync in (True, None):
            db = _bare_database(first_sync=first_sync, flush_count=60000)
            with patch.object(UpstreamDB, 'flush_dbs', return_value=None):
                db.flush_dbs(None, True, None)  # must not raise

    def test_upstream_flush_runs_first(self):
        # The committed flush must precede the tripwire: on-disk state
        # is consistent when the process exits for restart.
        calls = []
        db = _bare_database(first_sync=False, flush_count=55000)

        def fake_flush(_self, *args):
            calls.append('flush')

        with patch.object(UpstreamDB, 'flush_dbs', fake_flush):
            with self.assertRaises(CompactRestartRequested):
                db.flush_dbs(None, True, None)
        self.assertEqual(calls, ['flush'])

    def test_custom_threshold(self):
        db = _bare_database(first_sync=False, flush_count=1000,
                            threshold=1000)
        with patch.object(UpstreamDB, 'flush_dbs', return_value=None):
            with self.assertRaises(CompactRestartRequested):
                db.flush_dbs(None, True, None)


class CloseHelperTests(unittest.TestCase):
    def test_closes_both_handles(self):
        db = _bare_database()
        main._close_compacting_db(db)
        self.assertTrue(db.utxo_db.close_called)
        self.assertTrue(db.history.close_called)

    def test_history_closed_even_if_utxo_close_fails(self):
        db = _bare_database()

        def boom():
            raise IOError('lock busy')

        db.utxo_db.close = boom
        with self.assertRaises(IOError):
            main._close_compacting_db(db)
        self.assertTrue(db.history.close_called)


class ExitCodeTests(unittest.TestCase):
    def test_compact_exit_code_is_distinct_from_crash(self):
        self.assertEqual(COMPACT_EXIT_CODE, 75)
        self.assertNotEqual(COMPACT_EXIT_CODE, 1)


class AbnormalCompactionTests(unittest.TestCase):
    def test_abnormal_compaction_exits_1_without_serving(self):
        # A crashing compact_history must fail loud: serving now
        # would cancel any partial compaction and mask the DB
        # problem.  Controller must never be reached.
        # NOTE: ``coin``/``db_dir`` bind at import time, so they are
        # patched on the module, not via the environment.
        with patch.dict(os.environ, {'SKIP_COMPACT': 'true'}):
            with patch.object(main, 'coin', 'BLOCK'):
                with patch.object(main, 'compact_history',
                                  new_callable=AsyncMock,
                                  side_effect=RuntimeError('disk gone')):
                    fake_env = MagicMock()
                    fake_env.default.return_value = '%(message)s'
                    with patch.object(main, 'Env', return_value=fake_env):
                        with patch.object(main, 'isdir', return_value=True):
                            with patch.object(main, 'Controller') as ctrl:
                                with self.assertRaises(SystemExit) as cm:
                                    main.main(db_compacted=False)
                            self.assertEqual(cm.exception.code, 1)
                            ctrl.assert_not_called()


class ServeTripwireExitTests(unittest.TestCase):
    def test_serve_tripwire_maps_to_exit_75(self):
        # CompactRestartRequested escaping server.run() must become
        # a clean COMPACT_RESTART exit, not a crash exit 1.
        server = MagicMock()
        server.run = AsyncMock(
            side_effect=CompactRestartRequested(
                'flush_count 55,000 >= threshold 55,000'))
        fake_env = MagicMock()
        fake_env.default.return_value = '%(message)s'
        with patch.dict(os.environ, {'SKIP_COMPACT': 'true'}):
            with patch.object(main, 'coin', 'BLOCK'):
                with patch.object(main, 'Env', return_value=fake_env):
                    with patch.object(main, 'isdir', return_value=True):
                        with patch.object(main, 'Controller',
                                          return_value=server):
                            with self.assertRaises(SystemExit) as cm:
                                main.main(db_compacted=True)
                            self.assertEqual(cm.exception.code,
                                             COMPACT_EXIT_CODE)


class DeleteLockFilesTests(unittest.TestCase):
    def test_removes_both_locks_under_db_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            for sub in ('utxo', 'hist'):
                os.makedirs(os.path.join(tmp, sub))
                open(os.path.join(tmp, sub, 'LOCK'), 'w').close()
            with patch.object(main, 'db_dir', tmp):
                main.delete_lock_files()  # must not raise
            self.assertFalse(os.path.exists(os.path.join(tmp, 'utxo',
                                                          'LOCK')))
            self.assertFalse(os.path.exists(os.path.join(tmp, 'hist',
                                                          'LOCK')))

    def test_missing_locks_are_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(main, 'db_dir', tmp):
                main.delete_lock_files()  # must not raise


class FakeCompactHistory:
    def __init__(self, flush_count, comp_cursor):
        self.flush_count = flush_count
        self.comp_cursor = comp_cursor
        self.comp_flush_count = 0
        self.compact_calls = 0
        self.closed = False

    def _compact_history(self, limit):
        self.compact_calls += 1
        self.comp_cursor = -1  # completes in one pass

    def close_db(self):
        self.closed = True


class FakeCompactDb:
    def __init__(self, first_sync=False, flush_count=10, comp_cursor=-1):
        self.first_sync = first_sync
        self.history = FakeCompactHistory(flush_count, comp_cursor)
        self.utxo_db = FakeUtxoDb()
        self.flushed_to = None

    async def open_for_compacting(self):
        pass

    def set_flush_count(self, value):
        self.flushed_to = value


class CompactHistoryIntegrationTests(unittest.TestCase):
    def _run(self, db, skip='true', threshold=55000):
        with patch.object(main, 'Database', return_value=db):
            with patch.object(main, 'delete_lock_files') as locks:
                result = asyncio.run(
                    main.compact_history(MagicMock(), threshold, skip))
        return result, locks

    def test_skip_path_closes_and_deletes_locks(self):
        db = FakeCompactDb(flush_count=1067)
        result, locks = self._run(db)
        self.assertEqual(result, 'skipped')
        self.assertTrue(db.utxo_db.close_called)
        self.assertTrue(db.history.closed)
        locks.assert_called_once_with()
        self.assertEqual(db.history.compact_calls, 0)

    def test_threshold_path_compacts_and_records_flush(self):
        db = FakeCompactDb(flush_count=55000)
        result, locks = self._run(db)
        self.assertEqual(result, 'compacted')
        self.assertEqual(db.history.compact_calls, 1)
        self.assertEqual(db.flushed_to, 55000)
        self.assertTrue(db.utxo_db.close_called)
        self.assertTrue(db.history.closed)
        locks.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
