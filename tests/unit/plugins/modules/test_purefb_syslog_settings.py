# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for the purefb_syslog_settings module."""

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

from plugins.modules.purefb_syslog_settings import (
    main,
    get_settings,
    update_settings,
    _reference_name,
)

MODULE_PATH = "plugins.modules.purefb_syslog_settings"


def _params(**overrides):
    params = {
        "name": None,
        "state": "present",
        "ca_certificate": None,
        "ca_certificate_group": None,
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


def _ref(name):
    """A reference as the array returns it: a dict, all-None when unset."""
    if name:
        return {"name": name, "id": "ref-id", "resource_type": "certificates"}
    return {"name": None, "id": None, "resource_type": None}


def _settings(ca_certificate=None, ca_certificate_group=None):
    """The settings singleton shaped like a GET result."""
    obj = Mock(spec=["id", "name", "ca_certificate", "ca_certificate_group"])
    obj.name = "management"
    obj.ca_certificate = _ref(ca_certificate)
    obj.ca_certificate_group = _ref(ca_certificate_group)
    return obj


def _response(status_code=200, items=None):
    response = Mock()
    response.status_code = status_code
    response.items = items if items is not None else []
    return response


def _blade(settings=None, cert_status=200, group_status=200, patch_status=200):
    blade = Mock()
    blade.get_syslog_servers_settings.return_value = _response(
        items=[settings] if settings is not None else []
    )
    blade.get_certificates.return_value = _response(cert_status)
    blade.get_certificate_groups.return_value = _response(group_status)
    blade.patch_syslog_servers_settings.return_value = _response(patch_status)
    return blade


class TestReferenceName:
    """_reference_name must read dict references, object references and unset values."""

    def test_reads_name_from_dict(self):
        assert (
            _reference_name(_settings(ca_certificate="ca1"), "ca_certificate") == "ca1"
        )

    def test_unset_dict_is_none(self):
        assert _reference_name(_settings(), "ca_certificate") is None

    def test_empty_name_is_none(self):
        obj = Mock(spec=["ca_certificate"])
        obj.ca_certificate = {"name": ""}
        assert _reference_name(obj, "ca_certificate") is None

    def test_reads_name_from_object(self):
        ref = Mock(spec=["name"])
        ref.name = "grp1"
        obj = Mock(spec=["ca_certificate_group"])
        obj.ca_certificate_group = ref
        assert _reference_name(obj, "ca_certificate_group") == "grp1"

    def test_missing_field_is_none(self):
        assert _reference_name(Mock(spec=["name"]), "ca_certificate") is None


class TestGetSettings:
    """get_settings must find the singleton and fail clearly otherwise."""

    def test_returns_the_single_object_without_names(self):
        settings = _settings()
        blade = _blade(settings)
        assert get_settings(_module(), blade) is settings
        blade.get_syslog_servers_settings.assert_called_once_with()

    def test_queries_by_name_when_given(self):
        settings = _settings()
        blade = _blade(settings)
        assert get_settings(_module(name="management"), blade) is settings
        blade.get_syslog_servers_settings.assert_called_once_with(names=["management"])

    @patch(MODULE_PATH + ".get_error_message", return_value="boom")
    def test_fails_on_api_error(self, mock_error):
        module = _module()
        blade = _blade()
        blade.get_syslog_servers_settings.return_value = _response(400)
        try:
            get_settings(module, blade)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to read syslog server settings" in msg
        assert "boom" in msg

    def test_fails_when_nothing_is_returned(self):
        module = _module()
        try:
            get_settings(module, _blade())
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "No syslog server settings" in module.fail_json.call_args[1]["msg"]

    def test_fails_when_several_objects_and_no_name(self):
        module = _module()
        other = _settings()
        other.name = "data-audit"
        blade = _blade()
        blade.get_syslog_servers_settings.return_value = _response(
            items=[_settings(), other]
        )
        try:
            get_settings(module, blade)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "More than one" in msg
        assert "management, data-audit" in msg

    def test_fails_when_name_is_realm_qualified(self):
        """The array returns its object whatever name is asked for."""
        module = _module(name="realm1::management")
        blade = _blade(_settings())
        try:
            get_settings(module, blade)
        except SystemExit:
            pass
        blade.get_syslog_servers_settings.assert_called_once_with(
            names=["realm1::management"]
        )
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "realm1::management does not exist" in msg
        assert "array-wide" in msg
        assert "cannot be scoped to a realm" in msg
        assert msg.endswith("the settings object of this array is management.")

    def test_fails_when_name_is_unknown(self):
        module = _module(name="nosuch")
        blade = _blade(_settings())
        try:
            get_settings(module, blade)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Syslog server settings object nosuch does not exist" in msg
        assert msg.endswith("the settings object of this array is management.")

    def test_name_selects_one_of_several_objects(self):
        module = _module(name="data-audit")
        other = _settings()
        other.name = "data-audit"
        blade = _blade()
        blade.get_syslog_servers_settings.return_value = _response(
            items=[_settings(), other]
        )
        assert get_settings(module, blade) is other
        module.fail_json.assert_not_called()

    def test_name_mismatch_lists_every_object(self):
        module = _module(name="realm1::data-audit")
        other = _settings()
        other.name = "data-audit"
        blade = _blade()
        blade.get_syslog_servers_settings.return_value = _response(
            items=[_settings(), other]
        )
        try:
            get_settings(module, blade)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "realm1::data-audit does not exist" in msg
        assert msg.endswith("management, data-audit.")


class TestUpdateSettings:
    """update_settings must PATCH only what differs and report it."""

    @patch(MODULE_PATH + ".SyslogServerSettings")
    def test_sets_certificate_when_different(self, mock_model):
        module = _module(ca_certificate="ca2")
        blade = _blade()
        try:
            update_settings(module, blade, _settings(ca_certificate="ca1"))
        except SystemExit:
            pass
        blade.get_certificates.assert_called_once_with(names=["ca2"])
        mock_model.assert_called_once_with(ca_certificate={"name": "ca2"})
        blade.patch_syslog_servers_settings.assert_called_once_with(
            names=["management"], syslog_server_settings=mock_model.return_value
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".SyslogServerSettings")
    def test_sets_certificate_when_nothing_configured(self, mock_model):
        module = _module(ca_certificate="ca1")
        blade = _blade()
        try:
            update_settings(module, blade, _settings())
        except SystemExit:
            pass
        mock_model.assert_called_once_with(ca_certificate={"name": "ca1"})
        module.exit_json.assert_called_once_with(changed=True)

    def test_no_change_when_certificate_matches(self):
        module = _module(ca_certificate="ca1")
        blade = _blade()
        try:
            update_settings(module, blade, _settings(ca_certificate="ca1"))
        except SystemExit:
            pass
        blade.get_certificates.assert_not_called()
        blade.patch_syslog_servers_settings.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE_PATH + ".SyslogServerSettings")
    def test_switches_to_certificate_group(self, mock_model):
        """The array refuses both references, so the switch clears the certificate."""
        module = _module(ca_certificate_group="grp1")
        blade = _blade()
        try:
            update_settings(module, blade, _settings(ca_certificate="ca1"))
        except SystemExit:
            pass
        blade.get_certificate_groups.assert_called_once_with(names=["grp1"])
        blade.get_certificates.assert_not_called()
        mock_model.assert_called_once_with(
            ca_certificate_group={"name": "grp1"}, ca_certificate={"name": ""}
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".SyslogServerSettings")
    def test_switches_back_to_certificate(self, mock_model):
        """Switching from a group to a certificate clears the group."""
        module = _module(ca_certificate="ca1")
        blade = _blade()
        try:
            update_settings(module, blade, _settings(ca_certificate_group="grp1"))
        except SystemExit:
            pass
        blade.get_certificates.assert_called_once_with(names=["ca1"])
        mock_model.assert_called_once_with(
            ca_certificate={"name": "ca1"}, ca_certificate_group={"name": ""}
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_no_change_when_group_matches(self):
        module = _module(ca_certificate_group="grp1")
        blade = _blade()
        try:
            update_settings(module, blade, _settings(ca_certificate_group="grp1"))
        except SystemExit:
            pass
        blade.patch_syslog_servers_settings.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE_PATH + ".get_error_message", return_value="boom")
    def test_fails_when_certificate_is_missing(self, mock_error):
        module = _module(ca_certificate="nope")
        blade = _blade(cert_status=400)
        try:
            update_settings(module, blade, _settings())
        except SystemExit:
            pass
        module.fail_json.assert_called_once_with(
            msg="Certificate nope does not exist. Error: boom"
        )
        blade.patch_syslog_servers_settings.assert_not_called()

    @patch(MODULE_PATH + ".get_error_message", return_value="boom")
    def test_fails_when_certificate_group_is_missing(self, mock_error):
        module = _module(ca_certificate_group="nope")
        blade = _blade(group_status=400)
        try:
            update_settings(module, blade, _settings())
        except SystemExit:
            pass
        module.fail_json.assert_called_once_with(
            msg="Certificate group nope does not exist. Error: boom"
        )
        blade.patch_syslog_servers_settings.assert_not_called()

    @patch(MODULE_PATH + ".SyslogServerSettings")
    def test_empty_string_clears_certificate(self, mock_model):
        module = _module(ca_certificate="")
        blade = _blade()
        try:
            update_settings(module, blade, _settings(ca_certificate="ca1"))
        except SystemExit:
            pass
        blade.get_certificates.assert_not_called()
        mock_model.assert_called_once_with(ca_certificate={"name": ""})
        blade.patch_syslog_servers_settings.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    def test_empty_string_is_idempotent_when_unset(self):
        module = _module(ca_certificate="")
        blade = _blade()
        try:
            update_settings(module, blade, _settings())
        except SystemExit:
            pass
        blade.patch_syslog_servers_settings.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_empty_certificate_leaves_a_configured_group_alone(self):
        module = _module(ca_certificate="")
        blade = _blade()
        try:
            update_settings(module, blade, _settings(ca_certificate_group="grp1"))
        except SystemExit:
            pass
        blade.patch_syslog_servers_settings.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE_PATH + ".SyslogServerSettings")
    def test_absent_clears_configured_certificate(self, mock_model):
        module = _module(state="absent")
        blade = _blade()
        try:
            update_settings(module, blade, _settings(ca_certificate="ca1"))
        except SystemExit:
            pass
        mock_model.assert_called_once_with(ca_certificate={"name": ""})
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".SyslogServerSettings")
    def test_absent_clears_configured_group(self, mock_model):
        module = _module(state="absent")
        blade = _blade()
        try:
            update_settings(module, blade, _settings(ca_certificate_group="grp1"))
        except SystemExit:
            pass
        mock_model.assert_called_once_with(ca_certificate_group={"name": ""})
        module.exit_json.assert_called_once_with(changed=True)

    def test_absent_is_idempotent_when_nothing_configured(self):
        module = _module(state="absent")
        blade = _blade()
        try:
            update_settings(module, blade, _settings())
        except SystemExit:
            pass
        blade.patch_syslog_servers_settings.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE_PATH + ".SyslogServerSettings")
    def test_absent_ignores_requested_names(self, mock_model):
        module = _module(state="absent", ca_certificate="ca2")
        blade = _blade()
        try:
            update_settings(module, blade, _settings(ca_certificate="ca1"))
        except SystemExit:
            pass
        blade.get_certificates.assert_not_called()
        mock_model.assert_called_once_with(ca_certificate={"name": ""})
        module.exit_json.assert_called_once_with(changed=True)

    def test_nothing_requested_is_no_change(self):
        module = _module()
        blade = _blade()
        try:
            update_settings(module, blade, _settings(ca_certificate="ca1"))
        except SystemExit:
            pass
        blade.patch_syslog_servers_settings.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_check_mode_reports_change_without_patching(self):
        module = _module(ca_certificate="ca2")
        module.check_mode = True
        blade = _blade()
        try:
            update_settings(module, blade, _settings(ca_certificate="ca1"))
        except SystemExit:
            pass
        blade.patch_syslog_servers_settings.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".get_error_message", return_value="boom")
    @patch(MODULE_PATH + ".SyslogServerSettings")
    def test_fails_when_patch_is_rejected(self, mock_model, mock_error):
        module = _module(ca_certificate="ca2")
        blade = _blade(patch_status=400)
        try:
            update_settings(module, blade, _settings(ca_certificate="ca1"))
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Updating syslog server settings management failed" in msg
        assert "boom" in msg
        module.exit_json.assert_not_called()

    def test_no_change_when_realm_certificate_matches(self):
        module = _module(ca_certificate="realm1::ca1")
        blade = _blade()
        try:
            update_settings(module, blade, _settings(ca_certificate="realm1::ca1"))
        except SystemExit:
            pass
        blade.get_certificates.assert_not_called()
        blade.patch_syslog_servers_settings.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE_PATH + ".SyslogServerSettings")
    def test_realm_certificate_is_looked_up_and_sent_qualified(self, mock_model):
        """A bare name and its realm namesake are different certificates."""
        module = _module(ca_certificate="realm1::ca1")
        blade = _blade()
        try:
            update_settings(module, blade, _settings(ca_certificate="ca1"))
        except SystemExit:
            pass
        blade.get_certificates.assert_called_once_with(names=["realm1::ca1"])
        mock_model.assert_called_once_with(ca_certificate={"name": "realm1::ca1"})
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".SyslogServerSettings")
    def test_bare_group_replaces_its_realm_namesake(self, mock_model):
        module = _module(ca_certificate_group="grp1")
        blade = _blade()
        try:
            update_settings(
                module, blade, _settings(ca_certificate_group="realm1::grp1")
            )
        except SystemExit:
            pass
        blade.get_certificate_groups.assert_called_once_with(names=["grp1"])
        mock_model.assert_called_once_with(ca_certificate_group={"name": "grp1"})
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".SyslogServerSettings")
    def test_switches_from_realm_certificate_to_realm_group(self, mock_model):
        module = _module(ca_certificate_group="realm1::grp1")
        blade = _blade()
        try:
            update_settings(module, blade, _settings(ca_certificate="realm1::ca1"))
        except SystemExit:
            pass
        blade.get_certificate_groups.assert_called_once_with(names=["realm1::grp1"])
        mock_model.assert_called_once_with(
            ca_certificate_group={"name": "realm1::grp1"}, ca_certificate={"name": ""}
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".SyslogServerSettings")
    def test_absent_clears_realm_group(self, mock_model):
        module = _module(state="absent")
        blade = _blade()
        try:
            update_settings(
                module, blade, _settings(ca_certificate_group="realm1::grp1")
            )
        except SystemExit:
            pass
        mock_model.assert_called_once_with(ca_certificate_group={"name": ""})
        module.exit_json.assert_called_once_with(changed=True)


class TestMain:
    """main() wiring: SDK guard, version gate, argument spec."""

    @patch(MODULE_PATH + ".SyslogServerSettings")
    @patch(MODULE_PATH + ".LooseVersion")
    @patch(MODULE_PATH + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE_PATH + ".get_system")
    @patch(MODULE_PATH + ".AnsibleModule")
    @patch(MODULE_PATH + ".HAS_PYPURECLIENT", True)
    def test_sets_certificate_end_to_end(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_loose_version,
        mock_model,
    ):
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(ca_certificate="ca2")
        mock_ansible_module.return_value = module
        blade = _blade(_settings(ca_certificate="ca1"))
        mock_get_system.return_value = blade

        try:
            main()
        except SystemExit:
            pass

        assert mock_ansible_module.call_args[1]["mutually_exclusive"] == [
            ["ca_certificate", "ca_certificate_group"]
        ]
        assert mock_ansible_module.call_args[1]["supports_check_mode"] is True
        mock_model.assert_called_once_with(ca_certificate={"name": "ca2"})
        blade.patch_syslog_servers_settings.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".LooseVersion")
    @patch(MODULE_PATH + ".get_rest_api_version", return_value="1.12")
    @patch(MODULE_PATH + ".get_system")
    @patch(MODULE_PATH + ".AnsibleModule")
    @patch(MODULE_PATH + ".HAS_PYPURECLIENT", True)
    def test_version_gate_fails_before_any_read_or_write(
        self, mock_ansible_module, mock_get_system, mock_version, mock_loose_version
    ):
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)
        module = _module(ca_certificate="ca2")
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
        blade.get_syslog_servers_settings.assert_not_called()
        blade.patch_syslog_servers_settings.assert_not_called()

    @patch(MODULE_PATH + ".get_system")
    @patch(MODULE_PATH + ".AnsibleModule")
    @patch(MODULE_PATH + ".HAS_PYPURECLIENT", False)
    def test_fails_without_sdk(self, mock_ansible_module, mock_get_system):
        module = _module()
        mock_ansible_module.return_value = module

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once_with(
            msg="py-pure-client sdk is required for this module"
        )
        mock_get_system.assert_not_called()

    @patch(MODULE_PATH + ".SyslogServerSettings")
    @patch(MODULE_PATH + ".LooseVersion")
    @patch(MODULE_PATH + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE_PATH + ".get_system")
    @patch(MODULE_PATH + ".AnsibleModule")
    @patch(MODULE_PATH + ".HAS_PYPURECLIENT", True)
    def test_realm_qualified_name_fails_in_check_mode(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_loose_version,
        mock_model,
    ):
        """Check mode must not report a change for a name the array ignores."""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(name="realm1::management", ca_certificate_group="realm1::grp1")
        module.check_mode = True
        mock_ansible_module.return_value = module
        blade = _blade(_settings(ca_certificate="ca1"))
        mock_get_system.return_value = blade

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "realm1::management does not exist" in msg
        assert "array-wide" in msg
        blade.get_certificate_groups.assert_not_called()
        blade.patch_syslog_servers_settings.assert_not_called()
        module.exit_json.assert_not_called()

    @patch(MODULE_PATH + ".SyslogServerSettings")
    @patch(MODULE_PATH + ".LooseVersion")
    @patch(MODULE_PATH + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE_PATH + ".get_system")
    @patch(MODULE_PATH + ".AnsibleModule")
    @patch(MODULE_PATH + ".HAS_PYPURECLIENT", True)
    def test_wrong_name_with_state_absent_clears_nothing(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_loose_version,
        mock_model,
    ):
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(name="realm1::management", state="absent")
        mock_ansible_module.return_value = module
        blade = _blade(_settings(ca_certificate="ca1"))
        mock_get_system.return_value = blade

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "array-wide" in module.fail_json.call_args[1]["msg"]
        mock_model.assert_not_called()
        blade.patch_syslog_servers_settings.assert_not_called()
        module.exit_json.assert_not_called()

    @patch(MODULE_PATH + ".SyslogServerSettings")
    @patch(MODULE_PATH + ".LooseVersion")
    @patch(MODULE_PATH + ".get_rest_api_version", return_value="2.30")
    @patch(MODULE_PATH + ".get_system")
    @patch(MODULE_PATH + ".AnsibleModule")
    @patch(MODULE_PATH + ".HAS_PYPURECLIENT", True)
    def test_matching_name_sets_realm_group_end_to_end(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_loose_version,
        mock_model,
    ):
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(name="management", ca_certificate_group="realm1::grp1")
        mock_ansible_module.return_value = module
        blade = _blade(_settings(ca_certificate="ca1"))
        mock_get_system.return_value = blade

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_not_called()
        blade.get_certificate_groups.assert_called_once_with(names=["realm1::grp1"])
        mock_model.assert_called_once_with(
            ca_certificate_group={"name": "realm1::grp1"}, ca_certificate={"name": ""}
        )
        blade.patch_syslog_servers_settings.assert_called_once_with(
            names=["management"], syslog_server_settings=mock_model.return_value
        )
        module.exit_json.assert_called_once_with(changed=True)
