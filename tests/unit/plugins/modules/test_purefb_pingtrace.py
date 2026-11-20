# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_pingtrace module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import re
import sys
import multiprocessing
import ctypes
from unittest.mock import Mock, patch, MagicMock

import pytest
import yaml

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
from plugins.modules.purefb_pingtrace import (
    DOCUMENTATION,
    EXAMPLES,
    main,
    run_ping,
    run_trace,
)

MOD = "plugins.modules.purefb_pingtrace"
FQCN = "everpure.flashblade.purefb_pingtrace"
DEST = "127.0.0.1"
OPTIONS = [
    "action",
    "component",
    "count",
    "destination",
    "discover_mtu",
    "fragment",
    "latency",
    "method",
    "packet_size",
    "port",
    "resolve",
    "source",
]
# What the array accepts as a source: the address or the name of one of its
# network interfaces, or the name of a subnet
SOURCES = ["10.10.10.10", "vir0", "mgmt"]
# Answers of the array, as Purity//FB 4.8.8 sends them
PING_ONE = (
    "PING 127.0.0.1 (127.0.0.1) 56(84) bytes of data.\n"
    "64 bytes from 127.0.0.1: icmp_seq=1 ttl=64 time=0.028 ms\n"
    "\n"
    "--- 127.0.0.1 ping statistics ---\n"
    "1 packets transmitted, 1 received, 0% packet loss, time 0ms\n"
    "rtt min/avg/max/mdev = 0.028/0.028/0.028/0.000 ms\n"
)
PING_THREE = (
    "PING 127.0.0.1 (127.0.0.1) 1400(1428) bytes of data.\n"
    "1408 bytes from 127.0.0.1: icmp_seq=1 ttl=64 time=0.022 ms\n"
    "1408 bytes from 127.0.0.1: icmp_seq=2 ttl=64 time=0.072 ms\n"
    "1408 bytes from 127.0.0.1: icmp_seq=3 ttl=64 time=0.041 ms\n"
    "\n"
    "--- 127.0.0.1 ping statistics ---\n"
    "3 packets transmitted, 3 received, 0% packet loss, time 2065ms\n"
    "rtt min/avg/max/mdev = 0.022/0.045/0.072/0.020 ms\n"
)
# A destination that does not answer and a name that does not resolve
PING_NO_ANSWER = ""
PING_NO_NAME = "ping: nohost.invalid: Name or service not known\n"
TRACE_ONE = (
    "traceroute to 127.0.0.1 (127.0.0.1), 30 hops max, 60 byte packets\n"
    " 1  127.0.0.1  0.031 ms  0.007 ms  0.006 ms\n"
)
NO_SOURCE = "Need to be an existing subnet, IP or a network interface."
NO_COMPONENT = "Hardware component is unavailable or does not exist."
NO_USE = "Hardware component is not a valid choice with the current inputs."
NOT_PERMITTED = "Operation not permitted."
COMPONENT_NAME = re.compile(r"^CH\d+\.F[BM]\d+$")


def _params(**overrides):
    params = {
        "action": "ping",
        "method": "udp",
        "destination": DEST,
        "source": None,
        "component": None,
        "port": None,
        "count": 1,
        "packet_size": 56,
        "resolve": True,
        "fragment": True,
        "latency": False,
        "discover_mtu": False,
    }
    params.update(overrides)
    return params


def _module(check_mode=False, **overrides):
    module = Mock()
    module.params = _params(**overrides)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _item(component, details, destination=DEST, source=None):
    """One result of a ping or a trace: the answer of one component.

    The array repeats the source of the request in each result and leaves
    the field out when the request has none.
    """
    fields = ["component_name", "destination", "details"]
    if source is not None:
        fields.append("source")
    item = Mock(spec=fields)
    item.component_name = component
    item.destination = destination
    item.details = details
    if source is not None:
        item.source = source
    return item


def _response(*items):
    """A 200 answer of the SDK; its items can be read once."""
    res = Mock(spec=["status_code", "items"])
    res.status_code = 200
    res.items = iter(items)
    return res


def _error(message, status_code=400):
    """An error answer of the SDK: it has no items."""
    res = Mock(spec=["status_code", "errors"])
    res.status_code = status_code
    err = Mock()
    err.message = message
    res.errors = [err]
    return res


def _get_error_message(res):
    return res.errors[0].message


def _blade(ping=None, trace=None, source=None):
    blade = Mock()
    blade.get_network_interfaces_ping.return_value = (
        ping
        if ping is not None
        else _response(_item("CH1.FM1", PING_ONE, source=source))
    )
    blade.get_network_interfaces_trace.return_value = (
        trace
        if trace is not None
        else _response(_item("CH1.FM1", TRACE_ONE, source=source))
    )
    return blade


def _call(func, module, blade):
    """Call run_ping() or run_trace(); both end the module."""
    with patch(MOD + ".get_error_message", side_effect=_get_error_message):
        with pytest.raises(SystemExit):
            func(module, blade)


def _run(module, blade, api_version="2.30"):
    """Run main() against the stand-in; returns the patched AnsibleModule."""
    patchers = [
        patch(MOD + ".AnsibleModule", return_value=module),
        patch(MOD + ".get_system", return_value=blade),
        patch(MOD + ".get_rest_api_version", return_value=api_version),
        patch(MOD + ".get_error_message", side_effect=_get_error_message),
        patch(MOD + ".purefb_argument_spec", return_value={}),
        patch(MOD + ".LooseVersion", RealLooseVersion),
    ]
    started = [patcher.start() for patcher in patchers]
    try:
        main()
    except SystemExit:
        pass
    finally:
        for patcher in patchers:
            patcher.stop()
    return started[0]


def _result(module):
    module.fail_json.assert_not_called()
    module.exit_json.assert_called_once()
    return module.exit_json.call_args[1]


def _failure(module):
    module.exit_json.assert_not_called()
    module.fail_json.assert_called_once()
    return module.fail_json.call_args[1]["msg"]


class TestRunPing:
    """The ping request and the result per component"""

    def test_request_without_source_or_component(self):
        blade = _blade()
        module = _module()
        _call(run_ping, module, blade)
        blade.get_network_interfaces_ping.assert_called_once_with(
            destination=DEST,
            packet_size=56,
            count=1,
            print_latency=False,
            resolve_hostname=True,
        )
        blade.get_network_interfaces_trace.assert_not_called()

    @pytest.mark.parametrize("source", SOURCES)
    def test_source_is_sent_as_given(self, source):
        blade = _blade(source=source)
        module = _module(source=source)
        _call(run_ping, module, blade)
        kwargs = blade.get_network_interfaces_ping.call_args[1]
        assert kwargs["source"] == source
        assert "component_name" not in kwargs
        assert _result(module)["pingfact"]["CH1_FM1"]["source"] == source

    def test_component_is_sent_as_given(self):
        blade = _blade()
        module = _module(component="CH1.FM1")
        _call(run_ping, module, blade)
        kwargs = blade.get_network_interfaces_ping.call_args[1]
        assert kwargs["component_name"] == "CH1.FM1"
        assert "source" not in kwargs
        assert _result(module)["pingfact"]["CH1_FM1"]["source"] is None

    @pytest.mark.parametrize("source", SOURCES)
    def test_source_and_component(self, source):
        blade = _blade(source=source)
        module = _module(source=source, component="CH1.FB1")
        _call(run_ping, module, blade)
        blade.get_network_interfaces_ping.assert_called_once_with(
            destination=DEST,
            component_name="CH1.FB1",
            source=source,
            packet_size=56,
            count=1,
            print_latency=False,
            resolve_hostname=True,
        )

    def test_packet_options_are_sent(self):
        blade = _blade(ping=_response(_item("CH1.FM1", PING_THREE)))
        module = _module(count=3, packet_size=1400, latency=True, resolve=False)
        _call(run_ping, module, blade)
        blade.get_network_interfaces_ping.assert_called_once_with(
            destination=DEST,
            packet_size=1400,
            count=3,
            print_latency=True,
            resolve_hostname=False,
        )
        assert _result(module)["pingfact"]["CH1_FM1"] == {
            "destination": DEST,
            "source": None,
            "packet_loss": "0%",
            "packet_tx": 3,
            "packet_rx": 3,
            "time": "2065ms",
            "details": PING_THREE,
        }

    def test_one_result_per_component(self):
        answer = _response(
            _item("CH1.FB1", PING_ONE, source="vir0"),
            _item("CH1.FM1", PING_ONE, source="vir0"),
            _item("CH1.FM2", PING_ONE, source="vir0"),
        )
        module = _module(source="vir0")
        _call(run_ping, module, _blade(ping=answer))
        result = _result(module)
        assert result["changed"] is False
        assert sorted(result["pingfact"]) == ["CH1_FB1", "CH1_FM1", "CH1_FM2"]
        for fact in result["pingfact"].values():
            assert fact == {
                "destination": DEST,
                "source": "vir0",
                "packet_loss": "0%",
                "packet_tx": 1,
                "packet_rx": 1,
                "time": "0ms",
                "details": PING_ONE,
            }

    @pytest.mark.parametrize("details", [PING_NO_ANSWER, PING_NO_NAME])
    def test_component_without_statistics_is_reported_as_a_warning(self, details):
        answer = _response(_item("CH1.FM1", details), _item("CH1.FM2", PING_ONE))
        module = _module()
        _call(run_ping, module, _blade(ping=answer))
        result = _result(module)
        assert result["changed"] is False
        assert list(result["pingfact"]) == ["CH1_FM2"]
        module.warn.assert_called_once_with("CH1_FM1: {0}.".format(details))


class TestRunTrace:
    """The trace request and the result per component"""

    def test_request_without_source_or_component(self):
        blade = _blade()
        module = _module(action="trace")
        _call(run_trace, module, blade)
        blade.get_network_interfaces_trace.assert_called_once_with(
            port=None,
            destination=DEST,
            discover_mtu=False,
            fragment_packet=True,
            method="udp",
            resolve_hostname=True,
        )
        blade.get_network_interfaces_ping.assert_not_called()

    @pytest.mark.parametrize("source", SOURCES)
    def test_source_is_sent_as_given(self, source):
        blade = _blade(source=source)
        module = _module(action="trace", source=source)
        _call(run_trace, module, blade)
        kwargs = blade.get_network_interfaces_trace.call_args[1]
        assert kwargs["source"] == source
        assert "component_name" not in kwargs

    def test_component_is_sent_as_given(self):
        blade = _blade()
        module = _module(action="trace", component="CH1.FM1")
        _call(run_trace, module, blade)
        kwargs = blade.get_network_interfaces_trace.call_args[1]
        assert kwargs["component_name"] == "CH1.FM1"
        assert "source" not in kwargs

    @pytest.mark.parametrize("source", SOURCES)
    def test_source_and_component(self, source):
        blade = _blade(source=source)
        module = _module(action="trace", source=source, component="CH1.FM1")
        _call(run_trace, module, blade)
        blade.get_network_interfaces_trace.assert_called_once_with(
            port=None,
            destination=DEST,
            component_name="CH1.FM1",
            discover_mtu=False,
            source=source,
            fragment_packet=True,
            method="udp",
            resolve_hostname=True,
        )

    @pytest.mark.parametrize("fragment", [True, False])
    def test_trace_options_are_sent(self, fragment):
        blade = _blade()
        module = _module(
            action="trace",
            component="CH1.FM1",
            fragment=fragment,
            discover_mtu=True,
            method="tcp",
            port="443",
            resolve=False,
        )
        _call(run_trace, module, blade)
        blade.get_network_interfaces_trace.assert_called_once_with(
            port="443",
            destination=DEST,
            discover_mtu=True,
            component_name="CH1.FM1",
            fragment_packet=fragment,
            method="tcp",
            resolve_hostname=False,
        )

    def test_one_result_per_component(self):
        answer = _response(_item("CH1.FM1", TRACE_ONE), _item("CH1.FM2", TRACE_ONE))
        module = _module(action="trace")
        _call(run_trace, module, _blade(trace=answer))
        assert _result(module) == {
            "changed": False,
            "tracefact": {
                "CH1_FM1": {"details": TRACE_ONE},
                "CH1_FM2": {"details": TRACE_ONE},
            },
        }

    def test_component_without_details_is_left_out(self):
        silent = Mock(spec=["component_name", "destination"])
        silent.component_name = "CH1.FM2"
        answer = _response(_item("CH1.FM1", TRACE_ONE), silent)
        module = _module(action="trace")
        _call(run_trace, module, _blade(trace=answer))
        assert list(_result(module)["tracefact"]) == ["CH1_FM1"]


ACTIONS = [
    ("ping", run_ping, "Failed to run ping. Error: "),
    ("trace", run_trace, "Failed to run trace. Error: "),
]


@pytest.mark.parametrize("action, func, prefix", ACTIONS)
class TestRefusedRequest:
    """A request the array refuses fails with the message of the array"""

    # A hostname, a hardware component name, an address no network interface
    # has and a name no network interface or subnet has
    @pytest.mark.parametrize(
        "source", ["localhost", "CH1.FM1", "192.0.2.1", "tenant1::vir0"]
    )
    def test_source_the_array_does_not_know(self, action, func, prefix, source):
        blade = _blade(ping=_error(NO_SOURCE), trace=_error(NO_SOURCE))
        module = _module(action=action, source=source, component="CH1.FM1")
        _call(func, module, blade)
        request = getattr(blade, "get_network_interfaces_" + action)
        assert request.call_args[1]["source"] == source
        assert _failure(module) == prefix + NO_SOURCE

    @pytest.mark.parametrize("component", ["CH9.FM9", "tenant1::CH1.FM1"])
    def test_component_the_array_does_not_know(self, action, func, prefix, component):
        blade = _blade(ping=_error(NO_COMPONENT), trace=_error(NO_COMPONENT))
        module = _module(action=action, component=component)
        _call(func, module, blade)
        request = getattr(blade, "get_network_interfaces_" + action)
        assert request.call_args[1]["component_name"] == component
        assert _failure(module) == prefix + NO_COMPONENT

    # On a controller: a data interface by name and by address, a subnet that
    # has only data interfaces and the support interface of the other controller
    @pytest.mark.parametrize(
        "source", ["data1", "10.10.10.20", "data-subnet", "fm2.admin0"]
    )
    def test_component_that_cannot_use_the_source(self, action, func, prefix, source):
        blade = _blade(ping=_error(NO_USE), trace=_error(NO_USE))
        module = _module(action=action, source=source, component="CH1.FM1")
        _call(func, module, blade)
        request = getattr(blade, "get_network_interfaces_" + action)
        assert request.call_args[1]["source"] == source
        assert request.call_args[1]["component_name"] == "CH1.FM1"
        assert _failure(module) == prefix + NO_USE

    def test_administrator_without_access(self, action, func, prefix):
        blade = _blade(ping=_error(NOT_PERMITTED), trace=_error(NOT_PERMITTED))
        module = _module(action=action)
        _call(func, module, blade)
        assert _failure(module) == prefix + NOT_PERMITTED


class TestMain:
    """The version check, the choice of the action and check mode"""

    def test_old_rest_version_fails_before_any_request(self):
        blade = _blade()
        module = _module()
        _run(module, blade, api_version="2.5")
        assert _failure(module) == (
            "FlashBlade REST version not supported. Minimum version required: 2.6"
        )
        blade.get_network_interfaces_ping.assert_not_called()
        blade.get_network_interfaces_trace.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_ping(self, check_mode):
        blade = _blade(source="vir0")
        module = _module(check_mode=check_mode, source="vir0")
        _run(module, blade, api_version="2.6")
        blade.get_network_interfaces_ping.assert_called_once()
        blade.get_network_interfaces_trace.assert_not_called()
        result = _result(module)
        assert result["changed"] is False
        assert list(result["pingfact"]) == ["CH1_FM1"]

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_trace(self, check_mode):
        blade = _blade(source="vir0")
        module = _module(check_mode=check_mode, action="trace", source="vir0")
        _run(module, blade)
        blade.get_network_interfaces_trace.assert_called_once()
        blade.get_network_interfaces_ping.assert_not_called()
        result = _result(module)
        assert result["changed"] is False
        assert list(result["tracefact"]) == ["CH1_FM1"]

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("action, func, prefix", ACTIONS)
    def test_refusal_is_the_same_in_check_mode(self, action, func, prefix, check_mode):
        blade = _blade(ping=_error(NO_SOURCE), trace=_error(NO_SOURCE))
        module = _module(check_mode=check_mode, action=action, source="localhost")
        _run(module, blade)
        assert _failure(module) == prefix + NO_SOURCE

    def test_argument_spec(self):
        ansible_module = _run(_module(), _blade())
        args, kwargs = ansible_module.call_args
        spec = args[0]
        assert sorted(spec) == OPTIONS
        assert spec["destination"] == {"type": "str", "required": True}
        assert spec["source"] == {"type": "str"}
        assert spec["component"] == {"type": "str"}
        assert spec["fragment"] == {"type": "bool", "default": True}
        assert kwargs == {"supports_check_mode": True}


class TestDocumentation:
    """The documentation names what the array accepts and its examples can run"""

    def test_source_names_what_the_array_accepts(self):
        option = yaml.safe_load(DOCUMENTATION)["options"]["source"]
        text = " ".join(option["description"])
        for form in ("IP address", "network interface", "subnet"):
            assert form in text
        assert "hostname is not accepted" in text

    def test_component_names_the_rule_for_a_source(self):
        option = yaml.safe_load(DOCUMENTATION)["options"]["component"]
        text = " ".join(option["description"])
        assert "I(source) is also given" in text
        assert "accepted on a blade and refused on a controller" in text

    def test_documented_options_are_the_options_of_the_module(self):
        assert sorted(yaml.safe_load(DOCUMENTATION)["options"]) == OPTIONS

    def test_examples_use_documented_options(self):
        documented = set(OPTIONS + ["fb_url", "api_token"])
        for task in yaml.safe_load(EXAMPLES):
            assert set(task[FQCN]) <= documented

    def test_examples_have_a_source_the_array_accepts(self):
        tasks = [task[FQCN] for task in yaml.safe_load(EXAMPLES)]
        sources = [args["source"] for args in tasks if "source" in args]
        assert sources
        for source in sources:
            assert not COMPONENT_NAME.match(source)

    def test_examples_name_a_hardware_component(self):
        tasks = [task[FQCN] for task in yaml.safe_load(EXAMPLES)]
        components = [args["component"] for args in tasks if "component" in args]
        assert components
        for component in components:
            assert COMPONENT_NAME.match(component)
