"""Explicit loopback/HID test. Plays a quiet 120 BPM percussion sample, then stops."""
import argparse
import json
import math
import struct
import time
import urllib.request
import wave
import winsound
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--allow-hardware', action='store_true')
parser.add_argument('--output', required=True)
args = parser.parse_args()
if not args.allow_hardware:
    parser.error('Pass --allow-hardware for audio playback and the connected keyboard')
out = Path(args.output)
out.parent.mkdir(parents=True, exist_ok=True)
base = 'http://127.0.0.1:8787'


def state():
    with urllib.request.urlopen(base+'/api/state', timeout=5) as response:
        return json.load(response)


initial = state()
assert initial['build'] in ('20261021-ui6', '20261021-ui7', '20261021-ui8', '20261022-onboard1')
assert initial['params']['effect'] == 'audio'
for _ in range(30):
    if initial['audio']['active'] or initial['audio']['error']:
        break
    time.sleep(.1)
    initial = state()
assert initial['audio']['active'] and not initial['audio']['error']
rate, beats, interval = 48000, 8, .5
path = out.with_suffix('.wav')
pcm = bytearray()
for i in range(int(rate * (beats * interval + .5))):
    t = i / rate
    phase = t % interval
    # Short kick with no continuous tone between beats; modest sample amplitude.
    sample = .14 * math.sin(2*math.pi*75*t) * math.exp(-phase*28) if t < beats*interval and phase < .18 else 0
    value = int(32767 * sample)
    pcm.extend(struct.pack('<hh', value, value))
with wave.open(str(path), 'wb') as wav:
    wav.setnchannels(2)
    wav.setsampwidth(2)
    wav.setframerate(rate)
    wav.writeframes(pcm)

samples = []
with urllib.request.urlopen(base+'/api/stream', timeout=8) as stream:
    started = time.perf_counter()
    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    try:
        while time.perf_counter() - started < 5.2:
            line = stream.readline()
            if not line.startswith(b'data: '):
                continue
            packet = json.loads(line[6:])
            assert packet['c'] and not packet['e']
            raw = bytes.fromhex(packet['f'])
            parity = [[], []]
            for row in range(5):
                for col in range(22):
                    index = ((row+1)*22+col)*3
                    parity[(row+col)%2].append(max(raw[index:index+3]))
            samples.append({'t': round(time.perf_counter()-started, 4),
                            'pulse': packet.get('a', {}).get('pulse', 0),
                            'beat_count': packet.get('a', {}).get('beat_count', 0),
                            'peak': max(raw),
                            'even':sum(parity[0])/55, 'odd':sum(parity[1])/55,
                            'lit_slots': sum(max(raw[j:j+3])>40 for j in range(0,len(raw),3))})
    finally:
        winsound.PlaySound(None, 0)
final = state()
observed = final['audio']['beat_count'] - initial['audio']['beat_count']
out.with_name(out.stem+'-observed.json').write_text(json.dumps(
    {'params':initial['params'], 'observed_beats':observed, 'samples':samples}, indent=2), encoding='utf-8')
assert 6 <= observed <= 11, observed
assert max(s['pulse'] for s in samples) > .55
if initial['build'] == '20261021-ui6':
    assert max(s['peak'] for s in samples) > 90
    assert max(s['lit_slots'] for s in samples) >= 100
else:
    assert initial['params']['audio_style'] == 'staggered'
    assert 30 <= max(s['lit_slots'] for s in samples) <= 55
    assert any(s['even'] > 10*(s['odd']+1) for s in samples)
    assert any(s['odd'] > 10*(s['even']+1) for s in samples)
late = [s for s in samples if s['t'] > 4.8]
assert late and max(s['peak'] for s in late) < 10
assert final['params'] == initial['params']
assert final['audio']['active'] and not final['audio']['error']
report = {'build': final['build'], 'device': final['device']['name'],
          'audio_device': final['audio']['device'], 'observed_beats': observed,
          'checks': ['WASAPI loopback receives playback', 'repeated kicks trigger beat pulses',
                     'beat flashes follow selected spatial pattern', 'silence fades to dark', 'parameters preserved'],
          'visual_acceptance': False, 'hardware_receipt_acknowledged': False, 'samples': samples}
out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k != 'samples'}, ensure_ascii=True, indent=2))
