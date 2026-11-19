# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_s3user module."""

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

from plugins.module_utils.version import LooseVersion as RealLooseVersion
from plugins.modules import purefb_s3user
from plugins.modules.purefb_s3user import main

MOD = "plugins.modules.purefb_s3user"

# Synthetic access key IDs; the array names a key of a user in a realm
# realm::<access key ID> and reports the bare ID as access_key_id.
KEY_A = "PSFBIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
KEY_B = "PSFBIBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
KEY_NONE = "PSFBINONENONENONENONENONENONENONENONENONE"
SECRET = "synthetic-secret-for-unit-tests"

NO_ACCOUNT = "Object store account does not exist."
NO_USER = "Object store user does not exist."
NO_KEY = "Access key does not exist."
KEY_REALM = "User and imported access key must belong to the same realm."
KEY_TAKEN = "The access key provided already belongs to a user."
POLICY_ACCOUNT = "Cannot add policy to user in a different account."
REFUSED = "Operation not permitted."
NO_NAME = "Missing or invalid parameter."
MANY_NAMES = "Cannot process more than one name at a time."
MANY_KEYS_PATCH = "Cannot update more than one access keys at a time."
MANY_KEYS_DELETE = "Cannot delete more than one access keys at a time."


def _params(**overrides):
    params = {
        "name": "user1",
        "account": "acc1",
        "access_key": False,
        "multiple_keys": False,
        "imported_key": None,
        "key_name": None,
        "enable_key": True,
        "imported_secret": None,
        "policy": None,
        "state": "present",
        "context": "",
    }
    params.update(overrides)
    return params


def _module(check_mode=False, **overrides):
    module = Mock()
    module.params = _params(**overrides)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _ok(items=None):
    """A 200 answer. Only a successful answer has items."""
    res = Mock(spec=["status_code", "items"])
    res.status_code = 200
    res.items = list(items or [])
    return res


def _error(message, status_code=400):
    """An error answer as the SDK returns it: errors, and no items at all."""
    res = Mock(spec=["status_code", "errors"])
    res.status_code = status_code
    error = Mock()
    error.message = message
    res.errors = [error]
    return res


def _error_message(res, default="Unknown error"):
    """What module_utils.common.get_error_message returns for an answer."""
    errors = getattr(res, "errors", None)
    return errors[0].message if errors else default


def _realm(name):
    return name.rpartition("::")[0]


def _named(name):
    item = Mock()
    item.name = name
    return item


def _key(name, user, enabled=True, secret=None):
    """An access key as GET /object-store-access-keys returns it."""
    key = Mock()
    key.name = name
    key.access_key_id = name.rpartition("::")[2]
    key.enabled = enabled
    key.secret_access_key = secret
    key.user = _named(user)
    return key


class _Array:
    """A small stateful stand-in for the array.

    Accounts, users and access keys are held by name; names are matched
    without regard to case and returned as stored, as the array does. A
    read by name of something that is not there answers 400 with the
    array's "does not exist" text. A generated access key of a user in a
    realm is named realm::<ID>; an import is refused when the name is not
    in the realm of the user or the name is taken. A comma separates
    names: a read of users or access keys answers every object on the
    list, and a request that would create a second user, or change or
    delete a second access key, is refused. refuse maps a blade method to
    a message: that call then answers 400 with it.
    """

    def __init__(self, accounts=("acc1",), users=(), keys=(), policies=()):
        self.accounts = list(accounts)
        self.users = list(users)
        self.keys = dict((key.name, key) for key in keys)
        self.policies = list(policies)
        self.attached = set()
        self.refuse = {}
        self.generated = 0
        blade = Mock()
        blade.get_fleets.side_effect = self._wrap("get_fleets", self._fleets)
        for method in (
            "get_object_store_accounts",
            "get_object_store_users",
            "post_object_store_users",
            "delete_object_store_users",
            "get_object_store_access_keys",
            "post_object_store_access_keys",
            "patch_object_store_access_keys",
            "delete_object_store_access_keys",
            "get_object_store_access_policies",
            "get_object_store_users_object_store_access_policies",
            "post_object_store_access_policies_object_store_users",
            "delete_object_store_access_policies_object_store_users",
        ):
            getattr(blade, method).side_effect = self._wrap(
                method, getattr(self, "_" + method)
            )
        self.blade = blade

    def _wrap(self, method, handler):
        def call(**kwargs):
            if method in self.refuse:
                return _error(self.refuse[method])
            return handler(**kwargs)

        return call

    @staticmethod
    def _find(names, wanted):
        for name in names:
            if name.lower() == wanted.lower():
                return name
        return None

    @staticmethod
    def _split(names):
        """The names of a request: the array reads a comma as a separator."""
        return [part for name in names for part in name.split(",")]

    def _fleets(self, **kwargs):
        return _ok([])

    def _get_object_store_accounts(self, **kwargs):
        if "" in kwargs["names"]:
            return _error(NO_NAME)
        found = self._find(self.accounts, kwargs["names"][0])
        return _ok([_named(found)]) if found else _error(NO_ACCOUNT)

    def _get_object_store_users(self, **kwargs):
        found = [self._find(self.users, name) for name in self._split(kwargs["names"])]
        if None in found:
            return _error(NO_USER)
        return _ok([_named(name) for name in self.users if name in found])

    def _post_object_store_users(self, **kwargs):
        if len(self._split(kwargs["names"])) > 1:
            return _error(MANY_NAMES)
        self.users.append(kwargs["names"][0])
        return _ok([_named(kwargs["names"][0])])

    def _delete_object_store_users(self, **kwargs):
        found = self._find(self.users, kwargs["names"][0])
        if not found:
            return _error(NO_USER)
        self.users.remove(found)
        for name in [n for n, k in self.keys.items() if k.user.name == found]:
            del self.keys[name]
        return _ok()

    def _get_object_store_access_keys(self, **kwargs):
        names = kwargs.get("names")
        if names is None:
            return _ok(self.keys.values())
        if "" in names:
            return _error(NO_NAME)
        found = [self._find(self.keys, name) for name in self._split(names)]
        if None in found:
            return _error(NO_KEY)
        return _ok([key for name, key in self.keys.items() if name in found])

    def _post_object_store_access_keys(self, **kwargs):
        body = kwargs["object_store_access_key"]
        user = self._find(self.users, body["user"]["name"])
        if not user:
            return _error(NO_USER)
        names = kwargs.get("names")
        if names:
            name = names[0]
            if _realm(name).lower() != _realm(user).lower():
                return _error(KEY_REALM)
            if self._find(self.keys, name):
                return _error(KEY_TAKEN)
            secret = None
        else:
            self.generated += 1
            name = "PSFBIGENERATED{0:04d}".format(self.generated)
            if _realm(user):
                name = "{0}::{1}".format(_realm(user), name)
            secret = SECRET
        self.keys[name] = _key(name, user, secret=secret)
        return _ok([self.keys[name]])

    def _patch_object_store_access_keys(self, **kwargs):
        if len(self._split(kwargs["names"])) > 1:
            return _error(MANY_KEYS_PATCH)
        found = self._find(self.keys, kwargs["names"][0])
        if not found:
            return _error(NO_KEY)
        self.keys[found].enabled = kwargs["object_store_access_key"]["enabled"]
        return _ok([self.keys[found]])

    def _delete_object_store_access_keys(self, **kwargs):
        if len(self._split(kwargs["names"])) > 1:
            return _error(MANY_KEYS_DELETE)
        found = self._find(self.keys, kwargs["names"][0])
        if not found:
            return _error(NO_KEY)
        del self.keys[found]
        return _ok()

    def _get_object_store_access_policies(self, **kwargs):
        found = self._find(self.policies, kwargs["names"][0])
        if found:
            return _ok([_named(found)])
        return _error("Object store access policy does not exist.")

    def _get_object_store_users_object_store_access_policies(self, **kwargs):
        pair = (kwargs["member_names"][0], kwargs["policy_names"][0])
        return _ok([_named(pair[1])] if pair in self.attached else [])

    def _post_object_store_access_policies_object_store_users(self, **kwargs):
        user, policy = kwargs["member_names"][0], kwargs["policy_names"][0]
        if "/" in policy and not policy.startswith("pure:policy/"):
            if policy.rpartition("/")[0].lower() != user.rpartition("/")[0].lower():
                return _error(POLICY_ACCOUNT)
        self.attached.add((user, policy))
        return _ok()

    def _delete_object_store_access_policies_object_store_users(self, **kwargs):
        self.attached.discard((kwargs["member_names"][0], kwargs["policy_names"][0]))
        return _ok()

    def enabled(self, name):
        return self.keys[name].enabled

    def keys_of(self, user):
        return sorted(n for n, k in self.keys.items() if k.user.name == user)


def _run(module, array, api_version="2.30"):
    """Run main() against the stand-in array; return the AnsibleModule mock."""
    with patch(MOD + ".AnsibleModule", return_value=module) as ansible_module, patch(
        MOD + ".get_system", return_value=array.blade
    ), patch(MOD + ".get_rest_api_version", return_value=api_version), patch(
        MOD + ".LooseVersion", RealLooseVersion
    ), patch(
        MOD + ".HAS_PYPURECLIENT", True
    ), patch(
        MOD + ".ObjectStoreAccessKey", side_effect=lambda **kw: kw
    ), patch(
        MOD + ".ObjectStoreAccessKeyPost", side_effect=lambda **kw: kw
    ), patch(
        MOD + ".get_error_message", side_effect=_error_message
    ):
        try:
            main()
        except SystemExit:
            pass
    return ansible_module


def _changed(module):
    module.fail_json.assert_not_called()
    module.exit_json.assert_called_once()
    return module.exit_json.call_args[1]["changed"]


def _facts(module):
    return module.exit_json.call_args[1]["s3user_info"]


def _failure(module):
    """The message of the one and only fail_json; nothing may exit after it."""
    module.fail_json.assert_called_once()
    module.exit_json.assert_not_called()
    return module.fail_json.call_args[1]["msg"]


def _warnings(module):
    return [call[0][0] for call in module.warn.call_args_list]


def _no_writes(blade):
    blade.post_object_store_users.assert_not_called()
    blade.delete_object_store_users.assert_not_called()
    blade.post_object_store_access_keys.assert_not_called()
    blade.patch_object_store_access_keys.assert_not_called()
    blade.delete_object_store_access_keys.assert_not_called()
    blade.post_object_store_access_policies_object_store_users.assert_not_called()
    blade.delete_object_store_access_policies_object_store_users.assert_not_called()


def _twins():
    """The same access key ID outside any realm and in realm rz."""
    return _Array(
        accounts=["acc1", "rz::acc1"],
        users=["acc1/user1", "rz::acc1/user1"],
        keys=[_key(KEY_A, "acc1/user1"), _key("rz::" + KEY_A, "rz::acc1/user1")],
    )


class TestUsers:
    """Create, update and delete of users and their access keys."""

    def test_missing_sdk_fails(self):
        module = _module()
        with patch(MOD + ".AnsibleModule", return_value=module), patch(
            MOD + ".HAS_PYPURECLIENT", False
        ):
            try:
                main()
            except SystemExit:
                pass
        assert "py-pure-client" in _failure(module)

    def test_missing_account_fails(self):
        array = _Array(accounts=[])
        module = _module()
        _run(module, array)
        assert _failure(module) == "Object Store Account acc1 does not exist"
        _no_writes(array.blade)

    def test_account_name_is_lowercased_with_a_warning(self):
        array = _Array(users=["acc1/user1"])
        module = _module(account="ACC1")
        _run(module, array)
        assert _changed(module) is False
        assert module.params["account"] == "acc1"
        assert _warnings(module) == ["Changing account name to lowercase..."]

    def test_create_user(self):
        array = _Array()
        module = _module()
        _run(module, array)
        assert _changed(module) is True
        assert _facts(module) == {}
        assert array.users == ["acc1/user1"]
        array.blade.post_object_store_users.assert_called_once_with(
            names=["acc1/user1"]
        )
        array.blade.post_object_store_access_keys.assert_not_called()

    def test_create_user_is_idempotent(self):
        array = _Array(users=["acc1/user1"])
        module = _module()
        _run(module, array)
        assert _changed(module) is False
        _no_writes(array.blade)

    def test_create_user_check_mode_sends_nothing(self):
        array = _Array()
        module = _module(check_mode=True, access_key=True)
        _run(module, array)
        assert _changed(module) is True
        assert _facts(module) == {}
        _no_writes(array.blade)

    def test_create_user_in_a_realm_account(self):
        array = _Array(accounts=["rz::acc1"])
        module = _module(account="rz::acc1")
        _run(module, array)
        assert _changed(module) is True
        assert array.users == ["rz::acc1/user1"]

    def test_create_user_failure_reports_the_array_message(self):
        array = _Array()
        array.refuse["post_object_store_users"] = REFUSED
        module = _module()
        _run(module, array)
        assert REFUSED in _failure(module)

    def test_create_with_access_key_returns_the_key(self):
        array = _Array()
        module = _module(access_key=True)
        _run(module, array)
        assert _changed(module) is True
        facts = _facts(module)["fb_s3user"]
        assert facts["user"] == "acc1/user1"
        assert facts["enabled"] is True
        assert facts["access_key"] == SECRET
        assert facts["access_id"] == "PSFBIGENERATED0001"
        assert array.keys_of("acc1/user1") == ["PSFBIGENERATED0001"]
        array.blade.patch_object_store_access_keys.assert_not_called()

    def test_create_with_disabled_access_key(self):
        array = _Array()
        module = _module(access_key=True, enable_key=False)
        _run(module, array)
        assert _changed(module) is True
        assert _facts(module)["fb_s3user"]["enabled"] is False
        assert array.enabled("PSFBIGENERATED0001") is False

    def test_access_key_overrides_imported_key_with_a_warning(self):
        array = _Array()
        module = _module(access_key=True, imported_key=KEY_A, imported_secret=SECRET)
        _run(module, array)
        assert _changed(module) is True
        assert "'access_key: true' overrides imported keys" in _warnings(module)
        assert array.keys_of("acc1/user1") == ["PSFBIGENERATED0001"]

    def test_create_rolls_back_when_the_access_key_fails(self):
        array = _Array()
        array.refuse["post_object_store_access_keys"] = REFUSED
        module = _module(access_key=True)
        _run(module, array)
        assert REFUSED in _failure(module)
        assert array.users == []
        array.blade.delete_object_store_users.assert_called_once_with(
            names=["acc1/user1"]
        )

    def test_create_with_imported_key(self):
        array = _Array()
        module = _module(imported_key=KEY_A, imported_secret=SECRET)
        _run(module, array)
        assert _changed(module) is True
        assert _facts(module) == {}
        array.blade.post_object_store_access_keys.assert_called_once_with(
            names=[KEY_A],
            object_store_access_key={
                "user": {"name": "acc1/user1"},
                "secret_access_key": SECRET,
            },
        )
        assert array.keys_of("acc1/user1") == [KEY_A]

    def test_create_with_imported_key_disabled(self):
        array = _Array()
        module = _module(imported_key=KEY_A, imported_secret=SECRET, enable_key=False)
        _run(module, array)
        assert _changed(module) is True
        assert array.enabled(KEY_A) is False

    def test_create_rolls_back_when_the_import_is_refused(self):
        array = _Array()
        array.refuse["post_object_store_access_keys"] = (
            "The access key/secret key combination provided is invalid or "
            "unable to be imported"
        )
        module = _module(imported_key=KEY_A, imported_secret="wrong")
        _run(module, array)
        assert "unable to be imported" in _failure(module)
        assert array.users == []

    def test_create_with_policies(self):
        array = _Array(policies=["pure:policy/object-read", "acc1/pol1"])
        module = _module(policy=["pure:policy/object-read", "acc1/pol1"])
        _run(module, array)
        assert _changed(module) is True
        assert array.attached == set(
            [("acc1/user1", "pure:policy/object-read"), ("acc1/user1", "acc1/pol1")]
        )
        assert _warnings(module) == []

    def test_create_in_a_realm_with_the_realm_form_of_a_policy(self):
        array = _Array(accounts=["rz::acc1"], policies=["rz::acc1/pol1"])
        module = _module(account="rz::acc1", policy=["rz::acc1/pol1"])
        _run(module, array)
        assert _changed(module) is True
        assert array.attached == set([("rz::acc1/user1", "rz::acc1/pol1")])

    def test_unknown_policy_is_skipped_with_a_warning(self):
        array = _Array(policies=["pure:policy/object-read"])
        module = _module(policy=["nope", "pure:policy/object-read"])
        _run(module, array)
        assert _changed(module) is True
        assert _warnings(module) == ["Policy nope is not valid. Ignoring..."]
        assert array.attached == set([("acc1/user1", "pure:policy/object-read")])

    def test_policy_of_another_account_is_skipped_with_a_warning(self):
        array = _Array(accounts=["acc1", "rz::acc1"], policies=["rz::acc1/pol1"])
        module = _module(policy=["rz::acc1/pol1"])
        _run(module, array)
        assert _changed(module) is True
        assert array.attached == set()
        assert len(_warnings(module)) == 1
        assert POLICY_ACCOUNT in _warnings(module)[0]

    def test_default_full_access_is_dropped_for_an_explicit_list(self):
        array = _Array(policies=["pure:policy/object-read"])
        post_user = array.blade.post_object_store_users.side_effect

        def post_with_default(**kwargs):
            array.attached.add((kwargs["names"][0], "pure:policy/full-access"))
            return post_user(**kwargs)

        array.blade.post_object_store_users.side_effect = post_with_default
        module = _module(policy=["pure:policy/object-read"])
        _run(module, array)
        assert _changed(module) is True
        assert array.attached == set([("acc1/user1", "pure:policy/object-read")])

    def test_existing_user_with_one_key_gets_no_second_key(self):
        array = _Array(users=["acc1/user1"], keys=[_key(KEY_A, "acc1/user1")])
        module = _module(access_key=True)
        _run(module, array)
        assert _changed(module) is False
        assert _facts(module) == {}
        _no_writes(array.blade)

    def test_existing_user_without_key_gets_one(self):
        array = _Array(users=["acc1/user1", "acc1/user2"])
        array.keys[KEY_B] = _key(KEY_B, "acc1/user2")
        module = _module(access_key=True)
        _run(module, array)
        assert _changed(module) is True
        assert _facts(module)["fb_s3user"]["access_id"] == "PSFBIGENERATED0001"
        assert array.keys_of("acc1/user1") == ["PSFBIGENERATED0001"]

    def test_second_key_with_multiple_keys(self):
        array = _Array(users=["acc1/user1"], keys=[_key(KEY_A, "acc1/user1")])
        module = _module(access_key=True, multiple_keys=True)
        _run(module, array)
        assert _changed(module) is True
        assert len(array.keys_of("acc1/user1")) == 2

    def test_second_key_check_mode(self):
        array = _Array(users=["acc1/user1"], keys=[_key(KEY_A, "acc1/user1")])
        module = _module(check_mode=True, access_key=True, multiple_keys=True)
        _run(module, array)
        assert _changed(module) is True
        _no_writes(array.blade)

    def test_third_key_is_refused_with_a_warning(self):
        array = _Array(
            users=["acc1/user1"],
            keys=[_key(KEY_A, "acc1/user1"), _key(KEY_B, "acc1/user1")],
        )
        module = _module(access_key=True, multiple_keys=True)
        _run(module, array)
        assert _changed(module) is False
        assert _warnings(module) == [
            "Object Store User acc1/user1: Maximum Access Key count reached"
        ]
        _no_writes(array.blade)

    def test_generated_key_failure_on_an_existing_user(self):
        array = _Array(users=["acc1/user1"])
        array.refuse["post_object_store_access_keys"] = REFUSED
        module = _module(access_key=True)
        _run(module, array)
        assert REFUSED in _failure(module)
        assert array.users == ["acc1/user1"]

    def test_import_for_an_existing_user(self):
        array = _Array(users=["acc1/user1"])
        module = _module(imported_key=KEY_A, imported_secret=SECRET)
        _run(module, array)
        assert _changed(module) is True
        assert array.keys_of("acc1/user1") == [KEY_A]

    def test_import_for_an_existing_user_disabled(self):
        array = _Array(users=["acc1/user1"])
        module = _module(imported_key=KEY_A, imported_secret=SECRET, enable_key=False)
        _run(module, array)
        assert _changed(module) is True
        assert array.enabled(KEY_A) is False

    def test_import_is_idempotent(self):
        array = _Array(users=["acc1/user1"], keys=[_key(KEY_A, "acc1/user1")])
        module = _module(imported_key=KEY_A, imported_secret=SECRET)
        _run(module, array)
        assert _changed(module) is False
        assert _warnings(module) == []
        _no_writes(array.blade)

    def test_import_of_another_users_key_warns_for_an_existing_user(self):
        array = _Array(
            users=["acc1/user1", "acc1/user2"], keys=[_key(KEY_A, "acc1/user2")]
        )
        module = _module(imported_key=KEY_A, imported_secret=SECRET)
        _run(module, array)
        assert _changed(module) is False
        assert _warnings(module) == [
            "Imported key provided already belongs to another user"
        ]
        _no_writes(array.blade)

    def test_import_failure_on_an_existing_user(self):
        array = _Array(users=["acc1/user1"])
        array.refuse["post_object_store_access_keys"] = REFUSED
        module = _module(imported_key=KEY_A, imported_secret=SECRET)
        _run(module, array)
        assert REFUSED in _failure(module)

    def test_delete_user(self):
        array = _Array(users=["acc1/user1"], keys=[_key(KEY_A, "acc1/user1")])
        module = _module(state="absent")
        _run(module, array)
        assert _changed(module) is True
        assert array.users == []
        array.blade.delete_object_store_users.assert_called_once_with(
            names=["acc1/user1"]
        )

    def test_delete_user_check_mode(self):
        array = _Array(users=["acc1/user1"])
        module = _module(check_mode=True, state="absent")
        _run(module, array)
        assert _changed(module) is True
        _no_writes(array.blade)

    def test_delete_missing_user_is_unchanged(self):
        array = _Array()
        module = _module(state="absent")
        _run(module, array)
        assert _changed(module) is False
        _no_writes(array.blade)

    def test_delete_user_failure(self):
        array = _Array(users=["acc1/user1"])
        array.refuse["delete_object_store_users"] = REFUSED
        module = _module(state="absent")
        _run(module, array)
        assert "Deletion failed" in _failure(module)

    def test_fleet_context_is_passed_to_every_call(self):
        array = _Array(users=["acc1/user1"], keys=[_key(KEY_A, "acc1/user1")])
        module = _module(
            state="keystate", key_name=KEY_A, enable_key=False, context="fb2"
        )
        _run(module, array)
        assert _changed(module) is True
        blade = array.blade
        blade.get_fleets.assert_not_called()
        blade.get_object_store_accounts.assert_called_once_with(
            names=["acc1"], context_names=["fb2"]
        )
        blade.get_object_store_users.assert_called_once_with(
            names=["acc1/user1"], context_names=["fb2"]
        )
        blade.get_object_store_access_keys.assert_called_once_with(
            names=[KEY_A], context_names=["fb2"]
        )
        blade.patch_object_store_access_keys.assert_called_once_with(
            names=[KEY_A],
            object_store_access_key={"enabled": False},
            context_names=["fb2"],
        )

    def test_fleet_member_uses_its_own_name_as_context(self):
        array = _Array(users=["acc1/user1"], keys=[_key(KEY_A, "acc1/user1")])
        array.blade.get_fleets.side_effect = lambda **kw: _ok([_named("fleet1")])
        array.blade.get_arrays.return_value = _ok([_named("fb1")])
        module = _module(state="remove_key", key_name=KEY_A)
        _run(module, array)
        assert _changed(module) is True
        assert module.params["context"] == "fb1"
        array.blade.delete_object_store_access_keys.assert_called_once_with(
            names=[KEY_A], context_names=["fb1"]
        )

    def test_context_is_not_sent_below_rest_2_17(self):
        array = _Array(users=["acc1/user1"], keys=[_key(KEY_A, "acc1/user1")])
        module = _module(state="remove_key", key_name=KEY_A, context="fb2")
        _run(module, array, api_version="2.16")
        assert _changed(module) is True
        array.blade.get_object_store_access_keys.assert_called_once_with(names=[KEY_A])
        array.blade.delete_object_store_access_keys.assert_called_once_with(
            names=[KEY_A]
        )


class TestKeyStates:
    """state=keystate and state=remove_key on the user's own access key."""

    def test_disable_key(self):
        array = _Array(users=["acc1/user1"], keys=[_key(KEY_A, "acc1/user1")])
        module = _module(state="keystate", key_name=KEY_A, enable_key=False)
        _run(module, array)
        assert _changed(module) is True
        assert array.enabled(KEY_A) is False
        array.blade.patch_object_store_access_keys.assert_called_once_with(
            names=[KEY_A], object_store_access_key={"enabled": False}
        )

    def test_disable_key_is_idempotent(self):
        array = _Array(
            users=["acc1/user1"], keys=[_key(KEY_A, "acc1/user1", enabled=False)]
        )
        module = _module(state="keystate", key_name=KEY_A, enable_key=False)
        _run(module, array)
        assert _changed(module) is False
        _no_writes(array.blade)

    def test_enable_key(self):
        array = _Array(
            users=["acc1/user1"], keys=[_key(KEY_A, "acc1/user1", enabled=False)]
        )
        module = _module(state="keystate", key_name=KEY_A, enable_key=True)
        _run(module, array)
        assert _changed(module) is True
        assert array.enabled(KEY_A) is True

    def test_keystate_check_mode_predicts_the_change(self):
        array = _Array(users=["acc1/user1"], keys=[_key(KEY_A, "acc1/user1")])
        module = _module(
            check_mode=True, state="keystate", key_name=KEY_A, enable_key=False
        )
        _run(module, array)
        assert _changed(module) is True
        assert array.enabled(KEY_A) is True
        _no_writes(array.blade)

    def test_keystate_check_mode_unchanged_when_already_in_state(self):
        array = _Array(
            users=["acc1/user1"], keys=[_key(KEY_A, "acc1/user1", enabled=False)]
        )
        module = _module(
            check_mode=True, state="keystate", key_name=KEY_A, enable_key=False
        )
        _run(module, array)
        assert _changed(module) is False
        array.blade.get_object_store_access_keys.assert_called_once_with(names=[KEY_A])
        _no_writes(array.blade)

    def test_keystate_failure_reports_the_array_message(self):
        array = _Array(users=["acc1/user1"], keys=[_key(KEY_A, "acc1/user1")])
        array.refuse["patch_object_store_access_keys"] = REFUSED
        module = _module(state="keystate", key_name=KEY_A, enable_key=False)
        _run(module, array)
        assert REFUSED in _failure(module)

    def test_keystate_fails_when_the_key_does_not_exist(self):
        array = _Array(users=["acc1/user1"], keys=[_key(KEY_A, "acc1/user1")])
        for check_mode in (False, True):
            module = _module(
                check_mode=check_mode,
                state="keystate",
                key_name=KEY_NONE,
                enable_key=False,
            )
            _run(module, array)
            message = _failure(module)
            assert KEY_NONE in message
            assert "does not exist" in message
        _no_writes(array.blade)

    def test_keystate_fails_when_the_user_does_not_exist(self):
        array = _Array(users=["acc1/user2"], keys=[_key(KEY_A, "acc1/user2")])
        module = _module(state="keystate", key_name=KEY_A, enable_key=False)
        _run(module, array)
        assert "Object Store User acc1/user1 does not exist" in _failure(module)
        array.blade.get_object_store_access_keys.assert_not_called()
        _no_writes(array.blade)

    def test_keystate_requires_key_name(self):
        array = _Array(users=["acc1/user1"])
        ansible_module = _run(_module(), array)
        required_if = ansible_module.call_args[1]["required_if"]
        assert ["state", "keystate", ["key_name"]] in required_if
        assert ["state", "remove_key", ["key_name"]] in required_if

    def test_remove_key(self):
        array = _Array(
            users=["acc1/user1"],
            keys=[_key(KEY_A, "acc1/user1"), _key(KEY_B, "acc1/user1")],
        )
        module = _module(state="remove_key", key_name=KEY_A)
        _run(module, array)
        assert _changed(module) is True
        assert array.keys_of("acc1/user1") == [KEY_B]
        array.blade.delete_object_store_access_keys.assert_called_once_with(
            names=[KEY_A]
        )

    def test_remove_key_check_mode(self):
        array = _Array(users=["acc1/user1"], keys=[_key(KEY_A, "acc1/user1")])
        module = _module(check_mode=True, state="remove_key", key_name=KEY_A)
        _run(module, array)
        assert _changed(module) is True
        assert array.keys_of("acc1/user1") == [KEY_A]
        _no_writes(array.blade)

    def test_remove_key_is_idempotent(self):
        array = _Array(users=["acc1/user1"], keys=[_key(KEY_B, "acc1/user1")])
        module = _module(state="remove_key", key_name=KEY_A)
        _run(module, array)
        assert _changed(module) is False
        _no_writes(array.blade)

    def test_remove_key_of_a_missing_user_is_unchanged(self):
        array = _Array()
        module = _module(state="remove_key", key_name=KEY_A)
        _run(module, array)
        assert _changed(module) is False
        _no_writes(array.blade)

    def test_remove_key_failure_reports_the_array_message(self):
        array = _Array(users=["acc1/user1"], keys=[_key(KEY_A, "acc1/user1")])
        array.refuse["delete_object_store_access_keys"] = REFUSED
        module = _module(state="remove_key", key_name=KEY_A)
        _run(module, array)
        assert REFUSED in _failure(module)


class TestKeyOwnership:
    """key_name only ever reaches an access key of the user the task names."""

    def _two_users(self):
        return _Array(
            users=["acc1/user1", "acc1/user2"],
            keys=[_key(KEY_A, "acc1/user1"), _key(KEY_B, "acc1/user2")],
        )

    def test_keystate_refuses_another_users_key(self):
        array = self._two_users()
        module = _module(state="keystate", key_name=KEY_B, enable_key=False)
        _run(module, array)
        message = _failure(module)
        assert "belongs to object store user acc1/user2" in message
        assert "not to acc1/user1" in message
        assert array.enabled(KEY_B) is True
        _no_writes(array.blade)

    def test_keystate_refuses_another_users_key_in_check_mode(self):
        array = self._two_users()
        module = _module(
            check_mode=True, state="keystate", key_name=KEY_B, enable_key=False
        )
        _run(module, array)
        assert "belongs to object store user acc1/user2" in _failure(module)
        _no_writes(array.blade)

    def test_remove_key_refuses_another_users_key(self):
        array = self._two_users()
        module = _module(state="remove_key", key_name=KEY_B)
        _run(module, array)
        assert "belongs to object store user acc1/user2" in _failure(module)
        assert array.keys_of("acc1/user2") == [KEY_B]
        _no_writes(array.blade)

    def test_remove_key_refuses_another_users_key_in_check_mode(self):
        array = self._two_users()
        module = _module(check_mode=True, state="remove_key", key_name=KEY_B)
        _run(module, array)
        assert "belongs to object store user acc1/user2" in _failure(module)
        _no_writes(array.blade)

    def test_namesake_user_of_another_account_is_another_user(self):
        array = _Array(
            accounts=["acc1", "acc2"],
            users=["acc1/user1", "acc2/user1"],
            keys=[_key(KEY_A, "acc2/user1")],
        )
        module = _module(state="remove_key", key_name=KEY_A)
        _run(module, array)
        assert "belongs to object store user acc2/user1" in _failure(module)
        assert array.keys_of("acc2/user1") == [KEY_A]

    def test_owner_is_compared_without_regard_to_case(self):
        array = _Array(users=["acc1/user1"], keys=[_key(KEY_A, "acc1/user1")])
        module = _module(
            name="USER1", state="keystate", key_name=KEY_A, enable_key=False
        )
        _run(module, array)
        assert _changed(module) is True
        assert array.enabled(KEY_A) is False

    def test_key_count_is_taken_without_regard_to_case(self):
        array = _Array(users=["acc1/user1"], keys=[_key(KEY_A, "acc1/user1")])
        module = _module(name="USER1", access_key=True)
        _run(module, array)
        assert _changed(module) is False
        assert array.keys_of("acc1/user1") == [KEY_A]
        _no_writes(array.blade)

    def test_import_owner_is_compared_without_regard_to_case(self):
        array = _Array(users=["acc1/user1"], keys=[_key(KEY_A, "acc1/user1")])
        module = _module(name="USER1", imported_key=KEY_A, imported_secret=SECRET)
        _run(module, array)
        assert _changed(module) is False
        assert _warnings(module) == []


class TestRealmKeyNames:
    """An access key is addressed in the realm of the account of the task."""

    def test_keystate_with_a_bare_id_reaches_the_realm_key(self):
        array = _twins()
        module = _module(
            account="rz::acc1", state="keystate", key_name=KEY_A, enable_key=False
        )
        _run(module, array)
        assert _changed(module) is True
        assert array.enabled("rz::" + KEY_A) is False
        assert array.enabled(KEY_A) is True
        array.blade.patch_object_store_access_keys.assert_called_once_with(
            names=["rz::" + KEY_A], object_store_access_key={"enabled": False}
        )

    def test_keystate_with_a_bare_id_check_mode(self):
        array = _twins()
        module = _module(
            check_mode=True,
            account="rz::acc1",
            state="keystate",
            key_name=KEY_A,
            enable_key=False,
        )
        _run(module, array)
        assert _changed(module) is True
        array.blade.get_object_store_access_keys.assert_called_once_with(
            names=["rz::" + KEY_A]
        )
        _no_writes(array.blade)

    def test_remove_key_with_a_bare_id_removes_the_realm_key(self):
        array = _twins()
        module = _module(account="rz::acc1", state="remove_key", key_name=KEY_A)
        _run(module, array)
        assert _changed(module) is True
        assert array.keys_of("rz::acc1/user1") == []
        assert array.keys_of("acc1/user1") == [KEY_A]
        array.blade.delete_object_store_access_keys.assert_called_once_with(
            names=["rz::" + KEY_A]
        )

    def test_bare_id_without_an_array_level_namesake(self):
        array = _Array(
            accounts=["rz::acc1"],
            users=["rz::acc1/user1"],
            keys=[_key("rz::" + KEY_A, "rz::acc1/user1")],
        )
        module = _module(
            account="rz::acc1", state="keystate", key_name=KEY_A, enable_key=False
        )
        _run(module, array)
        assert _changed(module) is True
        assert array.enabled("rz::" + KEY_A) is False
        module = _module(account="rz::acc1", state="remove_key", key_name=KEY_A)
        _run(module, array)
        assert _changed(module) is True
        assert array.keys == {}

    def test_full_key_name_still_works(self):
        array = _twins()
        module = _module(
            account="rz::acc1",
            state="keystate",
            key_name="rz::" + KEY_A,
            enable_key=False,
        )
        _run(module, array)
        assert _changed(module) is True
        assert array.enabled("rz::" + KEY_A) is False
        assert array.enabled(KEY_A) is True

    def test_realm_prefix_is_matched_without_regard_to_case(self):
        array = _twins()
        module = _module(
            account="rz::acc1", state="remove_key", key_name="RZ::" + KEY_A
        )
        _run(module, array)
        assert _changed(module) is True
        assert module.params["key_name"] == "rz::" + KEY_A
        assert array.keys_of("rz::acc1/user1") == []

    def test_array_level_user_keeps_the_bare_id(self):
        array = _twins()
        module = _module(state="keystate", key_name=KEY_A, enable_key=False)
        _run(module, array)
        assert _changed(module) is True
        assert array.enabled(KEY_A) is False
        assert array.enabled("rz::" + KEY_A) is True

    def test_realm_key_name_is_refused_for_an_array_level_user(self):
        array = _twins()
        for state in ("keystate", "remove_key"):
            for check_mode in (False, True):
                module = _module(
                    check_mode=check_mode, state=state, key_name="rz::" + KEY_A
                )
                _run(module, array)
                message = _failure(module)
                assert "cannot belong to object store user acc1/user1" in message
                assert "not in a realm" in message
        array.blade.get_object_store_access_keys.assert_not_called()
        assert array.keys_of("rz::acc1/user1") == ["rz::" + KEY_A]
        _no_writes(array.blade)

    def test_key_name_of_another_realm_is_refused(self):
        array = _twins()
        module = _module(
            check_mode=True,
            account="rz::acc1",
            state="remove_key",
            key_name="other::" + KEY_A,
        )
        _run(module, array)
        message = _failure(module)
        assert "cannot belong to object store user rz::acc1/user1" in message
        assert "rz::<access key ID>" in message
        array.blade.get_object_store_access_keys.assert_not_called()

    def test_key_name_is_ignored_for_other_states(self):
        array = _Array(users=["acc1/user1"])
        module = _module(key_name="rz::" + KEY_A)
        _run(module, array)
        assert _changed(module) is False
        assert module.params["key_name"] == "rz::" + KEY_A

    def test_new_realm_user_imports_a_bare_id_into_the_realm(self):
        array = _Array(accounts=["rz::acc1"])
        module = _module(account="rz::acc1", imported_key=KEY_A, imported_secret=SECRET)
        _run(module, array)
        assert _changed(module) is True
        array.blade.post_object_store_access_keys.assert_called_once_with(
            names=["rz::" + KEY_A],
            object_store_access_key={
                "user": {"name": "rz::acc1/user1"},
                "secret_access_key": SECRET,
            },
        )
        assert array.keys_of("rz::acc1/user1") == ["rz::" + KEY_A]

    def test_existing_realm_user_imports_an_id_that_exists_outside_the_realm(self):
        array = _Array(
            accounts=["acc1", "rz::acc1"],
            users=["acc1/user1", "rz::acc1/user1"],
            keys=[_key(KEY_A, "acc1/user1")],
        )
        module = _module(account="rz::acc1", imported_key=KEY_A, imported_secret=SECRET)
        _run(module, array)
        assert _changed(module) is True
        assert _warnings(module) == []
        assert array.keys_of("rz::acc1/user1") == ["rz::" + KEY_A]
        assert array.keys_of("acc1/user1") == [KEY_A]

    def test_realm_import_is_idempotent_with_either_form(self):
        array = _twins()
        for imported_key in (KEY_A, "rz::" + KEY_A):
            module = _module(
                account="rz::acc1", imported_key=imported_key, imported_secret=SECRET
            )
            _run(module, array)
            assert _changed(module) is False
            assert _warnings(module) == []
        _no_writes(array.blade)

    def test_import_of_a_key_of_another_scope_is_refused(self):
        cases = (
            ("acc1", "rz::" + KEY_B, "not in a realm"),
            ("rz::acc1", "other::" + KEY_B, "rz::<access key ID>"),
        )
        for name in ("user1", "user9"):
            for account, imported_key, reason in cases:
                for check_mode in (False, True):
                    array = _twins()
                    module = _module(
                        check_mode=check_mode,
                        name=name,
                        account=account,
                        imported_key=imported_key,
                        imported_secret=SECRET,
                    )
                    _run(module, array)
                    message = _failure(module)
                    assert "cannot belong to object store user" in message
                    assert reason in message
                    _no_writes(array.blade)

    def test_ignored_imported_key_is_not_checked(self):
        array = _Array()
        module = _module(
            access_key=True, imported_key="rz::" + KEY_A, imported_secret=SECRET
        )
        _run(module, array)
        assert _changed(module) is True
        assert array.keys_of("acc1/user1") == ["PSFBIGENERATED0001"]

    def test_new_user_cannot_import_a_key_another_user_holds(self):
        for account in ("acc1", "rz::acc1"):
            for check_mode in (False, True):
                array = _twins()
                module = _module(
                    check_mode=check_mode,
                    name="user9",
                    account=account,
                    imported_key=KEY_A,
                    imported_secret=SECRET,
                )
                _run(module, array)
                message = _failure(module)
                assert "already belongs to object store user" in message
                assert account + "/user1" in message
                assert account + "/user9" not in array.users
                _no_writes(array.blade)


class TestOneName:
    """A task names one account, one user and one access key."""

    def _two_keys(self):
        return _Array(
            users=["acc1/user1", "acc1/user2"],
            keys=[_key(KEY_A, "acc1/user1"), _key(KEY_B, "acc1/user1")],
        )

    def test_list_of_key_names_is_refused(self):
        for state in ("keystate", "remove_key"):
            for check_mode in (False, True):
                array = self._two_keys()
                module = _module(
                    check_mode=check_mode,
                    state=state,
                    key_name=KEY_A + "," + KEY_B,
                    enable_key=False,
                )
                _run(module, array)
                assert "key_name names more than one object" in _failure(module)
                array.blade.get_object_store_accounts.assert_not_called()
                array.blade.get_object_store_access_keys.assert_not_called()
                _no_writes(array.blade)
                assert array.keys_of("acc1/user1") == [KEY_A, KEY_B]
                assert array.enabled(KEY_A) is True
                assert array.enabled(KEY_B) is True

    def test_list_of_key_names_in_a_realm_is_refused(self):
        array = _twins()
        key_name = KEY_A + "," + KEY_A
        module = _module(
            check_mode=True, account="rz::acc1", state="remove_key", key_name=key_name
        )
        _run(module, array)
        assert "key_name names more than one object" in _failure(module)
        assert module.params["key_name"] == key_name
        array.blade.get_object_store_access_keys.assert_not_called()
        _no_writes(array.blade)

    def test_list_of_user_names_is_refused(self):
        for state in ("absent", "present"):
            for check_mode in (False, True):
                array = _Array(users=["acc1/user1", "acc1/user2"])
                module = _module(
                    check_mode=check_mode, state=state, name="user1,acc1/user2"
                )
                _run(module, array)
                assert "name names more than one object" in _failure(module)
                array.blade.get_object_store_users.assert_not_called()
                _no_writes(array.blade)
                assert array.users == ["acc1/user1", "acc1/user2"]

    def test_list_of_new_user_names_is_refused(self):
        for check_mode in (False, True):
            array = _Array()
            module = _module(check_mode=check_mode, name="user1,acc1/user2")
            _run(module, array)
            assert "name names more than one object" in _failure(module)
            _no_writes(array.blade)
            assert array.users == []

    def test_list_of_accounts_is_refused(self):
        array = _Array(accounts=["acc1", "acc2"], users=["acc1/user1"])
        module = _module(check_mode=True, account="acc1,acc2", state="absent")
        _run(module, array)
        assert "account names more than one object" in _failure(module)
        array.blade.get_object_store_accounts.assert_not_called()
        _no_writes(array.blade)

    def test_list_of_imported_keys_is_refused(self):
        for users in (["acc1/user1"], []):
            for check_mode in (False, True):
                array = _Array(users=users)
                module = _module(
                    check_mode=check_mode,
                    imported_key=KEY_A + "," + KEY_B,
                    imported_secret=SECRET,
                )
                _run(module, array)
                assert "imported_key names more than one object" in _failure(module)
                array.blade.get_object_store_access_keys.assert_not_called()
                _no_writes(array.blade)

    def test_empty_names_are_refused(self):
        cases = (
            (dict(name=""), "name must not be empty."),
            (dict(name="  "), "name must not be empty."),
            (dict(account=""), "account must not be empty."),
            (dict(state="keystate", key_name=""), "key_name must not be empty."),
            (dict(state="remove_key", key_name=" "), "key_name must not be empty."),
            (dict(state="remove_key", key_name=None), "key_name must not be empty."),
            (
                dict(account="rz::acc1", state="remove_key", key_name=""),
                "key_name must not be empty.",
            ),
            (
                dict(account="rz::acc1", state="keystate", key_name="rz::"),
                "key_name must hold an access key ID.",
            ),
        )
        for overrides, message in cases:
            array = _twins()
            module = _module(check_mode=True, **overrides)
            _run(module, array)
            assert _failure(module) == message
            array.blade.get_object_store_users.assert_not_called()
            array.blade.get_object_store_access_keys.assert_not_called()
            _no_writes(array.blade)


class TestKeyFacts:
    """s3user_info carries the key name and the access key ID."""

    def test_generated_key_of_a_realm_user(self):
        array = _Array(accounts=["rz::acc1"])
        module = _module(account="rz::acc1", access_key=True)
        _run(module, array)
        facts = _facts(module)["fb_s3user"]
        assert facts["user"] == "rz::acc1/user1"
        assert facts["access_id"] == "rz::PSFBIGENERATED0001"
        assert facts["access_key_id"] == "PSFBIGENERATED0001"
        assert facts["access_key"] == SECRET

    def test_generated_key_of_an_array_level_user(self):
        array = _Array()
        module = _module(access_key=True)
        _run(module, array)
        facts = _facts(module)["fb_s3user"]
        assert facts["access_id"] == "PSFBIGENERATED0001"
        assert facts["access_key_id"] == "PSFBIGENERATED0001"

    def test_second_key_of_an_existing_realm_user(self):
        array = _Array(
            accounts=["rz::acc1"],
            users=["rz::acc1/user1"],
            keys=[_key("rz::" + KEY_A, "rz::acc1/user1")],
        )
        module = _module(account="rz::acc1", access_key=True, multiple_keys=True)
        _run(module, array)
        facts = _facts(module)["fb_s3user"]
        assert facts["access_id"] == "rz::PSFBIGENERATED0001"
        assert facts["access_key_id"] == "PSFBIGENERATED0001"

    def test_access_key_id_falls_back_to_the_name(self):
        key = _key("PSFBIGENERATED0009", "acc1/user1", secret=SECRET)
        key.access_key_id = None
        module = _module()
        facts = purefb_s3user._key_facts(module, "acc1/user1", key)
        assert facts == {
            "user": "acc1/user1",
            "enabled": True,
            "access_key": SECRET,
            "access_id": "PSFBIGENERATED0009",
            "access_key_id": "PSFBIGENERATED0009",
        }

    def test_returned_id_is_accepted_as_key_name(self):
        array = _Array(accounts=["rz::acc1"])
        module = _module(account="rz::acc1", access_key=True)
        _run(module, array)
        facts = _facts(module)["fb_s3user"]
        for key_name in (facts["access_key_id"], facts["access_id"]):
            module = _module(
                account="rz::acc1",
                state="keystate",
                key_name=key_name,
                enable_key=False,
            )
            _run(module, array)
            module.fail_json.assert_not_called()
        assert array.enabled(facts["access_id"]) is False


class TestCheckedReads:
    """A read that is refused is reported, never taken for a missing object."""

    def test_refused_account_read(self):
        array = _Array(users=["acc1/user1"])
        array.refuse["get_object_store_accounts"] = REFUSED
        module = _module()
        _run(module, array)
        message = _failure(module)
        assert REFUSED in message
        assert "does not exist" not in message

    def test_refused_user_read_is_not_a_create(self):
        array = _Array(users=["acc1/user1"])
        array.refuse["get_object_store_users"] = REFUSED
        module = _module(access_key=True)
        _run(module, array)
        assert REFUSED in _failure(module)
        _no_writes(array.blade)

    def test_refused_user_read_is_not_absent(self):
        array = _Array(users=["acc1/user1"])
        array.refuse["get_object_store_users"] = REFUSED
        module = _module(state="absent")
        _run(module, array)
        assert REFUSED in _failure(module)
        _no_writes(array.blade)

    def test_refused_key_read_in_remove_key(self):
        array = _Array(users=["acc1/user1"], keys=[_key(KEY_A, "acc1/user1")])
        array.refuse["get_object_store_access_keys"] = REFUSED
        module = _module(state="remove_key", key_name=KEY_A)
        _run(module, array)
        assert REFUSED in _failure(module)
        _no_writes(array.blade)

    def test_refused_key_read_in_keystate(self):
        array = _Array(users=["acc1/user1"], keys=[_key(KEY_A, "acc1/user1")])
        array.refuse["get_object_store_access_keys"] = REFUSED
        module = _module(state="keystate", key_name=KEY_A, enable_key=False)
        _run(module, array)
        message = _failure(module)
        assert REFUSED in message
        assert "does not exist" not in message

    def test_refused_key_list(self):
        array = _Array(users=["acc1/user1"])
        array.refuse["get_object_store_access_keys"] = REFUSED
        module = _module(access_key=True)
        _run(module, array)
        message = _failure(module)
        assert "Failed to list access keys" in message
        assert REFUSED in message
        _no_writes(array.blade)

    def test_refused_import_lookup(self):
        for users in (["acc1/user1"], []):
            array = _Array(users=users)
            array.refuse["get_object_store_access_keys"] = REFUSED
            module = _module(imported_key=KEY_A, imported_secret=SECRET)
            _run(module, array)
            assert REFUSED in _failure(module)
            _no_writes(array.blade)

    def test_refused_policy_membership_read(self):
        array = _Array(policies=["pure:policy/object-read"])
        array.refuse["get_object_store_users_object_store_access_policies"] = REFUSED
        module = _module(policy=["pure:policy/object-read"])
        _run(module, array)
        message = _failure(module)
        assert "Failed to read the access policies" in message
        assert REFUSED in message
        assert array.attached == set()


class TestHelpers:
    """The private helpers."""

    def test_realm_of(self):
        assert purefb_s3user._realm_of("acc1") == ""
        assert purefb_s3user._realm_of("rz::acc1") == "rz"
        assert purefb_s3user._realm_of("") == ""
        assert purefb_s3user._realm_of(None) == ""

    def test_same_name(self):
        assert purefb_s3user._same_name("RZ::Acc1/User1", "rz::acc1/user1")
        assert not purefb_s3user._same_name("acc1/user1", "acc1/user2")
        assert not purefb_s3user._same_name(None, "acc1/user1")
        assert purefb_s3user._same_name(None, "")

    def test_owner(self):
        assert purefb_s3user._owner(_key(KEY_A, "acc1/user1")) == "acc1/user1"
        orphan = Mock(spec=["name"])
        assert purefb_s3user._owner(orphan) is None

    def test_one_name(self):
        module = _module(account="rz::acc1", key_name="rz::" + KEY_A)
        for option in ("name", "account", "key_name"):
            purefb_s3user._one_name(module, option)
        module.fail_json.assert_not_called()
        cases = (
            (None, "name must not be empty."),
            ("", "name must not be empty."),
            (" ", "name must not be empty."),
            ("a,b", "name names more than one object (a,b)."),
        )
        for value, message in cases:
            module = _module(name=value)
            try:
                purefb_s3user._one_name(module, "name")
            except SystemExit:
                pass
            assert _failure(module).startswith(message)

    def test_qualify_key(self):
        module = _module(account="rz::acc1", key_name=KEY_A)
        purefb_s3user._qualify_key(module, "key_name")
        assert module.params["key_name"] == "rz::" + KEY_A
        module = _module(account="acc1", key_name=KEY_A)
        purefb_s3user._qualify_key(module, "key_name")
        assert module.params["key_name"] == KEY_A
        module = _module(account="rz::acc1", imported_key="Rz::" + KEY_A)
        purefb_s3user._qualify_key(module, "imported_key")
        assert module.params["imported_key"] == "rz::" + KEY_A
        module.fail_json.assert_not_called()

    @patch(MOD + ".LooseVersion", RealLooseVersion)
    def test_context_kwargs(self):
        module = _module(context="fb2")
        assert purefb_s3user._context_kwargs(module, "2.17") == {
            "context_names": ["fb2"]
        }
        assert purefb_s3user._context_kwargs(module, "2.16") == {}
        assert purefb_s3user._context_kwargs(_module(), "2.30") == {}

    @patch(MOD + ".get_error_message", side_effect=_error_message)
    def test_checked_item(self, mock_error):
        module = _module()
        item = _named("acc1")
        assert purefb_s3user._checked_item(module, _ok([item]), "x") is item
        assert purefb_s3user._checked_item(module, _ok([]), "x") is None
        assert purefb_s3user._checked_item(module, _error(NO_KEY), "x") is None
        module.fail_json.assert_not_called()
        try:
            purefb_s3user._checked_item(module, _error(REFUSED, 403), "access key k")
        except SystemExit:
            pass
        assert _failure(module) == "Failed to read access key k. Error: " + REFUSED
