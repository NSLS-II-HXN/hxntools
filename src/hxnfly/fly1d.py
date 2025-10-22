import os
import logging

from .fly import FlyScan


logger = logging.getLogger(__name__)


class Fly1D(FlyScan):
    '''1D fly scan

    Scan types:
    * soft: uses trajectory generation and triggering via motion scripts
    * fly: normal 'fly-scan' concept, using position compare
    '''
    scripts = {'soft': 'soft_1d.txt',
               'fly': 'fly1d.txt',
               }

    def subscan_config(self, motor, scan_start, scan_end, scan_points,
                       exposure_time=None, *, dead_time=0.010, speed=None,
                       fly_type='soft', relative=True, return_speed=0.4):

        axis = self._get_axis_name(motor)
        scan_start, scan_end = float(scan_start), float(scan_end)
        exposure_time = float(exposure_time)
        dead_time = float(dead_time)
        scan_points = int(scan_points)

        assert(axis in self.axes)

        if scan_points <= 1:
            raise ValueError('Number of points should be > 1')
        elif exposure_time < 0 or dead_time < 0:
            raise ValueError('Dwell time and dead time must be positive')

        if relative:
            all_pos = self.positions
            abs_pos = all_pos[axis]
            final_pos = abs_pos

            scan_start = abs_pos + scan_start
            scan_end = abs_pos + scan_end
        else:
            final_pos = scan_end

        distance = abs(scan_end - scan_start)

        if exposure_time is not None:
            speed = distance / (exposure_time * scan_points)

        per_point = distance / scan_points
        scan_start = min(scan_start, scan_end)
        scan_end = max(scan_start, scan_end)
        self.line_time = distance / speed

        macros = {'axis_name': axis,
                  'axis_names': [axis],
                  'coord_sys': self.coord_sys,
                  'dead_time': dead_time * 1000.0,  # expects milliseconds
                  'exposure_time': exposure_time,
                  'feed_rate': speed,
                  'final_pos': final_pos,
                  'line_time': self.line_time * 1000.0,
                  'per_point': per_point,
                  'points': scan_points,
                  'return_speed': return_speed,
                  'scan_start': scan_start,
                  'scan_starts': [scan_start],
                  }

        self._metadata['macros'] = {}
        for macro, value in sorted(macros.items()):
            logger.debug('Macro %s: %s', macro, value)
            self._metadata['macros'][macro] = value

        self._metadata['shape'] = [scan_points]
        self._metadata['scan_range'] = [[scan_start, scan_end]]
        self._total_points = scan_points
        self.estimated_time = self.line_time

        return dict(num_points=scan_points,
                    dimensions=[scan_points],
                    positioners=[self.axis_to_positioner[axis]],
                    paths=[(scan_start, scan_end)],
                    exposure_time=exposure_time,
                    fly_type=fly_type,
                    macros=macros,
                    script_fn=os.path.join(self._script_path,
                                           self.scripts[fly_type]),
                    )

    def _configure(self, motor, scan_start, scan_end, num,
                   exposure_time=None, *, dead_time=0.010, speed=None,
                   fly_type='soft', relative=True, return_speed=0.4):
        """
        1D closed-loop fly-scan of ss(x,y,z)
        """
        super()._configure()
        conf = self.subscan_config(motor, scan_start, scan_end, num,
                                   exposure_time=exposure_time,
                                   dead_time=dead_time,
                                   speed=speed,
                                   fly_type=fly_type,
                                   relative=relative,
                                   return_speed=return_speed)

        self._subscans = [conf]
        return self._subscans
