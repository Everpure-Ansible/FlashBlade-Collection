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
module: purefb_software
version_added: '1.30.0'
short_description: Manage Purity//FB software packages and upgrade checks
description:
- Run the Purity//FB pre-upgrade checks, download a Purity//FB software
  package from the Everpure cloud, stage a software bundle from a URL, or
  delete a downloaded package.
- Installing software is not part of this module.
- Upgrade checks require FlashBlade REST API version 2.16 or later
  (Purity//FB 4.5.2+). Software bundles require 2.24 (Purity//FB 4.6.8+).
  Package download and deletion, and checks against a local bundle,
  require 2.30 (Purity//FB 4.8.8+).
- Read the software catalogue, packages, bundles and check results back
  with the C(software) subset of M(everpure.flashblade.purefb_info).
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  state:
    description:
    - C(check) runs the pre-upgrade checks for I(version). A check task for
      the same version that already passed is left alone unless I(force) is
      set, and a task that is still running is waited on rather than
      duplicated. The module fails when the checks report a failure.
    - The array keeps one check task per target version. A forced re-run
      replaces the previous result for I(version), and a check the array
      refuses to start can still be recorded as a failed task for it.
    - C(downloaded) downloads the Purity//FB package for I(version) from the
      Everpure cloud. The array refuses the request while a different
      uninstalled package is present. A failed download of the same version
      is deleted and retried only when I(force) is set.
    - C(staged) downloads a software bundle from I(bundle_source) onto the
      array. The array cancels any download that is already running.
    - C(absent) deletes the software package for I(version), cancelling its
      download when one is in progress.
    type: str
    default: check
    choices: [ check, downloaded, staged, absent ]
  name:
    description:
    - Name of the software.
    type: str
    default: Purity//FB
  version:
    description:
    - Target software version, for example C(4.8.9).
    - Required for I(state=check), I(state=downloaded) and I(state=absent).
    type: str
  local:
    description:
    - Run the upgrade checks from the software bundle staged on the array
      instead of the latest checks from the Everpure cloud.
    - The bundle must be no more than 60 days old. Arrays with phone home
      disabled always check against the local bundle.
    - Only used with I(state=check). Requires REST API version 2.30.
    type: bool
    default: false
  bundle_source:
    description:
    - URL of the software bundle to stage. HTTP, HTTPS and FTP sources are
      supported.
    - Required for I(state=staged).
    type: str
  force:
    description:
    - With I(state=check), run the checks again although a task for
      I(version) already passed. The previous result for I(version) is
      replaced, as the array keeps one check task per target version.
    - With I(state=downloaded), delete a failed download of I(version)
      before downloading it again.
    type: bool
    default: false
  wait:
    description:
    - Wait for the check, download or staging to finish and report its
      result.
    - Defaults to C(true) for I(state=check) and to C(false) for
      I(state=downloaded) and I(state=staged), whose downloads can take a
      long time. Read the progress back with the C(software) subset of
      M(everpure.flashblade.purefb_info).
    type: bool
  timeout:
    description:
    - Seconds to wait for the operation to finish when I(wait) is set.
    - The module fails when the time runs out. The operation keeps running
      on the array.
    type: int
    default: 600
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Run the pre-upgrade checks for Purity//FB 4.8.9 and wait for the result
  everpure.flashblade.purefb_software:
    state: check
    version: 4.8.9
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
  register: result

- name: Show the individual check results
  debug:
    var: result.software_check.checks

- name: Run the checks again although an earlier run passed
  everpure.flashblade.purefb_software:
    state: check
    version: 4.8.9
    force: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Run the checks from the bundle staged on a dark site array
  everpure.flashblade.purefb_software:
    state: check
    version: 4.8.9
    local: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Start downloading Purity//FB 4.8.9 without waiting for it
  everpure.flashblade.purefb_software:
    state: downloaded
    version: 4.8.9
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Download Purity//FB 4.8.9 again after a failed download, waiting up to an hour
  everpure.flashblade.purefb_software:
    state: downloaded
    version: 4.8.9
    force: true
    wait: true
    timeout: 3600
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Stage a software bundle on a dark site array
  everpure.flashblade.purefb_software:
    state: staged
    bundle_source: https://repo.example.com/purity_fb_4.8.9.tar
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete the downloaded Purity//FB 4.8.9 package
  everpure.flashblade.purefb_software:
    state: absent
    version: 4.8.9
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = r"""
software_check:
  description: The check task for the requested version.
  returned: when I(state=check)
  type: dict
  contains:
    id:
      description: ID of the check task.
      type: str
    name:
      description: Name of the check task.
      type: str
      sample: Purity//FB_4.8.9
    status:
      description: Status of the task, one of C(queued), C(running), C(passed) or C(failed).
      type: str
    software_name:
      description: Name of the software the checks tested.
      type: str
    software_version:
      description: Software version field of the task as reported by the array. The target version is the last upgrade hop.
      type: str
    software_upgrade_hops:
      description: Versions the tested upgrade path passes through, ending with the target version.
      type: list
      elements: str
      sample: ["4.8.8", "4.8.9"]
    start_time:
      description: Start time of the task as reported by the array.
      type: int
    end_time:
      description: End time of the task as reported by the array.
      type: int
    details:
      description: Detailed reason for the status.
      type: str
    checks:
      description: The individual upgrade checks.
      type: list
      elements: dict
      contains:
        name:
          description: Name of the check.
          type: str
        status:
          description: Status of the check, one of C(running), C(passed) or C(failed).
          type: str
        details:
          description: Result details of the check.
          type: str
software:
  description: The software package for the requested version.
  returned: when I(state=downloaded)
  type: dict
  contains:
    id:
      description: ID of the package.
      type: str
    name:
      description: Name of the software.
      type: str
    version:
      description: Version of the package.
      type: str
    status:
      description: Status of the package, one of C(new), C(downloading), C(downloaded) or C(download_failed).
      type: str
    progress:
      description: Download progress as a decimal fraction.
      type: float
    details:
      description: Detailed reason for the status.
      type: str
    payload_id:
      description: Checksum of the package.
      type: str
    upgrade_hops:
      description: Versions the upgrade passes through.
      type: list
      elements: str
software_bundle:
  description: The software bundle matching I(bundle_source).
  returned: when I(state=staged)
  type: dict
  contains:
    id:
      description: ID of the bundle.
      type: str
    source:
      description: Location the bundle is downloaded from.
      type: str
    status:
      description: Status of the bundle, one of C(downloading), C(verifying), C(ready) or C(failed).
      type: str
    software_name:
      description: Name of the software in the bundle.
      type: str
    software_version:
      description: Version of the software in the bundle.
      type: str
    download_progress:
      description: Download progress as a decimal fraction.
      type: float
    bytes_downloaded:
      description: Bytes downloaded so far.
      type: int
    bytes_total:
      description: Total bytes to download.
      type: int
    created:
      description: Creation time of the bundle as reported by the array.
      type: int
    details:
      description: Detailed reason for the status.
      type: str
"""


HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        SoftwareBundlePost,
        SoftwarePost,
    )
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
    poll_until,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.version import (
    LooseVersion,
)

CHECK_API_VERSION = "2.16"
BUNDLE_API_VERSION = "2.24"
SOFTWARE_API_VERSION = "2.30"
POLL_INTERVAL = 10

CHECK_FINISHED = ("passed", "failed")
DOWNLOAD_FINISHED = ("downloaded", "download_failed")
BUNDLE_FINISHED = ("ready", "failed")


def _check_to_dict(task):
    if task is None:
        return {}
    return {
        "id": getattr(task, "id", None),
        "name": getattr(task, "name", None),
        "status": getattr(task, "status", None),
        "software_name": getattr(task, "software_name", None),
        "software_version": getattr(task, "software_version", None),
        "software_upgrade_hops": list(
            getattr(task, "software_upgrade_hops", None) or []
        ),
        "start_time": getattr(task, "start_time", None),
        "end_time": getattr(task, "end_time", None),
        "details": getattr(task, "details", None),
        "checks": [
            {
                "name": getattr(check, "name", None),
                "status": getattr(check, "status", None),
                "details": getattr(check, "details", None),
            }
            for check in (getattr(task, "checks", None) or [])
        ],
    }


def _software_to_dict(package):
    if package is None:
        return {}
    return {
        "id": getattr(package, "id", None),
        "name": getattr(package, "name", None),
        "version": getattr(package, "version", None),
        "status": getattr(package, "status", None),
        "progress": getattr(package, "progress", None),
        "details": getattr(package, "details", None),
        "payload_id": getattr(package, "payload_id", None),
        "upgrade_hops": list(getattr(package, "upgrade_hops", None) or []),
    }


def _bundle_to_dict(bundle):
    if bundle is None:
        return {}
    return {
        "id": getattr(bundle, "id", None),
        "source": getattr(bundle, "source", None),
        "status": getattr(bundle, "status", None),
        "software_name": getattr(bundle, "software_name", None),
        "software_version": getattr(bundle, "software_version", None),
        "download_progress": getattr(bundle, "download_progress", None),
        "bytes_downloaded": getattr(bundle, "bytes_downloaded", None),
        "bytes_total": getattr(bundle, "bytes_total", None),
        "created": getattr(bundle, "created", None),
        "details": getattr(bundle, "details", None),
    }


def _list_items(module, blade, method, what, **kwargs):
    res = getattr(blade, method)(**kwargs)
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to get {0}. Error: {1}".format(what, get_error_message(res))
        )
    return list(res.items)


def _latest(items, field):
    """The newest item by ``field``; the last listed wins a tie."""
    if not items:
        return None
    return sorted(items, key=lambda item: getattr(item, field, None) or 0)[-1]


def _check_matches(task, name, version):
    """Whether a check task was run for software ``name`` at target ``version``.

    The array names a task ``<software>_<target>`` and ends its upgrade hops
    with the target. ``software_version`` is not relied on: the array has
    been seen filling it with the running version rather than the target.
    """
    if getattr(task, "software_name", None) not in (None, name):
        return False
    hops = list(getattr(task, "software_upgrade_hops", None) or [])
    return getattr(task, "name", None) == "{0}_{1}".format(name, version) or (
        bool(hops) and hops[-1] == version
    )


def _get_check(module, blade, name, version):
    tasks = _list_items(module, blade, "get_software_check", "software check tasks")
    return _latest(
        [task for task in tasks if _check_matches(task, name, version)], "start_time"
    )


def _recorded_check(blade, name, version):
    """The newest check task for the target; a failed GET counts as none.

    Used after a refused POST, so a GET error must not hide the POST error.
    """
    res = blade.get_software_check()
    if res.status_code != 200:
        return None
    tasks = list(res.items or [])
    return _latest(
        [task for task in tasks if _check_matches(task, name, version)], "start_time"
    )


def _fetch_check(module, blade, task_id):
    items = _list_items(
        module, blade, "get_software_check", "software check task", ids=[task_id]
    )
    return items[0] if items else None


def _get_package(module, blade, name, version):
    for package in _list_items(module, blade, "get_software", "software packages"):
        if (
            getattr(package, "name", None) == name
            and getattr(package, "version", None) == version
        ):
            return package
    return None


def _get_bundle(module, blade, source):
    bundles = _list_items(module, blade, "get_software_bundle", "software bundles")
    return _latest(
        [bundle for bundle in bundles if getattr(bundle, "source", None) == source],
        "created",
    )


def _fetch_bundle(module, blade, bundle_id):
    items = _list_items(
        module, blade, "get_software_bundle", "software bundle", ids=[bundle_id]
    )
    return items[0] if items else None


def _wait(module, fetch, finished, what, changed):
    """Poll ``fetch`` until the object reaches a final status; fail on timeout."""

    def done(item):
        return item is not None and getattr(item, "status", None) in finished

    item, timed_out = poll_until(fetch, done, module.params["timeout"], POLL_INTERVAL)
    if timed_out:
        module.fail_json(
            changed=changed,
            msg=(
                "Timed out after {0} seconds waiting for {1} (status: {2}). "
                "The operation continues on the array."
            ).format(module.params["timeout"], what, getattr(item, "status", None)),
        )
    return item


def _fail_on_check_failure(module, task, changed):
    if getattr(task, "status", None) != "failed":
        return
    failed = [
        getattr(check, "name", None)
        for check in (getattr(task, "checks", None) or [])
        if getattr(check, "status", None) == "failed"
    ]
    module.fail_json(
        changed=changed,
        msg="Software check {0} failed. Failed checks: {1}".format(
            getattr(task, "name", None),
            ", ".join(failed) or getattr(task, "details", None) or "none reported",
        ),
        software_check=_check_to_dict(task),
    )


def _fail_on_download_failure(module, package, changed):
    if getattr(package, "status", None) != "download_failed":
        return
    module.fail_json(
        changed=changed,
        msg="Download of {0} {1} failed. {2}".format(
            getattr(package, "name", None),
            getattr(package, "version", None),
            getattr(package, "details", None) or "",
        ).strip(),
        software=_software_to_dict(package),
    )


def _fail_on_bundle_failure(module, bundle, changed):
    if getattr(bundle, "status", None) != "failed":
        return
    module.fail_json(
        changed=changed,
        msg="Software bundle download from {0} failed. {1}".format(
            getattr(bundle, "source", None), getattr(bundle, "details", None) or ""
        ).strip(),
        software_bundle=_bundle_to_dict(bundle),
    )


def run_check(module, blade):
    name = module.params["name"]
    version = module.params["version"]
    task = _get_check(module, blade, name, version)
    status = getattr(task, "status", None)
    if task is not None and status in ("queued", "running"):
        # a check is already in progress for this version; never start another
        if module.params["wait"] and not module.check_mode:
            task_id = task.id
            task = _wait(
                module,
                lambda: _fetch_check(module, blade, task_id),
                CHECK_FINISHED,
                "software check {0}".format(task.name),
                changed=False,
            )
            _fail_on_check_failure(module, task, changed=False)
        module.exit_json(changed=False, software_check=_check_to_dict(task))
    if task is not None and status == "passed" and not module.params["force"]:
        module.exit_json(changed=False, software_check=_check_to_dict(task))
    # no task yet, the last one failed, or a re-run was forced
    if module.check_mode:
        module.exit_json(changed=True, software_check=_check_to_dict(task))
    kwargs = {"software_names": [name], "software_versions": [version]}
    if module.params["local"]:
        kwargs["local"] = True
    res = blade.post_software_check(**kwargs)
    if res.status_code != 200:
        # the array can record a failed task for a check it refuses, which
        # replaces the previous result for the version
        recorded = _recorded_check(blade, name, version)
        replaced = recorded is not None and getattr(recorded, "id", None) != getattr(
            task, "id", None
        )
        module.fail_json(
            changed=replaced,
            msg="Failed to start software check for {0} {1}. Error: {2}".format(
                name, version, get_error_message(res)
            ),
            software_check=_check_to_dict(recorded if replaced else task),
        )
    items = list(res.items or [])
    task = items[0] if items else _get_check(module, blade, name, version)
    if module.params["wait"] and task is not None:
        task_id = task.id
        task = _wait(
            module,
            lambda: _fetch_check(module, blade, task_id),
            CHECK_FINISHED,
            "software check {0}".format(task.name),
            changed=True,
        )
        _fail_on_check_failure(module, task, changed=True)
    module.exit_json(changed=True, software_check=_check_to_dict(task))


def _delete_package(module, blade, name, version):
    res = blade.delete_software(names=[name], software_versions=[version])
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to delete software {0} {1}. Error: {2}".format(
                name, version, get_error_message(res)
            )
        )


def download_package(module, blade):
    name = module.params["name"]
    version = module.params["version"]
    package = _get_package(module, blade, name, version)
    status = getattr(package, "status", None)
    if package is not None:
        if status == "downloaded":
            module.exit_json(changed=False, software=_software_to_dict(package))
        if status in ("new", "downloading"):
            if module.params["wait"] and not module.check_mode:
                package = _wait(
                    module,
                    lambda: _get_package(module, blade, name, version),
                    DOWNLOAD_FINISHED,
                    "download of {0} {1}".format(name, version),
                    changed=False,
                )
                _fail_on_download_failure(module, package, changed=False)
            module.exit_json(changed=False, software=_software_to_dict(package))
        if status != "download_failed":
            module.exit_json(changed=False, software=_software_to_dict(package))
        if not module.params["force"]:
            module.fail_json(
                msg=(
                    "The download of {0} {1} failed previously ({2}). Set force "
                    "to delete the failed package and download it again, or "
                    "use state=absent to delete it."
                ).format(name, version, getattr(package, "details", None)),
                software=_software_to_dict(package),
            )
    if module.check_mode:
        module.exit_json(changed=True, software=_software_to_dict(package))
    if package is not None:
        _delete_package(module, blade, name, version)
    res = blade.post_software(software=SoftwarePost(name=name, version=version))
    if res.status_code != 200:
        # a failed package deleted just before counts as a change
        module.fail_json(
            changed=package is not None,
            msg="Failed to start the download of {0} {1}. Error: {2}".format(
                name, version, get_error_message(res)
            ),
        )
    items = list(res.items or [])
    package = items[0] if items else _get_package(module, blade, name, version)
    if module.params["wait"]:
        package = _wait(
            module,
            lambda: _get_package(module, blade, name, version),
            DOWNLOAD_FINISHED,
            "download of {0} {1}".format(name, version),
            changed=True,
        )
        _fail_on_download_failure(module, package, changed=True)
    module.exit_json(changed=True, software=_software_to_dict(package))


def stage_bundle(module, blade):
    source = module.params["bundle_source"]
    bundle = _get_bundle(module, blade, source)
    status = getattr(bundle, "status", None)
    if bundle is not None and status == "ready":
        module.exit_json(changed=False, software_bundle=_bundle_to_dict(bundle))
    if bundle is not None and status in ("downloading", "verifying"):
        if module.params["wait"] and not module.check_mode:
            bundle_id = bundle.id
            bundle = _wait(
                module,
                lambda: _fetch_bundle(module, blade, bundle_id),
                BUNDLE_FINISHED,
                "software bundle download from {0}".format(source),
                changed=False,
            )
            _fail_on_bundle_failure(module, bundle, changed=False)
        module.exit_json(changed=False, software_bundle=_bundle_to_dict(bundle))
    # no bundle from this source yet, or its download failed
    if module.check_mode:
        module.exit_json(changed=True, software_bundle=_bundle_to_dict(bundle))
    res = blade.post_software_bundle(source=SoftwareBundlePost(source=source))
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to start the software bundle download from {0}. Error: {1}".format(
                source, get_error_message(res)
            )
        )
    items = list(res.items or [])
    bundle = items[0] if items else _get_bundle(module, blade, source)
    if module.params["wait"] and bundle is not None:
        bundle_id = bundle.id
        bundle = _wait(
            module,
            lambda: _fetch_bundle(module, blade, bundle_id),
            BUNDLE_FINISHED,
            "software bundle download from {0}".format(source),
            changed=True,
        )
        _fail_on_bundle_failure(module, bundle, changed=True)
    module.exit_json(changed=True, software_bundle=_bundle_to_dict(bundle))


def delete_package(module, blade):
    name = module.params["name"]
    version = module.params["version"]
    package = _get_package(module, blade, name, version)
    if package is None:
        module.exit_json(changed=False)
    if not module.check_mode:
        _delete_package(module, blade, name, version)
    module.exit_json(changed=True)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(
                type="str",
                default="check",
                choices=["check", "downloaded", "staged", "absent"],
            ),
            name=dict(type="str", default="Purity//FB"),
            version=dict(type="str"),
            local=dict(type="bool", default=False),
            bundle_source=dict(type="str"),
            force=dict(type="bool", default=False),
            wait=dict(type="bool"),
            timeout=dict(type="int", default=600),
        )
    )
    required_if = [
        ["state", "check", ["version"]],
        ["state", "downloaded", ["version"]],
        ["state", "absent", ["version"]],
        ["state", "staged", ["bundle_source"]],
    ]

    module = AnsibleModule(
        argument_spec, required_if=required_if, supports_check_mode=True
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    state = module.params["state"]
    if module.params["wait"] is None:
        # checks finish in minutes; package and bundle downloads can take hours
        module.params["wait"] = state == "check"
    if module.params["timeout"] < 1:
        module.fail_json(msg="timeout must be at least 1 second")

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if state == "check":
        required, purity = CHECK_API_VERSION, "4.5.2"
    elif state == "staged":
        required, purity = BUNDLE_API_VERSION, "4.6.8"
    else:
        required, purity = SOFTWARE_API_VERSION, "4.8.8"
    if LooseVersion(required) > LooseVersion(api_version):
        module.fail_json(
            msg=(
                "FlashBlade REST version not supported. Minimum version required "
                "for state={0}: {1} (Purity//FB {2}+)"
            ).format(state, required, purity)
        )
    if (
        state == "check"
        and module.params["local"]
        and LooseVersion(SOFTWARE_API_VERSION) > LooseVersion(api_version)
    ):
        module.fail_json(
            msg=(
                "FlashBlade REST version not supported. The local option requires "
                "version {0} (Purity//FB 4.8.8+)"
            ).format(SOFTWARE_API_VERSION)
        )

    if state == "check":
        run_check(module, blade)
    elif state == "downloaded":
        download_package(module, blade)
    elif state == "staged":
        stage_bundle(module, blade)
    else:
        delete_package(module, blade)


if __name__ == "__main__":
    main()
