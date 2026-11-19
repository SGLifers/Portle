import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock,patch

import discord
from PIL import Image
from discord import app_commands
from portle.bot import PortleClient,RoundView,post_daily_result
from portle.game import GameError
from portle.clues import ClueLibrary
from portle.store import GameStore
from helpers import fixture_catalog
from test_discord import interaction


class ResultStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'results.db'
        self.now=datetime(2026,11,18,12,tzinfo=timezone.utc)
        self.store=GameStore(self.path,fixture_catalog(),clock=lambda:self.now)
        self.state=self.win()
    def tearDown(self):self.temp.cleanup()
    def win(self,user='11',mode='daily'):
        state=self.store.start(user,mode)
        return self.store.act(state['id'],user,0,guess=state['puzzle']['map']['name'])
    def claim(self,guild=22,manual=False):return self.store.results.claim(self.state['id'],'11',guild,33,manual)
    def test_completed_lookup_does_not_start_a_new_round_and_checks_owner_mode_and_day(self):
        self.assertEqual(self.store.results.completed('11'),self.state)
        for user,round_id in [('99',None),('99',self.state['id']),('11',self.win(mode='practice')['id'])]:
            with self.assertRaises(GameError):self.store.results.completed(user,round_id)
        playing=self.store.start('99')
        with self.assertRaises(GameError):self.store.results.completed('99',playing['id'])
        self.now+=timedelta(days=1)
        with self.assertRaises(GameError):self.claim()
        with self.store.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM server_result_posts').fetchone()[0],0)
    def test_per_server_claim_is_atomic_and_survives_restart(self):
        with ThreadPoolExecutor(max_workers=4) as pool:claims=list(pool.map(lambda _:self.claim(),range(12)))
        self.assertEqual(sum(c['claimed'] for c in claims),1)
        claim=next(c for c in claims if c['claimed'])
        self.store.results.finish(claim,'sent',444)
        restart=GameStore(self.path,self.store.catalog,clock=lambda:self.now)
        duplicate=restart.results.claim(self.state['id'],'11',22,34)
        self.assertFalse(duplicate['claimed']);self.assertEqual(duplicate['channel_id'],'33');self.assertEqual(duplicate['message_id'],'444')
        self.assertTrue(self.claim(guild=23)['claimed'])
        self.assertEqual([r['user_id'] for r in self.store.leaderboard(23)],['11'])
    def test_reset_and_channel_change_cannot_repeat_a_sent_daily(self):
        self.store.results.configure(22,33);claim=self.claim(manual=True);self.store.results.finish(claim,'sent',444)
        self.store.reset_daily('11',actor_id='99',guild_id=22,event_id='reset')
        fresh=self.win();self.assertNotEqual(fresh['id'],self.state['id'])
        with self.assertRaises(GameError):self.claim(manual=True)
        self.store.results.configure(22,34)
        self.assertFalse(self.store.results.claim(fresh['id'],'11',22,34,True)['claimed'])
        self.assertEqual(self.store.stats('11')['wins'],1)
    def test_only_explicit_retry_of_definite_rejection_is_allowed(self):
        self.store.results.configure(22,33)
        first=self.claim();self.store.results.finish(first,'rejected')
        self.assertFalse(self.claim()['claimed'])
        second=self.claim(manual=True);self.assertTrue(second['claimed'])
        self.assertEqual(self.store.results.nonce(first),self.store.results.nonce(second))
        # Late callbacks cannot overwrite a later reservation or its confirmation.
        self.store.results.finish(first,'sent',333)
        self.store.results.finish(second,'sent',444);self.store.results.finish(second,'uncertain')
        self.assertEqual(self.claim()['message_id'],'444')
    def test_uncertain_and_pending_deliveries_are_never_reclaimed(self):
        self.store.results.configure(22,33)
        claim=self.claim();self.assertFalse(self.claim(manual=True)['claimed'])
        self.store.results.finish(claim,'uncertain')
        restart=GameStore(self.path,self.store.catalog,clock=lambda:self.now)
        self.assertFalse(restart.results.claim(self.state['id'],'11',22,33,True)['claimed'])
    def test_configuration_is_independent_and_rechecked_at_claim(self):
        self.assertIsNone(self.store.results.configure(22))
        with self.assertRaises(GameError):self.claim(manual=True)
        with self.assertRaises(GameError):self.store.results.configure(22,enabled=True)
        self.store.results.configure(22,33);self.store.results.configure(23,44)
        self.store.results.configure(22,enabled=False)
        with self.assertRaises(GameError):self.claim(manual=True)
        self.assertEqual(self.store.results.configure(23)['channel_id'],'44')
        self.store.results.configure(22,enabled=True)
        self.store.results.configure(22,34)
        with self.assertRaises(GameError):self.claim(manual=True)
        self.assertTrue(self.store.results.claim(self.state['id'],'11',22,34,True)['claimed'])
        self.assertIsNone(self.store.announcements.configure(22))
    def test_new_day_and_manual_namespace_use_distinct_keys(self):
        first=self.claim();self.store.results.finish(first,'sent',444)
        self.now+=timedelta(days=1);self.state=self.win()
        self.assertTrue(self.claim()['claimed'])
        # A mode change must not permit an old generated round to be shared as manual.
        self.store.clues=object()
        with self.assertRaises(GameError):self.claim(guild=23)
    def test_upgrade_preserves_legacy_reservations_and_player_data(self):
        self.store.claim_result_post(self.state['id'],'11');self.store.record_result_post(self.state['id'],444)
        with self.store.connection() as db:
            db.execute('DROP TABLE result_config');db.execute('DROP TABLE server_result_posts')
        restart=GameStore(self.path,self.store.catalog,clock=lambda:self.now)
        self.assertTrue(restart.results.legacy_post(self.state['id']))
        self.assertEqual(restart.get(self.state['id'],'11'),self.state)
        self.assertEqual(restart.stats('11')['wins'],1)
        self.assertIsNone(restart.results.configure(22))


class ResultDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'results.db'
        self.now=datetime(2026,11,18,12,tzinfo=timezone.utc)
        self.store=GameStore(self.path,fixture_catalog(),clock=lambda:self.now)
        state=self.store.start('11',guild_id=99)
        self.state=self.store.act(state['id'],'11',0,guess=state['puzzle']['map']['name'])
        self.client=PortleClient(self.store);self.group=self.client.tree.get_command('portle')
    async def asyncTearDown(self):await self.client.close();self.temp.cleanup()
    def event(self,guild=22,**kwargs):
        event=interaction(**kwargs);event.guild_id=guild;event.guild.id=guild
        return event
    def rows(self):
        with self.store.connection() as db:return [dict(r) for r in db.execute('SELECT * FROM server_result_posts')]
    async def share(self,event):await self.group.share.callback(self.group,event)
    async def test_resume_elsewhere_does_not_post_until_share_results_is_clicked(self):
        self.store.results.configure(22,33);event=self.event()
        await self.group.play.callback(self.group,event)
        view=event.edit_original_response.call_args.kwargs['view']
        self.assertEqual(view.share_results.label,'Share results');self.assertIn(view.share_results,view.children)
        event.channel.send.assert_not_awaited()
        await view.share_results.callback(event)
        event.channel.send.assert_awaited_once();text=event.channel.send.call_args.args[0]
        self.assertIn('1/6',text);self.assertIn('<@11>',text)
        for spoiler in [self.state['puzzle']['map']['name'],self.state['puzzle']['map']['id'],'attachment://']:
            self.assertNotIn(spoiler,text)
        kwargs=event.channel.send.call_args.kwargs
        self.assertTrue(kwargs['view'].is_persistent());self.assertEqual(len(kwargs['nonce']),24)
        self.assertEqual(kwargs['allowed_mentions'].to_dict()['parse'],[])
        self.assertIn('Results shared',event.followup.send.call_args.args[0]);self.assertTrue(event.followup.send.call_args.kwargs['ephemeral'])
        self.assertEqual(self.store.stats('11')['wins'],1)
        self.assertEqual([r['user_id'] for r in self.store.leaderboard(22)],['11'])
    async def test_shortcut_and_button_share_the_automatic_post_reservation(self):
        self.store.results.configure(22,33);event=self.event()
        await post_daily_result(event,self.store,self.state)
        await self.share(event)
        await RoundView(self.store,self.state).share_results.callback(event)
        event.channel.send.assert_awaited_once()
        self.assertIn('already been posted',event.followup.send.call_args.args[0])
        other=self.event(23);self.store.results.configure(23,33);await self.share(other)
        other.channel.send.assert_awaited_once();self.assertEqual(len(self.rows()),2)
    async def test_routes_to_configured_channel_and_checks_both_bot_and_member_permissions(self):
        event=self.event();destination=self.event().channel;destination.id=44
        event.client.get_channel=lambda cid:destination if cid==44 else None
        self.store.results.configure(22,44)
        for member_allowed,bot_allowed in [(False,True),(True,False)]:
            destination.permissions_for=lambda member:discord.Permissions(view_channel=True,send_messages=bot_allowed if member.id==77 else member_allowed)
            await self.share(event);destination.send.assert_not_awaited();self.assertEqual(self.rows(),[])
        destination.permissions_for=lambda member:discord.Permissions(view_channel=True,send_messages=True)
        await self.share(event);destination.send.assert_awaited_once();event.channel.send.assert_not_awaited()
    async def test_no_config_disabled_or_foreign_destination_never_posts(self):
        event=self.event();await self.share(event)
        self.assertIn('/portle results',event.followup.send.call_args.args[0]);self.assertEqual(self.rows(),[])
        self.store.results.configure(22,33,False);await self.share(event)
        self.assertIn('disabled',event.followup.send.call_args.args[0])
        await post_daily_result(event,self.store,self.state);event.channel.send.assert_not_awaited()
        self.store.results.configure(22,33);event.channel.guild.id=23;event.guild=SimpleNamespace(id=22,me=SimpleNamespace(id=77))
        await self.share(event);self.assertIn('must be in this server',event.followup.send.call_args.args[0]);self.assertEqual(self.rows(),[])
    async def test_unfinished_unplayed_practice_old_and_other_players_cannot_be_shared(self):
        self.store.results.configure(22,33)
        event=self.event(user='99')
        with self.assertRaises(GameError):await self.share(event)
        self.assertFalse(await RoundView(self.store,self.state).interaction_check(event))
        await RoundView(self.store,self.state).share_results.callback(event)
        self.assertEqual(self.rows(),[])
        playing=self.store.start('99');self.assertNotIn('Share results',[getattr(c,'label',None) for c in RoundView(self.store,playing).children])
        with self.assertRaises(GameError):await self.share(event)
        practice=self.store.start('11','practice');practice=self.store.act(practice['id'],'11',0,guess=practice['puzzle']['map']['name'])
        view=RoundView(self.store,practice);self.assertNotIn(view.share_results,view.children)
        await view.share_results.callback(self.event());self.assertEqual(self.rows(),[])
        self.now+=timedelta(days=1)
        await RoundView(self.store,self.state).share_results.callback(self.event());self.assertEqual(self.rows(),[])
    async def test_dm_and_missing_bot_membership_do_not_send(self):
        self.store.results.configure(22,33)
        event=self.event();event.guild_id=None
        with self.assertRaises(GameError):await self.share(event)
        event=self.event();event.guild.me=None
        await self.share(event);event.channel.send.assert_not_awaited();self.assertEqual(self.rows(),[])
    async def test_concurrent_shares_send_once_and_survive_restart(self):
        self.store.results.configure(22,33);event=self.event()
        await asyncio.gather(self.share(event),self.share(event))
        event.channel.send.assert_awaited_once()
        restart=GameStore(self.path,self.store.catalog,clock=lambda:self.now)
        retry=self.event();await retry.response.defer(ephemeral=True);await post_daily_result(retry,restart,self.state,manual=True)
        retry.channel.send.assert_not_awaited();self.assertIn('already been posted',retry.followup.send.call_args.args[0])
    async def test_lookup_errors_do_not_consume_reservation_and_recovery_works(self):
        self.store.results.configure(22,44);event=self.event();event.client.fetch_channel.side_effect=OSError('private-detail')
        await self.share(event);self.assertEqual(self.rows(),[])
        self.assertNotIn('private-detail',event.followup.send.call_args.args[0])
        event.channel.id=44;event.client.fetch_channel.side_effect=None;event.client.fetch_channel.return_value=event.channel
        await self.share(event);event.channel.send.assert_awaited_once()
    async def test_rejected_send_can_be_manually_retried_but_uncertain_send_is_held(self):
        self.store.results.configure(22,33);event=self.event()
        event.channel.send.side_effect=discord.Forbidden(SimpleNamespace(status=403,reason='Forbidden'),{'code':50013,'message':'private-detail'})
        with self.assertLogs('portle.bot',level='WARNING'):await self.share(event)
        self.assertEqual(self.rows()[0]['status'],'rejected')
        event.channel.send.side_effect=None;await self.share(event)
        self.assertEqual(event.channel.send.await_count,2);self.assertEqual(self.rows()[0]['status'],'sent')
        self.store.results.configure(23,33);other=self.event(23);other.channel.send.side_effect=OSError('private-detail')
        with self.assertLogs('portle.bot',level='WARNING'):await self.share(other)
        await self.share(other);other.channel.send.assert_awaited_once()
        self.assertIn('could not be confirmed',other.followup.send.call_args.args[0])
    async def test_crash_after_send_is_held_and_legacy_automatic_post_is_not_repeated(self):
        self.store.results.configure(22,33);event=self.event()
        with patch.object(self.store.results,'finish',side_effect=RuntimeError('storage unavailable')):
            with self.assertRaises(RuntimeError):await self.share(event)
        await self.share(event);event.channel.send.assert_awaited_once();self.assertEqual(self.rows()[0]['status'],'pending')
        self.store.claim_result_post(self.state['id'],'11');self.store.record_result_post(self.state['id'],123)
        other=self.event(23);await post_daily_result(other,self.store,self.state);other.channel.send.assert_not_awaited()
        # Old global records lack server IDs; explicit opt-in sharing still works.
        self.store.results.configure(23,33);await self.share(other);other.channel.send.assert_awaited_once()
    async def test_admin_configuration_permissions_channel_validation_and_disable(self):
        command=self.group.get_command('results');event=self.event()
        with self.assertRaises(app_commands.MissingPermissions):await command._check_can_run(event)
        with self.assertRaises(app_commands.MissingPermissions):await command.callback(self.group,event,event.channel)
        self.assertIsNone(self.store.results.configure(22))
        event=self.event(administrator=True)
        await command.callback(self.group,event,event.channel)
        self.assertEqual(self.store.results.configure(22)['channel_id'],'33')
        await command.callback(self.group,event,enabled=False)
        self.assertFalse(self.store.results.configure(22)['enabled'])
        await command.callback(self.group,event,enabled=True)
        self.assertTrue(self.store.results.configure(22)['enabled'])
        bad=self.event(23).channel
        with self.assertRaises(GameError):await command.callback(self.group,event,bad)
        event.channel.permissions_for=lambda member:discord.Permissions.none()
        with self.assertRaises(GameError):await command.callback(self.group,event,event.channel)
    async def test_help_lists_share_and_result_setup_within_discord_limits(self):
        event=self.event();await self.group.help.callback(self.group,event)
        kwargs=event.response.send_message.call_args.kwargs
        self.assertTrue(kwargs['ephemeral']);self.assertLessEqual(len(kwargs['embed'].description),4096)
        self.assertIn('/portle share',kwargs['embed'].description);self.assertIn('Share results',kwargs['embed'].description)
        self.assertIn('/portle results channel:#games',kwargs['embed'].description)
    async def test_settings_change_and_rollover_during_channel_lookup_block_send(self):
        self.store.results.configure(22,44)
        event=self.event();destination=self.event().channel;destination.id=44
        async def changed(cid):
            self.store.results.configure(22,enabled=False)
            return destination
        event.client.fetch_channel.side_effect=changed
        await self.share(event);destination.send.assert_not_awaited();self.assertEqual(self.rows(),[])
        self.store.results.configure(22,enabled=True)
        async def rolled(cid):
            self.now+=timedelta(days=1)
            return destination
        event.client.fetch_channel.side_effect=rolled
        await self.share(event);destination.send.assert_not_awaited();self.assertEqual(self.rows(),[])
    async def test_manual_screenshot_daily_loss_shares_without_clues_or_answer(self):
        library=ClueLibrary(Path(self.temp.name)/'clues');mid=self.store.catalog.maps[0]['id']
        for index in range(1,7):
            image=BytesIO();Image.new('RGB',(32,24),(index*30,0,0)).save(image,format='PNG')
            library.upload(mid,index,image.getvalue())
        library.publish(mid)
        manual=GameStore(Path(self.temp.name)/'manual.db',self.store.catalog,clock=lambda:self.now,clues=library)
        manual.results.configure(22,33);state=manual.start('11')
        for version in range(6):state=manual.act(state['id'],'11',version,skip=True)
        event=self.event();await RoundView(manual,state).share_results.callback(event)
        text=event.channel.send.call_args.args[0]
        self.assertIn('X/6',text);self.assertNotIn(mid,text);self.assertNotIn(state['puzzle']['map']['name'],text)
        self.assertNotIn('file',event.channel.send.call_args.kwargs)
        with manual.connection() as db:self.assertTrue(db.execute('SELECT puzzle_id FROM server_result_posts').fetchone()[0].startswith('manual:daily:'))
