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
    path is a 404. Every request is recorded in `requests` as (path, query),
    and its Authorization header in `authorizations`."""
    routes = {}
    requests = []
    authorizations = []

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        FakeJira.requests.append((url.path, query))
        FakeJira.authorizations.append(self.headers.get("Authorization"))
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
        # Jira's formats, with or without milliseconds; None: a format it
        # doesn't use is refused rather than guessed.
        for ts, iso in [("2026-03-29T10:00:00.000+0100", "2026-03-29T10:00:00+01:00"),
                        ("2026-03-29T10:00:00+0200", "2026-03-29T10:00:00+02:00"),
                        ("2026-03-29T09:00:00.000Z", "2026-03-29T09:00:00+00:00"),
                        ("29/03/2026", None)]:
            with self.subTest(ts=ts):
                if iso is None:
                    with self.assertRaises(ValueError):
                        jira.parse_ts(ts)
                else:
                    self.assertEqual(jira.parse_ts(ts).isoformat(), iso)

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

    def test_issue_key(self):
        self.assertEqual(jira.ISSUE_KEY.findall("PROJ-1, A2B-30 and proj-4 or X-1a"),
                         ["PROJ-1", "A2B-30"])

    def test_plain_text(self):
        def para(*nodes):
            return {"type": "paragraph", "content": list(nodes)}

        def txt(value):
            return {"type": "text", "text": value}
        adf = {"type": "doc", "content": [
            {"type": "heading", "content": [txt("Goal")]},
            para(txt("Let staff  sign in"), {
                 "type": "hardBreak"}, txt("with SSO.")),
            {"type": "bulletList", "content": [
                {"type": "listItem", "content": [
                    para(txt("Ask "), {"type": "mention", "attrs": {"text": "@Ann"}})]},
                {"type": "listItem", "content": [
                    para({"type": "inlineCard", "attrs": {"url": "https://acme.test"}})]},
            ]},
            {"type": "table", "content": [{"type": "tableRow", "content": [
                {"type": "tableHeader", "content": [para(txt("A"))]},
                {"type": "tableCell", "content": [para(txt("B"))]}]}]},
        ]}
        cases = [
            ("none", None, ""),
            ("empty string", "", ""),
            ("wiki text", "Line one\n\n  Line   two ", "Line one\nLine two"),
            ("document", adf, "Goal\nLet staff sign in\nwith SSO.\nAsk @Ann\nhttps://acme.test\nA | B"),
            ("date", {"type": "date", "attrs": {
             "timestamp": "1690344879000"}}, "26/07/2023"),
            ("date in prose", para(txt("Blocked until "),
             {"type": "date", "attrs": {"timestamp": "1690344879000"}}, txt(".")),
             "Blocked until 26/07/2023."),
        ]
        for name, value, expected in cases:
            with self.subTest(name):
                self.assertEqual(jira.plain_text(value), expected)


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
        self.reset_jira()
        self.client = self.make_client(self.base_url + "/")

    def reset_jira(self):
        FakeJira.routes = {}
        FakeJira.requests = []
        FakeJira.authorizations = []

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

    def test_whoami_with_basic_auth_at_the_base_url(self):
        # The base-url's trailing slash is dropped, and every request carries
        # the email and token as basic auth.
        profile = {"displayName": "Alex Example", "timeZone": "Europe/London"}
        FakeJira.routes["/rest/api/3/myself"] = profile
        self.assertEqual(self.client.base_url, self.base_url)
        self.assertEqual(self.client.whoami(), profile)
        self.assertEqual(FakeJira.authorizations, [
                         "Basic bWVAYWNtZS50ZXN0OnMzY3JldC10b2tlbg=="])

    def test_errors(self):
        # name: (Jira's answer, the client's base-url if not the fake's,
        # expected in the message, the error's type)
        cases = [
            ("401", (401, {}), None, "401 Unauthorized for /rest/api/3/myself. Check that your `api-token`",
             SystemExit),
            ("403", (403, {}), None, "403 Forbidden for /rest/api/3/myself", SystemExit),
            ("500", (500, {"errorMessages": ["boom"]}), None,
             'Jira returned 500 for /rest/api/3/myself.', SystemExit),
            ("reflected token", (500, {"errorMessages": [TOKEN]}), None,
             'Jira returned 500 for /rest/api/3/myself.', SystemExit),
            # A missing resource has its own type, so callers can tell it apart.
            ("404", None, None, "404 Not Found for /rest/api/3/myself", jira.NotFound),
            ("unreachable site", None, "http://127.0.0.1:9",
             "could not reach Jira. Check your `base-url` setting", SystemExit),
        ]
        for name, answer, base_url, expected, kind in cases:
            with self.subTest(name):
                self.reset_jira()
                if answer:
                    FakeJira.routes["/rest/api/3/myself"] = answer
                client = self.make_client(
                    base_url) if base_url else self.client
                self.assertIsInstance(self.assert_exits(
                    expected, client.whoami), kind)
        with mock.patch.object(jira, "urlopen", side_effect=jira.URLError(TOKEN)):
            error = self.assert_exits(
                "could not reach Jira", self.client.whoami)
        self.assertNotIn(self.client.base_url, str(error))

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
        for first in ([{"key": "PROJ-1"}], []):
            with self.subTest(first=first):
                def search(query):
                    if "nextPageToken" not in query:
                        return {"issues": first, "nextPageToken": "t2"}
                    return {"issues": [{"key": "PROJ-2"}]}
                FakeJira.requests = []
                FakeJira.routes["/rest/api/3/search/jql"] = search
                issues = self.client.issues_by_keys(
                    ["PROJ-1", "PROJ-2"], ["summary"])
                self.assertEqual(issues, first + [{"key": "PROJ-2"}])
                self.assertEqual(
                    FakeJira.requests[0][1]["jql"], "key in (PROJ-1,PROJ-2)")
                self.assertEqual(
                    FakeJira.requests[1][1]["nextPageToken"], "t2")

    def test_issues_by_keys_and_ids(self):
        # Each searches by its JQL; with nothing to look up, it asks nothing
        # rather than a query that matches every issue.
        FakeJira.routes["/rest/api/3/search/jql"] = {
            "issues": [{"key": "PROJ-100"}]}
        cases = [("keys", self.client.issues_by_keys, ["PROJ-100"], "key in (PROJ-100)"),
                 ("ids", self.client.issues_by_ids, ["1001"], "id in (1001)")]
        for name, search, values, jql in cases:
            with self.subTest(name):
                FakeJira.requests = []
                self.assertEqual(search([], ["summary"]), [])
                self.assertEqual(FakeJira.requests, [])
                self.assertEqual(search(values, ["summary"]), [
                                 {"key": "PROJ-100"}])
                self.assertEqual(FakeJira.requests[0][1]["jql"], jql)

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
        # None: a report without its removed issues is refused, as it can't
        # be checked against.
        report = {"contents": {"puntedIssues": []}}
        for body, expected in ((report, report), ({}, None), ({"contents": {}}, None)):
            with self.subTest(body=body):
                self.reset_jira()
                FakeJira.routes["/rest/greenhopper/1.0/rapid/charts/sprintreport"] = body
                if expected is None:
                    self.assert_exits("unexpected shape (no contents.puntedIssues)",
                                      lambda: self.client.sprint_report(42, 7))
                else:
                    self.assertEqual(
                        self.client.sprint_report(42, 7), expected)
                self.assertEqual(FakeJira.requests[0][1], {
                                 "rapidViewId": "42", "sprintId": "7"})

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

    def test_find_sprint(self):
        # Each case finds sprint 7, logging only the warnings given.
        def kanban_and_scrum():
            self.boards({"id": 41, "type": "kanban"},
                        {"id": 42, "type": "scrum"})
            self.board_sprints(42, self.sprint(6, complete="2026-02-27T16:00:00.000Z"),
                               self.sprint(
                                   7, complete="2026-03-13T16:00:00.000Z"),
                               self.sprint(8, state="active"))

        def latest_by(field):
            # 17:30+02:00 is 15:30Z: earlier than sprint 7, despite the string.
            def setup():
                older, newer = self.sprint(6), self.sprint(7)
                older[field] = "2026-03-13T17:30:00+0200"
                newer[field] = "2026-03-13T16:00:00Z"
                self.board_sprints(42, older, newer, self.sprint(5))
            return setup

        def shared_by_two_boards():
            self.boards({"id": 42, "type": "scrum"},
                        {"id": 43, "type": "scrum"})
            shared = self.sprint(7, complete="2026-03-13T16:00:00.000Z")
            self.board_sprints(42, shared)
            self.board_sprints(43, shared, self.sprint(
                5, complete="2026-01-30T16:00:00.000Z", board=43))
        # name: (Jira's boards and sprints, selectors, warnings expected)
        cases = [
            ("by id", lambda: FakeJira.routes.update({"/rest/agile/1.0/sprint/7": {"id": 7}}),
             {"sprint_id": "7"}, []),
            # Only the project's scrum boards are asked, not kanban board 41.
            ("the latest closed on the project's scrum boards",
             kanban_and_scrum, {"project": "PROJ"}, []),
            ("the latest by completion instant", latest_by(
                "completeDate"), {"board_id": 42}, []),
            ("the latest by end instant, without a completion",
             latest_by("endDate"), {"board_id": 42}, []),
            ("one sprint on two boards, counted once", shared_by_two_boards, {"project": "PROJ"},
             ["closed sprints span several boards"]),
            ("the active one", lambda: self.board_sprints(42, self.sprint(6), self.sprint(7, state="active")),
             {"board_id": 42, "active": True}, []),
            ("by name, in any state",
             lambda: self.board_sprints(42, self.sprint(
                 6), self.sprint(7, state="active", name="Sprint X")),
             {"board_id": 42, "name": "Sprint X"}, []),
        ]
        for name, setup, selectors, warnings in cases:
            with self.subTest(name):
                self.reset_jira()
                setup()
                logged = []
                self.assertEqual(self.client.find_sprint(
                    log=logged.append, **selectors)["id"], 7)
                self.assertEqual(len(logged), len(warnings), logged)
                for warning, expected in zip(logged, warnings):
                    self.assertIn(expected, warning)
                self.assertNotIn(
                    "/rest/agile/1.0/board/41/sprint", self.paths())

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
