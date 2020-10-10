import re
from typing import Tuple


def catch_exceptions(logger):
    def decorator(func):

        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except:
                # log the exception
                err = "There was an exception in  "
                err += func.__name__
                logger.exception(err)

        return wrapper

    return decorator


def parse_arxiv_url(url: str) -> Tuple[str, int]:
    """
    examples is http://arxiv.org/abs/1512.08756v2
    we want to extract the raw id and the version
    """
    match = re.search(r"/(?P<id>(\d{4}\.\d{4,5})|([a-zA-Z\-.]+/\d{6,10}))(v(?P<version>\d+))?", url)
    return match.group('id').replace('/', '_'), int(match.group('version') or 0)
