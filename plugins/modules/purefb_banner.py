#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2020, Simon Dodsley (simon@everpuredata.com)
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
module: purefb_banner
version_added: '1.4.0'
short_description: Configure Everpure FlashBlade GUI and SSH MOTD message
description:
- Configure MOTD for Everpure FlashBlades.
- This will be shown during an SSH or GUI login to the system.
- Multiple line messages can be achieved using \\n.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  state:
    description:
    - Set ot delete the MOTD
    default: present
    type: str
    choices: [ present, absent ]
  banner:
    description:
    - Banner text, or MOTD, to use
    type: str
    default: "Welcome to the machine..."
  context:
    description:
    - Name of fleet member on which to perform the operation.
    - This requires the array receiving the request is a member of a fleet
      and the context name to be a member of the same fleet.
    - Requires FlashBlade REST 2.30 (Purity//FB 4.8.8) or higher.
    type: str
    default: ""
    version_added: "1.30.0"
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Set new banner text
  everpure.flashblade.purefb_banner:
    banner: "Banner over\ntwo lines"
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Set banner text on another member of the fleet
  everpure.flashblade.purefb_banner:
    banner: "Fleet member banner"
    context: fleet-member-01
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete banner text
  everpure.flashblade.purefb_banner:
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
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
    get_error_message,
    get_rest_api_version,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.version import (
    LooseVersion,
)

# REST versions at which the SDK methods used here accept context_names
CONTEXT_GET_API_VERSION = "2.22"  # get_arrays
CONTEXT_PATCH_API_VERSION = "2.30"  # patch_arrays (Purity//FB 4.8.8)


def _context_kwargs(module, api_version, context_version):
    """Return the context_names kwarg for one SDK call.

    The kwarg is only sent when a context is set and the negotiated REST
    version supports context on that method; each method has its own gate
    (get_arrays 2.22, patch_arrays 2.30).
    """
    if module.params["context"] and LooseVersion(context_version) <= LooseVersion(
        api_version
    ):
        return {"context_names": [module.params["context"]]}
    return {}


def set_banner(module, blade, ctx):
    """Set MOTD banner text"""
    changed = True
    if not module.check_mode:
        if not module.params["banner"]:
            module.fail_json(msg="Invalid MOTD banner given")
        blade_settings = Array(banner=module.params["banner"])
        res = blade.patch_arrays(array=blade_settings, **ctx)
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to set MOTD banner text. Error: {0}".format(
                    get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def delete_banner(module, blade, ctx):
    """Delete MOTD banner text"""
    changed = True
    if not module.check_mode:
        blade_settings = Array(banner="")
        res = blade.patch_arrays(array=blade_settings, **ctx)
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete current MOTD banner text. Error: {0}".format(
                    get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            banner=dict(type="str", default="Welcome to the machine..."),
            state=dict(type="str", default="present", choices=["present", "absent"]),
            context=dict(type="str", default=""),
        )
    )

    required_if = [("state", "present", ["banner"])]

    module = AnsibleModule(
        argument_spec, required_if=required_if, supports_check_mode=True
    )
    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    state = module.params["state"]
    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    # The banner is written through patch_arrays, so a context the PATCH
    # cannot carry must be refused before anything is read or changed.
    if module.params["context"] and LooseVersion(
        CONTEXT_PATCH_API_VERSION
    ) > LooseVersion(api_version):
        module.fail_json(
            msg=(
                "The context parameter requires FlashBlade REST {0} or higher "
                "(Purity//FB 4.8.8+); this array supports {1}."
            ).format(CONTEXT_PATCH_API_VERSION, api_version)
        )

    res = blade.get_arrays(
        **_context_kwargs(module, api_version, CONTEXT_GET_API_VERSION)
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to get current MOTD banner text. Error: {0}".format(
                get_error_message(res)
            )
        )
    current_banner = list(res.items)[0].banner
    patch_ctx = _context_kwargs(module, api_version, CONTEXT_PATCH_API_VERSION)

    # set banner if empty value or value differs
    if state == "present" and (
        not current_banner or current_banner != module.params["banner"]
    ):
        set_banner(module, blade, patch_ctx)
    # clear banner if it has a value
    elif state == "absent" and current_banner:
        delete_banner(module, blade, patch_ctx)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
