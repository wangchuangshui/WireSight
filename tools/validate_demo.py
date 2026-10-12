"""Offline browser acceptance: real pixels, image evidence, controls and mobile."""
from pathlib import Path
import json,hashlib,base64
from collections import Counter
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
PIXELS='''() => {
 const c=document.querySelector('#point-canvas'),g=c.getContext('webgl'),p=new Uint8Array(c.width*c.height*4);g.readPixels(0,0,c.width,c.height,g.RGBA,g.UNSIGNED_BYTE,p);
 const colors=[[255,107,107],[255,209,102],[77,214,153],[82,181,255],[207,161,255]];
 return colors.map(rgb=>{let n=0;for(let i=0;i<p.length;i+=4)if(rgb.every((v,j)=>Math.abs(v-p[i+j])<=6))n++;return n;});
}'''
def read_js(path):return json.loads(path.read_text().split('=',1)[1].rstrip(';\n'))
d=read_js(ROOT/'demo/story-data.js');audit=read_js(ROOT/'demo/audit/demo-data.js')
assert d['annotation_sha256']==json.loads((ROOT/'evidence/metrics.json').read_text())['annotation_sha256']
assets=set()
for r in audit['runs'].values():
 for s in r['steps']:
  for im in s.get('images',[])+s.get('before',[]):
   p=ROOT/'demo/audit'/im['url'].lstrip('/');assert p.is_file(),str(p);assets.add(str(p.relative_to(ROOT)))
 for name,url in r.get('artifacts',{}).items():assert (ROOT/'demo/audit'/url.lstrip('/')).is_file(),(name,url)
point_script=ROOT/'demo'/d['overview']['data_url'];payload=json.loads(point_script.read_text().split(']=',1)[1].rstrip(';\n'));raw=base64.b64decode(payload['data']);assert hashlib.sha256(raw).hexdigest()==payload['sha256'];assert len(raw)==payload['point_count']*16
import struct
counts=Counter(round(p[3]) for p in struct.iter_unpack('<4f',raw))
for w in d['overview']['main_wires']+d['overview']['additional_wires']:assert counts[w['id']]==w['points']
checks={};errors=[];external=[]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--no-sandbox','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
 context=b.new_context(viewport={'width':1600,'height':1000});context.route('http**://**',lambda route:(external.append(route.request.url),route.abort()))
 page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto((ROOT/'demo/index.html').as_uri());page.wait_for_function("document.querySelector('#point-canvas').dataset.ready==='true'");page.wait_for_timeout(100)
 assert page.locator('body').get_attribute('data-step')=='0';assert page.locator('#input-image').get_attribute('src').endswith('t1z5b_full_session/views/initial_top.png');assert 'Net gains over geometry baselines' in page.locator('#meaning').inner_text();checks['top_view_entry_and_evidence_bounded_meaning']=True
 page.evaluate('window.WireLaunch.stop()');assert page.locator('#hero-canvas').get_attribute('data-ready')=='true'
 page.click('#hero-plain');assert page.evaluate('WireLaunch.viewer.annotated') is False;page.click('#hero-colored');assert page.evaluate('WireLaunch.viewer.annotated') is True;checks['hero_colored_uncolored_display']=True
 page.click('#model-path-toggle');assert not page.locator('#model-path-overlay').evaluate('(e)=>e.hasAttribute("hidden")');assert page.locator('#model-path-overlay polyline').count()==5;assert 'PROPOSE' in page.locator('#input-footer').inner_text();page.click('#model-path-toggle');checks['recorded_model_paths_visible_and_disclosed']=True
 colors=page.evaluate(PIXELS);assert all(n>5 for n in colors),colors;checks['five_wire_pixels']=colors
 for i in range(8):
  page.locator('#steps button').nth(i).click();assert page.locator('body').get_attribute('data-step')==str(i)
  for j in [0,1]:
   if j:page.click('#angle')
   page.wait_for_function("document.querySelector('#input-image').complete && document.querySelector('#input-image').naturalWidth>0")
  assert page.locator('#guide').inner_text()==d['story'][i]['guide']
 checks['eight_steps_and_sixteen_images']=True
 for wire in range(1,6):
  page.locator(f'[data-wire="{wire}"]').click();color=page.evaluate(PIXELS);assert color[wire-1]>5 and all(n==0 for i,n in enumerate(color) if i!=wire-1),(wire,color)
 checks['five_instance_isolation_by_pixels']=True
 page.click('#all-wires');page.click('#raw-mode');assert sum(page.evaluate(PIXELS))==0;page.click('#raw-mode');checks['uncolored_display']=True
 before=page.locator('#point-canvas').screenshot();box=page.locator('#point-canvas').bounding_box();page.mouse.move(box['x']+80,box['y']+70);page.mouse.down();page.mouse.move(box['x']+160,box['y']+100);page.mouse.up();assert before!=page.locator('#point-canvas').screenshot();checks['rotation_changes_pixels']=True
 for name in ['top','side','oblique']:page.click(f'[data-camera="{name}"]')
 page.click('#region');assert '94–118' in page.locator('#view-scope').inner_text();page.click('#region');checks['camera_presets_and_region_scope']=True
 page.click('#open-input');assert page.locator('#image-dialog').is_visible();page.click('#close-dialog');checks['image_zoom']=True
 page.click('#tour');page.wait_for_timeout(150);assert page.locator('body').get_attribute('data-step')=='0';page.click('#tour');checks['guided_playback_controls']=True
 page.goto((ROOT/'demo/audit/index.html').as_uri()+'?run=conversation_connection_revision_20261011');page.wait_for_function("window.__demoState?.run?.id==='conversation_connection_revision_20261011'");checks['local_branch_evidence_link']=True
 for run in audit['runs']:
  page.select_option('#run',run);page.wait_for_function('(id)=>window.__demoState?.run?.id===id',arg=run)
  for anchor in page.locator('#artifacts a').all():
   href=anchor.get_attribute('href');assert (ROOT/'demo/audit'/href).exists()
  for i in range(len(audit['runs'][run]['steps'])):
   page.evaluate('(i)=>{const e=document.querySelector("#scrub");e.value=i;e.dispatchEvent(new Event("input"))}',i)
   assert page.evaluate('window.__demoState.index')==i
   assert 'NaN' not in page.locator('.stats').inner_text()
  page.wait_for_function('Array.from(document.images).every(x=>x.complete&&x.naturalWidth>0)')
 checks['all_ten_audit_runs']=True
 checks['all_audit_steps_rendered']=sum(len(r['steps']) for r in audit['runs'].values())
 page.set_viewport_size({'width':390,'height':844});page.goto((ROOT/'demo/index.html').as_uri());page.wait_for_function("document.querySelector('#point-canvas').dataset.ready==='true'");assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2');page.screenshot(path=str(ROOT/'media/mobile.png'),full_page=True);checks['mobile_no_horizontal_overflow']=True;page.click('#open-film');assert page.locator('#film-dialog').is_visible();page.click('#close-film');checks['intro_video_dialog']=True
 assert not errors,errors;assert not external,external;context.close();b.close()
report={'passed':True,'checks':checks,'evidence_images_checked':len(assets),'browser_errors':errors,'network_requests':external,'point_payload_sha256':payload['sha256'],'display_counts':dict(sorted(counts.items())),'mode':'file://; network blocked; actual canvas pixels inspected'}
(ROOT/'evidence/browser_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2))
