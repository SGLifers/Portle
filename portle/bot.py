"""Discord transport. Importing this module never connects or sends messages."""
import asyncio
from io import BytesIO
import logging
import discord
from discord import app_commands

from .game import GameError,public_view,share_text,revealed_stage

ADMIN_ONLY_MESSAGE='This action is restricted to server administrators. Use /portle play for the daily puzzle.'


def server_admin_check(interaction):
    if interaction.guild_id is None or not interaction.permissions.administrator:
        raise app_commands.MissingPermissions(['administrator'])
    return True


async def report_error(interaction,message):
    if interaction.response.is_done():await interaction.followup.send(message,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
    else:await interaction.response.send_message(message,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())


def round_embed(state,projection,clue_index=None):
    data=public_view(state);active=data['status']=='playing'
    title='Which arena is this?' if active else ('Arena identified!' if data['status']=='won' else 'The arena was '+data['answer'])
    mode='Daily · '+data['day'] if data['mode']=='daily' else 'Practice'
    manual=data['clueSource']=='manual'
    description=f"{mode}\nClue **{data['turn']}/6** · "+(f"Screenshot **{clue_index or revealed_stage(state)}** of **{revealed_stage(state)}** revealed." if manual else f"**{data['portalCount']}** portals revealed.")
    if active:description+='\nChoose a map from the dropdown to submit a guess, or reveal the next clue. Each miss/skip uses one guess.'
    else:description+='\n**'+data['answer']+'**\n```\n'+data['share']+'\n```'
    embed=discord.Embed(title=title,description=description,color=0x78E8D1 if data['status']!='lost' else 0xE8B777)
    if data['attempts']:
        history='\n'.join(f"{i+1}. "+('🟩 ' if a['correct'] else '⬜ ' if a['kind']=='skip' else '🟥 ')+(a['name'] or 'Skipped') for i,a in enumerate(data['attempts']))
        embed.add_field(name='Your guesses',value=history,inline=False)
    embed.set_image(url='attachment://portle-clue.png')
    embed.set_footer(text=('Manually supplied screenshot' if manual else f"{'Top' if projection=='top' else 'Isometric'} view · real asset placements")+' · /portle maps for valid answers')
    return embed


def result_message(state):
    return f"<@{state['user_id']}>\n"+share_text(state)


def result_post_error(error):
    if isinstance(error,discord.HTTPException):
        reason=f'Discord rejected the result post (HTTP {error.status}, Discord code {error.code}). '
        if error.code==50001:
            reason+='Check that this same bot is installed in this server and has View Channel access to this channel, including private-thread membership. '
        elif error.code==50013 or isinstance(error,discord.Forbidden):
            reason+='Allow the Portle bot View Channel and Send Messages in this channel; threads also need Send Messages in Threads. Check channel/category permission overrides. '
        elif error.code==50083:
            reason+='The thread is archived; unarchive it or share in an active channel. '
        elif error.code==10003:
            reason+='The channel is unavailable; share in an accessible server channel. '
    elif isinstance(error,GameError):reason='No accessible server channel was available for the result post. '
    else:reason='A network error prevented confirming the result post. '
    return 'Your result is saved. '+reason+'Check whether it appeared, then use Share result or /portle share to retry if needed.'


async def post_daily_result(interaction,store,state):
    if state['mode']!='daily' or state['status']=='playing':return
    if not await asyncio.to_thread(store.claim_result_post,state['id'],interaction.user.id):return
    try:
        if interaction.guild_id is None or interaction.channel is None:raise GameError('A server channel is required.')
        message=await interaction.channel.send(result_message(state),view=PlayPortleView(store),allowed_mentions=discord.AllowedMentions.none())
    except (discord.HTTPException,OSError,GameError) as error:
        await asyncio.to_thread(store.record_result_post,state['id'])
        logging.getLogger(__name__).warning('Automatic result post failed: %s (HTTP %s, Discord code %s)',type(error).__name__,getattr(error,'status','n/a'),getattr(error,'code','n/a'))
        return await report_error(interaction,result_post_error(error))
    await asyncio.to_thread(store.record_result_post,state['id'],message.id)


async def show_round(interaction,store,state,projection='iso',replace=False,clue_index=None,announce=False):
    if not interaction.response.is_done():await interaction.response.defer(ephemeral=True,thinking=not replace)
    try:
        image=await asyncio.to_thread(store.image,state,projection,clue_index)
        await interaction.edit_original_response(content=None,embed=round_embed(state,projection,clue_index),
            attachments=[discord.File(BytesIO(image),filename='portle-clue.png')],
            view=RoundView(store,state,projection,clue_index),allowed_mentions=discord.AllowedMentions.none())
    finally:
        if announce:await post_daily_result(interaction,store,state)


class PlayPortleView(discord.ui.View):
    def __init__(self,store):
        super().__init__(timeout=None);self.store=store

    @discord.ui.button(label='Play Portle',style=discord.ButtonStyle.success,custom_id='portle:play-daily:v1')
    async def play_button(self,interaction,button):
        if interaction.guild_id is None:return await report_error(interaction,'Play Portle in a server to open your private daily puzzle.')
        await interaction.response.defer(ephemeral=True,thinking=True)
        try:
            state=await asyncio.to_thread(self.store.start,interaction.user.id,guild_id=interaction.guild_id)
            await show_round(interaction,self.store,state)
        except GameError as error:await report_error(interaction,str(error))

    async def on_error(self,interaction,error,item):
        logging.getLogger(__name__).error('Play button failed: %s',type(error).__name__)
        await report_error(interaction,'Could not open your puzzle. Your progress is saved; try Play Portle again or /portle play.')


class MapGuessSelect(discord.ui.Select):
    def __init__(self,board,names,finished):
        super().__init__(placeholder='Choose a map to submit your guess…' if names else 'No maps remaining',
            options=[discord.SelectOption(label=name,value=name) for name in names] or [discord.SelectOption(label='No maps remaining',value='none')],
            min_values=1,max_values=1,disabled=finished or not names,row=0)
        self.board=board

    async def callback(self,interaction):
        await interaction.response.defer(ephemeral=True,thinking=False)
        try:
            state=await asyncio.to_thread(self.board.store.act,self.board.round_id,interaction.user.id,self.board.version,guess=self.values[0],event_id=str(interaction.id))
            await show_round(interaction,self.board.store,state,self.board.projection,replace=True,announce=True)
        except GameError as exc:await report_error(interaction,str(exc))


class RoundView(discord.ui.View):
    def __init__(self,store,state,projection='iso',clue_index=None,map_page=0):
        super().__init__(timeout=900)
        self.store=store;self.round_id=state['id'];self.owner=state['user_id'];self.version=state['version'];self.projection=projection;self.mode=state['mode']
        finished=state['status']!='playing'
        guessed={a['map_id'] for a in state['attempts'] if a['kind']=='guess'}
        guessed_names={m['name'] for m in store.catalog.maps if m['id'] in guessed}
        names=[name for name in store.catalog.choices() if name not in guessed_names]
        self.map_pages=max(1,(len(names)+24)//25)
        self.map_page=max(0,min(map_page,self.map_pages-1))
        self.map_select=MapGuessSelect(self,names[self.map_page*25:(self.map_page+1)*25],finished)
        self.add_item(self.map_select)
        if self.map_pages<=1:self.remove_item(self.previous_maps);self.remove_item(self.next_maps)
        else:
            self.previous_maps.disabled=finished or self.map_page==0
            self.next_maps.disabled=finished or self.map_page>=self.map_pages-1
            self.map_select.placeholder=f'Choose a map to guess · page {self.map_page+1}/{self.map_pages}'
        self.skip_button.disabled=finished;self.share_button.disabled=not finished
        self.projection_button.label='Top view' if projection=='iso' else 'Isometric view'
        self.clue_index=clue_index or revealed_stage(state)
        if state['puzzle'].get('clueSource')=='manual':
            self.remove_item(self.projection_button)
            self.earlier_button.disabled=self.clue_index<=1;self.later_button.disabled=self.clue_index>=revealed_stage(state)
        else:self.remove_item(self.earlier_button);self.remove_item(self.later_button)

    async def interaction_check(self,interaction):
        if str(interaction.user.id)!=self.owner:
            await report_error(interaction,'This is another player\'s round. Use /portle play for your own clues.');return False
        if self.mode=='practice':
            try:server_admin_check(interaction)
            except app_commands.MissingPermissions:
                await report_error(interaction,ADMIN_ONLY_MESSAGE);return False
        return True

    async def change_map_page(self,interaction,offset):
        await interaction.response.defer(ephemeral=True,thinking=False)
        try:
            state=await asyncio.to_thread(self.store.get,self.round_id,interaction.user.id)
            if state['version']!=self.version or state['status']!='playing':raise GameError('This board is out of date. Use /portle play to refresh your daily round.')
            await interaction.edit_original_response(view=RoundView(self.store,state,self.projection,self.clue_index,self.map_page+offset))
        except GameError as exc:await report_error(interaction,str(exc))

    @discord.ui.button(label='Previous maps',style=discord.ButtonStyle.secondary,row=1)
    async def previous_maps(self,interaction,button):await self.change_map_page(interaction,-1)

    @discord.ui.button(label='Next maps',style=discord.ButtonStyle.secondary,row=1)
    async def next_maps(self,interaction,button):await self.change_map_page(interaction,1)

    @discord.ui.button(label='Reveal more / skip',style=discord.ButtonStyle.secondary,row=2)
    async def skip_button(self,interaction,button):
        await interaction.response.defer(ephemeral=True,thinking=False)
        try:
            state=await asyncio.to_thread(self.store.act,self.round_id,interaction.user.id,self.version,skip=True,event_id=str(interaction.id))
            await show_round(interaction,self.store,state,self.projection,replace=True,announce=True)
        except GameError as exc:await report_error(interaction,str(exc))

    @discord.ui.button(label='Top view',style=discord.ButtonStyle.secondary,row=2)
    async def projection_button(self,interaction,button):
        await interaction.response.defer(ephemeral=True,thinking=False)
        state=await asyncio.to_thread(self.store.get,self.round_id,interaction.user.id)
        await show_round(interaction,self.store,state,'top' if self.projection=='iso' else 'iso',replace=True)

    @discord.ui.button(label='Earlier clue',style=discord.ButtonStyle.secondary,row=2)
    async def earlier_button(self,interaction,button):
        await interaction.response.defer(ephemeral=True,thinking=False)
        state=await asyncio.to_thread(self.store.get,self.round_id,interaction.user.id)
        await show_round(interaction,self.store,state,replace=True,clue_index=max(1,self.clue_index-1))

    @discord.ui.button(label='Later clue',style=discord.ButtonStyle.secondary,row=2)
    async def later_button(self,interaction,button):
        await interaction.response.defer(ephemeral=True,thinking=False)
        state=await asyncio.to_thread(self.store.get,self.round_id,interaction.user.id)
        await show_round(interaction,self.store,state,replace=True,clue_index=min(revealed_stage(state),self.clue_index+1))

    @discord.ui.button(label='Share result',style=discord.ButtonStyle.primary,row=2)
    async def share_button(self,interaction,button):
        state=await asyncio.to_thread(self.store.get,self.round_id,interaction.user.id)
        try:result=result_message(state)
        except GameError as exc:return await report_error(interaction,str(exc))
        await interaction.response.send_message(result,view=PlayPortleView(self.store),allowed_mentions=discord.AllowedMentions.none())

    async def on_error(self,interaction,error,item):
        logging.getLogger(__name__).error('Board action failed: %s',type(error).__name__)
        await report_error(interaction,'Could not complete that action. Your progress is saved; reopen the daily with /portle play.')


class PortleCommands(app_commands.Group):
    def __init__(self,store):
        super().__init__(name='portle',description='Guess the arena from its portal placements',guild_only=True)
        self.store=store

    @app_commands.command(description='Play or resume your private daily map puzzle')
    async def play(self,interaction:discord.Interaction):
        await interaction.response.defer(ephemeral=True,thinking=True)
        state=await asyncio.to_thread(self.store.start,interaction.user.id,guild_id=interaction.guild_id)
        await show_round(interaction,self.store,state)

    @app_commands.command(description='Admins only: start a practice round, separate from daily scores')
    @app_commands.check(server_admin_check)
    async def practice(self,interaction:discord.Interaction):
        await interaction.response.defer(ephemeral=True,thinking=True)
        state=await asyncio.to_thread(self.store.start,interaction.user.id,'practice',interaction.guild_id)
        await show_round(interaction,self.store,state)

    @app_commands.command(description='Admins only: reset a member\'s current daily score and guesses across servers')
    @app_commands.check(server_admin_check)
    @app_commands.describe(player='Server member whose current daily round will be reset')
    async def reset(self,interaction:discord.Interaction,player:discord.Member):
        await interaction.response.defer(ephemeral=True,thinking=True)
        result=await asyncio.to_thread(self.store.reset_daily,player.id,actor_id=interaction.user.id,guild_id=interaction.guild_id,event_id=interaction.id)
        if result['changed']:
            text=f"Reset <@{player.id}>'s daily score and guesses for {result['day']}. They can use Play Portle or /portle play to reopen today's puzzle. Daily progress is shared across servers. Earlier days and practice are preserved. Existing public result posts remain visible."
        else:text=f"<@{player.id}> has no daily score or guesses to reset for {result['day']}."
        await interaction.edit_original_response(content=text,allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(description='Guess today\'s map; autocomplete lists valid answers')
    @app_commands.describe(map_name='Arena name')
    async def guess(self,interaction:discord.Interaction,map_name:str):
        await interaction.response.defer(ephemeral=True,thinking=True)
        try:
            state=await asyncio.to_thread(self.store.start,interaction.user.id,guild_id=interaction.guild_id)
            state=await asyncio.to_thread(self.store.act,state['id'],interaction.user.id,state['version'],guess=map_name,event_id=str(interaction.id))
            await show_round(interaction,self.store,state,announce=True)
        except GameError as exc:await report_error(interaction,str(exc))

    @guess.autocomplete('map_name')
    async def autocomplete_maps(self,interaction,current:str):
        return [app_commands.Choice(name=name,value=name) for name in self.store.catalog.choices(current)[:25]]

    @app_commands.command(description='Show your daily wins, streaks and guess distribution')
    async def stats(self,interaction:discord.Interaction):
        await interaction.response.defer(ephemeral=True,thinking=True)
        stats=await asyncio.to_thread(self.store.stats,interaction.user.id)
        text=f"Played **{stats['played']}** · Wins **{stats['wins']}** · Win rate **{stats['winPercent']}%**\nCurrent streak **{stats['currentStreak']}** · Best **{stats['bestStreak']}**\n\n"+'\n'.join(f"{n} guesses: {count}" for n,count in stats['distribution'].items())
        await interaction.edit_original_response(embed=discord.Embed(title='Your Portle stats',description=text,color=0x78E8D1))

    @app_commands.command(description='Show daily records for players who joined in this server')
    async def leaderboard(self,interaction:discord.Interaction):
        await interaction.response.defer(ephemeral=True,thinking=True)
        rows=await asyncio.to_thread(self.store.leaderboard,interaction.guild_id)
        text='\n'.join(f"**{i+1}.** <@{r['user_id']}> · {r['wins']} wins · {r['currentStreak']} streak" for i,r in enumerate(rows)) or 'No finished daily rounds yet. Play with /portle play.'
        await interaction.edit_original_response(embed=discord.Embed(title='Portle · server players',description=text,color=0x78E8D1),allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(description='Share your finished daily score without revealing the map')
    async def share(self,interaction:discord.Interaction):
        state=await asyncio.to_thread(self.store.start,interaction.user.id,guild_id=interaction.guild_id)
        try:result=result_message(state)
        except GameError as exc:return await report_error(interaction,str(exc))
        await interaction.response.send_message(result,view=PlayPortleView(self.store),allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(description='List all map names accepted by the game')
    async def maps(self,interaction:discord.Interaction):
        await interaction.response.send_message('**Available arenas**\n'+', '.join(self.store.catalog.choices()),ephemeral=True)

    @app_commands.command(description='How to play Portle')
    async def help(self,interaction:discord.Interaction):
        clues=('Six guesses and six manually supplied screenshots. Revisit revealed clues for free.\n' if self.store.clues else 'Six guesses. Clues show 1, 2, 4, 8, 16, then all portals. Top/isometric views are free.\n')
        await interaction.response.send_message(
            '**PORTLE** — guess the arena from real portal placements.\n'
            +clues+'Choose a map from the board dropdown to submit a guess. Wrong guesses and skips reveal the next clue. Invalid or repeated names are free.\n'
            +
            f'Daily resets at midnight **{self.store.zone.key}**; everyone gets the same map with private progress.\n'
            '`/portle play` daily · `/portle practice` admins only · `/portle guess` guess daily · `/portle maps` answer list · `/portle stats` records.\n'
            'Admins: `/portle reset player` resets that member\'s current daily score and guesses. Earlier days and practice are preserved; daily progress is shared across servers.\n'
            'Finishing a daily automatically posts your score and squares in this channel, without the map name or clues. Anyone can use **Play Portle** on a result to open their own private daily. **Share result** or `/portle share` can post a score again. Practice does not auto-post. Private board controls expire after 15 minutes; public Play buttons survive restarts. Resume the daily with `/portle play`. Server administrators can start fresh practice with `/portle practice`; practice does not affect daily records.',ephemeral=True)

    async def on_error(self,interaction,error):
        original=getattr(error,'original',error)
        if isinstance(original,app_commands.MissingPermissions) and 'administrator' in original.missing_permissions:
            return await report_error(interaction,ADMIN_ONLY_MESSAGE)
        logging.getLogger(__name__).error('Command failed: %s',type(original).__name__)
        await report_error(interaction,str(original) if isinstance(original,GameError) else 'The command could not finish. Your progress is saved; try /portle play again.')


class DiscordSetupError(RuntimeError):
    """An actionable startup failure, safe to print without HTTP/token details."""


class PortleClient(discord.Client):
    def __init__(self,store,guild_id=None):
        intents=discord.Intents.none();intents.guilds=True
        super().__init__(intents=intents,allowed_mentions=discord.AllowedMentions.none())
        self.tree=app_commands.CommandTree(self);self.tree.add_command(PortleCommands(store));self.guild_id=guild_id;self.store=store

    async def setup_hook(self):
        try:
            if self.guild_id:
                guild=discord.Object(id=self.guild_id);self.tree.copy_global_to(guild=guild);commands=await self.tree.sync(guild=guild)
            else:commands=await self.tree.sync()
        except (discord.Forbidden,discord.NotFound) as error:
            target='the server configured in DISCORD_GUILD_ID' if self.guild_id else 'this application'
            message=f'Discord accepted the bot token, but could not register /portle commands for {target} (HTTP {error.status}, Discord code {error.code}).\n'
            if self.guild_id:
                message+='Check DISCORD_GUILD_ID in local .env: right-click the Discord server icon and Copy Server ID, not a channel, user or application ID. Environment variables override .env.\n'
                message+='Install this same application with Add to server (Guild Install), using both bot and applications.commands scopes. Installing only to your user account is insufficient.\n'
            else:message+='Check this application\'s installation/command settings in the Discord Developer Portal.\n'
            if self.application_id:
                permissions=discord.Permissions(view_channel=True,send_messages=True,embed_links=True,attach_files=True)
                message+='Server installation link: '+discord.utils.oauth_url(self.application_id,permissions=permissions)+'\n'
            message+='After correcting access, run ./run.sh again. See docs/DISCORD_SETUP.md.'
            raise DiscordSetupError(message) from None
        self.add_view(PlayPortleView(self.store))
        logging.getLogger(__name__).info('Registered %d command groups',len(commands))

    async def on_ready(self):logging.getLogger(__name__).info('Portle connected and ready')
