import threading
import queue
import subprocess
import os
import signal
import time

from collections import deque
from datetime import datetime

import utils


class Consumer(threading.Thread):
    def __init__(self,
                 hosted_gpus: list,
                 mq: queue.PriorityQueue,
                 mq_lock: threading.Lock,
                 num_records: int,
                 check_interval: int = 1):
        super().__init__()
        self.mq = mq
        self.mq_lock = mq_lock  # lock for mq threading safety
        self.hosted_gpus = hosted_gpus
        self.check_interval = check_interval
        self.exclude_gpus = []
        self.process_on_gpu = {}  # CMD processes

        # TODO: it is better to keep everything into a file for restoring in case of system crash.
        self.r_lock = threading.Lock()  # lock for running_info threading safety
        self.running_info = {}  # info about CMDs that are running
        self.f_lock = threading.Lock()  # lock for finished_info threading safety
        self.finished_info = deque(maxlen=num_records)  # info about the most recent hist_size CMDs that are finished

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

    def history(self, num_records):
        self.f_lock.acquire()
        if num_records < 0 or num_records > len(self.finished_info):
            show = len(self.finished_info)
        else:
            show = num_records
        msg = []
        for i in range(len(self.finished_info) - show, len(self.finished_info)):
            msg.append(self.finished_info[i])
        self.f_lock.release()
        return msg

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
                    self.f_lock.acquire()
                    self.finished_info.append(m)  # add to history
                    self.f_lock.release()
            # then allocate resources to incoming CMDs
            if not self.mq.empty():
                self.mq_lock.acquire()
                msg: utils.PrioritizedItem = self.mq.get()
                self.mq_lock.release()
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
                    self.mq_lock.acquire()
                    self.mq.put(msg)
                    self.mq_lock.release()
            time.sleep(self.check_interval)
