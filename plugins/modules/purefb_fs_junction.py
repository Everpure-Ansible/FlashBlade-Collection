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
module: purefb_fs_junction
version_added: '1.30.0'
short_description: Manage FlashBlade file system junctions
description:
- Create or delete local file system junctions on a FlashBlade.
- A junction mounts the root of one file system (the destination) at a
  directory inside another file system (the origin), so clients that mount
  the origin traverse into the destination through that directory. Junctions
  can be nested but may not form a cycle, the destination is always the root
  of a file system, and the junction directory cannot be under C(.snapshot).
- A junction is immutable. Its origin, destination and path cannot be
  changed after creation; use I(recreate) to delete and re-create it.
- Deleting a junction removes only the junction configuration. The junction
  directory remains in the origin file system as a normal empty directory.
- Junction configuration is not replicated with a file system. Only the
  empty directory is replicated, so junctions must be re-created on the
  target array, for example when promoting a replica.
- An array supports up to 1000 junctions, and a file system can be the
  origin of up to 1000 junctions.
- Requires FlashBlade REST API version 2.25 or later (Purity//FB 4.8.0+).
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - Name of the junction.
    - Must be 1 to 63 characters of letters, digits, C(_) and C(-), begin and
      end with a letter or digit, and include at least one letter.
    - When the file systems are realm-scoped the junction name must carry
      the same realm prefix, for example C(realm1::junction1).
    - A junction name is unique across the array and all of its realms,
      whatever the realm prefix. C(realm1::junction1) cannot be created
      while C(junction1) or C(realm2::junction1) exists.
    - Check mode reports this conflict only when the other junction is
      visible to the user. A user who is limited to a realm does not see
      the junctions outside that realm.
    - The array does not distinguish upper and lower case when it looks up
      a junction, a file system or a realm, and names are compared the
      same way. A name spelled in another case than the array stores it is
      the same object. A real run returns the spelling the array stores.
    - The realm prefix in the name of a new junction is the exception. The
      array accepts it only in the spelling it stores for the realm, and
      check mode does not predict that refusal.
    type: str
    required: true
  state:
    description:
    - Define whether the junction should exist or not.
    type: str
    default: present
    choices: [ absent, present ]
  origin_fs:
    description:
    - Name of the origin file system that holds the junction directory.
    - For a file system in a realm use the realm-qualified name, for
      example C(realm1::fs1). The junction and both file systems must be
      in the same realm, or all three at array level.
    - Required when I(state=present).
    type: str
  destination_fs:
    description:
    - Name of the destination file system whose root is mounted at the
      junction directory.
    - For a file system in a realm use the realm-qualified name, for
      example C(realm1::fs2). The junction and both file systems must be
      in the same realm, or all three at array level.
    - Required when I(state=present).
    type: str
  path:
    description:
    - Absolute path of the junction directory inside the origin file
      system, for example C(/projects/alpha).
    - A missing leading C(/) is added before the path is sent to the array
      or compared with an existing junction.
    - Required when I(state=present).
    type: str
  use_existing_directory:
    description:
    - If C(true) the junction is created on an existing empty directory at
      I(path).
    - If C(false) the array creates the directory and the request fails
      when something already exists at I(path).
    - Only used when a junction is created. A re-create with I(recreate)
      that keeps the origin file system and path always reuses the
      directory left behind by the deleted junction.
    type: bool
    default: false
  recreate:
    description:
    - Controls what happens when the junction exists but its origin,
      destination or path differ from the requested values.
    - If C(false) the module fails, because junctions cannot be modified.
    - If C(true) the module deletes the junction and creates it again with
      the requested values. When only the destination changes the junction
      is re-created on its existing directory.
    type: bool
    default: false
  context:
    description:
    - Name of fleet member on which to perform the operation.
    - This requires the array receiving the request is a member of a fleet
      and the context name to be a member of the same fleet.
    type: str
    default: ""
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Create a junction, letting the array create the directory
  everpure.flashblade.purefb_fs_junction:
    name: projects-alpha
    origin_fs: projects
    destination_fs: alpha
    path: /alpha
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create a junction on an existing empty directory
  everpure.flashblade.purefb_fs_junction:
    name: projects-beta
    origin_fs: projects
    destination_fs: beta
    path: /beta
    use_existing_directory: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create a junction between two file systems of the realm realm1
  everpure.flashblade.purefb_fs_junction:
    name: realm1::projects-alpha
    origin_fs: realm1::projects
    destination_fs: realm1::alpha
    path: /alpha
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Move a junction to a different directory (delete and re-create)
  everpure.flashblade.purefb_fs_junction:
    name: projects-alpha
    origin_fs: projects
    destination_fs: alpha
    path: /archive/alpha
    recreate: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete a junction (the directory remains in the origin file system)
  everpure.flashblade.purefb_fs_junction:
    name: projects-alpha
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = r"""
junction:
  description:
  - Details of the junction after the operation. In check mode the
    requested values are returned and I(status) is C(null).
  - For a junction in a realm the junction name and both file system names
    are realm-qualified, for example C(realm1::projects), in check mode and
    in a real run alike.
  returned: when I(state=present)
  type: dict
  contains:
    name:
      description: Name of the junction, with its realm prefix when it is in a realm.
      type: str
      sample: projects-alpha
    origin_fs:
      description:
      - Origin file system that holds the junction directory.
      - Realm-qualified when the junction is in a realm.
      type: str
      sample: projects
    destination_fs:
      description:
      - Destination file system mounted at the junction directory.
      - Realm-qualified when the junction is in a realm.
      type: str
      sample: alpha
    path:
      description: Absolute path of the junction directory in the origin file system.
      type: str
      sample: /alpha
    status:
      description: Junction status reported by the array.
      type: str
      sample: CONNECTED
"""


HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        FileSystemJunction,
        Reference,
    )
except ImportError:
    HAS_PYPURECLIENT = False


import re
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

MIN_REQUIRED_API_VERSION = "2.25"


def _context_kwargs(module):
    """Return context_names kwargs when a fleet context is set.

    Junctions require REST 2.25, above the 2.17 fleet-context floor, so every
    junction endpoint accepts context_names once the version gate has passed.
    """
    if module.params["context"]:
        return {"context_names": [module.params["context"]]}
    return {}


def _norm_path(path):
    """Return the path as an absolute path without a trailing slash."""
    if path is None:
        return None
    return "/" + path.strip("/")


def _realm(name):
    """Return the realm prefix of a realm-scoped name, or an empty string."""
    if name and "::" in name:
        return name.split("::", 1)[0]
    return ""


def _leaf(name):
    """Return a name without its realm prefix."""
    return name.split("::", 1)[-1]


def _same_name(first, second):
    """Compare two names as the array does, without regard to case."""
    return first.lower() == second.lower()


def _qualify(fs_name, realm):
    """Return a file system name with the realm prefix of its junction.

    The array reports the file systems of a junction in a realm without the
    realm prefix, where they read as the array-level file systems of the
    same names. Both are always in the realm of the junction.
    """
    if fs_name and realm and "::" not in fs_name:
        return "{0}::{1}".format(realm, fs_name)
    return fs_name


def _same_fs(current, requested):
    """Compare a file system of an existing junction with the requested one.

    Both are in the realm of the junction: the request is validated to
    carry the realm prefix of the junction name, and the junction was found
    by that name. The names are therefore compared without the prefix.

    The array resolves a name in any case to the same object and returns
    the spelling it stores, so the comparison ignores case. A file system
    that the request spells in another case is not drift, and recreate
    does not delete and re-create the junction for it.
    """
    if current is None or requested is None:
        return current == requested
    return _same_name(_leaf(current), _leaf(requested))


def _junction_facts(junction):
    name = getattr(junction, "name", None)
    realm = _realm(name)
    return {
        "name": name,
        "origin_fs": _qualify(
            getattr(getattr(junction, "origin_file_system", None), "name", None),
            realm,
        ),
        "destination_fs": _qualify(
            getattr(getattr(junction, "destination_file_system", None), "name", None),
            realm,
        ),
        "path": getattr(junction, "junction_origin_path", None),
        "status": getattr(junction, "status", None),
    }


def _requested_facts(module, name=None):
    return {
        "name": name or module.params["name"],
        "origin_fs": module.params["origin_fs"],
        "destination_fs": module.params["destination_fs"],
        "path": _norm_path(module.params["path"]),
        "status": None,
    }


def _get_junction(module, blade):
    """Return the junction object, or None when it does not exist.

    The array answers a lookup of a missing junction, including a name in
    an unknown realm, with 200 and no items, so any other status is a
    failed read (an unknown fleet context, authentication, a transient
    fault ...) and fails the task instead of masquerading as "absent",
    which would let state=absent report ok and state=present attempt a
    create.
    """
    res = blade.get_file_system_junctions(
        names=[module.params["name"]], **_context_kwargs(module)
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read file system junction {0}. Error: {1}".format(
                module.params["name"], get_error_message(res)
            )
        )
    items = list(res.items)
    return items[0] if items else None


def _check_realms(module):
    """Fail early when the realm prefixes disagree.

    The array requires both file systems and the junction to be in the same
    realm, but a bare junction name on realm-scoped file systems is rejected
    with a message about the file system realms not matching, which hides
    the real cause.

    The array finds a realm under a prefix in any case, so prefixes that
    differ only in case name the same realm and are not refused here. The
    one spelling the array does refuse, in the name of a new junction, is
    explained when it refuses it.
    """
    origin_realm = _realm(module.params["origin_fs"])
    destination_realm = _realm(module.params["destination_fs"])
    if not _same_name(origin_realm, destination_realm):
        module.fail_json(
            msg=(
                "Origin file system {0} and destination file system {1} "
                "must be in the same realm."
            ).format(module.params["origin_fs"], module.params["destination_fs"])
        )
    if not _same_name(_realm(module.params["name"]), origin_realm):
        if origin_realm:
            module.fail_json(
                msg=(
                    "Junction name must carry the realm prefix of its file "
                    "systems, for example {0}::{1}."
                ).format(origin_realm, module.params["name"].split("::", 1)[-1])
            )
        module.fail_json(
            msg=(
                "Junction name {0} is realm-scoped but file systems {1} and "
                "{2} are not."
            ).format(
                module.params["name"],
                module.params["origin_fs"],
                module.params["destination_fs"],
            )
        )


def _name_holders(module, blade):
    """Return the names of the junctions that use the requested leaf name.

    A junction name is unique across the array and all of its realms: j1,
    realm1::j1 and realm2::j1 exclude each other, and the array refuses the
    create with "already exists" although the requested name is not in use.
    A caller that is limited to a realm sees only the junctions of that
    realm. Returns None when the lookup fails, which leaves the array as
    the only judge of the request. The same applies to a name with a
    character that no junction name can hold: a filter has no escape for
    a quote, and a wildcard would match the names of other junctions.
    """
    leaf = _leaf(module.params["name"])
    if not re.match(r"[A-Za-z0-9_-]+\Z", leaf):
        return None
    res = blade.get_file_system_junctions(
        filter="name='{0}' or name='*::{0}'".format(leaf), **_context_kwargs(module)
    )
    if res.status_code != 200:
        return None
    return [item.name for item in res.items]


def _stored_realm(module, blade):
    """Return the realm of the origin file system as the array spells it.

    The array finds a file system under a realm prefix in any case, but it
    accepts the realm prefix of a new junction name only in the spelling
    it stores. Returns None when the file system cannot be read.
    """
    res = blade.get_file_systems(
        names=[module.params["origin_fs"]], **_context_kwargs(module)
    )
    if res.status_code != 200:
        return None
    items = list(res.items)
    return _realm(items[0].name) if items else None


def _name_taken_msg(module, holder):
    return (
        "File system junction {0} cannot be created because junction {1} "
        "already uses the name {2}. A junction name must be unique across "
        "the array and all of its realms."
    ).format(module.params["name"], holder, _leaf(holder))


def _name_refused(error):
    """Return True when the array refused a create because the name is taken.

    The refusals about the junction directory also say "already exists",
    but they name the path.
    """
    text = str(error).lower()
    return "already exists" in text and "path" not in text


def _create_error(module, blade, error):
    """Return the failure message for a create that the array refused.

    The module's own lookup found the name unused, so when the array says
    that the name is taken the junction that holds it is in another scope.
    A refusal about the realms of a request whose realm prefixes agree is
    explained when the array stores the realm in another case than the
    junction name spells it. Every other refusal is relayed as it is.
    """
    name = module.params["name"]
    plain = "Failed to create file system junction {0}. Error: {1}".format(name, error)
    if _name_refused(error):
        holders = _name_holders(module, blade)
        if holders is None or any(_same_name(name, holder) for holder in holders):
            return plain
        if holders:
            return _name_taken_msg(module, holders[0])
        return (
            "Failed to create file system junction {0}. Error: {1}. No "
            "junction named {2} is visible to this user, so the name is in "
            "use in another realm or at array level. A junction name must be "
            "unique across the array and all of its realms."
        ).format(name, str(error).rstrip("."), _leaf(name))
    realm = _realm(name)
    if realm and "realm" in str(error).lower():
        # The realm prefixes of the request agree, so a refusal about the
        # realms is about the spelling of the prefix of the junction name.
        stored = _stored_realm(module, blade)
        if stored and stored != realm and _same_name(stored, realm):
            return (
                "Failed to create file system junction {0}. Error: {1}. The "
                "array stores the realm as {2} and accepts only that spelling "
                "in the name of a new junction: use {2}::{3}."
            ).format(name, str(error).rstrip("."), stored, _leaf(name))
    return plain


def _post_junction(module, blade, use_existing_directory, recreate_as=None):
    """Create the junction and return the array's view of it.

    ``recreate_as`` is the name of the junction that was just deleted, as
    the array stored it. The junction is re-created under that name: the
    array accepts the realm prefix of a new junction name only in the
    spelling it stores, so a request that found the junction under another
    spelling would delete it and then be refused the re-create.
    """
    name = recreate_as or module.params["name"]
    res = blade.post_file_system_junctions(
        names=[name],
        origin_file_system_names=[module.params["origin_fs"]],
        file_system_junction=FileSystemJunction(
            destination_file_system=Reference(name=module.params["destination_fs"]),
            junction_origin_path=_norm_path(module.params["path"]),
        ),
        use_existing_directory=use_existing_directory,
        **_context_kwargs(module)
    )
    if res.status_code != 200:
        error = get_error_message(res)
        if recreate_as:
            module.fail_json(
                msg=(
                    "File system junction {0} was deleted but re-creating it "
                    "failed. Error: {1}"
                ).format(name, error)
            )
        module.fail_json(msg=_create_error(module, blade, error))
    items = list(res.items)
    if items:
        return _junction_facts(items[0])
    return _requested_facts(module, name)


def _delete_junction(module, blade, name):
    """Delete the junction under the name the array stores for it."""
    res = blade.delete_file_system_junctions(names=[name], **_context_kwargs(module))
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to delete file system junction {0}. Error: {1}".format(
                name, get_error_message(res)
            )
        )


def create_junction(module, blade):
    changed = True
    facts = _requested_facts(module)
    if module.check_mode:
        # Predict the refusal of a name that another scope already uses.
        for holder in _name_holders(module, blade) or []:
            if not _same_name(holder, module.params["name"]):
                module.fail_json(msg=_name_taken_msg(module, holder))
    else:
        facts = _post_junction(module, blade, module.params["use_existing_directory"])
    module.exit_json(changed=changed, junction=facts)


def update_junction(module, blade, junction):
    current = _junction_facts(junction)
    drift = []
    same_origin = _same_fs(current["origin_fs"], module.params["origin_fs"])
    same_path = _norm_path(current["path"]) == _norm_path(module.params["path"])
    if not same_origin:
        drift.append(
            "origin_fs {0} -> {1}".format(
                current["origin_fs"], module.params["origin_fs"]
            )
        )
    if not _same_fs(current["destination_fs"], module.params["destination_fs"]):
        drift.append(
            "destination_fs {0} -> {1}".format(
                current["destination_fs"], module.params["destination_fs"]
            )
        )
    if not same_path:
        drift.append(
            "path {0} -> {1}".format(current["path"], _norm_path(module.params["path"]))
        )
    if not drift:
        module.exit_json(changed=False, junction=current)
    if not module.params["recreate"]:
        module.fail_json(
            msg=(
                "File system junction {0} exists with different settings ({1}). "
                "Junctions cannot be modified; set recreate=true to delete and "
                "re-create it."
            ).format(module.params["name"], ", ".join(drift))
        )
    changed = True
    stored_name = current["name"] or module.params["name"]
    facts = _requested_facts(module, stored_name)
    if not module.check_mode:
        _delete_junction(module, blade, stored_name)
        # Deleting a junction leaves its directory behind, so a re-create on
        # the same origin and path must build on that existing directory.
        facts = _post_junction(
            module,
            blade,
            module.params["use_existing_directory"] or (same_origin and same_path),
            recreate_as=stored_name,
        )
    module.exit_json(changed=changed, junction=facts)


def delete_junction(module, blade, junction):
    changed = True
    if not module.check_mode:
        _delete_junction(
            module, blade, getattr(junction, "name", None) or module.params["name"]
        )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str", required=True),
            state=dict(type="str", default="present", choices=["absent", "present"]),
            origin_fs=dict(type="str"),
            destination_fs=dict(type="str"),
            path=dict(type="str"),
            use_existing_directory=dict(type="bool", default=False),
            recreate=dict(type="bool", default=False),
            context=dict(type="str", default=""),
        )
    )
    required_if = [["state", "present", ["origin_fs", "destination_fs", "path"]]]

    module = AnsibleModule(
        argument_spec, required_if=required_if, supports_check_mode=True
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg=(
                "FlashBlade REST version not supported. "
                "Minimum version required: {0} (Purity//FB 4.8.0+)"
            ).format(MIN_REQUIRED_API_VERSION)
        )

    state = module.params["state"]
    junction = _get_junction(module, blade)

    if state == "absent":
        if junction:
            delete_junction(module, blade, junction)
        module.exit_json(changed=False)

    _check_realms(module)
    if not junction:
        create_junction(module, blade)
    update_junction(module, blade, junction)


if __name__ == "__main__":
    main()
