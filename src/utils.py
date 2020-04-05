from os import path


def get_file_path(current_file: str, filename: str):
    return path.join(path.realpath(path.dirname(current_file)), filename)