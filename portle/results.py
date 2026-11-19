"""Server-scoped result destinations and durable per-day delivery reservations."""
import hashlib
import json
import uuid

from .game import GameError


class ResultStore:
    def __init__(self,store):
        self.store=store
        with store.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS result_config(guild_id TEXT PRIMARY KEY,channel_id TEXT NOT NULL,enabled INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS server_result_posts(guild_id TEXT NOT NULL,puzzle_id TEXT NOT NULL,user_id TEXT NOT NULL,round_id TEXT NOT NULL,channel_id TEXT NOT NULL,status TEXT NOT NULL,claim_id TEXT NOT NULL,message_id TEXT,PRIMARY KEY(guild_id,puzzle_id,user_id));
            ''')

    def configure(self,guild_id,channel_id=None,enabled=None):
        if not str(guild_id).isascii() or not str(guild_id).isdigit() or int(guild_id)<=0:raise GameError('Choose a server for results.')
        if channel_id is not None and (not str(channel_id).isascii() or not str(channel_id).isdigit() or int(channel_id)<=0):raise GameError('Choose a valid server text channel.')
        with self.store.transaction() as db:
            prior=db.execute('SELECT * FROM result_config WHERE guild_id=?',(str(guild_id),)).fetchone()
            if channel_id is None and enabled is None:return dict(prior) if prior else None
            channel=str(channel_id) if channel_id is not None else prior['channel_id'] if prior else None
            if channel is None:raise GameError('Choose a results channel first: /portle results channel:#games')
            active=bool(enabled) if enabled is not None else True if channel_id is not None else bool(prior['enabled'])
            db.execute('INSERT INTO result_config VALUES (?,?,?) ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id,enabled=excluded.enabled',(str(guild_id),channel,int(active)))
            return {'guild_id':str(guild_id),'channel_id':channel,'enabled':int(active)}

    def _completed(self,db,user_id,round_id=None):
        if round_id is not None:state=self.store._owned(db,round_id,user_id)
        else:
            pid=('manual:' if self.store.clues else '')+'daily:'+self.store.today().isoformat()
            row=db.execute('SELECT state FROM rounds WHERE puzzle_id=? AND user_id=? AND mode=?',(pid,str(user_id),'daily')).fetchone()
            if not row:raise GameError('Finish today\'s daily with /portle play before sharing results.')
            state=json.loads(row['state'])
        expected=('manual:' if self.store.clues else '')+'daily:'+self.store.today().isoformat()
        if state['mode']!='daily' or state['puzzle']['id']!=expected:
            raise GameError('Only today\'s daily result can be shared. Use /portle play for the current puzzle.')
        if state['status']=='playing':raise GameError('Finish today\'s daily before sharing results.')
        return state

    def completed(self,user_id,round_id=None):
        with self.store.connection() as db:return self._completed(db,user_id,round_id)

    def legacy_post(self,round_id):
        # Old reservations contain no destination. Do not repeat their automatic send.
        with self.store.connection() as db:return db.execute('SELECT 1 FROM result_posts WHERE round_id=?',(round_id,)).fetchone() is not None

    def claim(self,round_id,user_id,guild_id,channel_id,manual=False):
        if guild_id is None or channel_id is None:raise GameError('A server results channel is required.')
        with self.store.transaction() as db:
            state=self._completed(db,user_id,round_id)
            config=db.execute('SELECT * FROM result_config WHERE guild_id=?',(str(guild_id),)).fetchone()
            if (manual and not config) or (config and (not config['enabled'] or config['channel_id']!=str(channel_id))):
                raise GameError('Results channel settings changed. Reopen /portle play and try Share results again.')
            key=(str(guild_id),state['puzzle']['id'],str(user_id))
            prior=db.execute('SELECT * FROM server_result_posts WHERE guild_id=? AND puzzle_id=? AND user_id=?',key).fetchone()
            db.execute('INSERT OR IGNORE INTO participants VALUES (?,?)',(str(guild_id),str(user_id)))
            if prior and (prior['status']!='rejected' or not manual):return dict(prior,claimed=False)
            claim=uuid.uuid4().hex
            db.execute('''INSERT INTO server_result_posts VALUES (?,?,?,?,?,?,?,NULL)
                ON CONFLICT(guild_id,puzzle_id,user_id) DO UPDATE SET round_id=excluded.round_id,channel_id=excluded.channel_id,status=excluded.status,claim_id=excluded.claim_id,message_id=NULL''',
                (*key,round_id,str(channel_id),'pending',claim))
            row=dict(db.execute('SELECT * FROM server_result_posts WHERE guild_id=? AND puzzle_id=? AND user_id=?',key).fetchone())
            return dict(row,claimed=True,state=state)

    def finish(self,claim,status,message_id=None):
        if status not in ('sent','rejected','uncertain'):raise ValueError('Invalid result delivery status')
        with self.store.transaction() as db:
            db.execute("UPDATE server_result_posts SET status=?,message_id=? WHERE guild_id=? AND puzzle_id=? AND user_id=? AND claim_id=? AND status='pending'",
                (status,str(message_id) if message_id is not None else None,claim['guild_id'],claim['puzzle_id'],claim['user_id'],claim['claim_id']))

    @staticmethod
    def nonce(claim):
        return hashlib.sha256(json.dumps([claim[k] for k in ('guild_id','puzzle_id','user_id')]).encode()).hexdigest()[:24]
