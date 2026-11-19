# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_fs_lock module."""

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

# The real vendored LooseVersion, so the version gates are exercised for real.
from plugins.module_utils.version import LooseVersion as RealLooseVersion
from plugins.modules.purefb_fs_lock import (
    main,
    _lock_kwargs,
    _under_path,
)

MOD = "plugins.modules.purefb_fs_lock"
REALM_FS = "realm1::fs1"
# What the array says for a file system it does not have, and for a lock
# request narrowed to a file system in a realm.
NO_FILE_SYSTEM = "File system does not exist."
REALM_REFUSAL = (
    " File system realm1::fs1 does exist, in realm realm1: the array refused "
    "a lock request narrowed to it."
)
# What the array says to an identity whose role may not read file systems:
# a refusal that does not say the name is missing.
NOT_PERMITTED = (
    "Operation not permitted. Authorization for 'get' on "
    "'purestorage.com/api/v2/file-systems' is required."
)
# What the array says to an administrator whose access is limited to a realm,
# for every lock, session and open file request.
REALM_ADMIN_REFUSED = "Operation not permitted."
# What the array says for a path or an inode the file system does not have.
NO_FILE = "File does not exist."


def _params(**overrides):
    params = {
        "state": "query",
        "target": None,
        "file_system": None,
        "path": None,
        "inode": None,
        "client": None,
        "user": None,
        "protocols": None,
        "recursive": False,
        "disruptive": False,
        "nlm_reclaim": False,
        "context": "",
    }
    params.update(overrides)
    return params


def _response(items=None, status=200):
    response = Mock()
    response.status_code = status
    response.items = list(items or [])
    response.errors = []
    return response


def _refused(message, status=400):
    """An array refusal carrying one error message."""
    response = _response(status=status)
    response.errors = [Mock(message=message)]
    return response


def _error_message(response, default="Unknown error"):
    """The message module_utils.common.get_error_message takes from a response."""
    errors = list(response.errors or [])
    return errors[0].message if errors else default


def _ref(name):
    ref = Mock()
    ref.name = name
    return ref


def _file_system(name, realm=None):
    """A file system as the array returns it: realms is empty outside a realm."""
    file_system = _ref(name)
    file_system.destroyed = False
    file_system.realms = []
    if realm:
        realm_ref = _ref(realm)
        realm_ref.resource_type = "realms"
        file_system.realms = [realm_ref]
    return file_system


def _lock(
    name, path="/build/output.db", client="10.0.0.1", inode=42, file_system="fs1"
):
    lock = _ref(name)
    lock.access_type = "exclusive"
    lock.client = _ref(client)
    lock.created_at = 1700000000000
    lock.inode = inode
    lock.path = path
    lock.protocol = "NLM"
    lock.range = Mock(length=0, offset=0)
    lock.source = _ref(file_system)
    return lock


def _session(name, client="10.0.0.1", user="alice", protocol="smb"):
    session = _ref(name)
    session.authentication = "NTLMv2"
    session.client = _ref(client)
    session.connection_time = 1700000000000
    session.idle_time = 5000
    session.opens = 2
    session.port = 51234
    session.protocol = protocol
    session.user = _ref(user)
    return session


def _open_file(file_id, path="/build/output.db", file_system="fs1"):
    open_file = Mock()
    open_file.id = file_id
    open_file.client = _ref("10.0.0.1")
    open_file.lock_count = 1
    open_file.mode = "rw"
    open_file.path = path
    open_file.session = _ref("session-1")
    open_file.source = _ref(file_system)
    open_file.user = _ref("alice")
    return open_file


def _blade(locks=(), clients=(), sessions=(), open_files=(), file_systems=None):
    """A mocked array that has the file system fs1 unless file_systems says otherwise."""
    blade = Mock()
    if file_systems is None:
        file_systems = [_file_system("fs1")]
    known = dict((file_system.name, file_system) for file_system in file_systems)

    def get_file_systems(names, **kwargs):
        # The array refuses a name it does not have, realm-qualified or not.
        if [name for name in names if name not in known]:
            return _refused(NO_FILE_SYSTEM)
        return _response([known[name] for name in names])

    blade.get_file_systems = Mock(side_effect=get_file_systems)
    blade.get_file_systems_locks.return_value = _response(locks)
    blade.get_file_systems_locks_clients.return_value = _response(
        [_ref(client) for client in clients]
    )
    blade.get_file_systems_sessions.return_value = _response(sessions)
    blade.get_file_systems_open_files.return_value = _response(open_files)
    blade.delete_file_systems_locks.return_value = _response()
    blade.delete_file_systems_sessions.return_value = _response()
    blade.delete_file_systems_open_files.return_value = _response()
    reclamation = Mock(start=1700000000000, end=1700000090000)
    blade.post_file_systems_locks_nlm_reclamations.return_value = _response(
        [reclamation]
    )
    return blade


def _run(params, blade, api_version="2.30", check_mode=False):
    """Run main() against a mocked array and return the AnsibleModule mock."""
    module = Mock()
    module.params = params
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    with patch(MOD + ".AnsibleModule", return_value=module), patch(
        MOD + ".get_system", return_value=blade
    ), patch(MOD + ".get_rest_api_version", return_value=api_version), patch(
        MOD + ".LooseVersion", RealLooseVersion
    ), patch(
        MOD + ".get_error_message", _error_message
    ):
        try:
            main()
        except SystemExit:
            pass
    return module


def _result(module):
    module.exit_json.assert_called_once()
    module.fail_json.assert_not_called()
    return module.exit_json.call_args[1]


def _failure(module):
    module.fail_json.assert_called_once()
    module.exit_json.assert_not_called()
    return module.fail_json.call_args[1]["msg"]


class TestPurefbFsLock:
    """Test cases for purefb_fs_lock module"""

    # ---------------- helpers ----------------

    def test_under_path_matches_the_file_and_its_subtree(self):
        assert _under_path("/build/output.db", ["/build/output.db"])
        assert _under_path("/build/sub/file", ["/build"])
        assert _under_path("/build/sub/file", ["/build/"])
        assert _under_path("/anything", ["/"])
        assert not _under_path("/builder/file", ["/build"])
        assert not _under_path(None, ["/build"])
        # The array may report a lock path without a leading slash.
        assert _under_path("build/sub/file", ["/build"])
        assert _under_path("/build/sub/file", ["build"])
        assert _under_path("/", ["/"])
        assert not _under_path("", ["/"])

    def test_lock_kwargs_recursive_get_drops_paths_and_delete_keeps_them(self):
        module = Mock()
        module.params = _params(
            file_system="fs1", path=["/build"], client=["10.0.0.1"], recursive=True
        )
        assert _lock_kwargs(module) == {
            "client_names": ["10.0.0.1"],
            "file_system_names": ["fs1"],
        }
        assert _lock_kwargs(module, for_delete=True) == {
            "client_names": ["10.0.0.1"],
            "file_system_names": ["fs1"],
            "paths": ["/build"],
            "recursive": True,
        }

    # ---------------- listing ----------------

    def test_list_all_returns_every_kind(self):
        blade = _blade(
            locks=[_lock("lock1")],
            clients=["10.0.0.1"],
            sessions=[_session("sess1")],
            open_files=[_open_file("of1")],
        )
        result = _result(_run(_params(), blade))
        assert result["changed"] is False
        assert result["locks"] == {
            "lock1": {
                "access_type": "exclusive",
                "client": "10.0.0.1",
                "created_at": 1700000000000,
                "file_system": "fs1",
                "inode": 42,
                "path": "/build/output.db",
                "protocol": "NLM",
                "range": {"length": 0, "offset": 0},
            }
        }
        assert result["lock_clients"] == ["10.0.0.1"]
        assert result["sessions"] == {
            "sess1": {
                "authentication": "NTLMv2",
                "client": "10.0.0.1",
                "connection_time": 1700000000000,
                "idle_time": 5000,
                "opens": 2,
                "port": 51234,
                "protocol": "smb",
                "user": "alice",
            }
        }
        assert result["open_files"] == {
            "of1": {
                "client": "10.0.0.1",
                "file_system": "fs1",
                "lock_count": 1,
                "mode": "rw",
                "path": "/build/output.db",
                "session": "session-1",
                "user": "alice",
            }
        }
        blade.get_file_systems_locks.assert_called_once_with()
        blade.get_file_systems_locks_clients.assert_called_once_with()
        blade.get_file_systems_sessions.assert_called_once_with()
        blade.get_file_systems_open_files.assert_called_once_with(protocols=["smb"])

    def test_list_all_at_2_8_lists_locks_only(self):
        blade = _blade()
        result = _result(_run(_params(), blade, api_version="2.8"))
        assert result["locks"] == {} and result["lock_clients"] == []
        assert "sessions" not in result and "open_files" not in result
        blade.get_file_systems_sessions.assert_not_called()
        blade.get_file_systems_open_files.assert_not_called()

    def test_list_all_at_2_10_adds_sessions_but_not_open_files(self):
        blade = _blade()
        result = _result(_run(_params(), blade, api_version="2.10"))
        assert "sessions" in result and "open_files" not in result
        blade.get_file_systems_sessions.assert_called_once_with()
        blade.get_file_systems_open_files.assert_not_called()

    def test_list_all_file_system_filter_skips_sessions(self):
        blade = _blade()
        result = _result(_run(_params(file_system="fs1", path=["/build"]), blade))
        assert "locks" in result and "open_files" in result
        assert "sessions" not in result
        blade.get_file_systems_locks.assert_called_once_with(
            file_system_names=["fs1"], paths=["/build"]
        )
        blade.get_file_systems_open_files.assert_called_once_with(
            protocols=["smb"], file_system_names=["fs1"], paths=["/build"]
        )
        blade.get_file_systems_sessions.assert_not_called()

    def test_list_all_user_filter_skips_locks(self):
        blade = _blade()
        result = _result(_run(_params(user=["alice"]), blade))
        assert "locks" not in result and "lock_clients" not in result
        assert "sessions" in result and "open_files" in result
        blade.get_file_systems_locks.assert_not_called()
        blade.get_file_systems_sessions.assert_called_once_with(user_names=["alice"])
        blade.get_file_systems_open_files.assert_called_once_with(
            protocols=["smb"], user_names=["alice"]
        )

    def test_list_all_nfs_protocols_lists_sessions_only(self):
        blade = _blade()
        result = _result(_run(_params(protocols=["nfs"]), blade))
        assert list(result) == ["changed", "sessions"]
        blade.get_file_systems_sessions.assert_called_once_with(protocols=["nfs"])
        blade.get_file_systems_open_files.assert_not_called()

    def test_list_all_with_context_passes_it_and_skips_open_files(self):
        blade = _blade()
        result = _result(_run(_params(context="fb2"), blade))
        assert "open_files" not in result
        blade.get_file_systems_locks.assert_called_once_with(context_names=["fb2"])
        blade.get_file_systems_locks_clients.assert_called_once_with(
            context_names=["fb2"]
        )
        blade.get_file_systems_sessions.assert_called_once_with(context_names=["fb2"])
        blade.get_file_systems_open_files.assert_not_called()

    def test_list_all_fails_when_no_kind_accepts_the_filters(self):
        blade = _blade()
        msg = _failure(
            _run(_params(file_system="fs1", inode=[42], user=["alice"]), blade)
        )
        assert "None of locks, sessions or open files" in msg
        blade.get_file_systems_locks.assert_not_called()
        blade.get_file_systems_sessions.assert_not_called()
        blade.get_file_systems_open_files.assert_not_called()

    def test_list_all_user_filter_at_2_8_fails_instead_of_returning_nothing(self):
        blade = _blade()
        msg = _failure(_run(_params(user=["alice"]), blade, api_version="2.8"))
        assert "None of locks, sessions or open files" in msg
        blade.get_file_systems_locks.assert_not_called()
        blade.get_file_systems_sessions.assert_not_called()

    def test_list_locks_target_maps_the_filters(self):
        blade = _blade(locks=[_lock("lock1")], clients=["10.0.0.1", "10.0.0.2"])
        result = _result(
            _run(
                _params(
                    target="locks",
                    file_system="fs1",
                    inode=[42],
                    client=["10.0.0.1"],
                ),
                blade,
            )
        )
        assert result["changed"] is False
        assert list(result["locks"]) == ["lock1"]
        assert result["lock_clients"] == ["10.0.0.1", "10.0.0.2"]
        assert "sessions" not in result and "open_files" not in result
        blade.get_file_systems_locks.assert_called_once_with(
            client_names=["10.0.0.1"], file_system_names=["fs1"], inodes=[42]
        )
        blade.get_file_systems_sessions.assert_not_called()

    def test_list_locks_recursive_narrows_client_side(self):
        blade = _blade(
            locks=[
                _lock("in", path="/build/a"),
                _lock("deep", path="/build/sub/b"),
                _lock("out", path="/builder/c"),
                _lock("unresolved", path=None),
            ]
        )
        result = _result(
            _run(
                _params(
                    target="locks", file_system="fs1", path=["/build"], recursive=True
                ),
                blade,
            )
        )
        assert sorted(result["locks"]) == ["deep", "in"]
        blade.get_file_systems_locks.assert_called_once_with(file_system_names=["fs1"])

    def test_list_locks_recursive_matches_a_path_without_a_leading_slash(self):
        blade = _blade(locks=[_lock("bare", path="build/sub/b")])
        result = _result(
            _run(
                _params(
                    target="locks", file_system="fs1", path=["/build/"], recursive=True
                ),
                blade,
            )
        )
        assert list(result["locks"]) == ["bare"]
        assert result["locks"]["bare"]["path"] == "build/sub/b"

    def test_list_locks_without_a_range(self):
        lock = _lock("lock1")
        lock.range = None
        result = _result(_run(_params(target="locks"), _blade(locks=[lock])))
        assert result["locks"]["lock1"]["range"] is None

    def test_list_sessions_target_maps_the_filters(self):
        blade = _blade(sessions=[_session("sess1")])
        result = _result(
            _run(
                _params(
                    target="sessions",
                    client=["10.0.0.1"],
                    user=["alice"],
                    protocols=["smb"],
                ),
                blade,
            )
        )
        assert list(result) == ["changed", "sessions"]
        blade.get_file_systems_sessions.assert_called_once_with(
            client_names=["10.0.0.1"], user_names=["alice"], protocols=["smb"]
        )
        blade.get_file_systems_locks.assert_not_called()

    def test_list_open_files_target_passes_protocols_as_given(self):
        blade = _blade()
        result = _result(
            _run(
                _params(target="open_files", file_system="fs1", protocols=["nfs"]),
                blade,
            )
        )
        assert list(result) == ["changed", "open_files"]
        blade.get_file_systems_open_files.assert_called_once_with(
            protocols=["nfs"], file_system_names=["fs1"]
        )

    def test_list_open_files_target_defaults_to_smb(self):
        blade = _blade(open_files=[_open_file("of1")])
        result = _result(
            _run(
                _params(target="open_files", client=["10.0.0.1"], path=["/x"]),
                blade,
            )
        )
        assert list(result["open_files"]) == ["of1"]
        blade.get_file_systems_open_files.assert_called_once_with(
            protocols=["smb"], client_names=["10.0.0.1"], paths=["/x"]
        )

    def test_list_fails_on_api_error(self):
        blade = _blade()
        blade.get_file_systems_locks.return_value = _response(status=400)
        msg = _failure(_run(_params(target="locks"), blade))
        assert "Failed to list file locks" in msg

    # ---------------- clearing locks ----------------

    def test_clear_locks_deletes_the_matching_locks(self):
        blade = _blade(locks=[_lock("lock1")])
        result = _result(
            _run(
                _params(
                    state="absent",
                    target="locks",
                    file_system="fs1",
                    path=["/build/output.db"],
                    client=["10.0.0.1"],
                ),
                blade,
            )
        )
        assert result["changed"] is True
        assert list(result["locks"]) == ["lock1"]
        blade.delete_file_systems_locks.assert_called_once_with(
            client_names=["10.0.0.1"],
            file_system_names=["fs1"],
            paths=["/build/output.db"],
        )

    def test_clear_locks_is_a_noop_when_none_match(self):
        blade = _blade()
        result = _result(
            _run(
                _params(
                    state="absent",
                    target="locks",
                    file_system="fs1",
                    path=["/build/output.db"],
                ),
                blade,
            )
        )
        assert result["changed"] is False
        assert result["locks"] == {}
        blade.delete_file_systems_locks.assert_not_called()

    def test_clear_locks_check_mode_reports_without_deleting(self):
        blade = _blade(locks=[_lock("lock1")])
        result = _result(
            _run(
                _params(
                    state="absent",
                    target="locks",
                    file_system="fs1",
                    path=["/build/output.db"],
                ),
                blade,
                check_mode=True,
            )
        )
        assert result["changed"] is True
        assert list(result["locks"]) == ["lock1"]
        blade.delete_file_systems_locks.assert_not_called()

    def test_clear_locks_recursive_sends_paths_and_recursive(self):
        blade = _blade(locks=[_lock("deep", path="/build/sub/b")])
        result = _result(
            _run(
                _params(
                    state="absent",
                    target="locks",
                    file_system="fs1",
                    path=["/build"],
                    recursive=True,
                    context="fb2",
                ),
                blade,
            )
        )
        assert result["changed"] is True
        blade.get_file_systems_locks.assert_called_once_with(
            file_system_names=["fs1"], context_names=["fb2"]
        )
        blade.delete_file_systems_locks.assert_called_once_with(
            file_system_names=["fs1"],
            paths=["/build"],
            recursive=True,
            context_names=["fb2"],
        )

    def test_clear_locks_recursive_counts_a_path_without_a_leading_slash(self):
        blade = _blade(locks=[_lock("bare", path="build/sub/b")])
        result = _result(
            _run(
                _params(
                    state="absent",
                    target="locks",
                    file_system="fs1",
                    path=["/build"],
                    recursive=True,
                ),
                blade,
            )
        )
        assert result["changed"]
        assert list(result["locks"]) == ["bare"]
        blade.delete_file_systems_locks.assert_called_once_with(
            file_system_names=["fs1"], paths=["/build"], recursive=True
        )

    def test_clear_locks_requires_client_or_file_system(self):
        blade = _blade()
        msg = _failure(_run(_params(state="absent", target="locks"), blade))
        assert "requires client or file_system" in msg
        blade.get_file_systems_locks.assert_not_called()

    def test_clear_locks_by_file_system_needs_2_10(self):
        blade = _blade(locks=[_lock("lock1")])
        msg = _failure(
            _run(
                _params(
                    state="absent",
                    target="locks",
                    file_system="fs1",
                    path=["/build/output.db"],
                ),
                blade,
                api_version="2.8",
            )
        )
        assert "2.10" in msg
        blade.get_file_systems_locks.assert_not_called()
        blade.delete_file_systems_locks.assert_not_called()

    def test_clear_locks_by_client_works_at_2_8(self):
        blade = _blade(locks=[_lock("lock1")])
        result = _result(
            _run(
                _params(state="absent", target="locks", client=["10.0.0.1"]),
                blade,
                api_version="2.8",
            )
        )
        assert result["changed"] is True
        blade.delete_file_systems_locks.assert_called_once_with(
            client_names=["10.0.0.1"]
        )

    def test_clear_locks_fails_on_delete_error(self):
        blade = _blade(locks=[_lock("lock1")])
        blade.delete_file_systems_locks.return_value = _response(status=400)
        msg = _failure(
            _run(
                _params(
                    state="absent",
                    target="locks",
                    file_system="fs1",
                    path=["/build/output.db"],
                ),
                blade,
            )
        )
        assert "Failed to clear file locks" in msg

    # ---------------- closing sessions ----------------

    def test_clear_sessions_deletes_the_matching_sessions(self):
        blade = _blade(sessions=[_session("sess1")])
        result = _result(
            _run(
                _params(
                    state="absent",
                    target="sessions",
                    client=["10.0.0.1"],
                    protocols=["smb"],
                ),
                blade,
            )
        )
        assert result["changed"] is True
        assert list(result["sessions"]) == ["sess1"]
        blade.delete_file_systems_sessions.assert_called_once_with(
            client_names=["10.0.0.1"], protocols=["smb"]
        )

    def test_clear_sessions_single_filter_requires_disruptive(self):
        blade = _blade(sessions=[_session("sess1")])
        msg = _failure(
            _run(_params(state="absent", target="sessions", client=["10.0.0.1"]), blade)
        )
        assert "disruptive" in msg
        blade.get_file_systems_sessions.assert_not_called()
        blade.delete_file_systems_sessions.assert_not_called()

    def test_clear_sessions_single_filter_with_disruptive_sends_the_flag(self):
        blade = _blade(sessions=[_session("sess1")])
        result = _result(
            _run(
                _params(
                    state="absent",
                    target="sessions",
                    client=["10.0.0.1"],
                    disruptive=True,
                ),
                blade,
            )
        )
        assert result["changed"] is True
        blade.get_file_systems_sessions.assert_called_once_with(
            client_names=["10.0.0.1"]
        )
        blade.delete_file_systems_sessions.assert_called_once_with(
            client_names=["10.0.0.1"], disruptive=True
        )

    def test_clear_sessions_requires_a_filter(self):
        blade = _blade()
        msg = _failure(_run(_params(state="absent", target="sessions"), blade))
        assert "at least one of client, user or protocols" in msg

    def test_clear_sessions_is_a_noop_when_none_match(self):
        blade = _blade()
        result = _result(
            _run(
                _params(
                    state="absent",
                    target="sessions",
                    user=["alice"],
                    protocols=["nfs"],
                ),
                blade,
            )
        )
        assert result["changed"] is False
        assert result["sessions"] == {}
        blade.delete_file_systems_sessions.assert_not_called()

    def test_clear_sessions_check_mode_reports_without_deleting(self):
        blade = _blade(sessions=[_session("sess1")])
        result = _result(
            _run(
                _params(
                    state="absent",
                    target="sessions",
                    user=["alice"],
                    protocols=["nfs"],
                ),
                blade,
                check_mode=True,
            )
        )
        assert result["changed"] is True
        blade.delete_file_systems_sessions.assert_not_called()

    def test_clear_sessions_fails_on_delete_error(self):
        blade = _blade(sessions=[_session("sess1")])
        blade.delete_file_systems_sessions.return_value = _response(status=400)
        msg = _failure(
            _run(
                _params(
                    state="absent",
                    target="sessions",
                    user=["alice"],
                    protocols=["nfs"],
                ),
                blade,
            )
        )
        assert "Failed to close file sessions" in msg

    def test_sessions_need_2_10(self):
        blade = _blade()
        msg = _failure(
            _run(_params(target="sessions", client=["10.0.0.1"]), blade, "2.8")
        )
        assert "2.10" in msg
        blade.get_file_systems_sessions.assert_not_called()

    # ---------------- closing open files ----------------

    def test_close_open_files_deletes_by_id(self):
        blade = _blade(open_files=[_open_file("of2"), _open_file("of1")])
        result = _result(
            _run(
                _params(state="absent", target="open_files", file_system="fs1"),
                blade,
            )
        )
        assert result["changed"] is True
        assert sorted(result["open_files"]) == ["of1", "of2"]
        blade.get_file_systems_open_files.assert_called_once_with(
            protocols=["smb"], file_system_names=["fs1"]
        )
        blade.delete_file_systems_open_files.assert_called_once_with(ids=["of1", "of2"])

    def test_close_open_files_is_a_noop_when_none_match(self):
        blade = _blade()
        result = _result(
            _run(
                _params(state="absent", target="open_files", file_system="fs1"),
                blade,
            )
        )
        assert result["changed"] is False
        assert result["open_files"] == {}
        blade.delete_file_systems_open_files.assert_not_called()

    def test_close_open_files_check_mode_reports_without_deleting(self):
        blade = _blade(open_files=[_open_file("of1")])
        result = _result(
            _run(
                _params(state="absent", target="open_files", user=["alice"]),
                blade,
                check_mode=True,
            )
        )
        assert result["changed"] is True
        blade.delete_file_systems_open_files.assert_not_called()

    def test_close_open_files_requires_a_narrowing_filter(self):
        blade = _blade()
        msg = _failure(
            _run(
                _params(state="absent", target="open_files", protocols=["smb"]),
                blade,
            )
        )
        assert "at least one of file_system, path, client or user" in msg
        blade.get_file_systems_open_files.assert_not_called()

    def test_close_open_files_fails_on_delete_error(self):
        blade = _blade(open_files=[_open_file("of1")])
        blade.delete_file_systems_open_files.return_value = _response(status=400)
        msg = _failure(
            _run(
                _params(state="absent", target="open_files", file_system="fs1"),
                blade,
            )
        )
        assert "Failed to close open files" in msg

    def test_open_files_need_2_17(self):
        blade = _blade()
        msg = _failure(
            _run(_params(target="open_files", file_system="fs1"), blade, "2.10")
        )
        assert "2.17" in msg
        blade.get_file_systems_open_files.assert_not_called()

    def test_open_files_reject_context(self):
        blade = _blade()
        msg = _failure(
            _run(_params(target="open_files", file_system="fs1", context="fb2"), blade)
        )
        assert "context is not supported for open files" in msg

    def test_open_files_reject_inode(self):
        blade = _blade()
        msg = _failure(
            _run(_params(target="open_files", file_system="fs1", inode=[42]), blade)
        )
        assert "inode does not apply to target=open_files" in msg

    # ---------------- NLM reclamation ----------------

    def test_nlm_reclaim_posts_and_returns_the_window(self):
        blade = _blade()
        result = _result(_run(_params(state="absent", nlm_reclaim=True), blade))
        assert result["changed"] is True
        assert result["nlm_reclamation"] == {
            "end": 1700000090000,
            "start": 1700000000000,
        }
        blade.post_file_systems_locks_nlm_reclamations.assert_called_once_with()

    def test_nlm_reclaim_check_mode_sends_nothing(self):
        blade = _blade()
        result = _result(
            _run(_params(state="absent", nlm_reclaim=True), blade, check_mode=True)
        )
        assert result["changed"] is True
        assert result["nlm_reclamation"] == {}
        blade.post_file_systems_locks_nlm_reclamations.assert_not_called()

    def test_nlm_reclaim_passes_the_context(self):
        blade = _blade()
        _result(_run(_params(state="absent", nlm_reclaim=True, context="fb2"), blade))
        blade.post_file_systems_locks_nlm_reclamations.assert_called_once_with(
            context_names=["fb2"]
        )

    def test_nlm_reclaim_requires_state_absent(self):
        blade = _blade()
        msg = _failure(_run(_params(nlm_reclaim=True), blade))
        assert "state=absent" in msg
        blade.post_file_systems_locks_nlm_reclamations.assert_not_called()

    def test_nlm_reclaim_rejects_target_and_filters(self):
        blade = _blade()
        msg = _failure(
            _run(_params(state="absent", nlm_reclaim=True, target="locks"), blade)
        )
        assert "array-wide" in msg
        msg = _failure(
            _run(_params(state="absent", nlm_reclaim=True, client=["1.2.3.4"]), blade)
        )
        assert "array-wide" in msg
        blade.post_file_systems_locks_nlm_reclamations.assert_not_called()

    def test_nlm_reclaim_fails_on_api_error(self):
        blade = _blade()
        blade.post_file_systems_locks_nlm_reclamations.return_value = _response(
            status=400
        )
        msg = _failure(_run(_params(state="absent", nlm_reclaim=True), blade))
        assert "Failed to start NLM reclamation" in msg

    # ---------------- option and version checks ----------------

    def test_absent_requires_a_target(self):
        blade = _blade()
        msg = _failure(_run(_params(state="absent"), blade))
        assert "target is required" in msg

    def test_filter_that_does_not_apply_to_the_target_fails(self):
        blade = _blade()
        msg = _failure(_run(_params(target="locks", user=["alice"]), blade))
        assert "user does not apply to target=locks" in msg
        msg = _failure(_run(_params(target="sessions", file_system="fs1"), blade))
        assert "file_system does not apply to target=sessions" in msg
        blade.get_file_systems_locks.assert_not_called()
        blade.get_file_systems_sessions.assert_not_called()

    def test_recursive_requires_path(self):
        blade = _blade()
        msg = _failure(_run(_params(recursive=True), blade))
        assert "recursive requires path" in msg

    def test_recursive_applies_to_locks_only(self):
        blade = _blade()
        msg = _failure(
            _run(
                _params(
                    target="open_files", file_system="fs1", path=["/x"], recursive=True
                ),
                blade,
            )
        )
        assert "recursive applies to locks only" in msg

    def test_rest_version_below_2_8_is_refused(self):
        blade = _blade()
        msg = _failure(_run(_params(), blade, api_version="2.7"))
        assert "REST version not supported" in msg
        blade.get_file_systems_locks.assert_not_called()

    def test_context_needs_2_22(self):
        blade = _blade()
        msg = _failure(_run(_params(context="fb2"), blade, api_version="2.21"))
        assert "context requires FlashBlade REST API version 2.22" in msg
        blade.get_file_systems_locks.assert_not_called()

    # ---------------- locks on a file system in a realm ----------------

    def test_list_locks_realm_file_system_refusal_names_the_realm(self):
        blade = _blade(file_systems=[_file_system(REALM_FS, realm="realm1")])
        blade.get_file_systems_locks.return_value = _refused(NO_FILE_SYSTEM)
        msg = _failure(_run(_params(target="locks", file_system=REALM_FS), blade))
        assert msg == (
            "Failed to list file locks. Error: " + NO_FILE_SYSTEM + REALM_REFUSAL
        )
        blade.get_file_systems_locks.assert_called_once_with(
            file_system_names=[REALM_FS]
        )
        blade.get_file_systems.assert_called_once_with(names=[REALM_FS])
        blade.get_file_systems_locks_clients.assert_not_called()

    def test_list_all_realm_file_system_refusal_names_the_realm(self):
        blade = _blade(file_systems=[_file_system(REALM_FS, realm="realm1")])
        blade.get_file_systems_locks.return_value = _refused(NO_FILE_SYSTEM)
        msg = _failure(_run(_params(file_system=REALM_FS), blade))
        assert msg.endswith(REALM_REFUSAL)
        blade.get_file_systems_open_files.assert_not_called()

    def test_list_locks_realm_refusal_looks_up_in_the_same_context(self):
        blade = _blade(file_systems=[_file_system(REALM_FS, realm="realm1")])
        blade.get_file_systems_locks.return_value = _refused(NO_FILE_SYSTEM)
        msg = _failure(
            _run(_params(target="locks", file_system=REALM_FS, context="fb2"), blade)
        )
        assert msg.endswith(REALM_REFUSAL)
        blade.get_file_systems.assert_called_once_with(
            names=[REALM_FS], context_names=["fb2"]
        )

    def test_clear_locks_realm_file_system_refusal_names_the_realm(self):
        for check_mode in (False, True):
            blade = _blade(file_systems=[_file_system(REALM_FS, realm="realm1")])
            blade.get_file_systems_locks.return_value = _refused(NO_FILE_SYSTEM)
            msg = _failure(
                _run(
                    _params(
                        state="absent",
                        target="locks",
                        file_system=REALM_FS,
                        path=["/"],
                        recursive=True,
                    ),
                    blade,
                    check_mode=check_mode,
                )
            )
            assert msg == (
                "Failed to list file locks. Error: " + NO_FILE_SYSTEM + REALM_REFUSAL
            )
            blade.delete_file_systems_locks.assert_not_called()

    def test_clear_locks_realm_file_system_delete_refusal_names_the_realm(self):
        blade = _blade(
            locks=[_lock("lock1", file_system=REALM_FS)],
            file_systems=[_file_system(REALM_FS, realm="realm1")],
        )
        blade.delete_file_systems_locks.return_value = _refused(NO_FILE_SYSTEM)
        msg = _failure(
            _run(
                _params(
                    state="absent",
                    target="locks",
                    file_system=REALM_FS,
                    path=["/build/output.db"],
                ),
                blade,
            )
        )
        assert msg == (
            "Failed to clear file locks. Error: " + NO_FILE_SYSTEM + REALM_REFUSAL
        )

    def test_locks_realm_file_system_is_passed_through_when_the_array_serves_it(self):
        blade = _blade(
            locks=[_lock("lock1", file_system=REALM_FS)],
            file_systems=[_file_system(REALM_FS, realm="realm1")],
        )
        params = _params(
            target="locks", file_system=REALM_FS, path=["/build/output.db"]
        )
        result = _result(_run(params, blade))
        assert result["locks"]["lock1"]["file_system"] == REALM_FS
        blade.get_file_systems_locks.assert_called_once_with(
            file_system_names=[REALM_FS], paths=["/build/output.db"]
        )
        result = _result(_run(dict(params, state="absent"), blade))
        assert result["changed"] is True
        blade.delete_file_systems_locks.assert_called_once_with(
            file_system_names=[REALM_FS], paths=["/build/output.db"]
        )
        # A lock request the array serves is never preceded by a lookup.
        blade.get_file_systems.assert_not_called()

    def test_list_locks_missing_file_system_relays_the_array_error(self):
        blade = _blade(file_systems=[])
        blade.get_file_systems_locks.return_value = _refused(NO_FILE_SYSTEM)
        msg = _failure(_run(_params(target="locks", file_system="nope"), blade))
        assert msg == "Failed to list file locks. Error: " + NO_FILE_SYSTEM
        blade.get_file_systems.assert_called_once_with(names=["nope"])

    def test_list_locks_bare_name_does_not_match_a_realm_file_system(self):
        blade = _blade(file_systems=[_file_system(REALM_FS, realm="realm1")])
        blade.get_file_systems_locks.return_value = _refused(NO_FILE_SYSTEM)
        msg = _failure(_run(_params(target="locks", file_system="fs1"), blade))
        assert msg == "Failed to list file locks. Error: " + NO_FILE_SYSTEM

    def test_list_locks_unknown_realm_relays_the_array_error(self):
        blade = _blade(file_systems=[])
        blade.get_file_systems_locks.return_value = _refused("Realm does not exist.")
        msg = _failure(_run(_params(target="locks", file_system="norealm::fs1"), blade))
        assert msg == "Failed to list file locks. Error: Realm does not exist."
        blade.get_file_systems.assert_not_called()

    def test_list_locks_other_failure_on_a_realm_file_system_is_relayed(self):
        blade = _blade(file_systems=[_file_system(REALM_FS, realm="realm1")])
        blade.get_file_systems_locks.return_value = _response(status=500)
        msg = _failure(_run(_params(target="locks", file_system=REALM_FS), blade))
        assert msg == "Failed to list file locks. Error: Unknown error"
        blade.get_file_systems.assert_not_called()

    def test_lock_refusal_of_a_file_system_outside_a_realm_says_it_exists(self):
        # No array has been seen to answer this way for a file system outside
        # a realm; if one does, the file system is still reported as existing
        # and no realm is named.
        blade = _blade()
        blade.get_file_systems_locks.return_value = _refused(NO_FILE_SYSTEM)
        msg = _failure(_run(_params(target="locks", file_system="fs1"), blade))
        assert msg == (
            "Failed to list file locks. Error: " + NO_FILE_SYSTEM + " File system "
            "fs1 does exist: the array refused a lock request narrowed to it."
        )
        assert "realm" not in msg
        blade.get_file_systems.assert_called_once_with(names=["fs1"])

    def test_lock_refusal_is_relayed_when_the_lookup_is_refused_too(self):
        blade = _blade(file_systems=[_file_system(REALM_FS, realm="realm1")])
        blade.get_file_systems_locks.return_value = _refused(NO_FILE_SYSTEM)
        blade.get_file_systems = Mock(return_value=_refused(NOT_PERMITTED))
        module = _run(_params(target="locks", file_system=REALM_FS), blade)
        assert _failure(module) == "Failed to list file locks. Error: " + NO_FILE_SYSTEM
        module.warn.assert_not_called()

    def test_lock_refusal_of_a_destroyed_realm_file_system_is_relayed(self):
        # A destroyed file system is still returned by its name until it is
        # eradicated; saying that it exists would mislead.
        destroyed = _file_system(REALM_FS, realm="realm1")
        destroyed.destroyed = True
        blade = _blade(file_systems=[destroyed])
        blade.get_file_systems_locks.return_value = _refused(NO_FILE_SYSTEM)
        msg = _failure(_run(_params(target="locks", file_system=REALM_FS), blade))
        assert msg == "Failed to list file locks. Error: " + NO_FILE_SYSTEM
        blade.get_file_systems.assert_called_once_with(names=[REALM_FS])

    def test_locks_refused_to_a_realm_administrator_are_relayed(self):
        # The array refuses the realm's own administrator; that is not a
        # missing file system, so nothing is looked up or added.
        params = _params(target="locks", file_system=REALM_FS)
        clear = dict(params, state="absent", path=["/"], recursive=True)
        for case, check_mode in ((params, False), (clear, False), (clear, True)):
            blade = _blade(file_systems=[_file_system(REALM_FS, realm="realm1")])
            blade.get_file_systems_locks.return_value = _refused(REALM_ADMIN_REFUSED)
            module = _run(case, blade, check_mode=check_mode)
            assert _failure(module) == (
                "Failed to list file locks. Error: " + REALM_ADMIN_REFUSED
            )
            blade.get_file_systems.assert_not_called()
            blade.delete_file_systems_locks.assert_not_called()

    def test_list_locks_missing_path_or_inode_is_relayed_without_a_lookup(self):
        # "File does not exist." is about the path or the inode, not about
        # the file system.
        for narrow in ({"path": ["/nope"]}, {"inode": [999999999]}):
            blade = _blade()
            blade.get_file_systems_locks.return_value = _refused(NO_FILE)
            msg = _failure(
                _run(_params(target="locks", file_system="fs1", **narrow), blade)
            )
            assert msg == "Failed to list file locks. Error: " + NO_FILE
            blade.get_file_systems.assert_not_called()

    def test_list_locks_array_level_file_system_needs_no_lookup(self):
        blade = _blade(locks=[_lock("lock1")])
        result = _result(_run(_params(target="locks", file_system="fs1"), blade))
        assert list(result["locks"]) == ["lock1"]
        blade.get_file_systems_locks.assert_called_once_with(file_system_names=["fs1"])
        blade.get_file_systems.assert_not_called()

    # ---------------- open files: the file system is checked first ----------------

    def test_list_open_files_missing_file_system_fails(self):
        blade = _blade(file_systems=[])
        msg = _failure(_run(_params(target="open_files", file_system="nope"), blade))
        assert msg == (
            "Failed to list open files. File system nope was not found. "
            "Error: File system does not exist."
        )
        blade.get_file_systems.assert_called_once_with(names=["nope"])
        blade.get_file_systems_open_files.assert_not_called()

    def test_list_open_files_unknown_realm_fails(self):
        # The array answers the same way for a realm it does not have.
        blade = _blade(file_systems=[_file_system(REALM_FS, realm="realm1")])
        msg = _failure(
            _run(_params(target="open_files", file_system="norealm::fs1"), blade)
        )
        assert "File system norealm::fs1 was not found" in msg
        blade.get_file_systems_open_files.assert_not_called()

    def test_list_open_files_bare_name_does_not_match_a_realm_file_system(self):
        blade = _blade(file_systems=[_file_system(REALM_FS, realm="realm1")])
        msg = _failure(_run(_params(target="open_files", file_system="fs1"), blade))
        assert "File system fs1 was not found" in msg
        blade.get_file_systems_open_files.assert_not_called()

    def test_list_open_files_answer_without_the_file_system_fails(self):
        # The array answers an administrator limited to a realm this way for
        # a file system outside the realm: it exists, but not for the caller.
        blade = _blade()
        blade.get_file_systems = Mock(return_value=_response())
        module = _run(_params(target="open_files", file_system="fs1"), blade)
        assert _failure(module) == (
            "Failed to list open files. File system fs1 was not found."
        )
        module.warn.assert_not_called()
        blade.get_file_systems_open_files.assert_not_called()

    def test_close_open_files_missing_file_system_fails(self):
        for check_mode in (False, True):
            blade = _blade(open_files=[_open_file("of1")], file_systems=[])
            msg = _failure(
                _run(
                    _params(state="absent", target="open_files", file_system="nope"),
                    blade,
                    check_mode=check_mode,
                )
            )
            assert "File system nope was not found" in msg
            blade.get_file_systems_open_files.assert_not_called()
            blade.delete_file_systems_open_files.assert_not_called()

    def test_list_all_missing_file_system_fails_at_the_open_files(self):
        # user skips the locks and file_system skips the sessions, so only the
        # open files are left to list, and their GET does not check the name.
        blade = _blade(file_systems=[])
        msg = _failure(_run(_params(file_system="nope", user=["alice"]), blade))
        assert "File system nope was not found" in msg
        blade.get_file_systems_locks.assert_not_called()
        blade.get_file_systems_open_files.assert_not_called()

    def test_open_files_realm_file_system_is_listed_and_closed(self):
        blade = _blade(
            open_files=[_open_file("of1", file_system=REALM_FS)],
            file_systems=[_file_system(REALM_FS, realm="realm1")],
        )
        params = _params(target="open_files", file_system=REALM_FS)
        result = _result(_run(params, blade))
        assert result["changed"] is False
        assert result["open_files"]["of1"]["file_system"] == REALM_FS
        blade.get_file_systems.assert_called_once_with(names=[REALM_FS])
        blade.get_file_systems_open_files.assert_called_once_with(
            protocols=["smb"], file_system_names=[REALM_FS]
        )
        result = _result(_run(dict(params, state="absent"), blade))
        assert result["changed"] is True
        blade.delete_file_systems_open_files.assert_called_once_with(ids=["of1"])

    def test_open_files_array_level_file_system_is_checked_then_listed(self):
        blade = _blade(open_files=[_open_file("of1")])
        module = _run(_params(target="open_files", file_system="fs1"), blade)
        result = _result(module)
        assert list(result["open_files"]) == ["of1"]
        module.warn.assert_not_called()
        blade.get_file_systems.assert_called_once_with(names=["fs1"])
        blade.get_file_systems_open_files.assert_called_once_with(
            protocols=["smb"], file_system_names=["fs1"]
        )

    def test_list_open_files_lookup_refused_for_another_reason_warns_and_lists(self):
        # An identity may be allowed the open files but not the file systems.
        # That does not show the name is wrong, so the request is not blocked.
        blade = _blade(open_files=[_open_file("of1")])
        blade.get_file_systems = Mock(return_value=_refused(NOT_PERMITTED))
        module = _run(_params(target="open_files", file_system="fs1"), blade)
        result = _result(module)
        assert result["changed"] is False
        assert list(result["open_files"]) == ["of1"]
        module.warn.assert_called_once()
        warning = module.warn.call_args[0][0]
        assert "Could not check that file system fs1 exists" in warning
        assert NOT_PERMITTED in warning
        blade.get_file_systems_open_files.assert_called_once_with(
            protocols=["smb"], file_system_names=["fs1"]
        )

    def test_open_files_lookup_refusal_warning_keeps_one_full_stop(self):
        # The array's message ends with a full stop of its own.
        blade = _blade()
        blade.get_file_systems = Mock(return_value=_refused(NOT_PERMITTED))
        module = _run(_params(target="open_files", file_system="fs1"), blade)
        assert _result(module)["open_files"] == {}
        assert module.warn.call_args[0][0] == (
            "Could not check that file system fs1 exists. Error: " + NOT_PERMITTED + " "
            "The array lists no open files for a file system it does not have, "
            "so an empty result does not confirm the name."
        )

    def test_open_files_refused_to_a_realm_administrator_are_relayed(self):
        # The realm's administrator may read its file systems, so the lookup
        # is answered, and is then refused the open files themselves.
        for state in ("query", "absent"):
            blade = _blade(file_systems=[_file_system(REALM_FS, realm="realm1")])
            blade.get_file_systems_open_files.return_value = _refused(
                REALM_ADMIN_REFUSED
            )
            module = _run(
                _params(state=state, target="open_files", file_system=REALM_FS),
                blade,
            )
            assert _failure(module) == (
                "Failed to list open files. Error: " + REALM_ADMIN_REFUSED
            )
            module.warn.assert_not_called()
            blade.get_file_systems.assert_called_once_with(names=[REALM_FS])
            blade.delete_file_systems_open_files.assert_not_called()

    def test_list_open_files_lookup_error_without_a_message_warns_and_lists(self):
        blade = _blade()
        blade.get_file_systems = Mock(return_value=_response(status=503))
        module = _run(_params(target="open_files", file_system="fs1"), blade)
        assert _result(module)["open_files"] == {}
        module.warn.assert_called_once()
        assert "Error: Unknown error" in module.warn.call_args[0][0]

    def test_close_open_files_lookup_refused_for_another_reason_warns_and_closes(self):
        for check_mode in (False, True):
            blade = _blade(open_files=[_open_file("of1")])
            blade.get_file_systems = Mock(return_value=_refused(NOT_PERMITTED))
            module = _run(
                _params(state="absent", target="open_files", file_system="fs1"),
                blade,
                check_mode=check_mode,
            )
            assert _result(module)["changed"] is True
            module.warn.assert_called_once()
            if check_mode:
                blade.delete_file_systems_open_files.assert_not_called()
            else:
                blade.delete_file_systems_open_files.assert_called_once_with(
                    ids=["of1"]
                )

    def test_list_open_files_missing_file_system_fails_without_a_warning(self):
        # Any wording of "does not exist" from the lookup is a missing name.
        for message in (NO_FILE_SYSTEM, "Realm does not exist."):
            blade = _blade()
            blade.get_file_systems = Mock(return_value=_refused(message))
            module = _run(_params(target="open_files", file_system="nope"), blade)
            assert _failure(module) == (
                "Failed to list open files. File system nope was not found. "
                "Error: " + message
            )
            module.warn.assert_not_called()
            blade.get_file_systems_open_files.assert_not_called()

    def test_open_files_without_a_file_system_need_no_lookup(self):
        blade = _blade(open_files=[_open_file("of1")])
        _result(_run(_params(target="open_files", client=["10.0.0.1"]), blade))
        _result(_run(_params(), blade))
        blade.get_file_systems.assert_not_called()

    # ---------------- clearing locks by file system alone ----------------

    def test_clear_locks_by_file_system_alone_is_refused(self):
        for check_mode in (False, True):
            blade = _blade(locks=[_lock("lock1")])
            msg = _failure(
                _run(
                    _params(state="absent", target="locks", file_system="fs1"),
                    blade,
                    check_mode=check_mode,
                )
            )
            assert "also requires path or inode" in msg
            blade.get_file_systems_locks.assert_not_called()
            blade.delete_file_systems_locks.assert_not_called()

    def test_clear_locks_by_file_system_and_client_is_refused(self):
        blade = _blade(locks=[_lock("lock1", file_system=REALM_FS)])
        msg = _failure(
            _run(
                _params(
                    state="absent",
                    target="locks",
                    file_system=REALM_FS,
                    client=["10.0.0.1"],
                ),
                blade,
            )
        )
        assert "also requires path or inode" in msg
        blade.get_file_systems_locks.assert_not_called()
        blade.delete_file_systems_locks.assert_not_called()

    def test_clear_locks_by_file_system_and_inode_sends_the_inodes(self):
        blade = _blade(locks=[_lock("lock1")])
        result = _result(
            _run(
                _params(
                    state="absent",
                    target="locks",
                    file_system="fs1",
                    inode=[42],
                    client=["10.0.0.1"],
                ),
                blade,
            )
        )
        assert result["changed"] is True
        blade.delete_file_systems_locks.assert_called_once_with(
            client_names=["10.0.0.1"], file_system_names=["fs1"], inodes=[42]
        )

    def test_clear_locks_whole_file_system_sends_root_and_recursive(self):
        blade = _blade(locks=[_lock("lock1")])
        result = _result(
            _run(
                _params(
                    state="absent",
                    target="locks",
                    file_system="fs1",
                    path=["/"],
                    recursive=True,
                    client=["10.0.0.1"],
                ),
                blade,
            )
        )
        assert result["changed"] is True
        blade.get_file_systems_locks.assert_called_once_with(
            client_names=["10.0.0.1"], file_system_names=["fs1"]
        )
        blade.delete_file_systems_locks.assert_called_once_with(
            client_names=["10.0.0.1"],
            file_system_names=["fs1"],
            paths=["/"],
            recursive=True,
        )

    def test_list_locks_by_file_system_and_client_is_still_allowed(self):
        blade = _blade()
        result = _result(
            _run(_params(target="locks", file_system="fs1", client=["10.0.0.1"]), blade)
        )
        assert result["locks"] == {}
        blade.get_file_systems_locks.assert_called_once_with(
            client_names=["10.0.0.1"], file_system_names=["fs1"]
        )
