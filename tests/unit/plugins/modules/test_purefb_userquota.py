# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_userquota module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from fnmatch import fnmatchcase
from unittest.mock import Mock, patch, MagicMock

import pytest
import yaml

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
from plugins.modules.purefb_userquota import (
    DOCUMENTATION,
    EXAMPLES,
    get_quota,
    main,
)

MOD = "plugins.modules.purefb_userquota"
FQCN = "everpure.flashblade.purefb_userquota"
GIB = 1024**3
FS = "foo"
REALM_FS = "tenant1::foo"
OTHER_REALM_FS = "tenant2::foo"
ARRAY = "array1"
REFUSED = "refused"
# Messages of the array, as Purity//FB 4.8.8 sends them
NO_FS = "File system does not exist."
NO_MATCH = "File system was not found."
MANY_FS = "Cannot process more than one File system at a time."
NOT_PERMITTED = "Operation not permitted."
NO_NAMES = (
    "Cannot manage quotas using user names without either the NFS directory "
    "service enabled or an Active Directory configuration created with service "
    "principal names for the NFS service."
)


def _base_params(**overrides):
    params = {
        "name": FS,
        "uid": None,
        "uname": None,
        "state": "present",
        "quota": None,
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


def _named(name):
    item = Mock()
    item.name = name
    return item


def _response(items=None):
    """A 200 answer of the SDK."""
    res = Mock(spec=["status_code", "items", "total_item_count"])
    res.status_code = 200
    res.items = items if items is not None else []
    res.total_item_count = len(res.items)
    return res


def _error(message, status_code=400):
    """An error answer of the SDK: it has no items and no item count."""
    res = Mock(spec=["status_code", "errors"])
    res.status_code = status_code
    err = Mock()
    err.message = message
    res.errors = [err]
    return res


def _quota(file_system, user, quota):
    """A user quota as the array returns it, named <file system>/<uid>."""
    item = Mock()
    item.name = "{0}/{1}".format(file_system, user)
    item.file_system.name = file_system
    item.quota = quota
    item.usage = 0
    item.user.id = user if isinstance(user, int) else None
    item.user.name = None if isinstance(user, int) else user
    return item


def _filter_user(text):
    """The user a filter of the module selects: a uid or a user name."""
    key, _sep, value = text.partition("=")
    if key == "user.id":
        return int(value)
    assert key == "user.name" and value.startswith("'") and value.endswith("'")
    return value[1:-1]


def _write_user(kwargs):
    """The user a POST, PATCH or DELETE of the module addresses."""
    assert ("uids" in kwargs) != ("user_names" in kwargs)
    return kwargs["uids"][0] if "uids" in kwargs else kwargs["user_names"][0]


def _blade(file_systems=(FS,), quotas=None, fleet=None, hidden=()):
    """A small stateful stand-in for the array.

    file_systems are the names the array knows; any other name answers 400.
    hidden are file systems outside the realm of a realm-scoped administrator:
    GET /file-systems answers 200 with no item for them and their quotas
    answer 400. quotas maps (file system, user) to a limit in bytes, where
    user is the uid or the user name of the task. POST, PATCH and DELETE
    change that state so that a later GET reads it back.

    The SDK sends a name as it is given. GET /file-systems reads a comma as
    a list of names and a * as a pattern and answers with every match; the
    quota endpoints take one file system, so they refuse a list and know no
    file system by the name of a pattern.

    fleet "member" puts the array in a fleet, REFUSED makes the fleet read
    fail the way it does for a realm-scoped administrator. blade.fail maps
    "get", "post", "patch" or "delete" to the message of a refused quota
    request.
    """
    blade = Mock()
    blade.quotas = dict(quotas or {})
    blade.fail = {}

    def _visible(name):
        return name in file_systems and name not in hidden

    def _selected(name, part):
        if "*" in part:
            return fnmatchcase(name, part)
        return name == part

    def _get_file_systems(**kwargs):
        name = kwargs["names"][0]
        parts = name.split(",")
        found = [
            known
            for known in file_systems
            if any(_selected(known, part) for part in parts)
        ]
        if not found:
            return _error(NO_MATCH if "*" in name else NO_FS)
        return _response([_named(known) for known in found if known not in hidden])

    def _get(**kwargs):
        name = kwargs["file_system_names"][0]
        if "get" in blade.fail:
            return _error(blade.fail["get"])
        if "," in name:
            return _error(MANY_FS)
        if not _visible(name):
            return _error(NO_FS)
        user = _filter_user(kwargs["filter"])
        if (name, user) not in blade.quotas:
            return _response([])
        return _response([_quota(name, user, blade.quotas[(name, user)])])

    def _post(**kwargs):
        name = kwargs["file_system_names"][0]
        if "post" in blade.fail or not _visible(name):
            return _error(blade.fail.get("post", NO_FS))
        blade.quotas[(name, _write_user(kwargs))] = kwargs["quota"]["quota"]
        return _response()

    def _patch(**kwargs):
        name = kwargs["file_system_names"][0]
        if "patch" in blade.fail or not _visible(name):
            return _error(blade.fail.get("patch", NO_FS))
        blade.quotas[(name, _write_user(kwargs))] = kwargs["quota"]["quota"]
        return _response()

    def _delete(**kwargs):
        name = kwargs["file_system_names"][0]
        if "delete" in blade.fail or not _visible(name):
            return _error(blade.fail.get("delete", NO_FS))
        del blade.quotas[(name, _write_user(kwargs))]
        return _response()

    blade.get_file_systems = Mock(side_effect=_get_file_systems)
    blade.get_quotas_users = Mock(side_effect=_get)
    blade.post_quotas_users = Mock(side_effect=_post)
    blade.patch_quotas_users = Mock(side_effect=_patch)
    blade.delete_quotas_users = Mock(side_effect=_delete)
    if fleet == REFUSED:
        blade.get_fleets = Mock(return_value=_error(NOT_PERMITTED))
    else:
        blade.get_fleets = Mock(
            return_value=_response([_named("fleet1")] if fleet else [])
        )
    blade.get_arrays = Mock(return_value=_response([_named(ARRAY)]))
    return blade


def _get_filesystem(module, blade):
    """What module_utils.common.get_filesystem does: one read by the task's name."""
    res = blade.get_file_systems(names=[module.params["name"]])
    if res.status_code == 200:
        items = list(res.items)
        if items:
            return items[0]
    return None


def _get_error_message(res):
    return res.errors[0].message


def _run(module, blade, api_version="2.30", has_sdk=True):
    """Run main() against the stand-in; returns the patched AnsibleModule."""
    patchers = [
        patch(MOD + ".AnsibleModule", return_value=module),
        patch(MOD + ".get_system", return_value=blade),
        patch(MOD + ".get_rest_api_version", return_value=api_version),
        patch(MOD + ".get_filesystem", side_effect=_get_filesystem),
        patch(MOD + ".get_error_message", side_effect=_get_error_message),
        patch(MOD + ".purefb_argument_spec", return_value={}),
        patch(MOD + ".LooseVersion", RealLooseVersion),
        patch(MOD + ".HAS_PYPURECLIENT", has_sdk),
        patch(MOD + ".UserQuotaPost", side_effect=lambda **kw: kw),
        patch(MOD + ".UserQuotaPatch", side_effect=lambda **kw: kw),
    ]
    started = [patcher.start() for patcher in patchers]
    try:
        main()
    except SystemExit:
        pass
    finally:
        for patcher in patchers:
            patcher.stop()
    return started[0]


def _lookup(module, blade, api_version="2.30"):
    """Call get_quota() the way main() does."""
    with patch(MOD + ".LooseVersion", RealLooseVersion), patch(
        MOD + ".get_rest_api_version", return_value=api_version
    ), patch(MOD + ".get_error_message", side_effect=_get_error_message):
        return get_quota(module, blade)


def _changed(module):
    module.fail_json.assert_not_called()
    module.exit_json.assert_called_once()
    return module.exit_json.call_args[1]["changed"]


def _failure(module):
    """The message of the one and only fail_json; nothing may exit after it."""
    module.fail_json.assert_called_once()
    module.exit_json.assert_not_called()
    return module.fail_json.call_args[1]["msg"]


def _kwargs(mocked):
    """The keyword arguments of the only call a blade method received."""
    mocked.assert_called_once()
    return mocked.call_args[1]


def _no_writes(blade):
    blade.post_quotas_users.assert_not_called()
    blade.patch_quotas_users.assert_not_called()
    blade.delete_quotas_users.assert_not_called()


class TestGetQuota:
    """The read of one quota of one file system"""

    def test_uid_is_looked_up_by_user_id(self):
        blade = _blade(quotas={(FS, 1234): GIB})
        found = _lookup(_module(uid=1234), blade)
        assert found.quota == GIB
        assert found.name == "foo/1234"
        assert _kwargs(blade.get_quotas_users) == {
            "file_system_names": [FS],
            "filter": "user.id=1234",
        }

    def test_uid_zero_is_looked_up_by_user_id(self):
        blade = _blade(quotas={(FS, 0): GIB})
        found = _lookup(_module(uid=0), blade)
        assert found.user.id == 0
        assert _kwargs(blade.get_quotas_users)["filter"] == "user.id=0"

    def test_uname_is_looked_up_by_user_name(self):
        blade = _blade(quotas={(FS, "bar"): 2 * GIB})
        found = _lookup(_module(uname="bar"), blade)
        assert found.quota == 2 * GIB
        assert _kwargs(blade.get_quotas_users) == {
            "file_system_names": [FS],
            "filter": "user.name='bar'",
        }

    @pytest.mark.parametrize("user", [{"uid": 1234}, {"uname": "bar"}])
    def test_no_quota_is_none(self, user):
        blade = _blade(quotas={(FS, 99): GIB, (FS, "other"): GIB})
        assert _lookup(_module(**user), blade) is None

    @pytest.mark.parametrize("user", [{"uid": 1234}, {"uname": "bar"}])
    def test_context_is_sent_from_rest_2_17(self, user):
        blade = _blade()
        _lookup(_module(context="array2", **user), blade, api_version="2.17")
        assert _kwargs(blade.get_quotas_users)["context_names"] == ["array2"]

    @pytest.mark.parametrize("user", [{"uid": 1234}, {"uname": "bar"}])
    def test_context_is_not_sent_below_rest_2_17(self, user):
        blade = _blade()
        _lookup(_module(context="array2", **user), blade, api_version="2.16")
        assert "context_names" not in _kwargs(blade.get_quotas_users)

    @pytest.mark.parametrize("user", [{"uid": 1234}, {"uname": "bar"}])
    def test_no_context_is_not_sent(self, user):
        blade = _blade()
        _lookup(_module(**user), blade)
        assert "context_names" not in _kwargs(blade.get_quotas_users)

    def test_realm_name_is_sent_as_given(self):
        blade = _blade(
            file_systems=(FS, REALM_FS),
            quotas={(FS, 1234): 3 * GIB, (REALM_FS, 1234): GIB},
        )
        found = _lookup(_module(name=REALM_FS, uid=1234), blade)
        assert found.quota == GIB
        assert found.name == "tenant1::foo/1234"
        assert _kwargs(blade.get_quotas_users)["file_system_names"] == [REALM_FS]


class TestCreate:
    """state=present without a quota for the user"""

    def test_create_by_uid(self):
        blade = _blade()
        module = _module(uid=1234, quota="1G")
        _run(module, blade)
        assert _changed(module) is True
        assert _kwargs(blade.post_quotas_users) == {
            "file_system_names": [FS],
            "uids": [1234],
            "quota": {"quota": GIB},
        }
        assert blade.quotas == {(FS, 1234): GIB}

    def test_create_for_uid_zero(self):
        blade = _blade()
        module = _module(uid=0, quota="1G")
        _run(module, blade)
        assert _changed(module) is True
        assert _kwargs(blade.post_quotas_users)["uids"] == [0]
        assert "user_names" not in _kwargs(blade.post_quotas_users)

    def test_create_by_uname(self):
        blade = _blade()
        module = _module(uname="bar", quota="1G")
        _run(module, blade)
        assert _changed(module) is True
        assert _kwargs(blade.post_quotas_users) == {
            "file_system_names": [FS],
            "user_names": ["bar"],
            "quota": {"quota": GIB},
        }

    @pytest.mark.parametrize(
        "text, size",
        [
            ("1M", 1024**2),
            ("20G", 20 * 1024**3),
            ("1T", 1024**4),
            ("1P", 1024**5),
        ],
    )
    def test_quota_units(self, text, size):
        blade = _blade()
        module = _module(uid=1234, quota=text)
        _run(module, blade)
        assert _changed(module) is True
        assert blade.quotas == {(FS, 1234): size}

    @pytest.mark.parametrize("user", [{"uid": 1234}, {"uname": "bar"}])
    def test_create_twice_is_idempotent(self, user):
        blade = _blade()
        first = _module(quota="1G", **user)
        _run(first, blade)
        second = _module(quota="1G", **user)
        _run(second, blade)
        assert _changed(first) is True
        assert _changed(second) is False
        blade.post_quotas_users.assert_called_once()
        blade.patch_quotas_users.assert_not_called()

    @pytest.mark.parametrize("user", [{"uid": 1234}, {"uname": "bar"}])
    def test_create_check_mode_sends_nothing(self, user):
        blade = _blade()
        module = _module(check_mode=True, quota="1G", **user)
        _run(module, blade)
        assert _changed(module) is True
        _no_writes(blade)
        assert blade.quotas == {}

    def test_create_failure_by_uid_has_the_array_message(self):
        blade = _blade()
        blade.fail["post"] = NO_FS
        module = _module(uid=1234, quota="1G")
        _run(module, blade)
        msg = _failure(module)
        assert "UID 1234 on filesystem foo" in msg
        assert msg.endswith("Error: " + NO_FS)

    def test_create_failure_by_uname_has_the_array_message(self):
        blade = _blade()
        blade.fail["post"] = NO_NAMES
        module = _module(uname="bar", quota="1G")
        _run(module, blade)
        msg = _failure(module)
        assert "username bar on filesystem foo" in msg
        assert msg.endswith("Error: " + NO_NAMES)
        assert blade.quotas == {}


class TestUpdate:
    """state=present with a quota for the user"""

    def test_update_by_uid(self):
        blade = _blade(quotas={(FS, 1234): GIB})
        module = _module(uid=1234, quota="20G")
        _run(module, blade)
        assert _changed(module) is True
        assert _kwargs(blade.patch_quotas_users) == {
            "file_system_names": [FS],
            "uids": [1234],
            "quota": {"quota": 20 * GIB},
        }
        blade.post_quotas_users.assert_not_called()
        assert blade.quotas == {(FS, 1234): 20 * GIB}

    def test_update_by_uname(self):
        blade = _blade(quotas={(FS, "bar"): GIB})
        module = _module(uname="bar", quota="20G")
        _run(module, blade)
        assert _changed(module) is True
        assert _kwargs(blade.patch_quotas_users) == {
            "file_system_names": [FS],
            "user_names": ["bar"],
            "quota": {"quota": 20 * GIB},
        }

    @pytest.mark.parametrize("user", [1234, "bar"])
    def test_lower_quota_is_a_change(self, user):
        blade = _blade(quotas={(FS, user): 20 * GIB})
        key = "uid" if isinstance(user, int) else "uname"
        module = _module(quota="1G", **{key: user})
        _run(module, blade)
        assert _changed(module) is True
        blade.patch_quotas_users.assert_called_once()
        assert blade.quotas == {(FS, user): GIB}

    @pytest.mark.parametrize("user", [1234, 0, "bar"])
    @pytest.mark.parametrize("check_mode", [False, True])
    def test_same_quota_is_unchanged(self, user, check_mode):
        blade = _blade(quotas={(FS, user): GIB})
        key = "uid" if isinstance(user, int) else "uname"
        module = _module(check_mode=check_mode, quota="1G", **{key: user})
        _run(module, blade)
        assert _changed(module) is False
        _no_writes(blade)

    @pytest.mark.parametrize("user", [1234, "bar"])
    def test_update_twice_is_idempotent(self, user):
        blade = _blade(quotas={(FS, user): GIB})
        key = "uid" if isinstance(user, int) else "uname"
        first = _module(quota="2G", **{key: user})
        _run(first, blade)
        second = _module(quota="2G", **{key: user})
        _run(second, blade)
        assert _changed(first) is True
        assert _changed(second) is False
        blade.patch_quotas_users.assert_called_once()

    @pytest.mark.parametrize("user", [1234, "bar"])
    def test_update_check_mode_sends_nothing(self, user):
        blade = _blade(quotas={(FS, user): GIB})
        key = "uid" if isinstance(user, int) else "uname"
        module = _module(check_mode=True, quota="2G", **{key: user})
        _run(module, blade)
        assert _changed(module) is True
        _no_writes(blade)
        assert blade.quotas == {(FS, user): GIB}

    def test_update_failure_by_uid_has_the_array_message(self):
        blade = _blade(quotas={(FS, 1234): GIB})
        blade.fail["patch"] = NO_FS
        module = _module(uid=1234, quota="2G")
        _run(module, blade)
        msg = _failure(module)
        assert "UID 1234 on filesystem foo" in msg
        assert msg.endswith("Error: " + NO_FS)
        assert blade.quotas == {(FS, 1234): GIB}

    def test_update_failure_by_uname_has_the_array_message(self):
        blade = _blade(quotas={(FS, "bar"): GIB})
        blade.fail["patch"] = NO_NAMES
        module = _module(uname="bar", quota="2G")
        _run(module, blade)
        msg = _failure(module)
        assert "bar on filesystem foo" in msg
        assert msg.endswith("Error: " + NO_NAMES)


class TestDelete:
    """state=absent"""

    def test_delete_by_uid(self):
        blade = _blade(quotas={(FS, 1234): GIB, (FS, 99): GIB})
        module = _module(uid=1234, state="absent")
        _run(module, blade)
        assert _changed(module) is True
        assert _kwargs(blade.delete_quotas_users) == {
            "file_system_names": [FS],
            "uids": [1234],
        }
        assert blade.quotas == {(FS, 99): GIB}

    def test_delete_for_uid_zero(self):
        blade = _blade(quotas={(FS, 0): GIB})
        module = _module(uid=0, state="absent")
        _run(module, blade)
        assert _changed(module) is True
        assert _kwargs(blade.delete_quotas_users)["uids"] == [0]

    def test_delete_by_uname(self):
        blade = _blade(quotas={(FS, "bar"): GIB})
        module = _module(uname="bar", state="absent")
        _run(module, blade)
        assert _changed(module) is True
        assert _kwargs(blade.delete_quotas_users) == {
            "file_system_names": [FS],
            "user_names": ["bar"],
        }
        assert blade.quotas == {}

    @pytest.mark.parametrize("user", [{"uid": 1234}, {"uname": "bar"}])
    @pytest.mark.parametrize("check_mode", [False, True])
    def test_delete_without_quota_is_unchanged(self, user, check_mode):
        blade = _blade(quotas={(FS, 99): GIB})
        module = _module(check_mode=check_mode, state="absent", **user)
        _run(module, blade)
        assert _changed(module) is False
        _no_writes(blade)

    @pytest.mark.parametrize("user", [1234, "bar"])
    def test_delete_twice_is_idempotent(self, user):
        blade = _blade(quotas={(FS, user): GIB})
        key = "uid" if isinstance(user, int) else "uname"
        first = _module(state="absent", **{key: user})
        _run(first, blade)
        second = _module(state="absent", **{key: user})
        _run(second, blade)
        assert _changed(first) is True
        assert _changed(second) is False
        blade.delete_quotas_users.assert_called_once()

    @pytest.mark.parametrize("user", [1234, "bar"])
    def test_delete_check_mode_sends_nothing(self, user):
        blade = _blade(quotas={(FS, user): GIB})
        key = "uid" if isinstance(user, int) else "uname"
        module = _module(check_mode=True, state="absent", **{key: user})
        _run(module, blade)
        assert _changed(module) is True
        _no_writes(blade)
        assert blade.quotas == {(FS, user): GIB}

    def test_delete_failure_by_uid_has_the_array_message(self):
        blade = _blade(quotas={(FS, 1234): GIB})
        blade.fail["delete"] = NO_FS
        module = _module(uid=1234, state="absent")
        _run(module, blade)
        msg = _failure(module)
        assert "UID 1234 on filesystem foo" in msg
        assert msg.endswith("Error: " + NO_FS)
        assert blade.quotas == {(FS, 1234): GIB}

    def test_delete_failure_by_uname_has_the_array_message(self):
        blade = _blade(quotas={(FS, "bar"): GIB})
        blade.fail["delete"] = NO_NAMES
        module = _module(uname="bar", state="absent")
        _run(module, blade)
        msg = _failure(module)
        assert "username bar on filesystem foo" in msg
        assert msg.endswith("Error: " + NO_NAMES)


class TestRefusedQuotaRead:
    """Only an answered read says that the user has no quota"""

    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize("check_mode", [False, True])
    def test_refused_read_by_uid_has_the_array_message(self, state, check_mode):
        blade = _blade(quotas={(FS, 1234): GIB})
        blade.fail["get"] = NOT_PERMITTED
        module = _module(check_mode=check_mode, uid=1234, quota="2G", state=state)
        _run(module, blade)
        msg = _failure(module)
        assert "UID 1234 on filesystem foo" in msg
        assert msg.endswith("Error: " + NOT_PERMITTED)
        _no_writes(blade)
        assert blade.quotas == {(FS, 1234): GIB}

    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize("check_mode", [False, True])
    def test_refused_read_by_uname_has_the_array_message(self, state, check_mode):
        blade = _blade(quotas={(FS, "bar"): GIB})
        blade.fail["get"] = NOT_PERMITTED
        module = _module(check_mode=check_mode, uname="bar", quota="2G", state=state)
        _run(module, blade)
        msg = _failure(module)
        assert "username bar on filesystem foo" in msg
        assert msg.endswith("Error: " + NOT_PERMITTED)
        _no_writes(blade)
        assert blade.quotas == {(FS, "bar"): GIB}

    @pytest.mark.parametrize("user", [{"uid": 1234}, {"uname": "bar"}])
    def test_get_quota_fails_on_a_refused_read(self, user):
        blade = _blade()
        blade.fail["get"] = NOT_PERMITTED
        module = _module(**user)
        with pytest.raises(SystemExit):
            _lookup(module, blade)
        assert _failure(module).endswith("Error: " + NOT_PERMITTED)

    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize("check_mode", [False, True])
    def test_list_of_names_is_refused_with_the_array_message(self, state, check_mode):
        quotas = {(FS, 1234): 3 * GIB, (REALM_FS, 1234): GIB}
        blade = _blade(file_systems=(FS, REALM_FS), quotas=quotas)
        name = FS + "," + REALM_FS
        module = _module(
            check_mode=check_mode, name=name, uid=1234, quota="9G", state=state
        )
        _run(module, blade)
        msg = _failure(module)
        assert "UID 1234 on filesystem foo,tenant1::foo" in msg
        assert msg.endswith("Error: " + MANY_FS)
        _no_writes(blade)
        assert blade.quotas == quotas

    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize("check_mode", [False, True])
    def test_pattern_is_refused_with_the_array_message(self, state, check_mode):
        quotas = {(FS, 1234): 3 * GIB, (REALM_FS, 1234): GIB}
        blade = _blade(file_systems=(FS, REALM_FS), quotas=quotas)
        module = _module(
            check_mode=check_mode, name="fo*", uid=1234, quota="9G", state=state
        )
        _run(module, blade)
        blade.get_file_systems.assert_called_once_with(names=["fo*"])
        assert _failure(module).endswith("Error: " + NO_FS)
        _no_writes(blade)
        assert blade.quotas == quotas

    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize("check_mode", [False, True])
    def test_realm_administrator_list_of_names_is_refused(self, state, check_mode):
        quotas = {(FS, 1234): 3 * GIB, (REALM_FS, 1234): GIB}
        blade = _blade(
            file_systems=(FS, REALM_FS),
            quotas=quotas,
            fleet=REFUSED,
            hidden=(FS,),
        )
        name = FS + "," + REALM_FS
        module = _module(
            check_mode=check_mode, name=name, uid=1234, quota="9G", state=state
        )
        _run(module, blade)
        assert _failure(module).endswith("Error: " + MANY_FS)
        _no_writes(blade)
        assert blade.quotas == quotas

    def test_pattern_without_a_match_is_a_missing_file_system(self):
        blade = _blade(quotas={(FS, 1234): GIB})
        module = _module(name="zz*", uid=1234, state="absent")
        _run(module, blade)
        assert _failure(module) == "Filesystem zz* does not exist."
        blade.get_quotas_users.assert_not_called()
        _no_writes(blade)


class TestRealm:
    """A file system in a realm is named realm::name"""

    def test_create_in_realm_leaves_the_array_level_namesake(self):
        blade = _blade(file_systems=(FS, REALM_FS), quotas={(FS, 1234): 3 * GIB})
        module = _module(name=REALM_FS, uid=1234, quota="1G")
        _run(module, blade)
        assert _changed(module) is True
        blade.get_file_systems.assert_called_once_with(names=[REALM_FS])
        assert _kwargs(blade.post_quotas_users) == {
            "file_system_names": [REALM_FS],
            "uids": [1234],
            "quota": {"quota": GIB},
        }
        assert blade.quotas == {(FS, 1234): 3 * GIB, (REALM_FS, 1234): GIB}

    def test_realm_quota_is_compared_with_the_realm_file_system(self):
        blade = _blade(
            file_systems=(FS, REALM_FS),
            quotas={(FS, 1234): 3 * GIB, (REALM_FS, 1234): GIB},
        )
        same = _module(name=REALM_FS, uid=1234, quota="1G")
        _run(same, blade)
        assert _changed(same) is False
        _no_writes(blade)
        other = _module(name=REALM_FS, uid=1234, quota="3G")
        _run(other, blade)
        assert _changed(other) is True
        assert _kwargs(blade.patch_quotas_users) == {
            "file_system_names": [REALM_FS],
            "uids": [1234],
            "quota": {"quota": 3 * GIB},
        }

    def test_delete_in_realm_leaves_the_array_level_namesake(self):
        blade = _blade(
            file_systems=(FS, REALM_FS),
            quotas={(FS, 1234): 3 * GIB, (REALM_FS, 1234): GIB},
        )
        module = _module(name=REALM_FS, uid=1234, state="absent")
        _run(module, blade)
        assert _changed(module) is True
        assert _kwargs(blade.delete_quotas_users) == {
            "file_system_names": [REALM_FS],
            "uids": [1234],
        }
        assert blade.quotas == {(FS, 1234): 3 * GIB}

    def test_array_level_name_leaves_the_realm_quota(self):
        blade = _blade(file_systems=(FS, REALM_FS), quotas={(REALM_FS, 1234): GIB})
        create = _module(uid=1234, quota="3G")
        _run(create, blade)
        assert _changed(create) is True
        assert _kwargs(blade.post_quotas_users)["file_system_names"] == [FS]
        update = _module(uid=1234, quota="5G")
        _run(update, blade)
        assert _changed(update) is True
        assert _kwargs(blade.patch_quotas_users)["file_system_names"] == [FS]
        delete = _module(uid=1234, state="absent")
        _run(delete, blade)
        assert _changed(delete) is True
        assert _kwargs(blade.delete_quotas_users)["file_system_names"] == [FS]
        assert blade.quotas == {(REALM_FS, 1234): GIB}

    def test_same_leaf_in_two_realms_is_kept_apart(self):
        blade = _blade(
            file_systems=(REALM_FS, OTHER_REALM_FS),
            quotas={(OTHER_REALM_FS, 1234): 5 * GIB},
        )
        module = _module(name=REALM_FS, uid=1234, state="absent")
        _run(module, blade)
        assert _changed(module) is False
        _no_writes(blade)
        assert blade.quotas == {(OTHER_REALM_FS, 1234): 5 * GIB}

    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize("check_mode", [False, True])
    def test_bare_name_is_not_completed_with_a_realm(self, state, check_mode):
        blade = _blade(file_systems=(REALM_FS,), quotas={(REALM_FS, 1234): GIB})
        module = _module(check_mode=check_mode, uid=1234, quota="9G", state=state)
        _run(module, blade)
        assert _failure(module) == "Filesystem foo does not exist."
        blade.get_file_systems.assert_called_once_with(names=[FS])
        blade.get_quotas_users.assert_not_called()
        _no_writes(blade)
        assert blade.quotas == {(REALM_FS, 1234): GIB}

    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize("check_mode", [False, True])
    def test_unknown_realm_fails(self, state, check_mode):
        blade = _blade(file_systems=(FS, REALM_FS))
        module = _module(
            check_mode=check_mode,
            name="zznorealm::foo",
            uid=1234,
            quota="1G",
            state=state,
        )
        _run(module, blade)
        assert _failure(module) == "Filesystem zznorealm::foo does not exist."
        _no_writes(blade)

    @pytest.mark.parametrize("name", [FS, OTHER_REALM_FS])
    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize("check_mode", [False, True])
    def test_realm_administrator_cannot_reach_another_scope(
        self, name, state, check_mode
    ):
        quotas = {
            (FS, 1234): 3 * GIB,
            (REALM_FS, 1234): GIB,
            (OTHER_REALM_FS, 1234): 5 * GIB,
        }
        blade = _blade(
            file_systems=(FS, REALM_FS, OTHER_REALM_FS),
            quotas=quotas,
            fleet=REFUSED,
            hidden=(FS, OTHER_REALM_FS),
        )
        module = _module(
            check_mode=check_mode, name=name, uid=1234, quota="9G", state=state
        )
        _run(module, blade)
        assert _failure(module) == "Filesystem {0} does not exist.".format(name)
        blade.get_file_systems.assert_called_once_with(names=[name])
        blade.get_quotas_users.assert_not_called()
        _no_writes(blade)
        assert blade.quotas == quotas

    def test_realm_administrator_manages_its_realm_by_qualified_name(self):
        blade = _blade(
            file_systems=(FS, REALM_FS),
            quotas={(FS, 1234): 3 * GIB},
            fleet=REFUSED,
            hidden=(FS,),
        )
        create = _module(name=REALM_FS, uid=1234, quota="1G")
        _run(create, blade)
        again = _module(name=REALM_FS, uid=1234, quota="1G")
        _run(again, blade)
        update = _module(name=REALM_FS, uid=1234, quota="2G")
        _run(update, blade)
        assert blade.quotas == {(FS, 1234): 3 * GIB, (REALM_FS, 1234): 2 * GIB}
        delete = _module(name=REALM_FS, uid=1234, state="absent")
        _run(delete, blade)
        assert [_changed(module) for module in (create, again, update, delete)] == [
            True,
            False,
            True,
            True,
        ]
        assert blade.quotas == {(FS, 1234): 3 * GIB}
        for mocked in (
            blade.post_quotas_users,
            blade.patch_quotas_users,
            blade.delete_quotas_users,
        ):
            assert _kwargs(mocked)["file_system_names"] == [REALM_FS]
            assert "context_names" not in _kwargs(mocked)
        blade.get_arrays.assert_not_called()


class TestContext:
    """Fleet context of the reads and writes"""

    def test_standalone_array_sends_no_context(self):
        blade = _blade()
        module = _module(uid=1234, quota="1G")
        _run(module, blade)
        assert _changed(module) is True
        blade.get_fleets.assert_called_once()
        blade.get_arrays.assert_not_called()
        assert module.params["context"] == ""
        assert "context_names" not in _kwargs(blade.get_quotas_users)
        assert "context_names" not in _kwargs(blade.post_quotas_users)

    def test_fleet_member_defaults_to_the_local_array(self):
        blade = _blade(fleet="member")
        module = _module(uid=1234, quota="1G")
        _run(module, blade)
        assert _changed(module) is True
        assert module.params["context"] == ARRAY
        assert _kwargs(blade.get_quotas_users)["context_names"] == [ARRAY]
        assert _kwargs(blade.post_quotas_users)["context_names"] == [ARRAY]

    def test_refused_fleet_read_sends_no_context(self):
        blade = _blade(fleet=REFUSED)
        module = _module(uid=1234, quota="1G")
        _run(module, blade)
        assert _changed(module) is True
        blade.get_arrays.assert_not_called()
        assert "context_names" not in _kwargs(blade.post_quotas_users)

    def test_fleet_is_not_read_below_rest_2_17(self):
        blade = _blade(fleet="member")
        module = _module(uid=1234, quota="1G")
        _run(module, blade, api_version="2.16")
        assert _changed(module) is True
        blade.get_fleets.assert_not_called()
        assert "context_names" not in _kwargs(blade.post_quotas_users)

    def test_given_context_is_kept(self):
        blade = _blade(fleet="member")
        module = _module(uid=1234, quota="1G", context="array2")
        _run(module, blade)
        assert _changed(module) is True
        blade.get_fleets.assert_not_called()
        assert _kwargs(blade.get_quotas_users)["context_names"] == ["array2"]
        assert _kwargs(blade.post_quotas_users)["context_names"] == ["array2"]

    @pytest.mark.parametrize("user", [1234, "bar"])
    @pytest.mark.parametrize(
        "api_version, sent", [("2.17", True), ("2.30", True), ("2.16", False)]
    )
    def test_context_on_every_write(self, user, api_version, sent):
        key = "uid" if isinstance(user, int) else "uname"
        blade = _blade()
        runs = [
            (_module(quota="1G", context="array2", **{key: user}), "post"),
            (_module(quota="2G", context="array2", **{key: user}), "patch"),
            (_module(state="absent", context="array2", **{key: user}), "delete"),
        ]
        for module, verb in runs:
            _run(module, blade, api_version=api_version)
            assert _changed(module) is True
            kwargs = _kwargs(getattr(blade, verb + "_quotas_users"))
            assert kwargs.get("context_names") == (["array2"] if sent else None)
        assert blade.quotas == {}


class TestMain:
    """Argument handling and the checks before any quota request"""

    def test_missing_sdk_fails(self):
        blade = _blade()
        module = _module(uid=1234, quota="1G")
        _run(module, blade, has_sdk=False)
        assert _failure(module) == "py-pure-client sdk is required for this module"
        blade.get_file_systems.assert_not_called()

    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize("check_mode", [False, True])
    def test_missing_file_system_fails_before_any_quota_request(
        self, state, check_mode
    ):
        blade = _blade(file_systems=())
        module = _module(check_mode=check_mode, uid=1234, quota="1G", state=state)
        _run(module, blade)
        assert _failure(module) == "Filesystem foo does not exist."
        blade.get_quotas_users.assert_not_called()
        _no_writes(blade)

    def test_argument_spec(self):
        blade = _blade()
        ansible_module = _run(_module(uid=1234, quota="1G"), blade)
        args, kwargs = ansible_module.call_args
        spec = args[0]
        assert sorted(spec) == ["context", "name", "quota", "state", "uid", "uname"]
        assert spec["name"] == {"type": "str", "required": True}
        assert spec["uid"] == {"type": "int"}
        assert spec["state"] == {
            "default": "present",
            "choices": ["present", "absent"],
        }
        assert spec["context"] == {"type": "str", "default": ""}
        assert kwargs == {
            "mutually_exclusive": [["uid", "uname"]],
            "required_one_of": [["uid", "uname"]],
            "required_if": [["state", "present", ["quota"]]],
            "supports_check_mode": True,
        }


class TestDocumentation:
    """The realm form of the file system name is documented"""

    def test_name_documents_the_realm_form(self):
        option = yaml.safe_load(DOCUMENTATION)["options"]["name"]
        text = " ".join(option["description"])
        assert "C(realm::name)" in text
        assert "realm-scoped administrator" in text

    def test_examples_have_a_file_system_in_a_realm(self):
        tasks = [task[FQCN] for task in yaml.safe_load(EXAMPLES)]
        in_realm = [args for args in tasks if "::" in args["name"]]
        assert in_realm
        for args in in_realm:
            assert "uid" in args or "uname" in args

    def test_examples_use_documented_options(self):
        documented = set(yaml.safe_load(DOCUMENTATION)["options"])
        documented.update(["fb_url", "api_token"])
        for task in yaml.safe_load(EXAMPLES):
            assert set(task[FQCN]) <= documented
