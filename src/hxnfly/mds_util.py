from __future__ import print_function
import numpy as np


def get_mds_info(positioners=None, detectors=None, data=None,
                 desc=None):
    """Helper function to extract information from the positioners/detectors
    and send it over to metadatastore so that ophyd is insulated from mds
    spec changes

    Parameters
    ----------
    positioners : list, optional
        List of ophyd positioners
    detectors : list
        List of ophyd detectors, optional
    data : dict
        Dictionary of actual data
    """
    if desc is None:
        desc = {}

    [desc.update(x.describe()) for x in (detectors + positioners)]

    info_dict = {}
    for name, value in data.iteritems():
        # grab 'value' from [value, timestamp]
        val = np.asarray(value[0])

        dtype = 'number'
        try:
            shape = val.shape
        except AttributeError:
            # val is probably a float...
            shape = None

        if shape:
            dtype = 'array'

        d = {'dtype': dtype, 'shape': shape}
        d.update(desc[name])
        d = {name: d}
        info_dict.update(d)

    return info_dict
