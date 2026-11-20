# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_alert module."""

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

from plugins.modules import purefb_alert

MOD = "plugins.modules.purefb_alert"
ADDRESS = "user@example.com"
# The same address as a task may spell it. The array reads and tests an
# alert watcher without regard to the letter case of its address, but
# changes and deletes it only under the spelling it stored.
OTHER_CASE = "User@Example.COM"
REFUSED = "Operation not permitted."
STATES = ["present", "absent", "test"]
LIST_FAILED = "Failed to get existing email list. Error: {0}"
TEST_FAILED = "Failed to test alert email {0}. Error: {1}"
GET_FAILED = "Failed to get information for alert email {0}. Error: {1}"
CREATE_FAILED = "Failed to create alert email {0}. Error: {1}"
DISABLE_FAILED = "Failed to disable during create alert email {0}. Error: {1}"
UPDATE_FAILED = "Failed to update alert email {0}: Error: {1}"
DELETE_FAILED = "Failed to delete alert email {0}. Error: {1}"
NOT_A_WATCHER = (
    "{0} is not an alert watcher of the array: the array tested the "
    "address, but sends no alerts to it."
)
INVALID_ADDRESS = "Valid email address not provided."


class ExitJson(Exception):
    """Raised by the exit_json stand-in: the real one ends the module."""


class FailJson(Exception):
    """Raised by the fail_json stand-in: the real one ends the module."""


def _module(check_mode=False, **params):
    module = Mock()
    module.params = {
        "address": ADDRESS,
        "state": "present",
        "enabled": True,
        "severity": "info",
    }
    module.params.update(params)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=ExitJson)
    module.fail_json = Mock(side_effect=FailJson)
    return module


def _watcher(name=ADDRESS, enabled=True, severity="info"):
    """An alert watcher as the array returns it."""
    return SimpleNamespace(
        id="10000000-0000-4000-8000-000000000001",
        name=name,
        enabled=enabled,
        minimum_notification_severity=severity,
    )


def _component(destination=ADDRESS, watcher=None, **fields):
    """One result of an alert email test, as the array returns it.

    The destination is the address as the request spelled it and the
    resource is the alert watcher under its stored name. For an address
    that is not an alert watcher the array sends the email all the same,
    names no resource and reports enabled false.
    """
    resource = None
    enabled = False
    if watcher is not None:
        resource = SimpleNamespace(
            id=watcher.id, name=watcher.name, resource_type="alert-watchers"
        )
        enabled = watcher.enabled
    component = SimpleNamespace(
        component_address="192.0.2.1",
        component_name="FM1",
        description="Send a test email to a registered alert watcher.",
        destination=destination,
        enabled=enabled,
        resource=resource,
        result_details=(
            "Test email sent successfully! Please check the inbox of "
            "{0}.".format(destination)
        ),
        success=True,
        test_type="send-test-email",
    )
    for field, value in fields.items():
        setattr(component, field, value)
    return component


def _reported(destination=ADDRESS, resource_name=ADDRESS, **fields):
    """What the module returns for one test result."""
    reported = {
        "component_address": "192.0.2.1",
        "component_name": "FM1",
        "description": "Send a test email to a registered alert watcher.",
        "destination": destination,
        "enabled": "true",
        "result_details": (
            "Test email sent successfully! Please check the inbox of "
            "{0}.".format(destination)
        ),
        "success": "true",
        "test_type": "send-test-email",
        "resource_name": resource_name,
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


def _blade(watchers=(), **answers):
    """An array that holds the given alert watchers.

    Like the array it reads and tests a watcher without regard to the
    letter case of the address, refuses a second watcher on an address it
    holds, tests any address, and changes and deletes a watcher only under
    the spelling it stored. The keywords listing, read, test, post, patch
    and delete replace the answer to the list of the watchers, to the read
    of one watcher by name, to the test and to the POST, the PATCH and the
    DELETE.
    """
    watchers = list(watchers)
    blade = Mock()

    def find(name):
        for watcher in watchers:
            if watcher.name.lower() == name.lower():
                return watcher
        return None

    def missing(name):
        """The refusal of a PATCH or a DELETE, None when the name is stored."""
        watcher = find(name)
        if watcher is None:
            return _error("Alert watcher does not exist.")
        if watcher.name != name:
            return _error("Watcher {0} does not exist.".format(name))
        return None

    def get_alert_watchers(names=None):
        if names is None:
            return answers.get("listing") or _valid(watchers)
        if "read" in answers:
            return answers["read"]
        watcher = find(names[0])
        if watcher is None:
            return _error("Alert watcher does not exist.")
        return _valid([watcher])

    def get_alert_watchers_test(names=None):
        if "test" in answers:
            return answers["test"]
        return _valid([_component(names[0], find(names[0]))])

    def post_alert_watchers(names=None, alert_watcher=None):
        if "post" in answers:
            return answers["post"]
        if find(names[0]) is not None:
            return _error("Alert watcher already exists.")
        watchers.append(_watcher(names[0]))
        return _valid([watchers[-1]])

    def patch_alert_watchers(names=None, alert_watcher=None):
        if "patch" in answers:
            return answers["patch"]
        return missing(names[0]) or _valid([find(names[0])])

    def delete_alert_watchers(names=None):
        if "delete" in answers:
            return answers["delete"]
        return missing(names[0]) or _valid([])

    blade.get_alert_watchers.side_effect = get_alert_watchers
    blade.get_alert_watchers_test.side_effect = get_alert_watchers_test
    blade.post_alert_watchers.side_effect = post_alert_watchers
    blade.patch_alert_watchers.side_effect = patch_alert_watchers
    blade.delete_alert_watchers.side_effect = delete_alert_watchers
    return blade


def _run(module, blade, sdk=True):
    """Run main() against the stand-ins and return how the module ended.

    The SDK models are replaced by functions that return their name and
    their keyword arguments, so the body of a POST or a PATCH can be
    compared.
    """
    with ExitStack() as stack:
        stack.enter_context(patch(MOD + ".AnsibleModule", return_value=module))
        stack.enter_context(patch(MOD + ".purefb_argument_spec", return_value={}))
        stack.enter_context(patch(MOD + ".get_system", return_value=blade))
        stack.enter_context(
            patch(MOD + ".get_error_message", side_effect=_error_message)
        )
        stack.enter_context(patch(MOD + ".HAS_PYPURECLIENT", sdk))
        stack.enter_context(
            patch(
                MOD + ".AlertWatcherPost",
                side_effect=lambda **kwargs: ("AlertWatcherPost", kwargs),
            )
        )
        stack.enter_context(
            patch(
                MOD + ".AlertWatcher",
                side_effect=lambda **kwargs: ("AlertWatcher", kwargs),
            )
        )
        outcome = None
        try:
            purefb_alert.main()
        except ExitJson:
            outcome = "exit"
        except FailJson:
            outcome = "fail"
    assert outcome is not None, "main() ended without exit_json or fail_json"
    return outcome


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
    blade.post_alert_watchers.assert_not_called()
    blade.patch_alert_watchers.assert_not_called()
    blade.delete_alert_watchers.assert_not_called()


def _nothing_sent(blade):
    """No write, and no test email either."""
    _no_write(blade)
    blade.get_alert_watchers_test.assert_not_called()


class TestPurefbAlertRefusedList:
    """A list of the alert watchers the array refuses or fails is reported."""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("state", STATES)
    def test_refused_list_reports_the_answer_of_the_array(self, state, check_mode):
        """An identity that may not read the alert watchers is refused."""
        module = _module(check_mode=check_mode, state=state)
        blade = _blade([_watcher()], listing=_error())
        assert _run(module, blade) == "fail"
        assert _failure(module) == LIST_FAILED.format(REFUSED)
        blade.get_alert_watchers.assert_called_once_with()
        _nothing_sent(blade)

    @pytest.mark.parametrize("status_code", [429, 500, 503])
    @pytest.mark.parametrize("state", STATES)
    def test_failed_list_without_a_message(self, state, status_code):
        """An answer that carries no error message is reported all the same."""
        module = _module(state=state)
        blade = _blade([_watcher()], listing=_error(None, status_code=status_code))
        assert _run(module, blade) == "fail"
        assert _failure(module) == LIST_FAILED.format("Unknown error")
        _nothing_sent(blade)


class TestPurefbAlertTest:
    """state=test asks the array for the test and returns its results."""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("watchers", [[], [_watcher()]])
    def test_refused_test_reports_the_answer_of_the_array(self, watchers, check_mode):
        """The watchers were listed, the test itself is refused."""
        module = _module(check_mode=check_mode, state="test")
        blade = _blade(watchers, test=_error())
        assert _run(module, blade) == "fail"
        assert _failure(module) == TEST_FAILED.format(ADDRESS, REFUSED)
        blade.get_alert_watchers_test.assert_called_once_with(names=[ADDRESS])
        module.warn.assert_not_called()
        _no_write(blade)

    @pytest.mark.parametrize("status_code", [429, 500, 503])
    def test_failed_test_without_a_message(self, status_code):
        module = _module(state="test")
        blade = _blade([_watcher()], test=_error(None, status_code=status_code))
        assert _run(module, blade) == "fail"
        assert _failure(module) == TEST_FAILED.format(ADDRESS, "Unknown error")
        _no_write(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_results_of_a_watcher_are_returned(self, check_mode):
        module = _module(check_mode=check_mode, state="test")
        blade = _blade([_watcher("other@example.com"), _watcher()])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": False, "test_response": [_reported()]}
        blade.get_alert_watchers_test.assert_called_once_with(names=[ADDRESS])
        module.warn.assert_not_called()
        _no_write(blade)

    def test_results_of_a_disabled_watcher_are_returned(self):
        """The array tests a watcher that is disabled and says so."""
        module = _module(state="test")
        blade = _blade([_watcher(enabled=False)])
        assert _run(module, blade) == "exit"
        assert _result(module) == {
            "changed": False,
            "test_response": [_reported(enabled="false")],
        }
        module.warn.assert_not_called()
        _no_write(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("watchers", [[], [_watcher("other@example.com")]])
    def test_address_that_is_not_a_watcher(self, watchers, check_mode):
        """The array tests the address and names no resource in the result."""
        module = _module(check_mode=check_mode, state="test")
        blade = _blade(watchers)
        assert _run(module, blade) == "exit"
        assert _result(module) == {
            "changed": False,
            "test_response": [_reported(enabled="false", resource_name="")],
        }
        blade.get_alert_watchers_test.assert_called_once_with(names=[ADDRESS])
        module.warn.assert_called_once_with(NOT_A_WATCHER.format(ADDRESS))
        _no_write(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_watcher_in_another_letter_case(self, check_mode):
        """The watcher is tested under its stored address, with no warning."""
        module = _module(check_mode=check_mode, state="test", address=OTHER_CASE)
        blade = _blade([_watcher()])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": False, "test_response": [_reported()]}
        blade.get_alert_watchers_test.assert_called_once_with(names=[ADDRESS])
        module.warn.assert_not_called()
        _no_write(blade)

    def test_refused_test_names_the_stored_address(self):
        module = _module(state="test", address=OTHER_CASE)
        blade = _blade([_watcher()], test=_error())
        assert _run(module, blade) == "fail"
        assert _failure(module) == TEST_FAILED.format(ADDRESS, REFUSED)
        blade.get_alert_watchers_test.assert_called_once_with(names=[ADDRESS])
        _no_write(blade)

    def test_every_component_is_returned(self):
        """A test that did not succeed on a component is a result."""
        watcher = _watcher()
        failed = _component(
            watcher=watcher,
            component_name="FM2",
            success=False,
            result_details="Failed to send the test email.",
        )
        module = _module(state="test")
        blade = _blade([watcher], test=_valid([_component(watcher=watcher), failed]))
        assert _run(module, blade) == "exit"
        assert _result(module) == {
            "changed": False,
            "test_response": [
                _reported(),
                _reported(
                    component_name="FM2",
                    success="false",
                    result_details="Failed to send the test email.",
                ),
            ],
        }

    def test_no_component_is_an_empty_result(self):
        module = _module(state="test")
        blade = _blade([_watcher()], test=_valid([]))
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": False, "test_response": []}


class TestPurefbAlertLetterCase:
    """An address in another letter case names the watcher the array holds.

    The watcher is read, changed and deleted under the address the array
    stored: the array refuses a PATCH or a DELETE in another spelling.
    """

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_present_with_the_same_settings_is_unchanged(self, check_mode):
        module = _module(check_mode=check_mode, address=OTHER_CASE)
        blade = _blade([_watcher()])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": False}
        blade.get_alert_watchers.assert_called_with(names=[ADDRESS])
        _nothing_sent(blade)

    def test_present_with_other_settings_updates_the_watcher(self):
        module = _module(address=OTHER_CASE, severity="critical", enabled=False)
        blade = _blade([_watcher()])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": True}
        blade.post_alert_watchers.assert_not_called()
        blade.patch_alert_watchers.assert_called_once_with(
            names=[ADDRESS],
            alert_watcher=(
                "AlertWatcher",
                {"enabled": False, "minimum_notification_severity": "critical"},
            ),
        )

    def test_present_in_check_mode_reports_the_update(self):
        module = _module(check_mode=True, address=OTHER_CASE, severity="critical")
        blade = _blade([_watcher()])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": True}
        blade.get_alert_watchers.assert_called_with(names=[ADDRESS])
        _nothing_sent(blade)

    def test_refused_update_names_the_stored_address(self):
        module = _module(address=OTHER_CASE, severity="critical")
        blade = _blade([_watcher()], patch=_error())
        assert _run(module, blade) == "fail"
        assert _failure(module) == UPDATE_FAILED.format(ADDRESS, REFUSED)

    def test_absent_deletes_the_watcher(self):
        module = _module(address=OTHER_CASE, state="absent")
        blade = _blade([_watcher()])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": True}
        blade.delete_alert_watchers.assert_called_once_with(names=[ADDRESS])

    def test_absent_in_check_mode_reports_the_delete(self):
        module = _module(check_mode=True, address=OTHER_CASE, state="absent")
        blade = _blade([_watcher()])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": True}
        _nothing_sent(blade)

    def test_watcher_stored_in_mixed_case(self):
        """The stored spelling is used whatever it is."""
        module = _module(state="absent")
        blade = _blade([_watcher(OTHER_CASE)])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": True}
        blade.delete_alert_watchers.assert_called_once_with(names=[OTHER_CASE])

    @pytest.mark.parametrize(
        "stored,address,found",
        [
            (ADDRESS, ADDRESS, ADDRESS),
            (ADDRESS, OTHER_CASE, ADDRESS),
            (OTHER_CASE, ADDRESS, OTHER_CASE),
            (ADDRESS, "other@example.com", None),
            (ADDRESS, "user@example.org", None),
        ],
    )
    def test_stored_address(self, stored, address, found):
        watchers = [_watcher("first@example.com"), _watcher(stored)]
        assert purefb_alert._stored_address(watchers, address) == found

    def test_stored_address_without_watchers(self):
        assert purefb_alert._stored_address([], ADDRESS) is None


class TestPurefbAlertResourceName:
    """The watcher a test result refers to."""

    def test_watcher(self):
        component = _component(watcher=_watcher())
        assert purefb_alert._resource_name(component) == ADDRESS

    def test_address_that_is_not_a_watcher(self):
        assert purefb_alert._resource_name(_component()) == ""

    def test_result_without_the_field(self):
        assert purefb_alert._resource_name(SimpleNamespace()) == ""


class TestPurefbAlertPresent:
    """state=present creates the watcher or brings it to the settings asked."""

    def test_create(self):
        module = _module(severity="warning")
        blade = _blade([_watcher("other@example.com")])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": True}
        blade.post_alert_watchers.assert_called_once_with(
            names=[ADDRESS],
            alert_watcher=(
                "AlertWatcherPost",
                {"minimum_notification_severity": "warning"},
            ),
        )
        blade.patch_alert_watchers.assert_not_called()
        blade.delete_alert_watchers.assert_not_called()

    def test_create_disabled(self):
        """The watcher is created and then disabled."""
        module = _module(enabled=False)
        blade = _blade()
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": True}
        blade.post_alert_watchers.assert_called_once_with(
            names=[ADDRESS],
            alert_watcher=(
                "AlertWatcherPost",
                {"minimum_notification_severity": "info"},
            ),
        )
        blade.patch_alert_watchers.assert_called_once_with(
            names=[ADDRESS], alert_watcher=("AlertWatcher", {"enabled": False})
        )

    @pytest.mark.parametrize("enabled", [True, False])
    def test_create_in_check_mode(self, enabled):
        module = _module(check_mode=True, enabled=enabled)
        blade = _blade()
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": True}
        _nothing_sent(blade)

    def test_create_refused(self):
        module = _module()
        blade = _blade(post=_error())
        assert _run(module, blade) == "fail"
        assert _failure(module) == CREATE_FAILED.format(ADDRESS, REFUSED)

    def test_disable_after_create_refused(self):
        module = _module(enabled=False)
        blade = _blade(patch=_error())
        assert _run(module, blade) == "fail"
        assert _failure(module) == DISABLE_FAILED.format(ADDRESS, REFUSED)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_same_settings_are_unchanged(self, check_mode):
        module = _module(check_mode=check_mode, severity="warning", enabled=False)
        blade = _blade([_watcher(enabled=False, severity="warning")])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": False}
        _nothing_sent(blade)

    @pytest.mark.parametrize(
        "params,body",
        [
            (
                {"severity": "critical"},
                {"enabled": True, "minimum_notification_severity": "critical"},
            ),
            (
                {"enabled": False},
                {"enabled": False, "minimum_notification_severity": "info"},
            ),
            (
                {"enabled": False, "severity": "warning"},
                {"enabled": False, "minimum_notification_severity": "warning"},
            ),
        ],
    )
    def test_update(self, params, body):
        module = _module(**params)
        blade = _blade([_watcher()])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": True}
        blade.patch_alert_watchers.assert_called_once_with(
            names=[ADDRESS], alert_watcher=("AlertWatcher", body)
        )
        blade.post_alert_watchers.assert_not_called()
        blade.delete_alert_watchers.assert_not_called()

    def test_update_in_check_mode(self):
        module = _module(check_mode=True, severity="critical")
        blade = _blade([_watcher()])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": True}
        _nothing_sent(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_refused_read_of_the_watcher(self, check_mode):
        """The watchers were listed, the read of the one watcher is refused."""
        module = _module(check_mode=check_mode, severity="critical")
        blade = _blade([_watcher()], read=_error())
        assert _run(module, blade) == "fail"
        assert _failure(module) == GET_FAILED.format(ADDRESS, REFUSED)
        _nothing_sent(blade)

    def test_update_refused(self):
        module = _module(severity="critical")
        blade = _blade([_watcher()], patch=_error())
        assert _run(module, blade) == "fail"
        assert _failure(module) == UPDATE_FAILED.format(ADDRESS, REFUSED)


class TestPurefbAlertAbsent:
    """state=absent deletes the watcher."""

    def test_delete(self):
        module = _module(state="absent")
        blade = _blade([_watcher("other@example.com"), _watcher()])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": True}
        blade.delete_alert_watchers.assert_called_once_with(names=[ADDRESS])
        blade.post_alert_watchers.assert_not_called()
        blade.patch_alert_watchers.assert_not_called()

    def test_delete_in_check_mode(self):
        module = _module(check_mode=True, state="absent")
        blade = _blade([_watcher()])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": True}
        _nothing_sent(blade)

    def test_delete_refused(self):
        module = _module(state="absent")
        blade = _blade([_watcher()], delete=_error())
        assert _run(module, blade) == "fail"
        assert _failure(module) == DELETE_FAILED.format(ADDRESS, REFUSED)

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("watchers", [[], [_watcher("other@example.com")]])
    def test_address_that_is_not_a_watcher_is_unchanged(self, watchers, check_mode):
        module = _module(check_mode=check_mode, state="absent")
        blade = _blade(watchers)
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": False}
        _nothing_sent(blade)


class TestPurefbAlertBeforeTheArray:
    """Failures the module reports before it contacts the array."""

    @pytest.mark.parametrize(
        "address",
        [
            "user",
            "user@example",
            "user example@example.com",
            # Alert watchers have no realm form: a realm-style name is not
            # an email address.
            "realm1::user@example.com",
            "user@realm1::example.com",
        ],
    )
    @pytest.mark.parametrize("state", STATES)
    def test_invalid_address(self, state, address):
        module = _module(state=state, address=address)
        blade = _blade([_watcher()])
        assert _run(module, blade) == "fail"
        assert _failure(module) == INVALID_ADDRESS
        assert blade.mock_calls == []

    def test_sdk_missing(self):
        module = _module()
        blade = _blade()
        assert _run(module, blade, sdk=False) == "fail"
        assert _failure(module) == "py-pure-client SDK is required for this module"
        assert blade.mock_calls == []
