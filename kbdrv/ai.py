"""Natural-language lighting effects via any OpenAI-compatible chat API."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from .expr import DSL_GUIDE, ExpressionError, compile_expression
from .design import compile_design
from .program import GUIDE as PROGRAM_GUIDE

DEFAULT_BASE = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
TIMEOUT = 60
MAX_HISTORY = 10

CONVERSATION_PROMPT = """你是用户正在使用的键光软件中的灯效创作助手，与用户直接用自然语言对话。
请正常回复中文，可以讨论方案、解释效果、回答追问，在确实缺少关键条件时简短询问。
需求已经明确时直接准确复述方案，不要反复让用户补充同一信息。用户可以连续改变想法。
这是从零编写自定义灯效的功能，不能用现成涟漪等内置方案冒充用户要求。
可设计逐键颜色、按住/按下/松开后的独立计时、重复按键重计时、指定键控制另一键、
计数切换、空间动画、随系统声音能量和频段变化的动画；主副色、速度和亮度可在界面调整。
明确区分按下起计时与松开起计时、不扩散与波纹扩散。多个键可以分别保持与熄灭。
用户看到你的这条回复只是对话；只有点击“按对话生成光效”后软件才生成并应用预览。
不要假称已经应用、保存或实测成功，也不要直接输出 JSON、代码或内部验收表。
用户没有要求技术细节时，用日常语言解释按键和灯光行为，不展示变量名或公式。
如果有【程序反馈】生成失败，诚实解释该反馈中已知原因，不能把格式/校验问题归咎用户描述。
没有原始诊断给出的场景编号或失败程序源码时，不得编造编号、检查点或断言根因。
颜色不符合期望可能是状态/计时分支、灯位或验收条件错误，不能直接推断为固定颜色。
失败后当前作品仍是上一版；不能把当前旧公式说成失败那版的公式，也不能把猜测当作已查明。
软件通过安全的逐灯位程序运行，无法刷入任意键盘固件；自由动态效果需要软件运行。
不要索要API密钥或其他凭据。颜色以用户原话为准，参考配色只作补充。
"""

INTENT_PROMPT = """你负责理解键盘光效的用户意图并制定独立验收，暂不设计实现或选择内置效果。
只返回 JSON 对象：summary（一句准确复述需求）、checks（渲染断言数组）、controls（明确指定的界面参数）。
controls 只允许 color/color2（RGB数组）、brightness（0到1）、speed（0.05到3）。
用户明确说整体亮度60%，则 controls.brightness=0.6；纯白主色则 color=[255,255,255]。
后续修改时，保留当前实际作品中用户未要求改变的这些参数。未明确指定的参数可省略。
旧作品 checks 只是历史记录，可能包含旧颜色或旧速度，不可照抄；以当前实际参数和最新要求重建验收。
亮度/速度必须体现为界面参数，不能烘焙进表达式后把界面显示成另一数值。
这是从零定制功能。当前作品快照和用户最新要求优先；后续修改只改用户要求部分。
不要预先假定波动、涟漪、扩散或全键盘亮，不要把“按哪个键亮哪个键”误读为波纹。
精确区分：按下起计时/松开起计时；按住才亮/按一次保持；指定键控制另一个键；
不扩散/允许扩散；每个键独立计时/共用最后按键；重复按下重新计时/再次切换。
每个 check：{label,t,time_unit,keys:[{vk,held,age,count,release_age}],expect:[{vk,state}],others_off}。
vk 是 Windows 虚拟键码：A65 B66 W87 S83 D68 空格32 回车13 左Shift160 右Shift161。
age 是从最近按下起的实际秒数；release_age 是最近松开后秒数，从未松开须省略。
time_unit默认"seconds"，上述t/age/release_age均为实际秒；也可以用"program"，三者均直接写受速度缩放后的程序秒。
若时长按速度缩放，尤其speed不是1时，必须用time_unit:"program"表达边界，不要手算除法并截断小数！
例如基准10程序秒、速度3，刚到期用time_unit:"program",release_age:10，临界前用9.99，临界后用10.01。
不能用实际3.333秒期待10程序秒到期，3.333*3仅9.999，仍未到期。执行器会按真实速度换算程序秒。
若用户指定不受速度影响的实际时长，则使用seconds并把实际时长保持准确；不要混用两种单位。
未按过用 keys=[]。expect 使用 state=on/off，可用 row/col 替代 vk 指定灯位。
others_off=true 表示指定 expect 灯位之外全部灯位应黑，用户要求不扩散时必须检验。
注意：整块键盘亮、棋盘格一整组亮时，只列几个代表灯位来抽查，必须 others_off:false；
不能把未列出的其他本应发光的灯误写成全灭。others_off:true 仅用于明确限定发光范围或全黑。
全黑场景应使用 expect:[] 和 others_off:true，表示整块键盘没有任何亮灯，这是合法验收。
真实时间必须自洽：松开后的 release_age 不得大于 age；age 要包含按住期间和松开后的总时长。
例如按住2秒再松开，松开后9秒的状态应为 age:11,release_age:9，而不是 age:2,release_age:9。
到期时立即熄灭：用户说保持10秒，则9.99秒应亮、10秒及之后应灭，不能同一边界又亮又灭。
多键独立计时场景应让两个键具有不同的 release_age，例如 A=10秒应灭、B=5秒应亮；
不能给 A/B 同样的10秒释放年龄，却期望A灭B亮。
若用户明确指定颜色，在 expect 添加 rgb:[r,g,b] 验证实际配色，不能仅验证亮灭。考虑用户指定亮度。
rgb 是最终输出（包含总体亮度），不是原始选色。例如纯白在40%亮度下为 [102,102,102]。
用户只说主色/副色而没有明确RGB时，不要虚构固定红色或蓝色验收，可加 palette:"primary" 或 "secondary"。
提到界面主色/副色时必须用 palette，不可把其当前RGB值写成固定rgb断言。
若用户指定主副色的具体颜色，放在controls.color/color2，验收仍用palette以便后续调色。
palette 表示主副色的色相，允许随声音或动画变暗；需要精确亮度时另用 rgb。
纯主/副色保持、到点切换、不渐暗时，加 palette_exact:true，检验所选颜色经整体亮度后的完整输出；
呼吸、音频或渐暗等允许变化的场景不要加此标记。所有palette检查会在换主副色后再次执行。
音频需求的每条验收必须提供 audio:{levels:[22个0到1的频段能量],pulse:0到1,energy:0到1,beat:节拍次数}。
静音场景全部为0；有声场景必须明确频段数组，不能只用 t 时间假装声音输入。
例如左低频亮、右高频暗，可令levels前11列为1、后11列为0，再抽查左右灯位亮灭与palette。
区域/频段光效请使用 row/col 定位验收，不用猜测字母键的位置。灯阵为5行22列，
左半区 col=0..10，右半区 col=11..21；A/W/S/D/B都在左半区，不是右半区。
低音量变暗不等于全灭；用户没要求门限时，非零音量不要擅自添加强制熄灭的断言。
按键需求必须含未按、按住、松开；有持续时限需检验到期前后；独立计时需要 A/B不同年龄；
切换需要第二次、第三次按下。保持用户原话时长，不擅自缩短。不凭空增加未要求的行为。
纯动画不必强行设置按键断言，可 checks=[]。checks 最多16项，label必须是中文用户要求。
这份验收之后交给另一轮编写，写程序时不得改动这些条件。
"""

SYSTEM_PROMPT = f"""你是一个机械键盘灯效设计师，和用户一起迭代打磨光效。
把用户的自然语言变为可运行的灯效方案。用户不用懂代码，能不断用自然语言改进作品。

键盘是 5 行 x 22 列的灯阵（60% 配列，上方 F 行没有灯）。

{PROGRAM_GUIDE}

高级表达式兼容说明：
{DSL_GUIDE}

要求：
1. 只输出一个 JSON 对象，不要 markdown 代码块，不要多余文字。
2. 所有新建与修改只允许从零编写 kind=program 的完整表达式，不得使用 preset/layers 或内置效果。
   输出格式：
   {{"name": "四到八个字的中文名字",
     "kind": "program",
     "expression": "一段表达式",
     "color": [255,90,60], "color2": [30,123,255],
     "speed": 0.05 到 3.0 之间的数字,
     "brightness": 0 到 1.0 之间的数字,
     "explain": "一句话说明这个效果",
     "change": "如果是在改上一版，一句话说明改了什么；新生成则留空"}}
3. 表达式里不要有换行，不要用 for/while/lambda/赋值，只能用上面列出的变量和函数。
   使用 Python 条件表达式：成立值 if 条件 else 否则值；如 c1 if key_on else rgb(0,0,0)。
   逻辑运算用 and/or/not，比较用 ==；不要使用JavaScript的?:、&&、||或箭头函数。
   函数式 if(条件,成立值,否则值) 也会安全转为同一种条件表达式，但优先使用上述Python写法。
4. 尊重用户描述，包括静态、低亮度、局部亮、方向和保留部分。未要求变化的部分保持原样。
   精确区分按住、按一次、松开、淡出、保持时长、指定键与全部键；实时输入都由程序读取。
   独立验收中的 controls 是必须一致的界面参数。整体亮度由 brightness 统一作用一次；
   不要再在表达式里乘同一整体亮度，否则会重复变暗。局部背景衰减或音量变化可以写入表达式。
5. 不要使用 x**0.5 这类写法，用 sqrt()；除法分母不要为 0。
6. 当用户对上一版提出修改时，在上一版表达式基础上改，保留用户认可的部分，
   名字一般保持不变，只有整体方向变了才改名。当前作品快照优先于历史记录，包含用户手动调整。
7. explain 清楚说明效果；change 用中文说明本轮改动，不要提公式、验证、内部实现。
8. 高级表达式最多 2000 字、256 个语法节点、嵌套 24 层；RGB 是颜色三元组，
   不能直接与数字乘除或与其他颜色相加；调暗用 mix(rgb(0,0,0),颜色,亮度)，混色用 mix。
   数值必须有限且绝对值不超过 1e12。除法分母须保护，sqrt 输入须非负，避免 exp/tan。
9. 同时输出 checks 数组，把用户的要求转成可验证的渲染断言；输入类程序必须提供。
   每项为 {{"label":"对应用户哪条要求", "t":0, "keys":[{{"vk":65,"held":true,"age":0.1,"count":1}}],
   "expect":[{{"vk":65,"state":"on"}}], "others_off":true}}。
   state 可为 on/off；可用 row/col 指定灯位。others_off=true 表示 expect 指定灯位外全灭。
   keys 为空表示从未按过。vk 为 Windows 键码。age 为实际秒数，held 为当前是否按住。
   release_age 为最近松开后实际秒数（从未松开省略）。按下计时与松开计时不能混淆。
   按键要求必须验证未按、按下、松开、时间边界以及是否允许扩散；切换还验证第二次按下。
   不扩散时必须含 others_off 的断言，按用户要求的十秒等时间必须检验到期前后。
   若不能同时满足要求，修正程序，不能修改断言来掩盖错误或仅在说明里声称已做到。
10. 只要要求使用主/副色，相应的每个分支都直接引用 c1/c2；不能把当前RGB常量当作它们。
    按住、松开后的保持期、到期返回及未按过的背景都会换色复测，不能只让一个分支可调色。
    若报配色不符，先核对状态与计时条件、灯位、速度影响，不能只替换一个RGB值就声称修复。
"""


class AIError(RuntimeError):
    pass


def _endpoint(base: str) -> str:
    base = (base or DEFAULT_BASE).strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def chat_messages(config: dict, messages: list[dict], *, system_prompt=None) -> str:
    api_key = (config.get("api_key") or "").strip()
    if not api_key:
        raise AIError("还没有填写 API Key")
    model = (config.get("model") or DEFAULT_MODEL).strip()
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt or SYSTEM_PROMPT}, *messages],
        "temperature": 0.4,
        "max_tokens": 3200,
    }
    req = urllib.request.Request(
        _endpoint(config.get("base_url") or DEFAULT_BASE),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        raise AIError(f"接口返回 {exc.code}: {detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise AIError(f"请求失败: {exc}") from exc

    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AIError(f"返回格式异常: {str(body)[:200]}") from exc


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        snippet = text[start:end + 1]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError as exc:
            raise AIError(f"AI 返回的不是合法 JSON: {snippet[:200]}") from exc
    raise AIError("AI 没有返回 JSON")


def _normalise(spec: dict) -> dict:
    from .validation import spec as validate_spec
    if not isinstance(spec, dict):
        raise ExpressionError("AI 必须返回 JSON 对象")
    if spec.get("kind") == "layers":
        spec = compile_design(spec)
    name = str(spec.get("name") or "AI 光效").strip()[:24]
    kind = str(spec.get("kind") or "expression").strip()
    if kind == "program":
        result = {k:spec[k] for k in ("expression", "color", "color2", "speed", "brightness",
                                     "explain", "change", "checks") if k in spec}
        result.update(kind="program", name=name)
        from .program import verify, verify_palette
        checked, fn = validate_spec(result)
        verify(checked, fn)
        verify_palette(checked, fn)
        return checked
    if kind != "expression" and spec.get("effect"):
        result = {
            "ok": True, "kind": "preset", "name": name,
            "effect": str(spec.get("effect")),
            "color": spec.get("color") or [255, 120, 60],
            "color2": spec.get("color2") or [40, 110, 255],
            "speed": spec.get("speed", 1.0),
            "brightness": spec.get("brightness", 1.0),
            "audio_style": spec.get("audio_style", "staggered"),
            "explain": str(spec.get("explain") or ""),
            "change": str(spec.get("change") or ""),
        }
        try:
            return validate_spec(result)[0]
        except (ValueError, TypeError) as exc:
            raise ExpressionError(str(exc)) from exc
    expression = str(spec.get("expression") or "").strip()
    if not expression:
        raise AIError("AI 没有给出表达式")
    result = {
        "ok": True, "kind": "expression", "name": name, "expression": expression,
        "speed": spec.get("speed", 1.0),
        "brightness": spec.get("brightness", 1.0),
        "explain": str(spec.get("explain") or ""),
        "change": str(spec.get("change") or ""),
    }
    if "design" in spec:
        compiled = compile_design(spec["design"])
        # A legacy expression edit may still carry the old design metadata.
        if expression == compiled["expression"]:
            result["design"] = compiled["design"]
    try:
        checked, fn = validate_spec(result)
        # Validate every LED at several times, including a later playback point.
        for rows in (5, 6):
            for row in range(rows):
                for col in range(22):
                    for t in (0, 0.13, 0.7, 1.4, 3.1, 11.9, 60):
                        fn(col / 21, row / (rows-1), row*22+col, row, col, t, rows=rows)
        return checked
    except (ValueError, TypeError) as exc:
        raise ExpressionError(str(exc)) from exc


def _run(config: dict, messages: list[dict], retry_note: str | None = None,
         *, request=None, on_progress=None, intent_override=None) -> dict:
    # Interpret before implementing: the implementation cannot weaken its tests.
    request=request or chat_messages
    progress=on_progress or (lambda *_args,**_kwargs:None)
    intent = intent_override
    intent_error = ""
    for attempt in range(0 if intent is not None else 2):
        progress("understanding",{"attempt":attempt+1})
        raw_intent = request(config, list(messages), system_prompt=INTENT_PROMPT)
        candidate=None
        try:
            candidate = _extract_json(raw_intent)
            if not isinstance(candidate,dict) or not isinstance(candidate.get("summary"),str) or not candidate["summary"].strip():
                raise ValueError("需要 summary 准确复述用户要求")
            checks = candidate.get("checks")
            from .program import validate_checks
            validate_checks(checks)
            controls = candidate.get("controls", {})
            if not isinstance(controls, dict) or set(controls)-{"color","color2","brightness","speed"}:
                raise ValueError("controls 只能包含主副色、亮度和速度")
            from .validation import params as validate_params
            normalized_controls = validate_params(controls)
            controls = {key:normalized_controls[key] for key in controls}
            intent = {"summary":candidate["summary"][:1500],"checks":checks,"controls":controls}
            break
        except (ValueError,TypeError,AIError) as exc:
            intent_error = str(exc)
            print(f"[AI intent] attempt={attempt+1} validation_error={intent_error}", flush=True)
            if attempt == 1:
                failure=AIError(f"AI 已返回回复，但验收数据未通过检查：{intent_error}。上一版光效已保留，请重试。")
                failure.details={"stage":"intent","candidate":candidate,"errors":[intent_error],"raw":raw_intent[:6000]}
                raise failure from None
            messages = [*messages, {"role":"user", "content":f"验收 JSON 格式错误：{exc}。请修正验收结构，保持原始用户要求。"}]
    repair = [*messages, {"role":"user","content":"先前独立整理的验收条件（必须保留并满足，不能修改断言来适应错误程序）："+
                          json.dumps(intent,ensure_ascii=False)}]
    errors=[]
    for attempt in range(3):
        progress("designing" if attempt==0 else "repairing",{"attempt":attempt+1,"intent":intent})
        raw = request(config, list(repair))
        value=None
        try:
            value = _extract_json(raw)
            if not isinstance(value, dict):
                raise ExpressionError("AI 必须返回 program JSON 对象")
            if value.get("kind") != "program":
                raise ExpressionError("必须从零设计 kind=program，禁止采用内置 preset/layers 或旧方案")
            value["checks"] = intent["checks"]
            progress("checking",{"attempt":attempt+1})
            checked = _normalise(value)
            for key, wanted in intent["controls"].items():
                actual = checked.get(key)
                if (actual != wanted if isinstance(wanted,list) else abs(actual-wanted)>1e-8):
                    raise ExpressionError(f"界面参数 {key} 必须为 {wanted}，不能将该设置烘焙到公式后改成 {actual}")
            checked["intent"] = intent["summary"]
            return checked
        except (ValueError, TypeError, AIError, RecursionError) as exc:
            errors.append(str(exc))
            progress("repairing",{"error":str(exc),"attempt":attempt+1})
            print(f"[AI implementation] attempt={attempt+1} validation_error={exc}",flush=True)
            if attempt == 2:
                failure=AIError(f"生成未完成，程序检查未通过：{exc}。上一版光效已保留，可继续和 AI 讨论或重试生成。")
                failure.details={"intent":intent,"candidate":value if isinstance(value,dict) else None,"errors":errors}
                raise failure from exc
            note = f"方案未通过运行或语义断言检查：{exc}。严格保持用户意图与断言，只返回修复后的完整 program JSON。禁止内置方案或自动回退。"
            if retry_note:
                note = retry_note + "\n" + note
            repair += [{"role": "assistant", "content": raw[:6000]}, {"role": "user", "content": note}]


def generate(prompt: str, config: dict, colors: list[str] | None = None) -> dict:
    prompt = (prompt or "").strip()
    if not prompt:
        raise AIError("先描述一下你想要的光效")
    text = prompt
    if colors:
        text += f"\n\n可选配色参考（自然语言颜色优先）：{' '.join(colors)}"
    return _run(config, [{"role": "user", "content": text}])


def converse(prompt: str, config: dict, current: dict | None,
             history: list[dict] | None = None, colors: list[str] | None = None) -> str:
    """Actual model conversation; it does not compile or change the lighting."""
    text = prompt.strip()
    context = CONVERSATION_PROMPT
    if current:
        context += "\n当前实际作品快照（用户可手动调整，以此为准）：" + summarise(current)
    else:
        context += "\n用户正在从空白创作新作品。不要继承之前旧作品的内置涟漪行为。"
    if colors:
        context += "\n可选参考颜色：" + " ".join(colors)
    reply = chat_messages(config, [*clean_history(history)[-MAX_HISTORY:],
                                  {"role":"user", "content":text}], system_prompt=context)
    if not isinstance(reply, str) or not reply.strip():
        raise AIError("模型没有返回对话内容，请重试；当前光效未改变。")
    return reply.strip()[:16000]


def compose(config: dict, current: dict | None, history: list[dict], colors=None) -> dict:
    """Compile the agreed conversation only after the user's explicit UI action."""
    if not any(m.get("role") == "user" for m in history):
        raise AIError("先和 AI 描述或讨论想要的效果，再按对话生成。")
    text = "请按以上对话中用户最后明确的要求，从零编写一份完整光效。保留用户未要求修改的部分。"
    if current:
        text += "\n当前实际作品：" + summarise(current)
    if colors:
        text += "\n参考配色（用户文字优先）：" + " ".join(colors)
    return _run(config, [*clean_history(history)[-MAX_HISTORY:], {"role":"user", "content":text}])


def refine(prompt: str, config: dict, current: dict | None,
           history: list[dict] | None = None, colors: list[str] | None = None) -> dict:
    """Adjust the current effect with natural language, keeping the conversation."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise AIError("说一下想怎么改")
    msgs = list(history or [])[-MAX_HISTORY:]
    text = prompt
    if current:
        text += ("\n\n当前作品完整快照（以此为准，包含手动修改）：" + summarise(current) +
                 "\n请在这个作品基础上修改，只改用户要求的地方，返回完整方案。")
    if colors:
        text += f"\n可选配色参考（不得覆盖未要求修改的颜色）：{' '.join(colors)}"
    msgs.append({"role": "user", "content": text})
    return _run(config, msgs)


def summarise(spec: dict) -> str:
    """Compact assistant message stored in the conversation history."""
    keep = {k: spec[k] for k in ("name", "kind", "expression", "design", "effect", "color",
            "color2", "audio_style", "speed", "brightness", "explain", "change", "checks", "intent") if k in spec}
    return json.dumps(keep, ensure_ascii=False)


def clean_history(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [{"role": m["role"], "content": m["content"][:8000]} for m in value[-20:]
            if isinstance(m, dict) and m.get("role") in ("user", "assistant")
            and isinstance(m.get("content"), str)]
