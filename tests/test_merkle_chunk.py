"""Red-green tests for chunked header Merkle-cache population.

Covers the fix for the event-loop wedge observed on large AuxPoW chains
(Dogecoin: ~6.4M dynamic headers x scrypt): upstream
``DB.fs_block_hashes`` hashes every header in one synchronous loop with no
``await``, so the whole server goes dark for hours while
``MerkleCache.initialize`` runs.  The ``Database`` override under test
processes headers in ``MERKLE_CHUNK_HEADERS`` slices and yields to the loop
between slices.

Test strategy is deterministic (no wall-clock thresholds):
a heartbeat task counting raw loop passes can only advance when the code
under test yields.
"""
import asyncio
import logging
import os
import unittest

from electrumx.lib.hash import sha256
from electrumx.lib.merkle import Merkle, MerkleCache

from server.db import Database


HEADER_LEN = 80
ENV_KEY = 'MERKLE_CHUNK_HEADERS'


def async_test(f):
    def wrapper(*args, **kwargs):
        asyncio.run(f(*args, **kwargs))
    return wrapper


class StubCoin:
    STATIC_BLOCK_HEADERS = True

    @staticmethod
    def header_hash(header):
        return sha256(sha256(header))


class StubDB(Database):
    """Database double serving N synthetic fixed-size headers.

    Deliberately bypasses ``DB.__init__`` (needs Env + on-disk DBs) and
    serves headers from memory.  Only the attributes touched by
    ``fs_block_hashes`` are provided.
    """

    def __init__(self, count):
        # NOTE: super().__init__ intentionally not called (see class doc).
        self.logger = logging.getLogger('test_merkle_chunk')
        self.coin = StubCoin
        self.db_height = count - 1
        self._headers = b''.join(
            bytes([n % 256]) * HEADER_LEN for n in range(count)
        )

    async def read_headers(self, start_height, count):
        disk = max(0, min(count, self.db_height + 1 - start_height))
        if not disk:
            return b'', 0
        off = start_height * HEADER_LEN
        return self._headers[off:off + disk * HEADER_LEN], disk

    def header_len(self, height):
        return HEADER_LEN


async def run_with_heartbeat(coro):
    """Drive ``coro`` while a heartbeat task counts raw loop passes.

    Returns ``(result, passes)``.  ``passes`` can only grow when the code
    under test yields control back to the event loop.
    """
    passes = 0
    done = False

    async def heartbeat():
        nonlocal passes
        while not done:
            passes += 1
            await asyncio.sleep(0)

    task = asyncio.ensure_future(heartbeat())
    try:
        result = await coro
    finally:
        done = True
        await task
    return result, passes


class TestChunkedBlockHashes(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get(ENV_KEY)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop(ENV_KEY, None)
        else:
            os.environ[ENV_KEY] = self._saved

    @async_test
    async def test_heartbeat_runs_during_populate(self):
        """Loop must stay responsive while hashing headers.

        FAILS on unpatched code (inherited upstream method never yields,
        heartbeat records 0 passes); PASSES with the chunked override
        (one yield per chunk of 10 over 500 headers -> >= 50 passes).
        """
        os.environ[ENV_KEY] = '10'
        db = StubDB(500)
        _, passes = await run_with_heartbeat(db.fs_block_hashes(0, 500))
        self.assertGreaterEqual(passes, 50)

    @async_test
    async def test_chunked_output_matches_single_shot(self):
        """Chunking must not change a single hash for any length/chunk mix."""
        for count in (0, 1, 7, 100, 101, 500):
            with self.subTest(count=count):
                os.environ[ENV_KEY] = '7'
                chunked = await StubDB(count).fs_block_hashes(0, count)
                os.environ[ENV_KEY] = str(10 ** 9)
                single = await StubDB(count).fs_block_hashes(0, count)
                self.assertEqual(chunked, single)

    @async_test
    async def test_chunked_output_matches_merkle_root(self):
        """End-to-end: real MerkleCache roots agree chunked vs single-shot."""
        os.environ[ENV_KEY] = '7'
        chunked = await StubDB(300).fs_block_hashes(0, 300)
        os.environ[ENV_KEY] = str(10 ** 9)
        single = await StubDB(300).fs_block_hashes(0, 300)
        async def source(hashes):
            async def get(start, n):
                return hashes[start:start + n]
            return get
        # initialize() returns None; compare via fresh caches' branches
        mc1, mc2 = MerkleCache(Merkle(), await source(chunked)), \
            MerkleCache(Merkle(), await source(single))
        await mc1.initialize(len(chunked))
        await mc2.initialize(len(single))
        self.assertEqual(
            await mc1.branch_and_root(len(chunked), len(chunked) - 1),
            await mc2.branch_and_root(len(single), len(single) - 1),
        )

    @async_test
    async def test_garbage_chunk_env_falls_back_to_default(self):
        """A non-integer knob value must not crash population."""
        os.environ[ENV_KEY] = 'not-a-number'
        hashes = await StubDB(25).fs_block_hashes(0, 25)
        self.assertEqual(25, len(hashes))

    @async_test
    async def test_negative_count_raises_like_upstream(self):
        """Input validation parity: negative counts raise DBError."""
        with self.assertRaises(Database.DBError):
            await StubDB(10).fs_block_hashes(0, -1)

    def test_small_counts_stay_silent(self):
        """Per-block extends must not spam progress lines like upstream."""
        with self.assertNoLogs('test_merkle_chunk', level='INFO'):
            asyncio.run(StubDB(25).fs_block_hashes(0, 25))


if __name__ == '__main__':
    unittest.main()
