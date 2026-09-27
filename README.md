# utxoplugin

### Deployment Process
Within the EXR ENV, one utxo-plugin container should be deployed for each utxo coin to be indexed.
Example docker-compose.yml entry for utxo coin, BLOCK:
```yaml
  utxo-plugin-block:
    image: blocknetdx/utxo-plugin:latest
    restart: unless-stopped
    environment:
      PLUGIN_COIN: 'BLOCK'
      PLUGIN_PORT: 8000
      DB_ENGINE: 'rocksdb'
      NETWORK: 'mainnet'
      SKIP_COMPACT: 'true'
      AUTO_COMPACT_THRESHOLD: '55000'
      DAEMON_ADDR: 172.31.4.37
      DAEMON_RPC_PORT: '41414'
      RPC_USER: "${RPC_USER}"
      RPC_PASSWORD: "${RPC_PASSWORD}"
    stop_signal: SIGINT
    stop_grace_period: 5m
    volumes:
      - /snode/utxo_plugin/BLOCK:/app/plugins/utxoplugin-BLOCK
    logging:
      driver: "json-file"
      options:
        max-size: "2m"
        max-file: "10"
    depends_on:
      - snode
    networks:
      backend:
        ipv4_address: 172.31.8.23
```
DAEMON_ADDR is the IP addr of the container hosting the BLOCK daemon

DAEMON_RPC_PORT is the RPC port of the BLOCK daemon

AUTO_COMPACT_THRESHOLD is the history flush count at which the plugin
heals itself (default '55000', upstream ElectrumX dies at 65,536).
On boot the plugin compacts when the count is reached, whatever
SKIP_COMPACT says; while serving, crossing it exits the process with
code 75 so the container restart policy bounces it straight into
compaction. Set a lower value temporarily to drill the loop.

