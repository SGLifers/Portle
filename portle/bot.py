"""Discord transport. Importing this module never connects or sends messages."""
import asyncio
from contextlib import suppress
from datetime import datetime
from io import BytesIO
import json
import logging
import discord
from discord import app_commands
from discord.ext import tasks

from .game import GameError,public_view,share_text,revealed_stage
from .announcements import due_periods,board_embeds

ADMIN_ONLY_MESSAGE='This action is restricted to server administrators. Use /portle play for the daily puzzle.'


def server_admin_check(interaction):
    if interaction.guild_id is None or not interaction.permissions.administrator:
        raise app_commands.MissingPermissions(['administrator'])
    return True


async def report_error(interaction,message):
    if interaction.response.is_done():await interaction.followup.send(message,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
    else:await interaction.response.send_message(message,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())


async def verify_private_board(interaction,owner):
    """Check Discord's actual destination before sending any private board data."""
    reason=None
    if str(interaction.user.id)!=str(owner):reason='owner_mismatch'
    else:
        try:message=await interaction.original_response()
        except (discord.HTTPException,discord.ClientException,OSError):reason='verification_unavailable'
        else:
            if getattr(getattr(message,'flags',None),'ephemeral',False) is not True:reason='non_private_response'
            else:
                metadata=getattr(message,'interaction_metadata',None) or getattr(message,'interaction',None)
                if metadata is None:reason='recipient_unverified'
                elif str(getattr(getattr(metadata,'user',None),'id',''))!=str(owner):
                    reason='recipient_mismatch'
    if reason:
        response_type=getattr(getattr(interaction.response,'type',None),'name','unknown')
        logging.getLogger(__name__).warning('Private board blocked: %s (response=%s)',reason,response_type)
        raise GameError('Could not verify a private board for you. Use /portle play to reopen your own puzzle.')


def server_install_url(application_id):
    permissions=discord.Permissions(view_channel=True,send_messages=True,embed_links=True,attach_files=True)
    return discord.utils.oauth_url(application_id,permissions=permissions)+'&integration_type=0'


def round_embed(state,projection,clue_index=None):
    data=public_view(state);active=data['status']=='playing'
    title='Which arena is this?' if active else ('Arena identified!' if data['status']=='won' else 'The arena was '+data['answer'])
    mode='Daily · '+data['day'] if data['mode']=='daily' else 'Practice'
    manual=data['clueSource']=='manual'
    description=f"{mode} · <@{state['user_id']}>\nClue **{data['turn']}/6** · "+(f"Screenshot **{clue_index or revealed_stage(state)}** of **{revealed_stage(state)}** revealed." if manual else f"**{data['portalCount']}** portals revealed.")
    if active:description+='\n\n**🟢 Make your guess using a map menu below.**\nSelecting a map submits your guess. A wrong guess or skip uses one guess.'
    else:description+='\n**'+data['answer']+'**\n```\n'+data['share']+'\n```'
    embed=discord.Embed(title=title,description=description,color=0x78E8D1 if data['status']!='lost' else 0xE8B777)
    if data['attempts']:
        history='\n'.join(f"{i+1}. "+('🟩 ' if a['correct'] else '⬜ ' if a['kind']=='skip' else '🟥 ')+(a['name'] or 'Skipped') for i,a in enumerate(data['attempts']))
        embed.add_field(name='Your guesses',value=history,inline=False)
    embed.set_image(url='attachment://portle-clue.png')
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
            reason+='The thread is archived; a server administrator can unarchive it. '
        elif error.code==10003:
            reason+='The channel is unavailable; a server administrator can review its access. '
    elif isinstance(error,GameError):reason='No accessible server channel was available for the result post. '
    else:reason='A network error prevented confirming the result post. '
    return 'Your result is saved. '+reason+'Check this channel for the result and ask a server administrator to review the bot\'s access if it is missing.'


async def result_destination(interaction,store,manual):
    guild=getattr(interaction,'guild',None)
    if interaction.guild_id is None or guild is None or guild.id!=interaction.guild_id or guild.me is None:
        raise GameError('Portle must be installed and ready in this server before posting results.')
    config=await asyncio.to_thread(store.results.configure,interaction.guild_id)
    if config and not config['enabled']:
        if manual:raise GameError('Result posts are disabled in this server. Ask an administrator to enable /portle results.')
        return None
    if config:
        channel=interaction.client.get_channel(int(config['channel_id'])) or await interaction.client.fetch_channel(int(config['channel_id']))
    elif manual:raise GameError('Ask a server administrator to enable sharing with /portle results channel:#games.')
    else:channel=interaction.channel
    if channel is None or getattr(getattr(channel,'guild',None),'id',None)!=interaction.guild_id:
        raise GameError('The results channel must be in this server.')
    bot_permissions=channel.permissions_for(guild.me)
    if not bot_permissions.view_channel or not bot_permissions.send_messages:
        raise GameError('Allow Portle View Channel and Send Messages in the results channel.')
    member_permissions=channel.permissions_for(interaction.user)
    if not member_permissions.view_channel or not member_permissions.send_messages:
        raise GameError('You need View Channel and Send Messages in the results channel to share there.')
    return channel


async def post_daily_result(interaction,store,state,*,manual=False):
    if not manual and (state['mode']!='daily' or state['status']=='playing'):return
    try:
        state=await asyncio.to_thread(store.results.completed,interaction.user.id,state['id'])
        if not manual and await asyncio.to_thread(store.results.legacy_post,state['id']):return
        channel=await result_destination(interaction,store,manual)
        if channel is None:return
        claim=await asyncio.to_thread(store.results.claim,state['id'],interaction.user.id,interaction.guild_id,channel.id,manual)
    except GameError as error:return await report_error(interaction,str(error))
    except (discord.HTTPException,OSError) as error:return await report_error(interaction,result_post_error(error))
    if not claim['claimed']:
        if manual:
            text=(f"Your results have already been posted in <#{claim['channel_id']}>." if claim['status']=='sent'
                else 'A result post is already in progress or could not be confirmed. Check the results channel before asking an administrator for help; it will not be sent again automatically.')
            await report_error(interaction,text)
        return
    try:
        message=await channel.send(result_message(claim['state']),view=PlayPortleView(store),allowed_mentions=discord.AllowedMentions.none(),nonce=store.results.nonce(claim))
    except (discord.HTTPException,OSError) as error:
        rejected=isinstance(error,discord.HTTPException) and error.status in (403,404,429)
        await asyncio.to_thread(store.results.finish,claim,'rejected' if rejected else 'uncertain')
        logging.getLogger(__name__).warning('Result post failed: %s (HTTP %s, Discord code %s)',type(error).__name__,getattr(error,'status','n/a'),getattr(error,'code','n/a'))
        return await report_error(interaction,result_post_error(error))
    await asyncio.to_thread(store.results.finish,claim,'sent',message.id)
    if manual:await report_error(interaction,f'Results shared in <#{channel.id}>.')


async def show_round(interaction,store,state,projection='iso',replace=False,clue_index=None,announce=False):
    if not interaction.response.is_done():await interaction.response.defer(ephemeral=True,thinking=not replace)
    try:
        await verify_private_board(interaction,state['user_id'])
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
            await verify_private_board(interaction,interaction.user.id)
            state=await asyncio.to_thread(self.store.start,interaction.user.id,guild_id=interaction.guild_id)
            await show_round(interaction,self.store,state)
        except GameError as error:await report_error(interaction,str(error))

    async def on_error(self,interaction,error,item):
        logging.getLogger(__name__).error('Play button failed: %s',type(error).__name__)
        await report_error(interaction,'Could not open your puzzle. Your progress is saved; try Play Portle again or /portle play.')


MAP_CATEGORIES=('Arena','Simulation','Royale')
ROYALE_MAP_IDS=frozenset({'MAP_Erosion','MAP_Fracture','MAP_Glacier','MAP_Inferno','MAP_Outskirts','MAP_Sanctum'})


def map_category(item):
    # UI classification stays outside snapshots/revisions so daily selection is unchanged.
    if item['id'].startswith('MAP_Simulation_'):return 'Simulation'
    return 'Royale' if item['id'] in ROYALE_MAP_IDS else 'Arena'


class MapGuessSelect(discord.ui.Select):
    def __init__(self,board,names,finished,category,row):
        if len(names)>25:raise GameError(f'{category} has more than 25 remaining maps. Use /portle guess to enter a map name.')
        placeholder=f'{category} — round finished' if finished else f'🟢 GUESS — {category}' if names else f'{category} — no maps remaining'
        super().__init__(placeholder=placeholder,
            options=[discord.SelectOption(label=name,value=name) for name in names] or [discord.SelectOption(label='No maps remaining',value='none')],
            min_values=1,max_values=1,disabled=finished or not names,row=row)
        self.board=board;self.category=category

    async def callback(self,interaction):
        await interaction.response.defer(ephemeral=True,thinking=False)
        try:
            await verify_private_board(interaction,self.board.owner)
            state=await asyncio.to_thread(self.board.store.act,self.board.round_id,interaction.user.id,self.board.version,guess=self.values[0],event_id=str(interaction.id))
            await show_round(interaction,self.board.store,state,self.board.projection,replace=True,announce=True)
        except GameError as exc:await report_error(interaction,str(exc))


class RoundView(discord.ui.View):
    def __init__(self,store,state,projection='iso',clue_index=None):
        super().__init__(timeout=900)
        self.store=store;self.round_id=state['id'];self.owner=state['user_id'];self.version=state['version'];self.projection=projection;self.mode=state['mode']
        finished=state['status']!='playing'
        if not finished or self.mode!='daily':self.remove_item(self.share_results)
        guessed={a['map_id'] for a in state['attempts'] if a['kind']=='guess'}
        self.map_selects={}
        for row,category in enumerate(MAP_CATEGORIES):
            names=sorted((m['name'] for m in store.catalog.maps if m['id'] not in guessed and map_category(m)==category),key=str.casefold)
            select=MapGuessSelect(self,names,finished,category,row)
            self.map_selects[category]=select;self.add_item(select)
        self.arena_select=self.map_selects['Arena']
        self.simulation_select=self.map_selects['Simulation']
        self.royale_select=self.map_selects['Royale']
        self.skip_button.disabled=finished
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

    @discord.ui.button(label='Skip guess (costs 1)',style=discord.ButtonStyle.secondary,row=4)
    async def skip_button(self,interaction,button):
        await interaction.response.defer(ephemeral=True,thinking=False)
        try:
            await verify_private_board(interaction,self.owner)
            state=await asyncio.to_thread(self.store.act,self.round_id,interaction.user.id,self.version,skip=True,event_id=str(interaction.id))
            await show_round(interaction,self.store,state,self.projection,replace=True,announce=True)
        except GameError as exc:await report_error(interaction,str(exc))

    @discord.ui.button(label='Top view',style=discord.ButtonStyle.secondary,row=3)
    async def projection_button(self,interaction,button):
        await interaction.response.defer(ephemeral=True,thinking=False)
        await verify_private_board(interaction,self.owner)
        state=await asyncio.to_thread(self.store.get,self.round_id,interaction.user.id)
        await show_round(interaction,self.store,state,'top' if self.projection=='iso' else 'iso',replace=True)

    @discord.ui.button(label='Earlier clue',style=discord.ButtonStyle.secondary,row=3)
    async def earlier_button(self,interaction,button):
        await interaction.response.defer(ephemeral=True,thinking=False)
        await verify_private_board(interaction,self.owner)
        state=await asyncio.to_thread(self.store.get,self.round_id,interaction.user.id)
        await show_round(interaction,self.store,state,replace=True,clue_index=max(1,self.clue_index-1))

    @discord.ui.button(label='Later clue',style=discord.ButtonStyle.secondary,row=3)
    async def later_button(self,interaction,button):
        await interaction.response.defer(ephemeral=True,thinking=False)
        await verify_private_board(interaction,self.owner)
        state=await asyncio.to_thread(self.store.get,self.round_id,interaction.user.id)
        await show_round(interaction,self.store,state,replace=True,clue_index=min(revealed_stage(state),self.clue_index+1))

    @discord.ui.button(label='Share results',style=discord.ButtonStyle.success,row=4)
    async def share_results(self,interaction,button):
        await interaction.response.defer(ephemeral=True,thinking=True)
        try:
            state=await asyncio.to_thread(self.store.results.completed,interaction.user.id,self.round_id)
            await post_daily_result(interaction,self.store,state,manual=True)
        except GameError as error:await report_error(interaction,str(error))

    async def on_error(self,interaction,error,item):
        logging.getLogger(__name__).error('Board action failed: %s',type(error).__name__)
        await report_error(interaction,'Could not complete that action. Your progress is saved; reopen the daily with /portle play.')


class PortleCommands(app_commands.Group):
    def __init__(self,store,reset_guild_ids=()):
        super().__init__(name='portle',description='Guess the arena from its portal placements',guild_only=True,
            allowed_installs=app_commands.AppInstallationType(guild=True,user=False),
            allowed_contexts=app_commands.AppCommandContext(guild=True,dm_channel=False,private_channel=False))
        self.store=store
        self.reset_guild_ids=frozenset(reset_guild_ids)

    @app_commands.command(description='Play or resume your private daily map puzzle')
    async def play(self,interaction:discord.Interaction):
        await interaction.response.defer(ephemeral=True,thinking=True)
        await verify_private_board(interaction,interaction.user.id)
        state=await asyncio.to_thread(self.store.start,interaction.user.id,guild_id=interaction.guild_id)
        await show_round(interaction,self.store,state)

    @app_commands.command(description='Admins only: start a practice round, separate from daily scores')
    @app_commands.check(server_admin_check)
    async def practice(self,interaction:discord.Interaction):
        await interaction.response.defer(ephemeral=True,thinking=True)
        await verify_private_board(interaction,interaction.user.id)
        state=await asyncio.to_thread(self.store.start,interaction.user.id,'practice',interaction.guild_id)
        await show_round(interaction,self.store,state)

    @app_commands.command(description='Allowlisted server admins: reset a member\'s shared daily score and guesses')
    @app_commands.check(server_admin_check)
    @app_commands.describe(player='Server member whose current daily round will be reset')
    async def reset(self,interaction:discord.Interaction,player:discord.Member):
        server_admin_check(interaction)
        if interaction.guild_id not in self.reset_guild_ids:
            raise GameError('Daily resets are disabled in this server. The bot operator must allowlist this server before administrators can use /portle reset.')
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
            await verify_private_board(interaction,interaction.user.id)
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

    @app_commands.command(description='Share your completed daily in this server\'s configured results channel')
    async def share(self,interaction:discord.Interaction):
        if interaction.guild_id is None:raise GameError('Share results from a server where Portle is installed.')
        await interaction.response.defer(ephemeral=True,thinking=True)
        state=await asyncio.to_thread(self.store.results.completed,interaction.user.id)
        await post_daily_result(interaction,self.store,state,manual=True)

    @app_commands.command(description='Admins only: choose a results channel or enable/disable result posts')
    @app_commands.check(server_admin_check)
    @app_commands.describe(channel='Text channel for shared and automatic results; selecting enables posts',enabled='Enable or disable result posts; omit both options to check status')
    async def results(self,interaction:discord.Interaction,channel:discord.TextChannel=None,enabled:bool=None):
        server_admin_check(interaction)
        await interaction.response.defer(ephemeral=True,thinking=True)
        if channel is not None:
            if channel.guild.id!=interaction.guild_id:raise GameError('Choose a text channel in this server.')
            if not interaction.guild or not interaction.guild.me:raise GameError('Portle must be installed and ready in this server first.')
            permissions=channel.permissions_for(interaction.guild.me)
            if not permissions.view_channel or not permissions.send_messages:raise GameError('Allow Portle View Channel and Send Messages in that channel first.')
        config=await asyncio.to_thread(self.store.results.configure,interaction.guild_id,channel.id if channel else None,enabled)
        if config is None:text='Cross-server sharing is off until an administrator chooses `/portle results channel:#games`. Automatic completions still post in the channel where a game finishes.'
        else:text=f"Result posts: **{'enabled' if config['enabled'] else 'disabled'}** in <#{config['channel_id']}>. Share results and automatic completions use this channel, once per player/day/server. Scheduled recaps are configured separately with /portle announcements."
        await interaction.edit_original_response(content=text,allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(description='Admins only: configure daily and weekly leaderboard announcements')
    @app_commands.check(server_admin_check)
    @app_commands.describe(channel='Server text channel for recaps; selecting a channel enables them',enabled='Enable or disable automatic recaps; omit both options to check status')
    async def announcements(self,interaction:discord.Interaction,channel:discord.TextChannel=None,enabled:bool=None):
        await interaction.response.defer(ephemeral=True,thinking=True)
        if channel is not None:
            if channel.guild.id!=interaction.guild_id:raise GameError('Choose a text channel in this server.')
            if not interaction.guild or not interaction.guild.me:raise GameError('Portle is not ready in this server yet. Try configuring the channel again after it connects.')
            permissions=channel.permissions_for(interaction.guild.me)
            if not all((permissions.view_channel,permissions.send_messages,permissions.embed_links)):
                raise GameError('Allow Portle View Channel, Send Messages and Embed Links in that channel first.')
        config=await asyncio.to_thread(self.store.announcements.configure,interaction.guild_id,channel.id if channel else None,enabled)
        if config is None:text='Automatic recaps are off. Choose a channel with `/portle announcements channel:#games`.'
        else:
            text=f"Automatic recaps: **{'enabled' if config['enabled'] else 'disabled'}** in <#{config['channel_id']}>.\nDaily: **00:05** · Weekly + all-time: **Monday 00:10** · **{self.store.zone.key}**.\nDaily recaps name only the previous puzzle’s map. New configurations start with the next scheduled post."
            if config['last_error']:text+='\nLast delivery issue: '+config['last_error']
            if config['unconfirmed']:text+=f"\n**{config['unconfirmed']} unconfirmed delivery page(s)** are held to avoid duplicates. Check the channel before arranging a replacement."
        await interaction.edit_original_response(content=text,allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(description='Show daily records for players who joined in this server')
    async def leaderboard(self,interaction:discord.Interaction):
        await interaction.response.defer(ephemeral=True,thinking=True)
        rows=await asyncio.to_thread(self.store.leaderboard,interaction.guild_id)
        embeds=board_embeds('Portle · server players',rows,footer='Solves, then total clues on successful solves. Equal scores share a rank.')
        # This private command may exceed one response when a cutoff tie is large.
        await interaction.edit_original_response(embed=discord.Embed.from_dict(embeds[0]),allowed_mentions=discord.AllowedMentions.none())
        for embed in embeds[1:]:await interaction.followup.send(embed=discord.Embed.from_dict(embed),ephemeral=True,allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(description='List all map names accepted by the game')
    async def maps(self,interaction:discord.Interaction):
        await interaction.response.send_message('**Available arenas**\n'+', '.join(self.store.catalog.choices()),ephemeral=True)

    @app_commands.command(description='How to play Portle')
    async def help(self,interaction:discord.Interaction):
        clues=('Six guesses and six manually supplied screenshots. Revisit revealed clues for free.\n' if self.store.clues else 'Six guesses. Clues show 1, 2, 4, 8, 16, then all portals. Top/isometric views are free.\n')
        text=(
            '**PORTLE** — guess the arena from real portal placements.\n'
            +clues+'Choose a map from the Arena, Simulation or Royale dropdown to submit a guess. Wrong guesses and skips reveal the next clue. Invalid or repeated names are free.\n'
            +
            f'Daily resets at midnight **{self.store.zone.key}**; everyone gets the same map with private progress.\n'
            '`/portle play` daily · `/portle practice` admins only · `/portle guess` guess daily · `/portle maps` answer list · `/portle stats` records.\n'
            'Finished elsewhere? Open `/portle play` here and choose **Share results**, or run `/portle share`. An admin must enable `/portle results channel:#games`. Only your completed daily is shared, once per server.\n'
            'Admins in operator-allowlisted servers: `/portle reset player` resets that member\'s current daily score and guesses. Earlier days and practice are preserved; daily progress is shared across servers.\n'
            'Admins: `/portle announcements channel:#games` enables daily recaps at 00:05 and Monday weekly/all-time boards at 00:10 in the configured timezone. Use `enabled:false` to turn them off, or omit options to check delivery status. Closed daily recaps reveal yesterday\'s map.\n'
            'Finishing a daily automatically posts your score and squares in the configured results channel (or here if none is configured), without the map name or clues. Administrators can disable result posts with `/portle results enabled:false` after choosing a channel. Anyone can use **Play Portle** on a result to open their own private daily. Practice results stay private. Private board controls expire after 15 minutes; public Play buttons survive restarts. Resume the daily with `/portle play`. Server administrators can start fresh practice with `/portle practice`; practice does not affect daily records.')
        await interaction.response.send_message(embed=discord.Embed(title='Portle help',description=text,color=0x78E8D1),ephemeral=True,allowed_mentions=discord.AllowedMentions.none())

    async def on_error(self,interaction,error):
        original=getattr(error,'original',error)
        if isinstance(original,app_commands.MissingPermissions) and 'administrator' in original.missing_permissions:
            return await report_error(interaction,ADMIN_ONLY_MESSAGE)
        logging.getLogger(__name__).error('Command failed: %s',type(original).__name__)
        await report_error(interaction,str(original) if isinstance(original,GameError) else 'The command could not finish. Your progress is saved; try /portle play again.')


class DiscordSetupError(RuntimeError):
    """An actionable startup failure, safe to print without HTTP/token details."""


class PortleClient(discord.Client):
    def __init__(self,store,guild_id=None,*,reset_guild_ids=()):
        intents=discord.Intents.none();intents.guilds=True
        super().__init__(intents=intents,allowed_mentions=discord.AllowedMentions.none())
        self.tree=app_commands.CommandTree(self);self.tree.add_command(PortleCommands(store,reset_guild_ids));self.guild_id=guild_id;self.store=store
        self._announcement_lock=asyncio.Lock()

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
                message+='Server installation link: '+server_install_url(self.application_id)+'\n'
            message+='After correcting access, run ./run.sh again. See docs/DISCORD_SETUP.md.'
            raise DiscordSetupError(message) from None
        self.add_view(PlayPortleView(self.store))
        logging.getLogger(__name__).info('Registered %d command groups (%s)',len(commands),'single development server' if self.guild_id else 'global: all installed servers')

    async def on_ready(self):
        logging.getLogger(__name__).info('Portle connected and ready; private board verification enabled')
        print('Portle private board verification enabled',flush=True)
        # Bisect's panel recognizes this exact stdout marker after Discord is ready.
        print('successfully finished startup',flush=True)
        if not self.announcement_loop.is_running():self.announcement_loop.start()

    async def close(self):
        self.announcement_loop.cancel()
        task=self.announcement_loop.get_task()
        if task is not None:
            with suppress(asyncio.CancelledError):await task
        await super().close()

    @tasks.loop(seconds=60)
    async def announcement_loop(self):
        if not self.is_ready():return
        try:await self.send_due_announcements()
        except Exception as error:logging.getLogger(__name__).error('Scheduled recap cycle failed: %s',type(error).__name__)

    @announcement_loop.before_loop
    async def before_announcements(self):await self.wait_until_ready()

    async def send_due_announcements(self):
        manager=self.store.announcements
        async with self._announcement_lock:
            configs=await asyncio.to_thread(manager.enabled)
            for config in configs:
                try:await self._send_server_announcements(config)
                except Exception as error:
                    detail=f'Recap preparation failed: {type(error).__name__}'
                    await asyncio.to_thread(manager.note_error,config['guild_id'],detail)
                    logging.getLogger(__name__).warning(detail)

    async def _send_server_announcements(self,config):
        manager=self.store.announcements;now=self.store.clock().astimezone(self.store.zone)
        for kind,end,scheduled in due_periods(now):
            if scheduled>=datetime.fromisoformat(config['enabled_at']):await asyncio.to_thread(manager.prepare,config,kind,end)
        for batch in await asyncio.to_thread(manager.queued,config):
            pages=await asyncio.to_thread(manager.pages,batch)
            # Stop at an unconfirmed page rather than skipping it or resending it.
            first=next((page for page in pages if page['status']!='sent'),None)
            if first is None or first['status']!='ready' or first['retry_after']>self.store.clock().timestamp():continue
            try:
                channel=self.get_channel(int(batch['channel_id'])) or await self.fetch_channel(int(batch['channel_id']))
                if getattr(getattr(channel,'guild',None),'id',None)!=int(config['guild_id']):raise GameError('Announcement channel is not in this server.')
            except (discord.HTTPException,OSError,GameError) as error:
                reason=str(error) if isinstance(error,GameError) else f'{type(error).__name__} (HTTP {getattr(error,"status","n/a")}, Discord code {getattr(error,"code","n/a")})'
                detail='Channel access failed: '+reason
                await asyncio.to_thread(manager.note_error,config['guild_id'],detail)
                if config['last_error']!=detail:logging.getLogger(__name__).warning('Recap channel access failed for server %s: %s',config['guild_id'],reason)
                continue
            payload=json.loads(batch['payload'])
            for page in pages:
                if page['status']=='sent':continue
                if page['status']!='ready' or not await asyncio.to_thread(manager.claim,batch,page['page']):break
                try:
                    message=await channel.send(embeds=[discord.Embed.from_dict(embed) for embed in payload[page['page']]],
                        view=PlayPortleView(self.store),allowed_mentions=discord.AllowedMentions.none(),nonce=manager.nonce(batch,page['page']))
                except (discord.HTTPException,OSError) as error:
                    detail=f'{type(error).__name__} (HTTP {getattr(error,"status","n/a")}, Discord code {getattr(error,"code","n/a")})'
                    retry=isinstance(error,discord.HTTPException) and error.status in (403,404,429)
                    await asyncio.to_thread(manager.finish,batch,page['page'],error=detail,retry=retry)
                    logging.getLogger(__name__).warning('Scheduled recap post failed for server %s: %s%s',config['guild_id'],detail,'; will retry' if retry else '; delivery held to avoid duplicates')
                    break
                except Exception as error:
                    await asyncio.to_thread(manager.finish,batch,page['page'],error=type(error).__name__)
                    logging.getLogger(__name__).warning('Scheduled recap post unconfirmed: %s',type(error).__name__)
                    break
                await asyncio.to_thread(manager.finish,batch,page['page'],message_id=message.id)
