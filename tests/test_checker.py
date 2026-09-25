"""Offline startup checks, using the installed Telethon package for imports."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, call, patch

from name_hunter import checker


class StopRepeating(Exception):
    pass


class StartupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name) / "script"
        self.base.mkdir()
        self.other_cwd = Path(self.temp.name) / "ide-working-directory"
        self.other_cwd.mkdir()
        self.client = Mock(start=AsyncMock(), disconnect=AsyncMock())
        self.rows = [
            {
                "username": "sample_name",
                "status": "AVAILABLE",
                "detail": "Free registration",
            },
        ]
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(checker, "BASE_DIR", self.base))
        self.factory = self.stack.enter_context(
            patch.object(checker, "TelegramClient", return_value=self.client)
        )
        self.run_check = self.stack.enter_context(
            patch.object(checker, "run_check", new=AsyncMock(return_value=self.rows))
        )
        self.sleep = self.stack.enter_context(
            patch.object(checker.asyncio, "sleep", new=AsyncMock())
        )
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def write_candidates(self, relative_path="candidates.txt", text="@Sample_Name\n"):
        path = self.base / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    async def run_main(self, **kwargs):
        config = {"api_id": 12345, "api_hash": "test-api-hash"}
        config.update(kwargs)
        await checker.main(**config)

    def assert_results_saved(self, directory):
        result_files = list(directory.glob("*/results.csv"))
        self.assertEqual(len(result_files), 1)
        self.assertIn(
            "sample_name,AVAILABLE,Free registration", result_files[0].read_text()
        )
        self.assertEqual(
            (result_files[0].parent / "available.txt").read_text(), "sample_name"
        )

    async def test_default_paths_ignore_ide_working_directory_and_cli_arguments(self):
        self.write_candidates()
        with (
            contextlib.chdir(self.other_cwd),
            patch("sys.argv", ["tst.py", "--not-a-cli-option"]),
        ):
            await self.run_main()
        self.factory.assert_called_once_with(
            str(self.base / "username_checker"), 12345, "test-api-hash"
        )
        self.client.start.assert_awaited_once()
        self.run_check.assert_awaited_once_with(self.client, ["sample_name"], 1.0)
        self.sleep.assert_not_awaited()
        self.client.disconnect.assert_awaited_once()
        self.assert_results_saved(self.base / "results")
        self.assertEqual(list(self.other_cwd.iterdir()), [])

    async def test_custom_relative_paths_and_minimum_delay(self):
        self.write_candidates("inputs/usernames.txt")
        with contextlib.chdir(self.other_cwd):
            await self.run_main(
                candidates_file="inputs/usernames.txt",
                session_file="auth/custom_session",
                results_dir="exports",
                delay=0.1,
            )
        self.factory.assert_called_once_with(
            str(self.base / "auth/custom_session"), 12345, "test-api-hash"
        )
        self.assertTrue((self.base / "auth").is_dir())
        self.run_check.assert_awaited_once_with(self.client, ["sample_name"], 0.5)
        self.assert_results_saved(self.base / "exports")

    async def test_absolute_paths_are_preserved(self):
        candidates = self.other_cwd / "absolute.txt"
        candidates.write_text("Sample_Name\n", encoding="utf-8")
        session = self.other_cwd / "absolute_session"
        output = self.other_cwd / "absolute_results"
        await self.run_main(
            candidates_file=candidates,
            session_file=session,
            results_dir=output,
            delay=2.5,
        )
        self.factory.assert_called_once_with(str(session), 12345, "test-api-hash")
        self.run_check.assert_awaited_once_with(self.client, ["sample_name"], 2.5)
        self.assert_results_saved(output)

    async def test_repeat_interval_is_clamped_and_client_is_cleaned_up(self):
        self.write_candidates()
        for requested, expected in [(5, 300), (900, 900)]:
            with self.subTest(interval=requested):
                self.client.reset_mock()
                self.run_check.reset_mock()
                self.sleep.reset_mock()
                self.sleep.side_effect = [None, StopRepeating()]
                with self.assertRaises(StopRepeating):
                    await self.run_main(interval=requested)
                self.assertEqual(self.run_check.await_count, 2)
                self.sleep.assert_has_awaits([call(expected), call(expected)])
                self.client.start.assert_awaited_once()
                self.client.disconnect.assert_awaited_once()

    async def test_disconnect_runs_when_start_fails(self):
        self.write_candidates()
        self.client.start.side_effect = ConnectionError("offline startup failure")
        with self.assertRaisesRegex(ConnectionError, "offline startup failure"):
            await self.run_main()
        self.run_check.assert_not_awaited()
        self.client.disconnect.assert_awaited_once()

    async def test_repeat_respects_long_flood_wait(self):
        self.write_candidates()
        for wait, interval, expected in [
            (120, 5, 300),
            (121, 5, 300),
            (3600, 300, 3601),
            (3600, 7200, 7200),
        ]:
            with self.subTest(wait=wait, interval=interval):
                self.run_check.reset_mock()
                self.sleep.reset_mock()
                self.run_check.return_value = [
                    {
                        "username": "sample_name",
                        "status": "FLOOD_WAIT",
                        "detail": f"Wait {wait} seconds",
                        "wait": wait,
                    }
                ]
                self.sleep.side_effect = StopRepeating()
                with self.assertRaises(StopRepeating):
                    await self.run_main(interval=interval)
                self.run_check.assert_awaited_once()
                self.sleep.assert_awaited_once_with(expected)

    async def test_disconnect_runs_when_check_fails(self):
        self.write_candidates()
        self.run_check.side_effect = RuntimeError("check failed")
        with self.assertRaisesRegex(RuntimeError, "check failed"):
            await self.run_main()
        self.client.disconnect.assert_awaited_once()

    async def test_invalid_credentials_fail_before_connecting(self):
        self.write_candidates()
        for config in [
            {"api_id": 0},
            {"api_id": -1},
            {"api_id": None},
            {"api_id": "invalid"},
            {"api_hash": ""},
            {"api_hash": "  "},
        ]:
            with self.subTest(config=config):
                with self.assertRaises(SystemExit) as failure:
                    await self.run_main(**config)
                self.assertTrue(str(failure.exception).strip())
        self.factory.assert_not_called()

    async def test_missing_input_fails_before_connecting(self):
        with self.assertRaises(SystemExit) as failure:
            await self.run_main()
        self.assertIn("candidates.txt", str(failure.exception))
        self.factory.assert_not_called()

    async def test_empty_input_fails_before_connecting(self):
        self.write_candidates(text="# Comment\n\n   \n")
        with self.assertRaises(SystemExit) as failure:
            await self.run_main()
        self.assertTrue(str(failure.exception).strip())
        self.factory.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
