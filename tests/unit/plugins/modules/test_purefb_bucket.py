# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_bucket module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from types import SimpleNamespace
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

from plugins.module_utils.version import LooseVersion as RealLooseVersion
from plugins.modules.purefb_bucket import (
    main,
    _check_account,
    _check_one_name,
    _check_same_realm,
    _get_one,
    _realm_of,
)

MOD = "plugins.modules.purefb_bucket"
GIB = 1073741824

# Answers of the array, as it words them
NO_BUCKET = "Bucket does not exist."
NO_ACCOUNT = "Object store account does not exist."
OTHER_REALM = "Bucket must be created in the same realm as the account."
NO_REALM = "Realm does not exist."
QUOTA_RANGE = "The quota_limit for a bucket must be between 1 byte and 9.22 exabytes."
NOT_PERMITTED = "Operation not permitted."
ONE_NAME = "Cannot process more than one name at a time."

# The only client methods the module may use. Anything else, such as an
# attribute the client does not have, raises AttributeError as the client does.
CLIENT_METHODS = [
    "get_fleets",
    "get_arrays",
    "get_object_store_accounts",
    "get_buckets",
    "post_buckets",
    "patch_buckets",
    "delete_buckets",
    "post_buckets_bucket_access_policies",
    "post_buckets_bucket_access_policies_rules",
]

MODELS = (
    "BucketPost",
    "BucketPatch",
    "ReferenceWritable",
    "BucketEradicationConfig",
    "ObjectLockConfigRequestBody",
    "PublicAccessConfig",
    "BucketAccessPolicyPost",
    "BucketAccessPolicyRulePost",
    "BucketAccessPolicyRulePrincipal",
)


def _params(**overrides):
    params = {
        "name": "foo",
        "account": "bar",
        "state": "present",
        "eradicate": False,
        "mode": None,
        "versioning": None,
        "quota": None,
        "hard_limit": None,
        "retention_lock": "unlocked",
        "retention_mode": None,
        "default_retention": None,
        "object_lock_enabled": False,
        "freeze_locked_objects": False,
        "block_new_public_policies": None,
        "block_public_access": None,
        "eradication_mode": None,
        "eradication_delay": None,
        "manual_eradication": None,
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
    return SimpleNamespace(status_code=200, items=items if items is not None else [])


def _error(message, status_code=400):
    """An error answer: it has errors and, like the client's, no items."""
    return SimpleNamespace(
        status_code=status_code, errors=[SimpleNamespace(message=message)]
    )


def _error_message(res, default="Unknown error"):
    errors = list(getattr(res, "errors", None) or [])
    return errors[0].message if errors else default


def _human_to_bytes(size):
    units = {"B": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}
    number, unit = size[:-1], size[-1].upper()
    if number.isdigit() and unit in units:
        return int(number) * units[unit]
    return 0


def _account(name, quota=None, hard=False, default_quota=None, default_hard=False):
    """An object store account as the array returns it."""
    return SimpleNamespace(
        id="id-of-account-" + name.lower(),
        name=name,
        quota_limit=quota,
        hard_limit_enabled=hard,
        bucket_defaults=SimpleNamespace(
            quota_limit=default_quota, hard_limit_enabled=default_hard
        ),
    )


def _bucket(name, account, quota=None, hard=False, destroyed=False, versioning="none"):
    """A bucket as the array returns it; quota_limit is unset when unlimited."""
    return SimpleNamespace(
        id="id-of-bucket-" + name.lower(),
        name=name,
        account=SimpleNamespace(
            id=account.id, name=account.name, resource_type="object-store-accounts"
        ),
        bucket_type="multi-site-writable",
        destroyed=destroyed,
        quota_limit=quota,
        hard_limit_enabled=hard,
        versioning=versioning,
        retention_lock="unlocked",
        object_lock_config=SimpleNamespace(
            enabled=False,
            freeze_locked_objects=False,
            default_retention_mode=None,
            default_retention=None,
        ),
        public_access_config=SimpleNamespace(
            block_new_public_policies=True, block_public_access=True
        ),
        eradication_config=SimpleNamespace(
            eradication_delay=86400000,
            eradication_mode="permission-based",
            manual_eradication="enabled",
        ),
    )


class _Array:
    """A small stateful stand-in for the array.

    Names are matched without regard to case or to blanks around them, and a
    read of a missing name is a 400, as on the array. A name with a comma is
    a list of names: a read answers with every object of the list, sorted by
    name, or with a 400 when one of them is missing, and a change or an
    eradication of a bucket is refused for more than one name. A new bucket
    takes the limits the request leaves out from the bucket defaults of its
    account. Every write is recorded in writes as (verb, name, body) and
    changes the state a later read returns.

    refuse maps a client method to the message it answers with instead of
    acting; hidden names are missed by a read although they exist; fleet is
    the name of the local array when it is a member of a fleet.
    """

    def __init__(self, accounts=(), buckets=(), fleet=None):
        self.accounts = dict((item.name.lower(), item) for item in accounts)
        self.buckets = dict((item.name.lower(), item) for item in buckets)
        self.fleet = fleet
        self.refuse = {}
        self.hidden = set()
        self.writes = []
        self.contexts = []
        self.client = Mock(spec=CLIENT_METHODS)
        for method in CLIENT_METHODS:
            getattr(self.client, method).side_effect = getattr(self, "_" + method)

    def _seen(self, method, kwargs):
        self.contexts.append(kwargs.get("context_names"))
        if method in self.refuse:
            return _error(self.refuse[method])
        return None

    def _get_fleets(self, **kwargs):
        return _ok([SimpleNamespace(name="fleet1")] if self.fleet else [])

    def _get_arrays(self, **kwargs):
        return _ok([SimpleNamespace(name=self.fleet)])

    def _get_object_store_accounts(self, **kwargs):
        refused = self._seen("get_object_store_accounts", kwargs)
        if refused:
            return refused
        keys = self._keys(kwargs["names"][0])
        if not all(key in self.accounts for key in keys):
            return _error(NO_ACCOUNT)
        return _ok(sorted((self.accounts[key] for key in keys), key=self._by_name))

    def _get_buckets(self, **kwargs):
        refused = self._seen("get_buckets", kwargs)
        if refused:
            return refused
        keys = self._keys(kwargs["names"][0])
        if not all(key in self.buckets and key not in self.hidden for key in keys):
            return _error(NO_BUCKET)
        return _ok(sorted((self.buckets[key] for key in keys), key=self._by_name))

    @staticmethod
    def _keys(name):
        """The objects a name addresses: a comma separates the names of a list"""
        return [part.strip().lower() for part in name.split(",")]

    @staticmethod
    def _by_name(item):
        return item.name

    def _post_buckets(self, **kwargs):
        name = kwargs["names"][0]
        body = kwargs["bucket"]
        self.writes.append(("POST", name, body))
        refused = self._seen("post_buckets", kwargs)
        if refused:
            return refused
        assert "," not in name, "POST for a list of names"
        name = name.strip()
        account = self.accounts[body["account"]["name"].strip().lower()]
        if name.rpartition("::")[0].lower() != account.name.rpartition("::")[0].lower():
            return _error(OTHER_REALM)
        assert name.lower() not in self.buckets, "POST for a bucket that exists"
        quota = body.get("quota_limit", account.bucket_defaults.quota_limit)
        if quota is not None and quota != "" and int(quota) < 1:
            return _error(QUOTA_RANGE)
        hard = body.get(
            "hard_limit_enabled", account.bucket_defaults.hard_limit_enabled
        )
        bucket = _bucket(name, account, quota=int(quota) if quota else None, hard=hard)
        bucket.bucket_type = body.get("bucket_type") or "multi-site-writable"
        self.buckets[name.lower()] = bucket
        return _ok([bucket])

    def _patch_buckets(self, **kwargs):
        name = kwargs["names"][0]
        body = kwargs["bucket"]
        self.writes.append(("PATCH", name, body))
        refused = self._seen("patch_buckets", kwargs)
        if refused:
            return refused
        if "," in name:
            return _error(ONE_NAME)
        bucket = self.buckets.get(name.strip().lower())
        if bucket is None:
            return _error(NO_BUCKET)
        for key in ("destroyed", "versioning", "retention_lock", "hard_limit_enabled"):
            if body.get(key) is not None:
                setattr(bucket, key, body[key])
        if "quota_limit" in body:
            bucket.quota_limit = (
                int(body["quota_limit"]) if body["quota_limit"] else None
            )
        for key, value in (body.get("public_access_config") or {}).items():
            if value is not None:
                setattr(bucket.public_access_config, key, value)
        for key, value in (body.get("object_lock_config") or {}).items():
            if key == "default_retention":
                value = int(value) if value else None
            elif key == "default_retention_mode":
                value = value or None
            elif value is None:
                continue
            setattr(bucket.object_lock_config, key, value)
        mode = (body.get("eradication_config") or {}).get("eradication_mode")
        if mode:
            bucket.eradication_config.eradication_mode = mode
        return _ok([bucket])

    def _delete_buckets(self, **kwargs):
        name = kwargs["names"][0]
        self.writes.append(("DELETE", name, None))
        refused = self._seen("delete_buckets", kwargs)
        if refused:
            return refused
        if "," in name:
            return _error(ONE_NAME)
        key = name.strip().lower()
        assert self.buckets[key].destroyed, "eradication of a live bucket"
        del self.buckets[key]
        return _ok()

    def _post_buckets_bucket_access_policies(self, **kwargs):
        self.writes.append(("POST policy", kwargs["bucket_names"][0], kwargs["policy"]))
        return self._seen("post_buckets_bucket_access_policies", kwargs) or _ok()

    def _post_buckets_bucket_access_policies_rules(self, **kwargs):
        self.writes.append(("POST rule", kwargs["bucket_names"][0], kwargs["rule"]))
        return self._seen("post_buckets_bucket_access_policies_rules", kwargs) or _ok()

    def bucket(self, name):
        return self.buckets[name.strip().lower()]

    def sent(self, verb):
        """The bodies of the requests of one kind, in the order they were sent."""
        return [body for kind, name, body in self.writes if kind == verb]


def _run(module, array, api_version="2.30", has_sdk=True):
    """Run main() against the array stand-in at the given REST version."""
    patches = [
        patch(MOD + ".AnsibleModule", return_value=module),
        patch(MOD + ".get_system", return_value=array.client),
        patch(MOD + ".get_rest_api_version", return_value=api_version),
        patch(MOD + ".LooseVersion", RealLooseVersion),
        patch(MOD + ".HAS_PYPURECLIENT", has_sdk),
        patch(MOD + ".get_error_message", side_effect=_error_message),
        patch(MOD + ".human_to_bytes", side_effect=_human_to_bytes),
    ]
    # request models become plain dicts, so that bodies can be compared
    patches += [
        patch(MOD + "." + model, side_effect=lambda **kw: kw) for model in MODELS
    ]
    for item in patches:
        item.start()
    try:
        main()
    except SystemExit:
        pass
    finally:
        for item in reversed(patches):
            item.stop()


def _changed(module):
    module.fail_json.assert_not_called()
    module.exit_json.assert_called_once()
    return module.exit_json.call_args[1]["changed"]


def _failure(module):
    """The message of the one and only fail_json; nothing may exit after it."""
    module.fail_json.assert_called_once()
    module.exit_json.assert_not_called()
    return module.fail_json.call_args[1]["msg"]


def _twins():
    """The same bucket name at array level and in a realm, each with a quota."""
    array_account = _account("bar")
    realm_account = _account("tenant1::bar")
    return _Array(
        accounts=[
            array_account,
            realm_account,
            _account("other"),
            _account("tenant1::other"),
        ],
        buckets=[
            _bucket("foo", array_account, quota=2 * GIB),
            _bucket("tenant1::foo", realm_account, quota=GIB),
        ],
    )


# every way a task can address an existing bucket: state, eradicate, destroyed
ADDRESSED = [
    ("present", False, False),
    ("absent", False, False),
    ("absent", True, False),
    ("present", False, True),
    ("absent", True, True),
]


class TestHelpers:
    """The private helpers"""

    @pytest.mark.parametrize(
        "name,realm",
        [
            ("foo", ""),
            ("tenant1::foo", "tenant1"),
            ("a::b::foo", "a::b"),
            (" foo", ""),
            (" tenant1::foo", "tenant1"),
        ],
    )
    def test_realm_of(self, name, realm):
        assert _realm_of(name) == realm

    @pytest.mark.parametrize("name", ["foo", "tenant1::foo", " foo "])
    def test_one_name_is_accepted(self, name):
        module = _module(name=name)
        _check_one_name(module)
        module.fail_json.assert_not_called()

    @pytest.mark.parametrize("name", ["foo,baz", "tenant1::foo,foo", "foo,"])
    def test_list_of_names_is_refused(self, name):
        module = _module(name=name)
        with pytest.raises(SystemExit):
            _check_one_name(module)
        assert module.fail_json.call_args[1]["msg"] == (
            "Bucket {0} is a list of names: a comma separates names, and a task "
            "manages one bucket.".format(name)
        )

    @pytest.mark.parametrize(
        "name,account",
        [
            ("foo", "bar"),
            ("tenant1::foo", "tenant1::bar"),
            ("TENANT1::foo", "tenant1::bar"),
            (" tenant1::foo", "tenant1::bar"),
            ("tenant1::foo", " tenant1::bar"),
        ],
    )
    def test_same_realm_is_accepted(self, name, account):
        module = _module(name=name, account=account)
        _check_same_realm(module)
        module.fail_json.assert_not_called()

    @pytest.mark.parametrize(
        "name,account,hint",
        [
            ("foo", "tenant1::bar", "is named tenant1::<bucket>"),
            ("tenant1::foo", "bar", "named tenant1::<account>"),
            ("tenant2::foo", "tenant1::bar", "is named tenant1::<bucket>"),
        ],
    )
    def test_other_realm_is_refused(self, name, account, hint):
        module = _module(name=name, account=account)
        with pytest.raises(SystemExit):
            _check_same_realm(module)
        msg = module.fail_json.call_args[1]["msg"]
        assert "must be in the same realm" in msg
        assert name in msg and account in msg and hint in msg

    def test_account_with_the_same_id_is_the_owner(self):
        account = _account("bar")
        module = _module(account="BAR")
        _check_account(module, _bucket("foo", account), account)
        module.fail_json.assert_not_called()

    def test_account_with_another_id_is_not_the_owner(self):
        module = _module(account="other")
        with pytest.raises(SystemExit):
            _check_account(module, _bucket("foo", _account("bar")), _account("other"))
        assert module.fail_json.call_args[1]["msg"] == (
            "Bucket foo belongs to Object Store Account bar, not other."
        )

    @pytest.mark.parametrize("asked,same", [("BAR", True), ("other", False)])
    def test_names_decide_when_an_id_is_missing(self, asked, same):
        bucket = _bucket("foo", _account("bar"))
        bucket.account.id = None
        module = _module(account=asked)
        if same:
            _check_account(module, bucket, _account(asked))
            module.fail_json.assert_not_called()
        else:
            with pytest.raises(SystemExit):
                _check_account(module, bucket, _account(asked))

    def test_bucket_without_an_account_reference_is_not_judged(self):
        bucket = _bucket("foo", _account("bar"))
        bucket.account = None
        module = _module(account="other")
        _check_account(module, bucket, _account("other"))
        module.fail_json.assert_not_called()

    def test_get_one_returns_the_item(self):
        item = object()
        assert _get_one(_module(), _ok([item]), "Object Store Bucket", "foo") is item

    def test_get_one_without_items_is_absent(self):
        assert _get_one(_module(), _ok([]), "Object Store Bucket", "foo") is None

    def test_get_one_fails_on_more_than_one_item(self):
        module = _module()
        with pytest.raises(SystemExit):
            _get_one(
                module, _ok([object(), object()]), "Object Store Account", "bar,other"
            )
        assert module.fail_json.call_args[1]["msg"] == (
            "Object Store Account bar,other matches 2 objects. The name of one "
            "Object Store Account is needed."
        )

    @pytest.mark.parametrize("message", [NO_BUCKET, NO_ACCOUNT, NO_REALM])
    def test_get_one_does_not_exist_is_absent(self, message):
        module = _module()
        with patch(MOD + ".get_error_message", side_effect=_error_message):
            assert (
                _get_one(module, _error(message), "Object Store Bucket", "foo") is None
            )
        module.fail_json.assert_not_called()

    def test_get_one_fails_on_any_other_answer(self):
        module = _module()
        with patch(MOD + ".get_error_message", side_effect=_error_message):
            with pytest.raises(SystemExit):
                _get_one(
                    module, _error(NOT_PERMITTED, 403), "Object Store Bucket", "foo"
                )
        assert module.fail_json.call_args[1]["msg"] == (
            "Failed to get Object Store Bucket foo. Error: Operation not permitted."
        )


class TestSameRealm:
    """A bucket and an account that are not in the same realm are refused"""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("state,eradicate,destroyed", ADDRESSED)
    @pytest.mark.parametrize(
        "name,account,namesake",
        [
            ("foo", "tenant1::bar", "foo"),
            ("tenant1::foo", "bar", "tenant1::foo"),
            ("tenant1::foo", "tenant2::bar", "tenant1::foo"),
        ],
    )
    def test_namesake_outside_the_realm_of_the_account_is_left_alone(
        self, name, account, namesake, state, eradicate, destroyed, check_mode
    ):
        array = _twins()
        array.accounts["tenant2::bar"] = _account("tenant2::bar")
        array.bucket(namesake).destroyed = destroyed
        before = (array.bucket(namesake).quota_limit, destroyed)
        module = _module(
            check_mode=check_mode,
            name=name,
            account=account,
            state=state,
            eradicate=eradicate,
            quota="3G",
        )
        _run(module, array)
        assert "must be in the same realm" in _failure(module)
        # decided from the names: the array is not even asked
        assert array.client.mock_calls == []
        after = array.bucket(namesake)
        assert (after.quota_limit, after.destroyed) == before

    def test_bucket_is_not_created_for_such_a_pair(self):
        array = _Array(accounts=[_account("tenant1::bar")])
        module = _module(name="foo", account="tenant1::bar")
        _run(module, array)
        assert _failure(module) == (
            "Bucket foo cannot belong to Object Store Account tenant1::bar: a "
            "bucket and its account must be in the same realm. A bucket of this "
            "account is named tenant1::<bucket>."
        )
        assert array.writes == []


class TestAccountOwnership:
    """A bucket of another account is not the bucket the task describes"""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("state,eradicate,destroyed", ADDRESSED)
    @pytest.mark.parametrize(
        "name,account,owner",
        [("foo", "other", "bar"), ("tenant1::foo", "tenant1::other", "tenant1::bar")],
    )
    def test_bucket_of_another_account_is_left_alone(
        self, name, account, owner, state, eradicate, destroyed, check_mode
    ):
        array = _twins()
        array.bucket(name).destroyed = destroyed
        before = (array.bucket(name).quota_limit, destroyed)
        module = _module(
            check_mode=check_mode,
            name=name,
            account=account,
            state=state,
            eradicate=eradicate,
            quota="3G",
        )
        _run(module, array)
        assert _failure(module) == (
            "Bucket {0} belongs to Object Store Account {1}, not {2}.".format(
                name, owner, account
            )
        )
        assert array.writes == []
        after = array.bucket(name)
        assert (after.quota_limit, after.destroyed) == before


class TestNames:
    """A list of names is not one bucket; blanks around a name are ignored"""

    @staticmethod
    def _array(destroyed=False):
        # baz belongs to another account than foo and tenant1::foo
        array = _twins()
        array.buckets["baz"] = _bucket("baz", array.accounts["other"], quota=2 * GIB)
        for bucket in array.buckets.values():
            bucket.destroyed = destroyed
        return array

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("state,eradicate,destroyed", ADDRESSED)
    @pytest.mark.parametrize(
        "name,account",
        [
            ("foo,baz", "bar"),
            ("baz,foo", "bar"),
            ("tenant1::foo,baz", "tenant1::bar"),
            ("foo,foo", "bar"),
        ],
    )
    def test_list_of_bucket_names_is_refused(
        self, name, account, state, eradicate, destroyed, check_mode
    ):
        array = self._array(destroyed)
        module = _module(
            check_mode=check_mode,
            name=name,
            account=account,
            state=state,
            eradicate=eradicate,
            quota="3G",
        )
        _run(module, array)
        assert _failure(module) == (
            "Bucket {0} is a list of names: a comma separates names, and a task "
            "manages one bucket.".format(name)
        )
        # decided from the name: the array is not even asked
        assert array.client.mock_calls == []
        for bucket in array.buckets.values():
            assert bucket.destroyed is destroyed
            assert bucket.quota_limit in (GIB, 2 * GIB)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_list_of_new_bucket_names_is_not_created(self, check_mode):
        array = _Array(accounts=[_account("bar")])
        module = _module(check_mode=check_mode, name="new1,new2")
        _run(module, array)
        assert "is a list of names" in _failure(module)
        assert array.client.mock_calls == []

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_list_of_account_names_is_refused(self, state, check_mode):
        array = self._array()
        module = _module(
            check_mode=check_mode, account="bar,other", state=state, quota="3G"
        )
        _run(module, array)
        assert _failure(module) == (
            "Object Store Account bar,other matches 2 objects. The name of one "
            "Object Store Account is needed."
        )
        assert array.writes == []

    @pytest.mark.parametrize(
        "name,account",
        [
            (" foo", "bar"),
            ("foo", " bar "),
            (" tenant1::foo", "tenant1::bar"),
            ("tenant1::foo ", " tenant1::bar"),
        ],
    )
    def test_blanks_around_a_name_are_ignored(self, name, account):
        array = self._array()
        module = _module(name=name, account=account, quota="3G")
        _run(module, array)
        assert _changed(module) is True
        assert array.bucket(name).quota_limit == 3 * GIB
        again = _module(name=name, account=account, quota="3G")
        _run(again, array)
        assert _changed(again) is False

    def test_blank_padded_account_of_another_bucket_is_still_refused(self):
        array = self._array()
        array.bucket("foo").account.id = None
        module = _module(name="foo", account=" other ", quota="3G")
        _run(module, array)
        assert _failure(module) == (
            "Bucket foo belongs to Object Store Account bar, not  other ."
        )
        assert array.writes == []

    def test_blank_padded_account_without_an_id_is_the_owner(self):
        array = self._array()
        array.bucket("foo").account.id = None
        module = _module(name="foo", account=" BAR ", quota="3G")
        _run(module, array)
        assert _changed(module) is True


class TestReads:
    """A read the array refuses is reported, never taken for a missing object"""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_refused_bucket_read_fails_with_the_array_message(self, state, check_mode):
        array = _twins()
        array.refuse["get_buckets"] = NOT_PERMITTED
        module = _module(check_mode=check_mode, state=state)
        _run(module, array)
        assert _failure(module) == (
            "Failed to get Object Store Bucket foo. Error: Operation not permitted."
        )
        assert array.writes == []

    def test_refused_account_read_fails_with_the_array_message(self):
        array = _twins()
        array.refuse["get_object_store_accounts"] = NOT_PERMITTED
        module = _module()
        _run(module, array)
        assert _failure(module) == (
            "Failed to get Object Store Account bar. Error: Operation not permitted."
        )
        assert array.writes == []

    def test_update_reads_the_bucket_once(self):
        array = _twins()
        module = _module(quota="3G")
        _run(module, array)
        assert _changed(module) is True
        assert array.client.get_buckets.call_count == 1

    def test_create_reads_the_account_once(self):
        array = _Array(accounts=[_account("bar")])
        module = _module()
        _run(module, array)
        assert _changed(module) is True
        assert array.client.get_object_store_accounts.call_count == 1


class TestRefusedCreate:
    """A create the array refuses fails with its message and sends nothing more"""

    @pytest.mark.parametrize("message", [OTHER_REALM, NO_REALM, QUOTA_RANGE])
    def test_refusal_is_reported_and_nothing_is_rolled_back(self, message):
        array = _Array(accounts=[_account("bar")])
        array.refuse["post_buckets"] = message
        module = _module()
        _run(module, array)
        assert _failure(module) == (
            "Object Store Bucket foo creation failed. Error: " + message
        )
        assert [kind for kind, name, body in array.writes] == ["POST"]

    def test_bucket_of_that_name_is_never_destroyed(self):
        # the bucket appears between the read and the create
        array = _twins()
        array.hidden.add("foo")
        array.refuse["post_buckets"] = OTHER_REALM
        module = _module()
        _run(module, array)
        assert OTHER_REALM in _failure(module)
        assert array.sent("PATCH") == [] and array.sent("DELETE") == []
        assert array.bucket("foo").destroyed is False

    def test_quota_the_array_refuses(self):
        array = _Array(accounts=[_account("bar")])
        module = _module(quota="0B")
        _run(module, array)
        assert _failure(module) == (
            "Object Store Bucket foo creation failed. Error: " + QUOTA_RANGE
        )
        assert array.buckets == {}

    def test_versioning_on_an_old_rest_version(self):
        array = _Array(accounts=[_account("bar")])
        module = _module(versioning="enabled")
        _run(module, array, api_version="2.4")
        assert _changed(module) is True
        assert array.sent("POST") == [{"account": {"name": "bar"}}]
        assert array.sent("PATCH") == [{"versioning": "enabled"}]
        assert array.bucket("foo").versioning == "enabled"


class TestCreateLimits:
    """Limits the task leaves out are left to the bucket defaults of the account"""

    @staticmethod
    def _array(account="bar"):
        # the account's own quota differs from its default for new buckets
        return _Array(
            accounts=[
                _account(
                    account,
                    quota=2 * GIB,
                    hard=True,
                    default_quota=GIB,
                    default_hard=False,
                )
            ]
        )

    @pytest.mark.parametrize(
        "name,account", [("foo", "bar"), ("tenant1::foo", "tenant1::bar")]
    )
    def test_no_limits_asked_for(self, name, account):
        array = self._array(account)
        module = _module(name=name, account=account)
        _run(module, array)
        assert _changed(module) is True
        assert array.sent("POST") == [
            {"account": {"name": account}, "bucket_type": "multi-site-writable"}
        ]
        assert array.bucket(name).quota_limit == GIB
        assert array.bucket(name).hard_limit_enabled is False

    def test_quota_only(self):
        array = self._array()
        module = _module(quota="3G")
        _run(module, array)
        assert _changed(module) is True
        assert array.sent("POST")[0] == {
            "account": {"name": "bar"},
            "bucket_type": "multi-site-writable",
            "quota_limit": str(3 * GIB),
        }
        assert array.bucket("foo").hard_limit_enabled is False

    @pytest.mark.parametrize("hard_limit", [True, False])
    def test_hard_limit_only(self, hard_limit):
        array = self._array()
        module = _module(hard_limit=hard_limit)
        _run(module, array)
        assert _changed(module) is True
        assert array.sent("POST")[0] == {
            "account": {"name": "bar"},
            "bucket_type": "multi-site-writable",
            "hard_limit_enabled": hard_limit,
        }
        assert array.bucket("foo").quota_limit == GIB

    @pytest.mark.parametrize("hard_limit", [None, True])
    def test_quota_zero_is_an_unlimited_bucket(self, hard_limit):
        array = self._array()
        module = _module(quota="0", hard_limit=hard_limit)
        _run(module, array)
        assert _changed(module) is True
        assert array.sent("POST")[0] == {
            "account": {"name": "bar"},
            "bucket_type": "multi-site-writable",
            "quota_limit": "",
            "hard_limit_enabled": False,
        }
        assert array.bucket("foo").quota_limit is None
        # and the same task finds nothing to change afterwards
        again = _module(quota="0", hard_limit=hard_limit)
        _run(again, array)
        assert _changed(again) is False


class TestCreate:
    """Creating a bucket"""

    def test_check_mode_sends_nothing(self):
        array = _Array(accounts=[_account("bar")])
        module = _module(check_mode=True, quota="1G", versioning="enabled")
        _run(module, array)
        assert _changed(module) is True
        assert array.writes == []

    def test_create_then_unchanged(self):
        array = _Array(accounts=[_account("bar")])
        module = _module(quota="1G", hard_limit=True)
        _run(module, array)
        assert _changed(module) is True
        assert array.sent("POST") == [
            {
                "account": {"name": "bar"},
                "bucket_type": "multi-site-writable",
                "quota_limit": str(GIB),
                "hard_limit_enabled": True,
            }
        ]
        writes = len(array.writes)
        again = _module(quota="1G", hard_limit=True)
        _run(again, array)
        assert _changed(again) is False
        assert len(array.writes) == writes

    def test_realm_bucket_next_to_an_array_level_namesake(self):
        array = _twins()
        del array.buckets["tenant1::foo"]
        module = _module(name="tenant1::foo", account="tenant1::bar", quota="1G")
        _run(module, array)
        assert _changed(module) is True
        assert array.bucket("tenant1::foo").account.name == "tenant1::bar"
        assert array.bucket("foo").quota_limit == 2 * GIB

    def test_versioning_and_object_lock(self):
        array = _Array(accounts=[_account("bar")])
        module = _module(
            versioning="enabled",
            object_lock_enabled=True,
            retention_mode="governance",
            default_retention="7d",
        )
        _run(module, array)
        assert _changed(module) is True
        assert array.sent("PATCH") == [
            {
                "retention_lock": "unlocked",
                "object_lock_config": {
                    "default_retention_mode": "governance",
                    "enabled": True,
                    "freeze_locked_objects": False,
                    "default_retention": str(7 * 86400000),
                },
                "versioning": "enabled",
            }
        ]
        bucket = array.bucket("foo")
        assert bucket.versioning == "enabled"
        assert bucket.object_lock_config.default_retention == 7 * 86400000

    def test_public_bucket(self):
        array = _Array(accounts=[_account("bar")])
        module = _module(block_new_public_policies=False, block_public_access=False)
        _run(module, array)
        assert _changed(module) is True
        assert array.sent("POST policy") == [{"name": "foo"}]
        assert array.sent("POST rule")[0]["resources"] == ["foo/*"]
        assert array.bucket("foo").public_access_config.block_public_access is False

    def test_eradication_mode(self):
        array = _Array(accounts=[_account("bar")])
        module = _module(eradication_mode="retention-based")
        _run(module, array)
        assert _changed(module) is True
        assert array.bucket("foo").eradication_config.eradication_mode == (
            "retention-based"
        )

    def test_refused_setting_after_the_create_is_reported(self):
        array = _Array(accounts=[_account("bar")])
        array.refuse["patch_buckets"] = NOT_PERMITTED
        module = _module()
        _run(module, array)
        assert _failure(module) == (
            "Object Store Bucket foo creation update failed. Error: " + NOT_PERMITTED
        )

    @pytest.mark.parametrize(
        "api_version,body",
        [
            (
                "2.12",
                {"account": {"name": "bar"}, "bucket_type": "multi-site-writable"},
            ),
            ("2.8", {"account": {"name": "bar"}, "bucket_type": "classic"}),
            ("2.7", {"account": {"name": "bar"}, "bucket_type": "classic"}),
        ],
    )
    def test_default_mode_by_rest_version(self, api_version, body):
        array = _Array(accounts=[_account("bar")])
        module = _module()
        _run(module, array, api_version=api_version)
        assert _changed(module) is True
        assert array.sent("POST") == [body]

    def test_fleet_member_sends_its_context(self):
        array = _Array(accounts=[_account("bar")], fleet="array1")
        module = _module(quota="1G")
        _run(module, array)
        assert _changed(module) is True
        assert array.contexts and set(map(tuple, array.contexts)) == {("array1",)}

    def test_context_is_not_sent_below_its_rest_version(self):
        array = _Array(accounts=[_account("bar")])
        module = _module(context="array2")
        _run(module, array, api_version="2.16")
        assert _changed(module) is True
        assert set(array.contexts) == {None}


class TestUpdate:
    """Changing an existing bucket"""

    @pytest.mark.parametrize(
        "current,asked,result",
        [
            ("none", "enabled", "enabled"),
            ("none", "suspended", "suspended"),
            ("none", "absent", None),
            ("enabled", "suspended", "suspended"),
            ("enabled", "absent", "suspended"),
            ("enabled", "enabled", None),
            ("suspended", "absent", None),
            ("enabled", None, None),
        ],
    )
    def test_versioning(self, current, asked, result):
        array = _twins()
        array.bucket("foo").versioning = current
        module = _module(versioning=asked)
        _run(module, array)
        assert _changed(module) is (result is not None)
        assert array.sent("PATCH") == ([{"versioning": result}] if result else [])

    def test_quota_and_hard_limit(self):
        array = _twins()
        module = _module(quota="3G", hard_limit=True)
        _run(module, array)
        assert _changed(module) is True
        assert array.sent("PATCH") == [
            {"quota_limit": str(3 * GIB), "hard_limit_enabled": True}
        ]
        again = _module(quota="3G", hard_limit=True)
        _run(again, array)
        assert _changed(again) is False
        # the namesake in the realm keeps its quota
        assert array.bucket("tenant1::foo").quota_limit == GIB

    def test_quota_zero_removes_the_limit(self):
        array = _twins()
        module = _module(quota="0")
        _run(module, array)
        assert _changed(module) is True
        assert array.sent("PATCH") == [{"quota_limit": "", "hard_limit_enabled": False}]
        again = _module(quota="0")
        _run(again, array)
        assert _changed(again) is False

    def test_realm_bucket(self):
        array = _twins()
        module = _module(name="tenant1::foo", account="tenant1::bar", quota="3G")
        _run(module, array)
        assert _changed(module) is True
        assert array.bucket("tenant1::foo").quota_limit == 3 * GIB
        assert array.bucket("foo").quota_limit == 2 * GIB

    @pytest.mark.parametrize(
        "name,account",
        [
            ("FOO", "BAR"),
            ("TENANT1::foo", "tenant1::BAR"),
            ("tenant1::FOO", "Tenant1::bar"),
        ],
    )
    def test_names_in_another_case_are_the_same_objects(self, name, account):
        array = _twins()
        module = _module(name=name, account=account, quota="3G")
        _run(module, array)
        assert _changed(module) is True
        assert array.bucket(name).quota_limit == 3 * GIB

    def test_public_access_blocks(self):
        array = _twins()
        module = _module(block_public_access=False)
        _run(module, array)
        assert _changed(module) is True
        assert array.sent("PATCH") == [
            {
                "public_access_config": {
                    "block_new_public_policies": True,
                    "block_public_access": False,
                }
            }
        ]
        again = _module(block_public_access=False)
        _run(again, array)
        assert _changed(again) is False

    def test_eradication_mode(self):
        array = _twins()
        module = _module(eradication_mode="retention-based")
        _run(module, array)
        assert _changed(module) is True
        assert array.sent("PATCH") == [
            {"eradication_config": {"eradication_mode": "retention-based"}}
        ]
        again = _module(eradication_mode="retention-based")
        _run(again, array)
        assert _changed(again) is False

    def test_object_lock_and_retention_lock(self):
        array = _twins()
        params = dict(
            object_lock_enabled=True,
            retention_mode="governance",
            default_retention="2",
            retention_lock="ratcheted",
        )
        module = _module(**params)
        _run(module, array)
        assert _changed(module) is True
        assert array.sent("PATCH") == [
            {
                "object_lock_config": {
                    "enabled": True,
                    "default_retention_mode": "governance",
                    "default_retention": str(2 * 86400000),
                }
            },
            {"retention_lock": "ratcheted"},
        ]
        again = _module(**params)
        _run(again, array)
        assert _changed(again) is False

    def test_check_mode_sends_nothing(self):
        array = _twins()
        module = _module(
            check_mode=True,
            quota="3G",
            versioning="enabled",
            block_public_access=False,
            eradication_mode="retention-based",
            object_lock_enabled=True,
        )
        _run(module, array)
        assert _changed(module) is True
        assert array.writes == []

    def test_nothing_asked_changes_nothing(self):
        array = _twins()
        module = _module()
        _run(module, array)
        assert _changed(module) is False
        assert array.writes == []

    def test_bucket_type_cannot_be_changed(self):
        array = _twins()
        module = _module(mode="classic")
        _run(module, array)
        assert _changed(module) is False
        module.warn.assert_called_once_with("Changing bucket type is not permitted.")

    @pytest.mark.parametrize(
        "params,message",
        [
            ({"versioning": "enabled"}, "versioning change failed"),
            ({"quota": "3G"}, "Failed to update quota settings"),
            ({"block_public_access": False}, "Failed to update Public Access config"),
            ({"eradication_mode": "retention-based"}, "Failed to update Eradication"),
            ({"object_lock_enabled": True}, "Failed to update object lock config"),
            ({"retention_lock": "ratcheted"}, "Failed to set retention_lock"),
        ],
    )
    def test_refused_change_is_reported(self, params, message):
        array = _twins()
        array.refuse["patch_buckets"] = NOT_PERMITTED
        module = _module(**params)
        _run(module, array)
        failure = _failure(module)
        assert message in failure and failure.endswith("Error: " + NOT_PERMITTED)


class TestDeleteRecover:
    """Destroying, eradicating and recovering a bucket"""

    @pytest.mark.parametrize(
        "name,account", [("foo", "bar"), ("tenant1::foo", "tenant1::bar")]
    )
    def test_destroy_recover_eradicate(self, name, account):
        array = _twins()
        twin = "foo" if name != "foo" else "tenant1::foo"

        module = _module(name=name, account=account, state="absent")
        _run(module, array)
        assert _changed(module) is True
        assert array.bucket(name).destroyed is True
        again = _module(name=name, account=account, state="absent")
        _run(again, array)
        assert _changed(again) is False

        module = _module(name=name, account=account)
        _run(module, array)
        assert _changed(module) is True
        assert array.bucket(name).destroyed is False

        module = _module(name=name, account=account, state="absent", eradicate=True)
        _run(module, array)
        assert _changed(module) is True
        assert name not in array.buckets
        again = _module(name=name, account=account, state="absent", eradicate=True)
        _run(again, array)
        assert _changed(again) is False

        assert array.bucket(twin).destroyed is False

    def test_eradicate_a_destroyed_bucket(self):
        array = _twins()
        array.bucket("foo").destroyed = True
        module = _module(state="absent", eradicate=True)
        _run(module, array)
        assert _changed(module) is True
        assert [kind for kind, name, body in array.writes] == ["DELETE"]

    @pytest.mark.parametrize(
        "state,eradicate,destroyed", [s for s in ADDRESSED if s[0] != "present" or s[2]]
    )
    def test_check_mode_sends_nothing(self, state, eradicate, destroyed):
        array = _twins()
        array.bucket("foo").destroyed = destroyed
        module = _module(check_mode=True, state=state, eradicate=eradicate)
        _run(module, array)
        assert _changed(module) is True
        assert array.writes == []

    def test_missing_bucket_is_absent(self):
        array = _Array(accounts=[_account("bar")])
        module = _module(state="absent", eradicate=True)
        _run(module, array)
        assert _changed(module) is False
        assert array.writes == []

    @pytest.mark.parametrize(
        "state,eradicate,destroyed,method,message",
        [
            ("absent", False, False, "patch_buckets", "Deletion for bucket foo failed"),
            (
                "absent",
                True,
                False,
                "delete_buckets",
                "Eradication for bucket foo failed",
            ),
            ("absent", True, True, "delete_buckets", "Bucket foo eradication failed"),
            ("present", False, True, "patch_buckets", "Bucket foo Recovery failed"),
        ],
    )
    def test_refusal_is_reported(self, state, eradicate, destroyed, method, message):
        array = _twins()
        array.bucket("foo").destroyed = destroyed
        array.refuse[method] = NOT_PERMITTED
        module = _module(state=state, eradicate=eradicate)
        _run(module, array)
        failure = _failure(module)
        assert message in failure and failure.endswith("Error: " + NOT_PERMITTED)


class TestArguments:
    """Requests that are refused before anything is sent"""

    def test_sdk_is_required(self):
        module = _module()
        _run(module, _twins(), has_sdk=False)
        assert _failure(module) == "py-pure-client sdk is required"

    @pytest.mark.parametrize(
        "option,value", [("eradication_delay", 2), ("manual_eradication", True)]
    )
    def test_array_wide_eradication_settings(self, option, value):
        array = _twins()
        module = _module(**{option: value})
        _run(module, array)
        assert "read-only on a bucket" in _failure(module)
        assert array.client.mock_calls == []

    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_missing_account(self, state):
        array = _twins()
        module = _module(account="nope", state=state)
        _run(module, array)
        assert _failure(module) == "Object Store Account nope does not exist."
        assert array.writes == []

    def test_quota_above_the_maximum(self):
        array = _twins()
        module = _module(quota="9000P")
        _run(module, array)
        assert _failure(module) == "Quota must not exceed 9.22 exabytes"
        assert array.writes == []

    def test_eradicate_needs_state_absent(self):
        array = _twins()
        module = _module(eradicate=True)
        _run(module, array)
        assert _changed(module) is False
        module.warn.assert_called_once_with(
            "Eradicate flag ignored without state=absent"
        )
