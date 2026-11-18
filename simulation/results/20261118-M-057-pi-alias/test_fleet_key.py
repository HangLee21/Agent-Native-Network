import base64
import contextlib
import io
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools/mid_baseline/gateway_probe"))
import mkcard


KEY_DATA = base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes(range(32))).decode()
KEY = "ssh-ed25519 " + KEY_DATA


class FleetKeyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.boot = self.root / "boot"
        self.boot.mkdir()
        (self.boot / "cmdline.txt").write_text("root=PARTUUID=fake ds=nocloud\n")
        (self.boot / "user-data").write_text("#cloud-config\nusers:\n  - name: eora\n")
        (self.boot / "meta-data").write_text("instance-id: old\n")
        self.env = self.root / "env"
        self.env.write_text("WIFI_SSID=test\nWIFI_IDENTITY=test\nWIFI_PASSWORD=test\nTAILSCALE_AUTHKEY=test\n")
        self.pub = self.root / "fleet.pub"
        self.pub.write_text(KEY + " comment\n")

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, number):
        argv = ["mkcard", "--card", str(self.boot), "--number", str(number)]
        with patch.object(mkcard, "ENV_FILE", self.env), patch.object(mkcard, "FLEET_PUBLIC_KEY", self.pub), patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
            return mkcard.main()

    def test_normal_entry_and_numbered_hosts(self):
        for number in (5, 105, 255):
            self.assertEqual(self.prepare(number), 0)
            script = (self.boot / mkcard.INSTALLER_NAME).read_text(encoding="utf-8")
            self.assertIn(KEY, script)
            self.assertIn("eora-air-%02d" % number, script)
            self.assertLess(script.index("runuser -u eora -- python3 /usr/local/lib/eora/install_fleet_key.py"), script.index("systemctl start --no-block"))
            self.assertIn("runuser -u eora -- python3 /usr/local/lib/eora/install_fleet_key.py", mkcard.LOGIC)
            self.assertLess(mkcard.LOGIC.index("install_fleet_key.py"), mkcard.LOGIC.index("nmcli connection up"))
            self.assertEqual(yaml.safe_load((self.boot / "user-data").read_text())["users"][0]["name"], "eora")

    def test_missing_invalid_key_never_writes(self):
        for value in (None, "ssh-rsa AAAA", "ssh-ed25519 bad!", KEY + "\n" + KEY, "ssh-ed25519 " + base64.b64encode(b"invalid").decode()):
            if value is None:
                self.pub.unlink(missing_ok=True)
            else:
                self.pub.write_text(value)
            before = {p.name: p.read_bytes() for p in self.boot.iterdir()}
            self.assertEqual(self.prepare(5), 2)
            self.assertEqual(before, {p.name: p.read_bytes() for p in self.boot.iterdir()})

    def test_existing_authorizations_and_permissions(self):
        namespace = {"__name__": "key_fixture"}
        with patch.dict(sys.modules, {"pwd": types.ModuleType("pwd")}):
            exec(mkcard.KEY_INSTALLER, namespace)
        install = namespace["install_authorized_key"]
        ssh = self.root / ".ssh"
        ssh.mkdir()
        authorized = ssh / "authorized_keys"
        restricted = 'command="echo hello world",no-port-forwarding ' + KEY + ' existing\n'
        original = "ssh-rsa unrelated existing\n" + restricted
        authorized.write_text(original)
        with patch.object(os, "chmod") as chmod:
            install(self.root, KEY)
            install(self.root, KEY)
        self.assertEqual(authorized.read_text(), original)
        chmod.assert_any_call(ssh, 0o700)
        chmod.assert_any_call(authorized, 0o600)
        authorized.write_text("ssh-rsa unrelated")
        with patch.object(os, "chmod"):
            install(self.root, KEY)
            install(self.root, KEY)
        self.assertEqual(authorized.read_text(), "ssh-rsa unrelated\n" + KEY + "\n")

    def test_helper_rejects_wrong_effective_user(self):
        fake_pwd = types.ModuleType("pwd")
        fake_pwd.getpwnam = lambda name: types.SimpleNamespace(pw_uid=1000, pw_dir=str(self.root))
        with patch.dict(sys.modules, {"pwd": fake_pwd}), patch.object(os, "geteuid", return_value=0, create=True):
            with self.assertRaisesRegex(SystemExit, "must run as eora"):
                exec(mkcard.KEY_INSTALLER, {"__name__": "__main__"})
        self.assertFalse((self.root / ".ssh").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
