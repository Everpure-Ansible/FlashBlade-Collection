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
module: purefb_bucket_lifecycle
version_added: '1.30.0'
short_description: Manage FlashBlade bucket lifecycle policy rules
description:
- Create, update or delete the rules of an object store bucket's lifecycle policy.
- Every bucket owns one lifecycle policy, named C(<bucket>/lifecycle-policy), which
  the array creates with the bucket. This module manages the rules of that policy;
  the policy object itself cannot be created, deleted or disabled over the REST API.
- A rule can be filtered by object key prefix and/or object tags, expire current
  versions after a duration or on a date, expire previous versions after a duration
  while keeping a number of them, and abort incomplete multipart uploads.
- Requires FlashBlade REST API 2.29 or later (Purity//FB 4.8.6+). On older arrays
  use M(everpure.flashblade.purefb_lifecycle), which cannot set tag filters or
  I(keep_previous_versions_count).
- Options omitted from a task leave the corresponding rule setting unchanged.
  To remove a setting from an existing rule set the duration to C(0d), I(prefix)
  to an empty string or I(tags) to an empty list. I(keep_previous_versions_count)
  cannot be removed once set.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  bucket:
    description:
    - Name of the bucket whose lifecycle policy holds the rule.
    type: str
    required: true
  name:
    description:
    - Name of the rule. Must be unique within the bucket.
    - Rules cannot be renamed.
    type: str
    required: true
  state:
    description:
    - Create or update the rule (C(present)) or delete it (C(absent)).
    type: str
    default: present
    choices: [ absent, present ]
  enabled:
    description:
    - Whether the rule is enabled.
    - A new rule is enabled unless this is set to C(false). When omitted for an
      existing rule the current setting is kept.
    type: bool
  prefix:
    description:
    - Object key prefix identifying the objects the rule applies to.
    - Maximum length is 1024 characters. An empty string removes the prefix
      from an existing rule.
    type: str
  tags:
    description:
    - Object tags identifying the objects the rule applies to.
    - An object must carry every listed tag to be selected. Up to 10 tags.
    - Cannot be combined with a non-zero I(abort_uploads_after); the array
      rejects a multipart-upload abort on a tag-filtered rule, including a
      request that removes the tags and adds the abort at the same time.
    - An empty list removes the tags from an existing rule.
    type: list
    elements: dict
    suboptions:
      key:
        description:
        - Tag key. Must be 1 to 128 characters.
        type: str
        required: true
      value:
        description:
        - Tag value. Maximum length is 256 characters.
        type: str
        required: true
  keep_previous_for:
    description:
    - Time after which previous (non-current) versions are marked expired.
    - Enter as whole days (C(d)) or weeks (C(w)), for example C(30d) or C(2w).
    type: str
  keep_previous_versions_count:
    description:
    - Number of previous versions of each object to keep when I(keep_previous_for)
      expires them. Range is 1 to 100.
    - Requires I(keep_previous_for) in the same task.
    type: int
  keep_current_for:
    description:
    - Time after which current versions are marked expired.
    - Enter as whole days (C(d)) or weeks (C(w)).
    - Mutually exclusive with I(keep_current_until); setting it on a rule that
      has a I(keep_current_until) date replaces the date.
    type: str
  keep_current_until:
    description:
    - Date after which current versions are marked expired, as C(YYYY-MM-DD).
    - B(Note:) a date in the past expires every matching object as soon as it is
      created; the module warns when such a date is given.
    - Mutually exclusive with I(keep_current_for); setting it on a rule that
      has a I(keep_current_for) duration replaces the duration.
    type: str
  abort_uploads_after:
    description:
    - Time after which incomplete multipart uploads are aborted.
    - Enter as whole days (C(d)) or weeks (C(w)).
    - Not accepted on a tag-filtered rule. To add it to a rule that has tags,
      remove the tags in a separate task first.
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

EXAMPLES = r"""
- name: Expire previous versions under logs/ after 30 days, keeping the last three
  everpure.flashblade.purefb_bucket_lifecycle:
    bucket: foo
    name: logs-previous
    prefix: logs/
    keep_previous_for: 30d
    keep_previous_versions_count: 3
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Expire current versions after 90 days and abort stale uploads after a day
  everpure.flashblade.purefb_bucket_lifecycle:
    bucket: foo
    name: current-90d
    keep_current_for: 90d
    abort_uploads_after: 1d
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Expire previous versions of objects tagged env=dev after a week
  everpure.flashblade.purefb_bucket_lifecycle:
    bucket: foo
    name: dev-previous
    tags:
      - key: env
        value: dev
    keep_previous_for: 1w
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Expire current versions under tmp/ on a fixed date
  everpure.flashblade.purefb_bucket_lifecycle:
    bucket: foo
    name: tmp-cutoff
    prefix: tmp/
    keep_current_until: "2030-01-01"
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Disable a rule without deleting it
  everpure.flashblade.purefb_bucket_lifecycle:
    bucket: foo
    name: logs-previous
    enabled: false
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Delete a rule
  everpure.flashblade.purefb_bucket_lifecycle:
    bucket: foo
    name: logs-previous
    state: absent
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
"""

RETURN = r"""
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        BucketLifecyclePolicyRuleFilter,
        BucketLifecyclePolicyRulePatch,
        BucketLifecyclePolicyRulePost,
        ObjectStoreTag,
    )
except ImportError:
    HAS_PYPURECLIENT = False

from datetime import datetime, timezone

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.everpure.flashblade.plugins.module_utils.purefb import (
    get_system,
    purefb_argument_spec,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.common import (
    get_error_message,
    get_rest_api_version,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.time_utils import (
    time_to_milliseconds,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.version import (
    LooseVersion,
)

MIN_REQUIRED_API_VERSION = "2.29"
MAX_PREFIX_LENGTH = 1024
MAX_TAGS = 10
MAX_TAG_KEY_LENGTH = 128
MAX_TAG_VALUE_LENGTH = 256

# module option -> REST field for the whole-day durations
DURATION_FIELDS = {
    "keep_previous_for": "keep_previous_version_for",
    "keep_current_for": "keep_current_version_for",
    "abort_uploads_after": "abort_incomplete_multipart_uploads_after",
}
RETENTION_FIELDS = (
    "keep_previous_version_for",
    "keep_current_version_for",
    "keep_current_version_until",
    "abort_incomplete_multipart_uploads_after",
)
# what a rule looks like before it exists; create reuses the update diff
EMPTY_RULE = {
    "enabled": True,
    "prefix": None,
    "tags": [],
    "keep_previous_version_for": 0,
    "keep_previous_versions_count": 0,
    "keep_current_version_for": 0,
    "keep_current_version_until": 0,
    "abort_incomplete_multipart_uploads_after": 0,
}


def _context_kwargs(module):
    """Return context_names kwargs when a fleet context is set.

    Every lifecycle-policy method takes context_names from REST 2.29, the
    module's minimum, so no separate gate is needed.
    """
    if module.params["context"]:
        return {"context_names": [module.params["context"]]}
    return {}


def _convert_date_to_epoch(module):
    """Return keep_current_until as epoch milliseconds, or None if unset."""
    value = module.params["keep_current_until"]
    if not value:
        return None
    try:
        until = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        module.fail_json(
            msg="Incorrect date format for keep_current_until, use YYYY-MM-DD"
        )
    if until < datetime.now(timezone.utc).replace(tzinfo=None):
        module.warn(
            "This value of `keep_current_until` will permanently delete objects "
            "as they are created. Using this date is not recommended"
        )
    return int((until - datetime(1970, 1, 1)).total_seconds() * 1000)


def _tags_param(module):
    """Return the tags option as a sorted list of (key, value) pairs, or None."""
    if module.params["tags"] is None:
        return None
    return sorted((tag["key"], tag["value"]) for tag in module.params["tags"])


def _current_state(rule):
    """Normalise a BucketLifecyclePolicyRule response for comparison."""
    rule_filter = getattr(rule, "filter", None)
    tags = getattr(rule_filter, "tags", None) or []
    return {
        "enabled": bool(getattr(rule, "enabled", True)),
        "prefix": getattr(rule_filter, "prefix", None) or None,
        "tags": sorted((tag.key, tag.value) for tag in tags),
        "keep_previous_version_for": getattr(rule, "keep_previous_version_for", None)
        or 0,
        "keep_previous_versions_count": getattr(
            rule, "keep_previous_versions_count", None
        )
        or 0,
        "keep_current_version_for": getattr(rule, "keep_current_version_for", None)
        or 0,
        "keep_current_version_until": getattr(rule, "keep_current_version_until", None)
        or 0,
        "abort_incomplete_multipart_uploads_after": getattr(
            rule, "abort_incomplete_multipart_uploads_after", None
        )
        or 0,
    }


def _rule_changes(module, current, until_ms):
    """Return the REST fields whose desired value differs from current.

    Omitted options never appear in the result, so they are left unchanged
    on the array; a zero duration or date removes that setting. The array
    holds only one of keep_current_version_for / keep_current_version_until,
    so setting one zeroes the other in the same request. The filter is a
    sub-object, so when any part of it changes the whole desired filter
    (prefix and tags) is sent; an empty prefix string removes the prefix.
    """
    changes = {}
    for option, field in DURATION_FIELDS.items():
        if module.params[option] is not None:
            desired = time_to_milliseconds(module.params[option])
            if desired != current[field]:
                changes[field] = desired
    count = module.params["keep_previous_versions_count"]
    if count is not None and count != current["keep_previous_versions_count"]:
        changes["keep_previous_versions_count"] = count
    if until_ms is not None and until_ms != current["keep_current_version_until"]:
        changes["keep_current_version_until"] = until_ms
    if (
        changes.get("keep_current_version_for")
        and current["keep_current_version_until"]
    ):
        changes["keep_current_version_until"] = 0
    if (
        changes.get("keep_current_version_until")
        and current["keep_current_version_for"]
    ):
        changes["keep_current_version_for"] = 0
    enabled = module.params["enabled"]
    if enabled is not None and enabled != current["enabled"]:
        changes["enabled"] = enabled

    if module.params["prefix"] is not None:
        prefix = module.params["prefix"] or None
    else:
        prefix = current["prefix"]
    tags = _tags_param(module)
    if tags is None:
        tags = current["tags"]
    if prefix != current["prefix"] or tags != current["tags"]:
        filter_kwargs = {}
        if prefix is not None:
            filter_kwargs["prefix"] = prefix
        elif current["prefix"]:
            filter_kwargs["prefix"] = ""
        if tags or current["tags"]:
            filter_kwargs["tags"] = [
                ObjectStoreTag(key=key, value=value) for key, value in tags
            ]
        changes["filter"] = BucketLifecyclePolicyRuleFilter(**filter_kwargs)
    return changes


def _get_bucket(module, blade):
    res = blade.get_buckets(names=[module.params["bucket"]], **_context_kwargs(module))
    if res.status_code == 200:
        items = list(res.items)
        if items:
            return items[0]
    return None


def _get_rule(module, blade):
    """Return the named rule of the bucket's lifecycle policy, or None."""
    res = blade.get_buckets_lifecycle_policies_rules(
        bucket_names=[module.params["bucket"]],
        names=[module.params["name"]],
        **_context_kwargs(module)
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read lifecycle rule {0} for bucket {1}. Error: {2}".format(
                module.params["name"], module.params["bucket"], get_error_message(res)
            )
        )
    items = list(res.items)
    if items:
        return items[0]
    return None


def delete_rule(module, blade):
    """Delete a lifecycle policy rule"""
    changed = True
    if not module.check_mode:
        res = blade.delete_buckets_lifecycle_policies_rules(
            bucket_names=[module.params["bucket"]],
            names=[module.params["name"]],
            **_context_kwargs(module)
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete lifecycle rule {0} for bucket {1}. Error: {2}".format(
                    module.params["name"],
                    module.params["bucket"],
                    get_error_message(res),
                )
            )
    module.exit_json(changed=changed)


def create_rule(module, blade, until_ms):
    """Create a lifecycle policy rule"""
    body = _rule_changes(module, EMPTY_RULE, until_ms)
    # the POST model has no enabled field; a disabled rule is created then patched
    disable_after_create = body.pop("enabled", True) is False
    if not any(field in body for field in RETENTION_FIELDS):
        module.fail_json(
            msg=(
                "At least one of keep_previous_for, keep_current_for, "
                "keep_current_until or abort_uploads_after is required "
                "to create a lifecycle rule"
            )
        )
    changed = True
    if not module.check_mode:
        ctx = _context_kwargs(module)
        confirm = {}
        if body.get("keep_current_version_until"):
            confirm["confirm_date"] = True
        res = blade.post_buckets_lifecycle_policies_rules(
            bucket_names=[module.params["bucket"]],
            names=[module.params["name"]],
            rule=BucketLifecyclePolicyRulePost(**body),
            **confirm,
            **ctx
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to create lifecycle rule {0} for bucket {1}. Error: {2}".format(
                    module.params["name"],
                    module.params["bucket"],
                    get_error_message(res),
                )
            )
        if disable_after_create:
            res = blade.patch_buckets_lifecycle_policies_rules(
                bucket_names=[module.params["bucket"]],
                names=[module.params["name"]],
                rule=BucketLifecyclePolicyRulePatch(enabled=False),
                **ctx
            )
            if res.status_code != 200:
                module.fail_json(
                    msg=(
                        "Lifecycle rule {0} for bucket {1} was created but could "
                        "not be disabled. Error: {2}"
                    ).format(
                        module.params["name"],
                        module.params["bucket"],
                        get_error_message(res),
                    )
                )
    module.exit_json(changed=changed)


def update_rule(module, blade, rule, until_ms):
    """Update a lifecycle policy rule, sending only the changed fields"""
    changes = _rule_changes(module, _current_state(rule), until_ms)
    if not changes:
        module.exit_json(changed=False)
    changed = True
    if not module.check_mode:
        confirm = {}
        if changes.get("keep_current_version_until"):
            confirm["confirm_date"] = True
        res = blade.patch_buckets_lifecycle_policies_rules(
            bucket_names=[module.params["bucket"]],
            names=[module.params["name"]],
            rule=BucketLifecyclePolicyRulePatch(**changes),
            **confirm,
            **_context_kwargs(module)
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to update lifecycle rule {0} for bucket {1}. Error: {2}".format(
                    module.params["name"],
                    module.params["bucket"],
                    get_error_message(res),
                )
            )
    module.exit_json(changed=changed)


def _validate_params(module):
    for option in DURATION_FIELDS:
        value = module.params[option]
        if value and value[-1:].lower() not in ["w", "d"]:
            module.fail_json(
                msg="'{0}' format incorrect - specify as 'd' or 'w'".format(option)
            )
    count = module.params["keep_previous_versions_count"]
    if count is not None and not 1 <= count <= 100:
        module.fail_json(msg="keep_previous_versions_count must be between 1 and 100")
    prefix = module.params["prefix"]
    if prefix and len(prefix) > MAX_PREFIX_LENGTH:
        module.fail_json(
            msg="prefix must be at most {0} characters".format(MAX_PREFIX_LENGTH)
        )
    tags = module.params["tags"]
    if tags:
        if len(tags) > MAX_TAGS:
            module.fail_json(msg="At most {0} tags are allowed".format(MAX_TAGS))
        keys = [tag["key"] for tag in tags]
        if len(set(keys)) != len(keys):
            module.fail_json(msg="Tag keys must be unique")
        for tag in tags:
            if not 1 <= len(tag["key"]) <= MAX_TAG_KEY_LENGTH:
                module.fail_json(
                    msg="Tag keys must be 1 to {0} characters".format(
                        MAX_TAG_KEY_LENGTH
                    )
                )
            if len(tag["value"]) > MAX_TAG_VALUE_LENGTH:
                module.fail_json(
                    msg="Tag values must be at most {0} characters".format(
                        MAX_TAG_VALUE_LENGTH
                    )
                )
        # only a task that itself sets tags is refused here; the array rejects
        # the abort on a rule that still has tags, with its own message
        abort = module.params["abort_uploads_after"]
        if abort and time_to_milliseconds(abort):
            module.fail_json(
                msg=(
                    "tags cannot be combined with abort_uploads_after; the array "
                    "rejects a multipart-upload abort on a tag-filtered rule"
                )
            )


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            bucket=dict(type="str", required=True),
            name=dict(type="str", required=True),
            state=dict(type="str", default="present", choices=["absent", "present"]),
            enabled=dict(type="bool"),
            prefix=dict(type="str"),
            tags=dict(
                type="list",
                elements="dict",
                options=dict(
                    key=dict(type="str", required=True, no_log=False),
                    value=dict(type="str", required=True),
                ),
            ),
            keep_previous_for=dict(type="str"),
            keep_previous_versions_count=dict(type="int"),
            keep_current_for=dict(type="str"),
            keep_current_until=dict(type="str"),
            abort_uploads_after=dict(type="str"),
            context=dict(type="str", default=""),
        )
    )

    mutually_exclusive = [["keep_current_for", "keep_current_until"]]
    required_by = {"keep_previous_versions_count": ["keep_previous_for"]}

    module = AnsibleModule(
        argument_spec,
        mutually_exclusive=mutually_exclusive,
        required_by=required_by,
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
                "Minimum version required: {0} (Purity//FB 4.8.6+). "
                "Use the purefb_lifecycle module on this array."
            ).format(MIN_REQUIRED_API_VERSION)
        )

    _validate_params(module)

    if not module.params["context"]:
        # If no context is provided set the context to the local array name
        fleet_res = blade.get_fleets()
        if fleet_res.status_code == 200 and list(fleet_res.items):
            module.params["context"] = list(blade.get_arrays().items)[0].name

    if not _get_bucket(module, blade):
        module.fail_json(
            msg="Specified bucket {0} does not exist".format(module.params["bucket"])
        )

    until_ms = _convert_date_to_epoch(module)
    rule = _get_rule(module, blade)
    state = module.params["state"]

    if state == "absent" and rule:
        delete_rule(module, blade)
    elif state == "absent":
        module.exit_json(changed=False)
    elif state == "present" and not rule:
        create_rule(module, blade, until_ms)
    else:
        update_rule(module, blade, rule, until_ms)


if __name__ == "__main__":
    main()
