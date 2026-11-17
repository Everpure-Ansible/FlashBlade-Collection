#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2024, Simon Dodsley (simon@everpuredata.com)
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
module: purefb_saml
version_added: '1.19.0'
short_description: Manage FlashBlade SAML2 service and identity providers
description:
- Enable or disable FlashBlade SAML2 providers
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - Name of the SAML2 identity provider (IdP)
    type: str
    required: true
  state:
    description:
    - Define whether the API client should exist or not, or test.
    default: present
    choices: [ absent, present, test ]
    type: str
  url:
    description:
    - The URL of the identity provider
    type: str
  entity_id:
    description:
    - A globally unique name for the identity provider
    type: str
    version_added: '1.21.0'
  array_url:
    description:
    - The URL of the FlashBlade
    type: str
  metadata_url:
    description:
    - The URL of the identity provider metadata
    type: str
  enabled:
    description:
    - Defines the enabled state of the identity provider.
    - When not set the identity provider is created disabled and the current
      state is kept on update.
    type: bool
  encrypt_asserts:
    description:
    - If set to true, SAML assertions will be encrypted by the identity provider.
    - When not set the array default of C(false) applies on creation and the
      current value is kept on update.
    type: bool
  sign_request:
    description:
    - If set to true, SAML requests will be signed by the service provider.
    - When not set the array default of C(false) applies on creation and the
      current value is kept on update.
    type: bool
  x509_cert:
    description:
    - Name of the certificate, managed by M(everpure.flashblade.purefb_certs), that the
      service provider uses to verify the SAML response signature from the identity provider.
    - The array stores a reference to the certificate, not the certificate itself.
    type: str
  decryption_credential:
    description:
    - The credential used by the service provider to decrypt encrypted SAML assertions from the identity provider
    type: str
  signing_credential:
    description:
    - The credential used by the service provider to sign SAML requests
    type: str
  services:
    description:
    - Services that the SAML2 SSO authentication is used for.
    - When not set the array default of C(management) applies on creation and the
      current value is kept on update.
    - The array requires I(services) and I(binding) to be set together, so when one
      is given the module sends the other as well.
    - The array allows one identity provider per service and validates the
      combination with I(binding), accepting C(management) with C(http-redirect)
      and C(object) with C(none).
    - Requires REST 2.17 or higher.
    type: list
    elements: str
    choices: [ management, object ]
    version_added: '1.30.0'
  binding:
    description:
    - SAML2 binding used for the request from the FlashBlade to the identity provider.
    - When not set the array default of C(http-redirect) applies on creation and the
      current value is kept on update.
    - Sent together with I(services) whenever either is given, as the array requires.
    - Use C(none) for the C(object) service.
    - Requires REST 2.17 or higher.
    type: str
    choices: [ http-redirect, none ]
    version_added: '1.30.0'
  metadata_url_ca_certificate:
    description:
    - Name of the CA certificate used to validate the authenticity of the identity
      provider server when I(metadata_url) is fetched.
    - Mutually exclusive with I(metadata_url_ca_certificate_group), which is cleared
      when this is set.
    - Requires REST 2.17 or higher.
    type: str
    version_added: '1.30.0'
  metadata_url_ca_certificate_group:
    description:
    - Name of a certificate group containing CA certificates that can validate the
      authenticity of the identity provider server when I(metadata_url) is fetched.
      The group must contain at least one certificate.
    - Mutually exclusive with I(metadata_url_ca_certificate), which is cleared when
      this is set.
    - Requires REST 2.17 or higher.
    type: str
    version_added: '1.30.0'
  sp_entity_id:
    description:
    - Service provider entity ID. When not set the array generates one.
    - All members of a fleet must use the same service provider entity ID for SAML
      users to operate on remote arrays.
    - Requires REST 2.24 or higher.
    type: str
    version_added: '1.30.0'
  trust_other_saml_sps_in_fleet:
    description:
    - When C(false) the array verifies that the source and target arrays have matching
      SAML configurations (same identity provider and same service provider entity ID)
      before allowing remote command execution in a fleet.
    - When C(true) remote command execution is allowed from other fleet members without
      verifying SAML configuration consistency. Keep this C(false) unless there is a
      specific need.
    - Only available when I(services) includes C(management).
    - Requires REST 2.24 or higher.
    type: bool
    version_added: '1.30.0'
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Create (disabled) SAML2 SSO with only metadata URL
  everpure.flashblade.purefb_saml:
    name: myIDP
    array_url: "https://10.10.10.2"
    metadata_url: "https://myidp.acme.com/adfs/ls"
    x509_cert: idp-signing-cert
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Create SAML2 SSO for the management service with a fleet-wide SP entity ID
  everpure.flashblade.purefb_saml:
    name: myIDP
    array_url: "https://10.10.10.2"
    metadata_url: "https://myidp.acme.com/adfs/ls"
    metadata_url_ca_certificate: idp-ca
    services:
      - management
    sp_entity_id: "https://sso.acme.com/flashblade-fleet"
    trust_other_saml_sps_in_fleet: false
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Create SAML2 SSO for the object service
  everpure.flashblade.purefb_saml:
    name: myObjectIDP
    array_url: "https://10.10.10.2"
    url: "https://myidp.acme.com/sso"
    entity_id: "https://myidp.acme.com/idp"
    x509_cert: idp-signing-cert
    services:
      - object
    binding: none
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Enable SAML2 SSO
  everpure.flashblade.purefb_saml:
    name: myIDP
    enabled: true
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Delete SAML2 SSO
  everpure.flashblade.purefb_saml:
    state: absent
    name: myIDP
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
"""

RETURN = r"""
prn:
  description: Pure Resource Name of the identity provider, for use in object policies.
  returned: when state is present and the provider exists
  type: str
  sample: "prn::iam:array-id/local::saml-provider/myIDP"
sp_entity_id:
  description: Service provider entity ID, either the configured value or the array generated one.
  returned: when state is present and the provider exists
  type: str
  sample: "https://10.10.10.2/saml2/service-provider-metadata/myIDP"
test_response:
  description: Results of the SAML2 configuration tests.
  returned: when state is test
  type: list
  elements: dict
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        Saml2Sso,
        Saml2SsoPost,
        Saml2SsoSp,
        Saml2SsoIdp,
        Saml2SsoManagement,
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
from ansible_collections.everpure.flashblade.plugins.module_utils.common import (
    get_error_message,
    get_rest_api_version,
)

MIN_REQUIRED_API_VERSION = "2.15"
TEST_API_VERSION = "2.16"
# services, binding and the metadata URL CA references
SERVICES_API_VERSION = "2.17"
# writable service provider entity ID and the fleet trust flag
FLEET_API_VERSION = "2.24"

GATED_OPTIONS = (
    ("services", SERVICES_API_VERSION),
    ("binding", SERVICES_API_VERSION),
    ("metadata_url_ca_certificate", SERVICES_API_VERSION),
    ("metadata_url_ca_certificate_group", SERVICES_API_VERSION),
    ("sp_entity_id", FLEET_API_VERSION),
    ("trust_other_saml_sps_in_fleet", FLEET_API_VERSION),
)


def _check_option_versions(module, api_version):
    """Refuse options the array's REST version does not support, before any write"""
    for option, required in GATED_OPTIONS:
        if module.params[option] is not None and LooseVersion(required) > LooseVersion(
            api_version
        ):
            module.fail_json(
                msg="Option {0} requires FlashBlade REST version {1} or higher. "
                "Array REST version is {2}".format(option, required, api_version)
            )


def _ref_name(obj, attr):
    """Name held by a reference sub-object, or None when unset"""
    return getattr(getattr(obj, attr, None), "name", None)


def _ref(name):
    """ReferenceWritable for a name, or None so the field is omitted"""
    if name:
        return ReferenceWritable(name=name)
    return None


def _ref_update(new_name, old_name):
    """ReferenceWritable for an update: the new name, an empty name to clear a
    reference the array holds, or None so the field is omitted"""
    if new_name:
        return ReferenceWritable(name=new_name)
    if old_name:
        return ReferenceWritable(name="")
    return None


def _effective_services(module, current_idp):
    """Services the provider will have after this run"""
    if module.params["services"] is not None:
        return module.params["services"]
    if current_idp is not None:
        return list(getattr(current_idp, "services", None) or ["management"])
    return ["management"]


def _facts_from(idp):
    """Return values a playbook needs to configure the IdP side"""
    return {
        "prn": getattr(idp, "prn", None),
        "sp_entity_id": getattr(getattr(idp, "sp", None), "entity_id", None),
    }


def _idp_facts(blade, name):
    """Read the provider back and return its facts, or {} if it cannot be read"""
    res = blade.get_sso_saml2_idps(names=[name])
    if res.status_code != 200:
        return {}
    items = list(res.items)
    if not items:
        return {}
    return _facts_from(items[0])


def test_saml(module, blade):
    """Test SAML2 IdP configuration"""
    test_response = []
    response = list(blade.get_sso_saml2_idps_test(names=[module.params["name"]]).items)
    for component in response:
        if component.enabled:
            enabled = "true"
        else:
            enabled = "false"
        if component.success:
            success = "true"
        else:
            success = "false"
        test_response.append(
            {
                "component_address": component.component_address,
                "component_name": component.component_name,
                "description": component.description,
                "destination": component.destination,
                "enabled": enabled,
                "result_details": getattr(component, "result_details", ""),
                "success": success,
                "test_type": component.test_type,
                "resource_name": component.resource.name,
            }
        )
    module.exit_json(changed=False, test_response=test_response)


def delete_saml(module, blade):
    """Delete SSO SAML2 IdP"""
    changed = True
    if not module.check_mode:
        res = blade.delete_sso_saml2_idps(names=[module.params["name"]])
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete SAML2 IdP {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def update_saml(module, blade, current_idp):
    """Update SSO SAML2 IdP"""
    changed = False
    params = module.params
    old_idp = {
        "array_url": current_idp.array_url,
        "enabled": current_idp.enabled,
        "sp_sign_cred": _ref_name(current_idp.sp, "signing_credential"),
        "sp_decrypt_cred": _ref_name(current_idp.sp, "decryption_credential"),
        "sp_entity_id": getattr(current_idp.sp, "entity_id", None),
        "id_metadata": current_idp.idp.metadata_url,
        "id_entity": getattr(current_idp.idp, "entity_id", None),
        "id_url": getattr(current_idp.idp, "url", None),
        "id_sign_enabled": current_idp.idp.sign_request_enabled,
        "id_encrypt_enabled": current_idp.idp.encrypt_assertion_enabled,
        "id_cert": _ref_name(current_idp.idp, "verification_certificate"),
        "id_ca_cert": _ref_name(current_idp.idp, "metadata_url_ca_certificate"),
        "id_ca_group": _ref_name(current_idp.idp, "metadata_url_ca_certificate_group"),
        "services": sorted(getattr(current_idp, "services", None) or []),
        "binding": getattr(current_idp, "binding", None),
        "trust_fleet": getattr(
            getattr(current_idp, "management", None),
            "trust_other_saml_sps_in_fleet",
            None,
        ),
    }
    new_idp = dict(old_idp)
    # string options: an unset option keeps the current value
    for key, option in (
        ("array_url", "array_url"),
        ("id_url", "url"),
        ("id_entity", "entity_id"),
        ("id_metadata", "metadata_url"),
        ("sp_sign_cred", "signing_credential"),
        ("sp_decrypt_cred", "decryption_credential"),
        ("sp_entity_id", "sp_entity_id"),
        ("id_cert", "x509_cert"),
        ("id_ca_cert", "metadata_url_ca_certificate"),
        ("id_ca_group", "metadata_url_ca_certificate_group"),
        ("binding", "binding"),
    ):
        if params[option]:
            new_idp[key] = params[option]
    # the array holds either a CA certificate or a CA certificate group and
    # refuses a PATCH naming both, so setting one clears the other
    if params["metadata_url_ca_certificate"]:
        new_idp["id_ca_group"] = None
    if params["metadata_url_ca_certificate_group"]:
        new_idp["id_ca_cert"] = None
    # boolean options: an unset option keeps the current value, so a task that
    # changes another option never disables the provider or turns off signing
    for key, option in (
        ("enabled", "enabled"),
        ("id_sign_enabled", "sign_request"),
        ("id_encrypt_enabled", "encrypt_asserts"),
        ("trust_fleet", "trust_other_saml_sps_in_fleet"),
    ):
        if params[option] is not None:
            new_idp[key] = params[option]
    if params["services"] is not None:
        new_idp["services"] = sorted(params["services"])
    if old_idp != new_idp:
        changed = True
        if not module.check_mode:
            sp_kwargs = {
                "decryption_credential": _ref(new_idp["sp_decrypt_cred"]),
                "signing_credential": _ref(new_idp["sp_sign_cred"]),
            }
            # only pin the SP entity ID when asked to, otherwise the array keeps
            # generating it from the array URL
            if params["sp_entity_id"]:
                sp_kwargs["entity_id"] = new_idp["sp_entity_id"]
            idp_kwargs = {
                "url": new_idp["id_url"],
                "metadata_url": new_idp["id_metadata"],
                "entity_id": new_idp["id_entity"],
                "verification_certificate": _ref(new_idp["id_cert"]),
                "metadata_url_ca_certificate": _ref_update(
                    new_idp["id_ca_cert"], old_idp["id_ca_cert"]
                ),
                "metadata_url_ca_certificate_group": _ref_update(
                    new_idp["id_ca_group"], old_idp["id_ca_group"]
                ),
            }
            # the boolean flags are sent only when the task gives them
            if params["sign_request"] is not None:
                idp_kwargs["sign_request_enabled"] = new_idp["id_sign_enabled"]
            if params["encrypt_asserts"] is not None:
                idp_kwargs["encrypt_assertion_enabled"] = new_idp["id_encrypt_enabled"]
            body_kwargs = {
                "array_url": new_idp["array_url"],
                "idp": Saml2SsoIdp(**idp_kwargs),
                "sp": Saml2SsoSp(**sp_kwargs),
            }
            if params["enabled"] is not None:
                body_kwargs["enabled"] = new_idp["enabled"]
            # the array requires services and binding to be sent together, so a
            # change to one carries the current value of the other
            if params["services"] is not None or params["binding"]:
                body_kwargs["services"] = new_idp["services"]
                body_kwargs["binding"] = new_idp["binding"]
            if params["trust_other_saml_sps_in_fleet"] is not None:
                body_kwargs["management"] = Saml2SsoManagement(
                    trust_other_saml_sps_in_fleet=new_idp["trust_fleet"]
                )
            res = blade.patch_sso_saml2_idps(
                idp=Saml2Sso(**body_kwargs),
                names=[params["name"]],
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to update SAML2 IdP {0}. Error: {1}".format(
                        params["name"], get_error_message(res)
                    )
                )
            facts = _idp_facts(blade, params["name"])
        else:
            facts = _facts_from(current_idp)
    else:
        facts = _facts_from(current_idp)
    module.exit_json(changed=changed, **facts)


def create_saml(module, blade):
    """Create SAML2 IdP"""
    changed = True
    params = module.params
    facts = {}
    if not module.check_mode:
        sp_kwargs = {
            "decryption_credential": _ref(params["decryption_credential"]),
            "signing_credential": _ref(params["signing_credential"]),
        }
        if params["sp_entity_id"]:
            sp_kwargs["entity_id"] = params["sp_entity_id"]
        idp = Saml2SsoIdp(
            url=params["url"],
            metadata_url=params["metadata_url"],
            entity_id=params["entity_id"],
            sign_request_enabled=params["sign_request"],
            encrypt_assertion_enabled=params["encrypt_asserts"],
            verification_certificate=_ref(params["x509_cert"]),
            metadata_url_ca_certificate=_ref(params["metadata_url_ca_certificate"]),
            metadata_url_ca_certificate_group=_ref(
                params["metadata_url_ca_certificate_group"]
            ),
        )
        body_kwargs = {
            "array_url": params["array_url"],
            "idp": idp,
            "sp": Saml2SsoSp(**sp_kwargs),
        }
        # the array requires services and binding to be sent together, so the
        # array default stands in for the one not given
        if params["services"] is not None or params["binding"]:
            body_kwargs["services"] = params["services"] or ["management"]
            body_kwargs["binding"] = params["binding"] or "http-redirect"
        if params["trust_other_saml_sps_in_fleet"] is not None:
            body_kwargs["management"] = Saml2SsoManagement(
                trust_other_saml_sps_in_fleet=params["trust_other_saml_sps_in_fleet"]
            )
        res = blade.post_sso_saml2_idps(
            idp=Saml2SsoPost(**body_kwargs),
            names=[params["name"]],
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to create SAML2 Identity Provider {0}. Error message: {1}".format(
                    params["name"], get_error_message(res)
                )
            )
        if params["enabled"]:
            res = blade.patch_sso_saml2_idps(
                idp=Saml2Sso(enabled=params["enabled"]),
                names=[params["name"]],
            )
            if res.status_code != 200:
                blade.delete_sso_saml2_idps(names=[params["name"]])
                module.fail_json(
                    msg="Failed to create SAML2 Identity Provider {0}. Error message: {1}".format(
                        params["name"], get_error_message(res)
                    )
                )
        facts = _idp_facts(blade, params["name"])

    module.exit_json(changed=changed, **facts)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(
                type="str", default="present", choices=["absent", "present", "test"]
            ),
            name=dict(type="str", required=True),
            url=dict(type="str"),
            array_url=dict(type="str"),
            entity_id=dict(type="str"),
            metadata_url=dict(type="str"),
            x509_cert=dict(type="str"),
            signing_credential=dict(type="str"),
            decryption_credential=dict(type="str"),
            enabled=dict(type="bool"),
            encrypt_asserts=dict(type="bool"),
            sign_request=dict(type="bool"),
            services=dict(
                type="list", elements="str", choices=["management", "object"]
            ),
            binding=dict(type="str", choices=["http-redirect", "none"]),
            metadata_url_ca_certificate=dict(type="str"),
            metadata_url_ca_certificate_group=dict(type="str"),
            sp_entity_id=dict(type="str"),
            trust_other_saml_sps_in_fleet=dict(type="bool"),
        )
    )

    required_if = [
        ["encrypt_asserts", True, ["decryption_credential"]],
        ["sign_request", True, ["signing_credential"]],
    ]
    mutually_exclusive = [
        ["metadata_url_ca_certificate", "metadata_url_ca_certificate_group"],
    ]

    module = AnsibleModule(
        argument_spec,
        supports_check_mode=True,
        required_if=required_if,
        mutually_exclusive=mutually_exclusive,
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    blade = get_system(module)
    api_version = get_rest_api_version(blade)

    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg="FlashBlade REST version not supported. "
            "Minimum version required: {0}".format(MIN_REQUIRED_API_VERSION)
        )
    state = module.params["state"]
    if state == "test" and LooseVersion(TEST_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg="FlashBlade REST version not supported for SAML2 testing. "
            "Minimum version required: {0}".format(TEST_API_VERSION)
        )
    _check_option_versions(module, api_version)
    if module.params["services"] is not None and not module.params["services"]:
        module.fail_json(msg="services must contain at least one of management, object")

    res = blade.get_sso_saml2_idps(names=[module.params["name"]])
    current_idp = None
    if res.status_code == 200:
        items = list(res.items)
        if items:
            current_idp = items[0]
    exists = current_idp is not None

    if (
        state == "present"
        and module.params["trust_other_saml_sps_in_fleet"] is not None
        and "management" not in _effective_services(module, current_idp)
    ):
        module.fail_json(
            msg="trust_other_saml_sps_in_fleet is only available when "
            "services includes management"
        )

    if not exists and state == "present":
        create_saml(module, blade)
    elif exists and state == "present":
        update_saml(module, blade, current_idp)
    elif exists and state == "absent":
        delete_saml(module, blade)
    elif exists and state == "test":
        test_saml(module, blade)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
