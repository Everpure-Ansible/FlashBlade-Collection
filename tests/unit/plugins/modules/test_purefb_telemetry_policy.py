# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_telemetry_policy module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from contextlib import ExitStack
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

from plugins.modules.purefb_telemetry_policy import (
    main,
    _context_kwargs,
    _resolution_to_ms,
    _ms_to_human,
    _normalise_collection,
    _desired_rules,
    _rule_changes,
    _policy_to_dict,
)

MODULE = "plugins.modules.purefb_telemetry_policy"
ARRAY = "flashblade1"
DEVICE = "_device_perf_metrics"
FS_SPACE = "_fs_space_metrics"
BUCKET_SPACE = "_bucket_space_metrics"


def _ref(name):
    ref = Mock(spec=["name"])
    ref.name = name
    return ref


def _collection(name, default, supported):
    item = Mock(spec=["name", "default_resolution", "supported_resolutions"])
    item.name = name
    item.default_resolution = default
    item.supported_resolutions = supported
    return item


def _collections():
    return [
        _collection(DEVICE, 30000, [30000, 300000, 1800000, 7200000, 86400000]),
        _collection(FS_SPACE, 300000, [300000]),
        _collection(BUCKET_SPACE, 300000, [300000]),
    ]


def _rule(name, collection, resolution):
    rule = Mock(spec=["name", "collection", "resolution"])
    rule.name = name
    rule.collection = _ref(collection)
    rule.resolution = resolution
    return rule


def _policy(name="pol1", targets=("tgt1",), rules=None, enabled=True, version="v1"):
    policy = Mock(spec=["name", "enabled", "targets", "rules", "version"])
    policy.name = name
    policy.enabled = enabled
    policy.targets = [_ref(target) for target in targets]
    if rules is None:
        rules = [
            _rule(name + ".1", DEVICE, 30000),
            _rule(name + ".2", FS_SPACE, 300000),
        ]
    policy.rules = rules
    policy.version = version
    return policy


def _response(status=200, items=None):
    response = Mock()
    response.status_code = status
    response.items = items or []
    response.errors = []
    return response


def _member(policy_name, array=ARRAY):
    member = Mock(spec=["member", "policy"])
    member.member = _ref(array)
    member.policy = _ref(policy_name)
    return member


def _blade(policies=(), collections=None, members=(ARRAY,)):
    blade = Mock()
    blade.get_versions.return_value.items = ["2.30"]
    by_name = dict((policy.name, policy) for policy in policies)

    def get_policies(**kwargs):
        found = [by_name[name] for name in kwargs["names"] if name in by_name]
        if found:
            return _response(items=found)
        return _response(status=400)

    blade.get_telemetry_metrics_policies.side_effect = get_policies
    blade.get_telemetry_metrics_collections.return_value = _response(
        items=collections if collections is not None else _collections()
    )
    blade.get_telemetry_metrics_policies_arrays.return_value = _response(
        items=[_member("pol1", array) for array in members]
    )
    blade.get_arrays.return_value = _response(items=[_ref(ARRAY)])
    for method in (
        "post_telemetry_metrics_policies",
        "patch_telemetry_metrics_policies",
        "delete_telemetry_metrics_policies",
        "post_telemetry_metrics_policies_rules",
        "patch_telemetry_metrics_policies_rules",
        "delete_telemetry_metrics_policies_rules",
    ):
        getattr(blade, method).return_value = _response()
    return blade


def _base_params(**overrides):
    params = {
        "name": "pol1",
        "state": "present",
        "targets": None,
        "rules": None,
        "arrays": None,
        "rename": None,
        "force": False,
        "context": "",
    }
    params.update(overrides)
    return params


def _run_main(params, blade, check_mode=False, version_ok=True):
    """Run main() with AnsibleModule, get_system and LooseVersion patched."""
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.params = params
    module.check_mode = check_mode
    with ExitStack() as stack:
        stack.enter_context(patch(MODULE + ".AnsibleModule", return_value=module))
        stack.enter_context(patch(MODULE + ".get_system", return_value=blade))
        stack.enter_context(patch(MODULE + ".HAS_PYPURECLIENT", True))
        loose = stack.enter_context(patch(MODULE + ".LooseVersion"))
        loose.return_value.__gt__ = Mock(return_value=not version_ok)
        try:
            main()
        except SystemExit:
            pass
    return module


def _failing_module(params=None):
    module = Mock()
    module.fail_json = Mock(side_effect=SystemExit)
    module.params = params or _base_params()
    return module


class TestPurefbTelemetryPolicyHelpers:
    """Pure helper functions."""

    def test_context_kwargs(self):
        module = Mock()
        module.params = {"context": ""}
        assert _context_kwargs(module) == {}
        module.params = {"context": "peer1"}
        assert _context_kwargs(module) == {"context_names": ["peer1"]}

    def test_resolution_to_ms_accepts_ms_and_suffixes(self):
        assert _resolution_to_ms(30000) == 30000
        assert _resolution_to_ms("30000") == 30000
        assert _resolution_to_ms("500ms") == 500
        assert _resolution_to_ms("30s") == 30000
        assert _resolution_to_ms("5m") == 300000
        assert _resolution_to_ms(" 2H ") == 7200000
        assert _resolution_to_ms("1d") == 86400000

    def test_resolution_to_ms_rejects_garbage(self):
        for value in ("abc", "30x", "", True, "1.5m"):
            with pytest.raises(ValueError):
                _resolution_to_ms(value)

    def test_ms_to_human(self):
        assert _ms_to_human(30000) == "30000 (30s)"
        assert _ms_to_human(300000) == "300000 (5m)"
        assert _ms_to_human(1800000) == "1800000 (30m)"
        assert _ms_to_human(3600000) == "3600000 (1h)"
        assert _ms_to_human(86400000) == "86400000 (1d)"
        assert _ms_to_human(1500) == "1500"

    def test_normalise_collection_accepts_both_spellings(self):
        collections = dict((item.name, item) for item in _collections())
        assert _normalise_collection(DEVICE, collections) == DEVICE
        assert _normalise_collection("device_perf_metrics", collections) == DEVICE
        assert _normalise_collection("nope", collections) is None

    def test_desired_rules_resolves_names_and_defaults(self):
        module = _failing_module(
            _base_params(
                rules=[
                    {"collection": "device_perf_metrics", "resolution": "30s"},
                    {"collection": FS_SPACE, "resolution": None},
                ]
            )
        )
        collections = dict((item.name, item) for item in _collections())
        assert _desired_rules(module, collections) == {DEVICE: 30000, FS_SPACE: 300000}
        module.fail_json.assert_not_called()

    def test_desired_rules_unknown_collection_fails(self):
        module = _failing_module(
            _base_params(rules=[{"collection": "nothing", "resolution": None}])
        )
        collections = dict((item.name, item) for item in _collections())
        with pytest.raises(SystemExit):
            _desired_rules(module, collections)
        assert (
            "Unknown telemetry metrics collection"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_desired_rules_unsupported_resolution_fails(self):
        module = _failing_module(
            _base_params(rules=[{"collection": FS_SPACE, "resolution": "30s"}])
        )
        collections = dict((item.name, item) for item in _collections())
        with pytest.raises(SystemExit):
            _desired_rules(module, collections)
        msg = module.fail_json.call_args[1]["msg"]
        assert "not supported by collection _fs_space_metrics" in msg
        assert "300000 (5m)" in msg

    def test_desired_rules_duplicate_collection_fails(self):
        module = _failing_module(
            _base_params(
                rules=[
                    {"collection": DEVICE, "resolution": "30s"},
                    {"collection": "device_perf_metrics", "resolution": "5m"},
                ]
            )
        )
        collections = dict((item.name, item) for item in _collections())
        with pytest.raises(SystemExit):
            _desired_rules(module, collections)
        assert "more than once" in module.fail_json.call_args[1]["msg"]

    def test_desired_rules_bad_resolution_format_fails(self):
        module = _failing_module(
            _base_params(rules=[{"collection": DEVICE, "resolution": "soon"}])
        )
        collections = dict((item.name, item) for item in _collections())
        with pytest.raises(SystemExit):
            _desired_rules(module, collections)
        assert "Invalid resolution" in module.fail_json.call_args[1]["msg"]

    def test_rule_changes_diffs_by_collection(self):
        policy = _policy()
        to_delete, to_patch, to_add = _rule_changes(
            policy, {DEVICE: 300000, BUCKET_SPACE: 300000}
        )
        assert to_delete == ["pol1.2"]
        assert to_patch == [("pol1.1", 300000)]
        assert to_add == [(BUCKET_SPACE, 300000)]

    def test_rule_changes_no_diff(self):
        assert _rule_changes(_policy(), {DEVICE: 30000, FS_SPACE: 300000}) == (
            [],
            [],
            [],
        )

    def test_policy_to_dict(self):
        result = _policy_to_dict(_policy(), [ARRAY])
        assert result == {
            "name": "pol1",
            "enabled": True,
            "targets": ["tgt1"],
            "rules": [
                {"collection": DEVICE, "resolution": 30000},
                {"collection": FS_SPACE, "resolution": 300000},
            ],
            "arrays": [ARRAY],
            "version": "v1",
        }
        assert _policy_to_dict(None, []) is None


class TestPurefbTelemetryPolicyMain:
    """main() flows."""

    def test_version_gate_fails(self):
        blade = _blade()
        module = _run_main(_base_params(targets=["tgt1"]), blade, version_ok=False)
        module.fail_json.assert_called_once()
        assert "2.29" in module.fail_json.call_args[1]["msg"]
        blade.get_telemetry_metrics_collections.assert_not_called()

    def test_empty_targets_rejected(self):
        blade = _blade()
        module = _run_main(_base_params(targets=[]), blade)
        module.fail_json.assert_called_once()
        assert "cannot be empty" in module.fail_json.call_args[1]["msg"]
        blade.get_telemetry_metrics_policies.assert_not_called()

    # ---------------- create ----------------

    def test_create_policy_with_rules(self):
        blade = _blade()
        params = _base_params(
            targets=["tgt1"],
            rules=[
                {"collection": "device_perf_metrics", "resolution": "30s"},
                {"collection": FS_SPACE, "resolution": None},
            ],
        )

        def created(**kwargs):
            by_name = {"pol1": _policy()}
            found = [by_name[name] for name in kwargs["names"] if name in by_name]
            return _response(items=found) if found else _response(status=400)

        # first lookup: missing; after the POST the policy exists
        blade.get_telemetry_metrics_policies.side_effect = [
            _response(status=400),
            created(names=["pol1"]),
        ]
        module = _run_main(params, blade)

        blade.post_telemetry_metrics_policies.assert_called_once()
        post_kwargs = blade.post_telemetry_metrics_policies.call_args[1]
        assert post_kwargs["names"] == ["pol1"]
        assert post_kwargs["attach_member_array_names"] == [ARRAY]
        assert blade.post_telemetry_metrics_policies_rules.call_count == 2
        rule_kwargs = [
            call[1]
            for call in blade.post_telemetry_metrics_policies_rules.call_args_list
        ]
        assert all(kw["policy_names"] == ["pol1"] for kw in rule_kwargs)
        blade.patch_telemetry_metrics_policies.assert_not_called()
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True
        assert module.exit_json.call_args[1]["policy"]["name"] == "pol1"

    @patch(MODULE + ".TelemetryMetricsPolicyPost")
    def test_create_policy_with_arrays(self, mock_post_model):
        blade = _blade()
        blade.get_telemetry_metrics_policies.side_effect = [
            _response(status=400),
            _response(items=[_policy()]),
        ]
        params = _base_params(targets=["tgt1"], arrays=["fb-a", "fb-b"])
        module = _run_main(params, blade)

        post_kwargs = blade.post_telemetry_metrics_policies.call_args[1]
        assert post_kwargs["attach_member_array_names"] == ["fb-a", "fb-b"]
        blade.get_arrays.assert_not_called()
        # the body carries only the targets: policies are always enabled
        assert list(mock_post_model.call_args[1]) == ["targets"]
        blade.post_telemetry_metrics_policies_rules.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_default_array_lookup_uses_context(self):
        blade = _blade()
        blade.get_telemetry_metrics_policies.side_effect = [
            _response(status=400),
            _response(items=[_policy()]),
        ]
        module = _run_main(_base_params(targets=["tgt1"], context="peer1"), blade)
        blade.get_arrays.assert_called_once_with(context_names=["peer1"])
        post_kwargs = blade.post_telemetry_metrics_policies.call_args[1]
        assert post_kwargs["attach_member_array_names"] == [ARRAY]
        assert post_kwargs["context_names"] == ["peer1"]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_policy_check_mode(self):
        blade = _blade()
        params = _base_params(
            targets=["tgt1"], rules=[{"collection": DEVICE, "resolution": "30s"}]
        )
        module = _run_main(params, blade, check_mode=True)
        blade.post_telemetry_metrics_policies.assert_not_called()
        blade.post_telemetry_metrics_policies_rules.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_requires_targets(self):
        blade = _blade()
        module = _run_main(_base_params(), blade)
        module.fail_json.assert_called_once()
        assert "targets is required" in module.fail_json.call_args[1]["msg"]
        blade.post_telemetry_metrics_policies.assert_not_called()

    def test_create_validates_rules_before_posting(self):
        blade = _blade()
        params = _base_params(
            targets=["tgt1"], rules=[{"collection": FS_SPACE, "resolution": "30s"}]
        )
        module = _run_main(params, blade)
        module.fail_json.assert_called_once()
        blade.post_telemetry_metrics_policies.assert_not_called()

    def test_create_api_error(self):
        blade = _blade()
        blade.post_telemetry_metrics_policies.return_value = _response(status=400)
        module = _run_main(_base_params(targets=["tgt1"]), blade)
        module.fail_json.assert_called_once()
        assert (
            "Failed to create telemetry metrics policy"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_create_rule_api_error(self):
        blade = _blade()
        blade.post_telemetry_metrics_policies_rules.return_value = _response(status=400)
        params = _base_params(
            targets=["tgt1"], rules=[{"collection": DEVICE, "resolution": None}]
        )
        module = _run_main(params, blade)
        module.fail_json.assert_called_once()
        assert "Failed to add rule" in module.fail_json.call_args[1]["msg"]

    # ---------------- update ----------------

    def test_update_idempotent(self):
        blade = _blade(policies=[_policy()])
        params = _base_params(
            targets=["tgt1"],
            rules=[
                {"collection": "device_perf_metrics", "resolution": "30s"},
                {"collection": FS_SPACE, "resolution": "5m"},
            ],
            arrays=[ARRAY],
        )
        module = _run_main(params, blade)
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is False
        assert module.exit_json.call_args[1]["policy"]["arrays"] == [ARRAY]
        blade.patch_telemetry_metrics_policies.assert_not_called()
        blade.patch_telemetry_metrics_policies_rules.assert_not_called()
        blade.post_telemetry_metrics_policies_rules.assert_not_called()
        blade.delete_telemetry_metrics_policies_rules.assert_not_called()
        module.warn.assert_not_called()

    @patch(MODULE + ".TelemetryMetricsPolicyRulePatch")
    def test_update_resolution_patches_rule(self, mock_rule_patch):
        blade = _blade(policies=[_policy()])
        params = _base_params(
            rules=[
                {"collection": DEVICE, "resolution": "5m"},
                {"collection": FS_SPACE, "resolution": None},
            ]
        )
        module = _run_main(params, blade)
        blade.patch_telemetry_metrics_policies_rules.assert_called_once()
        assert blade.patch_telemetry_metrics_policies_rules.call_args[1]["names"] == [
            "pol1.1"
        ]
        mock_rule_patch.assert_called_once_with(resolution=300000)
        blade.post_telemetry_metrics_policies_rules.assert_not_called()
        blade.delete_telemetry_metrics_policies_rules.assert_not_called()
        blade.patch_telemetry_metrics_policies.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_adds_and_removes_rules(self):
        blade = _blade(policies=[_policy()])
        params = _base_params(
            rules=[
                {"collection": DEVICE, "resolution": "30s"},
                {"collection": "bucket_space_metrics", "resolution": None},
            ]
        )
        module = _run_main(params, blade)
        blade.delete_telemetry_metrics_policies_rules.assert_called_once_with(
            names=["pol1.2"]
        )
        blade.post_telemetry_metrics_policies_rules.assert_called_once()
        assert blade.post_telemetry_metrics_policies_rules.call_args[1][
            "policy_names"
        ] == ["pol1"]
        blade.patch_telemetry_metrics_policies_rules.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_empty_rules_removes_all(self):
        blade = _blade(policies=[_policy()])
        module = _run_main(_base_params(rules=[]), blade)
        assert blade.delete_telemetry_metrics_policies_rules.call_count == 2
        assert module.exit_json.call_args[1]["changed"] is True

    @patch(MODULE + ".TelemetryMetricsPolicyPatch")
    def test_update_targets_patches_with_version(self, mock_patch_model):
        blade = _blade(policies=[_policy()])
        module = _run_main(_base_params(targets=["tgt1", "tgt2"]), blade)
        blade.patch_telemetry_metrics_policies.assert_called_once()
        kwargs = blade.patch_telemetry_metrics_policies.call_args[1]
        assert kwargs["names"] == ["pol1"]
        assert kwargs["versions"] == ["v1"]
        assert list(mock_patch_model.call_args[1]) == ["targets"]
        assert len(mock_patch_model.call_args[1]["targets"]) == 2
        assert module.exit_json.call_args[1]["changed"] is True

    @patch(MODULE + ".TelemetryMetricsPolicyPatch")
    def test_update_rename(self, mock_patch_model):
        renamed = _policy(name="pol2")
        blade = _blade(policies=[_policy(), renamed])
        module = _run_main(_base_params(rename="pol2"), blade)
        assert mock_patch_model.call_args[1] == {"name": "pol2"}
        assert blade.patch_telemetry_metrics_policies.call_args[1]["names"] == ["pol1"]
        # the result is read back under the new name
        assert module.exit_json.call_args[1]["policy"]["name"] == "pol2"
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_rename_already_done_is_idempotent(self):
        blade = _blade(policies=[_policy(name="pol2")])
        module = _run_main(_base_params(rename="pol2"), blade)
        blade.patch_telemetry_metrics_policies.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False
        assert module.exit_json.call_args[1]["policy"]["name"] == "pol2"

    def test_rename_missing_policy_fails(self):
        blade = _blade()
        module = _run_main(_base_params(rename="pol2"), blade)
        module.fail_json.assert_called_once()
        assert "Cannot rename" in module.fail_json.call_args[1]["msg"]

    def test_update_check_mode(self):
        blade = _blade(policies=[_policy()])
        params = _base_params(
            targets=["tgt2"], rules=[{"collection": DEVICE, "resolution": "5m"}]
        )
        module = _run_main(params, blade, check_mode=True)
        blade.patch_telemetry_metrics_policies.assert_not_called()
        blade.patch_telemetry_metrics_policies_rules.assert_not_called()
        blade.delete_telemetry_metrics_policies_rules.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_rules_then_patch_refreshes_version(self):
        blade = _blade(policies=[_policy()])
        fresh = _policy(version="v2")
        blade.get_telemetry_metrics_policies.side_effect = [
            _response(items=[_policy()]),
            _response(items=[fresh]),
            _response(items=[fresh]),
        ]
        params = _base_params(
            targets=["tgt2"], rules=[{"collection": DEVICE, "resolution": "5m"}]
        )
        module = _run_main(params, blade)
        blade.delete_telemetry_metrics_policies_rules.assert_called_once()
        blade.patch_telemetry_metrics_policies_rules.assert_called_once()
        assert blade.patch_telemetry_metrics_policies.call_args[1]["versions"] == ["v2"]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_concurrent_change_hint(self):
        blade = _blade(policies=[_policy()])
        blade.patch_telemetry_metrics_policies.return_value = _response(status=412)
        module = _run_main(_base_params(targets=["tgt2"]), blade)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to update telemetry metrics policy pol1" in msg
        assert "re-run the task" in msg

    def test_update_concurrent_change_hint_on_400_message(self):
        blade = _blade(policies=[_policy()])
        blade.patch_telemetry_metrics_policies.return_value = _response(status=400)
        with patch(
            MODULE + ".get_error_message",
            return_value="rules may have been changed by other request(s)",
        ):
            module = _run_main(_base_params(targets=["tgt2"]), blade)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "changed by other request(s)" in msg
        assert "re-run the task" in msg

    def test_update_api_error_without_hint(self):
        blade = _blade(policies=[_policy()])
        blade.patch_telemetry_metrics_policies.return_value = _response(status=400)
        with patch(MODULE + ".get_error_message", return_value="Invalid body"):
            module = _run_main(_base_params(targets=["tgt2"]), blade)
        msg = module.fail_json.call_args[1]["msg"]
        assert "Invalid body" in msg
        assert "re-run" not in msg

    def test_update_builtin_requires_force(self):
        builtin = _policy(name="fs_space_metrics")
        blade = _blade(policies=[builtin])
        module = _run_main(
            _base_params(name="fs_space_metrics", targets=["tgt2"]), blade
        )
        module.fail_json.assert_called_once()
        assert "force" in module.fail_json.call_args[1]["msg"]
        blade.patch_telemetry_metrics_policies.assert_not_called()

    def test_update_builtin_with_force(self):
        builtin = _policy(name="fs_space_metrics")
        blade = _blade(policies=[builtin])
        module = _run_main(
            _base_params(name="fs_space_metrics", targets=["tgt2"], force=True), blade
        )
        blade.patch_telemetry_metrics_policies.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_builtin_unchanged_needs_no_force(self):
        builtin = _policy(name="fs_space_metrics")
        blade = _blade(policies=[builtin])
        module = _run_main(
            _base_params(name="fs_space_metrics", targets=["tgt1"]), blade
        )
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_pure1_policy_refused(self):
        pure1 = _policy(name="_internal_pure1_policy")
        blade = _blade(policies=[pure1])
        module = _run_main(
            _base_params(name="_internal_pure1_policy", targets=["tgt2"], force=True),
            blade,
        )
        module.fail_json.assert_called_once()
        assert "system-managed" in module.fail_json.call_args[1]["msg"]

    def test_update_arrays_mismatch_warns(self):
        blade = _blade(policies=[_policy()])
        module = _run_main(_base_params(arrays=["other-array"]), blade)
        module.warn.assert_called_once()
        assert "array membership" in module.warn.call_args[0][0]
        assert module.exit_json.call_args[1]["changed"] is False

    # ---------------- delete ----------------

    def test_delete_detaches_members(self):
        blade = _blade(policies=[_policy()])
        module = _run_main(_base_params(state="absent"), blade)
        blade.delete_telemetry_metrics_policies.assert_called_once_with(
            names=["pol1"], detach_member_array_names=[ARRAY]
        )
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_without_members(self):
        blade = _blade(policies=[_policy()], members=())
        module = _run_main(_base_params(state="absent"), blade)
        blade.delete_telemetry_metrics_policies.assert_called_once_with(names=["pol1"])
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_with_context(self):
        blade = _blade(policies=[_policy()])
        module = _run_main(_base_params(state="absent", context="peer1"), blade)
        kwargs = blade.delete_telemetry_metrics_policies.call_args[1]
        assert kwargs["context_names"] == ["peer1"]
        assert blade.get_telemetry_metrics_policies.call_args[1]["context_names"] == [
            "peer1"
        ]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_absent_no_change(self):
        blade = _blade()
        module = _run_main(_base_params(state="absent"), blade)
        blade.delete_telemetry_metrics_policies.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_delete_check_mode(self):
        blade = _blade(policies=[_policy()])
        module = _run_main(_base_params(state="absent"), blade, check_mode=True)
        blade.delete_telemetry_metrics_policies.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_pure1_refused(self):
        pure1 = _policy(name="_internal_pure1_policy")
        blade = _blade(policies=[pure1])
        module = _run_main(
            _base_params(name="_internal_pure1_policy", state="absent", force=True),
            blade,
        )
        module.fail_json.assert_called_once()
        blade.delete_telemetry_metrics_policies.assert_not_called()

    def test_delete_builtin_requires_force(self):
        builtin = _policy(name="device_perf_metrics")
        blade = _blade(policies=[builtin])
        module = _run_main(
            _base_params(name="device_perf_metrics", state="absent"), blade
        )
        module.fail_json.assert_called_once()
        assert "force" in module.fail_json.call_args[1]["msg"]
        blade.delete_telemetry_metrics_policies.assert_not_called()

    def test_delete_builtin_with_force(self):
        builtin = _policy(name="device_perf_metrics")
        blade = _blade(policies=[builtin])
        module = _run_main(
            _base_params(name="device_perf_metrics", state="absent", force=True), blade
        )
        blade.delete_telemetry_metrics_policies.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_api_error(self):
        blade = _blade(policies=[_policy()])
        blade.delete_telemetry_metrics_policies.return_value = _response(status=400)
        module = _run_main(_base_params(state="absent"), blade)
        module.fail_json.assert_called_once()
        assert (
            "Failed to delete telemetry metrics policy"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_members_lookup_error_fails(self):
        blade = _blade(policies=[_policy()])
        blade.get_telemetry_metrics_policies_arrays.return_value = _response(status=400)
        module = _run_main(_base_params(state="absent"), blade)
        module.fail_json.assert_called_once()
        assert "Failed to list arrays" in module.fail_json.call_args[1]["msg"]
        blade.delete_telemetry_metrics_policies.assert_not_called()

    def test_collections_lookup_error_fails(self):
        blade = _blade()
        blade.get_telemetry_metrics_collections.return_value = _response(status=400)
        module = _run_main(_base_params(targets=["tgt1"]), blade)
        module.fail_json.assert_called_once()
        assert "collections" in module.fail_json.call_args[1]["msg"]
