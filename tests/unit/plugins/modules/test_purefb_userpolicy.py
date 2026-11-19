# Copyright: (c) 2026, Pure Storage Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_userpolicy module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from types import SimpleNamespace
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

from plugins.module_utils.version import LooseVersion as RealLooseVersion
from plugins.modules.purefb_userpolicy import add_policy, list_policy, main

MOD = "plugins.modules.purefb_userpolicy"
REALM_ACCOUNT = "myrealm::myaccount"
REALM_USER = "myrealm::myaccount/myuser"
REALM_POLICY = "myrealm::myaccount/second-policy"
READ = "pure:policy/object-read"
LIST = "pure:policy/bucket-list"
REFUSED = "Operation not permitted."


def _make_module(context="array1", **overrides):
    module = Mock()
    module.check_mode = False
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.params = {
        "name": "myuser",
        "account": "myaccount",
        "policy": ["myaccount/second-policy"],
        "context": context,
        "state": "present",
    }
    module.params.update(overrides)
    return module


def _policy(name):
    policy = Mock()
    policy.name = name
    return policy


def _membership(policy_name):
    member = Mock()
    member.policy = _policy(policy_name)
    return member


def _ok(items):
    """A valid response: the items of the request."""
    items = list(items)
    return SimpleNamespace(status_code=200, items=items, total_item_count=len(items))


def _error(message):
    """An error response: it has errors and, like the SDK's, no items."""
    return SimpleNamespace(status_code=400, errors=[SimpleNamespace(message=message)])


def _error_message(response, default="Unknown error"):
    """What module_utils.common.get_error_message returns."""
    errors = list(getattr(response, "errors", None) or [])
    return errors[0].message if errors else default


def _ref(obj, resource_type):
    return SimpleNamespace(id=obj.id, name=obj.name, resource_type=resource_type)


class _Array:
    """The object store users and access policies of an array.

    It answers the way Purity//FB 4.8.8 does: names match without regard to
    case and come back in the stored spelling, an account policy carries its
    account and a built-in policy an empty one, the name of an object in a
    realm carries the realm prefix, a name the array cannot resolve is a 400,
    and a policy of another account is refused.
    """

    def __init__(self):
        self.accounts = {}
        self.users = {}
        self.policies = {}
        self.attached = []
        self.refuse = {}
        self.contexts = []
        blade = Mock()
        blade.get_fleets.side_effect = lambda **kwargs: _ok([])
        blade.get_object_store_users.side_effect = self._get_users
        blade.get_object_store_access_policies.side_effect = self._get_policies
        blade.get_object_store_access_policies_object_store_users.side_effect = (
            self._get_members
        )
        blade.get_object_store_users_object_store_access_policies.side_effect = (
            self._get_members
        )
        blade.post_object_store_access_policies_object_store_users.side_effect = (
            self._post
        )
        blade.delete_object_store_access_policies_object_store_users.side_effect = (
            self._delete
        )
        self.blade = blade
        self.post = blade.post_object_store_access_policies_object_store_users
        self.delete = blade.delete_object_store_access_policies_object_store_users

    def add_user(self, name):
        account = name.split("/")[0]
        if account not in self.accounts:
            self.accounts[account] = SimpleNamespace(
                id="account-{0}".format(len(self.accounts)), name=account
            )
        self.users[name.lower()] = SimpleNamespace(
            id="user-{0}".format(len(self.users)),
            name=name,
            account=_ref(self.accounts[account], "object-store-accounts"),
        )

    def add_policy(self, name):
        account = SimpleNamespace()
        if not name.startswith("pure:policy/"):
            account = _ref(self.accounts[name.split("/")[0]], "object-store-accounts")
        self.policies[name.lower()] = SimpleNamespace(
            id="policy-{0}".format(len(self.policies)), name=name, account=account
        )

    def attach(self, user, policy):
        self.attached.append((self.users[user.lower()], self.policies[policy.lower()]))

    def policies_of(self, user):
        owner = self.users[user.lower()]
        return [policy.name for member, policy in self.attached if member is owner]

    def _members(self, rows):
        return _ok(
            SimpleNamespace(
                member=_ref(user, "object-store-users"),
                policy=_ref(policy, "object-store-access-policies"),
            )
            for user, policy in rows
        )

    def _get_users(self, names=None, context_names=None):
        self.contexts.append(context_names)
        if "users" in self.refuse:
            return _error(self.refuse["users"])
        if names is None:
            return _ok(self.users.values())
        if names[0].lower() not in self.users:
            return _error("Object store user does not exist.")
        return _ok([self.users[names[0].lower()]])

    def _get_policies(self, names=None, context_names=None):
        self.contexts.append(context_names)
        if "policies" in self.refuse:
            return _error(self.refuse["policies"])
        if names is None:
            return _ok(self.policies.values())
        if names[0].lower() not in self.policies:
            return _error("Policy does not exist.")
        return _ok([self.policies[names[0].lower()]])

    def _get_members(self, member_names=None, policy_names=None, context_names=None):
        self.contexts.append(context_names)
        if "members" in self.refuse:
            return _error(self.refuse["members"])
        rows = list(self.attached)
        if member_names is not None:
            if member_names[0].lower() not in self.users:
                return _error("Member does not exist.")
            owner = self.users[member_names[0].lower()]
            rows = [row for row in rows if row[0] is owner]
        if policy_names is not None:
            if policy_names[0].lower() not in self.policies:
                return _error("Policy does not exist.")
            wanted = self.policies[policy_names[0].lower()]
            rows = [row for row in rows if row[1] is wanted]
        return self._members(rows)

    def _post(self, member_names=None, policy_names=None, context_names=None):
        self.contexts.append(context_names)
        if "post" in self.refuse:
            return _error(self.refuse["post"])
        user = self.users[member_names[0].lower()]
        policy = self.policies[policy_names[0].lower()]
        account = getattr(policy.account, "id", None)
        if account is not None and account != user.account.id:
            return _error("Cannot add policy to user in a different account.")
        assert (user, policy) not in self.attached, "attached a second time"
        self.attached.append((user, policy))
        return self._members([(user, policy)])

    def _delete(self, member_names=None, policy_names=None, context_names=None):
        self.contexts.append(context_names)
        if "delete" in self.refuse:
            return _error(self.refuse["delete"])
        row = (
            self.users[member_names[0].lower()],
            self.policies[policy_names[0].lower()],
        )
        assert row in self.attached, "removed a policy that was not attached"
        self.attached.remove(row)
        return SimpleNamespace(status_code=200)


def _array():
    """Accounts myaccount (array level), myrealm::myaccount and myrealm::other,
    each with a user myuser and a policy second-policy, plus built-in policies."""
    array = _Array()
    for account in ("myaccount", REALM_ACCOUNT, "myrealm::other"):
        array.add_user(account + "/myuser")
        array.add_policy(account + "/second-policy")
    for policy in (READ, LIST, "pure:policy/full-access"):
        array.add_policy(policy)
    return array


def _run(array, check_mode=False, api="2.30", context="", **params):
    """Run the module against the array and return the module mock."""
    module = _make_module(context=context, **params)
    module.check_mode = check_mode
    with patch(MOD + ".AnsibleModule", return_value=module), patch(
        MOD + ".get_system", return_value=array.blade
    ), patch(MOD + ".LooseVersion", RealLooseVersion), patch(
        MOD + ".get_rest_api_version", return_value=api
    ), patch(
        MOD + ".get_error_message", side_effect=_error_message
    ):
        try:
            main()
        except SystemExit:
            pass
    return module


def _exit(module):
    """Return what the module exited with; it must not have failed."""
    module.fail_json.assert_not_called()
    module.exit_json.assert_called_once()
    return module.exit_json.call_args[1]


def _failure(module):
    """Return the message the module failed with; it must not have exited."""
    module.exit_json.assert_not_called()
    module.fail_json.assert_called_once()
    return module.fail_json.call_args[1]["msg"]


class TestPurefbUserpolicyAddPolicy:
    """Regression tests for add_policy (issue #574)."""

    def test_add_issues_single_context_scoped_post(self):
        """On API >= 2.17 the add must issue exactly ONE context-scoped POST.

        Previously a second, non-context POST ran unconditionally (no else) and
        overwrote the checked result, so the context write was never verified and
        the membership silently failed to persist while still reporting changed.
        """
        array = _array()

        module = _run(array, context="array1")

        assert array.post.call_count == 1
        kwargs = array.post.call_args[1]
        assert kwargs.get("context_names") == ["array1"]
        assert kwargs.get("member_names") == ["myaccount/myuser"]
        assert kwargs.get("policy_names") == ["myaccount/second-policy"]
        assert _exit(module)["changed"] is True

    def test_add_is_idempotent_when_already_assigned(self):
        """If the policy is already assigned, no POST is issued and changed is False."""
        array = _array()
        array.attach("myaccount/myuser", "myaccount/second-policy")

        module = _run(array, context="array1")

        array.post.assert_not_called()
        assert _exit(module)["changed"] is False

    def test_add_then_remove_twice_at_array_level(self):
        """Array-level behaviour: changed, unchanged, changed, unchanged."""
        array = _array()
        policies = [READ, "myaccount/second-policy"]

        results = [
            _exit(_run(array, policy=policies)),
            _exit(_run(array, policy=policies)),
            _exit(_run(array, policy=policies, state="absent")),
            _exit(_run(array, policy=policies, state="absent")),
        ]

        assert [res["changed"] for res in results] == [True, False, True, False]
        assert array.post.call_count == 2
        assert array.delete.call_count == 2
        assert array.policies_of("myaccount/myuser") == []
        assert array.policies_of(REALM_USER) == []

    def test_direct_call_without_the_user_object(self):
        """add_policy() called without the user still attaches the policy."""
        array = _array()
        module = _make_module(context="")
        with patch(MOD + ".LooseVersion", RealLooseVersion), patch(
            MOD + ".get_rest_api_version", return_value="2.30"
        ):
            try:
                add_policy(module, array.blade)
            except SystemExit:
                pass

        assert _exit(module)["changed"] is True
        assert array.policies_of("myaccount/myuser") == ["myaccount/second-policy"]


class TestPurefbUserpolicyUnresolvedPolicy:
    """A policy the array cannot resolve fails the task with a message."""

    def test_add_unknown_policy(self):
        array = _array()

        module = _run(array, policy=["myaccount/nopol"])

        assert _failure(module) == "Access policy myaccount/nopol does not exist."
        array.post.assert_not_called()

    def test_add_unknown_policy_in_check_mode(self):
        array = _array()

        module = _run(array, check_mode=True, policy=["myaccount/nopol"])

        assert _failure(module) == "Access policy myaccount/nopol does not exist."

    def test_remove_unknown_policy(self):
        array = _array()

        module = _run(array, policy=["myaccount/nopol"], state="absent")

        assert _failure(module) == "Access policy myaccount/nopol does not exist."
        array.delete.assert_not_called()

    def test_realm_user_with_a_bare_policy_name_gets_the_realm_form(self):
        """second-policy exists in the account, but its name is realm::account/policy."""
        array = _array()

        module = _run(array, account=REALM_ACCOUNT, policy=["second-policy"])

        assert _failure(module) == (
            "Access policy second-policy does not exist. A policy of an account "
            "in a realm is named realm::account/policy."
        )
        array.post.assert_not_called()

    def test_realm_user_with_a_policy_of_an_unknown_realm(self):
        array = _array()
        policy = "zznorealm::myaccount/second-policy"

        module = _run(array, account=REALM_ACCOUNT, policy=[policy], state="absent")

        assert _failure(module) == "Access policy {0} does not exist.".format(policy)
        array.delete.assert_not_called()

    def test_nothing_is_attached_when_a_later_policy_is_unknown(self):
        array = _array()

        module = _run(array, policy=[READ, "myaccount/nopol", LIST])

        assert "myaccount/nopol does not exist" in _failure(module)
        array.post.assert_not_called()
        assert array.policies_of("myaccount/myuser") == []

    def test_nothing_is_removed_when_a_later_policy_is_unknown(self):
        array = _array()
        array.attach("myaccount/myuser", READ)

        module = _run(array, policy=[READ, "myaccount/nopol"], state="absent")

        assert "myaccount/nopol does not exist" in _failure(module)
        array.delete.assert_not_called()
        assert array.policies_of("myaccount/myuser") == [READ]


class TestPurefbUserpolicyRefusedReads:
    """A read the array refuses is reported with the array's message."""

    def test_policy_read_refused(self):
        array = _array()
        array.refuse["policies"] = REFUSED

        module = _run(array)

        msg = _failure(module)
        assert msg == (
            "Failed to get access policy myaccount/second-policy. Error: " + REFUSED
        )
        array.post.assert_not_called()

    def test_membership_read_refused_on_add(self):
        array = _array()
        array.refuse["members"] = REFUSED

        module = _run(array)

        assert _failure(module) == (
            "Failed to get access policies for account user myaccount/myuser. "
            "Error: " + REFUSED
        )
        array.post.assert_not_called()

    def test_membership_read_refused_on_remove(self):
        array = _array()
        array.attach("myaccount/myuser", "myaccount/second-policy")
        array.refuse["members"] = REFUSED

        module = _run(array, state="absent")

        assert REFUSED in _failure(module)
        array.delete.assert_not_called()

    def test_user_read_refused_is_not_reported_as_a_missing_user(self):
        array = _array()
        array.refuse["users"] = REFUSED

        module = _run(array)

        assert _failure(module) == (
            "Failed to get account user myaccount/myuser. Error: " + REFUSED
        )

    def test_missing_user(self):
        array = _array()

        module = _run(array, account="noaccount")

        assert _failure(module) == "Account User noaccount/myuser does not exist"
        array.post.assert_not_called()

    def test_bare_account_name_is_not_completed_with_a_realm(self):
        """myrealm::other2 exists, other2 does not: the bare name is not found."""
        array = _array()
        array.add_user("myrealm::other2/myuser")

        module = _run(array, account="other2", policy=[READ])

        assert _failure(module) == "Account User other2/myuser does not exist"
        assert array.policies_of("myrealm::other2/myuser") == []

    def test_show_all_refused(self):
        array = _array()
        array.refuse["policies"] = REFUSED

        module = _run(array, state="show", name=None, account=None, policy=None)

        assert _failure(module) == (
            "Failed to get Object Store User Access Policies. Error: " + REFUSED
        )

    def test_add_refused_by_the_array(self):
        array = _array()
        array.refuse["post"] = REFUSED

        module = _run(array)

        assert _failure(module) == (
            "Failed to add policy myaccount/second-policy to account user "
            "myaccount/myuser. Error: " + REFUSED
        )

    def test_remove_refused_by_the_array(self):
        array = _array()
        array.attach("myaccount/myuser", "myaccount/second-policy")
        array.refuse["delete"] = REFUSED

        module = _run(array, state="absent")

        assert _failure(module) == (
            "Failed to remove policy myaccount/second-policy from account user "
            "myaccount/myuser. Error: " + REFUSED
        )


class TestPurefbUserpolicyCheckMode:
    """Check mode sends nothing and reports what a run does."""

    def test_add_reports_changed_and_sends_nothing(self):
        array = _array()
        array.attach("myaccount/myuser", LIST)

        module = _run(array, check_mode=True, policy=[READ, "myaccount/second-policy"])

        result = _exit(module)
        assert result["changed"] is True
        assert result["policy_list"] == [LIST, READ, "myaccount/second-policy"]
        array.post.assert_not_called()
        assert array.policies_of("myaccount/myuser") == [LIST]

    def test_add_reports_unchanged_when_attached(self):
        array = _array()
        array.attach("myaccount/myuser", READ)

        module = _run(array, check_mode=True, policy=[READ])

        result = _exit(module)
        assert result["changed"] is False
        assert result["policy_list"] == [READ]

    def test_remove_reports_changed_and_sends_nothing(self):
        array = _array()
        array.attach("myaccount/myuser", LIST)
        array.attach("myaccount/myuser", READ)

        module = _run(array, check_mode=True, policy=[READ], state="absent")

        result = _exit(module)
        assert result["changed"] is True
        assert result["policy_list"] == [LIST]
        array.delete.assert_not_called()
        assert array.policies_of("myaccount/myuser") == [LIST, READ]

    def test_remove_reports_unchanged_when_not_attached(self):
        array = _array()
        array.attach("myaccount/myuser", LIST)

        module = _run(array, check_mode=True, policy=[READ], state="absent")

        result = _exit(module)
        assert result["changed"] is False
        assert result["policy_list"] == [LIST]

    def test_check_mode_and_run_agree_for_a_realm_user(self):
        array = _array()
        add = dict(account=REALM_ACCOUNT, policy=[READ, REALM_POLICY])
        remove = dict(state="absent", **add)

        results = [
            _exit(_run(array, check_mode=True, **add)),
            _exit(_run(array, **add)),
            _exit(_run(array, check_mode=True, **add)),
            _exit(_run(array, check_mode=True, **remove)),
            _exit(_run(array, **remove)),
            _exit(_run(array, check_mode=True, **remove)),
        ]

        assert [res["changed"] for res in results] == [
            True,
            True,
            False,
            True,
            True,
            False,
        ]
        assert results[0]["policy_list"] == results[1]["policy_list"]
        assert results[3]["policy_list"] == results[4]["policy_list"] == []


class TestPurefbUserpolicySameAccount:
    """The array refuses a policy of another account: so does the module,
    before it writes anything and in check mode too."""

    MESSAGE = (
        "Access policy {0} cannot be added to account user {1}: the user and "
        "the policy must belong to the same account."
    )

    def test_array_level_policy_on_a_realm_user(self):
        array = _array()

        module = _run(array, account=REALM_ACCOUNT)

        assert _failure(module) == self.MESSAGE.format(
            "myaccount/second-policy", REALM_USER
        )
        array.post.assert_not_called()

    def test_realm_policy_on_an_array_level_user(self):
        array = _array()

        module = _run(array, policy=[REALM_POLICY])

        assert _failure(module) == self.MESSAGE.format(REALM_POLICY, "myaccount/myuser")
        array.post.assert_not_called()

    def test_policy_of_another_account_of_the_realm_in_check_mode(self):
        array = _array()
        policy = "myrealm::other/second-policy"

        module = _run(array, check_mode=True, account=REALM_ACCOUNT, policy=[policy])

        assert _failure(module) == self.MESSAGE.format(policy, REALM_USER)

    def test_earlier_policies_stay_unattached(self):
        array = _array()

        module = _run(
            array, account=REALM_ACCOUNT, policy=[READ, "myaccount/second-policy"]
        )

        assert "must belong to the same account" in _failure(module)
        array.post.assert_not_called()
        assert array.policies_of(REALM_USER) == []

    def test_removing_a_policy_of_another_account_changes_nothing(self):
        """It cannot be attached, so there is nothing to remove."""
        array = _array()
        array.attach(REALM_USER, READ)

        module = _run(
            array,
            account=REALM_ACCOUNT,
            policy=["myaccount/second-policy"],
            state="absent",
        )

        result = _exit(module)
        assert result["changed"] is False
        assert result["policy_list"] == [READ]
        array.delete.assert_not_called()

    def test_built_in_policy_belongs_to_no_account(self):
        array = _array()

        module = _run(array, account=REALM_ACCOUNT, policy=[READ])

        assert _exit(module)["changed"] is True
        assert array.policies_of(REALM_USER) == [READ]


class TestPurefbUserpolicyRealm:
    """A user of an account in a realm: realm::account and realm::account/policy."""

    def test_add_and_remove_twice(self):
        array = _array()
        array.attach("myaccount/myuser", "myaccount/second-policy")
        task = dict(account=REALM_ACCOUNT, policy=[REALM_POLICY, READ])

        added = _exit(_run(array, **task))
        again = _exit(_run(array, **task))

        assert (added["changed"], again["changed"]) == (True, False)
        assert added["policy_list"] == again["policy_list"] == [REALM_POLICY, READ]
        assert [call[1] for call in array.post.call_args_list] == [
            dict(member_names=[REALM_USER], policy_names=[REALM_POLICY]),
            dict(member_names=[REALM_USER], policy_names=[READ]),
        ]

        removed = _exit(_run(array, state="absent", **task))
        again = _exit(_run(array, state="absent", **task))

        assert (removed["changed"], again["changed"]) == (True, False)
        assert removed["policy_list"] == again["policy_list"] == []
        assert [call[1] for call in array.delete.call_args_list] == [
            dict(member_names=[REALM_USER], policy_names=[REALM_POLICY]),
            dict(member_names=[REALM_USER], policy_names=[READ]),
        ]
        # the namesake at array level kept its own policy throughout
        assert array.policies_of("myaccount/myuser") == ["myaccount/second-policy"]

    def test_names_match_without_regard_to_case(self):
        array = _array()
        array.attach(REALM_USER, REALM_POLICY)

        module = _run(
            array,
            account=REALM_ACCOUNT.upper(),
            name="MYUSER",
            policy=[REALM_POLICY.upper(), READ.upper()],
        )

        result = _exit(module)
        assert result["changed"] is True
        assert array.post.call_count == 1
        assert array.post.call_args[1]["policy_names"] == [READ.upper()]
        # the names the array stores, not the spelling of the task
        assert result["policy_list"] == [REALM_POLICY, READ]

    def test_one_policy_named_twice_is_attached_once(self):
        array = _array()

        module = _run(
            array, account=REALM_ACCOUNT, policy=[REALM_POLICY, REALM_POLICY.upper()]
        )

        result = _exit(module)
        assert result["changed"] is True
        assert array.post.call_count == 1
        assert result["policy_list"] == [REALM_POLICY]

    def test_show_lists_the_full_names(self):
        array = _array()
        array.attach(REALM_USER, REALM_POLICY)
        array.attach(REALM_USER, READ)
        array.attach("myaccount/myuser", LIST)

        module = _run(array, account=REALM_ACCOUNT, state="show", policy=None)

        result = _exit(module)
        assert result["changed"] is False
        assert result["policy_list"] == [REALM_POLICY, READ]


class TestPurefbUserpolicyPolicyList:
    """policy_list is the list of the user's policies, each of them once."""

    def test_adding_several_policies_lists_each_once(self):
        array = _array()
        array.attach("myaccount/myuser", LIST)

        module = _run(array, policy=[READ, "myaccount/second-policy"])

        assert _exit(module)["policy_list"] == [LIST, READ, "myaccount/second-policy"]

    def test_unchanged_add_lists_the_policies_of_the_user(self):
        array = _array()
        array.attach("myaccount/myuser", LIST)
        array.attach("myaccount/myuser", READ)

        module = _run(array, policy=[READ])

        result = _exit(module)
        assert result["changed"] is False
        assert result["policy_list"] == [LIST, READ]

    def test_remove_lists_what_is_left(self):
        array = _array()
        array.attach("myaccount/myuser", LIST)
        array.attach("myaccount/myuser", READ)

        module = _run(array, policy=[READ], state="absent")

        result = _exit(module)
        assert result["changed"] is True
        assert result["policy_list"] == [LIST]


class TestPurefbUserpolicyContext:
    """The fleet context goes with every request, from REST 2.17 on."""

    def test_context_on_every_request(self):
        array = _array()

        _exit(_run(array, context="array1"))
        _exit(_run(array, context="array1", state="absent"))

        assert array.contexts
        assert all(context == ["array1"] for context in array.contexts)

    def test_no_context_before_rest_2_17(self):
        array = _array()

        _exit(_run(array, api="2.16", context="array1"))
        _exit(_run(array, api="2.16", context="array1", state="absent"))

        assert array.contexts
        assert all(context is None for context in array.contexts)
        array.blade.get_fleets.assert_not_called()


class TestPurefbUserpolicyShow:
    """state=show is read-only: it must list policies without reporting a change."""

    @patch("plugins.modules.purefb_userpolicy.LooseVersion")
    def test_show_user_policies_reports_no_change(self, mock_loose_version):
        module = _make_module(context="array1", state="show", policy=None)
        blade = Mock()
        blade.get_versions.return_value.items = ["2.17", "2.24"]
        res = blade.get_object_store_access_policies_object_store_users.return_value
        res.status_code = 200
        res.items = [
            _membership("pure:policy/full-access"),
            _membership("pure:policy/object-read"),
        ]
        mock_loose_version.return_value.__le__ = Mock(return_value=True)

        try:
            list_policy(module, blade)
        except SystemExit:
            pass

        kwargs = blade.get_object_store_access_policies_object_store_users.call_args[1]
        assert kwargs.get("member_names") == ["myaccount/myuser"]
        assert kwargs.get("context_names") == ["array1"]
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is False
        assert module.exit_json.call_args[1]["policy_list"] == [
            "pure:policy/full-access",
            "pure:policy/object-read",
        ]
        module.fail_json.assert_not_called()

    @patch("plugins.modules.purefb_userpolicy.LooseVersion")
    def test_show_all_policies_without_user_reports_no_change(self, mock_loose_version):
        """Array-wide show has no account/name; it must not build a user name."""
        module = _make_module(context="", state="show", name=None, account=None)
        module.params["policy"] = None
        blade = Mock()
        blade.get_versions.return_value.items = ["2.17", "2.24"]
        blade.get_object_store_access_policies.return_value.status_code = 200
        blade.get_object_store_access_policies.return_value.items = [
            _policy("pure:policy/full-access"),
            _policy("pure:policy/object-read"),
        ]
        mock_loose_version.return_value.__le__ = Mock(return_value=False)

        try:
            list_policy(module, blade)
        except SystemExit:
            pass

        blade.get_object_store_access_policies_object_store_users.assert_not_called()
        blade.get_object_store_access_policies.assert_called_once_with()
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is False
        assert module.exit_json.call_args[1]["policy_list"] == [
            "pure:policy/full-access",
            "pure:policy/object-read",
        ]

    @patch("plugins.modules.purefb_userpolicy.LooseVersion")
    @patch("plugins.modules.purefb_userpolicy.get_system")
    @patch("plugins.modules.purefb_userpolicy.AnsibleModule")
    def test_main_show_all_skips_user_lookup(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """main() used to concatenate account + name for the existence check even
        when both were None (array-wide show), which raised TypeError."""
        module = _make_module(context="", state="show", name=None, account=None)
        module.params["policy"] = None
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_versions.return_value.items = ["2.17", "2.24"]
        blade.get_object_store_access_policies.return_value.status_code = 200
        blade.get_object_store_access_policies.return_value.items = [
            _policy("pure:policy/full-access")
        ]
        mock_get_system.return_value = blade
        mock_loose_version.return_value.__le__ = Mock(return_value=False)

        try:
            main()
        except SystemExit:
            pass

        blade.get_object_store_users.assert_not_called()
        module.fail_json.assert_not_called()
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is False
        assert module.exit_json.call_args[1]["policy_list"] == [
            "pure:policy/full-access"
        ]
