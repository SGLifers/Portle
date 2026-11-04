"""Local authoring library. Published screenshots are immutable round snapshots."""
from contextlib import contextmanager
import fcntl
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import secrets
import threading
import warnings
from PIL import Image,ImageOps,UnidentifiedImageError
from .game import GameError

MAX_BYTES=8*1024*1024
MAX_PIXELS=24_000_000


class ClueLibrary:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        (self.root/'images').mkdir(exist_ok=True)
        self._thread_lock=threading.RLock()
    def _read(self):
        path=self.root/'index.json'
        if not path.exists():return {'version':1,'packs':{}}
        data=json.loads(path.read_text())
        if data.get('version')!=1 or not isinstance(data.get('packs'),dict):raise GameError('Unsupported clue library.')
        return data
    @contextmanager
    def _edit(self):
        with self._thread_lock,(self.root/'index.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);data=self._read()
            yield data
            path=self.root/('index-'+secrets.token_hex(12)+'.tmp')
            try:
                path.write_text(json.dumps(data,separators=(',',':')));path.chmod(0o600);os.replace(path,self.root/'index.json')
            finally:path.unlink(missing_ok=True)
    @staticmethod
    def _slot(slot):
        if not isinstance(slot,int) or isinstance(slot,bool) or not 1<=slot<=6:raise GameError('Choose a clue slot from 1 to 6.')
        return slot-1
    @staticmethod
    def _pack(data,map_id):
        return data['packs'].setdefault(map_id,{'draft':[None]*6,'published':None})
    def upload(self,map_id,slot,content):
        index=self._slot(slot)
        if not isinstance(content,bytes) or not 0<len(content)<=MAX_BYTES:raise GameError('Choose an image smaller than 8 MiB.')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error',Image.DecompressionBombWarning)
                with Image.open(BytesIO(content)) as source:
                    if source.format not in ('PNG','JPEG','WEBP'):raise GameError('Use a PNG, JPEG or WebP screenshot.')
                    if getattr(source,'n_frames',1)!=1:raise GameError('Use a still screenshot, not an animation.')
                    if source.width*source.height>MAX_PIXELS or max(source.size)>8192:raise GameError('Image dimensions are too large (24 megapixels maximum).')
                    source.load();image=ImageOps.exif_transpose(source)
                    # Decode/re-encode to strip EXIF/comments/filenames without resizing,
                    # cropping, annotating, or generating any part of the clue.
                    image=image.convert('RGBA' if 'A' in image.getbands() or 'transparency' in source.info else 'RGB')
                    image.info.clear()
                    output=BytesIO();image.save(output,format='PNG');pixels=output.getvalue()
        except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombWarning,Image.DecompressionBombError) as exc:
            raise GameError('That file could not be read as a safe screenshot.') from exc
        if len(pixels)>MAX_BYTES:raise GameError('PNG output exceeds 8 MiB; export a smaller screenshot.')
        digest=hashlib.sha256(pixels).hexdigest();destination=self.root/'images'/(digest+'.png')
        with self._edit() as data:
            if not destination.exists():
                temp=destination.with_suffix('.'+secrets.token_hex(8)+'.tmp')
                try:temp.write_bytes(pixels);temp.chmod(0o600);os.replace(temp,destination)
                finally:temp.unlink(missing_ok=True)
            self._pack(data,map_id)['draft'][index]=digest
        return digest
    def clear(self,map_id,slot):
        index=self._slot(slot)
        with self._edit() as data:self._pack(data,map_id)['draft'][index]=None
    def publish(self,map_id):
        with self._edit() as data:
            pack=self._pack(data,map_id)
            if len(pack['draft'])!=6 or not all(pack['draft']):raise GameError('Add all six screenshots before publishing.')
            for digest in pack['draft']:self.image(digest)
            pack['published']={'id':secrets.token_hex(16),'images':list(pack['draft'])}
    def unpublish(self,map_id):
        with self._edit() as data:self._pack(data,map_id)['published']=None
    def image(self,digest):
        if not isinstance(digest,str) or not re.fullmatch(r'[a-f0-9]{64}',digest):raise GameError('Invalid clue image.')
        path=self.root/'images'/(digest+'.png')
        if not path.is_file():raise GameError('A saved clue image is missing. Restore the clue library backup.')
        content=path.read_bytes()
        if hashlib.sha256(content).hexdigest()!=digest:raise GameError('A saved clue image changed. Restore the clue library backup.')
        return content
    def published(self):
        return {key:value['published'] for key,value in self._read()['packs'].items() if value.get('published')}
    def management(self,catalog):
        packs=self._read()['packs']
        return [{'id':m['id'],'name':m['name'],**packs.get(m['id'],{'draft':[None]*6,'published':None})} for m in catalog.maps]
