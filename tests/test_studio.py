"""Offline regressions: fake HID, temporary state, no keys/audio/network AI."""
import concurrent.futures
import copy
import ctypes
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aula_studio as app
from kbdrv import effects, validation, sharing
from kbdrv.audio import AudioAnalyzer
from kbdrv.expr import ExpressionError, compile_expression
from kbdrv.storage import read_json, write_json
from kbdrv import input_hook


class FakeKeyboard:
    rows, cols, row_offset = 5, 22, 1
    info = {"mapping_model":"WIN 60 HE", "model": "Fake", "vid": 1, "pid": 2, "family": "test"}

    def __init__(self):
        self.sent = self.released = 0
        self.closed = False
        self.fail = False
        self.last_frame = None

    def send_frame(self, frame):
        if self.fail:
            raise OSError("simulated unplug")
        if self.closed:
            raise OSError("closed")
        self.sent += 1
        self.last_frame = frame

    def release(self):
        self.released += 1

    def close(self):
        self.closed = True

    def save_onboard(self, request, paint):
        self.release()
        return {'verified':True, 'name':request['name'], 'effect':request['effect'], 'fields':request['fields']}


def wait_until(fn, timeout=2):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if fn():
            return
        time.sleep(0.01)
    raise AssertionError("condition did not become true")


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aula_regression_")
        self.root = Path(self.temp.name)
        web = self.root / "studio"
        web.mkdir()
        for filename in ("index.html", "app.js", "splash.js", "style.css"):
            (web / filename).write_text("audit asset", encoding="utf-8")
        self.patches = [patch.object(app, "WEB", web), patch.object(app, "_audio_devices_cache", (time.perf_counter(), []))]
        for attr, filename in [("SETTINGS","settings.json"),("PRESETS","presets.json"),
                               ("CUSTOM","custom_effects.json"),("AI_CONFIG","ai_config.json"),("KEYMAP_CONFIG","keymap_calibration.json")]:
            self.patches.append(patch.object(app, attr, web / filename))
        for p in self.patches:
            p.start()
        self.original = app.STUDIO
        app.STUDIO = app.Studio()
        self.studios = [app.STUDIO]
        self.server = app.StudioServer(("127.0.0.1", 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        for studio in self.studios:
            studio.shutdown()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        app.STUDIO = self.original
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def request(self, path, body=None, headers=None, raw=None):
        hdr = {"Content-Type":"application/json"}
        hdr.update(headers or {})
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base+path, data=data, headers=hdr)
        try:
            with urllib.request.urlopen(req, timeout=4) as response:
                data = response.read()
                return response.status, json.loads(data) if response.headers.get_content_type() == "application/json" else data
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def start_fake(self, keyboard=None):
        studio = app.STUDIO
        studio.keyboard = keyboard or FakeKeyboard()
        studio.connected = True
        studio._sync_inputs = lambda _effect: None
        studio._thread = threading.Thread(target=studio._run, daemon=True)
        studio._thread.start()
        return studio, studio.keyboard

    def test_creator_rejects_new_requests_during_shutdown(self):
        app.STUDIO._stop.set()
        with patch.object(app.creator,"turn") as model:
            self.assertEqual(self.request('/api/creator/message',{'prompt':'new work'})[0],503)
        model.assert_not_called();self.assertFalse(app.STUDIO.creator.busy())

    def test_creator_messages_make_only_a_draft_until_explicit_apply(self):
        before=app.STUDIO.current()
        candidate={"kind":"program","name":"独立预览","expression":"c1","color":[30,70,120],"color2":[1,2,3],"speed":.5,"brightness":.4,"checks":[]}
        with patch.object(app.creator,"turn",return_value={"action":"build","spec":candidate,"reply":"预览已更新","calls":1}):
            code,job=self.request("/api/creator/message",{"prompt":"创作我的灯光"})
            self.assertEqual(code,200)
            wait_until(lambda:not app.STUDIO.creator.busy())
        self.assertEqual(app.STUDIO.current(),before)
        self.assertEqual(self.request("/api/creator")[1]["draft"]["expression"],"c1")
        self.request("/api/creator/params",{"color":[12,34,56]})
        self.assertEqual(app.STUDIO.current(),before)
        code,response=self.request("/api/creator/apply",{})
        self.assertEqual(code,200);self.assertEqual(response["params"]["effect"],"ai")
        self.assertEqual(response["params"]["color"],[12,34,56])

    def test_creator_observations_are_computed_by_the_local_renderer(self):
        app.STUDIO.creator.edit(draft={"kind":"program","expression":"c1","color":[100,50,20],"brightness":.5})
        with patch.object(app.creator,"turn",return_value={"action":"discuss","reply":"看到了实际输出","calls":1}) as model:
            code,_=self.request("/api/creator/message",{"prompt":"当前是什么","observation":{"keys":[{"vk":65,"held":True,"age":.1}],"t":0}})
            self.assertEqual(code,200);wait_until(lambda:not app.STUDIO.creator.busy())
        observation=model.call_args.args[5]
        self.assertEqual(observation["source"],"local_simulated_preview")
        self.assertEqual(next(x["rgb"] for x in observation["samples"] if x["vk"]==65),[50,25,10])
        self.assertEqual(self.request("/api/creator/message",{"prompt":"bad","observation":{"spec":{}}})[0],400)

    def test_creator_persistence_and_reset_keep_the_active_lighting(self):
        original=app.STUDIO.current()
        app.STUDIO.creator.edit(draft={"kind":"program","expression":"c2","color2":[11,22,33]})
        restored=app.Studio();self.studios.append(restored)
        self.assertEqual(restored.creator.view()["draft"]["expression"],"c2")
        self.assertEqual(restored.current(),original)
        self.request("/api/creator/reset",{})
        self.assertIsNone(app.STUDIO.creator.view()["draft"])
        self.assertEqual(app.STUDIO.current(),original)

    def test_static_configuration_and_sibling_are_denied(self):
        write_json(app.AI_CONFIG, {"api_key":"FAKE_SENTINEL"})
        sibling = self.root / "studio_backup"
        sibling.mkdir()
        (sibling / "test.json").write_text("{}")
        for route in ("/ai_config.json","/settings.json","/../studio_backup/test.json","/devices.json"):
            self.assertEqual(self.request(route)[0], 404, route)
        self.assertEqual(self.request("/")[0], 200)
        self.assertEqual(self.request("/splash.js")[0], 200)

    def test_program_preview_uses_identical_renderer_without_changing_device(self):
        from test_program import program, led
        before = app.STUDIO.current()
        for age, expected in ((.1,True),(9.99,True),(10,False)):
            status, result = self.request("/api/preview",{"spec":program(),"keys":[{"vk":65,"held":False,"age":age}]})
            self.assertEqual(status,200)
            frame = bytes.fromhex(result["f"])
            lit = {i//3 for i in range(0,len(frame),3) if max(frame[i:i+3])}
            self.assertEqual(lit,{led(65)} if expected else set())
        self.assertEqual(app.STUDIO.current(),before)

    def test_program_controls_save_select_restart_and_delete(self):
        from test_program import program, led
        self.assertEqual(self.request('/api/ai/apply',{'spec':program()})[0],200)
        status, changed = self.request('/api/ai/params',{'color':[40,80,120],'color2':[20,40,60],'speed':.5,'brightness':.5})
        self.assertEqual(status,200)
        self.assertEqual(changed['spec']['color'],[40,80,120])
        self.request('/api/custom',{'name':'我的单键','spec':changed['spec']})
        self.request('/api/effect',{'effect':'paint'})
        self.assertEqual(self.request('/api/custom/apply',{'name':'我的单键'})[0],200)
        restored = app.Studio()
        self.studios.append(restored)
        self.assertEqual(restored.ai_spec['name'],'我的单键')
        self.assertEqual(restored.ai_spec['kind'],'program')
        frame = effects.render('ai',0,expr=restored.ai_expr,color=restored.params['color'],
            brightness=restored.params['brightness'],speed=restored.params['speed'],key_state={'ages':{65:1}})
        self.assertEqual(frame[led(65)],(20,40,60))
        before = app.STUDIO.current()
        status, deleted = self.request('/api/custom/delete',{'name':'我的单键'})
        self.assertEqual(status,200)
        self.assertEqual(deleted['custom'],[])
        self.assertEqual(app.STUDIO.current(),before)

    def test_program_frame_loop_receives_key_snapshot(self):
        from test_program import program, led
        app.STUDIO.apply_spec(program())
        app.STUDIO.hook._times = {65:time.time()}
        app.STUDIO.hook._pressed = {65}
        studio,kb = self.start_fake()
        wait_until(lambda:kb.sent>1)
        self.assertEqual({i for i,c in enumerate(kb.last_frame) if max(c)},{led(65)})
        self.assertIsNone(studio.error)

    def test_malformed_preview_keys_and_latent_key_branch_fail_atomically(self):
        for keys in ([1],{},'A'):
            self.assertEqual(self.request('/api/preview',{'keys':keys})[0],400)
        before = app.STUDIO.current()
        self.assertEqual(self.request('/api/ai/apply',{'spec':{'kind':'program','expression':'c1 if not down(90) else 1/0'}})[0],400)
        self.assertEqual(app.STUDIO.current(),before)

    def test_mapping_debug_exposes_vk_scan_and_last_sent_leds_without_saving_keys(self):
        before=app.STUDIO.current()
        self.assertEqual(self.request('/api/keymap/debug',{'enabled':True})[0],200)
        event=input_hook.KBDLLHOOKSTRUCT(vkCode=65,scanCode=0x1e)
        with patch.object(input_hook.user32,'CallNextHookEx',return_value=0):
            app.STUDIO.hook._callback(0,input_hook.WM_KEYDOWN,ctypes.addressof(event))
        status,data=self.request('/api/keymap')
        self.assertEqual(status,200)
        self.assertEqual((data['event']['vk'],data['event']['scan_code'],data['event']['led']),(65,30,68))
        self.assertEqual(app.STUDIO.current(),before)
        self.assertFalse(app.SETTINGS.exists())
        self.assertEqual(self.request('/api/keymap/debug',{'enabled':False})[0],200)
        self.assertIsNone(self.request('/api/keymap')[1]['event'])

    def test_mapping_calibration_is_shared_with_preview_and_recovers_on_reconnect(self):
        from test_program import program
        status,result=self.request('/api/keymap/calibrate',{'vk':65,'led':69})
        self.assertEqual(status,200)
        self.assertTrue(result['keymap']['calibrated'])
        status,data=self.request('/api/preview',{'spec':program(),'keys':[{'vk':65,'held':True,'age':0}]})
        frame=bytes.fromhex(data['f'])
        self.assertGreater(max(frame[69*3:70*3]),0)
        self.assertEqual(frame[68*3:69*3],b'\0\0\0')
        restored=app.Studio();self.studios.append(restored)
        with patch.object(app,'Keyboard',return_value=FakeKeyboard()):restored.connect()
        self.assertEqual(restored.keymap.by_vk[65]['led'],69)
        self.assertEqual(restored.keymap.by_vk[83]['led'],68)
        self.assertEqual(self.request('/api/keymap/calibrate',{'reset':True})[0],200)
        self.assertEqual(app.STUDIO.keymap.by_vk[65]['led'],68)

    def test_single_key_debug_overlay_restores_effect_without_changing_saved_work(self):
        before=app.STUDIO.current()
        studio,kb=self.start_fake()
        self.request('/api/keymap/debug',{'enabled':True,'single_key':True})
        studio.hook._pressed={65}
        wait_until(lambda:kb.last_frame and {i for i,c in enumerate(kb.last_frame) if max(c)}=={68})
        self.assertEqual(self.request('/api/keymap/probe',{'led':94})[0],200)
        wait_until(lambda:max(kb.last_frame[94])>0)
        self.request('/api/keymap/debug',{'enabled':False})
        wait_until(lambda:len([c for c in kb.last_frame if max(c)])>1)
        self.assertEqual(studio.current(),before)

    def test_static_keyrow_keycol_uses_calibration_in_real_frames_and_preview(self):
        app.STUDIO.apply_spec({'kind':'program','expression':'c1 if row==keyrow(65) and col==keycol(65) else grey(0)'})
        self.request('/api/keymap/calibrate',{'vk':65,'led':69})
        studio,kb=self.start_fake()
        wait_until(lambda:kb.sent>1)
        self.assertEqual({i for i,c in enumerate(kb.last_frame) if max(c)},{69})
        _,preview=self.request('/api/preview',{'spec':studio.ai_spec})
        pixels=bytes.fromhex(preview['f'])
        self.assertEqual({i for i in range(132) if max(pixels[i*3:i*3+3])},{69})

    def test_masked_configuration(self):
        write_json(app.AI_CONFIG, {"api_key":"FAKE_SENTINEL"})
        status, payload = self.request("/api/ai/config")
        self.assertEqual(status, 200)
        self.assertNotIn("FAKE_SENTINEL", json.dumps(payload))

    def test_direct_chat_preserves_lighting_and_displays_the_actual_reply(self):
        before = app.STUDIO.current()
        reply = "可以。你希望从按下还是松开开始计时？我先和你讨论，不改变灯光。"
        with patch.object(app.ai_effects, "converse", return_value=reply):
            status, result = self.request("/api/ai/chat", {"prompt":"想做一个按键灯光"})
        self.assertEqual(status, 200)
        self.assertEqual(result["reply"], reply)
        self.assertEqual(result["history"][-1]["content"], reply)
        self.assertEqual(app.STUDIO.current(), before)
        restored = app.Studio()
        self.studios.append(restored)
        self.assertEqual(restored.ai_history, result["history"])

    def test_compose_uses_full_dialogue_and_keeps_it_when_starting_a_new_work(self):
        from test_program import program
        self.request("/api/ai/reset", {})
        for prompt, reply in (("想做按键灯", "从按下还是松开起算？"), ("松开后保持十秒", "好的，只亮本键，不扩散。")):
            with patch.object(app.ai_effects, "converse", return_value=reply):
                self.assertEqual(self.request("/api/ai/chat", {"prompt":prompt})[0], 200)
        with patch.object(app.ai_effects, "compose", return_value=program()) as compose:
            status, result = self.request("/api/ai/compose", {})
        self.assertEqual(status, 200)
        self.assertIsNone(compose.call_args.args[1])
        self.assertEqual(len(compose.call_args.args[2]), 4)
        self.assertEqual(len(result["history"]), 6)
        self.assertEqual(result["history"][0]["content"], "想做按键灯")

    def test_compose_failure_stays_in_conversation_without_overwriting_effect(self):
        app.STUDIO.apply_spec({"expression":"rgb(10,20,30)"})
        with patch.object(app.ai_effects, "converse", return_value="我会按你的要求修改。"):
            self.request("/api/ai/chat", {"prompt":"速度再慢一点"})
        before = app.STUDIO.current()
        with patch.object(app.ai_effects, "compose", side_effect=app.ai_effects.AIError("验收数据格式错误")):
            self.assertEqual(self.request("/api/ai/compose", {})[0], 400)
        self.assertEqual(app.STUDIO.current(), before)
        self.assertIn("【程序反馈】", app.STUDIO.ai_history[-1]["content"])

    def test_slow_chat_does_not_replace_newer_work_or_conversation(self):
        def reply(*_args):
            app.STUDIO.update_params({"effect":"static"})
            return "旧作品的回复"
        with patch.object(app.ai_effects, "converse", side_effect=reply):
            self.assertEqual(self.request("/api/ai/chat", {"prompt":"聊聊"})[0], 409)
        self.assertEqual(app.STUDIO.params["effect"], "static")
        self.assertFalse(app.STUDIO.ai_history)

    def test_ai_conversation_survives_restart_and_undo(self):
        from test_ai import design
        spec = app.ai_effects._normalise(design())
        with patch.object(app.ai_effects, "generate", return_value=spec):
            status, first = self.request("/api/ai/generate", {"prompt":"深蓝底白光"})
        self.assertEqual(status, 200)
        app.STUDIO.update_params({"speed":.4,"brightness":.25})
        second_spec = {**spec,"speed":.2,"brightness":.25,"change":"白光更慢，保持配色和亮度"}
        with patch.object(app.ai_effects, "refine", return_value=second_spec) as refine:
            status, second = self.request("/api/ai/refine", {"prompt":"慢一点，其他不变"})
        self.assertEqual(status, 200)
        self.assertEqual(refine.call_args.args[2]["speed"], .4)
        self.assertEqual(second["undo"], 2)
        restarted = app.Studio()
        self.studios.append(restarted)
        app.STUDIO = restarted
        self.assertEqual(restarted.ai_history, second["history"])
        status, undone = self.request("/api/ai/undo", {})
        self.assertEqual(status, 200)
        self.assertEqual(undone["params"]["speed"], .4)
        self.assertEqual(undone["params"]["brightness"], .25)
        self.assertEqual(undone["history"], first["history"])
        self.assertEqual(undone["undo"], 1)

    def test_ai_failure_preserves_complete_last_version(self):
        spec = {"kind":"expression","name":"旧作品","expression":"rgb(0,10,30)"}
        with patch.object(app.ai_effects, "generate", return_value=spec):
            self.assertEqual(self.request("/api/ai/generate", {"prompt":"蓝底"})[0], 200)
        before = app.STUDIO.current()
        saved = app.SETTINGS.read_bytes()
        history = copy.deepcopy(app.STUDIO.ai_history)
        with patch.object(app.ai_effects, "refine", side_effect=app.ai_effects.AIError("模拟失败")):
            self.assertNotEqual(self.request("/api/ai/refine", {"prompt":"柔和一点"})[0], 200)
        self.assertEqual(app.STUDIO.current(), before)
        self.assertEqual(app.STUDIO.ai_history, history)
        self.assertEqual(app.SETTINGS.read_bytes(), saved)

    def test_ai_new_work_persists_without_stopping_current_light(self):
        app.STUDIO.apply_spec({"kind":"expression","expression":"rgb(0,10,30)"})
        before = app.STUDIO.current()
        self.assertEqual(self.request("/api/ai/reset", {})[0], 200)
        restarted = app.Studio()
        self.studios.append(restarted)
        app.STUDIO = restarted
        self.assertEqual(restarted.current(), before)
        self.assertTrue(self.request("/api/state")[1]["ai_new"])
        spec = {"kind":"expression","expression":"rgb(10,0,30)"}
        with patch.object(app.ai_effects, "generate", return_value=spec) as generate, patch.object(app.ai_effects, "refine") as refine:
            self.assertEqual(self.request("/api/ai/refine", {"prompt":"重新设计"})[0], 200)
        generate.assert_called_once()
        refine.assert_not_called()

    def test_ai_native_work_can_be_saved_and_applied(self):
        spec = {"kind":"preset","name":"音乐交错","effect":"audio","audio_style":"radial",
                "color":[0,10,30],"color2":[255,255,255],"speed":.5,"brightness":.3}
        self.assertEqual(self.request("/api/custom", {"name":"音乐交错","spec":spec})[0], 200)
        status, result = self.request("/api/custom/apply", {"name":"音乐交错"})
        self.assertEqual(status, 200)
        self.assertEqual(result["params"]["effect"], "audio")
        self.assertEqual(result["params"]["audio_style"], "radial")
        app.STUDIO.update_params({"color":[0,5,10], "brightness":.2})
        self.assertEqual(app.STUDIO.ai_spec["color"], [0,5,10])
        self.assertEqual(app.STUDIO.ai_spec["brightness"], .2)

    def test_ai_entry_without_work_preserves_current_light(self):
        before = app.STUDIO.current()
        status, result = self.request("/api/effect", {"effect":"ai"})
        self.assertEqual(status, 200)
        self.assertTrue(result["needs_ai"])
        self.assertEqual(app.STUDIO.current(), before)
        # Low-level parameter validation still refuses an absent expression.
        self.assertEqual(self.request("/api/params", {"effect":"ai"})[0], 400)

    def test_ai_entry_restores_native_and_expression_works_with_history(self):
        for spec in ({"kind":"preset","name":"按键光","effect":"ripple","color":[0,0,0],
                      "color2":[90,140,255],"speed":3,"brightness":.9},
                     {"kind":"preset","effect":"audio","audio_style":"radial"},
                     {"kind":"expression","expression":"rgb(10,20,30)"}):
            with self.subTest(kind=spec["kind"], effect=spec.get("effect")):
                with patch.object(app.ai_effects, "generate", return_value=spec):
                    self.assertEqual(self.request("/api/ai/generate", {"prompt":"测试作品"})[0], 200)
                history = copy.deepcopy(app.STUDIO.ai_history)
                versions = copy.deepcopy(app.STUDIO.ai_versions)
                self.assertEqual(self.request("/api/effect", {"effect":"paint"})[0], 200)
                status, result = self.request("/api/effect", {"effect":"ai"})
                self.assertEqual(status, 200)
                self.assertEqual(result["params"]["effect"], spec.get("effect", "ai"))
                self.assertEqual(app.STUDIO.ai_history, history)
                self.assertEqual(app.STUDIO.ai_versions, versions)
                if spec["kind"] == "preset":
                    self.assertIsNone(app.STUDIO.ai_expr)
                else:
                    self.assertIsNotNone(app.STUDIO.ai_expr)

    def test_saving_current_ai_work_keeps_conversation_and_undo(self):
        spec = {"kind":"expression","name":"白光","expression":"rgb(90,90,90)"}
        with patch.object(app.ai_effects, "generate", return_value=spec):
            _, result = self.request("/api/ai/generate", {"prompt":"白色"})
        renamed = {**spec, "name":"我的白光"}
        self.assertEqual(self.request("/api/custom", {"name":"我的白光","spec":renamed})[0], 200)
        self.assertEqual(self.request("/api/ai/apply", {"spec":renamed,"keep_conversation":True})[0], 200)
        self.assertEqual(app.STUDIO.ai_history, result["history"])
        self.assertEqual(len(app.STUDIO.ai_versions), result["undo"])
        self.assertEqual(app.STUDIO.ai_spec["name"], "我的白光")

    def test_window_activation_requires_ready_desktop_and_same_origin(self):
        self.assertEqual(self.request('/api/window/activate', {})[0], 503)
        calls = []
        self.server.window_activate = lambda: calls.append(True) or True
        self.assertEqual(self.request('/api/window/activate', {}, headers={'Origin':'https://example.com'})[0], 403)
        self.assertEqual(calls, [])
        self.assertEqual(self.request('/api/window/activate', {})[0], 200)
        self.assertEqual(calls, [True])

    def test_normal_state_does_not_initialize_portaudio(self):
        with patch.object(app.AudioAnalyzer,"list_devices",side_effect=AssertionError("audio discovery must be explicit")):
            self.assertEqual(self.request("/api/state")[0],200)

    def test_request_origin_host_and_content_type(self):
        for headers, expected in [({"Origin":"https://audit.invalid"},403),
            ({"Host":"audit.invalid"},403),({"Sec-Fetch-Site":"cross-site"},403),
            ({"Content-Type":"text/plain"},415)]:
            self.assertEqual(self.request("/api/params", {"speed":2}, headers)[0],expected)
        self.assertEqual(self.request("/api/params", {"speed":2}, {"Origin":self.base})[0],200)

    def test_invalid_json_size_and_shape(self):
        for raw, status in [(b"{",400),(b"[]",400),(b'{"speed":NaN}',400),(b"x"*65537,413)]:
            self.assertEqual(self.request("/api/params",raw=raw)[0],status)

    def test_invalid_params_are_atomic_and_loop_survives(self):
        studio, kb = self.start_fake()
        wait_until(lambda:kb.sent > 1)
        before = copy.deepcopy(studio.params)
        for body in ({"speed":"broken"},{"speed":True},{"speed":-1}, {"brightness":2},
                     {"effect":"bogus"},{"color":[1,2,"x"]}, {"speed":2,"brightness":"x"}, {"unknown":1}):
            self.assertEqual(self.request("/api/params",body)[0],400)
            self.assertEqual(studio.params,before)
        self.assertTrue(studio._thread.is_alive())
        self.assertTrue(self.request("/api/state")[1]["device"]["render_alive"])

    def test_paint_request_is_atomic(self):
        before = copy.deepcopy(app.STUDIO.paint)
        self.assertEqual(self.request("/api/paint",{"leds":{"22":[255,0,0],"23":["x",0,0]}})[0],400)
        self.assertEqual(app.STUDIO.paint,before)
        self.assertEqual(self.request("/api/paint",{"leds":{"132":[1,2,3]}})[0],400)

    def test_release_stops_and_explicit_effect_resumes(self):
        studio,kb = self.start_fake()
        wait_until(lambda:kb.sent > 1)
        self.assertEqual(self.request("/api/off",{})[0],200)
        before = kb.sent
        time.sleep(0.12)
        self.assertEqual(kb.sent,before)
        self.assertEqual(kb.released,1)
        self.assertEqual(self.request("/api/effect",{"effect":"breathe"})[0],200)
        wait_until(lambda:kb.sent > before)

    def test_unplug_keeps_only_last_successful_frame_and_reconnects(self):
        studio,kb = self.start_fake()
        wait_until(lambda:kb.sent > 1)
        before = studio.frame
        kb.fail = True
        wait_until(lambda:not studio.connected)
        self.assertEqual(studio.frame,before)
        self.assertTrue(kb.closed)
        replacement = FakeKeyboard()
        with patch.object(app,"Keyboard",return_value=replacement):
            studio._next_connect = 0
            wait_until(lambda:replacement.sent > 0)
        self.assertTrue(studio.connected)
        self.assertIsNone(studio.error)

    def test_shutdown_waits_for_inflight_frame_before_closing(self):
        entered, proceed = threading.Event(), threading.Event()
        class Slow(FakeKeyboard):
            def send_frame(self,frame):
                entered.set()
                proceed.wait(2)
                super().send_frame(frame)
        studio,kb = self.start_fake(Slow())
        self.assertTrue(entered.wait(1))
        done = threading.Thread(target=studio.shutdown)
        done.start()
        time.sleep(0.05)
        self.assertFalse(kb.closed)
        proceed.set()
        done.join(2)
        self.assertFalse(done.is_alive())
        self.assertTrue(kb.closed)
        self.assertFalse(studio._thread.is_alive())

    def test_onboard_save_pauses_stream_and_preserves_software_settings(self):
        studio, kb = self.start_fake()
        studio.update_params({'effect':'ripple', 'color':[0,229,208], 'color2':[30,123,255]})
        original = studio.current()
        status, result = self.request('/api/onboard/save', {})
        self.assertEqual(status,200)
        self.assertTrue(result['onboard']['verified'])
        self.assertEqual(result['onboard']['fields'][0],8)
        self.assertEqual(studio.current(),original)
        before = kb.sent
        time.sleep(.05)
        self.assertEqual(kb.sent,before)
        self.assertFalse(studio.control_enabled)
        self.assertEqual(json.loads(app.SETTINGS.read_text())['control'],'firmware')

    def test_onboard_failure_resumes_stream_and_unsupported_effect_is_not_written(self):
        studio, kb = self.start_fake()
        studio.update_params({'effect':'breathe'})
        with patch.object(kb,'save_onboard',side_effect=ValueError('readback mismatch')):
            self.assertEqual(self.request('/api/onboard/save', {})[0],400)
        self.assertTrue(studio.control_enabled)
        studio.update_params({'effect':'audio'})
        with patch.object(kb,'save_onboard',side_effect=AssertionError('must not write')):
            self.assertEqual(self.request('/api/onboard/save', {})[0],400)
            status, response = self.request('/api/shutdown', {})
            self.assertEqual(status,200)
            self.assertEqual(response['exit']['saved_to'],'computer')
            self.assertFalse(response['exit']['verified'])
        self.assertEqual(json.loads(app.SETTINGS.read_text())['params']['effect'],'audio')

    def test_ai_close_saves_current_work_locally_without_writing_hardware(self):
        studio, kb = self.start_fake()
        studio.apply_spec({'kind':'expression','name':'退出回归','expression':'rgb(20,30,40)'})
        studio.update_params({'brightness':.23, 'speed':.7})
        original = studio.current()
        with patch.object(kb,'save_onboard',side_effect=AssertionError('AI must not write onboard')):
            receipt = studio.prepare_exit()
        self.assertEqual(receipt['saved_to'],'computer')
        self.assertEqual(receipt['reason'],'software_effect')
        self.assertEqual(receipt['verified'],False)
        self.assertEqual(studio.current(),original)
        self.assertEqual(app.Studio().current(),original)
        self.assertEqual(kb.released,0)

    def test_close_still_saves_supported_effect_and_propagates_real_failures(self):
        studio, kb = self.start_fake()
        studio.update_params({'effect':'ripple'})
        with patch.object(kb,'save_onboard',side_effect=ValueError('readback mismatch')):
            with self.assertRaisesRegex(ValueError,'readback mismatch'):
                studio.prepare_exit()
        self.assertTrue(studio.control_enabled)
        self.assertEqual(json.loads(app.SETTINGS.read_text())['params']['effect'],'ripple')
        receipt = studio.prepare_exit()
        self.assertEqual(receipt['saved_to'],'keyboard')
        self.assertTrue(receipt['verified'])

    def test_onboard_save_does_not_overwrite_a_newer_edit(self):
        studio, kb = self.start_fake()
        studio.update_params({'effect':'static'})
        def edit_during_save(request, paint):
            studio.update_params({'color':[10,20,30]})
            return {'verified':True}
        with patch.object(kb,'save_onboard',side_effect=edit_during_save):
            self.assertEqual(self.request('/api/onboard/save', {})[0],400)
        self.assertEqual(studio.params['color'],[10,20,30])
        self.assertTrue(studio.control_enabled)

    def test_restart_restores_ai_paint_and_zero_brightness(self):
        app.STUDIO.apply_spec({"expression":"rgb(255,0,0)","brightness":0})
        restarted = app.Studio()
        self.assertEqual(restarted.params["brightness"],0)
        self.assertEqual(restarted.ai_expr(0,0,22,0,0,0),(255,0,0))
        self.request("/api/paint",{"leds":{"22":[123,45,67]}})
        restarted = app.Studio()
        self.assertEqual(restarted.params["effect"],"paint")
        self.assertEqual(restarted.paint[22],[123,45,67])

    def test_audio_style_migrates_saves_and_restores_with_preset(self):
        self.assertEqual(validation.params({'effect':'audio'})['audio_style'], 'staggered')
        self.assertEqual(self.request('/api/params', {'effect':'audio','audio_style':'radial'})[0],200)
        self.request('/api/presets', {'name':'radial'})
        self.assertEqual(app.Studio().params['audio_style'], 'radial')
        self.request('/api/params', {'audio_style':'staggered'})
        self.request('/api/presets/apply', {'name':'radial'})
        self.assertEqual(app.STUDIO.params['audio_style'], 'radial')
        before = copy.deepcopy(app.STUDIO.params)
        self.assertEqual(self.request('/api/params', {'audio_style':'unknown','brightness':0})[0],400)
        self.assertEqual(app.STUDIO.params, before)

    def test_only_radial_audio_enables_keyboard_hook(self):
        class Hook:
            _thread = None
            started = stopped = 0
            def start(self):
                self.started += 1
                self._thread = self
            def is_alive(self):
                return True
            def stop(self):
                self.stopped += 1
                self._thread = None
        studio = app.STUDIO
        studio.hook = Hook()
        studio._audio_attempted = True
        studio.params['audio_style'] = 'radial'
        studio._sync_inputs('audio')
        self.assertEqual(studio.hook.started, 1)
        studio.audio_center = (4,2)
        studio.params['audio_style'] = 'staggered'
        studio._sync_inputs('audio')
        self.assertEqual(studio.hook.stopped, 1)
        self.assertIsNone(studio.audio_center)

    def test_share_inspect_and_export_do_not_change_current_or_presets(self):
        self.request('/api/paint', {'leds':{'22':[123,45,67]}})
        before, revision = app.STUDIO.current(), app.STUDIO.revision
        status, exported = self.request('/api/share/export', {'name':'分享涂色'})
        self.assertEqual(status,200)
        status, inspected = self.request('/api/share/inspect', {'code':exported['code']})
        self.assertEqual(status,200)
        self.assertTrue(inspected['compatible'])
        self.assertEqual(inspected['snapshot']['paint'][22],[123,45,67])
        self.assertEqual(app.STUDIO.current(),before)
        self.assertEqual(app.STUDIO.revision,revision)
        self.assertFalse(app.PRESETS.exists())

    def test_share_import_collision_and_save_only_preserve_current(self):
        self.request('/api/presets', {'name':'夜色'})
        code = sharing.encode({'params':{'effect':'wave','brightness':0,'audio_style':'radial'}},
                              '夜色', sharing.layout(5,22,1))
        before = app.STUDIO.current()
        status, result = self.request('/api/share/import', {'code':code})
        self.assertEqual(status,200)
        self.assertEqual(result['name'],'夜色（导入2）')
        self.assertFalse(result['applied'])
        self.assertEqual(app.STUDIO.current(),before)
        self.assertEqual(len(read_json(app.PRESETS,[])),2)
        self.request('/api/presets/apply', {'name':result['name']})
        self.assertEqual(app.STUDIO.params['brightness'],0)
        self.assertEqual(app.STUDIO.params['audio_style'],'radial')

    def test_ai_share_import_applies_without_api_and_survives_restart(self):
        self.request('/api/ai/apply', {'spec':{'name':'自创','expression':'rgb(12,34,56)','brightness':.5}})
        status, exported = self.request('/api/share/export', {'source':'ai','spec':app.STUDIO.ai_spec})
        self.assertEqual(status,200)
        self.request('/api/params', {'effect':'static'})
        status, result = self.request('/api/share/import', {'code':exported['code'],'apply':True})
        self.assertEqual(status,200)
        self.assertTrue(result['applied'])
        self.assertEqual(app.STUDIO.ai_expr(0,0,22,0,0,0),(12,34,56))
        restarted = app.Studio()
        self.assertEqual(restarted.params['brightness'],.5)
        self.assertEqual(restarted.ai_expr(0,0,22,0,0,0),(12,34,56))

    def test_share_bad_code_and_mismatched_layout_never_mutate(self):
        self.request('/api/presets', {'name':'原有'})
        before, presets = app.STUDIO.current(), read_json(app.PRESETS,[])
        incompatible = sharing.encode({'params':{}}, '68', sharing.layout(6,22,0))
        self.assertFalse(self.request('/api/share/inspect', {'code':incompatible})[1]['compatible'])
        for code in ('KEYLIGHT1.broken.0000000000000000', incompatible):
            self.assertEqual(self.request('/api/share/import', {'code':code,'apply':True})[0],400)
            self.assertEqual(app.STUDIO.current(),before)
            self.assertEqual(read_json(app.PRESETS,[]),presets)

    def test_sharing_selected_preset_includes_edits_without_applying(self):
        self.request('/api/presets', {'name':'保存版'})
        before = app.STUDIO.current()
        status, exported = self.request('/api/share/export', {'source':'preset','name':'保存版','params':{'brightness':.32}})
        self.assertEqual(status,200)
        self.assertEqual(sharing.decode(exported['code'])['snapshot']['params']['brightness'],.32)
        self.assertEqual(app.STUDIO.current(),before)

    def test_release_mode_survives_restart_without_retake(self):
        studio,kb = self.start_fake()
        wait_until(lambda:kb.sent > 0)
        self.request("/api/off",{})
        self.assertFalse(app.Studio().control_enabled)

    def test_ai_preset_restores_expression_after_other_ai(self):
        app.STUDIO.apply_spec({"name":"A","expression":"rgb(255,0,0)"})
        self.request("/api/presets",{"name":"A"})
        app.STUDIO.apply_spec({"name":"B","expression":"rgb(0,0,255)"})
        self.assertEqual(self.request("/api/presets/apply",{"name":"A"})[0],200)
        self.assertEqual(app.STUDIO.ai_spec["name"],"A")
        self.assertEqual(app.STUDIO.ai_expr(0,0,22,0,0,0),(255,0,0))

    def test_paint_preset_application_with_editor_params(self):
        self.request("/api/paint",{"leds":{"22":[123,45,67]}})
        self.request("/api/presets",{"name":"paint"})
        self.request("/api/paint",{"leds":{"22":[0,0,255]}})
        self.assertEqual(self.request("/api/presets/apply",{"name":"paint","params":{"brightness":0}})[0],200)
        self.assertEqual(app.STUDIO.paint[22],[123,45,67])
        self.assertEqual(app.STUDIO.params["brightness"],0)

    def test_legacy_ai_preset_is_rejected_without_changing_current(self):
        write_json(app.PRESETS,[{"name":"old","params":{"effect":"ai"}}])
        before = app.STUDIO.current()
        self.assertEqual(self.request("/api/presets/apply",{"name":"old"})[0],400)
        self.assertEqual(app.STUDIO.current(),before)

    def test_legacy_builtin_preset_still_applies(self):
        write_json(app.PRESETS,[{"name":"old","params":{"effect":"wave","speed":1.5}}])
        self.assertEqual(self.request("/api/presets/apply",{"name":"old"})[0],200)
        self.assertEqual(app.STUDIO.params["effect"],"wave")

    def test_preview_zero_brightness_is_black(self):
        status, data = self.request("/api/preview",{"effect":"static","brightness":0,"t":0})
        self.assertEqual(status,200)
        self.assertEqual(set(bytes.fromhex(data["f"])),{0})

    def test_rename_conflict_preserves_both_presets(self):
        self.request("/api/presets",{"name":"A"})
        self.request("/api/presets",{"name":"B"})
        self.assertEqual(self.request("/api/presets/rename",{"old":"A","new":"B"})[0],409)
        self.assertEqual({i["name"] for i in read_json(app.PRESETS,[])},{"A","B"})

    def test_concurrent_saves_and_state_reads_do_not_deadlock_or_lose_items(self):
        def task(i):
            status,_ = self.request("/api/presets",{"name":str(i)})
            self.assertEqual(status,200)
            self.assertEqual(self.request("/api/state")[0],200)
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(task,range(12)))
        self.assertEqual(len(read_json(app.PRESETS,[])),12)

    def test_ai_invalid_output_retries_without_external_api(self):
        from kbdrv import ai
        outputs = [json.dumps({"summary":"原需求","checks":[]}),json.dumps({"kind":"program","expression":"1/0"}), json.dumps({"kind":"program","expression":"c1","color":[1,2,3],"brightness":0})]
        with patch.object(ai,"chat_messages",side_effect=outputs) as mocked:
            spec = ai.generate("test",{})
        self.assertEqual(mocked.call_count,3)
        self.assertEqual(spec["brightness"],0)

    def test_ai_without_key_returns_actionable_error_without_network(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network prohibited")):
            # Call handler directly: patching urlopen would also block this test client.
            with self.assertRaises(app.ai_effects.AIError):
                app.ai_effects.generate("test",{})
        status,body = self.request("/api/ai/generate",{"prompt":"test"})
        self.assertEqual(status,400)
        self.assertIn("API Key",body["error"])

    def test_late_ai_result_does_not_replace_new_user_effect(self):
        revision = app.STUDIO.revision
        app.STUDIO.update_params({"effect":"wave"})
        with self.assertRaises(app.RequestError):
            app.STUDIO.apply_spec({"expression":"rgb(1,2,3)"},expected_revision=revision)
        self.assertEqual(app.STUDIO.params["effect"],"wave")

    def test_audio_thread_can_join_without_opening_device(self):
        audio = AudioAnalyzer()
        audio.start()
        audio.join(1)
        self.assertFalse(audio.is_alive())
        audio.stop()

    def test_expression_limits_and_runtime_errors(self):
        for source in ("1/0","2**(2**30)","pow(2,1000000)","(1,2,3)*1000000",
                       "__import__('os')","x.real","'x'*1000000","(1,2)","1e300"):
            with self.assertRaises((ExpressionError,ValueError),msg=source):
                compile_expression(source)
        fn = compile_expression("1/(x-0.3)")
        with self.assertRaises(ExpressionError):
            fn(0.3,0,22,0,0,0)

    def test_renderer_rows_and_range(self):
        fn = compile_expression("hsv(x+t*0.1,y,1)")
        for rows,offset in ((5,1),(6,0)):
            for effect in app.EFFECTS:
                frame = effects.render(effect,1.2,rows=rows,row_offset=offset,expr=fn,levels=[0.3]*22,ripples=[(3,2,0.7)])
                self.assertEqual(len(frame),132)
                self.assertTrue(all(len(c)==3 and all(0 <= v <= 255 for v in c) for c in frame))


class RippleTests(unittest.TestCase):
    def frame(self, age=None, **kwargs):
        return effects.render("ripple", 0, color=(0, 0, 0), color2=(255, 255, 255),
                              rows=5, row_offset=1,
                              ripples=[] if age is None else [(11, 2, age)], **kwargs)

    def test_single_ring_expands_and_fades(self):
        brightness = []
        for age, radius in ((0.25, 3), (0.5, 6), (0.75, 9)):
            frame = self.frame(age)
            radial = [frame[3 * 22 + 11 + d][0] for d in range(11)]
            self.assertEqual(max(range(11), key=radial.__getitem__), radius)
            brightness.append(max(radial))
            local_peaks = [i for i in range(1, 10)
                           if radial[i] > radial[i-1] and radial[i] >= radial[i+1]]
            self.assertEqual(local_peaks, [radius])
            self.assertEqual(radial[0], 0)
        self.assertGreater(brightness[0], brightness[1])
        self.assertGreater(brightness[1], brightness[2])

    def test_ring_is_symmetric_in_all_directions(self):
        frame = self.frame(0.25)
        for d in range(1, 11):
            self.assertEqual(frame[3*22+11-d], frame[3*22+11+d])
        for d in (1, 2):
            self.assertEqual(frame[(3-d)*22+11], frame[(3+d)*22+11])
        self.assertGreater(frame[1*22+11][0], 0)
        self.assertGreater(frame[5*22+11][0], 0)

    def test_idle_is_steady_and_expired_ring_disappears(self):
        idle = effects.render("ripple", 0, color=(80, 100, 120))
        self.assertEqual(idle, effects.render("ripple", 100, color=(80, 100, 120)))
        for age in (-1, effects.RIPPLE_LIFETIME, 10):
            self.assertEqual(self.frame(age), self.frame())

    def test_main_color_stays_dim_and_secondary_color_forms_ring(self):
        options = dict(color=(200,0,0), color2=(0,0,255), rows=5, row_offset=1)
        idle = effects.render("ripple", 0, **options)
        center = 3*22+11
        self.assertEqual(idle[center], (40,0,0))
        ring = effects.render("ripple", 0, ripples=[(11,2,.25)], **options)
        self.assertGreaterEqual(ring[center][0], idle[center][0] - 1)
        self.assertEqual(ring[center][2], 0)
        self.assertGreater(ring[center+3][2], 200)
        self.assertLess(ring[center+3][0], idle[center+3][0])
        expired = effects.render("ripple", 0, ripples=[(11,2,2)], **options)
        self.assertEqual(expired, idle)
        dim = effects.render("ripple", 0, brightness=.5, **options)
        self.assertEqual(dim[center], (20,0,0))

    def test_speed_scales_ring_radius_and_lifetime(self):
        self.assertEqual(self.frame(.25, speed=2), self.frame(.5))
        self.assertEqual(self.frame(1, speed=2), self.frame())
        full = self.frame(.25)
        dim = self.frame(.25, brightness=.5)
        self.assertTrue(all(b[0] <= a[0] / 2 for a, b in zip(full, dim)))

    def test_independent_presses_each_keep_their_own_ring(self):
        options = dict(color=(0,0,0), color2=(255,255,255), rows=5, row_offset=1)
        a = effects.render("ripple", 0, ripples=[(4,2,.25)], **options)
        b = effects.render("ripple", 0, ripples=[(17,2,.5)], **options)
        both = effects.render("ripple", 0, ripples=[(4,2,.25),(17,2,.5)], **options)
        self.assertEqual(both, [tuple(max(x,y) for x,y in zip(c,d)) for c,d in zip(a,b)])

    def test_long_press_is_one_event_and_release_allows_next_press(self):
        hook = input_hook.KeyHook()
        def send(message, vk=0x41, code=0):
            data = input_hook.KBDLLHOOKSTRUCT(vkCode=vk)
            return hook._callback(code, message, ctypes.addressof(data))
        with patch.object(input_hook.user32, "CallNextHookEx", return_value=19) as chain:
            self.assertEqual(send(input_hook.WM_KEYDOWN), 19)
            for _ in range(8):
                send(input_hook.WM_KEYDOWN)
            self.assertEqual(len(hook.drain()), 1)
            send(input_hook.WM_KEYUP)
            send(input_hook.WM_KEYDOWN)
            send(input_hook.WM_SYSKEYDOWN, 0x53)
            send(input_hook.WM_SYSKEYDOWN, 0x53)
            self.assertEqual(len(hook.drain()), 2)
            send(input_hook.WM_SYSKEYUP, 0x53)
            send(input_hook.WM_SYSKEYDOWN, 0x53)
            send(input_hook.WM_KEYDOWN, 0xFF)
            send(input_hook.WM_KEYDOWN, 0x44, -1)
            self.assertEqual(len(hook.drain()), 1)
            self.assertEqual(chain.call_count, 17)
        hook.stop()
        self.assertEqual(hook._pressed, set())
        self.assertEqual(hook.drain(), [])


if __name__ == "__main__":
    unittest.main()
