"""Stream the full original LAS and score the bundled frozen positive labels.

Unlisted original records have instance 0 (unconfirmed). Every target record
remains in the recall denominator; this is not selected-only evaluation.
"""
from pathlib import Path
import argparse,json,hashlib
import numpy as np
import laspy
from download_data import verify,digest
ROOT=Path(__file__).resolve().parents[1]
def evaluate(las_path,manifest_path=None,prediction_path=None):
 m=json.loads(Path(manifest_path or ROOT/'examples/full_scene/manifest.json').read_text());verify(las_path,m)
 prediction=Path(prediction_path or ROOT/m['full_prediction'])
 if digest(prediction)!=m['full_prediction_sha256']:raise ValueError('Frozen prediction changed')
 with np.load(prediction,allow_pickle=False) as a:
  if set(a.files)!={'record_ids','instance_ids'}:raise ValueError('Unexpected prediction fields')
  ids=a['record_ids'];instances=a['instance_ids']
 if ids.ndim!=1 or instances.shape!=ids.shape or not np.issubdtype(ids.dtype,np.integer) or not np.issubdtype(instances.dtype,np.integer):raise ValueError('Invalid prediction arrays')
 if len(ids)!=m['positive_record_count'] or np.any(np.diff(ids)<=0) or np.any(ids<0) or np.any(ids>=m['scope_record_count']) or np.any(instances<=0):raise ValueError('Invalid positive-record scope')
 targets=np.array(m['target_raw_classes']);ignored=np.array(m['ignored_raw_classes']);stats=np.zeros(4,np.int64);classes={str(c):[0,0] for c in targets};hist={};count=0
 with laspy.open(las_path) as reader:
  if int(reader.header.point_count)!=m['scope_record_count']:raise ValueError('Unexpected LAS record count')
  if 'ground_truth' not in reader.header.point_format.dimension_names:raise ValueError('This evaluation requires the declared ground_truth field; classification is not a substitute')
  ymin=float(reader.header.mins[1]);edges=np.arange(ymin+m['roi_y_offset_m'][0],ymin+m['roi_y_offset_m'][1],10);bins=np.zeros((len(edges),4),np.int64)
  for points in reader.chunk_iterator(2_000_000):
   end=count+len(points);lo=np.searchsorted(ids,count);hi=np.searchsorted(ids,end);pred=np.zeros(len(points),bool);pred[ids[lo:hi]-count]=True
   truth=np.asarray(points['ground_truth']);positive=np.isin(truth,targets);ignore=np.isin(truth,ignored);tp=pred&positive;fp=pred&~positive&~ignore;fn=~pred&positive;ig=pred&ignore
   stats+=np.array([tp.sum(),fp.sum(),fn.sum(),ig.sum()])
   b=np.searchsorted(edges,np.asarray(points.y),side='right')-1
   if np.any(b<0) or np.any(b>=len(edges)):raise ValueError('Record outside declared full-scene ROI')
   for j,mask in enumerate([tp,fp,fn,ig]):bins[:,j]+=np.bincount(b[mask],minlength=len(edges))
   for c in targets:
    selected=truth==c;classes[str(c)][0]+=int(selected.sum());classes[str(c)][1]+=int((selected&pred).sum())
   values,counts=np.unique(truth[pred&~positive],return_counts=True)
   for c,n in zip(values,counts):hist[str(c)]=hist.get(str(c),0)+int(n)
   count=end
 def score(x):
  tp,fp,fn,ig=map(int,x);return {'tp':tp,'fp':fp,'fn':fn,'precision_pct':100*tp/(tp+fp) if tp+fp else None,'recall_pct':100*tp/(tp+fn) if tp+fn else None,'gt_points':tp+fn,'ignored_predicted_points':ig}
 combined={**score(stats),'predicted_points':len(ids)}
 result={'scope':'all original records in t1z5b','raw_record_count':count,'source_sha256':m['source_sha256'],'prediction_sha256':m['full_prediction_sha256'],'model_invoked':False,'unknown_targets_count_as_false_negatives':True,'development_scene':True,'combined':combined,'class_recalls':{k:{'gt':v[0],'tp':v[1],'recall_pct':100*v[1]/v[0] if v[0] else None} for k,v in classes.items()},'spatial_bins':[{'offset_m':round(float(y-ymin),3),**score(x)} for y,x in zip(edges,bins)],'false_positive_classes':hist,'instance_point_counts':{str(i):int((instances==i).sum()) for i in np.unique(instances)},'instance_accuracy':'NOT_EVALUATED: no independent instance truth'}
 reference=json.loads((ROOT/'evidence/metrics.json').read_text());equal=all(result['combined'][k]==reference['combined'][k] for k in ['tp','fp','fn','precision_pct','recall_pct','gt_points','predicted_points','ignored_predicted_points'])
 result['matches_published_combined_metrics']=equal
 if not equal:raise ValueError('Recomputed point metrics differ from the published frozen result')
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--las',type=Path,required=True);p.add_argument('--out',type=Path,default=Path('full-scene-metrics.json'));a=p.parse_args();r=evaluate(a.las);a.out.write_text(json.dumps(r,indent=2));print(json.dumps({k:v for k,v in r.items() if k not in ['spatial_bins','class_recalls','false_positive_classes']},indent=2))
