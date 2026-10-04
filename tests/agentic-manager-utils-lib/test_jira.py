# Unit tests for skills/agentic-manager-utils-lib/agentic_manager/jira.py.
# Run with: python3 tests/run.py agentic-manager-utils-lib
#
# The client talks to a local fake Jira, whose answers each test sets in
# FakeJira.routes. read_source is patched, so no config is read.
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock
from urllib.parse import parse_qs, urlparse

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", os.path.basename(TEST_DIR)))
from agentic_manager import jira  # noqa: E402

TOKEN = "s3cret-token"


class FakeJira(BaseHTTPRequestHandler):
    """Answers each path from `routes`: a payload, or a function of the query
    that returns one. A payload of (code, body) sends that status. Any other
    path is a 404. Every request is recorded in `requests` as (path, query)."""
    routes = {}
    requests = []

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        FakeJira.requests.append((url.path, query))
        answer = FakeJira.routes.get(
            url.path, (404, {"errorMessages": ["not found"]}))
        if callable(answer):
            answer = answer(query)
        code, body = answer if isinstance(answer, tuple) else (200, answer)
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def pages(*pages_by_start):
    """A route that answers each request by its startAt: pages_by_start maps
    startAt to the page."""
    by_start = dict(pages_by_start)
    return lambda query: by_start[int(query.get("startAt", 0))]


class HelpersTest(unittest.TestCase):
    def test_parse_ts(self):
        for ts, iso in [("2026-03-29T10:00:00.000+0100", "2026-03-29T10:00:00+01:00"),
                        ("2026-03-29T10:00:00+0200", "2026-03-29T10:00:00+02:00"),
                        ("2026-03-29T09:00:00.000Z", "2026-03-29T09:00:00+00:00")]:
            with self.subTest(ts=ts):
                self.assertEqual(jira.parse_ts(ts).isoformat(), iso)

    def test_parse_ts_unknown_format(self):
        with self.assertRaisesRegex(ValueError, "unrecognised timestamp format"):
            jira.parse_ts("29/03/2026")

    def test_key_order(self):
        keys = ["PROJ-10", "ABC-3", "PROJ-2", "PROJ-x"]
        self.assertEqual(sorted(keys, key=jira.key_order),
                         ["ABC-3", "PROJ-2", "PROJ-10", "PROJ-x"])

    def test_nested(self):
        node = {"status": {"statusCategory": {"key": "done"}}, "parent": None}
        cases = [(node, ["status", "statusCategory", "key"], None, "done"), (node, ["parent", "key"], "x", "x"),
                 (node, ["missing"], "", ""), (None, ["parent", "id"], None, None)]
        for node, path, default, expected in cases:
            with self.subTest(path=path):
                self.assertEqual(jira.nested(node, path, default), expected)

    def test_date_only(self):
        self.assertEqual(jira.date_only(
            "2026-03-29T23:30:00.000+0100"), "2026-03-29")
        self.assertIsNone(jira.date_only(None))

    def test_issue_key(self):
        self.assertEqual(jira.ISSUE_KEY.findall("PROJ-1, A2B-30 and proj-4 or X-1a"),
                         ["PROJ-1", "A2B-30"])


class ClientTest(unittest.TestCase):
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
        FakeJira.routes = {}
        FakeJira.requests = []
        self.client = self.make_client(self.base_url + "/")

    def make_client(self, base_url):
        settings = {"base-url": base_url,
                    "email": "me@acme.test", "api-token": TOKEN}
        with mock.patch.object(jira, "read_source", return_value=settings) as read:
            client = jira.JiraClient()
        read.assert_called_once_with("workflow", "jira-api", jira.SETTINGS)
        return client

    def paths(self):
        return [path for path, _ in FakeJira.requests]

    def assert_exits(self, expected, call):
        with self.assertRaises(SystemExit) as raised:
            call()
        self.assertIn(expected, str(raised.exception))
        self.assertNotIn(TOKEN, str(raised.exception))
        return raised.exception

    # --- requests and errors

    def test_base_url_trailing_slash_is_dropped(self):
        self.assertEqual(self.client.base_url, self.base_url)

    def test_whoami(self):
        FakeJira.routes["/rest/api/3/myself"] = {"displayName": "Alex Example"}
        self.assertEqual(self.client.whoami(), "Alex Example")

    def test_sends_basic_auth(self):
        seen = []
        FakeJira.routes["/rest/api/3/myself"] = lambda q: {"displayName": "x"}

        class Recording(FakeJira):
            def do_GET(self):
                seen.append(self.headers.get("Authorization"))
                super().do_GET()
        server = ThreadingHTTPServer(("127.0.0.1", 0), Recording)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            self.make_client(
                f"http://127.0.0.1:{server.server_address[1]}").whoami()
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(seen, ["Basic bWVAYWNtZS50ZXN0OnMzY3JldC10b2tlbg=="])

    def test_error_statuses(self):
        for code, body, expected in [
                (401, {}, "401 Unauthorized for /rest/api/3/myself. Check that your `api-token`"),
                (403, {}, "403 Forbidden for /rest/api/3/myself"),
                (500, {"errorMessages": ["boom"]},
                 'Jira returned 500 for /rest/api/3/myself: {"errorMessages": ["boom"]}')]:
            with self.subTest(code=code):
                FakeJira.routes["/rest/api/3/myself"] = (code, body)
                self.assert_exits(expected, self.client.whoami)

    def test_404_is_not_found(self):
        error = self.assert_exits(
            "404 Not Found for /rest/api/3/myself", self.client.whoami)
        self.assertIsInstance(error, jira.NotFound)

    def test_unreachable_site(self):
        client = self.make_client("http://127.0.0.1:9")
        self.assert_exits("could not reach http://127.0.0.1:9 (your `base-url` setting)",
                          client.whoami)

    # --- queries and paging

    def test_queries(self):
        # name: (path, its empty answer, call, expected query, query keys left out)
        cases = [
            ("board sprints in a state", "/rest/agile/1.0/board/42/sprint", {"values": [], "isLast": True},
             lambda: self.client.sprints_for_board(42, state="closed"), {"state": "closed"}, ()),
            ("board sprints in any state", "/rest/agile/1.0/board/42/sprint", {"values": [], "isLast": True},
             lambda: self.client.sprints_for_board(42), {}, ("state",)),
            ("boards of a project", "/rest/agile/1.0/board", {"values": [], "isLast": True},
             lambda: self.client.boards_for_project("PROJ"), {"projectKeyOrId": "PROJ"}, ()),
            ("sprint issue fields", "/rest/agile/1.0/sprint/7/issue", {"issues": [], "total": 0},
             lambda: self.client.sprint_issues(7, ["summary", "status"]), {"fields": "summary,status"}, ()),
        ]
        for name, path, answer, call, expected, absent in cases:
            with self.subTest(name):
                FakeJira.requests = []
                FakeJira.routes[path] = answer
                call()
                query = FakeJira.requests[0][1]
                self.assertEqual({k: query.get(k) for k in expected}, expected)
                for key in absent:
                    self.assertNotIn(key, query)

    def test_paging(self):
        cases = [
            # The server caps board sprints at 50 even when asked for 100.
            ("continues after a short page", "/rest/agile/1.0/board/42/sprint",
             lambda: self.client.sprints_for_board(42),
             [(0, {"values": [{"id": i} for i in range(50)], "isLast": False}),
              (50, {"values": [{"id": 50}], "isLast": True})], 51, ["0", "50"]),
            ("stops on an empty page", "/rest/agile/1.0/board", lambda: self.client.boards_for_project("PROJ"),
             [(0, {"values": [{"id": 1}]}), (1, {"values": []})], 1, ["0", "1"]),
            ("stops at the total", "/rest/agile/1.0/sprint/7/issue",
             lambda: self.client.sprint_issues(7, ["summary", "status"]),
             [(0, {"issues": [{"id": 1}, {"id": 2}], "total": 3}),
              (2, {"issues": [{"id": 3}], "total": 3})],
             3, ["0", "2"]),
            ("stops at the total of comments", "/rest/api/3/issue/PROJ-1/comment",
             lambda: self.client.comments("PROJ-1"),
             [(0, {"comments": [{"id": 1}, {"id": 2}], "total": 3}),
              (2, {"comments": [{"id": 3}], "total": 3})],
             3, ["0", "2"]),
        ]
        for name, path, call, answers, count, starts in cases:
            with self.subTest(name):
                FakeJira.requests = []
                FakeJira.routes[path] = pages(*answers)
                self.assertEqual(len(call()), count)
                self.assertEqual([q["startAt"]
                                 for _, q in FakeJira.requests], starts)

    def test_issues_by_keys_follows_the_page_token(self):
        def search(query):
            if "nextPageToken" not in query:
                return {"issues": [{"key": "PROJ-1"}], "nextPageToken": "t2"}
            return {"issues": [{"key": "PROJ-2"}]}
        FakeJira.routes["/rest/api/3/search/jql"] = search
        issues = self.client.issues_by_keys(["PROJ-1", "PROJ-2"], ["summary"])
        self.assertEqual([i["key"] for i in issues], ["PROJ-1", "PROJ-2"])
        self.assertEqual(FakeJira.requests[0]
                         [1]["jql"], "key in (PROJ-1,PROJ-2)")
        self.assertEqual(FakeJira.requests[1][1]["nextPageToken"], "t2")

    def test_issues_by_keys_without_keys_asks_nothing(self):
        self.assertEqual(self.client.issues_by_keys([], ["summary"]), [])
        self.assertEqual(FakeJira.requests, [])

    def test_issues_by_ids(self):
        FakeJira.routes["/rest/api/3/search/jql"] = {
            "issues": [{"key": "PROJ-100"}]}
        self.assertEqual(self.client.issues_by_ids(
            ["1001"], ["summary"]), [{"key": "PROJ-100"}])
        self.assertEqual(FakeJira.requests[0][1]["jql"], "id in (1001)")
        self.assertEqual(self.client.issues_by_ids([], ["summary"]), [])

    def test_field_changes_reads_every_page_names_fields_and_sorts_by_instant(self):
        def entry(created, *items):
            return {"created": created, "items": list(items)}
        sprint = {"field": "Sprint", "fieldId": "customfield_10020",
                  "from": "6", "to": "6, 7"}
        FakeJira.routes["/rest/api/3/issue/PROJ-1/changelog"] = pages(
            (0, {"values": [entry("2026-03-29T09:30:00.000+0200", sprint),
                            entry("2026-03-29T08:00:00.000+0200",
                                  {"field": "status", "fieldId": "status", "from": "1", "fromString": "To Do",
                                   "to": "3", "toString": "Done"},
                                  {"field": "summary", "fieldId": "summary"})],
                 "total": 3, "isLast": False}),
            # 08:00+01:00 is 09:00+02:00: earlier than the first entry despite the string.
            (2, {"values": [entry("2026-03-29T08:00:00.000+0100",
                                  {"field": "IssueParentAssociation", "to": "1001", "toString": "PROJ-100"})],
                 "total": 3, "isLast": True}))
        changes = self.client.field_changes(
            "PROJ-1", {"sprint": "Sprint", "status": "status", "parent": "IssueParentAssociation",
                       "points": None})
        self.assertEqual([(c["created"], c["field"]) for c in changes], [
            ("2026-03-29T08:00:00.000+0200", "status"),
            ("2026-03-29T08:00:00.000+0100", "parent"),
            ("2026-03-29T09:30:00.000+0200", "sprint")])
        self.assertEqual(changes[0], {"created": "2026-03-29T08:00:00.000+0200", "field": "status",
                                      "from": "1", "to": "3", "fromString": "To Do", "toString": "Done"})

    def test_value_at(self):
        changes = [
            {"created": "2026-03-02T10:00:00.000+0000", "field": "status",
             "from": "1", "fromString": "To Do", "to": "2", "toString": "In Progress"},
            {"created": "2026-03-05T10:00:00.000+0000", "field": "status",
             "from": "2", "fromString": "In Progress", "to": "3", "toString": "Done"},
            {"created": "2026-03-04T10:00:00.000+0000", "field": "priority",
             "from": "2", "fromString": "Low", "to": "1", "toString": "High"},
        ]
        current = ("4", "Reopened")
        cases = [("2026-03-01T00:00:00.000+0000", ("1", "To Do")),
                 ("2026-03-02T10:00:00.000+0000", ("2", "In Progress")),
                 ("2026-03-04T23:00:00.000+0000", ("2", "In Progress")),
                 ("2026-03-09T00:00:00.000+0000", ("3", "Done"))]
        for instant, expected in cases:
            with self.subTest(instant=instant):
                self.assertEqual(jira.value_at(
                    changes, "status", jira.parse_ts(instant), current), expected)
        self.assertEqual(jira.value_at(changes, "points", jira.parse_ts(
            cases[0][0]), (None, "3")), (None, "3"))

    # --- board and sprint report

    def estimation(self, statistic):
        FakeJira.routes["/rest/greenhopper/1.0/rapidviewconfig/editmodel.json"] = {
            "estimationStatisticConfig": {"currentEstimationStatistic": statistic}}

    def test_board_estimation_field(self):
        cases = [({"typeId": "field", "fieldId": "customfield_10016"}, "customfield_10016"),
                 ({"typeId": "issueCount"}, None), (None, None)]
        for statistic, expected in cases:
            with self.subTest(statistic=statistic):
                FakeJira.routes.pop(
                    "/rest/greenhopper/1.0/rapidviewconfig/editmodel.json", None)
                if statistic:
                    self.estimation(statistic)
                self.assertEqual(
                    self.client.board_estimation_field(42), expected)
        self.assertEqual(FakeJira.requests[0][1]["rapidViewId"], "42")

    def test_sprint_report(self):
        report = {"contents": {"puntedIssues": []}}
        FakeJira.routes["/rest/greenhopper/1.0/rapid/charts/sprintreport"] = report
        self.assertEqual(self.client.sprint_report(42, 7), report)
        self.assertEqual(FakeJira.requests[0][1], {
                         "rapidViewId": "42", "sprintId": "7"})

    def test_sprint_report_in_an_unexpected_shape(self):
        for body in ({}, {"contents": {}}):
            with self.subTest(body=body):
                FakeJira.routes["/rest/greenhopper/1.0/rapid/charts/sprintreport"] = body
                self.assert_exits("unexpected shape (no contents.puntedIssues)",
                                  lambda: self.client.sprint_report(42, 7))

    # --- fields

    def fields(self, *names):
        FakeJira.routes["/rest/api/3/field"] = [
            {"id": f"customfield_{i}", "name": name} for i, name in enumerate(names)]

    def test_flagged_and_points_fields(self):
        cases = [
            ("the board's own field", ("Flagged", "Story Points"), {"typeId": "field", "fieldId": "customfield_77"},
             ("customfield_0", "customfield_77")),
            ("by name, in order", ("Story point estimate",
             "Story Points"), None, (None, "customfield_1")),
            ("none", ("Flagged",), None, ("customfield_0", None)),
        ]
        for name, names, statistic, expected in cases:
            with self.subTest(name):
                FakeJira.routes.pop(
                    "/rest/greenhopper/1.0/rapidviewconfig/editmodel.json", None)
                self.fields(*names)
                if statistic:
                    self.estimation(statistic)
                self.assertEqual(
                    self.client.flagged_and_points_fields(42), expected)

    # --- find_sprint

    def board_sprints(self, board_id, *sprints):
        FakeJira.routes[f"/rest/agile/1.0/board/{board_id}/sprint"] = lambda q: {
            "values": [s for s in sprints if not q.get("state") or s["state"] == q["state"]],
            "isLast": True}

    def boards(self, *boards):
        FakeJira.routes["/rest/agile/1.0/board"] = {
            "values": list(boards), "isLast": True}

    def sprint(self, sprint_id, state="closed", name=None, complete=None, board=42):
        return {"id": sprint_id, "name": name or f"Sprint {sprint_id}", "state": state,
                "completeDate": complete, "endDate": None, "originBoardId": board}

    def test_find_sprint_by_id(self):
        FakeJira.routes["/rest/agile/1.0/sprint/7"] = {"id": 7}
        self.assertEqual(self.client.find_sprint(sprint_id="7"), {"id": 7})

    def test_find_latest_closed_sprint_on_the_projects_scrum_boards(self):
        self.boards({"id": 41, "type": "kanban"}, {"id": 42, "type": "scrum"})
        self.board_sprints(42, self.sprint(6, complete="2026-02-27T16:00:00.000Z"),
                           self.sprint(7, complete="2026-03-13T16:00:00.000Z"),
                           self.sprint(8, state="active"))
        self.assertEqual(self.client.find_sprint(project="PROJ")["id"], 7)
        self.assertNotIn("/rest/agile/1.0/board/41/sprint", self.paths())

    def test_find_sprint_dedupes_across_boards_and_warns(self):
        self.boards({"id": 42, "type": "scrum"}, {"id": 43, "type": "scrum"})
        shared = self.sprint(7, complete="2026-03-13T16:00:00.000Z")
        self.board_sprints(42, shared)
        self.board_sprints(43, shared, self.sprint(
            5, complete="2026-01-30T16:00:00.000Z", board=43))
        warnings = []
        self.assertEqual(self.client.find_sprint(
            project="PROJ", log=warnings.append)["id"], 7)
        self.assertEqual(len(warnings), 1)
        self.assertIn("closed sprints span several boards", warnings[0])

    def test_find_active_sprint(self):
        self.board_sprints(42, self.sprint(6), self.sprint(7, state="active"))
        self.assertEqual(self.client.find_sprint(
            board_id=42, active=True)["id"], 7)

    def test_find_sprint_by_name_in_any_state(self):
        self.board_sprints(42, self.sprint(6), self.sprint(
            7, state="active", name="Sprint X"))
        self.assertEqual(self.client.find_sprint(
            board_id=42, name="Sprint X")["id"], 7)
        self.assertNotIn("state", FakeJira.requests[0][1])

    def test_find_sprint_failures(self):
        cases = [
            (lambda: self.boards({"id": 41, "type": "kanban"}), {"project": "PROJ"},
             "no scrum board found for project PROJ"),
            (lambda: self.board_sprints(42, self.sprint(6)), {"board_id": 42, "active": True},
             "no sprint active found on board(s) [42]"),
            (lambda: self.board_sprints(42, self.sprint(6)), {"board_id": 42, "name": "Nope"},
             "no sprint named 'Nope' found"),
            (lambda: self.board_sprints(42, self.sprint(6, state="active"), self.sprint(7, state="active")),
             {"board_id": 42, "active": True}, "2 sprints match (ids [6, 7]); give a sprint id or a board"),
        ]
        for setup, selectors, expected in cases:
            with self.subTest(expected):
                setup()
                self.assert_exits(
                    expected, lambda: self.client.find_sprint(**selectors))


if __name__ == "__main__":
    unittest.main()
