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

DOCUMENTATION = r"""
---
module: purefb_snap
version_added: '1.0.0'
short_description: Manage filesystem snapshots on Everpure FlashBlades
description:
- Create or delete volumes and filesystem snapshots on Everpure FlashBlades.
- Restoring a filesystem uses the snapshot named by I(suffix) when one is
  given, otherwise the latest snapshot of the filesystem.
- Copying a snapshot (I(state=copy)) creates a new writable filesystem,
  named by I(target_fs), holding the snapshot's data. The snapshot is the
  one named by I(suffix) when one is given, otherwise the latest snapshot
  of the filesystem. Requires Purity//FB 4.8.0 (REST API 2.25) or higher.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - The name of the source filesystem.
    - For a filesystem in a realm use C(realm::name); the snapshot is then
      C(realm::name.suffix). The same name without the realm is a different
      filesystem at the array level.
    - A realm-scoped administrator must use the realm-qualified name; a bare
      name is not placed in, or resolved to, the administrator's realm.
    - This is the name of one filesystem. A I(name), I(suffix) or
      I(target_fs) that holds a C(*) or a comma, which the array reads as
      a pattern or as a list of names, is refused.
    required: true
    type: str
  suffix:
    description:
    - Suffix of snapshot name.
    - With I(state=restore) or I(state=copy), names the snapshot to use.
      If not given the latest snapshot of the filesystem is used.
    type: str
  state:
    description:
    - Define whether the filesystem snapshot should exist or not.
    - I(restore) overwrites filesystem I(name) with the snapshot's data.
    - I(copy) creates the new filesystem I(target_fs) from the snapshot.
    - I(present), I(restore) and I(copy) fail when filesystem I(name) does
      not exist. I(absent) reports no change.
    choices: [ absent, present, restore, copy ]
    default: present
    type: str
  target:
    aliases: [ targets ]
    description:
    - Name of target to replicate snapshot to.
    - This is only applicable when I(now) is B(true)
    type: str
    version_added: "1.7.0"
  target_fs:
    description:
    - Name of the new filesystem to create from the snapshot with
      I(state=copy).
    - The new filesystem must be in the same realm as I(name), so it is
      C(realm::name) for a source in a realm and a name without a realm
      for an array-level source. Any other name is refused, in check mode
      as well.
    - The copy is created with the settings the array assigns to a
      filesystem copy, which is an unlimited size with its protocols
      disabled and no exports; enable access with
      M(everpure.flashblade.purefb_fs) afterwards.
    - The array takes a baseline snapshot of the copy. While the copy
      exists neither that snapshot nor the source snapshot can be
      destroyed, and once the copy is eradicated the source snapshot
      stays a baseline snapshot that only I(latest_replica=true) destroys.
    - The array may allow only one copy per source filesystem, and a
      destroyed but not yet eradicated copy counts towards that limit;
      the task fails with the array's message when the limit is reached.
      Filesystems created before Purity//FB 3.0 cannot be copied.
      Purity//FB 4.8.5 or higher is recommended.
    - If I(target_fs) already exists and is a copy of I(name) the task
      reports no change. Any other existing filesystem is never
      overwritten and the task fails.
    - Requires Purity//FB 4.8.0 (REST API 2.25) or higher.
    type: str
    version_added: '1.30.0'
  now:
    description:
    - Whether to initiate a snapshot replication immeadiately
    type: bool
    default: false
    version_added: "1.7.0"
  eradicate:
    description:
    - Define whether to eradicate the snapshot on delete or leave in trash.
    type: bool
    default: false
  latest_replica:
    description:
    - Used when destroying a snapshot.
    - If false, and the snapshot is the
      latest replicated snapshot, then destroy will fail.
    - If true or the snapshot is not the latest replicated snapshot,
      then destroy will be successful.
    type: bool
    default: false
    version_added: "1.21.0"
  context:
    description:
    - Name of fleet member on which to perform the operation.
    - This requires the array receiving the request is a member of a fleet
      and the context name to be a member of the same fleet.
    type: str
    default: ""
    version_added: "1.22.0"
  detach_policies:
    description:
    - Names of snapshot policies to detach from the snapshot named by
      I(name) and I(suffix). Only valid with I(state=present) on an
      existing snapshot that is not destroyed.
    - Detaching is one-way. The array has no call to attach a snapshot to
      a policy again, so a detached snapshot is no longer subject to the
      policy's retention and stays until it is destroyed.
    - A policy that is not attached to the snapshot is ignored, so a
      second run reports no change. An empty list detaches nothing.
    - Each policy is detached with its own request. The array may refuse
      one, for example a retention-locked (SafeMode) policy or a
      replication baseline snapshot; the task then fails naming that
      policy with the array's message, and the policies detached before
      it stay detached.
    - Policies in a realm are matched on their full C(realm::policy) name.
    type: list
    elements: str
    version_added: '1.30.0'
  detach_all_policies:
    description:
    - Detach the snapshot named by I(name) and I(suffix) from every
      snapshot policy attached to it. Mutually exclusive with
      I(detach_policies), which describes the behaviour.
    type: bool
    default: false
    version_added: '1.30.0'
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Create snapshot foo.ansible
  everpure.flashblade.purefb_snap:
    name: foo
    suffix: ansible
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592
    state: present

- name: Create snapshot tenant1::foo.ansible of filesystem foo in realm tenant1
  everpure.flashblade.purefb_snap:
    name: tenant1::foo
    suffix: ansible
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592
    state: present

- name: Create immeadiate snapshot foo.ansible to connected FB bar
  everpure.flashblade.purefb_snap:
    name: foo
    suffix: ansible
    now: true
    target: bar
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592
    state: present

- name: Delete snapshot named foo.snap
  everpure.flashblade.purefb_snap:
    name: foo
    suffix: snap
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592
    state: absent

- name: Recover deleted snapshot foo.ansible
  everpure.flashblade.purefb_snap:
    name: foo
    suffix: ansible
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592
    state: present

- name: Restore filesystem foo (uses latest snapshot)
  everpure.flashblade.purefb_snap:
    name: foo
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592
    state: restore

- name: Restore filesystem foo from snapshot foo.ansible
  everpure.flashblade.purefb_snap:
    name: foo
    suffix: ansible
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592
    state: restore

- name: Create writable filesystem foo_copy from snapshot foo.ansible
  everpure.flashblade.purefb_snap:
    name: foo
    suffix: ansible
    target_fs: foo_copy
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592
    state: copy

- name: Create writable filesystem tenant1::foo_copy from snapshot tenant1::foo.ansible
  everpure.flashblade.purefb_snap:
    name: tenant1::foo
    suffix: ansible
    target_fs: tenant1::foo_copy
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592
    state: copy

- name: Eradicate snapshot named foo.snap
  everpure.flashblade.purefb_snap:
    name: foo
    suffix: snap
    eradicate: true
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592
    state: absent

- name: Detach policy snapshot foo.2026_01_01_00_00 from snapshot policy daily
  everpure.flashblade.purefb_snap:
    name: foo
    suffix: 2026_01_01_00_00
    detach_policies:
      - daily
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592
    state: present

- name: Detach policy snapshot foo.2026_01_01_00_00 from all its snapshot policies
  everpure.flashblade.purefb_snap:
    name: foo
    suffix: 2026_01_01_00_00
    detach_all_policies: true
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592
    state: present
"""

RETURN = r"""
promotion_status:
  description:
  - Promotion state of the filesystem created with I(state=copy). The
    array reports C(promoting) while the copy is in progress and
    C(promoted) once it is complete.
  returned: when I(state=copy)
  type: str
  sample: promoting
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
    get_error_message,
    get_rest_api_version,
)

from datetime import datetime

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        FileSystemSnapshotPost,
        FileSystemSnapshot,
        FileSystemPost,
        Reference,
    )
except ImportError:
    HAS_PYPURECLIENT = False

SNAP_NOW_API = "2.10"
CONTEXT_API_VERSION = "2.17"
COPY_API_VERSION = "2.25"


def _realm_of(name):
    """Return the realm of a realm::name name, empty for an array-level name."""
    return name.rpartition("::")[0]


def _check_names(module):
    """Take name, suffix and target_fs as the name of one object each.

    In a look-up the array reads * in a name as a pattern and a comma as a
    separator of names, and answers with every object that matches. It does
    not do so in a change, so a task with such a name could only report on
    an object that the array then does not act on, and is refused before
    anything is read. The array ignores blanks around a name; they are
    removed here because the name of a snapshot is built from name.
    """
    for option in ("name", "target_fs"):
        if module.params[option]:
            module.params[option] = module.params[option].strip()
    for option in ("name", "suffix", "target_fs"):
        value = module.params[option]
        if value and ("*" in value or "," in value):
            module.fail_json(
                msg="{0} {1} is not the name of one filesystem or snapshot: the "
                "array reads * as a pattern and a comma as a separator of "
                "names.".format(option, value)
            )


def _context_kwargs(module, blade):
    """Return context_names kwargs when a fleet context applies."""
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(get_rest_api_version(blade))
        and module.params["context"]
    ):
        return {"context_names": [module.params["context"]]}
    return {}


def _first_item(module, res, what):
    """Return the first item of a read, or None when the object is absent.

    Only the array's answer that the object does not exist means absent. Any
    other answer that is not a success, such as a read the array refuses to
    the identity in use, fails the task with the array's message.
    """
    if res.status_code == 200:
        items = list(res.items)
        return items[0] if items else None
    error = get_error_message(res)
    if "does not exist" in str(error).lower():
        return None
    module.fail_json(msg="Failed to get {0}. Error: {1}".format(what, error))
    return None


def _get_filesystem(module, blade):
    """Return the filesystem named by name, or None when it does not exist"""
    res = blade.get_file_systems(
        names=[module.params["name"]], **_context_kwargs(module, blade)
    )
    return _first_item(module, res, "filesystem {0}".format(module.params["name"]))


def _check_copy_scope(module):
    """Refuse a copy whose target is not in the realm of its source.

    The array creates the copy of a filesystem only in the realm of that
    filesystem, and outside of any realm for an array-level filesystem. The
    names decide it, so the request is refused in check mode as well.

    The array finds a realm whatever the letter case of its name, but it
    compares the realm of a new filesystem with the realm of the source as
    the name is written. name holds the name the array has for the source,
    so a target in the same realm is given the realm as it is written there.
    """
    name = module.params["name"]
    target_name = module.params["target_fs"]
    realm = _realm_of(name)
    target_realm, _sep, target_leaf = target_name.rpartition("::")
    if target_realm.lower() == realm.lower():
        if target_realm != realm:
            module.params["target_fs"] = "{0}::{1}".format(realm, target_leaf)
        return
    if realm:
        where = "in realm {0}, named {0}::<name>".format(realm)
    else:
        where = "outside of any realm, named without a realm"
    module.fail_json(
        msg="target_fs {0} must be in the same realm as the source filesystem "
        "{1}. A copy of {1} can only be created {2}.".format(target_name, name, where)
    )


def _is_copy_of(target, filesystem, name):
    """Return True when the filesystem target is a copy of filesystem.

    The array reports the source of a copy by its name without the realm,
    which filesystems of that name in other realms and at the array level
    share, and in the letter case it was created with. The ID of the source
    is exact, so it decides. Where the array reports no ID the full name of
    the source is compared, then its name.
    """
    source = getattr(target, "source", None)
    source_id = getattr(source, "id", None)
    filesystem_id = getattr(filesystem, "id", None)
    if source_id and filesystem_id:
        return source_id == filesystem_id
    display_name = getattr(source, "display_name", None)
    if display_name:
        return display_name.lower() == name.lower()
    source_name = getattr(source, "name", None)
    if not source_name:
        return False
    return source_name.lower() in (name.lower(), name.rpartition("::")[2].lower())


def get_latest_fssnapshot(module, blade):
    """Get the name of the latest snpshot or None"""
    api_version = get_rest_api_version(blade)
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and module.params["context"]
    ):
        res = blade.get_file_system_snapshots(
            names_or_owner_names=[module.params["name"]],
            context_names=[module.params["context"]],
        )
    else:
        res = blade.get_file_system_snapshots(
            names_or_owner_names=[module.params["name"]]
        )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to get filesystem snapshots. Error: {0}".format(
                get_error_message(res)
            )
        )
    all_snaps = list(res.items)
    if not all_snaps:
        return None
    # SDK models are attribute objects, not dicts, so sort on the attribute.
    last_snap = sorted(all_snaps, key=lambda x: getattr(x, "created", 0) or 0)[-1]
    if not last_snap.destroyed:
        return last_snap.name
    module.fail_json(
        msg="Latest snapshot {0} is destroyed."
        " Eradicate or recover this first.".format(last_snap.name)
    )
    return None


def get_fssnapshot(module, blade):
    """Return Snapshot or None"""
    snapname = module.params["name"] + "." + module.params["suffix"]
    res = blade.get_file_system_snapshots(
        names_or_owner_names=[snapname], **_context_kwargs(module, blade)
    )
    return _first_item(module, res, "snapshot {0}".format(snapname))


def get_target_filesystem(module, blade):
    """Return the filesystem named by target_fs, or None"""
    res = blade.get_file_systems(
        names=[module.params["target_fs"]], **_context_kwargs(module, blade)
    )
    return _first_item(module, res, "filesystem {0}".format(module.params["target_fs"]))


def create_snapshot(module, blade):
    """Create Snapshot"""
    api_version = get_rest_api_version(blade)
    changed = False
    # Special case as we have changed 'target' to be a string not a list of one string
    # so this provides backwards compatability
    # target = module.params["target"].replace("[", "").replace("'", "").replace("]", "")
    if module.params["target"]:
        # The array connections are only needed to check a target
        blade_exists = False
        res = blade.get_array_connections(**_context_kwargs(module, blade))
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to get the array connections to check target {0}. "
                "Error: {1}".format(module.params["target"], get_error_message(res))
            )
        for rem_blade in list(res.items):
            if (
                module.params["target"] == rem_blade.remote.name
                and rem_blade.status == "connected"
            ):
                blade_exists = True
                break
        if not blade_exists:
            module.fail_json(msg="Selected target is not a correctly connected system")
    changed = True
    if not module.check_mode:
        if module.params["target"]:
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.post_file_system_snapshots(
                    source_names=[module.params["name"]],
                    send=module.params["now"],
                    targets=[module.params["target"]],
                    file_system_snapshot=FileSystemSnapshotPost(
                        suffix=module.params["suffix"]
                    ),
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.post_file_system_snapshots(
                    source_names=[module.params["name"]],
                    send=module.params["now"],
                    targets=[module.params["target"]],
                    file_system_snapshot=FileSystemSnapshotPost(
                        suffix=module.params["suffix"]
                    ),
                )
        else:
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.post_file_system_snapshots(
                    source_names=[module.params["name"]],
                    file_system_snapshot=FileSystemSnapshotPost(
                        suffix=module.params["suffix"]
                    ),
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.post_file_system_snapshots(
                    source_names=[module.params["name"]],
                    file_system_snapshot=FileSystemSnapshotPost(
                        suffix=module.params["suffix"]
                    ),
                )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to create remote snapshot. Error: {0}".format(
                    get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def restore_snapshot(module, blade, snap=None):
    """Restore a filesystem from a snapshot.

    When the caller named a suffix, ``snap`` is that snapshot (or None if it
    does not exist) and it is used as the source. Without a suffix the
    latest snapshot of the filesystem is used.
    """
    changed = True
    api_version = get_rest_api_version(blade)
    if module.params["suffix_given"]:
        snapname = module.params["name"] + "." + module.params["suffix"]
        if snap is None:
            module.fail_json(
                msg="Snapshot {0} does not exist, cannot restore from it.".format(
                    snapname
                )
            )
        if snap.destroyed:
            module.fail_json(
                msg="Snapshot {0} is destroyed. Recover it before restoring.".format(
                    snapname
                )
            )
    else:
        snapname = get_latest_fssnapshot(module, blade)
    if snapname is not None:
        if not module.check_mode:
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.post_file_systems(
                    names=[module.params["name"]],
                    overwrite=True,
                    discard_non_snapshotted_data=True,
                    file_system=FileSystemPost(source=Reference(name=snapname)),
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.post_file_systems(
                    names=[module.params["name"]],
                    overwrite=True,
                    discard_non_snapshotted_data=True,
                    file_system=FileSystemPost(source=Reference(name=snapname)),
                )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to restore snapshot {0} to filesystem {1}. Error: {2}".format(
                        snapname, module.params["name"], get_error_message(res)
                    )
                )
    else:
        module.fail_json(
            msg="Filesystem {0} has no snapshots to restore from.".format(
                module.params["name"]
            )
        )
    module.exit_json(changed=changed)


def copy_snapshot(module, blade, filesystem, snap=None):
    """Create a new writable filesystem from a snapshot.

    The snapshot is the one named by ``suffix`` when the caller gave one
    (``snap``, or None if it does not exist), otherwise the latest snapshot
    of the filesystem. The target is created with ``include_snapshot`` so
    the array copies the snapshot's data into it. A target that already
    exists as a copy of the source is left alone; any other existing
    filesystem is never overwritten.
    """
    api_version = get_rest_api_version(blade)
    if filesystem is None:
        module.fail_json(
            msg="Filesystem {0} does not exist, cannot copy a snapshot of it.".format(
                module.params["name"]
            )
        )
    _check_copy_scope(module)
    if module.params["suffix_given"]:
        snapname = module.params["name"] + "." + module.params["suffix"]
        if snap is None:
            module.fail_json(
                msg="Snapshot {0} does not exist, cannot copy from it.".format(snapname)
            )
        if snap.destroyed:
            module.fail_json(
                msg="Snapshot {0} is destroyed. Recover it before copying.".format(
                    snapname
                )
            )
    else:
        snapname = get_latest_fssnapshot(module, blade)
        if snapname is None:
            module.fail_json(
                msg="Filesystem {0} has no snapshots to copy from.".format(
                    module.params["name"]
                )
            )
    target_name = module.params["target_fs"]
    target = get_target_filesystem(module, blade)
    changed = False
    promotion_status = None
    if target is None:
        changed = True
        if not module.check_mode:
            post_kwargs = {
                "names": [target_name],
                "include_snapshot": True,
                "file_system": FileSystemPost(source=Reference(name=snapname)),
            }
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                post_kwargs["context_names"] = [module.params["context"]]
            if "::" in target_name:
                # Realm-scoped filesystems are created without default exports
                post_kwargs["default_exports"] = ["''"]
            res = blade.post_file_systems(**post_kwargs)
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to copy snapshot {0} to new filesystem {1}. Error: {2}".format(
                        snapname, target_name, get_error_message(res)
                    )
                )
            items = list(res.items)
            if items:
                promotion_status = getattr(items[0], "promotion_status", None)
    else:
        name = module.params["name"]
        is_copy = _is_copy_of(target, filesystem, name)
        if target.destroyed and is_copy:
            module.fail_json(
                msg="Filesystem {0} exists but is destroyed. "
                "Recover or eradicate it before copying to it.".format(target_name)
            )
        if target.destroyed:
            module.fail_json(
                msg="Filesystem {0} exists but is destroyed and is not a copy of {1}. "
                "Eradicate it before copying to it; existing filesystems "
                "are not overwritten.".format(target_name, name)
            )
        if not is_copy:
            module.fail_json(
                msg="Filesystem {0} already exists and is not a copy of {1}. "
                "Existing filesystems are not overwritten.".format(target_name, name)
            )
        promotion_status = getattr(target, "promotion_status", None)
    module.exit_json(changed=changed, promotion_status=promotion_status)


def recover_snapshot(module, blade):
    """Recover deleted Snapshot"""
    changed = True
    api_version = get_rest_api_version(blade)
    if not module.check_mode:
        snapname = module.params["name"] + "." + module.params["suffix"]
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            res = blade.patch_file_system_snapshots(
                names=[snapname],
                file_system_snapshot=FileSystemSnapshot(destroyed=False),
                context_names=[module.params["context"]],
            )
        else:
            res = blade.patch_file_system_snapshots(
                names=[snapname],
                file_system_snapshot=FileSystemSnapshot(destroyed=False),
            )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to recover snapshot {0} for filesystem {1}. Error: {2}".format(
                    snapname, module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def update_snapshot(module, blade):
    """Update Snapshot"""
    changed = False
    module.exit_json(changed=changed)


def _attached_policy_names(snap):
    """Return the names of the snapshot policies attached to a snapshot.

    REST 2.12 and later report every attached policy in ``policies``;
    earlier versions report the single policy in ``policy``.
    """
    names = []
    for policy in getattr(snap, "policies", None) or []:
        policy_name = getattr(policy, "name", None)
        if policy_name and policy_name not in names:
            names.append(policy_name)
    if not names:
        policy_name = getattr(getattr(snap, "policy", None), "name", None)
        if policy_name:
            names.append(policy_name)
    return names


def detach_snapshot_policies(module, blade, snap):
    """Detach a snapshot from snapshot policies.

    The snapshot is the one named by ``name`` and ``suffix``. Detaching is
    one-way (the array has no call to attach a snapshot to a policy again),
    so only the policies still attached are sent and a rerun is a no-op.
    Each policy is sent in its own request: a refusal by the array, for
    example for a retention-locked policy or a replication baseline
    snapshot, names that policy and leaves the earlier detaches in place.
    """
    api_version = get_rest_api_version(blade)
    # Checked here, not with mutually_exclusive: Ansible counts supplied
    # keys, which would reject an explicit detach_all_policies=false.
    if module.params["detach_policies"] and module.params["detach_all_policies"]:
        module.fail_json(
            msg="detach_policies and detach_all_policies are mutually exclusive."
        )
    if module.params["state"] != "present":
        module.fail_json(
            msg="detach_policies and detach_all_policies require state=present."
        )
    if not module.params["suffix_given"]:
        module.fail_json(msg="suffix is required to detach policies from a snapshot.")
    snapname = module.params["name"] + "." + module.params["suffix"]
    if snap is None:
        module.fail_json(
            msg="Snapshot {0} does not exist, cannot detach policies from it.".format(
                snapname
            )
        )
    if snap.destroyed:
        module.fail_json(
            msg="Snapshot {0} is destroyed. Recover it before detaching policies.".format(
                snapname
            )
        )
    attached = _attached_policy_names(snap)
    if module.params["detach_all_policies"]:
        to_detach = attached
    else:
        to_detach = []
        for policy_name in module.params["detach_policies"]:
            if policy_name in attached and policy_name not in to_detach:
                to_detach.append(policy_name)
    changed = bool(to_detach)
    if changed and not module.check_mode:
        kwargs = {"member_names": [snapname]}
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            kwargs["context_names"] = [module.params["context"]]
        for policy_name in to_detach:
            res = blade.delete_file_system_snapshots_policies(
                policy_names=[policy_name], **kwargs
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to detach policy {0} from snapshot {1}. Error: {2}".format(
                        policy_name, snapname, get_error_message(res)
                    )
                )
    module.exit_json(changed=changed)


def delete_snapshot(module, blade):
    """Delete Snapshot"""
    changed = True
    api_version = get_rest_api_version(blade)
    if not module.check_mode:
        snapname = module.params["name"] + "." + module.params["suffix"]
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            res = blade.patch_file_system_snapshots(
                names=[snapname],
                latest_replica=module.params["latest_replica"],
                file_system_snapshot=FileSystemSnapshot(destroyed=True),
                context_names=[module.params["context"]],
            )
        else:
            res = blade.patch_file_system_snapshots(
                names=[snapname],
                latest_replica=module.params["latest_replica"],
                file_system_snapshot=FileSystemSnapshot(destroyed=True),
            )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete snapshot {0}. Error: {1}".format(
                    snapname, get_error_message(res)
                )
            )
        if module.params["eradicate"]:
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.delete_file_system_snapshots(
                    names=[snapname], context_names=[module.params["context"]]
                )
            else:
                res = blade.delete_file_system_snapshots(names=[snapname])
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to eradicate snapshot {0}. Error: {1}".format(
                        snapname, get_error_message(res)
                    )
                )
    module.exit_json(changed=changed)


def eradicate_snapshot(module, blade):
    """Eradicate Snapshot"""
    changed = True
    api_version = get_rest_api_version(blade)
    if not module.check_mode:
        snapname = module.params["name"] + "." + module.params["suffix"]
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            res = blade.delete_file_system_snapshots(
                names=[snapname], context_names=[module.params["context"]]
            )
        else:
            res = blade.delete_file_system_snapshots(names=[snapname])
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to eradicate snapshot {0}. Error: {1}".format(
                    snapname, get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(required=True),
            suffix=dict(type="str"),
            now=dict(type="bool", default=False),
            target=dict(type="str", aliases=["targets"]),
            target_fs=dict(type="str"),
            eradicate=dict(default="false", type="bool"),
            state=dict(
                default="present", choices=["present", "absent", "restore", "copy"]
            ),
            latest_replica=dict(default="false", type="bool"),
            context=dict(type="str", default=""),
            detach_policies=dict(type="list", elements="str"),
            detach_all_policies=dict(type="bool", default=False),
        )
    )

    required_if = [["now", True, ["target"]], ["state", "copy", ["target_fs"]]]
    module = AnsibleModule(
        argument_spec, required_if=required_if, supports_check_mode=True
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    _check_names(module)
    # Remember whether the caller named a suffix before a default is
    # generated; state=restore uses the named snapshot only in that case.
    module.params["suffix_given"] = module.params["suffix"] is not None
    if module.params["suffix"] is None:
        suffix = "snap-" + str(
            (datetime.utcnow() - datetime(1970, 1, 1, 0, 0, 0, 0)).total_seconds()
        )
        module.params["suffix"] = suffix.replace(".", "")

    state = module.params["state"]
    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and not module.params["context"]
    ):
        # If no context is provided set the context to the local array name
        fleet_res = blade.get_fleets()
        if fleet_res.status_code == 200 and list(fleet_res.items):
            module.params["context"] = list(blade.get_arrays().items)[0].name

    if LooseVersion(SNAP_NOW_API) > LooseVersion(api_version) and module.params["now"]:
        module.fail_json(
            msg="Minimum FlashBlade REST version for immeadiate remote snapshots: {0}".format(
                SNAP_NOW_API
            )
        )
    if state == "copy" and LooseVersion(COPY_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg="Minimum FlashBlade REST version for filesystem copy from snapshot: {0}".format(
                COPY_API_VERSION
            )
        )
    # state=absent acts on the snapshot alone
    filesystem = None
    if state != "absent":
        filesystem = _get_filesystem(module, blade)
        if filesystem:
            # The array finds a filesystem whatever the letter case of its
            # name, but it reads the names of a restore and of a copy as
            # they are written, so the name it has for the filesystem is used
            module.params["name"] = filesystem.name
    snap = get_fssnapshot(module, blade)
    if (
        module.params["detach_policies"] is not None
        or module.params["detach_all_policies"]
    ):
        detach_snapshot_policies(module, blade, snap)
    if state in ("present", "restore") and not filesystem:
        # Also a filesystem the identity in use cannot see, such as one named
        # without its realm by a realm-scoped administrator
        module.fail_json(
            msg="Filesystem {0} does not exist, cannot {1}.".format(
                module.params["name"],
                "restore it" if state == "restore" else "create a snapshot of it",
            )
        )
    if state == "present" and filesystem and not filesystem.destroyed and not snap:
        create_snapshot(module, blade)
    elif (
        state == "present"
        and filesystem
        and not filesystem.destroyed
        and snap
        and not snap.destroyed
    ):
        update_snapshot(module, blade)
    elif (
        state == "present"
        and filesystem
        and not filesystem.destroyed
        and snap
        and snap.destroyed
    ):
        recover_snapshot(module, blade)
    elif state == "present" and filesystem and filesystem.destroyed:
        update_snapshot(module, blade)
    elif state == "restore" and filesystem:
        restore_snapshot(module, blade, snap)
    elif state == "copy":
        copy_snapshot(module, blade, filesystem, snap)
    elif state == "absent" and snap and not snap.destroyed:
        delete_snapshot(module, blade)
    elif state == "absent" and snap and snap.destroyed and module.params["eradicate"]:
        eradicate_snapshot(module, blade)
    elif state == "absent" and snap and snap.destroyed:
        # Already destroyed and eradicate not requested: nothing to do.
        module.exit_json(changed=False)
    elif state == "absent" and not snap:
        module.exit_json(changed=False)
    else:
        module.exit_json(changed=False)


if __name__ == "__main__":
    main()
