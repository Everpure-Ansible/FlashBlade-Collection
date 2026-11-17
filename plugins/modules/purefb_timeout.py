#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2021, Simon Dodsley (simon@everpuredata.com)
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
module: purefb_timeout
version_added: '1.6.0'
short_description: Configure Everpure FlashBlade GUI idle timeout
description:
- Configure GUI idle timeout for Everpure FlashBlade.
- This does not affect existing GUI sessions.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  state:
    description:
    - Set or disable the GUI idle timeout
    default: present
    type: str
    choices: [ present, absent ]
  timeout:
    description:
    - Minutes for idle timeout.
    type: int
    default: 30
  context:
    description:
    - Name of fleet member on which to perform the operation.
    - This requires the array receiving the request is a member of a fleet
      and the context name to be a member of the same fleet.
    - Requires FlashBlade REST API 2.30 (Purity//FB 4.8.8) or later.
    - The context must name a single fleet member. A context that resolves
      to more than one array, such as a fleet name, is refused.
    type: str
    default: ""
    version_added: '1.30.0'
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Set GUI idle timeout to 25 minutes
  everpure.flashblade.purefb_timeout:
    timeout: 25
    state: present
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Disable idle timeout
  everpure.flashblade.purefb_timeout:
    state: absent
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Set GUI idle timeout to 25 minutes on another fleet member
  everpure.flashblade.purefb_timeout:
    timeout: 25
    context: fleet-member-2
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3
"""

RETURN = r"""
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient import flashblade
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

# REST versions from which each SDK call accepts context_names
GET_CONTEXT_API_VERSION = "2.22"
PATCH_CONTEXT_API_VERSION = "2.30"


def _context_kwargs(module, api_version, min_version):
    """Return the context_names kwargs for one SDK call, or {} without a context.

    Each /arrays call gained context_names at a different REST version, so the
    gate is per call. A context on an older array fails here with a clear
    message instead of the SDK raising TypeError on the unknown kwarg.
    """
    if not module.params["context"]:
        return {}
    if LooseVersion(min_version) > LooseVersion(api_version):
        module.fail_json(
            msg=(
                "The context parameter requires FlashBlade REST version {0} "
                "or later for this operation. Array REST version is {1}."
            ).format(min_version, api_version)
        )
    return {"context_names": [module.params["context"]]}


def set_timeout(module, blade, context_kwargs=None):
    """Set GUI idle timeout"""
    changed = True
    if not module.check_mode:
        res = blade.patch_arrays(
            flashblade.Array(idle_timeout=module.params["timeout"] * 60000),
            **(context_kwargs or {})
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to set GUI idle timeout. Error: {0}".format(
                    get_error_message(res)
                )
            )

    module.exit_json(changed=changed)


def disable_timeout(module, blade, context_kwargs=None):
    """Disable idle timeout"""
    changed = True
    if not module.check_mode:
        res = blade.patch_arrays(
            flashblade.Array(idle_timeout=0), **(context_kwargs or {})
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to disable GUI idle timeout. Error: {0}".format(
                    get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            timeout=dict(type="int", default=30),
            state=dict(type="str", default="present", choices=["present", "absent"]),
            context=dict(type="str", default=""),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    blade = get_system(module)

    state = module.params["state"]
    if (
        module.params["timeout"] < 5 or module.params["timeout"] > 180
    ) and module.params["timeout"] != 0:
        module.fail_json(msg="Timeout value must be between 5 and 180 minutes")
    # Both context gates are checked before anything is read or written, so a
    # context the array cannot honour fails before the module touches it.
    api_version = get_rest_api_version(blade)
    get_kwargs = _context_kwargs(module, api_version, GET_CONTEXT_API_VERSION)
    patch_kwargs = _context_kwargs(module, api_version, PATCH_CONTEXT_API_VERSION)
    res = blade.get_arrays(**get_kwargs)
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to get GUI idle timeout. Error: {0}".format(
                get_error_message(res)
            )
        )
    arrays = list(res.items)
    if len(arrays) != 1:
        module.fail_json(
            msg="Expected one array, got {0}. The context must name a single "
            "fleet member, not a fleet.".format(len(arrays))
        )
    current_timeout = arrays[0].idle_timeout / 60000
    if state == "present" and current_timeout != module.params["timeout"]:
        set_timeout(module, blade, patch_kwargs)
    elif state == "absent" and current_timeout != 0:
        disable_timeout(module, blade, patch_kwargs)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
