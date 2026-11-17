# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_object_role module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from contextlib import ExitStack
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

from plugins.modules.purefb_object_role import (
    main,
    _context_kwargs,
    _desired_policy_changes,
    _duration_to_ms,
    _qualify_policy,
    _role_facts,
)

MODULE = "plugins.modules.purefb_object_role"
ACCOUNT = "acme"
ROLE = "analytics"
FULL = "acme/analytics"
READ = "pure:policy/object-read"
LIST = "pure:policy/object-list"
MISSING = "Object store account does not exist."


def _base_params(**overrides):
    params = {
        "name": ROLE,
        "account": ACCOUNT,
        "state": "present",
        "max_session_duration": None,
        "access_policies": None,
        "remove_access_policies": None,
        "exclusive": False,
        "context": "",
    }
    params.update(overrides)
    return params


def _module(check_mode=False, **overrides):
    module = Mock()
    module.params = _base_params(**overrides)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _response(status=200, items=None):
    response = Mock()
    response.status_code = status
    response.items = items if items is not None else []
    return response


def _role(duration=3600000):
    role = Mock()
    role.name = FULL
    role.account = Mock()
    role.account.name = ACCOUNT
    role.prn = "prn:pure:fb:test:role/" + FULL
    role.max_session_duration = duration
    role.trusted_entities = []
    return role


def _link(policy):
    link = Mock()
    link.member = Mock()
    link.member.name = FULL
    link.policy = Mock()
    link.policy.name = policy
    return link


def _blade(role=None, attached=(), account=True, policies_valid=True):
    blade = Mock()
    blade.get_fleets.return_value = _response(400)
    blade.get_object_store_accounts.return_value = _response(
        200 if account else 400, [Mock()] if account else []
    )
    if role is None:
        blade.get_object_store_roles.return_value = _response(400)
    else:
        blade.get_object_store_roles.return_value = _response(200, [role])
    blade.get_object_store_roles_object_store_access_policies.return_value = _response(
        200, [_link(policy) for policy in attached]
    )
    blade.get_object_store_access_policies.return_value = _response(
        200 if policies_valid else 400, [Mock()] if policies_valid else []
    )
    blade.post_object_store_roles.return_value = _response(200)
    blade.patch_object_store_roles.return_value = _response(200)
    blade.delete_object_store_roles.return_value = _response(200)
    blade.post_object_store_roles_object_store_access_policies.return_value = _response(
        200
    )
    blade.delete_object_store_roles_object_store_access_policies.return_value = (
        _response(200)
    )
    return blade


def _run_main(module, blade, gate_fails=False, has_sdk=True, error=MISSING):
    """Run main() with the module surroundings patched; returns the model mocks."""
    with ExitStack() as stack:
        stack.enter_context(patch(MODULE + ".AnsibleModule", return_value=module))
        stack.enter_context(patch(MODULE + ".get_system", return_value=blade))
        stack.enter_context(patch(MODULE + ".get_error_message", return_value=error))
        loose = stack.enter_context(patch(MODULE + ".LooseVersion"))
        role_model = stack.enter_context(patch(MODULE + ".ObjectStoreRole"))
        post_model = stack.enter_context(patch(MODULE + ".ObjectStoreRolePost"))
        stack.enter_context(patch(MODULE + ".HAS_PYPURECLIENT", has_sdk))
        loose.return_value.__gt__ = Mock(return_value=gate_fails)
        with pytest.raises(SystemExit):
            main()
    return role_model, post_model


class TestHelpers:
    """Helper-function unit tests"""

    def test_context_kwargs_empty_without_context(self):
        module = Mock()
        module.params = {"context": ""}
        assert _context_kwargs(module) == {}

    def test_context_kwargs_set(self):
        module = Mock()
        module.params = {"context": "peer1"}
        assert _context_kwargs(module) == {"context_names": ["peer1"]}

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("1h", 3600000),
            ("2H", 7200000),
            ("90m", 5400000),
            ("3600s", 3600000),
            ("7200000", 7200000),
            (7200000, 7200000),
            ("12h", 43200000),
        ],
    )
    def test_duration_to_ms_accepts_units_and_milliseconds(self, value, expected):
        module = _module()
        assert _duration_to_ms(module, value) == expected
        module.fail_json.assert_not_called()

    @pytest.mark.parametrize("value", ["1d", "abc", "1.5h", "", "h"])
    def test_duration_to_ms_rejects_bad_format(self, value):
        module = _module()
        with pytest.raises(SystemExit):
            _duration_to_ms(module, value)
        assert "Invalid max_session_duration" in module.fail_json.call_args[1]["msg"]

    @pytest.mark.parametrize("value", ["30m", "13h", "3599999", "0"])
    def test_duration_to_ms_rejects_out_of_range(self, value):
        module = _module()
        with pytest.raises(SystemExit):
            _duration_to_ms(module, value)
        assert "between 1h and 12h" in module.fail_json.call_args[1]["msg"]

    def test_qualify_policy_passes_builtin_and_qualified_names(self):
        module = _module()
        assert _qualify_policy(module, READ) == READ
        assert _qualify_policy(module, "other/policy") == "other/policy"

    def test_qualify_policy_prefixes_bare_name_with_account(self):
        module = _module()
        assert _qualify_policy(module, "reports") == ACCOUNT + "/reports"

    def test_desired_policy_changes_additive_by_default(self):
        module = _module(access_policies=[READ, "reports"])
        to_attach, to_detach = _desired_policy_changes(module, [READ, LIST])
        assert to_attach == [ACCOUNT + "/reports"]
        assert to_detach == []

    def test_desired_policy_changes_exclusive_detaches_extras(self):
        module = _module(access_policies=[READ], exclusive=True)
        to_attach, to_detach = _desired_policy_changes(module, [READ, LIST])
        assert to_attach == []
        assert to_detach == [LIST]

    def test_desired_policy_changes_exclusive_without_wanted_detaches_all(self):
        module = _module(exclusive=True)
        to_attach, to_detach = _desired_policy_changes(module, [READ, LIST])
        assert to_attach == []
        assert to_detach == [READ, LIST]

    def test_desired_policy_changes_remove_only_when_attached(self):
        module = _module(remove_access_policies=[READ, LIST])
        to_attach, to_detach = _desired_policy_changes(module, [LIST])
        assert to_attach == []
        assert to_detach == [LIST]

    def test_desired_policy_changes_clash_fails(self):
        module = _module(access_policies=[READ], remove_access_policies=[READ])
        with pytest.raises(SystemExit):
            _desired_policy_changes(module, [])
        assert "both access_policies" in module.fail_json.call_args[1]["msg"]

    def test_role_facts_maps_fields(self):
        module = _module()
        role = _role(7200000)
        entity = Mock()
        entity.name = "idp1"
        role.trusted_entities = [entity]
        facts = _role_facts(module, role, [READ])
        assert facts == {
            "name": FULL,
            "account": ACCOUNT,
            "prn": "prn:pure:fb:test:role/" + FULL,
            "max_session_duration": 7200000,
            "trusted_entities": ["idp1"],
            "access_policies": [READ],
        }

    def test_role_facts_tolerates_missing_role(self):
        module = _module()
        facts = _role_facts(module, None, [])
        assert facts["name"] == FULL
        assert facts["account"] == ACCOUNT
        assert facts["trusted_entities"] == []


class TestPurefbObjectRole:
    """main() flows"""

    # ---------------- create ----------------

    def test_create_with_default_duration(self):
        module = _module()
        role = _role()
        blade = _blade(role=None)
        blade.get_object_store_roles.side_effect = [
            _response(400),
            _response(200, [role]),
        ]

        role_model, post_model = _run_main(module, blade)

        post_model.assert_called_once_with()
        blade.post_object_store_roles.assert_called_once()
        kwargs = blade.post_object_store_roles.call_args[1]
        assert kwargs["names"] == [FULL]
        assert kwargs["object_store_role"] is post_model.return_value
        assert "context_names" not in kwargs
        blade.post_object_store_roles_object_store_access_policies.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["role"]["name"] == FULL
        assert result["role"]["max_session_duration"] == 3600000
        assert result["role"]["access_policies"] == []

    def test_create_with_duration_policies_and_context(self):
        module = _module(
            max_session_duration="4h", access_policies=[READ, LIST], context="fb1"
        )
        role = _role(14400000)
        blade = _blade(role=None)
        blade.get_object_store_roles.side_effect = [
            _response(400),
            _response(200, [role]),
        ]
        blade.get_object_store_roles_object_store_access_policies.return_value = (
            _response(200, [_link(READ), _link(LIST)])
        )

        role_model, post_model = _run_main(module, blade)

        post_model.assert_called_once_with(max_session_duration=14400000)
        assert blade.post_object_store_roles.call_args[1]["context_names"] == ["fb1"]
        assert blade.get_object_store_access_policies.call_count == 2
        link_calls = (
            blade.post_object_store_roles_object_store_access_policies.call_args_list
        )
        assert [c[1]["policy_names"] for c in link_calls] == [[READ], [LIST]]
        assert all(c[1]["member_names"] == [FULL] for c in link_calls)
        assert all(c[1]["context_names"] == ["fb1"] for c in link_calls)
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["role"]["max_session_duration"] == 14400000
        assert result["role"]["access_policies"] == [READ, LIST]

    def test_create_check_mode_writes_nothing(self):
        module = _module(check_mode=True, access_policies=[READ])
        blade = _blade(role=None)

        _run_main(module, blade)

        blade.post_object_store_roles.assert_not_called()
        blade.post_object_store_roles_object_store_access_policies.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["role"]["name"] == FULL
        assert result["role"]["access_policies"] == [READ]

    def test_create_api_error_fails(self):
        module = _module()
        blade = _blade(role=None)
        blade.post_object_store_roles.return_value = _response(400)

        _run_main(module, blade)

        module.fail_json.assert_called_once()
        assert (
            "Failed to create object store role " + FULL
            in module.fail_json.call_args[1]["msg"]
        )

    def test_create_unknown_policy_fails_before_post(self):
        module = _module(access_policies=["pure:policy/no-such"])
        blade = _blade(role=None, policies_valid=False)

        _run_main(module, blade)

        blade.post_object_store_roles.assert_not_called()
        assert (
            "Access policy pure:policy/no-such does not exist"
            in module.fail_json.call_args[1]["msg"]
        )

    # ---------------- present on an existing role ----------------

    def test_present_idempotent(self):
        module = _module(max_session_duration="1h", access_policies=[READ])
        blade = _blade(role=_role(3600000), attached=[READ])

        _run_main(module, blade)

        blade.patch_object_store_roles.assert_not_called()
        blade.post_object_store_roles.assert_not_called()
        blade.post_object_store_roles_object_store_access_policies.assert_not_called()
        blade.delete_object_store_roles_object_store_access_policies.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is False
        assert result["role"]["access_policies"] == [READ]

    def test_present_without_duration_leaves_it_alone(self):
        module = _module()
        blade = _blade(role=_role(7200000))

        _run_main(module, blade)

        blade.patch_object_store_roles.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is False
        assert result["role"]["max_session_duration"] == 7200000

    def test_update_duration_patches_only_that_field(self):
        module = _module(max_session_duration="2h")
        blade = _blade(role=_role(3600000))
        blade.get_object_store_roles.side_effect = [
            _response(200, [_role(3600000)]),
            _response(200, [_role(7200000)]),
        ]

        role_model, post_model = _run_main(module, blade)

        role_model.assert_called_once_with(max_session_duration=7200000)
        blade.patch_object_store_roles.assert_called_once()
        kwargs = blade.patch_object_store_roles.call_args[1]
        assert kwargs["names"] == [FULL]
        assert kwargs["object_store_role"] is role_model.return_value
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["role"]["max_session_duration"] == 7200000

    def test_update_duration_check_mode(self):
        module = _module(check_mode=True, max_session_duration="7200000")
        blade = _blade(role=_role(3600000))

        _run_main(module, blade)

        blade.patch_object_store_roles.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["role"]["max_session_duration"] == 7200000

    def test_update_duration_api_error_fails(self):
        module = _module(max_session_duration="2h")
        blade = _blade(role=_role(3600000))
        blade.patch_object_store_roles.return_value = _response(400)

        _run_main(module, blade)

        module.fail_json.assert_called_once()
        assert (
            "Failed to update object store role " + FULL
            in module.fail_json.call_args[1]["msg"]
        )

    def test_attach_only_missing_policy(self):
        module = _module(access_policies=[READ, LIST])
        blade = _blade(role=_role(), attached=[READ])
        blade.get_object_store_roles_object_store_access_policies.side_effect = [
            _response(200, [_link(READ)]),
            _response(200, [_link(READ), _link(LIST)]),
        ]

        _run_main(module, blade)

        blade.post_object_store_roles_object_store_access_policies.assert_called_once()
        kwargs = blade.post_object_store_roles_object_store_access_policies.call_args[1]
        assert kwargs["member_names"] == [FULL]
        assert kwargs["policy_names"] == [LIST]
        blade.delete_object_store_roles_object_store_access_policies.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["role"]["access_policies"] == [READ, LIST]

    def test_attach_check_mode(self):
        module = _module(check_mode=True, access_policies=[LIST])
        blade = _blade(role=_role(), attached=[READ])

        _run_main(module, blade)

        blade.post_object_store_roles_object_store_access_policies.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["role"]["access_policies"] == [READ, LIST]

    def test_attach_api_error_fails(self):
        module = _module(access_policies=[LIST])
        blade = _blade(role=_role(), attached=[])
        blade.post_object_store_roles_object_store_access_policies.return_value = (
            _response(400)
        )

        _run_main(module, blade)

        assert (
            "Failed to attach access policy " + LIST
            in module.fail_json.call_args[1]["msg"]
        )

    def test_remove_access_policies_detaches(self):
        module = _module(remove_access_policies=[READ])
        blade = _blade(role=_role(), attached=[READ, LIST])
        blade.get_object_store_roles_object_store_access_policies.side_effect = [
            _response(200, [_link(READ), _link(LIST)]),
            _response(200, [_link(LIST)]),
        ]

        _run_main(module, blade)

        blade.delete_object_store_roles_object_store_access_policies.assert_called_once()
        kwargs = blade.delete_object_store_roles_object_store_access_policies.call_args[
            1
        ]
        assert kwargs["member_names"] == [FULL]
        assert kwargs["policy_names"] == [READ]
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["role"]["access_policies"] == [LIST]

    def test_remove_access_policies_idempotent(self):
        module = _module(remove_access_policies=[READ])
        blade = _blade(role=_role(), attached=[LIST])

        _run_main(module, blade)

        blade.delete_object_store_roles_object_store_access_policies.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_exclusive_detaches_extras(self):
        module = _module(access_policies=[LIST], exclusive=True)
        blade = _blade(role=_role(), attached=[READ, LIST])
        blade.get_object_store_roles_object_store_access_policies.side_effect = [
            _response(200, [_link(READ), _link(LIST)]),
            _response(200, [_link(LIST)]),
        ]

        _run_main(module, blade)

        blade.post_object_store_roles_object_store_access_policies.assert_not_called()
        kwargs = blade.delete_object_store_roles_object_store_access_policies.call_args[
            1
        ]
        assert kwargs["policy_names"] == [READ]
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["role"]["access_policies"] == [LIST]

    def test_detach_api_error_fails(self):
        module = _module(remove_access_policies=[READ])
        blade = _blade(role=_role(), attached=[READ])
        blade.delete_object_store_roles_object_store_access_policies.return_value = (
            _response(400)
        )

        _run_main(module, blade)

        assert (
            "Failed to detach access policy " + READ
            in module.fail_json.call_args[1]["msg"]
        )

    def test_exclusive_without_access_policies_detaches_all(self):
        module = _module(exclusive=True)
        blade = _blade(role=_role(), attached=[READ, LIST])
        blade.get_object_store_roles_object_store_access_policies.side_effect = [
            _response(200, [_link(READ), _link(LIST)]),
            _response(200, []),
        ]

        _run_main(module, blade)

        blade.post_object_store_roles_object_store_access_policies.assert_not_called()
        calls = (
            blade.delete_object_store_roles_object_store_access_policies.call_args_list
        )
        assert [c[1]["policy_names"] for c in calls] == [[READ], [LIST]]
        assert all(c[1]["member_names"] == [FULL] for c in calls)
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["role"]["access_policies"] == []

    def test_list_attached_policies_error_fails(self):
        module = _module(max_session_duration="2h", access_policies=[LIST])
        blade = _blade(role=_role(), attached=[READ])
        blade.get_object_store_roles_object_store_access_policies.return_value = (
            _response(400)
        )

        _run_main(module, blade, error="Internal error")

        assert (
            "Failed to list access policies for role " + FULL
            in module.fail_json.call_args[1]["msg"]
        )
        blade.patch_object_store_roles.assert_not_called()
        blade.post_object_store_roles_object_store_access_policies.assert_not_called()
        blade.delete_object_store_roles_object_store_access_policies.assert_not_called()

    def test_present_account_missing_fails(self):
        module = _module()
        blade = _blade(role=None, account=False)

        _run_main(module, blade)

        blade.get_object_store_roles.assert_not_called()
        blade.post_object_store_roles.assert_not_called()
        assert (
            "Object store account acme does not exist"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_present_account_lookup_error_fails(self):
        module = _module()
        blade = _blade(role=None, account=False)

        _run_main(module, blade, error="Permission denied")

        blade.get_object_store_roles.assert_not_called()
        blade.post_object_store_roles.assert_not_called()
        assert (
            "Failed to look up object store account acme. Error: Permission denied"
            in module.fail_json.call_args[1]["msg"]
        )

    # ---------------- absent ----------------

    def test_absent_deletes_role(self):
        module = _module(state="absent")
        blade = _blade(role=_role())

        _run_main(module, blade)

        blade.delete_object_store_roles.assert_called_once_with(names=[FULL])
        assert module.exit_json.call_args[1]["changed"] is True

    def test_absent_idempotent_when_role_missing(self):
        module = _module(state="absent")
        blade = _blade(role=None)

        _run_main(module, blade)

        blade.delete_object_store_roles.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_absent_idempotent_when_account_missing(self):
        module = _module(state="absent")
        blade = _blade(role=None, account=False)

        _run_main(module, blade)

        blade.get_object_store_roles.assert_not_called()
        blade.delete_object_store_roles.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_absent_role_lookup_error_fails(self):
        module = _module(state="absent")
        blade = _blade(role=None)

        _run_main(module, blade, error="Internal error")

        blade.delete_object_store_roles.assert_not_called()
        assert (
            "Failed to look up object store role " + FULL + ". Error: Internal error"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_absent_check_mode_skips_delete(self):
        module = _module(check_mode=True, state="absent")
        blade = _blade(role=_role())

        _run_main(module, blade)

        blade.delete_object_store_roles.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_absent_api_error_fails(self):
        module = _module(state="absent")
        blade = _blade(role=_role())
        blade.delete_object_store_roles.return_value = _response(400)

        _run_main(module, blade)

        assert (
            "Failed to delete object store role " + FULL
            in module.fail_json.call_args[1]["msg"]
        )

    # ---------------- gates ----------------

    def test_version_gate_fails_before_any_call(self):
        module = _module()
        blade = _blade(role=None)

        _run_main(module, blade, gate_fails=True)

        module.fail_json.assert_called_once()
        assert "REST version not supported" in module.fail_json.call_args[1]["msg"]
        blade.get_object_store_accounts.assert_not_called()
        blade.post_object_store_roles.assert_not_called()

    def test_bad_duration_fails_before_any_write(self):
        module = _module(max_session_duration="13h")
        blade = _blade(role=None)

        _run_main(module, blade)

        assert "between 1h and 12h" in module.fail_json.call_args[1]["msg"]
        blade.post_object_store_roles.assert_not_called()

    def test_fails_without_sdk(self):
        module = _module()
        blade = _blade(role=None)

        _run_main(module, blade, has_sdk=False)

        module.fail_json.assert_called_once()
        assert "py-pure-client" in module.fail_json.call_args[1]["msg"]

    def test_fleet_member_defaults_context_to_local_array(self):
        module = _module()
        blade = _blade(role=_role())
        blade.get_fleets.return_value = _response(200, [Mock()])
        local = Mock()
        local.name = "fb-local"
        blade.get_arrays.return_value = _response(200, [local])

        _run_main(module, blade)

        assert module.params["context"] == "fb-local"
        kwargs = blade.get_object_store_roles.call_args[1]
        assert kwargs["context_names"] == ["fb-local"]
