from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import unicodedata


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',value).casefold() if c.isalnum())


@dataclass(frozen=True)
class Catalog:
    maps: tuple
    revision: str

    @classmethod
    def names(cls,path=None):
        data=json.loads(Path(path or Path(__file__).with_name('map_names.json')).read_text())
        maps=tuple({k:m.get(k,[]) if k=='aliases' else m[k] for k in ('id','name','aliases')} for m in data['maps'])
        if len(maps)<2:raise ValueError('At least two answer names are required')
        names={};ids=set()
        for m in maps:
            if m['id'] in ids:raise ValueError('Duplicate map ID')
            ids.add(m['id'])
            for name in [m['name'],*m['aliases']]:
                key=normalize(name)
                if not key or (key in names and names[key]!=m['id']):raise ValueError('Ambiguous map alias')
                names[key]=m['id']
        return cls(maps,hashlib.sha256(json.dumps(maps,sort_keys=True).encode()).hexdigest())

    @classmethod
    def load(cls,path):
        data=json.loads(Path(path).read_text())
        if data.get('format')!='portle-catalog' or data.get('version')!=1:raise ValueError('Unsupported catalog; run import-assets')
        maps=tuple(data['maps'])
        if len(maps)<2:raise ValueError('At least two maps are required')
        names={}
        for item in maps:
            if len(item['portals'])<6:raise ValueError('Not enough portal walls for '+item['name'])
            for name in [item['name'],*item.get('aliases',[])]:
                key=normalize(name)
                if key in names and names[key]!=item['id']:raise ValueError('Ambiguous map alias '+name)
                names[key]=item['id']
            for portal in item['portals']:
                if not all(math.isfinite(v) for key in ('position','right','up','normal') for v in portal[key]):raise ValueError('Nonfinite portal data')
                if portal['width']<=0 or portal['height']<=0:raise ValueError('Invalid portal aperture')
        digest=hashlib.sha256(json.dumps(maps,sort_keys=True).encode()).hexdigest()
        return cls(maps,digest)

    def resolve(self,guess):
        key=normalize(guess)
        for item in self.maps:
            if key in {normalize(name) for name in [item['name'],*item.get('aliases',[])]}:return item
        raise ValueError('Choose a map from the available map list; this did not use a guess.')

    def choices(self,current=''):
        key=normalize(current)
        return sorted((m['name'] for m in self.maps if key in normalize(m['name'])),key=str.casefold)


def import_catalog(source,destination):
    excluded={'MAP_Training','MAP_HangmanR3','MAP_Ozone','MAP_Ozone_Graffiti'}
    maps=[]
    for path in sorted(Path(source).glob('MAP_*.json')):
        if path.stem in excluded or any(x in path.stem for x in ('Creative','Biome6','Simulation')):continue
        scene=json.loads(path.read_text())
        if not scene.get('source',{}).get('geometryUsable') or '/Sublevels/' in scene.get('rootPackage',''):continue
        portals=[];seen=set()
        for n in scene['nodes']:
            if not n.get('enabled',True):continue
            signature=tuple(round(x,4) for key in ('position','normal') for x in n[key])+(round(n['width'],4),round(n['height'],4))
            if signature in seen:continue
            seen.add(signature)
            portals.append({k:n[k] for k in ('position','normal','right','up','width','height','shape')})
        if len(portals)<6:continue
        name=scene['name'];aliases=[]
        if scene['id']=='MAP_Erosion':name='Dought';aliases=['Erosion']
        if name=='Ozone Night':aliases=['Ozone']
        if name=='Foregone Destruction':aliases=['Foregone','FD']
        maps.append({'id':scene['id'],'name':name,'aliases':aliases,'portals':portals,
            'source':{'revision':scene['revision'],'executableSha256':scene['source']['executableSha256'],'kind':'Portal Atlas asset coordinates'}})
    output=Path(destination);output.parent.mkdir(parents=True,exist_ok=True)
    data={'format':'portle-catalog','version':1,'maps':maps}
    temporary=output.with_suffix('.tmp');temporary.write_text(json.dumps(data,separators=(',',':'),allow_nan=False))
    Catalog.load(temporary);temporary.replace(output)
    return {'maps':len(maps),'portals':sum(len(m['portals']) for m in maps)}
