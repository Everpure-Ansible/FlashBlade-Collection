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
module: purefb_bladename
version_added: '1.0.0'
short_description: Configure Everpure FlashBlade name
description:
- Configure name of Everpure FlashBlades.
- Ideal for Day 0 initial configuration.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  state:
    description:
    - Set the FlashBlade name
    type: str
    default: present
    choices: [ present ]
  name:
    description:
    - Name of the FlashBlade. Must conform to correct naming schema.
    type: str
    required: true
  context:
    description:
    - Name of fleet member on which to perform the operation.
    - This requires the array receiving the request is a member of a fleet
      and the context name to be a member of the same fleet.
    - Reading the current name of a fleet member requires FlashBlade REST API
      2.22 (Purity//FB 4.6.5) or later and changing it requires REST API 2.30
      (Purity//FB 4.8.8) or later. The module fails when a context is given
      on an array below the version the operation needs.
    - The context must name a single fleet member. A context that resolves
      to more than one array, such as a fleet name, is refused.
    type: str
    default: ""
    version_added: '1.30.0'
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Set new FlashBlade name
  everpure.flashblade.purefb_bladename:
    name: new-flashblade-name
    state: present
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592

- name: Rename another member of the fleet through this FlashBlade
  everpure.flashblade.purefb_bladename:
    name: new-member-name
    context: current-member-name
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

# Each SDK method gained context_names in its own REST version
GET_CONTEXT_API_VERSION = "2.22"
PATCH_CONTEXT_API_VERSION = "2.30"


def _context_kwargs(module, api_version, context_version, operation):
    """Return the context_names kwarg for one SDK call, or {} without a context.

    A context on an array below the version that call requires fails here
    with a clear message instead of as a TypeError inside the SDK.
    """
    context = module.params.get("context")
    if not context:
        return {}
    if LooseVersion(context_version) > LooseVersion(api_version):
        module.fail_json(
            msg=(
                "Fleet context requires FlashBlade REST API version {0} or later "
                "for {1}. The array supports {2}."
            ).format(context_version, operation, api_version)
        )
    return {"context_names": [context]}


def update_name(module, blade, context_kwargs=None):
    """Change aray name"""
    changed = True
    if not module.check_mode:
        blade_settings = Array(name=module.params["name"])
        res = blade.patch_arrays(array=blade_settings, **(context_kwargs or {}))
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to change array name to {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )

    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str", required=True),
            state=dict(type="str", default="present", choices=["present"]),
            context=dict(type="str", default=""),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    blade = get_system(module)
    pattern = re.compile("^[a-zA-Z0-9]([a-zA-Z0-9-]{0,54}[a-zA-Z0-9])?$")
    if not pattern.match(module.params["name"]):
        module.fail_json(
            msg="FlashBlade name {0} does not conform to array name rules".format(
                module.params["name"]
            )
        )
    api_version = get_rest_api_version(blade)
    get_ctx = _context_kwargs(
        module, api_version, GET_CONTEXT_API_VERSION, "reading the array name"
    )
    res = blade.get_arrays(**get_ctx)
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to get array details. Error: {0}".format(get_error_message(res))
        )
    arrays = list(res.items)
    if not arrays:
        module.fail_json(msg="Failed to get array details. No array returned.")
    if len(arrays) > 1:
        module.fail_json(
            msg=(
                "Context {0} resolves to {1} arrays. Give the name of a single "
                "fleet member as the context."
            ).format(module.params["context"], len(arrays))
        )
    if module.params["name"] != arrays[0].name:
        patch_ctx = _context_kwargs(
            module, api_version, PATCH_CONTEXT_API_VERSION, "changing the array name"
        )
        update_name(module, blade, patch_ctx)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
