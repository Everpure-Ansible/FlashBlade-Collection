# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for the purefb_quota_settings module."""

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

from plugins.modules.purefb_quota_settings import (
    main,
    get_settings,
    update_settings,
    _wanted_changes,
)

MODULE_PATH = "plugins.modules.purefb_quota_settings"
CONTACT = "storage-admins@example.com"


def _params(**overrides):
    params = {
        "direct_notifications": None,
        "contact": None,
    }
    params.update(overrides)
    return params


def _module(**overrides):
    module = Mock()
    module.params = _params(**overrides)
    module.check_mode = False
    module.fail_json = Mock(side_effect=SystemExit)
    module.exit_json = Mock(side_effect=SystemExit)
    return module


def _settings(enabled=False, contact=None):
    """The settings singleton shaped like a GET result.

    The array omits the contact field entirely while it is unset, so the
    mock only carries the attribute when a contact is given.
    """
    spec = ["id", "name", "direct_notifications_enabled"]
    if contact is not None:
        spec.append("contact")
    obj = Mock(spec=spec)
    obj.name = "management"
    obj.direct_notifications_enabled = enabled
    if contact is not None:
        obj.contact = contact
    return obj


def _response(status_code=200, items=None):
    response = Mock()
    response.status_code = status_code
    response.items = items if items is not None else []
    return response


def _blade(settings=None, get_status=200, patch_status=200):
    blade = Mock()
    blade.get_quotas_settings.return_value = _response(
        get_status, items=[settings] if settings is not None else []
    )
    blade.patch_quotas_settings.return_value = _response(patch_status)
    return blade


class TestGetSettings:
    """get_settings must return the singleton and fail clearly otherwise."""

    def test_returns_the_single_object(self):
        settings = _settings()
        blade = _blade(settings)
        assert get_settings(_module(), blade) is settings
        blade.get_quotas_settings.assert_called_once_with()

    @patch(MODULE_PATH + ".get_error_message", return_value="boom")
    def test_fails_on_api_error(self, mock_error):
        module = _module()
        blade = _blade(get_status=400)
        try:
            get_settings(module, blade)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to read quota settings" in msg
        assert "boom" in msg

    def test_fails_when_nothing_is_returned(self):
        module = _module()
        try:
            get_settings(module, _blade())
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "No quota settings" in module.fail_json.call_args[1]["msg"]


class TestWantedChanges:
    """_wanted_changes must compare against the array with contact normalised."""

    def test_nothing_requested_is_empty(self):
        assert (
            _wanted_changes(_module(), _settings(enabled=True, contact=CONTACT)) == {}
        )

    def test_absent_contact_compares_as_empty_string(self):
        assert _wanted_changes(_module(contact=""), _settings()) == {}

    def test_absent_contact_differs_from_a_value(self):
        assert _wanted_changes(_module(contact=CONTACT), _settings()) == {
            "contact": CONTACT
        }

    def test_only_differing_fields_are_returned(self):
        module = _module(direct_notifications=True, contact=CONTACT)
        assert _wanted_changes(module, _settings(enabled=True)) == {"contact": CONTACT}
        assert _wanted_changes(module, _settings(contact=CONTACT)) == {
            "direct_notifications_enabled": True
        }

    def test_missing_enabled_field_is_treated_as_disabled(self):
        obj = Mock(spec=["id", "name"])
        obj.name = "management"
        assert _wanted_changes(_module(direct_notifications=False), obj) == {}
        assert _wanted_changes(_module(direct_notifications=True), obj) == {
            "direct_notifications_enabled": True
        }


class TestUpdateSettings:
    """update_settings must PATCH only what differs and report it."""

    @patch(MODULE_PATH + ".QuotaSetting")
    def test_enables_notifications(self, mock_model):
        module = _module(direct_notifications=True)
        blade = _blade()
        try:
            update_settings(module, blade, _settings(enabled=False))
        except SystemExit:
            pass
        mock_model.assert_called_once_with(direct_notifications_enabled=True)
        blade.patch_quotas_settings.assert_called_once_with(
            quota_setting=mock_model.return_value
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".QuotaSetting")
    def test_disables_notifications(self, mock_model):
        module = _module(direct_notifications=False)
        blade = _blade()
        try:
            update_settings(module, blade, _settings(enabled=True, contact=CONTACT))
        except SystemExit:
            pass
        mock_model.assert_called_once_with(direct_notifications_enabled=False)
        module.exit_json.assert_called_once_with(changed=True)

    def test_enable_is_idempotent(self):
        module = _module(direct_notifications=True)
        blade = _blade()
        try:
            update_settings(module, blade, _settings(enabled=True))
        except SystemExit:
            pass
        blade.patch_quotas_settings.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_disable_is_idempotent(self):
        module = _module(direct_notifications=False)
        blade = _blade()
        try:
            update_settings(module, blade, _settings(enabled=False))
        except SystemExit:
            pass
        blade.patch_quotas_settings.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE_PATH + ".QuotaSetting")
    def test_sets_contact_when_unset(self, mock_model):
        module = _module(contact=CONTACT)
        blade = _blade()
        try:
            update_settings(module, blade, _settings())
        except SystemExit:
            pass
        mock_model.assert_called_once_with(contact=CONTACT)
        blade.patch_quotas_settings.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".QuotaSetting")
    def test_changes_contact_when_different(self, mock_model):
        module = _module(contact="ops@example.com")
        blade = _blade()
        try:
            update_settings(module, blade, _settings(enabled=True, contact=CONTACT))
        except SystemExit:
            pass
        mock_model.assert_called_once_with(contact="ops@example.com")
        module.exit_json.assert_called_once_with(changed=True)

    def test_contact_is_idempotent(self):
        module = _module(contact=CONTACT)
        blade = _blade()
        try:
            update_settings(module, blade, _settings(contact=CONTACT))
        except SystemExit:
            pass
        blade.patch_quotas_settings.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE_PATH + ".QuotaSetting")
    def test_empty_string_clears_contact(self, mock_model):
        module = _module(contact="")
        blade = _blade()
        try:
            update_settings(module, blade, _settings(contact=CONTACT))
        except SystemExit:
            pass
        mock_model.assert_called_once_with(contact="")
        blade.patch_quotas_settings.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    def test_empty_string_is_idempotent_when_contact_is_absent(self):
        module = _module(contact="")
        blade = _blade()
        try:
            update_settings(module, blade, _settings())
        except SystemExit:
            pass
        blade.patch_quotas_settings.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE_PATH + ".QuotaSetting")
    def test_sets_both_fields_in_one_patch(self, mock_model):
        module = _module(direct_notifications=True, contact=CONTACT)
        blade = _blade()
        try:
            update_settings(module, blade, _settings())
        except SystemExit:
            pass
        mock_model.assert_called_once_with(
            direct_notifications_enabled=True, contact=CONTACT
        )
        blade.patch_quotas_settings.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".QuotaSetting")
    def test_both_requested_but_only_contact_differs(self, mock_model):
        module = _module(direct_notifications=True, contact=CONTACT)
        blade = _blade()
        try:
            update_settings(module, blade, _settings(enabled=True))
        except SystemExit:
            pass
        mock_model.assert_called_once_with(contact=CONTACT)
        module.exit_json.assert_called_once_with(changed=True)

    def test_both_requested_and_both_match_is_no_change(self):
        module = _module(direct_notifications=True, contact=CONTACT)
        blade = _blade()
        try:
            update_settings(module, blade, _settings(enabled=True, contact=CONTACT))
        except SystemExit:
            pass
        blade.patch_quotas_settings.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_check_mode_reports_change_without_patching(self):
        module = _module(direct_notifications=True, contact=CONTACT)
        module.check_mode = True
        blade = _blade()
        try:
            update_settings(module, blade, _settings())
        except SystemExit:
            pass
        blade.patch_quotas_settings.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_check_mode_no_change_stays_unchanged(self):
        module = _module(direct_notifications=False, contact="")
        module.check_mode = True
        blade = _blade()
        try:
            update_settings(module, blade, _settings())
        except SystemExit:
            pass
        blade.patch_quotas_settings.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE_PATH + ".get_error_message", return_value="boom")
    @patch(MODULE_PATH + ".QuotaSetting")
    def test_fails_when_patch_is_rejected(self, mock_model, mock_error):
        module = _module(contact=CONTACT)
        blade = _blade(patch_status=400)
        try:
            update_settings(module, blade, _settings())
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Updating quota settings management failed" in msg
        assert "boom" in msg
        module.exit_json.assert_not_called()


class TestMain:
    """main() wiring: SDK guard, contact length, version gate, argument spec."""

    @patch(MODULE_PATH + ".QuotaSetting")
    @patch(MODULE_PATH + ".LooseVersion")
    @patch(MODULE_PATH + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE_PATH + ".get_system")
    @patch(MODULE_PATH + ".AnsibleModule")
    @patch(MODULE_PATH + ".HAS_PYPURECLIENT", True)
    def test_sets_both_fields_end_to_end(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_loose_version,
        mock_model,
    ):
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(direct_notifications=True, contact=CONTACT)
        mock_ansible_module.return_value = module
        blade = _blade(_settings())
        mock_get_system.return_value = blade

        try:
            main()
        except SystemExit:
            pass

        assert mock_ansible_module.call_args[1]["required_one_of"] == [
            ["direct_notifications", "contact"]
        ]
        assert mock_ansible_module.call_args[1]["supports_check_mode"] is True
        mock_model.assert_called_once_with(
            direct_notifications_enabled=True, contact=CONTACT
        )
        blade.patch_quotas_settings.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".QuotaSetting")
    @patch(MODULE_PATH + ".LooseVersion")
    @patch(MODULE_PATH + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE_PATH + ".get_system")
    @patch(MODULE_PATH + ".AnsibleModule")
    @patch(MODULE_PATH + ".HAS_PYPURECLIENT", True)
    def test_rerun_with_matching_settings_is_unchanged(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_loose_version,
        mock_model,
    ):
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(direct_notifications=True, contact=CONTACT)
        mock_ansible_module.return_value = module
        blade = _blade(_settings(enabled=True, contact=CONTACT))
        mock_get_system.return_value = blade

        try:
            main()
        except SystemExit:
            pass

        mock_model.assert_not_called()
        blade.patch_quotas_settings.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE_PATH + ".LooseVersion")
    @patch(MODULE_PATH + ".get_rest_api_version", return_value="1.12")
    @patch(MODULE_PATH + ".get_system")
    @patch(MODULE_PATH + ".AnsibleModule")
    @patch(MODULE_PATH + ".HAS_PYPURECLIENT", True)
    def test_version_gate_fails_before_any_read_or_write(
        self, mock_ansible_module, mock_get_system, mock_version, mock_loose_version
    ):
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)
        module = _module(direct_notifications=True)
        mock_ansible_module.return_value = module
        blade = _blade(_settings())
        mock_get_system.return_value = blade

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Minimum version required: 2.0" in msg
        blade.get_quotas_settings.assert_not_called()
        blade.patch_quotas_settings.assert_not_called()

    @patch(MODULE_PATH + ".get_system")
    @patch(MODULE_PATH + ".AnsibleModule")
    @patch(MODULE_PATH + ".HAS_PYPURECLIENT", True)
    def test_contact_longer_than_256_fails_before_connecting(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(contact="a" * 257)
        mock_ansible_module.return_value = module

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "256 characters or less" in msg
        assert "257 given" in msg
        mock_get_system.assert_not_called()

    @patch(MODULE_PATH + ".QuotaSetting")
    @patch(MODULE_PATH + ".LooseVersion")
    @patch(MODULE_PATH + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE_PATH + ".get_system")
    @patch(MODULE_PATH + ".AnsibleModule")
    @patch(MODULE_PATH + ".HAS_PYPURECLIENT", True)
    def test_contact_of_exactly_256_is_accepted(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_loose_version,
        mock_model,
    ):
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(contact="a" * 256)
        mock_ansible_module.return_value = module
        blade = _blade(_settings())
        mock_get_system.return_value = blade

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_not_called()
        mock_model.assert_called_once_with(contact="a" * 256)
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".get_system")
    @patch(MODULE_PATH + ".AnsibleModule")
    @patch(MODULE_PATH + ".HAS_PYPURECLIENT", False)
    def test_fails_without_sdk(self, mock_ansible_module, mock_get_system):
        module = _module(direct_notifications=True)
        mock_ansible_module.return_value = module

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once_with(
            msg="py-pure-client sdk is required for this module"
        )
        mock_get_system.assert_not_called()
