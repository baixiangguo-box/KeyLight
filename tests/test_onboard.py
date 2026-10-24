"""Protocol readback, rollback and unsupported-mode boundaries without HID."""
import unittest
from unittest.mock import patch
from kbdrv import onboard


class Transport:
    def __init__(self):
        self.fields = [9,4,4,144,238,144,0,0,0,0,1,0]
        self.colors = [[i%256,20,30] for i in range(132)]
        self.queue, self.writes = [], []
        self.ignore_global = False

    def write(self, data):
        self.writes.append(data)
        assert len(data)==64 and data[0]==1
        if data[1:3]==bytes([7,1]):
            self.queue.append(bytes([1,7,0,0,0,12,*self.fields])+bytes(46))
        elif data[1:3]==bytes([7,0]) and not self.ignore_global:
            self.fields = list(data[6:18])
        elif data[1:3]==bytes([9,0]):
            index,size = data[4],data[5]
            for i in range(size//3):
                self.colors[18*index+i] = list(data[6+i*3:9+i*3])
        elif data[1:3]==bytes([9,128]):
            raw=bytes(v for rgb in self.colors for v in rgb)
            for index,start in enumerate(range(0,396,54)):
                chunk=raw[start:start+54]
                self.queue.append(bytes([1,9,128,0,index,len(chunk)])+chunk+bytes(58-len(chunk)))
        return 64

    def read(self, size, timeout):
        return self.queue.pop(0) if self.queue else []


class OnboardTests(unittest.TestCase):
    def lighting(self):
        obj=onboard.Lighting.__new__(onboard.Lighting)
        obj.device=Transport()
        return obj

    def test_ripple_has_secondary_ring_and_dim_main_color(self):
        request=onboard.plan({'effect':'ripple','color':[0,229,208],'color2':[30,123,255]})
        self.assertEqual(request['fields'],[8,2,4,30,123,255,0,45,41,0,0,0])
        obj=self.lighting()
        result=obj.save(request)
        self.assertTrue(result['verified'])
        self.assertEqual(obj.read(),request['fields'])
        self.assertEqual({p[1] for p in obj.device.writes},{7})

    def test_write_without_ack_still_needs_matching_readback(self):
        obj=self.lighting()
        old=obj.device.fields[:]
        obj.device.ignore_global=True
        with self.assertRaisesRegex(onboard.OnboardError,'不一致'):
            obj.save(onboard.plan({'effect':'breathe'}))
        self.assertEqual(obj.device.fields,old)
        self.assertEqual(list(obj.device.writes[-1][6:18]),old)

    def test_custom_colors_roundtrip_full_132_slots(self):
        obj=self.lighting()
        colors=[[0,0,0] for _ in range(132)]
        colors[22]=[1,2,3]
        colors[-1]=[200,150,100]
        with patch.object(onboard.time,'sleep'):
            obj.save(onboard.plan({'effect':'paint'}),colors)
        self.assertEqual(obj.read_colors(),colors)
        self.assertEqual(obj.read()[0],10)

    def test_audio_ai_and_unknown_effects_are_never_written(self):
        obj=self.lighting()
        for effect in ['audio','ai','meteor','unknown']:
            with self.assertRaises(onboard.OnboardError):
                obj.save(onboard.plan({'effect':effect}))
        self.assertEqual(obj.device.writes,[])

    def test_black_static_handles_zero_brightness_without_guessing_firmware_minimum(self):
        request=onboard.plan({'effect':'breathe','brightness':0})
        self.assertEqual(request['fields'][0],0)
        self.assertEqual(request['fields'][3:9],[0]*6)

    def test_malformed_or_missing_reply_does_not_report_success(self):
        obj=self.lighting()
        obj.device.write=lambda _:64
        with patch.object(onboard.time,'perf_counter',side_effect=[0,0,.9]):
            with self.assertRaises(onboard.OnboardError):
                obj.read()
