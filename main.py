import asyncio
import logging
import sys
import traceback
from os import environ
from pathlib import Path

from electrumx import Env
from electrumx.lib.util import CompactFormatter, make_logger

from server.compact_policy import (
    COMPACT_EXIT_CODE,
    CompactRestartRequested,
    parse_threshold,
    should_compact,
)
from server.controller import Controller
from server.db import Database
from server.utxoplugin_coins import (
    BitcoinCash,
    BitcoinSegwit,
    Bitcore,
    Blocknet,
    BlocknetTestnet,
    Coin,
    Dash,
    DigiByte,
    Dogecoin,
    Litecoin,
    Pivx,
    Pkoin,
    Ravencoin,
    Syscoin,
    Unobtanium,
    Verge,
)

coin_map = {
    "BLOCK": Blocknet,
    "TBLOCK": BlocknetTestnet,
    "BTC": BitcoinSegwit,
    "BCH": BitcoinCash,
    "BTX": Bitcore,
    "SYS": Syscoin,
    "LTC": Litecoin,
    "DASH": Dash,
    "DGB": DigiByte,
    "DOGE": Dogecoin,
    "RVN": Ravencoin,
    "PIVX": Pivx,
    "UNO": Unobtanium,
    "PKOIN": Pkoin,
    "XVG": Verge,
}

coin = environ.get("PLUGIN_COIN")
db_dir = f"{Path.cwd()}/utxoplugin-{coin}"

port = environ.get("PLUGIN_PORT", "8000")

environ["DB_ENGINE"] = environ.get("DB_ENGINE") or "rocksdb"
environ["COST_SOFT_LIMIT"] = "0"
environ["COST_HARD_LIMIT"] = "0"
environ["INITIAL_CONCURRENT"] = "1000"
environ["SERVICES"] = f"tcp://:{int(port) + 1000},rpc://:{port},ws://:50000"


async def compact_history(env, threshold, skip_compacting):
    environ["DAEMON_URL"] = ""  # Avoid Env erroring out
    db = Database(env)
    await db.open_for_compacting()

    # State is read from the already-open handle: opening a second
    # (serve-flavoured) handle would cancel an in-progress compaction.
    history = db.history
    do_compact, reason = should_compact(
        db.first_sync,
        skip_compacting,
        history.flush_count,
        history.comp_cursor,
        threshold,
    )
    print(
        "[utxoplugin] compact decision: {} reason={} flush_count={} "
        "threshold={} comp_cursor={}".format(
            "compact" if do_compact else "skip",
            reason,
            history.flush_count,
            threshold,
            history.comp_cursor,
        ),
    )

    if not do_compact:
        _close_compacting_db(db)
        delete_lock_files()
        return "skipped"

    # Continue where we left off, if interrupted
    if history.comp_cursor == -1:
        history.comp_cursor = 0

    history.comp_flush_count = max(history.comp_flush_count, 1)
    limit = 8 * 1000 * 1000

    while history.comp_cursor != -1:
        history._compact_history(limit)  # noqa: SLF001 - stock private API

    # When completed also update the UTXO flush count
    db.set_flush_count(history.flush_count)

    _close_compacting_db(db)

    delete_lock_files()

    return "compacted"


def _close_compacting_db(db):
    # Explicitly close both handles before serving: the serve phase
    # opens fresh handles in a new Database, and a lingering open
    # handle self-locks the DB (RocksIOError: ... LOCK).
    try:
        if db.utxo_db is not None:
            db.utxo_db.close()
    finally:
        db.history.close_db()
    print("[utxoplugin] compacting DB handles closed")


def delete_lock_files():
    # Absolute paths: this runs both pre-open (CWD is /app/plugins)
    # and post-compaction (CWD is already the data dir after the
    # upstream chdir), so relative removes only hit in the latter
    # case -- absolute hits in both.
    try:
        Path(db_dir, "utxo/LOCK").unlink()
    except OSError as e:
        print(e)

    try:
        Path(db_dir, "hist/LOCK").unlink()
    except OSError as e:
        print(e)


def main(db_compacted=False):
    network = environ.get("NETWORK")
    skip_compacting = environ.get("SKIP_COMPACT", "false")
    threshold = parse_threshold()

    print(f"[utxoplugin] Data-Directory: {db_dir}")

    delete_lock_files()

    coin_host_addr = environ.get("DAEMON_ADDR")
    rpc_port = environ.get("DAEMON_RPC_PORT")
    rpc_user = environ.get("RPC_USER")
    rpc_pass = environ.get("RPC_PASSWORD")

    if coin_host_addr is None or rpc_port is None:
        print("[utxoplugin] ERROR: Couldn't find coin host or rpc port!")

    url = f"http://{rpc_user}:{rpc_pass}@{coin_host_addr}:{rpc_port}"

    if coin in coin_map:
        MappedCoin = coin_map[coin]
    else:
        if network is None:
            network = "mainnet"

        MappedCoin = Coin.lookup_coin_class(coin, network)

    environ["DAEMON_URL"] = url
    environ["DB_DIRECTORY"] = db_dir

    if not Path(db_dir).is_dir() and not Path(db_dir).exists():
        Path(db_dir).mkdir()
    elif not Path(db_dir).is_dir() and Path(db_dir).exists():
        print(
            "[utxoplugin] ERROR: "
            + db_dir
            + " exists and is not a directory. Requiring manual deletion.",
        )
        sys.exit(1)

    env = Env(coin=MappedCoin)

    print(f"[utxoplugin] Coin: {coin}, Port: {port}, Daemon RPC Port: {rpc_port}")
    print(f"[utxoplugin] Using daemon RPC at {coin_host_addr}:{rpc_port}")

    env.rpc_port = port
    print("[utxoplugin] Starting RPC on port " + str(env.rpc_port))

    # Always enter the compaction path on a fresh boot: the threshold
    # is only knowable after opening the DB, so the heal-always
    # decision (threshold/resume regardless of SKIP_COMPACT) lives
    # inside compact_history.
    if not db_compacted:
        print("[utxoplugin] compacting db history check")

        try:
            result = asyncio.run(compact_history(env, threshold, skip_compacting))
        except Exception:  # noqa: BLE001 - any compaction failure must refuse to serve
            # Fail loud: serving now would cancel any partial
            # compaction and mask the underlying DB problem.
            traceback.print_exc()
            print(
                "[utxoplugin] History compaction terminated "
                "abnormally; refusing to serve",
            )
            sys.exit(1)
        else:
            print(f"[utxoplugin] History compaction {result}")

        del env
        return main(db_compacted=True)

    log_fmt = env.default("LOG_FORMAT", "%(levelname)s:%(name)s:%(message)s")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(CompactFormatter(log_fmt))
    make_logger("electrumx", handler=handler, level=logging.DEBUG)

    server = Controller(env)
    try:
        asyncio.run(server.run())
    except CompactRestartRequested as e:
        # Serve-time tripwire (server.db.Database.flush_dbs): the
        # flush count crossed the threshold after a committed flush.
        # Exit for a compaction restart; the restart policy bounces
        # the container straight into compact_history on next boot.
        print(f"[utxoplugin] COMPACT_RESTART: {e}")
        sys.exit(COMPACT_EXIT_CODE)
    except (KeyboardInterrupt, SystemExit, Exception):  # noqa: BLE001 - top-level guard must exit 1 on anything; CancelledError/GeneratorExit intentionally propagate
        print("[utxoplugin] main: fatal, asyncio.run raised:")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
