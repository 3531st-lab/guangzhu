"""Test configuration.

The public repository does not include the archived runs and reports that the development process produced
(runs/, reports/, reviews/, docs/, eval/results/). A test that fails only because it tried to open a file in
one of those folders is reported as skipped. Every other failure is reported as usual.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = tuple((ROOT / name).resolve() for name in ("reports", "reviews", "docs", "runs", "eval/results"))
REASON = "needs archived runs or reports that the public repository does not include"

# tests that replay archived runs through the API or the browser: they get an empty result or a 404 instead of a
# missing-file error, so they are listed here
NEEDS_ARCHIVE = {
    "tests/test_api.py::test_saved_t10_run_has_backfilled_selected_scene_and_keeps_candidate_missing_explicit",
    "tests/test_enhancements_dom.py::test_codex_e2_e3_each_change_and_each_option_opens_its_own_version",
    "tests/test_t22_dom.py::test_park_view_sums_the_ticked_buildings_and_splits_phases_by_budget",
    "tests/test_t22_dom.py::test_park_ticks_designs_finished_since_the_last_visit_and_keeps_hand_picks",
    "tests/test_t22_dom.py::test_result_page_lists_the_checks_before_construction",
    "tests/test_t22_site_park.py::test_result_page_and_proposal_check_the_answers_against_the_exported_version",
    "tests/test_t22_site_park.py::test_park_api_lists_only_verified_design_exports",
    "tests/test_t29_api_report.py::test_two_real_legacy_roofs_match_normalized_identity",
}


def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.nodeid.split("[", 1)[0] in NEEDS_ARCHIVE:
            item.add_marker(pytest.mark.skip(reason=REASON))


def _missing_archive_file(error):
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        name = getattr(error, "filename", None)
        if isinstance(error, (FileNotFoundError, NotADirectoryError)) and name:
            try:
                path = Path(name).resolve()
            except (OSError, ValueError):
                path = None
            if path is not None and any(path == folder or folder in path.parents for folder in ARCHIVES):
                return True
        error = error.__cause__ or error.__context__
    return False


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.failed and call.excinfo is not None and _missing_archive_file(call.excinfo.value):
        report.outcome = "skipped"
        report.longrepr = (str(item.path), (item.location[1] or 0) + 1, "Skipped: " + REASON)
