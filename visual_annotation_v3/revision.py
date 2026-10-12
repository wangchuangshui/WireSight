"""Versioned visual corrections with a reviewed change preview; never read GT."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import numpy as np
from .compose import _read
from .scene import digest
from .observation import selection_mask,read_view,project,overlay
from . import review_protocol


def fork(source,destination,delta_review=True):
    src=Path(source).resolve();dst=Path(destination).resolve()
    if dst.exists():raise ValueError('revision destination must be new')
    _,state,_=_read(src)
    dst.mkdir()
    os.link(src/'geometry.npz',dst/'geometry.npz')
    meta=json.loads((src/'scene.json').read_text());meta['annotation_protocol']='context_v1'
    meta['patch_review_protocol']='delta_v1' if delta_review else 'legacy_patch_v1'
    (dst/'scene.json').write_text(json.dumps(meta,indent=2))
    for name in ['views','measurements','candidates']:
        if (src/name).exists():shutil.copytree(src/name,dst/name)
    state=copy.deepcopy(state)
    state.setdefault('questions',{})
    state['patch_review_protocol']=meta['patch_review_protocol']
    state.update(finished=False,protocol='context_v1',surveys=[],annotation_revision=0,
                 revision_base={'path':str(src),'annotation_sha256':state['annotation_sha256'],
                                'state_sha256':digest(src/'state.json'),'actions_sha256':digest(src/'actions.jsonl'),
                                'initial_points':sum(v['points'] for v in state['instances'].values()),
                                'initial_instances':len(state['instances'])})
    state.pop('annotation_sha256',None)
    # Old composition and extension refer to the immutable source, not this
    # revision. Preserve them there instead of incorrectly replaying them twice.
    for key in ['composition','extension','observation_acceptance']:state.pop(key,None)
    (dst/'state.json').write_text(json.dumps(state,ensure_ascii=False,indent=2))
    return state['revision_base']


def _plan(session,candidate_id,spec):
    candidate=session.state['candidates'][candidate_id]
    target=spec['instance_id'];mode=spec['mode']
    if target not in session.state['instances']:raise ValueError('patch target must be an existing instance')
    question=session.state['questions'][candidate['question_id']]
    if mode not in ['add','remove','replace'] or question['operation']!=mode:raise ValueError('patch mode must match its visual question')
    selected=np.load(session.path/'candidates'/f'{candidate_id}.npy')
    if hashlib.sha256(session.scene.record_ids[selected].tobytes()).hexdigest()!=candidate['point_sha256']:raise ValueError('candidate points changed')
    old={}
    for name,instance in session.state['instances'].items():
        ids=np.load(session.path/'candidates'/f"{instance['candidate_id']}.npy")
        if hashlib.sha256(session.scene.record_ids[ids].tobytes()).hexdigest()!=instance['point_sha256']:raise ValueError('existing instance changed')
        old[name]=ids
    after={k:v.copy() for k,v in old.items()}
    transferred={name:np.intersect1d(ids,selected) for name,ids in old.items() if name!=target}
    conflicts={name for name,ids in transferred.items() if len(ids)}
    if set(spec.get('reassign_from',[]))!=conflicts:raise ValueError('conflicting instances require exact explicit reassign_from approval')
    if mode=='remove':
        if conflicts or not np.isin(selected,old[target]).all():raise ValueError('removal must name points of its target instance')
        after[target]=np.setdiff1d(old[target],selected)
    else:
        for name in conflicts:after[name]=np.setdiff1d(old[name],selected)
        if mode=='replace':
            selections=spec.get('scope',[]);views=[read_view(session.scene,s['view_id']) for s in selections]
            if not review_protocol.independent(views):raise ValueError('replace requires an explicit bounded scope in two directions')
            mask=np.ones(len(session.scene.coords),bool)
            for v,s in zip(views,selections):mask&=selection_mask(session.scene,v,s)
            if not mask[selected].all():raise ValueError('replacement points outside declared scope')
            after[target]=old[target][~mask[old[target]]]
        after[target]=np.union1d(after[target],selected)
    removed=np.unique(np.concatenate([np.setdiff1d(old[n],after[n]) for n in old]))
    added=np.unique(np.concatenate([np.setdiff1d(after[n],old[n]) for n in old]))
    changed=np.union1d(removed,added)
    if not len(changed):raise ValueError('patch makes no change')
    fingerprint={'candidate_sha256':candidate['point_sha256'],'spec':spec,
                 'before':{name:session.state['instances'][name]['point_sha256'] for name in sorted(old)}}
    sha=hashlib.sha256(json.dumps(fingerprint,sort_keys=True).encode()).hexdigest()
    return old,after,removed,added,changed,sha


def _visibility(session, view, indices):
    with np.load(session.path/'views'/f"{view['view_id']}.npz") as data:
        visible=np.unique(data['pixel_map']);visible=visible[visible>=0]
    seen=np.intersect1d(indices,visible)
    return {'records':len(indices),'visible_records':len(seen),
            'not_individually_visible_records':len(indices)-len(seen),
            'visible_record_ids_sha256':hashlib.sha256(session.scene.record_ids[seen].tobytes()).hexdigest()}


def _delta_contexts(session, name, candidate, old, after, removed, added):
    """Separate retained assignments from the additions/removals being approved."""
    target=candidate['patch_preview']['spec']['instance_id']
    retained=np.intersect1d(old[target],after[target])
    for c in candidate['contexts']:
        v=read_view(session.scene,c['view_id']);uv,_=project(session.scene,v)
        c['proposal_overlay']=c['overlay']
        c['image_hashes']={c['raw_image']:digest(c['raw_image'])}
        c['change_visibility']={}
        c['projection_sha256']=digest(session.path/'views'/f"{v['view_id']}.npz")
        for role,indices,color in [('retained',retained,(40,160,235)),('add',added,(0,230,100)),('remove',removed,(235,60,210))]:
            if role!='retained' and not len(indices):continue
            mask=np.zeros(len(session.scene.coords),bool);mask[indices]=True
            if role=='retained':mask&=np.all((uv>=0)&(uv<=v['size']-1),axis=1)
            path=str(session.path/'candidates'/f'{name}_{v["view_id"]}_delta_{role}.png')
            info=overlay(session.scene,v,mask,path,color=color,visibility_aware=True,point_radius_px=max(2,v.get('point_radius_px',1)))
            field={'retained':'overlay','add':'addition_image','remove':'removal_image'}[role]
            c[field]=path;c['image_hashes'][path]=digest(path)
            candidate['overlays'].append(path)
            candidate['overlay_metadata'].append({'path':path,'view_id':v['view_id'],
                'role':{'retained':'patch_retained','add':'patch_additions','remove':'patch_removals'}[role],**info})
            if role!='retained':c['change_visibility'][role]=_visibility(session,v,indices)


def validate_delta_commit(session, candidate, action, removed, added):
    preview=candidate['patch_preview']
    if preview.get('review_protocol')!='delta_v1':return
    components={role:indices for role,indices in [('add',added),('remove',removed)] if len(indices)}
    for role,indices in components.items():
        supported=[]
        for c in candidate['contexts']:
            review=candidate['reviews'][c['view_id']]
            view=read_view(session.scene,c['view_id'])
            if digest(session.path/'views'/f"{view['view_id']}.npz")!=c['projection_sha256']:
                raise ValueError('delta projection changed since preview')
            if _visibility(session,view,indices)!=c['change_visibility'][role]:
                raise ValueError('delta visibility changed since preview')
            outcome=review['change_outcomes'][role]
            if outcome=='contradict':raise ValueError('contradicting delta requires a revised candidate')
            if review['outcome']=='support' and outcome=='support' and c['change_visibility'][role]['visible_records']>=min(3,len(indices)):
                supported.append(view)
        if not review_protocol.independent(supported):
            raise ValueError(f'need supported {role} delta in two distinct directions; retained points cannot provide delta support')


def preview(session,action):
    if not review_protocol.enabled(session):raise ValueError('patch preview requires context_v1')
    name=action['candidate_id'];candidate=session.state['candidates'][name]
    if candidate['status']!='PENDING_REVIEW' or candidate.get('reviews') or candidate.get('patch_preview'):
        raise ValueError('preview corrections before reviewing a fresh pending candidate')
    spec={k:action[k] for k in ['mode','instance_id','scope','reassign_from'] if k in action}
    old,after,removed,added,changed,sha=_plan(session,name,spec)
    coverage=[]
    for c in candidate['contexts']:
        v=read_view(session.scene,c['view_id']);uv,_=project(session.scene,v)
        if np.all((uv[changed]>=0)&(uv[changed]<=v['size']-1)):coverage.append(v)
    if not review_protocol.independent(coverage):raise ValueError('changed points exceed review context; INSPECT wider views before preview')
    record={'spec':spec,'patch_sha256':sha,'added_assignments':len(added),'removed_assignments':len(removed),
            'net_selected_change':sum(map(len,after.values()))-sum(map(len,old.values())),
            'scope':'only explicitly named instances and points; magenta marks revoked assignments'}
    candidate['patch_preview']=record
    if session.state.get('patch_review_protocol')=='delta_v1':
        record['review_protocol']='delta_v1'
        record['change_components']=[role for role,indices in [('add',added),('remove',removed)] if len(indices)]
        _delta_contexts(session,name,candidate,old,after,removed,added)
    else:
        removal_mask=np.zeros(len(session.scene.coords),bool);removal_mask[removed]=True
        for c in candidate['contexts']:
            if not len(removed):continue
            v=read_view(session.scene,c['view_id']);path=str(session.path/'candidates'/f"{name}_{c['view_id']}_removed.png")
            info=overlay(session.scene,v,removal_mask,path,color=(235,60,210),visibility_aware=True)
            c['removal_image']=path;c['image_hashes'][path]=digest(path)
            candidate['overlays'].append(path)
            candidate['overlay_metadata'].append({'path':path,'view_id':v['view_id'],'role':'patch_removals',**info})
    record['contexts']=copy.deepcopy(candidate['contexts'])
    return record


def patch(session,action):
    name=action['candidate_id'];candidate=session.state['candidates'][name]
    if candidate['status']!='PENDING_REVIEW':raise ValueError('patch requires a pending candidate')
    p=candidate.get('patch_preview')
    if not p or action.get('patch_sha256')!=p['patch_sha256']:raise ValueError('approve the exact patch preview hash')
    review_protocol.validate_commit(session,candidate,action)
    required={c[k] for c in candidate['contexts'] for k in ['overlay','addition_image','removal_image'] if k in c}
    if not required.issubset(action.get('reviewed_images',[])):raise ValueError('review retained, addition and removal overlays before committing')
    old,after,removed,added,changed,sha=_plan(session,name,p['spec'])
    if sha!=p['patch_sha256']:raise ValueError('patch preview became stale')
    validate_delta_commit(session,candidate,action,removed,added)
    updates=[]
    for i,instance_name in enumerate(sorted(after)):
        if np.array_equal(old[instance_name],after[instance_name]):continue
        original=session.state['instances'][instance_name]
        derived=f"patch_{session.state.get('annotation_revision',0)+1}_{i}_{name}"
        if derived in session.state['candidates']:raise ValueError('derived candidate ID conflict')
        point_hash=hashlib.sha256(session.scene.record_ids[after[instance_name]].tobytes()).hexdigest()
        item=copy.deepcopy(candidate)
        item.update(status='CONFIRMED',points=len(after[instance_name]),point_sha256=point_hash,
                    evidence_parts=[{'base_candidate':original['candidate_id']},{'patch_candidate':name,'patch_sha256':sha}],
                    selection_coordinates_belong_to='patch delta only; complete instance reconstructed from evidence_parts')
        updates.append((instance_name,derived,item,point_hash))
    for instance_name,derived,item,point_hash in updates:
        np.save(session.path/'candidates'/f'{derived}.npy',after[instance_name])
        session.state['candidates'][derived]=item
        if len(after[instance_name]):session.state['instances'][instance_name].update(candidate_id=derived,points=len(after[instance_name]),point_sha256=point_hash,observer=action['observer'],reason=action['reason'])
        else:session.state['instances'].pop(instance_name)
    candidate['status']='APPLIED_PATCH'
    session.state['questions'][candidate['question_id']]['status']='resolved'
    review_protocol.changed(session)
    result={'patch_sha256':sha,'mode':p['spec']['mode'],'instance_id':p['spec']['instance_id'],
            'added_assignments':len(added),'removed_assignments':len(removed),
            'confirmed_points':sum(map(len,after.values())),'confirmed_instances':len(session.state['instances']),
            'instance_counts':{n:v['points'] for n,v in session.state['instances'].items()},
            'instance_candidates':{n:v['candidate_id'] for n,v in session.state['instances'].items()},
            'annotation_revision':session.state['annotation_revision'],'source_version_unchanged':True}
    session.state.setdefault('patches',[]).append(result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('destination');a=p.parse_args()
    print(json.dumps(fork(a.source,a.destination),ensure_ascii=False,indent=2))
