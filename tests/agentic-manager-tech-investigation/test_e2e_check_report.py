"""The validator CLI reports input failures as JSON and does not need config."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CheckReportCommandTest(unittest.TestCase):
    def test_missing_report_returns_json_without_config(self):
        script = Path(__file__).resolve().parents[2] / 'skills/agentic-manager-tech-investigation/scripts/check_report.py'
        with tempfile.TemporaryDirectory() as folder:
            process = subprocess.run(
                [sys.executable, str(script), '--report', str(Path(folder) / 'missing.md')],
                env={**os.environ, 'HOME': folder, 'TMPDIR': folder},
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(process.returncode, 1)
            result = json.loads(process.stdout)
            self.assertFalse(result['ok'])
            self.assertIn('Cannot read report', result['errors'][0])
            self.assertEqual(process.stderr, '')
            self.assertFalse((Path(folder) / 'missing.md').exists())
            self.assertFalse((Path(folder) / '.config').exists())


if __name__ == '__main__':
    unittest.main()
