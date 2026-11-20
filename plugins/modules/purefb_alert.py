#!/usr/bin/python
# -*- coding: utf-8 -*-

# 2018, Simon Dodsley (simon@everpuredata.com)
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
module: purefb_alert
version_added: '1.0.0'
short_description: Configure Everpure FlashBlade alert email settings
description:
- Manage the alert email recipients (alert watchers) of an Everpure
  FlashBlade.
- Create, update, delete or test an individual alert watcher.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  state:
    type: str
    description:
    - Create, delete or test alert email
    - C(test) asks the array to send a test email to I(address) and returns
      the result in C(test_response) without changing anything. The test
      also runs in check mode.
    - The array sends the test email whether or not the address is an alert
      watcher and whether or not the watcher is enabled. The module warns
      when the address is not an alert watcher.
    default: present
    choices: [ absent, present, test ]
  address:
    type: str
    description:
    - Email address (valid format required)
    - The letter case of the address is not significant. An alert watcher
      whose address differs only in letter case is the one that is updated,
      deleted or tested.
    required: true
  enabled:
    type: bool
    default: true
    description:
    - Set specified email address to be enabled or disabled
  severity:
    type: str
    description:
    - The minimum severity that an alert must have in order for
      emails to be sent to the array's alert watchers
    default: info
    choices: [ info, warning, critical ]
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Add new email recipient and enable, or enable existing email
  everpure.flashblade.purefb_alert:
    address: "user@domain.com"
    enabled: true
    state: present
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592
- name: Delete existing email recipient
  everpure.flashblade.purefb_alert:
    state: absent
    address: "user@domain.com"
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592
- name: Send a test email to an email recipient
  everpure.flashblade.purefb_alert:
    state: test
    address: "user@domain.com"
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592
  register: result
"""

RETURN = r"""
test_response:
    description: Result of the alert email test, one entry per component
        that ran it.
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
            description: Email address the test email was sent to.
            type: str
        enabled:
            description: Whether the address is an enabled alert watcher,
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
        resource_name:
            description: Name of the alert watcher that was tested. Empty
                when the address is not an alert watcher.
            type: str
"""


HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import AlertWatcher, AlertWatcherPost
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
)


def _stored_address(watchers, address):
    """Return the address of an alert watcher as the array stored it.

    The array reads and tests an alert watcher without regard to the letter
    case of its address, and refuses a second watcher on it, but changes and
    deletes the watcher only under the spelling it stored. A watcher stored
    in exactly the spelling asked for is preferred, so a task that names a
    stored address always gets that watcher. Returns None when no alert
    watcher has the address.
    """
    names = [watcher.name for watcher in watchers]
    if address in names:
        return address
    for name in names:
        if name.lower() == address.lower():
            return name
    return None


def _resource_name(component):
    """Return the name of the alert watcher a test result refers to.

    The array names no resource in the result of a test of an address that
    is not an alert watcher.
    """
    resource = getattr(component, "resource", None)
    return getattr(resource, "name", None) or ""


def create_alert(module, blade):
    """Create Alert Email"""
    changed = True
    if not module.check_mode:
        watcher_settings = AlertWatcherPost(
            minimum_notification_severity=module.params["severity"]
        )
        res = blade.post_alert_watchers(
            names=[module.params["address"]], alert_watcher=watcher_settings
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to create alert email {0}. Error: {1}".format(
                    module.params["address"], get_error_message(res)
                )
            )
        if not module.params["enabled"]:
            watcher_settings = AlertWatcher(enabled=module.params["enabled"])
            res = blade.patch_alert_watchers(
                names=[module.params["address"]], alert_watcher=watcher_settings
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to disable during create alert email {0}. Error: {1}".format(
                        module.params["address"], get_error_message(res)
                    )
                )
    module.exit_json(changed=changed)


def update_alert(module, blade, name):
    """Update alert Watcher"""
    mod_alert = False
    res = blade.get_alert_watchers(names=[name])
    if res.status_code == 200:
        alert = list(res.items)[0]
    else:
        module.fail_json(
            msg="Failed to get information for alert email {0}. Error: {1}".format(
                name, get_error_message(res)
            )
        )
    current_state = {
        "enabled": alert.enabled,
        "severity": alert.minimum_notification_severity,
    }
    if current_state["enabled"] != module.params["enabled"]:
        enabled = module.params["enabled"]
        mod_alert = True
    else:
        enabled = current_state["enabled"]
    if current_state["severity"] != module.params["severity"]:
        severity = module.params["severity"]
        mod_alert = True
    else:
        severity = current_state["severity"]
    if mod_alert:
        changed = True
        if not module.check_mode:
            watcher_settings = AlertWatcher(
                enabled=enabled,
                minimum_notification_severity=severity,
            )
            res = blade.patch_alert_watchers(
                names=[name], alert_watcher=watcher_settings
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to update alert email {0}: Error: {1}".format(
                        name, get_error_message(res)
                    )
                )
    else:
        changed = False
    module.exit_json(changed=changed)


def delete_alert(module, blade, name):
    """Delete Alert Email"""
    changed = True
    if not module.check_mode:
        res = blade.delete_alert_watchers(names=[name])
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete alert email {0}. Error: {1}".format(
                    name, get_error_message(res)
                )
            )

    module.exit_json(changed=changed)


def test_alert(module, blade, name):
    """Test alert watchers"""
    test_response = []
    address = name or module.params["address"]
    res = blade.get_alert_watchers_test(names=[address])
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to test alert email {0}. Error: {1}".format(
                address, get_error_message(res)
            )
        )
    if name is None:
        module.warn(
            "{0} is not an alert watcher of the array: the array tested the "
            "address, but sends no alerts to it.".format(address)
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
                "resource_name": _resource_name(component),
            }
        )
    module.exit_json(changed=False, test_response=test_response)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            address=dict(type="str", required=True),
            enabled=dict(type="bool", default=True),
            severity=dict(
                type="str", default="info", choices=["info", "warning", "critical"]
            ),
            state=dict(
                type="str", default="present", choices=["absent", "present", "test"]
            ),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client SDK is required for this module")

    pattern = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    if not pattern.match(module.params["address"]):
        module.fail_json(msg="Valid email address not provided.")

    blade = get_system(module)

    res = blade.get_alert_watchers()
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to get existing email list. Error: {0}".format(
                get_error_message(res)
            )
        )
    watcher = _stored_address(list(res.items), module.params["address"])
    exists = watcher is not None
    if module.params["state"] == "present" and not exists:
        create_alert(module, blade)
    elif module.params["state"] == "present" and exists:
        update_alert(module, blade, watcher)
    elif module.params["state"] == "absent" and exists:
        delete_alert(module, blade, watcher)
    elif module.params["state"] == "test":
        test_alert(module, blade, watcher)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
