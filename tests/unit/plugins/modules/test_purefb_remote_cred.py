# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_remote_cred module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from unittest.mock import Mock, patch, MagicMock

import yaml

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

from plugins.module_utils.version import LooseVersion as RealLooseVersion
from plugins.modules import purefb_remote_cred
from plugins.modules.purefb_remote_cred import main

MOD = "plugins.modules.purefb_remote_cred"
ABSENT = "Remote credentials does not exist."
NOT_PERMITTED = "Operation not permitted."
KEY = "FAKEACCESSKEY0000001"
OTHER_KEY = "FAKEACCESSKEY0000002"
SECRET = "fakeRemoteSecretNotReal000000000000000000000"
BODY = {"access_key_id": KEY, "secret_access_key": SECRET}
# What an array administrator sees: one connected array, two S3 targets.
CONNECTIONS = (("arrayb", "10.10.10.30", "connected"),)
TARGETS = (("target1", "connecting"), ("target2", "connected"))
# The realms of the array and the targets that are shared with them.
REALMS = ("realm1", "realm2")
SHARED = {"target1": ("realm1", "realm2")}


def _module(check_mode=False, **overrides):
    module = Mock()
    module.params = {
        "name": "cred1",
        "target": "target1",
        "state": "present",
        "access_key": KEY,
        "secret": SECRET,
        "force": False,
        "context": "",
    }
    module.params.update(overrides)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _valid(items=None):
    res = Mock()
    res.status_code = 200
    res.items = iter(items or [])
    return res


def _error(message, status_code=400):
    """An error answer of the SDK: it has errors and no items."""
    error = Mock()
    error.message = message
    res = Mock(spec=["status_code", "errors"])
    res.status_code = status_code
    res.errors = [error]
    return res


def _connection(name, address, status):
    """An array connection as GET /array-connections returns it."""
    connection = Mock()
    connection.remote = Mock()
    connection.remote.name = name
    connection.management_address = address
    connection.status = status
    return connection


def _target(name, status):
    """An S3 target as GET /targets returns it."""
    target = Mock()
    target.name = name
    target.status = status
    return target


def _cred(name, access_key):
    """A remote credential as GET /object-store-remote-credentials returns it."""
    cred = Mock()
    cred.name = name
    cred.access_key_id = access_key
    return cred


def _blade(creds=(), connections=CONNECTIONS, targets=TARGETS, realm_admin=None):
    """An array that answers the way Purity//FB does.

    creds are (full name, access key ID) pairs. The array keeps a remote
    credential under target/name and matches names without regard to case.
    With realm_admin the array answers an administrator whose management
    access is limited to that realm.
    """
    blade = Mock()
    blade.creds = dict((name.lower(), (name, key)) for name, key in creds)

    def visible(full_name):
        realm = full_name.split("/", 1)[1].rpartition("::")[0]
        return realm_admin is None or realm.lower() == realm_admin

    def get_creds(names=None, **kwargs):
        found = blade.creds.get(names[0].lower())
        if not found or not visible(names[0]):
            return _error(ABSENT)
        return _valid([_cred(*found)])

    def post_creds(names=None, remote_credentials=None, **kwargs):
        remote, name = names[0].split("/", 1)
        realm = name.rpartition("::")[0]
        if not visible(names[0]):
            return _error(NOT_PERMITTED)
        if realm and realm not in REALMS:
            return _error("Realm does not exist.")
        if realm and realm not in SHARED.get(remote.lower(), ()):
            return _error(
                "Target '{0}' is not shared into realm '{1}'.".format(remote, realm)
            )
        blade.creds[names[0].lower()] = (names[0], remote_credentials["access_key_id"])
        return _valid()

    def patch_creds(names=None, remote_credentials=None, **kwargs):
        stored = blade.creds[names[0].lower()]
        blade.creds[names[0].lower()] = (
            stored[0],
            remote_credentials["access_key_id"],
        )
        return _valid()

    def delete_creds(names=None, **kwargs):
        del blade.creds[names[0].lower()]
        return _valid()

    blade.get_array_connections.side_effect = lambda **kw: _valid(
        [_connection(*connection) for connection in connections]
    )
    blade.get_targets.side_effect = lambda **kw: _valid(
        [_target(*target) for target in targets]
    )
    blade.get_fleets.side_effect = lambda **kw: _valid()
    blade.get_object_store_remote_credentials.side_effect = get_creds
    blade.post_object_store_remote_credentials.side_effect = post_creds
    blade.patch_object_store_remote_credentials.side_effect = patch_creds
    blade.delete_object_store_remote_credentials.side_effect = delete_creds
    if realm_admin:
        # It is refused the fleet, sees no array connection and only the
        # targets that are shared with its realm.
        blade.get_fleets.side_effect = lambda **kw: _error(NOT_PERMITTED)
        blade.get_array_connections.side_effect = lambda **kw: _valid()
        blade.get_targets.side_effect = lambda **kw: _valid(
            [
                _target(*target)
                for target in targets
                if realm_admin in SHARED.get(target[0], ())
            ]
        )
    return blade


def _run(module, blade, api_version="2.30", has_sdk=True):
    """Run main() with the module and blade mocks; return the AnsibleModule mock."""
    with patch(MOD + ".AnsibleModule", return_value=module) as ansible_module, patch(
        MOD + ".get_system", return_value=blade
    ), patch(MOD + ".purefb_argument_spec", return_value={}), patch(
        MOD + ".HAS_PYPURECLIENT", has_sdk
    ), patch(
        MOD + ".get_rest_api_version", return_value=api_version
    ), patch(
        MOD + ".LooseVersion", RealLooseVersion
    ), patch(
        MOD + ".ObjectStoreRemoteCredentialsPost", side_effect=lambda **kw: kw
    ), patch(
        MOD + ".ObjectStoreRemoteCredentials", side_effect=lambda **kw: kw
    ), patch(
        MOD + ".get_error_message", side_effect=lambda res: res.errors[0].message
    ):
        try:
            main()
        except SystemExit:
            pass
    return ansible_module


def _apply(blade, check_mode=False, api_version="2.30", **params):
    """Run one task against the array; return its module mock."""
    module = _module(check_mode=check_mode, **params)
    _run(module, blade, api_version=api_version)
    return module


def _changed(module):
    module.fail_json.assert_not_called()
    module.exit_json.assert_called_once()
    return module.exit_json.call_args[1]["changed"]


def _failure(module):
    """The message of the one and only fail_json; nothing may exit after it."""
    module.fail_json.assert_called_once()
    module.exit_json.assert_not_called()
    return module.fail_json.call_args[1]["msg"]


def _no_writes(blade):
    blade.post_object_store_remote_credentials.assert_not_called()
    blade.patch_object_store_remote_credentials.assert_not_called()
    blade.delete_object_store_remote_credentials.assert_not_called()


def _stored(blade):
    """The remote credentials of the array: full name -> access key ID."""
    return dict(blade.creds.values())


class TestCreate:
    """state=present for a credential that does not exist"""

    def test_create_then_unchanged(self):
        blade = _blade()
        assert _changed(_apply(blade)) is True
        assert _changed(_apply(blade)) is False
        blade.post_object_store_remote_credentials.assert_called_once_with(
            names=["target1/cred1"], remote_credentials=BODY
        )
        blade.patch_object_store_remote_credentials.assert_not_called()
        assert _stored(blade) == {"target1/cred1": KEY}

    def test_create_check_mode_sends_nothing(self):
        blade = _blade()
        assert _changed(_apply(blade, check_mode=True)) is True
        _no_writes(blade)

    def test_create_for_a_connected_array(self):
        blade = _blade()
        assert _changed(_apply(blade, target="arrayb")) is True
        assert _changed(_apply(blade, target="arrayb")) is False
        assert _stored(blade) == {"arrayb/cred1": KEY}

    def test_target_is_read_only_when_no_array_connection_matches(self):
        blade = _blade()
        _apply(blade, target="arrayb")
        blade.get_targets.assert_not_called()

    def test_create_refused_by_the_array(self):
        blade = _blade()
        blade.post_object_store_remote_credentials.side_effect = lambda **kw: _error(
            NOT_PERMITTED
        )
        assert _failure(_apply(blade)) == (
            "Failed to create remote credential target1/cred1. "
            "Error: Operation not permitted."
        )

    def test_other_credentials_of_the_target_are_untouched(self):
        blade = _blade(creds=[("target1/cred2", OTHER_KEY)])
        assert _changed(_apply(blade)) is True
        assert _stored(blade) == {"target1/cred1": KEY, "target1/cred2": OTHER_KEY}

    def test_same_name_on_another_target_is_another_credential(self):
        blade = _blade(creds=[("target2/cred1", OTHER_KEY)])
        assert _changed(_apply(blade)) is True
        assert _stored(blade) == {"target1/cred1": KEY, "target2/cred1": OTHER_KEY}


class TestUpdate:
    """state=present for a credential that exists"""

    def test_new_access_key_then_unchanged(self):
        blade = _blade(creds=[("target1/cred1", OTHER_KEY)])
        assert _changed(_apply(blade)) is True
        assert _changed(_apply(blade)) is False
        blade.patch_object_store_remote_credentials.assert_called_once_with(
            names=["target1/cred1"], remote_credentials=BODY
        )
        blade.post_object_store_remote_credentials.assert_not_called()
        assert _stored(blade) == {"target1/cred1": KEY}

    def test_new_access_key_check_mode_sends_nothing(self):
        blade = _blade(creds=[("target1/cred1", OTHER_KEY)])
        assert _changed(_apply(blade, check_mode=True)) is True
        _no_writes(blade)
        assert _stored(blade) == {"target1/cred1": OTHER_KEY}

    def test_same_access_key_is_unchanged(self):
        """The secret cannot be read back, so it is not compared."""
        blade = _blade(creds=[("target1/cred1", KEY)])
        assert _changed(_apply(blade, secret="anotherSecretNotReal")) is False
        _no_writes(blade)

    def test_force_sends_the_keys_on_every_run(self):
        blade = _blade(creds=[("target1/cred1", KEY)])
        assert _changed(_apply(blade, force=True)) is True
        assert _changed(_apply(blade, force=True)) is True
        assert blade.patch_object_store_remote_credentials.call_count == 2

    def test_force_check_mode_sends_nothing(self):
        blade = _blade(creds=[("target1/cred1", KEY)])
        assert _changed(_apply(blade, force=True, check_mode=True)) is True
        _no_writes(blade)

    def test_update_refused_by_the_array(self):
        blade = _blade(creds=[("target1/cred1", OTHER_KEY)])
        blade.patch_object_store_remote_credentials.side_effect = lambda **kw: _error(
            NOT_PERMITTED
        )
        assert _failure(_apply(blade)) == (
            "Failed to update remote credential target1/cred1. "
            "Error: Operation not permitted."
        )


class TestDelete:
    """state=absent"""

    def test_delete_then_unchanged(self):
        blade = _blade(creds=[("target1/cred1", KEY)])
        assert _changed(_apply(blade, state="absent")) is True
        assert _changed(_apply(blade, state="absent")) is False
        blade.delete_object_store_remote_credentials.assert_called_once_with(
            names=["target1/cred1"]
        )
        assert not _stored(blade)

    def test_delete_check_mode_sends_nothing(self):
        blade = _blade(creds=[("target1/cred1", KEY)])
        assert _changed(_apply(blade, state="absent", check_mode=True)) is True
        _no_writes(blade)

    def test_delete_needs_no_keys(self):
        blade = _blade(creds=[("target1/cred1", KEY)])
        module = _apply(blade, state="absent", access_key=None, secret=None)
        assert _changed(module) is True

    def test_absent_credential_is_unchanged(self):
        blade = _blade(creds=[("target1/cred2", KEY)])
        assert _changed(_apply(blade, state="absent")) is False
        _no_writes(blade)

    def test_delete_refused_by_the_array(self):
        blade = _blade(creds=[("target1/cred1", KEY)])
        blade.delete_object_store_remote_credentials.side_effect = lambda **kw: _error(
            NOT_PERMITTED
        )
        assert _failure(_apply(blade, state="absent")) == (
            "Failed to delete remote credential target1/cred1. "
            "Error: Operation not permitted."
        )


class TestTarget:
    """The target is a connected array or an S3 target, found by its name"""

    def test_unknown_target(self):
        blade = _blade()
        assert _failure(_apply(blade, target="target9")) == (
            "Selected target target9 is not connected, "
            "or is not visible to this user."
        )
        _no_writes(blade)
        blade.get_object_store_remote_credentials.assert_not_called()

    def test_unknown_target_in_check_mode(self):
        blade = _blade()
        module = _apply(blade, target="target9", check_mode=True)
        assert "Selected target target9 is not connected" in _failure(module)

    def test_unknown_target_for_absent(self):
        blade = _blade(creds=[("target1/cred1", KEY)])
        module = _apply(blade, target="target9", state="absent")
        assert "Selected target target9 is not connected" in _failure(module)
        _no_writes(blade)

    def test_incompatible_array_connection_is_not_connected(self):
        blade = _blade(connections=[("arrayb", "10.10.10.30", "incompatible")])
        module = _apply(blade, target="arrayb")
        assert "Selected target arrayb is not connected" in _failure(module)
        _no_writes(blade)

    def test_partially_connected_array_is_connected(self):
        blade = _blade(connections=[("arrayb", "10.10.10.30", "partially_connected")])
        assert _changed(_apply(blade, target="arrayb")) is True

    def test_connecting_target_is_connected(self):
        blade = _blade(targets=[("target1", "connecting")])
        assert _changed(_apply(blade)) is True

    def test_target_in_another_letter_case(self):
        """The array matches names without regard to case."""
        blade = _blade()
        assert _changed(_apply(blade, target="TARGET1")) is True
        assert _changed(_apply(blade, target="Target1")) is False
        blade.post_object_store_remote_credentials.assert_called_once_with(
            names=["target1/cred1"], remote_credentials=BODY
        )
        assert _stored(blade) == {"target1/cred1": KEY}

    def test_stored_target_name_in_upper_case(self):
        blade = _blade(targets=[("S3-West", "connected")])
        assert _changed(_apply(blade, target="s3-west")) is True
        blade.post_object_store_remote_credentials.assert_called_once_with(
            names=["S3-West/cred1"], remote_credentials=BODY
        )

    def test_connected_array_in_another_letter_case(self):
        blade = _blade(creds=[("arrayb/cred1", OTHER_KEY)])
        assert _changed(_apply(blade, target="ArrayB")) is True
        blade.patch_object_store_remote_credentials.assert_called_once_with(
            names=["arrayb/cred1"], remote_credentials=BODY
        )

    def test_connected_array_by_its_management_address(self):
        """The credential is kept under the name of the array."""
        blade = _blade()
        assert _changed(_apply(blade, target="10.10.10.30")) is True
        assert _changed(_apply(blade, target="10.10.10.30")) is False
        blade.post_object_store_remote_credentials.assert_called_once_with(
            names=["arrayb/cred1"], remote_credentials=BODY
        )
        assert _stored(blade) == {"arrayb/cred1": KEY}

    def test_delete_by_the_management_address(self):
        blade = _blade(creds=[("arrayb/cred1", KEY)])
        assert _changed(_apply(blade, target="10.10.10.30", state="absent")) is True
        blade.delete_object_store_remote_credentials.assert_called_once_with(
            names=["arrayb/cred1"]
        )

    def test_array_connection_without_a_remote_name_is_skipped(self):
        """remote is optional in the SDK model."""
        blade = _blade()
        nameless = _connection(None, "10.10.10.40", "connecting")
        nameless.remote = None
        blade.get_array_connections.side_effect = lambda **kw: _valid(
            [nameless, _connection("arrayb", "10.10.10.30", "connected")]
        )
        assert _changed(_apply(blade, target="arrayb")) is True
        assert _stored(blade) == {"arrayb/cred1": KEY}

    def test_realm_prefix_on_the_target(self):
        """The prefix goes on the name; a target has none."""
        blade = _blade()
        module = _apply(blade, target="realm1::target1")
        assert _failure(module) == (
            "Selected target realm1::target1 is not connected, "
            "or is not visible to this user. The name of a target has no realm "
            "prefix: for a remote credential in a realm give name as realm::name."
        )
        _no_writes(blade)

    def test_realm_prefix_on_the_target_in_check_mode(self):
        blade = _blade()
        module = _apply(blade, target="realm1::target1", check_mode=True)
        assert "has no realm prefix" in _failure(module)


class TestRealm:
    """A credential in a realm is named realm::name; the target is shared"""

    def test_create_then_unchanged(self):
        blade = _blade()
        assert _changed(_apply(blade, name="realm1::cred1")) is True
        assert _changed(_apply(blade, name="realm1::cred1")) is False
        blade.post_object_store_remote_credentials.assert_called_once_with(
            names=["target1/realm1::cred1"], remote_credentials=BODY
        )

    def test_create_check_mode_sends_nothing(self):
        blade = _blade()
        module = _apply(blade, name="realm1::cred1", check_mode=True)
        assert _changed(module) is True
        _no_writes(blade)

    def test_namesakes_in_other_scopes_are_untouched(self):
        blade = _blade(
            creds=[("target1/cred1", OTHER_KEY), ("target1/realm2::cred1", OTHER_KEY)]
        )
        assert _changed(_apply(blade, name="realm1::cred1")) is True
        assert _stored(blade) == {
            "target1/cred1": OTHER_KEY,
            "target1/realm1::cred1": KEY,
            "target1/realm2::cred1": OTHER_KEY,
        }

    def test_update_changes_only_the_realm_credential(self):
        blade = _blade(
            creds=[("target1/cred1", OTHER_KEY), ("target1/realm1::cred1", OTHER_KEY)]
        )
        assert _changed(_apply(blade, name="realm1::cred1")) is True
        assert _changed(_apply(blade, name="realm1::cred1")) is False
        blade.patch_object_store_remote_credentials.assert_called_once_with(
            names=["target1/realm1::cred1"], remote_credentials=BODY
        )
        assert _stored(blade) == {
            "target1/cred1": OTHER_KEY,
            "target1/realm1::cred1": KEY,
        }

    def test_bare_name_changes_only_the_array_level_credential(self):
        blade = _blade(
            creds=[("target1/cred1", OTHER_KEY), ("target1/realm1::cred1", OTHER_KEY)]
        )
        assert _changed(_apply(blade)) is True
        assert _stored(blade) == {
            "target1/cred1": KEY,
            "target1/realm1::cred1": OTHER_KEY,
        }

    def test_bare_name_is_not_completed_with_a_realm(self):
        """Only a realm credential exists: the bare name is a new credential."""
        blade = _blade(creds=[("target1/realm1::cred1", KEY)])
        assert _changed(_apply(blade)) is True
        blade.post_object_store_remote_credentials.assert_called_once_with(
            names=["target1/cred1"], remote_credentials=BODY
        )

    def test_delete_then_unchanged(self):
        blade = _blade(creds=[("target1/cred1", KEY), ("target1/realm1::cred1", KEY)])
        module = _apply(blade, name="realm1::cred1", state="absent")
        assert _changed(module) is True
        module = _apply(blade, name="realm1::cred1", state="absent")
        assert _changed(module) is False
        blade.delete_object_store_remote_credentials.assert_called_once_with(
            names=["target1/realm1::cred1"]
        )
        assert _stored(blade) == {"target1/cred1": KEY}

    def test_absent_with_the_bare_name_keeps_the_realm_credential(self):
        blade = _blade(creds=[("target1/realm1::cred1", KEY)])
        assert _changed(_apply(blade, state="absent")) is False
        _no_writes(blade)

    def test_target_that_is_not_shared_with_the_realm(self):
        blade = _blade()
        module = _apply(blade, name="realm1::cred1", target="target2")
        assert _failure(module) == (
            "Failed to create remote credential target2/realm1::cred1. "
            "Error: Target 'target2' is not shared into realm 'realm1'."
        )

    def test_realm_that_does_not_exist(self):
        blade = _blade()
        module = _apply(blade, name="norealm::cred1")
        assert _failure(module) == (
            "Failed to create remote credential target1/norealm::cred1. "
            "Error: Realm does not exist."
        )

    def test_absent_in_a_realm_that_does_not_exist_is_unchanged(self):
        blade = _blade()
        module = _apply(blade, name="norealm::cred1", state="absent")
        assert _changed(module) is False

    def test_unknown_target_names_the_share(self):
        blade = _blade()
        module = _apply(blade, name="realm1::cred1", target="target9")
        assert _failure(module) == (
            "Selected target target9 is not connected, "
            "or is not visible to this user. A remote credential in a realm "
            "needs an S3 target that is shared with the realm."
        )
        _no_writes(blade)


class TestRealmScopedAdministrator:
    """An administrator whose management access is limited to realm1"""

    def test_qualified_name_works_for_the_whole_lifecycle(self):
        blade = _blade(realm_admin="realm1")
        assert _changed(_apply(blade, name="realm1::cred1")) is True
        assert _changed(_apply(blade, name="realm1::cred1")) is False
        module = _apply(blade, name="realm1::cred1", access_key=OTHER_KEY)
        assert _changed(module) is True
        assert _stored(blade) == {"target1/realm1::cred1": OTHER_KEY}
        module = _apply(blade, name="realm1::cred1", state="absent")
        assert _changed(module) is True
        module = _apply(blade, name="realm1::cred1", state="absent")
        assert _changed(module) is False

    def test_refused_fleet_read_adds_no_context(self):
        blade = _blade(realm_admin="realm1")
        _apply(blade, name="realm1::cred1")
        blade.get_arrays.assert_not_called()
        blade.post_object_store_remote_credentials.assert_called_once_with(
            names=["target1/realm1::cred1"], remote_credentials=BODY
        )

    def test_bare_name_is_refused_by_the_array(self):
        """The name is sent as given, never completed with the realm."""
        blade = _blade(realm_admin="realm1")
        assert _failure(_apply(blade)) == (
            "Failed to create remote credential target1/cred1. "
            "Error: Operation not permitted."
        )
        blade.post_object_store_remote_credentials.assert_called_once_with(
            names=["target1/cred1"], remote_credentials=BODY
        )

    def test_bare_leaf_of_a_realm_credential_is_not_resolved(self):
        blade = _blade(creds=[("target1/realm1::cred1", KEY)], realm_admin="realm1")
        module = _apply(blade, access_key=OTHER_KEY)
        assert "Operation not permitted." in _failure(module)
        assert _stored(blade) == {"target1/realm1::cred1": KEY}

    def test_absent_with_a_bare_name_is_unchanged(self):
        blade = _blade(creds=[("target1/cred1", KEY)], realm_admin="realm1")
        assert _changed(_apply(blade, state="absent")) is False
        assert _stored(blade) == {"target1/cred1": KEY}

    def test_target_that_is_not_shared_is_not_visible(self):
        blade = _blade(realm_admin="realm1")
        module = _apply(blade, name="realm1::cred1", target="target2")
        assert _failure(module) == (
            "Selected target target2 is not connected, "
            "or is not visible to this user. A remote credential in a realm "
            "needs an S3 target that is shared with the realm."
        )
        _no_writes(blade)

    def test_connected_array_is_not_visible(self):
        blade = _blade(realm_admin="realm1")
        module = _apply(blade, name="realm1::cred1", target="arrayb")
        assert "is not visible to this user" in _failure(module)
        _no_writes(blade)


class TestRefusedReads:
    """A read the array refuses fails the task with the array's message"""

    REFUSED = (
        "Operation not permitted. "
        "Authorization for 'read' on 'array-connections' is required."
    )

    def test_refused_read_of_the_array_connections(self):
        blade = _blade()
        blade.get_array_connections.side_effect = lambda **kw: _error(self.REFUSED, 403)
        assert _failure(_apply(blade)) == (
            "Failed to get array connections. Error: " + self.REFUSED
        )
        _no_writes(blade)

    def test_refused_read_of_the_array_connections_for_absent(self):
        blade = _blade(creds=[("target1/cred1", KEY)])
        blade.get_array_connections.side_effect = lambda **kw: _error(NOT_PERMITTED)
        module = _apply(blade, state="absent", check_mode=True)
        assert _failure(module) == (
            "Failed to get array connections. Error: Operation not permitted."
        )

    def test_refused_read_of_the_targets(self):
        blade = _blade()
        blade.get_targets.side_effect = lambda **kw: _error(NOT_PERMITTED)
        assert _failure(_apply(blade)) == (
            "Failed to get targets. Error: Operation not permitted."
        )
        _no_writes(blade)

    def test_refused_read_of_the_targets_in_check_mode(self):
        blade = _blade()
        blade.get_targets.side_effect = lambda **kw: _error(NOT_PERMITTED)
        module = _apply(blade, check_mode=True)
        assert "Failed to get targets." in _failure(module)

    def test_refused_read_of_the_credential_is_not_a_create(self):
        blade = _blade(creds=[("target1/cred1", OTHER_KEY)])
        blade.get_object_store_remote_credentials.side_effect = lambda **kw: _error(
            NOT_PERMITTED
        )
        assert _failure(_apply(blade)) == (
            "Failed to get remote credential target1/cred1. "
            "Error: Operation not permitted."
        )
        _no_writes(blade)

    def test_refused_read_of_the_credential_in_check_mode(self):
        blade = _blade()
        blade.get_object_store_remote_credentials.side_effect = lambda **kw: _error(
            NOT_PERMITTED
        )
        module = _apply(blade, name="realm1::cred1", check_mode=True)
        assert "Failed to get remote credential target1/realm1::cred1." in _failure(
            module
        )

    def test_refused_read_of_the_credential_is_not_absent(self):
        blade = _blade(creds=[("target1/cred1", KEY)])
        blade.get_object_store_remote_credentials.side_effect = lambda **kw: _error(
            NOT_PERMITTED
        )
        module = _apply(blade, state="absent")
        assert "Failed to get remote credential target1/cred1." in _failure(module)
        _no_writes(blade)

    def test_fleet_context_the_array_does_not_know(self):
        blade = _blade(creds=[("target1/cred1", KEY)])
        blade.get_array_connections.side_effect = lambda **kw: _error(
            "Cannot find array in fleet"
        )
        module = _apply(blade, state="absent", context="fb-west", check_mode=True)
        assert _failure(module) == (
            "Failed to get array connections. Error: Cannot find array in fleet"
        )
        blade.get_array_connections.assert_called_once_with(context_names=["fb-west"])
        _no_writes(blade)

    def test_only_does_not_exist_means_absent(self):
        blade = _blade()
        blade.get_object_store_remote_credentials.side_effect = lambda **kw: _error(
            ABSENT
        )
        assert _changed(_apply(blade, state="absent")) is False
        assert _changed(_apply(blade)) is True


def _requests(blade):
    """Every request of a run that takes a fleet context."""
    calls = []
    for method in (
        blade.get_array_connections,
        blade.get_targets,
        blade.get_object_store_remote_credentials,
        blade.post_object_store_remote_credentials,
        blade.patch_object_store_remote_credentials,
        blade.delete_object_store_remote_credentials,
    ):
        calls.extend(method.call_args_list)
    return calls


class TestContext:
    """The fleet context is sent with every request, from REST 2.17"""

    def test_context_on_every_request(self):
        blade = _blade(creds=[("target1/cred2", OTHER_KEY)])
        _apply(blade, context="fb-east")
        _apply(blade, name="cred2", context="fb-east")
        _apply(blade, name="cred2", state="absent", context="fb-east")
        requests = _requests(blade)
        assert len(requests) == 12
        for request in requests:
            assert request[1]["context_names"] == ["fb-east"]
        blade.get_fleets.assert_not_called()

    def test_fleet_member_uses_its_own_name(self):
        blade = _blade()
        local = Mock()
        local.name = "fb-local"
        blade.get_fleets.side_effect = lambda **kw: _valid([Mock()])
        blade.get_arrays.side_effect = lambda **kw: _valid([local])
        assert _changed(_apply(blade)) is True
        requests = _requests(blade)
        assert len(requests) == 4
        for request in requests:
            assert request[1]["context_names"] == ["fb-local"]

    def test_no_context_outside_a_fleet(self):
        blade = _blade()
        assert _changed(_apply(blade)) is True
        for request in _requests(blade):
            assert "context_names" not in request[1]
        blade.get_arrays.assert_not_called()

    def test_no_context_before_rest_2_17(self):
        blade = _blade(creds=[("target1/cred2", OTHER_KEY)])
        _apply(blade, context="fb-east", api_version="2.16")
        _apply(blade, name="cred2", context="fb-east", api_version="2.16")
        _apply(
            blade, name="cred2", state="absent", context="fb-east", api_version="2.16"
        )
        requests = _requests(blade)
        assert len(requests) == 12
        for request in requests:
            assert "context_names" not in request[1]
        blade.get_fleets.assert_not_called()


class TestModule:
    """Module plumbing and documentation"""

    def test_missing_sdk(self):
        module = _module()
        blade = _blade()
        _run(module, blade, has_sdk=False)
        assert _failure(module) == "py-pure-client sdk is required for this module"
        blade.get_array_connections.assert_not_called()

    def test_argument_spec(self):
        module = _module()
        ansible_module = _run(module, _blade())
        spec = ansible_module.call_args[0][0]
        assert spec["name"] == {"type": "str", "required": True}
        assert spec["target"] == {"type": "str", "required": True}
        assert spec["secret"]["no_log"] is True
        assert spec["state"]["choices"] == ["present", "absent"]
        assert ansible_module.call_args[1] == {
            "required_if": [["state", "present", ["access_key", "secret"]]],
            "supports_check_mode": True,
        }

    def test_examples_use_documented_options_only(self):
        documented = set(yaml.safe_load(purefb_remote_cred.DOCUMENTATION)["options"])
        documented.update(["fb_url", "api_token"])
        examples = yaml.safe_load(purefb_remote_cred.EXAMPLES)
        tasks = [
            task["everpure.flashblade.purefb_remote_cred"]
            for task in examples
            if "everpure.flashblade.purefb_remote_cred" in task
        ]
        assert len(tasks) >= 2
        for task in tasks:
            assert set(task) <= documented

    def test_examples_have_a_realm_credential(self):
        examples = yaml.safe_load(purefb_remote_cred.EXAMPLES)
        tasks = [
            task["everpure.flashblade.purefb_remote_cred"]
            for task in examples
            if "::" in task["everpure.flashblade.purefb_remote_cred"]["name"]
        ]
        assert tasks
        for task in tasks:
            assert "::" not in task["target"]

    def test_name_documents_the_realm_form(self):
        options = yaml.safe_load(purefb_remote_cred.DOCUMENTATION)["options"]
        assert "C(realm::name)" in " ".join(options["name"]["description"])

    def test_target_documents_what_it_names(self):
        options = yaml.safe_load(purefb_remote_cred.DOCUMENTATION)["options"]
        description = " ".join(options["target"]["description"])
        assert "initialize the S3 bucket" not in description
        assert "remote array" in description
        assert "S3 target" in description
        assert "never carries a realm prefix" in description
        assert "purefb_resource_access" in description

    def test_description_has_the_realm_administrator_rule(self):
        description = " ".join(
            yaml.safe_load(purefb_remote_cred.DOCUMENTATION)["description"]
        )
        assert "C(realm::name)" in description
        assert "A realm-scoped administrator must use the realm-qualified name" in (
            description
        )
