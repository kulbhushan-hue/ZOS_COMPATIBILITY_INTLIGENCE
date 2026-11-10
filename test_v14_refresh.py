import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from auto_scrape_v13 import _run
class Refresh(unittest.TestCase):
 def test_finished_checkpoint_restarts_fresh(self):
  with TemporaryDirectory() as d:
   root=Path(d);e=root/'exports/deep';e.mkdir(parents=True)
   (e/'deep_scrape_checkpoint.json').write_text('{"seen": [["IBM", "https://example.com"]], "queue": []}')
   (root/'reference').mkdir()
   (root/'reference/vendor_sources_v13.csv').write_text('Vendor,URL\n')
   import deep_scraper
   with patch.object(deep_scraper,'main') as fake:
    _run(root,False,200)
   self.assertIn('--fresh',fake.call_args.args[0])
 def test_pending_checkpoint_resumes(self):
  with TemporaryDirectory() as d:
   root=Path(d);e=root/'exports/deep';e.mkdir(parents=True)
   (e/'deep_scrape_checkpoint.json').write_text('{"seen": [], "queue": [{"vendor":"IBM","url":"https://www.ibm.com"}]}')
   (root/'reference').mkdir()
   (root/'reference/vendor_sources_v13.csv').write_text('Vendor,URL\n')
   import deep_scraper
   with patch.object(deep_scraper,'main') as fake:
    _run(root,False,200)
   self.assertNotIn('--fresh',fake.call_args.args[0])
