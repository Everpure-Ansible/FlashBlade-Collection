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
module: purefb_dns
version_added: '1.0.0'
short_description: Configure FlashBlade DNS settings
description:
- Set or erase configuration for the DNS settings.
- Nameservers provided will overwrite any existing nameservers.
- Nameservers may be DNS over HTTPS endpoints validated by a CA certificate
  or certificate group. This requires REST API 2.25 (Purity//FB 4.8.0) or higher.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - Name of the DNS configuration.
    - Default value only supported for management service
    default: management
    type: str
  state:
    description:
    - Set or delete directory service configuration
    default: present
    type: str
    choices: [ absent, present ]
  domain:
    description:
    - Domain suffix to be appended when performing DNS lookups.
    type: str
  nameservers:
    description:
    - List of up to 3 unique DNS servers.
    - Each entry is an IPv4 or IPv6 address, or a DNS over HTTPS endpoint of
      the form C(https://<ip>[:<port>]/<path>). HTTPS endpoints must use an
      IP address, not a hostname, and a configuration uses either all HTTPS
      endpoints or all IP addresses, never a mix.
    - HTTPS endpoints require REST API 2.25 (Purity//FB 4.8.0) or higher and
      one of I(ca_certificate) or I(ca_certificate_group).
    type: list
    elements: str
  ca_certificate:
    description:
    - Name of an existing certificate used to validate DNS over HTTPS nameservers.
    - Only valid when every nameserver is an C(https://) endpoint. The array
      drops the reference when the nameservers revert to IP addresses.
    - Mutually exclusive with I(ca_certificate_group).
    - Requires REST API 2.25 (Purity//FB 4.8.0) or higher.
    type: str
    version_added: '1.30.0'
  ca_certificate_group:
    description:
    - Name of an existing certificate group used to validate DNS over HTTPS nameservers.
    - Only valid when every nameserver is an C(https://) endpoint. The array
      drops the reference when the nameservers revert to IP addresses.
    - Mutually exclusive with I(ca_certificate).
    - Requires REST API 2.25 (Purity//FB 4.8.0) or higher.
    type: str
    version_added: '1.30.0'
  source:
    description:
    - A virtual network interface (vip)
    - The network interfaces must have a I(service) value of I(data)
    type: str
  service:
    description:
    - The service utilizing the DNS configuration.
    - Only aplicable when creating a new DNS configuration.
    type: str
    choices: [ management, data ]
    default: data
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Set managemnt DNS settings
  everpure.flashblade.purefb_dns:
    domain: everpuredata.com
    nameservers:
      - 8.8.8.8
      - 8.8.4.4
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Delete exisitng management DNS settings
  everpure.flashblade.purefb_dns:
    state: absent
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Set DNS settings with alternate name
  everpure.flashblade.purefb_dns:
    name: server1
    domain: everpuredata.com
    nameservers:
      - 8.8.8.8
      - 8.8.4.4
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Use DNS over HTTPS validated by an imported CA certificate
  everpure.flashblade.purefb_dns:
    name: server1
    domain: everpuredata.com
    nameservers:
      - https://192.0.2.53/dns-query
    ca_certificate: doh-ca
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
"""

RETURN = r"""
"""

import socket

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import Dns, DnsPost, Reference
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
    remove_duplicates,
)

NON_MGMT_DNS = "2.15"
DOH_API_VERSION = "2.25"

# Module option -> Dns field. Both are references to an object that must
# already exist on the array, so the module sends Reference(name=...) and
# compares against the name on the current configuration.
REFERENCE_PARAMS = {
    "ca_certificate": "ca_certificate",
    "ca_certificate_group": "ca_certificate_group",
}


def _reference_name(obj, field):
    """Name held by a reference field on a DNS configuration, or None."""
    return getattr(getattr(obj, field, None), "name", None)


def _ca_param(module):
    """Name of the CA option the caller set, or None."""
    for param in REFERENCE_PARAMS:
        if module.params[param]:
            return param
    return None


def _is_https(nameserver):
    return str(nameserver).lower().startswith("https://")


def _all_https(nameservers):
    """True when there is at least one nameserver and all are https:// endpoints."""
    return bool(nameservers) and all(_is_https(ns) for ns in nameservers)


def _https_host(nameserver):
    """Host part of an https:// nameserver, without scheme, port or path."""
    authority = nameserver[len("https://") :].split("/", 1)[0]
    if authority.startswith("["):
        return authority[1:].split("]", 1)[0]
    if authority.count(":") == 1:
        return authority.split(":", 1)[0]
    return authority


def _is_ip_address(host):
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            socket.inet_pton(family, host)
            return True
        except (socket.error, ValueError):
            continue
    return False


def _validate_nameservers(module, nameservers):
    """Fail on nameserver lists the array rejects.

    The array refuses a mix of https:// endpoints and IP addresses, and an
    https:// endpoint whose host is a hostname rather than an IP address.
    """
    https = [ns for ns in nameservers if _is_https(ns)]
    if https and len(https) != len(nameservers):
        module.fail_json(
            msg="nameservers must be either all https:// endpoints "
            "or all IP addresses, not a mix."
        )
    for nameserver in https:
        if not _is_ip_address(_https_host(nameserver)):
            module.fail_json(
                msg="https nameserver {0} must use an IP address, "
                "not a hostname.".format(nameserver)
            )


def _fail_if_ca_without_https(module, ca_param, nameservers):
    """Fail when a CA option is set but the nameservers are not all https://.

    The array rejects a CA reference on a configuration whose nameservers
    are IP addresses.
    """
    if ca_param and not _all_https(nameservers):
        module.fail_json(
            msg="{0} may only be set when all nameservers are "
            "https:// endpoints.".format(ca_param)
        )


def _check_certificate(module, blade, param):
    """Fail unless the named certificate or certificate group exists."""
    name = module.params[param]
    if not name:
        return
    if param == "ca_certificate_group":
        res = blade.get_certificate_groups(names=[name])
        kind = "Certificate group"
    else:
        res = blade.get_certificates(names=[name])
        kind = "Certificate"
    if res.status_code != 200:
        module.fail_json(msg="{0} {1} does not exist.".format(kind, name))


def _get_source(module, blade):
    res = blade.get_network_interfaces(names=[module.params["source"]])
    return bool(res.status_code == 200)


def delete_dns(module, blade):
    """Delete DNS settings"""
    changed = False
    current_dns = list(blade.get_dns().items)[0]
    if getattr(current_dns, "domain", None) in ["", None] and getattr(
        current_dns, "nameservers", None
    ) in [[""], None]:
        module.exit_json(changed=changed)
    else:
        changed = True
        if not module.check_mode:
            res = blade.delete_dns(names=["management"])
        if res.status_code != 200:
            module.fail_json(
                msg="Delete DNS settigs failed. Error: {0}".format(
                    get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def create_dns(module, blade):
    """Set DNS settings"""
    changed = False
    current_dns = list(blade.get_dns().items)[0]
    if current_dns["domain"] != module.params["domain"] or sorted(
        module.params["nameservers"]
    ) != sorted(current_dns["nameservers"]):
        changed = True
        if not module.check_mode:
            res = blade.post_dns(
                names=["management"],
                dns=DnsPost(
                    domain=module.params["domain"],
                    nameservers=module.params["nameservers"][0:3],
                ),
            )
        if res.status_code != 200:
            module.fail_json(
                msg="Set DNS settings failed. Error: {0}".format(get_error_message(res))
            )
    module.exit_json(changed=changed)


def update_multi_dns(module, blade):
    """Update a DNS configuration"""
    changed = False
    current_dns = list(blade.get_dns(names=[module.params["name"]]).items)[0]
    domain = current_dns.domain
    nameservers = current_dns.nameservers
    if module.params["domain"] and current_dns.domain != module.params["domain"]:
        domain = module.params["domain"]
        changed = True
    if module.params["nameservers"] and sorted(current_dns.nameservers) != sorted(
        module.params["nameservers"]
    ):
        nameservers = module.params["nameservers"]
        changed = True
    current_source = ""
    if current_dns.sources:
        current_source = getattr(current_dns.sources[0], "name", "") or ""
    if (
        module.params["source"] is not None
        and current_source != module.params["source"]
    ):
        changed = True
    # The array rejects a CA reference unless every nameserver is https://,
    # and a PATCH that changes the CA must carry the nameservers as well.
    # When the caller sets no CA, the current reference is carried over so a
    # domain-only change on an https configuration keeps its certificate; the
    # array drops the reference itself when the nameservers revert to IPs.
    ca_reference = None
    ca_param = _ca_param(module)
    if ca_param:
        _fail_if_ca_without_https(module, ca_param, nameservers)
        wanted = module.params[ca_param]
        if wanted != _reference_name(current_dns, REFERENCE_PARAMS[ca_param]):
            changed = True
        ca_reference = (REFERENCE_PARAMS[ca_param], wanted)
    elif _all_https(nameservers):
        for field in REFERENCE_PARAMS.values():
            current_name = _reference_name(current_dns, field)
            if current_name:
                ca_reference = (field, current_name)
    if changed and not module.check_mode:
        # Only send sources when the caller specified one, otherwise an
        # omitted source would be sent as a reference with no name.
        new_dns = {"domain": domain, "nameservers": nameservers}
        if module.params["source"] is not None:
            new_dns["sources"] = [Reference(name=module.params["source"])]
        if ca_reference:
            new_dns[ca_reference[0]] = Reference(name=ca_reference[1])
        res = blade.patch_dns(names=[module.params["name"]], dns=Dns(**new_dns))
        if res.status_code != 200:
            module.fail_json(
                msg="Update to DNS configuration {0} failed. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def delete_multi_dns(module, blade):
    """Delete a DNS configuration"""
    changed = True
    if module.params["name"] == "management":
        module.fail_json(msg="Management DNS configuration cannot be deleted")
    else:
        if not module.check_mode:
            res = blade.delete_dns(names=[module.params["name"]])
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to delete DNS configuration {0}. Error: {1}".format(
                        module.params["name"], get_error_message(res)
                    )
                )
    module.exit_json(changed=changed)


def create_multi_dns(module, blade):
    """Create a DNS configuration"""
    changed = True
    ca_param = _ca_param(module)
    _fail_if_ca_without_https(module, ca_param, module.params["nameservers"])
    if not module.check_mode:
        new_dns = {
            "services": [module.params["service"]],
            "domain": module.params["domain"],
            "nameservers": module.params["nameservers"],
        }
        if module.params["service"] == "data" and module.params["source"]:
            new_dns["sources"] = [Reference(name=module.params["source"].lower())]
        if ca_param:
            new_dns[REFERENCE_PARAMS[ca_param]] = Reference(
                name=module.params[ca_param]
            )
        res = blade.post_dns(names=[module.params["name"]], dns=DnsPost(**new_dns))
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to create {0} DNS configuration {1}. Error: {2}".format(
                    module.params["service"],
                    module.params["name"],
                    get_error_message(res),
                )
            )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(type="str", default="present", choices=["absent", "present"]),
            name=dict(type="str", default="management"),
            domain=dict(type="str"),
            source=dict(type="str"),
            nameservers=dict(type="list", elements="str"),
            service=dict(type="str", choices=["management", "data"], default="data"),
            ca_certificate=dict(type="str"),
            ca_certificate_group=dict(type="str"),
        )
    )

    module = AnsibleModule(
        argument_spec,
        supports_check_mode=True,
        mutually_exclusive=[["ca_certificate", "ca_certificate_group"]],
    )

    state = module.params["state"]
    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if module.params["nameservers"]:
        module.params["nameservers"] = remove_duplicates(module.params["nameservers"])

    if state == "present":
        ca_param = _ca_param(module)
        nameservers = module.params["nameservers"]
        if nameservers:
            _validate_nameservers(module, nameservers)
        if (ca_param or _all_https(nameservers)) and LooseVersion(
            DOH_API_VERSION
        ) > LooseVersion(api_version):
            module.fail_json(
                msg="DNS over HTTPS (https:// nameservers, ca_certificate and "
                "ca_certificate_group) requires REST API {0} "
                "(Purity//FB 4.8.0) or higher.".format(DOH_API_VERSION)
            )
        if nameservers:
            _fail_if_ca_without_https(module, ca_param, nameservers)
        if ca_param:
            _check_certificate(module, blade, ca_param)

    if LooseVersion(NON_MGMT_DNS) <= LooseVersion(api_version):
        configs = list(blade.get_dns().items)
        exists = False
        for config in configs:
            if config.name == module.params["name"]:
                exists = True
        if module.params["source"] and not _get_source(module, blade):
            module.fail_json(
                msg="Specified VIP {0} does not exist.".format(module.params["source"])
            )
        if state == "present" and exists:
            update_multi_dns(module, blade)
        elif state == "present" and not exists:
            if not module.params["nameservers"] and not module.params["domain"]:
                module.fail_json(
                    msg="DNS configuration must have at least one domain "
                    "or nameserver defined."
                )
            create_multi_dns(module, blade)
        elif exists and state == "absent":
            delete_multi_dns(module, blade)
        else:
            module.exit_json(changed=False)
    else:
        if state == "absent":
            delete_dns(module, blade)
        elif state == "present":
            if not module.params["domain"] or not module.params["nameservers"]:
                module.fail_json(
                    msg="DNS configuration must have at least one domain "
                    "or nameserver defined."
                )
            create_dns(module, blade)
        else:
            module.exit_json(changed=False)


if __name__ == "__main__":
    main()
