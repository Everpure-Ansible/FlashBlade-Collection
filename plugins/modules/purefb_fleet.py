#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2025, Simon Dodsley (simon@everpuredata.com)
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
module: purefb_fleet
version_added: '1.20.0'
short_description: Manage Fusion Fleet
description:
- Create/Modify/Delete Fusion fleet and members
- Members can be added one at a time with I(member_url) and I(member_api),
  or in one batch by management address and administrator credentials with
  I(members) (REST 2.27, Purity//FB 4.8.3 or later), and removed by name
  with I(member_name).
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - Name of the fleet.
    - If not provided local array will be used.
    type: str
  state:
    description:
    - Define whether to add or remove member from a fleet.
    - Create a new fleet if one does not exist.
      This will use the current array as the first member.
    - Fleet deletion can only occiur when the current array
      is the only fleet member.
    default: present
    choices: [ absent, present, create ]
    type: str
  member_url:
    description:
    - Management IP address/FQDN of array to add to fleet.
    - A fleet key is created only when that array is not yet a member of
      the fleet, and never in check mode. A new fleet key invalidates the
      fleet keys created before it.
    type: str
  member_api:
    description:
    - API token for target array
    type: str
  rename:
    description:
    - new name for fleet
    type: str
  members:
    description:
    - Arrays to add to the fleet in one batch request, by management address
      and administrator credentials, so no API token is needed on the target.
    - Requires FlashBlade REST API 2.27 (Purity//FB 4.8.3) or later on this
      array. Targets must run FlashArray REST 2.47 or FlashBlade REST 2.25
      or later. The array limits the number of targets in one request.
    - The join is asynchronous; see I(wait).
    - Only valid with I(state=present). Mutually exclusive with
      I(member_url), I(member_name) and I(rename).
    type: list
    elements: dict
    version_added: '1.30.0'
    suboptions:
      management_address:
        description:
        - Management IP address or FQDN of the array to add.
        type: str
        required: true
      name:
        description:
        - Name of the array as it appears in the fleet member list.
        - When set, a target that is already C(joined) or C(joining) is
          skipped, which makes a rerun idempotent. Without it the module
          cannot tell whether the array is already a member and sends the
          target to the array again.
        type: str
      username:
        description:
        - Administrator username on the target array.
        - Defaults to I(member_username).
        type: str
      password:
        description:
        - Password for I(username).
        - Defaults to I(member_password).
        type: str
      ca_certificate:
        description:
        - Name of a certificate on this array (see
          M(everpure.flashblade.purefb_certs)) used to verify the certificate
          presented by the target.
        - Mutually exclusive with I(ca_certificate_group).
          Ignored when I(validate_certificates=false).
        type: str
      ca_certificate_group:
        description:
        - Name of a certificate group on this array (see
          M(everpure.flashblade.purefb_certgrp)) used to verify the
          certificate presented by the target.
        - Mutually exclusive with I(ca_certificate).
          Ignored when I(validate_certificates=false).
        type: str
  member_username:
    description:
    - Default administrator username for every entry in I(members) that
      does not set its own.
    type: str
    version_added: '1.30.0'
  member_password:
    description:
    - Default password for every entry in I(members) that does not set
      its own.
    type: str
    version_added: '1.30.0'
  validate_certificates:
    description:
    - Validate the certificate presented by each target in I(members)
      against its I(ca_certificate) or I(ca_certificate_group).
    - C(false) skips certificate validation and ignores any certificate
      references; use only for self-signed lab certificates.
    type: bool
    default: true
    version_added: '1.30.0'
  wait:
    description:
    - Wait until every target in I(members) reports C(joined), polling the
      fleet member list every five seconds for up to I(timeout) seconds.
    - When C(false) the module returns as soon as the array has accepted
      the batch request, with each target still C(joining).
    type: bool
    default: true
    version_added: '1.30.0'
  timeout:
    description:
    - Seconds to wait for the targets to join when I(wait) is true.
    type: int
    default: 300
    version_added: '1.30.0'
  member_name:
    description:
    - Names of fleet members to remove with I(state=absent), as shown in
      the fleet member list.
    - Removal runs from this array alone, so no credentials for the target
      are needed. A member that is not C(joined) is removed with a
      one-sided disconnect.
    - Only valid with I(state=absent). Mutually exclusive with I(member_url),
      I(members) and I(rename).
    type: list
    elements: str
    version_added: '1.30.0'
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Create a new fleet
  everpure.flashblade.purefb_fleet:
    name: foo
    state: create
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Add a member to fleet foo
  everpure.flashblade.purefb_fleet:
    name: foo
    member_url: array2
    member_api: c6033033-fe69-2515-a9e8-966bb7fe4b40
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete a member from fleet foo
  everpure.flashblade.purefb_fleet:
    name: foo
    member_url: array2
    member_api: c6033033-fe69-2515-a9e8-966bb7fe4b40
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete fleet foo
  everpure.flashblade.purefb_fleet:
    name: foo
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Add two arrays to fleet foo in one batch by address
  everpure.flashblade.purefb_fleet:
    name: foo
    member_username: pureuser
    member_password: secret
    members:
      - management_address: array2.example.com
        name: array2
      - management_address: 10.10.10.3
        name: array3
        ca_certificate_group: fleet-cas
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Remove members from fleet foo by name
  everpure.flashblade.purefb_fleet:
    name: foo
    member_name:
      - array2
      - array3
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = r"""
members:
  description:
  - Result for each target of a batch join (I(members) with I(state=present)).
  returned: when I(members) is set
  type: list
  elements: dict
  contains:
    management_address:
      description: Management address given for the target.
      type: str
    member:
      description:
      - Name of the fleet member, when the array could be identified.
      - A target the batch response did not name is matched to the single
        new member in the fleet member list after I(wait); otherwise null.
      type: str
    status:
      description:
      - Join status, C(joining), C(joined) or C(failed). Null in check mode.
      - After I(wait) the status is read from the fleet member list; a target
        that could not be matched to a member keeps the status of the batch
        response.
      type: str
    status_details:
      description: Additional details about the join attempt.
      type: str
    certificate_details:
      description:
      - Issuer, subject and validity (not_before and not_after, in
        milliseconds since the epoch) of the certificate presented by the
        target, when available.
      type: dict
  sample:
  - management_address: array2.example.com
    member: array2
    status: joined
    status_details: null
    certificate_details:
      issuer: CN=array2
      subject: CN=array2
      not_before: 1700000000000
      not_after: 2000000000000
"""

HAS_URLLIB3 = True
try:
    import urllib3
except ImportError:
    HAS_URLLIB3 = False

HAS_DISTRO = True
try:
    import distro
except ImportError:
    HAS_DISTRO = False

HAS_PYPURECLIENT = True
try:
    from pypureclient import flashblade
    from pypureclient import flasharray
    from pypureclient.flashblade import (
        AuthenticationCredentials,
        FleetMemberBatchPost,
        FleetMemberPost,
        FleetMemberPostMembersMember,
        FleetMemberPostMembers,
        FleetPatch,
        ReferenceWritable,
    )
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
import platform
import time

VERSION = 1.5
USER_AGENT_BASE = "Ansible"
MIN_REQUIRED_API_VERSION = "2.17"
MIN_FA_VERSION = "2.42"
# POST /fleets/members/batch first appeared in REST 2.27 (Purity//FB 4.8.3)
BATCH_API_VERSION = "2.27"
BATCH_POLL_INTERVAL = 5
JOINED_STATES = ["joined", "connected", "partially connected"]


def create_fleet(module, blade):
    """Create new fleet - only ever called once per fleet"""
    changed = True
    if not module.check_mode:
        res = blade.post_fleets(names=[module.params["name"]])
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to create fleet {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def delete_fleet(module, blade):
    """Delete the fleet.

    Only works when the current array is the only remaining
    member of the fleet.
    """
    changed = True
    if not module.check_mode:
        res = blade.delete_fleets(names=[module.params["name"]])
        if res.status_code != 200:
            module.fail_json(
                msg="Fleet {0} deletion failed. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def add_fleet_members(module, blade):
    """Add new member to the fleet"""
    changed = False
    if not module.params["member_url"] or not module.params["member_api"]:
        module.fail_json(msg="missing required arguments: member_api, member_url")
    if HAS_URLLIB3 and module.params["disable_warnings"]:
        urllib3.disable_warnings()
    if HAS_DISTRO:
        user_agent = "%(base)s %(class)s/%(version)s (%(platform)s)" % {
            "base": USER_AGENT_BASE,
            "class": __name__,
            "version": VERSION,
            "platform": distro.name(pretty=True),
        }
    else:
        user_agent = "%(base)s %(class)s/%(version)s (%(platform)s)" % {
            "base": USER_AGENT_BASE,
            "class": __name__,
            "version": VERSION,
            "platform": platform.platform(),
        }
    # FlashBlade API tokens start with "T-" so use that to differentiate
    # fleet member platform type
    if "T-" in module.params["member_api"]:
        remote_system = flashblade.Client(
            target=module.params["member_url"],
            api_token=module.params["member_api"],
            user_agent=user_agent,
        )
        remote_version = get_rest_api_version(remote_system)
        if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(remote_version):
            module.fail_json(
                msg="Remote FlashBlade must be a minimum of REST API {0}"
                " to join a fleet".format(MIN_REQUIRED_API_VERSION)
            )
    else:
        remote_system = flasharray.Client(
            target=module.params["member_url"],
            api_token=module.params["member_api"],
            user_agent=user_agent,
        )
        remote_version = remote_system.get_rest_version()
        if LooseVersion(MIN_FA_VERSION) > LooseVersion(remote_version):
            module.fail_json(
                msg="FlashArray must be a minimum of Purity//FA 6.8.5"
                " to join a fleet containing FlashBlades"
            )
    local_name = _remote_array_name(module, remote_system)
    if local_name not in _get_fleet_members(module, blade):
        changed = True
        if not module.check_mode:
            # a new fleet key invalidates the keys created before it, so one
            # is requested only when the array is about to join
            res = blade.post_fleets_fleet_key()
            if res.status_code != 200:
                module.fail_json(
                    msg="Fleet key generation failed. Error: {0}".format(
                        get_error_message(res)
                    )
                )
            fleet_key = list(res.items)[0].fleet_key
            res = remote_system.post_fleets_members(
                fleet_names=[module.params["name"]],
                members=FleetMemberPost(
                    members=[
                        FleetMemberPostMembers(
                            key=fleet_key,
                            member=FleetMemberPostMembersMember(
                                name=local_name, resource_type="remote-arrays"
                            ),
                        )
                    ]
                ),
            )
            if res.status_code != 200:
                module.fail_json(
                    "Array {0} failed to join fleet {1}. Error: {2}".format(
                        local_name, module.params["name"], get_error_message(res)
                    )
                )
    module.exit_json(changed=changed)


def delete_fleet_members(module, blade):
    """Delete member from a fleet"""
    changed = False
    if HAS_URLLIB3 and module.params["disable_warnings"]:
        urllib3.disable_warnings()
    if HAS_DISTRO:
        user_agent = "%(base)s %(class)s/%(version)s (%(platform)s)" % {
            "base": USER_AGENT_BASE,
            "class": __name__,
            "version": VERSION,
            "platform": distro.name(pretty=True),
        }
    else:
        user_agent = "%(base)s %(class)s/%(version)s (%(platform)s)" % {
            "base": USER_AGENT_BASE,
            "class": __name__,
            "version": VERSION,
            "platform": platform.platform(),
        }
    # FlashBlade API tokens start with "T-" so use that to differentiate
    # fleet member platform type
    if "T-" in module.params["member_api"]:
        remote_system = flashblade.Client(
            target=module.params["member_url"],
            api_token=module.params["member_api"],
            user_agent=user_agent,
        )
    else:
        remote_system = flasharray.Client(
            target=module.params["member_url"],
            api_token=module.params["member_api"],
            user_agent=user_agent,
        )
    local_name = _remote_array_name(module, remote_system)
    for member in _get_fleet_members(module, blade).values():
        if member.member.name == local_name:
            changed = True
            if not module.check_mode:
                if member.status not in [
                    "joined",
                    "connected",
                    "partially connected",
                ]:
                    res = blade.delete_fleets_members(
                        member_names=[local_name], unreachable=True
                    )
                else:
                    res = blade.delete_fleets_members(member_names=[local_name])
                if res.status_code != 200:
                    module.fail_json(
                        "Array {0} failed to be removed from fleet. Error: {1}".format(
                            module.params["member_url"], get_error_message(res)
                        )
                    )
    module.exit_json(changed=changed)


def _current_fleet_name(module, blade):
    """Return the name of the fleet this array belongs to.

    An array belongs to at most one fleet, so I(name) may be omitted; when
    it is given it must be that fleet.
    """
    res = blade.get_fleets()
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read fleets. Error: {0}".format(get_error_message(res))
        )
    fleets = [fleet.name for fleet in list(res.items) if fleet.is_local is not False]
    if not fleets:
        module.fail_json(
            msg="This array is not a member of a fleet. "
            "Create one with state=create first."
        )
    if module.params["name"] and module.params["name"] not in fleets:
        module.fail_json(
            msg="Fleet {0} not found. This array is a member of fleet {1}.".format(
                module.params["name"], fleets[0]
            )
        )
    return module.params["name"] or fleets[0]


def _get_fleet_members(module, blade):
    """Return the current fleet members keyed by member name"""
    res = blade.get_fleets_members()
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to list fleet members. Error: {0}".format(
                get_error_message(res)
            )
        )
    return {member.member.name: member for member in list(res.items)}


def _remote_array_name(module, remote_system):
    """Return the name of the array at I(member_url)"""
    res = remote_system.get_arrays()
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read the array name from {0}. Error: {1}".format(
                module.params["member_url"], get_error_message(res)
            )
        )
    return list(res.items)[0].name


def _batch_entry(module, member):
    """Build the FleetMemberBatchPost body for one I(members) entry"""
    username = member.get("username") or module.params["member_username"]
    password = member.get("password") or module.params["member_password"]
    if not username or not password:
        module.fail_json(
            msg="Member {0} needs a username and password, either in the "
            "members entry or via member_username and member_password".format(
                member["management_address"]
            )
        )
    kwargs = dict(
        management_address=member["management_address"],
        authentication_credentials=AuthenticationCredentials(
            username=username, password=password
        ),
    )
    if member.get("ca_certificate"):
        kwargs["ca_certificate"] = ReferenceWritable(
            name=member["ca_certificate"], resource_type="certificates"
        )
    elif member.get("ca_certificate_group"):
        kwargs["ca_certificate_group"] = ReferenceWritable(
            name=member["ca_certificate_group"], resource_type="certificate-groups"
        )
    return FleetMemberBatchPost(**kwargs)


def _batch_result_dict(result):
    """Flatten one FleetMemberBatchResult for the module return value"""
    member = getattr(result, "member", None)
    certificate = getattr(result, "certificate_details", None)
    info = {
        "management_address": getattr(result, "management_address", None),
        "member": getattr(member, "name", None) if member else None,
        "status": getattr(result, "status", None),
        "status_details": getattr(result, "status_details", None),
        "certificate_details": None,
    }
    if certificate:
        info["certificate_details"] = {
            "issuer": getattr(certificate, "issuer", None),
            "subject": getattr(certificate, "subject", None),
            "not_before": getattr(certificate, "not_before", None),
            "not_after": getattr(certificate, "not_after", None),
        }
    return info


def _pending_text(member):
    """Status of a fleet member that is not yet joined, with its details"""
    text = member.status
    if member.status_details:
        text += ": " + member.status_details
    return text


def _wait_for_join(module, blade, names, known, results):
    """Poll the fleet member list until every target is joined.

    ``names`` are the member names the batch response identified. A target
    the response could not name is tracked through the members that were
    not listed before the request (``known``), so members another operator
    had already added are never waited for; when exactly one such member
    appears the target is reported under that name. Fails with the pending
    statuses on timeout.
    """
    unidentified = [result for result in results if not result["member"]]
    deadline = time.time() + module.params["timeout"]
    while True:
        members = _get_fleet_members(module, blade)
        pending = {}
        for name in names:
            member = members.get(name)
            if member is None:
                pending[name] = "not yet listed"
            elif member.status != "joined":
                pending[name] = _pending_text(member)
        new_names = [
            name for name in members if name not in known and name not in names
        ]
        if unidentified:
            for name in new_names:
                if members[name].status == "joining":
                    pending[name] = _pending_text(members[name])
        if not pending:
            break
        if time.time() >= deadline:
            module.fail_json(
                msg="Timed out after {0}s waiting for fleet members to join: {1}".format(
                    module.params["timeout"],
                    "; ".join(
                        "{0} ({1})".format(name, state)
                        for name, state in sorted(pending.items())
                    ),
                ),
                members=results,
            )
        time.sleep(BATCH_POLL_INTERVAL)
    for result in results:
        if result["member"] in members:
            result["status"] = members[result["member"]].status
    if len(unidentified) == 1 and len(new_names) == 1:
        unidentified[0]["member"] = new_names[0]
        unidentified[0]["status"] = members[new_names[0]].status
    return results


def add_fleet_members_batch(module, blade):
    """Add arrays to the fleet by management address and credentials.

    One POST /fleets/members/batch (REST 2.27) for every target that is not
    already a member. The array answers ``joining`` per target and the module
    polls the member list until each one is ``joined`` when I(wait) is set.
    """
    fleet_name = _current_fleet_name(module, blade)
    existing = _get_fleet_members(module, blade)
    targets = []
    for member in module.params["members"]:
        name = member.get("name")
        if name and name in existing and existing[name].status in ["joined", "joining"]:
            continue
        targets.append(member)
    if not targets:
        module.exit_json(changed=False, members=[])
    results = [
        {
            "management_address": member["management_address"],
            "member": member.get("name"),
            "status": None,
            "status_details": None,
            "certificate_details": None,
        }
        for member in targets
    ]
    # built before the check-mode branch so that a missing username or
    # password fails in check mode as well
    entries = [_batch_entry(module, member) for member in targets]
    if not module.check_mode:
        res = blade.post_fleets_members_batch(
            fleet_names=[fleet_name],
            fleet_member_batch_post=entries,
            validate_target_certificates=module.params["validate_certificates"],
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Batch join to fleet {0} failed. Error: {1}".format(
                    fleet_name, get_error_message(res)
                )
            )
        results = [_batch_result_dict(item) for item in list(res.items)]
        failed = [result for result in results if result["status"] == "failed"]
        if failed:
            module.fail_json(
                msg="{0} of {1} targets failed to join fleet {2}: {3}".format(
                    len(failed),
                    len(results),
                    fleet_name,
                    "; ".join(
                        "{0} ({1})".format(
                            result["management_address"], result["status_details"]
                        )
                        for result in failed
                    ),
                ),
                members=results,
            )
        if module.params["wait"]:
            names = [result["member"] for result in results if result["member"]]
            results = _wait_for_join(module, blade, names, set(existing), results)
    module.exit_json(changed=True, members=results)


def delete_fleet_members_by_name(module, blade):
    """Remove fleet members by name from this array, without remote credentials"""
    changed = False
    members = _get_fleet_members(module, blade)
    for name in module.params["member_name"]:
        member = members.get(name)
        if member is None:
            continue
        if member.member.is_local:
            module.fail_json(
                msg="{0} is this array. Use state=absent without member_name "
                "to delete the fleet.".format(name)
            )
        changed = True
        if not module.check_mode:
            if member.status not in JOINED_STATES:
                res = blade.delete_fleets_members(member_names=[name], unreachable=True)
            else:
                res = blade.delete_fleets_members(member_names=[name])
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to remove {0} from the fleet. Error: {1}".format(
                        name, get_error_message(res)
                    )
                )
    module.exit_json(changed=changed)


def rename_fleet(module, blade):
    """Rename the fleet this array belongs to"""
    changed = False
    fleet = _current_fleet_name(module, blade)
    if module.params["rename"] != fleet:
        changed = True
        if not module.check_mode:
            res = blade.patch_fleets(
                names=[fleet],
                fleet=FleetPatch(name=module.params["rename"]),
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Fleet rename failed. Error: {0}".format(get_error_message(res))
                )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str"),
            state=dict(
                type="str", default="present", choices=["absent", "present", "create"]
            ),
            member_url=dict(type="str"),
            member_api=dict(type="str"),
            rename=dict(type="str"),
            members=dict(
                type="list",
                elements="dict",
                options=dict(
                    management_address=dict(type="str", required=True),
                    name=dict(type="str"),
                    username=dict(type="str"),
                    password=dict(type="str", no_log=True),
                    ca_certificate=dict(type="str"),
                    ca_certificate_group=dict(type="str"),
                ),
                mutually_exclusive=[["ca_certificate", "ca_certificate_group"]],
            ),
            member_username=dict(type="str"),
            member_password=dict(type="str", no_log=True),
            validate_certificates=dict(type="bool", default=True),
            wait=dict(type="bool", default=True),
            timeout=dict(type="int", default=300),
            member_name=dict(type="list", elements="str"),
        )
    )

    required_together = [["member_url", "member_api"]]
    mutually_exclusive = [
        ["members", "member_url"],
        ["members", "member_name"],
        ["members", "rename"],
        ["member_name", "member_url"],
        ["member_name", "rename"],
    ]

    module = AnsibleModule(
        argument_spec,
        required_together=required_together,
        mutually_exclusive=mutually_exclusive,
        supports_check_mode=True,
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")
    # members adds and member_name removes; reject the other state before any
    # connection so neither can fall through to the fleet delete or the
    # legacy member_url path
    if module.params["members"] and module.params["state"] != "present":
        module.fail_json(
            msg="members is only valid with state=present; use member_name "
            "with state=absent to remove members"
        )
    if module.params["member_name"] and module.params["state"] != "absent":
        module.fail_json(
            msg="member_name is only valid with state=absent; use members or "
            "member_url with state=present to add members"
        )

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg="FlashBlade REST version not supported. "
            "Minimum version required: {0}".format(MIN_REQUIRED_API_VERSION)
        )
    if module.params["members"] and LooseVersion(BATCH_API_VERSION) > LooseVersion(
        api_version
    ):
        module.fail_json(
            msg="Batch fleet member join requires FlashBlade REST API {0} "
            "(Purity//FB 4.8.3) or later".format(BATCH_API_VERSION)
        )
    state = module.params["state"]
    fleet_res = blade.get_fleets()
    if fleet_res.status_code == 404:
        module.fail_json(
            msg="Fusion is not enabled on this system. "
            "Please speak to Pure Support to enable this feature"
        )
    if fleet_res.status_code != 200:
        module.fail_json(
            msg="Failed to read fleets. Error: {0}".format(get_error_message(fleet_res))
        )
    fleet = bool(list(fleet_res.items))

    if state == "present" and module.params["members"]:
        add_fleet_members_batch(module, blade)
    elif state == "absent" and module.params["member_name"]:
        delete_fleet_members_by_name(module, blade)
    elif state == "create" and not fleet:
        create_fleet(module, blade)
    elif state == "present" and module.params["rename"]:
        rename_fleet(module, blade)
    elif state == "present" and fleet:
        add_fleet_members(module, blade)
    elif state == "absent" and fleet and module.params["member_url"]:
        delete_fleet_members(module, blade)
    elif state == "absent" and fleet:
        delete_fleet(module, blade)
    else:
        module.exit_json(changed=False)


if __name__ == "__main__":
    main()
