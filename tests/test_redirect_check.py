import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import stoneart_products


class RedirectCheckTests(unittest.TestCase):
    def test_redirect_target_matches_same_path_and_query(self):
        self.assertTrue(
            stoneart_products.redirect_targets_match(
                "https://www.stoneartsculpture.com/products/new-slug/?ref=old",
                "https://www.stoneartsculpture.com/products/new-slug/?ref=old",
            )
        )

    def test_redirect_target_rejects_wrong_path_host_or_query(self):
        expected = "https://www.stoneartsculpture.com/products/new-slug/"
        for actual in (
            "https://www.stoneartsculpture.com/products/other-slug/",
            "https://example.com/products/new-slug/",
            "https://www.stoneartsculpture.com/products/new-slug/?ref=wrong",
        ):
            self.assertFalse(stoneart_products.redirect_targets_match(actual, expected))


if __name__ == "__main__":
    unittest.main()
