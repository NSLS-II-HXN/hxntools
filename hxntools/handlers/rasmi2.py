from databroker.assets.handlers import HandlerBase
import h5py
class SISHDF5Handler(HandlerBase):
    HANDLER_NAME = "SIS_HDF51_FLY_STREAM_V1"

    def __init__(self, resource_fn, *, frame_per_point):
        self._frame_per_point = frame_per_point
        if resource_fn.startswith('/data'):
            resource_fn = '/nsls2/data/hxn/legacy' + resource_fn[5:]
        self._handle = h5py.File(resource_fn, "r", libver='latest', swmr=True)

    def __call__(self, *, column, point_number):
        n_first = point_number * self._frame_per_point
        n_last = n_first + self._frame_per_point
        ds = self._handle[column]
        ds.id.refresh()
        return ds[n_first:n_last]

    # def close(self):
    #     self._handle.close()
    #     self._handle = None
    #     super().close()
class BulkMerlinStream(HandlerBase):
    HANDLER_NAME = 'MERLIN_FLY_STREAM_V2'

    def __init__(self, resource_fn, *, frame_per_point):
        self._frame_per_point = frame_per_point
        if resource_fn.startswith('/data'):
            resource_fn = '/nsls2/data/hxn/legacy' + resource_fn[5:]
        self._handle = h5py.File(resource_fn, "r", libver='latest', swmr=True)

    def __call__(self, point_number):
        n_first = point_number * self._frame_per_point
        n_last = n_first + self._frame_per_point
        ds = self._handle['entry/instrument/detector/data']
        ds.id.refresh()
        return ds[n_first:n_last, :, :]

    def dataset(self):
        return self._handle['entry/instrument/detector/data']

class ZebraHDF5Handler(HandlerBase):
    HANDLER_NAME = "ZEBRA_HDF51_FLY_STREAM_V1"

    def __init__(self, resource_fn, *, frame_per_point):
        self._frame_per_point = frame_per_point
        if resource_fn.startswith('/data'):
            resource_fn = '/nsls2/data/hxn/legacy' + resource_fn[5:]
        self._handle = h5py.File(resource_fn, "r", libver='latest', swmr=True)

    def __call__(self, *, column, point_number):
        n_first = point_number * self._frame_per_point
        n_last = n_first + self._frame_per_point
        ds = self._handle[column]
        ds.id.refresh()
        return ds[n_first:n_last]

def register(db):
    db.reg.register_handler(SISHDF5Handler.HANDLER_NAME, SISHDF5Handler, overwrite=True)
    db.reg.register_handler(BulkMerlinStream.HANDLER_NAME, BulkMerlinStream,  overwrite=True)
    db.reg.register_handler(ZebraHDF5Handler.HANDLER_NAME, ZebraHDF5Handler, overwrite=True)

