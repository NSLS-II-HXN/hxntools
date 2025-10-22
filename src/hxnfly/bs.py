import IPython
import numpy as np
import logging
import time
from contextlib import contextmanager

import ophyd
import ophyd.flyers
# import ophyd.pseudopos
# from ophyd.device import Component as Cpt
from cycler import cycler
from .object_plans import Plan
from bluesky.run_engine import Msg
from bluesky.utils import Subs

from .callbacks.table import BulkLiveTable
from .log import log_time


logger = logging.getLogger(__name__)


@contextmanager
def elapsed_time_context(log_msg):
    t1 = time.time()
    yield
    t2 = time.time()

    t_dict = {'t1': t1,
              't2': t2}

    try:
        log_time(logger, t_dict, log_msg, t1='t1', t2='t2')
    except Exception:
        pass


def maybe_a_table(scan):
    ip = IPython.get_ipython()
    table_max_lines = ip.user_ns.get('table_max_lines', 5000)

    flyer = scan.flyer
    if flyer.total_points < table_max_lines:
        # logbook = ip.user_ns.get('logbook', None)
        # if logbook is not None:
        #   logbook = logbook.log
        return BulkLiveTable(fields=flyer.table_columns[:15]
                             # logbook=logbook,
                             )


def update_subs(subs, flyer):
    '''Update subscriptions with a flyer instance

    Only updates subscriptions with an existing 'flyer' attribute.
    '''
    for name, sub_list in subs.items():
        for sub in sub_list:
            if hasattr(sub, 'flyer'):
                sub.flyer = flyer


class FlyPlan(Plan):
    def __init__(self, usable_detectors=None, scaler_channels=None,
                 init_kw=None, *, md=None):
        super().__init__()

        if init_kw is None:
            init_kw = {}
        if scaler_channels is None:
            scaler_channels = [1, 2, 3, 4, 5, 6]
        if usable_detectors is None:
            ip = IPython.get_ipython()
            usable_detectors = [ip.user_ns[det_name] for det_name in
                                ('xspress3', 'merlin1', 'zebra', 'sclr1',
                                 'dexela1')
                                if det_name in ip.user_ns
                                ]

        self.usable_detectors = list(usable_detectors)
        self.scaler_channels = list(scaler_channels)
        self.init_kw = init_kw
        self.md = md if md is not None else {}
        self.motors = []

    def _instance_from_motors(self, *motors):
        self.init_kw.update(scaler_channels=self.scaler_channels)

        if not hasattr(self, 'scans') or not self.scans:
            raise ValueError('Scans must be setup')

        fset = frozenset(motors)
        try:
            cls = self.scans[fset]
        except KeyError:
            options = '\n'.join(', '.join(mtr.name for mtr in key)
                                for key in self.scans.keys())
            raise ValueError('Can only use these motors in a flyscan:' +
                             options)

        return cls(detectors=self.detectors, **self.init_kw)

    def _update_md(self):
        # update the metadata from various sources:
        for md in [self.flyer.md, self._configure_kw]:
            self.md.update(**md)

        # ensure we aren't trying to save devices in mds
        for key, value in self.md.items():
            if isinstance(value, (ophyd.Signal, ophyd.Device)):
                self.md[key] = value.name

        self.md['detectors'] = [det.name for det in self.detectors]
        self.md['motors'] = [motor.name for motor in
                             self.flyer._subscans[0]['positioners']]
        self.md['fast_axis'] = self.md['motors'][0]
        self.md['plan_name'] = self.__class__.__name__
        self.md['plan_type'] = self.__class__.__name__  # ?

        # remove macros that are in the top-level metadata to lessen redundancy
        if 'macros' not in self.md:
            return

        for macro, value in list(self.md['macros'].items()):
            if self.md.get(macro, None) == value:
                del self.md['macros'][macro]

    def __call__(self):
        # **TODO** calling configure twice to ensure subs get valid information
        #          on the flyer
        self.flyer.configure(**self._configure_kw)
        update_subs(self.subs, self.flyer)
        yield from super().__call__()

    def _gen(self):
        yield Msg('hxn_next_scan_id')
        yield Msg('configure', self.flyer, **self._configure_kw)
        self._update_md()
        yield Msg('open_run', **self.md)

        for subscan in range(self.flyer.scan_count):
            yield from flyer_plan(self.flyer, subscan=subscan)

        yield Msg('close_run')


def flyer_plan(flyer, subscan, *, name='primary'):
    '''Plan to run a flyer'''
    with elapsed_time_context('checkpoint'):
        yield Msg('checkpoint')
        # start the flyscan
        with elapsed_time_context('flyscan'):
            yield Msg('kickoff', flyer, subscan=subscan,
                      group='fly-kickoff', name=name)
            yield Msg('wait', None, 'fly-kickoff')

            # wait for the collect to be ready
            yield Msg('complete', flyer, group='fly-collect')
            yield Msg('wait', None, 'fly-collect')

        yield Msg('collect', flyer)


class FlyPlan1D(FlyPlan):
    '''1D fly scan

    A continuous, relative scan of `motor` from scan_start to scan_end,
    triggering detectors `scan_points` times.  The speed to move the positioner
    will be automatically determined to get a consistent `exposure_time`.

    Parameters
    ----------
    motor : Positioner
        The motor to scan
    scan_start : float
        Ending position (relative) [um]
    scan_end : float
        Ending position (relative) [um]
    scan_points : int
        Number of scan points
    exposure_time : float
        Exposure time in seconds

    dead_time : float, optional
        Between-frame dead time to allow detectors to write their data out.
        If set too low, some detectors may not acquire and scans may fail.
    return_speed : float
        The speed at which to return the motor to its starting position after
        the scan
    fly_type : str, optional
        'soft' uses trajectory generation and triggering via motion scripts
        'fly' normal 'fly-scan' concept, using position compare (note that this
        is not yet setup at the HXN)
    md : dict, optional
        Additional metadata to be saved
    '''
    sub_factories = Subs([maybe_a_table])

    def __call__(self, dets, motor, scan_start, scan_end, num, exposure_time, *,
                 dead_time=None, return_speed=None, fly_type=None, md=None):
        self.detectors = dets
        if md is not None:
            self.md.update(**md)

        self.flyer = self._instance_from_motors(motor)

        defaults = self.flyer.configure_defaults
        self._configure_kw = dict(
            motor=motor,
            scan_start=scan_start,
            scan_end=scan_end,
            num=num,
            exposure_time=exposure_time,
            dead_time=dead_time or defaults['dead_time'],
            return_speed=return_speed or defaults['return_speed'],
            fly_type=fly_type or defaults['fly_type']
        )

        self.motors = [motor]

        self.md['plan_args'] = dict(
            motor=repr(motor),
            start=scan_start, stop=scan_end, num=num,
            time=exposure_time,
            dead_time=self._configure_kw['dead_time'],
            return_speed=self._configure_kw['return_speed'],
            fly_type=self._configure_kw['fly_type'],
        )
        yield from super().__call__()


class FlyPlan2D(FlyPlan):
    '''2D fly scan

    A continuous, outer-product relative scan of
        `motor1` from scan_start1 to scan_end1 of num1 points
    and a relative scan of
        `motor2` from scan_start2 to scan_end2 of num2 points

    triggering detectors `num1` * `num2` times.  The speed to move the
    first positioner will be automatically determined to get a consistent
    `exposure_time`.

    Parameters
    ----------
    motor1 : Positioner
        The fast motor to scan
    scan_start1 : float
        Ending position (relative) [um]
    scan_end1 : float
        Ending position (relative) [um]
    num1 : int
        Number of scan points
    motor2 : Positioner
        The slow motor to scan
    scan_start2 : float
        Ending position (relative) [um]
    scan_end2 : float
        Ending position (relative) [um]
    num2 : int
        Number of scan points
    exposure_time : float
        Exposure time in seconds

    dead_time : float, optional
        Between-frame dead time to allow detectors to write their data out.
        If set too low, some detectors may not acquire and scans may fail.
    return_speed : float
        The speed at which to return the motor to its starting position after
        the scan
    fly_type : str, optional
        'soft' uses trajectory generation and triggering via motion scripts
        'fly' normal 'fly-scan' concept, using position compare (note that this
        is not yet setup at the HXN)
    max_points : int, optional
        Maximum number of scan points to execute in one 2D fly-scan (defaults
        to 16K, a limitation imposed by the Xspress3)
    md : dict, optional
        Additional metadata to be saved
    '''
    sub_factories = Subs([maybe_a_table])

    def __call__(self,
                 dets,
                 motor1, scan_start1, scan_end1, num1,
                 motor2, scan_start2, scan_end2, num2,
                 exposure_time,
                 *,
                 dead_time=None, fly_type=None,
                 return_speed=None, max_points=None, md=None):
        '''
        Additional user_kw arguments are passed to fly2d.Fly2D._configure

        Parameters not recognized by that method are sent to the metadatastore
        '''
        self.detectors = dets
        if md is not None:
            self.md.update(**md)

        self.flyer = self._instance_from_motors(motor1, motor2)

        defaults = self.flyer.configure_defaults
        self._configure_kw = dict(
            motor1=motor1,
            scan_start1=scan_start1,
            scan_end1=scan_end1,
            num1=num1,

            motor2=motor2,
            scan_start2=scan_start2,
            scan_end2=scan_end2,
            num2=num2,

            exposure_time=exposure_time,
            dead_time=dead_time or defaults['dead_time'],
            fly_type=fly_type or defaults['fly_type'],
            return_speed=return_speed or defaults['return_speed'],
            max_points=max_points or defaults['max_points'],
        )

        self.motors = [motor1, motor2]
        self.md['plan_args'] = dict(self._configure_kw)
        for key in ('motor1', 'motor2'):
            self.md['plan_args'][key] = repr(self.md['plan_args'][key])

        yield from super().__call__()


class FlyStep1D(FlyPlan):
    '''1D fly scan plus 1D step-scan

    A continuous, outer-product relative fly-scan of
        `motor1` from scan_start1 to scan_end1 of num1 points
    and a relative step-scan of
        `motor2` from scan_start2 to scan_end2 of num2 points

    triggering detectors `num1` * `num2` times.  The speed to move the
    first positioner will be automatically determined to get a consistent
    `exposure_time`.

    Parameters
    ----------
    motor1 : Positioner
        The fast motor to scan
    scan_start1 : float
        Ending position (relative) [um]
    scan_end1 : float
        Ending position (relative) [um]
    num1 : int
        Number of scan points
    motor2 : Positioner
        The slow motor to scan
    scan_start2 : float
        Ending position relative)
    scan_end2 : float
        Ending position (relative)
    num2 : int
        Number of scan points
    exposure_time : float
        Exposure time in seconds

    dead_time : float, optional
        Between-frame dead time to allow detectors to write their data out.
        If set too low, some detectors may not acquire and scans may fail.
    return_speed : float
        The speed at which to return the motor to its starting position after
        the scan
    fly_type : str, optional
        'soft' uses trajectory generation and triggering via motion scripts
        'fly' normal 'fly-scan' concept, using position compare (note that this
        is not yet setup at the HXN)
    md : dict, optional
        Additional metadata to be saved
    record_motor2 : bool, optional
        Record motor2 positions in a separate stream. Default is True.
        It may be preferable to disable this if all axes exist on the
        pmac controller
    '''
    sub_factories = Subs([maybe_a_table])

    def __call__(self,
                 dets,
                 motor1, scan_start1, scan_end1, num1,
                 motor2, scan_start2, scan_end2, num2,
                 exposure_time,
                 *,
                 dead_time=None, fly_type=None,
                 return_speed=None, md=None, record_motor2=True):
        '''
        Additional user_kw arguments are passed to fly2d.Fly2D._configure

        Parameters not recognized by that method are sent to the metadatastore
        '''
        self.detectors = dets
        if md is not None:
            self.md.update(**md)

        self.flyer = self._instance_from_motors(motor1)

        defaults = self.flyer.configure_defaults
        self._configure_kw = dict(
            motor=motor1,
            scan_start=scan_start1,
            scan_end=scan_end1,
            num=num1,

            exposure_time=exposure_time,
            dead_time=dead_time or defaults['dead_time'],
            fly_type=fly_type or defaults['fly_type'],
            return_speed=return_speed or defaults['return_speed'],
        )

        self.md['plan_args'] = dict(
            motor1=repr(motor1),
            scan_start1=scan_start1,
            scan_end1=scan_end1,
            num1=num1,

            motor2=repr(motor2),
            scan_start2=scan_start2,
            scan_end2=scan_end2,
            num2=num2,

            exposure_time=self._configure_kw['exposure_time'],
            dead_time=self._configure_kw['dead_time'],
            fly_type=self._configure_kw['fly_type'],
            return_speed=self._configure_kw['return_speed'],

            record_motor2=record_motor2,
        )

        self.motors = [motor1, motor2]

        # Record the steps the slow motor has to take:
        positions = np.linspace(motor2.position + scan_start2,
                                motor2.position + scan_end2,
                                num=num2, endpoint=True)
        self.slow_steps = cycler(motor2, positions)

        all_flyer_axes = all(key in self.flyer.positioner_to_axis for key in
                             self.slow_steps.keys)

        if not record_motor2 or all_flyer_axes:
            self.slow_flyer = None
        else:
            class SlowFlyer(ophyd.flyers.MonitorFlyerMixin, ophyd.Device):
                pass

            if isinstance(motor2, ophyd.EpicsMotor):
                motor2 = motor2.user_readback
            # elif isinstance(motor2, ophyd.pseudopos.PseudoPositioner):
            #     motor2 = motor2.user_readback

            self.slow_flyer = SlowFlyer('', name='slow_flyer', pivot=True)
            # TODO: this only supports one motor now, but is easy to extend
            self.slow_flyer.monitor_attrs = [motor2.name]
            self.slow_flyer.stream_names = {motor2.name: 'motor2'}
            setattr(self.slow_flyer, motor2.name, motor2)

            # for mtr in self.slow_steps.keys:
            #     if isinstance(mtr, ophyd.EpicsMotor):
            #         mtr = mtr.user_readback
            #     setattr(self.slow_flyer, mtr.name, mtr)

        yield from super().__call__()

    def _update_md(self):
        super()._update_md()

        motor2 = list(self.slow_steps.keys)[0]
        steps = self.slow_steps.by_key()[motor2]

        # metadata will be filled from the flyer, but we know a bit more
        # about this scan - it's actually 2d:
        plan_args = self.md['plan_args']
        self.md['shape'] = [plan_args['num1'], plan_args['num2']]
        self.md['motors'] = [self._configure_kw['motor'].name, motor2.name]
        self.md['scan_range'] = [self.md['scan_range'][0],
                                 [np.min(steps), np.max(steps)]]

    def _gen(self):
        # over-rides default gen
        yield Msg('hxn_next_scan_id')
        yield Msg('configure', self.flyer, **self._configure_kw)
        self._update_md()

        if len(self.flyer._subscans) != len(self.slow_steps):
            # fun hack: duplicate the sub-scan configuration for all
            # slow-steps in the flyer. this will allow liveimage to work
            # without modification.
            self.flyer._subscans = ([self.flyer._subscans[0]] *
                                    len(self.slow_steps))

        yield Msg('open_run', **self.md)

        if self.slow_flyer is not None:
            yield Msg('kickoff', self.slow_flyer, group='slowflyer-kickoff')
            yield Msg('wait', None, 'slowflyer-kickoff')

        for subscan, pt in enumerate(iter(self.slow_steps)):
            for mtr, pos in pt.items():
                yield Msg('set', mtr, pos, group='step-motors')
            yield Msg('wait', None, 'step-motors')
            yield from flyer_plan(self.flyer, subscan=subscan)

        if self.slow_flyer is not None:
            yield Msg('complete', self.slow_flyer, group='slowflyer-collect')
            yield Msg('wait', None, 'slowflyer-collect')
            yield Msg('collect', self.slow_flyer)

        yield Msg('close_run')
