import sys
import time
import pylru
from electrumx.lib.hash import sha256, hash_to_hex_str, hex_str_to_hash
from electrumx.server.session import ElectrumX as BaseElectrumX, non_negative_integer

from server import get_address_history as GetAddressHistory

# Error constants
BAD_REQUEST = 1
DAEMON_ERROR = 2

def truncate(n, decimals=0):
    """Truncate a number to specified decimal places."""
    s = '{0:.{1}f}'.format(n, decimals)
    return float(s)

class CustomElectrumX(BaseElectrumX):
    """Extended ElectrumX with custom RPC methods and compatibility."""
    
    # Support latest protocol versions
    PROTOCOL_MAX = (1, 6, 0)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Initialize your custom caches exactly as before
        self.session_mgr._history_address_cache = pylru.lrucache(1000)
        self.cached_gettxoutsetinfo = None
        self.cached_rawblocks = None
        self.subscribe_blocks = False
    
    def set_request_handlers(self, ptuple):
        """Set request handlers combining base ElectrumX and custom methods."""
        # First, get the base handlers from ElectrumX
        super().set_request_handlers(ptuple)
        
        # Override and add custom RPC methods
        custom_handlers = {
            # Your blockchain data methods
            'getrawmempool': self.getrawmempool,
            'getblockcount': self.getblockcount,
            'getblock': self.getblock,
            'getblockhash': self.getblockhash,
            'getblockchaininfo': self.getblockchaininfo,
            'gettxoutsetinfo': self.gettxoutsetinfo,
            'getmempoolinfo': self.getmempoolinfo,
            
            # Your block streaming methods
            'getrawblocks': self.getrawblocks,
            'blockchain.block.subscribe': self.block_subscribe,
            
            # Your history methods
            'gethistory': self.get_address_history,
            'gethashx': self.get_hashx,
            'gethistoryhashx': self.get_history_hashx,
            
            'blockchain.address.get_balance': getattr(self, 'address_get_balance', self.address_get_balance),
            'blockchain.address.get_history': getattr(self, 'address_get_history', self.address_get_history),
            'blockchain.address.get_mempool': getattr(self, 'address_get_mempool', self.address_get_mempool),
            'blockchain.address.listunspent': getattr(self, 'address_listunspent', self.address_listunspent),
            'blockchain.address.subscribe': getattr(self, 'address_subscribe', self.address_subscribe),
            'blockchain.block.get_chunk': getattr(self, 'block_get_chunk', self.block_get_chunk),
            'blockchain.block.get_header': getattr(self, 'block_get_header', self.block_get_header),
            'blockchain.relayfee': getattr(self, 'relayfee', self.relayfee),
        }
        
        # Update with custom handlers (this will override base methods if they exist)
        self.request_handlers.update(custom_handlers)
    
    # === Custom RPC Methods ===
    
    async def getrawmempool(self, verbose=False):
        if any(verbose == x for x in [1, '1', True, 'true', 'True']):
            verbose = True

        args = (verbose,)

        return await self.daemon_request('_send_single', 'getrawmempool', args)

    async def getblockcount(self):
        cached_height = self.session_mgr.daemon.cached_height()

        if cached_height is None:
            return await self.session_mgr.daemon.height()

        return cached_height

    async def getblock(self, hex_hash, verbose=False):
        if any(verbose == x for x in [1, '1', True, 'true', 'True']):
            verbose = True

        args = (hex_hash, verbose)

        return await self.daemon_request('_send_single', 'getblock', args)

    async def getblockhash(self, height):
        block_hash, tx_hashes = await self._block_hash_and_tx_hashes(height)

        return block_hash

    async def getblockchaininfo(self):
        return await self.daemon_request('_send_single', 'getblockchaininfo')

    async def gettxoutsetinfo(self):
        if self.cached_gettxoutsetinfo is None or (time.time() - self.cached_gettxoutsetinfo_update_time) > 600:
            self.cached_gettxoutsetinfo = await self.daemon_request('_send_single', 'gettxoutsetinfo')
            self.cached_gettxoutsetinfo_update_time = time.time()

        return self.cached_gettxoutsetinfo

    async def getmempoolinfo(self):
        return await self.daemon_request('_send_single', 'getmempoolinfo')

    async def get_db_raw_blocks(self, last_height, count):
        return await self.db.raw_blocks(last_height, count)

    async def cache_raw_blocks(self, count=110):
        if self.cached_rawblocks is None or (time.time() - self.cached_rawblocks_update_time) > 30:
            self.cached_rawblocks_update_time = time.time()
            height = await self.getblockcount()

            self.logger.info('Getting raw blocks for {}-{}'.format((height - count), height))

            self.cached_rawblocks = await self.get_db_raw_blocks(height, count)

        return self.cached_rawblocks

    async def getrawblocks(self, from_height, to_height):
        try:
            cached_blocks = await self.cache_raw_blocks()
            if (to_height - from_height) > len(cached_blocks):
                return []

            return sorted([(height, block) for height, block in cached_blocks if from_height <= height <= to_height],
                          key=lambda x: x[0], reverse=True)
        except Exception:
            return []

    async def block_subscribe(self):
        self.subscribe_blocks = True
        return await self.subscribe_blocks_result()

    async def subscribe_blocks_result(self):
        return self.session_mgr.bsub_results

    async def get_address_history(self, addresses):
        self.logger.info('get_address_history: {}'.format(addresses))
        
        def address_to_hashX(address):
            return self.coin.address_to_hashX(address)
        
        async def limited_history_wrapper(hash_x):
            return await self.db.limited_history(hash_x, limit=100)
        
        def bump_cost_wrapper(cost):
            self.bump_cost(cost)
        
        async def transaction_get_wrapper(hash_x, verbose=False):
            return await self.transaction_get(hash_x, verbose=verbose)
        
        return await GetAddressHistory.get_history(
            addresses,
            address_to_hashX,
            limited_history_wrapper,
            bump_cost_wrapper,
            transaction_get_wrapper,
            self.logger
        )
    
    async def get_history(self, addresses):
        self.logger.info('get_history: {}'.format(addresses))
        return await self.get_address_history(addresses)

    async def get_history_hashx(self, hashx_list):
        self.bump_cost(2.0)  # Add appropriate cost for this expensive operation
        
        self.logger.info('get_history_hashx: {}'.format(hashx_list))
        addr_lookup = hashx_list
        spent = []
        spent_ids = set()
        processed_txs = set()  # track transactions that have already been processed
        for hash_x in addr_lookup:
            self.logger.info('get_history_hashx debug: {}'.format(hash_x))
            hash_x = hex_str_to_hash(hash_x)
            self.logger.info(hash_x)

            history = await self.db.limited_history(hash_x, limit=100)

            for tx_hash, height in history:
                if tx_hash in processed_txs:
                    continue  # skip, already processed
                tx = await self.transaction_get(hash_to_hex_str(tx_hash), verbose=True)
                if not tx:
                    continue
                processed_txs.add(tx_hash)

                spends = []
                from_addresses = set()
                total_send_amount = 0
                my_total_send_amount = 0
                for item in tx['vin']:
                    prev_tx = await self.transaction_get(item['txid'], verbose=True)
                    if not prev_tx:
                        continue

                    prev_out_amount = prev_tx['vout'][item['vout']]['value']
                    addrs = prev_tx['vout'][item['vout']]['scriptPubKey']['addresses']
                    # record total sent coin if sent from one of our addresses
                    if len(addrs) > 0:
                        for addr in addrs:
                            if addr in addr_lookup:
                                my_total_send_amount += prev_out_amount
                                break

                    total_send_amount += prev_out_amount
                    from_addresses.update(addrs)

                my_total_send_amount_running = my_total_send_amount  # track how much sent coin is left to report
                is_sending_coin = my_total_send_amount > 0
                
                # DEBUG: Log fee calculation details
                self.logger.debug(f'[GetAddressHistory] Fee calculation: total_send_amount={total_send_amount}, my_total_send_amount={my_total_send_amount}, is_sending_coin={is_sending_coin}')

                biggest_sent_amount_not_my_address = 0
                biggest_sent_address_not_my_address = ''
                biggest_sent_amount_my_address = 0
                biggest_sent_address_my_address = ''

                fees = -total_send_amount  # fees should be negative (cost to the sender)
                # DEBUG: Log calculated fees
                self.logger.debug(f'[GetAddressHistory] Calculated fees: {fees}')

                def valid_spend(p_spent_ids, p_address, p_amount, p_category, p_item, p_tx, p_from_addresses):
                    p_txid_n = (p_tx['txid'], p_item['n'], p_category)
                    if p_txid_n not in p_spent_ids:
                        return {
                                   'address': p_address,
                                   'amount': p_amount,
                                   'fee': 0.0,
                                   'vout': p_item['n'],
                                   'category': p_category,
                                   'confirmations': p_tx['confirmations'],
                                   'blockhash': p_tx['blockhash'],
                                   'blocktime': p_tx['blocktime'],
                                   'time': p_tx['blocktime'],
                                   'txid': p_tx['txid'],
                                   'from_addresses': p_from_addresses
                               }, p_txid_n
                    else:
                        return None, None

                def get_address(p_item):
                    if 'addresses' not in p_item['scriptPubKey'] or 'type' not in p_item['scriptPubKey'] \
                            or p_item['scriptPubKey']['type'] == 'nonstandard':
                        return None  # skip incompatible vout
                    if isinstance(p_item['scriptPubKey']['addresses'], str):
                        return p_item['scriptPubKey']['addresses']
                    elif isinstance(p_item['scriptPubKey']['addresses'], list):
                        return p_item['scriptPubKey']['addresses'][0]
                    else:
                        return None

                # First pass: Only process transactions sent to another address, record fees
                for item in tx['vout']:
                    # Add in fees (fees = total_in - total_out)
                    amount = item['value']
                    fees += amount
                    vout_address = get_address(item)
                    if not vout_address:
                        continue  # incompatible address, skip

                    if vout_address in addr_lookup:
                        continue  # not our address, skip

                    # Amount is negative for send and positive for receive
                    # Record sent coin to address if we have outstanding send amount.
                    # Note that my total sent amount is subtracted by any amounts
                    # previously marked sent.
                    # Compare with epsilon instead of 0 to avoid precision inaccuracies.
                    if my_total_send_amount_running > sys.float_info.epsilon:
                        if biggest_sent_amount_not_my_address < amount:
                            biggest_sent_amount_not_my_address = amount
                            biggest_sent_address_not_my_address = vout_address
                        # amount reported here cannot be larger than my total send amount
                        adjusted_amount = amount if my_total_send_amount_running > amount else my_total_send_amount_running
                        my_total_send_amount_running -= adjusted_amount  # track what we've already recorded as sent
                        spend, txid_n = valid_spend(spent_ids, vout_address, -float(adjusted_amount), 'send', item,
                                                    tx,
                                                    list(from_addresses))
                        if spend:
                            spent_ids.add(txid_n)
                            spends.append(spend)

                # Second pass: Only process transactions for all our own addresses
                for item in tx['vout']:
                    vout_address = get_address(item)
                    if not vout_address:
                        continue  # incompatible address, skip
                    if vout_address not in addr_lookup:
                        continue  # skip, already processed in block above

                    amount = item['value']

                    do_not_mark_send = False
                    if vout_address not in from_addresses:
                        do_not_mark_send = True

                    # Record received coin if this vout address is mine
                    spend, txid_n = valid_spend(spent_ids, vout_address, float(amount), 'receive', item, tx,
                                                list(from_addresses))
                    if spend:
                        spent_ids.add(txid_n)
                        spends.append(spend)

                    # Amount is negative for send and positive for receive
                    # Record sent coin to address if we have outstanding send amount.
                    # Note that my total sent amount is subtracted by any amounts
                    # previously marked sent.
                    # Compare with epsilon instead of 0 to avoid precision inaccuracies.
                    if my_total_send_amount_running > sys.float_info.epsilon:
                        # amount reported here cannot be larger than my total send amount
                        adjusted_amount = amount if my_total_send_amount_running > amount else my_total_send_amount_running
                        my_total_send_amount_running -= adjusted_amount  # track what we've already recorded as sent
                        if not do_not_mark_send:
                            spend, txid_n = valid_spend(spent_ids, vout_address, -float(adjusted_amount), 'send',
                                                        item, tx,
                                                        list(from_addresses))
                            if spend:
                                spent_ids.add(txid_n)
                                spends.append(spend)

                                if biggest_sent_amount_my_address < amount:
                                    biggest_sent_amount_my_address = amount
                                    biggest_sent_address_my_address = vout_address

                # Assign fees on tx with largest sent amount. Assign fees to transactions
                # sent to an address that is not our own. Otherwise assign fee to largest
                # sent transaction on our own address if that applies.
                if is_sending_coin and fees < 0:
                    for spend in spends:
                        biggest_sent_address = biggest_sent_address_not_my_address \
                            if biggest_sent_amount_not_my_address > 0 else biggest_sent_address_my_address
                        if spend['address'] == biggest_sent_address and spend['category'] == 'send':
                            spend['fee'] = truncate(fees, 10)
                            break

                # Consolidate spends to self
                remove_these = []
                if len(spends) >= 2:  # can only compare at least 2 spends
                    for spend in spends:
                        filtered_spends = list(filter(lambda sp: sp['address'] == spend['address'], spends))
                        if not filtered_spends:
                            continue
                        sends = list(filter(lambda sp: sp['category'] == 'send', filtered_spends))
                        receives = list(filter(lambda sp: sp['category'] == 'receive', filtered_spends))
                        from_spend = None if len(sends) == 0 else sends[0]
                        from_receive = None if len(receives) == 0 else receives[0]
                        if not from_spend or not from_receive:
                            continue  # skip if don't have both send and receive
                        if abs(from_spend['amount']) - from_receive['amount'] > -sys.float_info.epsilon:
                            from_spend['amount'] += from_receive['amount']
                            from_spend['fee'] += from_receive['fee']
                            remove_these.append(from_receive)
                        elif abs(from_spend['amount']) - from_receive['amount'] <= -sys.float_info.epsilon:
                            from_receive['amount'] += from_spend['amount']
                            from_receive['fee'] += from_spend['fee']
                            remove_these.append(from_spend)
                        if len(spends) - len(remove_these) < 2:  # done processing if nothing left to compare
                            break
                # Remove all the consolidated spends
                if len(remove_these) > 0:
                    spends[:] = [spend for spend in spends if spend not in remove_these]

                spent += spends

        self.logger.info(f'SPENT: {spent}')
        return spent

    async def get_hashx(self, address):
        self.bump_cost(0.5)  # Add cost for address conversion
        self.logger.info('get_hashx: {}'.format(address))
        hash_x = hash_to_hex_str(self.coin.address_to_hashX(address))
        self.logger.info('get_hashx result: {}'.format(hash_x))
        self.logger.info('get_hashx bytes result: {}'.format(self.coin.address_to_hashX(address)))

        return [hash_x]

    # Helper method from original implementation
    async def _block_hash_and_tx_hashes(self, height):
        '''Returns a pair (block_hash, tx_hashes) for the main chain block at
        the given height.

        block_hash is a hexadecimal string, and tx_hashes is an
        ordered list of hexadecimal strings.
        '''
        height = non_negative_integer(height)
        hex_hashes = await self.daemon_request('block_hex_hashes', height, 1)
        block_hash = hex_hashes[0]
        block = await self.daemon_request('deserialised_block', block_hash)
        return block_hash, block['tx']
    
    # Missing methods that need to be implemented for compatibility (using original method names)
    async def address_get_balance(self, address):
        '''Return the confirmed and unconfirmed balance of an address.'''
        hashX = self.coin.address_to_hashX(address)
        return await self.get_balance(hashX)
    
    async def address_get_history(self, address):
        '''Return the confirmed and unconfirmed history of an address.'''
        hashX = self.coin.address_to_hashX(address)
        return await self.confirmed_and_unconfirmed_history(hashX)
    
    async def address_get_mempool(self, address):
        '''Return the mempool transactions touching an address.'''
        hashX = self.coin.address_to_hashX(address)
        return await self.unconfirmed_history(hashX)
    
    async def address_listunspent(self, address):
        '''Return the list of UTXOs of an address.'''
        hashX = self.coin.address_to_hashX(address)

        utxos = await self.db.all_utxos(hashX)
        utxos = sorted(utxos)
        utxos.extend(await self.mempool.unordered_UTXOs(hashX))
        self.bump_cost(1.0 + len(utxos) / 50)
        spends = await self.mempool.potential_spends(hashX)

        return [{'address': address,
                 'tx_hash': hash_to_hex_str(utxo.tx_hash),
                 'tx_pos': utxo.tx_pos,
                 'height': utxo.height, 'value': utxo.value}
                for utxo in utxos
                if (utxo.tx_hash, utxo.tx_pos) not in spends]
    
    async def address_subscribe(self, address):
        '''Subscribe to an address.

        address: the address to subscribe to'''
        hashX = self.coin.address_to_hashX(address)
        return await self.hashX_subscribe(hashX, address)
    
    async def block_get_chunk(self, index):
        '''Return a chunk of block headers as a hexadecimal string.

        index: the chunk index'''
        index = non_negative_integer(index)
        size = self.coin.CHUNK_SIZE
        start_height = index * size
        headers, _ = await self.db.read_headers(start_height, size)
        return headers.hex()
    
    async def block_get_header(self, height):
        '''The deserialized header at a given height.

        height: the header's height'''
        height = non_negative_integer(height)
        return await self.session_mgr.electrum_header(height)
    
    async def relayfee(self):
        '''The minimum fee a low-priority tx must pay in order to be accepted
        to the daemon's memory pool.'''
        return await self.daemon_request('relayfee')
    
    async def get_balance(self, hashX):
        utxos = await self.db.all_utxos(hashX)
        confirmed = sum(utxo.value for utxo in utxos)
        unconfirmed = await self.mempool.balance_delta(hashX)
        return {'confirmed': confirmed, 'unconfirmed': unconfirmed}
    
    async def confirmed_and_unconfirmed_history(self, hashX):
        # Note history is ordered but unconfirmed is unordered in e-s
        history, cost = await self.session_mgr.limited_history(hashX)
        self.bump_cost(cost)
        conf = [{'tx_hash': hash_to_hex_str(tx_hash), 'height': height}
                for tx_hash, height in history]
        return conf + await self.unconfirmed_history(hashX)
    
    async def unconfirmed_history(self, hashX):
        # Note unconfirmed history is unordered in electrum-server
        # height is -1 if it has unconfirmed inputs, otherwise 0
        result = [{'tx_hash': hash_to_hex_str(tx.hash),
                   'height': -tx.has_unconfirmed_inputs,
                   'fee': tx.fee}
                  for tx in await self.mempool.transaction_summaries(hashX)]
        self.bump_cost(0.25 + len(result) / 50)
        return result
    
    async def hashX_subscribe(self, hashX, alias):
        # Store the subscription only after address_status succeeds
        result = await self.address_status(hashX)
        self.hashX_subs[hashX] = alias
        return result
    
    async def address_status(self, hashX):
        '''Returns an address status.
        Status is a hex string, but must be None if there is no history.
        '''
        # Note history is ordered and mempool unordered in electrum-server
        # For mempool, height is -1 if it has unconfirmed inputs, otherwise 0
        db_history, cost = await self.session_mgr.limited_history(hashX)
        mempool = await self.mempool.transaction_summaries(hashX)

        status = ''.join(f'{hash_to_hex_str(tx_hash)}:'
                         f'{height:d}:'
                         for tx_hash, height in db_history)
        status += ''.join(f'{hash_to_hex_str(tx.hash)}:'
                          f'{-tx.has_unconfirmed_inputs:d}:'
                          for tx in mempool)

        # Add status hashing cost
        self.bump_cost(cost + 0.1 + len(status) * 0.00002)

        if status:
            status = sha256(status.encode()).hex()
        else:
            status = None

        if mempool:
            self.mempool_statuses[hashX] = status
        else:
            self.mempool_statuses.pop(hashX, None)

        return status