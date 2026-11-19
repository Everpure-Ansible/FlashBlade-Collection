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
module: purefb_legal_hold
version_added: '1.30.0'
short_description: Manage FlashBlade file legal holds
description:
- Create, update or delete FlashBlade legal holds and apply them to, or
  release them from, files and directories in a file system.
- A legal hold is a named object. Once applied to a path the held files
  cannot be modified or deleted until every hold on them is released.
- Without I(file_system) and I(path) the module manages the legal hold
  object itself. With I(file_system) and I(path) it applies the hold to
  that single path (creating the hold first when it does not exist) or,
  with I(release=true) or I(state=absent), releases the hold from it. One
  path is handled per task.
- A legal hold that is still applied to one or more paths cannot be
  deleted. The module refuses the delete and lists the held paths; release
  them first.
- A legal hold in a realm is named C(realm::name). It can only be applied
  to a file system in the same realm, and a legal hold outside a realm only
  to a file system outside a realm. Realms require FlashBlade REST API
  version 2.19 or later.
- The array ignores the case of legal hold, file system and realm names,
  and so does the module.
- Requires FlashBlade REST API version 2.17 or later (Purity//FB 4.5.6+).
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - Name of the legal hold, 1 to 63 characters.
    - To manage a legal hold in a realm use C(realm::name). The realm prefix
      does not count towards the 63 characters.
    type: str
    required: true
  state:
    description:
    - Without I(path), whether the legal hold object should exist or not.
    - With I(file_system) and I(path), C(absent) releases the hold from
      the path and keeps the hold object (the same as I(release=true)).
    type: str
    default: present
    choices: [ absent, present ]
  description:
    description:
    - Description of the legal hold. Maximum 127 printable ASCII characters.
    - When omitted on an existing hold the description is left unchanged.
    - Ignored when releasing the hold from a path.
    type: str
  file_system:
    description:
    - Name of the file system containing I(path).
    - For a file system in a realm use C(realm::name). The legal hold and the
      file system must be in the same realm, or both outside a realm. Any
      other pair is refused before anything is read or written.
    - Must be given together with I(path).
    - The file system must already exist. It is checked before anything is
      read or written, so an unknown name fails with a clear message and a
      rejected apply never leaves a new hold behind.
    type: str
  path:
    description:
    - Absolute path of the file or directory inside I(file_system) to hold
      or release, for example C(/) or C(/projects/case-42). A trailing
      slash is ignored.
    - Must be given together with I(file_system).
    type: str
  recursive:
    description:
    - Apply or release the hold recursively. The array requires this to be
      C(true) when I(path) is a directory; a recursive operation on a large
      directory completes asynchronously and the held entity reports status
      C(applying) or C(releasing) until it finishes.
    type: bool
    default: false
  release:
    description:
    - Release the hold from I(path) instead of applying it.
    - Requires I(file_system) and I(path).
    type: bool
    default: false
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Create a legal hold
  everpure.flashblade.purefb_legal_hold:
    name: case-42
    description: Litigation hold for case 42
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Apply the hold to a single file
  everpure.flashblade.purefb_legal_hold:
    name: case-42
    file_system: evidence
    path: /case-42/contract.pdf
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Apply the hold to a directory tree
  everpure.flashblade.purefb_legal_hold:
    name: case-42
    file_system: evidence
    path: /case-42
    recursive: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Release the hold from the directory tree
  everpure.flashblade.purefb_legal_hold:
    name: case-42
    file_system: evidence
    path: /case-42
    recursive: true
    release: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create a legal hold in a realm and apply it to a file system of that realm
  everpure.flashblade.purefb_legal_hold:
    name: realm1::case-42
    file_system: realm1::evidence
    path: /case-42
    recursive: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete the legal hold (fails while any path is still held)
  everpure.flashblade.purefb_legal_hold:
    name: case-42
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = r"""
legal_hold:
  description: The legal hold after the operation.
  returned: when the legal hold exists after the operation
  type: dict
  contains:
    name:
      description: Name of the legal hold, C(realm::name) for a legal hold in a realm.
      type: str
    description:
      description: Description of the legal hold.
      type: str
    realms:
      description: Names of the realms the legal hold belongs to, empty outside a realm.
      type: list
      elements: str
  sample:
    name: case-42
    description: Litigation hold for case 42
    realms: []
held_entities:
  description: Every path the legal hold is currently applied to.
  returned: when the legal hold exists after the operation
  type: list
  elements: dict
  contains:
    file_system:
      description: Name of the file system containing the path, C(realm::name) for a file system in a realm.
      type: str
    path:
      description: Held path inside the file system.
      type: str
    status:
      description: One of C(applied), C(applying) or C(releasing).
      type: str
  sample:
    - file_system: evidence
      path: /case-42
      status: applied
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import LegalHold
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

MIN_REQUIRED_API_VERSION = "2.17"
REALM_API_VERSION = "2.19"
MAX_NAME_LENGTH = 63
MAX_DESCRIPTION_LENGTH = 127


def _realm_of(name):
    """Return the realm of a realm::name, or None for a name outside a realm."""
    if name and "::" in name:
        return name.split("::")[0]
    return None


def _leaf_name(name):
    """Return a name without its realm prefix."""
    return name.rsplit("::", 1)[-1]


def _same_name(first, second):
    """True when the array takes both names for the same object.

    The array ignores the case of names and reports each one as it was
    created.
    """
    return (first or "").lower() == (second or "").lower()


def _same_scope(name, file_system):
    """True when both names are in the same realm, or both outside a realm."""
    realm = _realm_of(name)
    fs_realm = _realm_of(file_system)
    if realm is None or fs_realm is None:
        return realm is fs_realm
    return _same_name(realm, fs_realm)


def _scope_text(name):
    realm = _realm_of(name)
    if realm is None:
        return "outside a realm"
    return "in realm {0}".format(realm)


def _norm_path(path):
    """Normalise a path for comparison: no trailing slash except for the root."""
    if path is None:
        return None
    return path.rstrip("/") or "/"


def _get_hold(module, blade):
    """Return the legal hold object, or None when it does not exist.

    The array answers 400 for an unknown name; any other failure is a
    real error and fails the module.
    """
    res = blade.get_legal_holds(names=[module.params["name"]])
    if res.status_code == 200:
        items = list(res.items)
        if items:
            return items[0]
        return None
    if res.status_code != 400:
        module.fail_json(
            msg="Failed to read legal hold {0}. Error: {1}".format(
                module.params["name"], get_error_message(res)
            )
        )
    return None


def _get_held_entities(module, blade, file_system=None, path=None):
    """Return the held entities of this hold, optionally for one path.

    Fails the module when the array rejects the query (for example a path
    that does not exist) so a refusal is never mistaken for 'not held'.
    """
    kwargs = {"names": [module.params["name"]]}
    if file_system:
        kwargs["file_system_names"] = [file_system]
        if path:
            kwargs["paths"] = [path]
    res = blade.get_legal_holds_held_entities(**kwargs)
    if res.status_code != 200:
        target = module.params["name"]
        if file_system and path:
            target = "{0} at {1}:{2}".format(target, file_system, path)
        elif file_system:
            target = "{0} in file system {1}".format(target, file_system)
        module.fail_json(
            msg="Failed to read held entities for legal hold {0}. Error: {1}".format(
                target, get_error_message(res)
            )
        )
    return list(res.items)


def _get_entity(module, blade):
    """Return the held entity for the requested file_system/path, or None.

    The array reports the file system under the name it was created with,
    whatever the case of the name in the request.
    """
    file_system = module.params["file_system"]
    path = module.params["path"]
    for entity in _get_held_entities(module, blade, file_system, path):
        fs_name = getattr(getattr(entity, "file_system", None), "name", None)
        if _same_name(fs_name, file_system) and _norm_path(
            getattr(entity, "path", None)
        ) == _norm_path(path):
            return entity
    return None


def _check_file_system(module, blade):
    """Fail when the requested file system cannot be read from the array.

    Runs for every file_system/path call, whether the hold exists or not,
    so an unknown file system is reported as such rather than through the
    held-entities query that would otherwise reject it.
    """
    file_system = module.params["file_system"]
    res = blade.get_file_systems(names=[file_system])
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read file system {0} for legal hold {1}. Error: {2}".format(
                file_system, module.params["name"], get_error_message(res)
            )
        )


def _check_realm(module, blade, api_version):
    """Fail a check mode run that would create a hold in an unusable realm.

    The array refuses to create a legal hold in a realm that does not exist
    or has been destroyed. A real run gets that answer from the create
    itself; check mode sends nothing, so it reads the realm instead of
    reporting a change the real run cannot make. Only a definite answer
    fails the module.
    """
    name = module.params["name"]
    realm = _realm_of(name)
    if not realm or LooseVersion(REALM_API_VERSION) > LooseVersion(api_version):
        return
    res = blade.get_realms(names=[realm])
    if res.status_code == 400:
        reason = get_error_message(res)
    elif res.status_code == 200:
        items = list(res.items)
        if not items:
            reason = "Realm does not exist."
        elif getattr(items[0], "destroyed", False):
            reason = "Realm has been destroyed."
        else:
            return
    else:
        return
    module.fail_json(
        msg="Legal hold {0} cannot be created in realm {1}. Error: {2}".format(
            name, realm, reason
        )
    )


def _hold_dict(hold):
    return {
        "name": getattr(hold, "name", None),
        "description": getattr(hold, "description", None),
        "realms": [
            getattr(realm, "name", None)
            for realm in (getattr(hold, "realms", None) or [])
        ],
    }


def _entity_dict(entity):
    return {
        "file_system": getattr(getattr(entity, "file_system", None), "name", None),
        "path": getattr(entity, "path", None),
        "status": getattr(entity, "status", None),
    }


def _exit(module, blade, changed):
    """Exit with the hold and its held entities as the array reports them."""
    result = {"changed": changed}
    hold = _get_hold(module, blade)
    if hold is not None:
        result["legal_hold"] = _hold_dict(hold)
        result["held_entities"] = [
            _entity_dict(entity) for entity in _get_held_entities(module, blade)
        ]
    module.exit_json(**result)


def ensure_hold(module, blade, hold, api_version):
    """Create the hold, or update its description. Returns True when changed."""
    description = module.params["description"]
    if hold is None:
        if module.check_mode:
            _check_realm(module, blade, api_version)
        else:
            if description is not None:
                body = LegalHold(description=description)
            else:
                body = LegalHold()
            res = blade.post_legal_holds(names=[module.params["name"]], hold=body)
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to create legal hold {0}. Error: {1}".format(
                        module.params["name"], get_error_message(res)
                    )
                )
        return True
    current = getattr(hold, "description", None) or ""
    if description is not None and description != current:
        if not module.check_mode:
            res = blade.patch_legal_holds(
                names=[module.params["name"]],
                hold=LegalHold(description=description),
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to update legal hold {0}. Error: {1}".format(
                        module.params["name"], get_error_message(res)
                    )
                )
        return True
    return False


def delete_hold(module, blade):
    """Delete the hold, refusing while it is still applied to any path."""
    entities = _get_held_entities(module, blade)
    if entities:
        held = ", ".join(
            "{0}:{1}".format(
                getattr(getattr(entity, "file_system", None), "name", None),
                getattr(entity, "path", None),
            )
            for entity in entities
        )
        module.fail_json(
            msg=(
                "Legal hold {0} is still applied to {1} path(s): {2}. "
                "Release every path (file_system and path with release=true) "
                "before deleting the hold."
            ).format(module.params["name"], len(entities), held)
        )
    changed = True
    if not module.check_mode:
        res = blade.delete_legal_holds(names=[module.params["name"]])
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete legal hold {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def apply_entity(module, blade, hold, api_version):
    """Apply the hold to file_system/path, creating the hold when needed.

    A path whose previous release is still in progress counts as not held
    and is applied again; the array decides whether it accepts that. The
    file system has already been validated by main(), so a rejected apply
    never leaves a freshly created hold behind.
    """
    changed = ensure_hold(module, blade, hold, api_version)
    entity = None
    if hold is not None:
        entity = _get_entity(module, blade)
    if entity is None or getattr(entity, "status", None) == "releasing":
        changed = True
        if not module.check_mode:
            res = blade.post_legal_holds_held_entities(
                names=[module.params["name"]],
                file_system_names=[module.params["file_system"]],
                paths=[module.params["path"]],
                recursive=module.params["recursive"],
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to apply legal hold {0} to {1}:{2}. Error: {3}".format(
                        module.params["name"],
                        module.params["file_system"],
                        module.params["path"],
                        get_error_message(res),
                    )
                )
    _exit(module, blade, changed)


def release_entity(module, blade, hold):
    """Release the hold from file_system/path; the hold object is kept."""
    if hold is None:
        module.exit_json(changed=False)
    entity = _get_entity(module, blade)
    if entity is None or getattr(entity, "status", None) == "releasing":
        _exit(module, blade, False)
    changed = True
    if not module.check_mode:
        res = blade.patch_legal_holds_held_entities(
            names=[module.params["name"]],
            file_system_names=[module.params["file_system"]],
            paths=[module.params["path"]],
            released=True,
            recursive=module.params["recursive"],
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to release legal hold {0} from {1}:{2}. Error: {3}".format(
                    module.params["name"],
                    module.params["file_system"],
                    module.params["path"],
                    get_error_message(res),
                )
            )
    _exit(module, blade, changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str", required=True),
            state=dict(type="str", default="present", choices=["absent", "present"]),
            description=dict(type="str"),
            file_system=dict(type="str"),
            path=dict(type="str"),
            recursive=dict(type="bool", default=False),
            release=dict(type="bool", default=False),
        )
    )

    module = AnsibleModule(
        argument_spec,
        required_together=[["file_system", "path"]],
        supports_check_mode=True,
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    name = module.params["name"]
    if not 1 <= len(_leaf_name(name)) <= MAX_NAME_LENGTH:
        module.fail_json(
            msg=(
                "Legal hold name must be 1 to {0} characters, not counting "
                "a realm prefix"
            ).format(MAX_NAME_LENGTH)
        )
    description = module.params["description"]
    if description is not None and len(description) > MAX_DESCRIPTION_LENGTH:
        module.fail_json(
            msg="Legal hold description must be {0} characters or fewer".format(
                MAX_DESCRIPTION_LENGTH
            )
        )
    path = module.params["path"]
    if module.params["release"] and not path:
        module.fail_json(msg="release=true requires file_system and path")
    if path and not path.startswith("/"):
        module.fail_json(msg="path must be absolute, starting with /")
    if path:
        path = _norm_path(path)
        module.params["path"] = path
        file_system = module.params["file_system"]
        if not _same_scope(name, file_system):
            module.fail_json(
                msg=(
                    "Legal hold {0} ({1}) and file system {2} ({3}) must be in "
                    "the same realm, or both outside a realm. Use the "
                    "realm::name form for both names or for neither."
                ).format(name, _scope_text(name), file_system, _scope_text(file_system))
            )

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg=(
                "FlashBlade REST version not supported. "
                "Minimum version required: {0} (Purity//FB 4.5.6+)"
            ).format(MIN_REQUIRED_API_VERSION)
        )

    hold = _get_hold(module, blade)
    state = module.params["state"]

    if path:
        # Validate the file system before any held-entity read or write so
        # an unknown name fails clearly instead of as a held-entities error.
        _check_file_system(module, blade)
        if state == "absent" or module.params["release"]:
            release_entity(module, blade, hold)
        else:
            apply_entity(module, blade, hold, api_version)
    elif state == "present":
        _exit(module, blade, ensure_hold(module, blade, hold, api_version))
    elif hold is not None:
        delete_hold(module, blade)
    else:
        module.exit_json(changed=False)


if __name__ == "__main__":
    main()
