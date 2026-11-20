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
module: purefb_ntp
version_added: '1.0.0'
short_description: Configure Everpure FlashBlade NTP settings
description:
- Set or erase NTP configuration for Everpure FlashBlades.
- The NTP servers are an array-wide setting that the array returns only to an
  administrator with array-wide access; for a realm-scoped administrator the
  module reads an empty list, so I(state=present) always tries to set the
  servers and I(state=absent) changes nothing.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  state:
    description:
    - Create or delete NTP servers configuration
    type: str
    default: present
    choices: [ absent, present ]
  ntp_servers:
    type: list
    elements: str
    description:
    - A list of up to 4 alternate NTP servers. These may include IPv4,
      IPv6 or FQDNs. Invalid IP addresses will cause the module to fail.
      No validation is performed for FQDNs.
    - If more than 4 servers are provided, only the first 4 unique
      nameservers will be used.
    - if no servers are given a default of C(0.pool.ntp.org) will be used.
  context:
    description:
    - Name of fleet member on which to perform the operation.
    - This requires the array receiving the request is a member of a fleet
      and the context name to be a member of the same fleet.
    - Requires Purity//FB 4.8.8 (REST API 2.30) or later. The module fails
      before any read or write when a context is given on an older array.
    type: str
    default: ""
    version_added: '1.30.0'
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Delete exisitng NTP server entries
  everpure.flashblade.purefb_ntp:
    state: absent
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592

- name: Set array NTP servers
  everpure.flashblade.purefb_ntp:
    state: present
    ntp_servers:
      - "0.pool.ntp.org"
      - "1.pool.ntp.org"
      - "2.pool.ntp.org"
      - "3.pool.ntp.org"
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592

- name: Set NTP servers on another member of the fleet
  everpure.flashblade.purefb_ntp:
    state: present
    ntp_servers:
      - "0.pool.ntp.org"
    context: fleet-member-2
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592
"""

RETURN = r"""
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import Array
except ImportError:
    HAS_PYPURECLIENT = False


from ansible.module_utils.basic import AnsibleModule
from ansible_collections.everpure.flashblade.plugins.module_utils.purefb import (
    get_system,
    purefb_argument_spec,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.common import (
    remove_duplicates,
    get_error_message,
    get_rest_api_version,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.version import (
    LooseVersion,
)

# REST API version at which patch_arrays accepts context_names. get_arrays
# accepted it from 2.22, but every path of this module may PATCH, so a context
# requires the later version.
CONTEXT_API_VERSION = "2.30"


def _context_kwargs(module):
    """Return the context_names kwargs for an SDK call when a context is set"""
    if module.params["context"]:
        return {"context_names": [module.params["context"]]}
    return {}


def _get_ntp_servers(module, blade):
    """Return the NTP servers configured on the (context) array"""
    res = blade.get_arrays(**_context_kwargs(module))
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read array NTP settings. Error: {0}".format(
                get_error_message(res)
            )
        )
    arrays = list(res.items)
    if len(arrays) != 1:
        module.fail_json(
            msg=(
                "Context {0} matched {1} arrays. "
                "The context must name a single fleet member."
            ).format(module.params["context"], len(arrays))
        )
    return arrays[0].ntp_servers or []


def delete_ntp(module, blade):
    """Delete NTP Servers"""
    changed = False
    current_servers = _get_ntp_servers(module, blade)
    if current_servers:
        changed = True
        if not module.check_mode:
            res = blade.patch_arrays(
                array=Array(ntp_servers=[]), **_context_kwargs(module)
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Deletion of NTP servers failed. Error: {0}".format(
                        get_error_message(res)
                    )
                )
    module.exit_json(changed=changed)


def create_ntp(module, blade):
    """Set NTP Servers"""
    changed = True
    if not module.check_mode:
        if not module.params["ntp_servers"]:
            module.params["ntp_servers"] = ["0.pool.ntp.org"]
        res = blade.patch_arrays(
            array=Array(ntp_servers=module.params["ntp_servers"][0:4]),
            **_context_kwargs(module)
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Update of NTP servers failed. Error: {0}".format(
                    get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            ntp_servers=dict(type="list", elements="str"),
            state=dict(type="str", default="present", choices=["absent", "present"]),
            context=dict(type="str", default=""),
        )
    )

    required_if = [["state", "present", ["ntp_servers"]]]

    module = AnsibleModule(
        argument_spec, required_if=required_if, supports_check_mode=True
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    blade = get_system(module)
    api_version = get_rest_api_version(blade)

    # Every path of this module may PATCH the array, so a context must be
    # supported by patch_arrays before anything is read or written.
    if module.params["context"] and LooseVersion(CONTEXT_API_VERSION) > LooseVersion(
        api_version
    ):
        module.fail_json(
            msg=(
                "Fleet context for NTP settings requires FlashBlade REST API "
                "version {0} (Purity//FB 4.8.8) or later, the array supports {1}."
            ).format(CONTEXT_API_VERSION, api_version)
        )

    if module.params["state"] == "absent":
        delete_ntp(module, blade)
    else:
        module.params["ntp_servers"] = remove_duplicates(module.params["ntp_servers"])
        current_servers = _get_ntp_servers(module, blade)
        if sorted(current_servers) != sorted(module.params["ntp_servers"][0:4]):
            create_ntp(module, blade)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
