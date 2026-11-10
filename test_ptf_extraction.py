"""Regression tests for real-world PTF display and anchor layouts."""
import sys,types
from pathlib import Path
import unittest
try:import streamlit
except ImportError:
 st=types.ModuleType('streamlit');st.cache_data=lambda **k:(lambda f:f);sys.modules['streamlit']=st
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crawler import parse_broadcom_html
from maintenance import display_ptfs,link_ids

class PTFDetailsTests(unittest.TestCase):
 def test_anchor_in_table_row_is_scoped_to_product(self):
  html='''<table><tr><th>Product/Release</th><th>Z/OS V3R2</th><th>Z/OS V3R1</th><th>z/OS V2R5</th></tr>
  <tr><td>ACF2 for z/OS 16.0</td><td>YES <a href="#A">PTFs</a></td><td>YES</td><td>YES</td></tr>
  <tr><td>Auditor 12.1</td><td>YES <a href="#B">PTFs</a></td><td>YES</td><td>YES</td></tr>
  <tr><td>Balancing 1.1</td><td>NO</td><td>NO</td><td>NO</td></tr></table>
  <table><tr><td><a name="A"></a>Required PTF(s)</td></tr><tr><td>CAX1G00 LU15603 LU16693</td></tr>
  <tr><td><a name="B"></a>Required PTF(s)</td></tr><tr><td>CAJ0C10 LU15606</td></tr></table>'''
  rows=parse_broadcom_html(html)
  a=next(r for r in rows if r['product']=='ACF2 for z/OS' and r['zos_version']=='3.2')
  b=next(r for r in rows if r['product']=='Auditor' and r['zos_version']=='3.2')
  self.assertEqual(a['ptfs'],['LU15603','LU16693'])
  self.assertEqual(b['ptfs'],['LU15606'])
 def test_unreadable_link_keeps_existing_ptfs(self):
  rec={'ptf_links_present':True,'links':[{'type':'PTFs','text':'','ptfs':[],'url':'https://example.com'}],'ptfs':[]}
  self.assertEqual(display_ptfs(rec,'LU17113, LU19858')[0],'LU17113, LU19858')
  self.assertIn('not extracted',display_ptfs(rec,'Verify')[0])
 def test_ptf_detail_ids_only(self):
  rec={'ptfs':[],'links':[{'type':'PTFs','ptfs':['LU16693']},{'type':'Additional Information','ptfs':['LU99999']}]}
  self.assertEqual(link_ids(rec),['LU16693'])
if __name__=='__main__':unittest.main()
