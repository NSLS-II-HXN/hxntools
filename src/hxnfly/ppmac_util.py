from __future__ import print_function
import logging

import os
import numpy as np
import IPython
from ppmac.pp_comm import PPComm


logger = logging.getLogger(__name__)


def ppmac_connect(force=False):
    """
    Store the ppmac connection in the user namespace.
    Set environment variable ``PPMAC_HOST`` to valid host name or IP address.
    """
    ip = IPython.get_ipython()
    ppmac = None
    if force or '_ppmac' not in ip.user_ns:
        logger.debug('Connecting to the Power PMAC...')
        try:
            host = os.environ.get('PPMAC_HOST', None)
            if not host:
                raise ValueError("Host name is not set: environment variable 'PPMAC_HOST' is not set")

            ppmac = ip.user_ns['_ppmac'] = PPComm(host=host,
                                                  fast_gather=True)
        except Exception as ex:
            logger.error('Failed to connect to Power PMAC: %s', ex,
                         exc_info=ex)
        except KeyboardInterrupt:
            logger.error('Failed to connect to Power PMAC'
                         '(interrupted by user)')
        else:
            logger.debug('Connected')
    else:
        logger.debug('Already connected to the ppmac')
        ppmac = ip.user_ns['_ppmac']

    ip.user_ns['_ppmac'] = ppmac
    return ppmac


def filter_ppmac_data(servo_period, servo_t, enable, motor_cols, other_cols,
                      axis_names, axis_keys, have_target_pos, gate_enable,
                      home_pos):
    '''Filter gathered power pmac data, returning two sets of data:
    scan_data, debug_data

    Where scan_data contains normal columns you expect to see in a table (such
    as timestamp, [average] motor position in one frame, detector alive time,
    detector dead time - according to ppmac servo clock)

    And debug_data has high-frequency servo data, target position information,
    and other stuff that may be useful for debugging/plotting (see plot.py)
    '''
    # -- time --
    servo_t *= servo_period
    servo_t -= servo_t[0]

    # -- enable signal --
    enable = enable.astype(int)

    diff = np.diff(enable)

    if gate_enable == 'low_to_high':
        start_i, = np.where(diff == 1)
        end_i, = np.where(diff == -1)
    elif gate_enable == 'high_to_low':
        start_i, = np.where(diff == -1)
        end_i, = np.where(diff == 1)

    slices = [slice(start, end) for start, end in zip(start_i, end_i)]
    mid_t = [np.average(servo_t[slice_]) for slice_ in slices]

    start_t = servo_t[start_i]
    end_t = servo_t[end_i]

    alive_t = [en - st for st, en in zip(start_t, end_t)]
    dead_t = [st - en for st, en in zip(start_t[1:], end_t[:-1])]
    dead_t.append(servo_t[-1] - end_t[-1])

    # -- motor positions --
    axis_names = list(sorted(axis_names))
    gathered_pos = [(motor_cols[i] - home_pos[axis_name])
                    for i, axis_name in enumerate(axis_names)
                    ]

    if have_target_pos:
        target_pos = {axis_key: (other_cols[i] - home_pos[axis_name])
                      for i, (axis_key, axis_name) in
                      enumerate(zip(axis_keys, axis_names))
                      }

    average_pos = [[np.average(pos[slice_]) for slice_ in slices]
                   for pos in gathered_pos]

    # -- return it all in a dictionary --
    logger.debug('total scaler alive time: %.1f', np.sum(alive_t))
    logger.debug('total scaler dead time: %.1fs', np.sum(dead_t))
    logger.debug('scaler alive+dead sum: %.1fs', np.sum(alive_t) +
                 np.sum(dead_t))

    data = dict(elapsed_time=mid_t,
                alive=alive_t,
                dead=dead_t,
                )

    debug_data = dict(start_time=start_t,
                      end_time=end_t,
                      servo_time=servo_t,
                      servo_enable=enable,
                      )

    items = (axis_keys, gathered_pos, average_pos)
    for key, gathered, average in zip(*items):
        data[key] = average

        debug_data['servo_{}'.format(key)] = gathered
        if have_target_pos:
            debug_data['target_{}'.format(key)] = target_pos[key]

    return data, debug_data


def gather_setup(axis_numbers, *, period=2, additional_addresses=None,
                 include_target_positions=False, gpascii=None,
                 send_to_controller=False):
    if additional_addresses is None:
        additional_addresses = []

    start_lines = ['gather.enable=0']

    addresses = ['Sys.ServoCount.a',
                 'Sys.M[100].a',
                 ]

    for axis_num in axis_numbers:
        addresses.append('Motor[{}].Pos.a'.format(axis_num))

    if include_target_positions:
        for axis_num in axis_numbers:
            addresses.append('Motor[{}].Desired.Pos.a'.format(axis_num))

    addresses.extend(additional_addresses)

    addr_lines = ['gather.addr[{}]={}'.format(i, addr)
                  for i, addr in enumerate(addresses)]

    end_lines = ['gather.items={}'.format(len(addresses)),
                 'gather.period={}'.format(period),
                 'gather.enable=1',
                 'gather.enable=0',
                 'gather.MaxSamples=Gather.MaxLines',
                 ]

    logger.debug('Sending gather configuration ({} addresses):'
                 ''.format(len(addresses)))

    config = start_lines + addr_lines + end_lines
    if send_to_controller:
        if gpascii is None:
            raise ValueError('gpascii must be specified to send to controller')

        for line in config:
            logger.debug('> ' + line)
            gpascii.send_line(line)

        gpascii.sync()

    return config


def is_closed_loop(gpascii, axis):
    var = 'Motor[{}].ClosedLoop'
    return gpascii.get_variable(var.format(axis), type_=int)
