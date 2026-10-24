"""Natural-language pipeline checks with local/fake model responses only."""
import copy
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from kbdrv import ai, validation, sharing
from kbdrv.expr import compile_expression

def free_program(**changes):
    return {"kind":"program","name":"深海白光","expression":"mix(c1,c2,clamp(1-abs(x-mod(t*0.2,1))/0.1,0,1))","color":[0,4,18],"color2":[220,235,255],"speed":1,"brightness":0.7,**changes}



def design(**changes):
    return {"kind":"layers", "name":"深海白光", "background":[0, 4, 18],
            "layers":[{"pattern":"scan", "color":[220,235,255], "rate":0.2}],
            "speed":1, "brightness":0.7, "explain":"深蓝底上白光缓缓掠过", **changes}


class AITests(unittest.TestCase):
    def test_conversation_is_actual_plaintext_with_no_effect_generation(self):
        history=[{"role":"user","content":"我想做按键灯"},{"role":"assistant","content":"你希望什么时候熄灭？"}]
        with patch.object(ai,"chat_messages",return_value="明白，从松开后计时十秒，每个键独立保持。") as chat, patch.object(ai,"_run",side_effect=AssertionError("chat must not compile")):
            reply=ai.converse("松开后十秒",{},None,history)
        self.assertIn("每个键独立",reply)
        self.assertEqual(chat.call_args.args[1][0],history[0])
        self.assertTrue(chat.call_args.kwargs["system_prompt"].startswith(ai.CONVERSATION_PROMPT))

    def test_real_provider_all_dark_empty_target_contract_is_accepted(self):
        intent={"summary":"纯色","checks":[{"keys":[],"expect":[],"others_off":True}]}
        # A dark-only program needs a palette dependency but brightness=0 is intentional.
        spec=free_program(expression="c1",brightness=0)
        with patch.object(ai,"chat_messages",side_effect=[json.dumps(intent),json.dumps(spec)]):
            result=ai.generate("全部灯光熄灭",{})
        self.assertEqual(result["checks"][0]["expect"],[])

    def test_invalid_intent_error_explains_the_specific_parser_failure(self):
        with patch.object(ai,"chat_messages",return_value='{"summary":"test","checks":[null]}'):
            with self.assertRaisesRegex(ai.AIError,"AI 已返回回复.*每条验收必须是对象"):
                ai.generate("白光",{})

    def intent(self):
        return json.dumps({"summary":"按用户要求设计","checks":[]})

    def test_global_brightness_cannot_be_baked_into_expression(self):
        intent=json.dumps({"summary":"主色六成亮度","checks":[{"expect":[{"row":0,"col":0,"rgb":[153,153,153]}]}],
                           "controls":{"brightness":.6,"color":[255,255,255]}})
        baked=free_program(expression="mix(rgb(0,0,0),c1,0.6)",color=[255,255,255],brightness=1)
        correct=free_program(expression="c1",color=[255,255,255],brightness=.6)
        with patch.object(ai,"chat_messages",side_effect=[intent,json.dumps(baked),json.dumps(correct)]) as chat:
            result=ai.generate("纯白，整体亮度60%",{})
        self.assertEqual(result["brightness"],.6)
        self.assertIn("界面参数 brightness",chat.call_args.args[1][-1]["content"])

    def test_fixed_manual_controls_survive_refinement(self):
        controls={"color":[10,20,30],"color2":[80,90,100],"speed":.4,"brightness":.3}
        intent=json.dumps({"summary":"只改动画","checks":[],"controls":controls})
        correct=free_program(**controls)
        with patch.object(ai,"chat_messages",side_effect=[intent,json.dumps(free_program()),json.dumps(correct)]):
            result=ai.refine("只改动画，其余不变",{},correct,[])
        for key,value in controls.items():
            self.assertEqual(result[key],value)

    def test_invalid_controls_are_not_accepted_or_silently_dropped(self):
        for controls in ({"effect":"ripple"},{"brightness":float("nan")},{"color":[999,0,0]}):
            with self.subTest(controls=controls),patch.object(ai,"chat_messages",return_value=json.dumps({"summary":"test","checks":[],"controls":controls})):
                with self.assertRaises(ai.AIError):
                    ai.generate("白光",{})

    def test_layers_render_and_share_without_new_dsl(self):
        spec = ai._normalise(design())
        fn = compile_expression(spec["expression"])
        self.assertEqual(fn(1, 0, 21, 0, 21, 0), (0,4,18))
        self.assertEqual(fn(0, 0, 0, 0, 0, 0), (220,235,255))
        snap = {"params":{**validation.DEFAULT_PARAMS,"effect":"ai"}, "ai_spec":spec}
        decoded = sharing.decode(sharing.encode(snap, "分享", sharing.layout(5,22,1)))
        self.assertEqual(decoded["snapshot"]["ai_spec"]["expression"], spec["expression"])
        self.assertNotIn("design", decoded["snapshot"]["ai_spec"])

    def test_patterns_are_bounded_and_move_independently(self):
        for pattern in ("solid","breathe","wave","scan","ring","sparkle","checker"):
            with self.subTest(pattern=pattern):
                spec = ai._normalise(design(layers=[{"pattern":pattern,"color":[200,100,30]}]))
                fn = compile_expression(spec["expression"])
                for t in (0,0.8,50):
                    self.assertTrue(all(0 <= c <= 255 for c in fn(.3,.6,48,2,4,t)))
        spec = ai._normalise(design(layers=[{"pattern":"checker","color":[255,255,255]}]))
        fn = compile_expression(spec["expression"])
        self.assertNotEqual(fn(0,0,0,0,0,0), fn(.1,0,1,0,1,0))

    def test_static_and_dim_are_not_forced_to_animate(self):
        spec = ai._normalise(design(layers=[], brightness=0.1))
        fn = compile_expression(spec["expression"])
        self.assertEqual(fn(0,0,0,0,0,0), fn(1,1,131,5,21,99))
        self.assertEqual(spec["brightness"], .1)

    def test_bad_layer_data_is_rejected(self):
        for layer in ({"pattern":"exec"}, {"rate":float("nan")}, {"color":[300,0,0]},
                      {"center":[0]}, {"axis":"__import__"}, {"width":0}):
            with self.subTest(layer=layer), self.assertRaises(ValueError):
                ai._normalise(design(layers=[layer]))

    def test_reverse_scan_and_three_ring_layers_remain_portable(self):
        spec = ai._normalise(design(layers=[{"pattern":"scan","direction":"reverse","color":[250,250,250]}]))
        fn = compile_expression(spec["expression"])
        self.assertEqual(fn(1,0,21,0,21,0), (250,250,250))
        self.assertEqual(fn(0,0,0,0,0,0), (0,4,18))
        ai._normalise(design(layers=[{"pattern":"ring","direction":"reverse"}]*3))

    def test_automatic_repair_of_color_math_and_grid_singularity(self):
        invalid = {"kind":"program", "expression":"rgb(255,0,0)*0.5"}
        grid_invalid = {"kind":"program", "expression":"1/(x-1/21)"}
        with patch.object(ai, "chat_messages", side_effect=[self.intent(),json.dumps(invalid), json.dumps(grid_invalid), json.dumps(free_program())]) as chat:
            result = ai.generate("蓝底白光", {"api_key":"FAKE"})
        self.assertEqual(chat.call_count, 4)
        self.assertEqual(result["kind"], "program")
        self.assertIn("mix", chat.call_args_list[2].args[1][-1]["content"])

    def test_failed_repairs_have_friendly_error(self):
        with patch.object(ai, "chat_messages", side_effect=[self.intent()]+['{"kind":"program","expression":"1/0"}']*3) as chat:
            with self.assertRaisesRegex(ai.AIError, "上一版光效已保留"):
                ai.generate("白光", {"api_key":"FAKE"})
        self.assertEqual(chat.call_count, 4)

    def test_refine_includes_complete_current_work_and_history(self):
        current = ai._normalise(design(speed=.4, brightness=.25))
        previous = [{"role":"user", "content":"蓝底白光"}, {"role":"assistant","content":ai.summarise(current)}]
        with patch.object(ai, "chat_messages", side_effect=[self.intent(),json.dumps(free_program(speed=.2))]) as chat:
            ai.refine("再慢一点，其他不变", {"api_key":"FAKE"}, current, previous, ["#FF0000"])
        msgs = chat.call_args.args[1]
        self.assertEqual(msgs[:2], previous)
        self.assertIn('"brightness": 0.25', msgs[-2]["content"])
        self.assertIn('"design"', msgs[-2]["content"])
        self.assertIn("不得覆盖", msgs[-2]["content"])
        self.assertEqual(previous, msgs[:2])

    def test_real_inputs_choose_native_engines(self):
        for effect in ("ripple", "audio"):
            result = ai._normalise({"kind":"preset", "effect":effect, "audio_style":"radial"})
            self.assertEqual(result["effect"], effect)
            self.assertEqual(result["audio_style"], "radial")

    def test_local_compatible_api_transport(self):
        captured = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                captured.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                reply = {"summary":"按用户要求设计","checks":[]} if len(captured)==1 else free_program()
                body = json.dumps({"choices":[{"message":{"content":json.dumps(reply)}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = ai.generate("深蓝白光", {"api_key":"OFFLINE_TEST_ONLY", "base_url":f"http://127.0.0.1:{server.server_port}","model":"test"})
            self.assertEqual(result["kind"], "program")
            self.assertIn("从零", captured[1]["messages"][0]["content"])
            self.assertEqual(captured[0]["messages"][-1]["content"], "深蓝白光")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)
