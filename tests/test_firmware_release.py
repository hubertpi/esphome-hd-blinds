"""Test release discovery against fake HTTP; no HA installation/network required."""
import pathlib
import subprocess
import sys
import unittest

class FirmwareReleaseTests(unittest.TestCase):
    def test_dynamic_release_checks_and_offline_retention(self):
        root=pathlib.Path(__file__).resolve().parents[1]
        script=r'''
import asyncio, importlib, sys, types
from enum import IntFlag
from pathlib import Path
package=types.ModuleType('release_test');package.__path__=[str(Path(sys.argv[1])/'custom_components/hd_blinds')]
sys.modules['release_test']=package
for name in ('homeassistant','homeassistant.components','homeassistant.components.update',
 'homeassistant.helpers','homeassistant.helpers.event','homeassistant.helpers.aiohttp_client',
 'homeassistant.exceptions'):
 sys.modules[name]=types.ModuleType(name)
class Features(IntFlag):INSTALL=1;PROGRESS=2
update=sys.modules['homeassistant.components.update']
update.UpdateEntity=type('UpdateEntity',(),{})
update.UpdateEntityFeature=Features
update.UpdateDeviceClass=types.SimpleNamespace(FIRMWARE='firmware')
sys.modules['homeassistant.exceptions'].HomeAssistantError=RuntimeError
sys.modules['homeassistant.helpers.event'].async_track_time_interval=lambda *args:lambda:None
manifest={'version':'0.3.2','bytes':64,'sha256':'a'*64,
 'url':'https://raw.githubusercontent.com/hubertpi/esphome-hd-blinds/main/test.gbl'}
class Response:
 def raise_for_status(self):pass
 async def json(self,**kwargs):return dict(manifest)
 async def __aenter__(self):return self
 async def __aexit__(self,*args):pass
class Session:
 failed=False
 def get(self,url):
  if self.failed:raise ConnectionError('offline')
  return Response()
session=Session()
sys.modules['homeassistant.helpers.aiohttp_client'].async_get_clientsession=lambda hass:session
entity=types.ModuleType('release_test.entity')
class BlindEntity:
 def __init__(self,coordinator,*args):self.coordinator=coordinator;self.hass=object();self.writes=0
 def async_write_ha_state(self):self.writes+=1
 @property
 def latest_version(self):return self._attr_latest_version
entity.BlindEntity=BlindEntity;sys.modules[entity.__name__]=entity
m=importlib.import_module('release_test.update')
async def test():
 e=m.BlindUpdate(types.SimpleNamespace())
 assert e.latest_version is None # no hardcoded latest version
 await e._async_check_release();assert e.latest_version=='0.3.2'
 manifest['version']='0.3.3';await e._async_check_release()
 assert e.latest_version=='0.3.3' # new firmware without an integration download
 session.failed=True;await e._async_check_release()
 assert e.latest_version=='0.3.3' # outage retains last successful metadata
 session.failed=False;manifest['version']='not-a-version'
 try:await e._fetch_manifest()
 except ValueError:pass
 else:raise AssertionError('Invalid version accepted')
 assert e.latest_version=='0.3.3'
 manifest['version']='0.3.4';manifest['bytes']=225284
 try:await e._fetch_manifest()
 except ValueError:pass
 else:raise AssertionError('Oversized update accepted')
 assert e.latest_version=='0.3.3'
asyncio.run(test())
'''
        subprocess.run([sys.executable,'-c',script,str(root)],check=True)
