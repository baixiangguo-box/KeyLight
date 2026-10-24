"""Explicit hardware check: play a test WAV; Shift keys move the audio center."""
import argparse
import ctypes
import json
import time
import urllib.request
import winsound
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--allow-hardware', action='store_true')
parser.add_argument('--wav', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
if not args.allow_hardware:
    parser.error('Pass --allow-hardware for playback and Shift-key input')
base = 'http://127.0.0.1:8787'


def api(route='/api/state', body=None):
    req = urllib.request.Request(base+route, data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.load(response)


emit = ctypes.WinDLL('user32').keybd_event
emit.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_uint, ctypes.c_size_t]
emit.restype = None


def press(vk, scan):
    try:
        emit(vk, scan, 0, 0)
        time.sleep(.05)
    finally:
        emit(vk, scan, 2, 0)
    time.sleep(.08)


original = api()
assert original['build'] in ('20261021-ui7', '20261021-ui8', '20261022-onboard1') and original['params']['effect'] == 'audio'
samples, centers = [], []
try:
    api('/api/params', {'audio_style':'radial'})
    for _ in range(30):
        if api()['device']['hook']['started']:
            break
        time.sleep(.1)
    assert api()['device']['hook']['started']
    press(0xA0, 0x2A)
    centers.append(api()['audio']['center'])
    assert centers[0] == [1,3]
    with urllib.request.urlopen(base+'/api/stream', timeout=8) as stream:
        started = time.perf_counter()
        changed = False
        winsound.PlaySound(args.wav, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        while time.perf_counter() - started < 5.2:
            elapsed = time.perf_counter() - started
            if elapsed >= 1.8 and not changed:
                press(0xA1, 0x36)
                centers.append(api()['audio']['center'])
                assert centers[1] == [19,3]
                changed = True
            line = stream.readline()
            if not line.startswith(b'data: '):
                continue
            packet = json.loads(line[6:])
            assert packet['c'] and not packet['e']
            raw = bytes.fromhex(packet['f'])
            peak_led = max(range(132), key=lambda i: max(raw[i*3:i*3+3]))
            samples.append({'t': round(elapsed,4), 'peak': max(raw),
                            'x': peak_led%22, 'y': peak_led//22-1,
                            'pulse': packet.get('a',{}).get('pulse',0)})
    left = [s for s in samples if .25 < s['t'] < 1.7 and s['pulse'] > .4]
    right = [s for s in samples if 2.3 < s['t'] < 3.8 and s['pulse'] > .4]
    assert left and right
    assert any(abs(s['x']-1)<=1 and abs(s['y']-3)<=1 for s in left), left
    assert any(abs(s['x']-19)<=1 and abs(s['y']-3)<=1 for s in right), right
    assert max(s['peak'] for s in samples if s['t'] > 4.8) < 10
finally:
    winsound.PlaySound(None, 0)
    api('/api/params', {'audio_style':original['params']['audio_style']})
    time.sleep(.2)
final = api()
assert final['params'] == original['params']
assert not final['device']['hook']['started']
report = {'build':final['build'], 'centers':centers,
          'checks':['real hook moves center with Left and Right Shift',
                    'peak lighting follows the chosen center', 'silence fades to dark',
                    'original style and parameters restored', 'staggered mode stops keyboard hook'],
          'visual_acceptance':False, 'hardware_receipt_acknowledged':False, 'samples':samples}
Path(args.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='samples'},indent=2))
