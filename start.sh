#!/bin/bash

flask db upgrade
gunicorn --worker-class eventlet -w 1 -b $HOST:$PORT src.app:flask_app

