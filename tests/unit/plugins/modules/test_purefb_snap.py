# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for the purefb_snap module (reads, state=present, restore and copy)."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from contextlib import ExitStack
from unittest.mock import Mock, patch, MagicMock

import pytest

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

from plugins.modules.purefb_snap import (
    main,
    get_fssnapshot,
    get_target_filesystem,
    _check_copy_scope,
    _first_item,
    _get_filesystem,
    _is_copy_of,
    _realm_of,
    COPY_API_VERSION,
)
from plugins.module_utils.version import LooseVersion as RealLooseVersion

MODULE = "plugins.modules.purefb_snap"

# IDs as the array reports them: opaque and different for filesystems that
# share a name in different realms.
FS_ID = "10000000-0000-4000-8000-000000000001"
TWIN_ID = "10000000-0000-4000-8000-000000000002"
COPY_ID = "10000000-0000-4000-8000-000000000003"

FS_MISSING = "File system does not exist."
SNAP_MISSING = "Snapshot does not exist."
REFUSED = "Operation not permitted."


class ExitJson(Exception):
    """Raised by the mocked exit_json so main() stops like the real one."""


class FailJson(Exception):
    """Raised by the mocked fail_json so main() stops like the real one."""


def _module(**overrides):
    params = {
        "name": "fs",
        "suffix": "snap",
        "now": False,
        "target": None,
        "target_fs": "fs-copy",
        "eradicate": False,
        "state": "copy",
        "detach_policies": None,
        "detach_all_policies": False,
        "latest_replica": False,
        "context": "",
    }
    params.update(overrides)
    module = Mock()
    module.check_mode = False
    module.params = params
    module.exit_json.side_effect = ExitJson
    module.fail_json.side_effect = FailJson
    return module


def _response(items=None, status_code=200, error=None):
    res = Mock()
    res.status_code = status_code
    res.items = items if items is not None else []
    res.errors = [Mock(message=error)] if error else []
    return res


def _error_message(res, default="Unknown error"):
    """What get_error_message of module_utils.common returns for a response"""
    errors = getattr(res, "errors", None)
    if errors:
        return errors[0].message
    return default


def _snapshot(name="fs.snap", destroyed=False, created=1):
    snap = Mock()
    snap.name = name
    snap.destroyed = destroyed
    snap.created = created
    return snap


def _filesystem(name="fs", destroyed=False, fs_id=FS_ID, promotion_status="promoted"):
    """A filesystem that is not a copy: the array reports an empty source."""
    fsys = Mock()
    fsys.id = fs_id
    fsys.name = name
    fsys.destroyed = destroyed
    fsys.promotion_status = promotion_status
    fsys.source = Mock()
    fsys.source.id = None
    fsys.source.name = None
    fsys.source.display_name = None
    fsys.source.is_local = True
    return fsys


def _copy(
    name="fs-copy",
    of="fs",
    source_id=FS_ID,
    destroyed=False,
    promotion_status="promoted",
):
    """A filesystem copy as the array reports it.

    source.name is the name of the source without its realm, in the letter
    case the source was created with, source.display_name its full name and
    source.id the ID of the source filesystem.
    """
    fsys = _filesystem(
        name=name,
        destroyed=destroyed,
        fs_id=COPY_ID,
        promotion_status=promotion_status,
    )
    fsys.source.id = source_id
    fsys.source.name = of.rpartition("::")[2]
    fsys.source.display_name = of
    return fsys


def _connection(name="remote1", status="connected"):
    connection = Mock()
    connection.remote = Mock()
    connection.remote.name = name
    connection.status = status
    return connection


def _blade(snapshots=None, target=None, post_status=200):
    """A client whose reads answer as the array does.

    A filesystem or snapshot that does not exist is a 400 with the array's
    message, not an empty listing.
    """
    blade = Mock()
    blade.get_fleets.return_value = _response([])
    if snapshots:
        blade.get_file_system_snapshots.return_value = _response(snapshots)
    else:
        blade.get_file_system_snapshots.return_value = _response([], 400, SNAP_MISSING)
    if target:
        blade.get_file_systems.return_value = _response([target])
    else:
        blade.get_file_systems.return_value = _response([], 400, FS_MISSING)
    blade.post_file_systems.return_value = _response(
        [_copy(promotion_status="promoting")], post_status
    )
    blade.post_file_system_snapshots.return_value = _response([])
    blade.get_array_connections.return_value = _response([_connection()])
    return blade


def _fail_msg(module):
    return module.fail_json.call_args.kwargs["msg"]


def _patched(cls):
    """Give the tests of a class the real helpers the module imports."""
    for name, new in (
        (".LooseVersion", RealLooseVersion),
        (".get_rest_api_version", Mock(return_value="2.30")),
        (".get_error_message", _error_message),
    ):
        cls = patch(MODULE + name, new)(cls)
    return cls


def _run_main(
    module, blade, filesystem, api_version="2.30", expect=ExitJson, real_read=False
):
    """Run main() with its collaborators patched.

    main() always ends in exit_json or fail_json, which the mocked module
    turns into ExitJson / FailJson. The source filesystem is the one given
    unless real_read is set, in which case main() reads it from the client.
    Returns the patched AnsibleModule, FileSystemPost, Reference and
    FileSystemSnapshotPost mocks in a dict so tests can check what was sent.
    """
    with ExitStack() as stack:
        ansible_module = stack.enter_context(
            patch(MODULE + ".AnsibleModule", return_value=module)
        )
        stack.enter_context(patch(MODULE + ".get_system", return_value=blade))
        if not real_read:
            stack.enter_context(
                patch(MODULE + "._get_filesystem", return_value=filesystem)
            )
        stack.enter_context(
            patch(MODULE + ".get_rest_api_version", return_value=api_version)
        )
        stack.enter_context(patch(MODULE + ".get_error_message", _error_message))
        stack.enter_context(patch(MODULE + ".LooseVersion", RealLooseVersion))
        stack.enter_context(patch(MODULE + ".HAS_PYPURECLIENT", True))
        fs_post = stack.enter_context(patch(MODULE + ".FileSystemPost"))
        reference = stack.enter_context(patch(MODULE + ".Reference"))
        snap_post = stack.enter_context(patch(MODULE + ".FileSystemSnapshotPost"))
        with pytest.raises(expect):
            main()
    return {
        "ansible_module": ansible_module,
        "fs_post": fs_post,
        "reference": reference,
        "snap_post": snap_post,
    }


class TestRealmOf:
    """_realm_of returns the realm a name places its object in"""

    @pytest.mark.parametrize(
        "name, realm",
        [("fs", ""), ("realm1::fs", "realm1"), ("Realm1::fs.snap", "Realm1")],
    )
    def test_realm_of(self, name, realm):
        assert _realm_of(name) == realm


@_patched
class TestFirstItem:
    """_first_item tells an absent object from a read that failed"""

    def test_returns_first_item(self):
        module = _module()
        item = _filesystem()
        assert _first_item(module, _response([item, _filesystem()]), "x") is item
        module.fail_json.assert_not_called()

    def test_returns_none_for_empty_listing(self):
        """A realm-scoped administrator gets an empty listing for a bare name"""
        module = _module()
        assert _first_item(module, _response([]), "x") is None
        module.fail_json.assert_not_called()

    @pytest.mark.parametrize("error", [FS_MISSING, SNAP_MISSING])
    def test_returns_none_when_array_says_does_not_exist(self, error):
        module = _module()
        assert _first_item(module, _response([], 400, error), "x") is None
        module.fail_json.assert_not_called()

    @pytest.mark.parametrize(
        "error",
        [
            REFUSED,
            "Operation not permitted. Authorization for 'read' on "
            "'file-systems' is required.",
        ],
    )
    def test_fails_with_array_message_on_any_other_answer(self, error):
        module = _module()
        with pytest.raises(FailJson):
            _first_item(module, _response([], 403, error), "filesystem fs")
        assert _fail_msg(module) == "Failed to get filesystem fs. Error: " + error


@_patched
class TestGetFilesystem:
    """_get_filesystem reads the source filesystem by name"""

    def test_returns_first_item(self):
        module = _module(name="realm1::fs")
        source = _filesystem(name="realm1::fs")
        blade = _blade(target=source)
        assert _get_filesystem(module, blade) is source
        blade.get_file_systems.assert_called_once_with(names=["realm1::fs"])

    def test_passes_context(self):
        module = _module(context="member1")
        blade = _blade(target=_filesystem())
        _get_filesystem(module, blade)
        blade.get_file_systems.assert_called_once_with(
            names=["fs"], context_names=["member1"]
        )

    def test_returns_none_when_missing(self):
        module = _module()
        assert _get_filesystem(module, _blade()) is None
        module.fail_json.assert_not_called()

    def test_fails_when_the_read_is_refused(self):
        module = _module()
        blade = _blade()
        blade.get_file_systems.return_value = _response([], 403, REFUSED)
        with pytest.raises(FailJson):
            _get_filesystem(module, blade)
        assert _fail_msg(module) == "Failed to get filesystem fs. Error: " + REFUSED


@_patched
class TestGetFssnapshot:
    """get_fssnapshot reads the snapshot named by name and suffix"""

    def test_returns_first_item(self):
        module = _module(name="realm1::fs")
        snap = _snapshot(name="realm1::fs.snap")
        blade = _blade(snapshots=[snap])
        assert get_fssnapshot(module, blade) is snap
        blade.get_file_system_snapshots.assert_called_once_with(
            names_or_owner_names=["realm1::fs.snap"]
        )

    def test_passes_context(self):
        module = _module(context="member1")
        blade = _blade(snapshots=[_snapshot()])
        get_fssnapshot(module, blade)
        blade.get_file_system_snapshots.assert_called_once_with(
            names_or_owner_names=["fs.snap"], context_names=["member1"]
        )

    @pytest.mark.parametrize("error", [SNAP_MISSING, FS_MISSING])
    def test_returns_none_when_missing(self, error):
        """Neither the snapshot nor, by owner, its filesystem exists"""
        module = _module()
        blade = _blade()
        blade.get_file_system_snapshots.return_value = _response([], 400, error)
        assert get_fssnapshot(module, blade) is None
        module.fail_json.assert_not_called()

    def test_fails_when_the_read_is_refused(self):
        module = _module()
        blade = _blade()
        blade.get_file_system_snapshots.return_value = _response([], 403, REFUSED)
        with pytest.raises(FailJson):
            get_fssnapshot(module, blade)
        assert _fail_msg(module) == "Failed to get snapshot fs.snap. Error: " + REFUSED


@_patched
class TestGetTargetFilesystem:
    """get_target_filesystem looks the target up by target_fs"""

    def test_returns_first_item(self):
        module = _module()
        target = _copy()
        blade = _blade(target=target)
        assert get_target_filesystem(module, blade) is target
        blade.get_file_systems.assert_called_once_with(names=["fs-copy"])

    def test_returns_none_when_missing(self):
        module = _module()
        assert get_target_filesystem(module, _blade()) is None
        module.fail_json.assert_not_called()

    def test_returns_none_for_empty_listing(self):
        module = _module()
        blade = _blade()
        blade.get_file_systems.return_value = _response([])
        assert get_target_filesystem(module, blade) is None

    def test_fails_when_the_read_is_refused(self):
        """A refused read is not taken to mean the target is free"""
        module = _module()
        blade = _blade()
        blade.get_file_systems.return_value = _response([], 403, REFUSED)
        with pytest.raises(FailJson):
            get_target_filesystem(module, blade)
        assert _fail_msg(module) == (
            "Failed to get filesystem fs-copy. Error: " + REFUSED
        )

    def test_passes_context(self):
        module = _module(context="member1")
        blade = _blade()
        get_target_filesystem(module, blade)
        blade.get_file_systems.assert_called_once_with(
            names=["fs-copy"], context_names=["member1"]
        )


class TestIsCopyOf:
    """_is_copy_of recognises a copy by the ID of its source"""

    def test_same_id_is_a_copy(self):
        source = _filesystem(name="realm1::fs")
        target = _copy(name="realm1::fs-copy", of="realm1::fs")
        assert _is_copy_of(target, source, "realm1::fs") is True

    def test_same_id_is_a_copy_whatever_the_letter_case(self):
        """The array finds FS for the name fs and reports the stored name"""
        assert _is_copy_of(_copy(of="fs"), _filesystem(name="fs"), "FS") is True

    @pytest.mark.parametrize(
        "name, twin",
        [("realm1::fs", "fs"), ("fs", "realm1::fs"), ("realm2::fs", "realm1::fs")],
    )
    def test_copy_of_a_namesake_in_another_scope_is_not_a_copy(self, name, twin):
        """source.name is the bare name in every scope; the IDs differ"""
        source = _filesystem(name=name)
        target = _copy(of=twin, source_id=TWIN_ID)
        assert target.source.name == "fs"
        assert _is_copy_of(target, source, name) is False

    def test_filesystem_without_a_source_is_not_a_copy(self):
        target = _filesystem(name="fs-copy", fs_id=COPY_ID)
        assert _is_copy_of(target, _filesystem(), "fs") is False

    def test_filesystem_without_a_source_reference_is_not_a_copy(self):
        target = _filesystem(name="fs-copy", fs_id=COPY_ID)
        target.source = None
        assert _is_copy_of(target, _filesystem(), "fs") is False

    @pytest.mark.parametrize(
        "name, display_name, expected",
        [
            ("realm1::fs", "realm1::fs", True),
            ("REALM1::FS", "realm1::fs", True),
            ("realm1::fs", "fs", False),
            ("fs", "realm1::fs", False),
        ],
    )
    def test_full_name_decides_without_an_id(self, name, display_name, expected):
        target = _copy(of=display_name, source_id=None)
        assert _is_copy_of(target, _filesystem(name=name), name) is expected

    @pytest.mark.parametrize(
        "name, source_name, expected",
        [
            ("fs", "fs", True),
            ("realm1::fs", "fs", True),
            ("realm1::fs", "realm1::fs", True),
            ("realm1::FS", "fs", True),
            ("realm1::fs", "other", False),
        ],
    )
    def test_name_decides_without_id_and_full_name(self, name, source_name, expected):
        target = _copy(source_id=None)
        target.source.display_name = None
        target.source.name = source_name
        assert _is_copy_of(target, _filesystem(name=name), name) is expected


class TestCheckCopyScope:
    """_check_copy_scope keeps a copy in the realm of its source"""

    @pytest.mark.parametrize(
        "name, target_fs",
        [
            ("fs", "fs-copy"),
            ("realm1::fs", "realm1::fs-copy"),
            ("REALM1::fs", "realm1::fs-copy"),
        ],
    )
    def test_same_scope_passes(self, name, target_fs):
        module = _module(name=name, target_fs=target_fs)
        _check_copy_scope(module)
        module.fail_json.assert_not_called()

    @pytest.mark.parametrize(
        "name, target_fs, hint",
        [
            ("realm1::fs", "fs-copy", "in realm realm1, named realm1::<name>"),
            ("realm1::fs", "realm2::fs-copy", "in realm realm1, named realm1::<name>"),
            ("fs", "realm1::fs-copy", "outside of any realm"),
        ],
    )
    def test_other_scope_is_refused(self, name, target_fs, hint):
        module = _module(name=name, target_fs=target_fs)
        with pytest.raises(FailJson):
            _check_copy_scope(module)
        msg = _fail_msg(module)
        assert msg.startswith(
            "target_fs {0} must be in the same realm as the source "
            "filesystem {1}.".format(target_fs, name)
        )
        assert hint in msg


class TestPurefbSnapCopy:
    """state=copy through main()"""

    def test_copy_creates_target_from_named_snapshot(self):
        module = _module()
        blade = _blade(snapshots=[_snapshot()])
        run = _run_main(module, blade, _filesystem())
        run["reference"].assert_called_once_with(name="fs.snap")
        run["fs_post"].assert_called_once_with(source=run["reference"].return_value)
        blade.post_file_systems.assert_called_once_with(
            names=["fs-copy"],
            include_snapshot=True,
            file_system=run["fs_post"].return_value,
        )
        module.exit_json.assert_called_once_with(
            changed=True, promotion_status="promoting"
        )

    def test_copy_requires_target_fs(self):
        module = _module()
        blade = _blade(snapshots=[_snapshot()])
        run = _run_main(module, blade, _filesystem())
        required_if = run["ansible_module"].call_args.kwargs["required_if"]
        assert ["state", "copy", ["target_fs"]] in required_if

    def test_copy_unchanged_when_target_is_copy_of_source(self):
        module = _module()
        blade = _blade(snapshots=[_snapshot()], target=_copy())
        _run_main(module, blade, _filesystem())
        blade.post_file_systems.assert_not_called()
        module.exit_json.assert_called_once_with(
            changed=False, promotion_status="promoted"
        )

    def test_copy_unchanged_with_other_suffix_when_target_is_copy(self):
        """Idempotency keys on the copy's source filesystem, not the snapshot"""
        module = _module(suffix="other")
        blade = _blade(snapshots=[_snapshot(name="fs.other")], target=_copy())
        _run_main(module, blade, _filesystem())
        blade.post_file_systems.assert_not_called()
        module.exit_json.assert_called_once_with(
            changed=False, promotion_status="promoted"
        )

    @pytest.mark.parametrize(
        "name, target_fs, stored",
        [
            ("FS", "fs-copy", "fs"),
            ("realm1::FS", "realm1::fs-copy", "realm1::fs"),
            ("REALM1::fs", "Realm1::FS-COPY", "realm1::fs"),
        ],
    )
    def test_copy_unchanged_when_names_differ_in_letter_case(
        self, name, target_fs, stored
    ):
        """The array matches names whatever their case; the source ID decides"""
        module = _module(name=name, target_fs=target_fs)
        target = _copy(name=stored + "-copy", of=stored)
        blade = _blade(snapshots=[_snapshot(name=stored + ".snap")], target=target)
        _run_main(module, blade, _filesystem(name=stored))
        blade.post_file_systems.assert_not_called()
        module.exit_json.assert_called_once_with(
            changed=False, promotion_status="promoted"
        )

    def test_copy_fails_when_target_exists_with_other_source(self):
        module = _module()
        target = _filesystem(name="fs-copy", fs_id=COPY_ID)
        blade = _blade(snapshots=[_snapshot()], target=target)
        _run_main(module, blade, _filesystem(), expect=FailJson)
        blade.post_file_systems.assert_not_called()
        assert "is not a copy of fs" in _fail_msg(module)

    @pytest.mark.parametrize("name", ["fs", "realm1::fs"])
    def test_copy_fails_when_target_is_copy_of_a_namesake(self, name):
        """Same source name, another filesystem: the source ID differs"""
        realm = name.rpartition("::")[0]
        target_fs = realm + "::fs-copy" if realm else "fs-copy"
        module = _module(name=name, target_fs=target_fs)
        target = _copy(name=target_fs, of=name, source_id=TWIN_ID)
        blade = _blade(snapshots=[_snapshot(name=name + ".snap")], target=target)
        _run_main(module, blade, _filesystem(name=name), expect=FailJson)
        blade.post_file_systems.assert_not_called()
        assert _fail_msg(module).startswith(
            "Filesystem {0} already exists and is not a copy of {1}.".format(
                target_fs, name
            )
        )

    def test_copy_fails_when_target_is_destroyed(self):
        """A destroyed copy of the source can be recovered or eradicated"""
        module = _module()
        blade = _blade(snapshots=[_snapshot()], target=_copy(destroyed=True))
        _run_main(module, blade, _filesystem(), expect=FailJson)
        blade.post_file_systems.assert_not_called()
        assert "exists but is destroyed" in _fail_msg(module)
        assert "Recover or eradicate it before copying to it" in _fail_msg(module)

    def test_copy_fails_when_destroyed_target_is_not_a_copy(self):
        """A destroyed filesystem with another source must be eradicated"""
        module = _module()
        target = _filesystem(name="fs-copy", destroyed=True, fs_id=COPY_ID)
        blade = _blade(snapshots=[_snapshot()], target=target)
        _run_main(module, blade, _filesystem(), expect=FailJson)
        blade.post_file_systems.assert_not_called()
        msg = _fail_msg(module)
        assert "exists but is destroyed and is not a copy of fs" in msg
        assert "Eradicate it before copying to it" in msg
        assert "Recover" not in msg

    def test_copy_unchanged_for_a_copy_inside_a_realm(self):
        """The array reports the source of a realm copy by its bare name"""
        module = _module(name="realm1::fs", target_fs="realm1::fs-copy")
        target = _copy(name="realm1::fs-copy", of="realm1::fs")
        assert target.source.name == "fs"
        blade = _blade(snapshots=[_snapshot(name="realm1::fs.snap")], target=target)
        _run_main(module, blade, _filesystem(name="realm1::fs"))
        blade.post_file_systems.assert_not_called()
        module.exit_json.assert_called_once_with(
            changed=False, promotion_status="promoted"
        )

    def test_copy_fails_when_realm_target_has_other_source(self):
        module = _module(name="realm1::fs", target_fs="realm1::fs-copy")
        target = _copy(name="realm1::fs-copy", of="realm1::other", source_id=TWIN_ID)
        blade = _blade(snapshots=[_snapshot(name="realm1::fs.snap")], target=target)
        _run_main(module, blade, _filesystem(name="realm1::fs"), expect=FailJson)
        blade.post_file_systems.assert_not_called()
        assert "is not a copy of realm1::fs" in _fail_msg(module)

    @pytest.mark.parametrize(
        "name, target_fs, twin",
        [
            ("realm1::fs", "fs-copy", "fs"),
            ("fs", "realm1::fs-copy", "realm1::fs"),
            ("realm2::fs", "realm1::fs-copy", "realm1::fs"),
        ],
    )
    def test_copy_fails_for_existing_target_in_another_scope(
        self, name, target_fs, twin
    ):
        """An existing copy of a namesake in another scope is not accepted"""
        module = _module(name=name, target_fs=target_fs)
        target = _copy(name=target_fs, of=twin, source_id=TWIN_ID)
        blade = _blade(snapshots=[_snapshot(name=name + ".snap")], target=target)
        _run_main(module, blade, _filesystem(name=name), expect=FailJson)
        blade.post_file_systems.assert_not_called()
        assert "must be in the same realm as the source filesystem" in _fail_msg(module)

    @pytest.mark.parametrize("check_mode", [True, False])
    @pytest.mark.parametrize(
        "name, target_fs",
        [
            ("realm1::fs", "fs-copy"),
            ("fs", "realm1::fs-copy"),
            ("realm2::fs", "realm1::fs-copy"),
        ],
    )
    def test_copy_to_another_scope_is_refused_in_both_modes(
        self, name, target_fs, check_mode
    ):
        """The array refuses it, so check mode does not report a change"""
        module = _module(name=name, target_fs=target_fs)
        module.check_mode = check_mode
        blade = _blade(snapshots=[_snapshot(name=name + ".snap")])
        _run_main(module, blade, _filesystem(name=name), expect=FailJson)
        blade.get_file_systems.assert_not_called()
        blade.post_file_systems.assert_not_called()
        module.exit_json.assert_not_called()
        assert _fail_msg(module).startswith(
            "target_fs {0} must be in the same realm as the source "
            "filesystem {1}.".format(target_fs, name)
        )

    def test_copy_inside_a_realm_whose_name_differs_in_case(self):
        """One realm written in two ways is not another scope"""
        module = _module(name="REALM1::fs", target_fs="realm1::fs-copy")
        blade = _blade(snapshots=[_snapshot(name="realm1::fs.snap")])
        _run_main(module, blade, _filesystem(name="realm1::fs"))
        blade.post_file_systems.assert_called_once()
        module.exit_json.assert_called_once_with(
            changed=True, promotion_status="promoting"
        )

    def test_copy_fails_when_the_target_read_is_refused(self):
        """A refused read of the target is not taken to mean it is free"""
        module = _module()
        blade = _blade(snapshots=[_snapshot()])
        blade.get_file_systems.return_value = _response([], 403, REFUSED)
        _run_main(module, blade, _filesystem(), expect=FailJson)
        blade.post_file_systems.assert_not_called()
        assert _fail_msg(module) == (
            "Failed to get filesystem fs-copy. Error: " + REFUSED
        )

    def test_copy_check_mode_sends_nothing(self):
        module = _module()
        module.check_mode = True
        blade = _blade(snapshots=[_snapshot()])
        _run_main(module, blade, _filesystem())
        blade.post_file_systems.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True, promotion_status=None)

    def test_copy_fails_below_minimum_api_version(self):
        module = _module()
        blade = _blade(snapshots=[_snapshot()])
        _run_main(module, blade, _filesystem(), api_version="2.24", expect=FailJson)
        assert COPY_API_VERSION in _fail_msg(module)
        blade.get_file_systems.assert_not_called()
        blade.post_file_systems.assert_not_called()

    def test_copy_fails_when_snapshot_missing(self):
        module = _module()
        blade = _blade(snapshots=[])
        _run_main(module, blade, _filesystem(), expect=FailJson)
        assert "Snapshot fs.snap does not exist" in _fail_msg(module)
        blade.post_file_systems.assert_not_called()

    def test_copy_fails_when_snapshot_destroyed(self):
        module = _module()
        blade = _blade(snapshots=[_snapshot(destroyed=True)])
        _run_main(module, blade, _filesystem(), expect=FailJson)
        assert "Snapshot fs.snap is destroyed" in _fail_msg(module)
        blade.post_file_systems.assert_not_called()

    def test_copy_fails_when_source_filesystem_missing(self):
        module = _module()
        blade = _blade(snapshots=[_snapshot()])
        _run_main(module, blade, None, expect=FailJson)
        assert "Filesystem fs does not exist" in _fail_msg(module)
        blade.post_file_systems.assert_not_called()

    def test_copy_uses_latest_snapshot_without_suffix(self):
        module = _module(suffix=None)
        older = _snapshot(name="fs.older", created=1)
        newer = _snapshot(name="fs.newer", created=2)

        def snapshots(**kwargs):
            # The exact-name lookup for the generated suffix finds nothing;
            # the owner lookup returns every snapshot of the filesystem.
            if "." in kwargs["names_or_owner_names"][0]:
                return _response([], 400, SNAP_MISSING)
            return _response([older, newer])

        blade = _blade()
        blade.get_file_system_snapshots.side_effect = snapshots
        run = _run_main(module, blade, _filesystem())
        run["reference"].assert_called_once_with(name="fs.newer")
        blade.post_file_systems.assert_called_once()
        module.exit_json.assert_called_once_with(
            changed=True, promotion_status="promoting"
        )

    def test_copy_fails_without_any_snapshot(self):
        module = _module(suffix=None)
        blade = _blade(snapshots=[])
        blade.get_file_system_snapshots.return_value = _response([])
        _run_main(module, blade, _filesystem(), expect=FailJson)
        assert "has no snapshots to copy from" in _fail_msg(module)
        blade.post_file_systems.assert_not_called()

    def test_copy_fails_on_api_error(self):
        module = _module()
        blade = _blade(snapshots=[_snapshot()], post_status=400)
        _run_main(module, blade, _filesystem(), expect=FailJson)
        assert _fail_msg(module).startswith(
            "Failed to copy snapshot fs.snap to new filesystem fs-copy."
        )

    def test_copy_with_context_and_realm_target(self):
        module = _module(
            context="member1", name="realm1::fs", target_fs="realm1::fs-copy"
        )
        blade = _blade(snapshots=[_snapshot(name="realm1::fs.snap")])
        run = _run_main(module, blade, _filesystem(name="realm1::fs"))
        blade.get_file_systems.assert_called_once_with(
            names=["realm1::fs-copy"], context_names=["member1"]
        )
        blade.post_file_systems.assert_called_once_with(
            names=["realm1::fs-copy"],
            include_snapshot=True,
            file_system=run["fs_post"].return_value,
            context_names=["member1"],
            default_exports=["''"],
        )
        module.exit_json.assert_called_once_with(
            changed=True, promotion_status="promoting"
        )


class TestPurefbSnapMissingFilesystem:
    """A filesystem that does not exist, or that the identity cannot see"""

    @pytest.mark.parametrize("check_mode", [True, False])
    @pytest.mark.parametrize("name", ["fs", "norealm::fs", "realm2::fs"])
    def test_present_fails(self, name, check_mode):
        module = _module(name=name, state="present", target_fs=None)
        module.check_mode = check_mode
        blade = _blade()
        _run_main(module, blade, None, expect=FailJson)
        assert _fail_msg(module) == (
            "Filesystem {0} does not exist, cannot create a snapshot of "
            "it.".format(name)
        )
        blade.post_file_system_snapshots.assert_not_called()
        module.exit_json.assert_not_called()

    @pytest.mark.parametrize("check_mode", [True, False])
    @pytest.mark.parametrize("suffix", [None, "snap"])
    def test_restore_fails(self, suffix, check_mode):
        module = _module(state="restore", suffix=suffix, target_fs=None)
        module.check_mode = check_mode
        blade = _blade()
        _run_main(module, blade, None, expect=FailJson)
        assert _fail_msg(module) == "Filesystem fs does not exist, cannot restore it."
        blade.post_file_systems.assert_not_called()
        module.exit_json.assert_not_called()

    @pytest.mark.parametrize("eradicate", [True, False])
    def test_absent_is_unchanged(self, eradicate):
        module = _module(state="absent", eradicate=eradicate, target_fs=None)
        blade = _blade()
        _run_main(module, blade, None)
        blade.patch_file_system_snapshots.assert_not_called()
        blade.delete_file_system_snapshots.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_present_fails_when_array_says_filesystem_does_not_exist(self):
        """main() reads the filesystem itself: the array answers 400"""
        module = _module(state="present", target_fs=None)
        blade = _blade()
        _run_main(module, blade, None, expect=FailJson, real_read=True)
        blade.get_file_systems.assert_called_once_with(names=["fs"])
        assert "Filesystem fs does not exist" in _fail_msg(module)
        blade.post_file_system_snapshots.assert_not_called()

    def test_present_fails_for_a_bare_name_of_a_realm_scoped_administrator(self):
        """That identity gets an empty listing for a name outside its realm"""
        module = _module(state="present", target_fs=None)
        blade = _blade()
        blade.get_file_systems.return_value = _response([])
        blade.get_file_system_snapshots.return_value = _response([], 400, FS_MISSING)
        _run_main(module, blade, None, expect=FailJson, real_read=True)
        assert "Filesystem fs does not exist" in _fail_msg(module)
        blade.post_file_system_snapshots.assert_not_called()

    @pytest.mark.parametrize("destroyed", [False, True])
    def test_absent_does_not_read_the_filesystem(self, destroyed):
        """state=absent acts on the snapshot alone"""
        module = _module(state="absent", eradicate=True, target_fs=None)
        blade = _blade(snapshots=[_snapshot(destroyed=destroyed)])
        blade.get_file_systems.return_value = _response([], 403, REFUSED)
        blade.patch_file_system_snapshots.return_value = _response([])
        blade.delete_file_system_snapshots.return_value = _response([])
        _run_main(module, blade, None, real_read=True)
        blade.get_file_systems.assert_not_called()
        blade.delete_file_system_snapshots.assert_called_once_with(names=["fs.snap"])
        module.exit_json.assert_called_once_with(changed=True)

    @pytest.mark.parametrize("state", ["present", "restore", "copy"])
    def test_refused_filesystem_read_fails_with_array_message(self, state):
        """A refused read is neither absent nor a reason to report no change"""
        module = _module(state=state)
        blade = _blade(snapshots=[_snapshot()])
        blade.get_file_systems.return_value = _response([], 403, REFUSED)
        _run_main(module, blade, None, expect=FailJson, real_read=True)
        assert _fail_msg(module) == "Failed to get filesystem fs. Error: " + REFUSED
        module.exit_json.assert_not_called()

    @pytest.mark.parametrize("state", ["present", "absent", "restore", "copy"])
    def test_refused_snapshot_read_fails_with_array_message(self, state):
        module = _module(state=state)
        blade = _blade()
        blade.get_file_system_snapshots.return_value = _response([], 403, REFUSED)
        _run_main(module, blade, _filesystem(), expect=FailJson)
        assert _fail_msg(module) == "Failed to get snapshot fs.snap. Error: " + REFUSED
        blade.post_file_system_snapshots.assert_not_called()
        blade.patch_file_system_snapshots.assert_not_called()
        module.exit_json.assert_not_called()


class TestPurefbSnapCreate:
    """state=present for a snapshot that does not exist yet"""

    @pytest.mark.parametrize("name", ["fs", "realm1::fs"])
    def test_create_without_target_does_not_read_array_connections(self, name):
        module = _module(name=name, state="present", target_fs=None)
        blade = _blade()
        run = _run_main(module, blade, _filesystem(name=name))
        blade.get_array_connections.assert_not_called()
        run["snap_post"].assert_called_once_with(suffix="snap")
        blade.post_file_system_snapshots.assert_called_once_with(
            source_names=[name], file_system_snapshot=run["snap_post"].return_value
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_create_check_mode_sends_nothing(self):
        module = _module(state="present", target_fs=None)
        module.check_mode = True
        blade = _blade()
        _run_main(module, blade, _filesystem())
        blade.get_array_connections.assert_not_called()
        blade.post_file_system_snapshots.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_create_with_connected_target(self):
        module = _module(state="present", target_fs=None, now=True, target="remote1")
        blade = _blade()
        run = _run_main(module, blade, _filesystem())
        blade.get_array_connections.assert_called_once_with()
        blade.post_file_system_snapshots.assert_called_once_with(
            source_names=["fs"],
            send=True,
            targets=["remote1"],
            file_system_snapshot=run["snap_post"].return_value,
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_create_with_target_and_context(self):
        module = _module(
            state="present", target_fs=None, now=True, target="remote1", context="m1"
        )
        blade = _blade()
        _run_main(module, blade, _filesystem())
        blade.get_array_connections.assert_called_once_with(context_names=["m1"])
        blade.post_file_system_snapshots.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    @pytest.mark.parametrize(
        "connections",
        [
            [],
            [_connection(name="other")],
            [_connection(status="connecting")],
        ],
    )
    def test_create_fails_when_target_is_not_connected(self, connections):
        module = _module(state="present", target_fs=None, now=True, target="remote1")
        blade = _blade()
        blade.get_array_connections.return_value = _response(connections)
        _run_main(module, blade, _filesystem(), expect=FailJson)
        assert _fail_msg(module) == (
            "Selected target is not a correctly connected system"
        )
        blade.post_file_system_snapshots.assert_not_called()

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_create_fails_when_array_connections_read_is_refused(self, check_mode):
        module = _module(state="present", target_fs=None, now=True, target="remote1")
        module.check_mode = check_mode
        blade = _blade()
        blade.get_array_connections.return_value = _response([], 403, REFUSED)
        _run_main(module, blade, _filesystem(), expect=FailJson)
        assert _fail_msg(module) == (
            "Failed to get the array connections to check target remote1. "
            "Error: " + REFUSED
        )
        blade.post_file_system_snapshots.assert_not_called()
