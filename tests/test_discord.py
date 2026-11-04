from io import BytesIO
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,patch
from urllib.parse import parse_qs,urlparse
from PIL import Image
import discord
from portle.bot import DiscordSetupError,PortleClient,RoundView,show_round
from portle.store import GameStore
from portle.clues import ClueLibrary
from helpers import fixture_catalog


class Response:
    def __init__(self):self.done=False;self.flags=None;self.send_message=AsyncMock();self.send_modal=AsyncMock()
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
        self.assertTrue(view.guess_button.disabled);self.assertTrue(view.skip_button.disabled);self.assertFalse(view.share_button.disabled)
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
        self.assertNotIn(state['puzzle']['map']['name'],kwargs['embed'].description)
        state=manual.act(state['id'],'11',0,skip=True);view=RoundView(manual,state);event=interaction()
        await view.earlier_button.callback(event)
        self.assertEqual(manual.get(state['id'],'11')['version'],1)
        self.assertEqual(event.edit_original_response.call_args.kwargs['attachments'][0].fp.read(),manual.image(state,clue=1))
