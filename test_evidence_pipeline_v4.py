import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evidence_pipeline import latest_unique_observations,review_candidates,observation_match,classification,canonical_url
from vendor_assertions import extract_ibm_zos_requirements,extract_explicit_vendor_release_table
from multi_vendor import reconcile_observations
from quality import maintenance_availability
import pandas as pd

class EvidencePipelineV4Tests(unittest.TestCase):
    def test_repeated_refresh_is_deduplicated_and_latest_kept(self):
        obs={'vendor':'Precisely','product':'MFX for z/OS','vrm':'3.1.8','zos_version':'','source_url':'https://www.precisely.com/support/mfx-support-lifecycle-schedule/','required_level':'Minimum z/OS 3.1','evidence_level':'Minimum OS only'}
        audits=[{'vendor':'Precisely','source_url':obs['source_url'],'checked_at':f'2026-11-09T0{i}:00:00Z','assertions':[obs]} for i in range(1,4)]
        found=latest_unique_observations(audits)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['source_checked_at'],'2026-11-09T03:00:00Z')
    def test_precisely_candidate_is_review_only(self):
        inv=[{'vendor':'Precisely','product':'Syncsort MFX','vrm':'3.1.8'}]
        o={'vendor':'Precisely','product':'MFX for z/OS','vrm':'3.1.8','zos_version':'','compatibility':'Not asserted','evidence_level':'Minimum OS only'}
        self.assertIsNone(observation_match(o,inv))
        self.assertEqual(len(review_candidates(o,inv)),1)
        result=reconcile_observations([o],pd.DataFrame(inv))[0]
        self.assertIn('Syncsort MFX',result['review_candidate'])
        self.assertIn('not promoted',result['matrix_promotion'])
    def test_no_assumed_release_if_not_stated(self):
        self.assertIsNone(observation_match({'vendor':'BMC','product':'BMC Performance Predictor','vrm':'Not stated'},[{'vendor':'BMC','product':'BMC Performance Predictor','vrm':'2.5'}]))
    def test_status_not_installed_is_not_unavailable(self):
        self.assertIn('Availability unknown',maintenance_availability('PTFs not installed'))
    def test_anchored_url_fragment_preserved(self):
        self.assertTrue(canonical_url('https://EXAMPLE.COM/a/#PTF123').endswith('#PTF123'))
    def test_ibm_minimum_level_is_not_certification(self):
        html=b'<table><tr><th>If you use this IBM product...</th><th>You need this product level (usually achieved with PTFs)</th></tr><tr><td>IBM Tivoli Event Pump for z/OS</td><td>Version 4.2.2 with PTF UA92963</td></tr></table>'
        obs=extract_ibm_zos_requirements(html,'https://www.ibm.com/docs/en/zos/3.2.0?topic=installation-software-requirements-running-zos-32')
        self.assertEqual(obs[0]['maintenance_ids'],'UA92963')
        self.assertEqual(obs[0]['compatibility'],'Not asserted')
    def test_rocket_exact_release_requires_review(self):
        html=b'<table><tr><th>Product</th><th>Version</th><th>z/OS 3.2</th></tr><tr><td>Rocket Widget</td><td>4.2</td><td>Yes</td></tr></table>'
        obs=extract_explicit_vendor_release_table('Rocket',html,'https://www.rocketsoftware.com/documentation')
        self.assertEqual(len(obs),1)
        inv=[{'vendor':'Rocket','product':'Rocket Widget','vrm':'4.2'}]
        self.assertEqual(classification(obs[0],observation_match(obs[0],inv)),'Exact release claim — manual review required')
if __name__=='__main__':unittest.main()

class UploadedDocumentTests(unittest.TestCase):
    def test_bmc_offline_html_matrix(self):
        from multi_vendor import audit_uploaded_document
        html=b'<table><tr><th>Operating systems/ Mainframe</th><th>BMC Performance Predictor</th><th>Comments</th></tr><tr><td>z/OS 3.2</td><td>X</td><td>Support started in version 2.5.00</td></tr></table>'
        result=audit_uploaded_document('BMC','matrix.html',html,[],'https://docs.bmc.com/example')
        self.assertEqual(result['state'],'Read')
        self.assertEqual(len(result['assertions']),1)
        self.assertEqual(result['assertions'][0]['vrm'],'Not stated')
        self.assertIn('not live',result['origin'].lower())
    def test_offline_rejects_wrong_domain(self):
        from multi_vendor import audit_uploaded_document
        with self.assertRaises(ValueError):
            audit_uploaded_document('IBM','requirements.html',b'<p>IBM requirements</p>',[],'https://unknown.example')
