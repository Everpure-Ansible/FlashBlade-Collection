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
    - List of up to 3 unique DNS server IP addresses. These can be
      IPv4 or IPv6 - No validation is done of the addresses is performed.
    type: list
    elements: str
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
"""

RETURN = r"""
"""

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


def _get_source(module, blade):
    res = blade.get_network_interfaces(names=[module.params["source"]])
    return bool(res.status_code == 200)


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
    current_dns = list(blade.get_dns(names=[module.params["name"]], **ctx).items)[0]
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
    if changed and not module.check_mode:
        # Only send sources when the caller specified one, otherwise an
        # omitted source would be sent as a reference with no name.
        new_dns = {"domain": domain, "nameservers": nameservers}
        if module.params["source"] is not None:
            new_dns["sources"] = [Reference(name=module.params["source"])]
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
    ctx = _context_kwargs(module)
    if not module.check_mode:
        if module.params["service"] == "data":
            if module.params["source"]:
                res = blade.post_dns(
                    names=[module.params["name"]],
                    dns=DnsPost(
                        services=[module.params["service"]],
                        domain=module.params["domain"],
                        nameservers=module.params["nameservers"],
                        sources=[Reference(name=module.params["source"].lower())],
                    ),
                    **ctx,
                )
            else:
                res = blade.post_dns(
                    names=[module.params["name"]],
                    dns=DnsPost(
                        services=[module.params["service"]],
                        domain=module.params["domain"],
                        nameservers=module.params["nameservers"],
                    ),
                    **ctx,
                )
        else:
            res = blade.post_dns(
                names=[module.params["name"]],
                dns=DnsPost(
                    services=[module.params["service"]],
                    domain=module.params["domain"],
                    nameservers=module.params["nameservers"],
                ),
                **ctx,
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
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

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

    if LooseVersion(NON_MGMT_DNS) <= LooseVersion(api_version):
        res = blade.get_dns(**_context_kwargs(module))
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to read DNS configurations. Error: {0}".format(
                    get_error_message(res)
                )
            )
        configs = list(res.items)
        exists = False
        for config in configs:
            if config.name == module.params["name"]:
                exists = True
        # get_network_interfaces takes no context and interface names belong
        # to the fleet member, so the source check only runs locally.
        if (
            module.params["source"]
            and not module.params["context"]
            and not _get_source(module, blade)
        ):
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
