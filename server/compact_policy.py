"""Single home for history-compaction policy (SOC/DRY).

Both the startup path (``main.compact_history``) and the serve-time
tripwire (``server.db.Database.flush_dbs``) decide from here, so the
threshold, the decision table, and the restart exit code exist exactly
once.  Everything in this module except ``parse_threshold``'s failure
exit is pure and unit-testable.
"""

import os
import sys

#: Environment variable overriding the threshold.
ENVVAR = "AUTO_COMPACT_THRESHOLD"

#: Default: compact once the history flush count reaches this.
#: Upstream ElectrumX packs the flush id as uint16
#: (``history.flush`` -> ``pack_be_uint16``), so the server dies at
#: 65,536.  55,000 leaves ~10.5k flushes of headroom.
DEFAULT_THRESHOLD = 55000

#: Process exit code for a deliberate compaction restart (sysexits.h
#: EX_TEMPFAIL: "temporary failure, retry").  Distinct from crash
#: exit 1 so restarts are greppable in docker events.  The
#: ``unless-stopped`` restart policy restarts on any code.
COMPACT_EXIT_CODE = 75


class CompactRestartRequested(Exception):
    """Raised by the serve-time tripwire after a committed flush crossed
    the threshold.  Propagates to ``main`` (a plain ``sys.exit`` here
    would only kill the flush worker thread), which logs one clean
    line and exits with :data:`COMPACT_EXIT_CODE`."""


def parse_threshold(raw=None):
    """Return the compaction threshold as a positive int.

    ``raw`` overrides; when ``None`` the ``AUTO_COMPACT_THRESHOLD``
    environment variable is read, defaulting to
    :data:`DEFAULT_THRESHOLD`.  Invalid values fail fast with
    ``sys.exit(1)`` -- never a silent fallback (a wrong threshold is
    either a crash loop waiting to happen or compaction on every
    boot).
    """
    if raw is None:
        raw = os.environ.get(ENVVAR, "")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return DEFAULT_THRESHOLD
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        value = -1
    if value <= 0:
        print(
            f"[utxoplugin] ERROR: {ENVVAR} must be a positive integer, got {raw!r}",
            file=sys.stderr,
        )
        sys.exit(1)
    return value


def should_compact(first_sync, skip_compacting, flush_count, comp_cursor, threshold):
    """Decide whether to compact on boot.

    Returns ``(do_compact, reason)``.  Table, in priority order:

    - ``first-sync``: initial sync in progress (or unknown state) --
      never compact, there is nothing worth compacting yet.
    - ``unconditional``: legacy path, ``SKIP_COMPACT`` is not
      ``'true'``.
    - ``resume``: a previous compaction was interrupted
      (``comp_cursor != -1``); restarting serve would cancel it and
      lose the progress, so it must be resumed.
    - ``threshold``: heal-always path -- ``flush_count`` reached the
      threshold regardless of ``SKIP_COMPACT``.
    - ``below-threshold``: nothing to do, go straight to serving.
    """
    if first_sync or first_sync is None:
        return False, "first-sync"
    if skip_compacting != "true":
        return True, "unconditional"
    if comp_cursor != -1:
        return True, "resume"
    if flush_count >= threshold:
        return True, "threshold"
    return False, "below-threshold"
