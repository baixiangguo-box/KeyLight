"""Read-only live sharing check. Does not import, apply or modify user presets."""
import argparse
import json
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
args = parser.parse_args()


def api(route='/api/state', body=None):
    req = urllib.request.Request('http://127.0.0.1:8787'+route,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=8) as response:
        return json.load(response)


before = api()
assert before['build'] in ('20261021-ui8', '20261022-onboard1')
exported = api('/api/share/export', {'source':'current','name':'当前光效'})
inspected = api('/api/share/inspect', {'code':exported['code']})
assert inspected['compatible']
assert inspected['snapshot']['params'] == before['params']
if before['params']['effect'] == 'paint':
    assert inspected['snapshot']['paint'] == before['paint']
if before['params']['effect'] == 'ai':
    assert inspected['snapshot']['ai_spec']['expression'] == before['ai_spec']['expression']
after = api()
assert before['params'] == after['params'] and before['paint'] == after['paint']
assert before['presets'] == after['presets']
assert before['custom'] == after['custom']
assert before['device']['revision'] == after['device']['revision']
assert after['device']['connected'] and not after['device']['error']
out = Path(args.output)
out.with_suffix('.txt').write_text(exported['code'], encoding='utf-8')
report = {'build':after['build'], 'effect':before['params']['effect'],
          'code_length':len(exported['code']), 'compatible':True,
          'checks':['current effect roundtrips', 'export and inspect do not apply lighting',
                    'user parameters and existing presets unchanged', 'device remains connected'],
          'preset_count':len(after['presets']), 'custom_count':len(after['custom'])}
out.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
