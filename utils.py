import GPUtil
from dataclasses import dataclass, field
from typing import Any


_limit = 1
_max_load = 0.1
_max_memory = 0.1


def init(limit: int, max_load: float, max_memory: float) -> None:
    global _limit, _max_load, _max_memory
    _limit = limit
    _max_load = max_load
    _max_memory = max_memory


def register_to(name: str, mapping: dict):
    def wrapper(fn):
        mapping[name] = fn
        return fn
    return wrapper


@dataclass(order=True)
class PrioritizedItem:
    priority: int
    item: Any = field(compare=False)


def get_free_gpus(host_ids: list, exclude_ids: list) -> list:
    """
    Get a list of GPU ids that are available for running.
    Args:
        host_ids (list): a list of GPU ids that are possibly available.
        exclude_ids (list): a list of GPU ids that are not available.

    Returns:
        list: a list of GPU ids that are available.
    """
    global _limit, _max_load, _max_memory
    if len(host_ids) > 0:
        other_exclude_ids = list(set(range(_limit)) - set(host_ids))
    else:
        other_exclude_ids = []

    total_exclude_ids = set(exclude_ids) | set(other_exclude_ids)

    deviceIDs = GPUtil.getAvailable(order='first', limit=_limit,
                                    maxLoad=_max_load, maxMemory=_max_memory, excludeID=total_exclude_ids)
    return deviceIDs


def send(socket, obj, flags=0, protocol=-1):
    """stringify an object, and then send it"""
    s = str(obj)
    return socket.send_string(s)


def recv(socket, flags=0, protocol=-1):
    """inverse of send"""
    s = socket.recv_string()
    return eval(s)


def format_msg(msg: dict):
    return str(msg)
