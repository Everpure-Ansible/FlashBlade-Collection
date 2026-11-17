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
module: purefb_sessions
version_added: '1.30.0'
short_description: List FlashBlade management sessions
description:
- List the management session log of a FlashBlade, which is the same data as
  the C(puresession list) CLI command. Each entry records an event on the
  GUI, CLI or REST interface, such as a login, a logout, a failed
  authentication, an API token request, a request made without a session or
  a request denied by a network policy.
- This is the management login audit. NFS and SMB client sessions on file
  systems are a different object and are not listed here.
- The array keeps a bounded, rolling session log and prunes the oldest entries
  itself, so the module returns only the entries the array still holds.
- Some entries carry no start time (reported by the array as 0 or not at
  all) and some, such as C(login) events and sessions that are still
  active, carry no end time. Those times are returned as null.
- Entries with neither a start nor an end time never match a time filter.
  To see them, leave I(start) and I(end) unset and filter by I(event) or
  I(user) instead.
- All filters are combined and applied by the array.
- Entries are returned newest first by start time. Entries without a
  recorded start time are returned before the newest entries and entries
  whose start time is reported as 0 are returned last.
- Requires FlashBlade REST API version 2.3 or later (Purity//FB 3.3.0+).
- The module is read-only and never reports a change.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  start:
    description:
    - Only return entries that started at or after this date and time.
    - Expected format is C(YYYY-MM-DD hh:mm:ss), interpreted in I(timezone).
    - Entries without a recorded start time are included when their end time
      is at or after this date and time. Entries with neither time never
      match.
    type: str
  end:
    description:
    - Only return entries that ended at or before this date and time.
    - Expected format is C(YYYY-MM-DD hh:mm:ss), interpreted in I(timezone).
    - Entries without a recorded end time, such as C(login) events and
      sessions that are still active, never match this filter.
    type: str
  timezone:
    description:
    - IANA timezone used to interpret I(start) and I(end) and to render the
      returned times.
    - Defaults to the timezone configured on the FlashBlade. If that cannot be
      read, the local timezone of the host running the module is used.
    type: str
  user:
    description:
    - Only return entries for this user name.
    type: str
  event:
    description:
    - Only return entries with one of these event types.
    - Values are passed to the array as given. Event types the array records
      include C(failed authentication), C(user session), C(login), C(logout),
      C(API token obtained), C(request without session) and
      C(denied by network policy).
    type: list
    elements: str
  user_interface:
    description:
    - Only return entries made through one of these interfaces.
    type: list
    elements: str
    choices: [ CLI, GUI, REST ]
  method:
    description:
    - Only return entries that used one of these authentication methods.
    - Entries for which the array recorded no method are never matched.
    type: list
    elements: str
    choices:
    - API token
    - password
    - ssh certificate
    - public key
  limit:
    description:
    - Maximum number of entries to return, newest first by start time.
    - Matching entries without a recorded start time are returned before the
      newest entries and count towards the limit.
    type: int
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: List every session log entry the array still holds
  everpure.flashblade.purefb_sessions:
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
  register: sessions

- name: List the sessions of one day, in the array's timezone
  everpure.flashblade.purefb_sessions:
    start: "2026-01-10 00:00:00"
    end: "2026-01-11 00:00:00"
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: List failed authentications and REST logins for one user, rendered in UTC
  everpure.flashblade.purefb_sessions:
    user: pureuser
    event:
      - failed authentication
      - login
    user_interface:
      - REST
    timezone: UTC
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: List at most 20 password logins since a date
  everpure.flashblade.purefb_sessions:
    start: "2026-01-10 08:00:00"
    method:
      - password
    limit: 20
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = r"""
purefb_sessions:
  description:
  - Session log entries that matched the filters, newest first by start
    time. Entries without a recorded start time come first and entries whose
    start time is reported as 0 come last.
  returned: success
  type: list
  elements: dict
  contains:
    name:
      description: Identifier of the session log entry.
      type: str
      sample: "22818414"
    user:
      description: User name the entry was recorded for.
      type: str
      sample: pureuser
    user_interface:
      description: Interface the entry was recorded on (C(CLI), C(GUI) or C(REST)).
      type: str
      sample: REST
    method:
      description:
      - Authentication method (C(API token), C(password), C(ssh certificate)
        or C(public key)). Empty when the array recorded none.
      type: str
      sample: API token
    event:
      description:
      - Event type of the entry, for example C(login), C(logout),
        C(failed authentication), C(user session), C(API token obtained),
        C(request without session) or C(denied by network policy).
      type: str
      sample: user session
    event_count:
      description: Number of events the array aggregated into the entry.
      type: int
      sample: 1
    location:
      description: IP address of the client, or C(console) for the local console.
      type: str
      sample: 10.10.10.20
    start_time:
      description:
      - Start of the entry in C(YYYY-MM-DD hh:mm:ss) format in I(timezone).
        Null when the array recorded no start time.
      type: str
      sample: "2026-01-10 08:12:52"
    end_time:
      description:
      - End of the entry in C(YYYY-MM-DD hh:mm:ss) format in I(timezone).
        Null when the array recorded no end time, for example while the
        session is still active.
      type: str
      sample: "2026-01-10 08:12:53"
    identifying_details:
      description:
      - Additional details identifying who authenticated, present only for
        ssh certificate and public key logins. Null otherwise.
      type: str
      sample: null
"""

HAS_PYTZ = True
try:
    import pytz
except ImportError:
    HAS_PYTZ = False

import datetime

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.everpure.flashblade.plugins.module_utils.purefb import (
    get_system,
    purefb_argument_spec,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.common import (
    get_error_message,
    get_local_tz,
    get_rest_api_version,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.version import (
    LooseVersion,
)

MIN_REQUIRED_API_VERSION = "2.3"

INTERFACE_CHOICES = ["CLI", "GUI", "REST"]
METHOD_CHOICES = ["API token", "password", "ssh certificate", "public key"]
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
# Newest first; the array accepts the trailing "-" form only.
SORT = ["start_time-"]


def _to_timestamp(module, name, timezone):
    """Convert the date/time in parameter ``name`` to epoch milliseconds.

    The value is read as ``YYYY-MM-DD hh:mm:ss`` in ``timezone``; the offset
    is resolved for that date, so a date on the other side of a DST change
    is not shifted by the current offset.
    """
    try:
        naive = datetime.datetime.strptime(module.params[name], TIME_FORMAT)
    except ValueError:
        module.fail_json(
            msg="{0} value {1} is not a valid date/time. "
            'Expected format is "YYYY-MM-DD hh:mm:ss"'.format(name, module.params[name])
        )
    aware = pytz.timezone(timezone).localize(naive)
    return int(aware.timestamp() * 1000)


def _or_clause(field, values):
    """Return ``field='a'`` or ``(field='a' or field='b')`` for ``values``."""
    clauses = ["{0}='{1}'".format(field, value) for value in values]
    if len(clauses) == 1:
        return clauses[0]
    return "(" + " or ".join(clauses) + ")"


def _get_filter_string(module, timezone):
    """Build the server-side filter from the parameters; "" when unfiltered."""
    clauses = []
    if module.params["start"]:
        start_ms = _to_timestamp(module, "start", timezone)
        # Entries whose start time the array did not record come back with
        # start_time 0 or without the field; match those on their end time.
        clauses.append(
            "(start_time>={0} or ((start_time=0 or not(start_time)) "
            "and end_time>={0}))".format(start_ms)
        )
    if module.params["end"]:
        clauses.append("end_time<={0}".format(_to_timestamp(module, "end", timezone)))
    if module.params["user"]:
        clauses.append("user='{0}'".format(module.params["user"]))
    for field in ("event", "user_interface", "method"):
        if module.params[field]:
            clauses.append(_or_clause(field, module.params[field]))
    return " and ".join(clauses)


def _format_time(timestamp_ms, timezone):
    """Render epoch milliseconds in ``timezone``; None when not recorded (0/absent)."""
    if not timestamp_ms:
        return None
    return datetime.datetime.fromtimestamp(
        timestamp_ms / 1000, tz=pytz.timezone(timezone)
    ).strftime(TIME_FORMAT)


def _get_timezone(module, blade):
    """Return the IANA timezone used to parse and render times."""
    timezone = module.params["timezone"]
    if not timezone:
        res = blade.get_arrays()
        if res.status_code == 200:
            arrays = list(res.items)
            if arrays:
                timezone = getattr(arrays[0], "time_zone", None)
        if not timezone:
            timezone = get_local_tz(module)
            module.warn(
                "Could not read the timezone of the array; using {0}".format(timezone)
            )
    if timezone not in pytz.all_timezones_set:
        module.fail_json(msg="Timezone {0} is not valid".format(timezone))
    return timezone


def _list_sessions(module, blade, timezone):
    """Return the matching session log entries as a list of dicts."""
    kwargs = {"sort": SORT}
    filter_string = _get_filter_string(module, timezone)
    if filter_string:
        kwargs["filter"] = filter_string
    if module.params["limit"]:
        kwargs["limit"] = module.params["limit"]
    res = blade.get_sessions(**kwargs)
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to get sessions. Error: {0}".format(get_error_message(res))
        )
    sessions = []
    for session in list(res.items):
        sessions.append(
            {
                "name": getattr(session, "name", None),
                "user": getattr(session, "user", None),
                "user_interface": getattr(session, "user_interface", None),
                "method": getattr(session, "method", None) or "",
                "event": getattr(session, "event", None),
                "event_count": getattr(session, "event_count", None),
                "location": getattr(session, "location", None),
                "start_time": _format_time(
                    getattr(session, "start_time", None), timezone
                ),
                "end_time": _format_time(getattr(session, "end_time", None), timezone),
                "identifying_details": getattr(session, "identifying_details", None),
            }
        )
    return sessions


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            start=dict(type="str"),
            end=dict(type="str"),
            timezone=dict(type="str"),
            user=dict(type="str"),
            event=dict(type="list", elements="str"),
            user_interface=dict(type="list", elements="str", choices=INTERFACE_CHOICES),
            method=dict(type="list", elements="str", choices=METHOD_CHOICES),
            limit=dict(type="int"),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    if not HAS_PYTZ:
        module.fail_json(msg="pytz is required for this module")
    if module.params["limit"] is not None and module.params["limit"] < 1:
        module.fail_json(msg="limit must be a positive integer")

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg=(
                "FlashBlade REST version not supported. "
                "Minimum version required: {0} (Purity//FB 3.3.0+)"
            ).format(MIN_REQUIRED_API_VERSION)
        )

    timezone = _get_timezone(module, blade)
    sessions = _list_sessions(module, blade, timezone)
    module.exit_json(changed=False, purefb_sessions=sessions)


if __name__ == "__main__":
    main()
