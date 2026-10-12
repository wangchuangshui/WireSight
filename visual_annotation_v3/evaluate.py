"""Independent post-freeze evaluator. Never imported by the observation agent."""
import json
from pathlib import Path
import numpy as np
from .scene import digest

def evaluate(path):
    import laspy
    root=Path(path);meta=json.loads((root/'scene.json').read_text());state=json.loads((root/'state.json').read_text())
    src=Path(meta['source_las'])
    if src.stat().st_size!=meta['source_size'] or src.stat().st_mtime_ns!=meta['source_mtime_ns']:raise ValueError('source LAS changed')
    if not state['finished'] or digest(root/'annotation.npz')!=state['annotation_sha256']:raise ValueError('freeze annotations before evaluating')
    with np.load(root/'annotation.npz') as a:record_ids=a['record_ids'];instances=a['instance_ids']
    if digest(root/'geometry.npz')!=meta['geometry_sha256']:raise ValueError('source geometry changed')
    with np.load(root/'geometry.npz') as a:
        xyz=a['coords']
        if not np.array_equal(record_ids,a['record_ids']):raise ValueError('annotation must contain every ROI raw point in source order')
    if instances.shape!=record_ids.shape or np.any(instances<0):raise ValueError('invalid instance array')
    pred=instances>0;labels=np.empty(len(record_ids),np.uint8);filled=np.zeros(len(record_ids),bool);start=0
    with laspy.open(meta['source_las']) as reader:
        for points in reader.chunk_iterator(2_000_000):
            end=start+len(points);lo=np.searchsorted(record_ids,start);hi=np.searchsorted(record_ids,end)
            if hi>lo:
                field='ground_truth' if 'ground_truth' in points.point_format.dimension_names else 'classification'
                labels[lo:hi]=np.asarray(points[field])[record_ids[lo:hi]-start];filled[lo:hi]=True
            start=end
    if not filled.all():raise ValueError('invalid original record IDs')
    positive=np.isin(labels,[5,6,7]);ignore=np.isin(labels,[12,13,255])
    def score(mask):
        tp=int(np.sum(mask&positive&pred));fp=int(np.sum(mask&~positive&pred&~ignore));fn=int(np.sum(mask&positive&~pred))
        return {'tp':tp,'fp':fp,'fn':fn,'precision_pct':100*tp/(tp+fp) if tp+fp else None,'recall_pct':100*tp/(tp+fn) if tp+fn else None,'gt_points':tp+fn,'predicted_points':int((mask&pred).sum()),'ignored_predicted_points':int((mask&pred&ignore).sum())}
    allmask=np.ones(len(labels),bool);overall=score(allmask)
    bins=[];y0,y1=meta['roi_y_absolute']
    for y in np.arange(y0,y1,10):bins.append({'offset_m':round(y-meta['scene_bounds'][0][1],3),**score((xyz[:,1]>=y)&(xyz[:,1]<min(y+10,y1)))})
    result={'source':meta['source_las'],'roi_y_offset':meta['roi_y_offset'],'roi_points':len(labels),'annotation_sha256':state['annotation_sha256'],'observer_types':sorted(set(v['observer'] for v in state['instances'].values())),'combined':overall,'class_recalls':{},'spatial_bins':bins,'instance_point_counts':{str(i):int((instances==i).sum()) for i in np.unique(instances) if i},'instance_accuracy':'NOT_EVALUATED: no independent real-scene instance truth','unknown_regions':state['unknown'],'thresholds':{'precision_pct':98,'recall_pct':90},'raw_point_gate_passed':(overall['precision_pct'] or 0)>=98 and (overall['recall_pct'] or 0)>=90,'full_scene_completed':False}
    for c in [5,6,7]:
        gt=labels==c;result['class_recalls'][str(c)]={'gt':int(gt.sum()),'tp':int((gt&pred).sum()),'recall_pct':100*int((gt&pred).sum())/int(gt.sum()) if gt.any() else None}
    result['per_class_recall_gate_passed']=all(v['gt']==0 or v['recall_pct']>=90 for v in result['class_recalls'].values())
    result['point_and_class_gate_passed']=result['raw_point_gate_passed'] and result['per_class_recall_gate_passed']
    result['thresholds']['each_present_class_recall_pct']=90
    result['development_context']=state.get('composition',{}).get('development_note','Development scene; not an independent held-out evaluation')
    hist,counts=np.unique(labels[pred&~positive],return_counts=True);result['false_positive_classes']={str(k):int(n) for k,n in zip(hist,counts)}
    result['evaluation_scope']='full_scene' if len(record_ids)==meta['scene_total_points'] and np.array_equal(record_ids,np.arange(meta['scene_total_points'])) else 'declared_ROI'
    result['unobserved_scene_points']=meta['scene_total_points']-len(record_ids)
    result['label_protocol']={'positive_classes':[5,6,7],'ignored_classes':[12,13,255],'unit':'original LAS records, no voxelization','unknown_positive_points_count_as_false_negatives':True,'undefined_precision_or_recall':None}
    usage=root/'model_usage.json'
    if usage.exists():result['local_model_run']=json.loads(usage.read_text())
    out=root/'evaluation';out.mkdir(exist_ok=True);(out/'metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    np.savez_compressed(out/'errors.npz',false_positive_record_ids=record_ids[pred&~positive&~ignore],false_negative_record_ids=record_ids[~pred&positive])
    return result

if __name__=='__main__':
    import sys
    print(json.dumps(evaluate(sys.argv[1]),ensure_ascii=False,indent=2))
