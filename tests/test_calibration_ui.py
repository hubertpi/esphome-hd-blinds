"""Exercise flow ordering and cover percentage mapping without a HA install."""
import pathlib
import subprocess
import sys
import unittest

class CalibrationUITests(unittest.TestCase):
    def test_flow_and_cover_contract(self):
        root=pathlib.Path(__file__).resolve().parents[1]
        script=r'''
import asyncio, importlib, sys, types
from enum import IntFlag
from unittest.mock import AsyncMock, patch
from pathlib import Path
package=types.ModuleType('calibration_test')
package.__path__=[str(Path(sys.argv[1])/'custom_components/hd_blinds')]
sys.modules['calibration_test']=package
for name in ('homeassistant','homeassistant.config_entries','homeassistant.helpers',
             'homeassistant.components','homeassistant.components.cover'):
 sys.modules[name]=types.ModuleType(name)
class Flow:
 config_entry=None
 def async_show_form(self,**kw):return dict(type='form',**kw)
 def async_show_menu(self,**kw):return dict(type='menu',**kw)
 def async_create_entry(self,**kw):return dict(type='create_entry',**kw)
 def async_abort(self,**kw):return dict(type='abort',**kw)
sys.modules['homeassistant.config_entries'].OptionsFlow=Flow
sys.modules['homeassistant.helpers'].selector=types.SimpleNamespace()
class Features(IntFlag):OPEN=1;CLOSE=2;STOP=4;SET_POSITION=8
cover=sys.modules['homeassistant.components.cover']
cover.CoverEntity=type('CoverEntity',(),{})
cover.CoverEntityFeature=Features
cover.CoverDeviceClass=types.SimpleNamespace(SHADE='shade')
entity=types.ModuleType('calibration_test.entity')
class Entity:
 def __init__(self,coordinator,*args):self.coordinator=coordinator
entity.BlindEntity=Entity;sys.modules[entity.__name__]=entity
p=importlib.import_module('calibration_test.protocol')
f=importlib.import_module('calibration_test.calibration_flow')
c=importlib.import_module('calibration_test.cover')
async def test():
 status=types.SimpleNamespace(flags=p.CAL_CAPABLE,position=123,percent=255,state=0)
 blind=types.SimpleNamespace(send=AsyncMock(),status=status,refresh_status=AsyncMock(return_value=status))
 coordinator=types.SimpleNamespace(data=status,blind=blind,
   async_set_updated_data=lambda value:setattr(coordinator,'data',value))
 flow=f.BlindCalibrationFlow()
 flow.config_entry=types.SimpleNamespace(runtime_data=coordinator)
 assert (await flow.async_step_init())['type']=='form'
 assert not blind.send.await_count # opening the config screen never moves the motor
 assert (await flow.async_step_init({}))['step_id']=='upper'
 assert blind.send.await_args.args==(p.Opcode.CALIBRATE_BEGIN,0)
 with patch.object(f.asyncio,'sleep',AsyncMock()):
  result=await flow.async_step_pulse_down()
 assert result['step_id']=='upper'
 assert blind.send.await_args.args==(p.Opcode.JOG_DOWN,250)
 assert (await flow.async_step_set_upper())['step_id']=='lower'
 assert blind.send.await_args.args==(p.Opcode.CALIBRATE_UPPER,0)
 assert (await flow.async_step_set_lower())['type']=='create_entry'
 assert blind.send.await_args.args==(p.Opcode.CALIBRATE_LOWER,0)
 # Failed commit must stay on lower page, never falsely report success.
 blind.send.side_effect=RuntimeError('Travel must be positive')
 result=await flow.async_step_set_lower()
 assert result['type']=='menu' and result['step_id']=='lower'
 blind.send.side_effect=None
 shade=c.BlindCover(coordinator)
 assert shade.current_cover_position is None
 assert not shade.supported_features & Features.SET_POSITION
 status.flags=p.CAL_CAPABLE|p.CALIBRATED|p.POSITION_VALID;status.percent=10
 assert shade.current_cover_position==10
 assert shade.supported_features & Features.SET_POSITION
 await shade.async_set_cover_position(position=10)
 assert blind.send.await_args.args==(p.Opcode.SET_POSITION,10)
 status.flags &= ~p.POSITION_VALID
 assert shade.current_cover_position is None
asyncio.run(test())
'''
        subprocess.run([sys.executable,'-c',script,str(root)],check=True)
