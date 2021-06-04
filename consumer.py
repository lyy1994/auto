import threading
import queue
import subprocess
import os
import signal

from collections import deque
from datetime import datetime

import utils


class Consumer(threading.Thread):
    def __init__(self,
                 hosted_gpus: list,
                 mq: queue.PriorityQueue,
                 mq_lock: threading.Lock,
                 num_records: int):
        super().__init__()
        self.mq = mq
        self.mq_lock = mq_lock  # lock for mq threading safety
        self.hosted_gpus = hosted_gpus
        self.exclude_gpus = []
        self.process_on_gpu = {}  # CMD processes

        # TODO: it is better to keep everything into a file for restoring in case of system crash.
        self.r_lock = threading.Lock()  # lock for running_info threading safety
        self.running_info = {}  # info about CMDs that are running
        self.f_lock = threading.Lock()  # lock for fail_info threading safety
        self.fail_info = deque(maxlen=num_records)  # info about the most recent failed CMDs
        self.s_lock = threading.Lock()  # lock for success_info threading safety
        self.success_info = deque(maxlen=num_records)  # info about the most recent succeed CMDs

    def kill(self, ids: list) -> list:
        msg = []
        self.r_lock.acquire()
        # kill CMD in runner.running_info by id
        for p, m in self.running_info.items():
            if m["id"] in ids:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
                msg.append(m)
        self.r_lock.release()
        return msg

    def running_status(self) -> list:
        msg = []
        self.r_lock.acquire()
        for v in self.running_info.values():
            msg.append(v)
        self.r_lock.release()
        return msg

    @staticmethod
    def _read_recent(q: deque, l: threading.Lock, n: int) -> list:
        l.acquire()
        if n < 0 or n > len(q):
            show = len(q)
        else:
            show = n
        msg = []
        for i in range(len(q) - show, len(q)):
            msg.append(q[i])
        l.release()
        return msg

    def success(self, num_records: int) -> list:
        return self._read_recent(self.success_info, self.s_lock, num_records)

    def fail(self, num_records: int) -> list:
        return self._read_recent(self.fail_info, self.f_lock, num_records)

    def run(self) -> None:
        while True:
            # first check whether running CMDs is finished
            processes = list(self.process_on_gpu.keys())
            for p in processes:
                if p.poll() is not None:  # process is done
                    for g in self.process_on_gpu[p]:
                        self.exclude_gpus.remove(g)  # release GPUs
                    self.process_on_gpu.pop(p)
                    self.r_lock.acquire()
                    m = self.running_info.pop(p)  # clean running record
                    self.r_lock.release()
                    m["time"] = str(datetime.today().strftime('%Y-%m-%d-%H:%M:%S'))
                    if p.returncode is not None:  # just for safety, should not be None after calling .poll()
                        # add to history
                        if p.returncode == 0:
                            self.s_lock.acquire()
                            self.success_info.append(m)
                            self.s_lock.release()
                        else:
                            self.f_lock.acquire()
                            m["return_code"] = p.returncode
                            self.fail_info.append(m)
                            self.f_lock.release()
            # then allocate resources to incoming CMDs
            if not self.mq.empty():
                self.mq_lock.acquire()
                msg: utils.PrioritizedItem = self.mq.get()
                n_gpus, cmd = msg.item["num_gpus"], msg.item["cmd"]
                gpus = utils.get_free_gpus(host_ids=self.hosted_gpus, exclude_ids=self.exclude_gpus)
                if len(gpus) >= n_gpus:  # if there is enough resources, then run it
                    gpu = gpus[:n_gpus]
                    gpu_str = ",".join([str(i) for i in gpu])
                    msg.item["GPUs"] = gpu_str
                    cmd = "export CUDA_VISIBLE_DEVICES={} && ".format(gpu_str) + cmd
                    p = subprocess.Popen(cmd, shell=True, preexec_fn=os.setsid)
                    self.exclude_gpus += gpu  # reserve GPUs for CMD
                    self.process_on_gpu[p] = gpu  # for checking status
                    self.r_lock.acquire()
                    self.running_info[p] = msg.item  # add running record
                    self.r_lock.release()
                else:  # if not, then put it back to the queue for waiting
                    self.mq.put(msg)
                self.mq_lock.release()
