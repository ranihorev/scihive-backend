#!/bin/bash

. venv/bin/activate

git pull
pip install -r requirements.txt

# Make sure that the python version is correct

if [ ! -d venv/lib/python3.6/site-packages/en_core_web_sm ]
then
    python -m spacy download en_core_web_sm
else
    echo "Spacy model was found"
fi

pids=$(pgrep python)
kill -9 $pids
# python src/run_background_tasks.py &
python app.py &

# sudo scalyr-agent-2 restart