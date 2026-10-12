"""Adversarial contracts: geometry support never substitutes for model confirmation."""
import json
from pathlib import Path
import numpy as np
import pytest
from visual_annotation_v3.scene import digest
from visual_annotation_v3.session import Session




def make_session(tmp_path):
    y=np.linspace(.1,19.9,100);a=np.column_stack([np.zeros(100),y,np.full(100,15)])
    pts=np.vstack([a,a+[4,0,0]])
    np.savez_compressed(tmp_path/'geometry.npz',coords=pts,record_ids=np.arange(len(pts)))
    (tmp_path/'scene.json').write_text(json.dumps({'geometry_sha256':digest(tmp_path/'geometry.npz')}))
    return Session(tmp_path)

def test_model_confirmation_required_and_single_view_rejected(tmp_path):
    s=make_session(tmp_path)
    s.act({'action':'LOOK','view_id':'s','kind':'side','observer':'test','reason':'initial'})
    with pytest.raises(ValueError,match='two observed'):
        s.act({'action':'PROPOSE','candidate_id':'one','observer':'test','reason':'one','selections':[{'view_id':'s','type':'box','coordinates':[0,0,1000,1000]}]})
    assert not s.state['instances']
    s.act({'action':'LOOK','view_id':'t','kind':'top','observer':'test','reason':'resolve depth'})
    out=s.act({'action':'PROPOSE','candidate_id':'first','observer':'test','reason':'two masks','selections':[{'view_id':'s','type':'box','coordinates':[0,0,1000,1000]},{'view_id':'t','type':'box','coordinates':[0,0,250,1000]}]})
    assert out['points']==100
    assert not s.state['instances']
    with pytest.raises(ValueError,match='hash'):
        s.act({'action':'CONFIRM','candidate_id':'first','instance_id':'w','observer':'test','reason':'checked'})
    s.act({'action':'CONFIRM','candidate_id':'first','instance_id':'w','point_sha256':out['point_sha256'],'reviewed_images':out['overlays'],'observer':'test','reason':'checked'})
    assert s.state['instances']['w']['points']==100

def test_parallel_views_do_not_resolve_depth(tmp_path):
    s=make_session(tmp_path)
    for name in ['a','b']:s.act({'action':'LOOK','view_id':name,'kind':'side','observer':'test','reason':'view'})
    with pytest.raises(ValueError,match='do not resolve depth'):
        s.act({'action':'PROPOSE','candidate_id':'x','observer':'test','reason':'same view twice','selections':[{'view_id':n,'type':'box','coordinates':[0,0,1000,1000]} for n in ['a','b']]})

def test_image_tampering_is_rejected(tmp_path):
    s=make_session(tmp_path);s.act({'action':'LOOK','view_id':'a','kind':'side','observer':'test','reason':'view'})
    with (tmp_path/'views/a.png').open('ab') as f:f.write(b'tampered')
    with pytest.raises(ValueError,match='image changed'):
        s.act({'action':'ZOOM','view_id':'b','parent':'a','box':[0,0,1000,1000],'observer':'test','reason':'zoom'})

def test_labels_cannot_enter_inference_scene(tmp_path):
    s=make_session(tmp_path)
    np.savez_compressed(tmp_path/'geometry.npz',coords=s.scene.coords,record_ids=s.scene.record_ids,ground_truth=np.ones(200))
    (tmp_path/'scene.json').write_text(json.dumps({'geometry_sha256':digest(tmp_path/'geometry.npz')}))
    with pytest.raises(ValueError,match='must not contain labels'):Session(tmp_path)

def test_candidate_file_tampering_cannot_commit_extra_hidden_line(tmp_path):
    s=make_session(tmp_path)
    for n,k in [('s','side'),('t','top')]:s.act({'action':'LOOK','view_id':n,'kind':k,'observer':'test','reason':'observe'})
    out=s.act({'action':'PROPOSE','candidate_id':'one','observer':'test','reason':'one visible wire','selections':[{'view_id':'s','type':'box','coordinates':[0,0,1000,1000]},{'view_id':'t','type':'box','coordinates':[0,0,250,1000]}]})
    np.save(tmp_path/'candidates/one.npy',np.arange(200))
    with pytest.raises(ValueError,match='points changed'):
        s.act({'action':'CONFIRM','candidate_id':'one','instance_id':'wire','observer':'test','reason':'reviewed','point_sha256':out['point_sha256'],'reviewed_images':out['overlays']})
    assert not s.state['instances']

def test_frozen_annotation_export_roundtrips_raw_ids_and_unknowns(tmp_path):
    from visual_annotation_v3.artifacts import export
    import laspy
    s=make_session(tmp_path)
    for n,k in [('s','side'),('t','top')]:s.act({'action':'LOOK','view_id':n,'kind':k,'observer':'test','reason':'observe'})
    out=s.act({'action':'PROPOSE','candidate_id':'one','observer':'test','reason':'select first wire','selections':[{'view_id':'s','type':'box','coordinates':[0,0,1000,1000]},{'view_id':'t','type':'box','coordinates':[0,0,250,1000]}]})
    s.act({'action':'CONFIRM','candidate_id':'one','instance_id':'wire','observer':'test','reason':'reviewed','point_sha256':out['point_sha256'],'reviewed_images':out['overlays']})
    s.act({'action':'UNKNOWN','observer':'test','reason':'Second line not annotated'})
    s.act({'action':'FINISH','observer':'test','reason':'freeze'})
    with pytest.raises(ValueError,match='immutable'):s.act({'action':'REVISE','candidate_id':'one','observer':'test','reason':'late change'})
    result=export(tmp_path)
    assert result['points']==200 and result['readback_verified']
    a=laspy.read(tmp_path/'annotated_scene.las')
    assert np.array_equal(a.source_record_id,np.arange(200))
    assert np.array_equal(a.vlm_confirmed,np.r_[np.ones(100),np.zeros(100)])
    assert np.all(np.asarray(a.classification)==0)

def test_composition_preserves_raw_ids_and_rejects_instance_overlap(tmp_path):
    from visual_annotation_v3.compose import compose, verify
    def frozen(name, box):
        root=tmp_path/name;root.mkdir();s=make_session(root)
        meta=json.loads((root/'scene.json').read_text())
        meta.update(source_las='same.las',source_size=123,source_mtime_ns=456,scene_total_points=200)
        (root/'scene.json').write_text(json.dumps(meta))
        for n,k in [('initial_side','oblique'),('initial_top','top')]:
            s.act({'action':'LOOK','view_id':n,'kind':k,'size':128,'observer':'test','reason':'observe'})
        c=s.act({'action':'PROPOSE','candidate_id':'line','observer':'test','reason':'select',
                 'selections':[{'view_id':'initial_side','type':'box','coordinates':[0,0,1000,1000]},
                               {'view_id':'initial_top','type':'box','coordinates':box}]})
        s.act({'action':'CONFIRM','candidate_id':'line','instance_id':'line','point_sha256':c['point_sha256'],
               'reviewed_images':c['overlays'],'observer':'test','reason':'reviewed'})
        s.act({'action':'FINISH','observer':'test','reason':'freeze'})
        return root
    base=frozen('base',[0,0,250,1000]);child=frozen('child',[750,0,1000,1000])
    out=tmp_path/'merged'
    compose(base,[child],out,'development composition')
    with np.load(out/'annotation.npz') as a:
        assert np.array_equal(a['record_ids'],np.arange(200))
        assert np.array_equal(a['instance_ids'],np.r_[np.ones(100),np.full(100,2)])
    assert verify(out)['point_labels_identical']
    with pytest.raises(ValueError,match='overlap'):
        compose(out,[child],tmp_path/'overlap','must not silently double assign')
    np.save(child/'candidates/line.npy',np.arange(200))
    with pytest.raises(ValueError,match='changed'):
        verify(out)

def test_high_aggregate_recall_cannot_hide_a_completely_missed_class(tmp_path):
    import laspy
    from visual_annotation_v3.scene import prepare, save_archive
    from visual_annotation_v3.evaluate import evaluate
    source=tmp_path/'source.las'
    header=laspy.LasHeader(point_format=6,version='1.4')
    header.add_extra_dim(laspy.ExtraBytesParams(name='ground_truth',type=np.uint8))
    cloud=laspy.LasData(header)
    cloud.x=np.zeros(201);cloud.y=np.linspace(0,2,201);cloud.z=np.ones(201)
    cloud.ground_truth=np.r_[np.full(100,5),np.full(100,6),7].astype(np.uint8)
    cloud.write(source)
    root=tmp_path/'run';prepare(source,0,3,root)
    save_archive(root/'annotation.npz',record_ids=np.arange(201),instance_ids=np.r_[np.ones(200,dtype=np.int32),0])
    (root/'state.json').write_text(json.dumps({'finished':True,'annotation_sha256':digest(root/'annotation.npz'),
        'instances':{'fixture':{'observer':'test'}},'unknown':[]}))
    result=evaluate(root)
    assert result['raw_point_gate_passed']
    assert result['class_recalls']['7']['recall_pct']==0
    assert not result['point_and_class_gate_passed']
    assert result['combined']['fn']==1
