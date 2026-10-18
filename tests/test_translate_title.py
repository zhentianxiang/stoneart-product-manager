import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import stoneart_products


class TranslateTitleZhTests(unittest.TestCase):
    def translate(self, response: str) -> str:
        with patch(
            "stoneart_products.call_deepseek",
            return_value=response,
        ):
            return stoneart_products.translate_title_zh(
                {},
                "White Marble Virgin Mary Statue",
            )

    def translate_sequence(self, *responses: str) -> str:
        with patch(
            "stoneart_products.call_deepseek",
            side_effect=responses,
        ):
            return stoneart_products.translate_title_zh(
                {},
                "White Marble Virgin Mary Statue",
            )

    def test_empty_response_returns_empty_string(self):
        self.assertEqual(self.translate(""), "")

    def test_whitespace_only_response_returns_empty_string(self):
        self.assertEqual(self.translate("   \n\t\n  "), "")

    def test_first_non_empty_line_is_used(self):
        self.assertEqual(
            self.translate("\n\n白色大理石圣母像\n"),
            "白色大理石圣母像",
        )

    def test_label_and_quotes_are_removed(self):
        self.assertEqual(
            self.translate('中文标题：“白色大理石圣母像”'),
            "白色大理石圣母像",
        )

    def test_retries_after_empty_response(self):
        self.assertEqual(
            self.translate_sequence("", "白色大理石圣母像"),
            "白色大理石圣母像",
        )

    def test_retries_after_incomplete_translation(self):
        self.assertEqual(
            self.translate_sequence(
                "耶稣像",
                "白色大理石圣母像",
            ),
            "白色大理石圣母像",
        )

    def test_returns_empty_after_all_retries_fail(self):
        self.assertEqual(self.translate_sequence("", " \n ", "", "", ""), "")


if __name__ == "__main__":
    unittest.main()
