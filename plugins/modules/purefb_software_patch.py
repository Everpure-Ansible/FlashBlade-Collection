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
module: purefb_software_patch
version_added: '1.30.0'
short_description: Install Purity//FB software patches
description:
- Download and install a Purity//FB software patch that the array lists,
  and wait for the installation to finish.
- A patch cannot be removed once installed, so the only state is
  C(present). A patch that is already installed, or that the array reports
  as not applicable, is left alone.
- The array lists the patches that Everpure Support or the Everpure cloud
  has published for it. The REST API has no catalogue of patches, so a
  name the array does not list cannot be installed. On a dark site, or to
  patch through your own tooling, stage the software bundle on the array
  with purefb_software (I(state=staged)), update the support diagnostics
  settings from that bundle, and then install the patch with
  I(local=true).
- Requires FlashBlade REST API version 2.24 or later (Purity//FB 4.6.8+).
  I(local) requires 2.29 (Purity//FB 4.8.6+).
- Read the patches the array knows about back with the C(software) subset
  of M(everpure.flashblade.purefb_info).
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - Name of the software patch, as listed by the array.
    type: str
    required: true
  state:
    description:
    - C(present) installs the patch when it is available or downloaded,
      waits for an installation that is already running, and leaves an
      installed or not applicable patch alone.
    type: str
    default: present
    choices: [ present ]
  allow_ha_reduction:
    description:
    - Allow the installation of a patch that reports
      C(ha_reduction_required). The array reduces its high availability
      while such a patch installs.
    - The module refuses to install a patch that requires an HA reduction
      unless this is set.
    type: bool
    default: false
  local:
    description:
    - Install the patch from the software bundle previously downloaded
      onto the array instead of from the Everpure cloud.
    - Requires REST API version 2.29.
    type: bool
    default: false
  retry:
    description:
    - Start the installation again when the previous attempt ended in
      C(failed) or C(download_failed). Without it the module fails and
      reports the reason the array gives.
    type: bool
    default: false
  wait:
    description:
    - Wait for the download and installation to finish and report the
      result. The module fails when the patch ends in C(failed) or
      C(download_failed).
    - When C(false) the module returns as soon as the installation has
      been requested. Read the progress back with the C(software) subset
      of M(everpure.flashblade.purefb_info).
    type: bool
    default: true
  timeout:
    description:
    - Seconds to wait for the installation to finish when I(wait) is set.
    - The module fails when the time runs out. The installation keeps
      running on the array.
    type: int
    default: 1800
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Install a software patch and wait for it to finish
  everpure.flashblade.purefb_software_patch:
    name: purity_fb_patch_1042
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
  register: result

- name: Show the patch status
  debug:
    var: result.software_patch.status

- name: Install a patch that reduces high availability while it installs
  everpure.flashblade.purefb_software_patch:
    name: purity_fb_patch_1042
    allow_ha_reduction: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Install a patch from the bundle staged on the array without waiting
  everpure.flashblade.purefb_software_patch:
    name: purity_fb_patch_1042
    local: true
    wait: false
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Try a failed patch installation again, waiting up to an hour
  everpure.flashblade.purefb_software_patch:
    name: purity_fb_patch_1042
    retry: true
    timeout: 3600
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = r"""
software_patch:
  description: The software patch after the module ran.
  returned: success
  type: dict
  contains:
    id:
      description: ID of the patch.
      type: str
    name:
      description: Name of the patch.
      type: str
      sample: purity_fb_patch_1042
    status:
      description:
      - Status of the patch, one of C(available), C(downloaded),
        C(downloading), C(download_failed), C(installing), C(installed),
        C(failed) or C(not_applicable).
      type: str
    progress:
      description: Installation progress as a decimal fraction.
      type: float
    description:
      description: Description of the patch.
      type: str
    details:
      description: Detailed reason for the status.
      type: str
    alert_code:
      description: Alert code that identifies the patch.
      type: int
    ha_reduction_required:
      description: Whether installing the patch reduces high availability.
      type: bool
"""


HAS_PYPURECLIENT = True
try:
    from pypureclient import flashblade  # noqa: F401 pylint: disable=unused-import
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

MIN_REQUIRED_API_VERSION = "2.24"
LOCAL_API_VERSION = "2.29"
POLL_INTERVAL = 10
# polls a retried patch may still show its previous failure before it counts
RETRY_GRACE_POLLS = 3

INSTALLABLE = ("available", "downloaded")
IN_PROGRESS = ("downloading", "installing")
FAILED = ("failed", "download_failed")
FINISHED = ("installed", "not_applicable") + FAILED


def _patch_to_dict(patch):
    if patch is None:
        return {}
    return {
        "id": getattr(patch, "id", None),
        "name": getattr(patch, "name", None),
        "status": getattr(patch, "status", None),
        "progress": getattr(patch, "progress", None),
        "description": getattr(patch, "description", None),
        "details": getattr(patch, "details", None),
        "alert_code": getattr(patch, "alert_code", None),
        "ha_reduction_required": getattr(patch, "ha_reduction_required", None),
    }


def _failure_text(status):
    return "failed to download" if status == "download_failed" else "failed to install"


def _get_patch(module, blade):
    """The patch named in the task, or None when the array does not list it.

    Every patch is listed and matched here because the API answers a
    ``names=`` query for a name it does not know with an error rather than
    an empty list.
    """
    res = blade.get_software_patches()
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to get software patches. Error: {0}".format(
                get_error_message(res)
            )
        )
    for patch in list(res.items):
        if getattr(patch, "name", None) == module.params["name"]:
            return patch
    return None


def _wait(module, blade, changed, first=None, stale_status=None):
    """Poll the patch until it reaches a final status; fail on timeout.

    ``first`` is the record the install request returned. It is the first
    observation, so the poll never acts on a listing taken before the
    request. ``stale_status`` is the failed status a retried patch had
    before the request; that status only counts as final once the array
    has reported another one since the request, or after RETRY_GRACE_POLLS
    observations, so a retry is not reported as failed from its own
    previous record.
    """
    seen = {"first": first, "other": False, "polls": 0}

    def fetch():
        patch = seen.pop("first", None)
        if patch is None:
            patch = _get_patch(module, blade)
        seen["polls"] += 1
        return patch

    def done(patch):
        if patch is None:
            return False
        status = getattr(patch, "status", None)
        if status != stale_status:
            seen["other"] = True
        if status not in FINISHED:
            return False
        return seen["other"] or seen["polls"] >= RETRY_GRACE_POLLS

    patch, timed_out = poll_until(fetch, done, module.params["timeout"], POLL_INTERVAL)
    if timed_out:
        module.fail_json(
            changed=changed,
            msg=(
                "Timed out after {0} seconds waiting for software patch {1} "
                "(status: {2}). The installation continues on the array."
            ).format(
                module.params["timeout"],
                module.params["name"],
                getattr(patch, "status", None),
            ),
            software_patch=_patch_to_dict(patch),
        )
    return patch


def _finish(module, patch, changed):
    """Report the final status of a patch the module waited for."""
    name = module.params["name"]
    status = getattr(patch, "status", None)
    details = getattr(patch, "details", None) or ""
    if status in FAILED:
        module.fail_json(
            changed=changed,
            msg="Software patch {0} {1}. {2}".format(
                name, _failure_text(status), details
            ).strip(),
            software_patch=_patch_to_dict(patch),
        )
    if status == "not_applicable":
        module.warn(
            "Software patch {0} is not applicable to this array. {1}".format(
                name, details
            ).strip()
        )
    module.exit_json(changed=changed, software_patch=_patch_to_dict(patch))


def install_patch(module, blade):
    name = module.params["name"]
    patch = _get_patch(module, blade)
    if patch is None:
        module.fail_json(
            msg=(
                "Software patch {0} is not known to the array. The array only "
                "lists the patches published for it; on a dark site, download "
                "the software bundle to the array and update the support "
                "diagnostics settings from it before installing the patch."
            ).format(name)
        )
    status = getattr(patch, "status", None)
    if status in ("installed", "not_applicable"):
        module.exit_json(changed=False, software_patch=_patch_to_dict(patch))
    if status in IN_PROGRESS:
        # the patch is already on its way; never request it a second time
        if module.params["wait"] and not module.check_mode:
            patch = _wait(module, blade, changed=False)
            _finish(module, patch, changed=False)
        module.exit_json(changed=False, software_patch=_patch_to_dict(patch))
    if status in FAILED:
        if not module.params["retry"]:
            module.fail_json(
                msg=(
                    "Software patch {0} {1} previously ({2}). Set retry to try "
                    "the installation again."
                ).format(name, _failure_text(status), getattr(patch, "details", None)),
                software_patch=_patch_to_dict(patch),
            )
    elif status not in INSTALLABLE:
        module.fail_json(
            msg="Software patch {0} reports an unexpected status: {1}".format(
                name, status
            ),
            software_patch=_patch_to_dict(patch),
        )
    # the patch is available or downloaded, or a failed attempt is retried
    if (
        getattr(patch, "ha_reduction_required", False)
        and not module.params["allow_ha_reduction"]
    ):
        module.fail_json(
            msg=(
                "Software patch {0} requires a reduction in high availability "
                "while it installs. Set allow_ha_reduction to install it."
            ).format(name),
            software_patch=_patch_to_dict(patch),
        )
    if module.check_mode:
        module.exit_json(changed=True, software_patch=_patch_to_dict(patch))
    kwargs = {"name": name}
    if module.params["allow_ha_reduction"]:
        kwargs["allow_ha_reduction"] = True
    if module.params["local"]:
        kwargs["local"] = True
    res = blade.post_software_patches(**kwargs)
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to install software patch {0}. Error: {1}".format(
                name, get_error_message(res)
            )
        )
    items = list(res.items or [])
    patch = items[0] if items else None
    if module.params["wait"]:
        patch = _wait(
            module,
            blade,
            changed=True,
            first=patch,
            stale_status=status if status in FAILED else None,
        )
        _finish(module, patch, changed=True)
    if patch is None:
        patch = _get_patch(module, blade)
    module.exit_json(changed=True, software_patch=_patch_to_dict(patch))


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str", required=True),
            state=dict(type="str", default="present", choices=["present"]),
            allow_ha_reduction=dict(type="bool", default=False),
            local=dict(type="bool", default=False),
            retry=dict(type="bool", default=False),
            wait=dict(type="bool", default=True),
            timeout=dict(type="int", default=1800),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")
    if module.params["timeout"] < 1:
        module.fail_json(msg="timeout must be at least 1 second")

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg=(
                "FlashBlade REST version not supported. Minimum version required: "
                "{0} (Purity//FB 4.6.8+)"
            ).format(MIN_REQUIRED_API_VERSION)
        )
    if module.params["local"] and LooseVersion(LOCAL_API_VERSION) > LooseVersion(
        api_version
    ):
        module.fail_json(
            msg=(
                "FlashBlade REST version not supported. The local option requires "
                "version {0} (Purity//FB 4.8.6+)"
            ).format(LOCAL_API_VERSION)
        )

    install_patch(module, blade)


if __name__ == "__main__":
    main()
