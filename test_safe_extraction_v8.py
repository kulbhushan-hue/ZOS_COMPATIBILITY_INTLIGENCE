import unittest
from deep_scraper import extract_html
from safe_extract_v8 import safe_install_status

ROOT='https://ftpdocs.broadcom.com/WebInterface/phpdocs/0/MSPSaccount/COMPAT/zos_compat.HTML'
INV={'Broadcom':[
 {'product':'ACF2 for z/OS 16.0','release':'16.0'},
 {'product':'CA 7','release':'12.0'},
 {'product':'Dispatch','release':'11.7'},
 {'product':'Earl','release':'6.1'}]}
class V8Regression(unittest.TestCase):
 def test_row_cannot_inherit_url_product(self):
  html=b'''<table><tr><th>Product</th><th>z/OS V3R2</th></tr>
  <tr><td>ACF2 for z/OS 16.0</td><td>YES</td></tr>
  <tr><td>CA 7 12.0</td><td>NO</td></tr></table>'''
  c,_,_,_,_=extract_html(html,'Broadcom',ROOT,INV,[('ACF2 for z/OS','16.0')],'t')
  self.assertEqual(len(c),2)
  self.assertEqual({(x['product'],x['compatibility']) for x in c},{('ACF2 for z/OS','Yes'),('CA 7','No')})
  self.assertEqual({x['match_status'] for x in c},{'Exact inventory match'})
 def test_no_fallback_if_unnamed_row(self):
  html=b'<table><tr><th>Product</th><th>z/OS V3R2</th></tr><tr><td></td><td>NO</td></tr></table>'
  c,_,_,_,_=extract_html(html,'Broadcom',ROOT,INV,[('ACF2 for z/OS','16.0')],'t')
  self.assertEqual(c,[])
 def test_ptf_need_to_install_unknown(self):
  self.assertEqual(safe_install_status('The following PTFs need to be installed: LU15603'), 'Unknown')
  self.assertEqual(safe_install_status('LU15603 has been installed'), 'Installed/applied (source-reported)')
  self.assertEqual(safe_install_status('LU15603 is not installed'), 'Not installed (source-reported)')
 def test_ptf_is_local(self):
  html=b'''<p>ACF2 for z/OS 16.0 z/OS V3R2 PTF LU15603 must be installed.</p>
  <p>CA 7 12.0 z/OS V3R2 PTF LU18026 has been installed.</p>'''
  _,p,_,_,_=extract_html(html,'Broadcom',ROOT,INV,[('ACF2 for z/OS','16.0')],'t')
  self.assertEqual({(x['product'],x['ptf_id']) for x in p},{('ACF2 for z/OS 16.0','LU15603'),('CA 7','LU18026')})
  self.assertEqual(next(x for x in p if x['ptf_id']=='LU15603')['installation_status'],'Unknown')
 def test_unnamed_pagewide_ptf_not_assigned(self):
  html=b'<p>z/OS 3.2 PTF LU99999 published as part of the general service report</p>'
  _,p,_,_,_=extract_html(html,'Broadcom',ROOT,INV,[('ACF2 for z/OS','16.0')],'t')
  self.assertFalse(p)
if __name__=='__main__':unittest.main()

class ConflictChecks(unittest.TestCase):
 def test_conflicts_are_flagged_not_resolved(self):
  from deep_scraper import conflicting_claims
  records=[{'vendor':'Broadcom','product':'ACF2 for z/OS','release':'16.0','zos_version':'3.2','compatibility':x,'source_url':f'https://source/{i}'} for i,x in enumerate(['Yes','No'])]
  conflicts=conflicting_claims(records)
  self.assertEqual(len(conflicts),1)
  self.assertEqual(conflicts[0]['observed_statuses'],'No; Yes')
  self.assertEqual(len(records),2)

class InlineAnchorAndPdf(unittest.TestCase):
 def test_linked_ptf_fixcat_and_compatibility(self):
  html=b'''<table><tr><th>Product</th><th>z/OS V3R2</th></tr>
  <tr><td>ACF2 for z/OS 16.0</td><td>YES <a href="#ACF160_PTFLIST">PTFs</a></td></tr></table>
  <a name="ACF160_PTFLIST"></a><h3>ACF2 for z/OS 16.0</h3>
  <p>Fix Category: CA.TargetSystem-RequiredService.z/OS.V3R2</p>
  <p>PTFs need to be installed: LU15603 LU16693</p><a name="NEXT"></a>
  <h3>CA 7 12.0</h3><p>LU18026</p>'''
  c,p,_,_,_=extract_html(html,'Broadcom',ROOT,INV,[], 't')
  self.assertEqual([(x['product'],x['compatibility']) for x in c],[('ACF2 for z/OS','Yes')])
  self.assertEqual({(x['zos_version'],x['ptf_id']) for x in p},{('3.2','LU15603'),('3.2','LU16693')})
  self.assertTrue(all(x['installation_status']=='Unknown' for x in p))
 def test_pdf_unnamed_ptf_not_assigned_from_url_context(self):
  from safe_extract_v8 import explicit_line_identity
  self.assertEqual(explicit_line_identity('Broadcom','CA 7 12.0 requires LU18026',INV),('CA 7','12.0'))
  self.assertEqual(explicit_line_identity('Broadcom','General PTF LU18026',INV),('',''))
