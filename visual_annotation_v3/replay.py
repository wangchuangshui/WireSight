"""Deterministically execute saved visual decisions without any truth access.

This checks the executor, not the repeatability of the model's perception.
"""
import argparse
import json
import shutil
from pathlib import Path
import numpy as np
from .session import Session


def replay(source,destination):
    src=Path(source).resolve();dst=Path(destination).resolve()
    if dst.exists():raise ValueError('replay destination must be new')
    state=json.loads((src/'state.json').read_text())
    if state.get('revision_base'):
        from .revision import fork
        from .scene import digest
        base=state['revision_base'];root=Path(base['path'])
        for name in ['annotation','state','actions']:
            suffix={'annotation':'.npz','state':'.json','actions':'.jsonl'}[name]
            if digest(root/(name+suffix))!=base[name+'_sha256']:raise ValueError('revision source changed')
        fork(root,dst,delta_review=state.get('patch_review_protocol')=='delta_v1')
    else:
        dst.mkdir(parents=True)
        for name in ['scene.json','geometry.npz']:shutil.copy2(src/name,dst/name)
    def remap(value):
        if isinstance(value,dict):return {remap(k):remap(v) for k,v in value.items()}
        if isinstance(value,list):return [remap(v) for v in value]
        if isinstance(value,str):
            for prefix in [str(src),str(source),*s.scene.meta.get('recorded_path_prefixes',[])]:
                if value.startswith(prefix+'/'):return str(dst)+value[len(prefix):]
        return value
    s=Session(dst);count=0
    for line in (src/'actions.jsonl').read_text().splitlines():
        row=json.loads(line);action=remap(row['action'])
        result=s.act(action);count+=1
        for key in ['point_sha256','points','selected_points','image_sha256']:
            if key in row['result'] and result.get(key)!=row['result'][key]:raise ValueError(f'replay diverged at action {count}: {key}')
    with np.load(src/'annotation.npz') as a,np.load(dst/'annotation.npz') as b:
        equal=all(np.array_equal(a[k],b[k]) for k in a.files)
    if not equal:raise ValueError('annotation mismatch after replay')
    result={'actions_replayed':count,'point_labels_identical':equal,'source':str(src),'destination':str(dst),'ground_truth_read':False,'model_invoked':False,'meaning':'executor replay of saved visual decisions, not an autonomous model repeat'}
    (dst/'replay_verification.json').write_text(json.dumps(result,indent=2));return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('destination');a=p.parse_args();print(json.dumps(replay(a.source,a.destination),indent=2))
