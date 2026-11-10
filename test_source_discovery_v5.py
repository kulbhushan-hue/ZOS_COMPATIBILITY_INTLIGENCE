"""V5 bounded official source discovery tests. Network is mocked."""
import sys, unittest
from pathlib import Path
from unittest.mock import patch
import requests
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from multi_vendor import discover_compatibility_links, audit_vendor

class SourceDiscoveryV5(unittest.TestCase):
    def test_only_explicit_official_links(self):
        html=b'''<a href="https://docs.bmc.com/xwiki/Compatibility-matrix">z/OS Compatibility Matrix</a>
          <a href="https://evil.example.com/matrix">Compatibility Matrix</a>
          <a href="https://docs.bmc.com/marketing">New products</a>'''
        result=discover_compatibility_links(html,'https://www.bmc.com/support/resources/', 'BMC')
        self.assertEqual(len(result),1)
        self.assertIn('docs.bmc.com',result[0]['url'])
    def test_one_hop_and_no_extra_product_assumption(self):
        hub=b'<a href="https://docs.bmc.com/xwiki/Compatibility-matrix">z/OS Compatibility Matrix</a>'
        table=b'''<table><tr><th>Operating systems/ Mainframe</th><th>BMC Performance Predictor</th></tr>
             <tr><td>z/OS 3.2</td><td>X</td></tr></table>'''
        def fake_get(session,url,vendor,timeout):
            if url.endswith('/resources/'):
                return url,'text/html',hub
            if 'Compatibility-matrix' in url:
                return url,'text/html',table
            raise AssertionError('Unexpected URL: '+url)
        with patch('multi_vendor._get_public',side_effect=fake_get):
            rows=audit_vendor('BMC',[{'url':'https://www.bmc.com/support/resources/','origin':'Curated'}],[],session=requests.Session())
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[1]['origin'],'Discovered on official vendor source')
        self.assertEqual(rows[1]['assertions'][0]['vrm'],'Not stated')
        self.assertEqual(rows[1]['assertions'][0]['compatibility'],'Yes')
    def test_no_automated_followup_for_generic_website(self):
        with patch('multi_vendor._get_public',return_value=('https://www.rocketsoftware.com/', 'text/html',b'<a href="/about">About</a>')):
            rows=audit_vendor('Rocket',[{'url':'https://www.rocketsoftware.com/','origin':'Curated'}],[],session=requests.Session())
        self.assertEqual(len(rows),1)
    def test_discovery_disabled(self):
        with patch('multi_vendor._get_public',return_value=('https://www.bmc.com/resources/', 'text/html',b'<a href="https://docs.bmc.com/matrix">Compatibility matrix</a>')):
            rows=audit_vendor('BMC',[{'url':'https://www.bmc.com/resources/','origin':'Curated'}],[],session=requests.Session(),follow_discovered=False)
        self.assertEqual(len(rows),1)

if __name__=='__main__':unittest.main()
