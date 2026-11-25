import unittest
import numpy as np
from simulation.spatial_mixing import block_average


class SpatialTests(unittest.TestCase):
    def test_no_mixing_control_is_identity(self):
        cube=np.random.default_rng(2).normal(size=(8,8,5))
        np.testing.assert_array_equal(block_average(cube,1),cube)

    def test_blocks_share_only_mean_and_preserve_global_mean(self):
        cube=np.arange(8*8*3).reshape(8,8,3).astype(float)
        averaged=block_average(cube,4)
        for y in (0,4):
            for x in (0,4):
                expected=cube[y:y+4,x:x+4].mean(axis=(0,1))
                np.testing.assert_allclose(averaged[y:y+4,x:x+4],np.broadcast_to(expected,(4,4,3)))
        np.testing.assert_allclose(averaged.mean(axis=(0,1)),cube.mean(axis=(0,1)))

    def test_rejects_partial_blocks(self):
        with self.assertRaises(ValueError):block_average(np.ones((8,8,3)),3)


if __name__=='__main__':unittest.main()
