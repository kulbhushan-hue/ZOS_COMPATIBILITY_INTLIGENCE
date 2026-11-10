import unittest
from vendor_adapters_v10 import extract_vendor_matrix, extract_ibm_report_table
from deep_scraper import consolidate_ptfs, source_quality

class V10VendorParsers(unittest.TestCase):
    def test_bmc_os_matrix_without_release_is_evidence_only(self):
        body=b'''<h1>BMC AMI Capacity Management</h1><table><tr><th>Operating systems/ Mainframe</th><th>BMC Performance Predictor for Mainframes</th><th>Comments</th></tr><tr><td>z/OS 3.2</td><td>X</td><td>Support started in version 2.5.00</td></tr></table>'''
        inv={'BMC':[{'product':'BMC Performance Predictor for Mainframes','release':'2.5.00'}]}
        c,o=extract_vendor_matrix(body,'BMC','https://docs.bmc.com/matrix',inv,'2026')
        self.assertFalse(c)
        self.assertEqual(len(o),1)
        self.assertEqual((o[0]['product'],o[0]['zos_version']),('BMC Performance Predictor for Mainframes','3.2'))
    def test_bmc_header_explicit_release_and_exact_inventory(self):
        body=b'''<table><tr><th>Operating System</th><th>BMC Performance Predictor for Mainframes 2.5.00</th></tr><tr><td>z/OS 3.2</td><td>X</td></tr></table>'''
        inv={'BMC':[{'product':'BMC Performance Predictor for Mainframes','release':'2.5.00'}]}
        c,o=extract_vendor_matrix(body,'BMC','https://docs.bmc.com/matrix',inv,'2026')
        self.assertEqual((len(c),len(o)),(1,0))
        self.assertEqual(c[0]['release'],'2.5.00')
    def test_bmc_wrong_release_stays_evidence_only(self):
        body=b'''<table><tr><th>Operating System</th><th>BMC Performance Predictor for Mainframes 2.6.00</th></tr><tr><td>z/OS 3.2</td><td>X</td></tr></table>'''
        inv={'BMC':[{'product':'BMC Performance Predictor for Mainframes','release':'2.5.00'}]}
        c,o=extract_vendor_matrix(body,'BMC','https://docs.bmc.com/matrix',inv,'2026')
        self.assertEqual(len(c),0)
        self.assertEqual(len(o),1)
    def test_linux_row_never_zos(self):
        body=b'<table><tr><th>Operating System</th><th>Widget 2.5</th></tr><tr><td>Linux 3.2</td><td>X</td></tr></table>'
        c,o=extract_vendor_matrix(body,'Rocket','https://www.rocketsoftware.com/x',{'Rocket':[]},'2026')
        self.assertFalse(c or o)
    def test_ibm_spcr_no_status_evidence_only(self):
        body=b'<h1>IBM Classic CDC for z/OS 11.3</h1><table><tr><th>Operating System</th><th>Notes</th></tr><tr><td>z/OS 3.2</td><td>See installation information</td></tr></table>'
        c,o=extract_ibm_report_table(body,'https://www.ibm.com/a',{'IBM':[{'product':'IBM Classic CDC for z/OS','release':'11.3'}]},'2026')
        self.assertEqual(len(c),0)
        self.assertEqual(len(o),1)
    def test_ibm_spcr_with_explicit_status(self):
        body=b'<h1>IBM Classic CDC for z/OS 11.3</h1><table><tr><th>Operating System</th><th>Support Status</th></tr><tr><td>z/OS 3.2</td><td>Supported</td></tr></table>'
        c,o=extract_ibm_report_table(body,'https://www.ibm.com/a',{'IBM':[{'product':'IBM Classic CDC for z/OS','release':'11.3'}]},'2026')
        self.assertEqual((len(c),len(o)),(1,0))
    def test_consolidate_links_and_conflicts(self):
        basic=dict(vendor='Broadcom',product='ACF2',release='16.0',zos_version='3.2',ptf_id='LU15603',installation_status='Unknown')
        a=dict(basic,publication_status='Required',source_url='https://a');b=dict(basic,publication_status='Not stated',source_url='https://b')
        out=consolidate_ptfs([a,b]);self.assertEqual(len(out),1)
        self.assertEqual(out[0]['source_count'],2)
        self.assertIn('inconsistent',out[0]['publication_status'].lower())
    def test_source_quality(self):
        rows=[{'vendor':'BMC','url':'https://x','state':'Read','compatibility_rows':0,'ptf_rows':0}]
        obs=[{'vendor':'BMC','source_url':'https://x'}]
        self.assertIn('Evidence-only',source_quality(rows,obs)[0]['result_class'])

if __name__=='__main__':unittest.main()
