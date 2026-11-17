# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for the fleet context parameter of the purefb_dns module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from unittest.mock import Mock, patch, MagicMock, call

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

from plugins.modules.purefb_dns import (
    main,
    _context_kwargs,
    CONTEXT_API_VERSION,
)

MODULE = "plugins.modules.purefb_dns"
MEMBER = "fleet-member-2"
NAME = "cc76-dns"


class _FakeLooseVersion:
    """Minimal LooseVersion stand-in that compares dotted integer versions."""

    def __init__(self, version):
        self.parts = tuple(int(part) for part in str(version).split("."))

    def __lt__(self, other):
        return self.parts < other.parts

    def __le__(self, other):
        return self.parts <= other.parts

    def __gt__(self, other):
        return self.parts > other.parts

    def __ge__(self, other):
        return self.parts >= other.parts


def _base_params(**overrides):
    params = {
        "state": "present",
        "name": NAME,
        "domain": "cc76.example.com",
        "source": None,
        "nameservers": ["9.9.9.9"],
        "service": "data",
        "context": "",
        "ca_certificate": None,
        "ca_certificate_group": None,
    }
    params.update(overrides)
    return params


def _module(params, check_mode=False):
    module = Mock()
    module.params = params
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _response(status_code=200, items=None):
    res = Mock()
    res.status_code = status_code
    res.items = items if items is not None else []
    res.errors = []
    return res


def _existing(name=NAME, domain="cc76.example.com", nameservers=None, source=None):
    dns = Mock()
    dns.name = name
    dns.domain = domain
    dns.nameservers = nameservers if nameservers is not None else ["9.9.9.9"]
    if source:
        ref = Mock()
        ref.name = source
        dns.sources = [ref]
    else:
        dns.sources = []
    return dns


def _run(module, blade, api_version="2.30"):
    """Run main() against a mocked array negotiated at api_version."""
    with patch(MODULE + ".AnsibleModule", return_value=module), patch(
        MODULE + ".get_system", return_value=blade
    ), patch(MODULE + ".get_rest_api_version", return_value=api_version), patch(
        MODULE + ".LooseVersion", _FakeLooseVersion
    ), patch(
        MODULE + ".remove_duplicates", side_effect=lambda value: value
    ), patch(
        MODULE + ".get_error_message", return_value="Cannot find array in fleet"
    ):
        try:
            main()
        except SystemExit:
            pass


class TestContextKwargs:
    """_context_kwargs helper"""

    def test_returns_empty_without_context(self):
        module = Mock()
        module.params = {"context": ""}
        assert _context_kwargs(module) == {}

    def test_returns_context_names_when_set(self):
        module = Mock()
        module.params = {"context": MEMBER}
        assert _context_kwargs(module) == {"context_names": [MEMBER]}

    def test_gate_matches_sdk_signature(self):
        """get/post/patch/delete_dns gained context_names at REST 2.25"""
        assert CONTEXT_API_VERSION == "2.25"


class TestPurefbDnsContext:
    """main() flows with and without a fleet context"""

    # ---------------- version gate ----------------

    def test_context_below_gate_fails_before_any_call(self):
        module = _module(_base_params(context=MEMBER))
        blade = Mock()

        _run(module, blade, api_version="2.24")

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "context requires REST API 2.25" in msg
        blade.get_dns.assert_not_called()
        blade.post_dns.assert_not_called()
        blade.patch_dns.assert_not_called()
        blade.delete_dns.assert_not_called()

    def test_context_below_gate_fails_in_check_mode_too(self):
        module = _module(_base_params(context=MEMBER), check_mode=True)
        blade = Mock()

        _run(module, blade, api_version="2.17")

        module.fail_json.assert_called_once()
        blade.get_dns.assert_not_called()

    def test_no_context_below_gate_is_not_gated(self):
        """An empty context never trips the gate on an older array"""
        module = _module(_base_params())
        blade = Mock()
        blade.get_dns.return_value = _response(items=[_existing(name="management")])
        blade.post_dns.return_value = _response()

        _run(module, blade, api_version="2.24")

        module.fail_json.assert_not_called()
        blade.get_dns.assert_called_once_with()
        assert "context_names" not in blade.post_dns.call_args[1]

    def test_context_at_gate_is_accepted(self):
        module = _module(_base_params(context=MEMBER))
        blade = Mock()
        blade.get_dns.return_value = _response(items=[_existing(name="management")])
        blade.post_dns.return_value = _response()

        _run(module, blade, api_version="2.25")

        module.fail_json.assert_not_called()
        blade.post_dns.assert_called_once()
        assert blade.post_dns.call_args[1]["context_names"] == [MEMBER]

    # ---------------- create ----------------

    def test_create_sends_context(self):
        module = _module(_base_params(context=MEMBER))
        blade = Mock()
        blade.get_dns.return_value = _response(items=[_existing(name="management")])
        blade.post_dns.return_value = _response()

        _run(module, blade)

        blade.get_dns.assert_called_once_with(context_names=[MEMBER])
        kwargs = blade.post_dns.call_args[1]
        assert kwargs["names"] == [NAME]
        assert kwargs["context_names"] == [MEMBER]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_without_context_omits_kwarg(self):
        module = _module(_base_params())
        blade = Mock()
        blade.get_dns.return_value = _response(items=[_existing(name="management")])
        blade.post_dns.return_value = _response()

        _run(module, blade)

        blade.get_dns.assert_called_once_with()
        kwargs = blade.post_dns.call_args[1]
        assert kwargs["names"] == [NAME]
        assert "context_names" not in kwargs
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_with_source_sends_context(self):
        module = _module(_base_params(context=MEMBER, source="cc76-vip"))
        blade = Mock()
        blade.get_dns.return_value = _response(items=[_existing(name="management")])
        blade.post_dns.return_value = _response()

        _run(module, blade)

        blade.post_dns.assert_called_once()
        assert blade.post_dns.call_args[1]["context_names"] == [MEMBER]

    def test_create_management_service_sends_context(self):
        module = _module(_base_params(context=MEMBER, service="management"))
        blade = Mock()
        blade.get_dns.return_value = _response(items=[_existing(name="management")])
        blade.post_dns.return_value = _response()

        _run(module, blade)

        blade.post_dns.assert_called_once()
        assert blade.post_dns.call_args[1]["context_names"] == [MEMBER]

    def test_create_check_mode_with_context_skips_post(self):
        module = _module(_base_params(context=MEMBER), check_mode=True)
        blade = Mock()
        blade.get_dns.return_value = _response(items=[_existing(name="management")])

        _run(module, blade)

        blade.post_dns.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    # ---------------- source check ----------------

    def test_source_check_skipped_with_context(self):
        """get_network_interfaces has no context, so it is not consulted"""
        module = _module(_base_params(context=MEMBER, source="cc76-vip"))
        blade = Mock()
        blade.get_dns.return_value = _response(items=[_existing(name="management")])
        blade.post_dns.return_value = _response()

        _run(module, blade)

        blade.get_network_interfaces.assert_not_called()
        module.fail_json.assert_not_called()

    def test_source_check_runs_without_context(self):
        module = _module(_base_params(source="cc76-vip"))
        blade = Mock()
        blade.get_dns.return_value = _response(items=[_existing(name="management")])
        blade.get_network_interfaces.return_value = _response(status_code=400)

        _run(module, blade)

        blade.get_network_interfaces.assert_called_once_with(names=["cc76-vip"])
        module.fail_json.assert_called_once()
        assert "does not exist" in module.fail_json.call_args[1]["msg"]
        blade.post_dns.assert_not_called()

    # ---------------- update ----------------

    def test_update_sends_context(self):
        module = _module(_base_params(context=MEMBER, nameservers=["149.112.112.112"]))
        blade = Mock()
        blade.get_dns.return_value = _response(items=[_existing()])
        blade.patch_dns.return_value = _response()

        _run(module, blade)

        assert blade.get_dns.call_args_list == [
            call(context_names=[MEMBER]),
            call(names=[NAME], context_names=[MEMBER]),
        ]
        kwargs = blade.patch_dns.call_args[1]
        assert kwargs["names"] == [NAME]
        assert kwargs["context_names"] == [MEMBER]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_without_context_omits_kwarg(self):
        module = _module(_base_params(nameservers=["149.112.112.112"]))
        blade = Mock()
        blade.get_dns.return_value = _response(items=[_existing()])
        blade.patch_dns.return_value = _response()

        _run(module, blade)

        assert blade.get_dns.call_args_list == [call(), call(names=[NAME])]
        kwargs = blade.patch_dns.call_args[1]
        assert kwargs["names"] == [NAME]
        assert "context_names" not in kwargs
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_idempotent_with_context(self):
        module = _module(_base_params(context=MEMBER))
        blade = Mock()
        blade.get_dns.return_value = _response(items=[_existing()])

        _run(module, blade)

        blade.patch_dns.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_check_mode_with_context_skips_patch(self):
        module = _module(
            _base_params(context=MEMBER, domain="ctx.cc76.example.com"),
            check_mode=True,
        )
        blade = Mock()
        blade.get_dns.return_value = _response(items=[_existing()])

        _run(module, blade)

        blade.patch_dns.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_api_error_with_context_fails(self):
        module = _module(_base_params(context=MEMBER, domain="ctx.cc76.example.com"))
        blade = Mock()
        blade.get_dns.return_value = _response(items=[_existing()])
        blade.patch_dns.return_value = _response(status_code=400)

        _run(module, blade)

        module.fail_json.assert_called_once()
        assert "Update to DNS configuration" in module.fail_json.call_args[1]["msg"]

    # ---------------- delete ----------------

    def test_delete_sends_context(self):
        module = _module(_base_params(context=MEMBER, state="absent"))
        blade = Mock()
        blade.get_dns.return_value = _response(items=[_existing()])
        blade.delete_dns.return_value = _response()

        _run(module, blade)

        blade.delete_dns.assert_called_once_with(names=[NAME], context_names=[MEMBER])
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_without_context_omits_kwarg(self):
        module = _module(_base_params(state="absent"))
        blade = Mock()
        blade.get_dns.return_value = _response(items=[_existing()])
        blade.delete_dns.return_value = _response()

        _run(module, blade)

        blade.delete_dns.assert_called_once_with(names=[NAME])
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_check_mode_with_context_skips_delete(self):
        module = _module(_base_params(context=MEMBER, state="absent"), check_mode=True)
        blade = Mock()
        blade.get_dns.return_value = _response(items=[_existing()])

        _run(module, blade)

        blade.delete_dns.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_absent_with_context_is_noop(self):
        module = _module(_base_params(context=MEMBER, state="absent"))
        blade = Mock()
        blade.get_dns.return_value = _response(items=[_existing(name="management")])

        _run(module, blade)

        blade.delete_dns.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    # ---------------- unknown context ----------------

    def test_unknown_context_read_error_fails_cleanly(self):
        """The array answers 400 for a name outside the fleet"""
        module = _module(_base_params(context="cc76-nomember"))
        blade = Mock()
        blade.get_dns.return_value = _response(status_code=400)

        _run(module, blade)

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to read DNS configurations" in msg
        assert "Cannot find array in fleet" in msg
        blade.post_dns.assert_not_called()
        blade.patch_dns.assert_not_called()
        blade.delete_dns.assert_not_called()
