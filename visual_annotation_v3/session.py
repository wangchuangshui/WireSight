"""Audited observation/action session. Candidates need independent views and review.

The caller is a visual model (local JSON adapter or this conversation). Every
decision is retained with its provenance; conversation observations are never
reported as unattended local-model runs.
"""
import json
from pathlib import Path
from datetime import datetime,timezone
import hashlib
import numpy as np
from .scene import Scene,digest,save_archive
from .observation import render,read_view,selection_mask,visible_support,overlay,measure_rows,coarse_grid
from . import review_protocol

class Session:
    def __init__(self,path):
        self.scene=Scene(path);self.path=self.scene.path
        p=self.path/'state.json'
        self.state=json.loads(p.read_text()) if p.exists() else {'instances':{},'candidates':{},'unknown':[],'finished':False,'protocol':self.scene.meta.get('annotation_protocol','legacy_v0')}
        if 'patch_review_protocol' not in self.state and self.scene.meta.get('patch_review_protocol'):
            self.state['patch_review_protocol']=self.scene.meta['patch_review_protocol']
    def _save(self,action,result):
        (self.path/'state.json').write_text(json.dumps(self.state,ensure_ascii=False,indent=2))
        with (self.path/'actions.jsonl').open('a') as f:f.write(json.dumps({'timestamp':datetime.now(timezone.utc).isoformat(),'action':action,'result':result},ensure_ascii=False)+'\n')
        return result
    def act(self,action):
        if self.state['finished']:raise ValueError('finished session is immutable')
        if not action.get('observer') or not action.get('reason'):raise ValueError('observer provenance and reason required')
        verb=action['action']
        if verb in ['QUESTION','INSPECT','REVIEW','SURVEY']:
            return self._save(action,review_protocol.handle(self,action))
        if verb=='PATCH':
            from .revision import patch
            return self._save(action,patch(self,action))
        if verb=='PREVIEW_PATCH':
            from .revision import preview
            return self._save(action,preview(self,action))
        if verb in ['LOOK','ZOOM']:
            parent=read_view(self.scene,action['parent']) if verb=='ZOOM' else None
            meta=render(self.scene,action['view_id'],action.get('kind',parent['kind'] if parent else 'side'),size=action.get('size',1024),parent=parent,box=action.get('box'),depth_range=action.get('depth_range',parent.get('depth_range') if parent else None),restrict=action.get('restrict'),point_radius_px=action.get('point_radius_px',1),color_mode=action.get('color_mode',parent.get('color_mode','height') if parent else 'height'),camera=action.get('camera'))
            return self._save(action,{'view_id':meta['view_id'],'image':str(self.path/'views'/f"{meta['view_id']}.png"),'image_sha256':meta['image_sha256']})
        if verb=='PROPOSE':
            name=action['candidate_id']
            if '/' in name or '..' in name or name in self.state['candidates']:raise ValueError('candidate ID must be fresh and path-safe')
            strict=review_protocol.enabled(self)
            if strict:
                question=self.state.get('questions',{}).get(action.get('question_id'))
                if not question or question['status']=='resolved':raise ValueError('declare an unresolved QUESTION before proposing points')
            evidence=action['selections']
            if len(evidence)<2:raise ValueError('confirmation needs at least two observed projections')
            views=[read_view(self.scene,s['view_id']) for s in evidence]
            forwards=np.array([v['basis'][2] for v in views])
            angle=max(np.degrees(np.arccos(np.clip(abs(np.dot(a,b)),0,1))) for a in forwards for b in forwards)
            if angle<20:raise ValueError('views do not resolve depth; request a different direction')
            mask=np.ones(len(self.scene.coords),bool)
            for v,s in zip(views,evidence):mask&=selection_mask(self.scene,v,s)
            for exclusion in action.get('exclude',[]):
                mask&=~selection_mask(self.scene,read_view(self.scene,exclusion['view_id']),exclusion)
            support={v['view_id']:visible_support(self.scene,v,mask) for v in views}
            status='PENDING_REVIEW' if int(mask.sum())>=3 and all(n>=3 for n in support.values()) else 'INSUFFICIENT_EVIDENCE'
            folder=self.path/'candidates';folder.mkdir(exist_ok=True)
            ids=np.flatnonzero(mask);point_hash=hashlib.sha256(self.scene.record_ids[ids].tobytes()).hexdigest()
            np.save(folder/f'{name}.npy',ids)
            paths=[];overlay_meta=[]
            for v in views:
                p=folder/f"{name}_{v['view_id']}.png";info=overlay(self.scene,v,mask,p,point_radius_px=action.get('overlay_radius_px',1),visibility_aware=strict);paths.append(str(p))
                if strict:overlay_meta.append({'path':str(p),'view_id':v['view_id'],'role':'focused_selection',**info})
            item={'status':status,'points':len(ids),'point_sha256':point_hash,'support':support,'selections':evidence,'exclude':action.get('exclude',[]),'overlays':paths,'proposer':action['observer'],'independent_view_angle_deg':float(angle)}
            self.state['candidates'][name]=item
            if strict:
                question['status']='open'
                item.update(question_id=action['question_id'],contexts=[],reviews={},overlay_metadata=overlay_meta)
                if status=='PENDING_REVIEW':
                    for view_id in dict.fromkeys([v['view_id'] for v in views]+action.get('inspection_views',[])):
                        review_protocol.inspect(self,name,view_id)
            return self._save(action,item)
        if verb=='MEASURE_ROWS':
            result=measure_rows(self.scene,read_view(self.scene,action['view_id']),action['marker_set'],action['rows'],half_height=action.get('half_height',15),gap=action.get('gap',10),axis=action.get('axis','rows'),restrict=action.get('restrict'))
            return self._save(action,result)
        if verb=='MEASURE_GRID':
            result=coarse_grid(self.scene,read_view(self.scene,action['view_id']),action['marker_set'])
            return self._save(action,result)
        if verb=='CONFIRM':
            name=action['candidate_id'];candidate=self.state['candidates'][name]
            if candidate['status']!='PENDING_REVIEW':raise ValueError('only supported pending candidates may be confirmed')
            if action.get('point_sha256')!=candidate['point_sha256']:raise ValueError('confirmation must reference exact reviewed point hash')
            required=([c['overlay'] for c in candidate.get('contexts',[])] if review_protocol.enabled(self) else candidate['overlays'])
            if not set(required).issubset(set(action.get('reviewed_images',[]))):raise ValueError('review all candidate context overlays before committing')
            review_protocol.validate_commit(self,candidate,action)
            if review_protocol.enabled(self) and self.state['questions'][candidate['question_id']]['operation']!='annotate':raise ValueError('correction questions must commit through PATCH')
            instance=action['instance_id']
            if instance in self.state['instances']:raise ValueError('new instance ID required; explicit association needed to extend')
            ids=np.load(self.path/'candidates'/f'{name}.npy')
            if hashlib.sha256(self.scene.record_ids[ids].tobytes()).hexdigest()!=candidate['point_sha256']:raise ValueError('candidate points changed since review')
            for selection in candidate['selections']:read_view(self.scene,selection['view_id'])
            for old in self.state['instances'].values():
                if len(np.intersect1d(ids,np.load(self.path/'candidates'/f"{old['candidate_id']}.npy"))):raise ValueError('instance overlap; revise selections or resolve identity')
            candidate['status']='CONFIRMED'
            self.state['instances'][instance]={'candidate_id':name,'point_sha256':candidate['point_sha256'],'points':len(ids),'observer':action['observer'],'reason':action['reason']}
            if review_protocol.enabled(self):
                self.state['questions'][candidate['question_id']]['status']='resolved'
                review_protocol.changed(self)
            return self._save(action,{'instance_id':instance,'points':len(ids),'status':'CONFIRMED'})
        if verb=='REVISE':
            name=action['candidate_id'];self.state['candidates'][name]['status']='RETRACTED'
            self.state['instances']={k:v for k,v in self.state['instances'].items() if v['candidate_id']!=name}
            if review_protocol.enabled(self):
                question=self.state['candidates'][name].get('question_id')
                if question:self.state['questions'][question]['status']='open'
                review_protocol.changed(self)
            return self._save(action,{'status':'RETRACTED','candidate_id':name})
        if verb=='UNKNOWN':
            if action.get('question_id'):
                question=self.state['questions'][action['question_id']]
                if question['status']=='resolved':raise ValueError('resolved question cannot silently become unknown')
                question['status']='deferred';question['deferred_reason']=action['reason']
            self.state['unknown'].append(action)
            return self._save(action,{'status':'UNKNOWN'})
        if verb=='FINISH':
            acceptance=review_protocol.finish(self)
            instances=sorted(self.state['instances']);labels=np.zeros(len(self.scene.coords),np.int32)
            for number,name in enumerate(instances,1):
                candidate=self.state['instances'][name]['candidate_id'];ids=np.load(self.path/'candidates'/f'{candidate}.npy')
                if hashlib.sha256(self.scene.record_ids[ids].tobytes()).hexdigest()!=self.state['instances'][name]['point_sha256']:raise ValueError('confirmed candidate changed')
                labels[ids]=number
            save_archive(self.path/'annotation.npz',record_ids=self.scene.record_ids,instance_ids=labels)
            self.state['finished']=True;self.state['annotation_sha256']=digest(self.path/'annotation.npz')
            return self._save(action,{'instances':instances,'selected_points':int((labels>0).sum()),'unconfirmed_points':int((labels==0).sum()),'unknown_region_count':len(self.state['unknown']),'annotation_sha256':self.state['annotation_sha256'],'status':'FINISHED_AWAITING_INDEPENDENT_EVALUATION',**acceptance})
        raise ValueError('unsupported action')

def main():
    import argparse
    from .scene import prepare
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','act']);p.add_argument('--out',required=True);p.add_argument('--las');p.add_argument('--y0',type=float);p.add_argument('--y1',type=float);p.add_argument('--action')
    a=p.parse_args()
    result=prepare(a.las,a.y0,a.y1,a.out) if a.command=='prepare' else Session(a.out).act(json.loads(Path(a.action).read_text()))
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
