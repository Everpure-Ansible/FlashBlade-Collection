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
module: purefb_ssh_ca_policy
version_added: '1.30.0'
short_description: Manage FlashBlade SSH Certificate Authority policies and their members
description:
- Create, update or delete a FlashBlade SSH Certificate Authority (CA)
  policy.
- An SSH CA policy names the signing authority, a public key or a
  certificate already present on the array, whose signed user SSH
  certificates are accepted for SSH login, and optionally a static list of
  authorized principals those certificates must carry.
- Reconcile the admins the policy is attached to, and whether the policy is
  attached to the array, where it becomes the default for every admin that
  has no explicit SSH CA policy.
- Requires FlashBlade REST API version 2.14 or later (Purity//FB 4.4.x+).
  The I(context) option requires REST API version 2.30 or later.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
notes:
- An admin attached to any SSH CA policy must present a signed SSH
  certificate to log in over SSH; plain SSH public-key login no longer
  works for that admin. Attaching the policy to the array applies the same
  requirement to every admin without an explicit policy. Review changes
  with check mode first and keep a password login path available.
- Membership is many-to-many. An admin or the array may be attached to
  several SSH CA policies at once, so attaching a member to this policy
  never detaches it from another policy.
- When a certificate is the signing authority, user SSH certificates it
  signed are no longer accepted once that certificate has expired.
- Deletion safety is enforced by this module, not by the array. A policy
  with attached members is not deleted until they are detached
  (I(admins=[]) together with I(array=false)).
- The built-in C(ir) and C(root) accounts cannot be attached.
- The array accepts but ignores a name change on PATCH, so this module
  offers no rename. To change a policy name, create a new policy and move
  the members to it.
- When I(state=absent), configuration and membership options are ignored.
- SSH CA policies and their members, the admins and the array, are
  array-level objects. Only the signing authority can live in a realm, see
  I(signing_authority).
- The array resolves the names of policies, signing authorities and admins
  without regard to case, so a name written in a different case from the one
  stored on the array is not a change.
options:
  name:
    description:
    - Name of the SSH CA policy.
    - SSH CA policies are array-level objects. The array refuses a policy
      name in the C(realm::name) form.
    type: str
    required: true
  state:
    description:
    - Whether the policy should exist.
    default: present
    choices: [ absent, present ]
    type: str
  enabled:
    description:
    - Whether the policy is active.
    - Omit to leave unchanged on an existing policy; the array defaults to
      C(true) when creating a new policy.
    type: bool
  signing_authority:
    description:
    - Name of the public key or certificate on the array that signs the
      user SSH certificates accepted by this policy.
    - A certificate that lives in a realm is named C(realm::certificate).
      Public keys are array-level objects and have no realm form.
    - Required when creating a policy. Omit to leave unchanged on an
      existing policy.
    type: str
  signing_authority_type:
    description:
    - Whether I(signing_authority) names a public key or a certificate.
    - Required when creating a policy. Omit on an existing policy to keep
      the type of the current signing authority.
    type: str
    choices: [ public_key, certificate ]
  static_authorized_principals:
    description:
    - Principals, at least one of which a user SSH certificate must
      contain to be accepted. When unset, a certificate must contain the
      logging-in user's own name as a principal.
    - At most 16 entries of at most 128 characters each.
    - Omit to leave unchanged; provide an empty list to clear the list.
    type: list
    elements: str
  admins:
    description:
    - Declarative list of admin names the policy is attached to.
    - Setting the list attaches the missing admins and detaches every
      admin not listed here.
    - Omit (or set to C(null)) to leave the current admin attachments
      untouched. Provide an empty list to detach every admin.
    type: list
    elements: str
  array:
    description:
    - Whether the policy is attached to the array, making it the default
      SSH CA policy for every admin without an explicit policy.
    - Omit to leave the array attachment untouched.
    type: bool
  context:
    description:
    - Name of the fleet member on which to perform the operation.
    - This requires the array receiving the request is a member of a fleet
      and the context name to be a member of the same fleet.
    - Requires FlashBlade REST API version 2.30 or later.
    type: str
    default: ""
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Create an SSH CA policy signed by an uploaded public key
  everpure.flashblade.purefb_ssh_ca_policy:
    name: ops-ssh-ca
    signing_authority: ops-ca-key
    signing_authority_type: public_key
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create a policy signed by a certificate, restricted to two principals
  everpure.flashblade.purefb_ssh_ca_policy:
    name: ops-ssh-ca
    signing_authority: corp-ssh-ca
    signing_authority_type: certificate
    static_authorized_principals:
      - storage-ops
      - oncall
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create a policy signed by a certificate that lives in a realm
  everpure.flashblade.purefb_ssh_ca_policy:
    name: tenant-ssh-ca
    signing_authority: realm1::corp-ssh-ca
    signing_authority_type: certificate
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Attach the policy to two admins
  everpure.flashblade.purefb_ssh_ca_policy:
    name: ops-ssh-ca
    admins:
      - alice
      - bob
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Make the policy the array-wide default for admins
  everpure.flashblade.purefb_ssh_ca_policy:
    name: ops-ssh-ca
    array: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Disable the policy and clear its principal list
  everpure.flashblade.purefb_ssh_ca_policy:
    name: ops-ssh-ca
    enabled: false
    static_authorized_principals: []
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Detach every member from the policy
  everpure.flashblade.purefb_ssh_ca_policy:
    name: ops-ssh-ca
    admins: []
    array: false
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete the policy (fails while members are attached)
  everpure.flashblade.purefb_ssh_ca_policy:
    name: ops-ssh-ca
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = r"""
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        ReferenceWritable,
        SshCertificateAuthorityPolicy,
        SshCertificateAuthorityPolicyPost,
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
)
from ansible_collections.everpure.flashblade.plugins.module_utils.version import (
    LooseVersion,
)

MIN_REQUIRED_API_VERSION = "2.14"
# context_names on the policy POST/PATCH/DELETE calls arrived with 2.30; the
# GET and member calls accepted it earlier, but the module gates once.
CONTEXT_API_VERSION = "2.30"
# Accounts the array exempts from SSH CA policies; never attach or detach.
PROTECTED_ADMINS = frozenset(["ir", "root"])
MAX_PRINCIPALS = 16
MAX_PRINCIPAL_LENGTH = 128
# Module signer type -> REST resource_type of the signing_authority reference.
SIGNER_RESOURCE_TYPE = {"public_key": "public-keys", "certificate": "certificates"}
# REST member resource_type -> module member type.
MEMBER_TYPE_MODULE = {"admins": "admin", "arrays": "array"}


def _context_kwargs(module):
    """Return the context_names kwargs dict when a context is set."""
    if module.params["context"]:
        return {"context_names": [module.params["context"]]}
    return {}


def _validate_principals(module):
    principals = module.params["static_authorized_principals"]
    if principals is None:
        return
    if len(principals) > MAX_PRINCIPALS:
        module.fail_json(
            msg="static_authorized_principals may contain at most {0} entries".format(
                MAX_PRINCIPALS
            )
        )
    if len(set(principals)) != len(principals):
        module.fail_json(msg="Duplicate entry in static_authorized_principals")
    for principal in principals:
        if not principal or len(principal) > MAX_PRINCIPAL_LENGTH:
            module.fail_json(
                msg=(
                    "Each static_authorized_principals entry must be 1 to {0} "
                    "characters long"
                ).format(MAX_PRINCIPAL_LENGTH)
            )


def _validate_admins(module):
    admins = module.params["admins"]
    if not admins:
        return
    # The array resolves admin names without regard to case.
    if len(set(admin.lower() for admin in admins)) != len(admins):
        module.fail_json(
            msg=(
                "Duplicate admin name in admins. Admin names are compared "
                "without regard to case."
            )
        )
    for admin in admins:
        if not admin:
            module.fail_json(msg="admins may not contain an empty name")
        if admin.lower() in PROTECTED_ADMINS:
            module.fail_json(
                msg=(
                    "Admin {0} is exempt from SSH certificate authority "
                    "policies and cannot be attached."
                ).format(admin)
            )


def _get_policy(module, blade, name):
    """The policy object, or None when it does not exist.

    The array answers a lookup of a missing policy with a 400 naming the
    policy as nonexistent, so only that error reads as None; any other
    failure fails the task instead of masquerading as "absent".
    """
    res = blade.get_ssh_certificate_authority_policies(
        names=[name], **_context_kwargs(module)
    )
    if res.status_code == 200:
        items = list(res.items)
        return items[0] if items else None
    error = get_error_message(res)
    lowered = str(error).lower()
    if error and ("does not exist" in lowered or "not found" in lowered):
        return None
    module.fail_json(
        msg="Failed to read SSH CA policy {0}. Error: {1}".format(name, error)
    )


def _get_members(module, blade):
    """Current membership as a set of (module_type, member_name)."""
    res = blade.get_ssh_certificate_authority_policies_members(
        policy_names=[module.params["name"]], **_context_kwargs(module)
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to list members of SSH CA policy {0}. Error: {1}".format(
                module.params["name"], get_error_message(res)
            )
        )
    members = set()
    for item in res.items:
        resource_type = getattr(item.member, "resource_type", None)
        members.add(
            (MEMBER_TYPE_MODULE.get(resource_type, resource_type), item.member.name)
        )
    return members


def _get_array_name(module, blade):
    """Name of the array (or context array) the policy would attach to."""
    res = blade.get_arrays(**_context_kwargs(module))
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read the array name. Error: {0}".format(
                get_error_message(res)
            )
        )
    items = list(res.items)
    if not items:
        module.fail_json(msg="Failed to read the array name: no array returned.")
    return items[0].name


def _validate_admins_exist(module, blade, admins):
    """Fail when a desired admin does not exist.

    The members GET returns 200 with no items for an unknown admin, so
    existence has to come from /admins. Runs in check mode too, so check
    mode fails exactly where a real run would.
    """
    for admin in sorted(admins):
        res = blade.get_admins(names=[admin], **_context_kwargs(module))
        if res.status_code != 200:
            module.fail_json(
                msg=(
                    "Admin {0} does not exist or could not be verified. " "Error: {1}"
                ).format(admin, get_error_message(res))
            )


def _desired_member_changes(module, blade, current):
    """Return (to_add, to_remove) sets of (type, name) for the given params.

    Only the member types the task names are reconciled: admins when
    I(admins) is a list, the array when I(array) is a boolean.
    """
    to_add = set()
    to_remove = set()

    if module.params["admins"] is not None:
        # The array resolves admin names without regard to case and reports
        # the stored spelling, so the two sides are matched on lowered names.
        # An admin to attach keeps the spelling of the task, an admin to
        # detach the spelling of the array.
        desired = set(admin.lower() for admin in module.params["admins"])
        current_admins = set(member for member in current if member[0] == "admin")
        attached = set(member[1].lower() for member in current_admins)
        to_add |= set(
            ("admin", admin)
            for admin in module.params["admins"]
            if admin.lower() not in attached
        )
        to_remove |= set(
            member
            for member in current_admins
            if member[1].lower() not in desired
            # Never detach exempt accounts, even if the array reports them.
            and member[1].lower() not in PROTECTED_ADMINS
        )

    if module.params["array"] is not None:
        current_arrays = set(member for member in current if member[0] == "array")
        if module.params["array"]:
            array_name = _get_array_name(module, blade)
            if ("array", array_name) not in current_arrays:
                to_add.add(("array", array_name))
        else:
            to_remove |= current_arrays

    return to_add, to_remove


def _detach(module, blade, member_type, member_name):
    kwargs = dict(
        policy_names=[module.params["name"]],
        member_names=[member_name],
        **_context_kwargs(module)
    )
    if member_type == "admin":
        res = blade.delete_ssh_certificate_authority_policies_admins(**kwargs)
    else:
        res = blade.delete_ssh_certificate_authority_policies_arrays(**kwargs)
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to detach {0} {1} from SSH CA policy {2}. Error: {3}".format(
                member_type,
                member_name,
                module.params["name"],
                get_error_message(res),
            )
        )


def _attach(module, blade, member_type, member_name):
    kwargs = dict(
        policy_names=[module.params["name"]],
        member_names=[member_name],
        **_context_kwargs(module)
    )
    if member_type == "admin":
        res = blade.post_ssh_certificate_authority_policies_admins(**kwargs)
    else:
        res = blade.post_ssh_certificate_authority_policies_arrays(**kwargs)
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to attach {0} {1} to SSH CA policy {2}. Error: {3}".format(
                member_type,
                member_name,
                module.params["name"],
                get_error_message(res),
            )
        )


def reconcile_members(module, blade, current=None):
    """Diff desired members against actual; attach/detach to converge.

    Returns True if any change was made (or would be made in check mode).
    Membership is many-to-many on the array, so attaching a member needs no
    conflict handling against other policies. I(current) is the membership
    already read by the caller; it is read here when not supplied.
    """
    if module.params["admins"] is None and module.params["array"] is None:
        return False

    if current is None:
        current = _get_members(module, blade)
    to_add, to_remove = _desired_member_changes(module, blade, current)

    # Existence checks run in check mode too so that check mode fails
    # exactly where a real run would.
    _validate_admins_exist(
        module, blade, [name for mtype, name in to_add if mtype == "admin"]
    )

    if not to_add and not to_remove:
        return False
    if module.check_mode:
        return True

    for member_type, member_name in sorted(to_remove):
        _detach(module, blade, member_type, member_name)
    for member_type, member_name in sorted(to_add):
        _attach(module, blade, member_type, member_name)
    return True


def _warn_if_live(module, members):
    """Warn when changing the policy while members are attached.

    I(members) is the membership as it was before this run, so members the
    same task has just attached do not trigger the warning.
    """
    if members:
        module.warn(
            "SSH CA policy {0} is attached to one or more members. The new "
            "settings apply to their subsequent SSH logins.".format(
                module.params["name"]
            )
        )


def _signer_resource_type(module, existing=None):
    """REST resource_type of the desired signing authority.

    When the task omits signing_authority_type on an existing policy, the
    type of the current signing authority is kept, so a rerun that names
    the signer without its type stays idempotent.
    """
    signer_type = module.params["signing_authority_type"]
    if signer_type is not None:
        return SIGNER_RESOURCE_TYPE[signer_type]
    current = getattr(existing, "signing_authority", None)
    resource_type = getattr(current, "resource_type", None)
    if resource_type is None:
        module.fail_json(
            msg=(
                "signing_authority_type is required: the type of the current "
                "signing authority of SSH CA policy {0} could not be determined."
            ).format(module.params["name"])
        )
    return resource_type


def _signer_reference(module, resource_type):
    return ReferenceWritable(
        name=module.params["signing_authority"], resource_type=resource_type
    )


def _signer_changed(module, existing):
    """Whether the desired signing authority differs from the current one.

    The array resolves the name of a public key or certificate, with or
    without a realm prefix, without regard to case and reports the stored
    spelling, so the names are compared the same way.
    """
    desired = module.params["signing_authority"]
    if desired is None:
        return False
    current = getattr(existing, "signing_authority", None)
    current_name = getattr(current, "name", None)
    if current_name is None or current_name.lower() != desired.lower():
        return True
    return getattr(current, "resource_type", None) != _signer_resource_type(
        module, existing
    )


def delete_policy(module, blade):
    """Guarded delete: the members check lives client-side."""
    if _get_members(module, blade):
        module.fail_json(
            msg=(
                "SSH CA policy {0} has attached members. Detach them first "
                "(admins: [] and array: false with state: present)."
            ).format(module.params["name"])
        )
    if not module.check_mode:
        res = blade.delete_ssh_certificate_authority_policies(
            names=[module.params["name"]], **_context_kwargs(module)
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete SSH CA policy {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=True)


def create_policy(module, blade):
    if not module.params["signing_authority"]:
        module.fail_json(msg="Creating an SSH CA policy requires signing_authority.")
    if module.params["signing_authority_type"] is None:
        module.fail_json(
            msg="Creating an SSH CA policy requires signing_authority_type."
        )
    # Preflight member existence before the policy POST so a refused attach
    # cannot leave a half-configured policy behind, and so check mode fails
    # exactly where a real run would.
    if module.params["admins"]:
        _validate_admins_exist(module, blade, module.params["admins"])
    if module.params["array"]:
        _get_array_name(module, blade)

    if module.check_mode:
        module.exit_json(changed=True)

    post_kwargs = {
        "signing_authority": _signer_reference(module, _signer_resource_type(module))
    }
    if module.params["enabled"] is not None:
        post_kwargs["enabled"] = module.params["enabled"]
    if module.params["static_authorized_principals"] is not None:
        post_kwargs["static_authorized_principals"] = module.params[
            "static_authorized_principals"
        ]
    res = blade.post_ssh_certificate_authority_policies(
        names=[module.params["name"]],
        policy=SshCertificateAuthorityPolicyPost(**post_kwargs),
        **_context_kwargs(module)
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to create SSH CA policy {0}. Error: {1}".format(
                module.params["name"], get_error_message(res)
            )
        )
    reconcile_members(module, blade)
    module.exit_json(changed=True)


def update_policy(module, blade, existing):
    changed = False

    # Membership before this run: reconciled below and, when settings change,
    # the basis of the live-members warning. Read once and only when needed.
    members_before = None
    if module.params["admins"] is not None or module.params["array"] is not None:
        members_before = _get_members(module, blade)
        if reconcile_members(module, blade, members_before):
            changed = True

    patch_kwargs = {}
    if (
        module.params["enabled"] is not None
        and module.params["enabled"] != existing.enabled
    ):
        patch_kwargs["enabled"] = module.params["enabled"]

    if _signer_changed(module, existing):
        patch_kwargs["signing_authority"] = _signer_reference(
            module, _signer_resource_type(module, existing)
        )

    principals = module.params["static_authorized_principals"]
    if principals is not None and set(principals) != set(
        getattr(existing, "static_authorized_principals", None) or []
    ):
        patch_kwargs["static_authorized_principals"] = principals

    if patch_kwargs:
        changed = True
        if members_before is None:
            members_before = _get_members(module, blade)
        _warn_if_live(module, members_before)
        if not module.check_mode:
            # There is no dedicated Patch model; the base model carries the
            # writable fields and only the set ones are sent.
            res = blade.patch_ssh_certificate_authority_policies(
                names=[module.params["name"]],
                policy=SshCertificateAuthorityPolicy(**patch_kwargs),
                **_context_kwargs(module)
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to update SSH CA policy {0}. Error: {1}".format(
                        module.params["name"], get_error_message(res)
                    )
                )

    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str", required=True),
            state=dict(type="str", default="present", choices=["absent", "present"]),
            enabled=dict(type="bool"),
            signing_authority=dict(type="str"),
            signing_authority_type=dict(
                type="str",
                choices=["public_key", "certificate"],
            ),
            static_authorized_principals=dict(type="list", elements="str"),
            admins=dict(type="list", elements="str"),
            array=dict(type="bool"),
            context=dict(type="str", default=""),
        )
    )

    module = AnsibleModule(
        argument_spec,
        supports_check_mode=True,
        required_by={"signing_authority_type": "signing_authority"},
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    state = module.params["state"]
    if state == "present":
        _validate_principals(module)
        _validate_admins(module)

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg=(
                "FlashBlade REST version {0} does not support SSH certificate "
                "authority policies (requires {1}+)."
            ).format(api_version, MIN_REQUIRED_API_VERSION)
        )
    if module.params["context"] and LooseVersion(CONTEXT_API_VERSION) > LooseVersion(
        api_version
    ):
        module.fail_json(
            msg=(
                "FlashBlade REST version {0} does not support the context "
                "option for SSH certificate authority policies (requires {1}+)."
            ).format(api_version, CONTEXT_API_VERSION)
        )

    existing = _get_policy(module, blade, module.params["name"])

    if state == "absent":
        if existing is None:
            module.exit_json(changed=False)
        delete_policy(module, blade)
    elif existing is None:
        create_policy(module, blade)
    else:
        update_policy(module, blade, existing)


if __name__ == "__main__":
    main()
