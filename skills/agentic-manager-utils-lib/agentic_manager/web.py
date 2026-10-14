"""Helpers for reaching the internet over https, shared by every skill.

Python installed from python.org on macOS ships without the certificates that
https needs until its "Install Certificates" step is run, so every download
fails there with CERTIFICATE_VERIFY_FAILED. The system has its own bundle, so
when Python's default has none, the context falls back to the first system
bundle that exists, rather than asking the user to fix their Python. It never
turns verification off.
"""
import os
import ssl

# The system's certificate bundles: macOS and the BSDs, then Debian and
# Ubuntu, then Fedora and RHEL.
SYSTEM_BUNDLES = ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt",
                  "/etc/pki/tls/certs/ca-bundle.crt")


def ssl_context(bundles=SYSTEM_BUNDLES):
    """An SSL context that verifies certificates: Python's default, or one
    from the first of `bundles` that exists when the default holds none."""
    context = ssl.create_default_context()
    if context.cert_store_stats()["x509_ca"]:
        return context
    for bundle in bundles:
        if os.path.isfile(bundle):
            return ssl.create_default_context(cafile=bundle)
    return context
