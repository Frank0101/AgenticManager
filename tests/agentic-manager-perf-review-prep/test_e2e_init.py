"""End-to-end tests for skills/agentic-manager-perf-review-prep/scripts/find_jira_account.py,
init_prep.py, find_person.py, set_identities.py, rules.py, set_summary.py,
read_notes.py, fetch_work.py,
set_notion.py, read_slack.py and check_prep.py: they run
each as a script, as the agent does, from looking the person up in Jira and
starting the prep on the account the manager confirmed, through who the
person is in each other source, their view, the person's previous reviews
and the period's feedback, the manager's notes, the person's work and their Slack
messages, to the final check. Each script's functions have unit tests of
their own, in test_<script>.py.
Run with: python3 tests/run.py agentic-manager-perf-review-prep

The scripts run against the library's tests' fake Jira, served on a local
port and set as the config's base-url, and its fake gh, put first on PATH,
so nothing reaches a service. The fake Jira holds the person's account and
two of their issues, one they resolved in the period, under an epic, and one
they created in it; the fake gh is in one organisation, where the person
opened and merged one pull request in the period, so the work flows through to the final check with an
item in every list. The period is a single day, which fetch_work.py
searches whole. Notion and Slack are the agent's, through their MCPs, so the
test gives their scripts what a search and a subagent would. HOME points at a temporary folder holding the test's own config, and
TMPDIR at the same folder, so nothing falls back to the system temp folder.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
SCRIPTS = os.path.join(REPO_ROOT, "skills",
                       os.path.basename(TEST_DIR), "scripts")
FAKES = os.path.join(os.path.dirname(TEST_DIR), "agentic-manager-utils-lib")
sys.path.insert(0, FAKES)
import jira_fake  # noqa: E402
from gh_fake import FAKE_GH  # noqa: E402
from jira_fake import FakeJira  # noqa: E402

ACCOUNT_SCRIPT = os.path.join(SCRIPTS, "find_jira_account.py")
INIT_SCRIPT = os.path.join(SCRIPTS, "init_prep.py")
FIND_SCRIPT = os.path.join(SCRIPTS, "find_person.py")
CHECK_SCRIPT = os.path.join(SCRIPTS, "check_prep.py")
IDENTITIES_SCRIPT = os.path.join(SCRIPTS, "set_identities.py")
SUMMARY_SCRIPT = os.path.join(SCRIPTS, "set_summary.py")
RULES_SCRIPT = os.path.join(SCRIPTS, "rules.py")
NOTES_SCRIPT = os.path.join(SCRIPTS, "read_notes.py")
WORK_SCRIPT = os.path.join(SCRIPTS, "fetch_work.py")
NOTION_SCRIPT = os.path.join(SCRIPTS, "set_notion.py")
SLACK_SCRIPT = os.path.join(SCRIPTS, "read_slack.py")
TOKEN = "s3cret-token"
JANE = {"accountId": "5b10ac8d82e05b22cc7d4ef5", "accountType": "atlassian", "displayName": "Jane Doe",
        "emailAddress": "jane@acme.test", "active": True}
# The period is today alone, so each reading has one month to read.
TODAY = date.today()
STAMP = f"{TODAY.isoformat()}T10:00:00Z"
# The person's pull request, opened and merged in the period.
PR = {"number": 7, "title": "Move invoices to the new billing service", "repository": {"nameWithOwner": "acme/billing"},
      "url": "https://github.com/acme/billing/pull/7", "createdAt": STAMP, "closedAt": STAMP,
      "author": {"login": "janedoe"}, "updatedAt": STAMP}
# What the fake gh answers, by the words of each command: signed in, the
# commit search by the Jira email, the login's profile, one organisation,
# and the pull request to both of fetch_work.py's searches, those opened and
# those merged in the period.
GH_ANSWERS = {"auth status": {}, "api": {"items": [{"author": {"login": "janedoe"}}]},
              "api users/janedoe": {"name": "Jane Doe"}, "api user/orgs?per_page=100": [{"login": "acme"}],
              "search prs": [PR]}
EPIC = {"key": "PROJ-1", "fields": {"summary": "Billing migration",
                                    "issuetype": {"name": "Epic"}}}
# The person's issues: one they resolved in the period, under the epic, and
# one they created in it.
RESOLVED = {"key": "PROJ-12", "id": "10012", "fields": {
    "summary": "Migrate invoices", "issuetype": {"name": "Story"}, "status": {"name": "Done"},
    "created": "2026-01-05T10:00:00.000+0000", "resolutiondate": f"{TODAY.isoformat()}T10:00:00.000+0000",
    "parent": EPIC, "assignee": {"accountId": JANE["accountId"]}, "reporter": None,
    "updated": f"{TODAY.isoformat()}T10:00:00.000+0000"}}
CREATED = {"key": "PROJ-13", "id": "10013", "fields": {
    "summary": "Retire the old billing service", "issuetype": {"name": "Story"}, "status": {"name": "To Do"},
    "created": f"{TODAY.isoformat()}T09:00:00.000+0000", "resolutiondate": None, "parent": None,
    "assignee": None, "reporter": {"accountId": JANE["accountId"]}, "updated": f"{TODAY.isoformat()}T09:00:00.000+0000"}}
# Who the person is in each source but Jira, as the manager confirmed.
CONFIRMED = {"github-cli": {"id": "janedoe", "name": "Jane Doe"},
             "notion-mcp": {"id": "2a4c1e8f-1234-4abc-9def-0123456789ab", "name": "Jane Doe"},
             "slack-mcp": {"id": "U012AB3CD", "name": "Jane Doe"},
             "logseq-fs": {"links": ["Jane"]}}
ORIENTATION = {"going_well": [{"point": "Has \"led\" the billing migration well since May, $quoted",
                               "values": ["Ownership"]}],
               "to_improve": [], "context": ["Came back from a long leave in May"]}
VALUES = [{"value": "Ownership", "meaning": "Sees work through to its end"}]
RATINGS = [{"rating": "Below", "meaning": "Misses most expectations"},
           {"rating": "Meets", "meaning": "Meets every expectation"}]
PIECE = {"period": "Mid Year Review", "rating": "Meets", "going_well": [{"point": "Delivered the billing migration on time", "values": []}],
         "to_improve": [], "context": []}
PAGE = {"title": "Billing plan",
        "url": "https://www.notion.so/billing-plan", "path": "Engineering"}
LINK = "https://acme.slack.com/archives/C1/p1"


def jira_routes():
    """The fake Jira's answers: the person's account, found by their name
    and read by its id; and their issues, resolved or created as the JQL
    asks."""
    return {"/rest/api/3/user/search": [JANE],
            "/rest/api/3/user": lambda query: JANE if query["accountId"] == JANE["accountId"]
            else (404, {"errorMessages": ["not found"]}),
            "/rest/api/3/search/jql": lambda query: {
                "issues": [RESOLVED if "statusCategory = Done" in query["jql"] else CREATED]}}


class ScriptsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.base_url = jira_fake.serve()

    @classmethod
    def tearDownClass(cls):
        jira_fake.stop(cls.server)

    def setUp(self):
        jira_fake.reset()
        FakeJira.routes = jira_routes()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = os.path.realpath(tmp.name)
        path = os.path.join(self.root, ".config",
                            "agentic-manager", "config.json")
        os.makedirs(os.path.dirname(path))
        graph = os.path.join(self.root, "graph", "journals")
        os.makedirs(graph)
        with open(os.path.join(graph, f"{TODAY:%Y_%m_%d}.md"), "w", encoding="utf-8") as f:
            f.write("- [[Jane]] presented the migration to the team\n")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"sources": {"workflow": {"jira-api": {"enabled": True, "base-url": self.base_url,
                                                             "email": "me@acme.test", "api-token": TOKEN}},
                                   "source_control": {"github-cli": {"enabled": True}},
                                   "local_vault": {"logseq-fs": {"enabled": True, "path": os.path.dirname(graph)}}},
                       "output": {"root": os.path.join(self.root, "out")},
                       "company": {"perf-review-ratings": RATINGS, "values": VALUES}}, f)
        self.bin_dir = os.path.join(self.root, "bin")
        os.makedirs(self.bin_dir)
        with open(os.path.join(self.bin_dir, "gh"), "w", encoding="utf-8") as f:
            f.write(FAKE_GH)
        os.chmod(os.path.join(self.bin_dir, "gh"), 0o755)
        self.gh_answers = os.path.join(self.root, "gh.json")
        with open(self.gh_answers, "w", encoding="utf-8") as f:
            json.dump(GH_ANSWERS, f)

    def run_script(self, script, *args, stdin=""):
        """(exit code, stdout, stderr) of the script, given `stdin`."""
        env = dict(os.environ, HOME=self.root, TMPDIR=self.root, FAKE_GH_ANSWERS=self.gh_answers,
                   FAKE_GH_LIB=FAKES, FAKE_GH_LOG=os.path.join(
                       self.root, "gh.log"),
                   PATH=self.bin_dir + os.pathsep + os.environ["PATH"])
        proc = subprocess.run([sys.executable, script, *args], env=env, input=stdin,
                              capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def run_ok(self, script, *args, stdin=""):
        """The JSON the script printed, once it ran well."""
        code, out, err = self.run_script(script, *args, stdin=stdin)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def read_slack(self, prep):
        """Runs the Slack reading as the agent does, its subagents
        answering: a task a month, then the merge, then finished."""
        started = self.run_ok(SLACK_SCRIPT, "start", "--prep", prep)
        for line in started["tasks"]:
            self.run_ok(SLACK_SCRIPT, "submit", "--prep", prep, "--task", line.split(": ")[0].removeprefix("Task "),
                        stdin=json.dumps({"items": [{"date": TODAY.isoformat(), "link": LINK,
                                                     "synopsis": "Posted the billing rollout plan"}]}))
        merged = {"going_well": [], "to_improve": [],
                  "context": [{"point": "Posted the billing rollout plan", "links": [LINK]}], "in_doubt": []}
        self.run_ok(SLACK_SCRIPT, "submit", "--prep", prep,
                    "--task", "merge", stdin=json.dumps(merged))
        self.assertEqual(self.run_ok(SLACK_SCRIPT, "finished",
                         "--prep", prep)["finished"], True)

    def test_starts_the_prep_and_checks_it(self):
        # As the skill runs them: find_jira_account.py looks the person up,
        # init_prep.py starts the prep on the account the manager
        # confirmed, find_person.py looks them up in GitHub and the vault,
        # set_identities.py records who they are, rules.py prints what the
        # summaries follow, set_summary.py records the summaries of the
        # manager's view, the previous reviews and the period's feedback, read_notes.py hands out the notes'
        # tasks and takes their answers, fetch_work.py and set_notion.py
        # record the work, read_slack.py the Slack messages, and
        # the work's facts are worked out once all three are in; check_prep.py
        # passes the prep, and fails it once the folder holds a file of the
        # agent's.
        found = self.run_ok(ACCOUNT_SCRIPT, "--person", "Jane Doe")
        self.assertEqual([account["accountId"] for account in found["accounts"]], [
                         JANE["accountId"]])
        # The prep is named after the account, whatever the manager calls
        # the person, and person.json keeps the manager's name and, until
        # step 2, only the Jira account.
        result = self.run_ok(INIT_SCRIPT, "--person", "Jane", "--account", JANE["accountId"],
                             "--start", TODAY.isoformat(), "--end", TODAY.isoformat())
        prep = result["prep"]
        self.assertEqual(prep, f"Jane-Doe_{TODAY:%y-%m-%d}")
        jira = {"jira-api": {"id": JANE["accountId"],
                             "name": "Jane Doe", "email": "jane@acme.test"}}
        self.assertEqual(result["person"], {"person": "Jane", "start": TODAY.isoformat(), "end": TODAY.isoformat(),
                                            "sources": jira})
        self.assertEqual(self.run_ok(FIND_SCRIPT, "--prep", prep), {
            "person": "Jane", "email": "jane@acme.test", "github": [{"login": "janedoe", "name": "Jane Doe"}],
            "vault": [{"link": "Jane", "mentions": 1, "page": False, "alias_of": None}]})
        self.assertEqual(self.run_ok(IDENTITIES_SCRIPT, "--prep", prep, stdin=json.dumps(CONFIRMED))["sources"],
                         {**jira, **CONFIRMED})
        self.assertEqual({key: value for key, value in self.run_ok(RULES_SCRIPT, "--prep", prep).items()
                          if key in ("values", "ratings")}, {"values": VALUES, "ratings": RATINGS})
        feedback = {"pieces": [
            {**{k: v for k, v in PIECE.items() if k != "rating"}, "period": None}]}
        for kind, recorded in [("orientation", ORIENTATION), ("reviews", {"pieces": [PIECE]}), ("feedback", feedback)]:
            with open(self.run_ok(SUMMARY_SCRIPT, "--prep", prep, "--of", kind, stdin=json.dumps(recorded))["path"],
                      encoding="utf-8") as f:
                self.assertEqual(json.load(f), recorded)
        started = self.run_ok(NOTES_SCRIPT, "start", "--prep", prep)
        month = f"month:{TODAY:%Y-%m}"
        self.assertEqual(([line.split(": ")[0] for line in started["tasks"]], started["merge"].split(": ")[0]),
                         ([f"Task {month}"], "Task merge"))
        item = {"note": 1, "synopsis": "Presented the migration to the team"}
        self.run_ok(NOTES_SCRIPT, "submit", "--prep", prep, "--task",
                    month, stdin=json.dumps({"items": [item]}))
        self.assertTrue(os.path.exists(started["merge"].split(": ", 1)[1]))
        merged = {"going_well": [{"point": item["synopsis"], "values": ["Ownership"],
                                  "links": [Path(self.root, "graph", "journals", f"{TODAY:%Y_%m_%d}.md").as_uri()]}],
                  "to_improve": [], "context": [], "in_doubt": []}
        self.run_ok(NOTES_SCRIPT, "submit", "--prep", prep,
                    "--task", "merge", stdin=json.dumps(merged))
        self.assertEqual(self.run_ok(NOTES_SCRIPT, "finished",
                         "--prep", prep)["finished"], True)
        # The work: Jira searched by the person's account there, both lists, the
        # pull request, opened and merged, and the Notion pages a search
        # found.
        fetched = self.run_ok(WORK_SCRIPT, "--prep", prep)
        self.assertEqual(fetched["counts"],
                         {"jira.resolved": 1, "jira.created": 1, "github.opened": 1, "github.merged": 1})
        searches = [query["jql"] for path,
                    query in FakeJira.requests if path == "/rest/api/3/search/jql"]
        self.assertEqual((len(searches), all(f'= "{JANE["accountId"]}"' in jql for jql in searches)),
                         (2, True))
        self.assertIsNone(fetched["work"])
        with open(fetched["raw"][0], encoding="utf-8") as f:
            jira = json.load(f)
        self.assertEqual(([issue["key"] for issue in jira["resolved"]], [issue["key"] for issue in jira["created"]],
                          jira["resolved_jql"], jira["base_url"]),
                         (["PROJ-12"], ["PROJ-13"], searches[0], self.base_url))
        with open(fetched["raw"][1], encoding="utf-8") as f:
            github = json.load(f)
        self.assertEqual(
            (github["opened"], github["merged"], github["orgs"]), ([PR], [PR], ["acme"]))
        day = {"start": TODAY.isoformat(), "end": TODAY.isoformat()}
        recorded = self.run_ok(NOTION_SCRIPT, "--prep", prep, stdin=json.dumps(
            {"created": [{**day, "pages": [PAGE]}], "edited": [{**day, "pages": [{**PAGE, "date": TODAY.isoformat()}]}]}))
        self.read_slack(prep)
        with open(recorded["work"], encoding="utf-8") as f:
            work = json.load(f)
        self.assertEqual(work["jira"]["resolved"], [
            {"key": "PROJ-12", "title": "Migrate invoices", "type": "Story",
             "parent": {"key": "PROJ-1", "title": "Billing migration", "type": "Epic"}, "status": "Done",
             "url": f"{self.base_url}/browse/PROJ-12", "date": TODAY.isoformat()}])
        self.assertEqual((work["jira"]["focus"], work["github"]["opened"]), (
            [{"key": "PROJ-1", "title": "Billing migration", "issues": 1}],
            [{"repo": "acme/billing", "number": 7, "title": PR["title"], "url": PR["url"], "date": TODAY.isoformat()}]))
        self.assertEqual(self.run_ok(CHECK_SCRIPT, "--prep", prep), {
                         "ok": True, "errors": []})
        open(os.path.join(result["prep_dir"], "draft.md"), "w").close()
        code, out, err = self.run_script(CHECK_SCRIPT, "--prep", prep)
        self.assertEqual(code, 1)
        self.assertIn("draft.md", out)

    def test_failures(self):
        # name: (script, arguments, exit code, expected on stderr)
        period = ["--start", "2026-01-01", "--end", "2026-06-30"]
        cases = [("no person", INIT_SCRIPT, ["--account", JANE["accountId"], *period], 2, "--person"),
                 ("no account", INIT_SCRIPT, [
                  "--person", "Jane Doe", *period], 2, "--account"),
                 ("not a date", INIT_SCRIPT, ["--person", "Jane Doe", "--account", JANE["accountId"],
                                              "--start", "01/01/2026", "--end", "2026-06-30"], 2, "YYYY-MM-DD"),
                 ("ends after today", INIT_SCRIPT, ["--person", "Jane Doe", "--account", JANE["accountId"],
                                                    "--start", "2026-01-01", "--end", "2999-01-01"], 1, "after today"),
                 ("an account Jira doesn't have", INIT_SCRIPT, ["--person", "Jane Doe", "--account", "a9", *period],
                  1, "Jira has no person's account a9"),
                 ("no person to look up", ACCOUNT_SCRIPT,
                  [], 2, "--person"),
                 ("no such prep", CHECK_SCRIPT, [
                  "--prep", "Jane-Doe_26-01-01"], 1, "run init_prep.py first"),
                 ("find for no prep", FIND_SCRIPT, [
                  "--prep", "Jane-Doe_26-01-01"], 1, "run init_prep.py first"),
                 ("identities that aren't JSON", IDENTITIES_SCRIPT, ["--prep", "Jane-Doe_26-01-01"], 1,
                  "the input isn't JSON"),
                 ("an orientation that isn't JSON", SUMMARY_SCRIPT, ["--prep", "Jane-Doe_26-01-01", "--of", "orientation"], 1,
                  "the input isn't JSON"),
                 ("reviews that aren't JSON", SUMMARY_SCRIPT, ["--prep", "Jane-Doe_26-01-01", "--of", "reviews"], 1,
                  "the input isn't JSON"),
                 ("feedback that isn't JSON", SUMMARY_SCRIPT, ["--prep", "Jane-Doe_26-01-01", "--of", "feedback"], 1,
                  "the input isn't JSON"),
                 ("finished for no prep", NOTES_SCRIPT, ["finished", "--prep", "Jane-Doe_26-01-01"], 1,
                  "run init_prep.py first"),
                 ("rules for no prep", RULES_SCRIPT, ["--prep", "Jane-Doe_26-01-01"], 1,
                  "run init_prep.py first")]
        for name, script, args, expected_code, expected in cases:
            with self.subTest(name):
                code, out, err = self.run_script(
                    script, *args, stdin="{not json")
                self.assertEqual((code, out), (expected_code, ""))
                self.assertIn(expected, err)


if __name__ == "__main__":
    unittest.main()
