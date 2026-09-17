# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_tls_policy module."""

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

from plugins.modules.purefb_tls_policy import (
    main,
    _get_policy,
    _get_attached_interfaces,
    _reconcile_interfaces,
    _validate_attachable,
    _check_mutual_tls_support,
)


class TestPurefbTlsPolicy:
    """Test cases for purefb_tls_policy module"""

    # ---------------- helper-function unit tests ----------------

    def test_get_policy_returns_first_item(self):
        """Test _get_policy returns the first policy when present"""
        mock_module = Mock()
        mock_module.params = {"name": "tls1"}

        existing = Mock()
        existing.name = "tls1"

        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.items = [existing]
        mock_blade.get_tls_policies.return_value = mock_response

        out = _get_policy(mock_module, mock_blade)

        assert out is existing
        mock_blade.get_tls_policies.assert_called_once_with(names=["tls1"])

    def test_get_policy_returns_none_when_empty(self):
        """Test _get_policy returns None when items is empty"""
        mock_module = Mock()
        mock_module.params = {"name": "tls1"}

        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.items = []
        mock_blade.get_tls_policies.return_value = mock_response

        assert _get_policy(mock_module, mock_blade) is None

    def test_get_policy_returns_none_on_error(self):
        """Test _get_policy returns None when status is non-200"""
        mock_module = Mock()
        mock_module.params = {"name": "tls1"}

        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.items = []
        mock_blade.get_tls_policies.return_value = mock_response

        assert _get_policy(mock_module, mock_blade) is None

    def test_get_attached_interfaces_returns_sorted_names(self):
        """Test _get_attached_interfaces returns member names sorted"""
        mock_module = Mock()
        mock_module.params = {"name": "tls1"}

        m1 = Mock()
        m1.member = Mock()
        m1.member.name = "data2.eth0"
        m2 = Mock()
        m2.member = Mock()
        m2.member.name = "data1.eth0"

        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.items = [m1, m2]
        mock_blade.get_tls_policies_network_interfaces.return_value = mock_response

        out = _get_attached_interfaces(mock_module, mock_blade)
        assert out == ["data1.eth0", "data2.eth0"]
        mock_blade.get_tls_policies_network_interfaces.assert_called_once_with(
            policy_names=["tls1"]
        )

    def test_get_attached_interfaces_returns_empty_on_error(self):
        """Test _get_attached_interfaces returns [] when status is non-200"""
        mock_module = Mock()
        mock_module.params = {"name": "tls1"}

        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.items = []
        mock_blade.get_tls_policies_network_interfaces.return_value = mock_response

        assert _get_attached_interfaces(mock_module, mock_blade) == []

    # ---------------- _reconcile_interfaces tests ----------------

    def test_reconcile_attaches_missing(self):
        """Test _reconcile_interfaces POSTs interfaces not yet attached"""
        mock_module = Mock()
        mock_module.params = {
            "name": "tls1",
            "network_interfaces": ["data1.eth0", "data2.eth0"],
        }
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        # serves both _get_attached_interfaces and _validate_attachable
        mock_blade.get_tls_policies_network_interfaces.return_value = get_response

        iface1 = Mock()
        iface1.name = "data1.eth0"
        iface2 = Mock()
        iface2.name = "data2.eth0"
        ni_response = Mock()
        ni_response.status_code = 200
        ni_response.items = [iface1, iface2]
        mock_blade.get_network_interfaces.return_value = ni_response

        post_response = Mock()
        post_response.status_code = 200
        mock_blade.post_tls_policies_network_interfaces.return_value = post_response

        changed = _reconcile_interfaces(mock_module, mock_blade)

        assert changed is True
        assert mock_blade.post_tls_policies_network_interfaces.call_args_list == [
            call(policy_names=["tls1"], member_names=["data1.eth0"]),
            call(policy_names=["tls1"], member_names=["data2.eth0"]),
        ]
        mock_blade.delete_tls_policies_network_interfaces.assert_not_called()

    def test_reconcile_detaches_extras(self):
        """Test _reconcile_interfaces DELETEs interfaces not in desired list"""
        mock_module = Mock()
        mock_module.params = {
            "name": "tls1",
            "network_interfaces": ["data1.eth0"],
        }
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        keep = Mock()
        keep.member = Mock()
        keep.member.name = "data1.eth0"
        drop = Mock()
        drop.member = Mock()
        drop.member.name = "data2.eth0"

        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [keep, drop]
        mock_blade.get_tls_policies_network_interfaces.return_value = get_response

        delete_response = Mock()
        delete_response.status_code = 200
        mock_blade.delete_tls_policies_network_interfaces.return_value = delete_response

        changed = _reconcile_interfaces(mock_module, mock_blade)

        assert changed is True
        mock_blade.delete_tls_policies_network_interfaces.assert_called_once_with(
            policy_names=["tls1"], member_names=["data2.eth0"]
        )
        mock_blade.post_tls_policies_network_interfaces.assert_not_called()

    def test_reconcile_idempotent_when_match(self):
        """Test _reconcile_interfaces is a no-op when current == desired"""
        mock_module = Mock()
        mock_module.params = {
            "name": "tls1",
            "network_interfaces": ["data1.eth0"],
        }
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        match = Mock()
        match.member = Mock()
        match.member.name = "data1.eth0"

        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [match]
        mock_blade.get_tls_policies_network_interfaces.return_value = get_response

        changed = _reconcile_interfaces(mock_module, mock_blade)

        assert changed is False
        mock_blade.post_tls_policies_network_interfaces.assert_not_called()
        mock_blade.delete_tls_policies_network_interfaces.assert_not_called()

    def test_reconcile_empty_desired_detaches_all(self):
        """Test _reconcile_interfaces with [] desired detaches everything"""
        mock_module = Mock()
        mock_module.params = {
            "name": "tls1",
            "network_interfaces": [],
        }
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        drop1 = Mock()
        drop1.member = Mock()
        drop1.member.name = "data1.eth0"
        drop2 = Mock()
        drop2.member = Mock()
        drop2.member.name = "data2.eth0"

        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [drop1, drop2]
        mock_blade.get_tls_policies_network_interfaces.return_value = get_response

        delete_response = Mock()
        delete_response.status_code = 200
        mock_blade.delete_tls_policies_network_interfaces.return_value = delete_response

        changed = _reconcile_interfaces(mock_module, mock_blade)

        assert changed is True
        assert mock_blade.delete_tls_policies_network_interfaces.call_args_list == [
            call(policy_names=["tls1"], member_names=["data1.eth0"]),
            call(policy_names=["tls1"], member_names=["data2.eth0"]),
        ]

    def test_reconcile_check_mode_skips_writes(self):
        """Test _reconcile_interfaces reports changed but skips writes in check mode"""
        mock_module = Mock()
        mock_module.params = {
            "name": "tls1",
            "network_interfaces": ["data1.eth0"],
        }
        mock_module.check_mode = True
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_tls_policies_network_interfaces.return_value = get_response

        iface = Mock()
        iface.name = "data1.eth0"
        ni_response = Mock()
        ni_response.status_code = 200
        ni_response.items = [iface]
        mock_blade.get_network_interfaces.return_value = ni_response

        changed = _reconcile_interfaces(mock_module, mock_blade)

        assert changed is True
        mock_blade.post_tls_policies_network_interfaces.assert_not_called()
        mock_blade.delete_tls_policies_network_interfaces.assert_not_called()

    # ---------------- _check_mutual_tls_support tests ----------------

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    def test_mutual_tls_support_ok_on_218(self, mock_loose_version):
        """Test mutual-TLS gate passes when api version meets MIN_MUTUAL_TLS_API_VERSION"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.params = {
            "client_certificates_required": True,
            "trusted_client_certificate_authority": "ca1",
            "verify_client_certificate_trust": True,
        }
        mock_module.fail_json = Mock(side_effect=SystemExit)
        _check_mutual_tls_support(mock_module, ["2.17", "2.18"])
        mock_module.fail_json.assert_not_called()

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    def test_mutual_tls_support_no_params_skipped(self, mock_loose_version):
        """Test mutual-TLS gate is a no-op when none of the gated params are set"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)
        mock_module = Mock()
        mock_module.params = {
            "client_certificates_required": None,
            "trusted_client_certificate_authority": None,
            "verify_client_certificate_trust": None,
        }
        mock_module.fail_json = Mock(side_effect=SystemExit)
        _check_mutual_tls_support(mock_module, ["2.17"])
        mock_module.fail_json.assert_not_called()

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    def test_mutual_tls_support_fails_when_param_set_on_217(self, mock_loose_version):
        """Test mutual-TLS gate fails clearly when a gated param is set on a 2.17-only array"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)
        mock_module = Mock()
        mock_module.params = {
            "client_certificates_required": True,
            "trusted_client_certificate_authority": None,
            "verify_client_certificate_trust": None,
        }
        mock_module.fail_json = Mock(side_effect=SystemExit)
        try:
            _check_mutual_tls_support(mock_module, ["2.17"])
        except SystemExit:
            pass
        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "client_certificates_required" in msg
        assert "2.18" in msg

    # ---------------- _validate_attachable tests ----------------

    def test_validate_attachable_passes_when_clean(self):
        """Test _validate_attachable returns silently when interfaces exist and have no conflict"""
        mock_module = Mock()
        mock_module.params = {"name": "tls1"}
        mock_module.fail_json = Mock(side_effect=SystemExit)

        iface = Mock()
        iface.name = "data1.eth0"
        ni_response = Mock()
        ni_response.status_code = 200
        ni_response.items = [iface]

        ti_response = Mock()
        ti_response.status_code = 200
        ti_response.items = []

        mock_blade = Mock()
        mock_blade.get_network_interfaces.return_value = ni_response
        mock_blade.get_tls_policies_network_interfaces.return_value = ti_response

        _validate_attachable(mock_module, mock_blade, ["data1.eth0"])
        mock_module.fail_json.assert_not_called()

    def test_validate_attachable_empty_is_noop(self):
        """Test _validate_attachable returns silently when interface list is empty"""
        mock_module = Mock()
        mock_module.params = {"name": "tls1"}
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_blade = Mock()

        _validate_attachable(mock_module, mock_blade, [])
        mock_module.fail_json.assert_not_called()
        mock_blade.get_network_interfaces.assert_not_called()

    def test_validate_attachable_fails_on_missing_interface(self):
        """Test _validate_attachable fails when a requested interface does not exist"""
        mock_module = Mock()
        mock_module.params = {"name": "tls1"}
        mock_module.fail_json = Mock(side_effect=SystemExit)

        iface = Mock()
        iface.name = "data1.eth0"
        ni_response = Mock()
        ni_response.status_code = 200
        ni_response.items = [iface]

        mock_blade = Mock()
        mock_blade.get_network_interfaces.return_value = ni_response

        try:
            _validate_attachable(mock_module, mock_blade, ["data1.eth0", "ghost.eth0"])
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "ghost.eth0" in msg

    def test_validate_attachable_fails_when_get_network_interfaces_errors(self):
        """Test _validate_attachable fails when the lookup itself errors"""
        mock_module = Mock()
        mock_module.params = {"name": "tls1"}
        mock_module.fail_json = Mock(side_effect=SystemExit)

        ni_response = Mock()
        ni_response.status_code = 400
        ni_response.items = []
        ni_response.errors = []

        mock_blade = Mock()
        mock_blade.get_network_interfaces.return_value = ni_response

        try:
            _validate_attachable(mock_module, mock_blade, ["data1.eth0"])
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert "not found" in mock_module.fail_json.call_args[1]["msg"]

    def test_validate_attachable_fails_on_conflict(self):
        """Test _validate_attachable fails when an interface is bound to a different policy"""
        mock_module = Mock()
        mock_module.params = {"name": "tls1"}
        mock_module.fail_json = Mock(side_effect=SystemExit)

        iface = Mock()
        iface.name = "data1.eth0"
        ni_response = Mock()
        ni_response.status_code = 200
        ni_response.items = [iface]

        member = Mock()
        member.member = Mock()
        member.member.name = "data1.eth0"
        member.policy = Mock()
        member.policy.name = "other-tls"

        ti_response = Mock()
        ti_response.status_code = 200
        ti_response.items = [member]

        mock_blade = Mock()
        mock_blade.get_network_interfaces.return_value = ni_response
        mock_blade.get_tls_policies_network_interfaces.return_value = ti_response

        try:
            _validate_attachable(mock_module, mock_blade, ["data1.eth0"])
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "data1.eth0=>other-tls" in msg
        assert "Detach" in msg

    def test_validate_attachable_self_attachment_is_not_conflict(self):
        """Test _validate_attachable treats existing self-attachment as non-conflicting"""
        mock_module = Mock()
        mock_module.params = {"name": "tls1"}
        mock_module.fail_json = Mock(side_effect=SystemExit)

        iface = Mock()
        iface.name = "data1.eth0"
        ni_response = Mock()
        ni_response.status_code = 200
        ni_response.items = [iface]

        member = Mock()
        member.member = Mock()
        member.member.name = "data1.eth0"
        member.policy = Mock()
        member.policy.name = "tls1"  # same as ours

        ti_response = Mock()
        ti_response.status_code = 200
        ti_response.items = [member]

        mock_blade = Mock()
        mock_blade.get_network_interfaces.return_value = ni_response
        mock_blade.get_tls_policies_network_interfaces.return_value = ti_response

        _validate_attachable(mock_module, mock_blade, ["data1.eth0"])
        mock_module.fail_json.assert_not_called()

    # ---------------- main() flows ----------------

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    @patch("plugins.modules.purefb_tls_policy.TlsPolicyPost")
    @patch("plugins.modules.purefb_tls_policy.get_system")
    @patch("plugins.modules.purefb_tls_policy.AnsibleModule")
    @patch("plugins.modules.purefb_tls_policy.HAS_PYPURECLIENT", True)
    def test_main_creates_policy(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_policy_post,
        mock_loose_version,
    ):
        """Test creating a new TLS policy"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "tls1",
            "state": "present",
            "enabled": None,
            "appliance_certificate": "my_cert",
            "client_certificates_required": None,
            "trusted_client_certificate_authority": None,
            "verify_client_certificate_trust": None,
            "min_tls_version": "1.2",
            "enabled_tls_ciphers": None,
            "disabled_tls_ciphers": None,
            "network_interfaces": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.17"]
        mock_get_system.return_value = mock_blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_tls_policies.return_value = get_response

        post_response = Mock()
        post_response.status_code = 200
        mock_blade.post_tls_policies.return_value = post_response

        try:
            main()
        except SystemExit:
            pass

        mock_blade.post_tls_policies.assert_called_once()
        call_kwargs = mock_blade.post_tls_policies.call_args[1]
        assert call_kwargs["names"] == ["tls1"]
        mock_module.exit_json.assert_called_once()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    @patch("plugins.modules.purefb_tls_policy.TlsPolicyPost")
    @patch("plugins.modules.purefb_tls_policy.get_system")
    @patch("plugins.modules.purefb_tls_policy.AnsibleModule")
    @patch("plugins.modules.purefb_tls_policy.HAS_PYPURECLIENT", True)
    def test_main_create_with_attachments(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_policy_post,
        mock_loose_version,
    ):
        """Test create + initial attachments POSTs to both endpoints"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "tls1",
            "state": "present",
            "enabled": None,
            "appliance_certificate": None,
            "client_certificates_required": None,
            "trusted_client_certificate_authority": None,
            "verify_client_certificate_trust": None,
            "min_tls_version": None,
            "enabled_tls_ciphers": None,
            "disabled_tls_ciphers": None,
            "network_interfaces": ["data1.eth0", "data2.eth0"],
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.17"]
        mock_get_system.return_value = mock_blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_tls_policies.return_value = get_response

        iface1 = Mock()
        iface1.name = "data1.eth0"
        iface2 = Mock()
        iface2.name = "data2.eth0"
        ni_response = Mock()
        ni_response.status_code = 200
        ni_response.items = [iface1, iface2]
        mock_blade.get_network_interfaces.return_value = ni_response

        conflict_response = Mock()
        conflict_response.status_code = 200
        conflict_response.items = []
        mock_blade.get_tls_policies_network_interfaces.return_value = conflict_response

        ok = Mock()
        ok.status_code = 200
        mock_blade.post_tls_policies.return_value = ok
        mock_blade.post_tls_policies_network_interfaces.return_value = ok

        try:
            main()
        except SystemExit:
            pass

        mock_blade.post_tls_policies.assert_called_once()
        assert mock_blade.post_tls_policies_network_interfaces.call_args_list == [
            call(policy_names=["tls1"], member_names=["data1.eth0"]),
            call(policy_names=["tls1"], member_names=["data2.eth0"]),
        ]
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    @patch("plugins.modules.purefb_tls_policy.get_system")
    @patch("plugins.modules.purefb_tls_policy.AnsibleModule")
    @patch("plugins.modules.purefb_tls_policy.HAS_PYPURECLIENT", True)
    def test_main_create_check_mode_skips_post(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test create reports changed but skips POST in check mode"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "tls1",
            "state": "present",
            "enabled": None,
            "appliance_certificate": None,
            "client_certificates_required": None,
            "trusted_client_certificate_authority": None,
            "verify_client_certificate_trust": None,
            "min_tls_version": None,
            "enabled_tls_ciphers": None,
            "disabled_tls_ciphers": None,
            "network_interfaces": None,
        }
        mock_module.check_mode = True
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.17"]
        mock_get_system.return_value = mock_blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_tls_policies.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        mock_blade.post_tls_policies.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    @patch("plugins.modules.purefb_tls_policy.TlsPolicy")
    @patch("plugins.modules.purefb_tls_policy.get_system")
    @patch("plugins.modules.purefb_tls_policy.AnsibleModule")
    @patch("plugins.modules.purefb_tls_policy.HAS_PYPURECLIENT", True)
    def test_main_updates_enabled_flag(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_tls_policy,
        mock_loose_version,
    ):
        """Test updating the enabled flag on an existing policy"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "tls1",
            "state": "present",
            "enabled": False,
            "appliance_certificate": None,
            "client_certificates_required": None,
            "trusted_client_certificate_authority": None,
            "verify_client_certificate_trust": None,
            "min_tls_version": None,
            "enabled_tls_ciphers": None,
            "disabled_tls_ciphers": None,
            "network_interfaces": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.17"]
        mock_get_system.return_value = mock_blade

        existing = Mock()
        existing.name = "tls1"
        existing.enabled = True
        existing.min_tls_version = None
        existing.enabled_tls_ciphers = None
        existing.disabled_tls_ciphers = None
        existing.appliance_certificate = None
        existing.trusted_client_certificate_authority = None
        existing.client_certificates_required = None
        existing.verify_client_certificate_trust = None

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        mock_blade.get_tls_policies.return_value = get_response

        patch_response = Mock()
        patch_response.status_code = 200
        mock_blade.patch_tls_policies.return_value = patch_response

        try:
            main()
        except SystemExit:
            pass

        mock_blade.patch_tls_policies.assert_called_once()
        call_kwargs = mock_blade.patch_tls_policies.call_args[1]
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    @patch("plugins.modules.purefb_tls_policy.get_system")
    @patch("plugins.modules.purefb_tls_policy.AnsibleModule")
    @patch("plugins.modules.purefb_tls_policy.HAS_PYPURECLIENT", True)
    def test_main_update_idempotent(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test update is a no-op when desired matches current state"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "tls1",
            "state": "present",
            "enabled": True,
            "appliance_certificate": None,
            "client_certificates_required": None,
            "trusted_client_certificate_authority": None,
            "verify_client_certificate_trust": None,
            "min_tls_version": "1.2",
            "enabled_tls_ciphers": None,
            "disabled_tls_ciphers": None,
            "network_interfaces": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.17"]
        mock_get_system.return_value = mock_blade

        existing = Mock()
        existing.name = "tls1"
        existing.enabled = True
        existing.min_tls_version = "1.2"
        existing.enabled_tls_ciphers = None
        existing.disabled_tls_ciphers = None
        existing.appliance_certificate = None
        existing.trusted_client_certificate_authority = None
        existing.client_certificates_required = None
        existing.verify_client_certificate_trust = None

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        mock_blade.get_tls_policies.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        mock_blade.patch_tls_policies.assert_not_called()
        mock_blade.post_tls_policies.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    @patch("plugins.modules.purefb_tls_policy.TlsPolicy")
    @patch("plugins.modules.purefb_tls_policy.ReferenceWritable")
    @patch("plugins.modules.purefb_tls_policy.get_system")
    @patch("plugins.modules.purefb_tls_policy.AnsibleModule")
    @patch("plugins.modules.purefb_tls_policy.HAS_PYPURECLIENT", True)
    def test_main_updates_appliance_certificate(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_reference_writable,
        mock_tls_policy,
        mock_loose_version,
    ):
        """Test updating the appliance certificate triggers a patch"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "tls1",
            "state": "present",
            "enabled": None,
            "appliance_certificate": "new_cert",
            "client_certificates_required": None,
            "trusted_client_certificate_authority": None,
            "verify_client_certificate_trust": None,
            "min_tls_version": None,
            "enabled_tls_ciphers": None,
            "disabled_tls_ciphers": None,
            "network_interfaces": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.17"]
        mock_get_system.return_value = mock_blade

        existing_cert = Mock()
        existing_cert.name = "old_cert"
        existing = Mock()
        existing.name = "tls1"
        existing.enabled = True
        existing.min_tls_version = None
        existing.enabled_tls_ciphers = None
        existing.disabled_tls_ciphers = None
        existing.appliance_certificate = existing_cert
        existing.trusted_client_certificate_authority = None
        existing.client_certificates_required = None
        existing.verify_client_certificate_trust = None

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        mock_blade.get_tls_policies.return_value = get_response

        patch_response = Mock()
        patch_response.status_code = 200
        mock_blade.patch_tls_policies.return_value = patch_response

        try:
            main()
        except SystemExit:
            pass

        mock_reference_writable.assert_called_with(name="new_cert")
        mock_blade.patch_tls_policies.assert_called_once()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    @patch("plugins.modules.purefb_tls_policy.TlsPolicy")
    @patch("plugins.modules.purefb_tls_policy.ReferenceWritable")
    @patch("plugins.modules.purefb_tls_policy.get_system")
    @patch("plugins.modules.purefb_tls_policy.AnsibleModule")
    @patch("plugins.modules.purefb_tls_policy.HAS_PYPURECLIENT", True)
    def test_main_resets_appliance_certificate_to_global(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_reference_writable,
        mock_tls_policy,
        mock_loose_version,
    ):
        """Test setting appliance_certificate='global' patches with ReferenceWritable(name='global')"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "tls1",
            "state": "present",
            "enabled": None,
            "appliance_certificate": "global",
            "client_certificates_required": None,
            "trusted_client_certificate_authority": None,
            "verify_client_certificate_trust": None,
            "min_tls_version": None,
            "enabled_tls_ciphers": None,
            "disabled_tls_ciphers": None,
            "network_interfaces": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.17"]
        mock_get_system.return_value = mock_blade

        existing_cert = Mock()
        existing_cert.name = "custom_cert"
        existing = Mock()
        existing.name = "tls1"
        existing.enabled = True
        existing.min_tls_version = None
        existing.enabled_tls_ciphers = None
        existing.disabled_tls_ciphers = None
        existing.appliance_certificate = existing_cert
        existing.trusted_client_certificate_authority = None
        existing.client_certificates_required = None
        existing.verify_client_certificate_trust = None

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        mock_blade.get_tls_policies.return_value = get_response

        patch_response = Mock()
        patch_response.status_code = 200
        mock_blade.patch_tls_policies.return_value = patch_response

        try:
            main()
        except SystemExit:
            pass

        mock_reference_writable.assert_called_with(name="global")
        mock_blade.patch_tls_policies.assert_called_once()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    @patch("plugins.modules.purefb_tls_policy.TlsPolicy")
    @patch("plugins.modules.purefb_tls_policy.ReferenceWritable")
    @patch("plugins.modules.purefb_tls_policy.get_system")
    @patch("plugins.modules.purefb_tls_policy.AnsibleModule")
    @patch("plugins.modules.purefb_tls_policy.HAS_PYPURECLIENT", True)
    def test_main_clears_trusted_client_certificate_authority(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_reference_writable,
        mock_tls_policy,
        mock_loose_version,
    ):
        """Test setting trusted_client_certificate_authority='' patches with ReferenceWritable(name='')"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "tls1",
            "state": "present",
            "enabled": None,
            "appliance_certificate": None,
            "client_certificates_required": None,
            "trusted_client_certificate_authority": "",
            "verify_client_certificate_trust": None,
            "min_tls_version": None,
            "enabled_tls_ciphers": None,
            "disabled_tls_ciphers": None,
            "network_interfaces": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.18"]
        mock_get_system.return_value = mock_blade

        existing_ca = Mock()
        existing_ca.name = "corp_ca"
        existing = Mock()
        existing.name = "tls1"
        existing.enabled = True
        existing.min_tls_version = None
        existing.enabled_tls_ciphers = None
        existing.disabled_tls_ciphers = None
        existing.appliance_certificate = None
        existing.trusted_client_certificate_authority = existing_ca
        existing.client_certificates_required = None
        existing.verify_client_certificate_trust = None

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        mock_blade.get_tls_policies.return_value = get_response

        patch_response = Mock()
        patch_response.status_code = 200
        mock_blade.patch_tls_policies.return_value = patch_response

        try:
            main()
        except SystemExit:
            pass

        mock_reference_writable.assert_called_with(name="")
        mock_blade.patch_tls_policies.assert_called_once()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    @patch("plugins.modules.purefb_tls_policy.get_system")
    @patch("plugins.modules.purefb_tls_policy.AnsibleModule")
    @patch("plugins.modules.purefb_tls_policy.HAS_PYPURECLIENT", True)
    def test_main_clear_trusted_ca_idempotent_when_already_unset(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test clearing CA with '' is a no-op when the policy has no CA set"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "tls1",
            "state": "present",
            "enabled": None,
            "appliance_certificate": None,
            "client_certificates_required": None,
            "trusted_client_certificate_authority": "",
            "verify_client_certificate_trust": None,
            "min_tls_version": None,
            "enabled_tls_ciphers": None,
            "disabled_tls_ciphers": None,
            "network_interfaces": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.18"]
        mock_get_system.return_value = mock_blade

        existing = Mock()
        existing.name = "tls1"
        existing.enabled = True
        existing.min_tls_version = None
        existing.enabled_tls_ciphers = None
        existing.disabled_tls_ciphers = None
        existing.appliance_certificate = None
        existing.trusted_client_certificate_authority = None
        existing.client_certificates_required = None
        existing.verify_client_certificate_trust = None

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        mock_blade.get_tls_policies.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        mock_blade.patch_tls_policies.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    @patch("plugins.modules.purefb_tls_policy.get_system")
    @patch("plugins.modules.purefb_tls_policy.AnsibleModule")
    @patch("plugins.modules.purefb_tls_policy.HAS_PYPURECLIENT", True)
    def test_main_deletes_policy_with_attachments(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test delete detaches network interfaces before removing the policy"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "tls1",
            "state": "absent",
            "enabled": None,
            "appliance_certificate": None,
            "client_certificates_required": None,
            "trusted_client_certificate_authority": None,
            "verify_client_certificate_trust": None,
            "min_tls_version": None,
            "enabled_tls_ciphers": None,
            "disabled_tls_ciphers": None,
            "network_interfaces": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.17"]
        mock_get_system.return_value = mock_blade

        existing = Mock()
        existing.name = "tls1"

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        mock_blade.get_tls_policies.return_value = get_response

        # Currently attached to one interface
        m1 = Mock()
        m1.member = Mock()
        m1.member.name = "data1.eth0"
        attached_response = Mock()
        attached_response.status_code = 200
        attached_response.items = [m1]
        mock_blade.get_tls_policies_network_interfaces.return_value = attached_response

        ok = Mock()
        ok.status_code = 200
        mock_blade.delete_tls_policies_network_interfaces.return_value = ok
        mock_blade.delete_tls_policies.return_value = ok

        try:
            main()
        except SystemExit:
            pass

        mock_blade.delete_tls_policies_network_interfaces.assert_called_once_with(
            policy_names=["tls1"],
            member_names=["data1.eth0"],
        )
        mock_blade.delete_tls_policies.assert_called_once_with(names=["tls1"])
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    @patch("plugins.modules.purefb_tls_policy.get_system")
    @patch("plugins.modules.purefb_tls_policy.AnsibleModule")
    @patch("plugins.modules.purefb_tls_policy.HAS_PYPURECLIENT", True)
    def test_main_delete_nonexistent_is_noop(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test delete on a non-existent policy is a no-op"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "tls1",
            "state": "absent",
            "enabled": None,
            "appliance_certificate": None,
            "client_certificates_required": None,
            "trusted_client_certificate_authority": None,
            "verify_client_certificate_trust": None,
            "min_tls_version": None,
            "enabled_tls_ciphers": None,
            "disabled_tls_ciphers": None,
            "network_interfaces": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.17"]
        mock_get_system.return_value = mock_blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_tls_policies.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        mock_blade.delete_tls_policies.assert_not_called()
        mock_blade.delete_tls_policies_network_interfaces.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    @patch("plugins.modules.purefb_tls_policy.get_system")
    @patch("plugins.modules.purefb_tls_policy.AnsibleModule")
    @patch("plugins.modules.purefb_tls_policy.HAS_PYPURECLIENT", True)
    def test_main_reconcile_attaches_on_update(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test update reconciles network interface attachments"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "tls1",
            "state": "present",
            "enabled": None,
            "appliance_certificate": None,
            "client_certificates_required": None,
            "trusted_client_certificate_authority": None,
            "verify_client_certificate_trust": None,
            "min_tls_version": None,
            "enabled_tls_ciphers": None,
            "disabled_tls_ciphers": None,
            "network_interfaces": ["data1.eth0"],
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.17"]
        mock_get_system.return_value = mock_blade

        existing = Mock()
        existing.name = "tls1"
        existing.enabled = True
        existing.min_tls_version = None
        existing.enabled_tls_ciphers = None
        existing.disabled_tls_ciphers = None
        existing.appliance_certificate = None
        existing.trusted_client_certificate_authority = None
        existing.client_certificates_required = None
        existing.verify_client_certificate_trust = None

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        mock_blade.get_tls_policies.return_value = get_response

        # Currently nothing attached (also serves _validate_attachable)
        ifaces_response = Mock()
        ifaces_response.status_code = 200
        ifaces_response.items = []
        mock_blade.get_tls_policies_network_interfaces.return_value = ifaces_response

        iface = Mock()
        iface.name = "data1.eth0"
        ni_response = Mock()
        ni_response.status_code = 200
        ni_response.items = [iface]
        mock_blade.get_network_interfaces.return_value = ni_response

        ok = Mock()
        ok.status_code = 200
        mock_blade.post_tls_policies_network_interfaces.return_value = ok

        try:
            main()
        except SystemExit:
            pass

        mock_blade.patch_tls_policies.assert_not_called()
        mock_blade.post_tls_policies_network_interfaces.assert_called_once_with(
            policy_names=["tls1"],
            member_names=["data1.eth0"],
        )
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    @patch("plugins.modules.purefb_tls_policy.TlsPolicyPost")
    @patch("plugins.modules.purefb_tls_policy.get_system")
    @patch("plugins.modules.purefb_tls_policy.AnsibleModule")
    @patch("plugins.modules.purefb_tls_policy.HAS_PYPURECLIENT", True)
    def test_main_create_fails(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_policy_post,
        mock_loose_version,
    ):
        """Test create surfaces backend errors via fail_json"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "tls1",
            "state": "present",
            "enabled": None,
            "appliance_certificate": None,
            "client_certificates_required": None,
            "trusted_client_certificate_authority": None,
            "verify_client_certificate_trust": None,
            "min_tls_version": None,
            "enabled_tls_ciphers": None,
            "disabled_tls_ciphers": None,
            "network_interfaces": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.17"]
        mock_get_system.return_value = mock_blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_tls_policies.return_value = get_response

        post_response = Mock()
        post_response.status_code = 400
        err = Mock()
        err.message = "boom"
        post_response.errors = [err]
        mock_blade.post_tls_policies.return_value = post_response

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert (
            "Failed to create TLS policy" in mock_module.fail_json.call_args[1]["msg"]
        )

    # ---------------- main() failure paths for new gating ----------------

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    @patch("plugins.modules.purefb_tls_policy.get_system")
    @patch("plugins.modules.purefb_tls_policy.AnsibleModule")
    @patch("plugins.modules.purefb_tls_policy.HAS_PYPURECLIENT", True)
    def test_main_mutual_tls_blocked_on_217(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test main fails when a mutual-TLS param is set on a 2.17-only array"""
        # Base 2.17 check passes (False), but mutual-TLS 2.18 check fails (True).
        mock_loose_version.return_value.__gt__ = Mock(side_effect=[False, True])
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "tls1",
            "state": "present",
            "enabled": None,
            "appliance_certificate": None,
            "client_certificates_required": True,
            "trusted_client_certificate_authority": None,
            "verify_client_certificate_trust": None,
            "min_tls_version": None,
            "enabled_tls_ciphers": None,
            "disabled_tls_ciphers": None,
            "network_interfaces": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.17"]
        mock_get_system.return_value = mock_blade

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "Mutual TLS" in msg
        assert "2.18" in msg

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    @patch("plugins.modules.purefb_tls_policy.get_system")
    @patch("plugins.modules.purefb_tls_policy.AnsibleModule")
    @patch("plugins.modules.purefb_tls_policy.HAS_PYPURECLIENT", True)
    def test_main_attach_to_missing_interface_fails(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test main fails before posting when a target interface does not exist"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "tls1",
            "state": "present",
            "enabled": None,
            "appliance_certificate": None,
            "client_certificates_required": None,
            "trusted_client_certificate_authority": None,
            "verify_client_certificate_trust": None,
            "min_tls_version": None,
            "enabled_tls_ciphers": None,
            "disabled_tls_ciphers": None,
            "network_interfaces": ["ghost.eth0"],
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.17"]
        mock_get_system.return_value = mock_blade

        # Policy doesn't exist -> create path
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_tls_policies.return_value = get_response

        # No interfaces match
        ni_response = Mock()
        ni_response.status_code = 200
        ni_response.items = []
        mock_blade.get_network_interfaces.return_value = ni_response

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert "ghost.eth0" in mock_module.fail_json.call_args[1]["msg"]
        mock_blade.post_tls_policies.assert_not_called()
        mock_blade.post_tls_policies_network_interfaces.assert_not_called()

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    @patch("plugins.modules.purefb_tls_policy.get_system")
    @patch("plugins.modules.purefb_tls_policy.AnsibleModule")
    @patch("plugins.modules.purefb_tls_policy.HAS_PYPURECLIENT", True)
    def test_main_attach_conflict_fails(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test main fails when target interface already has a different TLS policy"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "tls1",
            "state": "present",
            "enabled": None,
            "appliance_certificate": None,
            "client_certificates_required": None,
            "trusted_client_certificate_authority": None,
            "verify_client_certificate_trust": None,
            "min_tls_version": None,
            "enabled_tls_ciphers": None,
            "disabled_tls_ciphers": None,
            "network_interfaces": ["data1.eth0"],
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.17"]
        mock_get_system.return_value = mock_blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_tls_policies.return_value = get_response

        iface = Mock()
        iface.name = "data1.eth0"
        ni_response = Mock()
        ni_response.status_code = 200
        ni_response.items = [iface]
        mock_blade.get_network_interfaces.return_value = ni_response

        member = Mock()
        member.member = Mock()
        member.member.name = "data1.eth0"
        member.policy = Mock()
        member.policy.name = "other-tls"
        conflict_response = Mock()
        conflict_response.status_code = 200
        conflict_response.items = [member]
        mock_blade.get_tls_policies_network_interfaces.return_value = conflict_response

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "other-tls" in msg
        mock_blade.post_tls_policies.assert_not_called()
        mock_blade.post_tls_policies_network_interfaces.assert_not_called()

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    @patch("plugins.modules.purefb_tls_policy.get_system")
    @patch("plugins.modules.purefb_tls_policy.AnsibleModule")
    @patch("plugins.modules.purefb_tls_policy.HAS_PYPURECLIENT", True)
    def test_main_api_version_too_old(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test failure when API version is too old"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "tls1",
            "state": "present",
            "enabled": None,
            "appliance_certificate": None,
            "client_certificates_required": None,
            "trusted_client_certificate_authority": None,
            "verify_client_certificate_trust": None,
            "min_tls_version": None,
            "enabled_tls_ciphers": None,
            "disabled_tls_ciphers": None,
            "network_interfaces": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.10"]
        mock_get_system.return_value = mock_blade

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert (
            "FlashBlade REST version not supported"
            in mock_module.fail_json.call_args[1]["msg"]
        )

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    @patch("plugins.modules.purefb_tls_policy.TlsPolicyPost")
    @patch("plugins.modules.purefb_tls_policy.get_system")
    @patch("plugins.modules.purefb_tls_policy.AnsibleModule")
    @patch("plugins.modules.purefb_tls_policy.HAS_PYPURECLIENT", True)
    def test_main_create_attach_second_interface_fails_reports_first_succeeded(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_policy_post,
        mock_loose_version,
    ):
        """Test create-attach loop fails fast on 2nd interface and reports the 1st as already attached"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "tls1",
            "state": "present",
            "enabled": None,
            "appliance_certificate": None,
            "client_certificates_required": None,
            "trusted_client_certificate_authority": None,
            "verify_client_certificate_trust": None,
            "min_tls_version": None,
            "enabled_tls_ciphers": None,
            "disabled_tls_ciphers": None,
            "network_interfaces": ["data1.eth0", "data2.eth0", "data3.eth0"],
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.17"]
        mock_get_system.return_value = mock_blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_tls_policies.return_value = get_response

        iface1 = Mock()
        iface1.name = "data1.eth0"
        iface2 = Mock()
        iface2.name = "data2.eth0"
        iface3 = Mock()
        iface3.name = "data3.eth0"
        ni_response = Mock()
        ni_response.status_code = 200
        ni_response.items = [iface1, iface2, iface3]
        mock_blade.get_network_interfaces.return_value = ni_response

        conflict_response = Mock()
        conflict_response.status_code = 200
        conflict_response.items = []
        mock_blade.get_tls_policies_network_interfaces.return_value = conflict_response

        ok = Mock()
        ok.status_code = 200
        mock_blade.post_tls_policies.return_value = ok

        fail = Mock()
        fail.status_code = 500
        fail.errors = []
        mock_blade.post_tls_policies_network_interfaces.side_effect = [ok, fail]

        try:
            main()
        except SystemExit:
            pass

        # First attach for data1 succeeded, second for data2 failed, third never attempted.
        assert mock_blade.post_tls_policies_network_interfaces.call_count == 2
        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "Failed to attach TLS policy tls1 to interface data2.eth0" in msg
        assert "Already attached: ['data1.eth0']" in msg

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    @patch("plugins.modules.purefb_tls_policy.get_system")
    @patch("plugins.modules.purefb_tls_policy.AnsibleModule")
    @patch("plugins.modules.purefb_tls_policy.HAS_PYPURECLIENT", True)
    def test_main_delete_after_detach_partial_failure_message(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test delete failure after successful detach reports the detached interfaces"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "tls1",
            "state": "absent",
            "enabled": None,
            "appliance_certificate": None,
            "client_certificates_required": None,
            "trusted_client_certificate_authority": None,
            "verify_client_certificate_trust": None,
            "min_tls_version": None,
            "enabled_tls_ciphers": None,
            "disabled_tls_ciphers": None,
            "network_interfaces": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.17"]
        mock_get_system.return_value = mock_blade

        existing = Mock()
        existing.name = "tls1"
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        mock_blade.get_tls_policies.return_value = get_response

        m1 = Mock()
        m1.member = Mock()
        m1.member.name = "data1.eth0"
        attached_response = Mock()
        attached_response.status_code = 200
        attached_response.items = [m1]
        mock_blade.get_tls_policies_network_interfaces.return_value = attached_response

        detach_ok = Mock()
        detach_ok.status_code = 200
        mock_blade.delete_tls_policies_network_interfaces.return_value = detach_ok

        delete_fail = Mock()
        delete_fail.status_code = 500
        delete_fail.errors = []
        mock_blade.delete_tls_policies.return_value = delete_fail

        try:
            main()
        except SystemExit:
            pass

        mock_blade.delete_tls_policies_network_interfaces.assert_called_once()
        mock_blade.delete_tls_policies.assert_called_once()
        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "Failed to delete TLS policy" in msg
        assert "already been detached" in msg
        assert "data1.eth0" in msg
