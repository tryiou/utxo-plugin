from electrumx.lib.lrucache import LRUCache
from electrumx.server.session import SessionManager


class SessionManagerMixin(SessionManager):
    def __init__(self, env, db, bp, daemon, mempool, shutdown_event):
        super().__init__(
            env=env,
            db=db,
            block_processor=bp,
            daemon=daemon,
            mempool=mempool,
            shutdown_event=shutdown_event,
        )
        self.bsub_results = None
        self.history_address_cache = LRUCache(maxsize=1000)

    async def _notify_sessions(self, height, touched):
        for cache in (self._txids_cache, self._merkle_txid_cache):
            for key in range(height, self.db.db_height + 1):
                if key in cache:
                    del cache[key]

        height_changed = height != self.notified_height
        if height_changed:
            await self._refresh_hsub_results(height)
            await self._refresh_bsub_results(height)

            # Invalidate our history cache for touched hashXs
            cache = self._history_cache
            for hashX in set(cache).intersection(touched):
                del cache[hashX]

        for session in self.sessions:
            if self._task_group.joined:  # this can happen during shutdown
                self.logger.warning(
                    "task group already terminated. not notifying sessions.",
                )
                return
            await self._task_group.spawn(session.notify, touched, height_changed)

    async def _refresh_bsub_results(self, height):
        """Refresh cached raw block"""
        height = min(height, self.db.db_height)
        _, raw = await self.db.raw_block(height)
        self.bsub_results = {"hex": raw, "height": height}
        self.logger.info(f"Updated block subscription height: {height}")
