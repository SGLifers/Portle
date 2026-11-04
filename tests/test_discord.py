from io import BytesIO
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,PropertyMock,patch
from urllib.parse import parse_qs,urlparse
from PIL import Image
import discord
from portle.bot import DiscordSetupError,MapGuessSelect,PortleClient,RoundView,show_round
from portle.catalog import Catalog
from portle.store import GameStore
from portle.clues import ClueLibrary
from helpers import fixture_catalog


class Response:
    def __init__(self):self.done=False;self.flags=None;self.send_message=AsyncMock()
    def is_done(self):return self.done
    async def defer(self,**kwargs):self.done=True;self.flags=kwargs


def interaction(user='11'):
    return SimpleNamespace(user=SimpleNamespace(id=int(user)),guild_id=22,id=101,response=Response(),edit_original_response=AsyncMock(),followup=SimpleNamespace(send=AsyncMock()))


class DiscordTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=GameStore(Path(self.temp.name)/'discord.db',fixture_catalog());self.state=self.store.start('11')
    async def asyncTearDown(self):self.temp.cleanup()
    async def test_command_schema_and_no_privileged_intents(self):
        client=PortleClient(self.store);schema=client.tree.get_commands()[0].to_dict(client.tree)
        self.assertEqual(schema['name'],'portle');self.assertEqual(len(schema['options']),8)
        self.assertFalse(client.intents.message_content);self.assertFalse(client.intents.members)
        self.assertNotIn('token',str(schema).lower());await client.close()
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
        self.assertTrue(kwargs['view'].share_button.disabled)
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
    async def test_finished_board_disables_guess_and_enables_share(self):
        state=self.store.act(self.state['id'],'11',0,guess=self.state['puzzle']['map']['name']);view=RoundView(self.store,state)
        self.assertTrue(view.map_select.disabled);self.assertTrue(view.skip_button.disabled);self.assertFalse(view.share_button.disabled)
        event=interaction();await view.share_button.callback(event)
        text=event.response.send_message.call_args.args[0];self.assertNotIn(state['puzzle']['map']['name'],text)
        self.assertFalse(event.response.send_message.call_args.kwargs.get('ephemeral',False))
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
        state=manual.act(state['id'],'11',0,skip=True);view=RoundView(manual,state);event=interaction()
        await view.earlier_button.callback(event)
        self.assertEqual(manual.get(state['id'],'11')['version'],1)
        self.assertEqual(event.edit_original_response.call_args.kwargs['attachments'][0].fp.read(),manual.image(state,clue=1))
