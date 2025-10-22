import asyncio
import threading
import logging
import logging.handlers
import numpy as np
import os
import time
import tqdm

from datetime import datetime
from itertools import zip_longest
from collections import OrderedDict
import pandas as pd

import IPython

from ophyd import Device
from ophyd.status import Status
from ophyd.device import Staged
from ophyd.areadetector import FilePlugin

from nslsii.detectors.xspress3 import Xspress3Detector
from hxntools.shutter import (shutter_open, shutter_close)

from . import SCRIPT_PATH
from ppmac.pp_comm import (GPError, ScriptCancelled,
                           TimeoutError as PpmacTimeoutError)
from .ppmac_util import (ppmac_connect, filter_ppmac_data as filter_data,
                         gather_setup, is_closed_loop)
from .log import log_time

# from .plot import plot_position

# ip = IPython.get_ipython()
# global_state = ip.user_ns['gs']
# zebra = ip.user_ns['zebra']
# sclr1 = ip.user_ns['sclr1']
# from hxntools import HxnTriggeringScaler
# sclr1 = HxnTriggeringScaler('XF:03IDC-ES{Sclr:1}', name='sclr1')

logger = logging.getLogger(__name__)
UNSTAGE_TIME_LIMIT = 300


class FlyStatus(Status):
    pass


def get_dataframe(df_data, n_points):
    '''Create a dataframe from df_data, adjusting the size of lists if
    necessary

    Note: this should not really be happening (and hasn't recently I believe),
    but we'd rather a point or two to be clipped off than for the whole scan to
    die in case something went a bit wrong.
    '''
    for key in df_data.keys():
        len_ = len(df_data[key])
        if len_ < n_points:
            df_data[key] = np.pad(df_data[key], (0, n_points - len_),
                                  mode='constant')
        elif len_ > n_points:
            df_data[key] = df_data[key][:n_points]

    return pd.DataFrame(df_data)


def get_scaler_info(scaler, channels, *, with_data=False, num_points=None):
    '''Get scaler information, optionally including data

    Parameters
    ----------
    channels : list
        List of channels
    with_data : bool, optional
        Include MCA data
        For channel 1, this will be converted to seconds
    num_points : int, optional
        Number of points to get from the data PV, default (None) will get all
        available
    '''
    for chan in channels:
        key = '{}_ch{}'.format(scaler.name, chan)
        mca = scaler.mca_by_index[chan]

        if with_data:
            data = mca.spectrum.get(count=num_points, as_numpy=True)

        if chan == 1:
            # Channel 1 is special, as we know it counts the alive time of
            # the scaler:
            key = 'scaler_alive'
            if with_data:
                yield key, mca, data.astype(float) / 50e3
            else:
                yield key, mca
        elif with_data:
            yield key, mca, data.astype(int)
        else:
            yield key, mca


def dataframe_to_bluesky_data(df, *, timestamp_key='timestamp'):
    '''Take pandas dataframe -> generator of dictionaries for bluesky collect

    Parameters
    ----------
    df : pd.DataFrame
    '''
    keys = list(df.keys())
    keys.remove(timestamp_key)
    frame_timestamps = list(df[timestamp_key])
    keyed_timestamps = ({k: ts for k in keys}
                        for ts in frame_timestamps)

    v = [df[k] for k in keys]
    data = ({k: val for k, val in zip(keys, row)} for row in
            zip_longest(*v, fillvalue=np.nan))

    return ({'time': ts,
             'timestamps': keyed_ts,
             'data': _data,
             }
            for _data, ts, keyed_ts in zip(data, frame_timestamps,
                                           keyed_timestamps)
            )


class FlyBase(Device):
    '''FlyScan base class

    NOTE: this is only made a Device for bluesky compatibility currently(?)
    '''

    _cancel_script = 'cancel.txt'

    def __init__(self, cmd, ppmac, configure_defaults=None):
        super().__init__('', name=self.__class__.__name__, parent=None)

        self.stream_name = 'primary'
        self._sync_variable = 'Q1'
        self._status_variable = 'Q2'
        self._progress_bar = None
        self._collect_data = []
        self._data_desc = OrderedDict()
        self._cmd = cmd  # scan instance name user sees
        self._metadata = {}
        self._script_running = False
        self._failed = False
        self._start_positions = {}
        # TODO 1D scan is limited by buffer size, but 2D is not
        self._raw_gather_data = bytearray()
        self._debug_data = {}
        self._kickoff_status = None
        self._collect_status = None
        self._scan_index = 1
        self.scan_id = None
        self._total_points = None
        self.scan_command = ''
        self.estimated_time = 0.0

        ipython = IPython.get_ipython()
        self.zebra = ipython.user_ns['zebra']
        self.scaler = ipython.user_ns['sclr1']

        if configure_defaults is None:
            configure_defaults = {}

        self.configure_defaults = configure_defaults

        if ppmac is None:
            ppmac = ppmac_connect()

        self.ppmac = ppmac
        self.gpascii = ppmac.gpascii

    @property
    def scan_count(self):
        return len(self._subscans)

    @property
    def done(self):
        try:
            return self._collect_status.done
        except AttributeError:
            pass

    @property
    def total_points(self):
        return self._total_points

    @property
    def scan_index(self):
        return self._scan_index

    @property
    def failed(self):
        return self._failed

    @property
    def cancelled(self):
        return self._cancelled.is_set()

    def configure(self, *args, **kwargs):
        '''Configure the fly scan

        * Sets up metadata
        * Creates a 'scan command' based on args/kwargs to this function
        * Calls _configure (which is based on the fly-scan type) that populates
          the sub-scan list
        '''
        # assemble the scan_command
        arg_str = [arg.name if hasattr(arg, 'name') else repr(arg)
                   for arg in args]
        kwarg_str = ['{}={!r}'.format(k, v) for k, v in kwargs.items()]

        self.scan_command = '{}({})'.format(self._cmd,
                                            ', '.join(arg_str + kwarg_str))

        self._metadata['scan_command'] = self.scan_command

        # record the starting positions of the motors
        self._start_positions = self.positions

        # configure all of the subscans
        subscans = self._configure(*args, **kwargs)

        if subscans:
            scan_info = subscans[0]
            macros = scan_info['macros']
            self._metadata['script_path'] = scan_info['script_fn']
            self._metadata['fly_type'] = scan_info['fly_type']
            self._metadata['axes'] = macros['axis_names']

        self._collect_desc = self._get_collect_description()
        return kwargs, kwargs

    def kickoff(self, *, subscan=0, name=None):
        '''Bluesky kickoff to start a specific subscan
        '''
        self._kickoff_status = FlyStatus()
        self._collect_status = FlyStatus()
        # self.stream_name = name

        def run_fly():
            self._kickoff_status._finished(success=True)

            try:
                self._collect_data = self.run_subscan(subscan)
            except Exception:
                self._failed = True
                self._collect_status._finished(success=False)
                raise
            finally:
                self._collect_status._finished(success=True)

        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, run_fly)
        return self._kickoff_status

    def _get_collect_description(self):
        self._roi_keys = []
        for xsp in self.detectors_of_type(Xspress3Detector):
            for desc in xsp.describe_collect():
                self._data_desc.update(**desc)
            roi_keys = list(roi.name for roi in xsp.enabled_rois)
            self._roi_keys.extend(roi_keys)

        return {self.stream_name: self._data_desc}

    def describe_collect(self):
        if self._collect_desc is None:
            self._collect_desc = self._get_collect_description()

        return self._collect_desc

    def complete(self):
        '''Return status object for data collection status'''
        return self._collect_status

    def collect(self):
        '''The collected data from run_subscan'''
        yield from self._collect_data

    def pause(self):
        if self._collect_status.done and not self._script_running:
            return

        logger.info('Pause requested')

        if self.cancelled:
            logger.debug('Pause called twice')
            return

        self._cancelled.set()

        if self._script_running:
            logger.warning('Stopping the scan motion program...')
        elif self.failed:
            return
        else:
            logger.info('Scan not running - waiting for data to be '
                        'written')

        try:
            logger.warning('Waiting for motion program to exit safely')
            while not self._collect_status.done:
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.warning('Scan interrupted; data may not have been saved')

    def resume(self):
        if self.cancelled:
            raise RuntimeError('Cannot resume a hard-paused flyscan')

    @property
    def md(self):
        '''scan metadata for runstart header'''
        return self._metadata

    def _setup_axes(self, axes):
        '''
        Parameters
        ----------
        axes : OrderedDict
            {simple_axis_name: {'positioner': ophyd.Positioner,
                                'axis': axis_number}}
        '''
        # axes: name -> number
        self.axes = OrderedDict()

        # axis_to_positioner: name -> positioner
        self.axis_to_positioner = OrderedDict()

        # positioner_to_axis: positioner -> simple axis name for motion script
        self.positioner_to_axis = OrderedDict()
        for axis_name, axis_info in axes.items():
            axis_num = axis_info['axis_number']
            pos = axis_info['positioner']

            self.axes[axis_name] = axis_num
            if not is_closed_loop(self.gpascii, axis_num):
                raise RuntimeError('Axis {} not in closed loop'
                                   ''.format(axis_name))

            self.axis_to_positioner[axis_name] = pos
            self.positioner_to_axis[pos] = axis_name

        self.number_to_axis = OrderedDict((num, axis)
                                          for axis, num in self.axes.items())
        self.axis_keys = [positioner.name
                          for axis_name, positioner in
                          self.axis_to_positioner.items()]

    @property
    def positions(self):
        '''Positions for all axes {axis_simple_name: position}'''
        home_positions = self.home_positions
        return {axis: (self.gpascii.get_variable('Motor[%d].ActPos' % num,
                                                 type_=float) -
                       home_positions[axis])
                for num, axis in self.number_to_axis.items()}

    @property
    def home_positions(self):
        '''Home position for all axes {axis_simple_name: home_position}'''
        return {axis: self.gpascii.get_variable('Motor[%d].HomePos' % num,
                                                type_=float)
                for num, axis in self.number_to_axis.items()}

    @property
    def motor_numbers(self):
        '''motor numbers for the scan: 3, 4, and/or 5'''
        for name in self.simple_motor_names:
            yield self.axes[name]

    @property
    def simple_motor_names(self):
        '''motor names for the scan: x, y, and/or z'''
        for pos in self.scanning_positioners:
            yield self._get_axis_name(pos)

    def _move_all_axes(self, motors_targets, *, wait=True, msg='moved to'):
        '''Move motors to the starting position

        Parameters
        ----------
        motors_targets : list
            (axis_name, target)
        '''
        def _get_motor(motor):
            if motor in self.axes:
                return self.axes[motor]
            return motor

        motors_targets = [(_get_motor(motor), target)
                          for motor, target in motors_targets]

        for motor, target in motors_targets:
            self.gpascii.jog(motor, target, relative=False, wait=False)

        if wait:
            for motor, target in motors_targets:
                try:
                    self.gpascii.jog(motor, target, relative=False, wait=True)
                except PpmacTimeoutError:
                    logger.warning('Failed to move motor %s into position',
                                   motor)
                else:
                    logger.debug('Motor %s %s: %g', motor, msg, target)

    def _get_axis_name(self, motor):
        '''simple axis name of motor, such as "x", 'y", or "z"'''
        if motor in self.axes:
            return motor

        try:
            return self.positioner_to_axis[motor]
        except KeyError:
            raise KeyError('Unknown motor for this type of fly scan')


class FlyScan(FlyBase):

    def __init__(self, ppmac=None, script_path=SCRIPT_PATH, detectors=None,
                 shutter_control=False, coord_sys=5,
                 prog_num=50, axes=None, cmd='fly',
                 trigger_var='m100', scaler_channels=None,
                 configure_defaults=None):

        super().__init__(cmd=cmd, ppmac=ppmac,
                         configure_defaults=configure_defaults)

        self.coord_sys = coord_sys
        self.prog_num = prog_num

        self._setup_axes(axes)

        if detectors is None:
            detectors = []

        self.data = {}
        self.gather_client = self.ppmac.fast_gather
        self._script_path = script_path
        self.detectors = list(detectors)

        if self.zebra not in self.detectors:
            self.detectors.append(self.zebra)

        if self.scaler not in self.detectors:
            self.detectors.append(self.scaler)

        # self._debug = {'target_pos': True}
        self._debug = {}
        self._cancelled = threading.Event()
        self._shutter_control = shutter_control
        self._times = {}
        self._gate_enable = 'high_to_low'
        self._trigger_var = trigger_var
        self._roi_keys = []
        self.detector_status = []

        if scaler_channels is None:
            scaler_channels = [1]

        self._scaler_channels = list(sorted(scaler_channels))
        if 1 not in self._scaler_channels:
            self._scaler_channels.insert(0, 1)

        self._bulk_readable = []
        for det in detectors:
            for attr in det._sub_devices:
                sub_dev = getattr(det, attr)
                if hasattr(sub_dev, 'bulk_read'):
                    self._bulk_readable.append(sub_dev)

        logger.debug('Recording scaler channels: %s', self._scaler_channels)
        logger.debug('Bulk-readable detectors: %s',
                     ', '.join(sub_dev.name for sub_dev in self._bulk_readable)
                     )

    def stop(self):
        logger.info('Flyscan stop requested')
        if self.cancelled:
            logger.debug('Stop called twice')
            return

        if self._collect_status.done and not self._script_running:
            return

        self._cancelled.set()

        if self._script_running:
            logger.warning('Stopping the scan motion program...')
        elif self.failed:
            return
        else:
            logger.info('Scan not running - waiting for data to be '
                        'written')

    def _new_scan(self, dimensions=None, num_points=0, positioners=None,
                  paths=None, exposure_time=None, fly_type='soft',
                  **kwargs):
        self._cancelled.clear()
        self._failed = False
        self.dimensions = dimensions
        self.num_points = int(num_points)
        self.scanning_positioners = positioners
        self.paths = paths
        self.fly_type = fly_type
        self.exposure_time = exposure_time

        self._times['scan_init'] = time.time()

        self._detector_setup()

        self._times['detectors_configured'] = time.time()

        gather_setup(axis_numbers=list(self.axes.values()),
                     period=2,  # TODO can probably increase
                     gpascii=self.gpascii,
                     send_to_controller=True)

        # Ensure the 'capture buffer full' variable isn't set
        self.gpascii.set_variable(self._sync_variable, 0)

        if self._shutter_control:
            logger.debug('Opening shutter')
            shutter_open()

    def detectors_of_type(self, type_):
        '''Get all detectors which are of a specific (class) type'''
        for det in self.detectors:
            if isinstance(det, type_):
                yield det

    def _get_roi_data(self):
        rois = OrderedDict()

        for det in self.detectors_of_type(Xspress3Detector):
            try:
                logger.debug('%s HDF5 file: %s', det.name, det.hdf5_filename)
                rois.update(list(det.fly_collect_rois()))
                # rois is a list of (name, roi_info) pairs
            except Exception as ex:
                logger.error('Xspress3 failed to aggregate ROIs: %s.'
                             'If the HDF5 file was written properly, ROIs '
                             'can be calculated after the fact either '
                             'manually or with another tool such as pyxrf.',
                             ex, exc_info=ex)

        class NoROIData:
            ev_low = 0
            ev_high = 0

        # add missing keys, if necessary
        for key in self._roi_keys:
            if key not in rois:
                logger.error('ROI missing from detector readout: %s.  It will '
                             'be zero in the output, but can be re-calculated '
                             'using pyxrf', key)
                data = NoROIData()
                data.value = []
                rois[key] = data

        # remove unexpected keys, if necessary
        read_keys = set(rois.keys())
        expected_keys = set(self._roi_keys)
        for unexpected_key in read_keys.difference(expected_keys):
            logger.error('Unexpected ROI: %s', unexpected_key)
            del rois[unexpected_key]

        for key, roi in rois.items():
            yield key, roi

    @property
    def scan_id_string(self):
        if self.scan_count > 1:
            return '#{} (sub-scan {} of {})'.format(self.scan_id,
                                                    self.scan_index,
                                                    self.scan_count)
        return '#{}'.format(self.scan_id)

    def _process_data(self):
        self._times['data_aggregated'] = time.time()

        df_data = OrderedDict()

        # roi_info is a list of RoiTuples, with ev info and the data
        roi_info = list(self._get_roi_data())

        # and add the roi data itself
        for key, roi in roi_info:
            if key in df_data:
                logger.warning('Duplicate roi name %s; will not be stored',
                               key)
                continue

            df_data[key] = roi.value

        # tag on all filtered, gathered data
        gather_cols = self._get_gather_data()
        ppmac_data, self._debug_data = filter_data(
            servo_period=self.gpascii.servo_period,
            servo_t=gather_cols[0],
            enable=gather_cols[1],
            motor_cols=gather_cols[2:2 + len(self.axes)],
            other_cols=gather_cols[2 + len(self.axes):],
            axis_names=list(self.axes.keys()),
            axis_keys=self.axis_keys,
            have_target_pos=self._debug.get('target_pos', False),
            gate_enable=self._gate_enable,
            home_pos=self.home_positions,
        )

        # add ev information for all rois
        self._debug_data['rois'] = {key: (roi.ev_low, roi.ev_high)
                                    for key, roi in roi_info}

        df_data.update(ppmac_data)

        self._times['ppmac_run_time'] = self._debug_data['servo_time'][-1]

        scaler_info = get_scaler_info(self.scaler, self._scaler_channels,
                                      with_data=True,
                                      num_points=self.num_points)
        for key, mca, mca_data in scaler_info:
            df_data[key] = mca_data

        # TODO use EVR for all timestamps
        timestamps = (self._times['script_start'] +
                      np.asarray(df_data['elapsed_time']))
        df_data['timestamp'] = timestamps

        logger.debug('Total timestamps: %d', len(timestamps))

        # special-casing xspress3 for now :/
        for det in self.detectors_of_type(Xspress3Detector):
            # TODO: i think it will eventually move in this direction:
            det.flyer_timestamps.put(timestamps)
            df_data.update(det.bulk_read())
            logger.debug('Bulk read %d channels from %s',
                         len(det.channels), det.name)

        for readable in self._bulk_readable:
            df_data.update(readable.bulk_read(timestamps))

        self._times['data_filtered'] = time.time()

        self._record_times()

        try:
            new_df = get_dataframe(df_data, n_points=len(timestamps))
            full_df = pd.concat((self.data[self.scan_id], new_df))
            self.data[self.scan_id] = full_df
            return dataframe_to_bluesky_data(new_df, timestamp_key='timestamp')
        except Exception as ex:
            logger.error('Failed to aggregate into dataframe', exc_info=ex)
            raise

    def _record_times(self):
        if self._subscans:
            self._times['estimated_time'] = (self.estimated_time /
                                             len(self._subscans))
        else:
            self._times['estimated_time'] = self.estimated_time

        # setup time = time from initialization to the script starting
        log_time(logger, self._times, 'setup_time',
                 t1='scan_init', t2='script_start')

        # detector setup time is a portion of the overall setup time
        log_time(logger, self._times, 'detector_setup_time',
                 t1='scan_init', t2='detectors_configured')

        # aggregate_time = time when the script finishes to all data back
        log_time(logger, self._times, 'aggregate_time',
                 t1='script_finished', t2='data_aggregated')

        # filter_time = time to take the aggregated data and filter it
        log_time(logger, self._times, 'filter_time',
                 t1='data_aggregated', t2='data_filtered')

        # record just the ppmac script runtime
        log_time(logger, self._times, 'ppmac_run_time')

        # record the estimated script runtime
        log_time(logger, self._times, 'estimated_time')

    @property
    def table_columns(self):
        return [
            key
            for key, desc in self.describe_collect()[self.stream_name].items()
            if (key not in self._bulk_readable and desc['dtype'] != 'array')
        ]

    def _configure(self):
        for readable in self._bulk_readable:
            # bulk readable detectors have their own image data keys
            det = readable.parent
            self._data_desc[readable.image_name] = det.make_data_key()

        # motion axes and other data filtered from the gather buffer
        other_keys = ['elapsed_time', 'alive', 'dead', ]
        for key in list(self.axis_keys) + other_keys:
            self._data_desc[key] = dict(source='HW:ppmac_gather',
                                        shape=[],
                                        dtype='number')

        # all scaler-related signals
        def get_mca_desc(mca):
            spectrum_name = mca.spectrum.name
            desc = mca.spectrum.describe()
            return desc[spectrum_name]

        alive_desc = get_mca_desc(self.scaler.mca_by_index[1])
        self._data_desc['scaler_alive'] = alive_desc

        scaler_info = get_scaler_info(self.scaler, self._scaler_channels,
                                      with_data=False)
        for key, mca in scaler_info:
            self._data_desc[key] = get_mca_desc(mca)

    def trigger(self, on=False, off=False):
        if self._gate_enable == 'low_to_high':
            off_value, on_value = 0, 1
        elif self._gate_enable == 'high_to_low':
            off_value, on_value = 1, 0

        if on:
            logger.debug('Trigger on')
            self.gpascii.send_line('{}={}'.format(self._trigger_var, on_value))
            self.gpascii.sync()

        if off:
            logger.debug('Trigger off')
            self.gpascii.send_line('{}={}'.format(self._trigger_var,
                                                  off_value))
            self.gpascii.sync()

    def _detector_setup(self):
        self.trigger(off=True)
        logger.debug('Detector setup:')
        del self.detector_status[:]

        for det in self.detectors:
            try:
                settings = det.mode_settings
                settings.mode.put('external')
                settings.scan_type.put('fly')
                settings.total_points.put(self.num_points)
            except Exception:
                print(f"Det {det.name} mode_settings failed to set, check the detector object.")
                pass

            logger.debug('Staging %s (settings: %s)', det.name,
                         settings.get())

            if det._staged == Staged.yes:
                logger.debug('Detector %s already staged - restaging',
                             det.name)
                det.unstage()

            det.stage()
            self.detector_status.append(det.trigger())

        for readable in self._bulk_readable:
            det = readable.parent
            # TODO: ensure image key is in the datum uids, because the detector
            # is being used outside of the normal bluesky methods...
            readable._datum_uids[readable.image_name] = []

    def _get_gather_data(self):
        n_samples, raw_data = self.gather_client.query_raw_data()
        self._raw_gather_data += raw_data

        t0 = time.time()
        dtypes = self.gather_client.query_types()
        parsed = self.gather_client._parse_raw_data(dtypes,
                                                    self._raw_gather_data)
        t1 = time.time()

        # TODO in the future, this can be done in parallel in a queue
        logger.debug('[sync mode] Raw data parsing took %f ms',
                     (1000. * (t1 - t0)))
        gathered, n_addr, n_samples = parsed
        cols = np.asarray(gathered)
        return np.asarray(cols)

    def unstage(self):
        for det in self.detectors:
            sub_devs = [getattr(det, sub_dev) for sub_dev in det._sub_devices]
            for sub_dev in sub_devs:
                if isinstance(sub_dev, FilePlugin):
                    t0 = time.time()
                    i = 0
                    while sub_dev.capture.get() != 0:
                        elapsed = time.time() - t0
                        if elapsed > UNSTAGE_TIME_LIMIT:
                            logger.error('%s unstage time limit reached. '
                                         'Stopping file plugin capture.',
                                         sub_dev.name,
                                         )
                            sub_dev.capture.put(0)
                            break
                        elif (i % 20) == 0:
                            logger.info('%s still acquiring: %d frames '
                                        '(%.1f sec until considered failure)',
                                        sub_dev.name,
                                        sub_dev.num_captured.get(),
                                        UNSTAGE_TIME_LIMIT - elapsed)
                        i += 1
                        time.sleep(0.1)
                    logger.info('%s acquired %d frames', sub_dev.name,
                                sub_dev.num_captured.get())

            logger.debug('Unstaging %s', det.name)
            det.unstage()

        for st in self.detector_status:
            logger.debug('Unstage detector status: %s', st)

    def _status_variable_updated(self, old, new):
        if self._progress_bar is None:
            return

        # status update
        try:
            new = int(new)
            old = int(old)
        except TypeError:
            return

        if new > old:
            try:
                self._progress_bar.update((new - old))
            except Exception:
                pass

    def _buffer_status_updated(self, old, new):
        # otherwise, Q1 for buffer status
        new = int(new)
        logger.debug('[sync status] %s=%d', self._sync_variable, new)
        if new == 1:
            logger.debug('[sync mode] sample count reached')
            t0 = time.time()

            _, raw_data = self.gather_client.query_raw_data()
            samples = self.gpascii.get_variable('Gather.Samples', type_=int)
            self.gpascii.set_variable(self._sync_variable, 0)

            t1 = time.time()
            logger.debug('[sync mode] line time %f ms (%d bytes, %d samples)',
                         (t1 - t0) * 1000., len(raw_data), samples)

            self._raw_gather_data += raw_data

    def _sync_callback(self, var, old, new):
        if var == self._status_variable:
            return self._status_variable_updated(old, new)
        elif var == self._sync_variable:
            return self._buffer_status_updated(old, new)

    def _run_and_wait(self, *args, num_points=None, **kwargs):
        '''Run the motion script for the already-configured subscan'''
        ipython = IPython.get_ipython()

        self.scan_id = ipython.user_ns['RE'].md['scan_id']
        if self.scan_id not in self.data:
            self.data[self.scan_id] = None

        logger.info("Scan ID: %s", self.scan_id_string)

        if self.cancelled:
            logger.debug('Scan was cancelled before it was started')
            return

        if num_points:
            self._progress_bar = tqdm.tqdm(total=num_points, unit='points')

        self._times['script_start'] = time.time()
        try:
            self._script_running = True
            ret = self.gpascii.run_and_wait(self.coord_sys, self.prog_num,
                                            verbose=False, stop_on_cancel=True,
                                            cancel_signal=self._cancelled,
                                            **kwargs)
            if ret != 0:
                logger.error('Script failed; ret code=%s', ret)
                self._failed = True
                return
        except ScriptCancelled as ex:
            logger.warning('Script cancelled (%s)', ex)
        except GPError as ex:
            logger.error('Script run error: (%s) %s', ex.__class__.__name__,
                         ex, )
            if 'READY TO RUN' in str(ex):
                logger.warning('Are all motors in the coordinate system in '
                               'closed loop?')
            raise
        finally:
            self._script_running = False

            if self.cancelled or self.failed:
                logger.debug('Running post-scan cancel script')
                cancel_script = os.path.join(self._script_path,
                                             self._cancel_script)
                try:
                    self.gpascii.run_simple_script(cancel_script)
                except Exception as ex:
                    logger.error('Failed to run cancel script %s',
                                 cancel_script, exc_info=ex)

            logger.debug('Script finished')
            self._times['script_finished'] = time.time()

            if self._shutter_control:
                if self.scan_count == self.scan_index:
                    logger.debug('Closing shutter')
                    shutter_close()

            if self.failed:
                pass
            elif self.cancelled:
                for det in self.detectors:
                    try:
                        det.stop()
                    except AttributeError:
                        pass

                logger.info('Scan %s partially complete. Processing data...',
                            self.scan_id_string)
            else:
                logger.info('Scan %s completed. Processing data...',
                            self.scan_id_string)

            data = None
            if not self.failed:
                data = self._process_data()

            logger.debug('Unstaging scan')
            try:
                self.unstage()
            except Exception as ex:
                logger.error('Unstaging failed', exc_info=ex)

        return data

    def run_subscan(self, index, **kwargs):
        '''Run a specific subscan'''
        # NOTE it's too late to update metadata here
        try:
            scan_info = self._subscans[index]
            self._scan_index = index + 1
            self._raw_gather_data = bytearray()

            macros = scan_info['macros']
            num_points = np.product(macros['points'])

            # move the axes to the start, while sending the motion program in
            # parallel
            self._move_all_axes(zip(macros['axis_names'],
                                    macros['scan_starts']),
                                wait=False)

            try:
                self._new_scan(**scan_info)
                # TODO make scripts part of the ppmac configuration and then
                #      only modify M/P/Q variables for parameters
                self.gpascii.send_program(self.coord_sys, self.prog_num,
                                          filename=scan_info['script_fn'],
                                          verbose=False, macros=macros,
                                          motors=self.number_to_axis)

                self._move_all_axes(zip(macros['axis_names'],
                                        macros['scan_starts']),
                                    wait=True,
                                    msg='moved to starting position')

                # Run the motion program
                return self._run_and_wait(variables=[self._sync_variable,
                                                     self._status_variable],
                                          change_callback=self._sync_callback,
                                          num_points=num_points,
                                          **kwargs)
            except Exception as ex:
                logger.error('Scan #%d of grid failed', self.scan_index,
                             exc_info=ex)
                raise
        finally:
            if self._progress_bar is not None:
                self._progress_bar.close()
                self._progress_bar = None

            last_scan = ((index + 1) == len(self._subscans))
            if self.cancelled or last_scan:
                self._move_all_axes(self._start_positions.items(),
                                    msg='moved back to',
                                    wait=False)
