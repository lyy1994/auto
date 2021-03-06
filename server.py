import argparse
import queue
import threading
import json

import zmq

from datetime import datetime

import utils
import logger
from consumer import Consumer


_OPTION_IMPL = {}
counter = 0


@utils.register_to("run", _OPTION_IMPL)
def run(message: dict):
    global counter
    mq_lock.acquire()
    if mq.qsize() >= args.max_run:
        msg = "Reaching the maximum number ({}) of pending tasks to run!".format(args.max_run)
        logger.warning(msg)
        socket.send_string(msg)
        mq_lock.release()
        return
    message["id"] = counter
    message["submit_time"] = datetime.today()
    mq.put(utils.PrioritizedItem(message["priority"], message["submit_time"], message))
    mq_lock.release()
    socket.send_string("Task id: {}".format(counter))
    counter = (counter + 1) % args.max_run


@utils.register_to("status", _OPTION_IMPL)
def status(message: dict):
    # running CMDs
    running = [utils.format_msg(m) for m in runner.running_status()]
    pending = []
    # pending CMDs in message queue
    mq_lock.acquire()
    temp = []
    while not mq.empty():
        m: utils.PrioritizedItem = mq.get()
        temp.append(m)
        pending.append(utils.format_msg(m.item))
    for m in temp:
        mq.put(m)
    del temp
    mq_lock.release()
    socket.send_string("Runner Status:\nRunning Tasks:\n" + "\n".join(running) + "\nPending Tasks:\n" + "\n".join(pending))


@utils.register_to("cancel", _OPTION_IMPL)
def cancel(message: dict):
    ids = message["ids"]
    msg = []
    # cancel CMD pending in message queue
    mq_lock.acquire()
    temp = []
    while not mq.empty():
        m: utils.PrioritizedItem = mq.get()
        if m.item["id"] not in ids:
            temp.append(m)
        else:
            msg.append(utils.format_msg(m.item))
    for m in temp:
        mq.put(m)
    del temp
    mq_lock.release()
    socket.send_string("\nCanceled Tasks:\n" + "\n".join(msg))


@utils.register_to("history", _OPTION_IMPL)
def history(message: dict):
    if message["fail"]:
        msg = "\nFailed Tasks:\n" + "\n".join([utils.format_msg(m) for m in runner.fail(message["num_records"])])
    else:
        msg = "\nSucceed Tasks:\n" + "\n".join([utils.format_msg(m) for m in runner.success(message["num_records"])])
    socket.send_string(msg)


@utils.register_to("kill", _OPTION_IMPL)
def kill(message: dict):
    msg = [utils.format_msg(m) for m in runner.kill(message["ids"])]
    socket.send_string("\nKilled Tasks:\n" + "\n".join(msg))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backend to execute operations required by the client.",
    )
    # Required parameters
    parser.add_argument(
        "--gpus", required=True, type=int, nargs='+', help="Only find free GPU among these GPUs, e.g., '0 1 2 3'."
    )
    parser.add_argument(
        "--max-run", default=10000, type=int, help="The maximum number of pending tasks to run."
    )
    parser.add_argument(
        "--num-records", default=10000, type=int, help="The maximum number of records of finished tasks are kept."
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
    parser.add_argument(
        "--log-file", default=None, type=str, help="The file path to store the logging output."
    )
    args = parser.parse_args()

    logger.config(
        format="%(asctime)s | %(levelname)s >> %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handler=args.log_file,
    )
    logger.info(args)

    # set up variables from args
    hosted_gpus = args.gpus
    utils.init(min(args.limit, len(hosted_gpus)), args.max_load, args.max_memory)
    with open("config.json", 'w') as f:
        json.dump({"port": args.port}, f)

    # build connection
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.connect("tcp://localhost:{}".format(args.port))

    # set up task runner
    mq = queue.PriorityQueue()
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
