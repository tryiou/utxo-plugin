from asyncio import Event

import electrumx
from aiorpcx import _version as aiorpcx_version
from electrumx.lib.server_base import ServerBase
from electrumx.lib.util import OldTaskGroup, version_string
from electrumx.server.controller import Notifications
from electrumx.server.mempool import MemPool, MemPoolAPI

from server.db import Database
from server.sessionmanager import SessionManagerMixin


class Controller(ServerBase):
    """Upstream controller with local Database and SessionManagerMixin."""

    async def serve(self, shutdown_event):
        """Upstream serve flow with local Database and SessionManagerMixin."""
        try:
            env = self.env
            min_str, max_str = env.coin.SESSIONCLS.protocol_min_max_strings()
            self.logger.info(f"software version: {electrumx.version}")
            self.logger.info(f"aiorpcX version: {version_string(aiorpcx_version)}")
            self.logger.info(f"supported protocol versions: {min_str}-{max_str}")
            self.logger.info(f"event loop policy: {env.loop_policy}")
            self.logger.info(f"reorg limit is {env.reorg_limit:,d} blocks")

            notifications = Notifications()
            Daemon = env.coin.DAEMON
            BlockProcessor = env.coin.BLOCK_PROCESSOR

            async with Daemon(env.coin, env.daemon_url) as daemon:
                db = Database(env)
                bp = BlockProcessor(env, db, daemon, notifications)

                def get_db_height():
                    return db.db_height

                notifications.height = daemon.height
                notifications.db_height = get_db_height
                notifications.cached_height = daemon.cached_height
                notifications.mempool_hashes = daemon.mempool_hashes
                notifications.raw_transactions = daemon.getrawtransactions
                notifications.lookup_utxos = db.lookup_utxos
                MemPoolAPI.register(Notifications)
                mempool = MemPool(
                    env.coin,
                    notifications,
                    refresh_secs=env.daemon_poll_interval_mempool_msec / 1000,
                )

                session_mgr = SessionManagerMixin(
                    env,
                    db,
                    bp,
                    daemon,
                    mempool,
                    shutdown_event,
                )

                await daemon.height()

                # Check if daemon is recent enough
                await daemon.check_daemon_version()
                await daemon.check_daemon_indexes()

                caught_up_event = Event()
                mempool_event = Event()

                async def wait_for_catchup():
                    await caught_up_event.wait()
                    await group.spawn(db.populate_header_merkle_cache())
                    await group.spawn(mempool.keep_synchronized(mempool_event))

                async with OldTaskGroup() as group:
                    await group.spawn(session_mgr.serve(notifications, mempool_event))
                    await group.spawn(bp.fetch_and_process_blocks(caught_up_event))
                    await group.spawn(wait_for_catchup())
        except Exception:
            self.logger.exception("fatal error in Controller.serve")
            raise
