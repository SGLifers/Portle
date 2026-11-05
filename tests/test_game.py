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
    def test_automatic_result_claim_requires_finished_owned_daily(self):
        state=self.start()
        self.assertFalse(self.store.claim_result_post(state['id'],'player'))
        with self.assertRaises(GameError):self.store.claim_result_post(state['id'],'other')
        practice=self.store.start('player','practice')
        practice=self.store.act(practice['id'],'player',0,guess=practice['puzzle']['map']['name'])
        self.assertFalse(self.store.claim_result_post(practice['id'],'player'))
    def test_automatic_result_claim_is_atomic_and_survives_restart(self):
        state=self.start();self.store.act(state['id'],'player',0,guess=state['puzzle']['map']['name'])
        with ThreadPoolExecutor(max_workers=4) as pool:
            claims=list(pool.map(lambda _:self.store.claim_result_post(state['id'],'player'),range(12)))
        self.assertEqual(sum(claims),1)
        other=GameStore(self.path,self.catalog,clock=lambda:self.now)
        self.assertFalse(other.claim_result_post(state['id'],'player'))
        other.record_result_post(state['id'],987)
        with other.connection() as db:row=db.execute('SELECT * FROM result_posts').fetchone()
        self.assertEqual(row['status'],'sent');self.assertEqual(row['message_id'],'987')
        self.assertFalse(other.claim_result_post(state['id'],'player'))
    def test_failed_result_post_is_not_automatically_retried(self):
        state=self.start();self.store.act(state['id'],'player',0,guess=state['puzzle']['map']['name'])
        self.assertTrue(self.store.claim_result_post(state['id'],'player'));self.store.record_result_post(state['id'])
        with self.store.connection() as db:self.assertEqual(db.execute('SELECT status FROM result_posts').fetchone()['status'],'failed')
        self.assertFalse(self.store.claim_result_post(state['id'],'player'))
        self.assertEqual(self.store.get(state['id'],'player')['status'],'won')
    def test_result_post_schema_upgrade_preserves_existing_progress(self):
        state=self.start();self.store.act(state['id'],'player',0,skip=True)
        with self.store.connection() as db:db.execute('DROP TABLE result_posts')
        upgraded=GameStore(self.path,self.catalog,clock=lambda:self.now)
        resumed=upgraded.start('player');self.assertEqual(resumed['id'],state['id']);self.assertEqual(resumed['version'],1)
        with upgraded.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM result_posts').fetchone()[0],0)
    def test_foreign_owner_cannot_read_or_mutate(self):
        s=self.start('a')
        with self.assertRaises(GameError):self.store.get(s['id'],'b')
        with self.assertRaises(GameError):self.store.act(s['id'],'b',0,skip=True)
    def test_restart_persists_daily_and_attempts(self):
        s=self.start();self.store.act(s['id'],'player',0,skip=True)
        other=GameStore(self.path,self.catalog,clock=lambda:self.now);again=other.start('player')
        self.assertEqual(again['id'],s['id']);self.assertEqual(again['puzzle'],s['puzzle']);self.assertEqual(again['version'],1)
    def test_reset_daily_preserves_history_others_practice_and_frozen_puzzle(self):
        yesterday=self.start();self.store.act(yesterday['id'],'player',0,guess=yesterday['puzzle']['map']['name'])
        self.now+=timedelta(days=1)
        today=self.start();today=self.store.act(today['id'],'player',0,guess=today['puzzle']['map']['name'],event_id='old-guess')
        other=self.start('other');other=self.store.act(other['id'],'other',0,skip=True)
        practice=self.store.start('player','practice');practice=self.store.act(practice['id'],'player',0,guess=practice['puzzle']['map']['name'])
        self.assertTrue(self.store.claim_result_post(today['id'],'player'));self.store.record_result_post(today['id'],123)
        result=self.store.reset_daily('player',actor_id='admin',guild_id='server',event_id='reset')
        self.assertTrue(result['changed']);self.assertEqual(result['day'],self.store.today().isoformat())
        fresh=self.start();self.assertNotEqual(fresh['id'],today['id']);self.assertEqual(fresh['puzzle'],today['puzzle'])
        self.assertEqual(fresh['attempts'],[]);self.assertEqual(fresh['version'],0);self.assertEqual(fresh['status'],'playing')
        self.assertEqual(self.store.stats('player')['played'],1);self.assertEqual(self.store.stats('player')['wins'],1)
        self.assertEqual(self.store.get(other['id'],'other'),other);self.assertEqual(self.store.get(practice['id'],'player'),practice)
        with self.assertRaises(GameError):self.store.get(today['id'],'player')
        with self.assertRaises(GameError):self.store.act(today['id'],'player',1,skip=True)
        with self.assertRaises(GameError):self.store.act(fresh['id'],'player',0,skip=True,event_id='old-guess')
        self.assertEqual(self.start()['version'],0)
        with self.store.connection() as db:
            audit=db.execute('SELECT * FROM daily_resets').fetchone()
            self.assertEqual(json.loads(audit['old_state']),today);self.assertEqual(audit['actor_id'],'admin')
            self.assertEqual(audit['new_round_id'],fresh['id']);self.assertEqual(audit['guild_id'],'server')
            self.assertEqual(db.execute('SELECT status FROM result_posts WHERE round_id=?',(today['id'],)).fetchone()['status'],'sent')
        self.store.act(fresh['id'],'player',0,guess=fresh['puzzle']['map']['name'])
        self.assertTrue(self.store.claim_result_post(fresh['id'],'player'))
    def test_reset_daily_is_idempotent_after_new_progress_and_restart(self):
        state=self.start();self.store.act(state['id'],'player',0,skip=True)
        for _ in range(2):self.store.reset_daily('player',actor_id='admin',guild_id='server',event_id='reset')
        fresh=self.start();self.store.act(fresh['id'],'player',0,skip=True)
        restarted=GameStore(self.path,self.catalog,clock=lambda:self.now)
        self.assertTrue(restarted.reset_daily('player',actor_id='admin',guild_id='server',event_id='reset')['changed'])
        self.assertEqual(restarted.start('player')['version'],1)
        with self.assertRaises(GameError):restarted.reset_daily('other',actor_id='admin',guild_id='server',event_id='reset')
    def test_reset_unplayed_or_fresh_daily_is_noop_even_when_replayed_later(self):
        result=self.store.reset_daily('new',actor_id='admin',guild_id='server',event_id='noop')
        self.assertFalse(result['changed'])
        state=self.start('new')
        self.assertFalse(self.store.reset_daily('new',actor_id='admin',guild_id='server',event_id='fresh')['changed'])
        self.assertEqual(self.start('new')['id'],state['id'])
        self.store.act(state['id'],'new',0,skip=True)
        self.assertFalse(self.store.reset_daily('new',actor_id='admin',guild_id='server',event_id='noop')['changed'])
        self.assertEqual(self.start('new')['version'],1)
    def test_reset_only_current_day_and_requires_server_event(self):
        state=self.start();self.store.act(state['id'],'player',0,guess=state['puzzle']['map']['name'])
        self.now+=timedelta(days=1)
        self.assertFalse(self.store.reset_daily('player',actor_id='admin',guild_id='server',event_id='tomorrow')['changed'])
        self.assertEqual(self.store.stats('player')['wins'],1)
        with self.assertRaises(GameError):self.store.reset_daily('player',actor_id='admin',guild_id=None,event_id='dm')
        with self.assertRaises(GameError):self.store.reset_daily('player',actor_id='admin',guild_id='server',event_id='')
    def test_reset_uses_configured_local_date_instead_of_utc_date(self):
        self.now=datetime(2026,11,4,2,tzinfo=timezone.utc)
        local=GameStore(self.path,self.catalog,'America/Los_Angeles',clock=lambda:self.now)
        state=local.start('player');local.act(state['id'],'player',0,skip=True)
        result=local.reset_daily('player',actor_id='admin',guild_id='server',event_id='local-day')
        self.assertTrue(result['changed']);self.assertEqual(result['day'],'2026-11-03')
        self.assertEqual(local.start('player')['version'],0)
    def test_concurrent_reset_deliveries_archive_once_and_leave_one_fresh_round(self):
        state=self.start();self.store.act(state['id'],'player',0,skip=True)
        def reset(_):return self.store.reset_daily('player',actor_id='admin',guild_id='server',event_id='same-reset')
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(reset,range(12)))
        self.assertTrue(all(r['changed'] for r in results));self.assertEqual(self.start()['version'],0)
        with self.store.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM daily_resets').fetchone()[0],1)
    def test_reset_lost_daily_removes_loss_from_stats(self):
        state=self.start()
        for version in range(6):state=self.store.act(state['id'],'player',version,skip=True)
        self.assertEqual(self.store.stats('player')['played'],1)
        self.store.reset_daily('player',actor_id='admin',guild_id='server',event_id='lost')
        self.assertEqual(self.store.stats('player')['played'],0);self.assertEqual(self.start()['attempts'],[])
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
