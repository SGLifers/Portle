from contextlib import contextmanager
from datetime import datetime,date,timedelta,timezone
import hashlib
import json
from pathlib import Path
import random
import secrets
import sqlite3
import uuid
from zoneinfo import ZoneInfo

from .game import GameError,new_state,apply_action,portal_order


class GameStore:
    def __init__(self,path,catalog,timezone_name='UTC',clock=None,clues=None):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.catalog=catalog;self.zone=ZoneInfo(timezone_name);self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.clues=clues
        with self.connection() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS puzzles(id TEXT PRIMARY KEY,snapshot TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS rounds(id TEXT PRIMARY KEY,puzzle_id TEXT NOT NULL,user_id TEXT NOT NULL,mode TEXT NOT NULL,state TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(puzzle_id,user_id));
                CREATE TABLE IF NOT EXISTS events(user_id TEXT NOT NULL,event_id TEXT NOT NULL,round_id TEXT NOT NULL,PRIMARY KEY(user_id,event_id));
                CREATE TABLE IF NOT EXISTS participants(guild_id TEXT NOT NULL,user_id TEXT NOT NULL,PRIMARY KEY(guild_id,user_id));
                CREATE TABLE IF NOT EXISTS result_posts(round_id TEXT PRIMARY KEY,status TEXT NOT NULL,message_id TEXT);
                CREATE TABLE IF NOT EXISTS daily_resets(event_id TEXT PRIMARY KEY,actor_id TEXT NOT NULL,user_id TEXT NOT NULL,guild_id TEXT NOT NULL,day TEXT NOT NULL,old_state TEXT,new_round_id TEXT,created_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS round_owner ON rounds(user_id,mode);
            ''')
            db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)',('seed',secrets.token_hex(32)))
        self.path.chmod(0o600)

    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=10,isolation_level=None);db.row_factory=sqlite3.Row
        try:yield db
        finally:db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:yield db;db.commit()
            except Exception:db.rollback();raise

    def today(self):return self.clock().astimezone(self.zone).date()

    def _puzzle(self,db,mode):
        today=self.today().isoformat();pid=('manual:' if self.clues else '')+('daily:'+today if mode=='daily' else 'practice:'+uuid.uuid4().hex)
        row=db.execute('SELECT snapshot FROM puzzles WHERE id=?',(pid,)).fetchone()
        if row:return json.loads(row['snapshot'])
        seed=db.execute('SELECT value FROM settings WHERE key=?',('seed',)).fetchone()['value']
        maps=sorted(self.catalog.maps,key=lambda m:m['id'])
        published=self.clues.published() if self.clues else {}
        if self.clues:
            maps=[m for m in maps if m['id'] in published]
            if not maps:raise GameError('No manual clues are published yet. Add six screenshots in the local clue editor.')
        rng=random.Random(hashlib.sha256((seed+self.catalog.revision).encode()).hexdigest());rng.shuffle(maps)
        selected=maps[(self.today()-date(2026,1,1)).days%len(maps)] if mode=='daily' else secrets.choice(maps)
        order_seed=hashlib.sha256((seed+pid+self.catalog.revision).encode()).hexdigest()
        puzzle={'id':pid,'day':today,'map':selected,'catalogRevision':self.catalog.revision}
        if self.clues:puzzle.update(clueSource='manual',clueImages=list(published[selected['id']]['images']),cluePack=published[selected['id']]['id'])
        else:puzzle['order']=portal_order(selected['portals'],order_seed)
        db.execute('INSERT INTO puzzles VALUES (?,?)',(pid,json.dumps(puzzle)))
        return puzzle

    def start(self,user_id,mode='daily',guild_id=None):
        if mode not in ('daily','practice'):raise GameError('Unknown game mode')
        user_id=str(user_id)
        with self.transaction() as db:
            if guild_id is not None:db.execute('INSERT OR IGNORE INTO participants VALUES (?,?)',(str(guild_id),user_id))
            puzzle=self._puzzle(db,mode)
            row=db.execute('SELECT state FROM rounds WHERE puzzle_id=? AND user_id=?',(puzzle['id'],user_id)).fetchone()
            if row:return json.loads(row['state'])
            state=new_state(uuid.uuid4().hex,user_id,puzzle,mode)
            db.execute('INSERT INTO rounds VALUES (?,?,?,?,?,?)',(state['id'],puzzle['id'],user_id,mode,json.dumps(state),self.clock().isoformat()))
            return state

    @staticmethod
    def _owned(db,round_id,user_id):
        row=db.execute('SELECT state FROM rounds WHERE id=? AND user_id=?',(round_id,str(user_id))).fetchone()
        if not row:raise GameError('This round belongs to another player or is unavailable. Use /portle play to open your own puzzle.')
        return json.loads(row['state'])

    def get(self,round_id,user_id):
        with self.connection() as db:return self._owned(db,round_id,user_id)

    def reset_daily(self,user_id,*,actor_id,guild_id,event_id):
        """Reset only today's progress; archive it and invalidate the old board."""
        if guild_id is None:raise GameError('Reset a daily score from a server.')
        if not event_id:raise GameError('A reset interaction ID is required.')
        user_id=str(user_id);actor_id=str(actor_id);guild_id=str(guild_id);event_id=str(event_id)
        with self.transaction() as db:
            old=db.execute('SELECT * FROM daily_resets WHERE event_id=?',(event_id,)).fetchone()
            if old:
                if (old['actor_id'],old['user_id'],old['guild_id'])!=(actor_id,user_id,guild_id):raise GameError('This reset interaction was already used for another request.')
                return {'changed':old['old_state'] is not None,'day':old['day']}
            day=self.today().isoformat();pid=('manual:' if self.clues else '')+'daily:'+day
            row=db.execute('SELECT id,state FROM rounds WHERE puzzle_id=? AND user_id=? AND mode=?',(pid,user_id,'daily')).fetchone()
            prior=None;new_id=None
            if row:
                state=json.loads(row['state'])
                if state['attempts'] or state['status']!='playing':
                    prior=row['state'];new_id=uuid.uuid4().hex
                    fresh=new_state(new_id,user_id,state['puzzle'],'daily')
                    db.execute('UPDATE rounds SET id=?,state=?,created_at=? WHERE id=?',(new_id,json.dumps(fresh),self.clock().isoformat(),row['id']))
            # Retain old event IDs and post reservations as replay tombstones.
            db.execute('INSERT INTO daily_resets VALUES (?,?,?,?,?,?,?,?)',
                (event_id,actor_id,user_id,guild_id,day,prior,new_id,self.clock().isoformat()))
            return {'changed':prior is not None,'day':day}

    def claim_result_post(self,round_id,user_id):
        """Reserve one automatic post across replays, processes and restarts."""
        with self.transaction() as db:
            state=self._owned(db,round_id,user_id)
            if state['mode']!='daily' or state['status']=='playing':return False
            return db.execute('INSERT OR IGNORE INTO result_posts VALUES (?,?,NULL)',(round_id,'pending')).rowcount==1

    def record_result_post(self,round_id,message_id=None):
        # Keep failed/uncertain attempts reserved to avoid duplicate public posts.
        with self.transaction() as db:
            db.execute('UPDATE result_posts SET status=?,message_id=? WHERE round_id=? AND status=?',
                ('sent' if message_id is not None else 'failed',str(message_id) if message_id is not None else None,round_id,'pending'))

    def image(self,state,projection='iso',clue=None):
        if state['puzzle'].get('clueSource')=='manual':
            from .game import revealed_stage
            unlocked=revealed_stage(state)
            if clue is None:clue=unlocked
            if not isinstance(clue,int) or isinstance(clue,bool) or not 1<=clue<=unlocked:raise GameError('That screenshot is not revealed yet.')
            if not self.clues:raise GameError('Open this round using its manual clue library.')
            return self.clues.image(state['puzzle']['clueImages'][clue-1])
        from .render import png
        return png(state,projection)

    def act(self,round_id,user_id,version,*,guess=None,skip=False,event_id=None):
        user_id=str(user_id)
        with self.transaction() as db:
            state=self._owned(db,round_id,user_id)
            if event_id:
                old=db.execute('SELECT round_id FROM events WHERE user_id=? AND event_id=?',(user_id,str(event_id))).fetchone()
                if old:
                    if old['round_id']!=round_id:raise GameError('This interaction was already used for another round.')
                    return state
            if state['mode']=='daily' and state['puzzle']['day']!=self.today().isoformat():raise GameError('A new daily puzzle is available. Use /portle play; yesterday\'s round is closed.')
            if not isinstance(version,int) or isinstance(version,bool) or state['version']!=version:raise GameError('That clue is out of date. Reopen the round before guessing again.')
            resolved=None
            if not skip:
                # A frozen daily snapshot remains answerable after a catalog update.
                from .catalog import normalize
                answer=state['puzzle']['map']
                if normalize(guess or '') in {normalize(n) for n in [answer['name'],*answer.get('aliases',[])]}:resolved=answer
                else:
                    try:resolved=self.catalog.resolve(guess or '')
                    except ValueError as exc:raise GameError(str(exc)) from exc
            apply_action(state,resolved,skip)
            db.execute('UPDATE rounds SET state=? WHERE id=?',(json.dumps(state),round_id))
            if event_id:db.execute('INSERT INTO events VALUES (?,?,?)',(user_id,str(event_id),round_id))
            return state

    def stats(self,user_id):
        with self.connection() as db:states=[json.loads(r['state']) for r in db.execute('SELECT state FROM rounds WHERE user_id=? AND mode=? AND puzzle_id LIKE ?',(str(user_id),'daily',('manual:' if self.clues else '')+'daily:%'))]
        finished=sorted((s for s in states if s['status']!='playing'),key=lambda s:s['puzzle']['day'])
        wins=[s for s in finished if s['status']=='won'];distribution={str(i):0 for i in range(1,7)}
        for s in wins:distribution[str(len(s['attempts']))]+=1
        best=run=0;previous=None;solved_days=set()
        for s in finished:
            day=date.fromisoformat(s['puzzle']['day'])
            if s['status']=='won':
                run=run+1 if previous==day-timedelta(days=1) else 1;solved_days.add(day)
            else:run=0
            best=max(best,run);previous=day
        current=0;cursor=self.today()
        if cursor not in solved_days:cursor-=timedelta(days=1)
        while cursor in solved_days:current+=1;cursor-=timedelta(days=1)
        if finished and finished[-1]['puzzle']['day']==self.today().isoformat() and finished[-1]['status']=='lost':current=0
        return {'played':len(finished),'wins':len(wins),'winPercent':round(100*len(wins)/len(finished)) if finished else 0,'currentStreak':current,'bestStreak':best,'distribution':distribution}

    def leaderboard(self,guild_id):
        with self.connection() as db:users=[r['user_id'] for r in db.execute('SELECT user_id FROM participants WHERE guild_id=?',(str(guild_id),))]
        scores=[{'user_id':user,**self.stats(user)} for user in users]
        return sorted((s for s in scores if s['played']),key=lambda s:(-s['wins'],-s['currentStreak'],s['user_id']))[:10]
