from http.cookiejar import CookieJar
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from io import BytesIO
from PIL import Image
from portle.preview import server
from portle.store import GameStore
from helpers import fixture_catalog


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=GameStore(Path(self.temp.name)/'preview.db',fixture_catalog())
        self.http=server(self.store,0);self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.http.server_port)
        self.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    def tearDown(self):self.http.shutdown();self.http.server_close();self.thread.join();self.temp.cleanup()
    def request(self,path,payload=None,client=None,headers=None):
        request=urllib.request.Request(self.base+path,data=json.dumps(payload).encode() if payload is not None else None,headers=headers or {})
        try:
            with (client or self.client).open(request,timeout=5) as response:return response.status,response.read(),response.headers
        except urllib.error.HTTPError as exc:return exc.code,exc.read(),exc.headers
    def start(self):return json.loads(self.request('/api/start',{'mode':'daily'})[1])
    def test_browser_payload_hides_answer_but_renders_real_clue(self):
        state=self.start();self.assertNotIn('answer',state);self.assertNotIn('puzzle',state)
        code,data,headers=self.request(f"/api/image/{state['id']}.png?version=0&view=iso")
        self.assertEqual(code,200);self.assertEqual(headers['Content-Type'],'image/png')
        image=Image.open(BytesIO(data));self.assertEqual(image.size,(1100,760));self.assertEqual(image.info,{})
    def test_skip_updates_stage_and_old_image_version_rejected(self):
        state=self.start();code,data,_=self.request('/api/action',{'id':state['id'],'version':0,'skip':True});self.assertEqual(code,200)
        self.assertEqual(json.loads(data)['portalCount'],2)
        self.assertEqual(self.request(f"/api/image/{state['id']}.png?version=0")[0],409)
    def test_other_cookie_cannot_fetch_private_clue(self):
        state=self.start();other=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        self.assertEqual(self.request(f"/api/image/{state['id']}.png?version=0",client=other)[0],400)
    def test_invalid_guess_does_not_advance(self):
        state=self.start();self.assertEqual(self.request('/api/action',{'id':state['id'],'version':0,'guess':'not a map'})[0],400)
        self.assertEqual(self.start()['version'],0)
    def test_finished_round_has_answer_and_spoiler_free_share(self):
        state=self.start()
        for i in range(6):code,data,_=self.request('/api/action',{'id':state['id'],'version':i,'skip':True})
        done=json.loads(data);self.assertEqual(done['status'],'lost');self.assertIn('answer',done);self.assertNotIn(done['answer'],done['share'])
    def test_local_host_and_origin_guards(self):
        self.assertEqual(self.request('/api/info',headers={'Host':'foreign.example'})[0],403)
        self.assertEqual(self.request('/api/start',{'mode':'daily'},headers={'Origin':'https://foreign.example'})[0],403)
    def test_private_files_not_served(self):
        for path in ['/.env','/data/catalog.json','/data/portle.sqlite3','/../portle/store.py']:
            self.assertEqual(self.request(path)[0],404)
    def test_malformed_actions_return_json_error(self):
        for payload in [[],{'id':{},'version':0},{'id':'abc','skip':True},{'id':'a'*32,'skip':'yes'}]:
            code,body,_=self.request('/api/action',payload);self.assertEqual(code,400);self.assertIn('error',json.loads(body))
    def test_cookie_private_and_same_site(self):
        _,_,headers=self.request('/api/info');self.assertIn('HttpOnly',headers['Set-Cookie']);self.assertIn('SameSite=Strict',headers['Set-Cookie'])
