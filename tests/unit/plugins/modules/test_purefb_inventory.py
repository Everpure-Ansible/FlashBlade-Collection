# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_inventory module."""

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

from plugins.modules.purefb_inventory import (
    main,
    generate_hardware_dict,
    generate_connectors_dict,
    _sensor_readings,
)
from plugins.module_utils.version import LooseVersion as RealLooseVersion

MODULE = "plugins.modules.purefb_inventory"
GBPS = 1000000000


def _response(status_code=200, items=None):
    res = Mock()
    res.status_code = status_code
    res.items = items if items is not None else []
    res.errors = []
    return res


def _component(name, **attrs):
    component = Mock()
    component.name = name
    defaults = {
        "slot": 1,
        "index": 1,
        "status": "healthy",
        "serial": "SER" + name,
        "model": "MODEL",
        "speed": None,
        "temperature": None,
        "identify_enabled": False,
        "part_number": "83-0000-01",
        "details": None,
        "data_mac": None,
        "management_mac": None,
        "sensor_readings": [],
    }
    defaults.update(attrs)
    for key, value in defaults.items():
        setattr(component, key, value)
    return component


def _sensor(name, reading, status="HEALTHY", critical=70.0, non_critical=68.0):
    sensor = Mock()
    sensor.name = name
    sensor.reading = reading
    sensor.status = status
    sensor.thresholds = Mock()
    sensor.thresholds.critical = critical
    sensor.thresholds.non_critical = non_critical
    sensor.thresholds.unrecoverable = -999.0
    return sensor


def _connector(name, lanes_per_port=4):
    connector = Mock()
    connector.name = name
    connector.connector_type = "QSFP28"
    connector.lane_speed = 25 * GBPS
    connector.port_count = 1
    connector.port_speed = 100 * GBPS
    connector.transceiver_type = "AUTO"
    connector.lanes_per_port = lanes_per_port
    return connector


def _lab_components():
    return {
        "fm": [
            _component(
                "CH1.FM1",
                model="FIOM-1000",
                sensor_readings=[_sensor("m2-temp", 48.0), _sensor("t3-temp", 61.0)],
            )
        ],
        "eth": [
            _component(
                "CH1.FM1.ETH1",
                model="AOC-Q-Q-100G1MEO",
                speed=100 * GBPS,
                data_mac="24:a9:37:c6:02:cd",
                management_mac="24:a9:37:30:27:11",
            )
        ],
        "mgmt_port": [_component("CH1.FM1.ETH9", status="unused", speed=0)],
        "fan": [_component("CH1.FM1.FAN1")],
        "fb": [
            _component(
                "CH1.FB1",
                model="FB-S200",
                temperature=19,
                sensor_readings=[_sensor("Inlet", 19.0, critical=40.0)],
            )
        ],
        "pwr": [_component("CH1.PWR1", model="DPS-2400EB E")],
        "xfm": [],
        "ch": [_component("CH1", model="CH-FB-II", details="degraded link")],
        "bay": [_component("CH1.FB1.BAY1")],
    }


def _blade(components, connectors=None, connector_status=200):
    blade = Mock()

    def get_hardware(filter=None):
        hw_type = filter.split("'")[1]
        return _response(items=components.get(hw_type, []))

    blade.get_hardware.side_effect = get_hardware
    connector_items = connectors if connectors is not None else []
    blade.get_network_interfaces_connectors.return_value = _response(
        connector_status, connector_items
    )
    blade.get_hardware_connectors.return_value = _response(
        connector_status, connector_items
    )
    return blade


class TestPurefbInventory:
    """Test cases for purefb_inventory module"""

    # ---------------- helpers ----------------

    def test_sensor_readings_flattens_models(self):
        """Sensor readings become plain dicts with the threshold triple"""
        component = _component("CH1.FM1", sensor_readings=[_sensor("m2-temp", 48.0)])
        assert _sensor_readings(component) == [
            {
                "name": "m2-temp",
                "reading": 48.0,
                "status": "HEALTHY",
                "thresholds": {
                    "critical": 70.0,
                    "non_critical": 68.0,
                    "unrecoverable": -999.0,
                },
            }
        ]

    def test_sensor_readings_tolerates_missing_list_and_thresholds(self):
        """No sensor_readings attribute gives [], a sensor without thresholds gives Nones"""
        component = Mock(spec=["name"])
        assert _sensor_readings(component) == []
        sensor = Mock(spec=["name", "reading", "status"])
        sensor.name = "Location1"
        sensor.reading = 88.0
        sensor.status = "HEALTHY"
        component = _component("CH1.FM1", sensor_readings=[sensor])
        assert _sensor_readings(component)[0]["thresholds"] == {
            "critical": None,
            "non_critical": None,
            "unrecoverable": None,
        }

    # ---------------- connectors ----------------

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    def test_generate_connectors_dict_uses_network_interfaces_from_2_17(self):
        """REST 2.17+ reads /network-interfaces/connectors and 2.20+ adds lanes"""
        blade = _blade({}, connectors=[_connector("CH1.FM1.ETH1")])
        result = generate_connectors_dict(blade, "2.30")
        blade.get_network_interfaces_connectors.assert_called_once_with()
        blade.get_hardware_connectors.assert_not_called()
        assert result == {
            "CH1.FM1.ETH1": {
                "connector_type": "QSFP28",
                "lane_speed": 25 * GBPS,
                "port_count": 1,
                "port_speed": 100 * GBPS,
                "transceiver_type": "AUTO",
                "lanes_per_port": 4,
            }
        }

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    def test_generate_connectors_dict_falls_back_below_2_17_without_lanes(self):
        """REST below 2.17 reads /hardware-connectors and omits lanes_per_port"""
        blade = _blade({}, connectors=[_connector("CH1.FM1.ETH1")])
        result = generate_connectors_dict(blade, "2.16")
        blade.get_hardware_connectors.assert_called_once_with()
        blade.get_network_interfaces_connectors.assert_not_called()
        assert "lanes_per_port" not in result["CH1.FM1.ETH1"]
        assert result["CH1.FM1.ETH1"]["port_speed"] == 100 * GBPS

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    def test_generate_connectors_dict_lanes_gate_between_2_17_and_2_20(self):
        """REST 2.17-2.19 use the new endpoint but have no lanes_per_port field"""
        blade = _blade({}, connectors=[_connector("CH1.FM1.ETH1")])
        result = generate_connectors_dict(blade, "2.19")
        blade.get_network_interfaces_connectors.assert_called_once_with()
        assert "lanes_per_port" not in result["CH1.FM1.ETH1"]

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    def test_generate_connectors_dict_empty_on_error(self):
        """A failed connectors GET yields an empty dict, not an exception"""
        blade = _blade({}, connectors=[], connector_status=400)
        assert generate_connectors_dict(blade, "2.30") == {}

    # ---------------- hardware dict ----------------

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", Mock(return_value="2.30"))
    def test_generate_hardware_dict_2_30(self):
        """Current arrays report part numbers, MACs, details, sensors and connectors"""
        blade = _blade(_lab_components(), connectors=[_connector("CH1.FM1.ETH1")])
        result = generate_hardware_dict(blade)

        module_info = result["modules"]["CH1.FM1"]
        assert module_info["identify"] is False
        assert module_info["part_number"] == "83-0000-01"
        assert [s["name"] for s in module_info["sensor_readings"]] == [
            "m2-temp",
            "t3-temp",
        ]
        assert module_info["sensor_readings"][0]["thresholds"]["critical"] == 70.0

        eth = result["ethernet"]["CH1.FM1.ETH1"]
        assert eth["data_mac"] == "24:a9:37:c6:02:cd"
        assert eth["management_mac"] == "24:a9:37:30:27:11"
        assert eth["speed"] == 100 * GBPS
        assert eth["sensor_readings"] == []

        blade_info = result["blades"]["CH1.FB1"]
        assert blade_info["temperature"] == 19
        assert blade_info["sensor_readings"][0]["thresholds"]["critical"] == 40.0

        assert result["chassis"]["CH1"]["details"] == "degraded link"
        assert result["chassis"]["CH1"]["index"] == 1
        assert result["bays"]["CH1.FB1.BAY1"]["identify"] is False
        assert result["fans"]["CH1.FM1.FAN1"]["part_number"] == "83-0000-01"
        assert result["power"]["CH1.PWR1"]["model"] == "DPS-2400EB E"
        assert result["mgmt_ports"]["CH1.FM1.ETH9"]["status"] == "unused"
        assert result["switch"] == {}
        assert result["controllers"] == {}

        assert result["connectors"]["CH1.FM1.ETH1"]["lanes_per_port"] == 4
        blade.get_network_interfaces_connectors.assert_called_once_with()

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", Mock(return_value="2.16"))
    def test_generate_hardware_dict_2_16_has_macs_but_no_sensors(self):
        """REST 2.16 adds MACs; sensor readings and lanes_per_port are absent"""
        blade = _blade(_lab_components(), connectors=[_connector("CH1.FM1.ETH1")])
        result = generate_hardware_dict(blade)
        eth = result["ethernet"]["CH1.FM1.ETH1"]
        assert eth["data_mac"] == "24:a9:37:c6:02:cd"
        assert eth["part_number"] == "83-0000-01"
        assert "sensor_readings" not in eth
        assert "sensor_readings" not in result["modules"]["CH1.FM1"]
        assert "lanes_per_port" not in result["connectors"]["CH1.FM1.ETH1"]
        blade.get_hardware_connectors.assert_called_once_with()
        blade.get_network_interfaces_connectors.assert_not_called()

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", Mock(return_value="2.7"))
    def test_generate_hardware_dict_2_7_has_no_part_number_or_macs(self):
        """Old arrays keep the original keys plus details and connectors only"""
        blade = _blade(_lab_components(), connectors=[_connector("CH1.FM1.ETH1")])
        result = generate_hardware_dict(blade)
        fm = result["modules"]["CH1.FM1"]
        assert "part_number" not in fm
        assert "data_mac" not in fm
        assert "sensor_readings" not in fm
        assert fm["details"] is None
        assert set(fm) == {"slot", "status", "serial", "model", "identify", "details"}
        assert result["connectors"]["CH1.FM1.ETH1"]["connector_type"] == "QSFP28"

    # ---------------- main ----------------

    @patch(MODULE + ".LooseVersion", RealLooseVersion)
    @patch(MODULE + ".get_rest_api_version", Mock(return_value="2.30"))
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    def test_main_returns_inventory_unchanged(
        self, mock_ansible_module, mock_get_system
    ):
        """main() never reports a change and returns the inventory as purefb_info"""
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = {}
        mock_ansible_module.return_value = module
        mock_get_system.return_value = _blade(
            _lab_components(), connectors=[_connector("CH1.FM1.ETH1")]
        )

        try:
            main()
        except SystemExit:
            pass

        assert mock_ansible_module.call_args[1]["supports_check_mode"] is True
        module.exit_json.assert_called_once()
        kwargs = module.exit_json.call_args[1]
        assert kwargs["changed"] is False
        assert "CH1.FB1" in kwargs["purefb_info"]["blades"]
        assert "CH1.FM1.ETH1" in kwargs["purefb_info"]["connectors"]
