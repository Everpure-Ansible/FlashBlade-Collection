# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_maintenance module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from unittest.mock import DEFAULT, Mock, patch, MagicMock

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
# Bind the real time helpers so the duration parsing under test is genuine,
# not a MagicMock that accepts anything.
from plugins.module_utils import time_utils as _real_time_utils

sys.modules[
    "ansible_collections.everpure.flashblade.plugins.module_utils.time_utils"
] = _real_time_utils

from plugins.modules.purefb_maintenance import (
    main,
    parse_timeout,
    window_duration,
    window_facts,
    get_window,
    delete_window,
    set_window,
    WINDOW_NAME,
)

MOD = "plugins.modules.purefb_maintenance"
CREATED = 1700000000000
ONE_HOUR_MS = 3600000
# What the array answers (400) to a duration outside its range.
ARRAY_RANGE_ERROR = "Duration must be between 1 hour and 48 hours."
RANGE_MESSAGE = (
    "timeout must be between 1 hour and 48 hours "
    "(3600 to 172800 seconds), got {0} seconds"
)


def _window(created=CREATED, duration_ms=ONE_HOUR_MS, name="array"):
    window = Mock()
    window.name = name
    window.created = created
    window.expires = created + duration_ms
    return window


def _response(status=200, items=None, error="boom"):
    res = Mock()
    res.status_code = status
    res.items = list(items or [])
    err = Mock()
    err.message = error
    res.errors = [err]
    return res


def _module(params=None, check_mode=False):
    module = Mock()
    module.params = {"state": "present", "timeout": "4h", "extend": False}
    module.params.update(params or {})
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _exit_args(module):
    module.exit_json.assert_called_once()
    return module.exit_json.call_args[1]


def _fail_msg(module):
    module.fail_json.assert_called_once()
    return module.fail_json.call_args[1]["msg"]


class TestParseTimeout:
    """parse_timeout accepts seconds or s/m/h/d durations within 1h..48h"""

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("4h", 14400),
            ("90m", 5400),
            ("2d", 172800),
            ("48h", 172800),
            ("172800", 172800),
            ("1d", 86400),
            ("1h", 3600),
            ("60m", 3600),
            ("3600s", 3600),
            ("3600", 3600),
            (3600, 3600),
            (" 90M ", 5400),
        ],
    )
    def test_valid_values(self, value, expected):
        module = _module({"timeout": value})
        assert parse_timeout(module) == expected
        module.fail_json.assert_not_called()

    @pytest.mark.parametrize(
        "value,fragment",
        [
            ("49h", "between 1 hour and 48 hours"),
            ("172801", "between 1 hour and 48 hours"),
            ("3d", "between 1 hour and 48 hours"),
            ("1w", "Invalid timeout"),
            ("0", "between 1 hour and 48 hours"),
            ("0s", "between 1 hour and 48 hours"),
            # The array refuses anything shorter than one hour, so the
            # module does too instead of sending it.
            ("3599", "between 1 hour and 48 hours"),
            (3599, "between 1 hour and 48 hours"),
            ("3599s", "between 1 hour and 48 hours"),
            ("59m", "between 1 hour and 48 hours"),
            (" 30M ", "between 1 hour and 48 hours"),
            ("5s", "between 1 hour and 48 hours"),
            ("1s", "between 1 hour and 48 hours"),
            ("1", "between 1 hour and 48 hours"),
            ("-1h", "Invalid timeout"),
            ("abc", "Invalid timeout"),
            ("4x", "Invalid timeout"),
            ("2AM", "Invalid timeout"),
            ("h", "Invalid timeout"),
            ("", "Invalid timeout"),
            # Superscript digits satisfy str.isdigit() but int() rejects them;
            # the module must refuse them instead of raising ValueError.
            ("²", "Invalid timeout"),
            ("4²h", "Invalid timeout"),
            ("¹h", "Invalid timeout"),
        ],
    )
    def test_invalid_values(self, value, fragment):
        module = _module({"timeout": value})
        with pytest.raises(SystemExit):
            parse_timeout(module)
        assert fragment in _fail_msg(module)

    @pytest.mark.parametrize(
        "value,seconds",
        [("30m", 1800), ("3599", 3599), ("0", 0), ("172801", 172801)],
    )
    def test_out_of_range_message_names_both_bounds(self, value, seconds):
        module = _module({"timeout": value})
        with pytest.raises(SystemExit):
            parse_timeout(module)
        assert _fail_msg(module) == RANGE_MESSAGE.format(seconds)


class TestWindowHelpers:
    """window_duration, window_facts and get_window"""

    def test_window_duration_in_seconds(self):
        assert window_duration(_window(duration_ms=7200000)) == 7200

    def test_window_duration_rounds_to_whole_seconds(self):
        assert window_duration(_window(duration_ms=3600400)) == 3600

    def test_window_duration_none_when_times_missing(self):
        window = Mock()
        window.created = None
        window.expires = CREATED
        assert window_duration(window) is None

    def test_window_facts_empty_without_window(self):
        assert window_facts(None) == {}

    def test_window_facts_reports_window(self):
        assert window_facts(_window()) == {
            "name": "array",
            "created": CREATED,
            "expires": CREATED + ONE_HOUR_MS,
            "timeout": 3600,
        }

    def test_get_window_returns_open_window(self):
        window = _window()
        blade = Mock()
        blade.get_maintenance_windows.return_value = _response(items=[window])
        assert get_window(_module(), blade) is window
        blade.get_maintenance_windows.assert_called_once_with()

    def test_get_window_none_when_closed(self):
        blade = Mock()
        blade.get_maintenance_windows.return_value = _response(items=[])
        assert get_window(_module(), blade) is None

    def test_get_window_fails_on_api_error(self):
        module = _module()
        blade = Mock()
        blade.get_maintenance_windows.return_value = _response(status=400)
        with pytest.raises(SystemExit):
            get_window(module, blade)
        assert _fail_msg(module).startswith("Failed to get maintenance window")


class TestDeleteWindow:
    """delete_window closes an open window and is idempotent"""

    def test_delete_closes_open_window(self):
        module = _module({"state": "absent"})
        blade = Mock()
        blade.delete_maintenance_windows.return_value = _response()
        with pytest.raises(SystemExit):
            delete_window(module, blade, _window())
        blade.delete_maintenance_windows.assert_called_once_with(names=[WINDOW_NAME])
        assert _exit_args(module) == {"changed": True, "maintenance_window": {}}

    def test_delete_check_mode_reports_existing_window(self):
        module = _module({"state": "absent"}, check_mode=True)
        blade = Mock()
        with pytest.raises(SystemExit):
            delete_window(module, blade, _window())
        blade.delete_maintenance_windows.assert_not_called()
        args = _exit_args(module)
        assert args["changed"] is True
        assert args["maintenance_window"]["timeout"] == 3600

    def test_delete_idempotent_without_window(self):
        module = _module({"state": "absent"})
        blade = Mock()
        with pytest.raises(SystemExit):
            delete_window(module, blade, None)
        blade.delete_maintenance_windows.assert_not_called()
        assert _exit_args(module) == {"changed": False, "maintenance_window": {}}

    def test_delete_fails_on_api_error(self):
        module = _module({"state": "absent"})
        blade = Mock()
        blade.delete_maintenance_windows.return_value = _response(
            status=400, error="nope"
        )
        with pytest.raises(SystemExit):
            delete_window(module, blade, _window())
        assert _fail_msg(module).startswith("Failed to close maintenance window")
        module.exit_json.assert_not_called()


class TestSetWindow:
    """set_window opens or replaces a window only when the duration differs"""

    @patch(MOD + ".MaintenanceWindowPost")
    def test_opens_window_when_none_open(self, mock_post_model):
        module = _module({"timeout": "1h"})
        blade = Mock()
        blade.post_maintenance_windows.return_value = _response()
        blade.get_maintenance_windows.return_value = _response(items=[_window()])
        with pytest.raises(SystemExit):
            set_window(module, blade, None)
        mock_post_model.assert_called_once_with(timeout=ONE_HOUR_MS)
        blade.post_maintenance_windows.assert_called_once_with(
            names=[WINDOW_NAME], maintenance_window=mock_post_model.return_value
        )
        args = _exit_args(module)
        assert args["changed"] is True
        assert args["maintenance_window"]["timeout"] == 3600

    def test_open_check_mode_posts_nothing(self):
        module = _module({"timeout": "1h"}, check_mode=True)
        blade = Mock()
        with pytest.raises(SystemExit):
            set_window(module, blade, None)
        blade.post_maintenance_windows.assert_not_called()
        blade.get_maintenance_windows.assert_not_called()
        assert _exit_args(module) == {"changed": True, "maintenance_window": {}}

    def test_same_duration_is_idempotent(self):
        module = _module({"timeout": "3600"})
        blade = Mock()
        with pytest.raises(SystemExit):
            set_window(module, blade, _window())
        blade.post_maintenance_windows.assert_not_called()
        args = _exit_args(module)
        assert args["changed"] is False
        assert args["maintenance_window"]["expires"] == CREATED + ONE_HOUR_MS

    @patch(MOD + ".MaintenanceWindowPost")
    def test_different_duration_replaces_window(self, mock_post_model):
        module = _module({"timeout": "2h"})
        blade = Mock()
        blade.post_maintenance_windows.return_value = _response()
        blade.get_maintenance_windows.return_value = _response(
            items=[_window(created=CREATED + 1000, duration_ms=7200000)]
        )
        with pytest.raises(SystemExit):
            set_window(module, blade, _window())
        mock_post_model.assert_called_once_with(timeout=7200000)
        blade.post_maintenance_windows.assert_called_once()
        args = _exit_args(module)
        assert args["changed"] is True
        assert args["maintenance_window"]["timeout"] == 7200
        assert args["maintenance_window"]["created"] == CREATED + 1000

    def test_replace_check_mode_reports_existing_window(self):
        module = _module({"timeout": "2h"}, check_mode=True)
        blade = Mock()
        with pytest.raises(SystemExit):
            set_window(module, blade, _window())
        blade.post_maintenance_windows.assert_not_called()
        args = _exit_args(module)
        assert args["changed"] is True
        assert args["maintenance_window"]["timeout"] == 3600

    @patch(MOD + ".MaintenanceWindowPost")
    def test_post_failure_is_reported(self, mock_post_model):
        module = _module({"timeout": "1h"})
        blade = Mock()
        blade.post_maintenance_windows.return_value = _response(status=400)
        with pytest.raises(SystemExit):
            set_window(module, blade, None)
        assert _fail_msg(module).startswith("Failed to open maintenance window")
        blade.get_maintenance_windows.assert_not_called()
        module.exit_json.assert_not_called()

    def test_invalid_timeout_posts_nothing(self):
        module = _module({"timeout": "49h"})
        blade = Mock()
        with pytest.raises(SystemExit):
            set_window(module, blade, None)
        blade.post_maintenance_windows.assert_not_called()
        assert "48 hours" in _fail_msg(module)

    @patch(MOD + ".MaintenanceWindowPost")
    def test_extend_replaces_window_of_same_duration(self, mock_post_model):
        module = _module({"timeout": "1h", "extend": True})
        blade = Mock()
        blade.post_maintenance_windows.return_value = _response()
        blade.get_maintenance_windows.return_value = _response(
            items=[_window(created=CREATED + 5000)]
        )
        with pytest.raises(SystemExit):
            set_window(module, blade, _window())
        mock_post_model.assert_called_once_with(timeout=ONE_HOUR_MS)
        blade.post_maintenance_windows.assert_called_once_with(
            names=[WINDOW_NAME], maintenance_window=mock_post_model.return_value
        )
        args = _exit_args(module)
        assert args["changed"] is True
        assert args["maintenance_window"]["created"] == CREATED + 5000
        assert args["maintenance_window"]["timeout"] == 3600

    def test_extend_check_mode_reports_existing_window(self):
        module = _module({"timeout": "1h", "extend": True}, check_mode=True)
        blade = Mock()
        with pytest.raises(SystemExit):
            set_window(module, blade, _window())
        blade.post_maintenance_windows.assert_not_called()
        args = _exit_args(module)
        assert args["changed"] is True
        assert args["maintenance_window"]["created"] == CREATED

    @patch(MOD + ".MaintenanceWindowPost")
    def test_extend_without_window_opens_one(self, mock_post_model):
        module = _module({"timeout": "1h", "extend": True})
        blade = Mock()
        blade.post_maintenance_windows.return_value = _response()
        blade.get_maintenance_windows.return_value = _response(items=[_window()])
        with pytest.raises(SystemExit):
            set_window(module, blade, None)
        blade.post_maintenance_windows.assert_called_once()
        assert _exit_args(module)["changed"] is True

    def test_extend_still_validates_timeout(self):
        module = _module({"timeout": "49h", "extend": True})
        blade = Mock()
        with pytest.raises(SystemExit):
            set_window(module, blade, _window())
        blade.post_maintenance_windows.assert_not_called()
        assert "48 hours" in _fail_msg(module)

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("timeout", ["30m", "3599", "5s"])
    def test_sub_hour_timeout_opens_nothing(self, timeout, check_mode):
        module = _module({"timeout": timeout}, check_mode=check_mode)
        blade = Mock()
        blade.post_maintenance_windows.return_value = _response(
            status=400, error=ARRAY_RANGE_ERROR
        )
        with pytest.raises(SystemExit):
            set_window(module, blade, None)
        assert "between 1 hour and 48 hours" in _fail_msg(module)
        blade.post_maintenance_windows.assert_not_called()
        module.exit_json.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("extend", [False, True])
    def test_sub_hour_timeout_leaves_open_window_alone(self, extend, check_mode):
        module = _module({"timeout": "30m", "extend": extend}, check_mode=check_mode)
        blade = Mock()
        blade.post_maintenance_windows.return_value = _response(
            status=400, error=ARRAY_RANGE_ERROR
        )
        with pytest.raises(SystemExit):
            set_window(module, blade, _window())
        assert _fail_msg(module) == RANGE_MESSAGE.format(1800)
        blade.post_maintenance_windows.assert_not_called()
        blade.delete_maintenance_windows.assert_not_called()
        module.exit_json.assert_not_called()

    @pytest.mark.parametrize(
        "timeout,milliseconds",
        [
            ("3600", 3600000),
            ("60m", 3600000),
            ("172800", 172800000),
            ("48h", 172800000),
        ],
    )
    def test_range_bounds_are_sent_to_the_array(self, timeout, milliseconds):
        module = _module({"timeout": timeout})
        blade = Mock()
        blade.post_maintenance_windows.return_value = _response()
        blade.get_maintenance_windows.return_value = _response(
            items=[_window(duration_ms=milliseconds)]
        )
        with patch(MOD + ".MaintenanceWindowPost") as mock_post_model:
            with pytest.raises(SystemExit):
                set_window(module, blade, None)
        mock_post_model.assert_called_once_with(timeout=milliseconds)
        blade.post_maintenance_windows.assert_called_once_with(
            names=[WINDOW_NAME], maintenance_window=mock_post_model.return_value
        )
        args = _exit_args(module)
        assert args["changed"] is True
        assert args["maintenance_window"]["timeout"] == milliseconds // 1000


class TestMain:
    """main() wiring: SDK check, version gate, state dispatch"""

    def _run(self, params, blade, check_mode=False, gate_fails=False):
        module = _module(params, check_mode=check_mode)
        with patch.multiple(
            MOD,
            AnsibleModule=Mock(return_value=module),
            get_system=Mock(return_value=blade),
            get_rest_api_version=Mock(return_value="2.30"),
            LooseVersion=DEFAULT,
            MaintenanceWindowPost=DEFAULT,
        ) as mocks:
            mocks["LooseVersion"].return_value.__gt__ = Mock(return_value=gate_fails)
            with pytest.raises(SystemExit):
                main()
        module.post_model = mocks["MaintenanceWindowPost"]
        return module

    def test_main_requires_sdk(self):
        blade = Mock()
        with patch(MOD + ".HAS_PYPURECLIENT", False):
            module = self._run({}, blade)
        assert "py-pure-client" in _fail_msg(module)
        blade.get_maintenance_windows.assert_not_called()

    def test_main_version_gate_blocks_everything(self):
        blade = Mock()
        module = self._run({"timeout": "1h"}, blade, gate_fails=True)
        assert "2.16" in _fail_msg(module)
        blade.get_maintenance_windows.assert_not_called()
        blade.post_maintenance_windows.assert_not_called()
        blade.delete_maintenance_windows.assert_not_called()

    def test_main_version_gate_blocks_check_mode_too(self):
        blade = Mock()
        module = self._run({"state": "absent"}, blade, check_mode=True, gate_fails=True)
        assert "2.16" in _fail_msg(module)
        blade.get_maintenance_windows.assert_not_called()

    def test_main_creates_window_with_default_timeout(self):
        blade = Mock()
        blade.get_maintenance_windows.side_effect = [
            _response(items=[]),
            _response(items=[_window(duration_ms=14400000)]),
        ]
        blade.post_maintenance_windows.return_value = _response()
        module = self._run({}, blade)
        module.post_model.assert_called_once_with(timeout=14400000)
        blade.post_maintenance_windows.assert_called_once_with(
            names=[WINDOW_NAME], maintenance_window=module.post_model.return_value
        )
        args = _exit_args(module)
        assert args["changed"] is True
        assert args["maintenance_window"]["timeout"] == 14400
        assert blade.get_maintenance_windows.call_count == 2

    def test_main_accepts_integer_seconds(self):
        blade = Mock()
        blade.get_maintenance_windows.side_effect = [
            _response(items=[]),
            _response(items=[_window()]),
        ]
        blade.post_maintenance_windows.return_value = _response()
        module = self._run({"timeout": 3600}, blade)
        module.post_model.assert_called_once_with(timeout=ONE_HOUR_MS)
        assert _exit_args(module)["changed"] is True

    def test_main_create_check_mode(self):
        blade = Mock()
        blade.get_maintenance_windows.return_value = _response(items=[])
        module = self._run({"timeout": "1h"}, blade, check_mode=True)
        blade.post_maintenance_windows.assert_not_called()
        assert _exit_args(module) == {"changed": True, "maintenance_window": {}}

    def test_main_present_idempotent(self):
        blade = Mock()
        blade.get_maintenance_windows.return_value = _response(items=[_window()])
        module = self._run({"timeout": "60m"}, blade)
        blade.post_maintenance_windows.assert_not_called()
        args = _exit_args(module)
        assert args["changed"] is False
        assert args["maintenance_window"]["name"] == "array"

    def test_main_extends_open_window(self):
        blade = Mock()
        blade.get_maintenance_windows.side_effect = [
            _response(items=[_window()]),
            _response(items=[_window(duration_ms=7200000)]),
        ]
        blade.post_maintenance_windows.return_value = _response()
        module = self._run({"timeout": "2h"}, blade)
        module.post_model.assert_called_once_with(timeout=7200000)
        args = _exit_args(module)
        assert args["changed"] is True
        assert args["maintenance_window"]["timeout"] == 7200

    def test_main_extend_check_mode(self):
        blade = Mock()
        blade.get_maintenance_windows.return_value = _response(items=[_window()])
        module = self._run({"timeout": "2h"}, blade, check_mode=True)
        blade.post_maintenance_windows.assert_not_called()
        args = _exit_args(module)
        assert args["changed"] is True
        assert args["maintenance_window"]["timeout"] == 3600

    def test_main_extend_renews_same_duration(self):
        blade = Mock()
        blade.get_maintenance_windows.side_effect = [
            _response(items=[_window()]),
            _response(items=[_window(created=CREATED + 5000)]),
        ]
        blade.post_maintenance_windows.return_value = _response()
        module = self._run({"timeout": "1h", "extend": True}, blade)
        module.post_model.assert_called_once_with(timeout=ONE_HOUR_MS)
        blade.post_maintenance_windows.assert_called_once()
        args = _exit_args(module)
        assert args["changed"] is True
        assert args["maintenance_window"]["created"] == CREATED + 5000

    def test_main_extend_check_mode_posts_nothing(self):
        blade = Mock()
        blade.get_maintenance_windows.return_value = _response(items=[_window()])
        module = self._run({"timeout": "1h", "extend": True}, blade, check_mode=True)
        blade.post_maintenance_windows.assert_not_called()
        assert _exit_args(module)["changed"] is True

    def test_main_post_error(self):
        blade = Mock()
        blade.get_maintenance_windows.return_value = _response(items=[])
        blade.post_maintenance_windows.return_value = _response(status=400)
        module = self._run({"timeout": "1h"}, blade)
        assert _fail_msg(module).startswith("Failed to open maintenance window")

    def test_main_invalid_timeout(self):
        blade = Mock()
        blade.get_maintenance_windows.return_value = _response(items=[])
        module = self._run({"timeout": "49h"}, blade)
        assert "48 hours" in _fail_msg(module)
        blade.post_maintenance_windows.assert_not_called()

    def test_main_absent_closes_window(self):
        blade = Mock()
        blade.get_maintenance_windows.return_value = _response(items=[_window()])
        blade.delete_maintenance_windows.return_value = _response()
        module = self._run({"state": "absent"}, blade)
        blade.delete_maintenance_windows.assert_called_once_with(names=[WINDOW_NAME])
        assert _exit_args(module) == {"changed": True, "maintenance_window": {}}

    def test_main_absent_check_mode(self):
        blade = Mock()
        blade.get_maintenance_windows.return_value = _response(items=[_window()])
        module = self._run({"state": "absent"}, blade, check_mode=True)
        blade.delete_maintenance_windows.assert_not_called()
        assert _exit_args(module)["changed"] is True

    def test_main_absent_idempotent_and_ignores_timeout(self):
        blade = Mock()
        blade.get_maintenance_windows.return_value = _response(items=[])
        module = self._run({"state": "absent", "timeout": "49h"}, blade)
        blade.delete_maintenance_windows.assert_not_called()
        module.fail_json.assert_not_called()
        assert _exit_args(module) == {"changed": False, "maintenance_window": {}}

    def test_main_absent_ignores_extend(self):
        blade = Mock()
        blade.get_maintenance_windows.return_value = _response(items=[])
        module = self._run({"state": "absent", "extend": True}, blade)
        blade.post_maintenance_windows.assert_not_called()
        blade.delete_maintenance_windows.assert_not_called()
        assert _exit_args(module) == {"changed": False, "maintenance_window": {}}

    def test_main_delete_error(self):
        blade = Mock()
        blade.get_maintenance_windows.return_value = _response(items=[_window()])
        blade.delete_maintenance_windows.return_value = _response(status=400)
        module = self._run({"state": "absent"}, blade)
        assert _fail_msg(module).startswith("Failed to close maintenance window")

    def test_main_get_error(self):
        blade = Mock()
        blade.get_maintenance_windows.return_value = _response(status=400)
        module = self._run({"timeout": "1h"}, blade)
        assert _fail_msg(module).startswith("Failed to get maintenance window")
        blade.post_maintenance_windows.assert_not_called()
        blade.delete_maintenance_windows.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_main_sub_hour_timeout_fails_in_module(self, check_mode):
        blade = Mock()
        blade.get_maintenance_windows.return_value = _response(items=[])
        blade.post_maintenance_windows.return_value = _response(
            status=400, error=ARRAY_RANGE_ERROR
        )
        module = self._run({"timeout": "30m"}, blade, check_mode=check_mode)
        assert _fail_msg(module) == RANGE_MESSAGE.format(1800)
        blade.post_maintenance_windows.assert_not_called()
        module.exit_json.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_main_sub_hour_timeout_keeps_open_window(self, check_mode):
        blade = Mock()
        blade.get_maintenance_windows.return_value = _response(items=[_window()])
        blade.post_maintenance_windows.return_value = _response(
            status=400, error=ARRAY_RANGE_ERROR
        )
        module = self._run({"timeout": "3599"}, blade, check_mode=check_mode)
        assert _fail_msg(module) == RANGE_MESSAGE.format(3599)
        blade.post_maintenance_windows.assert_not_called()
        blade.delete_maintenance_windows.assert_not_called()
        module.exit_json.assert_not_called()

    def test_main_one_hour_window_is_opened(self):
        blade = Mock()
        blade.get_maintenance_windows.side_effect = [
            _response(items=[]),
            _response(items=[_window()]),
        ]
        blade.post_maintenance_windows.return_value = _response()
        module = self._run({"timeout": "60m"}, blade)
        module.post_model.assert_called_once_with(timeout=ONE_HOUR_MS)
        module.fail_json.assert_not_called()
        args = _exit_args(module)
        assert args["changed"] is True
        assert args["maintenance_window"]["timeout"] == 3600

    def test_main_absent_ignores_sub_hour_timeout(self):
        blade = Mock()
        blade.get_maintenance_windows.return_value = _response(items=[_window()])
        blade.delete_maintenance_windows.return_value = _response()
        module = self._run({"state": "absent", "timeout": "30m"}, blade)
        blade.delete_maintenance_windows.assert_called_once_with(names=[WINDOW_NAME])
        module.fail_json.assert_not_called()
        assert _exit_args(module) == {"changed": True, "maintenance_window": {}}
