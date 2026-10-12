"""Render a documentary film from actual evidence and frozen point coordinates.

Camera frames use the same original-point WebGL renderer as the demo. Stored
narration WAVs are supplied; no visual annotation model or speech model is called.
"""
from pathlib import Path
import json,subprocess,wave,hashlib
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];MEDIA=ROOT/'media';PLAN=json.loads((MEDIA/'film-plan.json').read_text());FPS=12
work=MEDIA/'recording-source';work.mkdir(exist_ok=True)
def stamp(t,separator=','):
 ms=round(t*1000);h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000);return f'{h:02}:{m:02}:{s:02}{separator}{ms:03}'
# Exact scene durations align voice, captions and rendered frames.
with wave.open(str(MEDIA/'narration.en.wav'),'wb') as mixed:
 mixed.setparams((1,2,22050,0,'NONE','not compressed'))
 for i,s in enumerate(PLAN['scenes']):
  with wave.open(str(MEDIA/'narration'/f'{i:02}.wav'),'rb') as source:
   assert source.getnchannels()==1 and source.getsampwidth()==2 and source.getframerate()==22050
   raw=source.readframes(source.getnframes())
  lead=int(.35*22050);frames=int(s['seconds']*22050);tail=frames-lead-len(raw)//2;assert tail>=0
  mixed.writeframes(b'\0'*(lead*2)+raw+b'\0'*(tail*2))
srt=[];vtt=['WEBVTT\n'];transcript=['WireSight / A Visual Interface for 3D Annotation','Synthetic English narration; documentary presentation of recorded decisions and frozen points. No live annotation inference.','']
for i,s in enumerate(PLAN['scenes']):
 srt.append(f'{i+1}\n{stamp(s["start"])} --> {stamp(s["end"])}\n{s["narration"]}\n');vtt.append(f'{stamp(s["start"],".")} --> {stamp(s["end"],".")}\n{s["narration"]}\n');transcript.append(f'{s["start"]}–{s["end"]}s: {s["narration"]}')
(MEDIA/'captions.en.srt').write_text('\n'.join(srt));(MEDIA/'captions.en.vtt').write_text('\n'.join(vtt));(MEDIA/'transcript.en.txt').write_text('\n'.join(transcript)+'\n')
silent=work/'film-silent.mp4';encoder=subprocess.Popen(['ffmpeg','-y','-hide_banner','-loglevel','error','-f','image2pipe','-framerate',str(FPS),'-vcodec','png','-i','pipe:0','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-r','24',str(silent)],stdin=subprocess.PIPE)
frames=0;errors=[];screenshots=0
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
 page=browser.new_page(viewport={'width':1600,'height':900},device_scale_factor=1);page.on('pageerror',lambda e:errors.append(str(e)));page.goto((ROOT/'demo/film.html').as_uri());page.wait_for_function('!!window.WireFilm');page.evaluate('document.body.classList.add("capture-mode")')
 for i,s in enumerate(PLAN['scenes']):
  print(f'Render {i+1}/9: {s["id"]} / {s["seconds"]}s',flush=True);page.evaluate('i=>WireFilm.show(i)',i)
  page.wait_for_function('Array.from(document.images).filter(x=>x.offsetHeight>0).every(x=>x.complete&&x.naturalWidth>0)')
  page.evaluate('WireFilm.frame(1)');page.screenshot(path=str(MEDIA/f'storyboard-{i:02}.png'))
  if i==0:
   page.evaluate('WireFilm.frame(2.5)');page.screenshot(path=str(MEDIA/'poster.png'))
  cached=None;last_key=None
  for f in range(s['seconds']*FPS):
   t=f/FPS
   # Freeze static shots between small progress updates; render every actual 3D camera frame.
   key=f if s['id'] in ['hook','result'] or t<.55 else ('static',int(t//2),t>s['seconds']*.37 if s['id']=='top' else False)
   if key!=last_key:
    page.evaluate('t=>WireFilm.frame(t)',t);cached=page.screenshot(type='png',animations='disabled');screenshots+=1;last_key=key
   encoder.stdin.write(cached);frames+=1
 browser.close()
encoder.stdin.close();assert encoder.wait()==0;assert not errors,errors
subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(silent),'-i',str(MEDIA/'narration.en.wav'),'-c:v','copy','-af','loudnorm=I=-16:TP=-1.5:LRA=7','-c:a','aac','-b:a','160k','-movflags','+faststart','-shortest',str(MEDIA/'wiresight-demo.mp4')],check=True)
info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(MEDIA/'wiresight-demo.mp4')]))
video=next(x for x in info['streams'] if x['codec_type']=='video');audio=next(x for x in info['streams'] if x['codec_type']=='audio');duration=float(info['format']['duration']);assert abs(duration-PLAN['duration_seconds'])<.2
report={'captured_real_evidence_and_point_renderer':True,'model_invoked_for_annotation':False,'synthetic_narration':True,'voice_source':PLAN['narrator'],'audio_codec':audio['codec_name'],'video_codec':video['codec_name'],'width':video['width'],'height':video['height'],'duration_seconds':duration,'rendered_frames':frames,'rendered_camera_fps':FPS,'unique_screenshots':screenshots,'browser_errors':errors,'bytes':(MEDIA/'wiresight-demo.mp4').stat().st_size,'sha256':hashlib.sha256((MEDIA/'wiresight-demo.mp4').read_bytes()).hexdigest(),'caption_timing':'deterministic scene boundaries; exact voiced segments with silence padding','point_labels_modified':False}
(ROOT/'evidence/video_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
for sec in [2,13,29,43,60,78]:subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-ss',str(sec),'-i',str(MEDIA/'wiresight-demo.mp4'),'-frames:v','1',str(MEDIA/f'frame-{sec:02}.png')],check=True)
print(json.dumps(report,ensure_ascii=False,indent=2))
