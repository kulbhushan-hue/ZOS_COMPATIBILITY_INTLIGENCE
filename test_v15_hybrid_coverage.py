import csv
import tempfile
import unittest
from pathlib import Path
from hybrid_coverage_v15 import build_reports
from dynamic_capture_v12 import is_report_shell

def write(path, rows):
    if not rows:return
    with path.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

class HybridCoverage(unittest.TestCase):
    def test_readable_url_not_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            write(out/'vendor_scraping_results.csv',[dict(vendor='IBM',url='https://www.ibm.com/report',state='Read')])
            write(out/'vendor_page_diagnostics.csv',[dict(vendor='IBM',url='https://www.ibm.com/report',potential_dynamic_content='Yes')])
            result=build_reports(out, {'IBM':[{'product':'CICS','release':'6.1'}]},[{'vendor':'IBM','url':'https://www.ibm.com/report'}],out/'nothing.csv')
            self.assertEqual(result['vendors_with_structured_claims'],0)
            with (out/'vendor_extraction_coverage.csv').open(encoding='utf-8-sig') as fh:
                row=list(csv.DictReader(fh))[0]
            self.assertEqual(row['urls_read'],'1')
            self.assertEqual(row['compatibility_claims'],'0')
            self.assertEqual(row['dynamic_shell_pages'],'1')
            self.assertIn('rendered',row['next_action'])
    def test_facts_are_not_exact_compatibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            write(out/'vendor_document_facts.csv',[dict(vendor='BMC',product='Predictor',release='Not established',fact_type='Minimum OS')])
            result=build_reports(out, {'BMC':[{'product':'Predictor','release':'2.5'}]},[],out/'nothing.csv')
            self.assertEqual(result['vendors_with_evidence_only'],1)
            self.assertEqual(result['vendors_with_structured_claims'],0)
    def test_product_claim_needs_exact_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            write(out/'all_vendor_extracted_compatibility.csv',[dict(vendor='IBM',product='CICS',release='6.1',zos_version='3.2',compatibility='Yes',match_status='No exact inventory match')])
            w=out/'products.csv'
            write(w,[{'Vendor':'IBM','Product':'CICS','Release':'6.1','Approved source URL':'https://www.ibm.com/report'}])
            build_reports(out,{},[],w)
            with (out/'vendor_product_extraction_coverage.csv').open(encoding='utf-8-sig') as fh:
                row=list(csv.DictReader(fh))[0]
            self.assertEqual(row['verification_state'],'Structured assertion — verify inventory release')
    def test_ibm_shell_detected(self):
        html=b'<html><script src="app.js"></script><script src="bundle.js"></script><div id="root"></div></html>'
        self.assertTrue(is_report_shell('https://www.ibm.com/software/reports/compatibility/clarity/',html))

if __name__=='__main__':unittest.main()
