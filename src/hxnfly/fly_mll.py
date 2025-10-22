import logging
from collections import OrderedDict
from IPython import get_ipython

from .fly1d import Fly1D
from .fly2d import Fly2D

logger = logging.getLogger(__name__)

ip = get_ipython()

try:
    ssx = ip.user_ns['ssx']
    ssy = ip.user_ns['ssy']
    ssz = ip.user_ns['ssz']
except KeyError as ex:
    logger.error('Ensure that fly scan motor "%s" is still in the startup '
                 'configuration with the same name.', ex,
                 exc_info=ex)
    raise

coord_sys = 5
prog_num = 50
axes = OrderedDict([('x', dict(positioner=ssx, axis_number=3)),
                    ('y', dict(positioner=ssy, axis_number=4)),
                    ('z', dict(positioner=ssz, axis_number=5))]
                    )
# change return_speed from 5.0 to 40 (H. Yan, 01/10/17)
# Reverted to 2ms dead time (Merlin requires at least 1.6ms)
configure_defaults = dict(return_speed=40.0,
                          dead_time=0.002,
                          fly_type='soft',
                          max_points=65536
                          )


class Fly1D_MLL(Fly1D):
    def __init__(self, cmd='fly1d', **kwargs):
        super().__init__(axes=axes, coord_sys=coord_sys, prog_num=prog_num,
                         cmd=cmd, configure_defaults=configure_defaults,
                         **kwargs)


class Fly2D_MLL(Fly2D):
    def __init__(self, cmd='fly2d', **kwargs):
        super().__init__(axes=axes, coord_sys=coord_sys, prog_num=prog_num,
                         cmd=cmd, configure_defaults=configure_defaults,
                         **kwargs)
