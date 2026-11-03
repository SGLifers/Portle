import hashlib
import json
from portle.catalog import Catalog


def fixture_catalog():
    maps=[]
    for k,name in enumerate(['Cinder','Harbor','Zen Garden']):
        portals=[{'position':[float(i*3),float((i%7)*4+k),float(i%5)],'normal':[1.,0.,0.],'right':[0.,1.,0.],'up':[0.,0.,1.],
            'width':2.,'height':3.,'shape':'rectangle'} for i in range(40)]
        maps.append({'id':'MAP_'+name.replace(' ','_'),'name':name,'aliases':['zg'] if k==2 else [],'portals':portals,'source':{'kind':'unit test fixture'}})
    return Catalog(tuple(maps),hashlib.sha256(json.dumps(maps,sort_keys=True).encode()).hexdigest())
