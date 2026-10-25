"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/jira.py.
Run with: python3 tests/run.py agentic-manager-utils-lib

The client talks to a local fake Jira, whose answers each test sets in
FakeJira.routes. read_source is patched, so no config is read.
"""

import io
import json
import os
import re
import sys
import threading
import unittest
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock
from urllib.parse import parse_qs, urlparse

# tests/<skill>/ mirrors skills/<skill>/.
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", os.path.basename(TEST_DIR)))
from agentic_manager import batch, jira, retry  # noqa: E402

TOKEN = "s3cret-token"


class FakeJira(BaseHTTPRequestHandler):
    """Answers each path from `routes`: a payload, or a function of the query,
    or of a POST's JSON body, that returns one. A payload of (code, body)
    sends that status. Any other path is a 404. Every request is recorded in
    `requests` as (path, query or body), and its Authorization header in
    `authorizations`; a POST's Content-Type in `content_types`."""
    routes = {}
    requests = []
    authorizations = []
    content_types = []

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        url = urlparse(self.path)
        self.answer(url.path, {k: v[0]
                    for k, v in parse_qs(url.query).items()})

    def do_POST(self):
        FakeJira.content_types.append(self.headers.get("Content-Type"))
        self.answer(urlparse(self.path).path, json.loads(
            self.rfile.read(int(self.headers["Content-Length"]))))

    def answer(self, path, query):
        FakeJira.requests.append((path, query))
        FakeJira.authorizations.append(self.headers.get("Authorization"))
        answer = FakeJira.routes.get(
            path, (404, {"errorMessages": ["not found"]}))
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

    def test_browse_url(self):
        cases = [("https://acme.example", "PROJ-7", "https://acme.example/browse/PROJ-7"),
                 ("https://acme.example/jira", "AB2-10", "https://acme.example/jira/browse/AB2-10")]
        for base, key, expected in cases:
            with self.subTest(key=key):
                self.assertEqual(jira.browse_url(base, key), expected)
                # BROWSE_URL reads back the site and the project.
                match = jira.BROWSE_URL.fullmatch(expected)
                self.assertEqual(match and match.groups(),
                                 (base, key.split("-")[0]))

    def test_key_order(self):
        keys = ["PROJ-10", "ABC-3", "PROJ-2", "PROJ-x"]
        self.assertEqual(sorted(keys, key=jira.key_order),
                         ["ABC-3", "PROJ-2", "PROJ-10", "PROJ-x"])

    def test_project_of(self):
        # Up to the last hyphen; a key without one, such as a project key,
        # has none.
        cases = [("PROJ-12", "PROJ"), ("ABC-DEF-12", "ABC-DEF"), ("PROJ", "")]
        for key, expected in cases:
            with self.subTest(key=key):
                self.assertEqual(jira.project_of(key), expected)

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
        # With links, linked text is followed by its URL, unless it is the URL.
        linked = para({"type": "text", "text": "the design", "marks": [
            {"type": "link", "attrs": {"href": "https://acme.test/design"}}]}, txt(" and "),
            {"type": "text", "text": "https://acme.test/x", "marks": [
                {"type": "link", "attrs": {"href": "https://acme.test/x"}}]})
        for links, expected in [(False, "the design and https://acme.test/x"),
                                (True, "the design (https://acme.test/design) and https://acme.test/x")]:
            with self.subTest(links=links):
                self.assertEqual(jira.plain_text(
                    linked, links=links), expected)

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
        # Retries wait for real; here each wait is only recorded.
        sleep = mock.patch.object(retry.time, "sleep")
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

    def reset_jira(self):
        FakeJira.routes = {}
        FakeJira.requests = []
        FakeJira.authorizations = []
        FakeJira.content_types = []

    def make_client(self, base_url, excluded=()):
        settings = {"base-url": base_url, "email": "me@acme.test", "api-token": TOKEN,
                    "excluded-projects": list(excluded)}
        with mock.patch.object(jira, "read_source", return_value=settings) as read:
            client = jira.JiraClient()
        read.assert_called_once_with(
            "workflow", "jira-api", jira.SETTINGS, lists=(jira.EXCLUDED,))
        return client

    def paths(self):
        return [path for path, _ in FakeJira.requests]

    def assert_fails(self, expected, call):
        """The JiraError call() raises, whose explanation holds `expected`
        and never the token."""
        with self.assertRaises(jira.JiraError) as raised:
            call()
        self.assertIn(expected, raised.exception.explanation)
        self.assertNotIn(TOKEN, raised.exception.explanation)
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
        # Every final failure raises JiraError, with the message and advice
        # the user is shown, never Jira's body, which can echo the token.
        # name: (Jira's answer, the client's base-url if not the fake's,
        # the explanation, whether it is a 404)
        cases = [
            ("401", (401, {}), None, "Jira returned 401 Unauthorized for /rest/api/3/myself. Check that your "
             "`api-token` in sources.workflow.jira-api is valid and belongs to the account in your `email` "
             "setting.", False),
            ("403", (403, {}), None,
             "Jira returned 403 Forbidden for /rest/api/3/myself: the account lacks permission.", False),
            ("429", (429, {}), None,
             "Jira returned 429 Too Many Requests for /rest/api/3/myself. Wait a minute and run it again.", False),
            ("500", (500, {"errorMessages": ["boom"]}), None,
             "Jira returned 500 for /rest/api/3/myself.", False),
            ("reflected token", (500, {"errorMessages": [TOKEN]}), None,
             "Jira returned 500 for /rest/api/3/myself.", False),
            # A missing resource says so, so the client can answer None for it.
            ("404", None, None,
             "Jira returned 404 Not Found for /rest/api/3/myself.", True),
            ("unreachable site", None, "http://127.0.0.1:9",
             "could not reach Jira, after trying 4 times. Check your `base-url` setting in "
             "sources.workflow.jira-api and the connection.", False),
        ]
        for name, answer, base_url, expected, not_found in cases:
            with self.subTest(name):
                self.reset_jira()
                if answer:
                    FakeJira.routes["/rest/api/3/myself"] = answer
                client = self.make_client(
                    base_url) if base_url else self.client
                error = self.assert_fails(expected, client.whoami)
                self.assertEqual(
                    (error.explanation, str(error), error.not_found), (expected, expected, not_found))
        with mock.patch.object(jira, "urlopen", side_effect=jira.URLError(TOKEN)):
            error = self.assert_fails(
                "could not reach Jira", self.client.whoami)
        self.assertNotIn(self.client.base_url, str(error))

    def test_retries(self):
        # A dropped connection or a 5xx is tried again after each of
        # RETRY_WAITS; any other answer, a 429 rate limit included, is final
        # at once.
        # name: (Jira's answers in turn, expected answer or error, waits)
        busy, ok = (503, {}), (200, {"displayName": "Alex Example"})
        cases = [
            ("busy, then fine", [busy, busy, ok], {
             "displayName": "Alex Example"}, [1, 3]),
            ("busy every time", [
             busy] * 4, "Jira returned 503 for /rest/api/3/myself.", [1, 3, 9]),
            ("a rate limit isn't tried again", [(429, {})],
             "Jira returned 429 Too Many Requests for /rest/api/3/myself. Wait a minute and run it again.", []),
            ("not found isn't tried again", [(404, {})], "404 Not Found", []),
            ("unauthorized isn't tried again", [
             (401, {})], "401 Unauthorized", []),
        ]
        for name, answers, expected, waits in cases:
            with self.subTest(name):
                self.reset_jira()
                self.sleep.reset_mock()
                queue = list(answers)
                FakeJira.routes["/rest/api/3/myself"] = lambda query: queue.pop(
                    0)
                if isinstance(expected, dict):
                    self.assertEqual(self.client.whoami(), expected)
                else:
                    self.assert_fails(expected, self.client.whoami)
                self.assertEqual(len(FakeJira.requests), len(answers))
                self.assertEqual([c.args[0]
                                 for c in self.sleep.call_args_list], waits)
        # A dropped connection is tried again too.
        self.sleep.reset_mock()
        response = mock.MagicMock()
        response.__enter__.return_value = io.BytesIO(
            b'{"displayName": "Alex Example"}')
        with mock.patch.object(jira, "urlopen", side_effect=[ConnectionResetError(), response]) as opened:
            self.assertEqual(self.client.whoami(), {
                             "displayName": "Alex Example"})
        self.assertEqual(opened.call_count, 2)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [1])

    def test_retry_note(self):
        # The line a retry prints names the request's path, never its
        # query, which can hold JQL, and the kind of failure, from the
        # error's type alone, never its text, which can echo the token.
        # name: (the error a try raises, the line's start)
        path = "/rest/api/3/search/jql"
        unreachable = "Jira couldn't be reached"
        cases = [
            ("connection reset", ConnectionResetError(TOKEN),
             f"{unreachable} (connection reset) on {path}"),
            ("connection refused", ConnectionRefusedError(TOKEN),
             f"{unreachable} (connection refused) on {path}"),
            ("timed out", TimeoutError(TOKEN),
             f"{unreachable} (timed out) on {path}"),
            ("socket timeout", jira.socket.timeout(TOKEN),
             f"{unreachable} (timed out) on {path}"),
            ("name not resolved", jira.URLError(jira.socket.gaierror(8, TOKEN)),
             f"{unreachable} (name not resolved) on {path}"),
            ("wrapped reset", jira.URLError(ConnectionResetError(TOKEN)),
             f"{unreachable} (connection reset) on {path}"),
            ("text only", jira.URLError(TOKEN), f"{unreachable} on {path}"),
            ("another error", ConnectionAbortedError(
                TOKEN), f"{unreachable} on {path}"),
            ("busy", jira.HTTPError(f"{self.base_url}{path}?jql={TOKEN}", 503, TOKEN, Message(), None),
             f"Jira answered 503 on {path}"),
        ]
        for name, error, expected in cases:
            with self.subTest(name):
                response = mock.MagicMock()
                response.__enter__.return_value = io.BytesIO(
                    b'{"issues": [], "isLast": true}')
                with mock.patch.object(jira, "urlopen", side_effect=[error, response]), \
                        mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
                    self.client.search(
                        f"project = PROJ AND summary ~ {TOKEN}", ["summary"])
                self.assertEqual(stderr.getvalue(),
                                 f"{expected}, trying again in 1 s\n")

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

    # --- changelogs

    BATCH = "/rest/api/3/changelog/bulkfetch"
    MYSELF = "/rest/api/3/myself"
    SEARCH = "/rest/api/3/search/jql"
    # The account's profile, read for its time zone by the batched changelog.
    ZONE = {"timeZone": "Europe/Berlin"}
    # The fields of the changelog tests: the Sprint field by name, the status
    # by id, the parent logged without an id, and points never logged.
    TRACKED = {"sprint": "Sprint", "status": "status", "parent": "IssueParentAssociation",
               "points": None}

    def histories(self):
        """One issue's change histories, as both changelog endpoints give
        them: out of order across a daylight saving offset, with an
        untracked field and the parent logged by name alone."""
        def entry(created, *items):
            return {"id": created[11:16], "created": created, "items": list(items)}
        return [entry("2026-03-29T09:30:00.000+0200",
                      {"field": "Sprint", "fieldId": "customfield_10020", "from": "6", "to": "6, 7"}),
                entry("2026-03-29T08:00:00.000+0200",
                      {"field": "status", "fieldId": "status", "from": "1", "fromString": "To Do",
                       "to": "3", "toString": "Done"},
                      {"field": "summary", "fieldId": "summary"}),
                # 08:00+01:00 is 09:00+02:00: earlier than the first entry despite the string.
                entry("2026-03-29T08:00:00.000+0100",
                      {"field": "IssueParentAssociation", "to": "1001", "toString": "PROJ-100"})]

    def search_by_id(self, *known):
        """A search route that answers `id in (...)` with the issues of the
        ids `known` among those asked for, as Jira's search finds them."""
        def answer(query):
            asked = re.findall(r"\d+", query["jql"])
            return {"issues": [{"id": i, "key": f"PROJ-{i}"} for i in asked if i in known]}
        return answer

    def searches(self):
        """The JQL of each search made."""
        return [q["jql"] for path, q in FakeJira.requests if path == self.SEARCH]

    def batch_pages(self, *pages):
        """A batched-changelog route answering each request by its page token: pages[0]
        without one, pages[n] for token "t<n>", each page given the next
        token but the last."""
        def answer(body):
            index = int(body.get("nextPageToken", "t0")[1:])
            page = {"issueChangeLogs": pages[index]}
            if index + 1 < len(pages):
                page["nextPageToken"] = f"t{index + 1}"
            return page
        return answer

    def batch_requests(self):
        """The requests to the batched changelog endpoint, the profile read for
        the account's time zone left out."""
        return [r for r in FakeJira.requests if r[0] == self.BATCH]

    def test_field_changes_reads_every_page_names_fields_and_sorts_by_instant(self):
        # 08:00+01:00 is 09:00+02:00: the parent's change sorts between the
        # others despite its string; the summary isn't tracked, nor are
        # points, which have no changelog name.
        histories = self.histories()
        FakeJira.routes["/rest/api/3/issue/PROJ-1/changelog"] = pages(
            (0, {"values": histories[:2], "total": 3, "isLast": False}),
            (2, {"values": histories[2:], "total": 3, "isLast": True}))
        changes = self.client.field_changes("PROJ-1", self.TRACKED)
        self.assertEqual([(c["created"], c["field"]) for c in changes], [
            ("2026-03-29T08:00:00.000+0200", "status"),
            ("2026-03-29T08:00:00.000+0100", "parent"),
            ("2026-03-29T09:30:00.000+0200", "sprint")])
        self.assertEqual(changes[0], {"created": "2026-03-29T08:00:00.000+0200", "field": "status",
                                      "from": "1", "to": "3", "fromString": "To Do", "toString": "Done"})
        self.assertEqual([q["startAt"]
                         for _, q in FakeJira.requests], ["0", "2"])

    def test_batched_field_changes_match_field_changes(self):
        # The same history gives the same changes either way. It is asked for
        # by id, each page by its token, and comes back under keys in the
        # issues' order: one issue's history split over two pages is joined;
        # one without an entry, which a search by id finds, or with an empty
        # one, has no changes.
        histories = self.histories()
        FakeJira.routes[self.MYSELF] = self.ZONE
        FakeJira.routes["/rest/api/3/issue/PROJ-1/changelog"] = {
            "values": histories, "total": 3, "isLast": True}
        FakeJira.routes[self.BATCH] = self.batch_pages(
            [{"issueId": "10001", "changeHistories": histories[:1]},
             {"issueId": "10003", "changeHistories": []}],
            [{"issueId": "10001", "changeHistories": histories[1:]}])
        FakeJira.routes[self.SEARCH] = self.search_by_id("10002")
        one = self.client.field_changes("PROJ-1", self.TRACKED)
        self.assertEqual([c["field"] for c in one], [
                         "status", "parent", "sprint"])
        FakeJira.requests, FakeJira.authorizations = [], []
        issues = [{"id": "10002", "key": "PROJ-2"}, {"id": "10001", "key": "PROJ-1"},
                  {"id": 10003, "key": "PROJ-3"}]
        changes, gone = self.client.batched_field_changes(
            issues, self.TRACKED)
        self.assertEqual(list(changes), ["PROJ-2", "PROJ-1", "PROJ-3"])
        self.assertEqual(
            (changes, gone), ({"PROJ-2": [], "PROJ-1": one, "PROJ-3": []}, {}))
        self.assertEqual(self.searches(), ["id in (10002)"])
        ids = ["10002", "10001", "10003"]
        self.assertEqual(self.batch_requests(), [
            (self.BATCH, {"issueIdsOrKeys": ids,
             "maxResults": jira.BATCH_CHANGELOG_PAGE}),
            (self.BATCH, {"issueIdsOrKeys": ids, "maxResults": jira.BATCH_CHANGELOG_PAGE,
                          "nextPageToken": "t1"})])
        self.assertEqual(FakeJira.content_types, ["application/json"] * 2)
        self.assertEqual(set(FakeJira.authorizations), {
                         "Basic bWVAYWNtZS50ZXN0OnMzY3JldC10b2tlbg=="})
        # No issues, no request.
        FakeJira.requests = []
        self.assertEqual(
            self.client.batched_field_changes([], self.TRACKED), ({}, {}))
        self.assertEqual(FakeJira.requests, [])

    def test_batched_field_changes_an_issue_jira_has_none_of(self):
        # An issue left without an entry that the search by id doesn't find
        # either is Jira's answer: no changes, and why, worded as issue()
        # words it. The changelogs are asked for a batch of issues at a time;
        # the search asks only for the issues left out, a batch at a time, and
        # isn't made when every issue has an entry.
        FakeJira.routes[self.MYSELF] = self.ZONE
        FakeJira.routes[self.SEARCH] = self.search_by_id("2", "4")
        why = "Jira has no such ticket, or this account can't see it"
        # name: (the ids with an entry, the keys gone, the searches made)
        cases = [("some gone", ["1"], ["PROJ-3", "PROJ-5"], ["id in (2,3)", "id in (4,5)"]),
                 ("every issue has an entry", ["1", "2", "3", "4", "5"], [], [])]
        issues = [{"id": str(n), "key": f"PROJ-{n}"} for n in range(1, 6)]
        for name, logged, gone, searches in cases:
            with self.subTest(name), mock.patch.object(batch, "BATCH_SIZE", 2):
                FakeJira.requests = []
                FakeJira.routes[self.BATCH] = lambda body, logged=logged: {"issueChangeLogs": [
                    {"issueId": i, "changeHistories": self.histories()} for i in body["issueIdsOrKeys"] if i in logged]}
                changes, missing = self.client.batched_field_changes(
                    issues, self.TRACKED)
                self.assertEqual(
                    missing, {key: f"{key}: {why}" for key in gone})
                self.assertEqual(list(changes), [i["key"]
                                 for i in issues if i["key"] not in gone])
                self.assertEqual(self.searches(), searches)
                self.assertEqual([body["issueIdsOrKeys"] for _, body in self.batch_requests()],
                                 [["1", "2"], ["3", "4"], ["5"]])
                self.assertTrue(
                    all(len(changes[f"PROJ-{i}"]) == 3 for i in logged))
        _, unread = self.client.issue("PROJ-9", ["summary"])
        self.assertEqual(unread, f"PROJ-9: {why}")

    def test_batched_field_changes_times_and_order(self):
        # The batched read gives times in milliseconds: they are written as the
        # per-issue changelog writes them, in the account's time zone; the
        # changes of one instant go by field, whichever order Jira lists them.
        FakeJira.routes[self.MYSELF] = {"timeZone": "Europe/London"}
        at = 1791363196961  # 2026-10-07T08:53:16.961Z, 09:53 in London
        FakeJira.routes[self.BATCH] = self.batch_pages([{"issueId": "1", "changeHistories": [
            {"id": "1", "created": at, "items": [
                {"field": "status", "fieldId": "status", "to": "3"},
                {"field": "resolution", "fieldId": "resolution", "to": "1"}]}]}])
        changes = self.client.batched_field_changes([{"id": "1", "key": "PROJ-1"}],
                                                    {"status": "status", "resolution": "resolution"})[0]["PROJ-1"]
        self.assertEqual([(c["created"], c["field"]) for c in changes],
                         [("2026-10-07T09:53:16.961+0100", "resolution"), ("2026-10-07T09:53:16.961+0100", "status")])

    def test_batched_field_changes_failures(self):
        # A busy Jira is tried again; an answer that is final names the
        # endpoint; an excluded ticket is refused before any request.
        ok = (200, {"issueChangeLogs": []})
        cases = [("busy, then fine", [(503, {}), ok], None, [1]),
                 ("a bad request", [(400, {"errorMessages": [TOKEN]})],
                  f"Jira returned 400 for {self.BATCH}.", [])]
        issues = [{"id": "1", "key": "PROJ-1"}]
        for name, answers, expected, waits in cases:
            with self.subTest(name):
                self.reset_jira()
                self.sleep.reset_mock()
                queue = list(answers)
                FakeJira.routes[self.BATCH] = lambda body: queue.pop(0)
                FakeJira.routes[self.MYSELF] = self.ZONE
                FakeJira.routes[self.SEARCH] = self.search_by_id("1")
                if expected is None:
                    self.assertEqual(self.client.batched_field_changes(
                        issues, self.TRACKED), ({"PROJ-1": []}, {}))
                else:
                    self.assert_fails(expected, lambda: self.client.batched_field_changes(
                        issues, self.TRACKED))
                self.assertEqual(len(self.batch_requests()), len(answers))
                self.assertEqual([c.args[0]
                                 for c in self.sleep.call_args_list], waits)
        with self.subTest("excluded"):
            self.reset_jira()
            client = self.make_client(self.base_url, excluded=["SEC"])
            self.assert_fails("SEC-1 is of a project excluded by `excluded-projects`",
                              lambda: client.batched_field_changes(issues + [{"id": "2", "key": "SEC-1"}], {}))
            self.assertEqual(FakeJira.requests, [])

    def test_issue(self):
        # A moved ticket is found under its current key. One Jira doesn't
        # have, or of an excluded project, even one moved into it, is an
        # answer: nothing, with why, which a skill prints. Any other
        # failure is raised.
        FakeJira.routes["/rest/api/3/issue/OLD-1"] = {
            "id": "1", "key": "NEW-5", "fields": {}}
        FakeJira.routes["/rest/api/3/issue/OLD-2"] = {
            "id": "2", "key": "SEC-3", "fields": {}}
        FakeJira.routes["/rest/api/3/issue/BAD-1"] = (500, {})
        client = self.make_client(self.base_url, excluded=["SEC"])
        excluded = "is of a project excluded by `excluded-projects` in sources.workflow.jira-api: it is never read"
        # key: (the issue's key, or None; why it isn't read)
        cases = {"OLD-1": ("NEW-5", None),
                 "PROJ-404": (None, "PROJ-404: Jira has no such ticket, or this account can't see it"),
                 "OLD-2": (None, f"SEC-3 {excluded}"),
                 "SEC-4": (None, f"SEC-4 {excluded}")}
        for key, (found, why) in cases.items():
            with self.subTest(key):
                FakeJira.requests = []
                issue, unread = client.issue(key, ["summary", "status"])
                self.assertEqual(
                    (issue and issue["key"], unread), (found, why))
                self.assertEqual(FakeJira.requests, [] if key == "SEC-4" else [
                                 (f"/rest/api/3/issue/{key}", {"fields": "summary,status"})])
        self.assert_fails("Jira returned 500 for /rest/api/3/issue/BAD-1.",
                          lambda: client.issue("BAD-1", ["summary"]))

    def test_only_projects_the_account_sees_are_excluded_in_jql(self):
        # JQL refuses a project the account can't see, and no search returns
        # its tickets, so it is left out of the clause; each project is
        # looked up once.
        FakeJira.routes["/rest/api/3/search/jql"] = {"issues": []}
        FakeJira.routes["/rest/api/3/project/SEC"] = {"key": "SEC"}
        client = self.make_client(self.base_url, excluded=["GONE", "SEC"])
        for _ in range(2):
            client.search("text ~ x", ["summary"])
        self.assertEqual([q.get("jql") for path, q in FakeJira.requests if path.endswith("/search/jql")],
                         ['(text ~ x) AND project not in ("SEC")'] * 2)
        self.assertEqual([path for path, _ in FakeJira.requests if "/project/" in path],
                         ["/rest/api/3/project/GONE", "/rest/api/3/project/SEC"])
        # None seen: no clause, and a sprint's issues are asked without one.
        unseen = self.make_client(self.base_url, excluded=["GONE"])
        FakeJira.routes["/rest/agile/1.0/sprint/7/issue"] = {
            "issues": [], "total": 0}
        FakeJira.requests = []
        unseen.sprint_issues(7, ["summary"])
        self.assertNotIn("jql", FakeJira.requests[-1][1])

    def test_search_puts_the_exclusion_before_the_ordering(self):
        FakeJira.routes["/rest/api/3/search/jql"] = {
            "issues": [{"key": "PROJ-1"}]}
        FakeJira.routes["/rest/api/3/project/IN"] = {"key": "IN"}
        FakeJira.routes["/rest/api/3/project/SEC"] = {"key": "SEC"}
        client = self.make_client(self.base_url, excluded=["IN", "SEC"])
        cases = [("ordered", "parent = PROJ-1 order  BY key",
                  '(parent = PROJ-1) AND project not in ("IN","SEC") order  BY key'),
                 ("unordered", "text ~ retry",
                  '(text ~ retry) AND project not in ("IN","SEC")'),
                 ("only an ordering", "ORDER BY created", 'project not in ("IN","SEC") ORDER BY created')]
        for name, jql, sent in cases:
            with self.subTest(name):
                FakeJira.requests = []
                self.assertEqual(client.search(
                    jql, ["summary"]), [{"key": "PROJ-1"}])
                self.assertEqual(FakeJira.requests[-1][1]["jql"], sent)
        FakeJira.requests = []
        self.client.search("parent = PROJ-1 ORDER BY key", ["summary"])
        self.assertEqual(
            FakeJira.requests[0][1]["jql"], "parent = PROJ-1 ORDER BY key")

    def test_pull_requests(self):
        # Every code host the panel's summary names is asked for its pull
        # requests; none named, nothing more is asked.
        detail = "/rest/dev-status/latest/issue/detail"
        for hosts, expected in (({"host-a": {}}, [{"n": 1}, {"n": 2}]), ({}, [])):
            with self.subTest(hosts=hosts):
                self.reset_jira()
                FakeJira.routes["/rest/dev-status/latest/issue/summary"] = {
                    "summary": {"pullrequest": {"byInstanceType": hosts}}}
                FakeJira.routes[detail] = {"detail": [
                    {"pullRequests": [{"n": 1}]}, {"pullRequests": [{"n": 2}]}]}
                self.assertEqual(self.client.pull_requests("1001"), expected)
                self.assertEqual([q for path, q in FakeJira.requests if path == detail],
                                 [{"issueId": "1001", "applicationType": host, "dataType": "pullrequest"}
                                  for host in hosts])

    def test_project(self):
        # None for a project the site doesn't have, or one excluded, unasked;
        # any other failure is raised.
        FakeJira.routes["/rest/api/3/project/PROJ"] = {
            "key": "PROJ", "name": "Project"}
        FakeJira.routes["/rest/api/3/project/SEC"] = {"key": "SEC"}
        FakeJira.routes["/rest/api/3/project/BAD"] = (500, {})
        client = self.make_client(self.base_url, excluded=["SEC"])
        self.assertEqual(client.project("PROJ"), {
                         "key": "PROJ", "name": "Project"})
        for key in ("SHA", "SEC"):
            with self.subTest(key):
                self.assertIsNone(client.project(key))
        self.assertNotIn("/rest/api/3/project/SEC", self.paths())
        self.assert_fails("Jira returned 500 for /rest/api/3/project/BAD.",
                          lambda: client.project("BAD"))

    def test_remote_links(self):
        FakeJira.routes["/rest/api/3/issue/PROJ-1/remotelink"] = [
            {"object": {"title": "Design", "url": "https://acme.test/d"}}]
        self.assertEqual(self.client.remote_links("PROJ-1")
                         [0]["object"]["title"], "Design")

    def test_sprint_field(self):
        # A site can have other fields named Sprint; the one of its type is it.
        cases = [([{"id": "customfield_1", "name": "Sprint", "schema": {"custom": "labels"}},
                   {"id": "customfield_7", "name": "Sprint", "schema": {"custom": jira.SPRINT_TYPE}}], "customfield_7"),
                 ([{"id": "customfield_1", "name": "Sprint"}], None)]
        for fields, expected in cases:
            with self.subTest(expected):
                FakeJira.routes["/rest/api/3/field"] = fields
                self.assertEqual(self.client.sprint_field(), expected)

    # --- excluded projects

    def test_excluded_projects(self):
        # Searches leave SEC out in Jira, and nothing of it is asked for.
        client = self.make_client(self.base_url, excluded=["SEC"])
        FakeJira.routes.update({
            "/rest/api/3/project/SEC": {"key": "SEC"},
            "/rest/api/3/search/jql": {"issues": [{"key": "PROJ-1"}]},
            "/rest/agile/1.0/sprint/7/issue": {"issues": [{"key": "PROJ-1"}], "total": 1},
        })
        # name: (call, the JQL of its request)
        cases = [
            ("by key", lambda: client.issues_by_keys(["PROJ-1", "SEC-1"], ["summary"]),
             '(key in (PROJ-1)) AND project not in ("SEC")'),
            ("by id", lambda: client.issues_by_ids(["1001"], ["summary"]),
             '(id in (1001)) AND project not in ("SEC")'),
            ("a sprint's issues", lambda: client.sprint_issues(
                7, ["summary"]), 'project not in ("SEC")'),
        ]
        for name, call, jql in cases:
            with self.subTest(name):
                FakeJira.requests = []
                self.assertEqual(call(), [{"key": "PROJ-1"}])
                self.assertEqual(FakeJira.requests[-1][1].get("jql"), jql)
        # What a returned issue says of excluded projects is dropped: its
        # parent, links and sub-tasks.
        FakeJira.routes["/rest/api/3/issue/PROJ-2"] = {"id": "2", "key": "PROJ-2", "fields": {
            "parent": {"key": "SEC-7"},
            "issuelinks": [{"outwardIssue": {"key": "SEC-8"}}, {"inwardIssue": {"key": "PROJ-3"}}],
            "subtasks": [{"key": "SEC-9"}, {"key": "PROJ-4"}]}}
        self.assertEqual(client.issue("PROJ-2", ["parent"]), ({"id": "2", "key": "PROJ-2", "fields": {
            "issuelinks": [{"inwardIssue": {"key": "PROJ-3"}}], "subtasks": [{"key": "PROJ-4"}]}}, None))
        FakeJira.routes["/rest/api/3/search/jql"] = {"issues": [
            {"key": "PROJ-5", "fields": {"parent": {"key": "SEC-7"}}}]}
        self.assertEqual(client.search("text ~ x", ["parent"]), [
                         {"key": "PROJ-5", "fields": {}}])
        FakeJira.routes["/rest/agile/1.0/sprint/7/issue"] = {"issues": [
            {"key": "PROJ-6", "fields": {"parent": {"key": "SEC-7"}}}], "total": 1}
        self.assertEqual(client.sprint_issues(7, ["parent"]), [
                         {"key": "PROJ-6", "fields": {}}])
        # A request for an excluded ticket or project is refused, unsent.
        FakeJira.requests = []
        with self.subTest("only excluded keys"):
            self.assertEqual(client.issues_by_keys(["SEC-1"], ["summary"]), [])
        for name, call in [("changelog", lambda: client.field_changes("SEC-1", {})),
                           ("comments", lambda: client.comments("SEC-1")),
                           ("remote links", lambda: client.remote_links("SEC-1")),
                           ("boards", lambda: client.boards_for_project("SEC")),
                           ("a sprint by project", lambda: client.find_sprint(project="SEC"))]:
            with self.subTest(name):
                self.assert_fails(
                    "is of a project excluded by `excluded-projects`", call)
        self.assertEqual(FakeJira.requests, [])
        # Without excluded projects, queries are unchanged.
        self.client.issues_by_keys(["SEC-1"], ["summary"])
        self.client.sprint_issues(7, ["summary"])
        self.assertEqual([q.get("jql") for _, q in FakeJira.requests], [
                         "key in (SEC-1)", None])

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
                    self.assert_fails("unexpected shape (no contents.puntedIssues)",
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

    def test_field_ids(self):
        # Of two fields with one name, the first Jira lists.
        FakeJira.routes["/rest/api/3/field"] = [{"id": "customfield_1", "name": "Acceptance Criteria"},
                                                {"id": "customfield_2",
                                                    "name": "Acceptance Criteria"},
                                                {"id": "summary", "name": "Summary"}]
        self.assertEqual(self.client.field_ids(), {
                         "Acceptance Criteria": "customfield_1", "Summary": "summary"})

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
            ("by name alone, in the project its first word spells",
             lambda: (self.boards({"id": 42, "type": "scrum"}),
                      self.board_sprints(42, self.sprint(6), self.sprint(7, name="PROJ Sprint 7"))),
             {"name": "PROJ Sprint 7"}, []),
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
            # A name alone: a first word that is no project, or one without the sprint.
            (lambda: self.boards(), {"name": "Sprint 7"},
             "no scrum board found for project Sprint ('Sprint' is the first word of the sprint name"),
            (lambda: (self.boards({"id": 42, "type": "scrum"}), self.board_sprints(42, self.sprint(6))),
             {"name": "PROJ Nope"}, "no sprint named 'PROJ Nope' found on board(s) [42] ('PROJ'"),
            (lambda: self.board_sprints(42, self.sprint(6, state="active"), self.sprint(7, state="active")),
             {"board_id": 42, "active": True}, "2 sprints match (ids [6, 7]); give a sprint id or a board"),
        ]
        for setup, selectors, expected in cases:
            with self.subTest(expected):
                self.reset_jira()
                setup()
                self.assert_fails(
                    expected, lambda: self.client.find_sprint(**selectors))


if __name__ == "__main__":
    unittest.main()
