"""Regression cases for cloud refresh / missing PTF column bug."""
import ast
import json
import sqlite3
import sys
import types
import tempfile
import unittest
from pathlib import Path

try:
    import streamlit
except ImportError:
    stub=types.ModuleType('streamlit')
    stub.cache_data=lambda **kwargs:(lambda f:f)
    sys.modules['streamlit']=stub

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
import pandas as pd
from compatibility_db import CompatibilityDB, ZOS_VERSIONS, VER
from crawler import parse_broadcom_html
from store import save, latest, connect
from maintenance import display_ptfs
from quality import maintenance_availability, maintenance_source, scraped_ptf_status, match_key

FIXTURE='''<html><table><tr><th>Product/Release</th><th>Z/OS V3R2</th><th>Z/OS V3R1</th><th>z/OS V2R5</th></tr>
<tr><td>ACF2 for z/OS 16.0</td><td>YES <a href="#ptf">PTFs</a></td><td>YES</td><td>YES</td></tr>
<tr><td>Auditor 12.0</td><td>In Progress</td><td>YES</td><td>YES</td></tr>
<tr><td>Balancing 1.1</td><td>NO</td><td>NO</td><td>NO</td></tr></table>
<section id="ptf"><h2>Required PTF(s)</h2>Component CAX1G00 requires LU15603 LU16693</section></html>'''

# Extract the function from app.py without executing the top-level Streamlit app.
module=ast.parse((BASE/'app.py').read_text())
func=next(x for x in module.body if isinstance(x,ast.FunctionDef) and x.name=='combined_data')
compiled=compile(ast.Module(body=[func],type_ignores=[]),str(BASE/'app.py'),'exec')
import re
ns={'pd':pd,'re':re,'ZOS_VERSIONS':ZOS_VERSIONS,'VER':VER,'CompatibilityDB':CompatibilityDB,'display_ptfs':display_ptfs,'maintenance_availability':maintenance_availability,'maintenance_source':maintenance_source,'scraped_ptf_status':scraped_ptf_status,'match_key':match_key}
exec(compiled,ns)

class RefreshRegressionTests(unittest.TestCase):
    def test_refresh_snapshot_still_displays_ptfs(self):
        scraped=parse_broadcom_html(FIXTURE)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'db.sqlite3'
            save(scraped,{'fixture':True},path)
            rows,info=latest(path=path)
            self.assertTrue(any(r['ptf_links_present'] for r in rows))
            frame=ns['combined_data'](CompatibilityDB.load(str(BASE/'data')),rows)
            result=frame[(frame.vendor=='Broadcom')&(frame['product']=='ACF2 for z/OS')&(frame.vrm=='16.0')].iloc[0]
            self.assertIn('LU15603',result['ptf_required'])
            self.assertIn('LU16693',result['ptf_required'])
    def test_missing_old_field_does_not_crash(self):
        scraped=parse_broadcom_html(FIXTURE)
        for item in scraped: item.pop('ptf_links_present',None)
        frame=ns['combined_data'](CompatibilityDB.load(str(BASE/'data')),scraped)
        result=frame[(frame.vendor=='Broadcom')&(frame['product']=='ACF2 for z/OS')&(frame.vrm=='16.0')].iloc[0]
        self.assertIn('LU15603',result['ptf_required'])
    def test_old_database_schema_migrates(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'old.sqlite3'
            c=sqlite3.connect(path)
            c.execute('''CREATE TABLE observations (snapshot_id INTEGER NOT NULL,row_key TEXT NOT NULL,vendor TEXT NOT NULL,product TEXT NOT NULL,vrm TEXT NOT NULL,zos_version TEXT NOT NULL,status TEXT NOT NULL,ptfs_json TEXT NOT NULL,links_json TEXT NOT NULL,source_url TEXT NOT NULL,evidence_status TEXT NOT NULL,display_name TEXT NOT NULL,PRIMARY KEY(snapshot_id,row_key))''')
            c.execute('''INSERT INTO observations VALUES(1,'abc','Broadcom','ACF2 for z/OS','16.0','3.2','Yes','[]',?,'url','Extracted','ACF2')''',(json.dumps([{'type':'PTFs'}]),))
            c.commit();c.close()
            with connect(path) as new:
                row=new.execute('SELECT ptf_links_present FROM observations LIMIT 1').fetchone()
                self.assertEqual(row['ptf_links_present'],1)

if __name__=='__main__':unittest.main()
