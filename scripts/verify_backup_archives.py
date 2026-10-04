#!/usr/bin/env python3
"""Read every tar member through gzip CRC, then verify extracted upload bytes."""
import gzip,hashlib,json,sys,tarfile,tempfile
from pathlib import Path

def verify(root):
    root=Path(root)
    manifest={}
    for archive in sorted(root.glob('*.tar.gz')):
        with gzip.open(archive,'rb') as stream:
            while stream.read(1024*1024):pass
        expected={}
        with tarfile.open(archive,'r:gz') as package:
            for member in package:
                path=Path(member.name)
                if path.is_absolute() or '..' in path.parts:raise ValueError('Unsicherer Archivpfad')
                if member.isfile():
                    stream=package.extractfile(member)
                    with stream:
                        expected[member.name]=hashlib.file_digest(stream,'sha256').hexdigest()
        # Code backup can contain links; upload archives may not contain links.
        if archive.name!='code.tar.gz':
            with tempfile.TemporaryDirectory(prefix='bibo-images-check-') as target:
                with tarfile.open(archive,'r:gz') as package:
                    if any(not (m.isfile() or m.isdir()) for m in package.getmembers()):raise ValueError('Upload-Archiv enthält Sonderdateien')
                    package.extractall(target,filter='data')
                for file in Path(target).rglob('*'):
                    if file.is_file():
                        with file.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
                        relative=str(file.relative_to(target))
                        if expected.get(relative)!=digest:raise ValueError('Wiederhergestellte Datei weicht vom Archiv ab')
                        manifest[f'{archive.name}:{relative}']=digest
    for file in root.iterdir():
        if file.is_file() and (file.name in {'database.sql','code.tar.gz','env.backup'} or file.name.endswith('.tar.gz')):
            with file.open('rb') as stream:manifest[file.name]=hashlib.file_digest(stream,'sha256').hexdigest()
    (root/'SHA256-manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')

if __name__=='__main__':verify(sys.argv[1])
