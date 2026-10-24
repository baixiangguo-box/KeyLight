"""User-owned creation loop: fake model, local rendering, no hardware or fees."""
import copy
import json
import threading
import time
import unittest
from unittest.mock import patch

from kbdrv import ai, creator
from tests.test_program import program


def work(**patches):
    return program(**{"expression":"c1","checks":[],**patches})


def route(action="build",reply="我理解了"):
    return json.dumps({"action":action,"reply":reply})


def intent(spec):
    return json.dumps({"summary":"按用户明确需求创作","checks":spec["checks"],"controls":{}})


def wait(session):
    end=time.monotonic()+5
    while session.busy() and time.monotonic()<end:time.sleep(.01)
    if session.busy():raise AssertionError("creator job timed out")
    return session.view()


class CreatorTests(unittest.TestCase):
    def test_cancelled_network_workers_are_bounded_until_they_finish(self):
        session=creator.Session(draft=work());release=threading.Event()
        def slow(*args,**kwargs):
            release.wait(2);return {"action":"discuss","reply":"late","calls":1}
        with patch.object(creator,"turn",side_effect=slow):
            for _ in range(2):session.submit("修改",{});session.cancel()
            with self.assertRaisesRegex(ValueError,"网络请求"):
                session.submit("第三个请求",{})
            self.assertEqual(session.workers,2);release.set()
            for _ in range(50):
                if not session.workers:break
                time.sleep(.01)
        self.assertEqual(session.workers,0)

    def test_invalid_intent_feedback_is_preserved_for_the_next_turn(self):
        session=creator.Session(draft=work())
        with patch.object(ai,"chat_messages",side_effect=[route(),'{"summary":"bad","checks":"invalid"}','{"summary":"bad","checks":"invalid"}']):
            session.submit("修改预览",{});view=wait(session)
        self.assertEqual(view["draft"]["expression"],"c1")
        self.assertEqual(view["diagnostics"]["stage"],"intent")
        self.assertEqual(view["diagnostics"]["candidate"]["checks"],"invalid")

    def test_failed_manual_save_restores_previous_draft(self):
        session=creator.Session(draft=work(),on_save=lambda:(_ for _ in ()).throw(OSError("disk")))
        with self.assertRaisesRegex(ValueError,"已撤回"):
            session.edit(patch={"brightness":.2})
        self.assertEqual(session.view()["draft"]["brightness"],1)

    def test_interrupted_saved_creation_restores_previous_draft_and_explains(self):
        session=creator.Session({"draft":work(),"history":[],"interrupted":True})
        self.assertFalse(session.busy());self.assertEqual(session.view()["draft"]["expression"],"c1")
        self.assertIn("关闭软件时停止",session.view()["history"][-1]["content"])

    def test_plain_discussion_and_clarification_never_build_a_draft(self):
        for action in ("discuss","clarify"):
            with patch.object(ai,"chat_messages",return_value=route(action,"你想从哪里开始？")) as model:
                result=creator.turn("先聊方案",{},work(),[])
            self.assertEqual(model.call_count,1);self.assertEqual(result["action"],action)
            self.assertNotIn("spec",result)

    def test_clear_description_builds_without_a_second_button(self):
        spec=work()
        with patch.object(ai,"chat_messages",side_effect=[route(),intent(spec),json.dumps(spec)]) as model:
            result=creator.turn("全键主色常亮",{},None,[])
        self.assertEqual(result["spec"]["expression"],"c1")
        self.assertEqual(model.call_count,3)
        self.assertIn("预览已更新",result["reply"])
        self.assertNotIn("已应用",result["reply"])

    def test_runtime_error_is_automatically_repaired_in_the_same_turn(self):
        spec=work();bad={**spec,"expression":"1/0"};events=[]
        with patch.object(ai,"chat_messages",side_effect=[route(),intent(spec),json.dumps(bad),json.dumps(spec)]) as model:
            result=creator.turn("白光常亮",{},None,[],progress=lambda stage,data:events.append(stage))
        self.assertEqual(result["spec"]["expression"],"c1")
        self.assertIn("repairing",events)
        self.assertIn("division",model.call_args.args[1][-1]["content"])

    def test_bad_route_format_is_repaired_before_designing(self):
        with patch.object(ai,"chat_messages",side_effect=['plain text',route("discuss","可以先讨论")]) as model:
            result=creator.turn("给点建议",{},None,[])
        self.assertEqual(model.call_count,2);self.assertEqual(result["action"],"discuss")

    def test_contract_review_corrects_a_bad_boundary_without_deleting_tests(self):
        correct=program("c1 if key_on or key_release_age < 10 else c2",checks=[
            {"keys":[],"expect":[{"vk":65,"palette":"secondary"}]},
            {"keys":[{"vk":65,"held":True,"age":20}],"expect":[{"vk":65,"palette":"primary"}]},
            {"keys":[{"vk":65,"held":False,"age":30,"release_age":10}],"expect":[{"vk":65,"palette":"secondary"}]},
        ])
        wrong=copy.deepcopy(correct);wrong["checks"][2]["expect"][0]["palette"]="primary"
        revised={"summary":"到期回副色","checks":correct["checks"],"controls":{}}
        audit={"decision":"contract","reason":"边界期望和原话相反","user_quote":"到期回副色","intent":revised}
        replies=[route(),intent(wrong),*[json.dumps(correct)]*3,json.dumps(audit),json.dumps(correct)]
        with patch.object(ai,"chat_messages",side_effect=replies) as model:
            result=creator.turn("松开10秒到期回副色",{},None,[])
        self.assertEqual(model.call_count,7);self.assertEqual(result["spec"]["checks"],correct["checks"])

    def test_review_cannot_drop_failed_expectations_or_change_controls(self):
        old={"summary":"用户原意","checks":program()["checks"],"controls":{"brightness":.4}}
        for fixed in ({**old,"checks":[]},{**old,"controls":{"brightness":1}}):
            with self.assertRaises(ValueError):
                creator.revised_intent({"user_quote":"十秒","intent":fixed},old,[{"role":"user","content":"只亮十秒"}])
        with self.assertRaisesRegex(ValueError,"原话"):
            creator.revised_intent({"user_quote":"用户没有说过","intent":old},old,[{"role":"user","content":"只亮十秒"}])

    def test_feedback_and_preview_are_sent_with_the_actual_draft(self):
        feedback={"candidate":{"expression":"1/0"},"errors":["division by zero"]}
        observation={"source":"local_simulated_preview","samples":[{"vk":65,"rgb":[1,2,3]}]}
        with patch.object(ai,"chat_messages",return_value=route("discuss","看到了实际反馈")) as model:
            creator.turn("为什么不对",{},work(),[],feedback,observation)
        context=json.loads(model.call_args.args[1][0]["content"].split("：",1)[1])
        self.assertEqual(context["last_failure"],feedback);self.assertEqual(context["local_preview"],observation)
        self.assertEqual(context["current_draft"]["expression"],"c1")

    def test_cancelled_response_cannot_replace_a_draft_or_restart_a_cancelled_job(self):
        entered=threading.Event();release=threading.Event()
        session=creator.Session(draft=work())
        def slow(*args,**kwargs):
            entered.set();release.wait(3);return {"action":"build","spec":work(expression="c2"),"reply":"done","calls":1}
        with patch.object(creator,"turn",side_effect=slow):
            session.submit("改成副色",{});self.assertTrue(entered.wait(1))
            session.cancel();session.edit(reset=True);release.set()
            time.sleep(.08)
        self.assertIsNone(session.view()["draft"]);self.assertEqual(session.view()["history"],[])

    def test_failed_creation_preserves_draft_and_keeps_diagnostics_for_the_next_message(self):
        session=creator.Session(draft=work());failure=ai.AIError("bad program")
        failure.details={"candidate":{"expression":"1/0"},"errors":["division"]}
        with patch.object(creator,"turn",side_effect=failure):
            session.submit("修改",{});view=wait(session)
        self.assertEqual(view["draft"]["expression"],"c1");self.assertEqual(view["job"]["state"],"failed")
        self.assertIn("candidate",view["diagnostics"])
        self.assertNotIn("开发者",view["history"][-1]["content"])
        with patch.object(creator,"turn",return_value={"action":"discuss","reply":"已看到失败候选","calls":1}) as model:
            session.submit("哪里不对",{});wait(session)
        self.assertEqual(model.call_args.args[4],failure.details)

    def test_undo_and_restart_restore_draft_without_any_apply_callback(self):
        session=creator.Session(draft=work());saved=[];session.on_save=lambda:saved.append(session.export())
        with patch.object(creator,"turn",return_value={"action":"build","spec":work(expression="c2"),"reply":"预览更新","calls":1}):
            session.submit("改副色",{});view=wait(session)
        self.assertEqual(view["undo"],1)
        restored=creator.Session(saved=saved[-1]);self.assertEqual(restored.draft["expression"],"c2")
        restored.edit(undo=True);self.assertEqual(restored.draft["expression"],"c1")

    def test_saving_failure_does_not_leave_an_unstarted_job_busy(self):
        session=creator.Session(on_save=lambda:(_ for _ in ()).throw(PermissionError("denied")))
        with self.assertRaisesRegex(ValueError,"保存"):
            session.submit("白光",{})
        self.assertFalse(session.busy());self.assertEqual(session.view()["history"],[])

    def test_credentials_are_redacted_from_persisted_failure_feedback(self):
        session=creator.Session();secret="NOT_A_REAL_KEY"
        with patch.object(creator,"turn",side_effect=ai.AIError("接口返回401 "+secret)):
            session.submit("白光",{"api_key":secret});wait(session)
        self.assertNotIn(secret,json.dumps(session.export()))
        self.assertIn("接口设置",session.view()["history"][-1]["content"])


if __name__=="__main__":unittest.main()
