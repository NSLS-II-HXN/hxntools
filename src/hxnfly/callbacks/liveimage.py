import asyncio
import logging
from collections import OrderedDict

import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt

from .flydata import (catch_exceptions, SubscanDataHandler)
from .liveplot import LivePlotBase
from .roiplot import FlyRoiPlot

logger = logging.getLogger(__name__)
mpl.rcParams['figure.raise_window'] = False


def _sum_func(*values):
    return np.sum(values, axis=0)


def resize_1d(data, length):
    try:
        len(data)
    except TypeError:
        return np.zeros(length)

    if len(data) > length:
        return data[:length]
    elif len(data) < length:
        try:
            fill_value = np.nanmin(data)
        except ValueError:
            fill_value = 0.0

        _data = np.ones(length) * fill_value
        _data[:len(data)] = data
        return _data
    else:
        return data


def reshape(data, nx, ny, *, fly_type=None):
    data = resize_1d(data, nx * ny)
    data = data.reshape(ny, nx)

    if fly_type in ('pyramid', ):
        data[1::2, :] = data[1::2, ::-1]

    return data


class FlyLiveImage(FlyRoiPlot):
    # TODO this whole thing is a mess of inefficiency with array
    def __init__(self, roi_names, use_sum=False, data_func=None, **kwargs):
        super().__init__(roi_names, use_sum=use_sum, data_func=data_func,
                         **kwargs)

        self._gridspec = None

        if use_sum:
            data_func = _sum_func

        self.subscan_keys = OrderedDict((group_key,
                                         [sig.name for sig in roi_signals])
                                        for group_key, roi_signals in
                                        self.signals.items())

        logger.debug('Subscan keys %s', self.subscan_keys)
        self.subscan_dh = SubscanDataHandler(self.subscan_keys,
                                             data_func=data_func)
        self.subscan_data = OrderedDict()
        self.new_subscan = False

    def _subscan_recalculate(self):
        try:
            data = self.subscan_dh.calc_data(self.flyer, self.scan_id)
        except TypeError as ex:
            logger.debug('Subscan recalculation failed', exc_info=ex)
        else:
            self.subscan_data = data
            self.new_subscan = True

        return self.subscan_data

    def subscan_start(self, index=0, **kwargs):
        self._subscan_recalculate()

    def _reset(self):
        super()._reset()

    @catch_exceptions
    def _replot_preview(self):
        if self.new_subscan:
            self.new_subscan = False
        elif not self.data.updated:
            return

        try:
            nx, ny = self._run_header['shape']
        except ValueError:
            return

        try:
            npts = self.data.num_points
        except ValueError:
            npts = self.num

        npts = npts or 0

        subscan_data = self.subscan_data
        livedata = self.data.calc_data(npts)
        fly_type = self._run_header['fly_type']

        plot_data = OrderedDict()
        for group_key in self.subscan_keys.keys():
            arrs = [arr for arr in (subscan_data.get(group_key, []),
                                    livedata[group_key])
                    if np.size(arr)]

            if not arrs:
                continue
            elif len(arrs) == 1:
                data = arrs[0]
            else:
                data = np.concatenate(arrs)

            plot_data[group_key] = reshape(data, nx, ny,
                                           fly_type=fly_type)

        self.plot(self.fig, plot_data)
        self.fig.canvas.manager.set_window_title(f"LiveImage - scan {self.scan_id}")
        self.draw()

    def draw(self, fig=None):
        if fig is None:
            fig = self.fig

        fig.canvas.manager.show()
        fig.canvas.draw()
        fig.canvas.flush_events()

    @catch_exceptions
    def plot(self, fig, labeled_data, *, final=False, **kwargs):
        count = len(labeled_data)

        # The first frame may contain no data.
        if not count:
            return

        if final or self._gridspec is None or count != len(self._axes):
            fig.clear()
            rows = int(np.ceil(np.sqrt(count)))
            gridspec = plt.GridSpec(rows, rows)
            axes = OrderedDict((key, fig.add_subplot(gs))
                               for gs, key in
                               zip(gridspec, labeled_data.keys()))

            if not final:
                self._gridspec = gridspec
                self._axes = axes
        elif not final:
            axes = self._axes

        extent = kwargs.pop('extent', self.default_extents)
        for label, data in labeled_data.items():
            ax = axes[label]
            ax.clear()
            ax.imshow(data, interpolation='none', extent=extent, **kwargs)
            ax.set_title(label)
            ax.autoscale_view(tight=True)
            # self.cs.update_image(data)
        return axes

    def scan_started(self, doc, ndim, **scan_args):
        if ndim != 2:
            return

        self._gridspec = None  # Clear the figure at the next update
        self.subscan_data = OrderedDict()
        self.new_subscan = False

        (x1, x2), (y1, y2) = doc['scan_range']
        self.default_extents = [x1, x2, y2, y1]
        super().scan_started(doc, ndim, **scan_args)

    def get_motor_positions(self):
        motor1, motor2 = self._run_header['motors']
        subscan_data = self.flyer.data[self.scan_id]
        pos = [subscan_data[motor] for motor in (motor1, motor2)]
        return pos

    def get_plot_extents(self):
        try:
            pos = self.get_motor_positions()
        except KeyError:
            # Scan positions from mixed fly/step scans might not be available
            return self.default_extents
        except Exception as ex:
            logger.debug('Failed to get motor positions', exc_info=ex)
        else:
            mins = [np.min(p) for p in pos]
            maxes = [np.max(p) for p in pos]
            extent = [mins[0], maxes[0], maxes[1], mins[1]]

            if ((abs(extent[0] - extent[1]) <= 0.001) or
                    (abs(extent[2] - extent[3]) <= 0.001)):
                return None

            return extent

    @catch_exceptions
    def scan_finished(self, doc, scan_data, cancelled=False, **kwargs):
        try:
            nx, ny = self._run_header['shape']
            fly_type = self._run_header['fly_type']
        except (KeyError, ValueError):
            return

        subscan_data = self._subscan_recalculate()
        if not subscan_data:
            return

        # TODO poor oo-code :(
        LivePlotBase.scan_finished(self, doc, scan_data, cancelled=cancelled,
                                   **kwargs)

        extent = self.get_plot_extents()

        data = OrderedDict((label, reshape(d, nx, ny, fly_type=fly_type))
                           for label, d in subscan_data.items())

        # re-create the grid
        self._gridspec = None

        for fig in [self.fig, self.final_fig]:
            final = (fig is self.final_fig)
            self.plot(fig, data, final=final, extent=extent,
                      **self.plot_kwargs)
            self.draw(fig)
            fig.canvas.manager.set_window_title(f"Final image - scan {self.scan_id}")
