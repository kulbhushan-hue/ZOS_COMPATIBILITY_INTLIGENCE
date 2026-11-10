import unittest
from vendor_facts_v14 import extract_document_facts
class Facts(unittest.TestCase):
 def test_precisely_ptfs_not_installed(self):
  html=b'<html><h1>Ironstream for z/OS v2.1.12 Service Pack Notice</h1><table><tr><th>PTF ID</th><th>Description</th></tr><tr><td>SDF21QS</td><td>Detect z/OS v3.2</td></tr></table></html>'
  f=extract_document_facts(html,'Precisely','https://community.precisely.com/discussion/example','today')
  self.assertEqual(f[0]['value'],'SDF21QS');self.assertEqual(f[0]['release'],'2.1.12');self.assertEqual(f[0]['zos_version'],'Not stated')
  self.assertNotIn('Installed',f[0]['verification'])
 def test_bmc_minimum_not_exact(self):
  html=b'<table><tr><th>Operating systems/ Mainframe</th><th>BMC Performance Predictor for Mainframes</th><th>Comments</th></tr><tr><td>z/OS 3.2</td><td>X</td><td>Support started in version 2.5.00</td></tr></table>'
  f=extract_document_facts(html,'BMC','https://docs.bmc.com/test','today')
  self.assertEqual(len(f),1);self.assertEqual(f[0]['release'],'Not established');self.assertEqual(f[0]['value'],'2.5.00')
 def test_ibm_shell_unverified(self):
  f=extract_document_facts(b'<html><title>IBM SPCR</title></html>','IBM','https://www.ibm.com/software/reports/compatibility/clarity-reports/report/html/osForProduct?x=1','today')
  self.assertEqual(len(f),1);self.assertIn('shell',f[0]['fact_type'].lower())
if __name__=='__main__':unittest.main()
