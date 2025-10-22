import asyncio
import logging
import functools
import time
import threading
from collections import OrderedDict

import numpy as np

from matplotlib.backends.qt_compat import QtCore
from bluesky.callbacks.mpl_plotting import QtAwareCallback

logger = logging.getLogger(__name__)


def catch_exceptions(fcn):
    @functools.wraps(fcn)
    def wrapped(*args, **kwargs):
        try:
            return fcn(*args, **kwargs)
        except Exception as ex:
            logger.error('Function call failed: %s(%s, %s)', fcn, args, kwargs,
                         exc_info=ex)
            raise

    return wrapped


class SubscanChecker:
    def __init__(self, subscan_rate):
        self._subscan_index = 0
        self._subscan_checker_enabled = False
        self._subscan_rate = subscan_rate

    def start_subscan_checker(self):
        if not self._subscan_checker_enabled:
            logger.debug('Starting subscan checker')
            self._subscan_checker_enabled = True
            self._schedule_subscan_check()

    def stop_subscan_checker(self):
        if self._subscan_checker_enabled:
            logger.debug('Stopping subscan checker')
            self._subscan_checker_enabled = False

    def _schedule_subscan_check(self):
        QtCore.QTimer.singleShot(int(self._subscan_rate * 1000), self.check_subscan)

    def check_subscan(self):

        if self._subscan_checker_enabled:

            flyer = self.flyer
            if flyer is not None and flyer.scan_count == 1:
                self.stop_subscan_checker()
                return

            try:
                if flyer is None or flyer.scan_count <= 1:
                    pass
                else:
                    last_index = self._subscan_index
                    if flyer.scan_index > last_index:
                        self._subscan_index = flyer.scan_index
                        self.subscan_start(index=self._subscan_index)
            finally:
                self._schedule_subscan_check()


class FlyDataCallbacks(SubscanChecker, QtAwareCallback):
    def __init__(self, flyer=None, subscan_rate=0.5):
        SubscanChecker.__init__(self, subscan_rate=subscan_rate)
        QtAwareCallback.__init__(self)

        self.flyer = flyer
        self._run_header = None

    @catch_exceptions
    def start(self, doc):
        self._run_header = doc
        logger.debug('Run header: scan_id=%d (%s)', doc['scan_id'],
                     self.__class__.__name__)

        self.scan_id = doc['scan_id']
        self.fast_axis = doc['fast_axis']
        dims = doc['shape']
        ndim = len(dims)
        self.num = np.product(dims)
        self._subscan_index = 0

        if ndim == 1:
            pass
        elif ndim == 2:
            self.start_subscan_checker()
        else:
            logger.error('Unsupported scan dimensions')
            return

        logger.debug('Number of points=%d', self.num)
        self.scan_started(doc, ndim, fast_axis=self.fast_axis,
                          **doc['plan_args'])

    @catch_exceptions
    def stop(self, doc):
        if self.flyer is None:
            logger.error('Flyer unset - not running scan_finished')
            return

        flyer = self.flyer
        self.stop_subscan_checker()

        while not flyer.done:
            logger.debug('Waiting for flyscan to finish')
            time.sleep(0.2)

        scan_data = self.flyer.data.get(self.scan_id, {})

        finish_func = (self.scan_failed if flyer.failed
                       else self.scan_finished)

        try:
            finish_func(doc, scan_data, cancelled=self.flyer.cancelled)
        finally:
            self._run_header = None
            self.flyer = None

    def scan_started(self, doc, ndim, **scan_kwargs):
        '''Re-implement me'''
        pass

    def scan_failed(self, doc, scan_data, **kwargs):
        '''Re-implement me'''
        pass

    def scan_finished(self, doc, scan_data, cancelled=False, **kwargs):
        '''Re-implement me'''
        pass

    def subscan_start(self, index=0, **kwargs):
        '''Re-implement me'''
        pass


def default_data_func(*arrays):
    return np.sum(arrays, axis=0)


class SignalDataHandler:
    def __init__(self, groups, data_func=None, point_signal=None):
        self.groups = groups
        self.point_signal = point_signal
        self.data_func = data_func
        self.signals = sum((signals for group, signals in groups.items()), [])
        self._updated = True
        self._lock = threading.RLock()
        self._calculated = None

        if point_signal is not None:
            point_signal.subscribe(self._value_updated)
        else:
            for sig in self.signals:
                sig.subscribe(self._value_updated)
        if not groups:
            raise ValueError('Must have at least one signal')

    @property
    def updated(self):
        '''Any signals changed since the last calculation?'''
        return self._updated

    def _value_updated(self, **kwargs):
        with self._lock:
            self._updated = True

    def get_group_data(self, key, npts):
        group_data = []
        for signal in self.groups[key]:
            try:
                value = signal.get(count=npts)
            except Exception as ex:
                logger.debug('Caget failed for signal %s', signal,
                             exc_info=ex)
                value = None

            if value is not None:
                try:
                    len(value)
                except TypeError:
                    value = [value]

                if len(value) < npts:
                    value = np.concatenate((value, [0] * (npts - len(value))))
                group_data.append(value)
            else:
                group_data.append(np.zeros(npts))
        return group_data

    @catch_exceptions
    def calc_data(self, npts):
        with self._lock:
            if not self._updated:
                return self._calculated
            elif npts <= 0:
                return OrderedDict((label, [])
                                   for label, signals in self.groups.items())

            data = OrderedDict()
            data_func = (self.data_func if self.data_func is not None
                         else default_data_func)

            for label, signals in self.groups.items():
                group_data = self.get_group_data(label, npts)
                data[label] = data_func(*group_data)

            self._updated = False
            self._calculated = data

        return OrderedDict(self._calculated)

    @property
    def num_points(self):
        if self.point_signal is None:
            raise ValueError('No point signal set')

        return self.point_signal.get(use_monitor=False)


class SubscanDataHandler:
    def __init__(self, key_groups, data_func=None):
        self.key_groups = key_groups
        self.data_func = data_func

    def calc_data(self, flyer, scan_id):
        try:
            data = flyer.data[scan_id]
        except KeyError:
            return OrderedDict()

        data_func = (self.data_func if self.data_func is not None
                     else default_data_func)
        return OrderedDict((main_key, data_func(*[data[key] for key in keys]))
                           for main_key, keys in self.key_groups.items())
