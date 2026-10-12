"""Conversation evidence contracts. No model calls, tracing, or inferred answers."""
from pathlib import Path
import numpy as np
from .observation import render, read_view, overlay
from .scene import digest


def enabled(session):
    return session.state.get('protocol')=='context_v1'


def independent(views):
    return len(views)>=2 and max(np.degrees(np.arccos(np.clip(abs(np.dot(a['basis'][2],b['basis'][2])),0,1))) for a in views for b in views)>=20


def check_images(expected, supplied):
    if set(expected)!=set(supplied):raise ValueError('review must reference exact raw and overlay image hashes')
    if any(digest(p)!=h or supplied[p]!=h for p,h in expected.items()):raise ValueError('review image changed or hash mismatch')


def inspect(session, candidate_id, view_id):
    candidate=session.state['candidates'][candidate_id]
    if candidate['status']!='PENDING_REVIEW':raise ValueError('inspect a pending candidate')
    if candidate.get('patch_preview'):raise ValueError('inspect all needed views before creating the patch preview')
    original=read_view(session.scene,view_id)
    context_id=f'context_{candidate_id}_{len(candidate.get("contexts",[])):02d}'
    radius=max(2,original.get('point_radius_px',1)) if session.state.get('patch_review_protocol')=='delta_v1' else 1
    meta=render(session.scene,context_id,size=original['size'],context_of=original,color_mode=original.get('color_mode','height'),point_radius_px=radius)
    ids=np.load(session.path/'candidates'/f'{candidate_id}.npy')
    mask=np.zeros(len(session.scene.coords),bool);mask[ids]=True
    raw=str(session.path/'views'/f'{context_id}.png');paint=str(session.path/'candidates'/f'{candidate_id}_{context_id}.png')
    visibility=overlay(session.scene,meta,mask,paint,visibility_aware=True,point_radius_px=radius)
    item={'view_id':context_id,'source_view_id':view_id,'raw_image':raw,'overlay':paint,
          'image_hashes':{raw:digest(raw),paint:digest(paint)},**visibility}
    candidate.setdefault('contexts',[]).append(item)
    candidate['overlays'].append(paint)
    candidate.setdefault('overlay_metadata',[]).append({'path':paint,'view_id':context_id,'role':'unfiltered_context',**visibility})
    return item


def validate_commit(session, candidate, action):
    if not enabled(session):return
    hypothesis=session.state['questions'][candidate['question_id']]
    if hypothesis['status'] not in ['open','contradicted','deferred']:raise ValueError('candidate question is no longer open')
    reviews=candidate.get('reviews',{})
    contexts=candidate.get('contexts',[])
    if not contexts or set(reviews)!={c['view_id'] for c in contexts}:raise ValueError('all unfiltered context views need an explicit review')
    supported=[]
    for c in contexts:
        r=reviews[c['view_id']];check_images(c['image_hashes'],r['image_hashes'])
        if r['outcome']=='contradict':raise ValueError('contradicting context requires a revised candidate')
        if r['outcome']=='support' and c['visible_selected_records']>=3:supported.append(read_view(session.scene,c['view_id']))
    if not independent(supported):raise ValueError('need supported unfiltered context from two distinct directions; unobservable is neutral')


def changed(session):
    session.state['annotation_revision']=session.state.get('annotation_revision',0)+1


def handle(session, action):
    if not enabled(session):raise ValueError('new evidence actions require context_v1 protocol')
    state=session.state;verb=action['action']
    if verb=='QUESTION':
        name=action['question_id']
        if not isinstance(name,str) or not name or name in state.setdefault('questions',{}):raise ValueError('fresh question ID required')
        if not action.get('claim') or not action.get('next_observation'):raise ValueError('question needs a claim and a discriminating next observation')
        operation=action.get('operation','annotate')
        if operation not in ['annotate','add','remove','replace']:raise ValueError('invalid question operation')
        item={'claim':action['claim'],'alternatives':action.get('alternatives',[]),'subjects':action.get('subjects',[]),
              'next_observation':action['next_observation'],'operation':operation,'status':'open','history':[]}
        state['questions'][name]=item
        return {'question_id':name,**item}
    if verb=='INSPECT':return inspect(session,action['candidate_id'],action['view_id'])
    if verb=='REVIEW':
        candidate=state['candidates'][action['candidate_id']]
        if candidate['status']!='PENDING_REVIEW':raise ValueError('review a pending candidate')
        views={v['view_id']:v for v in candidate['contexts']};view=views.get(action['view_id'])
        if view is None:raise ValueError('review must name an unfiltered context view')
        outcome=action['outcome']
        if outcome not in ['support','contradict','unobservable']:raise ValueError('invalid evidence outcome')
        if action['view_id'] in candidate.setdefault('reviews',{}):raise ValueError('review is immutable; inspect a new view or revise the candidate')
        operation=state['questions'][candidate['question_id']]['operation']
        if state.get('patch_review_protocol')=='delta_v1' and operation!='annotate':
            preview=candidate.get('patch_preview')
            if not preview or preview.get('review_protocol')!='delta_v1':raise ValueError('preview the delta before reviewing a correction')
            if action.get('patch_sha256')!=preview['patch_sha256']:raise ValueError('delta review must reference the exact preview hash')
            outcomes=action.get('change_outcomes',{})
            if set(outcomes)!=set(preview['change_components']) or any(o not in ['support','contradict','unobservable'] for o in outcomes.values()):
                raise ValueError('explicit delta outcomes required for every change component')
            if action.get('change_scope')!='entire_change_set' or not isinstance(action.get('change_reason'),str) or not action['change_reason'].strip():
                raise ValueError('delta review needs an entire-change-set decision and a semantic boundary reason')
        check_images(view['image_hashes'],action.get('image_hashes',{}))
        record={k:action[k] for k in ['view_id','outcome','reason','image_hashes']}
        if state.get('patch_review_protocol')=='delta_v1' and operation!='annotate':
            record.update({k:action[k] for k in ['patch_sha256','change_outcomes','change_scope','change_reason']})
        candidate['reviews'][action['view_id']]=record
        question=state['questions'][candidate['question_id']]
        question['history'].append({'candidate_id':action['candidate_id'],**record})
        if outcome=='contradict':question['status']='contradicted'
        return {'candidate_id':action['candidate_id'],'question_id':candidate['question_id'],**record,
                'selected_points_unchanged':candidate['points']}
    if verb=='SURVEY':
        view_ids=action.get('view_ids',[]);views=[read_view(session.scene,v) for v in view_ids]
        if not independent(views):raise ValueError('survey needs two distinct full-scene directions')
        for v in views:
            if v.get('restrict') or v.get('depth_range') is not None or v.get('parent') or v.get('context_of'):
                raise ValueError('survey must use unrestricted full-ROI observations')
        expected={str(session.path/'views'/f'{v}.png'):read_view(session.scene,v)['image_sha256'] for v in view_ids}
        check_images(expected,action.get('image_hashes',{}))
        remaining=action.get('remaining_question_ids')
        open_ids={k for k,v in state.get('questions',{}).items() if v['status']!='resolved'}
        if not isinstance(remaining,list) or set(remaining)!=open_ids:raise ValueError('survey must disclose every unresolved question')
        if not isinstance(action.get('coverage_note'),str) or not action['coverage_note'].strip():raise ValueError('survey needs a scene coverage observation')
        result={'view_ids':view_ids,'image_hashes':expected,'remaining_question_ids':remaining,
                'coverage_note':action['coverage_note'],'annotation_revision':state.get('annotation_revision',0),
                'scope':'entire declared ROI; observer statement, not an independent completeness test'}
        state.setdefault('surveys',[]).append(result)
        return result
    raise ValueError('unsupported evidence action')


def finish(session):
    if not enabled(session):return {}
    surveys=session.state.get('surveys',[])
    if not surveys or surveys[-1]['annotation_revision']!=session.state.get('annotation_revision',0):
        raise ValueError('perform a raw-scene SURVEY after the last annotation change')
    remaining={k for k,v in session.state.get('questions',{}).items() if v['status']!='resolved'}
    if set(surveys[-1]['remaining_question_ids'])!=remaining:raise ValueError('survey is stale; unresolved questions changed')
    result={'protocol':'context_v1','unresolved_questions':sorted(remaining),'raw_scene_survey_completed':True,
            'completeness':'NOT_VERIFIED','unknown_points_are_not_background':True}
    session.state['observation_acceptance']=result
    return result
