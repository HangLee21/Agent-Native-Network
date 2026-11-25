"""Structural tests for prefix pairing; no author environment or policy execution."""
import copy
import unittest
from simulation.heteromrta_scale_catalog import expand_catalog, normalize_catalog, validate_pairing, families

def fixture():
    return {'agents':{i:{'abilities':[1,1,1,1,1], 'depot':[i/10,0.],
                        'velocity':.2,'species':i//3} for i in range(9)},
            'tasks':{i:{'requirements':[1,0,1,0,0],'location':[i/60,0.],
                        'time':1.} for i in range(60)}}

class CatalogTests(unittest.TestCase):
    def test_prefix_and_original_ids(self):
        master=fixture()
        child=expand_catalog(master,36,30)
        self.assertEqual(child['tasks'],{i:master['tasks'][i] for i in range(30)})
        self.assertEqual({i:child['agents'][i] for i in range(9)},master['agents'])
        self.assertTrue(validate_pairing(master,child)['appended_clones_exact'])

    def test_clones_independent(self):
        master=fixture(); child=expand_catalog(master,18,15)
        child['agents'][9]['depot'][0]=999
        child['tasks'][0]['location'][0]=999
        self.assertNotEqual(child['agents'][0]['depot'][0],999)
        self.assertNotEqual(master['tasks'][0]['location'][0],999)
        with self.assertRaises(AssertionError):
            validate_pairing(master,child)

    def test_json_keys_sorted_numerically(self):
        master=fixture()
        shuffled={k:{str(i):v for i,v in reversed(list(d.items()))} for k,d in master.items()}
        result=normalize_catalog(shuffled)
        self.assertEqual(list(result['tasks']),list(range(60)))
        self.assertEqual(result,master)

    def test_bad_ids_or_counts_rejected(self):
        master=fixture(); broken=copy.deepcopy(master); broken['agents'][10]=broken['agents'].pop(8)
        with self.assertRaises(ValueError):
            normalize_catalog(broken)
        for n,t in [(10,15),(9,14),(18,61)]:
            with self.assertRaises(ValueError):
                expand_catalog(master,n,t)

    def test_two_families_shared_origin_only(self):
        self.assertEqual(len(families(9,15)),2)
        self.assertEqual(families(18,15),['fixed_total_15'])
        self.assertEqual(families(18,30),['fixed_tasks_per_agent_5_over_3'])
        self.assertEqual(families(36,60),['fixed_tasks_per_agent_5_over_3'])

if __name__=='__main__':
    unittest.main()
