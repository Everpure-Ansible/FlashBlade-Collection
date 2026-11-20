# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_snmp_mgr module."""

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

from plugins.modules.purefb_snmp_mgr import main, _readable

MOD = "plugins.modules.purefb_snmp_mgr"
REFUSED = "Operation not permitted."
MASKED = "****"
LIST_FAILED = "Failed to list SNMP managers. Error: {0}"
TEST_FAILED = "Failed to test SNMP manager {0}. Error: {1}"
GET_FAILED = "Failed to get configuration for SNMP manager {0}. Error: {1}"
NOT_CONFIGURED = "SNMP Manager {0} not configured"
CREATE_FAILED = "Failed to create {0} SNMP manager manager1. Error: {1}"
UPDATE_FAILED = "Failed to update {0} SNMP manager manager1. Error: {1}"
DELETE_FAILED = "Delete SNMP manager manager1 failed. Error: {0}"
AUTH_LENGTH = "auth_password must be between 8 and 32 characters"
PRIVACY_LENGTH = "privacy_password must be between 8 and 63 characters"
STATES = ["present", "absent", "test"]
# Names under which the array does not return the manager "manager1":
# another name, another spelling (a read by name is exact) and a
# realm-style name (SNMP managers have no realm form).
OTHER_NAMES = ["manager2", "MANAGER1", "realm1::manager1"]
EXISTS = "Manager {0} already exists."


class ExitJson(Exception):
    """Raised by the exit_json stand-in: the real one ends the module."""


class FailJson(Exception):
    """Raised by the fail_json stand-in: the real one ends the module."""


def _module(check_mode=False, **params):
    module = Mock()
    module.params = {
        "name": "manager1",
        "state": "present",
        "host": None,
        "user": None,
        "notification": "trap",
        "auth_passphrase": None,
        "auth_protocol": None,
        "privacy_passphrase": None,
        "privacy_protocol": None,
        "version": None,
        "community": None,
    }
    module.params.update(params)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=ExitJson)
    module.fail_json = Mock(side_effect=FailJson)
    return module


def _v2c_manager(name="manager1", host="192.0.2.10", notification="trap"):
    """A v2c manager as the array returns it.

    The community string comes back masked and the v3 block is empty.
    """
    return SimpleNamespace(
        id="10000000-0000-4000-8000-000000000001",
        name=name,
        host=host,
        notification=notification,
        v2c=SimpleNamespace(community=MASKED),
        v3=SimpleNamespace(),
        version="v2c",
    )


def _v3_manager(name="manager1", host="192.0.2.12", notification="trap"):
    """A v3 manager as the array returns it.

    The passphrases come back masked and the v2c block is empty.
    """
    return SimpleNamespace(
        id="10000000-0000-4000-8000-000000000003",
        name=name,
        host=host,
        notification=notification,
        v2c=SimpleNamespace(),
        v3=SimpleNamespace(
            auth_passphrase=MASKED,
            auth_protocol="SHA",
            privacy_passphrase=MASKED,
            privacy_protocol="AES",
            user="snmpuser",
        ),
        version="v3",
    )


def _component(name="manager1", **fields):
    """The result of a manager test: a test trap sent by a fabric module."""
    component = SimpleNamespace(
        component_address="192.0.2.1",
        component_name="FM1",
        description="Send a test trap to a manager",
        destination="192.0.2.10",
        enabled=True,
        resource=SimpleNamespace(name=name),
        result_details=(
            "Test trap sent to '{0}'. Check the remote machine to ensure it "
            "was correctly delivered.".format(name)
        ),
        success=True,
        test_type="message-sending",
    )
    for field, value in fields.items():
        setattr(component, field, value)
    return component


def _reported(name="manager1", **fields):
    """What the module returns for one test result."""
    reported = {
        "component_address": "192.0.2.1",
        "component_name": "FM1",
        "description": "Send a test trap to a manager",
        "destination": "192.0.2.10",
        "enabled": "true",
        "result_details": (
            "Test trap sent to '{0}'. Check the remote machine to ensure it "
            "was correctly delivered.".format(name)
        ),
        "success": "true",
        "test_type": "message-sending",
        "resource_name": name,
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


def _blade(managers=(), listing=None, read=None, test=None, write=None):
    """An array that holds the given SNMP managers.

    listing, read, test and write replace the answer to the list of the
    managers, to the read of one manager by name, to the manager test and
    to every POST, PATCH and DELETE.

    A manager is read by the exact spelling of its name, and the names are
    unique without regard to case: a create of another spelling of a name
    the array holds is refused.
    """
    managers = list(managers)
    blade = Mock()

    def post_snmp_managers(names=None, snmp_manager=None):
        if write is not None:
            return write
        for mgr in managers:
            if mgr.name.lower() == names[0].lower():
                return _error(EXISTS.format(mgr.name))
        return _valid([])

    def get_snmp_managers(names=None):
        if names is None:
            return listing if listing is not None else _valid(managers)
        if read is not None:
            return read
        found = [mgr for mgr in managers if mgr.name in names]
        if len(found) != len(names):
            return _error("Manager {0} does not exist.".format(names[0]))
        return _valid(found)

    blade.get_snmp_managers.side_effect = get_snmp_managers
    blade.get_snmp_managers_test.return_value = (
        test if test is not None else _valid([_component()])
    )
    blade.post_snmp_managers.side_effect = post_snmp_managers
    for call in ("patch_snmp_managers", "delete_snmp_managers"):
        getattr(blade, call).return_value = write if write is not None else _valid([])
    return blade


def _run(module, blade, sdk=True):
    """Run main() against the stand-ins and return how the module ended.

    The SDK models are replaced by functions that return their keyword
    arguments, so the body of a POST or a PATCH can be compared.
    """
    with ExitStack() as stack:
        stack.enter_context(patch(MOD + ".AnsibleModule", return_value=module))
        stack.enter_context(patch(MOD + ".purefb_argument_spec", return_value={}))
        stack.enter_context(patch(MOD + ".get_system", return_value=blade))
        stack.enter_context(
            patch(MOD + ".get_error_message", side_effect=_error_message)
        )
        stack.enter_context(patch(MOD + ".HAS_PYPURECLIENT", sdk))
        for model in ("SnmpManager", "SnmpV2c", "SnmpV3"):
            stack.enter_context(
                patch(MOD + "." + model, side_effect=lambda **kwargs: kwargs)
            )
        outcome = None
        try:
            main()
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
    blade.post_snmp_managers.assert_not_called()
    blade.patch_snmp_managers.assert_not_called()
    blade.delete_snmp_managers.assert_not_called()


def _nothing_sent(blade):
    """No write, and no test trap either."""
    _no_write(blade)
    blade.get_snmp_managers_test.assert_not_called()


class TestPurefbSnmpMgrRefusedList:
    """A list of the SNMP managers the array refuses or fails is reported."""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("state", STATES)
    def test_refused_list_reports_the_answer_of_the_array(self, state, check_mode):
        """An identity that may not read the SNMP managers is refused."""
        module = _module(check_mode=check_mode, state=state)
        blade = _blade(listing=_error())
        assert _run(module, blade) == "fail"
        assert _failure(module) == LIST_FAILED.format(REFUSED)
        blade.get_snmp_managers.assert_called_once_with()
        _nothing_sent(blade)

    @pytest.mark.parametrize("status_code", [429, 500, 503])
    @pytest.mark.parametrize("state", STATES)
    def test_failed_list_without_a_message(self, state, status_code):
        """An answer that carries no error message is reported all the same."""
        module = _module(state=state)
        blade = _blade(listing=_error(None, status_code=status_code))
        assert _run(module, blade) == "fail"
        assert _failure(module) == LIST_FAILED.format("Unknown error")
        _nothing_sent(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("state", STATES)
    def test_refused_list_with_a_realm_style_name(self, state, check_mode):
        """The refusal is reported whatever the form of the name."""
        module = _module(check_mode=check_mode, state=state, name="realm1::manager1")
        blade = _blade(listing=_error())
        assert _run(module, blade) == "fail"
        assert _failure(module) == LIST_FAILED.format(REFUSED)
        _nothing_sent(blade)

    @pytest.mark.parametrize("version", ["v2c", "v3"])
    def test_refused_list_on_a_create(self, version):
        """A create is not attempted behind a list the array refused."""
        module = _module(
            version=version, community="public", user="snmpuser", host="192.0.2.10"
        )
        blade = _blade(listing=_error())
        assert _run(module, blade) == "fail"
        assert _failure(module) == LIST_FAILED.format(REFUSED)
        _nothing_sent(blade)


class TestPurefbSnmpMgrTest:
    """state=test runs the manager test and returns its results."""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("manager", [_v2c_manager, _v3_manager])
    def test_refused_test_reports_the_answer_of_the_array(self, manager, check_mode):
        """The managers were listed, the test itself is refused."""
        module = _module(check_mode=check_mode, state="test")
        blade = _blade([manager()], test=_error())
        assert _run(module, blade) == "fail"
        assert _failure(module) == TEST_FAILED.format("manager1", REFUSED)
        blade.get_snmp_managers_test.assert_called_once_with(names=["manager1"])
        _no_write(blade)

    @pytest.mark.parametrize("status_code", [429, 500, 503])
    def test_failed_test_without_a_message(self, status_code):
        module = _module(state="test")
        blade = _blade([_v2c_manager()], test=_error(None, status_code=status_code))
        assert _run(module, blade) == "fail"
        assert _failure(module) == TEST_FAILED.format("manager1", "Unknown error")
        _no_write(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_results_are_returned(self, check_mode):
        module = _module(check_mode=check_mode, state="test")
        blade = _blade([_v2c_manager("manager0"), _v2c_manager()])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": False, "test_response": [_reported()]}
        blade.get_snmp_managers_test.assert_called_once_with(names=["manager1"])
        _no_write(blade)

    def test_failed_result_is_returned(self):
        """A test the array ran and that did not succeed is a result."""
        failed = _component(
            enabled=False, success=False, result_details="Failed to send the trap."
        )
        module = _module(state="test")
        blade = _blade([_v2c_manager()], test=_valid([_component(), failed]))
        assert _run(module, blade) == "exit"
        assert _result(module) == {
            "changed": False,
            "test_response": [
                _reported(),
                _reported(
                    enabled="false",
                    success="false",
                    result_details="Failed to send the trap.",
                ),
            ],
        }

    def test_no_results(self):
        module = _module(state="test")
        blade = _blade([_v2c_manager()], test=_valid([]))
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": False, "test_response": []}

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("name", OTHER_NAMES)
    def test_manager_that_is_not_configured(self, name, check_mode):
        """No test is run for a name the array does not hold."""
        module = _module(check_mode=check_mode, state="test", name=name)
        blade = _blade([_v2c_manager()])
        assert _run(module, blade) == "fail"
        assert _failure(module) == NOT_CONFIGURED.format(name)
        _nothing_sent(blade)


V3_PARAMS = {
    "version": "v3",
    "host": "192.0.2.12",
    "user": "snmpuser",
    "auth_protocol": "SHA",
    "auth_passphrase": "auth-passphrase",
    "privacy_protocol": "AES",
    "privacy_passphrase": "privacy-passphrase",
}
V3_BODY = {
    "host": "192.0.2.12",
    "notification": "trap",
    "version": "v3",
    "v3": {
        "auth_protocol": "SHA",
        "auth_passphrase": "auth-passphrase",
        "privacy_protocol": "AES",
        "privacy_passphrase": "privacy-passphrase",
        "user": "snmpuser",
    },
}


def _v3_params(**changes):
    """The parameters of the v3 manager with some of them replaced."""
    params = dict(V3_PARAMS)
    params.update(changes)
    return params


class TestPurefbSnmpMgrCreate:
    """state=present for a name the array does not hold creates the manager."""

    V2C_BODY = {
        "host": "192.0.2.10",
        "notification": "trap",
        "version": "v2c",
        "v2c": {"community": "public"},
    }

    @pytest.mark.parametrize("name", ["manager1", "manager2"])
    def test_create_v2c(self, name):
        """The manager is created next to the managers that exist."""
        module = _module(
            name=name, version="v2c", community="public", host="192.0.2.10"
        )
        other = "manager0" if name == "manager1" else "manager1"
        blade = _blade([_v2c_manager(other)])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": True}
        blade.post_snmp_managers.assert_called_once_with(
            names=[name], snmp_manager=self.V2C_BODY
        )
        blade.patch_snmp_managers.assert_not_called()
        blade.delete_snmp_managers.assert_not_called()

    def test_create_of_another_spelling_reports_the_answer_of_the_array(self):
        """The array holds manager1 and takes no MANAGER1 beside it.

        The module compares the names exactly, as a read by name does, so
        it sends the create; the refusal of the array is reported and the
        manager the array holds is not touched.
        """
        module = _module(
            name="MANAGER1", version="v2c", community="public", host="192.0.2.10"
        )
        blade = _blade([_v2c_manager()])
        assert _run(module, blade) == "fail"
        assert _failure(module) == (
            "Failed to create v2c SNMP manager MANAGER1. Error: "
            + EXISTS.format("manager1")
        )
        blade.post_snmp_managers.assert_called_once_with(
            names=["MANAGER1"], snmp_manager=self.V2C_BODY
        )
        blade.patch_snmp_managers.assert_not_called()
        blade.delete_snmp_managers.assert_not_called()

    def test_realm_style_name_is_sent_as_given(self):
        """The module has no rule for a realm-style name: the array decides."""
        module = _module(
            name="realm1::manager1",
            version="v2c",
            community="public",
            host="192.0.2.10",
        )
        blade = _blade([_v2c_manager()])
        _run(module, blade)
        blade.post_snmp_managers.assert_called_once_with(
            names=["realm1::manager1"], snmp_manager=self.V2C_BODY
        )
        blade.patch_snmp_managers.assert_not_called()
        blade.delete_snmp_managers.assert_not_called()

    def test_create_v3(self):
        module = _module(**V3_PARAMS)
        blade = _blade()
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": True}
        blade.post_snmp_managers.assert_called_once_with(
            names=["manager1"], snmp_manager=V3_BODY
        )

    @pytest.mark.parametrize("version", ["v2c", "v3"])
    def test_create_in_check_mode_sends_nothing(self, version):
        module = _module(
            check_mode=True,
            version=version,
            community="public",
            user="snmpuser",
            host="192.0.2.10",
        )
        blade = _blade()
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": True}
        _nothing_sent(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_create_needs_a_version(self, check_mode):
        module = _module(check_mode=check_mode, host="192.0.2.10")
        blade = _blade()
        assert _run(module, blade) == "fail"
        assert _failure(module) == "SNMP version required to create a new manager"
        _nothing_sent(blade)

    @pytest.mark.parametrize("version", ["v2c", "v3"])
    def test_refused_create_reports_the_answer_of_the_array(self, version):
        module = _module(
            version=version, community="public", user="snmpuser", host="192.0.2.10"
        )
        blade = _blade(write=_error())
        assert _run(module, blade) == "fail"
        assert _failure(module) == CREATE_FAILED.format(version, REFUSED)
        blade.post_snmp_managers.assert_called_once()


class TestPurefbSnmpMgrUpdate:
    """state=present for a manager the array holds changes what differs."""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize(
        "params",
        [
            {},
            {"host": "192.0.2.10"},
            {"version": "v2c", "community": "public", "host": "192.0.2.10"},
            {"version": "v2c", "community": "another", "host": "192.0.2.10"},
        ],
    )
    def test_v2c_values_the_array_holds_report_no_change(self, params, check_mode):
        """The masked community string is never a difference."""
        module = _module(check_mode=check_mode, **params)
        blade = _blade([_v2c_manager("manager0"), _v2c_manager()])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": False}
        blade.get_snmp_managers.assert_called_with(names=["manager1"])
        _nothing_sent(blade)

    @pytest.mark.parametrize("community", [None, "public"])
    def test_v2c_host_change(self, community):
        """The community string is sent with a change when the task gives it."""
        module = _module(host="192.0.2.11", community=community)
        blade = _blade([_v2c_manager()])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": True}
        blade.patch_snmp_managers.assert_called_once_with(
            names=["manager1"],
            snmp_manager={
                "host": "192.0.2.11",
                "notification": "trap",
                "version": "v2c",
                "v2c": {"community": community} if community else None,
            },
        )
        blade.post_snmp_managers.assert_not_called()
        blade.delete_snmp_managers.assert_not_called()

    def test_v2c_notification_change(self):
        module = _module(notification="inform")
        blade = _blade([_v2c_manager()])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": True}
        body = blade.patch_snmp_managers.call_args[1]["snmp_manager"]
        assert body["notification"] == "inform"
        assert body["host"] == "192.0.2.10"

    @pytest.mark.parametrize("manager", [_v2c_manager, _v3_manager])
    def test_change_in_check_mode_sends_nothing(self, manager):
        module = _module(check_mode=True, host="192.0.2.99")
        blade = _blade([manager()])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": True}
        _nothing_sent(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("params", [{}, V3_PARAMS])
    def test_v3_values_the_array_holds_report_no_change(self, params, check_mode):
        """The masked passphrases are never a difference."""
        module = _module(check_mode=check_mode, **params)
        blade = _blade([_v3_manager()])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": False}
        _nothing_sent(blade)

    def test_v3_user_change(self):
        module = _module(**_v3_params(user="another"))
        blade = _blade([_v3_manager()])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": True}
        blade.patch_snmp_managers.assert_called_once_with(
            names=["manager1"],
            snmp_manager=dict(V3_BODY, v3=dict(V3_BODY["v3"], user="another")),
        )

    def test_v2c_manager_becomes_v3(self):
        module = _module(**V3_PARAMS)
        blade = _blade([_v2c_manager()])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": True}
        blade.patch_snmp_managers.assert_called_once_with(
            names=["manager1"], snmp_manager=V3_BODY
        )

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_refused_read_of_the_manager(self, check_mode):
        """The manager was listed, its read by name is refused."""
        module = _module(check_mode=check_mode, host="192.0.2.11")
        blade = _blade([_v2c_manager()], read=_error())
        assert _run(module, blade) == "fail"
        assert _failure(module) == GET_FAILED.format("manager1", REFUSED)
        _nothing_sent(blade)

    @pytest.mark.parametrize("manager", [_v2c_manager, _v3_manager])
    def test_refused_update_reports_the_answer_of_the_array(self, manager):
        module = _module(host="192.0.2.99")
        blade = _blade([manager()], write=_error())
        assert _run(module, blade) == "fail"
        version = manager().version
        assert _failure(module) == UPDATE_FAILED.format(version, REFUSED)
        blade.patch_snmp_managers.assert_called_once()


class TestPurefbSnmpMgrDelete:
    """state=absent deletes the manager the array holds under that name."""

    @pytest.mark.parametrize("manager", [_v2c_manager, _v3_manager])
    def test_delete(self, manager):
        module = _module(state="absent")
        blade = _blade([_v2c_manager("manager0"), manager()])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": True}
        blade.delete_snmp_managers.assert_called_once_with(names=["manager1"])
        blade.post_snmp_managers.assert_not_called()
        blade.patch_snmp_managers.assert_not_called()

    def test_delete_in_check_mode_sends_nothing(self):
        module = _module(check_mode=True, state="absent")
        blade = _blade([_v2c_manager()])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": True}
        _nothing_sent(blade)

    def test_refused_delete_reports_the_answer_of_the_array(self):
        module = _module(state="absent")
        blade = _blade([_v2c_manager()], write=_error())
        assert _run(module, blade) == "fail"
        assert _failure(module) == DELETE_FAILED.format(REFUSED)
        blade.delete_snmp_managers.assert_called_once_with(names=["manager1"])

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("name", OTHER_NAMES)
    def test_manager_that_is_not_configured(self, name, check_mode):
        """Another name, spelling or a realm-style name deletes nothing."""
        module = _module(check_mode=check_mode, state="absent", name=name)
        blade = _blade([_v2c_manager()])
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": False}
        _nothing_sent(blade)

    def test_no_managers_at_all(self):
        module = _module(state="absent")
        blade = _blade()
        assert _run(module, blade) == "exit"
        assert _result(module) == {"changed": False}
        _nothing_sent(blade)


class TestPurefbSnmpMgrChecks:
    """What the module settles before any request for a manager."""

    @pytest.mark.parametrize("state", STATES)
    def test_missing_sdk(self, state):
        module = _module(state=state)
        blade = _blade([_v2c_manager()])
        assert _run(module, blade, sdk=False) == "fail"
        assert _failure(module) == "py-pure-client SDK is required for this module"
        blade.get_snmp_managers.assert_not_called()
        _nothing_sent(blade)

    @pytest.mark.parametrize("passphrase", ["short", "x" * 33])
    def test_auth_passphrase_length(self, passphrase):
        module = _module(**_v3_params(auth_passphrase=passphrase))
        blade = _blade()
        assert _run(module, blade) == "fail"
        assert _failure(module) == AUTH_LENGTH
        _nothing_sent(blade)

    @pytest.mark.parametrize("passphrase", ["short", "x" * 64])
    def test_privacy_passphrase_length(self, passphrase):
        module = _module(**_v3_params(privacy_passphrase=passphrase))
        blade = _blade()
        assert _run(module, blade) == "fail"
        assert _failure(module) == PRIVACY_LENGTH
        _nothing_sent(blade)

    @pytest.mark.parametrize(
        "value, readable",
        [(None, None), (MASKED, None), ("*", None), ("public", "public"), ("", "")],
    )
    def test_masked_value_is_not_readable(self, value, readable):
        assert _readable(value) == readable
