#!/bin/sh
set -e

# Bootstrap data-dir ownership when started as root, then drop privileges.
if [ "$(id -u)" = "0" ]; then
    DATA_DIR="/app/plugins/utxoplugin-${PLUGIN_COIN:?}"
    mkdir -p "$DATA_DIR"
    chown -R utxo:utxo "$DATA_DIR" || true
    exec gosu utxo:utxo "$@"
fi

exec "$@"
