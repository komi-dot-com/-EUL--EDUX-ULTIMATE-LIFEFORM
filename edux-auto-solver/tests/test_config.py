import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import src.config as cfg


class TestDetectAntigravityModels(unittest.TestCase):
    def setUp(self):
        cfg._MODELS_CACHE["ts"] = 0.0
        cfg._MODELS_CACHE["items"] = []

    def test_parses_ansi_spinner_and_models(self):
        stdout = (
            "\x1b[?25l⠋ Fetching available models...\r\n"
            "gemini-4-neon-high              Gemini 4 Neon (High)\n"
            "\x1b[32mgemini-4-hydrogen-medium\x1b[0m        Gemini 4 Hydrogen (Medium)\n"
            "gpt-oss-120b-medium\n"
        )
        fake_proc = subprocess.CompletedProcess(args=["agy", "models"], returncode=0, stdout=stdout, stderr="")

        with patch.object(cfg, "detect_available_ai_tools", return_value={"antigravity": "/usr/bin/agy"}):
            with patch.object(cfg.subprocess, "run", return_value=fake_proc):
                models = cfg.detect_antigravity_models(force_refresh=True)

        self.assertEqual(
            models,
            [
                {"id": "gemini-4-neon-high", "label": "Gemini 4 Neon (High)"},
                {"id": "gemini-4-hydrogen-medium", "label": "Gemini 4 Hydrogen (Medium)"},
                {"id": "gpt-oss-120b-medium", "label": "gpt-oss-120b-medium"},
            ],
        )

    def test_caches_timeout_failure(self):
        with patch.object(cfg, "detect_available_ai_tools", return_value={"antigravity": "/usr/bin/agy"}):
            with patch.object(cfg.subprocess, "run", side_effect=subprocess.TimeoutExpired(cmd="agy", timeout=8)) as mock_run:
                first = cfg.detect_antigravity_models()
                second = cfg.detect_antigravity_models()

        self.assertEqual(first, [])
        self.assertEqual(second, [])
        self.assertEqual(mock_run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
