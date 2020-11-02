#!/bin/bash

flask db upgrade || { echo 'DB upgrade failed' ; exit 1; }
python -m src.app

