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
module: purefb_apiclient
version_added: '1.6.0'
short_description: Manage FlashBlade API Clients
description:
- Create, enable, disable and delete FlashBlade API Clients.
- The management access policies of an API client are fixed when the client
  is created. Delete and recreate the client to change them.
- API clients are array-level objects and cannot be placed in a realm. An
  administrator whose access is limited to a realm may not read or change
  them; run this module as an administrator with array-wide access.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
notes:
- The array only allows the enabled state of an existing API client to be
  changed. I(access_policies), I(role), I(public_key), I(issuer) and
  I(token_ttl) cannot be changed in place, so when a supplied value differs
  from the array the module warns and leaves the client as it is.
options:
  name:
    description:
    - Name of the API Client
    - The name takes no realm prefix. A realm-qualified name
      (C(realm::name)) is refused.
    type: str
    required: true
  state:
    description:
    - Define whether the API client should exist or not.
    default: present
    choices: [ absent, present ]
    type: str
  access_policies:
    description:
    - Names of the management access policies granted to ID Tokens issued by
      this API client.
    - The bearer of an access token may perform actions within the intersection
      of these policies and those of the array user named in the token.
    - The realm scope of a token comes from the policies of the user named
      in it. A policy whose rules are scoped to a realm is accepted
      here, but it does not confine the tokens of this API client to that
      realm. On Purity//FB 4.8.8 a token issued to a user whose own policies
      are array-wide still reads objects outside the realm. To confine a
      token to a realm, give the user named in it only policies whose rules
      are scoped to that realm.
    - Policies are array-level objects and are named without a realm prefix.
    - The built-in policies are C(readonly), C(ops_admin), C(storage_admin) and
      C(array_admin). Custom policies are managed by
      M(everpure.flashblade.purefb_mgmt_policy).
    - Requires Purity//FB 4.6.1 or later (REST API 2.19).
    - One of I(access_policies) or I(role) is required when creating an API
      client. Mutually exclusive with I(role).
    type: list
    elements: str
    version_added: '1.30.0'
  role:
    description:
    - Legacy single management access policy for ID Tokens issued by this API
      client. Equivalent to I(access_policies) with the built-in policy of the
      same name.
    - Kept for backwards compatibility. The underlying C(max_role) field is
      deprecated on the array in favour of access policies, so prefer
      I(access_policies).
    - Mutually exclusive with I(access_policies).
    type: str
    choices: [readonly, ops_admin, storage_admin, array_admin]
  issuer:
    description:
    - The name of the identity provider that will be issuing ID Tokens for this API client
    - If not specified, defaults to the API client name, I(name).
    type: str
  public_key:
    description:
    - The API clients PEM formatted (Base64 encoded) RSA public key.
    - Include the I(—–BEGIN PUBLIC KEY—–) and I(—–END PUBLIC KEY—–) lines
    type: str
  token_ttl:
    description:
    - Time To Live length in seconds for the exchanged access token
    - Range is 1 second to 1 day (86400 seconds)
    - Defaults to 86400 when creating an API client.
    type: int
  enabled:
    description:
    - State of the API Client Key
    type: bool
    default: true
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Create API client with a built-in access policy
  everpure.flashblade.purefb_apiclient:
    name: ansible_token
    issuer: "Pure_Storage"
    token_ttl: 3000
    access_policies:
      - readonly
    public_key: "{{lookup('file', 'public_pem_file') }}"
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Create API client limited by two access policies
  everpure.flashblade.purefb_apiclient:
    name: backup_token
    access_policies:
      - readonly
      - backup-operator
    public_key: "{{lookup('file', 'public_pem_file') }}"
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Create API client using the legacy role option
  everpure.flashblade.purefb_apiclient:
    name: legacy_token
    role: array_admin
    public_key: "{{lookup('file', 'public_pem_file') }}"
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Disable API Client
  everpure.flashblade.purefb_apiclient:
    name: ansible_token
    enabled: false
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Enable API Client
  everpure.flashblade.purefb_apiclient:
    name: ansible_token
    enabled: true
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Delete API Client
  everpure.flashblade.purefb_apiclient:
    state: absent
    name: ansible_token
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3
"""

RETURN = r"""
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import ApiClient, ApiClientsPost, ReferenceWritable
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

MIN_ACCESS_POLICIES_API_VERSION = "2.19"
DEFAULT_TOKEN_TTL = 86400


def _requested_policies(module):
    """Return the de-duplicated policy names the task asks for, or None.

    ``access_policies`` wins; the legacy ``role`` maps to the built-in policy
    of the same name.
    """
    if module.params["access_policies"]:
        policies = []
        for policy in module.params["access_policies"]:
            if policy not in policies:
                policies.append(policy)
        return policies
    if module.params["role"]:
        return [module.params["role"]]
    return None


def _current_policies(client):
    """Return the policy names on an existing client.

    Arrays below REST 2.19 report only ``max_role``; treat it as a one-item
    policy list so the comparison works on every version.
    """
    policies = getattr(client, "access_policies", None)
    if policies:
        return [policy.name for policy in policies]
    max_role = getattr(getattr(client, "max_role", None), "name", None)
    return [max_role] if max_role else []


def _access_policies_supported(api_version):
    """Return True when the array accepts ``access_policies`` (REST 2.19+)."""
    return LooseVersion(MIN_ACCESS_POLICIES_API_VERSION) <= LooseVersion(api_version)


def _get_client(module, blade):
    """Return the named API client, or None when it does not exist.

    The array answers a GET for an unknown name with a 400 ("API client
    does not exist."), so only that error reads as None. Any other failure
    fails the task instead of masquerading as a missing client, which would
    let state=absent report ok on a transient error or send a POST for a
    client that is already there.
    """
    res = blade.get_api_clients(names=[module.params["name"]])
    if res.status_code == 200:
        items = list(res.items)
        return items[0] if items else None
    error = get_error_message(res)
    if error and "does not exist" in str(error).lower():
        return None
    module.fail_json(
        msg="Failed to get API Client {0}. Error: {1}".format(
            module.params["name"], error
        )
    )


def delete_client(module, blade):
    changed = True
    if not module.check_mode:
        res = blade.delete_api_clients(names=[module.params["name"]])
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete API Client {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def update_client(module, blade, client):
    """Update API Client

    The array only allows the enabled state of an existing API client to be
    changed; there is no PATCH for the access policies, public key, issuer or
    token TTL. A supplied value that differs from the array is reported as a
    warning rather than silently ignored.
    """
    changed = False
    immutable = []
    requested = _requested_policies(module)
    if requested is not None and sorted(requested) != sorted(_current_policies(client)):
        immutable.append(
            "access_policies" if module.params["access_policies"] else "role"
        )
    if module.params["public_key"] is not None:
        # Compare ignoring whitespace so line wrapping or a trailing newline
        # from a file lookup does not count as a different key.
        current_key = "".join((getattr(client, "public_key", None) or "").split())
        if "".join(module.params["public_key"].split()) != current_key:
            immutable.append("public_key")
    if module.params["issuer"] is not None and module.params["issuer"] != getattr(
        client, "issuer", None
    ):
        immutable.append("issuer")
    if module.params["token_ttl"] is not None and module.params[
        "token_ttl"
    ] * 1000 != getattr(client, "access_token_ttl_in_ms", None):
        immutable.append("token_ttl")
    if immutable:
        module.warn(
            "API Client {0}: {1} cannot be changed on an existing client and "
            "will remain as currently set on the array. Delete and recreate "
            "the client to apply the new value(s).".format(
                module.params["name"], ", ".join(immutable)
            )
        )
    if client.enabled != module.params["enabled"]:
        changed = True
        if not module.check_mode:
            res = blade.patch_api_clients(
                names=[module.params["name"]],
                api_clients=ApiClient(enabled=module.params["enabled"]),
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to update API Client {0}. Error: {1}".format(
                        module.params["name"], get_error_message(res)
                    )
                )
    module.exit_json(changed=changed)


def create_client(module, blade, api_version):
    """Create API Client

    On REST 2.19 and later the policies are sent as ``access_policies``
    (``max_role`` is deprecated there); older arrays only accept ``max_role``,
    so a legacy ``role`` is sent that way. ``main`` has already refused
    ``access_policies`` on such arrays.
    """
    changed = True
    if not module.params["public_key"]:
        module.fail_json(msg="public_key is required to create an API Client")
    policies = _requested_policies(module)
    if not policies:
        module.fail_json(
            msg="access_policies or role is required to create an API Client"
        )
    policies_supported = _access_policies_supported(api_version)
    token_ttl = module.params["token_ttl"]
    if token_ttl is None:
        token_ttl = DEFAULT_TOKEN_TTL
    if not 1 <= token_ttl <= 86400:
        module.fail_json(msg="token_ttl parameter is out of range (1 to 86400)")
    if not module.params["issuer"]:
        module.params["issuer"] = module.params["name"]
    if not module.check_mode:
        client_kwargs = dict(
            issuer=module.params["issuer"],
            access_token_ttl_in_ms=token_ttl * 1000,
            public_key=module.params["public_key"],
        )
        if policies_supported:
            client_kwargs["access_policies"] = [
                ReferenceWritable(name=policy) for policy in policies
            ]
        else:
            client_kwargs["max_role"] = ReferenceWritable(name=policies[0])
        res = blade.post_api_clients(
            names=[module.params["name"]], api_client=ApiClientsPost(**client_kwargs)
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to create API Client {0}. Error message: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
        if module.params["enabled"]:
            attr = ApiClient(enabled=True)
            res = blade.patch_api_clients(
                api_clients=attr, names=[module.params["name"]]
            )
            if res.status_code != 200:
                module.warn(
                    "API Client {0} created but enable failed. Please investigate.".format(
                        module.params["name"]
                    )
                )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(type="str", default="present", choices=["absent", "present"]),
            enabled=dict(type="bool", default=True),
            name=dict(type="str", required=True),
            role=dict(
                type="str",
                choices=["readonly", "ops_admin", "storage_admin", "array_admin"],
            ),
            access_policies=dict(type="list", elements="str"),
            public_key=dict(type="str", no_log=True),
            token_ttl=dict(type="int", no_log=False),
            issuer=dict(type="str"),
        )
    )

    module = AnsibleModule(
        argument_spec,
        mutually_exclusive=[["role", "access_policies"]],
        supports_check_mode=True,
    )
    pattern = re.compile("^[a-zA-Z0-9]([a-zA-Z0-9_-]{0,54}[a-zA-Z0-9])?$")
    if module.params["issuer"]:
        if not pattern.match(module.params["issuer"]):
            module.fail_json(
                msg="API Client Issuer name {0} does not conform to required naming convention".format(
                    module.params["issuer"]
                )
            )
    if not pattern.match(module.params["name"]):
        module.fail_json(
            msg="API Client name {0} does not conform to required naming convention".format(
                module.params["name"]
            )
        )
    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if module.params["access_policies"] and not _access_policies_supported(api_version):
        module.fail_json(
            msg=(
                "FlashBlade REST version {0} does not support access_policies "
                "(requires {1}+). Use the role option instead."
            ).format(api_version, MIN_ACCESS_POLICIES_API_VERSION)
        )
    state = module.params["state"]

    client = _get_client(module, blade)
    exists = client is not None

    if not exists and state == "present":
        create_client(module, blade, api_version)
    elif exists and state == "present":
        update_client(module, blade, client)
    elif exists and state == "absent":
        delete_client(module, blade)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
