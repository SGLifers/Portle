from concurrent.futures import ThreadPoolExecutor
from datetime import date,datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from portle.announcements import board_embeds,due_periods,message_pages,ranked,text_length
from portle.game import GameError
from portle.store import GameStore
from helpers import fixture_catalog


class AnnouncementTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'scores.db'
        self.now=datetime(2026,11,1,12,tzinfo=timezone.utc)
        self.store=GameStore(self.path,fixture_catalog(),clock=lambda:self.now)
        self.manager=self.store.announcements
        self.config=self.manager.configure(22,33)
    def tearDown(self):self.temp.cleanup()
    def play(self,user,day=8,clues=1,*,guild=22,win=True,mode='daily',unfinished=False):
        self.now=datetime(2026,11,day,12,tzinfo=timezone.utc)
        state=self.store.start(str(user),mode,guild)
        for _ in range(clues-1):state=self.store.act(state['id'],str(user),state['version'],skip=True)
        if unfinished:return self.store.act(state['id'],str(user),state['version'],skip=True)
        if win:return self.store.act(state['id'],str(user),state['version'],guess=state['puzzle']['map']['name'])
        while state['status']=='playing':state=self.store.act(state['id'],str(user),state['version'],skip=True)
        return state
    def close_day(self):self.now=datetime(2026,11,9,0,11,tzinfo=timezone.utc)
    def batch(self,kind='daily'):
        self.close_day();self.manager.prepare(self.config,kind,date(2026,11,8))
        return next(batch for batch in self.manager.queued(self.config) if batch['kind']==kind)

    def test_competition_ranks_and_cutoff_ties_are_not_arbitrarily_broken(self):
        rows=[{'user_id':str(i),'wins':7,'clues':17} for i in range(1,16)]
        self.assertEqual(len(ranked(rows)),15);self.assertEqual({r['rank'] for r in ranked(rows)},{1})
        rows=[{'user_id':'1','wins':7,'clues':17},{'user_id':'2','wins':7,'clues':17},{'user_id':'3','wins':7,'clues':18},{'user_id':'4','wins':6,'clues':6}]
        self.assertEqual([r['rank'] for r in ranked(rows)],[1,1,3,4])
        self.assertEqual([r['rank'] for r in ranked([dict(row,clues=2) for row in rows],True)],[1,1,1,1])
        rows=[{'user_id':str(i),'wins':1,'clues':i} for i in range(1,10)]+[{'user_id':str(i),'wins':1,'clues':10} for i in range(10,25)]
        self.assertEqual(len(ranked(rows)),24);self.assertEqual(ranked(rows)[-1]['rank'],10)

    def test_daily_uses_closed_frozen_map_name_and_counts_attempted_players(self):
        answer=self.play(101,clues=2)['puzzle']['map']['name']
        self.play(102,clues=2);self.play(103,clues=3);self.play(104,win=False)
        self.play(105,unfinished=True);self.play(106,guild=99)
        self.play(107,mode='practice')
        self.store.start('108',guild_id=22)  # opening without a guess is not participation
        from portle.catalog import Catalog
        self.store.catalog=Catalog(tuple(dict(row,name='Renamed '+row['name']) for row in self.store.catalog.maps),'renamed')
        batch=self.batch();embeds=json.loads(batch['payload'])[0]
        self.assertIn('2026-11-08',embeds[0]['title']);body=embeds[0]['description']
        self.assertIn('**Map: '+answer+'**',body);self.assertIn('3 of 5 players solved it',body)
        self.assertEqual(body.count('🥇'),2);self.assertIn('🥉 <@103>',body)
        for excluded in ('106','107','108'):self.assertNotIn('<@'+excluded+'>',body)
        self.assertNotIn('fresh puzzle',body.lower());self.assertNotIn('Can you top',body)
        with self.assertRaises(GameError):self.manager.prepare(self.config,'daily',date(2026,11,9))
        with self.assertRaises(GameError):self.manager.prepare(self.config,'daily',date(2026,11,10))
        with self.assertRaises(GameError):self.manager.prepare(self.config,'weekly',date(2026,11,7))

    def test_rounded_display_does_not_hide_distinct_exact_tie_breakers(self):
        rows=ranked([{'user_id':'1','wins':1000,'clues':2700},{'user_id':'2','wins':1000,'clues':2700},{'user_id':'3','wins':1000,'clues':2701}])
        self.assertEqual([row['rank'] for row in rows],[1,1,3])
        body=board_embeds('All time',rows)[0]['description']
        self.assertIn('2700 clues total',body);self.assertIn('2701 clues total',body)
        self.assertEqual(body.count('2.70 average clues'),3)

    def test_weekly_and_all_time_share_one_post_and_use_wins_then_total_successful_clues(self):
        self.play(101,day=1,clues=6)
        for day in range(2,9):
            self.play(101,day,2);self.play(102,day,2)
            if day>2:self.play(103,day,1)
        self.play(104,8,win=False)
        self.play(103,9,1)  # current day must not leak into the closed weekly totals
        batch=self.batch('weekly');messages=json.loads(batch['payload']);self.assertEqual(len(messages),1)
        weekly,all_time=messages[0];body=weekly['description']
        self.assertIn('2026-11-02 – 2026-11-08',weekly['title'])
        self.assertIn('🥇 <@101>',body);self.assertIn('🥇 <@102>',body);self.assertIn('🥉 <@103>',body)
        self.assertIn('4 players · 20 puzzles solved',body)
        self.assertIn('**8 solves**',all_time['description']);self.assertIn('All-Time',all_time['title'])
        for name in self.store.catalog.choices():self.assertNotIn(name,json.dumps(messages))
        self.assertNotIn('fresh leaderboard',json.dumps(messages))

    def test_empty_daily_is_skipped_and_quiet_week_still_posts_existing_all_time_standings(self):
        self.manager.prepare(self.config,'daily',date(2026,10,31))
        with self.store.connection() as db:self.assertEqual(db.execute('SELECT status FROM announcement_batches').fetchone()[0],'skipped')
        self.play(101,day=1)
        batch=self.batch('weekly');weekly,all_time=json.loads(batch['payload'])[0]
        self.assertIn('No solves',weekly['description']);self.assertIn('0 players',weekly['description'])
        self.assertIn('<@101>',all_time['description'])

    def test_config_is_private_per_server_persistent_and_resumes_only_future_schedules(self):
        self.assertIsNone(self.manager.configure(99))
        with self.assertRaises(GameError):self.manager.configure(99,enabled=True)
        with self.assertRaises(GameError):self.manager.configure('not-server',33)
        self.play(101);self.close_day()
        later=self.manager.configure(99,44)
        self.assertTrue(all(scheduled<datetime.fromisoformat(later['enabled_at']) for _,_,scheduled in due_periods(self.now)))
        restart=GameStore(self.path,self.store.catalog,clock=lambda:self.now)
        self.assertEqual(restart.announcements.configure(22)['channel_id'],'33')
        self.assertFalse(self.manager.configure(22,enabled=False)['enabled'])
        self.assertEqual({row['guild_id'] for row in self.manager.enabled()},{'99'})
        self.manager.configure(22,enabled=True)
        self.manager.prepare(self.manager.configure(22),'daily',date(2026,11,8))
        self.assertEqual(self.manager.queued(self.manager.configure(22)),[])

    def test_snapshot_and_reservations_survive_restart_replays_and_concurrent_claims(self):
        self.play(101);batch=self.batch();original=batch['payload']
        def prepare(_):self.manager.prepare(self.config,'daily',date(2026,11,8))
        with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(prepare,range(8)))
        with self.store.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM announcement_batches').fetchone()[0],1)
        def claim(_):return self.manager.claim(batch,0)
        with ThreadPoolExecutor(max_workers=4) as pool:self.assertEqual(sum(pool.map(claim,range(8))),1)
        restarted=GameStore(self.path,self.store.catalog,clock=lambda:self.now).announcements
        self.assertFalse(restarted.claim(batch,0));self.assertEqual(restarted.queued(self.config)[0]['payload'],original)
        self.assertEqual(restarted.configure(22)['unconfirmed'],1)
        restarted.finish(batch,0,message_id=555)
        self.assertFalse(restarted.claim(batch,0));self.assertEqual(restarted.queued(self.config),[])
        self.assertEqual(restarted.configure(22)['unconfirmed'],0)
        restarted.finish(batch,0,error='Stale replay')
        self.assertIsNone(restarted.configure(22)['last_error'])

    def test_known_failure_retries_after_cooldown_but_uncertain_delivery_never_auto_retries(self):
        self.play(101);batch=self.batch();self.assertTrue(self.manager.claim(batch,0))
        nonce=self.manager.nonce(batch,0)
        self.manager.finish(batch,0,error='Forbidden',retry=True)
        self.assertFalse(self.manager.claim(batch,0));self.now+=timedelta(minutes=6)
        self.assertTrue(self.manager.claim(batch,0));self.assertEqual(self.manager.nonce(batch,0),nonce)
        self.manager.finish(batch,0,error='Connection lost')
        self.now+=timedelta(minutes=6);self.assertFalse(self.manager.claim(batch,0))
        self.assertEqual(self.manager.configure(22)['unconfirmed'],1)

    def test_old_periods_or_changed_channels_are_not_dumped_into_new_channel(self):
        self.play(101);batch=self.batch()
        self.manager.configure(22,44);self.assertFalse(self.manager.claim(batch,0))
        self.assertEqual(self.manager.queued(self.manager.configure(22)),[])
        self.now+=timedelta(days=2);self.assertEqual(self.manager.queued(self.config),[])

    def test_claim_rechecks_latest_period_after_clock_moves_during_channel_lookup(self):
        self.play(101);batch=self.batch()
        self.now+=timedelta(days=1)
        self.assertFalse(self.manager.claim(batch,0))

    def test_namespace_isolation_preserves_existing_manual_and_generated_records(self):
        from portle.clues import ClueLibrary
        from PIL import Image
        from io import BytesIO
        self.play(101)
        library=ClueLibrary(Path(self.temp.name)/'clues');content=BytesIO();Image.new('RGB',(8,8)).save(content,format='PNG')
        for stage in range(1,7):library.upload(self.store.catalog.maps[0]['id'],stage,content.getvalue())
        library.publish(self.store.catalog.maps[0]['id'])
        manual=GameStore(self.path,self.store.catalog,clock=lambda:self.now,clues=library)
        self.assertEqual(manual.leaderboard(22),[])
        state=manual.start('102',guild_id=22);manual.act(state['id'],'102',0,guess=state['puzzle']['map']['name'])
        self.assertEqual([row['user_id'] for row in manual.leaderboard(22)],['102'])
        self.assertEqual([row['user_id'] for row in self.store.leaderboard(22)],['101'])

    def test_admin_reset_removes_score_before_snapshot_without_using_audit_history(self):
        self.play(101);self.store.reset_daily('101',actor_id='99',guild_id='22',event_id='reset')
        self.close_day();self.manager.prepare(self.config,'daily',date(2026,11,8))
        with self.store.connection() as db:self.assertEqual(db.execute('SELECT status FROM announcement_batches').fetchone()[0],'skipped')

    def test_many_cutoff_ties_and_astral_text_fit_discord_limits_without_omissions(self):
        rows=ranked([{'user_id':str(i),'wins':1,'clues':2} for i in range(1000,2000)],True)
        snapshot={'kind':'daily','end':'2026-11-08','timezone':'America/Los_Angeles','mapName':'😀'*300+'@everyone',
                  'daily':{'players':1000,'wins':1000,'rows':rows}}
        pages=message_pages(snapshot);self.assertGreater(len(pages),1)
        rendered=''.join(embed['description'] for page in pages for embed in page)
        self.assertEqual(rendered.count('<@'),1000)
        for page in pages:
            self.assertLessEqual(len(page),10)
            self.assertLessEqual(sum(text_length(e['title']+e['description']+e['footer']['text']) for e in page),6000)
            self.assertTrue(all(text_length(e['description'])<=4096 for e in page))

    def test_schedule_uses_local_dates_monday_boundaries_and_dst(self):
        la=ZoneInfo('America/Los_Angeles')
        now=datetime(2026,11,9,8,6,tzinfo=timezone.utc).astimezone(la)
        daily,weekly=due_periods(now)
        self.assertEqual(daily[1],date(2026,11,8));self.assertEqual(weekly[1],date(2026,11,1))
        self.assertEqual(due_periods(now+timedelta(minutes=5))[1][1],date(2026,11,8))
        spring=datetime(2026,3,9,7,11,tzinfo=timezone.utc).astimezone(la)
        self.assertEqual(due_periods(spring)[1][1],date(2026,3,8))
        self.assertEqual(due_periods(spring)[0][2].utcoffset(),timedelta(hours=-7))
        early=datetime(2026,11,9,0,4,tzinfo=la)
        self.assertEqual(due_periods(early)[0][1],date(2026,11,7))


if __name__=='__main__':unittest.main()
