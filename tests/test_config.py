import contextlib
import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError, asdict
from pathlib import Path

from name_hunter.config import Config, load_config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.config_path = self.root / "config.toml"

    def write_config(self, text=None):
        if text is None:
            text = '[telegram]\napi_id = 12345\napi_hash = "test-secret-hash"\n'
        self.config_path.write_text(text, encoding="utf-8")
        return self.config_path

    def test_minimal_config_defaults_and_no_directories_created(self):
        self.write_config()
        config = load_config(self.config_path)
        self.assertIsInstance(config, Config)
        self.assertEqual(config.api_id, 12345)
        self.assertEqual(config.api_hash, "test-secret-hash")
        self.assertEqual(config.candidates_file, self.root / "candidates.txt")
        self.assertEqual(config.session_file, self.root / "data/username_checker")
        self.assertEqual(config.results_dir, self.root / "results")
        self.assertEqual(config.delay, 1.0)
        self.assertIsInstance(config.delay, float)
        self.assertEqual(config.interval, 0)
        self.assertEqual(list(self.root.iterdir()), [self.config_path])

    def test_relative_paths_are_anchored_to_custom_config_directory(self):
        self.write_config(
            '[telegram]\napi_id = 12345\napi_hash = "hash"\n'
            'session_file = "sessions/custom"\n[checker]\n'
            'candidates_file = "lists/names.txt"\nresults_dir = "output"\n'
            "delay = 2\ninterval = 600\n"
        )
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        with contextlib.chdir(elsewhere):
            config = load_config(self.config_path)
        self.assertEqual(config.session_file, self.root / "sessions/custom")
        self.assertEqual(config.candidates_file, self.root / "lists/names.txt")
        self.assertEqual(config.results_dir, self.root / "output")
        self.assertEqual(config.delay, 2.0)
        self.assertIsInstance(config.delay, float)
        self.assertEqual(config.interval, 600)

    def test_absolute_and_tilde_paths(self):
        absolute = self.root / "external/names.txt"
        self.write_config(
            '[telegram]\napi_id = 12345\napi_hash = " hash "\n'
            'session_file = "~/sessions/account"\n[checker]\n'
            f"candidates_file = {json.dumps(str(absolute))}\n"
            'results_dir = "~/exports"\n'
        )
        config = load_config(self.config_path)
        self.assertEqual(config.api_hash, "hash")
        self.assertEqual(config.candidates_file, absolute)
        self.assertEqual(config.session_file, Path.home() / "sessions/account")
        self.assertEqual(config.results_dir, Path.home() / "exports")

    def test_config_is_frozen_and_credentials_are_hidden_in_repr(self):
        config = load_config(self.write_config())
        with self.assertRaises(FrozenInstanceError):
            config.delay = 5
        self.assertNotIn("12345", repr(config))
        self.assertNotIn("test-secret-hash", repr(config))
        self.assertNotIn("api_id=", repr(config))
        self.assertNotIn("api_hash=", repr(config))
        self.assertEqual(asdict(config)["api_id"], 12345)

    def test_missing_config_refers_to_example(self):
        with self.assertRaisesRegex(ValueError, "config.example.toml"):
            load_config(self.config_path)

    def test_invalid_toml_does_not_expose_source_values(self):
        for text in [
            "[telegram]\napi_hash = secret-value-without-quotes\n",
            '[telegram]\napi_hash = "secret"\napi_hash = "secret-again"\n',
        ]:
            with self.subTest(text=text):
                with self.assertRaises(ValueError) as failure:
                    load_config(self.write_config(text))
                self.assertNotIn("secret", str(failure.exception))

    def test_non_utf8_config_has_readable_error(self):
        self.config_path.write_bytes(b"\xff\xfe")
        with self.assertRaisesRegex(ValueError, "TOML"):
            load_config(self.config_path)

    def test_missing_or_invalid_sections(self):
        for text, section in [
            ("", "telegram"),
            ('telegram = "secret"\n', "telegram"),
            ('[[telegram]]\napi_id = 12345\napi_hash = "hash"\n', "telegram"),
            (
                'checker = false\n[telegram]\napi_id = 12345\napi_hash = "hash"\n',
                "checker",
            ),
        ]:
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, section):
                    load_config(self.write_config(text))

    def test_credentials_are_required_and_strictly_validated(self):
        for credentials, field in [
            ('api_hash = "secret"\n', "api_id"),
            ('api_id = 0\napi_hash = "secret"\n', "api_id"),
            ('api_id = -1\napi_hash = "secret"\n', "api_id"),
            ('api_id = true\napi_hash = "secret"\n', "api_id"),
            ('api_id = 12345.0\napi_hash = "secret"\n', "api_id"),
            ('api_id = "12345"\napi_hash = "secret"\n', "api_id"),
            ("api_id = 12345\n", "api_hash"),
            ('api_id = 12345\napi_hash = ""\n', "api_hash"),
            ('api_id = 12345\napi_hash = "  "\n', "api_hash"),
            ("api_id = 12345\napi_hash = 123\n", "api_hash"),
        ]:
            with self.subTest(credentials=credentials):
                with self.assertRaisesRegex(ValueError, field) as failure:
                    load_config(self.write_config("[telegram]\n" + credentials))
                self.assertNotIn("12345", str(failure.exception))
                self.assertNotIn("secret", str(failure.exception))

    def test_delay_rejects_nonfinite_negative_and_wrong_types(self):
        for value in ["nan", "inf", "-inf", "-0.1", "true", '"1"', "[]", "{}"]:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "checker.delay"):
                    load_config(
                        self.write_config(
                            '[telegram]\napi_id = 12345\napi_hash = "hash"\n'
                            f"[checker]\ndelay = {value}\n"
                        )
                    )

    def test_interval_rejects_negative_and_noninteger_values(self):
        for value in ["-1", "1.0", "true", '"600"', "nan", "[]"]:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "checker.interval"):
                    load_config(
                        self.write_config(
                            '[telegram]\napi_id = 12345\napi_hash = "hash"\n'
                            f"[checker]\ninterval = {value}\n"
                        )
                    )

    def test_zero_delay_and_interval_are_valid(self):
        config = load_config(
            self.write_config(
                '[telegram]\napi_id = 12345\napi_hash = "hash"\n'
                "[checker]\ndelay = 0\ninterval = 0\n"
            )
        )
        self.assertEqual(config.delay, 0.0)
        self.assertEqual(config.interval, 0)

    def test_paths_require_nonempty_strings(self):
        for section, key in [
            ("telegram", "session_file"),
            ("checker", "candidates_file"),
            ("checker", "results_dir"),
        ]:
            for value in ['""', '"  "', "123", "false", "[]"]:
                with self.subTest(section=section, key=key, value=value):
                    text = '[telegram]\napi_id = 12345\napi_hash = "hash"\n'
                    if section == "checker":
                        text += "[checker]\n"
                    text += f"{key} = {value}\n"
                    with self.assertRaisesRegex(ValueError, key):
                        load_config(self.write_config(text))


if __name__ == "__main__":
    unittest.main()
