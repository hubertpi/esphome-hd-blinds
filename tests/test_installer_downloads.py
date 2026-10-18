"""Check initial migration can fetch either verified main-flash image format."""
import base64
import gzip
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('hd_install',ROOT/'tools/install_bootloader.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)

class InstallerDownloadTests(unittest.TestCase):
 def test_bootstrap_and_original_artifact_filenames(self):
  def fetch(url,**kwargs):
   return io.BytesIO((ROOT/'firmware/releases'/url.rsplit('/',1)[-1]).read_bytes())
  with patch.object(installer.urllib.request,'urlopen',side_effect=fetch):
   for name in ['hd-bootloader-stage2','hd-bootloader-writer','hd-blind-bench','hd-ota-bootstrap']:
    with self.subTest(name=name):
     data=installer.download('pinned',name)
     meta=json.loads((ROOT/'firmware/releases'/f'{name}.json').read_text())
     self.assertEqual(len(data),meta['bytes'])
     self.assertEqual(installer.sha(data),meta['sha256'])
 def test_corrupt_bootstrap_is_rejected(self):
  def fetch(url,**kwargs):
   if url.endswith('.json'):
    return io.BytesIO((ROOT/'firmware/releases/hd-ota-bootstrap.json').read_bytes())
   return io.BytesIO(base64.encodebytes(gzip.compress(b'wrong image')))
  with patch.object(installer.urllib.request,'urlopen',side_effect=fetch):
   with self.assertRaisesRegex(RuntimeError,'Checksum mismatch'):
    installer.download('pinned','hd-ota-bootstrap')
