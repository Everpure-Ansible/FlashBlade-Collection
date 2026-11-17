# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_messages module."""

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

from plugins.modules.purefb_messages import (
    main,
    _create_time_window,
    _timestamp,
    _alert_to_dict,
    _get_alerts_by_reference,
    HOUR,
    DAY,
    WEEK,
    YEAR,
)

ALERT_ID = "930e8295-ef9c-743c-95d9-3b2f294e8fc5"


def _base_params(**overrides):
    params = {
        "state": "open",
        "history": "1w",
        "flagged": False,
        "severity": ["all"],
        "flag": None,
        "unflag": None,
    }
    params.update(overrides)
    return params


def _alert(name="1", flagged=True, **overrides):
    alert = Mock()
    alert.name = name
    alert.id = ALERT_ID
    alert.summary = "Insecure Default pureuser Password"
    alert.component_type = "security"
    alert.component_name = "pureuser"
    alert.description = "The user pureuser is configured with the default password."
    alert.code = 1123
    alert.severity = "warning"
    alert.state = "open"
    alert.flagged = flagged
    alert.created = 1730354846597
    alert.notified = 1794603108844
    alert.updated = 1794894726453
    for key, value in overrides.items():
        setattr(alert, key, value)
    return alert


def _response(status_code=200, items=None):
    response = Mock()
    response.status_code = status_code
    response.items = items if items is not None else []
    response.errors = []
    return response


def _module(params, check_mode=False):
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.params = params
    module.check_mode = check_mode
    return module


def _run_main():
    try:
        main()
    except SystemExit:
        pass


class TestPurefbMessages:
    """Test cases for purefb_messages module"""

    # ---------------- helper-function unit tests ----------------

    def test_create_time_window_periods(self):
        """_create_time_window converts each allowed period"""
        assert _create_time_window("3h") == 3 * HOUR
        assert _create_time_window("2d") == 2 * DAY
        assert _create_time_window("4w") == 4 * WEEK
        assert _create_time_window("1y") == YEAR
        assert _create_time_window("5x") is None

    def test_alert_to_dict_fields(self):
        """_alert_to_dict renders the alert fields and UTC timestamps"""
        result = _alert_to_dict(_alert(flagged=False))
        assert result["summary"] == "Insecure Default pureuser Password"
        assert result["code"] == 1123
        assert result["severity"] == "warning"
        assert result["state"] == "open"
        assert result["flagged"] is False
        assert result["created"] == "2024-10-31 06:07:26 UTC"
        assert result["notified"].endswith(" UTC")
        assert result["updated"].endswith(" UTC")

    def test_timestamp_handles_missing_value(self):
        """_timestamp renders milliseconds as UTC and passes None through"""
        assert _timestamp(1730354846597) == "2024-10-31 06:07:26 UTC"
        assert _timestamp(None) is None
        assert _alert_to_dict(_alert(notified=None))["notified"] is None

    def test_get_alerts_by_reference_names_only(self):
        """_get_alerts_by_reference fetches names in one call"""
        module = Mock()
        module.fail_json = Mock(side_effect=SystemExit)
        blade = Mock()
        blade.get_alerts.return_value = _response(
            items=[_alert("1"), _alert("13", flagged=False)]
        )

        alerts = _get_alerts_by_reference(module, blade, ["1", "13"])

        blade.get_alerts.assert_called_once_with(names=["1", "13"])
        assert list(alerts) == ["1", "13"]
        assert alerts["13"].flagged is False

    def test_get_alerts_by_reference_ids_only(self):
        """_get_alerts_by_reference fetches UUIDs with ids="""
        module = Mock()
        module.fail_json = Mock(side_effect=SystemExit)
        blade = Mock()
        blade.get_alerts.return_value = _response(items=[_alert("1")])

        alerts = _get_alerts_by_reference(module, blade, [ALERT_ID.upper()])

        blade.get_alerts.assert_called_once_with(ids=[ALERT_ID.upper()])
        assert list(alerts) == ["1"]

    def test_get_alerts_by_reference_mixed_dedups_by_name(self):
        """_get_alerts_by_reference issues one call per kind and keys by name"""
        module = Mock()
        module.fail_json = Mock(side_effect=SystemExit)
        blade = Mock()
        blade.get_alerts.side_effect = [
            _response(items=[_alert("1"), _alert("166")]),
            _response(items=[_alert("1")]),
        ]

        alerts = _get_alerts_by_reference(module, blade, ["1", ALERT_ID, "166"])

        assert blade.get_alerts.call_count == 2
        assert blade.get_alerts.call_args_list[0][1] == {"names": ["1", "166"]}
        assert blade.get_alerts.call_args_list[1][1] == {"ids": [ALERT_ID]}
        assert sorted(alerts) == ["1", "166"]

    def test_get_alerts_by_reference_fails_on_missing_alert(self):
        """_get_alerts_by_reference surfaces the API error for an unknown alert"""
        module = Mock()
        module.fail_json = Mock(side_effect=SystemExit)
        blade = Mock()
        blade.get_alerts.return_value = _response(status_code=400)

        try:
            _get_alerts_by_reference(module, blade, ["999999"])
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "Failed to get alerts 999999" in module.fail_json.call_args[1]["msg"]

    # ---------------- listing flows ----------------

    @patch("plugins.modules.purefb_messages.get_system")
    @patch("plugins.modules.purefb_messages.AnsibleModule")
    @patch("plugins.modules.purefb_messages.HAS_PYPURECLIENT", True)
    def test_main_lists_dismissed_open_alerts_by_default(
        self, mock_ansible_module, mock_get_system
    ):
        """Default listing filters on open, unflagged alerts of any severity"""
        module = _module(_base_params())
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_alerts.return_value = _response(items=[_alert("1", flagged=False)])
        mock_get_system.return_value = blade

        _run_main()

        blade.get_alerts.assert_called_once()
        filter_string = blade.get_alerts.call_args[1]["filter"]
        assert filter_string.startswith("notified>")
        assert filter_string.endswith(
            " and state='open' and flagged='False' and severity='*'"
        )
        blade.patch_alerts.assert_not_called()
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is False
        messages = module.exit_json.call_args[1]["purefb_messages"]
        assert list(messages) == ["1"]
        assert messages["1"]["flagged"] is False

    @patch("plugins.modules.purefb_messages.get_system")
    @patch("plugins.modules.purefb_messages.AnsibleModule")
    @patch("plugins.modules.purefb_messages.HAS_PYPURECLIENT", True)
    def test_main_lists_flagged_closed_alerts_with_two_severities(
        self, mock_ansible_module, mock_get_system
    ):
        """flagged=true, state and several severities build an or-filter"""
        module = _module(
            _base_params(flagged=True, state="closed", severity=["critical", "warning"])
        )
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_alerts.return_value = _response(items=[])
        mock_get_system.return_value = blade

        _run_main()

        filter_string = blade.get_alerts.call_args[1]["filter"]
        assert filter_string.endswith(
            " and state='closed' and flagged='True'"
            " and (severity='critical' or severity='warning')"
        )
        assert module.exit_json.call_args[1]["purefb_messages"] == {}

    @patch("plugins.modules.purefb_messages.get_system")
    @patch("plugins.modules.purefb_messages.AnsibleModule")
    @patch("plugins.modules.purefb_messages.HAS_PYPURECLIENT", True)
    def test_main_lists_all_states_when_all_in_severity_list(
        self, mock_ansible_module, mock_get_system
    ):
        """state=all and a severity list containing all collapse to wildcards"""
        module = _module(_base_params(state="all", severity=["all", "info"]))
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_alerts.return_value = _response(items=[])
        mock_get_system.return_value = blade

        _run_main()

        filter_string = blade.get_alerts.call_args[1]["filter"]
        assert filter_string.endswith(
            " and state='*' and flagged='False' and severity='*'"
        )

    @patch("plugins.modules.purefb_messages.get_system")
    @patch("plugins.modules.purefb_messages.AnsibleModule")
    @patch("plugins.modules.purefb_messages.HAS_PYPURECLIENT", True)
    def test_main_list_fails_on_bad_history_period(
        self, mock_ansible_module, mock_get_system
    ):
        """An unknown history period fails before any API call"""
        module = _module(_base_params(history="3m"))
        mock_ansible_module.return_value = module
        blade = Mock()
        mock_get_system.return_value = blade

        _run_main()

        blade.get_alerts.assert_not_called()
        module.fail_json.assert_called_once()
        assert "not an allowed time period" in module.fail_json.call_args[1]["msg"]

    @patch("plugins.modules.purefb_messages.get_system")
    @patch("plugins.modules.purefb_messages.AnsibleModule")
    @patch("plugins.modules.purefb_messages.HAS_PYPURECLIENT", True)
    def test_main_list_fails_on_api_error(self, mock_ansible_module, mock_get_system):
        """A non-200 listing response is surfaced via fail_json"""
        module = _module(_base_params())
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_alerts.return_value = _response(status_code=400)
        mock_get_system.return_value = blade

        _run_main()

        module.fail_json.assert_called_once()
        assert "Failed to get alert messages" in module.fail_json.call_args[1]["msg"]

    # ---------------- flag / unflag flows ----------------

    @patch("plugins.modules.purefb_messages.Alert")
    @patch("plugins.modules.purefb_messages.get_system")
    @patch("plugins.modules.purefb_messages.AnsibleModule")
    @patch("plugins.modules.purefb_messages.HAS_PYPURECLIENT", True)
    def test_main_flags_unflagged_alert(
        self, mock_ansible_module, mock_get_system, mock_alert
    ):
        """flag PATCHes an alert whose flagged value is False"""
        module = _module(_base_params(flag=["1"]))
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_alerts.return_value = _response(items=[_alert("1", flagged=False)])
        blade.patch_alerts.return_value = _response(items=[_alert("1", flagged=True)])
        mock_get_system.return_value = blade

        _run_main()

        blade.get_alerts.assert_called_once_with(names=["1"])
        mock_alert.assert_called_once_with(flagged=True)
        blade.patch_alerts.assert_called_once_with(
            names=["1"], alerts_settings=mock_alert.return_value
        )
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True
        messages = module.exit_json.call_args[1]["purefb_messages"]
        assert list(messages) == ["1"]
        assert messages["1"]["flagged"] is True
        assert messages["1"]["code"] == 1123

    @patch("plugins.modules.purefb_messages.Alert")
    @patch("plugins.modules.purefb_messages.get_system")
    @patch("plugins.modules.purefb_messages.AnsibleModule")
    @patch("plugins.modules.purefb_messages.HAS_PYPURECLIENT", True)
    def test_main_flag_returns_the_patched_alert_from_the_response(
        self, mock_ansible_module, mock_get_system, mock_alert
    ):
        """After a PATCH the returned alert is the array's own view of it"""
        module = _module(_base_params(flag=["1", "13"]))
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_alerts.return_value = _response(
            items=[
                _alert("1", flagged=False, updated=1794894726453),
                _alert("13", flagged=True, updated=1794894726453),
            ]
        )
        blade.patch_alerts.return_value = _response(
            items=[_alert("1", flagged=True, updated=1794900000000)]
        )
        mock_get_system.return_value = blade

        _run_main()

        blade.patch_alerts.assert_called_once_with(
            names=["1"], alerts_settings=mock_alert.return_value
        )
        messages = module.exit_json.call_args[1]["purefb_messages"]
        assert sorted(messages) == ["1", "13"]
        assert messages["1"]["flagged"] is True
        assert messages["1"]["updated"] == _timestamp(1794900000000)
        assert messages["13"]["flagged"] is True
        assert messages["13"]["updated"] == _timestamp(1794894726453)
        assert messages["1"]["updated"] != messages["13"]["updated"]

    @patch("plugins.modules.purefb_messages.Alert")
    @patch("plugins.modules.purefb_messages.get_system")
    @patch("plugins.modules.purefb_messages.AnsibleModule")
    @patch("plugins.modules.purefb_messages.HAS_PYPURECLIENT", True)
    def test_main_flag_tolerates_alert_without_notified(
        self, mock_ansible_module, mock_get_system, mock_alert
    ):
        """An alert with no notified timestamp is flagged and returned cleanly"""
        module = _module(_base_params(flag=["1"]))
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_alerts.return_value = _response(
            items=[_alert("1", flagged=False, notified=None)]
        )
        blade.patch_alerts.return_value = _response(
            items=[_alert("1", flagged=True, notified=None)]
        )
        mock_get_system.return_value = blade

        _run_main()

        blade.patch_alerts.assert_called_once()
        module.fail_json.assert_not_called()
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True
        messages = module.exit_json.call_args[1]["purefb_messages"]
        assert messages["1"]["flagged"] is True
        assert messages["1"]["notified"] is None
        assert messages["1"]["created"] == "2024-10-31 06:07:26 UTC"

    @patch("plugins.modules.purefb_messages.get_system")
    @patch("plugins.modules.purefb_messages.AnsibleModule")
    @patch("plugins.modules.purefb_messages.HAS_PYPURECLIENT", True)
    def test_main_flag_is_idempotent(self, mock_ansible_module, mock_get_system):
        """flag on an already flagged alert issues no PATCH"""
        module = _module(_base_params(flag=["1"]))
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_alerts.return_value = _response(items=[_alert("1", flagged=True)])
        mock_get_system.return_value = blade

        _run_main()

        blade.patch_alerts.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False
        messages = module.exit_json.call_args[1]["purefb_messages"]
        assert messages["1"]["flagged"] is True

    @patch("plugins.modules.purefb_messages.Alert")
    @patch("plugins.modules.purefb_messages.get_system")
    @patch("plugins.modules.purefb_messages.AnsibleModule")
    @patch("plugins.modules.purefb_messages.HAS_PYPURECLIENT", True)
    def test_main_unflags_only_the_flagged_alerts(
        self, mock_ansible_module, mock_get_system, mock_alert
    ):
        """unflag PATCHes only the alerts still flagged, in one call"""
        module = _module(_base_params(unflag=["1", "13", "166"]))
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_alerts.return_value = _response(
            items=[
                _alert("1", flagged=False),
                _alert("13", flagged=True),
                _alert("166", flagged=True),
            ]
        )
        blade.patch_alerts.return_value = _response(items=[])
        mock_get_system.return_value = blade

        _run_main()

        mock_alert.assert_called_once_with(flagged=False)
        blade.patch_alerts.assert_called_once_with(
            names=["13", "166"], alerts_settings=mock_alert.return_value
        )
        assert module.exit_json.call_args[1]["changed"] is True
        messages = module.exit_json.call_args[1]["purefb_messages"]
        assert sorted(messages) == ["1", "13", "166"]
        assert all(entry["flagged"] is False for entry in messages.values())

    @patch("plugins.modules.purefb_messages.get_system")
    @patch("plugins.modules.purefb_messages.AnsibleModule")
    @patch("plugins.modules.purefb_messages.HAS_PYPURECLIENT", True)
    def test_main_unflag_is_idempotent(self, mock_ansible_module, mock_get_system):
        """unflag on already unflagged alerts issues no PATCH"""
        module = _module(_base_params(unflag=["1"]))
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_alerts.return_value = _response(items=[_alert("1", flagged=False)])
        mock_get_system.return_value = blade

        _run_main()

        blade.patch_alerts.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_messages.get_system")
    @patch("plugins.modules.purefb_messages.AnsibleModule")
    @patch("plugins.modules.purefb_messages.HAS_PYPURECLIENT", True)
    def test_main_flag_check_mode_skips_patch(
        self, mock_ansible_module, mock_get_system
    ):
        """check mode reports the change but does not PATCH"""
        module = _module(_base_params(flag=["1"]), check_mode=True)
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_alerts.return_value = _response(items=[_alert("1", flagged=False)])
        mock_get_system.return_value = blade

        _run_main()

        blade.patch_alerts.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True
        messages = module.exit_json.call_args[1]["purefb_messages"]
        assert messages["1"]["flagged"] is True

    @patch("plugins.modules.purefb_messages.Alert")
    @patch("plugins.modules.purefb_messages.get_system")
    @patch("plugins.modules.purefb_messages.AnsibleModule")
    @patch("plugins.modules.purefb_messages.HAS_PYPURECLIENT", True)
    def test_main_flag_by_id_patches_by_name(
        self, mock_ansible_module, mock_get_system, mock_alert
    ):
        """An alert given by UUID is fetched with ids= and PATCHed by its name"""
        module = _module(_base_params(flag=[ALERT_ID]))
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_alerts.return_value = _response(items=[_alert("1", flagged=False)])
        blade.patch_alerts.return_value = _response(items=[])
        mock_get_system.return_value = blade

        _run_main()

        blade.get_alerts.assert_called_once_with(ids=[ALERT_ID])
        blade.patch_alerts.assert_called_once_with(
            names=["1"], alerts_settings=mock_alert.return_value
        )
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_messages.get_system")
    @patch("plugins.modules.purefb_messages.AnsibleModule")
    @patch("plugins.modules.purefb_messages.HAS_PYPURECLIENT", True)
    def test_main_flag_fails_on_unknown_alert(
        self, mock_ansible_module, mock_get_system
    ):
        """An unknown alert reference fails without a PATCH"""
        module = _module(_base_params(flag=["999999"]))
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_alerts.return_value = _response(status_code=400)
        mock_get_system.return_value = blade

        _run_main()

        blade.patch_alerts.assert_not_called()
        module.fail_json.assert_called_once()
        assert "Failed to get alerts 999999" in module.fail_json.call_args[1]["msg"]

    @patch("plugins.modules.purefb_messages.Alert")
    @patch("plugins.modules.purefb_messages.get_system")
    @patch("plugins.modules.purefb_messages.AnsibleModule")
    @patch("plugins.modules.purefb_messages.HAS_PYPURECLIENT", True)
    def test_main_unflag_fails_on_patch_error(
        self, mock_ansible_module, mock_get_system, mock_alert
    ):
        """A non-200 PATCH response is surfaced via fail_json"""
        module = _module(_base_params(unflag=["1"]))
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_alerts.return_value = _response(items=[_alert("1", flagged=True)])
        blade.patch_alerts.return_value = _response(status_code=400)
        mock_get_system.return_value = blade

        _run_main()

        module.fail_json.assert_called_once()
        assert "Failed to unflag alerts 1" in module.fail_json.call_args[1]["msg"]
        module.exit_json.assert_not_called()

    @patch("plugins.modules.purefb_messages.get_system")
    @patch("plugins.modules.purefb_messages.AnsibleModule")
    @patch("plugins.modules.purefb_messages.HAS_PYPURECLIENT", True)
    def test_main_empty_flag_list_is_noop(self, mock_ansible_module, mock_get_system):
        """An empty flag list neither lists nor PATCHes"""
        module = _module(_base_params(flag=[]))
        mock_ansible_module.return_value = module
        blade = Mock()
        mock_get_system.return_value = blade

        _run_main()

        blade.get_alerts.assert_not_called()
        blade.patch_alerts.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False
        assert module.exit_json.call_args[1]["purefb_messages"] == {}

    @patch("plugins.modules.purefb_messages.get_system")
    @patch("plugins.modules.purefb_messages.AnsibleModule")
    @patch("plugins.modules.purefb_messages.HAS_PYPURECLIENT", False)
    def test_main_fails_without_sdk(self, mock_ansible_module, mock_get_system):
        """Test failure when py-pure-client SDK is not installed"""
        module = _module(_base_params(flag=["1"]))
        mock_ansible_module.return_value = module

        _run_main()

        mock_get_system.assert_not_called()
        module.fail_json.assert_called_once()
        assert "py-pure-client" in module.fail_json.call_args[1]["msg"]

    @patch("plugins.modules.purefb_messages.purefb_argument_spec", return_value={})
    @patch("plugins.modules.purefb_messages.get_system")
    @patch("plugins.modules.purefb_messages.AnsibleModule")
    @patch("plugins.modules.purefb_messages.HAS_PYPURECLIENT", True)
    def test_main_declares_flag_unflag_mutually_exclusive(
        self, mock_ansible_module, mock_get_system, mock_argument_spec
    ):
        """AnsibleModule is built with flag and unflag mutually exclusive"""
        module = _module(_base_params())
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_alerts.return_value = _response(items=[])
        mock_get_system.return_value = blade

        _run_main()

        kwargs = mock_ansible_module.call_args[1]
        assert kwargs["mutually_exclusive"] == [["flag", "unflag"]]
        assert kwargs["supports_check_mode"] is True
        spec = mock_ansible_module.call_args[0][0]
        assert spec["flag"] == {"type": "list", "elements": "str"}
        assert spec["unflag"] == {"type": "list", "elements": "str"}
