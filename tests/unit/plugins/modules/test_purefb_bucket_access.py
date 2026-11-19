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
    _ACCESS_RULES,
    _CORS_RULES,
    _check_actions,
    _temp_rule_name,
    _valid_actions,
    main,
)
from plugins.module_utils.version import LooseVersion as RealLooseVersion

BUCKET = "bkt"
RULE = "rule1"
# The name a rule is posted under while it is being replaced.
TEMP = RULE + "tmp"
_ALL_METHODS = ["GET", "PUT", "HEAD", "POST", "DELETE"]

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
            "methods": _ALL_METHODS,
            "origins": ["*"],
            "headers": ["*"],
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


class _Rule:
    """A stored policy rule as the SDK returns it (plain attributes)."""

    def __init__(self, name, **attrs):
        self.name = name
        self.__dict__.update(attrs)


def _copy_rule(template, name):
    attrs = dict((k, v) for k, v in template.__dict__.items() if k != "name")
    return _Rule(name, **attrs)


def _stored_rule(actions=None, resources=None, all_principals=True, name=RULE):
    """Build a bucket access policy rule as the array returns it."""
    return _Rule(
        name,
        actions=actions if actions is not None else ["s3:GetObject"],
        resources=resources if resources is not None else [BUCKET + "/*"],
        effect="allow",
        principals=_Rule("principals", all=all_principals),
    )


def _stored_cors_rule(methods=None, origins=None, headers=None, name=RULE):
    """Build a CORS policy rule as the array returns it."""
    return _Rule(
        name,
        allowed_methods=methods if methods is not None else _ALL_METHODS,
        allowed_origins=origins if origins is not None else ["*"],
        allowed_headers=headers if headers is not None else ["*"],
    )


def _bucket(name=BUCKET):
    """A bucket as GET /buckets returns it; name is the array's own spelling."""
    bucket = Mock()
    bucket.name = name
    return bucket


def _wire_policy(
    blade,
    kind,
    rules=(),
    policy_exists=True,
    stored=None,
    post_status=200,
    delete_status=200,
    readback_status=200,
    policy_status=200,
    rules_status=200,
):
    """Back one policy kind's SDK methods with a small in-memory store.

    rules: the rules already on the array. stored: the content the array
    keeps for every rule that is POSTed (a rule matching the default request
    when None). The *_status knobs make a call fail; a list gives one status
    per call, in order.
    """
    store = dict((rule.name, rule) for rule in rules)
    state = {"policy": policy_exists}

    def _status(knob):
        if isinstance(knob, list):
            return knob.pop(0) if knob else 200
        return knob

    def get_policies(bucket_names, **kwargs):
        if policy_status != 200:
            return _response(policy_status)
        return _response(200, [Mock()] if state["policy"] else [])

    def post_policies(bucket_names, **kwargs):
        state["policy"] = True
        return _response(200)

    def delete_policies(bucket_names, **kwargs):
        state["policy"] = False
        store.clear()
        return _response(200)

    def get_rules(bucket_names, names=None, **kwargs):
        if names is None:
            if rules_status != 200:
                return _response(rules_status)
            return _response(200, list(store.values()))
        status = _status(readback_status)
        if status != 200:
            return _response(status)
        if names[0] not in store:
            return _response(400)
        return _response(200, [store[names[0]]])

    def post_rules(bucket_names, names, rule, **kwargs):
        status = _status(post_status)
        if status != 200:
            return _response(status)
        store[names[0]] = _copy_rule(stored, names[0])
        return _response(200)

    def delete_rules(bucket_names, names, **kwargs):
        status = _status(delete_status)
        if status != 200:
            return _response(status)
        store.pop(names[0], None)
        return _response(200)

    getattr(blade, kind["get_policies"]).side_effect = get_policies
    getattr(blade, kind["post_policies"]).side_effect = post_policies
    getattr(blade, kind["delete_policies"]).side_effect = delete_policies
    getattr(blade, kind["get_rules"]).side_effect = get_rules
    getattr(blade, kind["post_rules"]).side_effect = post_rules
    getattr(blade, kind["delete_rules"]).side_effect = delete_rules
    blade.rule_store = store


def _blade(
    catalogue=None,
    rule_exists=False,
    policy_exists=True,
    stored=None,
    existing=None,
    extra_rules=(),
    bucket=BUCKET,
    **knobs
):
    """Build a mock blade for main() with a bucket access policy fake.

    rule_exists: the rule is already on the array (existing, or a matching
    s3:GetObject rule) when main() first looks for it. stored: what the array
    keeps for a POSTed rule (defaults to a rule that matches the default
    request). extra_rules: other rules already in the policy. bucket: the
    name the array returns for the bucket. knobs: the failure switches of
    _wire_policy.
    """
    blade = Mock()
    blade.get_fleets.return_value = _response(400)
    blade.get_buckets.return_value = _response(200, [_bucket(bucket)])
    blade.get_object_store_access_policy_actions.return_value = _catalogue_response(
        _CATALOGUE if catalogue is None else catalogue
    )
    rules = list(extra_rules)
    if rule_exists:
        rules.append(existing if existing is not None else _stored_rule())
    _wire_policy(
        blade,
        _ACCESS_RULES,
        rules=rules,
        policy_exists=policy_exists,
        stored=stored if stored is not None else _stored_rule(),
        **knobs
    )
    return blade


def _cors_blade(
    rule_exists=False,
    policy_exists=True,
    stored=None,
    existing=None,
    bucket=BUCKET,
    **knobs
):
    """Build a mock blade for main() with a CORS policy fake."""
    blade = Mock()
    blade.get_fleets.return_value = _response(400)
    blade.get_buckets.return_value = _response(200, [_bucket(bucket)])
    rules = []
    if rule_exists:
        rules.append(existing if existing is not None else _stored_cors_rule())
    _wire_policy(
        blade,
        _CORS_RULES,
        rules=rules,
        policy_exists=policy_exists,
        stored=stored if stored is not None else _stored_cors_rule(),
        **knobs
    )
    return blade


def _run(mock_ansible_module, mock_get_system, module, blade, outcome):
    """Run main() with this module and blade; outcome is exit_json or fail_json."""
    mock_ansible_module.return_value = module
    mock_get_system.return_value = blade
    with pytest.raises(SystemExit, match=outcome):
        main()


def _write_sequence(blade, kind):
    """The rule POST and DELETE calls made on blade, in order, as (verb, name)."""
    verbs = {kind["post_rules"]: "post", kind["delete_rules"]: "delete"}
    return [
        (verbs[name], kwargs["names"][0])
        for name, args, kwargs in blade.mock_calls
        if name in verbs
    ]


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
        module = _module(policy_type="cors")
        blade = _cors_blade(policy_exists=True)

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

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
        blade = _blade(
            rule_exists=True,
            stored=_stored_rule(actions=["s3:GetObject", "s3:PutObjectTagging"]),
        )

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        # The replacement is posted under a temporary name before the existing
        # rule is deleted; TestReplace covers the failure paths.
        assert _write_sequence(blade, _ACCESS_RULES) == [
            ("post", TEMP),
            ("delete", RULE),
            ("post", RULE),
            ("delete", TEMP),
        ]
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
        blade = _blade(post_status=400)
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

        with patch(
            "plugins.modules.purefb_bucket_access.get_error_message",
            return_value="Bucket does not exist.",
        ):
            with pytest.raises(SystemExit, match="fail_json"):
                main()

        assert module.fail_json.call_args[1]["msg"] == (
            "Bucket bkt does not exist, or is destroyed."
        )
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


_CHANGED_REQUEST = ["s3:GetObject", "s3:PutObjectTagging"]


@patch("plugins.modules.purefb_bucket_access.LooseVersion", RealLooseVersion)
@patch("plugins.modules.purefb_bucket_access.HAS_PYPURECLIENT", True)
@patch("plugins.modules.purefb_bucket_access.get_rest_api_version", return_value="2.30")
@patch("plugins.modules.purefb_bucket_access.purefb_argument_spec", return_value={})
@patch("plugins.modules.purefb_bucket_access.get_system")
@patch("plugins.modules.purefb_bucket_access.AnsibleModule")
class TestReplace:
    """A rule whose content differs is replaced through a temporary rule, so
    the existing rule survives a replacement the array refuses or coerces."""

    def test_refused_replacement_keeps_the_existing_rule(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(actions=["s3:PutObjectTagging"])
        blade = _blade(rule_exists=True, post_status=400)

        with patch(
            "plugins.modules.purefb_bucket_access.get_error_message",
            return_value="Invalid rule for a bucket access policy.",
        ):
            _run(mock_ansible_module, mock_get_system, module, blade, "fail_json")

        kwargs = module.fail_json.call_args[1]
        assert kwargs["msg"] == (
            "Failed to replace access policy rule rule1 in policy bkt: the array "
            "refused the new rule and the existing rule was left unchanged. "
            "Error: Invalid rule for a bucket access policy."
        )
        assert "changed" not in kwargs
        assert _write_sequence(blade, _ACCESS_RULES) == [("post", TEMP)]
        assert blade.rule_store[RULE].actions == ["s3:GetObject"]

    def test_coerced_replacement_keeps_the_existing_rule(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        """The array keeps s3:GetObject alone out of the longer list; the
        temporary rule shows that, is removed, and the old rule stays."""
        module = _module(actions=_CHANGED_REQUEST)
        blade = _blade(rule_exists=True, stored=_stored_rule(actions=["s3:GetObject"]))

        _run(mock_ansible_module, mock_get_system, module, blade, "fail_json")

        kwargs = module.fail_json.call_args[1]
        assert kwargs["msg"].startswith(
            "Access policy rule rule1 in policy bkt cannot be changed as requested: "
            "the array stored the new rule as actions=['s3:GetObject'], "
        )
        assert kwargs["msg"].endswith("The existing rule was left unchanged.")
        assert "changed" not in kwargs
        assert _write_sequence(blade, _ACCESS_RULES) == [
            ("post", TEMP),
            ("delete", TEMP),
        ]
        assert sorted(blade.rule_store) == [RULE]

    def test_temporary_name_in_use_fails_before_any_write(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(actions=_CHANGED_REQUEST)
        blade = _blade(rule_exists=True, extra_rules=[_stored_rule(name=TEMP)])

        _run(mock_ansible_module, mock_get_system, module, blade, "fail_json")

        msg = module.fail_json.call_args[1]["msg"]
        assert "the temporary rule name rule1tmp is already in use" in msg
        assert _write_sequence(blade, _ACCESS_RULES) == []

    def test_replacement_in_check_mode_writes_nothing(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(actions=_CHANGED_REQUEST)
        module.check_mode = True
        blade = _blade(rule_exists=True)

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        assert _write_sequence(blade, _ACCESS_RULES) == []
        module.exit_json.assert_called_once_with(changed=True)

    def test_readback_failure_removes_the_temporary_rule(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(actions=_CHANGED_REQUEST)
        blade = _blade(rule_exists=True, readback_status=500)

        _run(mock_ansible_module, mock_get_system, module, blade, "fail_json")

        kwargs = module.fail_json.call_args[1]
        assert (
            "the new rule could not be read back and the existing rule was left "
            "unchanged" in kwargs["msg"]
        )
        assert "changed" not in kwargs
        assert _write_sequence(blade, _ACCESS_RULES) == [
            ("post", TEMP),
            ("delete", TEMP),
        ]
        assert sorted(blade.rule_store) == [RULE]

    def test_existing_rule_delete_failure_removes_the_temporary_rule(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(actions=_CHANGED_REQUEST)
        blade = _blade(
            rule_exists=True,
            stored=_stored_rule(actions=_CHANGED_REQUEST),
            delete_status=[400, 200],
        )

        _run(mock_ansible_module, mock_get_system, module, blade, "fail_json")

        kwargs = module.fail_json.call_args[1]
        assert "the existing rule could not be deleted" in kwargs["msg"]
        assert "could not be removed" not in kwargs["msg"]
        assert "changed" not in kwargs
        assert _write_sequence(blade, _ACCESS_RULES) == [
            ("post", TEMP),
            ("delete", RULE),
            ("delete", TEMP),
        ]
        assert sorted(blade.rule_store) == [RULE]

    def test_temporary_rule_cleanup_failure_is_noted(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(actions=_CHANGED_REQUEST)
        blade = _blade(
            rule_exists=True,
            stored=_stored_rule(actions=_CHANGED_REQUEST),
            delete_status=[400, 400],
        )

        _run(mock_ansible_module, mock_get_system, module, blade, "fail_json")

        msg = module.fail_json.call_args[1]["msg"]
        assert "the existing rule could not be deleted" in msg
        assert "The temporary rule rule1tmp could not be removed." in msg

    def test_recreate_failure_names_the_temporary_rule(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(actions=_CHANGED_REQUEST)
        blade = _blade(
            rule_exists=True,
            stored=_stored_rule(actions=_CHANGED_REQUEST),
            post_status=[200, 400],
        )

        _run(mock_ansible_module, mock_get_system, module, blade, "fail_json")

        kwargs = module.fail_json.call_args[1]
        assert kwargs["changed"] is True
        assert (
            "the requested rule is stored under the temporary name rule1tmp"
            in kwargs["msg"]
        )
        assert _write_sequence(blade, _ACCESS_RULES) == [
            ("post", TEMP),
            ("delete", RULE),
            ("post", RULE),
        ]
        assert sorted(blade.rule_store) == [TEMP]

    def test_temporary_rule_delete_failure_is_reported(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(actions=_CHANGED_REQUEST)
        blade = _blade(
            rule_exists=True,
            stored=_stored_rule(actions=_CHANGED_REQUEST),
            delete_status=[200, 400],
        )

        _run(mock_ansible_module, mock_get_system, module, blade, "fail_json")

        kwargs = module.fail_json.call_args[1]
        assert kwargs["changed"] is True
        assert "the temporary rule rule1tmp could not be deleted" in kwargs["msg"]
        assert sorted(blade.rule_store) == [RULE, TEMP]


class TestTempRuleName:
    def test_short_name_gets_the_suffix(self):
        assert _temp_rule_name("rule1") == "rule1tmp"

    def test_long_name_stays_within_63_characters(self):
        assert _temp_rule_name("a" * 63) == "a" * 60 + "tmp"
        assert _temp_rule_name("b" * 61) == "b" * 60 + "tmp"
        assert _temp_rule_name("c" * 60) == "c" * 60 + "tmp"


@patch("plugins.modules.purefb_bucket_access.LooseVersion", RealLooseVersion)
@patch("plugins.modules.purefb_bucket_access.HAS_PYPURECLIENT", True)
@patch("plugins.modules.purefb_bucket_access.get_rest_api_version", return_value="2.30")
@patch("plugins.modules.purefb_bucket_access.purefb_argument_spec", return_value={})
@patch("plugins.modules.purefb_bucket_access.get_system")
@patch("plugins.modules.purefb_bucket_access.AnsibleModule")
class TestReads:
    """Policy and rule lookups fail on errors instead of treating them as
    "nothing there", in the create and the delete path alike."""

    def test_policy_read_error_fails_a_delete(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(state="absent")
        blade = _blade(rule_exists=True, policy_status=500)

        with patch(
            "plugins.modules.purefb_bucket_access.get_error_message",
            return_value="Internal error",
        ):
            _run(mock_ansible_module, mock_get_system, module, blade, "fail_json")

        assert module.fail_json.call_args[1]["msg"] == (
            "Failed to read the access policy of bucket bkt. Error: Internal error"
        )
        blade.delete_buckets_bucket_access_policies_rules.assert_not_called()
        module.exit_json.assert_not_called()

    def test_rules_read_error_fails_a_delete(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(state="absent")
        blade = _blade(rule_exists=True, rules_status=500)

        with patch(
            "plugins.modules.purefb_bucket_access.get_error_message",
            return_value="Internal error",
        ):
            _run(mock_ansible_module, mock_get_system, module, blade, "fail_json")

        assert module.fail_json.call_args[1]["msg"] == (
            "Failed to read the access policy rules of bucket bkt. "
            "Error: Internal error"
        )
        blade.delete_buckets_bucket_access_policies_rules.assert_not_called()

    def test_policy_read_error_fails_a_create_before_any_write(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module()
        blade = _blade(policy_status=500)

        _run(mock_ansible_module, mock_get_system, module, blade, "fail_json")

        assert module.fail_json.call_args[1]["msg"].startswith(
            "Failed to read the access policy of bucket bkt."
        )
        blade.post_buckets_bucket_access_policies.assert_not_called()
        blade.post_buckets_bucket_access_policies_rules.assert_not_called()

    def test_rules_read_error_fails_a_create_before_any_write(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module()
        blade = _blade(rules_status=500)

        _run(mock_ansible_module, mock_get_system, module, blade, "fail_json")

        assert module.fail_json.call_args[1]["msg"].startswith(
            "Failed to read the access policy rules of bucket bkt."
        )
        blade.post_buckets_bucket_access_policies_rules.assert_not_called()

    def test_missing_policy_skips_the_rule_listing(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module()
        blade = _blade(policy_exists=False)

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        listings = [
            call
            for call in blade.get_buckets_bucket_access_policies_rules.call_args_list
            if "names" not in call[1]
        ]
        assert listings == []
        module.exit_json.assert_called_once_with(changed=True)

    def test_created_rule_that_cannot_be_read_back_fails(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module()
        blade = _blade(readback_status=500)

        _run(mock_ansible_module, mock_get_system, module, blade, "fail_json")

        kwargs = module.fail_json.call_args[1]
        assert kwargs["changed"] is True
        assert kwargs["msg"].startswith(
            "Access policy rule rule1 in policy bkt was created but could not be "
            "read back."
        )


@patch("plugins.modules.purefb_bucket_access.LooseVersion", RealLooseVersion)
@patch("plugins.modules.purefb_bucket_access.HAS_PYPURECLIENT", True)
@patch("plugins.modules.purefb_bucket_access.get_rest_api_version", return_value="2.30")
@patch("plugins.modules.purefb_bucket_access.purefb_argument_spec", return_value={})
@patch("plugins.modules.purefb_bucket_access.get_system")
@patch("plugins.modules.purefb_bucket_access.AnsibleModule")
class TestDelete:
    """state=absent deletes what exists, is idempotent and is accurate in
    check mode."""

    def test_delete_rule(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(state="absent")
        blade = _blade(rule_exists=True)

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        blade.delete_buckets_bucket_access_policies_rules.assert_called_once_with(
            bucket_names=[BUCKET], names=[RULE]
        )
        assert blade.rule_store == {}
        module.exit_json.assert_called_once_with(changed=True)

    def test_delete_rule_in_check_mode_reports_the_change(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(state="absent")
        module.check_mode = True
        blade = _blade(rule_exists=True)

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        blade.delete_buckets_bucket_access_policies_rules.assert_not_called()
        assert sorted(blade.rule_store) == [RULE]
        module.exit_json.assert_called_once_with(changed=True)

    def test_delete_missing_rule_in_check_mode_is_unchanged(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(state="absent")
        module.check_mode = True
        blade = _blade()

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        module.exit_json.assert_called_once_with(changed=False)

    def test_delete_rule_when_policy_is_missing_is_unchanged(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(state="absent")
        blade = _blade(policy_exists=False)

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        blade.get_buckets_bucket_access_policies_rules.assert_not_called()
        blade.delete_buckets_bucket_access_policies_rules.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_delete_rule_error_is_reported(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(state="absent")
        blade = _blade(rule_exists=True, delete_status=400)

        with patch(
            "plugins.modules.purefb_bucket_access.get_error_message",
            return_value="Internal error",
        ):
            _run(mock_ansible_module, mock_get_system, module, blade, "fail_json")

        assert module.fail_json.call_args[1]["msg"] == (
            "Failed to delete access policy rule rule1 for bucket bkt. "
            "Error: Internal error"
        )

    def test_delete_policy(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(state="absent", rule=None)
        blade = _blade()

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        blade.delete_buckets_bucket_access_policies.assert_called_once_with(
            bucket_names=[BUCKET]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_delete_missing_policy_is_unchanged(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(state="absent", rule=None)
        blade = _blade(policy_exists=False)

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        blade.delete_buckets_bucket_access_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_delete_policy_in_check_mode_writes_nothing(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(state="absent", rule=None)
        module.check_mode = True
        blade = _blade()

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        blade.delete_buckets_bucket_access_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_fleet_context_reaches_the_lookup_and_the_delete(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(state="absent", context="array-b")
        blade = _blade(rule_exists=True)

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        blade.get_buckets_bucket_access_policies.assert_called_once_with(
            bucket_names=[BUCKET], context_names=["array-b"]
        )
        blade.delete_buckets_bucket_access_policies_rules.assert_called_once_with(
            bucket_names=[BUCKET], names=[RULE], context_names=["array-b"]
        )


@patch("plugins.modules.purefb_bucket_access.LooseVersion", RealLooseVersion)
@patch("plugins.modules.purefb_bucket_access.HAS_PYPURECLIENT", True)
@patch("plugins.modules.purefb_bucket_access.get_rest_api_version", return_value="2.30")
@patch("plugins.modules.purefb_bucket_access.purefb_argument_spec", return_value={})
@patch("plugins.modules.purefb_bucket_access.get_system")
@patch("plugins.modules.purefb_bucket_access.AnsibleModule")
class TestCors:
    """CORS rules follow the same lookup, replace and delete flow."""

    def test_create_posts_policy_then_rule(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(policy_type="cors")
        blade = _cors_blade(policy_exists=False)

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        blade.post_buckets_cross_origin_resource_sharing_policies.assert_called_once_with(
            bucket_names=[BUCKET]
        )
        assert _write_sequence(blade, _CORS_RULES) == [("post", RULE)]
        blade.get_object_store_access_policy_actions.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_matching_rule_is_idempotent(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(policy_type="cors")
        blade = _cors_blade(rule_exists=True)

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        assert _write_sequence(blade, _CORS_RULES) == []
        module.exit_json.assert_called_once_with(changed=False)

    def test_refused_replacement_keeps_the_existing_rule(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(policy_type="cors", methods=["GET"])
        blade = _cors_blade(rule_exists=True, post_status=400)

        with patch(
            "plugins.modules.purefb_bucket_access.get_error_message",
            return_value="Invalid rule for a bucket cross-origin resource sharing policy.",
        ):
            _run(mock_ansible_module, mock_get_system, module, blade, "fail_json")

        kwargs = module.fail_json.call_args[1]
        assert kwargs["msg"] == (
            "Failed to replace CORS policy rule rule1 in policy bkt: the array "
            "refused the new rule and the existing rule was left unchanged. "
            "Error: Invalid rule for a bucket cross-origin resource sharing policy."
        )
        assert "changed" not in kwargs
        assert _write_sequence(blade, _CORS_RULES) == [("post", TEMP)]
        assert blade.rule_store[RULE].allowed_methods == _ALL_METHODS

    def test_replacement_goes_through_a_temporary_rule(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(policy_type="cors", methods=["GET"])
        blade = _cors_blade(rule_exists=True, stored=_stored_cors_rule(methods=["GET"]))

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        assert _write_sequence(blade, _CORS_RULES) == [
            ("post", TEMP),
            ("delete", RULE),
            ("post", RULE),
            ("delete", TEMP),
        ]
        assert sorted(blade.rule_store) == [RULE]
        module.exit_json.assert_called_once_with(changed=True)

    def test_coerced_rule_is_reported(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(policy_type="cors", origins=["https://example.com"])
        blade = _cors_blade()

        _run(mock_ansible_module, mock_get_system, module, blade, "fail_json")

        kwargs = module.fail_json.call_args[1]
        assert kwargs["changed"] is True
        assert kwargs["msg"].startswith(
            "CORS policy rule rule1 in policy bkt was not stored as requested: "
            "the array kept methods="
        )
        assert "origins=['*']" in kwargs["msg"]

    def test_delete_missing_rule_is_unchanged(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(policy_type="cors", state="absent")
        blade = _cors_blade()

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        assert _write_sequence(blade, _CORS_RULES) == []
        module.exit_json.assert_called_once_with(changed=False)

    def test_delete_rule(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(policy_type="cors", state="absent")
        blade = _cors_blade(rule_exists=True)

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        blade.delete_buckets_cross_origin_resource_sharing_policies_rules.assert_called_once_with(
            bucket_names=[BUCKET], names=[RULE]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_delete_policy(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(policy_type="cors", state="absent", rule=None)
        blade = _cors_blade()

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        blade.delete_buckets_cross_origin_resource_sharing_policies.assert_called_once_with(
            bucket_names=[BUCKET]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_policy_read_error_fails(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(policy_type="cors", state="absent")
        blade = _cors_blade(policy_status=500)

        _run(mock_ansible_module, mock_get_system, module, blade, "fail_json")

        assert module.fail_json.call_args[1]["msg"].startswith(
            "Failed to read the CORS policy of bucket bkt."
        )
        blade.delete_buckets_cross_origin_resource_sharing_policies_rules.assert_not_called()


REALM_BUCKET = "realm1::bkt"


class TestAccessRuleResources:
    """Stored rule resources carry the bucket name without its realm."""

    @pytest.mark.parametrize(
        "bucket, stored, requested, expected",
        [
            ("bkt", ["bkt/*"], ["*"], True),
            (REALM_BUCKET, ["bkt/*"], ["*"], True),
            (REALM_BUCKET, ["bkt/b/*", "bkt/a/*"], ["a/*", "b/*"], True),
            (REALM_BUCKET, ["other/*"], ["*"], False),
            (REALM_BUCKET, ["bkt/logs/*"], ["*"], False),
            ("bkt", ["bkt/logs/*"], ["*"], False),
        ],
    )
    def test_stored_resources_are_compared_with_the_bare_bucket_name(
        self, bucket, stored, requested, expected
    ):
        module = _module(name=bucket, resources=requested)
        rule = _stored_rule(resources=stored)

        assert _ACCESS_RULES["matches"](module, rule) is expected


@patch("plugins.modules.purefb_bucket_access.LooseVersion", RealLooseVersion)
@patch("plugins.modules.purefb_bucket_access.HAS_PYPURECLIENT", True)
@patch("plugins.modules.purefb_bucket_access.get_rest_api_version", return_value="2.30")
@patch("plugins.modules.purefb_bucket_access.purefb_argument_spec", return_value={})
@patch("plugins.modules.purefb_bucket_access.get_system")
@patch("plugins.modules.purefb_bucket_access.AnsibleModule")
class TestRealmBucket:
    """A bucket in a realm is named realm::bucket.

    The array accepts a rule resource only with the full bucket name and
    stores it with the bucket name without the realm: the rules of
    realm1::bkt read back with resources ["bkt/*"], exactly as those of an
    array-level bucket bkt do.
    """

    def test_matching_rule_is_idempotent(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(name=REALM_BUCKET)
        blade = _blade(bucket=REALM_BUCKET, rule_exists=True)

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        assert _write_sequence(blade, _ACCESS_RULES) == []
        blade.get_buckets_bucket_access_policies_rules.assert_called_once_with(
            bucket_names=[REALM_BUCKET]
        )
        module.exit_json.assert_called_once_with(changed=False)

    def test_matching_rule_in_check_mode_is_unchanged(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(name=REALM_BUCKET)
        module.check_mode = True
        blade = _blade(bucket=REALM_BUCKET, rule_exists=True)

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        assert _write_sequence(blade, _ACCESS_RULES) == []
        module.exit_json.assert_called_once_with(changed=False)

    def test_create_sends_the_realm_and_accepts_the_stored_rule(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(name=REALM_BUCKET)
        blade = _blade(bucket=REALM_BUCKET, policy_exists=False)

        with patch(
            "plugins.modules.purefb_bucket_access.BucketAccessPolicyRulePost"
        ) as mock_body:
            _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        # The array refuses "bkt/*" in the request for a bucket in a realm.
        assert mock_body.call_args[1]["resources"] == ["realm1::bkt/*"]
        blade.post_buckets_bucket_access_policies.assert_called_once_with(
            bucket_names=[REALM_BUCKET]
        )
        posted = blade.post_buckets_bucket_access_policies_rules.call_args[1]
        assert posted["bucket_names"] == [REALM_BUCKET]
        assert posted["names"] == [RULE]
        assert posted["rule"] is mock_body.return_value
        module.fail_json.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_create_in_check_mode_writes_nothing(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(name=REALM_BUCKET)
        module.check_mode = True
        blade = _blade(bucket=REALM_BUCKET)

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        assert _write_sequence(blade, _ACCESS_RULES) == []
        module.exit_json.assert_called_once_with(changed=True)

    def test_differing_rule_is_replaced(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(name=REALM_BUCKET)
        blade = _blade(
            bucket=REALM_BUCKET,
            rule_exists=True,
            existing=_stored_rule(all_principals=False),
        )

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        assert _write_sequence(blade, _ACCESS_RULES) == [
            ("post", TEMP),
            ("delete", RULE),
            ("post", RULE),
            ("delete", TEMP),
        ]
        module.exit_json.assert_called_once_with(changed=True)

    def test_coerced_rule_is_still_reported(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(
            name=REALM_BUCKET, actions=["s3:GetObject", "s3:PutObjectTagging"]
        )
        blade = _blade(
            bucket=REALM_BUCKET, stored=_stored_rule(actions=["s3:GetObject"])
        )

        _run(mock_ansible_module, mock_get_system, module, blade, "fail_json")

        kwargs = module.fail_json.call_args[1]
        assert kwargs["changed"] is True
        assert kwargs["msg"].startswith(
            "Access policy rule rule1 in policy realm1::bkt was not stored as "
            "requested: the array kept actions=['s3:GetObject'], "
            "resources=['bkt/*'], all_principals=True."
        )

    def test_delete_rule(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(name=REALM_BUCKET, state="absent")
        blade = _blade(bucket=REALM_BUCKET, rule_exists=True)

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        blade.delete_buckets_bucket_access_policies_rules.assert_called_once_with(
            bucket_names=[REALM_BUCKET], names=[RULE]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_delete_policy(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(name=REALM_BUCKET, state="absent", rule=None)
        blade = _blade(bucket=REALM_BUCKET, rule_exists=True)

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        blade.delete_buckets_bucket_access_policies.assert_called_once_with(
            bucket_names=[REALM_BUCKET]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_cors_rule_is_created_and_then_unchanged(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        blade = _cors_blade(bucket=REALM_BUCKET, policy_exists=False)
        for expected in (True, False):
            module = _module(name=REALM_BUCKET, policy_type="cors")

            _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

            module.exit_json.assert_called_once_with(changed=expected)
        policies = blade.post_buckets_cross_origin_resource_sharing_policies
        policies.assert_called_once_with(bucket_names=[REALM_BUCKET])
        assert _write_sequence(blade, _CORS_RULES) == [("post", RULE)]


@patch("plugins.modules.purefb_bucket_access.LooseVersion", RealLooseVersion)
@patch("plugins.modules.purefb_bucket_access.HAS_PYPURECLIENT", True)
@patch("plugins.modules.purefb_bucket_access.get_rest_api_version", return_value="2.30")
@patch("plugins.modules.purefb_bucket_access.purefb_argument_spec", return_value={})
@patch("plugins.modules.purefb_bucket_access.get_system")
@patch("plugins.modules.purefb_bucket_access.AnsibleModule")
class TestStoredBucketName:
    """The bucket is read once and its stored name is used from then on.

    The array finds a bucket whatever the letter case of the name and
    returns the stored spelling; a rule resource with any other spelling of
    the bucket name is refused.
    """

    def test_other_letter_case_matches_the_stored_rule(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(name="BKT")
        blade = _blade(rule_exists=True)

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        blade.get_buckets.assert_called_once_with(names=["BKT"], destroyed=False)
        assert _write_sequence(blade, _ACCESS_RULES) == []
        module.exit_json.assert_called_once_with(changed=False)

    def test_other_letter_case_posts_the_stored_spelling(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(name="REALM1::Bkt")
        blade = _blade(bucket=REALM_BUCKET)

        with patch(
            "plugins.modules.purefb_bucket_access.BucketAccessPolicyRulePost"
        ) as mock_body:
            _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        assert mock_body.call_args[1]["resources"] == ["realm1::bkt/*"]
        module.exit_json.assert_called_once_with(changed=True)

    @pytest.mark.parametrize(
        "error", ["Bucket does not exist.", "Bucket has been destroyed."]
    )
    def test_missing_or_destroyed_bucket_is_reported_as_absent(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version, error
    ):
        module = _module(name=REALM_BUCKET)
        blade = _blade()
        blade.get_buckets.return_value = _response(400)

        with patch(
            "plugins.modules.purefb_bucket_access.get_error_message",
            return_value=error,
        ):
            _run(mock_ansible_module, mock_get_system, module, blade, "fail_json")

        assert module.fail_json.call_args[1]["msg"] == (
            "Bucket realm1::bkt does not exist, or is destroyed."
        )
        blade.get_buckets_bucket_access_policies.assert_not_called()

    def test_refused_bucket_read_reports_the_array_message(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module()
        blade = _blade()
        blade.get_buckets.return_value = _response(403)

        with patch(
            "plugins.modules.purefb_bucket_access.get_error_message",
            return_value="Operation not permitted.",
        ):
            _run(mock_ansible_module, mock_get_system, module, blade, "fail_json")

        assert module.fail_json.call_args[1]["msg"] == (
            "Failed to read bucket bkt. Error: Operation not permitted."
        )
        blade.get_buckets_bucket_access_policies.assert_not_called()

    def test_empty_bucket_read_is_reported_as_absent(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module()
        blade = _blade()
        blade.get_buckets.return_value = _response(200, [])

        _run(mock_ansible_module, mock_get_system, module, blade, "fail_json")

        assert module.fail_json.call_args[1]["msg"] == (
            "Bucket bkt does not exist, or is destroyed."
        )
        blade.get_buckets_bucket_access_policies.assert_not_called()

    def test_fleet_context_reaches_the_bucket_read(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _module(context="array-b", state="absent")
        blade = _blade()

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        blade.get_buckets.assert_called_once_with(
            names=[BUCKET], destroyed=False, context_names=["array-b"]
        )

    def test_context_is_not_sent_below_rest_2_17(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        mock_version.return_value = "2.16"
        module = _module(context="array-b", state="absent")
        blade = _blade()

        _run(mock_ansible_module, mock_get_system, module, blade, "exit_json")

        blade.get_buckets.assert_called_once_with(names=[BUCKET], destroyed=False)
