"""Exact vendor indices, physical scan-code routing, and shared live context."""
import ctypes
import unittest
from unittest.mock import patch

from kbdrv.keymap import KeyMap
from kbdrv import input_hook, effects, models
from kbdrv.program import compile_program


class KeyMapTests(unittest.TestCase):
    def test_win60_reference_indices_are_not_geometry_projections(self):
        mapping=KeyMap('WIN 60 HE')
        expected={27:22,49:23,48:32,8:36,9:44,81:45,87:46,20:66,65:68,83:69,
                  13:80,160:88,90:90,66:94,161:100,162:110,91:111,164:112,
                  32:116,165:119,93:120,163:121}
        for vk,led in expected.items():
            self.assertEqual(mapping.by_vk[vk]['led'],led,(vk,led))
        self.assertEqual(len(mapping.entries),61)
        self.assertEqual(len(mapping.by_vk),60)
        self.assertNotIn(192,mapping.by_vk)  # No separate backtick key on this board.
        self.assertNotIn(92,mapping.by_vk)   # No fabricated right-Windows key.

    def test_every_supported_key_routes_to_one_unique_wire_slot(self):
        for model,total in (('WIN 60 HE',61),('WIN 68 HE',68)):
            mapping=KeyMap(model)
            self.assertEqual(len(mapping.entries),total)
            self.assertEqual(len({k['led'] for k in mapping.entries}),total)
            hook=input_hook.KeyHook();hook.configure_map(mapping)
            with patch.object(input_hook.user32,'CallNextHookEx',return_value=0):
                for vk,entry in mapping.by_vk.items():
                    event=input_hook.KBDLLHOOKSTRUCT(vkCode=vk)
                    hook._callback(0,input_hook.WM_KEYDOWN,ctypes.addressof(event))
                    self.assertEqual([led for led,_ in hook.drain()],[entry['led']])
                    frame=effects.render('ai',0,expr=compile_program('c1 if key_on else grey(0)'),
                        key_state=hook.snapshot(),color=(40,70,90))
                    self.assertEqual({i for i,rgb in enumerate(frame) if max(rgb)},{entry['led']})
                    hook._callback(0,input_hook.WM_KEYUP,ctypes.addressof(event))

    def test_scancode_preserves_physical_position_when_vk_or_layout_changes(self):
        hook=input_hook.KeyHook();hook.debug_enabled=True
        # Windows may report Q on this physical scan position under another layout.
        event=input_hook.KBDLLHOOKSTRUCT(vkCode=81,scanCode=0x1e)
        with patch.object(input_hook.user32,'CallNextHookEx',return_value=0):
            hook._callback(0,input_hook.WM_KEYDOWN,ctypes.addressof(event))
            self.assertEqual(hook.drain()[0][0],68)
            self.assertEqual(hook.debug_status()['last']['vk'],81)
            self.assertEqual(hook.debug_status()['last']['canonical_vk'],65)
            hook._callback(0,input_hook.WM_KEYUP,ctypes.addressof(event))
        self.assertNotIn(65,hook.snapshot()['held'])

    def test_extended_keys_do_not_alias_numpad_enter_or_other_sections(self):
        mapping=KeyMap()
        self.assertIsNone(mapping.resolve(13,0x1c,True))
        self.assertIsNone(mapping.resolve(37,0x4b,True))
        self.assertEqual(mapping.resolve(16,0x2a,False)['led'],88)
        self.assertEqual(mapping.resolve(16,0x36,False)['led'],100)
        self.assertEqual(mapping.resolve(17,0x1d,True)['led'],121)
        self.assertEqual(mapping.resolve(17,0x1d,False)['led'],110)

    def test_win68_uses_dedicated_navigation_and_modifier_indices(self):
        mapping=KeyMap('SI2828KZHEARGB')
        for vk,led in {45:38,46:60,33:82,34:104,161:101,163:122,37:124,40:125,39:126,38:103}.items():
            self.assertEqual(mapping.by_vk[vk]['led'],led)
        self.assertNotIn(93,mapping.by_vk)
        fn=compile_program('c1 if key_on else grey(0)')
        frame=effects.render('ai',0,expr=fn,key_state={'held':{161},'key_cells':mapping.cells})
        self.assertGreater(max(frame[101]),0)
        self.assertEqual(frame[100],(0,0,0))

    def test_calibration_swaps_without_two_keys_lighting_the_same_led(self):
        base=KeyMap();changed=base.swap(65,69)
        self.assertEqual(changed.by_vk[65]['led'],69)
        self.assertEqual(changed.by_vk[83]['led'],68)
        self.assertEqual(base.by_vk[65]['led'],68)
        self.assertEqual(KeyMap('WIN 60 HE',{str(k):v for k,v in changed.overrides.items()}).cells,changed.cells)
        with self.assertRaises(ValueError):KeyMap('WIN 60 HE',{'65':69})
        with self.assertRaises(ValueError):base.swap(65,122) # Fn is not a system key.

    def test_unknown_models_and_shared_usb_identity_do_not_invent_a_layout(self):
        for name in ('87 keys','104 keys','Unknown','WIN 60 HE PRO'):
            self.assertEqual(KeyMap(name).cells,{})
        for product in (None,'Unknown keyboard','SI2851UKKZHEARGB','WIN 60 HE PRO','WIN 68 HE MAX','unknown WIN60HE keyboard'):
            self.assertIsNone(models.guess_model(0x2e3c,0xc365,product,0xff1b))
        for product,name in (('SI2825HEARGB','WIN 60 HE'),('SI2828KZHEARGB','WIN 68 HE')):
            self.assertEqual(models.guess_model(0x2e3c,0xc365,product,0xff1b).name,name)
