"""Failure-oriented checks for context review and immutable visual corrections."""
import copy
import json
from pathlib import Path
import numpy as np
import pytest
from test_visual_annotation_v3 import make_session
from visual_annotation_v3.session import Session
from visual_annotation_v3.scene import digest
from visual_annotation_v3.revision import fork


def act(s,verb,**kwargs):
    return s.act({'action':verb,'observer':'test_fixture','reason':'Explicit synthetic evidence for protocol test',**kwargs})


def strict(root):
    root.mkdir(exist_ok=True);s=make_session(root)
    meta=json.loads((root/'scene.json').read_text());meta['annotation_protocol']='context_v1'
    (root/'scene.json').write_text(json.dumps(meta));s=Session(root)
    for name,kind in [('top','top'),('side','side'),('oblique','oblique')]:act(s,'LOOK',view_id=name,kind=kind,size=256)
    return s


def question(s,name,operation='annotate'):
    act(s,'QUESTION',question_id=name,claim='Selected segment belongs to the explicitly named operation',
        alternatives=['neighboring wire','unresolved overlap'],next_observation='Check uncropped top and oblique views',operation=operation)


def propose(s,name,box,operation='annotate',extra=()):
    question(s,name,operation)
    return act(s,'PROPOSE',candidate_id=name,question_id=name,
               selections=[{'view_id':'top','type':'box','coordinates':box},
                           {'view_id':'oblique','type':'box','coordinates':[0,0,1000,1000]}],inspection_views=list(extra))


def review(s,name,outcomes=None):
    for c in s.state['candidates'][name]['contexts']:
        outcome=(outcomes or {}).get(c['source_view_id'],'support')
        extra={};p=s.state['candidates'][name].get('patch_preview',{})
        if p.get('review_protocol')=='delta_v1':
            extra=dict(patch_sha256=p['patch_sha256'],change_outcomes={k:outcome for k in p['change_components']},
                       change_scope='entire_change_set',change_reason='Synthetic fixture: review the changed assignments separately')
        act(s,'REVIEW',candidate_id=name,view_id=c['view_id'],outcome=outcome,image_hashes=c['image_hashes'],**extra)


def confirm(s,name,instance):
    c=s.state['candidates'][name]
    return act(s,'CONFIRM',candidate_id=name,instance_id=instance,point_sha256=c['point_sha256'],reviewed_images=c['overlays'])


def survey(s):
    paths=[s.path/'views'/f'{v}.png' for v in ['top','oblique']]
    return act(s,'SURVEY',view_ids=['top','oblique'],image_hashes={str(p):digest(p) for p in paths},
               remaining_question_ids=[k for k,v in s.state.get('questions',{}).items() if v['status']!='resolved'],
               coverage_note='Synthetic whole ROI examined, including unassigned second line')


def test_context_restores_filtered_neighbor_and_reports_hidden_candidate(tmp_path):
    s=strict(tmp_path)
    restriction={'view_id':'top','type':'box','coordinates':[750,0,1000,1000]}
    act(s,'LOOK',view_id='isolated',kind='side',restrict=[restriction],size=256)
    question(s,'hidden')
    c=act(s,'PROPOSE',candidate_id='hidden',question_id='hidden',selections=[restriction,
          {'view_id':'isolated','type':'box','coordinates':[0,0,1000,1000]}])
    context=next(c for c in c['contexts'] if c['source_view_id']=='isolated')
    with np.load(tmp_path/'views'/(context['view_id']+'.npz')) as data:
        actual=np.unique(data['pixel_map']);actual=actual[actual>=0]
    assert len(actual)>0 and np.all(actual<100)  # raw front line was restored
    assert context['visible_selected_records']==0 and context['not_individually_visible_records']==100
    view=json.loads((tmp_path/'views'/(context['view_id']+'.json')).read_text())
    assert view['restrict']==[] and view['depth_range'] is None
    review(s,'hidden',{'isolated':'unobservable'})
    with pytest.raises(ValueError,match='two distinct'):confirm(s,'hidden','wire')
    act(s,'INSPECT',candidate_id='hidden',view_id='oblique')
    new=s.state['candidates']['hidden']['contexts'][-1]
    act(s,'REVIEW',candidate_id='hidden',view_id=new['view_id'],outcome='support',image_hashes=new['image_hashes'])
    confirm(s,'hidden','wire')
    assert s.state['instances']['wire']['points']==100


def test_inspection_neutrality_and_contradiction_not_mask_votes(tmp_path):
    s=strict(tmp_path);c=propose(s,'wire',[750,0,1000,1000],extra=['side'])
    before=np.load(tmp_path/'candidates/wire.npy').copy()
    with pytest.raises(ValueError,match='explicit review'):confirm(s,'wire','right')
    review(s,'wire',{'side':'unobservable'})
    assert np.array_equal(before,np.load(tmp_path/'candidates/wire.npy'))
    confirm(s,'wire','right')
    c=propose(s,'bad',[0,0,250,1000]);review(s,'bad',{'oblique':'contradict'})
    with pytest.raises(ValueError,match='contradict'):confirm(s,'bad','left')
    assert set(s.state['instances'])=={'right'}
    act(s,'REVISE',candidate_id='bad')
    assert s.state['questions']['bad']['status']=='open'


def test_review_hashes_and_survey_staleness_are_enforced(tmp_path):
    s=strict(tmp_path);c=propose(s,'left',[0,0,250,1000]);v=c['contexts'][0]
    wrong=dict(v['image_hashes']);wrong[v['raw_image']]='0'*64
    with pytest.raises(ValueError,match='hash'):act(s,'REVIEW',candidate_id='left',view_id=v['view_id'],outcome='support',image_hashes=wrong)
    with pytest.raises(ValueError,match='SURVEY'):act(s,'FINISH')
    review(s,'left');survey(s);confirm(s,'left','wire')
    with pytest.raises(ValueError,match='SURVEY'):act(s,'FINISH')
    survey(s);result=act(s,'FINISH')
    assert result['completeness']=='NOT_VERIFIED' and result['raw_scene_survey_completed']


def test_raw_survey_cannot_be_a_candidate_filtered_view(tmp_path):
    s=strict(tmp_path)
    act(s,'LOOK',view_id='filtered',kind='side',restrict=[{'view_id':'top','type':'box','coordinates':[0,0,250,1000]}])
    paths=[tmp_path/'views'/f'{n}.png' for n in ['top','filtered']]
    with pytest.raises(ValueError,match='unrestricted'):
        act(s,'SURVEY',view_ids=['top','filtered'],image_hashes={str(p):digest(p) for p in paths},remaining_question_ids=[],coverage_note='Invalid restricted observation')


def test_free_camera_keeps_orthonormal_basis_and_rejects_zoom_rotation(tmp_path):
    s=strict(tmp_path)
    act(s,'LOOK',view_id='angle',camera={'azimuth_deg':37,'elevation_deg':-28},size=256)
    meta=json.loads((tmp_path/'views/angle.json').read_text());basis=np.array(meta['basis'])
    assert np.allclose(basis@basis.T,np.eye(3))
    with pytest.raises(ValueError,match='keeps its parent'):act(s,'ZOOM',view_id='bad',parent='angle',box=[0,0,1000,1000],camera={'azimuth_deg':20,'elevation_deg':0})


def frozen_pair(root):
    s=strict(root)
    for name,box in [('left',[0,0,250,1000]),('right',[750,0,1000,1000])]:
        propose(s,name,box);review(s,name);confirm(s,name,name)
    survey(s);act(s,'FINISH');return s


def test_remove_revision_preserves_frozen_source_and_unaffected_points(tmp_path):
    base=tmp_path/'base';original=frozen_pair(base)
    hashes={n:digest(base/n) for n in ['annotation.npz','state.json','actions.jsonl']}
    dst=tmp_path/'revised';fork(base,dst);s=Session(dst)
    propose(s,'remove_tip',[0,0,250,250],operation='remove')
    preview=act(s,'PREVIEW_PATCH',candidate_id='remove_tip',mode='remove',instance_id='left')
    assert preview['removed_assignments']>0 and preview['added_assignments']==0
    assert all(c.get('removal_image') for c in preview['contexts'])
    with pytest.raises(ValueError,match='explicit review'):
        act(s,'PATCH',candidate_id='remove_tip',patch_sha256=preview['patch_sha256'],reviewed_images=s.state['candidates']['remove_tip']['overlays'])
    review(s,'remove_tip')
    contexts=s.state['candidates']['remove_tip']['contexts']
    with pytest.raises(ValueError,match='removal overlays'):
        act(s,'PATCH',candidate_id='remove_tip',patch_sha256=preview['patch_sha256'],reviewed_images=[c['overlay'] for c in contexts])
    reviewed=[c[k] for c in contexts for k in ['overlay','removal_image']]
    act(s,'PATCH',candidate_id='remove_tip',patch_sha256=preview['patch_sha256'],reviewed_images=reviewed)
    survey(s);act(s,'FINISH')
    with np.load(dst/'annotation.npz') as revised,np.load(base/'annotation.npz') as before:
        ids=np.load(dst/'candidates/remove_tip.npy')
        expected=before['instance_ids'].copy();expected[ids]=0
        assert np.array_equal(revised['instance_ids'],expected)
    assert {n:digest(base/n) for n in hashes}==hashes
    from visual_annotation_v3.replay import replay
    assert replay(dst,tmp_path/'replayed')['point_labels_identical']


def test_revision_preserves_unresolved_questions_for_final_survey(tmp_path):
    base=tmp_path/'base';s=strict(base)
    question(s,'connection')
    act(s,'UNKNOWN',question_id='connection',selection={'view_id':'top','type':'box','coordinates':[0,0,250,250]})
    survey(s);act(s,'FINISH')
    dst=tmp_path/'revised';fork(base,dst);revised=Session(dst)
    assert revised.state['questions']['connection']['status']=='deferred'
    assert revised.state['unknown']==s.state['unknown']
    paths=[dst/'views'/f'{v}.png' for v in ['top','oblique']]
    with pytest.raises(ValueError,match='every unresolved'):
        act(revised,'SURVEY',view_ids=['top','oblique'],image_hashes={str(p):digest(p) for p in paths},remaining_question_ids=[],coverage_note='Cannot discard inherited unresolved connection')
    survey(revised);result=act(revised,'FINISH')
    assert result['unresolved_questions']==['connection']


def test_reassignment_needs_explicit_source_and_preview_cannot_go_stale(tmp_path):
    base=tmp_path/'base';frozen_pair(base);dst=tmp_path/'revision';fork(base,dst);s=Session(dst)
    propose(s,'move',[750,0,1000,250],operation='add')
    with pytest.raises(ValueError,match='reassign_from'):
        act(s,'PREVIEW_PATCH',candidate_id='move',mode='add',instance_id='left')
    p=act(s,'PREVIEW_PATCH',candidate_id='move',mode='add',instance_id='left',reassign_from=['right'])
    review(s,'move')
    with pytest.raises(ValueError,match='hash'):
        act(s,'PATCH',candidate_id='move',patch_sha256='bad',reviewed_images=s.state['candidates']['move']['overlays'])
    result=act(s,'PATCH',candidate_id='move',patch_sha256=p['patch_sha256'],reviewed_images=s.state['candidates']['move']['overlays'])
    assert result['confirmed_points']==200
    assert s.state['instances']['left']['points']>100 and s.state['instances']['right']['points']<100


def test_replace_cannot_clear_beyond_reviewed_context(tmp_path):
    base=tmp_path/'base';frozen_pair(base);dst=tmp_path/'revision';fork(base,dst);s=Session(dst)
    act(s,'ZOOM',view_id='top_tip',parent='top',box=[0,0,1000,250],size=256)
    act(s,'ZOOM',view_id='oblique_tip',parent='oblique',box=[0,0,250,1000],size=256)
    question(s,'replacement','replace')
    c=act(s,'PROPOSE',candidate_id='replacement',question_id='replacement',selections=[
        {'view_id':'top_tip','type':'box','coordinates':[0,0,250,1000]},
        {'view_id':'oblique','type':'box','coordinates':[0,0,1000,1000]}])
    with pytest.raises(ValueError,match='exceed review context'):
        act(s,'PREVIEW_PATCH',candidate_id='replacement',mode='replace',instance_id='left',scope=[
            {'view_id':'top','type':'box','coordinates':[0,0,250,1000]},
            {'view_id':'oblique','type':'box','coordinates':[0,0,1000,1000]}])


def test_successful_replace_and_empty_instance_do_not_leave_phantom_labels(tmp_path):
    base=tmp_path/'base';frozen_pair(base);dst=tmp_path/'revision';fork(base,dst);s=Session(dst)
    propose(s,'replace',[0,0,250,500],operation='replace')
    scope=[{'view_id':'top','type':'box','coordinates':[0,0,250,1000]},
           {'view_id':'oblique','type':'box','coordinates':[0,0,1000,1000]}]
    p=act(s,'PREVIEW_PATCH',candidate_id='replace',mode='replace',instance_id='left',scope=scope)
    review(s,'replace');act(s,'PATCH',candidate_id='replace',patch_sha256=p['patch_sha256'],reviewed_images=s.state['candidates']['replace']['overlays'])
    assert s.state['instances']['left']['points']==50 and s.state['instances']['right']['points']==100
    propose(s,'remove_all',[0,0,250,500],operation='remove')
    p=act(s,'PREVIEW_PATCH',candidate_id='remove_all',mode='remove',instance_id='left')
    review(s,'remove_all');result=act(s,'PATCH',candidate_id='remove_all',patch_sha256=p['patch_sha256'],reviewed_images=s.state['candidates']['remove_all']['overlays'])
    assert result['confirmed_instances']==1 and set(s.state['instances'])=={'right'}
    survey(s);act(s,'FINISH')
    with np.load(dst/'annotation.npz') as a:assert np.array_equal(a['instance_ids'],np.r_[np.zeros(100),np.ones(100)])


def test_other_commit_invalidates_a_previously_reviewed_patch(tmp_path):
    base=tmp_path/'base';frozen_pair(base);dst=tmp_path/'revision';fork(base,dst);s=Session(dst)
    previews={}
    for name,target,box in [('a','left',[0,0,250,250]),('b','right',[750,0,1000,250])]:
        propose(s,name,box,operation='remove')
        previews[name]=act(s,'PREVIEW_PATCH',candidate_id=name,mode='remove',instance_id=target)
        review(s,name)
    act(s,'PATCH',candidate_id='b',patch_sha256=previews['b']['patch_sha256'],reviewed_images=s.state['candidates']['b']['overlays'])
    with pytest.raises(ValueError,match='stale'):
        act(s,'PATCH',candidate_id='a',patch_sha256=previews['a']['patch_sha256'],reviewed_images=s.state['candidates']['a']['overlays'])


def test_delta_review_needs_explicit_changed_set_decision(tmp_path):
    base=tmp_path/'base';frozen_pair(base);dst=tmp_path/'revision';fork(base,dst);s=Session(dst)
    propose(s,'tip',[0,0,250,250],operation='remove')
    c=s.state['candidates']['tip'];v=c['contexts'][0]
    with pytest.raises(ValueError,match='preview the delta'):
        act(s,'REVIEW',candidate_id='tip',view_id=v['view_id'],outcome='support',image_hashes=v['image_hashes'])
    p=act(s,'PREVIEW_PATCH',candidate_id='tip',mode='remove',instance_id='left');v=c['contexts'][0]
    assert p['review_protocol']=='delta_v1' and set(v['image_hashes'])=={v['raw_image'],v['overlay'],v['removal_image']}
    common=dict(candidate_id='tip',view_id=v['view_id'],outcome='support',image_hashes=v['image_hashes'],patch_sha256=p['patch_sha256'])
    with pytest.raises(ValueError,match='explicit delta outcomes'):act(s,'REVIEW',**common)
    with pytest.raises(ValueError,match='entire-change-set'):
        act(s,'REVIEW',**common,change_outcomes={'remove':'support'},change_scope='partial',change_reason='Only some points checked')
    assert not c['reviews']


def test_retained_points_cannot_supply_hidden_delta_support(tmp_path):
    base=tmp_path/'base';s=strict(base)
    propose(s,'left',[0,0,250,1000]);review(s,'left');confirm(s,'left','left');survey(s);act(s,'FINISH')
    dst=tmp_path/'revision';fork(base,dst);s=Session(dst);question(s,'hidden_add','add')
    c=act(s,'PROPOSE',candidate_id='hidden_add',question_id='hidden_add',selections=[
        {'view_id':v,'type':'box','coordinates':[0,0,1000,1000]} for v in ['top','side']])
    assert c['points']==200 and c['status']=='PENDING_REVIEW'
    p=act(s,'PREVIEW_PATCH',candidate_id='hidden_add',mode='add',instance_id='left')
    side=next(v for v in c['contexts'] if v['source_view_id']=='side')
    assert side['visible_selected_records']>=3  # legacy check is satisfied by retained points
    assert side['change_visibility']['add']['visible_records']==0
    assert p['added_assignments']==100
    review(s,'hidden_add')
    with pytest.raises(ValueError,match='retained points cannot provide delta support'):
        act(s,'PATCH',candidate_id='hidden_add',patch_sha256=p['patch_sha256'],reviewed_images=c['overlays'])
    assert s.state['instances']['left']['points']==100


def test_delta_contradiction_blocks_otherwise_supported_candidate(tmp_path):
    base=tmp_path/'base';frozen_pair(base);dst=tmp_path/'revision';fork(base,dst);s=Session(dst)
    propose(s,'tip',[0,0,250,250],operation='remove')
    p=act(s,'PREVIEW_PATCH',candidate_id='tip',mode='remove',instance_id='left');c=s.state['candidates']['tip']
    for i,v in enumerate(c['contexts']):
        act(s,'REVIEW',candidate_id='tip',view_id=v['view_id'],outcome='support',image_hashes=v['image_hashes'],
            patch_sha256=p['patch_sha256'],change_outcomes={'remove':'contradict' if i==0 else 'support'},
            change_scope='entire_change_set',change_reason='Synthetic removal contains a point that must remain assigned')
    with pytest.raises(ValueError,match='contradicting delta'):
        act(s,'PATCH',candidate_id='tip',patch_sha256=p['patch_sha256'],reviewed_images=c['overlays'])
    assert s.state['instances']['left']['points']==100


def test_delta_commit_rejects_projection_tampering(tmp_path):
    base=tmp_path/'base';frozen_pair(base);dst=tmp_path/'revision';fork(base,dst);s=Session(dst)
    propose(s,'tip',[0,0,250,250],operation='remove')
    p=act(s,'PREVIEW_PATCH',candidate_id='tip',mode='remove',instance_id='left')
    review(s,'tip');c=s.state['candidates']['tip']
    projection=dst/'views'/f"{c['contexts'][0]['view_id']}.npz"
    with np.load(projection) as data:fields={k:data[k].copy() for k in data.files}
    fields['pixel_map'].flat[0]=0
    np.savez_compressed(projection,**fields)
    with pytest.raises(ValueError,match='delta projection changed'):
        act(s,'PATCH',candidate_id='tip',patch_sha256=p['patch_sha256'],reviewed_images=c['overlays'])
    assert s.state['instances']['left']['points']==100
