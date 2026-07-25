import sys
import unittest
from pathlib import Path


PLUGIN_PARENT = Path(__file__).resolve().parents[2]
if str(PLUGIN_PARENT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_PARENT))

from astrbot_plugin_for_Arknights.OperatorInfo.renderer import (
    OPERATOR_INFO_TEMPLATE,
)
from astrbot_plugin_for_Arknights.analysis.GachaHistoryT2I import (
    GACHA_STATISTICS_TEMPLATE,
)


class TemplateLoadingTests(unittest.TestCase):

    def test_gacha_statistics_template_loads_from_html_file(self):
        self.assertTrue(GACHA_STATISTICS_TEMPLATE.startswith("<!doctype html>"))
        self.assertIn("{{ doctor_name }}", GACHA_STATISTICS_TEMPLATE)

    def test_operator_info_template_loads_from_html_file(self):
        self.assertTrue(OPERATOR_INFO_TEMPLATE.startswith("<!doctype html>"))
        self.assertIn("{{ name }}", OPERATOR_INFO_TEMPLATE)


if __name__ == "__main__":
    unittest.main()
