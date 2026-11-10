import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vendor_assertions import extract_ibm_zos_requirements,extract_precisely_mfx_lifecycle,extract_precisely_ironstream_announcement,extract_precisely_service_pack
from quality import maintenance_availability,installation_status,per_ptf_statements
from multi_vendor import sources_for_vendors

class VendorEvidenceV2Tests(unittest.TestCase):
    def test_ibm_minimum_product_requirements_do_not_certify_installed_release(self):
        html=b'<table><tr><th>If you use this IBM product...</th><th>You need this product level (usually achieved with PTFs)</th></tr><tr><td>IBM CICS Transaction Server</td><td>6.2 with PTF UI12345</td></tr></table>'
        r=extract_ibm_zos_requirements(html,'https://www.ibm.com/docs/en/zos/3.2.0?topic=installation-software-requirements-running-zos-32')
        self.assertEqual(len(r),1);self.assertEqual(r[0]['compatibility'],'Not asserted')
        self.assertIn('UI12345',r[0]['required_level'])
    def test_precisely_mfx_minimum_is_not_3_2_certification(self):
        html=b'<table><tr><th>Release Designation</th><th>MFX Version Number</th><th>Release Date</th><th>Minimum z/OS</th></tr><tr><td>GA</td><td>3.1.8</td><td>07/08/2025</td><td>3.1</td></tr></table>'
        x=extract_precisely_mfx_lifecycle(html,'https://www.precisely.com/support/mfx-support-lifecycle-schedule/')
        self.assertEqual(x[0]['vrm'],'3.1.8');self.assertEqual(x[0]['zos_version'],'')
    def test_precisely_announcement_release_unspecified(self):
        html=b'<html><body>Ironstream for IBM Z Now Compatible with z/OS 3.2. Customers upgrading to z/OS 3.2.</body></html>'
        x=extract_precisely_ironstream_announcement(html,'https://community.precisely.com/discussion/ironstream-for-ibm-z-now-compatible-with-zos-32')
        self.assertEqual(x[0]['vrm'],'Not stated')
    def test_precisely_alphanumeric_ptf(self):
        html=b'<body>PTF ID SDF21QS Extend detectable IBM z/OS system versions to include z/OS v3.2.</body>'
        x=extract_precisely_service_pack(html,'https://community.precisely.com/discussion/ironstream-for-zos-v2112-service-pack-notice')
        self.assertEqual(x[0]['maintenance_id'],'SDF21QS')
    def test_not_installed_is_not_unavailable(self):
        self.assertEqual(installation_status('PTFs not installed'),'Not installed (source-reported)')
        self.assertNotEqual(maintenance_availability('PTFs not installed'),'Not available')
    def test_one_ptf_unavailable(self):
        x=per_ptf_statements('PTF LU16627 is not available.')
        self.assertEqual(x[0]['ptf_id'],'LU16627')
        self.assertEqual(x[0]['availability'],'Not available')

if __name__=='__main__':unittest.main()
