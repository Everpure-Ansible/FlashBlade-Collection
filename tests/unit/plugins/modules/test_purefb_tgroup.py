# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_tgroup module."""

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

from plugins.modules.purefb_tgroup import (
    main,
    _build_members_payload,
    _context_kwargs,
    _error_text,
    _extract_members,
    _is_not_found,
    _missing_names,
    check_fleet_membership,
    fail_on_error,
    get_tgroup,
)

LOCAL = "fb-a"
PEER = "fa-b"
CONTEXT_REFUSED = "Parameter context_names is not supported in the target version."


def _base_params(**overrides):
    params = {
        "name": "app-stack",
        "state": "present",
        "rename": None,
        "parent": None,
        "array": None,
        "tgroup": None,
        "context": "",
    }
    params.update(overrides)
    return params


def _resp(status=200, items=None, errors=None):
    res = Mock()
    res.status_code = status
    res.items = items if items is not None else []
    res.errors = errors if errors is not None else []
    return res


def _err(message=None, context=None):
    err = Mock()
    err.message = message
    err.context = context
    return err


def _ref(name, resource_type=None):
    ref = Mock()
    ref.name = name
    ref.resource_type = resource_type
    return ref


def _tgroup(name, parent=None):
    tgroup = Mock()
    tgroup.name = name
    tgroup.parent_topology_group = _ref(parent, "topology-groups") if parent else None
    return tgroup


def _member(name, resource_type):
    member = Mock()
    member.member = _ref(name, resource_type)
    member.status = "joined"
    return member


def _module(**overrides):
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.warn = Mock()
    module.params = _base_params(**overrides)
    module.check_mode = False
    return module


def _blade(tgroups=None, members=None, remote_arrays=None, in_fleet=True):
    """Build a blade mock.

    tgroups: {name: tgroup mock}; members: {tgroup name: [member mocks]};
    remote_arrays: names returned by get_remote_arrays(current_fleet_only=True).
    """
    tgroups = tgroups or {}
    members = members or {}
    blade = Mock()
    blade.get_versions.return_value.items = ["2.17", "2.26"]
    blade.get_fleets.return_value = _resp(items=[_ref("fleet1")] if in_fleet else [])

    def get_tgroups(names=None, **kwargs):
        found = [tgroups[n] for n in names if n in tgroups]
        if len(found) != len(names):
            return _resp(400, errors=[_err("Topology group does not exist.")])
        return _resp(items=found)

    def get_members(topology_group_names=None, **kwargs):
        return _resp(items=list(members.get(topology_group_names[0], [])))

    blade.get_topology_groups.side_effect = get_tgroups
    blade.get_topology_groups_members.side_effect = get_members
    blade.get_remote_arrays.return_value = _resp(
        items=[_ref(name, "remote-arrays") for name in (remote_arrays or [])]
    )
    for method in (
        "post_topology_groups",
        "patch_topology_groups",
        "delete_topology_groups",
        "post_topology_groups_members",
        "delete_topology_groups_members",
    ):
        getattr(blade, method).return_value = _resp()
    return blade


def _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version):
    mock_loose_version.return_value.__gt__ = Mock(return_value=False)
    mock_ansible_module.return_value = module
    mock_get_system.return_value = blade
    try:
        main()
    except SystemExit:
        pass


class TestPurefbTgroupHelpers:
    """Helper-function unit tests"""

    def test_context_kwargs_returns_empty_without_context(self):
        module = Mock()
        module.params = {"context": ""}
        assert _context_kwargs(module) == {}

    def test_context_kwargs_returns_kwargs_when_set(self):
        module = Mock()
        module.params = {"context": "fleet1"}
        assert _context_kwargs(module) == {"context_names": ["fleet1"]}

    def test_extract_members_filters_by_resource_type(self):
        members = [
            _member(LOCAL, "remote-arrays"),
            _member("child", "topology-groups"),
            _member(PEER, "remote-arrays"),
        ]
        assert _extract_members(members, "remote-arrays") == [LOCAL, PEER]
        assert _extract_members(members, "topology-groups") == ["child"]

    def test_extract_members_skips_incomplete_entries(self):
        nameless = Mock()
        nameless.member = _ref(None, "remote-arrays")
        memberless = Mock()
        memberless.member = None
        assert _extract_members([nameless, memberless], "remote-arrays") == []

    def test_missing_names_reports_sorted_difference(self):
        items = [_ref("b"), _ref(None), _ref("a")]
        assert _missing_names(["c", "a", "d"], items) == ["c", "d"]
        assert _missing_names(None, items) == []

    def test_error_text_renders_message_and_context(self):
        res = _resp(400, errors=[_err("bad", "ctx"), _err(None, "only ctx")])
        assert _error_text(res) == "bad (ctx); only ctx"

    def test_error_text_without_errors_reports_status(self):
        assert _error_text(_resp(500)) == "HTTP 500 with no error detail"

    def test_fail_on_error_ignores_success(self):
        module = Mock()
        fail_on_error(_resp(200), module, "op")
        module.fail_json.assert_not_called()

    def test_fail_on_error_reports_operation_and_error(self):
        module = Mock()
        fail_on_error(_resp(400, errors=[_err("nope")]), module, "Create failed")
        module.fail_json.assert_called_once()
        kwargs = module.fail_json.call_args[1]
        assert kwargs["msg"] == "Create failed. Error: nope"
        assert kwargs["status_code"] == 400
        assert "directory-backed" not in kwargs["msg"]

    def test_fail_on_error_adds_permission_hint_on_403(self):
        module = Mock()
        fail_on_error(_resp(403, errors=[_err("Forbidden")]), module, "Create failed")
        msg = module.fail_json.call_args[1]["msg"]
        assert msg.startswith("Create failed. Error: Forbidden")
        assert "directory-backed" in msg
        assert "local users and API clients" in msg

    def test_fail_on_error_adds_permission_hint_on_not_permitted(self):
        # Purity//FB answers a local identity with 400 "Operation not permitted."
        module = Mock()
        fail_on_error(
            _resp(400, errors=[_err("Operation not permitted.")]),
            module,
            "Create failed",
        )
        msg = module.fail_json.call_args[1]["msg"]
        assert msg.startswith("Create failed. Error: Operation not permitted.")
        assert "directory-backed" in msg
        assert module.fail_json.call_args[1]["status_code"] == 400

    def test_fail_on_error_adds_context_hint_when_context_refused(self):
        # Purity//FB refuses context_names on /topology-groups
        module = Mock()
        fail_on_error(_resp(400, errors=[_err(CONTEXT_REFUSED)]), module, "Read failed")
        msg = module.fail_json.call_args[1]["msg"]
        assert msg.startswith("Read failed. Error: " + CONTEXT_REFUSED)
        assert "retry without the context option" in msg
        assert "directory-backed" not in msg

    def test_is_not_found_recognises_missing_object_text(self):
        assert _is_not_found(
            _resp(400, errors=[_err("Topology group does not exist.")])
        )
        assert _is_not_found(_resp(400, errors=[_err(None, "Group not found")]))
        assert not _is_not_found(_resp(400, errors=[_err(CONTEXT_REFUSED)]))
        assert not _is_not_found(_resp(400, errors=[_err("Syntax error in query")]))
        assert not _is_not_found(_resp(400))

    def test_get_tgroup_returns_none_on_empty_200(self):
        # Purity//FB shape for an unknown name
        module = Mock()
        module.params = _base_params()
        blade = Mock()
        blade.get_topology_groups.return_value = _resp(items=[])
        assert get_tgroup(module, blade) is None
        blade.get_topology_groups.assert_called_once_with(names=["app-stack"])
        module.fail_json.assert_not_called()

    def test_get_tgroup_returns_none_on_does_not_exist_400(self):
        # FlashArray shape for an unknown name
        module = Mock()
        module.params = _base_params()
        blade = Mock()
        blade.get_topology_groups.return_value = _resp(
            400, errors=[_err("Topology group does not exist.")]
        )
        assert get_tgroup(module, blade, "ghost") is None
        blade.get_topology_groups.assert_called_once_with(names=["ghost"])
        module.fail_json.assert_not_called()

    def test_get_tgroup_fails_on_unexpected_400(self):
        module = Mock()
        module.params = _base_params()
        module.fail_json = Mock(side_effect=SystemExit)
        blade = Mock()
        blade.get_topology_groups.return_value = _resp(
            400, errors=[_err("Syntax error in query")]
        )
        try:
            get_tgroup(module, blade)
        except SystemExit:
            pass
        kwargs = module.fail_json.call_args[1]
        assert kwargs["msg"] == (
            "Failed to read topology group app-stack. Error: Syntax error in query"
        )
        assert kwargs["status_code"] == 400

    def test_check_fleet_membership_passes_inside_fleet(self):
        module = Mock()
        blade = Mock()
        blade.get_fleets.return_value = _resp(items=[_ref("fleet1")])
        check_fleet_membership(module, blade)
        module.fail_json.assert_not_called()

    def test_check_fleet_membership_fails_outside_fleet(self):
        module = Mock()
        module.fail_json = Mock(side_effect=SystemExit)
        blade = Mock()
        blade.get_fleets.return_value = _resp(items=[])
        try:
            check_fleet_membership(module, blade)
        except SystemExit:
            pass
        assert "member of a fleet" in module.fail_json.call_args[1]["msg"]

    def test_check_fleet_membership_fails_when_fusion_disabled(self):
        module = Mock()
        module.fail_json = Mock(side_effect=SystemExit)
        blade = Mock()
        blade.get_fleets.return_value = _resp(404)
        try:
            check_fleet_membership(module, blade)
        except SystemExit:
            pass
        assert "Fusion is not enabled" in module.fail_json.call_args[1]["msg"]

    @patch("plugins.modules.purefb_tgroup.TgroupMembersPost")
    @patch("plugins.modules.purefb_tgroup.TgroupMembersPostMember")
    @patch("plugins.modules.purefb_tgroup.ReferenceWritable")
    def test_build_members_payload_types_members(
        self, mock_reference, mock_post_member, mock_members_post
    ):
        _build_members_payload([PEER, LOCAL, LOCAL], ["child"])
        reference_calls = [c[1] for c in mock_reference.call_args_list]
        # arrays first (sorted, de-duplicated), then child groups
        assert reference_calls == [
            {"name": PEER, "resource_type": "remote-arrays"},
            {"name": LOCAL, "resource_type": "remote-arrays"},
            {"name": "child", "resource_type": "topology-groups"},
        ]
        assert mock_post_member.call_count == 3
        mock_members_post.assert_called_once()
        assert len(mock_members_post.call_args[1]["members"]) == 3


class TestPurefbTgroupMain:
    """main() flows"""

    # ---------------- create ----------------

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_creates_tgroup(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module()
        blade = _blade()
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.post_topology_groups.assert_called_once_with(names=["app-stack"])
        blade.post_topology_groups_members.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_tgroup.TgroupMembersPost")
    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_creates_tgroup_with_parent_and_members(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_payload
    ):
        module = _module(parent="root", array=[LOCAL], tgroup=["child"])
        blade = _blade(
            tgroups={"root": _tgroup("root"), "child": _tgroup("child")},
            remote_arrays=[LOCAL],
        )
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.post_topology_groups.assert_called_once_with(
            names=["app-stack"], parent_topology_group_names=["root"]
        )
        blade.get_remote_arrays.assert_called_once_with(current_fleet_only=True)
        blade.post_topology_groups_members.assert_called_once()
        kwargs = blade.post_topology_groups_members.call_args[1]
        assert kwargs["topology_group_names"] == ["app-stack"]
        assert kwargs["members"] is mock_payload.return_value
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_create_check_mode_skips_post(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(array=[LOCAL])
        module.check_mode = True
        blade = _blade(remote_arrays=[LOCAL])
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.post_topology_groups.assert_not_called()
        blade.post_topology_groups_members.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_create_fails_on_api_error(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module()
        blade = _blade()
        blade.post_topology_groups.return_value = _resp(
            400, errors=[_err(None, "Invalid name")]
        )
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert msg == "Failed to create topology group app-stack. Error: Invalid name"
        module.exit_json.assert_not_called()

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_create_forbidden_explains_identity(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module()
        blade = _blade()
        blade.post_topology_groups.return_value = _resp(403, errors=[])
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        msg = module.fail_json.call_args[1]["msg"]
        assert "HTTP 403" in msg
        assert "directory-backed" in msg

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_create_with_rename_fails(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(rename="other")
        blade = _blade()
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.post_topology_groups.assert_not_called()
        assert "rename failed" in module.fail_json.call_args[1]["msg"]

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_rename_already_done_is_noop(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(rename="app-stack-qa")
        blade = _blade(tgroups={"app-stack-qa": _tgroup("app-stack-qa")})
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.post_topology_groups.assert_not_called()
        blade.patch_topology_groups.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    # ---------------- update ----------------

    @patch("plugins.modules.purefb_tgroup.NewName")
    @patch("plugins.modules.purefb_tgroup.TgroupPatch")
    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_renames_tgroup(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_patch,
        mock_new_name,
    ):
        module = _module(rename="app-stack-qa")
        blade = _blade(tgroups={"app-stack": _tgroup("app-stack")})
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        mock_new_name.assert_called_once_with(name="app-stack-qa")
        mock_patch.assert_called_once_with(topology_group=mock_new_name.return_value)
        blade.patch_topology_groups.assert_called_once_with(
            names=["app-stack"], topology_group=mock_patch.return_value
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_rename_to_existing_name_warns(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(rename="taken")
        blade = _blade(
            tgroups={"app-stack": _tgroup("app-stack"), "taken": _tgroup("taken")}
        )
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        module.warn.assert_called_once()
        assert "taken" in module.warn.call_args[0][0]
        blade.patch_topology_groups.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_tgroup.TgroupPatch")
    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_moves_tgroup_under_parent(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_patch
    ):
        module = _module(parent="root")
        blade = _blade(
            tgroups={"app-stack": _tgroup("app-stack"), "root": _tgroup("root")}
        )
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        mock_patch.assert_called_once_with()
        blade.patch_topology_groups.assert_called_once_with(
            names=["app-stack"],
            topology_group=mock_patch.return_value,
            to_parent_topology_group_names=["root"],
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_tgroup.NewName")
    @patch("plugins.modules.purefb_tgroup.TgroupPatch")
    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_rename_and_move_are_separate_patches(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_patch,
        mock_new_name,
    ):
        module = _module(rename="app-stack-qa", parent="root")
        blade = _blade(
            tgroups={"app-stack": _tgroup("app-stack"), "root": _tgroup("root")}
        )
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        assert blade.patch_topology_groups.call_count == 2
        rename_call, move_call = blade.patch_topology_groups.call_args_list
        assert rename_call[1]["names"] == ["app-stack"]
        assert "to_parent_topology_group_names" not in rename_call[1]
        # the move addresses the group by its new name
        assert move_call[1]["names"] == ["app-stack-qa"]
        assert move_call[1]["to_parent_topology_group_names"] == ["root"]
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_parent_already_set_is_noop(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(parent="root")
        blade = _blade(
            tgroups={
                "app-stack": _tgroup("app-stack", parent="root"),
                "root": _tgroup("root"),
            }
        )
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.patch_topology_groups.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_tgroup.TgroupMembersPost")
    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_adds_missing_members_only(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_payload
    ):
        module = _module(array=[LOCAL, PEER], tgroup=["child"])
        blade = _blade(
            tgroups={"app-stack": _tgroup("app-stack"), "child": _tgroup("child")},
            members={"app-stack": [_member(LOCAL, "remote-arrays")]},
            remote_arrays=[LOCAL, PEER],
        )
        with patch(
            "plugins.modules.purefb_tgroup._build_members_payload",
            return_value=mock_payload,
        ) as mock_build:
            _run(
                module, blade, mock_ansible_module, mock_get_system, mock_loose_version
            )

        mock_build.assert_called_once_with([PEER], ["child"])
        blade.post_topology_groups_members.assert_called_once_with(
            topology_group_names=["app-stack"], members=mock_payload
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_members_present_is_noop(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(array=[LOCAL], tgroup=["child"])
        blade = _blade(
            tgroups={"app-stack": _tgroup("app-stack"), "child": _tgroup("child")},
            members={
                "app-stack": [
                    _member(LOCAL, "remote-arrays"),
                    _member("child", "topology-groups"),
                ]
            },
            remote_arrays=[LOCAL],
        )
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.post_topology_groups_members.assert_not_called()
        blade.patch_topology_groups.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_add_members_check_mode(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(array=[PEER])
        module.check_mode = True
        blade = _blade(
            tgroups={"app-stack": _tgroup("app-stack")}, remote_arrays=[PEER]
        )
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.post_topology_groups_members.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_add_members_fails_on_api_error(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(array=[PEER])
        blade = _blade(
            tgroups={"app-stack": _tgroup("app-stack")}, remote_arrays=[PEER]
        )
        blade.post_topology_groups_members.return_value = _resp(
            400, errors=[_err("Array is already a member of another group")]
        )
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        msg = module.fail_json.call_args[1]["msg"]
        assert msg.startswith("Failed to add members to topology group app-stack")
        assert "another group" in msg

    # ---------------- absent ----------------

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_absent_removes_listed_members_only(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(state="absent", array=[LOCAL, PEER], tgroup=["child"])
        blade = _blade(
            tgroups={"app-stack": _tgroup("app-stack"), "child": _tgroup("child")},
            members={
                "app-stack": [
                    _member(LOCAL, "remote-arrays"),
                    _member("child", "topology-groups"),
                ]
            },
            remote_arrays=[LOCAL, PEER],
        )
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.delete_topology_groups_members.assert_called_once_with(
            topology_group_names=["app-stack"], member_names=[LOCAL, "child"]
        )
        blade.delete_topology_groups.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_absent_members_already_gone_is_noop(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(state="absent", array=[PEER])
        blade = _blade(
            tgroups={"app-stack": _tgroup("app-stack")},
            members={"app-stack": [_member(LOCAL, "remote-arrays")]},
            remote_arrays=[LOCAL, PEER],
        )
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.delete_topology_groups_members.assert_not_called()
        blade.delete_topology_groups.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_deletes_tgroup(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(state="absent")
        blade = _blade(tgroups={"app-stack": _tgroup("app-stack")})
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.delete_topology_groups.assert_called_once_with(names=["app-stack"])
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_delete_surfaces_error_context(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(state="absent")
        blade = _blade(tgroups={"app-stack": _tgroup("app-stack")})
        blade.delete_topology_groups.return_value = _resp(
            400, errors=[_err(None, "Topology group is referenced by preset p1")]
        )
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        msg = module.fail_json.call_args[1]["msg"]
        assert msg == (
            "Failed to delete topology group app-stack. "
            "Error: Topology group is referenced by preset p1"
        )

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_delete_check_mode_skips_call(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(state="absent")
        module.check_mode = True
        blade = _blade(tgroups={"app-stack": _tgroup("app-stack")})
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.delete_topology_groups.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_delete_nonexistent_is_noop(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(state="absent")
        blade = _blade()
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.delete_topology_groups.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    # ---------------- validation ----------------

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_rejects_self_as_parent(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(parent="app-stack")
        blade = _blade()
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        assert "its own parent" in module.fail_json.call_args[1]["msg"]
        blade.post_topology_groups.assert_not_called()

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_rejects_parent_that_is_also_child(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(parent="root", tgroup=["root"])
        blade = _blade(tgroups={"root": _tgroup("root")})
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        assert "both parent and child" in module.fail_json.call_args[1]["msg"]

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_rejects_missing_parent(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(parent="ghost")
        blade = _blade()
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        assert (
            module.fail_json.call_args[1]["msg"]
            == "Parent topology group ghost does not exist."
        )

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_rejects_move_under_direct_child(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(parent="child")
        blade = _blade(
            tgroups={"app-stack": _tgroup("app-stack"), "child": _tgroup("child")},
            members={"app-stack": [_member("child", "topology-groups")]},
        )
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        assert "direct child" in module.fail_json.call_args[1]["msg"]
        blade.patch_topology_groups.assert_not_called()

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_rejects_missing_child(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(tgroup=["ghost"])
        blade = _blade(tgroups={"app-stack": _tgroup("app-stack")})
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        assert "Child topology group not found" in module.fail_json.call_args[1]["msg"]
        blade.post_topology_groups_members.assert_not_called()

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_rejects_array_outside_fleet(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(array=[LOCAL, "stranger"])
        blade = _blade(remote_arrays=[LOCAL])
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        assert module.fail_json.call_args[1]["msg"] == "Array not found: stranger"
        blade.post_topology_groups.assert_not_called()

    # ---------------- preconditions ----------------

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_fails_on_unsupported_api_version(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)
        module = _module()
        blade = _blade()
        blade.get_versions.return_value.items = ["2.17", "2.25"]
        mock_ansible_module.return_value = module
        mock_get_system.return_value = blade
        try:
            main()
        except SystemExit:
            pass

        msg = module.fail_json.call_args[1]["msg"]
        assert "REST version not supported" in msg
        assert "2.26" in msg
        blade.get_fleets.assert_not_called()
        blade.get_topology_groups.assert_not_called()

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_fails_outside_fleet_before_any_write(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module()
        blade = _blade(in_fleet=False)
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        assert "member of a fleet" in module.fail_json.call_args[1]["msg"]
        blade.get_topology_groups.assert_not_called()
        blade.post_topology_groups.assert_not_called()

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", False)
    def test_main_fails_without_sdk(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module()
        _run(module, Mock(), mock_ansible_module, mock_get_system, mock_loose_version)

        assert "py-pure-client" in module.fail_json.call_args[1]["msg"]
        mock_get_system.assert_not_called()

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_passes_context_to_every_tgroup_call(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(state="absent", context="fleet1")
        blade = _blade(tgroups={"app-stack": _tgroup("app-stack")})
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.get_topology_groups.assert_called_once_with(
            names=["app-stack"], context_names=["fleet1"]
        )
        blade.get_topology_groups_members.assert_called_once_with(
            topology_group_names=["app-stack"], context_names=["fleet1"]
        )
        blade.delete_topology_groups.assert_called_once_with(
            names=["app-stack"], context_names=["fleet1"]
        )
        # fleet membership is a local question, never context-scoped
        blade.get_fleets.assert_called_once_with()

    # ---------------- convergence and read failures ----------------

    @patch("plugins.modules.purefb_tgroup.TgroupPatch")
    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_rename_already_done_converges_parent_and_members(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_patch
    ):
        # An earlier run renamed the group; parent and members still converge
        module = _module(rename="app-stack-qa", parent="root", array=[PEER])
        blade = _blade(
            tgroups={"app-stack-qa": _tgroup("app-stack-qa"), "root": _tgroup("root")},
            remote_arrays=[PEER],
        )
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.post_topology_groups.assert_not_called()
        blade.get_topology_groups_members.assert_called_once_with(
            topology_group_names=["app-stack-qa"]
        )
        blade.patch_topology_groups.assert_called_once_with(
            names=["app-stack-qa"],
            topology_group=mock_patch.return_value,
            to_parent_topology_group_names=["root"],
        )
        kwargs = blade.post_topology_groups_members.call_args[1]
        assert kwargs["topology_group_names"] == ["app-stack-qa"]
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_read_forbidden_explains_identity(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module()
        blade = _blade()
        blade.get_topology_groups.side_effect = None
        blade.get_topology_groups.return_value = _resp(403, errors=[])
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        msg = module.fail_json.call_args[1]["msg"]
        assert msg.startswith("Failed to read topology group app-stack")
        assert "directory-backed" in msg
        blade.post_topology_groups.assert_not_called()

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_read_not_permitted_explains_identity(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module()
        blade = _blade()
        blade.get_topology_groups.side_effect = None
        blade.get_topology_groups.return_value = _resp(
            400, errors=[_err("Operation not permitted.")]
        )
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        msg = module.fail_json.call_args[1]["msg"]
        assert msg.startswith("Failed to read topology group app-stack")
        assert "directory-backed" in msg
        blade.post_topology_groups.assert_not_called()

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_absent_with_refused_context_fails_instead_of_ok(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        # The array refuses context_names on /topology-groups: that is a
        # failed read, not "group already gone"
        module = _module(state="absent", context="fleet1")
        blade = _blade(tgroups={"app-stack": _tgroup("app-stack")})
        blade.get_topology_groups.side_effect = None
        blade.get_topology_groups.return_value = _resp(
            400, errors=[_err(CONTEXT_REFUSED)]
        )
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.get_topology_groups.assert_called_once_with(
            names=["app-stack"], context_names=["fleet1"]
        )
        msg = module.fail_json.call_args[1]["msg"]
        assert msg.startswith(
            "Failed to read topology group app-stack. Error: " + CONTEXT_REFUSED
        )
        assert "retry without the context option" in msg
        blade.delete_topology_groups.assert_not_called()
        module.exit_json.assert_not_called()

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_present_with_refused_context_does_not_create(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(parent="root", context="fleet1")
        blade = _blade(tgroups={"app-stack": _tgroup("app-stack")})
        blade.get_topology_groups.side_effect = None
        blade.get_topology_groups.return_value = _resp(
            400, errors=[_err(CONTEXT_REFUSED)]
        )
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        msg = module.fail_json.call_args[1]["msg"]
        assert msg.startswith("Failed to read topology group app-stack")
        assert "retry without the context option" in msg
        # neither a misleading "parent does not exist" nor a create attempt
        blade.get_topology_groups.assert_called_once()
        blade.post_topology_groups.assert_not_called()
        blade.patch_topology_groups.assert_not_called()
        module.exit_json.assert_not_called()

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_read_unexpected_error_does_not_create(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module()
        blade = _blade()
        blade.get_topology_groups.side_effect = None
        blade.get_topology_groups.return_value = _resp(
            400, errors=[_err("Syntax error in query")]
        )
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        msg = module.fail_json.call_args[1]["msg"]
        assert msg == (
            "Failed to read topology group app-stack. Error: Syntax error in query"
        )
        blade.post_topology_groups.assert_not_called()
        module.exit_json.assert_not_called()

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_creates_when_read_returns_empty_200(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        # Purity//FB answers an unknown name with 200 and no items
        module = _module()
        blade = _blade()
        blade.get_topology_groups.side_effect = None
        blade.get_topology_groups.return_value = _resp(items=[])
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.post_topology_groups.assert_called_once_with(names=["app-stack"])
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_members_read_error_fails(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(state="absent", array=[LOCAL])
        blade = _blade(tgroups={"app-stack": _tgroup("app-stack")})
        blade.get_topology_groups_members.side_effect = None
        blade.get_topology_groups_members.return_value = _resp(
            500, errors=[_err("Internal error")]
        )
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        msg = module.fail_json.call_args[1]["msg"]
        assert msg == (
            "Failed to read members of topology group app-stack. "
            "Error: Internal error"
        )
        blade.delete_topology_groups_members.assert_not_called()
        module.exit_json.assert_not_called()

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_absent_removes_stale_member_without_fleet_lookup(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        # PEER has left the fleet but is still listed as a member
        module = _module(state="absent", array=[PEER])
        blade = _blade(
            tgroups={"app-stack": _tgroup("app-stack")},
            members={"app-stack": [_member(PEER, "remote-arrays")]},
            remote_arrays=[LOCAL],
        )
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.get_remote_arrays.assert_not_called()
        blade.delete_topology_groups_members.assert_called_once_with(
            topology_group_names=["app-stack"], member_names=[PEER]
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_tgroup.LooseVersion")
    @patch("plugins.modules.purefb_tgroup.get_system")
    @patch("plugins.modules.purefb_tgroup.AnsibleModule")
    @patch("plugins.modules.purefb_tgroup.HAS_PYPURECLIENT", True)
    def test_main_present_skips_lookup_for_existing_members(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(array=[LOCAL], tgroup=["child"])
        blade = _blade(
            tgroups={"app-stack": _tgroup("app-stack"), "child": _tgroup("child")},
            members={
                "app-stack": [
                    _member(LOCAL, "remote-arrays"),
                    _member("child", "topology-groups"),
                ]
            },
        )
        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.get_remote_arrays.assert_not_called()
        blade.get_topology_groups.assert_called_once_with(names=["app-stack"])
        module.exit_json.assert_called_once_with(changed=False)
