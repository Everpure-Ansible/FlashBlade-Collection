# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_admin module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from contextlib import ExitStack
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

from plugins.modules.purefb_admin import main

MOD = "plugins.modules.purefb_admin"
REFUSED = "Operation not permitted."
READ_FAILED = "Failed to read Global Admin settings. Error: {0}"
CHANGE_FAILED = "Failed to change Global Admin settings. Error: {0}"


class ExitJson(Exception):
    """Raised by the exit_json stand-in: the real one ends the module."""


class FailJson(Exception):
    """Raised by the fail_json stand-in: the real one ends the module."""


def _module(check_mode=False, **params):
    module = Mock()
    module.params = {"max_login": None, "min_password": None, "lockout": None}
    module.params.update(params)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=ExitJson)
    module.fail_json = Mock(side_effect=FailJson)
    return module


def _settings(lockout=300000, max_login=5, min_password=10):
    """The Global Admin settings as the array returns them.

    The lockout duration is in milliseconds. A rule that is not set comes
    back as None.
    """
    return SimpleNamespace(
        lockout_duration=lockout,
        max_login_attempts=max_login,
        min_password_length=min_password,
    )


def _valid(items):
    """A response to a request the array accepted."""
    res = Mock(spec=["status_code", "items", "total_item_count", "headers"])
    res.status_code = 200
    res.items = list(items)
    res.total_item_count = len(res.items)
    res.headers = {}
    return res


def _error(message=REFUSED, status_code=400):
    """A response to a request the array refused: it carries no items."""
    res = Mock(spec=["status_code", "errors", "headers"])
    res.status_code = status_code
    res.errors = []
    if message is not None:
        res.errors = [
            SimpleNamespace(context=None, location_context=None, message=message)
        ]
    res.headers = {}
    return res


def _error_message(response, default="Unknown error"):
    """What get_error_message of module_utils returns for a response."""
    errors = list(getattr(response, "errors", None) or [])
    return errors[0].message if errors else default


def _blade(read=None, write=None):
    """An array holding lockout 300 s, 5 login attempts, 10 characters."""
    blade = Mock()
    blade.get_admins_settings.return_value = (
        read if read is not None else _valid([_settings()])
    )
    blade.patch_admins_settings.return_value = (
        write if write is not None else _valid([_settings()])
    )
    return blade


def _run(module, blade, sdk=True):
    """Run main() against the stand-ins.

    Returns how the module ended ("exit" or "fail") with the patched
    AnsibleModule and get_system. AdminSetting is replaced by a function that
    returns its keyword arguments, so the body of a PATCH can be compared.
    """
    with ExitStack() as stack:
        ansible_module = stack.enter_context(
            patch(MOD + ".AnsibleModule", return_value=module)
        )
        get_system = stack.enter_context(patch(MOD + ".get_system", return_value=blade))
        stack.enter_context(
            patch(MOD + ".get_error_message", side_effect=_error_message)
        )
        stack.enter_context(patch(MOD + ".HAS_PYPURECLIENT", sdk))
        stack.enter_context(
            patch(MOD + ".AdminSetting", side_effect=lambda **kwargs: kwargs)
        )
        outcome = None
        try:
            main()
        except ExitJson:
            outcome = "exit"
        except FailJson:
            outcome = "fail"
    assert outcome is not None, "main() ended without exit_json or fail_json"
    return SimpleNamespace(
        outcome=outcome, ansible_module=ansible_module, get_system=get_system
    )


def _failure(module):
    """The message of the single fail_json call of a run that failed."""
    module.fail_json.assert_called_once()
    module.exit_json.assert_not_called()
    return module.fail_json.call_args[1]["msg"]


class TestPurefbAdminRead:
    """The read of the current settings."""

    def test_refused_read_reports_the_answer_of_the_array(self):
        module = _module()
        blade = _blade(read=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == READ_FAILED.format(REFUSED)
        blade.patch_admins_settings.assert_not_called()

    def test_refused_read_in_check_mode(self):
        module = _module(check_mode=True, max_login=7)
        blade = _blade(read=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == READ_FAILED.format(REFUSED)
        blade.patch_admins_settings.assert_not_called()

    def test_refused_read_sends_no_write(self):
        module = _module(max_login=7, min_password=11, lockout=120)
        blade = _blade(read=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == READ_FAILED.format(REFUSED)
        blade.get_admins_settings.assert_called_once_with()
        blade.patch_admins_settings.assert_not_called()

    @pytest.mark.parametrize("status_code", [401, 403, 429, 500, 503])
    def test_failed_read_reports_the_text_whatever_the_status(self, status_code):
        message = "The text of the array."
        module = _module(lockout=120)
        blade = _blade(read=_error(message=message, status_code=status_code))
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == READ_FAILED.format(message)
        blade.patch_admins_settings.assert_not_called()

    def test_failed_read_without_an_error_text(self):
        module = _module(max_login=7)
        blade = _blade(read=_error(message=None, status_code=503))
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == READ_FAILED.format("Unknown error")
        blade.patch_admins_settings.assert_not_called()

    def test_read_without_settings_fails(self):
        module = _module(max_login=7)
        blade = _blade(read=_valid([]))
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == "The array returned no Global Admin settings."
        blade.patch_admins_settings.assert_not_called()

    def test_read_is_used_when_the_array_answers(self):
        module = _module(check_mode=True, max_login=5, min_password=10, lockout=300)
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        blade.get_admins_settings.assert_called_once_with()
        module.exit_json.assert_called_once_with(changed=False)
        module.fail_json.assert_not_called()


class TestPurefbAdminSettings:
    """Array-level behaviour of the module."""

    def test_module_supports_check_mode(self):
        module = _module()
        run = _run(module, _blade())
        assert run.ansible_module.call_args[1] == {"supports_check_mode": True}

    def test_no_options_changes_nothing(self):
        module = _module()
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        module.exit_json.assert_called_once_with(changed=False)
        blade.patch_admins_settings.assert_not_called()

    def test_current_values_change_nothing(self):
        module = _module(max_login=5, min_password=10, lockout=300)
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        module.exit_json.assert_called_once_with(changed=False)
        blade.patch_admins_settings.assert_not_called()

    def test_max_login_changed_keeps_the_other_settings(self):
        module = _module(max_login=7)
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        blade.patch_admins_settings.assert_called_once_with(
            admin_setting={
                "min_password_length": 10,
                "max_login_attempts": 7,
                "lockout_duration": 300000,
            }
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_min_password_changed_keeps_the_other_settings(self):
        module = _module(min_password=11)
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        blade.patch_admins_settings.assert_called_once_with(
            admin_setting={
                "min_password_length": 11,
                "max_login_attempts": 5,
                "lockout_duration": 300000,
            }
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_lockout_is_sent_in_milliseconds(self):
        module = _module(lockout=120)
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        blade.patch_admins_settings.assert_called_once_with(
            admin_setting={
                "min_password_length": 10,
                "max_login_attempts": 5,
                "lockout_duration": 120000,
            }
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_all_settings_changed(self):
        module = _module(max_login=7, min_password=11, lockout=120)
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        blade.patch_admins_settings.assert_called_once_with(
            admin_setting={
                "min_password_length": 11,
                "max_login_attempts": 7,
                "lockout_duration": 120000,
            }
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_rules_that_are_not_set_stay_unset(self):
        module = _module(min_password=11)
        blade = _blade(read=_valid([_settings(lockout=None, max_login=None)]))
        assert _run(module, blade).outcome == "exit"
        blade.patch_admins_settings.assert_called_once_with(
            admin_setting={
                "min_password_length": 11,
                "max_login_attempts": None,
                "lockout_duration": None,
            }
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_lockout_set_on_an_array_without_one(self):
        module = _module(lockout=300)
        blade = _blade(read=_valid([_settings(lockout=None)]))
        assert _run(module, blade).outcome == "exit"
        blade.patch_admins_settings.assert_called_once_with(
            admin_setting={
                "min_password_length": 10,
                "max_login_attempts": 5,
                "lockout_duration": 300000,
            }
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_check_mode_reports_the_change_without_a_write(self):
        module = _module(check_mode=True, max_login=7)
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        blade.get_admins_settings.assert_called_once_with()
        blade.patch_admins_settings.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_check_mode_with_current_values_is_unchanged(self):
        module = _module(check_mode=True, max_login=5, min_password=10, lockout=300)
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        blade.patch_admins_settings.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_refused_change_reports_the_answer_of_the_array(self):
        module = _module(max_login=7)
        blade = _blade(write=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == CHANGE_FAILED.format(REFUSED)
        blade.patch_admins_settings.assert_called_once()

    @pytest.mark.parametrize("lockout", [0, -1, 7776001])
    def test_lockout_out_of_range_fails_before_the_login(self, lockout):
        module = _module(lockout=lockout)
        blade = _blade()
        run = _run(module, blade)
        assert run.outcome == "fail"
        assert _failure(module) == "Lockout must be between 1 and 7776000 seconds"
        run.get_system.assert_not_called()
        blade.patch_admins_settings.assert_not_called()

    @pytest.mark.parametrize("min_password", [0, -1, 101])
    def test_min_password_out_of_range_fails_before_the_login(self, min_password):
        module = _module(min_password=min_password)
        blade = _blade()
        run = _run(module, blade)
        assert run.outcome == "fail"
        assert _failure(module) == "Minimum password length must be between 1 and 100"
        run.get_system.assert_not_called()
        blade.patch_admins_settings.assert_not_called()

    @pytest.mark.parametrize(
        "lockout, min_password", [(1, 1), (7776000, 100)], ids=["lowest", "highest"]
    )
    def test_range_limits_are_accepted(self, lockout, min_password):
        module = _module(lockout=lockout, min_password=min_password)
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        blade.patch_admins_settings.assert_called_once_with(
            admin_setting={
                "min_password_length": min_password,
                "max_login_attempts": 5,
                "lockout_duration": lockout * 1000,
            }
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_sdk_missing_fails(self):
        module = _module(max_login=7)
        blade = _blade()
        run = _run(module, blade, sdk=False)
        assert run.outcome == "fail"
        assert _failure(module) == "py-pure-client sdk is required for this module"
        run.get_system.assert_not_called()
