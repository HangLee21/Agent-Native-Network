import unittest
import numpy as np
from simulation.validate_observation import reconstruct, select_diverse, patch_data


class ObservationTests(unittest.TestCase):
    def test_reconstructs_identifiable_mixtures(self):
        library = np.array([[1.,0.,.5,0.],[0.,1.,0.,.5]])
        response = np.array([[1.,0.],[0.,1.],[0.,0.],[0.,0.]])
        truth = np.array([[.2,.8],[.7,.3]]) @ library
        prediction = reconstruct(truth @ response, library, response)
        np.testing.assert_allclose(prediction, truth, atol=1e-10)

    def test_remote_only_library_growth_adds_no_information(self):
        rng = np.random.default_rng(123)
        library = rng.uniform(.1,1,(4,20))
        response = rng.uniform(0,1,(20,9))
        test_remote = rng.uniform(0,1,(8,9))
        additional = reconstruct(rng.uniform(0,1,(12,9)), library, response)
        baseline = reconstruct(test_remote, library, response)
        enlarged = reconstruct(test_remote,np.vstack([library,additional]),response)
        np.testing.assert_allclose(baseline,enlarged,atol=1e-8)

    def test_selector_unique_and_deterministic(self):
        features=np.arange(60).reshape(20,3)
        a=select_diverse(features,np.zeros((1,3)),10)
        b=select_diverse(features,np.zeros((1,3)),10)
        np.testing.assert_array_equal(a,b)
        self.assertEqual(len(set(a)),10)

    def test_sampling_and_evaluation_are_disjoint(self):
        # Pixel IDs encoded in the spectra to test masks directly.
        cube=np.arange(80*80).reshape(80,80,1)
        candidate,evaluation,_=patch_data(cube,(0,0))
        self.assertEqual(candidate.shape,(256,1))
        self.assertEqual(evaluation.shape,(256,1))
        self.assertFalse(set(candidate.ravel()) & set(evaluation.ravel()))


if __name__=="__main__":
    unittest.main()
