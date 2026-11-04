import argparse
import json
import os
from pathlib import Path
import sys
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[1]


def main():
    load_dotenv(ROOT/'.env',override=False)
    parser=argparse.ArgumentParser(description='Portle · guess the arena from portal placements')
    sub=parser.add_subparsers(dest='command',required=True)
    importer=sub.add_parser('import-assets');importer.add_argument('--source',default=str(ROOT.parent/'PortalAtlas/data/scenes'))
    sub.add_parser('bot');sub.add_parser('doctor')
    preview=sub.add_parser('preview');preview.add_argument('--port',type=int,default=8742)
    sample=sub.add_parser('render-sample');sample.add_argument('--stage',type=int,choices=range(1,7),default=4);sample.add_argument('--view',choices=['iso','top'],default='iso')
    args=parser.parse_args()
    from .catalog import Catalog,import_catalog
    catalog_path=Path(os.getenv('PORTLE_CATALOG',str(ROOT/'data/catalog.json')))
    if args.command=='import-assets':
        print(json.dumps(import_catalog(args.source,catalog_path)));return 0
    source=os.getenv('PORTLE_CLUE_SOURCE','manual')
    if source not in ('manual','generated'):parser.exit(2,'PORTLE_CLUE_SOURCE must be manual or generated.\n')
    from .clues import ClueLibrary
    clues=ClueLibrary(Path(os.getenv('PORTLE_CLUES',str(ROOT/'data/clues')))) if source=='manual' else None
    if source=='manual':catalog=Catalog.names(os.getenv('PORTLE_CATALOG'))
    else:
        if not catalog_path.exists():parser.exit(2,'Import the real portal data first: .venv/bin/python -m portle import-assets\n')
        catalog=Catalog.load(catalog_path)
    from .store import GameStore
    timezone_name=os.getenv('PORTLE_TIMEZONE','UTC')
    if args.command=='preview':
        from .preview import serve
        serve(GameStore(ROOT/'.local/preview.sqlite3',catalog,timezone_name,clues=clues),args.port);return 0
    database=Path(os.getenv('PORTLE_DATABASE',str(ROOT/'data/portle.sqlite3')))
    store=GameStore(database,catalog,timezone_name,clues=clues)
    if args.command=='render-sample':
        from .game import apply_action,GameError
        try:state=store.start('local-art-preview','practice')
        except GameError as exc:parser.exit(2,str(exc)+'\n')
        for _ in range(args.stage-1):apply_action(state,skip=True)
        path=ROOT/'.local/sample.png';path.parent.mkdir(exist_ok=True);path.write_bytes(store.image(state,args.view));print(path);return 0
    from .bot import PortleClient
    if args.command=='doctor':
        client=PortleClient(store)
        print(json.dumps({'maps':len(catalog.maps),'portals':sum(len(m.get('portals',[])) for m in catalog.maps),'clueSource':source,'publishedClueSets':len(clues.published()) if clues else None,'timezone':timezone_name,
            'discordSdk':__import__('discord').__version__,'commands':client.tree.get_commands()[0].to_dict(client.tree),
            'tokenConfigured':bool(os.getenv('DISCORD_BOT_TOKEN')),'networkConnectionAttempted':False},indent=2))
        return 0
    token=os.getenv('DISCORD_BOT_TOKEN','').strip()
    if not token or token.startswith('replace_'):parser.exit(2,'DISCORD_BOT_TOKEN is not configured. Copy .env.example to .env and add your bot token locally; do not paste it into chat. See docs/DISCORD_SETUP.md.\n')
    guild=os.getenv('DISCORD_GUILD_ID','').strip()
    if guild and (not guild.isdigit() or int(guild)<=0):parser.exit(2,'DISCORD_GUILD_ID must be a positive server ID.\n')
    client=PortleClient(store,int(guild) if guild else None)
    import discord
    try:client.run(token)
    except discord.LoginFailure:parser.exit(2,'Discord rejected the configured bot token. Update .env locally.\n')
    return 0


if __name__=='__main__':raise SystemExit(main())
