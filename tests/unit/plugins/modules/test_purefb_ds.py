# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_ds module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import itertools
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

from plugins.module_utils.version import LooseVersion as RealLooseVersion
from plugins.modules.purefb_ds import main

MOD = "plugins.modules.purefb_ds"
# The answer of the array for a name it does not show to the caller: a server
# that does not exist, a realm that does not exist, and an array-level
# service asked for by a realm-scoped administrator all read the same.
MISSING = "Directory service does not exist."
REFUSED = "Operation not permitted."
REALM_SERVER = "tenant1::nas1"
REALM_DS = "tenant1::nas1_nfs"
ARRAY_SERVER = "nas1"
ARRAY_DS = "nas1_nfs"
NIS = {"nis_domain": "example.com", "nis_servers": ["192.0.2.10"]}
LDAP = {
    "uri": ["ldap://ad.example.com"],
    "base_dn": "DC=example,DC=com",
    "bind_user": "binder",
}
_IDS = itertools.count(1)


def _base_params(**overrides):
    params = {
        "state": "present",
        "dstype": "nfs",
        "enable": None,
        "uri": None,
        "base_dn": None,
        "bind_user": None,
        "bind_password": None,
        "force_bind_password": True,
        "nis_servers": None,
        "nis_domain": None,
        "join_ou": None,
        "nfs_server": None,
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


def _ds(name, enabled=False, nis_domains=(), nis_servers=(), **ldap):
    """A directory service as the array returns it.

    A service nothing was configured on has no URIs and empty NIS lists.
    """
    dirserv = Mock(
        spec=["id", "name", "uris", "base_dn", "bind_user", "enabled", "nfs", "smb"]
    )
    dirserv.id = "ds-{0}".format(next(_IDS))
    dirserv.name = name
    dirserv.uris = list(ldap.get("uri", ()))
    dirserv.base_dn = ldap.get("base_dn")
    dirserv.bind_user = ldap.get("bind_user")
    dirserv.enabled = enabled
    dirserv.nfs = Mock(spec=["nis_domains", "nis_servers"])
    dirserv.nfs.nis_domains = list(nis_domains)
    dirserv.nfs.nis_servers = list(nis_servers)
    dirserv.smb = Mock(spec=["join_ou"])
    dirserv.smb.join_ou = None
    return dirserv


def _nis_ds(name, domain="example.com", servers=("192.0.2.10",)):
    return _ds(name, nis_domains=[domain], nis_servers=servers)


def _ok(items=()):
    res = Mock(spec=["status_code", "items"])
    res.status_code = 200
    res.items = list(items)
    return res


def _error(status_code=400, message=MISSING):
    """An error response: it has errors and, as in the SDK, no items."""
    res = Mock(spec=["status_code", "errors"])
    res.status_code = status_code
    res.errors = []
    if message is not None:
        error = Mock(spec=["message"])
        error.message = message
        res.errors = [error]
    return res


def _error_message(response, default="Unknown error"):
    """What module_utils.common.get_error_message returns."""
    errors = getattr(response, "errors", None)
    if errors:
        return list(errors)[0].message
    return default


def _test_result(resource, success=True):
    result = Mock(
        spec=[
            "component_address",
            "component_name",
            "description",
            "destination",
            "enabled",
            "resource",
            "result_details",
            "success",
            "test_type",
        ]
    )
    result.component_address = "192.0.2.1"
    result.component_name = "CH1.FB1"
    result.description = "Testing NIS configuration"
    result.destination = "192.0.2.10"
    result.enabled = True
    result.resource = Mock(spec=["name"])
    result.resource.name = resource
    result.result_details = "" if success else "Timed out"
    result.success = success
    result.test_type = "nis-domain"
    return result


def _blade(*services):
    """A small stateful stand-in for the array.

    services are the directory services the caller is shown. Any other name
    answers 400 "Directory service does not exist.". Names match without
    regard to letter case, and a name that holds a comma is read as a list
    of names: every one of them is addressed, sorted by name, and one that
    is not shown fails the request. A PATCH changes the state, so a second
    run reads it back; an empty URI clears the URI list, as on the array.
    """
    store = dict((svc.name.lower(), svc) for svc in services)
    blade = Mock()
    blade.store = store

    def _addressed(kwargs):
        names = ",".join(kwargs["names"]).lower().split(",")
        found = [store.get(name) for name in names]
        if None in found:
            return None
        return sorted(found, key=lambda svc: svc.name)

    def _get(**kwargs):
        found = _addressed(kwargs)
        if found is None:
            return _error()
        return _ok(found)

    def _patch(**kwargs):
        found = _addressed(kwargs)
        if found is None:
            return _error()
        body = kwargs["directory_service"]
        for svc in found:
            if "uris" in body:
                svc.uris = [uri for uri in body["uris"] if uri]
            for key in ("base_dn", "bind_user", "enabled"):
                if key in body:
                    setattr(svc, key, body[key])
            if "nfs" in body:
                svc.nfs.nis_domains = list(body["nfs"]["nis_domains"])
                svc.nfs.nis_servers = list(body["nfs"]["nis_servers"])
            if "smb" in body:
                svc.smb.join_ou = body["smb"]["join_ou"]
        return _ok()

    def _test(**kwargs):
        found = _addressed(kwargs)
        if found is None:
            return _error()
        results = []
        for svc in found:
            results.append(_test_result(svc.name))
            results.append(_test_result(svc.name, success=False))
        return _ok(results)

    blade.get_directory_services.side_effect = _get
    blade.patch_directory_services.side_effect = _patch
    blade.get_directory_services_test.side_effect = _test
    return blade


def _run(module, blade, api_version="2.30", has_sdk=True):
    """Run main() with the module/blade mocks and the given REST version."""
    with patch(MOD + ".AnsibleModule", return_value=module), patch(
        MOD + ".get_system", return_value=blade
    ), patch(MOD + ".get_rest_api_version", return_value=api_version), patch(
        MOD + ".LooseVersion", RealLooseVersion
    ), patch(
        MOD + ".HAS_PYPURECLIENT", has_sdk
    ), patch(
        MOD + ".DirectoryService", side_effect=lambda **kw: kw
    ), patch(
        MOD + ".get_error_message", side_effect=_error_message
    ):
        try:
            main()
        except SystemExit:
            pass


def _result(module):
    """The keyword arguments of the one and only exit_json."""
    module.fail_json.assert_not_called()
    module.exit_json.assert_called_once()
    return module.exit_json.call_args[1]


def _failure(module):
    """The message of the one and only fail_json; nothing may exit after it."""
    module.exit_json.assert_not_called()
    module.fail_json.assert_called_once()
    return module.fail_json.call_args[1]["msg"]


def _patches(blade):
    """The (name, body) pairs of the PATCH requests in the order sent."""
    return [
        (call[1]["names"][0], call[1]["directory_service"])
        for call in blade.patch_directory_services.call_args_list
    ]


def _read_names(blade):
    """The names of the directory service reads in the order sent."""
    return [call[1]["names"][0] for call in blade.get_directory_services.call_args_list]


class TestMissingService:
    """A service the array does not show is an error for present and test."""

    def test_present_for_a_server_that_does_not_exist_fails(self):
        blade = _blade(_ds("nfs"), _ds(ARRAY_DS))
        module = _module(nfs_server="nosuch", **NIS)
        _run(module, blade)
        msg = _failure(module)
        assert "Directory Service nosuch_nfs does not exist" in msg
        assert "server nosuch" in msg
        assert "realm::server" in msg
        assert _patches(blade) == []

    def test_present_in_a_realm_that_does_not_exist_fails(self):
        blade = _blade(_ds("nfs"), _ds(ARRAY_DS))
        module = _module(nfs_server="norealm::nas1", **NIS)
        _run(module, blade)
        assert "norealm::nas1_nfs does not exist" in _failure(module)
        assert _patches(blade) == []

    def test_check_mode_fails_like_the_real_run(self):
        blade = _blade(_ds("nfs"))
        module = _module(check_mode=True, nfs_server="nosuch", **NIS)
        _run(module, blade)
        assert "nosuch_nfs does not exist" in _failure(module)

    def test_test_of_a_missing_service_fails(self):
        blade = _blade(_ds("nfs"))
        module = _module(state="test", nfs_server="nosuch")
        _run(module, blade)
        assert "nosuch_nfs does not exist" in _failure(module)
        blade.get_directory_services_test.assert_not_called()

    def test_bare_server_name_of_a_realm_administrator_fails(self):
        # The array-level server of the same leaf name exists, but its
        # service is not shown to an administrator of realm tenant1.
        blade = _blade(_nis_ds(REALM_DS))
        module = _module(
            nfs_server=ARRAY_SERVER,
            nis_domain="other.example",
            nis_servers=["192.0.2.30"],
        )
        _run(module, blade)
        msg = _failure(module)
        assert "Directory Service nas1_nfs does not exist" in msg
        assert "realm-scoped administrator must use that form" in msg
        assert _patches(blade) == []
        assert blade.store[REALM_DS.lower()].nfs.nis_domains == ["example.com"]

    def test_array_nfs_service_hidden_from_a_realm_administrator_fails(self):
        blade = _blade(_ds(REALM_DS))
        module = _module(check_mode=True, **NIS)
        _run(module, blade)
        msg = _failure(module)
        assert "Directory Service nfs does not exist for this user" in msg
        assert "array-level" in msg
        assert "nfs_server to realm::server" in msg

    def test_management_service_hidden_from_a_realm_administrator_fails(self):
        blade = _blade(_ds(REALM_DS))
        module = _module(dstype="management", bind_password="secret", **LDAP)
        _run(module, blade)
        msg = _failure(module)
        assert "Directory Service management does not exist for this user" in msg
        assert "array-level" in msg
        assert "nfs_server" not in msg
        assert _patches(blade) == []

    def test_management_test_hidden_from_a_realm_administrator_fails(self):
        blade = _blade(_ds(REALM_DS))
        module = _module(dstype="management", state="test")
        _run(module, blade)
        assert "management does not exist for this user" in _failure(module)
        blade.get_directory_services_test.assert_not_called()

    def test_empty_answer_reads_as_missing(self):
        blade = _blade()
        blade.get_directory_services.side_effect = None
        blade.get_directory_services.return_value = _ok([])
        module = _module(nfs_server=REALM_SERVER, **NIS)
        _run(module, blade)
        assert REALM_DS + " does not exist" in _failure(module)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_absent_of_a_missing_service_is_unchanged(self, check_mode):
        blade = _blade(_ds("nfs"))
        module = _module(
            check_mode=check_mode, state="absent", nfs_server="tenant1::nosuch"
        )
        _run(module, blade)
        assert _result(module) == {
            "changed": False,
            "msg": "Directory Service tenant1::nosuch_nfs does not exist",
        }
        assert _patches(blade) == []


class TestOneServer:
    """nfs_server names one server: the array reads a comma as a list of names."""

    @pytest.mark.parametrize("state", ["present", "absent", "test"])
    @pytest.mark.parametrize("check_mode", [False, True])
    def test_comma_in_the_server_name_is_refused(self, state, check_mode):
        # Without the refusal the array-level nfs service sorts first, is
        # the one compared, and the change goes to both services.
        blade = _blade(_ds("nfs", enabled=True, **LDAP), _nis_ds(REALM_DS))
        module = _module(
            check_mode=check_mode, state=state, nfs_server="nfs," + REALM_SERVER
        )
        _run(module, blade)
        msg = _failure(module)
        assert "name of one server" in msg
        assert "nfs," + REALM_SERVER in msg
        blade.get_directory_services.assert_not_called()
        blade.get_directory_services_test.assert_not_called()
        assert _patches(blade) == []
        assert blade.store["nfs"].uris == LDAP["uri"]
        assert blade.store[REALM_DS.lower()].nfs.nis_domains == ["example.com"]

    def test_comma_with_new_values_is_refused(self):
        blade = _blade(_ds("management", enabled=True, **LDAP), _ds(ARRAY_DS))
        module = _module(nfs_server="management," + ARRAY_SERVER, enable=False)
        _run(module, blade)
        assert "name of one server" in _failure(module)
        assert _patches(blade) == []
        assert blade.store["management"].enabled is True

    def test_comma_is_not_looked_at_for_management(self):
        blade = _blade(_ds("management", enabled=True, **LDAP))
        module = _module(dstype="management", nfs_server="a,b", enable=True)
        _run(module, blade)
        assert _result(module) == {"changed": False}
        assert set(_read_names(blade)) == {"management"}


class TestFailedRead:
    """A read the array refuses is reported with its message, never as absent."""

    @pytest.mark.parametrize("state", ["present", "absent", "test"])
    @pytest.mark.parametrize("check_mode", [False, True])
    def test_refused_read_fails_with_the_message_of_the_array(self, state, check_mode):
        blade = _blade(_nis_ds(REALM_DS))
        blade.get_directory_services.side_effect = None
        blade.get_directory_services.return_value = _error(403, REFUSED)
        module = _module(check_mode=check_mode, state=state, nfs_server=REALM_SERVER)
        _run(module, blade)
        msg = _failure(module)
        assert REALM_DS in msg
        assert REFUSED in msg
        assert _patches(blade) == []
        blade.get_directory_services_test.assert_not_called()

    def test_error_without_a_message_is_not_read_as_missing(self):
        blade = _blade()
        blade.get_directory_services.side_effect = None
        blade.get_directory_services.return_value = _error(500, None)
        module = _module(state="absent", dstype="management")
        _run(module, blade)
        msg = _failure(module)
        assert "management" in msg
        assert "Unknown error" in msg

    def test_refused_test_fails_with_the_message_of_the_array(self):
        blade = _blade(_nis_ds(REALM_DS))
        blade.get_directory_services_test.side_effect = None
        blade.get_directory_services_test.return_value = _error(400, REFUSED)
        module = _module(state="test", nfs_server=REALM_SERVER)
        _run(module, blade)
        msg = _failure(module)
        assert REALM_DS in msg
        assert REFUSED in msg


class TestAbsent:
    """state=absent clears the configuration and check mode predicts it."""

    def test_check_mode_on_a_cleared_realm_service_is_unchanged(self):
        blade = _blade(_ds(REALM_DS), _nis_ds(ARRAY_DS))
        module = _module(check_mode=True, state="absent", nfs_server=REALM_SERVER)
        _run(module, blade)
        assert _result(module) == {"changed": False}
        assert _patches(blade) == []

    @pytest.mark.parametrize("dstype", ["management", "nfs"])
    def test_check_mode_on_a_cleared_array_service_is_unchanged(self, dstype):
        blade = _blade(_ds(dstype))
        module = _module(check_mode=True, state="absent", dstype=dstype)
        _run(module, blade)
        assert _result(module) == {"changed": False}
        assert _patches(blade) == []

    def test_check_mode_on_a_nis_service_reports_changed_and_writes_nothing(self):
        blade = _blade(_nis_ds(REALM_DS))
        module = _module(check_mode=True, state="absent", nfs_server=REALM_SERVER)
        _run(module, blade)
        assert _result(module) == {"changed": True}
        assert _patches(blade) == []
        assert blade.store[REALM_DS.lower()].nfs.nis_domains == ["example.com"]

    @pytest.mark.parametrize("dstype", ["management", "nfs"])
    def test_check_mode_on_an_ldap_service_reports_changed_and_writes_nothing(
        self, dstype
    ):
        blade = _blade(_ds(dstype, enabled=True, **LDAP))
        module = _module(check_mode=True, state="absent", dstype=dstype)
        _run(module, blade)
        assert _result(module) == {"changed": True}
        assert _patches(blade) == []

    def test_clears_nis_on_the_realm_service_only_and_is_idempotent(self):
        blade = _blade(_nis_ds(REALM_DS), _nis_ds(ARRAY_DS, domain="twin.example"))
        module = _module(state="absent", nfs_server=REALM_SERVER)
        _run(module, blade)
        assert _result(module) == {"changed": True}
        assert _patches(blade) == [
            (
                REALM_DS,
                {"nfs": {"nis_domains": [], "nis_servers": []}, "enabled": False},
            )
        ]
        assert blade.store[ARRAY_DS].nfs.nis_domains == ["twin.example"]
        for check_mode in (False, True):
            again = _module(
                check_mode=check_mode, state="absent", nfs_server=REALM_SERVER
            )
            _run(again, blade)
            assert _result(again) == {"changed": False}
        assert len(_patches(blade)) == 1

    @pytest.mark.parametrize("dstype", ["management", "nfs"])
    def test_clears_ldap_and_is_idempotent(self, dstype):
        blade = _blade(_ds(dstype, enabled=True, **LDAP))
        module = _module(state="absent", dstype=dstype)
        _run(module, blade)
        assert _result(module) == {"changed": True}
        cleared = {
            "uris": [""],
            "base_dn": "",
            "bind_user": "",
            "bind_password": "",
            "enabled": False,
        }
        assert _patches(blade) == [(dstype, cleared)]
        again = _module(state="absent", dstype=dstype)
        _run(again, blade)
        assert _result(again) == {"changed": False}
        assert len(_patches(blade)) == 1

    def test_clears_smb_on_an_array_that_still_has_it(self):
        blade = _blade(_ds("smb", enabled=True, **LDAP))
        module = _module(state="absent", dstype="smb")
        _run(module, blade, api_version="2.15")
        assert _result(module) == {"changed": True}
        assert _patches(blade)[0][1]["smb"] == {"join_ou": ""}

    def test_failed_clear_is_reported(self):
        blade = _blade(_nis_ds(REALM_DS))
        blade.patch_directory_services.side_effect = None
        blade.patch_directory_services.return_value = _error(400, REFUSED)
        module = _module(state="absent", nfs_server=REALM_SERVER)
        _run(module, blade)
        msg = _failure(module)
        assert REALM_DS in msg
        assert REFUSED in msg


class TestPresent:
    """state=present compares with the service of the named server."""

    def test_nis_on_a_realm_server_changes_only_that_service(self):
        blade = _blade(
            _ds("nfs"), _ds(REALM_DS), _nis_ds(ARRAY_DS, domain="twin.example")
        )
        module = _module(nfs_server=REALM_SERVER, **NIS)
        _run(module, blade)
        assert _result(module) == {"changed": True}
        wanted = {"nis_domains": ["example.com"], "nis_servers": ["192.0.2.10"]}
        assert _patches(blade) == [(REALM_DS, {"nfs": wanted})]
        assert set(_read_names(blade)) == {REALM_DS}
        assert blade.store[ARRAY_DS].nfs.nis_domains == ["twin.example"]
        again = _module(nfs_server=REALM_SERVER, **NIS)
        _run(again, blade)
        assert _result(again) == {"changed": False}
        assert len(_patches(blade)) == 1

    def test_nis_on_the_array_level_twin_leaves_the_realm_service(self):
        blade = _blade(_nis_ds(REALM_DS), _ds(ARRAY_DS))
        module = _module(
            nfs_server=ARRAY_SERVER,
            nis_domain="twin.example",
            nis_servers=["192.0.2.20"],
        )
        _run(module, blade)
        assert _result(module) == {"changed": True}
        assert [name for name, body in _patches(blade)] == [ARRAY_DS]
        assert blade.store[REALM_DS.lower()].nfs.nis_domains == ["example.com"]

    def test_check_mode_reports_the_change_and_writes_nothing(self):
        blade = _blade(_ds(REALM_DS))
        module = _module(check_mode=True, nfs_server=REALM_SERVER, **NIS)
        _run(module, blade)
        assert _result(module) == {"changed": True}
        assert _patches(blade) == []

    @pytest.mark.parametrize(
        "nfs_server", [None, "", "_array_server", "_ARRAY_SERVER", "_Array_Server"]
    )
    def test_default_server_is_the_array_level_nfs_service(self, nfs_server):
        blade = _blade(_ds("nfs", **LDAP), _ds(ARRAY_DS))
        module = _module(nfs_server=nfs_server)
        _run(module, blade)
        assert _result(module) == {"changed": False}
        assert set(_read_names(blade)) == {"nfs"}

    def test_server_name_in_another_letter_case_is_the_same_service(self):
        blade = _blade(_nis_ds(REALM_DS))
        module = _module(nfs_server=REALM_SERVER.upper(), **NIS)
        _run(module, blade)
        assert _result(module) == {"changed": False}
        assert _patches(blade) == []

    def test_nfs_server_is_ignored_for_management(self):
        blade = _blade(_ds("management", enabled=True, **LDAP))
        module = _module(dstype="management", nfs_server=REALM_SERVER, enable=True)
        _run(module, blade)
        assert _result(module) == {"changed": False}
        assert set(_read_names(blade)) == {"management"}

    def test_enable_is_applied_once(self):
        blade = _blade(_nis_ds(REALM_DS))
        module = _module(nfs_server=REALM_SERVER, enable=True)
        _run(module, blade)
        assert _result(module) == {"changed": True}
        assert _patches(blade) == [(REALM_DS, {"enabled": True})]
        again = _module(nfs_server=REALM_SERVER, enable=True)
        _run(again, blade)
        assert _result(again) == {"changed": False}

    def test_ldap_on_a_realm_server_then_unchanged_without_the_password(self):
        blade = _blade(_ds(REALM_DS))
        module = _module(nfs_server=REALM_SERVER, bind_password="secret", **LDAP)
        _run(module, blade)
        assert _result(module) == {"changed": True}
        wanted = dict(
            uris=LDAP["uri"],
            base_dn=LDAP["base_dn"],
            bind_user=LDAP["bind_user"],
            bind_password="secret",
        )
        assert _patches(blade) == [(REALM_DS, wanted)]
        again = _module(nfs_server=REALM_SERVER, **LDAP)
        _run(again, blade)
        assert _result(again) == {"changed": False}
        assert len(_patches(blade)) == 1

    def test_new_uri_without_the_password_fails(self):
        blade = _blade(_ds(REALM_DS, **LDAP))
        changed = dict(LDAP)
        changed["uri"] = ["ldap://other.example.com"]
        module = _module(nfs_server=REALM_SERVER, **changed)
        _run(module, blade)
        assert "'bind_password' must be provided" in _failure(module)
        assert _patches(blade) == []

    def test_nis_values_on_an_ldap_service_fail(self):
        blade = _blade(_ds(REALM_DS, **LDAP))
        module = _module(nfs_server=REALM_SERVER, **NIS)
        _run(module, blade)
        assert "NIS configuration not supported" in _failure(module)
        assert _patches(blade) == []

    def test_failed_change_is_reported(self):
        blade = _blade(_ds(REALM_DS))
        blade.patch_directory_services.side_effect = None
        blade.patch_directory_services.return_value = _error(400, REFUSED)
        module = _module(nfs_server=REALM_SERVER, **NIS)
        _run(module, blade)
        msg = _failure(module)
        assert REALM_DS in msg
        assert REFUSED in msg


class TestStateTest:
    """state=test returns what the array reports for the named service."""

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_results_of_the_realm_service(self, check_mode):
        blade = _blade(_nis_ds(REALM_DS), _nis_ds(ARRAY_DS))
        module = _module(check_mode=check_mode, state="test", nfs_server=REALM_SERVER)
        _run(module, blade)
        result = _result(module)
        assert result["changed"] is False
        blade.get_directory_services_test.assert_called_once_with(names=[REALM_DS])
        assert [item["resource_name"] for item in result["test_response"]] == [
            REALM_DS,
            REALM_DS,
        ]
        assert [item["success"] for item in result["test_response"]] == [
            "true",
            "false",
        ]
        assert result["test_response"][1]["result_details"] == "Timed out"
        assert _patches(blade) == []


class TestGates:
    def test_smb_is_not_managed_from_rest_2_16(self):
        blade = _blade(_ds("nfs"))
        module = _module(dstype="smb", join_ou="OU=fb", bind_password="secret", **LDAP)
        _run(module, blade, api_version="2.16")
        assert _result(module) == {"changed": False}
        module.warn.assert_called_once()
        blade.get_directory_services.assert_not_called()

    def test_sdk_is_required(self):
        blade = _blade(_ds("nfs"))
        module = _module()
        _run(module, blade, has_sdk=False)
        assert "py-pure-client" in _failure(module)
        blade.get_directory_services.assert_not_called()
