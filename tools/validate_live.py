"""Check served demo, HTTP byte ranges and real video playback/seek."""
import argparse,json,urllib.request,urllib.error
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser(description=__doc__);p.add_argument('--url',default='http://127.0.0.1:8000');a=p.parse_args();base=a.url.rstrip('/');checks={}
for path in ['/','/demo/','/media/wiresight-demo.mp4']:
 with urllib.request.urlopen(base+path) as r:assert r.status==200;checks[path]=r.status
video=(ROOT/'media/wiresight-demo.mp4').read_bytes()
for value,expected in [('bytes=0-31',video[:32]),('bytes=-32',video[-32:]),('bytes=2048-2080',video[2048:2081])]:
 with urllib.request.urlopen(urllib.request.Request(base+'/media/wiresight-demo.mp4',headers={'Range':value})) as r:
  assert r.status==206 and r.headers['Accept-Ranges']=='bytes' and r.read()==expected
checks['http_range_prefix_suffix_middle']=True
try:
 urllib.request.urlopen(urllib.request.Request(base+'/media/wiresight-demo.mp4',headers={'Range':f'bytes={len(video)+10}-'}));raise AssertionError('Invalid range accepted')
except urllib.error.HTTPError as e:assert e.code==416;checks['invalid_range_416']=True
try:
 urllib.request.urlopen(urllib.request.Request(base+'/api/start',data=b'{}',headers={'Content-Type':'application/json'}));raise AssertionError('POST launched something')
except urllib.error.HTTPError as e:assert e.code==410;checks['model_launch_disabled']=True
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--no-sandbox','--use-angle=swiftshader','--enable-unsafe-swiftshader']);page=b.new_page(viewport={'width':1600,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto(base+'/');page.wait_for_function("document.querySelector('#point-canvas').dataset.ready==='true'")
 page.evaluate('()=>{const v=document.querySelector("video");v.muted=true;v.preload="auto";return v.play()}');page.wait_for_function('document.querySelector("video").currentTime>1')
 duration=page.evaluate('document.querySelector("video").duration');assert 72<=duration<=110
 page.evaluate('document.querySelector("video").currentTime=60');page.wait_for_function('document.querySelector("video").readyState>=2 && document.querySelector("video").currentTime>=60');checks['mp4_browser_play_and_seek']=True;checks['video_duration']=duration;page.evaluate('document.querySelector("video").pause()');page.screenshot(path=str(ROOT/'media/home-final.png'),full_page=True);b.close();assert not errors
checks['browser_errors']=errors;(ROOT/'evidence/live_service_validation.json').write_text(json.dumps(checks,indent=2));print(json.dumps(checks,indent=2))
