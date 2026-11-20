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

DOCUMENTATION = r"""
---
module: purefb_local_group
version_added: '1.28.0'
short_description: Manage FlashBlade Local Directory Service groups
description:
- Create, update, rename or delete a local group in a FlashBlade Local
  Directory Service (LDS). These are the SMB/NFS local identities that live
  inside an LDS attached to a FlashBlade server.
- Requires FlashBlade REST API version 2.24 or later (Purity//FB 4.6.8+).
- User memberships can be managed inline via the I(local_users) option. If
  you also drive membership from the user side (via
  M(everpure.flashblade.purefb_local_user)), only manage a given (user,group)
  edge from one side in a single playbook run.
- A group belongs to its LDS and, with it, to the realm of that LDS. A group
  of an LDS in a realm is addressed with the realm-qualified name of the LDS
  in I(local_directory_service) and its own name without a realm. A
  realm-scoped administrator must use the realm-qualified name; a bare name
  is not placed in, or resolved to, the administrator's realm.
author:
- Pure Storage Ansible Team (@avk) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - Name of the local group inside the LDS.
    - The name never takes a realm prefix, also when the LDS is in a realm.
      A name that contains C(::) is refused.
    - A name that contains a comma is refused as well. The array reads a
      comma as the separator of a list of names.
    - Both rules apply to I(new_name) too.
    type: str
    required: true
  state:
    description:
    - Whether the local group should exist or not.
    type: str
    default: present
    choices: [ absent, present ]
  local_directory_service:
    description:
    - Name of the Local Directory Service that owns this group.
    - For an LDS in a realm use the realm-qualified name C(realm::name).
    - The LDS has to exist. The module fails when the array does not find
      it, in check mode as well. With I(state=absent) a group of an LDS that
      does not exist is reported as absent.
    - The option names one LDS. A name that contains a comma is refused.
    - Attach LDSes to servers via M(everpure.flashblade.purefb_server).
    type: str
    required: true
  new_name:
    description:
    - New name for the group. Uses the C(LocalGroupPatch.name) field.
    - Applies to an existing group. A group that does not exist yet is
      created as I(name).
    - Idempotent when no group is called I(name) and a group called
      I(new_name) exists in the same LDS. The task then carries on with that
      group. The module fails without changing anything when I(name) and
      I(new_name) are two different groups.
    - The array matches names without regard to case and does not rename a
      group to its own name in another spelling, so that is refused.
    - Rejected for built-in groups.
    type: str
  gid:
    description:
    - Numeric GID for the group. Auto-assigned by the array if omitted at
      create time. Patchable.
    type: int
  email:
    description:
    - Email address for the group.
    type: str
  local_users:
    description:
    - List of local-user names that should be members of this group.
    - These are names of users of the same LDS, without a realm prefix.
      They are compared without regard to case, as the array matches them.
    - When set, the module reconciles the group's user members against this
      list via C(/directory-services/local/groups/members) filtered to user
      members (nested-group and external members are unaffected).
    - The option is named I(local_users) rather than I(members) to reserve
      option space for future I(external_members) and I(group_members)
      without a breaking rename.
    type: list
    elements: str
  force:
    description:
    - Only used when I(state=absent).
    - When the group has members and I(force=false), the module fails with
      a clear message rather than surfacing the raw API error.
    - When I(force=true), the module removes all current memberships before
      deleting the group. Refused on built-in groups regardless.
    type: bool
    default: false
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

EXAMPLES = r"""
- name: Create local group 'developers'
  everpure.flashblade.purefb_local_group:
    name: developers
    local_directory_service: myserver_local
    gid: 6001
    email: developers@example.com
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Ensure 'developers' has these local user members
  everpure.flashblade.purefb_local_group:
    name: developers
    local_directory_service: myserver_local
    local_users:
      - alice
      - bob
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Rename local group
  everpure.flashblade.purefb_local_group:
    name: developers
    new_name: devs
    local_directory_service: myserver_local
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create local group 'developers' in the LDS of a realm
  everpure.flashblade.purefb_local_group:
    name: developers
    local_directory_service: realm1::tenant_local
    local_users:
      - alice
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete an empty local group
  everpure.flashblade.purefb_local_group:
    name: devs
    local_directory_service: myserver_local
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Force-delete a group that still has members
  everpure.flashblade.purefb_local_group:
    name: devs
    local_directory_service: myserver_local
    state: absent
    force: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = r"""
"""


HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        LocalGroupPost,
        LocalGroupPatch,
        LocalGroupMembershipPost,
        LocalGroupMembershipPostMembers,
        ReferenceWritable,
    )
except ImportError:
    HAS_PYPURECLIENT = False


from ansible.module_utils.basic import AnsibleModule
from ansible_collections.everpure.flashblade.plugins.module_utils.purefb import (
    get_system,
    purefb_argument_spec,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.common import (
    get_error_message,
    get_rest_api_version,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.version import (
    LooseVersion,
)

MIN_REQUIRED_API_VERSION = "2.24"


def _context_kwargs(module):
    """Return context_names kwargs when a context is set.

    Local groups require REST 2.24, which is well above the 2.17 fleet-context
    floor, so context_names is always accepted here.
    """
    if module.params["context"]:
        return {"context_names": [module.params["context"]]}
    return {}


def _lds_filter(local_ds_name, extra=None):
    """Build a filter expression that scopes to the given LDS.

    The FB 2.24 GET endpoints for local groups / members do not accept
    ``local_directory_service_names``; scoping must go through ``filter``.
    """
    expr = "local_directory_service.name='{0}'".format(
        local_ds_name.replace("'", "\\'")
    )
    if extra:
        expr = "({0}) and ({1})".format(expr, extra)
    return expr


def _check_names(module):
    """Fail on a name that is not the name of one object, before any request.

    A group is placed by its LDS. Its own name carries no realm, and the array
    refuses a colon in it. The array reads a comma as the separator of a list
    of names, so a name with a comma addresses several groups, or several
    LDSes, in one request. The refusals here say what works, for every state
    and in check mode as well.
    """
    options = ["name"]
    if module.params["state"] == "present":
        options.append("new_name")
    for option in options:
        value = module.params[option]
        if value and "::" in value:
            module.fail_json(
                msg=(
                    "{0} {1} is not valid: the name of a local group takes no "
                    "realm prefix. Give the local directory service of the "
                    "realm as realm::name in local_directory_service and the "
                    "group name on its own."
                ).format(option, value)
            )
    for option in ["local_directory_service"] + options:
        value = module.params[option]
        if value and "," in value:
            module.fail_json(
                msg=(
                    "{0} {1} is not valid: the array reads a comma as the "
                    "separator of a list of names, so this would address "
                    "more than one object. Give one name."
                ).format(option, value)
            )


def _missing(res):
    """Tell the array's answer for a name it does not have from other failures.

    A local directory service that is not there answers "... does not
    exist.", a local group "... was not found.". Any other answer is a read
    that failed, and is reported as that.
    """
    text = str(get_error_message(res)).lower()
    return "does not exist" in text or "was not found" in text


def _get_lds(module, blade, local_ds_name):
    """Return the local directory service, or None when there is none.

    The array answers "does not exist" for a name it does not find and for an
    LDS the caller may not manage, such as one outside the realm of a
    realm-scoped administrator. It lists the groups of the latter all the
    same, so the LDS is read before any group is looked up in it.
    """
    res = blade.get_directory_services_local_directory_services(
        names=[local_ds_name], **_context_kwargs(module)
    )
    if res.status_code == 200:
        items = list(res.items)
        return items[0] if items else None
    if _missing(res):
        return None
    module.fail_json(
        msg="Failed to read local directory service {0}. Error: {1}".format(
            local_ds_name, get_error_message(res)
        )
    )


def _get_group(module, blade, local_ds_name, name=None):
    """Return the group called name in the LDS, or None when there is none.

    Only the array's answer that the group was not found reads as None. Any
    other failure of the read fails the task instead of passing for "absent".
    """
    name = name or module.params["name"]
    ctx = _context_kwargs(module)
    res = blade.get_directory_services_local_groups(
        names=[name],
        filter=_lds_filter(local_ds_name),
        **ctx,
    )
    if res.status_code == 200:
        items = list(res.items)
        return items[0] if items else None
    if _missing(res):
        return None
    module.fail_json(
        msg=(
            "Failed to read local group {0} of local directory service {1}. "
            "Error: {2}"
        ).format(name, local_ds_name, get_error_message(res))
    )


def _same_group(first, second):
    """Tell whether two reads of one LDS returned the same group."""
    first_sid = getattr(first, "sid", None)
    second_sid = getattr(second, "sid", None)
    if first_sid and second_sid:
        return first_sid == second_sid
    return str(first.name).lower() == str(second.name).lower()


def _resolve_rename(module, blade, local_ds_name, group):
    """Return the group the task works on and the name it is renamed to.

    The second value is None when there is nothing to rename. When no group
    is called name and one called new_name exists in the LDS, an earlier run
    of the task has renamed it: the task carries on with that group instead
    of creating the old name again. Refusals are decided here, before any
    other option is applied and in check mode as well.
    """
    name = module.params["name"]
    new_name = module.params["new_name"]
    if not new_name or new_name == name:
        return group, None
    if group is not None and getattr(group, "built_in", False):
        module.fail_json(msg="Refusing to rename built-in local group {0}".format(name))
    target = _get_group(module, blade, local_ds_name, new_name)
    if group is None:
        if target is None:
            # nothing to rename: the group is created as name
            return None, None
        if getattr(target, "built_in", False):
            module.fail_json(
                msg=(
                    "Cannot rename local group {0} to {1}: {0} does not exist "
                    "and {1} is a built-in group"
                ).format(name, new_name)
            )
        module.params["name"] = target.name
        return target, None
    if target is None:
        return group, new_name
    if not _same_group(group, target):
        module.fail_json(
            msg=(
                "Cannot rename local group {0} to {1}: target name already exists"
            ).format(name, new_name)
        )
    if target.name == new_name:
        # the array matches names without regard to case: both names are this
        # one group, which already carries the new one
        return group, None
    module.fail_json(
        msg=(
            "Cannot rename local group {0} to {1}: the new name differs from "
            "the name of the group only in case. The array matches names "
            "without regard to case and does not rename a group to its own "
            "name."
        ).format(name, new_name)
    )


def _get_current_user_members(module, blade, local_ds_name, group_name=None):
    """Return the set of user-member names currently attached to this group."""
    ctx = _context_kwargs(module)
    res = blade.get_directory_services_local_groups_members(
        group_names=[group_name or module.params["name"]],
        filter=_lds_filter(local_ds_name),
        member_types=["User"],
        **ctx,
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to fetch memberships for group {0}. Error: {1}".format(
                module.params["name"], get_error_message(res)
            )
        )
    result = set()
    for edge in list(res.items):
        member = getattr(edge, "member", None)
        if member is not None:
            mname = getattr(member, "name", None)
            if mname:
                result.add(mname)
    return result


def _get_all_current_members(module, blade, local_ds_name):
    """Return the full list of member edges for this group (any type)."""
    ctx = _context_kwargs(module)
    res = blade.get_directory_services_local_groups_members(
        group_names=[module.params["name"]],
        filter=_lds_filter(local_ds_name),
        **ctx,
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to fetch memberships for group {0}. Error: {1}".format(
                module.params["name"], get_error_message(res)
            )
        )
    return list(res.items)


def _add_user_members(module, blade, local_ds_name, users, group_name):
    ctx = _context_kwargs(module)
    body = LocalGroupMembershipPost(
        members=[
            LocalGroupMembershipPostMembers(member=ReferenceWritable(name=u))
            for u in users
        ]
    )
    res = blade.post_directory_services_local_groups_members(
        local_membership=body,
        group_names=[group_name],
        local_directory_service_names=[local_ds_name],
        **ctx,
    )
    if res.status_code != 200:
        module.fail_json(
            msg=("Failed to add user members {0} to group {1}. Error: {2}").format(
                sorted(users), group_name, get_error_message(res)
            )
        )


def _remove_user_members(module, blade, local_ds_name, users, group_name):
    ctx = _context_kwargs(module)
    for u in users:
        res = blade.delete_directory_services_local_groups_members(
            group_names=[group_name],
            member_names=[u],
            member_types=["User"],
            local_directory_service_names=[local_ds_name],
            **ctx,
        )
        if res.status_code != 200:
            module.fail_json(
                msg=("Failed to remove user {0} from group {1}. Error: {2}").format(
                    u, group_name, get_error_message(res)
                )
            )


def _reconcile_user_members(module, blade, local_ds_name, group_name):
    """Reconcile user members against module.params['local_users'].

    The array matches user names without regard to case and returns the
    stored spelling, so the two lists are compared in lower case: a member
    named in another case is left as it is, and a name given twice counts
    once.
    """
    desired = {}
    for user in module.params["local_users"] or []:
        desired.setdefault(user.lower(), user)
    current = {}
    for user in _get_current_user_members(
        module, blade, local_ds_name, group_name=group_name
    ):
        current[user.lower()] = user
    add = [desired[key] for key in sorted(desired) if key not in current]
    remove = [current[key] for key in sorted(current) if key not in desired]
    changed = bool(add or remove)
    if changed and not module.check_mode:
        if add:
            _add_user_members(module, blade, local_ds_name, add, group_name)
        if remove:
            _remove_user_members(module, blade, local_ds_name, remove, group_name)
    return changed


def delete_group(module, blade, local_ds_name, group):
    if getattr(group, "built_in", False):
        module.fail_json(
            msg="Refusing to delete built-in local group {0}".format(
                module.params["name"]
            )
        )

    current_edges = _get_all_current_members(module, blade, local_ds_name)
    if current_edges:
        if not module.params["force"]:
            module.fail_json(
                msg=(
                    "Local group {0} has {1} member(s); "
                    "remove them or set force: true to auto-clear before delete."
                ).format(module.params["name"], len(current_edges))
            )
        if not module.check_mode:
            ctx = _context_kwargs(module)
            for edge in current_edges:
                member = getattr(edge, "member", None)
                mname = getattr(member, "name", None) if member else None
                if not mname:
                    continue
                mtype = getattr(member, "resource_type", None)
                delete_kwargs = {
                    "group_names": [module.params["name"]],
                    "member_names": [mname],
                    "local_directory_service_names": [local_ds_name],
                }
                if mtype:
                    # resource_type is a hint like 'local-users' or 'local-groups';
                    # translate to the member_types filter when we can.
                    if "user" in mtype:
                        delete_kwargs["member_types"] = ["User"]
                    elif "group" in mtype:
                        delete_kwargs["member_types"] = ["Group"]
                delete_kwargs.update(ctx)
                res = blade.delete_directory_services_local_groups_members(
                    **delete_kwargs
                )
                if res.status_code != 200:
                    module.fail_json(
                        msg=(
                            "Failed to clear member {0} from group {1}. Error: {2}"
                        ).format(mname, module.params["name"], get_error_message(res))
                    )

    changed = True
    if not module.check_mode:
        ctx = _context_kwargs(module)
        res = blade.delete_directory_services_local_groups(
            names=[module.params["name"]],
            local_directory_service_names=[local_ds_name],
            **ctx,
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete local group {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def create_group(module, blade, local_ds_name):
    changed = True
    if not module.check_mode:
        body_kwargs = {}
        if module.params["email"] is not None:
            body_kwargs["email"] = module.params["email"]
        if module.params["gid"] is not None:
            body_kwargs["gid"] = module.params["gid"]

        ctx = _context_kwargs(module)
        res = blade.post_directory_services_local_groups(
            names=[module.params["name"]],
            local_directory_service_names=[local_ds_name],
            local_group=LocalGroupPost(**body_kwargs),
            **ctx,
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to create local group {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )

        if module.params["local_users"]:
            _reconcile_user_members(module, blade, local_ds_name, module.params["name"])
    module.exit_json(changed=changed)


def update_group(module, blade, local_ds_name, group, rename_to=None):
    ctx = _context_kwargs(module)
    built_in = bool(getattr(group, "built_in", False))
    patch_kwargs = {}
    identity_changes = []

    if rename_to:
        patch_kwargs["name"] = rename_to
        identity_changes.append("name")

    if module.params["email"] is not None and module.params["email"] != getattr(
        group, "email", None
    ):
        patch_kwargs["email"] = module.params["email"]
        identity_changes.append("email")

    if module.params["gid"] is not None and module.params["gid"] != getattr(
        group, "gid", None
    ):
        patch_kwargs["gid"] = module.params["gid"]
        identity_changes.append("gid")

    if identity_changes and built_in:
        module.fail_json(
            msg="Refusing to modify built-in local group {0}".format(
                module.params["name"]
            )
        )

    patch_changed = bool(patch_kwargs)
    if patch_changed and not module.check_mode:
        res = blade.patch_directory_services_local_groups(
            names=[module.params["name"]],
            local_directory_service_names=[local_ds_name],
            local_group=LocalGroupPatch(**patch_kwargs),
            **ctx,
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to update local group {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )

    membership_changed = False
    if module.params["local_users"] is not None:
        # After a successful rename the group is now known by new_name; in
        # check mode the rename was skipped, so it keeps its current name.
        if module.check_mode:
            effective_name = module.params["name"]
        else:
            effective_name = patch_kwargs.get("name") or module.params["name"]
        membership_changed = _reconcile_user_members(
            module, blade, local_ds_name, effective_name
        )

    module.exit_json(changed=patch_changed or membership_changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str", required=True),
            state=dict(type="str", default="present", choices=["absent", "present"]),
            local_directory_service=dict(type="str", required=True),
            new_name=dict(type="str"),
            gid=dict(type="int"),
            email=dict(type="str"),
            local_users=dict(type="list", elements="str"),
            force=dict(type="bool", default=False),
            context=dict(type="str", default=""),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg=(
                "FlashBlade REST version not supported. "
                "Minimum version required: {0} (Purity//FB 4.6.8+)"
            ).format(MIN_REQUIRED_API_VERSION)
        )

    if not module.params["context"]:
        # If no context is provided set the context to the local array name
        fleet_res = blade.get_fleets()
        if fleet_res.status_code == 200 and list(fleet_res.items):
            module.params["context"] = list(blade.get_arrays().items)[0].name

    local_ds_name = module.params["local_directory_service"]
    state = module.params["state"]
    _check_names(module)

    if _get_lds(module, blade, local_ds_name) is None:
        if state == "absent":
            module.exit_json(
                changed=False,
                msg=(
                    "Local directory service {0} does not exist, so it has "
                    "no local group {1}. A local directory service in a "
                    "realm is named realm::name."
                ).format(local_ds_name, module.params["name"]),
            )
        module.fail_json(
            msg=(
                "Local directory service {0} does not exist. A local "
                "directory service in a realm is named realm::name."
            ).format(local_ds_name)
        )

    group = _get_group(module, blade, local_ds_name)
    rename_to = None
    if state == "present":
        group, rename_to = _resolve_rename(module, blade, local_ds_name, group)

    if state == "absent" and group:
        delete_group(module, blade, local_ds_name, group)
    elif state == "absent":
        module.exit_json(changed=False)
    elif state == "present" and not group:
        create_group(module, blade, local_ds_name)
    else:
        update_group(module, blade, local_ds_name, group, rename_to)


if __name__ == "__main__":
    main()
