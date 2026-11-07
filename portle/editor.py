"""Loopback-only screenshot clue editor; gameplay is available in Discord."""
import json
import base64
import binascii
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import re
import secrets
from urllib.parse import urlparse
from .game import GameError

WEB=Path(__file__).resolve().parents[1]/'web'


def server(catalog,clues,port=8742):
    editor_key=secrets.token_hex(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def respond(self,value,code=200,mime='application/json'):
            body=json.dumps(value).encode() if mime=='application/json' else value
            self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(body)
        def host_ok(self):return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
        def do_GET(self):
            if not self.host_ok():return self.respond({'error':'Local host required'},403)
            path=urlparse(self.path).path
            try:
                if path=='/api/manage/info':
                    return self.respond({'key':editor_key,'maps':clues.management(catalog)})
                match=re.fullmatch(r'/api/manage/image/([a-f0-9]{64})\.png',path)
                if match:return self.respond(clues.image(match[1]),mime='image/png')
                if path in ('/','/manage','/manage.js','/manage.css'):
                    name='manage.html' if path in ('/','/manage') else path[1:];mime='text/html' if name.endswith('.html') else 'text/css' if name.endswith('.css') else 'application/javascript'
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
                if path not in ('/api/manage/upload','/api/manage/clear','/api/manage/publish','/api/manage/unpublish'):
                    return self.respond({'error':'Not found'},404)
                if not secrets.compare_digest(self.headers.get('X-Portle-Editor',''),editor_key):return self.respond({'error':'Open the local clue editor first.'},403)
                limit=12*1024*1024
                if not 1<size<limit:raise GameError('Invalid request size')
                payload=json.loads(self.rfile.read(size))
                if not isinstance(payload,dict):raise GameError('Expected a JSON object')
                map_id=payload.get('mapId')
                if map_id not in {m['id'] for m in catalog.maps}:raise GameError('Choose a map from the answer list.')
                if path=='/api/manage/upload':
                    try:content=base64.b64decode(payload.get('image',''),validate=True)
                    except (ValueError,TypeError,binascii.Error) as exc:raise GameError('Invalid image upload.') from exc
                    clues.upload(map_id,payload.get('slot'),content)
                elif path=='/api/manage/clear':clues.clear(map_id,payload.get('slot'))
                elif path=='/api/manage/publish':clues.publish(map_id)
                elif path=='/api/manage/unpublish':clues.unpublish(map_id)
                else:return self.respond({'error':'Not found'},404)
                return self.respond({'maps':clues.management(catalog)})
            except (GameError,ValueError,TypeError) as exc:return self.respond({'error':str(exc)},400)
            except (BrokenPipeError,ConnectionResetError):return
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def serve(catalog,clues,port):
    http=server(catalog,clues,port)
    print(f'Portle clue editor: http://127.0.0.1:{http.server_port}/manage',flush=True)
    try:http.serve_forever()
    except KeyboardInterrupt:pass
    finally:http.server_close()
