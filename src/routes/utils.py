from typing import Callable
from flask import Flask
from flask.globals import current_app
from flask_socketio import SocketIO


def context_provider(func: Callable, flask_app: Flask, *args, **kwargs):
    with flask_app.app_context():
        func(*args, **kwargs)


def start_background_task(target: Callable, *args, **kwargs):
    socketio_app: SocketIO = getattr(current_app, 'socketio_app', None)
    flask_app = current_app._get_current_object()
    if socketio_app:
        socketio_app.start_background_task(target=context_provider, func=target, flask_app=flask_app, *args, **kwargs)
