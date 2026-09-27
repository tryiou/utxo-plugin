import asyncio
import os
from aiorpcx import run_in_thread
from electrumx.server.db import DB


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
