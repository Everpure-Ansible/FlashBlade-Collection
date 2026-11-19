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
module: purefb_audits
version_added: '1.30.0'
short_description: List FlashBlade audit trail records
description:
- List the records of the FlashBlade management audit trail, optionally
  narrowed to a time window, a user, a command, a user interface, a
  correlation ID or the scopes (realms and/or the array) a record affected.
- Available on every FlashBlade REST API version (2.0 and later). The
  C(context), C(correlation_id) and C(system_event) fields of a record, the
  I(correlation_id) option, the system-event filtering behind
  I(include_system_events) and the fleet I(context) option require REST API
  version 2.28 or later (Purity//FB 4.8.4+). The C(scopes) field and the
  I(scopes) option require REST API version 2.20 or later
  (Purity//FB 4.6.3+).
- The activity of a realm is identified by C(scopes), which lists the realms
  and/or the array a record affected. A realm is listed under its current
  name, while C(arguments) keeps the names used when the command was run, so
  use I(scopes) rather than a match on C(arguments) to read the records of
  one realm.
- An identity whose management access is scoped to realms is only returned
  the records of those realms, and the C(scopes) of each record then lists
  only those realms.
- Reading the audit trail never changes the array, so the module always
  reports C(changed=false) and performs the read in check mode as well.
- The I(user), I(command), I(correlation_id) and I(scopes) values must not
  contain a single quote, which the array query syntax cannot escape. Such a
  value is refused before the array is contacted.
- Timezone names are resolved with the Python C(zoneinfo) module on the host
  running the module, which needs the system timezone database or the
  C(tzdata) Python package. C(UTC) works without either.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  start:
    description:
    - Only records logged at or after this date and time are returned.
    - Interpreted in the timezone given by I(timezone), or in the timezone
      resolved when I(timezone) is not provided.
    - Expected format C(YYYY-MM-DD hh:mm:ss).
    type: str
  end:
    description:
    - Only records logged at or before this date and time are returned.
    - Interpreted in the same timezone as I(start) and must not be earlier
      than I(start).
    - Expected format C(YYYY-MM-DD hh:mm:ss).
    type: str
  timezone:
    description:
    - IANA timezone in which I(start) and I(end) are interpreted and in which
      the C(time) of each returned record is reported, for example
      C(America/New_York).
    - If not provided, the timezone configured on the FlashBlade receiving
      the request is used, also when I(context) names another fleet member.
      When that timezone cannot be read the module warns and uses the local
      timezone of the host running the module.
    type: str
  user:
    description:
    - Only return records of commands run by this user.
    type: str
  command:
    description:
    - Only return records of this top-level command, for example C(purefs).
    type: str
  user_interface:
    description:
    - Only return records of commands run through this user interface.
    type: str
    choices: [ CLI, GUI, REST ]
  correlation_id:
    description:
    - Only return records whose correlation ID starts with this value.
    - A correlation ID connects the system actions triggered by a user action
      to that user action. Combine with I(include_system_events=true) to see
      the triggered system actions as well.
    - Requires REST API version 2.28 or later.
    type: str
  scopes:
    description:
    - Only return records that affected at least one of these scopes. A scope
      is a realm or the array itself, so each entry is the name of a realm or
      the name of the array.
    - With several entries a record is returned when it affected any one of
      them. Empty entries are ignored.
    - The array treats C(*) in an entry as a wildcard, so C(tenant*) selects
      the records of every realm whose name starts with C(tenant).
    - The array matches the names without regard to case.
    - The C(scopes) of each returned record then lists only the scopes that
      matched, not every scope the record affected.
    - A realm that has been eradicated cannot be selected, because the array
      no longer holds its name. Its records are still returned when this
      option is not used.
    - Requires REST API version 2.20 or later.
    type: list
    elements: str
  include_system_events:
    description:
    - Whether records of system-initiated events are returned alongside the
      records of user-initiated events.
    - On REST API versions before 2.28 the array records user-initiated
      events only, so every record is returned regardless of this option.
    type: bool
    default: false
  newest_first:
    description:
    - Return the records newest first (the API sort C(time-)) instead of the
      array default of oldest first.
    - Combine with I(limit) to read the most recent records.
    type: bool
    default: false
  limit:
    description:
    - Maximum number of records to return. Must be at least 1.
    - When not provided every matching record is returned.
    type: int
  context:
    description:
    - Name of fleet member on which to perform the operation.
    - This requires the array receiving the request is a member of a fleet
      and the context name to be a member of the same fleet.
    - Requires REST API version 2.28 or later.
    type: str
    default: ""
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: List the records of one day, interpreted in the array timezone
  everpure.flashblade.purefb_audits:
    start: "2026-03-01 00:00:00"
    end: "2026-03-02 00:00:00"
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: List the 10 most recent records
  everpure.flashblade.purefb_audits:
    newest_first: true
    limit: 10
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: List the 10 most recent records of one realm
  everpure.flashblade.purefb_audits:
    scopes:
      - realm1
    newest_first: true
    limit: 10
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: List the REST commands run by a user since a date, with times in UTC
  everpure.flashblade.purefb_audits:
    user: svc-ansible
    user_interface: REST
    start: "2026-03-01 00:00:00"
    timezone: UTC
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: List every file system command, including system-initiated events
  everpure.flashblade.purefb_audits:
    command: purefs
    include_system_events: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: List a user action and the system actions it triggered
  everpure.flashblade.purefb_audits:
    correlation_id: 6f1c0b9e
    include_system_events: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = r"""
purefb_audits:
  description:
    - The audit records read from the array, in the order the array returned
      them.
    - A field the array did not record for an event is returned as C(none).
  returned: always
  type: list
  elements: dict
  contains:
    name:
      description: Sequence number of the record on the array.
      type: str
      sample: "1044"
    time:
      description:
        - When the command was run, as C(YYYY-MM-DD HH:MM:SS ZONE) in the
          timezone given by I(timezone) or the timezone resolved when
          I(timezone) is not provided.
      type: str
      sample: 2026-03-01 12:31:34 PST
    user:
      description: The user who ran the command.
      type: str
      sample: pureuser
    user_interface:
      description: The user interface the command was run through, C(CLI), C(GUI) or C(REST).
      type: str
      sample: REST
    ip_address:
      description: The IP address the command was run from.
      type: str
      sample: 10.10.10.20
    user_agent:
      description: The user agent of the client that ran the command.
      type: str
      sample: Ansible ansible_collections.everpure.flashblade.plugins.module_utils.purefb/1.5
    command:
      description: The top level command, which by convention starts with C(pure).
      type: str
      sample: purefs
    subcommand:
      description: The subcommand, which together with C(command) names the action.
      type: str
      sample: create
    arguments:
      description: The arguments provided to the command.
      type: str
      sample: --size 10G fs1
    origin:
      description: The name of the array the command originated from.
      type: str
      sample: flashblade1
    context:
      description:
        - The name of the fleet member or fleet the command was performed in.
        - Available from REST API version 2.28.
      type: str
      sample: flashblade1
    scopes:
      description:
        - The names of the realms and/or array the command affected.
        - A realm is listed under its current name. A realm that has been
          eradicated no longer has a name and is listed by its ID instead.
        - Only the matching scopes are listed when I(scopes) is used, and
          only the realms of the identity when the module runs as an identity
          scoped to realms.
        - Available from REST API version 2.20.
      type: list
      elements: str
      sample: ["flashblade1"]
    system_event:
      description:
        - Whether the record is a system-initiated event rather than an event
          invoked directly by a user.
        - Always C(false) before REST API version 2.28.
      type: bool
      sample: false
    correlation_id:
      description:
        - The identifier connecting a user action to the system actions it
          triggered. Only present on records that have related actions.
        - Available from REST API version 2.28.
      type: str
      sample: 6f1c0b9e-2d1a-4c53-9f0e-8b7e6a5d4c3b
  sample:
    - name: "1044"
      time: 2026-03-01 12:31:34 PST
      user: pureuser
      user_interface: CLI
      ip_address: 10.10.10.20
      user_agent: OpenSSH
      command: purefs
      subcommand: create
      arguments: --size 10G fs1
      origin: flashblade1
      context: flashblade1
      scopes: ["flashblade1"]
      system_event: false
      correlation_id: null
"""

import datetime
import zoneinfo

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

# The fleet context parameter and the context, correlation_id and
# system_event record fields all arrived together in REST 2.28.
AUDIT_CONTEXT_VERSION = "2.28"
# Records carry the realms and/or array they affected, and the array filters
# on them, from REST 2.20.
AUDIT_SCOPES_VERSION = "2.20"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def _tzinfo(timezone):
    """Return the tzinfo for the IANA timezone name ``timezone``.

    UTC comes straight from the standard library so it works without a
    timezone database. Every other name goes through zoneinfo, which raises
    ZoneInfoNotFoundError for a name it does not know and ValueError for a
    malformed key.
    """
    if timezone == "UTC":
        return datetime.timezone.utc
    return zoneinfo.ZoneInfo(timezone)


def _resolve_timezone(module, blade):
    """Return the IANA timezone the module interprets and reports times in.

    The timezone option wins; otherwise the array's configured timezone is
    used, falling back (with a warning) to the local timezone of the
    controller.
    """
    timezone = module.params["timezone"]
    if not timezone:
        res = blade.get_arrays()
        if res.status_code == 200:
            arrays = list(res.items)
            if arrays:
                timezone = getattr(arrays[0], "time_zone", None)
        if not timezone:
            timezone = get_local_tz(module)
            module.warn("Could not read the array timezone, using {0}".format(timezone))
    try:
        _tzinfo(timezone)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        module.fail_json(msg="Timezone {0} is not valid".format(timezone))
    return timezone


def _to_timestamp(module, name, timezone):
    """Convert the date/time in parameter ``name`` to epoch milliseconds.

    The value is localized in ``timezone`` for its own date, so the offset is
    right on either side of a daylight-saving change.
    """
    try:
        naive = datetime.datetime.strptime(module.params[name], TIME_FORMAT)
    except ValueError:
        module.fail_json(
            msg='{0} value {1} is not a valid date/time. Expected format is "YYYY-MM-DD hh:mm:ss"'.format(
                name, module.params[name]
            )
        )
    localized = naive.replace(tzinfo=_tzinfo(timezone))
    return int(localized.timestamp() * 1000)


def _scope_names(module):
    """Return the scope names to filter on, without empty entries or repeats.

    An empty entry is not a filter, as with the other filter options, and a
    name is sent to the array as given.
    """
    names = []
    for name in module.params["scopes"] or []:
        if name and name not in names:
            names.append(name)
    return names


def _validate_filter_values(module):
    """Refuse filter values the array query syntax cannot express.

    The values are single-quoted in the filter expression and the array has
    no escape for a quote inside a value (a backslash-escaped or a doubled
    quote is a syntax error), so such a value is refused up front.
    """
    for key in ("user", "command", "user_interface", "correlation_id"):
        value = module.params[key]
        if value and "'" in value:
            module.fail_json(
                msg="{0} value {1} must not contain a single quote".format(key, value)
            )
    for name in _scope_names(module):
        if "'" in name:
            module.fail_json(
                msg="scopes value {0} must not contain a single quote".format(name)
            )


def _build_filter(module, api_version, timezone):
    """Return the audit filter expression, or None when nothing is filtered."""
    parts = []
    start_ms = None
    if module.params["start"]:
        start_ms = _to_timestamp(module, "start", timezone)
        parts.append("time>={0}".format(start_ms))
    if module.params["end"]:
        end_ms = _to_timestamp(module, "end", timezone)
        if start_ms is not None and end_ms < start_ms:
            module.fail_json(
                msg="end {0} is earlier than start {1}".format(
                    module.params["end"], module.params["start"]
                )
            )
        parts.append("time<={0}".format(end_ms))
    for key in ("user", "command", "user_interface"):
        if module.params[key]:
            parts.append("{0}='{1}'".format(key, module.params[key]))
    if module.params["correlation_id"]:
        parts.append("correlation_id='{0}*'".format(module.params["correlation_id"]))
    scopes = _scope_names(module)
    if scopes:
        # A record matches when any one of the names is among its scopes.
        # The alternatives are parenthesised so that they join the other
        # parts of the filter as one condition.
        clause = " or ".join("scopes.name='{0}'".format(name) for name in scopes)
        parts.append("({0})".format(clause) if len(scopes) > 1 else clause)
    if not module.params["include_system_events"] and LooseVersion(
        AUDIT_CONTEXT_VERSION
    ) <= LooseVersion(api_version):
        # Older arrays have no system_event field, so the filter would be
        # rejected there. The boolean value must be quoted; unquoted the
        # array answers "Unable to parse query".
        parts.append("system_event='false'")
    if parts:
        return " and ".join(parts)
    return None


def _format_scopes(audit):
    """Return the scopes of an SDK audit record as a list of strings.

    A scope is reported by its name. The array drops the name of a realm once
    the realm is eradicated and keeps only its ID, so such a scope is reported
    by that ID, which stays the same on every read. An entry with neither is
    left out rather than returned as a null.
    """
    labels = []
    for scope in getattr(audit, "scopes", None) or []:
        label = getattr(scope, "name", None) or getattr(scope, "id", None)
        if label:
            labels.append(label)
    return labels


def _format_audit(audit, timezone):
    """Convert one SDK audit record to the dictionary the module returns.

    Records only carry the fields that apply to the event and the SDK models
    raise AttributeError for an absent field, so every field is read with a
    default.
    """
    event_time = getattr(audit, "time", None)
    if event_time is not None:
        event_time = datetime.datetime.fromtimestamp(
            event_time / 1000, tz=_tzinfo(timezone)
        ).strftime(TIME_FORMAT + " %Z")
    system_event = getattr(audit, "system_event", None)
    if system_event is None:
        system_event = False
    return {
        "name": getattr(audit, "name", None),
        "time": event_time,
        "user": getattr(audit, "user", None),
        "user_interface": getattr(audit, "user_interface", None),
        "ip_address": getattr(audit, "ip_address", None),
        "user_agent": getattr(audit, "user_agent", None),
        "command": getattr(audit, "command", None),
        "subcommand": getattr(audit, "subcommand", None),
        "arguments": getattr(audit, "arguments", None),
        "origin": getattr(getattr(audit, "origin", None), "name", None),
        "context": getattr(getattr(audit, "context", None), "name", None),
        "scopes": _format_scopes(audit),
        "system_event": system_event,
        "correlation_id": getattr(audit, "correlation_id", None),
    }


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            start=dict(type="str"),
            end=dict(type="str"),
            timezone=dict(type="str"),
            user=dict(type="str"),
            command=dict(type="str"),
            user_interface=dict(type="str", choices=["CLI", "GUI", "REST"]),
            correlation_id=dict(type="str"),
            scopes=dict(type="list", elements="str"),
            include_system_events=dict(type="bool", default=False),
            newest_first=dict(type="bool", default=False),
            limit=dict(type="int"),
            context=dict(type="str", default=""),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    if module.params["limit"] is not None and module.params["limit"] < 1:
        module.fail_json(msg="limit must be at least 1")
    _validate_filter_values(module)

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if _scope_names(module) and LooseVersion(AUDIT_SCOPES_VERSION) > LooseVersion(
        api_version
    ):
        module.fail_json(
            msg=(
                "The scopes option requires FlashBlade REST version {0} "
                "or later (Purity//FB 4.6.3+)"
            ).format(AUDIT_SCOPES_VERSION)
        )
    if LooseVersion(AUDIT_CONTEXT_VERSION) > LooseVersion(api_version):
        for option in ("context", "correlation_id"):
            if module.params[option]:
                module.fail_json(
                    msg=(
                        "The {0} option requires FlashBlade REST version {1} "
                        "or later (Purity//FB 4.8.4+)"
                    ).format(option, AUDIT_CONTEXT_VERSION)
                )

    timezone = _resolve_timezone(module, blade)
    kwargs = {}
    filter_string = _build_filter(module, api_version, timezone)
    if filter_string:
        kwargs["filter"] = filter_string
    if module.params["limit"]:
        # The array returns at most this many records.
        kwargs["limit"] = module.params["limit"]
    if module.params["newest_first"]:
        kwargs["sort"] = ["time-"]
    if module.params["context"]:
        kwargs["context_names"] = [module.params["context"]]

    res = blade.get_audits(**kwargs)
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to get audit records. Error: {0}".format(get_error_message(res))
        )
    audits = [_format_audit(audit, timezone) for audit in list(res.items)]
    module.exit_json(changed=False, purefb_audits=audits)


if __name__ == "__main__":
    main()
