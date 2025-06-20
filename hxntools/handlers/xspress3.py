from __future__ import print_function

import logging

# imort XRF_DATA_KEY for back-compat
from databroker.assets.handlers import (Xspress3HDF5Handler,
                                        XS3_XRF_DATA_KEY as XRF_DATA_KEY)


logger = logging.getLogger(__name__)

FMT_ROI_KEY = 'entry/instrument/detector/NDAttributes/CHAN{}ROI{}'

class XSP3HDF5Handler(Xspress3HDF5Handler):
    def __init__(self,filename,key=XRF_DATA_KEY):
        if filename.startswith('/data'):
            filename = '/nsls2/data/hxn/legacy' + filename[5:]
        super().__init__(filename,key)

def register(db):
    #db.reg.register_handler(Xspress3HDF5Handler.HANDLER_NAME,
    #                        Xspress3HDF5Handler)
    db.reg.register_handler(XSP3HDF5Handler.HANDLER_NAME,
                            XSP3HDF5Handler, overwrite=True)
