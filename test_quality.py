"""Data-quality rules exercised without accessing the vendor website."""
import ast
import csv
from pathlib import Path
import sys
import unittest
import pandas as pd

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from compatibility_db import CompatibilityDB, VER, ZOS_VERSIONS
from maintenance import display_ptfs
from quality import (ptf_ids, maintenance_availability, maintenance_source,
                     scraped_ptf_status, match_key)
from workbook_data import load_workbook, merge_workbook

node=next(n for n in ast.parse((BASE/'app.py').read_text()).body
          if isinstance(n,ast.FunctionDef) and n.name=='combined_data')
ns={'pd':pd,'CompatibilityDB':CompatibilityDB,'ZOS_VERSIONS':ZOS_VERSIONS,'VER':VER,'display_ptfs':display_ptfs,
    'maintenance_availability':maintenance_availability,
    'maintenance_source':maintenance_source,
    'scraped_ptf_status':scraped_ptf_status,'match_key':match_key}
exec(compile(ast.Module(body=[node],type_ignores=[]),'app.py','exec'),ns)

class QualityTests(unittest.TestCase):
    def test_unavailable_not_misclassified(self):
        self.assertEqual(maintenance_availability('PTFs LU18196 and LU18696 are not available'),'Not available')
        self.assertEqual(maintenance_availability('LU18695 superseded by LU18187'),'Superseded / replacement noted')
        self.assertEqual(maintenance_availability('LU15603 and LU16693'),'Not stated / verify')
        self.assertEqual(maintenance_availability('PTF is required'),'Required (source statement)')

    def test_deep_link_and_exact_match(self):
        record={'source_url':'https://example.com/matrix','links':[{'type':'PTFs','url':'https://example.com/matrix#product_ptfs','text':'PTF LU15603 required'}],'ptfs':['LU15603']}
        self.assertEqual(maintenance_source(record),'https://example.com/matrix#product_ptfs')
        self.assertEqual(scraped_ptf_status(record),'Required (source statement)')
        self.assertNotEqual(match_key('Broadcom','ACF2 for z/OS','16.0'),match_key('Broadcom','ACF2 for z/OS','17.0'))
        self.assertNotEqual(match_key('Broadcom','ACF2 for z/OS','16.0'),match_key('IBM','ACF2 for z/OS','16.0'))
        self.assertEqual(match_key('Broadcom','ACF2 for z/OS 16.0',''),match_key('Broadcom','ACF2 for z/OS','16.0'))

    def test_snapshot_merges_exact_version_only(self):
        db=CompatibilityDB.load(str(BASE/'data'))
        r={'vendor':'Broadcom','product':'ACF2 for z/OS','vrm':'16.0','zos_version':'3.2','status':'Yes',
           'ptfs':['LU15603','LU16693'],'ptf_links_present':True,'captured_at':'2026-11-09T01:00:00+00:00',
           'links':[{'type':'PTFs','url':'https://example.com/#ptfs16','text':'LU15603 LU16693','ptfs':['LU15603','LU16693']}],
           'source_url':'https://example.com/','evidence_status':'Extracted'}
        merged=ns['combined_data'](db,[r])
        row=merged[(merged.vendor=='Broadcom')&(merged['product']=='ACF2 for z/OS')&(merged.vrm=='16.0')].iloc[0]
        self.assertEqual(row['ptf_source_url_3.2'],'https://example.com/#ptfs16')
        self.assertEqual(row['ptf_id_source_3.2'],'Broadcom linked detail')
        self.assertEqual(row['ptf_last_scraped_3.2'],'2026-11-09T01:00:00+00:00')
        self.assertIn('LU15603',row['ptf_required'])
        self.assertNotIn('LU15603',str(row['ptf_required_31']))

    def test_amxt_baseline_remains_when_scrape_empty(self):
        sheets,amxt,urls=load_workbook(BASE/'ISV Compatibility assessment -Data.xlsx')
        base=merge_workbook(CompatibilityDB.load(str(BASE/'data')).df,amxt,urls)
        needle=base[base['workbook_ptf_raw'].astype(str).str.contains('LU17113',na=False)]
        self.assertGreater(len(needle),0)
        row=needle.iloc[0]
        rec={'vendor':row['vendor'],'product':row['product'],'vrm':row['vrm'],'zos_version':'3.2',
             'status':'Yes','ptfs':[],'ptf_links_present':True,'links':[{'type':'PTFs','ptfs':[],'url':'https://example.com/#ptfs','text':''}],
             'source_url':'https://example.com/','evidence_status':'Partial'}
        enriched=ns['combined_data'](CompatibilityDB(base),[rec])
        match=enriched[(enriched.vendor==row.vendor)&(enriched['product']==row['product'])&(enriched.vrm==row.vrm)].iloc[0]
        self.assertIn('LU17113',str(match['ptf_required']))
        self.assertEqual(match['ptf_id_source_3.2'],'Workbook/CSV retained')

if __name__=='__main__':unittest.main()
