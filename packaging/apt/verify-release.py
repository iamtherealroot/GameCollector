"""Verify the named release checksum and safely extract its matching payload."""
import ast
import hashlib
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile

directory, tag, destination = sys.argv[1:]
assert re.fullmatch(r"v\d+\.\d+\.\d+", tag)
base = f"Bibo-{tag}"
archive = Path(directory) / f"{base}.zip"
text = (Path(directory) / f"{base}-SHA256SUMS.txt").read_text()
matches = re.findall(r"(?m)^([a-fA-F0-9]{64})\s+[* ]?([^\n]+)$", text)
hashes = [value.lower() for value, name in matches if Path(name.strip()).name == archive.name]
assert len(hashes) == 1 and hashlib.sha256(archive.read_bytes()).hexdigest() == hashes[0], "Release checksum mismatch"
with zipfile.ZipFile(archive) as z:
    assert sum(i.file_size for i in z.infolist()) < 512 * 1024 * 1024
    for info in z.infolist():
        path = PurePosixPath(info.filename)
        assert path.parts and path.parts[0] == base and not path.is_absolute()
        assert ".." not in path.parts and "\\" not in info.filename
        assert not stat.S_ISLNK(info.external_attr >> 16)
    tree = ast.parse(z.read(f"{base}/app/app.py").decode())
    version = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "APP_VERSION" for t in n.targets))
    assert version == tag[1:], "Wrong payload version"
    target = Path(destination)
    assert not target.exists(), "Use a new extraction directory"
    z.extractall(target)
