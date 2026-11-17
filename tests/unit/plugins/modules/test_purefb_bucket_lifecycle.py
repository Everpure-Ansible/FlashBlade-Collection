# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_bucket_lifecycle module."""

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
sys.modules[
    "ansible_collections.everpure.flashblade.plugins.module_utils.time_utils"
] = MagicMock()

from plugins.modules.purefb_bucket_lifecycle import (
    main,
    _context_kwargs,
    _current_state,
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

    def test_clear_tags_with_abort_in_one_task(self):
        module = _module(_base_params(tags=[], abort_uploads_after="1d"))
        blade = _blade(rule=_existing_rule(tags=[_tag("env", "dev")]))
        dummy, mock_patch = _run(module, blade)
        module.fail_json.assert_not_called()
        mock_patch.assert_called_once_with(
            abort_incomplete_multipart_uploads_after=DAY,
            filter={"prefix": "logs/", "tags": []},
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
