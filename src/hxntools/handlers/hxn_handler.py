from databroker.assets.handlers import HandlerBase
import h5py

class HXNHandlerBase(HandlerBase):

    def __init__(self, resource_fn, **kwargs):
        if resource_fn.startswith('/data'):
            resource_fn = '/nsls2/data/hxn/legacy' + resource_fn[5:]
        self._handle = h5py.File(resource_fn, "r", libver='latest', swmr=True, locking=False)

    @property
    def filename(self):
        return self._handle.filename

