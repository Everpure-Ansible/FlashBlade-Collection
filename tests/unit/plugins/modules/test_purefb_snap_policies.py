# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for the purefb_snap module (detach_policies / detach_all_policies)."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from contextlib import ExitStack
from unittest.mock import Mock, call, patch, MagicMock

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

from ansible.module_utils.common.arg_spec import ArgumentSpecValidator

from plugins.modules.purefb_snap import (
    main,
    _attached_policy_names,
    detach_snapshot_policies,
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
        "eradicate": False,
        "state": "present",
        "latest_replica": False,
        "context": "",
        "detach_policies": ["pol1"],
        "detach_all_policies": False,
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


def _ref(name):
    """A policy reference; Mock(name=...) would set the mock's own name."""
    ref = Mock()
    ref.name = name
    return ref


def _snapshot(name="fs.snap", destroyed=False, policies=("pol1",)):
    """A snapshot as REST 2.12+ reports it: policies list plus policy."""
    snap = Mock()
    snap.name = name
    snap.destroyed = destroyed
    snap.created = 1
    snap.policies = [_ref(policy) for policy in policies]
    snap.policy = _ref(policies[0] if policies else None)
    return snap


def _filesystem(name="fs", destroyed=False):
    fsys = Mock()
    fsys.name = name
    fsys.destroyed = destroyed
    return fsys


def _blade(snapshots=None, delete_status=200):
    blade = Mock()
    blade.get_fleets.return_value = _response([])
    blade.get_file_system_snapshots.return_value = _response(snapshots or [])
    blade.delete_file_system_snapshots_policies.return_value = _response(
        [], delete_status
    )
    return blade


def _fail_msg(module):
    return module.fail_json.call_args.kwargs["msg"]


def _run_main(module, blade, filesystem=None, api_version="2.30", expect=ExitJson):
    """Run main() with its collaborators patched.

    main() always ends in exit_json or fail_json, which the mocked module
    turns into ExitJson / FailJson. Returns the patched AnsibleModule mock
    so tests can check the argument spec it was given.
    """
    if filesystem is None:
        filesystem = _filesystem()
    with ExitStack() as stack:
        ansible_module = stack.enter_context(
            patch(MODULE + ".AnsibleModule", return_value=module)
        )
        stack.enter_context(patch(MODULE + ".purefb_argument_spec", return_value={}))
        stack.enter_context(patch(MODULE + ".get_system", return_value=blade))
        stack.enter_context(patch(MODULE + ".get_filesystem", return_value=filesystem))
        stack.enter_context(
            patch(MODULE + ".get_rest_api_version", return_value=api_version)
        )
        stack.enter_context(patch(MODULE + ".LooseVersion", RealLooseVersion))
        stack.enter_context(patch(MODULE + ".HAS_PYPURECLIENT", True))
        with pytest.raises(expect):
            main()
    return ansible_module


class TestAttachedPolicyNames:
    """_attached_policy_names reads policies, falling back to policy"""

    def test_reads_policies_in_order_without_duplicates(self):
        snap = _snapshot(policies=("pol1", "pol2"))
        snap.policies.append(_ref("pol1"))
        assert _attached_policy_names(snap) == ["pol1", "pol2"]

    def test_skips_unnamed_policy_references(self):
        snap = _snapshot(policies=("pol1",))
        snap.policies.append(_ref(None))
        assert _attached_policy_names(snap) == ["pol1"]

    def test_falls_back_to_policy_when_policies_is_empty(self):
        snap = _snapshot(policies=())
        snap.policy = _ref("pol1")
        assert _attached_policy_names(snap) == ["pol1"]

    def test_falls_back_to_policy_when_policies_is_absent(self):
        """REST versions before 2.12 only report the single policy"""
        snap = _snapshot()
        del snap.policies
        snap.policy = _ref("pol1")
        assert _attached_policy_names(snap) == ["pol1"]

    def test_returns_empty_list_when_nothing_is_attached(self):
        snap = _snapshot(policies=())
        assert _attached_policy_names(snap) == []
        del snap.policies
        snap.policy = None
        assert _attached_policy_names(snap) == []


class TestDetachSnapshotPolicies:
    """detach_snapshot_policies called directly"""

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", Mock(return_value="2.30"))
    def test_sends_only_attached_policies_once_each(self):
        """Every attached policy in the request order, one DELETE each"""
        module = _module(detach_policies=["pol2", "pol1", "pol2", "other"])
        module.params["suffix_given"] = True
        blade = _blade()
        with pytest.raises(ExitJson):
            detach_snapshot_policies(
                module, blade, _snapshot(policies=("pol1", "pol2"))
            )
        assert blade.delete_file_system_snapshots_policies.call_args_list == [
            call(member_names=["fs.snap"], policy_names=["pol2"]),
            call(member_names=["fs.snap"], policy_names=["pol1"]),
        ]
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", Mock(return_value="2.30"))
    def test_fails_when_both_options_are_set(self):
        """Checked in the module so an explicit false is not a conflict"""
        module = _module(detach_policies=["pol1"], detach_all_policies=True)
        module.params["suffix_given"] = True
        blade = _blade()
        with pytest.raises(FailJson):
            detach_snapshot_policies(module, blade, _snapshot())
        assert "mutually exclusive" in _fail_msg(module)
        blade.delete_file_system_snapshots_policies.assert_not_called()


class TestPurefbSnapDetach:
    """detach_policies / detach_all_policies through main()"""

    def test_argument_spec(self):
        module = _module()
        blade = _blade(snapshots=[_snapshot()])
        ansible_module = _run_main(module, blade)
        spec = ansible_module.call_args.args[0]
        assert spec["detach_policies"] == {"type": "list", "elements": "str"}
        assert spec["detach_all_policies"] == {"type": "bool", "default": False}
        assert "mutually_exclusive" not in ansible_module.call_args.kwargs
        assert ansible_module.call_args.kwargs["supports_check_mode"] is True

    def test_explicit_false_detach_all_policies_passes_validation(self):
        """A play that writes detach_all_policies: false next to detach_policies
        must pass Ansible's argument validation, which counts supplied keys"""
        module = _module()
        blade = _blade(snapshots=[_snapshot()])
        ansible_module = _run_main(module, blade)
        spec = ansible_module.call_args.args[0]
        rules = {
            key: value
            for key, value in ansible_module.call_args.kwargs.items()
            if key != "supports_check_mode"
        }
        result = ArgumentSpecValidator(spec, **rules).validate(
            {
                "name": "fs",
                "suffix": "snap",
                "detach_policies": ["pol1"],
                "detach_all_policies": False,
            }
        )
        assert list(result.error_messages) == []

    def test_main_fails_when_both_options_are_set(self):
        module = _module(detach_policies=["pol1"], detach_all_policies=True)
        blade = _blade(snapshots=[_snapshot()])
        _run_main(module, blade, expect=FailJson)
        assert "mutually exclusive" in _fail_msg(module)
        blade.delete_file_system_snapshots_policies.assert_not_called()

    def test_detach_policies_sends_delete_for_attached_policy(self):
        module = _module()
        blade = _blade(snapshots=[_snapshot()])
        _run_main(module, blade)
        blade.delete_file_system_snapshots_policies.assert_called_once_with(
            member_names=["fs.snap"], policy_names=["pol1"]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_detach_policies_unchanged_when_policy_not_attached(self):
        """A rerun after a detach finds nothing attached and sends nothing"""
        module = _module()
        blade = _blade(snapshots=[_snapshot(policies=())])
        _run_main(module, blade)
        blade.delete_file_system_snapshots_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_detach_policies_empty_list_is_a_noop(self):
        module = _module(detach_policies=[])
        blade = _blade(snapshots=[_snapshot()])
        _run_main(module, blade)
        blade.delete_file_system_snapshots_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_detach_policies_empty_list_does_not_create_a_missing_snapshot(self):
        """An empty list still names a policy snapshot, it is not a create"""
        module = _module(detach_policies=[])
        blade = _blade(snapshots=[])
        _run_main(module, blade, expect=FailJson)
        assert "Snapshot fs.snap does not exist" in _fail_msg(module)
        blade.post_file_system_snapshots.assert_not_called()

    def test_detach_policies_unchanged_when_other_policy_attached(self):
        module = _module(detach_policies=["pol2"])
        blade = _blade(snapshots=[_snapshot(policies=("pol1",))])
        _run_main(module, blade)
        blade.delete_file_system_snapshots_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_detach_policies_sends_only_the_attached_subset(self):
        module = _module(detach_policies=["pol1", "pol3"])
        blade = _blade(snapshots=[_snapshot(policies=("pol1", "pol2"))])
        _run_main(module, blade)
        blade.delete_file_system_snapshots_policies.assert_called_once_with(
            member_names=["fs.snap"], policy_names=["pol1"]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_detach_policies_matches_realm_policies_on_full_name(self):
        module = _module(detach_policies=["pol1"])
        blade = _blade(snapshots=[_snapshot(policies=("realm1::pol1",))])
        _run_main(module, blade)
        blade.delete_file_system_snapshots_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

        module = _module(detach_policies=["realm1::pol1"])
        blade = _blade(snapshots=[_snapshot(policies=("realm1::pol1",))])
        _run_main(module, blade)
        blade.delete_file_system_snapshots_policies.assert_called_once_with(
            member_names=["fs.snap"], policy_names=["realm1::pol1"]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_detach_all_policies_sends_every_attached_policy(self):
        module = _module(detach_policies=None, detach_all_policies=True)
        blade = _blade(snapshots=[_snapshot(policies=("pol1", "pol2"))])
        _run_main(module, blade)
        assert blade.delete_file_system_snapshots_policies.call_args_list == [
            call(member_names=["fs.snap"], policy_names=["pol1"]),
            call(member_names=["fs.snap"], policy_names=["pol2"]),
        ]
        module.exit_json.assert_called_once_with(changed=True)

    def test_detach_stops_at_the_first_refusal(self):
        """The refused policy is named; earlier detaches stay, later ones wait"""
        module = _module(detach_policies=None, detach_all_policies=True)
        blade = _blade(snapshots=[_snapshot(policies=("pol1", "pol2", "pol3"))])
        blade.delete_file_system_snapshots_policies.side_effect = [
            _response([], 200),
            _response([], 400),
        ]
        _run_main(module, blade, expect=FailJson)
        assert _fail_msg(module).startswith(
            "Failed to detach policy pol2 from snapshot fs.snap."
        )
        assert blade.delete_file_system_snapshots_policies.call_count == 2

    def test_detach_all_policies_unchanged_when_nothing_attached(self):
        module = _module(detach_policies=None, detach_all_policies=True)
        blade = _blade(snapshots=[_snapshot(policies=())])
        _run_main(module, blade)
        blade.delete_file_system_snapshots_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_detach_uses_policy_reference_before_rest_2_12(self):
        """Older arrays report only policy; the detach still works"""
        module = _module()
        snap = _snapshot()
        del snap.policies
        snap.policy = _ref("pol1")
        blade = _blade(snapshots=[snap])
        _run_main(module, blade, api_version="2.10")
        blade.delete_file_system_snapshots_policies.assert_called_once_with(
            member_names=["fs.snap"], policy_names=["pol1"]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_detach_check_mode_sends_nothing_but_reports_change(self):
        module = _module()
        module.check_mode = True
        blade = _blade(snapshots=[_snapshot()])
        _run_main(module, blade)
        blade.delete_file_system_snapshots_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_detach_passes_context_from_rest_2_17(self):
        module = _module(context="member1")
        blade = _blade(snapshots=[_snapshot()])
        _run_main(module, blade)
        blade.get_file_system_snapshots.assert_called_once_with(
            names_or_owner_names=["fs.snap"], context_names=["member1"]
        )
        blade.delete_file_system_snapshots_policies.assert_called_once_with(
            member_names=["fs.snap"], policy_names=["pol1"], context_names=["member1"]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_detach_ignores_context_before_rest_2_17(self):
        module = _module(context="member1")
        blade = _blade(snapshots=[_snapshot()])
        _run_main(module, blade, api_version="2.16")
        blade.get_file_system_snapshots.assert_called_once_with(
            names_or_owner_names=["fs.snap"]
        )
        blade.delete_file_system_snapshots_policies.assert_called_once_with(
            member_names=["fs.snap"], policy_names=["pol1"]
        )

    def test_detach_fails_when_snapshot_missing(self):
        module = _module()
        blade = _blade(snapshots=[])
        _run_main(module, blade, expect=FailJson)
        assert "Snapshot fs.snap does not exist" in _fail_msg(module)
        blade.delete_file_system_snapshots_policies.assert_not_called()
        blade.post_file_system_snapshots.assert_not_called()

    def test_detach_fails_when_snapshot_destroyed(self):
        module = _module()
        blade = _blade(snapshots=[_snapshot(destroyed=True)])
        _run_main(module, blade, expect=FailJson)
        assert "Snapshot fs.snap is destroyed" in _fail_msg(module)
        blade.delete_file_system_snapshots_policies.assert_not_called()
        blade.patch_file_system_snapshots.assert_not_called()

    def test_detach_fails_without_state_present(self):
        module = _module(state="absent")
        blade = _blade(snapshots=[_snapshot()])
        _run_main(module, blade, expect=FailJson)
        assert "require state=present" in _fail_msg(module)
        blade.delete_file_system_snapshots_policies.assert_not_called()
        blade.patch_file_system_snapshots.assert_not_called()

    def test_detach_fails_without_suffix(self):
        """A generated suffix never names a policy snapshot"""
        module = _module(suffix=None)
        blade = _blade(snapshots=[_snapshot()])
        _run_main(module, blade, expect=FailJson)
        assert "suffix is required" in _fail_msg(module)
        blade.delete_file_system_snapshots_policies.assert_not_called()

    def test_detach_fails_on_api_error(self):
        module = _module()
        blade = _blade(snapshots=[_snapshot()], delete_status=400)
        _run_main(module, blade, expect=FailJson)
        assert _fail_msg(module).startswith(
            "Failed to detach policy pol1 from snapshot fs.snap."
        )

    def test_detach_works_when_owning_filesystem_is_destroyed(self):
        """The snapshot is the member, not its filesystem"""
        module = _module()
        blade = _blade(snapshots=[_snapshot()])
        _run_main(module, blade, filesystem=_filesystem(destroyed=True))
        blade.delete_file_system_snapshots_policies.assert_called_once_with(
            member_names=["fs.snap"], policy_names=["pol1"]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_present_without_detach_options_is_unchanged(self):
        """Existing behaviour: state=present on an existing snapshot is a no-op"""
        module = _module(detach_policies=None)
        blade = _blade(snapshots=[_snapshot()])
        _run_main(module, blade)
        blade.delete_file_system_snapshots_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_present_without_detach_options_still_creates(self):
        """Existing behaviour: a missing snapshot is created"""
        module = _module(detach_policies=None)
        blade = _blade(snapshots=[])
        blade.get_array_connections.return_value = _response([])
        blade.post_file_system_snapshots.return_value = _response([])
        _run_main(module, blade)
        blade.post_file_system_snapshots.assert_called_once()
        blade.delete_file_system_snapshots_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)
