#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2026, Simon Dodsley (simon@everpuredata.com)
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
module: purefb_export
version_added: "1.25.0"
short_description:  Manage filesystem exports on Everpure FlashBlade
description:
    - This module manages filesystem exports on Everpure FlashBlade.
    - An export is in the realm of its file system and of its server, which
      must be the same realm. For a file system in a realm give both as
      C(realm::name). The export name itself is never realm-qualified.
    - A realm-scoped administrator must use the realm-qualified name; a bare
      name is not placed in, or resolved to, the administrator's realm.
author: Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
      - Export Name.
      - The export name is never realm-qualified. The realm of an export
        is that of I(filesystem) and I(server).
    required: true
    type: str
  server:
    description:
      - Name of server to assign export to
      - Required for a file system in a realm, a server of the same realm,
        C(realm::server). The default server is not in a realm.
      - The module fails, in check mode as well, when I(filesystem) and
        I(server) are not in the same realm or not both outside of any realm.
    type: str
    default: "_array_server"
  filesystem:
    description:
      - Filesystem to create the export for.
      - For a file system in a realm use C(realm::name).
    required: true
    type: str
  state:
    description:
      - Create, delete or modifies a filesystem export.
    required: false
    default: present
    type: str
    choices: [ "present", "absent" ]
  type:
    description:
      - Type of filesystem export
    type: str
    choices: [ "NFS", "SMB" ]
    default: NFS
  export_policy:
    description:
    - Name of NFS export policy to assign to the export
    - Required to create an NFS export.
    - For an export in a realm use a policy of the same realm,
      C(realm::policy).
    type: str
  share_policy:
    description:
    - Name of SMB share policy to assign to the export
    - A new SMB export gets C(_smb_share_allow_everyone) when this is not set.
    - For an export in a realm use a policy of the same realm,
      C(realm::policy), or a built-in policy.
    type: str
  client_policy:
    description:
    - Name of SMB client policy to assign to the export
    - A new SMB export gets C(_smb_client_allow_everyone) when this is not set.
    - For an export in a realm use a policy of the same realm,
      C(realm::policy), or a built-in policy.
    type: str
  rename:
    description:
      - New name for export
      - Never realm-qualified.
    type: str
  context:
    description:
    - Name of fleet member on which to perform the operation.
    - This requires the array receiving the request is a member of a fleet
      and the context name to be a member of the same fleet.
    type: str
    default: ""
extends_documentation_fragment:
    - everpure.flashblade.everpure.fb
"""

EXAMPLES = """
- name: Create new filesystem NFS export foo for filesystem bar
  everpure.flashblade.purefb_export:
    name: foo
    filesystem: bar
    export_policy: acme_1
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create new filesystem NFS export foo for filesystem bar on server test
  everpure.flashblade.purefb_export:
    name: foo
    server: test
    filesystem: bar
    export_policy: acme_1
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create new filesystem SMB export foo for filesystem bar
  everpure.flashblade.purefb_export:
    name: foo
    filesystem: bar
    type: SMB
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create NFS export foo for file system bar of realm tenant1
  everpure.flashblade.purefb_export:
    name: foo
    server: tenant1::test
    filesystem: tenant1::bar
    export_policy: tenant1::acme_1
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete filesystem export foo on server test
  everpure.flashblade.purefb_export:
    name: foo
    server: test
    filesystem: bar
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Attach NFS export policy to filesystem bar (replaces purefb_fs export_policy)
  everpure.flashblade.purefb_export:
    name: bar_nfs
    filesystem: bar
    type: NFS
    export_policy: nfs_pol1
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Attach SMB share policy to filesystem bar (replaces purefb_fs share_policy)
  everpure.flashblade.purefb_export:
    name: bar_smb
    filesystem: bar
    type: SMB
    share_policy: smb_share_pol1
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Attach SMB client policy to filesystem bar (replaces purefb_fs client_policy)
  everpure.flashblade.purefb_export:
    name: bar_smb
    filesystem: bar
    type: SMB
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
        FileSystemExport,
        FileSystemExportPost,
        Reference,
    )
except ImportError:
    HAS_PYPURECLIENT = False

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

MIN_API_VERSION = "2.17"
ARRAY_SERVER = "_array_server"
# option: (what the array calls the policy, the SDK method that reads it)
POLICY_READS = {
    "export_policy": ("NFS export", "get_nfs_export_policies"),
    "client_policy": ("SMB client", "get_smb_client_policies"),
    "share_policy": ("SMB share", "get_smb_share_policies"),
}


def _context_kwargs(module):
    """Return context_names kwargs only when a context is set.

    A standalone array is "not in a fleet" and rejects fleet context, so
    only send context_names when a context has actually been provided.
    """
    if module.params["context"]:
        return {"context_names": [module.params["context"]]}
    return {}


def _realm_of(name):
    """Return the realm of a realm::name name, empty for an array-level name."""
    return (name or "").rpartition("::")[0]


def _same_name(first, second):
    """Compare two names as the array matches them, without regard to case."""
    return (first or "").lower() == (second or "").lower()


def _does_not_exist(error):
    """Tell the array's answer for a missing object from any other failure."""
    return "does not exist" in str(error).lower()


def _check_names(module):
    """Fail on names that cannot address an export, before any request.

    An export is in the realm of its file system and of its server, and the
    array creates one only where both are in the same realm or both outside
    of any realm. A task that mixes the scopes, for instance a file system in
    a realm with the default server, names an export that cannot exist. It is
    refused for every state, in check mode as well, instead of reporting a
    change the array refuses, or no change while the export that was meant
    stays as it is. The export name itself carries no realm.
    """
    for option in ("name", "rename"):
        value = module.params[option]
        if value and "::" in value:
            module.fail_json(
                msg=(
                    "{0} {1} is not valid: an export name is never "
                    "realm-qualified. An export is in the realm of its file "
                    "system and server."
                ).format(option, value)
            )
    filesystem = module.params["filesystem"]
    server = module.params["server"]
    fs_realm = _realm_of(filesystem)
    server_realm = _realm_of(server)
    if _same_name(fs_realm, server_realm):
        return
    scopes = [
        "in realm {0}".format(realm) if realm else "not in a realm"
        for realm in (fs_realm, server_realm)
    ]
    msg = (
        "File system {0} is {1} and server {2} is {3}. The file system and "
        "the server of an export must be in the same realm, or both outside "
        "of any realm."
    ).format(filesystem, scopes[0], server, scopes[1])
    if fs_realm and server == ARRAY_SERVER:
        msg += (
            " Set server to a server of realm {0}, named {0}::<server>: the "
            "default server is not in a realm."
        ).format(fs_realm)
    module.fail_json(msg=msg)


def _check_server(module, blade):
    """Fail unless the server of the export can be read."""
    server = module.params["server"]
    res = blade.get_servers(names=[server])
    if res.status_code == 200:
        return
    error = get_error_message(res)
    if _does_not_exist(error):
        module.fail_json(msg="Server {0} does not exist.".format(server))
    module.fail_json(msg="Failed to read server {0}. Error: {1}".format(server, error))


def _require_file_system(module, blade):
    """Fail unless the file system to export exists.

    The array answers a name it does not find with an error or with an empty
    list, depending on who asks.
    """
    filesystem = module.params["filesystem"]
    res = blade.get_file_systems(names=[filesystem], **_context_kwargs(module))
    if res.status_code == 200:
        if list(res.items):
            return
    else:
        error = get_error_message(res)
        if not _does_not_exist(error):
            module.fail_json(
                msg="Failed to read file system {0}. Error: {1}".format(
                    filesystem, error
                )
            )
    module.fail_json(msg="File system {0} does not exist.".format(filesystem))


def _realm_policy_hint(module, policy):
    """Name the realm form of a policy that an export in a realm cannot find."""
    realm = _realm_of(module.params["filesystem"])
    if not realm or _same_name(_realm_of(policy), realm):
        return ""
    return (
        " The export is in realm {0}, where a policy of that realm is named "
        "{0}::{1}."
    ).format(realm, policy.rpartition("::")[2])


def _require_policy(module, blade, option):
    """Fail unless the policy an option names exists.

    Looked up before a change is reported, so that check mode does not
    predict a change the array refuses. Whether an existing policy may serve
    the export is left to the array: the built-in policies serve every realm.
    """
    policy = module.params[option]
    kind, method = POLICY_READS[option]
    res = getattr(blade, method)(names=[policy], **_context_kwargs(module))
    if res.status_code == 200:
        if list(res.items):
            return
    else:
        error = get_error_message(res)
        if not _does_not_exist(error):
            module.fail_json(
                msg="Failed to read {0} policy {1}. Error: {2}".format(
                    kind, policy, error
                )
            )
    module.fail_json(
        msg="{0} policy {1} does not exist.{2}".format(
            kind, policy, _realm_policy_hint(module, policy)
        )
    )


def _refusal_hint(module, error):
    """Say which policies an export can use when the array refuses one.

    The array refuses a policy from another scope than the export. Its
    message does not say how a policy of the right scope is named.
    """
    text = str(error).lower()
    if "polic" not in text or "same realm" not in text:
        return ""
    lead = " " if text.rstrip().endswith(".") else ". "
    realm = _realm_of(module.params["filesystem"])
    if not realm:
        return lead + (
            "The export is not in a realm: use a policy that is not in a "
            "realm either."
        )
    built_in = ", or a built-in policy" if module.params["type"] == "SMB" else ""
    return lead + (
        "The export is in realm {0}: use a policy of that realm, named "
        "{0}::<policy>{1}."
    ).format(realm, built_in)


def _check_create(module, blade):
    """Fail where the array would refuse to create the export.

    Decided before the check-mode branch, so check mode fails where a real
    run does: an NFS export is created with an NFS export policy, and the
    file system and every policy the task names have to exist.
    """
    nfs = module.params["type"] == "NFS"
    if nfs and not module.params["export_policy"]:
        module.fail_json(
            msg=(
                "export_policy is required to create NFS export {0} for file "
                "system {1}."
            ).format(module.params["name"], module.params["filesystem"])
        )
    _require_file_system(module, blade)
    for option in ("export_policy",) if nfs else ("client_policy", "share_policy"):
        if module.params[option]:
            _require_policy(module, blade, option)


def _warn_fs_policy_collision(module, blade):
    """Warn when the filesystem still carries a legacy filesystem-level
    policy on the protocol being touched.

    SMB warns even when the caller omits the matching field, because
    create_export always writes both client_policy and share_policy on a
    new SMB export (defaulting to the built-in allow-everyone policies)
    and would otherwise silently shadow the legacy value.
    """
    if module.params["type"] == "NFS" and not module.params["export_policy"]:
        return
    res = blade.get_file_systems(
        names=[module.params["filesystem"]], **_context_kwargs(module)
    )
    if res.status_code != 200:
        return
    items = list(res.items)
    if not items:
        return
    fsys = items[0]

    nfs = getattr(fsys, "nfs", None)
    smb = getattr(fsys, "smb", None)
    fs_export_policy = getattr(getattr(nfs, "export_policy", None), "name", None)
    fs_share_policy = getattr(getattr(smb, "share_policy", None), "name", None)
    fs_client_policy = getattr(getattr(smb, "client_policy", None), "name", None)
    if module.params["type"] == "NFS":
        if fs_export_policy:
            module.warn(
                "Filesystem {0} still has filesystem-level "
                "nfs.export_policy={1} set. The purefb_export "
                "attachment {2} is the surface Purity treats as "
                "authoritative; migrate off purefb_fs: export_policy "
                "to avoid confusion.".format(
                    module.params["filesystem"],
                    fs_export_policy,
                    module.params["export_policy"],
                )
            )
    else:
        if fs_share_policy:
            module.warn(
                "Filesystem {0} still has filesystem-level "
                "smb.share_policy={1} set. The export-level "
                "share_policy is the surface Purity treats as "
                "authoritative and will shadow it; migrate off "
                "purefb_fs: share_policy to avoid confusion.".format(
                    module.params["filesystem"],
                    fs_share_policy,
                )
            )
        if fs_client_policy:
            module.warn(
                "Filesystem {0} still has filesystem-level "
                "smb.client_policy={1} set. The export-level "
                "client_policy is the surface Purity treats as "
                "authoritative and will shadow it; migrate off "
                "purefb_fs: client_policy to avoid confusion.".format(
                    module.params["filesystem"],
                    fs_client_policy,
                )
            )


def get_export(module, blade):
    """Return Filesystem export true name or None"""
    filter_string = (
        "export_name='"
        + module.params["name"]
        + "' and policy_type='"
        + module.params["type"]
        + "' and member.name='"
        + module.params["filesystem"]
        + "' and server.name='"
        + module.params["server"]
        + "'"
    )
    res = blade.get_file_system_exports(filter=filter_string, **_context_kwargs(module))
    if res.status_code != 200:
        # an export that cannot be read is not an export that is absent
        module.fail_json(
            msg="Failed to read export {0} of file system {1}. Error: {2}".format(
                module.params["name"],
                module.params["filesystem"],
                get_error_message(res),
            )
        )
    items = list(res.items)
    return items[0] if items else None


def _warn_type_transition(module, blade):
    """Warn when a same-address export of the OTHER protocol exists.

    One export per protocol per filesystem is permitted, so
    both can legitimately coexist, but this almost always indicates a
    mistyped ``type:`` parameter.
    """
    other_type = "SMB" if module.params["type"] == "NFS" else "NFS"
    filter_string = (
        "export_name='"
        + module.params["name"]
        + "' and policy_type='"
        + other_type
        + "' and member.name='"
        + module.params["filesystem"]
        + "' and server.name='"
        + module.params["server"]
        + "'"
    )
    res = blade.get_file_system_exports(filter=filter_string, **_context_kwargs(module))
    if res.status_code == 200 and res.total_item_count != 0:
        module.warn(
            "A {0} export named {1} already exists on filesystem {2} "
            "server {3}. Creating a {4} export in addition rather than "
            "modifying the existing one. One FileSystemExport per protocol "
            "per filesystem is permitted. If this was "
            "not intentional, check the `type:` parameter.".format(
                other_type,
                module.params["name"],
                module.params["filesystem"],
                module.params["server"],
                module.params["type"],
            )
        )


def create_export(module, blade):
    """Create Filesystem Export"""
    changed = True
    _warn_fs_policy_collision(module, blade)
    if not module.check_mode:
        if module.params["type"] == "NFS":
            exp_obj = FileSystemExportPost(
                export_name=module.params["name"],
                server=Reference(name=module.params["server"]),
            )
            res = blade.post_file_system_exports(
                file_system_export=exp_obj,
                member_names=[module.params["filesystem"]],
                policy_names=[module.params["export_policy"]],
                **_context_kwargs(module),
            )
        else:
            if not module.params["client_policy"]:
                module.params["client_policy"] = "_smb_client_allow_everyone"
            if not module.params["share_policy"]:
                module.params["share_policy"] = "_smb_share_allow_everyone"
            exp_obj = FileSystemExportPost(
                export_name=module.params["name"],
                server=Reference(name=module.params["server"]),
                share_policy=Reference(name=module.params["share_policy"]),
            )
            res = blade.post_file_system_exports(
                file_system_export=exp_obj,
                member_names=[module.params["filesystem"]],
                policy_names=[module.params["client_policy"]],
                **_context_kwargs(module),
            )
        # Only evaluated when a request was made; in check mode there is
        # no response to inspect.
        if res.status_code != 200:
            error = get_error_message(res)
            module.fail_json(
                msg="Failed to create export {0} for {1}. Error: {2}{3}".format(
                    module.params["name"],
                    module.params["filesystem"],
                    error,
                    _refusal_hint(module, error),
                )
            )
    module.exit_json(changed=changed)


def modify_export(module, blade, export):
    """Modify Filesystem"""
    _warn_fs_policy_collision(module, blade)
    changed_export = False
    changed_policy = False
    if module.params["rename"] and module.params["rename"] != module.params["name"]:
        export_name = module.params["rename"]
        changed_export = True
    else:
        export_name = module.params["name"]
    if module.params["type"] == "NFS":
        if module.params["export_policy"] and not _same_name(
            module.params["export_policy"], export.policy.name
        ):
            _require_policy(module, blade, "export_policy")
            export_policy = module.params["export_policy"]
            changed_policy = True
        else:
            export_policy = export.policy.name
        if changed_policy or changed_export:
            if not module.check_mode:
                exp_obj = FileSystemExport()
                if changed_policy and not changed_export:
                    exp_obj = FileSystemExport(policy=Reference(name=export_policy))
                elif changed_policy and changed_export:
                    exp_obj = FileSystemExport(
                        export_name=export_name, policy=Reference(name=export_policy)
                    )
                elif not changed_policy and changed_export:
                    exp_obj = FileSystemExport(
                        export_name=export_name,
                    )
                res = blade.patch_file_system_exports(
                    names=[export.name], file_system_export=exp_obj
                )
                if res.status_code != 200:
                    error = get_error_message(res)
                    module.fail_json(
                        msg="Failed to update export {0}. Error: {1}{2}".format(
                            export.name, error, _refusal_hint(module, error)
                        )
                    )
    else:
        if module.params["client_policy"] and not _same_name(
            module.params["client_policy"], export.policy.name
        ):
            _require_policy(module, blade, "client_policy")
            client_policy = module.params["client_policy"]
            changed_policy = True
        else:
            client_policy = export.policy.name
        if module.params["share_policy"] and not _same_name(
            module.params["share_policy"], export.share_policy.name
        ):
            _require_policy(module, blade, "share_policy")
            share_policy = module.params["share_policy"]
            changed_policy = True
        else:
            share_policy = export.share_policy.name
        if changed_policy or changed_export:
            if not module.check_mode:
                exp_obj = FileSystemExport()
                if changed_policy and not changed_export:
                    exp_obj = FileSystemExport(
                        share_policy=Reference(name=share_policy),
                        policy=Reference(name=client_policy),
                    )
                elif changed_policy and changed_export:
                    exp_obj = FileSystemExport(
                        export_name=export_name,
                        share_policy=Reference(name=share_policy),
                        policy=Reference(name=client_policy),
                    )
                elif not changed_policy and changed_export:
                    exp_obj = FileSystemExport(
                        export_name=export_name,
                    )
                res = blade.patch_file_system_exports(
                    names=[export.name], file_system_export=exp_obj
                )
                if res.status_code != 200:
                    error = get_error_message(res)
                    module.fail_json(
                        msg="Failed to update export {0}. Error: {1}{2}".format(
                            export.name, error, _refusal_hint(module, error)
                        )
                    )

    module.exit_json(changed=(changed_policy or changed_export))


def delete_export(module, blade, export):
    """Delete Filesystem Export"""
    changed = True
    if not module.check_mode:
        res = blade.delete_file_system_exports(names=[export])
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete export {0}. Error: {1}".format(
                    export, get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str", required=True),
            server=dict(type="str", default=ARRAY_SERVER),
            filesystem=dict(type="str", required=True),
            rename=dict(type="str"),
            type=dict(type="str", choices=["NFS", "SMB"], default="NFS"),
            state=dict(default="present", choices=["present", "absent"]),
            export_policy=dict(type="str"),
            share_policy=dict(type="str"),
            client_policy=dict(type="str"),
            context=dict(type="str", default=""),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    state = module.params["state"]
    _check_names(module)
    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if (
        LooseVersion(MIN_API_VERSION) <= LooseVersion(api_version)
        and not module.params["context"]
    ):
        # If no context is provided set the context to the local array name
        fleet_res = blade.get_fleets()
        if fleet_res.status_code == 200 and list(fleet_res.items):
            module.params["context"] = list(blade.get_arrays().items)[0].name
    _check_server(module, blade)
    export = get_export(module, blade)

    if state == "present" and not export and not module.params["rename"]:
        _check_create(module, blade)
        _warn_type_transition(module, blade)
        create_export(module, blade)
    elif state == "present" and export:
        modify_export(module, blade, export)
    elif state == "absent" and export:
        delete_export(module, blade, export.name)
    elif state == "absent" and not export:
        module.exit_json(changed=False)
    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
