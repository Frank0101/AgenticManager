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
# Setting values the tests write: the script's output must never show them.
VALUES = ("s3cret", "acme.atlassian.net",
          "me@acme.test", "~/logseq", "~/reports")


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

    # Runs a copy of the script next to a copy of `template` (none if `template` is
    # None), for an install with a file missing. The shared library is linked next
    # to the copy, as an install puts it, unless `lib` is False.
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

    # (whether the config's path is a link, whether it is a folder, the
    # file's bytes if it is one), and with_time its modification time.
    def state(self, with_time=False):
        state = (os.path.islink(self.config_path), os.path.isdir(self.config_path),
                 self.read_raw() if os.path.isfile(self.config_path) else None)
        if with_time and os.path.lexists(self.config_path):
            state += (os.lstat(self.config_path).st_mtime_ns,)
        return state

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

    # Removes whatever is at the config's path: a file, a link or a folder.
    def clear_config(self):
        if os.path.islink(self.config_path) or os.path.isfile(self.config_path):
            os.remove(self.config_path)
        elif os.path.isdir(self.config_path):
            shutil.rmtree(self.config_path)

    # Enables jira-api in a "sources" object.
    def enable_jira(self, sources, token="s3cret"):
        sources["workflow"]["jira-api"].update({
            "enabled": True, "base-url": "https://acme.atlassian.net",
            "email": "me@acme.test", "api-token": token})

    # Asserts the script succeeds, showing no setting value.
    def assert_ok(self, *args):
        code, out = self.run_script(*args)
        self.assertEqual(code, 0, out)
        self.assertTrue(out["ok"])
        self.assert_no_values(out)
        return out

    # Asserts the script fails, that one of its errors contains `expected`,
    # and that it shows no setting value.
    def assert_error(self, expected, *args):
        code, out = self.run_script(*args)
        self.assertEqual(code, 1, out)
        self.assertFalse(out["ok"])
        self.assertTrue(any(expected in e for e in out["errors"]),
                        f"{expected!r} not in {out['errors']}")
        self.assert_no_values(out)
        return out

    def assert_no_values(self, out):
        for value in VALUES:
            self.assertNotIn(value, json.dumps(out))


class CheckConfigTest(ScriptTest):
    # --- --init, and the config never changed without it

    def test_init(self):
        # --init creates the config from the template only where there is
        # nothing: never over a file, through a dangling link or into a folder.
        def dangling_link():
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            os.symlink(os.path.join(self.home.name,
                       "missing.json"), self.config_path)
        # name: (what is at the config's path, exit code, expected in an error)
        cases = [
            ("nothing", lambda: None, 0, None),
            ("a valid config", lambda: self.write_config(self.enable_jira), 0, None),
            ("an invalid config", lambda: self.write_raw(
                '{"x": 1}'), 1, 'unknown key "x"'),
            ("a dangling link", dangling_link, 1, "not found"),
            ("a folder", lambda: os.makedirs(self.config_path), 1, "is not a file"),
        ]
        for name, make, code, expected in cases:
            with self.subTest(name):
                self.clear_config()
                make()
                before = self.state()
                if expected:
                    out = self.assert_error(expected, "--init")
                else:
                    out = self.assert_ok("--init")
                created = before == (False, False, None)
                self.assertEqual(out["created"], created)
                if created:
                    with open(self.config_path, encoding="utf-8") as f:
                        self.assertEqual(json.load(f), self.template)
                else:
                    self.assertEqual(self.state(), before)

    def test_config_is_never_changed(self):
        # Without --init, the check only reads: nothing is created, changed
        # or written beside the config, whatever it finds.
        cases = [
            ("missing", None, "not found"),
            ("valid", json.dumps(self.template), None),
            ("unknown key", '{"chat": {}}', 'unknown key "chat"'),
            ("placeholder", '{"sources": {"workflow": {"jira-api": {"enabled": true, "api-token": "<token>"}}}}',
             "api-token is not filled in"),
            ("invalid JSON", "nope", "invalid JSON"),
        ]
        for name, text, expected in cases:
            with self.subTest(name):
                self.clear_config()
                if text is not None:
                    self.write_raw(text)
                before = self.state(with_time=True)
                if expected:
                    self.assert_error(expected)
                else:
                    self.assert_ok()
                self.assertEqual(self.state(with_time=True), before)
                if text is not None:
                    self.assertEqual(os.listdir(os.path.dirname(
                        self.config_path)), ["config.json"])

    def test_unknown_argument(self):
        out = self.assert_error('unknown argument "workflow" (usage: check_config.py [--init])',
                                "--init", "workflow")
        self.assertEqual(len(out["errors"]), 1, out["errors"])
        self.assertFalse(os.path.exists(self.config_path))

    # --- valid configs and the sources returned

    def test_valid_configs(self):
        # Every source of the template is returned, by group, enabled or with
        # its setup (test_setup checks its wording). Groups, sources,
        # settings and output left out are allowed.
        def change(edit):
            return lambda: self.write_config(edit)

        def output_root(root):
            config = copy.deepcopy(self.template)
            config["output"]["root"] = root
            return lambda: self.write_raw(json.dumps(config))

        def jira_api_and_mcp(c):
            self.enable_jira(c)
            c["workflow"]["jira-mcp"]["enabled"] = True
        # name: (the config, the sources enabled)
        cases = [
            ("the template as is", self.write_config, set()),
            ("empty", lambda: self.write_raw("{}"), set()),
            ("no groups", lambda: self.write_raw('{"sources": {}}'), set()),
            ("a group left out", change(lambda c: c.pop("messaging")), set()),
            ("a source left out", change(
                lambda c: c["workflow"].pop("jira-api")), set()),
            ("disabled with a blank setting", change(lambda c: c["workflow"]["jira-api"].update({"api-token": ""})),
             set()),
            ("disabled with a setting left out", change(
                lambda c: c["workflow"]["jira-api"].pop("api-token")), set()),
            ("disabled with its settings filled in", change(lambda c: c["workflow"]["jira-api"].update(
                {"base-url": "https://acme.atlassian.net", "email": "me@acme.test", "api-token": "s3cret"})), set()),
            ("an fs source with a path", change(lambda c: c["local_vault"]["logseq-fs"].update(
                enabled=True, path="~/logseq")), {"local_vault.logseq-fs"}),
            ("several enabled", change(jira_api_and_mcp),
             {"workflow.jira-api", "workflow.jira-mcp"}),
            ("the output root a placeholder", output_root("<path>"), set()),
            ("the output root blank", output_root(""), set()),
            ("the output root set", output_root("~/reports"), set()),
        ]
        for name, write, enabled in cases:
            with self.subTest(name):
                write()
                out = self.assert_ok()
                self.assertEqual({g: list(s) for g, s in out["sources"].items()},
                                 {g: list(s) for g, s in self.template["sources"].items()})
                found = set()
                for group, sources in out["sources"].items():
                    for source_name, source in sources.items():
                        tool, _, channel = source_name.rpartition("-")
                        if source["enabled"]:
                            found.add(f"{group}.{source_name}")
                            self.assertEqual(
                                source, {"tool": tool, "channel": channel, "enabled": True})
                        else:
                            self.assertTrue(source["setup"], source_name)
                self.assertEqual(found, enabled)

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

    # --- invalid configs

    def test_invalid_configs(self):
        # Each case is the config's text, or a change to the template's
        # "sources"; each error names what to fix, never a setting's value.
        jira = "sources.workflow.jira-api"
        bad_root = copy.deepcopy(self.template)
        bad_root["output"]["root"] = 5
        cases = [
            # The file
            ("", "invalid JSON"), ("nope",
                                   "invalid JSON"), (b"\xff\xfe", "invalid JSON"),
            ('{"sources": {}, "sources": {}}', 'duplicate key "sources"'),
            ("[]", "must be a JSON object"),
            # Its shape
            ('{"sources": {}, "chat": {}}',
             'unknown key "chat" (supported: sources, output)'),
            ('{"sources": []}', "sources must be an object of groups"),
            (lambda c: c.update({"chat": {}}), 'unknown group "sources.chat"'),
            (lambda c: c.update({"workflow": []}),
             "sources.workflow must be an object of sources"),
            (lambda c: c["workflow"].update({"linear-mcp": {"enabled": True}}),
             'unknown source "sources.workflow.linear-mcp"'),
            (lambda c: c["workflow"].update(
                {"jira-api": True}), f"{jira} must be an object"),
            (lambda c: c["documentation"]["notion-mcp"].update({"workspace": "x"}),
             'unknown setting "sources.documentation.notion-mcp.workspace"'),
            (lambda c: c["documentation"]["notion-mcp"].pop("enabled"),
             "sources.documentation.notion-mcp.enabled is missing: set it to true or false"),
            # Its settings
            (lambda c: self.enable_jira(c, "<token>"),
             f"{jira}.api-token is not filled in"),
            (lambda c: self.enable_jira(c, " <token> "),
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
            (lambda c: c["workflow"]["jira-api"].update({"api-token": "s3cret", "enabled": "yes"}),
             f"{jira}.enabled must be true or false"),
            (lambda c: c["local_vault"]["logseq-fs"].update(enabled=True),
             "sources.local_vault.logseq-fs.path is not filled in"),
            (lambda c: c["local_vault"]["logseq-fs"].update(path=["~/logseq"]),
             "sources.local_vault.logseq-fs.path must be a string"),
            (json.dumps(bad_root), "output.root must be a string"),
        ]
        for config, expected in cases:
            with self.subTest(expected, config=config if not callable(config) else None):
                if callable(config):
                    self.write_config(config)
                else:
                    self.write_raw(config)
                self.assert_error(expected)

    def test_every_problem_is_listed(self):
        def change(c):
            c["chat"] = {}
            c["workflow"]["linear-mcp"] = {"enabled": False}
            c["workflow"]["jira-api"]["enabled"] = True
        self.write_config(change)
        out = self.assert_error('unknown group "sources.chat"')
        self.assertEqual(len(out["errors"]), 5, out["errors"])

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

    def test_skill_tables_match_the_template(self):
        # The SKILL.md's groups table lists the template's groups in order,
        # and its channels table the channels its sources use.
        with open(os.path.join(SKILL_DIR, "SKILL.md"), encoding="utf-8") as f:
            skill = f.read()
        cases = [
            ("groups", re.findall(
                r"^\| `([a-z_]+)` +\| Where", skill, re.M), list(self.template["sources"])),
            ("channels", sorted(set(re.findall(r"^\| `([a-z]+)` +\| (?!Where)", skill, re.M))),
             sorted({name.rpartition("-")[2] for sources in self.template["sources"].values()
                     for name in sources})),
        ]
        for name, documented, expected in cases:
            with self.subTest(name):
                self.assertEqual(documented, expected)


# An install with a file missing, run against a copy of the script.
class InstallTest(ScriptTest):
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
