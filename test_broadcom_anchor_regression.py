"""Regression coverage for the user's 89-row PTF report with no extracted IDs."""
import sys
import types
import unittest
from pathlib import Path
try:
    import streamlit  # noqa
except ImportError:
    st=types.ModuleType('streamlit')
    st.cache_data=lambda **kwargs:(lambda f:f)
    sys.modules['streamlit']=st
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crawler import parse_broadcom_html, _anchor_context, BROADCOM_URL
from bs4 import BeautifulSoup

class RealisticBroadcomAnchors(unittest.TestCase):
    def sample(self):
        return '''<html><body>
        <table><tr><th>Product/Release</th><th>Z/OS V3R2</th><th>Z/OS V3R1</th><th>z/OS V2R5</th></tr>
        <tr><td>ACF2 for z/OS 16.0</td>
          <td>YES <a href="#IN000135_ACF160_PTFLIST">PTFs</a></td>
          <td>YES <a href="#IN000119_ACF160_PTFLIST">PTFs</a></td>
          <td>YES <a href="#IN000098_ACF160_PTFLIST">PTFs</a></td></tr>
        <tr><td>Dispatch 11.6</td><td>YES <a href="#IN000135_DSP116_PTFLIST">PTFs</a></td><td>YES</td><td>YES</td></tr>
        <tr><td>Auditor for z/OS 12.1</td><td>YES <a href="#IN000135_AUD121_PTFLIST">PTFs</a></td><td>YES</td><td>YES</td></tr>
        </table>
        <h2>Required PTF(s)</h2>
        <div class="details"><a name="IN000135_ACF160_PTFLIST"></a>
          <h4>ACF2 for z/OS 16.0</h4><p>Fix Category: CA.TargetSystem-RequiredService.z/OS.V3R2</p>
          <div id="unrelated-layout-id"><table><tr><th>FMID</th><th>PTFs</th></tr>
          <tr><td>CAX1G00</td><td><ul><li>LU15603</li><li>LU16693</li></ul></td></tr></table></div>
        </div>
        <div><a id="IN000119_ACF160_PTFLIST"></a><h4>ACF2 for z/OS 16.0</h4>
        <p>Fix Category: CA.TargetSystem-RequiredService.z/OS.V3R1</p>
        <table><tr><td>CAX1G00</td><td>LU09157 LU16693</td></tr><tr><td>CAX1G01</td><td>LU10139</td></tr></table></div>
        <a name="IN000098_ACF160_PTFLIST"></a><h4>ACF2 for z/OS 16.0</h4>
        <p>Fix Category: CA.TargetSystem-RequiredService.z/OS.V2R5</p><p>LU00866 LU06315 LU10561 LU12765</p>
        <a name="IN000135_DSP116_PTFLIST"></a><h4>Dispatch 11.6</h4>
        <p>Fix Category: CA.TargetSystem-RequiredService.z/OS.V3R2</p>
        <table><tr><td>CADSB60</td><td>LU18026</td></tr><tr><td>CADSB62</td><td>LU18024</td></tr></table>
        <a name="IN000135_AUD121_PTFLIST"></a><p>Auditor for z/OS 12.1 CAJ0C10 LU15606</p>
        </body></html>'''

    def test_realistic_broadcom_nested_details(self):
        records=parse_broadcom_html(self.sample())
        get=lambda p,v: next(r for r in records if r['display_name']==p and r['zos_version']==v)
        self.assertEqual(get('ACF2 for z/OS 16.0','3.2')['ptfs'], ['LU15603','LU16693'])
        self.assertEqual(get('ACF2 for z/OS 16.0','3.1')['ptfs'], ['LU09157','LU10139','LU16693'])
        self.assertEqual(get('ACF2 for z/OS 16.0','2.5')['ptfs'], ['LU00866','LU06315','LU10561','LU12765'])
        self.assertEqual(get('Dispatch 11.6','3.2')['ptfs'], ['LU18024','LU18026'])
        self.assertEqual(get('Auditor for z/OS 12.1','3.2')['ptfs'], ['LU15606'])
        self.assertNotIn('LU18026', get('ACF2 for z/OS 16.0','2.5')['ptfs'])
        self.assertNotIn('LU16693', get('Dispatch 11.6','3.2')['ptfs'])
        self.assertEqual(get('ACF2 for z/OS 16.0','3.2')['links'][0]['extraction_status'],'Bounded anchor section')

    def test_missing_anchor_reports_no_claim(self):
        soup=BeautifulSoup('<html><a name="IN000135_OTHER"></a><p>LU99999</p></html>', 'html.parser')
        _,text,status=_anchor_context(soup,'#IN000135_ACF160_PTFLIST',BROADCOM_URL)
        self.assertEqual(text,'')
        self.assertEqual(status,'Anchor target not found in document')

if __name__=='__main__':unittest.main()
