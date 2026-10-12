"""Build a portable ZIP and SHA256 member manifest, excluding working caches."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,zipfile
ROOT=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
def keep(path):
 parts=path.relative_to(ROOT).parts
 return not any(x in ['__pycache__','.pytest_cache','.git','.venv','recording-source'] or x.endswith('.egg-info') for x in parts) and path.name!='RELEASE_MANIFEST.json' and path.suffix not in ['.zip','.las','.laz','.pyc']
files={}
for path in sorted(ROOT.rglob('*')):
 if path.is_file() and keep(path):files[path.relative_to(ROOT).as_posix()]={'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
manifest={'project':'WireSight','version':'0.2.0','built_utc':datetime.now(timezone.utc).isoformat(),'release_kind':'recorded conversation-VLM wire annotation prototype','frozen_labels_changed':False,'automatic_model_call_in_demo':False,'total_file_bytes':sum(x['bytes'] for x in files.values()),'file_count':len(files),'files':files}
(ROOT/'RELEASE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');a.out.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(a.out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for name in [*files,'RELEASE_MANIFEST.json']:z.write(ROOT/name,'WireSight-0.2.0/'+name)
with zipfile.ZipFile(a.out) as z:
 assert z.testzip() is None;assert len(z.namelist())==len(files)+1
sha=hashlib.sha256(a.out.read_bytes()).hexdigest();a.out.with_suffix('.zip.sha256').write_text(f'{sha}  {a.out.name}\n')
print(json.dumps({'zip':str(a.out),'bytes':a.out.stat().st_size,'sha256':sha,'members':len(files)+1,'uncompressed_bytes':manifest['total_file_bytes']},indent=2))
