from databroker.assets.handlers import HandlerBase
import h5py


class BulkMerlin(HandlerBase):
    HANDLER_NAME = 'MERLIN_HDF5_BULK'

    def __init__(self, resource_fn, **kwargs):
        if resource_fn.startswith('/data'):
            resource_fn = '/nsls2/data/hxn/legacy' + resource_fn[5:]
        self._handle = h5py.File(resource_fn, "r", libver='latest', swmr=True)

    def __call__(self, **kwargs):
        ds = self._handle['entry/instrument/detector/data']
        ds.id.refresh()
        return ds[:,:,:]

    def dataset(self):
        return self._handle['entry/instrument/detector/data']

class BulkXSP(HandlerBase):
    HANDLER_NAME = 'XSP3_BULK'

    def __init__(self, resource_fn):
        if resource_fn.startswith('/data'):
            resource_fn = '/nsls2/data/hxn/legacy' + resource_fn[5:]
        self._handle = h5py.File(resource_fn, "r", libver='latest', swmr=True)

    def __call__(self, frame = None, channel = None):
        ds = self._handle['entry/instrument/detector/data']
        ds.id.refresh()
        if channel is None:
            return ds[:,:,:]
        else:
            return ds[:,channel-1,:].squeeze()

class ROIHDF5Handler(HandlerBase):
    HANDLER_NAME = "ROI_HDF5_FLY"

    def __init__(self, resource_fn):
        if resource_fn.startswith('/data'):
            resource_fn = '/nsls2/data/hxn/legacy' + resource_fn[5:]
        self._handle = h5py.File(resource_fn, "r", libver='latest', swmr=True)

    def __call__(self, *, det_elem):
        ds = self._handle[det_elem]
        ds.id.refresh()
        return ds[:]

    def close(self):
        self._handle.close()
        self._handle = None
        super().close()

class PandAHandlerHDF5(HandlerBase):
    """The handler to read HDF5 files produced by PandABox."""
    HANDLER_NAME = "PANDA"

    specs = {"PANDA"}

    def __init__(self, filename):
        if filename.startswith('/data'):
            filename = '/nsls2/data/hxn/legacy' + filename[5:]
        self._name = filename

    def __call__(self, field):
        with h5py.File(self._name, "r") as f:
            entry = f[f"/{field}"]
            return entry[:]



def register(db):
    db.reg.register_handler(BulkMerlin.HANDLER_NAME,
                            BulkMerlin, overwrite=True)
    db.reg.register_handler(BulkXSP.HANDLER_NAME,
                            BulkXSP, overwrite=True)
    db.reg.register_handler(ROIHDF5Handler.HANDLER_NAME,
                            ROIHDF5Handler, overwrite=True)
    db.reg.register_handler(PandAHandlerHDF5.HANDLER_NAME,
                            PandAHandlerHDF5, overwrite=True)
