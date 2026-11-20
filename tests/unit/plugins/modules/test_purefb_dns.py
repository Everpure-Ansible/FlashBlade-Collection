# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_dns module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from unittest.mock import Mock, call, patch, MagicMock

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

from plugins.modules.purefb_dns import (
    main,
    _all_https,
    _fail_if_ca_without_https,
    _find_config,
    _https_host,
    _is_https,
    _is_ip_address,
    _realm_of,
    _reference_name,
    _same_name,
    _validate_nameservers,
)
from plugins.module_utils.version import LooseVersion as RealLooseVersion

MODULE = "plugins.modules.purefb_dns"
DOH = "https://192.0.2.53/dns-query"
IP = "192.0.2.53"


def _dedupe(items):
    return list(dict.fromkeys(items))


def _ref(name):
    """Stand-in for pypureclient Reference: a plain dict is easy to assert on."""
    return {"name": name}


def _body(**kwargs):
    """Stand-in for the Dns / DnsPost models: the request body as a dict."""
    return kwargs


def _base_params(**overrides):
    params = {
        "name": "cc46-dns",
        "state": "present",
        "domain": "example.com",
        "source": None,
        "nameservers": None,
        "service": "data",
        "ca_certificate": None,
        "ca_certificate_group": None,
        "context": "",
    }
    params.update(overrides)
    return params


def _module(check_mode=False, **overrides):
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.check_mode = check_mode
    module.params = _base_params(**overrides)
    return module


def _dns(
    name="cc46-dns",
    domain="example.com",
    nameservers=None,
    ca_certificate=None,
    ca_certificate_group=None,
    source=None,
):
    """A DNS configuration as the SDK returns it; absent CA fields raise on getattr."""
    attrs = ["name", "domain", "nameservers", "sources", "services"]
    if ca_certificate:
        attrs.append("ca_certificate")
    if ca_certificate_group:
        attrs.append("ca_certificate_group")
    obj = Mock(spec=attrs)
    obj.name = name
    obj.domain = domain
    obj.nameservers = nameservers or [IP]
    obj.sources = []
    if source:
        reference = Mock(spec=["name"])
        reference.name = source
        obj.sources = [reference]
    obj.services = ["data"]
    if ca_certificate:
        obj.ca_certificate = Mock(spec=["name"])
        obj.ca_certificate.name = ca_certificate
    if ca_certificate_group:
        obj.ca_certificate_group = Mock(spec=["name"])
        obj.ca_certificate_group.name = ca_certificate_group
    return obj


def _response(status_code=200, items=None):
    res = Mock()
    res.status_code = status_code
    res.items = items or []
    res.errors = []
    return res


def _refused(message, status_code=400):
    """An error response as the SDK returns it: errors, and no items at all."""
    res = Mock(spec=["status_code", "errors"])
    res.status_code = status_code
    error = Mock(spec=["message"])
    error.message = message
    res.errors = [error]
    return res


def _error_message(res):
    """Stand-in for get_error_message: the first error of the response."""
    errors = getattr(res, "errors", None)
    return errors[0].message if errors else "boom"


def _blade(configs):
    """Blade whose GET /dns returns the given configurations; writes succeed."""
    blade = Mock()
    blade.get_dns.return_value = _response(items=configs)
    blade.get_certificates.return_value = _response()
    blade.get_certificate_groups.return_value = _response()
    blade.get_network_interfaces.return_value = _response()
    blade.post_dns.return_value = _response()
    blade.patch_dns.return_value = _response()
    blade.delete_dns.return_value = _response()
    return blade


def _run():
    try:
        main()
    except SystemExit:
        pass


def _common(api_version="2.30"):
    """Patches shared by every main() test."""

    def decorator(func):
        for target in (
            patch(MODULE + ".HAS_PYPURECLIENT", True),
            patch(MODULE + ".LooseVersion", RealLooseVersion),
            patch(MODULE + ".get_rest_api_version", Mock(return_value=api_version)),
            patch(MODULE + ".remove_duplicates", _dedupe),
            patch(MODULE + ".get_error_message", _error_message),
            patch(MODULE + ".Reference", _ref),
            patch(MODULE + ".Dns", _body),
            patch(MODULE + ".DnsPost", _body),
        ):
            func = target(func)
        return func

    return decorator


class TestPurefbDnsHelpers:
    """Helper-function unit tests"""

    def test_is_https(self):
        assert _is_https(DOH)
        assert _is_https("HTTPS://192.0.2.53/dns-query")
        assert not _is_https(IP)
        assert not _is_https("http://192.0.2.53/dns-query")

    def test_all_https(self):
        assert _all_https([DOH, "https://192.0.2.54/dns-query"])
        assert not _all_https([DOH, IP])
        assert not _all_https([IP])
        assert not _all_https([])
        assert not _all_https(None)

    def test_https_host(self):
        assert _https_host(DOH) == IP
        assert _https_host("https://192.0.2.53:8443/dns-query") == IP
        assert _https_host("https://192.0.2.53") == IP
        assert _https_host("https://[2001:db8::53]:853/dns-query") == "2001:db8::53"
        assert _https_host("https://dns.example.com/dns-query") == "dns.example.com"

    def test_is_ip_address(self):
        assert _is_ip_address(IP)
        assert _is_ip_address("2001:db8::53")
        assert not _is_ip_address("dns.example.com")
        assert not _is_ip_address("192.0.2")
        assert not _is_ip_address("")

    def test_reference_name(self):
        assert _reference_name(_dns(ca_certificate="cc46-cert"), "ca_certificate") == (
            "cc46-cert"
        )
        assert _reference_name(_dns(), "ca_certificate") is None
        assert _reference_name(_dns(), "ca_certificate_group") is None

    def test_validate_nameservers_accepts_all_ip_and_all_https(self):
        module = _module()
        _validate_nameservers(module, [IP, "192.0.2.54"])
        _validate_nameservers(module, [DOH, "https://[2001:db8::53]/dns-query"])
        module.fail_json.assert_not_called()

    def test_validate_nameservers_rejects_mix(self):
        module = _module()
        try:
            _validate_nameservers(module, [DOH, IP])
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "not a mix" in module.fail_json.call_args[1]["msg"]

    def test_validate_nameservers_rejects_hostname(self):
        module = _module()
        try:
            _validate_nameservers(module, ["https://dns.example.com/dns-query"])
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "hostname" in module.fail_json.call_args[1]["msg"]

    def test_fail_if_ca_without_https(self):
        module = _module()
        _fail_if_ca_without_https(module, None, [IP])
        _fail_if_ca_without_https(module, "ca_certificate", [DOH])
        module.fail_json.assert_not_called()
        for nameservers in ([IP], [DOH, IP], [], None):
            try:
                _fail_if_ca_without_https(module, "ca_certificate", nameservers)
            except SystemExit:
                pass
        assert module.fail_json.call_count == 4
        assert "ca_certificate" in module.fail_json.call_args[1]["msg"]


class TestPurefbDnsMain:
    """main() flows on a REST 2.15+ array"""

    @_common()
    @patch(MODULE + ".purefb_argument_spec", Mock(return_value={}))
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_argument_spec_makes_ca_options_mutually_exclusive(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(state="absent", name="other")
        mock_ansible_module.return_value = module
        mock_get_system.return_value = _blade([_dns(name="management")])

        _run()

        assert mock_ansible_module.call_args[1]["mutually_exclusive"] == [
            ["ca_certificate", "ca_certificate_group"]
        ]
        spec = mock_ansible_module.call_args[0][0]
        assert spec["ca_certificate"] == {"type": "str"}
        assert spec["ca_certificate_group"] == {"type": "str"}

    # ---------------- create ----------------

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_create_with_ca_certificate(self, mock_ansible_module, mock_get_system):
        module = _module(nameservers=[DOH], ca_certificate="cc46-cert")
        mock_ansible_module.return_value = module
        blade = _blade([_dns(name="management")])
        mock_get_system.return_value = blade

        _run()

        blade.get_certificates.assert_called_once_with(names=["cc46-cert"])
        blade.post_dns.assert_called_once()
        assert blade.post_dns.call_args[1]["names"] == ["cc46-dns"]
        assert blade.post_dns.call_args[1]["dns"] == {
            "services": ["data"],
            "domain": "example.com",
            "nameservers": [DOH],
            "ca_certificate": {"name": "cc46-cert"},
        }
        assert module.exit_json.call_args[1]["changed"] is True

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_create_with_ca_certificate_group(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(nameservers=[DOH], ca_certificate_group="cc46-grp")
        mock_ansible_module.return_value = module
        blade = _blade([_dns(name="management")])
        mock_get_system.return_value = blade

        _run()

        blade.get_certificate_groups.assert_called_once_with(names=["cc46-grp"])
        blade.get_certificates.assert_not_called()
        body = blade.post_dns.call_args[1]["dns"]
        assert body["ca_certificate_group"] == {"name": "cc46-grp"}
        assert "ca_certificate" not in body
        assert module.exit_json.call_args[1]["changed"] is True

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_create_plain_ip_sends_no_ca_fields(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(nameservers=[IP, IP, "192.0.2.54"], source="vip1")
        mock_ansible_module.return_value = module
        blade = _blade([_dns(name="management")])
        mock_get_system.return_value = blade

        _run()

        blade.get_certificates.assert_not_called()
        blade.get_certificate_groups.assert_not_called()
        assert blade.post_dns.call_args[1]["dns"] == {
            "services": ["data"],
            "domain": "example.com",
            "nameservers": [IP, "192.0.2.54"],
            "sources": [{"name": "vip1"}],
        }

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_create_management_service_ignores_source(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(
            name="mgmt2", nameservers=[IP], service="management", source="vip1"
        )
        mock_ansible_module.return_value = module
        blade = _blade([_dns(name="management")])
        mock_get_system.return_value = blade

        _run()

        assert blade.post_dns.call_args[1]["dns"] == {
            "services": ["management"],
            "domain": "example.com",
            "nameservers": [IP],
        }

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_create_check_mode_skips_post(self, mock_ansible_module, mock_get_system):
        module = _module(check_mode=True, nameservers=[DOH], ca_certificate="cc46-cert")
        mock_ansible_module.return_value = module
        blade = _blade([_dns(name="management")])
        mock_get_system.return_value = blade

        _run()

        blade.post_dns.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_create_ca_without_nameservers_fails(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(ca_certificate="cc46-cert")
        mock_ansible_module.return_value = module
        blade = _blade([_dns(name="management")])
        mock_get_system.return_value = blade

        _run()

        blade.post_dns.assert_not_called()
        module.fail_json.assert_called_once()
        assert "https://" in module.fail_json.call_args[1]["msg"]

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_create_api_error_is_reported(self, mock_ansible_module, mock_get_system):
        module = _module(nameservers=[DOH], ca_certificate="cc46-cert")
        mock_ansible_module.return_value = module
        blade = _blade([_dns(name="management")])
        blade.post_dns.return_value = _response(status_code=400)
        mock_get_system.return_value = blade

        _run()

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "cc46-dns" in msg
        assert "boom" in msg

    # ---------------- validation before any write ----------------

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_ca_with_ip_nameservers_fails_before_write(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(nameservers=[IP], ca_certificate="cc46-cert")
        mock_ansible_module.return_value = module
        blade = _blade([_dns()])
        mock_get_system.return_value = blade

        _run()

        blade.get_dns.assert_not_called()
        blade.post_dns.assert_not_called()
        blade.patch_dns.assert_not_called()
        module.fail_json.assert_called_once()
        assert "ca_certificate" in module.fail_json.call_args[1]["msg"]

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_mixed_nameservers_fail_before_write(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(nameservers=[DOH, IP], ca_certificate="cc46-cert")
        mock_ansible_module.return_value = module
        blade = _blade([_dns()])
        mock_get_system.return_value = blade

        _run()

        blade.patch_dns.assert_not_called()
        blade.post_dns.assert_not_called()
        assert "not a mix" in module.fail_json.call_args[1]["msg"]

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_https_hostname_fails_before_write(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(
            nameservers=["https://dns.example.com/dns-query"],
            ca_certificate="cc46-cert",
        )
        mock_ansible_module.return_value = module
        blade = _blade([_dns()])
        mock_get_system.return_value = blade

        _run()

        blade.patch_dns.assert_not_called()
        assert "hostname" in module.fail_json.call_args[1]["msg"]

    @_common(api_version="2.24")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_version_gate_https_nameservers(self, mock_ansible_module, mock_get_system):
        module = _module(nameservers=[DOH])
        mock_ansible_module.return_value = module
        blade = _blade([_dns()])
        mock_get_system.return_value = blade

        _run()

        blade.get_dns.assert_not_called()
        blade.patch_dns.assert_not_called()
        module.fail_json.assert_called_once()
        assert "2.25" in module.fail_json.call_args[1]["msg"]

    @_common(api_version="2.24")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_version_gate_ca_option(self, mock_ansible_module, mock_get_system):
        module = _module(ca_certificate_group="cc46-grp")
        mock_ansible_module.return_value = module
        blade = _blade([_dns()])
        mock_get_system.return_value = blade

        _run()

        blade.get_certificate_groups.assert_not_called()
        blade.patch_dns.assert_not_called()
        assert "2.25" in module.fail_json.call_args[1]["msg"]

    @_common(api_version="2.24")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_plain_ip_update_still_works_below_doh_version(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(nameservers=["192.0.2.54"])
        mock_ansible_module.return_value = module
        blade = _blade([_dns()])
        mock_get_system.return_value = blade

        _run()

        module.fail_json.assert_not_called()
        assert blade.patch_dns.call_args[1]["dns"] == {
            "domain": "example.com",
            "nameservers": ["192.0.2.54"],
        }

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_missing_certificate_fails_before_write(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(nameservers=[DOH], ca_certificate="cc46-missing")
        mock_ansible_module.return_value = module
        blade = _blade([_dns(name="management")])
        blade.get_certificates.return_value = _refused("Certificate does not exist.")
        mock_get_system.return_value = blade

        _run()

        blade.post_dns.assert_not_called()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Certificate cc46-missing does not exist" in msg

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_missing_certificate_group_fails_before_write(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(nameservers=[DOH], ca_certificate_group="cc46-missing")
        mock_ansible_module.return_value = module
        blade = _blade([_dns()])
        blade.get_certificate_groups.return_value = _refused(
            "Certificate group does not exist."
        )
        mock_get_system.return_value = blade

        _run()

        blade.patch_dns.assert_not_called()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Certificate group cc46-missing does not exist" in msg

    # ---------------- update ----------------

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_update_moves_to_https_with_ca_in_one_patch(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(nameservers=[DOH], ca_certificate="cc46-cert")
        mock_ansible_module.return_value = module
        blade = _blade([_dns()])
        mock_get_system.return_value = blade

        _run()

        blade.patch_dns.assert_called_once()
        assert blade.patch_dns.call_args[1]["names"] == ["cc46-dns"]
        assert blade.patch_dns.call_args[1]["dns"] == {
            "domain": "example.com",
            "nameservers": [DOH],
            "ca_certificate": {"name": "cc46-cert"},
        }
        assert module.exit_json.call_args[1]["changed"] is True

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_update_idempotent_when_ca_matches(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(nameservers=[DOH], ca_certificate="cc46-cert")
        mock_ansible_module.return_value = module
        blade = _blade([_dns(nameservers=[DOH], ca_certificate="cc46-cert")])
        mock_get_system.return_value = blade

        _run()

        blade.patch_dns.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_update_changes_ca_on_existing_https_config(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(ca_certificate="cc46-other")
        mock_ansible_module.return_value = module
        blade = _blade([_dns(nameservers=[DOH], ca_certificate="cc46-cert")])
        mock_get_system.return_value = blade

        _run()

        # nameservers always travel with a CA change: the array rejects a
        # certificate change without them
        assert blade.patch_dns.call_args[1]["dns"] == {
            "domain": "example.com",
            "nameservers": [DOH],
            "ca_certificate": {"name": "cc46-other"},
        }
        assert module.exit_json.call_args[1]["changed"] is True

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_update_swaps_certificate_for_group(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(ca_certificate_group="cc46-grp")
        mock_ansible_module.return_value = module
        blade = _blade([_dns(nameservers=[DOH], ca_certificate="cc46-cert")])
        mock_get_system.return_value = blade

        _run()

        body = blade.patch_dns.call_args[1]["dns"]
        assert body["ca_certificate_group"] == {"name": "cc46-grp"}
        assert "ca_certificate" not in body
        assert module.exit_json.call_args[1]["changed"] is True

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_update_swaps_group_for_certificate(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(ca_certificate="cc46-cert")
        mock_ansible_module.return_value = module
        blade = _blade([_dns(nameservers=[DOH], ca_certificate_group="cc46-grp")])
        mock_get_system.return_value = blade

        _run()

        blade.get_certificates.assert_called_once_with(names=["cc46-cert"])
        assert blade.patch_dns.call_args[1]["dns"] == {
            "domain": "example.com",
            "nameservers": [DOH],
            "ca_certificate": {"name": "cc46-cert"},
        }
        assert module.exit_json.call_args[1]["changed"] is True

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_update_new_https_nameservers_carry_current_ca(
        self, mock_ansible_module, mock_get_system
    ):
        """New https:// nameservers without a CA option keep the current CA."""
        new_doh = "https://192.0.2.54/dns-query"
        module = _module(nameservers=[new_doh])
        mock_ansible_module.return_value = module
        blade = _blade([_dns(nameservers=[DOH], ca_certificate="cc46-cert")])
        mock_get_system.return_value = blade

        _run()

        blade.get_certificates.assert_not_called()
        assert blade.patch_dns.call_args[1]["dns"] == {
            "domain": "example.com",
            "nameservers": [new_doh],
            "ca_certificate": {"name": "cc46-cert"},
        }
        assert module.exit_json.call_args[1]["changed"] is True

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_update_revert_to_ip_sends_no_ca(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(nameservers=[IP])
        mock_ansible_module.return_value = module
        blade = _blade([_dns(nameservers=[DOH], ca_certificate="cc46-cert")])
        mock_get_system.return_value = blade

        _run()

        assert blade.patch_dns.call_args[1]["dns"] == {
            "domain": "example.com",
            "nameservers": [IP],
        }
        assert module.exit_json.call_args[1]["changed"] is True

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_update_domain_only_carries_current_ca(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(domain="example.net")
        mock_ansible_module.return_value = module
        blade = _blade([_dns(nameservers=[DOH], ca_certificate_group="cc46-grp")])
        mock_get_system.return_value = blade

        _run()

        blade.get_certificate_groups.assert_not_called()
        assert blade.patch_dns.call_args[1]["dns"] == {
            "domain": "example.net",
            "nameservers": [DOH],
            "ca_certificate_group": {"name": "cc46-grp"},
        }
        assert module.exit_json.call_args[1]["changed"] is True

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_update_ca_on_ip_config_without_nameservers_fails(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(ca_certificate="cc46-cert")
        mock_ansible_module.return_value = module
        blade = _blade([_dns()])
        mock_get_system.return_value = blade

        _run()

        blade.patch_dns.assert_not_called()
        module.fail_json.assert_called_once()
        assert "https://" in module.fail_json.call_args[1]["msg"]

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_update_check_mode_skips_patch(self, mock_ansible_module, mock_get_system):
        module = _module(check_mode=True, nameservers=[DOH], ca_certificate="cc46-cert")
        mock_ansible_module.return_value = module
        blade = _blade([_dns()])
        mock_get_system.return_value = blade

        _run()

        blade.patch_dns.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_update_keeps_source_fix(self, mock_ansible_module, mock_get_system):
        """A source given by the caller is sent as a reference; none otherwise."""
        module = _module(nameservers=[DOH], ca_certificate="cc46-cert", source="vip1")
        mock_ansible_module.return_value = module
        blade = _blade([_dns()])
        mock_get_system.return_value = blade

        _run()

        assert blade.patch_dns.call_args[1]["dns"]["sources"] == [{"name": "vip1"}]

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_update_api_error_is_reported(self, mock_ansible_module, mock_get_system):
        module = _module(nameservers=[DOH])
        mock_ansible_module.return_value = module
        blade = _blade([_dns()])
        blade.patch_dns.return_value = _response(status_code=400)
        mock_get_system.return_value = blade

        _run()

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "cc46-dns" in msg
        assert "boom" in msg

    # ---------------- delete ----------------

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_delete_existing(self, mock_ansible_module, mock_get_system):
        module = _module(state="absent")
        mock_ansible_module.return_value = module
        blade = _blade([_dns()])
        mock_get_system.return_value = blade

        _run()

        blade.delete_dns.assert_called_once_with(names=["cc46-dns"])
        assert module.exit_json.call_args[1]["changed"] is True

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_delete_missing_is_noop(self, mock_ansible_module, mock_get_system):
        module = _module(state="absent")
        mock_ansible_module.return_value = module
        blade = _blade([_dns(name="management")])
        mock_get_system.return_value = blade

        _run()

        blade.delete_dns.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @_common()
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_delete_management_refused(self, mock_ansible_module, mock_get_system):
        module = _module(state="absent", name="management")
        mock_ansible_module.return_value = module
        blade = _blade([_dns(name="management")])
        mock_get_system.return_value = blade

        _run()

        blade.delete_dns.assert_not_called()
        assert "cannot be deleted" in module.fail_json.call_args[1]["msg"]


# ---------------- names without regard to case, realms, refused reads ----------------

RDNS = "realm-1::cc46-dns"
RVIP = "realm-1::cc46-vip"
RCERT = "realm-1::cc46-cert"


def _named(name):
    obj = Mock(spec=["name"])
    obj.name = name
    return obj


def _by_name(objects, kind):
    """A GET that answers as the array does.

    Names match without regard to case, the stored spelling comes back, and
    a name the array does not hold is a 400 "<kind> does not exist.".
    """

    def get(names=None, **_kwargs):
        if names is None:
            return _response(items=list(objects))
        wanted = [name.lower() for name in names]
        found = [obj for obj in objects if obj.name.lower() in wanted]
        if len(found) != len(wanted):
            return _refused("{0} does not exist.".format(kind))
        return _response(items=found)

    return Mock(side_effect=get)


def _array(configs, interfaces=(), certificates=(), groups=()):
    """Blade holding the given objects; writes succeed."""
    blade = Mock()
    blade.get_dns = _by_name(configs, "DNS")
    blade.get_network_interfaces = _by_name(
        [_named(name) for name in interfaces], "Network"
    )
    blade.get_certificates = _by_name(
        [_named(name) for name in certificates], "Certificate"
    )
    blade.get_certificate_groups = _by_name(
        [_named(name) for name in groups], "Certificate group"
    )
    blade.post_dns.return_value = _response()
    blade.patch_dns.return_value = _response()
    blade.delete_dns.return_value = _response()
    return blade


def _main(module, blade, api_version="2.30"):
    """Run main() for one task against one array."""
    with patch(MODULE + ".AnsibleModule", return_value=module), patch(
        MODULE + ".get_system", return_value=blade
    ), patch(MODULE + ".HAS_PYPURECLIENT", True), patch(
        MODULE + ".LooseVersion", RealLooseVersion
    ), patch(
        MODULE + ".get_rest_api_version", Mock(return_value=api_version)
    ), patch(
        MODULE + ".remove_duplicates", _dedupe
    ), patch(
        MODULE + ".get_error_message", _error_message
    ), patch(
        MODULE + ".Reference", _ref
    ), patch(
        MODULE + ".Dns", _body
    ), patch(
        MODULE + ".DnsPost", _body
    ):
        _run()


def _no_write(blade):
    blade.post_dns.assert_not_called()
    blade.patch_dns.assert_not_called()
    blade.delete_dns.assert_not_called()


class TestPurefbDnsRealmHelpers:
    """Name helpers"""

    def test_realm_of(self):
        assert _realm_of(RDNS) == "realm-1"
        assert _realm_of("cc46-dns") == ""
        assert _realm_of("") == ""
        assert _realm_of(None) == ""

    def test_same_name_ignores_case(self):
        assert _same_name("REALM-1::cc46-dns", "realm-1::CC46-DNS")
        assert _same_name(None, "")
        assert not _same_name(RDNS, "cc46-dns")

    def test_find_config_returns_the_stored_object(self):
        configs = [_dns(name="management"), _dns(name=RDNS)]
        assert _find_config(configs, "REALM-1::CC46-dns") is configs[1]
        assert _find_config(configs, "cc46-dns") is None
        assert _find_config([], "cc46-dns") is None


class TestPurefbDnsLetterCase:
    """The array matches names without regard to case; so does the module"""

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_name_in_another_case_is_the_same_configuration(self, check_mode):
        module = _module(
            check_mode=check_mode,
            name="REALM-1::CC46-DNS",
            nameservers=[IP],
            source=RVIP,
        )
        blade = _array(
            [_dns(name="management"), _dns(name=RDNS, source=RVIP)],
            interfaces=[RVIP],
        )

        _main(module, blade)

        _no_write(blade)
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_name_in_another_case_changes_the_stored_configuration(self):
        module = _module(name="REALM-1::CC46-DNS", domain="example.net")
        blade = _array([_dns(name="management"), _dns(name=RDNS, source=RVIP)])

        _main(module, blade)

        blade.post_dns.assert_not_called()
        assert blade.get_dns.call_args_list[-1] == call(names=[RDNS])
        assert blade.patch_dns.call_args[1]["names"] == [RDNS]
        assert blade.patch_dns.call_args[1]["dns"] == {
            "domain": "example.net",
            "nameservers": [IP],
        }
        assert module.exit_json.call_args[1]["changed"] is True

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_delete_by_a_name_in_another_case(self, check_mode):
        module = _module(check_mode=check_mode, state="absent", name="CC46-DNS")
        blade = _array([_dns(name="management"), _dns()])

        _main(module, blade)

        if check_mode:
            blade.delete_dns.assert_not_called()
        else:
            blade.delete_dns.assert_called_once_with(names=["cc46-dns"])
        assert module.exit_json.call_args[1]["changed"] is True

    def test_management_in_another_case_is_not_deleted(self):
        module = _module(state="absent", name="MANAGEMENT")
        blade = _array([_dns(name="management")])

        _main(module, blade)

        _no_write(blade)
        assert "cannot be deleted" in module.fail_json.call_args[1]["msg"]

    def test_source_in_another_case_is_not_a_change(self):
        module = _module(name=RDNS, source="REALM-1::CC46-VIP")
        blade = _array([_dns(name=RDNS, source=RVIP)], interfaces=[RVIP])

        _main(module, blade)

        _no_write(blade)
        assert module.exit_json.call_args[1]["changed"] is False

    def test_another_source_is_a_change(self):
        new_source = "realm-1::cc46-vip2"
        module = _module(name=RDNS, source=new_source)
        blade = _array([_dns(name=RDNS, source=RVIP)], interfaces=[RVIP, new_source])

        _main(module, blade)

        assert blade.patch_dns.call_args[1]["dns"]["sources"] == [{"name": new_source}]
        assert module.exit_json.call_args[1]["changed"] is True

    @pytest.mark.parametrize(
        "param, stored, wanted",
        [
            ("ca_certificate", RCERT, "REALM-1::CC46-CERT"),
            ("ca_certificate_group", "realm-1::cc46-grp", "Realm-1::CC46-Grp"),
        ],
    )
    def test_ca_reference_in_another_case_is_not_a_change(self, param, stored, wanted):
        module = _module(name=RDNS, nameservers=[DOH], **{param: wanted})
        blade = _array(
            [_dns(name=RDNS, nameservers=[DOH], source=RVIP, **{param: stored})],
            certificates=[stored],
            groups=[stored],
        )

        _main(module, blade)

        _no_write(blade)
        assert module.exit_json.call_args[1]["changed"] is False

    @pytest.mark.parametrize(
        "param, stored, wanted",
        [
            ("ca_certificate", "cc46-cert", "CC46-CERT"),
            ("ca_certificate_group", "cc46-grp", "Cc46-Grp"),
            ("ca_certificate", RCERT, "REALM-1::CC46-CERT"),
        ],
    )
    def test_ca_reference_is_sent_in_the_stored_spelling(self, param, stored, wanted):
        """The array refuses the reference in another case: "... does not exist."."""
        name = RDNS if "::" in stored else "cc46-dns"
        source = RVIP if "::" in stored else None
        module = _module(
            name=name, domain="example.net", nameservers=[DOH], **{param: wanted}
        )
        blade = _array(
            [_dns(name=name, nameservers=[DOH], source=source, **{param: stored})],
            certificates=[stored],
            groups=[stored],
        )

        _main(module, blade)

        module.fail_json.assert_not_called()
        body = blade.patch_dns.call_args[1]["dns"]
        assert body["domain"] == "example.net"
        assert body[param] == {"name": stored}
        assert module.exit_json.call_args[1]["changed"] is True

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_switch_to_a_group_named_in_another_case(self, check_mode):
        module = _module(
            check_mode=check_mode, nameservers=[DOH], ca_certificate_group="CC46-GRP"
        )
        blade = _array(
            [_dns(nameservers=[DOH], ca_certificate="cc46-cert")],
            certificates=["cc46-cert"],
            groups=["cc46-grp"],
        )

        _main(module, blade)

        blade.get_certificate_groups.assert_called_once_with(names=["CC46-GRP"])
        if check_mode:
            _no_write(blade)
        else:
            body = blade.patch_dns.call_args[1]["dns"]
            assert body["ca_certificate_group"] == {"name": "cc46-grp"}
            assert "ca_certificate" not in body
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_sends_the_ca_reference_in_the_stored_spelling(self):
        module = _module(nameservers=[DOH], ca_certificate="CC46-Cert")
        blade = _array([_dns(name="management")], certificates=["cc46-cert"])

        _main(module, blade)

        module.fail_json.assert_not_called()
        assert blade.post_dns.call_args[1]["dns"]["ca_certificate"] == {
            "name": "cc46-cert"
        }

    def test_ca_reference_is_sent_as_given_with_a_context(self):
        """The certificate is read locally; its name belongs to the fleet member."""
        module = _module(
            nameservers=[DOH], ca_certificate="CC46-Cert", context="member-2"
        )
        blade = _array([_dns(name="management")], certificates=["cc46-cert"])

        _main(module, blade)

        module.fail_json.assert_not_called()
        assert blade.post_dns.call_args[1]["context_names"] == ["member-2"]
        assert blade.post_dns.call_args[1]["dns"]["ca_certificate"] == {
            "name": "CC46-Cert"
        }

    def test_unchanged_ca_reference_with_a_context_keeps_the_stored_spelling(self):
        """The current reference comes from the fleet member that holds it."""
        module = _module(
            domain="example.net",
            nameservers=[DOH],
            ca_certificate="CC46-CERT",
            context="member-2",
        )
        blade = _array(
            [_dns(nameservers=[DOH], ca_certificate="cc46-cert")],
            certificates=["CC46-Cert"],
        )

        _main(module, blade)

        module.fail_json.assert_not_called()
        assert blade.patch_dns.call_args[1]["context_names"] == ["member-2"]
        assert blade.patch_dns.call_args[1]["dns"]["ca_certificate"] == {
            "name": "cc46-cert"
        }

    def test_ca_reference_is_kept_when_the_read_returns_no_item(self):
        module = _module(nameservers=[DOH], ca_certificate="cc46-cert")
        blade = _array([_dns(name="management")])
        blade.get_certificates = Mock(return_value=_response())

        _main(module, blade)

        assert blade.post_dns.call_args[1]["dns"]["ca_certificate"] == {
            "name": "cc46-cert"
        }


class TestPurefbDnsRealm:
    """A configuration named realm::name, and its references"""

    def test_create_in_a_realm(self):
        module = _module(
            name=RDNS,
            nameservers=[DOH],
            source="REALM-1::cc46-vip",
            ca_certificate="Realm-1::cc46-cert",
        )
        blade = _array(
            [_dns(name="management"), _dns()],
            interfaces=[RVIP],
            certificates=[RCERT],
        )

        _main(module, blade)

        module.fail_json.assert_not_called()
        assert blade.post_dns.call_args[1]["names"] == [RDNS]
        assert blade.post_dns.call_args[1]["dns"] == {
            "services": ["data"],
            "domain": "example.com",
            "nameservers": [DOH],
            "sources": [{"name": RVIP}],
            "ca_certificate": {"name": RCERT},
        }
        assert module.exit_json.call_args[1]["changed"] is True

    def test_namesakes_in_other_scopes_are_left_alone(self):
        """The array-level namesake is neither read by name nor written."""
        module = _module(name=RDNS, domain="example.net")
        blade = _array(
            [
                _dns(name="cc46-dns"),
                _dns(name="realm-2::cc46-dns", source="realm-2::cc46-vip"),
                _dns(name=RDNS, source=RVIP),
            ]
        )

        _main(module, blade)

        assert blade.get_dns.call_args_list == [call(), call(names=[RDNS])]
        blade.patch_dns.assert_called_once()
        assert blade.patch_dns.call_args[1]["names"] == [RDNS]

    def test_update_without_source_option_sends_no_source(self):
        module = _module(name=RDNS, domain="example.net")
        blade = _array([_dns(name=RDNS, source=RVIP)])

        _main(module, blade)

        assert "sources" not in blade.patch_dns.call_args[1]["dns"]
        assert module.exit_json.call_args[1]["changed"] is True

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_realm_configuration_cannot_give_up_its_source(self, check_mode):
        module = _module(check_mode=check_mode, name=RDNS, source="")
        blade = _array([_dns(name=RDNS, source=RVIP)], interfaces=[RVIP])

        _main(module, blade)

        _no_write(blade)
        module.exit_json.assert_not_called()
        msg = module.fail_json.call_args[1]["msg"]
        assert RDNS in msg
        assert "cannot be left without a source" in msg

    def test_array_level_configuration_can_still_clear_its_source(self):
        module = _module(source="")
        blade = _array([_dns(source="cc46-vip")], interfaces=["cc46-vip"])

        _main(module, blade)

        module.fail_json.assert_not_called()
        assert blade.patch_dns.call_args[1]["dns"]["sources"] == [{"name": ""}]
        assert module.exit_json.call_args[1]["changed"] is True

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("source", [None, ""])
    def test_create_in_a_realm_needs_a_source(self, source, check_mode):
        module = _module(
            check_mode=check_mode, name=RDNS, nameservers=[IP], source=source
        )
        blade = _array([_dns(name="management"), _dns()])

        _main(module, blade)

        _no_write(blade)
        module.exit_json.assert_not_called()
        msg = module.fail_json.call_args[1]["msg"]
        assert "needs a source" in msg
        assert "realm-1::<interface>" in msg

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_create_in_a_realm_refuses_the_management_service(self, check_mode):
        module = _module(
            check_mode=check_mode,
            name=RDNS,
            nameservers=[IP],
            source=RVIP,
            service="management",
        )
        blade = _array([_dns(name="management")], interfaces=[RVIP])

        _main(module, blade)

        _no_write(blade)
        module.exit_json.assert_not_called()
        assert "only the data service" in module.fail_json.call_args[1]["msg"]

    def test_array_level_create_needs_no_source(self):
        module = _module(nameservers=[IP])
        blade = _array([_dns(name="management")])

        _main(module, blade)

        module.fail_json.assert_not_called()
        assert "sources" not in blade.post_dns.call_args[1]["dns"]

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("exists", [False, True])
    @pytest.mark.parametrize("source", ["cc46-vip", "realm-2::cc46-vip"])
    def test_realm_configuration_refuses_a_source_outside_its_realm(
        self, source, exists, check_mode
    ):
        module = _module(
            check_mode=check_mode, name=RDNS, nameservers=[IP], source=source
        )
        configs = [_dns(name="management")]
        if exists:
            configs.append(_dns(name=RDNS, source=RVIP))
        blade = _array(configs, interfaces=["cc46-vip", "realm-2::cc46-vip", RVIP])

        _main(module, blade)

        blade.get_dns.assert_not_called()
        blade.get_network_interfaces.assert_not_called()
        _no_write(blade)
        module.exit_json.assert_not_called()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Source {0} is not in realm realm-1".format(source) in msg
        assert "realm-1::<interface>" in msg

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_array_level_configuration_refuses_a_source_in_a_realm(self, check_mode):
        module = _module(check_mode=check_mode, source=RVIP)
        blade = _array([_dns()], interfaces=[RVIP])

        _main(module, blade)

        blade.get_network_interfaces.assert_not_called()
        _no_write(blade)
        module.exit_json.assert_not_called()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Source {0} is in a realm".format(RVIP) in msg
        assert "cc46-dns is not in a realm" in msg

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize(
        "param, value",
        [
            ("ca_certificate", "global"),
            ("ca_certificate", "realm-2::cc46-cert"),
            ("ca_certificate_group", "cc46-grp"),
        ],
    )
    def test_realm_configuration_refuses_a_certificate_outside_its_realm(
        self, param, value, check_mode
    ):
        module = _module(
            check_mode=check_mode,
            name=RDNS,
            nameservers=[DOH],
            source=RVIP,
            **{param: value}
        )
        blade = _array(
            [_dns(name="management")],
            interfaces=[RVIP],
            certificates=["global", "realm-2::cc46-cert"],
            groups=["cc46-grp"],
        )

        _main(module, blade)

        blade.get_certificates.assert_not_called()
        blade.get_certificate_groups.assert_not_called()
        _no_write(blade)
        module.exit_json.assert_not_called()
        msg = module.fail_json.call_args[1]["msg"]
        assert "{0} {1} is not in realm realm-1".format(param, value) in msg
        assert "realm-1::<name>" in msg

    def test_array_level_configuration_with_a_realm_certificate_is_left_to_the_array(
        self,
    ):
        module = _module(nameservers=[DOH], ca_certificate=RCERT)
        blade = _array([_dns(name="management")], certificates=[RCERT])

        _main(module, blade)

        module.fail_json.assert_not_called()
        blade.get_certificates.assert_called_once_with(names=[RCERT])
        assert blade.post_dns.call_args[1]["dns"]["ca_certificate"] == {"name": RCERT}

    def test_absent_is_not_held_to_the_realm_rules(self):
        module = _module(state="absent", name=RDNS, source="cc46-vip")
        blade = _array([_dns(name=RDNS, source=RVIP)], interfaces=["cc46-vip"])

        _main(module, blade)

        module.fail_json.assert_not_called()
        blade.delete_dns.assert_called_once_with(names=[RDNS])

    def test_realm_rules_are_not_applied_below_the_multiple_dns_version(self):
        """REST below 2.15 has one configuration and ignores name and source."""
        module = _module(name="management", nameservers=[IP], source=RVIP)
        blade = Mock()
        blade.get_dns.return_value = _response(
            items=[{"domain": "example.com", "nameservers": [IP]}]
        )

        _main(module, blade, api_version="2.14")

        module.fail_json.assert_not_called()
        blade.get_network_interfaces.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False


class TestPurefbDnsRefusedReads:
    """Only "does not exist" means absent; any other answer is reported"""

    @pytest.mark.parametrize("name, source", [("cc46-dns", "cc46-vip"), (RDNS, RVIP)])
    def test_source_that_does_not_exist(self, name, source):
        module = _module(name=name, nameservers=[IP], source=source)
        blade = _array([_dns(name="management")])

        _main(module, blade)

        blade.get_network_interfaces.assert_called_once_with(names=[source])
        _no_write(blade)
        msg = module.fail_json.call_args[1]["msg"]
        assert (
            "Specified VIP {0} does not exist or is not visible to this "
            "identity.".format(source) in msg
        )
        assert "realm::name" in msg

    def test_refused_source_read_reports_the_array_message(self):
        module = _module(nameservers=[IP], source="cc46-vip")
        blade = _array([_dns(name="management")])
        blade.get_network_interfaces = Mock(
            return_value=_refused("Operation not permitted.", status_code=403)
        )

        _main(module, blade)

        _no_write(blade)
        assert module.fail_json.call_args[1]["msg"] == (
            "Failed to read network interface cc46-vip. "
            "Error: Operation not permitted."
        )

    @pytest.mark.parametrize(
        "param, label, name",
        [
            ("ca_certificate", "Certificate", "global"),
            ("ca_certificate_group", "Certificate group", "cc46-grp"),
        ],
    )
    def test_certificate_that_does_not_exist(self, param, label, name):
        """Also what an identity limited to a realm gets for an array-level one."""
        module = _module(nameservers=[DOH], **{param: name})
        blade = _array([_dns()])

        _main(module, blade)

        _no_write(blade)
        msg = module.fail_json.call_args[1]["msg"]
        assert (
            "{0} {1} does not exist or is not visible to this "
            "identity.".format(label, name) in msg
        )
        assert "realm::name" in msg

    @pytest.mark.parametrize(
        "param, kind",
        [
            ("ca_certificate", "certificate"),
            ("ca_certificate_group", "certificate group"),
        ],
    )
    def test_refused_certificate_read_reports_the_array_message(self, param, kind):
        module = _module(nameservers=[DOH], **{param: "cc46-ca"})
        blade = _array([_dns()])
        refused = Mock(
            return_value=_refused("Operation not permitted.", status_code=403)
        )
        blade.get_certificates = refused
        blade.get_certificate_groups = refused

        _main(module, blade)

        _no_write(blade)
        assert module.fail_json.call_args[1]["msg"] == (
            "Failed to read {0} cc46-ca. Error: Operation not permitted.".format(kind)
        )

    def test_refused_configuration_read_reports_the_array_message(self):
        module = _module(domain="example.net")
        blade = _array([_dns()])
        blade.get_dns = Mock(
            side_effect=[
                _response(items=[_dns()]),
                _refused("Operation not permitted.", status_code=403),
            ]
        )

        _main(module, blade)

        _no_write(blade)
        assert module.fail_json.call_args[1]["msg"] == (
            "Failed to read DNS configuration cc46-dns. "
            "Error: Operation not permitted."
        )
