"""C-013 regression: reject self-reported hashes of same-size replacements.

Synthetic local bytes only, no model weights, downloads, or inference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import unittest

from .a0 import verify_model_file
from .common import ROOT, complete_run, file_sha, new_run
from .runtime import sha, write_json


def git_blob(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


class SourceIdentityChecks(unittest.TestCase):
    scratch = None

    def file(self, name, data):
        path = self.scratch / name
        path.write_bytes(data)
        return path

    def test_frozen_ordinary_blob_accepts_original_bytes(self):
        raw = b'{"token":"original"}\n'
        source = dict(path="ordinary.json", size_bytes=len(raw), sha256=None, git_blob_sha1=git_blob(raw))
        result = verify_model_file(self.file("original.json", raw), source, sha(raw))
        self.assertEqual(result, dict(sha256=sha(raw), git_blob_sha1=git_blob(raw)))

    def test_same_size_tamper_with_updated_self_sha_rejected(self):
        original, changed = b'{"token":"A"}\n', b'{"token":"B"}\n'
        self.assertEqual(len(original), len(changed))
        source = dict(path="ordinary.json", size_bytes=len(original), sha256=None, git_blob_sha1=git_blob(original))
        with self.assertRaisesRegex(ValueError, "Git blob differs"):
            verify_model_file(self.file("changed.json", changed), source, sha(changed))

    def test_all_five_actual_lock_entries_reject_self_reported_replacements(self):
        lock = json.loads((ROOT / "research/agent_native_network/preparation_20261028/SOURCE_LOCK.json").read_text(encoding="utf-8"))
        unknown = [r for r in lock["model"]["files"] if r["sha256"] is None]
        self.assertEqual({r["path"] for r in unknown},
                         {"added_tokens.json", "merges.txt", "special_tokens_map.json", "tokenizer.json", "vocab.json"})
        for record in unknown:
            with self.subTest(path=record["path"]):
                # This is a hostile stand-in, not a download or valid tokenizer.
                changed = b"x" * record["size_bytes"]
                self.assertNotEqual(git_blob(changed), record["git_blob_sha1"])
                with self.assertRaisesRegex(ValueError, "Git blob differs"):
                    verify_model_file(self.file("synthetic-" + record["path"], changed), record, sha(changed))

    def test_published_content_hash_binds_lfs_without_hashing_pointer_as_weights(self):
        raw = b"synthetic tensor contents"
        source = dict(path="model.safetensors", size_bytes=len(raw), sha256=sha(raw), git_blob_sha1="0" * 40)
        result = verify_model_file(self.file("synthetic-lfs", raw), source, sha(raw))
        self.assertEqual(result["sha256"], sha(raw))
        self.assertIsNone(result["git_blob_sha1"])

    def test_published_sha_cannot_be_replaced_by_local_sha(self):
        source = dict(path="file", size_bytes=3, sha256=sha(b"abc"), git_blob_sha1="0" * 40)
        with self.assertRaisesRegex(ValueError, "SHA-256 differs"):
            verify_model_file(self.file("wrong-published", b"xyz"), source, sha(b"xyz"))

    def test_missing_frozen_identity_refused(self):
        source = dict(path="file", size_bytes=3, sha256=None, git_blob_sha1=None)
        with self.assertRaisesRegex(ValueError, "no frozen content identity"):
            verify_model_file(self.file("missing-identity", b"abc"), source, sha(b"abc"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    out, manifest = new_run(args.output, "C-013_source_identity_regression", dict(model_forwards=0, downloads_bytes=0))
    SourceIdentityChecks.scratch = out / "scratch"
    SourceIdentityChecks.scratch.mkdir()
    lock = ROOT / "research/agent_native_network/preparation_20261028/SOURCE_LOCK.json"
    (out / "SOURCE_LOCK.json").write_bytes(lock.read_bytes())
    with (out / "checks.txt").open("w", encoding="utf-8") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SourceIdentityChecks))
    details = dict(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                   successful=result.wasSuccessful(), model_forwards=0, downloaded_bytes=0,
                   source_lock_sha256=file_sha(lock), five_fixed_entries_tested=True)
    write_json(out / "result.json", details)
    complete_run(out, manifest, "passed" if result.wasSuccessful() else "failed", 0 if result.wasSuccessful() else 1,
                 actual_model_forwards=0, source_lock_sha256=file_sha(lock))
    print(json.dumps(details))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
