import os
import logging

MODULE_PATH = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PATH = os.path.join(MODULE_PATH, 'scripts')

logger = logging.getLogger(__name__)

from .log import log_setup

log_setup(logging.DEBUG)

try:
    from hxntools._version import version as __version__
except ImportError:
    __version__ = "unknown"

# from .fly1d import Fly1D
# from .fly2d import Fly2D
#
# from .fly_mll import (Fly1D_MLL, Fly2D_MLL)
# from .fly_zp import (Fly1D_ZP, Fly2D_ZP)
