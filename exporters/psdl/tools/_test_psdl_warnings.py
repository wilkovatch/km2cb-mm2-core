"""Bounded synthetic checks of the PSDL warnings about the texture references, no stock data."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

CORE = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(CORE / 'exporters/psdl'), str(CORE.parents[1] / 'python')]
from common.psdl_writer import PSDLWriter


def warnings(mat_ids, cap=False, hook=False):
    writer = PSDLWriter(None, 'x.psdl', False, cap, hook)
    writer.tex_warning = 0
    writer.tex_warning_2 = 0
    writer.ct_warning = False
    for mat_id in mat_ids:
        writer.count_high_material(mat_id)
    with patch('common.psdl_writer.report.warning') as warning:
        writer.report_high_materials()
    return [call.args[0] for call in warning.call_args_list]


class HighMaterials(unittest.TestCase):
    def test_no_warning_up_to_511(self):
        for hook in (False, True):
            for cap in (False, True):
                self.assertEqual(warnings([1, 511], cap, hook), [])

    def test_stock_mentions_its_limit_and_the_flag(self):
        message = warnings([512])[0]
        self.assertIn('stock MM2', message)
        self.assertIn('767', message)
        self.assertIn('Assume using MM2Hook', message)

    def test_hook_leaves_only_the_tools(self):
        message = warnings([512], hook=True)[0]
        self.assertIn('City Toolkit', message)
        self.assertNotIn('stock', message)
        self.assertNotIn('767', message)

    def test_cap(self):
        self.assertIn('stock MM2', warnings([512], cap=True)[0])
        message = warnings([512, 600], cap=True, hook=True)[0]
        self.assertIn('affects 2 objects', message)
        self.assertNotIn('stock', message)

    def test_above_2047_is_reported_with_its_own_count(self):
        for hook in (False, True):
            messages = warnings([512, 2047, 2048, 3000], hook=hook)
            self.assertEqual(len(messages), 2)
            self.assertIn('more than 2047', messages[1])
            self.assertIn('affects 2 objects', messages[1])


if __name__ == '__main__':
    unittest.main()
