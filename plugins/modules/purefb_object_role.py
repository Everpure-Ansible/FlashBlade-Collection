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
module: purefb_object_role
version_added: '1.30.0'
short_description: Manage FlashBlade Object Store Roles
description:
- Create, update or delete FlashBlade object store roles and attach or
  detach object store access policies to them.
- Object store roles are part of Object Identity Federation. An identity
  from a trusted identity provider assumes a role through STS and acts with
  the permissions of the access policies attached to the role.
- Requires FlashBlade REST API 2.17 (Purity//FB 4.5.6) or higher.
- Roles cannot be renamed. Only the maximum session duration and the
  attached access policies can be changed after creation.
- Trust policy rules, which define who may assume the role, are not managed
  by this module.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - Name of the role within the object store account.
    type: str
    required: true
  account:
    description:
    - Name of the object store account that owns the role.
    - The account must already exist (see M(everpure.flashblade.purefb_s3acc)).
    type: str
    required: true
  state:
    description:
    - Whether the role should exist.
    default: present
    choices: [ absent, present ]
    type: str
  max_session_duration:
    description:
    - Maximum duration of a session that assumes the role.
    - Either a number of milliseconds or a number with a unit, for example
      C(1h), C(90m) or C(3600s).
    - Must be between C(1h) and C(12h). A new role defaults to C(1h).
    - When omitted on an existing role the current value is left unchanged.
    type: str
  access_policies:
    description:
    - Object store access policies to attach to the role.
    - Use the built-in C(pure:policy/...) names or account-scoped policies
      in the form C(account/policy). A bare policy name is qualified with
      I(account).
    - Policies already attached are left in place. Other policies attached
      to the role are only detached when listed in I(remove_access_policies)
      or when I(exclusive=true).
    - Every listed policy must exist.
    type: list
    elements: str
  remove_access_policies:
    description:
    - Object store access policies to detach from the role.
    - Uses the same naming as I(access_policies).
    - Every listed policy must exist. A policy that exists but is not
      attached to the role is left alone.
    type: list
    elements: str
  exclusive:
    description:
    - When C(true), every policy attached to the role that is not listed in
      I(access_policies) is detached.
    - Setting C(true) without I(access_policies) detaches every policy from
      the role.
    type: bool
    default: false
  context:
    description:
    - Name of fleet member on which to perform the operation.
    - This requires the array receiving the request is a member of a fleet
      and the context name to be a member of the same fleet.
    type: str
    default: ""
notes:
- The Everpure Quick Start Guide "Object Identity Federation on FlashBlade"
  describes how identity providers, roles and trust policies fit together.
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Create a role with the default one hour session duration
  everpure.flashblade.purefb_object_role:
    account: acme
    name: backup-writer
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create a role with a four hour session limit and two policies
  everpure.flashblade.purefb_object_role:
    account: acme
    name: analytics
    max_session_duration: 4h
    access_policies:
      - pure:policy/object-read
      - pure:policy/object-list
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Attach an account-scoped policy, keeping the policies already attached
  everpure.flashblade.purefb_object_role:
    account: acme
    name: analytics
    access_policies:
      - acme/reports-only
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Detach a policy from a role
  everpure.flashblade.purefb_object_role:
    account: acme
    name: analytics
    remove_access_policies:
      - pure:policy/object-list
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Make the attached policy set exactly object-read
  everpure.flashblade.purefb_object_role:
    account: acme
    name: analytics
    access_policies:
      - pure:policy/object-read
    exclusive: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete a role
  everpure.flashblade.purefb_object_role:
    account: acme
    name: analytics
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = r"""
role:
  description: The role after the operation.
  returned: success, when I(state=present)
  type: dict
  contains:
    name:
      description: Full name of the role in the form C(account/role).
      type: str
      sample: acme/analytics
    account:
      description: Name of the owning object store account.
      type: str
      sample: acme
    prn:
      description: Pure Resource Name of the role.
      type: str
      sample: "prn::iam:array-id/local:obj-account-id/42:role/analytics"
    max_session_duration:
      description: Maximum session duration in milliseconds.
      type: int
      sample: 14400000
    trusted_entities:
      description: Names of the entities trusted by the role.
      type: list
      elements: str
      sample: []
    access_policies:
      description: Names of the access policies attached to the role.
      type: list
      elements: str
      sample: ["pure:policy/object-read", "pure:policy/object-list"]
"""


HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        ObjectStoreRole,
        ObjectStoreRolePost,
    )
except ImportError:
    HAS_PYPURECLIENT = False

import re

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

MIN_REQUIRED_API_VERSION = "2.17"
MIN_SESSION_MS = 3600000
MAX_SESSION_MS = 43200000
UNIT_MS = {"h": 3600000, "m": 60000, "s": 1000}
DURATION_RE = re.compile(r"^(\d+)\s*([hms])$", re.IGNORECASE)


def _context_kwargs(module):
    """Return context_names kwargs when a context is set.

    Roles require REST 2.17, the same version that introduced fleet
    contexts, so context_names is always accepted once the gate passed.
    """
    if module.params["context"]:
        return {"context_names": [module.params["context"]]}
    return {}


def _duration_to_ms(module, value):
    """Convert a duration ('2h', '90m', '3600s' or milliseconds) to ms."""
    text = str(value).strip()
    if text.isdigit():
        millis = int(text)
    else:
        match = DURATION_RE.match(text)
        if not match:
            module.fail_json(
                msg=(
                    "Invalid max_session_duration '{0}'. Use milliseconds or a "
                    "value such as 1h, 90m or 3600s."
                ).format(value)
            )
        millis = int(match.group(1)) * UNIT_MS[match.group(2).lower()]
    if millis < MIN_SESSION_MS or millis > MAX_SESSION_MS:
        module.fail_json(
            msg=(
                "max_session_duration must be between 1h and 12h "
                "(3600000 to 43200000 milliseconds), got '{0}'."
            ).format(value)
        )
    return millis


def _dedupe(items):
    seen = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def _full_role_name(module):
    return module.params["account"] + "/" + module.params["name"]


def _qualify_policy(module, policy):
    """Built-in and account/policy names pass through; bare names get the account."""
    if "/" in policy:
        return policy
    return module.params["account"] + "/" + policy


def _not_found(res):
    """True when a lookup by name failed only because the object is missing."""
    return "does not exist" in str(get_error_message(res)).lower()


def _account_exists(module, blade):
    account = module.params["account"]
    res = blade.get_object_store_accounts(names=[account], **_context_kwargs(module))
    if res.status_code == 200:
        return bool(list(res.items))
    if not _not_found(res):
        module.fail_json(
            msg="Failed to look up object store account {0}. Error: {1}".format(
                account, get_error_message(res)
            )
        )
    return False


def _get_role(module, blade):
    role_name = _full_role_name(module)
    res = blade.get_object_store_roles(names=[role_name], **_context_kwargs(module))
    if res.status_code == 200:
        items = list(res.items)
        return items[0] if items else None
    if not _not_found(res):
        module.fail_json(
            msg="Failed to look up object store role {0}. Error: {1}".format(
                role_name, get_error_message(res)
            )
        )
    return None


def _get_attached_policies(module, blade):
    role_name = _full_role_name(module)
    res = blade.get_object_store_roles_object_store_access_policies(
        member_names=[role_name], **_context_kwargs(module)
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to list access policies for role {0}. Error: {1}".format(
                role_name, get_error_message(res)
            )
        )
    return [link.policy.name for link in list(res.items)]


def _check_policies_exist(module, blade, policies):
    for policy in policies:
        res = blade.get_object_store_access_policies(
            names=[policy], **_context_kwargs(module)
        )
        if res.status_code != 200 or not list(res.items):
            module.fail_json(msg="Access policy {0} does not exist.".format(policy))


def _requested_policies(module, key):
    """Qualified, de-duplicated policy names from a list parameter."""
    return _dedupe(
        [_qualify_policy(module, policy) for policy in (module.params[key] or [])]
    )


def _desired_policy_changes(module, current):
    """Return (to_attach, to_detach) from the parameters and the attached list."""
    wanted = _requested_policies(module, "access_policies")
    unwanted = _requested_policies(module, "remove_access_policies")
    clash = [policy for policy in wanted if policy in unwanted]
    if clash:
        module.fail_json(
            msg=(
                "Access policies {0} are listed in both access_policies "
                "and remove_access_policies."
            ).format(", ".join(clash))
        )
    if module.params["exclusive"]:
        unwanted.extend(
            [
                policy
                for policy in current
                if policy not in wanted and policy not in unwanted
            ]
        )
    to_attach = [policy for policy in wanted if policy not in current]
    to_detach = [policy for policy in unwanted if policy in current]
    return to_attach, to_detach


def _policies_to_validate(module, current, to_attach):
    """Names that must exist before anything is written.

    Policies to attach must exist. So must the names in
    remove_access_policies that are not attached: an attached policy exists
    by definition, but a mistyped name would otherwise pass silently as
    "nothing to detach".
    """
    unattached = [
        policy
        for policy in _requested_policies(module, "remove_access_policies")
        if policy not in current
    ]
    return to_attach + unattached


def _apply_policy_changes(module, blade, to_attach, to_detach):
    """Attach and detach the given policies; return True if anything changed."""
    changed = False
    role_name = _full_role_name(module)
    ctx = _context_kwargs(module)
    for policy in to_attach:
        changed = True
        if not module.check_mode:
            res = blade.post_object_store_roles_object_store_access_policies(
                member_names=[role_name], policy_names=[policy], **ctx
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to attach access policy {0} to role {1}. Error: {2}".format(
                        policy, role_name, get_error_message(res)
                    )
                )
    for policy in to_detach:
        changed = True
        if not module.check_mode:
            res = blade.delete_object_store_roles_object_store_access_policies(
                member_names=[role_name], policy_names=[policy], **ctx
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to detach access policy {0} from role {1}. Error: {2}".format(
                        policy, role_name, get_error_message(res)
                    )
                )
    return changed


def _role_facts(module, role, policies):
    account = getattr(role, "account", None)
    entities = getattr(role, "trusted_entities", None)
    if not isinstance(entities, list):
        entities = []
    return {
        "name": getattr(role, "name", None) or _full_role_name(module),
        "account": getattr(account, "name", None) or module.params["account"],
        "prn": getattr(role, "prn", None),
        "max_session_duration": getattr(role, "max_session_duration", None),
        "trusted_entities": [getattr(entity, "name", None) for entity in entities],
        "access_policies": policies,
    }


def create_role(module, blade, duration_ms):
    changed = True
    role_name = _full_role_name(module)
    wanted, _unused = _desired_policy_changes(module, [])
    _check_policies_exist(module, blade, _policies_to_validate(module, [], wanted))
    if module.check_mode:
        module.exit_json(
            changed=changed,
            role={
                "name": role_name,
                "account": module.params["account"],
                "prn": None,
                "max_session_duration": (
                    duration_ms if duration_ms is not None else MIN_SESSION_MS
                ),
                "trusted_entities": [],
                "access_policies": wanted,
            },
        )
    if duration_ms is not None:
        body = ObjectStoreRolePost(max_session_duration=duration_ms)
    else:
        body = ObjectStoreRolePost()
    res = blade.post_object_store_roles(
        names=[role_name], object_store_role=body, **_context_kwargs(module)
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to create object store role {0}. Error: {1}".format(
                role_name, get_error_message(res)
            )
        )
    _apply_policy_changes(module, blade, wanted, [])
    role = _get_role(module, blade)
    policies = _get_attached_policies(module, blade)
    module.exit_json(changed=changed, role=_role_facts(module, role, policies))


def update_role(module, blade, role, duration_ms):
    changed = False
    role_name = _full_role_name(module)
    current_policies = _get_attached_policies(module, blade)
    to_attach, to_detach = _desired_policy_changes(module, current_policies)
    _check_policies_exist(
        module, blade, _policies_to_validate(module, current_policies, to_attach)
    )
    if duration_ms is not None and duration_ms != getattr(
        role, "max_session_duration", None
    ):
        changed = True
        if not module.check_mode:
            res = blade.patch_object_store_roles(
                names=[role_name],
                object_store_role=ObjectStoreRole(max_session_duration=duration_ms),
                **_context_kwargs(module),
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to update object store role {0}. Error: {1}".format(
                        role_name, get_error_message(res)
                    )
                )
    if _apply_policy_changes(module, blade, to_attach, to_detach):
        changed = True
    if changed and not module.check_mode:
        role = _get_role(module, blade)
        policies = _get_attached_policies(module, blade)
        facts = _role_facts(module, role, policies)
    else:
        policies = [
            policy for policy in current_policies if policy not in to_detach
        ] + to_attach
        facts = _role_facts(module, role, policies)
        if duration_ms is not None:
            facts["max_session_duration"] = duration_ms
    module.exit_json(changed=changed, role=facts)


def delete_role(module, blade):
    changed = True
    role_name = _full_role_name(module)
    if not module.check_mode:
        res = blade.delete_object_store_roles(
            names=[role_name], **_context_kwargs(module)
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete object store role {0}. Error: {1}".format(
                    role_name, get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str", required=True),
            account=dict(type="str", required=True),
            state=dict(type="str", default="present", choices=["absent", "present"]),
            max_session_duration=dict(type="str"),
            access_policies=dict(type="list", elements="str"),
            remove_access_policies=dict(type="list", elements="str"),
            exclusive=dict(type="bool", default=False),
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
                "Minimum version required: {0} (Purity//FB 4.5.6+)"
            ).format(MIN_REQUIRED_API_VERSION)
        )

    if not module.params["context"]:
        # If no context is provided set the context to the local array name
        fleet_res = blade.get_fleets()
        if fleet_res.status_code == 200 and list(fleet_res.items):
            module.params["context"] = list(blade.get_arrays().items)[0].name

    duration_ms = None
    if module.params["max_session_duration"] is not None:
        duration_ms = _duration_to_ms(module, module.params["max_session_duration"])

    state = module.params["state"]
    if not _account_exists(module, blade):
        if state == "absent":
            module.exit_json(changed=False)
        module.fail_json(
            msg="Object store account {0} does not exist.".format(
                module.params["account"]
            )
        )

    role = _get_role(module, blade)
    if state == "absent":
        if role:
            delete_role(module, blade)
        module.exit_json(changed=False)
    if role:
        update_role(module, blade, role, duration_ms)
    create_role(module, blade, duration_ms)


if __name__ == "__main__":
    main()
