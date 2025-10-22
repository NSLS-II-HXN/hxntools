import os
import time
import logging
import numpy as np

from .fly import FlyScan


logger = logging.getLogger(__name__)


class Fly2D(FlyScan):
    '''2D fly scan

    Scan types:
    * soft: uses trajectory generation and triggering via motion scripts
    * pyramid: same method as soft, but acquires in both forward and reverse
               directions
    * fly: normal 'fly-scan' concept, using position compare
    '''
    scripts = {'soft': 'soft_2d.txt',
               # 'fly': 'fly2d.txt',
               'pyramid': 'soft_2d_pyramid.txt',
               }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._subscans = []

    def subscan_config(self, motor1, scan_start1, scan_end1, num1,
                       motor2, scan_start2, scan_end2, num2, *,
                       exposure_time=None, dead_time=0.010, speed=None,
                       fly_type='soft', return_speed=10.0):
        """
        2D closed-loop fly-scan of ss(x,y,z), where motor1 is the fast motor
        """
        assert(motor1 in self.axes)
        assert(motor2 in self.axes)

        if num1 < 1 or num2 < 0:
            raise ValueError('Number of points should be >= 1')
        elif exposure_time < 0 or dead_time < 0:
            raise ValueError('Dwell time and dead time must be positive')

        axis_names = [motor1, motor2]
        points = np.array([num1, num2])

        scan_starts = np.array([scan_start1, scan_start2])
        scan_ends = np.array([scan_end1, scan_end2])
        final_pos = np.array(scan_ends)

        distance = np.abs(scan_ends - scan_starts)

        if exposure_time is not None:
            speeds = distance / (exposure_time * points)

        scan_starts = np.min([scan_starts, scan_ends], axis=0)
        scan_ends = np.max([scan_starts, scan_ends], axis=0)

        per_points = distance / points
        self.line_time = distance[0] / speeds[0]

        gpascii = self.gpascii
        sync_samples = gpascii.get_variable('Gather.MaxLines', type_=int)

        macros = {'axis_names': axis_names,
                  'coord_sys': self.coord_sys,
                  'dead_time': dead_time * 1000.0,  # expects milliseconds
                  'exposure_time': exposure_time,
                  'feed_rates': speeds,
                  'final_pos': final_pos,
                  'line_time': self.line_time * 1000.0,
                  'per_points': per_points,
                  'points': points,
                  'return_speed': return_speed,
                  'scan_ends': scan_ends,
                  'scan_starts': scan_starts,
                  'sync_samples': int(sync_samples / 2),
                  }

        script_fn = os.path.join(self._script_path, self.scripts[fly_type])
        return dict(dimensions=points.tolist(),
                    num_points=points[0] * points[1],
                    positioners=[self.axis_to_positioner[m]
                                 for m in (motor1, motor2)],
                    paths=[(scan_starts[i], scan_ends[i]) for i in (0, 1)],
                    exposure_time=exposure_time,
                    fly_type=fly_type,
                    script_fn=script_fn,
                    macros=macros,
                    )

    def _configure(self, motor1, scan_start1, scan_end1, num1,
                   motor2, scan_start2, scan_end2, num2, *,
                   dead_time=0.007, relative=True, exposure_time=0.1,
                   max_points=None, fly_type='soft', return_speed=10.0):

        super()._configure()

        name1 = self._get_axis_name(motor1)
        name2 = self._get_axis_name(motor2)
        scan_start1, scan_end1 = float(scan_start1), float(scan_end1)
        scan_start2, scan_end2 = float(scan_start2), float(scan_end2)
        num1, num2 = int(num1), int(num2)
        exposure_time = float(exposure_time)
        dead_time = float(dead_time)

        if relative:
            start_pos = [self._start_positions[m]
                         for m in (name1, name2)]
        else:
            start_pos = [0.0, 0.0]

        points = _get_scan_points(scan_start1, scan_end1, num1,
                                  scan_start2, scan_end2, num2,
                                  max_points=max_points,
                                  start_x=start_pos[0],
                                  start_y=start_pos[1])
        points = list(points)

        self._subscans = [self.subscan_config(name1, _x1, _x2, nx,
                                              name2, _y1, _y2, ny,
                                              dead_time=dead_time,
                                              exposure_time=exposure_time,
                                              speed=None, fly_type=fly_type,
                                              return_speed=return_speed)
                          for i, (_x1, _x2, nx, _y1, _y2, ny)
                          in enumerate(points)]

        self._metadata['subscan_dims'] = [info['dimensions']
                                          for info in self._subscans]

        self.estimated_time = 0.0
        dim2 = int(np.sum([_ny for _nx, _ny in
                           self._metadata['subscan_dims']]))

        self._metadata['shape'] = [num1, dim2]
        self._total_points = num1 * dim2

        self._metadata['scan_count'] = self.scan_count
        self._metadata['scan_range'] = [(start_pos[0] + scan_start1,
                                         start_pos[0] + scan_end1),
                                        (start_pos[1] + scan_start2,
                                         start_pos[1] + scan_end2)]

        if self._subscans:
            line_time = self._subscans[0]['macros']['line_time']
            self.estimated_time = line_time / 1000.0 * num2

            for key in ('scan_starts', 'scan_ends', 'final_pos', 'per_points',
                        'points'):
                values = np.asarray([subscan['macros'][key] for subscan in
                                     self._subscans])
                self._metadata['{}'.format(key)] = values.tolist()

        return self._subscans


def _get_scan_points(x1, x2, total_pointsx,
                     y1, y2, total_pointsy, *,
                     max_points=None,
                     start_x=0., start_y=0.):
    '''
    Generates rectangular strips for a given scan range

    Maximum points, by default, is set to 16,384 for the xspress3
    '''
    # TODO: not so much limited by the number of points anymore
    #       - up to 16k frames for the xspress3
    #       however, need to break it up based on the travel range
    #       of the fine/coarse piezos
    if max_points is None:
        max_points = 65536

    assert x2 > x1
    assert y2 > y1

    dy = abs(y2 - y1) / total_pointsy

    single_scan_num_lines = max_points // total_pointsx
    if single_scan_num_lines <= 1:
        raise ValueError("One scan line won't fit with maximum points")

    # ensure the number of lines is even to ease data analysis with snaked/
    # pyramid scans
    if (single_scan_num_lines % 2) == 1:
        single_scan_num_lines -= 1

    pyi = 0

    xi = start_x + x1
    xj = start_x + x2

    while pyi < total_pointsy:
        remain = total_pointsy - pyi
        if remain < single_scan_num_lines:
            pointsy = remain
        else:
            pointsy = single_scan_num_lines

        yi = start_y + y1 + pyi * dy
        yj = yi + pointsy * dy

        yield xi, xj, total_pointsx, yi, yj, pointsy

        pyi += pointsy
