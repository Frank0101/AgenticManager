"""Unit tests for skills/agentic-manager-utils-lib/agentic_manager/web.py.
Run with: python3 tests/run.py agentic-manager-utils-lib
"""

import os
import ssl
import sys
import tempfile
import unittest
from unittest import mock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(TEST_DIR))
sys.path.insert(0, os.path.join(
    REPO_ROOT, "skills", "agentic-manager-utils-lib"))
from agentic_manager import web  # noqa: E402


class SslContextTest(unittest.TestCase):
    def test_falls_back_to_a_system_bundle_only_when_python_has_none(self):
        bundle = next(
            (b for b in web.SYSTEM_BUNDLES if os.path.isfile(b)), None)
        if not bundle:
            self.skipTest("no system certificate bundle")
        with tempfile.TemporaryDirectory() as folder:
            missing = os.path.join(folder, "missing.pem")
            cases = [("Python has certificates", 1, (missing, bundle), None),
                     ("it has none", 0, (missing, bundle), bundle),
                     ("neither has any", 0, (missing,), None)]
            for name, loaded, bundles, cafile in cases:
                with self.subTest(name), \
                        mock.patch.object(ssl.SSLContext, "cert_store_stats",
                                          return_value={"x509_ca": loaded}), \
                        mock.patch.object(web.ssl, "create_default_context",
                                          wraps=ssl.create_default_context) as create:
                    context = web.ssl_context(bundles)
                    self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
                    self.assertEqual([c.kwargs.get("cafile") for c in create.call_args_list[1:]],
                                     [cafile] if cafile else [])


if __name__ == "__main__":
    unittest.main()
