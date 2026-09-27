import asyncio
import os
from aiorpcx import run_in_thread
from electrumx.server.db import DB
from server.compact_policy import CompactRestartRequested, parse_threshold


# Slice size for cooperative header hashing.  Upstream builds the header
# Merkle cache by hashing every header in one synchronous loop
# (MerkleCache.initialize -> fs_block_hashes), which wedges the event
# loop for hours on large AuxPoW chains (Dogecoin: ~6.4M dynamic headers
# x scrypt; no await anywhere in the loop).  Hashing in slices with a
# loop yield between slices keeps sessions servable throughout the
# populate: worst scheduling block ~= CHUNK x per-header cost.
MERKLE_CHUNK_HEADERS_DEFAULT = 100
MERKLE_CHUNK_ENVVAR = 'MERKLE_CHUNK_HEADERS'


class Database(DB):
    def __init__(self, env):
        super().__init__(env)
        # Fail fast on a bad threshold at startup, not mid-serve.
        self.compact_threshold = parse_threshold()

    @staticmethod
    def merkle_chunk_size():
        try:
            return max(1, int(os.environ.get(MERKLE_CHUNK_ENVVAR,
                                             MERKLE_CHUNK_HEADERS_DEFAULT)))
        except (TypeError, ValueError):
            return MERKLE_CHUNK_HEADERS_DEFAULT

    async def fs_block_hashes(self, height, count):
        """Chunked variant of the upstream method: identical hashes, but
        yields to the event loop every chunk so long populates (millions
        of headers) never starve sessions, mempool sync, or block
        processing.  Non-empty small counts take a single chunk: one extra
        no-op yield, no behavior change; empty counts yield nothing."""
        if count < 0:
            # Preserve upstream input validation (DBError) verbatim.
            return await super().fs_block_hashes(height, count)
        chunk = self.merkle_chunk_size()
        hashes = []
        done = 0
        # Progress lines (~every 5%) only for long populates; per-block
        # extends and proof-adjacent calls stay as silent as upstream.
        verbose = count >= 1000
        mark = max(1, count // 20)
        for start in range(height, height + count, chunk):
            n = min(chunk, height + count - start)
            hashes.extend(await super().fs_block_hashes(start, n))
            done += n
            if verbose and (done == count
                            or done // mark != (done - n) // mark):
                self.logger.info(f'hashed {done:,d}/{count:,d} headers')
            await asyncio.sleep(0)
        return hashes

    def flush_dbs(self, flush_data, flush_utxos, estimate_txs_remaining):
        """Upstream flush plus the serve-time compaction tripwire.

        The flush is committed first, so on-disk state is consistent
        when the tripwire fires.  Raising (rather than exiting here)
        is the cross-thread vehicle: this runs in a flush worker
        thread, and only an exception propagating to ``main`` stops
        the process -- a ``sys.exit`` here would merely kill the
        worker thread.  ``main`` turns this into a clean
        COMPACT_RESTART exit, and the restart policy bounces the
        container straight into ``compact_history`` on next boot.
        Gated on ``not first_sync``: an initial sync is one long
        catch-up, not steady serving, and there is nothing worth
        compacting yet.
        """
        super().flush_dbs(flush_data, flush_utxos, estimate_txs_remaining)
        if not self.first_sync and self.first_sync is not None:
            flush_count = self.history.flush_count
            if flush_count >= self.compact_threshold:
                raise CompactRestartRequested(
                    'flush_count {:,d} >= threshold {:,d}; exiting '
                    'for compaction restart'.format(
                        flush_count, self.compact_threshold))

    async def raw_block(self, height):
        if height < 0:
            raise self.DBError(f'{height:,d} not on disk')

        def get_block():
            try:
                return height, bytes(self.read_raw_block(height)).hex()
            except FileNotFoundError:
                return None, None

        return await run_in_thread(get_block)

    async def raw_blocks(self, last_height, count):
        if last_height < 0 or count < 0:
            raise self.DBError(f'{count:,d} blocks starting at '
                               f'{last_height:,d} not on disk')

        def get_blocks():
            heights = range(last_height, last_height - count, -1)
            try:
                return [(height, bytes(self.read_raw_block(height)).hex()) for height in heights]
            except FileNotFoundError:
                return []

        return await run_in_thread(get_blocks)
