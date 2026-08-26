import unittest

from ..analysis.GachaHistoryT2I import (
    GACHA_STATISTICS_TEMPLATE,
)
from ..OperatorInfo.renderer import (
    OPERATOR_INFO_TEMPLATE,
)
from ..Renderer.AccountOperatorInfoRenderer.AccountOperatorInfo import (
    ACCOUNT_OPERATOR_INFO_TEMPLATE,
)


class TemplateLoadingTests(unittest.TestCase):

    def test_gacha_statistics_template_loads_from_html_file(self):
        self.assertTrue(GACHA_STATISTICS_TEMPLATE.startswith("<!doctype html>"))
        self.assertIn("{{ doctor_name }}", GACHA_STATISTICS_TEMPLATE)

    def test_operator_info_template_loads_from_html_file(self):
        self.assertTrue(OPERATOR_INFO_TEMPLATE.startswith("<!doctype html>"))
        self.assertIn("{{ name }}", OPERATOR_INFO_TEMPLATE)

    def test_account_operator_info_template_loads_from_html_file(self):
        self.assertTrue(ACCOUNT_OPERATOR_INFO_TEMPLATE.startswith("<!doctype html>"))
        self.assertIn("{% for group in groups %}", ACCOUNT_OPERATOR_INFO_TEMPLATE)
        self.assertIn("{{ group.rarity_icon_url }}", ACCOUNT_OPERATOR_INFO_TEMPLATE)
        self.assertIn("{{ operator.favor_text }}", ACCOUNT_OPERATOR_INFO_TEMPLATE)
        self.assertIn("top: 6px;\n        left: 6px;", ACCOUNT_OPERATOR_INFO_TEMPLATE)


if __name__ == "__main__":
    unittest.main()
