"""Loopback-only simulator using the same rules, persistence and PNGs as the bot."""
import json
import base64
import binascii
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import re
import secrets
from urllib.parse import urlparse,parse_qs
from .game import GameError,public_view

WEB=Path(__file__).resolve().parents[1]/'web'


def server(store,port=8742):
    editor_key=secrets.token_hex(32)
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
                    self.user();return self.respond({'maps':store.catalog.choices(),'timezone':store.zone.key,'day':store.today().isoformat(),'discordConnected':False,'clueSource':'manual' if store.clues else 'generated','readySets':len(store.clues.published()) if store.clues else None})
                if path=='/api/manage/info':
                    if not store.clues:raise GameError('The clue editor requires manual mode.')
                    return self.respond({'key':editor_key,'maps':store.clues.management(store.catalog)})
                match=re.fullmatch(r'/api/manage/image/([a-f0-9]{64})\.png',path)
                if match and store.clues:return self.respond(store.clues.image(match[1]),mime='image/png')
                if path=='/api/stats':return self.respond(store.stats(self.user()))
                match=re.fullmatch(r'/api/image/([a-f0-9]{32})\.png',path)
                if match:
                    state=store.get(match[1],self.user());query=parse_qs(urlparse(self.path).query)
                    if str(state['version'])!=query.get('version',[''])[0]:return self.respond({'error':'Clue changed; refresh the round'},409)
                    clue=query.get('clue',[None])[0]
                    if clue is not None:clue=int(clue)
                    return self.respond(store.image(state,query.get('view',['iso'])[0],clue),mime='image/png')
                if path in ('/','/app.js','/style.css','/manage','/manage.js','/manage.css'):
                    name='index.html' if path=='/' else 'manage.html' if path=='/manage' else path[1:];mime='text/html' if name.endswith('.html') else 'text/css' if name.endswith('.css') else 'application/javascript'
                    return self.respond((WEB/name).read_bytes(),mime=mime)
                return self.respond({'error':'Not found'},404)
            except (GameError,ValueError) as exc:return self.respond({'error':str(exc)},400)
            except (BrokenPipeError,ConnectionResetError):return
        def do_POST(self):
            if not self.host_ok():return self.respond({'error':'Local host required'},403)
            if self.headers.get('Origin') not in (None,'http://'+self.headers.get('Host','')):return self.respond({'error':'Local origin required'},403)
            try:
                size=int(self.headers.get('Content-Length','0'))
                path=urlparse(self.path).path
                if path.startswith('/api/manage/'):
                    if not store.clues:raise GameError('The clue editor requires manual mode.')
                    if not secrets.compare_digest(self.headers.get('X-Portle-Editor',''),editor_key):return self.respond({'error':'Open the local clue editor first.'},403)
                    limit=12*1024*1024
                else:limit=8192
                if not 1<size<limit:raise GameError('Invalid request size')
                payload=json.loads(self.rfile.read(size))
                if not isinstance(payload,dict):raise GameError('Expected a JSON object')
                if path.startswith('/api/manage/'):
                    map_id=payload.get('mapId')
                    if map_id not in {m['id'] for m in store.catalog.maps}:raise GameError('Choose a map from the answer list.')
                    if path=='/api/manage/upload':
                        try:content=base64.b64decode(payload.get('image',''),validate=True)
                        except (ValueError,TypeError,binascii.Error) as exc:raise GameError('Invalid image upload.') from exc
                        store.clues.upload(map_id,payload.get('slot'),content)
                    elif path=='/api/manage/clear':store.clues.clear(map_id,payload.get('slot'))
                    elif path=='/api/manage/publish':store.clues.publish(map_id)
                    elif path=='/api/manage/unpublish':store.clues.unpublish(map_id)
                    else:return self.respond({'error':'Not found'},404)
                    return self.respond({'maps':store.clues.management(store.catalog)})
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
