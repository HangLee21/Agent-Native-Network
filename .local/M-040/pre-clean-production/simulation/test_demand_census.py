"""Semantic checks for offline counting; never invokes the task executor."""
import unittest
from simulation.demand_census import coalition_requirement, cache_reference_counts, intent_graph


class CensusTests(unittest.TestCase):
    def test_complementary_and_infeasible_capabilities(self):
        agents = {'0': {'abilities': [1, 0], 'species': 0},
                  '1': {'abilities': [0, 1], 'species': 1}}
        self.assertEqual(coalition_requirement(agents, [1, 1])['min_members'], 2)
        self.assertEqual(coalition_requirement(agents, [1, 1])['min_species_among_min_size'], 2)
        self.assertIsNone(coalition_requirement(agents, [2, 1])['min_members'])

    def test_generalist_prevents_assumed_team_requirement(self):
        agents = {'0': {'abilities': [1, 0], 'species': 0},
                  '1': {'abilities': [1, 1], 'species': 1}}
        self.assertEqual(coalition_requirement(agents, [1, 1])['min_members'], 1)

    def test_local_scene_is_not_network_reference(self):
        events = [{'id': 7, 'scene': {'task': 2, 'version': [0, 1, 0, 1]}}]
        evidence = {'1': [{'via': 'local_observation', 'kind': 'task_scene', 'source': 0,
                           'evidence_id': 7, 'applied': True}]}
        dd = [{'actor': 1, 'evidence_count': 1, 'source_versions': {'0': 0, '1': 0},
               'task_versions': {'2': [0, 1, 0, 1]}}]
        counts, refs = cache_reference_counts(dd, evidence, [], events)
        self.assertEqual(counts['local_scene_references'], 1)
        self.assertEqual(counts['initial_remote_state_slots'], 1)
        self.assertFalse(refs)

    def test_replaced_version_is_not_counted_as_referenced(self):
        import json
        messages = [{'message_id': f'm{seq}', 'payload_utf8': json.dumps(
            {'kind':'self_state','source':0,'state':{'seq':seq}})} for seq in (1,2)]
        evidence = {'1':[{'via':'network','kind':'self_state','source':0,
                         'evidence_id':f'm{seq}','applied':True} for seq in (1,2)]}
        dd = [{'actor':1,'evidence_count':2,'source_versions':{'0':2,'1':0},'task_versions':{}}]
        _, refs = cache_reference_counts(dd, evidence, messages, [])
        self.assertEqual(refs, {('m2',1):1})

    def test_pair_birth_and_departure(self):
        events = [{'kind':'own_state','actor':i,'state':{'target':t,'mode':mode}}
                  for i,t,mode in [(0,2,'travel'),(1,2,'travel'),(0,2,'working'),(1,2,'idle')]]
        counts = intent_graph(events)
        self.assertEqual(counts['intent_pair_births'], 1)
        self.assertEqual(counts['intent_pair_deaths'], 1)
        self.assertEqual(counts['distinct_intent_pairs'], 1)


if __name__ == '__main__':
    unittest.main()
