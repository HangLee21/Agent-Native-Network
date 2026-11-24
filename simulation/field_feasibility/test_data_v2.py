import pathlib,sys,unittest
import numpy as np
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]))
from simulation.field_feasibility.baseline_run import predictions
from simulation.field_feasibility.data_v2 import FieldV2
class Checks(unittest.TestCase):
 def test_constant_field_predictions_and_variance(self):
  xy=np.array([(x*5,y*5) for x in range(5) for y in range(5)],dtype=float);values=np.full(len(xy),-70.0);p,v=predictions(xy,values,np.array([[12.5,12.5],[31,14]],dtype=float));np.testing.assert_allclose(p,-70,atol=1e-9);self.assertTrue(np.all(np.isfinite(v)));self.assertTrue(np.all((v>=0)&(v<=400)))
 def test_real_data_and_bounds(self):
  f=FieldV2(pathlib.Path(__file__).resolve().parents[2]/'data/field_feasibility_v2');self.assertAlmostEqual(f.query(0,0,2,0),-86.754)
  for args in ((-1,0,2,0),(0,0,12,0),(0,0,2,600),(0,0,2,0.5)):
   with self.assertRaises(ValueError):f.query(*args)
if __name__=='__main__':unittest.main(verbosity=2)
