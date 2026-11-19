# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_info module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import ANY, Mock, patch, MagicMock

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
    generate_quota_policies_dict,
    generate_fs_junctions_dict,
    generate_fs_worm_policies_dict,
    generate_array_conn_dict,
    generate_all_policies_dict,
    generate_bucket_access_policies_dict,
    generate_bucket_dict,
    generate_lag_dict,
    generate_subnet_dict,
    generate_bucket_cross_object_policies_dict,
    generate_network_dict,
    generate_network_connectors_dict,
    generate_network_connector_performance_dict,
    generate_network_connector_settings_dict,
    generate_lldp_neighbors_dict,
    generate_connections_list,
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
    generate_telemetry_targets_dict,
    generate_object_store_roles_dict,
    generate_public_keys_dict,
    generate_admin_cache_dict,
    generate_management_access_policies_dict,
    generate_management_access_roles_dict,
    generate_management_authentication_policies_dict,
    generate_rapid_data_locking_dict,
    generate_certificate_uses_dict,
    generate_remote_arrays_dict,
    generate_tgroups_dict,
    generate_presets_dict,
    generate_workloads_dict,
    generate_storage_class_members_dict,
    generate_realm_connections_dict,
    generate_remote_realms_dict,
    generate_fleet_dict,
    generate_fs_repl_transfer_dict,
    generate_ad_dict,
    _maintenance_window_list,
    _reference_name,
    generate_admin_dict,
    generate_directory_service_roles_dict,
    generate_legal_holds_dict,
    generate_oidc_idps_dict,
    generate_quota_settings_dict,
    generate_support_dict,
    generate_servers_dict,
    generate_telemetry_policies_dict,
    generate_telemetry_collections_dict,
    generate_software_dict,
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


# The WORM tests compare real REST versions, so they use the collection's own
# LooseVersion instead of the module_utils mock.
from plugins.module_utils.version import LooseVersion as _RealLooseVersion


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

    @patch("plugins.modules.purefb_info.LooseVersion")
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
        mock_loose_version,
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
        # Version feature gates OFF (the config subset carries a version-gated
        # key and the network subset's connector keys need REST 2.17)
        mock_loose_version.return_value.__le__ = Mock(return_value=False)

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
        mock_generate_capacity.assert_called_once_with(mock_blade, ANY)
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

        # Mock policies with different types, named as the array names them
        mock_policy_snapshot = Mock()
        mock_policy_snapshot.policy_type = "snapshot"
        mock_policy_access = Mock()
        mock_policy_access.policy_type = "object-store-access"
        mock_policy_nfs = Mock()
        mock_policy_nfs.policy_type = "nfs-export"
        mock_policy_smb_share = Mock()
        mock_policy_smb_share.policy_type = "smb-share"
        mock_policy_smb_client = Mock()
        mock_policy_smb_client.policy_type = "smb-client"
        mock_policy_network = Mock()
        mock_policy_network.policy_type = "network-access"
        mock_policy_worm = Mock()
        mock_policy_worm.policy_type = "worm-data"
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

        # Mock syslog server settings - the SDK returns the references as dicts
        mock_syslog_settings = Mock(
            spec=["name", "ca_certificate", "ca_certificate_group"]
        )
        mock_syslog_settings.name = "management"
        mock_syslog_settings.ca_certificate = {
            "name": "global",
            "id": "cert-id",
            "resource_type": "certificates",
        }
        mock_syslog_settings.ca_certificate_group = {
            "name": None,
            "id": None,
            "resource_type": None,
        }
        mock_blade.get_syslog_servers_settings.return_value.items = [
            mock_syslog_settings
        ]

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
        assert result["syslog_settings"] == {
            "management": {"ca_certificate": "global", "ca_certificate_group": None}
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
                "admin_type",
                "authorization_model",
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
        legacy.admin_type = "local-user"
        legacy.authorization_model = "static"
        legacy.locked = False
        legacy.lockout_remaining = None
        legacy.api_token = Mock(spec=["created_at", "expires_at"])
        legacy.api_token.created_at = 1700000000000
        legacy.api_token.expires_at = 1800000000000
        policy_admin = Mock(
            spec=[
                "name",
                "is_local",
                "role",
                "management_access_policies",
                "admin_type",
                "authorization_model",
                "api_token",
            ]
        )
        policy_admin.name = "svc-backup"
        policy_admin.is_local = True
        policy_admin.role = None
        policy_admin.api_token = None
        policy_admin.management_access_policies = [
            _reference("storage_admin"),
            _reference("readonly"),
        ]
        policy_admin.admin_type = "service-account"
        policy_admin.authorization_model = "static"
        mock_blade = Mock()
        mock_blade.get_admins.return_value.items = [legacy, policy_admin]

        result = generate_admin_dict(mock_blade)

        assert result["pureuser"]["role"] == "array_admin"
        assert result["pureuser"]["management_access_policies"] == ["array_admin"]
        assert result["pureuser"]["admin_type"] == "local-user"
        assert result["pureuser"]["authorization_model"] == "static"
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
            "admin_type": "service-account",
            "authorization_model": "static",
            "locked": None,
            "lockout_remaining": None,
            "token_expires": None,
            "token_created": None,
        }

    @patch("plugins.modules.purefb_info.get_rest_api_version")
    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_admin_dict_between_2_19_and_2_24(
        self, mock_loose_version, mock_api_version
    ):
        """An array at REST 2.20 reports the policy names but not yet the
        account type or authorization model, which the API adds at 2.24"""

        class _Version:
            def __init__(self, text):
                self.parts = tuple(int(part) for part in str(text).split("."))

            def __le__(self, other):
                return self.parts <= other.parts

        mock_loose_version.side_effect = _Version
        mock_api_version.return_value = "2.20"
        admin = Mock(
            spec=["name", "public_key", "is_local", "role", "locked", "api_token"]
        )
        admin.name = "pureuser"
        admin.public_key = None
        admin.is_local = True
        admin.role = _reference("array_admin")
        admin.locked = False
        admin.api_token = None
        mock_blade = Mock()
        mock_blade.get_admins.return_value.items = [admin]

        result = generate_admin_dict(mock_blade)

        assert result["pureuser"]["management_access_policies"] == []
        assert "admin_type" not in result["pureuser"]
        assert "authorization_model" not in result["pureuser"]

    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_admin_dict_token_object_without_timestamps(
        self, mock_loose_version
    ):
        """A service account without a token carries an api_token object
        whose timestamps are null; both token fields still read None"""
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        admin = Mock(spec=["name", "is_local", "role", "api_token"])
        admin.name = "svc-backup"
        admin.is_local = True
        admin.role = _reference("readonly")
        admin.api_token = Mock(spec=["created_at", "expires_at", "token"])
        admin.api_token.created_at = None
        admin.api_token.expires_at = None
        admin.api_token.token = None
        mock_blade = Mock()
        mock_blade.get_admins.return_value.items = [admin]

        result = generate_admin_dict(mock_blade)

        assert result["svc-backup"]["token_created"] is None
        assert result["svc-backup"]["token_expires"] is None

    def test_reference_name_reads_dict_and_object_references(self):
        """_reference_name handles dict references, object references and unset values"""
        obj = Mock(spec=["as_dict", "as_object", "unset", "empty"])
        obj.as_dict = {"name": "global", "id": "x", "resource_type": "certificates"}
        ref = Mock(spec=["name"])
        ref.name = "grp"
        obj.as_object = ref
        obj.unset = {"name": None, "id": None, "resource_type": None}
        obj.empty = None
        assert _reference_name(obj, "as_dict") == "global"
        assert _reference_name(obj, "as_object") == "grp"
        assert _reference_name(obj, "unset") is None
        assert _reference_name(obj, "empty") is None
        assert _reference_name(obj, "missing") is None

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
            "get_syslog_servers_settings",
            "get_sso_oidc_idps",
            "get_directory_services_local_directory_services",
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
            "get_syslog_servers_settings",
            "get_sso_oidc_idps",
            "get_directory_services_local_directory_services",
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

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_info.get_rest_api_version",
        Mock(return_value="2.30"),
    )
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

    def test_generate_fs_junctions_dict(self):
        """Junctions are keyed by name with origin, destination, path, status."""
        origin = Mock(spec=["name"])
        origin.name = "projects"
        destination = Mock(spec=["name"])
        destination.name = "alpha"
        junction = Mock(
            spec=[
                "name",
                "origin_file_system",
                "destination_file_system",
                "junction_origin_path",
                "status",
            ]
        )
        junction.name = "projects-alpha"
        junction.origin_file_system = origin
        junction.destination_file_system = destination
        junction.junction_origin_path = "/alpha"
        junction.status = "CONNECTED"

        mock_blade = Mock()
        mock_blade.get_file_system_junctions.return_value = Mock(
            status_code=200, items=[junction]
        )

        result = generate_fs_junctions_dict(mock_blade)

        assert result == {
            "projects-alpha": {
                "origin": "projects",
                "destination": "alpha",
                "path": "/alpha",
                "status": "CONNECTED",
            }
        }

    def test_generate_fs_junctions_dict_returns_empty_when_endpoint_errors(self):
        """An error response carries no items; the key must come back empty."""
        mock_blade = Mock()
        error = Mock(spec=["status_code", "errors", "headers"])
        error.status_code = 400
        mock_blade.get_file_system_junctions.return_value = error

        assert generate_fs_junctions_dict(mock_blade) == {}

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_fs_junctions_dict")
    @patch("plugins.modules.purefb_info.generate_fs_dict")
    @patch("plugins.modules.purefb_info.generate_file_system_exports_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_filesystems_subset_includes_junctions(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_exports,
        mock_generate_fs,
        mock_generate_junctions,
        mock_loose_version,
    ):
        """The filesystems subset carries the junctions key once the array
        supports REST 2.25."""
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["filesystems"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.25"]
        # every gate is open under the LooseVersion mock, so the WORM lookup runs
        mock_blade.get_file_systems_worm_data_policies.return_value.items = []
        mock_get_system.return_value = mock_blade
        mock_loose_version.return_value.__le__ = Mock(return_value=True)

        mock_generate_exports.return_value = []
        mock_generate_fs.return_value = {}
        mock_generate_junctions.return_value = {"jn1": {"status": "CONNECTED"}}

        main()

        mock_generate_junctions.assert_called_once_with(mock_blade)
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["purefb_info"]["junctions"] == {"jn1": {"status": "CONNECTED"}}

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_fs_junctions_dict")
    @patch("plugins.modules.purefb_info.generate_fs_dict")
    @patch("plugins.modules.purefb_info.generate_file_system_exports_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_filesystems_subset_skips_junctions_below_gate(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_exports,
        mock_generate_fs,
        mock_generate_junctions,
        mock_loose_version,
    ):
        """Below REST 2.25 the junctions endpoint is never called."""
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["filesystems"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.16"]
        mock_get_system.return_value = mock_blade
        mock_loose_version.return_value.__le__ = Mock(return_value=False)

        mock_generate_fs.return_value = {}

        main()

        mock_generate_junctions.assert_not_called()
        call_args = mock_module.exit_json.call_args[1]
        assert "junctions" not in call_args["purefb_info"]

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

    @staticmethod
    def _fs_repl_transfer(name, remote, remote_snapshot):
        """Build a replica link transfer mock with the SDK model's fields."""
        transfer = Mock(
            spec=[
                "name",
                "completed",
                "data_transferred",
                "progress",
                "direction",
                "local_snapshot",
                "remote",
                "remote_snapshot",
                "started",
                "status",
            ]
        )
        transfer.name = name
        transfer.completed = 1700000100000
        transfer.data_transferred = 4096
        transfer.progress = 1.0
        transfer.direction = "outbound"
        transfer.local_snapshot = Mock(spec=[])
        transfer.remote = remote
        transfer.remote_snapshot = remote_snapshot
        transfer.started = 1700000000000
        transfer.status = "completed"
        return transfer

    @staticmethod
    def _ref(name):
        ref = Mock(spec=["name"])
        ref.name = name
        return ref

    def test_generate_fs_repl_transfer_dict_reads_transfers(self):
        """Replica link transfers are keyed by snapshot name and then by
        remote array; an empty local_snapshot reference reads as None."""
        transfer = self._fs_repl_transfer(
            "fs1.daily-1", self._ref("peer"), self._ref("fs1.daily-1")
        )
        response = Mock()
        response.status_code = 200
        response.items = [transfer]
        mock_blade = Mock()
        mock_blade.get_file_system_replica_links_transfer.return_value = response

        result = generate_fs_repl_transfer_dict(mock_blade)

        assert list(result) == ["fs1.daily-1"]
        assert list(result["fs1.daily-1"]) == ["peer"]
        entry = result["fs1.daily-1"]["peer"]
        assert entry["remote"] == "peer"
        assert entry["remote_snapshot"] == "fs1.daily-1"
        assert entry["local_snapshot"] is None
        assert entry["status"] == "completed"
        assert entry["data_transferred"] == 4096

    def test_generate_fs_repl_transfer_dict_keeps_fan_out_transfers(self):
        """The same snapshot transferring to two arrays keeps both entries,
        and unset remote or remote_snapshot references do not raise."""
        to_b = self._fs_repl_transfer(
            "fs1.daily-1", self._ref("arrayB"), self._ref("fs1.daily-1")
        )
        to_c = self._fs_repl_transfer("fs1.daily-1", self._ref("arrayC"), None)
        unset = self._fs_repl_transfer("fs2.daily-1", None, None)
        response = Mock()
        response.status_code = 200
        response.items = [to_b, to_c, unset]
        mock_blade = Mock()
        mock_blade.get_file_system_replica_links_transfer.return_value = response

        result = generate_fs_repl_transfer_dict(mock_blade)

        assert sorted(result["fs1.daily-1"]) == ["arrayB", "arrayC"]
        assert result["fs1.daily-1"]["arrayB"]["remote_snapshot"] == "fs1.daily-1"
        assert result["fs1.daily-1"]["arrayC"]["remote_snapshot"] is None
        (orphan,) = result["fs2.daily-1"].values()
        assert orphan["remote"] is None
        assert orphan["remote_snapshot"] is None
        assert orphan["status"] == "completed"

    def test_generate_fs_repl_transfer_dict_returns_empty_on_error(self):
        response = Mock()
        response.status_code = 400
        mock_blade = Mock()
        mock_blade.get_file_system_replica_links_transfer.return_value = response

        assert generate_fs_repl_transfer_dict(mock_blade) == {}

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
                "realms": [],
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

    @staticmethod
    def _worm_blade(policy_attrs=None):
        """A blade with one WORM policy worm1 whose member is fs1.

        policy_attrs adds attributes beyond the retention settings every REST
        version carries (commit_mode and autocommit_config from REST 2.29)."""
        policy_attrs = policy_attrs or {}
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
            + sorted(policy_attrs)
        )
        policy.name = "worm1"
        policy.enabled = True
        policy.is_local = True
        policy.mode = "compliance"
        policy.retention_lock = "unlocked"
        policy.default_retention = 86400000
        policy.min_retention = 60000
        policy.max_retention = 172800000
        for attr, value in policy_attrs.items():
            setattr(policy, attr, value)
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
        return mock_blade

    @staticmethod
    def _autocommit(delay_on="creation", delay_period=7200000):
        config = Mock(spec=["delay_on", "delay_period"])
        config.delay_on = delay_on
        config.delay_period = delay_period
        return config

    @patch("plugins.modules.purefb_info.LooseVersion", new=_RealLooseVersion)
    @patch("plugins.modules.purefb_info.get_rest_api_version", return_value="2.28")
    def test_generate_worm_data_policies_dict(self, mock_version):
        """WORM policies carry their retention settings and member list; an
        array below REST 2.29 has no commit mode or autocommit configuration."""
        result = generate_worm_data_policies_dict(self._worm_blade())

        assert result["worm1"]["mode"] == "compliance"
        assert result["worm1"]["default_retention"] == 86400000
        assert result["worm1"]["members"] == ["fs1"]
        assert "commit_mode" not in result["worm1"]
        assert "autocommit_config" not in result["worm1"]

    @patch("plugins.modules.purefb_info.LooseVersion", new=_RealLooseVersion)
    @patch("plugins.modules.purefb_info.get_rest_api_version", return_value="2.30")
    def test_generate_worm_data_policies_dict_reports_autocommit(self, mock_version):
        """From REST 2.29 the commit mode and the autocommit configuration are
        reported as the array returns them (delay_period in milliseconds)."""
        blade = self._worm_blade(
            {"commit_mode": "autocommit", "autocommit_config": self._autocommit()}
        )

        result = generate_worm_data_policies_dict(blade)

        assert result["worm1"]["commit_mode"] == "autocommit"
        assert result["worm1"]["autocommit_config"] == {
            "delay_on": "creation",
            "delay_period": 7200000,
        }
        assert result["worm1"]["members"] == ["fs1"]

    @patch("plugins.modules.purefb_info.LooseVersion", new=_RealLooseVersion)
    @patch("plugins.modules.purefb_info.get_rest_api_version", return_value="2.29")
    def test_generate_worm_data_policies_dict_without_autocommit_config(
        self, mock_version
    ):
        """A policy the array returns without an autocommit configuration
        still gets both keys, with None values, so consumers see one shape."""
        blade = self._worm_blade({"commit_mode": "manual", "autocommit_config": None})

        result = generate_worm_data_policies_dict(blade)

        assert result["worm1"]["commit_mode"] == "manual"
        assert result["worm1"]["autocommit_config"] == {
            "delay_on": None,
            "delay_period": None,
        }

    def test_generate_legal_holds_dict(self):
        """Legal holds carry description, realms and their held paths."""
        realm = Mock(spec=["name"])
        realm.name = "legal"
        hold = Mock(spec=["name", "description", "realms"])
        hold.name = "case-42"
        hold.description = "Litigation hold"
        hold.realms = [realm]
        other = Mock(spec=["name", "description", "realms"])
        other.name = "test"
        other.description = ""
        other.realms = []
        fs_ref = Mock(spec=["name"])
        fs_ref.name = "evidence"
        hold_ref = Mock(spec=["name"])
        hold_ref.name = "case-42"
        entity = Mock(spec=["file_system", "legal_hold", "path", "status"])
        entity.file_system = fs_ref
        entity.legal_hold = hold_ref
        entity.path = "/case-42"
        entity.status = "applied"
        orphan_ref = Mock(spec=["name"])
        orphan_ref.name = "ghost"
        orphan = Mock(spec=["file_system", "legal_hold", "path", "status"])
        orphan.file_system = fs_ref
        orphan.legal_hold = orphan_ref
        orphan.path = "/x"
        orphan.status = "releasing"

        mock_blade = Mock()
        mock_blade.get_legal_holds.return_value.items = [hold, other]
        mock_blade.get_legal_holds_held_entities.return_value.items = [
            entity,
            orphan,
        ]

        result = generate_legal_holds_dict(mock_blade)

        assert result == {
            "case-42": {
                "description": "Litigation hold",
                "realms": ["legal"],
                "held_entities": [
                    {"file_system": "evidence", "path": "/case-42", "status": "applied"}
                ],
            },
            "test": {"description": "", "realms": [], "held_entities": []},
        }

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_legal_holds_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_legal_holds_subset(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_legal_holds,
        mock_loose_version,
    ):
        """gather_subset=legal_holds returns the legal_holds section alone."""
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["legal_holds"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.17"
        mock_blade.get_versions.return_value.items = [mock_version]
        mock_get_system.return_value = mock_blade
        # version gate ON
        mock_loose_version.return_value.__le__ = Mock(return_value=True)

        mock_generate_legal_holds.return_value = {"case-42": {"held_entities": []}}

        main()

        mock_generate_legal_holds.assert_called_once_with(mock_blade)
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["purefb_info"] == {
            "legal_holds": {"case-42": {"held_entities": []}}
        }

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_legal_holds_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_legal_holds_subset_skipped_below_2_17(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_legal_holds,
        mock_loose_version,
    ):
        """gather_subset=legal_holds is silently skipped on arrays below 2.17."""
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["legal_holds"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.16"
        mock_blade.get_versions.return_value.items = [mock_version]
        mock_get_system.return_value = mock_blade
        # version gate OFF
        mock_loose_version.return_value.__le__ = Mock(return_value=False)

        main()

        mock_generate_legal_holds.assert_not_called()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["purefb_info"] == {}

    def test_generate_quota_policies_dict(self):
        """Quota policies carry their rules and attached file systems."""
        location = Mock(spec=["name"])
        location.name = "array1"
        policy = Mock(spec=["name", "enabled", "is_local", "location", "realms"])
        policy.name = "qp1"
        policy.enabled = True
        policy.is_local = True
        policy.location = location
        policy.realms = []
        policy_ref = Mock(spec=["name"])
        policy_ref.name = "qp1"
        subject = Mock(spec=["id", "name", "sid"])
        subject.id = 1001
        subject.name = ""
        subject.sid = None
        rule = Mock(
            spec=[
                "name",
                "quota_type",
                "subject",
                "quota_limit",
                "enforced",
                "notifications",
                "index",
                "policy",
            ]
        )
        rule.name = "qp1.1"
        rule.quota_type = "user"
        rule.subject = subject
        rule.quota_limit = 10737418240
        rule.enforced = True
        rule.notifications = "Account"
        rule.index = 1
        rule.policy = policy_ref
        # a rule of a policy that is not in the listing is ignored
        other_ref = Mock(spec=["name"])
        other_ref.name = "other"
        stray = Mock(spec=["name", "policy"])
        stray.name = "other.1"
        stray.policy = other_ref
        member_ref = Mock(spec=["name"])
        member_ref.name = "fs1"
        member = Mock(spec=["member", "policy"])
        member.member = member_ref
        member.policy = policy_ref

        mock_blade = Mock()
        mock_blade.get_user_group_quota_policies.return_value.items = [policy]
        mock_blade.get_user_group_quota_policies_rules.return_value.items = [
            rule,
            stray,
        ]
        mock_blade.get_user_group_quota_policies_members.return_value.items = [member]

        result = generate_quota_policies_dict(mock_blade)

        assert result == {
            "qp1": {
                "local": True,
                "enabled": True,
                "location": "array1",
                "realms": [],
                "rules": [
                    {
                        "name": "qp1.1",
                        "type": "user",
                        "subject": {"id": 1001, "name": "", "sid": None},
                        "quota_limit": 10737418240,
                        "enforced": True,
                        "notifications": "Account",
                        "index": 1,
                    }
                ],
                "members": ["fs1"],
            }
        }

    @staticmethod
    def _quota_view_filesystem():
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
        return fs1

    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_fs_dict_adds_quota_policy_view(self, mock_loose_version):
        """At REST 2.25 each file system reports its attached quota policy and
        the per-user / per-group usage limited by it."""
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        mock_blade = Mock()
        mock_blade.get_file_systems.return_value.items = [self._quota_view_filesystem()]
        mock_blade.get_quotas_groups.return_value.items = []
        mock_blade.get_quotas_users.return_value.items = []

        policy_ref = Mock(spec=["name"])
        policy_ref.name = "qp1"
        member_ref = Mock(spec=["name"])
        member_ref.name = "fs1"
        attached = Mock(spec=["policy", "member"])
        attached.policy = policy_ref
        attached.member = member_ref
        # another file system's attachment must not be mistaken for fs1's
        other_policy = Mock(spec=["name"])
        other_policy.name = "qp2"
        other_member = Mock(spec=["name"])
        other_member.name = "fs2"
        other = Mock(spec=["policy", "member"])
        other.policy = other_policy
        other.member = other_member
        attached_res = Mock()
        attached_res.status_code = 200
        attached_res.items = [other, attached]
        mock_blade.get_file_systems_user_group_quota_policies.return_value = (
            attached_res
        )

        user_subject = Mock(spec=["id", "name", "sid"])
        user_subject.id = 1001
        user_subject.name = ""
        user_subject.sid = None
        limited_by = Mock(spec=["policy", "rule_name"])
        limited_by.policy = policy_ref
        limited_by.rule_name = "qp1.1"
        user = Mock(
            spec=["user", "quota_limit", "usage", "percentage_used", "limited_by"]
        )
        user.user = user_subject
        user.quota_limit = 10737418240
        user.usage = 94371840
        user.percentage_used = 0.0088
        user.limited_by = limited_by
        users_res = Mock()
        users_res.status_code = 200
        users_res.items = [user]
        mock_blade.get_file_systems_users.return_value = users_res
        # an error on the groups view is tolerated (destroyed file systems)
        groups_res = Mock()
        groups_res.status_code = 400
        groups_res.items = []
        mock_blade.get_file_systems_groups.return_value = groups_res

        result = generate_fs_dict(mock_blade, api_version="2.25")

        assert result["fs1"]["quota_policy"] == "qp1"
        assert result["fs1"]["policy_quotas"]["users"] == [
            {
                "user": {"id": 1001, "name": "", "sid": None},
                "quota_limit": 10737418240,
                "usage": 94371840,
                "percentage_used": 0.0088,
                "limited_by": {"policy": "qp1", "rule_name": "qp1.1"},
            }
        ]
        assert result["fs1"]["policy_quotas"]["groups"] == []
        mock_blade.get_file_systems_users.assert_called_once_with(
            file_system_names=["fs1"]
        )
        # the attachment listing is fetched once, not once per file system
        mock_blade.get_file_systems_user_group_quota_policies.assert_called_once_with()
        # legacy keys are still present
        assert result["fs1"]["user_quotas"] == {}

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_info.get_rest_api_version",
        Mock(return_value="2.24"),
    )
    def test_generate_fs_dict_without_api_version_skips_quota_view(self):
        """Without an api_version (pre-2.25 callers) the quota-policy GETs are
        never issued and the new keys are absent."""
        mock_blade = Mock()
        mock_blade.get_file_systems.return_value.items = [self._quota_view_filesystem()]
        mock_blade.get_quotas_groups.return_value.items = []
        mock_blade.get_quotas_users.return_value.items = []

        result = generate_fs_dict(mock_blade)

        assert "quota_policy" not in result["fs1"]
        assert "policy_quotas" not in result["fs1"]
        mock_blade.get_file_systems_users.assert_not_called()
        mock_blade.get_file_systems_user_group_quota_policies.assert_not_called()

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
                "realms": [],
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
            "realms": [],
        }
        assert result["s3.old.example.com"] == {
            "hostname": "s3.old.example.com",
            "attached_servers": [],
            "realms": [],
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

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    def test_generate_bucket_dict_reports_lifecycle_v2_fields(self):
        """Lifecycle rules report keep_previous_versions_count and tags.

        Both fields are on the legacy /lifecycle-rules response from REST 2.29
        and are read via getattr, so a rule from an older array yields None
        and an empty list instead of an AttributeError. The expiry date is
        rendered in UTC, the zone the modules write it in.
        """
        bucket = Mock()
        bucket.name = "bkt"
        bucket.id = "bkt-id"
        bucket.destroyed = False

        tag = Mock()
        tag.key = "env"
        tag.value = "dev"
        rule = Mock()
        rule.bucket.name = "bkt"
        rule.rule_id = "rule1"
        rule.keep_previous_version_for = 2 * 86400000
        rule.keep_current_version_for = None
        rule.abort_incomplete_multipart_uploads_after = None
        rule.keep_current_version_until = None
        rule.prefix = "logs/"
        rule.enabled = True
        rule.cleanup_expired_object_delete_marker = False
        rule.keep_previous_versions_count = 3
        rule.tags = [tag]

        legacy_fields = [
            "bucket",
            "rule_id",
            "keep_previous_version_for",
            "keep_current_version_for",
            "abort_incomplete_multipart_uploads_after",
            "keep_current_version_until",
            "prefix",
            "enabled",
            "cleanup_expired_object_delete_marker",
        ]
        legacy_rule = Mock(spec=legacy_fields)
        legacy_rule.bucket = Mock()
        legacy_rule.bucket.name = "bkt"
        legacy_rule.rule_id = "legacy"
        legacy_rule.keep_previous_version_for = None
        legacy_rule.keep_current_version_for = 30 * 86400000
        legacy_rule.abort_incomplete_multipart_uploads_after = None
        legacy_rule.keep_current_version_until = 1893456000000
        legacy_rule.prefix = None
        legacy_rule.enabled = True
        legacy_rule.cleanup_expired_object_delete_marker = False

        mock_blade = Mock()
        mock_blade.get_buckets.return_value.items = [bucket]
        mock_blade.get_lifecycle_rules.return_value.items = [rule, legacy_rule]

        result = generate_bucket_dict(mock_blade, "2.30")

        mock_blade.get_lifecycle_rules.assert_called_once_with(bucket_ids=["bkt-id"])
        rules = result["bkt"]["lifecycle_rules"]
        assert rules["rule1"]["keep_previous_version_for (days)"] == 2
        assert rules["rule1"]["keep_previous_versions_count"] == 3
        assert rules["rule1"]["tags"] == [{"key": "env", "value": "dev"}]
        assert rules["legacy"]["keep_current_version_for (days)"] == 30
        assert rules["legacy"]["keep_current_version_until"] == "2030-01-01"
        assert rules["legacy"]["keep_previous_versions_count"] is None
        assert rules["legacy"]["tags"] == []

    # ---------------- telemetry subset ----------------

    def test_generate_telemetry_targets_dict(self):
        """Telemetry targets report settings, reference names and attributes."""
        source = Mock(spec=["name"])
        source.name = "data-vip"
        attr = Mock(spec=["key", "value"])
        attr.key = "env"
        attr.value = "prod"
        target = Mock(
            spec=[
                "name",
                "enabled",
                "endpoint",
                "transport",
                "vendor",
                "source",
                "ca_certificate",
                "ca_certificate_group",
                "client_certificate",
                "api_token",
                "resource_attributes",
            ]
        )
        target.name = "otel"
        target.enabled = True
        target.endpoint = "collector.example.com:4318/v1/metrics"
        target.transport = "otlp-http-protobuf-without-tls"
        target.vendor = "generic-otlp"
        target.source = source
        # unset references come back as empty objects
        target.ca_certificate = {}
        target.ca_certificate_group = {}
        target.client_certificate = {}
        target.api_token = "***"
        target.resource_attributes = [attr]

        mock_blade = Mock()
        mock_blade.get_telemetry_targets.return_value.items = [target]

        result = generate_telemetry_targets_dict(mock_blade)

        assert result["otel"]["endpoint"] == "collector.example.com:4318/v1/metrics"
        assert result["otel"]["transport"] == "otlp-http-protobuf-without-tls"
        assert result["otel"]["source"] == "data-vip"
        assert result["otel"]["ca_certificate"] is None
        assert result["otel"]["api_token_configured"] is True
        assert result["otel"]["resource_attributes"] == [
            {"key": "env", "value": "prod"}
        ]

    def test_generate_telemetry_policies_dict(self):
        """Telemetry policies embed their rules and targets; member arrays
        come from the /arrays membership endpoint."""
        collection = Mock(spec=["name"])
        collection.name = "_device_perf_metrics"
        rule = Mock(spec=["name", "collection", "resolution", "index"])
        rule.name = "pol1.1"
        rule.collection = collection
        rule.resolution = 30000
        rule.index = 1
        target = Mock(spec=["name"])
        target.name = "prometheus"
        location = Mock(spec=["name"])
        location.name = "fb1"
        policy = Mock(
            spec=[
                "name",
                "enabled",
                "is_local",
                "location",
                "realms",
                "version",
                "rules",
                "targets",
            ]
        )
        policy.name = "pol1"
        policy.enabled = True
        policy.is_local = True
        policy.location = location
        policy.realms = []
        policy.version = "v1"
        policy.rules = [rule]
        policy.targets = [target]
        array_ref = Mock(spec=["name"])
        array_ref.name = "fb1"
        policy_ref = Mock(spec=["name"])
        policy_ref.name = "pol1"
        member = Mock(spec=["member", "policy"])
        member.member = array_ref
        member.policy = policy_ref
        stray_ref = Mock(spec=["name"])
        stray_ref.name = "unknown"
        stray = Mock(spec=["member", "policy"])
        stray.member = array_ref
        stray.policy = stray_ref

        mock_blade = Mock()
        mock_blade.get_telemetry_metrics_policies.return_value.items = [policy]
        mock_blade.get_telemetry_metrics_policies_arrays.return_value.items = [
            member,
            stray,
        ]

        result = generate_telemetry_policies_dict(mock_blade)

        assert result == {
            "pol1": {
                "enabled": True,
                "is_local": True,
                "location": "fb1",
                "realms": [],
                "version": "v1",
                "targets": ["prometheus"],
                "rules": [
                    {
                        "name": "pol1.1",
                        "collection": "_device_perf_metrics",
                        "resolution": 30000,
                        "index": 1,
                    }
                ],
                "arrays": ["fb1"],
            }
        }

    def test_generate_telemetry_collections_dict(self):
        """Collections report their resolutions as returned and the metrics
        grouped under them."""
        collection = Mock(spec=["name", "default_resolution", "supported_resolutions"])
        collection.name = "_device_perf_metrics"
        collection.default_resolution = 30000
        collection.supported_resolutions = [30000, 300000]
        group = Mock(spec=["name"])
        group.name = "_device_perf_metrics"
        metric = Mock(spec=["name"])
        metric.name = "storage.device.iops"
        membership = Mock(spec=["group", "member"])
        membership.group = group
        membership.member = metric

        mock_blade = Mock()
        mock_blade.get_telemetry_metrics_collections.return_value.items = [collection]
        mock_blade.get_telemetry_metrics_collections_metrics.return_value.items = [
            membership
        ]

        result = generate_telemetry_collections_dict(mock_blade)

        assert result == {
            "_device_perf_metrics": {
                "default_resolution": 30000,
                "supported_resolutions": [30000, 300000],
                "metrics": ["storage.device.iops"],
            }
        }

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_telemetry_collections_dict")
    @patch("plugins.modules.purefb_info.generate_telemetry_policies_dict")
    @patch("plugins.modules.purefb_info.generate_telemetry_targets_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_telemetry_subset(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_targets,
        mock_generate_policies,
        mock_generate_collections,
        mock_loose_version,
    ):
        """gather_subset=telemetry returns the three telemetry keys when the
        array supports REST 2.29."""
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["telemetry"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.30"
        mock_blade.get_versions.return_value.items = [mock_version]
        mock_get_system.return_value = mock_blade
        # version gates ON
        mock_loose_version.return_value.__le__ = Mock(return_value=True)

        mock_generate_targets.return_value = {"prometheus": {}}
        mock_generate_policies.return_value = {"pol1": {}}
        mock_generate_collections.return_value = {"_device_perf_metrics": {}}

        main()

        mock_generate_targets.assert_called_once_with(mock_blade)
        mock_generate_policies.assert_called_once_with(mock_blade)
        mock_generate_collections.assert_called_once_with(mock_blade)
        info = mock_module.exit_json.call_args[1]["purefb_info"]
        assert info["telemetry_targets"] == {"prometheus": {}}
        assert info["telemetry_policies"] == {"pol1": {}}
        assert info["telemetry_collections"] == {"_device_perf_metrics": {}}
        assert "default" not in info

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_telemetry_targets_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_telemetry_subset_below_required_version(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_targets,
        mock_loose_version,
    ):
        """Below REST 2.29 the telemetry keys are simply absent."""
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["telemetry"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.21"
        mock_blade.get_versions.return_value.items = [mock_version]
        mock_get_system.return_value = mock_blade
        # version gates OFF
        mock_loose_version.return_value.__le__ = Mock(return_value=False)

        main()

        mock_generate_targets.assert_not_called()
        info = mock_module.exit_json.call_args[1]["purefb_info"]
        assert "telemetry_targets" not in info

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_telemetry_targets_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_telemetry_subset_below_gate(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_telemetry,
        mock_loose_version,
    ):
        """gather_subset=telemetry is silent on arrays below REST 2.29."""
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["telemetry"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        # version gates OFF
        mock_loose_version.return_value.__le__ = Mock(return_value=False)

        main()

        mock_generate_telemetry.assert_not_called()
        call_args = mock_module.exit_json.call_args[1]
        assert "telemetry_targets" not in call_args["purefb_info"]

    def test_generate_object_store_roles_dict(self):
        """Roles are keyed by full name with their attached access policies."""
        account = Mock(spec=["name"])
        account.name = "acme"
        entity = Mock(spec=["name"])
        entity.name = "idp1"
        role = Mock(
            spec=[
                "name",
                "account",
                "created",
                "max_session_duration",
                "prn",
                "trusted_entities",
            ]
        )
        role.name = "acme/analytics"
        role.account = account
        role.created = 1700000000000
        role.max_session_duration = 7200000
        role.prn = "prn:pure:fb:test:role/acme/analytics"
        role.trusted_entities = [entity]

        link = Mock(spec=["member", "policy"])
        link.member = Mock(spec=["name"])
        link.member.name = "acme/analytics"
        link.policy = Mock(spec=["name"])
        link.policy.name = "pure:policy/object-read"
        stray = Mock(spec=["member", "policy"])
        stray.member = Mock(spec=["name"])
        stray.member.name = "other/role"
        stray.policy = Mock(spec=["name"])
        stray.policy.name = "pure:policy/object-list"

        mock_blade = Mock()
        mock_blade.get_object_store_roles.return_value.status_code = 200
        mock_blade.get_object_store_roles.return_value.items = [role]
        links = mock_blade.get_object_store_roles_object_store_access_policies
        links.return_value.status_code = 200
        links.return_value.items = [link, stray]

        result = generate_object_store_roles_dict(mock_blade)

        assert result == {
            "acme/analytics": {
                "account": "acme",
                "created": 1700000000000,
                "max_session_duration": 7200000,
                "prn": "prn:pure:fb:test:role/acme/analytics",
                "trusted_entities": ["idp1"],
                "access_policies": ["pure:policy/object-read"],
            }
        }

    def test_generate_object_store_roles_dict_empty_on_error(self):
        """A failed roles GET yields an empty dict instead of raising."""
        mock_blade = Mock()
        mock_blade.get_object_store_roles.return_value.status_code = 400

        assert generate_object_store_roles_dict(mock_blade) == {}
        mock_blade.get_object_store_roles_object_store_access_policies.assert_not_called()

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_object_store_roles_dict")
    @patch("plugins.modules.purefb_info.generate_object_store_account_exports_dict")
    @patch("plugins.modules.purefb_info.generate_object_store_accounts_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_accounts_subset_includes_object_store_roles(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_accounts,
        mock_generate_exports,
        mock_generate_roles,
        mock_loose_version,
    ):
        """gather_subset=accounts adds object_store_roles on REST 2.17+."""
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["accounts"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.30"
        mock_blade.get_versions.return_value.items = [mock_version]
        mock_get_system.return_value = mock_blade
        # version gates ON
        mock_loose_version.return_value.__le__ = Mock(return_value=True)

        mock_generate_accounts.return_value = {"acme": {}}
        mock_generate_exports.return_value = {}
        mock_generate_roles.return_value = {"acme/analytics": {"account": "acme"}}

        main()

        mock_generate_roles.assert_called_once_with(mock_blade)
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["purefb_info"]["accounts"] == {"acme": {}}
        assert call_args["purefb_info"]["object_store_roles"] == {
            "acme/analytics": {"account": "acme"}
        }

    # ------------------------------------------------------------------
    # security and identity read-back
    # ------------------------------------------------------------------

    @staticmethod
    def _typed_ref(name, resource_type=None):
        ref = Mock(spec=["name", "resource_type"])
        ref.name = name
        ref.resource_type = resource_type
        return ref

    @staticmethod
    def _response(items, status_code=200):
        res = Mock(spec=["status_code", "items"])
        res.status_code = status_code
        res.items = items
        return res

    def test_generate_admin_cache_dict_reads_policies_and_null_role(self):
        """Cached admins report their policies; role is null for a custom
        policy; the cache is read without a refresh."""
        entry = Mock(
            spec=[
                "name",
                "authorization_model",
                "management_access_policies",
                "role",
                "time",
            ]
        )
        entry.name = "svc-ansible"
        entry.authorization_model = "dynamic"
        entry.management_access_policies = [
            self._typed_ref("ops_admin", "management-access-policies")
        ]
        entry.role = None
        entry.time = 1700000000000
        mock_blade = Mock()
        mock_blade.get_admins_cache.return_value = self._response([entry])

        result = generate_admin_cache_dict(mock_blade)

        mock_blade.get_admins_cache.assert_called_once_with()
        assert result["svc-ansible"]["authorization_model"] == "dynamic"
        assert result["svc-ansible"]["management_access_policies"] == ["ops_admin"]
        assert result["svc-ansible"]["role"] is None
        assert result["svc-ansible"]["time"] is not None

    def test_generate_admin_cache_dict_returns_empty_on_error(self):
        mock_blade = Mock()
        mock_blade.get_admins_cache.return_value = self._response([], 400)

        assert generate_admin_cache_dict(mock_blade) == {}

    def test_generate_management_access_policies_dict_reports_rules_and_members(
        self,
    ):
        """Policies carry their rules in order and the members that use them;
        a member of an unknown policy is ignored."""
        rule = Mock(spec=["name", "index", "role", "scope"])
        rule.name = "readonly.1"
        rule.index = 1
        rule.role = self._typed_ref("viewer", "management-access-policies/roles")
        rule.scope = self._typed_ref("array1", "arrays")
        policy = Mock(
            spec=[
                "name",
                "enabled",
                "is_local",
                "location",
                "aggregation_strategy",
                "realms",
                "rules",
            ]
        )
        policy.name = "readonly"
        policy.enabled = True
        policy.is_local = True
        policy.location = self._typed_ref("array1", "arrays")
        policy.aggregation_strategy = "least-common-permission"
        policy.realms = []
        policy.rules = [rule]
        member = Mock(spec=["member", "policy"])
        member.member = self._typed_ref("pureuser", "admins")
        member.policy = self._typed_ref("readonly", "management-access-policies")
        stray = Mock(spec=["member", "policy"])
        stray.member = self._typed_ref("test", "directory-services/roles")
        stray.policy = self._typed_ref("gone", "management-access-policies")
        mock_blade = Mock()
        mock_blade.get_management_access_policies.return_value = self._response(
            [policy]
        )
        mock_blade.get_management_access_policies_members.return_value = self._response(
            [member, stray]
        )

        result = generate_management_access_policies_dict(mock_blade)

        assert result["readonly"]["enabled"] is True
        assert result["readonly"]["location"] == "array1"
        assert result["readonly"]["aggregation_strategy"] == "least-common-permission"
        assert result["readonly"]["realms"] == []
        assert result["readonly"]["rules"] == [
            {
                "name": "readonly.1",
                "index": 1,
                "role": "viewer",
                "scope": "array1",
                "scope_type": "arrays",
            }
        ]
        assert result["readonly"]["members"] == [
            {"name": "pureuser", "resource_type": "admins"}
        ]

    def test_generate_management_access_policies_dict_tolerates_member_error(self):
        policy = Mock(
            spec=[
                "name",
                "enabled",
                "is_local",
                "location",
                "aggregation_strategy",
                "realms",
                "rules",
            ]
        )
        policy.name = "readonly"
        policy.enabled = True
        policy.is_local = True
        policy.location = None
        policy.aggregation_strategy = None
        policy.realms = None
        policy.rules = None
        mock_blade = Mock()
        mock_blade.get_management_access_policies.return_value = self._response(
            [policy]
        )
        mock_blade.get_management_access_policies_members.return_value = self._response(
            [], 400
        )

        result = generate_management_access_policies_dict(mock_blade)

        assert result["readonly"]["rules"] == []
        assert result["readonly"]["members"] == []
        assert result["readonly"]["location"] is None

    def test_generate_management_access_roles_dict(self):
        role = Mock(spec=["name", "description", "pure_defined"])
        role.name = "admin"
        role.description = "Grants full administrative rights within a scope."
        role.pure_defined = True
        mock_blade = Mock()
        mock_blade.get_management_access_policies_roles.return_value = self._response(
            [role]
        )

        result = generate_management_access_roles_dict(mock_blade)

        assert result == {
            "admin": {
                "description": "Grants full administrative rights within a scope.",
                "pure_defined": True,
            }
        }

    def test_generate_management_authentication_policies_dict(self):
        """The SSH methods and the arrays the policy applies to are reported;
        a policy without an SSH section gives empty method lists."""
        ssh = Mock(spec=["allowed_methods", "required_methods"])
        ssh.allowed_methods = ["default"]
        ssh.required_methods = None
        policy = Mock(spec=["name", "enabled", "is_local", "location", "realms", "ssh"])
        policy.name = "default-authentication-policy"
        policy.enabled = True
        policy.is_local = True
        policy.location = self._typed_ref("array1", "arrays")
        policy.realms = [self._typed_ref("realm1", "realms")]
        policy.ssh = ssh
        bare = Mock(spec=["name", "enabled", "is_local", "location", "realms", "ssh"])
        bare.name = "bare"
        bare.enabled = False
        bare.is_local = True
        bare.location = None
        bare.realms = None
        bare.ssh = None
        member = Mock(spec=["member", "policy"])
        member.member = self._typed_ref("array1", "arrays")
        member.policy = self._typed_ref(
            "default-authentication-policy", "management-authentication-policies"
        )
        mock_blade = Mock()
        mock_blade.get_management_authentication_policies.return_value = self._response(
            [policy, bare]
        )
        mock_blade.get_management_authentication_policies_members.return_value = (
            self._response([member])
        )

        result = generate_management_authentication_policies_dict(mock_blade)

        assert result["default-authentication-policy"]["ssh"] == {
            "allowed_methods": ["default"],
            "required_methods": [],
        }
        assert result["default-authentication-policy"]["realms"] == ["realm1"]
        assert result["default-authentication-policy"]["members"] == [
            {"name": "array1", "resource_type": "arrays"}
        ]
        assert result["bare"]["ssh"] == {"allowed_methods": [], "required_methods": []}
        assert result["bare"]["members"] == []

    def test_generate_rapid_data_locking_dict(self):
        rdl = Mock(spec=["enabled", "kmip_server"])
        rdl.enabled = False
        rdl.kmip_server = self._typed_ref(None)
        mock_blade = Mock()
        mock_blade.get_rapid_data_locking.return_value = self._response([rdl])

        assert generate_rapid_data_locking_dict(mock_blade) == {
            "enabled": False,
            "kmip_server": None,
        }

    def test_generate_rapid_data_locking_dict_empty_on_error_or_no_items(self):
        mock_blade = Mock()
        mock_blade.get_rapid_data_locking.return_value = self._response([], 400)
        assert generate_rapid_data_locking_dict(mock_blade) == {}
        mock_blade.get_rapid_data_locking.return_value = self._response([])
        assert generate_rapid_data_locking_dict(mock_blade) == {}

    def test_generate_certificate_uses_dict_groups_uses_per_certificate(self):
        use1 = Mock(spec=["name", "resource_type", "remote"])
        use1.name = "default-tls-policy"
        use1.resource_type = "tls-policies"
        use1.remote = self._typed_ref(None)
        use2 = Mock(spec=["name", "resource_type", "remote"])
        use2.name = "management"
        use2.resource_type = "syslog-servers/settings"
        use2.remote = None
        item1 = Mock(spec=["name", "group", "use"])
        item1.name = "global"
        item1.group = self._typed_ref(None)
        item1.use = use1
        item2 = Mock(spec=["name", "group", "use"])
        item2.name = "global"
        item2.group = self._typed_ref("ca-group", "certificate-groups")
        item2.use = use2
        mock_blade = Mock()
        mock_blade.get_certificates_uses.return_value = self._response([item1, item2])

        result = generate_certificate_uses_dict(mock_blade)

        assert result == {
            "global": [
                {
                    "name": "default-tls-policy",
                    "resource_type": "tls-policies",
                    "remote": None,
                    "group": None,
                },
                {
                    "name": "management",
                    "resource_type": "syslog-servers/settings",
                    "remote": None,
                    "group": "ca-group",
                },
            ]
        }

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_rapid_data_locking_dict")
    @patch("plugins.modules.purefb_info.generate_certificate_uses_dict")
    @patch("plugins.modules.purefb_info.generate_admin_cache_dict")
    @patch("plugins.modules.purefb_info.generate_config_dict")
    @patch("plugins.modules.purefb_info.generate_admin_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_admins_and_config_add_cache_uses_and_rdl(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_admin,
        mock_generate_config,
        mock_admin_cache,
        mock_certificate_uses,
        mock_rdl,
        mock_loose_version,
    ):
        """admins gains admin_cache; config gains certificate_uses and, with
        the KMIP gate open, rapid_data_locking next to its existing keys."""
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["admins", "config"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        mock_generate_admin.return_value = {"pureuser": {}}
        mock_generate_config.return_value = {"dns": {}}
        mock_admin_cache.return_value = {"svc-ansible": {}}
        mock_certificate_uses.return_value = {"global": []}
        mock_rdl.return_value = {"enabled": False, "kmip_server": None}

        main()

        info = mock_module.exit_json.call_args[1]["purefb_info"]
        assert info["admins"] == {"pureuser": {}}
        assert info["admin_cache"] == {"svc-ansible": {}}
        assert info["config"] == {
            "dns": {},
            "certificate_uses": {"global": []},
            "rapid_data_locking": {"enabled": False, "kmip_server": None},
        }

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_policies_subset_adds_management_policies(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["policies"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        generators = {
            name: Mock(return_value={})
            for name in (
                "generate_all_policies_dict",
                "generate_policies_dict",
                "generate_object_store_access_policies_dict",
                "generate_bucket_access_policies_dict",
                "generate_bucket_cross_object_policies_dict",
                "generate_nfs_export_policies_dict",
                "generate_smb_client_policies_dict",
                "generate_smb_share_policies_dict",
                "generate_network_access_policies_dict",
                "generate_worm_data_policies_dict",
                "generate_password_policies_dict",
                "generate_fleet_dict",
                "generate_tls_policies_dict",
                "generate_s3_export_policies_dict",
                "generate_ssh_ca_policies_dict",
                "generate_quota_policies_dict",
                "generate_eviction_policies_dict",
            )
        }
        generators["generate_management_access_policies_dict"] = Mock(
            return_value={"readonly": {}}
        )
        generators["generate_management_authentication_policies_dict"] = Mock(
            return_value={"default-authentication-policy": {}}
        )
        generators["generate_management_access_roles_dict"] = Mock(
            return_value={"admin": {}}
        )

        with patch.multiple("plugins.modules.purefb_info", **generators):
            main()

        info = mock_module.exit_json.call_args[1]["purefb_info"]
        assert info["management_access_policies"] == {"readonly": {}}
        assert info["management_authentication_policies"] == {
            "default-authentication-policy": {}
        }
        assert info["management_access_roles"] == {"admin": {}}
        for name in (
            "generate_management_access_policies_dict",
            "generate_management_authentication_policies_dict",
            "generate_management_access_roles_dict",
        ):
            generators[name].assert_called_once_with(mock_blade)

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_new_keys_absent_below_their_versions(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """With every version gate closed none of the gated keys appear and
        none of the gated getters is called; the ungated ones still are."""
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["policies", "fleet", "realms"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        generators = {
            name: Mock(return_value={})
            for name in (
                "generate_all_policies_dict",
                "generate_policies_dict",
                "generate_object_store_access_policies_dict",
                "generate_nfs_export_policies_dict",
                "generate_management_access_policies_dict",
                "generate_management_authentication_policies_dict",
                "generate_management_access_roles_dict",
                "generate_remote_arrays_dict",
                "generate_presets_dict",
                "generate_workloads_dict",
                "generate_tgroups_dict",
                "generate_storage_class_members_dict",
                "generate_realm_connections_dict",
                "generate_remote_realms_dict",
            )
        }

        with patch.multiple("plugins.modules.purefb_info", **generators):
            main()

        info = mock_module.exit_json.call_args[1]["purefb_info"]
        for key in (
            "management_access_policies",
            "management_authentication_policies",
            "management_access_roles",
            "fleet",
            "presets",
            "workloads",
            "tgroups",
            "storage_class_members",
            "realm_connections",
            "remote_realms",
        ):
            assert key not in info
        for name in (
            "generate_management_access_policies_dict",
            "generate_remote_arrays_dict",
            "generate_presets_dict",
            "generate_workloads_dict",
            "generate_tgroups_dict",
            "generate_storage_class_members_dict",
            "generate_realm_connections_dict",
            "generate_remote_realms_dict",
        ):
            generators[name].assert_not_called()
        generators["generate_all_policies_dict"].assert_called_once_with(mock_blade)

    # ------------------------------------------------------------------
    # fleet read-back
    # ------------------------------------------------------------------

    @staticmethod
    def _error_response(status_code=400):
        """A refused read: pypureclient's ErrorResponse has no ``items``"""
        res = Mock(spec=["status_code", "errors", "headers"])
        res.status_code = status_code
        res.errors = []
        res.headers = {}
        return res

    def test_generate_fleet_dict_reports_members(self):
        fleet = Mock(spec=["name"])
        fleet.name = "fleet1"
        member1 = Mock(spec=["member", "status", "status_details"])
        member1.member = self._typed_ref("array1", "arrays")
        member1.status = "joined"
        member1.status_details = None
        member2 = Mock(spec=["member", "status", "status_details"])
        member2.member = self._typed_ref("array2", "arrays")
        member2.status = "joining"
        member2.status_details = "waiting for key exchange"
        mock_blade = Mock()
        mock_blade.get_fleets.return_value = self._response([fleet])
        mock_blade.get_fleets_members.return_value = self._response([member1, member2])

        result = generate_fleet_dict(mock_blade)

        assert result == {
            "fleet1": {
                "members": {
                    "array1": {"status": "joined", "status_details": None},
                    "array2": {
                        "status": "joining",
                        "status_details": "waiting for key exchange",
                    },
                }
            }
        }

    def test_generate_fleet_dict_not_in_fleet(self):
        """An array that is not in a fleet answers with no items; the
        members are not asked for."""
        mock_blade = Mock()
        mock_blade.get_fleets.return_value = self._response([])

        assert generate_fleet_dict(mock_blade) == {}
        mock_blade.get_fleets_members.assert_not_called()

    def test_generate_fleet_dict_fleets_read_refused(self):
        """A refused /fleets read returns an empty fleet key rather than
        failing on the missing ``items`` of the error response."""
        mock_blade = Mock()
        mock_blade.get_fleets.return_value = self._error_response()

        assert generate_fleet_dict(mock_blade) == {}
        mock_blade.get_fleets_members.assert_not_called()

    def test_generate_fleet_dict_members_read_refused(self):
        """A refused /fleets/members read keeps the fleet with no members."""
        fleet = Mock(spec=["name"])
        fleet.name = "fleet1"
        mock_blade = Mock()
        mock_blade.get_fleets.return_value = self._response([fleet])
        mock_blade.get_fleets_members.return_value = self._error_response()

        assert generate_fleet_dict(mock_blade) == {"fleet1": {"members": {}}}

    def test_generate_remote_arrays_dict_requires_current_fleet_only(self):
        array = Mock(
            spec=[
                "name",
                "os",
                "version",
                "model",
                "api_versions",
                "is_local",
                "topology_group",
            ]
        )
        array.name = "array1"
        array.os = "Purity//FB"
        array.version = "4.8.8"
        array.model = "FlashBlade//S200"
        array.api_versions = ["2.29", "2.30"]
        array.is_local = True
        array.topology_group = self._typed_ref("tg1", "topology-groups")
        mock_blade = Mock()
        mock_blade.get_remote_arrays.return_value = self._response([array])

        result = generate_remote_arrays_dict(mock_blade)

        mock_blade.get_remote_arrays.assert_called_once_with(current_fleet_only=True)
        assert result == {
            "array1": {
                "os": "Purity//FB",
                "version": "4.8.8",
                "model": "FlashBlade//S200",
                "api_versions": ["2.29", "2.30"],
                "is_local": True,
                "topology_group": "tg1",
            }
        }

    def test_generate_remote_arrays_dict_empty_on_error(self):
        mock_blade = Mock()
        mock_blade.get_remote_arrays.return_value = self._response([], 400)
        assert generate_remote_arrays_dict(mock_blade) == {}

    def test_generate_tgroups_dict_routes_members_by_type(self):
        """Array members and nested groups land in their own lists; members
        of an unknown group or without a name are skipped."""
        parent = Mock(spec=["name", "context", "parent_topology_group"])
        parent.name = "parent"
        parent.context = self._typed_ref("fleet1", "fleets")
        parent.parent_topology_group = self._typed_ref(None)
        child = Mock(spec=["name", "context", "parent_topology_group"])
        child.name = "child"
        child.context = self._typed_ref("fleet1", "fleets")
        child.parent_topology_group = self._typed_ref("parent", "topology-groups")

        def member(group, name, resource_type, status="joined"):
            item = Mock(spec=["topology_group", "member", "status", "status_details"])
            item.topology_group = self._typed_ref(group, "topology-groups")
            item.member = self._typed_ref(name, resource_type)
            item.status = status
            item.status_details = None
            return item

        mock_blade = Mock()
        mock_blade.get_topology_groups.return_value = self._response([parent, child])
        mock_blade.get_topology_groups_members.return_value = self._response(
            [
                member("parent", "child", "topology-groups"),
                member("child", "array1", "remote-arrays"),
                member("gone", "array2", "remote-arrays"),
                member("child", None, "remote-arrays"),
            ]
        )

        result = generate_tgroups_dict(mock_blade)

        mock_blade.get_topology_groups_members.assert_called_once_with()
        assert result["parent"]["parent_topology_group"] is None
        assert result["parent"]["context"] == "fleet1"
        assert result["parent"]["tgroups"] == [
            {"name": "child", "status": "joined", "status_details": None}
        ]
        assert result["parent"]["arrays"] == []
        assert result["child"]["parent_topology_group"] == "parent"
        assert result["child"]["arrays"] == [
            {"name": "array1", "status": "joined", "status_details": None}
        ]
        assert result["child"]["tgroups"] == []

    def test_generate_tgroups_dict_skips_members_without_groups(self):
        mock_blade = Mock()
        mock_blade.get_topology_groups.return_value = self._response([])

        assert generate_tgroups_dict(mock_blade) == {}
        mock_blade.get_topology_groups_members.assert_not_called()

    def test_generate_presets_dict_collates_sections_by_name(self):
        """Parameters carry the constraints of their own type; every
        configuration list is keyed by name; export configurations are
        split by protocol; a preset without a name is skipped."""
        param = SimpleNamespace(
            name="size",
            type="integer",
            metadata=SimpleNamespace(
                description="Capacity", display_name="Size", subtype="size"
            ),
            constraints=SimpleNamespace(
                integer=SimpleNamespace(min=1, max=10), string=None
            ),
        )
        free_text = SimpleNamespace(
            name="owner", type="string", metadata=None, constraints=None
        )
        placement = SimpleNamespace(
            name="place1",
            storage_class=SimpleNamespace(
                name="flashblade-s200", resource_type="storage-classes"
            ),
            targets=[],
            qos_configurations=["qos1"],
        )
        directory = SimpleNamespace(
            name="dir1", path=SimpleNamespace(value="/"), count="1"
        )
        exports = SimpleNamespace(
            nfs=[SimpleNamespace(name="nfs1", rules=[])], smb=None, smb_share=[]
        )
        preset = SimpleNamespace(
            name="fleet1:preset1",
            description="File preset",
            workload_type="File",
            revision=2,
            context=SimpleNamespace(name="fleet1", resource_type="fleets"),
            platform_features=["file"],
            parameters=[param, free_text],
            bucket_configurations=None,
            directory_configurations=[directory],
            volume_configurations=None,
            placement_configurations=[placement],
            qos_configurations=[],
            quota_configurations=[],
            snapshot_configurations=[],
            lifecycle_configurations=[],
            periodic_replication_configurations=[],
            export_configurations=exports,
            workload_tags=[
                SimpleNamespace(
                    key="env", value="prod", namespace="default", copyable=None
                )
            ],
        )
        nameless = SimpleNamespace(name=None)
        mock_blade = Mock()
        mock_blade.get_presets_workload.return_value = self._response(
            [preset, nameless]
        )

        result = generate_presets_dict(mock_blade)

        assert list(result) == ["fleet1:preset1"]
        info = result["fleet1:preset1"]
        assert info["workload_type"] == "File"
        assert info["revision"] == 2
        assert info["context"] == "fleet1"
        assert info["platform_features"] == ["file"]
        assert info["parameters"]["size"] == {
            "type": "integer",
            "description": "Capacity",
            "display_name": "Size",
            "subtype": "size",
            "constraints": {"min": 1, "max": 10},
        }
        assert info["parameters"]["owner"]["constraints"] == {}
        assert info["parameters"]["owner"]["description"] is None
        assert info["placement_configurations"]["place1"]["storage_class"] == {
            "name": "flashblade-s200",
            "resource_type": "storage-classes",
        }
        assert info["directory_configurations"]["dir1"]["path"] == {"value": "/"}
        assert info["bucket_configurations"] == {}
        assert info["volume_configurations"] == {}
        assert info["export_configurations"] == {
            "nfs": {"nfs1": {"name": "nfs1", "rules": []}},
            "smb": {},
            "smb_share": {},
        }
        assert info["workload_tags"] == [
            {"key": "env", "value": "prod", "namespace": "default", "copyable": None}
        ]

    def test_generate_presets_dict_empty_on_error(self):
        mock_blade = Mock()
        mock_blade.get_presets_workload.return_value = self._response([], 400)
        assert generate_presets_dict(mock_blade) == {}

    def _workload(self, name="wl1", space=None, destroyed=False):
        preset = Mock(spec=["name", "revision"])
        preset.name = "fleet1:preset1"
        preset.revision = 2
        workload = Mock(
            spec=[
                "name",
                "context",
                "preset",
                "status",
                "status_details",
                "created",
                "destroyed",
                "time_remaining",
                "space",
            ]
        )
        workload.name = name
        workload.context = self._typed_ref("array1", "arrays")
        workload.preset = preset
        workload.status = "ready"
        workload.status_details = None
        workload.created = 1700000000000
        workload.destroyed = destroyed
        workload.time_remaining = None
        workload.space = space
        return workload

    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_workloads_dict_reads_tags_space_and_performance(
        self, mock_loose_version
    ):
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        workload = self._workload(space=SimpleNamespace(total_used=10, virtual=20))
        tag = Mock(spec=["resource", "key", "value", "namespace", "copyable"])
        tag.resource = self._typed_ref("wl1")
        tag.key = "env"
        tag.value = "prod"
        tag.namespace = "default"
        tag.copyable = True
        stray_tag = Mock(spec=["resource", "key", "value", "namespace", "copyable"])
        stray_tag.resource = self._typed_ref("other")
        perf = Mock(spec=["name", "reads_per_sec", "writes_per_sec", "time"])
        perf.name = "wl1"
        perf.reads_per_sec = 5
        perf.writes_per_sec = 7
        perf.time = 1700000000000
        mock_blade = Mock()
        mock_blade.get_workloads.return_value = self._response([workload])
        mock_blade.get_workloads_tags.return_value = self._response([tag, stray_tag])
        mock_blade.get_workloads_performance.return_value = self._response([perf])

        result = generate_workloads_dict(mock_blade, "2.30")

        mock_blade.get_workloads_performance.assert_called_once_with(names=["wl1"])
        info = result["wl1"]
        assert info["preset"] == "fleet1:preset1"
        assert info["preset_revision"] == 2
        assert info["context"] == "array1"
        assert info["status"] == "ready"
        assert info["status_details"] == []
        assert info["created"] is not None
        assert info["destroyed"] is False
        assert info["tags"] == [
            {"key": "env", "value": "prod", "namespace": "default", "copyable": True}
        ]
        assert info["space"] == {"total_used": 10, "virtual": 20}
        assert info["performance"]["reads_per_sec"] == 5
        assert info["performance"]["writes_per_sec"] == 7
        assert info["performance"]["bytes_per_op"] is None
        assert len(info["performance"]) == 12

    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_workloads_dict_skips_performance_below_2_30(
        self, mock_loose_version
    ):
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        mock_blade = Mock()
        mock_blade.get_workloads.return_value = self._response([self._workload()])
        mock_blade.get_workloads_tags.return_value = self._response([], 400)

        result = generate_workloads_dict(mock_blade, "2.23")

        mock_blade.get_workloads_performance.assert_not_called()
        assert result["wl1"]["performance"] is None
        assert result["wl1"]["space"] is None
        assert result["wl1"]["tags"] == []

    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_workloads_dict_no_workloads_makes_no_further_calls(
        self, mock_loose_version
    ):
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        mock_blade = Mock()
        mock_blade.get_workloads.return_value = self._response([])

        assert generate_workloads_dict(mock_blade, "2.30") == {}
        mock_blade.get_workloads_tags.assert_not_called()
        mock_blade.get_workloads_performance.assert_not_called()

    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_workloads_dict_requests_performance_for_live_workloads_only(
        self, mock_loose_version
    ):
        """A destroyed workload is reported but never named in the
        performance request, so it cannot blank the others' metrics."""
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        perf = Mock(spec=["name", "reads_per_sec"])
        perf.name = "wl1"
        perf.reads_per_sec = 3
        mock_blade = Mock()
        mock_blade.get_workloads.return_value = self._response(
            [self._workload(), self._workload(name="wl2", destroyed=True)]
        )
        mock_blade.get_workloads_tags.return_value = self._response([])
        mock_blade.get_workloads_performance.return_value = self._response([perf])

        result = generate_workloads_dict(mock_blade, "2.30")

        mock_blade.get_workloads_performance.assert_called_once_with(names=["wl1"])
        assert result["wl1"]["performance"]["reads_per_sec"] == 3
        assert result["wl2"]["destroyed"] is True
        assert result["wl2"]["performance"] is None

    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_workloads_dict_all_destroyed_skips_performance(
        self, mock_loose_version
    ):
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        mock_blade = Mock()
        mock_blade.get_workloads.return_value = self._response(
            [self._workload(destroyed=True)]
        )
        mock_blade.get_workloads_tags.return_value = self._response([])

        result = generate_workloads_dict(mock_blade, "2.30")

        mock_blade.get_workloads_performance.assert_not_called()
        assert result["wl1"]["performance"] is None

    def test_generate_storage_class_members_dict(self):
        item = Mock(spec=["member", "storage_class"])
        item.member = self._typed_ref("array1", "remote-arrays")
        item.storage_class = self._typed_ref("flashblade-s200", "storage-classes")
        nameless = Mock(spec=["member", "storage_class"])
        nameless.member = self._typed_ref(None)
        nameless.storage_class = self._typed_ref("flashblade-s200", "storage-classes")
        mock_blade = Mock()
        mock_blade.get_storage_classes_members.return_value = self._response(
            [item, nameless]
        )

        assert generate_storage_class_members_dict(mock_blade) == {
            "array1": "flashblade-s200"
        }

    def test_generate_realm_connections_dict_keys_local_then_remote(self):
        def connection(local, remote, status):
            item = Mock(spec=["local_realm", "remote_realm", "status"])
            item.local_realm = self._typed_ref(local, "realms")
            item.remote_realm = self._typed_ref(remote, "realms")
            item.status = status
            return item

        mock_blade = Mock()
        mock_blade.get_realm_connections.return_value = self._response(
            [
                connection("realm1", "remote1", "CONNECTED"),
                connection("realm1", "remote2", "CONNECTING"),
                connection(None, "remote3", "UNREACHABLE"),
            ]
        )

        assert generate_realm_connections_dict(mock_blade) == {
            "realm1": {
                "remote1": {"status": "CONNECTED"},
                "remote2": {"status": "CONNECTING"},
            }
        }

    def test_generate_remote_realms_dict(self):
        realm = Mock(spec=["name", "arrays"])
        realm.name = "remote1"
        realm.arrays = [self._typed_ref("peer", "arrays")]
        bare = Mock(spec=["name", "arrays"])
        bare.name = "remote2"
        bare.arrays = None
        mock_blade = Mock()
        mock_blade.get_remote_realms.return_value = self._response([realm, bare])

        assert generate_remote_realms_dict(mock_blade) == {
            "remote1": {"arrays": ["peer"]},
            "remote2": {"arrays": []},
        }

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_storage_class_members_dict")
    @patch("plugins.modules.purefb_info.generate_tgroups_dict")
    @patch("plugins.modules.purefb_info.generate_workloads_dict")
    @patch("plugins.modules.purefb_info.generate_presets_dict")
    @patch("plugins.modules.purefb_info.generate_remote_arrays_dict")
    @patch("plugins.modules.purefb_info.generate_fleet_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_fleet_subset_enriches_members_and_adds_fleet_views(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_fleet,
        mock_remote_arrays,
        mock_presets,
        mock_workloads,
        mock_tgroups,
        mock_storage_class,
        mock_loose_version,
    ):
        """Fleet members gain the remote-array detail the array reports for
        them; a member the array does not describe is left as it was."""
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["fleet"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        mock_generate_fleet.return_value = {
            "fleet1": {
                "members": {
                    "array1": {"status": "joined", "status_details": None},
                    "array2": {"status": "joining", "status_details": None},
                }
            }
        }
        mock_remote_arrays.return_value = {
            "array1": {
                "os": "Purity//FB",
                "version": "4.8.8",
                "model": "FlashBlade//S200",
                "api_versions": ["2.30"],
                "is_local": True,
                "topology_group": None,
            }
        }
        mock_presets.return_value = {}
        mock_workloads.return_value = {}
        mock_tgroups.return_value = {}
        mock_storage_class.return_value = {"array1": "flashblade-s200"}

        main()

        info = mock_module.exit_json.call_args[1]["purefb_info"]
        mock_generate_fleet.assert_called_once_with(mock_blade)
        mock_workloads.assert_called_once_with(mock_blade, ANY)
        assert info["fleet"]["fleet1"]["members"]["array1"] == {
            "status": "joined",
            "status_details": None,
            "os": "Purity//FB",
            "version": "4.8.8",
            "model": "FlashBlade//S200",
            "api_versions": ["2.30"],
            "is_local": True,
            "topology_group": None,
        }
        assert info["fleet"]["fleet1"]["members"]["array2"] == {
            "status": "joining",
            "status_details": None,
        }
        assert info["presets"] == {}
        assert info["workloads"] == {}
        assert info["tgroups"] == {}
        assert info["storage_class_members"] == {"array1": "flashblade-s200"}

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_storage_class_members_dict")
    @patch("plugins.modules.purefb_info.generate_tgroups_dict")
    @patch("plugins.modules.purefb_info.generate_workloads_dict")
    @patch("plugins.modules.purefb_info.generate_presets_dict")
    @patch("plugins.modules.purefb_info.generate_remote_arrays_dict")
    @patch("plugins.modules.purefb_info.generate_fleet_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_fleet_subset_without_fleet_skips_remote_arrays(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_fleet,
        mock_remote_arrays,
        mock_presets,
        mock_workloads,
        mock_tgroups,
        mock_storage_class,
        mock_loose_version,
    ):
        """An array that is not in a fleet is not asked about remote arrays;
        the fleet views are still produced."""
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["fleet"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        mock_generate_fleet.return_value = {}
        mock_presets.return_value = {}
        mock_workloads.return_value = {}
        mock_tgroups.return_value = {}
        mock_storage_class.return_value = {"array1": "flashblade-s200"}

        main()

        info = mock_module.exit_json.call_args[1]["purefb_info"]
        mock_remote_arrays.assert_not_called()
        assert info["fleet"] == {}
        assert info["presets"] == {}
        assert info["storage_class_members"] == {"array1": "flashblade-s200"}

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_policies_subset_fleet_members_are_enriched(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """The fleet key built by the policies subset has the same shape as
        the one built by the fleet subset; the fleet-only views stay out."""
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["policies"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        generators = {
            name: Mock(return_value={})
            for name in (
                "generate_all_policies_dict",
                "generate_policies_dict",
                "generate_object_store_access_policies_dict",
                "generate_bucket_access_policies_dict",
                "generate_bucket_cross_object_policies_dict",
                "generate_nfs_export_policies_dict",
                "generate_smb_client_policies_dict",
                "generate_smb_share_policies_dict",
                "generate_network_access_policies_dict",
                "generate_worm_data_policies_dict",
                "generate_password_policies_dict",
                "generate_tls_policies_dict",
                "generate_s3_export_policies_dict",
                "generate_ssh_ca_policies_dict",
                "generate_quota_policies_dict",
                "generate_eviction_policies_dict",
                "generate_management_access_policies_dict",
                "generate_management_authentication_policies_dict",
                "generate_management_access_roles_dict",
                "generate_presets_dict",
                "generate_workloads_dict",
                "generate_tgroups_dict",
                "generate_storage_class_members_dict",
            )
        }
        generators["generate_fleet_dict"] = Mock(
            return_value={"fleet1": {"members": {"array1": {"status": "joined"}}}}
        )
        generators["generate_remote_arrays_dict"] = Mock(
            return_value={"array1": {"os": "Purity//FB", "version": "4.8.8"}}
        )

        with patch.multiple("plugins.modules.purefb_info", **generators):
            main()

        info = mock_module.exit_json.call_args[1]["purefb_info"]
        generators["generate_remote_arrays_dict"].assert_called_once_with(mock_blade)
        assert info["fleet"]["fleet1"]["members"]["array1"] == {
            "status": "joined",
            "os": "Purity//FB",
            "version": "4.8.8",
        }
        for name in (
            "generate_presets_dict",
            "generate_workloads_dict",
            "generate_tgroups_dict",
            "generate_storage_class_members_dict",
        ):
            generators[name].assert_not_called()
        for key in ("presets", "workloads", "tgroups", "storage_class_members"):
            assert key not in info

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_remote_realms_dict")
    @patch("plugins.modules.purefb_info.generate_realm_connections_dict")
    @patch("plugins.modules.purefb_info.generate_resource_accesses_dict")
    @patch("plugins.modules.purefb_info.generate_realms_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_realms_subset_adds_connections_and_remote_realms(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_realms,
        mock_resource_accesses,
        mock_connections,
        mock_remote_realms,
        mock_loose_version,
    ):
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["realms"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        mock_generate_realms.return_value = {"realm1": {}}
        mock_resource_accesses.return_value = {}
        mock_connections.return_value = {"realm1": {"remote1": {"status": "CONNECTED"}}}
        mock_remote_realms.return_value = {"remote1": {"arrays": ["peer"]}}

        main()

        info = mock_module.exit_json.call_args[1]["purefb_info"]
        assert info["realms"] == {"realm1": {}}
        assert info["realm_connections"] == {
            "realm1": {"remote1": {"status": "CONNECTED"}}
        }
        assert info["remote_realms"] == {"remote1": {"arrays": ["peer"]}}

    # network connectors, connector performance and settings, LLDP
    # neighbours (network subset) and the connections subset

    @staticmethod
    def _version_tuple(version):
        """Stand-in for LooseVersion: tuples compare like dotted versions."""
        return tuple(int(part) for part in str(version).split("."))

    @staticmethod
    def _error_response(status_code=400):
        return Mock(spec=["status_code", "errors", "headers"], status_code=status_code)

    def test_generate_network_connectors_dict_reports_empty_ports(self):
        """An unpopulated port comes back with connector_type "-" and zero
        speeds; it is reported as the array describes it."""
        populated = Mock()
        populated.name = "CH1.FM1.ETH1"
        populated.connector_type = "QSFP28"
        populated.lane_speed = 25000000000
        populated.lanes_per_port = 4
        populated.port_count = 1
        populated.port_speed = 100000000000
        populated.transceiver_type = "AUTO"
        empty = Mock(
            spec=[
                "name",
                "connector_type",
                "lane_speed",
                "port_count",
                "port_speed",
                "transceiver_type",
            ]
        )
        empty.name = "CH1.FM1.ETH5"
        empty.connector_type = "-"
        empty.lane_speed = 0
        empty.port_count = 1
        empty.port_speed = 0
        empty.transceiver_type = "AUTO"
        mock_blade = Mock()
        mock_blade.get_network_interfaces_connectors.return_value = Mock(
            status_code=200, items=[populated, empty]
        )

        result = generate_network_connectors_dict(mock_blade)

        assert sorted(result) == ["CH1.FM1.ETH1", "CH1.FM1.ETH5"]
        assert result["CH1.FM1.ETH1"] == {
            "connector_type": "QSFP28",
            "lane_speed": 25000000000,
            "lanes_per_port": 4,
            "port_count": 1,
            "port_speed": 100000000000,
            "transceiver_type": "AUTO",
        }
        assert result["CH1.FM1.ETH5"]["connector_type"] == "-"
        assert result["CH1.FM1.ETH5"]["port_speed"] == 0
        # a REST 2.17-2.19 model has no lanes_per_port
        assert result["CH1.FM1.ETH5"]["lanes_per_port"] is None

    def test_generate_network_connectors_dict_returns_empty_on_error(self):
        mock_blade = Mock()
        mock_blade.get_network_interfaces_connectors.return_value = (
            self._error_response()
        )
        assert generate_network_connectors_dict(mock_blade) == {}

    def test_generate_network_connector_performance_dict_keeps_blade_rows(self):
        """The performance view lists the blade NICs (CHx.FBn) next to the
        connectors; both are kept, keyed by name, and only the items are
        read (the aggregate total row of a total_only request is not)."""
        blade_nic = Mock()
        blade_nic.name = "CH1.FB1"
        blade_nic.link_aggregation_group = Mock(spec=["resource_type"])
        blade_nic.received_bytes_per_sec = 0.0
        blade_nic.rdma_received_req_cqe_errors_per_sec = 0.0
        blade_nic.flow_control_received_pause_frames_per_sec = 0.0
        blade_nic.time = 1794902460000
        uplink = Mock()
        uplink.name = "CH1.FM1.ETH1"
        uplink.link_aggregation_group = Mock()
        uplink.link_aggregation_group.name = "uplink"
        uplink.received_bytes_per_sec = 30797.7
        uplink.time = 1794902460000
        mock_blade = Mock()
        mock_blade.get_network_interfaces_connectors_performance.return_value = Mock(
            status_code=200, items=[blade_nic, uplink]
        )

        result = generate_network_connector_performance_dict(mock_blade)

        mock_blade.get_network_interfaces_connectors_performance.assert_called_once_with()
        assert sorted(result) == ["CH1.FB1", "CH1.FM1.ETH1"]
        assert result["CH1.FB1"]["link_aggregation_group"] is None
        assert result["CH1.FM1.ETH1"]["link_aggregation_group"] == "uplink"
        assert result["CH1.FM1.ETH1"]["received_bytes_per_sec"] == 30797.7
        assert result["CH1.FB1"]["rdma_received_req_cqe_errors_per_sec"] == 0.0
        assert result["CH1.FB1"]["flow_control_received_pause_frames_per_sec"] == 0.0
        assert result["CH1.FB1"]["time"] == 1794902460000
        # every documented counter is present on every row
        for field in (
            "transmitted_packets_per_sec",
            "total_errors_per_sec",
            "flow_control_transmitted_lossless_bytes_per_sec",
            "rdma_transmitted_local_ack_timeout_errors_per_sec",
        ):
            assert field in result["CH1.FB1"]
            assert field in result["CH1.FM1.ETH1"]

    def test_generate_network_connector_performance_dict_lag_as_dict(self):
        """Older SDKs hand references back as plain dicts."""
        row = Mock()
        row.name = "CH1.FM1.ETH2"
        row.link_aggregation_group = {"name": "uplink", "resource_type": "lags"}
        mock_blade = Mock()
        mock_blade.get_network_interfaces_connectors_performance.return_value = Mock(
            status_code=200, items=[row]
        )
        result = generate_network_connector_performance_dict(mock_blade)
        assert result["CH1.FM1.ETH2"]["link_aggregation_group"] == "uplink"

    def test_generate_network_connector_performance_dict_returns_empty_on_error(
        self,
    ):
        mock_blade = Mock()
        mock_blade.get_network_interfaces_connectors_performance.return_value = (
            self._error_response()
        )
        assert generate_network_connector_performance_dict(mock_blade) == {}

    def test_generate_network_connector_settings_dict_tolerates_disabled(self):
        """Without RoCE congestion control the array answers 400
        "Congestion control is not enabled."; that is an empty dict, not a
        failure."""
        mock_blade = Mock()
        mock_blade.get_network_interfaces_connectors_settings.return_value = (
            self._error_response(400)
        )
        assert generate_network_connector_settings_dict(mock_blade) == {}

    def test_generate_network_connector_settings_dict_reads_roce(self):
        setting = Mock()
        setting.name = "default-network-connector-settings"
        setting.roce.enabled = True
        setting.roce.network_congestion_mode = "lossless"
        setting.roce.trust_mode = "dscp"
        setting.roce.default_ecn.marking_probability = 0.0
        setting.roce.default_ecn.max_ecn_marked_threshold = 1664208
        setting.roce.default_ecn.min_ecn_marked_threshold = 187452
        setting.roce.default_pfc.port_buffer = 62992
        setting.roce.default_pfc.xoff_threshold = 3810
        setting.roce.default_pfc.xon_threshold = 762
        unnamed = Mock(spec=["name", "roce"])
        unnamed.name = None
        unnamed.roce = None
        mock_blade = Mock()
        mock_blade.get_network_interfaces_connectors_settings.return_value = Mock(
            status_code=200, items=[setting, unnamed]
        )

        result = generate_network_connector_settings_dict(mock_blade)

        assert result["default-network-connector-settings"] == {
            "roce": {
                "enabled": True,
                "network_congestion_mode": "lossless",
                "trust_mode": "dscp",
                "default_ecn": {
                    "marking_probability": 0.0,
                    "max_ecn_marked_threshold": 1664208,
                    "min_ecn_marked_threshold": 187452,
                },
                "default_pfc": {
                    "port_buffer": 62992,
                    "xoff_threshold": 3810,
                    "xon_threshold": 762,
                },
            }
        }
        # a row without a name or RoCE block is still reported, not dropped
        assert result["default"]["roce"]["enabled"] is None
        assert result["default"]["roce"]["default_pfc"]["xon_threshold"] is None

    def test_generate_lldp_neighbors_dict_keys_by_local_port(self):
        """Neighbours are keyed by the physical port name (CH1.FM1.ETH1),
        never merged into the VIP-keyed network dict."""
        neighbor = Mock()
        neighbor.initial_ttl_in_sec = 120
        neighbor.local_port.name = "CH1.FM1.ETH1"
        chassis = neighbor.neighbor_chassis
        chassis.name = "tor-switch-a"
        chassis.description = "Cisco Nexus Operating System (NX-OS) Software"
        chassis.addresses = ["10.0.0.72"]
        chassis.id.type = "mac"
        chassis.id.value = "80:27:6c:d2:8d:fc"
        for capability in ("bridge", "router"):
            getattr(chassis, capability).supported = True
            getattr(chassis, capability).enabled = True
        for capability in (
            "repeater",
            "station_only",
            "telephone",
            "wlan_access_point",
            "docsis_cable_device",
        ):
            getattr(chassis, capability).supported = False
            getattr(chassis, capability).enabled = False
        neighbor.neighbor_port.description = "Ethernet1/13"
        neighbor.neighbor_port.id.type = "ifname"
        neighbor.neighbor_port.id.value = "Ethernet1/13"
        # a port whose neighbour sent no chassis or port details
        bare = Mock(spec=["initial_ttl_in_sec", "local_port"])
        bare.initial_ttl_in_sec = 120
        bare.local_port = Mock(spec=["name"])
        bare.local_port.name = "CH1.FM1.ETH9"
        mock_blade = Mock()
        mock_blade.get_network_interfaces_neighbors.return_value = Mock(
            status_code=200, items=[neighbor, bare]
        )

        result = generate_lldp_neighbors_dict(mock_blade)

        mock_blade.get_network_interfaces_neighbors.assert_called_once_with()
        assert sorted(result) == ["CH1.FM1.ETH1", "CH1.FM1.ETH9"]
        # every port maps to the list of its neighbours, here one each
        assert len(result["CH1.FM1.ETH1"]) == 1
        assert len(result["CH1.FM1.ETH9"]) == 1
        eth1 = result["CH1.FM1.ETH1"][0]
        assert eth1["initial_ttl_in_sec"] == 120
        assert eth1["neighbor_chassis"]["name"] == "tor-switch-a"
        assert eth1["neighbor_chassis"]["addresses"] == ["10.0.0.72"]
        assert eth1["neighbor_chassis"]["id"] == {
            "type": "mac",
            "value": "80:27:6c:d2:8d:fc",
        }
        assert eth1["neighbor_chassis"]["capabilities"]["bridge"] == {
            "supported": True,
            "enabled": True,
        }
        assert eth1["neighbor_chassis"]["capabilities"]["telephone"] == {
            "supported": False,
            "enabled": False,
        }
        assert sorted(eth1["neighbor_chassis"]["capabilities"]) == [
            "bridge",
            "docsis_cable_device",
            "repeater",
            "router",
            "station_only",
            "telephone",
            "wlan_access_point",
        ]
        assert eth1["neighbor_port"] == {
            "id": {"type": "ifname", "value": "Ethernet1/13"},
            "description": "Ethernet1/13",
        }
        eth9 = result["CH1.FM1.ETH9"][0]
        assert eth9["neighbor_chassis"]["name"] is None
        assert eth9["neighbor_chassis"]["addresses"] == []
        assert eth9["neighbor_chassis"]["capabilities"]["router"] == {
            "supported": None,
            "enabled": None,
        }
        assert eth9["neighbor_port"]["id"] == {"type": None, "value": None}

    def test_generate_lldp_neighbors_dict_keeps_every_neighbor_of_a_port(self):
        """A port can see several LLDP neighbours (for example through an
        unmanaged switch); the array returns one row per neighbour and
        every row is kept, in the array's order, instead of the last one
        overwriting the others."""
        rows = []
        for chassis_name, chassis_mac, port_value in (
            ("tor-switch-a", "80:27:6c:d2:8d:fc", "Ethernet1/13"),
            ("tor-switch-b", "80:27:6c:d2:d1:04", "Ethernet1/21"),
        ):
            row = Mock()
            row.initial_ttl_in_sec = 120
            row.local_port.name = "CH1.FM1.ETH1"
            row.neighbor_chassis.name = chassis_name
            row.neighbor_chassis.id.type = "mac"
            row.neighbor_chassis.id.value = chassis_mac
            row.neighbor_port.id.type = "ifname"
            row.neighbor_port.id.value = port_value
            rows.append(row)
        other = Mock()
        other.local_port.name = "CH1.FM2.ETH1"
        other.neighbor_chassis.name = "tor-switch-b"
        mock_blade = Mock()
        mock_blade.get_network_interfaces_neighbors.return_value = Mock(
            status_code=200, items=rows + [other]
        )

        result = generate_lldp_neighbors_dict(mock_blade)

        assert sorted(result) == ["CH1.FM1.ETH1", "CH1.FM2.ETH1"]
        eth1 = result["CH1.FM1.ETH1"]
        assert len(eth1) == 2
        assert [n["neighbor_chassis"]["name"] for n in eth1] == [
            "tor-switch-a",
            "tor-switch-b",
        ]
        assert [n["neighbor_chassis"]["id"]["value"] for n in eth1] == [
            "80:27:6c:d2:8d:fc",
            "80:27:6c:d2:d1:04",
        ]
        assert [n["neighbor_port"]["id"]["value"] for n in eth1] == [
            "Ethernet1/13",
            "Ethernet1/21",
        ]
        assert [n["neighbor_chassis"]["name"] for n in result["CH1.FM2.ETH1"]] == [
            "tor-switch-b"
        ]

    def test_generate_lldp_neighbors_dict_returns_empty_on_error(self):
        mock_blade = Mock()
        mock_blade.get_network_interfaces_neighbors.return_value = (
            self._error_response()
        )
        assert generate_lldp_neighbors_dict(mock_blade) == {}

    def test_generate_connections_list(self):
        """Rows are flattened to state, local/remote address and port and
        the sample time; the array reports ports as strings."""
        conn = Mock()
        conn.current_state = "ESTABLISHED"
        conn.local.address = "10.0.0.234"
        conn.local.port = "8117"
        conn.remote.address = "10.0.0.7"
        conn.remote.port = "23691"
        conn.time = 1794902501349
        bare = Mock(spec=["current_state", "local", "remote", "time"])
        bare.current_state = "TIME_WAIT"
        bare.local = None
        bare.remote = None
        bare.time = 1794902501349
        mock_blade = Mock()
        mock_blade.get_network_interfaces_network_connection_statistics.return_value = (
            Mock(status_code=200, items=[conn, bare])
        )

        result = generate_connections_list(mock_blade)

        # no filters: the deprecated local_host/remote_host kwargs are never sent
        mock_blade.get_network_interfaces_network_connection_statistics.assert_called_once_with()
        assert result == [
            {
                "state": "ESTABLISHED",
                "local_address": "10.0.0.234",
                "local_port": "8117",
                "remote_address": "10.0.0.7",
                "remote_port": "23691",
                "time": 1794902501349,
            },
            {
                "state": "TIME_WAIT",
                "local_address": None,
                "local_port": None,
                "remote_address": None,
                "remote_port": None,
                "time": 1794902501349,
            },
        ]

    def test_generate_connections_list_returns_empty_on_error(self):
        mock_blade = Mock()
        mock_blade.get_network_interfaces_network_connection_statistics.return_value = (
            self._error_response()
        )
        assert generate_connections_list(mock_blade) == []

    def _run_main(self, subset, api_version, mock_loose_version, mock_get_version):
        """Run main() with real version comparisons and return exit_json kwargs."""
        mock_loose_version.side_effect = self._version_tuple
        mock_get_version.return_value = api_version
        with patch("plugins.modules.purefb_info.AnsibleModule") as mock_ansible_module:
            with patch("plugins.modules.purefb_info.get_system") as mock_get_system:
                mock_module = Mock()
                mock_module.params = {"gather_subset": subset}
                mock_module.check_mode = False
                mock_ansible_module.return_value = mock_module
                mock_get_system.return_value = Mock()
                main()
                mock_module.exit_json.assert_called_once()
                return mock_module.exit_json.call_args[1]

    @patch("plugins.modules.purefb_info.get_rest_api_version")
    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_connections_list")
    @patch("plugins.modules.purefb_info.generate_lldp_neighbors_dict")
    @patch("plugins.modules.purefb_info.generate_network_connector_settings_dict")
    @patch("plugins.modules.purefb_info.generate_network_connector_performance_dict")
    @patch("plugins.modules.purefb_info.generate_network_connectors_dict")
    @patch("plugins.modules.purefb_info.generate_network_dict")
    def test_main_network_subset_adds_connector_keys(
        self,
        mock_network,
        mock_connectors,
        mock_performance,
        mock_settings,
        mock_neighbors,
        mock_connections,
        mock_loose_version,
        mock_get_version,
    ):
        """On REST 2.20+ the network subset carries the four connector keys
        beside `network`; `connections` is not gathered unless named."""
        mock_network.return_value = {"vip1": {}}
        mock_connectors.return_value = {"CH1.FM1.ETH1": {}}
        mock_performance.return_value = {"CH1.FB1": {}}
        mock_settings.return_value = {}
        mock_neighbors.return_value = {"CH1.FM1.ETH1": [{}]}

        result = self._run_main(
            ["network"], "2.30", mock_loose_version, mock_get_version
        )

        info = result["purefb_info"]
        assert result["changed"] is False
        assert info["network"] == {"vip1": {}}
        assert info["network_connectors"] == {"CH1.FM1.ETH1": {}}
        assert info["network_connector_performance"] == {"CH1.FB1": {}}
        assert info["network_connector_settings"] == {}
        assert info["lldp_neighbors"] == {"CH1.FM1.ETH1": [{}]}
        assert "connections" not in info
        mock_connections.assert_not_called()

    @patch("plugins.modules.purefb_info.get_rest_api_version")
    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_lldp_neighbors_dict")
    @patch("plugins.modules.purefb_info.generate_network_connector_settings_dict")
    @patch("plugins.modules.purefb_info.generate_network_connector_performance_dict")
    @patch("plugins.modules.purefb_info.generate_network_connectors_dict")
    @patch("plugins.modules.purefb_info.generate_network_dict")
    def test_main_network_subset_gates_neighbors_on_2_20(
        self,
        mock_network,
        mock_connectors,
        mock_performance,
        mock_settings,
        mock_neighbors,
        mock_loose_version,
        mock_get_version,
    ):
        """REST 2.18: connectors, performance and settings are read, the LLDP
        endpoint (2.20) is not called."""
        mock_network.return_value = {}
        mock_connectors.return_value = {}
        mock_performance.return_value = {}
        mock_settings.return_value = {}

        info = self._run_main(
            ["network"], "2.18", mock_loose_version, mock_get_version
        )["purefb_info"]

        assert "network_connectors" in info
        assert "network_connector_performance" in info
        assert "network_connector_settings" in info
        assert "lldp_neighbors" not in info
        mock_neighbors.assert_not_called()

    @patch("plugins.modules.purefb_info.get_rest_api_version")
    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_lldp_neighbors_dict")
    @patch("plugins.modules.purefb_info.generate_network_connector_settings_dict")
    @patch("plugins.modules.purefb_info.generate_network_connector_performance_dict")
    @patch("plugins.modules.purefb_info.generate_network_connectors_dict")
    @patch("plugins.modules.purefb_info.generate_network_dict")
    def test_main_network_subset_skips_connectors_below_2_17(
        self,
        mock_network,
        mock_connectors,
        mock_performance,
        mock_settings,
        mock_neighbors,
        mock_loose_version,
        mock_get_version,
    ):
        """Below REST 2.17 the network subset is unchanged and none of the
        connector endpoints is called."""
        mock_network.return_value = {"vip1": {}}

        info = self._run_main(
            ["network"], "2.16", mock_loose_version, mock_get_version
        )["purefb_info"]

        assert info == {"network": {"vip1": {}}}
        mock_connectors.assert_not_called()
        mock_performance.assert_not_called()
        mock_settings.assert_not_called()
        mock_neighbors.assert_not_called()

    @patch("plugins.modules.purefb_info.get_rest_api_version")
    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_connections_list")
    @patch("plugins.modules.purefb_info.generate_network_dict")
    def test_main_connections_subset(
        self, mock_network, mock_connections, mock_loose_version, mock_get_version
    ):
        """`connections` is a subset of its own (REST 2.18+): it does not pull
        the network dict in and is skipped silently on an older array."""
        mock_connections.return_value = [{"state": "ESTABLISHED"}]

        info = self._run_main(
            ["connections"], "2.18", mock_loose_version, mock_get_version
        )["purefb_info"]
        assert info == {"connections": [{"state": "ESTABLISHED"}]}
        mock_network.assert_not_called()

        mock_connections.reset_mock()
        info = self._run_main(
            ["connections"], "2.17", mock_loose_version, mock_get_version
        )["purefb_info"]
        assert info == {}
        mock_connections.assert_not_called()

    # ==== filesystems: eradication_mode and worm_policy (REST 2.15) ====

    def _fs_for_worm(self, name, eradication_mode=None):
        """FileSystem mock with the fields generate_fs_dict reads directly.
        eradication_config is None (array omitted it) unless a mode is given."""
        fsys = Mock()
        fsys.name = name
        fsys.fast_remove_directory_enabled = False
        fsys.snapshot_directory_enabled = False
        fsys.provisioned = 1073741824
        fsys.destroyed = False
        fsys.nfs = None
        fsys.smb = None
        fsys.multi_protocol = None
        fsys.hard_limit_enabled = False
        fsys.promotion_status = "promoted"
        fsys.requested_promotion_state = "promoted"
        fsys.writable = True
        fsys.source = None
        fsys.location = None
        fsys.default_group_quota = 0
        fsys.default_user_quota = 0
        fsys.http = Mock(enabled=False)
        if eradication_mode is None:
            fsys.eradication_config = None
        else:
            fsys.eradication_config = Mock(eradication_mode=eradication_mode)
        return fsys

    def test_generate_fs_worm_policies_dict_maps_filesystem_to_policy(self):
        """GET file-systems/worm-data-policies lists one member per attached
        WORM data policy; the helper keys them by filesystem name."""
        mock_blade = Mock()
        member = Mock()
        member.member = Mock()
        member.member.name = "fs1"
        member.policy = Mock()
        member.policy.name = "worm1"
        mock_blade.get_file_systems_worm_data_policies.return_value.items = [member]

        result = generate_fs_worm_policies_dict(mock_blade)

        assert result == {"fs1": "worm1"}
        mock_blade.get_file_systems_worm_data_policies.assert_called_once_with()

    def test_generate_fs_worm_policies_dict_without_members_is_empty(self):
        """No WORM filesystem on the array gives an empty map, not None, so
        generate_fs_dict still adds the keys with worm_policy None."""
        mock_blade = Mock()
        mock_blade.get_file_systems_worm_data_policies.return_value.items = []

        assert generate_fs_worm_policies_dict(mock_blade) == {}

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_info.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def test_generate_fs_dict_reports_eradication_mode_and_worm_policy(self):
        """With a membership map every filesystem reports its eradication
        mode and the attached WORM data policy, None when it has none."""
        mock_blade = Mock()
        mock_blade.get_file_systems.return_value.items = [
            self._fs_for_worm("fs1", "retention-based"),
            self._fs_for_worm("fs2", "permission-based"),
        ]
        mock_blade.get_quotas_groups.return_value.items = []
        mock_blade.get_quotas_users.return_value.items = []

        result = generate_fs_dict(mock_blade, worm_policies={"fs1": "worm1"})

        assert result["fs1"]["eradication_mode"] == "retention-based"
        assert result["fs1"]["worm_policy"] == "worm1"
        assert result["fs2"]["eradication_mode"] == "permission-based"
        assert result["fs2"]["worm_policy"] is None
        # no exports list was given, so the REST 2.16 key stays absent
        assert "file_system_exports" not in result["fs1"]

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_info.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def test_generate_fs_dict_missing_eradication_config_reports_none(self):
        """A filesystem whose eradication_config the array omits reports
        eradication_mode None instead of raising."""
        mock_blade = Mock()
        mock_blade.get_file_systems.return_value.items = [self._fs_for_worm("fs1")]
        mock_blade.get_quotas_groups.return_value.items = []
        mock_blade.get_quotas_users.return_value.items = []

        result = generate_fs_dict(mock_blade, worm_policies={})

        assert result["fs1"]["eradication_mode"] is None
        assert result["fs1"]["worm_policy"] is None

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_info.get_rest_api_version",
        Mock(return_value="2.14"),
    )
    def test_generate_fs_dict_without_worm_support_omits_the_keys(self):
        """Before REST 2.15 main() passes no membership map and both keys are
        left out, like file_system_exports before REST 2.16."""
        mock_blade = Mock()
        mock_blade.get_file_systems.return_value.items = [
            self._fs_for_worm("fs1", "retention-based")
        ]
        mock_blade.get_quotas_groups.return_value.items = []
        mock_blade.get_quotas_users.return_value.items = []

        result = generate_fs_dict(mock_blade)

        assert "eradication_mode" not in result["fs1"]
        assert "worm_policy" not in result["fs1"]
        assert "file_system_exports" not in result["fs1"]

    @patch("plugins.modules.purefb_info.generate_fs_worm_policies_dict")
    @patch("plugins.modules.purefb_info.generate_file_system_exports_dict")
    @patch("plugins.modules.purefb_info.generate_fs_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_info.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def test_main_filesystems_subset_passes_worm_policies_from_rest_2_15(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_fs,
        mock_generate_exports,
        mock_generate_worm,
    ):
        """On REST 2.15+ main() reads the WORM memberships once and hands
        them to generate_fs_dict together with the exports list."""
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["filesystems"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        mock_generate_exports.return_value = []
        mock_generate_worm.return_value = {"fs1": "worm1"}
        mock_generate_fs.return_value = {"fs1": {"worm_policy": "worm1"}}

        main()

        mock_generate_worm.assert_called_once_with(mock_blade)
        mock_generate_fs.assert_called_once_with(
            mock_blade, [], "2.30", {"fs1": "worm1"}
        )
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["purefb_info"]["filesystems"]["fs1"]["worm_policy"] == "worm1"

    @patch("plugins.modules.purefb_info.generate_fs_worm_policies_dict")
    @patch("plugins.modules.purefb_info.generate_file_system_exports_dict")
    @patch("plugins.modules.purefb_info.generate_fs_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_info.get_rest_api_version",
        Mock(return_value="2.14"),
    )
    def test_main_filesystems_subset_skips_worm_policies_before_rest_2_15(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_fs,
        mock_generate_exports,
        mock_generate_worm,
    ):
        """Before REST 2.15 the worm-data-policies endpoint is never called
        and generate_fs_dict gets None for both optional inputs."""
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["filesystems"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        mock_generate_fs.return_value = {}

        main()

        mock_generate_worm.assert_not_called()
        mock_generate_exports.assert_not_called()
        mock_generate_fs.assert_called_once_with(mock_blade, None, "2.14", None)
        call_args = mock_module.exit_json.call_args[1]
        assert "file_system_exports" not in call_args["purefb_info"]

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

        assert result == {"diagnostics": {}, "diagnostics_settings": {}, "manifest": {}}
        mock_blade.get_support_diagnostics_settings.assert_not_called()
        mock_blade.get_support_system_manifest.assert_not_called()

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


class TestGenerateEvictionPoliciesDict:
    """Data eviction policies read-back (REST 2.21)."""

    def test_generate_eviction_policies_dict(self):
        """Policies carry keep_size and their attached file systems."""
        from plugins.modules.purefb_info import generate_eviction_policies_dict

        policy = Mock(spec=["name", "enabled", "is_local", "keep_size"])
        policy.name = "edge_cache"
        policy.enabled = True
        policy.is_local = True
        policy.keep_size = 107374182400
        member = Mock(spec=["policy", "member"])
        member.policy = Mock(spec=["name"])
        member.policy.name = "edge_cache"
        member.member = Mock(spec=["name"])
        member.member.name = "project_data"
        stray = Mock(spec=["policy", "member"])
        stray.policy = Mock(spec=["name"])
        stray.policy.name = "other"
        stray.member = Mock(spec=["name"])
        stray.member.name = "ignored"

        blade = Mock()
        blade.get_data_eviction_policies.return_value = Mock(
            status_code=200, items=[policy]
        )
        blade.get_data_eviction_policies_file_systems.return_value = Mock(
            status_code=200, items=[member, stray]
        )

        assert generate_eviction_policies_dict(blade) == {
            "edge_cache": {
                "local": True,
                "enabled": True,
                "keep_size": 107374182400,
                "realms": [],
                "file_systems": ["project_data"],
            }
        }

    def test_generate_eviction_policies_dict_tolerates_errors(self):
        """A failed policies read yields an empty dict and skips the members read."""
        from plugins.modules.purefb_info import generate_eviction_policies_dict

        blade = Mock()
        blade.get_data_eviction_policies.return_value = Mock(status_code=400, items=[])
        assert generate_eviction_policies_dict(blade) == {}
        blade.get_data_eviction_policies_file_systems.assert_not_called()


class TestPurefbInfoPublicKeys:
    """Public keys read-back of the admins subset"""

    def test_generate_public_keys_dict_groups_uses_by_key(self):
        key = Mock(spec=["name", "public_key", "algorithm", "key_size"])
        key.name = "ca-signer"
        key.public_key = "ssh-ed25519 AAAA"
        key.algorithm = "ed25519"
        key.key_size = 256
        unused = Mock(spec=["name", "public_key", "algorithm", "key_size"])
        unused.name = "test"
        unused.public_key = "-----BEGIN PUBLIC KEY-----"
        unused.algorithm = "rsa"
        unused.key_size = 2048
        ref = Mock(spec=["name", "resource_type"])
        ref.name = "ca-policy"
        ref.resource_type = "ssh-certificate-authority-policies"
        use = Mock(spec=["name", "use"])
        use.name = "ca-signer"
        use.use = ref

        mock_blade = Mock()
        mock_blade.get_public_keys.return_value.status_code = 200
        mock_blade.get_public_keys.return_value.items = [key, unused]
        mock_blade.get_public_keys_uses.return_value.status_code = 200
        mock_blade.get_public_keys_uses.return_value.items = [use]

        result = generate_public_keys_dict(mock_blade)

        assert result["ca-signer"] == {
            "algorithm": "ed25519",
            "key_size": 256,
            "public_key": "ssh-ed25519 AAAA",
            "uses": [
                {
                    "name": "ca-policy",
                    "resource_type": "ssh-certificate-authority-policies",
                }
            ],
        }
        assert result["test"]["algorithm"] == "rsa"
        assert result["test"]["uses"] == []

    def test_generate_public_keys_dict_returns_empty_when_endpoint_errors(self):
        mock_blade = Mock()
        mock_blade.get_public_keys.return_value.status_code = 400
        assert generate_public_keys_dict(mock_blade) == {}
        mock_blade.get_public_keys_uses.assert_not_called()

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_public_keys_dict")
    @patch("plugins.modules.purefb_info.generate_admin_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_admins_subset_adds_public_keys(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_admin,
        mock_generate_public_keys,
        mock_loose_version,
    ):
        """admins subset returns public_keys from REST 2.14"""
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["admins"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.14"]
        mock_get_system.return_value = mock_blade
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        mock_generate_admin.return_value = {"pureuser": {}}
        mock_generate_public_keys.return_value = {"ca-signer": {}}

        main()

        mock_generate_admin.assert_called_once_with(mock_blade)
        mock_generate_public_keys.assert_called_once_with(mock_blade)
        info = mock_module.exit_json.call_args[1]["purefb_info"]
        assert info["admins"] == {"pureuser": {}}
        assert info["public_keys"] == {"ca-signer": {}}

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_public_keys_dict")
    @patch("plugins.modules.purefb_info.generate_admin_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_admins_subset_skips_public_keys_on_old_rest(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_admin,
        mock_generate_public_keys,
        mock_loose_version,
    ):
        """admins subset leaves public_keys out before REST 2.14"""
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["admins"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.13"]
        mock_get_system.return_value = mock_blade
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        mock_generate_admin.return_value = {}

        main()

        mock_generate_public_keys.assert_not_called()
        info = mock_module.exit_json.call_args[1]["purefb_info"]
        assert "public_keys" not in info


from plugins.modules.purefb_info import (
    generate_capacity_dict,
    generate_object_store_accounts_dict,
)


class TestPurefbInfoSpace:
    """Space figures of the capacity subset, file systems, buckets and object
    store accounts, each returned from the REST version that reports it.

    The space objects carry exactly the figures the SDK model of a REST
    version has: one the array did not send is None, one the model does not
    have raises AttributeError.
    """

    SPACE_2_0 = ("data_reduction", "snapshots", "total_physical", "unique", "virtual")
    # the space of a bucket on REST 2.8 to 2.10
    SPACE_EXTENDED_2_8 = SPACE_2_0 + ("total_provisioned",)
    SPACE_2_11 = SPACE_2_0 + (
        "total_provisioned",
        "available_provisioned",
        "available_ratio",
        "destroyed",
        "destroyed_virtual",
    )
    SPACE_2_15 = SPACE_2_11 + ("shared",)
    SPACE_2_16 = SPACE_2_15 + ("total_used",)

    # Space of GET /arrays/space, of its file-system and object-store types
    # and of a bucket as a Purity//FB 4.8.8 array returns them. The array
    # sends no provisioned figures here.
    AGGREGATE = {
        "data_reduction": 1.5,
        "destroyed": 0,
        "destroyed_virtual": 0,
        "shared": 27354,
        "snapshots": 0,
        "total_physical": 178847773,
        "total_used": 178847773,
        "unique": 178820419,
        "virtual": 273155759,
    }
    FILE_SYSTEM = {
        "data_reduction": 1103.5,
        "destroyed": 0,
        "destroyed_virtual": 0,
        "shared": 0,
        "snapshots": 0,
        "total_physical": 85521,
        "total_used": 85521,
        "unique": 85521,
        "virtual": 94371840,
    }
    OBJECT_STORE = {
        "data_reduction": 1.0,
        "destroyed": 0,
        "destroyed_virtual": 0,
        "shared": 0,
        "snapshots": 0,
        "total_physical": 178734756,
        "total_used": 178734756,
        "unique": 178734756,
        "virtual": 178783407,
    }
    BUCKET = {
        "data_reduction": 2.1,
        "destroyed": 0,
        "destroyed_virtual": 0,
        "shared": 0,
        "snapshots": 0,
        "total_physical": 2476,
        "total_used": 2476,
        "unique": 2476,
        "virtual": 5120,
    }
    # A container with a hard limit also reports the provisioned figures
    LIMITED = dict(
        FILE_SYSTEM,
        total_provisioned=1073741824,
        available_provisioned=979369984,
        available_ratio=0.912109375,
    )

    @staticmethod
    def _space(fields, sent):
        return SimpleNamespace(**{field: sent.get(field) for field in fields})

    def _capacity_blade(self, fields, aggregate, file_system, object_store):
        reads = {
            None: aggregate,
            "file-system": file_system,
            "object-store": object_store,
        }

        def arrays_space(**kwargs):
            response = Mock()
            response.items = [
                SimpleNamespace(
                    capacity=197912092999680,
                    space=self._space(fields, reads[kwargs.get("type")]),
                )
            ]
            return response

        blade = Mock()
        blade.get_arrays_space.side_effect = arrays_space
        return blade

    @staticmethod
    def _file_system(name, space):
        return SimpleNamespace(
            name=name,
            fast_remove_directory_enabled=False,
            snapshot_directory_enabled=False,
            provisioned=1073741824,
            destroyed=False,
            nfs=SimpleNamespace(
                rules=None, v3_enabled=True, v4_1_enabled=True, export_policy=None
            ),
            smb=None,
            multi_protocol=None,
            http=SimpleNamespace(enabled=False),
            hard_limit_enabled=True,
            promotion_status="promoted",
            requested_promotion_state="promoted",
            writable=True,
            source=None,
            default_group_quota=0,
            default_user_quota=0,
            space=space,
        )

    @staticmethod
    def _fs_blade(file_systems):
        blade = Mock()
        blade.get_file_systems.return_value.items = file_systems
        blade.get_quotas_groups.return_value.items = []
        blade.get_quotas_users.return_value.items = []
        return blade

    @staticmethod
    def _bucket(name, account, space):
        return SimpleNamespace(
            name=name,
            id=name + "-id",
            versioning="none",
            object_count=3,
            account=SimpleNamespace(name=account),
            created=1700000000000,
            destroyed=False,
            retention_lock="unlocked",
            quota_limit=None,
            object_lock_config=SimpleNamespace(
                enabled=False, freeze_locked_objects=False
            ),
            eradication_config=SimpleNamespace(manual_eradication="enabled"),
            space=space,
        )

    @staticmethod
    def _bucket_blade(buckets):
        blade = Mock()
        blade.get_buckets.return_value.items = buckets
        blade.get_lifecycle_rules.return_value.items = []
        return blade

    @staticmethod
    def _account_blade(accounts):
        blade = Mock()
        blade.get_object_store_accounts.return_value.items = accounts
        blade.get_object_store_users.return_value.items = []
        return blade

    # ---------------- the version gates ----------------

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    def test_space_figures_follow_the_rest_version(self):
        """A figure is returned from the REST version that has it and versions
        compare as numbers, so 2.8 and 2.9 are older than 2.11."""
        space = self._space(self.SPACE_2_16, self.LIMITED)
        base = set(self.SPACE_2_0)
        extended = set(self.SPACE_2_11)

        for version in ("2.0", "2.7", "2.8", "2.9", "2.10"):
            assert (
                set(purefb_info_module._space_figures(space, version)) == base
            ), version
        for version in ("2.11", "2.14"):
            assert (
                set(purefb_info_module._space_figures(space, version)) == extended
            ), version
        assert set(purefb_info_module._space_figures(space, "2.15")) == extended | {
            "shared"
        }
        for version in ("2.16", "2.30"):
            figures = purefb_info_module._space_figures(space, version)
            assert set(figures) == set(self.SPACE_2_16), version
            assert figures == self.LIMITED

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    def test_space_figures_provisioned_gate_of_buckets_and_accounts(self):
        """Buckets and object store accounts report total_provisioned from
        REST 2.8, three versions before the other object types."""
        space = self._space(self.SPACE_EXTENDED_2_8, self.LIMITED)
        gate = purefb_info_module.SPACE_PROVISIONED_API_VERSION

        assert gate == "2.8"
        assert "total_provisioned" not in purefb_info_module._space_figures(
            space, "2.7", gate
        )
        for version in ("2.8", "2.10"):
            figures = purefb_info_module._space_figures(space, version, gate)
            assert figures["total_provisioned"] == 1073741824, version
            assert "available_provisioned" not in figures
            assert "total_provisioned" not in purefb_info_module._space_figures(
                space, version
            )

    def test_space_gate_constants(self):
        assert purefb_info_module.SPACE_API_VERSION == "2.11"
        assert purefb_info_module.SPACE_SHARED_API_VERSION == "2.15"
        assert purefb_info_module.SPACE_TOTAL_USED_API_VERSION == "2.16"

    # ---------------- capacity subset ----------------

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    def test_capacity_object_store_virtual_is_not_the_file_system_virtual(self):
        """The object-store block reports the virtual space of the
        object-store read and the per-type blocks the shared space of their
        own read, where the array total differs from both."""
        blade = self._capacity_blade(
            self.SPACE_2_16, self.AGGREGATE, self.FILE_SYSTEM, self.OBJECT_STORE
        )

        result = generate_capacity_dict(blade, "2.30")

        assert result["file-system"]["virtual"] == 94371840
        assert result["object-store"]["virtual"] == 178783407
        assert result["aggregate"]["virtual"] == 273155759
        assert result["aggregate"]["shared"] == 27354
        assert result["file-system"]["shared"] == 0
        assert result["object-store"]["shared"] == 0

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    def test_capacity_blocks_report_their_own_read(self):
        """Every block holds all the figures of its own array space read and
        keeps the keys of the figures the array did not send."""
        blade = self._capacity_blade(
            self.SPACE_2_16, self.AGGREGATE, self.FILE_SYSTEM, self.OBJECT_STORE
        )

        result = generate_capacity_dict(blade, "2.30")

        assert result["total"] == 197912092999680
        for block, read in (
            ("aggregate", self.AGGREGATE),
            ("file-system", self.FILE_SYSTEM),
            ("object-store", self.OBJECT_STORE),
        ):
            for field, figure in read.items():
                assert result[block][field] == figure, (block, field)
            # the array sent no provisioned figures; the keys stay, as null
            for field in (
                "total_provisioned",
                "available_provisioned",
                "available_ratio",
            ):
                assert field in result[block]
                assert result[block][field] is None

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    def test_capacity_blocks_report_their_own_provisioned_figures(self):
        """The provisioned and destroyed figures of a per-type block come
        from the read of that type when the array sends them."""
        aggregate = dict(
            self.AGGREGATE,
            total_provisioned=3000,
            available_provisioned=1800,
            available_ratio=0.6,
            destroyed=30,
            destroyed_virtual=60,
        )
        file_system = dict(
            self.FILE_SYSTEM,
            total_provisioned=1000,
            available_provisioned=900,
            available_ratio=0.9,
            destroyed=10,
            destroyed_virtual=20,
        )
        object_store = dict(
            self.OBJECT_STORE,
            total_provisioned=2000,
            available_provisioned=900,
            available_ratio=0.45,
            destroyed=20,
            destroyed_virtual=40,
        )
        blade = self._capacity_blade(
            self.SPACE_2_16, aggregate, file_system, object_store
        )

        result = generate_capacity_dict(blade, "2.30")

        assert result["aggregate"] == aggregate
        assert result["file-system"] == file_system
        assert result["object-store"] == object_store

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    def test_capacity_total_used_from_rest_2_16(self):
        """total_used is added to every block from REST 2.16; shared, which
        the blocks carry on every version, has a value from REST 2.15."""
        blade = self._capacity_blade(
            self.SPACE_2_15, self.AGGREGATE, self.FILE_SYSTEM, self.OBJECT_STORE
        )
        result = generate_capacity_dict(blade, "2.15")
        for block in ("aggregate", "file-system", "object-store"):
            assert "total_used" not in result[block]
        assert result["aggregate"]["shared"] == 27354

        blade = self._capacity_blade(
            self.SPACE_2_16, self.AGGREGATE, self.FILE_SYSTEM, self.OBJECT_STORE
        )
        result = generate_capacity_dict(blade, "2.16")
        assert result["aggregate"]["total_used"] == 178847773
        assert result["file-system"]["total_used"] == 85521
        assert result["object-store"]["total_used"] == 178734756

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    def test_capacity_before_rest_2_11_keeps_the_keys_null(self):
        """The space of REST 2.10 and earlier has five figures. The blocks
        keep their other keys, as null, instead of failing on a figure the
        model does not have."""
        blade = self._capacity_blade(
            self.SPACE_2_0, self.AGGREGATE, self.FILE_SYSTEM, self.OBJECT_STORE
        )

        result = generate_capacity_dict(blade, "2.10")

        assert result["object-store"] == {
            "data_reduction": 1.0,
            "snapshots": 0,
            "total_physical": 178734756,
            "unique": 178734756,
            "virtual": 178783407,
            "total_provisioned": None,
            "available_provisioned": None,
            "available_ratio": None,
            "destroyed": None,
            "destroyed_virtual": None,
            "shared": None,
        }
        assert result["file-system"]["virtual"] == 94371840

    # ---------------- file systems ----------------

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_info.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def test_fs_dict_reports_space_and_data_reduction(self):
        """A file system reports its space under the names the bucket entries
        use, inside a realm and outside, and keeps its own keys."""
        blade = self._fs_blade(
            [
                self._file_system("fs1", self._space(self.SPACE_2_16, self.LIMITED)),
                self._file_system(
                    "realm1::fs1", self._space(self.SPACE_2_16, self.FILE_SYSTEM)
                ),
            ]
        )

        result = generate_fs_dict(blade)

        limited = result["fs1"]
        assert limited["data_reduction"] == 1103.5
        assert limited["snapshot_space"] == 0
        assert limited["total_physical_space"] == 85521
        assert limited["unique_space"] == 85521
        assert limited["virtual_space"] == 94371840
        assert limited["total_provisioned_space"] == 1073741824
        assert limited["available_provisioned_space"] == 979369984
        assert limited["available_ratio"] == 0.912109375
        assert limited["destroyed_space"] == 0
        assert limited["destroyed_virtual_space"] == 0
        assert limited["shared_space"] == 0
        assert limited["total_used_space"] == 85521
        # the keys the entry had are not overwritten by a space figure
        assert limited["destroyed"] is False
        assert limited["provisioned"] == 1073741824
        assert limited["hard_limit"] is True

        in_realm = result["realm1::fs1"]
        assert in_realm["data_reduction"] == 1103.5
        assert in_realm["virtual_space"] == 94371840
        assert in_realm["total_used_space"] == 85521
        # figures of the REST version the array did not send are null
        assert in_realm["total_provisioned_space"] is None
        assert in_realm["available_provisioned_space"] is None
        assert in_realm["available_ratio"] is None

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    def test_fs_dict_space_follows_the_rest_version(self):
        """Only the figures the REST version of the array has are returned."""
        base = {
            "data_reduction",
            "snapshot_space",
            "total_physical_space",
            "unique_space",
            "virtual_space",
        }
        extended = {
            "total_provisioned_space",
            "available_provisioned_space",
            "available_ratio",
            "destroyed_space",
            "destroyed_virtual_space",
        }
        later = extended | {"shared_space", "total_used_space"}
        cases = (
            ("2.0", self.SPACE_2_0, base),
            ("2.10", self.SPACE_2_0, base),
            ("2.11", self.SPACE_2_11, base | extended),
            ("2.15", self.SPACE_2_15, base | extended | {"shared_space"}),
            ("2.16", self.SPACE_2_16, base | later),
        )
        for version, fields, expected in cases:
            blade = self._fs_blade(
                [self._file_system("realm1::fs1", self._space(fields, self.LIMITED))]
            )
            with patch(
                "plugins.modules.purefb_info.get_rest_api_version",
                Mock(return_value=version),
            ):
                entry = generate_fs_dict(blade)["realm1::fs1"]
            assert set(entry) & (base | later) == expected, version
            assert entry["data_reduction"] == 1103.5, version
            assert entry["virtual_space"] == 94371840, version
            assert entry["destroyed"] is False, version

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_info.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def test_fs_dict_without_space_reports_null_figures(self):
        """A file system the array returns without a space keeps the keys."""
        blade = self._fs_blade([self._file_system("fs1", None)])

        entry = generate_fs_dict(blade)["fs1"]

        assert entry["data_reduction"] is None
        assert entry["total_used_space"] is None
        assert entry["provisioned"] == 1073741824

    # ---------------- buckets ----------------

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    def test_bucket_dict_reports_total_used_and_shared(self):
        """A bucket adds shared_space and total_used_space to the figures it
        had, for a bucket of a realm as for any other."""
        blade = self._bucket_blade(
            [
                self._bucket(
                    "bkt1", "acct1", self._space(self.SPACE_2_16, self.BUCKET)
                ),
                self._bucket(
                    "realm1::bkt1",
                    "realm1::acct1",
                    self._space(self.SPACE_2_16, self.BUCKET),
                ),
            ]
        )

        result = generate_bucket_dict(blade, "2.30")

        for name in ("bkt1", "realm1::bkt1"):
            entry = result[name]
            assert entry["data_reduction"] == 2.1
            assert entry["snapshot_space"] == 0
            assert entry["total_physical_space"] == 2476
            assert entry["unique_space"] == 2476
            assert entry["virtual_space"] == 5120
            assert entry["destroyed_space"] == 0
            assert entry["destroyed_virtual_space"] == 0
            assert entry["shared_space"] == 0
            assert entry["total_used_space"] == 2476
            # not sent for a bucket without a hard limit
            assert entry["total_provisioned_space"] is None
            assert entry["available_provisioned_space"] is None
            assert entry["available_ratio"] is None
            # the destroyed flag of the bucket is not the destroyed space
            assert entry["destroyed"] is False
        assert result["realm1::bkt1"]["account_name"] == "realm1::acct1"

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    def test_bucket_dict_space_follows_the_rest_version(self):
        """shared_space is returned from REST 2.15 and total_used_space from
        2.16; the other space keys are returned on every version, null
        before the version that reports them."""
        entry = generate_bucket_dict(
            self._bucket_blade(
                [
                    self._bucket(
                        "bkt1", "acct1", self._space(self.SPACE_2_0, self.BUCKET)
                    )
                ]
            ),
            "2.7",
        )["bkt1"]
        assert entry["data_reduction"] == 2.1
        assert entry["virtual_space"] == 5120
        for key in (
            "total_provisioned_space",
            "available_provisioned_space",
            "available_ratio",
            "destroyed_space",
            "destroyed_virtual_space",
        ):
            assert key in entry
            assert entry[key] is None
        assert "shared_space" not in entry
        assert "total_used_space" not in entry

        limited = dict(self.BUCKET, total_provisioned=1048576)
        entry = generate_bucket_dict(
            self._bucket_blade(
                [
                    self._bucket(
                        "bkt1", "acct1", self._space(self.SPACE_EXTENDED_2_8, limited)
                    )
                ]
            ),
            "2.8",
        )["bkt1"]
        assert entry["total_provisioned_space"] == 1048576
        assert entry["destroyed_space"] is None
        assert "shared_space" not in entry

        entry = generate_bucket_dict(
            self._bucket_blade(
                [self._bucket("bkt1", "acct1", self._space(self.SPACE_2_15, limited))]
            ),
            "2.15",
        )["bkt1"]
        assert entry["shared_space"] == 0
        assert entry["destroyed_space"] == 0
        assert "total_used_space" not in entry

    # ---------------- object store accounts ----------------

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    def test_accounts_dict_reports_total_used_and_shared(self):
        """An account adds shared_space and total_used_space to the figures
        it had, for an account of a realm as for any other."""
        accounts = [
            SimpleNamespace(
                name=name,
                object_count=3,
                space=self._space(self.SPACE_2_16, self.OBJECT_STORE),
            )
            for name in ("acct1", "realm1::acct1")
        ]
        blade = self._account_blade(accounts)

        result = generate_object_store_accounts_dict(blade, "2.30")

        for name in ("acct1", "realm1::acct1"):
            entry = result[name]
            assert entry["data_reduction"] == 1.0
            assert entry["snapshots_space"] == 0
            assert entry["total_physical_space"] == 178734756
            assert entry["unique_space"] == 178734756
            assert entry["virtual_space"] == 178783407
            assert entry["destroyed_space"] == 0
            assert entry["destroyed_virtual_space"] == 0
            assert entry["shared_space"] == 0
            assert entry["total_used_space"] == 178734756
            assert entry["total_provisioned_space"] is None
            assert entry["total_provisioned"] is None
            assert entry["users"] == {}
        blade.get_object_store_users.assert_any_call(filter='name="realm1::acct1/*"')

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    def test_accounts_dict_space_follows_the_rest_version(self):
        """Before REST 2.15 an account has neither shared_space nor
        total_used_space, and from 2.15 only the first."""
        for version, fields, shared in (
            ("2.14", self.SPACE_2_11, False),
            ("2.15", self.SPACE_2_15, True),
        ):
            account = SimpleNamespace(
                name="acct1",
                object_count=3,
                space=self._space(fields, self.OBJECT_STORE),
            )
            entry = generate_object_store_accounts_dict(
                self._account_blade([account]), version
            )["acct1"]
            assert ("shared_space" in entry) is shared, version
            assert "total_used_space" not in entry, version
            assert entry["destroyed_space"] == 0, version
            assert entry["virtual_space"] == 178783407, version

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    def test_accounts_dict_reads_a_dictionary_space(self):
        """On REST 2.8 to 2.10 the SDK returns the space of an account as a
        plain dictionary; its figures are read like those of a model."""
        account = SimpleNamespace(
            name="acct1",
            object_count=3,
            space={
                "data_reduction": 1.0,
                "snapshots": 0,
                "total_physical": 178734756,
                "unique": 178734756,
                "virtual": 178783407,
                "total_provisioned": 1073741824,
            },
        )

        entry = generate_object_store_accounts_dict(
            self._account_blade([account]), "2.10"
        )["acct1"]

        assert entry["data_reduction"] == 1.0
        assert entry["snapshots_space"] == 0
        assert entry["virtual_space"] == 178783407
        assert entry["total_provisioned_space"] == 1073741824
        assert entry["total_provisioned"] == 1073741824
        assert entry["available_provisioned_space"] is None
        assert "total_used_space" not in entry

    # ---------------- namesakes ----------------

    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_info.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def test_namesakes_keep_their_own_figures(self):
        """The same leaf name at array level and in two realms gives three
        entries, each with the figures of its own object."""
        names = ("same", "realm1::same", "realm2::same")
        spaces = {
            name: dict(self.BUCKET, virtual=1000 * step, total_used=100 * step)
            for step, name in enumerate(names, start=1)
        }

        file_systems = generate_fs_dict(
            self._fs_blade(
                [
                    self._file_system(name, self._space(self.SPACE_2_16, spaces[name]))
                    for name in names
                ]
            )
        )
        buckets = generate_bucket_dict(
            self._bucket_blade(
                [
                    self._bucket(
                        name,
                        name.replace("same", "acct"),
                        self._space(self.SPACE_2_16, spaces[name]),
                    )
                    for name in names
                ]
            ),
            "2.30",
        )
        accounts = generate_object_store_accounts_dict(
            self._account_blade(
                [
                    SimpleNamespace(
                        name=name,
                        object_count=3,
                        space=self._space(self.SPACE_2_16, spaces[name]),
                    )
                    for name in names
                ]
            ),
            "2.30",
        )

        for entries in (file_systems, buckets, accounts):
            assert sorted(entries) == sorted(names)
            for step, name in enumerate(names, start=1):
                assert entries[name]["virtual_space"] == 1000 * step, name
                assert entries[name]["total_used_space"] == 100 * step, name
        assert buckets["same"]["account_name"] == "acct"
        assert buckets["realm2::same"]["account_name"] == "realm2::acct"

    # ---------------- main ----------------

    @patch("plugins.modules.purefb_info.generate_object_store_virtual_hosts_dict")
    @patch("plugins.modules.purefb_info.generate_object_store_accounts_dict")
    @patch("plugins.modules.purefb_info.generate_bucket_dict")
    @patch("plugins.modules.purefb_info.generate_capacity_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    @patch("plugins.modules.purefb_info.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_info.get_rest_api_version",
        Mock(return_value="2.15"),
    )
    def test_main_passes_the_rest_version_to_the_space_readers(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_capacity,
        mock_generate_bucket,
        mock_generate_accounts,
        mock_generate_virtual_hosts,
    ):
        """main() hands the REST version of the array to the capacity,
        buckets and accounts readers, which gate their figures on it."""
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["capacity", "buckets", "accounts"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        mock_generate_capacity.return_value = {"total": 1}
        mock_generate_bucket.return_value = {"bkt1": {}}
        mock_generate_accounts.return_value = {"acct1": {}}
        mock_generate_virtual_hosts.return_value = {}

        main()

        mock_generate_capacity.assert_called_once_with(mock_blade, "2.15")
        mock_generate_bucket.assert_called_once_with(mock_blade, "2.15")
        mock_generate_accounts.assert_called_once_with(mock_blade, "2.15")
        info = mock_module.exit_json.call_args[1]["purefb_info"]
        assert info["capacity"] == {"total": 1}
        assert info["buckets"] == {"bkt1": {}}
        assert info["accounts"] == {"acct1": {}}


class TestPurefbInfoSoftwareSupport:
    """Tests for the software and support subsets."""

    @staticmethod
    def _response(items):
        response = Mock()
        response.status_code = 200
        response.items = items
        return response

    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_software_dict_keys_repeating_names_by_id(
        self, mock_loose_version
    ):
        """Checks, installations and steps are keyed by id; packages by version."""
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        check = Mock(spec=["name", "status", "details"])
        check.name = "Firmware check"
        check.status = "passed"
        check.details = "No issues found."
        task = Mock(
            spec=[
                "id",
                "name",
                "status",
                "software_name",
                "software_version",
                "software_upgrade_hops",
                "start_time",
                "end_time",
                "details",
                "checks",
            ]
        )
        task.id = "task-1"
        task.name = "Purity//FB_4.8.8"
        task.status = "passed"
        task.software_name = "Purity//FB"
        task.software_version = "4.6.4"
        task.software_upgrade_hops = ["4.6.4", "4.8.8"]
        task.start_time = 1794862200
        task.end_time = 1794862433
        task.details = None
        task.checks = [check]
        package = Mock(
            spec=[
                "id",
                "name",
                "version",
                "status",
                "progress",
                "details",
                "payload_id",
                "upgrade_hops",
            ]
        )
        package.id = "679"
        package.name = "Purity//FB"
        package.version = "4.8.8"
        package.status = "download_failed"
        package.progress = 0.0
        package.details = "Software download failed"
        package.payload_id = "abc"
        package.upgrade_hops = ["4.6.4", "4.8.8"]
        software_ref = Mock(spec=["id", "name"])
        software_ref.id = "679"
        software_ref.name = None
        installation = Mock(
            spec=[
                "id",
                "name",
                "status",
                "mode",
                "software",
                "current_step_id",
                "start_time",
                "end_time",
                "details",
                "override_checks",
                "upgrade_parameters",
            ]
        )
        installation.id = "inst-1"
        installation.name = "Purity//FB_4.8.8"
        installation.status = "paused"
        installation.mode = "interactive"
        installation.software = software_ref
        installation.current_step_id = "step-1"
        installation.start_time = 1
        installation.end_time = None
        installation.details = None
        installation.override_checks = []
        installation.upgrade_parameters = None
        step_check = Mock(spec=["name", "status", "overridable", "details"])
        step_check.name = "Drive move check"
        step_check.status = "failed"
        step_check.overridable = True
        step_check.details = "-"
        inst_ref = Mock(spec=["id", "name"])
        inst_ref.id = "inst-1"
        inst_ref.name = None
        step = Mock(
            spec=[
                "id",
                "name",
                "description",
                "details",
                "status",
                "hop_version",
                "installation",
                "start_time",
                "end_time",
                "checks",
            ]
        )
        step.id = "step-1"
        step.name = "upgrade checks"
        step.description = "Run the upgrade checks"
        step.details = None
        step.status = "running"
        step.hop_version = "4.8.8"
        step.installation = inst_ref
        step.start_time = 2
        step.end_time = None
        step.checks = [step_check]
        version = Mock(
            spec=["name", "version", "release_family", "details", "upgrade_hops"]
        )
        version.name = "Purity//FB"
        version.version = "4.8.9"
        version.release_family = "4.8"
        version.details = None
        version.upgrade_hops = ["4.8.8", "4.8.9"]

        mock_blade = Mock()
        mock_blade.get_software_check.return_value = self._response([task])
        mock_blade.get_software_bundle.return_value = self._response([])
        mock_blade.get_software_patches.return_value = self._response([])
        mock_blade.get_software_versions.return_value = self._response([version])
        mock_blade.get_software.return_value = self._response([package])
        mock_blade.get_software_installations.return_value = self._response(
            [installation]
        )
        mock_blade.get_software_installation_steps.return_value = self._response([step])

        result = generate_software_dict(mock_blade, "2.30")

        assert result["checks"]["task-1"]["name"] == "Purity//FB_4.8.8"
        assert result["checks"]["task-1"]["software_upgrade_hops"] == ["4.6.4", "4.8.8"]
        assert result["checks"]["task-1"]["checks"][0]["name"] == "Firmware check"
        assert result["packages"]["4.8.8"]["status"] == "download_failed"
        assert result["versions"]["4.8.9"]["release_family"] == "4.8"
        assert result["installations"]["inst-1"]["software"] == "679"
        assert result["installations"]["inst-1"]["upgrade_parameters"] == []
        assert result["installation_steps"]["step-1"]["installation"] == "inst-1"
        assert (
            result["installation_steps"]["step-1"]["checks"][0]["overridable"] is True
        )
        assert result["bundles"] == {}
        assert result["patches"] == {}

    @patch("plugins.modules.purefb_info.LooseVersion")
    def test_generate_software_dict_respects_version_gates(self, mock_loose_version):
        """Below REST 2.16 nothing is called and every group is empty."""
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        mock_blade = Mock()

        result = generate_software_dict(mock_blade, "2.15")

        assert result == {
            "versions": {},
            "packages": {},
            "bundles": {},
            "checks": {},
            "patches": {},
            "installations": {},
            "installation_steps": {},
        }
        mock_blade.get_software_check.assert_not_called()
        mock_blade.get_software.assert_not_called()

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.get_rest_api_version", return_value="2.30")
    def test_generate_support_dict_summarises_manifest(
        self, mock_api_version, mock_loose_version
    ):
        """The manifest header, space and licensed features are kept, components counted."""
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        severity = Mock(spec=["severity", "count"])
        severity.severity = "warning"
        severity.count = 2
        period = Mock(spec=["start_time", "end_time"])
        period.start_time = 10
        period.end_time = 20
        run = Mock(
            spec=[
                "id",
                "name",
                "index",
                "status",
                "version",
                "task_id",
                "start_time",
                "analysis_period",
                "severity_count",
            ]
        )
        run.id = "run-1"
        run.name = "diag"
        run.index = 1
        run.status = "completed"
        run.version = "default"
        run.task_id = "t-1"
        run.start_time = 5
        run.analysis_period = period
        run.severity_count = [severity]
        settings = Mock(spec=["version", "last_updated"])
        settings.version = "default"
        settings.last_updated = None
        manifest = Mock(spec=["system_manifest"])
        manifest.system_manifest = (
            '{"appliance_id": "a-1", "array_name": "fb1", "domain": "example.com", '
            '"manifest_source": "system-manifest-service", "manifest_version": "v1", '
            '"product_family": "FlashBlade//S200", "product_model": "S200", '
            '"purity_version": "4.8.8", "time_zone": "UTC", "timestamp": 1794902547, '
            '"space": {"capacity": 10}, '
            '"components": [{"type": "chassis"}]}'
        )

        mock_blade = Mock()
        mock_blade.get_support_diagnostics.return_value = self._response([run])
        mock_blade.get_support_diagnostics_settings.return_value = self._response(
            [settings]
        )
        mock_blade.get_support_system_manifest.return_value = self._response([manifest])

        result = generate_support_dict(mock_blade)

        # runs are keyed by index, with the tool settings beside them
        assert result["diagnostics"]["1"]["severity_count"] == {
            "info": 0,
            "warning": 2,
            "critical": 0,
        }
        assert result["diagnostics"]["1"]["analysis_period_end"] == 20
        # per-test results belong to purefb_support_diagnostics state=report
        mock_blade.get_support_diagnostics_details.assert_not_called()
        assert result["diagnostics_settings"] == {
            "version": "default",
            "last_updated": None,
        }
        assert result["manifest"]["purity_version"] == "4.8.8"
        assert result["manifest"]["space"] == {"capacity": 10}
        assert "licensed_features" not in result["manifest"]
        assert result["manifest"]["component_count"] == 1
        assert "components" not in result["manifest"]

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.get_rest_api_version", return_value="2.30")
    def test_generate_support_dict_handles_bad_manifest_and_empty_lists(
        self, mock_api_version, mock_loose_version
    ):
        """Unparseable manifest text yields None fields; empty lists yield empty dicts."""
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        manifest = Mock(spec=["system_manifest"])
        manifest.system_manifest = "not json"

        mock_blade = Mock()
        mock_blade.get_support_diagnostics.return_value = self._response([])
        mock_blade.get_support_diagnostics_settings.return_value = self._response([])
        mock_blade.get_support_system_manifest.return_value = self._response([manifest])

        result = generate_support_dict(mock_blade)

        assert result["diagnostics"] == {}
        assert result["diagnostics_settings"] == {}
        assert result["manifest"]["purity_version"] is None
        assert result["manifest"]["component_count"] is None

    @patch("plugins.modules.purefb_info.LooseVersion")
    @patch("plugins.modules.purefb_info.generate_support_dict")
    @patch("plugins.modules.purefb_info.generate_software_dict")
    @patch("plugins.modules.purefb_info.generate_default_dict")
    @patch("plugins.modules.purefb_info.get_system")
    @patch("plugins.modules.purefb_info.AnsibleModule")
    def test_main_software_and_support_subsets(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_generate_default,
        mock_generate_software,
        mock_generate_support,
        mock_loose_version,
    ):
        """gather_subset software/support wire the two generators."""
        mock_module = Mock()
        mock_module.params = {"gather_subset": ["software", "support"]}
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_get_system.return_value = mock_blade
        # version gates ON: main() gates the support subset on REST 2.16
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        mock_generate_software.return_value = {"packages": {}}
        mock_generate_support.return_value = {"manifest": {}}

        main()

        mock_generate_default.assert_not_called()
        mock_generate_software.assert_called_once()
        mock_generate_support.assert_called_once()
        info = mock_module.exit_json.call_args[1]["purefb_info"]
        assert info["software"] == {"packages": {}}
        assert info["support"] == {"manifest": {}}


# Realm read-back. The answers used below are the ones Purity//FB 4.8.8
# (REST 2.30) gives. To an administrator whose management access policy is
# scoped to one realm the array refuses the array-wide reads with HTTP 400
# "Operation not permitted.", fails GET /keytabs with HTTP 500 "Unexpected
# error." and serves every other read with the objects of that realm.

import re

import pytest

REFUSED_TO_A_REALM_ADMIN = (
    "get_admins_settings",
    "get_alert_watchers",
    "get_api_clients",
    "get_array_connections_path",
    "get_array_connections_performance_replication",
    "get_arrays_eula",
    "get_arrays_http_specific_performance",
    "get_arrays_nfs_specific_performance",
    "get_arrays_performance",
    "get_arrays_performance_replication",
    "get_arrays_s3_specific_performance",
    "get_arrays_space",
    "get_blades",
    "get_buckets_performance",
    "get_buckets_s3_specific_performance",
    "get_directory_services_roles",
    "get_drives",
    "get_file_systems_locks",
    "get_file_systems_locks_clients",
    "get_file_systems_open_files",
    "get_file_systems_performance",
    "get_file_systems_sessions",
    "get_fleets",
    "get_fleets_members",
    "get_hardware",
    "get_kmip",
    "get_link_aggregation_groups",
    "get_management_access_policies",
    "get_management_access_policies_members",
    "get_management_access_policies_roles",
    "get_management_authentication_policies",
    "get_management_authentication_policies_members",
    "get_network_access_policies",
    "get_network_interfaces_connectors",
    "get_network_interfaces_connectors_performance",
    "get_network_interfaces_connectors_settings",
    "get_network_interfaces_neighbors",
    "get_network_interfaces_network_connection_statistics",
    "get_presets_workload",
    "get_public_keys",
    "get_public_keys_uses",
    "get_quotas_settings",
    "get_rapid_data_locking",
    "get_remote_arrays",
    "get_resource_accesses",
    "get_smtp_servers",
    "get_snmp_agents",
    "get_snmp_managers",
    "get_software",
    "get_software_bundle",
    "get_software_check",
    "get_software_installation_steps",
    "get_software_installations",
    "get_software_patches",
    "get_software_versions",
    "get_ssh_certificate_authority_policies",
    "get_ssh_certificate_authority_policies_members",
    "get_storage_classes_members",
    "get_support",
    "get_support_diagnostics",
    "get_support_diagnostics_settings",
    "get_support_system_manifest",
    "get_support_verification_keys",
    "get_syslog_servers",
    "get_syslog_servers_settings",
    "get_targets_performance_replication",
    "get_telemetry_metrics_collections",
    "get_telemetry_metrics_collections_metrics",
    "get_telemetry_metrics_policies",
    "get_telemetry_metrics_policies_arrays",
    "get_telemetry_targets",
    "get_topology_groups",
    "get_topology_groups_members",
    "get_workloads",
    "get_workloads_performance",
    "get_workloads_tags",
)

# every subset but clients, whose reads were not probed as a realm identity
SUBSETS_FOR_A_REALM_ADMIN = (
    "all",
    "minimum",
    "config",
    "performance",
    "capacity",
    "network",
    "subnets",
    "lags",
    "filesystems",
    "snapshots",
    "buckets",
    "arrays",
    "replication",
    "policies",
    "accounts",
    "admins",
    "ad",
    "kerberos",
    "drives",
    "servers",
    "fleet",
    "realms",
    "locks",
    "support",
    "legal_holds",
    "connections",
    "telemetry",
    "software",
)

REALM_ID = "11111111-1111-4111-8111-111111111111"
ARRAY_ID = "22222222-2222-4222-8222-222222222222"
OTHER_ID = "33333333-3333-4333-8333-333333333333"


class _SdkError(object):
    """The SDK's ErrorResponse: a status code, errors and headers, no items"""

    def __init__(self, status_code, message):
        self.status_code = status_code
        self.errors = [_Row(message=message, context=None)]
        self.headers = None


def _refused():
    return _SdkError(400, "Operation not permitted.")


def _listing(items=()):
    items = list(items)
    return _Row(status_code=200, items=items, total_item_count=len(items), headers=None)


def _ref(name, ref_id=None, resource_type=None):
    return _Row(name=name, id=ref_id, resource_type=resource_type)


def _fake_client(reads):
    """A client whose reads are methods of its class, as on the SDK client

    ``reads`` maps a method name to the response it gives, or to a callable
    that is handed the keyword arguments of the call. ``calls`` records
    every read made.
    """
    calls = []

    def method(name, answer):
        def read(self, *args, **kwargs):
            calls.append((name, kwargs))
            return answer(**kwargs) if callable(answer) else answer

        return read

    namespace = {name: method(name, answer) for name, answer in reads.items()}
    client = type("FakeClient", (object,), namespace)()
    client.calls = calls
    return client


def _module_reads():
    """Every GET the module makes, taken from its source"""
    with open(purefb_info_module.__file__) as source:
        return sorted(set(re.findall(r"blade\.(get_[a-z_0-9]+)", source.read())))


def _realm_admin_client(**overrides):
    """The array as an administrator scoped to realm realm1 reads it"""
    reads = {}
    for name in _module_reads():
        reads[name] = _refused() if name in REFUSED_TO_A_REALM_ADMIN else _listing()
    reads["get_hardware"] = _refused()
    reads["get_keytabs"] = _SdkError(500, "Unexpected error.")
    # the array leaves the array-wide settings out of what it reports about
    # itself; a field it left out reads as None on the SDK model
    reads["get_arrays"] = _listing(
        [
            _Row(
                name="fb1",
                version="4.8.8",
                os="Purity//FB",
                banner="",
                idle_timeout=1800000,
                time_zone="UTC",
                product_type="FlashBlade//S200",
                encryption=None,
                network_access_policy=None,
                ntp_servers=None,
                smb_mode=None,
                security_update=None,
            )
        ]
    )
    reads["get_realms"] = _listing(
        [_Row(name="realm1", created=1735689600000, destroyed=False)]
    )
    reads.update(overrides)
    return _fake_client(reads)


def _run_main(client, subset, version="2.30"):
    """Run main() for one subset; returns the module and the gathered info"""
    module = Mock()
    module.params = {"gather_subset": [subset]}
    module.check_mode = False
    with patch.multiple(
        purefb_info_module,
        AnsibleModule=Mock(return_value=module),
        get_system=Mock(return_value=client),
        get_rest_api_version=Mock(return_value=version),
        LooseVersion=_Version,
    ):
        main()
    module.fail_json.assert_not_called()
    module.exit_json.assert_called_once()
    assert module.exit_json.call_args[1]["changed"] is False
    return module, module.exit_json.call_args[1]["purefb_info"]


def _space_row(capacity, unique):
    return _Row(
        capacity=capacity,
        space=_Row(
            data_reduction=1.5,
            snapshots=10,
            total_physical=unique + 10,
            unique=unique,
            virtual=2 * unique,
            total_provisioned=4 * unique,
            available_provisioned=3 * unique,
            available_ratio=0.75,
            destroyed=0,
            destroyed_virtual=0,
            shared=0,
        ),
    )


def _quota_rule(name, policy, uid):
    return _Row(
        name=name,
        policy=policy,
        quota_type="user",
        subject=_Row(id=uid, name="", sid=None),
        quota_limit=1073741824,
        enforced=True,
        notifications="none",
        index=1,
    )


class TestPurefbInfoRealmReadBack:
    """Read-back of realm objects, and as an identity scoped to a realm"""

    # (a) an identity the array refuses the array-wide reads

    @pytest.mark.parametrize("subset", SUBSETS_FOR_A_REALM_ADMIN)
    def test_each_subset_is_gathered_for_a_realm_admin(self, subset):
        """No subset ends in a traceback when the array refuses its reads."""
        info = _run_main(_realm_admin_client(), subset)[1]
        assert isinstance(info, dict)

    def test_realms_subset_survives_refused_resource_accesses(self):
        """The array refuses the resource accesses to a realm admin; the
        realm it may read is still reported."""
        info = _run_main(_realm_admin_client(), "realms")[1]
        assert info["resource_accesses"] == []
        assert list(info["realms"]) == ["realm1"]
        assert info["realm_connections"] == {}
        assert info["remote_realms"] == {}

    def test_minimum_subset_for_a_realm_admin(self):
        """Refused reads give null counts and empty entries; the reads the
        array serves are reported as usual."""
        module, info = _run_main(_realm_admin_client(), "minimum")
        default = info["default"]
        assert default["flashblade_name"] == "fb1"
        assert default["purity_version"] == "4.8.8"
        assert default["idle_timeout"] == 30
        assert default["filesystems"] == 0
        assert default["policies"] == 0
        for key in (
            "blades",
            "total_capacity",
            "syslog_servers",
            "api_clients",
            "EULA",
            "max_login_attempts",
            "min_password_length",
            "kerberos_keytabs",
        ):
            assert default[key] is None, key
        assert "lockout_duration" not in default
        assert default["support_keys"] == {}
        assert default["remote_assist"] == {}
        assert default["encryption"] == {
            "data_at_rest_enabled": None,
            "data_at_rest_algorithms": None,
            "data_at_rest_entropy_source": None,
        }
        assert default["network_access_policy"] == "None"
        # the keytab read is a server error, not a refusal: it is reported
        module.warn.assert_called_once()
        assert "keytabs" in module.warn.call_args[0][0]
        assert "Unexpected error." in module.warn.call_args[0][0]

    def test_array_wide_subsets_are_empty_for_a_realm_admin(self):
        client = _realm_admin_client()
        assert _run_main(client, "capacity")[1]["capacity"] == {}
        assert _run_main(client, "drives")[1]["drives"] == {}
        assert _run_main(client, "kerberos")[1]["kerberos"] == {}
        perf = _run_main(client, "performance")[1]["performance"]
        for key in ("aggregate", "http", "s3", "nfs", "smb", "nfs_ops"):
            assert perf[key] == {}, key
        assert "file_replication" not in perf
        telemetry = _run_main(client, "telemetry")[1]
        assert telemetry == {
            "telemetry_targets": {},
            "telemetry_policies": {},
            "telemetry_collections": {},
        }
        config = _run_main(client, "config")[1]["config"]
        assert config["smtp"] == {}
        assert config["alert_watchers"] == {}
        assert config["directory_service_roles"] == {}
        assert config["syslog_servers"] == {}
        assert config["snmp_agents"] == {}
        assert config["ntp"] is None
        # no directory service is visible, so neither is its alias
        assert "array_management" not in config
        assert "management_directory_service" not in config

    def test_keytab_failure_asks_once_whether_the_identity_is_restricted(self):
        client = _realm_admin_client()
        module = _run_main(client, "kerberos")[0]
        assert [name for name, _kwargs in client.calls] == [
            "get_keytabs",
            "get_hardware",
        ]
        module.warn.assert_called_once()

    def test_keytab_failure_is_not_hidden_from_an_array_admin(self):
        """The same server error on an identity the array serves its
        hardware to is left as the failure it is today."""
        failure = _SdkError(500, "Unexpected error.")
        client = _fake_client(
            {
                "get_keytabs": failure,
                "get_hardware": _listing([_Row(name="CH1")]),
            }
        )
        module = Mock()
        purefb_info_module._guard_reads(module, client)
        assert client.get_keytabs() is failure
        module.warn.assert_not_called()
        with pytest.raises(AttributeError):
            purefb_info_module.generate_kerb_dict(client)

    def test_guard_only_replaces_refused_reads(self):
        served = _listing([_Row(name="dns1")])
        not_enabled = _SdkError(400, "Congestion control is not enabled.")
        missing = _SdkError(400, "File system does not exist.")
        client = _fake_client(
            {
                "get_dns": served,
                "get_network_interfaces_connectors_settings": not_enabled,
                "get_file_systems": missing,
                "get_blades": _refused(),
                "get_access_token": "not-a-response",
            }
        )
        module = Mock()
        purefb_info_module._guard_reads(module, client)
        assert client.get_dns() is served
        assert client.get_network_interfaces_connectors_settings() is not_enabled
        assert client.get_file_systems(names=["fs1"]) is missing
        assert client.get_access_token() == "not-a-response"
        refused = client.get_blades()
        assert refused.status_code == 400
        assert refused.items == []
        assert refused.total_item_count is None
        assert [error.message for error in refused.errors] == [
            "Operation not permitted."
        ]
        assert client.calls[2] == ("get_file_systems", {"names": ["fs1"]})
        module.warn.assert_not_called()

    def test_capacity_for_an_array_admin_is_unchanged(self):
        def space(**kwargs):
            if kwargs.get("type") == "file-system":
                return _listing([_space_row(1000, 30)])
            if kwargs.get("type") == "object-store":
                return _listing([_space_row(1000, 20)])
            return _listing([_space_row(1000, 50)])

        client = _fake_client({"get_arrays_space": space})
        capacity = _run_main(client, "capacity")[1]["capacity"]
        assert sorted(capacity) == ["aggregate", "file-system", "object-store", "total"]
        assert capacity["total"] == 1000
        assert capacity["aggregate"]["unique"] == 50
        assert capacity["file-system"]["unique"] == 30
        assert capacity["object-store"]["unique"] == 20
        assert len(client.calls) == 3

    def test_performance_rows_keep_their_keys_for_an_array_admin(self):
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
            others_per_sec=11,
        )
        blade = Mock()
        blade.get_arrays_performance.return_value = _listing([sample])
        blade.get_array_connections_performance_replication.return_value = _listing()
        with patch.object(
            purefb_info_module, "generate_perf_breakdown_dict", return_value={}
        ):
            perf = generate_perf_dict(blade)
        for key in ("aggregate", "http", "s3", "nfs"):
            assert perf[key] == {
                "bytes_per_op": 1,
                "bytes_per_read": 2,
                "bytes_per_write": 3,
                "read_bytes_per_sec": 4,
                "reads_per_sec": 5,
                "usec_per_other_op": 6,
                "usec_per_read_op": 7,
                "usec_per_write_op": 8,
                "write_bytes_per_sec": 9,
                "writes_per_sec": 10,
            }

    # (b) junctions

    def test_junction_in_a_realm_reports_realm_file_systems(self):
        """The array names the file systems of a junction bare; a realm
        junction and an array-level one on file systems of the same name
        must not read the same."""

        def junction(name, origin_id, destination_id):
            return _Row(
                name=name,
                origin_file_system=_ref("projects", origin_id, "file-systems"),
                destination_file_system=_ref("alpha", destination_id, "file-systems"),
                junction_origin_path="/alpha",
                status="CONNECTED",
            )

        blade = Mock()
        blade.get_file_system_junctions.return_value = _listing(
            [
                junction("realm1::projects-alpha", REALM_ID, OTHER_ID),
                junction("projects-alpha", ARRAY_ID, OTHER_ID),
            ]
        )

        result = generate_fs_junctions_dict(blade)

        assert result["realm1::projects-alpha"] == {
            "origin": "realm1::projects",
            "destination": "realm1::alpha",
            "path": "/alpha",
            "status": "CONNECTED",
        }
        assert result["projects-alpha"] == {
            "origin": "projects",
            "destination": "alpha",
            "path": "/alpha",
            "status": "CONNECTED",
        }

    def test_realm_qualified(self):
        qualify = purefb_info_module._realm_qualified
        assert qualify("fs1", "realm1::junction") == "realm1::fs1"
        assert qualify("realm1::fs1", "realm1::junction") == "realm1::fs1"
        assert qualify("fs1", "junction") == "fs1"
        assert qualify(None, "realm1::junction") is None
        assert qualify("fs1", None) == "fs1"

    # (c) quota policies

    @staticmethod
    def _quota_policy(name, policy_id, realm=None):
        return _Row(
            name=name,
            id=policy_id,
            is_local=True,
            enabled=True,
            location=_ref("fb1"),
            realms=[_ref(realm, resource_type="realms")] if realm else [],
        )

    def test_quota_rules_stay_with_their_policy_after_a_bare_rename(self):
        """After a bare rename the array names the rule of a realm policy,
        and the policy it refers to, without the realm. An array-level
        policy of that name keeps its own rule only."""
        blade = Mock()
        blade.get_user_group_quota_policies.return_value = _listing(
            [
                self._quota_policy("realm1::gold", REALM_ID, "realm1"),
                self._quota_policy("gold", ARRAY_ID),
            ]
        )
        blade.get_user_group_quota_policies_rules.return_value = _listing(
            [
                _quota_rule("gold.1", _ref("gold", REALM_ID), 1001),
                _quota_rule("gold.1", _ref("gold", ARRAY_ID), 3003),
            ]
        )
        blade.get_user_group_quota_policies_members.return_value = _listing()

        result = generate_quota_policies_dict(blade)

        assert [rule["subject"]["id"] for rule in result["realm1::gold"]["rules"]] == [
            1001
        ]
        assert [rule["subject"]["id"] for rule in result["gold"]["rules"]] == [3003]
        assert result["realm1::gold"]["realms"] == ["realm1"]
        assert result["gold"]["realms"] == []

    def test_quota_members_stay_with_their_policy(self):
        """The array can list the attachment of a realm policy under bare
        names. It belongs to the realm policy and to the realm file system,
        not to the array-level policy of the same name."""
        blade = Mock()
        blade.get_user_group_quota_policies.return_value = _listing(
            [
                self._quota_policy("realm1::gold", REALM_ID, "realm1"),
                self._quota_policy("gold", ARRAY_ID),
            ]
        )
        blade.get_user_group_quota_policies_rules.return_value = _listing()
        blade.get_user_group_quota_policies_members.return_value = _listing(
            [_Row(policy=_ref("gold", REALM_ID), member=_ref("fs1", OTHER_ID))]
        )

        result = generate_quota_policies_dict(blade)

        assert result["realm1::gold"]["members"] == ["realm1::fs1"]
        assert result["gold"]["members"] == []

    def test_quota_policy_rows_matched_by_id_for_array_level_policies(self):
        """Array-level policies read the same whether their rows are matched
        by id or by name; a row of an unlisted policy is dropped."""
        blade = Mock()
        blade.get_user_group_quota_policies.return_value = _listing(
            [self._quota_policy("gold", ARRAY_ID)]
        )
        blade.get_user_group_quota_policies_rules.return_value = _listing(
            [
                _quota_rule("gold.1", _ref("gold", ARRAY_ID), 3003),
                _quota_rule("other.1", _ref("other", OTHER_ID), 4004),
            ]
        )
        blade.get_user_group_quota_policies_members.return_value = _listing(
            [
                _Row(policy=_ref("gold", ARRAY_ID), member=_ref("fs1")),
                _Row(policy=_ref("other", OTHER_ID), member=_ref("fs2")),
            ]
        )

        result = generate_quota_policies_dict(blade)

        assert list(result) == ["gold"]
        assert [rule["name"] for rule in result["gold"]["rules"]] == ["gold.1"]
        assert result["gold"]["members"] == ["fs1"]

    def test_policy_name_of(self):
        name_of = purefb_info_module._policy_name_of
        names = {REALM_ID: "realm1::gold", ARRAY_ID: "gold"}
        assert name_of(_ref("gold", REALM_ID), names) == "realm1::gold"
        assert name_of(_ref("gold", ARRAY_ID), names) == "gold"
        # a row of a policy that is not listed is not attributed by name
        assert name_of(_ref("gold", OTHER_ID), names) is None
        # rows or listings without ids fall back to the exact name
        assert name_of(_ref("gold"), names) == "gold"
        assert name_of(_ref("gold", REALM_ID), {}) == "gold"
        assert name_of(None, names) is None

    # (d) realms of the policies

    def test_eviction_policies_report_realms_and_keep_their_members(self):
        blade = Mock()
        blade.get_data_eviction_policies.return_value = _listing(
            [
                _Row(
                    name="realm1::cache",
                    id=REALM_ID,
                    is_local=True,
                    enabled=True,
                    keep_size=1073741824,
                    realms=[_ref("realm1", resource_type="realms")],
                ),
                _Row(
                    name="cache",
                    id=ARRAY_ID,
                    is_local=True,
                    enabled=True,
                    keep_size=2147483648,
                    realms=[],
                ),
            ]
        )
        blade.get_data_eviction_policies_file_systems.return_value = _listing(
            [
                _Row(policy=_ref("cache", REALM_ID), member=_ref("fs1")),
                _Row(policy=_ref("cache", ARRAY_ID), member=_ref("fs2")),
            ]
        )

        result = purefb_info_module.generate_eviction_policies_dict(blade)

        assert result == {
            "realm1::cache": {
                "local": True,
                "enabled": True,
                "keep_size": 1073741824,
                "realms": ["realm1"],
                "file_systems": ["realm1::fs1"],
            },
            "cache": {
                "local": True,
                "enabled": True,
                "keep_size": 2147483648,
                "realms": [],
                "file_systems": ["fs2"],
            },
        }

    @pytest.mark.parametrize(
        "generator, read",
        [
            ("generate_policies_dict", "get_policies"),
            ("generate_all_policies_dict", "get_policies_all"),
            (
                "generate_object_store_access_policies_dict",
                "get_object_store_access_policies",
            ),
            ("generate_nfs_export_policies_dict", "get_nfs_export_policies"),
            ("generate_smb_client_policies_dict", "get_smb_client_policies"),
            ("generate_smb_share_policies_dict", "get_smb_share_policies"),
            ("generate_network_access_policies_dict", "get_network_access_policies"),
            ("generate_worm_data_policies_dict", "get_worm_data_policies"),
            ("generate_tls_policies_dict", "get_tls_policies"),
            (
                "generate_ssh_ca_policies_dict",
                "get_ssh_certificate_authority_policies",
            ),
            ("generate_s3_export_policies_dict", "get_s3_export_policies"),
            ("generate_password_policies_dict", "get_password_policies"),
        ],
    )
    def test_policy_entries_report_their_realms(self, generator, read):
        def policy(name, policy_id, realms):
            row = MagicMock()
            row.name = name
            row.id = policy_id
            row.rules = []
            row.realms = realms
            return row

        blade = MagicMock()
        getattr(blade, read).return_value.items = [
            policy("realm1::gold", REALM_ID, [_ref("realm1", resource_type="realms")]),
            policy("gold", ARRAY_ID, []),
        ]
        with patch.multiple(
            purefb_info_module,
            get_rest_api_version=Mock(return_value="2.30"),
            LooseVersion=_Version,
        ):
            result = getattr(purefb_info_module, generator)(blade)

        assert result["realm1::gold"]["realms"] == ["realm1"]
        assert result["gold"]["realms"] == []

    def test_bucket_policies_report_their_realms(self):
        policy = MagicMock()
        policy.name = "realm1::acct/bucket1/policy"
        policy.rules = []
        policy.realms = [_ref("realm1", resource_type="realms")]
        blade = MagicMock()
        blade.get_buckets.return_value.items = [_Row(name="realm1::acct/bucket1")]
        blade.get_buckets_bucket_access_policies.return_value = Mock(
            status_code=200, total_item_count=1, items=[policy]
        )
        blade.get_buckets_cross_origin_resource_sharing_policies.return_value = Mock(
            status_code=200, items=[policy]
        )

        access = generate_bucket_access_policies_dict(blade)
        cors = generate_bucket_cross_object_policies_dict(blade)

        assert access["realm1::acct/bucket1/policy"]["realms"] == ["realm1"]
        assert cors["realm1::acct/bucket1/policy"]["realms"] == ["realm1"]

    def test_realm_names(self):
        names = purefb_info_module._realm_names
        assert names(_Row(realms=[_ref("realm1"), {"name": "realm2"}])) == [
            "realm1",
            "realm2",
        ]
        assert names(_Row(realms=[])) == []
        assert names(_Row(realms=None)) == []
        assert names(_Row()) == []

    # (e) realm connection keys

    def test_realm_connection_keys_report_times_never_the_key(self):
        def keys(realm_names=None):
            if realm_names == ["realm1"]:
                return _listing(
                    [
                        _Row(
                            connection_key="****",
                            created=1735689600000,
                            expires=1735696800000,
                            realm=_ref("realm1", resource_type="realms"),
                        ),
                        _Row(
                            connection_key="****",
                            created=1735690000000,
                            expires=1735697200000,
                            realm=_ref("realm1", resource_type="realms"),
                        ),
                    ]
                )
            if realm_names == ["realm2"]:
                return _listing()
            return _SdkError(400, "Realm has been destroyed.")

        client = _fake_client({"get_realm_connections_connection_key": keys})

        result = purefb_info_module.generate_realm_connection_keys_dict(
            client, {"realm1": {}, "realm2": {}, "realm3": {}}
        )

        assert result == {
            "realm1": [
                {"created": 1735689600000, "expires": 1735696800000},
                {"created": 1735690000000, "expires": 1735697200000},
            ],
            "realm2": [],
        }
        assert "****" not in repr(result)
        assert "connection_key" not in repr(result)
        assert client.calls == [
            ("get_realm_connections_connection_key", {"realm_names": [name]})
            for name in ("realm1", "realm2", "realm3")
        ]

    def test_realms_subset_lists_connection_keys_from_rest_2_25(self):
        key = _Row(
            connection_key="****",
            created=1735689600000,
            expires=1735696800000,
            realm=_ref("realm1", resource_type="realms"),
        )
        client = _realm_admin_client(
            get_realm_connections_connection_key=_listing([key])
        )

        info = _run_main(client, "realms")[1]

        assert info["realm_connection_keys"] == {
            "realm1": [{"created": 1735689600000, "expires": 1735696800000}]
        }
        assert (
            "get_realm_connections_connection_key",
            {"realm_names": ["realm1"]},
        ) in client.calls

        older = _realm_admin_client(
            get_realm_connections_connection_key=_listing([key])
        )
        info = _run_main(older, "realms", version="2.24")[1]
        assert "realm_connection_keys" not in info
        assert "realm_connections" not in info
        assert not [call for call in older.calls if "connection_key" in call[0]]


# Read-back for an identity whose custom role grants one resource type. For
# a role with "file-systems: get" on the array Purity//FB 4.8.8 serves GET
# /file-systems and refuses GET /arrays, /hardware, /admins and /audits with
# HTTP 400 "Operation not permitted. Authorization for 'get' on
# 'purestorage.com/api/v2/<endpoint>' is required.". The other reads were not
# probed for such an identity; they are modelled as refused in the same way.


def _refused_for_role(read):
    return _SdkError(
        400,
        "Operation not permitted. Authorization for 'get' on "
        "'purestorage.com/api/v2/{0}' is required.".format(read[4:].replace("_", "-")),
    )


def _file_system_row(name):
    return _Row(
        name=name,
        id="44444444-4444-4444-8444-444444444444",
        fast_remove_directory_enabled=False,
        snapshot_directory_enabled=False,
        provisioned=1073741824,
        destroyed=False,
        http=_Row(enabled=False),
        hard_limit_enabled=False,
        promotion_status="promoted",
        requested_promotion_state="promoted",
        writable=True,
        default_group_quota=0,
        default_user_quota=0,
    )


def _custom_role_client(**overrides):
    """The array as an identity that may only read file systems reads it"""
    reads = {name: _refused_for_role(name) for name in _module_reads()}
    reads["get_hardware"] = _refused_for_role("get_hardware")
    reads["get_file_systems"] = _listing([_file_system_row("fs1")])
    reads.update(overrides)
    return _fake_client(reads)


class TestPurefbInfoRefusedReads:
    """No refused read ends in a traceback, the array record included"""

    @pytest.mark.parametrize("subset", SUBSETS_FOR_A_REALM_ADMIN + ("clients",))
    def test_each_subset_is_gathered_with_a_custom_role(self, subset):
        module, info = _run_main(_custom_role_client(), subset)
        assert isinstance(info, dict)
        # every read is refused, none fails: nothing to warn about
        module.warn.assert_not_called()

    @pytest.mark.parametrize("subset", SUBSETS_FOR_A_REALM_ADMIN + ("clients",))
    def test_each_subset_is_gathered_when_every_read_is_refused(self, subset):
        client = _custom_role_client(
            get_file_systems=_refused_for_role("get_file_systems")
        )
        info = _run_main(client, subset)[1]
        assert isinstance(info, dict)

    def test_minimum_subset_without_the_array_record(self):
        """GET /arrays is refused: the entries read from the array record
        are null and the read the role grants is still counted."""
        default = _run_main(_custom_role_client(), "minimum")[1]["default"]
        assert default["filesystems"] == 1
        for key in (
            "flashblade_name",
            "purity_version",
            "banner",
            "idle_timeout",
            "timezone",
            "smb_mode",
            "security_update",
            "blades",
            "policies",
            "kerberos_keytabs",
            "total_capacity",
        ):
            assert default[key] is None, key
        assert default["product_type"] == "Unknown"
        assert default["network_access_policy"] == "None"
        assert default["api_versions"] == "2.30"
        assert default["remote_assist"] == {}
        assert default["maintenance_window"] == []

    def test_file_systems_are_reported_with_a_custom_role(self):
        """The per-file-system reads the role does not grant leave their
        entries empty."""
        info = _run_main(_custom_role_client(), "filesystems")[1]
        assert list(info["filesystems"]) == ["fs1"]
        fsys = info["filesystems"]["fs1"]
        assert fsys["provisioned"] == 1073741824
        assert fsys["user_quotas"] == {}
        assert fsys["group_quotas"] == {}
        assert fsys["quota_policy"] is None
        assert fsys["policy_quotas"] == {"users": [], "groups": []}
        assert fsys["worm_policy"] is None
        assert info["file_system_exports"] == []
        assert info["junctions"] == {}

    def test_config_and_drives_without_the_array_record(self):
        client = _custom_role_client()
        config = _run_main(client, "config")[1]["config"]
        assert config["ntp"] is None
        assert config["dns"] == {}
        assert config["ssl_certs"] == {}
        assert _run_main(client, "drives")[1]["drives"] == {}

    def test_refusal_is_recognised_with_and_without_its_detail(self):
        refused = purefb_info_module._read_refused
        assert refused(_refused())
        assert refused(_refused_for_role("get_arrays"))
        assert not refused(_SdkError(400, "File system does not exist."))
        assert not refused(_SdkError(500, "Unexpected error."))
        assert not refused(_listing())
        # one error of a response that is not a refusal keeps it a failure
        mixed = _refused()
        mixed.errors.append(_Row(message="Unexpected error.", context=None))
        assert not refused(mixed)


# Attachments of a policy to a file system in a realm, as Purity//FB 4.8.8
# lists them: GET /worm-data-policies/members and GET
# /file-systems/worm-data-policies name the file system of a realm policy
# bare ("fs1" under policy "realm1::keep"), with the id of the realm file
# system. An array-level file system of the same name has its own row.

FS_REALM_ID = "55555555-5555-4555-8555-555555555555"
FS_ARRAY_ID = "66666666-6666-4666-8666-666666666666"


def _array_admin_client(**overrides):
    """An array every read of which is served, empty unless overridden"""
    reads = {name: _listing() for name in _module_reads()}
    reads.update(overrides)
    return _fake_client(reads)


def _file_system_with_id(name, fs_id):
    row = _file_system_row(name)
    row.id = fs_id
    return row


def _worm_policy_row(name, policy_id, realm=None):
    return _Row(
        name=name,
        id=policy_id,
        is_local=True,
        enabled=True,
        mode="compliance",
        retention_lock="unlocked",
        default_retention=3600000,
        min_retention=60000,
        max_retention=86400000,
        policy_type="worm",
        location=_ref("fb1"),
        realms=[_ref(realm, resource_type="realms")] if realm else [],
    )


def _worm_attachment_rows():
    return [
        _Row(
            policy=_ref("realm1::keep", REALM_ID, "worm-data-policies"),
            member=_ref("fs1", FS_REALM_ID, "file-systems"),
        ),
        _Row(
            policy=_ref("keep", ARRAY_ID, "worm-data-policies"),
            member=_ref("fs1", FS_ARRAY_ID, "file-systems"),
        ),
    ]


def _worm_policy_rows():
    return [
        _worm_policy_row("realm1::keep", REALM_ID, "realm1"),
        _worm_policy_row("keep", ARRAY_ID),
    ]


class TestPurefbInfoRealmAttachments:
    """A file system in a realm and an array-level one of the same name
    each report their own policy, and each policy its own file system"""

    def _worm_policies(self, rows):
        blade = Mock()
        blade.get_worm_data_policies.return_value = _listing(_worm_policy_rows())
        blade.get_worm_data_policies_members.return_value = _listing(rows)
        with patch.multiple(
            purefb_info_module,
            get_rest_api_version=Mock(return_value="2.30"),
            LooseVersion=_Version,
        ):
            return generate_worm_data_policies_dict(blade)

    def test_worm_policy_in_a_realm_lists_realm_file_systems(self):
        result = self._worm_policies(_worm_attachment_rows())

        assert result["realm1::keep"]["members"] == ["realm1::fs1"]
        assert result["realm1::keep"]["realms"] == ["realm1"]
        assert result["keep"]["members"] == ["fs1"]
        assert result["keep"]["realms"] == []

    def test_worm_members_are_matched_by_policy_id(self):
        """A row that names the policy of a realm bare belongs to the realm
        policy, not to the array-level policy of that name; a row of a
        policy that is not listed is dropped."""
        result = self._worm_policies(
            [
                _Row(policy=_ref("keep", REALM_ID), member=_ref("fs1", FS_REALM_ID)),
                _Row(policy=_ref("keep", OTHER_ID), member=_ref("fs2")),
            ]
        )

        assert result["realm1::keep"]["members"] == ["realm1::fs1"]
        assert result["keep"]["members"] == []

    def test_fs_worm_policies_are_keyed_by_file_system_id(self):
        blade = Mock()
        blade.get_file_systems_worm_data_policies.return_value = _listing(
            _worm_attachment_rows()
        )

        assert generate_fs_worm_policies_dict(blade) == {
            FS_REALM_ID: "realm1::keep",
            FS_ARRAY_ID: "keep",
        }

    def test_file_systems_report_their_own_worm_policy(self):
        """main(), filesystems subset: the bare name the array lists must
        not hand the realm policy to the array-level file system."""
        client = _array_admin_client(
            get_file_systems=_listing(
                [
                    _file_system_with_id("realm1::fs1", FS_REALM_ID),
                    _file_system_with_id("fs1", FS_ARRAY_ID),
                    _file_system_with_id("fs2", OTHER_ID),
                ]
            ),
            get_file_systems_worm_data_policies=_listing(_worm_attachment_rows()),
        )

        filesystems = _run_main(client, "filesystems")[1]["filesystems"]

        assert filesystems["realm1::fs1"]["worm_policy"] == "realm1::keep"
        assert filesystems["fs1"]["worm_policy"] == "keep"
        assert filesystems["fs2"]["worm_policy"] is None

    def test_file_systems_report_their_own_quota_policy(self):
        """The array can list the attachment of a realm quota policy under
        bare names. It belongs to the realm file system and names the realm
        policy; the array-level file system of that name has none."""
        client = _array_admin_client(
            get_file_systems=_listing(
                [
                    _file_system_with_id("realm1::fs1", FS_REALM_ID),
                    _file_system_with_id("fs1", FS_ARRAY_ID),
                    _file_system_with_id("realm1::fs2", OTHER_ID),
                ]
            ),
            get_file_systems_user_group_quota_policies=_listing(
                [
                    _Row(
                        policy=_ref("gold", REALM_ID),
                        member=_ref("fs1", FS_REALM_ID),
                    ),
                    _Row(
                        policy=_ref("realm1::silver", ARRAY_ID),
                        member=_ref("realm1::fs2", OTHER_ID),
                    ),
                ]
            ),
        )

        filesystems = _run_main(client, "filesystems")[1]["filesystems"]

        assert filesystems["realm1::fs1"]["quota_policy"] == "realm1::gold"
        assert filesystems["fs1"]["quota_policy"] is None
        assert filesystems["realm1::fs2"]["quota_policy"] == "realm1::silver"

    def test_policies_subset_qualifies_file_systems_of_a_realm_worm_policy(self):
        """main(), policies subset: worm_data_policies and the members of
        the policies view name the realm file system."""
        client = _array_admin_client(
            get_worm_data_policies=_listing(_worm_policy_rows()),
            get_worm_data_policies_members=_listing(_worm_attachment_rows()),
            get_policies_all=_listing(_worm_policy_rows()),
            get_policies_all_members=_listing(_worm_attachment_rows()),
        )

        info = _run_main(client, "policies")[1]

        assert info["worm_data_policies"]["realm1::keep"]["members"] == ["realm1::fs1"]
        assert info["worm_data_policies"]["keep"]["members"] == ["fs1"]
        assert info["policies"]["realm1::keep"]["members"] == [
            {"name": "realm1::fs1", "resource_type": "file-systems"}
        ]
        assert info["policies"]["keep"]["members"] == [
            {"name": "fs1", "resource_type": "file-systems"}
        ]

    def test_policies_view_qualifies_file_system_members_only(self):
        policies = [_worm_policy_row("realm1::keep", REALM_ID, "realm1")]
        blade = Mock()
        blade.get_policies_all_members.return_value = _listing(
            [
                _Row(
                    policy=_ref("realm1::keep", REALM_ID),
                    member=_ref("realm1::fs2", OTHER_ID, "file-systems"),
                ),
                _Row(
                    policy=_ref("realm1::keep", REALM_ID),
                    member=_ref("realm1", None, "realms"),
                ),
                _Row(
                    policy=_ref("realm1::keep", REALM_ID),
                    member=_ref("eth0", None, "network-interfaces"),
                ),
            ]
        )

        members = purefb_info_module._policy_members_by_name(blade, policies)

        assert members == {
            "realm1::keep": [
                {"name": "realm1::fs2", "resource_type": "file-systems"},
                {"name": "realm1", "resource_type": "realms"},
                {"name": "eth0", "resource_type": "network-interfaces"},
            ]
        }

    def test_attached_policy(self):
        attached = purefb_info_module._attached_policy
        realm_fs = _file_system_with_id("realm1::fs1", FS_REALM_ID)
        array_fs = _file_system_with_id("fs1", FS_ARRAY_ID)
        by_id = {FS_REALM_ID: "realm1::keep", FS_ARRAY_ID: "keep"}
        assert attached(by_id, realm_fs) == "realm1::keep"
        assert attached(by_id, array_fs) == "keep"
        # the policy of a file system in a realm is in that realm
        assert attached({FS_REALM_ID: "keep"}, realm_fs) == "realm1::keep"
        # a map keyed by name is read by name, and a bare name is not the
        # file system in the realm
        assert attached({"fs1": "keep"}, array_fs) == "keep"
        assert attached({"fs1": "keep"}, realm_fs) is None
        assert attached({"realm1::fs1": "realm1::keep"}, realm_fs) == "realm1::keep"
        assert attached({}, array_fs) is None
        # a file system the SDK returns without an id is read by name
        assert attached({"fs1": "keep"}, _Row(name="fs1")) == "keep"

    def test_attachment_key(self):
        key = purefb_info_module._attachment_key
        assert key(_ref("fs1", FS_REALM_ID)) == FS_REALM_ID
        assert key(_ref("fs1")) == "fs1"
        assert key(_ref("fs1", "")) == "fs1"
        assert key(None) is None


# GET /policies-all/members on Purity//FB 4.8.8: the listing of every policy
# at once is refused (HTTP 400) once the array holds more than about ten
# object store users with an access policy; a query that names at most ten
# policies is served.

MEMBERS_QUERY_REFUSED = (
    "Querying is only supported for a maximum of ten users or ten policies per query."
)


def _policy_id(index):
    return "00000000-0000-4000-8000-{0:012d}".format(index)


def _listed_policy(index):
    return _Row(
        name="policy{0}".format(index),
        id=_policy_id(index),
        enabled=True,
        is_local=True,
        location=_ref("fb1"),
        policy_type="object-store-access",
        realms=[],
    )


def _member_of(index):
    return _Row(
        policy=_ref("policy{0}".format(index), _policy_id(index)),
        member=_ref("acc/user{0}".format(index), None, "object-store-users"),
    )


def _members_served_ten_at_a_time(gone=(), broken=()):
    """GET policies-all/members as the array answers it with many users"""

    def read(policy_ids=None, **kwargs):
        if policy_ids is None or len(policy_ids) > 10:
            return _SdkError(400, MEMBERS_QUERY_REFUSED)
        if any(policy_id in broken for policy_id in policy_ids):
            return _SdkError(500, "Unexpected error.")
        if any(policy_id in gone for policy_id in policy_ids):
            return _SdkError(400, "Policy does not exist.")
        return _listing(
            [
                _member_of(index)
                for index in range(1, 24)
                if _policy_id(index) in policy_ids
            ]
        )

    return read


class TestPurefbInfoPolicyMembers:
    """The members of the policies view when the array refuses to list the
    members of every policy in one query"""

    POLICIES = [_listed_policy(index) for index in range(1, 24)]

    def _client(self, **kwargs):
        return _array_admin_client(
            get_policies_all=_listing(self.POLICIES),
            get_policies_all_members=_members_served_ten_at_a_time(**kwargs),
        )

    @staticmethod
    def _member_queries(client):
        return [
            call[1].get("policy_ids")
            for call in client.calls
            if call[0] == "get_policies_all_members"
        ]

    def test_members_are_read_ten_policies_at_a_time(self):
        """main(), policies subset: no traceback, every policy keeps its
        member, and no query names more than ten policies."""
        client = self._client()

        info = _run_main(client, "policies")[1]

        assert len(info["policies"]) == 23
        for index in range(1, 24):
            assert info["policies"]["policy{0}".format(index)]["members"] == [
                {
                    "name": "acc/user{0}".format(index),
                    "resource_type": "object-store-users",
                }
            ]
        ids = [policy.id for policy in self.POLICIES]
        assert self._member_queries(client) == [None, ids[:10], ids[10:20], ids[20:]]

    def test_all_subset_is_gathered_when_the_full_listing_is_refused(self):
        info = _run_main(self._client(), "all")[1]

        assert info["policies"]["policy23"]["members"][0]["name"] == "acc/user23"

    def test_one_query_when_the_array_serves_the_full_listing(self):
        client = _array_admin_client(
            get_policies_all=_listing(self.POLICIES),
            get_policies_all_members=_listing([_member_of(1), _member_of(23)]),
        )

        info = _run_main(client, "policies")[1]

        assert info["policies"]["policy1"]["members"][0]["name"] == "acc/user1"
        assert info["policies"]["policy2"]["members"] == []
        assert self._member_queries(client) == [None]

    def test_policy_removed_while_reading_is_skipped(self):
        """A policy deleted after it was listed fails the query of its ten;
        the others of that query are read one by one."""
        client = self._client(gone=(_policy_id(12),))

        info = _run_main(client, "policies")[1]

        assert info["policies"]["policy12"]["members"] == []
        for index in (1, 10, 11, 13, 20, 21, 23):
            assert info["policies"]["policy{0}".format(index)]["members"] == [
                {
                    "name": "acc/user{0}".format(index),
                    "resource_type": "object-store-users",
                }
            ]
        ids = [policy.id for policy in self.POLICIES]
        assert self._member_queries(client) == (
            [None, ids[:10], ids[10:20]] + [[one] for one in ids[10:20]] + [ids[20:]]
        )

    def test_another_failure_is_not_taken_for_an_empty_listing(self):
        """A query the array fails for another reason is not read as a
        policy without members."""
        blade = Mock()
        blade.get_policies_all_members.side_effect = _members_served_ten_at_a_time(
            broken=(_policy_id(5),)
        )

        with pytest.raises(AttributeError):
            purefb_info_module._policy_members_by_name(blade, self.POLICIES)
        # raised by the query that names the failing policy alone
        assert blade.get_policies_all_members.call_args[1] == {
            "policy_ids": [_policy_id(5)]
        }

    def test_refused_identity_makes_one_query(self):
        """An identity the array refuses the read gets no members and is
        not asked again policy by policy."""
        client = _realm_admin_client(
            get_policies_all=_listing(self.POLICIES),
            get_policies_all_members=_refused(),
        )

        info = _run_main(client, "policies")[1]

        assert info["policies"]["policy1"]["members"] == []
        assert self._member_queries(client) == [None]

    def test_refusals_are_told_apart(self):
        too_wide = purefb_info_module._query_too_wide
        gone = purefb_info_module._named_object_gone
        assert too_wide(_SdkError(400, MEMBERS_QUERY_REFUSED))
        assert not too_wide(_refused())
        assert not too_wide(_SdkError(400, "Policy does not exist."))
        assert not too_wide(_SdkError(500, "Unexpected error."))
        assert not too_wide(_listing())
        assert gone(_SdkError(400, "Policy does not exist."))
        assert gone(_SdkError(400, "Member does not exist."))
        assert not gone(_SdkError(400, MEMBERS_QUERY_REFUSED))
        assert not gone(_SdkError(500, "Unexpected error."))
        assert not gone(_listing())

    # roles: GET /object-store-roles/object-store-access-policies is refused
    # in the same way once the array holds more than ten roles; a query that
    # names at most ten roles is served

    @staticmethod
    def _role(index):
        return _Row(
            name="acc/role{0}".format(index),
            account=_ref("acc"),
            created=1735689600000,
            max_session_duration=3600000,
            prn="prn::iam:array-id/local:obj-account-id/1:role/role{0}".format(index),
            trusted_entities=[],
        )

    @staticmethod
    def _role_policies_served_ten_at_a_time(gone=(), broken=()):
        def read(member_names=None, **kwargs):
            if member_names is None or len(member_names) > 10:
                return _SdkError(400, MEMBERS_QUERY_REFUSED)
            if any(name in broken for name in member_names):
                return _SdkError(500, "Unexpected error.")
            if any(name in gone for name in member_names):
                return _SdkError(400, "Member does not exist.")
            return _listing(
                [
                    _Row(
                        member=_ref(name),
                        policy=_ref("pure:policy/bucket-list"),
                    )
                    for name in member_names
                ]
            )

        return read

    def _roles_client(self, **kwargs):
        return _array_admin_client(
            get_object_store_roles=_listing(
                [self._role(index) for index in range(1, 13)]
            ),
            get_object_store_roles_object_store_access_policies=(
                self._role_policies_served_ten_at_a_time(**kwargs)
            ),
        )

    @staticmethod
    def _role_queries(client):
        return [
            call[1].get("member_names")
            for call in client.calls
            if call[0] == "get_object_store_roles_object_store_access_policies"
        ]

    def test_role_policies_are_read_ten_roles_at_a_time(self):
        """main(), accounts subset: with more than ten roles every role
        still reports its policy instead of none."""
        client = self._roles_client()

        roles = _run_main(client, "accounts")[1]["object_store_roles"]

        assert len(roles) == 12
        for index in range(1, 13):
            assert roles["acc/role{0}".format(index)]["access_policies"] == [
                "pure:policy/bucket-list"
            ]
        names = ["acc/role{0}".format(index) for index in range(1, 13)]
        assert self._role_queries(client) == [None, names[:10], names[10:]]

    def test_role_removed_while_reading_is_skipped(self):
        client = self._roles_client(gone=("acc/role3",))

        roles = _run_main(client, "accounts")[1]["object_store_roles"]

        assert roles["acc/role3"]["access_policies"] == []
        for index in (1, 2, 4, 10, 11, 12):
            assert roles["acc/role{0}".format(index)]["access_policies"] == [
                "pure:policy/bucket-list"
            ]

    def test_role_policies_that_cannot_be_read_stay_empty(self):
        """As before, a failed read of the role policies does not fail the
        accounts subset."""
        client = self._roles_client(broken=("acc/role3",))
        roles = _run_main(client, "accounts")[1]["object_store_roles"]
        assert roles["acc/role3"]["access_policies"] == []
        assert roles["acc/role4"]["access_policies"] == ["pure:policy/bucket-list"]

        client = _array_admin_client(
            get_object_store_roles=_listing([self._role(1)]),
            get_object_store_roles_object_store_access_policies=_SdkError(
                500, "Unexpected error."
            ),
        )
        roles = _run_main(client, "accounts")[1]["object_store_roles"]
        assert roles["acc/role1"]["access_policies"] == []
        assert self._role_queries(client) == [None]


# ---------------------------------------------------------------------------
# Listings the array serves for ten objects per query, a file system that is
# removed while it is gathered, the policy counters of the default subset,
# the realms of the entries and the read-back of directory services and
# SAML2 providers. The rows are shaped as Purity//FB 4.8.8 returns them.
# ---------------------------------------------------------------------------

FS_QUERY_REFUSED = (
    "Querying is only supported for a maximum of 10 file systems per query."
)
BUCKET_QUERY_REFUSED = (
    "Querying is only supported for a maximum of 10 buckets per query."
)
LDS_REALM_ID = "77777777-7777-4777-8777-777777777777"
LDS_ARRAY_ID = "88888888-8888-4888-8888-888888888888"


def _realm_refs(realm=None):
    return [_ref(realm, REALM_ID, "realms")] if realm else []


def _fail_main(client, subset, version="2.30"):
    """Run main() for one subset that has to fail; returns the message"""
    module = Mock()
    module.params = {"gather_subset": [subset]}
    module.check_mode = False
    with patch.multiple(
        purefb_info_module,
        AnsibleModule=Mock(return_value=module),
        get_system=Mock(return_value=client),
        get_rest_api_version=Mock(return_value=version),
        LooseVersion=_Version,
    ):
        main()
    module.exit_json.assert_not_called()
    module.fail_json.assert_called_once()
    return module.fail_json.call_args[1]["msg"]


def _reads_of(client, name):
    return [call[1] for call in client.calls if call[0] == name]


def _performance_served_for_ten(
    refusal, gone=(), broken=(), gone_message="File system does not exist."
):
    """GET file-systems/performance or buckets/performance on an array that
    holds more of them than one query may cover"""

    def read(names=None, **kwargs):
        if names is None or len(names) > 10:
            return _SdkError(400, refusal)
        if any(name in broken for name in names):
            return _SdkError(500, "Unexpected error.")
        if any(name in gone for name in names):
            return _SdkError(400, gone_message)
        return _listing(
            [_Row(name=name, reads_per_sec=float(len(name)), time=4) for name in names]
        )

    return read


class TestPurefbInfoPerformanceAboveTen:
    """performance.filesystems and performance.buckets on an array that
    holds more file systems or buckets than one query may cover"""

    # file systems and buckets of a realm with array-level namesakes
    FILE_SYSTEMS = ["realm1::fs{0}".format(index) for index in range(1, 13)] + [
        "fs{0}".format(index) for index in range(1, 12)
    ]
    BUCKETS = ["realm1::bkt{0}".format(index) for index in range(1, 8)] + [
        "bkt{0}".format(index) for index in range(1, 8)
    ]

    def _client(self, **overrides):
        destroyed = _file_system_row("realm1::old")
        destroyed.destroyed = True
        reads = dict(
            get_file_systems=_listing(
                [_file_system_row(name) for name in self.FILE_SYSTEMS] + [destroyed]
            ),
            get_file_systems_performance=_performance_served_for_ten(FS_QUERY_REFUSED),
            get_buckets_performance=_performance_served_for_ten(BUCKET_QUERY_REFUSED),
            get_buckets_s3_specific_performance=_performance_served_for_ten(
                BUCKET_QUERY_REFUSED
            ),
        )
        reads.update(overrides)
        return _array_admin_client(**reads)

    @staticmethod
    def _names_asked(client, read):
        return [kwargs.get("names") for kwargs in _reads_of(client, read)]

    def test_file_systems_are_read_ten_names_at_a_time(self):
        """main(), performance subset: every file system has its sample, the
        one in a realm and its array-level namesake each their own, and no
        query names more than ten. A destroyed file system is not asked
        for: the query that names none does not report it either."""
        client = self._client()

        performance = _run_main(client, "performance")[1]["performance"]

        assert sorted(performance["filesystems"]) == sorted(self.FILE_SYSTEMS)
        assert performance["filesystems"]["realm1::fs1"]["reads_per_sec"] == 11.0
        assert performance["filesystems"]["fs1"]["reads_per_sec"] == 3.0
        names = self.FILE_SYSTEMS
        assert self._names_asked(client, "get_file_systems_performance") == [
            None,
            names[:10],
            names[10:20],
            names[20:],
        ]

    def test_buckets_are_read_ten_names_at_a_time(self):
        """A destroyed bucket is not asked for: the array fails a query
        that names one."""
        client = self._client(
            get_buckets=_listing(
                [_Row(name=name, destroyed=False) for name in self.BUCKETS]
                + [_Row(name="realm1::old", destroyed=True)]
            )
        )

        performance = _run_main(client, "performance")[1]["performance"]

        assert sorted(performance["buckets"]) == sorted(self.BUCKETS)
        for name in self.BUCKETS:
            assert performance["buckets"][name]["reads_per_sec"] == float(len(name))
            assert set(performance["buckets"][name]["s3"]) == set(S3_OPS_FIELDS)
        names = self.BUCKETS
        for read in ("get_buckets_performance", "get_buckets_s3_specific_performance"):
            assert self._names_asked(client, read) == [None, names[:10], names[10:]]

    def test_all_subset_reports_the_file_system_samples(self):
        info = _run_main(self._client(), "all")[1]

        assert len(info["performance"]["filesystems"]) == len(self.FILE_SYSTEMS)
        assert info["performance"]["buckets"] == {}

    def test_file_system_removed_while_reading_is_skipped(self):
        """A file system eradicated after it was listed fails the query of
        its ten; the others of that query are read one by one."""
        client = self._client(
            get_file_systems_performance=_performance_served_for_ten(
                FS_QUERY_REFUSED, gone=("realm1::fs12",)
            )
        )

        performance = _run_main(client, "performance")[1]["performance"]

        names = self.FILE_SYSTEMS
        assert sorted(performance["filesystems"]) == sorted(
            name for name in names if name != "realm1::fs12"
        )
        assert self._names_asked(client, "get_file_systems_performance") == (
            [None, names[:10], names[10:20]]
            + [[one] for one in names[10:20]]
            + [names[20:]]
        )

    def test_bucket_destroyed_while_reading_is_skipped(self):
        """A bucket destroyed after it was listed fails the query of its
        ten with another message; it is left out and the others are read
        one by one."""
        refused = _performance_served_for_ten(
            BUCKET_QUERY_REFUSED,
            gone=("bkt3",),
            gone_message="Bucket has been destroyed.",
        )
        client = self._client(
            get_buckets=_listing(
                [_Row(name=name, destroyed=False) for name in self.BUCKETS]
            ),
            get_buckets_performance=refused,
            get_buckets_s3_specific_performance=refused,
        )

        performance = _run_main(client, "performance")[1]["performance"]

        names = self.BUCKETS
        assert sorted(performance["buckets"]) == sorted(
            name for name in names if name != "bkt3"
        )
        assert self._names_asked(client, "get_buckets_performance") == (
            [None, names[:10]] + [[one] for one in names[:10]] + [names[10:]]
        )

    def test_a_read_the_array_fails_leaves_its_sample_out(self):
        """The performance subset reports what it can read: a file system
        whose sample the array fails to give is left out, the gather goes
        on."""
        client = self._client(
            get_file_systems_performance=_performance_served_for_ten(
                FS_QUERY_REFUSED, broken=("fs11",)
            )
        )

        performance = _run_main(client, "performance")[1]["performance"]

        assert sorted(performance["filesystems"]) == sorted(
            name for name in self.FILE_SYSTEMS if name != "fs11"
        )

    def test_file_system_without_a_sample_yet_is_left_out(self):
        """The array has no sample yet for a file system it has just
        created: the query that names it answers with the rows of the
        others, and nothing is asked again name by name."""
        served = _performance_served_for_ten(FS_QUERY_REFUSED)

        def read(names=None, **kwargs):
            response = served(names=names, **kwargs)
            if response.status_code == 200:
                response.items = [
                    row for row in response.items if row.name != "realm1::fs3"
                ]
            return response

        client = self._client(get_file_systems_performance=read)

        performance = _run_main(client, "performance")[1]["performance"]

        names = self.FILE_SYSTEMS
        assert sorted(performance["filesystems"]) == sorted(
            name for name in names if name != "realm1::fs3"
        )
        assert self._names_asked(client, "get_file_systems_performance") == [
            None,
            names[:10],
            names[10:20],
            names[20:],
        ]

    def test_no_samples_when_the_names_cannot_be_listed(self):
        client = self._client(get_file_systems=_SdkError(500, "Unexpected error."))

        performance = _run_main(client, "performance")[1]["performance"]

        assert performance["filesystems"] == {}
        assert self._names_asked(client, "get_file_systems_performance") == [None]

    def test_one_query_when_the_array_serves_every_sample(self):
        """Regression: up to ten file systems and buckets are read as
        before, in one query that names none, and nothing is listed."""
        client = _array_admin_client(
            get_file_systems_performance=_listing(
                [_Row(name="realm1::fs1", reads_per_sec=2.0, time=4)]
            ),
            get_buckets_performance=_listing(
                [_Row(name="bkt1", writes_per_sec=4.0, time=4)]
            ),
        )

        performance = _run_main(client, "performance")[1]["performance"]

        assert list(performance["filesystems"]) == ["realm1::fs1"]
        assert performance["filesystems"]["realm1::fs1"]["reads_per_sec"] == 2.0
        assert performance["buckets"]["bkt1"]["writes_per_sec"] == 4.0
        assert self._names_asked(client, "get_file_systems_performance") == [None]
        assert self._names_asked(client, "get_buckets_performance") == [None]
        assert _reads_of(client, "get_file_systems") == []
        assert _reads_of(client, "get_buckets") == []

    def test_refused_identity_makes_one_query(self):
        """Regression: an administrator limited to a realm is refused the
        samples; they stay empty and are not asked for again by name."""
        client = _realm_admin_client()

        performance = _run_main(client, "performance")[1]["performance"]

        assert performance["filesystems"] == {}
        assert performance["buckets"] == {}
        assert self._names_asked(client, "get_file_systems_performance") == [None]
        assert self._names_asked(client, "get_buckets_performance") == [None]


class TestPurefbInfoFileSystemGone:
    """A file system eradicated between the listing of the file systems and
    the reads of its quotas"""

    GONE = "realm1::gone"

    def _client(self, failure=None):
        failure = failure or _SdkError(400, "File system does not exist.")

        def answer(rows):
            def read(file_system_names=None, **kwargs):
                if file_system_names == [self.GONE]:
                    return failure
                return _listing(rows(file_system_names[0]))

            return read

        return _array_admin_client(
            get_file_systems=_listing(
                [
                    _file_system_with_id(self.GONE, FS_REALM_ID),
                    _file_system_with_id("gone", FS_ARRAY_ID),
                    _file_system_with_id("realm1::fs1", OTHER_ID),
                ]
            ),
            get_file_systems_users=answer(lambda name: []),
            get_file_systems_groups=answer(lambda name: []),
            get_quotas_groups=answer(
                lambda name: [
                    _Row(
                        name=name + "/2000",
                        group=_Row(id=2000, name=None),
                        quota=2048,
                        usage=0,
                    )
                ]
            ),
            get_quotas_users=answer(
                lambda name: [
                    _Row(
                        name=name + "/1000",
                        user=_Row(id=1000, name=None),
                        quota=1024,
                        usage=0,
                    )
                ]
            ),
        )

    @pytest.mark.parametrize("subset", ["filesystems", "all"])
    def test_file_system_is_reported_without_quotas(self, subset):
        """main(): no traceback. The file system keeps the entry of its
        listing, without quotas; its array-level namesake and the other
        file systems keep theirs."""
        filesystems = _run_main(self._client(), subset)[1]["filesystems"]

        assert list(filesystems) == [self.GONE, "gone", "realm1::fs1"]
        assert filesystems[self.GONE]["provisioned"] == 1073741824
        assert filesystems[self.GONE]["user_quotas"] == {}
        assert filesystems[self.GONE]["group_quotas"] == {}
        assert filesystems[self.GONE]["policy_quotas"] == {"users": [], "groups": []}
        assert filesystems["gone"]["user_quotas"] == {
            "1000": {"user_id": 1000, "user_name": None, "quota": 1024, "usage": 0}
        }
        assert filesystems["realm1::fs1"]["group_quotas"] == {
            "2000": {"group_id": 2000, "group_name": None, "quota": 2048, "usage": 0}
        }

    def test_another_failure_is_reported_with_the_message_of_the_array(self):
        """A quota read the array fails for another reason is neither a
        traceback nor a file system without quotas."""
        message = _fail_main(
            self._client(_SdkError(500, "Internal error.")), "filesystems"
        )

        assert message == (
            "Failed to read the group quotas of file system realm1::gone. "
            "Error: Internal error."
        )

    def test_refused_quota_reads_hold_no_quotas(self):
        """generate_fs_dict() on a client that is not guarded: a quota read
        the role does not grant leaves the quotas empty."""
        blade = self._client(_refused())

        with patch.multiple(
            purefb_info_module,
            get_rest_api_version=Mock(return_value="2.30"),
            LooseVersion=_Version,
        ):
            filesystems = generate_fs_dict(blade, [], "2.30", {})

        assert filesystems[self.GONE]["user_quotas"] == {}
        assert filesystems[self.GONE]["group_quotas"] == {}
        assert list(filesystems["gone"]["group_quotas"]) == ["2000"]

    def test_served_items(self):
        served = purefb_info_module._served_items
        named = purefb_info_module._items_of_named
        gone = _SdkError(400, "File system does not exist.")

        assert served(_listing([1, 2]), "x") == [1, 2]
        assert served(_refused(), "x") == []
        assert served(purefb_info_module._RefusedRead(gone), "x") == []
        assert named(_listing([1]), "x") == [1]
        assert named(gone, "x") == []
        assert named(_refused(), "x") == []
        for read in (served, named):
            with pytest.raises(purefb_info_module._ReadFailure) as failure:
                read(_SdkError(500, "Internal error."), "the quotas")
            assert str(failure.value) == (
                "Failed to read the quotas. Error: Internal error."
            )
        # "does not exist" only stands for no items where the read names
        # the object that is gone
        with pytest.raises(purefb_info_module._ReadFailure):
            served(gone, "x")


class TestPurefbInfoPolicyCounters:
    """The per-type policy counters of the default subset"""

    # policy types as GET policies-all names them
    TYPES = (
        ["snapshot"] * 2
        + ["object-store-access"] * 3
        + ["nfs-export"] * 2
        + ["smb-share", "smb-client", "network-access"]
        + ["worm-data"] * 2
        + ["telemetry-metrics"] * 4
        + ["qos", "user-group-quota", "s3-export", "tls"]
    )

    def _default(self, types):
        policies = [
            _Row(
                name="{0}policy{1}".format("realm1::" if index % 2 else "", index),
                policy_type=policy_type,
            )
            for index, policy_type in enumerate(types)
        ]
        client = _array_admin_client(get_policies_all=_listing(policies))
        return _run_main(client, "minimum")[1]["default"]

    def test_counters_use_the_policy_types_of_the_array(self):
        default = self._default(self.TYPES)

        assert default["policies"] == 20
        assert default["snapshot_policies"] == 2
        assert default["access_policies"] == 3
        assert default["nfs_policies"] == 2
        assert default["smb_share_policies"] == 1
        assert default["smb_client_policies"] == 1
        assert default["network_policies"] == 1
        assert default["worm_policies"] == 2
        assert default["telemetry_metrics_policies"] == 4

    def test_counters_accept_the_type_names_of_the_rest_reference(self):
        default = self._default(["nfs", "object-access", "nfs-export"])

        assert default["nfs_policies"] == 2
        assert default["access_policies"] == 1

    def test_no_policy_is_counted_twice(self):
        counted = [
            policy_type
            for counter, policy_types in purefb_info_module.POLICY_COUNTERS
            for policy_type in policy_types
        ]

        assert len(counted) == len(set(counted))


def _access_policy_row(name, realm=None):
    return _Row(
        name=name,
        arn=None,
        description="",
        enabled=True,
        is_local=True,
        policy_type="object-store-access",
        rules=[],
        realms=_realm_refs(realm),
    )


class TestPurefbInfoEntryRealms:
    """Every entry of an object type that can live in a realm reports the
    realms of its object"""

    def test_file_systems(self):
        in_realm = _file_system_with_id("realm1::fs1", FS_REALM_ID)
        in_realm.realms = _realm_refs("realm1")
        at_array = _file_system_with_id("fs1", FS_ARRAY_ID)
        at_array.realms = []
        client = _array_admin_client(get_file_systems=_listing([in_realm, at_array]))

        filesystems = _run_main(client, "filesystems")[1]["filesystems"]

        assert filesystems["realm1::fs1"]["realms"] == ["realm1"]
        assert filesystems["fs1"]["realms"] == []

    def test_accounts_and_their_exports(self):
        """An account export is named server::account, which is not a
        realm prefix: only the realms the array reports are listed."""
        client = _array_admin_client(
            get_object_store_accounts=_listing(
                [
                    _Row(
                        name="realm1::acc", object_count=0, realms=_realm_refs("realm1")
                    ),
                    _Row(name="acc", object_count=0, realms=[]),
                ]
            ),
            get_object_store_account_exports=_listing(
                [
                    _Row(
                        name="realm1::srv::realm1::acc",
                        enabled=True,
                        member=_ref("realm1::acc"),
                        policy=_ref("realm1::s3ep"),
                        server=_ref("realm1::srv"),
                        realms=_realm_refs("realm1"),
                    ),
                    _Row(
                        name="_array_server::acc",
                        enabled=True,
                        member=_ref("acc"),
                        policy=_ref("_s3_export_allow_everything"),
                        server=_ref("_array_server"),
                        realms=[],
                    ),
                ]
            ),
        )

        info = _run_main(client, "accounts")[1]

        assert info["accounts"]["realm1::acc"]["realms"] == ["realm1"]
        assert info["accounts"]["acc"]["realms"] == []
        exports = info["object_store_account_exports"]
        assert exports["realm1::srv::realm1::acc"]["realms"] == ["realm1"]
        assert exports["_array_server::acc"]["realms"] == []

    def test_virtual_hosts(self):
        client = _array_admin_client(
            get_object_store_virtual_hosts=_listing(
                [
                    _Row(
                        name="realm1::vh1",
                        hostname="a.example.com",
                        attached_servers=[_ref("realm1::srv")],
                        realms=_realm_refs("realm1"),
                    ),
                    _Row(
                        name="vh1",
                        hostname="b.example.com",
                        attached_servers=[_ref("_array_server")],
                        realms=[],
                    ),
                ]
            )
        )

        vhosts = _run_main(client, "buckets")[1]["object_store_virtual_hosts"]

        assert vhosts["realm1::vh1"] == {
            "hostname": "a.example.com",
            "attached_servers": ["realm1::srv"],
            "realms": ["realm1"],
        }
        assert vhosts["vh1"]["realms"] == []

    def test_dns_configurations_and_certificates(self):
        def certificate(name, realm=None):
            return _Row(
                name=name,
                valid_from=1795103101000,
                valid_to=1797695101000,
                realms=_realm_refs(realm),
            )

        client = _array_admin_client(
            get_dns=_listing(
                [
                    _Row(
                        name="realm1::dns1",
                        nameservers=["192.0.2.53"],
                        domain=None,
                        services=["data"],
                        realms=_realm_refs("realm1"),
                    ),
                    _Row(
                        name="management",
                        nameservers=["192.0.2.53"],
                        domain="example.com",
                        services=["management", "data"],
                        realms=[],
                    ),
                ]
            ),
            get_certificates=_listing(
                [certificate("realm1::cert1", "realm1"), certificate("cert1")]
            ),
        )

        config = _run_main(client, "config")[1]["config"]

        assert config["dns"]["realm1::dns1"]["realms"] == ["realm1"]
        assert config["dns"]["management"]["realms"] == []
        assert config["ssl_certs"]["realm1::cert1"]["realms"] == ["realm1"]
        assert config["ssl_certs"]["cert1"]["realms"] == []

    def test_active_directory_accounts(self):
        def account(name, realm=None):
            return _Row(
                name=name,
                computer_name="fb1",
                domain="example.com",
                directory_servers=[],
                kerberos_servers=[],
                service_principal_names=[],
                join_ou="",
                encryption_types=["aes256-cts-hmac-sha1-96"],
                realms=_realm_refs(realm),
            )

        client = _array_admin_client(
            get_active_directory=_listing(
                [account("realm1::ad1", "realm1"), account("ad1")]
            )
        )

        accounts = _run_main(client, "ad")[1]["active_directory"]

        assert accounts["realm1::ad1"]["realms"] == ["realm1"]
        assert accounts["ad1"]["realms"] == []

    def test_policies_of_realm_accounts_and_buckets(self):
        """The array reports no realm for the access policies of an account
        in a realm, nor for the access and CORS policies of a bucket in a
        realm. Their name places them; an array-level namesake and a
        built-in policy stay outside a realm."""

        def bucket_policies(suffix):
            def read(bucket_names=None, **kwargs):
                return _listing(
                    [
                        _Row(
                            name=bucket_names[0] + suffix,
                            enabled=True,
                            is_local=True,
                            rules=[],
                            realms=[],
                        )
                    ]
                )

            return read

        client = _array_admin_client(
            get_policies_all=_listing(
                [
                    _Row(
                        id=REALM_ID,
                        name="realm1::acc/pol",
                        enabled=True,
                        is_local=True,
                        location=_ref("fb1"),
                        policy_type="object-store-access",
                        realms=[],
                    ),
                    _Row(
                        id=ARRAY_ID,
                        name="acc/pol",
                        enabled=True,
                        is_local=True,
                        location=_ref("fb1"),
                        policy_type="object-store-access",
                        realms=[],
                    ),
                    _Row(
                        id=OTHER_ID,
                        name="realm1::daily",
                        enabled=True,
                        is_local=True,
                        location=_ref("realm1"),
                        policy_type="snapshot",
                        realms=_realm_refs("realm1"),
                    ),
                ]
            ),
            get_object_store_access_policies=_listing(
                [
                    _access_policy_row("realm1::acc/pol"),
                    _access_policy_row("acc/pol"),
                    _access_policy_row("pure:policy/full-access"),
                ]
            ),
            get_buckets=_listing([_Row(name="realm1::bkt"), _Row(name="bkt")]),
            get_buckets_bucket_access_policies=bucket_policies("/access-policy"),
            get_buckets_cross_origin_resource_sharing_policies=bucket_policies(
                "/cors-policy"
            ),
        )

        info = _run_main(client, "policies")[1]

        assert info["policies"]["realm1::acc/pol"]["realms"] == ["realm1"]
        assert info["policies"]["acc/pol"]["realms"] == []
        assert info["policies"]["realm1::daily"]["realms"] == ["realm1"]
        access = info["access_policies"]
        assert access["realm1::acc/pol"]["realms"] == ["realm1"]
        assert access["acc/pol"]["realms"] == []
        assert access["pure:policy/full-access"]["realms"] == []
        bucket_access = info["bucket_access_policies"]
        assert bucket_access["realm1::bkt/access-policy"]["realms"] == ["realm1"]
        assert bucket_access["bkt/access-policy"]["realms"] == []
        cors = info["bucket_cross_origin_policies"]
        assert cors["realm1::bkt/cors-policy"]["realms"] == ["realm1"]
        assert cors["bkt/cors-policy"]["realms"] == []

    def test_name_realm_and_policy_realms(self):
        name_realm = purefb_info_module._name_realm
        policy_realms = purefb_info_module._policy_realms

        assert name_realm("realm1::acc/pol") == "realm1"
        assert name_realm("acc/pol") is None
        assert name_realm("pure:policy/full-access") is None
        assert name_realm(None) is None
        # what the array reports comes first
        assert policy_realms(_Row(name="realm1::p", realms=_realm_refs("realm2"))) == [
            "realm2"
        ]
        assert policy_realms(_Row(name="realm1::p", realms=[])) == ["realm1"]
        assert policy_realms(_Row(name="realm1::p")) == ["realm1"]
        assert policy_realms(_Row(name="p", realms=[])) == []


def _saml2_provider(name, services, **idp):
    return _Row(
        name=name,
        enabled=False,
        array_url="https://fb.example.com",
        binding="none",
        prn="prn::iam:array-id/local::saml-provider/" + name,
        services=services,
        idp=_Row(
            encrypt_assertion_enabled=False,
            sign_request_enabled=False,
            metadata_url_ca_certificate=_Row(),
            metadata_url_ca_certificate_group=_Row(),
            **idp
        ),
        sp=_Row(
            decryption_credential=_Row(),
            signing_credential=_Row(),
            entity_id="https://fb.example.com/saml2/service-provider-metadata/" + name,
            assertion_consumer_url="https://fb.example.com/login/saml2/sso/" + name,
            metadata_url="https://fb.example.com/saml2/service-provider-metadata/"
            + name,
        ),
    )


class TestPurefbInfoSaml2Providers:
    """config.saml2_idps reports every SAML2 identity provider"""

    def _config(self, providers):
        client = _array_admin_client(get_sso_saml2_idps=_listing(providers))
        return _run_main(client, "config")[1]["config"]

    def test_every_provider_is_reported_under_its_name(self):
        """An array holds a provider for management and, shared with a
        realm, one for the object service; saml2sso keeps the first."""
        config = self._config(
            [
                _saml2_provider(
                    "PureSSO",
                    ["management"],
                    metadata_url="https://idp.example.com/metadata",
                    verification_certificate=_Row(),
                ),
                _saml2_provider(
                    "object-sso",
                    ["object"],
                    url="https://idp.example.com/sso",
                    entity_id="https://idp.example.com/idp",
                    verification_certificate=_ref("cert1"),
                ),
            ]
        )

        assert list(config["saml2_idps"]) == ["PureSSO", "object-sso"]
        assert config["saml2sso"] == config["saml2_idps"]["PureSSO"]
        assert config["saml2sso"]["name"] == "PureSSO"
        shared = config["saml2_idps"]["object-sso"]
        assert shared["services"] == ["object"]
        assert shared["enabled"] is False
        assert shared["prn"] == "prn::iam:array-id/local::saml-provider/object-sso"
        assert shared["trust_other_saml_sps_in_fleet"] is None
        assert shared["idp"] == {
            "url": "https://idp.example.com/sso",
            "entity_id": "https://idp.example.com/idp",
            "encrypt_enabled": False,
            "sign_enabled": False,
            "metadata_url": None,
            "metadata_url_ca_certificate": None,
            "metadata_url_ca_certificate_group": None,
            "verification_certificate": "cert1",
        }
        assert shared["sp"]["sign_cred"] is None
        assert shared["sp"]["assertion_consumer_url"] == (
            "https://fb.example.com/login/saml2/sso/object-sso"
        )

    def test_no_provider(self):
        config = self._config([])

        assert config["saml2sso"] == {}
        assert config["saml2_idps"] == {}


def _directory_service_row(name, **fields):
    """A directory service as the array lists it; the one of a server holds
    no base DN, bind user or URIs"""
    row = _Row(
        name=name,
        enabled=False,
        services=["nfs"],
        uris=[],
        ca_certificate=_Row(),
        ca_certificate_group=_Row(),
        management=_Row(user_login_attribute=None, user_object_class=None),
        nfs=_Row(nis_domains=[], nis_servers=[]),
        smb=_Row(join_ou=None),
    )
    for key, value in fields.items():
        setattr(row, key, value)
    return row


def _lds_ref(name, lds_id):
    return _ref(name, lds_id, "directory-services/local/directory-services")


def _lds_row(name, lds_id, server, realm=None):
    return _Row(
        name=name,
        id=lds_id,
        domain=name.split("::")[-1],
        server=_ref(server, None, "servers"),
        realms=_realm_refs(realm),
    )


def _local_user_row(lds, name, uid, group, built_in=False):
    return _Row(
        name=name,
        uid=uid,
        sid="S-1-5-21-1-2-3-{0}".format(uid),
        enabled=not built_in,
        built_in=built_in,
        primary_group=_ref(group, None, "directory-services/local/groups"),
        local_directory_service=lds,
    )


def _local_group_row(lds, name, gid, built_in=False):
    return _Row(
        name=name,
        gid=gid,
        sid="S-1-5-32-{0}".format(gid),
        built_in=built_in,
        local_directory_service=lds,
    )


def _local_member_row(lds, group, member, kind="users", primary=False):
    return _Row(
        group=_ref(group, None, "directory-services/local/groups"),
        member=_ref(member, None, "directory-services/local/" + kind),
        is_primary_group=primary,
        local_directory_service=lds,
    )


class TestPurefbInfoDirectoryServices:
    """config.directory_services and config.local_directory_services"""

    REALM_LDS = _lds_ref("realm1::lds1", LDS_REALM_ID)
    ARRAY_LDS = _lds_ref("lds1", LDS_ARRAY_ID)

    def test_directory_services_are_reported_under_their_full_name(self):
        """The directory services of the array keep their own keys; the
        ones of a server, in a realm or not, are reported as well."""
        client = _array_admin_client(
            get_directory_services=_listing(
                [
                    _directory_service_row(
                        "management",
                        enabled=True,
                        services=["management"],
                        uris=["ldap://ds.example.com"],
                        base_dn="DC=example,DC=com",
                        bind_user="svc",
                        management=_Row(
                            user_login_attribute="sAMAccountName",
                            user_object_class="User",
                        ),
                    ),
                    _directory_service_row(
                        "nfs", uris=[], base_dn=None, bind_user=None
                    ),
                    _directory_service_row("srv1_nfs"),
                    _directory_service_row("realm1::srv1_nfs"),
                ]
            )
        )

        config = _run_main(client, "config")[1]["config"]

        services = config["directory_services"]
        assert sorted(services) == ["management", "nfs", "realm1::srv1_nfs", "srv1_nfs"]
        assert services["realm1::srv1_nfs"] == {
            "base_dn": None,
            "bind_user": None,
            "ca_certificate": None,
            "ca_certificate_group": None,
            "enabled": False,
            "management": {"user_login_attribute": None, "user_object_class": None},
            "nis_servers": [],
            "nis_domains": [],
            "services": ["nfs"],
            "join_ou": None,
            "uris": [],
        }
        assert services["srv1_nfs"] == services["realm1::srv1_nfs"]
        assert services["management"]["base_dn"] == "DC=example,DC=com"
        assert services["management"]["management"] == {
            "user_login_attribute": "sAMAccountName",
            "user_object_class": "User",
        }
        assert config["management_directory_service"] == services["management"]
        assert config["array_management"] == services["management"]
        assert config["nfs_directory_service"] == services["nfs"]
        assert "smb_directory_service" not in config

    def _lds_client(self, **overrides):
        reads = dict(
            get_directory_services_local_directory_services=_listing(
                [
                    _lds_row("realm1::lds1", LDS_REALM_ID, "realm1::srv1", "realm1"),
                    _lds_row("lds1", LDS_ARRAY_ID, "srv1"),
                ]
            ),
            get_directory_services_local_users=_listing(
                [
                    _local_user_row(
                        self.REALM_LDS, "Administrator", 0, "Administrators", True
                    ),
                    _local_user_row(self.REALM_LDS, "alice", 5001, "staff"),
                    _local_user_row(self.ARRAY_LDS, "alice", 6001, "staff"),
                    _local_user_row(self.ARRAY_LDS, "staff", 6002, "staff"),
                ]
            ),
            get_directory_services_local_groups=_listing(
                [
                    _local_group_row(self.REALM_LDS, "Administrators", 0, True),
                    _local_group_row(self.REALM_LDS, "staff", 7001),
                    _local_group_row(self.ARRAY_LDS, "Backup Operators", 65535, True),
                    _local_group_row(self.ARRAY_LDS, "staff", 8001),
                ]
            ),
            get_directory_services_local_groups_members=_listing(
                [
                    _local_member_row(
                        self.REALM_LDS, "Administrators", "Administrator", primary=True
                    ),
                    _local_member_row(self.REALM_LDS, "staff", "alice", primary=True),
                    _local_member_row(self.REALM_LDS, "Administrators", "alice"),
                    _local_member_row(self.ARRAY_LDS, "staff", "alice", primary=True),
                    _local_member_row(self.ARRAY_LDS, "staff", "staff", primary=True),
                    _local_member_row(
                        self.ARRAY_LDS, "Backup Operators", "staff", kind="groups"
                    ),
                ]
            ),
        )
        reads.update(overrides)
        return _array_admin_client(**reads)

    def test_local_directory_services_with_their_users_and_groups(self):
        """A local directory service in a realm and an array-level one of
        the same name, with users and groups of the same names: each
        reports its own."""
        client = self._lds_client()

        services = _run_main(client, "config")[1]["config"]["local_directory_services"]

        assert sorted(services) == ["lds1", "realm1::lds1"]
        in_realm = services["realm1::lds1"]
        assert in_realm["domain"] == "lds1"
        assert in_realm["realms"] == ["realm1"]
        assert in_realm["server"] == "realm1::srv1"
        assert sorted(in_realm["users"]) == ["Administrator", "alice"]
        assert in_realm["users"]["alice"] == {
            "uid": 5001,
            "sid": "S-1-5-21-1-2-3-5001",
            "enabled": True,
            "built_in": False,
            "email": None,
            "primary_group": "staff",
            "groups": ["staff", "Administrators"],
        }
        assert in_realm["users"]["Administrator"]["built_in"] is True
        assert in_realm["groups"]["staff"] == {
            "gid": 7001,
            "sid": "S-1-5-32-7001",
            "built_in": False,
            "email": None,
            "members": [
                {"name": "alice", "resource_type": "directory-services/local/users"}
            ],
        }
        assert [
            member["name"] for member in in_realm["groups"]["Administrators"]["members"]
        ] == ["Administrator", "alice"]
        at_array = services["lds1"]
        assert at_array["realms"] == []
        assert at_array["server"] == "srv1"
        assert list(at_array["users"]) == ["alice", "staff"]
        assert at_array["users"]["alice"]["uid"] == 6001
        assert at_array["users"]["alice"]["groups"] == ["staff"]
        assert at_array["groups"]["staff"]["gid"] == 8001
        # a group that is a member of a group is listed with its type and
        # is no group membership of the user of that name
        assert at_array["groups"]["Backup Operators"]["members"] == [
            {"name": "staff", "resource_type": "directory-services/local/groups"}
        ]
        assert at_array["users"]["staff"]["groups"] == ["staff"]

    def test_local_directory_services_need_rest_2_24(self):
        client = self._lds_client()

        config = _run_main(client, "config", version="2.23")[1]["config"]

        assert "local_directory_services" not in config
        assert "directory_services" in config
        assert not [
            call for call in client.calls if "directory_services_local" in call[0]
        ]

    def test_users_and_groups_are_not_read_without_a_local_directory_service(self):
        client = _array_admin_client()

        config = _run_main(client, "config")[1]["config"]

        assert config["local_directory_services"] == {}
        assert [
            call[0] for call in client.calls if "directory_services_local" in call[0]
        ] == ["get_directory_services_local_directory_services"]

    def test_refused_reads_leave_their_entries_empty(self):
        """An identity the array refuses the local users sees the local
        directory services without users; refused the services, none."""
        client = self._lds_client(get_directory_services_local_users=_refused())
        services = _run_main(client, "config")[1]["config"]["local_directory_services"]
        assert services["realm1::lds1"]["users"] == {}
        assert sorted(services["realm1::lds1"]["groups"]) == ["Administrators", "staff"]

        client = self._lds_client(
            get_directory_services_local_directory_services=_refused()
        )
        config = _run_main(client, "config")[1]["config"]
        assert config["local_directory_services"] == {}

    def test_rows_of_a_service_that_is_not_listed_are_left_out(self):
        """An administrator limited to a realm lists the local directory
        service of its realm only, yet the array shows it the users, groups
        and memberships of every other one: they belong to no entry, those
        of the array-level namesake included."""
        client = self._lds_client(
            get_directory_services_local_directory_services=_listing(
                [_lds_row("realm1::lds1", LDS_REALM_ID, "realm1::srv1", "realm1")]
            )
        )

        services = _run_main(client, "config")[1]["config"]["local_directory_services"]

        assert list(services) == ["realm1::lds1"]
        in_realm = services["realm1::lds1"]
        assert sorted(in_realm["users"]) == ["Administrator", "alice"]
        assert in_realm["users"]["alice"]["uid"] == 5001
        assert in_realm["users"]["alice"]["groups"] == ["staff", "Administrators"]
        assert sorted(in_realm["groups"]) == ["Administrators", "staff"]
        assert in_realm["groups"]["staff"]["gid"] == 7001
        assert in_realm["groups"]["staff"]["members"] == [
            {"name": "alice", "resource_type": "directory-services/local/users"}
        ]

    @pytest.mark.parametrize(
        "read, what",
        [
            (
                "get_directory_services_local_directory_services",
                "the local directory services",
            ),
            ("get_directory_services_local_users", "the local users"),
            ("get_directory_services_local_groups", "the local groups"),
            (
                "get_directory_services_local_groups_members",
                "the members of the local groups",
            ),
        ],
    )
    def test_a_failed_read_is_reported_with_the_message_of_the_array(self, read, what):
        client = self._lds_client(**{read: _SdkError(500, "Internal error.")})

        message = _fail_main(client, "config")

        assert message == "Failed to read {0}. Error: Internal error.".format(what)
