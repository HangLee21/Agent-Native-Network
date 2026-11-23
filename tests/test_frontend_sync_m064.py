"""M-064 offline filesystem/Git tests; no servers, hardware, SSH or network."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('frontend_sync', Path(__file__).resolve().parents[1] / 'tools/release/sync_frontend.py')
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


class FrontendSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='M064-frontend-sync-')
        self.root = Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup)

    def put(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_crlf_only_difference_does_not_write(self):
        path = self.put('frontend/test.ts', b'first\r\nsecond\r\n')
        plan = sync.plan_sync({'frontend/test.ts': b'first\nsecond\n'}, {}, self.root)
        self.assertEqual(plan['unchanged'], ['frontend/test.ts'])
        self.assertEqual(path.read_bytes(), b'first\r\nsecond\r\n')

    def test_source_change_updates_only_matching_base(self):
        self.put('frontend/test.ts', b'old')
        plan = sync.plan_sync({'frontend/test.ts': b'new'}, {'frontend/test.ts': sync.digest(b'old')}, self.root)
        self.assertEqual(plan['update'], ['frontend/test.ts'])
        self.assertFalse(plan['conflicts'])

    def test_diverged_target_is_not_overwritten(self):
        path = self.put('frontend/test.ts', b'target work')
        plan = sync.plan_sync({'frontend/test.ts': b'source work'}, {'frontend/test.ts': sync.digest(b'old')}, self.root)
        self.assertEqual(len(plan['conflicts']), 1)
        self.assertEqual(path.read_bytes(), b'target work')

    def test_new_source_file_is_addition(self):
        plan = sync.plan_sync({'frontend/new.ts': b'new'}, {}, self.root)
        self.assertEqual(plan['add'], ['frontend/new.ts'])
        self.assertFalse((self.root / 'frontend/new.ts').exists())

    def test_target_deletion_is_preserved_for_review(self):
        plan = sync.plan_sync({'frontend/test.ts': b'new'}, {'frontend/test.ts': sync.digest(b'old')}, self.root)
        self.assertEqual(len(plan['conflicts']), 1)
        self.assertFalse((self.root / 'frontend').exists())

    def test_unmanaged_existing_file_is_conflict(self):
        path = self.put('frontend/new.ts', b'unrelated')
        plan = sync.plan_sync({'frontend/new.ts': b'new'}, {}, self.root)
        self.assertEqual(len(plan['conflicts']), 1)
        self.assertEqual(path.read_bytes(), b'unrelated')

    def test_source_removal_never_deletes_target(self):
        path = self.put('frontend/old.ts', b'old')
        plan = sync.plan_sync({}, {'frontend/old.ts': sync.digest(b'old')}, self.root)
        self.assertIn('never auto-delete', plan['conflicts'][0]['reason'])
        self.assertTrue(path.exists())

    def test_out_of_scope_and_sensitive_paths_are_rejected(self):
        for name in ('../outside', '/frontend/x', 'frontend/../backend/pom.xml',
                     'backend/pom.xml', 'frontend\\x', 'C:/frontend/x',
                     'frontend/.env.local', 'frontend/key.pem', 'frontend/node_modules/x',
                     'frontend/DIST/x', 'frontend/.BASELINE-SYNC.json'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                sync.destination(self.root, name)

    def test_symlink_guard_rejects_without_writes(self):
        from unittest.mock import patch
        path = self.put('frontend/test.ts', b'old')
        with patch.object(Path, 'is_symlink', return_value=True), self.assertRaises(ValueError):
            sync.destination(self.root, 'frontend/test.ts')
        self.assertEqual(path.read_bytes(), b'old')

    def test_binary_content_is_not_line_normalized(self):
        self.assertNotEqual(sync.digest(b'\0a\r\nb'), sync.digest(b'\0a\nb'))

    def test_atomic_replace_resolves_only_managed_target(self):
        path = self.put('frontend/test.ts', b'old')
        sync.atomic_write(self.root, 'frontend/test.ts', b'new')
        self.assertEqual(path.read_bytes(), b'new')
        self.assertEqual(list(path.parent.iterdir()), [path])

    def test_committed_archive_excludes_working_tree_edits(self):
        sync.git(self.root, 'init', '-q')
        self.put('frontend/package.json', b'{"name":"test"}\n')
        sync.git(self.root, 'add', '--', 'frontend/package.json')
        sync.git(self.root, '-c', 'user.name=M064 Offline Test', '-c', 'user.email=m064@example.invalid', 'commit', '-qm', 'fixture')
        self.put('frontend/package.json', b'uncommitted')
        files = sync.archive_files(self.root, 'HEAD')
        self.assertEqual(set(files), {'frontend/package.json'})
        self.assertEqual(sync.digest(files['frontend/package.json']), sync.digest(b'{"name":"test"}\n'))

    def test_archive_does_not_include_backend_or_local_files(self):
        sync.git(self.root, 'init', '-q')
        self.put('frontend/test.ts', b'front')
        self.put('backend/secret.txt', b'not exported')
        sync.git(self.root, 'add', '--', 'frontend/test.ts', 'backend/secret.txt')
        sync.git(self.root, '-c', 'user.name=M064 Offline Test', '-c', 'user.email=m064@example.invalid', 'commit', '-qm', 'fixture')
        self.put('frontend/local.txt', b'untracked')
        self.assertEqual(sync.archive_files(self.root, 'HEAD'), {'frontend/test.ts': b'front'})


if __name__ == '__main__':
    unittest.main()
