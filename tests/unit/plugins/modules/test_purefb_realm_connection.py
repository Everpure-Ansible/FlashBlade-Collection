# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_realm_connection module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from contextlib import ExitStack, contextmanager
from unittest.mock import ANY, Mock, patch, MagicMock

# Mock multiprocessing context for Windows
if sys.platform == "win32":
    original_get_context = multiprocessing.get_context

    def mock_get_context(method=None):
        if method == "fork":
            return original_get_context("spawn")
        return original_get_context(method)

    multiprocessing.get_context = mock_get_context

    # Mock ctypes LoadLibrary to prevent Windows errors
    original_load_library = ctypes.cdll.LoadLibrary

    def mock_load_library(name):
        if name is None or not isinstance(name, str):
            return MagicMock()
        try:
            return original_load_library(name)
        except (OSError, TypeError):
            return MagicMock()

    ctypes.cdll.LoadLibrary = mock_load_library

# Mock external dependencies before importing module
sys.modules["pypureclient"] = MagicMock()
sys.modules["pypureclient.flashblade"] = MagicMock()
sys.modules["urllib3"] = MagicMock()
sys.modules["distro"] = MagicMock()
# Mock Unix-specific modules for Windows compatibility
sys.modules["grp"] = MagicMock()
sys.modules["fcntl"] = MagicMock()
sys.modules["pwd"] = MagicMock()
sys.modules["syslog"] = MagicMock()
# Mock termios with required constants
mock_termios = MagicMock()
mock_termios.TCSAFLUSH = 2
sys.modules["termios"] = mock_termios
sys.modules["tty"] = MagicMock()

# Mock ansible_collections module structure
sys.modules["ansible_collections"] = MagicMock()
sys.modules["ansible_collections.everpure"] = MagicMock()
sys.modules["ansible_collections.everpure.flashblade"] = MagicMock()
sys.modules["ansible_collections.everpure.flashblade.plugins"] = MagicMock()
sys.modules["ansible_collections.everpure.flashblade.plugins.module_utils"] = (
    MagicMock()
)
sys.modules["ansible_collections.everpure.flashblade.plugins.module_utils.purefb"] = (
    MagicMock()
)
sys.modules["ansible_collections.everpure.flashblade.plugins.module_utils.common"] = (
    MagicMock()
)
sys.modules["ansible_collections.everpure.flashblade.plugins.module_utils.version"] = (
    MagicMock()
)

from plugins.modules.purefb_realm_connection import (
    main,
    get_connection,
    connection_to_dict,
)

MODULE = "plugins.modules.purefb_realm_connection"

# Error texts the FlashBlade answers on Purity//FB 4.8.8 (REST 2.30)
REALM_MISSING = "Realm does not exist."
REALM_DESTROYED = "Realm has been destroyed."
REMOTE_REALM_MISSING = "Remote Realm does not exist."
NO_MATCHING_KEY = "Cannot find any connection that matches realm and key"


class _Version:
    """Minimal LooseVersion stand-in so the REST gates compare real numbers."""

    def __init__(self, value):
        self.parts = [int(part) for part in str(value).split(".")]

    def __gt__(self, other):
        return self.parts > other.parts

    def __ge__(self, other):
        return self.parts >= other.parts

    def __lt__(self, other):
        return self.parts < other.parts

    def __le__(self, other):
        return self.parts <= other.parts

    def __eq__(self, other):
        return self.parts == other.parts


def _base_params(**overrides):
    params = {
        "realm": "finance",
        "remote_realm": "finance-dr",
        "state": "present",
        "target_url": None,
        "target_api": None,
        "connection_key": None,
        "generate_key": False,
        "invalidate_keys": False,
        "wait": False,
        "wait_timeout": 300,
        "disable_warnings": False,
    }
    params.update(overrides)
    return params


def _module(check_mode=False, **overrides):
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.params = _base_params(**overrides)
    module.check_mode = check_mode
    return module


def _error_message(response, default="Unknown error"):
    """What module_utils.common.get_error_message returns: the first error text."""
    if hasattr(response, "errors") and response.errors:
        errors = list(response.errors)
        if errors:
            return errors[0].message
    return default


def _response(status_code=200, items=None, error=None):
    if status_code != 200:
        # An ErrorResponse carries errors and has no items attribute
        response = Mock(spec=["status_code", "errors"])
        response.status_code = status_code
        response.errors = [Mock(message=error)] if error else []
        return response
    response = Mock()
    response.status_code = status_code
    response.items = items if items is not None else []
    response.errors = []
    return response


def _connection(status="CONNECTED"):
    connection = Mock()
    connection.local_realm = Mock()
    connection.local_realm.name = "finance"
    connection.remote_realm = Mock()
    connection.remote_realm.name = "finance-dr"
    connection.status = status
    return connection


def _key(secret="secret-key"):
    key = Mock()
    key.connection_key = secret
    key.created = 1735689600000
    key.expires = 1735696800000
    return key


def _array_connection():
    connection = Mock()
    connection.remote = Mock()
    connection.remote.name = "fb-dr"
    connection.status = "connected"
    return connection


def _blade(
    realm_exists=True,
    connections=None,
    remote_realm_visible=True,
    realm_error=REALM_MISSING,
    array_connections=None,
):
    """A FlashBlade as an array administrator sees it, unless told otherwise.

    remote_realm_visible=False and array_connections=[] give what a
    realm-scoped administrator is shown before its realm is connected: GET
    /remote-realms by name answers 400 and GET /array-connections an empty list.
    """
    blade = Mock()
    if realm_exists:
        blade.get_realms.return_value = _response(items=[Mock()])
    else:
        blade.get_realms.return_value = _response(400, error=realm_error)
    blade.get_realm_connections.return_value = _response(items=connections or [])
    if remote_realm_visible:
        blade.get_remote_realms.return_value = _response(items=[Mock()])
    else:
        blade.get_remote_realms.return_value = _response(
            400, error=REMOTE_REALM_MISSING
        )
    if array_connections is None:
        array_connections = [_array_connection()]
    blade.get_array_connections.return_value = _response(items=array_connections)
    return blade


@contextmanager
def _patched_main(module, blade, rest_version="2.30", remote_version=None):
    """Patch the module boundary: AnsibleModule, get_system and the REST gates."""
    if remote_version is None:
        version_kwargs = {"return_value": rest_version}
    else:
        version_kwargs = {"side_effect": [rest_version, remote_version]}
    with ExitStack() as stack:
        stack.enter_context(patch(MODULE + ".HAS_PYPURECLIENT", True))
        stack.enter_context(patch(MODULE + ".LooseVersion", _Version))
        stack.enter_context(patch(MODULE + ".AnsibleModule", return_value=module))
        stack.enter_context(patch(MODULE + ".get_system", return_value=blade))
        stack.enter_context(patch(MODULE + ".get_rest_api_version", **version_kwargs))
        stack.enter_context(
            patch(MODULE + ".get_error_message", side_effect=_error_message)
        )
        yield stack


def _run():
    try:
        main()
    except SystemExit:
        pass


class TestPurefbRealmConnection:
    """Test cases for purefb_realm_connection module"""

    # ---------------- helper-function unit tests ----------------

    def test_connection_to_dict_none(self):
        """connection_to_dict passes None through"""
        assert connection_to_dict(None) is None

    def test_connection_to_dict_reads_names_and_status(self):
        """connection_to_dict flattens the fixed references"""
        assert connection_to_dict(_connection("CONNECTING")) == {
            "local_realm": "finance",
            "remote_realm": "finance-dr",
            "status": "CONNECTING",
        }

    def test_get_connection_uses_pair_filter(self):
        """get_connection filters on both realm names and returns the match"""
        module = _module()
        connection = _connection()
        blade = Mock()
        blade.get_realm_connections.return_value = _response(items=[connection])

        assert get_connection(module, blade) is connection
        blade.get_realm_connections.assert_called_once_with(
            filter="local_realm.name='finance' and remote_realm.name='finance-dr'"
        )

    def test_get_connection_returns_none_when_empty(self):
        """get_connection returns None when the pair is not connected"""
        module = _module()
        blade = Mock()
        blade.get_realm_connections.return_value = _response(items=[])

        assert get_connection(module, blade) is None

    def test_get_connection_fails_on_api_error(self):
        """get_connection surfaces a failed GET"""
        module = _module()
        blade = Mock()
        blade.get_realm_connections.return_value = _response(status_code=400)

        try:
            get_connection(module, blade)
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert (
            "Failed to read realm connections" in module.fail_json.call_args[1]["msg"]
        )

    # ---------------- parameter validation ----------------

    def test_main_requires_sdk(self):
        """main fails when py-pure-client is missing"""
        module = _module()
        with patch(MODULE + ".HAS_PYPURECLIENT", False), patch(
            MODULE + ".AnsibleModule", return_value=module
        ):
            _run()

        assert "py-pure-client sdk is required" in module.fail_json.call_args[1]["msg"]

    def test_main_key_operation_rejects_remote_realm(self):
        """generate_key cannot be combined with remote_realm"""
        module = _module(generate_key=True)
        blade = _blade()
        with _patched_main(module, blade) as stack:
            mock_get_system = stack.enter_context(patch(MODULE + ".get_system"))
            _run()

        mock_get_system.assert_not_called()
        assert "local realm only" in module.fail_json.call_args[1]["msg"]

    def test_main_connection_requires_remote_realm(self):
        """Managing a connection without remote_realm fails before any API call"""
        module = _module(remote_realm=None)
        blade = _blade()
        with _patched_main(module, blade) as stack:
            mock_get_system = stack.enter_context(patch(MODULE + ".get_system"))
            _run()

        mock_get_system.assert_not_called()
        assert "remote_realm is required" in module.fail_json.call_args[1]["msg"]

    def test_main_api_version_too_old(self):
        """The local REST gate fails below 2.25 before any read or write"""
        module = _module()
        blade = _blade()
        with _patched_main(module, blade, rest_version="2.24"):
            _run()

        module.fail_json.assert_called_once()
        assert "Purity//FB 4.8.0" in module.fail_json.call_args[1]["msg"]
        blade.get_realms.assert_not_called()
        blade.get_realm_connections.assert_not_called()

    def test_main_missing_realm_fails_for_present(self):
        """A missing local realm fails state=present"""
        module = _module()
        blade = _blade(realm_exists=False)
        with _patched_main(module, blade):
            _run()

        blade.get_realms.assert_called_once_with(destroyed=False, names=["finance"])
        assert module.fail_json.call_args[1]["msg"] == (
            "Realm finance is not available. Error: Realm does not exist."
        )
        blade.get_realm_connections.assert_not_called()

    def test_main_missing_realm_is_noop_for_absent(self):
        """A missing local realm means no connection, so state=absent is a no-op"""
        module = _module(state="absent")
        blade = _blade(realm_exists=False)
        with _patched_main(module, blade):
            _run()

        module.exit_json.assert_called_once_with(changed=False, connection=None)
        blade.delete_realm_connections.assert_not_called()

    def test_main_missing_realm_fails_for_generate_key(self):
        """A missing local realm fails a key operation"""
        module = _module(remote_realm=None, generate_key=True)
        blade = _blade(realm_exists=False)
        with _patched_main(module, blade):
            _run()

        assert module.fail_json.call_args[1]["msg"] == (
            "Realm finance is not available. Error: Realm does not exist."
        )
        blade.post_realm_connections_connection_key.assert_not_called()

    # ---------------- generate_key ----------------

    def test_main_generate_key(self):
        """generate_key POSTs a key for the local realm and returns it once"""
        module = _module(remote_realm=None, generate_key=True)
        blade = _blade()
        blade.post_realm_connections_connection_key.return_value = _response(
            items=[_key()]
        )
        with _patched_main(module, blade):
            _run()

        blade.post_realm_connections_connection_key.assert_called_once_with(
            realm_names=["finance"]
        )
        module.exit_json.assert_called_once_with(
            changed=True,
            key={
                "connection_key": "secret-key",
                "created": 1735689600000,
                "expires": 1735696800000,
                "realm": "finance",
            },
        )

    def test_main_generate_key_check_mode(self):
        """generate_key in check mode reports a change without generating a key"""
        module = _module(check_mode=True, remote_realm=None, generate_key=True)
        blade = _blade()
        with _patched_main(module, blade):
            _run()

        blade.post_realm_connections_connection_key.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True, key=None)

    def test_main_generate_key_api_error(self):
        """generate_key surfaces a failed POST"""
        module = _module(remote_realm=None, generate_key=True)
        blade = _blade()
        blade.post_realm_connections_connection_key.return_value = _response(
            status_code=400
        )
        with _patched_main(module, blade):
            _run()

        assert (
            "Failed to generate a connection key for realm finance"
            in module.fail_json.call_args[1]["msg"]
        )

    # ---------------- invalidate_keys ----------------

    def test_main_invalidate_keys(self):
        """invalidate_keys DELETEs when keys are outstanding"""
        module = _module(remote_realm=None, invalidate_keys=True)
        blade = _blade()
        blade.get_realm_connections_connection_key.return_value = _response(
            items=[_key("a"), _key("b")]
        )
        blade.delete_realm_connections_connection_key.return_value = _response()
        with _patched_main(module, blade):
            _run()

        blade.get_realm_connections_connection_key.assert_called_once_with(
            realm_names=["finance"]
        )
        blade.delete_realm_connections_connection_key.assert_called_once_with(
            realm_names=["finance"]
        )
        module.exit_json.assert_called_once_with(changed=True, keys_invalidated=2)

    def test_main_invalidate_keys_none_outstanding(self):
        """invalidate_keys is a no-op when the realm has no keys"""
        module = _module(remote_realm=None, invalidate_keys=True)
        blade = _blade()
        blade.get_realm_connections_connection_key.return_value = _response(items=[])
        with _patched_main(module, blade):
            _run()

        blade.delete_realm_connections_connection_key.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False, keys_invalidated=0)

    def test_main_invalidate_keys_check_mode(self):
        """invalidate_keys in check mode reports the change without a DELETE"""
        module = _module(check_mode=True, remote_realm=None, invalidate_keys=True)
        blade = _blade()
        blade.get_realm_connections_connection_key.return_value = _response(
            items=[_key()]
        )
        with _patched_main(module, blade):
            _run()

        blade.delete_realm_connections_connection_key.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True, keys_invalidated=1)

    def test_main_invalidate_keys_list_error(self):
        """invalidate_keys surfaces a failed key listing"""
        module = _module(remote_realm=None, invalidate_keys=True)
        blade = _blade()
        blade.get_realm_connections_connection_key.return_value = _response(
            status_code=400
        )
        with _patched_main(module, blade):
            _run()

        blade.delete_realm_connections_connection_key.assert_not_called()
        assert (
            "Failed to list connection keys for realm finance"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_main_invalidate_keys_delete_error(self):
        """invalidate_keys surfaces a failed DELETE"""
        module = _module(remote_realm=None, invalidate_keys=True)
        blade = _blade()
        blade.get_realm_connections_connection_key.return_value = _response(
            items=[_key()]
        )
        blade.delete_realm_connections_connection_key.return_value = _response(
            status_code=400
        )
        with _patched_main(module, blade):
            _run()

        assert (
            "Failed to invalidate connection keys for realm finance"
            in module.fail_json.call_args[1]["msg"]
        )

    # ---------------- state=present ----------------

    def test_main_create_with_target_api(self):
        """Create generates the key on the remote and consumes it locally"""
        module = _module(target_url="10.0.0.2", target_api="T-remote")
        blade = _blade()
        blade.post_realm_connections.return_value = _response(
            items=[_connection("CONNECTING")]
        )
        remote = Mock()
        remote.post_realm_connections_connection_key.return_value = _response(
            items=[_key("remote-key")]
        )
        with _patched_main(module, blade, remote_version="2.25") as stack:
            mock_client = stack.enter_context(
                patch(MODULE + ".Client", return_value=remote)
            )
            mock_post = stack.enter_context(patch(MODULE + ".RealmConnectionPost"))
            _run()

        blade.get_remote_realms.assert_not_called()
        blade.get_array_connections.assert_not_called()
        module.warn.assert_not_called()
        mock_client.assert_called_once_with(
            target="10.0.0.2", api_token="T-remote", user_agent=ANY
        )
        remote.post_realm_connections_connection_key.assert_called_once_with(
            realm_names=["finance-dr"]
        )
        mock_post.assert_called_once_with(connection_key="remote-key")
        blade.post_realm_connections.assert_called_once_with(
            realm_connection_post=mock_post.return_value,
            local_realm_names=["finance"],
            remote_realm_names=["finance-dr"],
        )
        module.exit_json.assert_called_once_with(
            changed=True,
            connection={
                "local_realm": "finance",
                "remote_realm": "finance-dr",
                "status": "CONNECTING",
            },
        )

    def test_main_create_with_connection_key(self):
        """Create with an out-of-band key never contacts a remote FlashBlade"""
        module = _module(connection_key="oob-key")
        blade = _blade()
        blade.post_realm_connections.return_value = _response(items=[_connection()])
        with _patched_main(module, blade) as stack:
            mock_client = stack.enter_context(patch(MODULE + ".Client"))
            mock_post = stack.enter_context(patch(MODULE + ".RealmConnectionPost"))
            _run()

        mock_client.assert_not_called()
        mock_post.assert_called_once_with(connection_key="oob-key")
        blade.post_realm_connections.assert_called_once()
        blade.get_remote_realms.assert_not_called()
        blade.get_array_connections.assert_not_called()
        module.warn.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True
        assert module.exit_json.call_args[1]["connection"]["status"] == "CONNECTED"

    def test_main_create_check_mode_generates_no_key(self):
        """Check mode validates the remote but generates and consumes nothing"""
        module = _module(check_mode=True, target_url="10.0.0.2", target_api="T-remote")
        blade = _blade()
        remote = Mock()
        with _patched_main(module, blade, remote_version="2.30") as stack:
            mock_client = stack.enter_context(
                patch(MODULE + ".Client", return_value=remote)
            )
            _run()

        mock_client.assert_called_once()
        remote.post_realm_connections_connection_key.assert_not_called()
        blade.post_realm_connections.assert_not_called()
        blade.get_remote_realms.assert_called_once_with(names=["finance-dr"])
        module.warn.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True, connection=None)

    def test_main_create_without_key_source_fails(self):
        """Create needs either target_api or connection_key"""
        module = _module()
        blade = _blade()
        with _patched_main(module, blade):
            _run()

        blade.get_remote_realms.assert_not_called()
        blade.post_realm_connections.assert_not_called()
        assert (
            "Either target_url and target_api, or connection_key"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_main_create_remote_version_too_old(self):
        """Create fails when the remote FlashBlade is below REST 2.25"""
        module = _module(target_url="10.0.0.2", target_api="T-remote")
        blade = _blade()
        remote = Mock()
        with _patched_main(module, blade, remote_version="2.24") as stack:
            stack.enter_context(patch(MODULE + ".Client", return_value=remote))
            _run()

        remote.post_realm_connections_connection_key.assert_not_called()
        blade.post_realm_connections.assert_not_called()
        assert (
            "Remote FlashBlade 10.0.0.2 does not support realm connections"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_main_create_remote_login_failure(self):
        """Create fails cleanly when the remote FlashBlade cannot be reached"""
        module = _module(target_url="10.0.0.2", target_api="T-remote")
        blade = _blade()
        with _patched_main(module, blade) as stack:
            stack.enter_context(
                patch(MODULE + ".Client", side_effect=Exception("unreachable"))
            )
            _run()

        blade.post_realm_connections.assert_not_called()
        assert (
            "Failed to connect to remote FlashBlade 10.0.0.2"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_main_create_remote_key_failure(self):
        """Create surfaces a failed key generation on the remote"""
        module = _module(target_url="10.0.0.2", target_api="T-remote")
        blade = _blade()
        remote = Mock()
        remote.post_realm_connections_connection_key.return_value = _response(
            status_code=400
        )
        with _patched_main(module, blade, remote_version="2.30") as stack:
            stack.enter_context(patch(MODULE + ".Client", return_value=remote))
            _run()

        blade.post_realm_connections.assert_not_called()
        assert (
            "Failed to generate a connection key for remote realm finance-dr"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_main_create_api_error(self):
        """Create surfaces a failed local POST"""
        module = _module(connection_key="oob-key")
        blade = _blade()
        blade.post_realm_connections.return_value = _response(status_code=400)
        with _patched_main(module, blade) as stack:
            stack.enter_context(patch(MODULE + ".RealmConnectionPost"))
            _run()

        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to connect realm finance to remote realm finance-dr" in msg
        assert "remains outstanding" not in msg
        assert "purefb_connect" not in msg

    def test_main_create_api_error_after_remote_key_names_outstanding_key(self):
        """A failed local POST after generating the remote key says the key is left"""
        module = _module(target_url="10.0.0.2", target_api="T-remote")
        blade = _blade()
        blade.post_realm_connections.return_value = _response(status_code=400)
        remote = Mock()
        remote.post_realm_connections_connection_key.return_value = _response(
            items=[_key("remote-key")]
        )
        with _patched_main(module, blade, remote_version="2.25") as stack:
            stack.enter_context(patch(MODULE + ".Client", return_value=remote))
            stack.enter_context(patch(MODULE + ".RealmConnectionPost"))
            _run()

        remote.post_realm_connections_connection_key.assert_called_once_with(
            realm_names=["finance-dr"]
        )
        remote.delete_realm_connections_connection_key.assert_not_called()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to connect realm finance to remote realm finance-dr" in msg
        assert "remote realm finance-dr on 10.0.0.2 remains outstanding" in msg
        assert "invalidate_keys" in msg

    def test_main_create_with_wait(self):
        """Create with wait polls until the connection reports CONNECTED"""
        module = _module(connection_key="oob-key", wait=True)
        blade = _blade()
        blade.get_realm_connections.side_effect = [
            _response(items=[]),
            _response(items=[_connection("CONNECTING")]),
            _response(items=[_connection("CONNECTED")]),
        ]
        blade.post_realm_connections.return_value = _response(
            items=[_connection("CONNECTING")]
        )
        with _patched_main(module, blade) as stack:
            stack.enter_context(patch(MODULE + ".RealmConnectionPost"))
            mock_time = stack.enter_context(patch(MODULE + ".time"))
            mock_time.time.side_effect = [0, 1]
            _run()

        assert blade.get_realm_connections.call_count == 3
        mock_time.sleep.assert_called_once_with(5)
        module.exit_json.assert_called_once_with(
            changed=True,
            connection={
                "local_realm": "finance",
                "remote_realm": "finance-dr",
                "status": "CONNECTED",
            },
        )

    def test_main_create_wait_timeout_fails_with_changed(self):
        """A wait timeout fails but still reports the connection as created"""
        module = _module(connection_key="oob-key", wait=True, wait_timeout=30)
        blade = _blade()
        blade.get_realm_connections.side_effect = [
            _response(items=[]),
            _response(items=[_connection("CONNECTING")]),
        ]
        blade.post_realm_connections.return_value = _response(
            items=[_connection("CONNECTING")]
        )
        with _patched_main(module, blade) as stack:
            stack.enter_context(patch(MODULE + ".RealmConnectionPost"))
            mock_time = stack.enter_context(patch(MODULE + ".time"))
            mock_time.time.side_effect = [0, 1000]
            _run()

        mock_time.sleep.assert_not_called()
        module.fail_json.assert_called_once()
        call_kwargs = module.fail_json.call_args[1]
        assert "did not reach CONNECTED within 30 seconds" in call_kwargs["msg"]
        assert "Last status: CONNECTING" in call_kwargs["msg"]
        assert call_kwargs["changed"] is True
        assert call_kwargs["connection"]["status"] == "CONNECTING"

    def test_main_present_existing_is_noop(self):
        """An existing pair is reported and never re-created, whatever its status"""
        module = _module(connection_key="oob-key")
        blade = _blade(connections=[_connection("DISCONNECTED")])
        with _patched_main(module, blade) as stack:
            mock_client = stack.enter_context(patch(MODULE + ".Client"))
            _run()

        mock_client.assert_not_called()
        blade.get_remote_realms.assert_not_called()
        blade.post_realm_connections.assert_not_called()
        module.exit_json.assert_called_once_with(
            changed=False,
            connection={
                "local_realm": "finance",
                "remote_realm": "finance-dr",
                "status": "DISCONNECTED",
            },
        )

    def test_main_present_existing_with_wait_polls_until_connected(self):
        """wait on an existing CONNECTING pair polls without reporting a change"""
        module = _module(wait=True)
        blade = _blade()
        blade.get_realm_connections.side_effect = [
            _response(items=[_connection("CONNECTING")]),
            _response(items=[_connection("CONNECTED")]),
        ]
        with _patched_main(module, blade) as stack:
            mock_time = stack.enter_context(patch(MODULE + ".time"))
            mock_time.time.side_effect = [0]
            _run()

        blade.post_realm_connections.assert_not_called()
        module.exit_json.assert_called_once_with(
            changed=False,
            connection={
                "local_realm": "finance",
                "remote_realm": "finance-dr",
                "status": "CONNECTED",
            },
        )

    # ---------------- state=absent ----------------

    def test_main_delete(self):
        """state=absent disconnects an existing pair"""
        module = _module(state="absent")
        blade = _blade(connections=[_connection()])
        blade.delete_realm_connections.return_value = _response()
        with _patched_main(module, blade):
            _run()

        blade.delete_realm_connections.assert_called_once_with(
            local_realm_names=["finance"], remote_realm_names=["finance-dr"]
        )
        module.exit_json.assert_called_once_with(changed=True, connection=None)

    def test_main_delete_check_mode(self):
        """state=absent in check mode reports the change without a DELETE"""
        module = _module(check_mode=True, state="absent")
        blade = _blade(connections=[_connection()])
        with _patched_main(module, blade):
            _run()

        blade.delete_realm_connections.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True, connection=None)

    def test_main_delete_absent_is_noop(self):
        """state=absent on a missing pair is a no-op"""
        module = _module(state="absent")
        blade = _blade()
        with _patched_main(module, blade):
            _run()

        blade.delete_realm_connections.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False, connection=None)

    def test_main_delete_api_error(self):
        """state=absent surfaces a failed DELETE"""
        module = _module(state="absent")
        blade = _blade(connections=[_connection()])
        blade.delete_realm_connections.return_value = _response(status_code=400)
        with _patched_main(module, blade):
            _run()

        assert (
            "Failed to disconnect realm finance from remote realm finance-dr"
            in module.fail_json.call_args[1]["msg"]
        )

    # ---------------- remote realm not listed: the FlashBlade decides ----------------

    def test_main_create_unlisted_remote_realm_is_sent_to_the_array(self):
        """A remote realm the user is not shown no longer stops the POST

        The blade answers what a realm-scoped administrator is shown on
        Purity//FB 4.8.8 before its realm is connected: no remote realm and no
        array connection. The successful POST is what the design documents
        describe for the right name and key; it has not been seen on an array.
        """
        module = _module(connection_key="oob-key")
        blade = _blade(remote_realm_visible=False, array_connections=[])
        blade.post_realm_connections.return_value = _response(
            items=[_connection("CONNECTING")]
        )
        with _patched_main(module, blade) as stack:
            mock_post = stack.enter_context(patch(MODULE + ".RealmConnectionPost"))
            _run()

        module.fail_json.assert_not_called()
        module.warn.assert_not_called()
        blade.get_remote_realms.assert_not_called()
        blade.get_array_connections.assert_not_called()
        mock_post.assert_called_once_with(connection_key="oob-key")
        blade.post_realm_connections.assert_called_once_with(
            realm_connection_post=mock_post.return_value,
            local_realm_names=["finance"],
            remote_realm_names=["finance-dr"],
        )
        module.exit_json.assert_called_once_with(
            changed=True,
            connection={
                "local_realm": "finance",
                "remote_realm": "finance-dr",
                "status": "CONNECTING",
            },
        )

    def test_main_create_relays_the_array_refusal(self):
        """The FlashBlade's refusal is reported as it is when arrays are connected"""
        module = _module(connection_key="not-a-key")
        blade = _blade(remote_realm_visible=False)
        blade.post_realm_connections.return_value = _response(
            400, error=NO_MATCHING_KEY
        )
        with _patched_main(module, blade) as stack:
            stack.enter_context(patch(MODULE + ".RealmConnectionPost"))
            _run()

        blade.get_remote_realms.assert_not_called()
        blade.post_realm_connections.assert_called_once()
        blade.get_array_connections.assert_called_once_with()
        module.fail_json.assert_called_once_with(
            msg=(
                "Failed to connect realm finance to remote realm finance-dr. "
                "Error: Cannot find any connection that matches realm and key"
            )
        )

    def test_main_create_refusal_hints_purefb_connect_without_array_connection(self):
        """The purefb_connect hint is added only when no array connection is listed"""
        module = _module(connection_key="not-a-key")
        blade = _blade(remote_realm_visible=False, array_connections=[])
        blade.post_realm_connections.return_value = _response(
            400, error=NO_MATCHING_KEY
        )
        with _patched_main(module, blade) as stack:
            stack.enter_context(patch(MODULE + ".RealmConnectionPost"))
            _run()

        blade.post_realm_connections.assert_called_once()
        module.fail_json.assert_called_once_with(
            msg=(
                "Failed to connect realm finance to remote realm finance-dr. "
                "Error: Cannot find any connection that matches realm and key. "
                "No array connection is visible to this user: if the "
                "FlashBlades are not connected yet, connect them first with "
                "purefb_connect."
            )
        )

    def test_main_create_refusal_without_hint_when_array_connections_unreadable(self):
        """No hint when the user may not list array connections

        The refusal text is the FlashBlade's usual one for a read outside the
        user's scope; it has not been seen on this endpoint.
        """
        module = _module(connection_key="not-a-key")
        blade = _blade(remote_realm_visible=False)
        blade.post_realm_connections.return_value = _response(
            400, error=NO_MATCHING_KEY
        )
        blade.get_array_connections.return_value = _response(
            400, error="Operation not permitted."
        )
        with _patched_main(module, blade) as stack:
            stack.enter_context(patch(MODULE + ".RealmConnectionPost"))
            _run()

        msg = module.fail_json.call_args[1]["msg"]
        assert msg.endswith("Error: " + NO_MATCHING_KEY)
        assert "purefb_connect" not in msg

    def test_main_create_refusal_survives_a_failed_array_connection_read(self):
        """A transport error while looking for the hint never hides the refusal"""
        module = _module(connection_key="not-a-key")
        blade = _blade(remote_realm_visible=False)
        blade.post_realm_connections.return_value = _response(
            400, error=NO_MATCHING_KEY
        )
        blade.get_array_connections.side_effect = Exception("connection reset")
        with _patched_main(module, blade) as stack:
            stack.enter_context(patch(MODULE + ".RealmConnectionPost"))
            _run()

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert msg.endswith("Error: " + NO_MATCHING_KEY)
        assert "purefb_connect" not in msg

    def test_main_create_refusal_after_remote_key_keeps_hint_and_key_note(self):
        """With target_api the key is generated first, so both notes follow"""
        module = _module(target_url="10.0.0.2", target_api="T-remote")
        blade = _blade(remote_realm_visible=False, array_connections=[])
        blade.post_realm_connections.return_value = _response(
            400, error=NO_MATCHING_KEY
        )
        remote = Mock()
        remote.post_realm_connections_connection_key.return_value = _response(
            items=[_key("remote-key")]
        )
        with _patched_main(module, blade, remote_version="2.25") as stack:
            stack.enter_context(patch(MODULE + ".Client", return_value=remote))
            stack.enter_context(patch(MODULE + ".RealmConnectionPost"))
            _run()

        blade.get_remote_realms.assert_not_called()
        remote.post_realm_connections_connection_key.assert_called_once_with(
            realm_names=["finance-dr"]
        )
        remote.delete_realm_connections_connection_key.assert_not_called()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Error: " + NO_MATCHING_KEY + ". No array connection is visible" in msg
        assert msg.endswith(
            "purefb_connect. The connection key generated for remote realm "
            "finance-dr on 10.0.0.2 remains outstanding there until it expires "
            "or is invalidated with invalidate_keys."
        )

    def test_main_create_check_mode_unlisted_remote_realm_warns_and_changes(self):
        """Check mode no longer fails on a remote realm the user is not shown"""
        module = _module(check_mode=True, connection_key="oob-key")
        blade = _blade(remote_realm_visible=False, array_connections=[])
        with _patched_main(module, blade):
            _run()

        module.fail_json.assert_not_called()
        blade.get_remote_realms.assert_called_once_with(names=["finance-dr"])
        module.warn.assert_called_once()
        assert "Remote realm finance-dr is not listed" in module.warn.call_args[0][0]
        blade.post_realm_connections.assert_not_called()
        blade.get_array_connections.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True, connection=None)

    def test_main_create_check_mode_listed_remote_realm_does_not_warn(self):
        """Check mode stays silent when the remote realm is listed"""
        module = _module(check_mode=True, connection_key="oob-key")
        blade = _blade()
        with _patched_main(module, blade):
            _run()

        module.fail_json.assert_not_called()
        blade.get_remote_realms.assert_called_once_with(names=["finance-dr"])
        module.warn.assert_not_called()
        blade.post_realm_connections.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True, connection=None)

    def test_main_create_check_mode_unlisted_with_target_api_generates_no_key(self):
        """Check mode with target_api still validates the remote and writes nothing"""
        module = _module(check_mode=True, target_url="10.0.0.2", target_api="T-remote")
        blade = _blade(remote_realm_visible=False, array_connections=[])
        remote = Mock()
        with _patched_main(module, blade, remote_version="2.30") as stack:
            mock_client = stack.enter_context(
                patch(MODULE + ".Client", return_value=remote)
            )
            _run()

        mock_client.assert_called_once()
        remote.post_realm_connections_connection_key.assert_not_called()
        blade.post_realm_connections.assert_not_called()
        module.fail_json.assert_not_called()
        module.warn.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True, connection=None)

    # ---------------- destroyed local realm ----------------

    def test_main_destroyed_realm_fails_generate_key_with_recover_hint(self):
        """A destroyed realm is reported as destroyed, with the way out"""
        module = _module(remote_realm=None, generate_key=True)
        blade = _blade(realm_exists=False, realm_error=REALM_DESTROYED)
        with _patched_main(module, blade):
            _run()

        blade.get_realms.assert_called_once_with(destroyed=False, names=["finance"])
        blade.post_realm_connections_connection_key.assert_not_called()
        module.fail_json.assert_called_once_with(
            msg=(
                "Realm finance is not available. Error: Realm has been "
                "destroyed. Recover it with purefb_realm before managing its "
                "realm connections or connection keys."
            )
        )

    def test_main_destroyed_realm_fails_generate_key_in_check_mode(self):
        """Check mode reports the destroyed realm instead of a change"""
        module = _module(check_mode=True, remote_realm=None, generate_key=True)
        blade = _blade(realm_exists=False, realm_error=REALM_DESTROYED)
        with _patched_main(module, blade):
            _run()

        module.exit_json.assert_not_called()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Realm has been destroyed." in msg
        assert "purefb_realm" in msg

    def test_main_destroyed_realm_fails_invalidate_keys_with_recover_hint(self):
        """invalidate_keys on a destroyed realm names the cause before any read"""
        module = _module(remote_realm=None, invalidate_keys=True)
        blade = _blade(realm_exists=False, realm_error=REALM_DESTROYED)
        with _patched_main(module, blade):
            _run()

        blade.get_realm_connections_connection_key.assert_not_called()
        blade.delete_realm_connections_connection_key.assert_not_called()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Realm has been destroyed." in msg
        assert "Recover it with purefb_realm" in msg
        assert "does not exist" not in msg

    def test_main_destroyed_realm_fails_present_with_recover_hint(self):
        """state=present on a destroyed realm names the cause before any write"""
        module = _module(connection_key="oob-key")
        blade = _blade(realm_exists=False, realm_error=REALM_DESTROYED)
        with _patched_main(module, blade):
            _run()

        blade.get_realm_connections.assert_not_called()
        blade.post_realm_connections.assert_not_called()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Realm has been destroyed." in msg
        assert "Recover it with purefb_realm" in msg
        assert "does not exist" not in msg

    def test_main_destroyed_realm_is_noop_for_absent(self):
        """state=absent on a destroyed realm stays a no-op"""
        module = _module(state="absent")
        blade = _blade(realm_exists=False, realm_error=REALM_DESTROYED)
        with _patched_main(module, blade):
            _run()

        module.fail_json.assert_not_called()
        blade.delete_realm_connections.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False, connection=None)

    def test_main_missing_realm_has_no_recover_hint(self):
        """A realm that does not exist, or is outside the user's scope, gets no hint"""
        module = _module(remote_realm=None, invalidate_keys=True)
        blade = _blade(realm_exists=False)
        with _patched_main(module, blade):
            _run()

        blade.get_realm_connections_connection_key.assert_not_called()
        msg = module.fail_json.call_args[1]["msg"]
        assert "does not exist" in msg
        assert "purefb_realm" not in msg

    def test_main_unreadable_realm_relays_the_array_error(self):
        """Any other failed lookup is reported with the FlashBlade's own words

        The text stands for any answer other than the two seen on this lookup.
        """
        module = _module(remote_realm=None, generate_key=True)
        blade = _blade(realm_exists=False, realm_error="Operation not permitted.")
        with _patched_main(module, blade):
            _run()

        blade.post_realm_connections_connection_key.assert_not_called()
        module.fail_json.assert_called_once_with(
            msg="Realm finance is not available. Error: Operation not permitted."
        )

    # ---------------- realm-qualified values ----------------

    def test_main_realm_qualified_realm_is_reported_as_missing(self):
        """A realm::name value is looked up as given; no such realm can exist"""
        module = _module(realm="tenant::finance", remote_realm=None, generate_key=True)
        blade = _blade(realm_exists=False)
        with _patched_main(module, blade):
            _run()

        blade.get_realms.assert_called_once_with(
            destroyed=False, names=["tenant::finance"]
        )
        blade.post_realm_connections_connection_key.assert_not_called()
        module.fail_json.assert_called_once_with(
            msg="Realm tenant::finance is not available. Error: Realm does not exist."
        )

    def test_main_realm_qualified_realm_is_noop_for_absent(self):
        """state=absent with a realm::name value has nothing to disconnect"""
        module = _module(realm="tenant::finance", state="absent")
        blade = _blade(realm_exists=False)
        with _patched_main(module, blade):
            _run()

        module.fail_json.assert_not_called()
        blade.delete_realm_connections.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False, connection=None)

    def test_main_realm_qualified_remote_realm_is_sent_as_given(self):
        """A realm::name remote realm is passed through; the FlashBlade answers

        The refusal text is the one seen for an unknown plain remote realm; a
        qualified remote realm has not been posted to an array.
        """
        module = _module(remote_realm="tenant::finance-dr", connection_key="not-a-key")
        blade = _blade(remote_realm_visible=False)
        blade.post_realm_connections.return_value = _response(
            400, error=NO_MATCHING_KEY
        )
        with _patched_main(module, blade) as stack:
            mock_post = stack.enter_context(patch(MODULE + ".RealmConnectionPost"))
            _run()

        blade.get_realm_connections.assert_called_once_with(
            filter="local_realm.name='finance' and remote_realm.name='tenant::finance-dr'"
        )
        blade.post_realm_connections.assert_called_once_with(
            realm_connection_post=mock_post.return_value,
            local_realm_names=["finance"],
            remote_realm_names=["tenant::finance-dr"],
        )
        msg = module.fail_json.call_args[1]["msg"]
        assert "to remote realm tenant::finance-dr. Error: " + NO_MATCHING_KEY in msg
