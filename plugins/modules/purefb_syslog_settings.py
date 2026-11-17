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
module: purefb_syslog_settings
version_added: '1.30.0'
short_description: Manage FlashBlade syslog server settings
description:
- Manage the CA certificate, or CA certificate group, that a FlashBlade uses
  to validate syslog servers reached over TLS (C(tls://) servers created with
  M(everpure.flashblade.purefb_syslog)).
- The settings object is an array-wide singleton that always exists; the
  module only changes which certificate or certificate group it references.
- Requires FlashBlade REST API version 2.0 or later (Purity//FB 3.2.0+).
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - Name of the syslog server settings object.
    - When omitted the module operates on the array's single settings object
      (named C(management) on current arrays) and fails if the array returns
      more than one.
    type: str
  state:
    description:
    - C(present) applies the requested CA certificate or certificate group.
    - C(absent) clears whichever of the two the array currently references;
      I(ca_certificate) and I(ca_certificate_group) are ignored.
    type: str
    default: present
    choices: [ absent, present ]
  ca_certificate:
    description:
    - Name of an existing certificate on the array used to validate the
      syslog servers. Use M(everpure.flashblade.purefb_certs) to import one.
    - An empty string clears a configured CA certificate.
    - The array references at most one of a CA certificate and a CA
      certificate group; when one is set the module clears the other in the
      same request.
    type: str
  ca_certificate_group:
    description:
    - Name of an existing certificate group on the array whose certificates
      validate the syslog servers. Use M(everpure.flashblade.purefb_certgrp)
      to create one.
    - An empty string clears a configured CA certificate group.
    type: str
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Validate TLS syslog servers against an imported CA certificate
  everpure.flashblade.purefb_syslog_settings:
    ca_certificate: syslog-ca
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Validate TLS syslog servers against a certificate group
  everpure.flashblade.purefb_syslog_settings:
    ca_certificate_group: syslog-ca-group
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Clear a configured CA certificate
  everpure.flashblade.purefb_syslog_settings:
    ca_certificate: ""
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Clear whichever CA certificate or certificate group is configured
  everpure.flashblade.purefb_syslog_settings:
    state: absent
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
"""

RETURN = r"""
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import SyslogServerSettings
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

MIN_REQUIRED_API_VERSION = "2.0"

# Module option -> SyslogServerSettings field. The SDK types both fields as
# plain dicts rather than Reference objects, so the module sends {"name": x}
# and reads the name back out of a dict; {"name": ""} clears a reference.
REFERENCE_PARAMS = {
    "ca_certificate": "ca_certificate",
    "ca_certificate_group": "ca_certificate_group",
}
# The array refuses a PATCH that leaves both references set, so a switch
# clears the other field in the same request.
_OTHER_FIELD = {
    "ca_certificate": "ca_certificate_group",
    "ca_certificate_group": "ca_certificate",
}


def _reference_name(obj, field):
    """Name held by a reference field, or None when it is unset.

    The array returns the references as dicts ({"name": None, ...} when
    unset); tolerate reference objects as well.
    """
    ref = getattr(obj, field, None)
    if isinstance(ref, dict):
        return ref.get("name") or None
    return getattr(ref, "name", None) or None


def get_settings(module, blade):
    """Return the syslog server settings object the module operates on."""
    if module.params["name"]:
        res = blade.get_syslog_servers_settings(names=[module.params["name"]])
    else:
        res = blade.get_syslog_servers_settings()
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read syslog server settings. Error: {0}".format(
                get_error_message(res)
            )
        )
    items = list(res.items)
    if not items:
        module.fail_json(msg="No syslog server settings object found.")
    if len(items) > 1:
        module.fail_json(
            msg="More than one syslog server settings object exists ({0}). "
            "Specify name.".format(", ".join(item.name for item in items))
        )
    return items[0]


def _check_reference(module, blade, param, name):
    """Fail unless the named certificate or certificate group exists."""
    if param == "ca_certificate_group":
        res = blade.get_certificate_groups(names=[name])
        kind = "Certificate group"
    else:
        res = blade.get_certificates(names=[name])
        kind = "Certificate"
    if res.status_code != 200:
        module.fail_json(
            msg="{0} {1} does not exist. Error: {2}".format(
                kind, name, get_error_message(res)
            )
        )


def _wanted_changes(module, blade, settings):
    """Return the SyslogServerSettings fields that differ from the array."""
    patch_fields = {}
    if module.params["state"] == "absent":
        for field in REFERENCE_PARAMS.values():
            if _reference_name(settings, field):
                patch_fields[field] = {"name": ""}
        return patch_fields
    for param, field in REFERENCE_PARAMS.items():
        wanted = module.params[param]
        if wanted is None:
            continue
        current = _reference_name(settings, field)
        if wanted == "":
            if current:
                patch_fields[field] = {"name": ""}
        elif wanted != current:
            _check_reference(module, blade, param, wanted)
            patch_fields[field] = {"name": wanted}
            other = _OTHER_FIELD[field]
            if _reference_name(settings, other):
                patch_fields[other] = {"name": ""}
    return patch_fields


def update_settings(module, blade, settings):
    """PATCH only the references that differ from the current settings."""
    patch_fields = _wanted_changes(module, blade, settings)
    changed = bool(patch_fields)
    if changed and not module.check_mode:
        res = blade.patch_syslog_servers_settings(
            names=[settings.name],
            syslog_server_settings=SyslogServerSettings(**patch_fields),
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Updating syslog server settings {0} failed. Error: {1}".format(
                    settings.name, get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str"),
            state=dict(type="str", default="present", choices=["absent", "present"]),
            ca_certificate=dict(type="str"),
            ca_certificate_group=dict(type="str"),
        )
    )

    module = AnsibleModule(
        argument_spec,
        mutually_exclusive=[["ca_certificate", "ca_certificate_group"]],
        supports_check_mode=True,
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

    settings = get_settings(module, blade)
    update_settings(module, blade, settings)


if __name__ == "__main__":
    main()
