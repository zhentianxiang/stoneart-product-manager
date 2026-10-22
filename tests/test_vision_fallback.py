import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import stoneart_products


class VisionFallbackTests(unittest.TestCase):
    def test_local_vision_success_skips_deepseek(self):
        config = {
            "LOCAL_VISION_ENABLED": "true",
            "LOCAL_VISION_MODEL": "Qwen3-VL-30B-A3B-Instruct",
        }
        with patch.object(
            stoneart_products, "call_local_vision", return_value='{"ok": true}'
        ), patch.object(
            stoneart_products,
            "call_deepseek",
            side_effect=AssertionError("DeepSeek must not be called"),
        ):
            content, info = stoneart_products.call_vision_with_fallback(
                config, [{"role": "user", "content": "inspect"}]
            )
        self.assertEqual(content, '{"ok": true}')
        self.assertEqual(info["provider"], "local-qwen-vl")
        self.assertEqual(info["attempts"][0]["status"], "succeeded")

    def test_local_failure_falls_back_to_deepseek(self):
        config = {
            "LOCAL_VISION_ENABLED": "true",
            "LOCAL_VISION_MODEL": "Qwen3-VL-30B-A3B-Instruct",
            "DEEPSEEK_MODEL": "deepseek-flash",
        }
        with patch.object(
            stoneart_products,
            "call_local_vision",
            side_effect=RuntimeError("local offline"),
        ), patch.object(
            stoneart_products, "call_deepseek", return_value='{"ok": true}'
        ):
            content, info = stoneart_products.call_vision_with_fallback(
                config, [{"role": "user", "content": "inspect"}]
            )
        self.assertEqual(content, '{"ok": true}')
        self.assertEqual(info["provider"], "deepseek")
        self.assertEqual(
            [attempt["status"] for attempt in info["attempts"]],
            ["failed", "succeeded"],
        )

    def test_disabled_local_vision_goes_straight_to_deepseek(self):
        config = {
            "LOCAL_VISION_ENABLED": "false",
            "DEEPSEEK_MODEL": "deepseek-flash",
        }
        with patch.object(
            stoneart_products,
            "call_local_vision",
            side_effect=AssertionError("local vision must be skipped"),
        ), patch.object(
            stoneart_products, "call_deepseek", return_value='{"ok": true}'
        ):
            _, info = stoneart_products.call_vision_with_fallback(
                config, [{"role": "user", "content": "inspect"}]
            )
        self.assertEqual(info["provider"], "deepseek")
        self.assertEqual(len(info["attempts"]), 1)


if __name__ == "__main__":
    unittest.main()
