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
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - The name of the source filesystem.
    required: true
    type: str
  suffix:
    description:
    - Suffix of snapshot name.
    - With I(state=restore), names the snapshot to restore from. If not
      given the latest snapshot of the filesystem is used.
    type: str
  state:
    description:
    - Define whether the filesystem snapshot should exist or not.
    choices: [ absent, present, restore ]
    default: present
    type: str
  target:
    aliases: [ targets ]
    description:
    - Name of target to replicate snapshot to.
    - This is only applicable when I(now) is B(true)
    type: str
    version_added: "1.7.0"
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
    get_filesystem,
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
    api_version = get_rest_api_version(blade)
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and module.params["context"]
    ):
        res = blade.get_file_system_snapshots(
            names_or_owner_names=[
                module.params["name"] + "." + module.params["suffix"]
            ],
            context_names=[module.params["context"]],
        )
    else:
        res = blade.get_file_system_snapshots(
            names_or_owner_names=[
                module.params["name"] + "." + module.params["suffix"]
            ],
        )
    if res.status_code == 200:
        items = list(res.items)
        if items:
            return items[0]
    return None


def create_snapshot(module, blade):
    """Create Snapshot"""
    api_version = get_rest_api_version(blade)
    changed = False
    # Special case as we have changed 'target' to be a string not a list of one string
    # so this provides backwards compatability
    # target = module.params["target"].replace("[", "").replace("'", "").replace("]", "")
    blade_exists = False
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and module.params["context"]
    ):
        connected_blades = list(
            blade.get_array_connections(context_names=[module.params["context"]]).items
        )
    else:
        connected_blades = list(blade.get_array_connections().items)
    for rem_blade in connected_blades:
        if (
            module.params["target"]
            and module.params["target"] == rem_blade.remote.name
            and rem_blade.status == "connected"
        ):
            blade_exists = True
            break
    if module.params["target"] and not blade_exists:
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
            eradicate=dict(default="false", type="bool"),
            state=dict(default="present", choices=["present", "absent", "restore"]),
            latest_replica=dict(default="false", type="bool"),
            context=dict(type="str", default=""),
            detach_policies=dict(type="list", elements="str"),
            detach_all_policies=dict(type="bool", default=False),
        )
    )

    required_if = [["now", True, ["target"]]]
    module = AnsibleModule(
        argument_spec, required_if=required_if, supports_check_mode=True
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

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
    filesystem = get_filesystem(module, blade)
    snap = get_fssnapshot(module, blade)
    if (
        module.params["detach_policies"] is not None
        or module.params["detach_all_policies"]
    ):
        detach_snapshot_policies(module, blade, snap)
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
    elif state == "present" and not filesystem:
        update_snapshot(module, blade)
    elif state == "restore" and filesystem:
        restore_snapshot(module, blade, snap)
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
