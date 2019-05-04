#!/bin/bash

. venv/bin/activate

pip install -r requirements.txt
git pull
pids=$(pgrep python)
kill -9 $pids
python run_background_tasks.py &
python serve.py &

sudo scalyr-agent-2 restart