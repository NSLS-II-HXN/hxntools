import numpy as np

from .liveimage import FlyLiveImage
from .flydata import catch_exceptions

# from xray_vision.backend.mpl.cross_section_2d import CrossSection2DView
from xray_vision.qt_widgets import CrossSectionMainWindow
from matplotlib.backends.backend_qt5 import _create_qApp


def _new_window(title):
    fake_data = np.zeros((5, 5))
    return CrossSectionMainWindow(data_list=[fake_data], key_list=['fake'],
                                  title=title)


class FlyLiveCrossSection(FlyLiveImage):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        _create_qApp()
        if len(self.signals) != 1:
            raise ValueError('Cross section view only supports a single '
                             'ROI')

        self.label = list(self.signals.keys())[0]
        self.live_window = _new_window('Live update - {}'.format(self.label))
        self._final_window = None

    @property
    def final_window(self):
        if self._final_window is None:
            title = 'Scan {}: {}'.format(self.scan_id, self.label)
            self._final_window = _new_window(title)

        return self._final_window

    @catch_exceptions
    def plot(self, fig, data, *, final=False, **kwargs):
        window = self.live_window
        if final:
            window = self.final_window

        view = window._messenger._view._xsection
        view.update_image(data[self.label][::-1])
        window.show()

    def draw(self, fig=None):
        pass
