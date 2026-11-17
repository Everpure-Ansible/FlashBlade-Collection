# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_tz module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from unittest.mock import Mock, patch, MagicMock

from ansible.module_utils.compat.version import LooseVersion as RealLooseVersion

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

from plugins.modules.purefb_tz import (
    main,
    set_timezone,
    _context_kwargs,
    GET_CONTEXT_API_VERSION,
    PATCH_CONTEXT_API_VERSION,
)

MODULE = "plugins.modules.purefb_tz"
MEMBER = "fb-member-01"
CURRENT_TZ = "America/Los_Angeles"


def _module(timezone=CURRENT_TZ, context="", check_mode=False):
    module = Mock()
    module.params = {"timezone": timezone, "context": context}
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _blade(current_tz=CURRENT_TZ, get_status=200, patch_status=200):
    blade = Mock()
    array = Mock()
    array.time_zone = current_tz
    get_res = Mock()
    get_res.status_code = get_status
    get_res.items = [array]
    blade.get_arrays.return_value = get_res
    patch_res = Mock()
    patch_res.status_code = patch_status
    blade.patch_arrays.return_value = patch_res
    return blade


def _run(func, *args):
    try:
        func(*args)
    except SystemExit:
        pass


@patch(MODULE + ".LooseVersion", RealLooseVersion)
class TestContextKwargs:
    """_context_kwargs adds context_names only when set and the gate is met"""

    def test_empty_without_context(self):
        module = Mock()
        module.params = {"context": ""}
        assert _context_kwargs(module, "2.30", PATCH_CONTEXT_API_VERSION) == {}

    def test_patch_gate_met(self):
        module = Mock()
        module.params = {"context": MEMBER}
        assert _context_kwargs(module, "2.30", PATCH_CONTEXT_API_VERSION) == {
            "context_names": [MEMBER]
        }

    def test_patch_gate_not_met(self):
        module = Mock()
        module.params = {"context": MEMBER}
        assert _context_kwargs(module, "2.29", PATCH_CONTEXT_API_VERSION) == {}

    def test_get_gate_met(self):
        module = Mock()
        module.params = {"context": MEMBER}
        assert _context_kwargs(module, "2.22", GET_CONTEXT_API_VERSION) == {
            "context_names": [MEMBER]
        }

    def test_get_gate_not_met(self):
        module = Mock()
        module.params = {"context": MEMBER}
        assert _context_kwargs(module, "2.21", GET_CONTEXT_API_VERSION) == {}


@patch(MODULE + ".LooseVersion", RealLooseVersion)
@patch(MODULE + ".flashblade")
class TestSetTimezone:
    """set_timezone builds the PATCH with or without context"""

    def test_set_without_context(self, mock_fb):
        module = _module(timezone="UTC")
        blade = _blade()

        _run(set_timezone, module, blade, "2.30")

        mock_fb.Array.assert_called_once_with(time_zone="UTC")
        blade.patch_arrays.assert_called_once_with(mock_fb.Array.return_value)
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()

    def test_set_with_context(self, mock_fb):
        module = _module(timezone="UTC", context=MEMBER)
        blade = _blade()

        _run(set_timezone, module, blade, "2.30")

        mock_fb.Array.assert_called_once_with(time_zone="UTC")
        blade.patch_arrays.assert_called_once_with(
            mock_fb.Array.return_value, context_names=[MEMBER]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_check_mode_does_not_patch(self, mock_fb):
        module = _module(timezone="UTC", context=MEMBER, check_mode=True)
        blade = _blade()

        _run(set_timezone, module, blade, "2.30")

        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_api_error_fails(self, mock_fb):
        module = _module(timezone="UTC")
        blade = _blade(patch_status=400)

        _run(set_timezone, module, blade, "2.30")

        module.fail_json.assert_called_once()
        assert "Failed to set timezone" in module.fail_json.call_args[1]["msg"]
        module.exit_json.assert_not_called()


@patch(MODULE + ".LooseVersion", RealLooseVersion)
@patch(MODULE + ".flashblade")
@patch(MODULE + ".get_rest_api_version")
@patch(MODULE + ".get_system")
@patch(MODULE + ".AnsibleModule")
@patch(MODULE + ".HAS_PYTZ", True)
@patch(MODULE + ".HAS_PYPURECLIENT", True)
class TestMain:
    """main wires the context into both calls and gates it"""

    def test_unchanged_without_context(
        self, mock_ansible_module, mock_get_system, mock_version, mock_fb
    ):
        module = _module()
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade
        mock_version.return_value = "2.30"

        _run(main)

        blade.get_arrays.assert_called_once_with()
        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_unchanged_with_context(
        self, mock_ansible_module, mock_get_system, mock_version, mock_fb
    ):
        module = _module(context=MEMBER)
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade
        mock_version.return_value = "2.30"

        _run(main)

        blade.get_arrays.assert_called_once_with(context_names=[MEMBER])
        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_change_with_context(
        self, mock_ansible_module, mock_get_system, mock_version, mock_fb
    ):
        module = _module(timezone="UTC", context=MEMBER)
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade
        mock_version.return_value = "2.30"

        _run(main)

        blade.get_arrays.assert_called_once_with(context_names=[MEMBER])
        mock_fb.Array.assert_called_once_with(time_zone="UTC")
        blade.patch_arrays.assert_called_once_with(
            mock_fb.Array.return_value, context_names=[MEMBER]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_change_without_context_on_old_array(
        self, mock_ansible_module, mock_get_system, mock_version, mock_fb
    ):
        module = _module(timezone="UTC")
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade
        mock_version.return_value = "2.21"

        _run(main)

        blade.get_arrays.assert_called_once_with()
        blade.patch_arrays.assert_called_once_with(mock_fb.Array.return_value)
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()

    def test_context_below_patch_gate_fails_before_any_call(
        self, mock_ansible_module, mock_get_system, mock_version, mock_fb
    ):
        module = _module(timezone="UTC", context=MEMBER)
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade
        mock_version.return_value = "2.29"

        _run(main)

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "context requires FlashBlade REST version 2.30" in msg
        assert "2.29" in msg
        blade.get_arrays.assert_not_called()
        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_not_called()

    def test_context_at_get_gate_only_still_fails(
        self, mock_ansible_module, mock_get_system, mock_version, mock_fb
    ):
        """A 2.22 array can read with context but cannot write with it"""
        module = _module(context=MEMBER, check_mode=True)
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade
        mock_version.return_value = "2.22"

        _run(main)

        module.fail_json.assert_called_once()
        blade.get_arrays.assert_not_called()
        blade.patch_arrays.assert_not_called()

    def test_get_arrays_error_fails(
        self, mock_ansible_module, mock_get_system, mock_version, mock_fb
    ):
        module = _module(context="not-a-member")
        mock_ansible_module.return_value = module
        blade = _blade(get_status=400)
        mock_get_system.return_value = blade
        mock_version.return_value = "2.30"

        _run(main)

        module.fail_json.assert_called_once()
        assert "Failed to get array settings" in module.fail_json.call_args[1]["msg"]
        blade.patch_arrays.assert_not_called()

    def test_check_mode_change_with_context(
        self, mock_ansible_module, mock_get_system, mock_version, mock_fb
    ):
        module = _module(timezone="UTC", context=MEMBER, check_mode=True)
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade
        mock_version.return_value = "2.30"

        _run(main)

        blade.get_arrays.assert_called_once_with(context_names=[MEMBER])
        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".pytz", create=True)
    @patch(MODULE + "._get_local_tz")
    def test_local_timezone_fallback(
        self,
        mock_local_tz,
        mock_pytz,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_fb,
    ):
        module = _module(timezone=None)
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade
        mock_version.return_value = "2.30"
        mock_local_tz.return_value = "Europe/London"
        mock_pytz.all_timezones_set = {"Europe/London", "UTC"}

        _run(main)

        mock_local_tz.assert_called_once_with(module)
        mock_fb.Array.assert_called_once_with(time_zone="Europe/London")
        blade.patch_arrays.assert_called_once_with(mock_fb.Array.return_value)
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".pytz", create=True)
    @patch(MODULE + "._get_local_tz")
    def test_invalid_local_timezone_fails(
        self,
        mock_local_tz,
        mock_pytz,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_fb,
    ):
        module = _module(timezone=None)
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade
        mock_version.return_value = "2.30"
        mock_local_tz.return_value = "Nowhere/Land"
        mock_pytz.all_timezones_set = {"UTC"}

        _run(main)

        module.fail_json.assert_called_once()
        assert "is not valid" in module.fail_json.call_args[1]["msg"]
        blade.get_arrays.assert_not_called()
        blade.patch_arrays.assert_not_called()


class TestMainDependencies:
    """main fails before contacting the array when a dependency is missing"""

    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYTZ", True)
    @patch(MODULE + ".HAS_PYPURECLIENT", False)
    def test_missing_sdk(self, mock_ansible_module, mock_get_system):
        module = _module()
        mock_ansible_module.return_value = module

        _run(main)

        module.fail_json.assert_called_once()
        assert "py-pure-client sdk is required" in module.fail_json.call_args[1]["msg"]
        mock_get_system.assert_not_called()

    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYTZ", False)
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_missing_pytz(self, mock_ansible_module, mock_get_system):
        module = _module()
        mock_ansible_module.return_value = module

        _run(main)

        module.fail_json.assert_called_once()
        assert "pytz is required" in module.fail_json.call_args[1]["msg"]
        mock_get_system.assert_not_called()
