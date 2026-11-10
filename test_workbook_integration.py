"""Validate all workbook sheets and preserve original source statements."""
import sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from workbook_data import load_workbook,merge_workbook,extract_ptfs,workbook_worklist, vendor_name
from compatibility_db import CompatibilityDB

class WorkbookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sheets,cls.amxt,cls.links=load_workbook(ROOT/'ISV Compatibility assessment -Data.xlsx')
        cls.merged=merge_workbook(CompatibilityDB.load(str(ROOT/'data')).df,cls.amxt,cls.links)
    def test_three_sheets(self):
        self.assertEqual(list(self.sheets),['Sheet1','Sheet2','AMXT'])
        self.assertEqual(len(self.amxt),383)
        self.assertEqual(len(self.sheets['Sheet2']),241)
    def test_no_invented_31(self):
        rows=self.merged[self.merged['data_status'].eq('Workbook AMXT')]
        self.assertTrue(len(rows)>300)
        self.assertTrue((rows['zos31']=='Unverified').all())
        self.assertTrue((rows['ptf_required_31']=='Verify').all())
    def test_specific_ptfs(self):
        rows=self.amxt[self.amxt['Product'].str.strip()=='Allocate DASD Space and Placement']
        self.assertEqual(len(rows),1)
        self.assertEqual(extract_ptfs(rows.iloc[0]['If Yes, PTF Required?']),['LU17113','LU19858'])
        selected=self.merged[(self.merged['product']=='Allocate DASD Space and Placement') & (self.merged['vrm']=='V12')]
        self.assertEqual(selected.iloc[0]['zos32'],'Yes')
        self.assertIn('LU17113',selected.iloc[0]['ptf_required'])
    def test_worklist_and_links(self):
        self.assertGreaterEqual(len(workbook_worklist(self.amxt)),100)
        self.assertTrue(self.links['Broadcom'].startswith('https://'))
        self.assertEqual(vendor_name('Broadcom Inc.'),'Broadcom')
    def test_original_evidence(self):
        row=self.merged[(self.merged['product']=='Allocate DASD Space and Placement') & (self.merged['vrm']=='V12')].iloc[0]
        self.assertTrue(row['workbook_source'].startswith('AMXT Excel row'))
        self.assertIn('PTFs not installed',row['workbook_comments'])

if __name__=='__main__':unittest.main()
