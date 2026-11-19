# Copyright: (c) 2026, Pure Storage Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_mgmt_policy module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import fnmatch
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

from plugins.modules.purefb_mgmt_policy import (
    main,
    _ctx,
    _rule_key,
    _desired_rules_by_key,
    _validate_rules,
    _check_one_name,
    _find_realm,
    _get_policy,
    _get_current_rules,
    _members_attached,
    _resolve_realm_scopes,
    _build_post_rules,
    _inline_rules_differ,
    _reconcile_rules,
    create_policy,
    update_policy,
    delete_policy,
)


def _base_params(**overrides):
    """Return a full params dict with sane defaults, patched by overrides."""
    params = {
        "name": "tenant-a-ops",
        "state": "present",
        "enabled": None,
        "aggregation_strategy": None,
        "rules": None,
        "context": "",
    }
    params.update(overrides)
    return params


def _inline_rule(role, resource_type, name):
    """A rule as the array returns it inside the policy object (REST < 2.26)."""
    rule = Mock()
    rule.role = Mock()
    rule.role.name = role
    rule.scope = Mock()
    rule.scope.resource_type = resource_type
    rule.scope.name = name
    return rule


def _rule_spec(role, name="fb1", resource_type="arrays"):
    return {"role": role, "scope": {"name": name, "resource_type": resource_type}}


def _current_rule(role, name="fb1", resource_type="arrays", rule_id="rule-id-1"):
    """A rule as GET management-access-policies/rules returns it (REST 2.26+)."""
    rule = Mock()
    rule.id = rule_id
    rule.name = "tenant-a-ops.1"
    rule.role = Mock()
    rule.role.name = role
    rule.scope = Mock()
    rule.scope.name = name
    rule.scope.resource_type = resource_type
    return rule


def _ok():
    response = Mock()
    response.status_code = 200
    return response


class _Version:
    """Stand-in for LooseVersion so that a main() flow can take different
    branches at the policy (2.19) and per-rule (2.26) version gates."""

    def __init__(self, text):
        self.parts = tuple(int(part) for part in str(text).split("."))

    def __gt__(self, other):
        return self.parts > other.parts

    def __le__(self, other):
        return self.parts <= other.parts


class TestPurefbMgmtPolicy:
    """Test cases for purefb_mgmt_policy module"""

    # ---------------- _ctx tests ----------------

    def test_ctx_empty_when_context_unset(self):
        """Test _ctx returns {} when context is empty string"""
        mock_module = Mock()
        mock_module.params = {"context": ""}
        assert _ctx(mock_module, "2.19") == {}

    @patch("plugins.modules.purefb_mgmt_policy.LooseVersion")
    def test_ctx_returns_context_names_when_supported(self, mock_loose_version):
        """Test _ctx returns context_names dict when API supports it"""
        # CONTEXT_API_VERSION <= api_version → context is honored
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        mock_module = Mock()
        mock_module.params = {"context": "fleet1"}
        assert _ctx(mock_module, "2.19") == {"context_names": ["fleet1"]}

    @patch("plugins.modules.purefb_mgmt_policy.LooseVersion")
    def test_ctx_silently_drops_context_when_api_too_old(self, mock_loose_version):
        """Test _ctx returns {} when API is too old, even if context is set"""
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.params = {"context": "fleet1"}
        assert _ctx(mock_module, "2.16") == {}

    # ---------------- key / desired-key helpers ----------------

    def test_rule_key_is_normalized_tuple(self):
        """Test _rule_key lowercases all three parts of the identity tuple"""
        assert _rule_key("VIEWER", "arrays", "FB1") == ("viewer", "arrays", "fb1")
        assert _rule_key("viewer", "arrays", "fb1") == ("viewer", "arrays", "fb1")

    def test_desired_rules_by_key_builds_map(self):
        """Test _desired_rules_by_key maps identity keys to the original rule dicts"""
        rules = [
            {
                "role": "Viewer",
                "scope": {"name": "FB1", "resource_type": "arrays"},
            },
            {
                "role": "backup",
                "scope": {"name": "realm-a", "resource_type": "realms"},
            },
        ]
        by_key = _desired_rules_by_key(rules)
        assert set(by_key) == {
            ("viewer", "arrays", "fb1"),
            ("backup", "realms", "realm-a"),
        }
        # The user's spelling must be preserved in the mapped value.
        assert by_key[("viewer", "arrays", "fb1")]["role"] == "Viewer"
        assert by_key[("viewer", "arrays", "fb1")]["scope"]["name"] == "FB1"

    def test_desired_rules_by_key_first_spelling_wins(self):
        """Test _desired_rules_by_key collapses case-variant repeats keeping the first"""
        rules = [
            {"role": "viewer", "scope": {"name": "fb1", "resource_type": "arrays"}},
            {"role": "VIEWER", "scope": {"name": "FB1", "resource_type": "arrays"}},
        ]
        by_key = _desired_rules_by_key(rules)
        assert set(by_key) == {("viewer", "arrays", "fb1")}
        assert by_key[("viewer", "arrays", "fb1")]["role"] == "viewer"

    # ---------------- _validate_rules ----------------

    def test_validate_rules_rejects_duplicates(self):
        """Test _validate_rules fails on two rules with the same identity"""
        mock_module = Mock()
        mock_module.params = _base_params(
            rules=[
                {
                    "role": "viewer",
                    "scope": {"name": "fb1", "resource_type": "arrays"},
                },
                {
                    "role": "viewer",
                    "scope": {"name": "fb1", "resource_type": "arrays"},
                },
            ]
        )
        mock_module.fail_json = Mock(side_effect=SystemExit)

        try:
            _validate_rules(mock_module)
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "Duplicate rule" in msg
        assert "role=viewer" in msg
        assert "arrays/fb1" in msg

    def test_validate_rules_rejects_case_variant_duplicates(self):
        """Test _validate_rules treats case variants of the same rule as duplicates"""
        mock_module = Mock()
        mock_module.params = _base_params(
            rules=[
                {
                    "role": "viewer",
                    "scope": {"name": "fb1", "resource_type": "arrays"},
                },
                {
                    "role": "VIEWER",
                    "scope": {"name": "FB1", "resource_type": "arrays"},
                },
            ]
        )
        mock_module.fail_json = Mock(side_effect=SystemExit)

        try:
            _validate_rules(mock_module)
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert "Duplicate rule" in mock_module.fail_json.call_args[1]["msg"]

    def test_validate_rules_accepts_distinct_rules(self):
        """Test _validate_rules passes rules that differ in role or scope"""
        mock_module = Mock()
        mock_module.params = _base_params(
            rules=[
                {
                    "role": "viewer",
                    "scope": {"name": "fb1", "resource_type": "arrays"},
                },
                {
                    "role": "viewer",
                    "scope": {"name": "realm-a", "resource_type": "realms"},
                },
                {
                    "role": "storage",
                    "scope": {"name": "fb1", "resource_type": "arrays"},
                },
            ]
        )
        mock_module.fail_json = Mock(side_effect=SystemExit)

        _validate_rules(mock_module)
        mock_module.fail_json.assert_not_called()

    def test_validate_rules_noop_on_none_and_empty(self):
        """Test _validate_rules ignores rules=None and rules=[]"""
        mock_module = Mock()
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_module.params = _base_params(rules=None)
        _validate_rules(mock_module)

        mock_module.params = _base_params(rules=[])
        _validate_rules(mock_module)

        mock_module.fail_json.assert_not_called()

    # ---------------- _get_policy ----------------

    def test_get_policy_returns_first_item(self):
        """Test _get_policy returns the first policy when present"""
        mock_module = Mock()
        mock_module.params = _base_params()

        existing = Mock()
        existing.name = "tenant-a-ops"

        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        mock_blade.get_management_access_policies.return_value = get_response

        out = _get_policy(mock_module, mock_blade, {})
        assert out is existing
        mock_blade.get_management_access_policies.assert_called_once_with(
            names=["tenant-a-ops"]
        )

    def test_get_policy_returns_none_when_empty(self):
        """Test _get_policy returns None when items list is empty"""
        mock_module = Mock()
        mock_module.params = _base_params()

        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_management_access_policies.return_value = get_response

        assert _get_policy(mock_module, mock_blade, {}) is None

    @patch("plugins.modules.purefb_mgmt_policy.get_error_message")
    def test_get_policy_returns_none_when_policy_does_not_exist(self, mock_error):
        """Test _get_policy returns None when the array says the policy does not exist"""
        mock_error.return_value = "Management access policy does not exist."
        mock_module = Mock()
        mock_module.params = _base_params()

        mock_blade = Mock()
        get_response = Mock(spec=["status_code", "errors"])
        get_response.status_code = 400
        mock_blade.get_management_access_policies.return_value = get_response

        assert _get_policy(mock_module, mock_blade, {}) is None
        mock_module.fail_json.assert_not_called()

    def test_get_policy_forwards_context_kwargs(self):
        """Test _get_policy forwards context_names when provided by _ctx"""
        mock_module = Mock()
        mock_module.params = _base_params()

        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_management_access_policies.return_value = get_response

        _get_policy(mock_module, mock_blade, {"context_names": ["fleet1"]})
        mock_blade.get_management_access_policies.assert_called_once_with(
            names=["tenant-a-ops"], context_names=["fleet1"]
        )

    # ---------------- _get_current_rules ----------------

    def test_get_current_rules_returns_items(self):
        """Test _get_current_rules returns list of rule objects on 200"""
        mock_module = Mock()
        mock_module.params = _base_params()

        rule = Mock()
        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [rule]
        mock_blade.get_management_access_policies_rules.return_value = get_response

        out = _get_current_rules(mock_module, mock_blade, {})
        assert out == [rule]
        mock_blade.get_management_access_policies_rules.assert_called_once_with(
            policy_names=["tenant-a-ops"]
        )

    def test_get_current_rules_fails_on_error(self):
        """Test _get_current_rules calls fail_json on non-200"""
        mock_module = Mock()
        mock_module.params = _base_params()
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 400
        get_response.items = []
        mock_blade.get_management_access_policies_rules.return_value = get_response

        try:
            _get_current_rules(mock_module, mock_blade, {})
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert (
            "Failed to list rules for policy"
            in mock_module.fail_json.call_args[1]["msg"]
        )

    # ---------------- _members_attached ----------------

    def test_members_attached_true_when_items(self):
        """Test _members_attached returns True when at least one member is attached"""
        mock_module = Mock()
        mock_module.params = _base_params()

        member = Mock()
        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [member]
        mock_blade.get_management_access_policies_members.return_value = get_response

        assert _members_attached(mock_module, mock_blade, {}) is True

    def test_members_attached_false_when_empty(self):
        """Test _members_attached returns False when no members are attached"""
        mock_module = Mock()
        mock_module.params = _base_params()

        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_management_access_policies_members.return_value = get_response

        assert _members_attached(mock_module, mock_blade, {}) is False

    @patch("plugins.modules.purefb_mgmt_policy.get_error_message")
    def test_members_attached_fails_on_error(self, mock_error):
        """Test _members_attached fails on a non-200 instead of reporting no members"""
        mock_error.return_value = "Operation not permitted."
        mock_module = Mock()
        mock_module.params = _base_params()
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        get_response = Mock(spec=["status_code", "errors"])
        get_response.status_code = 400
        mock_blade.get_management_access_policies_members.return_value = get_response

        try:
            _members_attached(mock_module, mock_blade, {})
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once_with(
            msg=(
                "Failed to list members of policy tenant-a-ops. "
                "Error: Operation not permitted."
            )
        )

    # ---------------- _build_post_rules ----------------

    def test_build_post_rules_none_returns_none(self):
        """Test _build_post_rules returns None when rules is None"""
        assert _build_post_rules(None) is None

    @patch("plugins.modules.purefb_mgmt_policy.ManagementAccessPolicyRule")
    @patch("plugins.modules.purefb_mgmt_policy.ReferenceWritable")
    def test_build_post_rules_builds_list(self, mock_ref, mock_rule_cls):
        """Test _build_post_rules builds one ManagementAccessPolicyRule per input rule"""
        rules = [
            {"role": "viewer", "scope": {"name": "fb1", "resource_type": "arrays"}},
        ]
        out = _build_post_rules(rules)
        assert len(out) == 1
        mock_rule_cls.assert_called_once()

    @patch("plugins.modules.purefb_mgmt_policy.ManagementAccessPolicyRule")
    @patch("plugins.modules.purefb_mgmt_policy.ReferenceWritable")
    def test_build_post_rules_preserves_user_spelling(self, mock_ref, mock_rule_cls):
        """Test _build_post_rules sends the user's spelling verbatim on create"""
        rules = [
            {
                "role": "Backup-Operator",
                "scope": {"name": "Realm-A", "resource_type": "realms"},
            },
        ]
        _build_post_rules(rules)
        ref_calls = mock_ref.call_args_list
        assert any(c.kwargs.get("name") == "Backup-Operator" for c in ref_calls)
        assert any(
            c.kwargs.get("name") == "Realm-A"
            and c.kwargs.get("resource_type") == "realms"
            for c in ref_calls
        )

    # ---------------- _reconcile_rules ----------------

    def test_reconcile_none_returns_false(self):
        """Test _reconcile_rules returns False (untouched) when rules param is None"""
        mock_module = Mock()
        mock_module.params = _base_params(rules=None)
        mock_module.check_mode = False

        mock_blade = Mock()
        assert _reconcile_rules(mock_module, mock_blade, {}) is False
        mock_blade.get_management_access_policies_rules.assert_not_called()

    @patch("plugins.modules.purefb_mgmt_policy.ManagementAccessPolicyRule")
    @patch("plugins.modules.purefb_mgmt_policy.ReferenceWritable")
    def test_reconcile_adds_missing_rules(self, mock_ref, mock_rule_cls):
        """Test _reconcile_rules POSTs rules that are in desired but not on the blade"""
        mock_module = Mock()
        mock_module.params = _base_params(
            rules=[
                {
                    "role": "viewer",
                    "scope": {"name": "fb1", "resource_type": "arrays"},
                }
            ]
        )
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_management_access_policies_rules.return_value = get_response

        post_response = Mock()
        post_response.status_code = 200
        mock_blade.post_management_access_policies_rules.return_value = post_response

        changed = _reconcile_rules(mock_module, mock_blade, {})

        assert changed is True
        mock_blade.post_management_access_policies_rules.assert_called_once()
        mock_blade.delete_management_access_policies_rules.assert_not_called()

    def test_reconcile_removes_orphan_rules(self):
        """Test _reconcile_rules DELETEs rules that are on the blade but not in desired"""
        mock_module = Mock()
        mock_module.params = _base_params(
            rules=[
                {
                    "role": "viewer",
                    "scope": {"name": "fb1", "resource_type": "arrays"},
                }
            ]
        )
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        keep = Mock()
        keep.name = "rule-keep"
        keep.role = Mock()
        keep.role.name = "viewer"
        keep.scope = Mock()
        keep.scope.name = "fb1"
        keep.scope.resource_type = "arrays"

        drop = Mock()
        drop.name = "rule-drop"
        drop.id = "8a2f0c1e-9d4b-4e6a-b1c3-5f7e9a0d2b4c"
        drop.role = Mock()
        drop.role.name = "backup"
        drop.scope = Mock()
        drop.scope.name = "realm-a"
        drop.scope.resource_type = "realms"

        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [keep, drop]
        mock_blade.get_management_access_policies_rules.return_value = get_response

        delete_response = Mock()
        delete_response.status_code = 200
        mock_blade.delete_management_access_policies_rules.return_value = (
            delete_response
        )

        changed = _reconcile_rules(mock_module, mock_blade, {})

        assert changed is True
        mock_blade.delete_management_access_policies_rules.assert_called_once()
        call_kwargs = mock_blade.delete_management_access_policies_rules.call_args[1]
        # Rule names (<policy>.<index>) renumber when a lower-indexed rule
        # is deleted, so deleting by a snapshot name can remove the wrong
        # rule; the module must address rules by immutable id. The delete
        # endpoint also takes no policy_names parameter (SDK rejects it).
        assert call_kwargs["ids"] == [drop.id]
        assert "names" not in call_kwargs
        assert "policy_names" not in call_kwargs
        mock_blade.post_management_access_policies_rules.assert_not_called()

    def test_reconcile_idempotent_when_match(self):
        """Test _reconcile_rules makes no writes when desired matches current"""
        mock_module = Mock()
        mock_module.params = _base_params(
            rules=[
                {
                    "role": "viewer",
                    "scope": {"name": "fb1", "resource_type": "arrays"},
                }
            ]
        )
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        current = Mock()
        current.name = "rule-viewer"
        current.role = Mock()
        current.role.name = "viewer"
        current.scope = Mock()
        current.scope.name = "fb1"
        current.scope.resource_type = "arrays"

        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [current]
        mock_blade.get_management_access_policies_rules.return_value = get_response

        changed = _reconcile_rules(mock_module, mock_blade, {})

        assert changed is False
        mock_blade.post_management_access_policies_rules.assert_not_called()
        mock_blade.delete_management_access_policies_rules.assert_not_called()

    def test_reconcile_case_variant_is_idempotent(self):
        """Test _reconcile_rules treats a case variant of a stored rule as the same rule"""
        mock_module = Mock()
        mock_module.params = _base_params(
            rules=[
                {
                    "role": "VIEWER",
                    "scope": {"name": "FB1", "resource_type": "arrays"},
                }
            ]
        )
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        current = Mock()
        current.name = "rule-viewer"
        current.role = Mock()
        current.role.name = "viewer"
        current.scope = Mock()
        current.scope.name = "fb1"
        current.scope.resource_type = "arrays"

        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [current]
        mock_blade.get_management_access_policies_rules.return_value = get_response

        changed = _reconcile_rules(mock_module, mock_blade, {})

        # Before the fix this deleted and re-created the rule on every run.
        assert changed is False
        mock_blade.post_management_access_policies_rules.assert_not_called()
        mock_blade.delete_management_access_policies_rules.assert_not_called()

    @patch("plugins.modules.purefb_mgmt_policy.ManagementAccessPolicyRule")
    @patch("plugins.modules.purefb_mgmt_policy.ReferenceWritable")
    def test_reconcile_normalizes_array_side_spelling(self, mock_ref, mock_rule_cls):
        """Test the ARRAY-side case variant is matched: mixed list adds only the new rule"""
        mock_module = Mock()
        mock_module.params = _base_params(
            rules=[
                {
                    "role": "viewer",
                    "scope": {"name": "fb1", "resource_type": "arrays"},
                },
                {
                    "role": "backup",
                    "scope": {"name": "realm-a", "resource_type": "realms"},
                },
            ]
        )
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        # The stored rule carries the case-preserved spelling from the array.
        current = Mock()
        current.name = "rule-viewer"
        current.role = Mock()
        current.role.name = "Viewer"
        current.scope = Mock()
        current.scope.name = "FB1"
        current.scope.resource_type = "arrays"

        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [current]
        mock_blade.get_management_access_policies_rules.return_value = get_response

        post_response = Mock()
        post_response.status_code = 200
        mock_blade.post_management_access_policies_rules.return_value = post_response

        changed = _reconcile_rules(mock_module, mock_blade, {})

        # Only the genuinely new rule is added; the case-variant match is
        # neither deleted nor re-created.
        assert changed is True
        mock_blade.delete_management_access_policies_rules.assert_not_called()
        mock_blade.post_management_access_policies_rules.assert_called_once()
        ref_calls = mock_ref.call_args_list
        assert any(c.kwargs.get("name") == "backup" for c in ref_calls)
        assert not any(c.kwargs.get("name") == "viewer" for c in ref_calls)

    def test_reconcile_remove_failure_reports_stored_names(self):
        """Test a failed rule DELETE reports the array's stored spelling in the message"""
        mock_module = Mock()
        mock_module.params = _base_params(rules=[])
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        current = Mock()
        current.name = "rule-1"
        current.id = "rule-id-1"
        current.role = Mock()
        current.role.name = "Viewer"
        current.scope = Mock()
        current.scope.name = "FB1"
        current.scope.resource_type = "arrays"

        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [current]
        mock_blade.get_management_access_policies_rules.return_value = get_response

        delete_response = Mock()
        delete_response.status_code = 400
        delete_response.errors = []
        mock_blade.delete_management_access_policies_rules.return_value = (
            delete_response
        )

        try:
            _reconcile_rules(mock_module, mock_blade, {})
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "Failed to remove rule" in msg
        assert "role=Viewer" in msg
        assert "arrays/FB1" in msg

    @patch("plugins.modules.purefb_mgmt_policy.ManagementAccessPolicyRule")
    @patch("plugins.modules.purefb_mgmt_policy.ReferenceWritable")
    def test_reconcile_add_preserves_user_spelling(self, mock_ref, mock_rule_cls):
        """Test _reconcile_rules POSTs a new rule with the user's spelling, not the lowercased key"""
        mock_module = Mock()
        mock_module.params = _base_params(
            rules=[
                {
                    "role": "Backup-Operator",
                    "scope": {"name": "Realm-A", "resource_type": "realms"},
                }
            ]
        )
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_management_access_policies_rules.return_value = get_response

        post_response = Mock()
        post_response.status_code = 200
        mock_blade.post_management_access_policies_rules.return_value = post_response

        changed = _reconcile_rules(mock_module, mock_blade, {})

        assert changed is True
        ref_calls = mock_ref.call_args_list
        assert any(c.kwargs.get("name") == "Backup-Operator" for c in ref_calls)
        assert any(
            c.kwargs.get("name") == "Realm-A"
            and c.kwargs.get("resource_type") == "realms"
            for c in ref_calls
        )

    def test_reconcile_empty_desired_removes_all(self):
        """Test _reconcile_rules with rules=[] deletes every existing rule"""
        mock_module = Mock()
        mock_module.params = _base_params(rules=[])
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        current = Mock()
        current.name = "rule-1"
        current.role = Mock()
        current.role.name = "viewer"
        current.scope = Mock()
        current.scope.name = "fb1"
        current.scope.resource_type = "arrays"

        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [current]
        mock_blade.get_management_access_policies_rules.return_value = get_response

        delete_response = Mock()
        delete_response.status_code = 200
        mock_blade.delete_management_access_policies_rules.return_value = (
            delete_response
        )

        changed = _reconcile_rules(mock_module, mock_blade, {})

        assert changed is True
        mock_blade.delete_management_access_policies_rules.assert_called_once()

    def test_reconcile_check_mode_skips_writes(self):
        """Test _reconcile_rules reports changed but skips writes in check mode"""
        mock_module = Mock()
        mock_module.params = _base_params(
            rules=[
                {
                    "role": "viewer",
                    "scope": {"name": "fb1", "resource_type": "arrays"},
                }
            ]
        )
        mock_module.check_mode = True

        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_management_access_policies_rules.return_value = get_response

        changed = _reconcile_rules(mock_module, mock_blade, {})

        assert changed is True
        mock_blade.post_management_access_policies_rules.assert_not_called()
        mock_blade.delete_management_access_policies_rules.assert_not_called()

    @patch("plugins.modules.purefb_mgmt_policy.ManagementAccessPolicyRule")
    @patch("plugins.modules.purefb_mgmt_policy.ReferenceWritable")
    def test_reconcile_add_failure_calls_fail_json(self, mock_ref, mock_rule_cls):
        """Test _reconcile_rules surfaces backend errors on add via fail_json"""
        mock_module = Mock()
        mock_module.params = _base_params(
            rules=[
                {
                    "role": "viewer",
                    "scope": {"name": "fb1", "resource_type": "arrays"},
                }
            ]
        )
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_management_access_policies_rules.return_value = get_response

        post_response = Mock()
        post_response.status_code = 400
        post_response.errors = []
        mock_blade.post_management_access_policies_rules.return_value = post_response

        try:
            _reconcile_rules(mock_module, mock_blade, {})
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert "Failed to add rule" in mock_module.fail_json.call_args[1]["msg"]

    # ---------------- create_policy ----------------

    @patch("plugins.modules.purefb_mgmt_policy.ManagementAccessPolicyPost")
    def test_create_policy_defaults_enabled_true(self, mock_post_cls):
        """Test create_policy sends enabled=True when the caller didn't specify"""
        mock_module = Mock()
        mock_module.params = _base_params(enabled=None)
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        post_response = Mock()
        post_response.status_code = 200
        mock_blade.post_management_access_policies.return_value = post_response

        try:
            create_policy(mock_module, mock_blade, {})
        except SystemExit:
            pass

        mock_post_cls.assert_called_once()
        assert mock_post_cls.call_args[1]["enabled"] is True
        assert "aggregation_strategy" not in mock_post_cls.call_args[1]
        assert "rules" not in mock_post_cls.call_args[1]
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_mgmt_policy.ManagementAccessPolicyPost")
    def test_create_policy_includes_aggregation_and_rules(self, mock_post_cls):
        """Test create_policy passes aggregation_strategy and rules when provided"""
        mock_module = Mock()
        mock_module.params = _base_params(
            enabled=False,
            aggregation_strategy="least-common-permission",
            rules=[
                {
                    "role": "viewer",
                    "scope": {"name": "fb1", "resource_type": "arrays"},
                }
            ],
        )
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        post_response = Mock()
        post_response.status_code = 200
        mock_blade.post_management_access_policies.return_value = post_response

        try:
            create_policy(mock_module, mock_blade, {})
        except SystemExit:
            pass

        kw = mock_post_cls.call_args[1]
        assert kw["enabled"] is False
        assert kw["aggregation_strategy"] == "least-common-permission"
        assert len(kw["rules"]) == 1

    def test_create_policy_check_mode_skips_post(self):
        """Test create_policy reports changed but skips POST in check mode"""
        mock_module = Mock()
        mock_module.params = _base_params()
        mock_module.check_mode = True
        mock_module.exit_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()

        try:
            create_policy(mock_module, mock_blade, {})
        except SystemExit:
            pass

        mock_blade.post_management_access_policies.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_mgmt_policy.ManagementAccessPolicyPost")
    def test_create_policy_failure_calls_fail_json(self, mock_post_cls):
        """Test create_policy surfaces backend errors via fail_json"""
        mock_module = Mock()
        mock_module.params = _base_params()
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        post_response = Mock()
        post_response.status_code = 400
        post_response.errors = []
        mock_blade.post_management_access_policies.return_value = post_response

        try:
            create_policy(mock_module, mock_blade, {})
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert "Failed to create policy" in mock_module.fail_json.call_args[1]["msg"]

    # ---------------- update_policy ----------------

    @patch("plugins.modules.purefb_mgmt_policy.ManagementAccessPolicy")
    def test_update_policy_patches_enabled(self, mock_patch_cls):
        """Test update_policy PATCHes when enabled differs"""
        mock_module = Mock()
        mock_module.params = _base_params(enabled=False)
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        existing = Mock()
        existing.enabled = True
        existing.aggregation_strategy = None

        mock_blade = Mock()
        patch_response = Mock()
        patch_response.status_code = 200
        mock_blade.patch_management_access_policies.return_value = patch_response

        try:
            update_policy(mock_module, mock_blade, {}, existing)
        except SystemExit:
            pass

        mock_blade.patch_management_access_policies.assert_called_once()
        assert mock_patch_cls.call_args[1] == {"enabled": False}
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_mgmt_policy.ManagementAccessPolicy")
    def test_update_policy_patches_aggregation_strategy(self, mock_patch_cls):
        """Test update_policy PATCHes when aggregation_strategy differs"""
        mock_module = Mock()
        mock_module.params = _base_params(
            aggregation_strategy="least-common-permission"
        )
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        existing = Mock()
        existing.enabled = True
        existing.aggregation_strategy = "all-permissions"

        mock_blade = Mock()
        patch_response = Mock()
        patch_response.status_code = 200
        mock_blade.patch_management_access_policies.return_value = patch_response

        try:
            update_policy(mock_module, mock_blade, {}, existing)
        except SystemExit:
            pass

        mock_blade.patch_management_access_policies.assert_called_once()
        assert (
            mock_patch_cls.call_args[1]["aggregation_strategy"]
            == "least-common-permission"
        )

    def test_update_policy_idempotent_when_no_diff(self):
        """Test update_policy exits changed=False when nothing differs"""
        mock_module = Mock()
        mock_module.params = _base_params(enabled=True, aggregation_strategy=None)
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)

        existing = Mock()
        existing.enabled = True
        existing.aggregation_strategy = None

        mock_blade = Mock()

        try:
            update_policy(mock_module, mock_blade, {}, existing)
        except SystemExit:
            pass

        mock_blade.patch_management_access_policies.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is False

    def test_update_policy_check_mode_skips_patch(self):
        """Test update_policy reports changed but skips PATCH in check mode"""
        mock_module = Mock()
        mock_module.params = _base_params(enabled=False)
        mock_module.check_mode = True
        mock_module.exit_json = Mock(side_effect=SystemExit)

        existing = Mock()
        existing.enabled = True
        existing.aggregation_strategy = None

        mock_blade = Mock()

        try:
            update_policy(mock_module, mock_blade, {}, existing)
        except SystemExit:
            pass

        mock_blade.patch_management_access_policies.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    # ---------------- delete_policy ----------------

    def test_delete_policy_fails_when_members_attached(self):
        """Test delete_policy fails with a hand-off message when members are attached"""
        mock_module = Mock()
        mock_module.params = _base_params(state="absent")
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.exit_json = Mock(side_effect=SystemExit)

        member = Mock()
        mock_blade = Mock()
        members_response = Mock()
        members_response.status_code = 200
        members_response.items = [member]
        mock_blade.get_management_access_policies_members.return_value = (
            members_response
        )

        try:
            delete_policy(mock_module, mock_blade, {})
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "is attached to one or more members" in msg
        assert "purefb_mgmt_role" in msg
        mock_blade.delete_management_access_policies.assert_not_called()

    def test_delete_policy_success(self):
        """Test delete_policy DELETEs when no members are attached"""
        mock_module = Mock()
        mock_module.params = _base_params(state="absent")
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.exit_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        members_response = Mock()
        members_response.status_code = 200
        members_response.items = []
        mock_blade.get_management_access_policies_members.return_value = (
            members_response
        )

        delete_response = Mock()
        delete_response.status_code = 200
        mock_blade.delete_management_access_policies.return_value = delete_response

        try:
            delete_policy(mock_module, mock_blade, {})
        except SystemExit:
            pass

        mock_blade.delete_management_access_policies.assert_called_once_with(
            names=["tenant-a-ops"]
        )
        assert mock_module.exit_json.call_args[1]["changed"] is True

    def test_delete_policy_check_mode_skips_delete(self):
        """Test delete_policy reports changed but skips DELETE in check mode"""
        mock_module = Mock()
        mock_module.params = _base_params(state="absent")
        mock_module.check_mode = True
        mock_module.exit_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        members_response = Mock()
        members_response.status_code = 200
        members_response.items = []
        mock_blade.get_management_access_policies_members.return_value = (
            members_response
        )

        try:
            delete_policy(mock_module, mock_blade, {})
        except SystemExit:
            pass

        mock_blade.delete_management_access_policies.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    def test_delete_policy_failure_calls_fail_json(self):
        """Test delete_policy surfaces backend errors via fail_json"""
        mock_module = Mock()
        mock_module.params = _base_params(state="absent")
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.exit_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        members_response = Mock()
        members_response.status_code = 200
        members_response.items = []
        mock_blade.get_management_access_policies_members.return_value = (
            members_response
        )

        delete_response = Mock()
        delete_response.status_code = 400
        delete_response.errors = []
        mock_blade.delete_management_access_policies.return_value = delete_response

        try:
            delete_policy(mock_module, mock_blade, {})
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert "Failed to delete policy" in mock_module.fail_json.call_args[1]["msg"]

    # ---------------- main() flows ----------------

    @patch("plugins.modules.purefb_mgmt_policy.LooseVersion")
    @patch("plugins.modules.purefb_mgmt_policy.ManagementAccessPolicyPost")
    @patch("plugins.modules.purefb_mgmt_policy.get_system")
    @patch("plugins.modules.purefb_mgmt_policy.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_policy.HAS_PYPURECLIENT", True)
    def test_main_creates_policy(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_post_cls,
        mock_loose_version,
    ):
        """Test main creates a new policy when it doesn't exist"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = _base_params()
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.26"]
        mock_get_system.return_value = mock_blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_management_access_policies.return_value = get_response

        post_response = Mock()
        post_response.status_code = 200
        mock_blade.post_management_access_policies.return_value = post_response

        try:
            main()
        except SystemExit:
            pass

        mock_blade.post_management_access_policies.assert_called_once()
        call_kwargs = mock_blade.post_management_access_policies.call_args[1]
        assert call_kwargs["names"] == ["tenant-a-ops"]
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_mgmt_policy.LooseVersion")
    @patch("plugins.modules.purefb_mgmt_policy.get_system")
    @patch("plugins.modules.purefb_mgmt_policy.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_policy.HAS_PYPURECLIENT", True)
    def test_main_delete_idempotent_when_absent(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test main is a no-op when state=absent and the policy doesn't exist"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = _base_params(state="absent")
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.26"]
        mock_get_system.return_value = mock_blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_management_access_policies.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        mock_blade.delete_management_access_policies.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_mgmt_policy.LooseVersion")
    @patch("plugins.modules.purefb_mgmt_policy.get_system")
    @patch("plugins.modules.purefb_mgmt_policy.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_policy.HAS_PYPURECLIENT", True)
    def test_main_deletes_existing_policy(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test main DELETEs the policy when state=absent and no members attached"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = _base_params(state="absent")
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.26"]
        mock_get_system.return_value = mock_blade

        existing = Mock()
        existing.name = "tenant-a-ops"

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        mock_blade.get_management_access_policies.return_value = get_response

        members_response = Mock()
        members_response.status_code = 200
        members_response.items = []
        mock_blade.get_management_access_policies_members.return_value = (
            members_response
        )

        delete_response = Mock()
        delete_response.status_code = 200
        mock_blade.delete_management_access_policies.return_value = delete_response

        try:
            main()
        except SystemExit:
            pass

        mock_blade.delete_management_access_policies.assert_called_once_with(
            names=["tenant-a-ops"]
        )
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_mgmt_policy.LooseVersion")
    @patch("plugins.modules.purefb_mgmt_policy.get_system")
    @patch("plugins.modules.purefb_mgmt_policy.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_policy.HAS_PYPURECLIENT", True)
    def test_main_fails_when_policy_api_too_old(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test main fails when the array is older than the policy header API version"""
        # policy gate: LooseVersion(MIN_POLICY_API_VERSION) > LooseVersion(api_version) → True
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)

        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = _base_params()
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.18"]
        mock_get_system.return_value = mock_blade

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "does not support management access policies" in msg
        assert "2.19+" in msg

    @patch("plugins.modules.purefb_mgmt_policy.LooseVersion")
    @patch("plugins.modules.purefb_mgmt_policy.ManagementAccessPolicyPost")
    @patch("plugins.modules.purefb_mgmt_policy.get_system")
    @patch("plugins.modules.purefb_mgmt_policy.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_policy.HAS_PYPURECLIENT", True)
    def test_main_creates_policy_with_rules_on_2_19(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_post_cls,
        mock_loose_version,
    ):
        """Test main sends rules inline with the POST on REST < 2.26 instead of failing"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = _base_params(
            rules=[
                {
                    "role": "viewer",
                    "scope": {"name": "fb1", "resource_type": "arrays"},
                }
            ]
        )
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.19"]
        mock_get_system.return_value = mock_blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_management_access_policies.return_value = get_response

        post_response = Mock()
        post_response.status_code = 200
        mock_blade.post_management_access_policies.return_value = post_response

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_not_called()
        mock_blade.post_management_access_policies.assert_called_once()
        assert len(mock_post_cls.call_args[1]["rules"]) == 1
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_mgmt_policy.LooseVersion")
    def test_update_policy_inline_rules_idempotent_below_2_26(self, mock_loose_version):
        """Test update_policy on REST < 2.26 compares the inline rule list and skips PATCH"""
        # MIN_RULE_API_VERSION > api_version -> inline path
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)

        mock_module = Mock()
        mock_module.params = _base_params(
            rules=[
                {
                    "role": "viewer",
                    "scope": {"name": "fb1", "resource_type": "arrays"},
                }
            ]
        )
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        rule = Mock()
        rule.role = Mock()
        rule.role.name = "Viewer"
        rule.scope = Mock()
        rule.scope.resource_type = "arrays"
        rule.scope.name = "FB1"
        existing = Mock()
        existing.enabled = True
        existing.aggregation_strategy = None
        existing.rules = [rule]

        mock_blade = Mock()

        try:
            update_policy(mock_module, mock_blade, {}, existing, "2.21")
        except SystemExit:
            pass

        mock_blade.get_management_access_policies_rules.assert_not_called()
        mock_blade.patch_management_access_policies.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_mgmt_policy.LooseVersion")
    @patch("plugins.modules.purefb_mgmt_policy.ManagementAccessPolicy")
    def test_update_policy_inline_rules_replaced_below_2_26(
        self, mock_patch_cls, mock_loose_version
    ):
        """Test update_policy on REST < 2.26 PATCHes the whole rule list when it differs"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)

        mock_module = Mock()
        mock_module.params = _base_params(
            rules=[
                {
                    "role": "viewer",
                    "scope": {"name": "fb1", "resource_type": "arrays"},
                }
            ]
        )
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        existing = Mock()
        existing.enabled = True
        existing.aggregation_strategy = None
        existing.rules = []

        mock_blade = Mock()
        patch_response = Mock()
        patch_response.status_code = 200
        mock_blade.patch_management_access_policies.return_value = patch_response

        try:
            update_policy(mock_module, mock_blade, {}, existing, "2.21")
        except SystemExit:
            pass

        mock_blade.get_management_access_policies_rules.assert_not_called()
        mock_blade.patch_management_access_policies.assert_called_once()
        assert len(mock_patch_cls.call_args[1]["rules"]) == 1
        assert mock_module.exit_json.call_args[1]["changed"] is True

    # ---------------- _inline_rules_differ tests (REST < 2.26) ----------------

    def test_inline_rules_same_as_created_is_not_a_change(self):
        """Re-declaring the rule the policy was created with, in any case, is a no-op"""
        mock_module = Mock()
        mock_module.params = _base_params(rules=[_rule_spec("viewer")])
        existing = Mock()
        existing.rules = [_inline_rule("Viewer", "ARRAYS", "FB1")]

        assert _inline_rules_differ(mock_module, existing) is False

    def test_inline_rules_different_role_is_a_change(self):
        """Same scope, different role: the list must be replaced"""
        mock_module = Mock()
        mock_module.params = _base_params(rules=[_rule_spec("storage")])
        existing = Mock()
        existing.rules = [_inline_rule("viewer", "arrays", "fb1")]

        assert _inline_rules_differ(mock_module, existing) is True

    def test_inline_rules_added_rule_is_a_change(self):
        """A second rule on top of the existing one is a change"""
        mock_module = Mock()
        mock_module.params = _base_params(
            rules=[_rule_spec("viewer"), _rule_spec("support")]
        )
        existing = Mock()
        existing.rules = [_inline_rule("viewer", "arrays", "fb1")]

        assert _inline_rules_differ(mock_module, existing) is True

    def test_inline_rules_empty_desired(self):
        """rules: [] differs while rules exist and is a no-op once they are gone"""
        mock_module = Mock()
        mock_module.params = _base_params(rules=[])

        existing = Mock()
        existing.rules = [_inline_rule("viewer", "arrays", "fb1")]
        assert _inline_rules_differ(mock_module, existing) is True

        existing.rules = []
        assert _inline_rules_differ(mock_module, existing) is False

        existing.rules = None
        assert _inline_rules_differ(mock_module, existing) is False

    def test_inline_rules_tolerates_missing_references(self):
        """A rule whose role or scope reference is null does not raise"""
        mock_module = Mock()
        mock_module.params = _base_params(rules=[_rule_spec("viewer")])
        broken = Mock()
        broken.role = None
        broken.scope = None
        existing = Mock()
        existing.rules = [broken]

        assert _inline_rules_differ(mock_module, existing) is True

    @patch("plugins.modules.purefb_mgmt_policy.LooseVersion")
    @patch("plugins.modules.purefb_mgmt_policy.ManagementAccessPolicy")
    def test_update_policy_inline_rules_role_change_below_2_26(
        self, mock_patch_cls, mock_loose_version
    ):
        """On REST 2.21 changing the role of the only rule PATCHes the policy once"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)

        mock_module = Mock()
        mock_module.params = _base_params(rules=[_rule_spec("storage")])
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        existing = Mock()
        existing.enabled = True
        existing.aggregation_strategy = None
        existing.rules = [_inline_rule("viewer", "arrays", "fb1")]

        mock_blade = Mock()
        patch_response = Mock()
        patch_response.status_code = 200
        mock_blade.patch_management_access_policies.return_value = patch_response

        try:
            update_policy(mock_module, mock_blade, {}, existing, "2.21")
        except SystemExit:
            pass

        mock_module.fail_json.assert_not_called()
        mock_blade.patch_management_access_policies.assert_called_once()
        assert len(mock_patch_cls.call_args[1]["rules"]) == 1
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_mgmt_policy.LooseVersion")
    @patch("plugins.modules.purefb_mgmt_policy.get_system")
    @patch("plugins.modules.purefb_mgmt_policy.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_policy.HAS_PYPURECLIENT", True)
    def test_main_refuses_to_modify_builtin_management_policy(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test the built-in guard covers the management policy"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = _base_params(name="management", enabled=False)
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "Built-in policy management cannot be modified or deleted" in msg
        mock_get_system.assert_not_called()

    @patch("plugins.modules.purefb_mgmt_policy.LooseVersion")
    @patch("plugins.modules.purefb_mgmt_policy.get_system")
    @patch("plugins.modules.purefb_mgmt_policy.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_policy.HAS_PYPURECLIENT", True)
    def test_main_refuses_to_modify_builtin_policy(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test main fails immediately when a mutation is attempted on a built-in policy"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = _base_params(name="array_admin", enabled=False)
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "Built-in policy array_admin cannot be modified or deleted" in msg
        mock_get_system.assert_not_called()

    @patch("plugins.modules.purefb_mgmt_policy.LooseVersion")
    @patch("plugins.modules.purefb_mgmt_policy.get_system")
    @patch("plugins.modules.purefb_mgmt_policy.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_policy.HAS_PYPURECLIENT", True)
    def test_main_readonly_no_mutation_on_builtin_is_allowed(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test main lets a bare state=present with no mutation through even on a built-in policy"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        # No enabled / aggregation / rules → no mutation, state=present → the
        # built-in check should not fire.
        mock_module.params = _base_params(name="array_admin")
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.26"]
        mock_get_system.return_value = mock_blade

        existing = Mock()
        existing.name = "array_admin"
        existing.enabled = True
        existing.aggregation_strategy = "all-permissions"

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        mock_blade.get_management_access_policies.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        # No patch, no post, no delete — pure no-op
        mock_blade.patch_management_access_policies.assert_not_called()
        mock_blade.post_management_access_policies.assert_not_called()
        mock_blade.delete_management_access_policies.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_mgmt_policy.LooseVersion")
    @patch("plugins.modules.purefb_mgmt_policy.get_system")
    @patch("plugins.modules.purefb_mgmt_policy.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_policy.HAS_PYPURECLIENT", True)
    def test_main_refuses_to_modify_builtin_policy_case_variant(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test the built-in guard matches case variants of a built-in name"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = _base_params(name="Readonly", enabled=False)
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "Built-in policy Readonly cannot be modified or deleted" in msg
        mock_get_system.assert_not_called()

    @patch("plugins.modules.purefb_mgmt_policy.LooseVersion")
    @patch("plugins.modules.purefb_mgmt_policy.get_system")
    @patch("plugins.modules.purefb_mgmt_policy.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_policy.HAS_PYPURECLIENT", True)
    def test_main_rejects_duplicate_rules_before_connecting(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test main fails on duplicate rules before any connection is made"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = _base_params(
            rules=[
                {
                    "role": "viewer",
                    "scope": {"name": "fb1", "resource_type": "arrays"},
                },
                {
                    "role": "viewer",
                    "scope": {"name": "fb1", "resource_type": "arrays"},
                },
            ]
        )
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert "Duplicate rule" in mock_module.fail_json.call_args[1]["msg"]
        mock_get_system.assert_not_called()

    @patch("plugins.modules.purefb_mgmt_policy.LooseVersion")
    @patch("plugins.modules.purefb_mgmt_policy.get_system")
    @patch("plugins.modules.purefb_mgmt_policy.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_policy.HAS_PYPURECLIENT", True)
    def test_main_refuses_to_delete_builtin_policy(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test main refuses to delete a built-in policy"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = _base_params(name="readonly", state="absent")
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert (
            "Built-in policy readonly cannot be modified or deleted"
            in mock_module.fail_json.call_args[1]["msg"]
        )

    @patch("plugins.modules.purefb_mgmt_policy.get_system")
    @patch("plugins.modules.purefb_mgmt_policy.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_policy.HAS_PYPURECLIENT", False)
    def test_main_fails_when_sdk_missing(self, mock_ansible_module, mock_get_system):
        """Test main fails clearly when py-pure-client is not installed"""
        mock_module = Mock()
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.params = _base_params()
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert (
            "py-pure-client sdk is required"
            in mock_module.fail_json.call_args[1]["msg"]
        )

    # ---------------- _reconcile_rules: in-place role change, add before remove ----------------

    def _reconcile_blade(self, current):
        mock_blade = Mock()
        get_response = _ok()
        get_response.items = current
        mock_blade.get_management_access_policies_rules.return_value = get_response
        mock_blade.patch_management_access_policies_rules.return_value = _ok()
        mock_blade.post_management_access_policies_rules.return_value = _ok()
        mock_blade.delete_management_access_policies_rules.return_value = _ok()
        return mock_blade

    @patch("plugins.modules.purefb_mgmt_policy.ManagementAccessPolicyRule")
    @patch("plugins.modules.purefb_mgmt_policy.ReferenceWritable")
    def test_reconcile_role_change_patches_rule_in_place(self, mock_ref, mock_rule_cls):
        """A role change at an existing scope PATCHes the rule by id, no DELETE+POST"""
        mock_module = Mock()
        mock_module.params = _base_params(rules=[_rule_spec("storage")])
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = self._reconcile_blade([_current_rule("viewer", rule_id="id-v")])

        changed = _reconcile_rules(mock_module, mock_blade, {})

        assert changed is True
        mock_blade.patch_management_access_policies_rules.assert_called_once()
        call_kwargs = mock_blade.patch_management_access_policies_rules.call_args[1]
        assert call_kwargs["ids"] == ["id-v"]
        assert "names" not in call_kwargs
        # Only the role travels in the PATCH body; the scope is left alone.
        rule_kwargs = mock_rule_cls.call_args[1]
        assert "role" in rule_kwargs
        assert "scope" not in rule_kwargs
        assert any(c.kwargs.get("name") == "storage" for c in mock_ref.call_args_list)
        mock_blade.post_management_access_policies_rules.assert_not_called()
        mock_blade.delete_management_access_policies_rules.assert_not_called()

    @patch("plugins.modules.purefb_mgmt_policy.ManagementAccessPolicyRule")
    @patch("plugins.modules.purefb_mgmt_policy.ReferenceWritable")
    def test_reconcile_role_change_uses_user_spelling(self, mock_ref, mock_rule_cls):
        """The PATCHed role carries the user's spelling, not the lowercased key"""
        mock_module = Mock()
        mock_module.params = _base_params(rules=[_rule_spec("Storage", name="FB1")])
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = self._reconcile_blade([_current_rule("viewer", name="fb1")])

        assert _reconcile_rules(mock_module, mock_blade, {}) is True
        assert any(c.kwargs.get("name") == "Storage" for c in mock_ref.call_args_list)

    def test_reconcile_role_change_forwards_context(self):
        """The in-place PATCH carries the fleet context like the other rule calls"""
        mock_module = Mock()
        mock_module.params = _base_params(rules=[_rule_spec("storage")])
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = self._reconcile_blade([_current_rule("viewer")])

        _reconcile_rules(mock_module, mock_blade, {"context_names": ["fleet1"]})
        call_kwargs = mock_blade.patch_management_access_policies_rules.call_args[1]
        assert call_kwargs["context_names"] == ["fleet1"]

    def test_reconcile_role_change_failure_calls_fail_json(self):
        """A failed in-place PATCH reports old and new role and the scope"""
        mock_module = Mock()
        mock_module.params = _base_params(rules=[_rule_spec("storage")])
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = self._reconcile_blade([_current_rule("Viewer", name="FB1")])
        patch_response = Mock()
        patch_response.status_code = 400
        patch_response.errors = []
        mock_blade.patch_management_access_policies_rules.return_value = patch_response

        try:
            _reconcile_rules(mock_module, mock_blade, {})
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "Failed to change rule" in msg
        assert "role=Viewer to storage" in msg
        assert "arrays/FB1" in msg
        mock_blade.post_management_access_policies_rules.assert_not_called()
        mock_blade.delete_management_access_policies_rules.assert_not_called()

    def test_reconcile_role_change_check_mode_skips_patch(self):
        """Check mode reports the role change without PATCHing"""
        mock_module = Mock()
        mock_module.params = _base_params(rules=[_rule_spec("storage")])
        mock_module.check_mode = True

        mock_blade = self._reconcile_blade([_current_rule("viewer")])

        assert _reconcile_rules(mock_module, mock_blade, {}) is True
        mock_blade.patch_management_access_policies_rules.assert_not_called()
        mock_blade.post_management_access_policies_rules.assert_not_called()
        mock_blade.delete_management_access_policies_rules.assert_not_called()

    def test_reconcile_pairs_one_rule_per_scope(self):
        """Two stale rules and one new rule at a scope: one PATCH, one DELETE, no POST"""
        mock_module = Mock()
        mock_module.params = _base_params(rules=[_rule_spec("storage")])
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = self._reconcile_blade(
            [
                _current_rule("viewer", rule_id="id-v"),
                _current_rule("support", rule_id="id-s"),
            ]
        )

        assert _reconcile_rules(mock_module, mock_blade, {}) is True
        # Keys are sorted, so "support" is paired with "storage" and
        # "viewer" is removed.
        mock_blade.patch_management_access_policies_rules.assert_called_once()
        assert mock_blade.patch_management_access_policies_rules.call_args[1][
            "ids"
        ] == ["id-s"]
        mock_blade.delete_management_access_policies_rules.assert_called_once()
        assert mock_blade.delete_management_access_policies_rules.call_args[1][
            "ids"
        ] == ["id-v"]
        mock_blade.post_management_access_policies_rules.assert_not_called()

    def test_reconcile_same_role_other_scope_is_not_paired(self):
        """Moving a role to another scope is an add plus a remove, not a PATCH"""
        mock_module = Mock()
        mock_module.params = _base_params(
            rules=[_rule_spec("viewer", name="realm-a", resource_type="realms")]
        )
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = self._reconcile_blade([_current_rule("viewer", rule_id="id-v")])

        assert _reconcile_rules(mock_module, mock_blade, {}) is True
        mock_blade.patch_management_access_policies_rules.assert_not_called()
        mock_blade.post_management_access_policies_rules.assert_called_once()
        mock_blade.delete_management_access_policies_rules.assert_called_once()

    def test_reconcile_adds_before_removing(self):
        """New rules are POSTed before stale rules are DELETEd"""
        mock_module = Mock()
        mock_module.params = _base_params(rules=[_rule_spec("viewer")])
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = self._reconcile_blade(
            [_current_rule("support", name="realm-a", resource_type="realms")]
        )
        order = []

        def _post(**kwargs):
            order.append("post")
            return _ok()

        def _delete(**kwargs):
            order.append("delete")
            return _ok()

        mock_blade.post_management_access_policies_rules.side_effect = _post
        mock_blade.delete_management_access_policies_rules.side_effect = _delete

        assert _reconcile_rules(mock_module, mock_blade, {}) is True
        assert order == ["post", "delete"]
        mock_blade.patch_management_access_policies_rules.assert_not_called()

    def test_reconcile_add_failure_keeps_stale_rules(self):
        """A failed POST stops the run before any stale rule is DELETEd"""
        mock_module = Mock()
        mock_module.params = _base_params(rules=[_rule_spec("viewer")])
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = self._reconcile_blade(
            [_current_rule("support", name="realm-a", resource_type="realms")]
        )
        post_response = Mock()
        post_response.status_code = 400
        post_response.errors = []
        mock_blade.post_management_access_policies_rules.return_value = post_response

        try:
            _reconcile_rules(mock_module, mock_blade, {})
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert "Failed to add rule" in mock_module.fail_json.call_args[1]["msg"]
        mock_blade.delete_management_access_policies_rules.assert_not_called()

    def test_reconcile_empty_policy_and_empty_desired_is_noop(self):
        """rules: [] on a policy that already has no rules makes no writes"""
        mock_module = Mock()
        mock_module.params = _base_params(rules=[])
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = self._reconcile_blade([])

        assert _reconcile_rules(mock_module, mock_blade, {}) is False
        mock_blade.patch_management_access_policies_rules.assert_not_called()
        mock_blade.post_management_access_policies_rules.assert_not_called()
        mock_blade.delete_management_access_policies_rules.assert_not_called()

    def test_reconcile_empties_two_rules_by_id(self):
        """rules: [] DELETEs every rule by id, including the last one"""
        mock_module = Mock()
        mock_module.params = _base_params(rules=[])
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = self._reconcile_blade(
            [
                _current_rule("viewer", rule_id="id-v"),
                _current_rule("support", rule_id="id-s"),
            ]
        )

        assert _reconcile_rules(mock_module, mock_blade, {}) is True
        deleted = [
            c.kwargs["ids"]
            for c in mock_blade.delete_management_access_policies_rules.call_args_list
        ]
        assert sorted(deleted) == [["id-s"], ["id-v"]]
        mock_blade.patch_management_access_policies_rules.assert_not_called()
        mock_blade.post_management_access_policies_rules.assert_not_called()

    # ---------------- rules: [] below REST 2.26 (main() flows) ----------------

    def _run_main_on_2_21(
        self, mock_ansible_module, mock_get_system, params, existing, check_mode=False
    ):
        """Drive main() against a REST 2.21 array; returns (module, blade)."""
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = params
        mock_module.check_mode = check_mode
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        get_response = _ok()
        get_response.items = [] if existing is None else [existing]
        mock_blade.get_management_access_policies.return_value = get_response
        mock_blade.patch_management_access_policies.return_value = _ok()
        mock_blade.post_management_access_policies.return_value = _ok()
        mock_get_system.return_value = mock_blade

        try:
            main()
        except SystemExit:
            pass
        return mock_module, mock_blade

    @staticmethod
    def _inline_policy(rules, enabled=True):
        existing = Mock()
        existing.enabled = enabled
        existing.aggregation_strategy = None
        existing.rules = rules
        return existing

    @patch("plugins.modules.purefb_mgmt_policy.LooseVersion", side_effect=_Version)
    @patch(
        "plugins.modules.purefb_mgmt_policy.get_rest_api_version", return_value="2.21"
    )
    @patch("plugins.modules.purefb_mgmt_policy.get_system")
    @patch("plugins.modules.purefb_mgmt_policy.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_policy.HAS_PYPURECLIENT", True)
    def test_main_empty_rules_refused_below_2_26(
        self, mock_ansible_module, mock_get_system, mock_get_version, mock_loose_version
    ):
        """On REST < 2.26 emptying the rule list fails clearly before any write"""
        mock_module, mock_blade = self._run_main_on_2_21(
            mock_ansible_module,
            mock_get_system,
            _base_params(rules=[]),
            self._inline_policy([_inline_rule("viewer", "arrays", "fb1")]),
        )

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "cannot be left without rules" in msg
        assert "2.26" in msg
        mock_module.exit_json.assert_not_called()
        mock_blade.patch_management_access_policies.assert_not_called()
        mock_blade.get_management_access_policies_rules.assert_not_called()

    @patch("plugins.modules.purefb_mgmt_policy.LooseVersion", side_effect=_Version)
    @patch(
        "plugins.modules.purefb_mgmt_policy.get_rest_api_version", return_value="2.21"
    )
    @patch("plugins.modules.purefb_mgmt_policy.get_system")
    @patch("plugins.modules.purefb_mgmt_policy.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_policy.HAS_PYPURECLIENT", True)
    def test_main_empty_rules_refused_in_check_mode_below_2_26(
        self, mock_ansible_module, mock_get_system, mock_get_version, mock_loose_version
    ):
        """Check mode must not report a change the array would refuse"""
        mock_module, mock_blade = self._run_main_on_2_21(
            mock_ansible_module,
            mock_get_system,
            _base_params(rules=[]),
            self._inline_policy([_inline_rule("viewer", "arrays", "fb1")]),
            check_mode=True,
        )

        mock_module.fail_json.assert_called_once()
        mock_module.exit_json.assert_not_called()
        mock_blade.patch_management_access_policies.assert_not_called()

    @patch("plugins.modules.purefb_mgmt_policy.LooseVersion", side_effect=_Version)
    @patch(
        "plugins.modules.purefb_mgmt_policy.get_rest_api_version", return_value="2.21"
    )
    @patch("plugins.modules.purefb_mgmt_policy.get_system")
    @patch("plugins.modules.purefb_mgmt_policy.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_policy.HAS_PYPURECLIENT", True)
    def test_main_empty_rules_refused_before_enabled_patch_below_2_26(
        self, mock_ansible_module, mock_get_system, mock_get_version, mock_loose_version
    ):
        """enabled: false plus rules: [] fails before the enabled PATCH is sent"""
        mock_module, mock_blade = self._run_main_on_2_21(
            mock_ansible_module,
            mock_get_system,
            _base_params(enabled=False, rules=[]),
            self._inline_policy([_inline_rule("viewer", "arrays", "fb1")]),
        )

        mock_module.fail_json.assert_called_once()
        assert (
            "cannot be left without rules" in mock_module.fail_json.call_args[1]["msg"]
        )
        mock_module.exit_json.assert_not_called()
        mock_blade.patch_management_access_policies.assert_not_called()

    @patch("plugins.modules.purefb_mgmt_policy.LooseVersion", side_effect=_Version)
    @patch(
        "plugins.modules.purefb_mgmt_policy.get_rest_api_version", return_value="2.21"
    )
    @patch("plugins.modules.purefb_mgmt_policy.get_system")
    @patch("plugins.modules.purefb_mgmt_policy.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_policy.HAS_PYPURECLIENT", True)
    def test_main_empty_rules_refused_on_create_below_2_26(
        self, mock_ansible_module, mock_get_system, mock_get_version, mock_loose_version
    ):
        """rules: [] on a policy that does not exist yet is refused, not POSTed (check mode)"""
        mock_module, mock_blade = self._run_main_on_2_21(
            mock_ansible_module,
            mock_get_system,
            _base_params(rules=[]),
            None,
            check_mode=True,
        )

        mock_module.fail_json.assert_called_once()
        assert (
            "cannot be left without rules" in mock_module.fail_json.call_args[1]["msg"]
        )
        mock_module.exit_json.assert_not_called()
        mock_blade.post_management_access_policies.assert_not_called()

    @patch("plugins.modules.purefb_mgmt_policy.LooseVersion", side_effect=_Version)
    @patch(
        "plugins.modules.purefb_mgmt_policy.get_rest_api_version", return_value="2.21"
    )
    @patch("plugins.modules.purefb_mgmt_policy.get_system")
    @patch("plugins.modules.purefb_mgmt_policy.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_policy.HAS_PYPURECLIENT", True)
    def test_main_empty_rules_noop_when_already_empty_below_2_26(
        self, mock_ansible_module, mock_get_system, mock_get_version, mock_loose_version
    ):
        """rules: [] on a rule-less policy below 2.26 is not a change and not an error"""
        mock_module, mock_blade = self._run_main_on_2_21(
            mock_ansible_module,
            mock_get_system,
            _base_params(rules=[]),
            self._inline_policy([]),
        )

        mock_module.fail_json.assert_not_called()
        mock_blade.patch_management_access_policies.assert_not_called()
        mock_blade.get_management_access_policies_rules.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is False


# ---------------- failed reads and realm scopes ----------------

MOD = "plugins.modules.purefb_mgmt_policy"
POLICY_NOT_FOUND = "Management access policy does not exist."
REALM_NOT_FOUND = "Realm does not exist."
NO_REALM_MATCHES = "Realm was not found."
INVALID_NAME = "Missing or invalid parameter."
NOT_PERMITTED = "Operation not permitted."


def _refused(message, status_code=400):
    """An error answer of the array: a status and the errors, no items."""
    response = Mock(spec=["status_code", "errors"])
    response.status_code = status_code
    response.errors = [Mock(message=message)]
    return response


def _items(*items):
    response = _ok()
    response.items = list(items)
    return response


def _array_message(response, default="Unknown error"):
    """What module_utils.common.get_error_message returns for a response."""
    errors = getattr(response, "errors", None)
    return errors[0].message if errors else default


def _realm_rule(role, realm):
    return _rule_spec(role, name=realm, resource_type="realms")


def _realm_reads(*existing):
    """get_realms as the array answers it.

    A name matches without regard to case, blanks around it are ignored and
    the realm comes back in the stored spelling. A comma separates the names
    of a list and * is a wildcard, so the answer holds every realm that
    matches, the realm named last first here. A name the array does not
    know (a realm::name included) is a 400, and so are a pattern that
    matches nothing and an empty name, each with its own message.
    """
    known = dict((name.lower(), name) for name in existing)

    def get_realms(names=None, **kwargs):
        wanted = [part.strip().lower() for name in names for part in name.split(",")]
        wanted = [part for part in wanted if part]
        if not wanted:
            return _refused(INVALID_NAME)
        found = []
        for part in wanted:
            if "*" in part:
                matches = [key for key in known if fnmatch.fnmatchcase(key, part)]
                if not matches:
                    return _refused(NO_REALM_MATCHES)
            elif part in known:
                matches = [part]
            else:
                return _refused(REALM_NOT_FOUND)
            found.extend(key for key in matches if key not in found)
        realms = []
        for key in reversed(found):
            realm = Mock()
            realm.name = known[key]
            realms.append(realm)
        return _items(*realms)

    return Mock(side_effect=get_realms)


def _stored_policy(enabled=True, rules=None):
    policy = Mock()
    policy.name = "tenant-a-ops"
    policy.enabled = enabled
    policy.aggregation_strategy = "all-permissions"
    policy.rules = rules
    return policy


def _module(check_mode=False, **params):
    module = Mock()
    module.params = _base_params(**params)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _blade(policy=None, rules=(), members=(), realms=("rzaudit",)):
    """A blade that answers reads as the array does and accepts every write.

    ``policy`` is the stored policy, or None when the array has none.
    """
    blade = Mock()
    if policy is None:
        blade.get_management_access_policies.return_value = _refused(POLICY_NOT_FOUND)
    else:
        blade.get_management_access_policies.return_value = _items(policy)
    blade.get_management_access_policies_rules.return_value = _items(*rules)
    blade.get_management_access_policies_members.return_value = _items(*members)
    blade.get_realms = _realm_reads(*realms)
    for write in (
        "post_management_access_policies",
        "patch_management_access_policies",
        "delete_management_access_policies",
        "post_management_access_policies_rules",
        "patch_management_access_policies_rules",
        "delete_management_access_policies_rules",
    ):
        getattr(blade, write).return_value = _ok()
    return blade


def _writes(blade):
    """Names of the write calls a blade received."""
    return sorted(
        set(
            call[0]
            for call in blade.method_calls
            if call[0].split("_")[0] in ("post", "patch", "delete")
        )
    )


def _run(function, *args):
    """Call a module function that ends in exit_json or fail_json."""
    with patch(MOD + ".get_error_message", side_effect=_array_message), patch(
        MOD + ".LooseVersion", side_effect=_Version
    ):
        try:
            return function(*args)
        except SystemExit:
            return None


def _main(module, blade, api_version="2.30"):
    """Drive main() for a module and a blade on a REST version."""
    with patch(MOD + ".AnsibleModule", return_value=module), patch(
        MOD + ".get_system", return_value=blade
    ), patch(MOD + ".get_rest_api_version", return_value=api_version), patch(
        MOD + ".HAS_PYPURECLIENT", True
    ):
        _run(main)


class TestFailedReads:
    """A read the array refuses is reported with its message and is never
    taken for a policy that does not exist."""

    def test_get_policy_fails_when_the_read_is_refused(self):
        module = _module()
        blade = _blade()
        blade.get_management_access_policies.return_value = _refused(NOT_PERMITTED)

        _run(_get_policy, module, blade, {})

        module.fail_json.assert_called_once_with(
            msg="Failed to read policy tenant-a-ops. Error: Operation not permitted."
        )

    def test_get_policy_fails_on_an_error_without_a_message(self):
        module = _module()
        blade = _blade()
        response = _refused("unused", status_code=500)
        response.errors = []
        blade.get_management_access_policies.return_value = response

        _run(_get_policy, module, blade, {})

        module.fail_json.assert_called_once_with(
            msg="Failed to read policy tenant-a-ops. Error: Unknown error"
        )

    def test_get_policy_none_for_a_policy_that_does_not_exist(self):
        module = _module()

        assert _run(_get_policy, module, _blade(), {}) is None
        module.fail_json.assert_not_called()

    def test_main_present_fails_instead_of_creating(self):
        """An existing policy that cannot be read is not created again"""
        module = _module()
        blade = _blade()
        blade.get_management_access_policies.return_value = _refused(NOT_PERMITTED)

        _main(module, blade)

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert (
            msg == "Failed to read policy tenant-a-ops. Error: Operation not permitted."
        )
        module.exit_json.assert_not_called()
        assert _writes(blade) == []

    def test_main_present_check_mode_fails_instead_of_predicting_a_create(self):
        module = _module(check_mode=True, rules=[_realm_rule("admin", "rzaudit")])
        blade = _blade()
        blade.get_management_access_policies.return_value = _refused(NOT_PERMITTED)

        _main(module, blade)

        module.fail_json.assert_called_once()
        assert "Failed to read policy" in module.fail_json.call_args[1]["msg"]
        module.exit_json.assert_not_called()
        blade.get_realms.assert_not_called()

    def test_main_absent_fails_instead_of_reporting_ok(self):
        for check_mode in (True, False):
            module = _module(check_mode=check_mode, state="absent")
            blade = _blade()
            blade.get_management_access_policies.return_value = _refused(NOT_PERMITTED)

            _main(module, blade)

            module.fail_json.assert_called_once()
            assert "Failed to read policy" in module.fail_json.call_args[1]["msg"]
            module.exit_json.assert_not_called()
            assert _writes(blade) == []

    def test_main_absent_fails_when_the_members_cannot_be_read(self):
        """The delete guard does not take a refused read for "no members" """
        for check_mode in (True, False):
            module = _module(check_mode=check_mode, state="absent")
            blade = _blade(policy=_stored_policy())
            blade.get_management_access_policies_members.return_value = _refused(
                NOT_PERMITTED
            )

            _main(module, blade)

            module.fail_json.assert_called_once_with(
                msg=(
                    "Failed to list members of policy tenant-a-ops. "
                    "Error: Operation not permitted."
                )
            )
            module.exit_json.assert_not_called()
            assert _writes(blade) == []

    def test_main_absent_is_unchanged_for_a_policy_that_does_not_exist(self):
        module = _module(state="absent")
        blade = _blade()

        _main(module, blade)

        module.fail_json.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)
        assert _writes(blade) == []

    def test_main_present_creates_a_policy_that_does_not_exist(self):
        module = _module()
        blade = _blade()

        _main(module, blade)

        module.fail_json.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)
        assert _writes(blade) == ["post_management_access_policies"]

    def test_main_absent_deletes_a_policy_without_members(self):
        module = _module(state="absent")
        blade = _blade(policy=_stored_policy())

        _main(module, blade)

        module.exit_json.assert_called_once_with(changed=True)
        assert _writes(blade) == ["delete_management_access_policies"]


class TestRealmScopes:
    """A rule to add that names a realm the array does not know fails the
    task before any write, in check mode too."""

    def test_unknown_realm_fails(self):
        module = _module(rules=[_realm_rule("storage", "norealm")])
        blade = _blade()

        _run(_resolve_realm_scopes, module, blade, {}, [])

        blade.get_realms.assert_called_once_with(names=["norealm"])
        module.fail_json.assert_called_once_with(
            msg=(
                "Cannot add rule (role=storage, scope=realms/norealm) to policy "
                "tenant-a-ops: realm norealm does not exist. The scope name of a "
                "rule is the bare name of an existing realm."
            )
        )

    def test_realm_qualified_scope_name_fails(self):
        module = _module(rules=[_realm_rule("viewer", "rzaudit::tenant")])
        blade = _blade()

        _run(_resolve_realm_scopes, module, blade, {}, [])

        blade.get_realms.assert_called_once_with(names=["rzaudit::tenant"])
        module.fail_json.assert_called_once()
        assert (
            "realm rzaudit::tenant does not exist"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_existing_realm_passes_in_any_case(self):
        module = _module(
            rules=[_realm_rule("admin", "rzaudit"), _realm_rule("viewer", "RZAudit")]
        )
        blade = _blade()

        _run(_resolve_realm_scopes, module, blade, {}, [])

        module.fail_json.assert_not_called()
        # One read per realm, with the spelling of the first rule that names it.
        blade.get_realms.assert_called_once_with(names=["rzaudit"])
        assert [rule["scope"]["name"] for rule in module.params["rules"]] == [
            "rzaudit",
            "rzaudit",
        ]

    def test_new_realm_scope_takes_the_stored_spelling(self):
        """The array accepts a rule only with the spelling it holds"""
        module = _module(rules=[_realm_rule("Admin", "RZAUDIT")])
        blade = _blade()

        _run(_resolve_realm_scopes, module, blade, {}, [])

        blade.get_realms.assert_called_once_with(names=["RZAUDIT"])
        assert module.params["rules"] == [_realm_rule("Admin", "rzaudit")]

    def test_first_unknown_realm_is_named(self):
        module = _module(
            rules=[
                _realm_rule("admin", "rzaudit"),
                _realm_rule("viewer", "gone"),
                _realm_rule("viewer", "gone-too"),
            ]
        )
        blade = _blade()

        _run(_resolve_realm_scopes, module, blade, {}, [])

        assert "realms/gone)" in module.fail_json.call_args[1]["msg"]
        assert blade.get_realms.call_count == 2

    def test_scope_of_a_current_rule_is_not_read_again(self):
        """A second role at a realm the policy already has a rule on"""
        module = _module(
            rules=[_realm_rule("admin", "rzaudit"), _realm_rule("storage", "RZAUDIT")]
        )
        blade = _blade(realms=())
        current = [_current_rule("admin", name="rzaudit", resource_type="realms")]

        _run(_resolve_realm_scopes, module, blade, {}, current)

        blade.get_realms.assert_not_called()
        module.fail_json.assert_not_called()
        # The added rule carries the spelling of the rule the policy has.
        assert module.params["rules"][1] == _realm_rule("storage", "rzaudit")

    def test_array_scopes_are_neither_read_nor_respelled(self):
        module = _module(rules=[_rule_spec("viewer", "FB1"), _rule_spec("storage")])
        blade = _blade(realms=())

        _run(_resolve_realm_scopes, module, blade, {}, [_current_rule("admin")])

        blade.get_realms.assert_not_called()
        module.fail_json.assert_not_called()
        assert module.params["rules"] == [
            _rule_spec("viewer", "FB1"),
            _rule_spec("storage"),
        ]

    def test_realm_of_the_same_name_as_a_current_array_scope_is_read(self):
        module = _module(rules=[_realm_rule("viewer", "fb1")])
        blade = _blade()

        _run(_resolve_realm_scopes, module, blade, {}, [_current_rule("viewer")])

        blade.get_realms.assert_called_once_with(names=["fb1"])
        module.fail_json.assert_called_once()

    def test_refused_realm_read_leaves_the_decision_to_the_array(self):
        module = _module(rules=[_realm_rule("viewer", "RZAudit")])
        blade = _blade()
        blade.get_realms = Mock(return_value=_refused(NOT_PERMITTED))

        _run(_resolve_realm_scopes, module, blade, {}, [])

        blade.get_realms.assert_called_once()
        module.fail_json.assert_not_called()
        assert module.params["rules"] == [_realm_rule("viewer", "RZAudit")]

    def test_no_rules_no_reads(self):
        for rules in (None, []):
            module = _module(rules=rules)
            blade = _blade()

            _run(_resolve_realm_scopes, module, blade, {}, [])

            blade.get_realms.assert_not_called()
            module.fail_json.assert_not_called()

    def test_context_is_forwarded(self):
        module = _module(rules=[_realm_rule("viewer", "rzaudit")])
        blade = _blade()

        _run(_resolve_realm_scopes, module, blade, {"context_names": ["fb2"]}, [])

        blade.get_realms.assert_called_once_with(
            names=["rzaudit"], context_names=["fb2"]
        )

    def test_current_rule_without_references_is_tolerated(self):
        """A rule whose role was deleted comes back with role: null"""
        module = _module(rules=[_realm_rule("viewer", "rzaudit")])
        blade = _blade()
        broken = Mock(spec=["id", "name", "role", "scope"])
        broken.role = None
        broken.scope = None

        _run(_resolve_realm_scopes, module, blade, {}, [broken])

        blade.get_realms.assert_called_once_with(names=["rzaudit"])
        module.fail_json.assert_not_called()

    # ---- create ----

    def test_create_fails_for_an_unknown_realm_before_the_post(self):
        for check_mode in (True, False):
            module = _module(
                check_mode=check_mode,
                rules=[_realm_rule("admin", "rzaudit"), _realm_rule("viewer", "gone")],
            )
            blade = _blade()

            _main(module, blade)

            module.fail_json.assert_called_once()
            assert "realm gone does not exist" in module.fail_json.call_args[1]["msg"]
            module.exit_json.assert_not_called()
            assert _writes(blade) == []

    def test_create_with_an_existing_realm_is_a_change(self):
        for check_mode in (True, False):
            module = _module(
                check_mode=check_mode, rules=[_realm_rule("admin", "RZAUDIT")]
            )
            blade = _blade()

            _main(module, blade)

            module.fail_json.assert_not_called()
            module.exit_json.assert_called_once_with(changed=True)
            blade.get_realms.assert_called_once_with(names=["RZAUDIT"])
            expected = [] if check_mode else ["post_management_access_policies"]
            assert _writes(blade) == expected

    def test_create_on_rest_2_21_fails_for_an_unknown_realm(self):
        module = _module(check_mode=True, rules=[_realm_rule("viewer", "gone")])
        blade = _blade()

        _main(module, blade, api_version="2.21")

        module.fail_json.assert_called_once()
        module.exit_json.assert_not_called()

    def test_create_with_array_rules_reads_no_realm(self):
        module = _module(rules=[_rule_spec("viewer")])
        blade = _blade(realms=())

        _main(module, blade)

        blade.get_realms.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)
        assert _writes(blade) == ["post_management_access_policies"]

    # ---- update, REST 2.26 and later ----

    def test_update_fails_for_an_unknown_realm_before_any_write(self):
        """Neither the enabled PATCH nor the role change is sent first"""
        for check_mode in (True, False):
            module = _module(
                check_mode=check_mode,
                enabled=False,
                rules=[_realm_rule("admin", "rzaudit"), _realm_rule("viewer", "gone")],
            )
            current = [_current_rule("viewer", name="rzaudit", resource_type="realms")]
            blade = _blade(policy=_stored_policy(), rules=current)

            _main(module, blade)

            module.fail_json.assert_called_once()
            assert "realm gone does not exist" in module.fail_json.call_args[1]["msg"]
            module.exit_json.assert_not_called()
            assert _writes(blade) == []

    def test_update_fails_for_a_realm_qualified_scope_name(self):
        module = _module(
            check_mode=True,
            rules=[
                _realm_rule("admin", "rzaudit"),
                _realm_rule("viewer", "rzaudit::x"),
            ],
        )
        current = [_current_rule("admin", name="rzaudit", resource_type="realms")]
        blade = _blade(policy=_stored_policy(), rules=current)

        _main(module, blade)

        blade.get_realms.assert_called_once_with(names=["rzaudit::x"])
        module.fail_json.assert_called_once()
        module.exit_json.assert_not_called()

    def test_update_adds_a_rule_on_an_existing_realm(self):
        for check_mode in (True, False):
            module = _module(
                check_mode=check_mode,
                rules=[
                    _realm_rule("admin", "rzaudit"),
                    _realm_rule("storage", "Other"),
                ],
            )
            current = [_current_rule("admin", name="rzaudit", resource_type="realms")]
            blade = _blade(
                policy=_stored_policy(), rules=current, realms=("rzaudit", "other")
            )

            _main(module, blade)

            module.fail_json.assert_not_called()
            module.exit_json.assert_called_once_with(changed=True)
            blade.get_realms.assert_called_once_with(names=["Other"])
            # The rules are read once and handed on to the reconciliation.
            assert blade.get_management_access_policies_rules.call_count == 1
            expected = [] if check_mode else ["post_management_access_policies_rules"]
            assert _writes(blade) == expected

    def test_update_role_change_at_a_realm_scope_reads_no_realm(self):
        """After a realm rename the stored rule carries the new name"""
        module = _module(rules=[_realm_rule("admin", "renamed")])
        current = [_current_rule("viewer", name="renamed", resource_type="realms")]
        blade = _blade(policy=_stored_policy(), rules=current, realms=())

        _main(module, blade)

        blade.get_realms.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)
        assert _writes(blade) == ["patch_management_access_policies_rules"]

    def test_update_same_realm_rules_is_unchanged(self):
        for check_mode in (True, False):
            module = _module(
                check_mode=check_mode, rules=[_realm_rule("ADMIN", "RZAUDIT")]
            )
            current = [_current_rule("admin", name="rzaudit", resource_type="realms")]
            blade = _blade(policy=_stored_policy(), rules=current, realms=())

            _main(module, blade)

            blade.get_realms.assert_not_called()
            module.exit_json.assert_called_once_with(changed=False)
            assert _writes(blade) == []

    def test_update_fails_when_the_rules_cannot_be_read_before_any_write(self):
        module = _module(enabled=False, rules=[_realm_rule("admin", "rzaudit")])
        blade = _blade(policy=_stored_policy())
        blade.get_management_access_policies_rules.return_value = _refused(
            NOT_PERMITTED
        )

        _main(module, blade)

        module.fail_json.assert_called_once_with(
            msg=(
                "Failed to list rules for policy tenant-a-ops. "
                "Error: Operation not permitted."
            )
        )
        assert _writes(blade) == []

    def test_update_without_rules_reads_neither_rules_nor_realms(self):
        module = _module(enabled=False)
        blade = _blade(policy=_stored_policy())

        _main(module, blade)

        blade.get_management_access_policies_rules.assert_not_called()
        blade.get_realms.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)
        assert _writes(blade) == ["patch_management_access_policies"]

    # ---- update, REST 2.19 to 2.25 (rules inline on the policy) ----

    def test_inline_update_fails_for_an_unknown_realm_before_the_patch(self):
        for check_mode in (True, False):
            module = _module(
                check_mode=check_mode,
                enabled=False,
                rules=[_realm_rule("viewer", "gone")],
            )
            stored = _stored_policy(rules=[_inline_rule("viewer", "realms", "rzaudit")])
            blade = _blade(policy=stored)

            _main(module, blade, api_version="2.21")

            module.fail_json.assert_called_once()
            assert "realm gone does not exist" in module.fail_json.call_args[1]["msg"]
            module.exit_json.assert_not_called()
            assert _writes(blade) == []
            blade.get_management_access_policies_rules.assert_not_called()

    def test_inline_update_role_change_at_a_realm_scope_reads_no_realm(self):
        module = _module(rules=[_realm_rule("admin", "Rzaudit")])
        stored = _stored_policy(rules=[_inline_rule("viewer", "realms", "rzaudit")])
        blade = _blade(policy=stored, realms=())

        _main(module, blade, api_version="2.21")

        blade.get_realms.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)
        assert _writes(blade) == ["patch_management_access_policies"]

    def test_inline_update_to_an_existing_realm_is_a_change(self):
        module = _module(check_mode=True, rules=[_realm_rule("viewer", "rzaudit")])
        stored = _stored_policy(rules=[_inline_rule("viewer", "arrays", "fb1")])
        blade = _blade(policy=stored)

        _main(module, blade, api_version="2.21")

        blade.get_realms.assert_called_once_with(names=["rzaudit"])
        module.exit_json.assert_called_once_with(changed=True)
        assert _writes(blade) == []

    # ---- _reconcile_rules with the rules its caller has read ----

    def test_reconcile_uses_the_rules_it_is_given(self):
        module = _module(rules=[_realm_rule("admin", "rzaudit")])
        blade = _blade()
        current = [_current_rule("admin", name="rzaudit", resource_type="realms")]

        assert _run(_reconcile_rules, module, blade, {}, current) is False
        blade.get_management_access_policies_rules.assert_not_called()

    def test_reconcile_given_an_empty_rule_list_does_not_read_again(self):
        module = _module(rules=[_realm_rule("admin", "rzaudit")])
        blade = _blade()

        assert _run(_reconcile_rules, module, blade, {}, []) is True
        blade.get_management_access_policies_rules.assert_not_called()
        assert _writes(blade) == ["post_management_access_policies_rules"]

    # ---- the spelling that is sent ----

    @staticmethod
    def _sent_scopes(mock_ref):
        """(resource_type, name) of every scope reference that was built."""
        return [
            (call.kwargs["resource_type"], call.kwargs["name"])
            for call in mock_ref.call_args_list
            if "resource_type" in call.kwargs
        ]

    def test_create_sends_the_stored_spelling_of_a_realm(self):
        module = _module(
            rules=[_realm_rule("Admin", "RZAUDIT"), _rule_spec("viewer", "FB1")]
        )
        blade = _blade()

        with patch(MOD + ".ReferenceWritable") as mock_ref:
            _main(module, blade)

        module.exit_json.assert_called_once_with(changed=True)
        assert self._sent_scopes(mock_ref) == [
            ("realms", "rzaudit"),
            ("arrays", "FB1"),
        ]
        # The role travels as the task wrote it.
        assert any(call.kwargs == {"name": "Admin"} for call in mock_ref.call_args_list)

    def test_update_sends_the_stored_spelling_of_a_new_realm(self):
        module = _module(
            rules=[_realm_rule("admin", "rzaudit"), _realm_rule("storage", "OTHER")]
        )
        current = [_current_rule("admin", name="rzaudit", resource_type="realms")]
        blade = _blade(
            policy=_stored_policy(), rules=current, realms=("rzaudit", "Other")
        )

        with patch(MOD + ".ReferenceWritable") as mock_ref:
            _main(module, blade)

        assert _writes(blade) == ["post_management_access_policies_rules"]
        assert self._sent_scopes(mock_ref) == [("realms", "Other")]

    def test_update_second_role_at_a_realm_sends_the_spelling_of_the_current_rule(
        self,
    ):
        module = _module(
            rules=[_realm_rule("admin", "rzaudit"), _realm_rule("storage", "RZAUDIT")]
        )
        current = [_current_rule("admin", name="rzaudit", resource_type="realms")]
        blade = _blade(policy=_stored_policy(), rules=current, realms=())

        with patch(MOD + ".ReferenceWritable") as mock_ref:
            _main(module, blade)

        blade.get_realms.assert_not_called()
        assert _writes(blade) == ["post_management_access_policies_rules"]
        assert self._sent_scopes(mock_ref) == [("realms", "rzaudit")]

    def test_inline_update_sends_the_stored_spelling(self):
        module = _module(
            rules=[_realm_rule("admin", "RZAUDIT"), _realm_rule("viewer", "OTHER")]
        )
        stored = _stored_policy(rules=[_inline_rule("viewer", "realms", "rzaudit")])
        blade = _blade(policy=stored, realms=("rzaudit", "other"))

        with patch(MOD + ".ReferenceWritable") as mock_ref:
            _main(module, blade, api_version="2.21")

        assert _writes(blade) == ["patch_management_access_policies"]
        assert self._sent_scopes(mock_ref) == [
            ("realms", "rzaudit"),
            ("realms", "other"),
        ]


class TestOneRealmPerScope:
    """The realm read answers a list of names or a wildcard with other
    realms. A rule is only ever put on the realm the task names."""

    def _refused_scope(self, scope_name, realms, current=()):
        module = _module(
            rules=[_realm_rule("admin", "rzaudit"), _realm_rule("storage", scope_name)]
        )
        blade = _blade(realms=realms)

        _run(_resolve_realm_scopes, module, blade, {}, list(current))

        module.fail_json.assert_called_once_with(
            msg=(
                "Cannot add rule (role=storage, scope=realms/{0}) to policy "
                "tenant-a-ops: realm {0} does not exist. The scope name of a "
                "rule is the bare name of an existing realm."
            ).format(scope_name)
        )
        # The scope is left as the task wrote it, never respelled.
        assert module.params["rules"][1] == _realm_rule("storage", scope_name)

    def test_wildcard_scope_is_not_taken_for_a_realm_it_matches(self):
        self._refused_scope("tenant-*", ("rzaudit", "tenant-a", "tenant-b"))

    def test_wildcard_scope_that_matches_one_realm_is_refused(self):
        self._refused_scope("tenant-*", ("rzaudit", "tenant-a"))

    def test_wildcard_scope_that_matches_every_realm_is_refused(self):
        self._refused_scope("*", ("rzaudit",))

    def test_wildcard_scope_that_matches_nothing_is_refused(self):
        self._refused_scope("tenant-*", ("rzaudit",))

    def test_list_of_realms_as_scope_is_refused(self):
        self._refused_scope("tenant-a,tenant-b", ("rzaudit", "tenant-a", "tenant-b"))

    def test_list_with_one_realm_as_scope_is_refused(self):
        self._refused_scope("tenant-a,", ("rzaudit", "tenant-a"))

    def test_wildcard_scope_is_refused_beside_a_current_rule_on_that_realm(self):
        current = [_current_rule("viewer", name="tenant-a", resource_type="realms")]
        self._refused_scope("tenant-*", ("rzaudit", "tenant-a"), current)

    def test_blanks_around_a_realm_name_are_ignored(self):
        module = _module(rules=[_realm_rule("viewer", " RZAudit ")])
        blade = _blade()

        _run(_resolve_realm_scopes, module, blade, {}, [])

        module.fail_json.assert_not_called()
        assert module.params["rules"] == [_realm_rule("viewer", "rzaudit")]

    def test_empty_scope_name_is_left_to_the_array(self):
        """The read answers "Missing or invalid parameter.", which is not a
        statement about a realm"""
        module = _module(rules=[_realm_rule("viewer", "")])
        blade = _blade()

        _run(_resolve_realm_scopes, module, blade, {}, [])

        module.fail_json.assert_not_called()
        assert module.params["rules"] == [_realm_rule("viewer", "")]

    def test_find_realm_returns_the_stored_spelling(self):
        blade = _blade(realms=("Tenant-A", "tenant-b"))

        assert _run(_find_realm, blade, {}, "TENANT-a") == "Tenant-A"
        blade.get_realms.assert_called_once_with(names=["TENANT-a"])

    def test_find_realm_none_for_an_answer_without_that_realm(self):
        blade = _blade(realms=("tenant-a", "tenant-b"))

        for name in ("tenant-*", "*", "tenant-a,tenant-b", "tenant-b,tenant-a"):
            assert _run(_find_realm, blade, {}, name) is None

    def test_find_realm_none_for_an_empty_answer(self):
        blade = _blade()
        blade.get_realms = Mock(return_value=_items())

        assert _run(_find_realm, blade, {}, "rzaudit") is None

    def test_find_realm_none_when_the_array_has_no_such_realm(self):
        blade = _blade()

        assert _run(_find_realm, blade, {}, "gone") is None
        assert _run(_find_realm, blade, {}, "rzaudit::x") is None
        assert _run(_find_realm, blade, {}, "gone-*") is None

    def test_find_realm_returns_the_name_when_the_read_says_nothing(self):
        blade = _blade()
        for message in (NOT_PERMITTED, INVALID_NAME, "Internal error."):
            blade.get_realms = Mock(return_value=_refused(message))

            assert _run(_find_realm, blade, {}, "RZAudit") == "RZAudit"

    def test_find_realm_forwards_the_context(self):
        blade = _blade()

        _run(_find_realm, blade, {"context_names": ["fb2"]}, "rzaudit")

        blade.get_realms.assert_called_once_with(
            names=["rzaudit"], context_names=["fb2"]
        )

    def test_create_with_a_wildcard_scope_fails_before_the_post(self):
        for check_mode in (True, False):
            module = _module(
                check_mode=check_mode, rules=[_realm_rule("storage", "tenant-*")]
            )
            blade = _blade(realms=("rzaudit", "tenant-a", "tenant-b"))

            _main(module, blade)

            module.fail_json.assert_called_once()
            assert (
                "realm tenant-* does not exist" in module.fail_json.call_args[1]["msg"]
            )
            module.exit_json.assert_not_called()
            assert _writes(blade) == []

    def test_update_with_a_list_scope_fails_before_any_write(self):
        """Neither the enabled PATCH nor a rule for one realm of the list"""
        for check_mode in (True, False):
            module = _module(
                check_mode=check_mode,
                enabled=False,
                rules=[
                    _realm_rule("admin", "rzaudit"),
                    _realm_rule("storage", "tenant-a,tenant-b"),
                ],
            )
            current = [_current_rule("admin", name="rzaudit", resource_type="realms")]
            blade = _blade(
                policy=_stored_policy(),
                rules=current,
                realms=("rzaudit", "tenant-a", "tenant-b"),
            )

            _main(module, blade)

            module.fail_json.assert_called_once()
            assert (
                "realm tenant-a,tenant-b does not exist"
                in module.fail_json.call_args[1]["msg"]
            )
            module.exit_json.assert_not_called()
            assert _writes(blade) == []

    def test_inline_update_with_a_wildcard_scope_fails_before_the_patch(self):
        module = _module(rules=[_realm_rule("viewer", "*")])
        stored = _stored_policy(rules=[_inline_rule("viewer", "arrays", "fb1")])
        blade = _blade(policy=stored, realms=("rzaudit", "tenant-a"))

        _main(module, blade, api_version="2.21")

        module.fail_json.assert_called_once()
        assert "realm * does not exist" in module.fail_json.call_args[1]["msg"]
        assert _writes(blade) == []


class TestOnePolicyName:
    """A name the array reads as a list or a pattern is refused before any
    read: the rules and members of every policy that matches would be
    taken for those of one policy."""

    MESSAGE = (
        "Policy name {0} is not the name of one policy: the array reads a "
        "comma as the separator of a list of names and * as a wildcard. A "
        "task manages one policy."
    )

    def test_check_one_name_refuses_a_list_and_a_wildcard(self):
        for name in ("tenant-a-ops,readonly", "tenant-*", "*", "tenant-a-ops,"):
            module = _module(name=name)

            _run(_check_one_name, module)

            module.fail_json.assert_called_once_with(msg=self.MESSAGE.format(name))

    def test_check_one_name_passes_a_single_name(self):
        """A realm-qualified name is left to the name rule of the array"""
        for name in ("tenant-a-ops", "Tenant_A", "a1", "rzaudit::tenant", ""):
            module = _module(name=name)

            _run(_check_one_name, module)

            module.fail_json.assert_not_called()

    def test_main_refuses_a_wildcard_name_before_any_read(self):
        """Two policies match: the rules of both would be reconciled as one"""
        for check_mode in (True, False):
            module = _module(
                check_mode=check_mode, name="tenant-*", rules=[_rule_spec("viewer")]
            )
            first = _current_rule("viewer", rule_id="rule-of-tenant-a")
            second = _current_rule("storage", rule_id="rule-of-tenant-b")
            blade = _blade(policy=_stored_policy(), rules=[first, second])

            _main(module, blade)

            module.fail_json.assert_called_once_with(
                msg=self.MESSAGE.format("tenant-*")
            )
            module.exit_json.assert_not_called()
            assert blade.method_calls == []

    def test_main_refuses_a_list_name_for_absent(self):
        """A list with one missing policy read as "does not exist" before"""
        for check_mode in (True, False):
            module = _module(
                check_mode=check_mode, name="tenant-a-ops,gone", state="absent"
            )
            blade = _blade()

            _main(module, blade)

            module.fail_json.assert_called_once_with(
                msg=self.MESSAGE.format("tenant-a-ops,gone")
            )
            module.exit_json.assert_not_called()
            assert blade.method_calls == []

    def test_main_refuses_a_list_that_hides_a_builtin_policy(self):
        module = _module(name="tenant-a-ops,readonly", enabled=False)
        blade = _blade(policy=_stored_policy())

        _main(module, blade)

        module.fail_json.assert_called_once_with(
            msg=self.MESSAGE.format("tenant-a-ops,readonly")
        )
        assert blade.method_calls == []

    def test_main_single_name_is_read_as_before(self):
        module = _module(name="Tenant_A-ops", enabled=False)
        blade = _blade(policy=_stored_policy())

        _main(module, blade)

        module.fail_json.assert_not_called()
        blade.get_management_access_policies.assert_called_once_with(
            names=["Tenant_A-ops"]
        )
        module.exit_json.assert_called_once_with(changed=True)
        assert _writes(blade) == ["patch_management_access_policies"]
