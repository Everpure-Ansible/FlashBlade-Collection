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
module: purefb_support_diagnostics
version_added: '1.30.0'
short_description: Run FlashBlade self-diagnostics and report the results
description:
- Start an on-array self-diagnostics run (the built-in health checks) over
  an analysis window, optionally wait for it to finish, and return the
  per-test results with their severities and remediation details.
- Diagnostics runs are non-destructive. The array keeps the last 10 runs
  only; older runs are discarded.
- Requires FlashBlade REST API version 2.16 or later (Purity//FB 4.5.2+).
  The diagnostics tool version read-back (C(tools)) requires REST API 2.24
  or later (Purity//FB 4.6.8+) and is C(null) on older arrays.
- I(state=run) starts a new run every time it executes, so it is not
  idempotent - the same task run twice in a play produces two runs. The
  array refuses to start a run while another is in progress; in that case
  the module reports the run in progress instead and does not report a
  change. I(state=report) only reads and never reports a change.
- Updating the diagnostics tool set from a downloaded bundle is a dark-site
  support workflow and is not exposed by this module.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  state:
    description:
    - C(run) starts a diagnostics run. In check mode nothing is started and
      the latest retained run is reported instead.
    - C(report) reports the latest retained run, or the run selected with
      I(task), without starting one.
    type: str
    default: run
    choices: [ run, report ]
  start_time:
    description:
    - Start of the analysis window, in the format C(YYYY-MM-DD hh:mm:ss),
      interpreted in I(timezone).
    - Defaults to one hour before I(end_time).
    - Only used with I(state=run).
    type: str
  end_time:
    description:
    - End of the analysis window, in the format C(YYYY-MM-DD hh:mm:ss),
      interpreted in I(timezone).
    - Defaults to the current time.
    - Only used with I(state=run).
    type: str
  timezone:
    description:
    - Timezone in which I(start_time) and I(end_time) are interpreted,
      for example C(Europe/London).
    - Defaults to the timezone of the host running the module.
    type: str
  wait:
    description:
    - Wait for the run to complete before returning. When C(false) the run
      is returned as the array reports it immediately after starting, with
      no C(details).
    - With I(state=report), wait for the selected run if it is still in
      progress.
    type: bool
    default: true
  timeout:
    description:
    - Maximum time, in seconds, to wait for the run to complete.
    type: int
    default: 900
  severity:
    description:
    - Only return test results of these severities. All results are
      returned when not set.
    type: list
    elements: str
    choices: [ info, warning, critical ]
  task:
    description:
    - Index of the retained run to report. The latest run is reported when
      not set.
    - Only used with I(state=report).
    type: int
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Run diagnostics over the last hour and wait for the results
  everpure.flashblade.purefb_support_diagnostics:
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
  register: diag

- name: Fail the play when any check is critical
  ansible.builtin.assert:
    that: diag.task.severity_count.critical == 0
    fail_msg: >-
      Critical checks: {{ diag.details | selectattr('severity', 'equalto', 'critical')
      | map(attribute='test_name') | join(', ') }}

- name: Run diagnostics over an explicit window, reporting warnings and criticals only
  everpure.flashblade.purefb_support_diagnostics:
    start_time: "2026-03-01 08:00:00"
    end_time: "2026-03-01 10:00:00"
    timezone: Europe/London
    severity:
      - warning
      - critical
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Start a run without waiting for it
  everpure.flashblade.purefb_support_diagnostics:
    wait: false
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Report the latest retained run, waiting if it is still in progress
  everpure.flashblade.purefb_support_diagnostics:
    state: report
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Report the results of run 3
  everpure.flashblade.purefb_support_diagnostics:
    state: report
    task: 3
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = r"""
task:
  description:
  - The diagnostics run that was started or selected.
  - C(null) when I(state=report) finds no retained run.
  returned: success
  type: dict
  contains:
    index:
      description: Index of the run on the array.
      type: int
      sample: 3
    task_id:
      description: Unique ID of the run.
      type: str
      sample: 7c0a8d5e-3f2b-4c1d-9e8f-0a1b2c3d4e5f
    status:
      description: Status of the run, such as C(queued), C(running), C(completed) or C(failed).
      type: str
      sample: completed
    version:
      description: Version of the diagnostics tool set that produced the run.
      type: str
      sample: default
    start_time:
      description: When the run started, in seconds since the UNIX epoch.
      type: int
      sample: 1794902848
    analysis_period:
      description: Analysis window of the run, in seconds since the UNIX epoch.
      type: dict
      contains:
        start_time:
          description: Start of the window.
          type: int
        end_time:
          description: End of the window.
          type: int
    severity_count:
      description: Number of test results per severity.
      type: dict
      sample: {"info": 198, "warning": 4, "critical": 1}
details:
  description:
  - Test results of the run, filtered by I(severity) when set.
  - Empty until the run has completed.
  returned: success
  type: list
  elements: dict
  contains:
    index:
      description: Index of the test, as C(A.B) where C(A) is the run index.
      type: float
      sample: 3.42
    test_type:
      description: Category of the test.
      type: str
      sample: SYSTEM HEALTH (REAL-TIME)
    test_name:
      description: Name of the test.
      type: str
      sample: Watchers check
    severity:
      description: C(info), C(warning) or C(critical).
      type: str
      sample: warning
    result_details:
      description: Result of the test, including remediation hints when the array provides them.
      type: str
tools:
  description:
  - Version of the diagnostics tool set on the array and when it was last
    updated.
  - C(null) on arrays before REST API 2.24.
  returned: success
  type: dict
  contains:
    version:
      description: Version of the diagnostics tool set.
      type: str
      sample: default
    last_updated:
      description: When the tool set was last updated, C(null) for the built-in set.
      type: int
"""

import datetime
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.everpure.flashblade.plugins.module_utils.purefb import (
    get_system,
    purefb_argument_spec,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.common import (
    get_error_message,
    get_local_tz,
    get_rest_api_version,
    wait_for,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.version import (
    LooseVersion,
)

MIN_REQUIRED_API_VERSION = "2.16"
SETTINGS_API_VERSION = "2.24"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_WINDOW_SECONDS = 3600
TERMINAL_STATES = ("completed", "failed")
IN_PROGRESS_ERROR = "already running"


def _resolve_timezone(module):
    """Return the tzinfo the window times are interpreted in.

    The zone is I(timezone) or, when unset, the local zone of the host
    running the module. UTC is served by the standard library directly so
    the default works on hosts without system time zone data.
    """
    tz_name = module.params["timezone"] or get_local_tz(module)
    if tz_name == "UTC":
        return datetime.timezone.utc
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        module.fail_json(msg="Timezone {0} is not valid".format(tz_name))
        return None


def _to_epoch_seconds(module, name, tzinfo):
    """Convert the YYYY-MM-DD hh:mm:ss value of parameter ``name`` to epoch seconds."""
    value = module.params[name]
    try:
        naive = datetime.datetime.strptime(value, TIME_FORMAT)
    except ValueError:
        module.fail_json(
            msg=(
                '{0} value "{1}" is not a valid date/time. '
                'Expected format is "YYYY-MM-DD hh:mm:ss"'
            ).format(name, value)
        )
        return None
    return int(naive.replace(tzinfo=tzinfo).timestamp())


def _analysis_window(module):
    """Return the POST keyword arguments describing the analysis window.

    The array requires both ends of the window and, despite the SDK
    describing them as milliseconds, accepts them only as seconds since the
    epoch. A missing end defaults to now and a missing start to one hour
    before the end, mirroring the array's own default window.
    """
    tzinfo = None
    if module.params["start_time"] or module.params["end_time"]:
        tzinfo = _resolve_timezone(module)
    if module.params["end_time"]:
        end = _to_epoch_seconds(module, "end_time", tzinfo)
    else:
        end = int(time.time())
    if module.params["start_time"]:
        start = _to_epoch_seconds(module, "start_time", tzinfo)
    else:
        start = end - DEFAULT_WINDOW_SECONDS
    if start >= end:
        module.fail_json(msg="start_time must be earlier than end_time")
    return {"analysis_period_start_time": start, "analysis_period_end_time": end}


def _severity_counts(run):
    counts = {"info": 0, "warning": 0, "critical": 0}
    for entry in getattr(run, "severity_count", None) or []:
        severity = getattr(entry, "severity", None)
        if severity:
            counts[severity] = getattr(entry, "count", None) or 0
    return counts


def _task_dict(run):
    if run is None:
        return None
    period = getattr(run, "analysis_period", None)
    return {
        "index": getattr(run, "index", None),
        "task_id": getattr(run, "task_id", None),
        "status": getattr(run, "status", None),
        "version": getattr(run, "version", None),
        "start_time": getattr(run, "start_time", None),
        "analysis_period": {
            "start_time": getattr(period, "start_time", None),
            "end_time": getattr(period, "end_time", None),
        },
        "severity_count": _severity_counts(run),
    }


def _list_runs(module, blade):
    res = blade.get_support_diagnostics()
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to list support diagnostics runs. Error: {0}".format(
                get_error_message(res)
            )
        )
        return []
    return list(res.items)


def _find_run(runs, task_id):
    for run in runs:
        if getattr(run, "task_id", None) == task_id:
            return run
    return None


def _latest_run(runs):
    if not runs:
        return None
    return max(
        runs,
        key=lambda run: (
            getattr(run, "start_time", None) or 0,
            getattr(run, "index", None) or 0,
        ),
    )


def _select_run(module, runs):
    """Return the run with index I(task), or the latest run when unset."""
    index = module.params["task"]
    if index is None:
        return _latest_run(runs)
    for run in runs:
        if getattr(run, "index", None) == index:
            return run
    module.fail_json(
        msg=(
            "Diagnostics run with index {0} was not found. "
            "Only the last 10 runs are retained."
        ).format(index)
    )
    return None


def _get_details(module, blade, run):
    res = blade.get_support_diagnostics_details(
        filter="task_id='{0}'".format(run.task_id)
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read support diagnostics details. Error: {0}".format(
                get_error_message(res)
            )
        )
        return []
    wanted = module.params["severity"]
    details = []
    for item in list(res.items):
        severity = getattr(item, "severity", None)
        if wanted and severity not in wanted:
            continue
        details.append(
            {
                "index": getattr(item, "index", None),
                "test_type": getattr(item, "test_type", None),
                "test_name": getattr(item, "test_name", None),
                "severity": severity,
                "result_details": getattr(item, "result_details", None),
            }
        )
    return details


def _get_tools(module, blade, api_version):
    if LooseVersion(SETTINGS_API_VERSION) > LooseVersion(api_version):
        return None
    res = blade.get_support_diagnostics_settings()
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read support diagnostics settings. Error: {0}".format(
                get_error_message(res)
            )
        )
        return None
    items = list(res.items)
    if not items:
        return None
    return {
        "version": getattr(items[0], "version", None),
        "last_updated": getattr(items[0], "last_updated", None),
    }


def _wait_for_run(module, blade, run):
    """Poll the run until it completes; fail on a failed run or on timeout."""
    task_id = run.task_id
    label = getattr(run, "index", None)
    if label is None:
        label = task_id

    def probe():
        return _find_run(_list_runs(module, blade), task_id)

    def is_done(current):
        return current is not None and getattr(current, "status", None) == "completed"

    def is_failed(current):
        if current is not None and getattr(current, "status", None) == "failed":
            return "diagnostics run {0} reported status failed".format(label)
        return None

    def detail(current):
        if current is None:
            return "run {0} is no longer listed by the array".format(label)
        return "status {0}".format(getattr(current, "status", None))

    return wait_for(
        module,
        probe,
        is_done,
        module.params["timeout"],
        "diagnostics run {0} to complete".format(label),
        is_failed=is_failed,
        detail=detail,
        interval=10,
        max_interval=30,
        skip_in_check_mode=False,
    )


def _exit(module, blade, api_version, run, changed):
    details = []
    if run is not None and getattr(run, "status", None) == "completed":
        details = _get_details(module, blade, run)
    module.exit_json(
        changed=changed,
        task=_task_dict(run),
        details=details,
        tools=_get_tools(module, blade, api_version),
    )


def run_diagnostics(module, blade, api_version):
    window = _analysis_window(module)
    if module.check_mode:
        _exit(module, blade, api_version, _latest_run(_list_runs(module, blade)), True)
    changed = True
    res = blade.post_support_diagnostics(**window)
    if res.status_code == 200:
        items = list(res.items)
        run = items[0] if items else None
        if run is None:
            module.fail_json(
                msg="The array accepted the diagnostics request but returned no run."
            )
    else:
        message = get_error_message(res)
        in_progress = []
        if IN_PROGRESS_ERROR in str(message).lower():
            in_progress = [
                run
                for run in _list_runs(module, blade)
                if getattr(run, "status", None) not in TERMINAL_STATES
            ]
        if not in_progress:
            module.fail_json(
                msg="Failed to start support diagnostics. Error: {0}".format(message)
            )
        run = in_progress[0]
        changed = False
        module.warn(
            (
                "Diagnostics run {0} is already in progress; reporting it instead "
                "of starting a new run. Array response: {1}"
            ).format(getattr(run, "index", run.task_id), message)
        )
    if module.params["wait"]:
        run = _wait_for_run(module, blade, run)
    _exit(module, blade, api_version, run, changed)


def report_diagnostics(module, blade, api_version):
    run = _select_run(module, _list_runs(module, blade))
    if (
        run is not None
        and module.params["wait"]
        and getattr(run, "status", None) not in TERMINAL_STATES
    ):
        run = _wait_for_run(module, blade, run)
    _exit(module, blade, api_version, run, False)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(type="str", default="run", choices=["run", "report"]),
            start_time=dict(type="str"),
            end_time=dict(type="str"),
            timezone=dict(type="str"),
            wait=dict(type="bool", default=True),
            timeout=dict(type="int", default=900),
            severity=dict(
                type="list",
                elements="str",
                choices=["info", "warning", "critical"],
            ),
            task=dict(type="int"),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    if module.params["timeout"] <= 0:
        module.fail_json(msg="timeout must be a positive number of seconds")

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg=(
                "FlashBlade REST version not supported. "
                "Minimum version required: {0} (Purity//FB 4.5.2+)"
            ).format(MIN_REQUIRED_API_VERSION)
        )

    if module.params["state"] == "run":
        run_diagnostics(module, blade, api_version)
    else:
        report_diagnostics(module, blade, api_version)


if __name__ == "__main__":
    main()
