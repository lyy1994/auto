from io import TextIOWrapper
from datetime import datetime


_format = "%(message)s"
_datefmt = "%H:%M:%S"
_handler = None


def config(format=None, datefmt=None, handler=None):
    global _format, _datefmt, _handler
    if format is not None:
        _format = format
    if datefmt is not None:
        _datefmt = datefmt
    if handler is not None and isinstance(handler, str):
        _handler = open(handler, "a", encoding="utf-8")


def _print(msg, level):
    print(_format %
          {
              "asctime": str(datetime.today().strftime(_datefmt)),
              "levelname": level.upper(),
              "message": msg,
          }, file=_handler)
    if isinstance(_handler, TextIOWrapper):
        _handler.flush()


def info(msg):
    _print(msg, info.__name__)


def warning(msg):
    _print(msg, warning.__name__)
