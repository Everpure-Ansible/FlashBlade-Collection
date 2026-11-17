# Copyright: (c) 2026, Pure Storage Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_bladename module."""

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

# The collection's real version comparison, so the gate tests compare
# "2.29" < "2.30" the way the module does on an array
from plugins.module_utils.version import LooseVersion as RealLooseVersion

from plugins.modules.purefb_bladename import (
    main,
    update_name,
    _context_kwargs,
    GET_CONTEXT_API_VERSION,
    PATCH_CONTEXT_API_VERSION,
)


def _params(**overrides):
    params = {"name": "current-blade-name", "state": "present", "context": ""}
    params.update(overrides)
    return params


def _module(**overrides):
    module = Mock()
    module.check_mode = False
    module.params = _params(**overrides)
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _blade(current_name="current-blade-name", get_status=200, patch_status=200):
    blade = Mock()
    array = Mock()
    array.name = current_name
    get_response = Mock()
    get_response.status_code = get_status
    get_response.items = [array]
    get_response.errors = [Mock(message="Cannot find array in fleet")]
    blade.get_arrays.return_value = get_response
    patch_response = Mock()
    patch_response.status_code = patch_status
    patch_response.errors = [Mock(message="Invalid name")]
    blade.patch_arrays.return_value = patch_response
    return blade


def _run_main():
    try:
        main()
    except SystemExit:
        pass


class TestPurefbBladename:
    """Test cases for purefb_bladename module"""

    @patch("plugins.modules.purefb_bladename.get_system")
    @patch("plugins.modules.purefb_bladename.AnsibleModule")
    @patch("plugins.modules.purefb_bladename.HAS_PYPURECLIENT", True)
    def test_update_name_success(self, mock_ansible_module, mock_get_system):
        """Test successful blade name update"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = {"name": "new-blade-name", "context": ""}
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_arrays.return_value = mock_response
        mock_get_system.return_value = mock_blade

        # Call function
        update_name(mock_module, mock_blade)

        # Verify
        mock_blade.patch_arrays.assert_called_once()
        mock_module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_bladename.get_system")
    @patch("plugins.modules.purefb_bladename.AnsibleModule")
    @patch("plugins.modules.purefb_bladename.HAS_PYPURECLIENT", True)
    def test_update_name_check_mode(self, mock_ansible_module, mock_get_system):
        """Test blade name update in check mode"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = True
        mock_module.params = {"name": "new-blade-name", "context": ""}
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_get_system.return_value = mock_blade

        # Call function
        update_name(mock_module, mock_blade)

        # Verify - should not call patch_arrays in check mode
        mock_blade.patch_arrays.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_bladename.get_system")
    @patch("plugins.modules.purefb_bladename.AnsibleModule")
    @patch("plugins.modules.purefb_bladename.HAS_PYPURECLIENT", True)
    def test_update_name_failure(self, mock_ansible_module, mock_get_system):
        """Test blade name update failure"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = {"name": "new-blade-name", "context": ""}
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.errors = [Mock(message="Invalid name")]
        mock_blade.patch_arrays.return_value = mock_response
        mock_get_system.return_value = mock_blade

        # Call function
        update_name(mock_module, mock_blade)

        # Verify
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "Failed to change array name" in call_args["msg"]

    @patch("plugins.modules.purefb_bladename.Array")
    def test_update_name_passes_context_kwargs(self, mock_array_class):
        """update_name forwards the context kwargs to patch_arrays"""
        module = _module(name="new-blade-name")
        blade = _blade()

        try:
            update_name(module, blade, {"context_names": ["member1"]})
        except SystemExit:
            pass

        mock_array_class.assert_called_once_with(name="new-blade-name")
        blade.patch_arrays.assert_called_once_with(
            array=mock_array_class.return_value, context_names=["member1"]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_update_name_check_mode_with_context(self):
        """update_name with a context still sends nothing in check mode"""
        module = _module(name="new-blade-name", context="member1")
        module.check_mode = True
        blade = _blade()

        try:
            update_name(module, blade, {"context_names": ["member1"]})
        except SystemExit:
            pass

        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    # ---------------- _context_kwargs ----------------

    @patch("plugins.modules.purefb_bladename.LooseVersion", RealLooseVersion)
    def test_context_kwargs_empty_without_context(self):
        """No context means no context_names kwarg, whatever the REST version"""
        module = _module()
        assert _context_kwargs(module, "2.17", "2.30", "changing the array name") == {}
        module.fail_json.assert_not_called()

    @patch("plugins.modules.purefb_bladename.LooseVersion", RealLooseVersion)
    def test_context_kwargs_added_at_gate(self):
        """A context at exactly the gate version is passed through"""
        module = _module(context="member1")
        kwargs = _context_kwargs(module, "2.30", "2.30", "changing the array name")
        assert kwargs == {"context_names": ["member1"]}
        module.fail_json.assert_not_called()

    @patch("plugins.modules.purefb_bladename.LooseVersion", RealLooseVersion)
    def test_context_kwargs_fails_below_gate(self):
        """A context below the gate fails with the version named"""
        module = _module(context="member1")
        try:
            _context_kwargs(module, "2.29", "2.30", "changing the array name")
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "2.30" in msg
        assert "2.29" in msg
        assert "changing the array name" in msg

    def test_gate_constants(self):
        """The per-method gates match the SDK signatures"""
        assert GET_CONTEXT_API_VERSION == "2.22"
        assert PATCH_CONTEXT_API_VERSION == "2.30"

    # ---------------- main() flows ----------------

    @patch("plugins.modules.purefb_bladename.get_system")
    @patch("plugins.modules.purefb_bladename.AnsibleModule")
    @patch("plugins.modules.purefb_bladename.HAS_PYPURECLIENT", True)
    def test_main_name_unchanged(self, mock_ansible_module, mock_get_system):
        """Test main when name is already set correctly"""
        # Setup mocks
        mock_module = Mock()
        mock_module.params = _params()
        mock_ansible_module.return_value = mock_module

        mock_blade = _blade()
        mock_get_system.return_value = mock_blade

        # Call main
        main()

        # Verify - should not update if name is already correct
        mock_blade.get_arrays.assert_called_once_with()
        mock_blade.patch_arrays.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_bladename.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_bladename.get_rest_api_version")
    @patch("plugins.modules.purefb_bladename.Array")
    @patch("plugins.modules.purefb_bladename.get_system")
    @patch("plugins.modules.purefb_bladename.AnsibleModule")
    @patch("plugins.modules.purefb_bladename.HAS_PYPURECLIENT", True)
    def test_main_rename_without_context(
        self, mock_ansible_module, mock_get_system, mock_array_class, mock_version
    ):
        """Without a context neither call carries context_names"""
        mock_version.return_value = "2.30"
        module = _module(name="new-blade-name")
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run_main()

        blade.get_arrays.assert_called_once_with()
        mock_array_class.assert_called_once_with(name="new-blade-name")
        blade.patch_arrays.assert_called_once_with(array=mock_array_class.return_value)
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_bladename.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_bladename.get_rest_api_version")
    @patch("plugins.modules.purefb_bladename.Array")
    @patch("plugins.modules.purefb_bladename.get_system")
    @patch("plugins.modules.purefb_bladename.AnsibleModule")
    @patch("plugins.modules.purefb_bladename.HAS_PYPURECLIENT", True)
    def test_main_rename_with_context(
        self, mock_ansible_module, mock_get_system, mock_array_class, mock_version
    ):
        """With a context on REST 2.30 both the GET and the PATCH carry it"""
        mock_version.return_value = "2.30"
        module = _module(name="new-blade-name", context="member1")
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run_main()

        blade.get_arrays.assert_called_once_with(context_names=["member1"])
        blade.patch_arrays.assert_called_once_with(
            array=mock_array_class.return_value, context_names=["member1"]
        )
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()

    @patch("plugins.modules.purefb_bladename.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_bladename.get_rest_api_version")
    @patch("plugins.modules.purefb_bladename.get_system")
    @patch("plugins.modules.purefb_bladename.AnsibleModule")
    @patch("plugins.modules.purefb_bladename.HAS_PYPURECLIENT", True)
    def test_main_unchanged_with_context(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """With a context and a matching name the GET carries it and nothing is sent"""
        mock_version.return_value = "2.30"
        module = _module(context="member1")
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run_main()

        blade.get_arrays.assert_called_once_with(context_names=["member1"])
        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_bladename.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_bladename.get_rest_api_version")
    @patch("plugins.modules.purefb_bladename.get_system")
    @patch("plugins.modules.purefb_bladename.AnsibleModule")
    @patch("plugins.modules.purefb_bladename.HAS_PYPURECLIENT", True)
    def test_main_rename_with_context_check_mode(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """Check mode with a context reports the change without a PATCH"""
        mock_version.return_value = "2.30"
        module = _module(name="new-blade-name", context="member1")
        module.check_mode = True
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run_main()

        blade.get_arrays.assert_called_once_with(context_names=["member1"])
        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_bladename.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_bladename.get_rest_api_version")
    @patch("plugins.modules.purefb_bladename.get_system")
    @patch("plugins.modules.purefb_bladename.AnsibleModule")
    @patch("plugins.modules.purefb_bladename.HAS_PYPURECLIENT", True)
    def test_main_context_below_get_gate_fails_before_any_call(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """A context on REST 2.21 fails before the GET is attempted"""
        mock_version.return_value = "2.21"
        module = _module(name="new-blade-name", context="member1")
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run_main()

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "2.22" in msg
        assert "reading the array name" in msg
        blade.get_arrays.assert_not_called()
        blade.patch_arrays.assert_not_called()

    @patch("plugins.modules.purefb_bladename.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_bladename.get_rest_api_version")
    @patch("plugins.modules.purefb_bladename.get_system")
    @patch("plugins.modules.purefb_bladename.AnsibleModule")
    @patch("plugins.modules.purefb_bladename.HAS_PYPURECLIENT", True)
    def test_main_context_below_patch_gate_fails_before_patch(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """A rename with a context on REST 2.29 reads with context but never PATCHes"""
        mock_version.return_value = "2.29"
        module = _module(name="new-blade-name", context="member1")
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run_main()

        blade.get_arrays.assert_called_once_with(context_names=["member1"])
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "2.30" in msg
        assert "changing the array name" in msg
        blade.patch_arrays.assert_not_called()

    @patch("plugins.modules.purefb_bladename.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_bladename.get_rest_api_version")
    @patch("plugins.modules.purefb_bladename.get_system")
    @patch("plugins.modules.purefb_bladename.AnsibleModule")
    @patch("plugins.modules.purefb_bladename.HAS_PYPURECLIENT", True)
    def test_main_context_below_patch_gate_fails_in_check_mode(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """The PATCH gate is evaluated in check mode as well"""
        mock_version.return_value = "2.29"
        module = _module(name="new-blade-name", context="member1")
        module.check_mode = True
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run_main()

        module.fail_json.assert_called_once()
        assert "2.30" in module.fail_json.call_args[1]["msg"]
        module.exit_json.assert_not_called()

    @patch("plugins.modules.purefb_bladename.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_bladename.get_rest_api_version")
    @patch("plugins.modules.purefb_bladename.get_system")
    @patch("plugins.modules.purefb_bladename.AnsibleModule")
    @patch("plugins.modules.purefb_bladename.HAS_PYPURECLIENT", True)
    def test_main_context_between_gates_noop_when_name_matches(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """Between the gates a matching name is a clean no-op (GET only needs 2.22)"""
        mock_version.return_value = "2.25"
        module = _module(context="member1")
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run_main()

        blade.get_arrays.assert_called_once_with(context_names=["member1"])
        blade.patch_arrays.assert_not_called()
        module.fail_json.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_bladename.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_bladename.get_rest_api_version")
    @patch("plugins.modules.purefb_bladename.get_system")
    @patch("plugins.modules.purefb_bladename.AnsibleModule")
    @patch("plugins.modules.purefb_bladename.HAS_PYPURECLIENT", True)
    def test_main_get_arrays_error_fails(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """An error from GET arrays (for example an unknown context) is surfaced"""
        mock_version.return_value = "2.30"
        module = _module(context="no-such-member")
        mock_ansible_module.return_value = module
        blade = _blade(get_status=400)
        mock_get_system.return_value = blade

        _run_main()

        module.fail_json.assert_called_once()
        assert "Failed to get array details" in module.fail_json.call_args[1]["msg"]
        blade.patch_arrays.assert_not_called()

    @patch("plugins.modules.purefb_bladename.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_bladename.get_rest_api_version")
    @patch("plugins.modules.purefb_bladename.get_system")
    @patch("plugins.modules.purefb_bladename.AnsibleModule")
    @patch("plugins.modules.purefb_bladename.HAS_PYPURECLIENT", True)
    def test_main_get_arrays_empty_fails(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """An empty GET arrays response fails instead of raising IndexError"""
        mock_version.return_value = "2.30"
        module = _module()
        mock_ansible_module.return_value = module
        blade = _blade()
        blade.get_arrays.return_value.items = []
        mock_get_system.return_value = blade

        _run_main()

        module.fail_json.assert_called_once()
        assert "No array returned" in module.fail_json.call_args[1]["msg"]
        blade.patch_arrays.assert_not_called()

    @patch("plugins.modules.purefb_bladename.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_bladename.get_rest_api_version")
    @patch("plugins.modules.purefb_bladename.get_system")
    @patch("plugins.modules.purefb_bladename.AnsibleModule")
    @patch("plugins.modules.purefb_bladename.HAS_PYPURECLIENT", True)
    def test_main_context_resolving_to_many_arrays_fails(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """A fleet-name context (several arrays returned) is refused before any PATCH"""
        mock_version.return_value = "2.30"
        module = _module(name="new-blade-name", context="fleet1")
        mock_ansible_module.return_value = module
        blade = _blade()
        second = Mock()
        second.name = "other-member"
        blade.get_arrays.return_value.items.append(second)
        mock_get_system.return_value = blade

        _run_main()

        blade.get_arrays.assert_called_once_with(context_names=["fleet1"])
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "fleet1" in msg
        assert "2 arrays" in msg
        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_not_called()

    @patch("plugins.modules.purefb_bladename.get_system")
    @patch("plugins.modules.purefb_bladename.AnsibleModule")
    @patch("plugins.modules.purefb_bladename.HAS_PYPURECLIENT", True)
    def test_main_invalid_name_format(self, mock_ansible_module, mock_get_system):
        """Test main with invalid blade name format"""
        # Setup mocks
        mock_module = Mock()
        mock_module.params = _params(name="invalid_name!")
        mock_module.check_mode = False
        # Make fail_json raise exception to stop execution
        mock_module.fail_json.side_effect = SystemExit("fail_json called")
        mock_ansible_module.return_value = mock_module

        # Mock blade - get_system is called before validation
        mock_blade = Mock()
        mock_get_system.return_value = mock_blade

        # Call main - should raise SystemExit
        try:
            main()
        except SystemExit:
            pass

        # Verify - should fail with invalid name
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "does not conform to array name rules" in call_args["msg"]
        mock_blade.get_arrays.assert_not_called()

    @patch("plugins.modules.purefb_bladename.get_system")
    @patch("plugins.modules.purefb_bladename.AnsibleModule")
    @patch("plugins.modules.purefb_bladename.HAS_PYPURECLIENT", False)
    def test_main_missing_sdk(self, mock_ansible_module, mock_get_system):
        """Test main when pypureclient SDK is missing"""
        # Setup mocks
        mock_module = Mock()
        mock_module.params = _params(name="blade-name")
        mock_module.check_mode = False
        # Make fail_json raise exception to stop execution
        mock_module.fail_json.side_effect = SystemExit("fail_json called")
        mock_ansible_module.return_value = mock_module

        # Call main - should raise SystemExit
        try:
            main()
        except SystemExit:
            pass

        # Verify - should fail with SDK missing message (before calling get_system)
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "py-pure-client sdk is required" in call_args["msg"]
        # Should not call get_system since SDK check fails first
        mock_get_system.assert_not_called()

    @patch("plugins.modules.purefb_bladename.get_system")
    @patch("plugins.modules.purefb_bladename.AnsibleModule")
    @patch("plugins.modules.purefb_bladename.HAS_PYPURECLIENT", True)
    def test_main_valid_name_formats(self, mock_ansible_module, mock_get_system):
        """Test main with various valid blade name formats"""
        valid_names = [
            "blade1",
            "blade-1",
            "my-blade-123",
            "a",
            "a" * 56,  # Max length (56 chars)
            "blade-name-with-numbers-123",
        ]

        for name in valid_names:
            # Setup mocks
            mock_module = Mock()
            mock_module.params = _params(name=name)
            mock_module.check_mode = False
            mock_ansible_module.return_value = mock_module

            mock_blade = _blade(current_name="different-name")
            mock_get_system.return_value = mock_blade

            # Call main
            main()

            # Verify - should not fail validation
            assert not any(
                "does not conform" in str(call)
                for call in mock_module.fail_json.call_args_list
            )
            mock_blade.patch_arrays.assert_called_once()

    @patch("plugins.modules.purefb_bladename.get_system")
    @patch("plugins.modules.purefb_bladename.AnsibleModule")
    @patch("plugins.modules.purefb_bladename.HAS_PYPURECLIENT", True)
    def test_main_invalid_name_formats(self, mock_ansible_module, mock_get_system):
        """Test main with various invalid blade name formats"""
        invalid_names = [
            "blade_name",  # Underscore not allowed
            "-blade",  # Cannot start with hyphen
            "blade-",  # Cannot end with hyphen
            "blade name",  # Space not allowed
            "blade@name",  # Special char not allowed
            "a" * 57,  # Too long (>56 chars)
        ]

        for name in invalid_names:
            # Setup mocks
            mock_module = Mock()
            mock_module.params = _params(name=name)
            mock_module.check_mode = False
            # Make fail_json raise exception to stop execution
            mock_module.fail_json.side_effect = SystemExit("fail_json called")
            mock_ansible_module.return_value = mock_module

            mock_blade = Mock()
            mock_get_system.return_value = mock_blade

            # Call main - should raise SystemExit
            try:
                main()
            except SystemExit:
                pass

            # Verify - should fail validation
            mock_module.fail_json.assert_called()
            call_args = mock_module.fail_json.call_args[1]
            assert "does not conform to array name rules" in call_args["msg"]

            # Reset mocks for next iteration
            mock_module.reset_mock()
            mock_blade.reset_mock()
            mock_ansible_module.reset_mock()
            mock_get_system.reset_mock()
