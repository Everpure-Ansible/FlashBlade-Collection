# Copyright: (c) 2026, Pure Storage Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_realm module."""

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

from plugins.modules.purefb_realm import (
    main,
    get_realm,
    get_pending_realm,
    get_policy,
    make_realm,
    update_realm,
)


class TestPurefbRealm:
    """Test cases for purefb_realm module"""

    @patch("plugins.modules.purefb_realm.get_pending_realm")
    @patch("plugins.modules.purefb_realm.get_realm")
    @patch("plugins.modules.purefb_realm.LooseVersion")
    @patch("plugins.modules.purefb_realm.get_system")
    @patch("plugins.modules.purefb_realm.AnsibleModule")
    @patch("plugins.modules.purefb_realm.HAS_PURESTORAGE", True)
    def test_main_create_realm(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
    ):
        """Test creating a new realm"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-realm",
            "without_default_access_list": True,
            "state": "present",
            "qos_policy": None,
            "eradicate": False,
            "rename": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.19"]
        mock_get_system.return_value = mock_blade

        # Mock API version check
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        # Realm doesn't exist
        mock_get_realm.return_value = None
        mock_get_pending_realm.return_value = None

        # Mock successful realm creation
        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_blade.post_realms.return_value = mock_post_response

        # Call main
        try:
            main()
        except SystemExit:
            pass

        # Verify post_realms was called
        mock_blade.post_realms.assert_called_once_with(
            names=["test-realm"], without_default_access_list=True
        )

        # Verify exit_json was called with changed=True
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is True

    @patch("plugins.modules.purefb_realm.get_policy")
    @patch("plugins.modules.purefb_realm.get_pending_realm")
    @patch("plugins.modules.purefb_realm.get_realm")
    @patch("plugins.modules.purefb_realm.LooseVersion")
    @patch("plugins.modules.purefb_realm.get_system")
    @patch("plugins.modules.purefb_realm.AnsibleModule")
    @patch("plugins.modules.purefb_realm.HAS_PURESTORAGE", True)
    def test_main_create_realm_with_qos_policy(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_get_policy,
    ):
        """Test creating a new realm with QoS policy"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-realm",
            "without_default_access_list": True,
            "state": "present",
            "qos_policy": "test-qos-policy",
            "eradicate": False,
            "rename": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.19"]
        mock_get_system.return_value = mock_blade

        # Mock API version check
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        # Realm doesn't exist
        mock_get_realm.return_value = None
        mock_get_pending_realm.return_value = None

        # QoS policy exists
        mock_get_policy.return_value = True

        # Mock successful realm creation
        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_blade.post_realms.return_value = mock_post_response
        mock_blade.post_qos_policies_members.return_value = mock_post_response

        # Call main
        try:
            main()
        except SystemExit:
            pass

        # Verify post_realms was called
        mock_blade.post_realms.assert_called_once_with(
            names=["test-realm"], without_default_access_list=True
        )

        # Verify QoS policy was assigned to the realm member type
        mock_blade.post_qos_policies_members.assert_called_once_with(
            policy_names=["test-qos-policy"],
            member_names=["test-realm"],
            member_types=["realms"],
        )

        # Verify exit_json was called with changed=True
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is True

    @patch("plugins.modules.purefb_realm.get_pending_realm")
    @patch("plugins.modules.purefb_realm.get_realm")
    @patch("plugins.modules.purefb_realm.LooseVersion")
    @patch("plugins.modules.purefb_realm.get_system")
    @patch("plugins.modules.purefb_realm.AnsibleModule")
    @patch("plugins.modules.purefb_realm.HAS_PURESTORAGE", True)
    def test_main_delete_realm(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
    ):
        """Test deleting an existing realm"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-realm",
            "state": "absent",
            "qos_policy": None,
            "eradicate": False,
            "rename": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.19"]
        mock_get_system.return_value = mock_blade

        # Mock API version check
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        # Realm exists
        mock_get_realm.return_value = True
        mock_get_pending_realm.return_value = None

        # Mock successful realm deletion
        mock_patch_response = Mock()
        mock_patch_response.status_code = 200
        mock_blade.patch_realms.return_value = mock_patch_response

        # Call main
        try:
            main()
        except SystemExit:
            pass

        # Verify patch_realms was called
        mock_blade.patch_realms.assert_called_once()

        # Verify exit_json was called with changed=True
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is True

    @patch("plugins.modules.purefb_realm.get_pending_realm")
    @patch("plugins.modules.purefb_realm.get_realm")
    @patch("plugins.modules.purefb_realm.LooseVersion")
    @patch("plugins.modules.purefb_realm.get_system")
    @patch("plugins.modules.purefb_realm.AnsibleModule")
    @patch("plugins.modules.purefb_realm.HAS_PURESTORAGE", True)
    def test_main_eradicate_realm(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
    ):
        """Test deleting and eradicating a realm"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-realm",
            "state": "absent",
            "qos_policy": None,
            "eradicate": True,
            "rename": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.19"]
        mock_get_system.return_value = mock_blade

        # Mock API version check
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        # Realm exists
        mock_get_realm.return_value = True
        mock_get_pending_realm.return_value = None

        # Mock successful operations
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_realms.return_value = mock_response
        mock_blade.delete_realms.return_value = mock_response

        # Call main
        try:
            main()
        except SystemExit:
            pass

        # Verify patch_realms was called (delete)
        mock_blade.patch_realms.assert_called_once()

        # Verify delete_realms was called (eradicate)
        mock_blade.delete_realms.assert_called_once_with(names=["test-realm"])

        # Verify exit_json was called with changed=True
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is True

    @patch("plugins.modules.purefb_realm.get_pending_realm")
    @patch("plugins.modules.purefb_realm.get_realm")
    @patch("plugins.modules.purefb_realm.LooseVersion")
    @patch("plugins.modules.purefb_realm.get_system")
    @patch("plugins.modules.purefb_realm.AnsibleModule")
    @patch("plugins.modules.purefb_realm.HAS_PURESTORAGE", True)
    def test_main_recover_realm(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
    ):
        """Test recovering a deleted realm"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-realm",
            "state": "present",
            "qos_policy": None,
            "eradicate": False,
            "rename": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.19"]
        mock_get_system.return_value = mock_blade

        # Mock API version check
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        # Realm is in pending deletion
        mock_get_realm.return_value = None
        mock_get_pending_realm.return_value = True

        # Mock successful realm recovery
        mock_patch_response = Mock()
        mock_patch_response.status_code = 200
        mock_blade.patch_realms.return_value = mock_patch_response

        # Call main
        try:
            main()
        except SystemExit:
            pass

        # Verify patch_realms was called
        mock_blade.patch_realms.assert_called_once()

        # Verify exit_json was called with changed=True
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is True

    @patch("plugins.modules.purefb_realm.RealmPatch")
    @patch("plugins.modules.purefb_realm.get_pending_realm")
    @patch("plugins.modules.purefb_realm.get_realm")
    @patch("plugins.modules.purefb_realm.LooseVersion")
    @patch("plugins.modules.purefb_realm.get_system")
    @patch("plugins.modules.purefb_realm.AnsibleModule")
    @patch("plugins.modules.purefb_realm.HAS_PURESTORAGE", True)
    def test_main_rename_realm(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_patch,
    ):
        """Test renaming an existing realm"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-realm",
            "state": "present",
            "qos_policy": None,
            "eradicate": False,
            "rename": "new-realm-name",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.19"]
        mock_get_system.return_value = mock_blade

        # Mock API version check
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        # Realm exists
        mock_get_realm.return_value = True
        mock_get_pending_realm.return_value = None

        # Mock successful rename (the SDK method is patch_realms, plural)
        mock_patch_response = Mock()
        mock_patch_response.status_code = 200
        mock_blade.patch_realms.return_value = mock_patch_response

        # Call main
        try:
            main()
        except SystemExit:
            pass

        # Verify patch_realms was called for the rename
        mock_blade.patch_realms.assert_called_once()
        assert mock_blade.patch_realms.call_args[1]["names"] == ["test-realm"]

        # Verify exit_json was called with changed=True
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is True

    @patch("plugins.modules.purefb_realm.get_pending_realm")
    @patch("plugins.modules.purefb_realm.get_realm")
    @patch("plugins.modules.purefb_realm.LooseVersion")
    @patch("plugins.modules.purefb_realm.get_system")
    @patch("plugins.modules.purefb_realm.AnsibleModule")
    @patch("plugins.modules.purefb_realm.HAS_PURESTORAGE", True)
    def test_main_update_qos_policy(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
    ):
        """Test updating QoS policy for an existing realm"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-realm",
            "state": "present",
            "qos_policy": "new-qos-policy",
            "eradicate": False,
            "rename": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.19"]
        mock_get_system.return_value = mock_blade

        # Mock API version check
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        # Realm exists
        mock_get_realm.return_value = True
        mock_get_pending_realm.return_value = None

        # Mock current QoS policy
        mock_policy_member = Mock()
        mock_policy_member.policy = Mock()
        mock_policy_member.policy.name = "old-qos-policy"
        mock_blade.get_qos_policies_members.return_value.status_code = 200
        mock_blade.get_qos_policies_members.return_value.items = [mock_policy_member]

        # Mock successful QoS policy update (new policy exists)
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.get_qos_policies.return_value = mock_response
        mock_blade.delete_qos_policies_members.return_value = mock_response
        mock_blade.post_qos_policies_members.return_value = mock_response

        # Call main
        try:
            main()
        except SystemExit:
            pass

        # Verify old policy was removed
        mock_blade.delete_qos_policies_members.assert_called_once()

        # Verify new policy was added
        mock_blade.post_qos_policies_members.assert_called_once()

        # Verify exit_json was called with changed=True
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is True

    @patch("plugins.modules.purefb_realm.get_pending_realm")
    @patch("plugins.modules.purefb_realm.get_realm")
    @patch("plugins.modules.purefb_realm.LooseVersion")
    @patch("plugins.modules.purefb_realm.get_system")
    @patch("plugins.modules.purefb_realm.AnsibleModule")
    @patch("plugins.modules.purefb_realm.HAS_PURESTORAGE", True)
    def test_main_create_realm_check_mode(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
    ):
        """Test creating a realm in check mode"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-realm",
            "without_default_access_list": True,
            "state": "present",
            "qos_policy": None,
            "eradicate": False,
            "rename": None,
        }
        mock_module.check_mode = True
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.19"]
        mock_get_system.return_value = mock_blade

        # Mock API version check
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        # Realm doesn't exist
        mock_get_realm.return_value = None
        mock_get_pending_realm.return_value = None

        # Call main
        try:
            main()
        except SystemExit:
            pass

        # Verify post_realms was NOT called (check mode)
        mock_blade.post_realms.assert_not_called()

        # Verify exit_json was called with changed=True
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is True

    @patch("plugins.modules.purefb_realm.get_pending_realm")
    @patch("plugins.modules.purefb_realm.get_realm")
    @patch("plugins.modules.purefb_realm.LooseVersion")
    @patch("plugins.modules.purefb_realm.get_system")
    @patch("plugins.modules.purefb_realm.AnsibleModule")
    @patch("plugins.modules.purefb_realm.HAS_PURESTORAGE", True)
    def test_main_create_realm_fails(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
    ):
        """Test error handling when realm creation fails"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-realm",
            "without_default_access_list": True,
            "state": "present",
            "qos_policy": None,
            "eradicate": False,
            "rename": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.19"]
        mock_get_system.return_value = mock_blade

        # Mock API version check
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        # Realm doesn't exist
        mock_get_realm.return_value = None
        mock_get_pending_realm.return_value = None

        # Mock failed realm creation
        mock_post_response = Mock()
        mock_post_response.status_code = 400
        mock_error = Mock()
        mock_error.message = "Realm creation failed"
        mock_post_response.errors = [mock_error]
        mock_blade.post_realms.return_value = mock_post_response

        # Call main - expect failure
        try:
            main()
        except SystemExit:
            pass

        # Verify fail_json was called
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "Creation of realm" in call_args["msg"]

    @patch("plugins.modules.purefb_realm.get_policy")
    @patch("plugins.modules.purefb_realm.get_pending_realm")
    @patch("plugins.modules.purefb_realm.get_realm")
    @patch("plugins.modules.purefb_realm.LooseVersion")
    @patch("plugins.modules.purefb_realm.get_system")
    @patch("plugins.modules.purefb_realm.AnsibleModule")
    @patch("plugins.modules.purefb_realm.HAS_PURESTORAGE", True)
    def test_main_qos_policy_assignment_fails(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_get_policy,
    ):
        """Test error handling when QoS policy assignment fails"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-realm",
            "without_default_access_list": True,
            "state": "present",
            "qos_policy": "test-qos-policy",
            "eradicate": False,
            "rename": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.19"]
        mock_get_system.return_value = mock_blade

        # Mock API version check
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        # Realm doesn't exist
        mock_get_realm.return_value = None
        mock_get_pending_realm.return_value = None

        # QoS policy exists
        mock_get_policy.return_value = True

        # Mock successful realm creation but failed QoS assignment
        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_blade.post_realms.return_value = mock_post_response

        mock_qos_response = Mock()
        mock_qos_response.status_code = 400
        mock_error = Mock()
        mock_error.message = "QoS policy assignment failed"
        mock_qos_response.errors = [mock_error]
        mock_blade.post_qos_policies_members.return_value = mock_qos_response

        # Call main - expect failure
        try:
            main()
        except SystemExit:
            pass

        # Verify fail_json was called
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "QoS policy assignment failed" in call_args["msg"]

    @patch("plugins.modules.purefb_realm.LooseVersion")
    @patch("plugins.modules.purefb_realm.get_system")
    @patch("plugins.modules.purefb_realm.AnsibleModule")
    @patch("plugins.modules.purefb_realm.HAS_PURESTORAGE", True)
    def test_main_api_version_too_old(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test failure when API version is too old"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-realm",
            "state": "present",
            "qos_policy": None,
            "eradicate": False,
            "rename": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade with old API version
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.10"]
        mock_get_system.return_value = mock_blade

        # Mock API version check to fail
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)

        # Call main - expect failure
        try:
            main()
        except SystemExit:
            pass

        # Verify fail_json was called
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "Purity//FB 4.6.1, or higher, is required" in call_args["msg"]

    @patch("plugins.modules.purefb_realm.get_pending_realm")
    @patch("plugins.modules.purefb_realm.get_realm")
    @patch("plugins.modules.purefb_realm.LooseVersion")
    @patch("plugins.modules.purefb_realm.get_system")
    @patch("plugins.modules.purefb_realm.AnsibleModule")
    @patch("plugins.modules.purefb_realm.HAS_PURESTORAGE", True)
    def test_main_delete_nonexistent_realm(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
    ):
        """Test deleting a nonexistent realm (no-op)"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "nonexistent-realm",
            "state": "absent",
            "qos_policy": None,
            "eradicate": False,
            "rename": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.19"]
        mock_get_system.return_value = mock_blade

        # Mock API version check
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        # Realm doesn't exist
        mock_get_realm.return_value = None
        mock_get_pending_realm.return_value = None

        # Call main
        try:
            main()
        except SystemExit:
            pass

        # Verify no API calls were made
        mock_blade.patch_realms.assert_not_called()
        mock_blade.delete_realms.assert_not_called()

        # Verify exit_json was called with changed=False
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is False

    def test_get_realm(self):
        """Test get_realm function"""
        # Setup mock module
        mock_module = Mock()
        mock_module.params = {"name": "test-realm"}

        # Setup mock blade
        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.get_realms.return_value = mock_response

        # Call function
        result = get_realm(mock_module, mock_blade)

        # Verify result
        assert result is True
        mock_blade.get_realms.assert_called_once_with(
            destroyed=False, names=["test-realm"]
        )

    def test_get_realm_not_found(self):
        """Test get_realm when realm doesn't exist"""
        # Setup mock module
        mock_module = Mock()
        mock_module.params = {"name": "nonexistent-realm"}

        # Setup mock blade
        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 400
        mock_blade.get_realms.return_value = mock_response

        # Call function
        result = get_realm(mock_module, mock_blade)

        # Verify result
        assert result is None

    def test_get_pending_realm(self):
        """Test get_pending_realm function"""
        # Setup mock module
        mock_module = Mock()
        mock_module.params = {"name": "test-realm"}

        # Setup mock blade
        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.get_realms.return_value = mock_response

        # Call function
        result = get_pending_realm(mock_module, mock_blade)

        # Verify result
        assert result is True
        mock_blade.get_realms.assert_called_once_with(
            destroyed=True, names=["test-realm"]
        )

    def test_get_policy(self):
        """Test get_policy function"""
        # Setup mock module
        mock_module = Mock()
        mock_module.params = {"qos_policy": "test-policy"}

        # Setup mock blade
        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.get_qos_policies.return_value = mock_response

        # Call function
        result = get_policy(mock_module, mock_blade)

        # Verify result
        assert result is True
        mock_blade.get_qos_policies.assert_called_once_with(names=["test-policy"])

    def test_update_realm_without_qos_membership_is_noop(self):
        """A realm with no QoS policy answers the members GET with an error
        response that has no ``items``. update_realm must not touch
        ``.items`` on it and must report no change.
        """
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-realm",
            "state": "present",
            "qos_policy": None,
            "eradicate": False,
            "rename": None,
        }
        mock_module.check_mode = False

        mock_blade = Mock()
        error_response = Mock(spec=["status_code"])
        error_response.status_code = 400
        mock_blade.get_qos_policies_members.return_value = error_response

        try:
            update_realm(mock_module, mock_blade)
        except SystemExit:
            pass

        mock_blade.delete_qos_policies_members.assert_not_called()
        mock_blade.post_qos_policies_members.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_realm.get_pending_realm")
    @patch("plugins.modules.purefb_realm.get_realm")
    @patch("plugins.modules.purefb_realm.LooseVersion")
    @patch("plugins.modules.purefb_realm.get_system")
    @patch("plugins.modules.purefb_realm.AnsibleModule")
    @patch("plugins.modules.purefb_realm.HAS_PURESTORAGE", True)
    def test_main_rename_already_done_is_noop(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
    ):
        """Re-running a rename after it happened must not create a new
        realm under the old name.
        """
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "old-realm",
            "without_default_access_list": True,
            "state": "present",
            "qos_policy": None,
            "eradicate": False,
            "rename": "new-realm",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.19"]
        mock_get_system.return_value = mock_blade
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        # Old name is gone, but the rename target exists
        mock_get_realm.return_value = None
        mock_get_pending_realm.return_value = None
        mock_blade.get_realms.return_value.status_code = 200

        try:
            main()
        except SystemExit:
            pass

        mock_blade.get_realms.assert_called_once_with(
            destroyed=False, names=["new-realm"]
        )
        mock_blade.post_realms.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_realm.get_error_message", Mock(return_value="x"))
    def test_make_realm_false_access_list_failure_carries_hint(self):
        """Purity//FB rejects without_default_access_list=false; the failure
        message must tell the user which setting to change.
        """
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-realm",
            "without_default_access_list": False,
            "state": "present",
            "qos_policy": None,
            "eradicate": False,
            "rename": None,
        }
        mock_module.check_mode = False

        mock_blade = Mock()
        mock_post_response = Mock()
        mock_post_response.status_code = 400
        mock_blade.post_realms.return_value = mock_post_response

        try:
            make_realm(mock_module, mock_blade)
        except SystemExit:
            pass

        mock_blade.post_realms.assert_called_once_with(
            names=["test-realm"], without_default_access_list=False
        )
        mock_module.fail_json.assert_called_once()
        assert (
            "without_default_access_list" in mock_module.fail_json.call_args[1]["msg"]
        )


def _realm_module(default_object_server, check_mode=False, **overrides):
    """Mock AnsibleModule for an existing realm with default_object_server."""
    mock_module = Mock()
    mock_module.exit_json = Mock(side_effect=SystemExit)
    mock_module.fail_json = Mock(side_effect=SystemExit)
    params = {
        "name": "test-realm",
        "without_default_access_list": True,
        "state": "present",
        "qos_policy": None,
        "eradicate": False,
        "rename": None,
        "default_object_server": default_object_server,
    }
    params.update(overrides)
    mock_module.params = params
    mock_module.check_mode = check_mode
    return mock_module


def _defaults_response(server_name):
    """GET realms/defaults answer: one entry whose object_store names the
    server, or an empty object_store when server_name is None."""
    res = Mock()
    res.status_code = 200
    entry = Mock()
    if server_name is None:
        entry.object_store = []
    else:
        store_default = Mock()
        store_default.server = Mock()
        store_default.server.name = server_name
        entry.object_store = [store_default]
    res.items = [entry]
    return res


def _ok():
    res = Mock()
    res.status_code = 200
    return res


def _error(message="boom"):
    res = Mock()
    res.status_code = 400
    err = Mock()
    err.message = message
    res.errors = [err]
    return res


@patch("plugins.modules.purefb_realm.Reference")
@patch("plugins.modules.purefb_realm.ObjectStoreDefault")
@patch("plugins.modules.purefb_realm.RealmDefaults")
@patch("plugins.modules.purefb_realm.get_pending_realm")
@patch("plugins.modules.purefb_realm.get_realm")
@patch("plugins.modules.purefb_realm.LooseVersion")
@patch("plugins.modules.purefb_realm.get_system")
@patch("plugins.modules.purefb_realm.AnsibleModule")
@patch("plugins.modules.purefb_realm.HAS_PURESTORAGE", True)
class TestPurefbRealmDefaultObjectServer:
    """default_object_server: GET/PATCH realms/defaults (REST 2.20)."""

    def _setup(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        module,
        current_default,
        realm_exists=True,
        pending=None,
    ):
        mock_ansible_module.return_value = module
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.30"]
        mock_get_system.return_value = mock_blade
        # both version gates pass
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_get_realm.return_value = realm_exists
        mock_get_pending_realm.return_value = pending
        # no QoS policy on the realm
        mock_blade.get_qos_policies_members.return_value = _error()
        mock_blade.get_realms_defaults.return_value = _defaults_response(
            current_default
        )
        mock_blade.get_servers.return_value = _ok()
        mock_blade.patch_realms_defaults.return_value = _ok()
        mock_blade.patch_realms.return_value = _ok()
        mock_blade.post_realms.return_value = _ok()
        return mock_blade

    def test_set_qualifies_bare_name(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_defaults,
        mock_object_store_default,
        mock_reference,
    ):
        """A bare server name is qualified with the realm name before the
        existence check and the PATCH."""
        module = _realm_module("srv")
        blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            mock_get_realm,
            mock_get_pending_realm,
            module,
            current_default=None,
        )

        try:
            main()
        except SystemExit:
            pass

        blade.get_realms_defaults.assert_called_once_with(realm_names=["test-realm"])
        blade.get_servers.assert_called_once_with(names=["test-realm::srv"])
        mock_reference.assert_called_once_with(name="test-realm::srv")
        mock_object_store_default.assert_called_once_with(
            server=mock_reference.return_value
        )
        mock_realm_defaults.assert_called_once_with(
            object_store=[mock_object_store_default.return_value]
        )
        blade.patch_realms_defaults.assert_called_once_with(
            realm_names=["test-realm"],
            default_realm_configuration=mock_realm_defaults.return_value,
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_already_set_is_noop(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_defaults,
        mock_object_store_default,
        mock_reference,
    ):
        """Fully qualified name equal to the current default: nothing sent."""
        module = _realm_module("test-realm::srv")
        blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            mock_get_realm,
            mock_get_pending_realm,
            module,
            current_default="test-realm::srv",
        )

        try:
            main()
        except SystemExit:
            pass

        blade.get_servers.assert_not_called()
        blade.patch_realms_defaults.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_clear_sends_empty_object_store(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_defaults,
        mock_object_store_default,
        mock_reference,
    ):
        """An empty string clears the default with object_store=[]."""
        module = _realm_module("")
        blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            mock_get_realm,
            mock_get_pending_realm,
            module,
            current_default="test-realm::srv",
        )

        try:
            main()
        except SystemExit:
            pass

        blade.get_servers.assert_not_called()
        mock_object_store_default.assert_not_called()
        mock_realm_defaults.assert_called_once_with(object_store=[])
        blade.patch_realms_defaults.assert_called_once_with(
            realm_names=["test-realm"],
            default_realm_configuration=mock_realm_defaults.return_value,
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_clear_when_already_clear_is_noop(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_defaults,
        mock_object_store_default,
        mock_reference,
    ):
        module = _realm_module("")
        blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            mock_get_realm,
            mock_get_pending_realm,
            module,
            current_default=None,
        )

        try:
            main()
        except SystemExit:
            pass

        blade.patch_realms_defaults.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_check_mode_reports_change_without_patch(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_defaults,
        mock_object_store_default,
        mock_reference,
    ):
        module = _realm_module("srv", check_mode=True)
        blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            mock_get_realm,
            mock_get_pending_realm,
            module,
            current_default=None,
        )

        try:
            main()
        except SystemExit:
            pass

        blade.get_servers.assert_called_once_with(names=["test-realm::srv"])
        blade.patch_realms_defaults.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_missing_server_fails_before_patch(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_defaults,
        mock_object_store_default,
        mock_reference,
    ):
        module = _realm_module("srv")
        blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            mock_get_realm,
            mock_get_pending_realm,
            module,
            current_default=None,
        )
        blade.get_servers.return_value = _error()

        try:
            main()
        except SystemExit:
            pass

        blade.patch_realms_defaults.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "test-realm::srv does not exist in realm test-realm" in msg

    def test_requires_rest_2_20(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_defaults,
        mock_object_store_default,
        mock_reference,
    ):
        """Realms exist from 2.19 but the defaults endpoint needs 2.20; the
        gate fails before any read or write."""
        module = _realm_module("srv")
        blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            mock_get_realm,
            mock_get_pending_realm,
            module,
            current_default=None,
        )
        # realm gate passes, realm-defaults gate fails
        mock_loose_version.return_value.__gt__ = Mock(side_effect=[False, True])

        try:
            main()
        except SystemExit:
            pass

        blade.get_realms_defaults.assert_not_called()
        blade.patch_realms_defaults.assert_not_called()
        module.fail_json.assert_called_once()
        assert "4.6.3" in module.fail_json.call_args[1]["msg"]

    def test_patch_failure_is_reported(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_defaults,
        mock_object_store_default,
        mock_reference,
    ):
        module = _realm_module("srv")
        blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            mock_get_realm,
            mock_get_pending_realm,
            module,
            current_default=None,
        )
        blade.patch_realms_defaults.return_value = _error("nope")

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Setting default object store server for realm test-realm" in msg

    def test_defaults_read_failure_is_reported(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_defaults,
        mock_object_store_default,
        mock_reference,
    ):
        module = _realm_module("srv")
        blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            mock_get_realm,
            mock_get_pending_realm,
            module,
            current_default=None,
        )
        blade.get_realms_defaults.return_value = _error("nope")

        try:
            main()
        except SystemExit:
            pass

        blade.patch_realms_defaults.assert_not_called()
        module.fail_json.assert_called_once()
        assert "Failed to read defaults" in module.fail_json.call_args[1]["msg"]

    def test_no_defaults_entry_means_unset(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_defaults,
        mock_object_store_default,
        mock_reference,
    ):
        """A realm with no defaults entry at all counts as unset."""
        module = _realm_module("srv")
        blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            mock_get_realm,
            mock_get_pending_realm,
            module,
            current_default=None,
        )
        blade.get_realms_defaults.return_value.items = []

        try:
            main()
        except SystemExit:
            pass

        blade.patch_realms_defaults.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    def test_create_checks_server_before_post_then_sets_default(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_defaults,
        mock_object_store_default,
        mock_reference,
    ):
        module = _realm_module("srv")
        blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            mock_get_realm,
            mock_get_pending_realm,
            module,
            current_default=None,
            realm_exists=None,
        )

        try:
            main()
        except SystemExit:
            pass

        blade.get_servers.assert_called_with(names=["test-realm::srv"])
        blade.post_realms.assert_called_once_with(
            names=["test-realm"], without_default_access_list=True
        )
        blade.patch_realms_defaults.assert_called_once_with(
            realm_names=["test-realm"],
            default_realm_configuration=mock_realm_defaults.return_value,
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_create_with_missing_server_fails_before_post(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_defaults,
        mock_object_store_default,
        mock_reference,
    ):
        module = _realm_module("srv")
        blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            mock_get_realm,
            mock_get_pending_realm,
            module,
            current_default=None,
            realm_exists=None,
        )
        blade.get_servers.return_value = _error()

        try:
            main()
        except SystemExit:
            pass

        blade.post_realms.assert_not_called()
        blade.patch_realms_defaults.assert_not_called()
        module.fail_json.assert_called_once()
        assert "does not exist in realm" in module.fail_json.call_args[1]["msg"]

    def test_rename_applies_default_under_new_name(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_defaults,
        mock_object_store_default,
        mock_reference,
    ):
        module = _realm_module("srv", rename="new-realm")
        blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            mock_get_realm,
            mock_get_pending_realm,
            module,
            current_default=None,
        )

        try:
            main()
        except SystemExit:
            pass

        blade.patch_realms.assert_called_once()
        blade.get_realms_defaults.assert_called_once_with(realm_names=["new-realm"])
        # checked under the old name before the rename, under the new name
        # when the default is applied
        assert [c[1]["names"] for c in blade.get_servers.call_args_list] == [
            ["test-realm::srv"],
            ["new-realm::srv"],
        ]
        mock_reference.assert_called_once_with(name="new-realm::srv")
        blade.patch_realms_defaults.assert_called_once_with(
            realm_names=["new-realm"],
            default_realm_configuration=mock_realm_defaults.return_value,
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_recover_applies_default(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_defaults,
        mock_object_store_default,
        mock_reference,
    ):
        module = _realm_module("srv")
        blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            mock_get_realm,
            mock_get_pending_realm,
            module,
            current_default=None,
            realm_exists=None,
            pending=True,
        )

        try:
            main()
        except SystemExit:
            pass

        blade.patch_realms.assert_called_once()
        blade.patch_realms_defaults.assert_called_once_with(
            realm_names=["test-realm"],
            default_realm_configuration=mock_realm_defaults.return_value,
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_absent_ignores_default_object_server(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_defaults,
        mock_object_store_default,
        mock_reference,
    ):
        module = _realm_module("srv", state="absent")
        blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            mock_get_realm,
            mock_get_pending_realm,
            module,
            current_default=None,
        )

        try:
            main()
        except SystemExit:
            pass

        blade.patch_realms.assert_called_once()
        blade.get_realms_defaults.assert_not_called()
        blade.patch_realms_defaults.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_rename_check_mode_refuses_missing_server(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_defaults,
        mock_object_store_default,
        mock_reference,
    ):
        """Until the rename lands the server is named under the old realm;
        check mode refuses a missing one without renaming anything."""
        module = _realm_module("srv", rename="new-realm", check_mode=True)
        blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            mock_get_realm,
            mock_get_pending_realm,
            module,
            current_default=None,
        )
        blade.get_servers.return_value = _error()

        try:
            main()
        except SystemExit:
            pass

        blade.get_servers.assert_called_once_with(names=["test-realm::srv"])
        blade.patch_realms.assert_not_called()
        blade.patch_realms_defaults.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "test-realm::srv does not exist in realm test-realm" in msg

    def test_rename_check_mode_reports_change_without_writes(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_defaults,
        mock_object_store_default,
        mock_reference,
    ):
        module = _realm_module("srv", rename="new-realm", check_mode=True)
        blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            mock_get_realm,
            mock_get_pending_realm,
            module,
            current_default=None,
        )

        try:
            main()
        except SystemExit:
            pass

        blade.get_servers.assert_called_once_with(names=["test-realm::srv"])
        blade.patch_realms.assert_not_called()
        blade.get_realms_defaults.assert_not_called()
        blade.patch_realms_defaults.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_rename_accepts_server_qualified_with_old_name(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_defaults,
        mock_object_store_default,
        mock_reference,
    ):
        """A value qualified with the old realm name is applied under the
        new one after the rename."""
        module = _realm_module("test-realm::srv", rename="new-realm")
        blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            mock_get_realm,
            mock_get_pending_realm,
            module,
            current_default=None,
        )

        try:
            main()
        except SystemExit:
            pass

        assert [c[1]["names"] for c in blade.get_servers.call_args_list] == [
            ["test-realm::srv"],
            ["new-realm::srv"],
        ]
        mock_reference.assert_called_once_with(name="new-realm::srv")
        blade.patch_realms_defaults.assert_called_once_with(
            realm_names=["new-realm"],
            default_realm_configuration=mock_realm_defaults.return_value,
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_already_renamed_rerun_reconciles_default(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_defaults,
        mock_object_store_default,
        mock_reference,
    ):
        """name=old rename=new after the rename happened: no realm write,
        but the default is still reconciled under the new name."""
        module = _realm_module("srv", rename="new-realm")
        blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            mock_get_realm,
            mock_get_pending_realm,
            module,
            current_default=None,
            realm_exists=None,
        )
        # the old name is gone, the new one exists
        blade.get_realms.return_value = _ok()

        try:
            main()
        except SystemExit:
            pass

        blade.post_realms.assert_not_called()
        blade.patch_realms.assert_not_called()
        blade.get_realms_defaults.assert_called_once_with(realm_names=["new-realm"])
        blade.get_servers.assert_called_once_with(names=["new-realm::srv"])
        blade.patch_realms_defaults.assert_called_once_with(
            realm_names=["new-realm"],
            default_realm_configuration=mock_realm_defaults.return_value,
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_already_renamed_rerun_with_default_in_place_is_noop(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_defaults,
        mock_object_store_default,
        mock_reference,
    ):
        module = _realm_module("test-realm::srv", rename="new-realm")
        blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            mock_get_realm,
            mock_get_pending_realm,
            module,
            current_default="new-realm::srv",
            realm_exists=None,
        )
        blade.get_realms.return_value = _ok()

        try:
            main()
        except SystemExit:
            pass

        blade.post_realms.assert_not_called()
        blade.patch_realms.assert_not_called()
        blade.get_servers.assert_not_called()
        blade.patch_realms_defaults.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_recover_check_mode_refuses_missing_server(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_defaults,
        mock_object_store_default,
        mock_reference,
    ):
        module = _realm_module("srv", check_mode=True)
        blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            mock_get_realm,
            mock_get_pending_realm,
            module,
            current_default=None,
            realm_exists=None,
            pending=True,
        )
        blade.get_servers.return_value = _error()

        try:
            main()
        except SystemExit:
            pass

        blade.patch_realms.assert_not_called()
        blade.patch_realms_defaults.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "test-realm::srv does not exist in realm test-realm" in msg

    def test_missing_sdk_fails_before_any_array_call(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_realm,
        mock_get_pending_realm,
        mock_realm_defaults,
        mock_object_store_default,
        mock_reference,
    ):
        module = _realm_module("srv")
        self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            mock_get_realm,
            mock_get_pending_realm,
            module,
            current_default=None,
        )

        # a method-level patch decorator would be entered before the
        # class-level HAS_PURESTORAGE=True patch, so patch inline instead
        with patch("plugins.modules.purefb_realm.HAS_PURESTORAGE", False):
            try:
                main()
            except SystemExit:
                pass

        module.fail_json.assert_called_once_with(
            msg="py-pure-client sdk is required for this module"
        )
        mock_get_system.assert_not_called()
