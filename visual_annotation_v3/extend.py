"""Add reviewed points to explicitly associated instances; never infer a link.

Both inputs must be frozen. Raw-record overlap is allowed only within the
observer-specified instance identity. Existing predictions are never removed.
"""
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import numpy as np
from .compose import _read
from .scene import digest, save_archive


def _manifest(root):
    return {'path': str(root), **{name+'_sha256': digest(root/name)
        for name in ['geometry.npz','annotation.npz','state.json','actions.jsonl']}}


def _union(base, child, associations):
    scene, state, labels = base
    small, local_state, local_labels = child
    if set(associations) != set(local_state['instances']):
        raise ValueError('explicit association required for every refinement instance')
    identity = ['source_las','source_size','source_mtime_ns','scene_total_points']
    if any(scene.meta[k] != small.meta[k] for k in identity):
        raise ValueError('source LAS identity mismatch')
    numbers = {name:i for i,name in enumerate(sorted(state['instances']),1)}
    result = labels.copy(); contributions = {}
    for i,name in enumerate(sorted(local_state['instances']),1):
        target_name = associations[name]
        if target_name not in numbers:
            raise ValueError('association must name an existing base instance')
        local = np.flatnonzero(local_labels == i)
        mapped = np.searchsorted(scene.record_ids,small.record_ids[local])
        if np.any(mapped>=len(scene.record_ids)) or not np.array_equal(scene.record_ids[mapped],small.record_ids[local]):
            raise ValueError('refinement outside base raw-record coverage')
        if not np.array_equal(scene.coords[mapped],small.coords[local]):
            raise ValueError('refinement geometry mismatch')
        target = numbers[target_name]
        if np.any((result[mapped]!=0)&(result[mapped]!=target)):
            raise ValueError('association conflicts with another confirmed instance')
        added = int(np.sum(result[mapped]==0))
        contributions[name] = {'target_instance':target_name,
            'candidate_id':local_state['instances'][name]['candidate_id'],
            'new_points':added,'already_confirmed_points':len(mapped)-added}
        result[mapped] = target
    return result, contributions


def extend(base, refinement, destination, associations, reason, reviewed_images=()):
    if not reason.strip():raise ValueError('visual association reason required')
    base_root=Path(base).resolve(); child_root=Path(refinement).resolve()
    out=Path(destination).resolve()
    if out.exists():raise ValueError('choose a fresh output directory')
    original=_read(base_root); child=_read(child_root)
    labels,contributions=_union(original,child,associations)
    scene,state,base_labels=original
    state=copy.deepcopy(state)
    sources=[_manifest(base_root),_manifest(child_root)]
    out.mkdir(parents=True); (out/'candidates').mkdir()
    os.link(base_root/'geometry.npz',out/'geometry.npz')
    shutil.copy2(base_root/'scene.json',out/'scene.json')
    shutil.copytree(base_root/'views',out/'views')
    for number,name in enumerate(sorted(state['instances']),1):
        instance=state['instances'][name];candidate=state['candidates'][instance['candidate_id']]
        selected=np.flatnonzero(labels==number)
        np.save(out/'candidates'/(instance['candidate_id']+'.npy'),selected)
        point_hash=hashlib.sha256(scene.record_ids[selected].tobytes()).hexdigest()
        evidence=[{'session':str(base_root),'instance':name,'candidate':instance['candidate_id']}]
        overlays=[]
        for old in candidate['overlays']:
            dst=out/'candidates'/('base_'+Path(old).name)
            shutil.copy2(base_root/'candidates'/Path(old).name,dst);overlays.append(str(dst))
        for local,target in associations.items():
            if target!=name:continue
            c_id=child[1]['instances'][local]['candidate_id'];c=child[1]['candidates'][c_id]
            evidence.append({'session':str(child_root),'instance':local,'candidate':c_id,
                             'visual_association_reason':reason})
            for old in c['overlays']:
                dst=out/'candidates'/('refinement_'+Path(old).name)
                shutil.copy2(child_root/'candidates'/Path(old).name,dst);overlays.append(str(dst))
        candidate.update(points=len(selected),point_sha256=point_hash,overlays=overlays,
                         evidence_parts=evidence,selection_coordinates_belong_to='see evidence_parts; original camera frames preserved')
        instance.update(points=len(selected),point_sha256=point_hash)
        if len(evidence)>1:instance['reason']+=' '+reason
    # These are historical unresolved observations, not claims that all remain
    # unresolved after the new visual pass. Full-record evaluation is authoritative.
    state['unknown'] += [{**u,'evidence_session':str(child_root)} for u in child[1]['unknown']]
    image_hashes={str(Path(p).resolve()):digest(p) for p in reviewed_images}
    state['extension']={'sources':sources,'associations':associations,'observer':'conversation_vlm',
        'reviewed_reference_images':image_hashes,
        'reason':reason,'ground_truth_read':False,'contributions':contributions,
        'base_confirmed_points':int((base_labels>0).sum()),'added_points':int(((labels>0)&(base_labels==0)).sum())}
    state.setdefault('composition',{})['development_note']='Evaluation-directed conversation visual refinement; explicit instance association, no GT point IDs or local model used. Not held-out.'
    save_archive(out/'annotation.npz',record_ids=scene.record_ids,instance_ids=labels)
    state['annotation_sha256']=digest(out/'annotation.npz')
    (out/'state.json').write_text(json.dumps(state,ensure_ascii=False,indent=2))
    result={'selected_points':int((labels>0).sum()),'added_points':state['extension']['added_points'],
            'instances':len(state['instances']),'annotation_sha256':state['annotation_sha256']}
    action={'action':'EXTEND','observer':'conversation_vlm','reason':reason,
            'sources':sources,'associations':associations,'reviewed_reference_images':image_hashes}
    (out/'actions.jsonl').write_text(json.dumps({'timestamp':datetime.now(timezone.utc).isoformat(),
                                               'action':action,'result':result},ensure_ascii=False)+'\n')
    return result


def verify(path):
    root=Path(path).resolve(); scene,state,actual=_read(root)
    info=state['extension']; sources=info['sources']
    for item in sources:
        source=Path(item['path'])
        if _manifest(source)!=item:raise ValueError('frozen source changed')
    if any(digest(p)!=h for p,h in info.get('reviewed_reference_images',{}).items()):
        raise ValueError('association reference image changed')
    expected,contributions=_union(_read(sources[0]['path']),_read(sources[1]['path']),info['associations'])
    if not np.array_equal(actual,expected) or contributions!=info['contributions']:
        raise ValueError('extension differs from explicitly associated frozen inputs')
    result={'point_labels_identical':True,'raw_records':len(actual),
            'selected_points':int((actual>0).sum()),'ground_truth_read':False}
    (root/'extension_verification.json').write_text(json.dumps(result,indent=2))
    return result
