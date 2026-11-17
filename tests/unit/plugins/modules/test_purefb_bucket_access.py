# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_bucket_access module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from collections import defaultdict
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

from plugins.modules.purefb_bucket_access import (
    _ACCESS_ACTIONS_FALLBACK,
    _check_actions,
    _valid_actions,
    main,
)
from plugins.module_utils.version import LooseVersion as RealLooseVersion

BUCKET = "bkt"
RULE = "rule1"

# A cut-down array catalogue (GET /object-store-access-policy-actions).
_CATALOGUE = ["s3:*", "s3:GetObject", "s3:PutObjectTagging", "s3:GetBucketPolicy"]

# Actions Purity//FB 4.8.8 publishes that the old static choices list lacked.
_NEWER_ACTIONS = [
    "s3:DeleteObjectTagging",
    "s3:DeleteObjectVersionTagging",
    "s3:GetBucketCORS",
    "s3:GetBucketPolicy",
    "s3:GetBucketPolicyStatus",
    "s3:GetBucketPublicAccessBlock",
    "s3:PutObjectTagging",
    "s3:PutObjectVersionTagging",
]


def _module(**overrides):
    """Build a mock AnsibleModule for a bucket access policy task."""
    module = Mock()
    module.check_mode = False
    module.params = defaultdict(
        lambda: None,
        {
            "state": "present",
            "policy_type": "access",
            "name": BUCKET,
            "rule": RULE,
            "actions": ["s3:GetObject"],
            "resources": ["*"],
            "effect": "allow",
            "principals": True,
            "context": "",
        },
    )
    module.params.update(overrides)
    module.fail_json = Mock(side_effect=SystemExit("fail_json called"))
    module.exit_json = Mock(side_effect=SystemExit("exit_json called"))
    return module


def _response(status=200, items=None, total=None):
    res = Mock()
    res.status_code = status
    if items is not None:
        res.items = items
        res.total_item_count = len(items) if total is None else total
    elif total is not None:
        res.total_item_count = total
    return res


def _catalogue_response(names=None, status=200):
    items = []
    for name in names or []:
        action = Mock()
        action.name = name
        items.append(action)
    return _response(status, items)


def _stored_rule(actions=None, resources=None, all_principals=True):
    """Build a mock SDK bucket access policy rule as the array returns it."""
    rule = Mock()
    rule.name = RULE
    rule.actions = actions if actions is not None else ["s3:GetObject"]
    rule.resources = resources if resources is not None else [BUCKET + "/*"]
    rule.effect = "allow"
    rule.principals = Mock()
    rule.principals.all = all_principals
    return rule


def _blade(catalogue=None, rule_exists=False, policy_exists=True, stored=None):
    """Build a mock blade for main().

    rule_exists: the rule is already on the array (stored, or a matching
    s3:GetObject rule) when main() first looks for it.
    stored: what the array holds after the POST (defaults to a rule that
    matches the request).
    """
    blade = Mock()
    blade.get_fleets.return_value = _response(400)
    blade.get_buckets.return_value = _response(200, [Mock()])
    blade.get_object_store_access_policy_actions.return_value = _catalogue_response(
        _CATALOGUE if catalogue is None else catalogue
    )
    existing = _stored_rule() if rule_exists else None
    after_post = stored if stored is not None else _stored_rule()
    blade.get_buckets_bucket_access_policies_rules.side_effect = [
        _response(200, [existing]) if existing else _response(400),
        _response(200, [after_post]),
    ]
    blade.get_buckets_bucket_access_policies.return_value = _response(
        200, total=1 if policy_exists else 0
    )
    blade.post_buckets_bucket_access_policies.return_value = _response(200)
    blade.post_buckets_bucket_access_policies_rules.return_value = _response(200)
    blade.delete_buckets_bucket_access_policies_rules.return_value = _response(200)
    blade.delete_buckets_bucket_access_policies.return_value = _response(200)
    return blade


@patch("plugins.modules.purefb_bucket_access.LooseVersion", RealLooseVersion)
class TestCheckActions:
    """Rule actions are validated against the array's catalogue, not a frozen list."""

    def test_actions_in_the_array_catalogue_are_accepted(self):
        module = _module(actions=["s3:PutObjectTagging", "s3:GetBucketPolicy"])
        blade = _blade()

        _check_actions(module, blade, "2.30")

        module.fail_json.assert_not_called()
        module.warn.assert_not_called()
        blade.get_object_store_access_policy_actions.assert_called_once_with()

    def test_unknown_actions_are_named(self):
        module = _module(actions=["s3:GetObject", "s3:Bogus", "s3:Nope"])
        blade = _blade()

        with pytest.raises(SystemExit):
            _check_actions(module, blade, "2.30")

        msg = module.fail_json.call_args[1]["msg"]
        assert msg.startswith(
            "Unknown bucket access policy action(s): s3:Bogus, s3:Nope. "
        )
        assert "Valid actions: s3:*, s3:GetBucketPolicy, s3:GetObject" in msg

    def test_catalogue_error_falls_back_to_the_built_in_list(self):
        """The built-in list knows the object tagging and bucket policy actions."""
        module = _module(actions=["s3:PutObjectTagging", "s3:GetBucketCORS"])
        blade = _blade()
        blade.get_object_store_access_policy_actions.return_value = _response(400)

        _check_actions(module, blade, "2.30")

        module.fail_json.assert_not_called()
        module.warn.assert_called_once()
        assert module.warn.call_args[0][0].startswith(
            "Could not read the array's access policy action list, "
            "validating against the collection's built-in list. Error: "
        )

    def test_built_in_list_still_rejects_unknown_actions(self):
        module = _module(actions=["s3:GetObject", "s3:Bogus"])
        blade = _blade()
        blade.get_object_store_access_policy_actions.return_value = _response(400)

        with pytest.raises(SystemExit):
            _check_actions(module, blade, "2.30")

        assert "s3:Bogus" in module.fail_json.call_args[1]["msg"]

    def test_empty_catalogue_falls_back_to_the_built_in_list(self):
        module = _module()
        blade = _blade(catalogue=[])

        valid = _valid_actions(module, blade, "2.30")

        assert valid == list(_ACCESS_ACTIONS_FALLBACK)
        module.warn.assert_called_once()
        assert module.warn.call_args[0][0].endswith(
            "built-in list. The array returned an empty list."
        )

    def test_below_rest_2_2_never_asks_the_array(self):
        module = _module()
        blade = _blade()

        _check_actions(module, blade, "2.1")

        blade.get_object_store_access_policy_actions.assert_not_called()
        module.fail_json.assert_not_called()
        module.warn.assert_not_called()

    def test_no_actions_means_no_lookup(self):
        module = _module(actions=None)
        blade = _blade()

        _check_actions(module, blade, "2.30")

        blade.get_object_store_access_policy_actions.assert_not_called()
        module.fail_json.assert_not_called()

    def test_fleet_context_is_sent_with_the_lookup(self):
        module = _module(context="array-b")
        blade = _blade()

        _check_actions(module, blade, "2.30")

        blade.get_object_store_access_policy_actions.assert_called_once_with(
            context_names=["array-b"]
        )

    def test_context_is_not_sent_below_rest_2_17(self):
        module = _module(context="array-b")
        blade = _blade()

        _check_actions(module, blade, "2.16")

        blade.get_object_store_access_policy_actions.assert_called_once_with()

    @pytest.mark.parametrize("action", _NEWER_ACTIONS)
    def test_built_in_list_knows_the_newer_actions(self, action):
        assert action in _ACCESS_ACTIONS_FALLBACK

    def test_built_in_list_matches_the_4_8_8_catalogue_size(self):
        assert len(_ACCESS_ACTIONS_FALLBACK) == 40
        assert len(set(_ACCESS_ACTIONS_FALLBACK)) == 40


@patch("plugins.modules.purefb_bucket_access.LooseVersion", RealLooseVersion)
@patch("plugins.modules.purefb_bucket_access.HAS_PYPURECLIENT", True)
@patch("plugins.modules.purefb_bucket_access.get_rest_api_version", return_value="2.30")
@patch("plugins.modules.purefb_bucket_access.purefb_argument_spec", return_value={})
@patch("plugins.modules.purefb_bucket_access.get_system")
@patch("plugins.modules.purefb_bucket_access.AnsibleModule")
class TestMainActions:
    """main() asks the array about the actions before any rule write."""

    def test_argspec_has_no_static_action_choices(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(actions=["s3:PutObjectTagging"])
        mock_ansible_module.return_value = module
        blade = _blade(stored=_stored_rule(actions=["s3:PutObjectTagging"]))
        mock_get_system.return_value = blade

        with pytest.raises(SystemExit, match="exit_json"):
            main()

        spec = mock_ansible_module.call_args[0][0]
        assert "choices" not in spec["actions"]
        assert spec["actions"]["default"] == ["s3:GetObject"]
        rule = blade.post_buckets_bucket_access_policies_rules.call_args[1]
        assert rule["bucket_names"] == [BUCKET]
        assert rule["names"] == [RULE]
        module.exit_json.assert_called_once_with(changed=True)

    def test_unknown_action_fails_before_any_write(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(actions=["s3:GetObject", "s3:NotAnAction"])
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        with pytest.raises(SystemExit, match="fail_json"):
            main()

        msg = module.fail_json.call_args[1]["msg"]
        assert msg.startswith(
            "Unknown bucket access policy action(s): s3:NotAnAction. "
        )
        blade.post_buckets_bucket_access_policies.assert_not_called()
        blade.post_buckets_bucket_access_policies_rules.assert_not_called()
        blade.delete_buckets_bucket_access_policies_rules.assert_not_called()

    def test_unknown_action_fails_in_check_mode_too(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(actions=["s3:NotAnAction"])
        module.check_mode = True
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        with pytest.raises(SystemExit, match="fail_json"):
            main()

        assert "s3:NotAnAction" in module.fail_json.call_args[1]["msg"]
        module.exit_json.assert_not_called()

    def test_actions_are_not_checked_on_delete(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(state="absent", actions=["s3:NotAnAction"])
        mock_ansible_module.return_value = module
        blade = _blade(rule_exists=True)
        mock_get_system.return_value = blade

        with pytest.raises(SystemExit, match="exit_json"):
            main()

        blade.get_object_store_access_policy_actions.assert_not_called()
        blade.delete_buckets_bucket_access_policies_rules.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    def test_actions_are_not_checked_for_cors_policies(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(
            policy_type="cors",
            methods=["GET"],
            origins=["*"],
            headers=["*"],
        )
        mock_ansible_module.return_value = module
        blade = _blade()
        blade.get_buckets_cross_origin_resource_sharing_policies_rules.side_effect = [
            _response(400),
            _response(400),
        ]
        blade.get_buckets_cross_origin_resource_sharing_policies.return_value = (
            _response(200, total=1)
        )
        blade.post_buckets_cross_origin_resource_sharing_policies_rules.return_value = (
            _response(200)
        )
        mock_get_system.return_value = blade

        with pytest.raises(SystemExit, match="exit_json"):
            main()

        blade.get_object_store_access_policy_actions.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_create_posts_policy_then_rule(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module()
        mock_ansible_module.return_value = module
        blade = _blade(policy_exists=False)
        mock_get_system.return_value = blade

        with pytest.raises(SystemExit, match="exit_json"):
            main()

        blade.post_buckets_bucket_access_policies.assert_called_once_with(
            bucket_names=[BUCKET]
        )
        blade.post_buckets_bucket_access_policies_rules.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    def test_create_in_check_mode_writes_nothing(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module()
        module.check_mode = True
        mock_ansible_module.return_value = module
        blade = _blade(policy_exists=False)
        mock_get_system.return_value = blade

        with pytest.raises(SystemExit, match="exit_json"):
            main()

        blade.get_object_store_access_policy_actions.assert_called_once()
        blade.post_buckets_bucket_access_policies.assert_not_called()
        blade.post_buckets_bucket_access_policies_rules.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_matching_rule_is_idempotent(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module()
        mock_ansible_module.return_value = module
        blade = _blade(rule_exists=True)
        mock_get_system.return_value = blade

        with pytest.raises(SystemExit, match="exit_json"):
            main()

        blade.post_buckets_bucket_access_policies_rules.assert_not_called()
        blade.delete_buckets_bucket_access_policies_rules.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_differing_rule_is_replaced(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(actions=["s3:GetObject", "s3:PutObjectTagging"])
        mock_ansible_module.return_value = module
        blade = _blade(
            rule_exists=True,
            stored=_stored_rule(actions=["s3:GetObject", "s3:PutObjectTagging"]),
        )
        mock_get_system.return_value = blade

        with pytest.raises(SystemExit, match="exit_json"):
            main()

        blade.delete_buckets_bucket_access_policies_rules.assert_called_once()
        blade.post_buckets_bucket_access_policies_rules.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    def test_coerced_rule_is_reported(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        """The array keeps s3:GetObject alone out of a longer list; the module
        says what was kept instead of replacing the rule on every run."""
        module = _module(actions=["s3:GetObject", "s3:PutObjectTagging"])
        mock_ansible_module.return_value = module
        blade = _blade(stored=_stored_rule(actions=["s3:GetObject"]))
        mock_get_system.return_value = blade

        with pytest.raises(SystemExit, match="fail_json"):
            main()

        kwargs = module.fail_json.call_args[1]
        assert kwargs["changed"] is True
        assert "was not stored as requested" in kwargs["msg"]
        assert "actions=['s3:GetObject']" in kwargs["msg"]

    def test_array_refusal_is_reported(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        """A catalogue action the bucket policy does not support is refused by
        the array; its message reaches the user."""
        module = _module(actions=["s3:PutObjectTagging"])
        mock_ansible_module.return_value = module
        blade = _blade()
        blade.post_buckets_bucket_access_policies_rules.return_value = _response(400)
        mock_get_system.return_value = blade

        with patch(
            "plugins.modules.purefb_bucket_access.get_error_message",
            return_value="Invalid rule for a bucket access policy.",
        ):
            with pytest.raises(SystemExit, match="fail_json"):
                main()

        msg = module.fail_json.call_args[1]["msg"]
        assert msg.startswith(
            "Failed to create access policy rule rule1 in policy bkt."
        )
        assert msg.endswith("Error: Invalid rule for a bucket access policy.")

    def test_deny_is_refused_before_the_array_is_asked(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(effect="deny")
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        with pytest.raises(SystemExit, match="fail_json"):
            main()

        assert "only supports 'allow'" in module.fail_json.call_args[1]["msg"]
        mock_get_system.assert_not_called()

    def test_delete_missing_rule_is_idempotent(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(state="absent")
        mock_ansible_module.return_value = module
        blade = _blade(rule_exists=False)
        mock_get_system.return_value = blade

        with pytest.raises(SystemExit, match="exit_json"):
            main()

        blade.delete_buckets_bucket_access_policies_rules.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_old_array_is_refused_before_any_lookup(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        mock_version.return_value = "2.11"
        module = _module()
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        with pytest.raises(SystemExit, match="fail_json"):
            main()

        assert "2.12" in module.fail_json.call_args[1]["msg"]
        blade.get_object_store_access_policy_actions.assert_not_called()
        blade.post_buckets_bucket_access_policies_rules.assert_not_called()

    def test_missing_bucket_is_refused_before_any_lookup(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module()
        mock_ansible_module.return_value = module
        blade = _blade()
        blade.get_buckets.return_value = _response(400)
        mock_get_system.return_value = blade

        with pytest.raises(SystemExit, match="fail_json"):
            main()

        assert "does not exist" in module.fail_json.call_args[1]["msg"]
        blade.get_object_store_access_policy_actions.assert_not_called()

    def test_fleet_context_reaches_the_lookup(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(context="array-b")
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        with pytest.raises(SystemExit, match="exit_json"):
            main()

        blade.get_object_store_access_policy_actions.assert_called_once_with(
            context_names=["array-b"]
        )
        rule = blade.post_buckets_bucket_access_policies_rules.call_args[1]
        assert rule["context_names"] == ["array-b"]
