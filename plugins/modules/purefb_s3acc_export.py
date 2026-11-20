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
module: purefb_s3acc_export
version_added: '1.26.0'
short_description: Manage FlashBlade Object Store Account exports
description:
- Create, update or delete a FlashBlade object-store account export.
- An account export binds an object-store account to a server using an
  S3 export policy, making the account's buckets visible for S3 through
  that server.
- The account export is uniquely identified by the (I(account), I(server))
  pair.
- I(account), I(server) and I(policy) each name one object, and only the
  export of the named account on the named server is changed or removed.
  With I(state=present) an empty name and a name that holds a comma or an
  asterisk, which the array reads as a list of names or as a pattern, are
  refused. Blanks around a name are ignored.
- A new object store account is created by the array with a default export
  on its default object store server (normally C(_array_server)) bound to
  the built-in C(_s3_export_allow_everything) policy. On that server this
  module modifies the default export rather than creating a second one, and
  I(state=absent) removes it.
- An account in a realm gets a default export only when its realm has a
  default object store server (I(default_object_server) of
  M(everpure.flashblade.purefb_realm)). Without one the account has no
  export until one is created.
- An export is in the realm of its account and of its server, which must be
  the same realm. For an account in a realm give I(account), I(server) and
  I(policy) as C(realm::name).
- A realm-scoped administrator must use the realm-qualified name; a bare
  name is not placed in, or resolved to, the administrator's realm.
- In check mode the account, the server and the policy that a new export
  names, and the policy an existing export is re-pointed at, are looked up.
  The task fails when the array does not find one of them, as a real run
  does.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  state:
    description:
    - Define whether the account export should exist or not.
    default: present
    choices: [ absent, present ]
    type: str
  account:
    description:
    - Name of the object store account to export.
    - An account in a realm is named C(realm::account).
    type: str
    required: true
  server:
    description:
    - Name of the server the account will be exported on.
    - For an account in a realm use a server of the same realm,
      C(realm::server).
    - With I(state=present) the module fails, in check mode as well, when
      I(account) and I(server) are not in the same realm or not both outside
      of any realm. The array never creates such an export.
    type: str
    required: true
  policy:
    description:
    - Name of the S3 export policy used for the export.
    - Required when creating a new account export.
    - When supplied on update, the export will be re-pointed at the
      named policy.
    - An export in a realm uses a policy of the same realm,
      C(realm::policy), or the built-in C(_s3_export_allow_everything). An
      export outside of any realm uses a policy that is not in a realm.
    - Whether an existing policy can be used by the export is decided by
      the array when the export is written. Check mode does not predict
      that refusal.
    type: str
  enabled:
    description:
    - If C(true) the account export is enabled.
    - Defaults to C(true) on creation if not specified.
    type: bool
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
- name: Export account acme on server fb-01 using policy acme-export
  everpure.flashblade.purefb_s3acc_export:
    account: acme
    server: fb-01
    policy: acme-export
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Export account acme of realm tenant1 on server fb-01 of that realm
  everpure.flashblade.purefb_s3acc_export:
    account: tenant1::acme
    server: tenant1::fb-01
    policy: tenant1::acme-export
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Disable an existing account export
  everpure.flashblade.purefb_s3acc_export:
    account: acme
    server: fb-01
    enabled: false
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Re-point an existing account export at a different policy
  everpure.flashblade.purefb_s3acc_export:
    account: acme
    server: fb-01
    policy: acme-export-v2
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Delete an account export
  everpure.flashblade.purefb_s3acc_export:
    account: acme
    server: fb-01
    state: absent
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3
"""

RETURN = r"""
"""

import traceback

HAS_PYPURECLIENT = True
PYPURECLIENT_IMPORT_ERROR = None
try:
    from pypureclient.flashblade import (
        ObjectStoreAccountExportPost,
        ObjectStoreAccountExportPatch,
        Reference,
    )
except ImportError:
    HAS_PYPURECLIENT = False
    PYPURECLIENT_IMPORT_ERROR = traceback.format_exc()

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

MIN_REQUIRED_API_VERSION = "2.20"
# option: (what the array calls the object, the SDK method that reads it)
REFERENCE_READS = {
    "account": ("object store account", "get_object_store_accounts"),
    "server": ("server", "get_servers"),
    "policy": ("S3 export policy", "get_s3_export_policies"),
}
# character: what it makes of a name when the array reads it
NOT_ONE_NAME = {
    ",": "a comma separates the names of a list",
    "*": "an asterisk makes the name a pattern that several names can match",
}


def _context_kwargs(module):
    """Build context_names kwargs only when a context is supplied."""
    if module.params["context"]:
        return {"context_names": [module.params["context"]]}
    return {}


def _realm_of(name):
    """Return the realm of a realm::name name, empty for an array-level name."""
    return (name or "").rpartition("::")[0]


def _same_name(first, second):
    """Compare two names as the array matches them, without regard to case."""
    return (first or "").lower() == (second or "").lower()


def _strip_names(module):
    """Take the blanks from around the names of the task.

    A blank before or after a name is not part of the name. The array
    ignores it in the account of a new export, while the lookup of the
    export compares the name as it is given: an account with a blank at its
    end was exported, and the next run did not find the export, created it
    again and failed.
    """
    for option in REFERENCE_READS:
        value = module.params[option]
        if value and value.strip():
            module.params[option] = value.strip()


def _check_names(module):
    """Fail on names that cannot address an account export.

    An export has one account, one server and one policy. An empty name
    addresses nothing. The array reads a comma as the separator of a list of
    names and an asterisk as a pattern, so a lookup of such a name passes
    when the names in it, or a name that fits it, exist, although the array
    does not export more than one object at a time.

    An export is in the realm of its account and of its server. The array
    creates one only where both are in the same realm or both outside of any
    realm, so a task that mixes the scopes asks for an export that cannot
    exist.

    Such a task is refused before the export is looked up, in check mode as
    well, instead of reporting a change the array refuses.
    """
    for option in ("account", "server", "policy"):
        value = module.params[option]
        if option == "policy" and not value:
            # no policy: the export keeps the one it has
            continue
        if not (value or "").strip():
            module.fail_json(msg="{0} cannot be empty.".format(option))
        for character, meaning in NOT_ONE_NAME.items():
            if character in value:
                module.fail_json(
                    msg="{0} {1} is not valid: {2}, and an account export has one {3}.".format(
                        option, value, meaning, REFERENCE_READS[option][0]
                    )
                )
    account = module.params["account"]
    server = module.params["server"]
    account_realm = _realm_of(account)
    server_realm = _realm_of(server)
    if _same_name(account_realm, server_realm):
        return
    scopes = [
        "in realm {0}".format(realm) if realm else "not in a realm"
        for realm in (account_realm, server_realm)
    ]
    msg = (
        "Object store account {0} is {1} and server {2} is {3}. The account "
        "and the server of an account export must be in the same realm, or "
        "both outside of any realm."
    ).format(account, scopes[0], server, scopes[1])
    if account_realm and not server_realm:
        msg += " A server of realm {0} is named {0}::<server>.".format(account_realm)
    elif server_realm and not account_realm:
        msg += " An account of realm {0} is named {0}::<account>.".format(server_realm)
    module.fail_json(msg=msg)


def _check_references(module, blade, action, options):
    """Fail a check mode run that names an object the array does not find.

    A real run gets the array's answer from the write itself. Check mode
    sends nothing, so it reads the objects the export refers to instead of
    reporting a change the real run cannot make. Only a definite answer,
    an object the array does not find, fails the task. A read the array
    refuses for another reason is reported as a warning.
    """
    for option in options:
        kind, method = REFERENCE_READS[option]
        name = module.params[option]
        res = getattr(blade, method)(names=[name], **_context_kwargs(module))
        if res.status_code == 200:
            continue
        error = get_error_message(res)
        if "does not exist" in str(error).lower():
            module.fail_json(
                msg="Failed to {0} account export for account {1} on server {2}. Error: {3}".format(
                    action,
                    module.params["account"],
                    module.params["server"],
                    error,
                )
            )
        module.warn(
            "Check mode could not look up {0} {1}. Error: {2}".format(kind, name, error)
        )


def _get_export(module, blade):
    """Return the existing account export object, or None when there is none.

    A failed lookup is reported, never treated as "no export": doing so would
    turn an API error into a silent no-op for state=absent or into a POST that
    then fails with a misleading message for state=present.

    The filter of the lookup matches an asterisk as a pattern, and a quote in
    a name ends the quoted text of the filter, so the answer can hold the
    export of another account or server. Only the export of the account and
    the server the task names is returned.
    """
    filter_string = "member.name='{0}' and server.name='{1}'".format(
        module.params["account"], module.params["server"]
    )
    res = blade.get_object_store_account_exports(
        filter=filter_string, **_context_kwargs(module)
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to get account export for account {0} on server {1}. Error: {2}".format(
                module.params["account"],
                module.params["server"],
                get_error_message(res),
            )
        )
    for item in list(res.items):
        member = getattr(getattr(item, "member", None), "name", None)
        server = getattr(getattr(item, "server", None), "name", None)
        if _same_name(member, module.params["account"]) and _same_name(
            server, module.params["server"]
        ):
            return item
    return None


def delete_export(module, blade, export):
    """Delete an account export."""
    changed = True
    if not module.check_mode:
        res = blade.delete_object_store_account_exports(
            names=[getattr(export, "name", None)], **_context_kwargs(module)
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete account export for account {0} on server {1}. Error: {2}".format(
                    module.params["account"],
                    module.params["server"],
                    get_error_message(res),
                )
            )
    module.exit_json(changed=changed)


def create_export(module, blade):
    """Create a new account export."""
    if not module.params["policy"]:
        module.fail_json(msg="policy is required when creating a new account export.")
    if module.check_mode:
        _check_references(module, blade, "create", ("account", "server", "policy"))
    changed = True
    post_kwargs = {"server": Reference(name=module.params["server"])}
    if module.params["enabled"] is not None:
        post_kwargs["export_enabled"] = module.params["enabled"]
    if not module.check_mode:
        res = blade.post_object_store_account_exports(
            member_names=[module.params["account"]],
            policy_names=[module.params["policy"]],
            object_store_account_export=ObjectStoreAccountExportPost(**post_kwargs),
            **_context_kwargs(module),
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to create account export for account {0} on server {1}. Error: {2}".format(
                    module.params["account"],
                    module.params["server"],
                    get_error_message(res),
                )
            )
    module.exit_json(changed=changed)


def update_export(module, blade, export):
    """Update an existing account export."""
    changed = False
    patch_kwargs = {}

    if module.params["enabled"] is not None and module.params["enabled"] != getattr(
        export, "enabled", None
    ):
        patch_kwargs["export_enabled"] = module.params["enabled"]

    if module.params["policy"]:
        current_policy = getattr(getattr(export, "policy", None), "name", None)
        # The array matches names without regard to case and returns the
        # stored spelling, so another letter case is not another policy.
        if not _same_name(module.params["policy"], current_policy):
            patch_kwargs["policy"] = Reference(name=module.params["policy"])

    if patch_kwargs:
        changed = True
        if module.check_mode and "policy" in patch_kwargs:
            _check_references(module, blade, "update", ("policy",))
        if not module.check_mode:
            res = blade.patch_object_store_account_exports(
                names=[getattr(export, "name", None)],
                object_store_account_export=ObjectStoreAccountExportPatch(
                    **patch_kwargs
                ),
                **_context_kwargs(module),
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to update account export for account {0} on server {1}. Error: {2}".format(
                        module.params["account"],
                        module.params["server"],
                        get_error_message(res),
                    )
                )

    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(type="str", default="present", choices=["absent", "present"]),
            account=dict(type="str", required=True),
            server=dict(type="str", required=True),
            policy=dict(type="str"),
            enabled=dict(type="bool"),
            context=dict(type="str", default=""),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    if not HAS_PYPURECLIENT:
        # Keep the import failure itself: a half-installed or broken SDK gives
        # exactly the same symptom as a missing one, and only the traceback
        # tells them apart.
        module.fail_json(
            msg="py-pure-client sdk is required for this module",
            exception=PYPURECLIENT_IMPORT_ERROR,
        )

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg="FlashBlade REST version not supported. "
            "Minimum version required: {0}".format(MIN_REQUIRED_API_VERSION)
        )

    _strip_names(module)
    if module.params["state"] == "present":
        _check_names(module)

    if not module.params["context"]:
        # Only default the context to the local array name when this array is a
        # member of a fleet. A standalone array rejects any fleet context
        # ("Cannot find array in fleet: not in a fleet"), so leave context
        # unset - no context_names is then sent.
        fleet_res = blade.get_fleets()
        if fleet_res.status_code == 200 and list(fleet_res.items):
            module.params["context"] = list(blade.get_arrays().items)[0].name

    state = module.params["state"]
    export = _get_export(module, blade)

    if state == "present" and export is None:
        create_export(module, blade)
    elif state == "present" and export is not None:
        update_export(module, blade, export)
    elif state == "absent" and export is not None:
        delete_export(module, blade, export)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
