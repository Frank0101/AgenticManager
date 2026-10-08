# End-to-end tests for skills/agentic-manager-jira-sprint-report/scripts/fetch_sprint.py
# and prepare_report.py, which runs it, build_sprint_data.py and make_brief.py: they
# run the whole scripts. fetch_sprint.py's functions have unit tests in
# test_fetch_sprint.py.
# Run with: python3 tests/run.py agentic-manager-jira-sprint-report
#
# The scripts run against a fake Jira server, started on a local port, that serves the
# made-up sprint in sprint_fixture.py. HOME points at a temporary folder holding the
# test's own config, whose base-url is that server and whose output root is in that
# folder too, and TMPDIR at the same folder, so reports that fall back to the system
# temp folder stay inside it.
import base64
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from unittest import mock
from urllib.parse import parse_qs, urlparse

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
SCRIPTS = os.path.join(REPO_ROOT, "skills",
                       os.path.basename(TEST_DIR), "scripts")
sys.path.insert(0, TEST_DIR)
import sprint_fixture as fixture  # noqa: E402

EMAIL = "me@acme.test"
TOKEN = "s3cret-token"


class FakeJira(BaseHTTPRequestHandler):
    """Answers the endpoints fetch_sprint.py calls; anything else is a 404.
    `boards` holds the project's boards, `sprints` the board's sprints,
    `estimation` the board's estimation field, `fields` the site's fields and
    `removed` what a search for the removed issues returns and `parents` what
    a search by id for past epics returns, so a test can change them."""
    boards = []
    sprints = []
    fields = []
    removed = []
    parents = []
    parent_queries = []
    reporting_timezone: Optional[str] = "Europe/London"
    estimation: Optional[dict] = None
    requests = []

    def log_message(self, format, *args):
        pass

    def reply(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        FakeJira.requests.append(url.path)
        expected = "Basic " + \
            base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
        if self.headers.get("Authorization") != expected:
            return self.reply(401, {"errorMessages": ["unauthorized"]})
        payload = self.route(url.path, query)
        if payload is None:
            return self.reply(404, {"errorMessages": ["not found"]})
        if payload == "kanban":
            return self.reply(400, {"errorMessages": ["The board does not support sprints"]})
        self.reply(200, payload)

    def route(self, path, query):
        sprints = {str(s["id"]): s for s in FakeJira.sprints}
        if path == "/rest/api/3/myself":
            return {"accountId": "1", "displayName": "Alex Example", "timeZone": FakeJira.reporting_timezone}
        if path == "/rest/api/3/field":
            return FakeJira.fields
        if path == "/rest/api/3/status":
            return fixture.STATUSES
        if path == "/rest/agile/1.0/board":
            return {"values": FakeJira.boards, "isLast": True}
        if path == "/rest/agile/1.0/board/43/sprint":
            return "kanban"
        if path == f"/rest/agile/1.0/board/{fixture.BOARD_ID}/sprint":
            state = query.get("state")
            return {"values": [s for s in FakeJira.sprints if not state or s["state"] == state], "isLast": True}
        if path.startswith("/rest/agile/1.0/sprint/"):
            parts = path.split("/")
            sprint = sprints.get(parts[5])
            if sprint is None:
                return None
            if len(parts) == 6:
                return sprint
            return {"issues": fixture.CURRENT, "total": len(fixture.CURRENT)}
        if path == "/rest/greenhopper/1.0/rapidviewconfig/editmodel.json":
            return {"estimationStatisticConfig": {"currentEstimationStatistic": FakeJira.estimation}}
        if path == "/rest/greenhopper/1.0/rapid/charts/sprintreport":
            return fixture.SPRINT_REPORT
        if path == "/rest/api/3/search/jql":
            if query["jql"].startswith("id in"):
                FakeJira.parent_queries.append(
                    (query["jql"], query.get("fields")))
                return {"issues": FakeJira.parents}
            return {"issues": FakeJira.removed}
        if path.startswith("/rest/api/3/issue/"):
            key, kind = path.split("/")[5:7]
            if kind == "changelog":
                # Back to the shape Jira logs them in: the Sprint field by its
                # name and its site's id, the others by their ids.
                names = {"sprint": ("Sprint", "customfield_10020"), "status": ("status", "status"),
                         "flagged": ("Flagged", fixture.FLAGGED_FIELD), "parent": ("IssueParentAssociation", None)}
                values = [{"created": e["created"], "items": [{
                    **{k: v for k, v in e.items() if k not in ("created", "field")},
                    "field": names[e["field"]][0], "fieldId": names[e["field"]][1]}]}
                    for e in fixture.CHANGELOGS[key]]
                return {"values": values, "total": len(values), "isLast": True}
            comments = fixture.COMMENTS.get(key, [])
            return {"comments": comments, "total": len(comments)}
        return None


class FetchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeJira)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        self.root = os.path.join(self.tmp.name, "output")
        self.out_root = os.path.join(self.root, "jira-sprint-reports")
        self.reset_jira()
        self.write_config()

    def tearDown(self):
        self.tmp.cleanup()

    # Puts the fake Jira back to serving the fixture's sprint.
    def reset_jira(self):
        FakeJira.sprints = [copy.deepcopy(fixture.SPRINT),
                            copy.deepcopy(fixture.PREVIOUS_SPRINT),
                            {**fixture.SPRINT, "id": 8, "name": "Sprint 8", "state": "future",
                             "completeDate": None}]
        FakeJira.boards = [{"id": 43, "type": "kanban"},
                           {"id": fixture.BOARD_ID, "type": "scrum"}]
        FakeJira.fields = [{"id": fixture.FLAGGED_FIELD, "name": "Flagged"},
                           {"id": "customfield_99999", "name": "Story Points"}]
        FakeJira.removed = fixture.REMOVED
        FakeJira.parents = []
        FakeJira.parent_queries = []
        FakeJira.requests = []
        FakeJira.reporting_timezone = "Europe/London"
        FakeJira.estimation = {"typeId": "field",
                               "fieldId": fixture.POINTS_FIELD}

    # Writes the test's config. `output` is its output settings; by default the
    # output root is the test's own.
    def write_config(self, output=None, **settings):
        source = {"enabled": True, "base-url": self.base_url,
                  "email": EMAIL, "api-token": TOKEN}
        source.update(settings)
        config = {"sources": {"workflow": {"jira-api": source}},
                  "output": {"root": self.root} if output is None else output}
        path = os.path.join(self.home, ".config",
                            "agentic-manager", "config.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f)

    # Runs a script with the test's HOME, and its own system temp folder.
    def run_script(self, name, *args):
        env = dict(os.environ, HOME=self.home, TMPDIR=self.tmp.name)
        return subprocess.run([sys.executable, os.path.join(SCRIPTS, name), *args],
                              env=env, capture_output=True, text=True)

    def fetch(self, *args):
        return self.run_script("fetch_sprint.py", *args)

    def assert_fetches(self, *args):
        proc = self.fetch(*args)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn(TOKEN, proc.stdout + proc.stderr)
        return json.loads(proc.stdout)

    def assert_fails(self, expected, *args):
        proc = self.fetch(*args)
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertIn(expected, proc.stderr)
        self.assertNotIn(TOKEN, proc.stdout + proc.stderr)
        return proc

    def raw(self, out, name):
        with open(os.path.join(out["report_dir"], "_raw", name), encoding="utf-8") as f:
            return json.load(f)

    # --- selecting the sprint

    def test_selectors(self):
        board = str(fixture.BOARD_ID)
        cases = [
            # The latest closed sprint, on the project's scrum board: the
            # kanban board, which has no sprints, isn't asked.
            (None, ["--project", "PROJ"], 7, "closed"),
            (lambda: FakeJira.sprints[0].update(state="active", completeDate=None),
             ["--project", "PROJ", "--active"], 7, "active"),
            (None, ["--sprint-name", "Sprint 6", "--board", board], 6, "closed"),
            (None, ["--sprint-id", "7"], 7, "closed"),
        ]
        for change, args, sprint_id, state in cases:
            with self.subTest(args=args):
                self.reset_jira()
                if change:
                    change()
                out = self.assert_fetches(*args)
                self.assertEqual((out["sprint_id"], out["label"], out["sprint_state"]),
                                 (sprint_id, f"PROJ_Sprint_{sprint_id}", state))
                self.assertNotIn(
                    "/rest/agile/1.0/board/43/sprint", FakeJira.requests)

    def test_failures(self):
        # Each failure exits non-zero with a message saying what to fix, never
        # shows the token, and writes no report folder. Wrong selectors are
        # usage errors (exit 2); the rest exit 1.
        def two_active():
            for sprint in FakeJira.sprints[:2]:
                sprint.update(state="active")

        def kanban_only():
            FakeJira.boards = [{"id": 43, "type": "kanban"}]

        def config(**settings):
            return lambda: self.write_config(**settings)

        def no_config():
            os.remove(os.path.join(self.home, ".config",
                      "agentic-manager", "config.json"))
        board = str(fixture.BOARD_ID)
        cases = [
            (None, ["--sprint-id", "999"], 1, "404"),
            (None, ["--sprint-id", "8"], 1, "only active or closed sprints"),
            (two_active, ["--project", "PROJ", "--active"], 1,
             "give a sprint id or a board to pick one"),
            (kanban_only, ["--project", "PROJ"], 1,
             "no scrum board found for project PROJ"),
            (None, ["--project", "PROJ", "--active"],
             1, "no sprint active found"),
            (None, ["--sprint-name", "Sprint 9", "--board", board], 1,
             "no sprint named 'Sprint 9' found"),
            (lambda: FakeJira.sprints[0].update(originBoardId=None), ["--sprint-id", "7"], 1,
             "can't tell the sprint's board"),
            # A removed issue missing from the search would silently drop out
            # of the report.
            (lambda: setattr(FakeJira, "removed", fixture.REMOVED[1:]), ["--sprint-id", "7"], 1,
             "removed issue(s) could not be fetched: ['" + fixture.REMOVED[0]["key"] + "']"),
            # Conflicting selectors fail rather than one silently winning.
            (None, ["--sprint-id", "7", "--project", "PROJ"],
             2, "pass exactly one of"),
            (None, ["--sprint-id", "7", "--active"], 2,
             "--active applies only to --project or --board"),
            (None, ["--sprint-name", "Sprint 7"], 2,
             "needs exactly one of --project or --board"),
            (None, [], 2, "pass exactly one of"),
            # Config problems name the setting, never its value.
            (config(**{"api-token": "wrong-token"}),
             ["--project", "PROJ"], 1, "`api-token`"),
            (config(enabled=False), ["--project", "PROJ"],
             1, "sources.workflow.jira-api is not enabled"),
            (config(**{"api-token": "<token>"}),
             ["--project", "PROJ"], 1, "not filled in: api-token"),
            (config(**{"base-url": "http://127.0.0.1:9"}),
             ["--project", "PROJ"], 1, "your `base-url` setting"),
            (no_config, ["--project", "PROJ"], 1,
             "agentic-manager-utils-check-config"),
        ]
        for change, args, code, expected in cases:
            with self.subTest(expected, args=args):
                self.reset_jira()
                self.write_config()
                if change:
                    change()
                proc = self.fetch(*args)
                self.assertEqual(proc.returncode, code,
                                 proc.stdout + proc.stderr)
                self.assertIn(expected, proc.stderr)
                for token in (TOKEN, "wrong-token"):
                    self.assertNotIn(token, proc.stdout + proc.stderr)
                self.assertFalse(os.path.exists(self.out_root))

    def test_unusable_timezone_preserves_existing_reports(self):
        out = self.assert_fetches("--sprint-id", "7")
        sentinel = os.path.join(out["report_dir"], "kept.md")
        with open(sentinel, "w", encoding="utf-8") as f:
            f.write("Existing report")
        for zone in (None, "Missing/Zone"):
            with self.subTest(zone=zone):
                FakeJira.reporting_timezone = zone
                self.assert_fails("reporting timezone", "--sprint-id", "7")
                with open(sentinel, encoding="utf-8") as f:
                    self.assertEqual(f.read(), "Existing report")

    def test_warnings(self):
        def no_points_field():
            FakeJira.estimation = None
            FakeJira.fields = [
                {"id": fixture.FLAGGED_FIELD, "name": "Flagged"}]
        cases = [
            (lambda: FakeJira.sprints[1].update(originBoardId=99), ["--project", "PROJ"],
             "closed sprints span several boards"),
            (no_points_field, ["--sprint-id", "7"],
             "warning: no story points field found"),
        ]
        for change, args, expected in cases:
            with self.subTest(expected):
                self.reset_jira()
                change()
                proc = self.fetch(*args)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn(expected, proc.stderr)

    # --- what gets written

    def test_raw_files(self):
        out = self.assert_fetches("--project", "PROJ")
        self.assertTrue(os.path.basename(
            out["report_dir"]).startswith("PROJ_Sprint_7_"))
        meta = self.raw(out, "_meta.json")
        self.assertEqual(meta["base_url"], self.base_url)
        self.assertEqual(meta["report_timezone"], "Europe/London")
        # the board's, not "Story Points"
        self.assertEqual(meta["story_points_field"], fixture.POINTS_FIELD)
        self.assertEqual(meta["flagged_field"], fixture.FLAGGED_FIELD)
        self.assertEqual(meta["blocker_candidate_keys"], ["PROJ-7"])
        self.assertEqual(self.raw(out, "changelogs/PROJ-6.json"),
                         fixture.CHANGELOGS["PROJ-6"])
        self.assertEqual(os.listdir(os.path.join(
            out["report_dir"], "_raw", "comments")), ["PROJ-7.json"])
        self.assertEqual([i["key"] for i in self.raw(out, "punted_issues.json")], [
                         "PROJ-3", "PROJ-4", "PROJ-8", "PROJ-11"])
        self.assertEqual(self.raw(out, "previous_sprint.json"),
                         fixture.PREVIOUS_SPRINT)
        # Every epic is fetched with its description, the issues' current
        # epics too, as their own fields carry only the epic's summary.
        jql, fields = FakeJira.parent_queries[0]
        self.assertEqual(sorted(re.findall(r"\d+", jql)),
                         sorted({fixture.IMPORT[2], fixture.EXPORT[2]}))
        self.assertEqual(fields, "summary,description")
        # The token is in no file written.
        for folder, _, files in os.walk(out["report_dir"]):
            for name in files:
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    self.assertNotIn(TOKEN, f.read(), name)

    def test_raw_data_is_as_at_the_close(self):
        # The sprint closed at 16:00 on 13/03. Since then PROJ-2 was flagged,
        # PROJ-7 got and edited comments and PROJ-1 moved to another epic.
        after = fixture.ts(20)
        changelogs = {
            "PROJ-2": fixture.CHANGELOGS["PROJ-2"] + [
                {"created": after, "field": "flagged", "from": None, "fromString": None,
                 "to": "[10000]", "toString": "Impediment"}],
            "PROJ-1": fixture.CHANGELOGS["PROJ-1"] + [
                {"created": after, "field": "parent", "from": "1300", "fromString": "PROJ-130",
                 "to": fixture.IMPORT[2], "toString": fixture.IMPORT[0]}],
        }
        comments = {"PROJ-7": [{"id": "1", "created": fixture.ts(11), "body": "Waiting on a dependency."},
                               {"id": "2", "created": after, "body": "Unblocked."},
                               {"id": "3", "created": fixture.ts(11), "updated": after,
                                "body": "Blocked by a later incident."},
                               {"id": "4", "created": fixture.ts(11),
                                "updated": fixture.SPRINT["completeDate"],
                                "body": "Waiting on Security."}]}
        current = copy.deepcopy(fixture.CURRENT)
        current[1]["fields"][fixture.FLAGGED_FIELD] = [{"value": "Impediment"}]
        FakeJira.parents = [
            {"id": "1300", "key": "PROJ-130", "fields": {"summary": "Old epic"}}]
        with mock.patch.dict(fixture.CHANGELOGS, changelogs), mock.patch.dict(fixture.COMMENTS, comments), \
                mock.patch.object(fixture, "CURRENT", current):
            out = self.assert_fetches("--project", "PROJ")
        self.assertEqual(self.raw(out, "_meta.json")[
                         "blocker_candidate_keys"], ["PROJ-7"])
        self.assertEqual([c["id"] for c in self.raw(
            out, "comments/PROJ-7.json")], ["1", "4"])
        self.assertEqual(self.raw(out, "parents.json"), FakeJira.parents)
        self.assertEqual(self.raw(out, "statuses.json"), fixture.STATUSES)
        self.assertEqual(
            self.raw(out, "changelogs/PROJ-2.json"), changelogs["PROJ-2"])

    def test_points_field_found_by_name_when_the_board_estimates_by_count(self):
        FakeJira.estimation = {"typeId": "issueCount"}
        out = self.assert_fetches("--project", "PROJ")
        self.assertEqual(self.raw(out, "_meta.json")[
                         "story_points_field"], "customfield_99999")

    def test_blocker_comments_follow_membership_at_close(self):
        # A later removal must not lose the comments of an issue open at close;
        # an issue first added after close must not supply blocker comments.
        for added_after in (False, True):
            with self.subTest(added_after=added_after):
                self.reset_jira()
                current = copy.deepcopy(fixture.CURRENT)
                candidate = next(i for i in current if i["key"] == "PROJ-7")
                changes = copy.deepcopy(fixture.CHANGELOGS["PROJ-7"])
                report = copy.deepcopy(fixture.SPRINT_REPORT)
                if added_after:
                    changes = [fixture.added(16)]
                else:
                    current.remove(candidate)
                    FakeJira.removed = fixture.REMOVED + [candidate]
                    changes.append(fixture.removed(16))
                    report["contents"]["puntedIssues"].append(
                        {"key": "PROJ-7"})
                with mock.patch.object(fixture, "CURRENT", current), \
                        mock.patch.object(fixture, "SPRINT_REPORT", report), \
                        mock.patch.dict(fixture.CHANGELOGS, {"PROJ-7": changes}):
                    out = self.assert_fetches("--project", "PROJ")
                expected = [] if added_after else ["PROJ-7"]
                self.assertEqual(self.raw(out, "_meta.json")[
                                 "blocker_candidate_keys"], expected)
                self.assertEqual("/rest/api/3/issue/PROJ-7/comment" in FakeJira.requests,
                                 not added_after)

    # --- prepare_report.py: fetch, build and brief in one run

    def test_prepare_fetches_builds_and_writes_the_brief(self):
        # One line of JSON on stdout, the agent's only input to the next
        # step: fetch_sprint.py's, plus the brief to read and the path to
        # give output_file.py for content.json. Progress goes to stderr.
        proc = self.run_script("prepare_report.py", "--project", "PROJ")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn(TOKEN, proc.stdout + proc.stderr)
        self.assertEqual(len(proc.stdout.splitlines()), 1, proc.stdout)
        out = json.loads(proc.stdout)
        folder = os.path.basename(out["report_dir"])
        self.assertEqual(os.path.dirname(out["report_dir"]), self.out_root)
        self.assertEqual((out["sprint_id"], out["temporary"]), (7, False))
        self.assertEqual(out["brief"], os.path.join(
            out["report_dir"], "brief.json"))
        self.assertEqual(out["content_path"], f"{folder}/content.json")
        self.assertIn("[matches Jira's sprint report]", proc.stderr)
        self.assertTrue(os.path.exists(
            os.path.join(out["report_dir"], "data.json")))
        with open(out["brief"], encoding="utf-8") as f:
            brief = json.load(f)
        self.assertEqual(brief["sprint"]["name"], fixture.SPRINT["name"])
        self.assertTrue(brief["epics"] and brief["report_facts"])

    def test_prepare_stops_at_the_first_failure(self):
        # Each step needs the one before: a failure stops the run with that
        # step's message and code, prints no JSON and writes nothing after it.
        disagreeing = copy.deepcopy(fixture.SPRINT_REPORT)
        disagreeing["contents"]["completedIssues"].append({"key": "PROJ-99"})
        project = ["--project", "PROJ"]
        # name: (selectors, settings, Jira's sprint report, exit code,
        # expected on stderr, what the report folder holds)
        cases = [
            # As for fetch_sprint.py, which reports it: a usage error.
            ("no selector", [], {}, fixture.SPRINT_REPORT, 2,
             "pass exactly one of --sprint-id, --project or --board", []),
            ("the fetch", project, {"api-token": "wrong"},
             fixture.SPRINT_REPORT, 1, "401 Unauthorized", []),
            # Jira's sprint report disagrees with the issues fetched.
            ("the build", project, {}, disagreeing, 1,
             "differs from Jira's sprint report", ["_raw"]),
        ]
        for name, args, settings, sprint_report, code, expected, written in cases:
            with self.subTest(name), mock.patch.object(fixture, "SPRINT_REPORT", sprint_report):
                self.write_config(**settings)
                proc = self.run_script("prepare_report.py", *args)
                self.assertEqual(proc.returncode, code)
                self.assertEqual(proc.stdout, "")
                self.assertIn(expected, proc.stderr)
                reports = os.listdir(self.out_root) if os.path.exists(
                    self.out_root) else []
                self.assertEqual([sorted(os.listdir(os.path.join(self.out_root, r))) for r in reports],
                                 [written] if written else [])

    # --- where reports go

    def test_reports_folder(self):
        root = os.path.join(self.tmp.name, "my reports")
        cases = [
            ("the output root", {"root": root},
             os.path.join(root, "jira-sprint-reports"), False),
            ("the temp folder without an output root", {},
             os.path.join(self.tmp.name, "agentic-manager", "jira-sprint-reports"), True),
        ]
        for name, output, folder, temporary in cases:
            with self.subTest(name):
                self.write_config(output=output)
                proc = self.fetch("--sprint-id", "7")
                self.assertEqual(proc.returncode, 0, proc.stderr)
                out = json.loads(proc.stdout)
                self.assertEqual(
                    (os.path.dirname(out["report_dir"]), out["temporary"]), (folder, temporary))
                self.assertTrue(os.path.isdir(
                    os.path.join(out["report_dir"], "_raw")))

    def test_earlier_reports_of_the_sprint_are_replaced(self):
        def report(name, sprint_id):
            path = os.path.join(self.out_root, name, "_raw")
            os.makedirs(path)
            with open(os.path.join(path, "sprint.json"), "w", encoding="utf-8") as f:
                json.dump({"id": sprint_id}, f)
        report("PROJ_Sprint_7_26-01-01", 7)
        report("PROJ_Sprint_6_26-01-01", 6)
        out = self.assert_fetches("--project", "PROJ")
        self.assertEqual(sorted(os.listdir(self.out_root)),
                         sorted(["PROJ_Sprint_6_26-01-01", os.path.basename(out["report_dir"])]))


if __name__ == "__main__":
    unittest.main()
