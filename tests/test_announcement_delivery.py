import asyncio
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,patch

import discord
from discord import app_commands
from portle.bot import PortleClient,PlayPortleView
from portle.game import GameError
from portle.store import GameStore
from helpers import fixture_catalog
from test_discord import interaction


class AnnouncementDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'game.db'
        self.now=datetime(2026,11,9,12,tzinfo=timezone.utc)
        self.store=GameStore(self.path,fixture_catalog(),clock=lambda:self.now)
        self.store.announcements.configure(22,33)
        self.play('101')
        self.now=datetime(2026,11,10,0,6,tzinfo=timezone.utc)
        self.client=PortleClient(self.store)
        self.channel=SimpleNamespace(id=33,guild=SimpleNamespace(id=22),send=AsyncMock(return_value=SimpleNamespace(id=555)))
        self.channel_patch=patch.object(self.client,'get_channel',return_value=self.channel);self.channel_patch.start()
    async def asyncTearDown(self):
        self.channel_patch.stop();await self.client.close();self.temp.cleanup()
    def play(self,user,guild=22):
        state=self.store.start(user,guild_id=guild)
        return self.store.act(state['id'],user,0,guess=state['puzzle']['map']['name'])

    async def test_due_post_has_closed_answer_no_promotional_copy_no_pings_and_persistent_play(self):
        await self.client.send_due_announcements()
        self.channel.send.assert_awaited_once();kwargs=self.channel.send.call_args.kwargs
        self.assertIsInstance(kwargs['view'],PlayPortleView);self.assertTrue(kwargs['view'].is_persistent())
        self.assertEqual(kwargs['allowed_mentions'].to_dict()['parse'],[])
        payload=json.dumps([embed.to_dict() for embed in kwargs['embeds']])
        self.assertIn('2026-11-09',payload);self.assertIn('Map:',payload)
        self.assertNotIn('fresh puzzle',payload.lower());self.assertNotIn('top today',payload.lower())
        config=self.store.announcements.configure(22)
        self.assertEqual(self.store.announcements.queued(config),[])
        await self.client.send_due_announcements();self.assertEqual(self.channel.send.await_count,1)
        restart=GameStore(self.path,self.store.catalog,clock=lambda:self.now)
        other=PortleClient(restart)
        try:
            with patch.object(other,'get_channel',return_value=self.channel):await other.send_due_announcements()
        finally:await other.close()
        self.assertEqual(self.channel.send.await_count,1)

    async def test_weekly_and_all_time_are_two_embeds_in_one_weekly_message(self):
        self.now=datetime(2026,11,8,12,tzinfo=timezone.utc)
        self.store.announcements.configure(22,enabled=False);self.store.announcements.configure(22,enabled=True)
        self.play('102');self.now=datetime(2026,11,9,0,11,tzinfo=timezone.utc)
        await self.client.send_due_announcements()
        self.assertEqual(self.channel.send.await_count,2)
        weekly=next(call.kwargs for call in self.channel.send.call_args_list if len(call.kwargs['embeds'])==2)
        self.assertIn('Weekly',weekly['embeds'][0].title);self.assertIn('All-Time',weekly['embeds'][1].title)
        self.assertIn('2026-11-02 – 2026-11-08',weekly['embeds'][0].title)
        for name in self.store.catalog.choices():self.assertNotIn(name,json.dumps([e.to_dict() for e in weekly['embeds']]))

    async def test_permission_failure_retries_after_fix_with_same_nonce(self):
        error=discord.Forbidden(SimpleNamespace(status=403,reason='Forbidden'),{'code':50013,'message':'raw private detail'})
        self.channel.send.side_effect=error
        with self.assertLogs('portle.bot',level='WARNING'):await self.client.send_due_announcements()
        nonce=self.channel.send.call_args.kwargs['nonce']
        await self.client.send_due_announcements();self.assertEqual(self.channel.send.await_count,1)
        self.assertNotIn('raw private detail',self.store.announcements.configure(22)['last_error'])
        self.now+=timedelta(minutes=6);self.channel.send.side_effect=None
        await self.client.send_due_announcements();self.assertEqual(self.channel.send.await_count,2)
        self.assertEqual(self.channel.send.call_args.kwargs['nonce'],nonce)
        self.assertEqual(self.store.announcements.queued(self.store.announcements.configure(22)),[])

    async def test_uncertain_network_send_and_crash_after_send_are_not_repeated(self):
        self.channel.send.side_effect=OSError('connection lost')
        with self.assertLogs('portle.bot',level='WARNING'):await self.client.send_due_announcements()
        self.channel.send.side_effect=None;self.now+=timedelta(minutes=10)
        await self.client.send_due_announcements();self.assertEqual(self.channel.send.await_count,1)
        self.assertEqual(self.store.announcements.configure(22)['unconfirmed'],1)

    async def test_crash_after_success_before_sqlite_confirmation_holds_reservation(self):
        with patch.object(self.store.announcements,'finish',side_effect=RuntimeError('storage unavailable')):
            with self.assertLogs('portle.bot',level='WARNING'):await self.client.send_due_announcements()
        self.assertEqual(self.channel.send.await_count,1)
        await self.client.send_due_announcements();self.assertEqual(self.channel.send.await_count,1)
        self.assertEqual(self.store.announcements.configure(22)['unconfirmed'],1)

    async def test_one_blocked_server_does_not_prevent_another_servers_post(self):
        self.now=datetime(2026,11,9,12,tzinfo=timezone.utc)
        self.store.announcements.configure(99,44);self.play('102',99)
        self.now=datetime(2026,11,10,0,6,tzinfo=timezone.utc)
        good=SimpleNamespace(id=44,guild=SimpleNamespace(id=99),send=AsyncMock(return_value=SimpleNamespace(id=666)))
        self.channel.send.side_effect=discord.Forbidden(SimpleNamespace(status=403,reason='Forbidden'),{'code':50013})
        with patch.object(self.client,'get_channel',side_effect=lambda cid:self.channel if cid==33 else good):
            with self.assertLogs('portle.bot',level='WARNING'):await self.client.send_due_announcements()
        good.send.assert_awaited_once();self.assertNotIn('<@101>',good.send.call_args.kwargs['embeds'][0].description)

    async def test_disabled_or_wrong_server_channels_do_not_send(self):
        self.store.announcements.configure(22,enabled=False)
        await self.client.send_due_announcements();self.channel.send.assert_not_awaited()
        self.now=datetime(2026,11,9,12,tzinfo=timezone.utc)
        self.store.announcements.configure(22,enabled=True)
        self.now=datetime(2026,11,10,0,6,tzinfo=timezone.utc)
        self.channel.guild.id=99
        with self.assertLogs('portle.bot',level='WARNING'):await self.client.send_due_announcements()
        self.channel.send.assert_not_awaited()
        self.assertIn('Channel access failed',self.store.announcements.configure(22)['last_error'])

    async def test_large_tie_continuations_resume_safely_after_partial_delivery(self):
        self.now=datetime(2026,11,9,12,tzinfo=timezone.utc)
        def populate():
            for user in range(1000,1300):self.play(str(user))
        await asyncio.to_thread(populate)
        self.now=datetime(2026,11,10,0,6,tzinfo=timezone.utc)
        self.channel.send.side_effect=[SimpleNamespace(id=555),OSError('unknown outcome')]
        with self.assertLogs('portle.bot',level='WARNING'):await self.client.send_due_announcements()
        self.assertEqual(self.channel.send.await_count,2)
        config=self.store.announcements.configure(22);batch=self.store.announcements.queued(config)[0]
        pages=self.store.announcements.pages(batch)
        self.assertEqual([p['status'] for p in pages[:2]],['sent','uncertain'])
        await self.client.send_due_announcements();self.assertEqual(self.channel.send.await_count,2)

    async def test_admin_configuration_checks_channel_permissions_and_status_privately(self):
        command=self.client.tree.get_command('portle').get_command('announcements');group=command.parent
        for event in [interaction(),interaction(administrator=True)]:
            if event.permissions.administrator:event.guild_id=None
            with self.assertRaises(app_commands.MissingPermissions):await command._check_can_run(event)
        event=interaction(administrator=True);event.guild=SimpleNamespace(me=object())
        channel=SimpleNamespace(id=33,guild=SimpleNamespace(id=22),permissions_for=lambda me:discord.Permissions(view_channel=True,send_messages=True,embed_links=True))
        self.assertTrue(await command._check_can_run(event))
        await command.callback(group,event,channel=channel)
        self.assertTrue(event.response.flags['ephemeral']);text=event.edit_original_response.call_args.kwargs['content']
        self.assertIn('00:05',text);self.assertIn('Monday 00:10',text);self.assertIn('<#33>',text)
        self.store.announcements.note_error(22,'A safe delivery diagnostic')
        status=interaction(administrator=True);await command.callback(group,status)
        self.assertIn('A safe delivery diagnostic',status.edit_original_response.call_args.kwargs['content'])
        disabled=interaction(administrator=True);await command.callback(group,disabled,enabled=False)
        self.assertIn('disabled',disabled.edit_original_response.call_args.kwargs['content'])
        self.channel.send.assert_not_awaited()
        channel.permissions_for=lambda me:discord.Permissions.none()
        denied=interaction(administrator=True);denied.guild=event.guild
        with self.assertRaises(GameError):await command.callback(group,denied,channel=channel)
        channel.guild.id=99
        with self.assertRaises(GameError):await command.callback(group,interaction(administrator=True),channel=channel)

    async def test_two_workers_share_one_atomic_delivery_reservation(self):
        entered=asyncio.Event();release=asyncio.Event()
        async def send(**kwargs):
            entered.set();await release.wait();return SimpleNamespace(id=777)
        self.channel.send.side_effect=send
        other=PortleClient(GameStore(self.path,self.store.catalog,clock=lambda:self.now))
        task=asyncio.create_task(self.client.send_due_announcements())
        try:
            await asyncio.wait_for(entered.wait(),2)
            with patch.object(other,'get_channel',return_value=self.channel):await other.send_due_announcements()
            self.assertEqual(self.channel.send.await_count,1)
            release.set();await task
            await other.send_due_announcements();self.assertEqual(self.channel.send.await_count,1)
        finally:
            release.set();await task;await other.close()

    async def test_background_loop_starts_once_across_ready_replays_and_stops_on_close(self):
        with patch.object(self.client,'wait_until_ready',AsyncMock()),patch.object(self.client,'is_ready',return_value=False),patch('builtins.print'):
            await self.client.on_ready();task=self.client.announcement_loop.get_task()
            await asyncio.sleep(0)
            await self.client.on_ready();self.assertIs(self.client.announcement_loop.get_task(),task)
            await self.client.close();self.assertTrue(task.done())


if __name__=='__main__':unittest.main()
