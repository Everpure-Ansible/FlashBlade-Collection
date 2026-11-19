#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2020, Simon Dodsley (simon@everpuredata.com)
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
module: purefb_lifecycle
version_added: '1.4.0'
short_description: Manage FlashBlade object lifecycles
description:
- Manage lifecycles for object buckets
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  state:
    description:
    - Create or delete lifecycle rule
    default: present
    type: str
    choices: [ absent, present ]
  bucket:
    description:
    - Bucket the lifecycle rule applies to
    - For a bucket in a realm use C(realm::bucket). A realm-scoped
      administrator must use the realm-qualified name; a bare name is not
      placed in, or resolved to, the administrator's realm.
    - The name of one bucket is needed. A pattern or a list of names is
      refused. The letter case of the name does not matter.
    type: str
    required: true
  name:
    description:
    - Name of the lifecycle rule
    - The name is given without the bucket and without a realm.
    - A name that holds a comma is refused, the array reads it as a list of
      names.
    type: str
    required: true
  enabled:
    description:
    - State of lifecycle rule
    type: bool
    default: true
  keep_previous_for:
    aliases: [ keep_for ]
    description:
    - Time after which previous versions will be marked expired.
    - Enter as days (d) or weeks (w). Range is 1 - 2147483647 days.
    type: str
  keep_current_for:
    description:
    - Time after which current versions will be marked expired.
    - Enter as days (d) or weeks (w). Range is 1 - 2147483647 days.
    - On an existing rule this takes the place of a date set with
      I(keep_current_until).
    version_added: "1.8.0"
    type: str
  keep_current_until:
    description:
    - Date after which current versions will be marked expired.
    - Enter as date in form YYYY-MM-DD.
    - On an existing rule this takes the place of a duration set with
      I(keep_current_for).
    - B(Note:) setting a date in the past will delete ALL objects with
      the value of I(prefix) as they are created.
    version_added: "1.8.0"
    type: str
  abort_uploads_after:
    description:
    - Duration of time after which incomplete multipart uploads will be aborted.
    - Enter as days (d) or weeks (w). Range is 1 - 2147483647 days.
    version_added: "1.8.0"
    type: str
  prefix:
    description:
    - Object key prefix identifying one or more objects in the bucket
    type: str
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
- name: Create a lifecycle rule called bar for bucket foo
  everpure.flashblade.purefb_lifecycle:
    name: bar
    bucket: foo
    keep_previous_for: 2d
    abort_uploads_after: 1d
    keep_current_until: 2020-11-23
    prefix: test
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
- name: Create a lifecycle rule called bar for bucket foo in realm tenant1
  everpure.flashblade.purefb_lifecycle:
    name: bar
    bucket: tenant1::foo
    keep_current_for: 30d
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
- name: Modify a lifecycle rule
  everpure.flashblade.purefb_lifecycle:
    name: bar
    bucket: foo
    keep_previous_for: 10d
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
- name: Delete lifecycle rule foo from bucket foo
  everpure.flashblade.purefb_lifecycle:
    name: foo
    bucket: bar
    state: absent
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
"""

RETURN = r"""
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        LifecycleRulePost,
        LifecycleRulePatch,
        ReferenceWritable,
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
from ansible_collections.everpure.flashblade.plugins.module_utils.time_utils import (
    time_to_milliseconds,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.common import (
    get_error_message,
    get_rest_api_version,
)
from datetime import datetime

CONTEXT_API_VERSION = "2.17"
# What the array answers when the object asked for is not there. Any other
# failed read is reported with the message of the array.
NOT_FOUND = "does not exist"


def _context_kwargs(module, api_version):
    """Return context_names kwargs when a fleet context applies, else {}"""
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and module.params["context"]
    ):
        return {"context_names": [module.params["context"]]}
    return {}


def _check_one_name(module, option, kind):
    """Fail when the value of option holds a comma.

    The array reads a comma as a separator of names and answers a look-up
    of such a value with every object it names, so the task would no longer
    be about the one rule it names.
    """
    value = module.params[option]
    if value and "," in value:
        module.fail_json(
            msg="{0} {1} holds a comma, which the array reads as a separator "
            "of names. Give the name of one {2}.".format(option, value, kind)
        )


def _duration(module, option):
    """Return a duration option in milliseconds, or None when it is not set"""
    if module.params[option]:
        return time_to_milliseconds(module.params[option])
    return None


def _get_bucket(module, blade, api_version):
    """Return the bucket named by the task, or None when it does not exist.

    The array reads a name as a pattern and answers with every bucket that
    matches, whatever the letter case of the name. Only the bucket that has
    the name asked for is taken, never one that matches it some other way.
    """
    name = module.params["bucket"]
    res = blade.get_buckets(names=[name], **_context_kwargs(module, api_version))
    if res.status_code != 200:
        error = get_error_message(res)
        if NOT_FOUND in str(error).lower():
            return None
        module.fail_json(
            msg="Failed to read bucket {0}. Error: {1}".format(name, error)
        )
    for bucket in list(res.items):
        if str(bucket.name).strip().lower() == name.strip().lower():
            return bucket
    return None


def _get_rule(module, blade, api_version):
    """Return the rule named by the task, or None when it does not exist"""
    res = blade.get_lifecycle_rules(
        names=[module.params["bucket"] + "/" + module.params["name"]],
        **_context_kwargs(module, api_version)
    )
    if res.status_code != 200:
        error = get_error_message(res)
        if NOT_FOUND in str(error).lower():
            return None
        module.fail_json(
            msg="Failed to read lifecycle rule {0} for bucket {1}. Error: {2}".format(
                module.params["name"], module.params["bucket"], error
            )
        )
    items = list(res.items)
    if items:
        return items[0]
    return None


def _convert_date_to_epoch(module):
    try:
        unix_date = datetime.strptime(module.params["keep_current_until"], "%Y-%m-%d")
    except ValueError:
        module.fail_json(msg="Incorrect data format, should be YYYY-MM-DD")
    if unix_date < datetime.utcnow():
        module.warn(
            "This value of `keep_current_until` will permanently delete objects "
            "as they are created. Using this date is not recommended"
        )
    epoch_milliseconds = int((unix_date - datetime(1970, 1, 1)).total_seconds() * 1000)
    return epoch_milliseconds


def delete_rule(module, blade):
    """Delete lifecycle rule"""
    changed = True
    api_version = get_rest_api_version(blade)
    if not module.check_mode:
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            res = blade.delete_lifecycle_rules(
                names=[module.params["bucket"] + "/" + module.params["name"]],
                context_names=[module.params["context"]],
            )
        else:
            res = blade.delete_lifecycle_rules(
                names=[module.params["bucket"] + "/" + module.params["name"]]
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


def create_rule(module, blade):
    """Create lifecycle policy"""
    changed = True
    api_version = get_rest_api_version(blade)
    if (
        not module.params["keep_previous_for"]
        and not module.params["keep_current_until"]
        and not module.params["keep_current_for"]
        and not module.params["abort_uploads_after"]
    ):
        module.fail_json(
            msg="At least one parameter is required to create a new lifecycle rule"
        )

    if not module.check_mode:
        attr = LifecycleRulePost(
            bucket=ReferenceWritable(name=module.params["bucket"]),
            rule_id=module.params["name"],
            keep_previous_version_for=_duration(module, "keep_previous_for"),
            keep_current_version_until=module.params["keep_current_until"],
            keep_current_version_for=_duration(module, "keep_current_for"),
            abort_incomplete_multipart_uploads_after=_duration(
                module, "abort_uploads_after"
            ),
            prefix=module.params["prefix"],
        )
        if attr.keep_current_version_until:
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.post_lifecycle_rules(
                    rule=attr,
                    confirm_date=True,
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.post_lifecycle_rules(rule=attr, confirm_date=True)
        else:
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.post_lifecycle_rules(
                    rule=attr, context_names=[module.params["context"]]
                )
            else:
                res = blade.post_lifecycle_rules(rule=attr)
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to create lifecycle rule {0} for bucket {1}. Error: {2}".format(
                    module.params["name"],
                    module.params["bucket"],
                    get_error_message(res),
                )
            )
        if not module.params["enabled"]:
            attr = LifecycleRulePatch(enabled=module.params["enabled"])
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.patch_lifecycle_rules(
                    names=[module.params["bucket"] + "/" + module.params["name"]],
                    lifecycle=attr,
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.patch_lifecycle_rules(
                    names=[module.params["bucket"] + "/" + module.params["name"]],
                    lifecycle=attr,
                )
            if res.status_code != 200:
                module.warn(
                    "Lifecycle Rule {0} did not enable correctly. "
                    "Please chack your FlashBlade".format(module.params["name"])
                )
    module.exit_json(changed=changed)


def update_rule(module, blade, rule):
    """Update snapshot policy"""
    changed = False
    api_version = get_rest_api_version(blade)
    current_rule = {
        "prefix": rule.prefix,
        "abort_incomplete_multipart_uploads_after": rule.abort_incomplete_multipart_uploads_after,
        "keep_current_version_for": rule.keep_current_version_for,
        "keep_previous_version_for": rule.keep_previous_version_for,
        "keep_current_version_until": rule.keep_current_version_until,
        "enabled": rule.enabled,
    }
    if not module.params["prefix"]:
        prefix = current_rule["prefix"]
    else:
        prefix = module.params["prefix"]
    if not module.params["keep_previous_for"]:
        keep_previous_for = current_rule["keep_previous_version_for"]
    else:
        keep_previous_for = time_to_milliseconds(module.params["keep_previous_for"])
    if not module.params["keep_current_for"]:
        keep_current_for = current_rule["keep_current_version_for"]
    else:
        keep_current_for = time_to_milliseconds(module.params["keep_current_for"])
    if not module.params["abort_uploads_after"]:
        abort_uploads_after = current_rule["abort_incomplete_multipart_uploads_after"]
    else:
        abort_uploads_after = time_to_milliseconds(module.params["abort_uploads_after"])
    if not module.params["keep_current_until"]:
        keep_current_until = current_rule["keep_current_version_until"]
    else:
        keep_current_until = module.params["keep_current_until"]
    # The array holds a duration or a date for current versions, never both,
    # so the one the task sets removes the one the rule has
    if module.params["keep_current_until"] and keep_current_for:
        keep_current_for = 0
    if module.params["keep_current_for"] and keep_current_until:
        keep_current_until = 0
    new_rule = {
        "prefix": prefix,
        "abort_incomplete_multipart_uploads_after": abort_uploads_after,
        "keep_current_version_for": keep_current_for,
        "keep_previous_version_for": keep_previous_for,
        "keep_current_version_until": keep_current_until,
        "enabled": module.params["enabled"],
    }
    if current_rule != new_rule:
        changed = True
        if not module.check_mode:
            attr = LifecycleRulePatch(
                keep_previous_version_for=new_rule["keep_previous_version_for"],
                keep_current_version_for=new_rule["keep_current_version_for"],
                keep_current_version_until=new_rule["keep_current_version_until"],
                abort_incomplete_multipart_uploads_after=new_rule[
                    "abort_incomplete_multipart_uploads_after"
                ],
                prefix=new_rule["prefix"],
                enabled=new_rule["enabled"],
            )
            if attr.keep_current_version_until:
                if (
                    LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                    and module.params["context"]
                ):
                    res = blade.patch_lifecycle_rules(
                        names=[module.params["bucket"] + "/" + module.params["name"]],
                        lifecycle=attr,
                        confirm_date=True,
                        context_names=[module.params["context"]],
                    )
                else:
                    res = blade.patch_lifecycle_rules(
                        names=[module.params["bucket"] + "/" + module.params["name"]],
                        lifecycle=attr,
                        confirm_date=True,
                    )
            else:
                if (
                    LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                    and module.params["context"]
                ):
                    res = blade.patch_lifecycle_rules(
                        names=[module.params["bucket"] + "/" + module.params["name"]],
                        lifecycle=attr,
                        context_names=[module.params["context"]],
                    )
                else:
                    res = blade.patch_lifecycle_rules(
                        names=[module.params["bucket"] + "/" + module.params["name"]],
                        lifecycle=attr,
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


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(type="str", default="present", choices=["absent", "present"]),
            enabled=dict(type="bool", default=True),
            bucket=dict(type="str", required=True),
            name=dict(type="str", required=True),
            prefix=dict(
                type="str",
            ),
            keep_previous_for=dict(type="str", aliases=["keep_for"]),
            keep_current_for=dict(type="str"),
            keep_current_until=dict(type="str"),
            abort_uploads_after=dict(type="str"),
            context=dict(type="str", default=""),
        )
    )

    mutually_exclusive = [["keep_current_for", "keep_current_until"]]

    module = AnsibleModule(
        argument_spec, mutually_exclusive=mutually_exclusive, supports_check_mode=True
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    # A task is about one rule of one bucket
    _check_one_name(module, "bucket", "bucket")
    _check_one_name(module, "name", "lifecycle rule")

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

    if module.params["keep_previous_for"] and not module.params["keep_previous_for"][
        -1:
    ].lower() in ["w", "d"]:
        module.fail_json(
            msg="'keep_previous_for' format incorrect - specify as 'd' or 'w'"
        )
    if module.params["keep_current_for"] and not module.params["keep_current_for"][
        -1:
    ].lower() in ["w", "d"]:
        module.fail_json(
            msg="'keep_current_for' format incorrect - specify as 'd' or 'w'"
        )
    if module.params["abort_uploads_after"] and not module.params[
        "abort_uploads_after"
    ][-1:].lower() in ["w", "d"]:
        module.fail_json(
            msg="'abort_uploads_after' format incorrect - specify as 'd' or 'w'"
        )

    bucket = _get_bucket(module, blade, api_version)
    if not bucket:
        module.fail_json(
            msg="Specified bucket {0} does not exist".format(module.params["bucket"])
        )
    # The array finds a bucket whatever the letter case of the name, but it
    # changes a rule only under the stored spelling of the bucket name, so
    # every later request and message uses the name the array returned
    module.params["bucket"] = bucket.name
    if state == "present" and getattr(bucket, "destroyed", False):
        # The array hides the rules of a destroyed bucket and refuses new ones
        module.fail_json(
            msg="Specified bucket {0} is destroyed. A lifecycle rule cannot be "
            "created or changed until the bucket is recovered.".format(
                module.params["bucket"]
            )
        )
    if module.params["keep_current_until"]:
        module.params["keep_current_until"] = _convert_date_to_epoch(module)
    rule = _get_rule(module, blade, api_version)

    if rule and state == "present":
        update_rule(module, blade, rule)
    elif state == "present" and not rule:
        create_rule(module, blade)
    elif state == "absent" and rule:
        delete_rule(module, blade)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
