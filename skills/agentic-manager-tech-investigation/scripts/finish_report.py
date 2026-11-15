"""Finishes the investigation's report: writes it from content.json and the
ledger with make_report.py, then runs its final check with check_report.py.

make_report.py checks content.json field by field before writing anything.
The report of the write task's last submission in this run is deleted first,
so a new text that fails its checks can't leave an older report that passes
and makes the investigation read as finished.
"""
import os

from common import investigation_dir, report_path
import check_report
import make_report


def finish(relative):
    """Write the investigation `relative`'s report from its content.json, then
    check it; returns {path, temporary, warnings}, or exits with the problems
    unless the report passes."""
    folder, _, _ = investigation_dir(relative)
    old = report_path(folder)
    if os.path.isfile(old):
        os.remove(old)
    made = make_report.make_report(relative)
    checked = check_report.check_report(made["path"], handover=True)
    if not checked["ok"]:
        raise SystemExit("the report doesn't pass its final check; fix each of these and submit again:\n- "
                         + "\n- ".join(checked["errors"]))
    return {"path": made["path"], "temporary": made["temporary"],
            "warnings": made["warnings"] + checked["warnings"]}
