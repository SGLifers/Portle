"""Loopback-only simulator using the same rules, persistence and PNGs as the bot."""
import json
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import re
import secrets
from urllib.parse import urlparse,parse_qs
from .game import GameError,public_view
from .render import png

WEB=Path(__file__).resolve().parents[1]/'web'


def server(store,port=8742):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def user(self):
            cookie=SimpleCookie()
            try:cookie.load(self.headers.get('Cookie',''))
            except Exception:pass
            key=cookie.get('portle_preview')
            if key and re.fullmatch(r'[a-f0-9]{48}',key.value):return key.value
            if not hasattr(self,'new_user'):self.new_user=secrets.token_hex(24)
            return self.new_user
        def respond(self,value,code=200,mime='application/json'):
            body=json.dumps(value).encode() if mime=='application/json' else value
            self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'")
            if hasattr(self,'new_user'):self.send_header('Set-Cookie',f'portle_preview={self.new_user}; HttpOnly; SameSite=Strict; Path=/; Max-Age=31536000')
            self.end_headers();self.wfile.write(body)
        def host_ok(self):return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
        def do_GET(self):
            if not self.host_ok():return self.respond({'error':'Local host required'},403)
            path=urlparse(self.path).path
            try:
                if path=='/api/info':
                    self.user();return self.respond({'maps':store.catalog.choices(),'timezone':store.zone.key,'day':store.today().isoformat(),'discordConnected':False})
                if path=='/api/stats':return self.respond(store.stats(self.user()))
                match=re.fullmatch(r'/api/image/([a-f0-9]{32})\.png',path)
                if match:
                    state=store.get(match[1],self.user());query=parse_qs(urlparse(self.path).query)
                    if str(state['version'])!=query.get('version',[''])[0]:return self.respond({'error':'Clue changed; refresh the round'},409)
                    return self.respond(png(state,query.get('view',['iso'])[0]),mime='image/png')
                if path in ('/','/app.js','/style.css'):
                    name='index.html' if path=='/' else path[1:];mime='text/html' if name.endswith('.html') else 'text/css' if name.endswith('.css') else 'application/javascript'
                    return self.respond((WEB/name).read_bytes(),mime=mime)
                return self.respond({'error':'Not found'},404)
            except (GameError,ValueError) as exc:return self.respond({'error':str(exc)},400)
            except (BrokenPipeError,ConnectionResetError):return
        def do_POST(self):
            if not self.host_ok():return self.respond({'error':'Local host required'},403)
            if self.headers.get('Origin') not in (None,'http://'+self.headers.get('Host','')):return self.respond({'error':'Local origin required'},403)
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 1<size<8192:raise GameError('Invalid request size')
                payload=json.loads(self.rfile.read(size))
                if not isinstance(payload,dict):raise GameError('Expected a JSON object')
                path=urlparse(self.path).path
                if path=='/api/start':state=store.start(self.user(),payload.get('mode','daily'))
                elif path=='/api/action':
                    skip=payload.get('skip',False);guess=payload.get('guess')
                    if not isinstance(payload.get('id'),str) or not re.fullmatch(r'[a-f0-9]{32}',payload['id']):raise GameError('Invalid round')
                    if not isinstance(skip,bool) or (guess is not None and (not isinstance(guess,str) or len(guess)>80)):raise GameError('Invalid guess')
                    event=payload.get('eventId')
                    if event is not None and (not isinstance(event,str) or len(event)>128):raise GameError('Invalid interaction')
                    state=store.act(payload.get('id',''),self.user(),payload.get('version'),guess=guess,skip=skip,event_id=event)
                else:return self.respond({'error':'Not found'},404)
                return self.respond(public_view(state))
            except (GameError,ValueError,TypeError) as exc:return self.respond({'error':str(exc)},400)
            except (BrokenPipeError,ConnectionResetError):return
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def serve(store,port):
    http=server(store,port)
    print(f'Portle local preview: http://127.0.0.1:{http.server_port} (Discord is not connected)',flush=True)
    try:http.serve_forever()
    except KeyboardInterrupt:pass
    finally:http.server_close()
