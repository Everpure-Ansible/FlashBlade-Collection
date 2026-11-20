# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_ra module."""

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
sys.modules["ansible_collections.everpure.flashblade.plugins.module_utils.version"] = (
    MagicMock()
)

from plugins.module_utils.version import LooseVersion as RealLooseVersion
from plugins.modules.purefb_ra import main

MOD = "plugins.modules.purefb_ra"
REFUSED = "Operation not permitted."
READ_FAILED = "Failed to read the support settings. Error: {0}"
NO_SETTINGS = "The array returned no support settings."
TEST_FAILED = "Testing Remote Assist failed. Error: {0}"
ENABLE_FAILED = "Enabling Remote Assist failed. Error: {0}"
DISABLE_FAILED = "Disabling Remote Assist failed. Error: {0}"
HOUR = 3600000
STATES = ["present", "absent", "test"]


class ExitJson(Exception):
    """Raised by the exit_json stand-in: the real one ends the module."""


class FailJson(Exception):
    """Raised by the fail_json stand-in: the real one ends the module."""


def _module(check_mode=False, **params):
    module = Mock()
    module.params = {"state": "present", "duration": 24}
    module.params.update(params)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=ExitJson)
    module.fail_json = Mock(side_effect=FailJson)
    return module


def _support(active=True):
    """The single support object of an array, with or without a session.

    The module reads remote_assist_active only; the other fields are those
    of the Support model, with the session fields left unset while no
    session is open.
    """
    support = SimpleNamespace(
        id="10000000-0000-4000-8000-000000000001",
        name="fb-array",
        edge_agent_update_enabled=False,
        edge_management_enabled=False,
        phonehome_enabled=True,
        proxy=None,
        remote_assist_active=active,
        remote_assist_duration=None,
        remote_assist_expires=None,
        remote_assist_opened=None,
        remote_assist_paths=[
            SimpleNamespace(component_name="FM1", status="disconnected"),
            SimpleNamespace(component_name="FM2", status="disconnected"),
        ],
        remote_assist_status="disconnected",
    )
    if active:
        support.remote_assist_duration = 48 * HOUR
        support.remote_assist_opened = 1790000000000
        support.remote_assist_expires = 1790000000000 + 48 * HOUR
        support.remote_assist_paths = [
            SimpleNamespace(component_name="FM1", status="connected"),
            SimpleNamespace(component_name="FM2", status="connected"),
        ]
        support.remote_assist_status = "connected"
    return support


def _component(name, **fields):
    """One Remote Assist test result of a fabric module.

    The array names the component, the test and its outcome; it sets neither
    an address nor a destination, and no details when the test succeeds.
    """
    component = SimpleNamespace(
        component_address=None,
        component_name=name,
        description="Testing remote-assist connectivity",
        destination=None,
        enabled=None,
        resource=None,
        result_details=None,
        success=True,
        test_type="remote-assist",
    )
    for field, value in fields.items():
        setattr(component, field, value)
    return component


def _reported(name, **fields):
    """What the module returns for one test result."""
    reported = {
        "component_address": None,
        "component_name": name,
        "description": "Testing remote-assist connectivity",
        "destination": None,
        "enabled": "false",
        "result_details": None,
        "success": "true",
        "test_type": "remote-assist",
    }
    reported.update(fields)
    return reported


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


def _blade(active=True, read=None, test=None, write=None):
    """An array with (active) or without an open Remote Assist session.

    read, test and write replace the answer to the read of the support
    settings, to the Remote Assist test and to the PATCH of the settings.
    """
    blade = Mock()
    blade.get_support.return_value = (
        read if read is not None else _valid([_support(active)])
    )
    blade.get_support_test.return_value = (
        test if test is not None else _valid([_component("FM1"), _component("FM2")])
    )
    blade.patch_support.return_value = (
        write if write is not None else _valid([_support(not active)])
    )
    return blade


def _run(module, blade, api_version="2.30", sdk=True):
    """Run main() against the stand-ins and return how the module ended.

    Support is replaced by a function that returns its keyword arguments, so
    the body of a PATCH can be compared.
    """
    with ExitStack() as stack:
        ansible_module = stack.enter_context(
            patch(MOD + ".AnsibleModule", return_value=module)
        )
        stack.enter_context(patch(MOD + ".purefb_argument_spec", return_value={}))
        stack.enter_context(patch(MOD + ".get_system", return_value=blade))
        stack.enter_context(
            patch(MOD + ".get_error_message", side_effect=_error_message)
        )
        rest_version = stack.enter_context(
            patch(MOD + ".get_rest_api_version", return_value=api_version)
        )
        stack.enter_context(patch(MOD + ".LooseVersion", RealLooseVersion))
        stack.enter_context(patch(MOD + ".HAS_PYPURECLIENT", sdk))
        stack.enter_context(
            patch(MOD + ".Support", side_effect=lambda **kwargs: kwargs)
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
        outcome=outcome, ansible_module=ansible_module, rest_version=rest_version
    )


def _failure(module):
    """The message of the single fail_json call of a run that failed."""
    module.fail_json.assert_called_once()
    module.exit_json.assert_not_called()
    return module.fail_json.call_args[1]["msg"]


def _result(module):
    """The keyword arguments of the single exit_json call of a run."""
    module.exit_json.assert_called_once()
    module.fail_json.assert_not_called()
    return module.exit_json.call_args[1]


def _no_write(blade):
    blade.patch_support.assert_not_called()


class TestPurefbRaRefusedRead:
    """A read of the support settings the array refuses or fails is reported."""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("state", STATES)
    def test_refused_read_reports_the_answer_of_the_array(self, state, check_mode):
        """An identity that may not read the support settings is refused."""
        module = _module(check_mode=check_mode, state=state)
        blade = _blade(read=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == READ_FAILED.format(REFUSED)
        blade.get_support.assert_called_once_with()
        blade.get_support_test.assert_not_called()
        _no_write(blade)

    @pytest.mark.parametrize("status_code", [429, 500, 503])
    @pytest.mark.parametrize("state", STATES)
    def test_failed_read_without_a_message(self, state, status_code):
        """An answer that carries no error message is reported all the same."""
        module = _module(state=state)
        blade = _blade(read=_error(None, status_code=status_code))
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == READ_FAILED.format("Unknown error")
        blade.get_support_test.assert_not_called()
        _no_write(blade)

    @pytest.mark.parametrize("state", STATES)
    def test_read_that_returns_no_settings(self, state):
        module = _module(state=state)
        blade = _blade(read=_valid([]))
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == NO_SETTINGS
        blade.get_support_test.assert_not_called()
        _no_write(blade)


class TestPurefbRaTest:
    """state=test runs the Remote Assist test and returns its results."""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("active", [True, False])
    def test_refused_test_reports_the_answer_of_the_array(self, active, check_mode):
        """The settings were read, the test itself is refused."""
        module = _module(check_mode=check_mode, state="test")
        blade = _blade(active=active, test=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == TEST_FAILED.format(REFUSED)
        blade.get_support_test.assert_called_once_with(test_type="remote-assist")
        _no_write(blade)

    @pytest.mark.parametrize("status_code", [429, 500, 503])
    def test_failed_test_without_a_message(self, status_code):
        module = _module(state="test")
        blade = _blade(test=_error(None, status_code=status_code))
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == TEST_FAILED.format("Unknown error")
        _no_write(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("active", [True, False])
    def test_results_are_returned(self, active, check_mode):
        """The test is a read: it runs in check mode and changes nothing."""
        module = _module(check_mode=check_mode, state="test")
        blade = _blade(active=active)
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {
            "changed": False,
            "test_response": [_reported("FM1"), _reported("FM2")],
        }
        blade.get_support_test.assert_called_once_with(test_type="remote-assist")
        _no_write(blade)

    def test_flags_are_returned_as_text(self):
        module = _module(state="test")
        failed = _component(
            "FM2",
            component_address="192.0.2.10",
            destination="ra.example.com",
            enabled=True,
            result_details="Connection timed out",
            success=False,
        )
        blade = _blade(test=_valid([_component("FM1", enabled=False), failed]))
        assert _run(module, blade).outcome == "exit"
        assert _result(module)["test_response"] == [
            _reported("FM1"),
            _reported(
                "FM2",
                component_address="192.0.2.10",
                destination="ra.example.com",
                enabled="true",
                result_details="Connection timed out",
                success="false",
            ),
        ]

    def test_result_without_details(self):
        """A result object that has no result_details reports an empty text."""
        module = _module(state="test")
        component = _component("FM1")
        del component.result_details
        blade = _blade(test=_valid([component]))
        assert _run(module, blade).outcome == "exit"
        assert _result(module)["test_response"] == [_reported("FM1", result_details="")]

    def test_no_results(self):
        module = _module(state="test")
        blade = _blade(test=_valid([]))
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": False, "test_response": []}


class TestPurefbRaEnable:
    """state=present opens a session when none is open."""

    def test_session_is_opened_for_the_default_duration(self):
        module = _module()
        blade = _blade(active=False)
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        blade.patch_support.assert_called_once_with(
            support={
                "remote_assist_active": True,
                "remote_assist_duration": 24 * HOUR,
            }
        )
        blade.get_support_test.assert_not_called()

    def test_duration_is_sent_in_milliseconds(self):
        module = _module(duration=1)
        blade = _blade(active=False)
        assert _run(module, blade).outcome == "exit"
        blade.patch_support.assert_called_once_with(
            support={"remote_assist_active": True, "remote_assist_duration": HOUR}
        )

    @pytest.mark.parametrize(
        "api_version, body",
        [
            ("2.13", {"remote_assist_active": True}),
            ("2.14", {"remote_assist_active": True, "remote_assist_duration": HOUR}),
        ],
    )
    def test_duration_needs_rest_2_14(self, api_version, body):
        module = _module(duration=1)
        blade = _blade(active=False)
        assert _run(module, blade, api_version=api_version).outcome == "exit"
        assert _result(module) == {"changed": True}
        blade.patch_support.assert_called_once_with(support=body)

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("duration", [24, 1])
    def test_open_session_is_left_alone(self, duration, check_mode):
        module = _module(check_mode=check_mode, duration=duration)
        blade = _blade(active=True)
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": False}
        _no_write(blade)

    def test_check_mode_sends_no_write(self):
        module = _module(check_mode=True)
        blade = _blade(active=False)
        run = _run(module, blade)
        assert run.outcome == "exit"
        assert _result(module) == {"changed": True}
        _no_write(blade)
        run.rest_version.assert_not_called()

    def test_refused_write_reports_the_answer_of_the_array(self):
        module = _module()
        blade = _blade(active=False, write=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == ENABLE_FAILED.format(REFUSED)
        blade.patch_support.assert_called_once()


class TestPurefbRaDisable:
    """state=absent closes the open session."""

    def test_session_is_closed(self):
        module = _module(state="absent")
        blade = _blade(active=True)
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        blade.patch_support.assert_called_once_with(
            support={"remote_assist_active": False}
        )
        blade.get_support_test.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_closed_session_is_left_alone(self, check_mode):
        module = _module(check_mode=check_mode, state="absent")
        blade = _blade(active=False)
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": False}
        _no_write(blade)

    def test_check_mode_sends_no_write(self):
        module = _module(check_mode=True, state="absent")
        blade = _blade(active=True)
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        _no_write(blade)

    def test_refused_write_reports_the_answer_of_the_array(self):
        module = _module(state="absent")
        blade = _blade(active=True, write=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == DISABLE_FAILED.format(REFUSED)
        blade.patch_support.assert_called_once()


class TestPurefbRaMain:
    """The argument specification and the SDK guard."""

    def test_argument_spec(self):
        module = _module()
        run = _run(module, _blade())
        args, kwargs = run.ansible_module.call_args
        assert args[0] == {
            "state": {
                "type": "str",
                "default": "present",
                "choices": ["present", "absent", "test"],
            },
            "duration": {"type": "int", "default": 24},
        }
        assert kwargs == {"supports_check_mode": True}

    def test_missing_sdk(self):
        module = _module()
        blade = _blade()
        assert _run(module, blade, sdk=False).outcome == "fail"
        assert _failure(module) == "pypureclient SDK is required for this module"
        blade.get_support.assert_not_called()
        _no_write(blade)
