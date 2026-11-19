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
module: purefb_quota_policy
version_added: '1.30.0'
short_description: Manage FlashBlade user and group quota policies
description:
- Create, update or delete FlashBlade user-group quota policies, their rules
  and the file systems they are attached to.
- A quota policy holds a set of per-user and per-group space limits and is
  attached to one or more file systems. A file system can carry at most one
  quota policy.
- Requires FlashBlade REST API version 2.25 or later (Purity//FB 4.8.0+).
- Rules are an unordered set keyed by their subject. Only I(quota_limit) and
  I(notifications) of an existing rule are changed in place; changing
  I(enforced) deletes and re-creates the rule.
- The array requires its usage check to be skipped for every rule change and
  for enabling or disabling a policy, so those writes always send
  C(ignore_usage). The check still applies when a policy is attached to a
  file system, see I(ignore_usage).
- Rules with a SID subject can only be attached to file systems created on
  Purity//FB 4.8.0 or later. The array rejects the attachment of a policy
  holding SID based rules to an older file system.
- The legacy per-file-system quotas managed by
  M(everpure.flashblade.purefb_userquota) and
  M(everpure.flashblade.purefb_groupquota) cannot be used on a file system
  that has a quota policy attached. Use I(import_from) to migrate them.
- A policy can hold up to 800 rules and an array up to 1000 policies and
  10,000 rules.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - Name of the quota policy.
    - A policy in a realm is named C(realm::name). The same name without the
      realm is a different policy at the array level.
    type: str
    required: true
  state:
    description:
    - Whether the quota policy should exist or not.
    - I(state=absent) detaches the policy from every file system before
      deleting it, as the array refuses to delete an attached policy.
    type: str
    default: present
    choices: [ absent, present ]
  enabled:
    description:
    - Whether the policy is enabled.
    - When omitted the array default (enabled) applies on create and the
      existing value is left untouched on update.
    type: bool
  rename:
    description:
    - New name for the quota policy. Applies to an existing policy only; a
      policy that does not exist yet is created as I(name).
    - Idempotent when a policy with the new name already exists and the
      policy I(name) does not. The module fails without changing anything
      when another policy already has the new name.
    - A rename cannot move a policy into, out of or between realms. For a
      policy in a realm the new name is given either without the realm, in
      which case the policy keeps its realm, or as C(realm::name) with the
      realm of the policy. Any other realm is refused.
    - The array matches names without regard to case and does not rename a
      policy to its own name, so a new name that differs from the name of
      the policy only in case is refused.
    type: str
  import_from:
    description:
    - Name of a file system whose legacy user and group quotas (set with
      M(everpure.flashblade.purefb_userquota),
      M(everpure.flashblade.purefb_groupquota) or the file system default
      quotas) are copied into the rules of the new policy.
    - The import does not attach the policy and leaves the legacy quotas in
      place; attach it afterwards with I(file_systems) and
      I(delete_existing_quotas=true) to replace them.
    - Only used when the policy is created. Mutually exclusive with I(rules).
    - A file system in a realm is given by its full name C(realm::filesystem).
    type: str
  rules:
    description:
    - The complete set of rules of the policy. Rules on the array that are
      not listed are deleted. When omitted the rules are left untouched.
    - Each rule is identified by its I(type) and exactly one of I(id),
      I(name) or I(sid); the default rule types take no subject.
    type: list
    elements: dict
    suboptions:
      type:
        description:
        - Kind of subject the rule applies to.
        - C(user-default) and C(group-default) set the limit for every user
          or group without a specific rule.
        type: str
        required: true
        choices: [ user, group, user-default, group-default ]
      id:
        description:
        - UID of the user or GID of the group.
        type: int
      name:
        description:
        - Name of the user or group, resolved through the configured
          directory service.
        type: str
      sid:
        description:
        - SMB SID of the user. SID based group quotas are not supported by
          the array.
        type: str
      quota_limit:
        description:
        - Space limit of the rule, for example C(10G) or C(500M). Must be
          greater than zero.
        type: str
        required: true
      enforced:
        description:
        - If C(true) the limit is a hard quota and writes beyond it fail.
        - Purity//FB 4.8 accepts only enforced rules and rejects C(false)
          with C(Policy cannot have unenforced rules).
        type: bool
        default: true
      notifications:
        description:
        - Whether the affected user or group is notified when the quota is
          reached.
        type: str
        default: account
        choices: [ account, none ]
  file_systems:
    description:
    - The complete list of file systems the policy is attached to. File
      systems not listed are detached. When omitted the attachments are
      left untouched.
    - A file system can carry only one quota policy; the module fails when
      a listed file system is attached to another policy.
    - New file systems are attached before the ones that are no longer
      listed are detached, so a file system the array refuses leaves the
      existing attachments in place.
    - A file system in a realm is named C(realm::filesystem). A policy in a
      realm can only be attached to file systems of the same realm and an
      array-level policy only to file systems outside of any realm. The
      module fails without changing anything when a listed file system is
      not in the scope of the policy.
    type: list
    elements: str
  ignore_usage:
    description:
    - Skip the array's check, when the policy is attached to a file system,
      that the current usage of every user and group of that file system is
      within the policy limits.
    - Rule changes and enabling or disabling a policy always skip the check
      because the array refuses them otherwise.
    type: bool
    default: false
  delete_existing_quotas:
    description:
    - Acknowledge that legacy user, group and default quotas configured on a
      file system are erased when the policy is attached to it. Without it
      the array rejects the attachment to a file system that has legacy
      quotas.
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
- name: Create a quota policy with a user rule and a group rule
  everpure.flashblade.purefb_quota_policy:
    name: engineering
    rules:
      - type: user
        id: 1001
        quota_limit: 10G
      - type: group
        id: 2001
        quota_limit: 100G
        notifications: none
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Attach the policy to two file systems
  everpure.flashblade.purefb_quota_policy:
    name: engineering
    file_systems:
      - home
      - scratch
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Replace the rule set and set a default limit for every user
  everpure.flashblade.purefb_quota_policy:
    name: engineering
    rules:
      - type: user
        id: 1001
        quota_limit: 20G
      - type: user-default
        quota_limit: 5G
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Migrate the legacy quotas of a file system into a new policy
  everpure.flashblade.purefb_quota_policy:
    name: home_quotas
    import_from: home
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Disable and rename a policy
  everpure.flashblade.purefb_quota_policy:
    name: engineering
    enabled: false
    rename: engineering_old
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Attach a policy in realm tenant1 to a file system of that realm and rename it to tenant1::eng
  everpure.flashblade.purefb_quota_policy:
    name: tenant1::engineering
    file_systems:
      - tenant1::home
    rename: eng
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete a policy (detaching it from its file systems first)
  everpure.flashblade.purefb_quota_policy:
    name: engineering_old
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = r"""
policy:
  description:
  - State of the quota policy after the task. In check mode this is the
    state before any change.
  returned: when I(state=present)
  type: dict
  contains:
    name:
      description: Name of the policy, C(realm::name) for a policy in a realm.
      type: str
    enabled:
      description: Whether the policy is enabled.
      type: bool
    rules:
      description: Rules of the policy.
      type: list
      elements: dict
      contains:
        name:
          description:
          - Array-assigned positional name of the rule (C(policy.N)). It
            changes when an earlier rule is deleted.
          type: str
        type:
          description: Rule type (user, group, user-default or group-default).
          type: str
        subject:
          description: Subject of the rule (id, name and sid; unused keys are null).
          type: dict
        quota_limit:
          description: Space limit in bytes.
          type: int
        enforced:
          description: Whether the limit is enforced.
          type: bool
        notifications:
          description: Notification setting (account or none).
          type: str
    file_systems:
      description: Names of the file systems the policy is attached to.
      type: list
      elements: str
  sample:
    name: engineering
    enabled: true
    rules:
      - name: engineering.1
        type: user
        subject:
          id: 1001
          name: null
          sid: null
        quota_limit: 10737418240
        enforced: true
        notifications: account
    file_systems:
      - home
"""


HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        UserGroupQuotaPolicy,
        UserGroupQuotaPolicyPost,
        UserGroupQuotaPolicyRulePatch,
        UserGroupQuotaPolicyRulePost,
        UserGroupQuotaSubject,
    )
except ImportError:
    HAS_PYPURECLIENT = False


from ansible.module_utils.basic import AnsibleModule, human_to_bytes
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

MIN_REQUIRED_API_VERSION = "2.25"
DEFAULT_RULE_TYPES = ("user-default", "group-default")
SUBJECT_FIELDS = ("id", "name", "sid")
# Module option values are lower-case; the array spells them capitalised.
NOTIFICATIONS_TO_API = {"account": "Account", "none": "None"}


def _context_kwargs(module):
    """Return context_names kwargs when a fleet context is set.

    Quota policies require REST 2.25, above the 2.17 fleet-context floor, so
    the array always accepts context_names when we reach here.
    """
    if module.params["context"]:
        return {"context_names": [module.params["context"]]}
    return {}


def _usage_kwargs(module):
    """ignore_usage for the one call the array checks usage on: attach.

    Rule POST and PATCH and the policy PATCH (enable/disable) are refused
    without ignore_usage whether or not the policy is attached, so those
    always send it.
    """
    if module.params["ignore_usage"]:
        return {"ignore_usage": True}
    return {}


def _normalise_rules(module):
    """Validate the rules option and return it in array terms.

    Each entry becomes a dict with type, field (id, name, sid or None for the
    default types), value, quota_limit in bytes, enforced and the API
    spelling of notifications. Returns None when rules were not given.
    """
    rules = module.params["rules"]
    if rules is None:
        return None
    normalised = []
    seen = set()
    for rule in rules:
        rule_type = rule["type"]
        given = [field for field in SUBJECT_FIELDS if rule.get(field) is not None]
        if rule_type in DEFAULT_RULE_TYPES:
            if given:
                module.fail_json(
                    msg="Rule type {0} does not take a subject (id, name or sid)".format(
                        rule_type
                    )
                )
            field, value = None, None
        else:
            if len(given) != 1:
                module.fail_json(
                    msg="Rule type {0} requires exactly one of id, name or sid".format(
                        rule_type
                    )
                )
            field = given[0]
            value = rule[field]
            if field == "sid" and rule_type == "group":
                module.fail_json(
                    msg="SID based rules are only supported for user quotas"
                )
        try:
            limit = human_to_bytes(rule["quota_limit"])
        except ValueError as err:
            module.fail_json(
                msg="Invalid quota_limit {0}: {1}".format(rule["quota_limit"], err)
            )
        if not limit:
            module.fail_json(msg="quota_limit must be greater than zero")
        key = (rule_type, field, value)
        if key in seen:
            module.fail_json(
                msg="Duplicate rule for {0} {1}".format(
                    rule_type, "default" if value is None else value
                )
            )
        seen.add(key)
        normalised.append(
            {
                "type": rule_type,
                "field": field,
                "value": value,
                "quota_limit": limit,
                "enforced": rule["enforced"],
                "notifications": NOTIFICATIONS_TO_API[rule["notifications"]],
            }
        )
    return normalised


def _match_rule(desired, current_rules):
    """Return the array rule with the same type and subject, or None."""
    for current in current_rules:
        if getattr(current, "quota_type", None) != desired["type"]:
            continue
        if desired["field"] is None:
            return current
        subject = getattr(current, "subject", None)
        if (
            subject is not None
            and getattr(subject, desired["field"], None) == desired["value"]
        ):
            return current
    return None


def _realm_of(name):
    """Return the realm of a realm::name name, empty for an array-level name."""
    return name.rpartition("::")[0]


def _resolve_rename(module):
    """Return the full name the policy is renamed to, or None without rename.

    The array keeps a realm policy in its realm when the new name is bare, so
    a bare new name is resolved into the realm of the policy and that one name
    is used for every lookup. A new name in another realm is refused here, as
    the array does not move a policy with a rename.
    """
    rename = module.params["rename"]
    if not rename:
        return None
    name = module.params["name"]
    realm = _realm_of(name)
    if "::" not in rename:
        return "{0}::{1}".format(realm, rename) if realm else rename
    # the array matches names without regard to case
    if _realm_of(rename).lower() != realm.lower():
        module.fail_json(
            msg=(
                "Cannot rename quota policy {0} to {1}: a rename cannot change "
                "the realm of a policy. Give the new name without a realm{2}."
            ).format(
                name,
                rename,
                " or as {0}::<name>".format(realm) if realm else "",
            )
        )
    if realm:
        # one spelling of the realm; main() sends the one the array keeps
        return "{0}::{1}".format(realm, rename.rpartition("::")[2])
    return rename


def _check_file_system_scope(module):
    """Fail when file_systems names a file system the policy cannot have.

    The array attaches a policy in a realm only to file systems of that realm
    and an array-level policy only to file systems outside of any realm. It
    refuses any other one only after the other options were applied, or a
    new policy was created, and check mode cannot foresee that, so such a
    name is refused before anything is written.
    """
    name = module.params["name"]
    realm = _realm_of(name)
    for file_system in module.params["file_systems"] or []:
        # the array matches names without regard to case
        if _realm_of(file_system).lower() == realm.lower():
            continue
        if realm:
            reason = (
                "a policy in realm {0} can only be attached to file systems "
                "of that realm, named {0}::<filesystem>"
            ).format(realm)
        else:
            reason = (
                "an array-level policy can only be attached to file systems "
                "outside of any realm"
            )
        module.fail_json(
            msg="Cannot attach quota policy {0} to file system {1}: {2}.".format(
                name, file_system, reason
            )
        )


def _rule_hint(module, rule):
    """Explain a refused rule write when the rule is listed without the realm.

    After a rename that gave the new name of a realm policy without the realm
    the array lists the rules of the policy without it, and refuses to change
    or delete them until the policy is renamed with its full name.
    """
    rule_name = getattr(rule, "name", None)
    if (
        _realm_of(module.params["name"])
        and isinstance(rule_name, str)
        and "::" not in rule_name
    ):
        return (
            " The array lists this rule without the realm of its policy and "
            "does not change or delete it in that state. Renaming the policy "
            "with this module, in a task of its own, restores the rule names."
        )
    return ""


def _get_policy(module, blade, name):
    res = blade.get_user_group_quota_policies(names=[name], **_context_kwargs(module))
    if res.status_code == 200:
        items = list(res.items)
        if items:
            return items[0]
    return None


def _get_rules(module, blade, policy):
    # by policy id: a realm policy and an array-level policy can share the
    # name the array reports for their rules
    res = blade.get_user_group_quota_policies_rules(
        filter="policy.id='{0}'".format(policy.id),
        **_context_kwargs(module),
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to get rules of quota policy {0}. Error: {1}".format(
                module.params["name"], get_error_message(res)
            )
        )
    return list(res.items)


def _get_members(module, blade, policy):
    """Return the sorted names of the file systems the policy is attached to.

    The attachments are read by policy id, as the array can list those of a
    realm policy without the realm in either name. A realm policy is only ever
    attached to file systems of its own realm, so such a name is qualified.
    """
    res = blade.get_user_group_quota_policies_members(
        policy_ids=[policy.id], **_context_kwargs(module)
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to get members of quota policy {0}. Error: {1}".format(
                module.params["name"], get_error_message(res)
            )
        )
    realm = _realm_of(policy.name)
    members = set()
    for item in res.items:
        member_name = getattr(getattr(item, "member", None), "name", None)
        if member_name:
            if realm and "::" not in member_name:
                member_name = "{0}::{1}".format(realm, member_name)
            members.add(member_name)
    return sorted(members)


def _attached_policy(module, blade, file_system):
    """Return the name of the quota policy attached to a file system, or None."""
    res = blade.get_file_systems_user_group_quota_policies(
        member_names=[file_system], **_context_kwargs(module)
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to get the quota policy of file system {0}. Error: {1}".format(
                file_system, get_error_message(res)
            )
        )
    items = list(res.items)
    if items:
        return getattr(getattr(items[0], "policy", None), "name", None)
    return None


def _policy_facts(module, blade):
    policy = _get_policy(module, blade, module.params["name"])
    if policy is None:
        return {}
    rules = []
    for rule in _get_rules(module, blade, policy):
        subject = getattr(rule, "subject", None)
        notifications = getattr(rule, "notifications", None)
        rules.append(
            {
                "name": rule.name,
                "type": getattr(rule, "quota_type", None),
                "subject": {
                    "id": getattr(subject, "id", None),
                    "name": getattr(subject, "name", None),
                    "sid": getattr(subject, "sid", None),
                },
                "quota_limit": getattr(rule, "quota_limit", None),
                "enforced": getattr(rule, "enforced", None),
                "notifications": (
                    notifications.lower() if notifications is not None else None
                ),
            }
        )
    return {
        "name": policy.name,
        "enabled": getattr(policy, "enabled", None),
        "rules": rules,
        "file_systems": _get_members(module, blade, policy),
    }


def _rule_label(desired):
    if desired["field"] is None:
        return desired["type"]
    return "{0} {1} {2}".format(desired["type"], desired["field"], desired["value"])


def _desired_from_current(current):
    """Describe an array rule in the form _normalise_rules produces."""
    subject = getattr(current, "subject", None)
    field, value = None, None
    if getattr(current, "quota_type", None) not in DEFAULT_RULE_TYPES:
        for candidate in SUBJECT_FIELDS:
            if getattr(subject, candidate, None) not in (None, ""):
                field, value = candidate, getattr(subject, candidate)
                break
    return {
        "type": getattr(current, "quota_type", None),
        "field": field,
        "value": value,
        "quota_limit": getattr(current, "quota_limit", None),
        "enforced": bool(getattr(current, "enforced", True)),
        "notifications": getattr(current, "notifications", None) or "Account",
    }


def _post_rule(module, blade, desired, fail=True, note=""):
    """Add a rule; fail the module on error unless fail is False.

    note is appended to the failure message, see create_policy.
    """
    kwargs = dict(
        quota_type=desired["type"],
        quota_limit=desired["quota_limit"],
        enforced=desired["enforced"],
        notifications=desired["notifications"],
    )
    if desired["field"] is not None:
        kwargs["subject"] = UserGroupQuotaSubject(
            **{desired["field"]: desired["value"]}
        )
    # the array rejects rule writes without ignore_usage, see _usage_kwargs
    res = blade.post_user_group_quota_policies_rules(
        policy_names=[module.params["name"]],
        rule=UserGroupQuotaPolicyRulePost(**kwargs),
        ignore_usage=True,
        **_context_kwargs(module),
    )
    if res.status_code != 200 and fail:
        module.fail_json(
            msg="Failed to add {0} rule to quota policy {1}. Error: {2}{3}".format(
                _rule_label(desired),
                module.params["name"],
                get_error_message(res),
                note,
            )
        )
    return res


def _delete_rule(module, blade, rule):
    # rule names are positional (<policy>.<n>) and renumber after a delete,
    # so rules are always addressed by their immutable id
    res = blade.delete_user_group_quota_policies_rules(
        ids=[rule.id],
        policy_names=[module.params["name"]],
        **_context_kwargs(module),
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to delete rule {0} from quota policy {1}. Error: {2}{3}".format(
                rule.name,
                module.params["name"],
                get_error_message(res),
                _rule_hint(module, rule),
            )
        )


def _usage_hint(module, res):
    if module.params["ignore_usage"]:
        return ""
    if "usage" in get_error_message(res).lower():
        return " Set ignore_usage=true to skip the current-usage check."
    return ""


def reconcile_rules(module, blade, policy, desired_rules):
    """Make the array rules match desired_rules; return True when changed."""
    if desired_rules is None:
        return False
    current_rules = _get_rules(module, blade, policy)
    to_add, to_patch, to_replace = [], [], []
    matched = set()
    for desired in desired_rules:
        current = _match_rule(desired, current_rules)
        if current is None:
            to_add.append(desired)
            continue
        matched.add(current.id)
        if bool(getattr(current, "enforced", True)) != desired["enforced"]:
            # enforced is not patchable: the rule is deleted and re-added
            to_replace.append((current, desired))
            continue
        current_notifications = str(getattr(current, "notifications", "")).lower()
        if (
            getattr(current, "quota_limit", None) != desired["quota_limit"]
            or current_notifications != desired["notifications"].lower()
        ):
            # the array resets a patchable field that is left out of the
            # PATCH body (notifications falls back to None), so both are sent
            patch = {
                "quota_limit": desired["quota_limit"],
                "notifications": desired["notifications"],
            }
            to_patch.append((current, patch))
    to_delete = [rule for rule in current_rules if rule.id not in matched]
    if not (to_add or to_patch or to_replace or to_delete):
        return False
    if module.check_mode:
        return True
    for current, patch in to_patch:
        res = blade.patch_user_group_quota_policies_rules(
            ids=[current.id],
            rule=UserGroupQuotaPolicyRulePatch(**patch),
            ignore_usage=True,
            **_context_kwargs(module),
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to update rule {0} of quota policy {1}. Error: {2}{3}".format(
                    current.name,
                    module.params["name"],
                    get_error_message(res),
                    _rule_hint(module, current),
                )
            )
    for current in to_delete:
        _delete_rule(module, blade, current)
    for current, desired in to_replace:
        _delete_rule(module, blade, current)
        res = _post_rule(module, blade, desired, fail=False)
        if res.status_code != 200:
            error = get_error_message(res)
            # put the original rule back so a rejected change does not drop it
            _post_rule(module, blade, _desired_from_current(current), fail=False)
            module.fail_json(
                msg="Failed to replace {0} rule of quota policy {1}. Error: {2}".format(
                    _rule_label(desired), module.params["name"], error
                )
            )
    for desired in to_add:
        _post_rule(module, blade, desired)
    return True


def _as_member(module, file_system):
    """Return the name a file system is sent under beside the policy name.

    The array matches names without regard to case, but it refuses a file
    system whose realm is not written as the array keeps it. The policy is
    addressed by the name the array keeps, see main(), so the realm of the
    file system goes out as that name has it.
    """
    realm = _realm_of(module.params["name"])
    if realm and "::" in file_system:
        return "{0}::{1}".format(realm, file_system.rpartition("::")[2])
    return file_system


def _attach(module, blade, file_system, note=""):
    """Attach the policy to one file system; note is appended on refusal."""
    kwargs = _usage_kwargs(module)
    if module.params["delete_existing_quotas"]:
        kwargs["delete_existing_user_group_quota_settings"] = True
    res = blade.post_user_group_quota_policies_file_systems(
        policy_names=[module.params["name"]],
        member_names=[_as_member(module, file_system)],
        **kwargs,
        **_context_kwargs(module),
    )
    if res.status_code != 200:
        error = get_error_message(res)
        hint = _usage_hint(module, res)
        lowered = error.lower()
        if not module.params["delete_existing_quotas"] and (
            "purequota" in lowered or "already has quotas" in lowered
        ):
            hint += (
                " Set delete_existing_quotas=true to replace legacy quotas "
                "configured on the file system."
            )
        module.fail_json(
            msg=(
                "Failed to attach quota policy {0} to file system {1}. "
                "Error: {2}{3}{4}"
            ).format(module.params["name"], file_system, error, hint, note)
        )


def _detach(module, blade, file_system):
    res = blade.delete_user_group_quota_policies_file_systems(
        policy_names=[module.params["name"]],
        member_names=[_as_member(module, file_system)],
        **_context_kwargs(module),
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to detach quota policy {0} from file system {1}. Error: {2}".format(
                module.params["name"], file_system, get_error_message(res)
            )
        )


def reconcile_members(module, blade, current, note=""):
    """Attach and detach file systems to match the option; True when changed.

    current is the list of file systems the policy is attached to now. note
    is appended to every attach refusal, see create_policy.
    """
    desired = module.params["file_systems"]
    if desired is None:
        return False
    # the array matches names without regard to case: a file system written
    # in another case than the array keeps is the one that is attached
    attached = set(fs.lower() for fs in current)
    wanted = {}
    for file_system in sorted(set(desired)):
        wanted.setdefault(file_system.lower(), file_system)
    to_attach = [wanted[key] for key in sorted(wanted) if key not in attached]
    to_detach = [fs for fs in current if fs.lower() not in wanted]
    if not (to_attach or to_detach):
        return False
    for file_system in to_attach:
        other = _attached_policy(module, blade, file_system)
        if other and other.lower() != module.params["name"].lower():
            module.fail_json(
                msg=(
                    "File system {0} is already attached to quota policy {1}; "
                    "a file system can have only one quota policy.{2}"
                ).format(file_system, other, note)
            )
    if module.check_mode:
        return True
    # attach first: a refused attachment then leaves the policy on the file
    # systems it had, not on none
    for file_system in to_attach:
        _attach(module, blade, file_system, note)
    for file_system in to_detach:
        _detach(module, blade, file_system)
    return True


def delete_policy(module, blade, policy):
    name = module.params["name"]
    members = _get_members(module, blade, policy)
    if not module.check_mode:
        # the array refuses to delete an attached policy
        for file_system in members:
            _detach(module, blade, file_system)
        # by id: the array refuses the name of an unattached policy when the
        # attachment of a namesake in a realm is listed without that realm
        res = blade.delete_user_group_quota_policies(
            ids=[policy.id], **_context_kwargs(module)
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete quota policy {0}. Error: {1}".format(
                    name, get_error_message(res)
                )
            )
    module.exit_json(changed=True)


def create_policy(module, blade, desired_rules):
    name = module.params["name"]
    if module.check_mode:
        module.exit_json(changed=True, policy={})
    body = {}
    if module.params["enabled"] is not None:
        body["enabled"] = module.params["enabled"]
    kwargs = {}
    if module.params["import_from"]:
        kwargs["file_system_names"] = [module.params["import_from"]]
    res = blade.post_user_group_quota_policies(
        names=[name],
        policy=UserGroupQuotaPolicyPost(**body),
        **kwargs,
        **_context_kwargs(module),
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to create quota policy {0}. Error: {1}".format(
                name, get_error_message(res)
            )
        )
    created = [item.name for item in res.items if isinstance(item.name, str)]
    if created:
        # the array keeps the realm in its own spelling, see main()
        module.params["name"] = created[0]
    # the policy now exists, so a refused rule or attachment must say so;
    # the next run takes the update path and only adds what is missing
    for desired in desired_rules or []:
        _post_rule(
            module,
            blade,
            desired,
            note=" The policy was created; fix rules and re-run.",
        )
    # a new policy is not attached to anything yet
    reconcile_members(
        module,
        blade,
        [],
        note=" The policy was created; fix the attachment and re-run.",
    )
    module.exit_json(changed=True, policy=_policy_facts(module, blade))


def update_policy(module, blade, policy, desired_rules, new_name):
    name = module.params["name"]
    changed = False
    enabled = module.params["enabled"]
    members = _get_members(module, blade, policy)
    if enabled is not None and bool(getattr(policy, "enabled", True)) != enabled:
        changed = True
        if not module.check_mode:
            # like rule writes, the array refuses this without ignore_usage,
            # attached or not; see _usage_kwargs
            res = blade.patch_user_group_quota_policies(
                names=[name],
                policy=UserGroupQuotaPolicy(enabled=enabled),
                ignore_usage=True,
                **_context_kwargs(module),
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to {0} quota policy {1}. Error: {2}".format(
                        "enable" if enabled else "disable",
                        name,
                        get_error_message(res),
                    )
                )
    if reconcile_rules(module, blade, policy, desired_rules):
        changed = True
    if reconcile_members(module, blade, members):
        changed = True
    if new_name and new_name != name:
        changed = True
        if not module.check_mode:
            # the full name is sent: a bare name on a realm policy leaves the
            # array reporting its rules without the realm
            res = blade.patch_user_group_quota_policies(
                names=[name],
                policy=UserGroupQuotaPolicy(name=new_name),
                **_context_kwargs(module),
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to rename quota policy {0} to {1}. Error: {2}".format(
                        name, new_name, get_error_message(res)
                    )
                )
            module.params["name"] = new_name
    module.exit_json(changed=changed, policy=_policy_facts(module, blade))


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str", required=True),
            state=dict(type="str", default="present", choices=["absent", "present"]),
            enabled=dict(type="bool"),
            rename=dict(type="str"),
            import_from=dict(type="str"),
            rules=dict(
                type="list",
                elements="dict",
                options=dict(
                    type=dict(
                        type="str",
                        required=True,
                        choices=["user", "group", "user-default", "group-default"],
                    ),
                    id=dict(type="int"),
                    name=dict(type="str"),
                    sid=dict(type="str"),
                    quota_limit=dict(type="str", required=True),
                    enforced=dict(type="bool", default=True),
                    notifications=dict(
                        type="str", default="account", choices=["account", "none"]
                    ),
                ),
                mutually_exclusive=[["id", "name", "sid"]],
            ),
            file_systems=dict(type="list", elements="str"),
            ignore_usage=dict(type="bool", default=False),
            delete_existing_quotas=dict(type="bool", default=False),
            context=dict(type="str", default=""),
        )
    )

    module = AnsibleModule(
        argument_spec,
        mutually_exclusive=[["import_from", "rules"]],
        supports_check_mode=True,
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg=(
                "FlashBlade REST version not supported. "
                "Minimum version required: {0} (Purity//FB 4.8.0+)"
            ).format(MIN_REQUIRED_API_VERSION)
        )

    if not module.params["context"]:
        # If no context is provided set the context to the local array name
        fleet_res = blade.get_fleets()
        if fleet_res.status_code == 200 and list(fleet_res.items):
            module.params["context"] = list(blade.get_arrays().items)[0].name

    desired_rules = _normalise_rules(module)
    state = module.params["state"]
    name = module.params["name"]
    new_name = _resolve_rename(module) if state == "present" else None
    if state == "present":
        _check_file_system_scope(module)
    policy = _get_policy(module, blade, name)
    rename_to = None
    if new_name and new_name != name:
        renamed = _get_policy(module, blade, new_name)
        new_leaf = new_name.rpartition("::")[2]
        kept_leaf = renamed.name.rpartition("::")[2] if renamed is not None else ""
        if policy is None:
            # rename already applied by an earlier run, when renamed exists
            policy = renamed
        elif renamed is None:
            rename_to = new_name
        elif renamed.id != policy.id:
            # refused here, before enabled, rules and file_systems are applied
            module.fail_json(
                msg=(
                    "Cannot rename quota policy {0} to {1}: a quota policy "
                    "named {1} already exists."
                ).format(name, new_name)
            )
        elif kept_leaf == new_leaf:
            # the array matches names without regard to case: both names are
            # this one policy, which already carries the new one
            pass
        elif kept_leaf.lower() == new_leaf.lower():
            # the array answers this with "Policy already exists.", after
            # enabled, rules and file_systems were applied
            module.fail_json(
                msg=(
                    "Cannot rename quota policy {0} to {1}: the new name "
                    "differs from the name of the policy only in case. The "
                    "array matches names without regard to case and does not "
                    "rename a policy to its own name."
                ).format(name, new_name)
            )
        else:
            rename_to = new_name
    if policy is not None and isinstance(policy.name, str):
        # The array matches names without regard to case, but it compares the
        # realm of a second name in a request (the new name, a file system)
        # as it is written. From here on the policy goes by the name the
        # array keeps, and the names sent beside it take the realm from it.
        module.params["name"] = policy.name
        if rename_to and _realm_of(policy.name):
            rename_to = "{0}::{1}".format(
                _realm_of(policy.name), rename_to.rpartition("::")[2]
            )

    if state == "absent" and policy is not None:
        delete_policy(module, blade, policy)
    elif state == "absent":
        module.exit_json(changed=False)
    elif policy is None:
        create_policy(module, blade, desired_rules)
    else:
        update_policy(module, blade, policy, desired_rules, rename_to)


if __name__ == "__main__":
    main()
