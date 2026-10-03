# Tests for skills/agentic-manager-check-config/scripts/check_config.py.
# Run with: python3 tests/run.py
#
# Each test runs the script with HOME pointed at a temporary folder. The config is
# part of the test's setup, so each test writes its own and is free to change it.
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
SKILL_DIR = os.path.join(REPO_ROOT, "skills", os.path.basename(TEST_DIR))
SCRIPT = os.path.join(SKILL_DIR, "scripts", "check_config.py")
TEMPLATE = os.path.join(SKILL_DIR, "config-template.json")


# Helpers shared by the test classes below; it has no tests of its own.
class ScriptTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(
            self.home.name, ".config", "agentic-manager", "config.json")
        with open(TEMPLATE, encoding="utf-8") as f:
            self.template = json.load(f)

    def tearDown(self):
        if os.path.isfile(self.config_path):
            os.chmod(self.config_path, 0o644)
        self.home.cleanup()

    # Runs the script and returns (exit code, parsed JSON output).
    def run_script(self, *args, script=SCRIPT):
        env = dict(os.environ, HOME=self.home.name)
        proc = subprocess.run([sys.executable, script, *args], env=env,
                              capture_output=True, text=True)
        return proc.returncode, json.loads(proc.stdout)

    # Runs a copy of the script next to a custom template (none if `template` is None),
    # for cases the real template can't show, such as two sources in one group.
    def run_with_template(self, template, *args):
        skill = os.path.join(self.home.name, "skill")
        os.makedirs(os.path.join(skill, "scripts"), exist_ok=True)
        script = shutil.copy(SCRIPT, os.path.join(skill, "scripts"))
        if template is not None:
            with open(os.path.join(skill, "config-template.json"), "w", encoding="utf-8") as f:
                json.dump(template, f)
        return self.run_script(*args, script=script)

    def read_raw(self):
        with open(self.config_path, "rb") as f:
            return f.read()

    def write_raw(self, text):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write(text)

    # Writes the template as the config, after letting `change` edit a copy of it.
    def write_config(self, change=None):
        config = copy.deepcopy(self.template)
        if change:
            change(config)
        self.write_raw(json.dumps(config))

    def enable_jira(self, config, token="abc"):
        config["workflow"]["jira-api"]["enabled"] = True
        config["workflow"]["jira-api"]["personal-access-token"] = token

    def assert_ok(self, *args):
        code, out = self.run_script(*args)
        self.assertEqual(code, 0, out)
        self.assertTrue(out["ok"])
        return out

    # Asserts the script fails and that one of its errors contains `expected`.
    def assert_error(self, expected, *args):
        code, out = self.run_script(*args)
        self.assertEqual(code, 1, out)
        self.assertFalse(out["ok"])
        self.assertTrue(any(expected in e for e in out["errors"]),
                        f"{expected!r} not in {out['errors']}")
        return out


class CheckConfigTest(ScriptTest):
    # --- missing config and --init

    def test_missing_config(self):
        self.assert_error("not found")

    def test_missing_config_with_group(self):
        self.assert_error("not found", "workflow")

    def test_init_creates_config_from_template(self):
        out = self.assert_ok("--init")
        self.assertTrue(out["created"])
        with open(self.config_path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), self.template)

    def test_init_then_requested_group_has_no_source(self):
        out = self.assert_error(
            'no enabled source for "workflow"', "--init", "workflow")
        self.assertTrue(out["created"])

    def test_init_does_not_overwrite(self):
        self.write_raw('{"x": 1}')
        out = self.assert_error('unknown group "x"', "--init")
        self.assertFalse(out["created"])
        self.assertEqual(self.read_raw(), b'{"x": 1}')

    def test_init_does_not_overwrite_valid_config(self):
        self.write_config(self.enable_jira)
        before = self.read_raw()
        out = self.assert_ok("--init", "workflow")
        self.assertFalse(out["created"])
        self.assertEqual(self.read_raw(), before)

    # --- the config is never changed without --init

    def test_config_is_never_changed(self):
        # name: (config, requested group)
        cases = {
            "valid": (json.dumps(self.template), "documentation"),
            "no enabled source": (json.dumps(self.template), "workflow"),
            "unknown group": ('{"chat": {}}', "workflow"),
            "placeholder": ('{"workflow": {"jira-api": {"enabled": true, '
                            '"personal-access-token": "<token>"}}}', "workflow"),
            "invalid JSON": ("nope", "workflow"),
        }
        for name, (text, group) in cases.items():
            with self.subTest(name):
                self.write_raw(text)
                before = (self.read_raw(), os.stat(
                    self.config_path).st_mtime_ns)
                self.run_script(group)
                self.assertEqual(
                    (self.read_raw(), os.stat(self.config_path).st_mtime_ns), before)
                self.assertEqual(os.listdir(os.path.dirname(
                    self.config_path)), ["config.json"])

    def test_missing_config_is_not_created(self):
        self.run_script("workflow")
        self.assertFalse(os.path.exists(self.config_path))

    # --- valid configs and requested groups

    def test_template_as_is_is_valid(self):
        self.write_config()
        out = self.assert_ok()
        self.assertEqual(out["sources"], {g: [] for g in self.template})

    def test_requested_group_returns_its_sources(self):
        self.write_config(self.enable_jira)
        out = self.assert_ok("workflow")
        self.assertEqual(out["sources"], {"workflow": [{
            "source": "jira-api", "tool": "jira", "channel": "api",
            "settings": {"personal-access-token": "abc"}}]})

    def test_no_groups_returns_every_group(self):
        self.write_config(self.enable_jira)
        out = self.assert_ok()
        self.assertEqual(list(out["sources"]), list(self.template))
        self.assertEqual(len(out["sources"]["workflow"]), 1)
        self.assertEqual(out["sources"]["messaging"], [])

    def test_requested_groups_keep_their_order(self):
        def change(c):
            self.enable_jira(c)
            c["documentation"]["notion-mcp"]["enabled"] = True
        self.write_config(change)
        out = self.assert_ok("workflow", "documentation")
        self.assertEqual(list(out["sources"]), ["workflow", "documentation"])

    def test_duplicate_requested_group(self):
        self.write_config(self.enable_jira)
        out = self.assert_ok("workflow", "workflow")
        self.assertEqual(list(out["sources"]), ["workflow"])

    def test_requested_group_disabled_source(self):
        self.write_config(self.enable_jira)
        self.assert_error('no enabled source for "source_control". To use "github-cli" (github via CLI): '
                          'set "source_control.github-cli.enabled" to true. Edit',
                          "workflow", "source_control")

    def test_requested_group_disabled_source_with_setting_to_fill(self):
        self.write_config()
        self.assert_error('set "workflow.jira-api.enabled" to true, then fill in "personal-access-token"',
                          "workflow")

    def test_requested_group_disabled_source_with_setting_filled(self):
        self.write_config(
            lambda c: c["workflow"]["jira-api"].update({"personal-access-token": "abc"}))
        out = self.assert_error(
            'set "workflow.jira-api.enabled" to true. Edit', "workflow")
        self.assertNotIn("abc", out["errors"][0])

    def test_requested_group_missing_from_config(self):
        self.write_raw("{}")
        self.assert_error('add "workflow": {"jira-api": {"enabled": true, "personal-access-token": "<token>"}} '
                          'at the top level, then fill in "personal-access-token"', "workflow")

    def test_requested_source_missing_from_group(self):
        self.write_raw('{"workflow": {}}')
        self.assert_error('add "jira-api": {"enabled": true, "personal-access-token": "<token>"} '
                          'inside "workflow", then fill in "personal-access-token"', "workflow")

    def test_every_requested_group_is_reported(self):
        self.write_raw("{}")
        out = self.assert_error(
            'no enabled source for "workflow"', "workflow", "source_control")
        self.assertEqual(len(out["errors"]), 2, out["errors"])

    def test_unknown_requested_group(self):
        self.write_config(self.enable_jira)
        out = self.assert_error(
            'unknown group "chat" requested', "workflow", "chat")
        self.assertEqual(len(out["errors"]), 1, out["errors"])

    def test_config_problems_are_reported_before_requested_groups(self):
        self.write_raw('{"chat": {}}')
        out = self.assert_error('unknown group "chat" (supported', "workflow")
        self.assertEqual(len(out["errors"]), 1, out["errors"])

    # --- settings

    def test_enabled_with_placeholder(self):
        self.write_config(lambda c: self.enable_jira(c, "<token>"))
        self.assert_error("personal-access-token is not filled in")

    def test_enabled_with_blank_setting(self):
        self.write_config(lambda c: self.enable_jira(c, "  "))
        self.assert_error("personal-access-token is not filled in")

    def test_disabled_with_blank_setting_is_valid(self):
        self.write_config(
            lambda c: c["workflow"]["jira-api"].update({"personal-access-token": ""}))
        self.assert_ok()

    def test_setting_with_wrong_type(self):
        self.write_config(
            lambda c: c["workflow"]["jira-api"].update({"personal-access-token": 5}))
        self.assert_error(
            "workflow.jira-api.personal-access-token must be a string")

    def test_enabled_as_string(self):
        self.write_config(lambda c: c["workflow"]
                          ["jira-api"].update({"enabled": "true"}))
        self.assert_error("workflow.jira-api.enabled must be true or false")

    def test_enabled_as_number(self):
        self.write_config(lambda c: c["workflow"]
                          ["jira-api"].update({"enabled": 1}))
        self.assert_error("workflow.jira-api.enabled must be true or false")

    def test_setting_set_to_null(self):
        self.write_config(
            lambda c: c["workflow"]["jira-api"].update({"personal-access-token": None}))
        self.assert_error(
            "workflow.jira-api.personal-access-token must be a string")

    def test_enabled_as_null(self):
        self.write_config(lambda c: c["workflow"]
                          ["jira-api"].update({"enabled": None}))
        self.assert_error("workflow.jira-api.enabled must be true or false")

    def test_errors_never_contain_setting_values(self):
        self.write_config(lambda c: c["workflow"]["jira-api"].update(
            {"personal-access-token": "s3cret", "enabled": "yes"}))
        out = self.assert_error("enabled must be true or false", "workflow")
        self.assertNotIn("s3cret", json.dumps(out))

    def test_enabled_with_missing_setting(self):
        self.write_raw('{"workflow": {"jira-api": {"enabled": true}}}')
        self.assert_error("personal-access-token is not filled in")

    # --- shape: groups, sources and settings left out are allowed, extra ones are not

    def test_empty_config_is_valid(self):
        self.write_raw("{}")
        out = self.assert_ok()
        self.assertEqual(out["sources"], {g: [] for g in self.template})

    def test_missing_group_is_allowed(self):
        self.write_config(lambda c: c.pop("messaging"))
        self.assert_ok()

    def test_missing_source_is_allowed(self):
        self.write_config(lambda c: c["workflow"].pop("jira-api"))
        self.assert_ok()

    def test_disabled_with_missing_setting_is_allowed(self):
        self.write_config(lambda c: c["workflow"]
                          ["jira-api"].pop("personal-access-token"))
        self.assert_ok()

    def test_missing_enabled(self):
        self.write_config(lambda c: c["documentation"]
                          ["notion-mcp"].pop("enabled"))
        self.assert_error(
            "documentation.notion-mcp.enabled is missing: set it to true or false")

    def test_extra_group(self):
        self.write_config(lambda c: c.update({"chat": {}}))
        self.assert_error('unknown group "chat"')

    def test_extra_source(self):
        self.write_config(lambda c: c["workflow"].update(
            {"jira-mcp": {"enabled": True}}))
        self.assert_error('unknown source "workflow.jira-mcp"')

    def test_extra_setting(self):
        self.write_config(lambda c: c["documentation"]
                          ["notion-mcp"].update({"workspace": "x"}))
        self.assert_error(
            'unknown setting "documentation.notion-mcp.workspace"')

    def test_group_not_an_object(self):
        self.write_config(lambda c: c.update({"workflow": []}))
        self.assert_error("workflow must be an object of sources")

    def test_source_not_an_object(self):
        self.write_config(lambda c: c["workflow"].update({"jira-api": True}))
        self.assert_error("workflow.jira-api must be an object")

    def test_every_problem_is_listed(self):
        def change(c):
            c["chat"] = {}
            c["workflow"]["jira-mcp"] = {"enabled": False}
            c["workflow"]["jira-api"]["enabled"] = True
        self.write_config(change)
        out = self.assert_error('unknown group "chat"')
        self.assertEqual(len(out["errors"]), 3, out["errors"])

    # --- unreadable or malformed files

    def test_config_is_a_folder(self):
        os.makedirs(self.config_path)
        out = self.assert_error("is not a file", "--init")
        self.assertFalse(out["created"])

    def test_empty_file(self):
        self.write_raw("")
        self.assert_error("invalid JSON")

    def test_duplicate_key(self):
        self.write_raw('{"documentation": {}, "documentation": {}}')
        self.assert_error('duplicate key "documentation"')

    def test_top_level_not_an_object(self):
        self.write_raw("[]")
        self.assert_error("must be a JSON object")

    def test_invalid_json(self):
        self.write_raw("nope")
        self.assert_error("invalid JSON")

    def test_invalid_encoding(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "wb") as f:
            f.write(b"\xff\xfe")
        self.assert_error("invalid JSON")

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can read any file")
    def test_unreadable_config(self):
        self.write_config()
        os.chmod(self.config_path, 0)
        self.assert_error("Permission denied")

    # --- the template itself

    def test_template_follows_the_rules(self):
        self.assertTrue(self.template)
        for group, sources in self.template.items():
            self.assertRegex(group, r"^[a-z_]+$")
            self.assertTrue(sources, f"{group} has no sources")
            for name, settings in sources.items():
                where = f"{group}.{name}"
                self.assertRegex(
                    name, r"^[a-z0-9]+(-[a-z0-9]+)*-(mcp|cli|api)$", where)
                self.assertIs(settings.get("enabled"), False, where)
                for key, value in settings.items():
                    if key != "enabled":
                        self.assertRegex(value, r"^<.+>$", f"{where}.{key}")

    def test_groups_match_the_skill(self):
        with open(os.path.join(SKILL_DIR, "SKILL.md"), encoding="utf-8") as f:
            documented = re.findall(
                r"^\| `([a-z_]+)` +\| Where", f.read(), re.M)
        self.assertEqual(documented, list(self.template))


# Cases the real template can't show, run against a copy of the script with its own
# template.
class CustomTemplateTest(ScriptTest):
    TEMPLATE = {
        "workflow": {
            "jira-api": {"enabled": False, "personal-access-token": "<token>"},
            "azure-devops-cli": {"enabled": False, "organization": "<organization>"},
        },
    }

    def setUp(self):
        super().setUp()
        self.template = copy.deepcopy(self.TEMPLATE)

    def run_script(self, *args, script=None):
        if script:
            return super().run_script(*args, script=script)
        return self.run_with_template(self.template, *args)

    def test_several_enabled_sources_are_all_returned(self):
        def change(c):
            c["workflow"]["jira-api"].update(
                {"enabled": True, "personal-access-token": "abc"})
            c["workflow"]["azure-devops-cli"].update(
                {"enabled": True, "organization": "acme"})
        self.write_config(change)
        out = self.assert_ok("workflow")
        self.assertEqual(out["sources"]["workflow"], [
            {"source": "jira-api", "tool": "jira", "channel": "api",
             "settings": {"personal-access-token": "abc"}},
            {"source": "azure-devops-cli", "tool": "azure-devops", "channel": "cli",
             "settings": {"organization": "acme"}}])

    def test_every_source_of_the_group_is_suggested(self):
        self.write_raw("{}")
        out = self.assert_error(
            '"jira-api" (jira via API): add "workflow": ', "workflow")
        self.assertIn('; or "azure-devops-cli" (azure-devops via CLI): add "workflow": '
                      '{"azure-devops-cli": {"enabled": true, "organization": "<organization>"}} '
                      'at the top level, then fill in "organization". Edit', out["errors"][0])

    def test_missing_template(self):
        code, out = self.run_with_template(None, "workflow")
        self.assertEqual(code, 1, out)
        self.assertTrue(out["errors"][0].endswith(
            "config-template.json not found"))


if __name__ == "__main__":
    unittest.main()
