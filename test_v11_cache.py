import csv
import hashlib
import tempfile
import unittest
from pathlib import Path
from source_cache_v11 import ResponseCache, describe_document
from deep_scraper import DeepCrawler, source_quality

BMC_HTML=b'''<html><head><title>Support matrix</title></head><body>
<table><tr><th>Operating systems/ Mainframe</th><th>BMC Performance Predictor for Mainframes</th></tr>
<tr><td>z/OS 3.2</td><td>X</td></tr></table></body></html>'''

class TestSourceCache(unittest.TestCase):
    def test_cache_round_trip_and_immutable_content(self):
        with tempfile.TemporaryDirectory() as directory:
            cache=ResponseCache(Path(directory)/'source_cache')
            rec=cache.save('BMC','https://docs.bmc.com/example','https://docs.bmc.com/example',
                           'text/html',BMC_HTML,'2026-11-09T00:00:00Z')
            self.assertEqual(rec['sha256'],hashlib.sha256(BMC_HTML).hexdigest())
            self.assertEqual([(r['vendor'],data) for r,data in cache.entries()],[('BMC',BMC_HTML)])
            self.assertIn('BMC',cache.index.read_text())
            self.assertEqual(len(list((cache.root/'objects').iterdir())),1)
            # Corruption is skipped, not parsed or accepted as trusted evidence.
            (cache.payloads/rec['sha256']).write_bytes(b'corrupt')
            self.assertEqual(list(cache.entries()),[])

    def test_document_diagnostics(self):
        d=describe_document('BMC','https://docs.bmc.com/example','text/html',BMC_HTML,'abc','Saved')
        self.assertEqual(d['html_tables'],1)
        self.assertEqual(d['table_rows'],2)
        self.assertEqual(d['title'],'Support matrix')

    def test_offline_replay_evidence_only(self):
        with tempfile.TemporaryDirectory() as directory:
            crawler=DeepCrawler(Path(directory),{'BMC':[]})
            crawler.cache.save('BMC','https://docs.bmc.com/example','https://docs.bmc.com/example',
                               'text/html',BMC_HTML,'2026-11-09T00:00:00Z')
            result=crawler.reparse_cache()
            self.assertEqual(result['cached_documents'],1)
            self.assertEqual(result['compatibility_rows'],0)
            with (Path(directory)/'vendor_release_observations.csv').open(encoding='utf-8-sig') as f:
                observed=list(csv.DictReader(f))
            self.assertEqual(len(observed),1)
            self.assertEqual(observed[0]['zos_version'],'3.2')
            self.assertEqual(observed[0]['release'],'Not established')
            self.assertEqual(crawler.rows['vendor_page_diagnostics.csv'][0]['cache_status'],'Replayed')

    def test_unique_source_quality_counts(self):
        base={'vendor':'Broadcom','url':'https://ftpdocs.broadcom.com/test','state':'Read',
              'compatibility_rows':100,'ptf_rows':20}
        claim={'vendor':'Broadcom','source_url':base['url'],'product':'ACF2',
               'release':'16.0','zos_version':'3.2','compatibility':'Yes','source_excerpt':'row'}
        quality=source_quality([base],[],[claim,claim],[])
        self.assertEqual(quality[0]['raw_compatibility_rows'],100)
        self.assertEqual(quality[0]['unique_compatibility_rows'],1)
        self.assertEqual(quality[0]['unique_ptf_rows'],0)

if __name__=='__main__':unittest.main()
