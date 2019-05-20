#!/bin/bash

. venv/bin/activate

git pull
pip install -r requirements.txt
pids=$(pgrep python)
kill -9 $pids
python run_background_tasks.py &
python serve.py &

sudo scalyr-agent-2 restart