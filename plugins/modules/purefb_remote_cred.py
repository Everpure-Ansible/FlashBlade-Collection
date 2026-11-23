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
module: purefb_remote_cred
version_added: '1.0.0'
short_description: Create, modify and delete FlashBlade object store remote credentials
description:
- Create, modify and delete object store remote credentials
- You must have a correctly configured remote array or target
- The secret access key cannot be read back from the array, so an existing
  credential is only updated when I(access_key) differs from the configured
  access key ID, or when I(force) is set.
- A remote credential belongs to a realm when I(name) is given as
  C(realm::name). The realm prefix goes on I(name) only. I(target) is an
  array-level object and its name never carries a realm prefix.
- A remote credential in a realm needs an S3 target that is shared with the
  realm, see M(everpure.flashblade.purefb_resource_access).
- A realm-scoped administrator must use the realm-qualified name; a bare
  name is not placed in, or resolved to, the administrator's realm.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  state:
    description:
    - Define state of remote credential
    default: present
    choices: [ absent, present ]
    type: str
  name:
    description:
    - The name of the credential, without the name of its target.
    - For a credential in a realm use C(realm::name). The same name without
      the realm prefix is a different credential, at the array level.
    - A task manages one credential. A name that holds a comma or C(*) is
      refused, because the array reads a comma as the separator of a list of
      names and C(*) as a pattern.
    required: true
    type: str
  access_key:
    description:
    - Access Key ID of the S3 target
    type: str
  secret:
    description:
    - Secret Access Key for the S3 or Azure target
    type: str
  target:
    description:
    - Name of the connected remote array, or of the S3 target, that the
      credential is for.
    - A connected remote array can also be given by its management address.
    - The name is not case sensitive and never carries a realm prefix.
    - For a credential in a realm use an S3 target that is shared with the
      realm, see M(everpure.flashblade.purefb_resource_access) with
      I(resource_type=targets) and I(scope_type=realms). The array refuses
      the credential until the target is shared, which check mode cannot
      foresee.
    - A realm-scoped administrator sees only the targets that are shared
      with its realm.
    - A remote realm cannot be given as the target.
    required: true
    type: str
  force:
    description:
    - Re-send I(access_key) and I(secret) to an existing credential even
      when the access key ID is unchanged.
    - Required to rotate the secret of a credential whose access key ID
      stays the same, because the array never returns the current secret.
    - Always reports a change when set.
    type: bool
    default: false
    version_added: "1.29.0"
  context:
    description:
    - Name of fleet member on which to perform the operation.
    - This requires the array receiving the request is a member of a fleet
      and the context name to be a member of the same fleet.
    type: str
    default: ""
    version_added: "1.22.0"
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Create remote credential
  everpure.flashblade.purefb_remote_cred:
    name: cred1
    access_key: "3794fb12c6204e19195f"
    secret: "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    target: target1
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create remote credential in realm realm1 for an S3 target shared with the realm
  everpure.flashblade.purefb_remote_cred:
    name: realm1::cred1
    access_key: "3794fb12c6204e19195f"
    secret: "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    target: target1
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete remote credential
  everpure.flashblade.purefb_remote_cred:
    name: cred1
    target: target1
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = r"""
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        ObjectStoreRemoteCredentialsPost,
        ObjectStoreRemoteCredentials,
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

CONTEXT_API_VERSION = "2.17"
CONNECTED = ("connected", "connecting", "partially_connected")


def _realm_of(name):
    """Return the realm of a realm::name name, empty for an array-level name"""
    return name.rpartition("::")[0].strip()


def _same_name(first, second):
    """Return True when the array reads both names as the same name

    The array matches names without regard to case. A name the array did
    not return is the same as no name.
    """
    return (first or "").lower() == (second or "").lower()


def _check_name(module):
    """Refuse a name the array reads as a list of names or as a pattern

    In a read the array takes a comma for the separator of a list of names
    and * for a pattern, so such a name answers with several credentials, of
    this target or of another one, and the first of them would be taken for
    the credential of the task. A credential is created, changed and deleted
    one name at a time, so the name is refused before the array is asked.
    """
    name = module.params["name"]
    if "," in name or "*" in name:
        module.fail_json(
            msg="Remote credential name {0} is not the name of one credential: "
            "the array reads a comma as the separator of a list of names and "
            "* as a pattern.".format(name)
        )


def _items(module, res, what, absent_ok=False):
    """Return the items a read answered with

    A read that does not answer 200 fails the task with the array's
    message, so a refusal is never a traceback and never mistaken for a
    missing object. With absent_ok the array's "does not exist" is an empty
    list: only that answer means absent.
    """
    if res.status_code == 200:
        return list(res.items)
    error = get_error_message(res)
    if not (absent_ok and "does not exist" in str(error).lower()):
        module.fail_json(msg="Failed to get {0}. Error: {1}".format(what, error))
    return []


def _fail_not_connected(module):
    """Fail for a target that is not among the connected arrays and targets"""
    target = module.params["target"]
    msg = (
        "Selected target {0} is not connected, or is not visible to "
        "this user.".format(target)
    )
    if "::" in target:
        msg += (
            " The name of a target has no realm prefix: for a remote credential"
            " in a realm give name as realm::name."
        )
    elif _realm_of(module.params["name"]):
        msg += (
            " A remote credential in a realm needs an S3 target that is shared"
            " with the realm."
        )
    module.fail_json(msg=msg)


def get_connected(module, blade):
    """Return the name of the connected array or target, or None

    The name the array stores is returned, so that a target given in another
    letter case, or a connected array given by its management address, is
    addressed by its own name.
    """
    api_version = get_rest_api_version(blade)
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and module.params["context"]
    ):
        connected_blades = blade.get_array_connections(
            context_names=[module.params["context"]]
        )
    else:
        connected_blades = blade.get_array_connections()
    for target in _items(module, connected_blades, "array connections"):
        remote = getattr(getattr(target, "remote", None), "name", None)
        if (
            remote
            and (
                _same_name(remote, module.params["target"])
                or target.management_address == module.params["target"]
            )
            and target.status in CONNECTED
        ):
            return remote
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and module.params["context"]
    ):
        connected_targets = blade.get_targets(context_names=[module.params["context"]])
    else:
        connected_targets = blade.get_targets()
    for target in _items(module, connected_targets, "targets"):
        if (
            _same_name(target.name, module.params["target"])
            and target.status in CONNECTED
        ):
            return target.name
    return None


def get_remote_cred(module, blade):
    """Return Remote Credential or None"""
    api_version = get_rest_api_version(blade)
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and module.params["context"]
    ):
        res = blade.get_object_store_remote_credentials(
            names=[module.params["target"] + "/" + module.params["name"]],
            context_names=[module.params["context"]],
        )
    else:
        res = blade.get_object_store_remote_credentials(
            names=[module.params["target"] + "/" + module.params["name"]]
        )
    items = _items(
        module,
        res,
        "remote credential {0}/{1}".format(
            module.params["target"], module.params["name"]
        ),
        absent_ok=True,
    )
    return items[0] if items else None


def create_credential(module, blade):
    """Create remote credential"""
    changed = True
    api_version = get_rest_api_version(blade)
    if not module.check_mode:
        remote_cred = module.params["target"] + "/" + module.params["name"]
        remote_credentials = ObjectStoreRemoteCredentialsPost(
            access_key_id=module.params["access_key"],
            secret_access_key=module.params["secret"],
        )
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            res = blade.post_object_store_remote_credentials(
                names=[remote_cred],
                remote_credentials=remote_credentials,
                context_names=[module.params["context"]],
            )
        else:
            res = blade.post_object_store_remote_credentials(
                names=[remote_cred], remote_credentials=remote_credentials
            )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to create remote credential {0}. Error: {1}".format(
                    remote_cred, get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def update_credential(module, blade, current_cred):
    """Update remote credential

    The secret cannot be read back, so a change is only detected through
    the access key ID unless the caller forces a re-send.
    """
    changed = False
    api_version = get_rest_api_version(blade)
    if (
        module.params["force"]
        or getattr(current_cred, "access_key_id", None) != module.params["access_key"]
    ):
        changed = True
    if changed and not module.check_mode:
        remote_cred = module.params["target"] + "/" + module.params["name"]
        new_attr = ObjectStoreRemoteCredentials(
            access_key_id=module.params["access_key"],
            secret_access_key=module.params["secret"],
        )
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            res = blade.patch_object_store_remote_credentials(
                names=[remote_cred],
                remote_credentials=new_attr,
                context_names=[module.params["context"]],
            )
        else:
            res = blade.patch_object_store_remote_credentials(
                names=[remote_cred], remote_credentials=new_attr
            )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to update remote credential {0}. Error: {1}".format(
                    remote_cred, get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def delete_credential(module, blade):
    """Delete remote credential"""
    changed = True
    api_version = get_rest_api_version(blade)
    if not module.check_mode:
        remote_cred = module.params["target"] + "/" + module.params["name"]
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            res = blade.delete_object_store_remote_credentials(
                names=[remote_cred], context_names=[module.params["context"]]
            )
        else:
            res = blade.delete_object_store_remote_credentials(names=[remote_cred])
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete remote credential {0}. Error: {1}".format(
                    remote_cred, get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(type="str", default="present", choices=["present", "absent"]),
            name=dict(type="str", required=True),
            access_key=dict(type="str", no_log=False),
            secret=dict(type="str", no_log=True),
            target=dict(type="str", required=True),
            force=dict(type="bool", default=False),
            context=dict(type="str", default=""),
        )
    )

    required_if = [["state", "present", ["access_key", "secret"]]]

    module = AnsibleModule(
        argument_spec, required_if=required_if, supports_check_mode=True
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    _check_name(module)
    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and not module.params["context"]
    ):
        # If no context is provided set the context to the local array name
        fleet_res = blade.get_fleets()
        if fleet_res.status_code == 200 and list(fleet_res.items):
            module.params["context"] = list(blade.get_arrays().items)[0].name
    target = get_connected(module, blade)

    if not target:
        _fail_not_connected(module)
    # The credential is addressed by the name the array stores for its target
    module.params["target"] = target

    remote_cred = get_remote_cred(module, blade)

    if module.params["state"] == "present" and not remote_cred:
        create_credential(module, blade)
    elif module.params["state"] == "present":
        update_credential(module, blade, remote_cred)
    elif module.params["state"] == "absent" and remote_cred:
        delete_credential(module, blade)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
