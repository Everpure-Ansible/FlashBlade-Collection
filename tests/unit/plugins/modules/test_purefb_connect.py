# Copyright: (c) 2026, Pure Storage Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for the purefb_connect module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from unittest.mock import Mock, patch, MagicMock

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
sys.modules[
    "ansible_collections.everpure.flashblade.plugins.module_utils.time_utils"
] = MagicMock()

import pytest
from ansible.module_utils.compat.version import LooseVersion

from plugins.modules.purefb_connect import (
    _check_connected,
    break_connection,
    create_connection,
    main,
    update_connection,
)

MOD = "plugins.modules.purefb_connect"
LOCAL_NAME = "local-array"
REMOTE_NAME = "peer-array"
REMOTE_URL = "10.0.0.2"
REMOTE_TOKEN = "remote-token"
REFUSAL = "Operation not permitted."
TIMES = {"12AM": 0, "1AM": 3600000, "7AM": 25200000}


def _ok(items=(), total=None):
    """A response that answered 200. The items come as an iterator, like the
    SDK's ItemIterator: it cannot be indexed, only iterated."""
    res = Mock(spec=["status_code", "items", "total_item_count"])
    res.status_code = 200
    res.items = iter(list(items))
    res.total_item_count = len(items) if total is None else total
    return res


def _refused(message=REFUSAL, status_code=400):
    """A response the array refused: it carries errors and neither items nor
    a count."""
    error = Mock(spec=["message"])
    error.message = message
    res = Mock(spec=["status_code", "errors"])
    res.status_code = status_code
    res.errors = [error]
    return res


def _error_message(response, default="Unknown error"):
    """What get_error_message of module_utils returns."""
    errors = getattr(response, "errors", None)
    return errors[0].message if errors else default


def _writes(client):
    """Names of the calls made on a client that are not reads."""
    return [call[0] for call in client.method_calls if not call[0].startswith("get_")]


def _module(check_mode=False, **overrides):
    module = Mock()
    module.params = {
        "state": "present",
        "encrypted": False,
        "target_url": REMOTE_URL,
        "target_api": REMOTE_TOKEN,
        "target_repl": None,
        "default_limit": None,
        "window_limit": None,
        "window_start": None,
        "window_end": None,
        "context": "",
    }
    module.params.update(overrides)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _failure(module):
    """The message of the one fail_json call."""
    module.fail_json.assert_called_once()
    return module.fail_json.call_args[1]["msg"]


def _blade(connections=(), total=None):
    """The local array. Every read answers 200 with a fresh iterator."""
    local = Mock(spec=["name"])
    local.name = LOCAL_NAME
    blade = Mock()
    blade.get_arrays.side_effect = lambda **kwargs: _ok([local])
    blade.get_fleets.side_effect = lambda **kwargs: _ok([])
    blade.get_array_connections.side_effect = lambda **kwargs: _ok(connections, total)
    blade.get_file_system_replica_links.side_effect = lambda **kwargs: _ok()
    blade.get_bucket_replica_links.side_effect = lambda **kwargs: _ok()
    blade.post_array_connections.return_value = _ok()
    blade.patch_array_connections.return_value = _ok()
    blade.delete_array_connections.return_value = _ok()
    return blade


def _remote(connections=0):
    """The array at target_url, holding a number of array connections."""
    array = Mock(spec=["name"])
    array.name = REMOTE_NAME
    key = Mock(spec=["connection_key"])
    key.connection_key = "key-1"
    remote = Mock()
    remote.get_arrays.side_effect = lambda **kwargs: _ok([array])
    remote.get_array_connections.side_effect = lambda **kwargs: _ok(total=connections)
    remote.post_array_connections_connection_key.side_effect = lambda **kwargs: _ok(
        [key]
    )
    return remote


def _target(management_address=REMOTE_URL, status="connected"):
    """An array connection without bandwidth limits, as the array lists it.
    Only the array that formed the connection holds the management address."""
    target = Mock(
        spec=[
            "management_address",
            "remote",
            "status",
            "encrypted",
            "replication_addresses",
            "throttle",
        ]
    )
    target.management_address = management_address
    target.remote = Mock(spec=["name"])
    target.remote.name = REMOTE_NAME
    target.status = status
    target.encrypted = False
    target.replication_addresses = ["10.0.1.2"]
    target.throttle = Mock(spec=["default_limit", "window_limit", "window"])
    target.throttle.default_limit = None
    target.throttle.window_limit = None
    target.throttle.window = Mock(spec=["start", "end"])
    target.throttle.window.start = None
    target.throttle.window.end = None
    return target


@pytest.fixture(autouse=True)
def _sdk():
    """Request bodies become plain dicts so that they can be compared."""
    with patch(MOD + ".LooseVersion", LooseVersion), patch(
        MOD + ".get_rest_api_version", return_value="2.30"
    ), patch(MOD + ".get_error_message", _error_message), patch(
        MOD + ".ArrayConnectionPost", lambda **kwargs: kwargs
    ), patch(
        MOD + ".Throttle", lambda **kwargs: kwargs
    ), patch(
        MOD + ".TimeWindow", lambda **kwargs: kwargs
    ), patch(
        MOD + ".time_to_milliseconds", TIMES.__getitem__
    ):
        yield


@pytest.fixture
def client():
    """The SDK client factory the module logs in to the remote array with."""
    with patch(MOD + ".Client") as factory:
        yield factory


class TestBreakConnection:
    @patch("plugins.modules.purefb_connect.LooseVersion", LooseVersion)
    @patch("plugins.modules.purefb_connect.get_rest_api_version", return_value="2.21")
    def test_disconnect_iterates_the_arrays_response(self, _version):
        """Regression: get_arrays().items was indexed with [0], which raises
        TypeError on the SDK iterator and made every disconnect crash."""
        module = _module()
        blade = _blade()

        with pytest.raises(SystemExit):
            break_connection(module, blade, _target())

        blade.delete_array_connections.assert_called_once_with(
            remote_names=["peer-array"]
        )
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()

    @patch("plugins.modules.purefb_connect.LooseVersion", LooseVersion)
    @patch("plugins.modules.purefb_connect.get_rest_api_version", return_value="2.21")
    def test_disconnect_check_mode_changes_nothing(self, _version):
        module = _module(check_mode=True)
        blade = _blade()

        with pytest.raises(SystemExit):
            break_connection(module, blade, _target())

        blade.delete_array_connections.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_connect.LooseVersion", LooseVersion)
    @patch("plugins.modules.purefb_connect.get_rest_api_version", return_value="2.21")
    def test_disconnect_refused_from_the_target_side(self, _version):
        """Only the array that formed the connection holds the management
        address; the other side must fail cleanly rather than call delete."""
        module = _module()
        blade = _blade()
        target = _target()
        target.management_address = None

        with pytest.raises(SystemExit):
            break_connection(module, blade, target)

        module.fail_json.assert_called_once()
        blade.delete_array_connections.assert_not_called()

    def test_check_mode_refuses_the_target_side_like_the_real_run(self):
        """Check mode must not promise a disconnect the real run refuses."""
        module = _module(check_mode=True)
        blade = _blade()

        with pytest.raises(SystemExit):
            break_connection(module, blade, _target(management_address=None))

        assert "array that formed the connection" in _failure(module)
        module.exit_json.assert_not_called()
        assert blade.method_calls == []

    def test_refused_read_of_the_array_name_is_reported(self):
        module = _module()
        blade = _blade()
        blade.get_arrays.side_effect = lambda **kwargs: _refused()

        with pytest.raises(SystemExit):
            break_connection(module, blade, _target())

        assert _failure(module) == (
            "Failed to read the array name. Error: Operation not permitted."
        )
        blade.delete_array_connections.assert_not_called()

    def test_refused_disconnect_is_reported(self):
        module = _module()
        blade = _blade()
        blade.delete_array_connections.return_value = _refused()

        with pytest.raises(SystemExit):
            break_connection(module, blade, _target())

        assert _failure(module) == (
            "Failed to disconnect peer-array from local-array. "
            "Error: Operation not permitted."
        )

    def test_context_is_sent_with_the_local_requests(self):
        module = _module(context="fleet-member")
        blade = _blade()

        with pytest.raises(SystemExit):
            break_connection(module, blade, _target())

        blade.get_arrays.assert_called_once_with(context_names=["fleet-member"])
        blade.delete_array_connections.assert_called_once_with(
            remote_names=["peer-array"], context_names=["fleet-member"]
        )


class TestCheckConnected:
    def test_refused_read_is_reported(self, client):
        module = _module()
        blade = _blade()
        blade.get_array_connections.side_effect = lambda **kwargs: _refused()

        with pytest.raises(SystemExit):
            _check_connected(module, blade)

        assert _failure(module) == (
            "Failed to read the array connections. Error: Operation not permitted."
        )
        client.assert_not_called()

    def test_connection_formed_here_is_found_by_its_address(self, client):
        target = _target()

        assert _check_connected(_module(), _blade([target])) is target
        client.assert_not_called()

    def test_another_address_is_not_connected(self, client):
        module = _module(state="absent", target_url="192.0.2.1", target_api=None)

        assert _check_connected(module, _blade([_target()])) is None
        client.assert_not_called()

    def test_context_is_sent_with_the_read(self, client):
        blade = _blade()

        assert _check_connected(_module(context="fleet-member"), blade) is None
        blade.get_array_connections.assert_called_once_with(
            context_names=["fleet-member"]
        )

    def test_connection_formed_by_the_remote_is_found_by_its_name(self, client):
        """Such a connection has no management address here, so the name of
        the array at target_url decides."""
        target = _target(management_address=None)
        remote = client.return_value = _remote()

        assert _check_connected(_module(), _blade([target])) is target
        client.assert_called_once_with(target=REMOTE_URL, api_token=REMOTE_TOKEN)
        assert _writes(remote) == []

    def test_remote_login_failure_is_reported(self, client):
        module = _module()
        client.side_effect = Exception("no route to host")

        with pytest.raises(SystemExit):
            _check_connected(module, _blade([_target(management_address=None)]))

        assert _failure(module) == (
            "Failed to connect to remote array 10.0.0.2. Error: no route to host"
        )

    def test_refused_read_of_the_remote_name_is_reported(self, client):
        module = _module()
        remote = client.return_value = _remote()
        remote.get_arrays.side_effect = lambda **kwargs: _refused()

        with pytest.raises(SystemExit):
            _check_connected(module, _blade([_target(management_address=None)]))

        assert _failure(module) == (
            "Failed to read the array name from 10.0.0.2. "
            "Error: Operation not permitted."
        )


class TestCreateConnection:
    def test_check_mode_creates_no_connection_key(self, client):
        """The connection key is an object on the remote array: check mode
        reads both arrays and sends nothing to either."""
        module = _module(check_mode=True)
        blade = _blade()
        remote = client.return_value = _remote()

        with pytest.raises(SystemExit):
            create_connection(module, blade)

        remote.post_array_connections_connection_key.assert_not_called()
        assert _writes(remote) == []
        assert _writes(blade) == []
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()

    def test_create_requests_the_key_and_connects(self, client):
        module = _module()
        blade = _blade()
        remote = client.return_value = _remote()

        with pytest.raises(SystemExit):
            create_connection(module, blade)

        client.assert_called_once_with(target=REMOTE_URL, api_token=REMOTE_TOKEN)
        remote.post_array_connections_connection_key.assert_called_once_with()
        blade.post_array_connections.assert_called_once_with(
            array_connection={
                "management_address": REMOTE_URL,
                "replication_addresses": None,
                "encrypted": False,
                "connection_key": "key-1",
            }
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_create_with_bandwidth_limits(self, client):
        module = _module(
            encrypted=True,
            target_repl=["10.0.1.2"],
            default_limit="5M",
            window_limit="28G",
            window_start="1AM",
            window_end="7AM",
        )
        blade = _blade()
        client.return_value = _remote()

        with pytest.raises(SystemExit):
            create_connection(module, blade)

        blade.post_array_connections.assert_called_once_with(
            array_connection={
                "management_address": REMOTE_URL,
                "replication_addresses": ["10.0.1.2"],
                "encrypted": True,
                "connection_key": "key-1",
                "throttle": {
                    "default_limit": 5242880,
                    "window_limit": 30064771072,
                    "window": {"start": 3600000, "end": 25200000},
                },
            }
        )

    def test_limits_are_worked_out_before_the_key_is_requested(self, client):
        """A value that cannot be converted must not leave a key behind."""
        module = _module(window_limit="28G")
        blade = _blade()
        remote = client.return_value = _remote()

        def _to_milliseconds(value):
            assert not remote.post_array_connections_connection_key.called
            return TIMES[value]

        with patch(MOD + ".time_to_milliseconds", _to_milliseconds):
            with pytest.raises(SystemExit):
                create_connection(module, blade)

        remote.post_array_connections_connection_key.assert_called_once_with()
        blade.post_array_connections.assert_called_once_with(
            array_connection={
                "management_address": REMOTE_URL,
                "replication_addresses": None,
                "encrypted": False,
                "connection_key": "key-1",
                "throttle": {
                    "window_limit": 30064771072,
                    "window": {"start": 0, "end": 0},
                },
            }
        )

    def test_context_is_sent_with_the_local_requests(self, client):
        module = _module(context="fleet-member")
        blade = _blade()
        remote = client.return_value = _remote()

        with pytest.raises(SystemExit):
            create_connection(module, blade)

        blade.get_array_connections.assert_called_once_with(
            context_names=["fleet-member"]
        )
        remote.get_array_connections.assert_called_once_with()
        assert blade.post_array_connections.call_args[1]["context_names"] == [
            "fleet-member"
        ]

    def test_fan_out_maximum_is_reported_in_check_mode(self, client):
        module = _module(check_mode=True)

        with pytest.raises(SystemExit):
            create_connection(module, _blade(total=5))

        assert _failure(module) == "FlashBlade fan-out maximum of 5 already reached"
        client.assert_not_called()

    def test_fan_in_maximum_is_reported_in_check_mode(self, client):
        module = _module(check_mode=True)
        remote = client.return_value = _remote(connections=5)

        with pytest.raises(SystemExit):
            create_connection(module, _blade())

        assert "Fan-In not supported" in _failure(module)
        assert _writes(remote) == []

    def test_refused_read_of_the_local_connections_is_reported(self, client):
        module = _module(check_mode=True)
        blade = _blade()
        blade.get_array_connections.side_effect = lambda **kwargs: _refused()

        with pytest.raises(SystemExit):
            create_connection(module, blade)

        assert _failure(module) == (
            "Failed to read the array connections. Error: Operation not permitted."
        )
        client.assert_not_called()

    def test_remote_login_failure_is_reported(self, client):
        module = _module()
        blade = _blade()
        client.side_effect = Exception("no route to host")

        with pytest.raises(SystemExit):
            create_connection(module, blade)

        assert _failure(module) == (
            "Failed to connect to remote array 10.0.0.2. Error: no route to host"
        )
        assert _writes(blade) == []

    def test_refused_read_of_the_remote_name_is_reported(self, client):
        module = _module()
        blade = _blade()
        remote = client.return_value = _remote()
        remote.get_arrays.side_effect = lambda **kwargs: _refused()

        with pytest.raises(SystemExit):
            create_connection(module, blade)

        assert _failure(module) == (
            "Failed to read the array name from 10.0.0.2. "
            "Error: Operation not permitted."
        )
        assert _writes(remote) == []
        assert _writes(blade) == []

    def test_refused_read_of_the_remote_connections_is_reported(self, client):
        module = _module()
        blade = _blade()
        remote = client.return_value = _remote()
        remote.get_array_connections.side_effect = lambda **kwargs: _refused()

        with pytest.raises(SystemExit):
            create_connection(module, blade)

        assert _failure(module) == (
            "Failed to read the array connections of remote array peer-array. "
            "Error: Operation not permitted."
        )
        assert _writes(remote) == []
        assert _writes(blade) == []

    def test_refused_connection_key_is_reported(self, client):
        module = _module()
        blade = _blade()
        remote = client.return_value = _remote()
        remote.post_array_connections_connection_key.side_effect = (
            lambda **kwargs: _refused()
        )

        with pytest.raises(SystemExit):
            create_connection(module, blade)

        assert _failure(module) == (
            "Failed to create a connection key on remote array peer-array. "
            "Error: Operation not permitted."
        )
        blade.post_array_connections.assert_not_called()

    def test_refused_connection_is_reported(self, client):
        module = _module()
        blade = _blade()
        blade.post_array_connections.return_value = _refused()
        client.return_value = _remote()

        with pytest.raises(SystemExit):
            create_connection(module, blade)

        assert _failure(module) == (
            "Failed to connect to remote array peer-array. "
            "Error: Operation not permitted."
        )


class TestUpdateConnection:
    def test_unchanged_connection_sends_nothing(self, client):
        module = _module()
        blade = _blade([_target()])
        remote = client.return_value = _remote()

        with pytest.raises(SystemExit):
            update_connection(module, blade)

        blade.get_array_connections.assert_called_once_with(
            filter="remote.name='peer-array'"
        )
        assert _writes(blade) == []
        assert _writes(remote) == []
        module.exit_json.assert_called_once_with(changed=False)

    def test_change_is_sent(self, client):
        module = _module(target_repl=["10.0.1.3"])
        blade = _blade([_target()])
        client.return_value = _remote()

        with pytest.raises(SystemExit):
            update_connection(module, blade)

        blade.patch_array_connections.assert_called_once_with(
            remote_names=["peer-array"],
            array_connection={
                "replication_addresses": ["10.0.1.3"],
                "encrypted": False,
                "throttle": {
                    "default_limit": None,
                    "window_limit": None,
                    "window": {"start": None, "end": None},
                },
            },
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_check_mode_change_sends_nothing(self, client):
        module = _module(check_mode=True, target_repl=["10.0.1.3"])
        blade = _blade([_target()])
        remote = client.return_value = _remote()

        with pytest.raises(SystemExit):
            update_connection(module, blade)

        assert _writes(blade) == []
        assert _writes(remote) == []
        module.exit_json.assert_called_once_with(changed=True)

    def test_remote_login_failure_is_reported(self, client):
        module = _module()
        client.side_effect = Exception("no route to host")

        with pytest.raises(SystemExit):
            update_connection(module, _blade([_target()]))

        assert _failure(module) == (
            "Failed to connect to remote array 10.0.0.2. Error: no route to host"
        )

    def test_refused_read_of_the_remote_name_is_reported(self, client):
        module = _module()
        remote = client.return_value = _remote()
        remote.get_arrays.side_effect = lambda **kwargs: _refused()

        with pytest.raises(SystemExit):
            update_connection(module, _blade([_target()]))

        assert _failure(module) == (
            "Failed to read the array name from 10.0.0.2. "
            "Error: Operation not permitted."
        )

    def test_refused_read_of_the_connection_is_reported(self, client):
        module = _module()
        blade = _blade([_target()])
        blade.get_array_connections.side_effect = lambda **kwargs: _refused()
        client.return_value = _remote()

        with pytest.raises(SystemExit):
            update_connection(module, blade)

        assert _failure(module) == (
            "Failed to read the array connections. Error: Operation not permitted."
        )

    def test_connection_that_is_not_listed_is_reported(self, client):
        module = _module()
        client.return_value = _remote()

        with pytest.raises(SystemExit):
            update_connection(module, _blade())

        assert _failure(module) == "No connection to remote array peer-array found"

    def test_replica_links_stop_encryption(self, client):
        module = _module(encrypted=True)
        blade = _blade([_target()])
        blade.get_file_system_replica_links.side_effect = lambda **kwargs: _ok(total=1)
        client.return_value = _remote()

        with pytest.raises(SystemExit):
            update_connection(module, blade)

        assert "file system replica links exist" in _failure(module)
        assert _writes(blade) == []

    def test_refused_read_of_the_replica_links_is_reported(self, client):
        module = _module(encrypted=True)
        blade = _blade([_target()])
        blade.get_file_system_replica_links.side_effect = lambda **kwargs: _refused()
        client.return_value = _remote()

        with pytest.raises(SystemExit):
            update_connection(module, blade)

        assert _failure(module) == (
            "Failed to read the file system replica links. "
            "Error: Operation not permitted."
        )
        assert _writes(blade) == []

    def test_refused_read_of_the_bucket_links_is_reported(self, client):
        module = _module(default_limit="5M")
        blade = _blade([_target()])
        blade.get_bucket_replica_links.side_effect = lambda **kwargs: _refused()
        client.return_value = _remote()

        with pytest.raises(SystemExit):
            update_connection(module, blade)

        assert _failure(module) == (
            "Failed to read the bucket replica links. Error: Operation not permitted."
        )
        assert _writes(blade) == []

    def test_bucket_links_matter_only_for_a_limit(self, client):
        """Without a bandwidth limit in the task the count is not used, so a
        refused read of it does not stop the run."""
        module = _module()
        blade = _blade([_target()])
        blade.get_bucket_replica_links.side_effect = lambda **kwargs: _refused()
        client.return_value = _remote()

        with pytest.raises(SystemExit):
            update_connection(module, blade)

        module.exit_json.assert_called_once_with(changed=False)
        module.fail_json.assert_not_called()


def _run_main(module, blade):
    with patch(MOD + ".AnsibleModule", return_value=module), patch(
        MOD + ".get_system", return_value=blade
    ):
        with pytest.raises(SystemExit):
            main()


class TestMain:
    def test_check_mode_present_sends_no_write_to_either_array(self, client):
        module = _module(check_mode=True)
        blade = _blade()
        remote = client.return_value = _remote()

        _run_main(module, blade)

        assert _writes(blade) == []
        assert _writes(remote) == []
        module.exit_json.assert_called_once_with(changed=True)

    def test_present_connects_once(self, client):
        module = _module()
        blade = _blade()
        remote = client.return_value = _remote()

        _run_main(module, blade)

        assert _writes(remote) == ["post_array_connections_connection_key"]
        assert _writes(blade) == ["post_array_connections"]
        module.exit_json.assert_called_once_with(changed=True)

    def test_absent_and_not_connected_is_unchanged(self, client):
        module = _module(state="absent", target_url="192.0.2.1", target_api=None)
        blade = _blade([_target()])

        _run_main(module, blade)

        client.assert_not_called()
        assert _writes(blade) == []
        module.exit_json.assert_called_once_with(changed=False)

    def test_absent_check_mode_sends_nothing(self, client):
        module = _module(check_mode=True, state="absent", target_api=None)
        blade = _blade([_target()])

        _run_main(module, blade)

        client.assert_not_called()
        assert _writes(blade) == []
        module.exit_json.assert_called_once_with(changed=True)

    def test_fleet_member_uses_its_own_name_as_context(self, client):
        module = _module(state="absent", target_url="192.0.2.1", target_api=None)
        blade = _blade()
        blade.get_fleets.side_effect = lambda **kwargs: _ok([Mock()])

        _run_main(module, blade)

        blade.get_array_connections.assert_called_once_with(
            context_names=["local-array"]
        )
        module.exit_json.assert_called_once_with(changed=False)

    def test_refused_read_of_the_array_name_is_reported(self, client):
        module = _module(state="absent", target_url="192.0.2.1", target_api=None)
        blade = _blade()
        blade.get_fleets.side_effect = lambda **kwargs: _ok([Mock()])
        blade.get_arrays.side_effect = lambda **kwargs: _refused()

        _run_main(module, blade)

        assert _failure(module) == (
            "Failed to read the array name. Error: Operation not permitted."
        )
        blade.get_array_connections.assert_not_called()

    def test_refused_read_of_the_connections_is_reported(self, client):
        module = _module(state="absent", target_url="192.0.2.1", target_api=None)
        blade = _blade()
        blade.get_array_connections.side_effect = lambda **kwargs: _refused()

        _run_main(module, blade)

        assert _failure(module) == (
            "Failed to read the array connections. Error: Operation not permitted."
        )
