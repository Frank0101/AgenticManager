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
        """Writes `text`, or a config object, as the config; None removes it."""
        if text is None:
            if os.path.exists(self.path):
                os.remove(self.path)
            return
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(text if isinstance(text, str) else json.dumps(text))

    def jira(self, **settings):
        """A config with jira-api enabled and filled in, but for `settings`."""
        source = {"enabled": True,
                  "base-url": "https://acme.test", "api-token": "s3cret"}
        source.update(settings)
        return {"sources": {"workflow": {"jira-api": source}}}

    def read_source(self):
        return config.read_source("workflow", "jira-api", SETTINGS)

    def test_load_json(self):
        # None: no file; a str: the file's text. Anything but a JSON object,
        # read as JSON with no duplicate key, is refused.
        cases = [("an object", {"a": 1}, {"a": 1}), ("no file", None, "not found"),
                 ("a duplicate key", '{"a": 1, "a": 2}',
                  'invalid JSON .*duplicate key "a"'),
                 ("not JSON", "nope", "invalid JSON"), ("not an object", "[]", "must be a JSON object")]
        for name, text, expected in cases:
            with self.subTest(name):
                self.write(text)
                if isinstance(expected, dict):
                    self.assertEqual(config.load_json(self.path), expected)
                else:
                    with self.assertRaisesRegex(ValueError, expected):
                        config.load_json(self.path)
        with self.subTest("a folder"), self.assertRaisesRegex(ValueError, "is not a file"):
            config.load_json(self.tmp.name)

    def test_is_filled(self):
        for value, filled in [("abc", True), ("", False), ("  ", False), ("<token>", False),
                              (" \t<token>\n", False),
                              ("<a> b", True), (None, False), (False, True)]:
            with self.subTest(value=value):
                self.assertIs(config.is_filled(value), filled)

    def test_read_source(self):
        # Only the settings asked for, trimmed.
        self.write(
            self.jira(**{"base-url": " https://acme.test ", "email": "me@acme.test"}))
        self.assertEqual(self.read_source(),
                         {"base-url": "https://acme.test", "api-token": "s3cret"})

    def test_read_source_failures(self):
        # Each failure says what to fix, never showing a setting's value.
        jira = self.jira()["sources"]["workflow"]["jira-api"]
        not_enabled = "sources.workflow.jira-api is not enabled"
        fix = "Run agentic-manager-utils-check-config to see how to fix it"
        cases = [
            (None, "could not read"), (None, fix), ("nope", "could not read"),
            ({}, not_enabled), ({"sources": []},
                                not_enabled), ({"sources": {}}, not_enabled),
            ({"sources": {"workflow": []}}, not_enabled),
            ({"sources": {"workflow": {"jira-api": True}}}, not_enabled),
            ({"sources": {"workflow": {"jira-api": {**jira, "enabled": False}}}}, not_enabled),
            ({"sources": {"workflow": {"jira-api": {**jira, "enabled": "true"}}}}, not_enabled),
            (self.jira(**{"api-token": "<token>"}),
             "not filled in: api-token."),
            (self.jira(**{"api-token": " <token> "}),
             "not filled in: api-token."),
            (self.jira(**{"api-token": "  "}), "not filled in: api-token."),
            (self.jira(**{"api-token": 5}), "not filled in: api-token."),
            (self.jira(**{"api-token": None}), "not filled in: api-token."),
            (self.jira(**{"base-url": None, "api-token": ""}),
             "not filled in: base-url, api-token."),
        ]
        for written, expected in cases:
            with self.subTest(expected, config=written):
                self.write(written)
                with self.assertRaises(SystemExit) as raised:
                    self.read_source()
                self.assertIn(expected, str(raised.exception))
                self.assertNotIn("s3cret", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
