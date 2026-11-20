# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_phonehome module."""

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

from plugins.modules.purefb_phonehome import (
    main,
    _check_edge_support,
    _edge_options_set,
    _pending_changes,
    update_support,
    EDGE_API_VERSION,
)
from plugins.module_utils.version import LooseVersion as RealLooseVersion
from plugins.module_utils.common import get_error_message as real_get_error_message
from plugins.modules import purefb_phonehome

MODULE = "plugins.modules.purefb_phonehome"


REFUSAL = "Operation not permitted."
READ_REFUSED = "Failed to read the support settings. Error: " + REFUSAL
TEST_REFUSED = "Phone Home test failed. Error: " + REFUSAL


def _error_response(status_code=400, message=REFUSAL):
    """The SDK answer to a refused or failed call: a status and errors, no items"""
    res = Mock(spec=["status_code", "errors", "headers"])
    res.status_code = status_code
    res.errors = []
    if message:
        error = Mock(spec=["context", "message", "location_context"])
        error.message = message
        res.errors.append(error)
    return res


@pytest.fixture
def real_error_message():
    """Use the get_error_message of the collection instead of its mock"""
    with patch(MODULE + ".get_error_message", real_get_error_message):
        yield


def _base_params(**overrides):
    params = {
        "state": "present",
        "edge_management": None,
        "edge_agent_update": None,
    }
    params.update(overrides)
    return params


def _module(check_mode=False, **overrides):
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.params = _base_params(**overrides)
    module.check_mode = check_mode
    return module


def _support(phonehome=True, edge_management=False, edge_agent_update=False):
    support = Mock()
    support.phonehome_enabled = phonehome
    support.edge_management_enabled = edge_management
    support.edge_agent_update_enabled = edge_agent_update
    return support


def _blade(support=None, patch_status=200):
    blade = Mock()
    blade.get_support.return_value.status_code = 200
    blade.get_support.return_value.items = [support or _support()]
    blade.patch_support.return_value.status_code = patch_status
    return blade


def _run_main():
    try:
        main()
    except SystemExit:
        pass


class TestPurefbPhonehomeHelpers:
    """Helper-function unit tests"""

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    def test_check_edge_support_fails_below_2_18_when_option_set(self):
        module = _module(edge_management=True)
        try:
            _check_edge_support(module, "2.17")
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert EDGE_API_VERSION in msg
        assert "2.17" in msg

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    def test_check_edge_support_fails_for_agent_update_only(self):
        module = _module(edge_agent_update=False)
        try:
            _check_edge_support(module, "2.17")
        except SystemExit:
            pass
        module.fail_json.assert_called_once()

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    def test_check_edge_support_passes_below_2_18_without_options(self):
        module = _module()
        _check_edge_support(module, "2.17")
        module.fail_json.assert_not_called()

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    def test_check_edge_support_passes_at_2_18_and_later(self):
        for version in ("2.18", "2.21", "2.30"):
            module = _module(edge_management=True, edge_agent_update=True)
            _check_edge_support(module, version)
            module.fail_json.assert_not_called()

    def test_edge_options_set_none_supplied(self):
        assert _edge_options_set(_module()) is False

    def test_edge_options_set_false_counts_as_supplied(self):
        assert _edge_options_set(_module(edge_agent_update=False)) is True
        assert _edge_options_set(_module(edge_management=True)) is True

    def test_pending_changes_present_enables_phonehome(self):
        module = _module()
        assert _pending_changes(module, _support(phonehome=False)) == {
            "phonehome_enabled": True
        }

    def test_pending_changes_present_is_idempotent(self):
        module = _module()
        assert _pending_changes(module, _support(phonehome=True)) == {}

    def test_pending_changes_absent_disables_phonehome(self):
        module = _module(state="absent")
        assert _pending_changes(module, _support(phonehome=True)) == {
            "phonehome_enabled": False
        }

    def test_pending_changes_absent_is_idempotent(self):
        module = _module(state="absent")
        assert _pending_changes(module, _support(phonehome=False)) == {}

    def test_pending_changes_edge_flags_only_when_supplied(self):
        module = _module(edge_management=True)
        support = _support(edge_management=False, edge_agent_update=False)
        assert _pending_changes(module, support) == {"edge_management_enabled": True}

    def test_pending_changes_edge_flags_idempotent(self):
        module = _module(edge_management=True, edge_agent_update=False)
        support = _support(edge_management=True, edge_agent_update=False)
        assert _pending_changes(module, support) == {}

    def test_pending_changes_combines_phonehome_and_edge(self):
        module = _module(edge_management=True, edge_agent_update=True)
        support = _support(phonehome=False)
        assert _pending_changes(module, support) == {
            "phonehome_enabled": True,
            "edge_management_enabled": True,
            "edge_agent_update_enabled": True,
        }

    def test_pending_changes_absent_leaves_edge_untouched(self):
        module = _module(state="absent")
        support = _support(phonehome=True, edge_management=True)
        assert _pending_changes(module, support) == {"phonehome_enabled": False}

    def test_pending_changes_edge_disable(self):
        module = _module(edge_management=False)
        support = _support(edge_management=True)
        assert _pending_changes(module, support) == {"edge_management_enabled": False}

    def test_pending_changes_missing_edge_fields_read_as_none(self):
        """A pre-2.18 Support object has no edge attributes at all"""
        module = _module(edge_management=False)
        support = Mock(spec=["phonehome_enabled"])
        support.phonehome_enabled = True
        assert _pending_changes(module, support) == {"edge_management_enabled": False}

    @patch(MODULE + ".Support")
    def test_update_support_single_patch(self, mock_support_cls):
        module = _module()
        blade = _blade()
        changes = {"phonehome_enabled": True, "edge_management_enabled": True}
        try:
            update_support(module, blade, changes)
        except SystemExit:
            pass
        mock_support_cls.assert_called_once_with(**changes)
        blade.patch_support.assert_called_once_with(
            support=mock_support_cls.return_value
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".Support")
    def test_update_support_check_mode(self, mock_support_cls):
        module = _module(check_mode=True)
        blade = _blade()
        try:
            update_support(module, blade, {"edge_management_enabled": True})
        except SystemExit:
            pass
        blade.patch_support.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".get_error_message", return_value="boom")
    @patch(MODULE + ".Support")
    def test_update_support_api_error(self, mock_support_cls, mock_err):
        module = _module()
        blade = _blade(patch_status=400)
        try:
            update_support(module, blade, {"edge_management_enabled": True})
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "edge_management_enabled" in msg
        assert "Error: boom" in msg
        module.exit_json.assert_not_called()


class TestPurefbPhonehomeMain:
    """main() flows"""

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".Support")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_enables_phonehome(
        self, mock_ansible_module, mock_get_system, mock_support_cls, mock_ver
    ):
        module = _module()
        mock_ansible_module.return_value = module
        blade = _blade(_support(phonehome=False))
        mock_get_system.return_value = blade

        _run_main()

        mock_support_cls.assert_called_once_with(phonehome_enabled=True)
        blade.patch_support.assert_called_once_with(
            support=mock_support_cls.return_value
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".Support")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_present_idempotent(
        self, mock_ansible_module, mock_get_system, mock_support_cls, mock_ver
    ):
        module = _module()
        mock_ansible_module.return_value = module
        blade = _blade(_support(phonehome=True))
        mock_get_system.return_value = blade

        _run_main()

        blade.patch_support.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".Support")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_disables_phonehome(
        self, mock_ansible_module, mock_get_system, mock_support_cls, mock_ver
    ):
        module = _module(state="absent")
        mock_ansible_module.return_value = module
        blade = _blade(_support(phonehome=True, edge_management=True))
        mock_get_system.return_value = blade

        _run_main()

        mock_support_cls.assert_called_once_with(phonehome_enabled=False)
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".Support")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_edge_and_phonehome_in_one_patch(
        self, mock_ansible_module, mock_get_system, mock_support_cls, mock_ver
    ):
        module = _module(edge_management=True, edge_agent_update=True)
        mock_ansible_module.return_value = module
        blade = _blade(_support(phonehome=False))
        mock_get_system.return_value = blade

        _run_main()

        mock_support_cls.assert_called_once_with(
            phonehome_enabled=True,
            edge_management_enabled=True,
            edge_agent_update_enabled=True,
        )
        blade.patch_support.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".Support")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_edge_only_change(
        self, mock_ansible_module, mock_get_system, mock_support_cls, mock_ver
    ):
        module = _module(edge_management=True)
        mock_ansible_module.return_value = module
        blade = _blade(_support(phonehome=True, edge_management=False))
        mock_get_system.return_value = blade

        _run_main()

        mock_support_cls.assert_called_once_with(edge_management_enabled=True)
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".Support")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_edge_idempotent(
        self, mock_ansible_module, mock_get_system, mock_support_cls, mock_ver
    ):
        module = _module(edge_management=True, edge_agent_update=False)
        mock_ansible_module.return_value = module
        blade = _blade(_support(edge_management=True, edge_agent_update=False))
        mock_get_system.return_value = blade

        _run_main()

        blade.patch_support.assert_not_called()
        mock_support_cls.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".Support")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_check_mode(
        self, mock_ansible_module, mock_get_system, mock_support_cls, mock_ver
    ):
        module = _module(check_mode=True, edge_management=True)
        mock_ansible_module.return_value = module
        blade = _blade(_support(edge_management=False))
        mock_get_system.return_value = blade

        _run_main()

        blade.patch_support.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.17")
    @patch(MODULE + ".Support")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_edge_version_gate_fails_before_any_read_or_write(
        self, mock_ansible_module, mock_get_system, mock_support_cls, mock_ver
    ):
        module = _module(edge_management=True)
        mock_ansible_module.return_value = module
        blade = _blade(_support(phonehome=False))
        mock_get_system.return_value = blade

        _run_main()

        module.fail_json.assert_called_once()
        assert "2.18" in module.fail_json.call_args[1]["msg"]
        blade.get_support.assert_not_called()
        blade.patch_support.assert_not_called()
        module.exit_json.assert_not_called()

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.17")
    @patch(MODULE + ".Support")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_old_api_without_edge_options_still_works(
        self, mock_ansible_module, mock_get_system, mock_support_cls, mock_ver
    ):
        module = _module()
        mock_ansible_module.return_value = module
        support = Mock(spec=["phonehome_enabled"])
        support.phonehome_enabled = False
        blade = _blade(support)
        mock_get_system.return_value = blade

        _run_main()

        module.fail_json.assert_not_called()
        mock_support_cls.assert_called_once_with(phonehome_enabled=True)
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".get_error_message", return_value="boom")
    @patch(MODULE + ".Support")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_patch_error(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_support_cls,
        mock_err,
        mock_ver,
    ):
        module = _module(edge_management=True)
        mock_ansible_module.return_value = module
        blade = _blade(_support(edge_management=False), patch_status=400)
        mock_get_system.return_value = blade

        _run_main()

        module.fail_json.assert_called_once()
        assert "Error: boom" in module.fail_json.call_args[1]["msg"]
        module.exit_json.assert_not_called()

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".Support")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_state_test(
        self, mock_ansible_module, mock_get_system, mock_support_cls, mock_ver
    ):
        module = _module(state="test")
        mock_ansible_module.return_value = module
        blade = _blade()
        component = Mock()
        component.enabled = True
        component.success = False
        component.component_address = "10.0.0.1"
        component.component_name = "FM1"
        component.description = "Phone Home"
        component.destination = "phonehome.example"
        component.result_details = "timeout"
        component.test_type = "phonehome"
        blade.get_support_test.return_value.status_code = 200
        blade.get_support_test.return_value.items = [component]
        mock_get_system.return_value = blade

        _run_main()

        blade.get_support_test.assert_called_once_with(test_type="phonehome")
        blade.get_support.assert_not_called()
        blade.patch_support.assert_not_called()
        module.exit_json.assert_called_once()
        kwargs = module.exit_json.call_args[1]
        assert kwargs["changed"] is False
        assert kwargs["test_response"] == [
            {
                "component_address": "10.0.0.1",
                "component_name": "FM1",
                "description": "Phone Home",
                "destination": "phonehome.example",
                "enabled": "true",
                "result_details": "timeout",
                "success": "false",
                "test_type": "phonehome",
            }
        ]

    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_state_test_rejects_edge_options(
        self, mock_ansible_module, mock_get_system, mock_ver
    ):
        module = _module(state="test", edge_management=True)
        mock_ansible_module.return_value = module

        _run_main()

        module.fail_json.assert_called_once()
        assert "state=test" in module.fail_json.call_args[1]["msg"]
        mock_get_system.assert_not_called()
        module.exit_json.assert_not_called()

    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", False)
    def test_main_fails_without_sdk(self, mock_ansible_module, mock_get_system):
        module = _module()
        mock_ansible_module.return_value = module

        _run_main()

        module.fail_json.assert_called_once()
        assert "py-pure-client" in module.fail_json.call_args[1]["msg"]
        mock_get_system.assert_not_called()


@pytest.mark.usefixtures("real_error_message")
class TestPurefbPhonehomeRefusedReads:
    """A read the array refuses or fails is reported with its message"""

    def test_get_support_returns_the_settings(self):
        module = _module()
        support = _support(phonehome=False)
        blade = _blade(support)

        assert purefb_phonehome._get_support(module, blade) is support
        module.fail_json.assert_not_called()

    def test_get_support_refused(self):
        """An administrator limited to a realm may not read the support settings"""
        module = _module()
        blade = _blade()
        blade.get_support.return_value = _error_response()

        with pytest.raises(SystemExit):
            purefb_phonehome._get_support(module, blade)

        module.fail_json.assert_called_once_with(msg=READ_REFUSED)

    def test_get_support_failed_without_a_message(self):
        """An error answer that carries no message"""
        module = _module()
        blade = _blade()
        blade.get_support.return_value = _error_response(503, None)

        with pytest.raises(SystemExit):
            purefb_phonehome._get_support(module, blade)

        module.fail_json.assert_called_once_with(
            msg="Failed to read the support settings. Error: Unknown error"
        )

    def test_get_support_without_items(self):
        module = _module()
        blade = _blade()
        blade.get_support.return_value.items = []

        with pytest.raises(SystemExit):
            purefb_phonehome._get_support(module, blade)

        module.fail_json.assert_called_once_with(
            msg="The array returned no support settings."
        )

    def test_test_ph_refused(self):
        module = _module(state="test")
        blade = _blade()
        blade.get_support_test.return_value = _error_response()

        with pytest.raises(SystemExit):
            purefb_phonehome.test_ph(module, blade)

        blade.get_support_test.assert_called_once_with(test_type="phonehome")
        module.fail_json.assert_called_once_with(msg=TEST_REFUSED)
        module.exit_json.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize(
        "params",
        [
            {"state": "present"},
            {"state": "absent"},
            {"state": "present", "edge_management": True, "edge_agent_update": False},
        ],
        ids=["present", "absent", "edge_options"],
    )
    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".Support")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_refused_read(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_support_cls,
        mock_ver,
        params,
        check_mode,
    ):
        module = _module(check_mode=check_mode, **params)
        mock_ansible_module.return_value = module
        blade = _blade()
        blade.get_support.return_value = _error_response()
        mock_get_system.return_value = blade

        _run_main()

        module.fail_json.assert_called_once_with(msg=READ_REFUSED)
        mock_support_cls.assert_not_called()
        blade.patch_support.assert_not_called()
        module.exit_json.assert_not_called()

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".Support")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_read_without_items(
        self, mock_ansible_module, mock_get_system, mock_support_cls, mock_ver
    ):
        module = _module()
        mock_ansible_module.return_value = module
        blade = _blade()
        blade.get_support.return_value.items = []
        mock_get_system.return_value = blade

        _run_main()

        module.fail_json.assert_called_once_with(
            msg="The array returned no support settings."
        )
        blade.patch_support.assert_not_called()
        module.exit_json.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE + ".Support")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_main_state_test_refused(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_support_cls,
        mock_ver,
        check_mode,
    ):
        module = _module(check_mode=check_mode, state="test")
        mock_ansible_module.return_value = module
        blade = _blade()
        blade.get_support_test.return_value = _error_response()
        mock_get_system.return_value = blade

        _run_main()

        blade.get_support_test.assert_called_once_with(test_type="phonehome")
        module.fail_json.assert_called_once_with(msg=TEST_REFUSED)
        blade.get_support.assert_not_called()
        blade.patch_support.assert_not_called()
        module.exit_json.assert_not_called()
