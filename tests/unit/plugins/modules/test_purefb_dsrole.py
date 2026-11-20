# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_dsrole module."""

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

from plugins.modules.purefb_dsrole import (
    main,
    _current_policy_names,
    _policy_diff,
    _dn_changed,
    _get_mapping,
)
from plugins.module_utils.version import LooseVersion as RealLooseVersion

MODULE = "plugins.modules.purefb_dsrole"


def _ref(name):
    ref = Mock()
    ref.name = name
    return ref


def _mapping(
    group="cc44-grp",
    group_base="OU=groups",
    policies=("readonly",),
    legacy=False,
    name=None,
):
    """A directory service role mapping as the array reports it.

    ``legacy`` mimics an array below REST 2.19, which reports no
    management_access_policies, only the legacy role. ``name`` is the
    spelling the array stores; None stands for the spelling of the task.
    """
    mapping = Mock()
    mapping.name = name
    mapping.group = group
    mapping.group_base = group_base
    if legacy:
        mapping.management_access_policies = None
    else:
        mapping.management_access_policies = [_ref(name) for name in policies]
    mapping.role = _ref(policies[0]) if len(policies) == 1 else None
    return mapping


MISSING = "Directory service role does not exist."
NOT_PERMITTED = "Operation not permitted."


def _response(status=200, items=None, error="boom"):
    """An SDK response; ``error`` is what get_error_message reports for it"""
    res = Mock()
    res.status_code = status
    res.items = list(items or [])
    res.error = error
    return res


def _base_params(**overrides):
    params = {
        "name": "cc44-map",
        "role": None,
        "policies": ["readonly"],
        "state": "present",
        "group": "cc44-grp",
        "group_base": "ou=groups",
    }
    params.update(overrides)
    return params


WRITE_METHODS = (
    "post_directory_services_roles",
    "patch_directory_services_roles",
    "delete_directory_services_roles",
    "post_management_access_policies_directory_services_roles",
    "delete_management_access_policies_directory_services_roles",
)


def _blade(mapping=None, write_status=200):
    """A blade whose GET reports ``mapping`` (None: 400, missing) and whose
    writes all answer ``write_status``"""
    blade = Mock()
    if mapping is None:
        blade.get_directory_services_roles.return_value = _response(400, error=MISSING)
    else:
        blade.get_directory_services_roles.return_value = _response(200, [mapping])
    for method in WRITE_METHODS:
        getattr(blade, method).return_value = _response(write_status)
    return blade


def _module(params, check_mode=False):
    module = Mock()
    module.params = params
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _run(params, blade, api_version="2.30", check_mode=False, has_sdk=True):
    """Run main() with the module plumbing patched; return the module mock.

    Its ``get_system`` attribute is the patched login, so a test can assert
    that the array was never contacted.
    """
    module = _module(params, check_mode)
    with patch(MODULE + ".AnsibleModule", return_value=module), patch(
        MODULE + ".get_system", return_value=blade
    ) as get_system, patch(
        MODULE + ".get_rest_api_version", return_value=api_version
    ), patch(
        MODULE + ".LooseVersion", RealLooseVersion
    ), patch(
        MODULE + ".get_error_message", side_effect=lambda res: res.error
    ), patch(
        MODULE + ".HAS_PYPURECLIENT", has_sdk
    ):
        try:
            main()
        except SystemExit:
            pass
    module.get_system = get_system
    return module


def _no_writes(blade):
    for method in WRITE_METHODS:
        getattr(blade, method).assert_not_called()


def _fake_reference(name):
    return ("ref", name)


class TestPurefbDsrole:
    """Test cases for purefb_dsrole module"""

    # ---------------- helper-function unit tests ----------------

    def test_current_policy_names_from_policies(self):
        """Policy names come from management_access_policies when reported"""
        mapping = _mapping(policies=("readonly", "storage_admin"))
        assert _current_policy_names(mapping) == ["readonly", "storage_admin"]

    def test_current_policy_names_legacy_role(self):
        """Below REST 2.19 the legacy role stands for the policy set"""
        mapping = _mapping(policies=("readonly",), legacy=True)
        assert _current_policy_names(mapping) == ["readonly"]

    def test_current_policy_names_legacy_without_role(self):
        """A legacy mapping without a role has no policies"""
        mapping = _mapping(policies=("readonly",), legacy=True)
        mapping.role = None
        assert _current_policy_names(mapping) == []

    def test_policy_diff_adds_case_insensitively(self):
        """A policy already attached in another case is not re-added"""
        assert _policy_diff(["readonly"], ["READONLY", "storage_admin"]) == (
            ["storage_admin"],
            [],
        )

    def test_policy_diff_removes_with_array_spelling(self):
        """Detach uses the array's spelling of the policy name"""
        assert _policy_diff(["Readonly", "storage_admin"], ["storage_admin"]) == (
            [],
            ["Readonly"],
        )

    def test_policy_diff_equal_sets(self):
        """Order and case differences are not a change"""
        assert _policy_diff(["a", "b"], ["B", "a"]) == ([], [])

    def test_dn_changed(self):
        """group and group_base compare case-insensitively, omitted never"""
        assert _dn_changed("OU=groups", "ou=groups") is False
        assert _dn_changed("grp", None) is False
        assert _dn_changed(None, "") is False
        assert _dn_changed("grp", "other") is True
        assert _dn_changed("grp", "") is True

    def test_get_mapping_missing(self):
        """A 400 saying the role does not exist means the mapping is missing"""
        module = _module({"name": "cc44-map"})
        blade = Mock()
        blade.get_directory_services_roles.return_value = _response(400, error=MISSING)
        with patch(MODULE + ".get_error_message", side_effect=lambda res: res.error):
            assert _get_mapping(module, blade) is None
        blade.get_directory_services_roles.assert_called_once_with(names=["cc44-map"])
        module.fail_json.assert_not_called()

    def test_get_mapping_other_400_fails(self):
        """Any other 400 is an error, not a missing mapping"""
        module = _module({"name": "cc44-map"})
        blade = Mock()
        blade.get_directory_services_roles.return_value = _response(
            400, error="Invalid body parameter"
        )
        with patch(MODULE + ".get_error_message", side_effect=lambda res: res.error):
            with pytest.raises(SystemExit):
                _get_mapping(module, blade)
        msg = module.fail_json.call_args[1]["msg"]
        assert "Fetch Directory Service Role cc44-map failed" in msg
        assert "Invalid body parameter" in msg

    def test_get_mapping_server_error_fails(self):
        """A non-400 GET error is fatal"""
        module = _module({"name": "cc44-map"})
        blade = Mock()
        blade.get_directory_services_roles.return_value = _response(
            500, error="Internal error"
        )
        with patch(MODULE + ".get_error_message", side_effect=lambda res: res.error):
            with pytest.raises(SystemExit):
                _get_mapping(module, blade)
        msg = module.fail_json.call_args[1]["msg"]
        assert "Fetch Directory Service Role cc44-map failed" in msg
        assert "Internal error" in msg

    def test_get_mapping_returns_item(self):
        """The first item of a 200 is the mapping"""
        module = Mock()
        module.params = {"name": "cc44-map"}
        mapping = _mapping()
        blade = Mock()
        blade.get_directory_services_roles.return_value = _response(200, [mapping])
        assert _get_mapping(module, blade) is mapping

    # ---------------- main(): argument handling and gates ----------------

    def test_main_module_constraints(self):
        """AnsibleModule gets the option constraints and check mode"""
        blade = _blade(mapping=_mapping())
        module = _module(_base_params())
        with patch(MODULE + ".AnsibleModule", return_value=module) as mock_am, patch(
            MODULE + ".get_system", return_value=blade
        ), patch(MODULE + ".get_rest_api_version", return_value="2.30"), patch(
            MODULE + ".LooseVersion", RealLooseVersion
        ), patch(
            MODULE + ".HAS_PYPURECLIENT", True
        ):
            try:
                main()
            except SystemExit:
                pass
        kwargs = mock_am.call_args[1]
        assert kwargs["required_together"] == [["group", "group_base"]]
        assert kwargs["required_one_of"] == [["name", "role"]]
        assert kwargs["mutually_exclusive"] == [["role", "policies"]]
        assert kwargs["required_if"] == [
            ["state", "present", ["role", "policies"], True]
        ]
        assert kwargs["supports_check_mode"] is True

    def test_main_fails_below_min_version(self):
        """REST below 2.14 fails before the array is read or written"""
        blade = _blade()
        module = _run(_base_params(), blade, api_version="2.13")
        module.fail_json.assert_called_once()
        assert "2.14" in module.fail_json.call_args[1]["msg"]
        blade.get_directory_services_roles.assert_not_called()
        _no_writes(blade)

    def test_main_fails_policies_below_2_19(self):
        """policies on REST below 2.19 fails before the array is read or written"""
        blade = _blade()
        module = _run(_base_params(), blade, api_version="2.17")
        module.fail_json.assert_called_once()
        assert "2.19" in module.fail_json.call_args[1]["msg"]
        blade.get_directory_services_roles.assert_not_called()
        _no_writes(blade)

    def test_main_fails_empty_policies(self):
        """An empty policies list is refused"""
        blade = _blade()
        module = _run(_base_params(policies=[]), blade)
        module.fail_json.assert_called_once()
        assert "at least one" in module.fail_json.call_args[1]["msg"]
        blade.get_directory_services_roles.assert_not_called()
        _no_writes(blade)

    def test_main_fails_without_sdk(self):
        """A missing py-pure-client fails before the array is contacted"""
        blade = _blade()
        module = _run(_base_params(), blade, has_sdk=False)
        module.fail_json.assert_called_once()
        assert "py-pure-client sdk" in module.fail_json.call_args[1]["msg"]
        blade.get_directory_services_roles.assert_not_called()
        _no_writes(blade)

    def test_main_get_error_fails_before_writes(self):
        """A GET error other than a missing mapping fails, even with state=absent"""
        blade = _blade()
        blade.get_directory_services_roles.return_value = _response(
            500, error="Internal error"
        )
        module = _run(_base_params(state="absent", policies=None), blade)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Fetch Directory Service Role cc44-map failed" in msg
        assert "Internal error" in msg
        module.exit_json.assert_not_called()
        _no_writes(blade)

    # ---------------- main(): create ----------------

    def test_main_creates_custom_mapping_with_policies(self):
        """A missing custom mapping is POSTed with its policy references"""
        blade = _blade(mapping=None)
        with patch(MODULE + ".DirectoryServiceRolePost") as mock_post, patch(
            MODULE + ".ReferenceWritable", side_effect=_fake_reference
        ):
            module = _run(_base_params(policies=["readonly", "nfs_admins"]), blade)
        blade.post_directory_services_roles.assert_called_once()
        assert blade.post_directory_services_roles.call_args[1]["names"] == ["cc44-map"]
        mock_post.assert_called_once_with(
            group="cc44-grp",
            group_base="ou=groups",
            management_access_policies=[("ref", "readonly"), ("ref", "nfs_admins")],
        )
        blade.patch_directory_services_roles.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_creates_missing_builtin_from_role(self):
        """present on a missing built-in mapping POSTs it under the role name"""
        blade = _blade(mapping=None)
        with patch(MODULE + ".DirectoryServiceRolePost") as mock_post, patch(
            MODULE + ".ReferenceWritable", side_effect=_fake_reference
        ):
            module = _run(
                _base_params(name=None, role="ops_admin", policies=None), blade
            )
        blade.get_directory_services_roles.assert_called_once_with(names=["ops_admin"])
        assert blade.post_directory_services_roles.call_args[1]["names"] == [
            "ops_admin"
        ]
        mock_post.assert_called_once_with(
            group="cc44-grp",
            group_base="ou=groups",
            management_access_policies=[("ref", "ops_admin")],
        )
        blade.patch_directory_services_roles.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_creates_with_role_below_2_19(self):
        """Below REST 2.19 the mapping is POSTed with the legacy role field"""
        blade = _blade(mapping=None)
        with patch(MODULE + ".DirectoryServiceRolePost") as mock_post, patch(
            MODULE + ".ReferenceWritable", side_effect=_fake_reference
        ):
            module = _run(
                _base_params(role="readonly", policies=None), blade, api_version="2.17"
            )
        mock_post.assert_called_once_with(
            group="cc44-grp", group_base="ou=groups", role=("ref", "readonly")
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_create_check_mode(self):
        """Check mode reports the create without POSTing"""
        blade = _blade(mapping=None)
        module = _run(_base_params(), blade, check_mode=True)
        _no_writes(blade)
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_create_api_error(self):
        """A failed POST surfaces the array error"""
        blade = _blade(mapping=None, write_status=400)
        module = _run(_base_params(), blade)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Create Directory Service Role cc44-map failed" in msg
        assert "boom" in msg

    # ---------------- main(): update ----------------

    def test_main_update_group_patches_only_dn(self):
        """A group change PATCHes group and group_base and nothing else"""
        blade = _blade(mapping=_mapping(group="old-grp"))
        with patch(MODULE + ".DirectoryServiceRole") as mock_role:
            module = _run(_base_params(), blade)
        blade.patch_directory_services_roles.assert_called_once()
        assert blade.patch_directory_services_roles.call_args[1]["names"] == [
            "cc44-map"
        ]
        mock_role.assert_called_once_with(group="cc44-grp", group_base="ou=groups")
        blade.post_management_access_policies_directory_services_roles.assert_not_called()
        blade.delete_management_access_policies_directory_services_roles.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_update_attaches_missing_policy(self):
        """A policy missing from the mapping is attached, nothing detached"""
        blade = _blade(mapping=_mapping(policies=("readonly",)))
        module = _run(_base_params(policies=["readonly", "storage_admin"]), blade)
        blade.post_management_access_policies_directory_services_roles.assert_called_once_with(
            member_names=["cc44-map"], policy_names=["storage_admin"]
        )
        blade.delete_management_access_policies_directory_services_roles.assert_not_called()
        blade.patch_directory_services_roles.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_update_swaps_policy_attach_before_detach(self):
        """Replacing the policy set attaches the new policy before detaching"""
        blade = _blade(mapping=_mapping(policies=("readonly",)))
        calls = []

        def record_add(**kwargs):
            calls.append(("add", kwargs))
            return _response()

        def record_remove(**kwargs):
            calls.append(("remove", kwargs))
            return _response()

        blade.post_management_access_policies_directory_services_roles.side_effect = (
            record_add
        )
        blade.delete_management_access_policies_directory_services_roles.side_effect = (
            record_remove
        )
        module = _run(_base_params(policies=["storage_admin"]), blade)
        assert calls == [
            ("add", {"member_names": ["cc44-map"], "policy_names": ["storage_admin"]}),
            ("remove", {"member_names": ["cc44-map"], "policy_names": ["readonly"]}),
        ]
        blade.patch_directory_services_roles.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_update_role_leaves_other_policies(self):
        """role on a mapping that already holds its policy changes nothing,
        whatever else is attached"""
        blade = _blade(mapping=_mapping(policies=("readonly", "storage_admin")))
        module = _run(_base_params(role="readonly", policies=None), blade)
        module.exit_json.assert_called_once_with(changed=False)
        _no_writes(blade)

    def test_main_update_role_attaches_without_detaching(self):
        """role attaches its policy and leaves the others attached"""
        blade = _blade(mapping=_mapping(policies=("storage_admin",)))
        module = _run(_base_params(role="readonly", policies=None), blade)
        blade.post_management_access_policies_directory_services_roles.assert_called_once_with(
            member_names=["cc44-map"], policy_names=["readonly"]
        )
        blade.delete_management_access_policies_directory_services_roles.assert_not_called()
        blade.patch_directory_services_roles.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_update_role_below_2_19_patches_role(self):
        """Below REST 2.19 a role change is PATCHed through the legacy field"""
        blade = _blade(mapping=_mapping(policies=("readonly",), legacy=True))
        with patch(MODULE + ".DirectoryServiceRole") as mock_role, patch(
            MODULE + ".ReferenceWritable", side_effect=_fake_reference
        ):
            module = _run(
                _base_params(role="storage_admin", policies=None),
                blade,
                api_version="2.17",
            )
        mock_role.assert_called_once_with(role=("ref", "storage_admin"))
        blade.patch_directory_services_roles.assert_called_once()
        blade.post_management_access_policies_directory_services_roles.assert_not_called()
        blade.delete_management_access_policies_directory_services_roles.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_update_idempotent(self):
        """Case differences in DN parts and order/case in policies are no change"""
        blade = _blade(
            mapping=_mapping(
                group="CC44-grp",
                group_base="OU=groups",
                policies=("Readonly", "storage_admin"),
            )
        )
        module = _run(
            _base_params(
                group="cc44-grp",
                group_base="ou=groups",
                policies=["STORAGE_ADMIN", "readonly"],
            ),
            blade,
        )
        module.exit_json.assert_called_once_with(changed=False)
        _no_writes(blade)

    def test_main_update_omitted_group_not_compared(self):
        """Omitting group and group_base leaves them alone"""
        blade = _blade(mapping=_mapping(group="whatever", group_base="OU=x"))
        module = _run(_base_params(group=None, group_base=None), blade)
        module.exit_json.assert_called_once_with(changed=False)
        _no_writes(blade)

    def test_main_update_check_mode(self):
        """Check mode reports the policy change without writing"""
        blade = _blade(mapping=_mapping(policies=("readonly",)))
        module = _run(_base_params(policies=["storage_admin"]), blade, check_mode=True)
        module.exit_json.assert_called_once_with(changed=True)
        _no_writes(blade)

    def test_main_update_attach_error(self):
        """A failed attach surfaces the array error"""
        blade = _blade(mapping=_mapping(policies=("readonly",)), write_status=400)
        module = _run(_base_params(policies=["readonly", "storage_admin"]), blade)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Attaching policies ['storage_admin']" in msg
        assert "boom" in msg

    def test_main_update_detach_error(self):
        """A failed detach surfaces the array error"""
        blade = _blade(mapping=_mapping(policies=("readonly",)))
        blade.delete_management_access_policies_directory_services_roles.return_value = _response(
            400
        )
        module = _run(_base_params(policies=["storage_admin"]), blade)
        blade.post_management_access_policies_directory_services_roles.assert_called_once()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Detaching policies ['readonly']" in msg
        assert "boom" in msg

    def test_main_update_patch_error(self):
        """A failed group PATCH surfaces the array error"""
        blade = _blade(mapping=_mapping(group="old-grp"), write_status=400)
        module = _run(_base_params(), blade)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Update Directory Service Role cc44-map failed" in msg
        assert "boom" in msg

    # ---------------- main(): delete ----------------

    def test_main_delete_custom_mapping(self):
        """A custom mapping is DELETEd"""
        blade = _blade(mapping=_mapping())
        module = _run(_base_params(state="absent", policies=None), blade)
        blade.delete_directory_services_roles.assert_called_once_with(
            names=["cc44-map"]
        )
        blade.patch_directory_services_roles.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_delete_missing_mapping(self):
        """absent on a missing mapping is a no-op"""
        blade = _blade(mapping=None)
        module = _run(_base_params(state="absent", policies=None), blade)
        module.exit_json.assert_called_once_with(changed=False)
        _no_writes(blade)

    def test_main_delete_builtin_clears_group(self):
        """absent on a built-in mapping blanks its group instead of deleting"""
        blade = _blade(
            mapping=_mapping(
                group="array-admin-users",
                group_base="OU=RBAC-Groups",
                policies=("array_admin",),
            )
        )
        with patch(MODULE + ".DirectoryServiceRole") as mock_role:
            module = _run(
                _base_params(
                    name=None,
                    role="array_admin",
                    policies=None,
                    state="absent",
                    group=None,
                    group_base=None,
                ),
                blade,
            )
        mock_role.assert_called_once_with(group_base="", group="")
        assert blade.patch_directory_services_roles.call_args[1]["names"] == [
            "array_admin"
        ]
        blade.delete_directory_services_roles.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_delete_builtin_already_clear(self):
        """absent on an already cleared built-in mapping is a no-op"""
        blade = _blade(
            mapping=_mapping(group="", group_base="", policies=("readonly",))
        )
        module = _run(
            _base_params(
                name=None,
                role="readonly",
                policies=None,
                state="absent",
                group=None,
                group_base=None,
            ),
            blade,
        )
        module.exit_json.assert_called_once_with(changed=False)
        _no_writes(blade)

    def test_main_delete_check_mode(self):
        """Check mode reports the delete without DELETEing"""
        blade = _blade(mapping=_mapping())
        module = _run(
            _base_params(state="absent", policies=None), blade, check_mode=True
        )
        module.exit_json.assert_called_once_with(changed=True)
        _no_writes(blade)

    def test_main_delete_api_error(self):
        """A failed DELETE surfaces the array error"""
        blade = _blade(mapping=_mapping(), write_status=400)
        module = _run(_base_params(state="absent", policies=None), blade)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Delete Directory Service Role cc44-map failed" in msg
        assert "boom" in msg

    def test_main_delete_builtin_clear_error(self):
        """A failed PATCH clearing a built-in mapping surfaces the array error"""
        blade = _blade(
            mapping=_mapping(
                group="array-admin-users",
                group_base="OU=RBAC-Groups",
                policies=("array_admin",),
            ),
            write_status=400,
        )
        with patch(MODULE + ".DirectoryServiceRole"):
            module = _run(
                _base_params(
                    name=None,
                    role="array_admin",
                    policies=None,
                    state="absent",
                    group=None,
                    group_base=None,
                ),
                blade,
            )
        blade.delete_directory_services_roles.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Delete Directory Service Role array_admin failed" in msg
        assert "boom" in msg

    def test_main_delete_builtin_other_case_clears_group(self):
        """A built-in mapping named in another letter case is cleared like
        the built-in mapping it is, not deleted"""
        blade = _blade(
            mapping=_mapping(
                group="readonly-users",
                group_base="OU=RBAC-Groups",
                policies=("readonly",),
                name="readonly",
            )
        )
        with patch(MODULE + ".DirectoryServiceRole") as mock_role:
            module = _run(
                _base_params(
                    name="ReadOnly",
                    policies=None,
                    state="absent",
                    group=None,
                    group_base=None,
                ),
                blade,
            )
        blade.get_directory_services_roles.assert_called_once_with(names=["ReadOnly"])
        mock_role.assert_called_once_with(group_base="", group="")
        assert blade.patch_directory_services_roles.call_args[1]["names"] == [
            "readonly"
        ]
        blade.delete_directory_services_roles.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_main_delete_builtin_other_case_already_clear(self, check_mode):
        """absent on a cleared built-in mapping named in another letter case
        is a no-op, in check mode too"""
        blade = _blade(
            mapping=_mapping(
                group="", group_base="", policies=("readonly",), name="readonly"
            )
        )
        module = _run(
            _base_params(
                name="READONLY",
                policies=None,
                state="absent",
                group=None,
                group_base=None,
            ),
            blade,
            check_mode=check_mode,
        )
        module.exit_json.assert_called_once_with(changed=False)
        _no_writes(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_main_delete_uses_stored_spelling(self, check_mode):
        """A mapping found under another letter case is deleted under the
        name the array reports: the array answers a delete under any other
        spelling with success and deletes nothing"""
        blade = _blade(mapping=_mapping(name="cc44-map"))
        module = _run(
            _base_params(name="CC44-Map", state="absent", policies=None),
            blade,
            check_mode=check_mode,
        )
        blade.get_directory_services_roles.assert_called_once_with(names=["CC44-Map"])
        if check_mode:
            _no_writes(blade)
        else:
            blade.delete_directory_services_roles.assert_called_once_with(
                names=["cc44-map"]
            )
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_update_uses_stored_spelling(self):
        """Changes to a mapping found under another letter case are sent
        under the name the array reports"""
        blade = _blade(
            mapping=_mapping(policies=("readonly", "storage_admin"), name="cc44-map")
        )
        with patch(MODULE + ".DirectoryServiceRole"):
            module = _run(
                _base_params(
                    name="CC44-Map", group="other", policies=["readonly", "ops_admin"]
                ),
                blade,
            )
        assert blade.patch_directory_services_roles.call_args[1]["names"] == [
            "cc44-map"
        ]
        blade.post_management_access_policies_directory_services_roles.assert_called_once_with(
            member_names=["cc44-map"], policy_names=["ops_admin"]
        )
        blade.delete_management_access_policies_directory_services_roles.assert_called_once_with(
            member_names=["cc44-map"], policy_names=["storage_admin"]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_update_other_case_idempotent(self):
        """A mapping named in another letter case with nothing to change is
        left alone"""
        blade = _blade(mapping=_mapping(name="cc44-map"))
        module = _run(_base_params(name="CC44-MAP"), blade)
        module.exit_json.assert_called_once_with(changed=False)
        _no_writes(blade)

    # ---------------- main(): empty names and lists of names ----------------

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize("name", ["", None])
    def test_main_refuses_empty_name_without_role(self, name, state, check_mode):
        """An empty name with no role to stand in for it is refused before
        any request"""
        blade = _blade(mapping=None)
        params = _base_params(name=name, state=state)
        if state == "absent":
            params["policies"] = None
        module = _run(params, blade, check_mode=check_mode)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "name is empty" in msg
        assert "role" in msg
        module.exit_json.assert_not_called()
        module.get_system.assert_not_called()
        blade.get_directory_services_roles.assert_not_called()
        _no_writes(blade)

    def test_main_empty_name_defaults_to_role(self):
        """An empty name still addresses the built-in mapping of role"""
        blade = _blade(
            mapping=_mapping(
                group="readonly-users",
                group_base="OU=RBAC-Groups",
                policies=("readonly",),
            )
        )
        module = _run(
            _base_params(
                name="", role="readonly", policies=None, group=None, group_base=None
            ),
            blade,
        )
        module.fail_json.assert_not_called()
        blade.get_directory_services_roles.assert_called_once_with(names=["readonly"])
        module.exit_json.assert_called_once_with(changed=False)
        _no_writes(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_main_refuses_list_of_names(self, state, check_mode):
        """A name the array reads as two mappings is refused before any
        request, so no second mapping is read, changed or deleted"""
        # The array answers such a lookup with every mapping named in it.
        blade = _blade(mapping=_mapping())
        blade.get_directory_services_roles.return_value = _response(
            200, [_mapping(), _mapping(group="cc44-other")]
        )
        params = _base_params(name="cc44-map,cc44-other", state=state)
        if state == "absent":
            params["policies"] = None
        module = _run(params, blade, check_mode=check_mode)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "cc44-map,cc44-other" in msg
        assert "more than one mapping" in msg
        module.exit_json.assert_not_called()
        module.get_system.assert_not_called()
        blade.get_directory_services_roles.assert_not_called()
        _no_writes(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_main_refuses_list_in_policies_entry(self, check_mode):
        """An entry of policies the array reads as two policies is refused
        before any request"""
        blade = _blade(mapping=_mapping())
        module = _run(
            _base_params(policies=["readonly,storage_admin"]),
            blade,
            check_mode=check_mode,
        )
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "readonly,storage_admin" in msg
        assert "entry of its own" in msg
        module.exit_json.assert_not_called()
        module.get_system.assert_not_called()
        blade.get_directory_services_roles.assert_not_called()
        _no_writes(blade)

    def test_main_name_list_is_refused_before_realm_name(self):
        """A list of realm-qualified names gets the message about the list"""
        blade = _blade(mapping=None)
        module = _run(_base_params(name="realm1::a,realm1::b"), blade)
        module.fail_json.assert_called_once()
        assert "more than one mapping" in module.fail_json.call_args[1]["msg"]
        module.get_system.assert_not_called()

    # ---------------- main(): realms ----------------

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_main_refuses_realm_qualified_name(self, state, check_mode):
        """A realm-qualified mapping name is refused before any request"""
        blade = _blade(mapping=None)
        params = _base_params(name="realm1::cc44-map", state=state)
        if state == "absent":
            params["policies"] = None
        module = _run(params, blade, check_mode=check_mode)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "realm1::cc44-map" in msg
        assert "mappings are array-level" in msg
        assert "policies" in msg
        module.exit_json.assert_not_called()
        module.get_system.assert_not_called()
        blade.get_directory_services_roles.assert_not_called()
        _no_writes(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_main_refuses_realm_qualified_policy(self, check_mode):
        """A realm-qualified policy name is refused before any request"""
        blade = _blade(mapping=_mapping())
        module = _run(
            _base_params(policies=["readonly", "realm1::realm1-admin"]),
            blade,
            check_mode=check_mode,
        )
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "realm1::realm1-admin" in msg
        assert "policies are array-level" in msg
        assert "without a realm prefix" in msg
        module.exit_json.assert_not_called()
        module.get_system.assert_not_called()
        blade.get_directory_services_roles.assert_not_called()
        _no_writes(blade)

    @pytest.mark.parametrize(
        "policy", ["realm1::realm1-admin", "readonly,storage_admin"]
    )
    def test_main_absent_does_not_read_policies(self, policy):
        """policies is not read for state=absent, so it is not refused there"""
        blade = _blade(mapping=_mapping())
        module = _run(_base_params(state="absent", policies=[policy]), blade)
        module.fail_json.assert_not_called()
        blade.delete_directory_services_roles.assert_called_once_with(
            names=["cc44-map"]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_creates_mapping_granting_realm_scoped_policy(self):
        """A policy scoped to a realm is granted under its unqualified name"""
        blade = _blade(mapping=None)
        with patch(MODULE + ".DirectoryServiceRolePost") as mock_post, patch(
            MODULE + ".ReferenceWritable", side_effect=_fake_reference
        ):
            module = _run(
                _base_params(name="realm1-admins", policies=["realm1-admin"]), blade
            )
        module.fail_json.assert_not_called()
        module.get_system.assert_called_once()
        blade.get_directory_services_roles.assert_called_once_with(
            names=["realm1-admins"]
        )
        assert blade.post_directory_services_roles.call_args[1]["names"] == [
            "realm1-admins"
        ]
        mock_post.assert_called_once_with(
            group="cc44-grp",
            group_base="ou=groups",
            management_access_policies=[("ref", "realm1-admin")],
        )
        module.exit_json.assert_called_once_with(changed=True)

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_main_refused_read_is_not_a_missing_mapping(self, state, check_mode):
        """A read the array refuses, as it does for an administrator limited
        to a realm, fails with the array's message in every state"""
        blade = _blade()
        blade.get_directory_services_roles.return_value = _response(
            400, error=NOT_PERMITTED
        )
        module = _run(_base_params(state=state), blade, check_mode=check_mode)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Fetch Directory Service Role cc44-map failed" in msg
        assert NOT_PERMITTED in msg
        module.exit_json.assert_not_called()
        _no_writes(blade)
