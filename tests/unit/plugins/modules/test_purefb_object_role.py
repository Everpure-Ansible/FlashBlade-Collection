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
    _policies_to_validate,
    _qualify_policy,
    _requested_policies,
    _role_facts,
)

MODULE = "plugins.modules.purefb_object_role"
ACCOUNT = "acme"
ROLE = "analytics"
FULL = "acme/analytics"
RACCOUNT = "realm1::acme"
RFULL = "realm1::acme/analytics"
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


def _role(duration=3600000, account=ACCOUNT):
    role = Mock()
    role.name = account + "/" + ROLE
    role.account = Mock()
    role.account.name = account
    role.prn = "prn:pure:fb:test:role/" + account + "/" + ROLE
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


def _account_id(name):
    """One ID per account: the array resolves names without regard to case."""
    return "id-" + name.lower()


def _account(name, ids=True):
    """An object store account as the array returns it, in its own spelling."""
    account = Mock()
    account.id = _account_id(name) if ids else None
    account.name = name.lower()
    return account


def _policy(name, owners=None, ids=True):
    """An access policy as the array returns it.

    A built-in policy has an account reference without values. Any other
    policy belongs to the account its name starts with, unless owners says
    otherwise, and its account reference carries the ID and the name of
    that account. ids=False leaves the ID out of the reference.
    """
    policy = Mock()
    policy.name = name
    if owners and name in owners:
        owner = owners[name]
    elif name.startswith("pure:policy/"):
        owner = None
    else:
        owner = name.rpartition("/")[0]
    policy.account = Mock()
    policy.account.id = _account_id(owner) if owner and ids else None
    policy.account.name = owner.lower() if owner else None
    return policy


def _blade(
    role=None, attached=(), account=True, policies_valid=True, owners=None, ids=True
):
    blade = Mock()
    blade.get_fleets.return_value = _response(400)

    def account_lookup(names, **kwargs):
        if not account:
            return _response(400)
        return _response(200, [_account(names[0], ids)])

    blade.get_object_store_accounts.side_effect = account_lookup
    if role is None:
        blade.get_object_store_roles.return_value = _response(400)
    else:
        blade.get_object_store_roles.return_value = _response(200, [role])
    blade.get_object_store_roles_object_store_access_policies.return_value = _response(
        200, [_link(policy) for policy in attached]
    )

    def lookup(names, **kwargs):
        if not policies_valid:
            return _response(400)
        return _response(200, [_policy(name, owners, ids) for name in names])

    blade.get_object_store_access_policies.side_effect = lookup
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

    def test_requested_policies_qualifies_and_dedupes(self):
        module = _module(
            remove_access_policies=["reports", READ, "reports", ACCOUNT + "/reports"]
        )
        assert _requested_policies(module, "remove_access_policies") == [
            ACCOUNT + "/reports",
            READ,
        ]

    def test_requested_policies_empty_when_unset(self):
        module = _module()
        assert _requested_policies(module, "access_policies") == []

    def test_policies_to_validate_adds_unattached_removals_only(self):
        module = _module(remove_access_policies=[READ, LIST])
        assert _policies_to_validate(module, [READ], [ACCOUNT + "/new"]) == [
            ACCOUNT + "/new",
            LIST,
        ]

    def test_policies_to_validate_without_removals(self):
        module = _module(access_policies=[READ])
        assert _policies_to_validate(module, [], [READ]) == [READ]

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

    def test_create_unknown_remove_policy_fails_before_post(self):
        module = _module(remove_access_policies=["pure:policy/no-such"])
        blade = _blade(role=None, policies_valid=False)

        _run_main(module, blade)

        blade.post_object_store_roles.assert_not_called()
        assert (
            "Access policy pure:policy/no-such does not exist"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_create_with_known_remove_policy_only_checks_it(self):
        module = _module(remove_access_policies=[LIST])
        blade = _blade(role=None)
        blade.get_object_store_roles.side_effect = [
            _response(400),
            _response(200, [_role()]),
        ]

        _run_main(module, blade)

        blade.get_object_store_access_policies.assert_called_once()
        assert blade.get_object_store_access_policies.call_args[1]["names"] == [LIST]
        blade.post_object_store_roles.assert_called_once()
        blade.delete_object_store_roles_object_store_access_policies.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_policy_clash_fails_before_post(self):
        module = _module(access_policies=[READ], remove_access_policies=[READ])
        blade = _blade(role=None)

        _run_main(module, blade)

        blade.post_object_store_roles.assert_not_called()
        blade.get_object_store_access_policies.assert_not_called()
        assert "both access_policies" in module.fail_json.call_args[1]["msg"]

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

        # the unattached name is validated, then nothing is written
        blade.get_object_store_access_policies.assert_called_once()
        assert blade.get_object_store_access_policies.call_args[1]["names"] == [READ]
        blade.delete_object_store_roles_object_store_access_policies.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False
        module.warn.assert_not_called()

    def test_remove_attached_policy_skips_existence_lookup(self):
        module = _module(remove_access_policies=[READ])
        blade = _blade(role=_role(), attached=[READ])
        blade.get_object_store_roles_object_store_access_policies.side_effect = [
            _response(200, [_link(READ)]),
            _response(200, []),
        ]

        _run_main(module, blade)

        blade.get_object_store_access_policies.assert_not_called()
        blade.delete_object_store_roles_object_store_access_policies.assert_called_once()
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["role"]["access_policies"] == []

    def test_remove_unknown_policy_fails_before_any_write(self):
        module = _module(
            max_session_duration="2h", remove_access_policies=["pure:policy/no-such"]
        )
        blade = _blade(role=_role(3600000), attached=[READ], policies_valid=False)

        _run_main(module, blade)

        blade.patch_object_store_roles.assert_not_called()
        blade.post_object_store_roles_object_store_access_policies.assert_not_called()
        blade.delete_object_store_roles_object_store_access_policies.assert_not_called()
        assert (
            "Access policy pure:policy/no-such does not exist"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_remove_unknown_bare_policy_fails_in_check_mode(self):
        module = _module(check_mode=True, remove_access_policies=["no-such"])
        blade = _blade(role=_role(), attached=[READ], policies_valid=False)

        _run_main(module, blade)

        module.exit_json.assert_not_called()
        assert (
            "Access policy acme/no-such does not exist"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_remove_known_unattached_with_exclusive_detaches_only_extras(self):
        module = _module(
            access_policies=[READ], remove_access_policies=["acme/x"], exclusive=True
        )
        blade = _blade(role=_role(), attached=[READ, LIST])
        blade.get_object_store_roles_object_store_access_policies.side_effect = [
            _response(200, [_link(READ), _link(LIST)]),
            _response(200, [_link(READ)]),
        ]

        _run_main(module, blade)

        blade.get_object_store_access_policies.assert_called_once()
        assert blade.get_object_store_access_policies.call_args[1]["names"] == [
            "acme/x"
        ]
        calls = (
            blade.delete_object_store_roles_object_store_access_policies.call_args_list
        )
        assert [c[1]["policy_names"] for c in calls] == [[LIST]]
        assert module.exit_json.call_args[1]["role"]["access_policies"] == [READ]

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


def _assert_nothing_written(blade):
    blade.post_object_store_roles.assert_not_called()
    blade.patch_object_store_roles.assert_not_called()
    blade.delete_object_store_roles.assert_not_called()
    blade.post_object_store_roles_object_store_access_policies.assert_not_called()
    blade.delete_object_store_roles_object_store_access_policies.assert_not_called()


class TestRealmChecks:
    """Accounts in a realm, a qualifier on the role name, policies of another account"""

    # ---------------- qualifier on the role name ----------------

    @pytest.mark.parametrize(
        "account, name",
        [
            (ACCOUNT, "realm1::analytics"),
            (RACCOUNT, "realm1::analytics"),
            (ACCOUNT, "acme/analytics"),
            (RACCOUNT, "realm1::acme/analytics"),
        ],
    )
    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize("check_mode", [True, False])
    def test_qualified_role_name_fails_before_any_call(
        self, check_mode, state, account, name
    ):
        module = _module(check_mode=check_mode, state=state, account=account, name=name)
        blade = _blade(role=None)

        _run_main(module, blade)

        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Invalid role name " in msg and name in msg
        assert "realm::account" in msg
        assert blade.mock_calls == []

    # ---------------- policy of another account ----------------

    @pytest.mark.parametrize(
        "account, policy, owner",
        [
            (RACCOUNT, "acme/reports", "acme"),
            (RACCOUNT, "realm1::other/reports", "realm1::other"),
            (RACCOUNT, "realm2::acme/reports", "realm2::acme"),
            (ACCOUNT, "realm1::acme/reports", "realm1::acme"),
            (ACCOUNT, "other/reports", "other"),
        ],
    )
    @pytest.mark.parametrize("check_mode", [True, False])
    def test_attach_policy_of_another_account_fails_before_any_write(
        self, check_mode, account, policy, owner
    ):
        module = _module(
            check_mode=check_mode,
            account=account,
            max_session_duration="2h",
            access_policies=[READ, policy],
        )
        blade = _blade(role=_role(account=account), attached=[])

        _run_main(module, blade)

        module.exit_json.assert_not_called()
        msg = module.fail_json.call_args[1]["msg"]
        assert (
            "Access policy {0} belongs to object store account {1}, not to {2}.".format(
                policy, owner, account
            )
            in msg
        )
        assert "(" + account + "/policy)" in msg
        _assert_nothing_written(blade)

    @pytest.mark.parametrize("key", ["access_policies", "remove_access_policies"])
    @pytest.mark.parametrize("check_mode", [True, False])
    def test_create_with_policy_of_another_account_fails_before_post(
        self, check_mode, key
    ):
        module = _module(
            check_mode=check_mode, account=RACCOUNT, **{key: ["acme/reports"]}
        )
        blade = _blade(role=None)

        _run_main(module, blade)

        module.exit_json.assert_not_called()
        assert (
            "belongs to object store account acme, not to realm1::acme"
            in module.fail_json.call_args[1]["msg"]
        )
        _assert_nothing_written(blade)

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_remove_policy_of_another_account_fails(self, check_mode):
        module = _module(
            check_mode=check_mode,
            account=RACCOUNT,
            remove_access_policies=["acme/reports"],
        )
        blade = _blade(
            role=_role(account=RACCOUNT), attached=[RACCOUNT + "/reports", READ]
        )

        _run_main(module, blade)

        module.exit_json.assert_not_called()
        assert (
            "belongs to object store account acme, not to realm1::acme"
            in module.fail_json.call_args[1]["msg"]
        )
        _assert_nothing_written(blade)

    def test_missing_policy_named_without_the_realm_prefix_gets_a_hint(self):
        module = _module(
            check_mode=True, account=RACCOUNT, access_policies=["Acme/reports"]
        )
        blade = _blade(role=_role(account=RACCOUNT), policies_valid=False)

        _run_main(module, blade)

        assert module.fail_json.call_args[1]["msg"] == (
            "Access policy Acme/reports does not exist. Policies of the "
            "account realm1::acme are named realm1::acme/policy."
        )
        _assert_nothing_written(blade)

    @pytest.mark.parametrize(
        "account, policy, looked_up",
        [
            (RACCOUNT, "pure:policy/no-such", "pure:policy/no-such"),
            (RACCOUNT, "no-such", "realm1::acme/no-such"),
            (RACCOUNT, "other/no-such", "other/no-such"),
            (ACCOUNT, "other/no-such", "other/no-such"),
        ],
    )
    def test_missing_policy_message_has_no_hint_otherwise(
        self, account, policy, looked_up
    ):
        module = _module(account=account, access_policies=[policy])
        blade = _blade(role=_role(account=account), policies_valid=False)

        _run_main(module, blade)

        assert module.fail_json.call_args[1]["msg"] == (
            "Access policy {0} does not exist.".format(looked_up)
        )
        _assert_nothing_written(blade)

    # ---------------- what the array accepts stays accepted ----------------

    def test_realm_account_create_uses_qualified_names(self):
        module = _module(
            account=RACCOUNT,
            max_session_duration="2h",
            access_policies=["reports", RACCOUNT + "/audit", READ],
        )
        blade = _blade(role=None)
        blade.get_object_store_roles.side_effect = [
            _response(400),
            _response(200, [_role(7200000, RACCOUNT)]),
        ]

        _run_main(module, blade)

        wanted = [[RACCOUNT + "/reports"], [RACCOUNT + "/audit"], [READ]]
        assert blade.get_object_store_accounts.call_args[1]["names"] == [RACCOUNT]
        assert blade.post_object_store_roles.call_args[1]["names"] == [RFULL]
        lookups = blade.get_object_store_access_policies.call_args_list
        assert [c[1]["names"] for c in lookups] == wanted
        links = (
            blade.post_object_store_roles_object_store_access_policies.call_args_list
        )
        assert [c[1]["policy_names"] for c in links] == wanted
        assert all(c[1]["member_names"] == [RFULL] for c in links)
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["role"]["name"] == RFULL
        assert result["role"]["account"] == RACCOUNT

    def test_realm_account_update_and_detach_use_qualified_names(self):
        module = _module(
            account=RACCOUNT,
            max_session_duration="2h",
            remove_access_policies=["reports"],
        )
        blade = _blade(role=_role(account=RACCOUNT), attached=[RACCOUNT + "/reports"])

        _run_main(module, blade)

        assert blade.patch_object_store_roles.call_args[1]["names"] == [RFULL]
        kwargs = blade.delete_object_store_roles_object_store_access_policies.call_args[
            1
        ]
        assert kwargs["member_names"] == [RFULL]
        assert kwargs["policy_names"] == [RACCOUNT + "/reports"]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_realm_account_absent_deletes_qualified_name(self):
        module = _module(account=RACCOUNT, state="absent")
        blade = _blade(role=_role(account=RACCOUNT))

        _run_main(module, blade)

        assert blade.delete_object_store_roles.call_args[1]["names"] == [RFULL]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_realm_account_create_check_mode_reports_qualified_names(self):
        module = _module(
            check_mode=True, account=RACCOUNT, access_policies=["reports", READ]
        )
        blade = _blade(role=None)

        _run_main(module, blade)

        _assert_nothing_written(blade)
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["role"]["name"] == RFULL
        assert result["role"]["account"] == RACCOUNT
        assert result["role"]["access_policies"] == [RACCOUNT + "/reports", READ]

    def test_role_name_with_the_characters_the_array_allows_is_not_refused(self):
        name = "a+b=c,d.e@f_g-h"
        module = _module(account=RACCOUNT, name=name)
        blade = _blade(role=None)

        _run_main(module, blade)

        assert blade.post_object_store_roles.call_args[1]["names"] == [
            RACCOUNT + "/" + name
        ]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_account_and_policy_in_another_spelling_are_accepted(self):
        """The array resolves names without regard to case and answers with
        its own spelling: the references still name the same account."""
        module = _module(
            account="Realm1::Acme", access_policies=["REALM1::ACME/reports"]
        )
        blade = _blade(role=_role(account=RACCOUNT))

        _run_main(module, blade)

        blade.post_object_store_roles_object_store_access_policies.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_owner_id_decides_when_the_names_are_spelled_differently(self):
        """Defensive, not an observed array shape: the same account ID is the
        same account, however the two references spell its name."""
        module = _module(account=RACCOUNT, access_policies=[RACCOUNT + "/reports"])
        blade = _blade(role=_role(account=RACCOUNT))
        policy = _policy(RACCOUNT + "/reports")
        policy.account.name = "acme"
        blade.get_object_store_access_policies.side_effect = None
        blade.get_object_store_access_policies.return_value = _response(200, [policy])

        _run_main(module, blade)

        blade.post_object_store_roles_object_store_access_policies.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    # References without an ID were not seen on the array. The names are
    # the fallback and are compared without regard to case.

    @pytest.mark.parametrize(
        "account, policy",
        [
            (RACCOUNT, RACCOUNT + "/reports"),
            ("Realm1::Acme", "REALM1::ACME/reports"),
            (ACCOUNT, ACCOUNT + "/reports"),
        ],
    )
    def test_without_ids_own_policy_is_accepted_by_name(self, account, policy):
        module = _module(account=account, access_policies=[policy])
        blade = _blade(role=_role(account=account.lower()), ids=False)

        _run_main(module, blade)

        blade.post_object_store_roles_object_store_access_policies.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    @pytest.mark.parametrize(
        "account, policy, owner",
        [
            (RACCOUNT, "acme/reports", "acme"),
            (ACCOUNT, "realm1::acme/reports", "realm1::acme"),
        ],
    )
    @pytest.mark.parametrize("check_mode", [True, False])
    def test_without_ids_policy_of_another_account_fails_by_name(
        self, check_mode, account, policy, owner
    ):
        module = _module(
            check_mode=check_mode, account=account, access_policies=[policy]
        )
        blade = _blade(role=_role(account=account), ids=False)

        _run_main(module, blade)

        module.exit_json.assert_not_called()
        assert (
            "belongs to object store account {0}, not to {1}.".format(owner, account)
            in module.fail_json.call_args[1]["msg"]
        )
        _assert_nothing_written(blade)

    @pytest.mark.parametrize("reference", ["empty", "missing"])
    def test_policy_without_an_owning_account_is_accepted(self, reference):
        module = _module(account=RACCOUNT, access_policies=["shared/reports"])
        blade = _blade(role=_role(account=RACCOUNT), owners={"shared/reports": None})
        if reference == "missing":
            policy = Mock()
            policy.account = None
            blade.get_object_store_access_policies.side_effect = None
            blade.get_object_store_access_policies.return_value = _response(
                200, [policy]
            )

        _run_main(module, blade)

        blade.post_object_store_roles_object_store_access_policies.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    # ---------------- added in review ----------------

    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize("check_mode", [True, False])
    def test_qualified_role_name_fails_before_the_login(self, check_mode, state):
        """get_system() logs in, which is the first request to the array: the
        role name is refused before it."""
        module = _module(check_mode=check_mode, state=state, name="realm1::analytics")
        with ExitStack() as stack:
            stack.enter_context(patch(MODULE + ".AnsibleModule", return_value=module))
            login = stack.enter_context(patch(MODULE + ".get_system"))
            version = stack.enter_context(patch(MODULE + ".get_rest_api_version"))
            stack.enter_context(patch(MODULE + ".HAS_PYPURECLIENT", True))
            with pytest.raises(SystemExit):
                main()

        login.assert_not_called()
        version.assert_not_called()
        module.exit_json.assert_not_called()
        assert "Invalid role name " in module.fail_json.call_args[1]["msg"]

    @pytest.mark.parametrize("given", [RACCOUNT, "REALM1::ACME"])
    def test_without_ids_the_spelling_of_the_array_is_compared_without_case(
        self, given
    ):
        """No IDs, and the array spells the account with capitals in both
        references: it is still the role's own account."""
        module = _module(account=given, access_policies=[given + "/reports"])
        blade = _blade(role=_role(account=RACCOUNT), ids=False)
        account = _account(given, ids=False)
        account.name = "Realm1::Acme"
        blade.get_object_store_accounts.side_effect = None
        blade.get_object_store_accounts.return_value = _response(200, [account])
        policy = _policy(given + "/reports", ids=False)
        policy.account.name = "Realm1::Acme"
        blade.get_object_store_access_policies.side_effect = None
        blade.get_object_store_access_policies.return_value = _response(200, [policy])

        _run_main(module, blade)

        module.fail_json.assert_not_called()
        blade.post_object_store_roles_object_store_access_policies.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True
