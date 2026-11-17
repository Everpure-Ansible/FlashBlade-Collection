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
- Create, delete or modify realms on Everpure FlashBlades.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - The name of the realm.
    - This has to be unique and not equal to any existing realm or pod.
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
    - QoS policy to apply to the realm
    type: str
  rename:
    description:
    - Value to rename the specified realm to
    - This has to be unique and not equal to any existing realm or pods.
    type: str
  default_object_server:
    description:
    - Server inside the realm that object store accounts and virtual hosts
      created in the realm are exported through when no server is given.
    - Accepts the fully qualified name C(realm::server) or the bare server
      name, which is qualified with the realm name automatically.
    - The server must already exist inside the realm, so the default is
      normally set on an existing realm after its server has been created.
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


def get_pending_realm(module, blade):
    """Get Deleted realm"""
    res = blade.get_realms(destroyed=True, names=[module.params["name"]])
    if res.status_code == 200:
        return True
    return None


def get_policy(module, blade):
    """Get QoS Policy"""
    res = blade.get_qos_policies(names=[module.params["qos_policy"]])
    if res.status_code == 200:
        return True
    return None


def get_realm(module, blade):
    """Get Realm"""
    return _realm_exists(blade, module.params["name"])


def _realm_exists(blade, name):
    """Return True if a live (not destroyed) realm called name exists."""
    res = blade.get_realms(destroyed=False, names=[name])
    if res.status_code == 200:
        return True
    return None


def _qualify_server_name(realm_name, server_name, previous_realm_name=None):
    """Servers inside a realm are named realm::server on the array. A name
    qualified with previous_realm_name (the realm's name before a rename) is
    re-qualified with realm_name."""
    if "::" not in server_name:
        return "{0}::{1}".format(realm_name, server_name)
    prefix, bare = server_name.split("::", 1)
    if previous_realm_name and prefix == previous_realm_name:
        return "{0}::{1}".format(realm_name, bare)
    return server_name


def _desired_default_object_server(module, realm_name, previous_realm_name=None):
    """Return the wanted default server name, None to clear, or False when
    the parameter was not given."""
    wanted = module.params.get("default_object_server")
    if wanted is None:
        return False
    if wanted == "":
        return None
    return _qualify_server_name(realm_name, wanted, previous_realm_name)


def _server_exists(blade, server_name):
    """Return True if a server called server_name exists."""
    return blade.get_servers(names=[server_name]).status_code == 200


def _require_server(module, blade, server_name, realm_name):
    """Fail when the server does not exist; realm_name is the realm it is
    expected in."""
    if not _server_exists(blade, server_name):
        module.fail_json(
            msg="Server {0} does not exist in realm {1}.".format(
                server_name, realm_name
            )
        )


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


def update_default_object_server(module, blade, realm_name, previous_realm_name=None):
    """Reconcile the realm's default object store server.

    Returns True when the default was (or in check mode would be) changed.
    The parameter is ignored when not given; an empty string clears the
    default by sending an empty object_store list. previous_realm_name is
    the realm's name before a rename, so a server qualified with it is
    looked up under realm_name.
    """
    desired = _desired_default_object_server(module, realm_name, previous_realm_name)
    if desired is False:
        return False
    current = get_default_object_server(module, blade, realm_name)
    if desired == current:
        return False
    if desired:
        _require_server(module, blade, desired, realm_name)
    if not module.check_mode:
        object_store = []
        if desired:
            object_store = [ObjectStoreDefault(server=Reference(name=desired))]
        res = blade.patch_realms_defaults(
            realm_names=[realm_name],
            default_realm_configuration=RealmDefaults(object_store=object_store),
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Setting default object store server for realm {0} failed. "
                "Error: {1}".format(realm_name, get_error_message(res))
            )
    return True


def rename_realm(module, blade):
    changed = True
    old_name = module.params["name"]
    new_name = module.params["rename"]
    desired = _desired_default_object_server(module, new_name, old_name)
    if desired:
        # The server keeps the old realm prefix until the rename lands.
        _require_server(
            module, blade, _qualify_server_name(old_name, desired, new_name), old_name
        )
    if not module.check_mode:
        res = blade.patch_realms(names=[old_name], realm=RealmPatch(name=new_name))
        if res.status_code != 200:
            module.fail_json(
                msg="Rename to {0} failed. Error: {1}".format(
                    new_name, get_error_message(res)
                )
            )
        update_default_object_server(module, blade, new_name, old_name)
    module.exit_json(changed=changed)


def make_realm(module, blade):
    """Create Realm"""
    changed = True
    if module.params["qos_policy"] and not get_policy(module, blade):
        module.fail_json(
            msg="QoS policy {0} does not exist.".format(module.params["qos_policy"])
        )
    default_server = _desired_default_object_server(module, module.params["name"])
    if default_server:
        _require_server(module, blade, default_server, module.params["name"])
    if not module.check_mode:
        res = blade.post_realms(
            names=[module.params["name"]],
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
                    module.params["name"], get_error_message(res), hint
                )
            )
        if module.params["qos_policy"]:
            res = blade.post_qos_policies_members(
                policy_names=[module.params["qos_policy"]],
                member_names=[module.params["name"]],
                member_types=["realms"],
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="QoS policy assignment failed for realm {0}. Error: {1}".format(
                        module.params["name"], get_error_message(res)
                    )
                )
        if default_server:
            update_default_object_server(module, blade, module.params["name"])
    module.exit_json(changed=changed)


def update_realm(module, blade):
    """Update Realm QoS Policy and default object store server"""
    changed = False
    # Get current QoS policy for the realm. A realm without a policy may
    # come back as an error response, which has no items.
    current_policy = None
    res = blade.get_qos_policies_members(
        member_types=["realms"], member_names=[module.params["name"]]
    )
    if res.status_code == 200:
        first_member = next(iter(res.items), None)
        current_policy = getattr(getattr(first_member, "policy", None), "name", None)
    if module.params["qos_policy"] and current_policy != module.params["qos_policy"]:
        if not get_policy(module, blade):
            module.fail_json(
                msg="QoS policy {0} does not exist.".format(module.params["qos_policy"])
            )
        changed = True
        if not module.check_mode:
            if current_policy:
                res = blade.delete_qos_policies_members(
                    policy_names=[current_policy],
                    member_names=[module.params["name"]],
                    member_types=["realms"],
                )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Existing QoS policy removal failed for realm {0}. Error: {1}".format(
                            module.params["name"], get_error_message(res)
                        )
                    )
            res = blade.post_qos_policies_members(
                policy_names=[module.params["qos_policy"]],
                member_names=[module.params["name"]],
                member_types=["realms"],
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="QoS policy assignment failed for realm {0}. Error: {1}".format(
                        module.params["name"], get_error_message(res)
                    )
                )
    if update_default_object_server(module, blade, module.params["name"]):
        changed = True
    module.exit_json(changed=changed)


def recover_realm(module, blade):
    """Recover Realm"""
    changed = True
    default_server = _desired_default_object_server(module, module.params["name"])
    if default_server:
        _require_server(module, blade, default_server, module.params["name"])
    if not module.check_mode:
        res = blade.patch_realms(
            names=[module.params["name"]], realm=RealmPatch(destroyed=False)
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Recovery of realm {0} failed. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
        update_default_object_server(module, blade, module.params["name"])

    module.exit_json(changed=changed)


def eradicate_realm(module, blade):
    """Eradicate Realm"""
    changed = True
    if not module.check_mode:
        res = blade.delete_realms(
            names=[module.params["name"]],
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Eradicating realm {0} failed. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def delete_realm(module, blade):
    """Delete Realm"""
    changed = True
    if not module.check_mode:
        res = blade.patch_realms(
            names=[module.params["name"]],
            realm=RealmPatch(destroyed=True),
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Deleting realm {0} failed. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    if module.params["eradicate"]:
        eradicate_realm(module, blade)

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
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    if not HAS_PURESTORAGE:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    state = module.params["state"]
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
    realm = get_realm(module, blade)
    xrealm = get_pending_realm(module, blade)

    if xrealm and state == "present":
        recover_realm(module, blade)
    elif realm and state == "absent":
        delete_realm(module, blade)
    elif xrealm and state == "absent" and module.params["eradicate"]:
        eradicate_realm(module, blade)
    elif not realm and not xrealm and state == "present":
        if module.params["rename"] and _realm_exists(blade, module.params["rename"]):
            # The rename already happened on an earlier run; the default
            # object store server may still need reconciling under the new name.
            changed = update_default_object_server(
                module, blade, module.params["rename"], module.params["name"]
            )
            module.exit_json(changed=changed)
        make_realm(module, blade)
    elif state == "present" and realm and module.params["rename"] and not xrealm:
        rename_realm(module, blade)
    elif realm and state == "present":
        update_realm(module, blade)
    elif realm is None and state == "absent":
        module.exit_json(changed=False)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
