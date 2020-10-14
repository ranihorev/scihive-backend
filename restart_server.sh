#!/bin/bash

. venv/bin/activate

git pull
pip install -r requirements.txt

pkill python
pkill flask

flask db upgrade

python -m src.app &
flask run-background-tasks &
