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
module: purefb_realm_connection
version_added: '1.30.0'
short_description: Manage realm connections between Everpure FlashBlades
description:
- Connect a realm on the local FlashBlade to a realm on a remote FlashBlade,
  disconnect such a pair, and manage the connection keys of a local realm.
- A realm connection is the prerequisite for realm-level replication.
- Requires FlashBlade REST API 2.25 or later (Purity//FB 4.8.0+) on both
  FlashBlades. The two FlashBlades must already be connected with
  M(everpure.flashblade.purefb_connect), which makes the remote realms
  visible to the local FlashBlade.
- Realm connections between two realms on the same FlashBlade are not
  supported, and realm names must be unique across connected FlashBlades.
- A connection is created with a connection key generated on the remote
  FlashBlade for the remote realm. Either provide I(target_url) and
  I(target_api) so the module generates and consumes the key in one task,
  or pass a key obtained out of band (for example from a previous
  I(generate_key) run on the remote FlashBlade) in I(connection_key).
- Connection keys expire two hours after creation and are consumed when
  used. Invalidating the keys of a realm removes every outstanding key of
  that realm and does not affect existing connections.
- If the local FlashBlade rejects a key the module generated through
  I(target_url) and I(target_api), that key stays outstanding on the
  remote realm until it expires or I(invalidate_keys) is run on the
  remote FlashBlade.
- A realm connection has no modifiable attributes. An existing pair is
  reported with its status and is never re-created, whatever its status.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  realm:
    description:
    - Name of the realm on the local FlashBlade.
    type: str
    required: true
  remote_realm:
    description:
    - Name of the realm on the remote FlashBlade to connect I(realm) to.
    - Required unless I(generate_key) or I(invalidate_keys) is set.
    type: str
  state:
    description:
    - Whether the realm connection between I(realm) and I(remote_realm)
      should exist.
    - Not used when I(generate_key) or I(invalidate_keys) is set.
    type: str
    default: present
    choices: [ absent, present ]
  target_url:
    description:
    - Management IP address or hostname of the remote FlashBlade that owns
      I(remote_realm).
    - Used with I(target_api) to generate the connection key on the remote
      FlashBlade when creating a connection.
    type: str
  target_api:
    description:
    - API token of an administrator on the remote FlashBlade.
    - Mutually exclusive with I(connection_key).
    type: str
  connection_key:
    description:
    - Connection key previously generated for I(remote_realm) on the remote
      FlashBlade, as an alternative to I(target_url) and I(target_api).
    - Keys are single use and expire two hours after they were generated.
    type: str
  generate_key:
    description:
    - Generate a new connection key for the local I(realm) and return it in
      C(key). Another FlashBlade consumes this key to connect one of its
      realms to I(realm).
    - Every run generates a new key, so this operation always reports a
      change. The key is only shown once; register the result with
      C(no_log) on the task.
    type: bool
    default: false
  invalidate_keys:
    description:
    - Invalidate every outstanding connection key of the local I(realm).
    - Existing realm connections are not affected.
    type: bool
    default: false
  wait:
    description:
    - Wait for the realm connection to report C(CONNECTED) before returning.
    - Applies after a connection is created and to an existing connection
      that is not yet C(CONNECTED).
    - Not used when I(generate_key) or I(invalidate_keys) is set.
    type: bool
    default: false
  wait_timeout:
    description:
    - Seconds to wait for C(CONNECTED) when I(wait) is true.
    type: int
    default: 300
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Connect local realm finance to realm finance-dr on the remote FlashBlade
  everpure.flashblade.purefb_realm_connection:
    realm: finance
    remote_realm: finance-dr
    target_url: 10.10.10.20
    target_api: T-7e8b5a5c-3a07-4e75-9a6d-0f7a5f6f2b2c
    wait: true
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Generate a connection key for realm finance-dr (run on the remote FlashBlade)
  everpure.flashblade.purefb_realm_connection:
    realm: finance-dr
    generate_key: true
    fb_url: 10.10.10.20
    api_token: T-7e8b5a5c-3a07-4e75-9a6d-0f7a5f6f2b2c
  register: remote_key
  no_log: true

- name: Connect local realm finance with the key generated above
  everpure.flashblade.purefb_realm_connection:
    realm: finance
    remote_realm: finance-dr
    connection_key: "{{ remote_key.key.connection_key }}"
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
  no_log: true

- name: Invalidate all outstanding connection keys of realm finance-dr
  everpure.flashblade.purefb_realm_connection:
    realm: finance-dr
    invalidate_keys: true
    fb_url: 10.10.10.20
    api_token: T-7e8b5a5c-3a07-4e75-9a6d-0f7a5f6f2b2c

- name: Disconnect realm finance from realm finance-dr
  everpure.flashblade.purefb_realm_connection:
    realm: finance
    remote_realm: finance-dr
    state: absent
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
"""

RETURN = r"""
connection:
  description:
  - The realm connection between I(realm) and I(remote_realm) after the task.
  - C(null) when the connection does not exist.
  returned: when I(remote_realm) is set
  type: dict
  contains:
    local_realm:
      description: Name of the realm on the local FlashBlade.
      type: str
      sample: finance
    remote_realm:
      description: Name of the realm on the remote FlashBlade.
      type: str
      sample: finance-dr
    status:
      description:
      - Connection status, one of C(CONNECTING), C(CONNECTED),
        C(DISCONNECTED) or C(UNREACHABLE).
      type: str
      sample: CONNECTED
key:
  description:
  - The connection key generated for the local I(realm).
  - The key is only shown once and is a secret; register the result with
    C(no_log) on the task.
  - C(null) in check mode.
  returned: when I(generate_key) is true
  type: dict
  contains:
    connection_key:
      description: The connection key.
      type: str
    created:
      description: Creation time in milliseconds since the UNIX epoch.
      type: int
      sample: 1735689600000
    expires:
      description: Expiry time in milliseconds since the UNIX epoch.
      type: int
      sample: 1735696800000
    realm:
      description: Name of the realm the key was generated for.
      type: str
      sample: finance-dr
keys_invalidated:
  description: Number of outstanding connection keys that were invalidated.
  returned: when I(invalidate_keys) is true
  type: int
  sample: 1
"""

import platform
import time

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
    from pypureclient.flashblade import Client, RealmConnectionPost
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

VERSION = "1.5"
USER_AGENT_BASE = "Ansible"
MIN_REQUIRED_API_VERSION = "2.25"
WAIT_INTERVAL = 5


def _user_agent():
    if HAS_DISTRO:
        platform_name = distro.name(pretty=True)
    else:
        platform_name = platform.platform()
    return "%(base)s %(class)s/%(version)s (%(platform)s)" % {
        "base": USER_AGENT_BASE,
        "class": __name__,
        "version": VERSION,
        "platform": platform_name,
    }


def _realm_exists(module, blade):
    """Return True if the local realm exists and is not destroyed."""
    res = blade.get_realms(destroyed=False, names=[module.params["realm"]])
    return res.status_code == 200


def _connection_filter(module):
    return "local_realm.name='{0}' and remote_realm.name='{1}'".format(
        module.params["realm"], module.params["remote_realm"]
    )


def get_connection(module, blade):
    """Return the realm connection for the local/remote pair, or None."""
    res = blade.get_realm_connections(filter=_connection_filter(module))
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read realm connections. Error: {0}".format(
                get_error_message(res)
            )
        )
    items = list(res.items)
    if items:
        return items[0]
    return None


def connection_to_dict(connection):
    if connection is None:
        return None
    return {
        "local_realm": getattr(getattr(connection, "local_realm", None), "name", None),
        "remote_realm": getattr(
            getattr(connection, "remote_realm", None), "name", None
        ),
        "status": getattr(connection, "status", None),
    }


def _check_remote_realm_visible(module, blade):
    """Fail unless the remote realm is visible from the local FlashBlade."""
    res = blade.get_remote_realms(names=[module.params["remote_realm"]])
    if res.status_code != 200 or not list(res.items):
        module.fail_json(
            msg=(
                "Remote realm {0} is not visible from this FlashBlade; "
                "connect the arrays first with purefb_connect. Error: {1}"
            ).format(module.params["remote_realm"], get_error_message(res))
        )


def _remote_client(module):
    """Return a client for the remote FlashBlade after checking its REST version."""
    if HAS_URLLIB3 and module.params["disable_warnings"]:
        urllib3.disable_warnings()
    try:
        remote_system = Client(
            target=module.params["target_url"],
            api_token=module.params["target_api"],
            user_agent=_user_agent(),
        )
    except Exception:
        module.fail_json(
            msg="Failed to connect to remote FlashBlade {0}.".format(
                module.params["target_url"]
            )
        )
    remote_version = get_rest_api_version(remote_system)
    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(remote_version):
        module.fail_json(
            msg=(
                "Remote FlashBlade {0} does not support realm connections. "
                "Purity//FB 4.8.0, or higher, is required."
            ).format(module.params["target_url"])
        )
    return remote_system


def _remote_connection_key(module, remote_system):
    """Generate a connection key for the remote realm on the remote FlashBlade."""
    res = remote_system.post_realm_connections_connection_key(
        realm_names=[module.params["remote_realm"]]
    )
    if res.status_code != 200:
        module.fail_json(
            msg=(
                "Failed to generate a connection key for remote realm {0} "
                "on {1}. Error: {2}"
            ).format(
                module.params["remote_realm"],
                module.params["target_url"],
                get_error_message(res),
            )
        )
    return list(res.items)[0].connection_key


def wait_for_connected(module, blade, changed):
    """Poll the connection until it reports CONNECTED or the timeout expires."""
    deadline = time.time() + module.params["wait_timeout"]
    while True:
        connection = get_connection(module, blade)
        status = getattr(connection, "status", None) if connection else None
        if status == "CONNECTED":
            return connection
        if time.time() >= deadline:
            module.fail_json(
                msg=(
                    "Realm connection {0} to {1} did not reach CONNECTED "
                    "within {2} seconds. Last status: {3}"
                ).format(
                    module.params["realm"],
                    module.params["remote_realm"],
                    module.params["wait_timeout"],
                    status,
                ),
                changed=changed,
                connection=connection_to_dict(connection),
            )
        time.sleep(WAIT_INTERVAL)


def create_connection(module, blade):
    """Connect the local realm to the remote realm."""
    if not module.params["target_api"] and not module.params["connection_key"]:
        module.fail_json(
            msg=(
                "Either target_url and target_api, or connection_key, is "
                "required to create a realm connection"
            )
        )
    _check_remote_realm_visible(module, blade)
    changed = True
    connection = None
    remote_system = None
    if module.params["target_api"]:
        remote_system = _remote_client(module)
    if not module.check_mode:
        if module.params["connection_key"]:
            connection_key = module.params["connection_key"]
        else:
            connection_key = _remote_connection_key(module, remote_system)
        res = blade.post_realm_connections(
            realm_connection_post=RealmConnectionPost(connection_key=connection_key),
            local_realm_names=[module.params["realm"]],
            remote_realm_names=[module.params["remote_realm"]],
        )
        if res.status_code != 200:
            msg = "Failed to connect realm {0} to remote realm {1}. Error: {2}".format(
                module.params["realm"],
                module.params["remote_realm"],
                get_error_message(res),
            )
            if remote_system is not None:
                msg += (
                    " The connection key generated for remote realm {0} on {1} "
                    "remains outstanding there until it expires or is "
                    "invalidated with invalidate_keys."
                ).format(module.params["remote_realm"], module.params["target_url"])
            module.fail_json(msg=msg)
        items = list(res.items) if getattr(res, "items", None) is not None else []
        connection = items[0] if items else None
        if module.params["wait"]:
            connection = wait_for_connected(module, blade, changed)
    module.exit_json(changed=changed, connection=connection_to_dict(connection))


def delete_connection(module, blade):
    """Disconnect the local realm from the remote realm."""
    changed = True
    if not module.check_mode:
        res = blade.delete_realm_connections(
            local_realm_names=[module.params["realm"]],
            remote_realm_names=[module.params["remote_realm"]],
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to disconnect realm {0} from remote realm {1}. Error: {2}".format(
                    module.params["realm"],
                    module.params["remote_realm"],
                    get_error_message(res),
                )
            )
    module.exit_json(changed=changed, connection=None)


def generate_key(module, blade):
    """Generate a connection key for the local realm. Always a change."""
    changed = True
    key_info = None
    if not module.check_mode:
        res = blade.post_realm_connections_connection_key(
            realm_names=[module.params["realm"]]
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to generate a connection key for realm {0}. Error: {1}".format(
                    module.params["realm"], get_error_message(res)
                )
            )
        key = list(res.items)[0]
        key_info = {
            "connection_key": getattr(key, "connection_key", None),
            "created": getattr(key, "created", None),
            "expires": getattr(key, "expires", None),
            "realm": module.params["realm"],
        }
    module.exit_json(changed=changed, key=key_info)


def invalidate_keys(module, blade):
    """Invalidate every outstanding connection key of the local realm."""
    res = blade.get_realm_connections_connection_key(
        realm_names=[module.params["realm"]]
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to list connection keys for realm {0}. Error: {1}".format(
                module.params["realm"], get_error_message(res)
            )
        )
    outstanding = len(list(res.items))
    if outstanding == 0:
        module.exit_json(changed=False, keys_invalidated=0)
    changed = True
    if not module.check_mode:
        res = blade.delete_realm_connections_connection_key(
            realm_names=[module.params["realm"]]
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to invalidate connection keys for realm {0}. Error: {1}".format(
                    module.params["realm"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed, keys_invalidated=outstanding)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            realm=dict(type="str", required=True),
            remote_realm=dict(type="str"),
            state=dict(type="str", default="present", choices=["absent", "present"]),
            target_url=dict(type="str"),
            target_api=dict(type="str", no_log=True),
            connection_key=dict(type="str", no_log=True),
            generate_key=dict(type="bool", default=False),
            invalidate_keys=dict(type="bool", default=False),
            wait=dict(type="bool", default=False),
            wait_timeout=dict(type="int", default=300),
        )
    )

    module = AnsibleModule(
        argument_spec,
        mutually_exclusive=[
            ["generate_key", "invalidate_keys"],
            ["target_api", "connection_key"],
        ],
        required_together=[["target_url", "target_api"]],
        supports_check_mode=True,
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    key_operation = module.params["generate_key"] or module.params["invalidate_keys"]
    if key_operation and (
        module.params["remote_realm"]
        or module.params["target_url"]
        or module.params["connection_key"]
    ):
        module.fail_json(
            msg=(
                "generate_key and invalidate_keys act on the local realm only "
                "and cannot be combined with remote_realm, target_url, "
                "target_api or connection_key"
            )
        )
    if not key_operation and not module.params["remote_realm"]:
        module.fail_json(msg="remote_realm is required to manage a realm connection")

    state = module.params["state"]
    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg=(
                "Realm connections are not supported. "
                "Purity//FB 4.8.0, or higher, is required."
            )
        )

    if not _realm_exists(module, blade):
        if state == "absent" and not key_operation:
            module.exit_json(changed=False, connection=None)
        module.fail_json(msg="Realm {0} does not exist.".format(module.params["realm"]))

    if module.params["generate_key"]:
        generate_key(module, blade)
    if module.params["invalidate_keys"]:
        invalidate_keys(module, blade)

    connection = get_connection(module, blade)
    if state == "present":
        if connection:
            if module.params["wait"] and getattr(connection, "status", None) != (
                "CONNECTED"
            ):
                connection = wait_for_connected(module, blade, False)
            module.exit_json(changed=False, connection=connection_to_dict(connection))
        create_connection(module, blade)
    elif state == "absent" and connection:
        delete_connection(module, blade)

    module.exit_json(changed=False, connection=None)


if __name__ == "__main__":
    main()
