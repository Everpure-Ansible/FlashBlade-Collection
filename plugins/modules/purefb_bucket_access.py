#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2025, Simon Dodsley (simon@everpuredata.com)
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
module: purefb_bucket_access
version_added: '1.20.0'
short_description: Manage FlashBlade bucket access policies
description:
- Manage object store bucket policies.
- This modules allows the management of both bucket access and cross-origin
  resource sharing policies and their associated rules.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  state:
    description:
    - Create or delete policy or rule.
    default: present
    type: str
    choices: [ absent, present ]
  policy_type:
    description:
    - Type of policy
    type: str
    choices: [ access, cors ]
    default: access
  name:
    description:
    - Name of Object Store bucket the policy applies to.
    type: str
    required: true
  rule:
    description:
    - Name of the rule in the Bucket Policy
    - Required if I(state) is C(present)
    - A rule that exists with different content is replaced. The REST API
      has no PATCH for policy rules, so the replacement is created under a
      temporary name (the rule name with C(tmp) appended, kept within the
      63-character limit) before the existing rule is deleted. A rule the
      array refuses, or stores differently from the request, leaves the
      existing rule unchanged.
    type: str
  effect:
    description:
    - Allow S3 requests that match all of the I(actions) item selected.
      Rules are additive.
    - The FlashBlade REST API only supports C(allow) for bucket access
      policy rules. C(deny) is kept as a choice for backwards compatibility
      but is rejected with an error, because the array would silently store
      the rule as C(allow).
    type: str
    default: allow
    choices: [ allow, deny ]
  actions:
    description:
    - List of permissions to grant, for example C(s3:GetObject).
    - Actions are validated against the list the array publishes
      (GET /object-store-access-policy-actions, REST 2.2 and later), so an
      action introduced by a later Purity//FB release is accepted without a
      collection update. The task fails naming any action the array does
      not know. The collection's built-in list is used only when the array
      cannot be asked.
    - Which of the published actions a bucket access policy rule may hold is
      decided by the array. The FlashBlade REST API currently only supports
      C(s3:GetObject) in a bucket access policy rule. A list without it is
      refused by the array, and a list that also contains other actions is
      accepted but stored as C(s3:GetObject) alone. When the stored rule
      differs from the request the module fails and reports what the array
      kept, rather than replacing the rule on every run.
    - System-wide policy rules cannot be deleted or modified
    type: list
    elements: str
    default: [ "s3:GetObject" ]
  methods:
    description:
    - A list of HTTP methods that are permitted for cross-origin requests to access a bucket.
    - The only currently supported combination of allowed methods is all methods.
    choices:
      - GET
      - PUT
      - HEAD
      - POST
      - DELETE
    type: list
    elements: str
    default: ["GET", "PUT", "HEAD", "POST", "DELETE"]
  headers:
    description:
    - A list of headers that are permitted to be included in cross-origin requests to access a bucket.
    - The only currently supported allowed header is '*'.
    type: list
    elements: str
    default: ["*"]
  origins:
    description:
    - A list of origins (domains) that are permitted to make cross-origin requests to access a bucket.
    - The only currently supported allowed origin is '*'.
    type: list
    elements: str
    default: ["*"]
  resources:
    description:
    - The list of resources which this rule applies to.
    - The only currently supported resource is all objects in a bucket to
      which the parent policy belongs.
    elements: str
    type: list
    default: ["*"]
  principals:
    description:
    - Defines if the rule will apply to all object store users
      regardless of their origin or principal.
    - A rule for all principals is a public bucket policy. The array refuses
      it while the bucket or its object store account blocks new public
      policies, which is the default for new buckets and accounts. See the
      I(block_new_public_policies) option of M(everpure.flashblade.purefb_bucket)
      and M(everpure.flashblade.purefb_s3acc).
    type: bool
    default: true
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
- name: Create a bucket access policy rule for bucket bar
  everpure.flashblade.purefb_bucket_access:
    rule: foo
    name: bar
    policy_type: access
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
- name: Create a CORS policy rule for bucket bar
  everpure.flashblade.purefb_bucket_access:
    rule: foo
    name: bar
    policy_type: cors
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
- name: Delete bucket policy rule foo from bucket bar
  everpure.flashblade.purefb_bucket_access:
    rule: foo
    name: bar
    policy_type: access
    state: absent
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
- name: Delete all bucket policy rules from bucket bar
  everpure.flashblade.purefb_bucket_access:
    name: bar
    policy_type: access
    state: absent
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
"""

RETURN = r"""
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        BucketAccessPolicyRulePost,
        BucketAccessPolicyRulePrincipal,
        CrossOriginResourceSharingPolicyRulePost,
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

MIN_API_VERSION = "2.12"
CONTEXT_API_VERSION = "2.17"
# GET /object-store-access-policy-actions lists the rule actions the array
# knows. It grows with Purity//FB releases, so `actions` is validated against
# it rather than against a list frozen in the collection. Which of these a
# bucket access policy rule may hold is decided by the array when the rule
# is posted.
OS_ACTIONS_API_VERSION = "2.2"
# Used only when the array cannot be asked for its own catalogue.
_ACCESS_ACTIONS_FALLBACK = (
    "s3:*",
    "s3:AbortMultipartUpload",
    "s3:BypassGovernanceRetention",
    "s3:CreateBucket",
    "s3:DeleteBucket",
    "s3:DeleteObject",
    "s3:DeleteObjectTagging",
    "s3:DeleteObjectVersion",
    "s3:DeleteObjectVersionTagging",
    "s3:ExtendSafemodeRetentionPeriod",
    "s3:GetBucketAcl",
    "s3:GetBucketCORS",
    "s3:GetBucketLocation",
    "s3:GetBucketPolicy",
    "s3:GetBucketPolicyStatus",
    "s3:GetBucketPublicAccessBlock",
    "s3:GetBucketVersioning",
    "s3:GetLifecycleConfiguration",
    "s3:GetObject",
    "s3:GetObjectAcl",
    "s3:GetObjectLegalHold",
    "s3:GetObjectLockConfiguration",
    "s3:GetObjectRetention",
    "s3:GetObjectTagging",
    "s3:GetObjectVersion",
    "s3:GetObjectVersionTagging",
    "s3:ListAllMyBuckets",
    "s3:ListBucket",
    "s3:ListBucketMultipartUploads",
    "s3:ListBucketVersions",
    "s3:ListMultipartUploadParts",
    "s3:PutBucketVersioning",
    "s3:PutLifecycleConfiguration",
    "s3:PutObject",
    "s3:PutObjectLegalHold",
    "s3:PutObjectLockConfiguration",
    "s3:PutObjectRetention",
    "s3:PutObjectTagging",
    "s3:PutObjectVersionTagging",
    "s3:ResolveSafemodeConflicts",
)


def _context_kwargs(module, api_version):
    """Return context_names kwargs when a fleet context applies, else {}"""
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and module.params["context"]
    ):
        return {"context_names": [module.params["context"]]}
    return {}


def _valid_actions(module, blade, api_version):
    """Return the access policy rule actions this array knows.

    The array's catalogue is authoritative; the built-in list is used only
    when the catalogue cannot be read.
    """
    # MIN_API_VERSION already guarantees the endpoint; the gate is kept for
    # parity with purefb_policy so the helper can be shared later.
    if LooseVersion(OS_ACTIONS_API_VERSION) <= LooseVersion(api_version):
        res = blade.get_object_store_access_policy_actions(
            **_context_kwargs(module, api_version)
        )
        if res.status_code == 200:
            names = [action.name for action in res.items]
            if names:
                return names
            reason = "The array returned an empty list."
        else:
            reason = "Error: {0}".format(get_error_message(res))
        module.warn(
            "Could not read the array's access policy action list, "
            "validating against the collection's built-in list. {0}".format(reason)
        )
    return list(_ACCESS_ACTIONS_FALLBACK)


def _check_actions(module, blade, api_version):
    """Fail, naming every unknown action, unless all requested actions are valid."""
    if not module.params["actions"]:
        return
    valid = _valid_actions(module, blade, api_version)
    unknown = [action for action in module.params["actions"] if action not in valid]
    if unknown:
        module.fail_json(
            msg="Unknown bucket access policy action(s): {0}. "
            "Valid actions: {1}".format(", ".join(unknown), ", ".join(sorted(valid)))
        )


def _access_rule_matches(module, rule):
    """Compare a live bucket access policy rule with the requested rule.

    effect is not compared: the REST API only supports allow, and deny is
    rejected before this point.
    """
    desired = {
        "actions": sorted(module.params["actions"]),
        "resources": sorted(
            module.params["name"] + "/" + resource
            for resource in module.params["resources"]
        ),
        "all_principals": bool(module.params["principals"]),
    }
    current = {
        "actions": sorted(getattr(rule, "actions", None) or []),
        "resources": sorted(getattr(rule, "resources", None) or []),
        "all_principals": bool(
            getattr(getattr(rule, "principals", None), "all", False)
        ),
    }
    return desired == current


def _describe_access_rule(rule):
    """Return the stored content of a bucket access policy rule for messages"""
    return "actions={0}, resources={1}, all_principals={2}".format(
        sorted(getattr(rule, "actions", None) or []),
        sorted(getattr(rule, "resources", None) or []),
        bool(getattr(getattr(rule, "principals", None), "all", False)),
    )


def _describe_cors_rule(rule):
    """Return the stored content of a CORS policy rule for messages"""
    return "methods={0}, origins={1}, headers={2}".format(
        sorted(getattr(rule, "allowed_methods", None) or []),
        sorted(getattr(rule, "allowed_origins", None) or []),
        sorted(getattr(rule, "allowed_headers", None) or []),
    )


def _cors_rule_matches(module, rule):
    """Compare a live CORS policy rule with the requested rule"""
    desired = {
        "methods": sorted(module.params["methods"]),
        "origins": sorted(module.params["origins"]),
        "headers": sorted(module.params["headers"]),
    }
    current = {
        "methods": sorted(getattr(rule, "allowed_methods", None) or []),
        "origins": sorted(getattr(rule, "allowed_origins", None) or []),
        "headers": sorted(getattr(rule, "allowed_headers", None) or []),
    }
    return desired == current


# The two policy types share one lookup, create, replace and delete flow;
# these tables hold what differs between them.
_ACCESS_RULES = {
    "label": "access policy",
    "get_policies": "get_buckets_bucket_access_policies",
    "post_policies": "post_buckets_bucket_access_policies",
    "delete_policies": "delete_buckets_bucket_access_policies",
    "get_rules": "get_buckets_bucket_access_policies_rules",
    "post_rules": "post_buckets_bucket_access_policies_rules",
    "delete_rules": "delete_buckets_bucket_access_policies_rules",
    "matches": _access_rule_matches,
    "describe": _describe_access_rule,
    "supported": "The FlashBlade REST API currently only supports "
    "s3:GetObject on all objects in the bucket for all principals.",
}
_CORS_RULES = {
    "label": "CORS policy",
    "get_policies": "get_buckets_cross_origin_resource_sharing_policies",
    "post_policies": "post_buckets_cross_origin_resource_sharing_policies",
    "delete_policies": "delete_buckets_cross_origin_resource_sharing_policies",
    "get_rules": "get_buckets_cross_origin_resource_sharing_policies_rules",
    "post_rules": "post_buckets_cross_origin_resource_sharing_policies_rules",
    "delete_rules": "delete_buckets_cross_origin_resource_sharing_policies_rules",
    "matches": _cors_rule_matches,
    "describe": _describe_cors_rule,
    "supported": "The FlashBlade REST API currently only supports all "
    "methods, origin '*' and header '*'.",
}
# Policy rule names are 1 to 63 alphanumeric characters. A rule being
# replaced is first posted under its own name with this suffix appended.
_RULE_NAME_MAX = 63
_TEMP_RULE_SUFFIX = "tmp"


def _temp_rule_name(rule_name):
    """Return the temporary name used while a rule is replaced"""
    return rule_name[: _RULE_NAME_MAX - len(_TEMP_RULE_SUFFIX)] + _TEMP_RULE_SUFFIX


def _title(kind):
    """Return the policy kind's label capitalised for the start of a message"""
    return kind["label"][:1].upper() + kind["label"][1:]


def _policy_exists(module, blade, ctx, kind):
    """Return whether the bucket has a policy of this kind; a read error is fatal"""
    bucket = module.params["name"]
    res = getattr(blade, kind["get_policies"])(bucket_names=[bucket], **ctx)
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read the {0} of bucket {1}. Error: {2}".format(
                kind["label"], bucket, get_error_message(res)
            )
        )
    return bool(list(res.items))


def _get_rules(module, blade, ctx, kind):
    """Return the stored rules of the bucket's policy; a read error is fatal

    The rules are listed rather than fetched by name because the array
    answers a GET for a missing rule name with an error that cannot be told
    apart from any other failure.
    """
    bucket = module.params["name"]
    res = getattr(blade, kind["get_rules"])(bucket_names=[bucket], **ctx)
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read the {0} rules of bucket {1}. Error: {2}".format(
                kind["label"], bucket, get_error_message(res)
            )
        )
    return list(res.items)


def _find_rule(rules, name):
    """Return the rule called name from a list of stored rules, or None"""
    for rule in rules:
        if rule.name == name:
            return rule
    return None


def _read_rule(blade, ctx, kind, bucket, name):
    """GET one rule by name after it was posted.

    The POST response only echoes the request body (it returns actions that
    a GET immediately afterwards does not), so a posted rule is always read
    back rather than taken from the POST response.
    """
    return getattr(blade, kind["get_rules"])(bucket_names=[bucket], names=[name], **ctx)


def _post_rule(blade, ctx, kind, bucket, name, body):
    return getattr(blade, kind["post_rules"])(
        bucket_names=[bucket], names=[name], rule=body, **ctx
    )


def _delete_rule(blade, ctx, kind, bucket, name):
    return getattr(blade, kind["delete_rules"])(
        bucket_names=[bucket], names=[name], **ctx
    )


def _remove_temp_rule(blade, ctx, kind, bucket, temp_name):
    """Delete the temporary rule; return a note for the error message if that fails"""
    res = _delete_rule(blade, ctx, kind, bucket, temp_name)
    if res.status_code != 200:
        return " The temporary rule {0} could not be removed. Error: {1}".format(
            temp_name, get_error_message(res)
        )
    return ""


def _replace_rule(module, blade, ctx, kind, body, rules):
    """Replace a rule whose stored content differs from the request.

    The REST API has no PATCH for policy rules, so the rule has to be
    deleted and posted again. The replacement is posted under a temporary
    name first: a rule the array refuses, or stores differently from the
    request, then leaves the existing rule untouched instead of deleting it.
    """
    bucket = module.params["name"]
    rule_name = module.params["rule"]
    temp_name = _temp_rule_name(rule_name)
    label = kind["label"]
    if _find_rule(rules, temp_name) is not None:
        module.fail_json(
            msg="Cannot replace {0} rule {1} in policy {2}: the temporary rule "
            "name {3} is already in use. Remove or rename that rule first.".format(
                label, rule_name, bucket, temp_name
            )
        )
    res = _post_rule(blade, ctx, kind, bucket, temp_name, body)
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to replace {0} rule {1} in policy {2}: the array refused "
            "the new rule and the existing rule was left unchanged. "
            "Error: {3}".format(label, rule_name, bucket, get_error_message(res))
        )
    res = _read_rule(blade, ctx, kind, bucket, temp_name)
    if res.status_code != 200:
        error = get_error_message(res)
        note = _remove_temp_rule(blade, ctx, kind, bucket, temp_name)
        module.fail_json(
            msg="Failed to replace {0} rule {1} in policy {2}: the new rule could "
            "not be read back and the existing rule was left unchanged. "
            "Error: {3}{4}".format(label, rule_name, bucket, error, note)
        )
    stored = list(res.items)[0]
    if not kind["matches"](module, stored):
        note = _remove_temp_rule(blade, ctx, kind, bucket, temp_name)
        module.fail_json(
            msg="{0} rule {1} in policy {2} cannot be changed as requested: the "
            "array stored the new rule as {3}. {4} The existing rule was left "
            "unchanged.{5}".format(
                _title(kind),
                rule_name,
                bucket,
                kind["describe"](stored),
                kind["supported"],
                note,
            )
        )
    res = _delete_rule(blade, ctx, kind, bucket, rule_name)
    if res.status_code != 200:
        error = get_error_message(res)
        note = _remove_temp_rule(blade, ctx, kind, bucket, temp_name)
        module.fail_json(
            msg="Failed to replace {0} rule {1} in policy {2}: the existing rule "
            "could not be deleted. Error: {3}{4}".format(
                label, rule_name, bucket, error, note
            )
        )
    res = _post_rule(blade, ctx, kind, bucket, rule_name, body)
    if res.status_code != 200:
        module.fail_json(
            changed=True,
            msg="Failed to recreate {0} rule {1} in policy {2} after deleting it; "
            "the requested rule is stored under the temporary name {3}. "
            "Error: {4}".format(
                label, rule_name, bucket, temp_name, get_error_message(res)
            ),
        )
    res = _delete_rule(blade, ctx, kind, bucket, temp_name)
    if res.status_code != 200:
        module.fail_json(
            changed=True,
            msg="{0} rule {1} in policy {2} was replaced, but the temporary rule "
            "{3} could not be deleted. Error: {4}".format(
                _title(kind), rule_name, bucket, temp_name, get_error_message(res)
            ),
        )


def _create_rule(module, blade, kind, body):
    """Create a policy rule, replacing one whose content differs.

    The policy itself may be missing (never created, or removed with its
    last rule), in which case it is created before the rule is posted.
    """
    api_version = get_rest_api_version(blade)
    ctx = _context_kwargs(module, api_version)
    bucket = module.params["name"]
    rule_name = module.params["rule"]
    label = kind["label"]
    policy_exists = _policy_exists(module, blade, ctx, kind)
    rules = _get_rules(module, blade, ctx, kind) if policy_exists else []
    current = _find_rule(rules, rule_name)
    if current is not None:
        if kind["matches"](module, current):
            module.exit_json(changed=False)
        if not module.check_mode:
            _replace_rule(module, blade, ctx, kind, body, rules)
        module.exit_json(changed=True)
    if not module.check_mode:
        if not policy_exists:
            res = getattr(blade, kind["post_policies"])(bucket_names=[bucket], **ctx)
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to create the {0} of bucket {1}. Error: {2}".format(
                        label, bucket, get_error_message(res)
                    )
                )
        res = _post_rule(blade, ctx, kind, bucket, rule_name, body)
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to create {0} rule {1} in policy {2}. Error: {3}".format(
                    label, rule_name, bucket, get_error_message(res)
                )
            )
        # The array accepts a rule body it cannot honour and stores what it
        # supports instead (an action list with s3:GetObject and more is kept
        # as s3:GetObject alone). Left alone, every later run would see the
        # stored rule differ from the request and replace it again, so a
        # coerced rule is an error.
        res = _read_rule(blade, ctx, kind, bucket, rule_name)
        if res.status_code != 200:
            module.fail_json(
                changed=True,
                msg="{0} rule {1} in policy {2} was created but could not be read "
                "back. Error: {3}".format(
                    _title(kind), rule_name, bucket, get_error_message(res)
                ),
            )
        stored = list(res.items)[0]
        if not kind["matches"](module, stored):
            module.fail_json(
                changed=True,
                msg="{0} rule {1} in policy {2} was not stored as requested: the "
                "array kept {3}. {4}".format(
                    _title(kind),
                    rule_name,
                    bucket,
                    kind["describe"](stored),
                    kind["supported"],
                ),
            )
    module.exit_json(changed=True)


def _delete_policy(module, blade, kind):
    """Delete a policy rule, or the whole policy when no rule is named"""
    api_version = get_rest_api_version(blade)
    ctx = _context_kwargs(module, api_version)
    bucket = module.params["name"]
    rule_name = module.params["rule"]
    policy_exists = _policy_exists(module, blade, ctx, kind)
    if rule_name:
        rules = _get_rules(module, blade, ctx, kind) if policy_exists else []
        if _find_rule(rules, rule_name) is None:
            module.exit_json(changed=False)
        if not module.check_mode:
            res = _delete_rule(blade, ctx, kind, bucket, rule_name)
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to delete {0} rule {1} for bucket {2}. Error: {3}".format(
                        kind["label"], rule_name, bucket, get_error_message(res)
                    )
                )
    else:
        if not policy_exists:
            module.exit_json(changed=False)
        if not module.check_mode:
            res = getattr(blade, kind["delete_policies"])(bucket_names=[bucket], **ctx)
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to delete {0} for bucket {1}. Error: {2}".format(
                        kind["label"], bucket, get_error_message(res)
                    )
                )
    module.exit_json(changed=True)


def delete_cors_policy(module, blade):
    """Delete cross-origin resource sharing policy or rule"""
    _delete_policy(module, blade, _CORS_RULES)


def delete_access_policy(module, blade):
    """Delete bucket access policy or rule"""
    _delete_policy(module, blade, _ACCESS_RULES)


def create_access_policy(module, blade):
    """Create or update a bucket access policy rule (and the policy if needed)"""
    bucket = module.params["name"]
    body = BucketAccessPolicyRulePost(
        effect=module.params["effect"],
        resources=[bucket + "/" + resource for resource in module.params["resources"]],
        actions=module.params["actions"],
        principals=BucketAccessPolicyRulePrincipal(all=module.params["principals"]),
    )
    _create_rule(module, blade, _ACCESS_RULES, body)


def create_cors_policy(module, blade):
    """Create or update a CORS policy rule (and the policy if needed)"""
    body = CrossOriginResourceSharingPolicyRulePost(
        allowed_methods=module.params["methods"],
        allowed_origins=module.params["origins"],
        allowed_headers=module.params["headers"],
    )
    _create_rule(module, blade, _CORS_RULES, body)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(type="str", default="present", choices=["absent", "present"]),
            context=dict(type="str", default=""),
            policy_type=dict(
                type="str",
                default="access",
                choices=[
                    "access",
                    "cors",
                ],
            ),
            name=dict(type="str", required=True),
            rule=dict(type="str"),
            resources=dict(type="list", elements="str", default=["*"]),
            effect=dict(
                type="str",
                default="allow",
                choices=[
                    "allow",
                    "deny",
                ],
            ),
            methods=dict(
                type="list",
                elements="str",
                default=["GET", "PUT", "HEAD", "POST", "DELETE"],
                choices=[
                    # Only currently allowed option is:
                    # GET, PUT, HEAD, POST, DELETE
                    "GET",
                    "PUT",
                    "HEAD",
                    "POST",
                    "DELETE",
                ],
            ),
            principals=dict(type="bool", default="True"),
            origins=dict(type="list", elements="str", default=["*"]),
            headers=dict(type="list", elements="str", default=["*"]),
            actions=dict(type="list", elements="str", default=["s3:GetObject"]),
        )
    )

    required_if = [["state", "present", ["rule"]]]
    module = AnsibleModule(
        argument_spec,
        required_if=required_if,
        supports_check_mode=True,
    )

    state = module.params["state"]
    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")
    if (
        state == "present"
        and module.params["policy_type"] == "access"
        and module.params["effect"] != "allow"
    ):
        # The REST API documents allow as the only supported effect and the
        # array stores any other value as allow, so refuse rather than
        # silently create a rule that does the opposite of what was asked.
        module.fail_json(
            msg="effect '{0}' is not supported for bucket access policy rules; "
            "the FlashBlade REST API only supports 'allow'.".format(
                module.params["effect"]
            )
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
    if LooseVersion(MIN_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg=(
                "Minimum FlashBlade REST version required: {0}".format(MIN_API_VERSION)
            )
        )
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and module.params["context"]
    ):
        res = blade.get_buckets(
            names=[module.params["name"]],
            destroyed=False,
            context_names=[module.params["context"]],
        )
    else:
        res = blade.get_buckets(names=[module.params["name"]], destroyed=False)
    if res.status_code != 200:
        module.fail_json(
            msg="Bucket {0} does not exist, or is destroyed.".format(
                module.params["name"]
            )
        )
    if state == "present" and module.params["policy_type"] == "access":
        # Ask the array which actions it knows before anything is written.
        _check_actions(module, blade, api_version)
    if module.params["policy_type"] == "access":
        if state == "present":
            create_access_policy(module, blade)
        else:
            delete_access_policy(module, blade)
    else:
        if state == "present":
            create_cors_policy(module, blade)
        else:
            delete_cors_policy(module, blade)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
