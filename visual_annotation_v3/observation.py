"""Orthographic views and explicitly bounded 2-D selection tools; no 3-D tracing."""
from pathlib import Path
import json
import numpy as np
from PIL import Image, ImageDraw
from .scene import digest

BASES={
 'side':np.array([[0.,1,0],[0,0,1],[1,0,0]]),
 'top':np.array([[1.,0,0],[0,1,0],[0,0,-1.]]),
 'axial':np.array([[1.,0,0],[0,0,1],[0,1.,0]]),
 'oblique':np.array([[1/np.sqrt(2),1/np.sqrt(2),0],[-.3,.3,np.sqrt(.82)],[np.sqrt(.41),-np.sqrt(.41),.3*np.sqrt(2)]])}

def project(scene,meta):
    from collections import OrderedDict
    if not hasattr(scene,'projection_cache'):scene.projection_cache=OrderedDict()
    key=json.dumps([meta['basis'],meta['plane_bounds'],meta['size']])
    if key in scene.projection_cache:
        scene.projection_cache.move_to_end(key);return scene.projection_cache[key]
    c=scene.local@np.asarray(meta['basis']).T
    lo=np.array(meta['plane_bounds'][0]);hi=np.array(meta['plane_bounds'][1]);size=meta['size']
    uv=(c[:,:2]-lo)/(hi-lo)*(size-1)
    uv[:,1]=(size-1)-uv[:,1]
    result=(uv,c[:,2].copy())
    scene.projection_cache[key]=result
    while len(scene.projection_cache)>2:scene.projection_cache.popitem(last=False)
    return result

def camera_basis(camera):
    angles=np.asarray([camera['azimuth_deg'],camera['elevation_deg']],float)
    if not np.isfinite(angles).all() or not -90<=angles[1]<=90:raise ValueError('invalid camera angles')
    az,el=np.radians(angles)
    right=np.array([-np.sin(az),np.cos(az),0.])
    forward=np.array([np.cos(el)*np.cos(az),np.cos(el)*np.sin(az),np.sin(el)])
    return np.array([right,np.cross(forward,right),forward])


def render(scene,view_id,kind='side',size=1024,parent=None,box=None,depth_range=None,restrict=None,point_radius_px=1,color_mode='height',camera=None,context_of=None,context_margin=.2):
    if not view_id or '/' in view_id or '..' in view_id:raise ValueError('invalid view ID')
    if not 64<=size<=2048:raise ValueError('image size must be 64..2048')
    folder=scene.path/'views';folder.mkdir(exist_ok=True)
    if (folder/f'{view_id}.json').exists():raise ValueError('view_id is immutable; choose a new ID')
    if parent is not None and camera is not None:raise ValueError('zoom keeps its parent camera; use LOOK to change angle')
    if context_of is not None:
        if parent is not None or camera is not None or restrict or depth_range is not None:raise ValueError('context must preserve raw neighborhood')
        if not np.isfinite(context_margin) or not 0<=context_margin<=1:raise ValueError('invalid context margin')
        basis=np.asarray(context_of['basis']);kind=context_of['kind']
    else:
        basis=(camera_basis(camera) if camera else BASES[kind]) if parent is None else np.asarray(parent['basis'])
        if camera:kind='custom'
    cam=scene.local@basis.T
    eligible=np.ones(len(cam),bool)
    restrictions=restrict if restrict is not None else (parent.get('restrict',[]) if parent else [])
    for selection in restrictions:
        eligible&=selection_mask(scene,read_view(scene,selection['view_id']),selection)
    if depth_range is not None:eligible&=(cam[:,2]>=depth_range[0])&(cam[:,2]<=depth_range[1])
    if len(cam)==0:raise ValueError('empty ROI')
    if context_of is not None:
        lo,hi=np.array(context_of['plane_bounds']);pad=(hi-lo)*context_margin;lo-=pad;hi+=pad
    elif parent is None:
        shown=cam[eligible] if eligible.any() else cam
        lo=shown[:,:2].min(0);hi=shown[:,:2].max(0);pad=np.maximum((hi-lo)*.04,.2);lo-=pad;hi+=pad
    else:
        if box is None:raise ValueError('ZOOM requires an explicit rectangle')
        x0,y0,x1,y1=np.asarray(box,float)/1000
        if not(0<=x0<x1<=1 and 0<=y0<y1<=1):raise ValueError('invalid normalized zoom box')
        low=np.array(parent['plane_bounds'][0]);span=np.array(parent['plane_bounds'][1])-low
        lo=low+span*np.array([x0,1-y1]);hi=low+span*np.array([x1,1-y0])
    if point_radius_px not in [1,2,3]:raise ValueError('display radius must be 1, 2 or 3 pixels')
    if color_mode not in ['height','ink']:raise ValueError('invalid color mode')
    meta={'view_id':view_id,'kind':kind,'size':size,'basis':basis.tolist(),'plane_bounds':[lo.tolist(),hi.tolist()],'depth_range':depth_range,'restrict':restrictions,'origin':scene.origin.tolist(),'parent':parent['view_id'] if parent else None,'zoom_box':box,'coordinate_contract':'coordinates normalized 0..1000 over the entire PNG; x right, y down','geometry_sha256':scene.meta['geometry_sha256'],'point_radius_px':point_radius_px}
    meta['color_mode']=color_mode
    if camera:meta['camera']=camera
    if context_of is not None:meta.update(purpose='unfiltered_context',context_of=context_of['view_id'],context_margin=context_margin)
    uv,depth=project(scene,meta);pixels=np.rint(uv).astype(int)
    valid=eligible&(pixels[:,0]>=0)&(pixels[:,0]<size)&(pixels[:,1]>=0)&(pixels[:,1]<size)
    if depth_range is not None:valid&=(depth>=depth_range[0])&(depth<=depth_range[1])
    idx=np.flatnonzero(valid);flat=pixels[idx,1]*size+pixels[idx,0]
    order=np.lexsort((scene.record_ids[idx],depth[idx],flat));ordered=idx[order];flat_sorted=flat[order]
    first=np.r_[True,np.diff(flat_sorted)!=0] if len(flat_sorted) else np.zeros(0,bool)
    winners=ordered[first]
    pixel_map=np.full((size,size),-1,dtype=np.int64)
    depth_map=np.full((size,size),np.inf,dtype=np.float32)
    rgb=np.zeros((size,size,3),dtype=np.uint8)
    if color_mode=='ink':rgb[:]=255
    z=scene.local[winners,2];norm=(z-scene.local[:,2].min())/max(float(np.ptp(scene.local[:,2])),1e-5)
    colors=np.column_stack([170+85*norm,180+75*norm,195+60*norm]).astype(np.uint8)
    if color_mode=='ink':colors[:]=[20,25,35]
    for dy in range(1-point_radius_px,point_radius_px):
        for dx in range(1-point_radius_px,point_radius_px):
            yy=pixels[winners,1]+dy;xx=pixels[winners,0]+dx
            inside=(xx>=0)&(xx<size)&(yy>=0)&(yy<size)
            q=np.flatnonzero(inside);z=depth[winners[q]].astype(np.float32)
            old=depth_map[yy[q],xx[q]]
            win=(z<old)|((z==old)&(winners[q]<pixel_map[yy[q],xx[q]]))
            q=q[win];depth_map[yy[q],xx[q]]=depth[winners[q]]
            pixel_map[yy[q],xx[q]]=winners[q];rgb[yy[q],xx[q]]=colors[q]
    Image.fromarray(rgb).save(folder/f'{view_id}.png')
    np.savez_compressed(folder/f'{view_id}.npz',pixel_map=pixel_map,depth=depth_map)
    meta['image_sha256']=digest(folder/f'{view_id}.png');meta['visible_records']=int(len(np.unique(pixel_map[pixel_map>=0])))
    (folder/f'{view_id}.json').write_text(json.dumps(meta,indent=2));return meta

def read_view(scene,view_id):
    if '/' in view_id or '..' in view_id:raise ValueError('invalid view ID')
    meta=json.loads((scene.path/'views'/f'{view_id}.json').read_text())
    if digest(scene.path/'views'/f'{view_id}.png')!=meta['image_sha256']:raise ValueError('image changed after observation')
    return meta

def selection_mask(scene,meta,selection):
    from collections import OrderedDict
    if not hasattr(scene,'selection_cache'):scene.selection_cache=OrderedDict()
    key=json.dumps([meta['view_id'],meta['image_sha256'],selection],sort_keys=True)
    if selection['type']!='anchors' and key in scene.selection_cache:
        scene.selection_cache.move_to_end(key);return scene.selection_cache[key]
    uv,depth=project(scene,meta);points=uv*1000/(meta['size']-1)
    mask=(points[:,0]>=0)&(points[:,0]<=1000)&(points[:,1]>=0)&(points[:,1]<=1000)
    for restriction in meta.get('restrict',[]):
        mask&=selection_mask(scene,read_view(scene,restriction['view_id']),restriction)
    if meta['depth_range'] is not None:mask&=(depth>=meta['depth_range'][0])&(depth<=meta['depth_range'][1])
    kind=selection['type']
    if kind=='anchors':
        if '/' in selection['marker_set'] or '..' in selection['marker_set']:raise ValueError('invalid marker set')
        marker_file=scene.path/'measurements'/f"{selection['marker_set']}.json"
        markers=json.loads(marker_file.read_text())
        if markers['view_id']!=meta['view_id'] or markers['image_sha256']!=meta['image_sha256']:raise ValueError('anchors refer to another image')
        table={r['id']:r['center'] for r in markers['markers']}
        coords=np.asarray([table[k] for k in selection['marker_ids']],float)
        kind='polyline'
    else:coords=np.asarray(selection['coordinates'],float)
    if not np.isfinite(coords).all() or np.any(coords<0) or np.any(coords>1000):raise ValueError('selection coordinates must be finite and in 0..1000')
    if kind=='box':
        if coords.shape!=(4,):raise ValueError('box needs x0,y0,x1,y1')
        x0,y0,x1,y1=coords
        if x1<=x0 or y1<=y0:raise ValueError('empty/inverted box')
        mask&=(points[:,0]>=x0)&(points[:,0]<=x1)&(points[:,1]>=y0)&(points[:,1]<=y1)
    elif kind=='polyline':
        if coords.ndim!=2 or coords.shape[1]!=2 or len(coords)<2:raise ValueError('polyline needs at least two points')
        radius=float(selection.get('radius',3))
        if not 0<radius<=30:raise ValueError('brush radius must be in (0,30] normalized units')
        bboxlo=coords.min(0)-radius;bboxhi=coords.max(0)+radius
        mask&=np.all((points>=bboxlo)&(points<=bboxhi),axis=1)
        ids=np.flatnonzero(mask);q=points[ids];d=np.full(len(ids),np.inf)
        for a,b in zip(coords[:-1],coords[1:]):
            v=b-a;den=np.dot(v,v)
            if den<1e-12:continue
            t=np.clip(((q-a)@v)/den,0,1);d=np.minimum(d,np.linalg.norm(q-a-t[:,None]*v,axis=1))
        mask[ids]=d<=radius
    else:raise ValueError('unsupported selection type')
    mask.setflags(write=False)
    if selection['type']!='anchors':
        scene.selection_cache[key]=mask
        while len(scene.selection_cache)>16:scene.selection_cache.popitem(last=False)
    return mask

def visible_support(scene,meta,mask):
    with np.load(scene.path/'views'/f"{meta['view_id']}.npz") as a:ids=np.unique(a['pixel_map']);ids=ids[ids>=0]
    return int(mask[ids].sum())

def overlay(scene,meta,mask,path,color=(0,230,100),point_radius_px=1,visibility_aware=False):
    if point_radius_px not in [1,2,3,4]:raise ValueError('invalid overlay display radius')
    image=Image.open(scene.path/'views'/f"{meta['view_id']}.png").convert('RGB')
    draw=ImageDraw.Draw(image);uv,_=project(scene,meta)
    size=meta['size'];selected=np.flatnonzero(mask)
    if visibility_aware:
        with np.load(scene.path/'views'/f"{meta['view_id']}.npz") as a:visible=np.unique(a['pixel_map']);visible=visible[visible>=0]
        seen=np.isin(selected,visible)
        groups=[(selected[~seen],(255,155,45)),(selected[seen],color)]
    else:groups=[(selected,color)]
    for ids,paint in groups:
        px=np.rint(uv[ids]).astype(int);px=px[np.all((px>=0)&(px<size),axis=1)]
        for x,y in np.unique(px,axis=0):
            if point_radius_px==1:draw.point((int(x),int(y)),fill=paint)
            else:
                r=point_radius_px-1;draw.ellipse((int(x-r),int(y-r),int(x+r),int(y+r)),fill=paint)
    image.save(path)
    if visibility_aware:return {'visible_selected_records':int(seen.sum()),'not_individually_visible_records':int((~seen).sum()),'legend':{'green':'selected records visible in the raw projection','orange':'selected projection without individual visibility; includes occlusion and pixel collisions'}}

def measure_rows(scene,meta,name,rows,half_height=15,gap=10,axis='rows',restrict=None):
    """Number local 2-D point clusters in requested thin horizontal strips.

    No cross-strip association, semantic filtering, line fitting, or 3-D tracing.
    The visual observer must decide which markers correspond to an object.
    """
    from PIL import ImageFont
    if axis not in ['rows','columns'] or not 0<half_height<=100 or not 0<gap<=100:raise ValueError('invalid measurement parameters')
    if not rows or len(rows)>26 or not np.isfinite(rows).all() or min(rows)<0 or max(rows)>1000:raise ValueError('invalid measurement positions')
    folder=scene.path/'measurements';folder.mkdir(exist_ok=True)
    if '/' in name or '..' in name or (folder/f'{name}.json').exists():raise ValueError('measurement ID must be fresh and path-safe')
    uv,_=project(scene,meta);uv=uv*1000/(meta['size']-1)
    eligible=selection_mask(scene,meta,{'type':'box','coordinates':[0,0,1000,1000]}).copy()
    for selection in restrict or []:eligible&=selection_mask(scene,read_view(scene,selection['view_id']),selection)
    along,across=(1,0) if axis=='rows' else (0,1)
    image=Image.open(scene.path/'views'/f"{meta['view_id']}.png").convert('RGB');draw=ImageDraw.Draw(image)
    try:font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',16)
    except OSError:font=ImageFont.load_default()
    markers=[];scale=(meta['size']-1)/1000
    for row_index,v in enumerate(rows):
        selected=np.flatnonzero(eligible & (np.abs(uv[:,along]-v)<=half_height))
        order=selected[np.argsort(uv[selected,across])]
        groups=np.split(order,np.flatnonzero(np.diff(uv[order,across])>gap)+1) if len(order) else []
        line=[(0,int(v*scale)),(meta['size']-1,int(v*scale))] if axis=='rows' else [(int(v*scale),0),(int(v*scale),meta['size']-1)]
        draw.line(line,fill=(35,45,55),width=1)
        for j,group in enumerate(groups):
            center=np.median(uv[group],axis=0);label=f'{chr(65+row_index)}{j+1}'
            markers.append({'id':label,'center':center.tolist(),'point_count':len(group),'box':[uv[group,0].min(),uv[group,1].min(),uv[group,0].max(),uv[group,1].max()]})
            x,y=center*scale;draw.ellipse([x-5,y-5,x+5,y+5],outline=(255,170,0),width=2);draw.text((x+7,y-18),label,fill=(255,170,0),font=font)
    path=folder/f'{name}.png';image.save(path)
    result={'view_id':meta['view_id'],'image_sha256':meta['image_sha256'],'marker_set':name,'axis':axis,'rows':rows,'half_height':half_height,'gap':gap,'restrict':restrict or [],'markers':markers,'image':str(path),'marked_image_sha256':digest(path)}
    (folder/f'{name}.json').write_text(json.dumps(result,indent=2));return result

def coarse_grid(scene,meta,name):
    from PIL import ImageFont
    folder=scene.path/'measurements';folder.mkdir(exist_ok=True)
    if '/' in name or '..' in name or (folder/f'{name}.json').exists():raise ValueError('measurement ID must be fresh and path-safe')
    image=Image.open(scene.path/'views'/f"{meta['view_id']}.png").convert('RGB');draw=ImageDraw.Draw(image);size=meta['size']
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',max(18,size//32))
    rows={}
    for i in range(10):
        label=chr(65+i);y0=i*size/10;y1=(i+1)*size/10
        draw.line([(0,y0),(size-1,y0)],fill=(45,45,60),width=1)
        draw.text((3,(y0+y1)/2-12),label,fill=(255,170,0),font=font)
        rows[label]=[0,i*100,1000,(i+1)*100]
    path=folder/f'{name}.png';image.save(path)
    result={'view_id':meta['view_id'],'image_sha256':meta['image_sha256'],'image':str(path),'rows':rows,'marked_image_sha256':digest(path)}
    (folder/f'{name}.json').write_text(json.dumps(result,indent=2));return result
