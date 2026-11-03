from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest

from portle.catalog import Catalog,normalize
from portle.game import GameError,clue_count,public_view,share_text
from portle.store import GameStore
from helpers import fixture_catalog


class GameTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'game.sqlite3';self.catalog=fixture_catalog()
        self.now=datetime(2026,11,3,12,tzinfo=timezone.utc);self.store=GameStore(self.path,self.catalog,clock=lambda:self.now)
    def tearDown(self):self.temp.cleanup()
    def start(self,user='player'):return self.store.start(user)
    def wrong(self,state):return next(m['name'] for m in self.catalog.maps if m['id']!=state['puzzle']['map']['id'])
    def test_daily_shared_map_private_independent_progress(self):
        a=self.start('a');b=self.start('b');self.assertEqual(a['puzzle'],b['puzzle']);self.assertNotEqual(a['id'],b['id'])
        self.store.act(a['id'],'a',0,skip=True);self.assertEqual(self.store.get(b['id'],'b')['version'],0)
    def test_six_stages_reveal_nested_real_portals(self):
        state=self.start();order=state['puzzle']['order'];self.assertEqual(len(set(order)),40)
        for turn,expected in enumerate([1,2,4,8,16,40]):
            self.assertEqual(clue_count(state),expected)
            self.assertEqual(len(state['puzzle']['order'][:expected]),expected)
            state=self.store.act(state['id'],'player',turn,skip=True)
        self.assertEqual(state['status'],'lost');self.assertEqual(state['version'],6)
    def test_correct_guess_ends_immediately(self):
        s=self.start();s=self.store.act(s['id'],'player',0,guess=s['puzzle']['map']['name'])
        self.assertEqual(s['status'],'won');self.assertEqual(s['version'],1);self.assertIn('1/6',share_text(s))
        self.assertEqual(public_view(s)['turn'],1)
        with self.assertRaises(GameError):self.store.act(s['id'],'player',1,skip=True)
    def test_final_turn_can_win(self):
        s=self.start()
        for i in range(5):s=self.store.act(s['id'],'player',i,skip=True)
        s=self.store.act(s['id'],'player',5,guess=s['puzzle']['map']['name']);self.assertEqual(s['status'],'won');self.assertIn('6/6',share_text(s))
    def test_invalid_and_duplicate_guesses_are_free(self):
        s=self.start()
        with self.assertRaises(GameError):self.store.act(s['id'],'player',0,guess='No such map')
        self.assertEqual(self.store.get(s['id'],'player')['version'],0)
        s=self.store.act(s['id'],'player',0,guess=self.wrong(s))
        with self.assertRaises(GameError):self.store.act(s['id'],'player',1,guess=self.wrong(s))
        self.assertEqual(self.store.get(s['id'],'player')['version'],1)
    def test_normalization_and_aliases(self):
        self.assertEqual(normalize('Zén-Garden!'),'zengarden');self.assertEqual(self.catalog.resolve('zG')['name'],'Zen Garden')
    def test_stale_interaction_does_not_spend_another_guess(self):
        s=self.start();self.store.act(s['id'],'player',0,skip=True)
        with self.assertRaises(GameError):self.store.act(s['id'],'player',0,skip=True)
        self.assertEqual(self.store.get(s['id'],'player')['version'],1)
    def test_duplicate_delivery_is_idempotent(self):
        s=self.start()
        for _ in range(3):self.store.act(s['id'],'player',0,skip=True,event_id='event')
        self.assertEqual(self.store.get(s['id'],'player')['version'],1)
    def test_concurrent_actions_spend_one_turn(self):
        s=self.start()
        def submit(i):
            try:self.store.act(s['id'],'player',0,skip=True,event_id=str(i));return True
            except GameError:return False
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(submit,range(12)))
        self.assertEqual(sum(results),1);self.assertEqual(self.store.get(s['id'],'player')['version'],1)
    def test_foreign_owner_cannot_read_or_mutate(self):
        s=self.start('a')
        with self.assertRaises(GameError):self.store.get(s['id'],'b')
        with self.assertRaises(GameError):self.store.act(s['id'],'b',0,skip=True)
    def test_restart_persists_daily_and_attempts(self):
        s=self.start();self.store.act(s['id'],'player',0,skip=True)
        other=GameStore(self.path,self.catalog,clock=lambda:self.now);again=other.start('player')
        self.assertEqual(again['id'],s['id']);self.assertEqual(again['puzzle'],s['puzzle']);self.assertEqual(again['version'],1)
    def test_rollover_closes_previous_daily(self):
        s=self.start();self.now+=timedelta(days=1);new=self.start()
        self.assertNotEqual(s['puzzle']['id'],new['puzzle']['id'])
        with self.assertRaises(GameError):self.store.act(s['id'],'player',0,skip=True)
    def test_practice_does_not_change_daily_or_stats(self):
        daily=self.start();practice=self.store.start('player','practice')
        self.store.act(practice['id'],'player',0,guess=practice['puzzle']['map']['name'])
        self.assertEqual(self.store.stats('player')['played'],0);self.assertEqual(self.start()['id'],daily['id'])
    def test_unfinished_answer_not_in_client_view_or_share(self):
        s=self.start();payload=public_view(s);answer=s['puzzle']['map']
        for key in ['puzzle','order','user_id','map','portals','answer','catalogRevision']:self.assertNotIn(key,payload)
        self.assertNotIn(answer['id'],json.dumps(payload))
        with self.assertRaises(GameError):share_text(s)
        solved=self.store.act(s['id'],'player',0,guess=answer['name'])
        self.assertEqual(public_view(solved)['answer'],answer['name']);self.assertNotIn(answer['name'],share_text(solved))
    def test_frozen_puzzle_survives_catalog_change(self):
        s=self.start();answer=s['puzzle']['map'];maps=tuple(m for m in self.catalog.maps if m['id']!=answer['id'])
        other=GameStore(self.path,Catalog(maps,'changed'),clock=lambda:self.now)
        self.assertEqual(other.start('player')['puzzle'],s['puzzle'])
        self.assertEqual(other.act(s['id'],'player',0,guess=answer['name'])['status'],'won')
    def test_streaks_and_distribution(self):
        for i in range(3):
            s=self.start();self.store.act(s['id'],'player',0,guess=s['puzzle']['map']['name']);self.now+=timedelta(days=1)
        stats=self.store.stats('player');self.assertEqual(stats['currentStreak'],3);self.assertEqual(stats['distribution']['1'],3)
        s=self.start()
        for i in range(6):self.store.act(s['id'],'player',i,skip=True)
        stats=self.store.stats('player');self.assertEqual(stats['currentStreak'],0);self.assertEqual(stats['bestStreak'],3);self.assertEqual(stats['played'],4)
    def test_missing_day_breaks_streak(self):
        s=self.start();self.store.act(s['id'],'player',0,guess=s['puzzle']['map']['name']);self.now+=timedelta(days=2)
        self.assertEqual(self.store.stats('player')['currentStreak'],0)
    def test_daily_rotation_uses_full_pool_before_repeating(self):
        ids=[]
        for _ in range(len(self.catalog.maps)):
            ids.append(self.start()['puzzle']['map']['id']);self.now+=timedelta(days=1)
        self.assertEqual(len(set(ids)),len(self.catalog.maps))
    def test_timezone_rollover(self):
        self.now=datetime(2026,11,3,2,tzinfo=timezone.utc)
        store=GameStore(self.path,self.catalog,'America/Los_Angeles',clock=lambda:self.now)
        self.assertEqual(store.today().isoformat(),'2026-11-02')
