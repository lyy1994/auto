import argparse
import logging
import os
import sys
import queue
import threading
import json

import zmq

import utils
from consumer import Consumer


logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s > %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=os.environ.get("LOGLEVEL", "INFO").upper(),
    stream=sys.stdout,
)
logger = logging.getLogger("server")


_OPTION_IMPL = {}
counter = 0


@utils.register_to("run", _OPTION_IMPL)
def run(message: dict):
    global counter
    mq_lock.acquire()
    if mq.qsize() >= args.max_run:
        msg = "Reaching the maximum number ({}) of pending commands to run!".format(args.max_run)
        logger.warning(msg)
        socket.send_string(msg)
        mq_lock.release()
        return
    message["id"] = counter
    mq.put(message)
    mq_lock.release()
    socket.send_string("Command id: {}".format(counter))
    counter = (counter + 1) % args.max_run


@utils.register_to("status", _OPTION_IMPL)
def status(message: dict):
    # running CMDs
    running = [utils.format_msg(m) for m in runner.running_status()]
    # pending CMDs in runner
    pending = [utils.format_msg(m) for m in runner.pending_status()]
    # pending CMDs in message queue
    mq_lock.acquire()
    for _ in range(mq.qsize()):
        m: dict = mq.get()
        mq.put(m)
        pending.append(utils.format_msg(m))
    mq_lock.release()
    socket.send_string("Runner Status:\nRunning CMDs:\n" + "\n".join(running) + "\nPending CMDs:\n" + "\n".join(pending))


@utils.register_to("cancel", _OPTION_IMPL)
def cancel(message: dict):
    idx = message["id"]
    # cancel CMD pending in runner
    msg = [utils.format_msg(m) for m in runner.cancel(idx)]
    # cancel CMD pending in message queue
    mq_lock.acquire()
    for _ in range(mq.qsize()):
        m = mq.get()
        if m["id"] != idx:
            mq.put(m)
        else:
            msg.append(utils.format_msg(m))
    mq_lock.release()
    socket.send_string("\nCanceled CMDs:\n" + "\n".join(msg))


@utils.register_to("history", _OPTION_IMPL)
def history(message: dict):
    if message["n"] < 0 or message["n"] > len(runner.finished_info):
        show = len(runner.finished_info)
    else:
        show = message["n"]
    msg = []
    for i in range(len(runner.finished_info) - show, len(runner.finished_info)):
        msg.append(utils.format_msg(runner.finished_info[i]))
    socket.send_string("\nFinished CMDs:\n" + "\n".join(msg))


@utils.register_to("kill", _OPTION_IMPL)
def kill(message: dict):
    msg = [utils.format_msg(m) for m in runner.kill(message["id"])]
    socket.send_string("\nKilled CMDs:\n" + "\n".join(msg))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backend to execute operations required by the client.",
    )
    # Required parameters
    parser.add_argument(
        "--gpus", required=True, type=str, help="Only find free GPU among these GPUs, e.g., '0,1,2,3,4,5,6,7'."
    )
    parser.add_argument(
        "--max-run", default=10000, type=int, help="The maximum number of pending commands to run."
    )
    parser.add_argument(
        "--num-records", default=10000, type=int, help="The maximum number of records of finished commands are kept."
    )
    parser.add_argument(
        "--port", default=25647, type=int, help="The port to communicate with the client."
    )
    parser.add_argument(
        "--limit", default=8, type=int, help="The maximum number of available GPUs returned."
    )
    parser.add_argument(
        "--max-load", default=0.1, type=float, help="The maximum load of GPUs to be considered as not available."
    )
    parser.add_argument(
        "--max-memory", default=0.1, type=float, help="The maximum memory of GPUs to be considered as not available."
    )
    args = parser.parse_args()

    logger.info(args)

    # set up variables from args
    hosted_gpus = [eval(gpu) for gpu in args.gpus.split(",")]
    utils.init(min(args.limit, len(hosted_gpus)), args.max_load, args.max_memory)
    with open("config.json", 'w') as f:
        json.dump({"port": args.port}, f)

    # build connection
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.connect("tcp://localhost:{}".format(args.port))

    # set up task runner
    mq = queue.Queue()
    mq_lock = threading.Lock()
    runner = Consumer(hosted_gpus, mq, mq_lock, args.num_records)
    runner.start()

    while True:
        message: dict = utils.recv(socket)
        logger.info("Receive: {}".format(message))
        try:
            _OPTION_IMPL[message["option"]](message)
        except KeyError:
            logger.warning(
                "Invalid option detected: {}. "
                "Please consider one of the following options: {}"
                    .format(message["option"], _OPTION_IMPL.keys())
            )
