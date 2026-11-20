#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2018, Simon Dodsley (simon@everpuredata.com)
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
module: purefb_s3acc
version_added: '1.0.0'
short_description: Create or delete FlashBlade Object Store accounts
description:
- Create or delete object store accounts on a Pure Stoage FlashBlade.
- An account in a realm is managed by giving I(name) as C(realm::account).
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  state:
    description:
    - Create or delete object store account
    - An account that still has users or buckets is not deleted and the task
      fails, in check mode too. A destroyed bucket counts until it is
      eradicated.
    default: present
    choices: [ absent, present ]
    type: str
  name:
    description:
    - The name of object store account
    - An account in a realm is named C(realm::account).
    - A realm-scoped administrator must use the realm-qualified name; a bare
      name is not placed in, or resolved to, the administrator's realm.
    - A task manages one account. Blanks around the name are ignored and a
      comma-separated list of names is refused.
    type: str
    required: true
  quota:
    description:
    - The effective quota limit to be applied against the size of the account in bytes.
    - Values can be entered as K, M, T or P
    - If set to '' (empty string), the account is unlimited in size.
    - The array accepts 1 byte to 9223372036854775807 bytes. A value outside
      of that range, or one that is not a size, fails before the account is
      created or changed.
    version_added: 1.11.0
    type: str
  hard_limit:
    description:
    - If set to true, the account size, as defined by I(quota_limit), is used as a hard limit quota.
      The array refuses a hard limit while the account is unlimited in size.
    - If set to false, a hard limit quota will not be applied to the account, but soft quota alerts
      will still be sent if the account has a value set for I(quota_limit).
    version_added: 1.11.0
    type: bool
  default_quota:
    description:
    - The value of this field will be used to configure the I(quota_limit) field of newly created buckets
      associated with this object store account, if the bucket creation does not specify its own value.
    - Values can be entered as K, M, T or P
    - If set to '' (empty string), the bucket default is unlimited in size.
    - The same range as for I(quota) applies.
    version_added: 1.11.0
    type: str
  default_hard_limit:
    description:
    - The value of this field will be used to configure the I(hard_limit) field of newly created buckets
      associated with this object store account, if the bucket creation does not specify its own value.
      The array refuses a default hard limit while the bucket default is unlimited in size.
    version_added: 1.11.0
    type: bool
  block_new_public_policies:
    description:
    - If set to true, adding bucket policies that grant public access to a bucket is not allowed.
    type: bool
    version_added: 1.15.0
  block_public_access:
    description:
    - If set to true, access to a bucket with a public policy is restricted to only authenticated
      users within the account that bucket belongs to.
    type: bool
    version_added: 1.15.0
  account_exports:
    description:
    - Servers the account is exported on when it is created. Each element is a
      dictionary with a C(server) key naming the server. Exports created this way
      use the array default S3 export policy.
    - If omitted, the array creates its default export on the default object store
      server with the default S3 export policy. That server is C(_array_server)
      for an account outside a realm and the default object store server of the
      realm (I(default_object_server) of M(everpure.flashblade.purefb_realm)) for
      an account in a realm. An account in a realm that has no default object
      store server is created without any export.
    - An account is only exported on servers of its own realm. For an account
      named C(realm::account) a server given without a realm is taken as
      C(realm::server). A server of another realm, C(_array_server) for an
      account in a realm, or a server in a realm for an account outside of any
      realm is refused before the account is created.
    - Set to C([]) (an empty list) to create the account without any export. The
      buckets of such an account are not reachable over S3 until an export is added
      with M(everpure.flashblade.purefb_s3acc_export).
    - Only applied when the account is created. On an existing account the current
      exports are compared with this list and a warning is issued when they differ;
      the account is not changed. Add, change or remove the exports of an existing
      account with M(everpure.flashblade.purefb_s3acc_export).
    - Requires FlashBlade REST API version 2.20 or later (Purity//FB 4.6.3+).
    type: list
    elements: dict
    suboptions:
      server:
        description:
        - Name of the server the account is exported on.
        - A server in a realm is named C(realm::server).
        type: str
        required: true
    version_added: '1.30.0'
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
- name: Create object store account foo (with no quotas)
  everpure.flashblade.purefb_s3acc:
    name: foo
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592

- name: Create object store account foo (with quotas)
  everpure.flashblade.purefb_s3acc:
    name: foo
    quota: 20480000
    hard_limit: true
    default_quota: 1024000
    default_hard_limit: false
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592

- name: Create object store account foo without any export
  everpure.flashblade.purefb_s3acc:
    name: foo
    account_exports: []
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592

- name: Create object store account foo exported on server bar
  everpure.flashblade.purefb_s3acc:
    name: foo
    account_exports:
      - server: bar
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592

- name: Create object store account foo in realm myrealm, exported on server bar of that realm
  everpure.flashblade.purefb_s3acc:
    name: myrealm::foo
    account_exports:
      - server: bar
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592

- name: Delete object store account foo
  everpure.flashblade.purefb_s3acc:
    name: foo
    state: absent
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592
"""

RETURN = r"""
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        ObjectStoreAccountPatch,
        ObjectStoreAccountPost,
        BucketDefaults,
        PublicAccessConfig,
        Reference,
        ServerForAccountExport,
    )
except ImportError:
    HAS_PYPURECLIENT = False

from ansible.module_utils.basic import AnsibleModule, human_to_bytes
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

PUBLIC_API_VERSION = "2.12"
CONTEXT_API_VERSION = "2.17"
REALM_API_VERSION = "2.19"
ACCOUNT_EXPORTS_API_VERSION = "2.20"
REALM_CONTEXT_API_VERSION = "2.24"
ARRAY_DEFAULT_SERVER = "_array_server"
# The array keeps a quota as a signed 64-bit number of bytes.
MAX_QUOTA = 9223372036854775807


def _realm_of(name):
    """Return the realm of a realm::name name, empty for an array-level name."""
    return name.rpartition("::")[0]


def _one_name(module, option, value):
    """Return a name without the blanks around it; fail on a list or no name.

    Where the array looks an object up by name it ignores blanks around the
    name and reads a comma as a separator of names. The filters that find
    the users, buckets and exports of an account take their text as it is.
    A name the array reads differently from those filters would get past
    the checks made with them, so the blanks are dropped here and an empty
    name or a list of names is refused before anything is read.
    """
    name = value.strip()
    if not name:
        module.fail_json(msg="{0} must not be empty.".format(option))
    if "," in name:
        module.fail_json(
            msg="{0} {1} names more than one object: the array reads a comma as "
            "a separator of names. Give one name.".format(option, name)
        )
    return name


def _context_kwargs(module):
    """Build context_names kwargs only when a context is supplied."""
    if module.params["context"]:
        return {"context_names": [module.params["context"]]}
    return {}


def _api_context_kwargs(module, api_version, minimum=CONTEXT_API_VERSION):
    """Return the context kwargs for a call that takes them from REST minimum."""
    if LooseVersion(minimum) <= LooseVersion(api_version):
        return _context_kwargs(module)
    return {}


def _checked_items(module, res, what):
    """Return the items of a filtered read, failing with the array's message."""
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to get {0} of Object Store Account {1}. Error: {2}".format(
                what, module.params["name"], get_error_message(res)
            )
        )
    return list(res.items)


def get_s3acc(module, blade):
    """Return Object Store Account or None

    Only the array's "does not exist" means absent. Any other refusal fails
    the task with the array's message, so it is never taken for a missing
    account.
    """
    res = blade.get_object_store_accounts(
        names=[module.params["name"]],
        **_api_context_kwargs(module, get_rest_api_version(blade))
    )
    if res.status_code == 200:
        items = list(res.items)
        return items[0] if items else None
    error = get_error_message(res)
    if "does not exist" not in str(error).lower():
        module.fail_json(
            msg="Failed to get Object Store Account {0}. Error: {1}".format(
                module.params["name"], error
            )
        )
    return None


def _quota_bytes(module, option, value):
    """Return a quota as a string of bytes, an empty string for unlimited.

    The array takes a quota of 1 byte to MAX_QUOTA bytes and refuses any
    other value. A value outside of that range, or one that is not a size,
    fails here, before anything is written.
    """
    if not value:
        return ""
    size_text = str(value).strip()
    try:
        # a plain number of bytes is taken as it is, not through a float
        size = int(size_text) if size_text.isdigit() else human_to_bytes(size_text)
    except (ValueError, TypeError):
        module.fail_json(
            msg="{0} {1} is not a valid size for Object Store Account {2}. Use a "
            "number of bytes, or a number followed by K, M, G, T, P or "
            "E.".format(option, value, module.params["name"])
        )
    if not 1 <= size <= MAX_QUOTA:
        module.fail_json(
            msg="{0} {1} is out of range for Object Store Account {2}: the array "
            "accepts 1 byte to {3} bytes. Use '' (empty string) for no "
            "limit.".format(option, value, module.params["name"], MAX_QUOTA)
        )
    return str(size)


def _check_hard_limits(module, quota, hard_limit, default_quota, default_hard_limit):
    """Fail when the request would set a hard limit without a quota.

    The array refuses a hard limit on an account that is unlimited in size,
    and a default hard limit while the default bucket quota is unlimited. It
    judges the settings the request leaves behind, so they are checked here
    before the request is sent and check mode reports what a real run does.
    """
    name = module.params["name"]
    if hard_limit and not quota:
        module.fail_json(
            msg="Object Store Account {0} cannot have hard_limit set to true "
            "while its quota is unlimited. Set quota as well, or set hard_limit "
            "to false.".format(name)
        )
    if default_hard_limit and not default_quota:
        module.fail_json(
            msg="Object Store Account {0} cannot have default_hard_limit set to "
            "true while its default_quota is unlimited. Set default_quota as "
            "well, or set default_hard_limit to false.".format(name)
        )


def _qualify_server(module, server):
    """Return the name of an export server as the array knows it.

    The array exports an account only on servers of the account's own realm
    and does not look up a bare server name in that realm. A bare name on an
    account named realm::account is therefore taken as realm::server. The
    array's own server, _array_server, is outside of every realm and keeps
    its name.
    """
    realm = _realm_of(module.params["name"])
    if not realm or "::" in server or server.lower() == ARRAY_DEFAULT_SERVER:
        return server
    return "{0}::{1}".format(realm, server)


def _requested_export_servers(module):
    """Return the server names listed in account_exports, or None when unset."""
    if module.params["account_exports"] is None:
        return None
    return [
        _qualify_server(
            module, _one_name(module, "account_exports server", export["server"])
        )
        for export in module.params["account_exports"]
    ]


def _check_export_scope(module, servers):
    """Fail when a new account would be exported outside of its realm.

    An account in a realm is exported on servers of that realm, an account
    outside of any realm on servers outside of any realm. The array refuses
    every other pair, so the pair is refused before the account is created
    and check mode reports what a real run does.
    """
    name = module.params["name"]
    realm = _realm_of(name)
    for server in servers or []:
        # the array matches names without regard to case
        if _realm_of(server).lower() == realm.lower():
            continue
        if realm:
            reason = (
                "an account in realm {0} is exported on servers of that realm, "
                "named {0}::<server>"
            ).format(realm)
        else:
            reason = (
                "an account outside of any realm is exported on servers "
                "outside of any realm"
            )
        module.fail_json(
            msg="Object Store Account {0} cannot be exported on server {1}: "
            "{2}.".format(name, server, reason)
        )


def _check_export_servers(module, blade, api_version, servers):
    """Fail a check mode run that would export a new account on a missing server.

    A real run gets the array's answer from the create itself; check mode
    sends nothing, so it reads the servers instead of reporting a change the
    real run cannot make. Only a definite answer fails the task.
    """
    for server in servers or []:
        res = blade.get_servers(
            names=[server], **_api_context_kwargs(module, api_version)
        )
        if res.status_code == 200:
            continue
        error = get_error_message(res)
        if "does not exist" in str(error).lower():
            module.fail_json(
                msg="Object Store Account {0} cannot be exported on server {1}. "
                "Error: {2}".format(module.params["name"], server, error)
            )


def _check_realm(module, blade, api_version):
    """Fail a check mode run that would create an account in an unusable realm.

    The array refuses to create an account in a realm that does not exist or
    has been destroyed. A real run gets that answer from the create itself;
    check mode sends nothing, so it reads the realm instead of reporting a
    change the real run cannot make. Only a definite answer fails the task.
    """
    name = module.params["name"]
    realm = _realm_of(name)
    if not realm or LooseVersion(REALM_API_VERSION) > LooseVersion(api_version):
        return
    ctx = _context_kwargs(module)
    if ctx and LooseVersion(REALM_CONTEXT_API_VERSION) > LooseVersion(api_version):
        return
    res = blade.get_realms(names=[realm], **ctx)
    if res.status_code == 200:
        items = list(res.items)
        if not items or not getattr(items[0], "destroyed", False):
            return
        reason = "Realm has been destroyed."
    else:
        reason = get_error_message(res)
        if "does not exist" not in str(reason).lower():
            return
    module.fail_json(
        msg="Object Store Account {0} cannot be created in realm {1}. Error: "
        "{2}".format(name, realm, reason)
    )


def _current_export_servers(module, blade):
    """Return the sorted names of the servers the account is exported on."""
    res = blade.get_object_store_account_exports(
        filter="member.name='{0}'".format(module.params["name"]),
        **_context_kwargs(module)
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to get exports of account {0}. Error: {1}".format(
                module.params["name"], get_error_message(res)
            )
        )
    servers = []
    for export in list(res.items):
        server = getattr(export, "server", None)
        if server is not None:
            servers.append(server.name)
    return sorted(servers)


def _check_account_exports(module, blade):
    """Warn when the exports of an existing account differ from account_exports."""
    requested = _requested_export_servers(module)
    if requested is None:
        return
    current = _current_export_servers(module, blade)
    # the array matches server names without regard to case
    if sorted(server.lower() for server in requested) != sorted(
        server.lower() for server in current
    ):
        module.warn(
            "account_exports only applies when an account is created. Account {0} "
            "is exported on {1}; account_exports lists {2}. Use purefb_s3acc_export "
            "to change the exports of an existing account.".format(
                module.params["name"],
                ", ".join(current) or "no server",
                ", ".join(requested) or "no server",
            )
        )


def update_s3acc(module, blade, acc_settings):
    """Update Object Store Account"""
    changed = False
    api_version = get_rest_api_version(blade)
    public = False
    _check_account_exports(module, blade)
    if LooseVersion(PUBLIC_API_VERSION) <= LooseVersion(api_version):
        public = True
        current_account = {
            "hard_limit": acc_settings.hard_limit_enabled,
            "default_hard_limit": acc_settings.bucket_defaults.hard_limit_enabled,
            "quota": str(acc_settings.quota_limit),
            "default_quota": str(acc_settings.bucket_defaults.quota_limit),
            "block_new_public_policies": acc_settings.public_access_config.block_new_public_policies,
            "block_public_access": acc_settings.public_access_config.block_public_access,
        }
    else:
        current_account = {
            "hard_limit": acc_settings.hard_limit_enabled,
            "default_hard_limit": acc_settings.bucket_defaults.hard_limit_enabled,
            "quota": str(acc_settings.quota_limit),
            "default_quota": str(acc_settings.bucket_defaults.quota_limit),
        }
    if current_account["quota"] == "None":
        current_account["quota"] = ""
    if current_account["default_quota"] == "None":
        current_account["default_quota"] = ""
    if module.params["quota"] is None:
        module.params["quota"] = current_account["quota"]
    if module.params["default_quota"] is None:
        module.params["default_quota"] = current_account["default_quota"]
    if not module.params["default_quota"]:
        module.params["default_quota"] = ""
    quota = _quota_bytes(module, "quota", module.params["quota"])
    default_quota = _quota_bytes(
        module, "default_quota", module.params["default_quota"]
    )
    if module.params["hard_limit"] is None:
        hard_limit = current_account["hard_limit"]
    else:
        hard_limit = module.params["hard_limit"]
    if module.params["default_hard_limit"] is None:
        default_hard_limit = current_account["default_hard_limit"]
    else:
        default_hard_limit = module.params["default_hard_limit"]
    if public:
        if module.params["block_new_public_policies"] is None:
            new_public_policies = current_account["block_new_public_policies"]
        else:
            new_public_policies = module.params["block_new_public_policies"]
        if module.params["block_public_access"] is None:
            public_access = current_account["block_public_access"]
        else:
            public_access = module.params["block_public_access"]
        new_account = {
            "hard_limit": hard_limit,
            "default_hard_limit": default_hard_limit,
            "quota": quota,
            "default_quota": default_quota,
            "block_new_public_policies": new_public_policies,
            "block_public_access": public_access,
        }
    else:
        new_account = {
            "hard_limit": module.params["hard_limit"],
            "default_hard_limit": module.params["default_hard_limit"],
            "quota": quota,
            "default_quota": default_quota,
        }
    if new_account != current_account:
        changed = True
        _check_hard_limits(
            module,
            new_account["quota"],
            new_account["hard_limit"],
            new_account["default_quota"],
            new_account["default_hard_limit"],
        )
        if not module.check_mode:
            if public:
                osa = ObjectStoreAccountPatch(
                    hard_limit_enabled=new_account["hard_limit"],
                    quota_limit=new_account["quota"],
                    bucket_defaults=BucketDefaults(
                        hard_limit_enabled=new_account["default_hard_limit"],
                        quota_limit=new_account["default_quota"],
                    ),
                    public_access_config=PublicAccessConfig(
                        block_public_access=new_account["block_public_access"],
                        block_new_public_policies=new_account[
                            "block_new_public_policies"
                        ],
                    ),
                )
            else:
                osa = ObjectStoreAccountPatch(
                    hard_limit_enabled=new_account["hard_limit"],
                    quota_limit=new_account["quota"],
                    bucket_defaults=BucketDefaults(
                        hard_limit_enabled=new_account["default_hard_limit"],
                        quota_limit=new_account["default_quota"],
                    ),
                )
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.patch_object_store_accounts(
                    object_store_account=osa,
                    names=[module.params["name"]],
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.patch_object_store_accounts(
                    object_store_account=osa, names=[module.params["name"]]
                )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to update account {0}. "
                    "Error: {1}".format(module.params["name"], get_error_message(res))
                )

    module.exit_json(changed=changed)


def _remove_new_account(module, blade, ctx, error):
    """Fail after removing the account this task has just created.

    The quotas of a new account are set with a second request. When the
    array refuses them the account is deleted again, so a failed task does
    not leave an account without the quotas it was asked for.
    """
    name = module.params["name"]
    res = blade.delete_object_store_accounts(names=[name], **ctx)
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to set quotas correctly for account {0}. Error: {1} The "
            "new account could not be removed and is left without these quotas. "
            "Error: {2}".format(name, error, get_error_message(res))
        )
    module.fail_json(
        msg="Failed to set quotas correctly for account {0}. Error: {1} The new "
        "account has been removed.".format(name, error)
    )


def create_s3acc(module, blade):
    """Create Object Store Account"""
    changed = True
    api_version = get_rest_api_version(blade)
    ctx = _api_context_kwargs(module, api_version)
    export_servers = _requested_export_servers(module)
    _check_export_scope(module, export_servers)
    quota = _quota_bytes(module, "quota", module.params["quota"])
    default_quota = _quota_bytes(
        module, "default_quota", module.params["default_quota"]
    )
    hard_limit = bool(module.params["hard_limit"])
    default_hard_limit = bool(module.params["default_hard_limit"])
    if quota or default_quota:
        _check_hard_limits(module, quota, hard_limit, default_quota, default_hard_limit)
    if module.check_mode:
        _check_realm(module, blade, api_version)
        _check_export_servers(module, blade, api_version, export_servers)
    else:
        post_kwargs = dict(names=[module.params["name"]], **ctx)
        if export_servers is not None:
            # [] creates the account without any export; without a body the
            # array creates its default export.
            post_kwargs["object_store_account"] = ObjectStoreAccountPost(
                account_exports=[
                    ServerForAccountExport(server=Reference(name=server))
                    for server in export_servers
                ]
            )
        res = blade.post_object_store_accounts(**post_kwargs)
        if res.status_code != 200:
            module.fail_json(
                msg="Object Store Account {0} creation failed. Error: {1}".format(
                    module.params["name"],
                    get_error_message(res),
                )
            )
        if quota or default_quota:
            osa = ObjectStoreAccountPatch(
                hard_limit_enabled=hard_limit,
                quota_limit=quota,
                bucket_defaults=BucketDefaults(
                    hard_limit_enabled=default_hard_limit,
                    quota_limit=default_quota,
                ),
            )
            res = blade.patch_object_store_accounts(
                object_store_account=osa, names=[module.params["name"]], **ctx
            )
            if res.status_code != 200:
                _remove_new_account(module, blade, ctx, get_error_message(res))
        if LooseVersion(PUBLIC_API_VERSION) <= LooseVersion(api_version):
            if not module.params["block_new_public_policies"]:
                module.params["block_new_public_policies"] = False
            if not module.params["block_public_access"]:
                module.params["block_public_access"] = False
            osa = ObjectStoreAccountPatch(
                public_access_config=PublicAccessConfig(
                    block_new_public_policies=module.params[
                        "block_new_public_policies"
                    ],
                    block_public_access=module.params["block_public_access"],
                )
            )
            res = blade.patch_object_store_accounts(
                object_store_account=osa, names=[module.params["name"]], **ctx
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to Public Access config correctly for account {0}. "
                    "Error: {1}".format(module.params["name"], get_error_message(res))
                )

    module.exit_json(changed=changed)


def delete_s3acc(module, blade):
    """Delete Object Store Account

    The array refuses to delete an account that still has buckets, and the
    module does not delete one that still has users. Both are looked up
    before the check mode branch, so check mode reports what a real run does.
    """
    changed = True
    name = module.params["name"]
    ctx = _api_context_kwargs(module, get_rest_api_version(blade))
    # Users are named "<account>/<user>"; look for any user of this account.
    users = _checked_items(
        module,
        blade.get_object_store_users(filter="name='" + name + "/*'", **ctx),
        "users",
    )
    if users:
        module.fail_json(
            msg="Remove all Users from Object Store Account {0} "
            "before deletion".format(name)
        )
    buckets = _checked_items(
        module,
        blade.get_buckets(filter="account.name='" + name + "'", **ctx),
        "buckets",
    )
    if buckets:
        module.fail_json(
            msg="Remove all Buckets from Object Store Account {0} before "
            "deletion. A destroyed bucket counts until it is eradicated.".format(name)
        )
    if not module.check_mode:
        res = blade.delete_object_store_accounts(names=[name], **ctx)
        if res.status_code != 200:
            module.fail_json(
                msg="Object Store Account {0} deletion failed. Error: {1}".format(
                    name, get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(required=True, type="str"),
            hard_limit=dict(type="bool"),
            default_hard_limit=dict(type="bool"),
            block_new_public_policies=dict(type="bool"),
            block_public_access=dict(type="bool"),
            quota=dict(type="str"),
            default_quota=dict(type="str"),
            account_exports=dict(
                type="list",
                elements="dict",
                options=dict(server=dict(type="str", required=True)),
            ),
            state=dict(default="present", choices=["present", "absent"]),
            context=dict(type="str", default=""),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    state = module.params["state"]
    module.params["name"] = _one_name(module, "name", module.params["name"])
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

    if module.params["quota"] or module.params["default_quota"]:
        if not HAS_PYPURECLIENT:
            module.fail_json(msg="py-pure-client sdk is required for to set quotas")

    upper = False
    for element in module.params["name"]:
        if element.isupper():
            upper = True
            break
    if upper:
        module.warn("Changing account name to lowercase...")
        module.params["name"] = module.params["name"].lower()

    export_servers = _requested_export_servers(module)
    if export_servers is not None:
        if not HAS_PYPURECLIENT:
            module.fail_json(
                msg="py-pure-client sdk is required to set account_exports"
            )
        if LooseVersion(ACCOUNT_EXPORTS_API_VERSION) > LooseVersion(api_version):
            module.fail_json(
                msg="account_exports requires FlashBlade REST version {0} or later "
                "(Purity//FB 4.6.3+)".format(ACCOUNT_EXPORTS_API_VERSION)
            )
        # the array matches server names without regard to case
        if len(set(server.lower() for server in export_servers)) != len(export_servers):
            module.fail_json(msg="account_exports contains duplicate server names")

    if state == "present":
        # a quota the array cannot take fails before the account is read
        _quota_bytes(module, "quota", module.params["quota"])
        _quota_bytes(module, "default_quota", module.params["default_quota"])

    s3acc = get_s3acc(module, blade)

    if state == "absent" and s3acc:
        delete_s3acc(module, blade)
    elif state == "present" and s3acc:
        update_s3acc(module, blade, s3acc)
    elif not s3acc and state == "present":
        create_s3acc(module, blade)
    else:
        module.exit_json(changed=False)


if __name__ == "__main__":
    main()
