"""Offline regression tests: URL safety, source isolation, evidence and BMC table."""
from __future__ import annotations
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from multi_vendor import (safe_public_url, extract_text, evidence_for_products,
                          extract_bmc_support_matrix, sources_for_vendors, audit_vendor)
from store import save_vendor_audits, vendor_audits

class MultiVendorTests(unittest.TestCase):
    def test_url_restrictions(self):
        self.assertTrue(safe_public_url('https://www.ibm.com/docs/en/zos/3.2.0','IBM'))
        self.assertFalse(safe_public_url('http://127.0.0.1/private','IBM'))
        self.assertFalse(safe_public_url('http://192.168.1.4','IBM'))
        self.assertFalse(safe_public_url('file:///etc/passwd','IBM'))
        self.assertFalse(safe_public_url('https://username:pass@ibm.com/test','IBM'))
        self.assertFalse(safe_public_url('https://other-site.com/docs','IBM'))
        self.assertFalse(safe_public_url('https://www.ibm.com/account/login','IBM'))

    def test_evidence_does_not_assert_compatibility(self):
        html=b'<html><body><p>ACF2 for z/OS supports z/OS 3.2 with PTF LU15603. Please verify.</p></body></html>'
        text,typ=extract_text(html,'text/html')
        self.assertEqual(typ,'HTML')
        source={'origin':'AMXT product reference'}
        got=evidence_for_products(text,[{'product':'ACF2 for z/OS','vrm':'16.0'}],source,'https://broadcom.com/doc')
        self.assertEqual(len(got),1)
        self.assertIn('3.2',got[0]['zos_mentions'])
        self.assertEqual(got[0]['ptf_ids'],['LU15603'])
        self.assertIn('not confirmed',got[0]['evidence_level'])

    def test_bmc_explicit_support_table(self):
        html=b'''<table><tr><th>Operating systems/ Mainframe</th><th>BMC Performance Predictor for Mainframes</th><th>BMC Performance Analyzer for Mainframes</th></tr><tr><td>z/OS 3.2</td><td>X</td><td>X</td></tr><tr><td>z/OS 3.1</td><td>X</td><td></td></tr></table>'''
        items=extract_bmc_support_matrix(html,'https://docs.bmc.com/support-matrix/')
        self.assertEqual(len(items),3)
        self.assertEqual(items[0]['compatibility'],'Yes')
        self.assertEqual(items[0]['vrm'],'Not stated')

    def test_audit_history_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            db=Path(temp)/'tests.sqlite3'
            r={'vendor':'IBM','url':'https://www.ibm.com/docs','origin':'curated','checked_at':'2026-11-09T10:00:00+00:00',
               'state':'Read','matched_products':1,'ptf_mentions':1,'note':'public documentation',
               'matches':[{'product':'CICS','ptf_ids':['UI12345']}],
               'assertions':[]}
            save_vendor_audits([r],db)
            rows=vendor_audits(db)
            self.assertEqual(rows[0]['vendor'],'IBM')
            self.assertIn('UI12345',rows[0]['matches_json'])

if __name__=='__main__':unittest.main()

class ActionCompatibilityTests(unittest.TestCase):
    def test_explicit_release_range(self):
        from multi_vendor import extract_action_release_matrix
        body=b'''<table><tr><th>Release</th><th>General Availability</th><th>Maintenance</th><th>End of Service</th><th>System Compatibility</th></tr><tr><td>eventACTION 8.08</td><td>2025-02-06</td><td>8.08.24</td><td>2030-03-31</td><td>z/OS 2.1 - z/OS 3.2</td></tr></table>'''
        x=extract_action_release_matrix(body,'https://actionsoftware.com/support-form/release-history/')
        self.assertEqual(len(x),3)
        self.assertEqual(x[0]['product'],'eventACTION')
        self.assertEqual(x[0]['vrm'],'8.08')
        self.assertTrue(all(r['compatibility']=='Yes' for r in x))
