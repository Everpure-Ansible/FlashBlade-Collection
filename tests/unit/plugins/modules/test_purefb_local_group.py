# Copyright: (c) 2026, Pure Storage Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_local_group module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
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

from plugins.modules.purefb_local_group import (
    main,
    _get_group,
    _get_current_user_members,
    _missing,
    _reconcile_user_members,
    _same_group,
)


def _base_params(**overrides):
    params = {
        "name": "developers",
        "state": "present",
        "local_directory_service": "myserver_local",
        "new_name": None,
        "gid": None,
        "email": None,
        "local_users": None,
        "force": False,
        "context": "",
    }
    params.update(overrides)
    return params


def _found_lds(blade):
    """Let the read of the local directory service find it."""
    lds = Mock()
    lds.name = "myserver_local"
    response = Mock()
    response.status_code = 200
    response.items = [lds]
    blade.get_directory_services_local_directory_services.return_value = response
    return blade


class TestPurefbLocalGroup:
    """Test cases for purefb_local_group module"""

    # ---------------- helper-function unit tests ----------------

    def test_get_group_returns_first_item(self):
        """_get_group returns the first hit"""
        module = Mock()
        module.params = {"name": "developers", "context": ""}

        existing = Mock()
        existing.name = "developers"
        response = Mock()
        response.status_code = 200
        response.items = [existing]

        blade = Mock()
        blade.get_directory_services_local_groups.return_value = response

        assert _get_group(module, blade, "myserver_local") is existing
        blade.get_directory_services_local_groups.assert_called_once_with(
            names=["developers"],
            filter="local_directory_service.name='myserver_local'",
        )

    def test_get_group_returns_none_when_empty(self):
        """_get_group returns None when items is empty"""
        module = Mock()
        module.params = {"name": "developers", "context": ""}

        response = Mock()
        response.status_code = 200
        response.items = []
        blade = Mock()
        blade.get_directory_services_local_groups.return_value = response

        assert _get_group(module, blade, "myserver_local") is None

    def test_get_current_user_members_extracts_names(self):
        """_get_current_user_members returns the set of user-member names"""
        module = Mock()
        module.params = {"name": "developers", "context": ""}
        module.fail_json = Mock(side_effect=SystemExit)

        edge_a = Mock()
        edge_a.member = Mock()
        edge_a.member.name = "alice"
        edge_b = Mock()
        edge_b.member = Mock()
        edge_b.member.name = "bob"

        response = Mock()
        response.status_code = 200
        response.items = [edge_a, edge_b]
        blade = Mock()
        blade.get_directory_services_local_groups_members.return_value = response

        result = _get_current_user_members(
            module, blade, "myserver_local", group_name="developers"
        )
        assert result == {"alice", "bob"}
        blade.get_directory_services_local_groups_members.assert_called_once_with(
            group_names=["developers"],
            filter="local_directory_service.name='myserver_local'",
            member_types=["User"],
        )

    # ---------------- _reconcile_user_members tests ----------------

    def test_reconcile_adds_missing_members(self):
        """_reconcile_user_members POSTs users not yet in the group"""
        module = Mock()
        module.params = {
            "name": "developers",
            "local_users": ["alice", "bob"],
            "context": "",
        }
        module.check_mode = False
        module.fail_json = Mock(side_effect=SystemExit)

        current_response = Mock()
        current_response.status_code = 200
        current_response.items = []
        post_response = Mock()
        post_response.status_code = 200

        blade = Mock()
        blade.get_directory_services_local_groups_members.return_value = (
            current_response
        )
        blade.post_directory_services_local_groups_members.return_value = post_response

        changed = _reconcile_user_members(module, blade, "myserver_local", "developers")
        assert changed is True
        blade.post_directory_services_local_groups_members.assert_called_once()
        blade.delete_directory_services_local_groups_members.assert_not_called()

    def test_reconcile_removes_extras(self):
        """_reconcile_user_members DELETEs users no longer in the desired list"""
        module = Mock()
        module.params = {
            "name": "developers",
            "local_users": ["alice"],
            "context": "",
        }
        module.check_mode = False
        module.fail_json = Mock(side_effect=SystemExit)

        alice = Mock()
        alice.member = Mock()
        alice.member.name = "alice"
        bob = Mock()
        bob.member = Mock()
        bob.member.name = "bob"

        current_response = Mock()
        current_response.status_code = 200
        current_response.items = [alice, bob]
        delete_response = Mock()
        delete_response.status_code = 200

        blade = Mock()
        blade.get_directory_services_local_groups_members.return_value = (
            current_response
        )
        blade.delete_directory_services_local_groups_members.return_value = (
            delete_response
        )

        changed = _reconcile_user_members(module, blade, "myserver_local", "developers")
        assert changed is True
        blade.delete_directory_services_local_groups_members.assert_called_once()
        blade.post_directory_services_local_groups_members.assert_not_called()

    def test_reconcile_idempotent_when_match(self):
        """_reconcile_user_members is a no-op when current == desired"""
        module = Mock()
        module.params = {
            "name": "developers",
            "local_users": ["alice"],
            "context": "",
        }
        module.check_mode = False
        module.fail_json = Mock(side_effect=SystemExit)

        alice = Mock()
        alice.member = Mock()
        alice.member.name = "alice"
        current_response = Mock()
        current_response.status_code = 200
        current_response.items = [alice]

        blade = Mock()
        blade.get_directory_services_local_groups_members.return_value = (
            current_response
        )

        changed = _reconcile_user_members(module, blade, "myserver_local", "developers")
        assert changed is False
        blade.post_directory_services_local_groups_members.assert_not_called()
        blade.delete_directory_services_local_groups_members.assert_not_called()

    def test_reconcile_check_mode_skips_writes(self):
        """_reconcile_user_members reports changed but skips writes in check mode"""
        module = Mock()
        module.params = {
            "name": "developers",
            "local_users": ["alice"],
            "context": "",
        }
        module.check_mode = True
        module.fail_json = Mock(side_effect=SystemExit)

        current_response = Mock()
        current_response.status_code = 200
        current_response.items = []

        blade = Mock()
        blade.get_directory_services_local_groups_members.return_value = (
            current_response
        )

        changed = _reconcile_user_members(module, blade, "myserver_local", "developers")
        assert changed is True
        blade.post_directory_services_local_groups_members.assert_not_called()
        blade.delete_directory_services_local_groups_members.assert_not_called()

    # ---------------- main() flows ----------------

    @patch("plugins.modules.purefb_local_group.LooseVersion")
    @patch("plugins.modules.purefb_local_group.LocalGroupPost")
    @patch("plugins.modules.purefb_local_group.get_system")
    @patch("plugins.modules.purefb_local_group.AnsibleModule")
    @patch("plugins.modules.purefb_local_group.HAS_PYPURECLIENT", True)
    def test_main_creates_group(
        self, mock_ansible_module, mock_get_system, mock_group_post, mock_loose_version
    ):
        """Test creating a new local group with gid and email"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(gid=6001, email="devs@example.com")
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = _found_lds(Mock())
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        # Group doesn't exist
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        blade.get_directory_services_local_groups.return_value = get_response

        created = Mock()
        created.name = "developers"
        created.gid = 6001
        created.sid = "S-1-5-21-1"
        created.built_in = False

        post_response = Mock()
        post_response.status_code = 200
        post_response.items = [created]
        blade.post_directory_services_local_groups.return_value = post_response

        try:
            main()
        except SystemExit:
            pass

        blade.post_directory_services_local_groups.assert_called_once()
        call_kwargs = blade.post_directory_services_local_groups.call_args[1]
        assert call_kwargs["names"] == ["developers"]
        assert call_kwargs["local_directory_service_names"] == ["myserver_local"]
        mock_group_post.assert_called_once_with(email="devs@example.com", gid=6001)
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_local_group.LooseVersion")
    @patch("plugins.modules.purefb_local_group.get_system")
    @patch("plugins.modules.purefb_local_group.AnsibleModule")
    @patch("plugins.modules.purefb_local_group.HAS_PYPURECLIENT", True)
    def test_main_create_check_mode_skips_post(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test create reports changed but skips POST in check mode"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params()
        module.check_mode = True
        mock_ansible_module.return_value = module

        blade = _found_lds(Mock())
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        blade.get_directory_services_local_groups.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        blade.post_directory_services_local_groups.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_local_group.LooseVersion")
    @patch("plugins.modules.purefb_local_group.get_system")
    @patch("plugins.modules.purefb_local_group.AnsibleModule")
    @patch("plugins.modules.purefb_local_group.HAS_PYPURECLIENT", True)
    def test_main_create_fails_on_api_error(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test create surfaces API error via fail_json"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params()
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = _found_lds(Mock())
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        blade.get_directory_services_local_groups.return_value = get_response

        post_response = Mock()
        post_response.status_code = 400
        post_response.errors = []
        blade.post_directory_services_local_groups.return_value = post_response

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "Failed to create local group" in module.fail_json.call_args[1]["msg"]

    @patch("plugins.modules.purefb_local_group.LooseVersion")
    @patch("plugins.modules.purefb_local_group.LocalGroupPatch")
    @patch("plugins.modules.purefb_local_group.get_system")
    @patch("plugins.modules.purefb_local_group.AnsibleModule")
    @patch("plugins.modules.purefb_local_group.HAS_PYPURECLIENT", True)
    def test_main_updates_email_and_gid(
        self, mock_ansible_module, mock_get_system, mock_group_patch, mock_loose_version
    ):
        """Test updating an existing group's email and gid"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(gid=7001, email="new@example.com")
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = _found_lds(Mock())
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "developers"
        existing.built_in = False
        existing.gid = 6001
        existing.email = "old@example.com"

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_groups.return_value = get_response

        patch_response = Mock()
        patch_response.status_code = 200
        blade.patch_directory_services_local_groups.return_value = patch_response

        try:
            main()
        except SystemExit:
            pass

        blade.patch_directory_services_local_groups.assert_called_once()
        mock_group_patch.assert_called_once_with(email="new@example.com", gid=7001)
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_local_group.LooseVersion")
    @patch("plugins.modules.purefb_local_group.get_system")
    @patch("plugins.modules.purefb_local_group.AnsibleModule")
    @patch("plugins.modules.purefb_local_group.HAS_PYPURECLIENT", True)
    def test_main_update_idempotent_when_no_changes(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test update is a no-op when nothing changed"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(gid=6001, email="devs@example.com")
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = _found_lds(Mock())
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "developers"
        existing.built_in = False
        existing.gid = 6001
        existing.email = "devs@example.com"

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_groups.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        blade.patch_directory_services_local_groups.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_local_group.LooseVersion")
    @patch("plugins.modules.purefb_local_group.LocalGroupPatch")
    @patch("plugins.modules.purefb_local_group.get_system")
    @patch("plugins.modules.purefb_local_group.AnsibleModule")
    @patch("plugins.modules.purefb_local_group.HAS_PYPURECLIENT", True)
    def test_main_renames_group(
        self, mock_ansible_module, mock_get_system, mock_group_patch, mock_loose_version
    ):
        """Test renaming an existing group via new_name"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(new_name="devs")
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = _found_lds(Mock())
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "developers"
        existing.built_in = False
        existing.gid = 6001
        existing.email = None

        # First call is _get_group (existing found); second is the rename-clash lookup
        clash_response = Mock()
        clash_response.status_code = 200
        clash_response.items = []
        first_response = Mock()
        first_response.status_code = 200
        first_response.items = [existing]
        blade.get_directory_services_local_groups.side_effect = [
            first_response,
            clash_response,
        ]

        patch_response = Mock()
        patch_response.status_code = 200
        blade.patch_directory_services_local_groups.return_value = patch_response

        try:
            main()
        except SystemExit:
            pass

        mock_group_patch.assert_called_once_with(name="devs")
        blade.patch_directory_services_local_groups.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_local_group.LooseVersion")
    @patch("plugins.modules.purefb_local_group.get_system")
    @patch("plugins.modules.purefb_local_group.AnsibleModule")
    @patch("plugins.modules.purefb_local_group.HAS_PYPURECLIENT", True)
    def test_main_rename_fails_when_target_exists(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test rename fails cleanly when the target name already exists"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(new_name="devs")
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = _found_lds(Mock())
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "developers"
        existing.built_in = False
        existing.gid = 6001
        existing.email = None

        clash = Mock()
        clash.name = "devs"
        clash_response = Mock()
        clash_response.status_code = 200
        clash_response.items = [clash]
        first_response = Mock()
        first_response.status_code = 200
        first_response.items = [existing]
        blade.get_directory_services_local_groups.side_effect = [
            first_response,
            clash_response,
        ]

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "target name already exists" in msg
        blade.patch_directory_services_local_groups.assert_not_called()

    @patch("plugins.modules.purefb_local_group.LooseVersion")
    @patch("plugins.modules.purefb_local_group.get_system")
    @patch("plugins.modules.purefb_local_group.AnsibleModule")
    @patch("plugins.modules.purefb_local_group.HAS_PYPURECLIENT", True)
    def test_main_refuses_to_rename_builtin(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test rename is refused on built-in groups"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(name="Domain Users", new_name="dev-users")
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = _found_lds(Mock())
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "Domain Users"
        existing.built_in = True
        existing.gid = 100
        existing.email = None

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_groups.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "built-in" in module.fail_json.call_args[1]["msg"]
        blade.patch_directory_services_local_groups.assert_not_called()

    @patch("plugins.modules.purefb_local_group.LooseVersion")
    @patch("plugins.modules.purefb_local_group.get_system")
    @patch("plugins.modules.purefb_local_group.AnsibleModule")
    @patch("plugins.modules.purefb_local_group.HAS_PYPURECLIENT", True)
    def test_main_deletes_empty_group(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test deleting a group that has no members"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(state="absent")
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = _found_lds(Mock())
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "developers"
        existing.built_in = False

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_groups.return_value = get_response

        members_response = Mock()
        members_response.status_code = 200
        members_response.items = []
        blade.get_directory_services_local_groups_members.return_value = (
            members_response
        )

        delete_response = Mock()
        delete_response.status_code = 200
        blade.delete_directory_services_local_groups.return_value = delete_response

        try:
            main()
        except SystemExit:
            pass

        blade.delete_directory_services_local_groups.assert_called_once_with(
            names=["developers"],
            local_directory_service_names=["myserver_local"],
        )
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_local_group.LooseVersion")
    @patch("plugins.modules.purefb_local_group.get_system")
    @patch("plugins.modules.purefb_local_group.AnsibleModule")
    @patch("plugins.modules.purefb_local_group.HAS_PYPURECLIENT", True)
    def test_main_delete_refuses_when_members_and_no_force(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test delete refuses when the group has members and force=false"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(state="absent")
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = _found_lds(Mock())
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "developers"
        existing.built_in = False

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_groups.return_value = get_response

        edge = Mock()
        edge.member = Mock()
        edge.member.name = "alice"
        edge.member.resource_type = "local-users"
        members_response = Mock()
        members_response.status_code = 200
        members_response.items = [edge]
        blade.get_directory_services_local_groups_members.return_value = (
            members_response
        )

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "force: true" in module.fail_json.call_args[1]["msg"]
        blade.delete_directory_services_local_groups.assert_not_called()

    @patch("plugins.modules.purefb_local_group.LooseVersion")
    @patch("plugins.modules.purefb_local_group.get_system")
    @patch("plugins.modules.purefb_local_group.AnsibleModule")
    @patch("plugins.modules.purefb_local_group.HAS_PYPURECLIENT", True)
    def test_main_delete_force_clears_members_then_deletes(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test delete with force=true clears members first, then deletes the group"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(state="absent", force=True)
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = _found_lds(Mock())
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "developers"
        existing.built_in = False

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_groups.return_value = get_response

        edge = Mock()
        edge.member = Mock()
        edge.member.name = "alice"
        edge.member.resource_type = "local-users"
        members_response = Mock()
        members_response.status_code = 200
        members_response.items = [edge]
        blade.get_directory_services_local_groups_members.return_value = (
            members_response
        )

        ok = Mock()
        ok.status_code = 200
        blade.delete_directory_services_local_groups_members.return_value = ok
        blade.delete_directory_services_local_groups.return_value = ok

        try:
            main()
        except SystemExit:
            pass

        blade.delete_directory_services_local_groups_members.assert_called_once()
        blade.delete_directory_services_local_groups.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_local_group.LooseVersion")
    @patch("plugins.modules.purefb_local_group.get_system")
    @patch("plugins.modules.purefb_local_group.AnsibleModule")
    @patch("plugins.modules.purefb_local_group.HAS_PYPURECLIENT", True)
    def test_main_refuses_to_delete_builtin(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test delete is refused on built-in groups"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(state="absent", name="Domain Users")
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = _found_lds(Mock())
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "Domain Users"
        existing.built_in = True

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_groups.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "built-in" in module.fail_json.call_args[1]["msg"]
        blade.delete_directory_services_local_groups.assert_not_called()

    @patch("plugins.modules.purefb_local_group.LooseVersion")
    @patch("plugins.modules.purefb_local_group.get_system")
    @patch("plugins.modules.purefb_local_group.AnsibleModule")
    @patch("plugins.modules.purefb_local_group.HAS_PYPURECLIENT", True)
    def test_main_delete_nonexistent_is_noop(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test state=absent on a nonexistent group reports changed=False"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(state="absent", name="ghost")
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = _found_lds(Mock())
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        blade.get_directory_services_local_groups.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        blade.delete_directory_services_local_groups.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_local_group.LooseVersion")
    @patch("plugins.modules.purefb_local_group.LocalGroupPost")
    @patch("plugins.modules.purefb_local_group.get_system")
    @patch("plugins.modules.purefb_local_group.AnsibleModule")
    @patch("plugins.modules.purefb_local_group.HAS_PYPURECLIENT", True)
    def test_main_create_with_local_users_reconciles(
        self, mock_ansible_module, mock_get_system, mock_group_post, mock_loose_version
    ):
        """Test create-with-members POSTs the group then reconciles members"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(local_users=["alice", "bob"])
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = _found_lds(Mock())
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        blade.get_directory_services_local_groups.return_value = get_response

        created = Mock()
        created.name = "developers"
        created.gid = 6001
        created.sid = "S-1"
        created.built_in = False

        post_response = Mock()
        post_response.status_code = 200
        post_response.items = [created]
        blade.post_directory_services_local_groups.return_value = post_response

        members_current = Mock()
        members_current.status_code = 200
        members_current.items = []
        blade.get_directory_services_local_groups_members.return_value = members_current

        post_members = Mock()
        post_members.status_code = 200
        blade.post_directory_services_local_groups_members.return_value = post_members

        try:
            main()
        except SystemExit:
            pass

        blade.post_directory_services_local_groups.assert_called_once()
        blade.post_directory_services_local_groups_members.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_local_group.LooseVersion")
    @patch("plugins.modules.purefb_local_group.get_system")
    @patch("plugins.modules.purefb_local_group.AnsibleModule")
    @patch("plugins.modules.purefb_local_group.HAS_PYPURECLIENT", True)
    def test_main_fails_on_unsupported_api_version(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test failure when the array API version is older than MIN_REQUIRED_API_VERSION"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params()
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = _found_lds(Mock())
        blade.get_versions.return_value.items = ["2.17", "2.18", "2.19"]
        mock_get_system.return_value = blade

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "REST version not supported" in module.fail_json.call_args[1]["msg"]

    @patch("plugins.modules.purefb_local_group.LooseVersion")
    @patch("plugins.modules.purefb_local_group.get_system")
    @patch("plugins.modules.purefb_local_group.AnsibleModule")
    @patch("plugins.modules.purefb_local_group.HAS_PYPURECLIENT", False)
    def test_main_fails_without_sdk(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test failure when py-pure-client SDK is not installed"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params()
        module.check_mode = False
        mock_ansible_module.return_value = module

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "py-pure-client" in module.fail_json.call_args[1]["msg"]


# ---------------------------------------------------------------------------
# The LDS is read first, the group names carry no realm, and a rename that an
# earlier run applied is not applied again. The mocks answer as the array
# does: a local directory service that is not there (or that the caller may
# not manage) answers 400 "Local directory service does not exist.", a group
# that is not there 400 "Local group was not found.", names match without
# regard to case and come back in the stored spelling, and the group list
# also returns the groups of an LDS the caller cannot read.
# ---------------------------------------------------------------------------

MOD = "plugins.modules.purefb_local_group"
LDS_MISSING = "Local directory service does not exist."
GROUP_MISSING = "Local group was not found."
WRITES = (
    "post_directory_services_local_groups",
    "patch_directory_services_local_groups",
    "delete_directory_services_local_groups",
    "post_directory_services_local_groups_members",
    "delete_directory_services_local_groups_members",
)


def _version(value):
    return tuple(int(part) for part in str(value).split("."))


def _message(res):
    """Stand-in for get_error_message, which lives in the mocked module_utils."""
    return res.errors[0].message


def _response(items=None):
    res = Mock()
    res.status_code = 200
    res.items = items if items is not None else []
    res.errors = []
    return res


def _error(message, status_code=400):
    res = Mock()
    res.status_code = status_code
    error = Mock(spec=["message"])
    error.message = message
    res.errors = [error]
    return res


def _reference(name):
    ref = Mock(spec=["name"])
    ref.name = name
    return ref


def _lds(name):
    """A local directory service as the array returns it."""
    item = Mock(spec=["name", "domain", "realms", "server"])
    item.name = name
    item.domain = name.rpartition("::")[2]
    realm = name.rpartition("::")[0]
    item.realms = [_reference(realm)] if realm else []
    item.server = None
    return item


def _group(name, lds="myserver_local", gid=6001, email=None, built_in=False):
    """A local group as the array returns it: the name carries no realm."""
    item = Mock(
        spec=[
            "name",
            "gid",
            "email",
            "sid",
            "built_in",
            "local_directory_service",
            "realms",
        ]
    )
    item.name = name
    item.gid = gid
    item.email = email
    item.sid = "S-1-5-21-517968436-696578107-1734940895-{0}".format(gid)
    item.built_in = built_in
    item.local_directory_service = _reference(lds)
    realm = lds.rpartition("::")[0]
    item.realms = [_reference(realm)] if realm else []
    return item


def _member(name, group="developers"):
    """The membership of a local user as the array returns it."""
    edge = Mock(spec=["group", "member"])
    edge.group = _reference(group)
    edge.member = Mock(spec=["name", "resource_type"])
    edge.member.name = name
    edge.member.resource_type = "directory-services/local/users"
    return edge


def _array(
    lds="myserver_local", groups=(), lds_answer=None, group_answer=None, members=()
):
    """A client for an array with the LDS, or LDSes, and the groups given.

    ``lds=None`` is an LDS the array does not show to the caller; its groups
    are listed all the same. The array reads a comma in ``names`` as the
    separator of a list: it returns every LDS named when each of them exists,
    and every group of the LDS in the filter that matches one of the names.
    ``members`` are the user members the array reports for a group.
    """
    blade = Mock()
    blade.get_fleets.return_value = _response([])
    known = [lds] if isinstance(lds, str) else list(lds or [])

    def read_lds(names, **kwargs):
        if lds_answer is not None:
            return lds_answer
        wanted = ",".join(names).lower().split(",")
        found = [name for name in known if name.lower() in wanted]
        if found and len(found) == len(wanted):
            return _response([_lds(name) for name in found])
        return _error(LDS_MISSING)

    def read_groups(names, **kwargs):
        if group_answer is not None:
            return group_answer
        wanted = ",".join(names).lower().split(",")
        owner = kwargs.get("filter", "").partition("='")[2].rstrip("'").lower()
        found = [
            group
            for group in groups
            if group.name.lower() in wanted
            and (not owner or group.local_directory_service.name.lower() == owner)
        ]
        return _response(found) if found else _error(GROUP_MISSING)

    blade.get_directory_services_local_directory_services.side_effect = read_lds
    blade.get_directory_services_local_groups.side_effect = read_groups
    blade.get_directory_services_local_groups_members.return_value = _response(
        [_member(name) for name in members]
    )
    for method in WRITES:
        getattr(blade, method).return_value = _response()
    return blade


def _run(blade, check_mode=False, **overrides):
    """Run main() against the client and return the module mock."""
    module = Mock()
    module.params = _base_params(**overrides)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    with patch(MOD + ".AnsibleModule", return_value=module), patch(
        MOD + ".get_system", return_value=blade
    ), patch(MOD + ".get_rest_api_version", return_value="2.30"), patch(
        MOD + ".LooseVersion", side_effect=_version
    ), patch(
        MOD + ".get_error_message", side_effect=_message
    ), patch(
        MOD + ".LocalGroupPost", side_effect=lambda **kwargs: kwargs
    ), patch(
        MOD + ".LocalGroupPatch", side_effect=lambda **kwargs: kwargs
    ), patch(
        MOD + ".HAS_PYPURECLIENT", True
    ):
        try:
            main()
        except SystemExit:
            pass
    return module


def _failed(module):
    """Return the failure message of a run that has to fail."""
    assert module.fail_json.called, "no failure, exit_json{0}".format(
        module.exit_json.call_args
    )
    module.exit_json.assert_not_called()
    return module.fail_json.call_args[1]["msg"]


def _changed(module):
    """Return the changed value of a run that has to succeed."""
    assert not module.fail_json.called, "failed: {0}".format(module.fail_json.call_args)
    return module.exit_json.call_args[1]["changed"]


def _no_write(blade):
    for method in WRITES:
        getattr(blade, method).assert_not_called()


class TestLocalDirectoryServiceLookup:
    """The LDS is read before any group is looked up in it"""

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_create_in_missing_lds_fails_in_both_modes(self, check_mode):
        blade = _array(lds=None)
        module = _run(
            blade,
            check_mode=check_mode,
            local_directory_service="realm1::nolds",
        )
        msg = _failed(module)
        assert "Local directory service realm1::nolds does not exist" in msg
        assert "realm::name" in msg
        _no_write(blade)
        blade.get_directory_services_local_groups.assert_not_called()

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_update_of_a_listed_group_of_an_unmanageable_lds_fails(self, check_mode):
        """The array lists the group although it hides the LDS from the caller"""
        blade = _array(lds=None, groups=[_group("developers", lds="tenant_local")])
        module = _run(
            blade,
            check_mode=check_mode,
            local_directory_service="tenant_local",
            gid=7999,
        )
        assert "Local directory service tenant_local does not exist" in _failed(module)
        _no_write(blade)

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_absent_in_an_unmanageable_lds_reports_no_change(self, check_mode):
        blade = _array(lds=None, groups=[_group("developers", lds="realm2::lds")])
        module = _run(
            blade,
            check_mode=check_mode,
            local_directory_service="realm2::lds",
            state="absent",
            force=True,
        )
        assert _changed(module) is False
        msg = module.exit_json.call_args[1]["msg"]
        assert "Local directory service realm2::lds does not exist" in msg
        assert "realm::name" in msg
        _no_write(blade)
        blade.get_directory_services_local_groups_members.assert_not_called()

    def test_empty_lds_list_reads_as_missing(self):
        blade = _array(lds_answer=_response([]))
        module = _run(blade, check_mode=True)
        assert "Local directory service myserver_local does not exist" in _failed(
            module
        )
        _no_write(blade)

    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_refused_lds_read_is_reported_with_the_array_message(self, state):
        refusal = (
            "Operation not permitted. Authorization for 'read' on "
            "'directory-services' is required."
        )
        blade = _array(lds_answer=_error(refusal, 403))
        module = _run(blade, check_mode=True, state=state)
        msg = _failed(module)
        assert msg.startswith("Failed to read local directory service myserver_local.")
        assert refusal in msg
        _no_write(blade)
        blade.get_directory_services_local_groups.assert_not_called()

    def test_group_of_a_realm_lds_is_created_under_its_bare_name(self):
        blade = _array(lds="realm1::tenant_local")
        module = _run(
            blade,
            local_directory_service="realm1::tenant_local",
            gid=6001,
        )
        assert _changed(module) is True
        blade.get_directory_services_local_directory_services.assert_called_once_with(
            names=["realm1::tenant_local"]
        )
        blade.get_directory_services_local_groups.assert_called_once_with(
            names=["developers"],
            filter="local_directory_service.name='realm1::tenant_local'",
        )
        blade.post_directory_services_local_groups.assert_called_once_with(
            names=["developers"],
            local_directory_service_names=["realm1::tenant_local"],
            local_group={"gid": 6001},
        )

    def test_group_of_a_realm_lds_is_idempotent_beside_a_namesake(self):
        """Only the group of the named LDS counts, whatever else has the name"""
        blade = _array(
            lds="realm1::tenant_local",
            groups=[_group("developers", lds="realm1::tenant_local", gid=6001)],
        )
        module = _run(
            blade,
            local_directory_service="realm1::tenant_local",
            gid=6001,
        )
        assert _changed(module) is False
        _no_write(blade)

    def test_lds_read_carries_the_fleet_context(self):
        blade = _array()
        blade.get_fleets.return_value = _response([_reference("fleet1")])
        blade.get_arrays.return_value = _response([_reference("array1")])
        module = _run(blade, check_mode=True)
        assert _changed(module) is True
        blade.get_directory_services_local_directory_services.assert_called_once_with(
            names=["myserver_local"], context_names=["array1"]
        )

    def test_array_level_lds_keeps_working(self):
        blade = _array(groups=[_group("developers", gid=6001)])
        module = _run(blade, gid=7001, email="devs@example.com")
        assert _changed(module) is True
        blade.patch_directory_services_local_groups.assert_called_once_with(
            names=["developers"],
            local_directory_service_names=["myserver_local"],
            local_group={"email": "devs@example.com", "gid": 7001},
        )


class TestGroupRead:
    """A group read that fails is not taken for a group that is absent"""

    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_refused_group_read_is_reported_with_the_array_message(self, state):
        blade = _array(group_answer=_error("Operation not permitted.", 403))
        module = _run(blade, check_mode=True, state=state)
        msg = _failed(module)
        assert msg.startswith(
            "Failed to read local group developers of local directory service "
            "myserver_local."
        )
        assert "Operation not permitted." in msg
        _no_write(blade)

    def test_group_not_found_reads_as_absent(self):
        blade = _array()
        assert _changed(_run(blade, state="absent")) is False
        assert _changed(_run(blade)) is True
        blade.post_directory_services_local_groups.assert_called_once()

    def test_get_group_reads_the_name_it_is_given(self):
        module = Mock()
        module.params = {"name": "developers", "context": ""}
        blade = _array(groups=[_group("devs")])
        with patch(MOD + ".get_error_message", side_effect=_message):
            assert _get_group(module, blade, "myserver_local", "devs").name == "devs"
            assert _get_group(module, blade, "myserver_local") is None
        assert blade.get_directory_services_local_groups.call_args_list[0][1] == {
            "names": ["devs"],
            "filter": "local_directory_service.name='myserver_local'",
        }

    def test_missing_matches_the_two_answers_of_the_array_only(self):
        with patch(MOD + ".get_error_message", side_effect=_message):
            assert _missing(_error(LDS_MISSING)) is True
            assert _missing(_error(GROUP_MISSING)) is True
            assert _missing(_error("Operation not permitted.")) is False
            assert _missing(_error("Unexpected error.", 500)) is False


class TestGroupNames:
    """A group name takes no realm prefix"""

    @pytest.mark.parametrize("check_mode", [True, False])
    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_realm_prefix_in_name_is_refused(self, state, check_mode):
        blade = _array(lds="realm1::tenant_local")
        module = _run(
            blade,
            check_mode=check_mode,
            state=state,
            name="realm1::developers",
            local_directory_service="realm1::tenant_local",
        )
        msg = _failed(module)
        assert "name realm1::developers is not valid" in msg
        assert "realm::name in local_directory_service" in msg
        _no_write(blade)
        blade.get_directory_services_local_directory_services.assert_not_called()
        blade.get_directory_services_local_groups.assert_not_called()

    def test_realm_prefix_in_new_name_is_refused(self):
        blade = _array(
            lds="realm1::tenant_local",
            groups=[_group("developers", lds="realm1::tenant_local")],
        )
        module = _run(
            blade,
            check_mode=True,
            new_name="realm1::devs",
            local_directory_service="realm1::tenant_local",
        )
        assert "new_name realm1::devs is not valid" in _failed(module)
        _no_write(blade)

    def test_new_name_is_not_looked_at_for_absent(self):
        blade = _array(groups=[_group("developers")])
        module = _run(blade, state="absent", new_name="realm1::devs")
        assert _changed(module) is True
        blade.delete_directory_services_local_groups.assert_called_once_with(
            names=["developers"], local_directory_service_names=["myserver_local"]
        )


class TestRenameIdempotency:
    """The rename task run again carries on with the renamed group"""

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_second_run_of_a_rename_changes_nothing(self, check_mode):
        blade = _array(groups=[_group("devs")])
        module = _run(blade, check_mode=check_mode, new_name="devs")
        assert _changed(module) is False
        _no_write(blade)
        assert [
            call[1]["names"]
            for call in blade.get_directory_services_local_groups.call_args_list
        ] == [["developers"], ["devs"]]

    def test_second_run_in_a_realm_lds_changes_nothing(self):
        blade = _array(
            lds="realm1::tenant_local",
            groups=[_group("devs", lds="realm1::tenant_local")],
        )
        module = _run(
            blade,
            new_name="devs",
            local_directory_service="realm1::tenant_local",
        )
        assert _changed(module) is False
        _no_write(blade)

    def test_second_run_applies_the_other_options_to_the_renamed_group(self):
        blade = _array(groups=[_group("Devs", gid=6001)])
        module = _run(blade, new_name="devs", gid=7001)
        assert _changed(module) is True
        blade.post_directory_services_local_groups.assert_not_called()
        blade.patch_directory_services_local_groups.assert_called_once_with(
            names=["Devs"],
            local_directory_service_names=["myserver_local"],
            local_group={"gid": 7001},
        )

    def test_second_run_reconciles_the_members_of_the_renamed_group(self):
        blade = _array(groups=[_group("devs")])
        module = _run(blade, new_name="devs", local_users=["alice"])
        assert _changed(module) is True
        blade.post_directory_services_local_groups.assert_not_called()
        blade.patch_directory_services_local_groups.assert_not_called()
        blade.get_directory_services_local_groups_members.assert_called_once_with(
            group_names=["devs"],
            filter="local_directory_service.name='myserver_local'",
            member_types=["User"],
        )
        members = blade.post_directory_services_local_groups_members.call_args[1]
        assert members["group_names"] == ["devs"]
        assert members["local_directory_service_names"] == ["myserver_local"]

    def test_first_run_renames(self):
        blade = _array(groups=[_group("developers")])
        module = _run(blade, new_name="devs")
        assert _changed(module) is True
        blade.patch_directory_services_local_groups.assert_called_once_with(
            names=["developers"],
            local_directory_service_names=["myserver_local"],
            local_group={"name": "devs"},
        )

    def test_first_run_in_check_mode_sends_nothing(self):
        blade = _array(groups=[_group("developers")])
        module = _run(blade, check_mode=True, new_name="devs")
        assert _changed(module) is True
        _no_write(blade)

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_two_different_groups_are_refused(self, check_mode):
        blade = _array(
            groups=[_group("developers", gid=6001), _group("devs", gid=6002)]
        )
        module = _run(blade, check_mode=check_mode, new_name="devs", gid=7001)
        assert "target name already exists" in _failed(module)
        _no_write(blade)

    def test_a_built_in_group_is_not_taken_for_the_renamed_group(self):
        blade = _array(groups=[_group("Guests", gid=546, built_in=True)])
        module = _run(blade, new_name="Guests", local_users=["alice"])
        msg = _failed(module)
        assert "developers does not exist" in msg
        assert "Guests is a built-in group" in msg
        _no_write(blade)

    def test_group_that_does_not_exist_yet_is_created_as_name(self):
        blade = _array()
        module = _run(blade, new_name="devs", gid=6001)
        assert _changed(module) is True
        blade.post_directory_services_local_groups.assert_called_once_with(
            names=["developers"],
            local_directory_service_names=["myserver_local"],
            local_group={"gid": 6001},
        )
        blade.patch_directory_services_local_groups.assert_not_called()

    def test_absent_does_not_follow_the_new_name(self):
        """state=absent acts on name alone and leaves the renamed group"""
        blade = _array(groups=[_group("devs")])
        module = _run(blade, state="absent", new_name="devs", force=True)
        assert _changed(module) is False
        _no_write(blade)
        blade.get_directory_services_local_groups.assert_called_once_with(
            names=["developers"],
            filter="local_directory_service.name='myserver_local'",
        )

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_new_name_in_another_case_is_refused(self, check_mode):
        """The array answers "Local group with specified name already exists." """
        blade = _array(groups=[_group("developers")])
        module = _run(blade, check_mode=check_mode, new_name="Developers", gid=7001)
        msg = _failed(module)
        assert "differs from the name of the group only in case" in msg
        _no_write(blade)

    def test_group_that_carries_the_new_name_already_is_left_alone(self):
        """Both names are the one group, stored in the spelling of new_name"""
        blade = _array(groups=[_group("Devs")])
        module = _run(blade, name="devs", new_name="Devs")
        assert _changed(module) is False
        _no_write(blade)

    def test_same_group_by_sid_then_by_name(self):
        first = _group("devs", gid=6001)
        second = _group("DEVS", gid=6001)
        other = _group("devs", gid=6002)
        assert _same_group(first, second) is True
        assert _same_group(first, other) is False
        first.sid = None
        assert _same_group(first, second) is True
        assert _same_group(first, _group("developers")) is False


class TestNamesWithAComma:
    """The array reads a comma as the separator of a list of names"""

    @pytest.mark.parametrize("check_mode", [True, False])
    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_two_group_names_in_one_are_refused(self, state, check_mode):
        """The array returns both groups for the one name"""
        blade = _array(
            groups=[_group("developers", gid=6001), _group("devs", gid=6002)]
        )
        module = _run(
            blade,
            check_mode=check_mode,
            state=state,
            name="developers,devs",
            gid=7001,
            force=True,
        )
        msg = _failed(module)
        assert "name developers,devs is not valid" in msg
        assert "comma" in msg
        _no_write(blade)
        blade.get_directory_services_local_directory_services.assert_not_called()
        blade.get_directory_services_local_groups.assert_not_called()

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_a_group_name_and_a_name_that_is_not_there_are_refused(self, check_mode):
        """The array returns the one group it finds for the two names"""
        blade = _array(groups=[_group("developers", gid=6001)])
        module = _run(blade, check_mode=check_mode, name="developers,nogroup", gid=7001)
        assert "name developers,nogroup is not valid" in _failed(module)
        _no_write(blade)

    @pytest.mark.parametrize("check_mode", [True, False])
    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_two_lds_names_in_one_are_refused(self, state, check_mode):
        """The array returns both LDSes for the one name"""
        blade = _array(lds=["tenant_local", "realm1::tenant_local"])
        module = _run(
            blade,
            check_mode=check_mode,
            state=state,
            local_directory_service="tenant_local,realm1::tenant_local",
        )
        msg = _failed(module)
        assert (
            "local_directory_service tenant_local,realm1::tenant_local is not valid"
            in msg
        )
        assert "comma" in msg
        _no_write(blade)
        blade.get_directory_services_local_directory_services.assert_not_called()
        blade.get_directory_services_local_groups.assert_not_called()

    def test_comma_in_new_name_is_refused(self):
        blade = _array(groups=[_group("developers")])
        module = _run(blade, check_mode=True, new_name="devs,ops")
        assert "new_name devs,ops is not valid" in _failed(module)
        _no_write(blade)
        blade.get_directory_services_local_groups.assert_not_called()

    def test_new_name_is_not_looked_at_for_absent(self):
        blade = _array(groups=[_group("developers")])
        module = _run(blade, state="absent", new_name="devs,ops")
        assert _changed(module) is True
        blade.delete_directory_services_local_groups.assert_called_once_with(
            names=["developers"], local_directory_service_names=["myserver_local"]
        )

    def test_group_of_the_same_name_in_another_lds_is_not_the_group(self):
        """The group read is scoped to the LDS the task names"""
        blade = _array(
            lds=["tenant_local", "realm1::tenant_local"],
            groups=[_group("developers", lds="tenant_local", gid=6002)],
        )
        module = _run(
            blade,
            local_directory_service="realm1::tenant_local",
            gid=6001,
        )
        assert _changed(module) is True
        blade.patch_directory_services_local_groups.assert_not_called()
        blade.post_directory_services_local_groups.assert_called_once_with(
            names=["developers"],
            local_directory_service_names=["realm1::tenant_local"],
            local_group={"gid": 6001},
        )


class TestMemberNames:
    """Member names are compared as the array matches them: without regard to case"""

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_member_named_in_another_case_is_not_a_change(self, check_mode):
        blade = _array(groups=[_group("developers")], members=["alice"])
        module = _run(blade, check_mode=check_mode, local_users=["ALICE"])
        assert _changed(module) is False
        _no_write(blade)

    def test_member_named_twice_counts_once(self):
        blade = _array(groups=[_group("developers")], members=["alice"])
        module = _run(blade, local_users=["alice", "Alice"])
        assert _changed(module) is False
        _no_write(blade)

    def test_members_that_differ_are_added_and_removed(self):
        blade = _array(groups=[_group("developers")], members=["Alice", "bob"])
        with patch(
            MOD + ".ReferenceWritable", side_effect=lambda **kwargs: kwargs
        ), patch(
            MOD + ".LocalGroupMembershipPostMembers",
            side_effect=lambda **kwargs: kwargs,
        ), patch(
            MOD + ".LocalGroupMembershipPost", side_effect=lambda **kwargs: kwargs
        ):
            module = _run(blade, local_users=["alice", "Carol"])
        assert _changed(module) is True
        blade.post_directory_services_local_groups_members.assert_called_once_with(
            local_membership={"members": [{"member": {"name": "Carol"}}]},
            group_names=["developers"],
            local_directory_service_names=["myserver_local"],
        )
        blade.delete_directory_services_local_groups_members.assert_called_once_with(
            group_names=["developers"],
            member_names=["bob"],
            member_types=["User"],
            local_directory_service_names=["myserver_local"],
        )

    def test_check_mode_reports_the_members_that_differ(self):
        blade = _array(groups=[_group("developers")], members=["Alice", "bob"])
        module = _run(blade, check_mode=True, local_users=["alice"])
        assert _changed(module) is True
        _no_write(blade)
