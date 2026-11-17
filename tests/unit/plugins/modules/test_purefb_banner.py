# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_banner module."""

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

from plugins.modules.purefb_banner import (
    main,
    set_banner,
    delete_banner,
    _context_kwargs,
    CONTEXT_GET_API_VERSION,
    CONTEXT_PATCH_API_VERSION,
)

# The collection's own LooseVersion; module_utils.version is mocked above so
# the module sees a MagicMock unless the tests patch the real class back in.
from plugins.module_utils.version import LooseVersion as RealLooseVersion

MODULE = "plugins.modules.purefb_banner"
CONTEXT = "fb-member-01"


def _base_params(**overrides):
    params = {"banner": "Welcome to the machine...", "state": "present", "context": ""}
    params.update(overrides)
    return params


def _module(**overrides):
    module = Mock()
    module.params = _base_params(**overrides)
    module.check_mode = False
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _blade(current_banner, get_status=200, patch_status=200, items=None):
    blade = Mock()
    if items is None:
        item = Mock()
        item.banner = current_banner
        items = [item]
    get_response = Mock()
    get_response.status_code = get_status
    get_response.items = items
    blade.get_arrays.return_value = get_response
    patch_response = Mock()
    patch_response.status_code = patch_status
    blade.patch_arrays.return_value = patch_response
    return blade


def _run_main():
    try:
        main()
    except SystemExit:
        pass


class TestPurefbBanner:
    """Test cases for purefb_banner module"""

    # ---------------- _context_kwargs ----------------

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    def test_context_kwargs_empty_without_context(self):
        """No context -> nothing is added, whatever the REST version"""
        module = Mock()
        module.params = {"context": ""}
        assert _context_kwargs(module, "2.30", CONTEXT_GET_API_VERSION) == {}
        assert _context_kwargs(module, "2.30", CONTEXT_PATCH_API_VERSION) == {}

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    def test_context_kwargs_get_arrays_gate(self):
        """get_arrays accepts context_names from REST 2.22"""
        module = Mock()
        module.params = {"context": CONTEXT}
        assert _context_kwargs(module, "2.21", CONTEXT_GET_API_VERSION) == {}
        assert _context_kwargs(module, "2.22", CONTEXT_GET_API_VERSION) == {
            "context_names": [CONTEXT]
        }
        assert _context_kwargs(module, "2.30", CONTEXT_GET_API_VERSION) == {
            "context_names": [CONTEXT]
        }

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    def test_context_kwargs_patch_arrays_gate(self):
        """patch_arrays accepts context_names from REST 2.30 only"""
        module = Mock()
        module.params = {"context": CONTEXT}
        assert _context_kwargs(module, "2.22", CONTEXT_PATCH_API_VERSION) == {}
        assert _context_kwargs(module, "2.29", CONTEXT_PATCH_API_VERSION) == {}
        assert _context_kwargs(module, "2.30", CONTEXT_PATCH_API_VERSION) == {
            "context_names": [CONTEXT]
        }

    # ---------------- set_banner / delete_banner ----------------

    @patch(MODULE + ".Array")
    def test_set_banner_without_context(self, mock_array_class):
        """set_banner sends the banner with no context kwarg"""
        module = _module(banner="new text")
        blade = _blade("old")

        try:
            set_banner(module, blade, {})
        except SystemExit:
            pass

        mock_array_class.assert_called_once_with(banner="new text")
        blade.patch_arrays.assert_called_once_with(array=mock_array_class.return_value)
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".Array")
    def test_set_banner_with_context(self, mock_array_class):
        """set_banner forwards context_names to patch_arrays"""
        module = _module(banner="new text", context=CONTEXT)
        blade = _blade("old")

        try:
            set_banner(module, blade, {"context_names": [CONTEXT]})
        except SystemExit:
            pass

        blade.patch_arrays.assert_called_once_with(
            array=mock_array_class.return_value, context_names=[CONTEXT]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_set_banner_check_mode(self):
        """set_banner writes nothing in check mode but reports a change"""
        module = _module(banner="new text", context=CONTEXT)
        module.check_mode = True
        blade = _blade("old")

        try:
            set_banner(module, blade, {"context_names": [CONTEXT]})
        except SystemExit:
            pass

        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_set_banner_empty_text_fails(self):
        """set_banner refuses an empty banner"""
        module = _module(banner="")
        blade = _blade("old")

        try:
            set_banner(module, blade, {})
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "Invalid MOTD banner given" in module.fail_json.call_args[1]["msg"]
        blade.patch_arrays.assert_not_called()

    def test_set_banner_api_error(self):
        """set_banner surfaces a PATCH error"""
        module = _module(banner="new text")
        blade = _blade("old", patch_status=400)

        try:
            set_banner(module, blade, {})
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "Failed to set MOTD banner text" in module.fail_json.call_args[1]["msg"]

    @patch(MODULE + ".Array")
    def test_delete_banner_with_context(self, mock_array_class):
        """delete_banner clears the banner and forwards context_names"""
        module = _module(state="absent", context=CONTEXT)
        blade = _blade("old")

        try:
            delete_banner(module, blade, {"context_names": [CONTEXT]})
        except SystemExit:
            pass

        mock_array_class.assert_called_once_with(banner="")
        blade.patch_arrays.assert_called_once_with(
            array=mock_array_class.return_value, context_names=[CONTEXT]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_delete_banner_check_mode(self):
        """delete_banner writes nothing in check mode"""
        module = _module(state="absent")
        module.check_mode = True
        blade = _blade("old")

        try:
            delete_banner(module, blade, {})
        except SystemExit:
            pass

        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_delete_banner_api_error(self):
        """delete_banner surfaces a PATCH error"""
        module = _module(state="absent")
        blade = _blade("old", patch_status=400)

        try:
            delete_banner(module, blade, {})
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert (
            "Failed to delete current MOTD banner text"
            in module.fail_json.call_args[1]["msg"]
        )

    # ---------------- main() flows ----------------

    @patch(MODULE + ".Array")
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_set_without_context(
        self, mock_ansible_module, mock_get_system, mock_version, mock_array_class
    ):
        """Without context neither GET nor PATCH carries context_names"""
        module = _module(banner="new text")
        mock_ansible_module.return_value = module
        blade = _blade("old")
        mock_get_system.return_value = blade

        _run_main()

        blade.get_arrays.assert_called_once_with()
        mock_array_class.assert_called_once_with(banner="new text")
        blade.patch_arrays.assert_called_once_with(array=mock_array_class.return_value)
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".Array")
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_set_with_context(
        self, mock_ansible_module, mock_get_system, mock_version, mock_array_class
    ):
        """At REST 2.30 both GET and PATCH carry context_names"""
        module = _module(banner="new text", context=CONTEXT)
        mock_ansible_module.return_value = module
        blade = _blade("old")
        mock_get_system.return_value = blade

        _run_main()

        blade.get_arrays.assert_called_once_with(context_names=[CONTEXT])
        mock_array_class.assert_called_once_with(banner="new text")
        blade.patch_arrays.assert_called_once_with(
            array=mock_array_class.return_value, context_names=[CONTEXT]
        )
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_noop_with_context(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """Banner already set: read with context, no PATCH, changed=False"""
        module = _module(banner="same text", context=CONTEXT)
        mock_ansible_module.return_value = module
        blade = _blade("same text")
        mock_get_system.return_value = blade

        _run_main()

        blade.get_arrays.assert_called_once_with(context_names=[CONTEXT])
        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_noop_without_context(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """Banner already set without context: no PATCH, changed=False"""
        module = _module(banner="same text")
        mock_ansible_module.return_value = module
        blade = _blade("same text")
        mock_get_system.return_value = blade

        _run_main()

        blade.get_arrays.assert_called_once_with()
        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".Array")
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_delete_with_context(
        self, mock_ansible_module, mock_get_system, mock_version, mock_array_class
    ):
        """state=absent clears the banner through the context"""
        module = _module(state="absent", context=CONTEXT)
        mock_ansible_module.return_value = module
        blade = _blade("old")
        mock_get_system.return_value = blade

        _run_main()

        blade.get_arrays.assert_called_once_with(context_names=[CONTEXT])
        mock_array_class.assert_called_once_with(banner="")
        blade.patch_arrays.assert_called_once_with(
            array=mock_array_class.return_value, context_names=[CONTEXT]
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_delete_noop_with_context(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """state=absent on an empty banner is a no-op"""
        module = _module(state="absent", context=CONTEXT)
        mock_ansible_module.return_value = module
        blade = _blade("")
        mock_get_system.return_value = blade

        _run_main()

        blade.get_arrays.assert_called_once_with(context_names=[CONTEXT])
        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_check_mode_with_context(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """Check mode reads with context and never PATCHes"""
        module = _module(banner="new text", context=CONTEXT)
        module.check_mode = True
        mock_ansible_module.return_value = module
        blade = _blade("old")
        mock_get_system.return_value = blade

        _run_main()

        blade.get_arrays.assert_called_once_with(context_names=[CONTEXT])
        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.29")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_context_below_gate_fails_before_any_call(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """context on REST < 2.30 fails clearly before GET or PATCH"""
        module = _module(banner="new text", context=CONTEXT)
        mock_ansible_module.return_value = module
        blade = _blade("old")
        mock_get_system.return_value = blade

        _run_main()

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "context" in msg
        assert "2.30" in msg
        assert "2.29" in msg
        blade.get_arrays.assert_not_called()
        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_not_called()

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.29")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_context_below_gate_fails_in_check_mode(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """The gate applies in check mode too"""
        module = _module(banner="new text", context=CONTEXT)
        module.check_mode = True
        mock_ansible_module.return_value = module
        blade = _blade("old")
        mock_get_system.return_value = blade

        _run_main()

        module.fail_json.assert_called_once()
        blade.get_arrays.assert_not_called()
        blade.patch_arrays.assert_not_called()

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".Array")
    @patch(MODULE + ".get_rest_api_version", return_value="2.29")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_without_context_below_gate_still_works(
        self, mock_ansible_module, mock_get_system, mock_version, mock_array_class
    ):
        """Older arrays keep working when no context is given"""
        module = _module(banner="new text")
        mock_ansible_module.return_value = module
        blade = _blade("old")
        mock_get_system.return_value = blade

        _run_main()

        blade.get_arrays.assert_called_once_with()
        blade.patch_arrays.assert_called_once_with(array=mock_array_class.return_value)
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_get_arrays_error(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """A failed GET (for example an unknown context) is a clean failure"""
        module = _module(banner="new text", context=CONTEXT)
        mock_ansible_module.return_value = module
        blade = _blade("old", get_status=400)
        mock_get_system.return_value = blade

        _run_main()

        module.fail_json.assert_called_once()
        assert (
            "Failed to get current MOTD banner text"
            in module.fail_json.call_args[1]["msg"]
        )
        blade.patch_arrays.assert_not_called()

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_get_arrays_no_items(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """A 200 that carries no array fails cleanly instead of IndexError"""
        module = _module(banner="new text", context=CONTEXT)
        mock_ansible_module.return_value = module
        blade = _blade("old", items=[])
        mock_get_system.return_value = blade

        _run_main()

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to get current MOTD banner text" in msg
        assert "No array returned" in msg
        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_not_called()

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_context_fleet_name_refused(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """A context resolving to several arrays (the fleet name) is refused.

        The first member already carries the wanted banner, so the old
        unchecked [0] read would have reported changed=False for the fleet.
        """
        module = _module(banner="new text", context=CONTEXT)
        mock_ansible_module.return_value = module
        first = Mock()
        first.banner = "new text"
        second = Mock()
        second.banner = "other"
        blade = _blade("old", items=[first, second])
        mock_get_system.return_value = blade

        _run_main()

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert CONTEXT in msg
        assert "2 arrays" in msg
        assert "single fleet member" in msg
        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_not_called()

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_context_fleet_name_refused_in_check_mode(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """The item-count guard applies to state=absent in check mode too"""
        module = _module(state="absent", context=CONTEXT)
        module.check_mode = True
        mock_ansible_module.return_value = module
        first = Mock()
        first.banner = ""
        second = Mock()
        second.banner = "other"
        blade = _blade("old", items=[first, second])
        mock_get_system.return_value = blade

        _run_main()

        module.fail_json.assert_called_once()
        assert "2 arrays" in module.fail_json.call_args[1]["msg"]
        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_not_called()

    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", False)
    def test_main_missing_sdk(self, mock_ansible_module, mock_get_system, mock_version):
        """Missing py-pure-client fails before any array access"""
        module = _module()
        mock_ansible_module.return_value = module

        _run_main()

        module.fail_json.assert_called_once()
        assert "py-pure-client sdk is required" in module.fail_json.call_args[1]["msg"]
        mock_get_system.assert_not_called()

    @patch(MODULE + ".purefb_argument_spec", return_value={})
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_argument_spec_has_context(
        self, mock_ansible_module, mock_get_system, mock_version, mock_spec
    ):
        """The context option is declared as an optional string defaulting to empty"""
        module = _module(banner="same text")
        mock_ansible_module.return_value = module
        mock_get_system.return_value = _blade("same text")

        _run_main()

        spec = mock_ansible_module.call_args[0][0]
        assert spec["context"] == {"type": "str", "default": ""}
