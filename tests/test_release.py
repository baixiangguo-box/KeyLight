"""Compatibility boundaries and writable paths for distributable builds."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kbdrv import adapters, device, models, runtime


class ReleaseTests(unittest.TestCase):
    def test_only_two_catalog_entries_have_a_lighting_adapter(self):
        self.assertEqual({m.name for m in models.MODELS if m.supported}, {'WIN 60 HE','WIN 68 HE'})
        self.assertEqual([m.name for m in models.MODELS if m.hardware_verified], ['WIN 60 HE'])
        for model in models.MODELS:
            if model.supported:
                continue
            candidate = dict(model=model, path='fake', vid=model.vid, pid=model.pid,
                             usage_page=model.page, usage=model.usage)
            with patch.object(device,'lighting_candidates',return_value=[candidate]), patch.object(device.hidwin,'HidDevice') as handle:
                with self.assertRaises(device.UnsupportedKeyboard):
                    device.Keyboard()
                handle.assert_not_called()

    def test_68_name_variants_use_five_physical_rows_and_dedicated_columns(self):
        for name in ('AULA WIN68HE','WIN 68 HE','AULA WIN68 HE'):
            model = models.guess_model(0x2E3C,0xC365,name,0xFF1B)
            self.assertEqual(model.name,'WIN 68 HE')
            adapter = adapters.build(None,model)
            self.assertEqual((adapter.rows,adapter.row_offset),(5,1))
            self.assertFalse(adapter.verified)

    def test_packaged_data_is_separate_from_readonly_assets(self):
        with patch.dict(os.environ, {'LOCALAPPDATA':r'C:\TestLocal'}, clear=True), patch.object(sys,'frozen',True,create=True):
            path = runtime.data_directory(Path(r'C:\Program\_internal\studio'))
        self.assertEqual(path,Path(r'C:\TestLocal')/'KeyLight'/'data')
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'KEYLIGHT_DATA_DIR':folder}):
            self.assertEqual(runtime.data_directory(Path('studio')),Path(folder).resolve())
