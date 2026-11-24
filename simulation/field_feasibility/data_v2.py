"""Access audited Mendeley V2 samples without interpolation or fabricated values.

Abstract local grid: axis 0 is x, axis 1 is y, each index maps to 5 m.
The dataset does not specify a georeferenced origin or a definitive orientation.
Grid locations are 0..1245 m inclusive; nearest cell with ties upward is used.
t_s must be an integer relative second 0..599: 0 is manual's 1 s frame.
Only the four provided heights are supported; unsupported queries raise ValueError.
The measured repeated minimum is returned unchanged: its meaning is not established.
"""
from pathlib import Path
import math
import numpy as np


class FieldV2:
    HEIGHTS = (2, 25, 50, 80)

    def __init__(self, root):
        self.root = Path(root)
        self._arrays = {}
        for height in self.HEIGHTS:
            path = self.root / ('dynamic_h%dm_f64.npy' % height)
            array = np.load(path, mmap_mode='r', allow_pickle=False)
            if array.shape != (250, 250, 600) or array.dtype != np.float64:
                raise ValueError('invalid V2 derived array: ' + str(path))
            self._arrays[height] = array

    def query(self, x_m, y_m, h_m, t_s):
        try:
            x, y, height, second = map(float, (x_m, y_m, h_m, t_s))
        except (TypeError, ValueError) as exc:
            raise ValueError('query requires numeric x, y, height and time') from exc
        if not all(map(math.isfinite, (x, y, height, second))):
            raise ValueError('query coordinates must be finite')
        if not (0 <= x <= 1245 and 0 <= y <= 1245):
            raise ValueError('x and y must be within the 0..1245 m grid')
        if height not in self.HEIGHTS:
            raise ValueError('height must be one of 2, 25, 50, 80 m')
        if not second.is_integer() or not 0 <= second <= 599:
            raise ValueError('relative time must be an integer 0..599 seconds')
        return float(self._arrays[int(height)][math.floor(x / 5 + .5),
                                                math.floor(y / 5 + .5), int(second)])
