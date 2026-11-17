# Copyright: (c) 2026, Pure Storage Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_timeout module."""

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

from plugins.module_utils.version import LooseVersion as RealLooseVersion
from plugins.modules.purefb_timeout import (
    main,
    set_timeout,
    disable_timeout,
    _context_kwargs,
    GET_CONTEXT_API_VERSION,
    PATCH_CONTEXT_API_VERSION,
)


def _params(timeout=30, state="present", context=""):
    return {"timeout": timeout, "state": state, "context": context}


def _blade_with_timeout(idle_minutes, patch_status=200):
    """A blade mock whose get_arrays reports idle_minutes and whose PATCH succeeds"""
    blade = Mock()
    array = Mock()
    array.idle_timeout = idle_minutes * 60000
    blade.get_arrays.return_value.status_code = 200
    blade.get_arrays.return_value.items = [array]
    blade.patch_arrays.return_value.status_code = patch_status
    return blade


class TestPurefbTimeout:
    """Test cases for purefb_timeout module"""

    @patch("plugins.modules.purefb_timeout.flashblade.Array")
    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_set_timeout_success(
        self, mock_ansible_module, mock_get_system, mock_array_class
    ):
        """Test successful timeout set"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = _params(timeout=30)
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_arrays.return_value = mock_response
        mock_get_system.return_value = mock_blade

        # Call function
        set_timeout(mock_module, mock_blade)

        # Verify
        mock_blade.patch_arrays.assert_called_once()
        mock_array_class.assert_called_once_with(idle_timeout=30 * 60000)
        mock_module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_set_timeout_check_mode(self, mock_ansible_module, mock_get_system):
        """Test timeout set in check mode"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = True
        mock_module.params = _params(timeout=30)
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_get_system.return_value = mock_blade

        # Call function
        set_timeout(mock_module, mock_blade)

        # Verify - should not call patch_arrays in check mode
        mock_blade.patch_arrays.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_timeout.get_error_message")
    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_set_timeout_failure(
        self, mock_ansible_module, mock_get_system, mock_get_error_message
    ):
        """Test timeout set failure reports the array error"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = _params(timeout=30)
        mock_ansible_module.return_value = mock_module
        mock_get_error_message.return_value = "array said no"

        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 400
        mock_blade.patch_arrays.return_value = mock_response
        mock_get_system.return_value = mock_blade

        # Call function
        set_timeout(mock_module, mock_blade)

        # Verify
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "Failed to set GUI idle timeout" in call_args["msg"]
        assert "array said no" in call_args["msg"]

    @patch("plugins.modules.purefb_timeout.flashblade.Array")
    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_disable_timeout_success(
        self, mock_ansible_module, mock_get_system, mock_array_class
    ):
        """Test successful timeout disable"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_arrays.return_value = mock_response
        mock_get_system.return_value = mock_blade

        # Call function
        disable_timeout(mock_module, mock_blade)

        # Verify
        mock_blade.patch_arrays.assert_called_once()
        mock_array_class.assert_called_once_with(idle_timeout=0)
        mock_module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_disable_timeout_check_mode(self, mock_ansible_module, mock_get_system):
        """Test timeout disable in check mode"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = True
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_get_system.return_value = mock_blade

        # Call function
        disable_timeout(mock_module, mock_blade)

        # Verify - should not call patch_arrays in check mode
        mock_blade.patch_arrays.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_timeout.get_error_message")
    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_disable_timeout_failure(
        self, mock_ansible_module, mock_get_system, mock_get_error_message
    ):
        """Test timeout disable failure reports the array error"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module
        mock_get_error_message.return_value = "array said no"

        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 400
        mock_blade.patch_arrays.return_value = mock_response
        mock_get_system.return_value = mock_blade

        # Call function
        disable_timeout(mock_module, mock_blade)

        # Verify
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "Failed to disable GUI idle timeout" in call_args["msg"]
        assert "array said no" in call_args["msg"]

    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_main_timeout_unchanged(self, mock_ansible_module, mock_get_system):
        """Test main when timeout is already set correctly"""
        # Setup mocks
        mock_module = Mock()
        mock_module.params = _params(timeout=30, state="present")
        mock_ansible_module.return_value = mock_module

        mock_blade = _blade_with_timeout(30)  # Already set to 30 minutes
        mock_get_system.return_value = mock_blade

        # Call main
        main()

        # Verify - should not update if timeout is already correct
        mock_blade.patch_arrays.assert_not_called()
        mock_module.fail_json.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_main_timeout_already_disabled(self, mock_ansible_module, mock_get_system):
        """Test main when timeout is already disabled"""
        # Setup mocks
        mock_module = Mock()
        mock_module.params = _params(timeout=30, state="absent")
        mock_ansible_module.return_value = mock_module

        mock_blade = _blade_with_timeout(0)  # Already disabled
        mock_get_system.return_value = mock_blade

        # Call main
        main()

        # Verify - should not update if timeout is already disabled
        mock_blade.patch_arrays.assert_not_called()
        mock_module.fail_json.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_main_invalid_timeout_too_low(self, mock_ansible_module, mock_get_system):
        """Test main with timeout value too low"""
        # Setup mocks
        mock_module = Mock()
        mock_module.params = _params(timeout=3, state="present")
        mock_module.check_mode = False
        # Make fail_json raise exception to stop execution
        mock_module.fail_json.side_effect = SystemExit("fail_json called")
        mock_ansible_module.return_value = mock_module

        mock_blade = _blade_with_timeout(0)
        mock_get_system.return_value = mock_blade

        # Call main - should raise SystemExit
        try:
            main()
        except SystemExit:
            pass

        # Verify - should fail with invalid timeout message
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "Timeout value must be between 5 and 180 minutes" in call_args["msg"]

    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_main_invalid_timeout_too_high(self, mock_ansible_module, mock_get_system):
        """Test main with timeout value too high"""
        # Setup mocks
        mock_module = Mock()
        mock_module.params = _params(timeout=200, state="present")
        mock_module.check_mode = False
        # Make fail_json raise exception to stop execution
        mock_module.fail_json.side_effect = SystemExit("fail_json called")
        mock_ansible_module.return_value = mock_module

        mock_blade = _blade_with_timeout(0)
        mock_get_system.return_value = mock_blade

        # Call main - should raise SystemExit
        try:
            main()
        except SystemExit:
            pass

        # Verify - should fail with invalid timeout message
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "Timeout value must be between 5 and 180 minutes" in call_args["msg"]

    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", False)
    def test_main_missing_sdk(self, mock_ansible_module, mock_get_system):
        """Test main when pypureclient SDK is missing"""
        # Setup mocks
        mock_module = Mock()
        mock_module.params = _params(timeout=30, state="present")
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

    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_main_valid_timeout_boundaries(self, mock_ansible_module, mock_get_system):
        """Test main with valid timeout boundary values"""
        valid_timeouts = [5, 30, 180]  # Min, middle, max

        for timeout in valid_timeouts:
            # Setup mocks
            mock_module = Mock()
            mock_module.params = _params(timeout=timeout, state="present")
            mock_ansible_module.return_value = mock_module

            mock_blade = _blade_with_timeout(0)  # Different from target
            mock_get_system.return_value = mock_blade

            # Call main
            main()

            # Verify - should not fail validation
            assert not any(
                "Timeout value must be between 5 and 180 minutes" in str(call)
                for call in mock_module.fail_json.call_args_list
            )

            # Reset mocks for next iteration
            mock_module.reset_mock()
            mock_blade.reset_mock()
            mock_ansible_module.reset_mock()
            mock_get_system.reset_mock()

    @patch("plugins.modules.purefb_timeout.flashblade.Array")
    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_main_set_timeout_when_different(
        self, mock_ansible_module, mock_get_system, mock_array_class
    ):
        """Test main sets timeout when current value is different"""
        # Setup mocks
        mock_module = Mock()
        mock_module.params = _params(timeout=60, state="present")
        mock_module.check_mode = False
        # Make exit_json raise SystemExit to simulate actual module behavior
        mock_module.exit_json.side_effect = SystemExit("exit_json called")
        mock_ansible_module.return_value = mock_module

        mock_blade = _blade_with_timeout(30)  # Currently 30 minutes
        mock_get_system.return_value = mock_blade

        # Call main - set_timeout will call exit_json and raise SystemExit
        try:
            main()
        except SystemExit:
            pass

        # Verify - should call patch_arrays to update timeout
        mock_blade.patch_arrays.assert_called_once()
        mock_array_class.assert_called_once_with(idle_timeout=60 * 60000)
        # set_timeout calls exit_json(changed=True), which exits the module
        mock_module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_timeout.flashblade.Array")
    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_main_disable_timeout_when_enabled(
        self, mock_ansible_module, mock_get_system, mock_array_class
    ):
        """Test main disables timeout when currently enabled"""
        # Setup mocks
        mock_module = Mock()
        mock_module.params = _params(timeout=30, state="absent")
        mock_module.check_mode = False
        # Make exit_json raise SystemExit to simulate actual module behavior
        mock_module.exit_json.side_effect = SystemExit("exit_json called")
        mock_ansible_module.return_value = mock_module

        mock_blade = _blade_with_timeout(30)  # Currently enabled
        mock_get_system.return_value = mock_blade

        # Call main - disable_timeout will call exit_json and raise SystemExit
        try:
            main()
        except SystemExit:
            pass

        # Verify - should call patch_arrays to disable timeout
        mock_blade.patch_arrays.assert_called_once()
        mock_array_class.assert_called_once_with(idle_timeout=0)
        # disable_timeout calls exit_json(changed=True), which exits the module
        mock_module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_timeout.get_error_message")
    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_main_get_arrays_error_fails(
        self, mock_ansible_module, mock_get_system, mock_get_error_message
    ):
        """Test main fails cleanly when the array read itself is refused"""
        mock_module = Mock()
        mock_module.params = _params(timeout=30, state="present")
        mock_module.check_mode = False
        mock_module.fail_json.side_effect = SystemExit("fail_json called")
        mock_ansible_module.return_value = mock_module
        mock_get_error_message.return_value = "Cannot find array in fleet"

        mock_blade = Mock()
        mock_blade.get_arrays.return_value.status_code = 400
        mock_get_system.return_value = mock_blade

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "Failed to get GUI idle timeout" in msg
        assert "Cannot find array in fleet" in msg
        mock_blade.patch_arrays.assert_not_called()


class TestPurefbTimeoutContext:
    """Fleet context handling: kwargs, per-call version gates, main wiring"""

    def test_context_kwargs_without_context_is_empty(self):
        """No context set: nothing is added and no version check happens"""
        module = Mock()
        module.params = _params(context="")

        assert _context_kwargs(module, "2.17", PATCH_CONTEXT_API_VERSION) == {}
        module.fail_json.assert_not_called()

    @patch("plugins.modules.purefb_timeout.LooseVersion", RealLooseVersion)
    def test_context_kwargs_at_gate_returns_context_names(self):
        """Context set and the array is at the gate: context_names is sent"""
        module = Mock()
        module.params = _params(context="fleet-member-2")

        kwargs = _context_kwargs(module, "2.30", PATCH_CONTEXT_API_VERSION)

        assert kwargs == {"context_names": ["fleet-member-2"]}
        module.fail_json.assert_not_called()

    @patch("plugins.modules.purefb_timeout.LooseVersion", RealLooseVersion)
    def test_context_kwargs_above_gate_returns_context_names(self):
        """A newer array than the gate still gets context_names"""
        module = Mock()
        module.params = _params(context="fleet-member-2")

        kwargs = _context_kwargs(module, "2.31", GET_CONTEXT_API_VERSION)

        assert kwargs == {"context_names": ["fleet-member-2"]}

    @patch("plugins.modules.purefb_timeout.LooseVersion", RealLooseVersion)
    def test_context_kwargs_below_gate_fails_naming_versions(self):
        """Context set below the gate: fail_json names both versions"""
        module = Mock()
        module.params = _params(context="fleet-member-2")
        module.fail_json.side_effect = SystemExit("fail_json called")

        try:
            _context_kwargs(module, "2.29", PATCH_CONTEXT_API_VERSION)
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "context" in msg
        assert "2.30" in msg
        assert "2.29" in msg

    def test_gate_constants_match_sdk_signatures(self):
        """get_arrays gained context_names at 2.22, patch_arrays at 2.30"""
        assert GET_CONTEXT_API_VERSION == "2.22"
        assert PATCH_CONTEXT_API_VERSION == "2.30"
        assert RealLooseVersion(GET_CONTEXT_API_VERSION) < RealLooseVersion(
            PATCH_CONTEXT_API_VERSION
        )

    @patch("plugins.modules.purefb_timeout.flashblade.Array")
    def test_set_timeout_passes_context_kwargs(self, mock_array_class):
        """set_timeout forwards the context kwargs to patch_arrays"""
        module = Mock()
        module.check_mode = False
        module.params = _params(timeout=45, context="fleet-member-2")
        blade = Mock()
        blade.patch_arrays.return_value.status_code = 200

        set_timeout(module, blade, {"context_names": ["fleet-member-2"]})

        mock_array_class.assert_called_once_with(idle_timeout=45 * 60000)
        blade.patch_arrays.assert_called_once_with(
            mock_array_class.return_value, context_names=["fleet-member-2"]
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_timeout.flashblade.Array")
    def test_disable_timeout_passes_context_kwargs(self, mock_array_class):
        """disable_timeout forwards the context kwargs to patch_arrays"""
        module = Mock()
        module.check_mode = False
        module.params = _params(state="absent", context="fleet-member-2")
        blade = Mock()
        blade.patch_arrays.return_value.status_code = 200

        disable_timeout(module, blade, {"context_names": ["fleet-member-2"]})

        mock_array_class.assert_called_once_with(idle_timeout=0)
        blade.patch_arrays.assert_called_once_with(
            mock_array_class.return_value, context_names=["fleet-member-2"]
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_timeout.flashblade.Array")
    def test_set_timeout_without_context_kwargs_sends_none(self, mock_array_class):
        """set_timeout with no context kwargs sends only the body"""
        module = Mock()
        module.check_mode = False
        module.params = _params(timeout=45)
        blade = Mock()
        blade.patch_arrays.return_value.status_code = 200

        set_timeout(module, blade, {})

        blade.patch_arrays.assert_called_once_with(mock_array_class.return_value)

    @patch("plugins.modules.purefb_timeout.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_timeout.get_rest_api_version")
    @patch("plugins.modules.purefb_timeout.flashblade.Array")
    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_main_with_context_sends_context_to_get_and_patch(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_array_class,
        mock_get_rest_api_version,
    ):
        """At REST 2.30 both the read and the write carry context_names"""
        mock_module = Mock()
        mock_module.params = _params(timeout=60, state="present", context="fb-2")
        mock_module.check_mode = False
        mock_module.exit_json.side_effect = SystemExit("exit_json called")
        mock_ansible_module.return_value = mock_module
        mock_get_rest_api_version.return_value = "2.30"

        mock_blade = _blade_with_timeout(30)
        mock_get_system.return_value = mock_blade

        try:
            main()
        except SystemExit:
            pass

        mock_blade.get_arrays.assert_called_once_with(context_names=["fb-2"])
        mock_array_class.assert_called_once_with(idle_timeout=60 * 60000)
        mock_blade.patch_arrays.assert_called_once_with(
            mock_array_class.return_value, context_names=["fb-2"]
        )
        mock_module.fail_json.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_timeout.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_timeout.get_rest_api_version")
    @patch("plugins.modules.purefb_timeout.flashblade.Array")
    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_main_with_context_disable_sends_context_to_patch(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_array_class,
        mock_get_rest_api_version,
    ):
        """state=absent with a context disables the timeout on that member"""
        mock_module = Mock()
        mock_module.params = _params(state="absent", context="fb-2")
        mock_module.check_mode = False
        mock_module.exit_json.side_effect = SystemExit("exit_json called")
        mock_ansible_module.return_value = mock_module
        mock_get_rest_api_version.return_value = "2.30"

        mock_blade = _blade_with_timeout(30)
        mock_get_system.return_value = mock_blade

        try:
            main()
        except SystemExit:
            pass

        mock_blade.get_arrays.assert_called_once_with(context_names=["fb-2"])
        mock_array_class.assert_called_once_with(idle_timeout=0)
        mock_blade.patch_arrays.assert_called_once_with(
            mock_array_class.return_value, context_names=["fb-2"]
        )
        mock_module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_timeout.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_timeout.get_rest_api_version")
    @patch("plugins.modules.purefb_timeout.flashblade.Array")
    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_main_without_context_sends_no_context_names(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_array_class,
        mock_get_rest_api_version,
    ):
        """No context: neither the read nor the write carries context_names"""
        mock_module = Mock()
        mock_module.params = _params(timeout=60, state="present", context="")
        mock_module.check_mode = False
        mock_module.exit_json.side_effect = SystemExit("exit_json called")
        mock_ansible_module.return_value = mock_module
        mock_get_rest_api_version.return_value = "2.30"

        mock_blade = _blade_with_timeout(30)
        mock_get_system.return_value = mock_blade

        try:
            main()
        except SystemExit:
            pass

        mock_blade.get_arrays.assert_called_once_with()
        mock_blade.patch_arrays.assert_called_once_with(mock_array_class.return_value)
        mock_module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_timeout.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_timeout.get_rest_api_version")
    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_main_without_context_ignores_old_rest_version(
        self, mock_ansible_module, mock_get_system, mock_get_rest_api_version
    ):
        """No context on an old array: the module works as before"""
        mock_module = Mock()
        mock_module.params = _params(timeout=30, state="present", context="")
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module
        mock_get_rest_api_version.return_value = "2.17"

        mock_blade = _blade_with_timeout(30)
        mock_get_system.return_value = mock_blade

        main()

        mock_blade.get_arrays.assert_called_once_with()
        mock_module.fail_json.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_timeout.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_timeout.get_rest_api_version")
    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_main_with_context_unchanged_is_idempotent(
        self, mock_ansible_module, mock_get_system, mock_get_rest_api_version
    ):
        """Context set, value already correct: read with context, no write"""
        mock_module = Mock()
        mock_module.params = _params(timeout=30, state="present", context="fb-2")
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module
        mock_get_rest_api_version.return_value = "2.30"

        mock_blade = _blade_with_timeout(30)
        mock_get_system.return_value = mock_blade

        main()

        mock_blade.get_arrays.assert_called_once_with(context_names=["fb-2"])
        mock_blade.patch_arrays.assert_not_called()
        mock_module.fail_json.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_timeout.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_timeout.get_rest_api_version")
    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_main_with_context_check_mode_does_not_write(
        self, mock_ansible_module, mock_get_system, mock_get_rest_api_version
    ):
        """Check mode with a context reports the change without a PATCH"""
        mock_module = Mock()
        mock_module.params = _params(timeout=60, state="present", context="fb-2")
        mock_module.check_mode = True
        mock_module.exit_json.side_effect = SystemExit("exit_json called")
        mock_ansible_module.return_value = mock_module
        mock_get_rest_api_version.return_value = "2.30"

        mock_blade = _blade_with_timeout(30)
        mock_get_system.return_value = mock_blade

        try:
            main()
        except SystemExit:
            pass

        mock_blade.get_arrays.assert_called_once_with(context_names=["fb-2"])
        mock_blade.patch_arrays.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_timeout.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_timeout.get_rest_api_version")
    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_main_context_below_patch_gate_fails_before_any_call(
        self, mock_ansible_module, mock_get_system, mock_get_rest_api_version
    ):
        """REST 2.25 reads with context but cannot PATCH with it: fail up front"""
        mock_module = Mock()
        mock_module.params = _params(timeout=60, state="present", context="fb-2")
        mock_module.check_mode = False
        mock_module.fail_json.side_effect = SystemExit("fail_json called")
        mock_ansible_module.return_value = mock_module
        mock_get_rest_api_version.return_value = "2.25"

        mock_blade = _blade_with_timeout(30)
        mock_get_system.return_value = mock_blade

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "2.30" in msg
        assert "2.25" in msg
        mock_blade.get_arrays.assert_not_called()
        mock_blade.patch_arrays.assert_not_called()

    @patch("plugins.modules.purefb_timeout.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_timeout.get_rest_api_version")
    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_main_context_below_get_gate_fails_before_any_call(
        self, mock_ansible_module, mock_get_system, mock_get_rest_api_version
    ):
        """REST 2.21 predates context on GET /arrays: fail naming 2.22"""
        mock_module = Mock()
        mock_module.params = _params(timeout=60, state="present", context="fb-2")
        mock_module.check_mode = False
        mock_module.fail_json.side_effect = SystemExit("fail_json called")
        mock_ansible_module.return_value = mock_module
        mock_get_rest_api_version.return_value = "2.21"

        mock_blade = _blade_with_timeout(30)
        mock_get_system.return_value = mock_blade

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "2.22" in msg
        assert "2.21" in msg
        mock_blade.get_arrays.assert_not_called()
        mock_blade.patch_arrays.assert_not_called()

    @patch("plugins.modules.purefb_timeout.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_timeout.get_rest_api_version")
    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_main_context_below_gate_fails_even_in_check_mode(
        self, mock_ansible_module, mock_get_system, mock_get_rest_api_version
    ):
        """The gate is not skipped in check mode"""
        mock_module = Mock()
        mock_module.params = _params(timeout=60, state="present", context="fb-2")
        mock_module.check_mode = True
        mock_module.fail_json.side_effect = SystemExit("fail_json called")
        mock_ansible_module.return_value = mock_module
        mock_get_rest_api_version.return_value = "2.29"

        mock_blade = _blade_with_timeout(30)
        mock_get_system.return_value = mock_blade

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert "2.30" in mock_module.fail_json.call_args[1]["msg"]
        mock_blade.get_arrays.assert_not_called()
        mock_module.exit_json.assert_not_called()

    @patch("plugins.modules.purefb_timeout.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_timeout.get_error_message")
    @patch("plugins.modules.purefb_timeout.get_rest_api_version")
    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_main_unknown_context_is_refused_by_array_before_write(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_get_rest_api_version,
        mock_get_error_message,
    ):
        """A context the array does not know fails on the read, no PATCH"""
        mock_module = Mock()
        mock_module.params = _params(timeout=60, state="present", context="nope")
        mock_module.check_mode = False
        mock_module.fail_json.side_effect = SystemExit("fail_json called")
        mock_ansible_module.return_value = mock_module
        mock_get_rest_api_version.return_value = "2.30"
        mock_get_error_message.return_value = "Cannot find array in fleet"

        mock_blade = Mock()
        mock_blade.get_arrays.return_value.status_code = 400
        mock_get_system.return_value = mock_blade

        try:
            main()
        except SystemExit:
            pass

        mock_blade.get_arrays.assert_called_once_with(context_names=["nope"])
        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "Failed to get GUI idle timeout" in msg
        assert "Cannot find array in fleet" in msg
        mock_blade.patch_arrays.assert_not_called()

    @patch("plugins.modules.purefb_timeout.LooseVersion", RealLooseVersion)
    @patch("plugins.modules.purefb_timeout.get_rest_api_version")
    @patch("plugins.modules.purefb_timeout.get_system")
    @patch("plugins.modules.purefb_timeout.AnsibleModule")
    @patch("plugins.modules.purefb_timeout.HAS_PYPURECLIENT", True)
    def test_main_context_resolving_to_many_arrays_is_refused(
        self, mock_ansible_module, mock_get_system, mock_get_rest_api_version
    ):
        """A context that returns several arrays, such as a fleet name: no PATCH"""
        mock_module = Mock()
        mock_module.params = _params(timeout=60, state="present", context="fleet")
        mock_module.check_mode = False
        mock_module.fail_json.side_effect = SystemExit("fail_json called")
        mock_ansible_module.return_value = mock_module
        mock_get_rest_api_version.return_value = "2.30"

        member_a = Mock()
        member_a.idle_timeout = 30 * 60000
        member_b = Mock()
        member_b.idle_timeout = 0
        mock_blade = Mock()
        mock_blade.get_arrays.return_value.status_code = 200
        mock_blade.get_arrays.return_value.items = [member_a, member_b]
        mock_get_system.return_value = mock_blade

        try:
            main()
        except SystemExit:
            pass

        mock_blade.get_arrays.assert_called_once_with(context_names=["fleet"])
        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "single fleet member" in msg
        assert "got 2" in msg
        mock_blade.patch_arrays.assert_not_called()
