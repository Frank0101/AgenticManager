"""Unit tests for skills/agentic-manager-tech-investigation/scripts/save_example.py.
The whole pipeline has end-to-end tests in test_e2e_pipeline.py.
Run with: python3 tests/run.py agentic-manager-tech-investigation

The config's path is patched to the test's own config, in a temporary folder.
"""

import os
import sys
import unittest
from datetime import date
from pathlib import Path

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                os.path.basename(TEST_DIR), "scripts"))
import init_investigation  # noqa: E402
import save_example  # noqa: E402
sys.path.insert(0, TEST_DIR)
from investigation_fixture import temp_output  # noqa: E402

TODAY = date(2026, 10, 5)
INVESTIGATION = "Acme-Search_26-10-05"
REPORT = "Acme-Search_Report.md"


class SaveExampleTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        init_investigation.init("Acme-Search", today=TODAY)
        self.source = Path(self.folder) / INVESTIGATION

    def write(self, files):
        for name, text in files.items():
            (self.source / name).write_text(text, encoding="utf-8")

    def test_copies_the_report_and_what_it_links_with_a_description(self):
        self.write({REPORT: "![Picture](picture.svg)\n[Ledger](ledger.md#f01)\n"
                            "[Web](https://example.com) [Missing](gone.md)\n",
                    "picture.svg": "<svg/>", "notes.md": "unlinked"})
        first = save_example.save(INVESTIGATION, "Clear roadmap.")
        self.assertEqual(sorted(first["files"]), [
                         REPORT, "ledger.md", "picture.svg"])
        # A second one of the same day never overwrites the first.
        second = save_example.save(INVESTIGATION, "Revised.")
        self.assertTrue(second["example"].endswith(f"{INVESTIGATION}--2"))
        with open(os.path.join(second["example"], "description.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), f"# {INVESTIGATION}--2\n\n**Why it's good:** Revised.\n\n"
                             f"The approved report: [{REPORT}]({REPORT}).\n")
        # The examples list reads each one's note from its description.
        listed = init_investigation.init("Other", today=TODAY)["examples"]
        self.assertEqual([(os.path.basename(e["folder"]), e["note"]) for e in listed],
                         [(f"{INVESTIGATION}--2", "Revised."), (INVESTIGATION, "Clear roadmap.")])

    def test_reference_links_and_fenced_examples(self):
        # Preserve all Markdown link forms and recursively linked documents,
        # while ignoring illustrative links inside code fences.
        for form in ["[Asset](asset.svg)", "[Asset][proof]", "[proof][]", "[proof]"]:
            with self.subTest(form=form):
                files = {REPORT: "[Details](details.md)\n```text\n[Ignored](ignored.svg)\n```",
                         "details.md": form + "\n\n[proof]: asset.svg\n",
                         "asset.svg": "<svg/>", "ignored.svg": "<svg/>"}
                self.write(files)
                result = save_example.save(INVESTIGATION, "Clear report.")
                self.assertEqual(sorted(result["files"]), [
                                 REPORT, "asset.svg", "details.md"])
                with open(os.path.join(result["example"], "details.md"), encoding="utf-8") as f:
                    self.assertEqual(f.read(), files["details.md"])

    def test_refusals(self):
        # name: (note, whether the report exists, expected message)
        cases = [("no report", "Note.", False, "has no Acme-Search_Report.md"),
                 ("blank note", " ", True, "one line"), ("two-line note", "a\nb", True, "one line")]
        for name, note, report, expected in cases:
            with self.subTest(name):
                if report:
                    self.write({REPORT: "Report."})
                with self.assertRaisesRegex(SystemExit, expected):
                    save_example.save(INVESTIGATION, note)

    def test_linked_symlinks_must_stay_inside_investigation(self):
        outside = self.source.parent / "external"
        outside.mkdir()
        (outside / "details.md").write_text("Invented external document.", encoding="utf-8")
        (outside / "asset.svg").write_text("<svg/>", encoding="utf-8")
        inside = self.source / "details.md"
        inside.write_text("Invented investigation document.", encoding="utf-8")
        archive = self.source.parent / "_examples"
        cases = [("document", outside / "details.md", "linked.md", "linked.md", False),
                 ("file", outside / "asset.svg", "linked.svg", "linked.svg", False),
                 ("directory", outside, "linked-dir",
                  "linked-dir/details.md", False),
                 ("inside", inside, "linked.md", "linked.md", True)]
        for name, destination, link_name, reference, valid in cases:
            with self.subTest(name=name):
                symlink = self.source / link_name
                symlink.symlink_to(
                    destination, target_is_directory=destination.is_dir())
                self.write({REPORT: f"[Details]({reference})"})
                before = {str(path.relative_to(archive)): path.read_bytes()
                          for path in archive.rglob("*") if path.is_file()}
                folders = sorted(str(path.relative_to(archive))
                                 for path in archive.rglob("*"))
                try:
                    if valid:
                        result = save_example.save(
                            INVESTIGATION, "Clear report.")
                        self.assertEqual(result["files"], [REPORT, reference])
                        self.assertEqual((Path(result["example"]) / reference).read_bytes(),
                                         inside.read_bytes())
                    else:
                        with self.assertRaisesRegex(SystemExit, "leads outside"):
                            save_example.save(INVESTIGATION, "Clear report.")
                        self.assertEqual(folders, sorted(str(path.relative_to(archive))
                                                         for path in archive.rglob("*")))
                        self.assertEqual(before, {str(path.relative_to(archive)): path.read_bytes()
                                                  for path in archive.rglob("*") if path.is_file()})
                finally:
                    symlink.unlink()


if __name__ == "__main__":
    unittest.main()
