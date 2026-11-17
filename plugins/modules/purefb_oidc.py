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
module: purefb_oidc
version_added: '1.30.0'
short_description: Manage FlashBlade OIDC identity providers
description:
- Create, modify, rename or delete the OpenID Connect (OIDC) identity
  providers (IdPs) of a FlashBlade.
- An OIDC identity provider lets the object store exchange a JSON Web Token
  issued by an external provider for short-lived S3 credentials. Which
  tokens are accepted is governed by the object store roles and trust
  policies that reference the provider through its Pure Resource Name
  (C(prn)).
- Providers are array-wide objects. An array supports up to five OIDC
  identity providers for the object service.
- Requires FlashBlade REST API version 2.17 or later (Purity//FB 4.5.6+).
- The array does not contact the provider when it is configured. The
  provider's public keys are fetched when a token is validated, so a
  provider with an unreachable URL is accepted but tokens from it fail.
- A provider that is still referenced by an object store trust policy
  cannot be deleted, and C(object) cannot be removed from its services.
  The array rejects the request and the module reports the error.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - Name of the identity provider.
    type: str
    required: true
  state:
    description:
    - Create or update the identity provider (C(present)) or delete it
      (C(absent)).
    type: str
    default: present
    choices: [ absent, present ]
  provider_url:
    description:
    - URL of the identity provider, also known as the OIDC issuer URL.
    - Must be an C(https) URL. The array rejects any other scheme.
    - Required when creating a provider.
    type: str
  services:
    description:
    - Services that authenticate against the provider.
    - The array requires at least one service. Only C(object) exists.
    type: list
    elements: str
    default: [ object ]
    choices: [ object ]
  ca_certificate:
    description:
    - Name of an existing certificate on the array used to validate the
      identity of the provider server.
    - Use an empty string (C("")) to remove a configured certificate.
    - The array accepts either I(ca_certificate) or
      I(ca_certificate_group) on a provider, not both. To switch from one
      to the other, clear the current reference with an empty string in
      the same task that sets the new one.
    - Use M(everpure.flashblade.purefb_certs) to create certificates.
    type: str
  ca_certificate_group:
    description:
    - Name of an existing certificate group on the array whose CA
      certificates validate the identity of the provider server.
    - Use an empty string (C("")) to remove a configured certificate group.
    - See I(ca_certificate) for the restriction on using both references.
    - Use M(everpure.flashblade.purefb_certgrp) to create certificate
      groups.
    type: str
  enabled:
    description:
    - Whether the identity provider is enabled.
    - When omitted, a new provider takes the array default (enabled) and an
      existing provider keeps its current state.
    type: bool
  rename:
    description:
    - New name for the identity provider.
    - The Pure Resource Name of a provider embeds its name, so renaming a
      provider changes the C(prn) that object store trust policies
      reference.
    - The task fails when a provider called I(rename) already exists.
    type: str
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Create an OIDC identity provider
  everpure.flashblade.purefb_oidc:
    name: okta
    provider_url: https://acme.okta.com/oauth2/default
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
  register: result

- name: Show the PRN to reference from object store trust policies
  debug:
    var: result.prn

- name: Create a disabled provider validated by a CA certificate group
  everpure.flashblade.purefb_oidc:
    name: keycloak
    provider_url: https://sso.example.com/realms/storage
    ca_certificate_group: corporate-cas
    enabled: false
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Enable the provider
  everpure.flashblade.purefb_oidc:
    name: keycloak
    enabled: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Switch the provider from a certificate group to a single CA certificate
  everpure.flashblade.purefb_oidc:
    name: keycloak
    ca_certificate_group: ""
    ca_certificate: sso-root-ca
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Rename a provider
  everpure.flashblade.purefb_oidc:
    name: okta
    rename: okta-prod
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete a provider
  everpure.flashblade.purefb_oidc:
    name: okta-prod
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = r"""
name:
  description: Name of the identity provider after the task ran.
  returned: when I(state=present)
  type: str
  sample: okta
enabled:
  description:
  - Whether the identity provider is enabled.
  - C(null) in check mode when the provider does not exist yet and
    I(enabled) was not given.
  returned: when I(state=present)
  type: bool
  sample: true
prn:
  description:
  - Pure Resource Name of the identity provider, as referenced by object
    store trust policies. It embeds the provider name.
  - C(null) in check mode when the provider does not exist yet.
  returned: when I(state=present)
  type: str
  sample: prn::iam:array-id/local::oidc-provider/okta
provider_url:
  description: URL of the identity provider.
  returned: when I(state=present)
  type: str
  sample: https://acme.okta.com/oauth2/default
services:
  description: Services that authenticate against the provider.
  returned: when I(state=present)
  type: list
  elements: str
  sample: [ object ]
ca_certificate:
  description: Name of the CA certificate that validates the provider, if any.
  returned: when I(state=present)
  type: str
  sample: sso-root-ca
ca_certificate_group:
  description: Name of the CA certificate group that validates the provider, if any.
  returned: when I(state=present)
  type: str
  sample: corporate-cas
"""


HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        OidcSsoPatch,
        OidcSsoPost,
        OidcSsoPostIdp,
        Reference,
    )
except ImportError:
    HAS_PYPURECLIENT = False


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
SERVICES = ["object"]
# Module option -> field of the idp sub-object that holds the reference.
REFERENCE_FIELDS = {
    "ca_certificate": "provider_url_ca_certificate",
    "ca_certificate_group": "provider_url_ca_certificate_group",
}


def _reference_name(obj, field):
    """Name held by a reference field, or None when the reference is unset."""
    return getattr(getattr(obj, field, None), "name", None)


def _get_idp(module, blade, name):
    """Return the identity provider called name, or None when it does not exist.

    The array answers 400 for a name that is not configured. Any other
    failure is reported rather than mistaken for a missing provider.
    """
    res = blade.get_sso_oidc_idps(names=[name])
    if res.status_code == 200:
        items = list(res.items)
        return items[0] if items else None
    if res.status_code != 400:
        module.fail_json(
            msg="Failed to read OIDC identity provider {0}. Error: {1}".format(
                name, get_error_message(res)
            )
        )
    return None


def _facts(idp):
    """Return values of an identity provider as the array reports it."""
    idp_cfg = getattr(idp, "idp", None)
    return {
        "name": getattr(idp, "name", None),
        "enabled": getattr(idp, "enabled", None),
        "prn": getattr(idp, "prn", None),
        "provider_url": getattr(idp_cfg, "provider_url", None),
        "services": list(getattr(idp, "services", None) or []),
        "ca_certificate": _reference_name(idp_cfg, "provider_url_ca_certificate"),
        "ca_certificate_group": _reference_name(
            idp_cfg, "provider_url_ca_certificate_group"
        ),
    }


def _exit_with_facts(module, blade, changed, name, predicted):
    """Exit with the provider as the array now reports it.

    The provider is read back only after a write. In check mode, or when
    nothing differed, the values the task would have produced are reported.
    """
    facts = predicted
    if changed and not module.check_mode:
        current = _get_idp(module, blade, name)
        if current:
            facts = _facts(current)
    module.exit_json(changed=changed, **facts)


def delete_idp(module, blade):
    """Delete the identity provider."""
    changed = True
    if not module.check_mode:
        res = blade.delete_sso_oidc_idps(names=[module.params["name"]])
        if res.status_code != 200:
            msg = "Failed to delete OIDC identity provider {0}. Error: {1}".format(
                module.params["name"], get_error_message(res)
            )
            if res.status_code == 400:
                msg += (
                    " If an object store trust policy still references the "
                    "provider, it cannot be deleted."
                )
            module.fail_json(msg=msg)
    module.exit_json(changed=changed)


def create_idp(module, blade):
    """Create the identity provider with the fields given in the play."""
    if not module.params["provider_url"]:
        module.fail_json(
            msg="provider_url is required to create OIDC identity provider {0}".format(
                module.params["name"]
            )
        )
    idp_cfg = {"provider_url": module.params["provider_url"]}
    for param, field in REFERENCE_FIELDS.items():
        if module.params[param]:
            idp_cfg[field] = Reference(name=module.params[param])
    body = {
        "services": module.params["services"],
        "idp": OidcSsoPostIdp(**idp_cfg),
    }
    if module.params["enabled"] is not None:
        body["enabled"] = module.params["enabled"]
    changed = True
    if not module.check_mode:
        res = blade.post_sso_oidc_idps(
            names=[module.params["name"]], idp=OidcSsoPost(**body)
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to create OIDC identity provider {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    predicted = {
        "name": module.params["name"],
        "enabled": module.params["enabled"],
        "prn": None,
        "provider_url": module.params["provider_url"],
        "services": module.params["services"],
        "ca_certificate": module.params["ca_certificate"] or None,
        "ca_certificate_group": module.params["ca_certificate_group"] or None,
    }
    _exit_with_facts(module, blade, changed, module.params["name"], predicted)


def update_idp(module, blade, idp):
    """PATCH the fields of the existing provider that differ from the play."""
    current = _facts(idp)
    predicted = dict(current)
    patch = {}
    idp_cfg = {}
    if module.params["rename"] and module.params["rename"] != current["name"]:
        patch["name"] = module.params["rename"]
        predicted["name"] = module.params["rename"]
    if (
        module.params["enabled"] is not None
        and module.params["enabled"] != current["enabled"]
    ):
        patch["enabled"] = module.params["enabled"]
        predicted["enabled"] = module.params["enabled"]
    if sorted(module.params["services"]) != sorted(current["services"]):
        patch["services"] = module.params["services"]
        predicted["services"] = module.params["services"]
    if (
        module.params["provider_url"]
        and module.params["provider_url"] != current["provider_url"]
    ):
        idp_cfg["provider_url"] = module.params["provider_url"]
        predicted["provider_url"] = module.params["provider_url"]
    for param, field in REFERENCE_FIELDS.items():
        wanted = module.params[param]
        # An empty string clears the reference; the array reports a cleared
        # reference as an empty object, which reads back as None.
        if wanted is not None and wanted != (current[param] or ""):
            idp_cfg[field] = Reference(name=wanted)
            predicted[param] = wanted or None
    if idp_cfg:
        patch["idp"] = OidcSsoPostIdp(**idp_cfg)

    changed = bool(patch)
    if changed and not module.check_mode:
        res = blade.patch_sso_oidc_idps(
            names=[current["name"]], idp=OidcSsoPatch(**patch)
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to update OIDC identity provider {0}. Error: {1}".format(
                    current["name"], get_error_message(res)
                )
            )
    _exit_with_facts(module, blade, changed, predicted["name"], predicted)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str", required=True),
            state=dict(type="str", default="present", choices=["absent", "present"]),
            provider_url=dict(type="str"),
            services=dict(
                type="list", elements="str", default=SERVICES, choices=SERVICES
            ),
            ca_certificate=dict(type="str"),
            ca_certificate_group=dict(type="str"),
            enabled=dict(type="bool"),
            rename=dict(type="str"),
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

    state = module.params["state"]
    name = module.params["name"]
    rename = module.params["rename"]
    idp = _get_idp(module, blade, name)

    if state == "absent":
        if idp:
            delete_idp(module, blade)
        module.exit_json(changed=False)
    if idp:
        if rename and rename != name and _get_idp(module, blade, rename):
            msg = "Cannot rename OIDC identity provider {0}: {1} already exists"
            module.fail_json(msg=msg.format(name, rename))
        update_idp(module, blade, idp)
    if rename:
        renamed = _get_idp(module, blade, rename)
        if renamed:
            # The rename already happened on an earlier run; keep the
            # remaining fields of the renamed provider in line with the play.
            update_idp(module, blade, renamed)
    create_idp(module, blade)


if __name__ == "__main__":
    main()
