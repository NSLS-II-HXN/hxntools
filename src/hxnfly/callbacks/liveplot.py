import asyncio
import logging
from collections import OrderedDict

import PyQt5
import IPython

import matplotlib as mpl
import matplotlib.pyplot as plt

from .flydata import (FlyDataCallbacks, catch_exceptions, SignalDataHandler)

from matplotlib.backends.qt_compat import QtCore

logger = logging.getLogger(__name__)
mpl.rcParams['figure.raise_window'] = False


def get_insertFig():
    ip = IPython.get_ipython()
    try:
        return ip.user_ns['insertFig']
    except KeyError:
        def insertFig(*args, **kwargs):
            logger.error('insertFig not found in user namespace')
        return insertFig


def add_toolbar_button(fig, text, *, theme_icon='go-down', slot=None):
    toolbar = fig.canvas.manager.toolbar
    # QtWidgets.QToolBar
    icon = PyQt5.QtGui.QIcon.fromTheme(theme_icon)
    action = toolbar.addAction(icon, text)
    if slot is not None:
        action.triggered.connect(slot)
    return action


class LivePlotBase(FlyDataCallbacks):
    def __init__(self, signals, flyer=None, rate=2.0, point_signal=None,
                 data_func=None, enabled=True,
                 **plot_kwargs):
        super().__init__(flyer=flyer)

        if not signals:
            raise ValueError('Must have at least one signal to plot')

        self._continue_updates = False

        self.signals = signals
        self.data = SignalDataHandler(signals, data_func=data_func,
                                      point_signal=point_signal)

        self.plot_kwargs = plot_kwargs
        self.rate = rate
        self.enabled = enabled

        self.final_ax = None
        self.final_fig = None
        self.fig, self.ax = None, None

    def _reset(self):
        if self.fig is None or not plt.fignum_exists(self.fig.number):
            self.fig, self.ax = plt.subplots()
            add_toolbar_button(self.fig, 'Call insertFig()',
                               slot=lambda fig: get_insertFig()(fig=self.fig))
        else:
            self.fig.clear()
            self.ax = self.fig.add_subplot(111)

    def disable(self):
        '''Turn off plotting'''
        self.enabled = False

    def enable(self):
        '''Turn on plotting'''
        self.enabled = True

    def reset(self):
        '''Open new windows on the next scan'''
        # self.fast_axis = None
        pass

    def close_all(self):
        '''Close all plots'''
        plt.close('all')

    @catch_exceptions
    def _update(self):
        try:
            if self._run_header is not None:
                self._replot_preview()
        finally:
            # loop.call_later(self.rate, self._update)
            if self._continue_updates:
                QtCore.QTimer.singleShot(int(self.rate * 1000), self._update)


    def scan_started(self, doc, ndim, fast_axis=None, **scan_args):
        # if self.fast_axis != fast_axis:
        self._reset()

    def scan_finished(self, doc, scan_data, cancelled=False, **kwargs):
        self._stop_updates()

        if (self.final_fig is None or not
                plt.fignum_exists(self.final_fig.number)):
            fig, ax = plt.subplots()
            self.final_ax = ax
            self.final_fig = fig
            self.final_legend = None
            add_toolbar_button(self.final_fig, 'Call insertFig()',
                               slot=lambda fig: get_insertFig()(fig=self.final_fig))

    def _start_updates(self):
        # loop.call_soon(self._update)
        self._continue_updates = True
        QtCore.QTimer.singleShot(1000, self._update)  # First update after 1s

    def _stop_updates(self):
        self._continue_updates = False


class FlyLivePlot(LivePlotBase):
    def __init__(self, signals, y='counts', yscale='linear', **kwargs):
        super().__init__(signals, **kwargs)

        self.yscale = yscale
        self.ylabel = y
        self.enabled = True

        # Limit the number of lines simultaneously shown on the final plot
        #   (to avoid 100s of lines to be accumulated).
        self.final_plot_max_lines = 6


    def _reset(self):
        super()._reset()

        self.lines = []
        self.preview_lines = None

        self.ax.set_ylabel(self.ylabel or 'counts')
        self.ax.set_xlabel('Scan point')

        self.ax.set_yscale(self.yscale)
        self.ax.margins(0.1)

    @catch_exceptions
    def _replot_preview(self):
        try:
            npts = self.data.num_points
        except ValueError:
            npts = self.num

        npts = npts or 0

        with self.data._lock:
            if not self.data.updated:
                return

            data = self.data.calc_data(npts)

        if self.preview_lines is None:
            def _plot(label, linedata):
                return self.ax.plot(range(len(linedata)), linedata,
                                    label=label, **self.plot_kwargs)[0]

            lines = OrderedDict((label, _plot(label, linedata))
                                for label, linedata in data.items())
            self.preview_lines = lines
            self.legend = self.ax.legend(loc=0)
            if self.legend is not None:
                self.legend.set_draggable(True)
        else:
            for key, line in self.preview_lines.items():
                linedata = data[key]
                xpts = range(len(linedata))
                line.set_data(xpts, linedata)

        # Rescale and redraw.
        self.ax.relim(visible_only=True)
        self.ax.autoscale_view(tight=True)
        self.fig.canvas.draw()

    def scan_started(self, doc, ndim, **scan_args):
        super().scan_started(doc, ndim, **scan_args)

        self.ax.set_title('Scan {}'.format(self.scan_id))
        self._start_updates()

    def scan_finished(self, doc, scan_data, cancelled=False, **kwargs):
        super().scan_finished(doc, scan_data, cancelled=cancelled, **kwargs)

        ax, fig = self.final_ax, self.final_fig

        # Delete the extra lines from the plot. Leave 'self.final_plot_max_lines - 1' lines
        while True:
            lns = ax.get_lines()
            if len(lns) < self.final_plot_max_lines:
                break
            lns[0].remove()

        if scan_data is None:
            logger.error('No scan data for the live plot')
            return

        try:
            x_pos = scan_data[self.fast_axis]
        except KeyError as ex:
            logger.error('Motor position data not found in flyscan '
                         'instance?', exc_info=ex)
            return

        npts = len(x_pos)
        data = self.data.calc_data(npts)
        for label, y_data in data.items():
            label = 'S{} {}'.format(self.scan_id, label)
            try:
                length = min((npts, len(y_data)))
                ax.plot(x_pos[:length], y_data[:length], label=label,
                        **self.plot_kwargs)
            except TypeError:
                continue

        self.final_legend = ax.legend(loc=0)
        if self.final_legend is not None:
            self.final_legend.set_draggable(True)

        ax.set_ylabel(self.ylabel or 'counts')
        ax.set_xlabel(self.fast_axis)

        # Rescale and redraw.
        ax.set_yscale(self.yscale)
        ax.relim(visible_only=True)
        ax.autoscale_view(tight=True)
        fig.canvas.draw()
