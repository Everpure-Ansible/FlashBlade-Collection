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
module: purefb_phonehome
version_added: '1.0.0'
short_description: Enable or Disable Everpure FlashBlade Phone Home
description:
- Enable or disable remote Phone Home for an Everpure FlashBlade.
- Optionally opt the array in to, or out of, the Pure1 Edge Services
  switches that live in the same support configuration.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  state:
    description:
    - Define state of phone home.
    - C(test) runs the Phone Home connectivity test and returns the result
      without changing anything.
    type: str
    default: present
    choices: [ present, absent, test ]
  edge_management:
    description:
    - Opt in (C(true)) or out (C(false)) of Pure1 Edge Management, which
      allows Pure1 to send management commands to the array.
    - Left unchanged when not specified. Cannot be combined with I(state)
      C(test).
    - Requires Purity//FB 4.6.0 (REST API 2.18) or later; the module fails
      on older arrays when this option is set.
    - The opt-in only takes effect once Edge Services are enabled for the
      organization in Pure1.
    type: bool
    version_added: '1.30.0'
  edge_agent_update:
    description:
    - Opt in (C(true)) or out (C(false)) of Pure1 edge agent updates, which
      allow Pure1 to install, upgrade and remove the edge agent on the array.
    - Left unchanged when not specified. Cannot be combined with I(state)
      C(test).
    - Requires Purity//FB 4.6.0 (REST API 2.18) or later; the module fails
      on older arrays when this option is set.
    - The opt-in only takes effect once Edge Services are enabled for the
      organization in Pure1.
    type: bool
    version_added: '1.30.0'
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Enable Remote Phone Home
  everpure.flashblade.purefb_phonehome:
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Disable Remote Phone Home
  everpure.flashblade.purefb_phonehome:
    state: absent
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Enable Phone Home and opt in to Pure1 Edge Management and edge agent updates
  everpure.flashblade.purefb_phonehome:
    edge_management: true
    edge_agent_update: true
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Opt out of Pure1 Edge Management, leaving Phone Home enabled
  everpure.flashblade.purefb_phonehome:
    edge_management: false
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Test Phone Home connectivity
  everpure.flashblade.purefb_phonehome:
    state: test
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
"""

RETURN = r"""
test_response:
    description: Result of the Phone Home connectivity test, one entry per
        component that ran it.
    type: list
    elements: dict
    returned: when I(state) is C(test)
    contains:
        component_address:
            description: Address of the component that ran the test.
            type: str
        component_name:
            description: Name of the component that ran the test.
            type: str
        description:
            description: Description of the test.
            type: str
        destination:
            description: Destination the component tried to reach.
            type: str
        enabled:
            description: Whether Phone Home is enabled on the component,
                as the string C(true) or C(false).
            type: str
        result_details:
            description: Additional details about the test result.
            type: str
        success:
            description: Whether the test succeeded, as the string C(true)
                or C(false).
            type: str
        test_type:
            description: Type of test that was run.
            type: str
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import Support
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

EDGE_API_VERSION = "2.18"
# (module option, Support model field)
EDGE_PARAMS = (
    ("edge_management", "edge_management_enabled"),
    ("edge_agent_update", "edge_agent_update_enabled"),
)


def _edge_options_set(module):
    """Return True when either edge option was supplied (True or False)."""
    return any(module.params[param] is not None for param, dummy in EDGE_PARAMS)


def _check_edge_support(module, api_version):
    """Fail before any write if an edge option is set on an array below REST 2.18.

    The pre-2.18 Support model silently drops the edge fields when it is
    serialised, so without this guard the module would send an empty PATCH,
    get a 200 back and report a change that never happened.
    """
    if LooseVersion(EDGE_API_VERSION) > LooseVersion(api_version):
        if _edge_options_set(module):
            module.fail_json(
                msg=(
                    "edge_management and edge_agent_update require Purity//FB "
                    "4.6.0 (REST API {0}) or later; the array reports REST API {1}."
                ).format(EDGE_API_VERSION, api_version)
            )


def _get_support(module, blade):
    """Return the support settings of the array.

    A read the array refuses or fails is reported with the message of the
    array.
    """
    res = blade.get_support()
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read the support settings. Error: {0}".format(
                get_error_message(res)
            )
        )
    items = list(res.items)
    if not items:
        module.fail_json(msg="The array returned no support settings.")
    return items[0]


def _pending_changes(module, support):
    """Return the Support fields whose desired value differs from the array."""
    changes = {}
    state = module.params["state"]
    if state == "present" and not support.phonehome_enabled:
        changes["phonehome_enabled"] = True
    elif state == "absent" and support.phonehome_enabled:
        changes["phonehome_enabled"] = False
    for param, field in EDGE_PARAMS:
        desired = module.params[param]
        if desired is not None and desired != getattr(support, field, None):
            changes[field] = desired
    return changes


def update_support(module, blade, changes):
    """Send every pending change in a single PATCH of the support settings."""
    if not module.check_mode:
        res = blade.patch_support(support=Support(**changes))
        if res.status_code != 200:
            module.fail_json(
                msg="Updating support settings ({0}) failed. Error: {1}".format(
                    ", ".join(sorted(changes)), get_error_message(res)
                )
            )
    module.exit_json(changed=True)


def test_ph(module, blade):
    """Test phonehome configuration"""
    test_response = []
    res = blade.get_support_test(test_type="phonehome")
    if res.status_code != 200:
        module.fail_json(
            msg="Phone Home test failed. Error: {0}".format(get_error_message(res))
        )
    for component in list(res.items):
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
            }
        )
    module.exit_json(changed=False, test_response=test_response)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(
                type="str", default="present", choices=["present", "absent", "test"]
            ),
            edge_management=dict(type="bool"),
            edge_agent_update=dict(type="bool"),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client SDK is required for this module")

    if module.params["state"] == "test" and _edge_options_set(module):
        module.fail_json(
            msg=(
                "edge_management and edge_agent_update cannot be combined "
                "with state=test"
            )
        )

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    _check_edge_support(module, api_version)

    if module.params["state"] == "test":
        test_ph(module, blade)

    support = _get_support(module, blade)
    changes = _pending_changes(module, support)
    if changes:
        update_support(module, blade, changes)
    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
