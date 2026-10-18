"""Control-flow checks with factory hardware functions stubbed, not hardware validation."""
import importlib.util
from pathlib import Path
import struct
import unittest

spec = importlib.util.spec_from_file_location("motor_bench", Path(__file__).parents[1] / "tools/motor_bench.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
try:
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
    from unicorn.arm_const import UC_ARM_REG_MSP, UC_ARM_REG_R0, UC_ARM_REG_R9, UC_ARM_REG_R11
    HAVE_UNICORN = True
except ImportError:
    HAVE_UNICORN = False


@unittest.skipUnless(HAVE_UNICORN, "Install unicorn for payload emulation")
class MotorBenchFlow(unittest.TestCase):
    def emulate(self, duty, overflow=True):
        u = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        for address, size in [(0, 0x80000), (0x20000000, 0x10000),
                              (0xe0000000, 0x10000), (0x40018000, 0x1000)]:
            u.mem_map(address, size)
        data = bench.payload(duty)
        u.mem_write(0x2000f000, data)
        for address in [0x105f4, 0x10718]:
            u.mem_write(address, b"\x70\x47")  # bx lr: stub original functions
        u.mem_write(0x4001801c, struct.pack("<I", 120))
        u.mem_write(0x4001806c, struct.pack("<I", 60))
        u.mem_write(0x4001800c, struct.pack("<I", int(overflow)))
        u.reg_write(UC_ARM_REG_MSP, 0x20010000)
        calls, compare_writes = [], []
        cycles = 0
        finished = False

        def code(uc, address, size, _):
            nonlocal finished
            if address in [0x105f4, 0x10718]:
                calls.append((address, uc.reg_read(UC_ARM_REG_R0)))
            if bytes(uc.mem_read(address, 2)) == b"\x00\xbe":
                finished = True
                uc.emu_stop()

        def read(uc, access, address, size, value, _):
            nonlocal cycles
            if address == 0xe0001004:
                cycles = (cycles + 1000) & 0xffffffff
                uc.mem_write(address, struct.pack("<I", cycles))

        def write(uc, access, address, size, value, _):
            if address == 0x4001806c:
                compare_writes.append(value)

        u.hook_add(UC_HOOK_CODE, code)
        u.hook_add(UC_HOOK_MEM_READ, read)
        u.hook_add(UC_HOOK_MEM_WRITE, write)
        u.emu_start(0x2000f001, 0x2000f000 + len(data), count=1500000)
        self.assertTrue(finished, "Payload failed to reach its final breakpoint")
        self.assertEqual(calls[0], (0x105f4, 1))
        self.assertEqual(calls[1][0], 0x10718)
        self.assertEqual(calls[2], (0x105f4, 0))
        return u, compare_writes

    def test_ramp_then_requested_duty_and_stop(self):
        for duty in [0, 30, 50, 75, 100]:
            with self.subTest(duty=duty):
                u, writes = self.emulate(duty)
                expected = 121 if duty == 100 else 120 * duty // 100
                self.assertEqual(writes[:-1], list(range(61, 122)))
                self.assertEqual(writes[-1], expected)
                self.assertEqual(u.reg_read(UC_ARM_REG_R9), expected)
                self.assertEqual(u.reg_read(UC_ARM_REG_R11), 1)

    def test_stops_even_when_pwm_overflow_never_arrives(self):
        u, writes = self.emulate(75, overflow=False)
        self.assertEqual(writes, [])
        self.assertEqual(u.reg_read(UC_ARM_REG_R11), 0)


if __name__ == "__main__":
    unittest.main()
