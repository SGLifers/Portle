import json
from io import BytesIO
from pathlib import Path
import unittest
from PIL import Image
from portle.catalog import Catalog
from portle.game import new_state,portal_order
from portle.render import png,corners

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT/'data/catalog.json').exists(),'Private installed asset catalog not in Git')
class RealAssetTests(unittest.TestCase):
    def test_source_provenance_and_portal_values(self):
        catalog=Catalog.load(ROOT/'data/catalog.json');self.assertGreaterEqual(len(catalog.maps),20)
        for item in catalog.maps:
            self.assertEqual(len(item['source']['executableSha256']),64);self.assertTrue(item['source']['revision'])
            scene=json.loads((ROOT.parent/'PortalAtlas/data/scenes'/(item['id']+'.json')).read_text())
            positions={tuple(p['position']) for p in scene['nodes']}
            for portal in item['portals']:self.assertIn(tuple(portal['position']),positions)
    def test_each_real_map_renders_both_projections(self):
        catalog=Catalog.load(ROOT/'data/catalog.json')
        for item in catalog.maps:
            with self.subTest(map=item['id']):
                puzzle={'map':item,'day':'2026-11-03','order':portal_order(item['portals'],'test')}
                state=new_state('round','player',puzzle,'daily')
                for mode in ['iso','top']:
                    data=png(state,mode);image=Image.open(BytesIO(data));self.assertEqual(image.size,(1100,760));self.assertLess(len(data),2_000_000);self.assertEqual(image.info,{})
    def test_actual_aperture_corners_are_finite(self):
        import math
        for item in Catalog.load(ROOT/'data/catalog.json').maps:
            for portal in item['portals']:self.assertTrue(all(math.isfinite(v) for corner in corners(portal) for v in corner))
