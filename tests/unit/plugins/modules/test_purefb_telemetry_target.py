# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_telemetry_target module."""

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

from plugins.modules.purefb_telemetry_target import (
    main,
    _attribute_set,
    _context_kwargs,
    _get_target,
    _reference_name,
)

MODULE = "plugins.modules.purefb_telemetry_target"
ENDPOINT = "collector.example.com:4318/v1/metrics"


def _base_params(**overrides):
    params = {
        "name": "otel",
        "state": "present",
        "endpoint": ENDPOINT,
        "transport": "otlp-http-protobuf",
        "vendor": "generic-otlp",
        "source": "data-vip",
        "enabled": False,
        "target_api_token": None,
        "ca_certificate": None,
        "ca_certificate_group": None,
        "client_certificate": None,
        "resource_attributes": [{"key": "env", "value": "prod"}],
        "rename": None,
        "context": "",
    }
    params.update(overrides)
    return params


def _attr(key, value):
    attr = Mock(spec=["key", "value"])
    attr.key = key
    attr.value = value
    return attr


def _ref(name):
    ref = Mock(spec=["name"])
    ref.name = name
    return ref


def _existing(**overrides):
    """A target as the array returns it, matching _base_params by default."""
    target = Mock(
        spec=[
            "name",
            "enabled",
            "endpoint",
            "transport",
            "vendor",
            "source",
            "ca_certificate",
            "ca_certificate_group",
            "client_certificate",
            "api_token",
            "resource_attributes",
        ]
    )
    target.name = "otel"
    target.enabled = False
    target.endpoint = ENDPOINT
    target.transport = "otlp-http-protobuf"
    target.vendor = "generic-otlp"
    target.source = _ref("data-vip")
    # unset references come back as empty objects
    target.ca_certificate = {}
    target.ca_certificate_group = {}
    target.client_certificate = {}
    target.api_token = None
    target.resource_attributes = [_attr("env", "prod")]
    for key, value in overrides.items():
        setattr(target, key, value)
    return target


def _response(status_code=200, items=None):
    res = Mock()
    res.status_code = status_code
    res.items = items if items is not None else []
    res.errors = []
    return res


def _module(params, check_mode=False):
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.params = params
    module.check_mode = check_mode
    return module


def _run():
    try:
        main()
    except SystemExit:
        pass


class TestPurefbTelemetryTargetHelpers:
    """Helper-function unit tests"""

    def test_context_kwargs_empty_without_context(self):
        module = Mock()
        module.params = {"context": ""}
        assert _context_kwargs(module) == {}

    def test_context_kwargs_when_set(self):
        module = Mock()
        module.params = {"context": "peer1"}
        assert _context_kwargs(module) == {"context_names": ["peer1"]}

    def test_reference_name_unset_reference(self):
        target = _existing()
        assert _reference_name(target, "ca_certificate") is None
        assert _reference_name(target, "missing") is None

    def test_reference_name_set_reference(self):
        target = _existing()
        assert _reference_name(target, "source") == "data-vip"

    def test_attribute_set_is_order_insensitive(self):
        play = [{"key": "b", "value": "2"}, {"key": "a", "value": "1"}]
        array = [_attr("a", "1"), _attr("b", "2")]
        assert _attribute_set(play) == _attribute_set(array)
        assert _attribute_set(None) == set()
        assert _attribute_set([{"key": "a", "value": "x"}]) != _attribute_set(array)

    def test_get_target_returns_item(self):
        module = Mock()
        module.params = {"context": ""}
        target = _existing()
        blade = Mock()
        blade.get_telemetry_targets.return_value = _response(200, [target])
        assert _get_target(module, blade, "otel") is target
        blade.get_telemetry_targets.assert_called_once_with(names=["otel"])

    def test_get_target_passes_context(self):
        module = Mock()
        module.params = {"context": "peer1"}
        blade = Mock()
        blade.get_telemetry_targets.return_value = _response(200, [_existing()])
        _get_target(module, blade, "otel")
        blade.get_telemetry_targets.assert_called_once_with(
            names=["otel"], context_names=["peer1"]
        )

    def test_get_target_none_when_missing(self):
        module = Mock()
        module.params = {"context": ""}
        blade = Mock()
        blade.get_telemetry_targets.return_value = _response(400)
        assert _get_target(module, blade, "otel") is None
        blade.get_telemetry_targets.return_value = _response(200, [])
        assert _get_target(module, blade, "otel") is None


@patch(MODULE + ".LooseVersion")
@patch(MODULE + ".get_system")
@patch(MODULE + ".AnsibleModule")
@patch(MODULE + ".HAS_PYPURECLIENT", True)
class TestPurefbTelemetryTargetMain:
    """main() flows; the version gate passes unless a test says otherwise"""

    @staticmethod
    def _setup(
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        params,
        check_mode=False,
    ):
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(params, check_mode)
        mock_ansible_module.return_value = module
        blade = Mock()
        mock_get_system.return_value = blade
        return module, blade

    # ---------------- create ----------------

    @patch(MODULE + ".TelemetryTargetResourceAttributes")
    @patch(MODULE + ".ReferenceWritable")
    @patch(MODULE + ".TelemetryTargetPost")
    def test_create_target(
        self, mock_post_model, mock_ref, mock_attr_model, mock_am, mock_gs, mock_lv
    ):
        module, blade = self._setup(mock_am, mock_gs, mock_lv, _base_params())
        blade.get_telemetry_targets.return_value = _response(400)
        blade.post_telemetry_targets.return_value = _response(200)

        _run()

        blade.post_telemetry_targets.assert_called_once()
        call_kwargs = blade.post_telemetry_targets.call_args[1]
        assert call_kwargs["names"] == ["otel"]
        assert "context_names" not in call_kwargs
        body = mock_post_model.call_args[1]
        assert body["endpoint"] == ENDPOINT
        assert body["transport"] == "otlp-http-protobuf"
        assert body["vendor"] == "generic-otlp"
        assert body["enabled"] is False
        assert "api_token" not in body
        assert "ca_certificate" not in body
        mock_ref.assert_called_once_with(name="data-vip")
        mock_attr_model.assert_called_once_with(key="env", value="prod")
        assert len(body["resource_attributes"]) == 1
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".ReferenceWritable")
    @patch(MODULE + ".TelemetryTargetPost")
    def test_create_target_with_token_certificates_and_context(
        self, mock_post_model, mock_ref, mock_am, mock_gs, mock_lv
    ):
        params = _base_params(
            target_api_token="secret",
            ca_certificate_group="public-cas",
            client_certificate="fb-client",
            resource_attributes=None,
            context="peer1",
        )
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        blade.get_telemetry_targets.return_value = _response(400)
        blade.post_telemetry_targets.return_value = _response(200)

        _run()

        call_kwargs = blade.post_telemetry_targets.call_args[1]
        assert call_kwargs["context_names"] == ["peer1"]
        blade.get_telemetry_targets.assert_called_once_with(
            names=["otel"], context_names=["peer1"]
        )
        body = mock_post_model.call_args[1]
        assert body["api_token"] == "secret"
        assert "resource_attributes" not in body
        assert "ca_certificate" not in body
        mock_ref.assert_any_call(name="public-cas")
        mock_ref.assert_any_call(name="fb-client")
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".ReferenceWritable")
    @patch(MODULE + ".TelemetryTargetPost")
    def test_create_applies_array_defaults_for_omitted_options(
        self, mock_post_model, mock_ref, mock_am, mock_gs, mock_lv
    ):
        params = _base_params(
            transport=None,
            vendor=None,
            enabled=None,
            ca_certificate="",
            resource_attributes=None,
        )
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        blade.get_telemetry_targets.return_value = _response(400)
        blade.post_telemetry_targets.return_value = _response(200)

        _run()

        body = mock_post_model.call_args[1]
        assert body["transport"] == "otlp-http-protobuf"
        assert body["vendor"] == "generic-otlp"
        assert body["enabled"] is False
        # an empty certificate reference is not sent on create
        assert "ca_certificate" not in body
        mock_ref.assert_called_once_with(name="data-vip")
        module.exit_json.assert_called_once_with(changed=True)

    def test_create_check_mode_skips_post(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(), check_mode=True
        )
        blade.get_telemetry_targets.return_value = _response(400)

        _run()

        blade.post_telemetry_targets.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_create_requires_endpoint(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(endpoint=None)
        )
        blade.get_telemetry_targets.return_value = _response(400)

        _run()

        blade.post_telemetry_targets.assert_not_called()
        module.fail_json.assert_called_once()
        assert "endpoint is required" in module.fail_json.call_args[1]["msg"]

    def test_create_fails_on_api_error(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(mock_am, mock_gs, mock_lv, _base_params())
        blade.get_telemetry_targets.return_value = _response(400)
        blade.post_telemetry_targets.return_value = _response(400)

        _run()

        module.fail_json.assert_called_once()
        assert (
            "Failed to create telemetry target otel"
            in module.fail_json.call_args[1]["msg"]
        )

    # ---------------- update ----------------

    def test_update_idempotent(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(mock_am, mock_gs, mock_lv, _base_params())
        blade.get_telemetry_targets.return_value = _response(200, [_existing()])

        _run()

        blade.patch_telemetry_targets.assert_not_called()
        blade.post_telemetry_targets.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_update_idempotent_attribute_order(self, mock_am, mock_gs, mock_lv):
        params = _base_params(
            resource_attributes=[
                {"key": "team", "value": "ops"},
                {"key": "env", "value": "prod"},
            ]
        )
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        existing = _existing(
            resource_attributes=[_attr("env", "prod"), _attr("team", "ops")]
        )
        blade.get_telemetry_targets.return_value = _response(200, [existing])

        _run()

        blade.patch_telemetry_targets.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE + ".TelemetryTargetPatch")
    def test_update_endpoint_only_sends_changed_field(
        self, mock_patch_model, mock_am, mock_gs, mock_lv
    ):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(endpoint="new.example.com:4318")
        )
        blade.get_telemetry_targets.return_value = _response(200, [_existing()])
        blade.patch_telemetry_targets.return_value = _response(200)

        _run()

        blade.patch_telemetry_targets.assert_called_once()
        assert blade.patch_telemetry_targets.call_args[1]["names"] == ["otel"]
        mock_patch_model.assert_called_once_with(endpoint="new.example.com:4318")
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".TelemetryTargetPatch")
    def test_update_enable_recovers_disabled_target(
        self, mock_patch_model, mock_am, mock_gs, mock_lv
    ):
        # the alert 10176 recovery play: only name and enabled are given
        params = _base_params(
            endpoint=None,
            transport=None,
            vendor=None,
            source=None,
            enabled=True,
            resource_attributes=None,
        )
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        existing = _existing(
            transport="otlp-http-protobuf-without-tls", vendor="splunk"
        )
        blade.get_telemetry_targets.return_value = _response(200, [existing])
        blade.patch_telemetry_targets.return_value = _response(200)

        _run()

        mock_patch_model.assert_called_once_with(enabled=True)
        module.exit_json.assert_called_once_with(changed=True)

    def test_update_omitted_options_are_not_sent(self, mock_am, mock_gs, mock_lv):
        params = _base_params(transport=None, vendor=None, enabled=None)
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        existing = _existing(
            transport="otlp-grpc-without-tls", vendor="dynatrace", enabled=True
        )
        blade.get_telemetry_targets.return_value = _response(200, [existing])

        _run()

        blade.patch_telemetry_targets.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE + ".TelemetryTargetResourceAttributes")
    @patch(MODULE + ".TelemetryTargetPatch")
    def test_update_replaces_attribute_list(
        self, mock_patch_model, mock_attr_model, mock_am, mock_gs, mock_lv
    ):
        params = _base_params(
            resource_attributes=[
                {"key": "env", "value": "prod"},
                {"key": "team", "value": "ops"},
            ]
        )
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        blade.get_telemetry_targets.return_value = _response(200, [_existing()])
        blade.patch_telemetry_targets.return_value = _response(200)

        _run()

        body = mock_patch_model.call_args[1]
        assert list(body) == ["resource_attributes"]
        # the whole desired list is sent, not only the new pair
        assert mock_attr_model.call_count == 2
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".ReferenceWritable")
    @patch(MODULE + ".TelemetryTargetPatch")
    def test_update_sets_references(
        self, mock_patch_model, mock_ref, mock_am, mock_gs, mock_lv
    ):
        params = _base_params(source="other-vip", ca_certificate="receiver-ca")
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        blade.get_telemetry_targets.return_value = _response(200, [_existing()])
        blade.patch_telemetry_targets.return_value = _response(200)

        _run()

        body = mock_patch_model.call_args[1]
        assert sorted(body) == ["ca_certificate", "source"]
        mock_ref.assert_any_call(name="other-vip")
        mock_ref.assert_any_call(name="receiver-ca")
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".ReferenceWritable")
    @patch(MODULE + ".TelemetryTargetPatch")
    def test_update_empty_string_clears_certificate(
        self, mock_patch_model, mock_ref, mock_am, mock_gs, mock_lv
    ):
        # ca_certificate is removed; client_certificate is already unset
        params = _base_params(ca_certificate="", client_certificate="")
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        existing = _existing(ca_certificate=_ref("receiver-ca"))
        blade.get_telemetry_targets.return_value = _response(200, [existing])
        blade.patch_telemetry_targets.return_value = _response(200)

        _run()

        body = mock_patch_model.call_args[1]
        assert list(body) == ["ca_certificate"]
        mock_ref.assert_called_once_with(name="")
        module.exit_json.assert_called_once_with(changed=True)

    def test_update_empty_string_on_unset_certificate_is_noop(
        self, mock_am, mock_gs, mock_lv
    ):
        params = _base_params(ca_certificate_group="", client_certificate="")
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        blade.get_telemetry_targets.return_value = _response(200, [_existing()])

        _run()

        blade.patch_telemetry_targets.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE + ".ReferenceWritable")
    @patch(MODULE + ".TelemetryTargetPatch")
    def test_update_swaps_ca_certificate_for_group(
        self, mock_patch_model, mock_ref, mock_am, mock_gs, mock_lv
    ):
        # the array clears ca_certificate itself when a group is set
        params = _base_params(ca_certificate_group="public-cas")
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        existing = _existing(ca_certificate=_ref("receiver-ca"))
        blade.get_telemetry_targets.return_value = _response(200, [existing])
        blade.patch_telemetry_targets.return_value = _response(200)

        _run()

        body = mock_patch_model.call_args[1]
        assert list(body) == ["ca_certificate_group"]
        mock_ref.assert_called_once_with(name="public-cas")
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".TelemetryTargetPatch")
    def test_update_token_always_sent(
        self, mock_patch_model, mock_am, mock_gs, mock_lv
    ):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(target_api_token="secret")
        )
        blade.get_telemetry_targets.return_value = _response(
            200, [_existing(api_token="***")]
        )
        blade.patch_telemetry_targets.return_value = _response(200)

        _run()

        mock_patch_model.assert_called_once_with(api_token="secret")
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".TelemetryTargetPatch")
    def test_update_empty_token_clears(
        self, mock_patch_model, mock_am, mock_gs, mock_lv
    ):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(target_api_token="")
        )
        blade.get_telemetry_targets.return_value = _response(
            200, [_existing(api_token="***")]
        )
        blade.patch_telemetry_targets.return_value = _response(200)

        _run()

        mock_patch_model.assert_called_once_with(api_token="")
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".TelemetryTargetPatch")
    def test_update_rename(self, mock_patch_model, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(rename="otel-prod")
        )
        blade.get_telemetry_targets.return_value = _response(200, [_existing()])
        blade.patch_telemetry_targets.return_value = _response(200)

        _run()

        # looked up by the current name only; the PATCH addresses it too
        blade.get_telemetry_targets.assert_called_once_with(names=["otel"])
        assert blade.patch_telemetry_targets.call_args[1]["names"] == ["otel"]
        mock_patch_model.assert_called_once_with(name="otel-prod")
        module.exit_json.assert_called_once_with(changed=True)

    def test_rename_already_done_is_idempotent(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(rename="otel-prod")
        )
        blade.get_telemetry_targets.side_effect = [
            _response(400),
            _response(200, [_existing(name="otel-prod")]),
        ]

        _run()

        assert blade.get_telemetry_targets.call_count == 2
        blade.get_telemetry_targets.assert_any_call(names=["otel-prod"])
        blade.patch_telemetry_targets.assert_not_called()
        blade.post_telemetry_targets.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE + ".TelemetryTargetPatch")
    def test_rename_already_done_still_applies_other_changes(
        self, mock_patch_model, mock_am, mock_gs, mock_lv
    ):
        params = _base_params(rename="otel-prod", enabled=True)
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        blade.get_telemetry_targets.side_effect = [
            _response(400),
            _response(200, [_existing(name="otel-prod")]),
        ]
        blade.patch_telemetry_targets.return_value = _response(200)

        _run()

        assert blade.patch_telemetry_targets.call_args[1]["names"] == ["otel-prod"]
        mock_patch_model.assert_called_once_with(enabled=True)
        module.exit_json.assert_called_once_with(changed=True)

    def test_rename_missing_target_fails(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(rename="otel-prod")
        )
        blade.get_telemetry_targets.return_value = _response(400)

        _run()

        assert blade.get_telemetry_targets.call_count == 2
        blade.post_telemetry_targets.assert_not_called()
        blade.patch_telemetry_targets.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "does not exist" in msg
        assert "cannot rename" in msg

    def test_update_check_mode_skips_patch(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(enabled=True), check_mode=True
        )
        blade.get_telemetry_targets.return_value = _response(200, [_existing()])

        _run()

        blade.patch_telemetry_targets.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_update_fails_on_api_error(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(enabled=True)
        )
        blade.get_telemetry_targets.return_value = _response(200, [_existing()])
        blade.patch_telemetry_targets.return_value = _response(400)

        _run()

        module.fail_json.assert_called_once()
        assert (
            "Failed to update telemetry target otel"
            in module.fail_json.call_args[1]["msg"]
        )

    # ---------------- delete ----------------

    def test_delete_target(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(state="absent")
        )
        blade.get_telemetry_targets.return_value = _response(200, [_existing()])
        blade.delete_telemetry_targets.return_value = _response(200)

        _run()

        blade.delete_telemetry_targets.assert_called_once_with(names=["otel"])
        module.exit_json.assert_called_once_with(changed=True)

    def test_delete_missing_is_noop(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(state="absent")
        )
        blade.get_telemetry_targets.return_value = _response(400)

        _run()

        blade.delete_telemetry_targets.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_delete_check_mode_skips_call(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(state="absent"), check_mode=True
        )
        blade.get_telemetry_targets.return_value = _response(200, [_existing()])

        _run()

        blade.delete_telemetry_targets.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @patch(
        MODULE + ".get_error_message",
        return_value="Target otel is referenced by policy metrics-default.",
    )
    def test_delete_referenced_by_policy_adds_hint(
        self, mock_err, mock_am, mock_gs, mock_lv
    ):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(state="absent")
        )
        blade.get_telemetry_targets.return_value = _response(200, [_existing()])
        blade.delete_telemetry_targets.return_value = _response(400)

        _run()

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to delete telemetry target otel" in msg
        assert "referenced by policy metrics-default" in msg
        assert "Remove the target from every telemetry metrics policy" in msg

    @patch(MODULE + ".get_error_message", return_value="Context peer1 not found.")
    def test_delete_other_400_has_no_policy_hint(
        self, mock_err, mock_am, mock_gs, mock_lv
    ):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(state="absent")
        )
        blade.get_telemetry_targets.return_value = _response(200, [_existing()])
        blade.delete_telemetry_targets.return_value = _response(400)

        _run()

        msg = module.fail_json.call_args[1]["msg"]
        assert "Context peer1 not found" in msg
        assert "telemetry metrics policy" not in msg

    # ---------------- test ----------------

    def test_state_test_reports_result(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(state="test")
        )
        blade.get_telemetry_targets.return_value = _response(200, [_existing()])
        component = Mock(
            spec=[
                "component_address",
                "component_name",
                "description",
                "destination",
                "enabled",
                "result_details",
                "success",
                "test_type",
                "resource",
            ]
        )
        component.component_address = "ch1.fm1"
        component.component_name = "ch1.fm1"
        component.description = "Send a test metric"
        component.destination = ENDPOINT
        component.enabled = False
        component.result_details = ""
        component.success = True
        component.test_type = "telemetry-target"
        component.resource = _ref("otel")
        blade.get_telemetry_targets_test.return_value = _response(200, [component])

        _run()

        blade.get_telemetry_targets_test.assert_called_once_with(names=["otel"])
        module.exit_json.assert_called_once()
        kwargs = module.exit_json.call_args[1]
        assert kwargs["changed"] is False
        assert kwargs["test_response"] == [
            {
                "component_address": "ch1.fm1",
                "component_name": "ch1.fm1",
                "description": "Send a test metric",
                "destination": ENDPOINT,
                "enabled": False,
                "result_details": "",
                "success": True,
                "test_type": "telemetry-target",
                "resource_name": "otel",
            }
        ]

    def test_state_test_missing_target_fails(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(state="test")
        )
        blade.get_telemetry_targets.return_value = _response(400)

        _run()

        blade.get_telemetry_targets_test.assert_not_called()
        module.fail_json.assert_called_once()
        assert "does not exist" in module.fail_json.call_args[1]["msg"]

    def test_state_test_api_error(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(state="test")
        )
        blade.get_telemetry_targets.return_value = _response(200, [_existing()])
        blade.get_telemetry_targets_test.return_value = _response(400)

        _run()

        module.fail_json.assert_called_once()
        assert (
            "Failed to test telemetry target otel"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_state_test_rejects_context(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(state="test", context="peer1")
        )

        _run()

        mock_gs.assert_not_called()
        module.fail_json.assert_called_once()
        assert (
            "context is not supported with state=test"
            in module.fail_json.call_args[1]["msg"]
        )

    # ---------------- validation and gates ----------------

    def test_version_gate_blocks_before_any_call(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(mock_am, mock_gs, mock_lv, _base_params())
        mock_lv.return_value.__gt__ = Mock(return_value=True)

        _run()

        blade.get_telemetry_targets.assert_not_called()
        blade.post_telemetry_targets.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "REST version not supported" in msg
        assert "2.29" in msg

    def test_too_many_resource_attributes(self, mock_am, mock_gs, mock_lv):
        attrs = [{"key": "k%d" % i, "value": "v"} for i in range(11)]
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(resource_attributes=attrs)
        )

        _run()

        mock_gs.assert_not_called()
        module.fail_json.assert_called_once()
        assert "at most 10 resource attributes" in module.fail_json.call_args[1]["msg"]

    def test_endpoint_with_scheme_rejected(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(endpoint="https://collector:4318")
        )

        _run()

        mock_gs.assert_not_called()
        module.fail_json.assert_called_once()
        assert "without a scheme" in module.fail_json.call_args[1]["msg"]

    @patch(MODULE + ".purefb_argument_spec", return_value={})
    def test_mutually_exclusive_certificates_declared(
        self, mock_spec, mock_am, mock_gs, mock_lv
    ):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(state="absent")
        )
        blade.get_telemetry_targets.return_value = _response(400)

        _run()

        kwargs = mock_am.call_args[1]
        assert kwargs["supports_check_mode"] is True
        assert ["ca_certificate", "ca_certificate_group"] in kwargs[
            "mutually_exclusive"
        ]
        spec = mock_am.call_args[0][0]
        assert spec["target_api_token"]["no_log"] is True
        assert spec["resource_attributes"]["options"]["key"]["no_log"] is False
        # omitted options are left alone on an existing target
        for option in ("enabled", "transport", "vendor"):
            assert "default" not in spec[option]
        assert spec["enabled"]["type"] == "bool"
        assert "otlp-grpc-without-tls" in spec["transport"]["choices"]
        assert "datadog" in spec["vendor"]["choices"]


@patch(MODULE + ".LooseVersion")
@patch(MODULE + ".get_system")
@patch(MODULE + ".AnsibleModule")
@patch(MODULE + ".HAS_PYPURECLIENT", False)
def test_main_fails_without_sdk(mock_am, mock_gs, mock_lv):
    module = _module(_base_params())
    mock_am.return_value = module

    _run()

    mock_gs.assert_not_called()
    module.fail_json.assert_called_once()
    assert "py-pure-client" in module.fail_json.call_args[1]["msg"]
