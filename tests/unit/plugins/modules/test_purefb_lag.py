# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_lag module."""

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

from plugins.modules.purefb_lag import main, normalize_port

MOD = "plugins.modules.purefb_lag"
REFUSED = "Operation not permitted."
READ_FAILED = "Failed to read LAG {0}. Error: {1}"
LIST_FAILED = "Failed to read the LAGs. Error: {0}"
IN_USE = "Selected port {0} is currently in use by another LAG."
PRECONFIGURED = "Preconfigured Link Aggregation Group cannot be deleted"
ONE_NAME = (
    "name must be the name of one Link Aggregation Group: in {0} "
    "the array reads a comma as a separator of names."
)
UPLINK_PORTS = ["CH1.ETH1", "CH1.ETH2", "CH1.ETH3", "CH1.ETH4"]


class ExitJson(Exception):
    """Raised by the exit_json stand-in: the real one ends the module."""


class FailJson(Exception):
    """Raised by the fail_json stand-in: the real one ends the module."""


def _module(check_mode=False, **params):
    module = Mock()
    module.params = {"name": "uplink", "state": "present", "ports": None}
    module.params.update(params)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=ExitJson)
    module.fail_json = Mock(side_effect=FailJson)
    return module


def _expand(ports):
    """The port names the array reports for CHx.ETHy chassis ports."""
    chassis = [port.split(".") for port in ports]
    return [
        "{0}.{1}.{2}".format(ch, fm, eth)
        for fm in ("FM1", "FM2")
        for ch, eth in chassis
    ]


def _lag(name, ports):
    """A LAG as the array returns it; ports are CHx.ETHy chassis ports."""
    members = _expand(ports)
    return SimpleNamespace(
        id="10000000-0000-4000-8000-00000000000{0}".format(len(name) % 10),
        name=name,
        lag_speed=100000000000 * len(members),
        mac_address="24:a9:37:00:00:01",
        port_speed=100000000000,
        ports=[
            SimpleNamespace(
                id="20000000-0000-4000-8000-0000000000{0:02d}".format(index),
                name=member,
                resource_type="hardware",
            )
            for index, member in enumerate(members)
        ],
        status="healthy",
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


def _blade(lags=None, named_read=None, list_read=None, write=None):
    """An array holding LAG uplink with its four chassis port pairs.

    lags replaces the LAGs the array holds. A read by name answers as the
    array does: a comma separates names, white space around a name is
    ignored, the letter case counts, a LAG the array does not hold answers
    400 "LAG <name> does not exist." and no name at all 400 "Missing or
    invalid parameter.". named_read and list_read replace the answer of the
    read with and without a name, write the answer of POST, PATCH and DELETE.
    """
    held = {lag.name: lag for lag in (lags or [_lag("uplink", UPLINK_PORTS)])}
    blade = Mock()

    def _get(**kwargs):
        names = kwargs.get("names")
        if names is None:
            if list_read is not None:
                return list_read
            return _valid(held.values())
        if named_read is not None:
            return named_read
        asked = [name.strip() for name in ",".join(names).split(",")]
        asked = list(dict.fromkeys(name for name in asked if name))
        if not asked:
            return _error("Missing or invalid parameter.")
        for name in asked:
            if name not in held:
                return _error("LAG {0} does not exist.".format(name))
        return _valid([held[name] for name in asked])

    def _written(**kwargs):
        if write is not None:
            return write
        body = kwargs["link_aggregation_group"]
        chassis = sorted(
            set(
                "{0}.{2}".format(*ref["name"].split("."))
                for ref in body["ports"]
                if ".FM1." in ref["name"]
            )
        )
        return _valid([_lag(kwargs["names"][0], chassis)])

    blade.get_link_aggregation_groups.side_effect = _get
    blade.post_link_aggregation_groups.side_effect = _written
    blade.patch_link_aggregation_groups.side_effect = _written
    blade.delete_link_aggregation_groups.return_value = (
        write if write is not None else _valid([])
    )
    return blade


def _run(module, blade, sdk=True):
    """Run main() against the stand-ins and return how the module ended.

    Reference and LinkAggregationGroup are replaced by functions that return
    their keyword arguments, so the body of a POST or PATCH can be compared.
    """
    with ExitStack() as stack:
        ansible_module = stack.enter_context(
            patch(MOD + ".AnsibleModule", return_value=module)
        )
        stack.enter_context(patch(MOD + ".get_system", return_value=blade))
        stack.enter_context(
            patch(MOD + ".get_error_message", side_effect=_error_message)
        )
        stack.enter_context(patch(MOD + ".HAS_PYPURECLIENT", sdk))
        stack.enter_context(
            patch(MOD + ".Reference", side_effect=lambda **kwargs: kwargs)
        )
        stack.enter_context(
            patch(MOD + ".LinkAggregationGroup", side_effect=lambda **kwargs: kwargs)
        )
        outcome = None
        try:
            main()
        except ExitJson:
            outcome = "exit"
        except FailJson:
            outcome = "fail"
    assert outcome is not None, "main() ended without exit_json or fail_json"
    return SimpleNamespace(outcome=outcome, ansible_module=ansible_module)


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
    blade.post_link_aggregation_groups.assert_not_called()
    blade.patch_link_aggregation_groups.assert_not_called()
    blade.delete_link_aggregation_groups.assert_not_called()


def _refs(ports):
    """The port references the module sends for CHx.ETHy chassis ports."""
    return [{"name": name} for port in ports for name in _expand([port])]


class TestPurefbLagNormalizePort:
    """The port names a requested port expands to."""

    def test_chassis_port_expands_to_both_fabric_modules(self):
        assert normalize_port(Mock(), "ch1.eth2") == ["CH1.FM1.ETH2", "CH1.FM2.ETH2"]

    def test_fully_qualified_port_is_used_as_given(self):
        assert normalize_port(Mock(), "ch2.fm1.eth4") == ["CH2.FM1.ETH4"]

    def test_x_port_is_used_as_given(self):
        assert normalize_port(Mock(), "xfm1.eth1") == ["XFM1.ETH1"]

    def test_other_formats_are_refused(self):
        module = _module()
        with pytest.raises(FailJson):
            normalize_port(module, "eth1")
        assert _failure(module) == "Invalid port name ETH1. Format must be CHx.ETHy"


class TestPurefbLagRefusedRead:
    """A read the array refuses or fails is reported, never taken for absent."""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize(
        "params",
        [
            {"name": "uplink", "ports": ["CH1.ETH1"]},
            {"name": "lag2", "ports": ["CH1.ETH9"]},
            {"name": "lag2", "state": "absent"},
            {"name": "uplink", "state": "absent"},
        ],
    )
    def test_refused_lookup_reports_the_answer_of_the_array(self, params, check_mode):
        """An identity that may not read LAGs is refused every read."""
        module = _module(check_mode=check_mode, **params)
        blade = _blade(named_read=_error(), list_read=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == READ_FAILED.format(params["name"], REFUSED)
        _no_write(blade)

    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize(
        "message, status_code, reported",
        [
            (REFUSED, 400, REFUSED),
            (None, 429, "Unknown error"),
            (None, 500, "Unknown error"),
        ],
    )
    def test_failed_lookup_is_not_taken_for_absent(
        self, message, status_code, reported, state
    ):
        """Only "does not exist" means absent; the read of all LAGs works."""
        module = _module(name="lag2", state=state, ports=["CH1.ETH9"])
        blade = _blade(named_read=_error(message, status_code=status_code))
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == READ_FAILED.format("lag2", reported)
        _no_write(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_refused_list_read_on_create(self, check_mode):
        module = _module(check_mode=check_mode, name="lag2", ports=["CH1.ETH9"])
        blade = _blade(list_read=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == LIST_FAILED.format(REFUSED)
        _no_write(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_refused_list_read_on_update(self, check_mode):
        module = _module(check_mode=check_mode, ports=["CH1.ETH1"])
        blade = _blade(list_read=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == LIST_FAILED.format(REFUSED)
        _no_write(blade)

    def test_failed_list_read_without_a_message(self):
        module = _module(name="lag2", ports=["CH1.ETH9"])
        blade = _blade(list_read=_error(None, status_code=500))
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == LIST_FAILED.format("Unknown error")
        _no_write(blade)

    def test_missing_lag_is_still_absent(self):
        """The array answers "LAG <name> does not exist." for a missing LAG."""
        module = _module(name="lag2", state="absent")
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": False}
        _no_write(blade)

    def test_existing_lag_is_read_once_by_name(self):
        module = _module(ports=UPLINK_PORTS)
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        named = [
            call
            for call in blade.get_link_aggregation_groups.call_args_list
            if "names" in call[1]
        ]
        assert len(named) == 1
        assert named[0][1] == {"names": ["uplink"]}


class TestPurefbLagName:
    """The task names one LAG, in whatever way the array reads the name."""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize(
        "name", ["uplink,uplink", "uplink,", ",uplink", "lag2,uplink", "lag2, lag3"]
    )
    def test_list_of_names_is_refused_before_any_request(self, name, state, check_mode):
        """The array would read the LAGs lag2 and uplink for lag2,uplink."""
        module = _module(
            check_mode=check_mode, name=name, state=state, ports=["CH1.ETH5"]
        )
        blade = _blade(
            lags=[
                _lag("uplink", UPLINK_PORTS),
                _lag("lag2", ["CH1.ETH5"]),
                _lag("lag3", ["CH1.ETH6"]),
            ]
        )
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == ONE_NAME.format(name)
        blade.get_link_aggregation_groups.assert_not_called()
        _no_write(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("name", [" uplink", "uplink ", " uplink "])
    def test_preconfigured_lag_with_white_space_is_not_deleted(self, name, check_mode):
        """The array ignores white space around a name: the read finds uplink."""
        module = _module(check_mode=check_mode, name=name, state="absent")
        blade = _blade(lags=[_lag(name.strip(), UPLINK_PORTS)])
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == PRECONFIGURED
        _no_write(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_lag_the_array_returned_decides_the_delete(self, check_mode):
        """Whatever the spelling, the preconfigured LAG the read returned stays."""
        module = _module(check_mode=check_mode, name="lag2", state="absent")
        blade = _blade(named_read=_valid([_lag("uplink", UPLINK_PORTS)]))
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == PRECONFIGURED
        _no_write(blade)

    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize("name", ["", " "])
    def test_blank_name_reports_the_answer_of_the_array(self, name, state):
        module = _module(name=name, state=state, ports=["CH1.ETH5"])
        blade = _blade()
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == READ_FAILED.format(
            name, "Missing or invalid parameter."
        )
        _no_write(blade)

    def test_white_space_around_a_name_reaches_the_lag(self):
        module = _module(name=" lag2 ", state="absent")
        blade = _blade(lags=[_lag("uplink", UPLINK_PORTS), _lag("lag2", ["CH1.ETH5"])])
        assert _run(module, blade).outcome == "exit"
        blade.delete_link_aggregation_groups.assert_called_once_with(names=[" lag2 "])
        assert _result(module) == {"changed": True}

    def test_name_in_another_letter_case_is_another_lag(self):
        """The array answers "LAG UPLINK does not exist." beside uplink."""
        module = _module(name="UPLINK", state="absent")
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": False}
        _no_write(blade)


class TestPurefbLagCreate:
    """state=present for a LAG the array does not hold."""

    def test_create(self):
        module = _module(name="lag2", ports=["ch1.eth5", "CH1.ETH6"])
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        blade.post_link_aggregation_groups.assert_called_once_with(
            names=["lag2"],
            link_aggregation_group={"ports": _refs(["CH1.ETH5", "CH1.ETH6"])},
        )
        assert _result(module) == {
            "changed": True,
            "lag": {
                "mac_address": "24:a9:37:00:00:01",
                "port_speed": "100.0Gb/s",
                "lag_speed": "400.0Gb/s",
                "status": "healthy",
            },
        }

    def test_create_check_mode_sends_nothing(self):
        module = _module(check_mode=True, name="lag2", ports=["CH1.ETH5"])
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True, "lag": []}
        _no_write(blade)

    def test_create_removes_duplicate_ports(self):
        module = _module(name="lag2", ports=["CH1.ETH5", "CH1.ETH5"])
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        body = blade.post_link_aggregation_groups.call_args[1]
        assert body["link_aggregation_group"] == {"ports": _refs(["CH1.ETH5"])}

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_create_with_a_port_of_another_lag_is_refused(self, check_mode):
        module = _module(check_mode=check_mode, name="lag2", ports=["ch1.eth1"])
        blade = _blade()
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == IN_USE.format("CH1.ETH1")
        _no_write(blade)

    def test_create_with_an_invalid_port_name(self):
        module = _module(name="lag2", ports=["eth5"])
        blade = _blade()
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == "Invalid port name ETH5. Format must be CHx.ETHy"
        _no_write(blade)

    def test_create_refused_by_the_array(self):
        module = _module(name="lag2", ports=["CH1.ETH5"])
        blade = _blade(write=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == "Failed to create LAG lag2. Error: " + REFUSED


class TestPurefbLagUpdate:
    """state=present for a LAG the array holds."""

    @pytest.mark.parametrize(
        "ports",
        [
            UPLINK_PORTS,
            ["ch1.eth4", "ch1.eth3", "ch1.eth2", "ch1.eth1"],
            _expand(UPLINK_PORTS),
        ],
    )
    def test_current_ports_are_unchanged(self, ports):
        module = _module(ports=list(ports))
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": False, "lag": []}
        _no_write(blade)

    def test_ports_are_replaced(self):
        module = _module(name="lag2", ports=["CH1.ETH5", "CH1.ETH7"])
        blade = _blade(
            lags=[_lag("uplink", UPLINK_PORTS), _lag("lag2", ["CH1.ETH5", "CH1.ETH6"])]
        )
        assert _run(module, blade).outcome == "exit"
        blade.patch_link_aggregation_groups.assert_called_once_with(
            names=["lag2"],
            link_aggregation_group={"ports": _refs(["CH1.ETH5", "CH1.ETH7"])},
        )
        assert _result(module) == {
            "changed": True,
            "lag": {
                "mac_address": "24:a9:37:00:00:01",
                "port_speed": "100.0Gb/s",
                "lag_speed": "400.0Gb/s",
                "status": "healthy",
            },
        }

    def test_update_check_mode_sends_nothing(self):
        module = _module(check_mode=True, ports=["CH1.ETH1"])
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True, "lag": []}
        _no_write(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_update_with_a_port_of_another_lag_is_refused(self, check_mode):
        module = _module(check_mode=check_mode, name="lag2", ports=["CH1.ETH4"])
        blade = _blade(lags=[_lag("uplink", UPLINK_PORTS), _lag("lag2", ["CH1.ETH5"])])
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == IN_USE.format("CH1.ETH4")
        _no_write(blade)

    def test_update_refused_by_the_array(self):
        module = _module(name="lag2", ports=["CH1.ETH6"])
        blade = _blade(
            lags=[_lag("uplink", UPLINK_PORTS), _lag("lag2", ["CH1.ETH5"])],
            write=_error(),
        )
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == "Failed to update LAG lag2. Error: " + REFUSED


class TestPurefbLagDelete:
    """state=absent."""

    def test_delete(self):
        module = _module(name="lag2", state="absent")
        blade = _blade(lags=[_lag("uplink", UPLINK_PORTS), _lag("lag2", ["CH1.ETH5"])])
        assert _run(module, blade).outcome == "exit"
        blade.delete_link_aggregation_groups.assert_called_once_with(names=["lag2"])
        assert _result(module) == {"changed": True}

    def test_delete_check_mode_sends_nothing(self):
        module = _module(check_mode=True, name="lag2", state="absent")
        blade = _blade(lags=[_lag("uplink", UPLINK_PORTS), _lag("lag2", ["CH1.ETH5"])])
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        _no_write(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_preconfigured_lag_is_not_deleted(self, check_mode):
        module = _module(check_mode=check_mode, state="absent")
        blade = _blade()
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == PRECONFIGURED
        _no_write(blade)

    def test_delete_refused_by_the_array(self):
        module = _module(name="lag2", state="absent")
        blade = _blade(
            lags=[_lag("uplink", UPLINK_PORTS), _lag("lag2", ["CH1.ETH5"])],
            write=_error(),
        )
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == "Failed to delete LAG lag2. Error: " + REFUSED


class TestPurefbLagMain:
    """Argument handling of main()."""

    def test_missing_sdk(self):
        module = _module(ports=UPLINK_PORTS)
        blade = _blade()
        assert _run(module, blade, sdk=False).outcome == "fail"
        assert _failure(module) == "py-pure-client sdk is required for this module"
        blade.get_link_aggregation_groups.assert_not_called()

    def test_check_mode_is_supported_and_present_needs_ports(self):
        module = _module(ports=UPLINK_PORTS)
        run = _run(module, _blade())
        kwargs = run.ansible_module.call_args[1]
        assert kwargs["supports_check_mode"] is True
        assert kwargs["required_if"] == [["state", "present", ["ports"]]]
