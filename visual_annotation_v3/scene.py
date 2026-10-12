"""Geometry-only observation store. Labels never appear in a session archive."""
import hashlib
import json
from pathlib import Path
import numpy as np

def save_archive(path,**arrays):
    """Deterministic NPZ, fast compression for tens of millions of raw records."""
    import zipfile
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as archive:
        for name,array in arrays.items():
            info=zipfile.ZipInfo(name+'.npy',date_time=(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED;info._compresslevel=1
            with archive.open(info,'w',force_zip64=True) as entry:
                np.lib.format.write_array(entry,np.asarray(array),allow_pickle=False)

def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def prepare(las_path, y0, y1, output):
    import laspy
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    if (out/'scene.json').exists() or (out/'geometry.npz').exists():raise ValueError('existing scene is immutable; choose a fresh output directory')
    if not np.isfinite([y0,y1]).all() or y0>=y1:raise ValueError('invalid ROI')
    coords=[];ids=[];start=0
    with laspy.open(las_path) as reader:
        ymin=float(reader.header.mins[1]);bounds=[reader.header.mins.tolist(),reader.header.maxs.tolist()]
        total=int(reader.header.point_count)
        for points in reader.chunk_iterator(2_000_000):
            y=np.asarray(points.y);chosen=(y>=ymin+y0)&(y<ymin+y1)
            if chosen.any():
                coords.append(np.column_stack([np.asarray(points.x)[chosen],y[chosen],np.asarray(points.z)[chosen]]))
                ids.append(np.flatnonzero(chosen).astype(np.int64)+start)
            start+=len(points)
    xyz=np.concatenate(coords) if coords else np.empty((0,3));record_ids=np.concatenate(ids) if ids else np.empty(0,dtype=np.int64)
    save_archive(out/'geometry.npz',coords=xyz,record_ids=record_ids)
    source=Path(las_path)
    meta={'source_las':str(source.resolve()),'source_size':source.stat().st_size,'source_mtime_ns':source.stat().st_mtime_ns,'scene_total_points':total,'scene_bounds':bounds,'roi_y_offset':[y0,y1],'roi_y_absolute':[ymin+y0,ymin+y1],'roi_boundary':'left inclusive, right exclusive','roi_points':len(xyz),'geometry_sha256':digest(out/'geometry.npz'),'allowed_fields':['coords','record_ids'],'labels_in_geometry':False,'task':'power-line conductor and structural cable point annotation; separate instances where observed'}
    meta['annotation_protocol']='context_v1'
    meta['patch_review_protocol']='delta_v1'
    (out/'scene.json').write_text(json.dumps(meta,indent=2))
    return meta

class Scene:
    def __init__(self,path):
        self.path=Path(path);self.meta=json.loads((self.path/'scene.json').read_text())
        if digest(self.path/'geometry.npz')!=self.meta['geometry_sha256']:raise ValueError('scene geometry changed')
        with np.load(self.path/'geometry.npz') as a:
            if set(a.files)!={'coords','record_ids'}:raise ValueError('inference geometry must not contain labels or extra features')
            self.coords=a['coords'];self.record_ids=a['record_ids']
        if self.coords.shape!=(len(self.record_ids),3) or not np.isfinite(self.coords).all():raise ValueError('invalid geometry')
        if np.any(np.diff(self.record_ids)<=0):raise ValueError('raw record IDs must be sorted and unique')
        self.origin=self.coords.min(0) if len(self.coords) else np.zeros(3)
        self.local=self.coords-self.origin
