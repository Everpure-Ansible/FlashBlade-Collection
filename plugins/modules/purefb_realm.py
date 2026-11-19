#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Simon Dodsley (simon@everpuredata.com)
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
module: purefb_realm
version_added: '1.25.0'
short_description: Manage realms on Everpure FlashBlades
description:
- Create, rename, destroy, recover or eradicate realms on Everpure FlashBlades
  and manage the QoS policy, the default object store server and the default
  inbound TLS policy of a realm.
- The array matches realm names without regard to letter case.
- A realm-scoped administrator can manage the default object store server of
  its own realm. Creating or renaming a realm and changing its QoS policy or
  its default inbound TLS policy require an array administrator.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - The name of the realm.
    - This has to be unique among the realms of the array, including
      destroyed realms that are pending eradication.
    - A realm name cannot contain C(::) or a comma.
    type: str
    required: true
  without_default_access_list:
    description:
      - When creating a new realm, ensure it is created without any default resource accesses.
      - Only used when creating a new realm.
      - Purity//FB currently requires every realm to be created without the
        default access list, so the array rejects C(false). The default is
        therefore C(true); C(false) is passed through for Purity//FB versions
        that accept it.
    type: bool
    default: true
    version_added: '1.27.0'
  state:
    description:
    - Define whether the realm should exist or not.
    - A realm can only be destroyed when it is empty. The objects inside the
      realm, the resource accesses that share an array-level object with it
      (see M(everpure.flashblade.purefb_resource_access)) and the management
      access policy rules scoped to it (see
      M(everpure.flashblade.purefb_mgmt_policy)) have to be removed first.
      The module fails without changing anything when it finds such a
      resource access or rule.
    - A QoS policy attached to the realm is detached before the realm is
      destroyed. It is not attached again when the realm is recovered unless
      I(qos_policy) is given.
    type: str
    default: present
    choices: [ absent, present ]
  eradicate:
    description:
    - Define whether to eradicate the realm on delete or leave in trash.
    type : bool
    default: false
  qos_policy:
    description:
    - QoS policy to apply to the realm. A different policy that is attached
      to the realm is replaced.
    - Set to an empty string (C("")) to detach the QoS policy from the realm.
      When omitted the current policy is left unchanged.
    - QoS policies are not visible to a realm-scoped administrator, so the
      QoS policy of a realm can only be managed by an array administrator.
    - Only used when I(state) is C(present).
    - Requires Purity//FB 4.6.3 (REST API 2.20) or higher.
    type: str
  rename:
    description:
    - Value to rename the specified realm to.
    - This has to be unique among the realms of the array and cannot contain
      C(::). The module fails without changing anything when another realm
      already has the new name.
    - The other options of the task are applied to the renamed realm in the
      same run. A destroyed realm is recovered before it is renamed.
    - When I(name) no longer exists and a realm with the new name does, the
      rename is treated as already applied and the other options of the task
      are applied to the realm with the new name. The module cannot tell
      that realm from one that never had the old name, so it warns when this
      changes the realm.
    - When neither I(name) nor the new name exists the realm is created with
      the new name. A new name equal to I(name) renames nothing.
    - The array does not rename a realm to its own name in another letter
      case; such a request is refused.
    - The array accepts no change to the default inbound TLS policy of a realm
      that was renamed while it had one. A realm that has such a policy is
      therefore renamed in three steps. The policy is cleared, the realm is
      renamed and the policy, or the one given in
      I(default_inbound_tls_policy), is set under the new name of the realm.
    - Only used when I(state) is C(present).
    type: str
  default_object_server:
    description:
    - Server inside the realm that object store accounts and virtual hosts
      created in the realm are exported through when no server is given.
    - Accepts the fully qualified name C(realm::server) or the bare server
      name, which is qualified with the realm name automatically. A name
      qualified with any other realm is refused.
    - The server must already exist inside the realm. A realm that is created
      or recovered by the task has no servers, so the default is set by a
      later task, after the server has been created.
    - Set to an empty string (C("")) to clear the default. When omitted the
      current default is left unchanged.
    - The array refuses to delete a server while it is the realm default, so
      clear the default before deleting the server.
    - With I(rename) the server is looked up under the new realm name; a value
      qualified with the old realm name is accepted.
    - Only used when I(state) is C(present).
    - Requires Purity//FB 4.6.3 (REST API 2.20) or higher.
    type: str
    version_added: '1.30.0'
  default_inbound_tls_policy:
    description:
    - TLS policy for inbound connections to the network interfaces of the
      realm that have no TLS policy of their own. Without it these interfaces
      cannot be reached using TLS.
    - Only a TLS policy of the realm can be used. Accepts the fully qualified
      name C(realm::policy) or the bare policy name, which is qualified with
      the realm name automatically. A name qualified with any other realm is
      refused.
    - The policy must already exist inside the realm, so it is set by a later
      task than the one that creates or recovers the realm.
    - Set to an empty string (C("")) to clear the policy. When omitted the
      current policy is left unchanged.
    - With I(rename) the policy is looked up under the new realm name; a value
      qualified with the old realm name is accepted.
    - A realm that was renamed by other means while it had a default inbound
      TLS policy has to get its previous name back before the policy can be
      changed. The module fails without changing anything and names the
      previous name of the realm.
    - Only used when I(state) is C(present).
    type: str
    version_added: '1.30.0'
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Create new realm
  everpure.flashblade.purefb_realm:
    name: foo
    qos_policy: realm1_qos
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Detach the QoS policy from realm foo
  everpure.flashblade.purefb_realm:
    name: foo
    qos_policy: ""
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Destroy realm
  everpure.flashblade.purefb_realm:
    name: foo
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
    state: absent

- name: Recover deleted realm
  everpure.flashblade.purefb_realm:
    name: foo
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Destroy and Eradicate realm
  everpure.flashblade.purefb_realm:
    name: foo
    eradicate: true
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
    state: absent

- name: Rename realm foo to bar
  everpure.flashblade.purefb_realm:
    name: foo
    rename: bar
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Rename realm bar to baz and replace its QoS policy in the same task
  everpure.flashblade.purefb_realm:
    name: bar
    rename: baz
    qos_policy: realm2_qos
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Set the default object store server of realm foo to foo::s3srv
  everpure.flashblade.purefb_realm:
    name: foo
    default_object_server: s3srv
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Clear the default object store server of realm foo
  everpure.flashblade.purefb_realm:
    name: foo
    default_object_server: ""
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Set the default inbound TLS policy of realm foo to foo::strict
  everpure.flashblade.purefb_realm:
    name: foo
    default_inbound_tls_policy: strict
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Clear the default inbound TLS policy of realm foo
  everpure.flashblade.purefb_realm:
    name: foo
    default_inbound_tls_policy: ""
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
"""

RETURN = r"""
"""

HAS_PURESTORAGE = True
try:
    from pypureclient.flashblade import (
        RealmPatch,
        RealmDefaults,
        ObjectStoreDefault,
        Reference,
    )
except ImportError:
    HAS_PURESTORAGE = False

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

MINIMUM_API_VERSION = "2.19"
REALM_DEFAULTS_API_VERSION = "2.20"
REALM_QOS_API_VERSION = "2.20"
TLS_OPTION = "default_inbound_tls_policy"
NAME_OPTIONS = ("name", "rename", "qos_policy", "default_object_server", TLS_OPTION)


def _same(first, second):
    """The array matches names without regard to letter case."""
    return first is not None and second is not None and first.lower() == second.lower()


def _leaf(name):
    """Return a realm::name name without its realm."""
    return name.rpartition("::")[2] if name else name


def _realm_of(name):
    """Return the realm of a realm::name name, empty for a bare name."""
    return name.rpartition("::")[0] if name else ""


def _is_missing(res):
    """Only an answer that says the object does not exist means absent."""
    return "does not exist" in str(get_error_message(res)).lower()


def _first(module, res, what):
    """Return the first item of a read and None when the array says the
    object does not exist. Any other answer fails with the array's message."""
    if res.status_code == 200:
        return next(iter(res.items), None)
    if not _is_missing(res):
        module.fail_json(
            msg="Failed to read {0}. Error: {1}".format(what, get_error_message(res))
        )
    return None


def _get_realm(module, blade, name):
    """Return the realm called name, destroyed or not, or None when the
    array has no such realm."""
    return _first(module, blade.get_realms(names=[name]), "realm {0}".format(name))


def _get_qos_policy(module, blade, name):
    """Return the QoS policy called name, or None."""
    return _first(
        module, blade.get_qos_policies(names=[name]), "QoS policy {0}".format(name)
    )


def _attached_qos_policy(module, blade, realm_name, strict=True):
    """Return the name of the QoS policy the realm is a member of, or None.

    With strict a read the array refuses fails the task; without it the
    answer counts as no policy and the array decides on the request that
    follows."""
    res = blade.get_qos_policies_members(
        member_types=["realms"], member_names=[realm_name]
    )
    if res.status_code != 200 and not strict:
        return None
    member = _first(module, res, "the QoS policy of realm {0}".format(realm_name))
    return getattr(getattr(member, "policy", None), "name", None)


def _member_leaf(module, option, realm_names, realm_name):
    """Return the bare name of the realm member given in option.

    The value is the bare name or realm::name. Only an object of the realm
    can be used, so a value qualified with anything but one of realm_names
    (the names the realm goes by in this task) is refused."""
    value = module.params[option]
    prefix, separator, leaf = value.rpartition("::")
    if separator and not any(_same(prefix, known) for known in realm_names):
        module.fail_json(
            msg="{0} {1} is not in realm {2}. Give the bare name or "
            "{2}::{3}.".format(option, value, realm_name, leaf)
        )
    return leaf


def _tls_policy(realm):
    """Return the name of the default inbound TLS policy of a live realm,
    or None."""
    if realm is None or realm.destroyed:
        return None
    return getattr(getattr(realm, "default_inbound_tls_policy", None), "name", None)


def _patch_tls_policy(blade, realm_name, policy_name):
    """Set the default inbound TLS policy of the realm. An empty name clears
    the reference."""
    return blade.patch_realms(
        names=[realm_name],
        realm=RealmPatch(default_inbound_tls_policy=Reference(name=policy_name or "")),
    )


def _require_server(module, blade, server_name, realm_name):
    """Return the server called server_name. Fail when it does not exist;
    realm_name is the realm it is expected in."""
    server = _first(
        module,
        blade.get_servers(names=[server_name]),
        "server {0}".format(server_name),
    )
    if server is None:
        module.fail_json(
            msg="Server {0} does not exist in realm {1}.".format(
                server_name, realm_name
            )
        )
    return server


def _require_tls_policy(module, blade, policy_name, realm_name):
    """Return the TLS policy called policy_name. Fail when it does not
    exist; realm_name is the realm it is expected in."""
    policy = _first(
        module,
        blade.get_tls_policies(names=[policy_name]),
        "TLS policy {0}".format(policy_name),
    )
    if policy is None:
        module.fail_json(
            msg="TLS policy {0} does not exist in realm {1}.".format(
                policy_name, realm_name
            )
        )
    return policy


def get_default_object_server(module, blade, realm_name):
    """Return the realm's current default object store server name, or
    None when no default is set."""
    res = blade.get_realms_defaults(realm_names=[realm_name])
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read defaults for realm {0}. Error: {1}".format(
                realm_name, get_error_message(res)
            )
        )
    defaults = next(iter(res.items), None)
    object_store = getattr(defaults, "object_store", None) or []
    if not object_store:
        return None
    return getattr(getattr(object_store[0], "server", None), "name", None)


def _plan_qos(module, blade, realm):
    """Return (policy to detach, policy to attach), or None when the QoS
    policy of the realm stays as it is."""
    wanted = module.params["qos_policy"]
    if wanted is None:
        return None
    current = None
    if realm is not None:
        current = _attached_qos_policy(module, blade, realm.name)
    if wanted == "":
        return (current, None) if current else None
    if _same(current, wanted):
        return None
    policy = _get_qos_policy(module, blade, wanted)
    if policy is None:
        module.fail_json(
            msg="QoS policy {0} was not found or is not visible to this user. "
            "QoS policies are not visible to a realm-scoped administrator; the "
            "QoS policy of a realm is set by an array administrator.".format(wanted)
        )
    return (current, getattr(policy, "name", None) or wanted)


def _plan_member(module, blade, realm, realm_name, option):
    """Plan the default object store server or the default inbound TLS
    policy of the realm.

    Returns False when it stays as it is, None when it is cleared and
    otherwise the bare name of the server or policy to set. realm is the
    realm as the array has it, None when the task creates it, and
    realm_name the name it has at the end of the task. The member is looked
    up under the name the realm has now, because the members of a realm
    keep its old name until a rename lands."""
    wanted = module.params.get(option)
    if wanted is None:
        return False
    usable = realm is not None and not realm.destroyed
    current_realm = realm.name if realm is not None else realm_name
    current = None
    if option == "default_object_server":
        if usable:
            current = get_default_object_server(module, blade, current_realm)
    else:
        current = _tls_policy(realm)
    if wanted == "":
        return None if current else False
    known = [current_realm, realm_name, module.params["name"]]
    member_name = "{0}::{1}".format(
        current_realm, _member_leaf(module, option, known, realm_name)
    )
    if option == "default_object_server":
        member = _require_server(module, blade, member_name, current_realm)
    else:
        member = _require_tls_policy(module, blade, member_name, current_realm)
    # the name the array keeps, compared without the realm and without case
    leaf = _leaf(getattr(member, "name", None) or member_name)
    if _same(_leaf(current), leaf):
        return False
    return leaf


def _plan_settings(module, blade, realm, realm_name):
    """Work out what the task changes on the realm besides its name and its
    state. Every check that can refuse the task is made here, before
    anything is written, so a refused task leaves the realm as it was and
    check mode predicts the refusal."""
    plan = {}
    qos = _plan_qos(module, blade, realm)
    if qos is not None:
        plan["qos"] = qos
    for option in ("default_object_server", TLS_OPTION):
        member = _plan_member(module, blade, realm, realm_name, option)
        if member is not False:
            plan[option] = member
    return plan


def _detach_qos(module, blade, realm_name, policy_name):
    res = blade.delete_qos_policies_members(
        policy_names=[policy_name],
        member_names=[realm_name],
        member_types=["realms"],
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Existing QoS policy removal failed for realm {0}. Error: {1}".format(
                realm_name, get_error_message(res)
            )
        )


def _attach_qos(blade, realm_name, policy_name):
    return blade.post_qos_policies_members(
        policy_names=[policy_name],
        member_names=[realm_name],
        member_types=["realms"],
    )


def _apply_settings(module, blade, realm_name, plan):
    """Send the changes of _plan_settings to the realm called realm_name."""
    if "qos" in plan:
        detach, attach = plan["qos"]
        if detach:
            _detach_qos(module, blade, realm_name, detach)
        if attach:
            res = _attach_qos(blade, realm_name, attach)
            if res.status_code != 200:
                module.fail_json(
                    msg="QoS policy assignment failed for realm {0}. Error: {1}".format(
                        realm_name, get_error_message(res)
                    )
                )
    if "default_object_server" in plan:
        object_store = []
        if plan["default_object_server"]:
            server = "{0}::{1}".format(realm_name, plan["default_object_server"])
            object_store = [ObjectStoreDefault(server=Reference(name=server))]
        res = blade.patch_realms_defaults(
            realm_names=[realm_name],
            default_realm_configuration=RealmDefaults(object_store=object_store),
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Setting default object store server for realm {0} failed. "
                "Error: {1}".format(realm_name, get_error_message(res))
            )
    if TLS_OPTION in plan:
        policy = ""
        if plan[TLS_OPTION]:
            policy = "{0}::{1}".format(realm_name, plan[TLS_OPTION])
        res = _patch_tls_policy(blade, realm_name, policy)
        if res.status_code != 200:
            module.fail_json(
                msg="Setting default inbound TLS policy for realm {0} failed. "
                "Error: {1}".format(realm_name, get_error_message(res))
            )


def rename_realm(module, blade, old_name, new_name, tls_policy=None):
    """Rename Realm. tls_policy is the default inbound TLS policy of the
    realm, which is cleared before the rename (see _plan_tls_rename)."""
    if tls_policy:
        res = _patch_tls_policy(blade, old_name, "")
        if res.status_code != 200:
            module.fail_json(
                msg="Clearing default inbound TLS policy {0} of realm {1} before "
                "the rename failed. Error: {2}".format(
                    tls_policy, old_name, get_error_message(res)
                )
            )
    res = blade.patch_realms(names=[old_name], realm=RealmPatch(name=new_name))
    if res.status_code != 200:
        note = ""
        if tls_policy:
            # a refused rename leaves the realm as it was
            if _patch_tls_policy(blade, old_name, tls_policy).status_code != 200:
                note = (
                    " Default inbound TLS policy {0} was cleared for the rename "
                    "and could not be set again.".format(tls_policy)
                )
        module.fail_json(
            msg="Rename to {0} failed. Error: {1}{2}".format(
                new_name, get_error_message(res), note
            )
        )


def _restore_tls_policy(module, blade, old_name, new_name, leaf):
    """Set the default inbound TLS policy that was cleared for the rename of
    the realm from old_name to new_name. leaf is the bare name of the policy
    the renamed realm gets, None when the task clears it."""
    if not leaf:
        return
    policy = "{0}::{1}".format(new_name, leaf)
    res = _patch_tls_policy(blade, new_name, policy)
    if res.status_code != 200:
        module.fail_json(
            msg="Realm {0} was renamed to {1}, but its default inbound TLS "
            "policy, cleared for the rename, could not be set to {2}. "
            "Error: {3}".format(old_name, new_name, policy, get_error_message(res))
        )


def make_realm(module, blade, name):
    """Create Realm"""
    res = blade.post_realms(
        names=[name],
        without_default_access_list=module.params["without_default_access_list"],
    )
    if res.status_code != 200:
        hint = ""
        if not module.params["without_default_access_list"]:
            hint = (
                " This Purity//FB version requires realms to be created "
                "without the default access list; set "
                "without_default_access_list to true."
            )
        module.fail_json(
            msg="Creation of realm {0} failed. Error: {1}{2}".format(
                name, get_error_message(res), hint
            )
        )


def recover_realm(module, blade, name):
    """Recover Realm"""
    res = blade.patch_realms(names=[name], realm=RealmPatch(destroyed=False))
    if res.status_code != 200:
        module.fail_json(
            msg="Recovery of realm {0} failed. Error: {1}".format(
                name, get_error_message(res)
            )
        )


def _resolve_rename(module, blade, realm):
    """Decide what rename asks for.

    Returns (realm, new_name, adopted): the realm the task acts on, the
    name it is renamed to or, when the task creates it, created with (None
    without a rename), and whether the realm was found under the new name
    instead of name. Every refusal is decided here, before anything is
    written."""
    name = module.params["name"]
    rename = module.params["rename"]
    if not rename or rename == name:
        return realm, None, False
    if realm is not None:
        if rename == realm.name:
            return realm, None, False
        if _same(rename, realm.name):
            module.fail_json(
                msg="Cannot rename realm {0} to {1}: the new name differs from "
                "the name of the realm only in letter case. The array matches "
                "realm names without regard to case and does not rename a "
                "realm to its own name.".format(realm.name, rename)
            )
        other = _get_realm(module, blade, rename)
        if other is not None:
            module.fail_json(
                msg="Cannot rename realm {0} to {1}: a realm named {2} already "
                "exists{3}.".format(
                    realm.name,
                    rename,
                    other.name,
                    " and is pending eradication" if other.destroyed else "",
                )
            )
        return realm, rename, False
    if _same(rename, name):
        return None, rename, False
    other = _get_realm(module, blade, rename)
    if other is None:
        # neither name exists: the realm is created with its new name
        return None, rename, False
    if other.destroyed:
        module.fail_json(
            msg="Realm {0} does not exist and realm {1} is destroyed. Recover "
            "realm {1} with a task that names it.".format(name, other.name)
        )
    # renamed by an earlier run
    return other, None, True


def _plan_tls_rename(module, realm, new_name, realm_name, plan):
    """Carry the default inbound TLS policy of the realm over a rename.

    The array keeps the reference under the name the policy had when it was
    set and accepts no change to it once the realm has another name. A
    realm that has a policy is therefore renamed in three steps: the policy
    is cleared, the realm is renamed and the policy is set again. Returns
    the policy to clear before the rename, or None, and adds the policy to
    set afterwards to plan. A realm that was renamed with its policy in
    place accepts a change only after it got its previous name back; a
    task that needs one before that fails here."""
    current = _tls_policy(realm)
    if not current or not _realm_of(current):
        return None
    if new_name and _same(_realm_of(current), realm.name):
        plan.setdefault(TLS_OPTION, _leaf(current))
        return current
    if TLS_OPTION in plan and not _same(_realm_of(current), realm_name):
        module.fail_json(
            msg="The default inbound TLS policy of realm {0} is {1}, the name "
            "the policy had before the realm was renamed. The array accepts "
            "no change to the default inbound TLS policy of a realm in this "
            "state. Rename the realm back to {2} first.".format(
                realm.name, current, _realm_of(current)
            )
        )
    return None


def update_realm(module, blade, realm):
    """Create, recover, rename and update a realm in one pass."""
    realm, new_name, adopted = _resolve_rename(module, blade, realm)
    create = realm is None
    recover = realm is not None and bool(realm.destroyed)
    if create:
        realm_name = new_name or module.params["name"]
        new_name = None
    else:
        realm_name = new_name or realm.name
    plan = _plan_settings(module, blade, realm, realm_name)
    tls_policy = _plan_tls_rename(module, realm, new_name, realm_name, plan)
    changed = bool(create or recover or new_name or plan)
    if changed and not module.check_mode:
        if create:
            make_realm(module, blade, realm_name)
        if recover:
            recover_realm(module, blade, realm.name)
        if new_name:
            rename_realm(module, blade, realm.name, new_name, tls_policy)
            if tls_policy:
                _restore_tls_policy(
                    module, blade, realm.name, new_name, plan.pop(TLS_OPTION)
                )
        _apply_settings(module, blade, realm_name, plan)
    if adopted and changed:
        module.warn(
            "Realm {0} does not exist. Realm {1} was taken for the realm that an "
            "earlier run renamed, and the other options of the task apply to "
            "it.".format(module.params["name"], realm_name)
        )
    module.exit_json(changed=changed)


def _realm_attachments(blade, realm):
    """Return what the module can see is attached to the realm and makes
    the array refuse to destroy it.

    These reads only serve to name the attachment. A read the array
    refuses is skipped, and the destroy request gets the array's own
    answer."""
    found = []
    res = blade.get_resource_accesses(filter="scope.name='{0}'".format(realm.name))
    if res.status_code == 200:
        for access in res.items:
            scope = getattr(access, "scope", None)
            resource = getattr(access, "resource", None)
            if resource is not None and _same(getattr(scope, "name", None), realm.name):
                found.append(
                    "the resource access of {0} {1}".format(
                        getattr(resource, "resource_type", None), resource.name
                    )
                )
    res = blade.get_management_access_policies()
    if res.status_code == 200:
        for policy in res.items:
            for rule in getattr(policy, "rules", None) or []:
                scope = getattr(rule, "scope", None)
                if getattr(scope, "resource_type", None) == "realms" and _same(
                    getattr(scope, "name", None), realm.name
                ):
                    found.append(
                        "a rule of management access policy {0}".format(policy.name)
                    )
                    break
    return found


def eradicate_realm(module, blade, name):
    """Eradicate Realm"""
    changed = True
    if not module.check_mode:
        res = blade.delete_realms(names=[name])
        if res.status_code != 200:
            module.fail_json(
                msg="Eradicating realm {0} failed. Error: {1}".format(
                    name, get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def delete_realm(module, blade, realm, qos_supported):
    """Delete Realm"""
    changed = True
    name = realm.name
    attached = _realm_attachments(blade, realm)
    if attached:
        module.fail_json(
            msg="Realm {0} cannot be destroyed while it is referred to by {1}. "
            "A realm has to be empty before it can be destroyed.".format(
                name, " and ".join(attached)
            )
        )
    policy = None
    if qos_supported:
        policy = _attached_qos_policy(module, blade, name, strict=False)
    if not module.check_mode:
        if policy:
            # the array does not destroy a realm that has a QoS policy
            _detach_qos(module, blade, name, policy)
        res = blade.patch_realms(names=[name], realm=RealmPatch(destroyed=True))
        if res.status_code != 200:
            note = ""
            if policy:
                # a refused destroy leaves the realm as it was
                if _attach_qos(blade, name, policy).status_code != 200:
                    note = (
                        " QoS policy {0} was detached from the realm and could "
                        "not be attached again.".format(policy)
                    )
            module.fail_json(
                msg="Deleting realm {0} failed. Error: {1}{2}".format(
                    name, get_error_message(res), note
                )
            )
    if module.params["eradicate"]:
        eradicate_realm(module, blade, name)

    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str", required=True),
            without_default_access_list=dict(type="bool", default=True),
            state=dict(type="str", default="present", choices=["absent", "present"]),
            qos_policy=dict(type="str"),
            eradicate=dict(type="bool", default=False),
            rename=dict(type="str"),
            default_object_server=dict(type="str"),
            default_inbound_tls_policy=dict(type="str"),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    if not HAS_PURESTORAGE:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    state = module.params["state"]
    for option in NAME_OPTIONS:
        if "," in (module.params[option] or ""):
            # the array reads a comma as the separator of a list of names
            module.fail_json(
                msg="{0} {1} is not a name: the array reads a comma as the "
                "separator of a list of names. Give one name.".format(
                    option, module.params[option]
                )
            )
    for option in ("name", "rename"):
        if "::" in (module.params[option] or ""):
            module.fail_json(
                msg="{0} {1} is not a realm name: a realm name cannot contain "
                "'::'.".format(option, module.params[option])
            )
    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(MINIMUM_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg="Realms are not supported. Purity//FB 4.6.1, or higher, is required."
        )
    if module.params.get("default_object_server") is not None and LooseVersion(
        REALM_DEFAULTS_API_VERSION
    ) > LooseVersion(api_version):
        module.fail_json(
            msg="default_object_server requires Purity//FB 4.6.3 (REST API {0}), "
            "or higher.".format(REALM_DEFAULTS_API_VERSION)
        )
    qos_supported = LooseVersion(REALM_QOS_API_VERSION) <= LooseVersion(api_version)
    if module.params["qos_policy"] is not None and not qos_supported:
        module.fail_json(
            msg="qos_policy requires Purity//FB 4.6.3 (REST API {0}), "
            "or higher.".format(REALM_QOS_API_VERSION)
        )
    realm = _get_realm(module, blade, module.params["name"])

    if state == "present":
        update_realm(module, blade, realm)
    elif realm is not None and not realm.destroyed:
        delete_realm(module, blade, realm, qos_supported)
    elif realm is not None and module.params["eradicate"]:
        eradicate_realm(module, blade, realm.name)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
