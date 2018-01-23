from databroker.assets.handlers import HandlerBase, ImageStack


class HDF5DatasetSliceHandler(HandlerBase):
    """
    Handler for data stored in one Dataset of an HDF5 file.
    Parameters
    ----------
    filename : string
        path to HDF5 file
    key : string
        key of the single HDF5 Dataset used by this Handler
    frame_per_point : integer, optional
        number of frames to return as one datum, default 1
    swmr : bool, optional
        Open the hdf5 file in SWMR read mode. Only used when mode = 'r'.
        Default is False.
    """
    def __init__(self, filename, key, frame_per_point=1):
        self._fpp = frame_per_point
        self._filename = filename
        self._key = key
        self._file = None
        self._dataset = None
        self._data_objects = {}
        self.open()

    def get_file_list(self, datum_kwarg_gen):
        return [self._filename]

    def __call__(self, point_number):
        # Don't read out the dataset until it is requested for the first time.
        if not self._dataset:
            self._dataset = self._file[self._key]

        if point_number not in self._data_objects:
            start = point_number * self._fpp
            stop = (point_number + 1) * self._fpp
            self._data_objects[point_number] = ImageStack(self._dataset,
                                                          start, stop)
        return self._data_objects[point_number]

    def open(self):
        import h5py
        if self._file:
            return

        self._file = h5py.File(self._filename, 'r')

    def close(self):
        super(HDF5DatasetSliceHandler, self).close()
        self._file.close()
        self._file = None


class TimepixHDF5Handler(HDF5DatasetSliceHandler):
    """
    Handler for the 'AD_HDF5' spec used by Area Detectors.
    In this spec, the key (i.e., HDF5 dataset path) is always
    '/entry/detector/data'.
    Parameters
    ----------
    filename : string
        path to HDF5 file
    frame_per_point : integer, optional
        number of frames to return as one datum, default 1
    """
    _handler_name = 'TPX_HDF5'
    specs = {_handler_name}

    # TODO this is only different due to the hardcoded key being different?
    hardcoded_key = '/entry/instrument/detector/data'

    def __init__(self, filename, frame_per_point=1):
        super(TimepixHDF5Handler, self).__init__(
                filename=filename, key=self.hardcoded_key,
                frame_per_point=frame_per_point)


def register(db):
    db.reg.register_handler(TimepixHDF5Handler._handler_name,
                            TimepixHDF5Handler, overwrite=True)
