import unittest
from safe_extract_v8 import extract_html_safe, valid_product_name, scoped_fixcat_version
from deep_scraper import unique_rows

class V9Accuracy(unittest.TestCase):
    def setUp(self):
        self.inventory={'Broadcom':[{'product':'ACF2 for z/OS','release':'16.0'}, {'product':'File Master Plus','release':'11.0'}],
                        'IBM':[{'product':'IBM Classic CDC for z/OS','release':'11.3'}]}
    def test_fake_product_headers_rejected(self):
        self.assertFalse(valid_product_name('YES PTFs Info'))
        self.assertFalse(valid_product_name('YES'))
        self.assertFalse(valid_product_name('NO Info'))
        self.assertTrue(valid_product_name('ACF2 for z/OS'))
    def test_fake_html_header_never_product(self):
        raw=b'<table><tr><td>z/OS</td><td>YES PTFs Info</td></tr><tr><td>z/OS V3R2</td><td>YES</td></tr></table>'
        comp,*_=extract_html_safe(raw,'Broadcom','https://ftpdocs.broadcom.com/a',self.inventory,[], '2026-11-09')
        self.assertEqual(comp,[])
    def test_valid_named_product_and_version_table(self):
        raw=b'<table><tr><th>Product</th><th>Release</th><th>z/OS V3R2</th></tr><tr><td>ACF2 for z/OS</td><td>16.0</td><td>YES</td></tr></table>'
        comp,*_=extract_html_safe(raw,'Broadcom','https://ftpdocs.broadcom.com/a',self.inventory,[], '2026-11-09')
        self.assertEqual(len(comp),1)
        self.assertEqual((comp[0]['product'],comp[0]['release'],comp[0]['zos_version']),('ACF2 for z/OS','16.0','3.2'))
    def test_fixcat_scope(self):
        self.assertEqual(scoped_fixcat_version('Fix Category: CA.TargetSystem-RequiredService.z/OS.V2R5'),(['2.5'],True))
        self.assertEqual(scoped_fixcat_version('Fix Category: CA.TargetSystem-RequiredService.JES3plus.V1R0 z/OS 2.2'),([],True))
        self.assertEqual(scoped_fixcat_version('z/OS V3R2'),([],False))
    def test_non_zos_fixcat_is_not_relabelled(self):
        raw=b'''<a href="#PTFLIST">PTFs</a><a name="PTFLIST"></a><p>File Master Plus 11.0</p>
          <p>Fix Category: CA.TargetSystem-RequiredService.JES3plus.V1R0 LU11796 z/OS V2R2</p>'''
        _,ptfs,*_=extract_html_safe(raw,'Broadcom','https://ftpdocs.broadcom.com/a',self.inventory,[], '2026-11-09')
        self.assertTrue(ptfs)
        self.assertEqual({p['zos_version'] for p in ptfs},{'Not stated'})
    def test_ibm_unassigned_ptfs_are_evidence_not_requirements(self):
        raw=b'<p>Maintenance APARs and PTFs UI28936 UI28937 are described in release notes.</p>'
        comps,ptfs,evidence,*_=extract_html_safe(raw,'IBM','https://www.ibm.com/docs/a',self.inventory,[], '2026-11-09')
        self.assertEqual((comps,ptfs),([],[]))
        self.assertEqual(len(evidence),2)
        self.assertTrue(all('Unassigned IBM' in x['evidence_kind'] for x in evidence))
    def test_dedupe_claim_preserves_first_source(self):
        rows=[{'vendor':'Broadcom','product':'ACF2','release':'16','zos_version':'3.2','ptf_id':'LU15603','source_url':'url','source_excerpt':'a'},
              {'vendor':'Broadcom','product':'ACF2','release':'16','zos_version':'3.2','ptf_id':'LU15603','source_url':'url','source_excerpt':'b'}]
        self.assertEqual(len(unique_rows(rows,('vendor','product','release','zos_version','ptf_id','source_url'))),1)
if __name__=='__main__':unittest.main()

class IBMReleaseTable(unittest.TestCase):
    def test_explicit_heading_and_os_row(self):
        inventory={'IBM':[{'product':'IBM Classic CDC for z/OS','release':'11.3'}]}
        body=b'<h1>IBM Classic CDC for z/OS 11.3</h1><table><tr><th>Operating system</th><th>Support status</th></tr><tr><td>z/OS 3.2</td><td>Supported</td></tr></table>'
        comp,*_=extract_html_safe(body,'IBM','https://www.ibm.com/docs/x',inventory,[],'2026')
        self.assertEqual([(x['release'],x['zos_version'],x['compatibility']) for x in comp],[('11.3','3.2','Yes')])
    def test_generic_heading_not_certification(self):
        inventory={'IBM':[{'product':'IBM Classic CDC for z/OS','release':'11.3'}]}
        body=b'<h1>IBM Software Requirements</h1><table><tr><th>Operating system</th><th>Support status</th></tr><tr><td>z/OS 3.2</td><td>Supported</td></tr></table>'
        comp,*_=extract_html_safe(body,'IBM','https://www.ibm.com/docs/x',inventory,[],'2026')
        self.assertFalse(comp)

class MultipleFixcats(unittest.TestCase):
    def test_two_fixcats_same_paragraph_not_cross_assigned(self):
        inventory={'Broadcom':[{'product':'File Master Plus','release':'11.0'}]}
        raw=b'''<a href="#PTFLIST">PTFs</a><a name="PTFLIST"></a><p>File Master Plus 11.0</p>
          <p>Fix Category: CA.TargetSystem-RequiredService.z/OS.V2R5 LU11111
             Fix Category: CA.TargetSystem-RequiredService.z/OS.V3R2 LU22222</p>'''
        _,ptfs,*_=extract_html_safe(raw,'Broadcom','https://ftpdocs.broadcom.com/a',inventory,[],'2026')
        pairs={(r['ptf_id'],r['zos_version']) for r in ptfs}
        self.assertEqual(pairs,{('LU11111','2.5'),('LU22222','3.2')})

class ExactReleaseBoundary(unittest.TestCase):
    def test_major_release_cannot_claim_minor(self):
        from safe_extract_v8 import explicit_section_identity
        inv={'Broadcom':[{'product':'Allocate DASD Space and Placement','release':'V12'}]}
        product,release=explicit_section_identity(['Allocate DASD Space and Placement 12.5 Fix Category: z/OS V3R2'], 'Broadcom',inv)
        self.assertNotEqual(release,'V12')
