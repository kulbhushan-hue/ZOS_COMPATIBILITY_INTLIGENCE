import csv
import hashlib
import tempfile
import unittest
from pathlib import Path
from dynamic_capture_v12 import is_report_shell,candidate_rows
from source_cache_v11 import ResponseCache,describe_document

IBM='https://www.ibm.com/software/reports/compatibility/clarity-reports/report/html/osForProduct?deliverableId=ABC'
SHELL=b'<html><head><title>Report</title><script src="a.js"></script><script src="b.js"></script></head><body><div id="root">Loading...</div></body></html>'
RENDERED=b'<html><body><h1>Example product 7.1</h1><table><tr><th>OS</th><th>Status</th></tr><tr><td>z/OS 3.2</td><td>Supported</td></tr></table></body></html>'

class DynamicCaptureTests(unittest.TestCase):
    def test_ibm_report_shell_detected(self):
        self.assertTrue(is_report_shell(IBM,SHELL))
        d=describe_document('IBM',IBM,'text/html',SHELL,hashlib.sha256(SHELL).hexdigest(),'Cached')
        self.assertEqual(d['potential_dynamic_content'],'Yes')
    def test_other_vendor_not_assumed_dynamic(self):
        self.assertFalse(is_report_shell('https://example.com/',SHELL))
    def test_rendered_table_not_shell(self):
        self.assertFalse(is_report_shell(IBM,RENDERED))
    def test_capture_only_previously_read_ibm_urls(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.csv'
            with p.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=['vendor','url','state']);w.writeheader()
                w.writerows([{'vendor':'IBM','url':IBM,'state':'Read'},
                             {'vendor':'IBM','url':IBM+'2','state':'Blocked / failed'},
                             {'vendor':'BMC','url':'https://www.bmc.com','state':'Read'}])
            self.assertEqual(len(list(candidate_rows(p))),1)
    def test_latest_rendered_response_replaces_shell_in_replay(self):
        with tempfile.TemporaryDirectory() as td:
            c=ResponseCache(Path(td))
            c.save('IBM',IBM,IBM,'text/html',SHELL,'2026-01-01')
            c.save('IBM',IBM,IBM,'text/html; rendered-by-playwright',RENDERED,'2026-01-02')
            items=list(c.entries())
            self.assertEqual(len(items),1)
            self.assertEqual(items[0][1],RENDERED)
