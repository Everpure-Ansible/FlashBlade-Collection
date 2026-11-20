# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_syslog module."""

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
from plugins.modules.purefb_syslog import main

MOD = "plugins.modules.purefb_syslog"
REFUSED = "Operation not permitted."
NOT_FOUND = "Syslog connection does not exist."
NO_NAME = "Missing or invalid parameter."
LIST_FAILED = "Failed to list syslog servers. Error: {0}"
NOT_CONFIGURED = "Syslog server {0} is not configured"
NAME_LIST = (
    "name must be the name of one syslog server: in {0} the array reads a comma "
    "as a separator of names."
)
ADD_FAILED = "Failed to add syslog server. Error: {0}"
ADD_FAILED_OLD = "Failed to add syslog server {0} - {1}. Error: {2}"
UPDATE_FAILED = "Updating syslog server {0} failed. Error: {1}"
DELETE_FAILED = "Failed to remove syslog server {0}. Error: {1}"
TEST_FAILED = "Failed to test syslog server {0}. Error: {1}"
UPGRADE = "Purity//FB needs upgrading to support modification of existing syslog server"
STATES = ["present", "absent", "test"]
FABRIC = ("CH1.FM1", "CH1.FM2")
URI = "tcp://192.0.2.10:514"
# the settings of the server that every stand-in array holds as syslog1
SAME = {"protocol": "tcp", "address": "192.0.2.10", "port": "514"}
# spellings the array reads as the server syslog1
UNTIDY = [" syslog1", "syslog1 ", "syslog1\n", "\tSYSLOG1 "]
# names the array reads as a list of names
LISTS = ["syslog1,syslog2", "syslog1,", ",syslog1", "syslog1, SYSLOG1"]


class ExitJson(Exception):
    """Raised by the exit_json stand-in: the real one ends the module."""


class FailJson(Exception):
    """Raised by the fail_json stand-in: the real one ends the module."""


def _module(check_mode=False, **params):
    module = Mock()
    module.params = {
        "name": "syslog1",
        "state": "present",
        "protocol": None,
        "address": None,
        "port": None,
        "services": ["management"],
    }
    module.params.update(params)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=ExitJson)
    module.fail_json = Mock(side_effect=FailJson)
    return module


def _server(name="syslog1", uri=URI, services=None):
    """A syslog server as the array returns it (one without sources)."""
    return SimpleNamespace(
        id="10000000-0000-4000-8000-00000000{0:04d}".format(
            sum(map(ord, name)) % 10000
        ),
        name=name,
        uri=uri,
        services=list(services or ["management"]),
        sources=None,
        context=SimpleNamespace(
            id="20000000-0000-4000-8000-000000000001",
            name="fb-array",
            resource_type="remote-arrays",
        ),
    )


def _component(server="syslog1", name="CH1.FM1", **fields):
    """One result of the syslog test, with the fields of the TestResult model."""
    component = SimpleNamespace(
        component_address="192.0.2.1",
        component_name=name,
        description="Testing syslog connection",
        destination=URI,
        enabled=True,
        resource=SimpleNamespace(
            id="10000000-0000-4000-8000-00000000{0:04d}".format(
                sum(map(ord, server)) % 10000
            ),
            name=server,
            resource_type="syslog-servers",
        ),
        result_details=None,
        success=True,
        test_type="syslog",
    )
    for field, value in fields.items():
        setattr(component, field, value)
    return component


def _reported(server="syslog1", name="CH1.FM1", **fields):
    """What the module returns for one test result."""
    reported = {
        "component_address": "192.0.2.1",
        "component_name": name,
        "description": "Testing syslog connection",
        "destination": URI,
        "enabled": "true",
        "result_details": None,
        "success": "true",
        "test_type": "syslog",
        "resource_name": server,
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


def _blade(servers=None, read=None, results=None, test=None, write=None):
    """An array that holds the given syslog servers (default: syslog1).

    A read answers as the array does: every server when no name is given.
    A name is read as the array reads it: a comma separates names, white
    space around a name is ignored and case does not matter. The answer is
    the servers named, each once, the refusal of an unknown name when one
    of them is not configured, or the refusal of a name that is blank.
    read, test and write replace the answer to every read, to the syslog
    test and to every write.
    """
    servers = [_server()] if servers is None else list(servers)

    def get_syslog_servers(names=None):
        if read is not None:
            return read
        if names is None:
            return _valid(servers)
        asked = [part.strip().lower() for part in ",".join(names).split(",")]
        asked = [part for part in asked if part]
        if not asked:
            return _error(NO_NAME)
        found = []
        for name in asked:
            match = [srv for srv in servers if srv.name.lower() == name]
            if not match:
                return _error(NOT_FOUND)
            found.extend(srv for srv in match if srv not in found)
        return _valid(found)

    blade = Mock()
    blade.get_syslog_servers.side_effect = get_syslog_servers
    if results is None:
        results = [_component(srv.name, fabric) for srv in servers for fabric in FABRIC]
    blade.get_syslog_servers_test.return_value = (
        test if test is not None else _valid(results)
    )
    answer = write if write is not None else _valid([_server()])
    blade.post_syslog_servers.return_value = answer
    blade.patch_syslog_servers.return_value = answer
    blade.delete_syslog_servers.return_value = answer
    return blade


def _run(module, blade, api_version="2.30"):
    """Run main() against the stand-ins and return how the module ended.

    SyslogServerPost and SyslogServerPatch are replaced by functions that
    return their keyword arguments, so the body of a write can be compared.
    """
    with ExitStack() as stack:
        ansible_module = stack.enter_context(
            patch(MOD + ".AnsibleModule", return_value=module)
        )
        stack.enter_context(patch(MOD + ".purefb_argument_spec", return_value={}))
        get_system = stack.enter_context(patch(MOD + ".get_system", return_value=blade))
        stack.enter_context(
            patch(MOD + ".get_error_message", side_effect=_error_message)
        )
        stack.enter_context(
            patch(MOD + ".get_rest_api_version", return_value=api_version)
        )
        stack.enter_context(patch(MOD + ".LooseVersion", RealLooseVersion))
        stack.enter_context(
            patch(MOD + ".SyslogServerPost", side_effect=lambda **kwargs: kwargs)
        )
        stack.enter_context(
            patch(MOD + ".SyslogServerPatch", side_effect=lambda **kwargs: kwargs)
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


def _result(module):
    """The keyword arguments of the single exit_json call of a run."""
    module.exit_json.assert_called_once()
    module.fail_json.assert_not_called()
    return module.exit_json.call_args[1]


def _no_write(blade):
    blade.post_syslog_servers.assert_not_called()
    blade.patch_syslog_servers.assert_not_called()
    blade.delete_syslog_servers.assert_not_called()


def _no_test(blade):
    blade.get_syslog_servers_test.assert_not_called()


class TestPurefbSyslogRefusedRead:
    """A read of the syslog servers the array refuses or fails is reported."""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("state", STATES)
    def test_refused_read_reports_the_answer_of_the_array(self, state, check_mode):
        """A refusal does not mean that the server is not configured."""
        module = _module(check_mode=check_mode, state=state, **SAME)
        blade = _blade(read=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == LIST_FAILED.format(REFUSED)
        blade.get_syslog_servers.assert_called_once_with()
        _no_test(blade)
        _no_write(blade)

    @pytest.mark.parametrize("status_code", [429, 500, 503])
    @pytest.mark.parametrize("state", STATES)
    def test_failed_read_without_a_message(self, state, status_code):
        """An answer that carries no error message is reported all the same."""
        module = _module(state=state, **SAME)
        blade = _blade(read=_error(None, status_code=status_code))
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == LIST_FAILED.format("Unknown error")
        _no_test(blade)
        _no_write(blade)

    @pytest.mark.parametrize("state", STATES)
    def test_servers_are_read_once_and_not_by_name(self, state):
        """The module lists the servers; it sends no lookup that can be refused."""
        module = _module(state=state, **SAME)
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        blade.get_syslog_servers.assert_called_once_with()


class TestPurefbSyslogLookup:
    """Which configured server, if any, a name stands for."""

    @pytest.mark.parametrize("name", ["syslog1", "SYSLOG1", "SysLog1"])
    def test_name_is_matched_without_regard_to_case(self, name):
        module = _module(name=name, **SAME)
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": False}
        _no_write(blade)

    @pytest.mark.parametrize("servers", [[], [_server("syslog2")]])
    def test_name_that_is_not_configured(self, servers):
        module = _module(state="absent")
        blade = _blade(servers=servers)
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": False}
        _no_write(blade)

    def test_one_of_several_servers(self):
        module = _module(name="syslog2", state="absent")
        blade = _blade(servers=[_server(), _server("syslog2"), _server("syslog3")])
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        blade.delete_syslog_servers.assert_called_once_with(names=["syslog2"])

    def test_realm_style_name_is_not_the_server_of_that_leaf_absent(self):
        """Syslog servers live at array level: realm1::syslog1 is another name."""
        module = _module(name="realm1::syslog1", state="absent")
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": False}
        _no_write(blade)

    def test_realm_style_name_is_not_the_server_of_that_leaf_present(self):
        """The name is sent as given; the array decides whether it is valid."""
        module = _module(name="realm1::syslog1", **SAME)
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        blade.post_syslog_servers.assert_called_once_with(
            names=["realm1::syslog1"],
            syslog_server={"uri": URI, "services": ["management"]},
        )
        blade.patch_syslog_servers.assert_not_called()


class TestPurefbSyslogUntidyName:
    """White space around a name is ignored, as the array ignores it."""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("name", UNTIDY)
    def test_same_settings_change_nothing(self, name, check_mode):
        """The configured server is found: no create is sent or predicted."""
        module = _module(check_mode=check_mode, name=name, **SAME)
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": False}
        _no_write(blade)

    @pytest.mark.parametrize("name", UNTIDY)
    def test_update_names_the_server_as_the_array_does(self, name):
        module = _module(name=name, protocol="tcp", address="192.0.2.20")
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        blade.patch_syslog_servers.assert_called_once_with(
            names=["syslog1"],
            syslog_server={"uri": "tcp://192.0.2.20", "services": ["management"]},
        )
        blade.post_syslog_servers.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("name", UNTIDY)
    def test_delete_finds_the_server(self, name, check_mode):
        """state=absent does not report a configured server as absent."""
        module = _module(check_mode=check_mode, name=name, state="absent")
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        if check_mode:
            _no_write(blade)
        else:
            blade.delete_syslog_servers.assert_called_once_with(names=["syslog1"])

    @pytest.mark.parametrize("name", UNTIDY)
    def test_test_returns_the_results(self, name):
        module = _module(name=name, state="test")
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {
            "changed": False,
            "test_response": [
                _reported("syslog1", "CH1.FM1"),
                _reported("syslog1", "CH1.FM2"),
            ],
        }

    def test_new_name_is_sent_as_given(self):
        """A create carries the name of the task; the array trims it."""
        module = _module(name=" syslog2 ", protocol="udp", address="192.0.2.20")
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        blade.post_syslog_servers.assert_called_once_with(
            names=[" syslog2 "],
            syslog_server={"uri": "udp://192.0.2.20", "services": ["management"]},
        )

    @pytest.mark.parametrize("name", ["", " ", "\n"])
    def test_blank_name_is_no_server(self, name):
        module = _module(name=name, state="absent")
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": False}
        _no_write(blade)

    @pytest.mark.parametrize("name", ["", " ", "\n"])
    def test_test_of_a_blank_name_fails(self, name):
        module = _module(name=name, state="test")
        blade = _blade()
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == NOT_CONFIGURED.format(name)
        _no_test(blade)


class TestPurefbSyslogNameList:
    """A name the array reads as a list of names is refused."""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("state", STATES)
    @pytest.mark.parametrize("name", LISTS)
    def test_list_of_names_is_refused_before_any_request(self, name, state, check_mode):
        module = _module(check_mode=check_mode, name=name, state=state, **SAME)
        blade = _blade(servers=[_server(), _server("syslog2")])
        run = _run(module, blade)
        assert run.outcome == "fail"
        assert _failure(module) == NAME_LIST.format(name)
        run.get_system.assert_not_called()
        blade.get_syslog_servers.assert_not_called()
        _no_test(blade)
        _no_write(blade)

    @pytest.mark.parametrize("state", STATES)
    def test_refused_whoever_may_read_the_servers(self, state):
        """The name is refused before the read that the array may refuse."""
        module = _module(name="syslog1,syslog2", state=state, **SAME)
        blade = _blade(read=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == NAME_LIST.format("syslog1,syslog2")
        blade.get_syslog_servers.assert_not_called()


class TestPurefbSyslogCreate:
    """state=present for a name that is not configured."""

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_create(self, check_mode):
        module = _module(
            check_mode=check_mode, name="syslog2", protocol="udp", address="192.0.2.20"
        )
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        if check_mode:
            _no_write(blade)
        else:
            blade.post_syslog_servers.assert_called_once_with(
                names=["syslog2"],
                syslog_server={"uri": "udp://192.0.2.20", "services": ["management"]},
            )
            blade.patch_syslog_servers.assert_not_called()
            blade.delete_syslog_servers.assert_not_called()

    def test_create_with_port_and_services(self):
        module = _module(
            name="syslog2",
            protocol="tls",
            address="logs.example.com",
            port="6514",
            services=["data-audit", "management"],
        )
        blade = _blade(servers=[])
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        blade.post_syslog_servers.assert_called_once_with(
            names=["syslog2"],
            syslog_server={
                "uri": "tls://logs.example.com:6514",
                "services": ["data-audit", "management"],
            },
        )

    def test_create_before_the_services_version(self):
        """An array older than REST 2.14 is sent no services."""
        module = _module(name="syslog2", protocol="udp", address="192.0.2.20")
        blade = _blade()
        assert _run(module, blade, api_version="2.13").outcome == "exit"
        assert _result(module) == {"changed": True}
        blade.post_syslog_servers.assert_called_once_with(
            names=["syslog2"], syslog_server={"uri": "udp://192.0.2.20"}
        )

    def test_refused_create(self):
        module = _module(name="syslog2", protocol="udp", address="192.0.2.20")
        blade = _blade(write=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == ADD_FAILED.format(REFUSED)

    def test_refused_create_before_the_services_version(self):
        module = _module(name="syslog2", protocol="udp", address="192.0.2.20")
        blade = _blade(write=_error())
        assert _run(module, blade, api_version="2.13").outcome == "fail"
        assert _failure(module) == ADD_FAILED_OLD.format(
            "syslog2", "udp://192.0.2.20", REFUSED
        )


class TestPurefbSyslogUpdate:
    """state=present for a configured server."""

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_same_settings_change_nothing(self, check_mode):
        module = _module(check_mode=check_mode, **SAME)
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": False}
        _no_write(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_new_address(self, check_mode):
        module = _module(
            check_mode=check_mode, protocol="udp", address="192.0.2.20", port="1514"
        )
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        if check_mode:
            _no_write(blade)
        else:
            blade.patch_syslog_servers.assert_called_once_with(
                names=["syslog1"],
                syslog_server={
                    "uri": "udp://192.0.2.20:1514",
                    "services": ["management"],
                },
            )
            blade.post_syslog_servers.assert_not_called()
            blade.delete_syslog_servers.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_new_services(self, check_mode):
        module = _module(
            check_mode=check_mode, services=["data-audit", "management"], **SAME
        )
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        if check_mode:
            _no_write(blade)
        else:
            blade.patch_syslog_servers.assert_called_once_with(
                names=["syslog1"],
                syslog_server={"uri": URI, "services": ["data-audit", "management"]},
            )

    def test_update_names_the_server_as_the_array_does(self):
        """The write carries the name the array returned, not the spelling given."""
        module = _module(name="SYSLOG1", protocol="tcp", address="192.0.2.20")
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        blade.patch_syslog_servers.assert_called_once_with(
            names=["syslog1"],
            syslog_server={"uri": "tcp://192.0.2.20", "services": ["management"]},
        )

    def test_refused_update(self):
        module = _module(protocol="tcp", address="192.0.2.20")
        blade = _blade(write=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == UPDATE_FAILED.format("syslog1", REFUSED)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_update_before_the_services_version(self, check_mode):
        """An array older than REST 2.14 is sent no change of a server."""
        module = _module(check_mode=check_mode, protocol="tcp", address="192.0.2.20")
        blade = _blade()
        assert _run(module, blade, api_version="2.13").outcome == "exit"
        assert _result(module) == {"msg": UPGRADE}
        _no_write(blade)


class TestPurefbSyslogDelete:
    """state=absent."""

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_delete(self, check_mode):
        module = _module(check_mode=check_mode, state="absent")
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        if check_mode:
            _no_write(blade)
        else:
            blade.delete_syslog_servers.assert_called_once_with(names=["syslog1"])
            blade.post_syslog_servers.assert_not_called()
            blade.patch_syslog_servers.assert_not_called()

    def test_delete_names_the_server_as_the_array_does(self):
        module = _module(name="SYSLOG1", state="absent")
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        blade.delete_syslog_servers.assert_called_once_with(names=["syslog1"])

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_delete_of_a_server_that_is_not_configured(self, check_mode):
        module = _module(check_mode=check_mode, name="syslog2", state="absent")
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": False}
        _no_write(blade)

    def test_refused_delete(self):
        module = _module(state="absent")
        blade = _blade(write=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == DELETE_FAILED.format("syslog1", REFUSED)


class TestPurefbSyslogTest:
    """state=test returns the test results of the named server."""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("servers", [[], [_server()]])
    def test_server_that_is_not_configured_fails(self, servers, check_mode):
        """A test of nothing is not a test that passed."""
        module = _module(check_mode=check_mode, name="syslog2", state="test")
        blade = _blade(servers=servers)
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == NOT_CONFIGURED.format("syslog2")
        _no_test(blade)
        _no_write(blade)

    def test_results_of_the_named_server_only(self):
        """The array tests every server; the module returns those of name."""
        module = _module(name="syslog2", state="test")
        blade = _blade(servers=[_server(), _server("syslog2"), _server("syslog3")])
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {
            "changed": False,
            "test_response": [
                _reported("syslog2", "CH1.FM1"),
                _reported("syslog2", "CH1.FM2"),
            ],
        }
        blade.get_syslog_servers_test.assert_called_once_with()
        _no_write(blade)

    def test_name_in_another_case_returns_the_results(self):
        """The results carry the name of the server as the array spells it."""
        module = _module(name="SYSLOG1", state="test")
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {
            "changed": False,
            "test_response": [
                _reported("syslog1", "CH1.FM1"),
                _reported("syslog1", "CH1.FM2"),
            ],
        }

    def test_failed_and_disabled_results(self):
        results = [
            _component(enabled=False, success=False, result_details="Timed out"),
            _component(name="CH1.FM2", enabled=None, success=None),
        ]
        module = _module(state="test")
        blade = _blade(results=results)
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {
            "changed": False,
            "test_response": [
                _reported(enabled="false", success="false", result_details="Timed out"),
                _reported(name="CH1.FM2", enabled="false", success="false"),
            ],
        }

    def test_result_without_a_resource_is_left_out(self):
        results = [_component(resource=None), _component(name="CH1.FM2")]
        module = _module(state="test")
        blade = _blade(results=results)
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {
            "changed": False,
            "test_response": [_reported(name="CH1.FM2")],
        }

    def test_result_without_details(self):
        component = _component()
        del component.result_details
        module = _module(state="test")
        blade = _blade(results=[component])
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {
            "changed": False,
            "test_response": [_reported(result_details="")],
        }

    def test_no_results(self):
        module = _module(state="test")
        blade = _blade(results=[])
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": False, "test_response": []}

    def test_refused_test(self):
        """The servers were read, the test itself is refused."""
        module = _module(state="test")
        blade = _blade(test=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == TEST_FAILED.format("syslog1", REFUSED)
        _no_write(blade)


class TestPurefbSyslogArguments:
    """What main() hands to AnsibleModule."""

    def test_argument_spec(self):
        module = _module(**SAME)
        run = _run(module, _blade())
        args, kwargs = run.ansible_module.call_args
        spec = args[0]
        assert sorted(spec) == [
            "address",
            "name",
            "port",
            "protocol",
            "services",
            "state",
        ]
        assert spec["name"] == {"type": "str", "required": True}
        assert spec["state"]["default"] == "present"
        assert spec["state"]["choices"] == ["absent", "present", "test"]
        assert spec["protocol"]["choices"] == ["tcp", "tls", "udp"]
        assert spec["services"]["default"] == ["management"]
        assert spec["services"]["choices"] == ["management", "data-audit"]
        assert kwargs == {
            "required_if": [["state", "present", ["address", "protocol"]]],
            "supports_check_mode": True,
        }
