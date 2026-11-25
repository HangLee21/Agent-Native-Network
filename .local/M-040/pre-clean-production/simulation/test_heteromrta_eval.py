"""Safety and evidence checks; no network, asset download, or simulation."""
import io
import json
from pathlib import Path
import pickle
import tempfile
import unittest
from unittest.mock import patch

from simulation.heteromrta_eval import CheckpointUnpickler, run


class EvaluationSafetyTests(unittest.TestCase):
    def test_checkpoint_rejects_non_tensor_global(self):
        malicious = b'cos\nsystem\n.'
        with self.assertRaisesRegex(pickle.UnpicklingError, 'Forbidden'):
            CheckpointUnpickler(io.BytesIO(malicious)).load()

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            sentinel = Path(d) / 'result.json'
            sentinel.write_text('{"keep": true}')
            args = type('Args', (), {'output': d})()
            with patch('simulation.heteromrta_eval.asset_manifest', return_value=[]):
                with self.assertRaisesRegex(ValueError, 'new/empty'):
                    run(args)
            self.assertEqual(json.loads(sentinel.read_text()), {'keep': True})


if __name__ == '__main__':
    unittest.main()
