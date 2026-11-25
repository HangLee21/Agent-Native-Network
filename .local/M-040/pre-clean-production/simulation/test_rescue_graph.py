import unittest
from simulation.rescue_graph import parse, prepare, episode, shortest


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.graph = {i: {} for i in range(13)}
        for i in range(12):
            self.graph[i][i+1] = self.graph[i+1][i] = 3

    def test_visibility_is_not_travel(self):
        self.assertEqual(shortest(self.graph, 0)[0][12], 12)
        self.assertEqual(shortest(self.graph, 0, True)[0][12], 36)

    def test_disconnected_rejected(self):
        with self.assertRaises(AssertionError):
            parse('0 [label="base"];\n1 [label="isolated"];')

    def test_full_contact_negative_control(self):
        setup = prepare(self.graph, 9999)
        expected, _ = episode(self.graph, setup, 600, 'ideal', 0, 3)
        for policy, parameter in [('carry',0),('base_age',60),('contact_age',60),('contact_batch',1)]:
            actual, _ = episode(self.graph, setup, 600, policy, parameter, 3)
            self.assertEqual(actual, expected)

    def test_carry_path_independent_of_targets(self):
        setup = prepare(self.graph, 3)
        _, a = episode(self.graph, setup, 600, 'carry', 0, 1, True)
        _, b = episode(self.graph, setup, 600, 'carry', 0, 2, True)
        self.assertEqual(a['events'], b['events'])

    def test_budget_causality_and_same_hidden_targets(self):
        setup = prepare(self.graph, 6)
        for seed in range(12):
            targets = None
            for policy, parameter in [('ideal',0),('carry',0),('base_age',60),('contact_age',60),('contact_batch',1)]:
                row, trace = episode(self.graph, setup, 600, policy, parameter, seed, True)
                self.assertTrue(all(e['time'] <= 600 for e in trace['events']))
                self.assertTrue(all(r['discovered'] <= r['received'] <= 600 for r in trace['reports']))
                self.assertEqual(row['received'], row['discovered'])
                if targets is not None: self.assertEqual(targets, trace['targets'])
                targets = trace['targets']


if __name__ == '__main__':
    unittest.main()
