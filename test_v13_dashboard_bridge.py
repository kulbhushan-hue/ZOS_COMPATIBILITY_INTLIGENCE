import csv
import tempfile
import unittest
from pathlib import Path
import pandas as pd
from deep_app_bridge_v13 import merge_verified_deep

class BridgeTests(unittest.TestCase):
 def test_only_exact_unique_release_is_applied(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'d.csv'
   cols=['vendor','product','release','zos_version','compatibility','evidence_level']
   with p.open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=cols);writer.writeheader()
    writer.writerows([dict(vendor='IBM',product='Exact Product',release='5.0',zos_version='3.2',compatibility='Yes',evidence_level='Explicit source row'),
                     dict(vendor='IBM',product='Other Product',release='6.0',zos_version='3.2',compatibility='No',evidence_level='Explicit source row')])
   f=pd.DataFrame([{'vendor':'IBM','product':'Exact Product','vrm':'5.0','zos32':'Unverified','provenance_3.2':'CSV baseline'}])
   out=merge_verified_deep(f,p)
   self.assertEqual(out.loc[0,'zos32'],'Yes')
   self.assertIn('Exact live',out.loc[0,'provenance_3.2'])
 def test_conflicting_claims_not_promoted(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'d.csv'
   with p.open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=['vendor','product','release','zos_version','compatibility']);writer.writeheader()
    for status in ('Yes','No'):
     writer.writerow({'vendor':'IBM','product':'Exact Product','release':'5.0','zos_version':'3.2','compatibility':status})
   f=pd.DataFrame([{'vendor':'IBM','product':'Exact Product','vrm':'5.0','zos32':'Unverified'}])
   self.assertEqual(merge_verified_deep(f,p).loc[0,'zos32'],'Unverified')
if __name__=='__main__':unittest.main()
