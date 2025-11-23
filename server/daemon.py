from functools import wraps
from aiorpcx import RPCError
from electrumx.server.daemon import Daemon, DaemonError




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


