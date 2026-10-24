"""HTTP smoke checks only for an isolated packaged --no-device server on 8798."""
import argparse
import json
import urllib.request
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--output',required=True)
args = parser.parse_args()
BASE = 'http://127.0.0.1:8798'


def api(route='/api/state',body=None):
    request = urllib.request.Request(BASE+route,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=5) as response:
        return json.load(response)


initial = api()
assert initial['build'] == '20261024-creator1'
assert not initial['device']['connected'] and not initial['audio']['active']
assert api('/api/effect',{'effect':'ai'})['needs_ai']
assert api()['params']==initial['params']
mapping=api('/api/keymap')
assert mapping['profile']=='win60' and mapping['physical_keys']==61
assert next(k['led'] for k in mapping['keys'] if k['code']=='KeyA')==68
assert next(k['led'] for k in mapping['keys'] if k['code']=='KeyB')==94
with urllib.request.urlopen(BASE+'/',timeout=5) as response:
    assert '分享当前' in response.read().decode('utf-8')

# This script only runs against the installer's isolated --no-device data path.
# Exercise the frozen natural-language pipeline using a localhost model stub.
captured = []
implementations = []
class ModelStub(BaseHTTPRequestHandler):
    def do_POST(self):
        messages = json.loads(self.rfile.read(int(self.headers['Content-Length'])))['messages']
        captured.append(messages)
        conversational = '你是用户正在使用的键光软件' in messages[0]['content']
        interpreting = '暂不设计实现' in messages[0]['content']
        if not conversational and not interpreting:
            implementations.append(messages)
        spec = {'kind':'program','name':'Offline QA scan','color':[0,4,18],'color2':[220,235,255],
                'expression':'mix(c1,c2,clamp(1-abs(x-mod(t*0.2,1))/0.1,0,1))',
                'speed':1 if len(implementations)<=1 else .2, 'brightness':.7,
                'explain':'Local model fixture', 'change':'Slower scan' if len(captured)>1 else ''}
        if interpreting:
            spec = {'summary':'Keep blue background and white beam','checks':[]}
        content = 'I understand the requested lighting. We can discuss it before applying.' if conversational else json.dumps(spec)
        data = json.dumps({'choices':[{'message':{'content':content}}]}).encode()
        self.send_response(200)
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def log_message(self, *args):
        pass
stub = ThreadingHTTPServer(('127.0.0.1',0), ModelStub)
thread = threading.Thread(target=stub.serve_forever, daemon=True)
thread.start()
try:
    api('/api/ai/config',{'api_key':'OFFLINE_QA_ONLY','base_url':f'http://127.0.0.1:{stub.server_port}','model':'local-test'})
    before=api()['params']
    chat=api('/api/ai/chat',{'prompt':'Dark blue background with a soft white moving beam'})
    assert 'discuss' in chat['reply'] and api()['params']==before
    first = api('/api/ai/compose',{})
    assert first['spec']['color']==[0,4,18] and first['spec']['kind']=='program' and first['undo']==1
    api('/api/params',{'speed':.35})
    api('/api/ai/chat',{'prompt':'Slower, keep the colors'})
    second = api('/api/ai/compose',{})
    assert second['params']['speed']==.2 and len(second['history'])==8
    assert '"speed": 0.35' in implementations[1][-2]['content']
    undone = api('/api/ai/undo',{})
    assert undone['params']['speed']==.35 and len(undone['history'])==6
    api('/api/ai/reset',{})
    state = api()
    assert state['ai_new'] and not state['ai_history'] and state['params']['effect']=='ai'
finally:
    stub.shutdown()
    stub.server_close()
    thread.join(2)
api('/api/ai/apply',{'spec':{'expression':'rgb(5,10,15)','name':'Packaged QA','brightness':.5}})
shared = api('/api/share/export',{'name':'Packaged QA'})
assert api('/api/share/inspect',{'code':shared['code']})['snapshot']['ai_spec']['expression']=='rgb(5,10,15)'
api('/api/params',{'effect':'static'})
api('/api/share/import',{'code':shared['code'],'apply':True})
current = api()
assert current['params']['effect']=='ai' and current['params']['brightness']==.5
assert len(current['presets'])==1
assert not current['device']['connected'] and not current['audio']['active']
api('/api/ai/apply',{'spec':{'kind':'preset','name':'Native AI QA','effect':'ripple',
                           'color':[0,0,0],'color2':[90,140,255]}})
api('/api/effect',{'effect':'paint'})
restored = api('/api/effect',{'effect':'ai'})
assert restored['params']['effect']=='ripple' and api()['ai_spec']['kind']=='preset'
report={'ok':True,'build':current['build'],'checks':['packaged HTML served','AI expression applied offline',
        'AI entry without a work preserves lighting', 'AI card restores native engine after paint',
        'frozen two-stage original program generation with local model stub', 'natural language refinement includes manual edits',
        'undo and new conversation preserve the current light',
        'share export and import apply','data saved outside bundled assets','no HID/audio opened'],
        'hardware_opened':False}
Path(args.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
