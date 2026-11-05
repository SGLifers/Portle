from io import BytesIO
from datetime import timedelta
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,PropertyMock,patch
from urllib.parse import parse_qs,urlparse
from PIL import Image
import discord
from discord import app_commands
from portle.bot import DiscordSetupError,MapGuessSelect,PlayPortleView,PortleClient,RoundView,post_daily_result,result_post_error,server_install_url,show_round
from portle.catalog import Catalog
from portle.store import GameStore
from portle.clues import ClueLibrary
from helpers import fixture_catalog


class Response:
    def __init__(self):self.done=False;self.flags=None;self.send_message=AsyncMock()
    def is_done(self):return self.done
    async def defer(self,**kwargs):self.done=True;self.flags=kwargs


def interaction(user='11',*,administrator=False):
    return SimpleNamespace(user=SimpleNamespace(id=int(user)),guild_id=22,id=101,permissions=discord.Permissions(administrator=administrator),channel=SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(id=444))),response=Response(),edit_original_response=AsyncMock(),followup=SimpleNamespace(send=AsyncMock()))


class DiscordTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=GameStore(Path(self.temp.name)/'discord.db',fixture_catalog());self.state=self.store.start('11')
    async def asyncTearDown(self):self.temp.cleanup()
    async def test_command_schema_and_no_privileged_intents(self):
        client=PortleClient(self.store);schema=client.tree.get_commands()[0].to_dict(client.tree)
        self.assertEqual(schema['name'],'portle');self.assertEqual(len(schema['options']),8)
        self.assertNotIn('share',[c['name'] for c in schema['options']])
        reset=next(c for c in schema['options'] if c['name']=='reset')
        self.assertEqual(reset['options'][0]['name'],'player');self.assertEqual(reset['options'][0]['type'],6)
        self.assertTrue(reset['options'][0]['required'])
        self.assertEqual(schema['integration_types'],[0]);self.assertEqual(schema['contexts'],[0])
        self.assertFalse(client.intents.message_content);self.assertFalse(client.intents.members)
        self.assertNotIn('token',str(schema).lower());await client.close()
    async def test_practice_command_rejects_members_and_moderators_privately(self):
        client=PortleClient(self.store);group=client.tree.get_command('portle');command=group.get_command('practice')
        for permissions in [discord.Permissions.none(),discord.Permissions(manage_guild=True,manage_channels=True)]:
            for deferred in [False,True]:
                with self.subTest(permissions=permissions.value,deferred=deferred):
                    event=interaction();event.permissions=permissions
                    if deferred:await event.response.defer(ephemeral=True)
                    with patch.object(self.store,'start',wraps=self.store.start) as start:
                        with self.assertRaises(app_commands.MissingPermissions) as caught:await command._check_can_run(event)
                        await group.on_error(event,caught.exception);start.assert_not_called()
                    send=event.followup.send if deferred else event.response.send_message
                    self.assertIn('server administrators',send.call_args.args[0]);self.assertIn('/portle play',send.call_args.args[0])
                    self.assertTrue(send.call_args.kwargs['ephemeral']);event.edit_original_response.assert_not_awaited()
        await client.close()
    async def test_admin_can_start_private_practice_and_daily_remains_available_to_members(self):
        client=PortleClient(self.store);group=client.tree.get_command('portle');practice=group.get_command('practice')
        event=interaction(administrator=True);self.assertTrue(await practice._check_can_run(event))
        await practice.callback(group,event)
        view=event.edit_original_response.call_args.kwargs['view']
        self.assertEqual(view.mode,'practice');self.assertTrue(event.response.flags['ephemeral'])
        self.assertTrue(await view.interaction_check(event))
        event=interaction();play=group.get_command('play');self.assertTrue(await play._check_can_run(event))
        await play.callback(group,event)
        self.assertEqual(event.edit_original_response.call_args.kwargs['view'].mode,'daily')
        self.assertTrue(event.response.flags['ephemeral']);self.assertIsNone(group.default_permissions)
        await client.close()
    async def test_reset_command_denies_members_moderators_and_dm_before_mutation(self):
        client=PortleClient(self.store);group=client.tree.get_command('portle');command=group.get_command('reset')
        events=[interaction(),interaction(),interaction(administrator=True)]
        events[1].permissions=discord.Permissions(manage_guild=True);events[2].guild_id=None
        for event in events:
            with patch.object(self.store,'reset_daily',wraps=self.store.reset_daily) as reset:
                with self.assertRaises(app_commands.MissingPermissions) as caught:await command._check_can_run(event)
                await group.on_error(event,caught.exception);reset.assert_not_called()
            self.assertTrue(event.response.send_message.call_args.kwargs['ephemeral'])
            self.assertIn('server administrators',event.response.send_message.call_args.args[0])
        await client.close()
    async def test_admin_reset_targets_member_privately_and_old_board_cannot_be_used(self):
        target=self.store.start('99');target=self.store.act(target['id'],'99',0,guess=target['puzzle']['map']['name'])
        old=RoundView(self.store,target)
        client=PortleClient(self.store);group=client.tree.get_command('portle');command=group.get_command('reset')
        event=interaction(administrator=True);self.assertTrue(await command._check_can_run(event))
        await command.callback(group,event,SimpleNamespace(id=99))
        self.assertEqual(event.response.flags,{'ephemeral':True,'thinking':True})
        text=event.edit_original_response.call_args.kwargs['content']
        self.assertIn('<@99>',text);self.assertIn('Reset',text);self.assertNotIn(target['puzzle']['map']['name'],text)
        self.assertEqual(event.edit_original_response.call_args.kwargs['allowed_mentions'].to_dict()['parse'],[])
        event.channel.send.assert_not_awaited();self.assertEqual(self.store.stats('99')['played'],0)
        fresh=self.store.start('99');self.assertNotEqual(fresh['id'],target['id']);self.assertEqual(fresh['attempts'],[])
        player=interaction('99');await old.skip_button.callback(player)
        self.assertTrue(player.followup.send.call_args.kwargs['ephemeral']);self.assertEqual(self.store.start('99')['version'],0)
        self.assertTrue(await RoundView(self.store,fresh).interaction_check(interaction('99')))
        self.assertEqual(self.store.start('11')['id'],self.state['id']);await client.close()
    async def test_admin_reset_of_unplayed_member_is_noop_with_private_feedback(self):
        client=PortleClient(self.store);group=client.tree.get_command('portle');event=interaction(administrator=True)
        await group.reset.callback(group,event,SimpleNamespace(id=99))
        self.assertIn('no daily score or guesses',event.edit_original_response.call_args.kwargs['content'])
        self.assertTrue(event.response.flags['ephemeral']);event.channel.send.assert_not_awaited()
        with self.store.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM rounds WHERE user_id=?',('99',)).fetchone()[0],0)
        await client.close()
    async def test_practice_requires_a_server_and_rechecks_permission_on_existing_boards(self):
        client=PortleClient(self.store);practice=client.tree.get_command('portle').get_command('practice')
        event=interaction(administrator=True);event.guild_id=None
        with self.assertRaises(app_commands.MissingPermissions):await practice._check_can_run(event)
        state=self.store.start('11','practice');view=RoundView(self.store,state)
        for event in [interaction(),event,interaction('99',administrator=True)]:
            self.assertFalse(await view.interaction_check(event))
            self.assertTrue(event.response.send_message.call_args.kwargs['ephemeral'])
        self.assertTrue(await view.interaction_check(interaction(administrator=True)))
        self.assertEqual(self.store.get(state['id'],'11')['version'],0)
        self.assertTrue(await RoundView(self.store,self.state).interaction_check(interaction()))
        await client.close()
    async def test_guild_sync_failure_explains_installation_without_falling_back(self):
        for exception,status,code in [(discord.Forbidden,403,50001),(discord.NotFound,404,10004)]:
            with self.subTest(code=code):
                client=PortleClient(self.store,guild_id=987);client._connection.application_id=12345
                # Raw server error text must never be included in the clean diagnostic.
                error=exception(SimpleNamespace(status=status,reason='Denied'),{'code':code,'message':'private raw HTTP detail'})
                with patch.object(client.tree,'sync',AsyncMock(side_effect=error)) as sync:
                    with self.assertRaises(DiscordSetupError) as caught:await client.setup_hook()
                    sync.assert_awaited_once();self.assertEqual(sync.call_args.kwargs['guild'].id,987)
                text=str(caught.exception)
                self.assertIn('accepted the bot token',text);self.assertIn('DISCORD_GUILD_ID',text)
                self.assertIn('Copy Server ID',text);self.assertIn('Guild Install',text);self.assertIn(str(code),text)
                self.assertNotIn('private raw HTTP detail',text)
                link=text.split('Server installation link: ')[1].splitlines()[0]
                query=parse_qs(urlparse(link).query)
                self.assertEqual(query['client_id'],['12345']);self.assertEqual(query['permissions'],['52224'])
                self.assertEqual(query['scope'],['bot applications.commands']);self.assertNotIn('guild_id',query)
                self.assertEqual(query['integration_type'],['0'])
                await client.close()
    async def test_successful_guild_sync_and_unrelated_failure_keep_their_behavior(self):
        client=PortleClient(self.store,guild_id=987)
        with patch.object(client.tree,'sync',AsyncMock(return_value=[])) as sync:
            await client.setup_hook();self.assertEqual(sync.call_args.kwargs['guild'].id,987)
        error=discord.HTTPException(SimpleNamespace(status=500,reason='Server Error'),{'code':0,'message':'Temporary outage'})
        with patch.object(client.tree,'sync',AsyncMock(side_effect=error)):
            with self.assertRaises(discord.HTTPException) as caught:await client.setup_hook()
            self.assertIs(caught.exception,error)
        await client.close()
    async def test_global_registration_syncs_once_for_all_installed_servers(self):
        client=PortleClient(self.store)
        with patch.object(client.tree,'sync',AsyncMock(return_value=[])) as sync,patch.object(client.tree,'copy_global_to') as copy:
            await client.setup_hook();sync.assert_awaited_once_with();copy.assert_not_called()
        self.assertEqual(len(client.persistent_views),1);await client.close()
    async def test_server_install_url_is_reusable_and_requests_minimal_bot_permissions(self):
        query=parse_qs(urlparse(server_install_url(12345)).query)
        self.assertEqual(query['client_id'],['12345']);self.assertEqual(query['scope'],['bot applications.commands'])
        self.assertEqual(query['permissions'],['52224']);self.assertEqual(query['integration_type'],['0'])
        self.assertNotIn('guild_id',query);self.assertNotIn('disable_guild_select',query)
    async def test_doctor_reports_global_or_development_scope_without_network_or_ids(self):
        from contextlib import redirect_stdout
        import json
        from io import StringIO
        from portle.__main__ import main
        for guild,expected in [('', 'global: all installed servers'),('987','single development server')]:
            output=StringIO();env={'PORTLE_CLUE_SOURCE':'manual','PORTLE_CLUES':str(Path(self.temp.name)/'doctor-clues'),'DISCORD_GUILD_ID':guild}
            with patch.dict('os.environ',env,clear=True),patch('sys.argv',['portle','doctor']),patch('portle.__main__.load_dotenv'),patch('portle.store.GameStore',return_value=self.store),redirect_stdout(output):
                self.assertEqual(main(),0)
            result=json.loads(output.getvalue());self.assertEqual(result['commandScope'],expected)
            self.assertFalse(result['networkConnectionAttempted']);self.assertTrue(result['serverInstallOnly'])
            self.assertNotIn('987',output.getvalue())
    async def test_daily_can_be_opened_from_two_servers_with_independent_players(self):
        view=PlayPortleView(self.store)
        first=interaction('81');first.guild_id=501;second=interaction('82');second.guild_id=502
        await view.play_button.callback(first);await view.play_button.callback(second)
        first_state=self.store.get(first.edit_original_response.call_args.kwargs['view'].round_id,'81')
        second_state=self.store.get(second.edit_original_response.call_args.kwargs['view'].round_id,'82')
        self.assertEqual(first_state['puzzle'],second_state['puzzle']);self.assertNotEqual(first_state['id'],second_state['id'])
        first_state=self.store.act(first_state['id'],'81',0,guess=first_state['puzzle']['map']['name'])
        self.assertEqual([r['user_id'] for r in self.store.leaderboard(501)],['81'])
        self.assertEqual(self.store.leaderboard(502),[])
        self.assertEqual(self.store.get(second_state['id'],'82')['version'],0)
    async def test_public_play_button_is_registered_again_after_restart(self):
        for _ in range(2):
            client=PortleClient(self.store,guild_id=987)
            with patch.object(client.tree,'sync',AsyncMock(return_value=[])):await client.setup_hook()
            views=client.persistent_views;self.assertEqual(len(views),1)
            self.assertTrue(views[0].is_persistent());self.assertIsNone(views[0].timeout)
            self.assertEqual(views[0].play_button.custom_id,'portle:play-daily:v1')
            await client.close()
    async def test_public_play_button_opens_each_members_own_private_daily(self):
        button=PlayPortleView(self.store)
        for user in ['99','11']:
            event=interaction(user);await button.play_button.callback(event)
            self.assertEqual(event.response.flags,{'ephemeral':True,'thinking':True})
            view=event.edit_original_response.call_args.kwargs['view']
            state=self.store.get(view.round_id,user);self.assertEqual(state['mode'],'daily');self.assertEqual(state['user_id'],user)
            self.assertEqual(state['puzzle'],self.state['puzzle'])
            event.channel.send.assert_not_awaited()
        self.assertEqual(self.store.get(self.state['id'],'11')['version'],0)
    async def test_public_play_button_uses_current_day_and_resumes_without_reposting(self):
        button=PlayPortleView(self.store)
        done=self.store.act(self.state['id'],'11',0,guess=self.state['puzzle']['map']['name'])
        event=interaction();await button.play_button.callback(event)
        self.assertEqual(event.edit_original_response.call_args.kwargs['view'].round_id,done['id'])
        event.channel.send.assert_not_awaited()
        tomorrow=self.store.clock()+timedelta(days=1);self.store.clock=lambda:tomorrow
        event=interaction();await button.play_button.callback(event)
        view=event.edit_original_response.call_args.kwargs['view'];self.assertNotEqual(view.round_id,done['id'])
        state=self.store.get(view.round_id,'11');self.assertEqual(state['puzzle']['day'],self.store.today().isoformat())
        self.assertEqual(state['version'],0);event.channel.send.assert_not_awaited()
    async def test_public_play_button_handles_missing_clues_and_dm_privately(self):
        view=PlayPortleView(self.store);event=interaction();event.guild_id=None
        await view.play_button.callback(event)
        self.assertTrue(event.response.send_message.call_args.kwargs['ephemeral']);event.edit_original_response.assert_not_awaited()
        event=interaction()
        with self.assertLogs('portle.bot',level='ERROR') as logs:
            await view.on_error(event,RuntimeError('private raw detail'),view.play_button)
        self.assertNotIn('private raw detail',' '.join(logs.output))
        self.assertNotIn('private raw detail',event.response.send_message.call_args.args[0])
        event=interaction()
        from portle.game import GameError
        with patch.object(self.store,'start',side_effect=GameError('No manual clues are published yet.')):
            await view.play_button.callback(event)
        self.assertTrue(event.followup.send.call_args.kwargs['ephemeral'])
    async def test_final_skip_posts_one_spoiler_free_result_with_play_button(self):
        state=self.state
        for version in range(5):state=self.store.act(state['id'],'11',version,skip=True)
        view=RoundView(self.store,state);event=interaction();await view.skip_button.callback(event)
        event.channel.send.assert_awaited_once();text=event.channel.send.call_args.args[0]
        self.assertIn('<@11>',text);self.assertIn('X/6',text);self.assertIn('⬜'*6,text)
        self.assertNotIn(state['puzzle']['map']['name'],text);self.assertNotIn(state['puzzle']['map']['id'],text)
        kwargs=event.channel.send.call_args.kwargs
        self.assertEqual(set(kwargs),{'view','allowed_mentions'});self.assertEqual(kwargs['allowed_mentions'].to_dict()['parse'],[])
        self.assertTrue(kwargs['view'].is_persistent());self.assertEqual(kwargs['view'].play_button.label,'Play Portle')
        replay=interaction();await view.skip_button.callback(replay);replay.channel.send.assert_not_awaited()
        await show_round(replay,self.store,self.store.get(state['id'],'11'));replay.channel.send.assert_not_awaited()
    async def test_slash_guess_posts_once_with_public_play_button(self):
        client=PortleClient(self.store);group=client.tree.get_command('portle');event=interaction()
        await group.guess.callback(group,event,self.state['puzzle']['map']['name'])
        event.channel.send.assert_awaited_once();self.assertIn('1/6',event.channel.send.call_args.args[0])
        self.assertTrue(event.channel.send.call_args.kwargs['view'].is_persistent())
        self.assertNotIn(self.state['puzzle']['map']['name'],event.channel.send.call_args.args[0])
        await client.close()
    async def test_automatic_post_failure_preserves_result_and_gives_private_admin_guidance(self):
        error=discord.Forbidden(SimpleNamespace(status=403,reason='Forbidden'),{'code':50013,'message':'private raw detail'})
        for index,failure in enumerate([error,OSError('private raw detail')]):
            user=str(50+index);state=self.store.start(user)
            state=self.store.act(state['id'],user,0,guess=state['puzzle']['map']['name'])
            event=interaction(user);await event.response.defer(ephemeral=True);event.channel.send.side_effect=failure
            with self.assertLogs('portle.bot',level='WARNING') as logs:await post_daily_result(event,self.store,state)
            text=event.followup.send.call_args.args[0];self.assertIn('server administrator',text)
            self.assertNotIn('/portle share',text);self.assertNotIn('Share result',text)
            self.assertNotIn('private raw detail',text);self.assertNotIn('private raw detail',' '.join(logs.output))
            self.assertTrue(event.followup.send.call_args.kwargs['ephemeral'])
            restarted=GameStore(self.store.path,self.store.catalog)
            self.assertEqual(restarted.get(state['id'],user)['status'],'won')
            retry=interaction(user);await post_daily_result(retry,restarted,state);retry.channel.send.assert_not_awaited()
    async def test_result_post_errors_explain_permissions_access_and_network_without_raw_details(self):
        for status,code,expected in [(403,50013,'Send Messages in Threads'),(403,50001,'View Channel'),(400,50083,'archived'),(404,10003,'channel is unavailable'),(400,50035,'Discord rejected')]:
            error=discord.HTTPException(SimpleNamespace(status=status,reason='Error'),{'code':code,'message':'private raw detail'})
            text=result_post_error(error)
            self.assertIn(f'HTTP {status}',text);self.assertIn(f'Discord code {code}',text)
            self.assertIn(expected,text);self.assertNotIn('private raw detail',text)
            self.assertNotIn('/portle share',text);self.assertNotIn('Share result',text)
        self.assertIn('network error',result_post_error(OSError('private raw detail')))
    async def test_completed_score_posts_even_if_private_clue_rendering_fails(self):
        from portle.game import GameError
        state=self.store.act(self.state['id'],'11',0,guess=self.state['puzzle']['map']['name']);event=interaction()
        with patch.object(self.store,'image',side_effect=GameError('Clue image missing.')):
            with self.assertRaises(GameError):await show_round(event,self.store,state,announce=True)
        event.channel.send.assert_awaited_once()
    async def test_cli_reports_setup_failure_cleanly_without_a_traceback(self):
        from contextlib import redirect_stderr
        from io import StringIO
        from portle.__main__ import main
        env={'DISCORD_BOT_TOKEN':'unit-test-placeholder','DISCORD_GUILD_ID':'987','PORTLE_CLUE_SOURCE':'manual','PORTLE_CLUES':str(Path(self.temp.name)/'cli-clues'),'PORTLE_TIMEZONE':'UTC'}
        stderr=StringIO()
        with patch.dict('os.environ',env,clear=True),patch('sys.argv',['portle','bot']),patch('portle.__main__.load_dotenv'),patch('portle.store.GameStore',return_value=self.store),patch('portle.bot.PortleClient.run',side_effect=DiscordSetupError('Check DISCORD_GUILD_ID.')),redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:main()
        self.assertEqual(caught.exception.code,2);self.assertEqual(stderr.getvalue(),'Check DISCORD_GUILD_ID.\n')
        self.assertNotIn('unit-test-placeholder',stderr.getvalue())
    async def test_daily_board_private_deferred_and_safe_attachment(self):
        event=interaction();await show_round(event,self.store,self.state)
        self.assertTrue(event.response.flags['ephemeral']);kwargs=event.edit_original_response.call_args.kwargs
        attachment=kwargs['attachments'][0];self.assertEqual(attachment.filename,'portle-clue.png')
        Image.open(attachment.fp).verify()
        self.assertNotIn(self.state['puzzle']['map']['name'],kwargs['embed'].description)
        self.assertNotIn('footer',kwargs['embed'].to_dict())
        self.assertNotIn('Share result',[getattr(c,'label',None) for c in kwargs['view'].children])
    async def test_foreign_player_rejected(self):
        view=RoundView(self.store,self.state);event=interaction('99')
        self.assertFalse(await view.interaction_check(event));self.assertTrue(event.response.send_message.call_args.kwargs['ephemeral'])
    async def test_dropdown_lists_all_names_without_marking_the_answer(self):
        view=RoundView(self.store,self.state)
        self.assertEqual([o.label for o in view.map_select.options],self.store.catalog.choices())
        self.assertEqual([o.value for o in view.map_select.options],self.store.catalog.choices())
        self.assertTrue(all(not o.default and o.description is None for o in view.map_select.options))
        self.assertNotIn(view.previous_maps,view.children);self.assertNotIn(view.next_maps,view.children)
        self.assertNotIn(4,[c['type'] for row in view.to_components() for c in row['components']])
    async def test_dropdown_submits_private_daily_and_practice_guesses(self):
        for mode in ['daily','practice']:
            with self.subTest(mode=mode):
                state=self.store.start('11',mode);view=RoundView(self.store,state);event=interaction()
                event.id=101 if mode=='daily' else 102
                with patch.object(MapGuessSelect,'values',new_callable=PropertyMock,return_value=[state['puzzle']['map']['name']]):
                    await view.map_select.callback(event)
                updated=self.store.get(state['id'],'11');self.assertEqual(updated['status'],'won');self.assertEqual(updated['version'],1)
                self.assertTrue(event.response.flags['ephemeral']);self.assertFalse(event.response.flags['thinking'])
                self.assertTrue(event.edit_original_response.call_args.kwargs['view'].map_select.disabled)
                if mode=='daily':
                    event.channel.send.assert_awaited_once();text=event.channel.send.call_args.args[0]
                    self.assertIn('1/6',text);self.assertNotIn(state['puzzle']['map']['name'],text)
                else:event.channel.send.assert_not_awaited()
    async def test_dropdown_miss_advances_once_and_replayed_event_is_idempotent(self):
        view=RoundView(self.store,self.state)
        wrong=next(n for n in self.store.catalog.choices() if n!=self.state['puzzle']['map']['name'])
        with patch.object(MapGuessSelect,'values',new_callable=PropertyMock,return_value=[wrong]):
            for _ in range(2):await view.map_select.callback(interaction())
        updated=self.store.get(self.state['id'],'11')
        self.assertEqual(updated['version'],1);self.assertEqual(updated['status'],'playing');self.assertEqual(len(updated['attempts']),1)
        self.assertEqual(updated['attempts'][0]['name'],wrong)
        self.assertNotIn(wrong,[o.value for o in RoundView(self.store,updated).map_select.options])
    async def test_guessed_maps_stay_unavailable_after_resume_but_reset_for_new_practice(self):
        for mode in ['daily','practice']:
            with self.subTest(mode=mode):
                state=self.store.start('11',mode)
                wrong=next(m for m in self.store.catalog.maps if m['id']!=state['puzzle']['map']['id'])
                wrong['aliases'].append('test-alias')
                state=self.store.act(state['id'],'11',0,guess='test-alias')
                state=self.store.act(state['id'],'11',1,skip=True)
                restarted=GameStore(self.store.path,self.store.catalog)
                resumed=restarted.start('11') if mode=='daily' else restarted.get(state['id'],'11')
                view=RoundView(restarted,resumed)
                self.assertEqual([o.value for o in view.map_select.options],[n for n in self.store.catalog.choices() if n!=wrong['name']])
                self.assertEqual(resumed['version'],2)
                self.assertEqual([o.value for o in RoundView(self.store,self.store.start('99')).map_select.options],self.store.catalog.choices())
                self.assertEqual([o.value for o in RoundView(self.store,self.store.start('11','practice')).map_select.options],self.store.catalog.choices())
                wrong['aliases'].remove('test-alias')
    async def test_finished_round_with_all_names_used_has_a_valid_disabled_dropdown(self):
        state=self.state;answer=state['puzzle']['map']['name']
        for name in [n for n in self.store.catalog.choices() if n!=answer]+[answer]:
            state=self.store.act(state['id'],'11',state['version'],guess=name)
        view=RoundView(self.store,state)
        self.assertEqual(state['status'],'won');self.assertTrue(view.map_select.disabled)
        self.assertEqual(view.map_select.placeholder,'No maps remaining')
        components=[c for row in view.to_components() for c in row['components'] if c['type']==3]
        self.assertEqual(len(components[0]['options']),1);self.assertTrue(components[0]['disabled'])
    async def test_filtering_guesses_clamps_a_disappearing_last_page(self):
        maps=tuple({**self.store.catalog.maps[0],'id':f'MAP_{i}','name':f'Arena {i:02}'} for i in range(26))
        store=GameStore(Path(self.temp.name)/'page-shrink.db',Catalog(maps,'page-shrink-fixture'))
        state=store.start('11');wrong=next(m['name'] for m in maps if m['id']!=state['puzzle']['map']['id'])
        state=store.act(state['id'],'11',0,guess=wrong)
        view=RoundView(store,state,map_page=1)
        self.assertEqual(view.map_page,0);self.assertEqual(view.map_pages,1)
        self.assertEqual(len(view.map_select.options),25);self.assertNotIn(wrong,[o.value for o in view.map_select.options])
        self.assertNotIn(view.previous_maps,view.children);self.assertNotIn(view.next_maps,view.children)
    async def test_dropdown_rejects_foreign_stale_and_repeated_guesses_without_using_a_turn(self):
        wrong=next(n for n in self.store.catalog.choices() if n!=self.state['puzzle']['map']['name'])
        original=RoundView(self.store,self.state)
        with patch.object(MapGuessSelect,'values',new_callable=PropertyMock,return_value=[wrong]):
            foreign=interaction('99');await original.map_select.callback(foreign)
            self.assertEqual(self.store.get(self.state['id'],'11')['version'],0)
            self.assertTrue(foreign.followup.send.call_args.kwargs['ephemeral']);foreign.edit_original_response.assert_not_awaited()
            updated=self.store.act(self.state['id'],'11',0,guess=wrong)
            for view,message in [(original,'out of date'),(RoundView(self.store,updated),'already tried')]:
                event=interaction();await view.map_select.callback(event)
                self.assertIn(message,event.followup.send.call_args.args[0]);event.edit_original_response.assert_not_awaited()
                self.assertTrue(event.followup.send.call_args.kwargs['ephemeral'])
        self.assertEqual(self.store.get(self.state['id'],'11')['version'],1)
    async def test_large_roster_pages_are_free_and_preserve_the_board(self):
        maps=tuple({**self.store.catalog.maps[0],'id':f'MAP_{i}','name':f'Arena {i:02}'} for i in range(51))
        store=GameStore(Path(self.temp.name)/'large.db',Catalog(maps,'large-fixture'))
        state=store.start('11');view=RoundView(store,state,projection='top',clue_index=1)
        seen=[]
        for page,size in [(0,25),(1,25),(2,1)]:
            self.assertEqual(view.map_page,page);self.assertEqual(len(view.map_select.options),size)
            seen.extend(o.value for o in view.map_select.options)
            self.assertEqual(view.previous_maps.disabled,page==0);self.assertEqual(view.next_maps.disabled,page==2)
            self.assertEqual(view.projection,'top');self.assertEqual(view.clue_index,1)
            if page<2:
                event=interaction();await view.next_maps.callback(event)
                self.assertEqual(set(event.edit_original_response.call_args.kwargs),{'view'})
                view=event.edit_original_response.call_args.kwargs['view']
        self.assertEqual(seen,store.catalog.choices());self.assertEqual(store.get(state['id'],'11')['version'],0)
        event=interaction();await view.previous_maps.callback(event)
        view=event.edit_original_response.call_args.kwargs['view'];self.assertEqual(view.map_page,1)
        wrong=next(o.value for o in view.map_select.options if o.value!=state['puzzle']['map']['name'])
        with patch.object(MapGuessSelect,'values',new_callable=PropertyMock,return_value=[wrong]):await view.map_select.callback(interaction())
        self.assertEqual(store.get(state['id'],'11')['version'],1)
        event=interaction();await view.next_maps.callback(event)
        self.assertIn('out of date',event.followup.send.call_args.args[0]);event.edit_original_response.assert_not_awaited()
    async def test_skip_updates_original_private_board_once(self):
        view=RoundView(self.store,self.state);event=interaction();await view.skip_button.callback(event)
        self.assertEqual(self.store.get(self.state['id'],'11')['version'],1)
        self.assertFalse(event.response.flags['thinking']);self.assertEqual(event.edit_original_response.call_count,1)
    async def test_projection_is_free(self):
        view=RoundView(self.store,self.state);event=interaction();await view.projection_button.callback(event)
        self.assertEqual(self.store.get(self.state['id'],'11')['version'],0)
        self.assertEqual(event.edit_original_response.call_args.kwargs['view'].projection,'top')
    async def test_finished_board_disables_guesses_and_has_no_share_button(self):
        state=self.store.act(self.state['id'],'11',0,guess=self.state['puzzle']['map']['name']);view=RoundView(self.store,state)
        self.assertTrue(view.map_select.disabled);self.assertTrue(view.skip_button.disabled)
        self.assertNotIn('Share result',[getattr(c,'label',None) for c in view.children])
    async def test_manual_board_uses_authored_bytes_and_review_controls(self):
        library=ClueLibrary(Path(self.temp.name)/'clues')
        for i in range(1,7):
            output=BytesIO();Image.new('RGB',(32,24),(i*30,0,0)).save(output,format='PNG');library.upload(self.store.catalog.maps[0]['id'],i,output.getvalue())
        library.publish(self.store.catalog.maps[0]['id'])
        manual=GameStore(Path(self.temp.name)/'manual.db',self.store.catalog,clues=library);state=manual.start('11')
        event=interaction();await show_round(event,manual,state);kwargs=event.edit_original_response.call_args.kwargs
        self.assertEqual(kwargs['attachments'][0].fp.read(),manual.image(state))
        view=kwargs['view'];self.assertNotIn(view.projection_button,view.children);self.assertTrue(view.earlier_button.disabled)
        self.assertEqual([o.value for o in view.map_select.options],manual.catalog.choices())
        self.assertNotIn(state['puzzle']['map']['name'],kwargs['embed'].description)
        self.assertNotIn('footer',kwargs['embed'].to_dict())
        state=manual.act(state['id'],'11',0,skip=True);view=RoundView(manual,state);event=interaction()
        await view.earlier_button.callback(event)
        self.assertEqual(manual.get(state['id'],'11')['version'],1)
        self.assertEqual(event.edit_original_response.call_args.kwargs['attachments'][0].fp.read(),manual.image(state,clue=1))
