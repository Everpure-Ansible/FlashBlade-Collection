#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2020, Simon Dodsley (simon@everpuredata.com)
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
module: purefb_certgrp
version_added: '1.4.0'
short_description: Manage FlashBlade Certifcate Groups
description:
- Manage certifcate groups for FlashBlades
- A certificate group lives at array level or in a realm. A group in a realm
  is named C(realm::group) and holds only certificates of that realm.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  state:
    description:
    - Create or delete certifcate group
    default: present
    type: str
    choices: [ absent, present ]
  name:
    description:
    - Name of the certificate group
    - A group that lives in a realm is named C(realm::group). The same name
      without the realm is a different group at array level.
    - A realm-scoped administrator must use the realm-qualified name; a bare
      name is not placed in, or resolved to, the administrator's realm.
    type: str
    required: true
  certificates:
    description:
    - List of certificates to add to the group (I(state=present)) or to
      remove from the group (I(state=absent)).
    - Certificates already in the group are left alone, so repeated runs
      report no change.
    - With I(state=absent) and no certificates the whole group is deleted.
    - A group can only hold certificates of its own realm. Certificates in a
      realm are named C(realm::certificate), and a group at array level
      holds only certificates at array level. A certificate from another
      scope is refused before anything is changed.
    type: list
    elements: str
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Create a certifcate group
  everpure.flashblade.purefb_certgrp:
    name: test_grp
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
- name: Create a certificate group and add existing certificates
  everpure.flashblade.purefb_certgrp:
    name: test_grp
    certificates:
      - cert1
      - cert2
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
- name: Create a certificate group in realm realm1 with a certificate of that realm
  everpure.flashblade.purefb_certgrp:
    name: realm1::ca-group
    certificates:
      - realm1::ca1
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
- name: Delete a certifcate from a group
  everpure.flashblade.purefb_certgrp:
    name: test_grp
    certificates:
      - cert2
    state: absent
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
- name: Delete a certifcate group
  everpure.flashblade.purefb_certgrp:
    name: test_grp
    state: absent
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
"""

RETURN = r"""
"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.everpure.flashblade.plugins.module_utils.purefb import (
    get_system,
    purefb_argument_spec,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.common import (
    get_error_message,
    get_rest_api_version,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.version import (
    LooseVersion,
)

# Realms arrived with REST 2.19; an older array has no realm to read.
REALM_API_VERSION = "2.19"


def _realm_of(name):
    """Return the realm of a realm::name name, empty for an array-level name."""
    return name.rpartition("::")[0]


def _names(value):
    """Return the names in value the way the array reads them.

    The array takes a comma for a separator between names and ignores white
    space around a name, so "a, b" names a and b, whether it arrives as two
    entries of a list or as one. An empty name names nothing and is left
    out. Certificate names are compared, and sent, in this form.
    """
    if not isinstance(value, list):
        value = [value]
    names = []
    for entry in value:
        for name in str(entry or "").split(","):
            if name.strip():
                names.append(name.strip())
    return names


def _check_certificate_realms(module):
    """Fail when certificates names a certificate the group cannot hold.

    A group in a realm holds only certificates of that realm and a group at
    array level only certificates at array level. The array refuses any
    other certificate when it is added, which check mode cannot foresee, and
    such a name never matches a member when it is removed, so the member it
    was meant for would stay in the group. Both are settled here, before
    anything is read or written. The array matches names without regard to
    case, so the realms are compared that way.
    """
    certificates = _names(module.params["certificates"])
    for group in _names(module.params["name"]):
        realm = _realm_of(group)
        for certificate in certificates:
            if _realm_of(certificate).lower() == realm.lower():
                continue
            if realm:
                module.fail_json(
                    msg=(
                        "Certificate {0} is not in realm {1}. Certificate group "
                        "{2} can only hold certificates of its own realm, named "
                        "{1}::<certificate>."
                    ).format(certificate, realm, group)
                )
            module.fail_json(
                msg=(
                    "Certificate {0} is in a realm. Certificate group {1} is not "
                    "in a realm and can only hold certificates that are not in "
                    "one either."
                ).format(certificate, group)
            )


def _check_realm(module, blade):
    """Fail a check mode run that would create a group in an unusable realm.

    The array refuses to create a group in a realm that does not exist, has
    been destroyed or is not open to the caller. A real run gets that answer
    from the create itself; check mode sends nothing, so it reads the realm
    instead of reporting a change the real run cannot make. A realm the
    caller has no access to is read as an empty list and its create is
    refused with "Realm does not exist.". Only a definite answer fails the
    task.
    """
    name = module.params["name"]
    realms = []
    for group in _names(name):
        realm = _realm_of(group)
        if realm and realm.lower() not in [known.lower() for known in realms]:
            realms.append(realm)
    if not realms or LooseVersion(REALM_API_VERSION) > LooseVersion(
        get_rest_api_version(blade)
    ):
        return
    for realm in realms:
        res = blade.get_realms(names=[realm])
        if res.status_code == 200:
            items = list(res.items)
            if not items:
                error = "Realm does not exist."
            elif getattr(items[0], "destroyed", False) is True:
                error = "Realm has been destroyed."
            else:
                continue
        else:
            error = get_error_message(res)
            if "does not exist" not in str(error).lower():
                continue
        module.fail_json(
            msg="Failed to create certificate group {0}. Error: {1}".format(name, error)
        )


def _group_exists(module, blade):
    """Return True when the certificate group exists.

    A missing group is itself a 400 here ("Certificate group does not
    exist."), so only that answer reads as absent. Any other failure fails
    the task rather than passing for "absent", which would let state=absent
    report no change, or state=present attempt a create, on an error.
    """
    res = blade.get_certificate_groups(names=[module.params["name"]])
    if res.status_code == 200:
        return True
    error = get_error_message(res)
    if "does not exist" not in str(error).lower():
        module.fail_json(
            msg="Failed to read certificate group {0}. Error: {1}".format(
                module.params["name"], error
            )
        )
    return False


def delete_certgrp(module, blade):
    """Delete certificate group"""
    changed = True
    if not module.check_mode:
        res = blade.delete_certificate_groups(names=[module.params["name"]])
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete certificate group {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def create_certgrp(module, blade):
    """Create certificate group"""
    changed = True
    if module.check_mode:
        _check_realm(module, blade)
    else:
        res = blade.post_certificate_groups(names=[module.params["name"]])
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to create certificate group {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
        certificates = _names(module.params["certificates"])
        if certificates:
            res = blade.post_certificate_groups_certificates(
                certificate_names=certificates,
                certificate_group_names=[module.params["name"]],
            )
            if res.status_code != 200:
                blade.delete_certificate_groups(names=[module.params["name"]])
                module.fail_json(
                    msg="Failed to add certificates {0}. Error: {1}".format(
                        certificates, get_error_message(res)
                    )
                )
    module.exit_json(changed=changed)


def get_group_certificates(module, blade):
    """Return the names of the certificates currently in the group"""
    res = blade.get_certificate_groups_certificates(
        certificate_group_names=[module.params["name"]]
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to get certificate list for group {0}. Error: {1}".format(
                module.params["name"], get_error_message(res)
            )
        )
    return [item.member.name for item in list(res.items)]


def update_certgrp(module, blade):
    """Add certificates to, or remove certificates from, an existing group"""
    changed = False
    current = get_group_certificates(module, blade)
    # The array matches names without regard to case and returns the stored
    # spelling, so members are compared lower-cased and removed by the name
    # the array reports.
    wanted = _names(module.params["certificates"])
    members = [cert.lower() for cert in current]
    if module.params["state"] == "present":
        to_add = [cert for cert in wanted if cert.lower() not in members]
        if to_add:
            changed = True
            if not module.check_mode:
                res = blade.post_certificate_groups_certificates(
                    certificate_names=to_add,
                    certificate_group_names=[module.params["name"]],
                )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Failed to add certificates {0} to group {1}. Error: {2}".format(
                            to_add, module.params["name"], get_error_message(res)
                        )
                    )
    else:
        unwanted = [cert.lower() for cert in wanted]
        to_remove = [cert for cert in current if cert.lower() in unwanted]
        if to_remove:
            changed = True
            if not module.check_mode:
                res = blade.delete_certificate_groups_certificates(
                    certificate_names=to_remove,
                    certificate_group_names=[module.params["name"]],
                )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Failed to delete certificates {0} from group {1}. Error: {2}".format(
                            to_remove, module.params["name"], get_error_message(res)
                        )
                    )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(type="str", default="present", choices=["absent", "present"]),
            name=dict(type="str", required=True),
            certificates=dict(type="list", elements="str"),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    state = module.params["state"]
    _check_certificate_realms(module)
    blade = get_system(module)

    certgrp = _group_exists(module, blade)

    if certgrp and state == "present" and module.params["certificates"]:
        update_certgrp(module, blade)
    elif state == "present" and not certgrp:
        create_certgrp(module, blade)
    elif state == "absent" and certgrp:
        if module.params["certificates"]:
            update_certgrp(module, blade)
        else:
            delete_certgrp(module, blade)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
