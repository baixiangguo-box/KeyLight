"""Behavior-level regressions: no HID, no real keys, no external model."""
import copy
import ctypes
import json
import unittest
from unittest.mock import patch

from kbdrv import ai, effects, validation, sharing, input_hook
from kbdrv.program import Program, verify, KEY_CELLS


def program(expression="c1 if key_age < 10 else grey(0)", **patches):
    return {"kind":"program", "name":"十秒单键", "expression":expression,
            "color":[240,40,20], "color2":[20,30,230], "speed":1,"brightness":1,
            "checks":[
                {"label":"未按全黑","keys":[],"expect":[{"vk":65,"state":"off"}],"others_off":True},
                {"label":"A 按下只亮 A","keys":[{"vk":65,"held":True,"age":0}],"expect":[{"vk":65,"state":"on"}],"others_off":True},
                {"label":"松开仍亮，不扩散","keys":[{"vk":65,"held":False,"age":9.99}],"expect":[{"vk":65,"state":"on"}],"others_off":True},
                {"label":"十秒熄灭","keys":[{"vk":65,"held":False,"age":10}],"expect":[{"vk":65,"state":"off"}],"others_off":True}], **patches}


def led(vk):
    r,c = KEY_CELLS[vk]
    return (r+1)*22+c


def render(spec, keys=None, **params):
    checked, fn = validation.spec(spec)
    return effects.render("ai",0,expr=fn,color=checked["color"],color2=checked["color2"],
        speed=params.get("speed",checked["speed"]),brightness=params.get("brightness",checked["brightness"]),
        key_state=keys,rows=5,row_offset=1)


class ProgramTests(unittest.TestCase):
    def release_palette_program(self, expression="c1 if key_on or key_release_age < 10 else c2", **patches):
        def expect(vk,palette):
            return {"vk":vk,"palette":palette,"palette_exact":True}
        checks=[
            {"label":"未按过取副色","keys":[],"expect":[expect(65,"secondary")]},
            {"label":"按住取主色，邻键取副色","keys":[{"vk":65,"held":True,"age":20}],
             "expect":[expect(65,"primary"),expect(66,"secondary")]},
            {"label":"松开后主色保持期","keys":[{"vk":65,"held":False,"age":29.99,"release_age":9.99}],
             "expect":[expect(65,"primary"),expect(66,"secondary")]},
            {"label":"到时回副色","keys":[{"vk":65,"held":False,"age":30,"release_age":10}],
             "expect":[expect(65,"secondary")]},
            {"label":"多个键独立松开计时","keys":[{"vk":65,"held":False,"age":30,"release_age":10},
                                             {"vk":66,"held":False,"age":25,"release_age":5}],
             "expect":[expect(65,"secondary"),expect(66,"primary")]},
            {"label":"重新按住取消旧松开计时","keys":[{"vk":65,"held":True,"age":1,"release_age":20,"count":2}],
             "expect":[expect(65,"primary")]},
            {"label":"再次松开重新计时","keys":[{"vk":65,"held":False,"age":2,"release_age":.5,"count":2}],
             "expect":[expect(65,"primary")]},
        ]
        return program(expression,checks=checks,**patches)

    def test_every_release_branch_tracks_both_ui_colors(self):
        for colors in (([30,123,255],[164,191,229]),([221,67,39],[12,198,97])):
            with self.subTest(colors=colors):
                spec=self.release_palette_program(color=colors[0],color2=colors[1],brightness=.6)
                checked,fn=validation.spec(spec)
                verify(checked,fn)
                actual=render(spec,{"held":set(),"ages":{65:29,66:30},"releases":{65:9,66:10}})
                self.assertEqual(actual[led(65)],tuple(int(v*.6) for v in colors[0]))
                self.assertEqual(actual[led(66)],tuple(int(v*.6) for v in colors[1]))

    def test_palette_probe_rejects_a_fixed_background_despite_matching_current_color(self):
        spec=self.release_palette_program("c1 if key_on or key_release_age < 10 else rgb(20,30,230)")
        checked,fn=validation.spec(spec)
        with self.assertRaisesRegex(ValueError,"换色复测失败.*场景 1.*检查点 1.*副色"):
            verify(checked,fn)

    def test_palette_probe_rejects_only_the_release_hold_branch_being_fixed(self):
        spec=self.release_palette_program("c1 if key_on else (rgb(240,40,20) if key_release_age < 10 else c2)")
        checked,fn=validation.spec(spec)
        with self.assertRaisesRegex(ValueError,"换色复测失败.*场景 3.*主色"):
            verify(checked,fn)

    def test_color_error_identifies_real_case_and_does_not_invent_hardcoding(self):
        spec=self.release_palette_program("c1 if key_on else c2")
        checked,fn=validation.spec(spec)
        with self.assertRaisesRegex(ValueError,"配色断言失败.*场景 3.*松开后主色保持期.*检查点 1.*实际 RGB.*不等于使用了固定色值"):
            verify(checked,fn)

    def test_exact_palette_rejects_dimmed_hold_but_audio_hue_can_still_dim(self):
        spec=self.release_palette_program("mix(grey(0),c1,.5) if key_on or key_release_age < 10 else c2")
        checked,fn=validation.spec(spec)
        with self.assertRaisesRegex(ValueError,"配色断言失败.*场景 2"):
            verify(checked,fn)
        for bad in ("yes",1,None):
            spec=self.release_palette_program()
            spec["checks"][0]["expect"][0]["palette_exact"]=bad
            with self.assertRaisesRegex(ValueError,"palette_exact"):
                verify(*validation.spec(spec))

    def test_color_probe_keeps_speed_and_brightness_identical_to_real_rendering(self):
        spec=self.release_palette_program(speed=2,brightness=.4)
        for case in spec["checks"]:
            for key in case.get("keys",[]):
                for name in ("age","release_age"):
                    if name in key:key[name]/=2
        checked,fn=validation.spec(spec)
        verify(checked,fn)

    def test_program_seconds_express_exact_boundary_at_three_times_speed(self):
        spec=self.release_palette_program(speed=3,brightness=.6)
        for case in spec["checks"]:case["time_unit"]="program"
        verify(*validation.spec(spec))
        # A rounded physical time is genuinely before the boundary, not expired.
        wrong=self.release_palette_program(speed=3)
        wrong["checks"]=[
            {"keys":[],"expect":[{"vk":65,"palette":"secondary"}]},
            {"keys":[{"vk":65,"held":True,"age":20}],"expect":[{"vk":65,"palette":"primary"}]},
            {"label":"错误地把3.333当成10/3","keys":[{"vk":65,"held":False,"age":5,"release_age":3.333}],
             "expect":[{"vk":65,"palette":"secondary"}]},
        ]
        with self.assertRaisesRegex(ValueError,"程序计时9.999.*期望可调副色"):
            verify(*validation.spec(wrong))
        wrong["checks"][2]["time_unit"]="minutes"
        with self.assertRaisesRegex(ValueError,"time_unit"):
            verify(*validation.spec(wrong))

    def test_implementation_repairs_a_single_fixed_color_branch_without_changing_checks(self):
        good=self.release_palette_program()
        bad={**good,"expression":"c1 if key_on or key_release_age < 10 else rgb(20,30,230)"}
        intent=json.dumps({"summary":"松开计时主色保持，到时回可调副色","checks":good["checks"]})
        with patch.object(ai,"chat_messages",side_effect=[intent,json.dumps(bad),json.dumps(good)]) as chat:
            result=ai.generate("按住主色，松开后保持10秒，再回副色",{})
        self.assertEqual(result["expression"],good["expression"])
        self.assertEqual(result["checks"],good["checks"])
        self.assertIn("换色复测失败",chat.call_args.args[1][-1]["content"])

    def test_real_model_functional_if_is_normalized_and_stays_lazy(self):
        spec, fn = validation.spec(program("if(key_on, c1, if(key_release_age < 10, c1, rgb(0,0,0)))", checks=[]))
        self.assertNotIn("if(", spec["expression"])
        self.assertIn(" else ", spec["expression"])
        self.assertEqual(render(spec, {"held":{65}})[led(65)], (240,40,20))
        self.assertEqual(render(spec)[led(65)], (0,0,0))
        # The unused division branch must not execute eagerly.
        from kbdrv.expr import normalize_expression, compile_expression
        normalized=normalize_expression("if(1, rgb(1,2,3), 1/0)")
        self.assertEqual(compile_expression(normalized)(0,0,0,0,0,0), (1,2,3))
        for source in ("if(1, __import__(1), 0)", "if(1,c1.__class__,0)", "if(1,c1[0],0)"):
            with self.assertRaises(ValueError):
                validation.spec(program(source,checks=[]))

    def test_symbolic_palette_checks_do_not_invent_fixed_red_blue_colors(self):
        spec, fn=validation.spec(program("c1",checks=[{"keys":[],"expect":[{"vk":65,"palette":"primary"}]}]))
        verify(spec,fn)

    def test_audio_assertions_supply_real_renderer_inputs(self):
        from kbdrv.program import validate_checks
        audio={"levels":[.5]*22,"pulse":.8,"energy":.5,"beat":1}
        checks=[{"keys":[],"expect":[],"others_off":True,"audio":{"levels":[0]*22}},
                {"keys":[],"expect":[{"vk":65,"state":"on","palette":"primary"}],"audio":audio}]
        spec,fn=validation.spec(program("mix(grey(0),c1,level)",checks=checks))
        verify(spec,fn)
        for invalid in ({"levels":[]},{"levels":[2]*22},{"pulse":float('nan')},[],{"unknown":1}):
            with self.assertRaises(ValueError):
                validate_checks([{"expect":[],"others_off":True,"audio":invalid}])
        spec["color"]=[10,50,90]
        verify(spec,fn)

    def test_empty_expect_with_others_off_means_entire_board_dark(self):
        from kbdrv.program import validate_checks
        all_dark = {"label":"整块键盘全黑","keys":[],"expect":[],"others_off":True}
        validate_checks([all_dark])
        checked, fn = validation.spec(program("grey(0)", checks=[all_dark]))
        verify(checked, fn)
        checked, fn = validation.spec(program("c1", checks=[all_dark]))
        with self.assertRaisesRegex(ValueError,"其他灯位"):
            verify(checked, fn)
        for invalid in ({"keys":[],"expect":[]}, {"keys":[],"expect":[],"others_off":False}):
            with self.assertRaises(ValueError):
                validate_checks([invalid])

    def test_release_contract_requires_a_possible_time_line(self):
        from kbdrv.program import validate_checks
        case={"keys":[{"vk":65,"held":False,"age":.5,"release_age":10}],
              "expect":[],"others_off":True}
        with self.assertRaisesRegex(ValueError,"松开后的时间不能大于"):
            validate_checks([case])
        case["keys"][0].update(age=12)
        validate_checks([case])
        # During a second press, the previous release can be older than this press.
        case["keys"][0].update(held=True,age=1,release_age=2)
        validate_checks([case])

    def test_single_key_ten_seconds_is_independent_and_never_spreads(self):
        spec = ai._normalise(program())
        for a,b,lit in ((0,1,{65,66}),(9.99,5,{65,66}),(10,5,{66}),(11,10,set())):
            with self.subTest(a=a,b=b):
                frame = render(spec,{"ages":{65:a,66:b},"held":set(),"counts":{65:1,66:1}})
                self.assertEqual({i for i,rgb in enumerate(frame) if max(rgb)>0},{led(vk) for vk in lit})

    def test_hold_release_timing_toggle_and_specific_key_mapping_are_distinct(self):
        held_only = program("c1 if key_on else grey(0)",checks=[])
        self.assertEqual(render(held_only,{"held":{65}})[led(65)],(240,40,20))
        self.assertEqual(max(map(max,render(held_only,{"held":set(),"ages":{65:.01}}))),0)
        after_release = program("c1 if key_on or key_release_age < 10 else grey(0)",checks=[])
        self.assertEqual(render(after_release,{"ages":{65:100},"held":{65}})[led(65)],(240,40,20))
        self.assertEqual(render(after_release,{"ages":{65:109},"releases":{65:9}})[led(65)],(240,40,20))
        self.assertEqual(render(after_release,{"ages":{65:110},"releases":{65:10}})[led(65)],(0,0,0))
        mapping = program("c2 if down(65) and row == keyrow(66) and col == keycol(66) else grey(0)",checks=[])
        frame = render(mapping,{"held":{65}})
        self.assertEqual({i for i,c in enumerate(frame) if max(c)},{led(66)})
        toggle = program("c1 if mod(key_count,2) else grey(0)",checks=[])
        self.assertEqual(render(toggle,{"counts":{65:2}})[led(65)],(0,0,0))
        self.assertEqual(render(toggle,{"counts":{65:3}})[led(65)],(240,40,20))

    def test_parameter_controls_change_actual_color_duration_and_brightness(self):
        spec = program()
        self.assertGreater(max(render(spec,{"ages":{65:6}},speed=1)[led(65)]),0)
        self.assertEqual(render(spec,{"ages":{65:6}},speed=2)[led(65)],(0,0,0))
        changed = {**spec,"color":[40,80,160]}
        self.assertEqual(render(changed,{"ages":{65:0}},brightness=.5)[led(65)],(20,40,80))
        second = program("c2 if key_on else grey(0)",color2=[100,120,140],checks=[])
        self.assertEqual(render(second,{"held":{65}})[led(65)],(100,120,140))

    def test_claimed_no_spread_is_checked_against_pixels(self):
        with self.assertRaisesRegex(ValueError,"其他灯位|语义断言"):
            ai._normalise(program("c1 if last_age < 10 else grey(0)"))
        with self.assertRaisesRegex(ValueError,"语义断言"):
            ai._normalise(program("c1 if key_age < 2 else grey(0)"))

    def test_new_generation_rejects_presets_and_repairs_the_program(self):
        with patch.object(ai,"chat_messages",side_effect=[json.dumps({"summary":"十秒单键不扩散","checks":program()["checks"]}),json.dumps({"kind":"preset","effect":"ripple"}),json.dumps(program())]) as chat:
            result = ai.generate("按哪个键只亮哪个键，十秒熄灭不扩散",{})
        self.assertEqual(result["kind"],"program")
        self.assertIn("禁止",chat.call_args.args[1][-1]["content"])

    def test_bad_semantics_repair_is_required_before_returning_work(self):
        wrong = program("c1 if key_age < 1 else grey(0)")
        with patch.object(ai,"chat_messages",side_effect=[json.dumps({"summary":"十秒才熄灭","checks":program()["checks"]}),json.dumps(wrong),json.dumps(program())]) as chat:
            result = ai.generate("十秒才熄灭",{})
        self.assertEqual(chat.call_count,3)
        self.assertIn("10",result["expression"])
        self.assertIn("语义断言失败",chat.call_args.args[1][-1]["content"])

    def test_live_audio_uses_real_inputs_and_is_black_in_silence(self):
        spec = program("mix(grey(0),mix(c1,c2,level),pulse)",checks=[])
        _,fn = validation.spec(spec)
        self.assertTrue(fn.needs_audio)
        dark = effects.render("ai",0,expr=fn,audio_pulse=0,levels=[0]*22)
        lit = effects.render("ai",0,expr=fn,audio_pulse=.8,levels=[.5]*22)
        self.assertEqual(max(map(max,dark)),0)
        self.assertGreater(max(map(max,lit)),0)

    def test_program_share_roundtrip_keeps_behavior_without_private_checks(self):
        spec = ai._normalise(program())
        snap = {"params":{**validation.DEFAULT_PARAMS,"effect":"ai","color":spec["color"],"color2":spec["color2"]},"ai_spec":spec}
        decoded = sharing.decode(sharing.encode(snap,"十秒",sharing.layout(5,22,1)))
        restored = decoded["snapshot"]["ai_spec"]
        self.assertEqual(restored["kind"],"program")
        self.assertNotIn("checks",restored)
        self.assertEqual(render(restored,{"ages":{65:5}})[led(65)],(240,40,20))

    def test_hook_held_repeat_release_and_retrigger_feed_the_same_program(self):
        hook = input_hook.KeyHook()
        info = input_hook.KBDLLHOOKSTRUCT(vkCode=65)
        with patch.object(input_hook.user32,"CallNextHookEx",return_value=0):
            hook._callback(0,input_hook.WM_KEYDOWN,ctypes.addressof(info))
            hook._callback(0,input_hook.WM_KEYDOWN,ctypes.addressof(info))
            self.assertEqual(hook.snapshot()["counts"][65],1)
            self.assertIn(65,hook.snapshot()["held"])
            hook._callback(0,input_hook.WM_KEYUP,ctypes.addressof(info))
            self.assertNotIn(65,hook.snapshot()["held"])
            self.assertLess(hook.snapshot()["releases"][65],1)
            hook._callback(0,input_hook.WM_KEYDOWN,ctypes.addressof(info))
            self.assertEqual(hook.snapshot()["counts"][65],2)
        hook.stop()
        self.assertEqual(hook.snapshot()["ages"],{})

    def test_program_ast_does_not_allow_io_imports_or_unbounded_math(self):
        for source in ("__import__(1)","c1.__class__","down(65).__class__","(1,2)","pow(9,1000)","[c1 for x in c2]"):
            with self.subTest(source=source),self.assertRaises(ValueError):
                Program(source)

    def test_all_entry_points_reject_latent_z_branch_math_failure(self):
        source = 'c1 if not down(90) else 1/0'
        with self.assertRaises(ValueError):
            validation.spec({'kind':'program','expression':source})

    def test_implementation_cannot_weaken_previously_interpreted_ten_second_contract(self):
        correct_checks = program()['checks']
        wrong = program('c1 if key_on else grey(0)',checks=[correct_checks[0]])
        with patch.object(ai,'chat_messages',side_effect=[json.dumps({'summary':'按下后十秒才熄灭，不扩散','checks':correct_checks}),json.dumps(wrong),json.dumps(program())]) as chat:
            result = ai.generate('按下后亮十秒，不扩散',{})
        self.assertEqual(chat.call_count,3)
        self.assertEqual(result['checks'],correct_checks)
        self.assertIn('key_age',result['expression'])

    def test_non_object_model_output_enters_repair_instead_of_crashing(self):
        with patch.object(ai,'chat_messages',side_effect=[json.dumps({'summary':'原要求','checks':[]}), '[]', json.dumps(program('c1',checks=[]))]) as chat:
            result = ai.generate('全键盘常亮',{})
        self.assertEqual(chat.call_count,3)
        self.assertEqual(result['kind'],'program')

    def test_time_only_singularity_is_rejected_on_import_and_apply(self):
        with self.assertRaises(ValueError):
            validation.spec({'kind':'program','expression':'c1 if t < 4 else grey(1/(t-4))'})

    def test_malformed_contract_is_repaired_before_it_is_frozen(self):
        with patch.object(ai,'chat_messages',side_effect=[json.dumps({'summary':'白光','checks':[None]}),json.dumps({'summary':'白光','checks':[]}),json.dumps(program('c1',checks=[]))]) as chat:
            result = ai.generate('白色常亮',{})
        self.assertEqual(chat.call_count,3)
        self.assertTrue(chat.call_args_list[1].kwargs.get('system_prompt'))
        self.assertEqual(result['checks'],[])

    def test_hardcoded_palette_cannot_be_accepted_as_adjustable_creation(self):
        with self.assertRaisesRegex(ValueError,'可调主色'):
            ai._normalise(program('rgb(255,0,0)',checks=[]))
        with self.assertRaisesRegex(ValueError,'没有响应'):
            ai._normalise(program('mix(rgb(255,0,0),c1,0)',checks=[]))

    def test_requested_rgb_is_compared_with_rendered_pixels(self):
        spec = program('c1',color=[255,0,0],checks=[{'label':'用户要蓝色','expect':[{'vk':65,'rgb':[0,0,255]}]}])
        with self.assertRaisesRegex(ValueError,'配色断言'):
            ai._normalise(spec)
