# Copyright: (c) 2026, Pure Storage Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_mgmt_role module."""

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

from plugins.modules.purefb_mgmt_role import (
    main,
    _ctx,
    _normalize_resource,
    _normalize_actions,
    _validate_role_name,
    _read_named,
    _get_role,
    _get_permissions,
    _role_referenced_by_rule,
    _delete_role,
    _create_role,
    _reconcile_permissions,
    _current_attached_policy_names,
    _subject_exists,
    _handle_role,
    _handle_attach,
    RESOURCE_PREFIX,
)


def _base_params(**overrides):
    """Return a full params dict with sane defaults, patched by overrides."""
    params = {
        "object": "role",
        "state": "present",
        "name": "backup-operator",
        "description": None,
        "permissions": None,
        "admin": None,
        "ds_role": None,
        "policies": None,
        "context": "",
    }
    params.update(overrides)
    return params


GEM = "plugins.modules.purefb_mgmt_role.get_error_message"
LOOSE = "plugins.modules.purefb_mgmt_role.LooseVersion"

# Messages of the array (Purity//FB 4.8.8) for a name that does not exist,
# for a read it refuses and for a context that is not a fleet member.
ROLE_MISSING = "Management access policy role does not exist."
ADMIN_MISSING = "Admin does not exist."
DS_ROLE_MISSING = "Directory service role does not exist."
REFUSED = "Operation not permitted."
REFUSED_VERB = (
    "Operation not permitted. Authorization for 'get' on "
    "'purestorage.com/api/v2/policies/management-access/members' is required."
)
NOT_IN_FLEET = "Cannot find array in fleet"


def _ok(items):
    """A 200 answer holding items."""
    res = Mock()
    res.status_code = 200
    res.items = items
    return res


def _err(status_code=400):
    """An error answer: like the SDK's ErrorResponse it has no items.

    The message is what the patched get_error_message returns.
    """
    res = Mock(spec=["status_code", "errors"])
    res.status_code = status_code
    res.errors = [Mock()]
    return res


def _role_obj(name="backup-operator", role_id="role-id-1", pure_defined=False):
    """A role as GET management-access-policies/roles returns it."""
    role = Mock()
    role.name = name
    role.id = role_id
    role.pure_defined = pure_defined
    return role


def _rule(role_name="backup-operator", role_id="role-id-1"):
    """A policy rule as GET management-access-policies/rules returns it."""
    rule = Mock()
    rule.name = "tenant-a-ops.1"
    rule.role = Mock()
    rule.role.name = role_name
    rule.role.id = role_id
    return rule


def _module(check_mode=False, **overrides):
    module = Mock()
    module.params = _base_params(**overrides)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _run(func, *args):
    try:
        func(*args)
    except SystemExit:
        pass


class TestPurefbMgmtRole:
    """Tests for purefb_mgmt_role module."""

    # ================ pure-function helpers ================

    # ---------------- _ctx ----------------

    def test_ctx_empty_when_context_unset(self):
        """Test _ctx returns {} when context is empty string"""
        mock_module = Mock()
        mock_module.params = {"context": ""}
        assert _ctx(mock_module, "2.19") == {}

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_ctx_returns_context_names_when_supported(self, mock_loose_version):
        """Test _ctx returns context_names when API supports it"""
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        mock_module = Mock()
        mock_module.params = {"context": "fleet1"}
        assert _ctx(mock_module, "2.19") == {"context_names": ["fleet1"]}

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_ctx_drops_context_when_api_too_old(self, mock_loose_version):
        """Test _ctx returns {} when API is too old, even if context is set"""
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        mock_module = Mock()
        mock_module.params = {"context": "fleet1"}
        assert _ctx(mock_module, "2.16") == {}

    # ---------------- _normalize_resource ----------------

    def test_normalize_resource_prefixes_short_name(self):
        """Test _normalize_resource prefixes a short resource name"""
        assert _normalize_resource("file-system-snapshots") == (
            RESOURCE_PREFIX + "file-system-snapshots"
        )

    def test_normalize_resource_leaves_fully_qualified_alone(self):
        """Test _normalize_resource does not double-prefix a FQ resource"""
        fq = RESOURCE_PREFIX + "file-systems"
        assert _normalize_resource(fq) == fq

    # ---------------- _normalize_actions ----------------

    def test_normalize_actions_sorts_lowercases(self):
        """Test _normalize_actions returns a sorted list of lowercased verbs"""
        mock_module = Mock()
        mock_module.fail_json = Mock(side_effect=SystemExit)
        out = _normalize_actions(mock_module, ["POST", "GET", "delete"])
        assert out == ["delete", "get", "post"]
        mock_module.fail_json.assert_not_called()

    def test_normalize_actions_rejects_duplicates(self):
        """Test _normalize_actions calls fail_json when the same verb appears twice"""
        mock_module = Mock()
        mock_module.fail_json = Mock(side_effect=SystemExit)
        try:
            _normalize_actions(mock_module, ["get", "GET"])
        except SystemExit:
            pass
        mock_module.fail_json.assert_called_once()
        assert "Duplicate action" in mock_module.fail_json.call_args[1]["msg"]

    def test_normalize_actions_rejects_all_with_specific(self):
        """Test _normalize_actions calls fail_json when 'all' is mixed with specific verbs"""
        mock_module = Mock()
        mock_module.fail_json = Mock(side_effect=SystemExit)
        try:
            _normalize_actions(mock_module, ["all", "get"])
        except SystemExit:
            pass
        mock_module.fail_json.assert_called_once()
        assert "'all' cannot be combined" in mock_module.fail_json.call_args[1]["msg"]

    def test_normalize_actions_rejects_invalid_verb(self):
        """Test _normalize_actions calls fail_json on an unrecognized verb"""
        mock_module = Mock()
        mock_module.fail_json = Mock(side_effect=SystemExit)
        try:
            _normalize_actions(mock_module, ["get", "options"])
        except SystemExit:
            pass
        mock_module.fail_json.assert_called_once()
        assert "Invalid action(s)" in mock_module.fail_json.call_args[1]["msg"]

    def test_normalize_actions_accepts_all_alone(self):
        """Test _normalize_actions accepts the sentinel 'all' on its own"""
        mock_module = Mock()
        mock_module.fail_json = Mock(side_effect=SystemExit)
        out = _normalize_actions(mock_module, ["all"])
        assert out == ["all"]
        mock_module.fail_json.assert_not_called()

    # ---------------- _validate_role_name ----------------

    def test_validate_role_name_accepts_valid(self):
        """Test _validate_role_name is a no-op on a valid name"""
        mock_module = Mock()
        mock_module.fail_json = Mock(side_effect=SystemExit)
        _validate_role_name(mock_module, "backup-operator")
        mock_module.fail_json.assert_not_called()

    def test_validate_role_name_rejects_too_long(self):
        """Test _validate_role_name fails on a >63-character name"""
        mock_module = Mock()
        mock_module.fail_json = Mock(side_effect=SystemExit)
        try:
            _validate_role_name(mock_module, "x" * 64)
        except SystemExit:
            pass
        mock_module.fail_json.assert_called_once()
        assert "63 characters" in mock_module.fail_json.call_args[1]["msg"]

    def test_validate_role_name_rejects_leading_underscore(self):
        """Test _validate_role_name fails on a name starting with '_'"""
        mock_module = Mock()
        mock_module.fail_json = Mock(side_effect=SystemExit)
        try:
            _validate_role_name(mock_module, "_reserved")
        except SystemExit:
            pass
        mock_module.fail_json.assert_called_once()
        assert "reserved" in mock_module.fail_json.call_args[1]["msg"]

    # ---------------- _get_role ----------------

    def test_get_role_returns_first_item(self):
        """Test _get_role returns the first role when present"""
        mock_module = Mock()
        mock_module.params = _base_params()

        existing = Mock()
        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        mock_blade.get_management_access_policies_roles.return_value = get_response

        assert _get_role(mock_module, mock_blade, {}) is existing
        mock_blade.get_management_access_policies_roles.assert_called_once_with(
            names=["backup-operator"]
        )

    def test_get_role_returns_none_when_empty(self):
        """Test _get_role returns None when items list is empty"""
        mock_module = Mock()
        mock_module.params = _base_params()

        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        mock_blade.get_management_access_policies_roles.return_value = get_response

        assert _get_role(mock_module, mock_blade, {}) is None

    @patch(GEM, return_value=ROLE_MISSING)
    def test_get_role_returns_none_when_array_says_missing(self, mock_gem):
        """Test _get_role returns None on the array's 400 for an unknown name"""
        mock_module = _module()

        mock_blade = Mock()
        mock_blade.get_management_access_policies_roles.return_value = _err()

        assert _get_role(mock_module, mock_blade, {}) is None
        mock_module.fail_json.assert_not_called()

    # ---------------- _get_permissions ----------------

    def test_get_permissions_returns_items(self):
        """Test _get_permissions returns permission list on 200"""
        mock_module = Mock()
        mock_module.params = _base_params()

        perm = Mock()
        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [perm]
        mock_blade.get_management_access_policies_roles_permissions.return_value = (
            get_response
        )

        assert _get_permissions(mock_module, mock_blade, {}) == [perm]
        mock_blade.get_management_access_policies_roles_permissions.assert_called_once_with(
            role_names=["backup-operator"]
        )

    def test_get_permissions_fails_on_error(self):
        """Test _get_permissions calls fail_json on non-200"""
        mock_module = Mock()
        mock_module.params = _base_params()
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        get_response = Mock()
        get_response.status_code = 400
        get_response.items = []
        mock_blade.get_management_access_policies_roles_permissions.return_value = (
            get_response
        )

        try:
            _get_permissions(mock_module, mock_blade, {})
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert (
            "Failed to list permissions for role"
            in mock_module.fail_json.call_args[1]["msg"]
        )

    # ---------------- _role_referenced_by_rule ----------------

    def test_role_referenced_by_rule_true_when_match(self):
        """Test _role_referenced_by_rule returns True when a rule grants the role"""
        mock_blade = Mock()
        mock_blade.get_management_access_policies_rules.return_value = _ok([_rule()])

        assert _role_referenced_by_rule(_module(), mock_blade, _role_obj(), {}) is True

    def test_role_referenced_by_rule_false_when_no_match(self):
        """Test _role_referenced_by_rule returns False when no rule references the role"""
        mock_blade = Mock()
        mock_blade.get_management_access_policies_rules.return_value = _ok(
            [_rule(role_name="some-other-role", role_id="role-id-2")]
        )

        assert _role_referenced_by_rule(_module(), mock_blade, _role_obj(), {}) is False

    @patch(GEM, return_value=REFUSED)
    def test_role_referenced_by_rule_fails_on_error(self, mock_gem):
        """Test _role_referenced_by_rule fails when the rules cannot be listed"""
        mock_module = _module()
        mock_blade = Mock()
        mock_blade.get_management_access_policies_rules.return_value = _err()

        _run(_role_referenced_by_rule, mock_module, mock_blade, _role_obj(), {})

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "Failed to list management access policy rules" in msg
        assert "role backup-operator" in msg
        assert msg.endswith("Error: Operation not permitted.")

    # ================ _delete_role ================

    def test_delete_role_refuses_builtin(self):
        """Test _delete_role fails when the role is pure_defined"""
        mock_module = Mock()
        mock_module.params = _base_params()
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.exit_json = Mock(side_effect=SystemExit)

        existing = Mock()
        existing.pure_defined = True

        mock_blade = Mock()

        try:
            _delete_role(mock_module, mock_blade, {}, existing)
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert (
            "Built-in role backup-operator cannot be deleted"
            in mock_module.fail_json.call_args[1]["msg"]
        )
        mock_blade.delete_management_access_policies_roles.assert_not_called()

    def test_delete_role_refuses_when_referenced_by_rule(self):
        """Test _delete_role fails when a policy rule still references the role"""
        mock_module = Mock()
        mock_module.params = _base_params()
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.exit_json = Mock(side_effect=SystemExit)

        existing = _role_obj()

        mock_blade = Mock()
        mock_blade.get_management_access_policies_rules.return_value = _ok([_rule()])

        try:
            _delete_role(mock_module, mock_blade, {}, existing)
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "is referenced by one or more policy rules" in msg
        assert "purefb_mgmt_policy" in msg
        mock_blade.delete_management_access_policies_roles.assert_not_called()

    def test_delete_role_success(self):
        """Test _delete_role DELETEs when not built-in and not referenced"""
        mock_module = Mock()
        mock_module.params = _base_params()
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.exit_json = Mock(side_effect=SystemExit)

        existing = Mock()
        existing.pure_defined = False

        rules_res = Mock()
        rules_res.status_code = 200
        rules_res.items = []

        mock_blade = Mock()
        mock_blade.get_management_access_policies_rules.return_value = rules_res
        delete_res = Mock()
        delete_res.status_code = 200
        mock_blade.delete_management_access_policies_roles.return_value = delete_res

        try:
            _delete_role(mock_module, mock_blade, {}, existing)
        except SystemExit:
            pass

        mock_blade.delete_management_access_policies_roles.assert_called_once_with(
            names=["backup-operator"]
        )
        assert mock_module.exit_json.call_args[1]["changed"] is True

    def test_delete_role_check_mode_skips_delete(self):
        """Test _delete_role reports changed but skips DELETE in check mode"""
        mock_module = Mock()
        mock_module.params = _base_params()
        mock_module.check_mode = True
        mock_module.exit_json = Mock(side_effect=SystemExit)

        existing = Mock()
        existing.pure_defined = False

        rules_res = Mock()
        rules_res.status_code = 200
        rules_res.items = []

        mock_blade = Mock()
        mock_blade.get_management_access_policies_rules.return_value = rules_res

        try:
            _delete_role(mock_module, mock_blade, {}, existing)
        except SystemExit:
            pass

        mock_blade.delete_management_access_policies_roles.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    # ================ _create_role ================

    @patch("plugins.modules.purefb_mgmt_role.ManagementAccessPolicyRolePost")
    def test_create_role_without_description(self, mock_post_cls):
        """Test _create_role omits description from POST body when not provided"""
        mock_module = Mock()
        mock_module.params = _base_params(description=None)
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.exit_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        post_res = Mock()
        post_res.status_code = 200
        mock_blade.post_management_access_policies_roles.return_value = post_res

        try:
            _create_role(mock_module, mock_blade, {})
        except SystemExit:
            pass

        mock_post_cls.assert_called_once_with()
        mock_blade.post_management_access_policies_roles.assert_called_once()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_mgmt_role.ManagementAccessPolicyRolePost")
    def test_create_role_with_description(self, mock_post_cls):
        """Test _create_role passes description when the caller provides one"""
        mock_module = Mock()
        mock_module.params = _base_params(description="Does snapshot restore")
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.exit_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        post_res = Mock()
        post_res.status_code = 200
        mock_blade.post_management_access_policies_roles.return_value = post_res

        try:
            _create_role(mock_module, mock_blade, {})
        except SystemExit:
            pass

        mock_post_cls.assert_called_once_with(description="Does snapshot restore")

    def test_create_role_check_mode_skips_post(self):
        """Test _create_role reports changed but skips POST in check mode"""
        mock_module = Mock()
        mock_module.params = _base_params()
        mock_module.check_mode = True
        mock_module.exit_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()

        try:
            _create_role(mock_module, mock_blade, {})
        except SystemExit:
            pass

        mock_blade.post_management_access_policies_roles.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_mgmt_role.ManagementAccessPolicyRolePermissionPost")
    @patch("plugins.modules.purefb_mgmt_role.ManagementAccessPolicyRolePost")
    def test_create_role_posts_permissions(self, mock_post_cls, mock_perm_post_cls):
        """Test _create_role POSTs one permission per entry after the role is created"""
        mock_module = Mock()
        mock_module.params = _base_params(
            permissions=[
                {
                    "resource": "file-system-snapshots",
                    "actions": ["get", "post"],
                },
                {
                    "resource": "file-systems",
                    "actions": ["get"],
                },
            ]
        )
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.exit_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        ok = Mock()
        ok.status_code = 200
        mock_blade.post_management_access_policies_roles.return_value = ok
        mock_blade.post_management_access_policies_roles_permissions.return_value = ok

        try:
            _create_role(mock_module, mock_blade, {})
        except SystemExit:
            pass

        assert (
            mock_blade.post_management_access_policies_roles_permissions.call_count == 2
        )
        assert mock_perm_post_cls.call_count == 2
        # The resource passed to the SDK must be fully-qualified.
        for call in mock_perm_post_cls.call_args_list:
            assert call[1]["resource"].startswith(RESOURCE_PREFIX)
        assert mock_module.exit_json.call_args[1]["changed"] is True

    def test_create_role_validates_permissions_before_post(self):
        """Test _create_role rejects invalid permissions before creating the role"""
        mock_module = Mock()
        mock_module.params = _base_params(
            permissions=[
                {"resource": "file-systems", "actions": ["all", "get"]},
            ]
        )
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.exit_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()

        try:
            _create_role(mock_module, mock_blade, {})
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        # A rejected create must be side-effect free on the array.
        mock_blade.post_management_access_policies_roles.assert_not_called()
        mock_blade.post_management_access_policies_roles_permissions.assert_not_called()

    @patch("plugins.modules.purefb_mgmt_role.ManagementAccessPolicyRolePost")
    def test_create_role_failure_calls_fail_json(self, mock_post_cls):
        """Test _create_role surfaces backend errors via fail_json"""
        mock_module = Mock()
        mock_module.params = _base_params()
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.exit_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        post_res = Mock()
        post_res.status_code = 400
        post_res.errors = []
        mock_blade.post_management_access_policies_roles.return_value = post_res

        try:
            _create_role(mock_module, mock_blade, {})
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert "Failed to create role" in mock_module.fail_json.call_args[1]["msg"]

    # ================ _reconcile_permissions ================

    def test_reconcile_none_returns_false(self):
        """Test _reconcile_permissions returns False (untouched) when permissions is None"""
        mock_module = Mock()
        mock_module.params = _base_params(permissions=None)
        mock_module.check_mode = False

        mock_blade = Mock()
        assert _reconcile_permissions(mock_module, mock_blade, {}) is False
        mock_blade.get_management_access_policies_roles_permissions.assert_not_called()

    def test_reconcile_rejects_duplicate_resource(self):
        """Test _reconcile_permissions fails when the input has duplicate resources"""
        mock_module = Mock()
        mock_module.params = _base_params(
            permissions=[
                {"resource": "file-systems", "actions": ["get"]},
                {"resource": "file-systems", "actions": ["get"]},
            ]
        )
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()

        try:
            _reconcile_permissions(mock_module, mock_blade, {})
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert "Duplicate resource" in mock_module.fail_json.call_args[1]["msg"]

    @patch("plugins.modules.purefb_mgmt_role.ManagementAccessPolicyRolePermissionPost")
    def test_reconcile_adds_missing_permission(self, mock_perm_post_cls):
        """Test _reconcile_permissions POSTs permissions that are absent on the blade"""
        mock_module = Mock()
        mock_module.params = _base_params(
            permissions=[{"resource": "file-systems", "actions": ["get"]}]
        )
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        get_res = Mock()
        get_res.status_code = 200
        get_res.items = []
        mock_blade.get_management_access_policies_roles_permissions.return_value = (
            get_res
        )

        post_res = Mock()
        post_res.status_code = 200
        mock_blade.post_management_access_policies_roles_permissions.return_value = (
            post_res
        )

        changed = _reconcile_permissions(mock_module, mock_blade, {})

        assert changed is True
        mock_blade.post_management_access_policies_roles_permissions.assert_called_once()
        mock_blade.delete_management_access_policies_roles_permissions.assert_not_called()
        mock_blade.patch_management_access_policies_roles_permissions.assert_not_called()

    def test_reconcile_removes_orphan_permission(self):
        """Test _reconcile_permissions DELETEs permissions not in desired"""
        mock_module = Mock()
        mock_module.params = _base_params(
            permissions=[
                {"resource": "file-systems", "actions": ["get"]},
            ]
        )
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        keep = Mock()
        keep.name = "perm-keep"
        keep.resource = RESOURCE_PREFIX + "file-systems"
        keep.actions = ["get"]

        drop = Mock()
        drop.name = "perm-drop"
        drop.resource = RESOURCE_PREFIX + "orphan-resource"
        drop.actions = ["get"]

        mock_blade = Mock()
        get_res = Mock()
        get_res.status_code = 200
        get_res.items = [keep, drop]
        mock_blade.get_management_access_policies_roles_permissions.return_value = (
            get_res
        )

        del_res = Mock()
        del_res.status_code = 200
        mock_blade.delete_management_access_policies_roles_permissions.return_value = (
            del_res
        )

        changed = _reconcile_permissions(mock_module, mock_blade, {})

        assert changed is True
        mock_blade.delete_management_access_policies_roles_permissions.assert_called_once()
        call_kwargs = (
            mock_blade.delete_management_access_policies_roles_permissions.call_args[1]
        )
        assert call_kwargs["names"] == ["perm-drop"]
        # Permission names are globally unique; the delete endpoint takes
        # no role_names parameter (SDK rejects it).
        assert "role_names" not in call_kwargs

    @patch("plugins.modules.purefb_mgmt_role.ManagementAccessPolicyRolePermissionPatch")
    def test_reconcile_patches_changed_actions(self, mock_patch_cls):
        """Test _reconcile_permissions PATCHes when actions differ on the same resource"""
        mock_module = Mock()
        mock_module.params = _base_params(
            permissions=[
                {"resource": "file-systems", "actions": ["get", "post"]},
            ]
        )
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        current = Mock()
        current.name = "perm-fs"
        current.resource = RESOURCE_PREFIX + "file-systems"
        current.actions = ["get"]

        mock_blade = Mock()
        get_res = Mock()
        get_res.status_code = 200
        get_res.items = [current]
        mock_blade.get_management_access_policies_roles_permissions.return_value = (
            get_res
        )

        patch_res = Mock()
        patch_res.status_code = 200
        mock_blade.patch_management_access_policies_roles_permissions.return_value = (
            patch_res
        )

        changed = _reconcile_permissions(mock_module, mock_blade, {})

        assert changed is True
        mock_blade.patch_management_access_policies_roles_permissions.assert_called_once()
        assert mock_patch_cls.call_args[1]["actions"] == ["get", "post"]

    def test_reconcile_idempotent_when_match(self):
        """Test _reconcile_permissions is a no-op when actions and resources match"""
        mock_module = Mock()
        mock_module.params = _base_params(
            permissions=[{"resource": "file-systems", "actions": ["get"]}]
        )
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        current = Mock()
        current.name = "perm-fs"
        current.resource = RESOURCE_PREFIX + "file-systems"
        current.actions = ["get"]

        mock_blade = Mock()
        get_res = Mock()
        get_res.status_code = 200
        get_res.items = [current]
        mock_blade.get_management_access_policies_roles_permissions.return_value = (
            get_res
        )

        changed = _reconcile_permissions(mock_module, mock_blade, {})

        assert changed is False
        mock_blade.post_management_access_policies_roles_permissions.assert_not_called()
        mock_blade.delete_management_access_policies_roles_permissions.assert_not_called()
        mock_blade.patch_management_access_policies_roles_permissions.assert_not_called()

    def test_reconcile_short_and_fq_resource_are_equivalent(self):
        """Test _reconcile_permissions treats short and fully-qualified resource names as identical"""
        mock_module = Mock()
        mock_module.params = _base_params(
            # Short form on input
            permissions=[{"resource": "file-systems", "actions": ["get"]}]
        )
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        # Fully-qualified on the blade
        current = Mock()
        current.name = "perm-fs"
        current.resource = RESOURCE_PREFIX + "file-systems"
        current.actions = ["get"]

        mock_blade = Mock()
        get_res = Mock()
        get_res.status_code = 200
        get_res.items = [current]
        mock_blade.get_management_access_policies_roles_permissions.return_value = (
            get_res
        )

        changed = _reconcile_permissions(mock_module, mock_blade, {})
        assert changed is False

    def test_reconcile_check_mode_skips_writes(self):
        """Test _reconcile_permissions reports changed but skips writes in check mode"""
        mock_module = Mock()
        mock_module.params = _base_params(
            permissions=[{"resource": "file-systems", "actions": ["get"]}]
        )
        mock_module.check_mode = True
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        get_res = Mock()
        get_res.status_code = 200
        get_res.items = []
        mock_blade.get_management_access_policies_roles_permissions.return_value = (
            get_res
        )

        changed = _reconcile_permissions(mock_module, mock_blade, {})

        assert changed is True
        mock_blade.post_management_access_policies_roles_permissions.assert_not_called()

    def test_reconcile_empty_desired_removes_all(self):
        """Test _reconcile_permissions with permissions=[] removes every current permission"""
        mock_module = Mock()
        mock_module.params = _base_params(permissions=[])
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        current = Mock()
        current.name = "perm-fs"
        current.resource = RESOURCE_PREFIX + "file-systems"
        current.actions = ["get"]

        mock_blade = Mock()
        get_res = Mock()
        get_res.status_code = 200
        get_res.items = [current]
        mock_blade.get_management_access_policies_roles_permissions.return_value = (
            get_res
        )

        del_res = Mock()
        del_res.status_code = 200
        mock_blade.delete_management_access_policies_roles_permissions.return_value = (
            del_res
        )

        changed = _reconcile_permissions(mock_module, mock_blade, {})
        assert changed is True
        mock_blade.delete_management_access_policies_roles_permissions.assert_called_once()

    # ===== attachment helpers: _current_attached_policy_names / _subject_exists =====

    def test_current_attached_admin_returns_policy_names(self):
        """Test _current_attached_policy_names collects attached policy names for admin kind"""
        mock_module = Mock()
        mock_module.params = _base_params(
            object="admin_attach", admin="pureuser", policies=["p1"]
        )
        mock_module.fail_json = Mock(side_effect=SystemExit)

        m1 = Mock()
        m1.policy = Mock()
        m1.policy.name = "p1"
        m2 = Mock()
        m2.policy = Mock()
        m2.policy.name = "p2"

        mock_blade = Mock()
        res = Mock()
        res.status_code = 200
        res.items = [m1, m2]
        mock_blade.get_management_access_policies_admins.return_value = res

        out = _current_attached_policy_names(mock_module, mock_blade, "admin", {})
        assert out == {"p1", "p2"}
        mock_blade.get_management_access_policies_admins.assert_called_once_with(
            member_names=["pureuser"]
        )

    def test_current_attached_ds_returns_policy_names(self):
        """Test _current_attached_policy_names uses the DS endpoint for ds_role kind"""
        mock_module = Mock()
        mock_module.params = _base_params(
            object="ds_attach", ds_role="tenant-a-admins", policies=["p1"]
        )
        mock_module.fail_json = Mock(side_effect=SystemExit)

        m1 = Mock()
        m1.policy = Mock()
        m1.policy.name = "p1"

        mock_blade = Mock()
        res = Mock()
        res.status_code = 200
        res.items = [m1]
        mock_blade.get_management_access_policies_directory_services_roles.return_value = (
            res
        )

        out = _current_attached_policy_names(mock_module, mock_blade, "ds_role", {})
        assert out == {"p1"}
        mock_blade.get_management_access_policies_directory_services_roles.assert_called_once_with(
            member_names=["tenant-a-admins"]
        )

    def test_current_attached_fails_on_error(self):
        """Test _current_attached_policy_names fails on non-200 status"""
        mock_module = Mock()
        mock_module.params = _base_params(
            object="admin_attach", admin="pureuser", policies=["p1"]
        )
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        res = Mock()
        res.status_code = 400
        res.items = []
        mock_blade.get_management_access_policies_admins.return_value = res

        try:
            _current_attached_policy_names(mock_module, mock_blade, "admin", {})
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()

    def test_subject_exists_true_for_admin(self):
        """Test _subject_exists returns True when the admin exists"""
        mock_module = Mock()
        mock_module.params = _base_params(
            object="admin_attach", admin="pureuser", policies=["p1"]
        )

        mock_blade = Mock()
        res = Mock()
        res.status_code = 200
        res.items = [Mock()]
        mock_blade.get_admins.return_value = res

        assert _subject_exists(mock_module, mock_blade, "admin", {}) is True
        mock_blade.get_admins.assert_called_once_with(names=["pureuser"])
        mock_blade.get_directory_services_roles.assert_not_called()

    def test_subject_exists_true_for_ds_role(self):
        """Test _subject_exists returns True when the DS role mapping exists"""
        mock_module = Mock()
        mock_module.params = _base_params(
            object="ds_attach", ds_role="tenant-a-admins", policies=["p1"]
        )

        mock_blade = Mock()
        res = Mock()
        res.status_code = 200
        res.items = [Mock()]
        mock_blade.get_directory_services_roles.return_value = res

        assert _subject_exists(mock_module, mock_blade, "ds_role", {}) is True
        mock_blade.get_directory_services_roles.assert_called_once_with(
            names=["tenant-a-admins"]
        )
        mock_blade.get_admins.assert_not_called()

    def test_subject_exists_false_when_missing(self):
        """Test _subject_exists returns False when the admin is not found"""
        mock_module = Mock()
        mock_module.params = _base_params(
            object="admin_attach", admin="ghost", policies=["p1"]
        )

        mock_blade = Mock()
        res = Mock()
        res.status_code = 200
        res.items = []
        mock_blade.get_admins.return_value = res

        assert _subject_exists(mock_module, mock_blade, "admin", {}) is False

    @patch(GEM, return_value=ADMIN_MISSING)
    def test_subject_exists_false_when_array_says_missing(self, mock_gem):
        """Test _subject_exists returns False on the array's 400 for an unknown admin"""
        mock_module = _module(object="admin_attach", admin="ghost", policies=["p1"])

        mock_blade = Mock()
        mock_blade.get_admins.return_value = _err()

        assert _subject_exists(mock_module, mock_blade, "admin", {}) is False
        mock_module.fail_json.assert_not_called()

    # ================ _handle_role dispatcher ================

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_role_fails_when_api_too_old(self, mock_loose_version):
        """Test _handle_role fails when the API is too old for custom roles"""
        # role gate: LooseVersion(MIN_ROLE_API_VERSION) > LooseVersion(api_version) → True
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)

        mock_module = Mock()
        mock_module.params = _base_params()
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        try:
            _handle_role(mock_module, mock_blade, "2.19", {})
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "does not support custom roles and permissions" in msg
        assert "2.26+" in msg

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_role_absent_noop_when_missing(self, mock_loose_version):
        """Test _handle_role state=absent is a no-op when the role doesn't exist"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(state="absent")
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        get_res = Mock()
        get_res.status_code = 200
        get_res.items = []
        mock_blade.get_management_access_policies_roles.return_value = get_res

        try:
            _handle_role(mock_module, mock_blade, "2.26", {})
        except SystemExit:
            pass

        assert mock_module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_role_reconciles_permissions_on_existing(self, mock_loose_version):
        """Test _handle_role reconciles permissions when the role already exists"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(permissions=None)
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        existing = Mock()

        mock_blade = Mock()
        get_res = Mock()
        get_res.status_code = 200
        get_res.items = [existing]
        mock_blade.get_management_access_policies_roles.return_value = get_res

        try:
            _handle_role(mock_module, mock_blade, "2.26", {})
        except SystemExit:
            pass

        # permissions=None → no reconcile activity, changed=False
        assert mock_module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_role_refuses_builtin_permissions_rewrite(self, mock_loose_version):
        """Test _handle_role fails fast when permissions target a built-in role"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(name="viewer", permissions=[])
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        existing = Mock()
        existing.pure_defined = True

        mock_blade = Mock()
        get_res = Mock()
        get_res.status_code = 200
        get_res.items = [existing]
        mock_blade.get_management_access_policies_roles.return_value = get_res

        try:
            _handle_role(mock_module, mock_blade, "2.26", {})
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert (
            "Built-in role viewer cannot be modified"
            in mock_module.fail_json.call_args[1]["msg"]
        )
        # The guard must fire before any reconcile read or write.
        mock_blade.get_management_access_policies_roles_permissions.assert_not_called()

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_role_builtin_existence_check_is_noop(self, mock_loose_version):
        """Test _handle_role without permissions is a changed=False no-op on a built-in role"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(name="viewer", permissions=None)
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        existing = Mock()
        existing.pure_defined = True

        mock_blade = Mock()
        get_res = Mock()
        get_res.status_code = 200
        get_res.items = [existing]
        mock_blade.get_management_access_policies_roles.return_value = get_res

        try:
            _handle_role(mock_module, mock_blade, "2.26", {})
        except SystemExit:
            pass

        mock_module.fail_json.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_role_builtin_guard_ignores_custom_roles(self, mock_loose_version):
        """Test the built-in guard lets permissions reconcile proceed on a custom role"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(name="backup-operator", permissions=[])
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        existing = Mock()
        existing.pure_defined = False

        perm = Mock()
        perm.name = "backup-operator.1"
        perm.resource = RESOURCE_PREFIX + "file-systems"
        perm.actions = ["get"]

        mock_blade = Mock()
        get_role_res = Mock()
        get_role_res.status_code = 200
        get_role_res.items = [existing]
        mock_blade.get_management_access_policies_roles.return_value = get_role_res

        get_perm_res = Mock()
        get_perm_res.status_code = 200
        get_perm_res.items = [perm]
        mock_blade.get_management_access_policies_roles_permissions.return_value = (
            get_perm_res
        )

        del_res = Mock()
        del_res.status_code = 200
        mock_blade.delete_management_access_policies_roles_permissions.return_value = (
            del_res
        )

        try:
            _handle_role(mock_module, mock_blade, "2.26", {})
        except SystemExit:
            pass

        mock_module.fail_json.assert_not_called()
        mock_blade.delete_management_access_policies_roles_permissions.assert_called_once()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    # ================ _handle_attach ================

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_attach_fails_when_api_too_old(self, mock_loose_version):
        """Test _handle_attach fails when the API is older than the attach version"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)

        mock_module = Mock()
        mock_module.params = _base_params(
            object="admin_attach", admin="pureuser", policies=["p1"]
        )
        mock_module.check_mode = False
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        try:
            _handle_attach(mock_module, mock_blade, "2.18", {}, "admin")
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "does not support management access policy attachment" in msg
        assert "2.19+" in msg

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_attach_present_fails_when_subject_missing(self, mock_loose_version):
        """Test _handle_attach state=present fails when the admin does not exist"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(
            object="admin_attach",
            state="present",
            admin="ghost",
            policies=["p1"],
        )
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        admins_res = Mock()
        admins_res.status_code = 200
        admins_res.items = []
        mock_blade.get_admins.return_value = admins_res

        try:
            _handle_attach(mock_module, mock_blade, "2.26", {}, "admin")
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert "admin ghost does not exist" in mock_module.fail_json.call_args[1]["msg"]

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_attach_absent_noop_when_subject_missing(self, mock_loose_version):
        """Test _handle_attach state=absent is an idempotent no-op on a missing admin"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(
            object="admin_attach",
            state="absent",
            admin="ghost",
            policies=["p1"],
        )
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        admins_res = Mock()
        admins_res.status_code = 200
        admins_res.items = []
        mock_blade.get_admins.return_value = admins_res

        try:
            _handle_attach(mock_module, mock_blade, "2.26", {}, "admin")
        except SystemExit:
            pass

        mock_module.fail_json.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is False
        # Nothing can be attached to a missing subject — no policy calls.
        mock_blade.get_management_access_policies_admins.assert_not_called()
        mock_blade.delete_management_access_policies_admins.assert_not_called()

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_attach_present_case_variant_is_noop(self, mock_loose_version):
        """Test _handle_attach state=present matches attached policies case-insensitively"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(
            object="admin_attach",
            state="present",
            admin="pureuser",
            policies=["TENANT-A-OPS"],
        )
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()

        admins_res = Mock()
        admins_res.status_code = 200
        admins_res.items = [Mock()]
        mock_blade.get_admins.return_value = admins_res

        existing = Mock()
        existing.policy = Mock()
        existing.policy.name = "Tenant-A-Ops"
        current_res = Mock()
        current_res.status_code = 200
        current_res.items = [existing]
        mock_blade.get_management_access_policies_admins.return_value = current_res

        try:
            _handle_attach(mock_module, mock_blade, "2.26", {}, "admin")
        except SystemExit:
            pass

        mock_blade.post_management_access_policies_admins.assert_not_called()
        mock_blade.delete_management_access_policies_admins.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_attach_absent_case_variant_detaches_canonical(
        self, mock_loose_version
    ):
        """Test _handle_attach state=absent detaches a case variant using the array's spelling"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(
            object="admin_attach",
            state="absent",
            admin="pureuser",
            policies=["TENANT-A-OPS"],
        )
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()

        admins_res = Mock()
        admins_res.status_code = 200
        admins_res.items = [Mock()]
        mock_blade.get_admins.return_value = admins_res

        existing = Mock()
        existing.policy = Mock()
        existing.policy.name = "Tenant-A-Ops"
        current_res = Mock()
        current_res.status_code = 200
        current_res.items = [existing]
        mock_blade.get_management_access_policies_admins.return_value = current_res

        ok = Mock()
        ok.status_code = 200
        mock_blade.delete_management_access_policies_admins.return_value = ok

        try:
            _handle_attach(mock_module, mock_blade, "2.26", {}, "admin")
        except SystemExit:
            pass

        mock_blade.delete_management_access_policies_admins.assert_called_once_with(
            member_names=["pureuser"], policy_names=["Tenant-A-Ops"]
        )
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_attach_dedupes_case_variant_requests(self, mock_loose_version):
        """Test _handle_attach collapses case-variant duplicates in the policies list"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(
            object="admin_attach",
            state="present",
            admin="pureuser",
            policies=["p1", "P1"],
        )
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()

        admins_res = Mock()
        admins_res.status_code = 200
        admins_res.items = [Mock()]
        mock_blade.get_admins.return_value = admins_res

        current_res = Mock()
        current_res.status_code = 200
        current_res.items = []
        mock_blade.get_management_access_policies_admins.return_value = current_res

        ok = Mock()
        ok.status_code = 200
        mock_blade.post_management_access_policies_admins.return_value = ok

        try:
            _handle_attach(mock_module, mock_blade, "2.26", {}, "admin")
        except SystemExit:
            pass

        # One POST with a single spelling (first occurrence wins).
        mock_blade.post_management_access_policies_admins.assert_called_once_with(
            member_names=["pureuser"], policy_names=["p1"]
        )
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_attach_present_fails_when_ds_role_missing(self, mock_loose_version):
        """Test _handle_attach state=present fails when the DS role mapping does not exist"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(
            object="ds_attach",
            state="present",
            ds_role="ghost-mapping",
            policies=["p1"],
        )
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        ds_res = Mock()
        ds_res.status_code = 200
        ds_res.items = []
        mock_blade.get_directory_services_roles.return_value = ds_res

        try:
            _handle_attach(mock_module, mock_blade, "2.26", {}, "ds_role")
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        assert (
            "ds_role ghost-mapping does not exist"
            in mock_module.fail_json.call_args[1]["msg"]
        )

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_attach_absent_noop_when_ds_role_missing(self, mock_loose_version):
        """Test _handle_attach state=absent is an idempotent no-op on a missing DS role"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(
            object="ds_attach",
            state="absent",
            ds_role="ghost-mapping",
            policies=["p1"],
        )
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()
        ds_res = Mock()
        ds_res.status_code = 200
        ds_res.items = []
        mock_blade.get_directory_services_roles.return_value = ds_res

        try:
            _handle_attach(mock_module, mock_blade, "2.26", {}, "ds_role")
        except SystemExit:
            pass

        mock_module.fail_json.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is False
        mock_blade.get_management_access_policies_directory_services_roles.assert_not_called()
        mock_blade.delete_management_access_policies_directory_services_roles.assert_not_called()

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_attach_check_mode_case_variant_is_noop(self, mock_loose_version):
        """Test check_mode reports changed=False when the request is already satisfied case-insensitively"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(
            object="admin_attach",
            state="present",
            admin="pureuser",
            policies=["TENANT-A-OPS"],
        )
        mock_module.check_mode = True
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()

        admins_res = Mock()
        admins_res.status_code = 200
        admins_res.items = [Mock()]
        mock_blade.get_admins.return_value = admins_res

        existing = Mock()
        existing.policy = Mock()
        existing.policy.name = "Tenant-A-Ops"
        current_res = Mock()
        current_res.status_code = 200
        current_res.items = [existing]
        mock_blade.get_management_access_policies_admins.return_value = current_res

        try:
            _handle_attach(mock_module, mock_blade, "2.26", {}, "admin")
        except SystemExit:
            pass

        # The empty-diff exit must win over the check_mode changed=True exit.
        assert mock_module.exit_json.call_args[1]["changed"] is False
        mock_blade.post_management_access_policies_admins.assert_not_called()

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_attach_mixed_list_posts_only_new_with_user_spelling(
        self, mock_loose_version
    ):
        """Test a case-variant match is excluded from the POST while a new policy keeps the user's spelling"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(
            object="admin_attach",
            state="present",
            admin="pureuser",
            policies=["TENANT-A-OPS", "New-Pol"],
        )
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()

        admins_res = Mock()
        admins_res.status_code = 200
        admins_res.items = [Mock()]
        mock_blade.get_admins.return_value = admins_res

        existing = Mock()
        existing.policy = Mock()
        existing.policy.name = "Tenant-A-Ops"
        current_res = Mock()
        current_res.status_code = 200
        current_res.items = [existing]
        mock_blade.get_management_access_policies_admins.return_value = current_res

        ok = Mock()
        ok.status_code = 200
        mock_blade.post_management_access_policies_admins.return_value = ok

        try:
            _handle_attach(mock_module, mock_blade, "2.26", {}, "admin")
        except SystemExit:
            pass

        # Only the genuinely new policy, in the user's spelling — neither the
        # matched variant nor any lowercased key may leak into the POST.
        mock_blade.post_management_access_policies_admins.assert_called_once_with(
            member_names=["pureuser"], policy_names=["New-Pol"]
        )
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_attach_ds_absent_detaches_canonical(self, mock_loose_version):
        """Test ds_attach state=absent detaches via the DS endpoint using the array's spelling"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(
            object="ds_attach",
            state="absent",
            ds_role="tenant-a-admins",
            policies=["TENANT-A-OPS"],
        )
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()

        ds_res = Mock()
        ds_res.status_code = 200
        ds_res.items = [Mock()]
        mock_blade.get_directory_services_roles.return_value = ds_res

        existing = Mock()
        existing.policy = Mock()
        existing.policy.name = "Tenant-A-Ops"
        current_res = Mock()
        current_res.status_code = 200
        current_res.items = [existing]
        mock_blade.get_management_access_policies_directory_services_roles.return_value = (
            current_res
        )

        ok = Mock()
        ok.status_code = 200
        mock_blade.delete_management_access_policies_directory_services_roles.return_value = (
            ok
        )

        try:
            _handle_attach(mock_module, mock_blade, "2.26", {}, "ds_role")
        except SystemExit:
            pass

        mock_blade.delete_management_access_policies_directory_services_roles.assert_called_once_with(
            member_names=["tenant-a-admins"], policy_names=["Tenant-A-Ops"]
        )
        mock_blade.post_management_access_policies_directory_services_roles.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_attach_post_failure_calls_fail_json(self, mock_loose_version):
        """Test a non-200 attach POST surfaces as 'Failed to attach policies'"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(
            object="admin_attach",
            state="present",
            admin="pureuser",
            policies=["p1"],
        )
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()

        admins_res = Mock()
        admins_res.status_code = 200
        admins_res.items = [Mock()]
        mock_blade.get_admins.return_value = admins_res

        current_res = Mock()
        current_res.status_code = 200
        current_res.items = []
        mock_blade.get_management_access_policies_admins.return_value = current_res

        bad = Mock()
        bad.status_code = 400
        bad.errors = []
        mock_blade.post_management_access_policies_admins.return_value = bad

        try:
            _handle_attach(mock_module, mock_blade, "2.26", {}, "admin")
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "Failed to attach policies" in msg
        assert "['p1']" in msg
        assert "admin pureuser" in msg

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_attach_delete_failure_calls_fail_json(self, mock_loose_version):
        """Test a non-200 detach DELETE surfaces as 'Failed to detach policies'"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(
            object="admin_attach",
            state="absent",
            admin="pureuser",
            policies=["p1"],
        )
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()

        admins_res = Mock()
        admins_res.status_code = 200
        admins_res.items = [Mock()]
        mock_blade.get_admins.return_value = admins_res

        existing = Mock()
        existing.policy = Mock()
        existing.policy.name = "p1"
        current_res = Mock()
        current_res.status_code = 200
        current_res.items = [existing]
        mock_blade.get_management_access_policies_admins.return_value = current_res

        bad = Mock()
        bad.status_code = 400
        bad.errors = []
        mock_blade.delete_management_access_policies_admins.return_value = bad

        try:
            _handle_attach(mock_module, mock_blade, "2.26", {}, "admin")
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "Failed to detach policies" in msg
        assert "['p1']" in msg
        assert "admin pureuser" in msg

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_attach_attaches_new_policy(self, mock_loose_version):
        """Test _handle_attach POSTs the diff of desired-vs-current when state=present"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(
            object="admin_attach",
            state="present",
            admin="pureuser",
            policies=["p1", "p2"],
        )
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()

        admins_res = Mock()
        admins_res.status_code = 200
        admins_res.items = [Mock()]
        mock_blade.get_admins.return_value = admins_res

        # p1 already attached; p2 not attached → we should only add p2
        existing = Mock()
        existing.policy = Mock()
        existing.policy.name = "p1"
        current_res = Mock()
        current_res.status_code = 200
        current_res.items = [existing]
        mock_blade.get_management_access_policies_admins.return_value = current_res

        ok = Mock()
        ok.status_code = 200
        mock_blade.post_management_access_policies_admins.return_value = ok

        try:
            _handle_attach(mock_module, mock_blade, "2.26", {}, "admin")
        except SystemExit:
            pass

        mock_blade.post_management_access_policies_admins.assert_called_once_with(
            member_names=["pureuser"], policy_names=["p2"]
        )
        mock_blade.delete_management_access_policies_admins.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_attach_present_noop_when_all_attached(self, mock_loose_version):
        """Test _handle_attach state=present is a no-op when everything requested is already attached"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(
            object="admin_attach",
            state="present",
            admin="pureuser",
            policies=["p1"],
        )
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()

        admins_res = Mock()
        admins_res.status_code = 200
        admins_res.items = [Mock()]
        mock_blade.get_admins.return_value = admins_res

        existing = Mock()
        existing.policy = Mock()
        existing.policy.name = "p1"
        current_res = Mock()
        current_res.status_code = 200
        current_res.items = [existing]
        mock_blade.get_management_access_policies_admins.return_value = current_res

        try:
            _handle_attach(mock_module, mock_blade, "2.26", {}, "admin")
        except SystemExit:
            pass

        mock_blade.post_management_access_policies_admins.assert_not_called()
        mock_blade.delete_management_access_policies_admins.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_attach_absent_detaches_intersection(self, mock_loose_version):
        """Test _handle_attach state=absent DELETEs only the intersection of requested and current"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(
            object="admin_attach",
            state="absent",
            admin="pureuser",
            policies=["p1", "p3"],
        )
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()

        admins_res = Mock()
        admins_res.status_code = 200
        admins_res.items = [Mock()]
        mock_blade.get_admins.return_value = admins_res

        # Current: p1 and p2. Requested detach: p1 and p3.
        # Only p1 should be detached.
        e1 = Mock()
        e1.policy = Mock()
        e1.policy.name = "p1"
        e2 = Mock()
        e2.policy = Mock()
        e2.policy.name = "p2"
        current_res = Mock()
        current_res.status_code = 200
        current_res.items = [e1, e2]
        mock_blade.get_management_access_policies_admins.return_value = current_res

        ok = Mock()
        ok.status_code = 200
        mock_blade.delete_management_access_policies_admins.return_value = ok

        try:
            _handle_attach(mock_module, mock_blade, "2.26", {}, "admin")
        except SystemExit:
            pass

        mock_blade.delete_management_access_policies_admins.assert_called_once_with(
            member_names=["pureuser"], policy_names=["p1"]
        )
        mock_blade.post_management_access_policies_admins.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_attach_absent_noop_when_not_attached(self, mock_loose_version):
        """Test _handle_attach state=absent is a no-op when nothing requested is currently attached"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(
            object="admin_attach",
            state="absent",
            admin="pureuser",
            policies=["p1"],
        )
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()

        admins_res = Mock()
        admins_res.status_code = 200
        admins_res.items = [Mock()]
        mock_blade.get_admins.return_value = admins_res

        current_res = Mock()
        current_res.status_code = 200
        current_res.items = []
        mock_blade.get_management_access_policies_admins.return_value = current_res

        try:
            _handle_attach(mock_module, mock_blade, "2.26", {}, "admin")
        except SystemExit:
            pass

        mock_blade.post_management_access_policies_admins.assert_not_called()
        mock_blade.delete_management_access_policies_admins.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_attach_ds_role_uses_ds_endpoint(self, mock_loose_version):
        """Test _handle_attach on ds_role kind hits the DS-role endpoints"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(
            object="ds_attach",
            state="present",
            ds_role="tenant-a-admins",
            policies=["p1"],
        )
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()

        ds_res = Mock()
        ds_res.status_code = 200
        ds_res.items = [Mock()]
        mock_blade.get_directory_services_roles.return_value = ds_res

        current_res = Mock()
        current_res.status_code = 200
        current_res.items = []
        mock_blade.get_management_access_policies_directory_services_roles.return_value = (
            current_res
        )

        ok = Mock()
        ok.status_code = 200
        mock_blade.post_management_access_policies_directory_services_roles.return_value = (
            ok
        )

        try:
            _handle_attach(mock_module, mock_blade, "2.26", {}, "ds_role")
        except SystemExit:
            pass

        mock_blade.post_management_access_policies_directory_services_roles.assert_called_once_with(
            member_names=["tenant-a-admins"], policy_names=["p1"]
        )
        mock_blade.post_management_access_policies_admins.assert_not_called()

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_attach_check_mode_skips_writes(self, mock_loose_version):
        """Test _handle_attach reports changed but skips writes in check mode"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(
            object="admin_attach",
            state="present",
            admin="pureuser",
            policies=["p1"],
        )
        mock_module.check_mode = True
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()

        admins_res = Mock()
        admins_res.status_code = 200
        admins_res.items = [Mock()]
        mock_blade.get_admins.return_value = admins_res

        current_res = Mock()
        current_res.status_code = 200
        current_res.items = []
        mock_blade.get_management_access_policies_admins.return_value = current_res

        try:
            _handle_attach(mock_module, mock_blade, "2.26", {}, "admin")
        except SystemExit:
            pass

        mock_blade.post_management_access_policies_admins.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    def test_handle_attach_deduplicates_policies(self, mock_loose_version):
        """Test _handle_attach silently deduplicates a repeated policy name"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.params = _base_params(
            object="admin_attach",
            state="present",
            admin="pureuser",
            policies=["p1", "p1"],
        )
        mock_module.check_mode = False
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)

        mock_blade = Mock()

        admins_res = Mock()
        admins_res.status_code = 200
        admins_res.items = [Mock()]
        mock_blade.get_admins.return_value = admins_res

        current_res = Mock()
        current_res.status_code = 200
        current_res.items = []
        mock_blade.get_management_access_policies_admins.return_value = current_res

        ok = Mock()
        ok.status_code = 200
        mock_blade.post_management_access_policies_admins.return_value = ok

        try:
            _handle_attach(mock_module, mock_blade, "2.26", {}, "admin")
        except SystemExit:
            pass

        mock_blade.post_management_access_policies_admins.assert_called_once_with(
            member_names=["pureuser"], policy_names=["p1"]
        )

    # ================ end-to-end main() ================

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    @patch("plugins.modules.purefb_mgmt_role.ManagementAccessPolicyRolePost")
    @patch("plugins.modules.purefb_mgmt_role.get_system")
    @patch("plugins.modules.purefb_mgmt_role.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_role.HAS_PYPURECLIENT", True)
    def test_main_creates_role(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_post_cls,
        mock_loose_version,
    ):
        """Test main creates a new custom role"""
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

        # Role doesn't exist
        get_res = Mock()
        get_res.status_code = 200
        get_res.items = []
        mock_blade.get_management_access_policies_roles.return_value = get_res

        # Create succeeds
        post_res = Mock()
        post_res.status_code = 200
        mock_blade.post_management_access_policies_roles.return_value = post_res

        try:
            main()
        except SystemExit:
            pass

        mock_blade.post_management_access_policies_roles.assert_called_once()
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    @patch("plugins.modules.purefb_mgmt_role.get_system")
    @patch("plugins.modules.purefb_mgmt_role.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_role.HAS_PYPURECLIENT", True)
    def test_main_absent_role_when_missing_is_noop(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test main is a no-op when state=absent and the role doesn't exist"""
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

        get_res = Mock()
        get_res.status_code = 200
        get_res.items = []
        mock_blade.get_management_access_policies_roles.return_value = get_res

        try:
            main()
        except SystemExit:
            pass

        mock_blade.delete_management_access_policies_roles.assert_not_called()
        assert mock_module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    @patch("plugins.modules.purefb_mgmt_role.get_system")
    @patch("plugins.modules.purefb_mgmt_role.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_role.HAS_PYPURECLIENT", True)
    def test_main_deletes_existing_role(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test main deletes an existing custom role when nothing references it"""
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
        existing.pure_defined = False
        get_res = Mock()
        get_res.status_code = 200
        get_res.items = [existing]
        mock_blade.get_management_access_policies_roles.return_value = get_res

        rules_res = Mock()
        rules_res.status_code = 200
        rules_res.items = []
        mock_blade.get_management_access_policies_rules.return_value = rules_res

        delete_res = Mock()
        delete_res.status_code = 200
        mock_blade.delete_management_access_policies_roles.return_value = delete_res

        try:
            main()
        except SystemExit:
            pass

        mock_blade.delete_management_access_policies_roles.assert_called_once_with(
            names=["backup-operator"]
        )
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    @patch("plugins.modules.purefb_mgmt_role.get_system")
    @patch("plugins.modules.purefb_mgmt_role.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_role.HAS_PYPURECLIENT", True)
    def test_main_admin_attach_uses_admin_endpoint(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test main dispatches object=admin_attach to the admin endpoints"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = _base_params(
            object="admin_attach",
            state="present",
            name=None,
            admin="pureuser",
            policies=["tenant-a-ops"],
        )
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.26"]
        mock_get_system.return_value = mock_blade

        admins_res = Mock()
        admins_res.status_code = 200
        admins_res.items = [Mock()]
        mock_blade.get_admins.return_value = admins_res

        current_res = Mock()
        current_res.status_code = 200
        current_res.items = []
        mock_blade.get_management_access_policies_admins.return_value = current_res

        ok = Mock()
        ok.status_code = 200
        mock_blade.post_management_access_policies_admins.return_value = ok

        try:
            main()
        except SystemExit:
            pass

        mock_blade.post_management_access_policies_admins.assert_called_once_with(
            member_names=["pureuser"], policy_names=["tenant-a-ops"]
        )
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_mgmt_role.LooseVersion")
    @patch("plugins.modules.purefb_mgmt_role.get_system")
    @patch("plugins.modules.purefb_mgmt_role.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_role.HAS_PYPURECLIENT", True)
    def test_main_ds_attach_uses_ds_endpoint(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test main dispatches object=ds_attach to the directory-service endpoints"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = _base_params(
            object="ds_attach",
            state="present",
            name=None,
            ds_role="tenant-a-admins",
            policies=["tenant-a-ops"],
        )
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.26"]
        mock_get_system.return_value = mock_blade

        ds_res = Mock()
        ds_res.status_code = 200
        ds_res.items = [Mock()]
        mock_blade.get_directory_services_roles.return_value = ds_res

        current_res = Mock()
        current_res.status_code = 200
        current_res.items = []
        mock_blade.get_management_access_policies_directory_services_roles.return_value = (
            current_res
        )

        ok = Mock()
        ok.status_code = 200
        mock_blade.post_management_access_policies_directory_services_roles.return_value = (
            ok
        )

        try:
            main()
        except SystemExit:
            pass

        mock_blade.post_management_access_policies_directory_services_roles.assert_called_once_with(
            member_names=["tenant-a-admins"], policy_names=["tenant-a-ops"]
        )
        assert mock_module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_mgmt_role.get_system")
    @patch("plugins.modules.purefb_mgmt_role.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_role.HAS_PYPURECLIENT", False)
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


class TestPurefbMgmtRoleRefusedReads:
    """A read the array does not answer is reported, never read as absent."""

    # ---------------- _read_named ----------------

    def test_read_named_returns_items_on_200(self):
        """Test _read_named returns the items of a 200 answer"""
        mock_module = _module()
        item = Mock()
        assert _read_named(mock_module, _ok([item]), "role x") == [item]
        mock_module.fail_json.assert_not_called()

    @patch(GEM, return_value=ROLE_MISSING)
    def test_read_named_empty_when_array_says_missing(self, mock_gem):
        """Test _read_named reads only the array's does-not-exist as absent"""
        mock_module = _module()
        assert _read_named(mock_module, _err(), "role x") == []
        mock_module.fail_json.assert_not_called()

    @patch(GEM, return_value=REFUSED)
    def test_read_named_fails_on_refused_read(self, mock_gem):
        """Test _read_named fails with the array's message on a refused read"""
        mock_module = _module()
        _run(_read_named, mock_module, _err(), "role x")
        mock_module.fail_json.assert_called_once_with(
            msg="Failed to read role x. Error: Operation not permitted."
        )

    @patch(GEM, return_value="Unknown error")
    def test_read_named_fails_on_server_error(self, mock_gem):
        """Test _read_named fails on an answer that carries no usable message"""
        mock_module = _module()
        _run(_read_named, mock_module, _err(500), "admin x")
        mock_module.fail_json.assert_called_once_with(
            msg="Failed to read admin x. Error: Unknown error"
        )

    # ---------------- _get_role ----------------

    @patch(GEM, return_value=ROLE_MISSING)
    def test_get_role_realm_style_name_reads_as_missing(self, mock_gem):
        """Test a realm-style role name gets the same does-not-exist answer"""
        mock_module = _module(name="rzaudit::backup-operator")
        mock_blade = Mock()
        mock_blade.get_management_access_policies_roles.return_value = _err()

        assert _get_role(mock_module, mock_blade, {}) is None
        mock_blade.get_management_access_policies_roles.assert_called_once_with(
            names=["rzaudit::backup-operator"]
        )
        mock_module.fail_json.assert_not_called()

    @patch(GEM, return_value=REFUSED)
    def test_get_role_fails_on_refused_read(self, mock_gem):
        """Test _get_role fails when the array refuses the read"""
        mock_module = _module()
        mock_blade = Mock()
        mock_blade.get_management_access_policies_roles.return_value = _err()

        _run(_get_role, mock_module, mock_blade, {})

        mock_module.fail_json.assert_called_once_with(
            msg="Failed to read role backup-operator. Error: Operation not permitted."
        )

    @patch(GEM, return_value=REFUSED_VERB)
    def test_get_role_fails_on_refusal_naming_the_verb(self, mock_gem):
        """Test the longer refusal text of a custom role is not read as absent"""
        mock_module = _module()
        mock_blade = Mock()
        mock_blade.get_management_access_policies_roles.return_value = _err()

        _run(_get_role, mock_module, mock_blade, {})

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert msg.startswith("Failed to read role backup-operator. Error: ")
        assert msg.endswith(REFUSED_VERB)

    @patch(GEM, return_value=NOT_IN_FLEET)
    def test_get_role_fails_on_unknown_context(self, mock_gem):
        """Test a context that is not a fleet member is reported, not absent"""
        mock_module = _module(context="other-array")
        mock_blade = Mock()
        mock_blade.get_management_access_policies_roles.return_value = _err()

        _run(_get_role, mock_module, mock_blade, {"context_names": ["other-array"]})

        mock_blade.get_management_access_policies_roles.assert_called_once_with(
            names=["backup-operator"], context_names=["other-array"]
        )
        mock_module.fail_json.assert_called_once_with(
            msg="Failed to read role backup-operator. Error: Cannot find array in fleet"
        )

    # ---------------- _subject_exists ----------------

    @patch(GEM, return_value=DS_ROLE_MISSING)
    def test_subject_exists_false_when_mapping_missing(self, mock_gem):
        """Test a role mapping the array does not know reads as missing"""
        mock_module = _module(
            object="ds_attach", ds_role="tenant-a-admins", policies=["p1"]
        )
        mock_blade = Mock()
        mock_blade.get_directory_services_roles.return_value = _err()

        assert _subject_exists(mock_module, mock_blade, "ds_role", {}) is False
        mock_module.fail_json.assert_not_called()

    @patch(GEM, return_value=ADMIN_MISSING)
    def test_subject_exists_false_for_realm_style_admin(self, mock_gem):
        """Test a realm-style admin name gets the same does-not-exist answer"""
        mock_module = _module(
            object="admin_attach", admin="rzaudit::svc-automation", policies=["p1"]
        )
        mock_blade = Mock()
        mock_blade.get_admins.return_value = _err()

        assert _subject_exists(mock_module, mock_blade, "admin", {}) is False
        mock_blade.get_admins.assert_called_once_with(names=["rzaudit::svc-automation"])
        mock_module.fail_json.assert_not_called()

    @patch(GEM, return_value=REFUSED)
    def test_subject_exists_fails_on_refused_mapping_read(self, mock_gem):
        """Test a refused read of the role mapping fails the task"""
        mock_module = _module(
            object="ds_attach", ds_role="tenant-a-admins", policies=["p1"]
        )
        mock_blade = Mock()
        mock_blade.get_directory_services_roles.return_value = _err()

        _run(_subject_exists, mock_module, mock_blade, "ds_role", {})

        mock_module.fail_json.assert_called_once_with(
            msg="Failed to read ds_role tenant-a-admins. Error: Operation not permitted."
        )

    @patch(GEM, return_value=NOT_IN_FLEET)
    def test_subject_exists_fails_on_refused_admin_read(self, mock_gem):
        """Test a failed read of the admin fails the task"""
        mock_module = _module(
            object="admin_attach", admin="svc-automation", policies=["p1"]
        )
        mock_blade = Mock()
        mock_blade.get_admins.return_value = _err()

        _run(_subject_exists, mock_module, mock_blade, "admin", {})

        mock_module.fail_json.assert_called_once_with(
            msg="Failed to read admin svc-automation. Error: Cannot find array in fleet"
        )

    # ---------------- _handle_role ----------------

    @patch(GEM, return_value=REFUSED)
    @patch(LOOSE)
    def test_handle_role_present_refused_read_sends_no_create(
        self, mock_loose_version, mock_gem
    ):
        """Test an existing role the caller may not read is not created again"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module()
        mock_blade = Mock()
        mock_blade.get_management_access_policies_roles.return_value = _err()

        _run(_handle_role, mock_module, mock_blade, "2.30", {})

        mock_module.fail_json.assert_called_once_with(
            msg="Failed to read role backup-operator. Error: Operation not permitted."
        )
        mock_blade.post_management_access_policies_roles.assert_not_called()
        mock_module.exit_json.assert_not_called()

    @patch(GEM, return_value=REFUSED)
    @patch(LOOSE)
    def test_handle_role_present_refused_read_check_mode(
        self, mock_loose_version, mock_gem
    ):
        """Test check mode reports the refused read instead of a change"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(check_mode=True)
        mock_blade = Mock()
        mock_blade.get_management_access_policies_roles.return_value = _err()

        _run(_handle_role, mock_module, mock_blade, "2.30", {})

        mock_module.fail_json.assert_called_once()
        assert "Failed to read role" in mock_module.fail_json.call_args[1]["msg"]
        mock_module.exit_json.assert_not_called()

    @patch(GEM, return_value=REFUSED)
    @patch(LOOSE)
    def test_handle_role_absent_refused_read_is_not_ok(
        self, mock_loose_version, mock_gem
    ):
        """Test state=absent does not report ok when the role cannot be read"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(state="absent")
        mock_blade = Mock()
        mock_blade.get_management_access_policies_roles.return_value = _err()

        _run(_handle_role, mock_module, mock_blade, "2.30", {})

        mock_module.fail_json.assert_called_once_with(
            msg="Failed to read role backup-operator. Error: Operation not permitted."
        )
        mock_module.exit_json.assert_not_called()
        mock_blade.delete_management_access_policies_roles.assert_not_called()

    @patch(GEM, return_value=ROLE_MISSING)
    @patch(LOOSE)
    def test_handle_role_absent_realm_style_name_is_noop(
        self, mock_loose_version, mock_gem
    ):
        """Test state=absent on a realm-style name the array does not know is ok"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(state="absent", name="rzaudit::backup-operator")
        mock_blade = Mock()
        mock_blade.get_management_access_policies_roles.return_value = _err()

        _run(_handle_role, mock_module, mock_blade, "2.30", {})

        mock_module.fail_json.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=False)

    @patch(GEM, return_value=ROLE_MISSING)
    @patch(LOOSE)
    def test_handle_role_absent_missing_role_is_noop(
        self, mock_loose_version, mock_gem
    ):
        """Test state=absent on an array-level role that does not exist is ok"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(state="absent")
        mock_blade = Mock()
        mock_blade.get_management_access_policies_roles.return_value = _err()

        _run(_handle_role, mock_module, mock_blade, "2.30", {})

        mock_module.fail_json.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=False)
        mock_blade.get_management_access_policies_rules.assert_not_called()

    @patch(GEM, return_value=ROLE_MISSING)
    @patch(LOOSE)
    def test_handle_role_present_missing_role_check_mode_creates(
        self, mock_loose_version, mock_gem
    ):
        """Test a role the array does not know is still created (check mode)"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(check_mode=True)
        mock_blade = Mock()
        mock_blade.get_management_access_policies_roles.return_value = _err()

        _run(_handle_role, mock_module, mock_blade, "2.30", {})

        mock_module.fail_json.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=True)
        mock_blade.post_management_access_policies_roles.assert_not_called()

    # ---------------- _handle_attach ----------------

    @patch(GEM, return_value=REFUSED)
    @patch(LOOSE)
    def test_handle_attach_present_refused_mapping_read(
        self, mock_loose_version, mock_gem
    ):
        """Test ds_attach reports the refused read, not a missing mapping"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(
            check_mode=True,
            object="ds_attach",
            ds_role="tenant-a-admins",
            policies=["tenant-a-ops"],
        )
        mock_blade = Mock()
        mock_blade.get_directory_services_roles.return_value = _err()

        _run(_handle_attach, mock_module, mock_blade, "2.30", {}, "ds_role")

        mock_module.fail_json.assert_called_once_with(
            msg="Failed to read ds_role tenant-a-admins. Error: Operation not permitted."
        )
        mock_module.exit_json.assert_not_called()

    @patch(GEM, return_value=REFUSED)
    @patch(LOOSE)
    def test_handle_attach_absent_refused_mapping_read_is_not_ok(
        self, mock_loose_version, mock_gem
    ):
        """Test a detach does not report ok when the mapping cannot be read"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(
            object="ds_attach",
            state="absent",
            ds_role="tenant-a-admins",
            policies=["tenant-a-ops"],
        )
        mock_blade = Mock()
        mock_blade.get_directory_services_roles.return_value = _err()

        _run(_handle_attach, mock_module, mock_blade, "2.30", {}, "ds_role")

        mock_module.fail_json.assert_called_once_with(
            msg="Failed to read ds_role tenant-a-admins. Error: Operation not permitted."
        )
        mock_module.exit_json.assert_not_called()
        mock_blade.delete_management_access_policies_directory_services_roles.assert_not_called()

    @patch(GEM, return_value=REFUSED)
    @patch(LOOSE)
    def test_handle_attach_absent_refused_admin_read_is_not_ok(
        self, mock_loose_version, mock_gem
    ):
        """Test an admin detach does not report ok when the admin cannot be read"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(
            object="admin_attach",
            state="absent",
            admin="svc-automation",
            policies=["tenant-a-ops"],
        )
        mock_blade = Mock()
        mock_blade.get_admins.return_value = _err()

        _run(_handle_attach, mock_module, mock_blade, "2.30", {}, "admin")

        mock_module.fail_json.assert_called_once_with(
            msg="Failed to read admin svc-automation. Error: Operation not permitted."
        )
        mock_module.exit_json.assert_not_called()

    @patch(GEM, return_value=ADMIN_MISSING)
    @patch(LOOSE)
    def test_handle_attach_realm_style_admin_does_not_exist(
        self, mock_loose_version, mock_gem
    ):
        """Test attaching to a realm-style admin name fails as a missing admin"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(
            object="admin_attach",
            admin="rzaudit::svc-automation",
            policies=["tenant-a-ops"],
        )
        mock_blade = Mock()
        mock_blade.get_admins.return_value = _err()

        _run(_handle_attach, mock_module, mock_blade, "2.30", {}, "admin")

        mock_module.fail_json.assert_called_once_with(
            msg="admin rzaudit::svc-automation does not exist"
        )
        mock_blade.post_management_access_policies_admins.assert_not_called()

    @patch(GEM, return_value=DS_ROLE_MISSING)
    @patch(LOOSE)
    def test_handle_attach_absent_missing_mapping_is_noop(
        self, mock_loose_version, mock_gem
    ):
        """Test detaching from a mapping the array does not know stays a no-op"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(
            object="ds_attach",
            state="absent",
            ds_role="rzaudit::tenant-a-admins",
            policies=["tenant-a-ops"],
        )
        mock_blade = Mock()
        mock_blade.get_directory_services_roles.return_value = _err()

        _run(_handle_attach, mock_module, mock_blade, "2.30", {}, "ds_role")

        mock_module.fail_json.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=False)

    @patch(LOOSE)
    def test_handle_attach_realm_scoped_policy_uses_bare_name(self, mock_loose_version):
        """Test a realm-scoped policy is attached to an admin under its bare name"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(
            object="admin_attach", admin="svc-automation", policies=["tenant-a-ops"]
        )
        attached = Mock()
        attached.policy = Mock()
        attached.policy.name = "readonly"
        mock_blade = Mock()
        mock_blade.get_admins.return_value = _ok([Mock()])
        mock_blade.get_management_access_policies_admins.return_value = _ok([attached])
        mock_blade.post_management_access_policies_admins.return_value = _ok([])

        _run(_handle_attach, mock_module, mock_blade, "2.30", {}, "admin")

        mock_blade.post_management_access_policies_admins.assert_called_once_with(
            member_names=["svc-automation"], policy_names=["tenant-a-ops"]
        )
        mock_module.exit_json.assert_called_once_with(changed=True)

    # ---------------- main ----------------

    @patch(GEM, return_value=REFUSED)
    @patch(LOOSE)
    @patch("plugins.modules.purefb_mgmt_role.get_system")
    @patch("plugins.modules.purefb_mgmt_role.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_role.HAS_PYPURECLIENT", True)
    def test_main_role_absent_refused_read_fails(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_gem
    ):
        """Test main does not report ok for state=absent on a refused read"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(state="absent")
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_blade.get_management_access_policies_roles.return_value = _err()
        mock_get_system.return_value = mock_blade

        _run(main)

        mock_module.fail_json.assert_called_once_with(
            msg="Failed to read role backup-operator. Error: Operation not permitted."
        )
        mock_module.exit_json.assert_not_called()
        mock_blade.delete_management_access_policies_roles.assert_not_called()

    @patch(GEM, return_value=REFUSED)
    @patch(LOOSE)
    @patch("plugins.modules.purefb_mgmt_role.get_system")
    @patch("plugins.modules.purefb_mgmt_role.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_role.HAS_PYPURECLIENT", True)
    def test_main_ds_attach_refused_read_fails(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_gem
    ):
        """Test main reports a refused mapping read for object=ds_attach"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(
            object="ds_attach", ds_role="tenant-a-admins", policies=["tenant-a-ops"]
        )
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_blade.get_directory_services_roles.return_value = _err()
        mock_get_system.return_value = mock_blade

        _run(main)

        mock_module.fail_json.assert_called_once_with(
            msg="Failed to read ds_role tenant-a-admins. Error: Operation not permitted."
        )
        mock_blade.post_management_access_policies_directory_services_roles.assert_not_called()


class TestPurefbMgmtRoleDeleteGuardCase:
    """The delete guard holds whatever letter case the task uses."""

    # ---------------- _role_referenced_by_rule ----------------

    def test_referenced_by_id_under_case_variant(self):
        """Test a rule matches the stored role when the task uses another case"""
        mock_module = _module(name="BACKUP-Operator", state="absent")
        mock_blade = Mock()
        mock_blade.get_management_access_policies_rules.return_value = _ok(
            [_rule(role_name="other", role_id="role-id-9"), _rule()]
        )

        assert (
            _role_referenced_by_rule(mock_module, mock_blade, _role_obj(), {}) is True
        )

    def test_referenced_by_lowercased_name_without_ids(self):
        """Test names are compared lower-cased when a reference has no id"""
        mock_module = _module(name="backup-operator", state="absent")
        mock_blade = Mock()
        mock_blade.get_management_access_policies_rules.return_value = _ok(
            [_rule(role_name="backup-operator", role_id=None)]
        )
        stored = _role_obj(name="Backup-Operator", role_id=None)

        assert _role_referenced_by_rule(mock_module, mock_blade, stored, {}) is True

    def test_referenced_by_id_when_reference_has_no_name(self):
        """Test the id alone identifies the role"""
        mock_module = _module(state="absent")
        mock_blade = Mock()
        mock_blade.get_management_access_policies_rules.return_value = _ok(
            [_rule(role_name=None, role_id="role-id-1")]
        )

        assert (
            _role_referenced_by_rule(mock_module, mock_blade, _role_obj(), {}) is True
        )

    def test_rule_without_role_is_skipped(self):
        """Test a rule that carries no role reference does not match or crash"""
        mock_module = _module(state="absent")
        orphan = Mock()
        orphan.role = None
        mock_blade = Mock()
        mock_blade.get_management_access_policies_rules.return_value = _ok(
            [orphan, _rule(role_name="viewer", role_id="role-id-2")]
        )

        assert (
            _role_referenced_by_rule(mock_module, mock_blade, _role_obj(), {}) is False
        )

    def test_rules_listing_uses_the_context(self):
        """Test the rule listing is read in the context of the task"""
        mock_module = _module(state="absent", context="other-array")
        mock_blade = Mock()
        mock_blade.get_management_access_policies_rules.return_value = _ok([])

        assert (
            _role_referenced_by_rule(
                mock_module,
                mock_blade,
                _role_obj(),
                {"context_names": ["other-array"]},
            )
            is False
        )
        mock_blade.get_management_access_policies_rules.assert_called_once_with(
            context_names=["other-array"]
        )

    # ---------------- _delete_role ----------------

    def test_delete_refused_under_case_variant(self):
        """Test no DELETE is sent for a granted role named in another case"""
        mock_module = _module(name="BACKUP-OPERATOR", state="absent")
        mock_blade = Mock()
        mock_blade.get_management_access_policies_rules.return_value = _ok([_rule()])

        _run(_delete_role, mock_module, mock_blade, {}, _role_obj())

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "Role BACKUP-OPERATOR is referenced by one or more policy rules" in msg
        mock_blade.delete_management_access_policies_roles.assert_not_called()
        mock_module.exit_json.assert_not_called()

    def test_delete_refused_under_case_variant_check_mode(self):
        """Test check mode predicts the refusal instead of a change"""
        mock_module = _module(check_mode=True, name="BACKUP-OPERATOR", state="absent")
        mock_blade = Mock()
        mock_blade.get_management_access_policies_rules.return_value = _ok([_rule()])

        _run(_delete_role, mock_module, mock_blade, {}, _role_obj())

        mock_module.fail_json.assert_called_once()
        assert "is referenced by" in mock_module.fail_json.call_args[1]["msg"]
        mock_module.exit_json.assert_not_called()
        mock_blade.delete_management_access_policies_roles.assert_not_called()

    @patch(GEM, return_value=REFUSED_VERB)
    def test_delete_not_sent_when_rules_cannot_be_listed(self, mock_gem):
        """Test no DELETE is sent when the guard cannot be evaluated"""
        mock_module = _module(state="absent")
        mock_blade = Mock()
        mock_blade.get_management_access_policies_rules.return_value = _err()

        _run(_delete_role, mock_module, mock_blade, {}, _role_obj())

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert msg.startswith("Failed to list management access policy rules")
        assert msg.endswith(REFUSED_VERB)
        mock_blade.delete_management_access_policies_roles.assert_not_called()
        mock_module.exit_json.assert_not_called()

    def test_delete_unreferenced_role_under_case_variant(self):
        """Test a role no rule grants is deleted under the task's spelling"""
        mock_module = _module(name="BACKUP-OPERATOR", state="absent")
        mock_blade = Mock()
        mock_blade.get_management_access_policies_rules.return_value = _ok(
            [_rule(role_name="viewer", role_id="role-id-2")]
        )
        mock_blade.delete_management_access_policies_roles.return_value = _ok([])

        _run(_delete_role, mock_module, mock_blade, {}, _role_obj())

        mock_module.fail_json.assert_not_called()
        mock_blade.delete_management_access_policies_roles.assert_called_once_with(
            names=["BACKUP-OPERATOR"]
        )
        mock_module.exit_json.assert_called_once_with(changed=True)

    # ---------------- main ----------------

    @patch(LOOSE)
    @patch("plugins.modules.purefb_mgmt_role.get_system")
    @patch("plugins.modules.purefb_mgmt_role.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_role.HAS_PYPURECLIENT", True)
    def test_main_delete_refused_under_case_variant(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test main refuses to delete a granted role named in another case"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(name="Backup-Operator", state="absent")
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_blade.get_management_access_policies_roles.return_value = _ok(
            [_role_obj()]
        )
        mock_blade.get_management_access_policies_rules.return_value = _ok(
            [_rule(role_name="admin", role_id="role-id-0"), _rule()]
        )
        mock_get_system.return_value = mock_blade

        _run(main)

        mock_blade.get_management_access_policies_roles.assert_called_once_with(
            names=["Backup-Operator"]
        )
        mock_module.fail_json.assert_called_once()
        assert "is referenced by" in mock_module.fail_json.call_args[1]["msg"]
        mock_blade.delete_management_access_policies_roles.assert_not_called()


def _attached(policy_name):
    """A policy membership as GET management-access-policies/admins returns it."""
    member = Mock()
    member.policy = Mock()
    member.policy.name = policy_name
    return member


def _ds_roles_get(names=None):
    """Like the SDK's get_directory_services_roles: it takes no context_names."""
    return _ok([Mock()])


class TestPurefbMgmtRoleOneName:
    """A task manages one role, one admin or one role mapping."""

    # ---------------- _validate_role_name ----------------

    def test_validate_role_name_rejects_list_of_names(self):
        """Test a comma, which the array reads as a separator of names, is refused"""
        mock_module = _module()

        _run(_validate_role_name, mock_module, "backup-operator,viewer")

        mock_module.fail_json.assert_called_once_with(
            msg=(
                "Role name backup-operator,viewer must be the name of one role: "
                "the array reads a comma as a separator of names and * as a "
                "pattern."
            )
        )

    def test_validate_role_name_rejects_pattern(self):
        """Test a *, which the array reads as a pattern, is refused"""
        mock_module = _module()

        _run(_validate_role_name, mock_module, "backup-*")

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert msg.startswith("Role name backup-* must be the name of one role")

    def test_validate_role_name_accepts_every_legal_character(self):
        """Test letters, digits, hyphen and underscore pass"""
        mock_module = _module()

        _validate_role_name(mock_module, "Backup_operator-2")

        mock_module.fail_json.assert_not_called()

    # ---------------- _handle_role ----------------

    @patch(LOOSE)
    def test_handle_role_absent_list_is_not_deleted_on_its_first_role(
        self, mock_loose_version
    ):
        """Test a list whose second role a rule grants sends no DELETE"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(state="absent", name="free-role,backup-operator")
        mock_blade = Mock()
        # The array answers a list of names with every role on it.
        mock_blade.get_management_access_policies_roles.return_value = _ok(
            [_role_obj(name="free-role", role_id="role-id-7"), _role_obj()]
        )
        mock_blade.get_management_access_policies_rules.return_value = _ok([_rule()])
        mock_blade.delete_management_access_policies_roles.return_value = _ok([])

        _run(_handle_role, mock_module, mock_blade, "2.30", {})

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "must be the name of one role" in msg
        mock_blade.get_management_access_policies_roles.assert_not_called()
        mock_blade.delete_management_access_policies_roles.assert_not_called()
        mock_module.exit_json.assert_not_called()

    @patch(LOOSE)
    def test_handle_role_absent_pattern_check_mode_predicts_no_change(
        self, mock_loose_version
    ):
        """Test check mode refuses a pattern instead of predicting a delete"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(check_mode=True, state="absent", name="backup-*")
        mock_blade = Mock()
        # The array answers a pattern with every role that matches it.
        mock_blade.get_management_access_policies_roles.return_value = _ok(
            [_role_obj(name="backup-free", role_id="role-id-7"), _role_obj()]
        )
        mock_blade.get_management_access_policies_rules.return_value = _ok([_rule()])

        _run(_handle_role, mock_module, mock_blade, "2.30", {})

        mock_module.fail_json.assert_called_once()
        assert (
            "must be the name of one role" in mock_module.fail_json.call_args[1]["msg"]
        )
        mock_module.exit_json.assert_not_called()
        mock_blade.delete_management_access_policies_roles.assert_not_called()

    @patch(LOOSE)
    def test_handle_role_absent_list_with_builtin_role_is_refused(
        self, mock_loose_version
    ):
        """Test a built-in role behind a custom one on a list is not addressed"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(state="absent", name="free-role,viewer")
        mock_blade = Mock()
        mock_blade.get_management_access_policies_roles.return_value = _ok(
            [
                _role_obj(name="free-role", role_id="role-id-7"),
                _role_obj(name="viewer", role_id="role-id-8", pure_defined=True),
            ]
        )
        mock_blade.get_management_access_policies_rules.return_value = _ok([])
        mock_blade.delete_management_access_policies_roles.return_value = _ok([])

        _run(_handle_role, mock_module, mock_blade, "2.30", {})

        mock_module.fail_json.assert_called_once()
        mock_blade.delete_management_access_policies_roles.assert_not_called()
        mock_module.exit_json.assert_not_called()

    @patch(LOOSE)
    def test_handle_role_present_pattern_is_not_an_existing_role(
        self, mock_loose_version
    ):
        """Test a pattern that matches a role does not report that role as present"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(name="backup-*")
        mock_blade = Mock()
        mock_blade.get_management_access_policies_roles.return_value = _ok(
            [_role_obj()]
        )

        _run(_handle_role, mock_module, mock_blade, "2.30", {})

        mock_module.fail_json.assert_called_once()
        mock_module.exit_json.assert_not_called()
        mock_blade.get_management_access_policies_roles.assert_not_called()

    # ---------------- _handle_attach ----------------

    @patch(LOOSE)
    def test_handle_attach_admin_list_is_not_read_as_one_admin(
        self, mock_loose_version
    ):
        """Test a policy one admin of a list holds does not count for the other"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(
            object="admin_attach", admin="svc-a,svc-b", policies=["tenant-a-ops"]
        )
        mock_blade = Mock()
        # The array answers a list of members with the policies of all of them.
        mock_blade.get_admins.return_value = _ok([Mock(), Mock()])
        mock_blade.get_management_access_policies_admins.return_value = _ok(
            [_attached("tenant-a-ops")]
        )

        _run(_handle_attach, mock_module, mock_blade, "2.30", {}, "admin")

        mock_module.fail_json.assert_called_once_with(
            msg=(
                "admin svc-a,svc-b must be the name of one admin: the array "
                "reads a comma as a separator of names."
            )
        )
        mock_module.exit_json.assert_not_called()
        mock_blade.get_admins.assert_not_called()
        mock_blade.post_management_access_policies_admins.assert_not_called()

    @patch(LOOSE)
    def test_handle_attach_admin_list_detach_sends_nothing(self, mock_loose_version):
        """Test a detach from a list of admins is refused before any request"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(
            object="admin_attach",
            state="absent",
            admin="svc-a,svc-b",
            policies=["tenant-a-ops"],
        )
        mock_blade = Mock()
        mock_blade.get_admins.return_value = _ok([Mock(), Mock()])
        mock_blade.get_management_access_policies_admins.return_value = _ok(
            [_attached("tenant-a-ops")]
        )
        mock_blade.delete_management_access_policies_admins.return_value = _ok([])

        _run(_handle_attach, mock_module, mock_blade, "2.30", {}, "admin")

        mock_module.fail_json.assert_called_once()
        assert (
            "must be the name of one admin" in mock_module.fail_json.call_args[1]["msg"]
        )
        mock_blade.delete_management_access_policies_admins.assert_not_called()
        mock_module.exit_json.assert_not_called()

    @patch(LOOSE)
    def test_handle_attach_mapping_list_is_not_read_as_one_mapping(
        self, mock_loose_version
    ):
        """Test a list of role mappings is refused, check mode included"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(
            check_mode=True,
            object="ds_attach",
            ds_role="tenant-a-admins,tenant-b-admins",
            policies=["tenant-a-ops"],
        )
        mock_blade = Mock()
        mock_blade.get_directory_services_roles.return_value = _ok([Mock(), Mock()])
        mock_blade.get_management_access_policies_directory_services_roles.return_value = _ok(
            [_attached("tenant-a-ops")]
        )

        _run(_handle_attach, mock_module, mock_blade, "2.30", {}, "ds_role")

        mock_module.fail_json.assert_called_once_with(
            msg=(
                "ds_role tenant-a-admins,tenant-b-admins must be the name of one "
                "role mapping: the array reads a comma as a separator of names."
            )
        )
        mock_module.exit_json.assert_not_called()
        mock_blade.get_directory_services_roles.assert_not_called()

    # ---------------- ds_attach and a fleet context ----------------

    @patch(LOOSE)
    def test_handle_attach_mapping_with_context_fails_with_a_message(
        self, mock_loose_version
    ):
        """Test ds_attach with a context is refused, not passed to the SDK"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(
            object="ds_attach",
            ds_role="tenant-a-admins",
            policies=["tenant-a-ops"],
            context="other-array",
        )
        mock_blade = Mock()
        mock_blade.get_directory_services_roles = Mock(side_effect=_ds_roles_get)

        _run(
            _handle_attach,
            mock_module,
            mock_blade,
            "2.30",
            {"context_names": ["other-array"]},
            "ds_role",
        )

        mock_module.fail_json.assert_called_once_with(
            msg=(
                "context is not supported with object=ds_attach: the REST API "
                "offers no fleet context for directory-service role mappings."
            )
        )
        mock_blade.get_directory_services_roles.assert_not_called()
        mock_module.exit_json.assert_not_called()

    @patch(LOOSE)
    def test_handle_attach_mapping_detach_with_context_check_mode(
        self, mock_loose_version
    ):
        """Test the refusal comes in check mode and for a detach as well"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(
            check_mode=True,
            object="ds_attach",
            state="absent",
            ds_role="tenant-a-admins",
            policies=["tenant-a-ops"],
            context="other-array",
        )
        mock_blade = Mock()
        mock_blade.get_directory_services_roles = Mock(side_effect=_ds_roles_get)

        _run(
            _handle_attach,
            mock_module,
            mock_blade,
            "2.30",
            {"context_names": ["other-array"]},
            "ds_role",
        )

        mock_module.fail_json.assert_called_once()
        assert "context is not supported" in mock_module.fail_json.call_args[1]["msg"]
        mock_blade.get_directory_services_roles.assert_not_called()
        mock_module.exit_json.assert_not_called()

    @patch(LOOSE)
    def test_handle_attach_admin_with_context_still_uses_it(self, mock_loose_version):
        """Test admin_attach keeps sending the context with every call"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(
            object="admin_attach",
            admin="svc-automation",
            policies=["tenant-a-ops"],
            context="other-array",
        )
        ctx = {"context_names": ["other-array"]}
        mock_blade = Mock()
        mock_blade.get_admins.return_value = _ok([Mock()])
        mock_blade.get_management_access_policies_admins.return_value = _ok([])
        mock_blade.post_management_access_policies_admins.return_value = _ok([])

        _run(_handle_attach, mock_module, mock_blade, "2.30", ctx, "admin")

        mock_module.fail_json.assert_not_called()
        mock_blade.get_admins.assert_called_once_with(
            names=["svc-automation"], context_names=["other-array"]
        )
        mock_blade.post_management_access_policies_admins.assert_called_once_with(
            member_names=["svc-automation"],
            policy_names=["tenant-a-ops"],
            context_names=["other-array"],
        )
        mock_module.exit_json.assert_called_once_with(changed=True)

    # ---------------- main ----------------

    @patch(LOOSE)
    @patch("plugins.modules.purefb_mgmt_role.get_system")
    @patch("plugins.modules.purefb_mgmt_role.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_role.HAS_PYPURECLIENT", True)
    def test_main_role_absent_list_sends_no_delete(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test main refuses a list of roles before the array is asked"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_module = _module(state="absent", name="free-role,backup-operator")
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_blade.get_management_access_policies_roles.return_value = _ok(
            [_role_obj(name="free-role", role_id="role-id-7"), _role_obj()]
        )
        mock_blade.get_management_access_policies_rules.return_value = _ok([_rule()])
        mock_blade.delete_management_access_policies_roles.return_value = _ok([])
        mock_get_system.return_value = mock_blade

        _run(main)

        mock_module.fail_json.assert_called_once()
        assert (
            "must be the name of one role" in mock_module.fail_json.call_args[1]["msg"]
        )
        mock_blade.delete_management_access_policies_roles.assert_not_called()
        mock_module.exit_json.assert_not_called()

    @patch(LOOSE)
    @patch("plugins.modules.purefb_mgmt_role.get_system")
    @patch("plugins.modules.purefb_mgmt_role.AnsibleModule")
    @patch("plugins.modules.purefb_mgmt_role.HAS_PYPURECLIENT", True)
    def test_main_ds_attach_with_context_fails_with_a_message(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test main reports that ds_attach takes no context"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        mock_module = _module(
            object="ds_attach",
            ds_role="tenant-a-admins",
            policies=["tenant-a-ops"],
            context="other-array",
        )
        mock_ansible_module.return_value = mock_module
        mock_blade = Mock()
        mock_blade.get_directory_services_roles = Mock(side_effect=_ds_roles_get)
        mock_get_system.return_value = mock_blade

        _run(main)

        mock_module.fail_json.assert_called_once()
        assert "context is not supported" in mock_module.fail_json.call_args[1]["msg"]
        mock_blade.get_directory_services_roles.assert_not_called()
        mock_blade.post_management_access_policies_directory_services_roles.assert_not_called()
