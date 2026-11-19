# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_tls_policy module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import fnmatch
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

from plugins.module_utils.version import LooseVersion as RealLooseVersion
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

    @patch("plugins.modules.purefb_tls_policy.get_error_message")
    def test_get_policy_returns_none_when_array_says_missing(self, mock_get_error):
        """Test _get_policy returns None for the array's "does not exist" answer"""
        mock_get_error.return_value = "TLS Policy does not exist."
        mock_module = Mock()
        mock_module.params = {"name": "tls1"}
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        mock_response = Mock(spec=["status_code", "errors"])
        mock_response.status_code = 400
        mock_blade.get_tls_policies.return_value = mock_response

        assert _get_policy(mock_module, mock_blade) is None
        mock_module.fail_json.assert_not_called()

    @patch("plugins.modules.purefb_tls_policy.get_error_message")
    def test_get_policy_fails_on_any_other_error(self, mock_get_error):
        """Test _get_policy reports an answer that does not say the policy is missing"""
        mock_get_error.return_value = "Operation not permitted."
        mock_module = Mock()
        mock_module.params = {"name": "tls1"}
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        mock_response = Mock(spec=["status_code", "errors"])
        mock_response.status_code = 400
        mock_blade.get_tls_policies.return_value = mock_response

        try:
            _get_policy(mock_module, mock_blade)
        except SystemExit:
            pass
        mock_module.fail_json.assert_called_once_with(
            msg="Failed to read TLS policy tls1. Error: Operation not permitted."
        )

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

    @patch("plugins.modules.purefb_tls_policy.get_error_message")
    def test_get_attached_interfaces_fails_on_error(self, mock_get_error):
        """Test _get_attached_interfaces reports a list the array does not return"""
        mock_get_error.return_value = "Operation not permitted."
        mock_module = Mock()
        mock_module.params = {"name": "tls1"}
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        mock_response = Mock(spec=["status_code", "errors"])
        mock_response.status_code = 400
        mock_blade.get_tls_policies_network_interfaces.return_value = mock_response

        try:
            _get_attached_interfaces(mock_module, mock_blade)
        except SystemExit:
            pass
        mock_module.fail_json.assert_called_once_with(
            msg="Failed to list the network interfaces of TLS policy tls1. "
            "Error: Operation not permitted."
        )

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
            "appliance_certificate": "my_cert",
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
            "appliance_certificate": "my_cert",
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
            "appliance_certificate": "my_cert",
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
            "appliance_certificate": "my_cert",
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
            "appliance_certificate": "my_cert",
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
            "appliance_certificate": "my_cert",
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

    @patch("plugins.modules.purefb_tls_policy.LooseVersion")
    @patch("plugins.modules.purefb_tls_policy.get_system")
    @patch("plugins.modules.purefb_tls_policy.AnsibleModule")
    @patch("plugins.modules.purefb_tls_policy.HAS_PYPURECLIENT", True)
    def test_main_create_without_appliance_certificate_fails(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test create fails early when appliance_certificate is not given"""
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

        try:
            main()
        except SystemExit:
            pass

        mock_blade.post_tls_policies.assert_not_called()
        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "appliance_certificate is required" in msg


# ---------------- realm names, scope checks, letter case and checked reads ----------------

MOD = "plugins.modules.purefb_tls_policy"
WRITES = (
    "post_tls_policies",
    "patch_tls_policies",
    "delete_tls_policies",
    "post_tls_policies_network_interfaces",
    "delete_tls_policies_network_interfaces",
)


def _params(**overrides):
    params = {
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
    params.update(overrides)
    return params


def _key(name):
    """The array matches names without regard to letter case and outer blanks."""
    return name.strip().lower()


def _named(name):
    item = Mock()
    item.name = name
    return item


def _policy(name, certificate="global", trusted_ca=None, **fields):
    """A TLS policy as GET /tls-policies returns it.

    An unset trusted CA comes back as an empty reference, whose name is None.
    """
    policy = Mock()
    policy.name = name
    policy.enabled = fields.get("enabled", True)
    policy.min_tls_version = fields.get("min_tls_version", "default")
    policy.enabled_tls_ciphers = fields.get("enabled_tls_ciphers", ["default"])
    policy.disabled_tls_ciphers = fields.get("disabled_tls_ciphers", [])
    policy.appliance_certificate = _named(certificate)
    policy.trusted_client_certificate_authority = _named(trusted_ca)
    policy.client_certificates_required = fields.get(
        "client_certificates_required", False
    )
    policy.verify_client_certificate_trust = fields.get(
        "verify_client_certificate_trust", False
    )
    return policy


def _member(policy_name, interface_name):
    """A policy member as GET /tls-policies/network-interfaces returns it."""
    item = Mock()
    item.policy = _named(policy_name)
    item.member = _named(interface_name)
    return item


def _answer(items=None, error=None):
    """A 200 answer with items, or an error answer, which has no items."""
    if error is None:
        res = Mock()
        res.status_code = 200
        res.items = list(items or [])
        return res
    res = Mock(spec=["status_code", "errors"])
    res.status_code = 400
    err = Mock()
    err.message = error
    res.errors = [err]
    return res


def _error_message(res, default="Unknown error"):
    errors = getattr(res, "errors", None)
    return errors[0].message if errors else default


def _body(**kwargs):
    """Stand-in for the SDK models, so that request bodies are comparable."""
    return dict(kwargs)


def _wire_names(names):
    """Names as a request carries them: a comma separates two names."""
    return [part for name in names for part in name.split(",")]


def _array(policies=(), attached=(), interfaces=(), realms=("realm1",), destroyed=()):
    """A small stateful stand-in for the array.

    It answers as Purity//FB 4.8.8 does: names match without regard to letter
    case, * in a name is a pattern, a missing policy answers 400 "TLS Policy
    does not exist." (its member list "Policy does not exist."), a missing
    interface "Network does not exist." and a missing realm "Realm does not
    exist.". attached holds (policy name, interface name) pairs. POST, PATCH
    and DELETE change that state, so a second run reads it back.
    """
    blade = Mock()
    blade.policies = {_key(policy.name): policy for policy in policies}
    blade.attached = [tuple(pair) for pair in attached]
    stored_interfaces = {_key(name): name for name in interfaces}

    def get_tls_policies(names=None):
        found = []
        for name in _wire_names(names):
            if "*" in name:
                hits = [
                    policy
                    for key, policy in sorted(blade.policies.items())
                    if fnmatch.fnmatchcase(key, _key(name))
                ]
                if not hits:
                    return _answer(error="TLS Policy was not found.")
                found.extend(hits)
            elif _key(name) in blade.policies:
                found.append(blade.policies[_key(name)])
            else:
                return _answer(error="TLS Policy does not exist.")
        return _answer(found)

    def get_members(policy_names=None, member_names=None):
        if policy_names is not None:
            if [name for name in policy_names if _key(name) not in blade.policies]:
                return _answer(error="Policy does not exist.")
            wanted = [_key(name) for name in policy_names]
            pairs = [pair for pair in blade.attached if _key(pair[0]) in wanted]
        else:
            wanted = [_key(name) for name in member_names]
            pairs = [pair for pair in blade.attached if _key(pair[1]) in wanted]
        return _answer([_member(*pair) for pair in pairs])

    def get_network_interfaces(names=None):
        if [name for name in names if _key(name) not in stored_interfaces]:
            return _answer(error="Network does not exist.")
        return _answer([_named(stored_interfaces[_key(name)]) for name in names])

    def get_realms(names=None):
        found = []
        for name in names:
            if _key(name) in [_key(realm) for realm in realms]:
                item = _named(name)
                item.destroyed = False
            elif _key(name) in [_key(realm) for realm in destroyed]:
                item = _named(name)
                item.destroyed = True
            else:
                return _answer(error="Realm does not exist.")
            found.append(item)
        return _answer(found)

    def post_tls_policies(names=None, policy=None):
        fields = dict(policy)
        certificate = fields.pop("appliance_certificate")["name"]
        trusted_ca = fields.pop("trusted_client_certificate_authority", {}).get("name")
        blade.policies[_key(names[0])] = _policy(
            names[0].strip(), certificate, trusted_ca, **fields
        )
        return _answer()

    def patch_tls_policies(names=None, policy=None):
        for name in _wire_names(names):
            stored = blade.policies[_key(name)]
            for field, value in policy.items():
                if field in (
                    "appliance_certificate",
                    "trusted_client_certificate_authority",
                ):
                    setattr(stored, field, _named(value["name"] or None))
                else:
                    setattr(stored, field, value)
        return _answer()

    def delete_tls_policies(names=None):
        for name in _wire_names(names):
            del blade.policies[_key(name)]
        return _answer()

    def post_members(policy_names=None, member_names=None):
        blade.attached.append(
            (
                blade.policies[_key(policy_names[0])].name,
                stored_interfaces[_key(member_names[0])],
            )
        )
        return _answer()

    def delete_members(policy_names=None, member_names=None):
        gone = (_key(policy_names[0]), _key(member_names[0]))
        blade.attached = [
            pair for pair in blade.attached if (_key(pair[0]), _key(pair[1])) != gone
        ]
        return _answer()

    blade.get_tls_policies = Mock(side_effect=get_tls_policies)
    blade.get_tls_policies_network_interfaces = Mock(side_effect=get_members)
    blade.get_network_interfaces = Mock(side_effect=get_network_interfaces)
    blade.get_realms = Mock(side_effect=get_realms)
    blade.post_tls_policies = Mock(side_effect=post_tls_policies)
    blade.patch_tls_policies = Mock(side_effect=patch_tls_policies)
    blade.delete_tls_policies = Mock(side_effect=delete_tls_policies)
    blade.post_tls_policies_network_interfaces = Mock(side_effect=post_members)
    blade.delete_tls_policies_network_interfaces = Mock(side_effect=delete_members)
    return blade


def _writes(blade):
    """The write requests the module sent, in the order of WRITES."""
    return [name for name in WRITES if getattr(blade, name).called]


def _run(blade, check_mode=False, api_version="2.30", **overrides):
    """Run main() against blade and return ("exit" or "fail", its keywords)."""
    module = Mock()
    module.params = _params(**overrides)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    with patch(MOD + ".AnsibleModule", return_value=module), patch(
        MOD + ".HAS_PYPURECLIENT", True
    ), patch(MOD + ".get_system", return_value=blade), patch(
        MOD + ".get_rest_api_version", return_value=api_version
    ), patch(
        MOD + ".LooseVersion", RealLooseVersion
    ), patch(
        MOD + ".get_error_message", _error_message
    ), patch(
        MOD + ".TlsPolicy", side_effect=_body
    ), patch(
        MOD + ".TlsPolicyPost", side_effect=_body
    ), patch(
        MOD + ".ReferenceWritable", side_effect=_body
    ):
        try:
            main()
        except SystemExit:
            pass
    if module.fail_json.called:
        return "fail", module.fail_json.call_args[1]
    return "exit", module.exit_json.call_args[1]


class TestPurefbTlsPolicyOneName:
    """A name the array reads as a pattern or as several names is refused"""

    def test_pattern_name_is_refused_before_any_read(self):
        blade = _array(policies=[_policy("tls1"), _policy("tls2")])
        for check_mode in (True, False):
            outcome, result = _run(
                blade, check_mode=check_mode, name="tls*", state="absent"
            )
            assert outcome == "fail"
            assert "name of one TLS policy" in result["msg"]
            assert "tls*" in result["msg"]
        blade.get_tls_policies.assert_not_called()
        assert _writes(blade) == []
        assert sorted(blade.policies) == ["tls1", "tls2"]

    def test_two_names_in_one_are_refused(self):
        blade = _array(policies=[_policy("tls1"), _policy("tls2")])
        outcome, result = _run(blade, name="tls1,tls2", enabled=False)
        assert outcome == "fail"
        assert "comma" in result["msg"]
        blade.get_tls_policies.assert_not_called()
        assert _writes(blade) == []
        assert blade.policies["tls1"].enabled is True
        assert blade.policies["tls2"].enabled is True

    def test_pattern_in_the_realm_part_is_refused(self):
        blade = _array(policies=[_policy("realm1::data-tls", "realm1::tls-cert")])
        outcome, result = _run(blade, name="*::data-tls", state="absent")
        assert outcome == "fail"
        assert _writes(blade) == []

    def test_answer_with_another_name_is_not_adopted(self):
        blade = _array(policies=[_policy("tls1")])
        blade.get_tls_policies = Mock(return_value=_answer([_policy("tls2")]))
        outcome, result = _run(blade, name="tls1", enabled=False)
        assert outcome == "fail"
        assert "tls2" in result["msg"]
        assert "does not have that name" in result["msg"]
        assert _writes(blade) == []


class TestPurefbTlsPolicyReferenceScope:
    """A policy and the certificates it names are in one scope"""

    def test_global_on_a_new_realm_policy_is_refused(self):
        for check_mode in (True, False):
            blade = _array()
            outcome, result = _run(
                blade,
                check_mode=check_mode,
                name="realm1::data-tls",
                appliance_certificate="global",
            )
            assert outcome == "fail"
            assert "appliance_certificate global cannot be used" in result["msg"]
            assert "built-in certificate of the array" in result["msg"]
            assert "realm1::<name>" in result["msg"]
            blade.get_tls_policies.assert_not_called()
            assert _writes(blade) == []

    def test_global_on_an_existing_realm_policy_is_refused(self):
        for check_mode in (True, False):
            blade = _array(policies=[_policy("realm1::data-tls", "realm1::tls-cert")])
            outcome, result = _run(
                blade,
                check_mode=check_mode,
                name="realm1::data-tls",
                appliance_certificate="global",
                min_tls_version="1.3",
            )
            assert outcome == "fail"
            assert "built-in certificate of the array" in result["msg"]
            assert _writes(blade) == []
            assert blade.policies["realm1::data-tls"].min_tls_version == "default"

    def test_global_in_another_letter_case_is_refused_for_a_realm_policy(self):
        blade = _array()
        outcome, result = _run(
            blade, name="realm1::data-tls", appliance_certificate="GLOBAL"
        )
        assert outcome == "fail"
        assert "built-in certificate of the array" in result["msg"]

    def test_bare_certificate_on_a_realm_policy_is_refused(self):
        for check_mode in (True, False):
            blade = _array(policies=[_policy("realm1::data-tls", "realm1::tls-cert")])
            outcome, result = _run(
                blade,
                check_mode=check_mode,
                name="realm1::data-tls",
                appliance_certificate="tls-cert",
            )
            assert outcome == "fail"
            assert "tls-cert is an array-level name" in result["msg"]
            assert "Name a certificate of that realm" in result["msg"]
            assert _writes(blade) == []

    def test_certificate_of_another_realm_is_refused(self):
        blade = _array(policies=[_policy("realm1::data-tls", "realm1::tls-cert")])
        outcome, result = _run(
            blade,
            check_mode=True,
            name="realm1::data-tls",
            appliance_certificate="realm2::tls-cert",
        )
        assert outcome == "fail"
        assert "realm2::tls-cert is in realm realm2" in result["msg"]
        assert "realm1::<name>" in result["msg"]
        assert _writes(blade) == []

    def test_realm_certificate_on_an_array_level_policy_is_refused(self):
        for check_mode in (True, False):
            blade = _array(policies=[_policy("data-tls", "tls-cert")])
            outcome, result = _run(
                blade,
                check_mode=check_mode,
                name="data-tls",
                appliance_certificate="realm1::tls-cert",
            )
            assert outcome == "fail"
            assert "realm1::tls-cert is in realm realm1" in result["msg"]
            assert "data-tls is an array-level policy" in result["msg"]
            assert "realm1::<policy>" in result["msg"]
            assert _writes(blade) == []

    def test_realm_ca_group_on_an_array_level_policy_is_refused(self):
        blade = _array(policies=[_policy("data-tls", "tls-cert")])
        outcome, result = _run(
            blade,
            check_mode=True,
            name="data-tls",
            trusted_client_certificate_authority="realm1::ca-group",
        )
        assert outcome == "fail"
        assert result["msg"].startswith(
            "trusted_client_certificate_authority realm1::ca-group cannot be used"
        )
        assert _writes(blade) == []

    def test_bare_ca_on_a_realm_policy_is_refused(self):
        blade = _array(policies=[_policy("realm1::data-tls", "realm1::tls-cert")])
        outcome, result = _run(
            blade,
            name="realm1::data-tls",
            trusted_client_certificate_authority="ca-group",
            verify_client_certificate_trust=True,
        )
        assert outcome == "fail"
        assert "ca-group is an array-level name" in result["msg"]
        assert "certificate or certificate group of that realm" in result["msg"]
        assert _writes(blade) == []
        assert (
            blade.policies["realm1::data-tls"].verify_client_certificate_trust is False
        )

    def test_bare_policy_with_a_realm_certificate_is_refused_on_create(self):
        blade = _array()
        outcome, result = _run(
            blade, check_mode=True, name="data-tls", appliance_certificate="realm1::c"
        )
        assert outcome == "fail"
        assert "realm1::<policy>" in result["msg"]
        blade.get_tls_policies.assert_not_called()

    def test_realm_prefix_in_another_letter_case_is_the_same_realm(self):
        blade = _array()
        outcome, result = _run(
            blade,
            name="Realm1::data-tls",
            appliance_certificate="REALM1::tls-cert",
            trusted_client_certificate_authority="realm1::ca-group",
        )
        assert (outcome, result["changed"]) == ("exit", True)
        blade.post_tls_policies.assert_called_once_with(
            names=["Realm1::data-tls"],
            policy={
                "appliance_certificate": {"name": "REALM1::tls-cert"},
                "trusted_client_certificate_authority": {"name": "realm1::ca-group"},
            },
        )

    def test_clearing_the_trusted_ca_of_a_realm_policy_is_allowed(self):
        blade = _array(
            policies=[
                _policy("realm1::data-tls", "realm1::tls-cert", "realm1::ca-group")
            ]
        )
        outcome, result = _run(
            blade, name="realm1::data-tls", trusted_client_certificate_authority=""
        )
        assert (outcome, result["changed"]) == ("exit", True)
        blade.patch_tls_policies.assert_called_once_with(
            names=["realm1::data-tls"],
            policy={"trusted_client_certificate_authority": {"name": ""}},
        )
        outcome, result = _run(
            blade, name="realm1::data-tls", trusted_client_certificate_authority=""
        )
        assert (outcome, result["changed"]) == ("exit", False)
        blade.patch_tls_policies.assert_called_once()

    def test_scope_is_not_checked_for_absent(self):
        blade = _array(policies=[_policy("realm1::data-tls", "realm1::tls-cert")])
        outcome, result = _run(
            blade,
            name="realm1::data-tls",
            state="absent",
            appliance_certificate="global",
        )
        assert (outcome, result["changed"]) == ("exit", True)
        assert blade.policies == {}


class TestPurefbTlsPolicyCreateWithoutCertificate:
    """The create failure names a certificate the policy can use"""

    def test_realm_policy_is_pointed_to_a_certificate_of_its_realm(self):
        for check_mode in (True, False):
            blade = _array()
            outcome, result = _run(
                blade,
                check_mode=check_mode,
                name="realm1::data-tls",
                min_tls_version="1.2",
            )
            assert outcome == "fail"
            assert "appliance_certificate is required" in result["msg"]
            assert "realm1::<certificate>" in result["msg"]
            assert "cannot be used by a TLS policy in a realm" in result["msg"]
            assert "can use 'global'" not in result["msg"]
            assert _writes(blade) == []

    def test_array_level_policy_keeps_the_global_hint(self):
        blade = _array()
        outcome, result = _run(blade, name="data-tls", min_tls_version="1.2")
        assert outcome == "fail"
        assert "TLS policy data-tls was not found" in result["msg"]
        assert "appliance_certificate is required" in result["msg"]
        assert "an array-level policy can use 'global'" in result["msg"]
        assert "<realm>::<policy>" in result["msg"]
        blade.get_realms.assert_not_called()
        assert _writes(blade) == []

    def test_bare_leaf_of_a_realm_policy_names_the_realm_form(self):
        """A realm-scoped administrator is told "does not exist" for a bare name"""
        blade = _array(policies=[_policy("realm1::data-tls", "realm1::tls-cert")])
        outcome, result = _run(blade, name="data-tls", min_tls_version="1.3")
        assert outcome == "fail"
        assert "was not found" in result["msg"]
        assert "realm-scoped administrator must use that form" in result["msg"]
        assert _writes(blade) == []
        assert blade.policies["realm1::data-tls"].min_tls_version == "default"


class TestPurefbTlsPolicyRealmOfANewPolicy:
    """A create in a realm that cannot take the policy fails in both modes"""

    def test_unknown_realm_fails_before_the_create(self):
        for check_mode in (True, False):
            blade = _array(realms=("realm1",))
            outcome, result = _run(
                blade,
                check_mode=check_mode,
                name="nosuch::data-tls",
                appliance_certificate="nosuch::tls-cert",
            )
            assert outcome == "fail"
            assert "cannot be created in realm nosuch" in result["msg"]
            assert "Realm does not exist." in result["msg"]
            blade.get_realms.assert_called_once_with(names=["nosuch"])
            assert _writes(blade) == []

    def test_destroyed_realm_fails_before_the_create(self):
        for check_mode in (True, False):
            blade = _array(realms=("realm1",), destroyed=("realm9",))
            outcome, result = _run(
                blade,
                check_mode=check_mode,
                name="realm9::data-tls",
                appliance_certificate="realm9::tls-cert",
            )
            assert outcome == "fail"
            assert "Realm has been destroyed." in result["msg"]
            assert _writes(blade) == []

    def test_unknown_realm_outranks_the_missing_certificate(self):
        blade = _array(realms=())
        outcome, result = _run(blade, name="nosuch::data-tls", min_tls_version="1.3")
        assert outcome == "fail"
        assert "Realm does not exist." in result["msg"]
        assert "appliance_certificate" not in result["msg"]

    def test_realm_lookup_that_is_not_answered_is_left_to_the_create(self):
        blade = _array()
        blade.get_realms = Mock(return_value=_answer(error="Operation not permitted."))
        outcome, result = _run(
            blade, name="realm1::data-tls", appliance_certificate="realm1::tls-cert"
        )
        assert (outcome, result["changed"]) == ("exit", True)
        blade.post_tls_policies.assert_called_once()

    def test_realm_is_not_read_below_rest_2_19(self):
        blade = _array(realms=())
        outcome, result = _run(
            blade,
            api_version="2.18",
            name="realm1::data-tls",
            appliance_certificate="realm1::tls-cert",
        )
        assert (outcome, result["changed"]) == ("exit", True)
        blade.get_realms.assert_not_called()
        blade.post_tls_policies.assert_called_once()

    def test_array_level_create_reads_no_realm(self):
        blade = _array(realms=())
        outcome, result = _run(blade, name="data-tls", appliance_certificate="global")
        assert (outcome, result["changed"]) == ("exit", True)
        blade.get_realms.assert_not_called()
        blade.post_tls_policies.assert_called_once_with(
            names=["data-tls"], policy={"appliance_certificate": {"name": "global"}}
        )

    def test_existing_realm_policy_reads_no_realm(self):
        blade = _array(
            policies=[_policy("realm1::data-tls", "realm1::tls-cert")], realms=()
        )
        outcome, result = _run(blade, name="realm1::data-tls", min_tls_version="1.3")
        assert (outcome, result["changed"]) == ("exit", True)
        blade.get_realms.assert_not_called()


class TestPurefbTlsPolicyRealmLifecycle:
    """A policy in a realm next to an array-level policy of the same leaf name"""

    def _twins(self):
        return _array(
            policies=[
                _policy("data-tls", "tls-cert"),
                _policy("realm1::data-tls", "realm1::tls-cert"),
            ]
        )

    def test_create_sends_the_names_as_given_and_is_idempotent(self):
        blade = _array(policies=[_policy("data-tls", "tls-cert")])
        task = dict(
            name="realm1::data-tls",
            appliance_certificate="realm1::tls-cert",
            trusted_client_certificate_authority="realm1::ca-group",
            verify_client_certificate_trust=True,
            min_tls_version="1.2",
        )
        outcome, result = _run(blade, check_mode=True, **task)
        assert (outcome, result["changed"]) == ("exit", True)
        assert _writes(blade) == []

        outcome, result = _run(blade, **task)
        assert (outcome, result["changed"]) == ("exit", True)
        blade.post_tls_policies.assert_called_once_with(
            names=["realm1::data-tls"],
            policy={
                "appliance_certificate": {"name": "realm1::tls-cert"},
                "trusted_client_certificate_authority": {"name": "realm1::ca-group"},
                "verify_client_certificate_trust": True,
                "min_tls_version": "1.2",
            },
        )

        outcome, result = _run(blade, **task)
        assert (outcome, result["changed"]) == ("exit", False)
        assert _writes(blade) == ["post_tls_policies"]
        assert blade.policies["data-tls"].appliance_certificate.name == "tls-cert"

    def test_current_realm_certificate_sends_no_patch(self):
        blade = self._twins()
        outcome, result = _run(
            blade, name="realm1::data-tls", appliance_certificate="realm1::tls-cert"
        )
        assert (outcome, result["changed"]) == ("exit", False)
        assert _writes(blade) == []

    def test_certificate_in_another_letter_case_is_not_a_change(self):
        for wanted in ("realm1::TLS-CERT", "REALM1::tls-cert"):
            blade = self._twins()
            for check_mode in (True, False):
                outcome, result = _run(
                    blade,
                    check_mode=check_mode,
                    name="realm1::data-tls",
                    appliance_certificate=wanted,
                )
                assert (outcome, result["changed"]) == ("exit", False)
            assert _writes(blade) == []

    def test_trusted_ca_in_another_letter_case_is_not_a_change(self):
        blade = _array(
            policies=[
                _policy("realm1::data-tls", "realm1::tls-cert", "realm1::ca-group")
            ]
        )
        outcome, result = _run(
            blade,
            name="realm1::data-tls",
            trusted_client_certificate_authority="realm1::CA-Group",
        )
        assert (outcome, result["changed"]) == ("exit", False)
        assert _writes(blade) == []

    def test_another_certificate_of_the_realm_is_patched_once(self):
        blade = self._twins()
        task = dict(name="realm1::data-tls", appliance_certificate="realm1::tls-cert2")
        outcome, result = _run(blade, check_mode=True, **task)
        assert (outcome, result["changed"]) == ("exit", True)
        assert _writes(blade) == []
        outcome, result = _run(blade, **task)
        assert (outcome, result["changed"]) == ("exit", True)
        blade.patch_tls_policies.assert_called_once_with(
            names=["realm1::data-tls"],
            policy={"appliance_certificate": {"name": "realm1::tls-cert2"}},
        )
        outcome, result = _run(blade, **task)
        assert (outcome, result["changed"]) == ("exit", False)
        blade.patch_tls_policies.assert_called_once()
        assert blade.policies["data-tls"].appliance_certificate.name == "tls-cert"

    def test_array_level_namesake_is_changed_alone(self):
        blade = self._twins()
        outcome, result = _run(
            blade, name="data-tls", appliance_certificate="global", enabled=False
        )
        assert (outcome, result["changed"]) == ("exit", True)
        blade.patch_tls_policies.assert_called_once_with(
            names=["data-tls"],
            policy={"enabled": False, "appliance_certificate": {"name": "global"}},
        )
        realm_policy = blade.policies["realm1::data-tls"]
        assert realm_policy.enabled is True
        assert realm_policy.appliance_certificate.name == "realm1::tls-cert"

    def test_policy_name_in_another_letter_case_is_the_same_policy(self):
        blade = self._twins()
        outcome, result = _run(blade, name="REALM1::Data-TLS", min_tls_version="1.3")
        assert (outcome, result["changed"]) == ("exit", True)
        blade.post_tls_policies.assert_not_called()
        assert blade.policies["realm1::data-tls"].min_tls_version == "1.3"
        outcome, result = _run(blade, name="REALM1::Data-TLS", min_tls_version="1.3")
        assert (outcome, result["changed"]) == ("exit", False)

    def test_delete_twice_leaves_the_namesake(self):
        blade = self._twins()
        task = dict(name="realm1::data-tls", state="absent")
        outcome, result = _run(blade, check_mode=True, **task)
        assert (outcome, result["changed"]) == ("exit", True)
        assert _writes(blade) == []
        outcome, result = _run(blade, **task)
        assert (outcome, result["changed"]) == ("exit", True)
        blade.delete_tls_policies.assert_called_once_with(names=["realm1::data-tls"])
        outcome, result = _run(blade, **task)
        assert (outcome, result["changed"]) == ("exit", False)
        blade.delete_tls_policies.assert_called_once()
        assert sorted(blade.policies) == ["data-tls"]


class TestPurefbTlsPolicyRealmInterfaces:
    """Interface attachments of a policy in a realm"""

    def _blade(self, attached=()):
        return _array(
            policies=[
                _policy("data-tls", "tls-cert"),
                _policy("realm1::data-tls", "realm1::tls-cert"),
            ],
            attached=[("data-tls", "vip1")] + list(attached),
            interfaces=["vip1", "realm1::vip1", "realm1::vip2"],
        )

    def test_attach_a_realm_interface_once(self):
        blade = self._blade()
        task = dict(name="realm1::data-tls", network_interfaces=["realm1::vip1"])
        outcome, result = _run(blade, check_mode=True, **task)
        assert (outcome, result["changed"]) == ("exit", True)
        assert _writes(blade) == []
        outcome, result = _run(blade, **task)
        assert (outcome, result["changed"]) == ("exit", True)
        blade.post_tls_policies_network_interfaces.assert_called_once_with(
            policy_names=["realm1::data-tls"], member_names=["realm1::vip1"]
        )
        outcome, result = _run(blade, **task)
        assert (outcome, result["changed"]) == ("exit", False)
        assert _writes(blade) == ["post_tls_policies_network_interfaces"]
        assert ("data-tls", "vip1") in blade.attached

    def test_attached_interface_in_another_letter_case_is_left_alone(self):
        blade = self._blade(attached=[("realm1::data-tls", "realm1::vip1")])
        for check_mode in (True, False):
            outcome, result = _run(
                blade,
                check_mode=check_mode,
                name="realm1::data-tls",
                network_interfaces=["REALM1::VIP1"],
            )
            assert (outcome, result["changed"]) == ("exit", False)
        assert _writes(blade) == []
        assert ("realm1::data-tls", "realm1::vip1") in blade.attached

    def test_replace_the_interface_of_a_realm_policy(self):
        blade = self._blade(attached=[("realm1::data-tls", "realm1::vip1")])
        outcome, result = _run(
            blade, name="realm1::data-tls", network_interfaces=["realm1::vip2"]
        )
        assert (outcome, result["changed"]) == ("exit", True)
        blade.post_tls_policies_network_interfaces.assert_called_once_with(
            policy_names=["realm1::data-tls"], member_names=["realm1::vip2"]
        )
        blade.delete_tls_policies_network_interfaces.assert_called_once_with(
            policy_names=["realm1::data-tls"], member_names=["realm1::vip1"]
        )
        assert sorted(blade.attached) == [
            ("data-tls", "vip1"),
            ("realm1::data-tls", "realm1::vip2"),
        ]

    def test_empty_list_detaches_the_realm_policy_only(self):
        blade = self._blade(attached=[("realm1::data-tls", "realm1::vip1")])
        task = dict(name="realm1::data-tls", network_interfaces=[])
        outcome, result = _run(blade, **task)
        assert (outcome, result["changed"]) == ("exit", True)
        blade.delete_tls_policies_network_interfaces.assert_called_once_with(
            policy_names=["realm1::data-tls"], member_names=["realm1::vip1"]
        )
        outcome, result = _run(blade, **task)
        assert (outcome, result["changed"]) == ("exit", False)
        assert blade.attached == [("data-tls", "vip1")]

    def test_interface_of_another_policy_of_the_realm_is_a_conflict(self):
        blade = self._blade(attached=[("realm1::other-tls", "realm1::vip2")])
        outcome, result = _run(
            blade,
            check_mode=True,
            name="realm1::data-tls",
            network_interfaces=["realm1::vip2"],
        )
        assert outcome == "fail"
        assert "realm1::vip2=>realm1::other-tls" in result["msg"]
        assert _writes(blade) == []

    def test_own_policy_in_another_letter_case_is_no_conflict(self):
        module = Mock()
        module.params = {"name": "REALM1::Data-TLS"}
        module.fail_json = Mock(side_effect=SystemExit)
        blade = self._blade(attached=[("realm1::data-tls", "realm1::vip1")])
        _validate_attachable(module, blade, ["Realm1::VIP1"])
        module.fail_json.assert_not_called()

    def test_delete_detaches_the_realm_interface_of_the_policy_only(self):
        blade = self._blade(attached=[("realm1::data-tls", "realm1::vip1")])
        outcome, result = _run(blade, name="realm1::data-tls", state="absent")
        assert (outcome, result["changed"]) == ("exit", True)
        assert _writes(blade) == [
            "delete_tls_policies",
            "delete_tls_policies_network_interfaces",
        ]
        assert blade.attached == [("data-tls", "vip1")]
        assert sorted(blade.policies) == ["data-tls"]


class TestPurefbTlsPolicyCheckedReads:
    """A read the array refuses is reported, never taken as absent or empty"""

    def _refuse(self, blade, method):
        setattr(
            blade,
            method,
            Mock(return_value=_answer(error="Operation not permitted.")),
        )

    def test_refused_policy_read_fails_present(self):
        for check_mode in (True, False):
            blade = _array()
            self._refuse(blade, "get_tls_policies")
            outcome, result = _run(
                blade,
                check_mode=check_mode,
                name="realm1::data-tls",
                appliance_certificate="realm1::tls-cert",
            )
            assert outcome == "fail"
            assert result["msg"] == (
                "Failed to read TLS policy realm1::data-tls. Error: "
                "Operation not permitted."
            )
            assert _writes(blade) == []

    def test_refused_policy_read_fails_absent(self):
        for check_mode in (True, False):
            blade = _array(policies=[_policy("data-tls", "tls-cert")])
            self._refuse(blade, "get_tls_policies")
            outcome, result = _run(
                blade, check_mode=check_mode, name="data-tls", state="absent"
            )
            assert outcome == "fail"
            assert "Operation not permitted." in result["msg"]
            assert _writes(blade) == []

    def test_missing_policy_is_absent(self):
        blade = _array()
        outcome, result = _run(blade, name="realm1::data-tls", state="absent")
        assert (outcome, result["changed"]) == ("exit", False)
        assert _writes(blade) == []

    def test_refused_member_list_fails_the_reconcile(self):
        for check_mode in (True, False):
            blade = _array(policies=[_policy("realm1::data-tls", "realm1::tls-cert")])
            self._refuse(blade, "get_tls_policies_network_interfaces")
            outcome, result = _run(
                blade,
                check_mode=check_mode,
                name="realm1::data-tls",
                network_interfaces=[],
            )
            assert outcome == "fail"
            assert result["msg"] == (
                "Failed to list the network interfaces of TLS policy "
                "realm1::data-tls. Error: Operation not permitted."
            )
            assert _writes(blade) == []

    def test_refused_member_list_fails_the_delete_before_any_write(self):
        blade = _array(
            policies=[_policy("data-tls", "tls-cert")], attached=[("data-tls", "vip1")]
        )
        self._refuse(blade, "get_tls_policies_network_interfaces")
        outcome, result = _run(blade, name="data-tls", state="absent")
        assert outcome == "fail"
        assert "Failed to list the network interfaces" in result["msg"]
        assert _writes(blade) == []
        assert sorted(blade.policies) == ["data-tls"]

    def test_refused_conflict_read_fails_the_attach(self):
        blade = _array(policies=[_policy("data-tls", "tls-cert")], interfaces=["vip1"])
        members = blade.get_tls_policies_network_interfaces.side_effect

        def refuse_by_member(policy_names=None, member_names=None):
            if member_names is not None:
                return _answer(error="Operation not permitted.")
            return members(policy_names=policy_names)

        blade.get_tls_policies_network_interfaces = Mock(side_effect=refuse_by_member)
        for check_mode in (True, False):
            outcome, result = _run(
                blade,
                check_mode=check_mode,
                name="data-tls",
                network_interfaces=["vip1"],
            )
            assert outcome == "fail"
            assert result["msg"] == (
                "Failed to read the TLS policies of network interface(s) "
                "['vip1']. Error: Operation not permitted."
            )
        assert _writes(blade) == []
