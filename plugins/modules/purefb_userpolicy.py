#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2021, Simon Dodsley (simon@everpuredata.com)
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
module: purefb_userpolicy
version_added: '1.6.0'
short_description: Manage FlashBlade Object Store User Access Policies
description:
- Add or Remove FlashBlade Object Store Access Policies for Account User
- The user of an account in a realm is addressed with I(account) set to
  C(realm::account). A realm-scoped administrator must use the realm-qualified
  name; a bare name is not placed in, or resolved to, the administrator's realm.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - Name of the Object Store User
    - The user to have the policy request applied to
    type: str
  account:
    description:
    - Name of the Object Store Account associated with the user
    - For an account in a realm use C(realm::account).
    type: str
  state:
    description:
    - Define whether the Access Policy should be added or deleted
    - Option to list all available policies
    default: present
    choices: [ absent, present, show ]
    type: str
  policy:
    description:
    - Policies to added or deleted from the Object Store User
    - Only valid policies can be used
    - Use I(state=show) to see available policies
    - A policy of an account is named C(account/policy), or
      C(realm::account/policy) for an account in a realm. The built-in
      C(pure:policy/...) policies can be used with the users of every account.
    - The user and an account policy must belong to the same account.
    - A policy that does not exist fails the task, and so does adding a policy
      of another account. Both are found before anything is changed.
    type: list
    elements: str
  context:
    description:
    - Name of fleet member on which to perform the operation.
    - This requires the array receiving the request is a member of a fleet
      and the context name to be a member of the same fleet.
    type: str
    default: ""
    version_added: "1.22.0"
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: List existng ruser access policies for a specific user
  everpure.flashblade.purefb_userpolicy:
    state: show
    account: foo
    name: bar
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3
  register: policy_list

- name: List all available user access policies
  everpure.flashblade.purefb_userpolicy:
    state: show
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3
  register: policy_list

- name: Add user access policies to account user foo/bar
  everpure.flashblade.purefb_userpolicy:
    name: bar
    account: foo
    policy:
      - pure:policy/bucket-create
      - pure:policy/bucket-delete
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Add a built-in and an account access policy to user bar of account foo in realm myrealm
  everpure.flashblade.purefb_userpolicy:
    name: bar
    account: myrealm::foo
    policy:
      - pure:policy/object-read
      - myrealm::foo/mypolicy
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Delete user access policies to account user foo/bar
  everpure.flashblade.purefb_userpolicy:
    name: bar
    account: foo
    policy:
      - pure:policy/bucket-create
      - pure:policy/bucket-delete
    state: absent
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3
"""

RETURN = r"""
policy_list:
  description:
  - Returns the list of access policies for a user
  - If no user specified returns all available access policies
  - For I(state=present) and I(state=absent) this is the list the task leaves
    the user with, in check mode the list it would leave.
  returned: always
  type: list
  elements: str
  sample: ['pure:policy/object-list', 'pure:policy/bucket-list', 'pure:policy/object-read', 'pure:policy/bucket-delete', 'pure:policy/full-access']
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

CONTEXT_API_VERSION = "2.17"


def _context_kwargs(module, api_version):
    """Return context_names kwargs when a fleet context applies."""
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and module.params["context"]
    ):
        return {"context_names": [module.params["context"]]}
    return {}


def _account_id(obj):
    """Return the id of the account a user or a policy belongs to, or None.

    A built-in policy belongs to no account.
    """
    return getattr(getattr(obj, "account", None), "id", None)


def _get_user(module, blade, username, ctx):
    """Return the object store user, or fail with the reason it cannot be read."""
    res = blade.get_object_store_users(names=[username], **ctx)
    if res.status_code == 200:
        users = list(res.items)
        if users:
            return users[0]
    else:
        reason = get_error_message(res)
        if "does not exist" not in reason:
            module.fail_json(
                msg="Failed to get account user {0}. Error: {1}".format(
                    username, reason
                )
            )
    module.fail_json(msg="Account User {0} does not exist".format(username))


def _get_policy(module, blade, policy, ctx):
    """Return the access policy, or fail with the reason it cannot be read."""
    res = blade.get_object_store_access_policies(names=[policy], **ctx)
    if res.status_code == 200:
        policies = list(res.items)
        if policies:
            return policies[0]
    else:
        reason = get_error_message(res)
        if "does not exist" not in reason:
            module.fail_json(
                msg="Failed to get access policy {0}. Error: {1}".format(policy, reason)
            )
    hint = ""
    if "::" in module.params["account"] and "::" not in policy:
        hint = " A policy of an account in a realm is named realm::account/policy."
    module.fail_json(msg="Access policy {0} does not exist.{1}".format(policy, hint))


def _wanted_policies(module, blade, ctx):
    """Return (name, policy) for every policy of the task, each policy once.

    The array matches names without regard to case, so the id decides whether
    two entries of the task are the same policy.
    """
    wanted = []
    seen = set()
    for name in module.params["policy"]:
        policy = _get_policy(module, blade, name, ctx)
        if policy.id not in seen:
            seen.add(policy.id)
            wanted.append((name, policy))
    return wanted


def _check_same_account(module, username, user, wanted):
    """Fail when a policy of the task belongs to another account than the user.

    The array refuses such a policy, so the refusal is made before anything is
    written and in check mode too. Built-in policies belong to no account.
    """
    user_account = _account_id(user)
    for name, policy in wanted:
        policy_account = _account_id(policy)
        if user_account and policy_account and policy_account != user_account:
            module.fail_json(
                msg="Access policy {0} cannot be added to account user {1}: the user "
                "and the policy must belong to the same account.".format(name, username)
            )


def _user_policies(module, blade, username, ctx):
    """Return the policy memberships of a user, or fail with the array's reason."""
    res = blade.get_object_store_access_policies_object_store_users(
        member_names=[username], **ctx
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to get access policies for account user {0}. "
            "Error: {1}".format(username, get_error_message(res))
        )
    return list(res.items)


def add_policy(module, blade, user=None):
    """Add a single or list of policies to an account user"""
    ctx = _context_kwargs(module, get_rest_api_version(blade))
    username = module.params["account"] + "/" + module.params["name"]
    # Every read and every refusal comes before the first write: a task that
    # fails has attached nothing, and check mode reports what a run would do.
    wanted = _wanted_policies(module, blade, ctx)
    _check_same_account(module, username, user, wanted)
    members = _user_policies(module, blade, username, ctx)
    attached = set(member.policy.id for member in members)
    missing = [(name, policy) for name, policy in wanted if policy.id not in attached]
    changed = bool(missing)
    user_policy_list = [member.policy.name for member in members]
    if changed and module.check_mode:
        user_policy_list += [policy.name for name, policy in missing]
    elif changed:
        for name, policy in missing:
            res = blade.post_object_store_access_policies_object_store_users(
                member_names=[username], policy_names=[name], **ctx
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to add policy {0} to account user {1}. Error: {2}".format(
                        name, username, get_error_message(res)
                    )
                )
        user_policy_list = [
            member.policy.name
            for member in _user_policies(module, blade, username, ctx)
        ]
    module.exit_json(changed=changed, policy_list=user_policy_list)


def remove_policy(module, blade):
    """Remove a single or list of policies to an account user"""
    ctx = _context_kwargs(module, get_rest_api_version(blade))
    username = module.params["account"] + "/" + module.params["name"]
    wanted = _wanted_policies(module, blade, ctx)
    members = _user_policies(module, blade, username, ctx)
    attached = set(member.policy.id for member in members)
    present = [(name, policy) for name, policy in wanted if policy.id in attached]
    changed = bool(present)
    if changed and module.check_mode:
        leaving = set(policy.id for name, policy in present)
        members = [member for member in members if member.policy.id not in leaving]
    elif changed:
        for name, policy in present:
            res = blade.delete_object_store_access_policies_object_store_users(
                member_names=[username], policy_names=[name], **ctx
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to remove policy {0} from account user {1}. Error: {2}".format(
                        name, username, get_error_message(res)
                    )
                )
        members = _user_policies(module, blade, username, ctx)
    module.exit_json(
        changed=changed, policy_list=[member.policy.name for member in members]
    )


def list_policy(module, blade):
    """List Object Store User Access Policies"""
    # Listing is read-only: it never changes the array, in or out of check mode.
    changed = False
    ctx = _context_kwargs(module, get_rest_api_version(blade))
    policy_list = []
    if module.params["account"] and module.params["name"]:
        username = module.params["account"] + "/" + module.params["name"]
        for user_policy in _user_policies(module, blade, username, ctx):
            policy_list.append(user_policy.policy.name)
    else:
        policies = blade.get_object_store_access_policies(**ctx)
        if policies.status_code != 200:
            module.fail_json(
                msg="Failed to get Object Store User Access Policies. "
                "Error: {0}".format(get_error_message(policies))
            )
        for policy in list(policies.items):
            policy_list.append(policy.name)
    module.exit_json(changed=changed, policy_list=policy_list)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(
                type="str", default="present", choices=["absent", "present", "show"]
            ),
            name=dict(type="str"),
            account=dict(type="str"),
            policy=dict(type="list", elements="str"),
            context=dict(type="str", default=""),
        )
    )
    required_if = [
        ["state", "present", ["name", "account", "policy"]],
        ["state", "absent", ["name", "account", "policy"]],
    ]
    module = AnsibleModule(
        argument_spec, required_if=required_if, supports_check_mode=True
    )

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

    state = module.params["state"]
    # state=show without account/name lists every policy on the array, so the
    # user lookup (and its name concatenation) must only run when a user is named.
    user = None
    if module.params["account"] and module.params["name"]:
        username = module.params["account"] + "/" + module.params["name"]
        user = _get_user(module, blade, username, _context_kwargs(module, api_version))
    if state == "show":
        list_policy(module, blade)
    elif state == "present":
        add_policy(module, blade, user)
    elif state == "absent":
        remove_policy(module, blade)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
