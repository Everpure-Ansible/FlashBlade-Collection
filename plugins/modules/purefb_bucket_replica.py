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


DOCUMENTATION = """
---
module: purefb_bucket_replica
version_added: '1.0.0'
short_description:  Manage bucket replica links between Everpure FlashBlades
description:
    - This module manages bucket replica links between Everpure FlashBlades.
    - An unhealthy link, for example while its target is unreachable, can be
      paused or deleted, and re-applying its current settings is a no-op.
      Resuming it, or changing its credential or cascading setting, is
      refused until the link is healthy again.
    - The array itself refuses to pause a link whose set-up has not completed,
      for example when the target bucket has no versioning enabled; the
      failure message then includes the link's status details.
    - A replica link belongs to the realm of its local bucket. For a bucket
      in a realm give I(name) as C(realm::bucket) and I(credential) as
      C(realm::credential), and use an S3 target that is shared with the
      realm as I(target).
    - A realm-scoped administrator must use the realm-qualified names; a bare
      name is not placed in, or resolved to, the administrator's realm.
author: Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
      - Local Bucket Name.
      - A bucket in a realm is named C(realm::bucket). Its replica link
        belongs to the same realm.
    required: true
    type: str
  state:
    description:
      - Creates or modifies a bucket replica link
    required: false
    default: present
    type: str
    choices: [ "present", "absent" ]
  target:
    description:
      - Remote array or target name to create replica on.
      - The name of a target never carries a realm prefix. For a bucket in a
        realm use an S3 target that has been shared with the realm, see
        M(everpure.flashblade.purefb_resource_access).
    required: false
    type: str
  target_bucket:
    description:
      - Name of target bucket name
      - If not supplied, will default to I(name). For a bucket in a realm
        that replicates to an S3 target the array stores this default without
        the realm prefix.
    type: str
    required: false
  paused:
    description:
      - State of the bucket replica link
      - Pausing is allowed while the link is unhealthy.
    type: bool
    default: false
  credential:
    description:
      - Name of remote credential name to use, without the name of its
        target.
      - For a bucket in a realm use a remote credential of the same realm,
        named C(realm::credential).
      - The task fails, and nothing is changed, when I(name) and
        I(credential) are not in the same realm.
      - The name is not case sensitive.
    required: false
    type: str
  cascading:
    description:
      - Objects replicated to this bucket via a replica link from
        another array will also be replicated by this link to the
        remote bucket
    type: bool
    default: false
    version_added: "1.14.0"
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

EXAMPLES = """
- name: Create new bucket replica from foo to bar on arrayB
  everpure.flashblade.purefb_bucket_replica:
    name: foo
    target: arrayB
    target_bucket: bar
    credential: cred_1
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create new bucket replica for bucket foo of realm realm1 to S3 target s3target
  everpure.flashblade.purefb_bucket_replica:
    name: realm1::foo
    target: s3target
    target_bucket: bar
    credential: realm1::cred_1
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Pause existing bucket replica link
  everpure.flashblade.purefb_bucket_replica:
    name: foo
    paused: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete bucket replica link foo
  everpure.flashblade.purefb_bucket_replica:
    name: foo
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = """
"""

CONTEXT_API_VERSION = "2.17"

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        BucketReplicaLink,
        ReferenceWritable,
        BucketReplicaLinkPost,
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


def _realm_of(name):
    """Return the realm of a realm::name name, empty for an array-level name"""
    return name.rpartition("::")[0].strip()


def _same_name(first, second):
    """Return True when the array reads both names as the same name

    The array matches names without regard to case.
    """
    return first.lower() == second.lower()


def _check_same_realm(module):
    """Fail unless the bucket and the remote credential are in the same realm

    A replica link belongs to the realm of its local bucket and uses a remote
    credential of that realm, so both names carry the same realm prefix or
    neither does. The array refuses any other pair when a link is created
    and when the credential of a link is changed, so such a pair is refused
    before anything is read or written, in check mode too.
    """
    name = module.params["name"]
    credential = module.params["credential"]
    if not credential:
        return
    realm = _realm_of(name)
    credential_realm = _realm_of(credential)
    if _same_name(realm, credential_realm):
        return
    if realm:
        hint = "A remote credential of this bucket is named {0}::<credential>".format(
            realm
        )
    else:
        hint = (
            "A remote credential of realm {0} is used by buckets named "
            "{0}::<bucket>".format(credential_realm)
        )
    module.fail_json(
        msg="Bucket {0} cannot use remote credential {1}: a bucket and the "
        "remote credential of its replica link must be in the same realm. "
        "{2}.".format(name, credential, hint)
    )


def _items(module, res, what):
    """Return the items a read answered with, an empty list when absent

    Only the array's "does not exist" means absent. Any other refusal fails
    the task with the array's message, so it is never mistaken for a missing
    object.
    """
    if res.status_code == 200:
        return list(res.items)
    error = get_error_message(res)
    if "does not exist" not in str(error).lower():
        module.fail_json(msg="Failed to get {0}. Error: {1}".format(what, error))
    return []


def get_local_bucket(module, blade):
    """Return Bucket or None"""
    api_version = get_rest_api_version(blade)
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and module.params["context"]
    ):
        res = blade.get_buckets(
            context_names=[module.params["context"]],
            names=[module.params["name"]],
        )
    else:
        res = blade.get_buckets(names=[module.params["name"]])
    items = _items(module, res, "bucket {0}".format(module.params["name"]))
    return items[0] if items else None


def get_remote_cred(module, blade, target):
    """Return Remote Credential or None"""
    api_version = get_rest_api_version(blade)
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and module.params["context"]
    ):
        res = blade.get_object_store_remote_credentials(
            names=[target + "/" + module.params["credential"]],
            context_names=[module.params["context"]],
        )
    else:
        res = blade.get_object_store_remote_credentials(
            names=[target + "/" + module.params["credential"]]
        )
    items = _items(
        module,
        res,
        "remote credential {0}/{1}".format(target, module.params["credential"]),
    )
    return items[0] if items else None


def get_local_rl(module, blade):
    """Return Bucket Replica Link or None"""
    api_version = get_rest_api_version(blade)
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and module.params["context"]
    ):
        res = blade.get_bucket_replica_links(
            local_bucket_names=[module.params["name"]],
            context_names=[module.params["context"]],
        )
    else:
        res = blade.get_bucket_replica_links(local_bucket_names=[module.params["name"]])
    items = _items(
        module, res, "replica link of bucket {0}".format(module.params["name"])
    )
    return items[0] if items else None


def get_connected(module, blade):
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
    for item in _items(module, connected_blades, "array connections"):
        if _same_name(item.remote.name, module.params["target"]) and item.status in [
            "connected",
            "connecting",
            "partially_connected",
        ]:
            return item.remote.name
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and module.params["context"]
    ):
        connected_targets = blade.get_targets(context_names=[module.params["context"]])
    else:
        connected_targets = blade.get_targets()
    for target in _items(module, connected_targets, "targets"):
        if _same_name(target.name, module.params["target"]) and target.status in [
            "connected",
            "connecting",
            "partially_connected",
        ]:
            return target.name
    return None


def create_rl(module, blade, remote_cred):
    """Create Bucket Replica Link"""
    changed = True
    api_version = get_rest_api_version(blade)
    if not module.check_mode:
        if not module.params["target_bucket"]:
            module.params["target_bucket"] = module.params["name"]
        else:
            module.params["target_bucket"] = module.params["target_bucket"].lower()
        new_rl = BucketReplicaLinkPost(
            cascading_enabled=module.params["cascading"],
            paused=module.params["paused"],
        )
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            res = blade.post_bucket_replica_links(
                local_bucket_names=[module.params["name"]],
                remote_bucket_names=[module.params["target_bucket"]],
                remote_credentials_names=[remote_cred.name],
                bucket_replica_link=new_rl,
                context_names=[module.params["context"]],
            )
        else:
            res = blade.post_bucket_replica_links(
                local_bucket_names=[module.params["name"]],
                remote_bucket_names=[module.params["target_bucket"]],
                remote_credentials_names=[remote_cred.name],
                bucket_replica_link=new_rl,
            )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to create bucket replica link {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def update_rl_policy(module, blade, local_replica_link):
    """Update Bucket Replica Link"""
    api_version = get_rest_api_version(blade)
    changed = False
    new_cred = local_replica_link.remote.name + "/" + module.params["credential"]
    if local_replica_link.paused != module.params["paused"]:
        paused = module.params["paused"]
        changed = True
    else:
        paused = local_replica_link.paused
    if not _same_name(local_replica_link.remote_credentials.name, new_cred):
        new_rl_cred = new_cred
        changed = True
    else:
        new_rl_cred = local_replica_link.remote_credentials.name
    if local_replica_link.cascading_enabled != module.params["cascading"]:
        cascading = module.params["cascading"]
        changed = True
    else:
        cascading = local_replica_link.cascading_enabled
    if not module.check_mode and changed:
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            res = blade.patch_bucket_replica_links(
                local_bucket_names=[module.params["name"]],
                remote_bucket_names=[local_replica_link.remote_bucket.name],
                remote_names=[local_replica_link.remote.name],
                bucket_replica_link=BucketReplicaLink(
                    paused=paused,
                    remote_credentials=ReferenceWritable(name=new_rl_cred),
                    cascading_enabled=cascading,
                ),
                context_names=[module.params["context"]],
            )
        else:
            res = blade.patch_bucket_replica_links(
                local_bucket_names=[module.params["name"]],
                remote_bucket_names=[local_replica_link.remote_bucket.name],
                remote_names=[local_replica_link.remote.name],
                bucket_replica_link=BucketReplicaLink(
                    paused=paused,
                    remote_credentials=ReferenceWritable(name=new_rl_cred),
                    cascading_enabled=cascading,
                ),
            )
        if res.status_code != 200:
            msg = "Failed to update bucket replica link {0}. Error: {1}".format(
                module.params["name"], get_error_message(res)
            )
            if local_replica_link.status == "unhealthy":
                # The array answers "Unexpected error." when it cannot act on
                # an unhealthy link; the status details say why it is unhealthy.
                msg += " Link is unhealthy: {0}".format(
                    local_replica_link.status_details
                )
            module.fail_json(msg=msg)
    module.exit_json(changed=changed)


def delete_rl_policy(module, blade, local_replica_link):
    """Delete Bucket Replica Link"""
    api_version = get_rest_api_version(blade)
    changed = True
    if not module.check_mode:
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            res = blade.delete_bucket_replica_links(
                remote_names=[local_replica_link.remote.name],
                local_bucket_names=[module.params["name"]],
                remote_bucket_names=[local_replica_link.remote_bucket.name],
                context_names=[module.params["context"]],
            )
        else:
            res = blade.delete_bucket_replica_links(
                remote_names=[local_replica_link.remote.name],
                local_bucket_names=[module.params["name"]],
                remote_bucket_names=[local_replica_link.remote_bucket.name],
            )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete bucket replica link {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def get_unhealthy_blocked_changes(module, local_replica_link):
    """Return the requested changes an unhealthy link cannot accept

    Pausing a link does not need its remote side, so an unhealthy link may
    be paused (it also reports unhealthy for a while after a resume, until
    the first sync completes). Resuming it, or changing its remote credential
    or cascading setting, needs a healthy link.
    """
    blocked = []
    if local_replica_link.paused and not module.params["paused"]:
        blocked.append("resume")
    new_cred = local_replica_link.remote.name + "/" + module.params["credential"]
    if not _same_name(local_replica_link.remote_credentials.name, new_cred):
        blocked.append("credential")
    if local_replica_link.cascading_enabled != module.params["cascading"]:
        blocked.append("cascading")
    return blocked


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str", required=True),
            target=dict(type="str"),
            target_bucket=dict(type="str"),
            paused=dict(type="bool", default=False),
            cascading=dict(type="bool", default=False),
            credential=dict(type="str"),
            state=dict(default="present", choices=["present", "absent"]),
            context=dict(type="str", default=""),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    state = module.params["state"]
    module.params["name"] = module.params["name"].lower()
    if state == "present":
        _check_same_realm(module)
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

    local_replica_link = get_local_rl(module, blade)

    # Removing a replica link only requires the link itself. The local and
    # remote buckets, the target connection and the remote credential may
    # already have been deleted, so none of these are required when deleting.
    if state == "absent":
        if local_replica_link:
            delete_rl_policy(module, blade, local_replica_link)
        module.exit_json(changed=False)

    local_bucket = get_local_bucket(module, blade)

    if module.params["target"]:
        target = get_connected(module, blade)
        if not target:
            module.fail_json(
                msg="Selected target {0} is not connected.".format(
                    module.params["target"]
                )
            )
    elif local_replica_link:
        # An existing link already knows its remote; use it to look up the
        # credential when the caller did not repeat the target.
        target = local_replica_link.remote.name
        module.params["target"] = target
    else:
        module.fail_json(
            msg="target parameter is required when creating a new replica link"
        )

    if local_replica_link and not module.params["credential"]:
        module.params["credential"] = local_replica_link.remote_credentials.name.split(
            "/"
        )[1]
    if not module.params["credential"]:
        module.fail_json(
            msg="credential parameter is required when creating a new replica link"
        )
    remote_cred = get_remote_cred(module, blade, target)
    if not remote_cred:
        module.fail_json(
            msg="Selected remote credential {0} does not exist for target {1}.".format(
                module.params["credential"], module.params["target"]
            )
        )

    if not local_bucket:
        module.fail_json(
            msg="Selected local bucket {0} does not exist.".format(
                module.params["name"]
            )
        )

    if local_replica_link and local_replica_link.status == "unhealthy":
        blocked = get_unhealthy_blocked_changes(module, local_replica_link)
        if blocked:
            module.fail_json(
                msg="Replica Link unhealthy - please check target. "
                "An unhealthy link can only be paused or deleted; "
                "refused change(s): {0}".format(", ".join(blocked))
            )

    if not local_replica_link:
        create_rl(module, blade, remote_cred)
    else:
        update_rl_policy(module, blade, local_replica_link)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
