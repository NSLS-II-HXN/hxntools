import numpy as np
import matplotlib.pyplot as plt


def plot_position(scan_id, data, debug_data, *, left='ssx', right='ssy'):
    start_t = debug_data['start_time']
    end_t = debug_data['end_time']
    t = debug_data['servo_time']
    gather_x = debug_data['servo_' + left]
    gather_y = debug_data['servo_' + right]
    target_x = debug_data.get('target_' + left, None)
    target_y = debug_data.get('target_' + right, None)
    avg_x = data[left]
    avg_y = data[right]
    # gather_z = data['servo_ssz']
    mid_t = data['elapsed_time']

    colors = {'x': 'blue',
              'y': 'red',
              'z': 'green',
              'target_x': 'black',
              'target_y': 'black',
              'target_z': 'black'
              }

    plt.clf()
    y_min, y_max = np.min(gather_x), np.max(gather_x)

    # frame start/end times (green = start, red = end)
    plt.vlines(start_t, y_min, y_max, colors='g', linestyle='solid')
    plt.vlines(end_t, y_min, y_max, colors='r', linestyle='dashed')

    plt.ylabel('x position [um]')
    plt.plot(t, gather_x, colors['x'], label='fssx')
    if target_x is not None:
        plt.plot(t, target_x, colors['target_x'], label='target_fssx')
    plt.scatter(mid_t, avg_x, marker='o', color=colors['x'],
                zorder=10)

    ax1 = plt.gca()
    ax1.yaxis.label.set_color(colors['x'])
    ax1.tick_params(axis='y', colors=colors['x'])

    ax2 = plt.gca().twinx()
    plt.ylabel('y position [um]')
    ax2.plot(t, gather_y, colors['y'], label='fssy')
    if target_y is not None:
        plt.plot(t, target_y, colors['target_y'], label='target_fssy')

    ax2.yaxis.label.set_color(colors['y'])
    ax2.tick_params(axis='y', colors=colors['y'])

    y_min = np.min(gather_y)
    y_max = np.max(gather_y)

    # frame start/end times (green = start, red = end)
    ax2.vlines(start_t, y_min, y_max, colors='g', linestyle='solid')
    ax2.vlines(end_t, y_min, y_max, colors='r', linestyle='dashed')

    ax2.scatter(mid_t, avg_y, marker='o', color=colors['y'],
                zorder=10)

    plt.xlim(0, t[-1])
    plt.title('Scan {} positions'.format(scan_id, ))
    plt.xlabel('Time [s]')
    return [ax1, ax2]
