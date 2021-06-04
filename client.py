import zmq
import argparse
import logging
import os
import sys
import json

import utils


logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s > %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=os.environ.get("LOGLEVEL", "INFO").upper(),
    stream=sys.stdout,
)
logger = logging.getLogger("client")


_OPTION_IMPL = {}


@utils.register_to("run", _OPTION_IMPL)
def run(args: argparse.Namespace):
    return {
        "option": args.option,
        "num_gpus": args.num_gpus,
        "cmd": args.cmd,
        "priority": args.priority,
    }


@utils.register_to("status", _OPTION_IMPL)
def status(args: argparse.Namespace):
    return {
        "option": args.option,
    }


@utils.register_to("cancel", _OPTION_IMPL)
def cancel(args: argparse.Namespace):
    return {
        "option": args.option,
        "ids": args.id,
    }


@utils.register_to("history", _OPTION_IMPL)
def history(args: argparse.Namespace):
    return {
        "option": args.option,
        "num_records": args.num_records,
        "fail": args.fail,
    }


@utils.register_to("kill", _OPTION_IMPL)
def kill(args: argparse.Namespace):
    return {
        "option": args.option,
        "ids": args.id,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Interface to communicate with the server.",
    )
    # Required parameters
    parser.add_argument(
        "--ip", default="*", type=str, help="The ip to communicate with the server."
    )
    parser.add_argument(
        "--port", default=None, type=int, help="The port to communicate with the server."
    )
    # Sub-parsers
    subparsers = parser.add_subparsers(
        help='Possible options.', dest='option'
    )
    # for run option
    parser_run = subparsers.add_parser('run', help='Run a task.')
    parser_run.add_argument(
        "--num-gpus", "-n", default=1, type=int, help="The number of GPUs you want to allocate."
    )
    parser_run.add_argument(
        "--cmd", "-c", required=True, type=str, help="The task you want to run."
    )
    parser_run.add_argument(
        "--priority", "-p", default=10, type=int,
        help="The priority of the task you want to run. Smaller is higher."
    )
    # for status option
    parser_status = subparsers.add_parser('status', help='Check task status.')
    # for cancel option
    parser_cancel = subparsers.add_parser('cancel', help='Cancel a pending task.')
    parser_cancel.add_argument(
        "--id", "-i", required=True, type=int, nargs='+', help="The task id you want to cancel."
    )
    # for history option
    parser_history = subparsers.add_parser('history', help='Show finished tasks.')
    parser_history.add_argument(
        "--num-records", "-n", default=-1, type=int, help="The number of finished tasks you want to show."
    )
    parser_history.add_argument(
        "--fail", "-f", action="store_true", help="Show the failed tasks."
    )
    # for kill option
    parser_history = subparsers.add_parser('kill', help='Kill running tasks.')
    parser_history.add_argument(
        "--id", "-i", required=True, type=int, nargs='+', help="The task id you want to kill."
    )

    args = parser.parse_args()
    logger.info(args)

    # set up connection
    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    if args.port is None:
        # if not specify, then load from the server setting
        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.json"), 'r') as f:
            args.port = json.load(f)["port"]
    socket.bind("tcp://{}:{}".format(args.ip, args.port))

    utils.send(socket, _OPTION_IMPL[args.option](args))
    logger.info(socket.recv_string())

