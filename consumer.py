import threading
import queue
import subprocess
import os
import signal

from collections import deque
from datetime import datetime

import utils


class Consumer(threading.Thread):
    def __init__(self, hosted_gpus: list, mq: queue.Queue, mq_lock: threading.Lock, num_records: int):
        super().__init__()
        self.mq = mq
        self.mq_lock = mq_lock  # lock for mq threading safety
        self.p_lock = threading.Lock()  # lock for pending_info threading safety
        self.r_lock = threading.Lock()  # lock for running_info threading safety
        self.hosted_gpus = hosted_gpus
        self.exclude_gpus = []
        self.process_on_gpu = {}  # CMD processes

        # TODO: it is better to keep everything into a file for restoring in case of system crash.
        self.running_info = {}  # info about CMDs that are running
        self.pending_info = []  # info about CMDs that are retrieved from queue but not being run
        self.finished_info = deque(maxlen=num_records)  # info about the most recent hist_size CMDs that are finished

    def cancel(self, idx):
        msg = []
        self.p_lock.acquire()
        for _ in range(len(self.pending_info)):
            m = self.pending_info.pop(0)
            if m["id"] != idx:
                self.pending_info.append(m)
            else:
                msg.append(m)
        self.p_lock.release()
        return msg

    def kill(self, idx):
        msg = []
        self.r_lock.acquire()
        # kill CMD in runner.running_info by id
        for p, m in self.running_info.items():
            if m["id"] == idx:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
                msg.append(m)
        self.r_lock.release()
        return msg

    def running_status(self):
        msg = []
        self.r_lock.acquire()
        for v in self.running_info.values():
            msg.append(v)
        self.r_lock.release()
        return msg

    def pending_status(self):
        msg = []
        self.p_lock.acquire()
        for m in self.pending_info:
            msg.append(m)
        self.p_lock.release()
        return msg

    def run(self) -> None:
        while True:
            if not self.mq.empty():
                self.mq_lock.acquire()
                msg: dict = self.mq.get()
                self.mq_lock.release()

                idx, n_gpus, cmd = msg["id"], msg["n_gpus"], msg["cmd"]

                gpus = utils.get_free_gpus(host_ids=self.hosted_gpus, exclude_ids=self.exclude_gpus)

                self.p_lock.acquire()
                self.pending_info.append(msg)  # current CMD might not have enough resources to run
                self.p_lock.release()

                while len(gpus) < n_gpus:
                    # keep monitoring the running processes until enough resources are available
                    processes = list(self.process_on_gpu.keys())
                    for p in processes:
                        if p.poll() is not None:
                            for g in self.process_on_gpu[p]:
                                self.exclude_gpus.remove(g)
                            self.process_on_gpu.pop(p)
                            self.r_lock.acquire()
                            m = self.running_info.pop(p)
                            self.r_lock.release()
                            m["time"] = str(datetime.today().strftime('%Y-%m-%d %H:%M:%S'))
                            self.finished_info.append(m)
                    gpus = utils.get_free_gpus(host_ids=self.hosted_gpus, exclude_ids=self.exclude_gpus)

                self.p_lock.acquire()
                try:
                    self.pending_info.pop(0)  # current CMD have enough resources to run
                except IndexError:
                    # TODO: though CMD is cancelled, its --n-gpus still have an impact on waiting resources
                    continue  # CMD is cancelled
                finally:
                    self.p_lock.release()  # avoid deadlock

                gpu = gpus[:n_gpus]
                gpu_str = ",".join([str(i) for i in gpu])

                cmd = "export CUDA_VISIBLE_DEVICES={} && ".format(gpu_str) + cmd

                p = subprocess.Popen(cmd, shell=True, preexec_fn=os.setsid)
                self.exclude_gpus += gpu
                self.process_on_gpu[p] = gpu
                self.r_lock.acquire()
                self.running_info[p] = msg
                self.r_lock.release()
            else:
                # if no incoming CMDs to run, then check whether running CMDs is finished
                processes = list(self.process_on_gpu.keys())
                for p in processes:
                    if p.poll() is not None:
                        for g in self.process_on_gpu[p]:
                            self.exclude_gpus.remove(g)
                        self.process_on_gpu.pop(p)
                        self.r_lock.acquire()
                        m = self.running_info.pop(p)
                        self.r_lock.release()
                        m["time"] = str(datetime.today().strftime('%Y-%m-%d-%H:%M:%S'))
                        self.finished_info.append(m)
