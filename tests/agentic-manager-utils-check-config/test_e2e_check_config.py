# End-to-end tests for skills/agentic-manager-utils-check-config/scripts/check_config.py:
# they run the whole script, as a skill does. Its functions have unit tests in
# test_check_config.py.
# Run with: python3 tests/run.py agentic-manager-utils-check-config
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
LIB_DIR = os.path.join(REPO_ROOT, "skills", "agentic-manager-utils-lib")
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
    # for cases the real template can't show, such as two sources in one group. The
    # shared library is linked next to the copy, as an install puts it, unless
    # `lib` is False.
    def run_with_template(self, template, *args, lib=True):
        skill = os.path.join(self.home.name, "skill")
        os.makedirs(os.path.join(skill, "scripts"), exist_ok=True)
        script = shutil.copy(SCRIPT, os.path.join(skill, "scripts"))
        link = os.path.join(self.home.name, os.path.basename(LIB_DIR))
        if lib and not os.path.lexists(link):
            os.symlink(LIB_DIR, link)
        elif not lib and os.path.lexists(link):
            os.remove(link)
        template_path = os.path.join(skill, "config-template.json")
        if template is not None:
            with open(template_path, "w", encoding="utf-8") as f:
                json.dump(template, f)
        elif os.path.exists(template_path):
            os.remove(template_path)
        return self.run_script(*args, script=script)

    def read_raw(self):
        with open(self.config_path, "rb") as f:
            return f.read()

    # Writes `content`, text or bytes, as the config.
    def write_raw(self, content):
        if isinstance(content, str):
            content = content.encode("utf-8")
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "wb") as f:
            f.write(content)

    # Writes the template as the config, after letting `change` edit a copy of its
    # "sources" object.
    def write_config(self, change=None):
        config = copy.deepcopy(self.template)
        if change:
            change(config["sources"])
        self.write_raw(json.dumps(config))

    # Enables jira-api in a "sources" object.
    def enable_jira(self, sources, token="abc"):
        sources["workflow"]["jira-api"].update({
            "enabled": True, "base-url": "https://acme.atlassian.net",
            "email": "me@acme.test", "api-token": token})

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

    def test_init_creates_config_from_template(self):
        out = self.assert_ok("--init")
        self.assertTrue(out["created"])
        with open(self.config_path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), self.template)

    def test_init_does_not_overwrite(self):
        for name, text in {"invalid": '{"x": 1}', "valid": None}.items():
            with self.subTest(name):
                if text is None:
                    self.write_config(self.enable_jira)
                else:
                    self.write_raw(text)
                before = self.read_raw()
                code, out = self.run_script("--init")
                self.assertEqual(code, 0 if text is None else 1, out)
                self.assertFalse(out["created"])
                self.assertEqual(self.read_raw(), before)

    def test_unknown_argument(self):
        out = self.assert_error('unknown argument "workflow" (usage: check_config.py [--init])',
                                "--init", "workflow")
        self.assertEqual(len(out["errors"]), 1, out["errors"])
        self.assertFalse(os.path.exists(self.config_path))

    # --- the config is never changed without --init

    def test_config_is_never_changed(self):
        cases = {
            "valid": json.dumps(self.template),
            "unknown key": '{"chat": {}}',
            "placeholder": '{"sources": {"workflow": {"jira-api": {"enabled": true, "api-token": "<token>"}}}}',
            "invalid JSON": "nope",
        }
        for name, text in cases.items():
            with self.subTest(name):
                self.write_raw(text)
                before = (self.read_raw(), os.stat(
                    self.config_path).st_mtime_ns)
                self.run_script()
                self.assertEqual(
                    (self.read_raw(), os.stat(self.config_path).st_mtime_ns), before)
                self.assertEqual(os.listdir(os.path.dirname(
                    self.config_path)), ["config.json"])

    def test_missing_config_is_not_created(self):
        self.run_script()
        self.assertFalse(os.path.exists(self.config_path))

    # --- the sources returned

    def test_template_as_is_lists_every_source_disabled(self):
        self.write_config()
        out = self.assert_ok()
        self.assertEqual({g: list(s) for g, s in out["sources"].items()},
                         {g: list(s) for g, s in self.template["sources"].items()})
        for group, sources in out["sources"].items():
            for name, source in sources.items():
                self.assertFalse(source["enabled"], f"{group}.{name}")
                self.assertIn(
                    f'"sources.{group}.{name}.enabled" to true', source["setup"])

    def test_enabled_source(self):
        self.write_config(self.enable_jira)
        out = self.assert_ok()
        self.assertEqual(out["sources"]["workflow"]["jira-api"],
                         {"tool": "jira", "channel": "api", "enabled": True})

    def test_setting_values_are_never_returned(self):
        self.write_config(lambda c: self.enable_jira(c, "s3cret"))
        out = self.assert_ok()
        for value in ("s3cret", "acme.atlassian.net", "me@acme.test"):
            self.assertNotIn(value, json.dumps(out))

    def test_setup(self):
        jira = ('{"enabled": true, "base-url": "<https://your-site.atlassian.net>", "email": "<email>", '
                '"api-token": "<token>"}')
        fill = 'then fill in "base-url", "email", "api-token"'
        filled = {"base-url": "https://acme.atlassian.net",
                  "email": "me@acme.test", "api-token": "abc"}
        cases = [
            (lambda: self.write_config(),
             f'set "sources.workflow.jira-api.enabled" to true, {fill}'),
            (lambda: self.write_config(lambda c: c["workflow"]["jira-api"].update(filled)),
             'set "sources.workflow.jira-api.enabled" to true'),
            (lambda: self.write_raw("{}"),
             f'add "sources": {{"workflow": {{"jira-api": {jira}}}}} at the top level, {fill}'),
            (lambda: self.write_raw('{"sources": {}}'),
             f'add "workflow": {{"jira-api": {jira}}} inside "sources", {fill}'),
            (lambda: self.write_raw('{"sources": {"workflow": {}}}'),
             f'add "jira-api": {jira} inside "sources.workflow", {fill}'),
        ]
        for write, expected in cases:
            with self.subTest(expected):
                write()
                self.assertEqual(self.assert_ok()[
                                 "sources"]["workflow"]["jira-api"]["setup"], expected)

    # --- settings

    def test_valid_settings(self):
        cases = {
            "disabled with a blank setting": lambda c: c["workflow"]["jira-api"].update({"api-token": ""}),
            "disabled with a setting left out": lambda c: c["workflow"]["jira-api"].pop("api-token"),
            "fs source with a path": lambda c: c["local_vault"]["logseq-fs"].update(
                enabled=True, path="~/logseq"),
        }
        for name, change in cases.items():
            with self.subTest(name):
                self.write_config(change)
                self.assert_ok()

    def test_invalid_settings(self):
        jira = "sources.workflow.jira-api"
        cases = [
            (lambda c: self.enable_jira(c, "<token>"),
             f"{jira}.api-token is not filled in"),
            (lambda c: self.enable_jira(c, "  "),
             f"{jira}.api-token is not filled in"),
            (lambda c: c["workflow"].update(
                {"jira-api": {"enabled": True}}), f"{jira}.api-token is not filled in"),
            (lambda c: c["workflow"]["jira-api"].update(
                {"api-token": 5}), f"{jira}.api-token must be a string"),
            (lambda c: c["workflow"]["jira-api"].update(
                {"api-token": None}), f"{jira}.api-token must be a string"),
            (lambda c: c["workflow"]["jira-api"].update(
                {"enabled": "true"}), f"{jira}.enabled must be true or false"),
            (lambda c: c["workflow"]["jira-api"].update(
                {"enabled": 1}), f"{jira}.enabled must be true or false"),
            (lambda c: c["workflow"]["jira-api"].update(
                {"enabled": None}), f"{jira}.enabled must be true or false"),
            (lambda c: c["local_vault"]["logseq-fs"].update(enabled=True),
             "sources.local_vault.logseq-fs.path is not filled in"),
            (lambda c: c["local_vault"]["logseq-fs"].update(path=["~/logseq"]),
             "sources.local_vault.logseq-fs.path must be a string"),
        ]
        for change, expected in cases:
            with self.subTest(expected):
                self.write_config(change)
                self.assert_error(expected)

    def test_errors_never_contain_setting_values(self):
        self.write_config(lambda c: c["workflow"]["jira-api"].update(
            {"api-token": "s3cret", "enabled": "yes"}))
        out = self.assert_error("enabled must be true or false")
        self.assertNotIn("s3cret", json.dumps(out))

    def test_output_root_is_optional(self):
        config = copy.deepcopy(self.template)
        for root in ("<path>", "", "~/reports"):
            with self.subTest(root):
                config["output"]["root"] = root
                self.write_raw(json.dumps(config))
                self.assertNotIn("reports", json.dumps(self.assert_ok()))
        config["output"]["root"] = 5
        self.write_raw(json.dumps(config))
        self.assert_error("output.root must be a string")

    # --- shape: keys, groups, sources and settings left out are allowed, extra ones are not

    def test_left_out_is_allowed(self):
        for text in ("{}", '{"sources": {}}'):
            with self.subTest(text):
                self.write_raw(text)
                out = self.assert_ok()
                self.assertFalse(any(source["enabled"] for sources in out["sources"].values()
                                     for source in sources.values()))
        for name, change in {"group": lambda c: c.pop("messaging"),
                             "source": lambda c: c["workflow"].pop("jira-api")}.items():
            with self.subTest(name):
                self.write_config(change)
                self.assert_ok()

    def test_wrong_shape(self):
        raw_cases = [
            ('{"sources": {}, "chat": {}}',
             'unknown key "chat" (supported: sources, output)'),
            ('{"sources": []}', "sources must be an object of groups"),
        ]
        for text, expected in raw_cases:
            with self.subTest(expected):
                self.write_raw(text)
                self.assert_error(expected)
        cases = [
            (lambda c: c["documentation"]["notion-mcp"].pop("enabled"),
             "sources.documentation.notion-mcp.enabled is missing: set it to true or false"),
            (lambda c: c.update({"chat": {}}), 'unknown group "sources.chat"'),
            (lambda c: c["workflow"].update({"jira-mcp": {"enabled": True}}),
             'unknown source "sources.workflow.jira-mcp"'),
            (lambda c: c["documentation"]["notion-mcp"].update({"workspace": "x"}),
             'unknown setting "sources.documentation.notion-mcp.workspace"'),
            (lambda c: c.update({"workflow": []}),
             "sources.workflow must be an object of sources"),
            (lambda c: c["workflow"].update(
                {"jira-api": True}), "sources.workflow.jira-api must be an object"),
        ]
        for change, expected in cases:
            with self.subTest(expected):
                self.write_config(change)
                self.assert_error(expected)

    def test_every_problem_is_listed(self):
        def change(c):
            c["chat"] = {}
            c["workflow"]["jira-mcp"] = {"enabled": False}
            c["workflow"]["jira-api"]["enabled"] = True
        self.write_config(change)
        out = self.assert_error('unknown group "sources.chat"')
        self.assertEqual(len(out["errors"]), 5, out["errors"])

    # --- unreadable or malformed files

    def test_config_is_a_folder(self):
        os.makedirs(self.config_path)
        out = self.assert_error("is not a file", "--init")
        self.assertFalse(out["created"])

    def test_malformed_files(self):
        for text, expected in [("", "invalid JSON"), ("nope", "invalid JSON"),
                               ('{"sources": {}, "sources": {}}',
                                'duplicate key "sources"'),
                               ("[]", "must be a JSON object"), (b"\xff\xfe", "invalid JSON")]:
            with self.subTest(text=text):
                self.write_raw(text)
                self.assert_error(expected)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can read any file")
    def test_unreadable_config(self):
        self.write_config()
        os.chmod(self.config_path, 0)
        self.assert_error("Permission denied")

    # --- the template itself

    def test_template_follows_the_rules(self):
        self.assertEqual(list(self.template), ["sources", "output"])
        self.assertTrue(self.template["sources"])
        for group, sources in self.template["sources"].items():
            self.assertRegex(group, r"^[a-z_]+$")
            self.assertTrue(sources, f"{group} has no sources")
            for name, settings in sources.items():
                where = f"sources.{group}.{name}"
                self.assertRegex(
                    name, r"^[a-z0-9]+(-[a-z0-9]+)*-(mcp|cli|api|fs)$", where)
                self.assertIs(settings.get("enabled"), False, where)
                for key, value in settings.items():
                    if key != "enabled":
                        self.assertRegex(value, r"^<.+>$", f"{where}.{key}")
        for key, value in self.template["output"].items():
            self.assertRegex(value, r"^<.+>$", f"output.{key}")

    def test_channels_match_the_skill(self):
        with open(os.path.join(SKILL_DIR, "SKILL.md"), encoding="utf-8") as f:
            documented = set(re.findall(
                r"^\| `([a-z]+)` +\| (?!Where)", f.read(), re.M))
        used = {name.rpartition("-")[2] for sources in self.template["sources"].values()
                for name in sources}
        self.assertEqual(documented, used)

    def test_groups_match_the_skill(self):
        with open(os.path.join(SKILL_DIR, "SKILL.md"), encoding="utf-8") as f:
            documented = re.findall(
                r"^\| `([a-z_]+)` +\| Where", f.read(), re.M)
        self.assertEqual(documented, list(self.template["sources"]))


# Cases the real template can't show, run against a copy of the script with its own
# template.
class CustomTemplateTest(ScriptTest):
    TEMPLATE = {"sources": {
        "workflow": {
            "jira-api": {"enabled": False, "api-token": "<token>"},
            "azure-devops-cli": {"enabled": False, "organization": "<organization>"},
        },
    }, "output": {"root": "<path>"}}

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
                {"enabled": True, "api-token": "abc"})
            c["workflow"]["azure-devops-cli"].update(
                {"enabled": True, "organization": "acme"})
        self.write_config(change)
        out = self.assert_ok()
        self.assertEqual(out["sources"]["workflow"], {
            "jira-api": {"tool": "jira", "channel": "api", "enabled": True},
            "azure-devops-cli": {"tool": "azure-devops", "channel": "cli", "enabled": True}})

    def test_missing_files(self):
        cases = [
            ("lib", self.template, False,
             "agentic-manager-utils-lib is not installed"),
            ("template", None, True, "config-template.json not found"),
        ]
        for name, template, lib, expected in cases:
            with self.subTest(name):
                code, out = self.run_with_template(template, lib=lib)
                self.assertEqual(code, 1, out)
                self.assertIn(expected, out["errors"][0])


if __name__ == "__main__":
    unittest.main()
