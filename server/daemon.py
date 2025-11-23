from functools import wraps
from aiorpcx import RPCError
from electrumx.server.daemon import Daemon, DaemonError


class SyscoinDaemon(Daemon):

    async def masternode_broadcast(self, params):
        '''Broadcast a transaction to the network.'''
        return await self._send_single('masternodebroadcast', params)

    async def masternode_list(self, params):
        '''Return the masternode status.'''
        return await self._send_single('masternodelist', params)

    async def assetallocationsend(self, asset_guid, from_address, to_address, amount):
        return await self._send_single('assetallocationsend', [int(asset_guid), from_address, to_address, amount])

    async def listassetallocations(self, params):
        return await self._send_single('listassetallocations', [0, 0, {'addresses': params}])

    async def listassetindex(self, page, params):
        return await self._send_single('listassetindex', [page, params])


def handles_errors(decorated_function):
    @wraps(decorated_function)
    async def wrapper(*args, **kwargs):
        try:
            return await decorated_function(*args, **kwargs)
        except DaemonError as daemon_error:
            error_dict = daemon_error.args[0]
            message, code = error_dict['message'], error_dict['code']
            raise RPCError(message, code=code)
    return wrapper


