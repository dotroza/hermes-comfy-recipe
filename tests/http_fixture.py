"""Controlled HTTP server used only by tests; never forwards to a real ComfyUI."""
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit, parse_qs

@contextmanager
def comfy_server():
    files={}; events=[]; fail=set(); corrupt=set(); races=set(); unavailable=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def answer(self,code,obj):
            raw=json.dumps(obj).encode(); self.send_response(code)
            self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw)))
            self.end_headers(); self.wfile.write(raw)
        def do_GET(self):
            u=urlsplit(self.path); events.append(('GET',self.path)); name=unquote(u.path.removeprefix('/api/userdata/'))
            if unavailable: return self.answer(503,{'error':'test outage'})
            if u.path=='/api/userdata': return self.answer(200,[k.removeprefix('workflows/') for k in files])
            if u.path.startswith('/api/userdata/'):
                if name not in files: return self.answer(404,{})
                return self.answer(200,{'corrupted':True} if name in corrupt else files[name])
            return self.answer(404,{})
        def do_POST(self):
            u=urlsplit(self.path); events.append(('POST',self.path))
            name=unquote(u.path.removeprefix('/api/userdata/')); q=parse_qs(u.query)
            if not u.path.startswith('/api/userdata/') or q.get('overwrite')!=['false']:
                return self.answer(400,{'error':'unsafe write'})
            value=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if name in fail: return self.answer(500,{'error':'test write failure'})
            if name in races: files[name]={'foreign':True}
            if name in files: return self.answer(409,{'error':'already exists'})
            files[name]=value; return self.answer(200,{})
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        yield {'url':f'http://127.0.0.1:{server.server_port}','root':'test-root','name':'test'},files,events,fail,corrupt,races,unavailable
    finally:
        server.shutdown(); server.server_close(); thread.join()
