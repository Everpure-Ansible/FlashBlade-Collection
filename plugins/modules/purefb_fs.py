#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2017, Simon Dodsley (simon@everpuredata.com)
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type


ANSIBLE_METADATA = {
    "metadata_version": "1.1",
    "status": ["preview"],
    "supported_by": "community",
}


DOCUMENTATION = """
---
module: purefb_fs
version_added: "1.0.0"
short_description:  Manage filesystemon Everpure FlashBlade`
description:
    - This module manages filesystems on Everpure FlashBlade.
author: Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
      - Filesystem Name.
      - A filesystem in a realm is named C(realm::name). Give that name, or
        give the short name together with I(realm).
      - Without I(realm) the name is used as it is given, so a short name is
        never looked up inside a realm.
    required: true
    type: str
  state:
    description:
      - Create, delete or modifies a filesystem.
    required: false
    default: present
    type: str
    choices: [ "present", "absent" ]
  eradicate:
    description:
      - Define whether to eradicate the filesystem on delete or leave in trash.
    required: false
    type: bool
    default: false
  size:
    description:
      - Volume size in M, G, T or P units. See examples.
      - If size is not set at filesystem creation time the filesystem size becomes unlimited.
    type: str
    required: false
  nfsv3:
    description:
      - Define whether to NFSv3 protocol is enabled for the filesystem.
    required: false
    type: bool
    default: true
  nfsv4:
    description:
      - Define whether to NFSv4.1 protocol is enabled for the filesystem.
    required: false
    type: bool
    default: true
  nfs_rules:
    description:
      - Define the NFS client export rules for the filesystem, for example
        C(10.21.200.0/24(rw,no_root_squash)).
      - Deprecated. Use the M(everpure.flashblade.purefb_export) module to
        attach NFS export policies via the File System Exports endpoints.
        This parameter will be removed in 2.0.0.
      - Only honoured when explicitly set, and only for non-realm
        filesystems. It is ignored for filesystems in a realm.
    required: false
    type: str
  smb:
    description:
      - Define whether to SMB protocol is enabled for the filesystem.
      - Defaults to C(false) when the filesystem is created. On an existing
        filesystem the protocol is only changed when this option is set.
    required: false
    type: bool
  smb_aclmode:
    description:
      - Specify the ACL mode for the SMB protocol.
      - Deprecated from Purity//FB 3.1.1. Use I(access_control) instead.
    required: false
    type: str
    default: shared
    choices: [ "shared", "native" ]
  http:
    description:
      - Define whether to HTTP/HTTPS protocol is enabled for the filesystem.
      - Defaults to C(false) when the filesystem is created. On an existing
        filesystem the protocol is only changed when this option is set.
    required: false
    type: bool
  snapshot:
    description:
      - Define whether a snapshot directory is enabled for the filesystem.
      - Defaults to C(false) when the filesystem is created. On an existing
        filesystem the setting is only changed when this option is set.
    required: false
    type: bool
  writable:
    description:
      - Define if a filesystem is writable.
    required: false
    type: bool
  promote:
    description:
      - Promote/demote a filesystem.
      - Can only demote the file-system if it is in a replica-link relationship.
      - A filesystem that is C(demoting) in a planned failover cannot be
        promoted directly; use I(abort_quiesce) to cancel the failover.
    required: false
    type: bool
  quiesce:
    description:
      - Planned failover control, used together with I(promote) set to C(false).
      - When C(true), a promoted filesystem starts a planned failover. It moves
        to C(demoting) while the data not yet replicated is sent to the target
        and becomes C(demoted) once replication completes. The module returns
        as soon as the array accepts the request; follow the promotion status
        with M(everpure.flashblade.purefb_info).
      - When C(false), a C(demoting) filesystem skips the remaining replication
        and is demoted immediately. Data not yet replicated is lost, so
        I(discard_snaps) must also be C(true). On a promoted filesystem
        C(false) is the same as omitting I(quiesce).
      - When omitted, I(promote) set to C(false) requests a regular demotion
        without a planned failover, as in earlier releases.
      - Requires Purity//FB 4.8.4+ (REST API 2.28+) on both the source and the
        target FlashBlade, and a replica link that does not fan out. The array
        refuses a planned failover while a replication transfer is in progress,
        and refuses to destroy the filesystem or delete its replica link while
        it is C(demoting).
      - The array takes a snapshot named C(<filesystem>.quiesce.<timestamp>) on
        the source. It keeps the longest retention of the snapshot policies on
        the replica link, or has to be removed manually when the link has none.
    required: false
    type: bool
    version_added: "1.30.0"
  abort_quiesce:
    description:
      - Cancel a planned failover, used together with I(promote) set to C(true).
      - On the source, a C(demoting) filesystem returns to C(promoted). On the
        target, whose replica link is C(quiescing), the target is promoted and
        the source rolls back to C(promoted). Any in-progress data transfer is
        cancelled.
      - Nothing is sent, and no change is reported, when no planned failover is
        in progress. A regular promotion is never sent with this option.
      - Requires Purity//FB 4.8.4+ (REST API 2.28+).
    required: false
    type: bool
    default: false
    version_added: "1.30.0"
  fastremove:
    description:
      - Define whether the fast remove directory is enabled for the filesystem.
      - Defaults to C(false) when the filesystem is created. On an existing
        filesystem the setting is only changed when this option is set.
    required: false
    type: bool
  hard_limit:
    description:
      - Define whether the capacity for a filesystem is a hard limit.
      - CAUTION This will cause the filesystem to go Read-Only if the
        capacity has already exceeded the logical size of the filesystem.
      - Defaults to C(false) when the filesystem is created. On an existing
        filesystem the setting is only changed when this option is set.
    required: false
    type: bool
  user_quota:
    description:
      - Default quota in M, G, T or P units for a user under this file system.
    required: false
    type: str
  group_quota:
    description:
      - Default quota in M, G, T or P units for a group under this file system.
    required: false
    type: str
  policy:
    description:
      - Filesystem policy to assign to or remove from a filesystem.
      - A WORM data policy cannot be attached this way, use I(worm_policy)
        when creating the filesystem.
    required: false
    type: str
  policy_state:
    description:
    - Add or delete a policy from a filesystem
    required: false
    default: present
    type: str
    choices: [ "absent", "present" ]
  worm_policy:
    description:
      - Name of the WORM data policy to attach when the filesystem is created.
        Snapshot and other filesystem policies are attached with I(policy).
      - A WORM data policy can only be attached at creation time and cannot be
        changed or removed afterwards. The module fails if an existing
        filesystem has a different WORM data policy, or none.
      - The array only creates a WORM filesystem in C(retention-based)
        eradication mode, so I(eradication_mode) defaults to that value when
        this option is set.
      - Requires Purity//FB REST API 2.15 or later.
    type: str
    version_added: "1.30.0"
  eradication_mode:
    description:
      - Eradication mode of the filesystem.
      - C(permission-based) allows a destroyed filesystem to be eradicated
        based on user permissions.
      - C(retention-based) prevents eradication while any file in the
        filesystem is locked or retained. The array requires it for a WORM
        filesystem and refuses it without I(worm_policy).
      - Can only be set at creation time and cannot be changed afterwards.
        The module fails if an existing filesystem has a different mode.
        When not set the array default (C(permission-based)) applies, except
        that a filesystem created with I(worm_policy) uses C(retention-based).
      - Requires Purity//FB REST API 2.15 or later.
    type: str
    choices: [ permission-based, retention-based ]
    version_added: "1.30.0"
  delete_link:
    description:
      - Define if the filesystem can be deleted even if it has a replica link
    required: false
    default: false
    type: bool
  discard_snaps:
    description:
      - Allow a filesystem to be demoted.
      - Also required to skip a planned failover, that is I(quiesce) set to
        C(false) on a C(demoting) filesystem.
    required: false
    default: false
    type: bool
  access_control:
    description:
      - The access control style that is utilized for client actions such
        as setting file and directory ACLs.
    type: str
    default: shared
    choices: [ 'nfs', 'smb', 'shared', 'independent', 'mode-bits' ]
  safeguard_acls:
    description:
      - Safeguards ACLs on a filesystem.
      - Performs different roles depending on the filesystem protocol enabled.
      - See Purity//FB documentation for detailed description.
      - Defaults to C(true) when the filesystem is created. On an existing
        filesystem the setting is only changed when this option is set.
    type: bool
  export_policy:
    description:
    - Name of NFS export policy to assign to filesystem.
    - Deprecated. This writes the legacy C(nfs.export_policy) field
      on the filesystem, which Purity//FB marks as deprecated. Use the
      M(everpure.flashblade.purefb_export) module's C(export_policy)
      option to attach NFS export policies via the dedicated File
      System Exports endpoints.
      This parameter will be removed in 2.0.0.
    type: str
    version_added: "1.9.0"
  share_policy:
    description:
    - Name of SMB share policy to assign to filesystem
    - Only valid with REST 2.10 or higher
    - Remove policy with empty string
    - Deprecated. This writes the legacy C(smb.share_policy) field
      on the filesystem, which Purity//FB marks as deprecated. Use the
      M(everpure.flashblade.purefb_export) module's C(share_policy)
      option to attach SMB share policies via the dedicated File
      System Exports endpoints.
      This parameter will be removed in 2.0.0.
    type: str
    version_added: "1.12.0"
  client_policy:
    description:
    - Name of SMB client policy to assign to filesystem
    - Only valid with REST 2.10 or higher
    - Remove policy with empty string
    - Deprecated. This writes the legacy C(smb.client_policy) field
      on the filesystem, which Purity//FB marks as deprecated. Use the
      M(everpure.flashblade.purefb_export) module's C(client_policy)
      option to attach SMB client policies via the dedicated File
      System Exports endpoints.
      This parameter will be removed in 2.0.0.
    type: str
    version_added: "1.12.0"
  continuous_availability:
    description:
    - Defines if the file system will be continuously available during
      disruptive scenarios such as network disruption, blades failover, etc
    type: bool
    default: true
    version_added: "1.15.0"
  group_ownership:
    description:
    - The group ownership for new files and directories in a file system
    type: str
    choices: [ 'creator', 'parent-directory' ]
    default: creator
    version_added: "1.17.0"
  ignore_usage:
    description:
    - Allow update operations that lead to a hard_limit_enabled file
      system with usage over its limiting value
    type: bool
    default: false
    version_added: "1.22.0"
  cancel_in_progress:
    description:
    - Whether to cancel any existing storage class transitions that are in progress
      if the file system is requested to change to another storage class.
    - Only takes effect together with a I(storage_class) that differs from
      the file system's current storage class.
    type: bool
    default: false
    version_added: "1.22.0"
  storage_class:
    description:
    - Name of the storage class the file system is associated with.
    - Only FlashBlade platforms with storage classes accept this option.
      Elsewhere the array rejects the change and the module fails with
      the array error. Check mode reports a pending change on such
      platforms because the array only rejects the request when it is sent.
    - When omitted, or when the file system already has the requested
      storage class, no storage class change is sent.
    type: str
    version_added: "1.22.0"
  context:
    description:
    - Name of fleet member on which to perform the operation.
    - This requires the array receiving the request is a member of a fleet
      and the context name to be a member of the same fleet.
    type: str
    default: ""
    version_added: "1.22.0"
  realm:
    description:
    - Name of the realm to associate the filesystem with.
    - Requires Purity//FB 4.6.1+ (REST API 2.19+).
    - The realm of a filesystem can only be set when the filesystem is created.
    - To move a filesystem to a different realm, the filesystem must be destroyed and recreated.
    - If the realm has a QoS policy, the filesystem will inherit it unless overridden.
    - With I(realm) set, a short I(name) always means the filesystem
      C(realm::name), for every I(state). A filesystem with the same short
      name outside the realm is never read or changed.
    - I(name) may already be realm-qualified. The realm in I(name) must then
      be the same as I(realm), ignoring case, otherwise the module fails
      before anything is sent to the array.
    type: str
    version_added: "1.25.0"
extends_documentation_fragment:
    - everpure.flashblade.everpure.fb
"""

EXAMPLES = """
- name: Create new filesystem named foo
  everpure.flashblade.purefb_fs:
    name: foo
    size: 1T
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create a WORM-protected filesystem using WORM data policy worm1
  everpure.flashblade.purefb_fs:
    name: compliance-fs
    size: 1T
    worm_policy: worm1
    eradication_mode: retention-based
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create new filesystem in realm
  everpure.flashblade.purefb_fs:
    name: prod-fs
    size: 5T
    realm: production-realm
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
  # Filesystem will be created as 'production-realm::prod-fs'

- name: Modify filesystem that belongs to a realm
  everpure.flashblade.purefb_fs:
    name: production-realm::prod-fs
    size: 10T
    nfsv4: false
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
  # The short name with realm: production-realm addresses the same filesystem
  # Realm association cannot be changed after creation

- name: Delete filesystem prod-fs in realm production-realm
  everpure.flashblade.purefb_fs:
    name: prod-fs
    realm: production-realm
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
  # A filesystem named prod-fs outside the realm is not touched

- name: Delete filesystem named foo
  everpure.flashblade.purefb_fs:
    name: foo
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Recover filesystem named foo
  everpure.flashblade.purefb_fs:
    name: foo
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: the iss that ven thou hth ansible Eradicate filesystem named foo
  everpure.flashblade.purefb_fs:
    name: foo
    state: absent
    eradicate: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Promote filesystem named foo ready for failover
  everpure.flashblade.purefb_fs:
    name: foo
    promote: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Demote filesystem named foo after failover
  everpure.flashblade.purefb_fs:
    name: foo
    promote: false
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Start a planned failover of filesystem foo (quiesce, then demote)
  everpure.flashblade.purefb_fs:
    name: foo
    promote: false
    quiesce: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Skip the remaining replication and demote filesystem foo now
  everpure.flashblade.purefb_fs:
    name: foo
    promote: false
    quiesce: false
    discard_snaps: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Abort the planned failover of filesystem foo
  everpure.flashblade.purefb_fs:
    name: foo
    promote: true
    abort_quiesce: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Modify attributes of an existing filesystem named foo
  everpure.flashblade.purefb_fs:
    name: foo
    size: 2T
    nfsv3: false
    nfsv4: true
    user_quota: 10K
    group_quota: 25M
    snapshot: true
    fastremove: true
    hard_limit: true
    smb: true
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Attach export_policy to filesystem foo (deprecated - prefer purefb_export)
  everpure.flashblade.purefb_fs:
    name: foo
    export_policy: nfs_pol1
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create filesystem foo (modern workflow - attach policies via purefb_export)
  everpure.flashblade.purefb_fs:
    name: foo
    size: 1T
    smb: true
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Attach NFS export policy to filesystem foo via purefb_export
  everpure.flashblade.purefb_export:
    name: foo_nfs
    filesystem: foo
    type: NFS
    export_policy: nfs_pol1
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Attach SMB share and client policies to filesystem foo via purefb_export
  everpure.flashblade.purefb_export:
    name: foo_smb
    filesystem: foo
    type: SMB
    share_policy: smb_share_pol1
    client_policy: smb_client_pol1
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = """
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        FileSystemPatch,
        NfsPatch,
        Reference,
        Smb,
        FileSystemPost,
        FileSystemEradicationConfig,
        Nfs,
        SmbPost,
        Http,
        MultiProtocolPost,
        MultiProtocol,
        StorageClassInfo,
    )
except ImportError:
    HAS_PYPURECLIENT = False

from ansible.module_utils.basic import AnsibleModule, human_to_bytes
from ansible_collections.everpure.flashblade.plugins.module_utils.purefb import (
    get_system,
    purefb_argument_spec,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.version import (
    LooseVersion,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.common import (
    get_error_message,
    get_filesystem,
    get_rest_api_version,
)

EXPORT_POLICY_API_VERSION = "2.3"
SMB_POLICY_API_VERSION = "2.10"
CA_API_VERSION = "2.12"
GOWNER_API_VERSION = "2.13"
WORM_API_VERSION = "2.15"
CONTEXT_API_VERSION = "2.17"
REALM_API_VERSION = "2.19"
QUIESCE_API_VERSION = "2.28"


def _item_count(res):
    """Return the number of items in a successful SDK response.

    A membership GET returns 200 with an empty item list when nothing
    matches, so the status code alone does not say whether a member exists.
    """
    if getattr(res, "status_code", None) != 200:
        return 0
    count = getattr(res, "total_item_count", None)
    if isinstance(count, int):
        return count
    try:
        return len(list(res.items))
    except TypeError:
        return 0


def _failover_action(module, blade, fsys, fs_name):
    """Classify a planned-failover request.

    Returns the FileSystemPatch field to send ("quiesce", "skip_quiesce" or
    "abort_quiesce"), "noop" when the planned failover is already in the
    requested state, or None when the request belongs to the regular
    promote/demote path. The caller has checked that promote is set and that
    the array supports planned failover.
    """
    status = fsys.promotion_status
    if module.params["promote"]:
        if not module.params.get("abort_quiesce"):
            return None
        if status == "demoting":
            return "abort_quiesce"
        # A demoted target only shows the failover on its inbound link.
        if status == "demoted" and _link_quiescing(module, blade, fs_name):
            return "abort_quiesce"
        return "noop"
    quiesce = module.params.get("quiesce")
    if quiesce is None:
        return None
    if quiesce:
        return "quiesce" if status == "promoted" else "noop"
    if status == "demoting":
        return "skip_quiesce"
    return None


def _link_quiescing(module, blade, fs_name):
    """Return True when a replica link of the filesystem is quiescing."""
    kwargs = {"local_file_system_names": [fs_name]}
    if module.params["context"]:
        kwargs["context_names"] = [module.params["context"]]
    res = blade.get_file_system_replica_links(**kwargs)
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to get replica links for filesystem {0}. Error: {1}".format(
                fs_name, get_error_message(res)
            )
        )
    links = list(res.items)
    return any(getattr(link, "status", None) == "quiescing" for link in links)


def _patch_failover(module, blade, fs_name, action):
    """Send the dedicated planned-failover PATCH for ``action``.

    The three controls are FileSystemPatch body fields that modify a
    promotion-state request: the array refuses each flag unless the same
    body carries requested_promotion_state (demoted for quiesce and
    skip_quiesce, promoted for abort_quiesce). The PATCH is sent on its own
    so that no other attribute rides along with a failover request.
    """
    body = {action: True}
    if action == "abort_quiesce":
        body["requested_promotion_state"] = "promoted"
    else:
        body["requested_promotion_state"] = "demoted"
    kwargs = {"names": [fs_name], "file_system": FileSystemPatch(**body)}
    if action == "skip_quiesce":
        # Skipping discards the data not yet replicated; the array only
        # accepts that with discard_non_snapshotted_data, and refuses the
        # same flag on a quiesce request.
        kwargs["discard_non_snapshotted_data"] = True
    if module.params["context"]:
        kwargs["context_names"] = [module.params["context"]]
    res = blade.patch_file_systems(**kwargs)
    if res.status_code != 200:
        module.fail_json(
            msg="Planned failover ({0}) failed for filesystem {1}. Error: {2}".format(
                action, fs_name, get_error_message(res)
            )
        )


def _resolve_name(module):
    """Return the one name every request uses for the filesystem.

    A filesystem is in a realm when it is named ``realm::name``. With the
    ``realm`` option set, a short ``name`` is resolved inside that realm
    only. A ``name`` that is already realm-qualified is used as it is, and
    must name the same realm as the ``realm`` option when both are given.
    The two realm names are compared without regard to case, so that a
    spelling the array may resolve to the same realm is not refused.
    """
    name = module.params["name"]
    realm = module.params.get("realm")
    if not realm:
        return name
    if "::" not in name:
        return "{0}::{1}".format(realm, name)
    name_realm = name.split("::")[0]
    if name_realm.lower() != realm.lower():
        module.fail_json(
            msg="Filesystem name {0} is in realm {1}, but realm is set to {2}. "
            "Use the same realm in both, or give only one of them.".format(
                name, name_realm, realm
            )
        )
    return name


def create_fs(module, blade):
    """Create Filesystem"""
    changed = True
    api_version = get_rest_api_version(blade)
    if not module.check_mode:
        # Boolean flags default to None so that modify_fs only touches them
        # when the caller sets them. At creation time None means the array
        # default (safeguard_acls on, every other flag off).
        safeguard_acls = module.params["safeguard_acls"]
        if safeguard_acls is None:
            safeguard_acls = True
        # Determine realm from either realm parameter or name prefix (realm::fs)
        realm_name = None
        if module.params.get("realm"):
            realm_name = module.params["realm"]
        elif "::" in module.params["name"]:
            # Extract realm from name (e.g., "production::prod-fs" -> "production")
            realm_name = module.params["name"].split("::")[0]

        # Validate realm if present
        if realm_name:
            if LooseVersion(REALM_API_VERSION) > LooseVersion(api_version):
                module.fail_json(
                    msg="Realm support requires Purity//FB 4.6.1+ (REST API 2.19+)"
                )
            # Check realm exists
            realm_check = blade.get_realms(destroyed=False, names=[realm_name])
            if realm_check.status_code != 200:
                module.fail_json(msg="Realm '{0}' does not exist".format(realm_name))

        if module.params["size"]:
            size = human_to_bytes(module.params["size"])
        else:
            size = 0

        if module.params["user_quota"]:
            user_quota = human_to_bytes(module.params["user_quota"])
        else:
            user_quota = None
        if module.params["group_quota"]:
            group_quota = human_to_bytes(module.params["group_quota"])
        else:
            group_quota = None

        if module.params["access_control"] == "nfs" and not (
            module.params["nfsv3"] or module.params["nfsv4"]
        ):
            module.fail_json(
                msg="Cannot set access_control to nfs when NFS is not enabled."
            )
        if (
            module.params["access_control"] in ["smb", "independent"]
            and not module.params["smb"]
        ):
            module.fail_json(
                msg="Cannot set access_control to smb or independent when SMB is not enabled."
            )
        if safeguard_acls and (
            module.params["access_control"] in ["mode-bits", "independent"]
        ):
            module.fail_json(
                msg="ACL Safeguarding cannot be enabled if access_control is mode-bits or independent."
            )
        # Determine if this is a realm filesystem
        realm_name = None
        if module.params.get("realm"):
            realm_name = module.params["realm"]
        elif "::" in module.params["name"]:
            realm_name = module.params["name"].split("::")[0]

        # nfs_rules is deprecated in favour of export_policy. It is still
        # honoured for non-realm filesystems for backwards compatibility, but
        # only when explicitly supplied.
        nfs_kwargs = {
            "v3_enabled": module.params["nfsv3"],
            "v4_1_enabled": module.params["nfsv4"],
        }
        if module.params["nfs_rules"] is not None:
            module.deprecate(
                "nfs_rules is deprecated. Use the purefb_export module to attach "
                "NFS export policies via the File System Exports endpoints.",
                version="2.0.0",
                collection_name="everpure.flashblade",
            )
            if realm_name:
                module.warn(
                    "nfs_rules is not supported for realm filesystems and "
                    "will be ignored."
                )
            else:
                nfs_kwargs["rules"] = module.params["nfs_rules"]
        if module.params["export_policy"] is not None:
            module.deprecate(
                "export_policy is deprecated. Use the purefb_export "
                "module's export_policy option to attach NFS export "
                "policies via the dedicated File System Exports "
                "endpoints.",
                version="2.0.0",
                collection_name="everpure.flashblade",
            )
        if module.params["share_policy"] is not None:
            module.deprecate(
                "share_policy is deprecated. Use the purefb_export "
                "module's share_policy option to attach SMB share "
                "policies via the dedicated File System Exports "
                "endpoints.",
                version="2.0.0",
                collection_name="everpure.flashblade",
            )
        if module.params["client_policy"] is not None:
            module.deprecate(
                "client_policy is deprecated. Use the purefb_export "
                "module's client_policy option to attach SMB client "
                "policies via the dedicated File System Exports "
                "endpoints.",
                version="2.0.0",
                collection_name="everpure.flashblade",
            )

        # Build FileSystemPost object
        fs_kwargs = {}
        eradication_mode = module.params.get("eradication_mode")
        if module.params.get("worm_policy") and not eradication_mode:
            # The array refuses to create a filesystem with a WORM data policy
            # in any other eradication mode.
            eradication_mode = "retention-based"
        if eradication_mode:
            # eradication_config is accepted on POST only (FileSystemPatch has
            # no such field), so it is set here and never patched afterwards.
            fs_kwargs["eradication_config"] = FileSystemEradicationConfig(
                eradication_mode=eradication_mode
            )
        fs_obj = FileSystemPost(
            provisioned=size,
            fast_remove_directory_enabled=bool(module.params["fastremove"]),
            hard_limit_enabled=bool(module.params["hard_limit"]),
            snapshot_directory_enabled=bool(module.params["snapshot"]),
            nfs=Nfs(**nfs_kwargs),
            smb=SmbPost(enabled=bool(module.params["smb"])),
            http=Http(enabled=bool(module.params["http"])),
            multi_protocol=MultiProtocolPost(
                safeguard_acls=safeguard_acls,
                access_control_style=module.params["access_control"],
            ),
            default_user_quota=user_quota,
            default_group_quota=group_quota,
            **fs_kwargs
        )
        # Construct filesystem name - if realm provided, prepend realm::
        fs_name = module.params["name"]
        if realm_name and "::" not in fs_name:
            fs_name = "{0}::{1}".format(realm_name, fs_name)

        # Build post_file_systems call with optional parameters
        post_kwargs = {
            "names": [fs_name],
            "file_system": fs_obj,
        }

        # Add context if API supports it
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            post_kwargs["context_names"] = [module.params["context"]]

        # A WORM data policy can only be attached on POST /file-systems; the
        # snapshot policy below is still attached after creation as before.
        if module.params.get("worm_policy"):
            post_kwargs["policy_names"] = [module.params["worm_policy"]]

        # Add default_exports=[""] for realm filesystems (empty string)
        if realm_name:
            post_kwargs["default_exports"] = ["''"]

        res = blade.post_file_systems(**post_kwargs)
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to create filesystem {0}. Error: {1}".format(
                    fs_name, get_error_message(res)
                )
            )
        if module.params["policy"]:
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.get_policies(
                    names=[module.params["policy"]],
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.get_policies(names=[module.params["policy"]])
            if res.status_code != 200:
                _delete_fs(module, blade)
                module.fail_json(
                    msg="Policy {0} doesn't exist.".format(module.params["policy"])
                )
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.post_policies_file_systems(
                    policy_names=[module.params["policy"]],
                    member_names=[fs_name],
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.post_policies_file_systems(
                    policy_names=[module.params["policy"]],
                    member_names=[fs_name],
                )
            if res.status_code != 200:
                _delete_fs(module, blade)
                module.fail_json(
                    msg="Failed to apply policy {0} when creating filesystem {1}. Error: {2}".format(
                        module.params["policy"],
                        fs_name,
                        get_error_message(res),
                    )
                )
        if (
            LooseVersion(EXPORT_POLICY_API_VERSION) <= LooseVersion(api_version)
            and module.params["export_policy"]
            and (module.params["nfsv3"] or module.params["nfsv4"])
        ):
            export_attr = FileSystemPatch(
                nfs=NfsPatch(
                    export_policy=Reference(name=module.params["export_policy"])
                )
            )
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.patch_file_systems(
                    names=[fs_name],
                    file_system=export_attr,
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.patch_file_systems(names=[fs_name], file_system=export_attr)
            if res.status_code != 200:
                module.fail_json(
                    msg="Filesystem {0} created, but failed to assign export "
                    "policy {1}. Error: {2}".format(
                        fs_name,
                        module.params["export_policy"],
                        get_error_message(res),
                    )
                )
        if (
            LooseVersion(SMB_POLICY_API_VERSION) <= LooseVersion(api_version)
            and module.params["smb"]
        ):
            if module.params["client_policy"]:
                export_attr = FileSystemPatch(
                    smb=Smb(
                        client_policy=Reference(name=module.params["client_policy"])
                    )
                )
                if (
                    LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                    and module.params["context"]
                ):
                    res = blade.patch_file_systems(
                        names=[fs_name],
                        file_system=export_attr,
                        context_names=[module.params["context"]],
                    )
                else:
                    res = blade.patch_file_systems(
                        names=[fs_name], file_system=export_attr
                    )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Filesystem {0} created, but failed to assign client "
                        "policy {1}. Error: {2}".format(
                            fs_name,
                            module.params["client_policy"],
                            get_error_message(res),
                        )
                    )
            if module.params["share_policy"]:
                export_attr = FileSystemPatch(
                    smb=Smb(share_policy=Reference(name=module.params["share_policy"]))
                )
                if (
                    LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                    and module.params["context"]
                ):
                    res = blade.patch_file_systems(
                        names=[fs_name],
                        file_system=export_attr,
                        context_names=[module.params["context"]],
                    )
                else:
                    res = blade.patch_file_systems(
                        names=[fs_name],
                        file_system=export_attr,
                    )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Filesystem {0} created, but failed to assign share "
                        "policy {1}. Error: {2}".format(
                            fs_name,
                            module.params["share_policy"],
                            get_error_message(res),
                        )
                    )
            if LooseVersion(CA_API_VERSION) <= LooseVersion(api_version):
                ca_attr = FileSystemPatch(
                    smb=Smb(
                        continuous_availability_enabled=module.params[
                            "continuous_availability"
                        ]
                    )
                )
                if (
                    LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                    and module.params["context"]
                ):
                    res = blade.patch_file_systems(
                        names=[fs_name],
                        file_system=ca_attr,
                        context_names=[module.params["context"]],
                    )
                else:
                    res = blade.patch_file_systems(names=[fs_name], file_system=ca_attr)
                if res.status_code != 200:
                    module.fail_json(
                        msg="Filesystem {0} created, but failed to set continuous availability. "
                        "Error: {1}".format(
                            fs_name,
                            get_error_message(res),
                        )
                    )
        # group_ownership and storage_class are not SMB attributes, so they
        # are applied whether or not SMB is enabled.
        if (
            LooseVersion(GOWNER_API_VERSION) <= LooseVersion(api_version)
            and module.params["group_ownership"]
        ):
            go_attr = FileSystemPatch(group_ownership=module.params["group_ownership"])
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.patch_file_systems(
                    names=[fs_name],
                    file_system=go_attr,
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.patch_file_systems(names=[fs_name], file_system=go_attr)
            if res.status_code != 200:
                module.fail_json(
                    msg="Filesystem {0} created, but failed to set group ownership. "
                    "Error: {1}".format(
                        fs_name,
                        get_error_message(res),
                    )
                )
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["storage_class"]
        ):
            sc_patch = {
                "names": [fs_name],
                "file_system": FileSystemPatch(
                    storage_class=StorageClassInfo(name=module.params["storage_class"])
                ),
                "cancel_in_progress_storage_class_transition": False,
            }
            if module.params["context"]:
                sc_patch["context_names"] = [module.params["context"]]
            res = blade.patch_file_systems(**sc_patch)
            if res.status_code != 200:
                module.fail_json(
                    msg="Filesystem {0} created, but failed to set storage class. "
                    "Error: {1}".format(
                        fs_name,
                        get_error_message(res),
                    )
                )

    module.exit_json(changed=changed)


def _check_create_only_options(module, blade, fsys, api_version):
    """Refuse a worm_policy or eradication_mode that differs from the
    existing filesystem ``fsys`` (the object main() already fetched).

    Both are accepted on POST /file-systems only: FileSystemPatch has no
    eradication_config and a WORM data policy cannot be attached to or
    detached from an existing filesystem. Runs before any PATCH so a
    mismatch fails the task without touching the filesystem; matching
    values are a no-op so a replayed create task stays idempotent.
    """
    worm_policy = module.params.get("worm_policy")
    eradication_mode = module.params.get("eradication_mode")
    if not worm_policy and not eradication_mode:
        return
    fs_name = fsys.name
    if eradication_mode:
        current_mode = getattr(
            getattr(fsys, "eradication_config", None), "eradication_mode", None
        )
        if current_mode != eradication_mode:
            module.fail_json(
                msg="Filesystem {0} has eradication_mode {1}. The eradication "
                "mode can only be set when the filesystem is created.".format(
                    fs_name, current_mode
                )
            )
    if worm_policy:
        member_kwargs = {"member_names": [fs_name]}
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            member_kwargs["context_names"] = [module.params["context"]]
        res = blade.get_file_systems_worm_data_policies(**member_kwargs)
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to get WORM data policy of filesystem {0}. "
                "Error: {1}".format(fs_name, get_error_message(res))
            )
        attached = [
            getattr(getattr(item, "policy", None), "name", None)
            for item in list(res.items)
        ]
        if worm_policy not in attached:
            module.fail_json(
                msg="Filesystem {0} has WORM data policy {1}. A WORM data policy "
                "can only be attached when the filesystem is created.".format(
                    fs_name, ", ".join(name for name in attached if name) or "none"
                )
            )


def modify_fs(module, blade):
    """Modify Filesystem"""
    changed = False
    change_client = False
    change_export = False
    change_share = False
    change_ca = False
    change_go = False
    change_sc = False
    change_rules = False
    mod_fs = False
    # Determine if this is a realm filesystem
    realm_name = None
    if module.params.get("realm"):
        realm_name = module.params["realm"]
    elif "::" in module.params["name"]:
        realm_name = module.params["name"].split("::")[0]
    # Construct filesystem name - if realm provided, prepend realm::
    fs_name = module.params["name"]
    if realm_name and "::" not in fs_name:
        fs_name = "{0}::{1}".format(realm_name, fs_name)
    api_version = get_rest_api_version(blade)
    if module.params["policy"] and module.params["policy_state"] == "present":
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            res = blade.get_policies(
                names=[module.params["policy"]],
                context_names=[module.params["context"]],
            )
        else:
            res = blade.get_policies(names=[module.params["policy"]])
        if res.status_code != 200:
            module.fail_json(
                msg="Policy {0} doesn't exist.".format(module.params["policy"])
            )
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            res = blade.get_policies_file_systems(
                policy_names=[module.params["policy"]],
                member_names=[fs_name],
                context_names=[module.params["context"]],
            )
        else:
            res = blade.get_policies_file_systems(
                policy_names=[module.params["policy"]],
                member_names=[fs_name],
            )
        if not _item_count(res):
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.post_policies_file_systems(
                    policy_names=[module.params["policy"]],
                    member_names=[fs_name],
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.post_policies_file_systems(
                    policy_names=[module.params["policy"]],
                    member_names=[fs_name],
                )
            mod_fs = True
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to add filesystem {0} to policy {1}. Error: {2}".format(
                        fs_name,
                        module.params["policy"],
                        get_error_message(res),
                    )
                )
    if module.params["policy"] and module.params["policy_state"] == "absent":
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            res = blade.get_policies(
                names=[module.params["policy"]],
                context_names=[module.params["context"]],
            )
        else:
            res = blade.get_policies(names=[module.params["policy"]])
        if res.status_code == 200:
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.get_policies_file_systems(
                    policy_names=[module.params["policy"]],
                    member_names=[fs_name],
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.get_policies_file_systems(
                    policy_names=[module.params["policy"]],
                    member_names=[fs_name],
                )
            # A 200 with no items means the policy is not attached, so a
            # second policy_state=absent run must be a no-op.
            if _item_count(res):
                if (
                    LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                    and module.params["context"]
                ):
                    res = blade.delete_policies_file_systems(
                        policy_names=[module.params["policy"]],
                        member_names=[fs_name],
                        context_names=[module.params["context"]],
                    )
                else:
                    res = blade.delete_policies_file_systems(
                        policy_names=[module.params["policy"]],
                        member_names=[fs_name],
                    )
                mod_fs = True
                if res.status_code != 200:
                    module.fail_json(
                        msg="Failed to remove filesystem {0} from policy {1}. Error: {2}".format(
                            fs_name,
                            module.params["policy"],
                            get_error_message(res),
                        )
                    )
    if module.params["user_quota"]:
        user_quota = human_to_bytes(module.params["user_quota"])
    if module.params["group_quota"]:
        group_quota = human_to_bytes(module.params["group_quota"])
    fsys = get_filesystem(module, blade)
    new_fsys = {
        "destroyed": fsys.destroyed,
        "provisioned": fsys.provisioned,
        "nfsv3": fsys.nfs.v3_enabled,
        "nfsv4": fsys.nfs.v4_1_enabled,
        "default_user_quota": fsys.default_user_quota,
        "default_group_quota": fsys.default_group_quota,
        "group_ownership": fsys.group_ownership,
        "smb": fsys.smb.enabled,
        "http": fsys.http.enabled,
        "snapshot": fsys.snapshot_directory_enabled,
        "fastremove": fsys.fast_remove_directory_enabled,
        "hardlimit": fsys.hard_limit_enabled,
        "safeguard_acls": fsys.multi_protocol.safeguard_acls,
        "acs": fsys.multi_protocol.access_control_style,
        "writable": fsys.writable,
        "promotion_status": fsys.promotion_status,
        "requested_promotion_state": fsys.requested_promotion_state,
        "storage_class": getattr(getattr(fsys, "storage_class", None), "name", None),
    }
    if fsys.destroyed:
        new_fsys["destroyed"] = False
        mod_fs = True
    if module.params["size"]:
        if human_to_bytes(module.params["size"]) != fsys.provisioned:
            new_fsys["provisioned"] = human_to_bytes(module.params["size"])
            mod_fs = True
    if module.params["nfsv3"] != fsys.nfs.v3_enabled:
        new_fsys["nfsv3"] = module.params["nfsv3"]
        mod_fs = True
    if module.params["nfsv4"] != fsys.nfs.v4_1_enabled:
        new_fsys["nfsv4"] = module.params["nfsv4"]
        mod_fs = True
    if module.params["user_quota"] and user_quota != fsys.default_user_quota:
        new_fsys["default_user_quota"] = user_quota
        mod_fs = True
    if module.params["group_quota"] and group_quota != fsys.default_group_quota:
        new_fsys["default_group_quota"] = group_quota
        mod_fs = True
    # Boolean flags are only compared when the caller set them, and then in
    # both directions, so an explicit false turns the setting off.
    bool_flags = [
        ("smb", "smb", fsys.smb.enabled),
        ("http", "http", fsys.http.enabled),
        ("snapshot", "snapshot", fsys.snapshot_directory_enabled),
        ("fastremove", "fastremove", fsys.fast_remove_directory_enabled),
        ("hard_limit", "hardlimit", fsys.hard_limit_enabled),
        ("safeguard_acls", "safeguard_acls", fsys.multi_protocol.safeguard_acls),
    ]
    for param, key, current in bool_flags:
        if module.params[param] is not None and module.params[param] != current:
            new_fsys[key] = module.params[param]
            mod_fs = True
    if module.params["access_control"] != fsys.multi_protocol.access_control_style:
        new_fsys["acs"] = module.params["access_control"]
        mod_fs = True
    if module.params["writable"] is not None:
        if not module.params["writable"] and fsys.writable:
            new_fsys["writable"] = module.params["writable"]
            mod_fs = True
        if (
            module.params["writable"]
            and not fsys.writable
            and fsys.promotion_status == "promoted"
        ):
            new_fsys["writable"] = module.params["writable"]
            mod_fs = True
    failover = None
    if module.params["promote"] is not None:
        failover = _failover_action(module, blade, fsys, fs_name)
    if failover == "skip_quiesce" and not module.params["discard_snaps"]:
        module.fail_json(
            msg="Filesystem {0} is demoting. Skipping the planned failover "
            "discards the data not yet replicated; set discard_snaps=true "
            "to confirm.".format(fs_name)
        )
    if module.params["promote"] is not None and failover is None:
        if module.params["promote"] and fsys.promotion_status != "promoted":
            if fsys.promotion_status == "demoting":
                module.fail_json(
                    msg="Filesystem {0} is demoting in a planned failover and "
                    "cannot be promoted directly. Use abort_quiesce=true to "
                    "cancel the failover.".format(fs_name)
                )
            new_fsys["requested_promotion_state"] = "promoted"
            mod_fs = True
        if not module.params["promote"] and fsys.promotion_status == "promoted":
            # Demotion only allowed on filesystems in a replica-link
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.get_file_system_replica_links(
                    local_file_system_names=[fs_name],
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.get_file_system_replica_links(
                    local_file_system_names=[fs_name]
                )
            if res.status_code != 200:
                module.fail_json(
                    msg="Filesystem {0} not demoted. Not in a replica-link".format(
                        fs_name
                    )
                )
            new_fsys["requested_promotion_state"] = "demoted"
            mod_fs = True
    if mod_fs:
        changed = True
        if not module.check_mode:
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                if new_fsys["destroyed"] != fsys.destroyed:
                    delres = blade.patch_file_systems(
                        names=[fs_name],
                        context_names=[module.params["context"]],
                        file_system=FileSystemPatch(destroyed=new_fsys["destroyed"]),
                    )
                    if delres.status_code != 200:
                        module.fail_json(
                            msg="Failed to update filesystem {0} deleted status. Error {1}".format(
                                fs_name, get_error_message(res)
                            )
                        )
                res = blade.patch_file_systems(
                    names=[fs_name],
                    context_names=[module.params["context"]],
                    file_system=FileSystemPatch(
                        default_group_quota=new_fsys["default_group_quota"],
                        default_user_quota=new_fsys["default_user_quota"],
                        fast_remove_directory_enabled=new_fsys["fastremove"],
                        hard_limit_enabled=new_fsys["hardlimit"],
                        snapshot_directory_enabled=new_fsys["snapshot"],
                        http=Http(enabled=new_fsys["http"]),
                        multi_protocol=MultiProtocol(
                            access_control_style=new_fsys["acs"],
                            safeguard_acls=new_fsys["safeguard_acls"],
                        ),
                        nfs=NfsPatch(
                            v3_enabled=new_fsys["nfsv3"],
                            v4_1_enabled=new_fsys["nfsv4"],
                        ),
                        provisioned=new_fsys["provisioned"],
                        requested_promotion_state=new_fsys["requested_promotion_state"],
                        smb=Smb(enabled=new_fsys["smb"]),
                        writable=new_fsys["writable"],
                    ),
                    discard_non_snapshotted_data=module.params["discard_snaps"],
                    ignore_usage=module.params["ignore_usage"],
                )
            else:
                if new_fsys["destroyed"] != fsys.destroyed:
                    delres = blade.patch_file_systems(
                        names=[fs_name],
                        file_system=FileSystemPatch(destroyed=new_fsys["destroyed"]),
                    )
                    if delres.status_code != 200:
                        module.fail_json(
                            msg="Failed to update filesystem {0} deleted status. Error {1}".format(
                                fs_name, get_error_message(res)
                            )
                        )
                res = blade.patch_file_systems(
                    names=[fs_name],
                    file_system=FileSystemPatch(
                        default_group_quota=new_fsys["default_group_quota"],
                        default_user_quota=new_fsys["default_user_quota"],
                        fast_remove_directory_enabled=new_fsys["fastremove"],
                        hard_limit_enabled=new_fsys["hardlimit"],
                        snapshot_directory_enabled=new_fsys["snapshot"],
                        http=Http(enabled=new_fsys["http"]),
                        multi_protocol=MultiProtocol(
                            access_control_style=new_fsys["acs"],
                            safeguard_acls=new_fsys["safeguard_acls"],
                        ),
                        nfs=NfsPatch(
                            v3_enabled=new_fsys["nfsv3"],
                            v4_1_enabled=new_fsys["nfsv4"],
                        ),
                        provisioned=new_fsys["provisioned"],
                        requested_promotion_state=new_fsys["requested_promotion_state"],
                        smb=Smb(enabled=new_fsys["smb"]),
                        writable=new_fsys["writable"],
                    ),
                    discard_non_snapshotted_data=module.params["discard_snaps"],
                    ignore_usage=module.params["ignore_usage"],
                )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to update filesystem {0}. Error {1}".format(
                        fs_name, get_error_message(res)
                    )
                )
    if failover in ("quiesce", "skip_quiesce", "abort_quiesce"):
        changed = True
        if not module.check_mode:
            _patch_failover(module, blade, fs_name, failover)
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and module.params["context"]
    ):
        current_fs = list(
            blade.get_file_systems(
                context_names=[module.params["context"]],
                filter="name='" + fs_name + "'",
            ).items
        )[0]
    else:
        current_fs = list(
            blade.get_file_systems(filter="name='" + fs_name + "'").items
        )[0]
    if (
        LooseVersion(EXPORT_POLICY_API_VERSION) <= LooseVersion(api_version)
        and module.params["export_policy"]
        and (current_fs.nfs.v3_enabled or current_fs.nfs.v4_1_enabled)
    ):
        change_export = False
        if (
            current_fs.nfs.export_policy.name
            and current_fs.nfs.export_policy.name != module.params["export_policy"]
        ):
            change_export = True
        if not current_fs.nfs.export_policy.name and module.params["export_policy"]:
            change_export = True
        if change_export and not module.check_mode:
            export_attr = FileSystemPatch(
                nfs=NfsPatch(
                    export_policy=Reference(name=module.params["export_policy"])
                )
            )
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.patch_file_systems(
                    names=[fs_name],
                    file_system=export_attr,
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.patch_file_systems(names=[fs_name], file_system=export_attr)
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to modify export policy {1} for "
                    "filesystem {0}. Error: {2}".format(
                        fs_name,
                        module.params["export_policy"],
                        get_error_message(res),
                    )
                )
    if module.params["export_policy"] is not None:
        module.deprecate(
            "export_policy is deprecated. Use the purefb_export "
            "module's export_policy option to attach NFS export "
            "policies via the dedicated File System Exports "
            "endpoints.",
            version="2.0.0",
            collection_name="everpure.flashblade",
        )
    if module.params["share_policy"] is not None:
        module.deprecate(
            "share_policy is deprecated. Use the purefb_export "
            "module's share_policy option to attach SMB share "
            "policies via the dedicated File System Exports "
            "endpoints.",
            version="2.0.0",
            collection_name="everpure.flashblade",
        )
    if module.params["client_policy"] is not None:
        module.deprecate(
            "client_policy is deprecated. Use the purefb_export "
            "module's client_policy option to attach SMB client "
            "policies via the dedicated File System Exports "
            "endpoints.",
            version="2.0.0",
            collection_name="everpure.flashblade",
        )
    if module.params["nfs_rules"] is not None:
        module.deprecate(
            "nfs_rules is deprecated. Use the purefb_export module to attach "
            "NFS export policies via the File System Exports endpoints.",
            version="2.0.0",
            collection_name="everpure.flashblade",
        )
        if realm_name:
            module.warn(
                "nfs_rules is not supported for realm filesystems and "
                "will be ignored."
            )
        elif getattr(current_fs.nfs, "rules", None) != module.params["nfs_rules"]:
            change_rules = True
            if not module.check_mode:
                rules_attr = FileSystemPatch(
                    nfs=NfsPatch(rules=module.params["nfs_rules"])
                )
                if (
                    LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                    and module.params["context"]
                ):
                    res = blade.patch_file_systems(
                        names=[fs_name],
                        file_system=rules_attr,
                        context_names=[module.params["context"]],
                    )
                else:
                    res = blade.patch_file_systems(
                        names=[fs_name], file_system=rules_attr
                    )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Failed to modify nfs_rules for "
                        "filesystem {0}. Error: {1}".format(
                            fs_name,
                            get_error_message(res),
                        )
                    )
    if (
        LooseVersion(SMB_POLICY_API_VERSION) <= LooseVersion(api_version)
        and module.params["client_policy"]
        and current_fs.smb.enabled
    ):
        if (
            current_fs.smb.client_policy.name
            and current_fs.smb.client_policy.name != module.params["client_policy"]
        ):
            change_client = True
        if not current_fs.smb.client_policy.name and module.params["client_policy"]:
            change_client = True
        if change_client and not module.check_mode:
            client_attr = FileSystemPatch(
                smb=Smb(client_policy=Reference(name=module.params["client_policy"]))
            )
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.patch_file_systems(
                    names=[fs_name],
                    file_system=client_attr,
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.patch_file_systems(names=[fs_name], file_system=client_attr)
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to modify client policy {1} for "
                    "filesystem {0}. Error: {2}".format(
                        fs_name,
                        module.params["client_policy"],
                        get_error_message(res),
                    )
                )
    if (
        LooseVersion(SMB_POLICY_API_VERSION) <= LooseVersion(api_version)
        and module.params["share_policy"]
        and current_fs.smb.enabled
    ):
        if (
            current_fs.smb.share_policy.name
            and current_fs.smb.share_policy.name != module.params["share_policy"]
        ):
            change_share = True
        if not current_fs.smb.share_policy.name and module.params["share_policy"]:
            change_share = True
        if change_share and not module.check_mode:
            share_attr = FileSystemPatch(
                smb=Smb(share_policy=Reference(name=module.params["share_policy"]))
            )
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.patch_file_systems(
                    names=[fs_name],
                    file_system=share_attr,
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.patch_file_systems(names=[fs_name], file_system=share_attr)
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to modify share policy {1} for "
                    "filesystem {0}. Error: {2}".format(
                        fs_name,
                        module.params["share_policy"],
                        get_error_message(res),
                    )
                )
    if (
        LooseVersion(CA_API_VERSION) <= LooseVersion(api_version)
        and current_fs.smb.enabled
    ):
        if (
            module.params["continuous_availability"]
            != current_fs.smb.continuous_availability_enabled
        ):
            change_ca = True
        if not module.check_mode and change_ca:
            ca_attr = FileSystemPatch(
                smb=Smb(
                    continuous_availability_enabled=module.params[
                        "continuous_availability"
                    ]
                )
            )
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.patch_file_systems(
                    names=[fs_name],
                    file_system=ca_attr,
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.patch_file_systems(names=[fs_name], file_system=ca_attr)
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to modify continuous availability for "
                    "filesystem {0}. Error: {1}".format(
                        fs_name,
                        get_error_message(res),
                    )
                )
    if LooseVersion(GOWNER_API_VERSION) <= LooseVersion(api_version):
        if module.params["group_ownership"] != current_fs.group_ownership:
            change_go = True
        if not module.check_mode and change_go:
            go_attr = FileSystemPatch(group_ownership=module.params["group_ownership"])
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.patch_file_systems(
                    names=[fs_name],
                    file_system=go_attr,
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.patch_file_systems(names=[fs_name], file_system=go_attr)
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to modify group ownership for "
                    "filesystem {0}. Error: {1}".format(
                        fs_name,
                        get_error_message(res),
                    )
                )
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and module.params["storage_class"]
    ):
        # The array reports storage_class as an object, so only its name is
        # comparable. Platforms without storage classes return the object
        # with no name and reject any storage class PATCH, so the PATCH is
        # only sent when the requested class differs from the current one.
        current_sc = getattr(getattr(current_fs, "storage_class", None), "name", None)
        if module.params["storage_class"] != current_sc:
            change_sc = True
            if not module.check_mode:
                sc_patch = {
                    "names": [fs_name],
                    "file_system": FileSystemPatch(
                        storage_class=StorageClassInfo(
                            name=module.params["storage_class"]
                        )
                    ),
                    "cancel_in_progress_storage_class_transition": module.params[
                        "cancel_in_progress"
                    ],
                }
                if module.params["context"]:
                    sc_patch["context_names"] = [module.params["context"]]
                res = blade.patch_file_systems(**sc_patch)
                if res.status_code != 200:
                    module.fail_json(
                        msg="Failed to modify storage class for "
                        "filesystem {0}. Error: {1}".format(
                            fs_name,
                            get_error_message(res),
                        )
                    )

    module.exit_json(
        changed=(
            changed
            or change_export
            or change_share
            or change_ca
            or change_go
            or change_sc
            or change_client
            or change_rules
        )
    )


def _delete_fs(module, blade):
    """In module Delete Filesystem"""
    # Determine if this is a realm filesystem
    realm_name = None
    if module.params.get("realm"):
        realm_name = module.params["realm"]
    elif "::" in module.params["name"]:
        realm_name = module.params["name"].split("::")[0]
    # Construct filesystem name - if realm provided, prepend realm::
    fs_name = module.params["name"]
    if realm_name and "::" not in fs_name:
        fs_name = "{0}::{1}".format(realm_name, fs_name)
    res = blade.patch_file_systems(
        names=[fs_name],
        file_system=FileSystemPatch(
            nfs=NfsPatch(v3_enabled=False, v4_1_enabled=False),
            smb=Smb(enabled=False),
            http=Http(enabled=False),
            multi_protocol=MultiProtocol(access_control_style="shared"),
            destroyed=True,
        ),
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to delete filesystem {0}. Error: {1}".format(
                fs_name, get_error_message(res)
            )
        )

    res = blade.delete_file_systems(names=[fs_name])
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to eradicate deleted filesystem {0}. Error: {1}".format(
                fs_name, get_error_message(res)
            )
        )


def delete_fs(module, blade):
    """Delete Filesystem"""
    # Determine if this is a realm filesystem
    realm_name = None
    if module.params.get("realm"):
        realm_name = module.params["realm"]
    elif "::" in module.params["name"]:
        realm_name = module.params["name"].split("::")[0]
    # Construct filesystem name - if realm provided, prepend realm::
    fs_name = module.params["name"]
    if realm_name and "::" not in fs_name:
        fs_name = "{0}::{1}".format(realm_name, fs_name)
    changed = True
    if not module.check_mode:
        res = blade.patch_file_systems(
            names=[fs_name],
            file_system=FileSystemPatch(
                nfs=NfsPatch(v3_enabled=False, v4_1_enabled=False),
                smb=Smb(enabled=False),
                http=Http(enabled=False),
                destroyed=True,
            ),
            delete_link_on_eradication=module.params["delete_link"],
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete filesystem {0}. Error: {1}".format(
                    fs_name, get_error_message(res)
                )
            )
        if module.params["eradicate"]:
            res = blade.delete_file_systems(names=[fs_name])
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to eradicate filesystem {0}. Error: {1}".format(
                        fs_name, get_error_message(res)
                    )
                )
    module.exit_json(changed=changed)


def eradicate_fs(module, blade):
    """Eradicate Filesystem"""
    # Determine if this is a realm filesystem
    realm_name = None
    if module.params.get("realm"):
        realm_name = module.params["realm"]
    elif "::" in module.params["name"]:
        realm_name = module.params["name"].split("::")[0]
    # Construct filesystem name - if realm provided, prepend realm::
    fs_name = module.params["name"]
    if realm_name and "::" not in fs_name:
        fs_name = "{0}::{1}".format(realm_name, fs_name)
    changed = True
    if not module.check_mode:
        res = blade.delete_file_systems(names=[fs_name])
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to eradicate filesystem {0}. Error: {1}".format(
                    fs_name, get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str", required=True),
            eradicate=dict(default="false", type="bool"),
            nfsv3=dict(default="true", type="bool"),
            nfsv4=dict(default="true", type="bool"),
            nfs_rules=dict(type="str"),
            smb=dict(type="bool"),
            http=dict(type="bool"),
            snapshot=dict(type="bool"),
            writable=dict(type="bool"),
            promote=dict(type="bool"),
            quiesce=dict(type="bool"),
            abort_quiesce=dict(type="bool", default=False),
            fastremove=dict(type="bool"),
            hard_limit=dict(type="bool"),
            user_quota=dict(type="str"),
            policy=dict(type="str"),
            group_quota=dict(type="str"),
            smb_aclmode=dict(
                type="str", default="shared", choices=["shared", "native"]
            ),
            group_ownership=dict(
                choices=["creator", "parent-directory"], default="creator"
            ),
            policy_state=dict(default="present", choices=["present", "absent"]),
            worm_policy=dict(type="str"),
            eradication_mode=dict(
                type="str", choices=["permission-based", "retention-based"]
            ),
            state=dict(default="present", choices=["present", "absent"]),
            delete_link=dict(default=False, type="bool"),
            discard_snaps=dict(default=False, type="bool"),
            safeguard_acls=dict(type="bool"),
            access_control=dict(
                type="str",
                default="shared",
                choices=["nfs", "smb", "shared", "independent", "mode-bits"],
            ),
            size=dict(type="str"),
            export_policy=dict(type="str"),
            share_policy=dict(type="str"),
            client_policy=dict(type="str"),
            continuous_availability=dict(type="bool", default="true"),
            ignore_usage=dict(type="bool", default=False),
            cancel_in_progress=dict(type="bool", default=False),
            context=dict(type="str", default=""),
            storage_class=dict(type="str"),
            realm=dict(type="str"),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    state = module.params["state"]
    # Resolve the name once, before anything is read. With realm set a short
    # name means realm::name and nothing else, so a filesystem of the same
    # name outside the realm is never read, compared against or changed.
    # Every later read and write uses module.params["name"].
    module.params["name"] = _resolve_name(module)
    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if module.params.get("quiesce") is not None or module.params.get("abort_quiesce"):
        # Planned failover controls: gate and validate before any write.
        if LooseVersion(QUIESCE_API_VERSION) > LooseVersion(api_version):
            module.fail_json(
                msg="Planned failover (quiesce, abort_quiesce) requires "
                "Purity//FB 4.8.4+ (REST API {0}+)".format(QUIESCE_API_VERSION)
            )
        if (
            module.params.get("quiesce") is not None
            and module.params["promote"] is not False
        ):
            module.fail_json(msg="quiesce is only valid with promote=false")
        if module.params.get("abort_quiesce") and not module.params["promote"]:
            module.fail_json(msg="abort_quiesce is only valid with promote=true")
    if (
        module.params.get("worm_policy") or module.params.get("eradication_mode")
    ) and LooseVersion(WORM_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg="worm_policy and eradication_mode require Purity//FB REST API "
            "{0} or later".format(WORM_API_VERSION)
        )
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and not module.params["context"]
    ):
        # Only default the context to the local array name when this array is a
        # member of a fleet. A standalone array is "not in a fleet" and rejects
        # fleet context, so leave context unset - no context_names is then sent.
        fleet_res = blade.get_fleets()
        if fleet_res.status_code == 200 and list(fleet_res.items):
            module.params["context"] = list(blade.get_arrays().items)[0].name

    # Check if filesystem exists, under the name resolved above
    fsys = get_filesystem(module, blade)

    if module.params["eradicate"] and state == "present":
        module.warn("Eradicate flag ignored without state=absent")

    if module.params["smb_aclmode"] == "native":
        module.fail_json(
            msg="Native SMB ACL mode is no longer supported. "
            "Use the access_control parameter."
        )
    if state == "present" and not fsys:
        create_fs(module, blade)
    elif state == "present" and fsys:
        _check_create_only_options(module, blade, fsys, api_version)
        modify_fs(module, blade)
    elif state == "absent" and fsys and not fsys.destroyed:
        delete_fs(module, blade)
    elif state == "absent" and fsys and fsys.destroyed and module.params["eradicate"]:
        eradicate_fs(module, blade)
    elif state == "absent" and not fsys:
        module.exit_json(changed=False)
    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
