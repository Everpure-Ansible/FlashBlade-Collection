# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_eviction_policy module."""

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

from plugins.modules.purefb_eviction_policy import (
    main,
    _context_kwargs,
    _get_members,
    _get_policy,
    _keep_size_bytes,
)

MOD = "plugins.modules.purefb_eviction_policy"
GIB = 1073741824
# human_to_bytes lives in the mocked module_utils, so tests supply a fixed table.
SIZES = {"100G": 100 * GIB, "200G": 200 * GIB, "bad": 0}


def _fake_human_to_bytes(value):
    return SIZES.get(value, 0)


def _base_params(**overrides):
    params = {
        "name": "edge_cache",
        "state": "present",
        "enabled": None,
        "keep_size": None,
        "rename": None,
        "file_systems": None,
        "context": "",
    }
    params.update(overrides)
    return params


def _module(params, check_mode=False):
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.params = params
    module.check_mode = check_mode
    return module


def _response(status_code=200, items=None):
    res = Mock()
    res.status_code = status_code
    res.items = items if items is not None else []
    res.errors = []
    return res


def _policy(name="edge_cache", enabled=True, keep_size=100 * GIB):
    policy = Mock(spec=["name", "enabled", "keep_size", "is_local"])
    policy.name = name
    policy.enabled = enabled
    policy.keep_size = keep_size
    policy.is_local = True
    return policy


def _member(policy_name, fs_name):
    item = Mock(spec=["policy", "member"])
    item.policy = Mock(spec=["name"])
    item.policy.name = policy_name
    item.member = Mock(spec=["name"])
    item.member.name = fs_name
    return item


def _policies_by_name(existing):
    """Side effect for get_data_eviction_policies that filters on names."""

    def _get(names=None, **kwargs):
        return _response(items=[p for p in existing if p.name in (names or [])])

    return _get


def _swap_policies(blade, policies):
    """Side effect for a write that makes later lookups see C(policies)."""

    def _write(**kwargs):
        blade.get_data_eviction_policies.side_effect = _policies_by_name(policies)
        return _response()

    return _write


def _blade(existing=None, members=None):
    """Return a blade mock holding C(existing) policies with C(members) attached."""
    blade = Mock()
    blade.get_data_eviction_policies.side_effect = _policies_by_name(existing or [])
    blade.get_data_eviction_policies_file_systems.return_value = _response(
        items=members or []
    )
    blade.post_data_eviction_policies.return_value = _response()
    blade.patch_data_eviction_policies.return_value = _response()
    blade.delete_data_eviction_policies.return_value = _response()
    blade.post_data_eviction_policies_file_systems.return_value = _response()
    blade.delete_data_eviction_policies_file_systems.return_value = _response()
    return blade


def _run_main(params, blade, check_mode=False, old_api=False, sdk=True):
    """Run main() against a prepared blade mock.

    Returns (module, DataEvictionPolicyPost mock, DataEvictionPolicy mock).
    """
    module = _module(params, check_mode)
    with patch(MOD + ".HAS_PYPURECLIENT", sdk), patch(
        MOD + ".AnsibleModule", return_value=module
    ), patch(MOD + ".get_system", return_value=blade), patch(
        MOD + ".LooseVersion"
    ) as mock_loose_version, patch(
        MOD + ".DataEvictionPolicyPost"
    ) as mock_post_model, patch(
        MOD + ".DataEvictionPolicy"
    ) as mock_patch_model, patch(
        MOD + ".human_to_bytes", side_effect=_fake_human_to_bytes
    ), patch(
        MOD + ".get_error_message", return_value="array says no"
    ):
        mock_loose_version.return_value.__gt__ = Mock(return_value=old_api)
        try:
            main()
        except SystemExit:
            pass
    return module, mock_post_model, mock_patch_model


class TestPurefbEvictionPolicy:
    """Test cases for purefb_eviction_policy module"""

    # ---------------- helper-function unit tests ----------------

    def test_context_kwargs_returns_empty_without_context(self):
        """_context_kwargs returns {} when no context is set"""
        module = Mock()
        module.params = {"context": ""}
        assert _context_kwargs(module) == {}

    def test_context_kwargs_returns_kwargs_when_set(self):
        """_context_kwargs returns context_names when a context is set"""
        module = Mock()
        module.params = {"context": "peer1"}
        assert _context_kwargs(module) == {"context_names": ["peer1"]}

    def test_keep_size_bytes_none_when_unset(self):
        """_keep_size_bytes returns None when keep_size is not given"""
        module = _module(_base_params())
        assert _keep_size_bytes(module) is None

    def test_keep_size_bytes_plain_integer(self):
        """_keep_size_bytes treats a plain integer as bytes"""
        module = _module(_base_params(keep_size="1073741824"))
        with patch(MOD + ".human_to_bytes") as mock_h2b:
            assert _keep_size_bytes(module) == GIB
        mock_h2b.assert_not_called()

    def test_keep_size_bytes_human_size(self):
        """_keep_size_bytes converts a human size through human_to_bytes"""
        module = _module(_base_params(keep_size="100G"))
        with patch(MOD + ".human_to_bytes", side_effect=_fake_human_to_bytes) as h2b:
            assert _keep_size_bytes(module) == 100 * GIB
        h2b.assert_called_once_with("100G")

    def test_keep_size_bytes_invalid_fails(self):
        """_keep_size_bytes fails on a size human_to_bytes cannot parse"""
        module = _module(_base_params(keep_size="bad"))
        with patch(MOD + ".human_to_bytes", side_effect=_fake_human_to_bytes):
            try:
                _keep_size_bytes(module)
            except SystemExit:
                pass
        module.fail_json.assert_called_once()
        assert "not a valid size" in module.fail_json.call_args[1]["msg"]

    def test_get_policy_returns_first_item(self):
        """_get_policy returns the matching policy"""
        module = Mock()
        module.params = {"context": ""}
        policy = _policy()
        blade = _blade([policy])
        assert _get_policy(module, blade, "edge_cache") is policy
        blade.get_data_eviction_policies.assert_called_once_with(names=["edge_cache"])

    def test_get_policy_returns_none_when_missing(self):
        """_get_policy returns None when nothing matches"""
        module = Mock()
        module.params = {"context": ""}
        assert _get_policy(module, _blade([]), "edge_cache") is None

    def test_get_policy_returns_none_on_error(self):
        """_get_policy returns None on a non-200 response"""
        module = Mock()
        module.params = {"context": ""}
        blade = Mock()
        blade.get_data_eviction_policies.return_value = _response(status_code=400)
        assert _get_policy(module, blade, "edge_cache") is None

    def test_get_policy_passes_context(self):
        """_get_policy passes context_names when a context is set"""
        module = Mock()
        module.params = {"context": "peer1"}
        blade = _blade([])
        _get_policy(module, blade, "edge_cache")
        blade.get_data_eviction_policies.assert_called_once_with(
            names=["edge_cache"], context_names=["peer1"]
        )

    def test_get_members_returns_sorted_names(self):
        """_get_members returns the attached file system names sorted"""
        module = _module(_base_params())
        blade = _blade(
            members=[_member("edge_cache", "fs_b"), _member("edge_cache", "fs_a")]
        )
        assert _get_members(module, blade) == ["fs_a", "fs_b"]
        blade.get_data_eviction_policies_file_systems.assert_called_once_with(
            policy_names=["edge_cache"]
        )

    def test_get_members_fails_on_error(self):
        """_get_members surfaces a members read failure"""
        module = _module(_base_params())
        blade = Mock()
        blade.get_data_eviction_policies_file_systems.return_value = _response(
            status_code=400
        )
        with patch(MOD + ".get_error_message", return_value="boom"):
            try:
                _get_members(module, blade)
            except SystemExit:
                pass
        module.fail_json.assert_called_once()
        assert "Failed to list file systems" in module.fail_json.call_args[1]["msg"]

    # ---------------- create ----------------

    def test_main_creates_policy(self):
        """Create posts keep_size only and returns the new policy"""
        created = _policy()
        blade = _blade([])
        blade.post_data_eviction_policies.side_effect = _swap_policies(blade, [created])

        module, post_model, patch_model = _run_main(
            _base_params(keep_size="100G"), blade
        )

        post_model.assert_called_once_with(keep_size=100 * GIB)
        call_kwargs = blade.post_data_eviction_policies.call_args[1]
        assert call_kwargs["names"] == ["edge_cache"]
        assert call_kwargs["policy"] is post_model.return_value
        patch_model.assert_not_called()
        blade.post_data_eviction_policies_file_systems.assert_not_called()
        module.exit_json.assert_called_once()
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["policy"] == {
            "name": "edge_cache",
            "enabled": True,
            "keep_size": 100 * GIB,
            "file_systems": [],
        }

    def test_main_create_passes_enabled(self):
        """Create forwards an explicit enabled flag"""
        blade = _blade([])
        module, post_model, _patch_model = _run_main(
            _base_params(keep_size="100G", enabled=False), blade
        )
        post_model.assert_called_once_with(keep_size=100 * GIB, enabled=False)
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_create_requires_keep_size(self):
        """Create without keep_size fails before any write"""
        blade = _blade([])
        module, _post_model, _patch_model = _run_main(_base_params(), blade)
        module.fail_json.assert_called_once()
        assert "keep_size is required" in module.fail_json.call_args[1]["msg"]
        blade.post_data_eviction_policies.assert_not_called()

    def test_main_create_check_mode_skips_post(self):
        """Create in check mode reports changed without a POST"""
        blade = _blade([])
        module, post_model, _patch_model = _run_main(
            _base_params(keep_size="100G"), blade, check_mode=True
        )
        blade.post_data_eviction_policies.assert_not_called()
        post_model.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["policy"] == {}

    def test_main_create_fails_on_api_error(self):
        """Create surfaces the array error"""
        blade = _blade([])
        blade.post_data_eviction_policies.return_value = _response(status_code=400)
        module, _post_model, _patch_model = _run_main(
            _base_params(keep_size="100G"), blade
        )
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to create data eviction policy edge_cache" in msg
        assert "array says no" in msg

    def test_main_create_attaches_file_systems(self):
        """Create attaches each requested file system after the POST"""
        blade = _blade([])
        module, _post_model, _patch_model = _run_main(
            _base_params(keep_size="100G", file_systems=["fs_b", "fs_a"]), blade
        )
        calls = blade.post_data_eviction_policies_file_systems.call_args_list
        assert [c[1]["member_names"] for c in calls] == [["fs_a"], ["fs_b"]]
        assert all(c[1]["policy_names"] == ["edge_cache"] for c in calls)
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_create_attach_refused_surfaces_array_error(self):
        """A refused attach fails with the array's message and a created note"""
        blade = _blade([])
        blade.post_data_eviction_policies_file_systems.return_value = _response(
            status_code=400
        )
        module, _post_model, _patch_model = _run_main(
            _base_params(keep_size="100G", file_systems=["plain_fs"]), blade
        )
        blade.post_data_eviction_policies.assert_called_once()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to attach data eviction policy edge_cache" in msg
        assert "plain_fs" in msg
        assert "array says no" in msg
        assert "The policy was created" in msg

    # ---------------- update ----------------

    def test_main_updates_keep_size(self):
        """A different keep_size is patched"""
        blade = _blade([_policy()])
        module, post_model, patch_model = _run_main(
            _base_params(keep_size="200G"), blade
        )
        patch_model.assert_called_once_with(keep_size=200 * GIB)
        call_kwargs = blade.patch_data_eviction_policies.call_args[1]
        assert call_kwargs["names"] == ["edge_cache"]
        assert call_kwargs["policy"] is patch_model.return_value
        post_model.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_updates_enabled(self):
        """Disabling an enabled policy is patched"""
        blade = _blade([_policy()])
        module, _post_model, patch_model = _run_main(_base_params(enabled=False), blade)
        patch_model.assert_called_once_with(enabled=False)
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_idempotent_rerun(self):
        """Matching settings and members produce no writes"""
        blade = _blade([_policy()], members=[_member("edge_cache", "fs_a")])
        module, post_model, patch_model = _run_main(
            _base_params(keep_size="100G", enabled=True, file_systems=["fs_a"]),
            blade,
        )
        post_model.assert_not_called()
        patch_model.assert_not_called()
        blade.patch_data_eviction_policies.assert_not_called()
        blade.post_data_eviction_policies_file_systems.assert_not_called()
        blade.delete_data_eviction_policies_file_systems.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is False
        assert result["policy"]["file_systems"] == ["fs_a"]

    def test_main_update_check_mode_skips_patch(self):
        """Update in check mode reports changed without a PATCH"""
        blade = _blade([_policy()])
        module, _post_model, patch_model = _run_main(
            _base_params(keep_size="200G"), blade, check_mode=True
        )
        blade.patch_data_eviction_policies.assert_not_called()
        patch_model.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["policy"]["keep_size"] == 100 * GIB

    def test_main_update_fails_on_api_error(self):
        """Update surfaces the array error"""
        blade = _blade([_policy()])
        blade.patch_data_eviction_policies.return_value = _response(status_code=400)
        module, _post_model, _patch_model = _run_main(
            _base_params(keep_size="200G"), blade
        )
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to update data eviction policy edge_cache" in msg
        assert "array says no" in msg

    def test_main_update_invalid_keep_size_fails_before_patch(self):
        """An unparsable keep_size fails without a PATCH"""
        blade = _blade([_policy()])
        module, _post_model, _patch_model = _run_main(
            _base_params(keep_size="bad"), blade
        )
        module.fail_json.assert_called_once()
        assert "not a valid size" in module.fail_json.call_args[1]["msg"]
        blade.patch_data_eviction_policies.assert_not_called()

    def test_main_update_invalid_keep_size_fails_before_member_writes(self):
        """A bad keep_size with file_systems fails before any member call"""
        blade = _blade([_policy()], members=[_member("edge_cache", "fs_a")])
        module, _post_model, _patch_model = _run_main(
            _base_params(keep_size="bad", file_systems=["fs_b"]), blade
        )
        module.fail_json.assert_called_once()
        assert "not a valid size" in module.fail_json.call_args[1]["msg"]
        blade.get_data_eviction_policies_file_systems.assert_not_called()
        blade.post_data_eviction_policies_file_systems.assert_not_called()
        blade.delete_data_eviction_policies_file_systems.assert_not_called()
        blade.patch_data_eviction_policies.assert_not_called()

    # ---------------- rename ----------------

    def test_main_renames_policy(self):
        """Rename patches the name and reports under the new name"""
        old = _policy()
        new = _policy(name="site_b")
        blade = _blade([old])
        blade.patch_data_eviction_policies.side_effect = _swap_policies(blade, [new])
        module, _post_model, patch_model = _run_main(
            _base_params(rename="site_b"), blade
        )
        patch_model.assert_called_once_with(name="site_b")
        assert blade.patch_data_eviction_policies.call_args[1]["names"] == [
            "edge_cache"
        ]
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["policy"]["name"] == "site_b"
        assert blade.get_data_eviction_policies_file_systems.call_args[1] == {
            "policy_names": ["site_b"]
        }

    def test_main_rename_already_applied_is_idempotent(self):
        """A rename whose target already exists is a no-op"""
        blade = _blade([_policy(name="site_b")])
        module, _post_model, patch_model = _run_main(
            _base_params(rename="site_b"), blade
        )
        patch_model.assert_not_called()
        blade.patch_data_eviction_policies.assert_not_called()
        blade.post_data_eviction_policies.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is False
        assert result["policy"]["name"] == "site_b"

    def test_main_rename_missing_policy_fails(self):
        """Renaming a policy that exists under neither name fails"""
        blade = _blade([])
        module, _post_model, _patch_model = _run_main(
            _base_params(rename="site_b"), blade
        )
        module.fail_json.assert_called_once()
        assert "Cannot rename" in module.fail_json.call_args[1]["msg"]
        blade.post_data_eviction_policies.assert_not_called()

    # ---------------- members ----------------

    def test_main_reconciles_members(self):
        """Missing file systems are attached and extras detached"""
        blade = _blade(
            [_policy()],
            members=[_member("edge_cache", "fs_a"), _member("edge_cache", "fs_b")],
        )
        module, _post_model, patch_model = _run_main(
            _base_params(file_systems=["fs_b", "fs_c"]), blade
        )
        attach = blade.post_data_eviction_policies_file_systems
        detach = blade.delete_data_eviction_policies_file_systems
        attach.assert_called_once_with(
            policy_names=["edge_cache"], member_names=["fs_c"]
        )
        detach.assert_called_once_with(
            policy_names=["edge_cache"], member_names=["fs_a"]
        )
        patch_model.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_empty_file_systems_detaches_all(self):
        """An empty list detaches every member"""
        blade = _blade(
            [_policy()],
            members=[_member("edge_cache", "fs_a"), _member("edge_cache", "fs_b")],
        )
        module, _post_model, _patch_model = _run_main(
            _base_params(file_systems=[]), blade
        )
        detach = blade.delete_data_eviction_policies_file_systems
        assert [c[1]["member_names"] for c in detach.call_args_list] == [
            ["fs_a"],
            ["fs_b"],
        ]
        blade.post_data_eviction_policies_file_systems.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_members_check_mode_skips_writes(self):
        """Member reconciliation in check mode reports changed without writes"""
        blade = _blade([_policy()], members=[_member("edge_cache", "fs_a")])
        module, _post_model, _patch_model = _run_main(
            _base_params(file_systems=["fs_b"]), blade, check_mode=True
        )
        blade.post_data_eviction_policies_file_systems.assert_not_called()
        blade.delete_data_eviction_policies_file_systems.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["policy"]["file_systems"] == ["fs_a"]

    def test_main_attach_refused_on_update(self):
        """A refused attach on update surfaces the array's message"""
        blade = _blade([_policy()])
        blade.post_data_eviction_policies_file_systems.return_value = _response(
            status_code=400
        )
        module, _post_model, _patch_model = _run_main(
            _base_params(file_systems=["plain_fs"]), blade
        )
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to attach data eviction policy edge_cache" in msg
        assert "array says no" in msg
        assert "The policy was created" not in msg

    # ---------------- delete ----------------

    def test_main_deletes_policy(self):
        """Delete detaches members first, then deletes the policy"""
        blade = _blade([_policy()], members=[_member("edge_cache", "fs_a")])
        module, _post_model, _patch_model = _run_main(
            _base_params(state="absent"), blade
        )
        blade.delete_data_eviction_policies_file_systems.assert_called_once_with(
            policy_names=["edge_cache"], member_names=["fs_a"]
        )
        blade.delete_data_eviction_policies.assert_called_once_with(
            names=["edge_cache"]
        )
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert "policy" not in result

    def test_main_delete_check_mode_skips_delete(self):
        """Delete in check mode reports changed without a DELETE"""
        blade = _blade([_policy()])
        module, _post_model, _patch_model = _run_main(
            _base_params(state="absent"), blade, check_mode=True
        )
        blade.delete_data_eviction_policies.assert_not_called()
        blade.get_data_eviction_policies_file_systems.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_delete_absent_policy_is_idempotent(self):
        """Deleting a missing policy reports no change"""
        blade = _blade([])
        module, _post_model, _patch_model = _run_main(
            _base_params(state="absent"), blade
        )
        blade.delete_data_eviction_policies.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_main_delete_fails_on_api_error(self):
        """Delete surfaces the array error and notes detached members"""
        blade = _blade([_policy()], members=[_member("edge_cache", "fs_a")])
        blade.delete_data_eviction_policies.return_value = _response(status_code=400)
        module, _post_model, _patch_model = _run_main(
            _base_params(state="absent"), blade
        )
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to delete data eviction policy edge_cache" in msg
        assert "array says no" in msg
        assert "already been detached" in msg

    # ---------------- gates and context ----------------

    def test_main_fails_on_unsupported_api_version(self):
        """An array below REST 2.21 is refused before any read or write"""
        blade = _blade([])
        module, _post_model, _patch_model = _run_main(
            _base_params(keep_size="100G"), blade, old_api=True
        )
        module.fail_json.assert_called_once()
        assert "REST version not supported" in module.fail_json.call_args[1]["msg"]
        assert "2.21" in module.fail_json.call_args[1]["msg"]
        blade.get_data_eviction_policies.assert_not_called()
        blade.post_data_eviction_policies.assert_not_called()

    def test_main_fails_without_sdk(self):
        """Missing py-pure-client fails early"""
        blade = _blade([])
        module, _post_model, _patch_model = _run_main(
            _base_params(keep_size="100G"), blade, sdk=False
        )
        module.fail_json.assert_called_once()
        assert "py-pure-client" in module.fail_json.call_args[1]["msg"]
        blade.get_data_eviction_policies.assert_not_called()

    def test_main_passes_context_to_every_call(self):
        """A fleet context is forwarded as context_names on reads and writes"""
        blade = _blade([_policy()], members=[_member("edge_cache", "fs_a")])
        _run_main(
            _base_params(keep_size="200G", file_systems=[], context="peer1"), blade
        )
        for call in blade.get_data_eviction_policies.call_args_list:
            assert call[1]["context_names"] == ["peer1"]
        assert blade.get_data_eviction_policies_file_systems.call_args[1][
            "context_names"
        ] == ["peer1"]
        assert blade.delete_data_eviction_policies_file_systems.call_args[1][
            "context_names"
        ] == ["peer1"]
        assert blade.patch_data_eviction_policies.call_args[1]["context_names"] == [
            "peer1"
        ]
