"""Report checks use invented evidence and never read the developer's config."""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] /
                       'skills/agentic-manager-tech-investigation/scripts'))
import check_report
from init_investigation import ledger_skeleton

LEDGER = ledger_skeleton('Acme').replace(
    '## Decisions and precise evidence gaps\n\nNone yet.',
    '## Decisions and precise evidence gaps\n\n### G1\n\nEvidence unavailable.')


class CheckReportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.report = self.folder / 'Acme_Report.md'
        (self.folder / 'ledgers.md').write_text(LEDGER)
        prep = []
        parts = ['# Acme\n\nEvidence snapshot: today. [Research ledger](ledgers.md).\n']
        for level, title in check_report.HEADINGS:
            parts.append('#' * level + ' ' + title + '\n\n')
            if title == 'Roadmap':
                parts.append('| Stage | Intended outcome | Commitment and evidence | Dependencies |\n'
                             '| --- | --- | --- | --- |\n')
                for stage in check_report.STAGES:
                    parts.append(f'| {stage} | Search improvements | Proposed [document](https://example.com/plan) | Review |\n')
            elif title in check_report.MAPS:
                filename = check_report.MAPS[title]
                (self.folder / filename).write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
                parts.append(f'Architecture summary with [code](https://example.com/code).\n\n'
                             f'![{title}]({filename})\n\n'
                             '```mermaid\nsequenceDiagram\nautonumber\n'
                             'Client->>Service: Search\n```\n\n'
                             'The service responds to the client; [code](https://example.com/code) establishes this flow.\n\n')
                prep.append(f'## {title}\n\n{filename}\n\n```mermaid\nflowchart LR\nClient --> Service\n```\n')
            elif title == 'Technical decisions and gaps':
                parts.append('| Decision | Options and tradeoffs | Rationale and evidence | Status | Owner |\n'
                             '| --- | --- | --- | --- | --- |\n'
                             '| Storage | Cache or index | [Proposal](https://example.com/proposal) | Open | Not established |\n')
            else:
                parts.append('Account supported by [source](https://example.com/evidence).\n\n')
        self.text = ''.join(parts)
        self.report.write_text(self.text)
        (self.folder / 'mermaids.md').write_text('\n'.join(prep))

    def check(self, text=None):
        if text is not None:
            self.report.write_text(text)
        return check_report.check_report(self.report)

    def test_complete_report_and_no_writes(self):
        before = {p.name: p.read_bytes() for p in self.folder.iterdir()}
        self.assertEqual(self.check(), {'ok': True, 'errors': [], 'warnings': []})
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.folder.iterdir()})

    def test_shortcut_reference_links_cite_a_table_row(self):
        cited = self.text.replace('[Proposal](https://example.com/proposal)', '[Proposal]') + \
            '\n[Proposal]: https://example.com/proposal\n'
        self.assertEqual(self.check(cited)['errors'], [])
        undefined = self.text.replace('[Proposal](https://example.com/proposal)', '[Proposal]')
        self.assertTrue(any('table row needs' in e for e in self.check(undefined)['errors']))

    def test_links_into_the_ledger_must_name_a_heading(self):
        (self.folder / 'ledgers.md').write_text(
            '# Research\n\n## G1\nGap.\n\n### F03 — Delivery is exploration\n\n## Repeat\n\n## Repeat\n')
        cases = [('[F03](ledgers.md#f03--delivery-is-exploration)', True), ('[gap](ledgers.md#g1)', True),
                 ('[second](ledgers.md#repeat-1)', True), ('[gone](ledgers.md#f99--missing)', False)]
        for link, ok in cases:
            with self.subTest(link=link):
                errors = self.check(self.text.replace('[Research ledger](ledgers.md)', link))['errors']
                self.assertEqual(any('has no heading for' in e for e in errors), not ok, errors)

    def test_headings_and_roadmap_order(self):
        cases = [
            ('missing section', self.text.replace('### Key decisions and risks', '#### Key decisions and risks'), 'H2/H3'),
            ('extra section', self.text + '\n## Engineering\n', 'H2/H3'),
            ('roadmap order', self.text.replace('| Current milestone |', '| Next milestones |', 1), 'Roadmap table'),
            ('missing roadmap row', '\n'.join(line for line in self.text.splitlines() if not line.startswith('| Next milestones |')), 'Roadmap table'),
        ]
        for name, text, expected in cases:
            with self.subTest(name=name):
                self.assertIn(expected, ' '.join(self.check(text)['errors']))

    def test_point_of_use_citations_do_not_accept_unknown_owner(self):
        text = self.text.replace('[Proposal](https://example.com/proposal)', 'Lower latency')
        result = self.check(text)
        self.assertFalse(result['ok'])
        self.assertEqual(len(result['errors']), 1)
        self.assertIn('point-of-use source link', result['errors'][0])

    def test_unknown_rows_and_ledger_gap_citations(self):
        old = '| Storage | Cache or index | [Proposal](https://example.com/proposal) | Open | Not established |'
        cases = [
            '| Storage | Not established | Evidence unavailable | Unverified | Not established |',
            '| Storage | Cache or index | [G1](ledgers.md#g1) | Open | Not established |',
        ]
        for row in cases:
            with self.subTest(row=row):
                self.assertTrue(self.check(self.text.replace(old, row))['ok'])

    def test_local_links_and_svg(self):
        cases = [
            ('missing image', '![Map](missing.svg)', 'local link target is missing'),
            ('missing document', '[Details](absent.md#section)', 'local link target is missing'),
            ('unresolved reference', '[Details][absent]', 'unresolved Markdown'),
            ('bad XML', '![Map](broken.svg)', 'not valid SVG XML'),
            ('wrong root', '![Map](other.svg)', 'not valid SVG XML'),
        ]
        (self.folder / 'broken.svg').write_text('<svg>')
        (self.folder / 'other.svg').write_text('<document/>')
        for name, link, expected in cases:
            with self.subTest(name=name):
                result = self.check(self.text + '\n' + link)
                self.assertIn(expected, ' '.join(result['errors']))

    def test_reference_links_encoded_paths_and_fences(self):
        (self.folder / 'extra evidence.md').write_text('Evidence')
        text = self.text.replace('[Proposal](https://example.com/proposal)', '[Proposal][proof]')
        text += ('\n[proof]: https://example.com/proposal\n'
                 '[Local](<extra%20evidence.md>)\n'
                 '```text\n## Fake heading\n[Not a link](missing.md)\n```\n')
        self.assertTrue(self.check(text)['ok'])

    def test_sequence_and_map_order_and_commentary(self):
        image = '![Current architecture](architecture-as-is.svg)'
        sequence = '```mermaid\nsequenceDiagram\nautonumber\nClient->>Service: Search\n```'
        commentary = 'The service responds to the client; [code](https://example.com/code) establishes this flow.'
        cases = [
            ('missing sequence', self.text.replace(sequence, '', 1), 'native Mermaid sequence'),
            ('wrong order', self.text.replace(image + '\n\n' + sequence, sequence + '\n\n' + image, 1), 'map must precede'),
            ('no commentary', self.text.replace(commentary, '', 1), 'shared commentary'),
            ('no map', self.text.replace(image, '', 1), 'embed architecture-as-is.svg'),
            ('duplicate map', self.text.replace(image, image + '\n\n```mermaid\nflowchart LR\nA --> B\n```'), 'duplicated map source'),
            ('appendix map source', self.text + '\n```mermaid\nflowchart LR\nA --> B\n```', 'not elsewhere in the report'),
        ]
        for name, text, expected in cases:
            with self.subTest(name=name):
                self.assertIn(expected, ' '.join(self.check(text)['errors']))

    def test_explicit_evidence_gap_replaces_map_and_flow(self):
        start = self.text.index('Architecture summary')
        end = self.text.index('### Next evolution')
        text = self.text[:start] + 'Map evidence gap: architecture placement is unavailable.\n\nFlow evidence gap: sequence not established. [G1](ledgers.md#g1).\n\n' + self.text[end:]
        self.assertTrue(self.check(text)['ok'])

    def test_documented_fallback(self):
        text = self.text.replace('![Current architecture](architecture-as-is.svg)',
                                 'Node.js unavailable; map layout is unchecked.\n\n```mermaid\nflowchart LR\nClient --> Service\n```')
        result = self.check(text)
        self.assertTrue(result['ok'], result)
        self.assertEqual(len(result['warnings']), 1)

    def test_interleaved_prose_requires_review_but_titles_are_allowed(self):
        image = '![Current architecture](architecture-as-is.svg)'
        for insertion, warning in (('\n\n#### Search flow', False),
                                   ('\n\n<div style="width:62.42%; margin:0 auto;">', False),
                                   ('\n\n<div style="zoom:2">', True),
                                   ('\n\nThis paragraph explains the structure.', True)):
            with self.subTest(insertion=insertion):
                result = self.check(self.text.replace(image, image + insertion, 1))
                self.assertTrue(result['ok'], result)
                self.assertEqual(bool(result['warnings']), warning)

    def test_preparation_sources(self):
        prep = self.folder / 'mermaids.md'
        original = prep.read_text()
        cases = [
            (original.replace('architecture-next.svg', 'other.svg'), 'architecture-next.svg map source'),
            (original + '\n```mermaid\nsequenceDiagram\nA->>B: Search\n```\n', 'map sources only'),
            (original + '\n```mermaid\nflowchart LR\n', 'unclosed code fence'),
        ]
        for text, expected in cases:
            with self.subTest(expected=expected):
                prep.write_text(text)
                self.assertIn(expected, ' '.join(self.check()['errors']))

    def test_skipped_sections_follow_content_json(self):
        content = self.folder / 'content.json'
        content.write_text('{"skip": ["evolution"]}')
        self.assertIn('H2/H3 headings', ' '.join(self.check()['errors']))
        text = self.text
        for title in ('Roadmap', 'Next evolution', 'Target architecture'):
            start = text.index('### ' + title + '\n')
            end = text.index('\n### ', start + 4) + 1
            text = text[:start] + text[end:]
        self.assertTrue(self.check(text)['ok'], self.check(text))
        content.unlink()
        self.assertIn('H2/H3 headings', ' '.join(self.check(text)['errors']))

    def test_ledger_structure(self):
        ledger = self.folder / 'ledgers.md'
        finding = ('### F01 — Search is merged\n\n' +
                   '\n'.join(f'**{field}:** text.' for field in check_report.FINDING_FIELDS))
        complete = LEDGER.replace('## Findings and validation chains\n\nNone yet.',
                                  '## Findings and validation chains\n\n' + finding)
        cases = [
            ('complete', complete, None, None),
            ('section order', complete.replace('## Resume here', '## Summary'), 'sections must be exactly', None),
            ('queue subsections', complete.replace('### Blocked', '### Waiting'), 'queue needs exactly', None),
            ('duplicate finding', complete + '\n' + finding, 'duplicate findings: F01', None),
            ('undefined finding', complete.replace('None yet.', 'See F07.', 1), 'never written: F07', None),
            ('missing fields', complete.replace('**Kind:** text.', ''), None, 'F01 lacks Kind'),
        ]
        for name, text, error, warning in cases:
            with self.subTest(name=name):
                ledger.write_text(text)
                result = self.check()
                self.assertEqual(any(error in e for e in result['errors']) if error else result['errors'] == [],
                                 True, result)
                if warning:
                    self.assertIn(warning, ' '.join(result['warnings']))

    def test_handover_needs_empty_ready_queue_and_reflection(self):
        ledger = self.folder / 'ledgers.md'
        ready = LEDGER.replace('### Ready / in progress\n\n', '### Ready / in progress\n\n'
                               '| Q01 | Start | Read code | Code | — | High | In progress | — |\n\n', 1)
        reflected = LEDGER.replace('## Correction history\n\nNone yet.',
                                   '## Correction history\n\n### Reflection\n\nConverged.')
        cases = [(LEDGER, False, 'Reflection'), (reflected, True, None),
                 (ready.replace('## Correction history\n\nNone yet.',
                                '## Correction history\n\n### Reflection\n\nConverged.'), False, 'still ready')]
        for text, ok, expected in cases:
            with self.subTest(expected=expected):
                ledger.write_text(text)
                self.assertTrue(check_report.check_report(self.report)['ok'])
                result = check_report.check_report(self.report, handover=True)
                self.assertEqual(result['ok'], ok, result)
                if expected:
                    self.assertIn(expected, ' '.join(result['errors']))

    def test_unreadable_missing_and_relative_report(self):
        for path in ('relative.md', self.folder / 'missing.md'):
            with self.subTest(path=str(path)):
                self.assertFalse(check_report.check_report(path)['ok'])
        self.report.write_bytes(b'\xff')
        self.assertIn('UTF-8', ' '.join(self.check()['errors']))

    def test_cli_json_and_exit_status(self):
        for path, status in ((self.report, 0), (self.folder / 'missing.md', 1)):
            with self.subTest(status=status), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(check_report.main(['--report', str(path)]), status)
                self.assertEqual(json.loads(output.getvalue())['ok'], status == 0)


if __name__ == '__main__':
    unittest.main()
