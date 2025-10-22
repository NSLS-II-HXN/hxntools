import asyncio
import logging
import IPython
from collections import OrderedDict

from .liveplot import FlyLivePlot

loop = asyncio.get_event_loop()
logger = logging.getLogger(__name__)


def get_default_xspress3():
    ip = IPython.get_ipython()
    return ip.user_ns['xspress3']


def signals_from_roi_name(roi_name, *, use_sum=False,
                          channels=None, xspress3=None,
                          channel_delimiter='_'):
    '''Get all ROI signals that match roi_name

    Parameters
    ----------
    roi_name : str
        Name of ROI
    use_sum : bool, optional
        Use the ROI value or the running sum
    channels : list, optional
        List of allowable channels to match
    xspress3 : Xspress3Detector, optional
        The detector instance. If unspecified, this is retrieved through the
        IPython user namespace variable 'xspress3'
    channel_delimiter : str, optional
        Rois are named in the form so as not to clash with other keys:
            Detector<-DELIMITER->ROI_NAME
        This function will match either Det1_ROI_NAME or ROI_NAME.
    '''

    if xspress3 is None:
        xspress3 = get_default_xspress3()

    signals = {}
    for roi in xspress3.enabled_rois:
        if channel_delimiter is not None and channel_delimiter in roi.name:
            name = roi.name.split(channel_delimiter, 1)[1]
        else:
            name = roi.name

        if name == roi_name or roi.name == roi_name:
            if channels is not None and roi.channel_num not in channels:
                continue

            if use_sum:
                # TODO
                # old version is ARRSUM1:ArrayData
                pass

            signals[roi.channel_num] = roi.settings.array_data
            # TODO: these data keys need to be the same...
            # TODO: if this is ever used in acquisition, it could be a problem
            signals[roi.channel_num].name = roi.name

    return [sig for chan, sig in
            sorted(signals.items(), key=lambda chan_sig: chan_sig[0])]


class FlyRoiPlot(FlyLivePlot):
    def __init__(self, roi_names, *, channels=None, use_sum=False,
                 group_rois=True, xspress3=None, **kwargs):

        if xspress3 is None:
            xspress3 = get_default_xspress3()

        if channels is None:
            channels = [1, 2, 3]

        self._channels = channels
        self._use_sum = use_sum
        self._group_rois = group_rois

        if isinstance(roi_names, str):
            roi_names = [roi_names]

        signals = OrderedDict()
        if group_rois:
            # group all channels together
            for roi_name in roi_names:
                signals[roi_name] = list(signals_from_roi_name(
                    roi_name, use_sum=use_sum, channels=channels))
        else:
            # keep all rois separate, use their full name
            for roi_name in roi_names:
                for sig in signals_from_roi_name(roi_name, use_sum=use_sum,
                                                 channels=channels):
                    signals[sig.name] = [sig]

        super().__init__(signals, point_signal=xspress3.settings.array_counter,
                         **kwargs)
