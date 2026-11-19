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
module: purefb_maintenance
version_added: '1.30.0'
short_description: Manage the FlashBlade maintenance window
description:
- Open, replace or close the FlashBlade maintenance window.
- While a maintenance window is open the array suppresses alert
  notifications for the duration of the window. The array keeps a single
  window, named C(array), so this module has no name option.
- An open window is only replaced when its duration differs from
  I(timeout) or when I(extend=true). The replacement is a new window of
  I(timeout) starting now, so changing I(timeout) extends or shortens the
  window and I(extend=true) pushes a window of the same duration out again.
- Equivalent to the C(puremaintenance schedule) and C(puremaintenance
  unschedule) CLI commands.
- Requires FlashBlade REST API version 2.16 or later (Purity//FB 4.5.2+).
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  state:
    description:
    - C(present) opens a maintenance window, or replaces the open one when
      its duration differs from I(timeout) or I(extend=true).
    - C(absent) closes the open maintenance window before its scheduled end.
    type: str
    default: present
    choices: [ absent, present ]
  timeout:
    description:
    - Duration of the maintenance window.
    - Accepts a number of seconds, or a duration with a unit suffix of
      C(s) (seconds), C(m) (minutes), C(h) (hours) or C(d) (days), for
      example C(90m) or C(6h).
    - Range is 1 hour to 48 hours (C(1h) to C(48h), or C(3600) to
      C(172800)); the array refuses a shorter or longer window. The default
      of 4 hours matches the array default.
    - Ignored when I(state=absent).
    type: str
    default: 4h
  extend:
    description:
    - When C(true), replace an open window with a new window of I(timeout)
      starting now even if its duration is unchanged.
    - A task with I(extend=true) reports changed whenever a window is open,
      so it is not idempotent. Use it to push the window out again during
      long maintenance.
    - Ignored when I(state=absent). When no window is open one is opened.
    type: bool
    default: false
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Open a maintenance window with the default duration of 4 hours
  everpure.flashblade.purefb_maintenance:
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Open a 90 minute maintenance window
  everpure.flashblade.purefb_maintenance:
    timeout: 90m
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Extend the open maintenance window to 8 hours from now
  everpure.flashblade.purefb_maintenance:
    timeout: 8h
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Push the open 4 hour maintenance window out to 4 hours from now
  everpure.flashblade.purefb_maintenance:
    extend: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Close the maintenance window
  everpure.flashblade.purefb_maintenance:
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = r"""
maintenance_window:
  description:
  - The maintenance window open on the array after the task.
  - Empty when no window is open. In check mode this is the window found
    before the task, since nothing is changed.
  returned: success
  type: dict
  contains:
    name:
      description: Name of the window, always C(array).
      type: str
      sample: array
    created:
      description: Start of the window in milliseconds since the UNIX epoch.
      type: int
      sample: 1700000000000
    expires:
      description: End of the window in milliseconds since the UNIX epoch.
      type: int
      sample: 1700014400000
    timeout:
      description: Duration of the window in seconds.
      type: int
      sample: 14400
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import MaintenanceWindowPost
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
from ansible_collections.everpure.flashblade.plugins.module_utils.time_utils import (
    time_to_milliseconds,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.version import (
    LooseVersion,
)

MIN_REQUIRED_API_VERSION = "2.16"
# The array keeps exactly one maintenance window and requires this name.
WINDOW_NAME = "array"
# The array refuses a window shorter than one hour or longer than 48 hours.
MIN_TIMEOUT_SECONDS = 3600
MAX_TIMEOUT_SECONDS = 48 * 3600
DURATION_UNITS = ("s", "m", "h", "d")


def parse_timeout(module):
    """Return the requested window duration in whole seconds.

    Accepts a bare number of seconds or a duration with an s/m/h/d suffix
    and enforces the 1 hour to 48 hour range the array supports.
    """
    value = str(module.params["timeout"]).strip().lower()
    # isdecimal() matches exactly the characters int() accepts; isdigit()
    # also matches superscripts, which int() rejects.
    if value.isdecimal():
        seconds = int(value)
    elif value[:-1].isdecimal() and value[-1:] in DURATION_UNITS:
        seconds = time_to_milliseconds(value) // 1000
    else:
        module.fail_json(
            msg=(
                "Invalid timeout {0}: use a number of seconds or a duration "
                "such as 90m, 6h or 2d"
            ).format(module.params["timeout"])
        )
    if not MIN_TIMEOUT_SECONDS <= seconds <= MAX_TIMEOUT_SECONDS:
        module.fail_json(
            msg=(
                "timeout must be between 1 hour and 48 hours "
                "({0} to {1} seconds), got {2} seconds"
            ).format(MIN_TIMEOUT_SECONDS, MAX_TIMEOUT_SECONDS, seconds)
        )
    return seconds


def window_duration(window):
    """Return the duration of an open window in whole seconds, or None."""
    created = getattr(window, "created", None)
    expires = getattr(window, "expires", None)
    if created is None or expires is None:
        return None
    return int(round((expires - created) / 1000.0))


def window_facts(window):
    """Return the result dict for a window, or {} when none is open."""
    if window is None:
        return {}
    return {
        "name": getattr(window, "name", WINDOW_NAME),
        "created": getattr(window, "created", None),
        "expires": getattr(window, "expires", None),
        "timeout": window_duration(window),
    }


def get_window(module, blade):
    """Return the open maintenance window, or None when none is open."""
    res = blade.get_maintenance_windows()
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to get maintenance window. Error: {0}".format(
                get_error_message(res)
            )
        )
    items = list(res.items)
    if items:
        return items[0]
    return None


def delete_window(module, blade, window):
    """Close the open maintenance window"""
    changed = False
    if window is not None:
        changed = True
        if not module.check_mode:
            res = blade.delete_maintenance_windows(names=[WINDOW_NAME])
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to close maintenance window. Error: {0}".format(
                        get_error_message(res)
                    )
                )
            window = None
    module.exit_json(changed=changed, maintenance_window=window_facts(window))


def set_window(module, blade, window):
    """Open a maintenance window, replacing one of a different duration
    or, with extend=true, any open window."""
    timeout = parse_timeout(module)
    # A POST while a window is open replaces it with a new window of the
    # requested duration starting now, so only post when the duration
    # differs unless the user asked to extend unconditionally.
    changed = (
        window is None or module.params["extend"] or window_duration(window) != timeout
    )
    if changed and not module.check_mode:
        res = blade.post_maintenance_windows(
            names=[WINDOW_NAME],
            maintenance_window=MaintenanceWindowPost(timeout=timeout * 1000),
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to open maintenance window. Error: {0}".format(
                    get_error_message(res)
                )
            )
        window = get_window(module, blade)
    module.exit_json(changed=changed, maintenance_window=window_facts(window))


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(type="str", default="present", choices=["absent", "present"]),
            timeout=dict(type="str", default="4h"),
            extend=dict(type="bool", default=False),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg=(
                "FlashBlade REST version not supported. "
                "Minimum version required: {0} (Purity//FB 4.5.2+)"
            ).format(MIN_REQUIRED_API_VERSION)
        )

    window = get_window(module, blade)

    if module.params["state"] == "absent":
        delete_window(module, blade, window)
    else:
        set_window(module, blade, window)


if __name__ == "__main__":
    main()
