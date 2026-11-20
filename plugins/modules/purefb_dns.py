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
- A DNS configuration in a realm is named C(realm::name). Its I(source),
  I(ca_certificate) and I(ca_certificate_group) are objects of the same
  realm and carry the same prefix.
- An array-level DNS configuration can be shared with a realm using
  M(everpure.flashblade.purefb_resource_access). It keeps its name, without
  a realm prefix.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - Name of the DNS configuration.
    - Default value only supported for management service
    - A configuration in a realm is named C(realm::name). It supports only
      the C(data) service and needs a I(source) when it is created.
    - A name without a realm prefix is an array-level configuration. A
      realm-scoped administrator must use the realm-qualified name; a bare
      name is not placed in, or resolved to, the administrator's realm.
    - The array matches names without regard to case, and so does the module.
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
    - A configuration in a realm takes a certificate of the same realm,
      named C(realm::name).
    - The array takes this reference only in the spelling it stored, so the
      module sends the name as the array returns it, whatever the case given.
    - Requires REST API 2.25 (Purity//FB 4.8.0) or higher.
    type: str
    version_added: '1.30.0'
  ca_certificate_group:
    description:
    - Name of an existing certificate group used to validate DNS over HTTPS nameservers.
    - Only valid when every nameserver is an C(https://) endpoint. The array
      drops the reference when the nameservers revert to IP addresses.
    - Mutually exclusive with I(ca_certificate).
    - A configuration in a realm takes a certificate group of the same
      realm, named C(realm::name).
    - The array takes this reference only in the spelling it stored, so the
      module sends the name as the array returns it, whatever the case given.
    - Requires REST API 2.25 (Purity//FB 4.8.0) or higher.
    type: str
    version_added: '1.30.0'
  source:
    description:
    - A virtual network interface (vip)
    - The network interface of an array-level configuration must have a
      I(service) value of I(data).
    - A configuration and its source must be in the same realm, or both at
      array level. A configuration in a realm takes a network interface of
      that realm, named C(realm::name), normally the C(egress-only) interface
      of the realm.
    - A configuration in a realm needs a source when it is created, and the
      module does not clear it, so an empty string is refused for it.
    type: str
  service:
    description:
    - The service utilizing the DNS configuration.
    - Only aplicable when creating a new DNS configuration.
    - A configuration in a realm supports only C(data).
    type: str
    choices: [ management, data ]
    default: data
  context:
    description:
    - Name of fleet member on which to perform the operation.
    - This requires the array receiving the request is a member of a fleet
      and the context name to be a member of the same fleet.
    - Requires REST API 2.25 (Purity//FB 4.8.0) or higher.
    - When set, I(source) is not checked against the array receiving the
      request, because network interface names belong to the fleet member,
      which rejects an unknown interface itself.
    type: str
    default: ""
    version_added: '1.30.0'
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

- name: Set a data DNS configuration on another fleet member
  everpure.flashblade.purefb_dns:
    name: server1
    domain: everpuredata.com
    nameservers:
      - 8.8.8.8
    context: fleet-member-2
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

- name: Create a DNS configuration in realm realm-1 using the realm's egress-only interface
  everpure.flashblade.purefb_dns:
    name: realm-1::dns
    domain: everpuredata.com
    nameservers:
      - 8.8.8.8
    source: realm-1::egress
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


def _realm_of(name):
    """Realm of a realm::name name, empty for an array-level name."""
    return (name or "").rpartition("::")[0]


def _same_name(left, right):
    """True when the array takes both names as one: it ignores their case."""
    return (left or "").lower() == (right or "").lower()


def _find_config(configs, name):
    """The configuration the array holds under this name, or None."""
    for config in configs:
        if _same_name(config.name, name):
            return config
    return None


def _check_realm_references(module):
    """Fail on a reference the array refuses for the realm of the configuration.

    A configuration is in a realm when it is named realm::name. The array
    refuses a source outside the realm of the configuration, in either
    direction ("DNS configuration and it's source must be in the same
    realm."), and for a configuration in a realm a certificate or certificate
    group from outside it ("DNS cannot be changed/created with certificate
    or certificate group from a different realm."). The names carry the
    realm, so this is settled before any request and check mode agrees with
    a real run.
    """
    name = module.params["name"]
    realm = _realm_of(name)
    source = module.params["source"]
    if source and not _same_name(_realm_of(source), realm):
        if realm:
            module.fail_json(
                msg="Source {0} is not in realm {1}. DNS configuration {2} "
                "takes a network interface of its own realm, named "
                "{1}::<interface>.".format(source, realm, name)
            )
        module.fail_json(
            msg="Source {0} is in a realm. DNS configuration {1} is not in a "
            "realm and takes a network interface that is not in one "
            "either.".format(source, name)
        )
    ca_param = _ca_param(module)
    if realm and ca_param and not _same_name(_realm_of(module.params[ca_param]), realm):
        module.fail_json(
            msg="{0} {1} is not in realm {2}. DNS configuration {3} takes a "
            "certificate or certificate group of its own realm, named "
            "{2}::<name>.".format(ca_param, module.params[ca_param], realm, name)
        )


def _check_realm_source(module, exists):
    """Fail when a configuration in a realm would have no source.

    The array refuses to create a configuration in a realm without a source
    ("DNS configuration must have a source when created inside realm.") or
    with another service than data ("Invalid DNS service value. Valid value
    is 'data'."). An existing one is therefore never asked to give its
    source up. Refused in check mode as well.
    """
    name = module.params["name"]
    realm = _realm_of(name)
    if not realm:
        return
    if exists:
        if module.params["source"] == "":
            module.fail_json(
                msg="DNS configuration {0} is in a realm and cannot be left "
                "without a source. Name the network interface of realm {1} "
                "that replaces the current one.".format(name, realm)
            )
        return
    if module.params["service"] != "data":
        module.fail_json(
            msg="DNS configuration {0} is in a realm, where only the data "
            "service is supported.".format(name)
        )
    if not module.params["source"]:
        module.fail_json(
            msg="DNS configuration {0} is in a realm and needs a source when "
            "it is created: a network interface of realm {1}, named "
            "{1}::<interface>.".format(name, realm)
        )


def _fail_reference(module, res, label, kind, name):
    """Fail on a referenced object the array did not return.

    Only "does not exist" means the object is absent, which for an identity
    whose access is limited to a realm also covers an object outside that
    realm. Any other answer is reported as the array gave it.
    """
    reason = get_error_message(res)
    if "does not exist" in reason.lower():
        module.fail_json(
            msg="{0} {1} does not exist or is not visible to this identity. "
            "An object in a realm is named realm::name.".format(label, name)
        )
    module.fail_json(
        msg="Failed to read {0} {1}. Error: {2}".format(kind, name, reason)
    )


def _check_certificate(module, blade, param):
    """Fail unless the named certificate or certificate group can be read.

    Returns the name as the array stores it. The array finds a certificate
    or certificate group whatever the case of the name, but it takes the
    reference on a DNS configuration only in the stored spelling and
    answers "Certificate does not exist." for any other.
    """
    name = module.params[param]
    if not name:
        return name
    if param == "ca_certificate_group":
        res = blade.get_certificate_groups(names=[name])
        label = "Certificate group"
    else:
        res = blade.get_certificates(names=[name])
        label = "Certificate"
    if res.status_code != 200:
        _fail_reference(module, res, label, label.lower(), name)
    for item in res.items:
        if _same_name(getattr(item, "name", None), name):
            return item.name
    return name


def _check_source(module, blade):
    """Fail unless the source network interface can be read."""
    name = module.params["source"]
    res = blade.get_network_interfaces(names=[name])
    if res.status_code != 200:
        _fail_reference(module, res, "Specified VIP", "network interface", name)


# REST version at which get_dns, post_dns, patch_dns and delete_dns accept
# the context_names keyword (Purity//FB 4.8.0). get_network_interfaces never
# takes it, so the source check is skipped when a context is set.
CONTEXT_API_VERSION = "2.25"


def _context_kwargs(module):
    """Return the context_names kwargs for a fleet context, or {} when unset.

    main() fails before any API call when a context is given below
    CONTEXT_API_VERSION, so the keyword only reaches an SDK method that
    accepts it.
    """
    if module.params["context"]:
        return {"context_names": [module.params["context"]]}
    return {}


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
    ctx = _context_kwargs(module)
    res = blade.get_dns(names=[module.params["name"]], **ctx)
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read DNS configuration {0}. Error: {1}".format(
                module.params["name"], get_error_message(res)
            )
        )
    current_dns = list(res.items)[0]
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
    # The array matches a reference without regard to case and keeps the
    # spelling it stored, so a different case is not a change.
    if module.params["source"] is not None and not _same_name(
        current_source, module.params["source"]
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
        current_name = _reference_name(current_dns, REFERENCE_PARAMS[ca_param])
        if _same_name(wanted, current_name):
            # The same reference: carried in the spelling the configuration
            # holds, the only one the array takes.
            wanted = current_name
        else:
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
        res = blade.patch_dns(names=[module.params["name"]], dns=Dns(**new_dns), **ctx)
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
    ctx = _context_kwargs(module)
    if module.params["name"] == "management":
        module.fail_json(msg="Management DNS configuration cannot be deleted")
    else:
        if not module.check_mode:
            res = blade.delete_dns(names=[module.params["name"]], **ctx)
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
    ctx = _context_kwargs(module)
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
        res = blade.post_dns(
            names=[module.params["name"]], dns=DnsPost(**new_dns), **ctx
        )
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
            context=dict(type="str", default=""),
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
    if module.params["context"] and LooseVersion(CONTEXT_API_VERSION) > LooseVersion(
        api_version
    ):
        module.fail_json(
            msg="context requires REST API {0} (Purity//FB 4.8.0) or higher.".format(
                CONTEXT_API_VERSION
            )
        )
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
        if LooseVersion(NON_MGMT_DNS) <= LooseVersion(api_version):
            _check_realm_references(module)
        if ca_param:
            stored_name = _check_certificate(module, blade, ca_param)
            # The certificate is read on the array receiving the request.
            # With a context the name belongs to the fleet member and is
            # sent as given.
            if not module.params["context"]:
                module.params[ca_param] = stored_name

    if LooseVersion(NON_MGMT_DNS) <= LooseVersion(api_version):
        res = blade.get_dns(**_context_kwargs(module))
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to read DNS configurations. Error: {0}".format(
                    get_error_message(res)
                )
            )
        current = _find_config(list(res.items), module.params["name"])
        exists = current is not None
        if exists:
            # The array matches names without regard to case and returns the
            # spelling it stored, which is the one used from here on.
            module.params["name"] = current.name
        if state == "present":
            _check_realm_source(module, exists)
        # get_network_interfaces takes no context and interface names belong
        # to the fleet member, so the source check only runs locally.
        if module.params["source"] and not module.params["context"]:
            _check_source(module, blade)
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
