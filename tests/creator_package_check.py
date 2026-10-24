"""Frozen creator integration against the isolated native QA instance only."""
import json
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

BASE='http://127.0.0.1:8797'
def api(path='/api/state',body=None):
    req=urllib.request.Request(BASE+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=8) as r:return json.load(r)
def finished():
    for _ in range(160):
        result=api('/api/creator')
        if result['job']['state']!='running':return result
        time.sleep(.05)
    raise AssertionError('Frozen creator timed out')
checks=[];calls=[]
class Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        messages=json.loads(self.rfile.read(int(self.headers['Content-Length'])))['messages']
        system=messages[0]['content'];calls.append(system[:25])
        text='\n'.join(m['content'] for m in messages[1:])
        routing='discuss|clarify|build' in system
        interpreting='暂不设计实现' in system
        if routing:
            if 'CANCEL_TEST' in text:time.sleep(.8)
            value={'action':'discuss' if 'DISCUSS_ONLY' in text else 'build','reply':'Local model fixture conversation'}
        elif interpreting:value={'summary':'Independent original light','checks':[]}
        else:
            bad='AUTO_REPAIR' in text and not any(m['content'].startswith('方案未通过') for m in messages)
            value={'kind':'program','name':'Native creator QA','expression':'1/0' if bad else 'mix(c1,c2,0.5+0.5*sin(t+x*3))',
                   'color':[10,20,30],'color2':[80,120,200],'speed':1,'brightness':.7,'explain':'Local fixture animation'}
        data=json.dumps({'choices':[{'message':{'content':json.dumps(value)}}]}).encode()
        self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def log_message(self,*args):pass
initial=api()
assert initial['build']=='20261024-creator1' and not initial['device']['connected']
stub=ThreadingHTTPServer(('127.0.0.1',0),Stub);thread=threading.Thread(target=stub.serve_forever,daemon=True);thread.start()
try:
    api('/api/ai/config',{'api_key':'LOCAL_STUB_NOT_A_SECRET','base_url':f'http://127.0.0.1:{stub.server_port}','model':'native-qa'})
    api('/api/creator/reset',{})
    before=api()['params']
    api('/api/creator/message',{'prompt':'Create a flowing animation'})
    first=finished();assert first['draft']['kind']=='program' and first['job']['calls']==3
    assert api()['params']==before
    checks.append('Frozen creator auto-builds a draft without applying hardware parameters')
    api('/api/creator/message',{'prompt':'AUTO_REPAIR the animation'})
    fixed=finished();assert fixed['job']['state']=='done' and fixed['job']['repairs']>0
    checks.append('Actual HTTP transport feeds runtime errors back and repairs in the same turn')
    api('/api/creator/message',{'prompt':'DISCUSS_ONLY explain the idea'})
    discussed=finished();assert discussed['draft']==fixed['draft'] and discussed['undo']==fixed['undo']
    checks.append('Discussion preserves the draft and undo history')
    api('/api/creator/message',{'prompt':'CANCEL_TEST create another work'})
    api('/api/creator/cancel',{});time.sleep(1)
    assert api('/api/creator')['draft']==fixed['draft']
    checks.append('Cancelled network completion cannot overwrite the draft')
    api('/api/creator/params',{'brightness':.35})
    assert api()['params']==before
    api('/api/creator/apply',{})
    assert api()['params']['brightness']==.35 and api()['ai_spec']['name']=='Native creator QA'
    checks.append('Explicit apply adopts the draft, including manual controls')
    shared=api('/api/share/export',{'source':'ai','spec':api('/api/creator')['draft']})
    assert api('/api/share/inspect',{'code':shared['code']})['snapshot']['ai_spec']['kind']=='program'
    checks.append('Compiled draft remains shareable offline')
    report={'ok':True,'source':'FROZEN_NATIVE_NO_HID_LOCAL_MODEL_STUB','checks':checks,'model_requests':len(calls)}
    Path('.build/creator-native.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
finally:
    stub.shutdown();stub.server_close();thread.join(2)
