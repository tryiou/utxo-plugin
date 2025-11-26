import sys
from electrumx.lib.hash import hash_to_hex_str, hex_str_to_hash

def truncate(n, decimals=0):
    s = '{0:.{1}f}'.format(n, decimals)
    return float(s)


async def get_history(addresses, address_to_hashX, session_mgr, bump_cost, transaction_get, logger):
    """
    Autonomous address history function that processes transaction history for given addresses.
    
    Args:
        addresses: List of addresses or single address string
        address_to_hashX: Function to convert address to hashX
        session_mgr: Function that retrieves limited history for a hashX
        bump_cost: Function to bump cost
        transaction_get: Function to get transaction data
        logger: Logger object
    
    Returns:
        List of transaction history entries
    """
    addr_lookup = _normalize_addresses(addresses)
    spent = []
    spent_ids = set()
    processed_txs = set()
    
    for address in addr_lookup:
        address = str(address)
        logger.debug(f'Processing address: {address}')

        try:
            hash_x = _convert_address_to_hashx(address, address_to_hashX, logger)
            if hash_x is None:
                continue

            # history, cost = await session_mgr(hash_x)
            result = await session_mgr(hash_x)
            if isinstance(result, tuple):
                history, cost = result
            else:
                history = result
                cost = 1.0  # Default cost when not provided
                
            bump_cost(cost)
            logger.debug(f'History retrieved for address: {address}, cost: {cost}')

            await _process_transaction_history(
                history, processed_txs, addr_lookup, transaction_get, 
                spent, spent_ids, logger
            )

        except Exception as e:
            logger.warning(f'Exception while retrieving history for address {address}: {e}')
            import traceback
            traceback.print_exc()

    return spent


def _normalize_addresses(addresses):
    """Convert addresses input to a set."""
    if type(addresses) is str:
        return {addresses}
    else:
        return set(addresses)


def _convert_address_to_hashx(address, address_to_hashX, logger):
    """Try to convert address to hashX, return None on failure."""
    try:
        hash_x = address_to_hashX(address)
        logger.debug(f'Address converted to hashX: {hash_x}')
        return hash_x
    except Exception as e:
        logger.warning(f'Exception while converting address: {e}')
        return None


async def _process_transaction_history(history, processed_txs, addr_lookup, transaction_get, spent, spent_ids, logger):
    """Process all transactions in the history."""
    for tx_hash, height in history:
        if tx_hash in processed_txs:
            logger.debug(f'Skipping transaction, already processed: {tx_hash}')
            continue
        
        logger.debug(f'Processing transaction: {tx_hash}')
        tx = await transaction_get(hash_to_hex_str(tx_hash), verbose=True)
        if not tx:
            logger.debug(f'Transaction not found: {tx_hash}')
            continue
        processed_txs.add(tx_hash)

        spends = await _process_single_transaction(tx, addr_lookup, spent_ids, transaction_get, logger)
        spent.extend(spends)
        logger.debug(f'Spends recorded for transaction: {spends}')


async def _process_single_transaction(tx, addr_lookup, spent_ids, transaction_get, logger):
    """Process a single transaction and return its spends."""
    from_addresses, my_total_send_amount, total_send_amount = await _analyze_transaction_inputs(
        tx, addr_lookup, transaction_get, logger
    )
    
    logger.debug(f'Transaction analysis for {tx["txid"]}:')
    logger.debug(f'  from_addresses: {from_addresses}')
    logger.debug(f'  my_total_send_amount: {my_total_send_amount}')
    logger.debug(f'  total_send_amount: {total_send_amount}')
    
    my_total_send_amount_running = my_total_send_amount
    is_sending_coin = my_total_send_amount > 0
    fees = 0.0  # Initialize fees to 0, will calculate properly below
    
    tracking = {
        'biggest_sent_amount_not_my_address': 0,
        'biggest_sent_address_not_my_address': '',
        'biggest_sent_amount_my_address': 0,
        'biggest_sent_address_my_address': ''
    }
    
    spends = []
    
    # First pass: Process transactions sent to other addresses
    my_total_send_amount_running, total_output_amount = _process_outputs_to_other_addresses(
        tx, addr_lookup, my_total_send_amount_running, 0.0, spends,
        spent_ids, from_addresses, tracking, logger
    )
    
    # Second pass: Process transactions to our own addresses
    my_total_send_amount_running = _process_outputs_to_own_addresses(
        tx, addr_lookup, my_total_send_amount_running, spends,
        spent_ids, from_addresses, tracking, logger
    )
    
    # Calculate proper fees: total_inputs - total_outputs
    # Only calculate fees if we have inputs from our addresses
    fees = 0.0
    is_staking_reward = False
    
    if is_sending_coin and my_total_send_amount > 0:
        # Calculate total input value from our addresses
        total_input_value = my_total_send_amount
        # Calculate total output value sent to addresses other than ours
        total_output_value = total_output_amount
        
        # STAKING DETECTION: If output > input, this is a staking reward
        if total_output_value > total_input_value:
            is_staking_reward = True
            fees = 0.0  # No fees for staking rewards
            logger.debug(f'STAKING REWARD detected for {tx["txid"]}: input={total_input_value}, output={total_output_value}')
        else:
            fees = -(total_input_value - total_output_value)  # Make fees negative as expected by tests
            logger.debug(f'Fee calculation for {tx["txid"]}: input={total_input_value}, output={total_output_value}, fee={fees}')
    
    # Assign fees to the largest send transaction (only if not a staking reward)
    if not is_staking_reward:
        _assign_fees_to_largest_send(is_sending_coin, fees, spends, tracking, logger)
    
    # Consolidate spends to self
    spends = _consolidate_spends_to_self(spends)
    
    # Filter out zero-amount spends
    spends = list(filter(lambda sp: abs(sp['amount']) > sys.float_info.epsilon, spends))
    
    # Add timestamps
    _add_timestamps_to_spends(tx, spends)
    
    return spends


async def _analyze_transaction_inputs(tx, addr_lookup, transaction_get, logger):
    """Analyze transaction inputs to determine from_addresses and amounts."""
    from_addresses = set()
    total_send_amount = 0
    my_total_send_amount = 0
    
    for item in tx['vin']:
        prev_tx = await transaction_get(item['txid'], verbose=True)
        if not prev_tx:
            logger.debug(f'Previous transaction not found: {item["txid"]}')
            continue

        prev_out_amount = prev_tx['vout'][item['vout']]['value']
        script_pub_key = prev_tx['vout'][item['vout']]['scriptPubKey']
        addrs = _extract_addresses_from_script(script_pub_key)

        if len(addrs) > 0:
            is_my_address = _is_any_address_mine(addrs, addr_lookup)
            if is_my_address:
                my_total_send_amount += prev_out_amount
            else:
                total_send_amount += prev_out_amount
            from_addresses.update(addrs)
    
    return from_addresses, my_total_send_amount, total_send_amount


def _extract_addresses_from_script(script_pub_key):
    """Extract addresses from scriptPubKey."""
    addrs = []
    if 'addresses' in script_pub_key:
        addrs = script_pub_key['addresses']
    elif 'address' in script_pub_key:
        addrs = [script_pub_key['address']]
    return addrs


def _is_any_address_mine(addrs, addr_lookup):
    """Check if any address in the list is in our address lookup."""
    for addr in addrs:
        if addr in addr_lookup:
            return True
    return False


def _process_outputs_to_other_addresses(tx, addr_lookup, my_total_send_amount_running,
                                        _, spends, spent_ids, from_addresses, tracking, logger):
    """First pass: Process outputs sent to addresses not in our lookup."""
    total_output_amount = 0.0
    
    for item in tx['vout']:
        amount = item['value']
        total_output_amount += amount
        
        vout_address = _get_address_from_output(item)
        if not vout_address:
            continue
        if vout_address in addr_lookup:
            continue

        if my_total_send_amount_running > sys.float_info.epsilon:
            if tracking['biggest_sent_amount_not_my_address'] < amount:
                tracking['biggest_sent_amount_not_my_address'] = amount
                tracking['biggest_sent_address_not_my_address'] = vout_address
            
            adjusted_amount = amount if my_total_send_amount_running > amount else my_total_send_amount_running
            my_total_send_amount_running -= adjusted_amount
            
            spend, txid_n = _create_valid_spend(
                spent_ids, vout_address, -float(adjusted_amount), 'send',
                item, tx, list(from_addresses)
            )
            if spend:
                spent_ids.add(txid_n)
                spends.append(spend)
                logger.debug(f'Spent coin recorded: {spend}')
    
    return my_total_send_amount_running, total_output_amount


def _process_outputs_to_own_addresses(tx, addr_lookup, my_total_send_amount_running, 
                                      spends, spent_ids, from_addresses, tracking, logger):
    """Second pass: Process outputs sent to our own addresses."""
    for item in tx['vout']:
        vout_address = _get_address_from_output(item)
        if not vout_address:
            continue
        if vout_address not in addr_lookup:
            continue

        amount = item['value']
        do_not_mark_send = vout_address not in from_addresses

        # Record received coin
        spend, txid_n = _create_valid_spend(
            spent_ids, vout_address, float(amount), 'receive', 
            item, tx, list(from_addresses)
        )
        if spend:
            spent_ids.add(txid_n)
            spends.append(spend)
            logger.debug(f'Received coin recorded: {spend}')

        # Record sent coin if applicable
        if my_total_send_amount_running > sys.float_info.epsilon:
            adjusted_amount = amount if my_total_send_amount_running > amount else my_total_send_amount_running
            my_total_send_amount_running -= adjusted_amount
            
            if not do_not_mark_send:
                spend, txid_n = _create_valid_spend(
                    spent_ids, vout_address, -float(adjusted_amount), 'send', 
                    item, tx, list(from_addresses)
                )
                if spend:
                    spent_ids.add(txid_n)
                    spends.append(spend)
                    logger.debug(f'Spent coin recorded: {spend}')

                    if tracking['biggest_sent_amount_my_address'] < amount:
                        tracking['biggest_sent_amount_my_address'] = amount
                        tracking['biggest_sent_address_my_address'] = vout_address
    
    return my_total_send_amount_running


def _get_address_from_output(item):
    """Extract address from a transaction output item."""
    if 'type' not in item['scriptPubKey'] or item['scriptPubKey']['type'] == 'nonstandard':
        return None

    if 'address' in item['scriptPubKey']:
        if isinstance(item['scriptPubKey']['address'], str):
            return item['scriptPubKey']['address']

    elif 'addresses' in item['scriptPubKey']:
        if isinstance(item['scriptPubKey']['addresses'], str):
            return item['scriptPubKey']['addresses']
        elif isinstance(item['scriptPubKey']['addresses'], list) and len(item['scriptPubKey']['addresses']) > 0:
            return item['scriptPubKey']['addresses'][0]

    return None


def _create_valid_spend(spent_ids, address, amount, category, item, tx, from_addresses):
    """Create a spend record if not already recorded."""
    txid_n = (tx['txid'], item['n'], category)
    if txid_n not in spent_ids:
        return {
            'address': address,
            'amount': amount,
            'fee': 0.0,
            'vout': item['n'],
            'category': category,
            'confirmations': tx['confirmations'],
            'blockhash': tx['blockhash'],
            'blocktime': tx['blocktime'],
            'time': tx['blocktime'],
            'txid': tx['txid'],
            'from_addresses': from_addresses
        }, txid_n
    else:
        return None, None


def _assign_fees_to_largest_send(is_sending_coin, fees, spends, tracking, logger):
    """Assign fees to the transaction with the largest sent amount."""
    if is_sending_coin and fees != 0:
        # Find the address with the biggest sent amount to external addresses
        biggest_sent_address = None
        biggest_amount = 0
        
        # Priority 1: Biggest sent amount to external addresses
        if tracking['biggest_sent_amount_not_my_address'] > biggest_amount:
            biggest_amount = tracking['biggest_sent_amount_not_my_address']
            biggest_sent_address = tracking['biggest_sent_address_not_my_address']
        
        # Priority 2: If no external sends, use biggest sent amount to our own addresses
        if biggest_sent_address is None and tracking['biggest_sent_amount_my_address'] > biggest_amount:
            biggest_amount = tracking['biggest_sent_amount_my_address']
            biggest_sent_address = tracking['biggest_sent_address_my_address']
        
        logger.debug(f'Fee assignment: is_sending_coin={is_sending_coin}, fees={fees}, biggest_sent_address={biggest_sent_address}')
        
        if biggest_sent_address:
            for spend in spends:
                if spend['address'] == biggest_sent_address and spend['category'] == 'send':
                    spend['fee'] = truncate(fees, 10)
                    logger.debug(f'Assigned fee: {spend}')
                    break


def _consolidate_spends_to_self(spends):
    """Consolidate send and receive transactions to the same address."""
    remove_these = []
    
    if len(spends) >= 2:
        for spend in spends:
            filtered_spends = list(filter(lambda sp: sp['address'] == spend['address'], spends))
            if not filtered_spends:
                continue
            
            sends = list(filter(lambda sp: sp['category'] == 'send', filtered_spends))
            receives = list(filter(lambda sp: sp['category'] == 'receive', filtered_spends))
            from_spend = None if len(sends) == 0 else sends[0]
            from_receive = None if len(receives) == 0 else receives[0]
            
            if not from_spend or not from_receive:
                continue
            
            if abs(from_spend['amount']) - from_receive['amount'] > -sys.float_info.epsilon:
                from_spend['amount'] += from_receive['amount']
                from_spend['fee'] += from_receive['fee']
                remove_these.append(from_receive)
            elif abs(from_spend['amount']) - from_receive['amount'] <= -sys.float_info.epsilon:
                from_receive['amount'] += from_spend['amount']
                from_receive['fee'] += from_spend['fee']
                remove_these.append(from_spend)
            
            if len(spends) - len(remove_these) < 2:
                break
    
    # Remove consolidated spends
    if len(remove_these) > 0:
        for spend in remove_these:
            if spend in spends:
                spends.remove(spend)
    
    return spends


def _add_timestamps_to_spends(tx, spends):
    """Add timestamp to all spend records."""
    blocktime = tx.get('blocktime')
    if blocktime:
        for spend in spends:
            spend['time'] = blocktime