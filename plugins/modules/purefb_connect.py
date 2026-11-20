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
module: purefb_connect
version_added: '1.0.0'
short_description: Manage replication connections between two FlashBlades
description:
- Manage replication connections to specified remote FlashBlade system
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  state:
    description:
    - Create or delete replication connection
    default: present
    type: str
    choices: [ absent, present ]
  encrypted:
    description:
    - Define if replication connection is encrypted
    type: bool
    default: false
  target_url:
    description:
    - Management IP address of target FlashBlade system
    type: str
    required: true
  target_api:
    description:
    - API token for target FlashBlade system
    - Creating a connection creates a connection key on the target FlashBlade
      with this token. No connection key is created in check mode.
    type: str
  target_repl:
    description:
    - Replication IP address of target FlashBlade system
    - If not set at time of connection creation, will default to
      all the replication addresses available on the target array
      at the time of connection creation.
    type: list
    elements: str
    version_added: "1.9.0"
  default_limit:
    description:
    - Default maximum bandwidth threshold for outbound traffic in bytes.
    - B, K, M, or G units. See examples.
    - Must be 0 or between 5MB and 28GB
    - Once exceeded, bandwidth throttling occurs
    type: str
    version_added: "1.9.0"
  window_limit:
    description:
    - Maximum bandwidth threshold for outbound traffic during the specified
      time range in bytes.
    - B, K, M, or G units. See examples.
    - Must be 0 or between 5MB and 28GB
    - Once exceeded, bandwidth throttling occurs
    type: str
    version_added: "1.9.0"
  window_start:
    description:
    - The window start time.
    - The time must be set to the hour.
    type: str
    version_added: "1.9.0"
  window_end:
    description:
    - The window end time.
    - The time must be set to the hour.
    type: str
    version_added: "1.9.0"
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
- name: Create a connection to remote FlashBlade system
  everpure.flashblade.purefb_connect:
    target_url: 10.10.10.20
    target_api: T-b3275b1c-8958-4190-9052-eb46b0bd09f8
    fb_url: 10.10.10.2
    api_token: T-91528421-fe42-47ee-bcb1-47eefb0a9220
- name: Create a connection to remote FlashBlade system with bandwidth limits
  everpure.flashblade.purefb_connect:
    target_url: 10.10.10.20
    target_api: T-b3275b1c-8958-4190-9052-eb46b0bd09f8
    window_limit: 28G
    window_start: 1AM
    window_end: 7AM
    default_limit: 5M
    fb_url: 10.10.10.2
    api_token: T-91528421-fe42-47ee-bcb1-47eefb0a9220
- name: Delete connection to target FlashBlade system
  everpure.flashblade.purefb_connect:
    state: absent
    target_url: 10.10.10.20
    target_api: T-b3275b1c-8958-4190-9052-eb46b0bd09f8
    fb_url: 10.10.10.2
    api_token: T-91528421-fe42-47ee-bcb1-47eefb0a9220
"""

RETURN = r"""
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        Client,
        ArrayConnectionPost,
        TimeWindow,
        Throttle,
    )
except ImportError:
    HAS_PYPURECLIENT = False

from ansible.module_utils.basic import AnsibleModule, human_to_bytes
from ansible_collections.everpure.flashblade.plugins.module_utils.purefb import (
    get_system,
    purefb_argument_spec,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.time_utils import (
    time_to_milliseconds,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.version import (
    LooseVersion,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.common import (
    get_error_message,
    get_rest_api_version,
)

CONTEXT_API_VERSION = "2.17"
FAN_IN_MAXIMUM = 5
FAN_OUT_MAXIMUM = 5


def _checked(module, res, what):
    """Return a response that answered 200, or fail with the answer of the array"""
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read {0}. Error: {1}".format(what, get_error_message(res))
        )
    return res


def _remote_client(module):
    """Return a client for the array at I(target_url)"""
    try:
        remote_system = Client(
            target=module.params["target_url"], api_token=module.params["target_api"]
        )
    except Exception as exc:
        module.fail_json(
            msg="Failed to connect to remote array {0}. Error: {1}".format(
                module.params["target_url"], exc
            )
        )
    return remote_system


def _remote_array_name(module, remote_system):
    """Return the name of the array at I(target_url)"""
    res = _checked(
        module,
        remote_system.get_arrays(),
        "the array name from {0}".format(module.params["target_url"]),
    )
    return list(res.items)[0].name


def _connection_key(module, remote_system, remote_array):
    """Create a connection key on the remote array and return it"""
    res = remote_system.post_array_connections_connection_key()
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to create a connection key on remote array {0}. "
            "Error: {1}".format(remote_array, get_error_message(res))
        )
    return list(res.items)[0].connection_key


def _check_connected(module, blade):
    api_version = get_rest_api_version(blade)
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and module.params["context"]
    ):
        res = blade.get_array_connections(context_names=[module.params["context"]])
    else:
        res = blade.get_array_connections()
    connected_blades = list(_checked(module, res, "the array connections").items)
    for target in connected_blades:
        if target.management_address is None:
            remote_array = _remote_array_name(module, _remote_client(module))
            if target.remote.name == remote_array:
                return target
        if target.management_address == module.params[
            "target_url"
        ] and target.status in [
            "connected",
            "connecting",
            "partially_connected",
        ]:
            return target
    return None


def break_connection(module, blade, target_blade):
    """Break connection between arrays"""
    api_version = get_rest_api_version(blade)
    changed = True
    if target_blade.management_address is None:
        module.fail_json(
            msg="Disconnect can only happen from the array that formed the connection"
        )
    if not module.check_mode:
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            res = blade.get_arrays(context_names=[module.params["context"]])
        else:
            res = blade.get_arrays()
        source_blade = list(_checked(module, res, "the array name").items)[0].name
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            res = blade.delete_array_connections(
                remote_names=[target_blade.remote.name],
                context_names=[module.params["context"]],
            )
        else:
            res = blade.delete_array_connections(
                remote_names=[target_blade.remote.name]
            )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to disconnect {0} from {1}. Error: {2}".format(
                    target_blade.remote.name, source_blade, get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def create_connection(module, blade):
    """Create connection between REST 2 capable arrays"""
    api_version = get_rest_api_version(blade)
    changed = True
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and module.params["context"]
    ):
        res = blade.get_array_connections(context_names=[module.params["context"]])
    else:
        res = blade.get_array_connections()
    res = _checked(module, res, "the array connections")
    if res.total_item_count >= FAN_OUT_MAXIMUM:
        module.fail_json(
            msg="FlashBlade fan-out maximum of {0} already reached".format(
                FAN_OUT_MAXIMUM
            )
        )
    remote_system = _remote_client(module)
    remote_array = _remote_array_name(module, remote_system)
    remote_conn_cnt = _checked(
        module,
        remote_system.get_array_connections(),
        "the array connections of remote array {0}".format(remote_array),
    ).total_item_count
    if remote_conn_cnt >= FAN_IN_MAXIMUM:
        module.fail_json(
            msg="Remote array {0} already connected to {1} other array. Fan-In not supported".format(
                remote_array, remote_conn_cnt
            )
        )

    throttle = None
    if module.params["default_limit"] or module.params["window_limit"]:
        if module.params["window_limit"]:
            if not module.params["window_start"]:
                module.params["window_start"] = "12AM"
            if not module.params["window_end"]:
                module.params["window_end"] = "12AM"
            window = TimeWindow(
                start=time_to_milliseconds(module.params["window_start"]),
                end=time_to_milliseconds(module.params["window_end"]),
            )
        if module.params["window_limit"] and module.params["default_limit"]:
            throttle = Throttle(
                default_limit=human_to_bytes(module.params["default_limit"]),
                window_limit=human_to_bytes(module.params["window_limit"]),
                window=window,
            )
        elif module.params["window_limit"] and not module.params["default_limit"]:
            throttle = Throttle(
                window_limit=human_to_bytes(module.params["window_limit"]),
                window=window,
            )
        else:
            throttle = Throttle(
                default_limit=human_to_bytes(module.params["default_limit"]),
            )
    if not module.check_mode:
        # The connection key is created on the remote array, so it is
        # requested only when the connection is about to be made
        connection = dict(
            management_address=module.params["target_url"],
            replication_addresses=module.params["target_repl"],
            encrypted=module.params["encrypted"],
            connection_key=_connection_key(module, remote_system, remote_array),
        )
        if throttle is not None:
            connection["throttle"] = throttle
        connection_info = ArrayConnectionPost(**connection)
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            res = blade.post_array_connections(
                array_connection=connection_info,
                context_names=[module.params["context"]],
            )
        else:
            res = blade.post_array_connections(array_connection=connection_info)
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to connect to remote array {0}. Error: {1}".format(
                    remote_array, get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def update_connection(module, blade):
    """Update REST 2 based array connection"""
    changed = False
    api_version = get_rest_api_version(blade)
    remote_name = _remote_array_name(module, _remote_client(module))
    connections = list(
        _checked(
            module,
            blade.get_array_connections(filter="remote.name='" + remote_name + "'"),
            "the array connections",
        ).items
    )
    if not connections:
        module.fail_json(
            msg="No connection to remote array {0} found".format(remote_name)
        )
    remote_connection = connections[0]
    if remote_connection.management_address is None:
        module.fail_json(
            msg="Update can only happen from the array that formed the connection"
        )
    if module.params["encrypted"] != remote_connection.encrypted:
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            res = blade.get_file_system_replica_links(
                context_names=[module.params["context"]]
            )
        else:
            res = blade.get_file_system_replica_links()
        if module.params["encrypted"]:
            res = _checked(module, res, "the file system replica links")
            if res.total_item_count != 0:
                module.fail_json(
                    msg="Cannot turn array connection encryption on if file system replica links exist"
                )
    current_connection = {
        "encrypted": remote_connection.encrypted,
        "replication_addresses": sorted(remote_connection.replication_addresses),
        "throttle": [],
    }
    if (
        not remote_connection.throttle.default_limit
        and not remote_connection.throttle.window_limit
    ):
        if (
            LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
            and module.params["context"]
        ):
            res = blade.get_bucket_replica_links(
                context_names=[module.params["context"]]
            )
        else:
            res = blade.get_bucket_replica_links()
        if module.params["default_limit"] or module.params["window_limit"]:
            res = _checked(module, res, "the bucket replica links")
            if res.total_item_count != 0:
                module.fail_json(
                    msg="Cannot set throttle when bucket replica links already exist"
                )
    current_connection["throttle"] = {
        "default_limit": remote_connection.throttle.default_limit,
        "window_limit": remote_connection.throttle.window_limit,
        "start": remote_connection.throttle.window.start,
        "end": remote_connection.throttle.window.end,
    }
    if module.params["encrypted"]:
        encryption = module.params["encrypted"]
    else:
        encryption = remote_connection.encrypted
    if module.params["target_repl"]:
        target_repl = sorted(module.params["target_repl"])
    else:
        target_repl = remote_connection.replication_addresses
    if module.params["default_limit"]:
        default_limit = human_to_bytes(module.params["default_limit"])
        if default_limit == 0:
            default_limit = None
    else:
        default_limit = remote_connection.throttle.default_limit
    if module.params["window_limit"]:
        window_limit = human_to_bytes(module.params["window_limit"])
    else:
        window_limit = remote_connection.throttle.window_limit
    if module.params["window_start"]:
        start = time_to_milliseconds(module.params["window_start"])
    else:
        start = remote_connection.throttle.window.start
    if module.params["window_end"]:
        end = time_to_milliseconds(module.params["window_end"])
    else:
        end = remote_connection.throttle.window.end

    new_connection = {
        "encrypted": encryption,
        "replication_addresses": target_repl,
        "throttle": [],
    }
    new_connection["throttle"] = {
        "default_limit": default_limit,
        "window_limit": window_limit,
        "start": start,
        "end": end,
    }
    if new_connection != current_connection:
        changed = True
        if not module.check_mode:
            window = TimeWindow(
                start=new_connection["throttle"]["start"],
                end=new_connection["throttle"]["end"],
            )
            throttle = Throttle(
                default_limit=new_connection["throttle"]["default_limit"],
                window_limit=new_connection["throttle"]["window_limit"],
                window=window,
            )
            connection_info = ArrayConnectionPost(
                replication_addresses=new_connection["replication_addresses"],
                encrypted=new_connection["encrypted"],
                throttle=throttle,
            )
            if (
                LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
                and module.params["context"]
            ):
                res = blade.patch_array_connections(
                    remote_names=[remote_name],
                    array_connection=connection_info,
                    context_names=[module.params["context"]],
                )
            else:
                res = blade.patch_array_connections(
                    remote_names=[remote_name], array_connection=connection_info
                )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to update connection to remote array {0}. Error: {1}".format(
                        remote_name, get_error_message(res)
                    )
                )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(type="str", default="present", choices=["absent", "present"]),
            encrypted=dict(type="bool", default=False),
            target_url=dict(type="str", required=True),
            target_api=dict(type="str", no_log=True),
            target_repl=dict(type="list", elements="str"),
            default_limit=dict(type="str"),
            window_limit=dict(type="str"),
            window_start=dict(type="str"),
            window_end=dict(type="str"),
            context=dict(type="str", default=""),
        )
    )

    required_if = [("state", "present", ["target_api"])]

    module = AnsibleModule(
        argument_spec, required_if=required_if, supports_check_mode=True
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    state = module.params["state"]
    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and not module.params["context"]
    ):
        # If no context is provided set the context to the local array name
        fleet_res = blade.get_fleets()
        if fleet_res.status_code == 200 and list(fleet_res.items):
            module.params["context"] = list(
                _checked(module, blade.get_arrays(), "the array name").items
            )[0].name

    if module.params["default_limit"]:
        default_limit = human_to_bytes(module.params["default_limit"])
        if default_limit != 0 and not (5242880 <= default_limit <= 30064771072):
            module.fail_json(msg="Default Bandwidth must be between 5MB and 28GB")
    if module.params["window_limit"]:
        window_limit = human_to_bytes(module.params["window_limit"])
        if window_limit != 0 and not (5242880 <= window_limit <= 30064771072):
            module.fail_json(msg="Window Bandwidth must be between 5MB and 28GB")

    target_blade = _check_connected(module, blade)
    if state == "present" and not target_blade:
        create_connection(module, blade)
    elif state == "present" and target_blade:
        update_connection(module, blade)
    elif state == "absent" and target_blade:
        break_connection(module, blade, target_blade)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
