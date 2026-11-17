# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_info module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from datetime import datetime
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
# Mock ansible_collections module and submodules
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
sys.modules[
    "ansible_collections.everpure.flashblade.plugins.module_utils.time_utils"
] = MagicMock()

from plugins.modules.purefb_info import (
    main,
    generate_default_dict,
    generate_perf_dict,
    generate_config_dict,
    generate_password_policies_dict,
    generate_file_system_exports_dict,
    generate_fs_dict,
    generate_array_conn_dict,
    generate_all_policies_dict,
    generate_bucket_access_policies_dict,
    generate_lag_dict,
    generate_subnet_dict,
    generate_bucket_cross_object_policies_dict,
    generate_network_dict,
    generate_smb_share_policies_dict,
    generate_network_access_policies_dict,
    generate_worm_data_policies_dict,
    generate_tls_policies_dict,
    generate_ssh_ca_policies_dict,
    generate_s3_export_policies_dict,
    generate_object_store_account_exports_dict,
    generate_object_store_virtual_hosts_dict,
    generate_realms_dict,
    generate_resource_accesses_dict,
    generate_file_repl_dict,
    generate_ad_dict,
    _maintenance_window_list,
    generate_admin_dict,
    generate_directory_service_roles_dict,
    generate_oidc_idps_dict,
    generate_quota_settings_dict,
    generate_support_dict,
    generate_servers_dict,
)
from plugins.module_utils.version import LooseVersion as RealLooseVersion
from plugins.modules.purefb_info import (
    generate_perf_breakdown_dict,
    generate_clients_dict,
    CLIENTS_PERF_LIMIT,
    HTTP_OPS_FIELDS,
    NFS_OPS_FIELDS,
    PERF_FIELDS,
    S3_OPS_FIELDS,
)
from plugins.modules import purefb_info as purefb_info_module


def _reference(name):
    reference = Mock(spec=["name"])
    reference.name = name
    return reference


class TestPurefbInfo:
    """Test cases for purefb_info module"""

    @patch("plugins.modules.purefb_info.generate_default_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_minimum_subset(
        self, mock_ansible_module, mock_get_system, mock_generate_default
    ):
        """Test main with minimum subset (default)"""
        # Setup mocks
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["minimum"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0.0"
        mock_blade.get_versions.return_value.items = [mock_version]
        mock_get_system.return_value = mock_blade

        mock_default_info = {"array_name": "test-array"}
        mock_generate_default.return_value = mock_default_info

        # Call main
        main()

        # Verify
        mock_generate_default.assert_called_once_with(mock_blade)
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is False
        assert "purefb_info" in call_args
        assert "default" in call_args["purefb_info"]
        assert call_args["purefb_info"]["default"] == mock_default_info

    @patch("plugins.modules.purefb_info.generate_default_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_default_subset_when_none(
        self, mock_ansible_module, mock_get_system, mock_generate_default
    ):
        """Test main defaults to minimum when gather_subset is None"""
        # Setup mocks
        mock_module = Mock()
        mock_module.params = {"gather_subset": None}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0.0"
        mock_blade.get_versions.return_value.items = [mock_version]
        mock_get_system.return_value = mock_blade

        mock_default_info = {"array_name": "test-array"}
        mock_generate_default.return_value = mock_default_info

        # Call main
        main()

        # Verify - should default to minimum
        assert mock_module.params["gather_subset"] == ["minimum"]
        mock_generate_default.assert_called_once_with(mock_blade)
        mock_module.exit_json.assert_called_once()

    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_invalid_subset(self, mock_ansible_module, mock_get_system):
        """Test main with invalid gather_subset"""
        # Setup mocks
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["invalid_subset"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0.0"
        mock_blade.get_versions.return_value.items = [mock_version]
        mock_get_system.return_value = mock_blade

        # Call main
        main()

        # Verify - should fail with invalid subset message
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "gather_subset must be one or more of" in call_args["msg"]
        assert "invalid_subset" in call_args["msg"]

    @patch("plugins.modules.purefb_info.generate_perf_dict")
    @patch("plugins.modules.purefb_info.generate_default_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_performance_subset(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_default,
        mock_generate_perf,
    ):
        """Test main with performance subset"""
        # Setup mocks
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["performance"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0.0"
        mock_blade.get_versions.return_value.items = [mock_version]
        mock_get_system.return_value = mock_blade

        mock_perf_info = {"read_bandwidth": 1000}
        mock_generate_perf.return_value = mock_perf_info

        # Call main
        main()

        # Verify
        mock_generate_perf.assert_called_once_with(mock_blade)
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert "performance" in call_args["purefb_info"]
        assert call_args["purefb_info"]["performance"] == mock_perf_info

    @patch("plugins.modules.purefb_info.generate_config_dict")
    @patch("plugins.modules.purefb_info.generate_capacity_dict")
    @patch("plugins.modules.purefb_info.generate_network_dict")
    @patch("plugins.modules.purefb_info.generate_default_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_multiple_subsets(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_default,
        mock_generate_network,
        mock_generate_capacity,
        mock_generate_config,
    ):
        """Test main with multiple subsets"""
        # Setup mocks
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["config", "capacity", "network"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0.0"
        mock_blade.get_versions.return_value.items = [mock_version]
        mock_get_system.return_value = mock_blade

        mock_config_info = {"dns": {}}
        mock_capacity_info = {"total": 1000}
        mock_network_info = {"eth0": {}}
        mock_generate_config.return_value = mock_config_info
        mock_generate_capacity.return_value = mock_capacity_info
        mock_generate_network.return_value = mock_network_info

        # Call main
        main()

        # Verify all three generators were called
        mock_generate_config.assert_called_once_with(mock_blade)
        mock_generate_capacity.assert_called_once_with(mock_blade)
        mock_generate_network.assert_called_once_with(mock_blade)
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert "config" in call_args["purefb_info"]
        assert "capacity" in call_args["purefb_info"]
        assert "network" in call_args["purefb_info"]

    @patch("plugins.modules.purefb_info.generate_object_store_virtual_hosts_dict")
    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_perf_dict")
    @patch("plugins.modules.purefb_info.generate_config_dict")
    @patch("plugins.modules.purefb_info.generate_capacity_dict")
    @patch("plugins.modules.purefb_info.generate_network_dict")
    @patch("plugins.modules.purefb_info.generate_subnet_dict")
    @patch("plugins.modules.purefb_info.generate_lag_dict")
    @patch("plugins.modules.purefb_info.generate_fs_dict")
    @patch("plugins.modules.purefb_info.generate_admin_dict")
    @patch("plugins.modules.purefb_info.generate_snap_dict")
    @patch("plugins.modules.purefb_info.generate_bucket_dict")
    @patch("plugins.modules.purefb_info.generate_all_policies_dict")
    @patch("plugins.modules.purefb_info.generate_policies_dict")
    @patch("plugins.modules.purefb_info.generate_array_conn_dict")
    @patch("plugins.modules.purefb_info.generate_file_repl_dict")
    @patch("plugins.modules.purefb_info.generate_bucket_repl_dict")
    @patch("plugins.modules.purefb_info.generate_snap_transfer_dict")
    @patch("plugins.modules.purefb_info.generate_remote_creds_dict")
    @patch("plugins.modules.purefb_info.generate_targets_dict")
    @patch("plugins.modules.purefb_info.generate_object_store_accounts_dict")
    @patch("plugins.modules.purefb_info.generate_ad_dict")
    @patch("plugins.modules.purefb_info.generate_kerb_dict")
    @patch("plugins.modules.purefb_info.generate_object_store_access_policies_dict")
    @patch("plugins.modules.purefb_info.generate_nfs_export_policies_dict")
    @patch("plugins.modules.purefb_info.generate_default_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_all_subset(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_default,
        mock_generate_nfs_export,
        mock_generate_access_policies,
        mock_generate_kerb,
        mock_generate_ad,
        mock_generate_accounts,
        mock_generate_targets,
        mock_generate_remote_creds,
        mock_generate_snap_transfer,
        mock_generate_bucket_repl,
        mock_generate_file_repl,
        mock_generate_array_conn,
        mock_generate_policies,
        mock_generate_all_policies,
        mock_generate_bucket,
        mock_generate_snap,
        mock_generate_admin,
        mock_generate_fs,
        mock_generate_lag,
        mock_generate_subnet,
        mock_generate_network,
        mock_generate_capacity,
        mock_generate_config,
        mock_generate_perf,
        mock_loose_version,
        mock_generate_virtual_hosts,
    ):
        """Test main with 'all' subset"""
        # Setup mocks
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["all"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.0.0"
        mock_blade.get_versions.return_value.items = [mock_version]
        mock_get_system.return_value = mock_blade

        # Version feature gates OFF (matches pre-migration behavior where the
        # membership check against the versions list never matched)
        mock_loose_version.return_value.__le__ = Mock(return_value=False)

        # Set return values for all generators
        mock_generate_default.return_value = {}
        mock_generate_perf.return_value = {}
        mock_generate_config.return_value = {}
        mock_generate_capacity.return_value = {}
        mock_generate_network.return_value = {}
        mock_generate_subnet.return_value = {}
        mock_generate_lag.return_value = {}
        mock_generate_fs.return_value = {}
        mock_generate_admin.return_value = {}
        mock_generate_snap.return_value = {}
        mock_generate_bucket.return_value = {}
        mock_generate_policies.return_value = {}
        mock_generate_all_policies.return_value = {}
        mock_generate_array_conn.return_value = {}
        mock_generate_file_repl.return_value = {}
        mock_generate_bucket_repl.return_value = {}
        mock_generate_snap_transfer.return_value = {}
        mock_generate_remote_creds.return_value = {}
        mock_generate_targets.return_value = {}
        mock_generate_accounts.return_value = {}
        mock_generate_ad.return_value = {}
        mock_generate_kerb.return_value = {}
        mock_generate_access_policies.return_value = {}
        mock_generate_nfs_export.return_value = {}
        mock_generate_virtual_hosts.return_value = {}

        # Call main
        main()

        # Verify all generators were called
        mock_generate_default.assert_called_once()
        mock_generate_virtual_hosts.assert_called_once()
        mock_generate_perf.assert_called_once()
        mock_generate_config.assert_called_once()
        mock_generate_capacity.assert_called_once()
        mock_generate_network.assert_called_once()
        mock_generate_subnet.assert_called_once()
        mock_generate_lag.assert_called_once()
        mock_generate_fs.assert_called_once()
        mock_generate_admin.assert_called_once()
        mock_generate_snap.assert_called_once()
        mock_generate_bucket.assert_called_once()
        mock_generate_policies.assert_called_once()
        mock_generate_all_policies.assert_called_once()
        mock_generate_array_conn.assert_called_once()
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is False
        assert "purefb_info" in call_args

    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_default_dict(self, mock_loose_version):
        """Test generate_default_dict function"""
        # Setup mock blade
        mock_blade = Mock()

        # Mock API version - needs to support 'in' operator
        mock_version = Mock()
        mock_version.version = "2.7"  # Use version that supports SECURITY_API_VERSION
        mock_version.__contains__ = Mock(return_value=True)
        mock_blade.get_versions.return_value.items = [mock_version]

        # Version feature gates ON (SECURITY/NAP/RA_DURATION) - matches the
        # pre-migration mock where __contains__ returned True for every check
        mock_loose_version.return_value.__le__ = Mock(return_value=True)

        # Mock array info
        mock_array = Mock()
        mock_array.name = "test-array"
        mock_array.id = "12345"
        mock_array.os = "Purity//FB"
        mock_array.version = "3.0.0"
        mock_array.banner = "Welcome to the lab"
        mock_array.idle_timeout = 600000  # 10 minutes in milliseconds
        mock_blade.get_arrays.return_value.items = [mock_array]

        # Mock counts
        mock_blade.get_buckets.return_value.total_item_count = 5
        mock_blade.get_file_systems.return_value.total_item_count = 10
        mock_blade.get_file_system_snapshots.return_value.total_item_count = 20
        mock_blade.get_object_store_users.return_value.total_item_count = 3
        mock_blade.get_object_store_accounts.return_value.total_item_count = 2
        mock_blade.get_blades.return_value.total_item_count = 4
        mock_blade.get_certificates.return_value.total_item_count = 1

        # Mock policies with different types
        mock_policy_snapshot = Mock()
        mock_policy_snapshot.policy_type = "snapshot"
        mock_policy_access = Mock()
        mock_policy_access.policy_type = "access"
        mock_policy_nfs = Mock()
        mock_policy_nfs.policy_type = "nfs"
        mock_policy_smb_share = Mock()
        mock_policy_smb_share.policy_type = "smb_share"
        mock_policy_smb_client = Mock()
        mock_policy_smb_client.policy_type = "smb_client"
        mock_policy_network = Mock()
        mock_policy_network.policy_type = "network"
        mock_policy_worm = Mock()
        mock_policy_worm.policy_type = "worm"
        mock_policy_telemetry = Mock()
        mock_policy_telemetry.policy_type = "telemetry-metrics"

        mock_blade.get_policies_all.return_value.total_item_count = 8
        mock_blade.get_policies_all.return_value.items = [
            mock_policy_snapshot,
            mock_policy_access,
            mock_policy_nfs,
            mock_policy_smb_share,
            mock_policy_smb_client,
            mock_policy_network,
            mock_policy_worm,
            mock_policy_telemetry,
        ]

        mock_blade.get_certificate_groups.return_value.total_item_count = 2
        mock_blade.get_file_system_replica_links.return_value.total_item_count = 0
        mock_blade.get_object_store_remote_credentials.return_value.total_item_count = 0
        mock_blade.get_bucket_replica_links.return_value.total_item_count = 0
        mock_blade.get_array_connections.return_value.total_item_count = 0
        mock_blade.get_targets.return_value.total_item_count = 0
        mock_blade.get_keytabs.return_value.total_item_count = 0

        # Mock items that use len()
        mock_blade.get_syslog_servers.return_value.items = []
        mock_blade.get_object_store_virtual_hosts.return_value.items = []
        mock_blade.get_api_clients.return_value.items = []

        # Mock space info
        mock_space = Mock()
        mock_space.capacity = 1000000000
        mock_space.space = Mock()
        mock_space.space.total_physical = 500000000
        mock_space.space.unique = 300000000
        mock_space.space.snapshots = 100000000
        mock_space.space.virtual = 400000000
        mock_blade.get_arrays_space.return_value.items = [mock_space]

        # Mock EULA
        mock_eula = Mock()
        mock_eula.signature = Mock()
        mock_eula.signature.accepted = True
        mock_blade.get_arrays_eula.return_value.items = [mock_eula]

        # Mock admin settings
        mock_admin_settings = Mock()
        mock_admin_settings.max_login_attempts = 5
        mock_admin_settings.min_password_length = 8
        mock_admin_settings.lockout_duration = 30000  # 30 seconds in milliseconds
        mock_blade.get_admins_settings.return_value.items = [mock_admin_settings]

        # Add more attributes to array mock
        mock_array.smb_mode = "native"
        mock_array.time_zone = "America/Los_Angeles"
        mock_array.product_type = "FlashBlade"
        mock_array.encryption = Mock()
        mock_array.encryption.data_at_rest = Mock()
        mock_array.encryption.data_at_rest.enabled = True
        mock_array.encryption.data_at_rest.algorithms = ["AES-256"]
        mock_array.encryption.data_at_rest.entropy_source = "internal"
        mock_array.security_update = "enabled"
        mock_array.network_access_policy = Mock()
        mock_array.network_access_policy.name = "default"

        # Mock support verification keys (for SECURITY_API_VERSION)
        mock_blade.get_support_verification_keys.return_value.items = []

        # Mock support/remote assist info
        mock_support = Mock()
        mock_support.phonehome_enabled = True
        mock_support.proxy = None
        mock_support.remote_assist_active = False
        mock_support.remote_assist_expires = None
        mock_support.remote_assist_opened = None
        mock_support.remote_assist_status = "disabled"
        mock_support.remote_assist_duration = 0
        mock_support.edge_management_enabled = False
        mock_support.edge_agent_update_enabled = True
        mock_blade.get_support.return_value.items = [mock_support]

        # Mock maintenance window (for MAINTENANCE_API_VERSION) - none open
        mock_blade.get_maintenance_windows.return_value.status_code = 200
        mock_blade.get_maintenance_windows.return_value.items = []

        # Call function
        result = generate_default_dict(mock_blade)

        # Verify
        assert "flashblade_name" in result
        assert result["flashblade_name"] == "test-array"
        assert "purity_version" in result
        assert result["purity_version"] == "3.0.0"
        assert result["banner"] == "Welcome to the lab"
        assert "buckets" in result
        assert result["buckets"] == 5
        assert "filesystems" in result
        assert result["filesystems"] == 10
        assert "snapshots" in result
        assert result["snapshots"] == 20
        assert "total_capacity" in result
        assert result["total_capacity"] == 1000000000
        assert "EULA" in result
        assert result["EULA"] == "Signed"

        # Verify support settings read-back with the 2.14 and 2.18 gates open
        assert result["remote_assist"]["phonehome_enabled"] is True
        assert result["remote_assist"]["ra_duration"] == 0
        assert result["remote_assist"]["edge_management_enabled"] is False
        assert result["remote_assist"]["edge_agent_update_enabled"] is True

        # With the gates closed (below REST 2.18) the edge keys are not reported
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        ungated = generate_default_dict(mock_blade)
        assert ungated["remote_assist"]["phonehome_enabled"] is True
        assert "ra_duration" not in ungated["remote_assist"]
        assert "edge_management_enabled" not in ungated["remote_assist"]
        assert "edge_agent_update_enabled" not in ungated["remote_assist"]

        # Verify policy counts
        assert "policies" in result
        assert result["policies"] == 8
        assert "snapshot_policies" in result
        assert result["snapshot_policies"] == 1
        assert "access_policies" in result
        assert result["access_policies"] == 1
        assert "nfs_policies" in result
        assert result["nfs_policies"] == 1
        assert "smb_share_policies" in result
        assert result["smb_share_policies"] == 1
        assert "smb_client_policies" in result
        assert result["smb_client_policies"] == 1
        assert "network_policies" in result
        assert result["network_policies"] == 1
        assert "worm_policies" in result
        assert result["worm_policies"] == 1
        assert "telemetry_metrics_policies" in result
        assert result["telemetry_metrics_policies"] == 1
        assert result["maintenance_window"] == []
        # the misspelt key is kept alongside the correct one
        assert result["network_access_protocol"] == "default"
        assert result["network_access_policy"] == "default"

    def test_maintenance_window_list_with_open_window(self):
        """An open window is reported with human-readable start and end"""
        window = Mock()
        window.name = "array"
        window.created = 1700000000000
        window.expires = 1700014400000
        mock_blade = Mock()
        mock_blade.get_maintenance_windows.return_value.status_code = 200
        mock_blade.get_maintenance_windows.return_value.items = [window]

        result = _maintenance_window_list(mock_blade)

        assert result == [
            {
                "name": "array",
                "created": datetime.fromtimestamp(1700000000).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "expires": datetime.fromtimestamp(1700014400).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            }
        ]

    def test_maintenance_window_list_empty_and_error(self):
        """No open window, or a failed GET, yields an empty list"""
        mock_blade = Mock()
        mock_blade.get_maintenance_windows.return_value.status_code = 200
        mock_blade.get_maintenance_windows.return_value.items = []
        assert _maintenance_window_list(mock_blade) == []

        mock_blade.get_maintenance_windows.return_value.status_code = 400
        mock_blade.get_maintenance_windows.return_value.items = [Mock()]
        assert _maintenance_window_list(mock_blade) == []

    def test_generate_perf_dict(self):
        """Test generate_perf_dict function"""
        # Setup mock blade
        mock_blade = Mock()

        # Mock performance data with all required attributes
        mock_total_perf = Mock()
        mock_total_perf.bytes_per_op = 4096
        mock_total_perf.bytes_per_read = 8192
        mock_total_perf.bytes_per_write = 4096
        mock_total_perf.read_bytes_per_sec = 1000000
        mock_total_perf.write_bytes_per_sec = 500000
        mock_total_perf.reads_per_sec = 100
        mock_total_perf.writes_per_sec = 50
        mock_total_perf.usec_per_other_op = 10
        mock_total_perf.usec_per_read_op = 20
        mock_total_perf.usec_per_write_op = 30

        mock_http_perf = Mock()
        mock_http_perf.bytes_per_op = 2048
        mock_http_perf.bytes_per_read = 4096
        mock_http_perf.bytes_per_write = 2048
        mock_http_perf.read_bytes_per_sec = 100000
        mock_http_perf.write_bytes_per_sec = 50000
        mock_http_perf.reads_per_sec = 10
        mock_http_perf.writes_per_sec = 5
        mock_http_perf.usec_per_other_op = 5
        mock_http_perf.usec_per_read_op = 10
        mock_http_perf.usec_per_write_op = 15

        mock_s3_perf = Mock()
        mock_s3_perf.bytes_per_op = 2048
        mock_s3_perf.bytes_per_read = 4096
        mock_s3_perf.bytes_per_write = 2048
        mock_s3_perf.read_bytes_per_sec = 200000
        mock_s3_perf.write_bytes_per_sec = 100000
        mock_s3_perf.reads_per_sec = 20
        mock_s3_perf.writes_per_sec = 10
        mock_s3_perf.usec_per_other_op = 5
        mock_s3_perf.usec_per_read_op = 10
        mock_s3_perf.usec_per_write_op = 15

        mock_nfs_perf = Mock()
        mock_nfs_perf.bytes_per_op = 2048
        mock_nfs_perf.bytes_per_read = 4096
        mock_nfs_perf.bytes_per_write = 2048
        mock_nfs_perf.read_bytes_per_sec = 300000
        mock_nfs_perf.write_bytes_per_sec = 150000
        mock_nfs_perf.reads_per_sec = 30
        mock_nfs_perf.writes_per_sec = 15
        mock_nfs_perf.usec_per_other_op = 5
        mock_nfs_perf.usec_per_read_op = 10
        mock_nfs_perf.usec_per_write_op = 15

        # Setup return values for different protocol queries
        def get_perf_side_effect(protocol=None):
            mock_result = Mock()
            if protocol == "http":
                mock_result.items = [mock_http_perf]
            elif protocol == "s3":
                mock_result.items = [mock_s3_perf]
            elif protocol == "nfs":
                mock_result.items = [mock_nfs_perf]
            else:
                mock_result.items = [mock_total_perf]
            return mock_result

        mock_blade.get_arrays_performance.side_effect = get_perf_side_effect

        # Mock replication performance count
        mock_blade.get_array_connections_performance_replication.return_value.total_item_count = (
            0
        )

        # Call function
        result = generate_perf_dict(mock_blade)

        # Verify
        assert "aggregate" in result
        assert "http" in result
        assert "s3" in result
        assert "nfs" in result
        assert result["aggregate"]["read_bytes_per_sec"] == 1000000
        assert result["http"]["read_bytes_per_sec"] == 100000
        assert result["s3"]["read_bytes_per_sec"] == 200000
        assert result["nfs"]["read_bytes_per_sec"] == 300000

    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_config_dict(self, mock_loose_version):
        """Test generate_config_dict function"""
        # Setup mock blade
        mock_blade = Mock()

        # Mock API version
        mock_version = Mock()
        mock_version.version = "2.0.0"
        mock_blade.get_versions.return_value.items = [mock_version]

        # SMTP_ENCRYPT feature gate OFF (matches pre-migration behavior where
        # the membership check against the versions list never matched)
        mock_loose_version.return_value.__le__ = Mock(return_value=False)

        # Mock DNS
        mock_dns = Mock()
        mock_dns.name = "management"
        mock_dns.domain = "example.com"
        mock_dns.nameservers = ["8.8.8.8", "8.8.4.4"]
        # sources is a list of references (at most one), not a reference
        mock_source = Mock(spec=["name"])
        mock_source.name = "vir0"
        mock_dns.sources = [mock_source]
        # DNS over HTTPS CA references (REST 2.25+); absent on older arrays
        mock_dns.ca_certificate = Mock(spec=["name"])
        mock_dns.ca_certificate.name = "doh-ca"
        mock_dns.ca_certificate_group = None
        mock_blade.get_dns.return_value.items = [mock_dns]

        # Mock SMTP
        mock_blade.get_smtp_servers.return_value.items = []

        # Mock alert watchers
        mock_blade.get_alert_watchers.return_value.items = []

        # Mock directory services - need at least management to avoid KeyError
        mock_ds = Mock()
        mock_ds.name = "management"
        mock_ds.base_dn = "DC=example,DC=com"
        mock_ds.bind_user = "admin"
        mock_ds.ca_certificate = Mock()
        mock_ds.ca_certificate.name = "ca-cert"
        mock_ds.ca_certificate_group = Mock()
        mock_ds.ca_certificate_group.name = "ca-group"
        mock_ds.enabled = True
        mock_ds.management = Mock()
        mock_ds.management.user_login_attribute = "sAMAccountName"
        mock_ds.management.user_object_class = "user"
        mock_ds.nfs = Mock()
        mock_ds.nfs.nis_servers = []
        mock_ds.nfs.nis_domains = []
        mock_ds.services = ["management"]
        mock_ds.smb = Mock()
        mock_ds.smb.join_ou = "OU=Computers"
        mock_ds.uris = ["ldap://dc.example.com"]
        mock_blade.get_directory_services.return_value.items = [mock_ds]

        # Mock directory service roles: one legacy mapping and one that
        # holds two policies, for which the array returns role as null
        legacy_role = Mock(spec=["name", "group", "group_base", "role"])
        legacy_role.name = "array_admin"
        legacy_role.group = "array-admin-users"
        legacy_role.group_base = "OU=RBAC-Groups"
        legacy_role.role = _reference("array_admin")
        policy_role = Mock(
            spec=["name", "group", "group_base", "role", "management_access_policies"]
        )
        policy_role.name = "ops-team"
        policy_role.group = ""
        policy_role.group_base = ""
        policy_role.role = None
        policy_role.management_access_policies = [
            _reference("readonly"),
            _reference("storage_admin"),
        ]
        mock_blade.get_directory_services_roles.return_value.items = [
            legacy_role,
            policy_role,
        ]

        # Mock arrays for NTP
        mock_array = Mock()
        mock_array.name = "test-array"
        mock_array.ntp_servers = ["time.google.com"]
        mock_blade.get_arrays.return_value.items = [mock_array]

        # Mock SSL certs - spec'd to the real attribute names so that the
        # old misspelt reads (certificatei_type, intermeadiate_certificate)
        # would come back as None
        mock_cert = Mock(
            spec=[
                "name",
                "certificate_type",
                "intermediate_certificate",
                "valid_from",
                "valid_to",
            ]
        )
        mock_cert.name = "management"
        mock_cert.certificate_type = "external"
        mock_cert.intermediate_certificate = "-----BEGIN CERTIFICATE-----"
        mock_cert.valid_from = 1700000000000
        mock_cert.valid_to = 1800000000000
        mock_blade.get_certificates.return_value.items = [mock_cert]

        # Mock certificate groups
        mock_blade.get_certificate_groups.return_value.items = []

        # Mock syslog servers
        mock_blade.get_syslog_servers.return_value.items = []

        # Mock SNMP agents
        mock_blade.get_snmp_agents.return_value.items = []

        # Mock SNMP managers
        mock_blade.get_snmp_managers.return_value.items = []

        # Mock SAML2 SSO (for SMTP_ENCRYPT_API_VERSION check)
        mock_blade.get_sso_saml2_idps.return_value.items = []

        # Call function
        result = generate_config_dict(mock_blade)

        # Verify
        assert "dns" in result
        assert "management" in result["dns"]
        assert result["dns"]["management"]["domain"] == "example.com"
        assert result["dns"]["management"]["nameservers"] == ["8.8.8.8", "8.8.4.4"]
        assert result["dns"]["management"]["source"] == "vir0"
        assert result["dns"]["management"]["ca_certificate"] == "doh-ca"
        assert result["dns"]["management"]["ca_certificate_group"] is None
        assert "management_directory_service" in result
        assert "array_management" in result
        cert = result["ssl_certs"]["management"]
        assert cert["certificate_type"] == "external"
        assert cert["intermediate_certificate"] == "-----BEGIN CERTIFICATE-----"
        # the LooseVersion mock keeps the REST 2.19 policy gate off here, so
        # only the null-safe role read is checked; the policy names are
        # covered by test_generate_directory_service_roles_dict
        ds_roles = result["directory_service_roles"]
        assert ds_roles["array_admin"] == {
            "group": "array-admin-users",
            "group_base": "OU=RBAC-Groups",
            "role": "array_admin",
        }
        assert ds_roles["ops-team"] == {
            "group": "",
            "group_base": "",
            "role": None,
        }
        # gated blocks are skipped below their REST version
        assert "oidc_idps" not in result
        mock_blade.get_sso_oidc_idps.assert_not_called()

    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_directory_service_roles_dict(self, mock_loose_version):
        """From REST 2.19 the policy names are reported next to the
        null-safe role for a legacy and for a two-policy mapping"""
        legacy_role = Mock(
            spec=["name", "group", "group_base", "role", "management_access_policies"]
        )
        legacy_role.name = "array_admin"
        legacy_role.group = "array-admin-users"
        legacy_role.group_base = "OU=RBAC-Groups"
        legacy_role.role = _reference("array_admin")
        legacy_role.management_access_policies = [_reference("array_admin")]
        policy_role = Mock(
            spec=["name", "group", "group_base", "role", "management_access_policies"]
        )
        policy_role.name = "ops-team"
        policy_role.group = ""
        policy_role.group_base = ""
        policy_role.role = None
        policy_role.management_access_policies = [
            _reference("readonly"),
            _reference("storage_admin"),
        ]
        mock_blade = Mock()
        mock_blade.get_directory_services_roles.return_value.items = [
            legacy_role,
            policy_role,
        ]
        mock_loose_version.return_value.__le__ = Mock(return_value=True)

        result = generate_directory_service_roles_dict(mock_blade, "2.30")

        assert result["array_admin"] == {
            "group": "array-admin-users",
            "group_base": "OU=RBAC-Groups",
            "role": "array_admin",
            "management_access_policies": ["array_admin"],
        }
        assert result["ops-team"] == {
            "group": "",
            "group_base": "",
            "role": None,
            "management_access_policies": ["readonly", "storage_admin"],
        }

    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_directory_service_roles_dict_before_2_19(
        self, mock_loose_version
    ):
        """An older array has no management_access_policies on a mapping,
        so the key is left out instead of being read as an empty list"""
        old_role = Mock(spec=["name", "group", "group_base", "role"])
        old_role.name = "readonly"
        old_role.group = "ro-users"
        old_role.group_base = "OU=Groups"
        old_role.role = _reference("readonly")
        mock_blade = Mock()
        mock_blade.get_directory_services_roles.return_value.items = [old_role]
        mock_loose_version.return_value.__le__ = Mock(return_value=False)

        result = generate_directory_service_roles_dict(mock_blade, "2.18")

        assert result == {
            "readonly": {
                "group": "ro-users",
                "group_base": "OU=Groups",
                "role": "readonly",
            }
        }

    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_admin_dict_before_2_19(self, mock_loose_version):
        """An older array has no management_access_policies on an admin,
        so the key is left out while role is still read null-safe"""
        old_admin = Mock(
            spec=["name", "public_key", "is_local", "role", "locked", "api_token"]
        )
        old_admin.name = "pureuser"
        old_admin.public_key = None
        old_admin.is_local = True
        old_admin.role = _reference("array_admin")
        old_admin.locked = False
        old_admin.api_token = None
        mock_blade = Mock()
        mock_blade.get_admins.return_value.items = [old_admin]
        mock_loose_version.return_value.__le__ = Mock(return_value=False)

        result = generate_admin_dict(mock_blade)

        assert result == {
            "pureuser": {
                "public_key": None,
                "local": True,
                "role": "array_admin",
                "locked": False,
                "lockout_remaining": None,
                "token_expires": None,
                "token_created": None,
            }
        }

    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_admin_dict_tolerates_null_role(self, mock_loose_version):
        """An admin with two policies has role null; one with a legacy
        policy has role set and a token with timestamps"""
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        legacy = Mock(
            spec=[
                "name",
                "public_key",
                "is_local",
                "role",
                "management_access_policies",
                "locked",
                "lockout_remaining",
                "api_token",
            ]
        )
        legacy.name = "pureuser"
        legacy.public_key = None
        legacy.is_local = True
        legacy.role = _reference("array_admin")
        legacy.management_access_policies = [_reference("array_admin")]
        legacy.locked = False
        legacy.lockout_remaining = None
        legacy.api_token = Mock(spec=["created_at", "expires_at"])
        legacy.api_token.created_at = 1700000000000
        legacy.api_token.expires_at = 1800000000000
        policy_admin = Mock(
            spec=["name", "is_local", "role", "management_access_policies", "api_token"]
        )
        policy_admin.name = "svc-backup"
        policy_admin.is_local = True
        policy_admin.role = None
        policy_admin.api_token = None
        policy_admin.management_access_policies = [
            _reference("storage_admin"),
            _reference("readonly"),
        ]
        mock_blade = Mock()
        mock_blade.get_admins.return_value.items = [legacy, policy_admin]

        result = generate_admin_dict(mock_blade)

        assert result["pureuser"]["role"] == "array_admin"
        assert result["pureuser"]["management_access_policies"] == ["array_admin"]
        assert result["pureuser"]["local"] is True
        assert result["pureuser"]["token_created"] == datetime.fromtimestamp(
            1700000000
        ).strftime("%Y-%m-%d %H:%M:%S")
        assert result["pureuser"]["token_expires"] == datetime.fromtimestamp(
            1800000000
        ).strftime("%Y-%m-%d %H:%M:%S")
        assert result["svc-backup"] == {
            "public_key": None,
            "local": True,
            "role": None,
            "management_access_policies": ["storage_admin", "readonly"],
            "locked": None,
            "lockout_remaining": None,
            "token_expires": None,
            "token_created": None,
        }

    def test_generate_oidc_idps_dict(self):
        """OIDC providers are keyed by name with their URL, PRN and CA references."""
        ca_cert = Mock(spec=["name"])
        ca_cert.name = "sso-root-ca"
        okta_cfg = Mock(
            spec=[
                "provider_url",
                "provider_url_ca_certificate",
                "provider_url_ca_certificate_group",
            ]
        )
        okta_cfg.provider_url = "https://acme.okta.com/oauth2/default"
        okta_cfg.provider_url_ca_certificate = ca_cert
        # an unset reference comes back as an empty object
        okta_cfg.provider_url_ca_certificate_group = {}
        okta = Mock(spec=["name", "enabled", "prn", "services", "idp"])
        okta.name = "okta"
        okta.enabled = True
        okta.prn = "prn::iam:array-id/local::oidc-provider/okta"
        okta.services = ["object"]
        okta.idp = okta_cfg

        keycloak_cfg = Mock(
            spec=[
                "provider_url",
                "provider_url_ca_certificate",
                "provider_url_ca_certificate_group",
            ]
        )
        keycloak_cfg.provider_url = "https://sso.example.com/realms/storage"
        keycloak_cfg.provider_url_ca_certificate = {}
        keycloak_cfg.provider_url_ca_certificate_group = {}
        keycloak = Mock(spec=["name", "enabled", "prn", "services", "idp"])
        keycloak.name = "keycloak"
        keycloak.enabled = False
        keycloak.prn = "prn::iam:array-id/local::oidc-provider/keycloak"
        keycloak.services = ["object"]
        keycloak.idp = keycloak_cfg

        mock_blade = Mock()
        mock_blade.get_sso_oidc_idps.return_value.items = [okta, keycloak]

        result = generate_oidc_idps_dict(mock_blade)

        assert sorted(result) == ["keycloak", "okta"]
        assert result["okta"] == {
            "enabled": True,
            "prn": "prn::iam:array-id/local::oidc-provider/okta",
            "services": ["object"],
            "provider_url": "https://acme.okta.com/oauth2/default",
            "ca_certificate": "sso-root-ca",
            "ca_certificate_group": None,
        }
        assert result["keycloak"]["enabled"] is False
        assert result["keycloak"]["ca_certificate"] is None
        assert result["keycloak"]["ca_certificate_group"] is None

    def test_generate_oidc_idps_dict_empty(self):
        """No providers configured gives an empty dict, not an error."""
        mock_blade = Mock()
        mock_blade.get_sso_oidc_idps.return_value.items = []

        assert generate_oidc_idps_dict(mock_blade) == {}

    def test_generate_quota_settings_dict_without_contact(self):
        """generate_quota_settings_dict reads the singleton; contact is absent when unset"""
        mock_blade = Mock()
        settings = Mock(spec=["name", "direct_notifications_enabled"])
        settings.name = "management"
        settings.direct_notifications_enabled = False
        mock_blade.get_quotas_settings.return_value.status_code = 200
        mock_blade.get_quotas_settings.return_value.items = [settings]
        assert generate_quota_settings_dict(mock_blade) == {
            "management": {"contact": None, "direct_notifications_enabled": False}
        }

    def test_generate_quota_settings_dict_with_contact_and_api_error(self):
        """generate_quota_settings_dict reports a set contact and returns {} on an API error"""
        mock_blade = Mock()
        settings = Mock(spec=["name", "contact", "direct_notifications_enabled"])
        settings.name = "management"
        settings.contact = "storage-admins@example.com"
        settings.direct_notifications_enabled = True
        mock_blade.get_quotas_settings.return_value.status_code = 200
        mock_blade.get_quotas_settings.return_value.items = [settings]
        assert generate_quota_settings_dict(mock_blade) == {
            "management": {
                "contact": "storage-admins@example.com",
                "direct_notifications_enabled": True,
            }
        }
        mock_blade.get_quotas_settings.return_value.status_code = 400
        assert generate_quota_settings_dict(mock_blade) == {}

    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_config_dict_saml2sso_fields(self, mock_loose_version):
        """saml2sso reports the SAML2 service, binding, fleet and SP fields"""
        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.30"
        mock_blade.get_versions.return_value.items = [mock_version]
        # every version gate ON
        mock_loose_version.return_value.__le__ = Mock(return_value=True)

        for method in (
            "get_dns",
            "get_smtp_servers",
            "get_alert_watchers",
            "get_directory_services_roles",
            "get_certificates",
            "get_certificate_groups",
            "get_syslog_servers",
            "get_snmp_agents",
            "get_snmp_managers",
            "get_kmip",
            "get_sso_oidc_idps",
        ):
            getattr(mock_blade, method).return_value.items = []
        mock_ds = Mock()
        mock_ds.name = "management"
        mock_blade.get_directory_services.return_value.items = [mock_ds]
        mock_array = Mock()
        mock_array.ntp_servers = []
        mock_blade.get_arrays.return_value.items = [mock_array]

        def reference(name):
            ref = Mock(spec=["name"])
            ref.name = name
            return ref

        saml = Mock(
            spec=[
                "name",
                "enabled",
                "array_url",
                "prn",
                "services",
                "binding",
                "management",
                "idp",
                "sp",
            ]
        )
        saml.name = "PureSSO"
        saml.enabled = False
        saml.array_url = "https://fb.example.com"
        saml.prn = "prn::iam:array-id/local::saml-provider/PureSSO"
        saml.services = ["management", "object"]
        saml.binding = "none"
        saml.management = Mock(spec=["trust_other_saml_sps_in_fleet"])
        saml.management.trust_other_saml_sps_in_fleet = True
        saml.idp = Mock()
        saml.idp.url = "https://idp.example.com/sso"
        saml.idp.entity_id = "https://idp.example.com/idp"
        saml.idp.encrypt_assertion_enabled = False
        saml.idp.sign_request_enabled = True
        saml.idp.metadata_url = "https://idp.example.com/metadata"
        saml.idp.metadata_url_ca_certificate = reference("idp-ca")
        saml.idp.metadata_url_ca_certificate_group = reference(None)
        saml.idp.verification_certificate = reference("idp-cert")
        saml.sp = Mock()
        saml.sp.entity_id = "https://sso.example.com/fleet"
        saml.sp.assertion_consumer_url = (
            "https://fb.example.com/login/saml2/sso/PureSSO"
        )
        saml.sp.metadata_url = (
            "https://fb.example.com/saml2/service-provider-metadata/PureSSO"
        )
        saml.sp.decryption_credential = reference(None)
        saml.sp.signing_credential = reference("sp-signing")
        mock_blade.get_sso_saml2_idps.return_value.items = [saml]

        result = generate_config_dict(mock_blade)

        sso = result["saml2sso"]
        assert sso["name"] == "PureSSO"
        assert sso["prn"] == "prn::iam:array-id/local::saml-provider/PureSSO"
        assert sso["services"] == ["management", "object"]
        assert sso["binding"] == "none"
        assert sso["trust_other_saml_sps_in_fleet"] is True
        assert sso["idp"]["entity_id"] == "https://idp.example.com/idp"
        assert sso["idp"]["metadata_url_ca_certificate"] == "idp-ca"
        assert sso["idp"]["metadata_url_ca_certificate_group"] is None
        assert sso["idp"]["verification_certificate"] == "idp-cert"
        assert sso["sp"]["entity_id"] == "https://sso.example.com/fleet"
        assert (
            sso["sp"]["assertion_consumer_url"]
            == "https://fb.example.com/login/saml2/sso/PureSSO"
        )
        assert (
            sso["sp"]["metadata_url"]
            == "https://fb.example.com/saml2/service-provider-metadata/PureSSO"
        )
        assert sso["sp"]["decrypt_cred"] is None
        assert sso["sp"]["sign_cred"] == "sp-signing"

    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_config_dict_saml2sso_old_array(self, mock_loose_version):
        """saml2sso fields a pre-2.17 array lacks are reported as None"""
        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.16"
        mock_blade.get_versions.return_value.items = [mock_version]
        mock_loose_version.return_value.__le__ = Mock(return_value=True)

        for method in (
            "get_dns",
            "get_smtp_servers",
            "get_alert_watchers",
            "get_directory_services_roles",
            "get_certificates",
            "get_certificate_groups",
            "get_syslog_servers",
            "get_snmp_agents",
            "get_snmp_managers",
            "get_kmip",
            "get_sso_oidc_idps",
        ):
            getattr(mock_blade, method).return_value.items = []
        mock_ds = Mock()
        mock_ds.name = "management"
        mock_blade.get_directory_services.return_value.items = [mock_ds]
        mock_array = Mock()
        mock_array.ntp_servers = []
        mock_blade.get_arrays.return_value.items = [mock_array]

        saml = Mock(spec=["name", "enabled", "array_url", "idp", "sp"])
        saml.name = "PureSSO"
        saml.enabled = True
        saml.array_url = "https://fb.example.com"
        saml.idp = Mock(
            spec=[
                "url",
                "entity_id",
                "encrypt_assertion_enabled",
                "sign_request_enabled",
                "metadata_url",
                "verification_certificate",
            ]
        )
        saml.idp.url = None
        saml.idp.entity_id = None
        saml.idp.encrypt_assertion_enabled = False
        saml.idp.sign_request_enabled = False
        saml.idp.metadata_url = "https://idp.example.com/metadata"
        saml.idp.verification_certificate = Mock(spec=["name"])
        saml.idp.verification_certificate.name = None
        saml.sp = Mock(spec=["decryption_credential", "signing_credential"])
        saml.sp.decryption_credential = Mock(spec=["name"])
        saml.sp.decryption_credential.name = None
        saml.sp.signing_credential = Mock(spec=["name"])
        saml.sp.signing_credential.name = None
        mock_blade.get_sso_saml2_idps.return_value.items = [saml]

        result = generate_config_dict(mock_blade)

        sso = result["saml2sso"]
        assert sso["enabled"] is True
        assert sso["prn"] is None
        assert sso["services"] is None
        assert sso["binding"] is None
        assert sso["trust_other_saml_sps_in_fleet"] is None
        assert sso["idp"]["metadata_url_ca_certificate"] is None
        assert sso["idp"]["metadata_url_ca_certificate_group"] is None
        assert sso["idp"]["verification_certificate"] is None
        assert sso["sp"]["entity_id"] is None
        assert sso["sp"]["assertion_consumer_url"] is None
        assert sso["sp"]["metadata_url"] is None

    def test_generate_password_policies_dict(self):
        """Test generate_password_policies_dict reports all fields in seconds"""
        mock_blade = Mock()

        # Policy as the GET endpoint returns it: durations in milliseconds.
        # spec-limited so getattr on absent fields returns the default.
        fields = {
            "name": "management",
            "enabled": True,
            "min_password_length": 8,
            "max_login_attempts": 10,
            "lockout_duration": 3600000,
            "password_history": 5,
            "min_password_age": 86400000,
            "max_password_age": 8640000000,
            "min_character_groups": 3,
            "min_characters_per_group": 1,
            "enforce_username_check": True,
            "enforce_dictionary_check": False,
        }
        mock_policy = Mock(spec=list(fields))
        for field, value in fields.items():
            setattr(mock_policy, field, value)
        mock_blade.get_password_policies.return_value.items = [mock_policy]

        result = generate_password_policies_dict(mock_blade)

        policy_info = result["management"]
        assert policy_info["enabled"] is True
        assert policy_info["min_password_length"] == 8
        assert policy_info["max_login_attempts"] == 10
        assert policy_info["lockout_duration"] == 3600
        assert policy_info["password_history"] == 5
        assert policy_info["min_password_age"] == 86400
        assert policy_info["max_password_age"] == 8640000
        assert policy_info["min_character_groups"] == 3
        assert policy_info["min_characters_per_group"] == 1
        assert policy_info["enforce_username_check"] is True
        assert policy_info["enforce_dictionary_check"] is False

    def test_generate_password_policies_dict_null_disabled_rules(self):
        """Test rules absent from the API object are reported as None

        Disabled rules (set to 0) read back as absent, and older REST
        versions lack max_password_age entirely; both report as None.
        """
        mock_blade = Mock()

        fields = {
            "name": "management",
            "enabled": True,
            "min_password_length": 1,
            "min_character_groups": 1,
            "min_characters_per_group": 1,
            "enforce_username_check": False,
            "enforce_dictionary_check": False,
        }
        mock_policy = Mock(spec=list(fields))
        for field, value in fields.items():
            setattr(mock_policy, field, value)
        mock_blade.get_password_policies.return_value.items = [mock_policy]

        result = generate_password_policies_dict(mock_blade)

        policy_info = result["management"]
        assert policy_info["max_login_attempts"] is None
        assert policy_info["lockout_duration"] is None
        assert policy_info["password_history"] is None
        assert policy_info["min_password_age"] is None
        assert policy_info["max_password_age"] is None

    # ==== file_system_exports generator ====

    def _mk_export(
        self,
        export_name,
        policy_type,
        filesystem,
        server,
        policy_name=None,
        share_policy_name=None,
    ):
        """Build a mock FileSystemExport shaped like pypureclient returns.

        policy_type is UPPERCASE ("NFS" / "SMB") because
        pypureclient.flashblade.FileSystemExport.policy_type reports it that
        way. Passing lowercase here would mask the case-branch mismatch bug
        the generator is guarding against.
        """
        exp = Mock()
        exp.export_name = export_name
        exp.policy_type = policy_type
        member = Mock()
        member.name = filesystem
        exp.member = member
        srv = Mock()
        srv.name = server
        exp.server = srv
        if policy_name:
            pol = Mock()
            pol.name = policy_name
            exp.policy = pol
        else:
            exp.policy = None
        if share_policy_name:
            sp = Mock()
            sp.name = share_policy_name
            exp.share_policy = sp
        else:
            exp.share_policy = None
        return exp

    def test_generate_file_system_exports_dict_nfs_populates_export_policy(self):
        """An NFS export must expose export_policy and leave client/share None.

        Guards against the lowercase-vs-uppercase policy_type comparison bug
        where every policy field silently came back None in production.
        """
        mock_blade = Mock()
        mock_blade.get_file_system_exports.return_value.items = [
            self._mk_export(
                "fs1_nfs",
                "NFS",
                "fs1",
                "_array_server",
                policy_name="nfs_pol1",
            ),
        ]

        result = generate_file_system_exports_dict(mock_blade)

        assert result == [
            {
                "export_name": "fs1_nfs",
                "type": "NFS",
                "filesystem": "fs1",
                "server": "_array_server",
                "export_policy": "nfs_pol1",
                "client_policy": None,
                "share_policy": None,
            }
        ]

    def test_generate_file_system_exports_dict_smb_populates_client_and_share(self):
        """An SMB export must expose client_policy and share_policy and leave
        export_policy None. Same case-branch guard as the NFS test."""
        mock_blade = Mock()
        mock_blade.get_file_system_exports.return_value.items = [
            self._mk_export(
                "fs1_smb",
                "SMB",
                "fs1",
                "_array_server",
                policy_name="smb_client_pol1",
                share_policy_name="smb_share_pol1",
            ),
        ]

        result = generate_file_system_exports_dict(mock_blade)

        assert result[0]["type"] == "SMB"
        assert result[0]["export_policy"] is None
        assert result[0]["client_policy"] == "smb_client_pol1"
        assert result[0]["share_policy"] == "smb_share_pol1"

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_info.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def test_generate_fs_dict_scopes_exports_per_filesystem(self):
        """generate_fs_dict must scope its file_system_exports list to the
        current filesystem only. A global list leak would attribute exports
        of other filesystems to this one."""
        mock_blade = Mock()

        fs1 = Mock()
        fs1.name = "fs1"
        fs1.fast_remove_directory_enabled = False
        fs1.snapshot_directory_enabled = False
        fs1.provisioned = 0
        fs1.destroyed = False
        fs1.nfs = Mock(
            rules=None, v3_enabled=True, v4_1_enabled=True, export_policy=None
        )
        fs1.smb = Mock(
            acl_mode=None,
            client_policy=None,
            share_policy=None,
            continuous_availability_enabled=False,
        )
        fs1.multi_protocol = Mock(safeguard_acls=True, access_control_style=None)
        fs1.hard_limit_enabled = False
        fs1.promotion_status = None
        fs1.requested_promotion_state = None
        fs1.writable = True
        fs1.source = None
        fs1.location = None
        fs1.default_group_quota = 0
        fs1.default_user_quota = 0
        fs1.http = Mock(enabled=False)

        mock_blade.get_file_systems.return_value.items = [fs1]
        mock_blade.get_quotas_groups.return_value.items = []
        mock_blade.get_quotas_users.return_value.items = []

        exports = [
            {"filesystem": "fs1", "type": "NFS", "export_name": "fs1_nfs"},
            {"filesystem": "other_fs", "type": "SMB", "export_name": "other"},
        ]

        result = generate_fs_dict(mock_blade, exports=exports)

        assert len(result["fs1"]["file_system_exports"]) == 1
        assert result["fs1"]["file_system_exports"][0]["export_name"] == "fs1_nfs"
        # the misspelt key is kept alongside the correct one
        assert result["fs1"]["multi_protocol"]["safegaurd_acls"] is True
        assert result["fs1"]["multi_protocol"]["safeguard_acls"] is True
        # a plain filesystem has a source with no name
        assert result["fs1"]["source"] == {
            "is_local": None,
            "name": None,
            "resource_type": None,
            "display_name": None,
            "location": None,
        }

    def test_generate_fs_dict_reports_copy_source(self):
        """A filesystem copy reports the filesystem it was copied from, and
        the location comes from the source reference, not the filesystem."""
        mock_blade = Mock()

        location = Mock()
        location.name = "array1"
        source = Mock()
        source.name = "fs1"
        source.is_local = True
        source.resource_type = "file-systems"
        source.display_name = "fs1"
        source.location = location

        copy = Mock()
        copy.name = "fs1-copy"
        copy.fast_remove_directory_enabled = False
        copy.snapshot_directory_enabled = False
        copy.provisioned = 0
        copy.destroyed = False
        copy.nfs = Mock(
            rules=None, v3_enabled=True, v4_1_enabled=True, export_policy=None
        )
        copy.smb = Mock(
            acl_mode=None,
            client_policy=None,
            share_policy=None,
            continuous_availability_enabled=False,
        )
        copy.multi_protocol = Mock(safeguard_acls=True, access_control_style=None)
        copy.hard_limit_enabled = False
        copy.promotion_status = "promoting"
        copy.requested_promotion_state = "promoted"
        copy.writable = True
        copy.source = source
        copy.default_group_quota = 0
        copy.default_user_quota = 0
        copy.http = Mock(enabled=False)

        mock_blade.get_file_systems.return_value.items = [copy]
        mock_blade.get_quotas_groups.return_value.items = []
        mock_blade.get_quotas_users.return_value.items = []

        result = generate_fs_dict(mock_blade)

        assert result["fs1-copy"]["promotion_status"] == "promoting"
        assert result["fs1-copy"]["source"] == {
            "is_local": True,
            "name": "fs1",
            "resource_type": "file-systems",
            "display_name": "fs1",
            "location": "array1",
        }

    # ==== storage_class read-back: the name purefb_fs compares ====

    def _fs_for_storage_class(self, storage_class):
        """Minimal file system for generate_fs_dict. ``storage_class`` is the
        object the array returns, or None for a REST version whose file
        system model has no such field.
        """
        fsys = Mock()
        fsys.name = "fs1"
        fsys.fast_remove_directory_enabled = False
        fsys.snapshot_directory_enabled = False
        fsys.provisioned = 0
        fsys.destroyed = False
        fsys.nfs = Mock(
            rules=None, v3_enabled=True, v4_1_enabled=False, export_policy=None
        )
        fsys.smb = Mock(
            acl_mode=None,
            client_policy=None,
            share_policy=None,
            continuous_availability_enabled=False,
        )
        fsys.multi_protocol = Mock(safeguard_acls=False, access_control_style=None)
        fsys.hard_limit_enabled = False
        fsys.promotion_status = None
        fsys.requested_promotion_state = None
        fsys.writable = True
        fsys.source = None
        fsys.location = None
        fsys.default_group_quota = 0
        fsys.default_user_quota = 0
        fsys.http = Mock(enabled=False)
        if storage_class is None:
            del fsys.storage_class
        else:
            fsys.storage_class = storage_class
        return fsys

    def _blade_with_fs(self, fsys):
        mock_blade = Mock()
        mock_blade.get_file_systems.return_value.items = [fsys]
        mock_blade.get_quotas_groups.return_value.items = []
        mock_blade.get_quotas_users.return_value.items = []
        return mock_blade

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_info.get_rest_api_version",
        Mock(return_value="2.17"),
    )
    def test_generate_fs_dict_reports_storage_class_name(self):
        """From REST 2.17 the storage class is reported by name, the value
        purefb_fs compares its storage_class option with.
        """
        storage_class = Mock()
        storage_class.name = "S500X-S"
        mock_blade = self._blade_with_fs(self._fs_for_storage_class(storage_class))

        result = generate_fs_dict(mock_blade)

        assert result["fs1"]["storage_class"] == "S500X-S"

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_info.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def test_generate_fs_dict_storage_class_null_without_storage_classes(self):
        """Platforms without storage classes return the storage_class object
        with no name; the key is still reported, as null.
        """
        storage_class = Mock()
        storage_class.name = None
        mock_blade = self._blade_with_fs(self._fs_for_storage_class(storage_class))

        result = generate_fs_dict(mock_blade)

        assert "storage_class" in result["fs1"]
        assert result["fs1"]["storage_class"] is None

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_info.get_rest_api_version",
        Mock(return_value="2.16"),
    )
    def test_generate_fs_dict_storage_class_not_reported_before_2_17(self):
        """Below REST 2.17 the key is not reported, matching the version from
        which purefb_fs manages the storage class.
        """
        mock_blade = self._blade_with_fs(self._fs_for_storage_class(None))

        result = generate_fs_dict(mock_blade)

        assert "storage_class" not in result["fs1"]
        assert result["fs1"]["nfs_v3"] is True

    def test_generate_array_conn_dict_keys_by_remote_and_reads_the_connection(self):
        """The dict is keyed by the remote name, values come from the connection.

        Rebinding the loop variable to array.remote.name made every attribute
        read below raise AttributeError, so the arrays subset - and therefore
        gather_subset=all - failed on any array with a replication connection.
        The spec'd mock reproduces that: a str has no .encrypted.
        """
        window = Mock(spec=["start", "end"])
        window.start = None
        window.end = None
        throttle = Mock(spec=["default_limit", "window_limit", "window"])
        throttle.default_limit = None
        throttle.window_limit = None
        throttle.window = window
        remote = Mock(spec=["name"])
        remote.name = "remote-array"
        conn = Mock(
            spec=[
                "remote",
                "encrypted",
                "replication_addresses",
                "management_address",
                "status",
                "version",
                "ca_certificate_group",
                "throttle",
            ]
        )
        conn.remote = remote
        conn.encrypted = False
        conn.replication_addresses = ["10.0.0.1"]
        conn.management_address = "10.0.0.2"
        conn.status = "connected"
        conn.version = "4.3.3"
        # The array returns a FixedReference whose name may be None, rather
        # than None itself. Both shapes must be tolerated.
        ca_group = Mock(spec=["name"])
        ca_group.name = None
        conn.ca_certificate_group = ca_group
        conn.throttle = throttle

        mock_blade = Mock()
        mock_blade.get_array_connections.return_value.items = [conn]
        mock_blade.get_array_connections_path.return_value.items = []

        result = generate_array_conn_dict(mock_blade)

        assert list(result) == ["remote-array"]
        entry = result["remote-array"]
        assert entry["connection_paths"] == []
        assert entry["encrypted"] is False
        assert entry["status"] == "connected"
        assert entry["version"] == "4.3.3"
        assert entry["management_address"] == "10.0.0.2"
        assert entry["replication_addresses"] == ["10.0.0.1"]
        assert entry["ca_certificate_group"] is None

        # and when the field itself is absent
        conn.ca_certificate_group = None
        result = generate_array_conn_dict(mock_blade)
        assert result["remote-array"]["ca_certificate_group"] is None

    def test_generate_bucket_access_policies_dict_tolerates_no_description(self):
        """BucketAccessPolicy has no description field.

        Reading it directly raised AttributeError, which broke the policies
        subset. The spec'd mock has no description, matching the real model.
        """
        principal = Mock(spec=["all"])
        principal.all = True
        rule = Mock(spec=["name", "actions", "principals", "resources", "effect"])
        rule.name = "rule1"
        rule.actions = ["s3:GetObject"]
        rule.principals = principal
        rule.resources = ["bucket/*"]
        rule.effect = "allow"

        policy = Mock(spec=["name", "enabled", "is_local", "rules"])
        policy.name = "bucket/access-policy"
        policy.enabled = True
        policy.is_local = True
        policy.rules = [rule]

        bucket = Mock(spec=["name"])
        bucket.name = "bucket"

        response = Mock()
        response.status_code = 200
        response.total_item_count = 1
        response.items = [policy]

        mock_blade = Mock()
        mock_blade.get_buckets.return_value.items = [bucket]
        mock_blade.get_buckets_bucket_access_policies.return_value = response

        result = generate_bucket_access_policies_dict(mock_blade)

        assert "bucket/access-policy" in result
        entry = result["bucket/access-policy"]
        assert entry["description"] is None
        assert entry["enabled"] is True
        assert entry["local"] is True
        assert len(entry["rules"]) == 1

    def test_generate_lag_dict_returns_empty_when_endpoint_errors(self):
        """An array in Layer 3 (BGP) mode has no link aggregation groups and
        the endpoint returns an error response, which carries no items. The
        subset must come back empty instead of raising AttributeError."""
        mock_blade = Mock()
        error = Mock(spec=["status_code", "errors", "headers"])
        error.status_code = 400
        mock_blade.get_link_aggregation_groups.return_value = error

        assert generate_lag_dict(mock_blade) == {}

    def test_generate_lag_dict_tolerates_lag_without_ports(self):
        """The SDK model defaults ports to None; iterate it as empty."""
        mock_blade = Mock()
        lag = Mock()
        lag.name = "uplink"
        lag.lag_speed = 0
        lag.port_speed = 100000000000
        lag.mac_address = "24:a9:37:f8:c0:63"
        lag.status = "unused"
        lag.ports = None
        mock_blade.get_link_aggregation_groups.return_value = Mock(
            status_code=200, items=[lag]
        )

        result = generate_lag_dict(mock_blade)

        assert result["uplink"]["ports"] == []
        assert result["uplink"]["status"] == "unused"

    def test_generate_subnet_dict_tolerates_subnet_without_lag(self):
        """BGP data subnets carry no LAG, VLAN or gateway, so the LAG
        reference is None and must be reported as such, not dereferenced."""
        mock_blade = Mock()
        iface = Mock()
        iface.name = "vip1"
        sub = Mock()
        sub.name = "net2"
        sub.enabled = True
        sub.gateway = None
        sub.mtu = 1500
        sub.vlan = None
        sub.prefix = "10.255.9.0/24"
        sub.services = ["data"]
        sub.link_aggregation_group = None
        sub.interfaces = [iface]
        mock_blade.get_subnets.return_value.items = [sub]

        result = generate_subnet_dict(mock_blade)

        assert result["net2"]["lag"] is None
        assert result["net2"]["vlan"] is None
        assert result["net2"]["interfaces"] == [{"name": "vip1"}]

    def test_generate_network_dict_reads_attached_servers_and_subnet(self):
        """server comes from attached_servers[0] and subnet may be a dict.

        The interface model has no server attribute (the API field is
        attached_servers, a list of references) and subnet is a plain dict on
        current SDKs, so both keys always read back as null. The spec'd mock
        has no server attribute, matching the real model.
        """
        server = Mock(spec=["name"])
        server.name = "_array_server"
        port = Mock(
            spec=[
                "name",
                "type",
                "mtu",
                "vlan",
                "address",
                "services",
                "gateway",
                "netmask",
                "attached_servers",
                "subnet",
                "enabled",
            ]
        )
        port.name = "vip1"
        port.type = "vip"
        port.mtu = 1500
        port.vlan = 0
        port.address = "10.0.0.5"
        port.services = ["data"]
        port.gateway = "10.0.0.1"
        port.netmask = "255.255.255.0"
        port.attached_servers = [server]
        port.subnet = {"name": "data-subnet", "resource_type": "subnets"}
        port.enabled = True

        mock_blade = Mock()
        mock_blade.get_network_interfaces.return_value.items = [port]

        result = generate_network_dict(mock_blade)

        assert result["vip1"]["server"] == "_array_server"
        assert result["vip1"]["attached_servers"] == ["_array_server"]
        assert result["vip1"]["subnet"] == "data-subnet"
        assert result["vip1"]["address"] == "10.0.0.5"
        # fields missing from the model on older arrays read back as unset
        assert result["vip1"]["rdma_enabled"] is None
        assert result["vip1"]["realms"] == []

        # reference-shaped subnet, no attached server
        subnet = Mock(spec=["name"])
        subnet.name = "mgmt"
        port.subnet = subnet
        port.attached_servers = []
        result = generate_network_dict(mock_blade)
        assert result["vip1"]["server"] is None
        assert result["vip1"]["attached_servers"] == []
        assert result["vip1"]["subnet"] == "mgmt"

    def test_generate_network_dict_reports_rdma_and_realms(self):
        """rdma_enabled (REST 2.28) and realms (REST 2.19) are passed through.

        Realm references arrive as plain dicts on current SDKs and as
        reference objects on older ones; both shapes reduce to names.
        """
        realm_ref = Mock(spec=["name"])
        realm_ref.name = "realm-2"
        port = Mock(
            spec=[
                "name",
                "type",
                "address",
                "services",
                "attached_servers",
                "subnet",
                "enabled",
                "rdma_enabled",
                "realms",
            ]
        )
        port.name = "realm-1::vip1"
        port.type = "vip"
        port.address = "10.0.0.6"
        port.services = ["data"]
        port.attached_servers = []
        port.subnet = {"name": "data-subnet"}
        port.enabled = True
        port.rdma_enabled = False
        port.realms = [{"name": "realm-1", "resource_type": "realms"}, realm_ref]

        mock_blade = Mock()
        mock_blade.get_network_interfaces.return_value.items = [port]

        result = generate_network_dict(mock_blade)

        assert result["realm-1::vip1"]["rdma_enabled"] is False
        assert result["realm-1::vip1"]["realms"] == ["realm-1", "realm-2"]

        port.rdma_enabled = True
        port.realms = []
        result = generate_network_dict(mock_blade)
        assert result["realm-1::vip1"]["rdma_enabled"] is True
        assert result["realm-1::vip1"]["realms"] == []

    def test_generate_bucket_cross_object_policies_dict_reports_rules(self):
        """The allowed_* lists live on the CORS rules, not on the policy.

        Reading them from the policy raised AttributeError as soon as any
        bucket had a CORS policy, which broke the policies subset. The spec'd
        policy mock has no allowed_* attributes, matching the real model.
        """
        policy = Mock(spec=["name", "enabled", "is_local"])
        policy.name = "bkt/cors"
        policy.enabled = True
        policy.is_local = True
        rule = Mock(
            spec=["name", "allowed_headers", "allowed_methods", "allowed_origins"]
        )
        rule.name = "bkt/cors/rule1"
        rule.allowed_headers = ["*"]
        rule.allowed_methods = ["GET", "PUT"]
        rule.allowed_origins = ["*"]
        bucket = Mock(spec=["name"])
        bucket.name = "bkt"

        policy_res = Mock()
        policy_res.status_code = 200
        policy_res.items = [policy]
        rule_res = Mock()
        rule_res.status_code = 200
        rule_res.items = [rule]

        mock_blade = Mock()
        mock_blade.get_buckets.return_value.items = [bucket]
        mock_blade.get_buckets_cross_origin_resource_sharing_policies.return_value = (
            policy_res
        )
        mock_blade.get_buckets_cross_origin_resource_sharing_policies_rules.return_value = (
            rule_res
        )

        result = generate_bucket_cross_object_policies_dict(mock_blade)

        assert list(result) == ["bkt/cors"]
        assert result["bkt/cors"]["enabled"] is True
        assert result["bkt/cors"]["local"] is True
        assert result["bkt/cors"]["rules"] == [
            {
                "name": "bkt/cors/rule1",
                "allowed_headers": ["*"],
                "allowed_methods": ["GET", "PUT"],
                "allowed_origins": ["*"],
            }
        ]
        mock_blade.get_buckets_cross_origin_resource_sharing_policies_rules.assert_called_once_with(
            policy_names=["bkt/cors"]
        )

        # a bucket whose policy lookup fails is skipped, not fatal
        policy_res.status_code = 400
        assert generate_bucket_cross_object_policies_dict(mock_blade) == {}

    def test_generate_smb_share_policies_dict(self):
        """SMB share policies are reported with their inline rules."""
        rule = Mock(spec=["name", "principal", "change", "full_control", "read"])
        rule.name = "share1/rule1"
        rule.principal = "DOMAIN\\Everyone"
        rule.change = "allow"
        rule.full_control = "deny"
        rule.read = "allow"
        policy = Mock(spec=["name", "enabled", "is_local", "rules"])
        policy.name = "share1"
        policy.enabled = True
        policy.is_local = True
        policy.rules = [rule]

        mock_blade = Mock()
        mock_blade.get_smb_share_policies.return_value.items = [policy]

        result = generate_smb_share_policies_dict(mock_blade)

        assert result == {
            "share1": {
                "local": True,
                "enabled": True,
                "rules": [
                    {
                        "name": "share1/rule1",
                        "principal": "DOMAIN\\Everyone",
                        "change": "allow",
                        "full_control": "deny",
                        "read": "allow",
                    }
                ],
            }
        }

    def test_generate_network_access_policies_dict(self):
        """Network access policies are reported with their inline rules."""
        rule = Mock(spec=["name", "client", "effect", "interfaces", "index"])
        rule.name = "default-network-access-policy/rule1"
        rule.client = "10.0.0.0/8"
        rule.effect = "allow"
        rule.interfaces = ["management-ssh"]
        rule.index = 1
        policy = Mock(spec=["name", "enabled", "is_local", "version", "rules"])
        policy.name = "default-network-access-policy"
        policy.enabled = True
        policy.is_local = True
        policy.version = "abc123"
        policy.rules = [rule]

        mock_blade = Mock()
        mock_blade.get_network_access_policies.return_value.items = [policy]

        result = generate_network_access_policies_dict(mock_blade)

        entry = result["default-network-access-policy"]
        assert entry["version"] == "abc123"
        assert entry["rules"] == [
            {
                "name": "default-network-access-policy/rule1",
                "client": "10.0.0.0/8",
                "effect": "allow",
                "interfaces": ["management-ssh"],
                "index": 1,
            }
        ]

    def test_generate_worm_data_policies_dict(self):
        """WORM policies carry their retention settings and member list."""
        policy = Mock(
            spec=[
                "name",
                "enabled",
                "is_local",
                "mode",
                "retention_lock",
                "default_retention",
                "min_retention",
                "max_retention",
            ]
        )
        policy.name = "worm1"
        policy.enabled = True
        policy.is_local = True
        policy.mode = "compliance"
        policy.retention_lock = "unlocked"
        policy.default_retention = 86400000
        policy.min_retention = 60000
        policy.max_retention = 172800000
        member_ref = Mock(spec=["name"])
        member_ref.name = "fs1"
        policy_ref = Mock(spec=["name"])
        policy_ref.name = "worm1"
        member = Mock(spec=["member", "policy"])
        member.member = member_ref
        member.policy = policy_ref

        mock_blade = Mock()
        mock_blade.get_worm_data_policies.return_value.items = [policy]
        mock_blade.get_worm_data_policies_members.return_value.items = [member]

        result = generate_worm_data_policies_dict(mock_blade)

        assert result["worm1"]["mode"] == "compliance"
        assert result["worm1"]["default_retention"] == 86400000
        assert result["worm1"]["members"] == ["fs1"]

    def test_generate_tls_policies_dict(self):
        """TLS policies carry their settings and attached interfaces."""
        cert = Mock(spec=["name"])
        cert.name = "management"
        policy = Mock(
            spec=[
                "name",
                "enabled",
                "is_local",
                "appliance_certificate",
                "min_tls_version",
                "enabled_tls_ciphers",
                "disabled_tls_ciphers",
                "client_certificates_required",
                "verify_client_certificate_trust",
                "trusted_client_certificate_authority",
            ]
        )
        policy.name = "tls1"
        policy.enabled = True
        policy.is_local = True
        policy.appliance_certificate = cert
        policy.min_tls_version = "1.2"
        policy.enabled_tls_ciphers = None
        policy.disabled_tls_ciphers = ["RC4"]
        policy.client_certificates_required = False
        policy.verify_client_certificate_trust = False
        policy.trusted_client_certificate_authority = None
        iface_ref = Mock(spec=["name"])
        iface_ref.name = "vip1"
        policy_ref = Mock(spec=["name"])
        policy_ref.name = "tls1"
        member = Mock(spec=["member", "policy"])
        member.member = iface_ref
        member.policy = policy_ref

        array_ref = Mock(spec=["name", "resource_type"])
        array_ref.name = "array1"
        array_ref.resource_type = "arrays"
        array_member = Mock(spec=["member", "policy"])
        array_member.member = array_ref
        array_member.policy = policy_ref

        mock_blade = Mock()
        mock_blade.get_tls_policies.return_value.items = [policy]
        mock_blade.get_tls_policies_network_interfaces.return_value.items = [member]
        mock_blade.get_tls_policies_members.return_value.items = [array_member]

        result = generate_tls_policies_dict(mock_blade)

        assert result["tls1"]["appliance_certificate"] == "management"
        assert result["tls1"]["min_tls_version"] == "1.2"
        assert result["tls1"]["disabled_tls_ciphers"] == ["RC4"]
        assert result["tls1"]["trusted_client_certificate_authority"] is None
        assert result["tls1"]["network_interfaces"] == ["vip1"]
        # tls-policies/members lists the policy applied to the whole array
        assert result["tls1"]["array_wide"] is True

        # a policy attached only to interfaces is not array-wide
        mock_blade.get_tls_policies_members.return_value.items = []
        result = generate_tls_policies_dict(mock_blade)
        assert result["tls1"]["array_wide"] is False
        assert result["tls1"]["network_interfaces"] == ["vip1"]

    def test_generate_ssh_ca_policies_dict(self):
        """SSH CA policies carry their signer, principals and members."""
        signer = Mock(spec=["name", "resource_type"])
        signer.name = "ops-ca-key"
        signer.resource_type = "public-keys"
        policy = Mock(
            spec=[
                "name",
                "enabled",
                "is_local",
                "signing_authority",
                "static_authorized_principals",
            ]
        )
        policy.name = "ssh-ca"
        policy.enabled = True
        policy.is_local = True
        policy.signing_authority = signer
        policy.static_authorized_principals = ["ops"]
        unset = Mock(
            spec=[
                "name",
                "enabled",
                "is_local",
                "signing_authority",
                "static_authorized_principals",
            ]
        )
        unset.name = "ssh-ca-cert"
        unset.enabled = False
        unset.is_local = True
        unset.signing_authority = Mock(spec=["name", "resource_type"])
        unset.signing_authority.name = "corp-ca"
        unset.signing_authority.resource_type = "certificates"
        unset.static_authorized_principals = None
        admin_ref = Mock(spec=["name", "resource_type"])
        admin_ref.name = "alice"
        admin_ref.resource_type = "admins"
        array_ref = Mock(spec=["name", "resource_type"])
        array_ref.name = "myblade"
        array_ref.resource_type = "arrays"
        policy_ref = Mock(spec=["name"])
        policy_ref.name = "ssh-ca"
        admin_member = Mock(spec=["member", "policy"])
        admin_member.member = admin_ref
        admin_member.policy = policy_ref
        array_member = Mock(spec=["member", "policy"])
        array_member.member = array_ref
        array_member.policy = policy_ref

        mock_blade = Mock()
        mock_blade.get_ssh_certificate_authority_policies.return_value.items = [
            policy,
            unset,
        ]
        mock_blade.get_ssh_certificate_authority_policies_members.return_value.items = [
            admin_member,
            array_member,
        ]

        result = generate_ssh_ca_policies_dict(mock_blade)

        assert result["ssh-ca"]["enabled"] is True
        assert result["ssh-ca"]["signing_authority"] == "ops-ca-key"
        assert result["ssh-ca"]["signing_authority_type"] == "public_key"
        assert result["ssh-ca"]["static_authorized_principals"] == ["ops"]
        assert result["ssh-ca"]["admins"] == ["alice"]
        assert result["ssh-ca"]["arrays"] == ["myblade"]
        assert result["ssh-ca-cert"]["signing_authority_type"] == "certificate"
        assert result["ssh-ca-cert"]["static_authorized_principals"] == []
        assert result["ssh-ca-cert"]["admins"] == []

    def test_generate_s3_export_policies_dict(self):
        """S3 export policies are reported with their inline rules."""
        rule = Mock(spec=["name", "actions", "effect", "resources"])
        rule.name = "s3exp/rule1"
        rule.actions = ["s3:*"]
        rule.effect = "allow"
        rule.resources = ["*"]
        policy = Mock(spec=["name", "enabled", "is_local", "rules"])
        policy.name = "s3exp"
        policy.enabled = True
        policy.is_local = True
        policy.rules = [rule]

        mock_blade = Mock()
        mock_blade.get_s3_export_policies.return_value.items = [policy]

        result = generate_s3_export_policies_dict(mock_blade)

        assert result["s3exp"]["rules"] == [
            {
                "name": "s3exp/rule1",
                "actions": ["s3:*"],
                "effect": "allow",
                "resources": ["*"],
            }
        ]

    def test_generate_object_store_account_exports_dict(self):
        """Account exports report account, policy and server by name."""
        account = Mock(spec=["name"])
        account.name = "acc1"
        policy = Mock(spec=["name"])
        policy.name = "s3exp"
        server = Mock(spec=["name"])
        server.name = "_array_server"
        export = Mock(spec=["name", "enabled", "member", "policy", "server"])
        export.name = "acc1-export"
        export.enabled = True
        export.member = account
        export.policy = policy
        export.server = server

        mock_blade = Mock()
        mock_blade.get_object_store_account_exports.return_value.items = [export]

        result = generate_object_store_account_exports_dict(mock_blade)

        assert result == {
            "acc1-export": {
                "enabled": True,
                "account": "acc1",
                "policy": "s3exp",
                "server": "_array_server",
            }
        }

    def test_generate_object_store_virtual_hosts_dict(self):
        """Virtual hosts report hostname and attached servers; before REST
        2.20 the name is the hostname."""
        server = Mock(spec=["name"])
        server.name = "_array_server"
        new_vhost = Mock(spec=["name", "hostname", "attached_servers"])
        new_vhost.name = "vh1"
        new_vhost.hostname = "s3.example.com"
        new_vhost.attached_servers = [server]
        old_vhost = Mock(spec=["name"])
        old_vhost.name = "s3.old.example.com"

        mock_blade = Mock()
        mock_blade.get_object_store_virtual_hosts.return_value.items = [
            new_vhost,
            old_vhost,
        ]

        result = generate_object_store_virtual_hosts_dict(mock_blade)

        assert result["vh1"] == {
            "hostname": "s3.example.com",
            "attached_servers": ["_array_server"],
        }
        assert result["s3.old.example.com"] == {
            "hostname": "s3.old.example.com",
            "attached_servers": [],
        }

    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_realms_and_resource_accesses(self, mock_loose_version):
        """Realms report their space, TLS policy and default object store
        server; resource accesses map a scope to a resource by name and type."""
        # REST 2.20+: the realms/defaults endpoint exists
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        space = Mock(spec=["total_physical", "virtual"])
        space.total_physical = 1024
        space.virtual = 2048
        tls = Mock(spec=["name"])
        tls.name = "tls1"
        realm_spec = [
            "name",
            "created",
            "destroyed",
            "time_remaining",
            "default_inbound_tls_policy",
            "space",
        ]
        realm = Mock(spec=realm_spec)
        realm.name = "realm1"
        realm.created = 1700000000000
        realm.destroyed = False
        realm.time_remaining = None
        realm.default_inbound_tls_policy = tls
        realm.space = space
        realm2 = Mock(spec=realm_spec)
        realm2.name = "realm2"
        realm2.created = None
        realm2.destroyed = False
        realm2.time_remaining = None
        realm2.default_inbound_tls_policy = None
        realm2.space = space

        # realm1 has a default server, realm2 an empty object_store list
        server = Mock(spec=["name"])
        server.name = "realm1::s3srv"
        store_default = Mock(spec=["server"])
        store_default.server = server
        realm1_ref = Mock(spec=["name"])
        realm1_ref.name = "realm1"
        realm1_defaults = Mock(spec=["realm", "object_store"])
        realm1_defaults.realm = realm1_ref
        realm1_defaults.object_store = [store_default]
        realm2_ref = Mock(spec=["name"])
        realm2_ref.name = "realm2"
        realm2_defaults = Mock(spec=["realm", "object_store"])
        realm2_defaults.realm = realm2_ref
        realm2_defaults.object_store = []

        mock_blade = Mock()
        mock_blade.get_realms.return_value.items = [realm, realm2]
        mock_blade.get_realms_defaults.return_value.status_code = 200
        mock_blade.get_realms_defaults.return_value.items = [
            realm1_defaults,
            realm2_defaults,
        ]

        result = generate_realms_dict(mock_blade)

        mock_blade.get_realms_defaults.assert_called_once_with()
        assert result["realm1"]["destroyed"] is False
        assert result["realm1"]["created"] is not None
        assert result["realm1"]["default_inbound_tls_policy"] == "tls1"
        assert result["realm1"]["default_object_server"] == "realm1::s3srv"
        assert result["realm1"]["space"]["total_physical"] == 1024
        assert result["realm1"]["space"]["virtual"] == 2048
        # fields absent from this Space version are reported as null
        assert result["realm1"]["space"]["total_used"] is None
        assert result["realm2"]["created"] is None
        assert result["realm2"]["default_object_server"] is None

        resource = Mock(spec=["name", "resource_type"])
        resource.name = "data-subnet"
        resource.resource_type = "subnets"
        scope = Mock(spec=["name", "resource_type"])
        scope.name = "realm1"
        scope.resource_type = "realms"
        access = Mock(spec=["id", "resource", "scope"])
        access.id = "abc"
        access.resource = resource
        access.scope = scope
        mock_blade.get_resource_accesses.return_value.items = [access]

        result = generate_resource_accesses_dict(mock_blade)

        assert result == [
            {
                "id": "abc",
                "resource": "data-subnet",
                "resource_type": "subnets",
                "scope": "realm1",
                "scope_type": "realms",
            }
        ]

    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_realms_dict_before_realm_defaults_api(self, mock_loose_version):
        """Before REST 2.20 there is no realms/defaults endpoint: it is not
        queried and the default object store server is reported as null."""
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        realm = Mock(
            spec=[
                "name",
                "created",
                "destroyed",
                "time_remaining",
                "default_inbound_tls_policy",
                "space",
            ]
        )
        realm.name = "realm1"
        realm.created = None
        realm.destroyed = False
        realm.time_remaining = None
        realm.default_inbound_tls_policy = None
        realm.space = None

        mock_blade = Mock()
        mock_blade.get_realms.return_value.items = [realm]

        result = generate_realms_dict(mock_blade)

        mock_blade.get_realms_defaults.assert_not_called()
        assert result["realm1"]["default_object_server"] is None
        assert result["realm1"]["default_inbound_tls_policy"] is None

    def test_generate_file_repl_dict_reads_status_details(self):
        """The SDK replica link model has status_details, not status_detail.

        Reading status_detail raised AttributeError as soon as a filesystem
        replica link existed, which broke the replication (and all) subsets.
        The spec'd mock has no status_detail attribute, matching the model;
        the output key keeps its historical name.
        """
        remote = Mock(spec=["name"])
        remote.name = "peer"
        remote_fs = Mock(spec=["name"])
        remote_fs.name = "fs1"
        local_fs = Mock(spec=["name"])
        local_fs.name = "fs1"
        policy = Mock(spec=["display_name"])
        policy.display_name = "daily"
        link = Mock(
            spec=[
                "local_file_system",
                "direction",
                "link_type",
                "lag",
                "status",
                "status_details",
                "remote",
                "remote_file_system",
                "recovery_point",
                "policies",
            ]
        )
        link.local_file_system = local_fs
        link.direction = "outbound"
        link.link_type = "periodic"
        link.lag = 0
        link.status = "replicating"
        link.status_details = None
        link.remote = remote
        link.remote_file_system = remote_fs
        link.recovery_point = 1700000000000
        link.policies = [policy]

        mock_blade = Mock()
        mock_blade.get_file_system_replica_links.return_value.items = [link]

        result = generate_file_repl_dict(mock_blade)

        assert result["fs1"]["status"] == "replicating"
        assert result["fs1"]["status_detail"] is None
        assert result["fs1"]["remote_fs"] == "peer:fs1"
        assert result["fs1"]["policies"] == ["daily"]

    def test_generate_servers_dict_reports_lds_and_realms(self):
        """Servers report their local directory service and realms. Servers
        from arrays older than REST 2.24 (no local_directory_service) or 2.19
        (no realms) report null and an empty list."""
        dns = Mock(spec=["name"])
        dns.name = "management"
        nfs_ds = Mock(spec=["name"])
        nfs_ds.name = "srv1_nfs"
        lds = Mock(spec=["name"])
        lds.name = "srv1_local"
        realm = Mock(spec=["name"])
        realm.name = "realm1"

        server_fields = [
            "name",
            "created",
            "dns",
            "directory_services",
            "local_directory_service",
            "realms",
        ]
        with_lds = Mock(spec=server_fields)
        with_lds.name = "srv1"
        with_lds.created = 1700000000000
        with_lds.dns = [dns]
        with_lds.directory_services = [nfs_ds]
        with_lds.local_directory_service = lds
        with_lds.realms = [realm]

        # a current array returns an unattached server with the field null
        unattached = Mock(spec=server_fields)
        unattached.name = "_array_server"
        unattached.created = 0
        unattached.dns = [dns]
        unattached.directory_services = [nfs_ds]
        unattached.local_directory_service = None
        unattached.realms = []

        # an older array returns servers without either field
        old = Mock(spec=["name", "created", "dns", "directory_services"])
        old.name = "old"
        old.created = 0
        old.dns = [dns]
        old.directory_services = [nfs_ds]

        mock_blade = Mock()
        mock_blade.get_servers.return_value.items = [with_lds, unattached, old]

        result = generate_servers_dict(mock_blade)

        assert result["srv1"]["dns"] == ["management"]
        assert result["srv1"]["directory_services"] == ["srv1_nfs"]
        assert result["srv1"]["local_directory_service"] == "srv1_local"
        assert result["srv1"]["realms"] == ["realm1"]
        assert result["_array_server"]["local_directory_service"] is None
        assert result["_array_server"]["realms"] == []
        assert result["old"]["local_directory_service"] is None
        assert result["old"]["realms"] == []

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_fleet_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_fleet_subset(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_fleet,
        mock_loose_version,
    ):
        """gather_subset=fleet returns the fleet section on its own.

        The data used to be produced only inside the policies subset, so the
        documented fleet subset came back without a fleet key.
        """
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["fleet"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.21"
        mock_blade.get_versions.return_value.items = [mock_version]
        mock_get_system.return_value = mock_blade
        # version gates ON
        mock_loose_version.return_value.__le__ = Mock(return_value=True)

        mock_generate_fleet.return_value = {"fleet1": {"members": {}}}

        main()

        mock_generate_fleet.assert_called_once_with(mock_blade)
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["purefb_info"]["fleet"] == {"fleet1": {"members": {}}}
        assert "policies" not in call_args["purefb_info"]

    # ---------------- support subset (self-diagnostics) ----------------

    @staticmethod
    def _diagnostics_run(index, task_id, status, counts):
        run = Mock(
            spec=[
                "index",
                "task_id",
                "status",
                "version",
                "start_time",
                "analysis_period",
                "severity_count",
            ]
        )
        run.index = index
        run.task_id = task_id
        run.status = status
        run.version = "default"
        run.start_time = 1700003600
        period = Mock(spec=["start_time", "end_time"])
        period.start_time = 1700000000
        period.end_time = 1700003600
        run.analysis_period = period
        run.severity_count = []
        for severity, count in counts:
            entry = Mock(spec=["severity", "count"])
            entry.severity = severity
            entry.count = count
            run.severity_count.append(entry)
        return run

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.get_rest_api_version", return_value="2.30")
    def test_generate_support_dict_reports_runs_and_settings(
        self, mock_api_version, mock_loose_version
    ):
        """Retained runs are keyed by index; the tool version is read on 2.24+."""
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        mock_blade = Mock()
        runs = Mock()
        runs.status_code = 200
        runs.items = [
            self._diagnostics_run(1, "task-1", "completed", [("info", 200)]),
            self._diagnostics_run(
                2, "task-2", "running", [("info", 5), ("warning", 1)]
            ),
        ]
        mock_blade.get_support_diagnostics.return_value = runs
        settings = Mock()
        settings.status_code = 200
        item = Mock(spec=["version", "last_updated"])
        item.version = "default"
        item.last_updated = None
        settings.items = [item]
        mock_blade.get_support_diagnostics_settings.return_value = settings

        result = generate_support_dict(mock_blade)

        assert sorted(result["diagnostics"]) == ["1", "2"]
        assert result["diagnostics"]["1"]["severity_count"] == {
            "info": 200,
            "warning": 0,
            "critical": 0,
        }
        assert result["diagnostics"]["2"] == {
            "task_id": "task-2",
            "status": "running",
            "version": "default",
            "start_time": 1700003600,
            "analysis_period_start": 1700000000,
            "analysis_period_end": 1700003600,
            "severity_count": {"info": 5, "warning": 1, "critical": 0},
        }
        assert result["diagnostics_settings"] == {
            "version": "default",
            "last_updated": None,
        }

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.get_rest_api_version", return_value="2.17")
    def test_generate_support_dict_skips_settings_before_2_24(
        self, mock_api_version, mock_loose_version
    ):
        """No runs and an old array: both sections come back empty, no settings call."""
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        mock_blade = Mock()
        runs = Mock()
        runs.status_code = 200
        runs.items = []
        mock_blade.get_support_diagnostics.return_value = runs

        result = generate_support_dict(mock_blade)

        assert result == {"diagnostics": {}, "diagnostics_settings": {}}
        mock_blade.get_support_diagnostics_settings.assert_not_called()

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_support_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_support_subset(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_support,
        mock_loose_version,
    ):
        """gather_subset=support returns the support section on its own."""
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["support"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.30"
        mock_blade.get_versions.return_value.items = [mock_version]
        mock_get_system.return_value = mock_blade
        # version gates ON
        mock_loose_version.return_value.__le__ = Mock(return_value=True)

        mock_generate_support.return_value = {
            "diagnostics": {},
            "diagnostics_settings": {},
        }

        main()

        mock_generate_support.assert_called_once_with(mock_blade)
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["purefb_info"]["support"] == {
            "diagnostics": {},
            "diagnostics_settings": {},
        }
        assert "default" not in call_args["purefb_info"]

    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_file_locks_dict(self, mock_loose_version):
        """The locks subset returns locks, lock clients, sessions and SMB open files."""
        # Imported here so the shared import block above stays untouched.
        from plugins.modules.purefb_info import generate_file_locks_dict

        mock_loose_version.return_value.__le__ = Mock(return_value=True)

        def ref(name):
            item = Mock()
            item.name = name
            return item

        lock = ref("lock1")
        lock.access_type = "exclusive"
        lock.client = ref("10.0.0.1")
        lock.created_at = 1700000000000
        lock.inode = 42
        lock.path = "/build/output.db"
        lock.protocol = "NLM"
        lock.range = Mock(length=0, offset=0)
        lock.source = ref("fs1")
        session = ref("sess1")
        session.authentication = "NTLMv2"
        session.client = ref("10.0.0.1")
        session.connection_time = 1700000000000
        session.idle_time = 5000
        session.opens = 2
        session.port = 51234
        session.protocol = "smb"
        session.user = ref("alice")
        open_file = Mock()
        open_file.id = "of1"
        open_file.client = ref("10.0.0.1")
        open_file.lock_count = 1
        open_file.mode = "rw"
        open_file.path = "/build/output.db"
        open_file.session = ref("sess1")
        open_file.source = ref("fs1")
        open_file.user = ref("alice")

        blade = Mock()
        blade.get_file_systems_locks.return_value = Mock(status_code=200, items=[lock])
        blade.get_file_systems_locks_clients.return_value = Mock(
            status_code=200, items=[ref("10.0.0.1")]
        )
        blade.get_file_systems_sessions.return_value = Mock(
            status_code=200, items=[session]
        )
        blade.get_file_systems_open_files.return_value = Mock(
            status_code=200, items=[open_file]
        )

        result = generate_file_locks_dict(blade)

        assert result["file_locks"]["lock1"]["client"] == "10.0.0.1"
        assert result["file_locks"]["lock1"]["file_system"] == "fs1"
        assert result["file_locks"]["lock1"]["range"] == {"length": 0, "offset": 0}
        assert result["file_lock_clients"] == ["10.0.0.1"]
        assert result["file_sessions"]["sess1"]["user"] == "alice"
        assert result["file_sessions"]["sess1"]["protocol"] == "smb"
        assert result["open_files"]["of1"]["session"] == "sess1"
        assert result["open_files"]["of1"]["mode"] == "rw"
        blade.get_file_systems_open_files.assert_called_once_with(protocols=["smb"])

    def test_generate_ad_dict_reports_ca_references(self):
        """The CA certificate and group names are read back, None when unset."""
        ca = Mock(spec=["name"])
        ca.name = "domain_ca"
        account = Mock(
            spec=[
                "name",
                "computer_name",
                "domain",
                "directory_servers",
                "kerberos_servers",
                "service_principal_names",
                "join_ou",
                "encryption_types",
                "global_catalog_servers",
                "server",
                "ca_certificate",
                "ca_certificate_group",
            ]
        )
        account.name = "ad1"
        account.computer_name = "AD1"
        account.domain = "acme.com"
        account.directory_servers = ["ldap.acme.com"]
        account.kerberos_servers = ["kdc.acme.com"]
        account.service_principal_names = ["nfs/ad1.acme.com"]
        account.join_ou = "CN=Computers"
        account.encryption_types = ["aes256-cts-hmac-sha1-96"]
        account.global_catalog_servers = None
        account.server = None
        account.ca_certificate = ca
        account.ca_certificate_group = None

        mock_blade = Mock()
        mock_blade.get_active_directory.return_value.total_item_count = 1
        mock_blade.get_active_directory.return_value.items = [account]

        result = generate_ad_dict(mock_blade)

        assert result["ad1"]["ca_certificate"] == "domain_ca"
        assert result["ad1"]["ca_certificate_group"] is None
        assert result["ad1"]["server"] is None

    @staticmethod
    def _connection(remote_name):
        """An array connection mock shaped like the real model."""
        window = Mock(spec=["start", "end"])
        window.start = None
        window.end = None
        throttle = Mock(spec=["default_limit", "window_limit", "window"])
        throttle.default_limit = None
        throttle.window_limit = None
        throttle.window = window
        remote = Mock(spec=["name"])
        remote.name = remote_name
        conn = Mock(
            spec=[
                "remote",
                "encrypted",
                "replication_addresses",
                "management_address",
                "status",
                "version",
                "ca_certificate_group",
                "throttle",
            ]
        )
        conn.remote = remote
        conn.encrypted = False
        conn.replication_addresses = ["10.0.0.1"]
        conn.management_address = "10.0.0.2"
        conn.status = "connected"
        conn.version = "4.5.6"
        conn.ca_certificate_group = None
        conn.throttle = throttle
        return conn

    @staticmethod
    def _path(remote_name, destination, status, **extra):
        """An array-connections/path row; extra adds optional fields."""
        remote = Mock(spec=["name"])
        remote.name = remote_name
        fields = {
            "remote": remote,
            "source": "10.0.0.2",
            "destination": destination,
            "status": status,
            "type": "async-replication",
        }
        fields.update(extra)
        path = Mock(spec=list(fields))
        for key, value in fields.items():
            setattr(path, key, value)
        return path

    def test_generate_array_conn_dict_connection_paths(self):
        """Each connection lists its network paths from array-connections/path.

        A connected path comes back with status_details empty or without
        the field at all; both are reported as None. Rows for a remote that
        is not a connection are ignored.
        """
        mock_blade = Mock()
        mock_blade.get_array_connections.return_value.items = [
            self._connection("remote-array")
        ]
        mock_blade.get_array_connections_path.return_value.items = [
            self._path("remote-array", "10.0.0.1:80", "connected"),
            self._path("remote-array", "10.0.0.1:8117", "connected", status_details=""),
            self._path(
                "remote-array",
                "10.0.0.3:8117",
                "connecting",
                status_details="Connection refused",
                type="fleet-management",
            ),
            self._path("other-array", "10.0.0.9:80", "connected"),
        ]

        result = generate_array_conn_dict(mock_blade)

        assert list(result) == ["remote-array"]
        assert result["remote-array"]["connection_paths"] == [
            {
                "source": "10.0.0.2",
                "destination": "10.0.0.1:80",
                "status": "connected",
                "status_details": None,
                "type": "async-replication",
            },
            {
                "source": "10.0.0.2",
                "destination": "10.0.0.1:8117",
                "status": "connected",
                "status_details": None,
                "type": "async-replication",
            },
            {
                "source": "10.0.0.2",
                "destination": "10.0.0.3:8117",
                "status": "connecting",
                "status_details": "Connection refused",
                "type": "fleet-management",
            },
        ]
        mock_blade.get_array_connections_path.assert_called_once_with()

    def test_generate_array_conn_dict_without_connections_skips_paths(self):
        """No connections means no array-connections/path call."""
        mock_blade = Mock()
        mock_blade.get_array_connections.return_value.items = []

        assert generate_array_conn_dict(mock_blade) == {}
        mock_blade.get_array_connections_path.assert_not_called()

    @staticmethod
    def _policy(name, policy_id, policy_type):
        """A policies-all row."""
        policy = Mock(
            spec=["name", "id", "enabled", "is_local", "location", "policy_type"]
        )
        policy.name = name
        policy.id = policy_id
        policy.enabled = True
        policy.is_local = True
        policy.location = None
        policy.policy_type = policy_type
        return policy

    @staticmethod
    def _ref(name, ref_id=None, resource_type=None):
        """A FixedReference."""
        ref = Mock(spec=["name", "id", "resource_type"])
        ref.name = name
        ref.id = ref_id
        ref.resource_type = resource_type
        return ref

    @staticmethod
    def _member_row(policy_ref, member_ref, link=None):
        """A policies-all/members row."""
        row = Mock(spec=["policy", "member", "link"])
        row.policy = policy_ref
        row.member = member_ref
        row.link = link
        return row

    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_all_policies_dict_members(self, mock_loose_version):
        """Every policy carries its members from one policies-all/members call.

        Rows are attributed by policy id, so a realm policy that shares its
        name with an array-level policy keeps its own members; replica-link
        members carry the link's file systems; a policy without members
        reports an empty list.
        """
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        link = Mock(spec=["local_file_system", "remote", "remote_file_system"])
        link.local_file_system = self._ref("fs1")
        link.remote = self._ref("peer")
        link.remote_file_system = self._ref("fs1-dr")

        mock_blade = Mock()
        mock_blade.get_policies_all.return_value.items = [
            self._policy("daily", "p1", "snapshot"),
            self._policy("realm1::daily", "p2", "snapshot"),
            self._policy("device_perf_metrics", "p3", "telemetry-metrics"),
            self._policy("unused", "p4", "nfs"),
        ]
        mock_blade.get_policies_all_members.return_value.items = [
            self._member_row(
                self._ref("daily", "p1", "policies"),
                self._ref("fs1", "f1", "file-systems"),
            ),
            self._member_row(
                self._ref("daily", "p1", "policies"),
                self._ref("fs1-link", "l1", "file-system-replica-links"),
                link,
            ),
            # the realm policy is reported under its own name but with its id
            self._member_row(
                self._ref("daily", "p2", "policies"),
                self._ref("realm1::fs9", "f9", "file-systems"),
            ),
            self._member_row(
                self._ref("device_perf_metrics", "p3", "telemetry-metrics-policies"),
                self._ref("array1", "a1", "arrays"),
            ),
        ]

        result = generate_all_policies_dict(mock_blade)

        assert result["daily"]["policy_type"] == "snapshot"
        assert result["daily"]["members"] == [
            {"name": "fs1", "resource_type": "file-systems"},
            {
                "name": "fs1-link",
                "resource_type": "file-system-replica-links",
                "link": {
                    "local_file_system": "fs1",
                    "remote": "peer",
                    "remote_file_system": "fs1-dr",
                },
            },
        ]
        assert result["realm1::daily"]["members"] == [
            {"name": "realm1::fs9", "resource_type": "file-systems"}
        ]
        assert result["device_perf_metrics"]["members"] == [
            {"name": "array1", "resource_type": "arrays"}
        ]
        assert result["unused"]["members"] == []
        mock_blade.get_policies_all_members.assert_called_once_with()

    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_all_policies_dict_members_need_rest_2_2(self, mock_loose_version):
        """Below REST 2.2 the members call is not made and no key is added."""
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        mock_blade = Mock()
        mock_blade.get_policies_all.return_value.items = [
            self._policy("daily", "p1", "snapshot")
        ]

        result = generate_all_policies_dict(mock_blade)

        assert result["daily"]["policy_type"] == "snapshot"
        assert "members" not in result["daily"]
        mock_blade.get_policies_all_members.assert_not_called()

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_nfs_export_policies_dict")
    @patch("plugins.modules.purefb_info.generate_object_store_access_policies_dict")
    @patch("plugins.modules.purefb_info.generate_policies_dict")
    @patch("plugins.modules.purefb_info.generate_all_policies_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_policies_subset_copies_members_to_snapshot_policies(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_all_policies,
        mock_generate_policies,
        mock_generate_access,
        mock_generate_nfs_export,
        mock_loose_version,
    ):
        """snapshot_policies reuse the members gathered by the policies view.

        No second members call is made; a snapshot policy missing from the
        policies view, or one gathered below REST 2.2, has no members key.
        """
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["policies"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        # the other version gates in the policies subset stay off
        mock_loose_version.return_value.__le__ = Mock(return_value=False)

        members = [{"name": "fs1", "resource_type": "file-systems"}]
        mock_generate_all_policies.return_value = {
            "daily": {"policy_type": "snapshot", "members": members},
            "nfs1": {"policy_type": "nfs", "members": []},
        }
        mock_generate_policies.return_value = {
            "daily": {"enabled": True},
            "weekly": {"enabled": True},
        }
        mock_generate_access.return_value = {}
        mock_generate_nfs_export.return_value = {}

        main()

        info = mock_module.exit_json.call_args[1]["purefb_info"]
        assert info["snapshot_policies"]["daily"]["members"] == members
        assert "members" not in info["snapshot_policies"]["weekly"]
        assert info["policies"]["nfs1"]["members"] == []

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_info.get_rest_api_version")
    def test_generate_all_policies_dict_members_gate_compares_real_versions(
        self, mock_get_rest_api_version
    ):
        """The REST 2.2 gate holds against real version strings.

        2.1 is below the gate, 2.2 meets it and 2.10 is above it (a numeric,
        not a string, comparison).
        """
        mock_blade = Mock()
        mock_blade.get_policies_all.return_value.items = [
            self._policy("daily", "p1", "snapshot")
        ]
        mock_blade.get_policies_all_members.return_value.items = []

        mock_get_rest_api_version.return_value = "2.1"
        assert "members" not in generate_all_policies_dict(mock_blade)["daily"]
        mock_blade.get_policies_all_members.assert_not_called()

        mock_get_rest_api_version.return_value = "2.2"
        assert generate_all_policies_dict(mock_blade)["daily"]["members"] == []
        mock_blade.get_policies_all_members.assert_called_once_with()

        mock_get_rest_api_version.return_value = "2.10"
        assert generate_all_policies_dict(mock_blade)["daily"]["members"] == []
        assert mock_blade.get_policies_all_members.call_count == 2


class _Row(object):
    """Attribute holder standing in for an SDK model row.

    Unlike Mock, getattr on a field that was not set yields the default.
    """

    def __init__(self, **fields):
        for key, value in fields.items():
            setattr(self, key, value)


class _Version(object):
    """Minimal LooseVersion stand-in comparing dotted integer versions."""

    def __init__(self, vstring):
        self.parts = tuple(int(part) for part in str(vstring).split("."))

    def __le__(self, other):
        return self.parts <= other.parts

    def __gt__(self, other):
        return self.parts > other.parts


def _ok(items):
    response = Mock()
    response.status_code = 200
    response.items = items
    response.total_item_count = len(items)
    return response


def _failed():
    response = Mock()
    response.status_code = 400
    response.items = None
    return response


def _repl_row(**extra):
    return _Row(
        aggregate=_Row(received_bytes_per_sec=10.0, transmitted_bytes_per_sec=20.0),
        periodic=_Row(received_bytes_per_sec=10.0, transmitted_bytes_per_sec=20.0),
        continuous=_Row(
            received_bytes_per_sec=0.0,
            transmitted_bytes_per_sec=0.0,
            object_backlog=_Row(
                bytes_count=0, delete_ops_count=0, other_ops_count=0, put_ops_count=1
            ),
        ),
        time=1700000000000,
        **extra
    )


class TestPurefbInfoPerformance:
    """Performance breakdown and opt-in clients subset."""

    def _breakdown_blade(self):
        blade = Mock()

        def arrays_performance(protocol=None):
            if protocol == "smb":
                return _ok([_Row(name="fb", reads_per_sec=5.0, time=1)])
            return _ok([_Row(name="fb", reads_per_sec=50.0, time=1)])

        blade.get_arrays_performance.side_effect = arrays_performance
        blade.get_arrays_nfs_specific_performance.return_value = _ok(
            [_Row(lookups_per_sec=7.0, time=2)]
        )
        blade.get_arrays_s3_specific_performance.return_value = _ok(
            [_Row(read_objects_per_sec=3.0, time=2)]
        )
        blade.get_arrays_http_specific_performance.return_value = _ok(
            [_Row(read_files_per_sec=2.0, time=2)]
        )
        blade.get_arrays_performance_replication.return_value = _ok([_repl_row()])
        # one peer row with no continuous sub-object, one without a remote name
        blade.get_array_connections_performance_replication.return_value = _ok(
            [
                _Row(
                    remote=_Row(name="peer-fb"),
                    aggregate=_Row(
                        received_bytes_per_sec=1.0, transmitted_bytes_per_sec=2.0
                    ),
                    periodic=_Row(
                        received_bytes_per_sec=1.0, transmitted_bytes_per_sec=2.0
                    ),
                    time=3,
                ),
                _repl_row(id="conn-id"),
            ]
        )
        blade.get_targets_performance_replication.return_value = _ok(
            [_repl_row(name="s3-target")]
        )
        blade.get_file_systems_performance.return_value = _ok(
            [_Row(name="fs1", reads_per_sec=1.0, time=4)]
        )
        blade.get_buckets_performance.return_value = _ok(
            [_Row(name="b1", writes_per_sec=4.0, time=4)]
        )
        blade.get_buckets_s3_specific_performance.return_value = _ok(
            [
                _Row(name="b1", write_objects_per_sec=4.0, time=4),
                _Row(name="b2", write_objects_per_sec=0.0, time=4),
            ]
        )
        return blade

    def test_generate_perf_breakdown_dict_reports_every_key(self):
        blade = self._breakdown_blade()

        result = generate_perf_breakdown_dict(blade)

        assert set(result) == {
            "smb",
            "nfs_ops",
            "s3_ops",
            "http_ops",
            "replication",
            "filesystems",
            "buckets",
        }
        blade.get_arrays_performance.assert_called_once_with(protocol="smb")
        assert set(result["smb"]) == set(PERF_FIELDS)
        assert result["smb"]["reads_per_sec"] == 5.0
        assert result["smb"]["writes_per_sec"] is None
        assert set(result["nfs_ops"]) == set(NFS_OPS_FIELDS)
        assert result["nfs_ops"]["lookups_per_sec"] == 7.0
        assert set(result["s3_ops"]) == set(S3_OPS_FIELDS)
        assert result["s3_ops"]["read_objects_per_sec"] == 3.0
        assert set(result["http_ops"]) == set(HTTP_OPS_FIELDS)
        assert result["http_ops"]["read_files_per_sec"] == 2.0

        repl = result["replication"]
        assert repl["aggregate"] == {
            "received_bytes_per_sec": 10.0,
            "transmitted_bytes_per_sec": 20.0,
        }
        assert repl["periodic"]["received_bytes_per_sec"] == 10.0
        assert repl["continuous"]["object_backlog"]["put_ops_count"] == 1
        assert repl["time"] == 1700000000000
        # array connections are keyed by the remote array name, falling back
        # to the connection id; a row without continuous data has no backlog
        assert set(repl["array_connections"]) == {"peer-fb", "conn-id"}
        assert repl["array_connections"]["peer-fb"]["continuous"] == {}
        assert repl["array_connections"]["peer-fb"]["periodic"] == {
            "received_bytes_per_sec": 1.0,
            "transmitted_bytes_per_sec": 2.0,
        }
        assert (
            repl["array_connections"]["conn-id"]["continuous"]["object_backlog"][
                "bytes_count"
            ]
            == 0
        )
        assert (
            repl["targets"]["s3-target"]["aggregate"]["transmitted_bytes_per_sec"]
            == 20.0
        )

        assert set(result["filesystems"]["fs1"]) == set(PERF_FIELDS)
        assert result["filesystems"]["fs1"]["reads_per_sec"] == 1.0
        assert set(result["buckets"]["b1"]) == set(PERF_FIELDS) | {"s3"}
        assert result["buckets"]["b1"]["writes_per_sec"] == 4.0
        assert result["buckets"]["b1"]["s3"]["write_objects_per_sec"] == 4.0
        assert set(result["buckets"]["b1"]["s3"]) == set(S3_OPS_FIELDS)
        # a bucket only present in the S3-specific listing still appears
        assert set(result["buckets"]["b2"]) == {"s3"}

    def test_generate_perf_breakdown_dict_tolerates_failed_gets(self):
        blade = Mock()
        for method in (
            "get_arrays_performance",
            "get_arrays_nfs_specific_performance",
            "get_arrays_s3_specific_performance",
            "get_arrays_http_specific_performance",
            "get_arrays_performance_replication",
            "get_array_connections_performance_replication",
            "get_targets_performance_replication",
            "get_file_systems_performance",
            "get_buckets_performance",
            "get_buckets_s3_specific_performance",
        ):
            getattr(blade, method).return_value = _failed()

        result = generate_perf_breakdown_dict(blade)

        assert result == {
            "smb": {},
            "nfs_ops": {},
            "s3_ops": {},
            "http_ops": {},
            "replication": {"array_connections": {}, "targets": {}},
            "filesystems": {},
            "buckets": {},
        }

    @patch("plugins.modules.purefb_info.generate_perf_breakdown_dict")
    def test_generate_perf_dict_merges_breakdown(self, mock_breakdown):
        blade = Mock()
        sample = _Row(
            bytes_per_op=1,
            bytes_per_read=2,
            bytes_per_write=3,
            read_bytes_per_sec=4,
            reads_per_sec=5,
            usec_per_other_op=6,
            usec_per_read_op=7,
            usec_per_write_op=8,
            write_bytes_per_sec=9,
            writes_per_sec=10,
        )
        blade.get_arrays_performance.return_value = _ok([sample])
        blade.get_array_connections_performance_replication.return_value.total_item_count = (
            0
        )
        mock_breakdown.return_value = {"smb": {"reads_per_sec": 0.0}}

        result = generate_perf_dict(blade)

        mock_breakdown.assert_called_once_with(blade)
        assert result["aggregate"]["reads_per_sec"] == 5
        assert result["nfs"]["writes_per_sec"] == 10
        assert result["smb"] == {"reads_per_sec": 0.0}

    @patch("plugins.modules.purefb_info.LooseVersion", _Version)
    def test_generate_clients_dict_before_2_18_reports_nfs_only(self):
        blade = Mock()
        blade.get_arrays_clients_performance.return_value = _ok(
            [_Row(name="10.0.0.1:2049", reads_per_sec=9.0, time=5)]
        )

        result = generate_clients_dict(blade, "2.17")

        blade.get_arrays_clients_performance.assert_called_once_with(
            limit=CLIENTS_PERF_LIMIT
        )
        blade.get_arrays_clients_s3_specific_performance.assert_not_called()
        assert set(result) == {"nfs", "s3", "s3_ops"}
        assert set(result["nfs"]["10.0.0.1:2049"]) == set(PERF_FIELDS)
        assert result["nfs"]["10.0.0.1:2049"]["reads_per_sec"] == 9.0
        assert result["s3"] == {}
        assert result["s3_ops"] == {}

    @patch("plugins.modules.purefb_info.LooseVersion", _Version)
    def test_generate_clients_dict_from_2_18_reports_s3_clients(self):
        blade = Mock()

        def clients_performance(protocol=None, limit=None):
            assert limit == CLIENTS_PERF_LIMIT
            if protocol == "s3":
                return _ok([_Row(name="10.0.0.2:51000", writes_per_sec=3.0)])
            return _ok([_Row(name="10.0.0.1:2049", reads_per_sec=9.0)])

        blade.get_arrays_clients_performance.side_effect = clients_performance
        blade.get_arrays_clients_s3_specific_performance.return_value = _ok(
            [_Row(name="10.0.0.2:51000", write_objects_per_sec=3.0)]
        )

        result = generate_clients_dict(blade, "2.18")

        assert blade.get_arrays_clients_performance.call_count == 2
        blade.get_arrays_clients_performance.assert_any_call(limit=CLIENTS_PERF_LIMIT)
        blade.get_arrays_clients_performance.assert_any_call(
            protocol="s3", limit=CLIENTS_PERF_LIMIT
        )
        blade.get_arrays_clients_s3_specific_performance.assert_called_once_with(
            limit=CLIENTS_PERF_LIMIT
        )
        assert result["nfs"]["10.0.0.1:2049"]["reads_per_sec"] == 9.0
        assert result["s3"]["10.0.0.2:51000"]["writes_per_sec"] == 3.0
        assert set(result["s3_ops"]["10.0.0.2:51000"]) == set(S3_OPS_FIELDS)
        assert result["s3_ops"]["10.0.0.2:51000"]["write_objects_per_sec"] == 3.0

    @patch("plugins.modules.purefb_info.LooseVersion", _Version)
    def test_generate_clients_dict_tolerates_failed_gets(self):
        blade = Mock()
        blade.get_arrays_clients_performance.return_value = _failed()
        blade.get_arrays_clients_s3_specific_performance.return_value = _failed()

        result = generate_clients_dict(blade, "2.30")

        assert result == {"nfs": {}, "s3": {}, "s3_ops": {}}

    @patch("plugins.modules.purefb_info.generate_clients_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_clients_subset_is_opt_in(
        self, mock_ansible_module, mock_get_system, mock_generate_clients
    ):
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["clients"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        mock_generate_clients.return_value = {"nfs": {}, "s3": {}, "s3_ops": {}}

        main()

        mock_module.fail_json.assert_not_called()
        mock_generate_clients.assert_called_once()
        assert mock_generate_clients.call_args[0][0] is mock_blade
        info = mock_module.exit_json.call_args[1]["purefb_info"]
        assert info == {"clients": {"nfs": {}, "s3": {}, "s3_ops": {}}}

    def test_main_all_subset_excludes_clients(self):
        generators = {
            name: Mock(return_value={})
            for name in dir(purefb_info_module)
            if name.startswith("generate_")
        }
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["all"]}
        mock_module.check_mode = False
        mock_blade = Mock()

        with patch.multiple(purefb_info_module, **generators), patch.object(
            purefb_info_module, "LooseVersion", _Version
        ), patch.object(
            purefb_info_module, "get_system", return_value=mock_blade
        ), patch.object(
            purefb_info_module, "AnsibleModule", return_value=mock_module
        ), patch.object(
            purefb_info_module, "get_rest_api_version", return_value="2.30"
        ):
            main()

        mock_module.fail_json.assert_not_called()
        generators["generate_perf_dict"].assert_called_once_with(mock_blade)
        generators["generate_clients_dict"].assert_not_called()
        info = mock_module.exit_json.call_args[1]["purefb_info"]
        assert "performance" in info
        assert "clients" not in info
