# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for the purefb_snap module (state=copy)."""

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
    get_target_filesystem,
    COPY_API_VERSION,
)
from plugins.module_utils.version import LooseVersion as RealLooseVersion

MODULE = "plugins.modules.purefb_snap"


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


def _response(items=None, status_code=200):
    res = Mock()
    res.status_code = status_code
    res.items = items if items is not None else []
    return res


def _snapshot(name="fs.snap", destroyed=False, created=1):
    snap = Mock()
    snap.name = name
    snap.destroyed = destroyed
    snap.created = created
    return snap


def _filesystem(
    name="fs-copy", destroyed=False, source_name=None, promotion_status="promoted"
):
    fsys = Mock()
    fsys.name = name
    fsys.destroyed = destroyed
    fsys.promotion_status = promotion_status
    fsys.source = Mock()
    fsys.source.name = source_name
    fsys.source.is_local = True
    return fsys


def _blade(snapshots=None, target=None, post_status=200):
    blade = Mock()
    blade.get_fleets.return_value = _response([])
    blade.get_file_system_snapshots.return_value = _response(snapshots or [])
    blade.get_file_systems.return_value = _response([target] if target else [])
    blade.post_file_systems.return_value = _response(
        [_filesystem(promotion_status="promoting")], post_status
    )
    return blade


def _fail_msg(module):
    return module.fail_json.call_args.kwargs["msg"]


def _run_main(module, blade, filesystem, api_version="2.30", expect=ExitJson):
    """Run main() with its collaborators patched.

    main() always ends in exit_json or fail_json, which the mocked module
    turns into ExitJson / FailJson. Returns the patched AnsibleModule,
    FileSystemPost and Reference mocks in a dict so tests can check what
    was sent.
    """
    with ExitStack() as stack:
        ansible_module = stack.enter_context(
            patch(MODULE + ".AnsibleModule", return_value=module)
        )
        stack.enter_context(patch(MODULE + ".get_system", return_value=blade))
        stack.enter_context(patch(MODULE + ".get_filesystem", return_value=filesystem))
        stack.enter_context(
            patch(MODULE + ".get_rest_api_version", return_value=api_version)
        )
        stack.enter_context(patch(MODULE + ".LooseVersion", RealLooseVersion))
        stack.enter_context(patch(MODULE + ".HAS_PYPURECLIENT", True))
        fs_post = stack.enter_context(patch(MODULE + ".FileSystemPost"))
        reference = stack.enter_context(patch(MODULE + ".Reference"))
        with pytest.raises(expect):
            main()
    return {
        "ansible_module": ansible_module,
        "fs_post": fs_post,
        "reference": reference,
    }


class TestGetTargetFilesystem:
    """get_target_filesystem looks the target up by target_fs"""

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", Mock(return_value="2.30"))
    def test_returns_first_item(self):
        module = _module()
        target = _filesystem()
        blade = _blade(target=target)
        assert get_target_filesystem(module, blade) is target
        blade.get_file_systems.assert_called_once_with(names=["fs-copy"])

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", Mock(return_value="2.30"))
    def test_returns_none_when_missing(self):
        module = _module()
        assert get_target_filesystem(module, _blade()) is None

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", Mock(return_value="2.30"))
    def test_returns_none_on_error(self):
        module = _module()
        blade = _blade()
        blade.get_file_systems.return_value = _response([], 400)
        assert get_target_filesystem(module, blade) is None

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", Mock(return_value="2.30"))
    def test_passes_context(self):
        module = _module(context="member1")
        blade = _blade()
        get_target_filesystem(module, blade)
        blade.get_file_systems.assert_called_once_with(
            names=["fs-copy"], context_names=["member1"]
        )


class TestPurefbSnapCopy:
    """state=copy through main()"""

    def test_copy_creates_target_from_named_snapshot(self):
        module = _module()
        blade = _blade(snapshots=[_snapshot()])
        run = _run_main(module, blade, _filesystem(name="fs"))
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
        run = _run_main(module, blade, _filesystem(name="fs"))
        required_if = run["ansible_module"].call_args.kwargs["required_if"]
        assert ["state", "copy", ["target_fs"]] in required_if

    def test_copy_unchanged_when_target_is_copy_of_source(self):
        module = _module()
        target = _filesystem(source_name="fs")
        blade = _blade(snapshots=[_snapshot()], target=target)
        _run_main(module, blade, _filesystem(name="fs"))
        blade.post_file_systems.assert_not_called()
        module.exit_json.assert_called_once_with(
            changed=False, promotion_status="promoted"
        )

    def test_copy_unchanged_with_other_suffix_when_target_is_copy(self):
        """Idempotency keys on the copy's source filesystem, not the snapshot"""
        module = _module(suffix="other")
        target = _filesystem(source_name="fs")
        blade = _blade(snapshots=[_snapshot(name="fs.other")], target=target)
        _run_main(module, blade, _filesystem(name="fs"))
        blade.post_file_systems.assert_not_called()
        module.exit_json.assert_called_once_with(
            changed=False, promotion_status="promoted"
        )

    def test_copy_fails_when_target_exists_with_other_source(self):
        module = _module()
        blade = _blade(snapshots=[_snapshot()], target=_filesystem(source_name=None))
        _run_main(module, blade, _filesystem(name="fs"), expect=FailJson)
        blade.post_file_systems.assert_not_called()
        assert "is not a copy of fs" in _fail_msg(module)

    def test_copy_fails_when_target_is_destroyed(self):
        """A destroyed copy of the source can be recovered or eradicated"""
        module = _module()
        target = _filesystem(destroyed=True, source_name="fs")
        blade = _blade(snapshots=[_snapshot()], target=target)
        _run_main(module, blade, _filesystem(name="fs"), expect=FailJson)
        blade.post_file_systems.assert_not_called()
        assert "exists but is destroyed" in _fail_msg(module)
        assert "Recover or eradicate it before copying to it" in _fail_msg(module)

    def test_copy_fails_when_destroyed_target_is_not_a_copy(self):
        """A destroyed filesystem with another source must be eradicated"""
        module = _module()
        target = _filesystem(destroyed=True, source_name=None)
        blade = _blade(snapshots=[_snapshot()], target=target)
        _run_main(module, blade, _filesystem(name="fs"), expect=FailJson)
        blade.post_file_systems.assert_not_called()
        msg = _fail_msg(module)
        assert "exists but is destroyed and is not a copy of fs" in msg
        assert "Eradicate it before copying to it" in msg
        assert "Recover" not in msg

    @pytest.mark.parametrize("source_name", ["realm1::fs", "fs"])
    def test_copy_unchanged_when_realm_source_reads_back_either_form(self, source_name):
        """The array may report a realm-scoped source as realm::name or name"""
        module = _module(name="realm1::fs", target_fs="realm1::fs-copy")
        target = _filesystem(name="realm1::fs-copy", source_name=source_name)
        blade = _blade(snapshots=[_snapshot(name="realm1::fs.snap")], target=target)
        _run_main(module, blade, _filesystem(name="realm1::fs"))
        blade.post_file_systems.assert_not_called()
        module.exit_json.assert_called_once_with(
            changed=False, promotion_status="promoted"
        )

    def test_copy_fails_when_realm_target_has_other_source(self):
        """A short-name match is only accepted for the realm-scoped source"""
        module = _module(name="realm1::fs", target_fs="realm1::fs-copy")
        target = _filesystem(name="realm1::fs-copy", source_name="other")
        blade = _blade(snapshots=[_snapshot(name="realm1::fs.snap")], target=target)
        _run_main(module, blade, _filesystem(name="realm1::fs"), expect=FailJson)
        blade.post_file_systems.assert_not_called()
        assert "is not a copy of realm1::fs" in _fail_msg(module)

    def test_copy_check_mode_sends_nothing(self):
        module = _module()
        module.check_mode = True
        blade = _blade(snapshots=[_snapshot()])
        _run_main(module, blade, _filesystem(name="fs"))
        blade.post_file_systems.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True, promotion_status=None)

    def test_copy_fails_below_minimum_api_version(self):
        module = _module()
        blade = _blade(snapshots=[_snapshot()])
        _run_main(
            module, blade, _filesystem(name="fs"), api_version="2.24", expect=FailJson
        )
        assert COPY_API_VERSION in _fail_msg(module)
        blade.get_file_systems.assert_not_called()
        blade.post_file_systems.assert_not_called()

    def test_copy_fails_when_snapshot_missing(self):
        module = _module()
        blade = _blade(snapshots=[])
        _run_main(module, blade, _filesystem(name="fs"), expect=FailJson)
        assert "Snapshot fs.snap does not exist" in _fail_msg(module)
        blade.post_file_systems.assert_not_called()

    def test_copy_fails_when_snapshot_destroyed(self):
        module = _module()
        blade = _blade(snapshots=[_snapshot(destroyed=True)])
        _run_main(module, blade, _filesystem(name="fs"), expect=FailJson)
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
                return _response([])
            return _response([older, newer])

        blade = _blade()
        blade.get_file_system_snapshots.side_effect = snapshots
        run = _run_main(module, blade, _filesystem(name="fs"))
        run["reference"].assert_called_once_with(name="fs.newer")
        blade.post_file_systems.assert_called_once()
        module.exit_json.assert_called_once_with(
            changed=True, promotion_status="promoting"
        )

    def test_copy_fails_without_any_snapshot(self):
        module = _module(suffix=None)
        blade = _blade(snapshots=[])
        _run_main(module, blade, _filesystem(name="fs"), expect=FailJson)
        assert "has no snapshots to copy from" in _fail_msg(module)
        blade.post_file_systems.assert_not_called()

    def test_copy_fails_on_api_error(self):
        module = _module()
        blade = _blade(snapshots=[_snapshot()], post_status=400)
        _run_main(module, blade, _filesystem(name="fs"), expect=FailJson)
        assert _fail_msg(module).startswith(
            "Failed to copy snapshot fs.snap to new filesystem fs-copy."
        )

    def test_copy_with_context_and_realm_target(self):
        module = _module(context="member1", target_fs="realm1::fs-copy")
        blade = _blade(snapshots=[_snapshot()])
        run = _run_main(module, blade, _filesystem(name="fs"))
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
