# Auto
**Auto** is a simple job scheduling tool to manage your tasks and GPUs in a single machine with multiple GPUs. This tool has a simple interface and is very easy to use. Its installation has a minimal dependency and does not require `sudo`. If you are looking for a more powerful job scheduling system, like managing a cluster, please refer to [SLURM](https://slurm.schedmd.com/documentation.html).

In practice, it is very common for users to run multiple tasks (via the command line) in different GPUs of a single machine. It thus becomes tedious to manually monitor the available GPU resources before running the commands, say, keep typing `nvidia-smi` (though `watch nvidia-smi` or `nvidia-smi -l` will avoid the typing, you still need to watch the screen and run the command).

**Auto** is designed to meet such a demand. After running the server in the backend, users can submit any task (in a form of a series of commands) to the server via the client. The server will then do the job for users, like monitoring the available GPUs, assigning GPUs to tasks, running the tasks, etc. Users can also check the status of the submitted tasks for their own records via the client.

## Requirements
It supports Python 3.X.

It also depends on the following packages:

    GPUtil
    zmq

## Installation
```commandline
git clone https://github.com/lyy1994/auto.git
cd auto
pip install -r requirements.txt
```

## Usage
### Server
Before using this tool to automatically manage your tasks and GPUs, you need to run the server in the backend via the following command:

```commandline
nohup python server.py \
    --gpus 0,1,2,3 \
    --max-run 10000 \
    --num-records 10000 \
    --port 25647 \
    --limit 8 \
    --max-load 0.1 \
    --max-memory 0.1 &
```

- `--gpus`: **Required**, the ids of GPUs you want to manage by the server.
- `--max-run`: Optional, the maximum number of commands allowed to wait for GPU resources, default is *10000*.
- `--num-records`: Optional, the maximum number of finished commands kept, default is *10000*.
- `--port`: Optional, the portal to communicate with the clients, default is *25647*.
- `--limit`: Optional, the maximum number of available GPUs allocated to each command, default is *min(8, #gpus)*.
- `--max-load`: Optional, the maximum percentage of load for a GPU to be considered as *not available*, default is *0.1*.
- `--max-memory`: Optional, the maximum percentage of memory for a GPU to be considered as *not available*, default is *0.1*.

**TODO**: 
- [ ] Logging status, outputs, etc. to files (for debugging, restoration, etc.).

### Client
After running the server, you can now use the client to submit your tasks, check your task status, etc. By specifying different `option` of the client, the server will do different jobs for you.

#### Submit a task
You can submit your own tasks (in a form of commands) via the `run` option of the client. The server will execute the commands if the required GPU resources are available. The ID of the submitted task will be shown in the client side.

```commandline
python client.py run \
    --cmd "YOUR COMMAND1 && YOUR COMMAND2 && ..." \
    --n-gpus 1
```

- `--cmd`: **Required**, the commands you want to run.
- `--n-gpus`: Optional, the number of GPUs required by the inputted commands, default is *1*.

**IMPORTANT NOTE**:
1. The `run` option simply runs commands for you and it does not check the status of them, i.e., whether they are success or not. It is your responsibility to check the final results (success or not) of your commands.
2. The commands to run your tasks is passed to the server in a string format via `--cmd`. It is thus important to take care of the quotation mark in your command string if there is any.

[comment]: <> (3. You should not run a shell script via `--cmd`, otherwise the server will not be able to restrict the task to run on the available GPUs &#40;it is implemented via `export CUDA_VISIBLE_DEVICES=...` and a shell script will open a new shell that does not contain `CUDA_VISIBLE_DEVICES` in the current shell&#41;. One way to resolve this issue is to pass `$CUDA_VISIBLE_DEVICES` to your shell script as an argument and write `export CUDA_VISIBLE_DEVICES=...` within your script.)

**TODO**: 
- [ ] Support specifying CPUs & memory.

#### Check task status
You can check the status of your submitted tasks via the `status` option, e.g., whether they are running or waiting resources. The server will return a list of tasks that are running or waiting for GPUs, including their IDs, the required number of GPUs, the exact commands, etc.

```commandline
python client.py status
```

**TODO**: 
- [ ] Better formatting of the returned results, e.g., as a table.
- [ ] Return the records of failed commands.

#### Cancel a pending task
You can cancel a submitted but pending task via its ID in the `cancel` option, which can be retrieved from the output of `run` or `status`. The server will return the information about the cancelled task, including its exact commands, the required number of GPUs, etc.

```commandline
python client.py cancel \
    --id 1
```

- `--id`: **Required**, the task ID you want to cancel.

**TODO**: 
- [ ] Support cancelling multiple tasks via a list of ids, e.g., `1,2,3`.

#### Kill a running task
You can kill a running task via its ID in the `kill` option, which can be retrieved from the output of `run` or `status`. The server will return the information about the killed task, including its exact commands, the required number of GPUs, etc.

```commandline
python client.py kill \
    --id 1
```

- `--id`: **Required**, the task ID you want to cancel.

**TODO**: 
- [ ] Support killing multiple tasks via a list of ids, e.g., `1,2,3`.

#### View finished commands
You can view the finished tasks via the `history` option. The server will return the information about the finished tasks (either killed or done normally), including its ID, the time it finished, its exact commands, the required number of GPUs, etc.

```commandline
python client.py history \
    -n -1
```

- `-n`: Optional, the number of the most recent finished commands you want to show, default is `-1` (show all).

**IMPORTANT NOTE**:
1. The cancelled tasks will not be shown in the history.

**TODO**: 
- [ ] Support cleaning the history.

## Best Practices
1. To make the usage of the client easier, you can add `alias auto='python /path/to/auto/client.py'` to `~/.bashrc` and run `source ~/.bashrc`. Then specifying the option as well as its arguments becomes:

```commandline
auto <OPTION> [ARGUMENTS]
```

2. If you want to use **Auto** to manage multiple machines, a quick hack is to run a server for each machine (and you have to know their IPs and ports). Then you can submit tasks to different machines by overwriting the `--ip` and `--port` arguments in the client interface:

```commandline
auto --ip 127.0.0.1 --port 25647 <OPTION> [ARGUMENTS]
```

**TODO**: 
- [ ] Schedule tasks on multiple machines.
