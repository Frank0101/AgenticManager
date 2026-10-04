# End-to-end tests for skills/agentic-manager-jira-sprint-report/scripts/fetch_sprint.py:
# they run the whole script. Its functions have unit tests in test_fetch_sprint.py.
# Run with: python3 tests/run.py agentic-manager-jira-sprint-report
#
# The script runs against a fake Jira server, started on a local port, that serves the
# made-up sprint in sprint_fixture.py. HOME points at a temporary folder holding the
# test's own config, whose base-url is that server, and TMPDIR at the same folder, so
# reports that fall back to the system temp folder stay inside it.
import base64
import copy
import json
import os
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
            return {"accountId": "1", "displayName": "Alex Example"}
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
        self.out_root = os.path.join(self.tmp.name, "reports")
        self.reset_jira()
        self.write_config()

    def tearDown(self):
        self.tmp.cleanup()

    # Puts the fake Jira back to serving the fixture's sprint.
    def reset_jira(self):
        FakeJira.sprints = [copy.deepcopy(fixture.SPRINT),
                            {**fixture.SPRINT, "id": 6, "name": "Sprint 6",
                             "completeDate": "2026-02-27T16:00:00.000Z"},
                            {**fixture.SPRINT, "id": 8, "name": "Sprint 8", "state": "future",
                             "completeDate": None}]
        FakeJira.boards = [{"id": 43, "type": "kanban"},
                           {"id": fixture.BOARD_ID, "type": "scrum"}]
        FakeJira.fields = [{"id": fixture.FLAGGED_FIELD, "name": "Flagged"},
                           {"id": "customfield_99999", "name": "Story Points"}]
        FakeJira.removed = fixture.REMOVED
        FakeJira.parents = []
        FakeJira.requests = []
        FakeJira.estimation = {"typeId": "field",
                               "fieldId": fixture.POINTS_FIELD}

    def write_config(self, output=None, **settings):
        source = {"enabled": True, "base-url": self.base_url,
                  "email": EMAIL, "api-token": TOKEN}
        source.update(settings)
        config = {"sources": {"workflow": {"jira-api": source}}}
        if output:
            config["output"] = output
        path = os.path.join(self.home, ".config",
                            "agentic-manager", "config.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f)

    # Runs the script with --out-root, unless `out_root` is False. The system temp
    # folder is the test's own.
    def fetch(self, *args, out_root=True):
        env = dict(os.environ, HOME=self.home, TMPDIR=self.tmp.name)
        options = ["--out-root", self.out_root] if out_root else []
        return subprocess.run([sys.executable, os.path.join(SCRIPTS, "fetch_sprint.py"),
                               *options, *args], env=env, capture_output=True, text=True)

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

    def test_project_picks_latest_closed_sprint_on_scrum_boards(self):
        out = self.assert_fetches("--project", "PROJ")
        self.assertEqual((out["sprint_id"], out["label"],
                         out["sprint_state"]), (7, "PROJ_Sprint_7", "closed"))
        self.assertFalse(out["temporary"])  # --out-root isn't the temp folder
        self.assertNotIn("/rest/agile/1.0/board/43/sprint", FakeJira.requests)

    def test_selectors(self):
        board = str(fixture.BOARD_ID)
        cases = [
            (lambda: FakeJira.sprints[0].update(state="active", completeDate=None),
             ["--project", "PROJ", "--active"], 7),
            (None, ["--sprint-name", "Sprint 6", "--board", board], 6),
            (None, ["--sprint-id", "7"], 7),
        ]
        for change, args, sprint_id in cases:
            with self.subTest(args=args):
                self.reset_jira()
                if change:
                    change()
                out = self.assert_fetches(*args)
                self.assertEqual(
                    (out["sprint_id"], out["label"]), (sprint_id, f"PROJ_Sprint_{sprint_id}"))

    def test_failures(self):
        def two_active():
            for sprint in FakeJira.sprints[:2]:
                sprint.update(state="active")

        def kanban_only():
            FakeJira.boards = [{"id": 43, "type": "kanban"}]
        board = str(fixture.BOARD_ID)
        cases = [
            (None, ["--sprint-id", "999"], "404"),
            (None, ["--sprint-id", "8"], "only active or closed sprints"),
            (two_active, ["--project", "PROJ", "--active"],
             "give a sprint id or a board to pick one"),
            (kanban_only, ["--project", "PROJ"],
             "no scrum board found for project PROJ"),
            (None, ["--project", "PROJ", "--active"],
             "no sprint active found"),
            (None, ["--sprint-name", "Sprint 9", "--board", board],
             "no sprint named 'Sprint 9' found"),
            (lambda: FakeJira.sprints[0].update(originBoardId=None), ["--sprint-id", "7"],
             "can't tell the sprint's board"),
            (lambda: setattr(FakeJira, "removed", fixture.REMOVED[1:]), ["--sprint-id", "7"],
             "removed issue(s) could not be fetched: ['" + fixture.REMOVED[0]["key"] + "']"),
        ]
        for change, args, expected in cases:
            with self.subTest(expected):
                self.reset_jira()
                if change:
                    change()
                self.assert_fails(expected, *args)
                self.assertFalse(os.path.exists(self.out_root))

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

    def test_conflicting_selectors_fail(self):
        for args in (["--sprint-id", "7", "--project", "PROJ"], ["--sprint-id", "7", "--active"],
                     ["--sprint-name", "Sprint 7"], []):
            with self.subTest(args=args):
                self.assertEqual(self.fetch(*args).returncode, 2)

    # --- what gets written

    def test_raw_files(self):
        out = self.assert_fetches("--project", "PROJ")
        self.assertTrue(os.path.basename(
            out["report_dir"]).startswith("PROJ_Sprint_7_"))
        meta = self.raw(out, "_meta.json")
        self.assertEqual(meta["base_url"], self.base_url)
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

    def test_raw_data_is_as_at_the_close(self):
        # The sprint closed at 16:00 on 13/03. Since then PROJ-2 was flagged,
        # PROJ-7 got a comment and PROJ-1 moved to another epic.
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
                               {"id": "2", "created": after, "body": "Unblocked."}]}
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
            out, "comments/PROJ-7.json")], ["1"])
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

    def test_token_is_written_nowhere(self):
        out = self.assert_fetches("--project", "PROJ")
        for folder, _, files in os.walk(out["report_dir"]):
            for name in files:
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    self.assertNotIn(TOKEN, f.read(), name)

    def test_fetched_data_builds(self):
        out = self.assert_fetches("--project", "PROJ")
        proc = subprocess.run([sys.executable, os.path.join(SCRIPTS, "build_sprint_data.py"), "--report-dir",
                               out["report_dir"], "--today", "2026-03-16"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("[matches Jira's sprint report]", proc.stdout)

    def test_reports_folder_without_out_root(self):
        root = os.path.join(self.tmp.name, "my reports")
        cases = [
            ("the output root", {"root": root},
             os.path.join(root, "jira-sprint-reports"), False),
            ("the temp folder without an output root", None,
             os.path.join(self.tmp.name, "agentic-manager", "jira-sprint-reports"), True),
        ]
        for name, output, folder, temporary in cases:
            with self.subTest(name):
                self.write_config(output=output)
                proc = self.fetch("--sprint-id", "7", out_root=False)
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

    # --- credentials

    def test_wrong_token(self):
        self.write_config(**{"api-token": "wrong"})
        proc = self.assert_fails("401 Unauthorized", "--project", "PROJ")
        self.assertIn("`api-token`", proc.stderr)
        self.assertNotIn("wrong", proc.stderr.replace("401 Unauthorized", ""))

    def test_config_problems(self):
        cases = [
            ({"enabled": False}, "sources.workflow.jira-api is not enabled"),
            ({"api-token": "<token>"}, "not filled in: api-token"),
            ({"base-url": "http://127.0.0.1:9"}, "your `base-url` setting"),
        ]
        for settings, expected in cases:
            with self.subTest(expected):
                self.write_config(**settings)
                self.assert_fails(expected, "--project", "PROJ")
        os.remove(os.path.join(self.home, ".config",
                  "agentic-manager", "config.json"))
        self.assert_fails(
            "agentic-manager-utils-check-config", "--project", "PROJ")


if __name__ == "__main__":
    unittest.main()
