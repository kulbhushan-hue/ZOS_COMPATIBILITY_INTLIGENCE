import sys, unittest
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from multi_vendor import extract_bmc_support_matrix, reconcile_observations, sources_for_vendors
from vendor_assertions import extract_explicit_vendor_release_table, extract_ibm_zos_requirements

class V3Tests(unittest.TestCase):
    def test_rocket_requires_explicit_product_release_and_os(self):
        html=b'<table><tr><th>Product</th><th>Release</th><th>z/OS 3.2</th><th>z/OS 3.1</th></tr><tr><td>Rocket Tool</td><td>4.2</td><td>Yes</td><td>No</td></tr></table>'
        x=extract_explicit_vendor_release_table('Rocket',html,'https://www.rocketsoftware.com/doc')
        self.assertEqual(len(x),2)
        self.assertEqual(x[0]['vrm'],'4.2')
        self.assertEqual(x[0]['zos_version'],'3.2')
        self.assertEqual(x[0]['compatibility'],'Yes')
    def test_generic_marketing_not_certification(self):
        self.assertFalse(extract_explicit_vendor_release_table('ASG',b'<p>Supports z/OS 3.2 and many products</p>','https://www.rocketsoftware.com'))
    def test_ibm_extracts_ptfs_without_certifying_release(self):
        html=b'<table><tr><th>IBM product</th><th>Required level</th></tr><tr><td>IBM Tool</td><td>Version 7 with PTF UI12345</td></tr></table>'
        x=extract_ibm_zos_requirements(html,'https://www.ibm.com/docs/en/zos/3.2.0?topic=installation-software-requirements-running-zos-32')
        self.assertEqual(x[0]['maintenance_ids'],'UI12345')
        self.assertEqual(x[0]['compatibility'],'Not asserted')
    def test_exact_match_only(self):
        df=pd.DataFrame([{'vendor':'Rocket','product':'Rocket Tool','vrm':'4.2'}])
        a={'vendor':'Rocket','product':'Rocket Tool','vrm':'4.2','zos_version':'3.2','compatibility':'Yes','evidence_level':'Explicit vendor table: product, release, z/OS; manual source verification recommended'}
        b=dict(a,vrm='Not stated')
        x=reconcile_observations([a,b],df)
        self.assertEqual(x[0]['matrix_promotion'],'Eligible for manual review')
        self.assertEqual(x[1]['matrix_promotion'],'Evidence only — not promoted')
    def test_bmc_support_release_not_inferred(self):
        html=b'<table><tr><th>Operating systems/ Mainframe</th><th>BMC Performance Predictor</th><th>Comments</th></tr><tr><td>z/OS 3.2</td><td>X</td><td>Support started in version 2.5.00</td></tr></table>'
        x=extract_bmc_support_matrix(html,'https://docs.bmc.com/test')
        self.assertEqual(len(x),1)
        self.assertEqual(x[0]['vrm'],'Not stated')
        self.assertIn('2.5.00',x[0]['required_level'])
if __name__=='__main__':unittest.main()
