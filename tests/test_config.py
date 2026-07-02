import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from campus_notice_ai.config import load_dotenv
from campus_notice_ai.rag import OpenAICompatibleProvider


class ConfigTests(unittest.TestCase):
    def test_load_dotenv_sets_missing_and_empty_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "OPENAI_API_KEY=sk-test",
                        "OPENAI_MODEL='gpt-4.1-mini'",
                        "KEEP_EXISTING=file-value",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"OPENAI_API_KEY": "", "KEEP_EXISTING": "env-value"}, clear=True):
                loaded = load_dotenv(env_path)

                self.assertEqual(loaded["OPENAI_API_KEY"], "sk-test")
                self.assertEqual(os.environ["OPENAI_API_KEY"], "sk-test")
                self.assertEqual(os.environ["OPENAI_MODEL"], "gpt-4.1-mini")
                self.assertEqual(os.environ["KEEP_EXISTING"], "env-value")

    def test_load_dotenv_can_override_existing_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("OPENAI_MODEL=gpt-4.1-mini", encoding="utf-8")

            with patch.dict(os.environ, {"OPENAI_MODEL": "other-model"}, clear=True):
                load_dotenv(env_path, override=True)

                self.assertEqual(os.environ["OPENAI_MODEL"], "gpt-4.1-mini")

    def test_openai_provider_defaults_to_gpt_4_1_mini(self):
        with (
            patch("campus_notice_ai.rag.load_dotenv", return_value={}),
            patch.dict(os.environ, {"OPENAI_MODEL": "", "OPENAI_BASE_URL": ""}, clear=True),
        ):
            provider = OpenAICompatibleProvider(api_key="sk-test")

        self.assertEqual(provider.model, "gpt-4.1-mini")
        self.assertTrue(provider.is_available())


if __name__ == "__main__":
    unittest.main()
