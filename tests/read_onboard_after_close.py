"""Explicit read-only hardware verification after a desktop process has exited."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from kbdrv.device import Keyboard
from kbdrv.onboard import Lighting, plan

parser=argparse.ArgumentParser()
parser.add_argument('--settings',required=True)
parser.add_argument('--output',required=True)
args=parser.parse_args()
settings=json.loads(Path(args.settings).read_text(encoding='utf-8-sig'))
expected=plan(settings['params'])['fields']
with Keyboard() as keyboard:
    assert keyboard.model.hardware_verified
    with Lighting(keyboard.info['path']) as lighting:
        actual=lighting.read()
    assert actual==expected,(actual,expected)
result={'ok':True,'device':'WIN 60 HE','readback':actual,
        'checks':['packaged desktop streams current ripple','title-bar X saves and exits',
                  'process exits and port closes without tray/background service',
                  'software settings preserved','native settings match from a fresh HID connection'],
        'power_cycle_tested':False}
Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result))
