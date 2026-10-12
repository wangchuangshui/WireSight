"""Verify packaged file hashes and fail on missing or changed release assets."""
from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parents[1];manifest=json.loads((root/'RELEASE_MANIFEST.json').read_text());checked=0
for name,row in manifest['files'].items():
 path=root/name
 if not path.resolve().is_relative_to(root):raise ValueError('Manifest path escapes release root')
 if not path.is_file():raise ValueError('Missing file: '+name)
 if path.stat().st_size!=row['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('Changed file: '+name)
 checked+=1
print(json.dumps({'verified_files':checked,'all_packaged_hashes_match':True,'version':manifest['version']},indent=2))
