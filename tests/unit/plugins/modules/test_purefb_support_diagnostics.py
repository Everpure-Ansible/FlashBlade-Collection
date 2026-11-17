# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_support_diagnostics module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import contextlib
import sys
import multiprocessing
import ctypes
from unittest.mock import Mock, patch, MagicMock

# Mock multiprocessing context for Windows
if sys.platform == "win32":
    original_get_context = multiprocessing.get_context

    def mock_get_context(method=None):
        if method == "fork":
            return original_get_context("spawn")
        return original_get_context(method)

    multiprocessing.get_context = mock_get_context

    # Mock ctypes LoadLibrary to prevent Windows errors
    original_load_library = ctypes.cdll.LoadLibrary

    def mock_load_library(name):
        if name is None or not isinstance(name, str):
            return MagicMock()
        try:
            return original_load_library(name)
        except (OSError, TypeError):
            return MagicMock()

    ctypes.cdll.LoadLibrary = mock_load_library

# Mock external dependencies before importing module
sys.modules["pypureclient"] = MagicMock()
sys.modules["pypureclient.flashblade"] = MagicMock()
sys.modules["urllib3"] = MagicMock()
sys.modules["distro"] = MagicMock()
# Mock Unix-specific modules for Windows compatibility
sys.modules["grp"] = MagicMock()
sys.modules["fcntl"] = MagicMock()
sys.modules["pwd"] = MagicMock()
sys.modules["syslog"] = MagicMock()
# Mock termios with required constants
mock_termios = MagicMock()
mock_termios.TCSAFLUSH = 2
sys.modules["termios"] = mock_termios
sys.modules["tty"] = MagicMock()

# Mock ansible_collections module structure
sys.modules["ansible_collections"] = MagicMock()
sys.modules["ansible_collections.everpure"] = MagicMock()
sys.modules["ansible_collections.everpure.flashblade"] = MagicMock()
sys.modules["ansible_collections.everpure.flashblade.plugins"] = MagicMock()
sys.modules["ansible_collections.everpure.flashblade.plugins.module_utils"] = (
    MagicMock()
)
sys.modules["ansible_collections.everpure.flashblade.plugins.module_utils.purefb"] = (
    MagicMock()
)
sys.modules["ansible_collections.everpure.flashblade.plugins.module_utils.common"] = (
    MagicMock()
)
sys.modules["ansible_collections.everpure.flashblade.plugins.module_utils.version"] = (
    MagicMock()
)

from plugins.module_utils.version import LooseVersion as RealLooseVersion
from plugins.modules.purefb_support_diagnostics import (
    main,
    _analysis_window,
    _get_details,
    _latest_run,
    _resolve_timezone,
    _select_run,
    _severity_counts,
    _task_dict,
    _to_epoch_seconds,
    _wait_for_run,
)

MOD = "plugins.modules.purefb_support_diagnostics"
# 2026-01-01 00:00:00 UTC and one hour later, in epoch seconds
JAN_1_2026 = 1767225600
JAN_1_2026_PLUS_1H = JAN_1_2026 + 3600


def _base_params(**overrides):
    params = {
        "state": "run",
        "start_time": None,
        "end_time": None,
        "timezone": None,
        "wait": True,
        "timeout": 900,
        "severity": None,
        "task": None,
    }
    params.update(overrides)
    return params


def _module(params=None, check_mode=False):
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.warn = Mock()
    module.params = params if params is not None else _base_params()
    module.check_mode = check_mode
    return module


def _severity(name, count):
    entry = Mock(spec=["severity", "count"])
    entry.severity = name
    entry.count = count
    return entry


def _run(index=3, task_id="task-3", status="completed", start_time=1700000000):
    run = Mock(
        spec=[
            "id",
            "name",
            "index",
            "task_id",
            "status",
            "version",
            "start_time",
            "analysis_period",
            "severity_count",
        ]
    )
    run.id = "id-{0}".format(index)
    run.name = None
    run.index = index
    run.task_id = task_id
    run.status = status
    run.version = "default"
    run.start_time = start_time
    period = Mock(spec=["start_time", "end_time"])
    period.start_time = start_time - 3600
    period.end_time = start_time
    run.analysis_period = period
    run.severity_count = [_severity("info", 10), _severity("warning", 2)]
    return run


def _detail(index, test_name, severity, test_type="SYSTEM HEALTH"):
    item = Mock(
        spec=[
            "index",
            "task_id",
            "test_name",
            "test_type",
            "severity",
            "result_details",
        ]
    )
    item.index = index
    item.task_id = "task-3"
    item.test_name = test_name
    item.test_type = test_type
    item.severity = severity
    item.result_details = "details of {0}".format(test_name)
    return item


def _settings(version="default", last_updated=None):
    item = Mock(spec=["version", "last_updated"])
    item.version = version
    item.last_updated = last_updated
    return item


def _response(items=None, status_code=200, message=None):
    response = Mock()
    response.status_code = status_code
    response.items = items if items is not None else []
    if message is not None:
        error = Mock()
        error.message = message
        response.errors = [error]
    else:
        response.errors = []
    return response


def _blade(runs=None, details=None, settings=None, post=None):
    blade = Mock()
    blade.get_support_diagnostics.return_value = _response(runs)
    blade.get_support_diagnostics_details.return_value = _response(
        details if details is not None else [_detail(3.1, "Watchers check", "info")]
    )
    blade.get_support_diagnostics_settings.return_value = _response(
        settings if settings is not None else [_settings()]
    )
    blade.post_support_diagnostics.return_value = (
        post if post is not None else _response([_run(status="queued")])
    )
    return blade


def _probe_once(module, probe, is_done, timeout, description, **kwargs):
    """Stand-in for wait_for: one probe, no sleeping."""
    return probe()


def _error_message(response, default="Unknown error"):
    if getattr(response, "errors", None):
        return response.errors[0].message
    return default


@contextlib.contextmanager
def _env(module, blade, api_version="2.30", wait=None):
    """Patch main()'s collaborators; yields the wait_for mock."""
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch(MOD + ".AnsibleModule", return_value=module))
        stack.enter_context(patch(MOD + ".get_system", return_value=blade))
        stack.enter_context(
            patch(MOD + ".get_rest_api_version", return_value=api_version)
        )
        stack.enter_context(patch(MOD + ".LooseVersion", RealLooseVersion))
        stack.enter_context(
            patch(MOD + ".get_error_message", side_effect=_error_message)
        )
        stack.enter_context(patch(MOD + ".get_local_tz", return_value="UTC"))
        mock_wait = stack.enter_context(
            patch(MOD + ".wait_for", side_effect=wait or _probe_once)
        )
        yield mock_wait


def _call_main():
    try:
        main()
    except SystemExit:
        pass


class TestHelpers:
    """Helper-function unit tests"""

    def test_severity_counts_defaults_missing_severities_to_zero(self):
        run = _run()
        assert _severity_counts(run) == {"info": 10, "warning": 2, "critical": 0}

    def test_severity_counts_tolerates_missing_list(self):
        run = Mock(spec=["index"])
        assert _severity_counts(run) == {"info": 0, "warning": 0, "critical": 0}

    def test_task_dict_none(self):
        assert _task_dict(None) is None

    def test_task_dict_reports_every_field(self):
        result = _task_dict(_run(index=7, task_id="task-7", start_time=1700003600))
        assert result == {
            "index": 7,
            "task_id": "task-7",
            "status": "completed",
            "version": "default",
            "start_time": 1700003600,
            "analysis_period": {"start_time": 1700000000, "end_time": 1700003600},
            "severity_count": {"info": 10, "warning": 2, "critical": 0},
        }

    def test_task_dict_without_analysis_period(self):
        run = Mock(spec=["index", "task_id", "status"])
        run.index = 1
        run.task_id = "t"
        run.status = "queued"
        result = _task_dict(run)
        assert result["analysis_period"] == {"start_time": None, "end_time": None}
        assert result["version"] is None

    def test_to_epoch_seconds_utc(self):
        module = _module(_base_params(start_time="2026-01-01 00:00:00"))
        assert _to_epoch_seconds(module, "start_time", "UTC") == JAN_1_2026

    def test_to_epoch_seconds_applies_timezone(self):
        module = _module(_base_params(start_time="2026-01-01 00:00:00"))
        # Midnight in Los Angeles is 08:00 UTC in winter
        assert (
            _to_epoch_seconds(module, "start_time", "America/Los_Angeles")
            == JAN_1_2026 + 8 * 3600
        )

    def test_to_epoch_seconds_rejects_bad_format(self):
        module = _module(_base_params(end_time="01/01/2026 10:00"))
        with contextlib.suppress(SystemExit):
            _to_epoch_seconds(module, "end_time", "UTC")
        module.fail_json.assert_called_once()
        assert "not a valid date/time" in module.fail_json.call_args[1]["msg"]

    def test_resolve_timezone_uses_parameter(self):
        module = _module(_base_params(timezone="Europe/London"))
        assert _resolve_timezone(module) == "Europe/London"

    @patch(MOD + ".get_local_tz", return_value="Asia/Tokyo")
    def test_resolve_timezone_defaults_to_local(self, mock_local_tz):
        module = _module(_base_params())
        assert _resolve_timezone(module) == "Asia/Tokyo"
        mock_local_tz.assert_called_once_with(module)

    def test_resolve_timezone_rejects_unknown(self):
        module = _module(_base_params(timezone="Mars/Olympus"))
        with contextlib.suppress(SystemExit):
            _resolve_timezone(module)
        module.fail_json.assert_called_once()
        assert "Mars/Olympus" in module.fail_json.call_args[1]["msg"]

    @patch(MOD + ".HAS_PYTZ", False)
    def test_resolve_timezone_requires_pytz(self):
        module = _module(_base_params(timezone="UTC"))
        with contextlib.suppress(SystemExit):
            _resolve_timezone(module)
        module.fail_json.assert_called_once()
        assert "pytz" in module.fail_json.call_args[1]["msg"]

    @patch(MOD + ".time.time", return_value=1800000000.7)
    def test_analysis_window_defaults_to_last_hour(self, mock_time):
        module = _module(_base_params())
        assert _analysis_window(module) == {
            "analysis_period_start_time": 1800000000 - 3600,
            "analysis_period_end_time": 1800000000,
        }

    def test_analysis_window_explicit_times_in_seconds(self):
        module = _module(
            _base_params(
                start_time="2026-01-01 00:00:00",
                end_time="2026-01-01 01:00:00",
                timezone="UTC",
            )
        )
        assert _analysis_window(module) == {
            "analysis_period_start_time": JAN_1_2026,
            "analysis_period_end_time": JAN_1_2026_PLUS_1H,
        }

    @patch(MOD + ".time.time", return_value=1800000000.0)
    def test_analysis_window_start_only_ends_now(self, mock_time):
        module = _module(_base_params(start_time="2026-01-01 00:00:00", timezone="UTC"))
        assert _analysis_window(module) == {
            "analysis_period_start_time": JAN_1_2026,
            "analysis_period_end_time": 1800000000,
        }

    def test_analysis_window_end_only_starts_an_hour_earlier(self):
        module = _module(_base_params(end_time="2026-01-01 01:00:00", timezone="UTC"))
        assert _analysis_window(module) == {
            "analysis_period_start_time": JAN_1_2026,
            "analysis_period_end_time": JAN_1_2026_PLUS_1H,
        }

    def test_analysis_window_rejects_inverted_window(self):
        module = _module(
            _base_params(
                start_time="2026-01-01 02:00:00",
                end_time="2026-01-01 01:00:00",
                timezone="UTC",
            )
        )
        with contextlib.suppress(SystemExit):
            _analysis_window(module)
        module.fail_json.assert_called_once()
        assert "earlier than end_time" in module.fail_json.call_args[1]["msg"]

    def test_latest_run_prefers_newest_start_time(self):
        older = _run(index=9, task_id="t9", start_time=1700000000)
        newer = _run(index=2, task_id="t2", start_time=1700009000)
        assert _latest_run([older, newer]) is newer
        assert _latest_run([]) is None

    def test_select_run_by_index(self):
        module = _module(_base_params(state="report", task=9))
        wanted = _run(index=9, task_id="t9")
        assert _select_run(module, [_run(index=3), wanted]) is wanted

    def test_select_run_unknown_index_fails(self):
        module = _module(_base_params(state="report", task=42))
        with contextlib.suppress(SystemExit):
            _select_run(module, [_run(index=3)])
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "42" in msg
        assert "last 10 runs" in msg

    @patch(MOD + ".get_error_message", side_effect=_error_message)
    def test_get_details_filters_by_task_and_severity(self, mock_error):
        module = _module(_base_params(severity=["warning", "critical"]))
        blade = _blade(
            details=[
                _detail(3.1, "Watchers check", "info"),
                _detail(3.2, "ARP check", "warning"),
                _detail(3.3, "Monitor check", "critical"),
            ]
        )
        details = _get_details(module, blade, _run())
        blade.get_support_diagnostics_details.assert_called_once_with(
            filter="task_id='task-3'"
        )
        assert [d["test_name"] for d in details] == ["ARP check", "Monitor check"]
        assert details[0] == {
            "index": 3.2,
            "test_type": "SYSTEM HEALTH",
            "test_name": "ARP check",
            "severity": "warning",
            "result_details": "details of ARP check",
        }

    @patch(MOD + ".wait_for")
    def test_wait_for_run_callbacks(self, mock_wait):
        module = _module(_base_params(timeout=120))
        running = _run(status="running")
        completed = _run(status="completed")
        failed = _run(status="failed")
        blade = _blade(runs=[_run(index=1, task_id="other"), completed])

        _wait_for_run(module, blade, running)

        mock_wait.assert_called_once()
        args, kwargs = mock_wait.call_args
        probe, is_done = args[1], args[2]
        assert args[0] is module
        assert args[3] == 120
        assert "diagnostics run 3" in args[4]
        assert kwargs["skip_in_check_mode"] is False
        assert probe() is completed
        assert is_done(completed) is True
        assert is_done(running) is False
        assert is_done(None) is False
        assert "failed" in kwargs["is_failed"](failed)
        assert kwargs["is_failed"](running) is None
        assert kwargs["is_failed"](None) is None
        assert "no longer listed" in kwargs["detail"](None)
        assert kwargs["detail"](running) == "status running"


class TestMain:
    """main() flows"""

    def test_run_waits_and_reports_details(self):
        module = _module()
        blade = _blade(
            runs=[_run(status="completed")],
            post=_response([_run(status="queued")]),
        )
        with _env(module, blade) as mock_wait:
            _call_main()
        blade.post_support_diagnostics.assert_called_once()
        mock_wait.assert_called_once()
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["task"]["status"] == "completed"
        assert result["task"]["task_id"] == "task-3"
        assert result["details"][0]["test_name"] == "Watchers check"
        assert result["tools"] == {"version": "default", "last_updated": None}

    def test_run_posts_window_in_epoch_seconds(self):
        module = _module(
            _base_params(
                start_time="2026-01-01 00:00:00",
                end_time="2026-01-01 01:00:00",
                timezone="UTC",
            )
        )
        blade = _blade(runs=[_run(status="completed")])
        with _env(module, blade):
            _call_main()
        blade.post_support_diagnostics.assert_called_once_with(
            analysis_period_start_time=JAN_1_2026,
            analysis_period_end_time=JAN_1_2026_PLUS_1H,
        )

    def test_run_without_wait_returns_queued_run_without_details(self):
        module = _module(_base_params(wait=False))
        blade = _blade(post=_response([_run(status="queued")]))
        with _env(module, blade) as mock_wait:
            _call_main()
        mock_wait.assert_not_called()
        blade.get_support_diagnostics_details.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["task"]["status"] == "queued"
        assert result["details"] == []

    def test_run_check_mode_starts_nothing(self):
        module = _module(check_mode=True)
        latest = _run(index=5, task_id="task-5", start_time=1700009000)
        blade = _blade(runs=[_run(index=4, task_id="task-4"), latest])
        with _env(module, blade) as mock_wait:
            _call_main()
        blade.post_support_diagnostics.assert_not_called()
        mock_wait.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["task"]["index"] == 5

    def test_run_is_not_idempotent(self):
        """A second state=run starts a second run and reports a change again."""
        blade = _blade(runs=[_run(status="completed")])
        for _attempt in range(2):
            module = _module()
            with _env(module, blade):
                _call_main()
            assert module.exit_json.call_args[1]["changed"] is True
        assert blade.post_support_diagnostics.call_count == 2

    def test_run_falls_back_to_run_in_progress(self):
        module = _module()
        in_progress = _run(index=6, task_id="task-6", status="running")
        blade = _blade(
            runs=[_run(index=5, task_id="task-5"), in_progress],
            post=_response(
                status_code=400,
                message="Internal error: Another instance is already running",
            ),
        )
        # the poll sees the in-progress run completing
        completed = _run(index=6, task_id="task-6", status="completed")

        def wait(module_, probe, is_done, timeout, description, **kwargs):
            blade.get_support_diagnostics.return_value = _response([completed])
            return probe()

        with _env(module, blade, wait=wait) as mock_wait:
            _call_main()
        mock_wait.assert_called_once()
        module.warn.assert_called_once()
        assert "already in progress" in module.warn.call_args[0][0]
        assert "already running" in module.warn.call_args[0][0]
        result = module.exit_json.call_args[1]
        assert result["changed"] is False
        assert result["task"]["index"] == 6
        assert result["task"]["status"] == "completed"

    def test_run_fails_on_unrelated_error_while_run_in_progress(self):
        """An unrelated POST error is not mistaken for the already-running refusal."""
        module = _module()
        blade = _blade(
            runs=[_run(index=6, task_id="task-6", status="running")],
            post=_response(status_code=400, message="Internal error: Invalid input"),
        )
        with _env(module, blade) as mock_wait:
            _call_main()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to start support diagnostics" in msg
        assert "Invalid input" in msg
        module.warn.assert_not_called()
        mock_wait.assert_not_called()

    def test_run_fails_on_api_error_when_nothing_in_progress(self):
        module = _module()
        blade = _blade(
            runs=[_run(status="completed")],
            post=_response(status_code=400, message="Internal error: Invalid input"),
        )
        with _env(module, blade):
            _call_main()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to start support diagnostics" in msg
        assert "Invalid input" in msg

    def test_run_fails_when_post_returns_no_run(self):
        module = _module()
        blade = _blade(post=_response([]))
        with _env(module, blade):
            _call_main()
        module.fail_json.assert_called_once()
        assert "returned no run" in module.fail_json.call_args[1]["msg"]

    def test_run_fails_when_listing_runs_fails(self):
        module = _module()
        blade = _blade()
        blade.get_support_diagnostics.return_value = _response(
            status_code=500, message="boom"
        )
        with _env(module, blade):
            _call_main()
        module.fail_json.assert_called_once()
        assert "Failed to list support diagnostics runs" in (
            module.fail_json.call_args[1]["msg"]
        )

    def test_run_fails_when_details_fail(self):
        module = _module()
        blade = _blade(runs=[_run(status="completed")])
        blade.get_support_diagnostics_details.return_value = _response(
            status_code=400, message="bad filter"
        )
        with _env(module, blade):
            _call_main()
        module.fail_json.assert_called_once()
        assert "Failed to read support diagnostics details" in (
            module.fail_json.call_args[1]["msg"]
        )

    def test_run_fails_when_settings_fail(self):
        module = _module()
        blade = _blade(runs=[_run(status="completed")])
        blade.get_support_diagnostics_settings.return_value = _response(
            status_code=400, message="nope"
        )
        with _env(module, blade):
            _call_main()
        module.fail_json.assert_called_once()
        assert "Failed to read support diagnostics settings" in (
            module.fail_json.call_args[1]["msg"]
        )

    def test_severity_filter_applied_to_result(self):
        module = _module(_base_params(severity=["critical"]))
        blade = _blade(
            runs=[_run(status="completed")],
            details=[
                _detail(3.1, "Watchers check", "info"),
                _detail(3.2, "Monitor check", "critical"),
            ],
        )
        with _env(module, blade):
            _call_main()
        details = module.exit_json.call_args[1]["details"]
        assert [d["test_name"] for d in details] == ["Monitor check"]

    def test_report_reports_latest_run(self):
        module = _module(_base_params(state="report"))
        latest = _run(index=3, task_id="task-3", start_time=1700009000)
        blade = _blade(runs=[_run(index=2, task_id="task-2"), latest])
        with _env(module, blade) as mock_wait:
            _call_main()
        blade.post_support_diagnostics.assert_not_called()
        mock_wait.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is False
        assert result["task"]["index"] == 3
        assert result["details"][0]["test_name"] == "Watchers check"
        assert result["tools"]["version"] == "default"

    def test_report_selects_run_by_index(self):
        module = _module(_base_params(state="report", task=2))
        blade = _blade(
            runs=[
                _run(index=2, task_id="task-2", start_time=1700000000),
                _run(index=3, task_id="task-3", start_time=1700009000),
            ]
        )
        with _env(module, blade):
            _call_main()
        assert module.exit_json.call_args[1]["task"]["task_id"] == "task-2"
        blade.get_support_diagnostics_details.assert_called_once_with(
            filter="task_id='task-2'"
        )

    def test_report_with_no_runs(self):
        module = _module(_base_params(state="report"))
        blade = _blade(runs=[])
        with _env(module, blade):
            _call_main()
        blade.get_support_diagnostics_details.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is False
        assert result["task"] is None
        assert result["details"] == []

    def test_report_waits_for_run_in_progress(self):
        module = _module(_base_params(state="report"))
        queued = _run(status="queued")
        blade = _blade(runs=[queued])
        completed = _run(status="completed")

        def wait(module_, probe, is_done, timeout, description, **kwargs):
            blade.get_support_diagnostics.return_value = _response([completed])
            return probe()

        with _env(module, blade, wait=wait) as mock_wait:
            _call_main()
        mock_wait.assert_called_once()
        result = module.exit_json.call_args[1]
        assert result["changed"] is False
        assert result["task"]["status"] == "completed"
        assert len(result["details"]) == 1

    def test_report_without_wait_reports_run_in_progress(self):
        module = _module(_base_params(state="report", wait=False))
        blade = _blade(runs=[_run(status="running")])
        with _env(module, blade) as mock_wait:
            _call_main()
        mock_wait.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["task"]["status"] == "running"
        assert result["details"] == []

    def test_report_is_idempotent(self):
        blade = _blade(runs=[_run(status="completed")])
        for _attempt in range(2):
            module = _module(_base_params(state="report"))
            with _env(module, blade):
                _call_main()
            assert module.exit_json.call_args[1]["changed"] is False
        blade.post_support_diagnostics.assert_not_called()

    def test_tools_omitted_before_rest_2_24(self):
        module = _module(_base_params(state="report"))
        blade = _blade(runs=[_run(status="completed")])
        with _env(module, blade, api_version="2.17"):
            _call_main()
        blade.get_support_diagnostics_settings.assert_not_called()
        assert module.exit_json.call_args[1]["tools"] is None

    def test_fails_before_rest_2_16(self):
        module = _module()
        blade = _blade()
        with _env(module, blade, api_version="2.15"):
            _call_main()
        module.fail_json.assert_called_once()
        assert "REST version not supported" in module.fail_json.call_args[1]["msg"]
        blade.post_support_diagnostics.assert_not_called()
        blade.get_support_diagnostics.assert_not_called()

    def test_fails_on_non_positive_timeout(self):
        module = _module(_base_params(timeout=0))
        blade = _blade()
        with _env(module, blade):
            _call_main()
        module.fail_json.assert_called_once()
        assert "timeout" in module.fail_json.call_args[1]["msg"]
        blade.post_support_diagnostics.assert_not_called()

    def test_fails_on_inverted_window_before_posting(self):
        module = _module(
            _base_params(
                start_time="2026-01-01 02:00:00",
                end_time="2026-01-01 01:00:00",
                timezone="UTC",
            )
        )
        blade = _blade()
        with _env(module, blade):
            _call_main()
        module.fail_json.assert_called_once()
        blade.post_support_diagnostics.assert_not_called()
