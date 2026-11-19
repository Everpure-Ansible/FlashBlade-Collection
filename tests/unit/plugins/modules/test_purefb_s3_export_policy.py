# Copyright: (c) 2026, Pure Storage Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_s3_export_policy module."""

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

from plugins.modules.purefb_s3_export_policy import (
    main,
    _normalize_rule,
    _normalize_existing_rule,
    _get_policy,
    _get_policy_rules,
    _reconcile_rules,
)

from plugins.modules import purefb_s3_export_policy as s3ep

MOD = "plugins.modules.purefb_s3_export_policy"
# what the array answers to a GET of a name it does not hold
MISSING = "S3 export policy does not exist."
WRITES = (
    "post_s3_export_policies",
    "patch_s3_export_policies",
    "delete_s3_export_policies",
    "post_s3_export_policies_rules",
    "patch_s3_export_policies_rules",
    "delete_s3_export_policies_rules",
)


def _error_text(res, default="Unknown error"):
    """Stand-in for get_error_message: the first error message of an answer."""
    errors = getattr(res, "errors", None)
    return errors[0].message if errors else default


def _found(*items):
    """A 200 answer holding items."""
    res = Mock()
    res.status_code = 200
    res.items = list(items)
    return res


def _refused(message=MISSING):
    """A 400 answer; the array answers a GET of a missing policy this way."""
    res = Mock()
    res.status_code = 400
    error = Mock()
    error.message = message
    res.errors = [error]
    return res


def _policy(name, enabled=True):
    """A policy as GET /s3-export-policies returns it: full name, own id."""
    policy = Mock()
    policy.name = name
    policy.enabled = enabled
    policy.id = "id-" + name.lower()
    return policy


def _rule(name, effect="allow", resources=("*",)):
    rule = Mock()
    rule.name = name
    rule.actions = ["pure:S3Access"]
    rule.effect = effect
    rule.resources = list(resources)
    return rule


def _array(policies):
    """get_s3_export_policies of an array holding policies.

    Names are matched without regard to case and returned as stored; a name
    the array does not hold is a 400, in a realm and outside of one alike.
    A comma separates names: the answer holds every policy named, once, or
    is the same 400 when one of them is missing. A blank name is a 400 of
    its own.
    """
    by_name = {policy.name.lower(): policy for policy in policies}

    def get(names=None, **kwargs):
        if not names[0].strip():
            return _refused("Missing or invalid parameter.")
        found = []
        for name in names[0].split(","):
            if not name:
                continue
            policy = by_name.get(name.lower())
            if policy is None:
                return _refused()
            if policy not in found:
                found.append(policy)
        return _found(*found) if found else _refused()

    return get


def _run(params, policies=(), check_mode=False, rules=(), reads=None):
    """Run main() against a mocked array and return (module, blade).

    The SDK models are replaced by their keyword arguments, so the body of a
    request can be compared as a dict.
    """
    full = {
        "name": None,
        "state": "present",
        "enabled": None,
        "rename": None,
        "rules": None,
        "context": "",
    }
    full.update(params)
    module = Mock()
    module.params = full
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)

    blade = Mock()
    blade.get_fleets.return_value = _found()
    blade.get_s3_export_policies.side_effect = reads or _array(policies)
    blade.get_s3_export_policies_rules.return_value = _found(*rules)
    for call in WRITES:
        getattr(blade, call).return_value = _found()

    with patch(MOD + ".AnsibleModule", return_value=module), patch(
        MOD + ".get_system", return_value=blade
    ), patch(MOD + ".LooseVersion") as loose, patch(
        MOD + ".get_error_message", _error_text
    ), patch(
        MOD + ".HAS_PYPURECLIENT", True
    ), patch(
        MOD + ".S3ExportPolicyPost", side_effect=lambda **kwargs: kwargs
    ), patch(
        MOD + ".S3ExportPolicyPatch", side_effect=lambda **kwargs: kwargs
    ), patch(
        MOD + ".S3ExportPolicyRulePost", side_effect=lambda **kwargs: kwargs
    ):
        loose.return_value.__gt__ = Mock(return_value=False)
        try:
            main()
        except SystemExit:
            pass
    return module, blade


def _writes(blade):
    """Names of the write calls main() made, in order."""
    return [call[0] for call in blade.mock_calls if call[0] in WRITES]


def _lookups(blade):
    """Policy names main() looked up, in order."""
    return [call.kwargs["names"][0] for call in blade.get_s3_export_policies.mock_calls]


def _failure(module):
    """The message main() failed with."""
    module.fail_json.assert_called_once()
    return module.fail_json.call_args[1]["msg"]


def _changed(module):
    """The changed value main() ended with, without a failure."""
    module.fail_json.assert_not_called()
    return module.exit_json.call_args[1]["changed"]


X1 = {
    "name": "x1",
    "actions": ["pure:S3Access"],
    "effect": "deny",
    "resources": ["finance-*"],
}


class TestPurefbS3ExportPolicy:
    """Test cases for purefb_s3_export_policy module"""

    # ---------------- helper-function unit tests ----------------

    def test_normalize_rule_sorts_lists(self):
        """Test _normalize_rule sorts actions and resources for stable comparison"""
        out = _normalize_rule(
            {
                "name": "r1",
                "actions": ["b", "a"],
                "effect": "allow",
                "resources": ["z", "a"],
            }
        )
        assert out == {
            "name": "r1",
            "actions": ["a", "b"],
            "effect": "allow",
            "resources": ["a", "z"],
        }

    def test_normalize_rule_handles_none_lists(self):
        """Test _normalize_rule normalizes missing lists to empty lists"""
        out = _normalize_rule({"name": "r1", "effect": "allow"})
        assert out == {
            "name": "r1",
            "actions": [],
            "effect": "allow",
            "resources": [],
        }

    def test_normalize_existing_rule_uses_attr_access(self):
        """Test _normalize_existing_rule reads rule object attributes"""
        rule = Mock()
        rule.name = "r1"
        rule.actions = ["b", "a"]
        rule.effect = "allow"
        rule.resources = ["*"]

        out = _normalize_existing_rule(rule)
        assert out == {
            "name": "r1",
            "actions": ["a", "b"],
            "effect": "allow",
            "resources": ["*"],
        }

    def test_get_policy_returns_first_item(self):
        """Test _get_policy returns the first policy when present"""
        mock_module = Mock()
        mock_module.params = {"name": "test-policy", "context": ""}

        existing_policy = Mock()
        existing_policy.name = "test-policy"
        existing_policy.enabled = True

        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.items = [existing_policy]
        mock_blade.get_s3_export_policies.return_value = mock_response

        out = _get_policy(mock_module, mock_blade)

        assert out is not None
        mock_blade.get_s3_export_policies.assert_called_once_with(names=["test-policy"])

    def test_get_policy_passes_context_when_set(self):
        """Test _get_policy forwards context_names when context is set"""
        mock_module = Mock()
        mock_module.params = {"name": "test-policy", "context": "fleet1"}

        existing_policy = Mock()
        existing_policy.name = "test-policy"

        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.items = [existing_policy]
        mock_blade.get_s3_export_policies.return_value = mock_response

        _get_policy(mock_module, mock_blade)

        mock_blade.get_s3_export_policies.assert_called_once_with(
            names=["test-policy"], context_names=["fleet1"]
        )

    @patch(MOD + ".get_error_message", _error_text)
    def test_get_policy_returns_none_when_missing(self):
        """Test _get_policy returns None when the array has no such policy"""
        mock_module = Mock()
        mock_module.params = {"name": "test-policy", "context": ""}

        mock_blade = Mock()
        mock_blade.get_s3_export_policies.return_value = _refused()

        out = _get_policy(mock_module, mock_blade)

        assert out is None
        mock_module.fail_json.assert_not_called()

    def test_get_policy_rules_returns_items(self):
        """Test _get_policy_rules returns all rule objects for the policy"""
        mock_module = Mock()
        mock_module.params = {"name": "test-policy", "context": ""}

        rule = Mock()
        rule.name = "r1"
        rule.actions = ["pure:S3Access"]
        rule.effect = "allow"
        rule.resources = ["*"]

        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.items = [rule]
        mock_blade.get_s3_export_policies_rules.return_value = mock_response

        out = _get_policy_rules(mock_module, mock_blade)

        assert len(out) == 1
        mock_blade.get_s3_export_policies_rules.assert_called_once_with(
            policy_names=["test-policy"]
        )

    # ---------------- _reconcile_rules tests ----------------

    @patch("plugins.modules.purefb_s3_export_policy.S3ExportPolicyRulePost")
    def test_reconcile_adds_missing_rules(self, mock_rule_post):
        """Test _reconcile_rules POSTs rules that are missing on the blade"""
        mock_module = Mock()
        mock_module.params = {"name": "test-policy", "context": ""}
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        get_rules_response = Mock()
        get_rules_response.status_code = 200
        get_rules_response.items = []
        mock_blade.get_s3_export_policies_rules.return_value = get_rules_response

        post_response = Mock()
        post_response.status_code = 200
        mock_blade.post_s3_export_policies_rules.return_value = post_response

        desired = [
            {
                "name": "new_rule",
                "actions": ["pure:S3Access"],
                "effect": "allow",
                "resources": ["*"],
            }
        ]

        changed = _reconcile_rules(mock_module, mock_blade, desired)

        assert changed is True
        mock_blade.post_s3_export_policies_rules.assert_called_once()
        mock_blade.patch_s3_export_policies_rules.assert_not_called()
        mock_blade.delete_s3_export_policies_rules.assert_not_called()

    @patch("plugins.modules.purefb_s3_export_policy.S3ExportPolicyRulePost")
    def test_reconcile_modifies_divergent_rules(self, mock_rule_post):
        """Test _reconcile_rules PATCHes rules whose content has drifted"""
        mock_module = Mock()
        mock_module.params = {"name": "test-policy", "context": ""}
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        existing_rule = Mock()
        existing_rule.name = "r1"
        existing_rule.actions = ["pure:S3Access"]
        existing_rule.effect = "allow"
        existing_rule.resources = ["old-*"]

        mock_blade = Mock()
        get_rules_response = Mock()
        get_rules_response.status_code = 200
        get_rules_response.items = [existing_rule]
        mock_blade.get_s3_export_policies_rules.return_value = get_rules_response

        patch_response = Mock()
        patch_response.status_code = 200
        mock_blade.patch_s3_export_policies_rules.return_value = patch_response

        desired = [
            {
                "name": "r1",
                "actions": ["pure:S3Access"],
                "effect": "allow",
                "resources": ["new-*"],
            }
        ]

        changed = _reconcile_rules(mock_module, mock_blade, desired)

        assert changed is True
        mock_blade.post_s3_export_policies_rules.assert_not_called()
        mock_blade.patch_s3_export_policies_rules.assert_called_once()
        mock_blade.delete_s3_export_policies_rules.assert_not_called()

    def test_reconcile_removes_orphan_rules(self):
        """Test _reconcile_rules DELETEs rules that are absent from desired"""
        mock_module = Mock()
        mock_module.params = {"name": "test-policy", "context": ""}
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        keep_rule = Mock()
        keep_rule.name = "keep"
        keep_rule.actions = ["pure:S3Access"]
        keep_rule.effect = "allow"
        keep_rule.resources = ["*"]

        drop_rule = Mock()
        drop_rule.name = "drop"
        drop_rule.actions = ["pure:S3Access"]
        drop_rule.effect = "allow"
        drop_rule.resources = ["*"]

        mock_blade = Mock()
        get_rules_response = Mock()
        get_rules_response.status_code = 200
        get_rules_response.items = [keep_rule, drop_rule]
        mock_blade.get_s3_export_policies_rules.return_value = get_rules_response

        delete_response = Mock()
        delete_response.status_code = 200
        mock_blade.delete_s3_export_policies_rules.return_value = delete_response

        desired = [
            {
                "name": "keep",
                "actions": ["pure:S3Access"],
                "effect": "allow",
                "resources": ["*"],
            }
        ]

        changed = _reconcile_rules(mock_module, mock_blade, desired)

        assert changed is True
        mock_blade.delete_s3_export_policies_rules.assert_called_once()
        call_kwargs = mock_blade.delete_s3_export_policies_rules.call_args[1]
        assert call_kwargs["names"] == ["drop"]
        mock_blade.post_s3_export_policies_rules.assert_not_called()
        mock_blade.patch_s3_export_policies_rules.assert_not_called()

    def test_reconcile_idempotent_when_match(self):
        """Test _reconcile_rules makes no calls when desired matches current"""
        mock_module = Mock()
        mock_module.params = {"name": "test-policy", "context": ""}
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        existing_rule = Mock()
        existing_rule.name = "r1"
        existing_rule.actions = ["pure:S3Access"]
        existing_rule.effect = "allow"
        existing_rule.resources = ["*"]

        mock_blade = Mock()
        get_rules_response = Mock()
        get_rules_response.status_code = 200
        get_rules_response.items = [existing_rule]
        mock_blade.get_s3_export_policies_rules.return_value = get_rules_response

        desired = [
            {
                "name": "r1",
                "actions": ["pure:S3Access"],
                "effect": "allow",
                "resources": ["*"],
            }
        ]

        changed = _reconcile_rules(mock_module, mock_blade, desired)

        assert changed is False
        mock_blade.post_s3_export_policies_rules.assert_not_called()
        mock_blade.patch_s3_export_policies_rules.assert_not_called()
        mock_blade.delete_s3_export_policies_rules.assert_not_called()

    def test_reconcile_check_mode_skips_writes(self):
        """Test _reconcile_rules reports changed but skips writes in check mode"""
        mock_module = Mock()
        mock_module.params = {"name": "test-policy", "context": ""}
        mock_module.check_mode = True
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        get_rules_response = Mock()
        get_rules_response.status_code = 200
        get_rules_response.items = []
        mock_blade.get_s3_export_policies_rules.return_value = get_rules_response

        desired = [
            {
                "name": "new_rule",
                "actions": ["pure:S3Access"],
                "effect": "allow",
                "resources": ["*"],
            }
        ]

        changed = _reconcile_rules(mock_module, mock_blade, desired)

        assert changed is True
        mock_blade.post_s3_export_policies_rules.assert_not_called()

    # ---------------- main() flows ----------------

    @patch("plugins.modules.purefb_s3_export_policy.LooseVersion")
    @patch("plugins.modules.purefb_s3_export_policy.S3ExportPolicyPost")
    @patch("plugins.modules.purefb_s3_export_policy.get_system")
    @patch("plugins.modules.purefb_s3_export_policy.AnsibleModule")
    @patch("plugins.modules.purefb_s3_export_policy.HAS_PYPURECLIENT", True)
    def test_main_creates_policy(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_policy_post,
        mock_loose_version,
    ):
        """Test creating a new S3 export policy"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-policy",
            "state": "present",
            "enabled": True,
            "rename": None,
            "rules": None,
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        # Policy does not exist
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_s3_export_policies.return_value = get_response

        # Mock successful policy creation
        post_response = Mock()
        post_response.status_code = 200
        mock_blade.post_s3_export_policies.return_value = post_response

        # Call main
        try:
            main()
        except SystemExit:
            pass

        # Verify post_s3_export_policies was called
        mock_blade.post_s3_export_policies.assert_called_once()
        call_kwargs = mock_blade.post_s3_export_policies.call_args[1]
        assert call_kwargs["names"] == ["test-policy"]

        # Verify exit_json was called with changed=True
        mock_module.exit_json.assert_called_once()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_s3_export_policy.LooseVersion")
    @patch("plugins.modules.purefb_s3_export_policy.S3ExportPolicyPost")
    @patch("plugins.modules.purefb_s3_export_policy.get_system")
    @patch("plugins.modules.purefb_s3_export_policy.AnsibleModule")
    @patch("plugins.modules.purefb_s3_export_policy.HAS_PYPURECLIENT", True)
    def test_main_create_check_mode_skips_post(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_policy_post,
        mock_loose_version,
    ):
        """Test create reports changed but skips POST in check mode"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-policy",
            "state": "present",
            "enabled": True,
            "rename": None,
            "rules": None,
            "context": "",
        }
        mock_module.check_mode = True
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        # Policy does not exist
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_s3_export_policies.return_value = get_response

        # Call main
        try:
            main()
        except SystemExit:
            pass

        # Verify no POST was made
        mock_blade.post_s3_export_policies.assert_not_called()

        # Verify exit_json was called with changed=True
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_s3_export_policy.LooseVersion")
    @patch("plugins.modules.purefb_s3_export_policy.S3ExportPolicyPatch")
    @patch("plugins.modules.purefb_s3_export_policy.get_system")
    @patch("plugins.modules.purefb_s3_export_policy.AnsibleModule")
    @patch("plugins.modules.purefb_s3_export_policy.HAS_PYPURECLIENT", True)
    def test_main_updates_enabled_flag(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_patch_cls,
        mock_loose_version,
    ):
        """Test updating the enabled flag on an existing policy"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-policy",
            "state": "present",
            "enabled": False,
            "rename": None,
            "rules": None,
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        # Existing policy with enabled=True
        existing_policy = Mock()
        existing_policy.name = "test-policy"
        existing_policy.enabled = True

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing_policy]
        mock_blade.get_s3_export_policies.return_value = get_response

        # Mock successful patch
        patch_response = Mock()
        patch_response.status_code = 200
        mock_blade.patch_s3_export_policies.return_value = patch_response

        # Call main
        try:
            main()
        except SystemExit:
            pass

        # Verify patch_s3_export_policies was called
        mock_blade.patch_s3_export_policies.assert_called_once()

        # Verify exit_json was called with changed=True
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_s3_export_policy.LooseVersion")
    @patch("plugins.modules.purefb_s3_export_policy.get_system")
    @patch("plugins.modules.purefb_s3_export_policy.AnsibleModule")
    @patch("plugins.modules.purefb_s3_export_policy.HAS_PYPURECLIENT", True)
    def test_main_update_idempotent_when_enabled_matches(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test update is a no-op when desired enabled already matches"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-policy",
            "state": "present",
            "enabled": True,
            "rename": None,
            "rules": None,
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        # Existing policy already has enabled=True
        existing_policy = Mock()
        existing_policy.name = "test-policy"
        existing_policy.enabled = True

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing_policy]
        mock_blade.get_s3_export_policies.return_value = get_response

        # Call main
        try:
            main()
        except SystemExit:
            pass

        # Verify no patch was made
        mock_blade.patch_s3_export_policies.assert_not_called()

        # Verify exit_json was called with changed=False
        assert mock_module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_s3_export_policy.LooseVersion")
    @patch("plugins.modules.purefb_s3_export_policy.S3ExportPolicyPatch")
    @patch("plugins.modules.purefb_s3_export_policy.get_system")
    @patch("plugins.modules.purefb_s3_export_policy.AnsibleModule")
    @patch("plugins.modules.purefb_s3_export_policy.HAS_PYPURECLIENT", True)
    @patch(MOD + ".get_error_message", _error_text)
    def test_main_renames_policy(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_patch_cls,
        mock_loose_version,
    ):
        """Test renaming an existing policy"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-policy",
            "state": "present",
            "enabled": None,
            "rename": "renamed-policy",
            "rules": None,
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        # Existing policy
        existing_policy = Mock()
        existing_policy.name = "test-policy"
        existing_policy.enabled = True

        # the array holds this policy only: the new name is free
        mock_blade.get_s3_export_policies.side_effect = _array([existing_policy])

        # Mock successful patch
        patch_response = Mock()
        patch_response.status_code = 200
        mock_blade.patch_s3_export_policies.return_value = patch_response

        # Call main
        try:
            main()
        except SystemExit:
            pass

        # Verify patch_s3_export_policies was called
        mock_blade.patch_s3_export_policies.assert_called_once()
        patch_kwargs = mock_blade.patch_s3_export_policies.call_args[1]
        assert patch_kwargs["names"] == ["test-policy"]
        mock_patch_cls.assert_called_once_with(name="renamed-policy")

        # Verify exit_json was called with changed=True
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_s3_export_policy.LooseVersion")
    @patch("plugins.modules.purefb_s3_export_policy.get_system")
    @patch("plugins.modules.purefb_s3_export_policy.AnsibleModule")
    @patch("plugins.modules.purefb_s3_export_policy.HAS_PYPURECLIENT", True)
    @patch(MOD + ".get_error_message", _error_text)
    def test_main_rename_is_idempotent_when_already_renamed(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """A repeated rename finds no policy under the old name but one under
        the new name: that is the desired state, not an error, and no change."""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-policy",
            "state": "present",
            "enabled": None,
            "rename": "renamed-policy",
            "rules": None,
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        mock_get_system.return_value = mock_blade

        renamed_policy = Mock()
        renamed_policy.name = "renamed-policy"
        renamed_policy.enabled = True

        mock_blade.get_s3_export_policies.side_effect = _array([renamed_policy])

        try:
            main()
        except SystemExit:
            pass

        mock_module.fail_json.assert_not_called()
        mock_blade.patch_s3_export_policies.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_s3_export_policy.LooseVersion")
    @patch("plugins.modules.purefb_s3_export_policy.S3ExportPolicyRulePost")
    @patch("plugins.modules.purefb_s3_export_policy.S3ExportPolicyPatch")
    @patch("plugins.modules.purefb_s3_export_policy.get_system")
    @patch("plugins.modules.purefb_s3_export_policy.AnsibleModule")
    @patch("plugins.modules.purefb_s3_export_policy.HAS_PYPURECLIENT", True)
    @patch(MOD + ".get_error_message", _error_text)
    def test_main_reconciles_rules_before_rename(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_patch_cls,
        mock_rule_post,
        mock_loose_version,
    ):
        """Rules are reconciled under the current name before the rename PATCH,
        otherwise the rule calls would address a name that no longer exists."""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-policy",
            "state": "present",
            "enabled": None,
            "rename": "renamed-policy",
            "rules": [
                {
                    "name": "r1",
                    "actions": ["pure:S3Access"],
                    "effect": "allow",
                    "resources": ["*"],
                }
            ],
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        mock_get_system.return_value = mock_blade

        existing_policy = Mock()
        existing_policy.name = "test-policy"
        existing_policy.enabled = True
        # the array holds this policy only: the new name is free
        mock_blade.get_s3_export_policies.side_effect = _array([existing_policy])

        # No rules yet, so r1 has to be added
        get_rules_response = Mock()
        get_rules_response.status_code = 200
        get_rules_response.items = []
        mock_blade.get_s3_export_policies_rules.return_value = get_rules_response
        mock_blade.post_s3_export_policies_rules.return_value.status_code = 200
        mock_blade.patch_s3_export_policies.return_value.status_code = 200

        try:
            main()
        except SystemExit:
            pass

        rule_kwargs = mock_blade.post_s3_export_policies_rules.call_args[1]
        assert rule_kwargs["policy_names"] == ["test-policy"]
        call_names = [c[0] for c in mock_blade.mock_calls]
        assert call_names.index("post_s3_export_policies_rules") < call_names.index(
            "patch_s3_export_policies"
        )
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_s3_export_policy.LooseVersion")
    @patch("plugins.modules.purefb_s3_export_policy.get_system")
    @patch("plugins.modules.purefb_s3_export_policy.AnsibleModule")
    @patch("plugins.modules.purefb_s3_export_policy.HAS_PYPURECLIENT", True)
    def test_main_standalone_array_sends_no_context(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """An array that is not in a fleet must not get a default context; the
        array rejects context_names with 'Cannot find array in fleet'."""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-policy",
            "state": "absent",
            "enabled": None,
            "rename": None,
            "rules": None,
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        mock_blade.get_fleets.return_value.status_code = 200
        mock_blade.get_fleets.return_value.items = []
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_s3_export_policies.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        assert mock_module.params["context"] == ""
        mock_blade.get_s3_export_policies.assert_called_once_with(names=["test-policy"])

    @patch("plugins.modules.purefb_s3_export_policy.LooseVersion")
    @patch("plugins.modules.purefb_s3_export_policy.get_system")
    @patch("plugins.modules.purefb_s3_export_policy.AnsibleModule")
    @patch("plugins.modules.purefb_s3_export_policy.HAS_PYPURECLIENT", True)
    def test_main_fleet_member_defaults_context_to_local_array(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-policy",
            "state": "absent",
            "enabled": None,
            "rename": None,
            "rules": None,
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        mock_blade.get_fleets.return_value.status_code = 200
        mock_blade.get_fleets.return_value.items = [Mock()]
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_s3_export_policies.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        assert mock_module.params["context"] == "local-array"
        mock_blade.get_s3_export_policies.assert_called_once_with(
            names=["test-policy"], context_names=["local-array"]
        )

    @patch("plugins.modules.purefb_s3_export_policy.LooseVersion")
    @patch("plugins.modules.purefb_s3_export_policy.get_system")
    @patch("plugins.modules.purefb_s3_export_policy.AnsibleModule")
    @patch("plugins.modules.purefb_s3_export_policy.HAS_PYPURECLIENT", True)
    def test_main_deletes_policy(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test deleting an existing policy"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-policy",
            "state": "absent",
            "enabled": None,
            "rename": None,
            "rules": None,
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        # Existing policy
        existing_policy = Mock()
        existing_policy.name = "test-policy"
        existing_policy.enabled = True

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing_policy]
        mock_blade.get_s3_export_policies.return_value = get_response

        # Mock successful delete
        delete_response = Mock()
        delete_response.status_code = 200
        mock_blade.delete_s3_export_policies.return_value = delete_response

        # Call main
        try:
            main()
        except SystemExit:
            pass

        # Verify delete_s3_export_policies was called
        mock_blade.delete_s3_export_policies.assert_called_once()
        call_kwargs = mock_blade.delete_s3_export_policies.call_args[1]
        assert call_kwargs["names"] == ["test-policy"]

        # Verify exit_json was called with changed=True
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_s3_export_policy.LooseVersion")
    @patch("plugins.modules.purefb_s3_export_policy.get_system")
    @patch("plugins.modules.purefb_s3_export_policy.AnsibleModule")
    @patch("plugins.modules.purefb_s3_export_policy.HAS_PYPURECLIENT", True)
    def test_main_delete_idempotent_when_absent(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test delete is a no-op when the policy does not exist"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-policy",
            "state": "absent",
            "enabled": None,
            "rename": None,
            "rules": None,
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        # Policy does not exist
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_s3_export_policies.return_value = get_response

        # Call main
        try:
            main()
        except SystemExit:
            pass

        # Verify no delete was made
        mock_blade.delete_s3_export_policies.assert_not_called()

        # Verify exit_json was called with changed=False
        assert mock_module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_s3_export_policy.LooseVersion")
    @patch("plugins.modules.purefb_s3_export_policy.get_system")
    @patch("plugins.modules.purefb_s3_export_policy.AnsibleModule")
    @patch("plugins.modules.purefb_s3_export_policy.HAS_PYPURECLIENT", True)
    def test_main_fails_when_api_version_too_old(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test failure when API version is too old"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-policy",
            "state": "present",
            "enabled": None,
            "rename": None,
            "rules": None,
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade with too-old API versions
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.10", "2.15", "2.19"]
        mock_get_system.return_value = mock_blade

        # Call main - expect failure
        try:
            main()
        except SystemExit:
            pass

        # Verify fail_json was called
        mock_module.fail_json.assert_called_once()
        assert (
            "FlashBlade REST version not supported"
            in mock_module.fail_json.call_args[1]["msg"]
        )

    @patch("plugins.modules.purefb_s3_export_policy.LooseVersion")
    @patch("plugins.modules.purefb_s3_export_policy.S3ExportPolicyPost")
    @patch("plugins.modules.purefb_s3_export_policy.get_system")
    @patch("plugins.modules.purefb_s3_export_policy.AnsibleModule")
    @patch("plugins.modules.purefb_s3_export_policy.HAS_PYPURECLIENT", True)
    def test_main_create_failure_calls_fail_json(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_post_cls,
        mock_loose_version,
    ):
        """Test SDK error on create is surfaced via fail_json"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "name": "test-policy",
            "state": "present",
            "enabled": True,
            "rename": None,
            "rules": None,
            "context": "",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        local_array = Mock()
        local_array.name = "local-array"
        mock_blade.get_arrays.return_value.items = [local_array]
        mock_get_system.return_value = mock_blade

        # Policy does not exist
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_s3_export_policies.return_value = get_response

        # Mock failed policy creation
        post_response = Mock()
        post_response.status_code = 400
        post_err = Mock()
        post_err.message = "nope"
        post_response.errors = [post_err]
        mock_blade.post_s3_export_policies.return_value = post_response

        # Call main - expect failure
        try:
            main()
        except SystemExit:
            pass

        # Verify fail_json was called
        mock_module.fail_json.assert_called_once()
        assert (
            "Failed to create S3 export policy"
            in mock_module.fail_json.call_args[1]["msg"]
        )


class TestPurefbS3ExportPolicyRealms:
    """Realm names, the scope of a rename and failed reads"""

    # ---------------- name helpers ----------------

    def test_realm_and_leaf_of_a_name(self):
        """The realm is the part before the last '::', the rest is the leaf"""
        assert s3ep._realm("realm1::pol") == "realm1"
        assert s3ep._leaf("realm1::pol") == "pol"
        assert s3ep._realm("pol") == ""
        assert s3ep._leaf("pol") == "pol"
        assert s3ep._realm(None) == ""
        assert s3ep._leaf(None) == ""

    def test_resolve_rename_without_rename(self):
        """No rename, nothing to resolve and nothing to refuse"""
        module = Mock()
        module.params = {"name": "realm1::pol", "rename": None}
        assert s3ep._resolve_rename(module) is None
        module.fail_json.assert_not_called()

    def test_resolve_rename_array_level_name_is_kept(self):
        """A bare new name for a policy outside a realm is used as given"""
        module = Mock()
        module.params = {"name": "pol", "rename": "new"}
        assert s3ep._resolve_rename(module) == "new"
        module.fail_json.assert_not_called()

    def test_resolve_rename_bare_name_stays_in_realm(self):
        """A bare new name for a policy in a realm is a name in that realm"""
        module = Mock()
        module.params = {"name": "realm1::pol", "rename": "new"}
        assert s3ep._resolve_rename(module) == "realm1::new"
        module.fail_json.assert_not_called()

    def test_resolve_rename_same_realm_in_any_case(self):
        """The realm of the new name is compared without regard to case"""
        module = Mock()
        module.params = {"name": "realm1::pol", "rename": "REALM1::new"}
        assert s3ep._resolve_rename(module) == "realm1::new"
        module.fail_json.assert_not_called()

    def test_resolve_rename_refuses_another_realm(self):
        """A new name in another realm is refused and names the valid forms"""
        module = Mock()
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = {"name": "realm1::pol", "rename": "realm2::new"}
        try:
            s3ep._resolve_rename(module)
        except SystemExit:
            pass
        msg = _failure(module)
        assert "cannot move a policy into or out of a realm" in msg
        assert "realm1::<name>" in msg

    def test_resolve_rename_refuses_a_realm_for_an_array_level_policy(self):
        """A policy outside a realm cannot be renamed into one"""
        module = Mock()
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = {"name": "pol", "rename": "realm1::new"}
        try:
            s3ep._resolve_rename(module)
        except SystemExit:
            pass
        msg = _failure(module)
        assert "cannot move a policy into or out of a realm" in msg
        assert msg.endswith("Give the new name without a realm.")

    # ---------------- reads ----------------

    @patch(MOD + ".get_error_message", _error_text)
    def test_read_missing_policy_in_realm_is_absent(self):
        """Only the array's 'does not exist' answer reads as absent"""
        module = Mock()
        module.params = {"name": "realm1::pol", "context": ""}
        blade = Mock()
        blade.get_s3_export_policies.return_value = _refused()

        assert _get_policy(module, blade) is None
        module.fail_json.assert_not_called()
        blade.get_s3_export_policies.assert_called_once_with(names=["realm1::pol"])

    @patch(MOD + ".get_error_message", _error_text)
    def test_read_refused_is_reported_not_absent(self):
        """A refused read fails with the array's message instead of 'absent'"""
        module = Mock()
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = {"name": "realm1::pol", "context": ""}
        blade = Mock()
        blade.get_s3_export_policies.return_value = _refused("Operation not permitted.")

        try:
            _get_policy(module, blade)
        except SystemExit:
            pass

        msg = _failure(module)
        assert "Failed to read S3 export policy realm1::pol" in msg
        assert "Operation not permitted." in msg

    @patch(MOD + ".get_error_message", _error_text)
    def test_read_rules_refused_is_reported_not_empty(self):
        """A failed read of the rules is not an empty rule list"""
        module = Mock()
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = {"name": "realm1::pol", "context": ""}
        blade = Mock()
        blade.get_s3_export_policies_rules.return_value = _refused(
            "Operation not permitted."
        )

        try:
            _get_policy_rules(module, blade)
        except SystemExit:
            pass

        msg = _failure(module)
        assert "Failed to read the rules of S3 export policy realm1::pol" in msg
        assert "Operation not permitted." in msg

    def test_main_refused_read_never_creates(self):
        """A refused read of name must not end in a create or a delete"""

        def refuse(names=None, **kwargs):
            return _refused("Operation not permitted.")

        for state in ("present", "absent"):
            module, blade = _run(
                {"name": "realm1::pol", "state": state, "enabled": True},
                reads=refuse,
            )
            assert "Operation not permitted." in _failure(module)
            assert _writes(blade) == []

    def test_main_refused_rules_read_sends_no_rule(self):
        """With the rule list unread no rule is added, changed or removed"""
        module = Mock()
        module.params = {"name": "realm1::pol", "context": ""}
        module.check_mode = False
        module.fail_json = Mock(side_effect=SystemExit)
        blade = Mock()
        blade.get_s3_export_policies_rules.return_value = _refused(
            "Operation not permitted."
        )
        with patch(MOD + ".get_error_message", _error_text):
            try:
                _reconcile_rules(module, blade, [X1])
            except SystemExit:
                pass
        _failure(module)
        assert _writes(blade) == []

    # ---------------- create, update and delete in a realm ----------------

    def test_main_creates_policy_in_realm(self):
        """A realm policy is created under its realm::policy name"""
        module, blade = _run({"name": "realm1::pol", "rules": [X1]})

        assert _changed(module) is True
        assert _writes(blade) == ["post_s3_export_policies"]
        kwargs = blade.post_s3_export_policies.call_args[1]
        assert kwargs["names"] == ["realm1::pol"]
        assert kwargs["policy"]["rules"][0]["name"] == "x1"

    def test_main_updates_realm_policy_not_its_namesakes(self):
        """Every call for a realm policy carries the realm::policy name"""
        policies = [
            _policy("realm1::pol"),
            _policy("pol"),
            _policy("realm2::pol"),
        ]
        module, blade = _run(
            {"name": "realm1::pol", "enabled": False, "rules": [X1]},
            policies=policies,
            rules=[_rule("keep")],
        )

        assert _changed(module) is True
        assert _lookups(blade) == ["realm1::pol"]
        blade.get_s3_export_policies_rules.assert_called_once_with(
            policy_names=["realm1::pol"]
        )
        for call in (
            blade.post_s3_export_policies_rules,
            blade.delete_s3_export_policies_rules,
        ):
            assert call.call_args[1]["policy_names"] == ["realm1::pol"]
        kwargs = blade.patch_s3_export_policies.call_args[1]
        assert kwargs["names"] == ["realm1::pol"]
        assert kwargs["policy"] == {"enabled": False}

    def test_main_realm_policy_idempotent(self):
        """A realm policy that matches the task is left alone"""
        module, blade = _run(
            {"name": "realm1::pol", "enabled": True, "rules": [X1]},
            policies=[_policy("realm1::pol")],
            rules=[_rule("x1", effect="deny", resources=["finance-*"])],
        )

        assert _changed(module) is False
        assert _writes(blade) == []

    def test_main_deletes_realm_policy(self):
        """state=absent removes the realm policy, twice is a no-op"""
        module, blade = _run(
            {"name": "realm1::pol", "state": "absent"},
            policies=[_policy("realm1::pol"), _policy("pol")],
        )
        assert _changed(module) is True
        assert _writes(blade) == ["delete_s3_export_policies"]
        assert blade.delete_s3_export_policies.call_args[1]["names"] == ["realm1::pol"]

        module, blade = _run(
            {"name": "realm1::pol", "state": "absent"},
            policies=[_policy("pol")],
        )
        assert _changed(module) is False
        assert _writes(blade) == []

    def test_main_name_in_another_case_is_not_drift(self):
        """The array matches names without regard to case: the stored name
        is used for the calls and a differently cased name is no change"""
        policies = [_policy("realm1::Pol")]
        module, blade = _run(
            {"name": "REALM1::pol", "enabled": True, "rename": "REALM1::Pol"},
            policies=policies,
        )
        assert _changed(module) is False
        assert _writes(blade) == []

        module, blade = _run(
            {"name": "REALM1::pol", "enabled": False}, policies=policies
        )
        assert _changed(module) is True
        assert blade.patch_s3_export_policies.call_args[1]["names"] == ["realm1::Pol"]

    # ---------------- rename ----------------

    def test_main_array_level_rename_is_unchanged(self):
        """Outside a realm the rename is sent as before"""
        module, blade = _run(
            {"name": "pol", "rename": "new"}, policies=[_policy("pol")]
        )

        assert _changed(module) is True
        assert _writes(blade) == ["patch_s3_export_policies"]
        kwargs = blade.patch_s3_export_policies.call_args[1]
        assert kwargs["names"] == ["pol"]
        assert kwargs["policy"] == {"name": "new"}

    def test_main_bare_rename_in_realm_is_qualified(self):
        """A bare new name is sent with the realm of the policy; a policy
        outside the realm that has the new name is neither read nor touched"""
        for check_mode in (True, False):
            module, blade = _run(
                {"name": "realm1::pol", "rename": "new"},
                policies=[_policy("realm1::pol"), _policy("new")],
                check_mode=check_mode,
            )

            assert _changed(module) is True
            assert _lookups(blade) == ["realm1::pol", "realm1::new"]
            if check_mode:
                assert _writes(blade) == []
                continue
            assert _writes(blade) == ["patch_s3_export_policies"]
            kwargs = blade.patch_s3_export_policies.call_args[1]
            assert kwargs["names"] == ["realm1::pol"]
            assert kwargs["policy"] == {"name": "realm1::new"}

    def test_main_rename_takes_realm_as_the_array_stores_it(self):
        """The new name carries the realm in the stored spelling, which is
        the one the array accepts"""
        module, blade = _run(
            {"name": "REALM1::pol", "rename": "REALM1::new"},
            policies=[_policy("realm1::pol")],
        )

        assert _changed(module) is True
        kwargs = blade.patch_s3_export_policies.call_args[1]
        assert kwargs["names"] == ["realm1::pol"]
        assert kwargs["policy"] == {"name": "realm1::new"}

    def test_main_rename_already_applied_in_realm(self):
        """name gone and the new name present in the same realm: the rename
        is done, the policy is managed under its new name"""
        policies = [_policy("realm1::new")]
        module, blade = _run(
            {"name": "realm1::old", "rename": "new"}, policies=policies
        )
        assert _changed(module) is False
        assert _lookups(blade) == ["realm1::old", "realm1::new"]
        assert _writes(blade) == []

        module, blade = _run(
            {"name": "realm1::old", "rename": "new", "enabled": False, "rules": [X1]},
            policies=policies,
        )
        assert _changed(module) is True
        assert _writes(blade) == [
            "post_s3_export_policies_rules",
            "patch_s3_export_policies",
        ]
        rule_kwargs = blade.post_s3_export_policies_rules.call_args[1]
        assert rule_kwargs["policy_names"] == ["realm1::new"]
        kwargs = blade.patch_s3_export_policies.call_args[1]
        assert kwargs["names"] == ["realm1::new"]
        assert kwargs["policy"] == {"enabled": False}

    def test_main_missing_name_never_adopts_policy_outside_the_realm(self):
        """name is gone from the realm and a policy outside the realm has
        the new name: that policy is not the renamed one and stays as it is"""
        for check_mode in (True, False):
            module, blade = _run(
                {
                    "name": "realm1::gone",
                    "rename": "pol",
                    "enabled": False,
                    "rules": [X1],
                },
                policies=[_policy("pol"), _policy("realm2::pol")],
                rules=[_rule("keep")],
                check_mode=check_mode,
            )

            msg = _failure(module)
            assert "realm1::gone" in msg
            assert "neither does a policy named realm1::pol" in msg
            assert _lookups(blade) == ["realm1::gone", "realm1::pol"]
            assert _writes(blade) == []
            blade.get_s3_export_policies_rules.assert_not_called()

    def test_main_rename_into_another_realm_refused_before_any_read(self):
        """A new name in another realm is refused in both modes, whether or
        not name exists, and nothing is read or written"""
        cases = [
            ("realm1::gone", "realm2::pol"),
            ("realm1::pol", "realm2::pol"),
            ("realm1::pol", "realm2::new"),
            ("gone", "realm1::pol"),
            ("pol", "realm1::new"),
        ]
        for name, rename in cases:
            for check_mode in (True, False):
                module, blade = _run(
                    {"name": name, "rename": rename, "enabled": False, "rules": [X1]},
                    policies=[
                        _policy("pol"),
                        _policy("realm1::pol"),
                        _policy("realm2::pol"),
                    ],
                    rules=[_rule("keep")],
                    check_mode=check_mode,
                )

                msg = _failure(module)
                assert "cannot move a policy into or out of a realm" in msg
                assert _lookups(blade) == []
                assert _writes(blade) == []

    def test_main_absent_with_missing_name_ignores_rename(self):
        """state=absent removes name only: with name gone nothing is deleted,
        whatever policy the rename option names"""
        cases = [
            ("realm1::gone", "pol"),
            ("realm1::gone", "realm2::pol"),
            ("gone", "pol"),
            ("gone", "realm1::pol"),
        ]
        for name, rename in cases:
            for check_mode in (True, False):
                module, blade = _run(
                    {"name": name, "rename": rename, "state": "absent"},
                    policies=[
                        _policy("pol"),
                        _policy("realm1::pol"),
                        _policy("realm2::pol"),
                    ],
                    check_mode=check_mode,
                )

                assert _changed(module) is False
                assert _lookups(blade) == [name]
                assert _writes(blade) == []

    def test_main_absent_with_rename_deletes_name(self):
        """state=absent with a rename still deletes the policy called name"""
        module, blade = _run(
            {"name": "realm1::pol", "rename": "realm2::other", "state": "absent"},
            policies=[_policy("realm1::pol"), _policy("realm2::other")],
        )

        assert _changed(module) is True
        assert _lookups(blade) == ["realm1::pol"]
        assert _writes(blade) == ["delete_s3_export_policies"]
        assert blade.delete_s3_export_policies.call_args[1]["names"] == ["realm1::pol"]

    def test_main_rename_to_taken_name_refused_before_rules(self):
        """Another policy has the new name: refused in both modes before a
        rule or the policy is changed"""
        for policies, name in (
            ([_policy("realm1::pol"), _policy("realm1::new")], "realm1::pol"),
            ([_policy("pol"), _policy("new")], "pol"),
        ):
            for check_mode in (True, False):
                module, blade = _run(
                    {"name": name, "rename": "new", "enabled": False, "rules": [X1]},
                    policies=policies,
                    rules=[_rule("keep")],
                    check_mode=check_mode,
                )

                assert "already exists" in _failure(module)
                assert _writes(blade) == []
                blade.get_s3_export_policies_rules.assert_not_called()

    def test_main_rename_that_only_changes_case_refused(self):
        """The array does not rename a policy to its own name in another
        case ('Policy already exists.'): refused before any write"""
        for policies, name, rename in (
            ([_policy("pol")], "pol", "POL"),
            ([_policy("realm1::pol")], "realm1::pol", "Pol"),
            ([_policy("realm1::pol")], "realm1::pol", "realm1::POL"),
        ):
            for check_mode in (True, False):
                module, blade = _run(
                    {"name": name, "rename": rename, "rules": [X1]},
                    policies=policies,
                    rules=[_rule("keep")],
                    check_mode=check_mode,
                )

                assert "only in case" in _failure(module)
                assert _writes(blade) == []
                blade.get_s3_export_policies_rules.assert_not_called()

    # ---------------- names holding a comma ----------------

    def test_main_name_holding_a_comma_refused(self):
        """The array reads a comma as a separator of names and answers with
        every policy named: such a name is refused before any lookup"""
        policies = [_policy("pol"), _policy("other"), _policy("realm1::pol")]
        for name in ("pol,other", "other,pol", "pol,", "pol,gone", "realm1::pol,pol"):
            for state in ("present", "absent"):
                for check_mode in (True, False):
                    module, blade = _run(
                        {"name": name, "state": state, "enabled": False},
                        policies=policies,
                        check_mode=check_mode,
                    )

                    msg = _failure(module)
                    assert "name {0} holds a comma".format(name) in msg
                    assert _lookups(blade) == []
                    assert _writes(blade) == []

    def test_main_rename_holding_a_comma_refused(self):
        """A new name holding a comma is refused whether or not name exists:
        with name gone, the lookup of it answers with the policies it names
        and the first of them would be taken for the renamed policy"""
        policies = [_policy("pol"), _policy("other")]
        for name, rename in (
            ("gone", "pol,other"),
            ("gone", "other,"),
            ("pol", "new,other"),
            ("pol", "new,"),
        ):
            for check_mode in (True, False):
                module, blade = _run(
                    {"name": name, "rename": rename, "enabled": False},
                    policies=policies,
                    check_mode=check_mode,
                )

                msg = _failure(module)
                assert "rename {0} holds a comma".format(rename) in msg
                assert _lookups(blade) == []
                assert _writes(blade) == []

    def test_main_absent_does_not_read_rename_holding_a_comma(self):
        """rename is ignored with state=absent, whatever it holds"""
        module, blade = _run(
            {"name": "pol", "rename": "new,other", "state": "absent"},
            policies=[_policy("pol"), _policy("other")],
        )

        assert _changed(module) is True
        assert _lookups(blade) == ["pol"]
        assert _writes(blade) == ["delete_s3_export_policies"]
        assert blade.delete_s3_export_policies.call_args[1]["names"] == ["pol"]

    def test_main_rename_of_missing_policy_fails(self):
        """Neither name nor the new name exists: nothing to rename"""
        module, blade = _run({"name": "pol", "rename": "new"})

        msg = _failure(module)
        assert "Cannot rename S3 export policy pol" in msg
        assert "neither does a policy named new" in msg
        assert _writes(blade) == []
