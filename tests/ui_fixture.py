"""Explicit offline browser fixture; never opens a real HID device."""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aula_studio as app
from test_studio import FakeKeyboard

parser = argparse.ArgumentParser()
parser.add_argument("--port",type=int,default=8799)
args = parser.parse_args()
scratch=Path(__file__).resolve().parents[1]/'.build'
scratch.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="aula_ui_fixture_",dir=scratch) as tmp:
    for attr in ("SETTINGS","PRESETS","CUSTOM","AI_CONFIG","KEYMAP_CONFIG"):
        setattr(app, attr, Path(tmp)/(attr.lower()+".json"))
    app.STUDIO = app.Studio()
    fake = FakeKeyboard()
    app.Keyboard = lambda: fake
    app.STUDIO._sync_inputs = lambda _effect: None
    # Explicit fake AI transport; exercises the real compiler, repair and history.
    def fake_chat(_config, messages, *, system_prompt=None):
        time.sleep(.2)
        natural=[m["content"] for m in messages if m["role"]=="user" and not m["content"].startswith(
            ("软件当前上下文", "按用户明确", "请按以上对话", "先前独立整理", "方案未通过", "验收 JSON", "独立复查", "真实检查"))]
        latest=natural[-1] if natural else ""
        if system_prompt==app.creator.ROUTE_PROMPT:
            return json.dumps({"action":"discuss" if any(w in latest for w in ("先不要", "什么建议", "怎么实现", "当前是什么", "不要改灯效")) else "build",
                               "reply":"可以先聊想法，明确后我会制作预览。"})
        if system_prompt==app.creator.REVIEW_PROMPT:
            return json.dumps({"decision":"implementation","reason":"修正失败表达式，保持原始验收"})
        if (system_prompt or "").startswith(app.ai_effects.CONVERSATION_PROMPT):
            return "我理解你的想法：" + messages[-1]["content"] + "。可以继续讨论，方案明确后按对话生成光效。"
        if system_prompt:
            if "单键" in latest:
                from test_program import program
                return json.dumps({"summary":"按哪个键只亮该键，按下起十秒熄灭，不扩散","checks":program()["checks"]})
            return json.dumps({"summary":"按用户要求从零设计，并保留未修改部分","checks":[]})
        text = "\n".join(m["content"] for m in messages if m["role"] == "user")
        if natural and "测试失败" in natural[-1]:
            return '{"kind":"expression","expression":"1/0"}'
        if "自动修正" in latest and not any(m["content"].startswith("方案未通过") for m in messages):
            return '{"kind":"program","expression":"1/0"}'
        if "音乐" in latest:
            return json.dumps({"kind":"program","name":"交错音乐","expression":"mix(grey(0),mix(c1,c2,level),pulse) if mod(row+col,2)==mod(beat,2) else grey(0)",
                "audio_style":"staggered","color":[0,4,18],"color2":[220,235,255],
                "explain":"灯位分别跟随声音起伏","change":"保持配色，改为交错音频律动"})
        if "单键" in latest:
            from test_program import program
            return json.dumps(program())
        slower = "慢一点" in text
        return json.dumps({"kind":"program","name":"深海白光","color":[0,4,18],"color2":[220,235,255],
            "expression":"mix(c1,c2,clamp(1-abs(x-mod(t*0.2,1))/0.1,0,1))",
            "speed":.4 if slower else 1,"brightness":.7,
            "explain":"暗蓝底上一道白光从左向右移动",
            "change":"减慢速度，保持深蓝底与白光" if slower else ""})
    app.ai_effects.chat_messages = fake_chat
    # Seed a complete AI and a paint preset without any AI request.
    red = [[0,0,0] for _ in range(132)]
    red[22] = [220,30,10]
    app._write_json(app.PRESETS,[{"name":"涂色回归", "version":2,
        "params":{**app.DEFAULT_PARAMS,"effect":"paint"},"paint":red,"ai_spec":None}])
    app._write_json(app.CUSTOM,[{"name":"离线AI样例","kind":"expression",
        "expression":"hsv(x+t*0.1,0.8,1)","speed":1,"brightness":0.6}])
    app._audio_devices_cache = float("inf"), []
    server = app.StudioServer(("127.0.0.1",args.port),app.Handler)
    app.STUDIO.start()
    print(json.dumps({"fixture":"FAKE_HID_NO_REAL_DEVICE","port":server.server_port}),flush=True)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        app.STUDIO.shutdown()
        server.server_close()
