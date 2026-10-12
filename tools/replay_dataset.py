"""Re-execute saved visual decisions from the pinned LAS; no model calls.

The full route preserves historical legacy_v0 actions and explicit instance
associations. It is execution replay, not a fresh autonomous perception run.
"""
from pathlib import Path
import argparse,json,shutil,os,hashlib,zipfile
import numpy as np
from download_data import verify,digest
from visual_annotation_v3.scene import prepare
from visual_annotation_v3.session import Session
from visual_annotation_v3.compose import compose
from visual_annotation_v3.extend import extend
ROOT=Path(__file__).resolve().parents[1]
def geometry_members(path):
 with zipfile.ZipFile(path) as archive:
  if set(archive.namelist())!={'coords.npy','record_ids.npy'}:raise ValueError('Unexpected inference geometry fields')
  hashes={}
  for name in sorted(archive.namelist()):
   h=hashlib.sha256()
   with archive.open(name) as f:
    for block in iter(lambda:f.read(1<<20),b''):h.update(block)
   hashes[name]=h.hexdigest()
  return hashes
def replay_session(las_path,name,out,cache=None):
 trace=ROOT/'examples/full_trace'/name;m=json.loads((trace/'manifest.json').read_text())
 if digest(trace/'actions.jsonl')!=m['actions_sha256']:raise ValueError('Stored trace changed')
 if out.exists():raise ValueError('Choose a new replay destination')
 cached=Path(cache)/name if cache else None
 if cached and (cached/'geometry.npz').exists():
  if digest(cached/'geometry.npz')!=m['geometry_sha256']:raise ValueError('Cached geometry differs from the recorded source')
  out.mkdir(parents=True);os.link(cached/'geometry.npz',out/'geometry.npz');meta=json.loads((cached/'scene.json').read_text());meta.update(source_las=str(las_path.resolve()),source_size=las_path.stat().st_size,source_mtime_ns=las_path.stat().st_mtime_ns)
 else:meta=prepare(las_path,*m['roi_y_offset_m'],out)
 # Historical NPZ compression changed between sessions. Verify the exact NPY
 # payloads when a fresh archive has different bytes, never weaken point checks.
 archive_matches=meta['geometry_sha256']==m['geometry_sha256']
 if not archive_matches and geometry_members(out/'geometry.npz')!=m['geometry_member_sha256']:raise ValueError('Prepared geometry differs from the recorded raw ROI')
 meta['annotation_protocol']=m['protocol'];meta.pop('patch_review_protocol',None);meta['recorded_path_prefixes']=m['recorded_path_prefixes'];(out/'scene.json').write_text(json.dumps(meta,indent=2))
 def remap(value):
  if isinstance(value,dict):return {remap(k):remap(v) for k,v in value.items()}
  if isinstance(value,list):return [remap(v) for v in value]
  if isinstance(value,str):
   for prefix in m['recorded_path_prefixes']:
    if value.startswith(prefix+'/'):return str(out)+value[len(prefix):]
  return value
 s=Session(out)
 for i,line in enumerate((trace/'actions.jsonl').read_text().splitlines(),1):
  row=json.loads(line);result=s.act(remap(row['action']))
  for key in ['point_sha256','points','selected_points','image_sha256']:
   if key in row['result'] and result.get(key)!=row['result'][key]:raise ValueError(f'{name}: diverged at action {i}: {key}')
  print(f'{name}: {i}/{m["action_count"]} {row["action"]["action"]}',flush=True)
 if not s.state['finished']:raise ValueError('Stored session did not finish')
 return {'session':name,'actions_replayed':m['action_count'],'geometry_payloads_identical':True,'geometry_archive_sha256_match':archive_matches,'reference_annotation_sha256_match':s.state['annotation_sha256']==m['reference_annotation_sha256']}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--las',type=Path);p.add_argument('--scope',choices=['roi','full'],default='roi');p.add_argument('--out',type=Path,default=Path('dataset-replay'));p.add_argument('--dry-run',action='store_true');p.add_argument('--geometry-cache',type=Path,help='Optional existing recorded geometry; every cache file must match the frozen geometry hash');a=p.parse_args();m=json.loads((ROOT/'examples/full_scene/manifest.json').read_text());trace=json.loads((ROOT/'examples/full_trace/manifest.json').read_text());names=trace['full_chain'] if a.scope=='full' else [trace['small_demo']]
 if a.dry_run:print(json.dumps({'sessions':names,'model_invoked':False,'truth_read':False,'scope':a.scope,'full_scope_resource_note':'Rendering tens of millions of points may require tens of GB of RAM and several GB of disk; start with the ROI example.'},indent=2));raise SystemExit
 if not a.las:p.error('--las is required unless --dry-run is used')
 verify(a.las,m)
 if a.out.exists():raise ValueError('Output directory must be new')
 a.out.mkdir(parents=True);reports=[]
 for name in names:reports.append(replay_session(a.las,name,a.out/name,a.geometry_cache))
 if a.scope=='roi':
  final=a.out/names[0]
  with np.load(final/'annotation.npz') as actual,np.load(ROOT/'examples/recorded_roi/annotation.npz') as expected:equal=all(np.array_equal(actual[k],expected[k]) for k in expected.files)
 else:
  base=a.out/'full_refined';compose(a.out/names[0],[a.out/names[1],a.out/names[2]],base,'Replay of stored development-scene visual decisions, not new perception or a held-out test')
  final=a.out/'full_conversation_refined';extend(base,a.out/names[3],final,trace['associations'],trace['association_reason_en'])
  with np.load(final/'annotation.npz') as actual,np.load(ROOT/m['full_prediction']) as expected:
   ids=actual['record_ids'];labels=actual['instance_ids'];positive=labels>0
   equal=len(ids)==m['scope_record_count'] and np.array_equal(ids[positive],expected['record_ids']) and np.array_equal(labels[positive],expected['instance_ids'])
 if not equal:raise ValueError('Replayed labels differ from the frozen reference')
 report={'scope':a.scope,'sessions':reports,'point_labels_identical':True,'model_invoked':False,'ground_truth_read':False,'final_run':str(final.resolve()),'meaning':'Re-executed saved visual decisions; not a model perception repeat'};(a.out/'replay_verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
