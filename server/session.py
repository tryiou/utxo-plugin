import sys

import electrumx
from electrumx.lib.hash import hash_to_hex_str
from electrumx.server.session import ElectrumX as _StockElectrumX
from electrumx.server.session import non_negative_integer


def truncate(n, decimals=0):
    s = "{0:.{1}f}".format(n, decimals)
    return float(s)


MIN_SPENDS_TO_COMPARE = 2


class ElectrumX(_StockElectrumX):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.subscribe_blocks = False
        self.set_request_handlers(self.PROTOCOL_MIN)

    @classmethod
    def server_features(cls, env):
        """Return the server features dictionary."""
        hosts_dict = {}
        for service in env.report_services:
            port_dict = hosts_dict.setdefault(str(service.host), {})
            if service.protocol not in port_dict:
                port_dict[f"{service.protocol}_port"] = service.port

        min_str, max_str = cls.protocol_min_max_strings()
        return {
            "hosts": hosts_dict,
            "pruning": None,
            "server_version": electrumx.version,
            "protocol_min": min_str,
            "protocol_max": max_str,
            "genesis_hash": env.coin.GENESIS_HASH,
            "value_per_coin": env.coin.VALUE_PER_COIN,
            "hash_function": "sha256",
            "services": [str(service) for service in env.report_services],
        }

    async def _notify_inner(self, touched, height_changed):
        if height_changed and self.subscribe_headers:
            args = (await self.subscribe_headers_result(),)
            await self.send_notification("blockchain.headers.subscribe", args)

        if height_changed and self.subscribe_blocks:
            args = (await self.subscribe_blocks_result(),)
            await self.send_notification("blockchain.block.subscribe", args)

        touched = touched.intersection(self.hashX_subs)
        if touched or (height_changed and self.mempool_statuses):
            changed = {}

            for hashX in touched:
                alias = self.hashX_subs.get(hashX)
                if alias:
                    status = await self.subscription_address_status(hashX)
                    changed[alias] = status

            mempool_statuses = self.mempool_statuses.copy()
            for hashX, old_status in mempool_statuses.items():
                alias = self.hashX_subs.get(hashX)
                if alias:
                    status = await self.subscription_address_status(hashX)
                    if status != old_status:
                        changed[alias] = status

            method = "blockchain.scripthash.subscribe"
            for alias, status in changed.items():
                await self.send_notification(method, (alias, status))

            if changed:
                es = "" if len(changed) == 1 else "es"
                self.logger.info(f"notified of {len(changed):,d} address{es}")

    async def address_get_balance(self, address):
        """Return the confirmed and unconfirmed balance of an address."""
        hashX = self.coin.address_to_hashX(address)
        return await self.get_balance(hashX)

    async def address_listunspent(self, address):
        """Return the list of UTXOs of an address."""
        hashX = self.coin.address_to_hashX(address)

        utxos = await self.db.all_utxos(hashX)
        utxos = sorted(utxos)
        utxos.extend(await self.mempool.unordered_UTXOs(hashX))
        spends = await self.mempool.potential_spends(hashX)

        return [
            {
                "address": address,
                "tx_hash": hash_to_hex_str(utxo.tx_hash),
                "tx_pos": utxo.tx_pos,
                "height": utxo.height,
                "value": utxo.value,
            }
            for utxo in utxos
            if (utxo.tx_hash, utxo.tx_pos) not in spends
        ]

    async def _block_hash_and_tx_hashes(self, height):
        """Returns a pair (block_hash, tx_hashes) for the main chain block at
        the given height.

        block_hash is a hexadecimal string, and tx_hashes is an
        ordered list of hexadecimal strings.
        """
        height = non_negative_integer(height)
        hex_hashes = await self.daemon_request("block_hex_hashes", height, 1)
        block_hash = hex_hashes[0]
        block = await self.daemon_request("deserialised_block", block_hash)
        return block_hash, block["tx"]

    async def getrawmempool(self, verbose=False):
        if any(verbose == x for x in [1, "1", True, "true", "True"]):
            verbose = True

        args = (verbose,)

        return await self.daemon_request("_send_single", "getrawmempool", args)

    async def getblockcount(self):
        cached_height = self.session_mgr.daemon.cached_height()

        if cached_height is None:
            return await self.session_mgr.daemon.height()

        return cached_height

    async def getblock(self, hex_hash, verbose=False):
        if any(verbose == x for x in [1, "1", True, "true", "True"]):
            verbose = True

        args = (hex_hash, verbose)

        return await self.daemon_request("_send_single", "getblock", args)

    async def getblockhash(self, height):
        block_hash, _ = await self._block_hash_and_tx_hashes(height)

        return block_hash

    async def block_subscribe(self):
        self.subscribe_blocks = True
        return await self.subscribe_blocks_result()

    async def subscribe_blocks_result(self):
        return self.session_mgr.bsub_results

    async def get_address_history(self, addresses):
        addr_lookup = {addresses} if type(addresses) is str else set(addresses)
        spent = []
        spent_ids = set()
        processed_txs = set()  # track transactions that have already been processed
        for raw_address in addr_lookup:
            address = str(raw_address)

            try:
                hash_x = self.session_mgr.history_address_cache[address]
            except KeyError:
                try:
                    hash_x = self.coin.address_to_hashX(address)
                    self.session_mgr.history_address_cache[address] = hash_x
                except Exception:
                    self.logger.exception(
                        "[GetAddressHistory] Exception while converting address",
                    )
                    continue

            try:
                history = await self.db.limited_history(hash_x, limit=100)

                for tx_hash, _height in history:
                    if tx_hash in processed_txs:
                        continue  # skip, already processed
                    tx = await self.transaction_get(
                        hash_to_hex_str(tx_hash),
                        verbose=True,
                    )
                    if not tx:
                        continue
                    processed_txs.add(tx_hash)

                    spends = []
                    from_addresses = set()
                    total_send_amount = 0
                    my_total_send_amount = 0
                    for item in tx["vin"]:
                        if "txid" not in item:
                            continue
                        prev_tx = await self.transaction_get(item["txid"], verbose=True)
                        if not prev_tx:
                            continue

                        prev_out_amount = prev_tx["vout"][item["vout"]]["value"]
                        script_pub_key = prev_tx["vout"][item["vout"]]["scriptPubKey"]
                        addrs = []

                        if "addresses" in script_pub_key:
                            addrs = script_pub_key["addresses"]
                        elif "address" in script_pub_key:
                            addrs = [script_pub_key["address"]]

                        # Record total sent coin if sent from one of our addresses
                        if len(addrs) > 0:
                            is_my_address = False
                            for addr in addrs:
                                if addr in addr_lookup:
                                    my_total_send_amount += prev_out_amount
                                    is_my_address = True
                                    break

                            if not is_my_address:
                                total_send_amount += prev_out_amount

                            from_addresses.update(addrs)

                    my_total_send_amount_running = my_total_send_amount
                    is_sending_coin = my_total_send_amount > 0

                    biggest_sent_amount_not_my_address = 0
                    biggest_sent_address_not_my_address = ""
                    biggest_sent_amount_my_address = 0
                    biggest_sent_address_my_address = ""

                    fees = (total_send_amount + my_total_send_amount) * -1

                    def valid_spend(
                        p_spent_ids,
                        p_address,
                        p_amount,
                        p_category,
                        p_item,
                        p_tx,
                        p_from_addresses,
                    ):
                        p_txid_n = (p_tx["txid"], p_item["n"], p_category)
                        if p_txid_n not in p_spent_ids:
                            return {
                                "address": p_address,
                                "amount": p_amount,
                                "fee": 0.0,
                                "vout": p_item["n"],
                                "category": p_category,
                                "confirmations": p_tx["confirmations"],
                                "blockhash": p_tx["blockhash"],
                                "blocktime": p_tx["blocktime"],
                                "time": p_tx["blocktime"],
                                "txid": p_tx["txid"],
                                "from_addresses": p_from_addresses,
                            }, p_txid_n
                        return None, None

                    def get_address(p_item):

                        if (
                            "type" not in p_item["scriptPubKey"]
                            or p_item["scriptPubKey"]["type"] == "nonstandard"
                        ):
                            return None  # skip incompatible vout

                        if "address" in p_item["scriptPubKey"]:
                            if isinstance(p_item["scriptPubKey"]["address"], str):
                                return p_item["scriptPubKey"]["address"]

                        elif "addresses" in p_item["scriptPubKey"]:
                            if isinstance(p_item["scriptPubKey"]["addresses"], str):
                                return p_item["scriptPubKey"]["addresses"]

                            if (
                                isinstance(p_item["scriptPubKey"]["addresses"], list)
                                and len(p_item["scriptPubKey"]["addresses"]) > 0
                            ):
                                return p_item["scriptPubKey"]["addresses"][0]

                        return None

                    # First pass: only process transactions sent to
                    # another address, record fees
                    for item in tx["vout"]:
                        # Tally output values toward the fee total
                        amount = item["value"]
                        fees += amount
                        vout_address = get_address(item)
                        if not vout_address:
                            continue  # incompatible address, skip

                        if vout_address in addr_lookup:
                            continue  # not our address, skip

                        # Amount is negative for send and positive for receive.
                        # Record sent coin to address if we have outstanding
                        # send amount. Note that my total sent amount is
                        # subtracted by any amounts previously marked sent.
                        # Compare with epsilon instead of 0 to avoid precision
                        # inaccuracies.
                        if my_total_send_amount_running > sys.float_info.epsilon:
                            if biggest_sent_amount_not_my_address < amount:
                                biggest_sent_amount_not_my_address = amount
                                biggest_sent_address_not_my_address = vout_address
                            # amount reported here cannot be larger than my
                            # total send amount
                            adjusted_amount = min(my_total_send_amount_running, amount)
                            # track what we've already recorded as sent
                            my_total_send_amount_running -= adjusted_amount
                            spend, txid_n = valid_spend(
                                spent_ids,
                                vout_address,
                                -float(adjusted_amount),
                                "send",
                                item,
                                tx,
                                list(from_addresses),
                            )
                            if spend:
                                spent_ids.add(txid_n)
                                spends.append(spend)

                    # Second pass: Only process transactions for all our own addresses
                    for item in tx["vout"]:
                        vout_address = get_address(item)
                        if not vout_address:
                            continue  # incompatible address, skip
                        if vout_address not in addr_lookup:
                            continue  # skip, already processed in block above

                        amount = item["value"]

                        do_not_mark_send = False
                        if vout_address not in from_addresses:
                            do_not_mark_send = True

                        # Record received coin if this vout address is mine
                        spend, txid_n = valid_spend(
                            spent_ids,
                            vout_address,
                            float(amount),
                            "receive",
                            item,
                            tx,
                            list(from_addresses),
                        )
                        if spend:
                            spent_ids.add(txid_n)
                            spends.append(spend)

                        # Amount is negative for send and positive for receive.
                        # Record sent coin to address if we have outstanding
                        # send amount. Note that my total sent amount is
                        # subtracted by any amounts previously marked sent.
                        # Compare with epsilon instead of 0 to avoid precision
                        # inaccuracies.
                        if my_total_send_amount_running > sys.float_info.epsilon:
                            # amount reported here cannot be larger than my
                            # total send amount
                            adjusted_amount = min(my_total_send_amount_running, amount)
                            # track what we've already recorded as sent
                            my_total_send_amount_running -= adjusted_amount
                            if not do_not_mark_send:
                                spend, txid_n = valid_spend(
                                    spent_ids,
                                    vout_address,
                                    -float(adjusted_amount),
                                    "send",
                                    item,
                                    tx,
                                    list(from_addresses),
                                )
                                if spend:
                                    spent_ids.add(txid_n)
                                    spends.append(spend)

                                    if biggest_sent_amount_my_address < amount:
                                        biggest_sent_amount_my_address = amount
                                        biggest_sent_address_my_address = vout_address

                    # Assign fees on tx with largest sent amount: to an
                    # address that is not our own, otherwise to the largest
                    # sent transaction on our own address if that applies.
                    if is_sending_coin and fees < 0:
                        for spend in spends:
                            biggest_sent_address = (
                                biggest_sent_address_not_my_address
                                if biggest_sent_amount_not_my_address > 0
                                else biggest_sent_address_my_address
                            )
                            if (
                                spend["address"] == biggest_sent_address
                                and spend["category"] == "send"
                            ):
                                spend["fee"] = truncate(fees, 10)
                                break

                    # Consolidate spends to self
                    remove_these = []
                    if len(spends) >= MIN_SPENDS_TO_COMPARE:
                        for spend in spends:
                            filtered_spends = list(
                                filter(
                                    lambda sp: sp["address"] == spend["address"],
                                    spends,
                                ),
                            )
                            if not filtered_spends:
                                continue
                            sends = list(
                                filter(
                                    lambda sp: sp["category"] == "send",
                                    filtered_spends,
                                ),
                            )
                            receives = list(
                                filter(
                                    lambda sp: sp["category"] == "receive",
                                    filtered_spends,
                                ),
                            )
                            from_spend = None if len(sends) == 0 else sends[0]
                            from_receive = None if len(receives) == 0 else receives[0]
                            if not from_spend or not from_receive:
                                continue  # skip if don't have both send and receive
                            if (
                                abs(from_spend["amount"]) - from_receive["amount"]
                                > -sys.float_info.epsilon
                            ):
                                from_spend["amount"] += from_receive["amount"]
                                from_spend["fee"] += from_receive["fee"]
                                remove_these.append(from_receive)
                            elif (
                                abs(from_spend["amount"]) - from_receive["amount"]
                                <= -sys.float_info.epsilon
                            ):
                                from_receive["amount"] += from_spend["amount"]
                                from_receive["fee"] += from_spend["fee"]
                                remove_these.append(from_spend)
                            if len(spends) - len(remove_these) < MIN_SPENDS_TO_COMPARE:
                                break
                    # Remove all the consolidated spends
                    if len(remove_these) > 0:
                        for spend in remove_these:
                            if spend in spends:
                                spends.remove(spend)

                    # Filter out spends that have zero amount after consolidation
                    spends = list(
                        filter(
                            lambda sp: abs(sp["amount"]) > sys.float_info.epsilon,
                            spends,
                        ),
                    )

                    # Add timestamp to spends
                    blocktime = tx.get("blocktime")
                    if blocktime:
                        for spend in spends:
                            spend["time"] = blocktime

                    spent.extend(spends)

            except Exception:
                self.logger.exception(
                    "[GetAddressHistory] Exception while retrieving history",
                )

        return spent

    def set_request_handlers(self, ptuple):
        self.protocol_tuple = ptuple

        handlers = {
            "blockchain.block.header": self.block_header,
            "blockchain.block.headers": self.block_headers,
            "blockchain.estimatefee": self.estimatefee,
            "blockchain.headers.subscribe": self.headers_subscribe,
            "blockchain.scripthash.get_balance": self.scripthash_get_balance,
            "blockchain.scripthash.get_history": self.scripthash_get_history,
            "blockchain.scripthash.get_mempool": self.scripthash_get_mempool,
            "blockchain.scripthash.listunspent": self.scripthash_listunspent,
            "blockchain.scripthash.subscribe": self.scripthash_subscribe,
            "blockchain.transaction.broadcast": self.transaction_broadcast,
            "blockchain.transaction.get": self.transaction_get,
            "blockchain.transaction.get_merkle": self.transaction_merkle,
            "blockchain.transaction.id_from_pos": self.transaction_id_from_pos,
            "mempool.get_fee_histogram": self.compact_fee_histogram,
            "server.add_peer": self.add_peer,
            "server.banner": self.banner,
            "server.donation_address": self.donation_address,
            "server.features": self.server_features_async,
            "server.peers.subscribe": self.peers_subscribe,
            "server.ping": self.ping,
            "server.version": self.server_version,
            "blockchain.address.get_balance": self.address_get_balance,
            "blockchain.address.listunspent": self.address_listunspent,
            "blockchain.block.subscribe": self.block_subscribe,
            "getrawmempool": self.getrawmempool,
            "getblockcount": self.getblockcount,
            "getblock": self.getblock,
            "getblockhash": self.getblockhash,
            "gethistory": self.get_address_history,
        }

        if ptuple >= (1, 4, 2):
            handlers["blockchain.scripthash.unsubscribe"] = self.scripthash_unsubscribe

        if ptuple >= (1, 6):
            handlers["blockchain.transaction.broadcast_package"] = (
                self.package_broadcast
            )
            handlers["mempool.get_info"] = self.mempool_info
        else:
            handlers["blockchain.relayfee"] = self.relayfee

        self.request_handlers = handlers


class AuxPoWElectrumX(ElectrumX):
    async def block_header(self, height, cp_height=0):
        result = await super().block_header(height, cp_height)

        # Older protocol versions don't truncate AuxPoW
        if self.protocol_tuple < (1, 4, 1):
            return result

        # Not covered by a checkpoint; return full AuxPoW data
        if cp_height == 0:
            return result

        # Covered by a checkpoint; truncate AuxPoW data
        result["header"] = self.truncate_auxpow_single(result["header"])
        return result

    async def block_headers(self, start_height, count, cp_height=0):
        # Older protocol versions don't truncate AuxPoW
        if self.protocol_tuple < (1, 4, 1):
            return await super().block_headers(start_height, count, cp_height)

        # Not covered by a checkpoint; return full AuxPoW data
        if cp_height == 0:
            return await super().block_headers(start_height, count, cp_height)

        result = await super().block_headers_array(start_height, count, cp_height)

        # Covered by a checkpoint; truncate AuxPoW data
        result["headers"] = self.truncate_auxpow_headers(result["headers"])

        if self.protocol_tuple >= (1, 6):
            return result

        result["hex"] = "".join(result["headers"])
        del result["headers"]
        return result

    def truncate_auxpow_headers(self, headers):
        return [self.truncate_auxpow_single(header) for header in headers]

    def truncate_auxpow_single(self, header: str):
        return header[: 2 * self.coin.TRUNCATED_HEADER_SIZE]
