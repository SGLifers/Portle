"""Closed-period standings, message snapshots and durable scheduled delivery records."""
from datetime import date,datetime,time,timedelta,timezone
import hashlib
import json
import re

from .game import GameError


def due_periods(now):
    """Latest due daily and Monday recap; local dates survive DST changes."""
    daily=datetime.combine(now.date(),time(0,5),now.tzinfo)
    if daily>now:daily=datetime.combine(now.date()-timedelta(days=1),time(0,5),now.tzinfo)
    monday=now.date()-timedelta(days=now.weekday())
    weekly=datetime.combine(monday,time(0,10),now.tzinfo)
    if weekly>now:weekly=datetime.combine(monday-timedelta(days=7),time(0,10),now.tzinfo)
    return [('daily',daily.date()-timedelta(days=1),daily),('weekly',weekly.date()-timedelta(days=1),weekly)]


def ranked(rows,daily=False,limit=10):
    def score(row):return (row['clues'],) if daily else (-row['wins'],row['clues'])
    rows=sorted(rows,key=lambda row:(score(row),row['user_id']))
    output=[];previous=None;rank=0
    for position,row in enumerate(rows,1):
        current=score(row)
        if current!=previous:rank=position
        previous=current
        if rank>limit:break
        output.append(dict(row,rank=rank))
    return output


def safe_text(text):
    return re.sub(r'([\\`*_~|>])',r'\\\1',str(text).replace('\n',' ')).replace('@','@\u200b')[:250]


def text_length(text):return len(text.encode('utf-16-le'))//2


def board_embeds(title,rows,prefix='',suffix='',daily=False,footer=''):
    lines=[];rounded_totals={}
    if not daily:
        for row in rows:
            rounded_totals.setdefault((row['wins'],f"{row['clues']/row['wins']:.2f}"),set()).add(row['clues'])
    for row in rows:
        medal={1:'🥇',2:'🥈',3:'🥉'}.get(row['rank'],f"**{row['rank']}.**")
        score=f"**{row['clues']}/6**" if daily else f"**{row['wins']} {'solve' if row['wins']==1 else 'solves'}** · {row['clues']/row['wins']:.2f} average clues"
        if not daily and len(rounded_totals[row['wins'],f"{row['clues']/row['wins']:.2f}"])>1:score+=f" · {row['clues']} clues total"
        lines.append(f"{medal} <@{row['user_id']}> — {score}")
    if not lines:lines=['No solves in this period.']
    chunks=[];current=prefix
    for line in lines:
        if text_length(current+line+suffix)+4>3500:
            chunks.append(current.rstrip());current=''
        current+=line+'\n'
    chunks.append(current.rstrip()+ ('\n\n'+suffix if suffix else ''))
    return [{'title':title+(' · continued' if i else ''),'description':chunk,'color':0x78E8D1,
             'footer':{'text':footer}} for i,chunk in enumerate(chunks)]


def message_pages(snapshot):
    end=snapshot['end'];zone=snapshot['timezone']
    if snapshot['kind']=='daily':
        board=snapshot['daily']
        embeds=board_embeds(f'🏆 Portle Daily Results · {end}',board['rows'],
            prefix=f"**Map: {safe_text(snapshot['mapName'])}**\n\n",
            suffix=f"**{board['wins']} of {board['players']} {'player' if board['players']==1 else 'players'} solved it.**",daily=True,footer=zone)
    else:
        board=snapshot['weekly']
        embeds=board_embeds(f"📊 Portle Weekly Leaderboard · {snapshot['start']} – {end}",board['rows'],
            suffix=f"**{board['players']} {'player' if board['players']==1 else 'players'} · {board['wins']} {'puzzle' if board['wins']==1 else 'puzzles'} solved this week.**",footer=zone)
        embeds+=board_embeds('🏆 Portle All-Time Leaderboard',snapshot['allTime']['rows'],footer=f'Through {end} · {zone}')
    pages=[];current=[];characters=0
    for embed in embeds:
        length=sum(text_length(embed[field]) for field in ('title','description'))+text_length(embed['footer']['text'])
        if current and (characters+length>5700 or len(current)>=10):pages.append(current);current=[];characters=0
        current.append(embed);characters+=length
    if current:pages.append(current)
    return pages


class AnnouncementStore:
    def __init__(self,store):
        self.store=store
        with store.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS announcement_config(guild_id TEXT PRIMARY KEY,channel_id TEXT NOT NULL,enabled INTEGER NOT NULL,enabled_at TEXT NOT NULL,last_error TEXT);
                CREATE TABLE IF NOT EXISTS announcement_batches(guild_id TEXT NOT NULL,namespace TEXT NOT NULL,kind TEXT NOT NULL,period_end TEXT NOT NULL,channel_id TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL,PRIMARY KEY(guild_id,namespace,kind,period_end));
                CREATE TABLE IF NOT EXISTS announcement_pages(guild_id TEXT NOT NULL,namespace TEXT NOT NULL,kind TEXT NOT NULL,period_end TEXT NOT NULL,page INTEGER NOT NULL,status TEXT NOT NULL,retry_after REAL NOT NULL DEFAULT 0,message_id TEXT,error TEXT,PRIMARY KEY(guild_id,namespace,kind,period_end,page));
                CREATE INDEX IF NOT EXISTS recap_round_lookup ON rounds(mode,puzzle_id,user_id);
            ''')

    @property
    def namespace(self):return 'manual' if self.store.clues else 'generated'

    @property
    def prefix(self):return ('manual:' if self.store.clues else '')+'daily:'

    def configure(self,guild_id,channel_id=None,enabled=None):
        guild_id=str(guild_id)
        if not guild_id.isdigit() or int(guild_id)<=0:raise GameError('Choose a server for announcements.')
        if channel_id is not None and (not str(channel_id).isdigit() or int(channel_id)<=0):raise GameError('Choose a valid server text channel.')
        with self.store.transaction() as db:
            prior=db.execute('SELECT * FROM announcement_config WHERE guild_id=?',(guild_id,)).fetchone()
            if channel_id is None and enabled is None:return self._status(db,guild_id)
            channel=str(channel_id) if channel_id is not None else prior['channel_id'] if prior else None
            if channel is None:raise GameError('Choose an announcement channel first: /portle announcements channel:#games')
            active=bool(enabled) if enabled is not None else True if channel_id is not None else bool(prior['enabled'])
            fresh=not prior or (active and not prior['enabled']) or prior['channel_id']!=channel
            since=self.store.clock().astimezone(timezone.utc).isoformat() if fresh else prior['enabled_at']
            db.execute('INSERT INTO announcement_config VALUES (?,?,?,?,NULL) ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id,enabled=excluded.enabled,enabled_at=excluded.enabled_at,last_error=NULL',
                (guild_id,channel,int(active),since))
            return self._status(db,guild_id)

    def _status(self,db,guild_id):
        row=db.execute('SELECT * FROM announcement_config WHERE guild_id=?',(str(guild_id),)).fetchone()
        if not row:return None
        result=dict(row)
        result['unconfirmed']=db.execute("SELECT count(*) FROM announcement_pages p JOIN announcement_batches b USING(guild_id,namespace,kind,period_end) WHERE p.guild_id=? AND p.namespace=? AND b.channel_id=? AND p.status IN ('sending','uncertain')",(str(guild_id),self.namespace,result['channel_id'])).fetchone()[0]
        return result

    def enabled(self):
        with self.store.connection() as db:return [dict(row) for row in db.execute('SELECT * FROM announcement_config WHERE enabled=1 ORDER BY guild_id')]

    def _standings(self,db,guild_id,start,end,daily=False):
        lower=self.prefix+(start.isoformat() if start else '')
        upper=self.prefix+end.isoformat()
        rows=db.execute('SELECT r.state FROM rounds r JOIN participants p ON p.user_id=r.user_id AND p.guild_id=? WHERE r.mode=? AND r.puzzle_id LIKE ? AND r.puzzle_id>=? AND r.puzzle_id<=?',
            (str(guild_id),'daily',self.prefix+'%',lower,upper))
        scores={};players=set();wins=0
        for row in rows:
            state=json.loads(row['state']);user=state['user_id']
            if state['attempts'] or state['status']!='playing':players.add(user)
            if state['status']!='won':continue
            wins+=1;score=scores.setdefault(user,{'user_id':user,'wins':0,'clues':0})
            score['wins']+=1;score['clues']+=len(state['attempts'])
        return {'players':len(players),'wins':wins,'rows':ranked(scores.values(),daily)}

    def standings(self,guild_id,end=None):
        with self.store.connection() as db:return self._standings(db,guild_id,None,end or self.store.today())

    def prepare(self,config,kind,end):
        if kind not in ('daily','weekly') or end>=self.store.today():raise GameError('Recaps may only cover closed daily puzzles.')
        if kind=='weekly' and end.weekday()!=6:raise GameError('Weekly recaps end on Sunday.')
        key=(config['guild_id'],self.namespace,kind,end.isoformat())
        with self.store.transaction() as db:
            if db.execute('SELECT 1 FROM announcement_batches WHERE guild_id=? AND namespace=? AND kind=? AND period_end=?',key).fetchone():return
            current=db.execute('SELECT * FROM announcement_config WHERE guild_id=? AND enabled=1',(config['guild_id'],)).fetchone()
            if not current or current['channel_id']!=config['channel_id'] or current['enabled_at']!=config['enabled_at']:return
            snapshot={'kind':kind,'end':end.isoformat(),'timezone':self.store.zone.key}
            if kind=='daily':
                board=self._standings(db,config['guild_id'],end,end,True)
                row=db.execute('SELECT snapshot FROM puzzles WHERE id=?',(self.prefix+end.isoformat(),)).fetchone()
                snapshot.update(daily=board,mapName=json.loads(row['snapshot'])['map']['name'] if row else 'Unavailable')
                active=board['players']>0
            else:
                start=end-timedelta(days=6)
                weekly=self._standings(db,config['guild_id'],start,end)
                all_time=self._standings(db,config['guild_id'],None,end)
                snapshot.update(start=start.isoformat(),weekly=weekly,allTime=all_time)
                active=all_time['players']>0
            pages=message_pages(snapshot) if active else []
            db.execute('INSERT INTO announcement_batches VALUES (?,?,?,?,?,?,?)',(*key,config['channel_id'],json.dumps(pages),'queued' if pages else 'skipped'))
            db.executemany('INSERT INTO announcement_pages VALUES (?,?,?,?,?,?,0,NULL,NULL)',[(*key,i,'ready') for i in range(len(pages))])

    def queued(self,config):
        now=self.store.clock().astimezone(self.store.zone)
        due={kind:(end.isoformat(),scheduled) for kind,end,scheduled in due_periods(now)}
        with self.store.connection() as db:
            rows=db.execute("SELECT * FROM announcement_batches WHERE guild_id=? AND namespace=? AND channel_id=? AND status='queued' ORDER BY period_end,kind",(config['guild_id'],self.namespace,config['channel_id']))
            return [dict(row) for row in rows if row['period_end']==due[row['kind']][0] and due[row['kind']][1]>=datetime.fromisoformat(config['enabled_at'])]

    @staticmethod
    def key(batch):return tuple(batch[field] for field in ('guild_id','namespace','kind','period_end'))

    def pages(self,batch):
        with self.store.connection() as db:return [dict(row) for row in db.execute('SELECT * FROM announcement_pages WHERE guild_id=? AND namespace=? AND kind=? AND period_end=? ORDER BY page',self.key(batch))]

    def claim(self,batch,page):
        with self.store.transaction() as db:
            config=db.execute('SELECT * FROM announcement_config WHERE guild_id=? AND enabled=1',(batch['guild_id'],)).fetchone()
            if not config or config['channel_id']!=batch['channel_id']:return False
            scheduled=datetime.combine(date.fromisoformat(batch['period_end'])+timedelta(days=1),time(0,5 if batch['kind']=='daily' else 10),self.store.zone)
            if not datetime.fromisoformat(config['enabled_at'])<=scheduled<=self.store.clock():return False
            latest={kind:end.isoformat() for kind,end,_ in due_periods(self.store.clock().astimezone(self.store.zone))}
            if batch['period_end']!=latest[batch['kind']]:return False
            return db.execute("UPDATE announcement_pages SET status='sending' WHERE guild_id=? AND namespace=? AND kind=? AND period_end=? AND page=? AND status='ready' AND retry_after<=?",(*self.key(batch),page,self.store.clock().timestamp())).rowcount==1

    def note_error(self,guild_id,error):
        with self.store.transaction() as db:db.execute('UPDATE announcement_config SET last_error=? WHERE guild_id=?',(error,str(guild_id)))

    def finish(self,batch,page,*,message_id=None,error=None,retry=False):
        status='sent' if message_id is not None else 'ready' if retry else 'uncertain'
        with self.store.transaction() as db:
            changed=db.execute("UPDATE announcement_pages SET status=?,message_id=?,error=?,retry_after=? WHERE guild_id=? AND namespace=? AND kind=? AND period_end=? AND page=? AND status='sending'",
                (status,str(message_id) if message_id is not None else None,error,self.store.clock().timestamp()+300 if retry else 0,*self.key(batch),page))
            if not changed.rowcount:return
            db.execute('UPDATE announcement_config SET last_error=? WHERE guild_id=?',(error,batch['guild_id']))
            if not db.execute("SELECT 1 FROM announcement_pages WHERE guild_id=? AND namespace=? AND kind=? AND period_end=? AND status!='sent'",self.key(batch)).fetchone():
                db.execute("UPDATE announcement_batches SET status='sent' WHERE guild_id=? AND namespace=? AND kind=? AND period_end=?",self.key(batch))

    def nonce(self,batch,page):
        value=':'.join((*self.key(batch),str(page)))
        return hashlib.sha256(value.encode()).hexdigest()[:24]
