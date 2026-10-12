"""Download or verify the exact public LAS used for the wire demonstration."""
from pathlib import Path
import argparse,json,urllib.request,hashlib,os
ROOT=Path(__file__).resolve().parents[1]
def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
 return h.hexdigest()
def verify(path,m):
 if Path(path).stat().st_size!=m['source_bytes'] or digest(path)!=m['source_sha256']:raise ValueError('LAS size/SHA256 does not match the pinned dataset revision')
 return {'file':str(Path(path).resolve()),'source_sha256':m['source_sha256'],'revision':m['revision'],'verified':True}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=Path('data'));p.add_argument('--verify-existing',type=Path);a=p.parse_args();m=json.loads((ROOT/'examples/full_scene/manifest.json').read_text())
 if a.verify_existing:print(json.dumps(verify(a.verify_existing,m),indent=2));raise SystemExit
 dst=a.out/m['file'];dst.parent.mkdir(parents=True,exist_ok=True)
 if dst.exists():print(json.dumps(verify(dst,m),indent=2));raise SystemExit
 tmp=dst.with_suffix('.las.part');print(f'Downloading {m["source_bytes"]:,} bytes from pinned revision {m["revision"]}',flush=True)
 try:
  with urllib.request.urlopen(m['download_url']) as src,tmp.open('wb') as output:
   while chunk:=src.read(1<<20):output.write(chunk)
  verify(tmp,m);os.replace(tmp,dst)
 finally:
  if tmp.exists():tmp.unlink()
 print(json.dumps(verify(dst,m),indent=2))
