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


DOCUMENTATION = """
---
module: purefb_bucket
version_added: "1.0.0"
short_description:  Manage Object Store Buckets on a  Everpure FlashBlade.
description:
    - This module managess object store (s3) buckets on Everpure FlashBlade.
author: Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
      - Bucket Name.
      - A task manages one bucket. A comma-separated list of names is
        refused.
      - A bucket in a realm is named C(realm::bucket) and belongs to an
        account of the same realm, so I(account) carries the same realm
        prefix.
      - The realm is never taken from I(account) or from the identity that
        runs the task. A realm-scoped administrator must use the
        realm-qualified name; a bare name is not placed in, or resolved to,
        the administrator's realm.
    required: true
    type: str
  account:
    description:
      - Object Store Account for Bucket.
      - An account in a realm is named C(realm::account).
      - The task fails, and nothing is changed, when I(name) and I(account)
        are not in the same realm or when the bucket exists and belongs to
        another account.
    required: true
    type: str
  versioning:
    description:
      - State of S3 bucket versioning
      - If not specified, the current versioning state of the bucket is
        left unchanged
      - S3 versioning cannot be removed once enabled, so I(absent) on an
        already versioned bucket suspends versioning rather than removing it
    required: false
    type: str
    choices: [ "enabled", "suspended", "absent" ]
  state:
    description:
      - Create, delete or modifies a bucket.
    required: false
    default: present
    type: str
    choices: [ "present", "absent" ]
  eradicate:
    description:
      - Define whether to eradicate the bucket on delete or leave in trash.
    required: false
    type: bool
    default: false
  mode:
    description:
      - The type of bucket to be created. Also referred to a VSO Mode.
      - I(multi-site-writable) type can only be used after feature is
        enabled by Pure Technical Support
    type: str
    choices: [ "classic", "multi-site-writable" ]
    version_added: '1.10.0'
  quota:
    description:
      - The effective quota limit applied against the size of the bucket.
      - User byte quota in B, K, M, G, T or P units.
      - Range must be between 1 byte and 9.22 exabytes.
      - Setting to 0 will allow the bucket size to be unlimited.
      - If not provided when the bucket is created, the default bucket quota
        of the object store account is used.
    type: str
    version_added: '1.12.0'
  hard_limit:
    description:
     - Whether the I(quota) value is enforced or not.
     - If not provided when the bucket is created, the default bucket hard
       limit setting of the object store account is used.
    type: bool
    version_added: '1.12.0'
  retention_lock:
    description:
     - Set retention lock level for the bucket
     - Once set to I(ratcheted) can only be lowered by Pure Technical Services
    type: str
    choices: [ "ratcheted", "unlocked" ]
    default: unlocked
    version_added: '1.12.0'
  retention_mode:
    description:
     - The retention mode used to apply locks on new objects if none is specified by the S3 client
     - I(safemode) is available if global Per-Bucket Safemode config is enabled
     - Use "" to clear
     - Once set to I(compliance) this can only be changed by contacting Pure Technical Services
    type: str
    choices: [ "compliance", "governance", "safemode", "" ]
    version_added: '1.12.0'
  object_lock_enabled:
    description:
     - If set to true, then S3 APIs relating to object lock may be used
    type: bool
    default: false
    version_added: '1.12.0'
  freeze_locked_objects:
    description:
     - If set to true, a locked object will be read-only and no new versions of
       the object may be created due to modifications
     - After enabling, can be disabled only by contacting Pure Technical Services
     - The array rejects I(freeze_locked_objects=true) together with
       I(versioning=enabled) as an invalid combination
    type: bool
    default: false
    version_added: '1.12.0'
  default_retention:
    description:
     - The retention period, in days, used to apply locks on new objects if
       none is specified by the S3 client
     - Valid values between 1 and 365000, given as a number of days
       (a trailing C(d) is accepted, for example C(7d))
     - Use "" to clear
     - On an existing bucket this is compared with the current value and
       changed when it differs. On a I(ratcheted) bucket it can only be raised.
    type: str
    version_added: '1.12.0'
  block_new_public_policies:
    description:
    - If set to true, adding bucket policies that grant public access to a bucket is not allowed.
    type: bool
    version_added: '1.15.0'
  block_public_access:
    description:
    - If set to true, access to a bucket with a public policy is restricted to only authenticated
      users within the account that bucket belongs to.
    type: bool
    version_added: '1.15.0'
  eradication_mode:
    description:
    - The eradication mode of the bucket.
    - This is the only per-bucket eradication setting the REST API accepts.
    - Switching to I(retention-based) requires object lock on the bucket and is one-way; the array
      refuses to change the mode back to I(permission-based).
    type: str
    choices: [ "permission-based", "retention-based" ]
    version_added: '1.17.0'
  manual_eradication:
    description:
    - Not settable per bucket. A bucket inherits its manual eradication status
      from the array-wide eradication config (REST C(PATCH /arrays)
      I(eradication_config.manual_eradication), CLI
      C(purearray eradication-config setattr)); the REST API rejects the
      field on a bucket and this module fails when it is set.
    - The inherited value is reported by M(everpure.flashblade.purefb_info)
      under I(buckets.<name>.eradication_config).
    type: bool
    version_added: '1.17.0'
  eradication_delay:
    description:
    - Not settable per bucket. A bucket inherits its eradication delay from
      the array-wide eradication config (REST C(PATCH /arrays)
      I(eradication_config.eradication_delay), CLI
      C(purearray eradication-config setattr)); the REST API rejects the
      field on a bucket and this module fails when it is set.
    - The inherited value is reported by M(everpure.flashblade.purefb_info)
      under I(buckets.<name>.eradication_config).
    type: int
    version_added: '1.17.0'
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

EXAMPLES = """
- name: Create new bucket named foo in account bar
  everpure.flashblade.purefb_bucket:
    name: foo
    quota: 10G
    hard_limit: false
    account: bar
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create new bucket named foo in account bar of realm tenant1
  everpure.flashblade.purefb_bucket:
    name: tenant1::foo
    account: tenant1::bar
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Update bucket foo in account bar with new quota
  everpure.flashblade.purefb_bucket:
    name: foo
    quota: 500B
    hard_limit: true
    account: bar
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Remove quota limits from bucket named foo in account bar
  everpure.flashblade.purefb_bucket:
    name: foo
    quota: 0
    account: bar
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete bucket named foo in account bar
  everpure.flashblade.purefb_bucket:
    name: foo
    account: bar
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Change bucket versioning state
  everpure.flashblade.purefb_bucket:
    name: foo
    account: bar
    versioning: enabled
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Recover deleted bucket named foo in account bar
  everpure.flashblade.purefb_bucket:
    name: foo
    account: bar
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Eradicate bucket named foo in account bar
  everpure.flashblade.purefb_bucket:
    name: foo
    account: bar
    state: absent
    eradicate: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = """
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        BucketPost,
        ReferenceWritable,
        BucketPatch,
        BucketEradicationConfig,
        ObjectLockConfigRequestBody,
        PublicAccessConfig,
        BucketAccessPolicyPost,
        BucketAccessPolicyRulePost,
        BucketAccessPolicyRulePrincipal,
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
    human_to_bytes,
)

MS_PER_DAY = 86400000
VSO_VERSION = "2.5"
QUOTA_VERSION = "2.8"
MODE_VERSION = "2.12"
WORM_VERSION = "2.13"
CONTEXT_API_VERSION = "2.17"


def _context_kwargs(module, api_version):
    """Return context_names kwargs when a fleet context applies, else {}"""
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and module.params["context"]
    ):
        return {"context_names": [module.params["context"]]}
    return {}


def _eradication_mode_patch(mode):
    """Build the PATCH /buckets body that sets eradication_mode.

    eradication_mode is the only writable field of a bucket's
    eradication_config. eradication_delay and manual_eradication are
    read-only on a bucket (the array answers "Invalid body parameter" when
    they are sent) and are inherited from the array-wide eradication config.
    """
    return BucketPatch(
        eradication_config=BucketEradicationConfig(eradication_mode=mode)
    )


def _retention_to_ms(module, value):
    """Convert default_retention (days, optional trailing d; "" clears) to ms"""
    if value is None:
        return 0
    text = str(value).strip().lower()
    if text == "":
        return 0
    if text.endswith("d"):
        text = text[:-1]
    try:
        days = int(text)
    except ValueError:
        module.fail_json(
            msg='default_retention must be a number of days (1-365000) or "" '
            "to clear, got {0}".format(value)
        )
    if not 1 <= days <= 365000:
        module.fail_json(msg="default_retention must be between 1 and 365000 days")
    return days * MS_PER_DAY


def _object_lock_changes(module, bucket_detail):
    """Return the object_lock_config fields that differ from the request.

    Only the requested fields that differ are returned, so the PATCH is
    minimal and a repeat run finds nothing to change. Settings the array
    does not allow to be lowered are reported with a warning instead.
    """
    current = getattr(bucket_detail, "object_lock_config", None)
    cur_enabled = bool(getattr(current, "enabled", False))
    cur_freeze = bool(getattr(current, "freeze_locked_objects", False))
    cur_mode = getattr(current, "default_retention_mode", None) or ""
    cur_retention = getattr(current, "default_retention", None) or 0
    ratcheted = getattr(bucket_detail, "retention_lock", None) == "ratcheted"
    changes = {}
    if module.params["object_lock_enabled"] and not cur_enabled:
        changes["enabled"] = True
    elif not module.params["object_lock_enabled"] and cur_enabled:
        module.warn("Object lock cannot be disabled.")
    if module.params["freeze_locked_objects"] and not cur_freeze:
        changes["freeze_locked_objects"] = True
    elif not module.params["freeze_locked_objects"] and cur_freeze:
        module.warn("Freeze locked objects cannot be disabled.")
    if (
        module.params["retention_mode"] is not None
        and module.params["retention_mode"] != cur_mode
    ):
        if ratcheted and cur_mode == "compliance":
            module.warn(
                "Changing retention_mode can only be performed by Pure Technical Support."
            )
        else:
            changes["default_retention_mode"] = module.params["retention_mode"]
    if module.params["default_retention"] is not None:
        new_retention = _retention_to_ms(module, module.params["default_retention"])
        if new_retention != cur_retention:
            if ratcheted and new_retention < cur_retention:
                module.warn(
                    "Default retention can only be reduced by Pure Technical Support."
                )
            else:
                changes["default_retention"] = (
                    str(new_retention) if new_retention else ""
                )
    return changes


def _realm_of(name):
    """Return the realm of a realm::name name, empty for an array-level name"""
    # the array ignores blanks around a name
    return name.rpartition("::")[0].strip()


def _check_one_name(module):
    """Fail when name is a list of bucket names.

    The array reads a comma as the separator of a list of names. A read
    answers with every bucket of the list, but a bucket is changed,
    destroyed, recovered and eradicated one name at a time, so such a task
    can only fail and is refused before the array is asked.
    """
    if "," in module.params["name"]:
        module.fail_json(
            msg="Bucket {0} is a list of names: a comma separates names, and a "
            "task manages one bucket.".format(module.params["name"])
        )


def _check_same_realm(module):
    """Fail unless the bucket and its account are named in the same realm.

    A bucket belongs to an account of its own realm, so both names carry the
    same realm prefix or neither does. The array refuses to create any other
    pair, and a bucket found under such a name is a namesake that cannot
    belong to the account, so the pair is refused before anything is read or
    written.
    """
    name = module.params["name"]
    account = module.params["account"]
    realm = _realm_of(account)
    # the array matches names without regard to case
    if _realm_of(name).lower() == realm.lower():
        return
    if realm:
        hint = "A bucket of this account is named {0}::<bucket>".format(realm)
    else:
        hint = (
            "A bucket in realm {0} needs an account of that realm, named "
            "{0}::<account>".format(_realm_of(name))
        )
    module.fail_json(
        msg="Bucket {0} cannot belong to Object Store Account {1}: a bucket "
        "and its account must be in the same realm. {2}.".format(name, account, hint)
    )


def _same_account(stored, asked):
    """Return True when two names of accounts of one realm are one account.

    The array matches names without regard to case or to blanks around them.
    Both names belong to the same realm, so the realm prefix is compared
    only when both carry one: a bare name next to a realm-qualified one is
    the account of that name in the realm.
    """
    stored_realm, asked_realm = _realm_of(stored).lower(), _realm_of(asked).lower()
    if stored_realm and asked_realm and stored_realm != asked_realm:
        return False
    return (
        stored.rpartition("::")[2].strip().lower()
        == asked.rpartition("::")[2].strip().lower()
    )


def _check_account(module, bucket, account):
    """Fail when the bucket that was found belongs to another account.

    A bucket is looked up by its name alone, which finds it whichever account
    the task names. A bucket of another account is not the bucket the task
    describes and is never modified, destroyed, recovered or eradicated.

    The name of the account decides. The bucket and the account were read
    under names of one realm, and an account name is unique within a realm,
    so the bucket belongs to the account of the task when the account name it
    carries is the name of that account, as the task spells it or as the
    array returned it. The id the bucket carries for its account is not
    compared then, because it can differ from the id of the account of that
    name. The ids decide only for a bucket that carries no account name.
    """
    owner = getattr(bucket, "account", None)
    owner_id = getattr(owner, "id", None)
    owner_name = getattr(owner, "name", None)
    account_id = getattr(account, "id", None)
    if owner_name:
        asked = [module.params["account"], getattr(account, "name", None)]
        if not any(_same_account(owner_name, name) for name in asked if name):
            module.fail_json(
                msg="Bucket {0} belongs to Object Store Account {1}, not {2}.".format(
                    module.params["name"], owner_name, module.params["account"]
                )
            )
    elif owner_id and account_id and owner_id != account_id:
        module.fail_json(
            msg="Bucket {0} belongs to the Object Store Account with id {1}, "
            "not to {2}, whose id is {3}.".format(
                module.params["name"], owner_id, module.params["account"], account_id
            )
        )


def _get_one(module, res, what, name):
    """Return the object a read by name answered with, or None when absent.

    Only the array's "does not exist" means absent. Any other refusal fails
    the task with the array's message, so it is never mistaken for a missing
    object. A name the array reads as a list of names answers with several
    objects; the task describes one, so it fails rather than act on the
    first of them.
    """
    if res.status_code == 200:
        items = list(res.items)
        if len(items) > 1:
            module.fail_json(
                msg="{0} {1} matches {2} objects. The name of one {0} is "
                "needed.".format(what, name, len(items))
            )
        return items[0] if items else None
    error = get_error_message(res)
    if "does not exist" not in str(error).lower():
        module.fail_json(
            msg="Failed to get {0} {1}. Error: {2}".format(what, name, error)
        )
    return None


def get_s3acc(module, blade):
    """Return Object Store Account or None"""
    res = blade.get_object_store_accounts(
        names=[module.params["account"]],
        **_context_kwargs(module, get_rest_api_version(blade))
    )
    return _get_one(module, res, "Object Store Account", module.params["account"])


def get_bucket(module, blade):
    """Return Bucket or None"""
    res = blade.get_buckets(
        names=[module.params["name"]],
        **_context_kwargs(module, get_rest_api_version(blade))
    )
    return _get_one(module, res, "Object Store Bucket", module.params["name"])


def create_bucket(module, blade):
    """Create bucket"""
    changed = True
    api_version = get_rest_api_version(blade)
    if not module.check_mode:
        if LooseVersion(VSO_VERSION) <= LooseVersion(api_version):
            if LooseVersion(QUOTA_VERSION) <= LooseVersion(api_version):
                # Only the limits the task asks for are sent. The array gives
                # a bucket created without them the bucket defaults of its
                # object store account, not the account's own quota.
                limits = {}
                if module.params["hard_limit"] is not None:
                    limits["hard_limit_enabled"] = module.params["hard_limit"]
                if module.params["quota"] == "0":
                    # 0 asks for an unlimited bucket, as it does on an update
                    limits["quota_limit"] = ""
                    limits["hard_limit_enabled"] = False
                elif module.params["quota"]:
                    limits["quota_limit"] = str(human_to_bytes(module.params["quota"]))
                if not module.params["retention_mode"]:
                    module.params["retention_mode"] = ""
                retention_ms = _retention_to_ms(
                    module, module.params["default_retention"]
                )
                module.params["default_retention"] = (
                    str(retention_ms) if retention_ms else ""
                )
                bucket = BucketPost(
                    account=ReferenceWritable(name=module.params["account"]),
                    bucket_type=module.params["mode"],
                    **limits
                )
            else:
                bucket = BucketPost(
                    account=ReferenceWritable(name=module.params["account"]),
                    bucket_type=module.params["mode"],
                )
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.post_buckets(
                    names=[module.params["name"]],
                    bucket=bucket,
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.post_buckets(names=[module.params["name"]], bucket=bucket)
            if res.status_code != 200:
                module.fail_json(
                    msg="Object Store Bucket {0} creation failed. Error: {1}".format(
                        module.params["name"],
                        get_error_message(res),
                    )
                )
            if module.params["versioning"] not in [None, "absent"]:
                if LooseVersion(QUOTA_VERSION) <= LooseVersion(api_version):
                    bucket = BucketPatch(
                        retention_lock=module.params["retention_lock"],
                        object_lock_config=ObjectLockConfigRequestBody(
                            default_retention_mode=module.params["retention_mode"],
                            enabled=module.params["object_lock_enabled"],
                            freeze_locked_objects=module.params[
                                "freeze_locked_objects"
                            ],
                            default_retention=module.params["default_retention"],
                        ),
                        versioning=module.params["versioning"],
                    )
                else:
                    bucket = BucketPatch(
                        retention_lock=module.params["retention_lock"],
                        versioning=module.params["versioning"],
                    )
            else:
                if LooseVersion(QUOTA_VERSION) <= LooseVersion(api_version):
                    bucket = BucketPatch(
                        retention_lock=module.params["retention_lock"],
                        object_lock_config=ObjectLockConfigRequestBody(
                            default_retention_mode=module.params["retention_mode"],
                            enabled=module.params["object_lock_enabled"],
                            freeze_locked_objects=module.params[
                                "freeze_locked_objects"
                            ],
                            default_retention=module.params["default_retention"],
                        ),
                        versioning=None,
                    )
                else:
                    bucket = BucketPatch(
                        retention_lock=module.params["retention_lock"],
                        versioning=None,
                    )

            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.patch_buckets(
                    names=[module.params["name"]],
                    bucket=bucket,
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.patch_buckets(names=[module.params["name"]], bucket=bucket)
            if res.status_code != 200:
                module.fail_json(
                    msg="Object Store Bucket {0} creation update failed. Error: {1}".format(
                        module.params["name"],
                        get_error_message(res),
                    )
                )
        else:
            bucket = BucketPost(
                account=ReferenceWritable(name=module.params["account"]),
            )
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.post_buckets(
                    names=[module.params["name"]],
                    bucket=bucket,
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.post_buckets(names=[module.params["name"]], bucket=bucket)
            if res.status_code != 200:
                module.fail_json(
                    msg="Object Store Bucket {0} creation failed. Error: {1}".format(
                        module.params["name"],
                        get_error_message(res),
                    )
                )
            if module.params["versioning"] not in [None, "absent"]:
                if (
                    LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                    and module.params["context"]
                ):
                    res = blade.patch_buckets(
                        names=[module.params["name"]],
                        bucket=BucketPatch(versioning=module.params["versioning"]),
                        context_names=[module.params["context"]],
                    )
                else:
                    res = blade.patch_buckets(
                        names=[module.params["name"]],
                        bucket=BucketPatch(versioning=module.params["versioning"]),
                    )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Object Store Bucket {0} created but versioning state failed. Error: {1}".format(
                            module.params["name"], get_error_message(res)
                        )
                    )
        if LooseVersion(MODE_VERSION) <= LooseVersion(api_version):
            ctx = _context_kwargs(module, api_version)
            block_policies = module.params["block_new_public_policies"]
            block_access = module.params["block_public_access"]
            if block_policies is not None or block_access is not None:
                # Only send what was asked for. Anything left unset keeps the
                # array default (public access blocked), so a bucket created
                # without these options is never made public here.
                pac = BucketPatch(
                    public_access_config=PublicAccessConfig(
                        block_new_public_policies=block_policies,
                        block_public_access=block_access,
                    )
                )
                res = blade.patch_buckets(
                    bucket=pac, names=[module.params["name"]], **ctx
                )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Failed to set Public Access config for bucket {0}. "
                        "Error: {1}".format(
                            module.params["name"], get_error_message(res)
                        )
                    )
            if block_policies is False and block_access is False:
                # Both blocks were explicitly lifted: the caller wants a public
                # bucket, which also needs a bucket access policy with a rule
                # granting s3:GetObject to all principals.
                policy = BucketAccessPolicyPost(
                    name=module.params["name"],
                )
                res = blade.post_buckets_bucket_access_policies(
                    bucket_names=[module.params["name"]], policy=policy, **ctx
                )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Failed to set bucket access policy for bucket {0}. "
                        "Error: {1}".format(
                            module.params["name"], get_error_message(res)
                        )
                    )
                rule = BucketAccessPolicyRulePost(
                    actions=["s3:GetObject"],
                    effect="allow",
                    principals=BucketAccessPolicyRulePrincipal(all=True),
                    resources=[module.params["name"] + "/*"],
                )
                res = blade.post_buckets_bucket_access_policies_rules(
                    bucket_names=[module.params["name"]],
                    rule=rule,
                    names=["default"],
                    **ctx
                )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Failed to set bucket access policy rule for bucket {0}. "
                        "Error: {1}".format(
                            module.params["name"], get_error_message(res)
                        )
                    )
        if (
            LooseVersion(WORM_VERSION) <= LooseVersion(api_version)
            and module.params["eradication_mode"]
        ):
            res = blade.patch_buckets(
                bucket=_eradication_mode_patch(module.params["eradication_mode"]),
                names=[module.params["name"]],
                **_context_kwargs(module, api_version)
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to set Bucket Eradication config for bucket {0}. "
                    "Error: {1}".format(module.params["name"], get_error_message(res))
                )
    module.exit_json(changed=changed)


def delete_bucket(module, blade):
    """Delete Bucket"""
    changed = True
    api_version = get_rest_api_version(blade)
    if not module.check_mode:
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            res = blade.patch_buckets(
                names=[module.params["name"]],
                bucket=BucketPatch(destroyed=True),
                context_names=[module.params["context"]],
            )
        else:
            res = blade.patch_buckets(
                names=[module.params["name"]], bucket=BucketPatch(destroyed=True)
            )
        if res.status_code != 200:
            module.fail_json(
                msg="Deletion for bucket {0} failed. "
                "Error: {1}".format(module.params["name"], get_error_message(res))
            )
        if module.params["eradicate"]:
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.delete_buckets(
                    names=[module.params["name"]],
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.delete_buckets(names=[module.params["name"]])
            if res.status_code != 200:
                module.fail_json(
                    msg="Eradication for bucket {0} failed. "
                    "Error: {1}".format(module.params["name"], get_error_message(res))
                )
    module.exit_json(changed=changed)


def recover_bucket(module, blade):
    """Recover Bucket"""
    changed = True
    api_version = get_rest_api_version(blade)
    if not module.check_mode:
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            res = blade.patch_buckets(
                names=[module.params["name"]],
                bucket=BucketPatch(destroyed=False),
                context_names=[module.params["context"]],
            )
        else:
            res = blade.patch_buckets(
                names=[module.params["name"]], bucket=BucketPatch(destroyed=False)
            )
        if res.status_code != 200:
            module.fail_json(
                msg="Object Store Bucket {0} Recovery failed. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def update_bucket(module, blade, bucket):
    """Update Bucket"""
    changed = False
    change_pac = False
    change_worm = False
    change_quota = False
    change_lock = False
    api_version = get_rest_api_version(blade)
    ctx = _context_kwargs(module, api_version)
    bucket_detail = bucket
    if LooseVersion(VSO_VERSION) <= LooseVersion(api_version):
        if module.params["mode"] and bucket_detail.bucket_type != module.params["mode"]:
            module.warn("Changing bucket type is not permitted.")

    if module.params["versioning"] is not None and bucket.versioning != "none":
        # "absent" is the module's sentinel, not a valid API value, and versioning
        # can never return to "none" once enabled, so it always maps to "suspended"
        # whether the bucket is currently "enabled" or already "suspended".
        if module.params["versioning"] == "absent":
            versioning = "suspended"
        else:
            versioning = module.params["versioning"]
        if bucket.versioning != versioning:
            changed = True
            if not module.check_mode:
                if (
                    LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                    and module.params["context"]
                ):
                    res = blade.patch_buckets(
                        names=[module.params["name"]],
                        bucket=BucketPatch(versioning=versioning),
                        context_names=[module.params["context"]],
                    )
                else:
                    res = blade.patch_buckets(
                        names=[module.params["name"]],
                        bucket=BucketPatch(versioning=versioning),
                    )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Object Store Bucket {0} versioning change failed. Error: {1}".format(
                            module.params["name"], get_error_message(res)
                        )
                    )
    elif module.params["versioning"] not in [None, "absent"]:
        changed = True
        if not module.check_mode:
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.patch_buckets(
                    names=[module.params["name"]],
                    bucket=BucketPatch(versioning=module.params["versioning"]),
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.patch_buckets(
                    names=[module.params["name"]],
                    bucket=BucketPatch(versioning=module.params["versioning"]),
                )
            if res.status_code != 200:
                module.fail_json(
                    msg="Object Store Bucket {0} versioning change failed. Error: {1}".format(
                        module.params["name"], get_error_message(res)
                    )
                )
    if LooseVersion(QUOTA_VERSION) <= LooseVersion(api_version):
        # Object lock configuration (after versioning, which object lock needs)
        lock_changes = _object_lock_changes(module, bucket_detail)
        if lock_changes:
            change_lock = True
            if not module.check_mode:
                res = blade.patch_buckets(
                    names=[module.params["name"]],
                    bucket=BucketPatch(
                        object_lock_config=ObjectLockConfigRequestBody(**lock_changes)
                    ),
                    **ctx
                )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Failed to update object lock config for bucket {0}. "
                        "Error: {1}".format(
                            module.params["name"], get_error_message(res)
                        )
                    )
        if (
            module.params["retention_lock"] == "ratcheted"
            and bucket_detail.retention_lock != "ratcheted"
        ):
            # retention_lock can only ever be raised; unlocked (the option
            # default) is left alone so an unrelated update never warns.
            change_lock = True
            if not module.check_mode:
                res = blade.patch_buckets(
                    names=[module.params["name"]],
                    bucket=BucketPatch(retention_lock="ratcheted"),
                    **ctx
                )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Failed to set retention_lock for bucket {0}. "
                        "Error: {1}".format(
                            module.params["name"], get_error_message(res)
                        )
                    )
        current_quota = {
            "quota": bucket_detail.quota_limit,
            "hard": bucket_detail.hard_limit_enabled,
        }
        new_quota = {
            "quota": bucket_detail.quota_limit,
            "hard": bucket_detail.hard_limit_enabled,
        }
        if module.params["quota"]:
            quota = human_to_bytes(module.params["quota"])
            if module.params["quota"] == "0":
                quota = None
                module.params["hard_limit"] = False
            if quota != current_quota["quota"]:
                change_quota = True
                new_quota["quota"] = human_to_bytes(module.params["quota"])
        if (
            module.params["hard_limit"] is not None
            and module.params["hard_limit"] != current_quota["hard"]
        ):
            change_quota = True
            new_quota["hard"] = module.params["hard_limit"]
        if current_quota != new_quota and not module.check_mode:
            if new_quota["quota"] is None or new_quota["quota"] == 0:
                bucket = BucketPatch(
                    quota_limit="",
                    hard_limit_enabled=False,
                )
            else:
                bucket = BucketPatch(
                    quota_limit=str(new_quota["quota"]),
                    hard_limit_enabled=new_quota["hard"],
                )
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.patch_buckets(
                    bucket=bucket,
                    names=[module.params["name"]],
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.patch_buckets(bucket=bucket, names=[module.params["name"]])
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to update quota settings correctly for bucket {0}. "
                    "Error: {1}".format(module.params["name"], get_error_message(res))
                )
    if LooseVersion(MODE_VERSION) <= LooseVersion(api_version):
        current_pac = {
            "block_new_public_policies": bucket_detail.public_access_config.block_new_public_policies,
            "block_public_access": bucket_detail.public_access_config.block_public_access,
        }
        if module.params["block_new_public_policies"] is None:
            new_public_policies = current_pac["block_new_public_policies"]
        else:
            new_public_policies = module.params["block_new_public_policies"]
        if module.params["block_public_access"] is None:
            new_public_access = current_pac["block_public_access"]
        else:
            new_public_access = module.params["block_public_access"]
        new_pac = {
            "block_new_public_policies": new_public_policies,
            "block_public_access": new_public_access,
        }
        if current_pac != new_pac:
            change_pac = True
            pac = BucketPatch(
                public_access_config=PublicAccessConfig(
                    block_new_public_policies=new_pac["block_new_public_policies"],
                    block_public_access=new_pac["block_public_access"],
                )
            )
        if change_pac and not module.check_mode:
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.patch_buckets(
                    bucket=pac,
                    names=[module.params["name"]],
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.patch_buckets(bucket=pac, names=[module.params["name"]])
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to update Public Access config correctly for bucket {0}. "
                    "Error: {1}".format(module.params["name"], get_error_message(res))
                )
    if LooseVersion(WORM_VERSION) <= LooseVersion(api_version):
        # eradication_mode is the only per-bucket eradication setting; the
        # delay and manual status are array-wide and rejected in main().
        current_mode = getattr(
            getattr(bucket_detail, "eradication_config", None),
            "eradication_mode",
            None,
        )
        new_mode = module.params["eradication_mode"]
        if new_mode and new_mode != current_mode:
            change_worm = True
            if not module.check_mode:
                res = blade.patch_buckets(
                    bucket=_eradication_mode_patch(new_mode),
                    names=[module.params["name"]],
                    **ctx
                )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Failed to update Eradication config correctly for "
                        "bucket {0}. Error: {1}".format(
                            module.params["name"], get_error_message(res)
                        )
                    )
    module.exit_json(
        changed=(changed or change_pac or change_worm or change_quota or change_lock)
    )


def eradicate_bucket(module, blade):
    """Eradicate Bucket"""
    changed = True
    api_version = get_rest_api_version(blade)
    if not module.check_mode:
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            res = blade.delete_buckets(
                names=[module.params["name"]], context_names=[module.params["context"]]
            )
        else:
            res = blade.delete_buckets(names=[module.params["name"]])
        if res.status_code != 200:
            module.fail_json(
                msg="Object Store Bucket {0} eradication failed. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(required=True),
            account=dict(required=True),
            eradicate=dict(default="false", type="bool"),
            mode=dict(
                type="str",
                choices=["classic", "multi-site-writable"],
            ),
            retention_mode=dict(
                type="str", choices=["compliance", "governance", "safemode", ""]
            ),
            default_retention=dict(type="str"),
            retention_lock=dict(
                type="str", choices=["ratcheted", "unlocked"], default="unlocked"
            ),
            hard_limit=dict(type="bool"),
            block_new_public_policies=dict(type="bool"),
            block_public_access=dict(type="bool"),
            object_lock_enabled=dict(type="bool", default=False),
            freeze_locked_objects=dict(type="bool", default=False),
            quota=dict(type="str"),
            versioning=dict(type="str", choices=["enabled", "suspended", "absent"]),
            state=dict(default="present", choices=["present", "absent"]),
            eradication_delay=dict(type="int"),
            eradication_mode=dict(
                type="str", choices=["permission-based", "retention-based"]
            ),
            manual_eradication=dict(type="bool"),
            context=dict(type="str", default=""),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required")

    if (
        module.params["eradication_delay"] is not None
        or module.params["manual_eradication"] is not None
    ):
        # Both fields are read-only on a bucket at every REST API version
        # (py-pure-client strips them from BucketEradicationConfig requests
        # and the array answers "Invalid body parameter" when they are sent).
        # A bucket inherits them from the array-wide eradication config.
        module.fail_json(
            msg="eradication_delay and manual_eradication are read-only on a "
            "bucket: Purity//FB inherits them from the array-wide eradication "
            "config (REST PATCH /arrays eradication_config, CLI purearray "
            "eradication-config setattr). Only eradication_mode can be set "
            "per bucket."
        )

    # Decided from the names alone, before the array is asked or changed
    _check_one_name(module)
    _check_same_realm(module)

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

    # From REST 2.12 classic is no longer the default mode
    if LooseVersion(MODE_VERSION) <= LooseVersion(api_version):
        if not module.params["mode"]:
            module.params["mode"] = "multi-site-writable"
    elif not module.params["mode"]:
        module.params["mode"] = "classic"
    account = get_s3acc(module, blade)
    if not account:
        module.fail_json(
            msg="Object Store Account {0} does not exist.".format(
                module.params["account"]
            )
        )
    bucket = get_bucket(module, blade)
    if bucket:
        _check_account(module, bucket, account)
    if (
        module.params["quota"]
        and human_to_bytes(module.params["quota"]) > 9223372036854775807
    ):
        module.fail_json(msg="Quota must not exceed 9.22 exabytes")
    if module.params["eradicate"] and state == "present":
        module.warn("Eradicate flag ignored without state=absent")

    if state == "present" and not bucket:
        create_bucket(module, blade)
    elif state == "present" and bucket and bucket.destroyed:
        recover_bucket(module, blade)
    elif state == "absent" and bucket and not bucket.destroyed:
        delete_bucket(module, blade)
    elif state == "present" and bucket:
        update_bucket(module, blade, bucket)
    elif (
        state == "absent" and bucket and bucket.destroyed and module.params["eradicate"]
    ):
        eradicate_bucket(module, blade)
    elif state == "absent" and not bucket:
        module.exit_json(changed=False)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
