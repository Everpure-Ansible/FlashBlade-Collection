# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_proxy module."""

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

from plugins.modules.purefb_proxy import main

MOD = "plugins.modules.purefb_proxy"
REFUSED = "Operation not permitted."
READ_FAILED = "Failed to read the support settings. Error: {0}"
HOST = "proxy.example.com"
HTTPS_PROXY = "https://proxy.example.com:8080"
HTTP_PROXY = "http://proxy.example.com:8080"


class ExitJson(Exception):
    """Raised by the exit_json stand-in: the real one ends the module."""


class FailJson(Exception):
    """Raised by the fail_json stand-in: the real one ends the module."""


def _module(check_mode=False, **params):
    module = Mock()
    module.params = {"state": "present", "host": None, "port": None, "secure": True}
    module.params.update(params)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=ExitJson)
    module.fail_json = Mock(side_effect=FailJson)
    return module


def _support(proxy=None):
    """The support settings as the array returns them; proxy is null when none is set."""
    return SimpleNamespace(
        id="10000000-0000-4000-8000-000000000001",
        name="array1",
        edge_agent_update_enabled=False,
        edge_management_enabled=False,
        phonehome_enabled=True,
        proxy=proxy,
        remote_assist_active=False,
        remote_assist_duration=None,
        remote_assist_expires=None,
        remote_assist_opened=None,
        remote_assist_paths=[],
        remote_assist_status="disconnected",
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


def _blade(proxy=None, read=None, write=None):
    """An array whose support settings hold proxy.

    read replaces the answer of GET /support, write the answer of PATCH
    /support.
    """
    blade = Mock()
    blade.get_support.return_value = (
        read if read is not None else _valid([_support(proxy)])
    )
    blade.patch_support.side_effect = lambda **kwargs: (
        write if write is not None else _valid([_support(kwargs["support"]["proxy"])])
    )
    return blade


def _run(module, blade, sdk=True):
    """Run main() against the stand-ins and return how the module ended.

    Support is replaced by a function that returns its keyword arguments, so
    the body of a PATCH can be compared.
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


def _sent(blade):
    """The proxy of the single PATCH /support of a run."""
    blade.patch_support.assert_called_once()
    assert list(blade.patch_support.call_args[1]) == ["support"]
    body = blade.patch_support.call_args[1]["support"]
    assert list(body) == ["proxy"]
    return body["proxy"]


class TestPurefbProxyRead:
    """A read of the support settings the array refuses or fails is reported."""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize(
        "params",
        [
            {"state": "absent"},
            {"host": HOST, "port": 8080},
            {"host": HOST, "port": 8080, "secure": False},
        ],
    )
    def test_refused_read_reports_the_answer_of_the_array(self, params, check_mode):
        """An identity that may not read the support settings is refused."""
        module = _module(check_mode=check_mode, **params)
        blade = _blade(read=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == READ_FAILED.format(REFUSED)
        blade.patch_support.assert_not_called()

    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize(
        "message, status_code, reported",
        [
            (REFUSED, 403, REFUSED),
            (None, 429, "Unknown error"),
            (None, 500, "Unknown error"),
            ("Service unavailable.", 503, "Service unavailable."),
        ],
    )
    def test_failed_read_is_not_taken_for_no_proxy(
        self, message, status_code, reported, state
    ):
        """A read that fails says nothing about the proxy: nothing is sent."""
        module = _module(state=state, host=HOST, port=8080)
        blade = _blade(read=_error(message, status_code=status_code))
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == READ_FAILED.format(reported)
        blade.patch_support.assert_not_called()

    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_read_without_support_settings(self, state):
        module = _module(state=state, host=HOST, port=8080)
        blade = _blade(read=_valid([]))
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == "The array returned no support settings."
        blade.patch_support.assert_not_called()

    @pytest.mark.parametrize(
        "proxy, params",
        [
            (None, {"state": "absent"}),
            (None, {"host": HOST, "port": 8080}),
            (HTTPS_PROXY, {"state": "absent"}),
            (HTTPS_PROXY, {"host": HOST, "port": 8080}),
            (HTTPS_PROXY, {"host": HOST, "port": 8081}),
        ],
    )
    def test_support_settings_are_read_once(self, proxy, params):
        module = _module(**params)
        blade = _blade(proxy=proxy)
        assert _run(module, blade).outcome == "exit"
        blade.get_support.assert_called_once_with()


class TestPurefbProxyAbsent:
    """state=absent clears the proxy."""

    @pytest.mark.parametrize("proxy", [None, ""])
    @pytest.mark.parametrize("check_mode", [False, True])
    def test_no_proxy_is_unchanged(self, check_mode, proxy):
        module = _module(check_mode=check_mode, state="absent")
        blade = _blade(proxy=proxy)
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": False}
        blade.patch_support.assert_not_called()

    def test_settings_without_a_proxy_field_are_unchanged(self):
        """An answer that leaves the proxy out means no proxy is set."""
        support = _support()
        del support.proxy
        module = _module(state="absent")
        blade = _blade(read=_valid([support]))
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": False}
        blade.patch_support.assert_not_called()

    @pytest.mark.parametrize("proxy", [HTTPS_PROXY, HTTP_PROXY])
    def test_proxy_is_cleared(self, proxy):
        module = _module(state="absent")
        blade = _blade(proxy=proxy)
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        assert _sent(blade) == ""

    def test_host_and_port_are_ignored(self):
        module = _module(state="absent", host="other.example.com", port=3128)
        blade = _blade(proxy=HTTPS_PROXY)
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        assert _sent(blade) == ""

    def test_check_mode_sends_nothing(self):
        module = _module(check_mode=True, state="absent")
        blade = _blade(proxy=HTTPS_PROXY)
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        blade.patch_support.assert_not_called()

    def test_refused_by_the_array(self):
        module = _module(state="absent")
        blade = _blade(proxy=HTTPS_PROXY, write=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == "Delete proxy settings failed. Error: " + REFUSED


class TestPurefbProxySet:
    """state=present sets the proxy when the array has none."""

    @pytest.mark.parametrize("proxy", [None, ""])
    @pytest.mark.parametrize(
        "secure, port, expected",
        [
            (True, 8080, HTTPS_PROXY),
            (False, 8080, HTTP_PROXY),
            (True, 443, "https://proxy.example.com:443"),
        ],
    )
    def test_set(self, secure, port, expected, proxy):
        module = _module(host=HOST, port=port, secure=secure)
        blade = _blade(proxy=proxy)
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        assert _sent(blade) == expected

    def test_settings_without_a_proxy_field_are_set(self):
        support = _support()
        del support.proxy
        module = _module(host=HOST, port=8080)
        blade = _blade(read=_valid([support]))
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        assert _sent(blade) == HTTPS_PROXY

    def test_check_mode_sends_nothing(self):
        module = _module(check_mode=True, host=HOST, port=8080)
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        blade.patch_support.assert_not_called()

    def test_refused_by_the_array(self):
        module = _module(host=HOST, port=8080)
        blade = _blade(write=_error("Invalid proxy."))
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == "Set phone home proxy failed. Error: Invalid proxy."


class TestPurefbProxyUpdate:
    """state=present compares the proxy the array holds with the one asked for."""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize(
        "proxy, secure", [(HTTPS_PROXY, True), (HTTP_PROXY, False)]
    )
    def test_current_proxy_is_unchanged(self, proxy, secure, check_mode):
        module = _module(check_mode=check_mode, host=HOST, port=8080, secure=secure)
        blade = _blade(proxy=proxy)
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": False}
        blade.patch_support.assert_not_called()

    @pytest.mark.parametrize(
        "params, expected",
        [
            ({"host": HOST, "port": 8081}, "https://proxy.example.com:8081"),
            ({"host": HOST, "port": 8080, "secure": False}, HTTP_PROXY),
            (
                {"host": "other.example.com", "port": 8080},
                "https://other.example.com:8080",
            ),
        ],
    )
    def test_proxy_is_replaced(self, params, expected):
        module = _module(**params)
        blade = _blade(proxy=HTTPS_PROXY)
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        assert _sent(blade) == expected

    def test_check_mode_sends_nothing(self):
        module = _module(check_mode=True, host=HOST, port=8081)
        blade = _blade(proxy=HTTPS_PROXY)
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        blade.patch_support.assert_not_called()

    def test_refused_by_the_array(self):
        module = _module(host=HOST, port=8081)
        blade = _blade(proxy=HTTPS_PROXY, write=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == "Phone home proxy update failed. Error: " + REFUSED


class TestPurefbProxyMain:
    """Argument handling of main()."""

    def test_missing_sdk(self):
        module = _module(host=HOST, port=8080)
        blade = _blade()
        assert _run(module, blade, sdk=False).outcome == "fail"
        assert _failure(module) == "py-pure-client SDK is required for this module"
        blade.get_support.assert_not_called()

    def test_check_mode_is_supported_and_host_needs_port(self):
        module = _module(host=HOST, port=8080)
        run = _run(module, _blade())
        kwargs = run.ansible_module.call_args[1]
        assert kwargs["supports_check_mode"] is True
        assert kwargs["required_together"] == [["host", "port"]]

    def test_present_needs_host_and_port(self):
        module = _module(host=HOST, port=8080)
        run = _run(module, _blade())
        kwargs = run.ansible_module.call_args[1]
        assert kwargs["required_if"] == [["state", "present", ["host", "port"]]]

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("proxy", [None, HTTPS_PROXY])
    @pytest.mark.parametrize(
        "params, missing",
        [
            ({}, "host, port"),
            ({"host": None, "port": None}, "host, port"),
            ({"host": None, "port": 8080}, "host"),
            ({"host": HOST, "port": None}, "port"),
        ],
    )
    def test_present_with_a_null_host_or_port_is_refused(
        self, params, missing, proxy, check_mode
    ):
        """An option given as null passes the argument check: the module refuses it."""
        module = _module(check_mode=check_mode, **params)
        blade = _blade(proxy=proxy)
        run = _run(module, blade)
        assert run.outcome == "fail"
        assert _failure(module) == (
            "state is present but all of the following are missing: " + missing
        )
        run.get_system.assert_not_called()
        blade.get_support.assert_not_called()
        blade.patch_support.assert_not_called()

    @pytest.mark.parametrize(
        "params", [{}, {"host": None, "port": 8080}, {"host": HOST, "port": None}]
    )
    def test_absent_takes_a_null_host_or_port(self, params):
        """state=absent uses neither option, so a null one is no reason to refuse."""
        module = _module(state="absent", **params)
        blade = _blade(proxy=HTTPS_PROXY)
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        assert _sent(blade) == ""
