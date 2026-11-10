"""Ensure all original vendor data is shipped and the Excel writer remains usable."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from compatibility_db import CompatibilityDB, build_excel

class BaselineTests(unittest.TestCase):
    def test_load_six_vendors_and_240_records(self):
        db=CompatibilityDB.load(str(Path(__file__).resolve().parents[1]/'data'))
        self.assertEqual(len(db.df),240)
        self.assertEqual(set(db.df['vendor']),{'Broadcom','IBM','BMC','Rocket','Precisely','ASG'})
    def test_generate_original_excel(self):
        db=CompatibilityDB.load(str(Path(__file__).resolve().parents[1]/'data'))
        value=build_excel({'Filtered':db.df.head(2)},version='3.2')
        self.assertTrue(value.startswith(b'PK'))
        self.assertGreater(len(value),2000)

if __name__=='__main__':unittest.main()
