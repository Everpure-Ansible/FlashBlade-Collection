#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2022, Simon Dodsley (simon@everpuredata.com)
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
module: purefb_messages
version_added: '1.10.0'
short_description: List, flag or unflag FlashBlade Alert Messages
description:
- List alert messages based on the filters provided.
- Flag or unflag alerts by name or ID. FlashBlade alerts are flagged when
  they are raised. Unflagging an alert dismisses it from the default alert
  listing of the array and flagging it again restores it.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  severity:
    description:
    - Severity of the alerts to list.
    - Ignored when I(flag) or I(unflag) is set.
    type: list
    elements: str
    choices: [ all, critical, warning, info ]
    default: [ all ]
  state:
    description:
    - State of the alerts to list.
    - Ignored when I(flag) or I(unflag) is set.
    default: open
    choices: [ all, open, closed ]
    type: str
  flagged:
    description:
    - Filter the listing on the flagged attribute of the alerts.
    - FlashBlade alerts are flagged when they are raised. An alert becomes
      unflagged when an administrator dismisses it, for example with I(unflag).
    - The default of C(false) lists only dismissed alerts. Set C(true) to list
      the alerts the array itself shows by default.
    - Ignored when I(flag) or I(unflag) is set.
    default: false
    type: bool
  history:
    description:
    - Historical time period to list alerts for, from the present time.
    - Allowed time periods are hour(h), day(d), week(w) and year(y).
    - Ignored when I(flag) or I(unflag) is set.
    type: str
    default: 1w
  flag:
    description:
    - List of alerts to flag, each given as the alert name (its numeric
      index, for example C(1)) or its ID.
    - Alerts that are already flagged are left untouched. In check mode the
      alerts that would be flagged are returned with the intended flagged value.
    - When set, only the referenced alerts are returned and the listing
      options I(severity), I(state), I(flagged) and I(history) are ignored.
    - Mutually exclusive with I(unflag).
    type: list
    elements: str
    version_added: '1.30.0'
  unflag:
    description:
    - List of alerts to unflag (dismiss), each given as the alert name (its
      numeric index, for example C(1)) or its ID.
    - Alerts that are already unflagged are left untouched. In check mode the
      alerts that would be unflagged are returned with the intended flagged value.
    - When set, only the referenced alerts are returned and the listing
      options I(severity), I(state), I(flagged) and I(history) are ignored.
    - Mutually exclusive with I(flag).
    type: list
    elements: str
    version_added: '1.30.0'
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Show critical alerts from the past 4 weeks that have been dismissed
  purefb_messages:
    history: 4w
    flagged: false
    severity:
      - critical
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Show all open alerts from the past day that have not been dismissed
  purefb_messages:
    history: 1d
    flagged: true
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Dismiss two known alerts by name
  purefb_messages:
    unflag:
      - "1"
      - "13"
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Restore a dismissed alert by ID
  purefb_messages:
    flag:
      - 11111111-2222-3333-4444-555555555555
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3
"""

RETURN = r"""
purefb_messages:
  description:
  - The alerts matching the listing filters, or the alerts referenced by
    I(flag) or I(unflag), keyed by alert name.
  - In check mode an alert that would be patched is returned with the
    intended flagged value.
  returned: success
  type: dict
  sample:
    "1":
      summary: Insecure Default pureuser Password
      component_type: security
      component_name: pureuser
      description: The user pureuser is configured with the default password.
      code: 1123
      severity: warning
      state: open
      flagged: true
      created: "2026-01-05 08:00:00 UTC"
      notified: "2026-01-12 08:00:00 UTC"
      updated: "2026-01-12 08:00:00 UTC"
"""

import re
import time

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import Alert
except ImportError:
    HAS_PYPURECLIENT = False

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.everpure.flashblade.plugins.module_utils.purefb import (
    get_system,
    purefb_argument_spec,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.common import (
    get_error_message,
)

ALLOWED_PERIODS = ["h", "d", "w", "y"]
# Time periods in micro-seconds
HOUR = 3600000
DAY = HOUR * 24
WEEK = DAY * 7
YEAR = WEEK * 52

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _create_time_window(window):
    period = window[-1].lower()
    multiple = int(window[0:-1])
    if period == "h":
        return HOUR * multiple
    if period == "d":
        return DAY * multiple
    if period == "w":
        return WEEK * multiple
    if period == "y":
        return YEAR * multiple
    return None


def _timestamp(value):
    if value is None:
        return None
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(value / 1000)) + " UTC"


def _alert_to_dict(message):
    return {
        "summary": message.summary,
        "component_type": message.component_type,
        "component_name": message.component_name,
        "description": message.description,
        "code": message.code,
        "severity": message.severity,
        "state": message.state,
        "flagged": message.flagged,
        "created": _timestamp(message.created),
        "notified": _timestamp(message.notified),
        "updated": _timestamp(message.updated),
    }


def _get_alerts_by_reference(module, blade, references):
    """Return the referenced alerts keyed by name.

    References are alert names (numeric index strings) or alert IDs (UUIDs).
    The API does not accept names and ids in one request, so each kind is
    fetched separately. A reference that matches no alert is an API error.
    """
    names = [ref for ref in references if not UUID_RE.match(ref)]
    ids = [ref for ref in references if UUID_RE.match(ref)]
    alerts = {}
    for key, values in (("names", names), ("ids", ids)):
        if not values:
            continue
        res = blade.get_alerts(**{key: values})
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to get alerts {0}. Error: {1}".format(
                    ", ".join(values), get_error_message(res)
                )
            )
        for alert in list(res.items):
            alerts[alert.name] = alert
    return alerts


def set_flagged(module, blade):
    """Flag or unflag the referenced alerts, patching only those that differ."""
    if module.params["flag"] is not None:
        target = True
        references = module.params["flag"]
    else:
        target = False
        references = module.params["unflag"]
    alerts = _get_alerts_by_reference(module, blade, references)
    to_change = [name for name, alert in alerts.items() if alert.flagged != target]
    changed = bool(to_change)
    messages = {}
    for name, alert in alerts.items():
        messages[name] = _alert_to_dict(alert)
    for name in to_change:
        # The intended value; replaced by the array's own view after the PATCH.
        messages[name]["flagged"] = target
    if changed and not module.check_mode:
        res = blade.patch_alerts(names=to_change, alerts_settings=Alert(flagged=target))
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to {0} alerts {1}. Error: {2}".format(
                    "flag" if target else "unflag",
                    ", ".join(to_change),
                    get_error_message(res),
                )
            )
        for alert in list(res.items):
            messages[alert.name] = _alert_to_dict(alert)
    module.exit_json(changed=changed, purefb_messages=messages)


def list_alerts(module, blade):
    """List alerts matching the severity, state, flagged and history filters."""
    time_now = int(time.time() * 1000)
    if module.params["history"][-1].lower() not in ALLOWED_PERIODS:
        module.fail_json(msg="historical window value is not an allowed time period")
    since_time = str(time_now - _create_time_window(module.params["history"].lower()))
    if module.params["flagged"]:
        flagged = " and flagged='True'"
    else:
        flagged = " and flagged='False'"

    multi_sev = False
    if len(module.params["severity"]) > 1:
        if "all" in module.params["severity"]:
            module.params["severity"] = ["*"]
        else:
            multi_sev = True
    if multi_sev:
        severity = " and ("
        for level in module.params["severity"]:
            severity += "severity='" + str(level) + "' or "
        severity = severity[0:-4] + ")"
    else:
        if module.params["severity"] == ["all"]:
            severity = " and severity='*'"
        else:
            severity = " and severity='" + str(module.params["severity"][0]) + "'"
    messages = {}
    if module.params["state"] == "all":
        state = " and state='*'"
    else:
        state = " and state='" + module.params["state"] + "'"
    filter_string = "notified>" + since_time + state + flagged + severity
    res = blade.get_alerts(filter=filter_string)
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to get alert messages. Error: {0}".format(
                get_error_message(res)
            )
        )
    for message in list(res.items):
        messages[message.name] = _alert_to_dict(message)
    module.exit_json(changed=False, purefb_messages=messages)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(type="str", default="open", choices=["all", "open", "closed"]),
            history=dict(type="str", default="1w"),
            flagged=dict(type="bool", default=False),
            severity=dict(
                type="list",
                elements="str",
                default=["all"],
                choices=["all", "critical", "warning", "info"],
            ),
            flag=dict(type="list", elements="str"),
            unflag=dict(type="list", elements="str"),
        )
    )

    module = AnsibleModule(
        argument_spec,
        mutually_exclusive=[["flag", "unflag"]],
        supports_check_mode=True,
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    blade = get_system(module)

    if module.params["flag"] is not None or module.params["unflag"] is not None:
        set_flagged(module, blade)
    else:
        list_alerts(module, blade)


if __name__ == "__main__":
    main()
