# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_quota_policy module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from contextlib import contextmanager
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

from plugins.modules.purefb_quota_policy import (
    main,
    _context_kwargs,
    _match_rule,
    _normalise_rules,
)

MODULE = "plugins.modules.purefb_quota_policy"
GIB = 1073741824


def _base_params(**overrides):
    params = {
        "name": "qp1",
        "state": "present",
        "enabled": None,
        "rename": None,
        "import_from": None,
        "rules": None,
        "file_systems": None,
        "ignore_usage": False,
        "delete_existing_quotas": False,
        "context": "",
    }
    params.update(overrides)
    return params


def _rule_param(rule_type, quota_limit, enforced=True, notifications="account", **subj):
    rule = {
        "type": rule_type,
        "id": None,
        "name": None,
        "sid": None,
        "quota_limit": quota_limit,
        "enforced": enforced,
        "notifications": notifications,
    }
    rule.update(subj)
    return rule


def _module(params, check_mode=False):
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.warn = Mock()
    module.params = params
    module.check_mode = check_mode
    return module


def _response(status=200, items=None):
    res = Mock()
    res.status_code = status
    res.items = items if items is not None else []
    res.errors = []
    return res


def _array_rule(
    rule_name, quota_type, quota_limit, enforced=True, notifications="Account", **subj
):
    rule = Mock()
    rule.name = rule_name
    rule.id = rule_name + "-id"
    rule.quota_type = quota_type
    rule.quota_limit = quota_limit
    rule.enforced = enforced
    rule.notifications = notifications
    if subj:
        subject = Mock(spec=["id", "name", "sid"])
        subject.id = subj.get("id")
        subject.name = subj.get("name")
        subject.sid = subj.get("sid")
        rule.subject = subject
    else:
        rule.subject = None
    return rule


def _array_policy(name="qp1", enabled=True):
    policy = Mock()
    policy.name = name
    policy.enabled = enabled
    return policy


def _member(fs_name):
    item = Mock()
    item.member = Mock()
    item.member.name = fs_name
    return item


def _attached(policy_name):
    item = Mock()
    item.policy = Mock()
    item.policy.name = policy_name
    return item


WRITE_METHODS = (
    "post_user_group_quota_policies",
    "patch_user_group_quota_policies",
    "delete_user_group_quota_policies",
    "post_user_group_quota_policies_rules",
    "patch_user_group_quota_policies_rules",
    "delete_user_group_quota_policies_rules",
    "post_user_group_quota_policies_file_systems",
    "delete_user_group_quota_policies_file_systems",
)


def _blade(policy=None, rules=None, members=None, attached=None):
    blade = Mock()
    blade.get_versions.return_value.items = ["2.25"]
    blade.get_fleets.return_value = _response(200, [])
    blade.get_user_group_quota_policies.return_value = _response(
        200 if policy else 400, [policy] if policy else []
    )
    blade.get_user_group_quota_policies_rules.return_value = _response(
        200, list(rules or [])
    )
    blade.get_user_group_quota_policies_members.return_value = _response(
        200, [_member(name) for name in members or []]
    )
    blade.get_file_systems_user_group_quota_policies.return_value = _response(
        200, [_attached(attached)] if attached else []
    )
    for method in WRITE_METHODS:
        getattr(blade, method).return_value = _response(200)
    return blade


def _assert_no_writes(blade):
    for method in WRITE_METHODS:
        getattr(blade, method).assert_not_called()


@contextmanager
def _patched(module, blade, api_too_old=False, has_sdk=True):
    with patch(MODULE + ".AnsibleModule", return_value=module), patch(
        MODULE + ".get_system", return_value=blade
    ), patch(MODULE + ".LooseVersion") as loose_version, patch(
        MODULE + ".HAS_PYPURECLIENT", has_sdk
    ):
        loose_version.return_value.__gt__ = Mock(return_value=api_too_old)
        yield


def _run(module, blade, **kwargs):
    with _patched(module, blade, **kwargs):
        try:
            main()
        except SystemExit:
            pass


class TestPurefbQuotaPolicyHelpers:
    """Helper-function unit tests"""

    def test_context_kwargs_returns_empty_without_context(self):
        module = Mock()
        module.params = {"context": ""}
        assert _context_kwargs(module) == {}

    def test_context_kwargs_returns_kwargs_when_set(self):
        module = Mock()
        module.params = {"context": "peer1"}
        assert _context_kwargs(module) == {"context_names": ["peer1"]}

    def test_normalise_rules_none_when_omitted(self):
        module = _module(_base_params())
        assert _normalise_rules(module) is None

    def test_normalise_rules_converts_sizes_and_notifications(self):
        module = _module(
            _base_params(
                rules=[
                    _rule_param("user", "10G", id=1001),
                    _rule_param("group", "512M", notifications="none", name="devs"),
                    _rule_param("user-default", "1G", enforced=False),
                ]
            )
        )
        rules = _normalise_rules(module)
        assert rules[0] == {
            "type": "user",
            "field": "id",
            "value": 1001,
            "quota_limit": 10 * GIB,
            "enforced": True,
            "notifications": "Account",
        }
        assert rules[1]["field"] == "name"
        assert rules[1]["value"] == "devs"
        assert rules[1]["quota_limit"] == 512 * 1048576
        assert rules[1]["notifications"] == "None"
        assert rules[2]["field"] is None
        assert rules[2]["enforced"] is False

    def test_normalise_rules_rejects_default_type_with_subject(self):
        module = _module(_base_params(rules=[_rule_param("user-default", "1G", id=5)]))
        try:
            _normalise_rules(module)
        except SystemExit:
            pass
        assert "does not take a subject" in module.fail_json.call_args[1]["msg"]

    def test_normalise_rules_rejects_missing_subject(self):
        module = _module(_base_params(rules=[_rule_param("user", "1G")]))
        try:
            _normalise_rules(module)
        except SystemExit:
            pass
        assert "exactly one of" in module.fail_json.call_args[1]["msg"]

    def test_normalise_rules_rejects_group_sid(self):
        module = _module(
            _base_params(rules=[_rule_param("group", "1G", sid="S-1-5-21-1-2-3-500")])
        )
        try:
            _normalise_rules(module)
        except SystemExit:
            pass
        assert "SID based rules" in module.fail_json.call_args[1]["msg"]

    def test_normalise_rules_rejects_zero_limit(self):
        module = _module(_base_params(rules=[_rule_param("user", "0", id=1)]))
        try:
            _normalise_rules(module)
        except SystemExit:
            pass
        assert "greater than zero" in module.fail_json.call_args[1]["msg"]

    def test_normalise_rules_rejects_bad_size(self):
        module = _module(_base_params(rules=[_rule_param("user", "lots", id=1)]))
        try:
            _normalise_rules(module)
        except SystemExit:
            pass
        assert "Invalid quota_limit" in module.fail_json.call_args[1]["msg"]

    def test_normalise_rules_rejects_duplicate_subject(self):
        module = _module(
            _base_params(
                rules=[_rule_param("user", "1G", id=1), _rule_param("user", "2G", id=1)]
            )
        )
        try:
            _normalise_rules(module)
        except SystemExit:
            pass
        assert "Duplicate rule" in module.fail_json.call_args[1]["msg"]

    def test_match_rule_by_subject_and_default(self):
        by_id = _array_rule("qp1.1", "user", GIB, id=1001)
        by_name = _array_rule("qp1.2", "group", GIB, name="devs")
        default = _array_rule("qp1.3", "user-default", GIB)
        current = [by_id, by_name, default]
        assert (
            _match_rule({"type": "user", "field": "id", "value": 1001}, current)
            is by_id
        )
        assert (
            _match_rule({"type": "group", "field": "name", "value": "devs"}, current)
            is by_name
        )
        assert (
            _match_rule({"type": "user-default", "field": None, "value": None}, current)
            is default
        )
        assert (
            _match_rule({"type": "group", "field": "id", "value": 1001}, current)
            is None
        )


class TestPurefbQuotaPolicyMain:
    """main() flows"""

    def test_main_fails_on_unsupported_api_version(self):
        module = _module(_base_params())
        blade = _blade()
        _run(module, blade, api_too_old=True)
        module.fail_json.assert_called_once()
        assert "REST version not supported" in module.fail_json.call_args[1]["msg"]
        _assert_no_writes(blade)

    def test_main_fails_without_sdk(self):
        module = _module(_base_params())
        _run(module, _blade(), has_sdk=False)
        module.fail_json.assert_called_once()
        assert "py-pure-client" in module.fail_json.call_args[1]["msg"]

    def test_main_rejects_invalid_rules_before_any_write(self):
        module = _module(_base_params(rules=[_rule_param("user", "1G")]))
        blade = _blade()
        _run(module, blade)
        module.fail_json.assert_called_once()
        _assert_no_writes(blade)

    def test_main_creates_policy_with_rules_and_attachment(self):
        module = _module(
            _base_params(
                enabled=True,
                rules=[
                    _rule_param("user", "10G", id=1001),
                    _rule_param("group", "20G", id=1001, notifications="none"),
                ],
                file_systems=["fs1"],
            )
        )
        blade = _blade()
        with patch(MODULE + ".UserGroupQuotaPolicyPost") as policy_post, patch(
            MODULE + ".UserGroupQuotaPolicyRulePost"
        ) as rule_post, patch(MODULE + ".UserGroupQuotaSubject") as subject:
            _run(module, blade)
        policy_post.assert_called_once_with(enabled=True)
        blade.post_user_group_quota_policies.assert_called_once()
        post_kwargs = blade.post_user_group_quota_policies.call_args[1]
        assert post_kwargs["names"] == ["qp1"]
        assert "file_system_names" not in post_kwargs
        assert blade.post_user_group_quota_policies_rules.call_count == 2
        rule_kwargs = [call[1] for call in rule_post.call_args_list]
        assert rule_kwargs[0]["quota_type"] == "user"
        assert rule_kwargs[0]["quota_limit"] == 10 * GIB
        assert rule_kwargs[0]["notifications"] == "Account"
        assert rule_kwargs[1]["quota_type"] == "group"
        assert rule_kwargs[1]["notifications"] == "None"
        subject.assert_any_call(id=1001)
        for call in blade.post_user_group_quota_policies_rules.call_args_list:
            assert call[1]["policy_names"] == ["qp1"]
            assert call[1]["ignore_usage"] is True
        blade.post_user_group_quota_policies_file_systems.assert_called_once_with(
            policy_names=["qp1"], member_names=["fs1"]
        )
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_create_with_import_from_passes_file_system_names(self):
        module = _module(_base_params(import_from="home"))
        blade = _blade()
        _run(module, blade)
        post_kwargs = blade.post_user_group_quota_policies.call_args[1]
        assert post_kwargs["file_system_names"] == ["home"]
        blade.post_user_group_quota_policies_rules.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_create_passes_context(self):
        module = _module(_base_params(context="peer1"))
        blade = _blade()
        _run(module, blade)
        assert blade.post_user_group_quota_policies.call_args[1]["context_names"] == [
            "peer1"
        ]

    def test_main_create_check_mode_skips_writes(self):
        module = _module(
            _base_params(rules=[_rule_param("user", "1G", id=1)], file_systems=["fs1"]),
            check_mode=True,
        )
        blade = _blade()
        _run(module, blade)
        _assert_no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_create_fails_on_api_error(self):
        module = _module(_base_params())
        blade = _blade()
        blade.post_user_group_quota_policies.return_value = _response(400)
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert "Failed to create quota policy" in module.fail_json.call_args[1]["msg"]

    def test_main_rule_post_error_surfaces_array_message(self):
        module = _module(_base_params(rules=[_rule_param("user", "1G", id=1)]))
        blade = _blade()
        error = Mock()
        error.message = "current usage exceeds the quota limit"
        failed = _response(400)
        failed.errors = [error]
        blade.post_user_group_quota_policies_rules.return_value = failed
        with patch(MODULE + ".get_error_message", return_value=error.message):
            _run(module, blade)
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to add user id 1 rule to quota policy qp1" in msg
        assert "exceeds the quota limit" in msg
        # rule writes always send ignore_usage, so no hint is appended
        assert "ignore_usage=true" not in msg

    def test_main_idempotent_rerun_makes_no_writes(self):
        module = _module(
            _base_params(
                enabled=True,
                rules=[
                    _rule_param("user", "10G", id=1001),
                    _rule_param("group", "20G", name="devs", notifications="none"),
                    _rule_param("user-default", "1G"),
                ],
                file_systems=["fs1"],
            )
        )
        blade = _blade(
            policy=_array_policy(enabled=True),
            rules=[
                _array_rule("qp1.1", "user", 10 * GIB, id=1001, name=""),
                _array_rule(
                    "qp1.2", "group", 20 * GIB, notifications="None", name="devs"
                ),
                _array_rule("qp1.3", "user-default", GIB),
            ],
            members=["fs1"],
        )
        _run(module, blade)
        _assert_no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is False
        facts = module.exit_json.call_args[1]["policy"]
        assert facts["name"] == "qp1"
        assert facts["file_systems"] == ["fs1"]
        assert facts["rules"][1]["notifications"] == "none"
        assert facts["rules"][0]["subject"]["id"] == 1001

    def test_main_update_enabled_patches_policy(self):
        module = _module(_base_params(enabled=False))
        blade = _blade(policy=_array_policy(enabled=True))
        with patch(MODULE + ".UserGroupQuotaPolicy") as policy_model:
            _run(module, blade)
        policy_model.assert_called_once_with(enabled=False)
        blade.patch_user_group_quota_policies.assert_called_once()
        kwargs = blade.patch_user_group_quota_policies.call_args[1]
        assert kwargs["names"] == ["qp1"]
        # the array refuses enable/disable without the flag, so it is always sent
        assert kwargs["ignore_usage"] is True
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_update_rule_limit_patches_rule_by_id(self):
        module = _module(_base_params(rules=[_rule_param("user", "15G", id=1001)]))
        blade = _blade(
            policy=_array_policy(),
            rules=[_array_rule("qp1.1", "user", 10 * GIB, id=1001)],
        )
        with patch(MODULE + ".UserGroupQuotaPolicyRulePatch") as rule_patch:
            _run(module, blade)
        # both patchable fields are always sent (the array resets an omitted one)
        rule_patch.assert_called_once_with(
            quota_limit=15 * GIB, notifications="Account"
        )
        blade.patch_user_group_quota_policies_rules.assert_called_once()
        kwargs = blade.patch_user_group_quota_policies_rules.call_args[1]
        assert kwargs["ids"] == ["qp1.1-id"]
        assert kwargs["ignore_usage"] is True
        blade.post_user_group_quota_policies_rules.assert_not_called()
        blade.delete_user_group_quota_policies_rules.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_update_rule_notifications_patches_with_ignore_usage(self):
        module = _module(
            _base_params(
                rules=[_rule_param("user", "10G", id=1001, notifications="none")],
                ignore_usage=True,
            )
        )
        blade = _blade(
            policy=_array_policy(),
            rules=[_array_rule("qp1.1", "user", 10 * GIB, id=1001)],
        )
        with patch(MODULE + ".UserGroupQuotaPolicyRulePatch") as rule_patch:
            _run(module, blade)
        rule_patch.assert_called_once_with(quota_limit=10 * GIB, notifications="None")
        kwargs = blade.patch_user_group_quota_policies_rules.call_args[1]
        assert kwargs["ignore_usage"] is True

    def test_main_update_enforced_change_replaces_rule(self):
        module = _module(
            _base_params(rules=[_rule_param("user", "10G", id=1001, enforced=False)])
        )
        blade = _blade(
            policy=_array_policy(),
            rules=[_array_rule("qp1.1", "user", 10 * GIB, id=1001, enforced=True)],
        )
        with patch(MODULE + ".UserGroupQuotaPolicyRulePost") as rule_post:
            _run(module, blade)
        blade.delete_user_group_quota_policies_rules.assert_called_once_with(
            ids=["qp1.1-id"], policy_names=["qp1"]
        )
        blade.post_user_group_quota_policies_rules.assert_called_once()
        assert rule_post.call_args[1]["enforced"] is False
        blade.patch_user_group_quota_policies_rules.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_update_deletes_unlisted_rule(self):
        module = _module(_base_params(rules=[_rule_param("user", "10G", id=1001)]))
        blade = _blade(
            policy=_array_policy(),
            rules=[
                _array_rule("qp1.1", "user", 10 * GIB, id=1001),
                _array_rule("qp1.2", "group", 10 * GIB, id=2001),
            ],
        )
        _run(module, blade)
        blade.delete_user_group_quota_policies_rules.assert_called_once_with(
            ids=["qp1.2-id"], policy_names=["qp1"]
        )
        blade.post_user_group_quota_policies_rules.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_update_rules_omitted_leaves_rules_alone(self):
        module = _module(_base_params())
        blade = _blade(
            policy=_array_policy(),
            rules=[_array_rule("qp1.1", "user", 10 * GIB, id=1001)],
        )
        _run(module, blade)
        _assert_no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is False

    def test_main_update_rules_check_mode_reports_without_writes(self):
        module = _module(
            _base_params(rules=[_rule_param("user", "15G", id=1001)]), check_mode=True
        )
        blade = _blade(
            policy=_array_policy(),
            rules=[_array_rule("qp1.1", "user", 10 * GIB, id=1001)],
        )
        _run(module, blade)
        _assert_no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_update_fails_when_rules_get_errors(self):
        module = _module(_base_params(rules=[_rule_param("user", "15G", id=1001)]))
        blade = _blade(policy=_array_policy())
        blade.get_user_group_quota_policies_rules.return_value = _response(400)
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert "Failed to get rules" in module.fail_json.call_args[1]["msg"]
        _assert_no_writes(blade)

    def test_main_attaches_missing_file_system(self):
        module = _module(_base_params(file_systems=["fs1", "fs2"]))
        blade = _blade(policy=_array_policy(), members=["fs1"])
        _run(module, blade)
        blade.post_user_group_quota_policies_file_systems.assert_called_once_with(
            policy_names=["qp1"], member_names=["fs2"]
        )
        blade.delete_user_group_quota_policies_file_systems.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_attach_passes_usage_and_delete_existing_flags(self):
        module = _module(
            _base_params(
                file_systems=["fs1"], ignore_usage=True, delete_existing_quotas=True
            )
        )
        blade = _blade(policy=_array_policy())
        _run(module, blade)
        kwargs = blade.post_user_group_quota_policies_file_systems.call_args[1]
        assert kwargs["ignore_usage"] is True
        assert kwargs["delete_existing_user_group_quota_settings"] is True

    def test_main_attach_refused_when_attached_to_another_policy(self):
        module = _module(_base_params(file_systems=["fs1"]))
        blade = _blade(policy=_array_policy(), attached="other")
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert "already attached to quota policy other" in (
            module.fail_json.call_args[1]["msg"]
        )
        blade.post_user_group_quota_policies_file_systems.assert_not_called()

    def test_main_attach_error_includes_legacy_quota_hint(self):
        module = _module(_base_params(file_systems=["fs1"]))
        blade = _blade(policy=_array_policy())
        blade.post_user_group_quota_policies_file_systems.return_value = _response(400)
        message = "Filesystem already has quotas configured from purequota"
        with patch(MODULE + ".get_error_message", return_value=message):
            _run(module, blade)
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to attach quota policy qp1 to file system fs1" in msg
        assert "delete_existing_quotas=true" in msg

    def test_main_attach_usage_refusal_gets_only_the_usage_hint(self):
        """The usage refusal mentions a quota limit, but only the
        ignore_usage hint applies to it."""
        module = _module(_base_params(file_systems=["fs1"]))
        blade = _blade(policy=_array_policy())
        blade.post_user_group_quota_policies_file_systems.return_value = _response(400)
        message = (
            "Current user/group usage can be higher than their provisioned "
            "quota limit. Please use ignore usage option to proceed."
        )
        with patch(MODULE + ".get_error_message", return_value=message):
            _run(module, blade)
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to attach quota policy qp1 to file system fs1" in msg
        assert "Set ignore_usage=true" in msg
        assert "delete_existing_quotas=true" not in msg

    def test_main_attach_sid_refusal_gets_no_hint(self):
        module = _module(_base_params(file_systems=["fs1"]))
        blade = _blade(policy=_array_policy())
        blade.post_user_group_quota_policies_file_systems.return_value = _response(400)
        message = (
            "Filesystem cannot be attached to a user-group-quota policy "
            "with SID based rules"
        )
        with patch(MODULE + ".get_error_message", return_value=message):
            _run(module, blade)
        msg = module.fail_json.call_args[1]["msg"]
        assert msg.endswith(message)

    def test_main_attach_fails_when_attached_policy_get_errors(self):
        module = _module(_base_params(file_systems=["fs1"]))
        blade = _blade(policy=_array_policy())
        blade.get_file_systems_user_group_quota_policies.return_value = _response(400)
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert "Failed to get the quota policy of file system fs1" in (
            module.fail_json.call_args[1]["msg"]
        )
        _assert_no_writes(blade)

    def test_main_fails_when_members_get_errors(self):
        module = _module(_base_params(file_systems=["fs1"]))
        blade = _blade(policy=_array_policy())
        blade.get_user_group_quota_policies_members.return_value = _response(400)
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert "Failed to get members of quota policy qp1" in (
            module.fail_json.call_args[1]["msg"]
        )
        _assert_no_writes(blade)

    def test_main_detaches_unlisted_file_system(self):
        module = _module(_base_params(file_systems=[]))
        blade = _blade(policy=_array_policy(), members=["fs1"])
        _run(module, blade)
        blade.delete_user_group_quota_policies_file_systems.assert_called_once_with(
            policy_names=["qp1"], member_names=["fs1"]
        )
        blade.post_user_group_quota_policies_file_systems.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_members_check_mode_reports_without_writes(self):
        module = _module(_base_params(file_systems=["fs1"]), check_mode=True)
        blade = _blade(policy=_array_policy())
        _run(module, blade)
        _assert_no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_rename_patches_name_last(self):
        module = _module(_base_params(rename="qp2"))
        blade = _blade(policy=_array_policy())
        with patch(MODULE + ".UserGroupQuotaPolicy") as policy_model:
            _run(module, blade)
        policy_model.assert_called_once_with(name="qp2")
        assert blade.patch_user_group_quota_policies.call_args[1]["names"] == ["qp1"]
        assert module.exit_json.call_args[1]["changed"] is True
        # the facts are read back under the new name
        blade.get_user_group_quota_policies.assert_called_with(names=["qp2"])

    def test_main_rename_already_applied_is_idempotent(self):
        module = _module(_base_params(rename="qp2"))
        blade = _blade()
        blade.get_user_group_quota_policies.side_effect = [
            _response(400),
            _response(200, [_array_policy(name="qp2")]),
            _response(200, [_array_policy(name="qp2")]),
        ]
        _run(module, blade)
        _assert_no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is False
        assert module.exit_json.call_args[1]["policy"]["name"] == "qp2"

    def test_main_delete_detaches_members_then_deletes(self):
        module = _module(_base_params(state="absent"))
        blade = _blade(policy=_array_policy(), members=["fs1", "fs2"])
        _run(module, blade)
        assert blade.delete_user_group_quota_policies_file_systems.call_count == 2
        detached = sorted(
            call[1]["member_names"][0]
            for call in blade.delete_user_group_quota_policies_file_systems.call_args_list
        )
        assert detached == ["fs1", "fs2"]
        blade.delete_user_group_quota_policies.assert_called_once_with(names=["qp1"])
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_delete_fails_on_api_error(self):
        module = _module(_base_params(state="absent"))
        blade = _blade(policy=_array_policy())
        blade.delete_user_group_quota_policies.return_value = _response(400)
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert "Failed to delete quota policy" in module.fail_json.call_args[1]["msg"]

    def test_main_delete_nonexistent_is_noop(self):
        module = _module(_base_params(state="absent"))
        blade = _blade()
        _run(module, blade)
        _assert_no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is False

    def test_main_delete_check_mode_skips_calls(self):
        module = _module(_base_params(state="absent"), check_mode=True)
        blade = _blade(policy=_array_policy(), members=["fs1"])
        _run(module, blade)
        _assert_no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_update_replace_failure_restores_original_rule(self):
        """When the re-add after a delete is rejected, the original rule is
        put back and the module fails with the array message."""
        module = _module(
            _base_params(rules=[_rule_param("user", "10G", id=1001, enforced=False)])
        )
        blade = _blade(
            policy=_array_policy(),
            rules=[_array_rule("qp1.1", "user", 10 * GIB, id=1001, enforced=True)],
        )
        rejected = _response(400)
        blade.post_user_group_quota_policies_rules.side_effect = [
            rejected,
            _response(200),
        ]
        message = "Policy cannot have unenforced rules."
        with patch(MODULE + ".UserGroupQuotaPolicyRulePost") as rule_post, patch(
            MODULE + ".get_error_message", return_value=message
        ):
            _run(module, blade)
        blade.delete_user_group_quota_policies_rules.assert_called_once_with(
            ids=["qp1.1-id"], policy_names=["qp1"]
        )
        assert blade.post_user_group_quota_policies_rules.call_count == 2
        first, second = [call[1] for call in rule_post.call_args_list]
        assert first["enforced"] is False
        assert second["enforced"] is True
        assert second["quota_limit"] == 10 * GIB
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to replace user id 1001 rule of quota policy qp1" in msg
        assert message in msg

    def test_main_update_patches_before_deleting(self):
        """Rule names renumber after a delete, so in-place patches (by id)
        are issued before any rule is removed."""
        module = _module(_base_params(rules=[_rule_param("user", "15G", id=1001)]))
        blade = _blade(
            policy=_array_policy(),
            rules=[
                _array_rule("qp1.1", "user", 10 * GIB, id=1001),
                _array_rule("qp1.2", "group", 10 * GIB, id=2001),
            ],
        )
        _run(module, blade)
        calls = [name for name, _args, _kwargs in blade.method_calls]
        assert calls.index("patch_user_group_quota_policies_rules") < calls.index(
            "delete_user_group_quota_policies_rules"
        )
        assert blade.patch_user_group_quota_policies_rules.call_args[1]["ids"] == [
            "qp1.1-id"
        ]
        assert blade.delete_user_group_quota_policies_rules.call_args[1]["ids"] == [
            "qp1.2-id"
        ]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_update_enable_attached_policy_always_skips_usage_check(self):
        """Enabling an attached policy also sends ignore_usage (array requirement)."""
        module = _module(_base_params(enabled=True))
        blade = _blade(policy=_array_policy(enabled=False), members=["fs1"])
        _run(module, blade)
        kwargs = blade.patch_user_group_quota_policies.call_args[1]
        assert kwargs["names"] == ["qp1"]
        assert kwargs["ignore_usage"] is True
        blade.post_user_group_quota_policies_file_systems.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_update_enable_attached_policy_with_ignore_usage(self):
        module = _module(_base_params(enabled=True, ignore_usage=True))
        blade = _blade(policy=_array_policy(enabled=False), members=["fs1"])
        _run(module, blade)
        kwargs = blade.patch_user_group_quota_policies.call_args[1]
        assert kwargs["ignore_usage"] is True
