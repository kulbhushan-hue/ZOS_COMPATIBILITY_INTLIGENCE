"""Offline tests for anchor extraction, status mapping, and preservation of snapshots."""
import sys
import types
from pathlib import Path
import tempfile
import unittest

# The extraction layer imports the original vendor_details module; replace only
# the Streamlit cache decorator in environments without Streamlit installed.
try:
    import streamlit
except ImportError:
    st=types.ModuleType('streamlit')
    st.cache_data=lambda **kwargs:(lambda func:func)
    sys.modules['streamlit']=st

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crawler import parse_broadcom_html
from store import save,latest,changes,record_error,jobs

HTML='''<html><body>
<table><tr><th>Product/Release</th><th>Z/OS V3R2</th><th>Z/OS V3R1</th><th>z/OS V2R5</th></tr>
<tr><td>ACF2 for z/OS 16.0</td><td>YES <a href="#a32">PTFs</a></td><td>YES</td><td>YES <a href="#more">Additional Information</a></td></tr>
<tr><td>Auditor for z/OS 12.0</td><td>In Progress</td><td>YES</td><td>YES</td></tr>
<tr><td>Balancing 1.1 (End Of Life)</td><td>NO</td><td>NO</td><td>NO</td></tr>
</table>
<section><h3 id="a32">Required PTF(s)</h3><p>Component CAX1G00 needs LU15603 and LU16693. CA.TargetSystem-RequiredService.z/OS.V3R2</p></section>
<section id="more"><h4>Additional Information</h4><p>Review SAF prerequisites before the migration.</p></section>
</body></html>'''

class CrawlerTests(unittest.TestCase):
    def test_parse_all_os_and_links(self):
        r=parse_broadcom_html(HTML)
        self.assertEqual(len(r),9)
        acf=next(x for x in r if x['product']=='ACF2 for z/OS' and x['zos_version']=='3.2')
        self.assertEqual(acf['vrm'],'16.0')
        self.assertEqual(acf['status'],'Yes')
        self.assertEqual(acf['ptfs'],['LU15603','LU16693'])
        self.assertIn('CAX1G00',acf['links'][0]['text'])
        self.assertEqual(next(x for x in r if x['product']=='Auditor for z/OS' and x['zos_version']=='3.2')['status'],'In Progress')
        self.assertEqual(next(x for x in r if x['product']=='Balancing' and x['zos_version']=='3.2')['status'],'No')
    def test_store_preserves_previous_and_changes(self):
        r=parse_broadcom_html(HTML)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'snapshot.sqlite3'
            a=save(r,{'source':'fixture'},path)
            self.assertEqual(a,1)
            self.assertFalse(changes(path=path))
            changed=[dict(x) for x in r]
            changed[0]['status']='No'
            save(changed,{'source':'fixture'},path)
            self.assertEqual(len(changes(path=path)),1)
            rows,snap=latest(path=path)
            self.assertEqual(rows[0]['source_url'].split('#')[0],r[0]['source_url'])
            record_error('Broadcom','simulated failure',path)
            rows2,snap2=latest(path=path)
            self.assertEqual(snap['id'],snap2['id'])
            self.assertEqual(jobs(path=path)[0]['result'],'Failed')

if __name__=='__main__':unittest.main()
