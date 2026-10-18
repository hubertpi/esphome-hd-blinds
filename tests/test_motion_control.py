"""Compile and exercise the actual firmware's encoder controller."""
import pathlib
import subprocess
import tempfile
import unittest

class MotionTests(unittest.TestCase):
    def test_targets_slowdown_coast_and_reference(self):
        root=pathlib.Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            work=pathlib.Path(directory)
            (work/'test.c').write_text(r'''
#include <assert.h>
#include "motion.h"
int main(void) {
 hd_motion_t m={.travel=1000,.calibrated=true,.referenced=true};
 assert(hd_motion_percent(&m,0)==100);
 assert(hd_motion_percent(&m,1000)==0);
 assert(hd_motion_target(&m,10)==900);
 assert(hd_motion_percent(&m,900)==10);
 assert(hd_motion_percent(&m,-5)==100);
 assert(hd_motion_percent(&m,1005)==0);
 for(int pct=0;pct<=100;pct++) {
  int32_t target=hd_motion_target(&m,pct);
  assert(target>=0 && target<=1000);
  assert(hd_motion_percent(&m,target)==pct);
 }
 m.referenced=false;assert(hd_motion_percent(&m,400)==255);
 m.referenced=true;m.targeting=true;m.target=900;
 assert(hd_motion_duty(&m,0,2,65)==65);
 assert(hd_motion_duty(&m,899,2,65)==55);
 assert(hd_motion_duty(&m,899,2,40)==40);
 assert(!hd_motion_should_stop(&m,899,2));
 assert(hd_motion_should_stop(&m,900,2));
 assert(hd_motion_should_stop(&m,901,2));
 m.target=0;
 assert(!hd_motion_should_stop(&m,1,1));
 assert(hd_motion_should_stop(&m,0,1));
 assert(hd_motion_should_stop(&m,-1,1));
 hd_motion_learn(&m,1,10,6);assert(m.lead_up==2);
 assert(m.lead_down==0);
 hd_motion_learn(&m,2,890,896);assert(m.lead_down==3);
 m.target=900;
 assert(hd_motion_should_stop(&m,897,2));
 assert(!hd_motion_should_stop(&m,896,2));
 hd_motion_sample(&m,50,100);assert(m.velocity==500);
 assert(hd_motion_duty(&m,810,2,65)<65); /* velocity expands slowdown */
 m.stage=2;
 assert(hd_motion_flags(&m)&HD_UPPER_SET);
 assert(hd_motion_flags(&m)&HD_CALIBRATING);
 /* Firmware records this encoder count rather than snapping to a target. */
 assert(hd_motion_percent(&m,903)==10);
 /* Target moves must retain the configured startup torque, even when
    cruise/near-target speeds are lower. This also covers short moves. */
 m.target=900;m.targeting=true;
 assert(hd_motion_output(&m,0,2,60,75,0,250)==75);
 assert(hd_motion_output(&m,0,2,60,75,240,250)==61);
 assert(hd_motion_output(&m,899,2,60,75,240,250)==61);
 assert(hd_motion_output(&m,0,2,60,75,100,250)==69);
 assert(hd_motion_output(&m,0,2,60,75,250,250)==60);
 assert(hd_motion_output(&m,0,1,80,50,125,250)==65);
 assert(hd_motion_output(&m,899,2,60,75,250,250)==55);
 assert(hd_motion_output(&m,0,2,60,75,0,0)==60);
 int32_t record[6],restored;
 hd_motion_record(&m,903,true,record);
 hd_motion_t rebooted={0};
 assert(hd_motion_restore(&rebooted,record,&restored));
 assert(restored==903 && rebooted.referenced && rebooted.calibrated);
 assert(hd_motion_percent(&rebooted,restored)==10);
 hd_motion_record(&m,903,false,record); /* power lost while moving */
 assert(hd_motion_restore(&rebooted,record,&restored));
 assert(rebooted.calibrated && !rebooted.referenced);
 assert(hd_motion_percent(&rebooted,restored)==255);
 record[2]=0;assert(!hd_motion_restore(&rebooted,record,&restored));
 return 0;
}
''')
            subprocess.run(['gcc','-std=c11','-Wall','-I'+str(root/'firmware/src'),
                            str(work/'test.c'),'-o',str(work/'test')],check=True)
            subprocess.run([str(work/'test')],check=True)
