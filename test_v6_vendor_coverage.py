import sys, unittest
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vendor_coverage import product_source_worklist, coverage_summary
from vendor_assertions import extract_official_document_tables

class V6VendorCoverageTests(unittest.TestCase):
    def test_source_gap_and_exact_release_only(self):
        data=pd.DataFrame([
            {'vendor':'IBM','product':'CICS TS','vrm':'6.2','zos32':'Yes','link':'https://www.ibm.com/docs/something','ptf_required':''},
            {'vendor':'BMC','product':'AMI','vrm':'2.5','zos32':'Yes','link':'https://bad.example/page','ptf_required':'LU12345'},
            {'vendor':'Rocket','product':'Tmon','vrm':'4','zos32':'Unverified','link':''}])
        observations=[{'vendor':'IBM','product':'CICS TS','vrm':'Not stated','zos_version':'3.2','compatibility':'Yes','evidence_level':'Explicit vendor table: product, release'},
        {'vendor':'IBM','product':'CICS TS','vrm':'6.2','zos_version':'3.2','compatibility':'Not asserted','evidence_level':'IBM requirement'}]
        output=product_source_worklist(data,observations=observations)
        sums=coverage_summary(output)
        self.assertEqual(sums['products'],3)
        self.assertEqual(sums['approved_vendor_references'],1)
        self.assertEqual(sums['explicit_3_2_claims_for_review'],0)
        self.assertEqual(output.iloc[0]['Exact release observations'],1)
        self.assertEqual(output.iloc[1]['Workbook/baseline PTF identifiers'],'LU12345')
    def test_blocked_source_label(self):
        data=pd.DataFrame([{'vendor':'BMC','product':'AMI','vrm':'2.5','link':'https://docs.bmc.com/example'}])
        history=[{'vendor':'BMC','source_url':'https://docs.bmc.com/example','state':'Blocked / failed','checked_at':'2026-11-09T12:00:00Z'}]
        result=product_source_worklist(data,history)
        self.assertIn('blocked',result.iloc[0]['Review action'].lower())
    def test_bmc_structured_exported_table(self):
        text='''Product compatibility matrix\nOperating systems/ Mainframe | BMC Performance Predictor | Comments\nz/OS 3.2 | X | Support started in version 2.5.00\n'''
        result=extract_official_document_tables('BMC',text,'https://docs.bmc.com/report.pdf')
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['vrm'],'Not stated')
        self.assertEqual(result[0]['required_level'],'Support started in version 2.5.00')
    def test_ibm_exported_table_is_requirement_only(self):
        text='''z/OS 3.2 software requirements\nIf you use this IBM product... | You need this product level (usually achieved with PTFs)\nIBM CICS Transaction Server | V6.2 with PTF UI12345\n'''
        rows=extract_official_document_tables('IBM',text,'https://www.ibm.com/docs/en/zos/3.2.0')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['maintenance_ids'],'UI12345')
        self.assertEqual(rows[0]['compatibility'],'Not asserted')
    def test_unstructured_prose_is_not_certification(self):
        self.assertEqual(extract_official_document_tables('BMC','BMC supports z/OS 3.2 with AMI 2.5','https://docs.bmc.com/x'),[])

if __name__=='__main__':unittest.main()
