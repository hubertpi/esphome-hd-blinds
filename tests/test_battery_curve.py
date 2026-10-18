import pathlib
import subprocess
import tempfile
import unittest

class BatteryCurveTests(unittest.TestCase):
    def test_boundaries_and_monotonicity(self):
        root=pathlib.Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            p=pathlib.Path(temp)
            (p/'test.c').write_text('''
#include <assert.h>
#include "battery_curve.h"
int main(void) {
 assert(hd_battery_estimate(65535)==255);
 assert(hd_battery_estimate(2800)==0);
 assert(hd_battery_estimate(3750)==50);
 assert(hd_battery_estimate(4200)==100);
 assert(hd_battery_estimate(4350)==100);
 unsigned prev=0;
 for(unsigned mv=2800;mv<=4350;mv++) {
  unsigned pct=hd_battery_estimate(mv);
  assert(pct>=prev && pct<=100);prev=pct;
 }
 return 0;
}
''')
            subprocess.run(['gcc','-I'+str(root/'firmware/src'),str(p/'test.c'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
