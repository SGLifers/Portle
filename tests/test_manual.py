import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from io import BytesIO
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from PIL import Image,PngImagePlugin
from portle.catalog import Catalog
from portle.clues import ClueLibrary
from portle.game import GameError,public_view
from portle.editor import server
from portle.store import GameStore


def screenshot(number=1):
    buffer=BytesIO();info=PngImagePlugin.PngInfo();info.add_text('Answer','Academy-secret-filename')
    Image.new('RGB',(32,24),(number*30,10,15)).save(buffer,format='PNG',pnginfo=info);return buffer.getvalue()


class ManualFixture:
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.library=ClueLibrary(self.root/'clues')
        self.catalog=Catalog.names();self.mid=self.catalog.maps[0]['id'];self.now=datetime(2026,11,3,12,tzinfo=timezone.utc)
        self.store=GameStore(self.root/'game.db',self.catalog,clock=lambda:self.now,clues=self.library)
    def tearDown(self):self.temp.cleanup()
    def pack(self):
        for i in range(1,7):self.library.upload(self.mid,i,screenshot(i))
        self.library.publish(self.mid)


class ManualTests(ManualFixture,unittest.TestCase):
    def test_names_only_catalog_has_no_game_geometry(self):
        self.assertGreater(len(self.catalog.maps),1)
        self.assertTrue(all('portals' not in m for m in self.catalog.maps))
    def test_renamed_map_keeps_clues_and_old_daily_answerable(self):
        self.mid='MAP_Erosion';self.pack()
        previous=Catalog(tuple(dict(m,name='Erosion',aliases=[]) if m['id']==self.mid else m for m in self.catalog.maps),'previous-name')
        old=GameStore(self.root/'game.db',previous,clock=lambda:self.now,clues=self.library)
        state=old.start('u');image=old.image(state)
        renamed=GameStore(self.root/'game.db',self.catalog,clock=lambda:self.now,clues=self.library)
        self.assertIn('Dought',self.catalog.choices());self.assertNotIn('Erosion',self.catalog.choices())
        self.assertEqual(self.catalog.resolve('Dought')['id'],self.catalog.resolve('Erosion')['id'])
        won=renamed.act(state['id'],'u',0,guess='Dought')
        self.assertEqual(won['status'],'won');self.assertEqual(won['puzzle'],state['puzzle'])
        self.assertEqual(renamed.image(state,clue=1),image)
        second=renamed.start('other');self.assertEqual(renamed.act(second['id'],'other',0,guess='Erosion')['status'],'won')
    def test_empty_library_and_drafts_cannot_be_played(self):
        for i in range(1,6):self.library.upload(self.mid,i,screenshot(i))
        with self.assertRaises(GameError):self.library.publish(self.mid)
        with self.assertRaises(GameError):self.store.start('u')
    def test_images_preserve_pixels_strip_metadata_and_use_opaque_ids(self):
        digest=self.library.upload(self.mid,1,screenshot())
        self.assertEqual(len(digest),64)
        image=Image.open(BytesIO(self.library.image(digest)))
        self.assertEqual(image.size,(32,24));self.assertEqual(image.getpixel((0,0)),(30,10,15));self.assertEqual(image.info,{})
    def test_invalid_images_slots_and_path_traversal_rejected(self):
        for content in [b'not an image',b'<svg/>',b'']:
            with self.assertRaises(GameError):self.library.upload(self.mid,1,content)
        for slot in [0,7,True,'1']:
            with self.assertRaises(GameError):self.library.upload(self.mid,slot,screenshot())
        with self.assertRaises(GameError):self.library.image('../index.json')
    def test_six_screenshots_are_revealed_in_order_and_future_clues_denied(self):
        self.pack();s=self.store.start('u')
        for stage in range(1,7):
            self.assertEqual(Image.open(BytesIO(self.store.image(s))).getpixel((0,0)),(stage*30,10,15))
            if stage<6:
                with self.assertRaises(GameError):self.store.image(s,clue=stage+1)
            self.assertEqual(Image.open(BytesIO(self.store.image(s,clue=1))).getpixel((0,0)),(30,10,15))
            s=self.store.act(s['id'],'u',s['version'],skip=True)
        self.assertEqual(s['status'],'lost');self.assertEqual(public_view(s)['revealedClues'],6)
    def test_answer_and_source_hashes_not_in_active_payload(self):
        self.pack();s=self.store.start('u');view=public_view(s)
        self.assertEqual(view['clueSource'],'manual');self.assertIsNone(view['portalCount'])
        payload=json.dumps(view)
        for secret in [s['puzzle']['map']['name'],self.mid,*s['puzzle']['clueImages']]:self.assertNotIn(secret,payload)
    def test_correct_answer_unlocks_final_authored_image(self):
        self.pack();s=self.store.start('u');s=self.store.act(s['id'],'u',0,guess=s['puzzle']['map']['name'])
        self.assertEqual(s['status'],'won');self.assertEqual(Image.open(BytesIO(self.store.image(s))).getpixel((0,0)),(180,10,15))
    def test_republishing_and_clearing_draft_do_not_change_started_daily(self):
        self.pack();s=self.store.start('u');original=self.store.image(s)
        self.library.upload(self.mid,1,screenshot(5));self.library.publish(self.mid);self.library.clear(self.mid,2)
        self.assertEqual(self.store.image(self.store.start('u')),original)
        self.now+=timedelta(days=1)
        self.assertNotEqual(self.store.image(self.store.start('u')),original)
    def test_unpublish_keeps_started_round_and_restarts_safe(self):
        self.pack();s=self.store.start('u');self.library.unpublish(self.mid)
        restored=GameStore(self.root/'game.db',self.catalog,clock=lambda:self.now,clues=ClueLibrary(self.root/'clues'))
        self.assertEqual(restored.start('u'),s);self.assertEqual(restored.image(s),self.store.image(s))
        self.now+=timedelta(days=1)
        with self.assertRaises(GameError):restored.start('u')
    def test_reset_reuses_frozen_manual_clues_and_preserves_legacy_scores(self):
        from helpers import fixture_catalog
        self.pack();state=self.store.start('u');first=self.store.image(state)
        self.store.act(state['id'],'u',0,guess=state['puzzle']['map']['name'])
        legacy=GameStore(self.root/'game.db',fixture_catalog(),clock=lambda:self.now)
        old=legacy.start('u');old=legacy.act(old['id'],'u',0,guess=old['puzzle']['map']['name'])
        self.library.upload(self.mid,1,screenshot(5));self.library.publish(self.mid);self.library.unpublish(self.mid)
        result=self.store.reset_daily('u',actor_id='admin',guild_id='server',event_id='manual-reset')
        self.assertTrue(result['changed']);fresh=self.store.start('u')
        self.assertEqual(fresh['puzzle'],state['puzzle']);self.assertEqual(self.store.image(fresh),first)
        self.assertEqual(self.store.stats('u')['played'],0);self.assertEqual(legacy.stats('u')['wins'],1)
        self.assertEqual(legacy.get(old['id'],'u'),old)
    def test_changed_media_is_detected(self):
        digest=self.library.upload(self.mid,1,screenshot());(self.library.root/'images'/(digest+'.png')).write_bytes(b'changed')
        with self.assertRaises(GameError):self.library.image(digest)
    def test_drafts_persist_and_do_not_replace_published_version(self):
        self.pack();published=self.library.published()[self.mid];self.library.clear(self.mid,1)
        other=ClueLibrary(self.root/'clues');self.assertEqual(other.published()[self.mid],published)
        self.assertIsNone(other.management(self.catalog)[0]['draft'][0])
    def test_parallel_uploads_do_not_lose_other_slots(self):
        def upload(i):return ClueLibrary(self.root/'clues').upload(self.mid,i,screenshot(i))
        with ThreadPoolExecutor(max_workers=4) as pool:digests=list(pool.map(upload,range(1,7)))
        self.library.publish(self.mid);self.assertEqual(self.library.published()[self.mid]['images'],digests)
    def test_manual_stats_are_separate_from_legacy_generated_rounds(self):
        from helpers import fixture_catalog
        legacy=GameStore(self.root/'game.db',fixture_catalog(),clock=lambda:self.now)
        old=legacy.start('u');legacy.act(old['id'],'u',0,guess=old['puzzle']['map']['name'])
        self.assertEqual(self.store.stats('u')['played'],0)
        self.pack();current=self.store.start('u');self.store.act(current['id'],'u',0,guess=current['puzzle']['map']['name'])
        self.assertEqual(self.store.stats('u')['played'],1);self.assertEqual(legacy.stats('u')['played'],1)


class ManualHttpTests(ManualFixture,unittest.TestCase):
    def setUp(self):
        super().setUp();self.http=server(self.catalog,self.library,0)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.http.server_port)
        self.client=urllib.request.build_opener()
        self.key=json.loads(self.request('/api/manage/info')[1])['key']
    def tearDown(self):self.http.shutdown();self.http.server_close();self.thread.join();super().tearDown()
    def request(self,path,payload=None,headers=None):
        request=urllib.request.Request(self.base+path,data=json.dumps(payload).encode() if payload is not None else None,headers=headers or {})
        try:
            with self.client.open(request,timeout=5) as response:return response.status,response.read()
        except urllib.error.HTTPError as exc:return exc.code,exc.read()
    def test_editor_mutations_require_capability_and_same_origin(self):
        payload={'mapId':self.mid,'slot':1,'image':base64.b64encode(screenshot()).decode()}
        self.assertEqual(self.request('/api/manage/upload',payload)[0],403)
        self.assertEqual(self.request('/api/manage/upload',payload,{'X-Portle-Editor':self.key,'Origin':'https://foreign.example'})[0],403)
        self.assertEqual(self.request('/api/manage/upload',payload,{'X-Portle-Editor':self.key})[0],200)
    def test_editor_html_and_private_files_not_exposed(self):
        self.assertIn(b'Build a clue set',self.request('/manage')[1])
        self.assertEqual(self.request('/data/clues/index.json')[0],404)
        self.assertEqual(self.request('/api/manage/image/../../index.json')[0],404)
    def test_root_and_manage_are_editor_only(self):
        code,html=self.request('/')
        self.assertEqual(code,200);self.assertEqual(html,self.request('/manage')[1])
        self.assertIn(b'Build a clue set',html)
        self.assertNotIn(b'Back to game',html);self.assertNotIn(b'Play Portle',html)
        for path in ['/manage.css','/manage.js']:self.assertEqual(self.request(path)[0],200)
    def test_browser_gameplay_routes_and_assets_are_removed(self):
        for path in ['/api/info','/api/stats','/api/image/'+'a'*32+'.png?version=0','/app.js','/style.css','/index.html']:
            self.assertEqual(self.request(path)[0],404,path)
        for path in ['/api/start','/api/action']:
            self.assertEqual(self.request(path,{'mode':'daily'})[0],404,path)
    def test_editor_publish_review_clear_and_unpublish(self):
        headers={'X-Portle-Editor':self.key}
        for slot in range(1,7):
            code,body=self.request('/api/manage/upload',{'mapId':self.mid,'slot':slot,'image':base64.b64encode(screenshot(slot)).decode()},headers)
            self.assertEqual(code,200)
        digest=json.loads(body)['maps'][0]['draft'][0]
        code,image=self.request(f'/api/manage/image/{digest}.png')
        self.assertEqual(code,200);self.assertEqual(Image.open(BytesIO(image)).getpixel((0,0)),(30,10,15))
        self.assertEqual(self.request('/api/manage/publish',{'mapId':self.mid},headers)[0],200)
        self.assertIn(self.mid,self.library.published())
        self.assertEqual(self.request('/api/manage/clear',{'mapId':self.mid,'slot':1},headers)[0],200)
        self.assertIn(self.mid,self.library.published())
        self.assertEqual(self.request('/api/manage/unpublish',{'mapId':self.mid},headers)[0],200)
        self.assertNotIn(self.mid,self.library.published())
    def test_editor_rejects_foreign_host_and_private_paths(self):
        self.assertEqual(self.request('/api/manage/info',headers={'Host':'foreign.example'})[0],403)
        for path in ['/.env','/data/portle.sqlite3','/../portle/store.py']:
            self.assertEqual(self.request(path)[0],404)
    def test_malformed_editor_requests_are_errors_without_mutation(self):
        headers={'X-Portle-Editor':self.key}
        for payload in [[],{'mapId':'not-a-map'},{'mapId':self.mid,'slot':1,'image':'not base64!'}]:
            code,body=self.request('/api/manage/upload',payload,headers)
            self.assertEqual(code,400);self.assertIn('error',json.loads(body))
        self.assertEqual(self.library.published(),{})
        self.assertTrue(all(value is None for value in self.library.management(self.catalog)[0]['draft']))


if __name__=='__main__':unittest.main()
