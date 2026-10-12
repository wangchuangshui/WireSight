"""Create an image handoff for a capable observer, without exposing truth."""
import argparse,json
from pathlib import Path
from visual_annotation_v3.scene import Scene
p=argparse.ArgumentParser(description=__doc__);p.add_argument('run');a=p.parse_args();scene=Scene(a.run)
state_path=scene.path/'state.json';state=json.loads(state_path.read_text()) if state_path.exists() else {}
views=[]
for meta_path in sorted((scene.path/'views').glob('*.json')):
 v=json.loads(meta_path.read_text());views.append({k:v.get(k) for k in ['view_id','kind','basis','extent','image_sha256','depth_range','restrict']})
 views[-1]['image']=str((meta_path.with_suffix('.png')).resolve())
contexts=[]
for name,c in state.get('candidates',{}).items():
 if c['status']=='PENDING_REVIEW':contexts.append({'candidate_id':name,'point_sha256':c['point_sha256'],'contexts':c.get('contexts',[]),'reviews':c.get('reviews',{})})
print(json.dumps({'task':'Wire annotation: discover and associate visible cables through multiview image inspection. Request views/zooms, explicitly select image regions, and judge support/contradiction/unobservable. Do not use semantic truth or automatically trace geometry.','mode':'observer handoff; no model call made','original_roi_points':len(scene.record_ids),'protocol':scene.meta.get('annotation_protocol','legacy_v0'),'finished':state.get('finished',False),'views':views,'pending_reviews':contexts,'unresolved_questions':{k:v for k,v in state.get('questions',{}).items() if v['status']!='resolved'},'next':'Actually inspect these images. Submit a new action JSON with session act; follow docs/OBSERVER_GUIDE.md.'},ensure_ascii=False,indent=2))
