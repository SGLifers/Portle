"""Discord transport. Importing this module never connects or sends messages."""
import asyncio
from io import BytesIO
import logging
import discord
from discord import app_commands

from .game import GameError,public_view,share_text
from .render import png


async def report_error(interaction,message):
    if interaction.response.is_done():await interaction.followup.send(message,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
    else:await interaction.response.send_message(message,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())


def round_embed(state,projection):
    data=public_view(state);active=data['status']=='playing'
    title='Which arena is this?' if active else ('Arena identified!' if data['status']=='won' else 'The arena was '+data['answer'])
    mode='Daily · '+data['day'] if data['mode']=='daily' else 'Practice'
    description=f"{mode}\nClue **{data['turn']}/6** · **{data['portalCount']}** portals revealed."
    if active:description+='\nGuess a map or reveal the next clue. Each miss/skip uses one guess.'
    else:description+='\n**'+data['answer']+'**\n```\n'+data['share']+'\n```'
    embed=discord.Embed(title=title,description=description,color=0x78E8D1 if data['status']!='lost' else 0xE8B777)
    if data['attempts']:
        history='\n'.join(f"{i+1}. "+('🟩 ' if a['correct'] else '⬜ ' if a['kind']=='skip' else '🟥 ')+(a['name'] or 'Skipped') for i,a in enumerate(data['attempts']))
        embed.add_field(name='Your guesses',value=history,inline=False)
    embed.set_image(url='attachment://portle-clue.png')
    embed.set_footer(text=f"{'Top' if projection=='top' else 'Isometric'} view · real asset placements · /portle maps for valid answers")
    return embed


async def show_round(interaction,store,state,projection='iso',replace=False):
    if not interaction.response.is_done():await interaction.response.defer(ephemeral=True,thinking=not replace)
    image=await asyncio.to_thread(png,state,projection)
    await interaction.edit_original_response(content=None,embed=round_embed(state,projection),
        attachments=[discord.File(BytesIO(image),filename='portle-clue.png')],
        view=RoundView(store,state,projection),allowed_mentions=discord.AllowedMentions.none())


class GuessModal(discord.ui.Modal,title='Name the arena'):
    answer=discord.ui.TextInput(label='Map name',placeholder='Type a map from /portle maps',min_length=1,max_length=80)

    def __init__(self,board):
        super().__init__(timeout=300);self.board=board

    async def on_submit(self,interaction):
        if str(interaction.user.id)!=self.board.owner:return await report_error(interaction,'Open your own round with /portle play.')
        await interaction.response.defer(ephemeral=True,thinking=False)
        try:
            state=await asyncio.to_thread(self.board.store.act,self.board.round_id,interaction.user.id,self.board.version,guess=str(self.answer.value),event_id=str(interaction.id))
            await show_round(interaction,self.board.store,state,self.board.projection,replace=True)
        except GameError as exc:await report_error(interaction,str(exc))

    async def on_error(self,interaction,error):
        logging.getLogger(__name__).error('Modal failed: %s',type(error).__name__)
        await report_error(interaction,'Could not complete that action. Your round is saved; reopen it with /portle play.')


class RoundView(discord.ui.View):
    def __init__(self,store,state,projection='iso'):
        super().__init__(timeout=900)
        self.store=store;self.round_id=state['id'];self.owner=state['user_id'];self.version=state['version'];self.projection=projection
        finished=state['status']!='playing'
        self.guess_button.disabled=finished;self.skip_button.disabled=finished;self.share_button.disabled=not finished
        self.projection_button.label='Top view' if projection=='iso' else 'Isometric view'

    async def interaction_check(self,interaction):
        if str(interaction.user.id)!=self.owner:
            await report_error(interaction,'This is another player\'s round. Use /portle play for your own clues.');return False
        return True

    @discord.ui.button(label='Guess map',style=discord.ButtonStyle.success)
    async def guess_button(self,interaction,button):
        try:
            state=await asyncio.to_thread(self.store.get,self.round_id,interaction.user.id)
            if state['version']!=self.version or state['status']!='playing':raise GameError('This board is out of date. Use /portle play to refresh your daily round.')
            await interaction.response.send_modal(GuessModal(self))
        except GameError as exc:await report_error(interaction,str(exc))

    @discord.ui.button(label='Reveal more / skip',style=discord.ButtonStyle.secondary)
    async def skip_button(self,interaction,button):
        await interaction.response.defer(ephemeral=True,thinking=False)
        try:
            state=await asyncio.to_thread(self.store.act,self.round_id,interaction.user.id,self.version,skip=True,event_id=str(interaction.id))
            await show_round(interaction,self.store,state,self.projection,replace=True)
        except GameError as exc:await report_error(interaction,str(exc))

    @discord.ui.button(label='Top view',style=discord.ButtonStyle.secondary)
    async def projection_button(self,interaction,button):
        await interaction.response.defer(ephemeral=True,thinking=False)
        state=await asyncio.to_thread(self.store.get,self.round_id,interaction.user.id)
        await show_round(interaction,self.store,state,'top' if self.projection=='iso' else 'iso',replace=True)

    @discord.ui.button(label='Share result',style=discord.ButtonStyle.primary)
    async def share_button(self,interaction,button):
        state=await asyncio.to_thread(self.store.get,self.round_id,interaction.user.id)
        try:result=share_text(state)
        except GameError as exc:return await report_error(interaction,str(exc))
        await interaction.response.send_message(result,allowed_mentions=discord.AllowedMentions.none())

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

    @app_commands.command(description='Start an unlimited practice round, separate from daily scores')
    async def practice(self,interaction:discord.Interaction):
        await interaction.response.defer(ephemeral=True,thinking=True)
        state=await asyncio.to_thread(self.store.start,interaction.user.id,'practice',interaction.guild_id)
        await show_round(interaction,self.store,state)

    @app_commands.command(description='Guess today\'s map; autocomplete lists valid answers')
    @app_commands.describe(map_name='Arena name')
    async def guess(self,interaction:discord.Interaction,map_name:str):
        await interaction.response.defer(ephemeral=True,thinking=True)
        try:
            state=await asyncio.to_thread(self.store.start,interaction.user.id,guild_id=interaction.guild_id)
            state=await asyncio.to_thread(self.store.act,state['id'],interaction.user.id,state['version'],guess=map_name,event_id=str(interaction.id))
            await show_round(interaction,self.store,state)
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
        try:result=share_text(state)
        except GameError as exc:return await report_error(interaction,str(exc))
        await interaction.response.send_message(result,allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(description='List all map names accepted by the game')
    async def maps(self,interaction:discord.Interaction):
        await interaction.response.send_message('**Available arenas**\n'+', '.join(self.store.catalog.choices()),ephemeral=True)

    @app_commands.command(description='How to play Portle')
    async def help(self,interaction:discord.Interaction):
        await interaction.response.send_message(
            '**PORTLE** — guess the arena from real portal placements.\n'
            'Six guesses. Clues show 1, 2, 4, 8, 16, then all portals. Wrong guesses and skips advance the clue. Invalid or repeated names are free.\n'
            'Top/isometric views show the same portals and do not use a guess.\n'
            f'Daily resets at midnight **{self.store.zone.key}**; everyone gets the same map with private progress.\n'
            '`/portle play` daily · `/portle practice` unlimited · `/portle guess` guess daily · `/portle maps` answer list · `/portle stats` records.\n'
            'Only **Share result** or `/portle share` posts a score publicly; the map name is omitted. Buttons expire after 15 minutes. Resume the daily with `/portle play`, or start fresh practice with `/portle practice`. Practice does not affect daily records.',ephemeral=True)

    async def on_error(self,interaction,error):
        original=getattr(error,'original',error)
        logging.getLogger(__name__).error('Command failed: %s',type(original).__name__)
        await report_error(interaction,str(original) if isinstance(original,GameError) else 'The command could not finish. Your progress is saved; try /portle play again.')


class PortleClient(discord.Client):
    def __init__(self,store,guild_id=None):
        intents=discord.Intents.none();intents.guilds=True
        super().__init__(intents=intents,allowed_mentions=discord.AllowedMentions.none())
        self.tree=app_commands.CommandTree(self);self.tree.add_command(PortleCommands(store));self.guild_id=guild_id

    async def setup_hook(self):
        if self.guild_id:
            guild=discord.Object(id=self.guild_id);self.tree.copy_global_to(guild=guild);commands=await self.tree.sync(guild=guild)
        else:commands=await self.tree.sync()
        logging.getLogger(__name__).info('Registered %d command groups',len(commands))

    async def on_ready(self):logging.getLogger(__name__).info('Portle connected and ready')
