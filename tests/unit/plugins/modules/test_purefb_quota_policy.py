# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_quota_policy module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import re
import sys
import multiprocessing
import ctypes
from contextlib import contextmanager
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

from plugins.modules.purefb_quota_policy import (
    main,
    _context_kwargs,
    _match_rule,
    _normalise_rules,
    _resolve_rename,
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
    policy.id = name + "-id"
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


class _Body:
    """Stands in for an SDK request model and keeps the fields it was given."""

    def __init__(self, **fields):
        self.__dict__.update(fields)


def _realm(name):
    return name.rpartition("::")[0]


def _by_name(blade, *policies, fold=False):
    """Make the policy endpoints behave as the array does; return its policies.

    A policy is found by its full name only. A PATCH that carries a name
    renames the policy: a new name without a realm keeps a realm policy in
    its realm, a name in another realm or a name that is taken is refused.
    A POST adds the named policy. A PATCH only takes effect when the request
    body is a _Body.

    With fold, names are matched without regard to case, as the array does,
    and kept in the case they were given. The realm of a new name has to be
    spelled as the realm in the name the request addresses the policy by,
    and a policy cannot be renamed to its own name in another case: that
    name is taken. The returned policies are then keyed by their lower-case
    names.
    """
    key = str.lower if fold else str
    known = dict((key(policy.name), policy) for policy in policies)

    def get_policies(**kwargs):
        policy = known.get(key(kwargs["names"][0]))
        return _response(200 if policy else 400, [policy] if policy else [])

    def patch_policies(**kwargs):
        asked = kwargs["names"][0]
        policy = known.get(key(asked))
        if policy is None:
            return _response(400)
        body = kwargs["policy"]
        new_name = getattr(body, "name", None)
        if isinstance(new_name, str):
            if "::" not in new_name and _realm(policy.name):
                new_name = "{0}::{1}".format(_realm(asked), new_name)
            if _realm(new_name) != _realm(asked) or key(new_name) in known:
                return _response(400)
            del known[key(policy.name)]
            if _realm(policy.name):
                # the realm is a reference and keeps its own spelling
                new_name = "{0}::{1}".format(
                    _realm(policy.name), new_name.rpartition("::")[2]
                )
            policy.name = new_name
            known[key(new_name)] = policy
        if isinstance(getattr(body, "enabled", None), bool):
            policy.enabled = body.enabled
        return _response(200, [policy])

    def post_policies(**kwargs):
        name = kwargs["names"][0]
        if key(name) in known:
            return _response(400)
        known[key(name)] = _array_policy(name)
        return _response(200, [known[key(name)]])

    blade.get_user_group_quota_policies.side_effect = get_policies
    blade.patch_user_group_quota_policies.side_effect = patch_policies
    blade.post_user_group_quota_policies.side_effect = post_policies
    return known


def _reference(ref_id, name):
    """A reference as the array lists it: an id and a name."""
    reference = Mock(spec=["id", "name"])
    reference.id = ref_id
    reference.name = name
    return reference


def _policy_rule(policy, uid, quota_limit, listed_as=None):
    """A user rule of policy.

    listed_as is the policy name the array lists the rule under when that is
    not the full name of the policy.
    """
    rule = _array_rule((listed_as or policy.name) + ".1", "user", quota_limit, id=uid)
    rule.id = "{0}-rule-{1}".format(policy.id, uid)
    rule.policy = _reference(policy.id, listed_as) if listed_as else policy
    return rule


def _rules_by_policy(blade, rules):
    """Answer the rules GET for a policy.id or a policy.name filter."""

    def get_rules(**kwargs):
        field, value = re.match(r"policy\.(id|name)='(.*)'$", kwargs["filter"]).groups()
        return _response(
            200, [rule for rule in rules if getattr(rule.policy, field) == value]
        )

    blade.get_user_group_quota_policies_rules.side_effect = get_rules


def _attachment(policy, member_id, member_name, listed_as=None):
    """An attachment of policy to a file system.

    member_name is the file system name the array lists and listed_as the
    policy name it lists when that is not the full name of the policy.
    """
    item = Mock(spec=["policy", "member"])
    item.policy = _reference(policy.id, listed_as) if listed_as else policy
    item.member = _reference(member_id, member_name)
    return item


def _attachments(blade, records):
    """Answer both attachment GETs by the ids and the names the array lists."""

    def get_members(**kwargs):
        found = list(records)
        for key, side, part in (
            ("policy_ids", "policy", "id"),
            ("policy_names", "policy", "name"),
            ("member_ids", "member", "id"),
            ("member_names", "member", "name"),
        ):
            if key in kwargs:
                found = [
                    record
                    for record in found
                    if getattr(getattr(record, side), part) in kwargs[key]
                ]
        return _response(200, found)

    blade.get_user_group_quota_policies_members.side_effect = get_members
    blade.get_file_systems_user_group_quota_policies.side_effect = get_members


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

    def test_main_create_attach_refusal_reports_policy_created(self):
        module = _module(_base_params(file_systems=["fs1"]))
        blade = _blade()
        blade.post_user_group_quota_policies_file_systems.return_value = _response(400)
        with patch(MODULE + ".get_error_message", return_value="refused"):
            _run(module, blade)
        blade.post_user_group_quota_policies.assert_called_once()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to attach quota policy qp1 to file system fs1" in msg
        assert msg.endswith(
            "refused The policy was created; fix the attachment and re-run."
        )

    def test_main_create_attach_refusal_keeps_hint_before_created_note(self):
        module = _module(_base_params(file_systems=["fs1"]))
        blade = _blade()
        blade.post_user_group_quota_policies_file_systems.return_value = _response(400)
        message = "Filesystem already has quotas configured from purequota"
        with patch(MODULE + ".get_error_message", return_value=message):
            _run(module, blade)
        msg = module.fail_json.call_args[1]["msg"]
        assert "delete_existing_quotas=true" in msg
        assert msg.index("delete_existing_quotas=true") < msg.index(
            "The policy was created"
        )

    def test_main_create_claimed_file_system_reports_policy_created(self):
        module = _module(_base_params(file_systems=["fs1"]))
        blade = _blade(attached="other")
        _run(module, blade)
        blade.post_user_group_quota_policies.assert_called_once()
        blade.post_user_group_quota_policies_file_systems.assert_not_called()
        msg = module.fail_json.call_args[1]["msg"]
        assert "already attached to quota policy other" in msg
        assert "The policy was created" in msg

    def test_main_create_rule_refusal_reports_policy_created(self):
        module = _module(_base_params(rules=[_rule_param("user", "1G", id=1)]))
        blade = _blade()
        blade.post_user_group_quota_policies_rules.return_value = _response(400)
        with patch(MODULE + ".get_error_message", return_value="refused"):
            _run(module, blade)
        blade.post_user_group_quota_policies.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to add user id 1 rule to quota policy qp1" in msg
        assert msg.endswith("refused The policy was created; fix rules and re-run.")

    def test_main_update_attach_refusal_has_no_created_note(self):
        module = _module(_base_params(file_systems=["fs1"]))
        blade = _blade(policy=_array_policy())
        blade.post_user_group_quota_policies_file_systems.return_value = _response(400)
        with patch(MODULE + ".get_error_message", return_value="refused"):
            _run(module, blade)
        blade.post_user_group_quota_policies.assert_not_called()
        msg = module.fail_json.call_args[1]["msg"]
        assert "The policy was created" not in msg
        assert msg.endswith("refused")

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

    def test_main_refused_attachment_leaves_the_others_attached(self):
        """A swap attaches the new file system first: when the array refuses
        it, the policy stays on the file system it had."""
        module = _module(_base_params(file_systems=["fs2"]))
        blade = _blade(policy=_array_policy(), members=["fs1"])
        blade.post_user_group_quota_policies_file_systems.return_value = _response(400)
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert "Failed to attach quota policy qp1 to file system fs2" in (
            module.fail_json.call_args[1]["msg"]
        )
        blade.delete_user_group_quota_policies_file_systems.assert_not_called()

    def test_main_swap_attaches_before_it_detaches(self):
        module = _module(_base_params(file_systems=["fs2"]))
        blade = _blade(policy=_array_policy(), members=["fs1"])
        _run(module, blade)
        calls = [
            (name, kwargs["member_names"])
            for name, _args, kwargs in blade.method_calls
            if name.endswith("_file_systems")
        ]
        assert calls == [
            ("post_user_group_quota_policies_file_systems", ["fs2"]),
            ("delete_user_group_quota_policies_file_systems", ["fs1"]),
        ]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_members_check_mode_reports_without_writes(self):
        module = _module(_base_params(file_systems=["fs1"]), check_mode=True)
        blade = _blade(policy=_array_policy())
        _run(module, blade)
        _assert_no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_rename_patches_name_last(self):
        module = _module(_base_params(rename="qp2"))
        blade = _blade()
        _by_name(blade, _array_policy())
        with patch(MODULE + ".UserGroupQuotaPolicy", side_effect=_Body) as policy_model:
            _run(module, blade)
        policy_model.assert_called_once_with(name="qp2")
        assert blade.patch_user_group_quota_policies.call_args[1]["names"] == ["qp1"]
        assert module.exit_json.call_args[1]["changed"] is True
        # the facts are read back under the new name
        assert module.exit_json.call_args[1]["policy"]["name"] == "qp2"

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
        blade.delete_user_group_quota_policies.assert_called_once_with(ids=["qp1-id"])
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


class TestPurefbQuotaPolicyRealm:
    """Realm policies (realm::name): rename resolution and lookups by policy id"""

    # ---- the name a rename resolves to

    def test_resolve_rename_none_without_rename(self):
        module = _module(_base_params(name="rz::qp1"))
        assert _resolve_rename(module) is None
        module.fail_json.assert_not_called()

    def test_resolve_rename_bare_name_takes_the_realm_of_the_policy(self):
        module = _module(_base_params(name="rz::qp1", rename="qp2"))
        assert _resolve_rename(module) == "rz::qp2"

    def test_resolve_rename_name_in_the_same_realm_is_kept(self):
        module = _module(_base_params(name="rz::qp1", rename="rz::qp2"))
        assert _resolve_rename(module) == "rz::qp2"

    def test_resolve_rename_bare_name_of_array_level_policy_is_kept(self):
        module = _module(_base_params(name="qp1", rename="qp2"))
        assert _resolve_rename(module) == "qp2"
        module.fail_json.assert_not_called()

    def test_resolve_rename_into_another_realm_fails(self):
        module = _module(_base_params(name="rz::qp1", rename="other::qp2"))
        with pytest.raises(SystemExit):
            _resolve_rename(module)
        msg = module.fail_json.call_args[1]["msg"]
        assert "Cannot rename quota policy rz::qp1 to other::qp2" in msg
        assert "cannot change the realm" in msg
        assert msg.endswith("Give the new name without a realm or as rz::<name>.")

    def test_resolve_rename_of_array_level_policy_into_a_realm_fails(self):
        module = _module(_base_params(name="qp1", rename="rz::qp2"))
        with pytest.raises(SystemExit):
            _resolve_rename(module)
        msg = module.fail_json.call_args[1]["msg"]
        assert "Cannot rename quota policy qp1 to rz::qp2" in msg
        assert msg.endswith("Give the new name without a realm.")

    # ---- rename of a realm policy

    def test_main_bare_rename_three_runs_stay_in_the_realm(self):
        """The array keeps a realm policy in its realm when the new name is
        bare. Runs 2 and 3 of the task must find it there, create no stray
        policy and leave the array-level policy of that bare name alone."""
        realm_policy = _array_policy("rz::qp1")
        namesake = _array_policy("qp2")
        blade = _blade()
        known = _by_name(blade, realm_policy, namesake)
        _rules_by_policy(
            blade,
            [
                _policy_rule(realm_policy, 1001, GIB),
                _policy_rule(namesake, 3003, 2 * GIB),
            ],
        )
        results = []
        with patch(MODULE + ".UserGroupQuotaPolicy", side_effect=_Body) as model:
            for _run_number in range(3):
                module = _module(
                    _base_params(
                        name="rz::qp1",
                        rename="qp2",
                        enabled=False,
                        rules=[_rule_param("user", "1G", id=1001)],
                    )
                )
                _run(module, blade)
                module.fail_json.assert_not_called()
                results.append(module.exit_json.call_args[1])
        assert [result["changed"] for result in results] == [True, False, False]
        assert [result["policy"]["name"] for result in results] == ["rz::qp2"] * 3
        assert [result["policy"]["enabled"] for result in results] == [False] * 3
        for result in results:
            assert [rule["subject"]["id"] for rule in result["policy"]["rules"]] == [
                1001
            ]
        # run 1 disabled the policy and sent the full new name; nothing after
        assert [call[1] for call in model.call_args_list] == [
            {"enabled": False},
            {"name": "rz::qp2"},
        ]
        assert sorted(known) == ["qp2", "rz::qp2"]
        assert namesake.enabled is True
        blade.post_user_group_quota_policies.assert_not_called()
        blade.post_user_group_quota_policies_rules.assert_not_called()
        blade.delete_user_group_quota_policies_rules.assert_not_called()
        for call in blade.get_user_group_quota_policies.call_args_list:
            assert call[1]["names"] != ["qp2"]

    def test_main_bare_rename_check_mode_is_honest(self):
        """Check mode reports the pending rename, writes nothing, and reports
        no change once the policy carries the new name in its realm."""
        blade = _blade()
        known = _by_name(blade, _array_policy("rz::qp1"), _array_policy("qp2"))
        params = dict(name="rz::qp1", rename="qp2")

        before = _module(_base_params(**params), check_mode=True)
        _run(before, blade)
        _assert_no_writes(blade)
        assert before.exit_json.call_args[1]["changed"] is True
        # check mode reports the state before the change
        assert before.exit_json.call_args[1]["policy"]["name"] == "rz::qp1"

        with patch(MODULE + ".UserGroupQuotaPolicy", side_effect=_Body):
            _run(_module(_base_params(**params)), blade)
        assert sorted(known) == ["qp2", "rz::qp2"]

        after = _module(_base_params(**params), check_mode=True)
        _run(after, blade)
        assert after.exit_json.call_args[1]["changed"] is False
        assert after.exit_json.call_args[1]["policy"]["name"] == "rz::qp2"

    def test_main_rename_with_the_full_name_of_the_realm(self):
        blade = _blade()
        known = _by_name(blade, _array_policy("rz::qp1"))
        results = []
        with patch(MODULE + ".UserGroupQuotaPolicy", side_effect=_Body) as model:
            for _run_number in range(2):
                module = _module(_base_params(name="rz::qp1", rename="rz::qp2"))
                _run(module, blade)
                results.append(module.exit_json.call_args[1])
        model.assert_called_once_with(name="rz::qp2")
        assert [result["changed"] for result in results] == [True, False]
        assert [result["policy"]["name"] for result in results] == ["rz::qp2"] * 2
        assert sorted(known) == ["rz::qp2"]

    def test_main_rename_to_own_leaf_name_is_a_noop(self):
        module = _module(_base_params(name="rz::qp1", rename="qp1"))
        blade = _blade()
        _by_name(blade, _array_policy("rz::qp1"))
        _run(module, blade)
        _assert_no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is False
        assert module.exit_json.call_args[1]["policy"]["name"] == "rz::qp1"

    def test_main_missing_realm_policy_with_rename_is_created_as_name(self):
        """Neither name exists: the policy is created as name, and the bare
        new name is never looked up at the array level."""
        module = _module(_base_params(name="rz::qp1", rename="qp2"))
        blade = _blade()
        known = _by_name(blade, _array_policy("qp2"))
        _run(module, blade)
        assert sorted(known) == ["qp2", "rz::qp1"]
        assert module.exit_json.call_args[1]["changed"] is True
        assert module.exit_json.call_args[1]["policy"]["name"] == "rz::qp1"
        blade.patch_user_group_quota_policies.assert_not_called()
        for call in blade.get_user_group_quota_policies.call_args_list:
            assert call[1]["names"] != ["qp2"]

    # ---- renames that are refused before anything is written

    def test_main_rename_into_another_realm_fails_before_any_call(self):
        module = _module(
            _base_params(name="rz::qp1", rename="other::qp2", enabled=False)
        )
        blade = _blade()
        _by_name(blade, _array_policy("rz::qp1", enabled=True))
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert "cannot change the realm" in module.fail_json.call_args[1]["msg"]
        blade.get_user_group_quota_policies.assert_not_called()
        _assert_no_writes(blade)

    def test_main_qualified_rename_of_array_level_policy_fails_before_any_call(self):
        module = _module(_base_params(rename="rz::qp2", enabled=False), check_mode=True)
        blade = _blade()
        _by_name(blade, _array_policy(enabled=True))
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert "Cannot rename quota policy qp1 to rz::qp2" in (
            module.fail_json.call_args[1]["msg"]
        )
        blade.get_user_group_quota_policies.assert_not_called()
        _assert_no_writes(blade)

    def test_main_rename_onto_existing_policy_fails_before_any_write(self):
        """enabled, rules and file_systems are applied before the rename, so
        a name that is taken has to be refused first."""
        module = _module(
            _base_params(
                rename="qp2",
                enabled=False,
                rules=[_rule_param("user", "1G", id=1001)],
                file_systems=["fs1"],
            )
        )
        blade = _blade()
        _by_name(blade, _array_policy("qp1", enabled=True), _array_policy("qp2"))
        _run(module, blade)
        module.fail_json.assert_called_once()
        assert module.fail_json.call_args[1]["msg"] == (
            "Cannot rename quota policy qp1 to qp2: "
            "a quota policy named qp2 already exists."
        )
        _assert_no_writes(blade)

    def test_main_bare_rename_onto_existing_realm_policy_is_never_sent(self):
        """The array answers a bare rename onto a realm policy with an
        unexpected error and then lists that policy's attachment without the
        realm, so the request must not reach it, in check mode or not."""
        for check_mode in (True, False):
            module = _module(
                _base_params(name="rz::qp1", rename="qp2", enabled=False),
                check_mode=check_mode,
            )
            blade = _blade()
            _by_name(blade, _array_policy("rz::qp1"), _array_policy("rz::qp2"))
            _run(module, blade)
            module.fail_json.assert_called_once()
            assert module.fail_json.call_args[1]["msg"] == (
                "Cannot rename quota policy rz::qp1 to rz::qp2: "
                "a quota policy named rz::qp2 already exists."
            )
            _assert_no_writes(blade)

    # ---- names that differ only in case

    def test_resolve_rename_keeps_one_spelling_of_the_realm(self):
        """The realm of the policy may be written in another case in rename;
        the resolved name carries the realm as name spells it."""
        for name, rename, sent in (
            ("RZ::qp1", "rz::qp2", "RZ::qp2"),
            ("rz::qp1", "RZ::qp2", "rz::qp2"),
            ("rz::qp1", "rz::qp2", "rz::qp2"),
        ):
            module = _module(_base_params(name=name, rename=rename))
            assert _resolve_rename(module) == sent
            module.fail_json.assert_not_called()

    def test_main_rename_with_the_realm_in_another_case_is_accepted(self):
        """The array compares the realm of the new name with the realm in the
        name the request addresses the policy by, as the two are written,
        and answers another spelling with "Realm can't be changed with
        rename." Both go out with the realm as the array keeps it."""
        for name, rename in (
            ("rz::qp1", "RZ::qp2"),
            ("RZ::qp1", "rz::qp2"),
            ("RZ::QP1", "qp2"),
            ("Rz::qp1", "rZ::qp2"),
        ):
            blade = _blade()
            known = _by_name(blade, _array_policy("rz::qp1"), fold=True)
            results = []
            with patch(MODULE + ".UserGroupQuotaPolicy", side_effect=_Body) as model:
                for _run_number in range(2):
                    module = _module(_base_params(name=name, rename=rename))
                    _run(module, blade)
                    module.fail_json.assert_not_called()
                    results.append(module.exit_json.call_args[1])
            model.assert_called_once_with(name="rz::qp2")
            assert blade.patch_user_group_quota_policies.call_args[1]["names"] == [
                "rz::qp1"
            ]
            assert [result["changed"] for result in results] == [True, False]
            assert [result["policy"]["name"] for result in results] == ["rz::qp2"] * 2
            assert sorted(known) == ["rz::qp2"]

    def test_main_rename_that_only_changes_the_case_fails_before_any_write(self):
        """The array matches names without regard to case, so the new name
        finds the policy itself, and it answers such a rename with "Policy
        already exists." That would come after enabled, rules and
        file_systems were applied, and check mode would report a change."""
        for name, rename, new_name in (
            ("qp1", "QP1", "QP1"),
            ("rz::qp1", "QP1", "rz::QP1"),
            ("rz::qp1", "RZ::Qp1", "rz::Qp1"),
            ("RZ::QP1", "Qp1", "RZ::Qp1"),
        ):
            realm = "rz::" if "::" in name else ""
            for check_mode in (True, False):
                module = _module(
                    _base_params(
                        name=name,
                        rename=rename,
                        enabled=False,
                        rules=[_rule_param("user", "1G", id=1001)],
                        file_systems=[realm + "fs1"],
                    ),
                    check_mode=check_mode,
                )
                blade = _blade()
                _by_name(blade, _array_policy(realm + "qp1", enabled=True), fold=True)
                _run(module, blade)
                module.fail_json.assert_called_once()
                assert module.fail_json.call_args[1]["msg"] == (
                    "Cannot rename quota policy {0} to {1}: the new name differs "
                    "from the name of the policy only in case. The array matches "
                    "names without regard to case and does not rename a policy "
                    "to its own name."
                ).format(name, new_name)
                _assert_no_writes(blade)

    def test_main_rename_to_the_name_as_the_array_keeps_it_is_a_noop(self):
        """name is written in another case than the array keeps and rename
        in the case it keeps: the policy already carries the new name."""
        for name, rename, kept in (
            ("QP1", "qp1", "qp1"),
            ("rz::QP1", "qp1", "rz::qp1"),
        ):
            module = _module(_base_params(name=name, rename=rename))
            blade = _blade()
            _by_name(blade, _array_policy(kept), fold=True)
            _run(module, blade)
            module.fail_json.assert_not_called()
            _assert_no_writes(blade)
            assert module.exit_json.call_args[1]["changed"] is False
            assert module.exit_json.call_args[1]["policy"]["name"] == kept

    def test_main_rename_to_own_name_in_another_realm_case_is_a_noop(self):
        """The realm is spelled in another case than the array keeps it."""
        module = _module(_base_params(name="RZ::qp1", rename="rz::qp1"))
        blade = _blade()
        _by_name(blade, _array_policy("rz::qp1"), fold=True)
        _run(module, blade)
        module.fail_json.assert_not_called()
        _assert_no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is False
        assert module.exit_json.call_args[1]["policy"]["name"] == "rz::qp1"

    def test_main_rename_onto_another_policy_in_another_case_fails(self):
        """A different policy that answers to the new name is still a name
        that is taken, whatever its case."""
        for check_mode in (True, False):
            module = _module(
                _base_params(name="qp1", rename="QP2", enabled=False),
                check_mode=check_mode,
            )
            blade = _blade()
            _by_name(blade, _array_policy("qp1"), _array_policy("qp2"), fold=True)
            _run(module, blade)
            module.fail_json.assert_called_once()
            assert module.fail_json.call_args[1]["msg"] == (
                "Cannot rename quota policy qp1 to QP2: "
                "a quota policy named QP2 already exists."
            )
            _assert_no_writes(blade)

    # ---- file systems: names in another case, and the scope of the policy

    def test_main_file_system_in_another_case_is_not_attached_again(self):
        """The array matches names without regard to case. Detaching the
        file system and attaching it again would be a change on every run."""
        for check_mode in (True, False):
            module = _module(
                _base_params(name="rz::qp1", file_systems=["RZ::FS1", "rz::fs2"]),
                check_mode=check_mode,
            )
            blade = _blade(
                policy=_array_policy("rz::qp1"), members=["rz::fs1", "rz::Fs2"]
            )
            _run(module, blade)
            module.fail_json.assert_not_called()
            _assert_no_writes(blade)
            blade.get_file_systems_user_group_quota_policies.assert_not_called()
            assert module.exit_json.call_args[1]["changed"] is False
            assert module.exit_json.call_args[1]["policy"]["file_systems"] == [
                "rz::Fs2",
                "rz::fs1",
            ]

    def test_main_file_system_listed_in_two_cases_is_attached_once(self):
        module = _module(_base_params(file_systems=["fs1", "FS1", "fs2"]))
        blade = _blade(policy=_array_policy(), members=["fs2"])
        _run(module, blade)
        blade.post_user_group_quota_policies_file_systems.assert_called_once_with(
            policy_names=["qp1"], member_names=["FS1"]
        )
        blade.delete_user_group_quota_policies_file_systems.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_own_policy_in_another_case_is_not_another_policy(self):
        """The file system names the policy it is attached to as the array
        keeps it, which may not be the case the task writes it in."""
        module = _module(_base_params(name="RZ::QP1", file_systems=["rz::fs1"]))
        blade = _blade(policy=_array_policy("rz::qp1"), attached="rz::qp1")
        _run(module, blade)
        module.fail_json.assert_not_called()
        blade.post_user_group_quota_policies_file_systems.assert_called_once_with(
            policy_names=["rz::qp1"], member_names=["rz::fs1"]
        )

    def test_main_file_system_is_sent_with_the_realm_as_the_array_keeps_it(self):
        """The array refuses a file system whose realm is not written as it
        keeps it ("must belong to the same realm"), so the policy and the
        file systems go out with the realm of the name the array keeps."""
        module = _module(
            _base_params(name="RZ::qp1", file_systems=["rz::FS2", "Rz::fs3"])
        )
        blade = _blade(policy=_array_policy("rz::qp1"), members=["rz::fs1"])
        _run(module, blade)
        module.fail_json.assert_not_called()
        blade.delete_user_group_quota_policies_file_systems.assert_called_once_with(
            policy_names=["rz::qp1"], member_names=["rz::fs1"]
        )
        assert [
            call[1]
            for call in blade.post_user_group_quota_policies_file_systems.call_args_list
        ] == [
            {"policy_names": ["rz::qp1"], "member_names": ["rz::FS2"]},
            {"policy_names": ["rz::qp1"], "member_names": ["rz::fs3"]},
        ]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_new_policy_goes_by_the_name_the_array_gave_it(self):
        """A policy created with the realm in another case is kept with the
        realm in its own spelling; its rules and attachments use that name."""
        module = _module(
            _base_params(
                name="RZ::qp1",
                rules=[_rule_param("user", "1G", id=1001)],
                file_systems=["RZ::fs1"],
            )
        )
        blade = _blade()
        blade.post_user_group_quota_policies.return_value = _response(
            200, [_array_policy("rz::qp1")]
        )
        _run(module, blade)
        module.fail_json.assert_not_called()
        assert blade.post_user_group_quota_policies.call_args[1]["names"] == ["RZ::qp1"]
        assert blade.post_user_group_quota_policies_rules.call_args[1][
            "policy_names"
        ] == ["rz::qp1"]
        blade.post_user_group_quota_policies_file_systems.assert_called_once_with(
            policy_names=["rz::qp1"], member_names=["rz::fs1"]
        )
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_writes_address_the_policy_by_the_name_the_array_keeps(self):
        module = _module(
            _base_params(
                name="RZ::QP1",
                enabled=False,
                rules=[
                    _rule_param("user", "1G", id=1001),
                    _rule_param("user", "1G", id=1002),
                ],
            )
        )
        policy = _array_policy("rz::qp1", enabled=True)
        blade = _blade(policy=policy, rules=[_array_rule("rz::qp1.1", "user", GIB)])
        _run(module, blade)
        module.fail_json.assert_not_called()
        assert blade.patch_user_group_quota_policies.call_args[1]["names"] == [
            "rz::qp1"
        ]
        for call in blade.post_user_group_quota_policies_rules.call_args_list:
            assert call[1]["policy_names"] == ["rz::qp1"]
        assert blade.delete_user_group_quota_policies_rules.call_args[1][
            "policy_names"
        ] == ["rz::qp1"]

    def test_main_delete_detaches_with_the_realm_as_the_array_keeps_it(self):
        module = _module(_base_params(name="RZ::QP1", state="absent"))
        blade = _blade(policy=_array_policy("rz::qp1"), members=["rz::fs1"])
        _run(module, blade)
        module.fail_json.assert_not_called()
        blade.delete_user_group_quota_policies_file_systems.assert_called_once_with(
            policy_names=["rz::qp1"], member_names=["rz::fs1"]
        )
        blade.delete_user_group_quota_policies.assert_called_once_with(
            ids=["rz::qp1-id"]
        )

    def test_main_file_system_outside_the_scope_fails_before_any_call(self):
        """The array refuses such an attachment, but only after enabled and
        rules were applied or a new policy was created, and check mode
        would report a change."""
        in_realm = (
            "a policy in realm rz can only be attached to file systems of "
            "that realm, named rz::<filesystem>"
        )
        array_level = (
            "an array-level policy can only be attached to file systems "
            "outside of any realm"
        )
        for name, file_systems, refused, reason in (
            ("rz::qp1", ["rz::fs1", "fs2"], "fs2", in_realm),
            ("rz::qp1", ["other::fs2"], "other::fs2", in_realm),
            ("qp1", ["fs1", "rz::fs2"], "rz::fs2", array_level),
        ):
            for check_mode in (True, False):
                for exists in (True, False):
                    module = _module(
                        _base_params(
                            name=name, file_systems=file_systems, enabled=False
                        ),
                        check_mode=check_mode,
                    )
                    blade = _blade(
                        policy=_array_policy(name) if exists else None,
                        members=[file_systems[0]] if exists else None,
                    )
                    _run(module, blade)
                    module.fail_json.assert_called_once()
                    assert module.fail_json.call_args[1]["msg"] == (
                        "Cannot attach quota policy {0} to file system {1}: {2}."
                    ).format(name, refused, reason)
                    blade.get_user_group_quota_policies.assert_not_called()
                    _assert_no_writes(blade)

    def test_main_file_system_of_the_realm_in_another_case_is_in_scope(self):
        module = _module(_base_params(name="rz::qp1", file_systems=["RZ::fs1"]))
        blade = _blade(policy=_array_policy("rz::qp1"))
        _run(module, blade)
        module.fail_json.assert_not_called()
        blade.post_user_group_quota_policies_file_systems.assert_called_once_with(
            policy_names=["rz::qp1"], member_names=["rz::fs1"]
        )

    def test_main_delete_does_not_check_the_scope_of_file_systems(self):
        module = _module(
            _base_params(name="rz::qp1", state="absent", file_systems=["fs1"])
        )
        blade = _blade(policy=_array_policy("rz::qp1"))
        _run(module, blade)
        module.fail_json.assert_not_called()
        blade.delete_user_group_quota_policies.assert_called_once_with(
            ids=["rz::qp1-id"]
        )

    # ---- rules the array lists without the realm of their policy

    def test_main_refused_write_of_rule_listed_without_realm_gets_a_hint(self):
        """After a rename that gave the new name without the realm the array
        lists the rules of a realm policy without it, and refuses to change
        or delete them until the policy is renamed with its full name."""
        for rules, refused, failure in (
            (
                [_rule_param("user", "2G", id=1001)],
                "patch_user_group_quota_policies_rules",
                "Failed to update rule qp2.1 of quota policy rz::qp2.",
            ),
            (
                [],
                "delete_user_group_quota_policies_rules",
                "Failed to delete rule qp2.1 from quota policy rz::qp2.",
            ),
        ):
            realm_policy = _array_policy("rz::qp2")
            blade = _blade()
            _by_name(blade, realm_policy)
            _rules_by_policy(
                blade, [_policy_rule(realm_policy, 1001, GIB, listed_as="qp2")]
            )
            getattr(blade, refused).return_value = _response(400)
            module = _module(_base_params(name="rz::qp2", rules=rules))
            with patch(
                MODULE + ".get_error_message",
                return_value="Before rule does not exist.",
            ):
                _run(module, blade)
            module.fail_json.assert_called_once()
            msg = module.fail_json.call_args[1]["msg"]
            assert msg.startswith(
                failure + " Error: Before rule does not exist. The array lists "
                "this rule without the realm of its policy"
            )
            assert msg.endswith("in a task of its own, restores the rule names.")

    def test_main_refused_write_of_rule_listed_with_its_policy_gets_no_hint(self):
        for name in ("rz::qp2", "qp2"):
            policy = _array_policy(name)
            blade = _blade()
            _by_name(blade, policy)
            _rules_by_policy(blade, [_policy_rule(policy, 1001, GIB)])
            blade.patch_user_group_quota_policies_rules.return_value = _response(400)
            module = _module(
                _base_params(name=name, rules=[_rule_param("user", "2G", id=1001)])
            )
            with patch(MODULE + ".get_error_message", return_value="Refused."):
                _run(module, blade)
            module.fail_json.assert_called_once()
            assert module.fail_json.call_args[1]["msg"] == (
                "Failed to update rule {0}.1 of quota policy {0}. Error: Refused."
            ).format(name)

    # ---- rules and attachments are read by policy id

    def test_main_rules_of_array_level_policy_exclude_realm_namesake(self):
        """The array can list the rule of a realm policy under the bare
        policy name, which is the name of an array-level policy; that rule
        must not be reported for, or removed from, the array-level policy."""
        realm_policy = _array_policy("rz::qp2")
        namesake = _array_policy("qp2")
        blade = _blade()
        _by_name(blade, realm_policy, namesake)
        _rules_by_policy(
            blade,
            [
                _policy_rule(realm_policy, 1001, GIB, listed_as="qp2"),
                _policy_rule(namesake, 3003, 2 * GIB),
            ],
        )
        module = _module(
            _base_params(name="qp2", rules=[_rule_param("user", "2G", id=3003)])
        )
        _run(module, blade)
        _assert_no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is False
        facts = module.exit_json.call_args[1]["policy"]
        assert [rule["subject"]["id"] for rule in facts["rules"]] == [3003]

    def test_main_rules_of_realm_policy_listed_without_realm_are_found(self):
        realm_policy = _array_policy("rz::qp2")
        namesake = _array_policy("qp2")
        blade = _blade()
        _by_name(blade, realm_policy, namesake)
        _rules_by_policy(
            blade,
            [
                _policy_rule(realm_policy, 1001, GIB, listed_as="qp2"),
                _policy_rule(namesake, 3003, 2 * GIB),
            ],
        )
        module = _module(
            _base_params(name="rz::qp2", rules=[_rule_param("user", "1G", id=1001)])
        )
        _run(module, blade)
        _assert_no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is False
        facts = module.exit_json.call_args[1]["policy"]
        assert [rule["subject"]["id"] for rule in facts["rules"]] == [1001]

    def test_main_members_of_array_level_policy_exclude_realm_namesake(self):
        """The array can list the attachment of a realm policy without the
        realm in either name; by name it then also answers for an array-level
        policy of that name, which is not attached to anything."""
        realm_policy = _array_policy("rz::qp2")
        namesake = _array_policy("qp2")
        blade = _blade()
        _by_name(blade, realm_policy, namesake)
        _attachments(
            blade, [_attachment(realm_policy, "fs1-id", "fs1", listed_as="qp2")]
        )
        module = _module(_base_params(name="qp2", file_systems=[]))
        _run(module, blade)
        _assert_no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is False
        assert module.exit_json.call_args[1]["policy"]["file_systems"] == []

    def test_main_members_of_realm_policy_listed_without_realm_are_qualified(self):
        realm_policy = _array_policy("rz::qp2")
        blade = _blade()
        _by_name(blade, realm_policy)
        _attachments(
            blade, [_attachment(realm_policy, "fs1-id", "fs1", listed_as="qp2")]
        )
        module = _module(_base_params(name="rz::qp2", file_systems=["rz::fs1"]))
        _run(module, blade)
        _assert_no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is False
        assert module.exit_json.call_args[1]["policy"]["file_systems"] == ["rz::fs1"]

    def test_main_delete_realm_policy_with_attachment_listed_without_realm(self):
        """The attachment is found by policy id and detached under the full
        names. rename is not used with state=absent, so its realm is not
        checked."""
        realm_policy = _array_policy("rz::qp2")
        blade = _blade()
        _by_name(blade, realm_policy)
        _attachments(
            blade, [_attachment(realm_policy, "fs1-id", "fs1", listed_as="qp2")]
        )
        module = _module(
            _base_params(name="rz::qp2", state="absent", rename="other::qp3")
        )
        _run(module, blade)
        module.fail_json.assert_not_called()
        blade.delete_user_group_quota_policies_file_systems.assert_called_once_with(
            policy_names=["rz::qp2"], member_names=["rz::fs1"]
        )
        blade.delete_user_group_quota_policies.assert_called_once_with(
            ids=["rz::qp2-id"]
        )
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_delete_array_level_policy_keeps_realm_namesake_attached(self):
        realm_policy = _array_policy("rz::qp2")
        namesake = _array_policy("qp2")
        blade = _blade()
        _by_name(blade, realm_policy, namesake)
        _attachments(
            blade, [_attachment(realm_policy, "fs1-id", "fs1", listed_as="qp2")]
        )
        module = _module(_base_params(name="qp2", state="absent"))
        _run(module, blade)
        module.fail_json.assert_not_called()
        blade.delete_user_group_quota_policies_file_systems.assert_not_called()
        blade.delete_user_group_quota_policies.assert_called_once_with(ids=["qp2-id"])
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_create_realm_policy_attaches_and_reads_members_by_id(self):
        module = _module(_base_params(name="rz::qp1", file_systems=["rz::fs1"]))
        blade = _blade()
        known = _by_name(blade)
        records = []
        _attachments(blade, records)

        def attach(**kwargs):
            policy = known[kwargs["policy_names"][0]]
            name = kwargs["member_names"][0]
            records.append(_attachment(policy, name + "-id", name))
            return _response(200)

        blade.post_user_group_quota_policies_file_systems.side_effect = attach
        _run(module, blade)
        assert sorted(known) == ["rz::qp1"]
        blade.post_user_group_quota_policies_file_systems.assert_called_once_with(
            policy_names=["rz::qp1"], member_names=["rz::fs1"]
        )
        blade.delete_user_group_quota_policies_file_systems.assert_not_called()
        assert [
            call[1]
            for call in blade.get_user_group_quota_policies_members.call_args_list
        ] == [{"policy_ids": ["rz::qp1-id"]}]
        assert module.exit_json.call_args[1]["changed"] is True
        assert module.exit_json.call_args[1]["policy"]["file_systems"] == ["rz::fs1"]

    # ---- array-level policies next to a realm namesake

    def test_main_array_level_rename_ignores_realm_namesake(self):
        """An array-level policy is renamed to a name that a realm policy
        carries inside its realm: the two names are different policies."""
        realm_policy = _array_policy("rz::qp2", enabled=False)
        blade = _blade()
        known = _by_name(blade, _array_policy("qp1"), realm_policy)
        results = []
        with patch(MODULE + ".UserGroupQuotaPolicy", side_effect=_Body) as model:
            for _run_number in range(2):
                module = _module(_base_params(name="qp1", rename="qp2", enabled=True))
                _run(module, blade)
                module.fail_json.assert_not_called()
                results.append(module.exit_json.call_args[1])
        model.assert_called_once_with(name="qp2")
        assert [result["changed"] for result in results] == [True, False]
        assert [result["policy"]["name"] for result in results] == ["qp2", "qp2"]
        assert sorted(known) == ["qp2", "rz::qp2"]
        assert realm_policy.enabled is False
        for call in blade.get_user_group_quota_policies.call_args_list:
            assert call[1]["names"] != ["rz::qp2"]
