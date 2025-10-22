import logging
from collections import OrderedDict
from IPython import get_ipython

from .fly1d import Fly1D
from .fly2d import Fly2D

logger = logging.getLogger(__name__)

ip = get_ipython()

try:
    zpssx = ip.user_ns['zpssx']
    zpssy = ip.user_ns['zpssy']
    zpssz = ip.user_ns['zpssz']
except KeyError as ex:
    logger.error('Ensure that fly scan motor "%s" is still in the startup '
                 'configuration with the same name.', ex,
                 exc_info=ex)
    raise

coord_sys = 6
prog_num = 50
axes = OrderedDict([('x', dict(positioner=zpssx, axis_number=6)),
                    ('y', dict(positioner=zpssy, axis_number=7)),
                    ('z', dict(positioner=zpssz, axis_number=8))]
                    )
# change return_speed from 25.0 to 40.0; change dead_time from 0.002 to 0.005. (H. Yan, 01/10/2017)
configure_defaults = dict(return_speed=40.0,
                          dead_time=0.002,
                          fly_type='soft',
                          max_points=65536,
                          )


class Fly1D_ZP(Fly1D):
    def __init__(self, cmd='fly1d', **kwargs):
        super().__init__(axes=axes, coord_sys=coord_sys, prog_num=prog_num,
                         cmd=cmd, configure_defaults=configure_defaults,
                         **kwargs)


class Fly2D_ZP(Fly2D):
    def __init__(self, cmd='fly2d', **kwargs):
        super().__init__(axes=axes, coord_sys=coord_sys, prog_num=prog_num,
                         cmd=cmd, configure_defaults=configure_defaults,
                         **kwargs)
