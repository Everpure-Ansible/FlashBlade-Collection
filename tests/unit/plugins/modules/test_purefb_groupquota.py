# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_groupquota module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
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
from plugins.modules.purefb_groupquota import (
    DOCUMENTATION,
    EXAMPLES,
    main,
)

MOD = "plugins.modules.purefb_groupquota"
TASK = "everpure.flashblade.purefb_groupquota"
GIB = 1024**3
GID = 1234
GROUP = "staff"
# The same leaf name in a realm, at the array level and in a second realm:
# three different file systems, each with its own quotas.
REALM_FS = "tenant1::projects"
ARRAY_FS = "projects"
OTHER_REALM_FS = "tenant2::projects"
FILE_SYSTEMS = (REALM_FS, ARRAY_FS, OTHER_REALM_FS)
SCOPES = [REALM_FS, ARRAY_FS]
LOCAL_ARRAY = "array1"
NO_FILE_SYSTEM = "File system does not exist."
REFUSED = "Operation not permitted."
NO_NAME_SERVICE = (
    "Cannot manage quotas using group names without either the NFS directory "
    "service enabled or an Active Directory configuration created with "
    "service principal names for the NFS service."
)


def _base_params(**overrides):
    params = {
        "name": REALM_FS,
        "state": "present",
        "quota": None,
        "gid": None,
        "gname": None,
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


def _response(items=None):
    res = Mock()
    res.status_code = 200
    res.items = items if items is not None else []
    res.total_item_count = len(res.items)
    return res


def _error(message):
    """An error answer: like the SDK's, it has no items to read."""
    res = Mock(spec=["status_code", "errors"])
    res.status_code = 400
    err = Mock()
    err.message = message
    res.errors = [err]
    return res


def _quota(fsys, group, size):
    """A group quota as the array returns it, named <file system>/<group>.

    The file system part carries the realm, for example
    tenant1::projects/1234. The module reads only the quota.
    """
    item = Mock()
    item.name = "{0}/{1}".format(fsys, group)
    item.file_system.name = fsys
    item.group.id = group if isinstance(group, int) else None
    item.group.name = None if isinstance(group, int) else group
    item.quota = size
    item.usage = 0
    return item


def _twins(fsys, size=3 * GIB, group=GID):
    """Quotas of the same group on the namesakes of fsys in other scopes."""
    return {(name, group): size for name in FILE_SYSTEMS if name != fsys}


def _blade(quotas=None, file_systems=FILE_SYSTEMS, fleet=False):
    """A small stateful stand-in for the array.

    file_systems are the names GET /file-systems knows. Every other name is
    answered with an error, the bare leaf of a file system in a realm
    included. quotas maps (file system, gid or group name) to the quota in
    bytes. POST, PATCH and DELETE change that state so that a later GET reads
    it back. blade.fail maps post, patch or delete to the message the array
    refuses that request with.
    """
    state = dict(quotas or {})
    blade = Mock()
    blade.quotas = state
    blade.fail = {}
    blade.get_fleets.return_value = _response(items=[Mock()] if fleet else [])
    local = Mock()
    local.name = LOCAL_ARRAY
    blade.get_arrays.return_value = _response(items=[local])

    def _group(kwargs):
        if "gids" in kwargs:
            return kwargs["gids"][0]
        return kwargs["group_names"][0]

    def _get_file_systems(**kwargs):
        name = kwargs["names"][0]
        if name not in file_systems:
            return _error(NO_FILE_SYSTEM)
        fsys = Mock()
        fsys.name = name
        return _response(items=[fsys])

    def _get(**kwargs):
        fsys = kwargs["file_system_names"][0]
        if fsys not in file_systems:
            return _error(NO_FILE_SYSTEM)
        field, value = kwargs["filter"].split("=", 1)
        group = int(value) if field == "group.id" else value.strip("'")
        if (fsys, group) not in state:
            return _response()
        return _response(items=[_quota(fsys, group, state[(fsys, group)])])

    def _post(**kwargs):
        if "post" in blade.fail:
            return _error(blade.fail["post"])
        fsys = kwargs["file_system_names"][0]
        state[(fsys, _group(kwargs))] = kwargs["quota"]["quota"]
        return _response()

    def _patch(**kwargs):
        if "patch" in blade.fail:
            return _error(blade.fail["patch"])
        fsys = kwargs["file_system_names"][0]
        state[(fsys, _group(kwargs))] = kwargs["quota"]["quota"]
        return _response()

    def _delete(**kwargs):
        if "delete" in blade.fail:
            return _error(blade.fail["delete"])
        fsys = kwargs["file_system_names"][0]
        del state[(fsys, _group(kwargs))]
        return _response()

    blade.get_file_systems.side_effect = _get_file_systems
    blade.get_quotas_groups.side_effect = _get
    blade.post_quotas_groups.side_effect = _post
    blade.patch_quotas_groups.side_effect = _patch
    blade.delete_quotas_groups.side_effect = _delete
    return blade


def _get_filesystem(module, blade):
    """What module_utils.common.get_filesystem does with the answer."""
    res = blade.get_file_systems(names=[module.params["name"]])
    if res.status_code == 200:
        items = list(res.items)
        if items:
            return items[0]
    return None


def _get_error_message(response):
    """What module_utils.common.get_error_message returns."""
    return response.errors[0].message


def _run(module, blade, api_version="2.30", has_sdk=True):
    """Run main() with the module/blade stand-ins and the given REST version.

    Returns the AnsibleModule mock so the argument rules can be inspected.
    """
    with patch(MOD + ".AnsibleModule", return_value=module) as ansible_module, patch(
        MOD + ".get_system", return_value=blade
    ), patch(MOD + ".get_rest_api_version", return_value=api_version), patch(
        MOD + ".LooseVersion", RealLooseVersion
    ), patch(
        MOD + ".HAS_PYPURECLIENT", has_sdk
    ), patch(
        MOD + ".GroupQuotaPost", side_effect=lambda **kw: kw
    ), patch(
        MOD + ".GroupQuotaPatch", side_effect=lambda **kw: kw
    ), patch(
        MOD + ".get_filesystem", side_effect=_get_filesystem
    ), patch(
        MOD + ".get_error_message", side_effect=_get_error_message
    ):
        with pytest.raises(SystemExit):
            main()
    return ansible_module


def _changed(module):
    """The changed flag of a run that ended without a failure."""
    module.fail_json.assert_not_called()
    module.exit_json.assert_called_once()
    return module.exit_json.call_args[1]["changed"]


def _failure(module):
    """The message of a run that failed."""
    module.exit_json.assert_not_called()
    module.fail_json.assert_called_once()
    return module.fail_json.call_args[1]["msg"]


def _no_write(blade):
    blade.post_quotas_groups.assert_not_called()
    blade.patch_quotas_groups.assert_not_called()
    blade.delete_quotas_groups.assert_not_called()


class TestArguments:
    def test_argument_rules(self):
        module = _module(gid=GID, state="absent")
        ansible_module = _run(module, _blade())
        rules = ansible_module.call_args[1]
        assert rules["mutually_exclusive"] == [["gid", "gname"]]
        assert rules["required_one_of"] == [["gid", "gname"]]
        assert rules["required_if"] == [["state", "present", ["quota"]]]
        assert rules["supports_check_mode"] is True

    def test_sdk_missing(self):
        module = _module(gid=GID, quota="1G")
        blade = _blade()
        _run(module, blade, has_sdk=False)
        assert "py-pure-client" in _failure(module)
        blade.get_file_systems.assert_not_called()
        _no_write(blade)


class TestCreate:
    @pytest.mark.parametrize("fsys", SCOPES)
    def test_create_by_gid(self, fsys):
        """The quota goes to the named file system, namesakes are left alone."""
        blade = _blade(quotas=_twins(fsys))
        module = _module(name=fsys, gid=GID, quota="1G")
        _run(module, blade)
        assert _changed(module) is True
        blade.get_file_systems.assert_called_once_with(names=[fsys])
        blade.get_quotas_groups.assert_called_once_with(
            file_system_names=[fsys], filter="group.id=1234"
        )
        blade.post_quotas_groups.assert_called_once_with(
            file_system_names=[fsys], gids=[GID], quota={"quota": GIB}
        )
        expected = _twins(fsys)
        expected[(fsys, GID)] = GIB
        assert blade.quotas == expected
        blade.patch_quotas_groups.assert_not_called()
        blade.delete_quotas_groups.assert_not_called()

    @pytest.mark.parametrize("fsys", SCOPES)
    def test_create_twice(self, fsys):
        blade = _blade(quotas=_twins(fsys))
        first = _module(name=fsys, gid=GID, quota="1G")
        _run(first, blade)
        second = _module(name=fsys, gid=GID, quota="1G")
        _run(second, blade)
        assert _changed(first) is True
        assert _changed(second) is False
        blade.post_quotas_groups.assert_called_once()
        blade.patch_quotas_groups.assert_not_called()

    @pytest.mark.parametrize("fsys", SCOPES)
    def test_create_check_mode(self, fsys):
        blade = _blade(quotas=_twins(fsys))
        module = _module(check_mode=True, name=fsys, gid=GID, quota="1G")
        _run(module, blade)
        assert _changed(module) is True
        _no_write(blade)
        assert blade.quotas == _twins(fsys)

    def test_create_for_gid_zero(self):
        """gid 0 is a group like any other, not a missing value."""
        blade = _blade()
        module = _module(gid=0, quota="1G")
        _run(module, blade)
        assert _changed(module) is True
        blade.get_quotas_groups.assert_called_once_with(
            file_system_names=[REALM_FS], filter="group.id=0"
        )
        blade.post_quotas_groups.assert_called_once_with(
            file_system_names=[REALM_FS], gids=[0], quota={"quota": GIB}
        )

    @pytest.mark.parametrize("fsys", SCOPES)
    def test_create_by_group_name(self, fsys):
        blade = _blade()
        module = _module(name=fsys, gname=GROUP, quota="2G")
        _run(module, blade)
        assert _changed(module) is True
        blade.get_quotas_groups.assert_called_once_with(
            file_system_names=[fsys], filter="group.name='staff'"
        )
        blade.post_quotas_groups.assert_called_once_with(
            file_system_names=[fsys], group_names=[GROUP], quota={"quota": 2 * GIB}
        )
        assert blade.quotas == {(fsys, GROUP): 2 * GIB}

    def test_create_refused_by_gid(self):
        blade = _blade()
        blade.fail["post"] = REFUSED
        module = _module(gid=GID, quota="1G")
        _run(module, blade)
        msg = _failure(module)
        assert REALM_FS in msg
        assert str(GID) in msg
        assert REFUSED in msg
        assert not blade.quotas

    def test_create_refused_by_group_name(self):
        """The array's reason for refusing a group name reaches the user."""
        blade = _blade()
        blade.fail["post"] = NO_NAME_SERVICE
        module = _module(gname=GROUP, quota="1G")
        _run(module, blade)
        msg = _failure(module)
        assert REALM_FS in msg
        assert GROUP in msg
        assert NO_NAME_SERVICE in msg
        assert not blade.quotas


class TestUpdate:
    @pytest.mark.parametrize("fsys", SCOPES)
    def test_update_by_gid(self, fsys):
        quotas = _twins(fsys)
        quotas[(fsys, GID)] = GIB
        blade = _blade(quotas=quotas)
        module = _module(name=fsys, gid=GID, quota="2G")
        _run(module, blade)
        assert _changed(module) is True
        blade.patch_quotas_groups.assert_called_once_with(
            file_system_names=[fsys], gids=[GID], quota={"quota": 2 * GIB}
        )
        expected = _twins(fsys)
        expected[(fsys, GID)] = 2 * GIB
        assert blade.quotas == expected
        blade.post_quotas_groups.assert_not_called()
        blade.delete_quotas_groups.assert_not_called()

    @pytest.mark.parametrize("fsys", SCOPES)
    def test_update_twice(self, fsys):
        quotas = _twins(fsys)
        quotas[(fsys, GID)] = GIB
        blade = _blade(quotas=quotas)
        first = _module(name=fsys, gid=GID, quota="2G")
        _run(first, blade)
        second = _module(name=fsys, gid=GID, quota="2G")
        _run(second, blade)
        assert _changed(first) is True
        assert _changed(second) is False
        blade.patch_quotas_groups.assert_called_once()

    @pytest.mark.parametrize("fsys", SCOPES)
    def test_namesake_quota_is_not_this_quota(self, fsys):
        """A different quota on a namesake is no reason to change this one."""
        quotas = _twins(fsys, size=5 * GIB)
        quotas[(fsys, GID)] = GIB
        blade = _blade(quotas=quotas)
        module = _module(name=fsys, gid=GID, quota="1G")
        _run(module, blade)
        assert _changed(module) is False
        _no_write(blade)

    def test_same_size_in_another_unit(self):
        blade = _blade(quotas={(REALM_FS, GID): GIB})
        module = _module(gid=GID, quota="1024M")
        _run(module, blade)
        assert _changed(module) is False
        _no_write(blade)

    @pytest.mark.parametrize("fsys", SCOPES)
    def test_update_check_mode(self, fsys):
        quotas = _twins(fsys)
        quotas[(fsys, GID)] = GIB
        blade = _blade(quotas=quotas)
        module = _module(check_mode=True, name=fsys, gid=GID, quota="2G")
        _run(module, blade)
        assert _changed(module) is True
        _no_write(blade)
        assert blade.quotas == quotas

    def test_unchanged_check_mode(self):
        blade = _blade(quotas={(REALM_FS, GID): GIB})
        module = _module(check_mode=True, gid=GID, quota="1G")
        _run(module, blade)
        assert _changed(module) is False
        _no_write(blade)

    def test_update_by_group_name(self):
        blade = _blade(quotas={(REALM_FS, GROUP): GIB})
        module = _module(gname=GROUP, quota="2G")
        _run(module, blade)
        assert _changed(module) is True
        blade.patch_quotas_groups.assert_called_once_with(
            file_system_names=[REALM_FS],
            group_names=[GROUP],
            quota={"quota": 2 * GIB},
        )
        assert blade.quotas == {(REALM_FS, GROUP): 2 * GIB}

    @pytest.mark.parametrize("group", [{"gid": GID}, {"gname": GROUP}])
    def test_update_refused(self, group):
        key = list(group.values())[0]
        blade = _blade(quotas={(REALM_FS, key): GIB})
        blade.fail["patch"] = REFUSED
        module = _module(quota="2G", **group)
        _run(module, blade)
        msg = _failure(module)
        assert REALM_FS in msg
        assert str(key) in msg
        assert REFUSED in msg
        assert blade.quotas == {(REALM_FS, key): GIB}


class TestDelete:
    @pytest.mark.parametrize("fsys", SCOPES)
    def test_delete_by_gid(self, fsys):
        quotas = _twins(fsys)
        quotas[(fsys, GID)] = GIB
        blade = _blade(quotas=quotas)
        module = _module(name=fsys, gid=GID, state="absent")
        _run(module, blade)
        assert _changed(module) is True
        blade.delete_quotas_groups.assert_called_once_with(
            file_system_names=[fsys], gids=[GID]
        )
        assert blade.quotas == _twins(fsys)
        blade.post_quotas_groups.assert_not_called()
        blade.patch_quotas_groups.assert_not_called()

    @pytest.mark.parametrize("fsys", SCOPES)
    def test_delete_twice(self, fsys):
        quotas = _twins(fsys)
        quotas[(fsys, GID)] = GIB
        blade = _blade(quotas=quotas)
        first = _module(name=fsys, gid=GID, state="absent")
        _run(first, blade)
        second = _module(name=fsys, gid=GID, state="absent")
        _run(second, blade)
        assert _changed(first) is True
        assert _changed(second) is False
        blade.delete_quotas_groups.assert_called_once()

    @pytest.mark.parametrize("fsys", SCOPES)
    def test_absent_leaves_namesake_quotas(self, fsys):
        """No quota on the named file system: the namesakes keep theirs."""
        blade = _blade(quotas=_twins(fsys))
        module = _module(name=fsys, gid=GID, state="absent")
        _run(module, blade)
        assert _changed(module) is False
        _no_write(blade)
        assert blade.quotas == _twins(fsys)

    @pytest.mark.parametrize("fsys", SCOPES)
    def test_delete_check_mode(self, fsys):
        quotas = _twins(fsys)
        quotas[(fsys, GID)] = GIB
        blade = _blade(quotas=quotas)
        module = _module(check_mode=True, name=fsys, gid=GID, state="absent")
        _run(module, blade)
        assert _changed(module) is True
        _no_write(blade)
        assert blade.quotas == quotas

    def test_delete_gid_zero(self):
        blade = _blade(quotas={(REALM_FS, 0): GIB, (REALM_FS, GID): GIB})
        module = _module(gid=0, state="absent")
        _run(module, blade)
        assert _changed(module) is True
        blade.delete_quotas_groups.assert_called_once_with(
            file_system_names=[REALM_FS], gids=[0]
        )
        assert blade.quotas == {(REALM_FS, GID): GIB}

    def test_delete_by_group_name(self):
        blade = _blade(quotas={(REALM_FS, GROUP): GIB})
        module = _module(gname=GROUP, state="absent")
        _run(module, blade)
        assert _changed(module) is True
        blade.delete_quotas_groups.assert_called_once_with(
            file_system_names=[REALM_FS], group_names=[GROUP]
        )
        assert not blade.quotas

    def test_delete_refused_by_gid(self):
        blade = _blade(quotas={(REALM_FS, GID): GIB})
        blade.fail["delete"] = REFUSED
        module = _module(gid=GID, state="absent")
        _run(module, blade)
        msg = _failure(module)
        assert REALM_FS in msg
        assert str(GID) in msg
        assert blade.quotas == {(REALM_FS, GID): GIB}

    def test_delete_refused_by_group_name(self):
        blade = _blade(quotas={(REALM_FS, GROUP): GIB})
        blade.fail["delete"] = REFUSED
        module = _module(gname=GROUP, state="absent")
        _run(module, blade)
        msg = _failure(module)
        assert REALM_FS in msg
        assert GROUP in msg
        assert REFUSED in msg
        assert blade.quotas == {(REALM_FS, GROUP): GIB}


class TestFileSystem:
    @pytest.mark.parametrize("name", ["tenant1::nosuch", "nosuch", "norealm::projects"])
    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_unknown_file_system(self, name, state):
        """An unknown file system or realm fails before any quota request."""
        blade = _blade(quotas=_twins("none"))
        module = _module(name=name, gid=GID, quota="1G", state=state)
        _run(module, blade)
        assert _failure(module) == "Filesystem {0} does not exist.".format(name)
        blade.get_file_systems.assert_called_once_with(names=[name])
        blade.get_quotas_groups.assert_not_called()
        _no_write(blade)
        assert blade.quotas == _twins("none")

    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_bare_name_is_not_resolved_to_a_realm(self, state):
        """The name is sent as given: the leaf of a realm file system is unknown."""
        quotas = {(REALM_FS, GID): GIB}
        blade = _blade(quotas=quotas, file_systems=(REALM_FS,))
        module = _module(name=ARRAY_FS, gid=GID, quota="2G", state=state)
        _run(module, blade)
        assert _failure(module) == "Filesystem projects does not exist."
        blade.get_file_systems.assert_called_once_with(names=[ARRAY_FS])
        blade.get_quotas_groups.assert_not_called()
        _no_write(blade)
        assert blade.quotas == quotas

    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_realm_name_is_not_stripped_to_the_array_level(self, state):
        """Only the array-level namesake exists: the realm name is unknown."""
        quotas = {(ARRAY_FS, GID): GIB}
        blade = _blade(quotas=quotas, file_systems=(ARRAY_FS,))
        module = _module(name=REALM_FS, gid=GID, quota="2G", state=state)
        _run(module, blade)
        assert _failure(module) == "Filesystem tenant1::projects does not exist."
        blade.get_file_systems.assert_called_once_with(names=[REALM_FS])
        _no_write(blade)
        assert blade.quotas == quotas


class TestContext:
    """context is the fleet context; it has nothing to do with the realm."""

    def test_no_fleet_sends_no_context(self):
        blade = _blade()
        module = _module(gid=GID, quota="1G")
        _run(module, blade)
        assert _changed(module) is True
        blade.get_fleets.assert_called_once_with()
        blade.get_arrays.assert_not_called()
        assert module.params["context"] == ""
        assert "context_names" not in blade.get_quotas_groups.call_args[1]
        assert "context_names" not in blade.post_quotas_groups.call_args[1]

    def test_fleet_member_defaults_to_the_local_array(self):
        blade = _blade(fleet=True)
        module = _module(gid=GID, quota="1G")
        _run(module, blade)
        assert _changed(module) is True
        assert module.params["context"] == LOCAL_ARRAY
        blade.get_quotas_groups.assert_called_once_with(
            file_system_names=[REALM_FS],
            filter="group.id=1234",
            context_names=[LOCAL_ARRAY],
        )
        blade.post_quotas_groups.assert_called_once_with(
            file_system_names=[REALM_FS],
            gids=[GID],
            quota={"quota": GIB},
            context_names=[LOCAL_ARRAY],
        )

    @pytest.mark.parametrize(
        "group,selector",
        [({"gid": GID}, {"gids": [GID]}), ({"gname": GROUP}, {"group_names": [GROUP]})],
    )
    def test_named_context_on_every_request(self, group, selector):
        key = list(group.values())[0]
        blade = _blade()

        create = _module(context="member2", quota="1G", **group)
        _run(create, blade)
        assert _changed(create) is True
        blade.post_quotas_groups.assert_called_once_with(
            file_system_names=[REALM_FS],
            quota={"quota": GIB},
            context_names=["member2"],
            **selector
        )

        update = _module(context="member2", quota="2G", **group)
        _run(update, blade)
        assert _changed(update) is True
        blade.patch_quotas_groups.assert_called_once_with(
            file_system_names=[REALM_FS],
            quota={"quota": 2 * GIB},
            context_names=["member2"],
            **selector
        )
        assert blade.quotas == {(REALM_FS, key): 2 * GIB}

        delete = _module(context="member2", state="absent", **group)
        _run(delete, blade)
        assert _changed(delete) is True
        blade.delete_quotas_groups.assert_called_once_with(
            file_system_names=[REALM_FS], context_names=["member2"], **selector
        )
        assert not blade.quotas

        for call in blade.get_quotas_groups.call_args_list:
            assert call[1]["context_names"] == ["member2"]
        blade.get_fleets.assert_not_called()

    @pytest.mark.parametrize("group", [{"gid": GID}, {"gname": GROUP}])
    def test_context_is_not_sent_before_rest_2_17(self, group):
        blade = _blade()

        create = _module(context="member2", quota="1G", **group)
        _run(create, blade, api_version="2.16")
        update = _module(context="member2", quota="2G", **group)
        _run(update, blade, api_version="2.16")
        delete = _module(context="member2", state="absent", **group)
        _run(delete, blade, api_version="2.16")

        assert [_changed(create), _changed(update), _changed(delete)] == [True] * 3
        blade.get_fleets.assert_not_called()
        requests = (
            blade.get_quotas_groups.call_args_list
            + blade.post_quotas_groups.call_args_list
            + blade.patch_quotas_groups.call_args_list
            + blade.delete_quotas_groups.call_args_list
        )
        # one read per run, a second one in the update, and the three writes
        assert len(requests) == 7
        for call in requests:
            assert "context_names" not in call[1]


class TestDocumentation:
    def test_name_documents_the_realm_form(self):
        name = yaml.safe_load(DOCUMENTATION)["options"]["name"]
        text = " ".join(name["description"])
        assert "C(realm::name)" in text
        assert "realm-scoped administrator" in text

    def test_examples_include_a_file_system_in_a_realm(self):
        tasks = [task[TASK] for task in yaml.safe_load(EXAMPLES)]
        assert [task for task in tasks if "::" in task["name"]]
        assert [task for task in tasks if "::" not in task["name"]]

    def test_examples_follow_the_argument_rules(self):
        for task in yaml.safe_load(EXAMPLES):
            args = task[TASK]
            assert ("gid" in args) != ("gname" in args), task["name"]
            if args.get("state", "present") == "present":
                assert "quota" in args, task["name"]
