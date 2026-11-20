# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_s3acc_export module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import importlib
import multiprocessing
import ctypes
from contextlib import ExitStack
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

from plugins.modules.purefb_s3acc_export import (
    main,
    _get_export,
)
import plugins.modules.purefb_s3acc_export as s3acc_export_module


class TestPurefbS3accExport:
    """Test cases for purefb_s3acc_export module"""

    # ---------------- _get_export tests ----------------

    def test_get_export_returns_first_item(self):
        """Test _get_export returns the first export when present"""
        mock_module = Mock()
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "context": "",
        }

        existing_export = Mock()
        existing_export.name = "acme/fb-01"

        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.items = [existing_export]
        mock_blade.get_object_store_account_exports.return_value = mock_response

        out = _get_export(mock_module, mock_blade)

        assert out is not None
        mock_blade.get_object_store_account_exports.assert_called_once_with(
            filter="member.name='acme' and server.name='fb-01'"
        )

    def test_get_export_passes_context_when_set(self):
        """Test _get_export forwards context_names when context is set"""
        mock_module = Mock()
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "context": "fleet1",
        }

        existing_export = Mock()
        existing_export.name = "acme/fb-01"

        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.items = [existing_export]
        mock_blade.get_object_store_account_exports.return_value = mock_response

        _get_export(mock_module, mock_blade)

        mock_blade.get_object_store_account_exports.assert_called_once_with(
            filter="member.name='acme' and server.name='fb-01'",
            context_names=["fleet1"],
        )

    @patch(
        "plugins.modules.purefb_s3acc_export.get_error_message",
        return_value="Unknown attribute.",
    )
    def test_get_export_fails_on_api_error(self, mock_get_error_message):
        """A failed lookup is reported, not treated as 'no export'"""
        mock_module = Mock()
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "context": "",
        }

        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.items = []
        mock_blade.get_object_store_account_exports.return_value = mock_response

        try:
            _get_export(mock_module, mock_blade)
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "Failed to get account export for account acme on server fb-01" in msg
        assert "Unknown attribute." in msg

    def test_get_export_returns_none_when_no_items(self):
        """Test _get_export returns None when no export matches the filter"""
        mock_module = Mock()
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "context": "",
        }

        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.items = []
        mock_blade.get_object_store_account_exports.return_value = mock_response

        out = _get_export(mock_module, mock_blade)

        assert out is None

    # ---------------- main() create flows ----------------

    @patch("plugins.modules.purefb_s3acc_export.LooseVersion")
    @patch("plugins.modules.purefb_s3acc_export.Reference")
    @patch("plugins.modules.purefb_s3acc_export.ObjectStoreAccountExportPost")
    @patch("plugins.modules.purefb_s3acc_export.get_system")
    @patch("plugins.modules.purefb_s3acc_export.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc_export.HAS_PYPURECLIENT", True)
    def test_main_creates_export(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_post_cls,
        mock_reference_cls,
        mock_loose_version,
    ):
        """Test creating a new account export"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "policy": "acme-export",
            "enabled": True,
            "state": "present",
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        # Export does not exist
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_object_store_account_exports.return_value = get_response

        # Mock successful create
        post_response = Mock()
        post_response.status_code = 200
        mock_blade.post_object_store_account_exports.return_value = post_response

        try:
            main()
        except SystemExit:
            pass

        mock_blade.post_object_store_account_exports.assert_called_once()
        call_kwargs = mock_blade.post_object_store_account_exports.call_args[1]
        assert call_kwargs["member_names"] == ["acme"]
        assert call_kwargs["policy_names"] == ["acme-export"]

        mock_module.exit_json.assert_called_once()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_s3acc_export.LooseVersion")
    @patch("plugins.modules.purefb_s3acc_export.Reference")
    @patch("plugins.modules.purefb_s3acc_export.ObjectStoreAccountExportPost")
    @patch("plugins.modules.purefb_s3acc_export.get_system")
    @patch("plugins.modules.purefb_s3acc_export.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc_export.HAS_PYPURECLIENT", True)
    def test_main_create_check_mode_skips_post(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_post_cls,
        mock_reference_cls,
        mock_loose_version,
    ):
        """Test create reports changed but skips POST in check mode"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "policy": "acme-export",
            "enabled": True,
            "state": "present",
            "context": "",
        }
        mock_module.check_mode = True
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_object_store_account_exports.return_value = get_response

        # Check mode looks up the account, the server and the policy
        found = Mock()
        found.status_code = 200
        mock_blade.get_object_store_accounts.return_value = found
        mock_blade.get_servers.return_value = found
        mock_blade.get_s3_export_policies.return_value = found

        try:
            main()
        except SystemExit:
            pass

        mock_blade.post_object_store_account_exports.assert_not_called()
        mock_module.warn.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_s3acc_export.LooseVersion")
    @patch("plugins.modules.purefb_s3acc_export.get_system")
    @patch("plugins.modules.purefb_s3acc_export.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc_export.HAS_PYPURECLIENT", True)
    def test_main_create_without_policy_fails(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test create fails when policy is not supplied"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "policy": None,
            "enabled": None,
            "state": "present",
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_object_store_account_exports.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert "policy is required" in mock_module.fail_json.call_args[1]["msg"]

    @patch("plugins.modules.purefb_s3acc_export.LooseVersion")
    @patch("plugins.modules.purefb_s3acc_export.Reference")
    @patch("plugins.modules.purefb_s3acc_export.ObjectStoreAccountExportPost")
    @patch("plugins.modules.purefb_s3acc_export.get_system")
    @patch("plugins.modules.purefb_s3acc_export.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc_export.HAS_PYPURECLIENT", True)
    def test_main_create_failure_calls_fail_json(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_post_cls,
        mock_reference_cls,
        mock_loose_version,
    ):
        """Test SDK error on create is surfaced via fail_json"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "policy": "acme-export",
            "enabled": True,
            "state": "present",
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_object_store_account_exports.return_value = get_response

        post_response = Mock()
        post_response.status_code = 400
        post_err = Mock()
        post_err.message = "nope"
        post_response.errors = [post_err]
        mock_blade.post_object_store_account_exports.return_value = post_response

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert (
            "Failed to create account export"
            in mock_module.fail_json.call_args[1]["msg"]
        )

    # ---------------- main() update flows ----------------

    @patch("plugins.modules.purefb_s3acc_export.LooseVersion")
    @patch("plugins.modules.purefb_s3acc_export.Reference")
    @patch("plugins.modules.purefb_s3acc_export.ObjectStoreAccountExportPatch")
    @patch("plugins.modules.purefb_s3acc_export.get_system")
    @patch("plugins.modules.purefb_s3acc_export.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc_export.HAS_PYPURECLIENT", True)
    def test_main_updates_enabled_flag(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_patch_cls,
        mock_reference_cls,
        mock_loose_version,
    ):
        """Test updating the enabled flag on an existing export"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "policy": None,
            "enabled": False,
            "state": "present",
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        existing_export = Mock()
        existing_export.name = "acme/fb-01"
        existing_export.enabled = True
        existing_export.policy = Mock()
        existing_export.policy.name = "acme-export"

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing_export]
        mock_blade.get_object_store_account_exports.return_value = get_response

        patch_response = Mock()
        patch_response.status_code = 200
        mock_blade.patch_object_store_account_exports.return_value = patch_response

        try:
            main()
        except SystemExit:
            pass

        mock_blade.patch_object_store_account_exports.assert_called_once()
        call_kwargs = mock_blade.patch_object_store_account_exports.call_args[1]
        assert call_kwargs["names"] == ["acme/fb-01"]
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_s3acc_export.LooseVersion")
    @patch("plugins.modules.purefb_s3acc_export.Reference")
    @patch("plugins.modules.purefb_s3acc_export.ObjectStoreAccountExportPatch")
    @patch("plugins.modules.purefb_s3acc_export.get_system")
    @patch("plugins.modules.purefb_s3acc_export.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc_export.HAS_PYPURECLIENT", True)
    def test_main_updates_policy(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_patch_cls,
        mock_reference_cls,
        mock_loose_version,
    ):
        """Test re-pointing an export at a different policy"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "policy": "acme-export-v2",
            "enabled": None,
            "state": "present",
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        existing_export = Mock()
        existing_export.name = "acme/fb-01"
        existing_export.enabled = True
        existing_export.policy = Mock()
        existing_export.policy.name = "acme-export"

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing_export]
        mock_blade.get_object_store_account_exports.return_value = get_response

        patch_response = Mock()
        patch_response.status_code = 200
        mock_blade.patch_object_store_account_exports.return_value = patch_response

        try:
            main()
        except SystemExit:
            pass

        mock_blade.patch_object_store_account_exports.assert_called_once()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_s3acc_export.LooseVersion")
    @patch("plugins.modules.purefb_s3acc_export.get_system")
    @patch("plugins.modules.purefb_s3acc_export.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc_export.HAS_PYPURECLIENT", True)
    def test_main_update_idempotent_when_matches(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test update is a no-op when desired state already matches"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "policy": "acme-export",
            "enabled": True,
            "state": "present",
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        existing_export = Mock()
        existing_export.name = "acme/fb-01"
        existing_export.enabled = True
        existing_export.policy = Mock()
        existing_export.policy.name = "acme-export"

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing_export]
        mock_blade.get_object_store_account_exports.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        mock_blade.patch_object_store_account_exports.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_s3acc_export.LooseVersion")
    @patch("plugins.modules.purefb_s3acc_export.Reference")
    @patch("plugins.modules.purefb_s3acc_export.ObjectStoreAccountExportPatch")
    @patch("plugins.modules.purefb_s3acc_export.get_system")
    @patch("plugins.modules.purefb_s3acc_export.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc_export.HAS_PYPURECLIENT", True)
    def test_main_update_failure_calls_fail_json(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_patch_cls,
        mock_reference_cls,
        mock_loose_version,
    ):
        """Test SDK error on update is surfaced via fail_json"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "policy": None,
            "enabled": False,
            "state": "present",
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        existing_export = Mock()
        existing_export.name = "acme/fb-01"
        existing_export.enabled = True
        existing_export.policy = Mock()
        existing_export.policy.name = "acme-export"

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing_export]
        mock_blade.get_object_store_account_exports.return_value = get_response

        patch_response = Mock()
        patch_response.status_code = 400
        patch_err = Mock()
        patch_err.message = "nope"
        patch_response.errors = [patch_err]
        mock_blade.patch_object_store_account_exports.return_value = patch_response

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert (
            "Failed to update account export"
            in mock_module.fail_json.call_args[1]["msg"]
        )

    # ---------------- main() delete flows ----------------

    @patch("plugins.modules.purefb_s3acc_export.LooseVersion")
    @patch("plugins.modules.purefb_s3acc_export.get_system")
    @patch("plugins.modules.purefb_s3acc_export.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc_export.HAS_PYPURECLIENT", True)
    def test_main_deletes_export(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test deleting an existing export"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "policy": None,
            "enabled": None,
            "state": "absent",
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        existing_export = Mock()
        existing_export.name = "acme/fb-01"

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing_export]
        mock_blade.get_object_store_account_exports.return_value = get_response

        delete_response = Mock()
        delete_response.status_code = 200
        mock_blade.delete_object_store_account_exports.return_value = delete_response

        try:
            main()
        except SystemExit:
            pass

        mock_blade.delete_object_store_account_exports.assert_called_once()
        call_kwargs = mock_blade.delete_object_store_account_exports.call_args[1]
        assert call_kwargs["names"] == ["acme/fb-01"]
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_s3acc_export.LooseVersion")
    @patch("plugins.modules.purefb_s3acc_export.get_system")
    @patch("plugins.modules.purefb_s3acc_export.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc_export.HAS_PYPURECLIENT", True)
    def test_main_delete_idempotent_when_absent(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test delete is a no-op when the export does not exist"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "policy": None,
            "enabled": None,
            "state": "absent",
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_object_store_account_exports.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        mock_blade.delete_object_store_account_exports.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_s3acc_export.LooseVersion")
    @patch("plugins.modules.purefb_s3acc_export.get_system")
    @patch("plugins.modules.purefb_s3acc_export.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc_export.HAS_PYPURECLIENT", True)
    def test_main_delete_check_mode_skips_delete(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test delete reports changed but skips DELETE in check mode"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "policy": None,
            "enabled": None,
            "state": "absent",
            "context": "",
        }
        mock_module.check_mode = True
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        existing_export = Mock()
        existing_export.name = "acme/fb-01"

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing_export]
        mock_blade.get_object_store_account_exports.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        mock_blade.delete_object_store_account_exports.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_s3acc_export.LooseVersion")
    @patch("plugins.modules.purefb_s3acc_export.get_system")
    @patch("plugins.modules.purefb_s3acc_export.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc_export.HAS_PYPURECLIENT", True)
    def test_main_delete_failure_calls_fail_json(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test SDK error on delete is surfaced via fail_json"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "policy": None,
            "enabled": None,
            "state": "absent",
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        existing_export = Mock()
        existing_export.name = "acme/fb-01"

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing_export]
        mock_blade.get_object_store_account_exports.return_value = get_response

        delete_response = Mock()
        delete_response.status_code = 400
        delete_err = Mock()
        delete_err.message = "nope"
        delete_response.errors = [delete_err]
        mock_blade.delete_object_store_account_exports.return_value = delete_response

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert (
            "Failed to delete account export"
            in mock_module.fail_json.call_args[1]["msg"]
        )

    @patch("plugins.modules.purefb_s3acc_export.LooseVersion")
    @patch("plugins.modules.purefb_s3acc_export.get_system")
    @patch("plugins.modules.purefb_s3acc_export.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc_export.HAS_PYPURECLIENT", True)
    def test_main_delete_uses_array_name_and_context(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Delete sends the name the array reports (server::account) and the
        fleet context when the array is a fleet member"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "policy": None,
            "enabled": None,
            "state": "absent",
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.30"]
        mock_blade.get_fleets.return_value.status_code = 200
        mock_blade.get_fleets.return_value.items = [Mock()]
        local_array = Mock()
        local_array.name = "fb-a"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        existing_export = Mock()
        existing_export.name = "fb-01::acme"

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing_export]
        mock_blade.get_object_store_account_exports.return_value = get_response

        delete_response = Mock()
        delete_response.status_code = 200
        mock_blade.delete_object_store_account_exports.return_value = delete_response

        try:
            main()
        except SystemExit:
            pass

        mock_blade.delete_object_store_account_exports.assert_called_once_with(
            names=["fb-01::acme"], context_names=["fb-a"]
        )
        mock_module.fail_json.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch(
        "plugins.modules.purefb_s3acc_export.get_error_message",
        return_value="Unknown attribute.",
    )
    @patch("plugins.modules.purefb_s3acc_export.LooseVersion")
    @patch("plugins.modules.purefb_s3acc_export.get_system")
    @patch("plugins.modules.purefb_s3acc_export.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc_export.HAS_PYPURECLIENT", True)
    def test_main_delete_fails_when_lookup_fails(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_error_message,
    ):
        """state=absent must not report ok when the export lookup itself failed"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "policy": None,
            "enabled": None,
            "state": "absent",
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.30"]
        mock_blade.get_fleets.return_value.status_code = 200
        mock_blade.get_fleets.return_value.items = []
        mock_get_system.return_value = mock_blade

        get_response = Mock()
        get_response.status_code = 400
        get_response.items = []
        mock_blade.get_object_store_account_exports.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        mock_blade.delete_object_store_account_exports.assert_not_called()
        mock_module.exit_json.assert_not_called()
        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "Failed to get account export" in msg
        assert "Unknown attribute." in msg

    @patch(
        "plugins.modules.purefb_s3acc_export.get_error_message",
        return_value="Export does not exist.",
    )
    @patch("plugins.modules.purefb_s3acc_export.LooseVersion")
    @patch("plugins.modules.purefb_s3acc_export.get_system")
    @patch("plugins.modules.purefb_s3acc_export.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc_export.HAS_PYPURECLIENT", True)
    def test_main_delete_failure_includes_array_error(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_error_message,
    ):
        """The array's own error text is part of the delete failure message"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "policy": None,
            "enabled": None,
            "state": "absent",
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.30"]
        mock_blade.get_fleets.return_value.status_code = 200
        mock_blade.get_fleets.return_value.items = []
        mock_get_system.return_value = mock_blade

        existing_export = Mock()
        existing_export.name = "fb-01::acme"

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing_export]
        mock_blade.get_object_store_account_exports.return_value = get_response

        delete_response = Mock()
        delete_response.status_code = 400
        mock_blade.delete_object_store_account_exports.return_value = delete_response

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "Failed to delete account export for account acme on server fb-01" in msg
        assert "Export does not exist." in msg

    # ---------------- main() context defaulting ----------------

    @patch("plugins.modules.purefb_s3acc_export.LooseVersion")
    @patch("plugins.modules.purefb_s3acc_export.get_system")
    @patch("plugins.modules.purefb_s3acc_export.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc_export.HAS_PYPURECLIENT", True)
    def test_main_standalone_array_sends_no_context(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """An array that is not in a fleet must not get a default context; the
        array rejects context_names with 'Cannot find array in fleet'."""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "policy": None,
            "enabled": None,
            "state": "absent",
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        mock_blade.get_fleets.return_value.status_code = 200
        mock_blade.get_fleets.return_value.items = []
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_object_store_account_exports.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        assert mock_module.params["context"] == ""
        mock_blade.get_object_store_account_exports.assert_called_once_with(
            filter="member.name='acme' and server.name='fb-01'"
        )

    @patch("plugins.modules.purefb_s3acc_export.LooseVersion")
    @patch("plugins.modules.purefb_s3acc_export.get_system")
    @patch("plugins.modules.purefb_s3acc_export.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc_export.HAS_PYPURECLIENT", True)
    def test_main_fleet_member_defaults_context_to_local_array(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "policy": None,
            "enabled": None,
            "state": "absent",
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        mock_blade.get_fleets.return_value.status_code = 200
        mock_blade.get_fleets.return_value.items = [Mock()]
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_object_store_account_exports.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        assert mock_module.params["context"] == "local-array"
        mock_blade.get_object_store_account_exports.assert_called_once_with(
            filter="member.name='acme' and server.name='fb-01'",
            context_names=["local-array"],
        )

    # ---------------- main() version gating ----------------

    @patch("plugins.modules.purefb_s3acc_export.LooseVersion")
    @patch("plugins.modules.purefb_s3acc_export.get_system")
    @patch("plugins.modules.purefb_s3acc_export.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc_export.HAS_PYPURECLIENT", True)
    def test_main_fails_when_api_version_too_old(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test failure when API version is too old"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "policy": None,
            "enabled": None,
            "state": "present",
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.10", "2.15", "2.19"]
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

    @patch("plugins.modules.purefb_s3acc_export.get_system")
    @patch("plugins.modules.purefb_s3acc_export.AnsibleModule")
    @patch(
        "plugins.modules.purefb_s3acc_export.PYPURECLIENT_IMPORT_ERROR",
        "Traceback (most recent call last):\n  ...\n"
        "ModuleNotFoundError: No module named 'pypureclient.flashblade'\n",
    )
    @patch("plugins.modules.purefb_s3acc_export.HAS_PYPURECLIENT", False)
    def test_main_fails_when_sdk_missing(self, mock_ansible_module, mock_get_system):
        """A missing or broken SDK fails before any array contact and the
        failure carries the import traceback"""
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "account": "acme",
            "server": "fb-01",
            "policy": None,
            "enabled": None,
            "state": "absent",
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        try:
            main()
        except SystemExit:
            pass

        mock_get_system.assert_not_called()
        mock_module.fail_json.assert_called_once()
        kwargs = mock_module.fail_json.call_args[1]
        assert "py-pure-client sdk is required" in kwargs["msg"]
        assert "No module named 'pypureclient.flashblade'" in kwargs["exception"]

    def test_import_guard_records_the_import_error(self):
        """When pypureclient.flashblade cannot be imported the module records
        the traceback instead of discarding it, and recovers once it can"""
        saved = sys.modules["pypureclient.flashblade"]
        # None in sys.modules makes the import raise ImportError
        sys.modules["pypureclient.flashblade"] = None
        try:
            importlib.reload(s3acc_export_module)
            assert s3acc_export_module.HAS_PYPURECLIENT is False
            err = s3acc_export_module.PYPURECLIENT_IMPORT_ERROR
            assert err.startswith("Traceback")
            assert "pypureclient.flashblade" in err
        finally:
            sys.modules["pypureclient.flashblade"] = saved
            importlib.reload(s3acc_export_module)
        assert s3acc_export_module.HAS_PYPURECLIENT is True
        assert s3acc_export_module.PYPURECLIENT_IMPORT_ERROR is None


# ---------------- realm scopes, check mode lookups, letter case ----------------

MODULE = "plugins.modules.purefb_s3acc_export"
CREATE_FAILED = (
    "Failed to create account export for account {0} on server {1}. Error: {2}"
)
UPDATE_FAILED = (
    "Failed to update account export for account {0} on server {1}. Error: {2}"
)
NO_ACCOUNT = "Object store account does not exist."
NO_SERVER = "Server does not exist."
NO_POLICY = "S3 export policy does not exist."
BUILT_IN_POLICY = "_s3_export_allow_everything"


def _as_dict(**kwargs):
    """Stand in for an SDK model: keep the keyword arguments it was built with."""
    return kwargs


def _error_message(res):
    """What get_error_message returns: the message of the first array error."""
    return res.errors[0].message


def _named(name):
    """A reference as the array returns it."""
    item = Mock()
    item.name = name
    return item


def _found(items=None):
    """A 200 answer of the array."""
    res = Mock()
    res.status_code = 200
    res.items = items if items is not None else []
    return res


def _refused(message, status_code=400):
    """An error answer of the array."""
    res = Mock()
    res.status_code = status_code
    res.errors = [Mock(message=message)]
    return res


def _export(account, server, policy, enabled=True):
    """An account export as the array returns it, named server::account."""
    export = Mock()
    export.name = "{0}::{1}".format(server, account)
    export.enabled = enabled
    export.member = _named(account)
    export.server = _named(server)
    export.policy = _named(policy)
    realm = account.rpartition("::")[0]
    export.realms = [_named(realm)] if realm else []
    return export


def _module(check_mode=False, **params):
    """An AnsibleModule double with the options of the module."""
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.check_mode = check_mode
    module.params = {
        "account": "acme",
        "server": "fb-01",
        "policy": None,
        "enabled": None,
        "state": "present",
        "context": "",
    }
    module.params.update(params)
    return module


def _blade(export=None):
    """A standalone array that holds the given export, or none."""
    blade = Mock()
    blade.get_fleets.return_value = _found([])
    blade.get_object_store_account_exports.return_value = _found(
        [export] if export else []
    )
    blade.get_object_store_accounts.return_value = _found()
    blade.get_servers.return_value = _found()
    blade.get_s3_export_policies.return_value = _found()
    blade.post_object_store_account_exports.return_value = _found()
    blade.patch_object_store_account_exports.return_value = _found()
    blade.delete_object_store_account_exports.return_value = _found()
    return blade


def _run(module, blade):
    """Run main() for the given task against the given array."""
    with ExitStack() as stack:
        stack.enter_context(patch(MODULE + ".AnsibleModule", return_value=module))
        stack.enter_context(patch(MODULE + ".get_system", return_value=blade))
        stack.enter_context(patch(MODULE + ".HAS_PYPURECLIENT", True))
        stack.enter_context(
            patch(MODULE + ".get_error_message", side_effect=_error_message)
        )
        for model in (
            "Reference",
            "ObjectStoreAccountExportPost",
            "ObjectStoreAccountExportPatch",
        ):
            stack.enter_context(patch(MODULE + "." + model, side_effect=_as_dict))
        loose_version = stack.enter_context(patch(MODULE + ".LooseVersion"))
        loose_version.return_value.__gt__ = Mock(return_value=False)
        try:
            main()
        except SystemExit:
            pass


def _lookups(blade):
    """The reads of the objects an export refers to."""
    return (
        blade.get_object_store_accounts,
        blade.get_servers,
        blade.get_s3_export_policies,
    )


class TestPurefbS3accExportRealm:
    """Exports of an account in a realm, and what check mode predicts"""

    # ---------------- helpers ----------------

    def test_realm_of(self):
        """The realm is the text before the last separator, empty without one"""
        realm_of = s3acc_export_module._realm_of
        assert realm_of("tenant1::acme") == "tenant1"
        assert realm_of("acme") == ""
        assert realm_of("_array_server") == ""
        assert realm_of(None) == ""

    def test_same_name(self):
        """Names are compared as the array matches them, without regard to case"""
        same_name = s3acc_export_module._same_name
        assert same_name("tenant1::acme-export", "TENANT1::Acme-Export")
        assert same_name("", None)
        assert not same_name("tenant1::acme-export", "acme-export")

    # ---------------- account and server in one scope ----------------

    def test_present_realm_account_on_array_server_is_refused(self):
        """An account in a realm is not exported on a server outside of it"""
        module = _module(
            account="tenant1::acme", server="fb-01", policy="tenant1::acme-export"
        )
        blade = _blade()

        _run(module, blade)

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "tenant1::acme is in realm tenant1" in msg
        assert "server fb-01 is not in a realm" in msg
        assert "tenant1::<server>" in msg
        blade.get_object_store_account_exports.assert_not_called()
        blade.post_object_store_account_exports.assert_not_called()
        module.exit_json.assert_not_called()

    def test_present_mixed_scopes_is_refused_in_check_mode(self):
        """Check mode does not report a create the array always refuses"""
        module = _module(
            check_mode=True,
            account="tenant1::acme",
            server="fb-01",
            policy="tenant1::acme-export",
        )
        blade = _blade()

        _run(module, blade)

        module.fail_json.assert_called_once()
        assert "same realm" in module.fail_json.call_args[1]["msg"]
        module.exit_json.assert_not_called()
        for lookup in _lookups(blade):
            lookup.assert_not_called()

    def test_present_array_account_on_realm_server_is_refused(self):
        """An account outside of any realm is not exported on a realm server"""
        module = _module(account="acme", server="tenant1::fb-01", policy="acme-export")
        blade = _blade()

        _run(module, blade)

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "account acme is not in a realm" in msg
        assert "server tenant1::fb-01 is in realm tenant1" in msg
        assert "tenant1::<account>" in msg
        blade.post_object_store_account_exports.assert_not_called()

    def test_present_account_and_server_of_two_realms_is_refused(self):
        """Two different realms are two different scopes"""
        module = _module(
            account="tenant1::acme",
            server="tenant2::fb-01",
            policy="tenant1::acme-export",
        )
        blade = _blade()

        _run(module, blade)

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "is in realm tenant1" in msg
        assert "is in realm tenant2" in msg
        assert "<server>" not in msg
        blade.post_object_store_account_exports.assert_not_called()

    def test_realm_in_another_letter_case_is_the_same_realm(self):
        """The array matches the realm of a name without regard to case"""
        export = _export("tenant1::acme", "tenant1::fb-01", "tenant1::acme-export")
        module = _module(account="TENANT1::acme", server="tenant1::fb-01")
        blade = _blade(export)

        _run(module, blade)

        module.fail_json.assert_not_called()
        blade.get_object_store_account_exports.assert_called_once_with(
            filter="member.name='TENANT1::acme' and server.name='tenant1::fb-01'"
        )
        assert module.exit_json.call_args[1]["changed"] is False

    def test_absent_with_mixed_scopes_reports_no_change(self):
        """An export that cannot exist is absent"""
        module = _module(account="tenant1::acme", server="fb-01", state="absent")
        blade = _blade()

        _run(module, blade)

        module.fail_json.assert_not_called()
        blade.delete_object_store_account_exports.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    # ---------------- one account, one server, one policy ----------------

    def test_present_list_of_accounts_is_refused(self):
        """The array reads a comma as the separator of a list of names and
        does not export more than one account at a time"""
        module = _module(account="acme,beta", policy="acme-export")
        blade = _blade()

        _run(module, blade)

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert msg.startswith("account acme,beta is not valid")
        assert "one object store account" in msg
        blade.get_object_store_account_exports.assert_not_called()
        blade.post_object_store_account_exports.assert_not_called()
        module.exit_json.assert_not_called()

    def test_present_list_of_servers_is_refused_in_check_mode(self):
        """Check mode does not look up a list of names, which the array finds"""
        module = _module(check_mode=True, server="fb-01,fb-02", policy="acme-export")
        blade = _blade()

        _run(module, blade)

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert msg.startswith("server fb-01,fb-02 is not valid")
        assert "one server" in msg
        for lookup in _lookups(blade):
            lookup.assert_not_called()
        module.exit_json.assert_not_called()

    def test_present_list_of_policies_is_refused(self):
        """An existing export is not re-pointed at a list of policies"""
        export = _export("acme", "fb-01", "acme-export")
        module = _module(policy="acme-export-v2,acme-export")
        blade = _blade(export)

        _run(module, blade)

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert msg.startswith("policy acme-export-v2,acme-export is not valid")
        assert "one S3 export policy" in msg
        blade.patch_object_store_account_exports.assert_not_called()
        module.exit_json.assert_not_called()

    def test_present_empty_server_is_refused(self):
        """An export is never asked for without a server"""
        module = _module(server=" ", policy="acme-export")
        blade = _blade()

        _run(module, blade)

        module.fail_json.assert_called_once_with(msg="server cannot be empty.")
        blade.get_object_store_account_exports.assert_not_called()
        blade.post_object_store_account_exports.assert_not_called()
        module.exit_json.assert_not_called()

    def test_present_empty_account_is_refused_in_check_mode(self):
        """An export is never asked for without an account"""
        module = _module(check_mode=True, account="", policy="acme-export")
        blade = _blade()

        _run(module, blade)

        module.fail_json.assert_called_once_with(msg="account cannot be empty.")
        for lookup in _lookups(blade):
            lookup.assert_not_called()
        module.exit_json.assert_not_called()

    def test_present_blank_policy_is_refused(self):
        """A policy of blanks is not a policy"""
        export = _export("acme", "fb-01", "acme-export")
        module = _module(policy="  ")
        blade = _blade(export)

        _run(module, blade)

        module.fail_json.assert_called_once_with(msg="policy cannot be empty.")
        blade.patch_object_store_account_exports.assert_not_called()

    def test_present_without_policy_keeps_the_policy_of_the_export(self):
        """No policy, or an empty one, leaves the policy of the export alone"""
        export = _export("acme", "fb-01", "acme-export")
        for policy in (None, ""):
            module = _module(policy=policy, enabled=True)
            blade = _blade(export)

            _run(module, blade)

            module.fail_json.assert_not_called()
            blade.patch_object_store_account_exports.assert_not_called()
            assert module.exit_json.call_args[1]["changed"] is False

    def test_absent_takes_any_name_to_the_lookup(self):
        """state=absent sends no name in a write: the lookup answers"""
        module = _module(account="acme,beta", server="", state="absent")
        blade = _blade()

        _run(module, blade)

        module.fail_json.assert_not_called()
        blade.get_object_store_account_exports.assert_called_once_with(
            filter="member.name='acme,beta' and server.name=''"
        )
        assert module.exit_json.call_args[1]["changed"] is False

    # ---------------- exports in a realm ----------------

    def test_create_realm_export_sends_the_qualified_names(self):
        """A real run creates the export with the names of the task and
        leaves every answer to the array: nothing is looked up first"""
        module = _module(
            account="tenant1::acme",
            server="tenant1::fb-01",
            policy="tenant1::acme-export",
        )
        blade = _blade()

        _run(module, blade)

        blade.get_object_store_account_exports.assert_called_once_with(
            filter="member.name='tenant1::acme' and server.name='tenant1::fb-01'"
        )
        blade.post_object_store_account_exports.assert_called_once_with(
            member_names=["tenant1::acme"],
            policy_names=["tenant1::acme-export"],
            object_store_account_export={"server": {"name": "tenant1::fb-01"}},
        )
        for lookup in _lookups(blade):
            lookup.assert_not_called()
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_realm_export_with_the_built_in_policy(self):
        """The built-in policy is not in a realm and serves a realm export:
        the scope of the policy is left to the array"""
        module = _module(
            account="tenant1::acme", server="tenant1::fb-01", policy=BUILT_IN_POLICY
        )
        blade = _blade()

        _run(module, blade)

        module.fail_json.assert_not_called()
        kwargs = blade.post_object_store_account_exports.call_args[1]
        assert kwargs["policy_names"] == [BUILT_IN_POLICY]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_realm_export_uses_the_name_of_the_array(self):
        """The export is deleted by the name the array gave it"""
        export = _export("tenant1::acme", "tenant1::fb-01", "tenant1::acme-export")
        module = _module(
            account="tenant1::acme", server="tenant1::fb-01", state="absent"
        )
        blade = _blade(export)

        _run(module, blade)

        blade.delete_object_store_account_exports.assert_called_once_with(
            names=["tenant1::fb-01::tenant1::acme"]
        )
        assert module.exit_json.call_args[1]["changed"] is True

    # ---------------- check mode, new export ----------------

    def test_check_mode_create_looks_up_account_server_and_policy(self):
        """Check mode reads what the new export refers to and sends nothing"""
        module = _module(
            check_mode=True,
            account="tenant1::acme",
            server="tenant1::fb-01",
            policy="tenant1::acme-export",
        )
        blade = _blade()

        _run(module, blade)

        blade.get_object_store_accounts.assert_called_once_with(names=["tenant1::acme"])
        blade.get_servers.assert_called_once_with(names=["tenant1::fb-01"])
        blade.get_s3_export_policies.assert_called_once_with(
            names=["tenant1::acme-export"]
        )
        blade.post_object_store_account_exports.assert_not_called()
        module.fail_json.assert_not_called()
        module.warn.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_check_mode_create_lookups_carry_the_context(self):
        """The lookups are made on the fleet member the task names"""
        module = _module(check_mode=True, policy="acme-export", context="fb-2")
        blade = _blade()

        _run(module, blade)

        for lookup, name in zip(_lookups(blade), ("acme", "fb-01", "acme-export")):
            lookup.assert_called_once_with(names=[name], context_names=["fb-2"])
        assert module.exit_json.call_args[1]["changed"] is True

    def test_check_mode_create_fails_for_a_missing_account(self):
        """Check mode fails as the real run does, with the same message"""
        module = _module(check_mode=True, policy="acme-export")
        blade = _blade()
        blade.get_object_store_accounts.return_value = _refused(NO_ACCOUNT)

        _run(module, blade)

        module.fail_json.assert_called_once_with(
            msg=CREATE_FAILED.format("acme", "fb-01", NO_ACCOUNT)
        )
        blade.get_servers.assert_not_called()
        blade.post_object_store_account_exports.assert_not_called()
        module.exit_json.assert_not_called()

    def test_check_mode_create_fails_for_a_realm_that_does_not_exist(self):
        """The array does not find an account in a realm that does not exist"""
        module = _module(
            check_mode=True,
            account="nowhere::acme",
            server="nowhere::fb-01",
            policy="nowhere::acme-export",
        )
        blade = _blade()
        blade.get_object_store_accounts.return_value = _refused(NO_ACCOUNT)

        _run(module, blade)

        module.fail_json.assert_called_once_with(
            msg=CREATE_FAILED.format("nowhere::acme", "nowhere::fb-01", NO_ACCOUNT)
        )
        module.exit_json.assert_not_called()

    def test_check_mode_create_fails_for_a_missing_server(self):
        """A server the array does not find fails the check mode run"""
        module = _module(check_mode=True, policy="acme-export")
        blade = _blade()
        blade.get_servers.return_value = _refused(NO_SERVER)

        _run(module, blade)

        module.fail_json.assert_called_once_with(
            msg=CREATE_FAILED.format("acme", "fb-01", NO_SERVER)
        )
        blade.get_s3_export_policies.assert_not_called()
        module.exit_json.assert_not_called()

    def test_check_mode_create_fails_for_a_missing_policy(self):
        """A policy the array does not find fails the check mode run"""
        module = _module(
            check_mode=True,
            account="tenant1::acme",
            server="tenant1::fb-01",
            policy="acme-export",
        )
        blade = _blade()
        blade.get_s3_export_policies.return_value = _refused(NO_POLICY)

        _run(module, blade)

        module.fail_json.assert_called_once_with(
            msg=CREATE_FAILED.format("tenant1::acme", "tenant1::fb-01", NO_POLICY)
        )
        module.exit_json.assert_not_called()

    def test_check_mode_create_warns_when_a_lookup_is_refused(self):
        """Only a definite answer fails the task: a refused read is reported
        as a warning and the prediction stands"""
        refusal = (
            "Operation not permitted. Authorization for 'read' on 'servers' "
            "is required."
        )
        module = _module(check_mode=True, policy="acme-export")
        blade = _blade()
        blade.get_servers.return_value = _refused(refusal, status_code=403)

        _run(module, blade)

        module.fail_json.assert_not_called()
        module.warn.assert_called_once()
        warning = module.warn.call_args[0][0]
        assert "server fb-01" in warning
        assert refusal in warning
        blade.get_s3_export_policies.assert_called_once_with(names=["acme-export"])
        assert module.exit_json.call_args[1]["changed"] is True

    # ---------------- existing export ----------------

    def test_update_policy_in_another_letter_case_is_unchanged(self):
        """The array returns the stored spelling of the policy: another
        letter case in the task is not a change"""
        export = _export("acme", "fb-01", "acme-export")
        module = _module(policy="ACME-Export", enabled=True)
        blade = _blade(export)

        _run(module, blade)

        blade.patch_object_store_account_exports.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_realm_policy_in_another_letter_case_is_unchanged(self):
        """The same holds for the realm of the policy"""
        export = _export("tenant1::acme", "tenant1::fb-01", "tenant1::acme-export")
        module = _module(
            account="tenant1::acme",
            server="tenant1::fb-01",
            policy="TENANT1::Acme-Export",
        )
        blade = _blade(export)

        _run(module, blade)

        blade.patch_object_store_account_exports.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_repoints_a_realm_export(self):
        """A real run re-points the export and looks nothing up first"""
        export = _export("tenant1::acme", "tenant1::fb-01", "tenant1::acme-export")
        module = _module(
            account="tenant1::acme", server="tenant1::fb-01", policy=BUILT_IN_POLICY
        )
        blade = _blade(export)

        _run(module, blade)

        blade.patch_object_store_account_exports.assert_called_once_with(
            names=["tenant1::fb-01::tenant1::acme"],
            object_store_account_export={"policy": {"name": BUILT_IN_POLICY}},
        )
        blade.get_s3_export_policies.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_check_mode_repoint_looks_up_the_policy(self):
        """Check mode reads the policy an export is re-pointed at"""
        export = _export("tenant1::acme", "tenant1::fb-01", BUILT_IN_POLICY)
        module = _module(
            check_mode=True,
            account="tenant1::acme",
            server="tenant1::fb-01",
            policy="tenant1::acme-export",
        )
        blade = _blade(export)

        _run(module, blade)

        blade.get_s3_export_policies.assert_called_once_with(
            names=["tenant1::acme-export"]
        )
        blade.get_object_store_accounts.assert_not_called()
        blade.get_servers.assert_not_called()
        blade.patch_object_store_account_exports.assert_not_called()
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_check_mode_repoint_fails_for_a_missing_policy(self):
        """Check mode fails as the real run does, with the same message"""
        export = _export("tenant1::acme", "tenant1::fb-01", "tenant1::acme-export")
        module = _module(
            check_mode=True,
            account="tenant1::acme",
            server="tenant1::fb-01",
            policy="acme-export-v2",
        )
        blade = _blade(export)
        blade.get_s3_export_policies.return_value = _refused(NO_POLICY)

        _run(module, blade)

        module.fail_json.assert_called_once_with(
            msg=UPDATE_FAILED.format("tenant1::acme", "tenant1::fb-01", NO_POLICY)
        )
        blade.patch_object_store_account_exports.assert_not_called()
        module.exit_json.assert_not_called()

    def test_check_mode_enabled_change_looks_nothing_up(self):
        """A change that names no other object needs no lookup"""
        export = _export("acme", "fb-01", "acme-export")
        module = _module(check_mode=True, enabled=False)
        blade = _blade(export)

        _run(module, blade)

        for lookup in _lookups(blade):
            lookup.assert_not_called()
        blade.patch_object_store_account_exports.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True
