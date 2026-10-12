"""Serve only the release directory, bound to localhost by default."""
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import argparse,shutil,re
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8000);p.add_argument('--download',type=Path,help='Optional release ZIP served at /download.zip');a=p.parse_args()
class Handler(SimpleHTTPRequestHandler):
 def do_GET(self):
  if self.path=='/':
   self.send_response(302);self.send_header('Location','/demo/');self.end_headers();return
  if self.path=='/download.zip' and a.download and a.download.is_file():
   self.send_response(200);self.send_header('Content-Type','application/zip');self.send_header('Content-Length',str(a.download.stat().st_size));self.send_header('Content-Disposition',f'attachment; filename="{a.download.name}"');self.end_headers()
   try:
    with a.download.open('rb') as f:shutil.copyfileobj(f,self.wfile)
   except (BrokenPipeError,ConnectionResetError):pass
   return
  super().do_GET()
 def do_HEAD(self):
  if self.path=='/download.zip' and a.download and a.download.is_file():
   self.send_response(200);self.send_header('Content-Type','application/zip');self.send_header('Content-Length',str(a.download.stat().st_size));self.end_headers();return
  super().do_HEAD()
 def send_head(self):
  self.__dict__.pop('byte_range',None)
  path=Path(self.translate_path(self.path))
  if path.suffix.lower()!='.mp4' or not path.is_file():return super().send_head()
  size=path.stat().st_size;start,end=0,size-1;status=200
  header=self.headers.get('Range')
  if header:
   m=re.fullmatch(r'bytes=(\d*)-(\d*)',header)
   if not m or not any(m.groups()):self.send_error(416);return None
   left,right=m.groups()
   if left:start=int(left);end=min(int(right),size-1) if right else size-1
   else:start=max(0,size-int(right))
   if start>=size or start>end:
    self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return None
   status=206
  f=path.open('rb');f.seek(start);self.byte_range=(start,end)
  self.send_response(status);self.send_header('Content-Type',self.guess_type(str(path)));self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(end-start+1))
  if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
  self.end_headers();return f
 def copyfile(self,source,outputfile):
  if not hasattr(self,'byte_range'):return super().copyfile(source,outputfile)
  remaining=self.byte_range[1]-self.byte_range[0]+1
  try:
   while remaining:
    chunk=source.read(min(1<<20,remaining))
    if not chunk:break
    outputfile.write(chunk);remaining-=len(chunk)
  except (BrokenPipeError,ConnectionResetError):pass
 def do_POST(self):
  self.send_error(410,'Recorded evidence viewer only. No model can be launched through this page.')
print(f'WireSight recorded demo: http://{a.host}:{a.port}/demo/',flush=True)
ThreadingHTTPServer((a.host,a.port),partial(Handler,directory=str(ROOT))).serve_forever()
