import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from deep_scraper import (DeepCrawler, extract_html, inventory_and_queue,
                          explicit_status, relevant_links, versions)

HTML=b'''<html><body><table><tr><th>Product</th><th>z/OS 3.2</th><th>z/OS 3.1</th></tr>
<tr><td>ACF2 for z/OS 16.0</td><td>Yes</td><td>No</td></tr></table>
<p>ACF2 for z/OS 16.0 z/OS 3.2 required PTFs LU15603 and LU16693; component CAX1G00.</p>
<a href="/support/compatibility/ptfs.html">PTF support details</a>
<a href="https://evil.example/login">other</a></body></html>'''

class TestDeepScraper(unittest.TestCase):
    def setUp(self):
        self.inv={'Broadcom':[{'product':'ACF2 for z/OS 16.0','release':'16.0'}]}
        self.url='https://www.broadcom.com/support/matrix'
    def test_table_and_local_ptf(self):
        c,p,e,n,s=extract_html(HTML,'Broadcom',self.url,self.inv,[], '2026-11-09T00:00:00Z')
        self.assertEqual({(x['zos_version'],x['compatibility']) for x in c},{('3.2','Yes'),('3.1','No')})
        self.assertEqual({x['ptf_id'] for x in p},{'LU15603','LU16693'})
        self.assertTrue(all(x['match_status']=='Exact inventory match' for x in c))
        self.assertGreaterEqual(len(e),4)
        self.assertEqual(n,1)
        self.assertEqual(relevant_links(s,self.url,'Broadcom',self.url),['https://www.broadcom.com/support/compatibility/ptfs.html'])
    def test_no_certification_from_mention(self):
        c,p,_,_,_=extract_html(b'<p>ACF2 for z/OS 16.0 supports z/OS 3.2 PTF LU12345</p>', 'Broadcom',self.url,self.inv,[], 't')
        self.assertEqual(c,[])
        self.assertEqual({x['ptf_id'] for x in p},{'LU12345'})
    def test_resume_and_errors(self):
        with tempfile.TemporaryDirectory() as d:
            cr=DeepCrawler(Path(d),self.inv,delay=0,depth=0,max_pages=1,respect_robots=False)
            cr.seed([{'vendor':'Broadcom','url':self.url,'contexts':[],'origin':'test'}])
            with patch('deep_scraper._get_public',return_value=(self.url,'text/html',HTML)):
                result=cr.run()
            self.assertEqual(result['processed_this_run'],1)
            self.assertEqual(result['compatibility_rows'],2)
            self.assertTrue((Path(d)/'all_vendor_extracted_ptfs.csv').is_file())
            cr2=DeepCrawler(Path(d),self.inv,delay=0,depth=0,max_pages=1,respect_robots=False)
            cr2.seed([{'vendor':'Broadcom','url':self.url,'contexts':[],'origin':'test'}])
            self.assertEqual(cr2.run()['processed_this_run'],0)
    def test_seed_all_products(self):
        root=Path(__file__).resolve().parents[1]
        urls,inventory=inventory_and_queue(root,root/'reference/vendor_product_source_worklist.csv')
        self.assertGreater(len(urls),30)
        self.assertIn('IBM',inventory)
        self.assertIn('Broadcom',inventory)
    def test_safe_status(self):
        self.assertEqual(explicit_status('Possibly yes'), '')
        self.assertEqual(explicit_status('YES'), 'Yes')
        self.assertEqual(versions('z/OS V3R2 and z/OS 3.1'), ['3.1','3.2'])
if __name__=='__main__':unittest.main()
