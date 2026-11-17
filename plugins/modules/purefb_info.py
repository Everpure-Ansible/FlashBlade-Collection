#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2019, Simon Dodsley (simon@everpuredata.com)
# GNU General Public License v3.0+ (see COPYING or
# https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

ANSIBLE_METADATA = {
    "metadata_version": "1.1",
    "status": ["preview"],
    "supported_by": "community",
}

DOCUMENTATION = r"""
---
module: purefb_info
version_added: '1.0.0'
short_description: Collect information from Everpure FlashBlade
description:
  - Collect information from a Everpure FlashBlade running the
    Purity//FB operating system. By default, the module will collect basic
    information including hosts, host groups, protection
    groups and volume counts. Additional information can be collected
    based on the configured set of arguements.
author:
  - Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  gather_subset:
    description:
      - When supplied, this argument will define the information to be collected.
        Possible values for this include all, minimum, config, performance,
        capacity, network, subnets, lags, filesystems, snapshots, buckets,
        replication, policies, arrays, accounts, admins, ad, kerberos,
        drives, servers, fleet, realms, clients, locks, support and
        legal_holds.
      - The C(performance) subset reports array-wide performance per protocol
        (C(aggregate), C(http), C(s3), C(nfs), C(smb)), the protocol-specific
        operation breakdowns (C(nfs_ops), C(s3_ops), C(http_ops)), replication
        performance (array-wide, per array connection and per target under
        C(replication)) and point-in-time per-object samples keyed by name
        under C(filesystems) and C(buckets).
      - The C(clients) subset lists per-client NFS and S3 performance from
        the array's client sample. Clients are reported as C(IP:PORT) and
        each list is capped at the first 100 entries the array returns.
        Sampling takes several seconds per protocol and S3 clients are
        listed per connection, so this subset is not part of C(all) and
        must be requested explicitly. S3 client performance requires
        REST 2.18 (Purity//FB 4.6.0) and is reported empty on older arrays.
      - The C(legal_holds) subset lists every file legal hold with its
        description, realms and the paths it is currently applied to.
        Requires REST API 2.17 or later and is skipped on older arrays.
      - The C(filesystems) subset surfaces the legacy file system keys
        C(nfs_rules), C(export_policy), C(smb_client_policy) and
        C(smb_share_policy). Purity//FB marks the underlying fields as
        deprecated in favour of File System Exports, so these keys may
        return C(null) in future releases. Read export policy
        assignments from the per-filesystem C(file_system_exports)
        list (and the top-level C(file_system_exports) view under
        C(subset=filesystems)/C(subset=all)) instead. These keys will
        be removed from this module in 2.0.0.
      - The C(arrays) subset reports C(connection_paths) for every array
        connection, one entry per network path with its C(source),
        C(destination), C(status), C(status_details) and C(type).
      - The C(policies) subset reports C(members) for every policy
        (Purity//FB REST 2.2 or later), each with the member C(name) and
        C(resource_type); replica link members also carry a C(link) with
        the local and remote file systems. Snapshot policies in
        C(snapshot_policies) carry the same C(members). TLS policies
        report C(array_wide), true when the policy applies to the array
        as a whole.
      - The C(minimum) subset key C(network_access_protocol) holds the
        name of the array network access policy and is misspelt. Use
        C(network_access_policy) instead; the misspelt key is kept for
        backwards compatibility and will be removed in 2.0.0.
    required: false
    type: list
    elements: str
    default: minimum
extends_documentation_fragment:
  - everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: collect default set of info
  everpure.flashblade.purefb_info:
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
  register: blade_info
- name: show default information
  debug:
    msg: "{{ blade_info['purefb_info']['default'] }}"

- name: collect configuration and capacity info
  everpure.flashblade.purefb_info:
    gather_subset:
      - config
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
  register: blade_info
- name: show config information
  debug:
    msg: "{{ blade_info['purefb_info']['config'] }}"

- name: collect all info
  everpure.flashblade.purefb_info:
    gather_subset:
      - all
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
  register: blade_info
- name: show all information
  debug:
    msg: "{{ blade_info['purefb_info'] }}"

- name: collect per-client performance (opt-in, not part of all)
  everpure.flashblade.purefb_info:
    gather_subset:
      - clients
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
  register: blade_info
- name: show NFS client performance
  debug:
    msg: "{{ blade_info['purefb_info']['clients']['nfs'] }}"
"""

RETURN = r"""
purefb_info:
  description: Returns the information collected from the FlashBlade
  returned: always
  type: dict
"""


from ansible.module_utils.basic import AnsibleModule
from ansible_collections.everpure.flashblade.plugins.module_utils.purefb import (
    get_system,
    purefb_argument_spec,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.version import (
    LooseVersion,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.common import (
    get_rest_api_version,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.time_utils import (
    milliseconds_to_time,
)
from datetime import datetime, timezone
import time

KMIP_API_VERSION = "2.1"
POLICY_MEMBERS_API_VERSION = "2.2"
DRIVES_API_VERSION = "2.5"
SECURITY_API_VERSION = "2.7"
BUCKET_API_VERSION = "2.8"
SMB_CLIENT_API_VERSION = "2.10"
SPACE_API_VERSION = "2.11"
PUBLIC_API_VERSION = "2.12"
NAP_API_VERSION = "2.13"
RA_DURATION_API_VERSION = "2.14"
SSH_CA_API_VERSION = "2.14"
SMTP_ENCRYPT_API_VERSION = "2.15"
WORM_API_VERSION = "2.15"
SERVERS_API_VERSION = "2.16"
PASSWORD_POLICY_API_VERSION = "2.16"
MAINTENANCE_API_VERSION = "2.16"
FLEET_API_VERSION = "2.17"
TLS_API_VERSION = "2.17"
LEGAL_HOLD_API_VERSION = "2.17"
EDGE_API_VERSION = "2.18"
OIDC_API_VERSION = "2.17"
CLIENTS_S3_API_VERSION = "2.18"
STORAGE_CLASS_API_VERSION = "2.17"
REALMS_API_VERSION = "2.19"
MAP_API_VERSION = "2.19"
S3_EXPORT_API_VERSION = "2.20"
# From REST 2.29 (Purity//FB 4.8.6) a WORM data policy carries commit_mode and
# the autocommit configuration.
WORM_AUTOCOMMIT_API_VERSION = "2.29"
REALM_DEFAULTS_API_VERSION = "2.20"
SUPPORT_DIAGNOSTICS_API_VERSION = "2.16"
SUPPORT_DIAGNOSTICS_SETTINGS_API_VERSION = "2.24"
EVICTION_API_VERSION = "2.21"


def _bytes_to_human(bytes_number):
    if bytes_number:
        labels = ["B/s", "KB/s", "MB/s", "GB/s", "TB/s", "PB/s"]
        i = 0
        double_bytes = bytes_number
        while i < len(labels) and bytes_number >= 1024:
            double_bytes = bytes_number / 1024.0
            i += 1
            bytes_number = bytes_number / 1024
        return str(round(double_bytes, 2)) + " " + labels[i]
    return None


def _reference_names(references):
    """Return the names in a list of references (None or empty gives [])"""
    return [
        reference.name
        for reference in (references or [])
        if getattr(reference, "name", None)
    ]


def generate_directory_service_roles_dict(blade, api_version):
    """Return the directory service role mappings

    ``role`` is null for a mapping with no, several, or a custom management
    access policy, so it is read through getattr. The policy names are
    reported from REST 2.19, where the array exposes them.
    """
    roles_info = {}
    report_policies = LooseVersion(MAP_API_VERSION) <= LooseVersion(api_version)
    for ds_role in list(blade.get_directory_services_roles().items):
        roles_info[ds_role.name] = {
            "group": getattr(ds_role, "group", None),
            "group_base": getattr(ds_role, "group_base", None),
            "role": getattr(getattr(ds_role, "role", None), "name", None),
        }
        if report_policies:
            roles_info[ds_role.name]["management_access_policies"] = _reference_names(
                getattr(ds_role, "management_access_policies", None)
            )
    return roles_info


def _maintenance_window_list(blade):
    """Return the open maintenance window as a one-item list, or []"""
    windows = []
    res = blade.get_maintenance_windows()
    if res.status_code == 200:
        for window in list(res.items):
            windows.append(
                {
                    "name": window.name,
                    "created": datetime.fromtimestamp(
                        int(window.created) / 1000
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                    "expires": datetime.fromtimestamp(
                        int(window.expires) / 1000
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
    return windows


def _reference_name(obj, field):
    """Name held by a reference field the SDK returns as a dict or an object."""
    ref = getattr(obj, field, None)
    if isinstance(ref, dict):
        return ref.get("name") or None
    return getattr(ref, "name", None) or None


def generate_default_dict(blade):
    default_info = {}
    # NOTE(latent bug): this previously read list(blade.get_versions().items)[0]
    # - a single version string - so the SECURITY/NAP/RA_DURATION gates below
    # were substring checks that could never match as intended. The
    # get_rest_api_version()/LooseVersion migration makes these gates evaluate
    # correctly, so the gated sections can now appear where they never did.
    api_version = get_rest_api_version(blade)
    defaults = list(blade.get_arrays().items)[0]
    default_info["flashblade_name"] = defaults.name
    default_info["purity_version"] = defaults.version
    # the login (MOTD) banner, so purefb_banner changes can be read back
    default_info["banner"] = getattr(defaults, "banner", None)
    default_info["filesystems"] = blade.get_file_systems().total_item_count
    default_info["snapshots"] = blade.get_file_system_snapshots().total_item_count
    default_info["buckets"] = blade.get_buckets().total_item_count
    default_info["object_store_users"] = blade.get_object_store_users().total_item_count
    default_info["object_store_accounts"] = (
        blade.get_object_store_accounts().total_item_count
    )
    default_info["blades"] = blade.get_blades().total_item_count
    default_info["certificates"] = blade.get_certificates().total_item_count
    default_info["total_capacity"] = list(blade.get_arrays_space().items)[0].capacity
    default_info["api_versions"] = api_version
    default_info["policies"] = blade.get_policies_all().total_item_count
    # Count policies by type
    all_policies = list(blade.get_policies_all().items)
    default_info["snapshot_policies"] = sum(
        1 for p in all_policies if p.policy_type == "snapshot"
    )
    default_info["access_policies"] = sum(
        1 for p in all_policies if p.policy_type == "access"
    )
    default_info["nfs_policies"] = sum(
        1 for p in all_policies if p.policy_type == "nfs"
    )
    default_info["smb_share_policies"] = sum(
        1 for p in all_policies if p.policy_type == "smb_share"
    )
    default_info["smb_client_policies"] = sum(
        1 for p in all_policies if p.policy_type == "smb_client"
    )
    default_info["network_policies"] = sum(
        1 for p in all_policies if p.policy_type == "network"
    )
    default_info["worm_policies"] = sum(
        1 for p in all_policies if p.policy_type == "worm"
    )
    default_info["telemetry_metrics_policies"] = sum(
        1 for p in all_policies if p.policy_type == "telemetry-metrics"
    )
    default_info["certificate_groups"] = blade.get_certificate_groups().total_item_count
    default_info["fs_replicas"] = blade.get_file_system_replica_links().total_item_count
    default_info["remote_credentials"] = (
        blade.get_object_store_remote_credentials().total_item_count
    )
    default_info["bucket_replicas"] = blade.get_bucket_replica_links().total_item_count
    default_info["connected_arrays"] = blade.get_array_connections().total_item_count
    default_info["targets"] = blade.get_targets().total_item_count
    default_info["kerberos_keytabs"] = blade.get_keytabs().total_item_count
    default_info["syslog_servers"] = len(blade.get_syslog_servers().items)
    default_info["object_store_virtual_hosts"] = len(
        blade.get_object_store_virtual_hosts().items
    )
    default_info["api_clients"] = len(blade.get_api_clients().items)
    default_info["idle_timeout"] = int(defaults.idle_timeout / 60000)
    if list(blade.get_arrays_eula().items)[0].signature.accepted:
        default_info["EULA"] = "Signed"
    else:
        default_info["EULA"] = "Not Signed"
    admin_settings = list(blade.get_admins_settings().items)[0]
    default_info["max_login_attempts"] = admin_settings.max_login_attempts
    default_info["min_password_length"] = admin_settings.min_password_length
    if admin_settings.lockout_duration:
        default_info["lockout_duration"] = (
            str(admin_settings.lockout_duration / 1000) + " seconds"
        )
    default_info["smb_mode"] = getattr(defaults, "smb_mode", None)
    default_info["timezone"] = defaults.time_zone
    default_info["product_type"] = getattr(defaults, "product_type", "Unknown")
    if LooseVersion(SECURITY_API_VERSION) <= LooseVersion(api_version):
        dar = defaults.encryption.data_at_rest
        default_info["encryption"] = {
            "data_at_rest_enabled": dar.enabled,
            "data_at_rest_algorithms": dar.algorithms,
            "data_at_rest_entropy_source": dar.entropy_source,
        }
        keys = list(blade.get_support_verification_keys().items)
        default_info["support_keys"] = {}
        for key in keys:
            keyname = key.name
            default_info["support_keys"][keyname] = {key.verification_key}
        default_info["security_update"] = getattr(defaults, "security_update", None)
    if LooseVersion(NAP_API_VERSION) <= LooseVersion(api_version):
        default_info["network_access_protocol"] = getattr(
            defaults.network_access_policy, "name", "None"
        )
        # the key above is misspelt; it is kept for backwards compatibility
        default_info["network_access_policy"] = default_info["network_access_protocol"]
    ra_info = list(blade.get_support().items)[0]
    if ra_info.remote_assist_active:
        ra_expires = datetime.fromtimestamp(
            int(ra_info.remote_assist_expires) / 1000
        ).strftime("%Y-%m-%d %H:%M:%S")
        ra_opened = datetime.fromtimestamp(
            int(ra_info.remote_assist_opened) / 1000
        ).strftime("%Y-%m-%d %H:%M:%S")
    else:
        ra_expires = ra_opened = None
    default_info["remote_assist"] = {
        "phonehome_enabled": ra_info.phonehome_enabled,
        "proxy": ra_info.proxy,
        "ra_active": ra_info.remote_assist_active,
        "ra_expires": ra_expires,
        "ra_opened": ra_opened,
        "ra_status": ra_info.remote_assist_status,
    }
    if LooseVersion(RA_DURATION_API_VERSION) <= LooseVersion(api_version):
        default_info["remote_assist"]["ra_duration"] = ra_info.remote_assist_duration
    if LooseVersion(MAINTENANCE_API_VERSION) <= LooseVersion(api_version):
        default_info["maintenance_window"] = _maintenance_window_list(blade)
    if LooseVersion(EDGE_API_VERSION) <= LooseVersion(api_version):
        # Pure1 Edge Services opt-ins, set by purefb_phonehome
        default_info["remote_assist"]["edge_management_enabled"] = getattr(
            ra_info, "edge_management_enabled", None
        )
        default_info["remote_assist"]["edge_agent_update_enabled"] = getattr(
            ra_info, "edge_agent_update_enabled", None
        )
    return default_info


# Performance samples (array, file system, bucket and client rows) share one
# metric layout; the protocol-specific endpoints each have their own.
PERF_FIELDS = (
    "bytes_per_op",
    "bytes_per_read",
    "bytes_per_write",
    "others_per_sec",
    "read_bytes_per_sec",
    "reads_per_sec",
    "time",
    "usec_per_other_op",
    "usec_per_read_op",
    "usec_per_write_op",
    "write_bytes_per_sec",
    "writes_per_sec",
)
NFS_OPS_FIELDS = (
    "accesses_per_sec",
    "aggregate_file_metadata_creates_per_sec",
    "aggregate_file_metadata_modifies_per_sec",
    "aggregate_file_metadata_reads_per_sec",
    "aggregate_other_per_sec",
    "aggregate_share_metadata_reads_per_sec",
    "aggregate_usec_per_file_metadata_create_op",
    "aggregate_usec_per_file_metadata_modify_op",
    "aggregate_usec_per_file_metadata_read_op",
    "aggregate_usec_per_other_op",
    "aggregate_usec_per_share_metadata_read_op",
    "creates_per_sec",
    "fsinfos_per_sec",
    "fsstats_per_sec",
    "getattrs_per_sec",
    "links_per_sec",
    "lookups_per_sec",
    "mkdirs_per_sec",
    "pathconfs_per_sec",
    "readdirpluses_per_sec",
    "readdirs_per_sec",
    "readlinks_per_sec",
    "reads_per_sec",
    "removes_per_sec",
    "renames_per_sec",
    "rmdirs_per_sec",
    "setattrs_per_sec",
    "symlinks_per_sec",
    "time",
    "usec_per_access_op",
    "usec_per_create_op",
    "usec_per_fsinfo_op",
    "usec_per_fsstat_op",
    "usec_per_getattr_op",
    "usec_per_link_op",
    "usec_per_lookup_op",
    "usec_per_mkdir_op",
    "usec_per_pathconf_op",
    "usec_per_read_op",
    "usec_per_readdir_op",
    "usec_per_readdirplus_op",
    "usec_per_readlink_op",
    "usec_per_remove_op",
    "usec_per_rename_op",
    "usec_per_rmdir_op",
    "usec_per_setattr_op",
    "usec_per_symlink_op",
    "usec_per_write_op",
    "writes_per_sec",
)
S3_OPS_FIELDS = (
    "others_per_sec",
    "read_buckets_per_sec",
    "read_objects_per_sec",
    "time",
    "usec_per_other_op",
    "usec_per_read_bucket_op",
    "usec_per_read_object_op",
    "usec_per_write_bucket_op",
    "usec_per_write_object_op",
    "write_buckets_per_sec",
    "write_objects_per_sec",
)
HTTP_OPS_FIELDS = (
    "others_per_sec",
    "read_dirs_per_sec",
    "read_files_per_sec",
    "time",
    "usec_per_other_op",
    "usec_per_read_dir_op",
    "usec_per_read_file_op",
    "usec_per_write_dir_op",
    "usec_per_write_file_op",
    "write_dirs_per_sec",
    "write_files_per_sec",
)
REPL_PERF_FIELDS = ("received_bytes_per_sec", "transmitted_bytes_per_sec")
OBJECT_BACKLOG_FIELDS = (
    "bytes_count",
    "delete_ops_count",
    "other_ops_count",
    "put_ops_count",
)
# The array samples clients for several seconds per request and lists S3
# clients per connection, so the listings are capped like the CLI does.
CLIENTS_PERF_LIMIT = 100


def _perf_fields(sample, fields):
    """Return the requested metric fields of a performance sample as a dict.

    Fields the array did not report come back as None; a missing sample
    gives an empty dict so callers can store the result as-is.
    """
    if sample is None:
        return {}
    return {field: getattr(sample, field, None) for field in fields}


def _perf_items(response):
    """Return the items of a successful list response, or an empty list."""
    if getattr(response, "status_code", None) != 200:
        return []
    return list(response.items)


def _perf_first(response):
    """Return the first item of a successful list response, or None."""
    items = _perf_items(response)
    return items[0] if items else None


def _replication_perf(sample):
    """Flatten a ResourcePerformanceReplication sample.

    ``aggregate`` and ``periodic`` carry bytes received/transmitted per
    second; ``continuous`` adds the object replication backlog. The array
    omits sub-objects it has no data for, so every level is optional.
    """
    if sample is None:
        return {}
    continuous = getattr(sample, "continuous", None)
    repl_info = {
        "aggregate": _perf_fields(getattr(sample, "aggregate", None), REPL_PERF_FIELDS),
        "periodic": _perf_fields(getattr(sample, "periodic", None), REPL_PERF_FIELDS),
        "continuous": _perf_fields(continuous, REPL_PERF_FIELDS),
        "time": getattr(sample, "time", None),
    }
    if continuous is not None:
        repl_info["continuous"]["object_backlog"] = _perf_fields(
            getattr(continuous, "object_backlog", None), OBJECT_BACKLOG_FIELDS
        )
    return repl_info


def generate_perf_breakdown_dict(blade):
    """Protocol, replication and per-object performance for the performance subset.

    Every endpoint used here exists since REST 2.0, so there is no version
    gate. A failed GET leaves its key empty instead of failing the gather.
    """
    breakdown = {
        "smb": _perf_fields(
            _perf_first(blade.get_arrays_performance(protocol="smb")), PERF_FIELDS
        ),
        "nfs_ops": _perf_fields(
            _perf_first(blade.get_arrays_nfs_specific_performance()), NFS_OPS_FIELDS
        ),
        "s3_ops": _perf_fields(
            _perf_first(blade.get_arrays_s3_specific_performance()), S3_OPS_FIELDS
        ),
        "http_ops": _perf_fields(
            _perf_first(blade.get_arrays_http_specific_performance()),
            HTTP_OPS_FIELDS,
        ),
        "replication": _replication_perf(
            _perf_first(blade.get_arrays_performance_replication())
        ),
        "filesystems": {},
        "buckets": {},
    }
    breakdown["replication"]["array_connections"] = {}
    breakdown["replication"]["targets"] = {}
    for conn in _perf_items(blade.get_array_connections_performance_replication()):
        remote = getattr(getattr(conn, "remote", None), "name", None) or getattr(
            conn, "id", None
        )
        if remote:
            breakdown["replication"]["array_connections"][remote] = _replication_perf(
                conn
            )
    for target in _perf_items(blade.get_targets_performance_replication()):
        breakdown["replication"]["targets"][target.name] = _replication_perf(target)
    for fsys in _perf_items(blade.get_file_systems_performance()):
        breakdown["filesystems"][fsys.name] = _perf_fields(fsys, PERF_FIELDS)
    for bucket in _perf_items(blade.get_buckets_performance()):
        breakdown["buckets"][bucket.name] = _perf_fields(bucket, PERF_FIELDS)
    for bucket in _perf_items(blade.get_buckets_s3_specific_performance()):
        breakdown["buckets"].setdefault(bucket.name, {})["s3"] = _perf_fields(
            bucket, S3_OPS_FIELDS
        )
    return breakdown


def generate_clients_dict(blade, api_version):
    """Per-client performance for the opt-in clients subset.

    Clients are reported as IP:PORT and each listing is capped at
    CLIENTS_PERF_LIMIT entries. The protocol selector and the S3-specific
    listing need REST 2.18; older arrays get the S3 keys back empty.
    """
    clients_info = {"nfs": {}, "s3": {}, "s3_ops": {}}
    for client in _perf_items(
        blade.get_arrays_clients_performance(limit=CLIENTS_PERF_LIMIT)
    ):
        clients_info["nfs"][client.name] = _perf_fields(client, PERF_FIELDS)
    if LooseVersion(CLIENTS_S3_API_VERSION) <= LooseVersion(api_version):
        for client in _perf_items(
            blade.get_arrays_clients_performance(
                protocol="s3", limit=CLIENTS_PERF_LIMIT
            )
        ):
            clients_info["s3"][client.name] = _perf_fields(client, PERF_FIELDS)
        for client in _perf_items(
            blade.get_arrays_clients_s3_specific_performance(limit=CLIENTS_PERF_LIMIT)
        ):
            clients_info["s3_ops"][client.name] = _perf_fields(client, S3_OPS_FIELDS)
    return clients_info


def generate_perf_dict(blade):
    perf_info = {}
    total_perf = list(blade.get_arrays_performance().items)[0]
    http_perf = list(blade.get_arrays_performance(protocol="http").items)[0]
    s3_perf = list(blade.get_arrays_performance(protocol="s3").items)[0]
    nfs_perf = list(blade.get_arrays_performance(protocol="nfs").items)[0]
    perf_info["aggregate"] = {
        "bytes_per_op": total_perf.bytes_per_op,
        "bytes_per_read": total_perf.bytes_per_read,
        "bytes_per_write": total_perf.bytes_per_write,
        "read_bytes_per_sec": total_perf.read_bytes_per_sec,
        "reads_per_sec": total_perf.reads_per_sec,
        "usec_per_other_op": total_perf.usec_per_other_op,
        "usec_per_read_op": total_perf.usec_per_read_op,
        "usec_per_write_op": total_perf.usec_per_write_op,
        "write_bytes_per_sec": total_perf.write_bytes_per_sec,
        "writes_per_sec": total_perf.writes_per_sec,
    }
    perf_info["http"] = {
        "bytes_per_op": http_perf.bytes_per_op,
        "bytes_per_read": http_perf.bytes_per_read,
        "bytes_per_write": http_perf.bytes_per_write,
        "read_bytes_per_sec": http_perf.read_bytes_per_sec,
        "reads_per_sec": http_perf.reads_per_sec,
        "usec_per_other_op": http_perf.usec_per_other_op,
        "usec_per_read_op": http_perf.usec_per_read_op,
        "usec_per_write_op": http_perf.usec_per_write_op,
        "write_bytes_per_sec": http_perf.write_bytes_per_sec,
        "writes_per_sec": http_perf.writes_per_sec,
    }
    perf_info["s3"] = {
        "bytes_per_op": s3_perf.bytes_per_op,
        "bytes_per_read": s3_perf.bytes_per_read,
        "bytes_per_write": s3_perf.bytes_per_write,
        "read_bytes_per_sec": s3_perf.read_bytes_per_sec,
        "reads_per_sec": s3_perf.reads_per_sec,
        "usec_per_other_op": s3_perf.usec_per_other_op,
        "usec_per_read_op": s3_perf.usec_per_read_op,
        "usec_per_write_op": s3_perf.usec_per_write_op,
        "write_bytes_per_sec": s3_perf.write_bytes_per_sec,
        "writes_per_sec": s3_perf.writes_per_sec,
    }
    perf_info["nfs"] = {
        "bytes_per_op": nfs_perf.bytes_per_op,
        "bytes_per_read": nfs_perf.bytes_per_read,
        "bytes_per_write": nfs_perf.bytes_per_write,
        "read_bytes_per_sec": nfs_perf.read_bytes_per_sec,
        "reads_per_sec": nfs_perf.reads_per_sec,
        "usec_per_other_op": nfs_perf.usec_per_other_op,
        "usec_per_read_op": nfs_perf.usec_per_read_op,
        "usec_per_write_op": nfs_perf.usec_per_write_op,
        "write_bytes_per_sec": nfs_perf.write_bytes_per_sec,
        "writes_per_sec": nfs_perf.writes_per_sec,
    }
    if blade.get_array_connections_performance_replication().total_item_count > 0:
        file_repl_perf = list(
            blade.get_array_connections_performance_replication(
                type="file-system"
            ).items
        )[0]
        obj_repl_perf = list(
            blade.get_array_connections_performance_replication(
                type="object-store"
            ).items
        )[0]
        perf_info["file_replication"] = {
            "received_bytes_per_sec": getattr(
                file_repl_perf.periodic, "received_bytes_per_sec", None
            ),
            "transmitted_bytes_per_sec": getattr(
                file_repl_perf.periodic, "transmitted_bytes_per_sec", None
            ),
        }
        perf_info["object_replication"] = {
            "received_bytes_per_sec": getattr(
                obj_repl_perf.periodic, "received_bytes_per_sec", None
            ),
            "transmitted_bytes_per_sec": getattr(
                obj_repl_perf.periodic, "transmitted_bytes_per_sec", None
            ),
        }
    perf_info.update(generate_perf_breakdown_dict(blade))
    return perf_info


def generate_quota_settings_dict(blade):
    """Legacy user and group quota notification settings (/quotas/settings).

    Keyed by the settings object name (a single object named management).
    The array omits contact from the response while it is unset.
    """
    quota_settings = {}
    res = blade.get_quotas_settings()
    if res.status_code != 200:
        return quota_settings
    for settings in list(res.items):
        quota_settings[settings.name] = {
            "contact": getattr(settings, "contact", None),
            "direct_notifications_enabled": getattr(
                settings, "direct_notifications_enabled", None
            ),
        }
    return quota_settings


def generate_config_dict(blade):
    config_info = {}
    api_version = get_rest_api_version(blade)
    config_info["dns"] = {}
    dns_configs = list(blade.get_dns().items)
    for config in dns_configs:
        config_info["dns"][config.name] = {
            "nameservers": config.nameservers,
            "domain": config.domain,
            "services": getattr(config, "services", None),
            "ca_certificate": getattr(
                getattr(config, "ca_certificate", None), "name", None
            ),
            "ca_certificate_group": getattr(
                getattr(config, "ca_certificate_group", None), "name", None
            ),
        }
        if hasattr(config, "sources"):
            # sources is a list of references (at most one), not a reference
            sources = getattr(config, "sources", None)
            if isinstance(sources, list):
                source = getattr(sources[0], "name", None) if sources else None
            else:
                source = getattr(sources, "name", None)
            config_info["dns"][config.name]["source"] = source
    smtp_config = list(blade.get_smtp_servers().items)
    config_info["smtp"] = {}
    for config in smtp_config:
        config_info["smtp"][config.name] = {
            "relay_host": getattr(config, "relay_host", None),
            "sender_domain": getattr(config, "sender_domain", None),
            "encryption_mode": getattr(config, "encryption_mode", None),
        }
    config_info["quota_settings"] = generate_quota_settings_dict(blade)
    alert_config = list(blade.get_alert_watchers().items)
    config_info["alert_watchers"] = {}
    for config in alert_config:
        config_info["alert_watchers"][config.name] = {
            "enabled": config.enabled,
            "minimum_notification_severity": config.minimum_notification_severity,
        }
    directory_services = list(blade.get_directory_services().items)
    for ds_service in directory_services:
        if ds_service.name in {"management", "nfs", "smb"}:
            key = f"{ds_service.name}_directory_service"
            config_info[key] = {
                "base_dn": ds_service.base_dn,
                "bind_user": ds_service.bind_user,
                "ca_certificate": ds_service.ca_certificate.name,
                "ca_certificate_group": ds_service.ca_certificate_group.name,
                "enabled": ds_service.enabled,
                "management": {
                    "user_login_attribute": ds_service.management.user_login_attribute,
                    "user_object_class": ds_service.management.user_object_class,
                },
                "nis_servers": ds_service.nfs.nis_servers,
                "nis_domains": ds_service.nfs.nis_domains,
                "services": ds_service.services,
                "join_ou": ds_service.smb.join_ou,
                "uris": ds_service.uris,
            }
    # Forward backwards compatability
    config_info["array_management"] = config_info["management_directory_service"]

    config_info["directory_service_roles"] = generate_directory_service_roles_dict(
        blade, api_version
    )
    config_info["ntp"] = list(blade.get_arrays().items)[0].ntp_servers
    certs = list(blade.get_certificates().items)
    config_info["ssl_certs"] = {}
    for cert in certs:
        cert_name = cert.name
        valid_from = time.strftime(
            "%a, %d %b %Y %H:%M:%S %Z",
            time.localtime(cert.valid_from / 1000),
        )
        valid_to = time.strftime(
            "%a, %d %b %Y %H:%M:%S %Z",
            time.localtime(cert.valid_to / 1000),
        )
        config_info["ssl_certs"][cert_name] = {
            "certificate": getattr(cert, "certificate", None),
            "certificate_type": getattr(cert, "certificate_type", None),
            "common_name": getattr(cert, "common_name", None),
            "country": getattr(cert, "country", None),
            "email": getattr(cert, "email", None),
            "intermediate_certificate": getattr(cert, "intermediate_certificate", None),
            "issued_by": getattr(cert, "issued_by", None),
            "issued_to": getattr(cert, "issued_to", None),
            "key_size": getattr(cert, "key_size", None),
            "locality": getattr(cert, "locality", None),
            "organization": getattr(cert, "organization", None),
            "organizational_unit": getattr(cert, "organizational_unit", None),
            "state": getattr(cert, "state", None),
            "status": getattr(cert, "status", None),
            "subject_alternative_names": getattr(
                cert, "subject_alternative_names", None
            ),
            "valid_from": valid_from,
            "valid_to": valid_to,
        }
    crt_grps = list(blade.get_certificate_groups().items)
    config_info["certificate_groups"] = []
    for crt_grp in crt_grps:
        config_info["certificate_groups"].append(crt_grp.name)
    config_info["syslog_servers"] = {}
    syslog_servers = list(blade.get_syslog_servers().items)
    for server in syslog_servers:
        server_name = server.name
        config_info["syslog_servers"][server_name] = {
            "uri": server.uri,
            "services": getattr(server, "services", None),
        }
    config_info["syslog_settings"] = {}
    for settings in list(blade.get_syslog_servers_settings().items):
        config_info["syslog_settings"][settings.name] = {
            "ca_certificate": _reference_name(settings, "ca_certificate"),
            "ca_certificate_group": _reference_name(settings, "ca_certificate_group"),
        }
    snmp_agents = list(blade.get_snmp_agents().items)
    config_info["snmp_agents"] = {}
    for agent in snmp_agents:
        agent_name = agent.name
        config_info["snmp_agents"][agent_name] = {
            "version": agent.version,
            "engine_id": agent.engine_id,
        }
        if config_info["snmp_agents"][agent_name]["version"] == "v3":
            config_info["snmp_agents"][agent_name]["auth_protocol"] = getattr(
                agent.v3, "auth_protocol", None
            )
            config_info["snmp_agents"][agent_name]["privacy_protocol"] = getattr(
                agent.v3, "privacy_protocol", None
            )
            config_info["snmp_agents"][agent_name]["user"] = getattr(
                agent.v3, "user", None
            )
    config_info["snmp_managers"] = {}
    snmp_managers = list(blade.get_snmp_managers().items)
    for manager in snmp_managers:
        mgr_name = manager.name
        config_info["snmp_managers"][mgr_name] = {
            "version": manager.version,
            "host": manager.host,
            "notification": manager.notification,
        }
        if config_info["snmp_managers"][mgr_name]["version"] == "v3":
            config_info["snmp_managers"][mgr_name]["auth_protocol"] = getattr(
                manager.v3, "auth_protocol", None
            )
            config_info["snmp_managers"][mgr_name]["privacy_protocol"] = getattr(
                manager.v3, "privacy_protocol", None
            )
            config_info["snmp_managers"][mgr_name]["user"] = getattr(
                manager.v3, "user", None
            )
    if LooseVersion(KMIP_API_VERSION) <= LooseVersion(api_version):
        config_info["kmip"] = {}
        for kmip in list(blade.get_kmip().items):
            config_info["kmip"][kmip.name] = {
                "uris": getattr(kmip, "uris", None),
                "ca_certificate": getattr(
                    getattr(kmip, "ca_certificate", None), "name", None
                ),
                "ca_certificate_group": getattr(
                    getattr(kmip, "ca_certificate_group", None), "name", None
                ),
            }
    if LooseVersion(SMTP_ENCRYPT_API_VERSION) <= LooseVersion(api_version):
        config_info["saml2sso"] = {}
        saml2 = list(blade.get_sso_saml2_idps().items)
        if saml2:
            config_info["saml2sso"] = {
                "enabled": saml2[0].enabled,
                "array_url": saml2[0].array_url,
                "name": saml2[0].name,
                "prn": getattr(saml2[0], "prn", None),
                "services": getattr(saml2[0], "services", None),
                "binding": getattr(saml2[0], "binding", None),
                "trust_other_saml_sps_in_fleet": getattr(
                    getattr(saml2[0], "management", None),
                    "trust_other_saml_sps_in_fleet",
                    None,
                ),
                "idp": {
                    "url": getattr(saml2[0].idp, "url", None),
                    "entity_id": getattr(saml2[0].idp, "entity_id", None),
                    "encrypt_enabled": saml2[0].idp.encrypt_assertion_enabled,
                    "sign_enabled": saml2[0].idp.sign_request_enabled,
                    "metadata_url": saml2[0].idp.metadata_url,
                    "metadata_url_ca_certificate": getattr(
                        getattr(saml2[0].idp, "metadata_url_ca_certificate", None),
                        "name",
                        None,
                    ),
                    "metadata_url_ca_certificate_group": getattr(
                        getattr(
                            saml2[0].idp, "metadata_url_ca_certificate_group", None
                        ),
                        "name",
                        None,
                    ),
                    "verification_certificate": getattr(
                        getattr(saml2[0].idp, "verification_certificate", None),
                        "name",
                        None,
                    ),
                },
                "sp": {
                    "entity_id": getattr(saml2[0].sp, "entity_id", None),
                    "assertion_consumer_url": getattr(
                        saml2[0].sp, "assertion_consumer_url", None
                    ),
                    "metadata_url": getattr(saml2[0].sp, "metadata_url", None),
                    "decrypt_cred": getattr(
                        saml2[0].sp.decryption_credential, "name", None
                    ),
                    "sign_cred": getattr(saml2[0].sp.signing_credential, "name", None),
                },
            }
    if LooseVersion(OIDC_API_VERSION) <= LooseVersion(api_version):
        config_info["oidc_idps"] = generate_oidc_idps_dict(blade)
    return config_info


def generate_oidc_idps_dict(blade):
    """OIDC identity providers keyed by name (an array may hold several)."""
    idps_info = {}
    for idp in list(blade.get_sso_oidc_idps().items):
        idp_cfg = getattr(idp, "idp", None)
        idps_info[idp.name] = {
            "enabled": getattr(idp, "enabled", None),
            "prn": getattr(idp, "prn", None),
            "services": list(getattr(idp, "services", None) or []),
            "provider_url": getattr(idp_cfg, "provider_url", None),
            "ca_certificate": getattr(
                getattr(idp_cfg, "provider_url_ca_certificate", None), "name", None
            ),
            "ca_certificate_group": getattr(
                getattr(idp_cfg, "provider_url_ca_certificate_group", None),
                "name",
                None,
            ),
        }
    return idps_info


def generate_subnet_dict(blade):
    sub_info = {}
    subnets = list(blade.get_subnets().items)
    for sub in subnets:
        sub_name = sub.name
        if sub.enabled:
            sub_info[sub_name] = {
                "gateway": sub.gateway,
                "mtu": sub.mtu,
                "vlan": sub.vlan,
                "prefix": sub.prefix,
                "services": sub.services,
            }
            # Subnets on an array in Layer 3 (BGP) mode have no LAG
            sub_info[sub_name]["lag"] = getattr(
                sub.link_aggregation_group, "name", None
            )
            sub_info[sub_name]["interfaces"] = []
            for iface in sub.interfaces or []:
                sub_info[sub_name]["interfaces"].append({"name": iface.name})
    return sub_info


def generate_lag_dict(blade):
    lag_info = {}
    res = blade.get_link_aggregation_groups()
    if res.status_code != 200:
        # An array in Layer 3 (BGP) mode has no link aggregation groups
        # and the endpoint returns an error rather than an empty list
        return lag_info
    for groupcnt in list(res.items):
        lag_name = groupcnt.name
        lag_info[lag_name] = {
            "lag_speed": groupcnt.lag_speed,
            "port_speed": groupcnt.port_speed,
            "mac_address": getattr(groupcnt, "mac_address", None),
            "status": groupcnt.status,
        }
        lag_info[lag_name]["ports"] = []
        for port in groupcnt.ports or []:
            lag_info[lag_name]["ports"].append({"name": port.name})
    return lag_info


def generate_admin_dict(blade):
    """Return the array's administrators

    ``role`` is set only when the admin holds exactly one management access
    policy that corresponds to a legacy role of the same name; it is null for
    an admin with no, several, or a custom policy, so it is read through
    getattr. The policy names are reported from REST 2.19, where the array
    exposes them.
    """
    admin_info = {}
    api_version = get_rest_api_version(blade)
    report_policies = LooseVersion(MAP_API_VERSION) <= LooseVersion(api_version)
    admins = list(blade.get_admins().items)
    for admin in admins:
        admin_name = admin.name
        admin_info[admin_name] = {
            "public_key": getattr(admin, "public_key", None),
            "local": getattr(admin, "is_local", None),
            "role": getattr(getattr(admin, "role", None), "name", None),
            "locked": getattr(admin, "locked", None),
            "lockout_remaining": getattr(admin, "lockout_remaining", None),
        }
        if report_policies:
            admin_info[admin_name]["management_access_policies"] = _reference_names(
                getattr(admin, "management_access_policies", None)
            )
        if hasattr(admin.api_token, "expires_at"):
            if admin.api_token.expires_at:
                admin_info[admin_name]["token_expires"] = datetime.fromtimestamp(
                    admin.api_token.expires_at / 1000
                ).strftime("%Y-%m-%d %H:%M:%S")
        else:
            admin_info[admin_name]["token_expires"] = None
        if hasattr(admin.api_token, "created_at"):
            if admin.api_token.created_at:
                admin_info[admin_name]["token_created"] = datetime.fromtimestamp(
                    admin.api_token.created_at / 1000
                ).strftime("%Y-%m-%d %H:%M:%S")
        else:
            admin_info[admin_name]["token_created"] = None
    return admin_info


def generate_targets_dict(blade):
    targets_info = {}
    targets = list(blade.get_targets().items)
    for target in targets:
        target_name = target.name
        targets_info[target_name] = {
            "address": target.address,
            "status": target.status,
            "status_details": target.status_details,
            "ca_certificate_group": getattr(
                getattr(target, "ca_certificate_group", None), "name", None
            ),
        }
    return targets_info


def generate_remote_creds_dict(blade):
    remote_creds_info = {}
    remote_creds = list(blade.get_object_store_remote_credentials().items)
    for remote_cred in remote_creds:
        cred_name = remote_cred.name
        remote_creds_info[cred_name] = {
            "access_key": remote_cred.access_key_id,
            "remote_array": remote_cred.remote.name,
            "secret_access_key": remote_cred.secret_access_key,
        }
    return remote_creds_info


def generate_file_repl_dict(blade):
    file_repl_info = {}
    file_links = list(blade.get_file_system_replica_links().items)
    for file_link in file_links:
        fs_name = file_link.local_file_system.name
        file_repl_info[fs_name] = {
            "direction": file_link.direction,
            "link_type": file_link.link_type,
            "lag": file_link.lag,
            "status": file_link.status,
            # the SDK model calls this status_details; the key is kept for
            # backwards compatibility
            "status_detail": getattr(file_link, "status_details", None),
            "remote_fs": file_link.remote.name
            + ":"
            + file_link.remote_file_system.name,
            "recovery_point": file_link.recovery_point,
        }
        file_repl_info[fs_name]["policies"] = []
        for policy_cnt in file_link.policies:
            file_repl_info[fs_name]["policies"].append(policy_cnt.display_name)
    return file_repl_info


def generate_bucket_repl_dict(blade):
    bucket_repl_info = {}
    bucket_links = list(blade.get_bucket_replica_links().items)
    for bucket_link in bucket_links:
        bucket_name = bucket_link.local_bucket.name
        bucket_repl_info[bucket_name] = {
            "direction": bucket_link.direction,
            "lag": bucket_link.lag,
            "paused": bucket_link.paused,
            "status": bucket_link.status,
            "status_details": bucket_link.status_details,
            "remote_bucket": bucket_link.remote_bucket.name,
            "remote_array": bucket_link.remote.name,
            "remote_credentials": bucket_link.remote_credentials.name,
            "recovery_point": bucket_link.recovery_point,
            "object_backlog": {
                "bytes_count": bucket_link.object_backlog.bytes_count,
                "delete_ops_count": bucket_link.object_backlog.delete_ops_count,
                "other_ops_count": bucket_link.object_backlog.other_ops_count,
                "put_ops_count": bucket_link.object_backlog.put_ops_count,
            },
            "cascading_enabled": bucket_link.cascading_enabled,
        }
    return bucket_repl_info


def generate_network_dict(blade):
    net_info = {}
    ports = list(blade.get_network_interfaces().items)
    for port in ports:
        int_name = port.name
        # attached_servers is a list of references on the API even though an
        # interface carries at most one server; the subnet comes back as a
        # plain dict on current SDKs and as a reference on older ones.
        attached = getattr(port, "attached_servers", None) or []
        if not isinstance(attached, list):
            attached = []
        attached_names = [getattr(srv, "name", None) for srv in attached]
        subnet = getattr(port, "subnet", None)
        if isinstance(subnet, dict):
            subnet_name = subnet.get("name")
        else:
            subnet_name = getattr(subnet, "name", None)
        # realms (REST 2.19) and rdma_enabled (REST 2.28) are absent from
        # the interface model on older arrays
        realms = getattr(port, "realms", None) or []
        if not isinstance(realms, list):
            realms = []
        realm_names = [
            (
                realm.get("name")
                if isinstance(realm, dict)
                else getattr(realm, "name", None)
            )
            for realm in realms
        ]
        net_info[int_name] = {
            "type": getattr(port, "type", None),
            "mtu": getattr(port, "mtu", None),
            "vlan": getattr(port, "vlan", None),
            "address": getattr(port, "address", None),
            "services": getattr(port, "services", None),
            "gateway": getattr(port, "gateway", None),
            "netmask": getattr(port, "netmask", None),
            "server": attached_names[0] if attached_names else None,
            "attached_servers": attached_names,
            "subnet": subnet_name,
            "enabled": port.enabled,
            "rdma_enabled": getattr(port, "rdma_enabled", None),
            "realms": realm_names,
        }
    return net_info


def generate_capacity_dict(blade):
    capacity_info = {}
    total_cap = list(blade.get_arrays_space().items)[0]
    file_cap = list(blade.get_arrays_space(type="file-system").items)[0]
    object_cap = list(blade.get_arrays_space(type="object-store").items)[0]
    capacity_info["total"] = total_cap.capacity
    capacity_info["aggregate"] = {
        "data_reduction": total_cap.space.data_reduction,
        "snapshots": total_cap.space.snapshots,
        "total_physical": total_cap.space.total_physical,
        "unique": total_cap.space.unique,
        "virtual": total_cap.space.virtual,
        "total_provisioned": total_cap.space.total_provisioned,
        "available_provisioned": total_cap.space.available_provisioned,
        "available_ratio": total_cap.space.available_ratio,
        "destroyed": total_cap.space.destroyed,
        "destroyed_virtual": total_cap.space.destroyed_virtual,
        "shared": getattr(total_cap.space, "shared", None),
    }
    capacity_info["file-system"] = {
        "data_reduction": file_cap.space.data_reduction,
        "snapshots": file_cap.space.snapshots,
        "total_physical": file_cap.space.total_physical,
        "unique": file_cap.space.unique,
        "virtual": file_cap.space.virtual,
        "total_provisioned": total_cap.space.total_provisioned,
        "available_provisioned": total_cap.space.available_provisioned,
        "available_ratio": total_cap.space.available_ratio,
        "destroyed": total_cap.space.destroyed,
        "destroyed_virtual": total_cap.space.destroyed_virtual,
        "shared": getattr(total_cap.space, "shared", None),
    }
    capacity_info["object-store"] = {
        "data_reduction": object_cap.space.data_reduction,
        "snapshots": object_cap.space.snapshots,
        "total_physical": object_cap.space.total_physical,
        "unique": object_cap.space.unique,
        "virtual": file_cap.space.virtual,
        "total_provisioned": total_cap.space.total_provisioned,
        "available_provisioned": total_cap.space.available_provisioned,
        "available_ratio": total_cap.space.available_ratio,
        "destroyed": total_cap.space.destroyed,
        "destroyed_virtual": total_cap.space.destroyed_virtual,
        "shared": getattr(total_cap.space, "shared", None),
    }

    return capacity_info


def generate_snap_dict(blade):
    snap_info = {}
    snaps = list(blade.get_file_system_snapshots().items)
    api_version = get_rest_api_version(blade)
    for snap in snaps:
        snapshot = snap.name
        snap_info[snapshot] = {
            "destroyed": snap.destroyed,
            "source": snap.source.location.name,
            "suffix": snap.suffix,
            "created": datetime.fromtimestamp(
                snap.created / 1000,
                tz=timezone.utc,
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "time_remaining": getattr(snap, "time_remaining", None),
            "policy": getattr(getattr(snap, "policy", None), "name", None),
            "owner": snap.owner.name,
            "owner_destroyed": snap.owner_destroyed,
            "source_display_name": snap.source.display_name,
            "source_is_local": snap.source.is_local,
            "source_location": snap.source.location.name,
            "policies": [],
        }
        if LooseVersion(PUBLIC_API_VERSION) <= LooseVersion(api_version):
            if hasattr(snap, "policies"):
                for policy in snap.policies:
                    snap_info[snapshot]["policies"].append(
                        {
                            "name": policy.name,
                            "location": policy.location.name,
                        }
                    )
    return snap_info


def generate_snap_transfer_dict(blade):
    snap_transfer_info = {}
    snap_transfers = list(blade.get_file_system_snapshots_transfer().items)
    for snap_transfer in snap_transfers:
        transfer = snap_transfer.name
        snap_transfer_info[transfer] = {
            "completed": snap_transfer.completed,
            "data_transferred": snap_transfer.data_transferred,
            "progress": snap_transfer.progress,
            "direction": snap_transfer.direction,
            "remote": snap_transfer.remote.name,
            "remote_snapshot": snap_transfer.remote_snapshot.name,
            "started": snap_transfer.started,
            "status": snap_transfer.status,
        }
    return snap_transfer_info


def generate_fs_repl_transfer_dict(blade):
    """Transfer status of file system replica links.

    Keyed by snapshot name and then by remote array, so a snapshot that
    replicates to several arrays (fan-out) keeps one entry per transfer.
    """
    fs_transfer_info = {}
    res = blade.get_file_system_replica_links_transfer()
    if res.status_code != 200:
        return fs_transfer_info
    for transfer in list(res.items):
        remote = getattr(getattr(transfer, "remote", None), "name", None)
        fs_transfer_info.setdefault(transfer.name, {})[remote] = {
            "completed": transfer.completed,
            "data_transferred": transfer.data_transferred,
            "progress": transfer.progress,
            "direction": transfer.direction,
            "local_snapshot": getattr(
                getattr(transfer, "local_snapshot", None), "name", None
            ),
            "remote": remote,
            "remote_snapshot": getattr(
                getattr(transfer, "remote_snapshot", None), "name", None
            ),
            "started": transfer.started,
            "status": transfer.status,
        }
    return fs_transfer_info


def _connection_paths_by_remote(blade):
    """Group the GET array-connections/path rows by remote array name.

    One connection has several paths (one per replication address and
    port). ``status_details`` is only meaningful when a path is not
    connected; the array returns it empty or omits it otherwise, so both
    shapes are normalised to None.
    """
    paths = {}
    for path in blade.get_array_connections_path().items:
        remote_name = getattr(getattr(path, "remote", None), "name", None)
        paths.setdefault(remote_name, []).append(
            {
                "source": getattr(path, "source", None),
                "destination": getattr(path, "destination", None),
                "status": getattr(path, "status", None),
                "status_details": getattr(path, "status_details", None) or None,
                "type": getattr(path, "type", None),
            }
        )
    return paths


def generate_array_conn_dict(blade):
    array_conn_info = {}
    arrays = list(blade.get_array_connections().items)
    for array in arrays:
        # Keep the connection object intact: rebinding `array` to the remote
        # name here made every attribute read below fail with AttributeError.
        remote_name = array.remote.name
        array_conn_info[remote_name] = {
            "encrypted": array.encrypted,
            "replication_addresses": array.replication_addresses,
            "management_address": array.management_address,
            "status": array.status,
            "version": array.version,
            "ca_certificate_group": getattr(
                getattr(array, "ca_certificate_group", None), "name", None
            ),
            "throttle": {
                "default_limit": _bytes_to_human(
                    getattr(array.throttle, "default_limit", None)
                ),
                "window_limit": _bytes_to_human(
                    getattr(array.throttle, "window_limit", None)
                ),
                "window_start": (
                    milliseconds_to_time(getattr(array.throttle.window, "start", None))
                    if getattr(array.throttle.window, "start", None)
                    else None
                ),
                "window_end": (
                    milliseconds_to_time(getattr(array.throttle.window, "end", None))
                    if getattr(array.throttle.window, "end", None)
                    else None
                ),
            },
        }
    # Per-path status of each connection (REST 2.0), the first thing to
    # check when replication or fleet management misbehaves.
    if array_conn_info:
        paths = _connection_paths_by_remote(blade)
        for remote_name in array_conn_info:
            array_conn_info[remote_name]["connection_paths"] = paths.get(
                remote_name, []
            )
    return array_conn_info


def generate_policies_dict(blade):
    policies_info = {}
    policies = list(blade.get_policies().items)
    for policy in policies:
        policy_name = policy.name
        policies_info[policy_name] = {
            "enabled": policy.enabled,
            "retention_lock": getattr(policy, "retention_lock", None),
            "policy_type": policy.policy_type,
            "rules": {},
        }
        rules = getattr(policy, "rules", None)
        if rules:
            policies_info[policy_name]["rules"] = {
                "at": getattr(rules[0], "at", None),
                "every": getattr(rules[0], "every", None),
                "keep_for": getattr(rules[0], "keep_for", None),
                "time_zone": getattr(rules[0], "time_zone", None),
            }
    return policies_info


def _policy_members_by_name(blade, policies):
    """Map policy name -> members from one GET policies-all/members call.

    The endpoint covers every policy type (snapshot, access, telemetry,
    network, TLS ...) in a single response. Rows are attributed by policy
    id first, so a realm-scoped policy that shares its name with an
    array-level one keeps its own members. The server refuses responses
    over 150,000 rows, which an info read does not approach.
    """
    names_by_id = {policy.id: policy.name for policy in policies}
    members = {}
    for row in blade.get_policies_all_members().items:
        policy_ref = getattr(row, "policy", None)
        policy_name = names_by_id.get(
            getattr(policy_ref, "id", None), getattr(policy_ref, "name", None)
        )
        member_ref = getattr(row, "member", None)
        member = {
            "name": getattr(member_ref, "name", None),
            "resource_type": getattr(member_ref, "resource_type", None),
        }
        if member["resource_type"] == "file-system-replica-links":
            link = getattr(row, "link", None)
            member["link"] = {
                "local_file_system": getattr(
                    getattr(link, "local_file_system", None), "name", None
                ),
                "remote": getattr(getattr(link, "remote", None), "name", None),
                "remote_file_system": getattr(
                    getattr(link, "remote_file_system", None), "name", None
                ),
            }
        members.setdefault(policy_name, []).append(member)
    return members


def generate_all_policies_dict(blade):
    policies_info = {}
    policies = list(blade.get_policies_all().items)
    for policy in policies:
        policy_name = policy.name
        policies_info[policy_name] = {
            "id": policy.id,
            "enabled": policy.enabled,
            "is_local": getattr(policy, "is_local", None),
            "location": getattr(getattr(policy, "location", None), "name", None),
            "policy_type": policy.policy_type,
        }
    if LooseVersion(POLICY_MEMBERS_API_VERSION) <= LooseVersion(
        get_rest_api_version(blade)
    ):
        members = _policy_members_by_name(blade, policies)
        for policy_name in policies_info:
            policies_info[policy_name]["members"] = members.get(policy_name, [])
    return policies_info


def generate_bucket_dict(blade):
    bucket_info = {}
    buckets = list(blade.get_buckets().items)
    for bucket in buckets:
        bucket_name = bucket.name
        bucket_info[bucket_name] = {
            "versioning": bucket.versioning,
            "bucket_type": getattr(bucket, "bucket_type", None),
            "object_count": bucket.object_count,
            "id": bucket.id,
            "account_name": bucket.account.name,
            "data_reduction": getattr(bucket.space, "data_reduction", None),
            "snapshot_space": bucket.space.snapshots,
            "total_physical_space": bucket.space.total_physical,
            "unique_space": bucket.space.unique,
            "virtual_space": bucket.space.virtual,
            "total_provisioned_space": getattr(bucket.space, "total_provisioned", None),
            "available_provisioned_space": getattr(
                bucket.space, "available_provisioned", None
            ),
            "available_ratio": getattr(bucket.space, "available_ratio", None),
            "destroyed_space": getattr(bucket.space, "destroyed", None),
            "destroyed_virtual_space": getattr(bucket.space, "destroyed_virtual", None),
            "created": bucket.created,
            "destroyed": bucket.destroyed,
            "time_remaining": getattr(bucket, "time_remaining", None),
            "time_remaining_status": getattr(bucket, "time_remaining_status", None),
            "retention_lock": bucket.retention_lock,
            "quota_limit": bucket.quota_limit,
            "object_lock_config": {
                "enabled": bucket.object_lock_config.enabled,
                "freeze_locked_objects": bucket.object_lock_config.freeze_locked_objects,
                "default_retention": getattr(
                    bucket.object_lock_config, "default_retention", None
                ),
                "default_retention_mode": getattr(
                    bucket.object_lock_config,
                    "default_retention_mode",
                    None,
                ),
            },
            "eradication_config": {
                "eradication_delay": getattr(
                    bucket.eradication_config, "eradication_delay", None
                ),
                "eradication_mode": getattr(
                    bucket.eradication_config, "eradication_mode", None
                ),
                "manual_eradication": bucket.eradication_config.manual_eradication,
            },
            "public_status": getattr(bucket, "public_status", None),
            "public_access_config": {
                "block_new_public_policies": getattr(
                    getattr(bucket, "public_access_config", None),
                    "block_new_public_policies",
                    None,
                ),
                "block_public_access": getattr(
                    getattr(bucket, "public_access_config", None),
                    "block_public_access",
                    None,
                ),
            },
            "lifecycle_rules": {},
        }
        if not bucket.destroyed:
            all_rules = list(blade.get_lifecycle_rules(bucket_ids=[bucket.id]).items)
            for rule in all_rules:
                bucket_name = rule.bucket.name
                rule_id = rule.rule_id
                if rule.keep_previous_version_for:
                    keep_previous_version_for = int(
                        rule.keep_previous_version_for / 86400000
                    )
                else:
                    keep_previous_version_for = None
                if rule.keep_current_version_for:
                    keep_current_version_for = int(
                        rule.keep_current_version_for / 86400000
                    )
                else:
                    keep_current_version_for = None
                if rule.abort_incomplete_multipart_uploads_after:
                    abort_incomplete_multipart_uploads_after = int(
                        rule.abort_incomplete_multipart_uploads_after / 86400000
                    )
                else:
                    abort_incomplete_multipart_uploads_after = None
                if rule.keep_current_version_until:
                    keep_current_version_until = datetime.fromtimestamp(
                        rule.keep_current_version_until / 1000
                    ).strftime("%Y-%m-%d")
                else:
                    keep_current_version_until = None
                bucket_info[bucket_name]["lifecycle_rules"][rule_id] = {
                    "keep_previous_version_for (days)": keep_previous_version_for,
                    "keep_current_version_for (days)": keep_current_version_for,
                    "keep_current_version_until": keep_current_version_until,
                    "prefix": rule.prefix,
                    "enabled": rule.enabled,
                    "abort_incomplete_multipart_uploads_after (days)": abort_incomplete_multipart_uploads_after,
                    "cleanup_expired_object_delete_marker": rule.cleanup_expired_object_delete_marker,
                }

    return bucket_info


def generate_kerb_dict(blade):
    kerb_info = {}

    for keytab in blade.get_keytabs().items:
        prefix = keytab.prefix
        suffix = keytab.suffix

        if prefix not in kerb_info:
            kerb_info[prefix] = {}

        kerb_info[prefix][suffix] = {
            "fqdn": keytab.fqdn,
            "kvno": keytab.kvno,
            "principal": keytab.principal,
            "realm": keytab.realm,
            "encryption_type": keytab.encryption_type,
            "server": getattr(getattr(keytab, "server", None), "name", None),
            "source": getattr(getattr(keytab, "source", None), "name", None),
        }

    return kerb_info


def generate_ad_dict(blade):
    ad_info = {}

    active_directory = blade.get_active_directory()
    if active_directory.total_item_count == 0:
        return ad_info

    for ad in active_directory.items:
        ad_info[ad.name] = {
            "computer": ad.computer_name,
            "domain": ad.domain,
            "directory_servers": ad.directory_servers,
            "kerberos_servers": ad.kerberos_servers,
            "service_principals": ad.service_principal_names,
            "join_ou": ad.join_ou,
            "encryption_types": ad.encryption_types,
            "global_catalog_servers": getattr(ad, "global_catalog_servers", None),
            "server": getattr(getattr(ad, "server", None), "name", None),
            "ca_certificate": getattr(
                getattr(ad, "ca_certificate", None), "name", None
            ),
            "ca_certificate_group": getattr(
                getattr(ad, "ca_certificate_group", None), "name", None
            ),
        }

    return ad_info


def generate_bucket_access_policies_dict(blade):
    policies_info = {}

    for bucket in blade.get_buckets().items:
        res = blade.get_buckets_bucket_access_policies(bucket_names=[bucket.name])

        if res.status_code == 200 and res.total_item_count != 0:
            for policy in res.items:
                policies_info[policy.name] = {
                    # BucketAccessPolicy has no description field, unlike the
                    # object store access policy reported further down.
                    "description": getattr(policy, "description", None),
                    "enabled": policy.enabled,
                    "local": policy.is_local,
                    "rules": [],
                }

                for rule in policy.rules:
                    policies_info[policy.name]["rules"].append(
                        {
                            "actions": rule.actions,
                            "resources": rule.resources,
                            "all_principals": rule.principals.all,
                            "effect": rule.effect,
                            "name": rule.name,
                        }
                    )

    return policies_info


def generate_bucket_cross_object_policies_dict(blade):
    policies_info = {}

    for bucket in blade.get_buckets().items:
        res = blade.get_buckets_cross_origin_resource_sharing_policies(
            bucket_names=[bucket.name]
        )
        if res.status_code != 200:
            continue

        for policy in res.items:
            # The allowed_* lists live on the rules, not on the policy.
            policies_info[policy.name] = {
                "enabled": getattr(policy, "enabled", None),
                "local": getattr(policy, "is_local", None),
                "rules": [],
            }
            rules = blade.get_buckets_cross_origin_resource_sharing_policies_rules(
                policy_names=[policy.name]
            )
            if rules.status_code != 200:
                continue
            for rule in rules.items:
                policies_info[policy.name]["rules"].append(
                    {
                        "name": rule.name,
                        "allowed_headers": getattr(rule, "allowed_headers", None),
                        "allowed_methods": getattr(rule, "allowed_methods", None),
                        "allowed_origins": getattr(rule, "allowed_origins", None),
                    }
                )

    return policies_info


def generate_object_store_access_policies_dict(blade):
    policies_info = {}

    for policy in blade.get_object_store_access_policies().items:
        policy_name = policy.name
        policies_info[policy_name] = {
            "ARN": policy.arn,
            "description": policy.description,
            "enabled": policy.enabled,
            "local": policy.is_local,
            "rules": [],
        }

        for rule in policy.rules:
            policies_info[policy_name]["rules"].append(
                {
                    "actions": rule.actions,
                    "conditions": {
                        "source_ips": rule.conditions.source_ips,
                        "s3_delimiters": rule.conditions.s3_delimiters,
                        "s3_prefixes": rule.conditions.s3_prefixes,
                    },
                    "effect": rule.effect,
                    "name": rule.name,
                }
            )

    return policies_info


def generate_nfs_export_policies_dict(blade):
    policies_info = {}

    for policy in blade.get_nfs_export_policies().items:
        policy_name = policy.name
        policies_info[policy_name] = {
            "local": policy.is_local,
            "enabled": policy.enabled,
            "rules": [],
        }

        for rule in policy.rules:
            policies_info[policy_name]["rules"].append(
                {
                    "access": rule.access,
                    "anongid": rule.anongid,
                    "anonuid": rule.anonuid,
                    "atime": rule.atime,
                    "client": rule.client,
                    "fileid_32bit": rule.fileid_32bit,
                    "permission": rule.permission,
                    "secure": rule.secure,
                    "security": rule.security,
                    "index": rule.index,
                }
            )

    return policies_info


def generate_smb_client_policies_dict(blade):
    policies_info = {}

    for policy in blade.get_smb_client_policies().items:
        policy_name = policy.name
        policies_info[policy_name] = {
            "local": policy.is_local,
            "enabled": policy.enabled,
            "version": policy.version,
            "rules": [],
        }

        for rule in policy.rules:
            policies_info[policy_name]["rules"].append(
                {
                    "name": rule.name,
                    "change": getattr(rule, "change", None),
                    "full_control": getattr(rule, "full_control", None),
                    "principal": getattr(rule, "principal", None),
                    "read": getattr(rule, "read", None),
                    "client": getattr(rule, "client", None),
                    "index": getattr(rule, "index", None),
                    "policy_version": getattr(rule, "policy_version", None),
                    "encryption": getattr(rule, "encryption", None),
                    "permission": getattr(rule, "permission", None),
                }
            )

    return policies_info


def generate_smb_share_policies_dict(blade):
    policies_info = {}

    for policy in blade.get_smb_share_policies().items:
        policy_name = policy.name
        policies_info[policy_name] = {
            "local": getattr(policy, "is_local", None),
            "enabled": getattr(policy, "enabled", None),
            "rules": [],
        }

        for rule in getattr(policy, "rules", None) or []:
            policies_info[policy_name]["rules"].append(
                {
                    "name": rule.name,
                    "principal": getattr(rule, "principal", None),
                    "change": getattr(rule, "change", None),
                    "full_control": getattr(rule, "full_control", None),
                    "read": getattr(rule, "read", None),
                }
            )

    return policies_info


def generate_network_access_policies_dict(blade):
    policies_info = {}

    for policy in blade.get_network_access_policies().items:
        policy_name = policy.name
        policies_info[policy_name] = {
            "local": getattr(policy, "is_local", None),
            "enabled": getattr(policy, "enabled", None),
            "version": getattr(policy, "version", None),
            "rules": [],
        }

        for rule in getattr(policy, "rules", None) or []:
            policies_info[policy_name]["rules"].append(
                {
                    "name": rule.name,
                    "client": getattr(rule, "client", None),
                    "effect": getattr(rule, "effect", None),
                    "interfaces": getattr(rule, "interfaces", None),
                    "index": getattr(rule, "index", None),
                }
            )

    return policies_info


def generate_worm_data_policies_dict(blade):
    policies_info = {}
    api_version = get_rest_api_version(blade)
    has_autocommit = LooseVersion(WORM_AUTOCOMMIT_API_VERSION) <= LooseVersion(
        api_version
    )

    for policy in blade.get_worm_data_policies().items:
        policies_info[policy.name] = {
            "local": getattr(policy, "is_local", None),
            "enabled": getattr(policy, "enabled", None),
            "mode": getattr(policy, "mode", None),
            "retention_lock": getattr(policy, "retention_lock", None),
            "default_retention": getattr(policy, "default_retention", None),
            "min_retention": getattr(policy, "min_retention", None),
            "max_retention": getattr(policy, "max_retention", None),
            "members": [],
        }
        if has_autocommit:
            # commit_mode and the autocommit configuration exist from REST
            # 2.29; delay_period is in milliseconds like the retentions.
            autocommit = getattr(policy, "autocommit_config", None)
            policies_info[policy.name]["commit_mode"] = getattr(
                policy, "commit_mode", None
            )
            policies_info[policy.name]["autocommit_config"] = {
                "delay_on": getattr(autocommit, "delay_on", None),
                "delay_period": getattr(autocommit, "delay_period", None),
            }

    for member in blade.get_worm_data_policies_members().items:
        policy_name = getattr(getattr(member, "policy", None), "name", None)
        if policy_name in policies_info:
            policies_info[policy_name]["members"].append(
                getattr(getattr(member, "member", None), "name", None)
            )

    return policies_info


def generate_tls_policies_dict(blade):
    policies_info = {}

    for policy in blade.get_tls_policies().items:
        policies_info[policy.name] = {
            "local": getattr(policy, "is_local", None),
            "enabled": getattr(policy, "enabled", None),
            "appliance_certificate": getattr(
                getattr(policy, "appliance_certificate", None), "name", None
            ),
            "min_tls_version": getattr(policy, "min_tls_version", None),
            "enabled_tls_ciphers": getattr(policy, "enabled_tls_ciphers", None),
            "disabled_tls_ciphers": getattr(policy, "disabled_tls_ciphers", None),
            "client_certificates_required": getattr(
                policy, "client_certificates_required", None
            ),
            "verify_client_certificate_trust": getattr(
                policy, "verify_client_certificate_trust", None
            ),
            "trusted_client_certificate_authority": getattr(
                getattr(policy, "trusted_client_certificate_authority", None),
                "name",
                None,
            ),
            "network_interfaces": [],
        }

    for member in blade.get_tls_policies_network_interfaces().items:
        policy_name = getattr(getattr(member, "policy", None), "name", None)
        if policy_name in policies_info:
            policies_info[policy_name]["network_interfaces"].append(
                getattr(getattr(member, "member", None), "name", None)
            )

    # tls-policies/members also lists the policy applied to the array as a
    # whole (member resource_type "arrays"); interface members are above.
    for policy_name in policies_info:
        policies_info[policy_name]["array_wide"] = False
    for member in blade.get_tls_policies_members().items:
        policy_name = getattr(getattr(member, "policy", None), "name", None)
        member_type = getattr(getattr(member, "member", None), "resource_type", None)
        if member_type == "arrays" and policy_name in policies_info:
            policies_info[policy_name]["array_wide"] = True

    return policies_info


def generate_ssh_ca_policies_dict(blade):
    policies_info = {}
    signer_types = {"public-keys": "public_key", "certificates": "certificate"}

    for policy in blade.get_ssh_certificate_authority_policies().items:
        signer = getattr(policy, "signing_authority", None)
        signer_type = getattr(signer, "resource_type", None)
        policies_info[policy.name] = {
            "local": getattr(policy, "is_local", None),
            "enabled": getattr(policy, "enabled", None),
            "signing_authority": getattr(signer, "name", None),
            "signing_authority_type": signer_types.get(signer_type, signer_type),
            "static_authorized_principals": getattr(
                policy, "static_authorized_principals", None
            )
            or [],
            "admins": [],
            "arrays": [],
        }

    for member in blade.get_ssh_certificate_authority_policies_members().items:
        policy_name = getattr(getattr(member, "policy", None), "name", None)
        if policy_name in policies_info:
            ref = getattr(member, "member", None)
            key = (
                "arrays"
                if getattr(ref, "resource_type", None) == "arrays"
                else "admins"
            )
            policies_info[policy_name][key].append(getattr(ref, "name", None))

    return policies_info


def generate_s3_export_policies_dict(blade):
    policies_info = {}

    for policy in blade.get_s3_export_policies().items:
        policy_name = policy.name
        policies_info[policy_name] = {
            "local": getattr(policy, "is_local", None),
            "enabled": getattr(policy, "enabled", None),
            "rules": [],
        }

        for rule in getattr(policy, "rules", None) or []:
            policies_info[policy_name]["rules"].append(
                {
                    "name": rule.name,
                    "actions": getattr(rule, "actions", None),
                    "effect": getattr(rule, "effect", None),
                    "resources": getattr(rule, "resources", None),
                }
            )

    return policies_info


def generate_object_store_account_exports_dict(blade):
    exports_info = {}

    for export in blade.get_object_store_account_exports().items:
        exports_info[export.name] = {
            "enabled": getattr(export, "enabled", None),
            "account": getattr(getattr(export, "member", None), "name", None),
            "policy": getattr(getattr(export, "policy", None), "name", None),
            "server": getattr(getattr(export, "server", None), "name", None),
        }

    return exports_info


def generate_object_store_virtual_hosts_dict(blade):
    vhosts_info = {}

    for vhost in blade.get_object_store_virtual_hosts().items:
        attached = getattr(vhost, "attached_servers", None) or []
        if not isinstance(attached, list):
            attached = []
        vhosts_info[vhost.name] = {
            # Before REST 2.20 the name is the hostname
            "hostname": getattr(vhost, "hostname", None) or vhost.name,
            "attached_servers": [getattr(srv, "name", None) for srv in attached],
        }

    return vhosts_info


def generate_realms_dict(blade):
    realms_info = {}
    api_version = get_rest_api_version(blade)

    # Default object store server per realm (REST 2.20+). A realm without a
    # default has an empty object_store list or no defaults entry at all.
    default_servers = {}
    if LooseVersion(REALM_DEFAULTS_API_VERSION) <= LooseVersion(api_version):
        res = blade.get_realms_defaults()
        if res.status_code == 200:
            for defaults in res.items:
                realm_name = getattr(getattr(defaults, "realm", None), "name", None)
                object_store = getattr(defaults, "object_store", None) or []
                server = None
                if object_store:
                    server = getattr(
                        getattr(object_store[0], "server", None), "name", None
                    )
                default_servers[realm_name] = server

    for realm in blade.get_realms().items:
        space = getattr(realm, "space", None)
        created = getattr(realm, "created", None)
        realms_info[realm.name] = {
            "created": (
                datetime.fromtimestamp(created / 1000).strftime("%Y-%m-%d %H:%M:%S")
                if created
                else None
            ),
            "destroyed": getattr(realm, "destroyed", None),
            "time_remaining": getattr(realm, "time_remaining", None),
            "default_inbound_tls_policy": getattr(
                getattr(realm, "default_inbound_tls_policy", None), "name", None
            ),
            "default_object_server": default_servers.get(realm.name),
            "space": {
                "data_reduction": getattr(space, "data_reduction", None),
                "snapshots": getattr(space, "snapshots", None),
                "total_physical": getattr(space, "total_physical", None),
                "total_used": getattr(space, "total_used", None),
                "unique": getattr(space, "unique", None),
                "virtual": getattr(space, "virtual", None),
                "total_provisioned": getattr(space, "total_provisioned", None),
                "available_provisioned": getattr(space, "available_provisioned", None),
                "available_ratio": getattr(space, "available_ratio", None),
                "destroyed": getattr(space, "destroyed", None),
                "destroyed_virtual": getattr(space, "destroyed_virtual", None),
            },
        }

    return realms_info


def generate_resource_accesses_dict(blade):
    accesses_info = []

    for access in blade.get_resource_accesses().items:
        resource = getattr(access, "resource", None)
        scope = getattr(access, "scope", None)
        accesses_info.append(
            {
                "id": getattr(access, "id", None),
                "resource": getattr(resource, "name", None),
                "resource_type": getattr(resource, "resource_type", None),
                "scope": getattr(scope, "name", None),
                "scope_type": getattr(scope, "resource_type", None),
            }
        )

    return accesses_info


def generate_password_policies_dict(blade):
    policies_info = {}
    policies = list(blade.get_password_policies().items)
    for policy in policies:
        # Rules disabled on the array (set to 0) read back as absent and
        # are reported as null. Durations are reported in seconds, matching
        # the purefb_password_policy module and the admin settings values
        # in the default subset; the API stores milliseconds.
        lockout = getattr(policy, "lockout_duration", None)
        min_age = getattr(policy, "min_password_age", None)
        max_age = getattr(policy, "max_password_age", None)
        policies_info[policy.name] = {
            "enabled": getattr(policy, "enabled", None),
            "min_password_length": getattr(policy, "min_password_length", None),
            "max_login_attempts": getattr(policy, "max_login_attempts", None),
            "lockout_duration": (int(lockout / 1000) if lockout is not None else None),
            "password_history": getattr(policy, "password_history", None),
            "min_password_age": (int(min_age / 1000) if min_age is not None else None),
            "max_password_age": (int(max_age / 1000) if max_age is not None else None),
            "min_character_groups": getattr(policy, "min_character_groups", None),
            "min_characters_per_group": getattr(
                policy, "min_characters_per_group", None
            ),
            "enforce_username_check": getattr(policy, "enforce_username_check", None),
            "enforce_dictionary_check": getattr(
                policy, "enforce_dictionary_check", None
            ),
        }
    return policies_info


def generate_object_store_accounts_dict(blade):
    account_info = {}

    for account in blade.get_object_store_accounts().items:
        acc_name = account.name
        space = account.space

        account_info[acc_name] = {
            "object_count": account.object_count,
            "data_reduction": space.data_reduction,
            "snapshots_space": space.snapshots,
            "total_physical_space": space.total_physical,
            "unique_space": space.unique,
            "virtual_space": space.virtual,
            "total_provisioned_space": getattr(space, "total_provisioned", None),
            "available_provisioned_space": getattr(
                space, "available_provisioned", None
            ),
            "available_ratio": getattr(space, "available_ratio", None),
            "destroyed_space": getattr(space, "destroyed", None),
            "destroyed_virtual_space": getattr(space, "destroyed_virtual", None),
            "quota_limit": getattr(account, "quota_limit", None),
            "hard_limit_enabled": getattr(account, "hard_limit_enabled", None),
            "total_provisioned": getattr(space, "total_provisioned", None),
            "users": {},
            "bucket_defaults": {
                "hard_limit_enabled": getattr(
                    getattr(account, "bucket_defaults", None),
                    "hard_limit_enabled",
                    None,
                ),
                "quota_limit": getattr(
                    getattr(account, "bucket_defaults", None),
                    "quota_limit",
                    None,
                ),
            },
            "public_access_config": {
                "block_new_public_policies": getattr(
                    getattr(account, "public_access_config", None),
                    "block_new_public_policies",
                    None,
                ),
                "block_public_access": getattr(
                    getattr(account, "public_access_config", None),
                    "block_public_access",
                    None,
                ),
            },
        }

        # Users for this account
        acc_users = blade.get_object_store_users(filter=f'name="{acc_name}/*"').items

        for acc_user in acc_users:
            user_name = acc_user.name.split("/")[1]
            account_info[acc_name]["users"][user_name] = {
                "keys": [],
                "policies": [],
            }

            # Access Keys
            keys_res = blade.get_object_store_access_keys(
                filter=f'user.name="{acc_user.name}"'
            )
            if keys_res.total_item_count != 0:
                for key in keys_res.items:
                    account_info[acc_name]["users"][user_name]["keys"].append(
                        {
                            "name": key.name,
                            "enabled": bool(key.enabled),
                        }
                    )

            # Policies
            policies_res = blade.get_object_store_access_policies_object_store_users(
                member_names=[acc_user.name]
            )
            if policies_res.total_item_count != 0:
                for policy in policies_res.items:
                    account_info[acc_name]["users"][user_name]["policies"].append(
                        policy.policy.name
                    )

    return account_info


def generate_fs_dict(blade, exports=None):
    fs_info = {}
    by_fs = {}
    api_version = get_rest_api_version(blade)
    for e in exports or []:
        by_fs.setdefault(e.get("filesystem"), []).append(e)
    for fsystem in blade.get_file_systems().items:
        share = fsystem.name

        nfs = getattr(fsystem, "nfs", None)
        smb = getattr(fsystem, "smb", None)
        multi = getattr(fsystem, "multi_protocol", None)
        # A filesystem copy reports its source filesystem here; a plain
        # filesystem has a source with no name.
        source = getattr(fsystem, "source", None)
        source_location = getattr(source, "location", None)

        fs_info[share] = {
            "fast_remove": fsystem.fast_remove_directory_enabled,
            "snapshot_enabled": fsystem.snapshot_directory_enabled,
            "provisioned": fsystem.provisioned,
            "destroyed": fsystem.destroyed,
            "nfs_rules": getattr(nfs, "rules", None),
            "nfs_v3": getattr(nfs, "v3_enabled", False),
            "nfs_v4_1": getattr(nfs, "v4_1_enabled", False),
            "user_quotas": {},
            "group_quotas": {},
            "http": fsystem.http.enabled,
            "smb_mode": getattr(smb, "acl_mode", None),
            "multi_protocol": {
                # safegaurd_acls is kept for backwards compatibility
                "safegaurd_acls": getattr(multi, "safeguard_acls", None),
                "safeguard_acls": getattr(multi, "safeguard_acls", None),
                "access_control_style": getattr(multi, "access_control_style", None),
            },
            "hard_limit": fsystem.hard_limit_enabled,
            "promotion_status": fsystem.promotion_status,
            "requested_promotion_state": fsystem.requested_promotion_state,
            "writable": fsystem.writable,
            "source": {
                "is_local": getattr(source, "is_local", None),
                "name": getattr(source, "name", None),
                "resource_type": getattr(source, "resource_type", None),
                "display_name": getattr(source, "display_name", None),
                "location": getattr(source_location, "name", None),
            },
            "default_group_quota": fsystem.default_group_quota,
            "default_user_quota": fsystem.default_user_quota,
            "export_policy": getattr(getattr(nfs, "export_policy", None), "name", None),
            "smb_client_policy": getattr(
                getattr(smb, "client_policy", None), "name", None
            ),
            "smb_share_policy": getattr(
                getattr(smb, "share_policy", None), "name", None
            ),
            "smb_continuous_availability_enabled": getattr(
                smb, "continuous_availability_enabled", False
            ),
            "multi_protocol_access_control_style": getattr(
                multi, "access_control_style", None
            ),
            "multi_protocol_safeguard_acls": getattr(multi, "safeguard_acls", None),
        }
        if LooseVersion(STORAGE_CLASS_API_VERSION) <= LooseVersion(api_version):
            # The array returns storage_class as an object; platforms without
            # storage classes return it with no name, so the name is null there.
            fs_info[share]["storage_class"] = getattr(
                getattr(fsystem, "storage_class", None), "name", None
            )
        if exports is not None:
            fs_info[share]["file_system_exports"] = by_fs.get(share, [])

        # Group quotas
        for group_quota in blade.get_quotas_groups(file_system_names=[share]).items:
            group_name = group_quota.name.rsplit("/", 1)[1]
            fs_info[share]["group_quotas"][group_name] = {
                "group_id": getattr(group_quota.group, "id", None),
                "group_name": getattr(group_quota.group, "name", None),
                "quota": group_quota.quota,
                "usage": group_quota.usage,
            }

        # User quotas
        for user_quota in blade.get_quotas_users(file_system_names=[share]).items:
            user_name = user_quota.name.rsplit("/", 1)[1]
            fs_info[share]["user_quotas"][user_name] = {
                "user_id": getattr(user_quota.user, "id", None),
                "user_name": getattr(user_quota.user, "name", None),
                "quota": user_quota.quota,
                "usage": user_quota.usage,
            }

    return fs_info


def generate_drives_dict(blade):
    """
    Drives information is only available for the Legend chassis.
    The Legend chassis product_name has // in it so only bother if
    that is the case.
    """
    drives_info = {}
    arrays = list(blade.get_arrays().items)
    if not arrays:
        return drives_info

    product_type = getattr(arrays[0], "product_type", "")

    if "//" not in product_type:
        return drives_info

    for drive in blade.get_drives().items:
        drives_info[drive.name] = {
            "progress": getattr(drive, "progress", None),
            "raw_capacity": getattr(drive, "raw_capacity", None),
            "status": getattr(drive, "status", None),
            "details": getattr(drive, "details", None),
            "type": getattr(drive, "type", None),
        }
    return drives_info


def generate_servers_dict(blade):
    servers_info = {}
    for server in blade.get_servers().items:
        servers_info[server.name] = {
            "created": datetime.fromtimestamp(server.created / 1000).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "dns": [dns.name for dns in server.dns],
            "directory_services": [ds.name for ds in server.directory_services],
            # local_directory_service arrived in REST 2.24 and realms in 2.19;
            # older arrays return servers without either field
            "local_directory_service": getattr(
                getattr(server, "local_directory_service", None), "name", None
            ),
            "realms": [realm.name for realm in (getattr(server, "realms", None) or [])],
        }
    return servers_info


def generate_file_system_exports_dict(blade):
    """Return the list of File System Exports for the whole array.

    Requires REST API 2.16+ (SERVERS_API_VERSION). Callers must gate on
    the API version before invoking; this helper does not check.
    """
    exports = []
    for exp in blade.get_file_system_exports().items:
        member = getattr(exp, "member", None)
        server = getattr(exp, "server", None)
        policy = getattr(exp, "policy", None)
        share_policy = getattr(exp, "share_policy", None)
        ptype = getattr(exp, "policy_type", None)
        exports.append(
            {
                "export_name": getattr(exp, "export_name", None),
                "type": ptype,
                "filesystem": getattr(member, "name", None),
                "server": getattr(server, "name", None),
                "export_policy": (
                    getattr(policy, "name", None) if ptype == "NFS" else None
                ),
                "client_policy": (
                    getattr(policy, "name", None) if ptype == "SMB" else None
                ),
                "share_policy": (
                    getattr(share_policy, "name", None) if ptype == "SMB" else None
                ),
            }
        )
    return exports


def generate_legal_holds_dict(blade):
    """File legal holds keyed by name, each with the paths it is applied to.

    Requires REST API 2.17+ (LEGAL_HOLD_API_VERSION). Callers gate on it.
    """
    holds_info = {}
    for hold in blade.get_legal_holds().items:
        holds_info[hold.name] = {
            "description": getattr(hold, "description", None),
            "realms": [
                getattr(realm, "name", None)
                for realm in (getattr(hold, "realms", None) or [])
            ],
            "held_entities": [],
        }
    for entity in blade.get_legal_holds_held_entities().items:
        hold_name = getattr(getattr(entity, "legal_hold", None), "name", None)
        if hold_name in holds_info:
            holds_info[hold_name]["held_entities"].append(
                {
                    "file_system": getattr(
                        getattr(entity, "file_system", None), "name", None
                    ),
                    "path": getattr(entity, "path", None),
                    "status": getattr(entity, "status", None),
                }
            )
    return holds_info


def generate_fleet_dict(blade):
    fleet_items = list(blade.get_fleets().items)
    if not fleet_items:
        return {}

    fleet_name = fleet_items[0].name
    members = blade.get_fleets_members().items

    fleet_info = {
        fleet_name: {
            "members": {
                member.member.name: {
                    "status": member.status,
                    "status_details": member.status_details,
                }
                for member in members
            }
        }
    }
    return fleet_info


# File locks, lock clients, file sessions and SMB open files (the read-back
# for purefb_fs_lock). Locks need REST 2.8, sessions 2.10, open files 2.17.
FILE_LOCKS_API_VERSION = "2.8"
FILE_SESSIONS_API_VERSION = "2.10"
OPEN_FILES_API_VERSION = "2.17"


def _ref_name(ref):
    return getattr(ref, "name", None) if ref is not None else None


def generate_file_locks_dict(blade):
    """Return the active file locks, lock clients, file sessions and open files.

    Point-in-time data that changes as clients work. Open files are only
    tracked for SMB, so they are queried with protocols=smb.
    """
    api_version = get_rest_api_version(blade)
    info = {
        "file_locks": {},
        "file_lock_clients": [],
        "file_sessions": {},
        "open_files": {},
    }
    res = blade.get_file_systems_locks()
    if res.status_code == 200:
        for lock in list(res.items):
            lock_range = getattr(lock, "range", None)
            info["file_locks"][lock.name] = {
                "access_type": getattr(lock, "access_type", None),
                "client": _ref_name(getattr(lock, "client", None)),
                "created_at": getattr(lock, "created_at", None),
                "file_system": _ref_name(getattr(lock, "source", None)),
                "inode": getattr(lock, "inode", None),
                "path": getattr(lock, "path", None),
                "protocol": getattr(lock, "protocol", None),
                "range": (
                    None
                    if lock_range is None
                    else {
                        "length": getattr(lock_range, "length", None),
                        "offset": getattr(lock_range, "offset", None),
                    }
                ),
            }
    res = blade.get_file_systems_locks_clients()
    if res.status_code == 200:
        names = [_ref_name(client) for client in list(res.items)]
        info["file_lock_clients"] = sorted(name for name in names if name)
    if LooseVersion(FILE_SESSIONS_API_VERSION) <= LooseVersion(api_version):
        res = blade.get_file_systems_sessions()
        if res.status_code == 200:
            for session in list(res.items):
                info["file_sessions"][session.name] = {
                    "authentication": getattr(session, "authentication", None),
                    "client": _ref_name(getattr(session, "client", None)),
                    "connection_time": getattr(session, "connection_time", None),
                    "idle_time": getattr(session, "idle_time", None),
                    "opens": getattr(session, "opens", None),
                    "port": getattr(session, "port", None),
                    "protocol": getattr(session, "protocol", None),
                    "user": _ref_name(getattr(session, "user", None)),
                }
    if LooseVersion(OPEN_FILES_API_VERSION) <= LooseVersion(api_version):
        res = blade.get_file_systems_open_files(protocols=["smb"])
        if res.status_code == 200:
            for open_file in list(res.items):
                info["open_files"][open_file.id] = {
                    "client": _ref_name(getattr(open_file, "client", None)),
                    "file_system": _ref_name(getattr(open_file, "source", None)),
                    "lock_count": getattr(open_file, "lock_count", None),
                    "mode": getattr(open_file, "mode", None),
                    "path": getattr(open_file, "path", None),
                    "session": _ref_name(getattr(open_file, "session", None)),
                    "user": _ref_name(getattr(open_file, "user", None)),
                }
    return info


def generate_support_dict(blade):
    """Return the retained self-diagnostics runs and the diagnostics tool version.

    Requires REST API 2.16+ (SUPPORT_DIAGNOSTICS_API_VERSION); callers gate
    on the API version. The array keeps the last 10 runs only, keyed here by
    run index. Per-test results are not included - they belong to
    purefb_support_diagnostics state=report. The tool version read-back needs
    REST API 2.24+ and is empty on older arrays.
    """
    api_version = get_rest_api_version(blade)
    support_info = {"diagnostics": {}, "diagnostics_settings": {}}
    res = blade.get_support_diagnostics()
    if res.status_code == 200:
        for run in list(res.items):
            period = getattr(run, "analysis_period", None)
            counts = {"info": 0, "warning": 0, "critical": 0}
            for entry in getattr(run, "severity_count", None) or []:
                severity = getattr(entry, "severity", None)
                if severity:
                    counts[severity] = getattr(entry, "count", None) or 0
            support_info["diagnostics"][str(getattr(run, "index", ""))] = {
                "task_id": getattr(run, "task_id", None),
                "status": getattr(run, "status", None),
                "version": getattr(run, "version", None),
                "start_time": getattr(run, "start_time", None),
                "analysis_period_start": getattr(period, "start_time", None),
                "analysis_period_end": getattr(period, "end_time", None),
                "severity_count": counts,
            }
    if LooseVersion(SUPPORT_DIAGNOSTICS_SETTINGS_API_VERSION) <= LooseVersion(
        api_version
    ):
        res = blade.get_support_diagnostics_settings()
        if res.status_code == 200:
            settings = next(iter(list(res.items)), None)
            if settings is not None:
                support_info["diagnostics_settings"] = {
                    "version": getattr(settings, "version", None),
                    "last_updated": getattr(settings, "last_updated", None),
                }
    return support_info


def generate_eviction_policies_dict(blade):
    """Data eviction policies (REST 2.21) with their attached file systems."""
    policies_info = {}

    res = blade.get_data_eviction_policies()
    if res.status_code != 200:
        return policies_info
    for policy in list(res.items):
        policies_info[policy.name] = {
            "local": getattr(policy, "is_local", None),
            "enabled": getattr(policy, "enabled", None),
            "keep_size": getattr(policy, "keep_size", None),
            "file_systems": [],
        }

    res = blade.get_data_eviction_policies_file_systems()
    if res.status_code == 200:
        for member in list(res.items):
            policy_name = getattr(getattr(member, "policy", None), "name", None)
            if policy_name in policies_info:
                policies_info[policy_name]["file_systems"].append(
                    getattr(getattr(member, "member", None), "name", None)
                )

    return policies_info


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(gather_subset=dict(default="minimum", type="list", elements="str"))
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    blade = get_system(module)
    api_version = get_rest_api_version(blade)

    if not module.params["gather_subset"]:
        module.params["gather_subset"] = ["minimum"]
    subset = [test.lower() for test in module.params["gather_subset"]]
    valid_subsets = (
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
        "clients",
        "locks",
        "support",
        "legal_holds",
    )
    subset_test = (test in valid_subsets for test in subset)
    if not all(subset_test):
        module.fail_json(
            msg="value must gather_subset must be one or more of: %s, got: %s"
            % (",".join(valid_subsets), ",".join(subset))
        )

    info = {}

    if "minimum" in subset or "all" in subset:
        info["default"] = generate_default_dict(blade)
    if "performance" in subset or "all" in subset:
        info["performance"] = generate_perf_dict(blade)
    if "config" in subset or "all" in subset:
        info["config"] = generate_config_dict(blade)
    if "capacity" in subset or "all" in subset:
        info["capacity"] = generate_capacity_dict(blade)
    if "lags" in subset or "all" in subset:
        info["lag"] = generate_lag_dict(blade)
    if "network" in subset or "all" in subset:
        info["network"] = generate_network_dict(blade)
    if "subnets" in subset or "all" in subset:
        info["subnet"] = generate_subnet_dict(blade)
    if "filesystems" in subset or "all" in subset:
        exports_list = None
        if LooseVersion(SERVERS_API_VERSION) <= LooseVersion(api_version):
            exports_list = generate_file_system_exports_dict(blade)
            info["file_system_exports"] = exports_list
        info["filesystems"] = generate_fs_dict(blade, exports_list)
    if "admins" in subset or "all" in subset:
        info["admins"] = generate_admin_dict(blade)
    if "snapshots" in subset or "all" in subset:
        info["snapshots"] = generate_snap_dict(blade)
    if "buckets" in subset or "all" in subset:
        info["buckets"] = generate_bucket_dict(blade)
        info["object_store_virtual_hosts"] = generate_object_store_virtual_hosts_dict(
            blade
        )
    if "policies" in subset or "all" in subset:
        info["policies"] = generate_all_policies_dict(blade)
        info["snapshot_policies"] = generate_policies_dict(blade)
        # snapshot policies share the membership gathered by the policies
        # view, so no second members call is made
        for name, snap_policy in info["snapshot_policies"].items():
            if "members" in info["policies"].get(name, {}):
                snap_policy["members"] = info["policies"][name]["members"]
    if "arrays" in subset or "all" in subset:
        info["arrays"] = generate_array_conn_dict(blade)
    if "replication" in subset or "all" in subset:
        info["file_replication"] = generate_file_repl_dict(blade)
        info["bucket_replication"] = generate_bucket_repl_dict(blade)
        info["snap_transfers"] = generate_snap_transfer_dict(blade)
        info["fs_replica_transfers"] = generate_fs_repl_transfer_dict(blade)
        info["remote_credentials"] = generate_remote_creds_dict(blade)
        info["targets"] = generate_targets_dict(blade)
    if "accounts" in subset or "all" in subset:
        info["accounts"] = generate_object_store_accounts_dict(blade)
        if LooseVersion(S3_EXPORT_API_VERSION) <= LooseVersion(api_version):
            info["object_store_account_exports"] = (
                generate_object_store_account_exports_dict(blade)
            )
    if "ad" in subset or "all" in subset:
        info["active_directory"] = generate_ad_dict(blade)
    if "kerberos" in subset or "all" in subset:
        info["kerberos"] = generate_kerb_dict(blade)
    if "policies" in subset or "all" in subset:
        info["access_policies"] = generate_object_store_access_policies_dict(blade)
        if LooseVersion(PUBLIC_API_VERSION) <= LooseVersion(api_version):
            info["bucket_access_policies"] = generate_bucket_access_policies_dict(blade)
            info["bucket_cross_origin_policies"] = (
                generate_bucket_cross_object_policies_dict(blade)
            )
        info["export_policies"] = generate_nfs_export_policies_dict(blade)
        if LooseVersion(SMB_CLIENT_API_VERSION) <= LooseVersion(api_version):
            # share_policies has always held the SMB *client* policies; it is
            # kept for backwards compatibility alongside the correct key.
            info["smb_client_policies"] = generate_smb_client_policies_dict(blade)
            info["share_policies"] = info["smb_client_policies"]
            info["smb_share_policies"] = generate_smb_share_policies_dict(blade)
        if LooseVersion(NAP_API_VERSION) <= LooseVersion(api_version):
            info["network_access_policies"] = generate_network_access_policies_dict(
                blade
            )
        if LooseVersion(WORM_API_VERSION) <= LooseVersion(api_version):
            info["worm_data_policies"] = generate_worm_data_policies_dict(blade)
        if LooseVersion(PASSWORD_POLICY_API_VERSION) <= LooseVersion(api_version):
            info["password_policies"] = generate_password_policies_dict(blade)
        if LooseVersion(FLEET_API_VERSION) <= LooseVersion(api_version):
            info["fleet"] = generate_fleet_dict(blade)
        if LooseVersion(TLS_API_VERSION) <= LooseVersion(api_version):
            info["tls_policies"] = generate_tls_policies_dict(blade)
        if LooseVersion(SSH_CA_API_VERSION) <= LooseVersion(api_version):
            info["ssh_ca_policies"] = generate_ssh_ca_policies_dict(blade)
        if LooseVersion(S3_EXPORT_API_VERSION) <= LooseVersion(api_version):
            info["s3_export_policies"] = generate_s3_export_policies_dict(blade)
        if LooseVersion(EVICTION_API_VERSION) <= LooseVersion(api_version):
            info["eviction_policies"] = generate_eviction_policies_dict(blade)
    if ("realms" in subset or "all" in subset) and LooseVersion(
        REALMS_API_VERSION
    ) <= LooseVersion(api_version):
        info["realms"] = generate_realms_dict(blade)
        info["resource_accesses"] = generate_resource_accesses_dict(blade)
    if ("drives" in subset or "all" in subset) and LooseVersion(
        DRIVES_API_VERSION
    ) <= LooseVersion(api_version):
        info["drives"] = generate_drives_dict(blade)
    # `fleet` is a documented subset of its own; until now the data was only
    # produced as part of `policies`, so gather_subset=fleet returned nothing.
    if ("fleet" in subset or "all" in subset) and LooseVersion(
        FLEET_API_VERSION
    ) <= LooseVersion(api_version):
        info["fleet"] = generate_fleet_dict(blade)
    if ("servers" in subset or "all" in subset) and LooseVersion(
        SERVERS_API_VERSION
    ) <= LooseVersion(api_version):
        info["servers"] = generate_servers_dict(blade)
    # `clients` samples the array for several seconds per protocol and lists
    # S3 clients per connection, so it is opt-in and not part of `all`.
    if "clients" in subset:
        info["clients"] = generate_clients_dict(blade, api_version)
    if ("locks" in subset or "all" in subset) and LooseVersion(
        FILE_LOCKS_API_VERSION
    ) <= LooseVersion(api_version):
        info.update(generate_file_locks_dict(blade))
    if ("support" in subset or "all" in subset) and LooseVersion(
        SUPPORT_DIAGNOSTICS_API_VERSION
    ) <= LooseVersion(api_version):
        info["support"] = generate_support_dict(blade)
    if ("legal_holds" in subset or "all" in subset) and LooseVersion(
        LEGAL_HOLD_API_VERSION
    ) <= LooseVersion(api_version):
        info["legal_holds"] = generate_legal_holds_dict(blade)
    module.exit_json(changed=False, purefb_info=info)


if __name__ == "__main__":
    main()
