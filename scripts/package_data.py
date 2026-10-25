"""Create a consistent, verified data/storage archive for a private GitHub release."""
import argparse
import hashlib
import io
import json
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import store


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='zday-snapshot-') as temp:
        snapshot = Path(temp) / 'research.sqlite3'
        with store.locked():
            with sqlite3.connect(f'file:{store.HOME / "research.sqlite3"}?mode=ro', uri=True) as src:
                with sqlite3.connect(snapshot) as dst:
                    src.backup(dst)
                    assert dst.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
            files = []
            for folder in ('data', 'storage'):
                for path in sorted((ROOT / folder).rglob('*')):
                    if not path.is_file() or path.is_symlink():
                        continue
                    if path.name in ('.lock', '.DS_Store') or path.name.endswith(('-wal','-shm','.tmp')):
                        continue
                    relative = path.relative_to(ROOT).as_posix()
                    source = snapshot if relative == 'storage/research.sqlite3' else path
                    files.append((relative, source))
            manifest = {'created_at': datetime.now(timezone.utc).isoformat(),
                        'sqlite_integrity': 'quick_check: ok',
                        'files': [{'path': name, 'bytes': path.stat().st_size, 'sha256': digest(path)}
                                  for name, path in files]}
            temporary = args.output.with_suffix('.tmp')
            with tarfile.open(temporary, 'w:gz', compresslevel=6) as tar:
                for name, path in files:
                    tar.add(path, arcname=name, recursive=False)
                payload = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
                info = tarfile.TarInfo('snapshot-manifest.json'); info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
            temporary.replace(args.output)
        expected = {entry['path']: entry for entry in manifest['files']}
        with tarfile.open(args.output, 'r:gz') as tar:
            for member in tar:
                if member.name == 'snapshot-manifest.json':
                    continue
                entry = expected.pop(member.name)
                h = hashlib.sha256()
                with tar.extractfile(member) as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b''):
                        h.update(chunk)
                assert member.size == entry['bytes'] and h.hexdigest() == entry['sha256'], member.name
        assert not expected
        checksum = digest(args.output)
        args.output.with_suffix(args.output.suffix + '.sha256').write_text(f'{checksum}  {args.output.name}\n')
        print(json.dumps({'file': str(args.output), 'bytes': args.output.stat().st_size,
                          'files': len(files), 'sha256': checksum, 'verified': True}, indent=2))


if __name__ == '__main__':
    main()
