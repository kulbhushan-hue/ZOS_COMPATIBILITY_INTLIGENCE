import csv
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from vendor_content_v13 import extract_v13
import auto_scrape_v13

class VendorContentV13Tests(unittest.TestCase):
    def test_bmc_real_matrix_minimum_not_inventory_certification(self):
        html=b'''<table><tr><th>Operating systems/ Mainframe</th><th>BMC Performance Predictor for Mainframes</th><th>BMC Performance Analyzer for Mainframes</th><th>Comments</th></tr>
        <tr><td>z/OS 3.2</td><td>X</td><td>X</td><td>Support started in version 2.5.00</td></tr></table>'''
        c,o,p=extract_v13(html,'BMC','https://docs.bmc.com/xwiki/example',{'BMC':[{'product':'BMC Performance Predictor for Mainframes','release':'2.3.00'}]},'2026')
        self.assertFalse(c or p)
        self.assertEqual(len(o),2)
        self.assertEqual({x['zos_version'] for x in o},{'3.2'})
        self.assertTrue(all('2.5.00' in x['reason'] for x in o))

    def test_precisely_mfx_minimum_not_32_certification(self):
        html=b'''<table><tr><th>Release Designation</th><th>MFX Version Number</th><th>Release Date</th><th>Minimum z/OS</th></tr>
        <tr><td>GA</td><td>3.1.8</td><td>07/08/2025</td><td>3.1</td></tr></table>'''
        c,o,p=extract_v13(html,'Precisely','https://www.precisely.com/support/mfx-support-lifecycle-schedule/',{},'2026')
        self.assertFalse(c or p)
        self.assertEqual((o[0]['product'],o[0]['release'],o[0]['zos_version']),('MFX for z/OS','3.1.8','3.1'))
        self.assertNotIn('3.2',[x['zos_version'] for x in o])

    def test_precisely_ironstream_announcement_release_unknown(self):
        html=b'''<h1>Ironstream for IBM Z Now Compatible with z/OS 3.2</h1><p>Ironstream for IBM Z is now compatible with IBM z/OS 3.2.</p>'''
        c,o,p=extract_v13(html,'Precisely','https://community.precisely.com/discussion/ironstream-for-ibm-z-now-compatible-with-zos-32',{},'2026')
        self.assertEqual((len(c),len(o),len(p)),(0,1,0))
        self.assertEqual(o[0]['release'],'Not established')

    def test_precisely_ptf_without_inventory_stays_evidence_only(self):
        html=b'''<h1>Ironstream for z/OS v2.1.12 Service Pack Notice</h1>
        <table><tr><th>PTF ID</th><th>Description</th></tr>
        <tr><td>SDF21QS</td><td>Extend detectable IBM z/OS system versions to include z/OS v3.2.</td></tr>
        <tr><td>SDF21QT</td><td>Ensure connection and disconnection messages are consistently generated.</td></tr></table>'''
        c,o,p=extract_v13(html,'Precisely','https://community.precisely.com/discussion/ironstream-for-zos-v2112-service-pack-notice',{},'2026')
        self.assertFalse(c or p)
        self.assertEqual({x['assertion'] for x in o},{'SDF21QS','SDF21QT'})
        self.assertEqual({x['zos_version'] for x in o},{'3.2','Not stated'})
        c,o,p=extract_v13(html,'Precisely','https://community.precisely.com/discussion/ironstream-for-zos-v2112-service-pack-notice',{'Precisely':[{'product':'Ironstream for z/OS','release':'2.1.12'}]},'2026')
        self.assertEqual(len(p),2)
        self.assertTrue(all(x['installation_status']=='Unknown' for x in p))

    def test_vanguard_tested_range_only_evidence(self):
        html=b'''<table><tr><th>Vanguard Product</th><th>Version</th><th>Minimum Tested z/OS</th><th>Maximum Tested z/OS</th></tr>
        <tr><td>Vanguard Security Solutions</td><td>3.1</td><td>2.5</td><td>3.2</td></tr></table>'''
        c,o,p=extract_v13(html,'VANGUARD Integrity Prof.','https://www.go2vanguard.com/product-support-eol-schedule/',{},'2026')
        self.assertFalse(c or p)
        self.assertEqual({x['zos_version'] for x in o},{'2.5','3.1','3.2'})

    def test_ibm_error_page_never_compatible(self):
        c,o,p=extract_v13(b'<h1>Unable to create Software Product Compatibility Reports</h1><p>No product data found.</p>','IBM','https://www.ibm.com/software/reports/compatibility/clarity-reports/report/html/osForProduct',{},'2026')
        self.assertFalse(c or o or p)

    def test_streamlit_startup_runs_nonblocking_with_two_commands(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'reference').mkdir()
            (root/'reference'/'vendor_sources_v13.csv').write_text('Vendor,URL\n')
            with patch('deep_scraper.main') as fake:
                auto_scrape_v13._run(root,False,2)
                self.assertTrue(fake.called)
            status=json.loads((root/'exports/deep/auto_scrape_status.json').read_text())
            self.assertEqual(status['state'],'Completed')
            self.assertFalse((root/'exports/deep/.auto_scrape.lock').exists())

if __name__=='__main__':unittest.main()

class AdditionalVendorEvidenceTests(unittest.TestCase):
 def test_action_software_version_range_not_certified(self):
  html=b'''<table><tr><th>Release</th><th>General Availability</th><th>Maintenance Level</th><th>End of Service</th><th>System Compatibility</th></tr>
  <tr><td>eventACTION 8.08</td><td>2025-02-06</td><td>8.08.24</td><td>2030-03-31</td><td>z/OS 2.1 - z/OS 3.2</td></tr></table>'''
  c,o,p=extract_v13(html,'Action Software International','https://actionsoftware.com/support-form/release-history/',{},'2026')
  self.assertFalse(c or p)
  self.assertEqual({x['zos_version'] for x in o},{'2.5','3.1','3.2'})
  self.assertEqual({x['release'] for x in o},{'8.08'})
 def test_rocket_announcement_no_specific_version(self):
  html=b'<h1>TMON Modernization 2025: AI and Data Streaming</h1><p>TMON support for IBM z17 and IBM z/OS 3.2.</p>'
  c,o,p=extract_v13(html,'Rocket','https://www.rocketsoftware.com/en-us/events/tmon-modernization-2025-ai-and-data-streaming',{},'2026')
  self.assertFalse(c or p)
  self.assertEqual((len(o),o[0]['release']),(1,'Not established'))
