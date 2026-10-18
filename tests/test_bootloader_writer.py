from pathlib import Path
from unicorn import *
from unicorn.arm_const import *
import struct
import base64,gzip
root=Path(__file__).resolve().parents[1]
code=gzip.decompress(base64.decodebytes((root/'firmware/releases/hd-bootloader-writer.bin.gz.b64').read_bytes()))
image=bytes(range(256))*56
original=bytes([0xA5])*16384
import unittest
class WriterTests(unittest.TestCase):
 def test_writer_and_protection(self):
  for protected in [False,True]:
   u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
   u.mem_map(0x20000000,0x10000);u.mem_map(0xfe10000,0x4000);u.mem_map(0x40000000,0x100000)
   u.mem_write(0x20008000,code);u.mem_write(0x20000000,image);u.mem_write(0xfe10000,original)
   msc=0x400e0000
   u.mem_write(msc+0x1c,struct.pack('<I',8))
   u.mem_write(msc+0x90,struct.pack('<I',2 if protected else 0))
   state={'addr':0,'data':0,'pages':0}
   def write(u,access,addr,size,value,data):
    if addr==msc+0x10:state['addr']=value
    if addr==msc+0x18:state['data']=value
    if addr==msc+0xc:
     if value==2:
      assert 0xfe10800<=state['addr']<0xfe14000
      u.mem_write(state['addr'],b'\xff'*2048);state['pages']+=1
     if value==8:
      u.mem_write(state['addr'],struct.pack('<I',state['data']));state['addr']+=4
   def insn(u,pc,size,data):
    if bytes(u.mem_read(pc,2))==b'\x00\xbe':u.emu_stop()
   u.hook_add(UC_HOOK_MEM_WRITE,write);u.hook_add(UC_HOOK_CODE,insn)
   u.reg_write(UC_ARM_REG_MSP,0x20010000)
   u.emu_start(0x20008001,0,count=3000000)
   result=struct.unpack('<I',u.mem_read(0x20007000,4))[0]
   assert bytes(u.mem_read(0xfe10000,0x800))==original[:0x800]
   if protected:
    assert result==0xe001 and state['pages']==0
   else:
    assert result==0x4844424c and state['pages']==7
    assert bytes(u.mem_read(0xfe10800,0x3800))==image
  
