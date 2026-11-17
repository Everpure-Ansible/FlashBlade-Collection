# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_sessions module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import datetime
import multiprocessing
import ctypes
from types import SimpleNamespace
from unittest.mock import Mock, patch, MagicMock

import pytest

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

from plugins.modules.purefb_sessions import (
    main,
    _to_timestamp,
    _or_clause,
    _get_filter_string,
    _format_time,
    _get_timezone,
    _list_sessions,
)

MODULE = "plugins.modules.purefb_sessions"

# 2024-01-01 00:00:00 UTC and 2024-01-01 23:59:59 UTC in epoch milliseconds
DAY_START_MS = 1704067200000
DAY_END_MS = 1704153599000
# The start clause also matches entries whose start time is 0 or absent on their end time
START_CLAUSE = (
    "(start_time>={0} or ((start_time=0 or not(start_time)) and end_time>={0}))"
)
# Every listing is requested newest first
SORT = ["start_time-"]


class _FakeTz(datetime.tzinfo):
    """A fixed UTC tzinfo with the pytz ``localize`` method.

    pytz is not installed in the unit-test environment, so the module is run
    against this stand-in. Keeping the offset at zero makes every rendered
    time deterministic.
    """

    def utcoffset(self, dt):
        return datetime.timedelta(0)

    def dst(self, dt):
        return datetime.timedelta(0)

    def tzname(self, dt):
        return "UTC"

    def localize(self, naive):
        return naive.replace(tzinfo=self)


FAKE_PYTZ = SimpleNamespace(
    all_timezones_set={"UTC", "America/Los_Angeles", "Europe/London"},
    timezone=lambda name: _FakeTz(),
)


def _base_params(**overrides):
    params = {
        "start": None,
        "end": None,
        "timezone": None,
        "user": None,
        "event": None,
        "user_interface": None,
        "method": None,
        "limit": None,
    }
    params.update(overrides)
    return params


def _module(params=None, check_mode=False):
    module = Mock()
    module.params = params if params is not None else _base_params()
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _session(**fields):
    """A session row; attributes the array did not send are simply absent."""
    return SimpleNamespace(**fields)


def _blade(sessions=None, status_code=200, time_zone="America/Los_Angeles"):
    blade = Mock()
    arrays = Mock()
    arrays.status_code = 200
    arrays.items = [SimpleNamespace(time_zone=time_zone)]
    blade.get_arrays.return_value = arrays
    response = Mock()
    response.status_code = status_code
    response.items = sessions if sessions is not None else []
    blade.get_sessions.return_value = response
    return blade


@pytest.fixture(autouse=True)
def _fake_pytz():
    """Run every test against the deterministic pytz stand-in."""
    with patch(MODULE + ".pytz", FAKE_PYTZ, create=True):
        with patch(MODULE + ".HAS_PYTZ", True):
            yield


class TestToTimestamp:
    """Tests for _to_timestamp"""

    def test_valid_value_is_converted_to_epoch_milliseconds(self):
        module = _module(_base_params(start="2024-01-01 00:00:00"))
        assert _to_timestamp(module, "start", "UTC") == DAY_START_MS

    def test_malformed_value_fails_with_expected_format(self):
        module = _module(_base_params(start="2024-13-45"))
        with pytest.raises(SystemExit):
            _to_timestamp(module, "start", "UTC")
        msg = module.fail_json.call_args[1]["msg"]
        assert "start value 2024-13-45 is not a valid date/time" in msg
        assert "YYYY-MM-DD hh:mm:ss" in msg


class TestOrClause:
    """Tests for _or_clause"""

    def test_single_value_has_no_parentheses(self):
        assert _or_clause("event", ["login"]) == "event='login'"

    def test_multiple_values_are_or_joined_in_parentheses(self):
        assert (
            _or_clause("event", ["login", "logout"])
            == "(event='login' or event='logout')"
        )


class TestGetFilterString:
    """Tests for _get_filter_string"""

    def test_no_filters_returns_empty_string(self):
        assert _get_filter_string(_module(), "UTC") == ""

    def test_start_matches_unrecorded_start_times_on_end_time(self):
        module = _module(_base_params(start="2024-01-01 00:00:00"))
        assert _get_filter_string(module, "UTC") == START_CLAUSE.format(DAY_START_MS)

    def test_end_only(self):
        module = _module(_base_params(end="2024-01-01 23:59:59"))
        assert _get_filter_string(module, "UTC") == "end_time<={0}".format(DAY_END_MS)

    def test_start_and_end_are_and_joined(self):
        module = _module(
            _base_params(start="2024-01-01 00:00:00", end="2024-01-01 23:59:59")
        )
        result = _get_filter_string(module, "UTC")
        assert result.startswith("(start_time>={0}".format(DAY_START_MS))
        assert result.endswith(" and end_time<={0}".format(DAY_END_MS))

    def test_user_clause(self):
        module = _module(_base_params(user="pureuser"))
        assert _get_filter_string(module, "UTC") == "user='pureuser'"

    def test_single_event(self):
        module = _module(_base_params(event=["failed authentication"]))
        assert _get_filter_string(module, "UTC") == "event='failed authentication'"

    def test_undocumented_event_is_passed_through_unchanged(self):
        """The event set is open: the array records values the docs do not list"""
        module = _module(_base_params(event=["denied by network policy"]))
        assert _get_filter_string(module, "UTC") == "event='denied by network policy'"

    def test_multiple_events_interfaces_and_methods(self):
        module = _module(
            _base_params(
                event=["login", "logout"],
                user_interface=["CLI", "GUI"],
                method=["password"],
            )
        )
        assert _get_filter_string(module, "UTC") == (
            "(event='login' or event='logout') and "
            "(user_interface='CLI' or user_interface='GUI') and "
            "method='password'"
        )

    def test_all_filters_combined_in_order(self):
        module = _module(
            _base_params(
                start="2024-01-01 00:00:00",
                end="2024-01-01 23:59:59",
                user="pureuser",
                event=["user session"],
                user_interface=["REST"],
                method=["API token"],
            )
        )
        assert _get_filter_string(module, "UTC") == (
            START_CLAUSE + " and "
            "end_time<={1} and user='pureuser' and event='user session' and "
            "user_interface='REST' and method='API token'"
        ).format(DAY_START_MS, DAY_END_MS)


class TestFormatTime:
    """Tests for _format_time"""

    def test_zero_is_not_recorded(self):
        assert _format_time(0, "UTC") is None

    def test_none_is_not_recorded(self):
        assert _format_time(None, "UTC") is None

    def test_value_is_rendered_in_timezone(self):
        assert _format_time(DAY_START_MS, "UTC") == "2024-01-01 00:00:00"


class TestGetTimezone:
    """Tests for _get_timezone"""

    def test_explicit_timezone_is_used_without_reading_the_array(self):
        module = _module(_base_params(timezone="Europe/London"))
        blade = _blade()
        assert _get_timezone(module, blade) == "Europe/London"
        blade.get_arrays.assert_not_called()

    def test_explicit_invalid_timezone_fails(self):
        module = _module(_base_params(timezone="Mars/Olympus"))
        with pytest.raises(SystemExit):
            _get_timezone(module, _blade())
        assert (
            module.fail_json.call_args[1]["msg"] == "Timezone Mars/Olympus is not valid"
        )

    def test_default_timezone_is_read_from_the_array(self):
        module = _module()
        assert _get_timezone(module, _blade()) == "America/Los_Angeles"
        module.warn.assert_not_called()

    @patch(MODULE + ".get_local_tz")
    def test_array_read_failure_falls_back_to_local_timezone(self, mock_local_tz):
        mock_local_tz.return_value = "Europe/London"
        module = _module()
        blade = _blade()
        blade.get_arrays.return_value.status_code = 500
        assert _get_timezone(module, blade) == "Europe/London"
        mock_local_tz.assert_called_once_with(module)
        module.warn.assert_called_once_with(
            "Could not read the timezone of the array; using Europe/London"
        )

    @patch(MODULE + ".get_local_tz")
    def test_array_without_timezone_falls_back_to_local_timezone(self, mock_local_tz):
        mock_local_tz.return_value = "UTC"
        module = _module()
        assert _get_timezone(module, _blade(time_zone=None)) == "UTC"
        mock_local_tz.assert_called_once_with(module)
        module.warn.assert_called_once_with(
            "Could not read the timezone of the array; using UTC"
        )

    @patch(MODULE + ".get_local_tz")
    def test_array_without_items_falls_back_to_local_timezone(self, mock_local_tz):
        mock_local_tz.return_value = "UTC"
        module = _module()
        blade = _blade()
        blade.get_arrays.return_value.items = []
        assert _get_timezone(module, blade) == "UTC"
        mock_local_tz.assert_called_once_with(module)

    @patch(MODULE + ".get_local_tz")
    def test_unknown_fallback_timezone_fails(self, mock_local_tz):
        mock_local_tz.return_value = "Not/AZone"
        module = _module()
        with pytest.raises(SystemExit):
            _get_timezone(module, _blade(time_zone=None))
        assert module.fail_json.call_args[1]["msg"] == "Timezone Not/AZone is not valid"


class TestListSessions:
    """Tests for _list_sessions"""

    def test_rows_are_rendered_with_times_in_timezone(self):
        module = _module()
        blade = _blade(
            sessions=[
                _session(
                    name="22818414",
                    user="pureuser",
                    user_interface="REST",
                    method="API token",
                    event="user session",
                    event_count=1,
                    location="10.21.22.11",
                    start_time=DAY_START_MS,
                    end_time=DAY_START_MS + 1000,
                    identifying_details=None,
                )
            ]
        )
        assert _list_sessions(module, blade, "UTC") == [
            {
                "name": "22818414",
                "user": "pureuser",
                "user_interface": "REST",
                "method": "API token",
                "event": "user session",
                "event_count": 1,
                "location": "10.21.22.11",
                "start_time": "2024-01-01 00:00:00",
                "end_time": "2024-01-01 00:00:01",
                "identifying_details": None,
            }
        ]
        blade.get_sessions.assert_called_once_with(sort=SORT)

    def test_unrecorded_times_and_method_are_normalised(self):
        """start_time 0, an absent end_time and an absent method all come from the array"""
        module = _module()
        blade = _blade(
            sessions=[
                _session(
                    name="22818596",
                    user="pureuser",
                    user_interface="REST",
                    event="login",
                    event_count=1,
                    location="10.21.200.169",
                    start_time=0,
                ),
                _session(
                    name="22818389",
                    user="pureuser",
                    user_interface="REST",
                    method="",
                    event="user session",
                    event_count=1,
                    location="10.21.93.235",
                    start_time=0,
                    end_time=DAY_END_MS,
                ),
            ]
        )
        rows = _list_sessions(module, blade, "UTC")
        assert rows[0]["start_time"] is None
        assert rows[0]["end_time"] is None
        assert rows[0]["method"] == ""
        assert rows[0]["identifying_details"] is None
        assert rows[1]["start_time"] is None
        assert rows[1]["end_time"] == "2024-01-01 23:59:59"
        assert rows[1]["method"] == ""

    def test_filter_limit_and_newest_first_sort_are_passed(self):
        module = _module(
            _base_params(start="2024-01-01 00:00:00", user="pureuser", limit=20)
        )
        blade = _blade()
        assert _list_sessions(module, blade, "UTC") == []
        kwargs = blade.get_sessions.call_args[1]
        assert kwargs == {
            "filter": (START_CLAUSE + " and user='pureuser'").format(DAY_START_MS),
            "limit": 20,
            "sort": SORT,
        }

    def test_empty_result_is_an_empty_list(self):
        assert _list_sessions(_module(), _blade(), "UTC") == []

    @patch(MODULE + ".get_error_message")
    def test_api_error_fails_with_array_message(self, mock_error):
        mock_error.return_value = "Unknown attribute."
        module = _module()
        with pytest.raises(SystemExit):
            _list_sessions(module, _blade(status_code=400), "UTC")
        assert (
            module.fail_json.call_args[1]["msg"]
            == "Failed to get sessions. Error: Unknown attribute."
        )


def _run_main(module, blade, version_too_low=False):
    """Run main() with the collection helpers patched; return the blade."""
    with patch(MODULE + ".AnsibleModule") as mock_ansible_module:
        with patch(MODULE + ".get_system") as mock_get_system:
            with patch(MODULE + ".get_rest_api_version") as mock_version:
                with patch(MODULE + ".LooseVersion") as mock_loose_version:
                    mock_ansible_module.return_value = module
                    mock_get_system.return_value = blade
                    mock_version.return_value = "2.30"
                    mock_loose_version.return_value.__gt__ = Mock(
                        return_value=version_too_low
                    )
                    with pytest.raises(SystemExit):
                        main()
    return blade


class TestMain:
    """Tests for main()"""

    def test_missing_pytz_fails_before_connecting(self):
        module = _module()
        with patch(MODULE + ".HAS_PYTZ", False):
            with patch(MODULE + ".get_system") as mock_get_system:
                with patch(MODULE + ".AnsibleModule") as mock_ansible_module:
                    mock_ansible_module.return_value = module
                    with pytest.raises(SystemExit):
                        main()
                mock_get_system.assert_not_called()
        assert (
            module.fail_json.call_args[1]["msg"] == "pytz is required for this module"
        )

    def test_non_positive_limit_fails_before_connecting(self):
        module = _module(_base_params(limit=0))
        with patch(MODULE + ".get_system") as mock_get_system:
            with patch(MODULE + ".AnsibleModule") as mock_ansible_module:
                mock_ansible_module.return_value = module
                with pytest.raises(SystemExit):
                    main()
            mock_get_system.assert_not_called()
        assert (
            module.fail_json.call_args[1]["msg"] == "limit must be a positive integer"
        )

    def test_version_gate_fails_before_any_read(self):
        module = _module()
        blade = _run_main(module, _blade(), version_too_low=True)
        msg = module.fail_json.call_args[1]["msg"]
        assert "FlashBlade REST version not supported" in msg
        assert "Minimum version required: 2.3" in msg
        blade.get_arrays.assert_not_called()
        blade.get_sessions.assert_not_called()
        module.exit_json.assert_not_called()

    def test_lists_sessions_without_filters_and_never_changes(self):
        module = _module()
        blade = _run_main(
            module,
            _blade(
                sessions=[
                    _session(
                        name="1",
                        user="pureuser",
                        user_interface="CLI",
                        method="password",
                        event="login",
                        event_count=1,
                        location="console",
                        start_time=DAY_START_MS,
                    )
                ]
            ),
        )
        blade.get_sessions.assert_called_once_with(sort=SORT)
        kwargs = module.exit_json.call_args[1]
        assert kwargs["changed"] is False
        assert kwargs["purefb_sessions"] == [
            {
                "name": "1",
                "user": "pureuser",
                "user_interface": "CLI",
                "method": "password",
                "event": "login",
                "event_count": 1,
                "location": "console",
                "start_time": "2024-01-01 00:00:00",
                "end_time": None,
                "identifying_details": None,
            }
        ]

    def test_filters_use_the_array_timezone_by_default(self):
        """Times are parsed in the array timezone read from get_arrays()"""
        module = _module(
            _base_params(
                start="2024-01-01 00:00:00",
                event=["failed authentication", "login"],
                user_interface=["REST"],
                method=["API token"],
                limit=5,
            )
        )
        blade = _run_main(module, _blade())
        blade.get_arrays.assert_called_once_with()
        kwargs = blade.get_sessions.call_args[1]
        assert kwargs == {
            "filter": (
                START_CLAUSE + " and "
                "(event='failed authentication' or event='login') and "
                "user_interface='REST' and method='API token'"
            ).format(DAY_START_MS),
            "limit": 5,
            "sort": SORT,
        }
        assert module.exit_json.call_args[1]["changed"] is False

    def test_explicit_timezone_skips_the_array_read(self):
        module = _module(_base_params(timezone="UTC"))
        blade = _run_main(module, _blade())
        blade.get_arrays.assert_not_called()
        assert module.exit_json.call_args[1] == {
            "changed": False,
            "purefb_sessions": [],
        }

    def test_invalid_timezone_fails_before_reading_sessions(self):
        module = _module(_base_params(timezone="Mars/Olympus"))
        blade = _run_main(module, _blade())
        assert (
            module.fail_json.call_args[1]["msg"] == "Timezone Mars/Olympus is not valid"
        )
        blade.get_sessions.assert_not_called()

    @patch(MODULE + ".get_error_message")
    def test_api_error_fails(self, mock_error):
        mock_error.return_value = "boom"
        module = _module()
        _run_main(module, _blade(status_code=500))
        assert (
            module.fail_json.call_args[1]["msg"]
            == "Failed to get sessions. Error: boom"
        )
        module.exit_json.assert_not_called()

    def test_check_mode_reads_and_reports_unchanged(self):
        module = _module(check_mode=True)
        blade = _run_main(
            module,
            _blade(
                sessions=[
                    _session(
                        name="1",
                        user="pureuser",
                        user_interface="REST",
                        event="user session",
                        event_count=1,
                        location="10.21.22.11",
                        start_time=0,
                        end_time=DAY_START_MS,
                    )
                ]
            ),
        )
        blade.get_sessions.assert_called_once_with(sort=SORT)
        kwargs = module.exit_json.call_args[1]
        assert kwargs["changed"] is False
        assert len(kwargs["purefb_sessions"]) == 1
        assert kwargs["purefb_sessions"][0]["end_time"] == "2024-01-01 00:00:00"

    def test_rerun_is_idempotent(self):
        """Two identical runs read twice, change nothing and return the same rows"""
        rows = [
            _session(
                name="1",
                user="pureuser",
                user_interface="REST",
                method="API token",
                event="login",
                event_count=1,
                location="10.21.22.11",
                start_time=DAY_START_MS,
            )
        ]
        module = _module(_base_params(user="pureuser"))
        blade = _blade(sessions=rows)
        _run_main(module, blade)
        _run_main(module, blade)
        assert blade.get_sessions.call_count == 2
        assert (
            blade.get_sessions.call_args_list[0] == blade.get_sessions.call_args_list[1]
        )
        first, second = module.exit_json.call_args_list
        assert first[1]["changed"] is False
        assert second[1]["changed"] is False
        assert first[1]["purefb_sessions"] == second[1]["purefb_sessions"]
        module.fail_json.assert_not_called()
