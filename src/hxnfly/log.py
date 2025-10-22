import os
import logging
import logging.handlers
from . import logger


handler = None


def log_setup(level=logging.DEBUG, log_path=None):
    global handler

    if handler is not None:
        return

    if log_path is None:
        log_path = os.path.expanduser('~/flyscan_debug.log')

    fmt = logging.Formatter('%(asctime)s - %(funcName)s/%(levelname)s: '
                            '%(message)s')

    handler = logging.handlers.TimedRotatingFileHandler(log_path, 'W6')
    handler.setLevel(level)

    handler.setFormatter(fmt)
    logger.addHandler(handler)


def log_time(logger, time_dict, name, *, t1=None, t2=None, ms=True):
    '''Calculate time difference and log it
    '''
    if t1 is not None and t2 is not None:
        dt = time_dict[t2] - time_dict[t1]
        time_dict[name] = dt
    else:
        dt = time_dict[name]

    if dt > 5.0 and ms:
        ms = False

    if ms:
        units = 'ms'
        dt *= 1000.0
    else:
        units = 's'

    logger.debug('%s: %.1f %s', name, dt, units)
