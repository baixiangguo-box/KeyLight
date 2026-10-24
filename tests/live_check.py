"""Explicit live WIN 60 HE checks. Temporarily changes RAM lighting, then restores.

No firmware/flash commands and no AI API calls. Not part of unittest discovery.
"""
import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--allow-hardware",action="store_true")
parser.add_argument("--output",required=True)
args = parser.parse_args()
if not args.allow_hardware:
    parser.error("Pass --allow-hardware to temporarily test the connected keyboard")
BASE = "http://127.0.0.1:8787"


def api(route, body=None):
    req = urllib.request.Request(BASE+route, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=8) as resp:
        return json.load(resp)


def stream_sample(seconds=0.35):
    out=[]
    with urllib.request.urlopen(BASE+"/api/stream",timeout=4) as response:
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            line=response.readline()
            if line.startswith(b"data: "):
                out.append(json.loads(line[6:]))
    return out


original=api("/api/state")
assert original.get("build") in ("20261021-fix1", "20261021-ui1", "20261021-ui2", "20261021-ui3", "20261021-ui4", "20261021-ui5", "20261021-ui6", "20261021-ui7", "20261021-ui8", "20261022-onboard1")
assert original["device"]["connected"] and original["device"]["model"]["name"]=="WIN 60 HE"
results={"build":original["build"],"device":"WIN 60 HE","checks":[],"visual_acceptance":False,
         "real_ai_api_called":False,"hardware_receipt_acknowledged":False}
failure=None
try:
    for color in ([255,0,0],[0,255,0],[0,0,255]):
        api("/api/params",{"effect":"static","color":color,"brightness":0.5})
        frames=stream_sample(0.2)
        assert frames and frames[-1]["c"] and not frames[-1]["e"]
        raw=bytes.fromhex(frames[-1]["f"])
        assert list(raw[22*3:22*3+3])==[int(v*.5) for v in color]
    results["checks"].append("RGB frames written successfully")
    api("/api/off",{})
    before=api("/api/state")["device"]["frames_sent"]
    time.sleep(.3)
    state=api("/api/state")
    assert state["device"]["control"]=="firmware" and state["device"]["frames_sent"]==before
    results["checks"].append("firmware release stops frame count")
    api("/api/effect",{"effect":"rainbow"})
    speed_results=[]
    for speed in (.2,1,3):
        api("/api/params",{"speed":speed})
        time.sleep(.15)
        frames=[bytes.fromhex(p["f"]) for p in stream_sample(.45)]
        deltas=[sum(abs(a-b) for a,b in zip(x,y))/len(x) for x,y in zip(frames,frames[1:])]
        speed_results.append({"speed":speed,"samples":len(frames),"mean_delta":round(sum(deltas)/len(deltas),3)})
    assert speed_results[0]["mean_delta"] < speed_results[1]["mean_delta"] < speed_results[2]["mean_delta"]
    results["speed_samples"]=speed_results
    results["checks"].append("speed affects live transmitted animation")
    api("/api/effect",{"effect":"ripple"})
    time.sleep(.4)
    assert api("/api/state")["device"]["hook"]["started"]
    results["checks"].append("global ripple hook starts")
    api("/api/params",{"effect":"audio","audio_style":"staggered"})
    for _ in range(20):
        status=api("/api/state")
        if status["audio"]["active"]:break
        time.sleep(.1)
    assert status["audio"]["active"] and not status["audio"]["error"]
    assert not status["device"]["hook"]["started"]
    frames=stream_sample(.2)
    assert len(frames[-1].get("l",[]))==22
    results["checks"].append("loopback audio starts and provides 22 bands; ripple hook stops")
    api("/api/effect",{"effect":"breathe"})
    time.sleep(.3)
    assert not api("/api/state")["audio"]["active"]
    results["checks"].append("audio capture stops on leaving audio effect")
    try:
        api("/api/params",{"speed":"broken"})
        raise AssertionError("invalid speed accepted")
    except urllib.error.HTTPError as exc:
        assert exc.code==400
    assert api("/api/state")["device"]["render_alive"]
    results["checks"].append("invalid parameters rejected without stopping render loop")
    try:
        api("/ai_config.json")
        raise AssertionError("configuration download accepted")
    except urllib.error.HTTPError as exc:
        assert exc.code==404
    results["checks"].append("configuration URL denied without reading key")
except Exception as exc:
    failure=exc
    results["failure"]=repr(exc)
finally:
    try:
        api("/api/paint",{"clear":True,"leds":{str(i):c for i,c in enumerate(original["paint"])}})
        if original.get("ai_spec"):
            api("/api/ai/apply",{"spec":original["ai_spec"]})
        api("/api/params",original["params"])
        api("/api/settings",original["settings"])
        if original["device"].get("control")=="firmware":api("/api/off",{})
        time.sleep(.3)
        after=api("/api/state")
        assert after["params"]==original["params"] and after["paint"]==original["paint"]
        results["original_restored"]=True
    except Exception as exc:
        results["original_restored"]=False
        results["restore_failure"]=repr(exc)
        failure=failure or exc
    first=api("/api/state")
    t=time.monotonic()
    time.sleep(2.2)
    last=api("/api/state")
    results["observed_fps"]=round((last["device"]["frames_sent"]-first["device"]["frames_sent"])/(time.monotonic()-t),2)
    results["final_device"]=last["device"]
    results["final_params"]=last["params"]
    Path(args.output).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(results,ensure_ascii=True,indent=2))
if failure:raise failure
