# Unit tests for skills/agentic-manager-tech-investigation/scripts/save_example.py.
# The whole pipeline has end-to-end tests in test_e2e_pipeline.py.
# Run with: python3 tests/run.py agentic-manager-tech-investigation
#
# The config's path is patched to the test's own config, in a temporary folder.
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


class SaveExampleTest(unittest.TestCase):
    def setUp(self):
        self.folder = temp_output(self)
        init_investigation.init("Acme-Search", today=TODAY)
        self.source = os.path.join(self.folder, "Acme-Search_26-10-05")
        files = {"Acme-Search_Report.md": "![Map](architecture-as-is.svg)\n[Ledger](ledgers.md#f01)\n"
                                          "[Web](https://example.com) [Missing](gone.md)\n",
                 "architecture-as-is.svg": "<svg/>", "mermaids.md": "unlinked",
                 "exec-summary.md": "Summary. [Full report](Acme-Search_Report.md)\n"}
        for name, text in files.items():
            with open(os.path.join(self.source, name), "w", encoding="utf-8") as f:
                f.write(text)

    def test_copies_linked_files_and_indexes_newest_first(self):
        first = save_example.save(
            "Acme-Search_26-10-05", "Acme-Search_Report.md", "long-analysis", "Clear roadmap.")
        self.assertEqual(sorted(first["files"]), [
                         "Acme-Search_Report.md", "architecture-as-is.svg", "ledgers.md"])
        second = save_example.save(
            "Acme-Search_26-10-05", "exec-summary.md", "exec-summary", "Tight summary.")
        self.assertEqual(sorted(second["files"]), ["Acme-Search_Report.md", "architecture-as-is.svg",
                                                   "exec-summary.md", "ledgers.md"])
        third = save_example.save(
            "Acme-Search_26-10-05", "exec-summary.md", "exec-summary", "Revised.")
        self.assertTrue(third["example"].endswith(
            "Acme-Search_26-10-05--exec-summary--2"))
        with open(os.path.join(self.folder, "_examples", "README.md"), encoding="utf-8") as f:
            index = f.read().split("## Index\n", 1)[1]
        self.assertEqual(index.strip().splitlines(), [
            "- [Acme-Search_26-10-05--exec-summary--2/exec-summary.md]"
            "(Acme-Search_26-10-05--exec-summary--2/exec-summary.md) — Revised.",
            "- [Acme-Search_26-10-05--exec-summary/exec-summary.md]"
            "(Acme-Search_26-10-05--exec-summary/exec-summary.md) — Tight summary.",
            "- [Acme-Search_26-10-05--long-analysis/Acme-Search_Report.md]"
            "(Acme-Search_26-10-05--long-analysis/Acme-Search_Report.md) — Clear roadmap.",
        ])

    def test_reference_links_and_fenced_examples(self):
        # Preserve all Markdown link forms and recursively linked documents,
        # while ignoring illustrative links inside code fences.
        forms = ["[Asset](asset.svg)", "[Asset][proof]",
                 "[proof][]", "[proof]"]
        for form in forms:
            with self.subTest(form=form):
                files = {"approved.md": "[Details](details.md)\n```text\n[Ignored](ignored.svg)\n```",
                         "details.md": form + "\n\n[proof]: asset.svg\n",
                         "asset.svg": "<svg/>", "ignored.svg": "<svg/>"}
                for name, text in files.items():
                    with open(os.path.join(self.source, name), "w", encoding="utf-8") as f:
                        f.write(text)
                result = save_example.save("Acme-Search_26-10-05", "approved.md",
                                           "exec-summary", "Clear summary.")
                self.assertEqual(sorted(result["files"]),
                                 ["approved.md", "asset.svg", "details.md"])
                with open(os.path.join(result["example"], "details.md"), encoding="utf-8") as f:
                    self.assertEqual(f.read(), files["details.md"])

    def test_refusals(self):
        cases = [("missing.md", "exec-summary", "Note."), ("exec-summary.md", "Exec Summary", "Note."),
                 ("exec-summary.md", "exec-summary", " "), ("exec-summary.md", "exec-summary", "a\nb")]
        for document, wanted, note in cases:
            with self.subTest(document=document, wanted=wanted, note=note):
                with self.assertRaises(SystemExit):
                    save_example.save("Acme-Search_26-10-05",
                                      document, wanted, note)

    def test_document_must_be_relative_and_inside_investigation(self):
        source = Path(self.source)
        outside = source.parent / "outside.md"
        outside.write_text("Invented external document.", encoding="utf-8")
        archive = source.parent / "_examples"
        before = {str(path.relative_to(archive)): path.read_bytes()
                  for path in archive.rglob("*") if path.is_file()}
        for document in (str(outside), "../outside.md"):
            with self.subTest(document=document):
                with self.assertRaisesRegex(SystemExit, "relative path inside"):
                    save_example.save("Acme-Search_26-10-05", document,
                                      "exec-summary", "Clear summary.")
                self.assertEqual(
                    sorted(path.name for path in archive.iterdir()), ["README.md"])
                self.assertEqual(before, {str(path.relative_to(archive)): path.read_bytes()
                                          for path in archive.rglob("*") if path.is_file()})
        nested = source / "summaries" / "approved.md"
        nested.parent.mkdir()
        nested.write_text("Approved nested summary.", encoding="utf-8")
        result = save_example.save("Acme-Search_26-10-05", "summaries/approved.md",
                                   "exec-summary", "Clear summary.")
        self.assertEqual(result["files"], ["summaries/approved.md"])
        self.assertEqual((Path(result["example"]) / "summaries" / "approved.md").read_bytes(),
                         nested.read_bytes())

    def test_linked_symlinks_must_stay_inside_investigation(self):
        source = Path(self.source)
        outside = source.parent / "external"
        outside.mkdir()
        (outside / "details.md").write_text("Invented external document.", encoding="utf-8")
        (outside / "asset.svg").write_text("<svg/>", encoding="utf-8")
        inside = source / "details.md"
        inside.write_text("Invented investigation document.", encoding="utf-8")
        archive = source.parent / "_examples"
        cases = [("document", outside / "details.md", "linked.md", "linked.md", False),
                 ("file", outside / "asset.svg", "linked.svg", "linked.svg", False),
                 ("directory", outside, "linked-dir",
                  "linked-dir/details.md", False),
                 ("inside", inside, "linked.md", "linked.md", True)]
        for name, destination, link_name, reference, valid in cases:
            with self.subTest(name=name):
                symlink = source / link_name
                symlink.symlink_to(
                    destination, target_is_directory=destination.is_dir())
                approved = source / "approved.md"
                approved.write_text(
                    f"[Details]({reference})", encoding="utf-8")
                before = {str(path.relative_to(archive)): path.read_bytes()
                          for path in archive.rglob("*") if path.is_file()}
                folders = sorted(str(path.relative_to(archive))
                                 for path in archive.rglob("*"))
                try:
                    if valid:
                        result = save_example.save("Acme-Search_26-10-05", "approved.md",
                                                   "exec-summary", "Clear summary.")
                        self.assertEqual(result["files"], [
                                         "approved.md", reference])
                        self.assertEqual((Path(result["example"]) / reference).read_bytes(),
                                         inside.read_bytes())
                    else:
                        with self.assertRaisesRegex(SystemExit, "leads outside"):
                            save_example.save("Acme-Search_26-10-05", "approved.md",
                                              "exec-summary", "Clear summary.")
                        self.assertEqual(folders, sorted(str(path.relative_to(archive))
                                                         for path in archive.rglob("*")))
                        self.assertEqual(before, {str(path.relative_to(archive)): path.read_bytes()
                                                  for path in archive.rglob("*") if path.is_file()})
                finally:
                    symlink.unlink()


if __name__ == "__main__":
    unittest.main()
