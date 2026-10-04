# Unit tests for skills/agentic-manager-utils-check-config/scripts/check_config.py.
# Run with: python3 tests/run.py agentic-manager-utils-check-config
#
# They call the script's functions directly with small templates and configs.
# test_e2e_check_config.py runs the whole script against real files.
import os
import sys
import unittest

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import check_config  # noqa: E402

TEMPLATE = {"sources": {
    "workflow": {
        "jira-api": {"enabled": False, "api-token": "<token>"},
        "azure-devops-cli": {"enabled": False},
    },
    "messaging": {"slack-mcp": {"enabled": False}},
}, "output": {"root": "<path>"}}
GROUPS = TEMPLATE["sources"]


class HelpersTest(unittest.TestCase):
    def test_type_name(self):
        self.assertEqual(check_config.type_name(True), "true or false")
        self.assertEqual(check_config.type_name("<token>"), "a string")

    def test_quoted(self):
        self.assertEqual(check_config.quoted(["a", "b"]), '"a", "b"')

    def test_check_unknown(self):
        cases = [
            ("sources", {"workflow": {}, "chat": {}}, GROUPS, "group",
             ['unknown group "sources.chat" (supported: workflow, messaging)']),
            ("", {"sources": {}, "x": 1}, TEMPLATE, "key", [
             'unknown key "x" (supported: sources, output)']),
            ("", {}, TEMPLATE, "key", []),
        ]
        for where, actual, expected_keys, kind, expected in cases:
            with self.subTest(actual=actual):
                self.assertEqual(check_config.check_unknown(
                    where, actual, expected_keys, kind), expected)


class CheckSourceTest(unittest.TestCase):
    def check(self, settings):
        return check_config.check_source("sources.workflow.jira-api", settings, GROUPS["workflow"]["jira-api"])

    def test_valid(self):
        for settings in ({"enabled": False}, {"enabled": False, "api-token": ""},
                         {"enabled": True, "api-token": "abc"}):
            with self.subTest(settings=settings):
                self.assertEqual(self.check(settings), [])

    def test_invalid(self):
        where = "sources.workflow.jira-api"
        unfilled = f'{where}.api-token is not filled in: fill it in, or disable "{where}"'
        cases = [
            (True, [f"{where} must be an object"]),
            ({}, [f"{where}.enabled is missing: set it to true or false"]),
            ({"enabled": "true"}, [f"{where}.enabled must be true or false"]),
            ({"enabled": 1}, [f"{where}.enabled must be true or false"]),
            ({"enabled": False, "api-token": 5},
             [f"{where}.api-token must be a string"]),
            ({"enabled": True}, [unfilled]),
            ({"enabled": True, "api-token": ""}, [unfilled]),
            ({"enabled": True, "api-token": " "}, [unfilled]),
            ({"enabled": True, "api-token": "<token>"}, [unfilled]),
            ({"enabled": True, "url": "x"},
             [f'unknown setting "{where}.url" (supported: enabled, api-token)', unfilled]),
        ]
        for settings, expected in cases:
            with self.subTest(settings=settings):
                self.assertEqual(self.check(settings), expected)


class CheckConfigTest(unittest.TestCase):
    def test_valid(self):
        # Missing groups and sources count as disabled.
        full = {"sources": {"workflow": {"jira-api": {"enabled": True, "api-token": "abc"},
                                         "azure-devops-cli": {"enabled": True}},
                            "messaging": {"slack-mcp": {"enabled": False}}}}
        for config in (full, {}, {"sources": {}}):
            with self.subTest(config=config):
                self.assertEqual(
                    check_config.check_config(config, TEMPLATE), [])

    def test_every_problem_is_reported(self):
        config = {"other": {}, "sources": {"chat": {}, "workflow": {"jira-mcp": {}, "jira-api": {"enabled": True}},
                                           "messaging": []},
                  "output": {"root": 1}}
        self.assertEqual(check_config.check_config(config, TEMPLATE), [
            'unknown key "other" (supported: sources, output)',
            'unknown group "sources.chat" (supported: workflow, messaging)',
            'unknown source "sources.workflow.jira-mcp" (supported: jira-api, azure-devops-cli)',
            'sources.workflow.jira-api.api-token is not filled in: fill it in, or disable '
            '"sources.workflow.jira-api"',
            "sources.messaging must be an object of sources",
            "output.root must be a string"])

    def test_sources_not_an_object(self):
        self.assertEqual(check_config.check_config({"sources": []}, TEMPLATE),
                         ["sources must be an object of groups"])


class CheckOutputTest(unittest.TestCase):
    def check(self, output):
        return check_config.check_output(output, TEMPLATE["output"])

    def test_settings_are_optional(self):
        for output in ({}, {"root": "<path>"}, {"root": ""}, {"root": "~/reports"}):
            with self.subTest(output=output):
                self.assertEqual(self.check(output), [])

    def test_invalid(self):
        cases = [
            ([], ["output must be an object of settings"]),
            ({"root": None, "folder": "x"},
             ['unknown setting "output.folder" (supported: root)', "output.root must be a string"]),
        ]
        for output, expected in cases:
            with self.subTest(output=output):
                self.assertEqual(self.check(output), expected)


class SetupStepsTest(unittest.TestCase):
    def test_setup_steps(self):
        jira = '{"enabled": true, "api-token": "<token>"}'
        cases = [
            ({}, "jira-api",
             f'add "sources": {{"workflow": {{"jira-api": {jira}}}}} at the top level, then fill in "api-token"'),
            ({"sources": {}}, "jira-api",
             f'add "workflow": {{"jira-api": {jira}}} inside "sources", then fill in "api-token"'),
            ({"sources": {"workflow": {}}}, "jira-api",
             f'add "jira-api": {jira} inside "sources.workflow", then fill in "api-token"'),
            ({"sources": {"workflow": {"jira-api": {"enabled": False}}}}, "jira-api",
             'set "sources.workflow.jira-api.enabled" to true, then fill in "api-token"'),
            ({"sources": {"workflow": {"jira-api": {"enabled": False, "api-token": "abc"}}}}, "jira-api",
             'set "sources.workflow.jira-api.enabled" to true'),
            ({"sources": {"workflow": {}}}, "azure-devops-cli",
             'add "azure-devops-cli": {"enabled": true} inside "sources.workflow"'),
        ]
        for config, name, expected in cases:
            with self.subTest(config=config, name=name):
                self.assertEqual(check_config.setup_steps(
                    "workflow", name, GROUPS["workflow"][name], config), expected)


class ListSourcesTest(unittest.TestCase):
    def test_every_source_is_listed_by_group(self):
        config = {"sources": {"workflow": {
            "jira-api": {"enabled": True, "api-token": "abc"}}}}
        self.assertEqual(check_config.list_sources(config, TEMPLATE), {
            "workflow": {
                "jira-api": {"tool": "jira", "channel": "api", "enabled": True},
                "azure-devops-cli": {"tool": "azure-devops", "channel": "cli", "enabled": False,
                                     "setup": 'add "azure-devops-cli": {"enabled": true} inside "sources.workflow"'}},
            "messaging": {
                "slack-mcp": {"tool": "slack", "channel": "mcp", "enabled": False,
                              "setup": 'add "messaging": {"slack-mcp": {"enabled": true}} inside "sources"'}}})

    def test_setting_values_are_never_returned(self):
        config = {"sources": {"workflow": {"jira-api": {"enabled": True, "api-token": "s3cret"}},
                              "messaging": {"slack-mcp": {"enabled": False}}}}
        self.assertNotIn("s3cret", str(
            check_config.list_sources(config, TEMPLATE)))
        config["sources"]["workflow"]["jira-api"]["enabled"] = False
        self.assertNotIn("s3cret", str(
            check_config.list_sources(config, TEMPLATE)))


if __name__ == "__main__":
    unittest.main()
