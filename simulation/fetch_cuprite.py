"""Fetch a pinned author-distributed benchmark; never silently replace cached files."""

import hashlib
import json
from pathlib import Path
import urllib.request

COMMIT = "29774c39f00d385b1d7898a8b1f26b3710aa036b"
BASE = f"https://raw.githubusercontent.com/gaetanosettembre/data_unmixing/{COMMIT}/"
FILES = {
    "Datasets/Cuprite/Cuprite_data_R188.mat":
        "dca2af6236bfdbe1a8e68c69873c74f470e32f931881df3b0b296034cbe14e37",
    "README.md": "10654c4d9cbd11d8730a8bf6e295c7d030fb83ed52243c13cb4a2006a98f8f7f",
    "LICENSE": "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986",
}


def fetch(folder=Path("data/cuprite")):
    folder.mkdir(parents=True, exist_ok=True)
    for relative, expected in FILES.items():
        target = folder / Path(relative).name
        if target.exists():
            content = target.read_bytes()
        else:
            with urllib.request.urlopen(BASE + relative, timeout=60) as response:
                content = response.read()
        actual = hashlib.sha256(content).hexdigest()
        if actual != expected:
            raise ValueError(f"Checksum mismatch: {target}; not overwriting.")
        if not target.exists():
            target.write_bytes(content)
        print(target, len(content), actual)
    return folder / "Cuprite_data_R188.mat"


if __name__ == "__main__":
    fetch()
