# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_dns module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from unittest.mock import Mock, patch, MagicMock

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
    _https_host,
    _is_https,
    _is_ip_address,
    _reference_name,
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
    return res


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
            patch(MODULE + ".get_error_message", Mock(return_value="boom")),
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
        blade.get_certificates.return_value = _response(status_code=400)
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
        blade.get_certificate_groups.return_value = _response(status_code=400)
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
