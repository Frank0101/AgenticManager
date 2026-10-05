# Unit tests for skills/agentic-manager-utils-lib/agentic_manager/config.py.
# Run with: python3 tests/run.py agentic-manager-utils-lib
#
# CONFIG_PATH is patched to a file in a temporary folder, which each test writes.
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", os.path.basename(TEST_DIR)))
from agentic_manager import config  # noqa: E402

SETTINGS = ("base-url", "api-token")


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "config.json")
        patcher = mock.patch.object(config, "CONFIG_PATH", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def write(self, text):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(text if isinstance(text, str) else json.dumps(text))

    def jira(self, **settings):
        source = {"enabled": True,
                  "base-url": "https://acme.test", "api-token": "s3cret"}
        source.update(settings)
        self.write({"sources": {"workflow": {"jira-api": source}}})

    def read_source(self):
        return config.read_source("workflow", "jira-api", SETTINGS)

    def assert_exits(self, expected):
        with self.assertRaises(SystemExit) as raised:
            self.read_source()
        message = str(raised.exception)
        self.assertIn(expected, message)
        self.assertNotIn("s3cret", message)
        return message

    # --- load_json

    def test_load_json(self):
        self.write({"a": 1})
        self.assertEqual(config.load_json(self.path), {"a": 1})

    def test_load_json_errors(self):
        cases = [(None, "not found"), ('{"a": 1, "a": 2}', 'invalid JSON .*duplicate key "a"'),
                 ("nope", "invalid JSON"), ("[]", "must be a JSON object")]
        for text, expected in cases:
            with self.subTest(text=text):
                if text is None:
                    if os.path.exists(self.path):
                        os.remove(self.path)
                else:
                    self.write(text)
                with self.assertRaisesRegex(ValueError, expected):
                    config.load_json(self.path)
        with self.assertRaisesRegex(ValueError, "is not a file"):
            config.load_json(self.tmp.name)

    # --- is_filled

    def test_is_filled(self):
        for value, filled in [("abc", True), ("", False), ("  ", False), ("<token>", False),
                              (" \t<token>\n", False),
                              ("<a> b", True), (None, False), (False, True)]:
            with self.subTest(value=value):
                self.assertIs(config.is_filled(value), filled)

    # --- read_source

    def test_read_source(self):
        self.jira(**{"base-url": " https://acme.test "})
        self.assertEqual(self.read_source(),
                         {"base-url": "https://acme.test", "api-token": "s3cret"})

    def test_read_source_returns_only_the_asked_settings(self):
        self.jira(email="me@acme.test")
        self.assertEqual(set(self.read_source()), set(SETTINGS))

    def test_read_source_unreadable_config(self):
        message = self.assert_exits("could not read")
        self.assertIn(
            "Run agentic-manager-utils-check-config to see how to fix it", message)
        self.write("nope")
        self.assert_exits("could not read")

    def test_read_source_not_enabled(self):
        jira = {"enabled": True, "base-url": "https://acme.test",
                "api-token": "s3cret"}
        for config_ in ({}, {"sources": []}, {"sources": {}}, {"sources": {"workflow": []}},
                        {"sources": {"workflow": {"jira-api": True}}},
                        {"sources": {"workflow": {"jira-api": {**jira, "enabled": False}}}},
                        {"sources": {"workflow": {"jira-api": {**jira, "enabled": "true"}}}}):
            with self.subTest(config=config_):
                self.write(config_)
                self.assert_exits("sources.workflow.jira-api is not enabled")

    def test_read_source_unfilled_settings(self):
        for settings, missing in [({"api-token": "<token>"}, "api-token"),
                                  ({"api-token": " <token> "}, "api-token"),
                                  ({"api-token": "  "}, "api-token"),
                                  ({"api-token": 5}, "api-token"),
                                  ({"api-token": None}, "api-token"),
                                  ({"base-url": None, "api-token": ""}, "base-url, api-token")]:
            with self.subTest(settings=settings):
                self.jira(**settings)
                self.assert_exits(f"not filled in: {missing}.")


if __name__ == "__main__":
    unittest.main()
