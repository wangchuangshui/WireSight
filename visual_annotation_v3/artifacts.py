"""Export raw-index annotations and a local evidence browser; no model or GT."""
import argparse
import html
import json
from pathlib import Path
import numpy as np
from .scene import Scene,digest


def export(path,selected_only=False):
    import laspy
    scene=Scene(path);root=scene.path;state=json.loads((root/'state.json').read_text())
    if not state['finished'] or digest(root/'annotation.npz')!=state['annotation_sha256']:
        raise ValueError('export requires a frozen, intact annotation')
    with np.load(root/'annotation.npz') as a:ids=a['record_ids'];instances=a['instance_ids']
    if not np.array_equal(ids,scene.record_ids):raise ValueError('raw-index mismatch')
    name='selected_points.las' if selected_only else 'annotated_scene.las'
    header=laspy.LasHeader(point_format=6,version='1.4')
    header.scales=np.array([.0001,.0001,.0001]);header.offsets=scene.origin
    header.add_extra_dims([laspy.ExtraBytesParams(name='source_record_id',type=np.uint64),laspy.ExtraBytesParams(name='vlm_instance_id',type=np.uint32),laspy.ExtraBytesParams(name='vlm_confirmed',type=np.uint8)])
    count=0
    with laspy.open(root/name,mode='w',header=header) as writer:
        for start in range(0,len(ids),1_000_000):
            end=min(start+1_000_000,len(ids));idx=np.arange(start,end)
            if selected_only:idx=idx[instances[idx]>0]
            points=laspy.ScaleAwarePointRecord.zeros(len(idx),header=header)
            points.x=scene.coords[idx,0];points.y=scene.coords[idx,1];points.z=scene.coords[idx,2]
            points.source_record_id=ids[idx];points.vlm_instance_id=instances[idx];points.vlm_confirmed=(instances[idx]>0).astype(np.uint8)
            writer.write_points(points);count+=len(idx)
    checked=0;max_error=0.
    with laspy.open(root/name) as reader:
        for points in reader.chunk_iterator(1_000_000):
            raw=np.asarray(points.source_record_id);idx=np.searchsorted(ids,raw)
            if not np.array_equal(ids[idx],raw) or not np.array_equal(np.asarray(points.vlm_instance_id),instances[idx]):raise ValueError('LAS readback ID/instance mismatch')
            xyz=np.column_stack([points.x,points.y,points.z]);max_error=max(max_error,float(np.max(np.abs(xyz-scene.coords[idx]))) if len(idx) else 0.)
            checked+=len(points)
    if count!=checked:raise ValueError('LAS readback count mismatch')
    result={'file':name,'sha256':digest(root/name),'points':count,'readback_verified':True,'max_coordinate_error_m':max_error,'selected_only':selected_only,'authoritative_fields':['source_record_id','vlm_instance_id','vlm_confirmed'],'zero_instance_means':'unconfirmed, including unknown; not a certified background label','classification_field':'left unclassified; cable subclasses were not visually assigned','instance_names':{str(i):k for i,k in enumerate(sorted(state['instances']),1)}}
    (root/(name+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result


def review(path):
    root=Path(path);state=json.loads((root/'state.json').read_text())
    metric_file=root/'evaluation/metrics.json';metrics=json.loads(metric_file.read_text()) if metric_file.exists() else {'status':'NOT_EVALUATED'}
    def esc(x):return html.escape(str(x),quote=True)
    chunks=['<!doctype html><meta charset="utf-8"><title>VLM 标注证据</title><style>body{font:16px sans-serif;max-width:1400px;margin:30px auto;background:#171a1f;color:#eee}a{color:#8bd0ff}img{max-width:48%;max-height:720px;object-fit:contain}pre{white-space:pre-wrap;background:#222;padding:16px}summary{cursor:pointer}section{margin:26px 0}</style>',f'<h1>{esc(root.name)}</h1>', '<p>白色为原始点投影，绿色为已选点。0 类表示未确认，不能据此认定背景。会话视觉操作与本地模型自动运行分别记账。</p>',f'<pre>{esc(json.dumps(metrics,ensure_ascii=False,indent=2))}</pre>','<p><a href="annotation.npz">原始点索引标注 NPZ</a> · <a href="actions.jsonl">完整操作日志</a> · <a href="state.json">实例与未决状态</a></p>']
    if state.get('protocol')=='context_v1':
        chunks[2]='<p>候选复核图：绿色为原图可见的候选点；橙色为因遮挡或像素重叠而无法单独辨认的候选点；紫红色为拟撤销归属。下方实例汇总采用实例配色。0 表示未确认，不能认定为背景。生成图片不等于已经复核，实际判断见 REVIEW 动作。</p>'
        if state.get('patch_review_protocol')=='delta_v1':
            chunks[2]='<p>改动独立复核：未过滤原图、蓝色既有标注、绿色拟新增点分别显示；紫红色为拟撤销点，橙色表示无法单独辨认。原有线段支持不能替代新增点支持。下方实例汇总使用实例配色。0 表示未确认，不能认定为背景；实际判断见 REVIEW 动作。</p>'
        chunks.insert(3,f'<p>原始场景复查已记录，完整性尚未验收。未解决问题：{esc(", ".join(state.get("observation_acceptance",{}).get("unresolved_questions",[])))}</p>')
    from PIL import Image
    with np.load(root/'annotation.npz') as a:labels=a['instance_ids']
    palette=np.array([[255,90,90],[60,220,110],[70,160,255],[240,190,40],[205,110,255],[40,220,220]],dtype=np.uint8)
    for kind in ['side','top']:
        view=root/'views'/f'initial_{kind}.npz'
        if not view.exists():continue
        with np.load(view) as a:pixel_map=a['pixel_map']
        rgb=np.asarray(Image.open(view.with_suffix('.png')).convert('RGB')).copy()
        valid=pixel_map>=0;image_labels=np.zeros(pixel_map.shape,np.int32);image_labels[valid]=labels[pixel_map[valid]]
        positive=image_labels>0;rgb[positive]=palette[(image_labels[positive]-1)%len(palette)]
        name=f'instances_{kind}.png';Image.fromarray(rgb).save(root/name)
        chunks.append(f'<a href="{name}"><img src="{name}"></a>')
    for name,instance in state['instances'].items():
        c=state['candidates'][instance['candidate_id']]
        chunks.append(f'<section><h2>{esc(name)} · {c["points"]:,} 点 · {esc(instance["observer"])}</h2><p>{esc(instance["reason"])}</p>')
        if c.get('evidence_parts'):
            chunks.append('<p>下图展示最近修订的局部证据；完整实例包含冻结来源及已提交修订，不能将局部复核图视为整条线的完整性证明。</p>')
        for p in c['overlays']:
            rel='candidates/'+Path(p).name;chunks.append(f'<a href="{esc(rel)}"><img loading="lazy" src="{esc(rel)}"></a>')
        chunks.append(f'<details><summary>选择范围与证据</summary><pre>{esc(json.dumps(c,ensure_ascii=False,indent=2))}</pre></details></section>')
    chunks.append('<h2>逐步动作</h2>')
    for row in (root/'actions.jsonl').read_text().splitlines():
        obj=json.loads(row);a=obj['action'];chunks.append(f'<details><summary>{esc(a["action"])} · {esc(a["reason"])}</summary><pre>{esc(json.dumps(obj,ensure_ascii=False,indent=2))}</pre></details>')
    (root/'review.html').write_text('\n'.join(chunks));return str(root/'review.html')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('path');p.add_argument('--las',action='store_true');p.add_argument('--selected-only',action='store_true');a=p.parse_args()
    if a.las:print(json.dumps(export(a.path,a.selected_only),ensure_ascii=False,indent=2))
    print(review(a.path))
