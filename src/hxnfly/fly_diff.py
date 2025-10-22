import logging
from collections import OrderedDict
from IPython import get_ipython

from .fly1d import Fly1D
from .fly2d import Fly2D

logger = logging.getLogger(__name__)

ip = get_ipython()

try:
    dssx = ip.user_ns['dssx']
    dssy = ip.user_ns['dssy']
    dssz = ip.user_ns['dssz']
except KeyError as ex:
    logger.error('Ensure that fly scan motor "%s" is still in the startup '
                 'configuration with the same name.', ex,
                 exc_info=ex)
    raise

coord_sys = 7
prog_num = 50
# swap x and z axes: interchange axis_numbers of x and z (H. Yan, 01/10/17)
# physically swapped cable for dssx and dssz; change the seeting to their original state (H. Yan, 08/08/2019)
axes = OrderedDict([('x', dict(positioner=dssx, axis_number=9)),
                    ('y', dict(positioner=dssy, axis_number=10)),
                    ('z', dict(positioner=dssz, axis_number=11))]
                    )
# change return_speed from 5.0 to 40 (H. Yan, 01/10/17)
configure_defaults = dict(return_speed=40.0,
                          dead_time=0.002,
                          fly_type='soft',
                          max_points=65536
                          )


class Fly1D_Diffraction(Fly1D):
    def __init__(self, cmd='fly1d', **kwargs):
        super().__init__(axes=axes, coord_sys=coord_sys, prog_num=prog_num,
                         cmd=cmd, configure_defaults=configure_defaults,
                         **kwargs)


class Fly2D_Diffraction(Fly2D):
    def __init__(self, cmd='fly2d', **kwargs):
        super().__init__(axes=axes, coord_sys=coord_sys, prog_num=prog_num,
                         cmd=cmd, configure_defaults=configure_defaults,
                         **kwargs)
