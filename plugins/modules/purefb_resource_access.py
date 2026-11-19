#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Simon Dodsley (simon@everpuredata.com)
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
module: purefb_resource_access
version_added: '1.28.0'
short_description: Manage Resource Access on Everpure FlashBlades
description:
    - Create or delete resource access on Everpure FlashBlades.
    - A resource access shares an array-level resource with a realm, so that
      the objects of the realm can use it. The resource stays at the array
      level.
    - A shared DNS configuration can also be changed from the realm. On
      Purity//FB 4.8 an administrator whose management access is limited to
      a realm can change a DNS configuration that is shared with that realm,
      for example its nameservers, and a configuration shared with several
      realms can be changed by the administrators of each of them. Share a
      DNS configuration that serves only the realms it is shared with.
author:
    - Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
    - Leo Wahlandt (@valen98) <wahlandtleo@gmail.com>
options:
  resource_type:
    description:
      - The type of resource you want to add, given as the REST collection
        name of the resource.
      - The set of valid resource types is defined by the array and grows
        with the REST API version, so it is not validated by this module.
      - For a realm scope, the array accepts the array-level resources that
        can be shared with a realm. Purity//FB 4.6 accepts C(subnets) and
        C(dns). Purity//FB 4.8 accepts C(subnets), C(dns), C(targets) (a
        remote S3 target managed with
        M(everpure.flashblade.purefb_target)), C(sso/oidc/idps) (an OIDC
        identity provider managed with M(everpure.flashblade.purefb_oidc))
        and C(sso/saml2/idps) (a SAML2 identity provider managed with
        M(everpure.flashblade.purefb_saml)).
      - Purity//FB 4.8 keeps OIDC identity providers at the array level. A
        provider has to be shared with a realm before the trust policies of
        the object store roles in that realm can name it, and the array
        refuses to revoke the share while one of them does.
      - Policies cannot be shared with a realm through a resource access;
        the array rejects them with C(Invalid resource type). A policy for
        a realm, for example an NFS export policy, is created in the realm
        under the name C(realm::policy).
    type: str
    required: true
  resource_name:
    description:
      - The name of the resource you want to target.
      - An array-level resource is shared under its own name, without a
        realm prefix. Purity//FB 4.8 does not find an OIDC identity provider
        under the name C(realm::provider).
      - Names are unique on the array whatever their case, and an existing
        resource access is found whatever the case of I(resource_name) and
        I(scope_name). To create one, give both names as the array holds
        them. Purity//FB 4.8 does not find a realm, a DNS configuration, a
        target or an OIDC identity provider under a name in another case
        when a resource access is created.
    type: str
    required: true
  state:
    description:
      - Define whether the resource access should exist or not.
    type: str
    default: present
    choices: [ absent, present ]
  scope_type:
    description:
      - The type of scopes.
      - When using Realms, this value will be 'realms'
      - As with I(resource_type), the set of valid scope types is defined
        by the array and is not validated by this module.
    type: str
    required: true
  scope_name:
    description:
      - The name of the scope, that should be using the resource.
      - For a realm scope, the name of the realm as the array holds it.
      - You can not rename a resource access.
      - Resource access are immutable. You have to delete it and then create a new one.
    type: str
    required: true
notes:
- Check mode sends no request that changes the array. For a new resource
  access with a realm scope it reads the realm and, for the resource types
  named under I(resource_type), the resource, and fails as the create
  request would when the array does not hold one of them under the name
  given. What these reads do not settle is reported with a warning and the
  change is predicted, because only the array decides it. This applies to a
  resource type or scope type other than the ones named here, a destroyed
  realm, a subnet named in another case, a resource that belongs to a realm
  and a read the array refuses.
- Whether the array accepts a revoke is only known when the request is
  sent, and so is whether an administrator who may read the resource
  accesses may also change them.
- The array refuses to destroy a realm while a resource access names it.
  Revoke the resource accesses of a realm before the realm is destroyed
  with M(everpure.flashblade.purefb_realm).
- The module reads the resource accesses to find out whether one exists.
  Purity//FB 4.8 refuses that read with C(Operation not permitted) for an
  administrator whose management access is limited to a realm. With
  I(state=absent) and in check mode the module then fails with the error of
  the array; with I(state=present) it still sends the create request, which
  Purity//FB 4.8 refuses for such an administrator as well.
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Delegate subnet subnet_foo to realm realm_foo
  everpure.flashblade.purefb_resource_access:
    resource_type: subnets
    resource_name: subnet_foo
    scope_type: realms
    scope_name: realm_foo
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Share the data DNS configuration dns_foo with realm realm_foo
  everpure.flashblade.purefb_resource_access:
    resource_type: dns
    resource_name: dns_foo
    scope_type: realms
    scope_name: realm_foo
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Share remote S3 target target_foo with realm realm_foo
  everpure.flashblade.purefb_resource_access:
    resource_type: targets
    resource_name: target_foo
    scope_type: realms
    scope_name: realm_foo
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Share OIDC identity provider okta with realm realm_foo
  everpure.flashblade.purefb_resource_access:
    resource_type: sso/oidc/idps
    resource_name: okta
    scope_type: realms
    scope_name: realm_foo
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Share SAML2 identity provider saml_foo with realm realm_foo
  everpure.flashblade.purefb_resource_access:
    resource_type: sso/saml2/idps
    resource_name: saml_foo
    scope_type: realms
    scope_name: realm_foo
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Revoke the subnet delegation (the subnet itself is not deleted)
  everpure.flashblade.purefb_resource_access:
    resource_type: subnets
    resource_name: subnet_foo
    scope_type: realms
    scope_name: realm_foo
    state: absent
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
"""

RETURN = r"""
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import ResourceAccessPost
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

MINIMUM_API_VERSION = "2.19"

REALM_PREFIX_HINT = (
    "An array-level resource is shared under its own name, without a realm prefix."
)

# The resources Purity//FB 4.8 shares with a realm, by REST collection name,
# each with the read that finds one by its name
REALM_SHAREABLE = {
    "subnets": "get_subnets",
    "dns": "get_dns",
    "targets": "get_targets",
    "sso/oidc/idps": "get_sso_oidc_idps",
    "sso/saml2/idps": "get_sso_saml2_idps",
}

# Purity//FB 4.8 reads these by name whatever the case, but was seen to
# refuse a new resource access that names one in another case than it holds
EXACT_NAME_ON_CREATE = ("realms", "dns", "targets", "sso/oidc/idps")


def _access_text(module):
    """Name both ends of the resource access for a message"""
    return "{0} {1} and {2} {3}".format(
        module.params["scope_type"],
        module.params["scope_name"],
        module.params["resource_type"],
        module.params["resource_name"],
    )


def _realm_prefix_hint(module):
    """Hint for a realm-qualified resource name the array refused to share"""
    if (
        module.params["scope_type"] == "realms"
        and "::" in module.params["resource_name"]
    ):
        return REALM_PREFIX_HINT
    return ""


def _with_realm_prefix_hint(module, msg):
    """Add the hint for a realm-qualified resource name to a failure message"""
    hint = _realm_prefix_hint(module)
    if hint:
        if not msg.endswith("."):
            msg += "."
        msg = "{0} {1}".format(msg, hint)
    return msg


def _create_would_fail(module, reason):
    """Fail a check mode run for a create the array would refuse"""
    module.fail_json(
        msg=_with_realm_prefix_hint(
            module,
            "Create resource access between {0} would fail. {1}".format(
                _access_text(module), reason
            ),
        )
    )


def _not_verified(module, reason):
    """Warn that check mode predicts a create it could not verify"""
    if not reason.endswith("."):
        reason += "."
    module.warn(
        "Check mode did not verify the resource access between {0}: {1} The"
        " array decides when the request is sent.".format(_access_text(module), reason)
    )


def _read_by_name(module, blade, method, resource_type, name):
    """Read one end of a new resource access for check mode

    Returns the object the array holds under the name, or None when the
    read does not settle whether there is one. The array answers a create
    that names a missing realm or resource with the error of this read, so
    only that answer fails the task.
    """
    res = getattr(blade, method)(names=[name])
    if res.status_code == 200:
        items = list(res.items)
        if items:
            return items[0]
        _not_verified(
            module, "the array returned no {0} {1}".format(resource_type, name)
        )
        return None
    error = get_error_message(res)
    if "does not exist" in error.lower():
        _create_would_fail(module, "Error: {0}".format(error))
        return None
    _not_verified(
        module,
        "the read of {0} {1} failed. Error: {2}".format(resource_type, name, error),
    )
    return None


def _check_name_as_held(module, resource_type, given, found):
    """Compare a name of a new resource access with the name the array holds"""
    held = getattr(found, "name", None)
    if not held or held == given:
        return
    if resource_type in EXACT_NAME_ON_CREATE:
        _create_would_fail(
            module,
            "The array holds {0} {1} as {2} and creates a resource access only"
            " under the name as it holds it.".format(resource_type, given, held),
        )
        return
    _not_verified(
        module,
        "the array holds {0} {1} as {2} and may not find it under another"
        " case".format(resource_type, given, held),
    )


def _predict_create(module, blade):
    """Tell in check mode whether the array would accept a new resource access

    The array finds the realm and the resource of a new resource access by
    name and refuses the request when it holds no such realm or resource.
    The same reads are made here, so that check mode fails where the create
    request would. Everything they do not settle is left to the array and
    reported with a warning: no request the array might accept is refused.
    """
    resource_type = module.params["resource_type"]
    resource_name = module.params["resource_name"]
    scope_name = module.params["scope_name"]
    if module.params["scope_type"] != "realms":
        _not_verified(module, "the module can only check a scope of type realms")
        return
    realm = _read_by_name(module, blade, "get_realms", "realms", scope_name)
    if realm is not None:
        _check_name_as_held(module, "realms", scope_name, realm)
        if getattr(realm, "destroyed", False):
            _not_verified(module, "realm {0} is destroyed".format(scope_name))
    if resource_type not in REALM_SHAREABLE:
        _not_verified(
            module,
            "the module can only check a resource of type {0}".format(
                ", ".join(sorted(REALM_SHAREABLE))
            ),
        )
        return
    resource = _read_by_name(
        module, blade, REALM_SHAREABLE[resource_type], resource_type, resource_name
    )
    if resource is not None:
        _check_name_as_held(module, resource_type, resource_name, resource)
        if "::" in resource_name:
            _not_verified(
                module,
                "{0} {1} belongs to a realm, and the array is only known to"
                " share array-level resources".format(resource_type, resource_name),
            )


def get_resource_access(module, blade):
    """Get resource access"""
    filter_string = (
        "resource.resource_type='"
        + module.params["resource_type"]
        + "' and scope.name='"
        + module.params["scope_name"]
        + "' and scope.resource_type='"
        + module.params["scope_type"]
        + "'"
    )
    res = blade.get_resource_accesses(filter=filter_string)
    if res.status_code != 200:
        if module.params["state"] == "present" and not module.check_mode:
            # Whether the access exists is not known, but the create request
            # can still be sent and the array accepts or refuses it.
            return False, False
        module.fail_json(
            msg="Get resource access between {0} failed. Error: {1}".format(
                _access_text(module), get_error_message(res)
            )
        )
    if res.total_item_count:
        items = list(res.items)
        wanted = module.params["resource_name"]
        for item in items:
            if item.resource.name == wanted:
                return True, item.id
        # Names are unique on the array whatever their case, and a resource
        # access is listed under the name the resource was created with.
        for item in items:
            if item.resource.name.lower() == wanted.lower():
                return True, item.id
    return False, False


def create_resource_access(module, blade):
    """Create a new resource_access"""
    changed = True
    if module.check_mode:
        _predict_create(module, blade)
    else:
        resource = ResourceAccessPost(
            resource={
                "name": module.params["resource_name"],
                "resource_type": module.params["resource_type"],
            },
            scope={
                "name": module.params["scope_name"],
                "resource_type": module.params["scope_type"],
            },
        )
        res = blade.post_resource_accesses_batch(items=[resource])
        if res.status_code != 200:
            msg = "Create resource access between {0} failed. Error: {1}".format(
                _access_text(module), get_error_message(res)
            )
            module.fail_json(msg=_with_realm_prefix_hint(module, msg))
    module.exit_json(changed=changed)


def delete_resource_access(module, blade, access_id):
    """Delete resource access"""
    changed = True
    if not module.check_mode:
        res = blade.delete_resource_accesses(ids=[access_id])
        if res.status_code != 200:
            module.fail_json(
                msg="Delete resource access between {0} failed. Error: {1}".format(
                    _access_text(module),
                    get_error_message(res),
                )
            )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            resource_type=dict(type="str", required=True),
            resource_name=dict(type="str", required=True),
            state=dict(type="str", default="present", choices=["absent", "present"]),
            scope_type=dict(type="str", required=True),
            scope_name=dict(type="str", required=True),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)
    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    state = module.params["state"]
    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(MINIMUM_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg="Resource Access is not supported. Purity//FB 4.6.1, or higher, is required."
        )
    resource, access_id = get_resource_access(module, blade)

    if not resource and state == "present":
        create_resource_access(module, blade)
    elif resource and state == "absent":
        delete_resource_access(module, blade, access_id)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
