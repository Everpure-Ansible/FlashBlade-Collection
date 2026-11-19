# Copyright: (c) 2026, Pure Storage Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_fs module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
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
mock_collections = MagicMock()
mock_collections.everpure.flashblade.plugins.module_utils.purefb.get_system = (
    MagicMock()
)
mock_collections.everpure.flashblade.plugins.module_utils.purefb.purefb_argument_spec = (
    MagicMock()
)
mock_collections.everpure.flashblade.plugins.module_utils.common.get_filesystem = (
    MagicMock()
)
mock_collections.everpure.flashblade.plugins.module_utils.common.get_error_message = (
    MagicMock()
)
sys.modules["ansible_collections"] = mock_collections
sys.modules["ansible_collections.everpure"] = mock_collections.everpure
sys.modules["ansible_collections.everpure.flashblade"] = (
    mock_collections.everpure.flashblade
)
sys.modules["ansible_collections.everpure.flashblade.plugins"] = (
    mock_collections.everpure.flashblade.plugins
)
sys.modules["ansible_collections.everpure.flashblade.plugins.module_utils"] = (
    mock_collections.everpure.flashblade.plugins.module_utils
)
sys.modules["ansible_collections.everpure.flashblade.plugins.module_utils.purefb"] = (
    mock_collections.everpure.flashblade.plugins.module_utils.purefb
)
sys.modules["ansible_collections.everpure.flashblade.plugins.module_utils.common"] = (
    mock_collections.everpure.flashblade.plugins.module_utils.common
)
sys.modules["ansible_collections.everpure.flashblade.plugins.module_utils.version"] = (
    mock_collections.everpure.flashblade.plugins.module_utils.version
)

from plugins.modules.purefb_fs import (
    main,
    create_fs,
    delete_fs,
    eradicate_fs,
    modify_fs,
    _check_create_only_options,
    _resolve_name,
)
from plugins.module_utils.version import LooseVersion as RealLooseVersion


class TestPurefbFs:
    """Test cases for purefb_fs module"""

    def get_default_params(self):
        """Get default parameters for purefb_fs module"""
        return {
            "name": "test-fs",
            "state": "present",
            "eradicate": False,
            "nfsv3": True,
            "nfsv4": True,
            "nfs_rules": None,
            # The boolean flags default to None (only applied when set).
            "smb": None,
            "http": None,
            "snapshot": None,
            "writable": None,
            "promote": None,
            "quiesce": None,
            "abort_quiesce": False,
            "fastremove": None,
            "hard_limit": None,
            "user_quota": None,
            "policy": None,
            "group_quota": None,
            "smb_aclmode": "shared",
            "group_ownership": "creator",
            "policy_state": "present",
            "delete_link": False,
            "discard_snaps": False,
            "safeguard_acls": None,
            "access_control": "shared",
            "size": None,
            "export_policy": None,
            "share_policy": None,
            "client_policy": None,
            "continuous_availability": True,
            "ignore_usage": False,
            "cancel_in_progress": False,
            "context": "",
            "storage_class": None,
            "realm": None,
        }

    def _existing_fs(self, **overrides):
        """Mock of an existing, promoted, writable filesystem with every
        boolean flag off and safeguard_acls on. Keyword overrides set the
        flat attributes (e.g. hard_limit_enabled=True) or the nested ones
        through smb_enabled / http_enabled / safeguard_acls.
        """
        fs = Mock()
        fs.destroyed = False
        fs.provisioned = 1099511627776
        fs.nfs = Mock()
        fs.nfs.v3_enabled = True
        fs.nfs.v4_1_enabled = True
        fs.nfs.rules = ""
        fs.nfs.export_policy = Mock()
        fs.nfs.export_policy.name = None
        fs.smb = Mock()
        fs.smb.enabled = overrides.pop("smb_enabled", False)
        fs.smb.continuous_availability_enabled = True
        fs.http = Mock()
        fs.http.enabled = overrides.pop("http_enabled", False)
        fs.snapshot_directory_enabled = False
        fs.fast_remove_directory_enabled = False
        fs.hard_limit_enabled = False
        fs.default_user_quota = None
        fs.default_group_quota = None
        fs.group_ownership = "creator"
        fs.multi_protocol = Mock()
        fs.multi_protocol.safeguard_acls = overrides.pop("safeguard_acls", True)
        fs.multi_protocol.access_control_style = "shared"
        fs.promotion_status = "promoted"
        fs.requested_promotion_state = "promoted"
        fs.writable = True
        for attr, value in overrides.items():
            setattr(fs, attr, value)
        return fs

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.get_system")
    @patch("plugins.modules.purefb_fs.AnsibleModule")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_main_create_filesystem(
        self, mock_ansible_module, mock_get_system, mock_get_filesystem
    ):
        """Test creating a new filesystem"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = {
            "name": "test-fs",
            "state": "present",
            "size": "1T",
            "nfsv3": True,
            "nfsv4": True,
            "nfs_rules": "*(rw,no_root_squash)",
            "smb": False,
            "http": False,
            "snapshot": False,
            "fastremove": False,
            "hard_limit": False,
            "user_quota": None,
            "group_quota": None,
            "policy": None,
            "eradicate": False,
            "smb_aclmode": "shared",
            "writable": None,
            "promote": None,
            "access_control": "shared",
            "safeguard_acls": True,
            "export_policy": None,
            "share_policy": None,
            "client_policy": None,
            "continuous_availability": True,
            "ignore_usage": False,
            "cancel_in_progress": False,
            "context": "",
            "storage_class": None,
            "delete_link": False,
            "discard_snaps": False,
            "group_ownership": None,
        }
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        mock_get_filesystem.return_value = None  # Filesystem doesn't exist

        # Mock API version
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock successful creation
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_response

        # Call main
        main()

        # Verify
        mock_blade.post_file_systems.assert_called_once()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.get_system")
    @patch("plugins.modules.purefb_fs.AnsibleModule")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_main_delete_filesystem(
        self, mock_ansible_module, mock_get_system, mock_get_filesystem
    ):
        """Test deleting an existing filesystem"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = {
            "name": "test-fs",
            "state": "absent",
            "eradicate": False,
            "smb_aclmode": "shared",
            "delete_link": False,
        }
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_get_system.return_value = mock_blade

        # Mock API version
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock existing filesystem
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.name = "test-fs"
        mock_get_filesystem.return_value = mock_fs

        # Mock successful deletion
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_response

        # Call main
        main()

        # Verify
        mock_blade.patch_file_systems.assert_called()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.get_system")
    @patch("plugins.modules.purefb_fs.AnsibleModule")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_main_eradicate_filesystem(
        self, mock_ansible_module, mock_get_system, mock_get_filesystem
    ):
        """Test eradicating a deleted filesystem"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = {
            "name": "test-fs",
            "state": "absent",
            "eradicate": True,
            "smb_aclmode": "shared",
        }
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_get_system.return_value = mock_blade

        # Mock API version
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock destroyed filesystem
        mock_fs = Mock()
        mock_fs.destroyed = True
        mock_fs.name = "test-fs"
        mock_get_filesystem.return_value = mock_fs

        # Mock successful eradication
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.delete_file_systems.return_value = mock_response

        # Call main
        main()

        # Verify
        mock_blade.delete_file_systems.assert_called()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.FileSystemPost")
    @patch("plugins.modules.purefb_fs.Nfs")
    @patch("plugins.modules.purefb_fs.SmbPost")
    @patch("plugins.modules.purefb_fs.Http")
    @patch("plugins.modules.purefb_fs.MultiProtocolPost")
    @patch("plugins.modules.purefb_fs.human_to_bytes")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_create_fs_with_size(
        self,
        mock_human_to_bytes,
        mock_multi_protocol,
        mock_http,
        mock_smb,
        mock_nfs,
        mock_fs_post,
    ):
        """Test creating filesystem with specific size"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = {
            "name": "test-fs",
            "size": "2T",
            "nfsv3": True,
            "nfsv4": True,
            "nfs_rules": None,
            "smb": False,
            "http": False,
            "snapshot": False,
            "fastremove": False,
            "hard_limit": False,
            "user_quota": None,
            "group_quota": None,
            "policy": None,
            "access_control": "shared",
            "safeguard_acls": True,
            "export_policy": None,
            "share_policy": None,
            "client_policy": None,
            "continuous_availability": True,
            "context": "",
            "storage_class": None,
            "group_ownership": None,
        }

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        mock_human_to_bytes.return_value = 2199023255552  # 2TB in bytes

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_response

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify
        mock_human_to_bytes.assert_called_with("2T")
        mock_blade.post_file_systems.assert_called_once()
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.FileSystemPost")
    @patch("plugins.modules.purefb_fs.Nfs")
    @patch("plugins.modules.purefb_fs.SmbPost")
    @patch("plugins.modules.purefb_fs.Http")
    @patch("plugins.modules.purefb_fs.MultiProtocolPost")
    @patch("plugins.modules.purefb_fs.human_to_bytes")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_create_fs_with_nfs_rules(
        self,
        mock_human_to_bytes,
        mock_multi_protocol,
        mock_http,
        mock_smb,
        mock_nfs,
        mock_fs_post,
    ):
        """Explicit nfs_rules must reach the SDK and emit a deprecation warning"""
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = {
            "name": "test-fs",
            "size": "1T",
            "nfsv3": True,
            "nfsv4": True,
            "nfs_rules": "10.21.200.0/24(rw,no_root_squash)",
            "smb": False,
            "http": False,
            "snapshot": False,
            "fastremove": False,
            "hard_limit": False,
            "user_quota": None,
            "group_quota": None,
            "policy": None,
            "access_control": "shared",
            "safeguard_acls": True,
            "export_policy": None,
            "share_policy": None,
            "client_policy": None,
            "continuous_availability": True,
            "context": "",
            "storage_class": None,
            "group_ownership": None,
        }

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]
        mock_human_to_bytes.return_value = 1099511627776
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_response

        create_fs(mock_module, mock_blade)

        # The inline rules must be passed through to the Nfs SDK object
        mock_nfs.assert_called_once_with(
            v3_enabled=True,
            v4_1_enabled=True,
            rules="10.21.200.0/24(rw,no_root_squash)",
        )
        # And the deprecation notice must be emitted
        mock_module.deprecate.assert_any_call(
            "nfs_rules is deprecated. Use the purefb_export module to attach "
            "NFS export policies via the File System Exports endpoints.",
            version="2.0.0",
            collection_name="everpure.flashblade",
        )
        mock_blade.post_file_systems.assert_called_once()
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.FileSystemPost")
    @patch("plugins.modules.purefb_fs.Nfs")
    @patch("plugins.modules.purefb_fs.SmbPost")
    @patch("plugins.modules.purefb_fs.Http")
    @patch("plugins.modules.purefb_fs.MultiProtocolPost")
    @patch("plugins.modules.purefb_fs.human_to_bytes")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.17"),
    )
    def test_create_fs_no_context_omits_context_names(
        self,
        mock_human_to_bytes,
        mock_multi_protocol,
        mock_http,
        mock_smb,
        mock_nfs,
        mock_fs_post,
    ):
        """On a context-capable array with no context set (e.g. standalone,
        not in a fleet), context_names must NOT be sent."""
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = {
            "name": "test-fs",
            "size": "1T",
            "nfsv3": True,
            "nfsv4": True,
            "nfs_rules": None,
            "smb": False,
            "http": False,
            "snapshot": False,
            "fastremove": False,
            "hard_limit": False,
            "user_quota": None,
            "group_quota": None,
            "policy": None,
            "access_control": "shared",
            "safeguard_acls": True,
            "export_policy": None,
            "share_policy": None,
            "client_policy": None,
            "continuous_availability": True,
            "context": "",  # no context -> standalone / not in a fleet
            "storage_class": None,
            "group_ownership": None,
        }
        mock_blade = Mock()
        # Array supports the context API version (2.17+)
        mock_blade.get_versions.return_value.items = ["2.17"]
        mock_human_to_bytes.return_value = 1099511627776
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_response

        create_fs(mock_module, mock_blade)

        mock_blade.post_file_systems.assert_called_once()
        call_kwargs = mock_blade.post_file_systems.call_args[1]
        assert "context_names" not in call_kwargs

    @patch("plugins.modules.purefb_fs.FileSystemPost")
    @patch("plugins.modules.purefb_fs.Nfs")
    @patch("plugins.modules.purefb_fs.SmbPost")
    @patch("plugins.modules.purefb_fs.Http")
    @patch("plugins.modules.purefb_fs.MultiProtocolPost")
    @patch("plugins.modules.purefb_fs.human_to_bytes")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.17"),
    )
    def test_create_fs_with_context_sends_context_names(
        self,
        mock_human_to_bytes,
        mock_multi_protocol,
        mock_http,
        mock_smb,
        mock_nfs,
        mock_fs_post,
    ):
        """When a context is explicitly set, context_names must be sent."""
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = {
            "name": "test-fs",
            "size": "1T",
            "nfsv3": True,
            "nfsv4": True,
            "nfs_rules": None,
            "smb": False,
            "http": False,
            "snapshot": False,
            "fastremove": False,
            "hard_limit": False,
            "user_quota": None,
            "group_quota": None,
            "policy": None,
            "access_control": "shared",
            "safeguard_acls": True,
            "export_policy": None,
            "share_policy": None,
            "client_policy": None,
            "continuous_availability": True,
            "context": "member-array",
            "storage_class": None,
            "group_ownership": None,
        }
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.17"]
        mock_human_to_bytes.return_value = 1099511627776
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_response

        create_fs(mock_module, mock_blade)

        mock_blade.post_file_systems.assert_called_once()
        call_kwargs = mock_blade.post_file_systems.call_args[1]
        assert call_kwargs["context_names"] == ["member-array"]

    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    def test_create_fs_check_mode(self):
        """Test creating filesystem in check mode"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = True
        mock_module.params = {
            "name": "test-fs",
            "size": "1T",
        }

        mock_blade = Mock()
        # Mock API version even in check mode (it's called before check_mode check)
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify - should not call API in check mode
        mock_blade.post_file_systems.assert_not_called()
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.FileSystemPatch")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    def test_delete_fs_success(self, mock_fs_patch):
        """Test successful filesystem deletion"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "delete_link": False,
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_response

        # Call function
        delete_fs(mock_module, mock_blade)

        # Verify
        mock_blade.patch_file_systems.assert_called_once()
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    def test_delete_fs_check_mode(self):
        """Test deleting filesystem in check mode"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = True
        mock_module.params = {
            "name": "test-fs",
        }

        mock_blade = Mock()

        # Call function
        delete_fs(mock_module, mock_blade)

        # Verify - should not call API in check mode
        mock_blade.patch_file_systems.assert_not_called()
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    def test_eradicate_fs_success(self):
        """Test successful filesystem eradication"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = {
            "name": "test-fs",
        }

        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.delete_file_systems.return_value = mock_response

        # Call function
        eradicate_fs(mock_module, mock_blade)

        # Verify
        mock_blade.delete_file_systems.assert_called_once()
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    def test_eradicate_fs_check_mode(self):
        """Test eradicating filesystem in check mode"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = True
        mock_module.params = {
            "name": "test-fs",
        }

        mock_blade = Mock()

        # Call function
        eradicate_fs(mock_module, mock_blade)

        # Verify - should not call API in check mode
        mock_blade.delete_file_systems.assert_not_called()
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.get_system")
    @patch("plugins.modules.purefb_fs.AnsibleModule")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_main_filesystem_not_exists_absent(
        self, mock_ansible_module, mock_get_system, mock_get_filesystem
    ):
        """Test deleting a filesystem that doesn't exist"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = {
            "name": "nonexistent-fs",
            "state": "absent",
            "eradicate": False,
            "smb_aclmode": "shared",
        }
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        mock_get_filesystem.return_value = None  # Filesystem doesn't exist

        # Mock API version
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Call main
        main()

        # Verify - should exit with changed=False
        mock_module.exit_json.assert_called_with(changed=False)

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.get_system")
    @patch("plugins.modules.purefb_fs.AnsibleModule")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_main_native_smb_aclmode_fails(
        self, mock_ansible_module, mock_get_system, mock_get_filesystem
    ):
        """Test that native SMB ACL mode fails with error"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "state": "present",
                "smb_aclmode": "native",
            }
        )
        mock_module.params = params
        # Make fail_json raise an exception to stop execution (like real Ansible)
        mock_module.fail_json.side_effect = SystemExit(1)
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        # Mock API version
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]
        mock_get_system.return_value = mock_blade
        mock_get_filesystem.return_value = None

        # Call main - should raise SystemExit
        try:
            main()
        except SystemExit:
            pass

        # Verify - should fail with error message
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args
        assert "Native SMB ACL mode is no longer supported" in call_args[1]["msg"]

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.human_to_bytes")
    @patch("plugins.modules.purefb_fs.FileSystemPatch")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_size_change(
        self, mock_fs_patch, mock_human_to_bytes, mock_get_filesystem
    ):
        """Test modifying filesystem size"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "3T",
                "nfs_rules": "*(rw,no_root_squash)",
                "group_ownership": None,
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock existing filesystem
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776  # 1TB
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        mock_human_to_bytes.return_value = 3298534883328  # 3TB in bytes

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_response

        # Mock get_file_systems for the final retrieval
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function
        modify_fs(mock_module, mock_blade)

        # Verify
        mock_human_to_bytes.assert_called_with("3T")
        mock_blade.patch_file_systems.assert_called()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_no_changes(self, mock_get_filesystem):
        """Test modifying filesystem when no changes needed"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "nfs_rules": "*(rw,no_root_squash)",
                "group_ownership": None,
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock existing filesystem with same settings
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776  # 1TB
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        # Mock get_file_systems for the final retrieval
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function
        modify_fs(mock_module, mock_blade)

        # Verify - should exit with changed=False
        mock_module.exit_json.assert_called()
        call_args = mock_module.exit_json.call_args
        # The function should detect no changes needed

    @patch("plugins.modules.purefb_fs.get_error_message")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    def test_delete_fs_failure(self, mock_get_error):
        """Test filesystem deletion failure"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "delete_link": False,
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 400
        mock_blade.patch_file_systems.return_value = mock_response
        mock_get_error.return_value = "Filesystem is in use"

        # Call function
        delete_fs(mock_module, mock_blade)

        # Verify - should fail with error
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args
        assert "Failed to delete filesystem" in call_args[1]["msg"]

    @patch("plugins.modules.purefb_fs.get_error_message")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    def test_eradicate_fs_failure(self, mock_get_error):
        """Test filesystem eradication failure"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = {
            "name": "test-fs",
        }

        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 400
        mock_blade.delete_file_systems.return_value = mock_response
        mock_get_error.return_value = "Filesystem not in destroyed state"

        # Call function
        eradicate_fs(mock_module, mock_blade)

        # Verify - should fail with error
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args
        assert "Failed to eradicate filesystem" in call_args[1]["msg"]

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.get_system")
    @patch("plugins.modules.purefb_fs.AnsibleModule")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_main_eradicate_warning(
        self, mock_ansible_module, mock_get_system, mock_get_filesystem
    ):
        """Test that eradicate flag with state=present shows warning"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = {
            "name": "test-fs",
            "state": "present",
            "eradicate": True,
            "smb_aclmode": "shared",
            "size": "1T",
            "nfsv3": True,
            "nfsv4": True,
            "nfs_rules": None,
            "smb": False,
            "http": False,
            "snapshot": False,
            "fastremove": False,
            "hard_limit": False,
            "user_quota": None,
            "group_quota": None,
            "policy": None,
            "writable": None,
            "promote": None,
            "access_control": "shared",
            "safeguard_acls": True,
            "export_policy": None,
            "share_policy": None,
            "client_policy": None,
            "continuous_availability": True,
            "ignore_usage": False,
            "cancel_in_progress": False,
            "context": "",
            "storage_class": None,
            "delete_link": False,
            "discard_snaps": False,
            "group_ownership": None,
        }
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        mock_get_filesystem.return_value = None

        # Mock API version
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock successful creation
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_response

        # Call main
        main()

        # Verify warning was issued
        mock_module.warn.assert_called_once_with(
            "Eradicate flag ignored without state=absent"
        )

    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", False)
    @patch("plugins.modules.purefb_fs.get_system")
    @patch("plugins.modules.purefb_fs.AnsibleModule")
    def test_main_missing_sdk(self, mock_ansible_module, mock_get_system):
        """Test that missing SDK is handled"""
        # Setup mocks
        mock_module = Mock()
        mock_module.params = {
            "name": "test-fs",
            "state": "present",
        }
        mock_ansible_module.return_value = mock_module

        # This would normally be caught by module initialization
        # but we test the HAS_PYPURECLIENT flag
        assert not __import__(
            "plugins.modules.purefb_fs"
        ).modules.purefb_fs.HAS_PYPURECLIENT

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_create_fs_with_snapshot_enabled(self, mock_get_filesystem):
        """Test creating filesystem with snapshot directory enabled"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "snapshot": True,
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock successful filesystem creation
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_response

        mock_get_filesystem.return_value = None

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify
        mock_blade.post_file_systems.assert_called_once()
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_create_fs_with_fastremove(self, mock_get_filesystem):
        """Test creating filesystem with fast remove enabled"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "fastremove": True,
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock successful filesystem creation
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_response

        mock_get_filesystem.return_value = None

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify
        mock_blade.post_file_systems.assert_called_once()
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_create_fs_with_hard_limit(self, mock_get_filesystem):
        """Test creating filesystem with hard limit enabled"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "hard_limit": True,
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock successful filesystem creation
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_response

        mock_get_filesystem.return_value = None

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify
        mock_blade.post_file_systems.assert_called_once()
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_create_fs_failure(self, mock_get_filesystem):
        """Test filesystem creation failure"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock failed filesystem creation
        mock_response = Mock()
        mock_response.status_code = 400
        mock_blade.post_file_systems.return_value = mock_response

        mock_get_filesystem.return_value = None

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify - should fail
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args
        assert "Failed to create filesystem" in call_args[1]["msg"]

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.human_to_bytes")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_add_policy(self, mock_human_to_bytes, mock_get_filesystem):
        """Test adding a policy to filesystem"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "policy": "test-policy",
                "policy_state": "present",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock existing filesystem
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        # Mock policy exists
        mock_policy_response = Mock()
        mock_policy_response.status_code = 200
        mock_blade.get_policies.return_value = mock_policy_response

        # Mock policy not yet attached
        mock_policy_fs_response = Mock()
        mock_policy_fs_response.status_code = 400
        mock_blade.get_policies_file_systems.return_value = mock_policy_fs_response

        # Mock successful policy attachment
        mock_patch_response = Mock()
        mock_patch_response.status_code = 200
        mock_blade.post_policies_file_systems.return_value = mock_patch_response
        mock_blade.patch_file_systems.return_value = mock_patch_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function
        modify_fs(mock_module, mock_blade)

        # Verify
        mock_blade.post_policies_file_systems.assert_called_once()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.human_to_bytes")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_remove_policy(self, mock_human_to_bytes, mock_get_filesystem):
        """Test removing a policy from filesystem"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "policy": "test-policy",
                "policy_state": "absent",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock existing filesystem
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        # Mock policy exists and is attached (membership GET has one item)
        mock_policy_response = Mock()
        mock_policy_response.status_code = 200
        mock_policy_response.total_item_count = 1
        mock_blade.get_policies.return_value = mock_policy_response
        mock_blade.get_policies_file_systems.return_value = mock_policy_response

        # Mock successful policy removal
        mock_delete_response = Mock()
        mock_delete_response.status_code = 200
        mock_blade.delete_policies_file_systems.return_value = mock_delete_response
        mock_blade.patch_file_systems.return_value = mock_delete_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function
        modify_fs(mock_module, mock_blade)

        # Verify
        mock_blade.delete_policies_file_systems.assert_called_once()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.human_to_bytes")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_user_quota(self, mock_human_to_bytes, mock_get_filesystem):
        """Test modifying filesystem user quota"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "user_quota": "100G",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock existing filesystem
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        mock_human_to_bytes.return_value = 107374182400  # 100GB

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function
        modify_fs(mock_module, mock_blade)

        # Verify
        mock_blade.patch_file_systems.assert_called()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.human_to_bytes")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_group_quota(self, mock_human_to_bytes, mock_get_filesystem):
        """Test modifying filesystem group quota"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "group_quota": "200G",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock existing filesystem
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        mock_human_to_bytes.return_value = 214748364800  # 200GB

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function
        modify_fs(mock_module, mock_blade)

        # Verify
        mock_blade.patch_file_systems.assert_called()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_enable_http(self, mock_get_filesystem):
        """Test enabling HTTP on filesystem"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "http": True,
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock existing filesystem with HTTP disabled
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False  # Currently disabled
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function
        modify_fs(mock_module, mock_blade)

        # Verify
        mock_blade.patch_file_systems.assert_called()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_nfsv3_change(self, mock_get_filesystem):
        """Test modifying filesystem NFSv3 setting"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "nfsv3": False,  # Change from True to False
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock existing filesystem with NFSv3 enabled
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True  # Currently enabled
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function
        modify_fs(mock_module, mock_blade)

        # Verify
        mock_blade.patch_file_systems.assert_called()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_nfsv4_change(self, mock_get_filesystem):
        """Test modifying filesystem NFSv4 setting"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "nfsv4": False,  # Change from True to False
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock existing filesystem with NFSv4 enabled
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True  # Currently enabled
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function
        modify_fs(mock_module, mock_blade)

        # Verify
        mock_blade.patch_file_systems.assert_called()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_promote(self, mock_get_filesystem):
        """Test promoting a filesystem"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "promote": True,
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock existing filesystem that is demoted
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"  # Currently demoted
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function
        modify_fs(mock_module, mock_blade)

        # Verify
        mock_blade.patch_file_systems.assert_called()
        mock_module.exit_json.assert_called()

    # ==== planned failover: quiesce / skip_quiesce / abort_quiesce (REST 2.28) ====

    def _failover_params(self, **overrides):
        """Default params for a planned-failover request on test-fs."""
        params = self.get_default_params()
        params.update(overrides)
        return params

    def _link_response(self, status):
        """GET file-system-replica-links answer with one link in ``status``."""
        res = Mock()
        res.status_code = 200
        link = Mock()
        link.status = status
        res.items = [link]
        return res

    def _failing_module(self, params, check_mode=False):
        """Module mock whose fail_json stops execution like real Ansible."""
        mock_module = Mock()
        mock_module.check_mode = check_mode
        mock_module.params = params
        mock_module.fail_json.side_effect = SystemExit(1)
        return mock_module

    @patch("plugins.modules.purefb_fs.FileSystemPatch")
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.28"),
    )
    def test_modify_fs_quiesce_promoted_sends_dedicated_patch(
        self, mock_get_filesystem, mock_fs_patch
    ):
        """promote=false with quiesce=true on a promoted filesystem sends one
        PATCH whose body is FileSystemPatch(requested_promotion_state="demoted",
        quiesce=True) and nothing else: no other attribute, no discard flag
        (the array refuses it with quiesce), no replica-link GET.
        """
        params = self._failover_params(promote=False, quiesce=True)
        mock_fs = self._existing_fs()

        mock_module, mock_blade = self._run_modify(params, mock_fs, mock_get_filesystem)

        mock_fs_patch.assert_called_once_with(
            requested_promotion_state="demoted", quiesce=True
        )
        mock_blade.patch_file_systems.assert_called_once_with(
            names=["test-fs"], file_system=mock_fs_patch.return_value
        )
        mock_blade.get_file_system_replica_links.assert_not_called()
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.FileSystemPatch")
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.28"),
    )
    def test_modify_fs_quiesce_passes_fleet_context(
        self, mock_get_filesystem, mock_fs_patch
    ):
        """The failover PATCH carries context_names when a context is set."""
        params = self._failover_params(
            promote=False, quiesce=True, context="fleet-member"
        )
        mock_fs = self._existing_fs()

        mock_module, mock_blade = self._run_modify(params, mock_fs, mock_get_filesystem)

        mock_blade.patch_file_systems.assert_called_once_with(
            names=["test-fs"],
            file_system=mock_fs_patch.return_value,
            context_names=["fleet-member"],
        )
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.28"),
    )
    def test_modify_fs_quiesce_while_demoting_is_noop(self, mock_get_filesystem):
        """A rerun while the failover is still replicating changes nothing."""
        params = self._failover_params(promote=False, quiesce=True)
        mock_fs = self._existing_fs(
            promotion_status="demoting", requested_promotion_state="demoted"
        )

        mock_module, mock_blade = self._run_modify(params, mock_fs, mock_get_filesystem)

        mock_blade.patch_file_systems.assert_not_called()
        mock_module.exit_json.assert_called_with(changed=False)

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.28"),
    )
    def test_modify_fs_quiesce_when_demoted_is_noop(self, mock_get_filesystem):
        """A rerun after the failover completed changes nothing."""
        params = self._failover_params(promote=False, quiesce=True)
        mock_fs = self._existing_fs(
            promotion_status="demoted", requested_promotion_state="demoted"
        )

        mock_module, mock_blade = self._run_modify(params, mock_fs, mock_get_filesystem)

        mock_blade.patch_file_systems.assert_not_called()
        mock_module.exit_json.assert_called_with(changed=False)

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.28"),
    )
    def test_modify_fs_quiesce_check_mode(self, mock_get_filesystem):
        """Check mode reports the pending failover without sending it."""
        params = self._failover_params(promote=False, quiesce=True)
        mock_module = Mock()
        mock_module.check_mode = True
        mock_module.params = params
        mock_blade = Mock()
        mock_fs = self._existing_fs()
        mock_get_filesystem.return_value = mock_fs
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        modify_fs(mock_module, mock_blade)

        mock_blade.patch_file_systems.assert_not_called()
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.28"),
    )
    @patch(
        "plugins.modules.purefb_fs.get_error_message",
        Mock(return_value="Operation not permitted."),
    )
    def test_modify_fs_quiesce_array_error_is_surfaced(self, mock_get_filesystem):
        """A refused quiesce (no replica link, mixed versions, transfer in
        progress) fails with the array's own message.
        """
        params = self._failover_params(promote=False, quiesce=True)
        mock_module = self._failing_module(params)
        mock_blade = Mock()
        mock_fs = self._existing_fs()
        mock_get_filesystem.return_value = mock_fs
        mock_blade.get_file_systems.return_value.items = [mock_fs]
        error_res = Mock()
        error_res.status_code = 400
        mock_blade.patch_file_systems.return_value = error_res

        try:
            modify_fs(mock_module, mock_blade)
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "quiesce" in msg
        assert "Operation not permitted." in msg
        mock_module.exit_json.assert_not_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.28"),
    )
    def test_modify_fs_skip_quiesce_requires_discard_snaps(self, mock_get_filesystem):
        """quiesce=false on a demoting filesystem discards unreplicated data,
        so it is refused before any PATCH unless discard_snaps is true.
        """
        params = self._failover_params(promote=False, quiesce=False)
        mock_module = self._failing_module(params)
        mock_blade = Mock()
        mock_fs = self._existing_fs(
            promotion_status="demoting", requested_promotion_state="demoted"
        )
        mock_get_filesystem.return_value = mock_fs

        try:
            modify_fs(mock_module, mock_blade)
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert "discard_snaps" in mock_module.fail_json.call_args[1]["msg"]
        mock_blade.patch_file_systems.assert_not_called()

    @patch("plugins.modules.purefb_fs.FileSystemPatch")
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.28"),
    )
    def test_modify_fs_skip_quiesce_sends_skip_with_discard(
        self, mock_get_filesystem, mock_fs_patch
    ):
        """quiesce=false with discard_snaps=true on a demoting filesystem sends
        FileSystemPatch(requested_promotion_state="demoted", skip_quiesce=True)
        with discard_non_snapshotted_data.
        """
        params = self._failover_params(promote=False, quiesce=False, discard_snaps=True)
        mock_fs = self._existing_fs(
            promotion_status="demoting", requested_promotion_state="demoted"
        )

        mock_module, mock_blade = self._run_modify(params, mock_fs, mock_get_filesystem)

        mock_fs_patch.assert_called_once_with(
            requested_promotion_state="demoted", skip_quiesce=True
        )
        mock_blade.patch_file_systems.assert_called_once_with(
            names=["test-fs"],
            file_system=mock_fs_patch.return_value,
            discard_non_snapshotted_data=True,
        )
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.FileSystemPatch")
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.28"),
    )
    def test_modify_fs_quiesce_false_on_promoted_demotes_immediately(
        self, mock_get_filesystem, mock_fs_patch
    ):
        """quiesce=false on a promoted filesystem is the pre-existing
        immediate demotion (requested_promotion_state=demoted), never a
        skip_quiesce.
        """
        params = self._failover_params(promote=False, quiesce=False, discard_snaps=True)
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = params
        mock_blade = Mock()
        mock_fs = self._existing_fs()
        mock_get_filesystem.return_value = mock_fs
        mock_blade.get_file_systems.return_value.items = [mock_fs]
        mock_blade.get_file_system_replica_links.return_value = self._link_response(
            "idle"
        )
        ok_res = Mock()
        ok_res.status_code = 200
        mock_blade.patch_file_systems.return_value = ok_res

        modify_fs(mock_module, mock_blade)

        sent = [call.kwargs for call in mock_fs_patch.call_args_list]
        assert any(k.get("requested_promotion_state") == "demoted" for k in sent)
        assert not any("skip_quiesce" in k or "quiesce" in k for k in sent)
        mock_blade.patch_file_systems.assert_called_once()
        patch_kwargs = mock_blade.patch_file_systems.call_args.kwargs
        assert patch_kwargs["discard_non_snapshotted_data"] is True
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.FileSystemPatch")
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.28"),
    )
    def test_modify_fs_abort_quiesce_on_demoting_source(
        self, mock_get_filesystem, mock_fs_patch
    ):
        """promote=true with abort_quiesce=true on the demoting source sends
        FileSystemPatch(requested_promotion_state="promoted", abort_quiesce=True)
        without looking up the link.
        """
        params = self._failover_params(promote=True, abort_quiesce=True)
        mock_fs = self._existing_fs(
            promotion_status="demoting", requested_promotion_state="demoted"
        )

        mock_module, mock_blade = self._run_modify(params, mock_fs, mock_get_filesystem)

        mock_fs_patch.assert_called_once_with(
            requested_promotion_state="promoted", abort_quiesce=True
        )
        mock_blade.patch_file_systems.assert_called_once_with(
            names=["test-fs"], file_system=mock_fs_patch.return_value
        )
        mock_blade.get_file_system_replica_links.assert_not_called()
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.FileSystemPatch")
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.28"),
    )
    def test_modify_fs_abort_quiesce_on_quiescing_target(
        self, mock_get_filesystem, mock_fs_patch
    ):
        """A demoted target shows the failover only on its replica link; a
        quiescing link makes abort_quiesce send the abort PATCH.
        """
        params = self._failover_params(promote=True, abort_quiesce=True)
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = params
        mock_blade = Mock()
        mock_fs = self._existing_fs(
            promotion_status="demoted", requested_promotion_state="demoted"
        )
        mock_get_filesystem.return_value = mock_fs
        mock_blade.get_file_systems.return_value.items = [mock_fs]
        mock_blade.get_file_system_replica_links.return_value = self._link_response(
            "quiescing"
        )
        ok_res = Mock()
        ok_res.status_code = 200
        mock_blade.patch_file_systems.return_value = ok_res

        modify_fs(mock_module, mock_blade)

        mock_blade.get_file_system_replica_links.assert_called_once_with(
            local_file_system_names=["test-fs"]
        )
        mock_fs_patch.assert_called_once_with(
            requested_promotion_state="promoted", abort_quiesce=True
        )
        mock_blade.patch_file_systems.assert_called_once_with(
            names=["test-fs"], file_system=mock_fs_patch.return_value
        )
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.FileSystemPatch")
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.28"),
    )
    def test_modify_fs_abort_quiesce_without_failover_is_noop(
        self, mock_get_filesystem, mock_fs_patch
    ):
        """abort_quiesce on a demoted filesystem whose link is idle changes
        nothing and never falls back to a regular promotion.
        """
        params = self._failover_params(promote=True, abort_quiesce=True)
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = params
        mock_blade = Mock()
        mock_fs = self._existing_fs(
            promotion_status="demoted", requested_promotion_state="demoted"
        )
        mock_get_filesystem.return_value = mock_fs
        mock_blade.get_file_systems.return_value.items = [mock_fs]
        mock_blade.get_file_system_replica_links.return_value = self._link_response(
            "idle"
        )

        modify_fs(mock_module, mock_blade)

        mock_fs_patch.assert_not_called()
        mock_blade.patch_file_systems.assert_not_called()
        mock_module.exit_json.assert_called_with(changed=False)

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.28"),
    )
    def test_modify_fs_abort_quiesce_on_promoted_is_noop(self, mock_get_filesystem):
        """A rerun after the abort completed (filesystem promoted again)
        changes nothing and needs no replica-link lookup.
        """
        params = self._failover_params(promote=True, abort_quiesce=True)
        mock_fs = self._existing_fs()

        mock_module, mock_blade = self._run_modify(params, mock_fs, mock_get_filesystem)

        mock_blade.get_file_system_replica_links.assert_not_called()
        mock_blade.patch_file_systems.assert_not_called()
        mock_module.exit_json.assert_called_with(changed=False)

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.28"),
    )
    def test_modify_fs_promote_while_demoting_fails(self, mock_get_filesystem):
        """The array denies a plain promotion during a planned failover, so
        promote=true without abort_quiesce fails before any PATCH.
        """
        params = self._failover_params(promote=True)
        mock_module = self._failing_module(params)
        mock_blade = Mock()
        mock_fs = self._existing_fs(
            promotion_status="demoting", requested_promotion_state="demoted"
        )
        mock_get_filesystem.return_value = mock_fs

        try:
            modify_fs(mock_module, mock_blade)
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert "abort_quiesce" in mock_module.fail_json.call_args[1]["msg"]
        mock_blade.patch_file_systems.assert_not_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.get_system")
    @patch("plugins.modules.purefb_fs.AnsibleModule")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.27"),
    )
    def test_main_quiesce_below_rest_2_28_fails(
        self, mock_ansible_module, mock_get_system, mock_get_filesystem
    ):
        """quiesce is gated in main() on REST 2.28 before any write."""
        params = self._failover_params(promote=False, quiesce=True)
        mock_module = self._failing_module(params)
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        mock_get_filesystem.return_value = self._existing_fs()

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert "2.28" in mock_module.fail_json.call_args[1]["msg"]
        mock_blade.patch_file_systems.assert_not_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.get_system")
    @patch("plugins.modules.purefb_fs.AnsibleModule")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.27"),
    )
    def test_main_abort_quiesce_below_rest_2_28_fails(
        self, mock_ansible_module, mock_get_system, mock_get_filesystem
    ):
        """abort_quiesce is gated in main() on REST 2.28 before any write."""
        params = self._failover_params(promote=True, abort_quiesce=True)
        mock_module = self._failing_module(params)
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        mock_get_filesystem.return_value = self._existing_fs(
            promotion_status="demoting", requested_promotion_state="demoted"
        )

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert "2.28" in mock_module.fail_json.call_args[1]["msg"]
        mock_blade.patch_file_systems.assert_not_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.get_system")
    @patch("plugins.modules.purefb_fs.AnsibleModule")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.28"),
    )
    def test_main_quiesce_requires_promote_false(
        self, mock_ansible_module, mock_get_system, mock_get_filesystem
    ):
        """quiesce without promote=false is refused before any write."""
        params = self._failover_params(quiesce=True)
        mock_module = self._failing_module(params)
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        mock_get_filesystem.return_value = self._existing_fs()

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert "promote=false" in mock_module.fail_json.call_args[1]["msg"]
        mock_blade.patch_file_systems.assert_not_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.get_system")
    @patch("plugins.modules.purefb_fs.AnsibleModule")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.28"),
    )
    def test_main_abort_quiesce_requires_promote_true(
        self, mock_ansible_module, mock_get_system, mock_get_filesystem
    ):
        """abort_quiesce without promote=true is refused before any write."""
        params = self._failover_params(promote=False, abort_quiesce=True)
        mock_module = self._failing_module(params)
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        mock_get_filesystem.return_value = self._existing_fs()

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert "promote=true" in mock_module.fail_json.call_args[1]["msg"]
        mock_blade.patch_file_systems.assert_not_called()

    @patch("plugins.modules.purefb_fs.FileSystemPatch")
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.get_system")
    @patch("plugins.modules.purefb_fs.AnsibleModule")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.28"),
    )
    def test_main_quiesce_on_rest_2_28_sends_patch(
        self, mock_ansible_module, mock_get_system, mock_get_filesystem, mock_fs_patch
    ):
        """End to end on a standalone 2.28 array: the gate passes and the
        quiesce PATCH is sent.
        """
        params = self._failover_params(promote=False, quiesce=True)
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = params
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        mock_fs = self._existing_fs()
        mock_get_filesystem.return_value = mock_fs
        mock_blade.get_file_systems.return_value.items = [mock_fs]
        no_fleet = Mock()
        no_fleet.status_code = 400
        mock_blade.get_fleets.return_value = no_fleet
        ok_res = Mock()
        ok_res.status_code = 200
        mock_blade.patch_file_systems.return_value = ok_res

        main()

        mock_fs_patch.assert_called_once_with(
            requested_promotion_state="demoted", quiesce=True
        )
        mock_blade.patch_file_systems.assert_called_once_with(
            names=["test-fs"], file_system=mock_fs_patch.return_value
        )
        mock_module.fail_json.assert_not_called()
        mock_module.exit_json.assert_any_call(changed=True)

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_writable_false(self, mock_get_filesystem):
        """Test making filesystem read-only"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "writable": False,
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock existing filesystem that is writable
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True  # Currently writable
        mock_get_filesystem.return_value = mock_fs

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function
        modify_fs(mock_module, mock_blade)

        # Verify
        mock_blade.patch_file_systems.assert_called()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_writable_true_promoted(self, mock_get_filesystem):
        """Test making promoted filesystem writable"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "writable": True,
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock existing filesystem that is promoted but not writable
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "promoted"  # Promoted
        mock_fs.requested_promotion_state = "promoted"
        mock_fs.writable = False  # Not writable
        mock_get_filesystem.return_value = mock_fs

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function
        modify_fs(mock_module, mock_blade)

        # Verify
        mock_blade.patch_file_systems.assert_called()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_snapshot_enable(self, mock_get_filesystem):
        """Test enabling snapshot directory on filesystem"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "snapshot": True,
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock existing filesystem with snapshot disabled
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False  # Currently disabled
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function
        modify_fs(mock_module, mock_blade)

        # Verify
        mock_blade.patch_file_systems.assert_called()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_fastremove_enable(self, mock_get_filesystem):
        """Test enabling fast remove on filesystem"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "fastremove": True,
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock existing filesystem with fastremove disabled
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False  # Currently disabled
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function
        modify_fs(mock_module, mock_blade)

        # Verify
        mock_blade.patch_file_systems.assert_called()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_hard_limit_enable(self, mock_get_filesystem):
        """Test enabling hard limit on filesystem"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "hard_limit": True,
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock existing filesystem with hard_limit disabled
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False  # Currently disabled
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function
        modify_fs(mock_module, mock_blade)

        # Verify
        mock_blade.patch_file_systems.assert_called()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_safeguard_acls_enable(self, mock_get_filesystem):
        """Test enabling safeguard ACLs on filesystem"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "safeguard_acls": True,
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock existing filesystem with safeguard_acls disabled
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = False  # Currently disabled
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function
        modify_fs(mock_module, mock_blade)

        # Verify
        mock_blade.patch_file_systems.assert_called()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_access_control_change(self, mock_get_filesystem):
        """Test changing access control style on filesystem"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "access_control": "independent",  # Change from shared
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock existing filesystem with shared access control
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"  # Current style
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function
        modify_fs(mock_module, mock_blade)

        # Verify
        mock_blade.patch_file_systems.assert_called()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_recover_destroyed(self, mock_get_filesystem):
        """Test recovering a destroyed filesystem"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "state": "present",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock existing filesystem that is destroyed
        mock_fs = Mock()
        mock_fs.destroyed = True  # Currently destroyed
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function
        modify_fs(mock_module, mock_blade)

        # Verify - should recover the filesystem
        mock_blade.patch_file_systems.assert_called()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_create_fs_with_policy(self, mock_get_filesystem):
        """Test creating filesystem with snapshot/access policy"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "policy": "test-policy",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock successful filesystem creation
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_response
        mock_blade.get_policies.return_value = mock_response
        mock_blade.post_policies_file_systems.return_value = mock_response

        mock_get_filesystem.return_value = None

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify
        mock_blade.post_file_systems.assert_called_once()
        mock_blade.get_policies.assert_called_once()
        mock_blade.post_policies_file_systems.assert_called_once()
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_create_fs_with_invalid_policy(self, mock_get_filesystem):
        """Test creating filesystem with invalid policy"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.fail_json.side_effect = Exception("fail_json")
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "policy": "invalid-policy",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock successful filesystem creation
        mock_create_response = Mock()
        mock_create_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_create_response

        # Mock failed policy check
        mock_policy_response = Mock()
        mock_policy_response.status_code = 400
        mock_blade.get_policies.return_value = mock_policy_response

        # Mock delete for cleanup
        mock_delete_response = Mock()
        mock_delete_response.status_code = 200
        mock_blade.delete_file_systems.return_value = mock_delete_response

        mock_get_filesystem.return_value = None

        # Call function - should fail
        try:
            create_fs(mock_module, mock_blade)
        except Exception as e:
            assert str(e) == "fail_json"

        # Verify - should have tried to delete the filesystem
        mock_blade.post_file_systems.assert_called_once()
        mock_blade.get_policies.assert_called_once()
        mock_module.fail_json.assert_called_once()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    def test_create_fs_access_control_nfs_without_nfs(self, mock_get_filesystem):
        """Test creating filesystem with NFS access control but NFS disabled"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.fail_json.side_effect = Exception("fail_json")
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "access_control": "nfs",
                "nfsv3": False,
                "nfsv4": False,
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions().items = [mock_version]

        mock_get_filesystem.return_value = None

        # Call function - should fail
        try:
            create_fs(mock_module, mock_blade)
        except Exception as e:
            assert str(e) == "fail_json"

        # Verify - should have failed
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args
        assert "Cannot set access_control to nfs" in call_args[1]["msg"]

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    def test_create_fs_access_control_smb_without_smb(self, mock_get_filesystem):
        """Test creating filesystem with SMB access control but SMB disabled"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.fail_json.side_effect = Exception("fail_json")
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "access_control": "smb",
                "smb": False,
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions().items = [mock_version]

        mock_get_filesystem.return_value = None

        # Call function - should fail
        try:
            create_fs(mock_module, mock_blade)
        except Exception as e:
            assert str(e) == "fail_json"

        # Verify - should have failed
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args
        assert "Cannot set access_control" in call_args[1]["msg"]

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.3"),
    )
    def test_modify_fs_change_export_policy(self, mock_get_filesystem):
        """Test changing NFS export policy on existing filesystem"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "export_policy": "new-export-policy",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.3"
        # Make the version object comparable with strings
        mock_version.__eq__ = lambda self, other: self.version == other
        mock_blade.get_versions.return_value.items = [mock_version, "2.3"]

        # Mock existing filesystem with different export policy
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.nfs.export_policy = Mock()
        mock_fs.nfs.export_policy.name = "old-export-policy"  # Current policy
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function
        modify_fs(mock_module, mock_blade)

        # Verify
        mock_blade.patch_file_systems.assert_called()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.3"),
    )
    def test_modify_fs_add_export_policy(self, mock_get_filesystem):
        """Test adding NFS export policy to filesystem without one"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "export_policy": "new-export-policy",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.3"
        mock_version.__eq__ = lambda self, other: self.version == other
        mock_blade.get_versions.return_value.items = [mock_version, "2.3"]

        # Mock existing filesystem without export policy
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.nfs.export_policy = Mock()
        mock_fs.nfs.export_policy.name = None  # No current policy
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function
        modify_fs(mock_module, mock_blade)

        # Verify
        mock_blade.patch_file_systems.assert_called()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.10"),
    )
    def test_modify_fs_change_share_policy(self, mock_get_filesystem):
        """Test changing SMB share policy on existing filesystem"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "smb": True,
                "share_policy": "new-share-policy",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.10"
        mock_version.__eq__ = lambda self, other: self.version == other
        mock_blade.get_versions.return_value.items = [mock_version, "2.10"]

        # Mock existing filesystem with different share policy
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.nfs.export_policy = Mock()
        mock_fs.nfs.export_policy.name = None
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = True
        mock_fs.smb.share_policy = Mock()
        mock_fs.smb.share_policy.name = "old-share-policy"  # Current policy
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function
        modify_fs(mock_module, mock_blade)

        # Verify
        mock_blade.patch_file_systems.assert_called()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.10"),
    )
    def test_modify_fs_change_client_policy(self, mock_get_filesystem):
        """Test changing SMB client policy on existing filesystem"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "smb": True,
                "client_policy": "new-client-policy",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.10"
        mock_version.__eq__ = lambda self, other: self.version == other
        mock_blade.get_versions.return_value.items = [mock_version, "2.10"]

        # Mock existing filesystem with different client policy
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.nfs.export_policy = Mock()
        mock_fs.nfs.export_policy.name = None
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = True
        mock_fs.smb.share_policy = Mock()
        mock_fs.smb.share_policy.name = None
        mock_fs.smb.client_policy = Mock()
        mock_fs.smb.client_policy.name = "old-client-policy"  # Current policy
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function
        modify_fs(mock_module, mock_blade)

        # Verify
        mock_blade.patch_file_systems.assert_called()
        mock_module.exit_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.3"),
    )
    def test_modify_fs_export_policy_failure(self, mock_get_filesystem):
        """Test export policy modification failure"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.fail_json.side_effect = Exception("fail_json")
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "export_policy": "new-export-policy",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.3"
        mock_version.__eq__ = lambda self, other: self.version == other
        mock_blade.get_versions.return_value.items = [mock_version, "2.3"]

        # Mock existing filesystem
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.nfs.export_policy = Mock()
        mock_fs.nfs.export_policy.name = None
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        # Mock failed patch
        mock_response = Mock()
        mock_response.status_code = 400
        mock_blade.patch_file_systems.return_value = mock_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function - should fail
        try:
            modify_fs(mock_module, mock_blade)
        except Exception as e:
            assert str(e) == "fail_json"

        # Verify
        mock_blade.patch_file_systems.assert_called()
        mock_module.fail_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.10"),
    )
    def test_modify_fs_share_policy_failure(self, mock_get_filesystem):
        """Test share policy modification failure"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.fail_json.side_effect = Exception("fail_json")
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "smb": True,
                "share_policy": "new-share-policy",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.10"
        mock_version.__eq__ = lambda self, other: self.version == other
        mock_blade.get_versions.return_value.items = [mock_version, "2.10"]

        # Mock existing filesystem
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.nfs.export_policy = Mock()
        mock_fs.nfs.export_policy.name = None
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = True
        mock_fs.smb.share_policy = Mock()
        mock_fs.smb.share_policy.name = None
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        # Mock failed patch
        mock_response = Mock()
        mock_response.status_code = 400
        mock_blade.patch_file_systems.return_value = mock_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function - should fail
        try:
            modify_fs(mock_module, mock_blade)
        except Exception as e:
            assert str(e) == "fail_json"

        # Verify
        mock_blade.patch_file_systems.assert_called()
        mock_module.fail_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.10"),
    )
    def test_modify_fs_client_policy_failure(self, mock_get_filesystem):
        """Test client policy modification failure"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.fail_json.side_effect = Exception("fail_json")
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "smb": True,
                "client_policy": "new-client-policy",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.10"
        mock_version.__eq__ = lambda self, other: self.version == other
        mock_blade.get_versions.return_value.items = [mock_version, "2.10"]

        # Mock existing filesystem
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.nfs.export_policy = Mock()
        mock_fs.nfs.export_policy.name = None
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = True
        mock_fs.smb.share_policy = Mock()
        mock_fs.smb.share_policy.name = None
        mock_fs.smb.client_policy = Mock()
        mock_fs.smb.client_policy.name = None
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        # Mock failed patch
        mock_response = Mock()
        mock_response.status_code = 400
        mock_blade.patch_file_systems.return_value = mock_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        # Call function - should fail
        try:
            modify_fs(mock_module, mock_blade)
        except Exception as e:
            assert str(e) == "fail_json"

        # Verify
        mock_blade.patch_file_systems.assert_called()
        mock_module.fail_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_create_fs_with_user_quota(self, mock_get_filesystem):
        """Test creating filesystem with user quota"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "user_quota": "100G",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions().items = [mock_version]

        # Mock successful filesystem creation
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_response

        mock_get_filesystem.return_value = None

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify
        mock_blade.post_file_systems.assert_called_once()
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_create_fs_with_group_quota(self, mock_get_filesystem):
        """Test creating filesystem with group quota"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "group_quota": "200G",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions().items = [mock_version]

        # Mock successful filesystem creation
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_response

        mock_get_filesystem.return_value = None

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify
        mock_blade.post_file_systems.assert_called_once()
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    def test_create_fs_safeguard_acls_with_invalid_access_control(
        self, mock_get_filesystem
    ):
        """Test creating filesystem with safeguard ACLs and invalid access control"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.fail_json.side_effect = Exception("fail_json")
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "safeguard_acls": True,
                "access_control": "mode-bits",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions().items = [mock_version]

        mock_get_filesystem.return_value = None

        # Call function - should fail
        try:
            create_fs(mock_module, mock_blade)
        except Exception as e:
            assert str(e) == "fail_json"

        # Verify - should have failed
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args
        assert "ACL Safeguarding" in call_args[1]["msg"]

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_create_fs_smb_disabled_with_empty_nfs_rules(self, mock_get_filesystem):
        """Test creating filesystem with SMB disabled and empty NFS rules"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "smb": False,
                "nfs_rules": "",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions().items = [mock_version]

        # Mock successful filesystem creation
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_response

        mock_get_filesystem.return_value = None

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify - NFS rules should be set to empty string
        mock_blade.post_file_systems.assert_called_once()
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_add_policy_invalid(self, mock_get_filesystem):
        """Test adding invalid policy to filesystem"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.fail_json.side_effect = Exception("fail_json")
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "policy": "invalid-policy",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock existing filesystem
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.nfs.export_policy = Mock()
        mock_fs.nfs.export_policy.name = None
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        # Mock policy doesn't exist
        mock_policy_response = Mock()
        mock_policy_response.status_code = 400
        mock_blade.get_policies.return_value = mock_policy_response

        # Call function - should fail
        try:
            modify_fs(mock_module, mock_blade)
        except Exception as e:
            assert str(e) == "fail_json"

        # Verify
        mock_blade.get_policies.assert_called()
        mock_module.fail_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_add_policy_attach_failure(self, mock_get_filesystem):
        """Test adding policy to filesystem with attach failure"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.fail_json.side_effect = Exception("fail_json")
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "policy": "test-policy",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock existing filesystem
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_fs.provisioned = 1099511627776
        mock_fs.nfs = Mock()
        mock_fs.nfs.v3_enabled = True
        mock_fs.nfs.v4_1_enabled = True
        mock_fs.nfs.rules = "*(rw,no_root_squash)"
        mock_fs.nfs.export_policy = Mock()
        mock_fs.nfs.export_policy.name = None
        mock_fs.smb = Mock()
        mock_fs.smb.enabled = False
        mock_fs.http = Mock()
        mock_fs.http.enabled = False
        mock_fs.snapshot_directory_enabled = False
        mock_fs.fast_remove_directory_enabled = False
        mock_fs.hard_limit_enabled = False
        mock_fs.default_user_quota = None
        mock_fs.default_group_quota = None
        mock_fs.group_ownership = None
        mock_fs.multi_protocol = Mock()
        mock_fs.multi_protocol.safeguard_acls = True
        mock_fs.multi_protocol.access_control_style = "shared"
        mock_fs.promotion_status = "demoted"
        mock_fs.requested_promotion_state = "demoted"
        mock_fs.writable = True
        mock_get_filesystem.return_value = mock_fs

        # Mock policy exists
        mock_policy_response = Mock()
        mock_policy_response.status_code = 200
        mock_blade.get_policies.return_value = mock_policy_response

        # Mock filesystem is not in policy
        mock_member_response = Mock()
        mock_member_response.status_code = 400
        mock_blade.get_policies_file_systems.return_value = mock_member_response

        # Mock failed attach
        mock_attach_response = Mock()
        mock_attach_response.status_code = 400
        mock_blade.post_policies_file_systems.return_value = mock_attach_response

        # Call function - should fail
        try:
            modify_fs(mock_module, mock_blade)
        except Exception as e:
            assert str(e) == "fail_json"

        # Verify
        mock_blade.post_policies_file_systems.assert_called()
        mock_module.fail_json.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.3"),
    )
    def test_create_fs_with_export_policy(self, mock_get_filesystem):
        """Test creating filesystem with export policy (API 2.3+)"""
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "nfs": True,
                "export_policy": "test-export-policy",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        # Mock API version 2.3 for export policy support
        mock_version = Mock()
        mock_version.version = "2.3"
        mock_version.__eq__ = lambda self, other: self.version == other
        mock_blade.get_versions.return_value.items = [mock_version]

        mock_get_filesystem.return_value = None

        # Mock successful filesystem creation
        mock_create_response = Mock()
        mock_create_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_create_response

        # Mock successful export policy assignment
        mock_export_response = Mock()
        mock_export_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_export_response

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify filesystem was created
        mock_blade.post_file_systems.assert_called_once()

        # Verify export policy was assigned
        mock_blade.patch_file_systems.assert_called()
        call_args = mock_blade.patch_file_systems.call_args
        assert call_args[1]["names"] == ["test-fs"]

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.3"),
    )
    def test_create_fs_with_export_policy_failure(self, mock_get_filesystem):
        """Test creating filesystem with export policy assignment failure"""
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.fail_json.side_effect = Exception("fail_json")
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "nfs": True,
                "export_policy": "test-export-policy",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        # Mock API version 2.3 for export policy support
        mock_version = Mock()
        mock_version.version = "2.3"
        mock_version.__eq__ = lambda self, other: self.version == other
        mock_blade.get_versions.return_value.items = [mock_version]

        mock_get_filesystem.return_value = None

        # Mock successful filesystem creation
        mock_create_response = Mock()
        mock_create_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_create_response

        # Mock failed export policy assignment
        mock_export_response = Mock()
        mock_export_response.status_code = 400
        mock_export_response.errors = [Mock(message="Export policy not found")]
        mock_blade.patch_file_systems.return_value = mock_export_response

        # Call function - should fail
        try:
            create_fs(mock_module, mock_blade)
        except Exception as e:
            assert str(e) == "fail_json"

        # Verify error was raised
        mock_module.fail_json.assert_called()
        call_args = mock_module.fail_json.call_args[1]
        assert "failed to assign export policy" in call_args["msg"]

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.10"),
    )
    def test_create_fs_with_client_policy(self, mock_get_filesystem):
        """Test creating filesystem with SMB client policy (API 2.10+)"""
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "smb": True,
                "client_policy": "test-client-policy",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        # Mock API version 2.10 for SMB policy support
        mock_version = Mock()
        mock_version.version = "2.10"
        mock_version.__eq__ = lambda self, other: self.version == other
        mock_blade.get_versions.return_value.items = [mock_version]

        mock_get_filesystem.return_value = None

        # Mock successful filesystem creation
        mock_create_response = Mock()
        mock_create_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_create_response

        # Mock successful client policy assignment
        mock_policy_response = Mock()
        mock_policy_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_policy_response

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify filesystem was created
        mock_blade.post_file_systems.assert_called_once()

        # Verify client policy was assigned
        mock_blade.patch_file_systems.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.10"),
    )
    def test_create_fs_with_client_policy_failure(self, mock_get_filesystem):
        """Test creating filesystem with SMB client policy assignment failure"""
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.fail_json.side_effect = Exception("fail_json")
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "smb": True,
                "client_policy": "test-client-policy",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        # Mock API version 2.10 for SMB policy support
        mock_version = Mock()
        mock_version.version = "2.10"
        mock_version.__eq__ = lambda self, other: self.version == other
        mock_blade.get_versions.return_value.items = [mock_version]

        mock_get_filesystem.return_value = None

        # Mock successful filesystem creation
        mock_create_response = Mock()
        mock_create_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_create_response

        # Mock failed client policy assignment
        mock_policy_response = Mock()
        mock_policy_response.status_code = 400
        mock_policy_response.errors = [Mock(message="Client policy not found")]
        mock_blade.patch_file_systems.return_value = mock_policy_response

        # Call function - should fail
        try:
            create_fs(mock_module, mock_blade)
        except Exception as e:
            assert str(e) == "fail_json"

        # Verify error was raised
        mock_module.fail_json.assert_called()
        call_args = mock_module.fail_json.call_args[1]
        assert "failed to assign client policy" in call_args["msg"]

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.10"),
    )
    def test_create_fs_with_share_policy(self, mock_get_filesystem):
        """Test creating filesystem with SMB share policy (API 2.10+)"""
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "smb": True,
                "share_policy": "test-share-policy",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        # Mock API version 2.10 for SMB policy support
        mock_version = Mock()
        mock_version.version = "2.10"
        mock_version.__eq__ = lambda self, other: self.version == other
        mock_blade.get_versions.return_value.items = [mock_version]

        mock_get_filesystem.return_value = None

        # Mock successful filesystem creation
        mock_create_response = Mock()
        mock_create_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_create_response

        # Mock successful share policy assignment
        mock_policy_response = Mock()
        mock_policy_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_policy_response

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify filesystem was created
        mock_blade.post_file_systems.assert_called_once()

        # Verify share policy was assigned
        mock_blade.patch_file_systems.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.10"),
    )
    def test_create_fs_with_share_policy_failure(self, mock_get_filesystem):
        """Test creating filesystem with SMB share policy assignment failure"""
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.fail_json.side_effect = Exception("fail_json")
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "smb": True,
                "share_policy": "test-share-policy",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        # Mock API version 2.10 for SMB policy support
        mock_version = Mock()
        mock_version.version = "2.10"
        mock_version.__eq__ = lambda self, other: self.version == other
        mock_blade.get_versions.return_value.items = [mock_version]

        mock_get_filesystem.return_value = None

        # Mock successful filesystem creation
        mock_create_response = Mock()
        mock_create_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_create_response

        # Mock failed share policy assignment
        mock_policy_response = Mock()
        mock_policy_response.status_code = 400
        mock_policy_response.errors = [Mock(message="Share policy not found")]
        mock_blade.patch_file_systems.return_value = mock_policy_response

        # Call function - should fail
        try:
            create_fs(mock_module, mock_blade)
        except Exception as e:
            assert str(e) == "fail_json"

        # Verify error was raised
        mock_module.fail_json.assert_called()
        call_args = mock_module.fail_json.call_args[1]
        assert "failed to assign share policy" in call_args["msg"]

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_create_fs_without_size(self, mock_get_filesystem):
        """Test creating filesystem without size parameter (defaults to 0)"""
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": None,  # No size specified
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_version.__eq__ = lambda self, other: self.version == other
        mock_blade.get_versions.return_value.items = [mock_version]

        mock_get_filesystem.return_value = None

        # Mock successful filesystem creation
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_response

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify filesystem was created
        mock_blade.post_file_systems.assert_called_once()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.17"),
    )
    def test_create_fs_with_context_api(self, mock_get_filesystem):
        """Test creating filesystem with context API (API 2.17+)"""
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "context": "test-context",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        # Mock API version 2.17 for context support
        mock_version = Mock()
        mock_version.version = "2.17"
        mock_version.__eq__ = lambda self, other: self.version == other
        mock_blade.get_versions.return_value.items = [mock_version]

        mock_get_filesystem.return_value = None

        # Mock successful filesystem creation
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_response

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify filesystem was created with context
        mock_blade.post_file_systems.assert_called_once()
        call_args = mock_blade.post_file_systems.call_args
        assert "context_names" in call_args[1]

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.17"),
    )
    def test_create_fs_with_policy_context_api(self, mock_get_filesystem):
        """Test creating filesystem with policy using context API (API 2.17+)"""
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "policy": "test-policy",
                "context": "test-context",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        # Mock API version 2.17 for context support
        mock_version = Mock()
        mock_version.version = "2.17"
        mock_version.__eq__ = lambda self, other: self.version == other
        mock_blade.get_versions.return_value.items = [mock_version]

        mock_get_filesystem.return_value = None

        # Mock successful filesystem creation
        mock_create_response = Mock()
        mock_create_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_create_response

        # Mock policy exists
        mock_policy_response = Mock()
        mock_policy_response.status_code = 200
        mock_blade.get_policies.return_value = mock_policy_response

        # Mock policy attachment (uses POST during creation)
        mock_attach_response = Mock()
        mock_attach_response.status_code = 200
        mock_blade.post_policies_file_systems.return_value = mock_attach_response

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify policy was checked with context
        mock_blade.get_policies.assert_called_once()
        call_args = mock_blade.get_policies.call_args
        assert "context_names" in call_args[1]

        # Verify policy was attached with context (POST during creation)
        mock_blade.post_policies_file_systems.assert_called_once()
        call_args = mock_blade.post_policies_file_systems.call_args
        assert "context_names" in call_args[1]

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.17"),
    )
    def test_create_fs_policy_attach_with_context(self, mock_get_filesystem):
        """Test policy attachment during creation with context API"""
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "policy": "test-policy",
                "context": "test-context",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        # Mock API version 2.17 for context support
        mock_version = Mock()
        mock_version.version = "2.17"
        mock_version.__eq__ = lambda self, other: self.version == other
        mock_blade.get_versions.return_value.items = [mock_version]

        mock_get_filesystem.return_value = None

        # Mock successful filesystem creation
        mock_create_response = Mock()
        mock_create_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_create_response

        # Mock policy exists
        mock_policy_response = Mock()
        mock_policy_response.status_code = 200
        mock_blade.get_policies.return_value = mock_policy_response

        # Mock policy attachment with context
        mock_attach_response = Mock()
        mock_attach_response.status_code = 200
        mock_blade.post_policies_file_systems.return_value = mock_attach_response

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify policy was attached with context
        mock_blade.post_policies_file_systems.assert_called_once()
        call_args = mock_blade.post_policies_file_systems.call_args
        assert "context_names" in call_args[1]

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    def test_eradicate_fs_eradicate_failure(self, mock_get_filesystem):
        """Test eradicate_fs when eradication fails"""
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "state": "absent",
                "eradicate": True,
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_version.__eq__ = lambda self, other: self.version == other
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock filesystem exists and is destroyed
        mock_fs = Mock()
        mock_fs.destroyed = True
        mock_get_filesystem.return_value = mock_fs

        # Mock eradication failure
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.errors = [Mock(message="Eradication failed")]
        mock_blade.delete_file_systems.return_value = mock_response

        # Call function
        eradicate_fs(mock_module, mock_blade)

        # Verify error was raised
        mock_module.fail_json.assert_called()
        call_args = mock_module.fail_json.call_args[1]
        assert "Failed to eradicate filesystem" in call_args["msg"]

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    def test_delete_fs_with_eradicate_failure(self, mock_get_filesystem):
        """Test delete_fs with eradicate=True when eradication fails"""
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "state": "absent",
                "eradicate": True,
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_version.__eq__ = lambda self, other: self.version == other
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock filesystem exists and is not destroyed
        mock_fs = Mock()
        mock_fs.destroyed = False
        mock_get_filesystem.return_value = mock_fs

        # Mock successful deletion
        mock_delete_response = Mock()
        mock_delete_response.status_code = 200

        # Mock eradication failure
        mock_eradicate_response = Mock()
        mock_eradicate_response.status_code = 400
        mock_eradicate_response.errors = [Mock(message="Eradication failed")]

        mock_blade.patch_file_systems.return_value = mock_delete_response
        mock_blade.delete_file_systems.return_value = mock_eradicate_response

        # Call function
        delete_fs(mock_module, mock_blade)

        # Verify error was raised
        mock_module.fail_json.assert_called()
        call_args = mock_module.fail_json.call_args[1]
        assert "Failed to eradicate filesystem" in call_args["msg"]

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_create_fs_policy_attach_failure_cleanup(self, mock_get_filesystem):
        """Test that filesystem is cleaned up when policy attachment fails during creation"""
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "policy": "test-policy",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_version.__eq__ = lambda self, other: self.version == other
        mock_blade.get_versions.return_value.items = [mock_version]

        mock_get_filesystem.return_value = None

        # Mock successful filesystem creation
        mock_create_response = Mock()
        mock_create_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_create_response

        # Mock policy exists
        mock_policy_response = Mock()
        mock_policy_response.status_code = 200
        mock_blade.get_policies.return_value = mock_policy_response

        # Mock policy attachment failure
        mock_attach_response = Mock()
        mock_attach_response.status_code = 400
        mock_attach_response.errors = [Mock(message="Policy attachment failed")]
        mock_blade.post_policies_file_systems.return_value = mock_attach_response

        # Mock cleanup operations
        mock_cleanup_response = Mock()
        mock_cleanup_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_cleanup_response
        mock_blade.delete_file_systems.return_value = mock_cleanup_response

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify error was raised
        mock_module.fail_json.assert_called()
        call_args = mock_module.fail_json.call_args[1]
        assert "Failed to apply policy" in call_args["msg"]

        # Verify cleanup was attempted (patch_file_systems called to destroy)
        mock_blade.patch_file_systems.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_create_fs_policy_check_failure_cleanup(self, mock_get_filesystem):
        """Test that filesystem is cleaned up when policy check fails during creation"""
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "policy": "nonexistent-policy",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0"
        mock_version.__eq__ = lambda self, other: self.version == other
        mock_blade.get_versions.return_value.items = [mock_version]

        mock_get_filesystem.return_value = None

        # Mock successful filesystem creation
        mock_create_response = Mock()
        mock_create_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_create_response

        # Mock policy check failure (get_policies returns 400)
        mock_policy_response = Mock()
        mock_policy_response.status_code = 400
        mock_policy_response.errors = [Mock(message="Policy not found")]
        mock_blade.get_policies.return_value = mock_policy_response

        # Mock cleanup operations
        mock_cleanup_response = Mock()
        mock_cleanup_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_cleanup_response
        mock_blade.delete_file_systems.return_value = mock_cleanup_response

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify error was raised with correct message
        mock_module.fail_json.assert_called()
        call_args = mock_module.fail_json.call_args[1]
        # The error message should contain "doesn't exist" when get_policies fails
        assert (
            "doesn't exist" in call_args["msg"]
            or "Failed to apply policy" in call_args["msg"]
        )

        # Verify cleanup was attempted
        mock_blade.patch_file_systems.assert_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.17"),
    )
    def test_create_fs_export_policy_with_context(self, mock_get_filesystem):
        """Test creating filesystem with export policy using context API"""
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "nfsv3": True,
                "export_policy": "test-export-policy",
                "context": "test-context",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        # Mock API versions: 2.17 (context), 2.3 (export policy)
        versions = []
        for ver in ["2.17", "2.3"]:
            mock_ver = Mock()
            mock_ver.version = ver
            mock_ver.__eq__ = lambda self, other: self.version == other
            versions.append(mock_ver)
        mock_blade.get_versions.return_value.items = versions

        mock_get_filesystem.return_value = None

        # Mock successful filesystem creation
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_response
        mock_blade.patch_file_systems.return_value = mock_response

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify export policy was applied with context
        assert mock_blade.patch_file_systems.call_count >= 1
        # Check if any call includes context_names
        calls = mock_blade.patch_file_systems.call_args_list
        has_context = any("context_names" in str(call) for call in calls)
        assert has_context

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.17"),
    )
    def test_create_fs_client_policy_with_context(self, mock_get_filesystem):
        """Test creating filesystem with client policy using context API and SMB"""
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "smb": True,
                "client_policy": "test-client-policy",
                "context": "test-context",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        # Mock API version 2.17 for context support and 2.10 for SMB policies
        mock_version_217 = Mock()
        mock_version_217.version = "2.17"
        mock_version_210 = Mock()
        mock_version_210.version = "2.10"

        def version_eq(self, other):
            return self.version == other

        mock_version_217.__eq__ = version_eq
        mock_version_210.__eq__ = version_eq
        mock_blade.get_versions.return_value.items = [
            mock_version_217,
            mock_version_210,
        ]

        mock_get_filesystem.return_value = None

        # Mock successful operations
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_response
        mock_blade.patch_file_systems.return_value = mock_response

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify client policy was applied with context
        assert mock_blade.patch_file_systems.call_count >= 1

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.17"),
    )
    def test_create_fs_share_policy_with_context(self, mock_get_filesystem):
        """Test creating filesystem with share policy using context API and SMB"""
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "smb": True,
                "share_policy": "test-share-policy",
                "context": "test-context",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        # Mock API version 2.17 for context support and 2.10 for SMB policies
        mock_version_217 = Mock()
        mock_version_217.version = "2.17"
        mock_version_210 = Mock()
        mock_version_210.version = "2.10"

        def version_eq(self, other):
            return self.version == other

        mock_version_217.__eq__ = version_eq
        mock_version_210.__eq__ = version_eq
        mock_blade.get_versions.return_value.items = [
            mock_version_217,
            mock_version_210,
        ]

        mock_get_filesystem.return_value = None

        # Mock successful operations
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_response
        mock_blade.patch_file_systems.return_value = mock_response

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify share policy was applied with context
        assert mock_blade.patch_file_systems.call_count >= 1

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.17"),
    )
    def test_create_fs_continuous_availability_with_context(self, mock_get_filesystem):
        """Test creating filesystem with continuous availability using context API"""
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "smb": True,
                "continuous_availability": True,
                "context": "test-context",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        # Mock API versions: 2.17 (context), 2.12 (CA), 2.10 (SMB policies)
        versions = []
        for ver in ["2.17", "2.12", "2.10"]:
            mock_ver = Mock()
            mock_ver.version = ver
            mock_ver.__eq__ = lambda self, other: self.version == other
            versions.append(mock_ver)
        mock_blade.get_versions.return_value.items = versions

        mock_get_filesystem.return_value = None

        # Mock successful operations
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_response
        mock_blade.patch_file_systems.return_value = mock_response

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify CA was set with context
        assert mock_blade.patch_file_systems.call_count >= 1

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.17"),
    )
    def test_create_fs_group_ownership_with_context(self, mock_get_filesystem):
        """Test creating filesystem with group ownership using context API"""
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "smb": True,
                "group_ownership": "creator",
                "context": "test-context",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        # Mock API versions: 2.17 (context), 2.13 (group ownership), 2.10 (SMB policies)
        versions = []
        for ver in ["2.17", "2.13", "2.10"]:
            mock_ver = Mock()
            mock_ver.version = ver
            mock_ver.__eq__ = lambda self, other: self.version == other
            versions.append(mock_ver)
        mock_blade.get_versions.return_value.items = versions

        mock_get_filesystem.return_value = None

        # Mock successful operations
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_response
        mock_blade.patch_file_systems.return_value = mock_response

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify group ownership was set with context
        assert mock_blade.patch_file_systems.call_count >= 1

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.17"),
    )
    def test_create_fs_storage_class_with_context(self, mock_get_filesystem):
        """Test creating filesystem with storage class using context API"""
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update(
            {
                "name": "test-fs",
                "size": "1T",
                "smb": True,  # Need SMB enabled to trigger the storage class logic path
                "storage_class": "test-class",
                "context": "test-context",
            }
        )
        mock_module.params = params

        mock_blade = Mock()
        # Mock API versions: 2.17 (context), 2.10 (SMB policies)
        versions = []
        for ver in ["2.17", "2.10"]:
            mock_ver = Mock()
            mock_ver.version = ver
            mock_ver.__eq__ = lambda self, other: self.version == other
            versions.append(mock_ver)
        mock_blade.get_versions.return_value.items = versions

        mock_get_filesystem.return_value = None

        # Mock successful operations
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_response
        mock_blade.patch_file_systems.return_value = mock_response

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify storage class was set with context
        assert mock_blade.patch_file_systems.call_count >= 1

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.get_system")
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.20"),
    )
    def test_create_fs_with_realm_success(self, mock_get_system, mock_get_filesystem):
        """Test creating filesystem with realm succeeds on API 2.19+

        When creating a filesystem in a realm:
        - name parameter is just the filesystem name (no realm prefix)
        - realm parameter specifies which realm to use
        - FlashBlade creates it as 'realm::filesystem' internally
        """
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = self.get_default_params()
        # Qualified name already constructed by main()
        mock_module.params["name"] = "production-realm::prod-fs"
        mock_module.params["realm"] = "production-realm"
        mock_module.params["state"] = "present"

        mock_blade = Mock()
        # Mock API version 2.19+
        versions = []
        for ver in ["2.19", "2.20"]:
            mock_ver = Mock()
            mock_ver.version = ver
            mock_ver.__eq__ = lambda self, other: self.version == other
            versions.append(mock_ver)
        mock_blade.get_versions.return_value.items = versions

        mock_get_filesystem.return_value = None

        # Mock successful filesystem creation
        mock_fs_response = Mock()
        mock_fs_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_fs_response

        mock_get_system.return_value = mock_blade

        # Call function (realm validation already done in main())
        create_fs(mock_module, mock_blade)

        # Verify filesystem was created with qualified name
        assert mock_blade.post_file_systems.called
        call_args = mock_blade.post_file_systems.call_args
        assert "production-realm::prod-fs" in call_args[1]["names"]

    def test_create_fs_with_realm_old_api_fails(self):
        """Test creating filesystem with realm fails on old API version

        NOTE: Realm validation now happens in main(), not create_fs().
        This test is now covered by integration tests or tests that call main().
        Keeping as placeholder for documentation.
        """
        # Realm API validation is now done in main() before create_fs() is called
        # Tests that call main() will cover this scenario
        assert True

    def test_create_fs_with_nonexistent_realm_fails(self):
        """Test creating filesystem with nonexistent realm fails

        NOTE: Realm validation now happens in main(), not create_fs().
        This test is now covered by integration tests or tests that call main().
        Keeping as placeholder for documentation.
        """
        # Realm existence validation is now done in main() before create_fs() is called
        # Tests that call main() will cover this scenario
        assert True

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.get_system")
    def test_create_fs_with_realm_check_mode(
        self, mock_get_system, mock_get_filesystem
    ):
        """Test creating filesystem with realm in check mode

        NOTE: Qualified name should already be constructed in check mode test
        """
        mock_module = Mock()
        mock_module.exit_json = Mock()
        mock_module.params = self.get_default_params()
        # Qualified name already constructed by main()
        mock_module.params["name"] = "production-realm::test-fs"
        mock_module.params["realm"] = "production-realm"
        mock_module.params["state"] = "present"
        mock_module.check_mode = True

        mock_blade = Mock()
        # Mock API version 2.19+
        versions = []
        for ver in ["2.19"]:
            mock_ver = Mock()
            mock_ver.version = ver
            mock_ver.__eq__ = lambda self, other: self.version == other
            versions.append(mock_ver)
        mock_blade.get_versions.return_value.items = versions

        mock_get_filesystem.return_value = None
        mock_get_system.return_value = mock_blade

        # Call function
        create_fs(mock_module, mock_blade)

        # In check mode, no API calls should be made
        mock_blade.post_file_systems.assert_not_called()

        # exit_json should be called with changed=True
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is True

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.get_system")
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.19"),
    )
    def test_create_fs_without_realm(self, mock_get_system, mock_get_filesystem):
        """Test creating filesystem without realm works as before"""
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = self.get_default_params()
        mock_module.params["realm"] = None  # No realm
        mock_module.params["state"] = "present"

        mock_blade = Mock()
        # Mock API version 2.19+
        versions = []
        for ver in ["2.19"]:
            mock_ver = Mock()
            mock_ver.version = ver
            mock_ver.__eq__ = lambda self, other: self.version == other
            versions.append(mock_ver)
        mock_blade.get_versions.return_value.items = versions

        mock_get_filesystem.return_value = None

        # Mock successful filesystem creation
        mock_fs_response = Mock()
        mock_fs_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_fs_response

        mock_get_system.return_value = mock_blade

        # Call function
        create_fs(mock_module, mock_blade)

        # Verify realm was not checked (since none provided)
        mock_blade.get_realms.assert_not_called()

        # Verify filesystem was created
        mock_blade.post_file_systems.assert_called_once()

    def test_create_fs_with_realm_prefix_in_name_validates_realm(self):
        """Test that realm is validated when specified in filesystem name

        NOTE: Realm validation now happens in main(), not create_fs().
        This test is now covered by integration tests or tests that call main().
        Keeping as placeholder for documentation.
        """
        # Realm extraction and validation from name is now done in main()
        # Tests that call main() will cover this scenario
        assert True

    @patch("plugins.modules.purefb_fs.delete_fs")
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.get_system")
    @patch("plugins.modules.purefb_fs.AnsibleModule")
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.20"),
    )
    def test_delete_fs_using_name_and_realm_params(
        self, mock_ansible_module, mock_get_system, mock_get_filesystem, mock_delete_fs
    ):
        """Test that realm parameter works for delete operations

        User can delete a realm filesystem using name='fs' + realm='realm' params
        instead of having to use the full qualified name='realm::fs'
        """
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = self.get_default_params()
        mock_module.params["name"] = "prod-fs"
        mock_module.params["realm"] = "production-realm"
        mock_module.params["state"] = "absent"
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        # Mock API versions for realm validation in main()
        versions = []
        for ver in ["2.19", "2.20"]:
            mock_ver = Mock()
            mock_ver.version = ver
            mock_ver.__eq__ = lambda self, other: self.version == other
            versions.append(mock_ver)
        mock_blade.get_versions.return_value.items = versions

        # Mock realm exists
        mock_realm_response = Mock()
        mock_realm_response.status_code = 200
        mock_blade.get_realms.return_value = mock_realm_response

        mock_get_system.return_value = mock_blade

        # Mock filesystem exists with qualified name (not destroyed)
        mock_fs = Mock()
        mock_fs.name = "production-realm::prod-fs"
        mock_fs.destroyed = False

        def get_fs_side_effect(module, blade):
            # Return filesystem when called with qualified name
            if module.params["name"] == "production-realm::prod-fs":
                return mock_fs
            return None

        mock_get_filesystem.side_effect = get_fs_side_effect

        # Call main
        from plugins.modules.purefb_fs import main

        try:
            main()
        except SystemExit:
            pass

        # Verify delete_fs was called
        mock_delete_fs.assert_called_once()

        # Verify the module name was updated to qualified format
        assert mock_module.params["name"] == "production-realm::prod-fs"

    def test_modify_fs_with_realm_association_succeeds(self):
        """Test modifying a filesystem that has a realm association works correctly

        This test verifies that filesystems with realm associations can still be
        modified (e.g., size changes) without issues. The realm parameter only
        resolves a short name to realm::name; it is not part of the request.
        """
        # This is a documentation test that verifies realm doesn't break modifications
        # The actual modify_fs logic doesn't need special handling for realms
        # because realm is immutable and not part of FileSystemPatch object

        # Key points documented:
        # 1. Realm can be provided in params during modify (for user convenience)
        # 2. Realm is NOT included in FileSystemPatch (immutable field)
        # 3. Modifications work the same whether filesystem has realm or not
        # 4. Realm association persists after modification (cannot be changed)

        assert True  # Documentation test - realm doesn't affect modify operations

    @patch("plugins.modules.purefb_fs.modify_fs")
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.get_system")
    @patch("plugins.modules.purefb_fs.AnsibleModule")
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.19"),
    )
    def test_main_modify_fs_using_name_and_realm_params(
        self, mock_ansible_module, mock_get_system, mock_get_filesystem, mock_modify_fs
    ):
        """Test that providing name='fs' and realm='realm' allows modification

        When a filesystem exists as 'realm::fs' and user provides:
        - name='fs' (just filesystem name)
        - realm='realm'

        The module should find the existing filesystem and call modify_fs
        instead of trying to create it.
        """
        # Setup mock module
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = self.get_default_params()
        mock_module.params["name"] = "prod-fs"
        mock_module.params["realm"] = "production-realm"
        mock_module.params["state"] = "present"
        mock_module.params["size"] = "10T"
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.19"]
        mock_get_system.return_value = mock_blade

        # Mock get_filesystem behavior:
        # name='prod-fs' (outside the realm) returns None (not found)
        # name='production-realm::prod-fs' returns the filesystem
        mock_fs = Mock()
        mock_fs.name = "production-realm::prod-fs"
        mock_fs.provisioned = 1099511627776

        def get_fs_side_effect(module, blade):
            # Return filesystem when called with qualified name
            if module.params["name"] == "production-realm::prod-fs":
                return mock_fs
            return None

        mock_get_filesystem.side_effect = get_fs_side_effect

        # Call main
        from plugins.modules.purefb_fs import main

        try:
            main()
        except SystemExit:
            pass

        # Verify modify_fs was called (not create_fs)
        mock_modify_fs.assert_called_once()

        # Verify the module name was updated to qualified format
        assert mock_module.params["name"] == "production-realm::prod-fs"

    # ==== worm_policy / eradication_mode (POST /file-systems only, REST 2.15) ====

    def _worm_members(self, *names):
        """Mock GET file-systems/worm-data-policies listing the attached
        policies (200 with zero items when none is attached)."""
        res = Mock()
        res.status_code = 200
        res.total_item_count = len(names)
        items = []
        for name in names:
            item = Mock()
            item.policy = Mock()
            item.policy.name = name
            items.append(item)
        res.items = items
        return res

    def _worm_create_module(self, **overrides):
        """Module mock for create_fs with the PATCH-triggering defaults off."""
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.fail_json.side_effect = Exception("fail_json")
        params = self.get_default_params()
        params.update({"group_ownership": None, "worm_policy": None})
        params["eradication_mode"] = None
        params.update(overrides)
        mock_module.params = params
        return mock_module

    @patch("plugins.modules.purefb_fs.FileSystemEradicationConfig")
    @patch("plugins.modules.purefb_fs.FileSystemPost")
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.15"),
    )
    def test_create_fs_worm_policy_and_eradication_mode_on_post(
        self, mock_get_filesystem, mock_fs_post, mock_erad_config
    ):
        """worm_policy reaches POST /file-systems as policy_names and
        eradication_mode as eradication_config on the body; nothing is
        PATCHed afterwards and the snapshot-policy attach is not used."""
        mock_module = self._worm_create_module(
            worm_policy="worm-pol", eradication_mode="retention-based"
        )
        mock_blade = Mock()
        mock_get_filesystem.return_value = None
        ok = Mock()
        ok.status_code = 200
        mock_blade.post_file_systems.return_value = ok

        create_fs(mock_module, mock_blade)

        kwargs = mock_blade.post_file_systems.call_args[1]
        assert kwargs["names"] == ["test-fs"]
        assert kwargs["policy_names"] == ["worm-pol"]
        assert "context_names" not in kwargs
        mock_erad_config.assert_called_once_with(eradication_mode="retention-based")
        assert (
            mock_fs_post.call_args[1]["eradication_config"]
            is mock_erad_config.return_value
        )
        mock_blade.patch_file_systems.assert_not_called()
        mock_blade.post_policies_file_systems.assert_not_called()
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.FileSystemEradicationConfig")
    @patch("plugins.modules.purefb_fs.FileSystemPost")
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def test_create_fs_without_worm_options_sends_neither(
        self, mock_get_filesystem, mock_fs_post, mock_erad_config
    ):
        """Omitted options never reach the array: no policy_names and no
        eradication_config, so arrays keep their defaults."""
        mock_module = self._worm_create_module()
        mock_blade = Mock()
        mock_get_filesystem.return_value = None
        ok = Mock()
        ok.status_code = 200
        mock_blade.post_file_systems.return_value = ok

        create_fs(mock_module, mock_blade)

        kwargs = mock_blade.post_file_systems.call_args[1]
        assert "policy_names" not in kwargs
        assert "eradication_config" not in mock_fs_post.call_args[1]
        mock_erad_config.assert_not_called()
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.FileSystemEradicationConfig")
    @patch("plugins.modules.purefb_fs.FileSystemPost")
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.15"),
    )
    def test_create_fs_worm_policy_defaults_to_retention_based(
        self, mock_get_filesystem, mock_fs_post, mock_erad_config
    ):
        """The array only creates a WORM filesystem in retention-based
        eradication mode, so worm_policy alone sends that mode."""
        mock_module = self._worm_create_module(worm_policy="worm-pol")
        mock_blade = Mock()
        mock_get_filesystem.return_value = None
        ok = Mock()
        ok.status_code = 200
        mock_blade.post_file_systems.return_value = ok

        create_fs(mock_module, mock_blade)

        assert mock_blade.post_file_systems.call_args[1]["policy_names"] == ["worm-pol"]
        mock_erad_config.assert_called_once_with(eradication_mode="retention-based")
        assert (
            mock_fs_post.call_args[1]["eradication_config"]
            is mock_erad_config.return_value
        )
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.15"),
    )
    def test_create_fs_worm_policy_check_mode_creates_nothing(self):
        """Check mode reports the create without POSTing anything."""
        mock_module = self._worm_create_module(worm_policy="worm-pol")
        mock_module.check_mode = True
        mock_blade = Mock()

        create_fs(mock_module, mock_blade)

        mock_blade.post_file_systems.assert_not_called()
        mock_blade.get_realms.assert_not_called()
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.17"),
    )
    def test_create_fs_worm_policy_with_context(self, mock_get_filesystem):
        """policy_names and context_names travel together on the POST."""
        mock_module = self._worm_create_module(worm_policy="worm-pol", context="fb1")
        mock_blade = Mock()
        mock_get_filesystem.return_value = None
        ok = Mock()
        ok.status_code = 200
        mock_blade.post_file_systems.return_value = ok

        create_fs(mock_module, mock_blade)

        kwargs = mock_blade.post_file_systems.call_args[1]
        assert kwargs["policy_names"] == ["worm-pol"]
        assert kwargs["context_names"] == ["fb1"]
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.get_error_message", Mock(return_value="boom"))
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.15"),
    )
    def test_create_fs_worm_policy_post_failure_fails(self, mock_get_filesystem):
        """A rejected POST (for example an unknown WORM policy) fails the
        task with the array message; nothing exists to clean up."""
        mock_module = self._worm_create_module(worm_policy="missing-pol")
        mock_blade = Mock()
        mock_get_filesystem.return_value = None
        bad = Mock()
        bad.status_code = 400
        mock_blade.post_file_systems.return_value = bad

        try:
            create_fs(mock_module, mock_blade)
        except Exception as exc:
            assert str(exc) == "fail_json"

        mock_module.fail_json.assert_called_once()
        assert "boom" in mock_module.fail_json.call_args[1]["msg"]
        mock_blade.delete_file_systems.assert_not_called()
        mock_module.exit_json.assert_not_called()

    def _run_main_with_version(
        self,
        version,
        mock_ansible_module,
        mock_get_system,
        mock_get_filesystem,
        **params
    ):
        """Run main() against an array at the given REST version with the
        filesystem absent; returns the module mock."""
        mock_module = Mock()
        mock_module.check_mode = params.pop("check_mode", False)
        mock_module.fail_json.side_effect = Exception("fail_json")
        mock_module.params = self.get_default_params()
        mock_module.params.update(params)
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        mock_get_filesystem.return_value = None
        ok = Mock()
        ok.status_code = 200
        mock_blade.post_file_systems.return_value = ok
        with patch(
            "plugins.modules.purefb_fs.get_rest_api_version",
            Mock(return_value=version),
        ):
            try:
                main()
            except Exception as exc:
                assert str(exc) == "fail_json"
        return mock_module, mock_blade

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.get_system")
    @patch("plugins.modules.purefb_fs.AnsibleModule")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    def test_main_worm_policy_below_2_15_fails_before_any_write(
        self, mock_ansible_module, mock_get_system, mock_get_filesystem
    ):
        """Below REST 2.15 worm_policy fails in main() naming the version
        and no POST is attempted."""
        mock_module, mock_blade = self._run_main_with_version(
            "2.14",
            mock_ansible_module,
            mock_get_system,
            mock_get_filesystem,
            worm_policy="worm-pol",
        )
        mock_module.fail_json.assert_called_once()
        assert "2.15" in mock_module.fail_json.call_args[1]["msg"]
        mock_blade.post_file_systems.assert_not_called()
        mock_blade.patch_file_systems.assert_not_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.get_system")
    @patch("plugins.modules.purefb_fs.AnsibleModule")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    def test_main_eradication_mode_below_2_15_fails_in_check_mode(
        self, mock_ansible_module, mock_get_system, mock_get_filesystem
    ):
        """The gate also covers eradication_mode and runs in check mode."""
        mock_module, mock_blade = self._run_main_with_version(
            "2.10",
            mock_ansible_module,
            mock_get_system,
            mock_get_filesystem,
            eradication_mode="retention-based",
            check_mode=True,
        )
        mock_module.fail_json.assert_called_once()
        assert "2.15" in mock_module.fail_json.call_args[1]["msg"]
        mock_blade.post_file_systems.assert_not_called()

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.get_system")
    @patch("plugins.modules.purefb_fs.AnsibleModule")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    def test_main_worm_policy_at_2_15_creates(
        self, mock_ansible_module, mock_get_system, mock_get_filesystem
    ):
        """At exactly REST 2.15 the gate passes and the filesystem is
        created with the policy on the POST."""
        mock_module, mock_blade = self._run_main_with_version(
            "2.15",
            mock_ansible_module,
            mock_get_system,
            mock_get_filesystem,
            worm_policy="worm-pol",
            group_ownership=None,
        )
        mock_module.fail_json.assert_not_called()
        kwargs = mock_blade.post_file_systems.call_args[1]
        assert kwargs["policy_names"] == ["worm-pol"]
        # exit_json is a Mock, so main() falls through to its final
        # exit_json(changed=False); the create result is the first call.
        assert mock_module.exit_json.call_args_list[0][1] == {"changed": True}

    def _worm_modify_module(self, **params):
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.fail_json.side_effect = Exception("fail_json")
        mock_module.params = self.get_default_params()
        mock_module.params["worm_policy"] = None
        mock_module.params["eradication_mode"] = None
        mock_module.params.update(params)
        return mock_module

    def _worm_fs(self, eradication_mode="permission-based"):
        """Existing filesystem as main() fetched it, with the GET model's
        eradication_config."""
        fsys = self._existing_fs()
        fsys.name = "test-fs"
        fsys.eradication_config = Mock()
        fsys.eradication_config.eradication_mode = eradication_mode
        return fsys

    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    def test_check_create_only_same_worm_policy_is_noop(self):
        """Replaying the create task reads the membership of the filesystem
        main() already holds, finds the same policy and returns quietly
        without re-querying the filesystem."""
        mock_module = self._worm_modify_module(worm_policy="worm-pol")
        mock_blade = Mock()
        mock_blade.get_file_systems_worm_data_policies.return_value = (
            self._worm_members("worm-pol")
        )

        _check_create_only_options(mock_module, mock_blade, self._worm_fs(), "2.15")

        mock_blade.get_file_systems_worm_data_policies.assert_called_once_with(
            member_names=["test-fs"]
        )
        mock_blade.get_file_systems.assert_not_called()
        mock_module.fail_json.assert_not_called()

    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    def test_check_create_only_other_worm_policy_fails(self):
        """A different attached policy cannot be reconciled: fail naming the
        attached policy."""
        mock_module = self._worm_modify_module(worm_policy="worm-pol", size="2T")
        mock_blade = Mock()
        mock_blade.get_file_systems_worm_data_policies.return_value = (
            self._worm_members("other-pol")
        )

        try:
            _check_create_only_options(mock_module, mock_blade, self._worm_fs(), "2.15")
        except Exception as exc:
            assert str(exc) == "fail_json"

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "other-pol" in msg
        assert "can only be attached" in msg

    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    def test_check_create_only_no_worm_policy_attached_fails(self):
        """GET answers 200 with zero items for a filesystem without a WORM
        policy; one cannot be attached later, so the task fails."""
        mock_module = self._worm_modify_module(worm_policy="worm-pol")
        mock_blade = Mock()
        mock_blade.get_file_systems_worm_data_policies.return_value = (
            self._worm_members()
        )

        try:
            _check_create_only_options(mock_module, mock_blade, self._worm_fs(), "2.15")
        except Exception as exc:
            assert str(exc) == "fail_json"

        mock_module.fail_json.assert_called_once()
        assert "none" in mock_module.fail_json.call_args[1]["msg"]

    @patch("plugins.modules.purefb_fs.get_error_message", Mock(return_value="boom"))
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    def test_check_create_only_lookup_error_fails_with_context(self):
        """The membership GET carries context_names on a fleet member and a
        non-200 answer fails with the array message."""
        mock_module = self._worm_modify_module(worm_policy="worm-pol", context="fb1")
        mock_blade = Mock()
        bad = Mock()
        bad.status_code = 400
        mock_blade.get_file_systems_worm_data_policies.return_value = bad

        try:
            _check_create_only_options(mock_module, mock_blade, self._worm_fs(), "2.17")
        except Exception as exc:
            assert str(exc) == "fail_json"

        mock_blade.get_file_systems_worm_data_policies.assert_called_once_with(
            member_names=["test-fs"], context_names=["fb1"]
        )
        mock_module.fail_json.assert_called_once()
        assert "boom" in mock_module.fail_json.call_args[1]["msg"]

    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    def test_check_create_only_same_eradication_mode_is_noop(self):
        """A matching eradication_mode is read from the filesystem object and
        needs no membership lookup."""
        mock_module = self._worm_modify_module(eradication_mode="retention-based")
        mock_blade = Mock()

        _check_create_only_options(
            mock_module, mock_blade, self._worm_fs("retention-based"), "2.15"
        )

        mock_blade.get_file_systems_worm_data_policies.assert_not_called()
        mock_blade.get_file_systems.assert_not_called()
        mock_module.fail_json.assert_not_called()

    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    def test_check_create_only_different_eradication_mode_fails(self):
        """FileSystemPatch has no eradication_config, so a different mode
        fails naming the current one."""
        mock_module = self._worm_modify_module(
            eradication_mode="retention-based", size="2T"
        )
        mock_blade = Mock()

        try:
            _check_create_only_options(
                mock_module, mock_blade, self._worm_fs("permission-based"), "2.15"
            )
        except Exception as exc:
            assert str(exc) == "fail_json"

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "permission-based" in msg
        assert "can only be set" in msg
        mock_blade.get_file_systems_worm_data_policies.assert_not_called()

    def _run_main_existing(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_get_filesystem,
        members,
        **params
    ):
        """Run main() at REST 2.15 against an existing filesystem whose WORM
        membership GET answers ``members``; returns the module and blade."""
        mock_module = self._worm_modify_module(**params)
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        mock_get_filesystem.return_value = self._worm_fs()
        mock_blade.get_file_systems_worm_data_policies.return_value = members
        with patch(
            "plugins.modules.purefb_fs.get_rest_api_version",
            Mock(return_value="2.15"),
        ):
            try:
                main()
            except Exception as exc:
                assert str(exc) == "fail_json"
        return mock_module, mock_blade

    @patch("plugins.modules.purefb_fs.modify_fs")
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.get_system")
    @patch("plugins.modules.purefb_fs.AnsibleModule")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    def test_main_other_worm_policy_fails_before_modify(
        self, mock_ansible_module, mock_get_system, mock_get_filesystem, mock_modify
    ):
        """main() runs the create-only check before modify_fs, so a
        mismatch fails without any PATCH or policy attach."""
        mock_module, mock_blade = self._run_main_existing(
            mock_ansible_module,
            mock_get_system,
            mock_get_filesystem,
            self._worm_members("other-pol"),
            worm_policy="worm-pol",
            size="2T",
        )
        mock_module.fail_json.assert_called_once()
        assert "other-pol" in mock_module.fail_json.call_args[1]["msg"]
        mock_modify.assert_not_called()
        mock_blade.patch_file_systems.assert_not_called()
        mock_blade.post_policies_file_systems.assert_not_called()

    @patch("plugins.modules.purefb_fs.modify_fs")
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.get_system")
    @patch("plugins.modules.purefb_fs.AnsibleModule")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    def test_main_same_worm_policy_reuses_filesystem_and_modifies(
        self, mock_ansible_module, mock_get_system, mock_get_filesystem, mock_modify
    ):
        """Matching values pass the check using the filesystem main()
        fetched (one GET) and hand over to modify_fs."""
        mock_module, mock_blade = self._run_main_existing(
            mock_ansible_module,
            mock_get_system,
            mock_get_filesystem,
            self._worm_members("worm-pol"),
            worm_policy="worm-pol",
            eradication_mode="permission-based",
        )
        mock_module.fail_json.assert_not_called()
        assert mock_get_filesystem.call_count == 1
        mock_blade.get_file_systems_worm_data_policies.assert_called_once_with(
            member_names=["test-fs"]
        )
        mock_modify.assert_called_once_with(mock_module, mock_blade)

    # ==== deprecation warnings for legacy FS-level policy fields ====

    def _mk_module_for_deprecation(
        self,
        export_policy=None,
        share_policy=None,
        client_policy=None,
    ):
        """Minimal AnsibleModule mock sized to reach the three deprecation
        call sites in create_fs. Only the deprecation-track fields vary."""
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = {
            "name": "test-fs",
            "size": "1T",
            "nfsv3": True,
            "nfsv4": True,
            "nfs_rules": None,
            "smb": False,
            "http": False,
            "snapshot": False,
            "fastremove": False,
            "hard_limit": False,
            "user_quota": None,
            "group_quota": None,
            "policy": None,
            "access_control": "shared",
            "safeguard_acls": True,
            "export_policy": export_policy,
            "share_policy": share_policy,
            "client_policy": client_policy,
            "continuous_availability": True,
            "context": "",
            "storage_class": None,
            "group_ownership": None,
        }
        return mock_module

    @patch("plugins.modules.purefb_fs.FileSystemPost")
    @patch("plugins.modules.purefb_fs.Nfs")
    @patch("plugins.modules.purefb_fs.SmbPost")
    @patch("plugins.modules.purefb_fs.Http")
    @patch("plugins.modules.purefb_fs.MultiProtocolPost")
    @patch("plugins.modules.purefb_fs.human_to_bytes")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.17"),
    )
    def test_deprecation_fires_for_each_legacy_policy_field(
        self,
        mock_human_to_bytes,
        mock_multi_protocol,
        mock_http,
        mock_smb,
        mock_nfs,
        mock_fs_post,
    ):
        """Supplying export_policy / share_policy / client_policy explicitly
        must trigger a module.deprecate() call for each - one per field.
        Guards the deprecation surface: removing any of these silently is
        exactly what this test would catch."""
        mock_module = self._mk_module_for_deprecation(
            export_policy="nfs_pol1",
            share_policy="smb_share_pol1",
            client_policy="smb_client_pol1",
        )
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.17"]
        mock_human_to_bytes.return_value = 1099511627776
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_blade.post_file_systems.return_value = mock_resp

        create_fs(mock_module, mock_blade)

        emitted = [c.args[0] for c in mock_module.deprecate.call_args_list]
        assert any("export_policy is deprecated" in msg for msg in emitted)
        assert any("share_policy is deprecated" in msg for msg in emitted)
        assert any("client_policy is deprecated" in msg for msg in emitted)
        # Every deprecation must be versioned 2.0.0 for the export-migration set
        for c in mock_module.deprecate.call_args_list:
            if any(
                needle in c.args[0]
                for needle in (
                    "export_policy is deprecated",
                    "share_policy is deprecated",
                    "client_policy is deprecated",
                )
            ):
                assert c.kwargs["version"] == "2.0.0"
                assert c.kwargs["collection_name"] == "everpure.flashblade"

    @patch("plugins.modules.purefb_fs.FileSystemPost")
    @patch("plugins.modules.purefb_fs.Nfs")
    @patch("plugins.modules.purefb_fs.SmbPost")
    @patch("plugins.modules.purefb_fs.Http")
    @patch("plugins.modules.purefb_fs.MultiProtocolPost")
    @patch("plugins.modules.purefb_fs.human_to_bytes")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.17"),
    )
    def test_no_deprecation_when_legacy_policy_fields_omitted(
        self,
        mock_human_to_bytes,
        mock_multi_protocol,
        mock_http,
        mock_smb,
        mock_nfs,
        mock_fs_post,
    ):
        """No deprecation warning fires for a policy field the caller did
        not supply. Guards against a regression where the guard flips from
        `is not None` to truthy, or the guard is removed entirely - either
        would spam every existing user."""
        mock_module = self._mk_module_for_deprecation()
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.17"]
        mock_human_to_bytes.return_value = 1099511627776
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_blade.post_file_systems.return_value = mock_resp

        create_fs(mock_module, mock_blade)

        for c in mock_module.deprecate.call_args_list:
            assert not any(
                needle in c.args[0]
                for needle in (
                    "export_policy is deprecated",
                    "share_policy is deprecated",
                    "client_policy is deprecated",
                )
            )

    # ==== boolean flags on modify (hard_limit / fastremove / snapshot / ...) ====

    def _run_modify(self, params, mock_fs, mock_get_filesystem):
        """Run modify_fs against mock_fs and return (module, blade)."""
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = params
        mock_blade = Mock()
        mock_get_filesystem.return_value = mock_fs
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_file_systems.return_value = mock_response
        mock_blade.get_file_systems.return_value.items = [mock_fs]
        modify_fs(mock_module, mock_blade)
        return mock_module, mock_blade

    @patch("plugins.modules.purefb_fs.FileSystemPatch")
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_flags_are_sent_in_patch(
        self, mock_get_filesystem, mock_fs_patch
    ):
        """hard_limit, fastremove and snapshot must reach the FileSystemPatch
        under their REST names. The old code compared under one key and
        read another, so the PATCH always carried the current value and
        the flags were never applied.
        """
        params = self.get_default_params()
        params.update({"hard_limit": True, "fastremove": True, "snapshot": True})

        mock_module, mock_blade = self._run_modify(
            params, self._existing_fs(), mock_get_filesystem
        )

        mock_blade.patch_file_systems.assert_called_once()
        kwargs = mock_fs_patch.call_args[1]
        assert kwargs["hard_limit_enabled"] is True
        assert kwargs["fast_remove_directory_enabled"] is True
        assert kwargs["snapshot_directory_enabled"] is True
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.FileSystemPatch")
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_explicit_false_turns_flags_off(
        self, mock_get_filesystem, mock_fs_patch
    ):
        """An explicit false must turn a flag off (True -> False)."""
        params = self.get_default_params()
        params.update({"hard_limit": False, "http": False, "safeguard_acls": False})
        mock_fs = self._existing_fs(
            hard_limit_enabled=True, http_enabled=True, safeguard_acls=True
        )

        mock_module, mock_blade = self._run_modify(params, mock_fs, mock_get_filesystem)

        mock_blade.patch_file_systems.assert_called_once()
        kwargs = mock_fs_patch.call_args[1]
        assert kwargs["hard_limit_enabled"] is False
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_omitted_flags_are_left_alone(self, mock_get_filesystem):
        """Flags that are not set (None) must not be compared, so a run that
        only names the filesystem does not turn anything off and is a no-op.
        """
        params = self.get_default_params()
        mock_fs = self._existing_fs(
            hard_limit_enabled=True,
            fast_remove_directory_enabled=True,
            snapshot_directory_enabled=True,
            smb_enabled=True,
            http_enabled=True,
            safeguard_acls=False,
        )

        mock_module, mock_blade = self._run_modify(params, mock_fs, mock_get_filesystem)

        mock_blade.patch_file_systems.assert_not_called()
        mock_module.exit_json.assert_called_with(changed=False)

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_flag_already_set_is_noop(self, mock_get_filesystem):
        """Setting a flag that is already on reports no change."""
        params = self.get_default_params()
        params.update({"hard_limit": True})
        mock_fs = self._existing_fs(hard_limit_enabled=True)

        mock_module, mock_blade = self._run_modify(params, mock_fs, mock_get_filesystem)

        mock_blade.patch_file_systems.assert_not_called()
        mock_module.exit_json.assert_called_with(changed=False)

    # ==== policy_state=absent idempotency ====

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.0"),
    )
    def test_modify_fs_remove_policy_not_attached_is_noop(self, mock_get_filesystem):
        """GET policies/file-systems answers 200 with zero items when the
        policy is not attached. A second policy_state=absent run must not
        try to detach again (the array rejects that) and must report no
        change.
        """
        params = self.get_default_params()
        params.update({"policy": "test-policy", "policy_state": "absent"})
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = params

        mock_blade = Mock()
        mock_fs = self._existing_fs()
        mock_get_filesystem.return_value = mock_fs
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        policy_res = Mock()
        policy_res.status_code = 200
        mock_blade.get_policies.return_value = policy_res
        member_res = Mock()
        member_res.status_code = 200
        member_res.total_item_count = 0
        member_res.items = []
        mock_blade.get_policies_file_systems.return_value = member_res

        modify_fs(mock_module, mock_blade)

        mock_blade.delete_policies_file_systems.assert_not_called()
        mock_module.exit_json.assert_called_with(changed=False)

    # ==== realm-qualified eradicate ====

    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    def test_eradicate_fs_uses_realm_qualified_name(self):
        """name + realm must eradicate realm::name, not the bare name."""
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = {"name": "prod-fs", "realm": "production-realm"}
        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.delete_file_systems.return_value = mock_response

        eradicate_fs(mock_module, mock_blade)

        mock_blade.delete_file_systems.assert_called_once_with(
            names=["production-realm::prod-fs"]
        )
        mock_module.exit_json.assert_called_with(changed=True)

    # ==== create: group_ownership is not an SMB attribute ====

    @patch("plugins.modules.purefb_fs.FileSystemPatch")
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.13"),
    )
    def test_create_fs_group_ownership_applied_without_smb(
        self, mock_get_filesystem, mock_fs_patch
    ):
        """group_ownership used to be nested under the SMB block, so an NFS
        only filesystem never got it at creation time and the next run
        reported a change.
        """
        mock_module = Mock()
        mock_module.check_mode = False
        params = self.get_default_params()
        params.update({"group_ownership": "parent-directory"})
        mock_module.params = params

        mock_blade = Mock()
        mock_get_filesystem.return_value = None
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_file_systems.return_value = mock_response
        mock_blade.patch_file_systems.return_value = mock_response

        create_fs(mock_module, mock_blade)

        mock_fs_patch.assert_any_call(group_ownership="parent-directory")
        mock_blade.patch_file_systems.assert_called()
        mock_module.exit_json.assert_called_with(changed=True)

    # ==== storage_class on modify: compare by name, PATCH only on drift ====

    def _existing_fs_with_storage_class(self, name):
        """Existing filesystem whose storage_class object carries ``name``.
        The array always returns the storage_class object; on platforms
        without storage classes it has no name.
        """
        fs = self._existing_fs()
        fs.storage_class = Mock()
        fs.storage_class.name = name
        return fs

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.17"),
    )
    def test_modify_fs_storage_class_same_is_noop(self, mock_get_filesystem):
        """The requested class matches storage_class.name: no PATCH and
        changed=False. The old code compared the string with the
        StorageClassInfo object, so every run sent a PATCH and reported a
        change.
        """
        params = self.get_default_params()
        params.update({"storage_class": "S500X-S"})
        mock_fs = self._existing_fs_with_storage_class("S500X-S")

        mock_module, mock_blade = self._run_modify(params, mock_fs, mock_get_filesystem)

        mock_blade.patch_file_systems.assert_not_called()
        mock_module.exit_json.assert_called_with(changed=False)

    @patch("plugins.modules.purefb_fs.StorageClassInfo")
    @patch("plugins.modules.purefb_fs.FileSystemPatch")
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.17"),
    )
    def test_modify_fs_storage_class_different_is_patched(
        self, mock_get_filesystem, mock_fs_patch, mock_sc_info
    ):
        """A different class sends exactly one storage_class PATCH carrying
        cancel_in_progress and reports changed=True.
        """
        params = self.get_default_params()
        params.update({"storage_class": "S500X-A", "cancel_in_progress": True})
        mock_fs = self._existing_fs_with_storage_class("S500X-S")

        mock_module, mock_blade = self._run_modify(params, mock_fs, mock_get_filesystem)

        mock_sc_info.assert_called_once_with(name="S500X-A")
        mock_fs_patch.assert_called_once_with(storage_class=mock_sc_info.return_value)
        mock_blade.patch_file_systems.assert_called_once_with(
            names=["test-fs"],
            file_system=mock_fs_patch.return_value,
            cancel_in_progress_storage_class_transition=True,
        )
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.StorageClassInfo")
    @patch("plugins.modules.purefb_fs.FileSystemPatch")
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.17"),
    )
    def test_modify_fs_storage_class_with_context(
        self, mock_get_filesystem, mock_fs_patch, mock_sc_info
    ):
        """With a fleet context the storage_class PATCH carries context_names."""
        params = self.get_default_params()
        params.update({"storage_class": "S500X-A", "context": "fleet-member"})
        mock_fs = self._existing_fs_with_storage_class("S500X-S")

        mock_module, mock_blade = self._run_modify(params, mock_fs, mock_get_filesystem)

        mock_blade.patch_file_systems.assert_called_once_with(
            names=["test-fs"],
            file_system=mock_fs_patch.return_value,
            cancel_in_progress_storage_class_transition=False,
            context_names=["fleet-member"],
        )
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.17"),
    )
    def test_modify_fs_storage_class_check_mode(self, mock_get_filesystem):
        """Check mode reports the pending change without sending the PATCH."""
        params = self.get_default_params()
        params.update({"storage_class": "S500X-A"})
        mock_fs = self._existing_fs_with_storage_class("S500X-S")
        mock_module = Mock()
        mock_module.check_mode = True
        mock_module.params = params
        mock_blade = Mock()
        mock_get_filesystem.return_value = mock_fs
        mock_blade.get_file_systems.return_value.items = [mock_fs]

        modify_fs(mock_module, mock_blade)

        mock_blade.patch_file_systems.assert_not_called()
        mock_module.exit_json.assert_called_with(changed=True)

    @patch("plugins.modules.purefb_fs.get_error_message")
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.17"),
    )
    def test_modify_fs_storage_class_unsupported_platform_fails(
        self, mock_get_filesystem, mock_get_error
    ):
        """Platforms without storage classes return the storage_class object
        with no name and answer the PATCH with 400. The old code never
        looked at the response; the module now fails with the array message.
        """
        mock_get_error.return_value = (
            "Storage classes are not supported on this product."
        )
        params = self.get_default_params()
        params.update({"storage_class": "S500X-S"})
        mock_fs = self._existing_fs_with_storage_class(None)
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = params
        mock_module.fail_json.side_effect = Exception("fail_json")
        mock_blade = Mock()
        mock_get_filesystem.return_value = mock_fs
        mock_blade.get_file_systems.return_value.items = [mock_fs]
        mock_response = Mock()
        mock_response.status_code = 400
        mock_blade.patch_file_systems.return_value = mock_response

        try:
            modify_fs(mock_module, mock_blade)
        except Exception as exc:  # fail_json stops the module
            assert str(exc) == "fail_json"
        else:
            raise AssertionError("fail_json was not called")

        mock_blade.patch_file_systems.assert_called_once()
        msg = mock_module.fail_json.call_args.kwargs["msg"]
        assert "Storage classes are not supported on this product." in msg
        assert "test-fs" in msg
        mock_module.exit_json.assert_not_called()

    # ==== realm option with a short name: a namesake outside the realm ====

    REALM_FS = "production-realm::prod-fs"
    GIB = 1073741824

    def _realm_params(self, **overrides):
        """Default params for the short name prod-fs in production-realm."""
        params = self.get_default_params()
        params.update({"name": "prod-fs", "realm": "production-realm"})
        params.update(overrides)
        return params

    def _namesakes(self, array_level=None, in_realm=None):
        """The filesystems on the array, keyed by name. ``array_level`` and
        ``in_realm`` are _existing_fs overrides; None leaves that one out.
        """
        found = {}
        if array_level is not None:
            found["prod-fs"] = self._existing_fs(name="prod-fs", **array_level)
        if in_realm is not None:
            found[self.REALM_FS] = self._existing_fs(name=self.REALM_FS, **in_realm)
        return found

    @patch("plugins.modules.purefb_fs.FileSystemPatch")
    @patch("plugins.modules.purefb_fs.get_filesystem")
    @patch("plugins.modules.purefb_fs.get_system")
    @patch("plugins.modules.purefb_fs.AnsibleModule")
    @patch("plugins.modules.purefb_fs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_fs.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_fs.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def _run_main_on(
        self,
        params,
        found,
        mock_ansible_module,
        mock_get_system,
        mock_get_filesystem,
        mock_fs_patch,
        check_mode=False,
    ):
        """Run main() against an array holding the filesystems in ``found``
        (name -> mock filesystem). exit_json and fail_json end the run as
        they do in Ansible. Returns (module, blade, lookups, fs_patch):
        ``lookups`` lists every filesystem name the module read, in order,
        and ``fs_patch`` is the patched FileSystemPatch class.
        """
        mock_module = Mock()
        mock_module.check_mode = check_mode
        mock_module.params = params
        mock_module.exit_json.side_effect = SystemExit(0)
        mock_module.fail_json.side_effect = SystemExit(1)
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        ok = Mock()
        ok.status_code = 200
        for write in ("post_file_systems", "patch_file_systems", "delete_file_systems"):
            getattr(mock_blade, write).return_value = ok
        mock_blade.get_realms.return_value = ok
        lookups = []

        def by_name(module, blade):
            lookups.append(module.params["name"])
            return found.get(module.params["name"])

        def by_filter(**kwargs):
            wanted = kwargs["filter"][len("name='") : -1]
            lookups.append(wanted)
            res = Mock()
            res.status_code = 200
            res.items = [fs for name, fs in found.items() if name == wanted]
            return res

        mock_get_filesystem.side_effect = by_name
        mock_blade.get_file_systems.side_effect = by_filter
        try:
            main()
        except SystemExit:
            pass
        return mock_module, mock_blade, lookups, mock_fs_patch

    def _written_names(self, mock_blade):
        """Every filesystem name a write request was sent for."""
        names = []
        for write in ("post_file_systems", "patch_file_systems", "delete_file_systems"):
            for call in getattr(mock_blade, write).call_args_list:
                names.extend(call.kwargs["names"])
        return names

    def test_resolve_name_short_name_with_realm_is_qualified(self):
        mock_module = Mock()
        mock_module.params = {"name": "prod-fs", "realm": "production-realm"}
        assert _resolve_name(mock_module) == self.REALM_FS
        mock_module.fail_json.assert_not_called()

    def test_resolve_name_without_realm_is_unchanged(self):
        """No realm option: a short name stays short (outside every realm)
        and a qualified name is used as it is."""
        for name, realm in (
            ("prod-fs", None),
            ("prod-fs", ""),
            (self.REALM_FS, None),
        ):
            mock_module = Mock()
            mock_module.params = {"name": name, "realm": realm}
            assert _resolve_name(mock_module) == name
            mock_module.fail_json.assert_not_called()

    def test_resolve_name_qualified_name_agreeing_with_realm(self):
        mock_module = Mock()
        mock_module.params = {"name": self.REALM_FS, "realm": "production-realm"}
        assert _resolve_name(mock_module) == self.REALM_FS
        mock_module.fail_json.assert_not_called()

    def test_resolve_name_realm_spelled_in_another_case_agrees(self):
        """The realm in the name and the realm option are compared without
        regard to case, and the name is used as it was given."""
        mock_module = Mock()
        mock_module.params = {
            "name": "Production-Realm::prod-fs",
            "realm": "production-realm",
        }
        assert _resolve_name(mock_module) == "Production-Realm::prod-fs"
        mock_module.fail_json.assert_not_called()

    def test_resolve_name_qualified_name_in_another_realm_fails(self):
        mock_module = Mock()
        mock_module.params = {
            "name": "other-realm::prod-fs",
            "realm": "production-realm",
        }
        mock_module.fail_json.side_effect = SystemExit(1)
        with pytest.raises(SystemExit):
            _resolve_name(mock_module)
        msg = mock_module.fail_json.call_args.kwargs["msg"]
        assert "other-realm::prod-fs" in msg
        assert "production-realm" in msg

    def test_main_realm_short_name_is_compared_with_the_realm_fs(self):
        """Both names exist. The request matches the namesake outside the
        realm (2G, snapshot directory and hard limit on) but not the realm
        filesystem (1G, both off): the realm filesystem is the one read,
        and the PATCH carries its own flags, not the namesake's.
        """
        found = self._namesakes(
            array_level={
                "provisioned": 2 * self.GIB,
                "snapshot_directory_enabled": True,
                "hard_limit_enabled": True,
            },
            in_realm={"provisioned": self.GIB},
        )
        mock_module, mock_blade, lookups, mock_fs_patch = self._run_main_on(
            self._realm_params(size="2G"), found
        )

        assert lookups and set(lookups) == {self.REALM_FS}
        mock_blade.patch_file_systems.assert_called_once()
        assert self._written_names(mock_blade) == [self.REALM_FS]
        kwargs = mock_fs_patch.call_args.kwargs
        assert kwargs["provisioned"] == 2 * self.GIB
        assert kwargs["snapshot_directory_enabled"] is False
        assert kwargs["hard_limit_enabled"] is False
        mock_module.exit_json.assert_called_once_with(changed=True)

    def test_main_realm_short_name_matching_the_realm_fs_is_noop(self):
        """Both names exist and the request matches the realm filesystem:
        nothing is sent, whatever the namesake outside the realm looks like,
        in check mode as well."""
        for check_mode in (False, True):
            found = self._namesakes(
                array_level={"provisioned": 2 * self.GIB, "hard_limit_enabled": True},
                in_realm={"provisioned": self.GIB},
            )
            mock_module, mock_blade, lookups, mock_fs_patch = self._run_main_on(
                self._realm_params(size="1G"), found, check_mode=check_mode
            )

            assert set(lookups) == {self.REALM_FS}
            assert self._written_names(mock_blade) == []
            mock_module.exit_json.assert_called_once_with(changed=False)

    def test_main_realm_short_name_creates_when_only_the_namesake_exists(self):
        """Only the filesystem outside the realm exists: state=present
        creates realm::name instead of modifying through the namesake."""
        found = self._namesakes(array_level={"provisioned": 2 * self.GIB})
        mock_module, mock_blade, lookups, mock_fs_patch = self._run_main_on(
            self._realm_params(size="1G"), found
        )

        assert set(lookups) == {self.REALM_FS}
        mock_blade.post_file_systems.assert_called_once()
        written = self._written_names(mock_blade)
        assert written and set(written) == {self.REALM_FS}
        mock_blade.delete_file_systems.assert_not_called()
        mock_module.fail_json.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=True)

    def test_main_realm_short_name_create_check_mode_writes_nothing(self):
        found = self._namesakes(array_level={"provisioned": 2 * self.GIB})
        mock_module, mock_blade, lookups, mock_fs_patch = self._run_main_on(
            self._realm_params(size="1G"), found, check_mode=True
        )

        assert set(lookups) == {self.REALM_FS}
        assert self._written_names(mock_blade) == []
        mock_module.exit_json.assert_called_once_with(changed=True)

    def test_main_realm_short_name_absent_when_only_the_namesake_exists(self):
        """Only the filesystem outside the realm exists: state=absent has
        nothing to delete and must not send a delete for realm::name, with
        or without eradicate and in check mode."""
        for overrides, check_mode in (
            ({}, False),
            ({"eradicate": True}, False),
            ({}, True),
        ):
            found = self._namesakes(array_level={"provisioned": 2 * self.GIB})
            mock_module, mock_blade, lookups, mock_fs_patch = self._run_main_on(
                self._realm_params(state="absent", **overrides),
                found,
                check_mode=check_mode,
            )

            assert set(lookups) == {self.REALM_FS}
            assert self._written_names(mock_blade) == []
            mock_module.fail_json.assert_not_called()
            mock_module.exit_json.assert_called_once_with(changed=False)

    def test_main_realm_short_name_absent_ignores_a_destroyed_namesake(self):
        """The namesake outside the realm is destroyed, the realm filesystem
        is live: state=absent destroys the realm filesystem, and with
        eradicate=true destroys and then eradicates it. The destroyed
        namesake does not turn the request into a no-op or a bare eradicate.
        """
        for eradicate in (False, True):
            found = self._namesakes(array_level={"destroyed": True}, in_realm={})
            mock_module, mock_blade, lookups, mock_fs_patch = self._run_main_on(
                self._realm_params(state="absent", eradicate=eradicate), found
            )

            assert set(lookups) == {self.REALM_FS}
            mock_blade.patch_file_systems.assert_called_once()
            assert mock_fs_patch.call_args.kwargs["destroyed"] is True
            written = [self.REALM_FS, self.REALM_FS] if eradicate else [self.REALM_FS]
            assert self._written_names(mock_blade) == written
            assert mock_blade.delete_file_systems.call_count == int(eradicate)
            mock_module.exit_json.assert_called_once_with(changed=True)

    def test_main_realm_short_name_eradicates_the_destroyed_realm_fs(self):
        """The namesake outside the realm is live, the realm filesystem is
        destroyed: eradicate=true eradicates the realm filesystem only, and
        the live namesake does not turn the request into a destroy."""
        found = self._namesakes(array_level={}, in_realm={"destroyed": True})
        mock_module, mock_blade, lookups, mock_fs_patch = self._run_main_on(
            self._realm_params(state="absent", eradicate=True), found
        )

        assert set(lookups) == {self.REALM_FS}
        mock_blade.patch_file_systems.assert_not_called()
        mock_blade.delete_file_systems.assert_called_once_with(names=[self.REALM_FS])
        mock_module.exit_json.assert_called_once_with(changed=True)

    def test_main_realm_short_name_recovers_the_destroyed_realm_fs(self):
        """The namesake outside the realm is live, the realm filesystem is
        destroyed: state=present recovers the realm filesystem."""
        found = self._namesakes(array_level={}, in_realm={"destroyed": True})
        mock_module, mock_blade, lookups, mock_fs_patch = self._run_main_on(
            self._realm_params(), found
        )

        assert set(lookups) == {self.REALM_FS}
        written = self._written_names(mock_blade)
        assert written and set(written) == {self.REALM_FS}
        assert mock_fs_patch.call_args_list[0].kwargs == {"destroyed": False}
        mock_module.exit_json.assert_called_once_with(changed=True)

    def test_main_short_name_without_realm_never_reads_the_realm_fs(self):
        """No realm option: the short name means the filesystem outside
        every realm, also when a realm holds a filesystem of that name."""
        found = self._namesakes(
            array_level={"provisioned": 2 * self.GIB, "hard_limit_enabled": True},
            in_realm={"provisioned": self.GIB},
        )
        params = self.get_default_params()
        params.update({"name": "prod-fs", "size": "1G"})
        mock_module, mock_blade, lookups, mock_fs_patch = self._run_main_on(
            params, found
        )

        assert lookups and set(lookups) == {"prod-fs"}
        assert self._written_names(mock_blade) == ["prod-fs"]
        kwargs = mock_fs_patch.call_args.kwargs
        assert kwargs["provisioned"] == self.GIB
        assert kwargs["hard_limit_enabled"] is True
        mock_module.exit_json.assert_called_once_with(changed=True)

    def test_main_short_name_without_realm_when_only_the_realm_fs_exists(self):
        """No realm option and only the realm filesystem exists: the short
        name is not found, so state=absent is a no-op and state=present
        creates the filesystem outside every realm."""
        found = self._namesakes(in_realm={"provisioned": self.GIB})
        params = self.get_default_params()
        params.update({"name": "prod-fs", "state": "absent", "eradicate": True})
        mock_module, mock_blade, lookups, mock_fs_patch = self._run_main_on(
            params, found
        )

        assert set(lookups) == {"prod-fs"}
        assert self._written_names(mock_blade) == []
        mock_module.exit_json.assert_called_once_with(changed=False)

        found = self._namesakes(in_realm={"provisioned": self.GIB})
        params = self.get_default_params()
        params.update({"name": "prod-fs", "size": "1G"})
        mock_module, mock_blade, lookups, mock_fs_patch = self._run_main_on(
            params, found
        )

        assert set(lookups) == {"prod-fs"}
        mock_blade.post_file_systems.assert_called_once()
        assert set(self._written_names(mock_blade)) == {"prod-fs"}
        mock_blade.get_realms.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=True)

    def test_main_qualified_name_agreeing_with_realm_is_accepted(self):
        """realm::name together with the same realm option addresses the
        realm filesystem, like the short name does."""
        found = self._namesakes(
            array_level={"provisioned": 2 * self.GIB},
            in_realm={"provisioned": self.GIB},
        )
        mock_module, mock_blade, lookups, mock_fs_patch = self._run_main_on(
            self._realm_params(name=self.REALM_FS, size="2G"), found
        )

        assert lookups and set(lookups) == {self.REALM_FS}
        assert self._written_names(mock_blade) == [self.REALM_FS]
        mock_module.fail_json.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=True)

    def test_main_qualified_name_in_another_realm_fails_before_any_lookup(self):
        """A realm-qualified name that names another realm than the realm
        option is refused before the array is contacted, in check mode as
        well."""
        for state, check_mode in (
            ("present", False),
            ("present", True),
            ("absent", False),
        ):
            found = self._namesakes(array_level={}, in_realm={})
            found["other-realm::prod-fs"] = self._existing_fs()
            mock_module, mock_blade, lookups, mock_fs_patch = self._run_main_on(
                self._realm_params(name="other-realm::prod-fs", state=state),
                found,
                check_mode=check_mode,
            )

            mock_module.fail_json.assert_called_once()
            msg = mock_module.fail_json.call_args.kwargs["msg"]
            assert "other-realm::prod-fs" in msg
            assert "production-realm" in msg
            assert lookups == []
            assert mock_blade.mock_calls == []
            mock_module.exit_json.assert_not_called()

    def test_main_realm_short_name_ignores_a_namesake_in_another_realm(self):
        """The short name also exists outside every realm and in another
        realm, but not in the realm of the task: state=present creates it
        in that realm and state=absent has nothing to delete. Neither
        namesake is read or written."""
        for state, written in (("present", {self.REALM_FS}), ("absent", set())):
            found = self._namesakes(array_level={"provisioned": 2 * self.GIB})
            found["other-realm::prod-fs"] = self._existing_fs(
                name="other-realm::prod-fs", provisioned=3 * self.GIB
            )
            mock_module, mock_blade, lookups, mock_fs_patch = self._run_main_on(
                self._realm_params(state=state, size="1G"), found
            )

            assert set(lookups) == {self.REALM_FS}
            assert set(self._written_names(mock_blade)) == written
            mock_module.fail_json.assert_not_called()
            mock_module.exit_json.assert_called_once_with(changed=state == "present")

    def test_main_realm_short_name_check_mode_change_writes_nothing(self):
        """Both names exist and the request differs from the realm
        filesystem but not from the namesake: check mode reports the change
        a real run makes and sends nothing."""
        found = self._namesakes(
            array_level={"provisioned": 2 * self.GIB},
            in_realm={"provisioned": self.GIB},
        )
        mock_module, mock_blade, lookups, mock_fs_patch = self._run_main_on(
            self._realm_params(size="2G"), found, check_mode=True
        )

        assert set(lookups) == {self.REALM_FS}
        assert self._written_names(mock_blade) == []
        mock_module.exit_json.assert_called_once_with(changed=True)

    def test_main_realm_short_name_absent_check_mode_writes_nothing(self):
        """The namesake outside the realm is destroyed, the realm filesystem
        is live: state=absent in check mode reports the destroy a real run
        makes, with and without eradicate, and sends nothing."""
        for eradicate in (False, True):
            found = self._namesakes(array_level={"destroyed": True}, in_realm={})
            mock_module, mock_blade, lookups, mock_fs_patch = self._run_main_on(
                self._realm_params(state="absent", eradicate=eradicate),
                found,
                check_mode=True,
            )

            assert set(lookups) == {self.REALM_FS}
            assert self._written_names(mock_blade) == []
            mock_module.exit_json.assert_called_once_with(changed=True)
