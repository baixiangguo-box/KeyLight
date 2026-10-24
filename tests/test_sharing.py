"""Offline sharing format tests; untrusted input stays bounded and data-only."""
import base64
import hashlib
import json
import unittest
import zlib

from kbdrv import effects, sharing, validation

GEOMETRY = dict(rows=5, cols=22, row_offset=1)


def pack(payload):
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    compressed = zlib.compress(raw)
    return 'KEYLIGHT1.'+base64.urlsafe_b64encode(compressed).decode().rstrip('=')+'.'+hashlib.sha256(compressed).hexdigest()[:16]


def payload(**updates):
    value = dict(format=1, renderer=1, name='测试', layout=GEOMETRY,
                 snapshot={'params':validation.DEFAULT_PARAMS})
    value.update(updates)
    return value


class SharingTests(unittest.TestCase):
    def test_builtin_effects_and_audio_styles_keep_all_parameters(self):
        for effect in set(validation.EFFECTS) - {'ai','paint'}:
            for style in ('staggered','radial'):
                params = validation.params(dict(effect=effect, audio_style=style, brightness=0,
                                               speed=.65, color=[0,9,255], color2=[120,20,5]))
                code = sharing.encode({'params':params}, '我的光效', GEOMETRY)
                decoded = sharing.decode(code)
                self.assertEqual(decoded['snapshot']['params'], params)
                self.assertEqual(decoded['layout'], GEOMETRY)
                self.assertEqual(code, sharing.encode(decoded['snapshot'], '我的光效', GEOMETRY))

    def test_every_painted_pixel_is_preserved(self):
        paint = [[i, i*2%256, 255-i] for i in range(132)]
        decoded = sharing.decode(sharing.encode({'params':{'effect':'paint'}, 'paint':paint}, '逐键配色', GEOMETRY))
        self.assertEqual(decoded['snapshot']['paint'], paint)
        original = effects.render('paint', 0, paint=paint)
        restored = effects.render('paint', 0, paint=decoded['snapshot']['paint'])
        self.assertEqual(original, restored)

    def test_ai_expression_roundtrips_without_secrets_or_chat(self):
        expr = 'rgb(x*255,y*120,(sin(t)+1)*127)'
        value = {'params':{'effect':'ai','brightness':.45,'speed':.65},
                 'ai_spec':{'expression':expr, 'name':'极光', 'api_key':'FAKE_SENTINEL',
                            'explain':'PRIVATE_PROMPT', 'history':['PRIVATE_HISTORY']},
                 'api_key':'FAKE_SENTINEL', 'ai_history':['PRIVATE_HISTORY']}
        code = sharing.encode(value, '极光', GEOMETRY)
        decoded = sharing.decode(code)
        text = json.dumps(decoded, ensure_ascii=False)
        for secret in ('FAKE_SENTINEL','PRIVATE_PROMPT','PRIVATE_HISTORY'):
            self.assertNotIn(secret, text)
        original, fn1 = validation.snapshot(value)
        restored, fn2 = validation.snapshot(decoded['snapshot'])
        self.assertEqual(fn1(.4,.6,22,1.5,0,0), fn2(.4,.6,22,1.5,0,0))
        self.assertEqual(restored['params'], original['params'])

    def test_whitespace_from_chat_copy_and_chinese_names(self):
        code = sharing.encode({'params':{}}, '夜色·我的光', GEOMETRY)
        wrapped = '\n  '+ '\n'.join(code[i:i+30] for i in range(0,len(code),30))+'\t'
        self.assertEqual(sharing.decode(wrapped)['name'], '夜色·我的光')

    def test_damaged_oversize_and_unknown_version_codes_are_rejected(self):
        code = sharing.encode({'params':{}}, '光', GEOMETRY)
        for invalid in (None, 123, '', code[:-1], code[:-1]+('a' if code[-1]!='a' else 'b'),
                        code.replace('KEYLIGHT1','KEYLIGHT2'), 'x'*33000):
            with self.assertRaises(ValueError, msg=str(invalid)[:30]):
                sharing.decode(invalid)

    def test_compression_bomb_and_trailing_data_are_rejected(self):
        with self.assertRaises(ValueError):
            sharing.decode(pack(b' '*1000000))
        compressed = zlib.compress(json.dumps(payload()).encode()) + b'trailing'
        code = 'KEYLIGHT1.'+base64.urlsafe_b64encode(compressed).decode().rstrip('=')+'.'+hashlib.sha256(compressed).hexdigest()[:16]
        with self.assertRaises(ValueError):
            sharing.decode(code)

    def test_unsafe_expressions_invalid_layouts_and_deep_json_are_rejected(self):
        for expression in ('__import__("os")','1/0','2**(2**30)'):
            with self.assertRaises(ValueError):
                sharing.decode(pack(payload(snapshot={'params':{'effect':'ai'},'ai_spec':{'expression':expression}})))
        for geometry in (dict(rows=5,cols=22,row_offset=True), dict(rows=9,cols=22,row_offset=0)):
            with self.assertRaises(ValueError):
                sharing.decode(pack(payload(layout=geometry)))
        for field in ('format','renderer'):
            with self.assertRaises(ValueError):
                sharing.decode(pack(payload(**{field:99})))
        with self.assertRaises(ValueError):
            sharing.decode(pack(b'['*1500+b'0'+b']'*1500))

    def test_different_supported_layout_is_kept(self):
        geometry = dict(rows=6, cols=22, row_offset=0)
        self.assertEqual(sharing.decode(sharing.encode({'params':{}}, '68', geometry))['layout'], geometry)
