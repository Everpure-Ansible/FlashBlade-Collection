# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_bucket_lifecycle module."""

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
sys.modules[
    "ansible_collections.everpure.flashblade.plugins.module_utils.time_utils"
] = MagicMock()

from plugins.modules.purefb_bucket_lifecycle import (
    main,
    _context_kwargs,
    _current_state,
    _get_bucket,
    _get_rule,
    _tags_param,
)

DAY = 86400000
MODULE = "plugins.modules.purefb_bucket_lifecycle."


def _ms(value):
    """Real d/w conversion standing in for the mocked time_to_milliseconds."""
    unit = value[-1].lower()
    return int(value[:-1]) * (7 * DAY if unit == "w" else DAY)


def _base_params(**overrides):
    params = {
        "bucket": "bkt",
        "name": "rule1",
        "state": "present",
        "enabled": None,
        "prefix": None,
        "tags": None,
        "keep_previous_for": None,
        "keep_previous_versions_count": None,
        "keep_current_for": None,
        "keep_current_until": None,
        "abort_uploads_after": None,
        "context": "",
    }
    params.update(overrides)
    return params


def _response(status_code=200, items=None):
    response = Mock()
    response.status_code = status_code
    response.items = items if items is not None else []
    response.errors = []
    return response


def _tag(key, value):
    tag = Mock()
    tag.key = key
    tag.value = value
    return tag


def _existing_rule(**overrides):
    """A BucketLifecyclePolicyRule as the array returns it."""
    rule_filter = Mock()
    rule_filter.prefix = overrides.pop("prefix", "logs/")
    rule_filter.tags = overrides.pop("tags", [])
    rule = Mock()
    rule.name = "rule1"
    rule.filter = rule_filter
    rule.enabled = True
    rule.keep_previous_version_for = 2 * DAY
    rule.keep_previous_versions_count = 3
    rule.keep_current_version_for = None
    rule.keep_current_version_until = None
    rule.abort_incomplete_multipart_uploads_after = None
    for key, value in overrides.items():
        setattr(rule, key, value)
    return rule


def _module(params, check_mode=False):
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.warn = Mock()
    module.params = params
    module.check_mode = check_mode
    return module


def _blade(rule=None, bucket_exists=True, rule_status=200):
    blade = Mock()
    blade.get_versions.return_value.items = ["2.29", "2.30"]
    blade.get_fleets.return_value = _response(200, [])
    bucket = Mock()
    bucket.name = "bkt"
    blade.get_buckets.return_value = _response(
        200 if bucket_exists else 400, [bucket] if bucket_exists else []
    )
    blade.get_buckets_lifecycle_policies_rules.return_value = _response(
        rule_status, [rule] if rule else []
    )
    blade.post_buckets_lifecycle_policies_rules.return_value = _response(200)
    blade.patch_buckets_lifecycle_policies_rules.return_value = _response(200)
    blade.delete_buckets_lifecycle_policies_rules.return_value = _response(200)
    return blade


def _run(module, blade, loose_version_gt=False):
    """Run main() with the module-level collaborators patched."""
    with patch(MODULE + "AnsibleModule", return_value=module), patch(
        MODULE + "get_system", return_value=blade
    ), patch(MODULE + "LooseVersion") as mock_loose_version, patch(
        MODULE + "time_to_milliseconds", side_effect=_ms
    ), patch(
        MODULE + "BucketLifecyclePolicyRulePost"
    ) as mock_post, patch(
        MODULE + "BucketLifecyclePolicyRulePatch"
    ) as mock_patch, patch(
        MODULE + "BucketLifecyclePolicyRuleFilter"
    ) as mock_filter, patch(
        MODULE + "ObjectStoreTag", side_effect=lambda key, value: (key, value)
    ), patch(
        MODULE + "HAS_PYPURECLIENT", True
    ):
        mock_loose_version.return_value.__gt__ = Mock(return_value=loose_version_gt)
        mock_filter.side_effect = lambda **kwargs: kwargs
        try:
            main()
        except SystemExit:
            pass
    return mock_post, mock_patch


class TestPurefbBucketLifecycle:
    """Test cases for purefb_bucket_lifecycle module"""

    # ---------------- helper-function unit tests ----------------

    def test_context_kwargs(self):
        module = Mock()
        module.params = {"context": ""}
        assert _context_kwargs(module) == {}
        module.params = {"context": "peer1"}
        assert _context_kwargs(module) == {"context_names": ["peer1"]}

    def test_tags_param_sorted_pairs(self):
        module = Mock()
        module.params = {"tags": None}
        assert _tags_param(module) is None
        module.params = {
            "tags": [{"key": "team", "value": "ops"}, {"key": "env", "value": "dev"}]
        }
        assert _tags_param(module) == [("env", "dev"), ("team", "ops")]

    def test_current_state_normalises_unset_values(self):
        rule = _existing_rule(tags=[_tag("team", "ops"), _tag("env", "dev")])
        state = _current_state(rule)
        assert state["prefix"] == "logs/"
        assert state["tags"] == [("env", "dev"), ("team", "ops")]
        assert state["keep_previous_version_for"] == 2 * DAY
        assert state["keep_previous_versions_count"] == 3
        assert state["keep_current_version_for"] == 0
        assert state["keep_current_version_until"] == 0
        assert state["abort_incomplete_multipart_uploads_after"] == 0
        assert state["enabled"] is True

    def test_current_state_without_filter(self):
        rule = _existing_rule()
        rule.filter = None
        state = _current_state(rule)
        assert state["prefix"] is None
        assert state["tags"] == []

    def test_get_rule_returns_item_or_none(self):
        module = _module(_base_params())
        blade = Mock()
        rule = _existing_rule()
        blade.get_buckets_lifecycle_policies_rules.return_value = _response(200, [rule])
        assert _get_rule(module, blade) is rule
        blade.get_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=["bkt"], names=["rule1"]
        )
        blade.get_buckets_lifecycle_policies_rules.return_value = _response(200, [])
        assert _get_rule(module, blade) is None

    def test_get_rule_fails_on_api_error(self):
        module = _module(_base_params())
        blade = Mock()
        blade.get_buckets_lifecycle_policies_rules.return_value = _response(400)
        try:
            _get_rule(module, blade)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "Failed to read lifecycle rule" in module.fail_json.call_args[1]["msg"]

    def test_get_rule_passes_context(self):
        module = _module(_base_params(context="peer1"))
        blade = Mock()
        blade.get_buckets_lifecycle_policies_rules.return_value = _response(200, [])
        _get_rule(module, blade)
        blade.get_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=["bkt"], names=["rule1"], context_names=["peer1"]
        )

    # ---------------- create ----------------

    def test_create_rule_with_prefix_and_durations(self):
        module = _module(
            _base_params(
                prefix="logs/",
                keep_previous_for="2d",
                keep_previous_versions_count=3,
                keep_current_for="30d",
                abort_uploads_after="1w",
            )
        )
        blade = _blade()
        mock_post, mock_patch = _run(module, blade)

        mock_post.assert_called_once_with(
            keep_previous_version_for=2 * DAY,
            keep_current_version_for=30 * DAY,
            abort_incomplete_multipart_uploads_after=7 * DAY,
            keep_previous_versions_count=3,
            filter={"prefix": "logs/"},
        )
        blade.post_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=["bkt"], names=["rule1"], rule=mock_post.return_value
        )
        blade.patch_buckets_lifecycle_policies_rules.assert_not_called()
        mock_patch.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_rule_with_tags(self):
        module = _module(
            _base_params(
                tags=[{"key": "team", "value": "ops"}, {"key": "env", "value": "dev"}],
                keep_previous_for="1d",
            )
        )
        blade = _blade()
        mock_post, dummy = _run(module, blade)

        mock_post.assert_called_once_with(
            keep_previous_version_for=DAY,
            filter={"tags": [("env", "dev"), ("team", "ops")]},
        )
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_rule_with_until_confirms_date(self):
        module = _module(_base_params(keep_current_until="2030-01-01"))
        blade = _blade()
        mock_post, dummy = _run(module, blade)

        mock_post.assert_called_once_with(keep_current_version_until=1893456000000)
        blade.post_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=["bkt"],
            names=["rule1"],
            rule=mock_post.return_value,
            confirm_date=True,
        )
        module.warn.assert_not_called()

    def test_create_rule_past_date_warns(self):
        module = _module(_base_params(keep_current_until="2001-01-01"))
        blade = _blade()
        _run(module, blade)
        module.warn.assert_called_once()
        blade.post_buckets_lifecycle_policies_rules.assert_called_once()

    def test_create_rule_bad_date_fails(self):
        module = _module(_base_params(keep_current_until="01/01/2030"))
        blade = _blade()
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert "YYYY-MM-DD" in module.fail_json.call_args[1]["msg"]
        blade.post_buckets_lifecycle_policies_rules.assert_not_called()

    def test_create_disabled_rule_posts_then_patches(self):
        module = _module(_base_params(keep_previous_for="2d", enabled=False))
        blade = _blade()
        mock_post, mock_patch = _run(module, blade)

        mock_post.assert_called_once_with(keep_previous_version_for=2 * DAY)
        mock_patch.assert_called_once_with(enabled=False)
        blade.patch_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=["bkt"], names=["rule1"], rule=mock_patch.return_value
        )
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_disabled_rule_patch_failure_fails(self):
        module = _module(_base_params(keep_previous_for="2d", enabled=False))
        blade = _blade()
        blade.patch_buckets_lifecycle_policies_rules.return_value = _response(400)
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert "could not be disabled" in module.fail_json.call_args[1]["msg"]

    def test_create_rule_check_mode_skips_post(self):
        module = _module(_base_params(keep_previous_for="2d"), check_mode=True)
        blade = _blade()
        _run(module, blade)
        blade.post_buckets_lifecycle_policies_rules.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_rule_without_retention_fails(self):
        module = _module(_base_params(prefix="logs/"))
        blade = _blade()
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert "At least one of" in module.fail_json.call_args[1]["msg"]
        blade.post_buckets_lifecycle_policies_rules.assert_not_called()

    def test_create_rule_api_error_fails(self):
        module = _module(_base_params(keep_previous_for="2d"))
        blade = _blade()
        blade.post_buckets_lifecycle_policies_rules.return_value = _response(400)
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert "Failed to create lifecycle rule" in module.fail_json.call_args[1]["msg"]

    def test_create_rule_with_context(self):
        module = _module(_base_params(keep_previous_for="2d", context="peer1"))
        blade = _blade()
        mock_post, dummy = _run(module, blade)
        blade.get_buckets.assert_called_once_with(
            names=["bkt"], context_names=["peer1"]
        )
        blade.post_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=["bkt"],
            names=["rule1"],
            rule=mock_post.return_value,
            context_names=["peer1"],
        )

    # ---------------- update ----------------

    def test_update_sends_only_changed_duration(self):
        module = _module(
            _base_params(
                prefix="logs/", keep_previous_for="3d", keep_previous_versions_count=3
            )
        )
        blade = _blade(rule=_existing_rule())
        dummy, mock_patch = _run(module, blade)

        mock_patch.assert_called_once_with(keep_previous_version_for=3 * DAY)
        blade.patch_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=["bkt"], names=["rule1"], rule=mock_patch.return_value
        )
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_idempotent_when_nothing_differs(self):
        module = _module(
            _base_params(
                prefix="logs/",
                keep_previous_for="2d",
                keep_previous_versions_count=3,
                tags=[{"key": "team", "value": "ops"}, {"key": "env", "value": "dev"}],
            )
        )
        rule = _existing_rule(tags=[_tag("env", "dev"), _tag("team", "ops")])
        blade = _blade(rule=rule)
        dummy, mock_patch = _run(module, blade)

        mock_patch.assert_not_called()
        blade.patch_buckets_lifecycle_policies_rules.assert_not_called()
        blade.post_buckets_lifecycle_policies_rules.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_omitted_options_leave_rule_unchanged(self):
        module = _module(_base_params())
        blade = _blade(rule=_existing_rule(tags=[_tag("env", "dev")]))
        dummy, mock_patch = _run(module, blade)
        mock_patch.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_tags_resends_whole_filter(self):
        module = _module(_base_params(tags=[{"key": "env", "value": "prod"}]))
        blade = _blade(rule=_existing_rule(tags=[_tag("env", "dev")]))
        dummy, mock_patch = _run(module, blade)

        mock_patch.assert_called_once_with(
            filter={"prefix": "logs/", "tags": [("env", "prod")]}
        )
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_prefix_preserves_tags(self):
        module = _module(_base_params(prefix="archive/"))
        blade = _blade(rule=_existing_rule(tags=[_tag("env", "dev")]))
        dummy, mock_patch = _run(module, blade)

        mock_patch.assert_called_once_with(
            filter={"prefix": "archive/", "tags": [("env", "dev")]}
        )

    def test_update_clear_tags_sends_empty_list(self):
        module = _module(_base_params(tags=[]))
        blade = _blade(rule=_existing_rule(tags=[_tag("env", "dev")]))
        dummy, mock_patch = _run(module, blade)

        mock_patch.assert_called_once_with(filter={"prefix": "logs/", "tags": []})

    def test_update_disable_rule(self):
        module = _module(_base_params(enabled=False))
        blade = _blade(rule=_existing_rule())
        dummy, mock_patch = _run(module, blade)

        mock_patch.assert_called_once_with(enabled=False)
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_omitted_enabled_keeps_disabled_rule_disabled(self):
        module = _module(_base_params(prefix="archive/"))
        blade = _blade(rule=_existing_rule(enabled=False))
        dummy, mock_patch = _run(module, blade)

        mock_patch.assert_called_once_with(filter={"prefix": "archive/"})
        assert "enabled" not in mock_patch.call_args[1]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_omitted_enabled_on_disabled_rule_is_noop(self):
        module = _module(_base_params())
        blade = _blade(rule=_existing_rule(enabled=False))
        dummy, mock_patch = _run(module, blade)
        mock_patch.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_enable_rule_explicitly(self):
        module = _module(_base_params(enabled=True))
        blade = _blade(rule=_existing_rule(enabled=False))
        dummy, mock_patch = _run(module, blade)

        mock_patch.assert_called_once_with(enabled=True)
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_enabled_true_on_enabled_rule_is_noop(self):
        module = _module(_base_params(enabled=True))
        blade = _blade(rule=_existing_rule())
        dummy, mock_patch = _run(module, blade)
        mock_patch.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_create_rule_enabled_true_does_not_patch(self):
        module = _module(_base_params(keep_previous_for="2d", enabled=True))
        blade = _blade()
        mock_post, mock_patch = _run(module, blade)
        mock_post.assert_called_once_with(keep_previous_version_for=2 * DAY)
        mock_patch.assert_not_called()
        blade.patch_buckets_lifecycle_policies_rules.assert_not_called()

    def test_update_until_confirms_date(self):
        module = _module(_base_params(keep_current_until="2030-01-01"))
        blade = _blade(rule=_existing_rule())
        dummy, mock_patch = _run(module, blade)

        mock_patch.assert_called_once_with(keep_current_version_until=1893456000000)
        blade.patch_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=["bkt"],
            names=["rule1"],
            rule=mock_patch.return_value,
            confirm_date=True,
        )

    def test_update_until_idempotent(self):
        module = _module(_base_params(keep_current_until="2030-01-01"))
        blade = _blade(rule=_existing_rule(keep_current_version_until=1893456000000))
        dummy, mock_patch = _run(module, blade)
        mock_patch.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_count_changed(self):
        module = _module(
            _base_params(keep_previous_for="2d", keep_previous_versions_count=5)
        )
        blade = _blade(rule=_existing_rule())
        dummy, mock_patch = _run(module, blade)
        mock_patch.assert_called_once_with(keep_previous_versions_count=5)

    def test_update_check_mode_skips_patch(self):
        module = _module(_base_params(enabled=False), check_mode=True)
        blade = _blade(rule=_existing_rule())
        _run(module, blade)
        blade.patch_buckets_lifecycle_policies_rules.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_api_error_fails(self):
        module = _module(_base_params(enabled=False))
        blade = _blade(rule=_existing_rule())
        blade.patch_buckets_lifecycle_policies_rules.return_value = _response(400)
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert "Failed to update lifecycle rule" in module.fail_json.call_args[1]["msg"]

    # ---------------- delete ----------------

    def test_delete_rule(self):
        module = _module(_base_params(state="absent"))
        blade = _blade(rule=_existing_rule())
        _run(module, blade)
        blade.delete_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=["bkt"], names=["rule1"]
        )
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_missing_rule_is_noop(self):
        module = _module(_base_params(state="absent"))
        blade = _blade()
        _run(module, blade)
        blade.delete_buckets_lifecycle_policies_rules.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_delete_check_mode_skips_call(self):
        module = _module(_base_params(state="absent"), check_mode=True)
        blade = _blade(rule=_existing_rule())
        _run(module, blade)
        blade.delete_buckets_lifecycle_policies_rules.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_api_error_fails(self):
        module = _module(_base_params(state="absent"))
        blade = _blade(rule=_existing_rule())
        blade.delete_buckets_lifecycle_policies_rules.return_value = _response(400)
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert "Failed to delete lifecycle rule" in module.fail_json.call_args[1]["msg"]

    # ---------------- guards ----------------

    def test_fails_on_unsupported_api_version(self):
        module = _module(_base_params(keep_previous_for="2d"))
        blade = _blade()
        blade.get_versions.return_value.items = ["2.17", "2.28"]
        _run(module, blade, loose_version_gt=True)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "REST version not supported" in msg
        assert "purefb_lifecycle" in msg
        blade.get_buckets.assert_not_called()
        blade.post_buckets_lifecycle_policies_rules.assert_not_called()

    def test_fails_when_bucket_missing(self):
        module = _module(_base_params(keep_previous_for="2d"))
        blade = _blade(bucket_exists=False)
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert "does not exist" in module.fail_json.call_args[1]["msg"]
        blade.get_buckets_lifecycle_policies_rules.assert_not_called()

    def test_fails_on_bad_duration_suffix(self):
        module = _module(_base_params(keep_previous_for="2h"))
        blade = _blade()
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert "keep_previous_for" in module.fail_json.call_args[1]["msg"]

    def test_fails_on_too_many_tags(self):
        tags = [{"key": "k{0}".format(i), "value": "v"} for i in range(11)]
        module = _module(_base_params(tags=tags, keep_previous_for="2d"))
        blade = _blade()
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert "At most 10 tags" in module.fail_json.call_args[1]["msg"]

    def test_fails_on_tag_key_length(self):
        for key in ["", "k" * 129]:
            module = _module(
                _base_params(tags=[{"key": key, "value": "v"}], keep_previous_for="2d")
            )
            blade = _blade()
            _run(module, blade)
            module.fail_json.assert_called_once()
            assert "1 to 128" in module.fail_json.call_args[1]["msg"]
            blade.post_buckets_lifecycle_policies_rules.assert_not_called()

    def test_tag_key_of_max_length_is_accepted(self):
        module = _module(
            _base_params(
                tags=[{"key": "k" * 128, "value": "v"}], keep_previous_for="2d"
            )
        )
        blade = _blade()
        _run(module, blade)
        module.fail_json.assert_not_called()
        blade.post_buckets_lifecycle_policies_rules.assert_called_once()

    def test_fails_on_tags_with_abort(self):
        module = _module(
            _base_params(
                tags=[{"key": "env", "value": "dev"}],
                abort_uploads_after="1d",
                keep_previous_for="2d",
            )
        )
        blade = _blade()
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert "abort_uploads_after" in module.fail_json.call_args[1]["msg"]
        blade.post_buckets_lifecycle_policies_rules.assert_not_called()

    def test_tags_with_zero_abort_allowed(self):
        module = _module(
            _base_params(
                tags=[{"key": "env", "value": "dev"}],
                abort_uploads_after="0d",
                keep_previous_for="2d",
            )
        )
        blade = _blade()
        mock_post, dummy = _run(module, blade)
        module.fail_json.assert_not_called()
        mock_post.assert_called_once_with(
            keep_previous_version_for=2 * DAY, filter={"tags": [("env", "dev")]}
        )

    # ---------------- tags and an upload abort on an existing rule ----------------

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("tags", [None, []])
    def test_abort_on_a_tagged_rule_fails_before_any_write(self, tags, check_mode):
        """The array judges the abort by the tags the rule has, also when the
        same request removes them; check mode must not report a change"""
        module = _module(
            _base_params(tags=tags, abort_uploads_after="1d"), check_mode=check_mode
        )
        blade = _blade(rule=_existing_rule(tags=[_tag("env", "dev")]))
        dummy, mock_patch = _run(module, blade)

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert msg.startswith(
            "abort_uploads_after cannot be set on lifecycle rule rule1 for "
            "bucket bkt while the rule has tags"
        )
        assert "separate task" in msg
        module.exit_json.assert_not_called()
        mock_patch.assert_not_called()
        blade.patch_buckets_lifecycle_policies_rules.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_tags_on_a_rule_with_an_abort_fail_before_any_write(self, check_mode):
        module = _module(
            _base_params(tags=[{"key": "env", "value": "dev"}]), check_mode=check_mode
        )
        blade = _blade(
            rule=_existing_rule(abort_incomplete_multipart_uploads_after=DAY)
        )
        dummy, mock_patch = _run(module, blade)

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert msg.startswith(
            "tags cannot be set on lifecycle rule rule1 for bucket bkt while "
            "the rule has abort_uploads_after set"
        )
        assert "abort_uploads_after to 0d in the same task" in msg
        module.exit_json.assert_not_called()
        mock_patch.assert_not_called()
        blade.patch_buckets_lifecycle_policies_rules.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_tags_replace_the_abort_in_one_task(self, check_mode):
        """Removing the abort and adding tags in one request is accepted"""
        module = _module(
            _base_params(
                tags=[{"key": "env", "value": "dev"}], abort_uploads_after="0d"
            ),
            check_mode=check_mode,
        )
        blade = _blade(
            rule=_existing_rule(abort_incomplete_multipart_uploads_after=DAY)
        )
        dummy, mock_patch = _run(module, blade)

        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True
        if check_mode:
            blade.patch_buckets_lifecycle_policies_rules.assert_not_called()
        else:
            mock_patch.assert_called_once_with(
                abort_incomplete_multipart_uploads_after=0,
                filter={"prefix": "logs/", "tags": [("env", "dev")]},
            )

    @pytest.mark.parametrize(
        "rule_tags, rule_abort, params",
        [
            # a tagged rule: nothing to remove, the tags it has, both
            ([("env", "dev")], None, {"abort_uploads_after": "0d"}),
            ([("env", "dev")], None, {"tags": [{"key": "env", "value": "dev"}]}),
            (
                [("env", "dev")],
                None,
                {"tags": [{"key": "env", "value": "dev"}], "abort_uploads_after": "0d"},
            ),
            # a rule with an abort: the abort it has, no tags, both
            ([], DAY, {"abort_uploads_after": "1d"}),
            ([], DAY, {"tags": []}),
            ([], DAY, {"tags": [], "abort_uploads_after": "1d"}),
            # a rule holding both, however it came to be: its own values
            ([("env", "dev")], DAY, {"abort_uploads_after": "1d"}),
            ([("env", "dev")], DAY, {"tags": [{"key": "env", "value": "dev"}]}),
        ],
    )
    @pytest.mark.parametrize("check_mode", [False, True])
    def test_rule_as_it_stands_is_never_refused(
        self, rule_tags, rule_abort, params, check_mode
    ):
        module = _module(_base_params(**params), check_mode=check_mode)
        rule = _existing_rule(
            tags=[_tag(key, value) for key, value in rule_tags],
            abort_incomplete_multipart_uploads_after=rule_abort,
        )
        blade = _blade(rule=rule)
        dummy, mock_patch = _run(module, blade)

        module.fail_json.assert_not_called()
        mock_patch.assert_not_called()
        blade.patch_buckets_lifecycle_policies_rules.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_abort_changed_on_a_rule_without_tags(self):
        module = _module(_base_params(abort_uploads_after="2d"))
        blade = _blade(
            rule=_existing_rule(abort_incomplete_multipart_uploads_after=DAY)
        )
        dummy, mock_patch = _run(module, blade)

        module.fail_json.assert_not_called()
        mock_patch.assert_called_once_with(
            abort_incomplete_multipart_uploads_after=2 * DAY
        )
        assert module.exit_json.call_args[1]["changed"] is True

    def test_other_settings_of_a_tagged_rule_can_change(self):
        module = _module(_base_params(keep_previous_for="3d", enabled=False))
        blade = _blade(rule=_existing_rule(tags=[_tag("env", "dev")]))
        dummy, mock_patch = _run(module, blade)

        module.fail_json.assert_not_called()
        mock_patch.assert_called_once_with(
            keep_previous_version_for=3 * DAY, enabled=False
        )
        assert module.exit_json.call_args[1]["changed"] is True

    def test_fails_on_duplicate_tag_keys(self):
        tags = [{"key": "env", "value": "a"}, {"key": "env", "value": "b"}]
        module = _module(_base_params(tags=tags, keep_previous_for="2d"))
        blade = _blade()
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert "unique" in module.fail_json.call_args[1]["msg"]

    def test_fails_on_count_out_of_range(self):
        module = _module(
            _base_params(keep_previous_for="2d", keep_previous_versions_count=101)
        )
        blade = _blade()
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert "between 1 and 100" in module.fail_json.call_args[1]["msg"]

    def test_fails_on_long_prefix(self):
        module = _module(_base_params(prefix="x" * 1025, keep_previous_for="2d"))
        blade = _blade()
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert "prefix" in module.fail_json.call_args[1]["msg"]

    def test_fails_without_sdk(self):
        module = _module(_base_params(keep_previous_for="2d"))
        with patch(MODULE + "AnsibleModule", return_value=module), patch(
            MODULE + "HAS_PYPURECLIENT", False
        ):
            try:
                main()
            except SystemExit:
                pass
        module.fail_json.assert_called_once()
        assert "py-pure-client" in module.fail_json.call_args[1]["msg"]

    def test_fleet_member_defaults_context_to_local_array(self):
        module = _module(_base_params(keep_previous_for="2d"))
        blade = _blade()
        blade.get_fleets.return_value = _response(200, [Mock()])
        local_array = Mock()
        local_array.name = "local-fb"
        blade.get_arrays.return_value.items = [local_array]
        _run(module, blade)
        assert module.params["context"] == "local-fb"
        blade.post_buckets_lifecycle_policies_rules.assert_called_once()
        assert blade.post_buckets_lifecycle_policies_rules.call_args[1][
            "context_names"
        ] == ["local-fb"]

    # ---------------- clearing and switching ----------------

    def test_update_clear_prefix_sends_empty_string(self):
        module = _module(_base_params(prefix=""))
        blade = _blade(rule=_existing_rule())
        dummy, mock_patch = _run(module, blade)
        mock_patch.assert_called_once_with(filter={"prefix": ""})
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_empty_prefix_on_rule_without_prefix_is_noop(self):
        module = _module(_base_params(prefix=""))
        blade = _blade(rule=_existing_rule(prefix=None))
        dummy, mock_patch = _run(module, blade)
        mock_patch.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_zero_duration_clears_it(self):
        module = _module(_base_params(abort_uploads_after="0d"))
        blade = _blade(
            rule=_existing_rule(abort_incomplete_multipart_uploads_after=DAY)
        )
        dummy, mock_patch = _run(module, blade)
        mock_patch.assert_called_once_with(abort_incomplete_multipart_uploads_after=0)

    def test_update_zero_duration_on_unset_is_noop(self):
        module = _module(_base_params(abort_uploads_after="0d"))
        blade = _blade(rule=_existing_rule())
        dummy, mock_patch = _run(module, blade)
        mock_patch.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_for_replaces_until(self):
        module = _module(_base_params(keep_current_for="45d"))
        blade = _blade(rule=_existing_rule(keep_current_version_until=1893456000000))
        dummy, mock_patch = _run(module, blade)
        mock_patch.assert_called_once_with(
            keep_current_version_for=45 * DAY, keep_current_version_until=0
        )
        blade.patch_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=["bkt"], names=["rule1"], rule=mock_patch.return_value
        )

    def test_update_until_replaces_for(self):
        module = _module(_base_params(keep_current_until="2030-01-01"))
        blade = _blade(rule=_existing_rule(keep_current_version_for=30 * DAY))
        dummy, mock_patch = _run(module, blade)
        mock_patch.assert_called_once_with(
            keep_current_version_until=1893456000000, keep_current_version_for=0
        )
        assert (
            blade.patch_buckets_lifecycle_policies_rules.call_args[1]["confirm_date"]
            is True
        )

    def test_create_zero_duration_is_not_sent(self):
        module = _module(_base_params(keep_previous_for="2d", abort_uploads_after="0d"))
        blade = _blade()
        mock_post, dummy = _run(module, blade)
        mock_post.assert_called_once_with(keep_previous_version_for=2 * DAY)

    def test_tags_allowed_with_keep_current_for(self):
        module = _module(
            _base_params(tags=[{"key": "env", "value": "dev"}], keep_current_for="10d")
        )
        blade = _blade()
        mock_post, dummy = _run(module, blade)
        mock_post.assert_called_once_with(
            keep_current_version_for=10 * DAY, filter={"tags": [("env", "dev")]}
        )
        module.fail_json.assert_not_called()


# ---------------- buckets in a realm ----------------

REALM_BUCKET = "realm1::bkt"
OTHER_REALM_BUCKET = "realm2::bkt"
BOTH_BUCKETS = ["bkt", REALM_BUCKET]
# (the bucket a task names, another bucket with the same leaf name): outside and
# inside a realm in both directions, and in two realms
NAMESAKES = [
    ("bkt", REALM_BUCKET),
    (REALM_BUCKET, "bkt"),
    (REALM_BUCKET, OTHER_REALM_BUCKET),
]


def _array(buckets):
    """A blade that resolves bucket names the way the array does.

    ``buckets`` maps the name of each bucket the array holds to its rules by
    rule name. A bucket in a realm is named realm::bucket and answers to that
    name only, so "bkt", "realm1::bkt" and "realm2::bkt" are three buckets.
    A lookup of a name the array does not hold answers 400, whether the name
    is unknown, in a realm that does not exist, or the bare name of a bucket
    that lives in a realm. A rule name the bucket does not have answers 200
    with no items. Without names, every bucket is listed. A rule call on a
    bucket the array does not hold is refused here as the REST reference
    describes; the module never sends one, it stops at the bucket lookup.
    """
    blade = Mock()
    blade.get_versions.return_value.items = ["2.29", "2.30"]
    blade.get_fleets.return_value = _response(200, [])

    def get_buckets(names=None, **kwargs):
        if names is None:
            names = list(buckets)
        if any(name not in buckets for name in names):
            return _response(400)
        items = []
        for name in names:
            bucket = Mock()
            bucket.name = name
            items.append(bucket)
        return _response(200, items)

    def get_rules(bucket_names, names, **kwargs):
        if bucket_names[0] not in buckets:
            return _response(400)
        rules = buckets[bucket_names[0]]
        return _response(200, [rules[name] for name in names if name in rules])

    def write_rule(bucket_names, **kwargs):
        return _response(200 if bucket_names[0] in buckets else 400)

    blade.get_buckets = Mock(side_effect=get_buckets)
    blade.get_buckets_lifecycle_policies_rules = Mock(side_effect=get_rules)
    blade.post_buckets_lifecycle_policies_rules = Mock(side_effect=write_rule)
    blade.patch_buckets_lifecycle_policies_rules = Mock(side_effect=write_rule)
    blade.delete_buckets_lifecycle_policies_rules = Mock(side_effect=write_rule)
    return blade


def _bucket_names_sent(blade):
    """Every bucket name the module sent to the array, whatever the call."""
    sent = set()
    for call in blade.get_buckets.call_args_list:
        sent.update(call[1].get("names") or ["<every bucket>"])
    for method in (
        blade.get_buckets_lifecycle_policies_rules,
        blade.post_buckets_lifecycle_policies_rules,
        blade.patch_buckets_lifecycle_policies_rules,
        blade.delete_buckets_lifecycle_policies_rules,
    ):
        for call in method.call_args_list:
            sent.update(call[1]["bucket_names"])
    return sent


def _no_rule_written(blade):
    return not (
        blade.post_buckets_lifecycle_policies_rules.called
        or blade.patch_buckets_lifecycle_policies_rules.called
        or blade.delete_buckets_lifecycle_policies_rules.called
    )


class TestPurefbBucketLifecycleRealmBucket:
    """A bucket in a realm is addressed by its full name, realm::bucket"""

    # ---------------- lookups ----------------

    @pytest.mark.parametrize("bucket", BOTH_BUCKETS)
    def test_get_bucket_sends_the_name_as_given(self, bucket):
        module = _module(_base_params(bucket=bucket))
        blade = _array({"bkt": {}, REALM_BUCKET: {}})
        assert _get_bucket(module, blade).name == bucket
        blade.get_buckets.assert_called_once_with(names=[bucket])

    @pytest.mark.parametrize("bucket", ["bkt", "zznorealm::bkt", "realm1::other"])
    def test_get_bucket_never_falls_back_to_another_name(self, bucket):
        module = _module(_base_params(bucket=bucket))
        blade = _array({REALM_BUCKET: {}})
        assert _get_bucket(module, blade) is None
        blade.get_buckets.assert_called_once_with(names=[bucket])

    def test_get_rule_addresses_the_realm_bucket(self):
        module = _module(_base_params(bucket=REALM_BUCKET))
        rule = _existing_rule()
        blade = _array({"bkt": {}, REALM_BUCKET: {"rule1": rule}})
        assert _get_rule(module, blade) is rule
        blade.get_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=[REALM_BUCKET], names=["rule1"]
        )

    def test_get_rule_of_realm_bucket_passes_context(self):
        module = _module(_base_params(bucket=REALM_BUCKET, context="peer1"))
        blade = _array({REALM_BUCKET: {}})
        assert _get_rule(module, blade) is None
        blade.get_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=[REALM_BUCKET], names=["rule1"], context_names=["peer1"]
        )

    # ---------------- create ----------------

    @pytest.mark.parametrize("bucket", BOTH_BUCKETS)
    def test_create_sends_the_bucket_name_unchanged(self, bucket):
        module = _module(
            _base_params(
                bucket=bucket,
                prefix="logs/",
                keep_previous_for="2d",
                keep_previous_versions_count=3,
            )
        )
        blade = _array({"bkt": {}, REALM_BUCKET: {}})
        mock_post, dummy = _run(module, blade)

        blade.get_buckets.assert_called_once_with(names=[bucket])
        blade.get_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=[bucket], names=["rule1"]
        )
        mock_post.assert_called_once_with(
            keep_previous_version_for=2 * DAY,
            keep_previous_versions_count=3,
            filter={"prefix": "logs/"},
        )
        blade.post_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=[bucket], names=["rule1"], rule=mock_post.return_value
        )
        blade.patch_buckets_lifecycle_policies_rules.assert_not_called()
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_on_realm_bucket_with_date_confirms_date(self):
        module = _module(
            _base_params(bucket=REALM_BUCKET, keep_current_until="2030-01-01")
        )
        blade = _array({REALM_BUCKET: {}})
        mock_post, dummy = _run(module, blade)

        mock_post.assert_called_once_with(keep_current_version_until=1893456000000)
        blade.post_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=[REALM_BUCKET],
            names=["rule1"],
            rule=mock_post.return_value,
            confirm_date=True,
        )
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_disabled_on_realm_bucket_posts_then_patches(self):
        module = _module(
            _base_params(bucket=REALM_BUCKET, keep_previous_for="2d", enabled=False)
        )
        blade = _array({"bkt": {}, REALM_BUCKET: {}})
        mock_post, mock_patch = _run(module, blade)

        mock_post.assert_called_once_with(keep_previous_version_for=2 * DAY)
        blade.post_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=[REALM_BUCKET], names=["rule1"], rule=mock_post.return_value
        )
        mock_patch.assert_called_once_with(enabled=False)
        blade.patch_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=[REALM_BUCKET], names=["rule1"], rule=mock_patch.return_value
        )
        assert _bucket_names_sent(blade) == {REALM_BUCKET}
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_on_realm_bucket_check_mode_writes_nothing(self):
        module = _module(
            _base_params(bucket=REALM_BUCKET, keep_previous_for="2d"), check_mode=True
        )
        blade = _array({REALM_BUCKET: {}})
        _run(module, blade)

        assert _no_rule_written(blade)
        assert _bucket_names_sent(blade) == {REALM_BUCKET}
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_on_realm_bucket_with_context(self):
        module = _module(
            _base_params(bucket=REALM_BUCKET, keep_previous_for="2d", context="peer1")
        )
        blade = _array({REALM_BUCKET: {}})
        mock_post, dummy = _run(module, blade)

        blade.get_buckets.assert_called_once_with(
            names=[REALM_BUCKET], context_names=["peer1"]
        )
        blade.get_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=[REALM_BUCKET], names=["rule1"], context_names=["peer1"]
        )
        blade.post_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=[REALM_BUCKET],
            names=["rule1"],
            rule=mock_post.return_value,
            context_names=["peer1"],
        )

    # ---------------- update ----------------

    @pytest.mark.parametrize("bucket", BOTH_BUCKETS)
    def test_update_sends_the_bucket_name_unchanged(self, bucket):
        module = _module(_base_params(bucket=bucket, keep_previous_for="3d"))
        blade = _array(
            {
                "bkt": {"rule1": _existing_rule()},
                REALM_BUCKET: {"rule1": _existing_rule()},
            }
        )
        dummy, mock_patch = _run(module, blade)

        mock_patch.assert_called_once_with(keep_previous_version_for=3 * DAY)
        blade.patch_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=[bucket], names=["rule1"], rule=mock_patch.return_value
        )
        assert _bucket_names_sent(blade) == {bucket}
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_realm_rule_is_idempotent(self):
        module = _module(
            _base_params(
                bucket=REALM_BUCKET,
                prefix="logs/",
                keep_previous_for="2d",
                keep_previous_versions_count=3,
                tags=[{"key": "team", "value": "ops"}, {"key": "env", "value": "dev"}],
            )
        )
        rule = _existing_rule(tags=[_tag("env", "dev"), _tag("team", "ops")])
        blade = _array({REALM_BUCKET: {"rule1": rule}})
        dummy, mock_patch = _run(module, blade)

        mock_patch.assert_not_called()
        assert _no_rule_written(blade)
        assert _bucket_names_sent(blade) == {REALM_BUCKET}
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_realm_rule_check_mode_writes_nothing(self):
        module = _module(
            _base_params(bucket=REALM_BUCKET, enabled=False), check_mode=True
        )
        blade = _array({REALM_BUCKET: {"rule1": _existing_rule()}})
        _run(module, blade)

        assert _no_rule_written(blade)
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_realm_rule_until_confirms_date(self):
        module = _module(
            _base_params(bucket=REALM_BUCKET, keep_current_until="2030-01-01")
        )
        blade = _array({REALM_BUCKET: {"rule1": _existing_rule()}})
        dummy, mock_patch = _run(module, blade)

        mock_patch.assert_called_once_with(keep_current_version_until=1893456000000)
        blade.patch_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=[REALM_BUCKET],
            names=["rule1"],
            rule=mock_patch.return_value,
            confirm_date=True,
        )

    # ---------------- delete ----------------

    @pytest.mark.parametrize("bucket", BOTH_BUCKETS)
    def test_delete_sends_the_bucket_name_unchanged(self, bucket):
        module = _module(_base_params(bucket=bucket, state="absent"))
        blade = _array(
            {
                "bkt": {"rule1": _existing_rule()},
                REALM_BUCKET: {"rule1": _existing_rule()},
            }
        )
        _run(module, blade)

        blade.delete_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=[bucket], names=["rule1"]
        )
        assert _bucket_names_sent(blade) == {bucket}
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_realm_rule_check_mode_writes_nothing(self):
        module = _module(
            _base_params(bucket=REALM_BUCKET, state="absent"), check_mode=True
        )
        blade = _array({REALM_BUCKET: {"rule1": _existing_rule()}})
        _run(module, blade)

        assert _no_rule_written(blade)
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_missing_realm_rule_is_noop(self):
        module = _module(_base_params(bucket=REALM_BUCKET, state="absent"))
        blade = _array({REALM_BUCKET: {}})
        _run(module, blade)

        assert _no_rule_written(blade)
        assert _bucket_names_sent(blade) == {REALM_BUCKET}
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    # ---------------- the same leaf name outside the realm, in it, and in two realms ----------------

    @pytest.mark.parametrize("bucket, other", NAMESAKES)
    def test_same_rule_name_on_both_buckets_is_two_rules(self, bucket, other):
        # the request differs from the rule of this bucket and matches the other one
        module = _module(_base_params(bucket=bucket, keep_previous_for="9d"))
        blade = _array(
            {
                bucket: {"rule1": _existing_rule()},
                other: {"rule1": _existing_rule(keep_previous_version_for=9 * DAY)},
            }
        )
        dummy, mock_patch = _run(module, blade)

        mock_patch.assert_called_once_with(keep_previous_version_for=9 * DAY)
        blade.patch_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=[bucket], names=["rule1"], rule=mock_patch.return_value
        )
        assert _bucket_names_sent(blade) == {bucket}
        assert module.exit_json.call_args[1]["changed"] is True

    @pytest.mark.parametrize("bucket, other", NAMESAKES)
    def test_rule_that_differs_only_on_the_other_bucket_is_unchanged(
        self, bucket, other
    ):
        # the request matches the rule of this bucket and differs from the other one
        module = _module(_base_params(bucket=bucket, keep_previous_for="2d"))
        blade = _array(
            {
                bucket: {"rule1": _existing_rule()},
                other: {"rule1": _existing_rule(keep_previous_version_for=9 * DAY)},
            }
        )
        _run(module, blade)

        assert _no_rule_written(blade)
        assert _bucket_names_sent(blade) == {bucket}
        assert module.exit_json.call_args[1]["changed"] is False

    @pytest.mark.parametrize("bucket, other", NAMESAKES)
    def test_delete_ignores_the_rule_of_the_other_bucket(self, bucket, other):
        module = _module(_base_params(bucket=bucket, state="absent"))
        blade = _array({bucket: {}, other: {"rule1": _existing_rule()}})
        _run(module, blade)

        assert _no_rule_written(blade)
        assert _bucket_names_sent(blade) == {bucket}
        assert module.exit_json.call_args[1]["changed"] is False

    @pytest.mark.parametrize("bucket, other", NAMESAKES)
    def test_create_ignores_the_rule_of_the_other_bucket(self, bucket, other):
        module = _module(_base_params(bucket=bucket, keep_previous_for="2d"))
        blade = _array({bucket: {}, other: {"rule1": _existing_rule()}})
        mock_post, dummy = _run(module, blade)

        blade.post_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=[bucket], names=["rule1"], rule=mock_post.return_value
        )
        blade.patch_buckets_lifecycle_policies_rules.assert_not_called()
        assert _bucket_names_sent(blade) == {bucket}
        assert module.exit_json.call_args[1]["changed"] is True

    # ---------------- a fleet context ----------------

    def test_update_realm_rule_with_context(self):
        module = _module(
            _base_params(bucket=REALM_BUCKET, keep_previous_for="3d", context="peer1")
        )
        blade = _array({"bkt": {}, REALM_BUCKET: {"rule1": _existing_rule()}})
        dummy, mock_patch = _run(module, blade)

        blade.get_buckets.assert_called_once_with(
            names=[REALM_BUCKET], context_names=["peer1"]
        )
        blade.get_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=[REALM_BUCKET], names=["rule1"], context_names=["peer1"]
        )
        mock_patch.assert_called_once_with(keep_previous_version_for=3 * DAY)
        blade.patch_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=[REALM_BUCKET],
            names=["rule1"],
            rule=mock_patch.return_value,
            context_names=["peer1"],
        )
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_realm_rule_with_context(self):
        module = _module(
            _base_params(bucket=REALM_BUCKET, state="absent", context="peer1")
        )
        blade = _array({"bkt": {}, REALM_BUCKET: {"rule1": _existing_rule()}})
        _run(module, blade)

        blade.get_buckets.assert_called_once_with(
            names=[REALM_BUCKET], context_names=["peer1"]
        )
        blade.delete_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=[REALM_BUCKET], names=["rule1"], context_names=["peer1"]
        )
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_disabled_on_realm_bucket_with_context(self):
        module = _module(
            _base_params(
                bucket=REALM_BUCKET,
                keep_previous_for="2d",
                enabled=False,
                context="peer1",
            )
        )
        blade = _array({"bkt": {}, REALM_BUCKET: {}})
        mock_post, mock_patch = _run(module, blade)

        blade.post_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=[REALM_BUCKET],
            names=["rule1"],
            rule=mock_post.return_value,
            context_names=["peer1"],
        )
        mock_patch.assert_called_once_with(enabled=False)
        blade.patch_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=[REALM_BUCKET],
            names=["rule1"],
            rule=mock_patch.return_value,
            context_names=["peer1"],
        )
        assert module.exit_json.call_args[1]["changed"] is True

    @pytest.mark.parametrize("bucket", BOTH_BUCKETS)
    @pytest.mark.parametrize(
        "params, has_rule, method",
        [
            (
                {"keep_previous_for": "2d"},
                False,
                "post_buckets_lifecycle_policies_rules",
            ),
            (
                {"keep_previous_for": "3d"},
                True,
                "patch_buckets_lifecycle_policies_rules",
            ),
            ({"state": "absent"}, True, "delete_buckets_lifecycle_policies_rules"),
        ],
    )
    def test_fleet_member_names_itself_as_context(
        self, bucket, params, has_rule, method
    ):
        # no context in the task: a fleet member sends its own name, for a bucket
        # in a realm exactly as for any other bucket
        module = _module(_base_params(bucket=bucket, **params))
        rules = {"rule1": _existing_rule()} if has_rule else {}
        blade = _array({"bkt": dict(rules), REALM_BUCKET: dict(rules)})
        blade.get_fleets.return_value = _response(200, [Mock()])
        local_array = Mock()
        local_array.name = "local-fb"
        blade.get_arrays.return_value.items = [local_array]
        _run(module, blade)

        blade.get_buckets.assert_called_once_with(
            names=[bucket], context_names=["local-fb"]
        )
        blade.get_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=[bucket], names=["rule1"], context_names=["local-fb"]
        )
        write = getattr(blade, method)
        write.assert_called_once()
        assert write.call_args[1]["bucket_names"] == [bucket]
        assert write.call_args[1]["context_names"] == ["local-fb"]
        assert _bucket_names_sent(blade) == {bucket}
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    # ---------------- refusals ----------------

    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize("check_mode", [False, True])
    def test_bare_name_of_a_bucket_in_a_realm_fails(self, state, check_mode):
        module = _module(
            _base_params(bucket="bkt", state=state, keep_previous_for="2d"),
            check_mode=check_mode,
        )
        blade = _array({REALM_BUCKET: {"rule1": _existing_rule()}})
        _run(module, blade)

        module.fail_json.assert_called_once_with(
            msg="Specified bucket bkt does not exist"
        )
        module.exit_json.assert_not_called()
        blade.get_buckets.assert_called_once_with(names=["bkt"])
        blade.get_buckets_lifecycle_policies_rules.assert_not_called()
        assert _no_rule_written(blade)

    @pytest.mark.parametrize("bucket", BOTH_BUCKETS)
    @pytest.mark.parametrize("check_mode", [False, True])
    def test_abort_on_a_tagged_rule_fails_and_names_the_bucket(
        self, bucket, check_mode
    ):
        module = _module(
            _base_params(bucket=bucket, abort_uploads_after="1d"),
            check_mode=check_mode,
        )
        blade = _array(
            {
                "bkt": {"rule1": _existing_rule(tags=[_tag("env", "dev")])},
                REALM_BUCKET: {"rule1": _existing_rule(tags=[_tag("env", "dev")])},
            }
        )
        _run(module, blade)

        module.fail_json.assert_called_once()
        assert (
            "lifecycle rule rule1 for bucket {0} while the rule has tags".format(bucket)
            in module.fail_json.call_args[1]["msg"]
        )
        module.exit_json.assert_not_called()
        assert _no_rule_written(blade)
        assert _bucket_names_sent(blade) == {bucket}

    @pytest.mark.parametrize("bucket, other", NAMESAKES)
    def test_abort_is_judged_by_the_rule_of_the_named_bucket_alone(self, bucket, other):
        module = _module(_base_params(bucket=bucket, abort_uploads_after="1d"))
        blade = _array(
            {
                bucket: {"rule1": _existing_rule()},
                other: {"rule1": _existing_rule(tags=[_tag("env", "dev")])},
            }
        )
        dummy, mock_patch = _run(module, blade)

        module.fail_json.assert_not_called()
        mock_patch.assert_called_once_with(abort_incomplete_multipart_uploads_after=DAY)
        blade.patch_buckets_lifecycle_policies_rules.assert_called_once_with(
            bucket_names=[bucket], names=["rule1"], rule=mock_patch.return_value
        )
        assert _bucket_names_sent(blade) == {bucket}
        assert module.exit_json.call_args[1]["changed"] is True

    @pytest.mark.parametrize("bucket", ["zznorealm::bkt", "realm1::other"])
    def test_realm_qualified_name_the_array_does_not_hold_fails(self, bucket):
        module = _module(_base_params(bucket=bucket, keep_previous_for="2d"))
        blade = _array({"bkt": {}, REALM_BUCKET: {}})
        _run(module, blade)

        module.fail_json.assert_called_once_with(
            msg="Specified bucket {0} does not exist".format(bucket)
        )
        blade.get_buckets.assert_called_once_with(names=[bucket])
        blade.get_buckets_lifecycle_policies_rules.assert_not_called()
        assert _no_rule_written(blade)

    @pytest.mark.parametrize(
        "method, params, has_rule, message",
        [
            (
                "get_buckets_lifecycle_policies_rules",
                {"keep_previous_for": "2d"},
                False,
                "Failed to read lifecycle rule rule1 for bucket realm1::bkt.",
            ),
            (
                "post_buckets_lifecycle_policies_rules",
                {"keep_previous_for": "2d"},
                False,
                "Failed to create lifecycle rule rule1 for bucket realm1::bkt.",
            ),
            (
                "patch_buckets_lifecycle_policies_rules",
                {"enabled": False},
                True,
                "Failed to update lifecycle rule rule1 for bucket realm1::bkt.",
            ),
            (
                "delete_buckets_lifecycle_policies_rules",
                {"state": "absent"},
                True,
                "Failed to delete lifecycle rule rule1 for bucket realm1::bkt.",
            ),
        ],
    )
    def test_api_errors_name_the_realm_bucket(self, method, params, has_rule, message):
        module = _module(_base_params(bucket=REALM_BUCKET, **params))
        rules = {"rule1": _existing_rule()} if has_rule else {}
        blade = _array({REALM_BUCKET: rules})
        setattr(blade, method, Mock(return_value=_response(400)))
        _run(module, blade)

        module.fail_json.assert_called_once()
        assert module.fail_json.call_args[1]["msg"].startswith(message)
        module.exit_json.assert_not_called()
