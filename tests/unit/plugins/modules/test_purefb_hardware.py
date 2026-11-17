# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_hardware module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from unittest.mock import Mock, call, patch, MagicMock

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

from plugins.modules.purefb_hardware import (
    main,
    get_hardware,
    get_connector,
    patch_connector,
    connector_changes,
    GBPS,
)
from plugins.module_utils.version import LooseVersion as RealLooseVersion

MODULE = "plugins.modules.purefb_hardware"
CONNECTOR = "CH1.FM1.ETH1"
BLADE = "CH1.FB1"


def _base_params(**overrides):
    params = {
        "name": CONNECTOR,
        "enabled": None,
        "speed": None,
        "ports": None,
        "port_speed": None,
        "lanes_per_port": None,
    }
    params.update(overrides)
    return params


def _module(check_mode=False, **params):
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.params = _base_params(**params)
    module.check_mode = check_mode
    return module


def _response(status_code=200, items=None):
    res = Mock()
    res.status_code = status_code
    res.items = items if items is not None else []
    res.errors = []
    return res


def _connector(
    lane_speed=25 * GBPS, port_count=1, port_speed=100 * GBPS, lanes_per_port=4
):
    connector = Mock()
    connector.name = CONNECTOR
    connector.lane_speed = lane_speed
    connector.port_count = port_count
    connector.port_speed = port_speed
    connector.lanes_per_port = lanes_per_port
    return connector


def _hardware(identify_enabled=False):
    hardware = Mock()
    hardware.name = BLADE
    hardware.identify_enabled = identify_enabled
    return hardware


def _blade(api_version="2.30", hardware=None, connector=None):
    """A blade mock whose GETs return the given objects (or 400 when None)."""
    blade = Mock()
    if hardware is None:
        blade.get_hardware.return_value = _response(400)
    else:
        blade.get_hardware.return_value = _response(items=[hardware])
    if connector is None:
        blade.get_network_interfaces_connectors.return_value = _response(400)
        blade.get_hardware_connectors.return_value = _response(400)
    else:
        blade.get_network_interfaces_connectors.return_value = _response(
            items=[connector]
        )
        blade.get_hardware_connectors.return_value = _response(items=[connector])
    blade.patch_hardware.return_value = _response()
    blade.patch_network_interfaces_connectors.return_value = _response()
    blade.patch_hardware_connectors.return_value = _response()
    blade.get_versions.return_value.items = [api_version]
    return blade


def _run_main(module, blade, api_version="2.30"):
    """Run main() with the module/blade mocks and a fresh flashblade SDK mock."""
    sdk = MagicMock()
    with patch(MODULE + ".AnsibleModule", return_value=module) as ansible_module, patch(
        MODULE + ".purefb_argument_spec", return_value={}
    ), patch(MODULE + ".get_system", return_value=blade), patch(
        MODULE + ".get_rest_api_version", return_value=api_version
    ), patch(
        MODULE + ".LooseVersion", RealLooseVersion
    ), patch(
        MODULE + ".HAS_PYPURECLIENT", True
    ), patch(
        MODULE + ".flashblade", sdk
    ), patch(
        MODULE + ".get_error_message", return_value="boom"
    ):
        try:
            main()
        except SystemExit:
            pass
    return sdk, ansible_module


class TestPurefbHardware:
    """Test cases for purefb_hardware module"""

    # ---------------- connector_changes ----------------

    def test_connector_changes_legacy_no_change(self):
        """Legacy pair already configured sends nothing"""
        module = _module(speed=25, ports=1)
        assert connector_changes(module, _connector()) == {}

    def test_connector_changes_legacy_sends_whole_pair(self):
        """A differing lane speed sends both legacy fields in one body"""
        module = _module(speed=40, ports=1)
        assert connector_changes(module, _connector()) == {
            "lane_speed": 40 * GBPS,
            "port_count": 1,
        }

    def test_connector_changes_legacy_single_field(self):
        """Only the requested legacy field is sent when the other is omitted"""
        module = _module(ports=4)
        assert connector_changes(module, _connector()) == {"port_count": 4}

    def test_connector_changes_port_speed_no_change(self):
        """port_speed pair already configured sends nothing"""
        module = _module(port_speed=100, lanes_per_port=4)
        assert connector_changes(module, _connector()) == {}

    def test_connector_changes_port_speed_sends_pair_without_legacy_fields(self):
        """port_speed form sends port_speed and lanes_per_port only"""
        module = _module(port_speed=400, lanes_per_port=8)
        assert connector_changes(module, _connector()) == {
            "port_speed": 400 * GBPS,
            "lanes_per_port": 8,
        }

    # ---------------- endpoint selection ----------------

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    def test_get_connector_uses_network_interfaces_from_2_17(self):
        """REST 2.17+ reads /network-interfaces/connectors"""
        connector = _connector()
        blade = _blade(connector=connector)
        assert get_connector(_module(), blade, "2.17", CONNECTOR) is connector
        blade.get_network_interfaces_connectors.assert_called_once_with(
            names=[CONNECTOR]
        )
        blade.get_hardware_connectors.assert_not_called()

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    def test_get_connector_uses_hardware_connectors_below_2_17(self):
        """REST below 2.17 keeps the /hardware-connectors endpoint"""
        connector = _connector()
        blade = _blade(connector=connector)
        assert get_connector(_module(), blade, "2.16", CONNECTOR) is connector
        blade.get_hardware_connectors.assert_called_once_with(names=[CONNECTOR])
        blade.get_network_interfaces_connectors.assert_not_called()

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_error_message", Mock(return_value="boom"))
    def test_get_connector_fails_with_array_error_on_non_200(self):
        """A rejected GET fails and carries the array's error text"""
        module = _module(name=BLADE)
        blade = _blade(connector=None)
        with pytest.raises(SystemExit):
            get_connector(module, blade, "2.30", BLADE)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "is not a connector or does not exist" in msg
        assert "boom" in msg

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    def test_get_connector_fails_on_empty_result(self):
        """A 200 with no items means the name is not a connector"""
        module = _module(name=BLADE)
        blade = _blade(connector=None)
        blade.get_network_interfaces_connectors.return_value = _response(items=[])
        with pytest.raises(SystemExit):
            get_connector(module, blade, "2.30", BLADE)
        module.fail_json.assert_called_once_with(
            msg="Hardware component {0} is not a connector".format(BLADE)
        )

    @patch(MODULE + ".get_error_message", Mock(return_value="boom"))
    def test_get_hardware_fails_on_error_or_empty(self):
        """A rejected or empty hardware GET fails with 'does not exist'"""
        module = _module(name=BLADE)
        blade = _blade(hardware=None)
        with pytest.raises(SystemExit):
            get_hardware(module, blade, BLADE)
        msg = module.fail_json.call_args[1]["msg"]
        assert "does not exist" in msg
        assert "boom" in msg

        module = _module(name=BLADE)
        blade.get_hardware.return_value = _response(items=[])
        with pytest.raises(SystemExit):
            get_hardware(module, blade, BLADE)
        assert "does not exist" in module.fail_json.call_args[1]["msg"]

        hardware = _hardware()
        blade = _blade(hardware=hardware)
        assert get_hardware(_module(name=BLADE), blade, BLADE) is hardware

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    def test_patch_connector_endpoint_and_kwarg_follow_version(self):
        """PATCH uses network_connector= on 2.17+ and hardware_connector= before"""
        blade = _blade()
        body = Mock()
        patch_connector(blade, "2.30", CONNECTOR, body)
        blade.patch_network_interfaces_connectors.assert_called_once_with(
            names=[CONNECTOR], network_connector=body
        )
        blade.patch_hardware_connectors.assert_not_called()

        blade = _blade()
        patch_connector(blade, "2.14", CONNECTOR, body)
        blade.patch_hardware_connectors.assert_called_once_with(
            names=[CONNECTOR], hardware_connector=body
        )
        blade.patch_network_interfaces_connectors.assert_not_called()

    # ---------------- main(): argument constraints ----------------

    def test_main_declares_mutual_exclusion_and_required_together(self):
        """The two configuration forms are exclusive and the new pair is complete"""
        module = _module(name=BLADE)
        blade = _blade(hardware=_hardware())
        ansible_module = _run_main(module, blade)[1]
        kwargs = ansible_module.call_args[1]
        assert kwargs["supports_check_mode"] is True
        assert kwargs["required_together"] == [["port_speed", "lanes_per_port"]]
        for pair in (
            ["speed", "port_speed"],
            ["speed", "lanes_per_port"],
            ["ports", "port_speed"],
            ["ports", "lanes_per_port"],
        ):
            assert pair in kwargs["mutually_exclusive"]
        spec = ansible_module.call_args[0][0]
        assert spec["port_speed"]["choices"] == [10, 25, 40, 50, 100, 200, 400]
        assert spec["lanes_per_port"]["choices"] == [1, 2, 4, 8]

    # ---------------- main(): identification LED ----------------

    def test_main_led_enable(self):
        """Enabling the LED PATCHes /hardware once and reports changed"""
        module = _module(name=BLADE, enabled=True)
        blade = _blade(hardware=_hardware(False))
        sdk = _run_main(module, blade)[0]
        blade.get_hardware.assert_called_once_with(names=[BLADE])
        sdk.Hardware.assert_called_once_with(identify_enabled=True)
        blade.patch_hardware.assert_called_once_with(
            names=[BLADE], hardware=sdk.Hardware.return_value
        )
        blade.get_network_interfaces_connectors.assert_not_called()
        blade.get_hardware_connectors.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_led_idempotent(self):
        """LED already in the requested state issues no PATCH"""
        module = _module(name=BLADE, enabled=True)
        blade = _blade(hardware=_hardware(True))
        _run_main(module, blade)
        blade.patch_hardware.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_main_led_check_mode(self):
        """Check mode reports the LED change without PATCHing"""
        module = _module(check_mode=True, name=BLADE, enabled=False)
        blade = _blade(hardware=_hardware(True))
        _run_main(module, blade)
        blade.patch_hardware.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_led_unknown_component_fails(self):
        """A name that is not a hardware component fails instead of no-op"""
        module = _module(name="CH9.FB9", enabled=True)
        blade = _blade(hardware=None)
        _run_main(module, blade)
        module.fail_json.assert_called_once()
        assert "does not exist" in module.fail_json.call_args[1]["msg"]
        blade.patch_hardware.assert_not_called()

    def test_main_led_patch_error_fails(self):
        """A failed LED PATCH surfaces the array error"""
        module = _module(name=BLADE, enabled=True)
        blade = _blade(hardware=_hardware(False))
        blade.patch_hardware.return_value = _response(400)
        _run_main(module, blade)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to set identification LED" in msg
        assert "boom" in msg

    # ---------------- main(): legacy connector form ----------------

    def test_main_legacy_pair_single_patch_on_network_endpoint(self):
        """speed+ports send ONE PATCH to /network-interfaces/connectors on 2.17+"""
        module = _module(speed=40, ports=4)
        blade = _blade(connector=_connector())
        sdk = _run_main(module, blade, api_version="2.30")[0]
        blade.get_hardware.assert_not_called()
        blade.get_network_interfaces_connectors.assert_called_once_with(
            names=[CONNECTOR]
        )
        sdk.HardwareConnector.assert_called_once_with(
            lane_speed=40 * GBPS, port_count=4
        )
        blade.patch_network_interfaces_connectors.assert_called_once_with(
            names=[CONNECTOR], network_connector=sdk.HardwareConnector.return_value
        )
        blade.patch_hardware_connectors.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_legacy_pair_uses_hardware_connectors_below_2_17(self):
        """Older arrays keep PATCH /hardware-connectors with hardware_connector="""
        module = _module(speed=40, ports=4)
        blade = _blade(connector=_connector())
        sdk = _run_main(module, blade, api_version="2.14")[0]
        blade.get_hardware_connectors.assert_called_once_with(names=[CONNECTOR])
        blade.get_network_interfaces_connectors.assert_not_called()
        sdk.HardwareConnector.assert_called_once_with(
            lane_speed=40 * GBPS, port_count=4
        )
        blade.patch_hardware_connectors.assert_called_once_with(
            names=[CONNECTOR], hardware_connector=sdk.HardwareConnector.return_value
        )
        blade.patch_network_interfaces_connectors.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_legacy_pair_idempotent(self):
        """Matching lane speed and port count issue no PATCH"""
        module = _module(speed=25, ports=1)
        blade = _blade(connector=_connector())
        sdk = _run_main(module, blade)[0]
        sdk.HardwareConnector.assert_not_called()
        blade.patch_network_interfaces_connectors.assert_not_called()
        blade.patch_hardware_connectors.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_main_legacy_check_mode(self):
        """Check mode reports the connector change without PATCHing"""
        module = _module(check_mode=True, speed=40)
        blade = _blade(connector=_connector())
        _run_main(module, blade)
        blade.patch_network_interfaces_connectors.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    # ---------------- main(): port_speed form ----------------

    def test_main_port_speed_pair_single_patch(self):
        """port_speed+lanes_per_port send one PATCH with both fields in bps/lanes"""
        module = _module(port_speed=400, lanes_per_port=8)
        blade = _blade(connector=_connector())
        sdk = _run_main(module, blade, api_version="2.30")[0]
        sdk.HardwareConnector.assert_called_once_with(
            port_speed=400 * GBPS, lanes_per_port=8
        )
        blade.patch_network_interfaces_connectors.assert_called_once_with(
            names=[CONNECTOR], network_connector=sdk.HardwareConnector.return_value
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_port_speed_breakout_at_2_20(self):
        """4 x 25Gb breakout at the minimum version uses the new endpoint"""
        module = _module(port_speed=25, lanes_per_port=1)
        blade = _blade(connector=_connector())
        sdk = _run_main(module, blade, api_version="2.20")[0]
        sdk.HardwareConnector.assert_called_once_with(
            port_speed=25 * GBPS, lanes_per_port=1
        )
        blade.patch_network_interfaces_connectors.assert_called_once()
        module.fail_json.assert_not_called()

    def test_main_port_speed_pair_idempotent(self):
        """Matching port speed and lanes per port issue no PATCH"""
        module = _module(port_speed=100, lanes_per_port=4)
        blade = _blade(connector=_connector())
        sdk = _run_main(module, blade)[0]
        sdk.HardwareConnector.assert_not_called()
        blade.patch_network_interfaces_connectors.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_main_port_speed_below_2_20_fails_before_any_call(self):
        """The 2.20 gate fails before the connector is read or written"""
        module = _module(port_speed=100, lanes_per_port=4)
        blade = _blade(connector=_connector())
        _run_main(module, blade, api_version="2.19")
        module.fail_json.assert_called_once()
        assert "2.20" in module.fail_json.call_args[1]["msg"]
        blade.get_network_interfaces_connectors.assert_not_called()
        blade.get_hardware_connectors.assert_not_called()
        blade.patch_network_interfaces_connectors.assert_not_called()
        blade.patch_hardware_connectors.assert_not_called()

    def test_main_port_speed_check_mode(self):
        """Check mode reports the port_speed change without PATCHing"""
        module = _module(check_mode=True, port_speed=40, lanes_per_port=4)
        blade = _blade(connector=_connector())
        _run_main(module, blade)
        blade.patch_network_interfaces_connectors.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    # ---------------- main(): connector error paths ----------------

    def test_main_connector_params_on_non_connector_fails(self):
        """Connector parameters on a component that is not a connector fail"""
        module = _module(name=BLADE, speed=25)
        blade = _blade(hardware=_hardware(), connector=None)
        _run_main(module, blade)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "is not a connector or does not exist" in msg
        assert "boom" in msg
        blade.patch_network_interfaces_connectors.assert_not_called()
        blade.patch_hardware_connectors.assert_not_called()

    def test_main_led_with_connector_params_on_non_connector_fails_before_patch(
        self,
    ):
        """enabled plus connector params on a blade fail before the LED is touched"""
        module = _module(name=BLADE, enabled=True, speed=25)
        blade = _blade(hardware=_hardware(False), connector=None)
        _run_main(module, blade)
        module.fail_json.assert_called_once()
        assert "is not a connector" in module.fail_json.call_args[1]["msg"]
        blade.get_hardware.assert_called_once_with(names=[BLADE])
        blade.patch_hardware.assert_not_called()
        blade.patch_network_interfaces_connectors.assert_not_called()
        module.exit_json.assert_not_called()

    def test_main_reads_both_objects_before_any_patch(self):
        """Both GETs happen before either PATCH when LED and connector change"""
        module = _module(enabled=True, port_speed=400, lanes_per_port=8)
        blade = _blade(hardware=_hardware(False), connector=_connector())
        sdk = _run_main(module, blade)[0]
        assert blade.mock_calls == [
            call.get_hardware(names=[CONNECTOR]),
            call.get_network_interfaces_connectors(names=[CONNECTOR]),
            call.patch_hardware(names=[CONNECTOR], hardware=sdk.Hardware.return_value),
            call.patch_network_interfaces_connectors(
                names=[CONNECTOR], network_connector=sdk.HardwareConnector.return_value
            ),
        ]
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_connector_patch_error_fails(self):
        """A failed connector PATCH surfaces the array error"""
        module = _module(port_speed=400, lanes_per_port=8)
        blade = _blade(connector=_connector())
        blade.patch_network_interfaces_connectors.return_value = _response(400)
        _run_main(module, blade)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to change connector configuration" in msg
        assert "boom" in msg

    def test_main_led_and_connector_together(self):
        """LED already set plus a connector change reports changed once"""
        module = _module(enabled=True, speed=40, ports=1)
        blade = _blade(hardware=_hardware(True), connector=_connector())
        _run_main(module, blade)
        blade.patch_hardware.assert_not_called()
        blade.patch_network_interfaces_connectors.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)
