"""Fail the integrated G3 proof if any selected test is skipped."""

import pytest


SKIPPED = []


def pytest_runtest_logreport(report):
    if report.skipped:
        SKIPPED.append(f"{report.nodeid} ({report.when})")


def pytest_sessionfinish(session, exitstatus):
    if SKIPPED:
        terminal = session.config.pluginmanager.get_plugin("terminalreporter")
        if terminal is not None:
            terminal.write_line("G3 required-test skip detected: " + ", ".join(SKIPPED))
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
