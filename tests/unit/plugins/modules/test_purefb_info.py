# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_info module."""

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
    generate_bucket_access_policies_dict,
    generate_lag_dict,
    generate_subnet_dict,
    generate_bucket_cross_object_policies_dict,
    generate_network_dict,
    generate_smb_share_policies_dict,
    generate_network_access_policies_dict,
    generate_worm_data_policies_dict,
    generate_tls_policies_dict,
    generate_s3_export_policies_dict,
    generate_object_store_account_exports_dict,
    generate_object_store_virtual_hosts_dict,
    generate_realms_dict,
    generate_resource_accesses_dict,
    generate_file_repl_dict,
    generate_ad_dict,
)


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
        mock_blade.get_support.return_value.items = [mock_support]

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

        # Mock directory service roles
        mock_blade.get_directory_services_roles.return_value.items = []

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
        assert "management_directory_service" in result
        assert "array_management" in result
        cert = result["ssl_certs"]["management"]
        assert cert["certificate_type"] == "external"
        assert cert["intermediate_certificate"] == "-----BEGIN CERTIFICATE-----"

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

        result = generate_array_conn_dict(mock_blade)

        assert list(result) == ["remote-array"]
        entry = result["remote-array"]
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

        # reference-shaped subnet, no attached server
        subnet = Mock(spec=["name"])
        subnet.name = "mgmt"
        port.subnet = subnet
        port.attached_servers = []
        result = generate_network_dict(mock_blade)
        assert result["vip1"]["server"] is None
        assert result["vip1"]["attached_servers"] == []
        assert result["vip1"]["subnet"] == "mgmt"

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

        mock_blade = Mock()
        mock_blade.get_tls_policies.return_value.items = [policy]
        mock_blade.get_tls_policies_network_interfaces.return_value.items = [member]

        result = generate_tls_policies_dict(mock_blade)

        assert result["tls1"]["appliance_certificate"] == "management"
        assert result["tls1"]["min_tls_version"] == "1.2"
        assert result["tls1"]["disabled_tls_ciphers"] == ["RC4"]
        assert result["tls1"]["trusted_client_certificate_authority"] is None
        assert result["tls1"]["network_interfaces"] == ["vip1"]

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

    def test_generate_realms_and_resource_accesses(self):
        """Realms report their space and TLS policy; resource accesses map a
        scope to a resource by name and type."""
        space = Mock(spec=["total_physical", "virtual"])
        space.total_physical = 1024
        space.virtual = 2048
        tls = Mock(spec=["name"])
        tls.name = "tls1"
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
        realm.created = 1700000000000
        realm.destroyed = False
        realm.time_remaining = None
        realm.default_inbound_tls_policy = tls
        realm.space = space

        mock_blade = Mock()
        mock_blade.get_realms.return_value.items = [realm]

        result = generate_realms_dict(mock_blade)

        assert result["realm1"]["destroyed"] is False
        assert result["realm1"]["created"] is not None
        assert result["realm1"]["default_inbound_tls_policy"] == "tls1"
        assert result["realm1"]["space"]["total_physical"] == 1024
        assert result["realm1"]["space"]["virtual"] == 2048
        # fields absent from this Space version are reported as null
        assert result["realm1"]["space"]["total_used"] is None

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
