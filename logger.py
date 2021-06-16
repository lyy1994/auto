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


def info(msg):
    print(_format %
          {
              "asctime": str(datetime.today().strftime(_datefmt)),
              "levelname": info.__name__.upper(),
              "message": msg,
          }, file=_handler)
    if isinstance(_handler, TextIOWrapper):
        _handler.flush()
