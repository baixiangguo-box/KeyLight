"""AI-authored per-LED programs with bounded, ephemeral live inputs.

No preset dispatch, executable Python, I/O, or key history persistence.
"""
from __future__ import annotations

from .expr import compile_expression, normalize_expression
from .input_hook import vk_to_cell, _KEY_TABLE
from .layout import cells
from functools import lru_cache

KEY_CELLS = {vk: vk_to_cell(vk) for vk in _KEY_TABLE}


class Program:
    is_program = True

    def __init__(self, source):
        source = normalize_expression(source)
        self.source = source
        self.fn = compile_expression(source, interactive=True)
        self.needs_keys = any(word in self.fn_source_names(source) for word in
                              ("key_on", "key_age", "key_count", "down", "since", "count",
                               "last_col", "last_row", "last_age", "last_vk", "key_release_age", "released"))
        self.needs_audio = any(word in self.fn_source_names(source) for word in
                               ("pulse", "energy", "beat", "level"))
        self._probe_live_branches(source)

    def _probe_live_branches(self, source):
        """Also used for imports/apply, where AI intent checks may be absent."""
        import ast
        tree = ast.parse(source,mode="eval")
        ages = {0,.1,1,5,9.99,10,10.01,60}
        for node in ast.walk(tree):
            if isinstance(node,ast.Constant) and isinstance(node.value,(int,float)) and 0<=node.value<=600:
                ages.update((float(node.value),max(0,float(node.value)-.01),float(node.value)+.01))
        for rows,offset in ((5,1),(6,0)):
            grid = cells(rows,offset)
            self.frame(grid,0,rows,1,(255,90,60),(30,123,255))
            # Every supported physical key, not a fixed A/B-only sample.
            for vk in KEY_CELLS if self.needs_keys else ():
                for held in ({vk},set()):
                    self.frame(grid,.1,rows,1,(255,90,60),(30,123,255),
                        {"held":held,"ages":{vk:.1},"releases":{vk:.05},"counts":{vk:1},"last_vk":vk})
            for age in sorted(ages):
                for count in ((1,2,3) if self.needs_keys else (1,)):
                    self.frame(grid,age,rows,1,(255,90,60),(30,123,255),
                        {"held":set(KEY_CELLS),"ages":dict.fromkeys(KEY_CELLS,age),
                         "releases":dict.fromkeys(KEY_CELLS,age),"counts":dict.fromkeys(KEY_CELLS,count),"last_vk":90},
                        {"pulse":.7,"energy":.5,"beat":count,"levels":[.2]*22})

    @staticmethod
    def fn_source_names(source):
        import ast
        return {n.id for n in ast.walk(ast.parse(source, mode="eval")) if isinstance(n, ast.Name)}

    def context(self, keys, speed, color, color2, audio):
        keys, audio = keys or {}, audio or {}
        held, ages, counts = keys.get("held", ()), keys.get("ages", {}), keys.get("counts", {})
        releases = keys.get("releases", {})
        last = keys.get("last_vk", 0)
        key_cells = keys.get("key_cells",KEY_CELLS)
        pos = key_cells.get(last) or (-100, -100)
        return dict(c1=tuple(color), c2=tuple(color2),
                    down=lambda vk: int(vk in held), since=lambda vk: ages.get(vk, 1e6)*speed,
                    count=lambda vk: counts.get(vk, 0),
                    released=lambda vk: releases.get(vk, 1e6)*speed,
                    keycol=lambda vk: (key_cells.get(vk) or (-100,-100))[1],
                    keyrow=lambda vk: (key_cells.get(vk) or (-100,-100))[0],
                    last_row=pos[0], last_col=pos[1], last_vk=last,
                    last_age=ages.get(last, 1e6)*speed, pulse=audio.get("pulse", 0),
                    energy=audio.get("energy", 0), beat=audio.get("beat", 0))

    def frame(self, cells, t, rows, speed, color, color2, keys=None, audio=None):
        keys, audio = keys or {}, audio or {}
        shared = self.context(keys, speed, color, color2, audio)
        held, ages, counts = keys.get("held", ()), keys.get("ages", {}), keys.get("counts", {})
        by_cell = {}
        for vk, cell in keys.get("key_cells",KEY_CELLS).items():
            by_cell.setdefault(cell, []).append(vk)
        levels = audio.get("levels") or [0]*22
        frame = [(0,0,0)]*132
        for led, row, col in cells:
            vks = by_cell.get((row,col), ())
            local = dict(shared, key_on=int(any(vk in held for vk in vks)),
                         key_age=min((ages.get(vk, 1e6) for vk in vks), default=1e6)*speed,
                         key_count=sum(counts.get(vk, 0) for vk in vks), level=levels[min(col,len(levels)-1)])
            local["key_release_age"] = min((keys.get("releases",{}).get(vk,1e6) for vk in vks),default=1e6)*speed
            frame[led] = self.fn(col/21, row/max(1,rows-1), led, row, col, t, rows=rows, context=local)
        return frame

    def __call__(self, x, y, i, row, col, t, rows=5):
        return self.fn(x,y,i,row,col,t,rows=rows)


@lru_cache(maxsize=64)
def compile_program(source):
    return Program(source)


def validate_checks(checks):
    """Validate an intent contract before freezing it for implementation."""
    from .validation import number
    if not isinstance(checks,list) or len(checks)>16:
        raise ValueError("checks 必须是最多16项的断言数组")
    for case in checks:
        if not isinstance(case,dict):
            raise ValueError("每条验收必须是对象")
        if case.get("time_unit","seconds") not in ("seconds","program"):
            raise ValueError("time_unit 只能为 seconds（实际秒）或 program（受速度缩放的程序秒）")
        number(case.get("t",0),0,1e6,"验收时间")
        if "audio" in case:
            audio = case["audio"]
            if not isinstance(audio,dict) or set(audio)-{"levels","pulse","energy","beat"}:
                raise ValueError("音频验收须为 levels/pulse/energy/beat 对象")
            levels=audio.get("levels",[0]*22)
            if not isinstance(levels,list) or len(levels)!=22:
                raise ValueError("音频频段 levels 必须包含22个0～1数值")
            for level in levels:
                number(level,0,1,"频段能量")
            for key in ("pulse","energy"):
                number(audio.get(key,0),0,1,"音频能量")
            number(audio.get("beat",0),0,1e6,"节拍次数")
        if "others_off" in case and type(case["others_off"]) is not bool:
            raise ValueError("others_off 必须是布尔值")
        keys, expect = case.get("keys",[]), case.get("expect",[])
        if not isinstance(keys,list) or len(keys)>64 or not isinstance(expect,list) or len(expect)>132:
            raise ValueError("验收最多132条灯位结果、64个按键")
        if not expect and case.get("others_off") is not True:
            raise ValueError("空灯位列表仅能配合 others_off=true 表示全部熄灭")
        for key in keys:
            if not isinstance(key,dict) or type(key.get("vk")) is not int or key["vk"] not in KEY_CELLS:
                raise ValueError("验收按键需要可映射的整数VK码")
            if type(key.get("held",False)) is not bool:
                raise ValueError("held 必须是布尔值")
            number(key.get("age",0),0,1e6,"按下后时间")
            number(key.get("count",1),0,1e6,"按下次数")
            if "release_age" in key:
                number(key["release_age"],0,1e6,"松开后时间")
                if not key.get("held",False) and key["release_age"] > key.get("age",0):
                    raise ValueError("松开后的时间不能大于按下后的时间；age 必须包含按住和松开后的总时长")
        for item in expect:
            if not isinstance(item,dict) or (item.get("state") not in ("on","off") and "rgb" not in item and "palette" not in item):
                raise ValueError("灯位验收需要 on/off 状态或 RGB 颜色")
            if "rgb" in item:
                from .validation import color
                color(item["rgb"])
            if "palette" in item and item["palette"] not in ("primary","secondary"):
                raise ValueError("palette 只能为 primary 或 secondary")
            if "palette_exact" in item and ("palette" not in item or type(item["palette_exact"]) is not bool):
                raise ValueError("palette_exact 必须配合 palette 使用且为布尔值")
            if "vk" in item:
                if type(item["vk"]) is not int or item["vk"] not in KEY_CELLS:
                    raise ValueError("验收目标按键无效")
            elif type(item.get("row")) is not int or type(item.get("col")) is not int or not 0<=item["row"]<5 or not 0<=item["col"]<22:
                raise ValueError("验收目标灯位无效")


def _palette_matches(actual, wanted, exact=False):
    """Account for RGB rounding while optionally requiring the full UI color."""
    if exact or max(wanted)<=1:
        return all(abs(a-b)<=2 for a,b in zip(actual,wanted))
    channel=max(range(3),key=lambda k:wanted[k])
    strength=actual[channel]/wanted[channel]
    return (strength<=1.01 and max(actual)>1 and
            all(abs(a-b*strength)<=2 for a,b in zip(actual,wanted)))


def verify(spec, program):
    """Execute authored intent assertions and sample the entire live domain."""
    from .validation import number
    from .effects import render
    checks = spec.get("checks", [])
    validate_checks(checks)
    if not isinstance(checks, list) or len(checks) > 16:
        raise ValueError("checks 必须是最多16项的断言数组")
    if program.needs_keys and not checks:
        raise ValueError("按键程序必须给出未按、按下、松开及时间边界的 checks")
    if program.needs_keys:
        idle = any(isinstance(c,dict) and c.get("keys",[]) == [] for c in checks)
        pressed = any(isinstance(c,dict) and isinstance(c.get("keys"),list) and
                      any(isinstance(k,dict) and k.get("held") is True for k in c["keys"]) for c in checks)
        released_case = any(isinstance(c,dict) and isinstance(c.get("keys"),list) and c["keys"] and
                            all(isinstance(k,dict) and k.get("held") is False for k in c["keys"]) for c in checks)
        if not (idle and pressed and released_case):
            raise ValueError("按键断言必须覆盖未按过、按住中和松开后三种状态")
    color, color2 = spec["color"], spec["color2"]
    speed = spec.get("speed", 1)
    for case_index,case in enumerate(checks,1):
        if not isinstance(case, dict):
            raise ValueError("断言必须是对象")
        key_list, expectations = case.get("keys", []), case.get("expect", [])
        if not isinstance(key_list, list) or len(key_list)>64 or not isinstance(expectations,list) or len(expectations)>132:
            raise ValueError("断言最多132个灯位结果、64个按键")
        held, ages, counts, last, releases = set(), {}, {}, 0, {}
        # Intent can use exact program-time boundaries (e.g. 10 at speed=3)
        # rather than rounding the recurring physical time 10/3 to 3.333.
        time_scale=1/speed if case.get("time_unit")=="program" else 1
        for key in key_list:
            if not isinstance(key,dict):
                raise ValueError("断言按键必须是对象")
            vk = int(number(key.get("vk"), 0, 255, "键码"))
            ages[vk] = number(key.get("age", 0), 0, 1e6, "按下后时间")*time_scale
            counts[vk] = int(number(key.get("count", 1), 0, 1e6, "按下次数"))
            if "release_age" in key:
                releases[vk] = number(key["release_age"], 0,1e6,"松开后时间")*time_scale
            if type(key.get("held", False)) is not bool:
                raise ValueError("held 必须是布尔值")
            if key.get("held"):
                held.add(vk)
            if not last or ages[vk] <= ages[last]:
                last = vk
        t = number(case.get("t", 0), 0, 1e6, "断言时间")*time_scale
        inputs=dict(expr=program,speed=speed,brightness=spec.get("brightness",1),rows=5,row_offset=1,
                    levels=case.get("audio",{}).get("levels"),
                    audio_pulse=case.get("audio",{}).get("pulse",0),
                    audio_energy=case.get("audio",{}).get("energy",0),
                    audio_beat=case.get("audio",{}).get("beat",0),
                    key_state={"held":held,"ages":ages,"counts":counts,"last_vk":last,"releases":releases})
        frame = render("ai",t,color=color,color2=color2,**inputs)
        # Check every asserted palette branch, including released/expired states.
        # Merely finding one responsive branch cannot prove the rest are adjustable.
        probe_colors=(((237,43,91),(31,181,223)),((47,219,113),(211,79,29)))
        probes=[]
        if any("palette" in e for e in expectations):
            probes=[(c1,c2,render("ai",t,color=c1,color2=c2,**inputs)) for c1,c2 in probe_colors]
        allowed = set()
        for expect_index,expect in enumerate(expectations,1):
            if not isinstance(expect,dict):
                raise ValueError("断言灯位必须是对象")
            cell = KEY_CELLS.get(expect["vk"]) if "vk" in expect else (expect.get("row"),expect.get("col"))
            if not cell or type(cell[0]) is not int or type(cell[1]) is not int or not 0<=cell[0]<5 or not 0<=cell[1]<22:
                raise ValueError("断言键位无效")
            led = (cell[0]+1)*22+cell[1]
            timing="；".join(f"VK{vk}:按下后{ages[vk]:g}秒"+
                             (f",松开后{releases[vk]:g}秒,程序计时{releases[vk]*speed:g}" if vk in releases else "")
                             for vk in list(ages)[:4])
            where=(f"场景 {case_index}「{str(case.get('label',''))[:120]}」，检查点 {expect_index}，灯位 {cell}"
                   f"（t={t:g}实际秒，速度={speed:g}"+(f"；{timing}" if timing else "")+"）")
            allowed.add(led)
            state = expect.get("state")
            if state not in ("on", "off") and "rgb" not in expect and "palette" not in expect:
                raise ValueError("断言 state 只允许 on/off")
            lit = max(frame[led]) > 1
            if state is not None and lit != (state == "on"):
                raise ValueError(f"语义断言失败：{where}，应为 {state}，实际 RGB {frame[led]}")
            if "rgb" in expect and any(abs(a-b)>2 for a,b in zip(frame[led],expect["rgb"])):
                raise ValueError(f"配色断言失败：{where}，期望 RGB {expect['rgb']}，实际 RGB {frame[led]}")
            if "palette" in expect:
                wanted = color if expect["palette"] == "primary" else color2
                wanted = [int(v*spec.get("brightness",1)) for v in wanted]
                exact=expect.get("palette_exact",False)
                palette_name="主色" if expect["palette"]=="primary" else "副色"
                if not _palette_matches(frame[led],wanted,exact):
                    raise ValueError(f"配色断言失败：{where}，期望可调{palette_name} {wanted}，实际 RGB {frame[led]}。"
                                     "请检查状态/时间分支及取色；颜色不符不等于使用了固定色值。")
                for c1,c2,probe in probes:
                    selected=c1 if expect["palette"]=="primary" else c2
                    changed=[int(v*spec.get("brightness",1)) for v in selected]
                    if not _palette_matches(probe[led],changed,exact):
                        raise ValueError(f"换色复测失败：{where}，改变界面配色后应跟随可调{palette_name} {changed}，"
                                         f"实际 RGB {probe[led]}。此状态分支未正确响应主副色调整。")
        if case.get("others_off") is True and any(max(rgb)>1 for led,rgb in enumerate(frame) if led not in allowed):
            raise ValueError(f"语义断言失败：{str(case.get('label',''))[:120]}，出现不允许的其他灯位亮起/扩散")
    # Always evaluate idle, held, released, multiple simultaneous keys, and sound.
    for rows, offset in ((5,1),(6,0)):
        for age in (0,.1,.7,1.9,5,9.99,10,10.01,60):
            for held in (set(), {65,66}):
                program.frame(cells(rows,offset), age*speed, rows, speed, color,color2,
                              {"held":held,"ages":{65:age,66:age+.1},"counts":{65:1,66:2},"last_vk":65},
                              {"pulse":.7,"energy":.2,"beat":3,"levels":[.3]*22})


def verify_palette(spec, program):
    """New creations must actually respond to the exposed palette controls."""
    names = program.fn_source_names(spec["expression"])
    if not names & {"c1","c2"}:
        raise ValueError("作品颜色必须引用可调主色 c1 或副色 c2，不能硬编码全部颜色使调色失效")
    if spec.get("brightness",1) == 0:
        return
    grid = cells(5,1)
    contexts = [None, {"held":set(KEY_CELLS),"ages":dict.fromkeys(KEY_CELLS,.1),"last_vk":65,"counts":dict.fromkeys(KEY_CELLS,1)}]
    if program.needs_keys:
        contexts += [{"held":{vk},"ages":{vk:.1},"last_vk":vk,"counts":{vk:1}} for vk in KEY_CELLS]
    for keys in contexts:
        for t in (0,.7,3.1,10):
            a = program.frame(grid,t,5,1,(255,0,0),(0,0,255),keys,{"pulse":1,"energy":1,"levels":[.5]*22})
            b = program.frame(grid,t,5,1,(0,255,0),(255,255,0),keys,{"pulse":1,"energy":1,"levels":[.5]*22})
            if a != b:
                return
    raise ValueError("作品没有响应主副色调整，请修正公式中可调颜色的实际作用")


GUIDE = """从零编写灯效程序，kind 必须为 program；不能挑选内置效果或 layers。
JSON 字段：kind,name,expression,color,color2,speed,brightness,explain,change。
expression 是对每个灯位求值的安全数学表达式，返回 RGB 颜色。可用 if/else、比较、and/or。
c1 为用户可调主色，c2 为可调副色。主要颜色必须引用 c1/c2，避免硬编码使调色无效。
实时变量：key_on=当前灯位对应的键是否正被按住(0/1)，key_age=此键最近按下后秒数，
key_count=此键按下次数；未按过 age=1000000、count=0。长按不会重复累计。
down(vk)=指定 Windows 虚拟键是否按住；since(vk)=它最近按下后秒数；count(vk)=按下次数。
key_release_age=此灯位键最近松开后秒数；released(vk)=指定键最近松开后秒数；未松开过均1000000。
keyrow(vk)/keycol(vk)=指定键映射行列；常用 VK：A=65，B=66，Z=90，W=87，S=83，D=68，
空格=32，回车=13，Esc=27，左Shift=160，右Shift=161，左Ctrl=162，右Ctrl=163，数字1=49。
last_row/last_col/last_vk/last_age 是最近按下的键及时间；无按键时位置=-100、age=1000000。
t/key_age/since/last_age 均受速度控制；key_on/down 保持真实按下松开状态。
pulse/energy=真实音频脉冲/能量0..1，beat=真实节拍次数，level=当前列频段音量0..1；静音均0。
语义必须区分：按住才亮用 key_on；按下后淡出用 key_age；按A亮B用 down(65) 与 B 的行列比较；
切换常亮用 mod(count(65),2)。除非用户明确要求扩散，绝不能添加波纹、涟漪或邻键点亮。
对模糊请求采用最直接的字面行为，并在 explain 说明按下、松开及作用范围。
这是完整自由程序，不要求动态、波动或全键盘发亮。不支持的硬件动作应说明，不能伪装已实现。
"""
