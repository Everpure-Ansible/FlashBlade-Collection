# Copyright: (c) 2026, Pure Storage Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_realm module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from contextlib import ExitStack
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
from plugins.modules.purefb_realm import main

MOD = "plugins.modules.purefb_realm"

# Answers of Purity//FB 4.8.8
NO_REALM = "Realm does not exist."
EXISTS = "A realm already exists with the given name."
CONTAINS = (
    "This realm contains entities. Please destroy and eradicate all entities "
    "before destroying the realm."
)
DENIED = "Operation not permitted."
STALE = "Object changed during processing. Please try again."
NEEDS_FLAG = "without_default_access_list query parameter is required."
# The stand-in's own answer where the answer of the array is not known
REFUSED = "Refused by the stand-in."


class _Item:
    """A plain object with the given attributes: a model or a response."""

    def __init__(self, **attrs):
        self.__dict__.update(attrs)


def _ok(items=None):
    return _Item(status_code=200, items=list(items or []), errors=[])


def _err(message):
    return _Item(status_code=400, items=[], errors=[_Item(message=message)])


def _error_message(res, default="Unknown error"):
    errors = list(getattr(res, "errors", None) or [])
    return errors[0].message if errors else default


def _body(**kwargs):
    """Stand-in for the pypureclient models, so request bodies compare."""
    return kwargs


def _find(names, wanted):
    """The array matches names without regard to case and returns the name
    it keeps."""
    for name in names:
        if name.lower() == wanted.lower():
            return name
    return None


def _prefix(name):
    return name.rpartition("::")[0]


class _Array:
    """A small stateful stand-in for the array.

    realms and destroyed name the live and the destroyed realms. qos maps a
    realm to its QoS policy, defaults a realm to its default object store
    server and tls a realm to its default inbound TLS policy (full names).
    accesses are (resource type, resource name, realm) and rules (management
    access policy, realm). entities names realms that hold objects of other
    kinds. realm_admin makes it answer a realm-scoped administrator. fail
    maps a method, or patch_realms.name / .destroyed / .tls, to the message
    that request is refused with; a list holds one answer for each call and
    None lets a call through. writes records every write that was sent.
    """

    METHODS = (
        "get_realms",
        "post_realms",
        "patch_realms",
        "delete_realms",
        "get_qos_policies",
        "get_qos_policies_members",
        "post_qos_policies_members",
        "delete_qos_policies_members",
        "get_servers",
        "get_tls_policies",
        "get_realms_defaults",
        "patch_realms_defaults",
        "get_resource_accesses",
        "get_management_access_policies",
    )
    REST_2_20 = (
        "post_qos_policies_members",
        "delete_qos_policies_members",
        "get_realms_defaults",
        "patch_realms_defaults",
    )

    def __init__(
        self,
        realms=("tenant1",),
        destroyed=(),
        qos_policies=("gold", "silver"),
        qos=None,
        servers=(),
        defaults=None,
        tls_policies=(),
        tls=None,
        accesses=(),
        rules=(),
        entities=(),
    ):
        self.realms = {}
        for name in realms:
            self.realms[name.lower()] = {"name": name, "destroyed": False, "tls": None}
        for name in destroyed:
            self.realms[name.lower()] = {"name": name, "destroyed": True, "tls": None}
        for realm, policy in (tls or {}).items():
            self.realms[realm.lower()]["tls"] = policy
        self.qos_policies = list(qos_policies)
        self.qos = dict(
            (realm.lower(), policy) for realm, policy in (qos or {}).items()
        )
        self.servers = list(servers)
        self.defaults = dict(
            (realm.lower(), server) for realm, server in (defaults or {}).items()
        )
        self.tls_policies = list(tls_policies)
        self.accesses = [list(access) for access in accesses]
        self.rules = [list(rule) for rule in rules]
        self.entities = set(name.lower() for name in entities)
        self.realm_admin = False
        self.fail = {}
        self.writes = []

    def blade(self, api_version="2.30"):
        blade = Mock()
        for method in self.METHODS:
            setattr(blade, method, Mock(side_effect=getattr(self, method)))
        if api_version == "2.19":
            for method in self.REST_2_20:
                delattr(blade, method)
        return blade

    # ---- state helpers ----

    def _refused(self, key):
        answer = self.fail.get(key)
        if isinstance(answer, list):
            answer = answer.pop(0) if answer else None
        return answer

    def _realm(self, name):
        return self.realms.get(name.lower())

    def name_of(self, name):
        """The name the array keeps for the realm, None when it has none."""
        realm = self._realm(name)
        return realm["name"] if realm else None

    def is_destroyed(self, name):
        return self._realm(name)["destroyed"]

    def tls_of(self, name):
        return self._realm(name)["tls"]

    def qos_of(self, name):
        return self.qos.get(name.lower())

    def default_of(self, name):
        return self.defaults.get(name.lower())

    def _holds_something(self, realm):
        key = realm["name"].lower()
        members = [
            name
            for name in self.servers + self.tls_policies
            if _prefix(name).lower() == key
        ]
        scoped = [
            entry for entry in self.accesses + self.rules if entry[-1].lower() == key
        ]
        return bool(members or scoped or key in self.qos or key in self.entities)

    def _rename(self, realm, new):
        old = realm["name"]

        def moved(name):
            if _prefix(name).lower() == old.lower():
                return "{0}::{1}".format(new, name.rpartition("::")[2])
            return name

        del self.realms[old.lower()]
        realm["name"] = new
        self.realms[new.lower()] = realm
        self.servers = [moved(name) for name in self.servers]
        self.tls_policies = [moved(name) for name in self.tls_policies]
        if old.lower() in self.defaults:
            self.defaults[new.lower()] = moved(self.defaults.pop(old.lower()))
        if old.lower() in self.qos:
            self.qos[new.lower()] = self.qos.pop(old.lower())
        if old.lower() in self.entities:
            self.entities.discard(old.lower())
            self.entities.add(new.lower())
        for entry in self.accesses + self.rules:
            if entry[-1].lower() == old.lower():
                entry[-1] = new
        # the reference to the default inbound TLS policy keeps the name the
        # policy had before the rename

    # ---- realms ----

    def get_realms(self, names=None, destroyed=None, **kwargs):
        refused = self._refused("get_realms")
        if refused:
            return _err(refused)
        realm = self._realm(names[0])
        if realm is None:
            return _err(NO_REALM)
        if destroyed is True and not realm["destroyed"]:
            return _err("Realm is not destroyed.")
        if destroyed is False and realm["destroyed"]:
            return _err("Realm has been destroyed.")
        policy = None
        if realm["tls"]:
            policy = _Item(name=realm["tls"], resource_type="tls-policies")
        return _ok(
            [
                _Item(
                    name=realm["name"],
                    destroyed=realm["destroyed"],
                    default_inbound_tls_policy=policy,
                )
            ]
        )

    def post_realms(self, names=None, without_default_access_list=None, **kwargs):
        name = names[0]
        self.writes.append(("create", name))
        refused = self._refused("post_realms")
        if refused or self.realm_admin:
            return _err(refused or DENIED)
        if not without_default_access_list:
            return _err(NEEDS_FLAG)
        if "::" in name:
            return _err("Realm name must be between 1 and 63 characters.")
        if self._realm(name) is not None:
            return _err(EXISTS)
        self.realms[name.lower()] = {"name": name, "destroyed": False, "tls": None}
        return _ok()

    def patch_realms(self, names=None, realm=None, **kwargs):
        body = realm
        current = self._realm(names[0])
        if "name" in body:
            self.writes.append(("rename", names[0], body["name"]))
            refused = self._refused("patch_realms.name")
            if refused or self.realm_admin:
                return _err(refused or DENIED)
            if current is None:
                return _err(NO_REALM)
            if body["name"] != current["name"]:
                if self._realm(body["name"]) is not None:
                    return _err(EXISTS)
                self._rename(current, body["name"])
        if "destroyed" in body:
            action = "destroy" if body["destroyed"] else "recover"
            self.writes.append((action, names[0]))
            refused = self._refused("patch_realms.destroyed")
            if refused:
                return _err(refused)
            if current is None:
                return _err(NO_REALM)
            if body["destroyed"] and self._holds_something(current):
                return _err(CONTAINS)
            current["destroyed"] = body["destroyed"]
        if "default_inbound_tls_policy" in body:
            wanted = body["default_inbound_tls_policy"]["name"]
            self.writes.append(("tls", names[0], wanted))
            refused = self._refused("patch_realms.tls")
            if refused or self.realm_admin:
                return _err(refused or DENIED)
            if current is None:
                return _err(NO_REALM)
            if current["tls"] and (
                _prefix(current["tls"]).lower() != current["name"].lower()
            ):
                return _err(STALE)
            if wanted == "":
                current["tls"] = None
            else:
                policy = _find(self.tls_policies, wanted)
                if policy is None or (
                    _prefix(policy).lower() != current["name"].lower()
                ):
                    return _err("TLS Policy does not exist.")
                current["tls"] = policy
        return _ok()

    def delete_realms(self, names=None, **kwargs):
        self.writes.append(("eradicate", names[0]))
        refused = self._refused("delete_realms")
        if refused:
            return _err(refused)
        realm = self._realm(names[0])
        if realm is None:
            return _err(NO_REALM)
        if not realm["destroyed"]:
            return _err(REFUSED)
        del self.realms[realm["name"].lower()]
        return _ok()

    # ---- QoS ----

    def get_qos_policies(self, names=None, **kwargs):
        refused = self._refused("get_qos_policies")
        if refused:
            return _err(refused)
        policy = _find(self.qos_policies, names[0])
        if policy is None or self.realm_admin:
            return _err("QoS Policy does not exist.")
        return _ok([_Item(name=policy)])

    def get_qos_policies_members(self, member_types=None, member_names=None, **kwargs):
        refused = self._refused("get_qos_policies_members")
        if refused:
            return _err(refused)
        realm = self._realm(member_names[0])
        if realm is None:
            return _err("Member does not exist.")
        policy = self.qos.get(realm["name"].lower())
        if policy is None or self.realm_admin:
            return _ok()
        return _ok(
            [
                _Item(
                    policy=_Item(name=policy),
                    member=_Item(name=realm["name"], resource_type="realms"),
                )
            ]
        )

    def post_qos_policies_members(
        self, policy_names=None, member_names=None, member_types=None, **kwargs
    ):
        self.writes.append(("attach", member_names[0], policy_names[0]))
        refused = self._refused("post_qos_policies_members")
        if refused:
            return _err(refused)
        realm = self._realm(member_names[0])
        policy = _find(self.qos_policies, policy_names[0])
        if realm is None or policy is None or realm["name"].lower() in self.qos:
            return _err(REFUSED)
        self.qos[realm["name"].lower()] = policy
        return _ok()

    def delete_qos_policies_members(
        self, policy_names=None, member_names=None, member_types=None, **kwargs
    ):
        self.writes.append(("detach", member_names[0], policy_names[0]))
        refused = self._refused("delete_qos_policies_members")
        if refused:
            return _err(refused)
        realm = self._realm(member_names[0])
        attached = self.qos.get(realm["name"].lower()) if realm else None
        if attached is None or attached.lower() != policy_names[0].lower():
            return _err(REFUSED)
        del self.qos[realm["name"].lower()]
        return _ok()

    # ---- members of a realm ----

    def get_servers(self, names=None, **kwargs):
        refused = self._refused("get_servers")
        if refused:
            return _err(refused)
        server = _find(self.servers, names[0])
        if server is None:
            return _err("Server does not exist.")
        return _ok([_Item(name=server)])

    def get_tls_policies(self, names=None, **kwargs):
        refused = self._refused("get_tls_policies")
        if refused:
            return _err(refused)
        policy = _find(self.tls_policies, names[0])
        if policy is None:
            return _err("TLS Policy does not exist.")
        return _ok([_Item(name=policy)])

    def get_realms_defaults(self, realm_names=None, **kwargs):
        refused = self._refused("get_realms_defaults")
        if refused:
            return _err(refused)
        realm = self._realm(realm_names[0])
        if realm is None:
            return _err(NO_REALM)
        object_store = []
        server = self.defaults.get(realm["name"].lower())
        if server:
            object_store = [_Item(server=_Item(name=server))]
        return _ok([_Item(realm=_Item(name=realm["name"]), object_store=object_store)])

    def patch_realms_defaults(
        self, realm_names=None, default_realm_configuration=None, **kwargs
    ):
        object_store = default_realm_configuration["object_store"]
        wanted = object_store[0]["server"]["name"] if object_store else None
        self.writes.append(("default", realm_names[0], wanted))
        refused = self._refused("patch_realms_defaults")
        if refused:
            return _err(refused)
        realm = self._realm(realm_names[0])
        if realm is None:
            return _err(NO_REALM)
        if wanted is None:
            self.defaults.pop(realm["name"].lower(), None)
            return _ok()
        server = _find(self.servers, wanted)
        if server is None or _prefix(server).lower() != realm["name"].lower():
            return _err("Server does not exist.")
        self.defaults[realm["name"].lower()] = server
        return _ok()

    # ---- what refers to a realm ----

    def get_resource_accesses(self, **kwargs):
        refused = self._refused("get_resource_accesses")
        if refused or self.realm_admin:
            return _err(refused or DENIED)
        wanted = kwargs["filter"].split("'")[1]
        return _ok(
            [
                _Item(
                    resource=_Item(resource_type=kind, name=name),
                    scope=_Item(resource_type="realms", name=realm),
                )
                for kind, name, realm in self.accesses
                if realm.lower() == wanted.lower()
            ]
        )

    def get_management_access_policies(self, **kwargs):
        refused = self._refused("get_management_access_policies")
        if refused or self.realm_admin:
            return _err(refused or DENIED)
        policies = {}
        for policy, realm in self.rules:
            rule = _Item(scope=_Item(resource_type="realms", name=realm))
            policies.setdefault(policy, []).append(rule)
        built_in = _Item(scope=_Item(resource_type="arrays", name="array1"))
        policies["pure:policy/array_admin"] = [built_in]
        return _ok([_Item(name=name, rules=rules) for name, rules in policies.items()])


def _params(**overrides):
    params = {
        "name": "tenant1",
        "without_default_access_list": True,
        "state": "present",
        "qos_policy": None,
        "eradicate": False,
        "rename": None,
        "default_object_server": None,
        "default_inbound_tls_policy": None,
    }
    params.update(overrides)
    return params


def _run(array, check_mode=False, api_version="2.30", sdk=True, **overrides):
    """Run main() against the stand-in array and return the module mock."""
    module = Mock()
    module.params = _params(**overrides)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.blade = array.blade(api_version)
    module.get_system = Mock(return_value=module.blade)
    replaced = {
        "AnsibleModule": Mock(return_value=module),
        "get_system": module.get_system,
        "get_rest_api_version": Mock(return_value=api_version),
        "LooseVersion": RealLooseVersion,
        "HAS_PURESTORAGE": sdk,
        "RealmPatch": _body,
        "RealmDefaults": _body,
        "ObjectStoreDefault": _body,
        "Reference": _body,
        "get_error_message": _error_message,
    }
    with ExitStack() as stack:
        for name, value in replaced.items():
            stack.enter_context(patch(MOD + "." + name, value))
        try:
            main()
        except SystemExit:
            pass
    return module


def _changed(module):
    module.fail_json.assert_not_called()
    module.exit_json.assert_called_once()
    return module.exit_json.call_args[1]["changed"]


def _failure(module):
    """The message of the one and only fail_json; nothing may exit after it."""
    module.fail_json.assert_called_once()
    module.exit_json.assert_not_called()
    return module.fail_json.call_args[1]["msg"]


def _warnings(module):
    return [call[0][0] for call in module.warn.call_args_list]


class TestPurefbRealm:
    """Create, destroy, recover, eradicate and rename"""

    def test_create(self):
        array = _Array(realms=())
        module = _run(array)
        assert _changed(module) is True
        assert array.writes == [("create", "tenant1")]
        module.blade.post_realms.assert_called_once_with(
            names=["tenant1"], without_default_access_list=True
        )

    def test_create_again_is_noop(self):
        array = _Array(realms=())
        _run(array)
        array.writes = []
        assert _changed(_run(array)) is False
        assert array.writes == []

    def test_create_check_mode(self):
        array = _Array(realms=())
        assert _changed(_run(array, check_mode=True)) is True
        assert array.writes == []

    def test_create_failure_is_reported(self):
        array = _Array(realms=())
        array.realm_admin = True
        message = _failure(_run(array))
        assert "Creation of realm tenant1 failed" in message
        assert DENIED in message

    def test_create_with_default_access_list_failure_carries_hint(self):
        array = _Array(realms=())
        message = _failure(_run(array, without_default_access_list=False))
        assert NEEDS_FLAG in message
        assert "set without_default_access_list to true" in message

    def test_refused_realm_read_is_reported(self):
        array = _Array(realms=())
        array.fail["get_realms"] = DENIED
        message = _failure(_run(array))
        assert "Failed to read realm tenant1" in message
        assert DENIED in message
        assert array.writes == []

    def test_realm_in_other_case_is_found(self):
        array = _Array(realms=("Tenant1",))
        assert _changed(_run(array, name="TENANT1")) is False
        assert array.writes == []

    def test_destroy(self):
        array = _Array()
        assert _changed(_run(array, state="absent")) is True
        assert array.writes == [("destroy", "tenant1")]
        assert array.is_destroyed("tenant1")

    def test_destroy_again_is_noop(self):
        array = _Array(realms=(), destroyed=("tenant1",))
        assert _changed(_run(array, state="absent")) is False
        assert array.writes == []

    def test_destroy_check_mode(self):
        array = _Array()
        assert _changed(_run(array, state="absent", check_mode=True)) is True
        assert array.writes == []

    def test_destroy_uses_the_name_the_array_keeps(self):
        array = _Array(realms=("Tenant1",))
        assert _changed(_run(array, name="TENANT1", state="absent")) is True
        assert array.writes == [("destroy", "Tenant1")]

    def test_destroy_failure_is_reported(self):
        array = _Array(entities=("tenant1",))
        message = _failure(_run(array, state="absent"))
        assert "Deleting realm tenant1 failed" in message
        assert CONTAINS in message

    def test_destroy_and_eradicate(self):
        array = _Array()
        assert _changed(_run(array, state="absent", eradicate=True)) is True
        assert array.writes == [("destroy", "tenant1"), ("eradicate", "tenant1")]
        assert array.name_of("tenant1") is None

    def test_destroy_and_eradicate_check_mode(self):
        array = _Array()
        module = _run(array, state="absent", eradicate=True, check_mode=True)
        assert _changed(module) is True
        assert array.writes == []

    def test_eradicate_destroyed_realm(self):
        array = _Array(realms=(), destroyed=("tenant1",))
        assert _changed(_run(array, state="absent", eradicate=True)) is True
        assert array.writes == [("eradicate", "tenant1")]

    def test_eradicate_failure_is_reported(self):
        array = _Array(realms=(), destroyed=("tenant1",))
        array.fail["delete_realms"] = DENIED
        message = _failure(_run(array, state="absent", eradicate=True))
        assert "Eradicating realm tenant1 failed" in message
        assert DENIED in message

    def test_absent_on_missing_realm_is_noop(self):
        array = _Array(realms=())
        assert _changed(_run(array, state="absent", eradicate=True)) is False
        assert array.writes == []

    def test_recover(self):
        array = _Array(realms=(), destroyed=("tenant1",))
        assert _changed(_run(array)) is True
        assert array.writes == [("recover", "tenant1")]
        assert not array.is_destroyed("tenant1")

    def test_recover_check_mode(self):
        array = _Array(realms=(), destroyed=("tenant1",))
        assert _changed(_run(array, check_mode=True)) is True
        assert array.writes == []

    def test_recover_failure_is_reported(self):
        array = _Array(realms=(), destroyed=("tenant1",))
        array.fail["patch_realms.destroyed"] = DENIED
        message = _failure(_run(array))
        assert "Recovery of realm tenant1 failed" in message
        assert DENIED in message

    def test_rename(self):
        array = _Array()
        assert _changed(_run(array, rename="tenant2")) is True
        assert array.writes == [("rename", "tenant1", "tenant2")]
        assert array.name_of("tenant2") == "tenant2"

    def test_rename_check_mode(self):
        array = _Array()
        assert _changed(_run(array, rename="tenant2", check_mode=True)) is True
        assert array.writes == []

    def test_rename_again_is_noop_without_warning(self):
        array = _Array(realms=("tenant2",))
        module = _run(array, rename="tenant2")
        assert _changed(module) is False
        assert array.writes == []
        assert _warnings(module) == []

    def test_rename_failure_is_reported(self):
        array = _Array()
        array.realm_admin = True
        message = _failure(_run(array, rename="tenant2"))
        assert "Rename to tenant2 failed" in message
        assert DENIED in message

    def test_api_version_too_old(self):
        array = _Array()
        message = _failure(_run(array, api_version="2.18"))
        assert "Realms are not supported" in message
        assert array.writes == []

    def test_missing_sdk_fails_before_any_array_call(self):
        array = _Array()
        module = _run(array, sdk=False)
        assert "py-pure-client sdk is required" in _failure(module)
        module.get_system.assert_not_called()


class TestPurefbRealmNames:
    """What a realm can be called and what rename asks for"""

    def test_separator_in_name_fails_before_login(self):
        array = _Array()
        module = _run(array, name="tenant1::inner", check_mode=True)
        assert "a realm name cannot contain '::'" in _failure(module)
        module.get_system.assert_not_called()

    def test_separator_in_rename_fails_before_login(self):
        array = _Array()
        module = _run(array, rename="tenant1::inner")
        assert "rename tenant1::inner is not a realm name" in _failure(module)
        module.get_system.assert_not_called()

    def test_comma_in_name_fails_before_login(self):
        array = _Array(realms=("tenant1", "tenant2"))
        for state in ("present", "absent"):
            module = _run(array, name="tenant1,tenant2", state=state)
            assert "name tenant1,tenant2 is not a name" in _failure(module)
            module.get_system.assert_not_called()
        assert array.writes == []

    def test_comma_in_rename_fails_before_login(self):
        array = _Array()
        module = _run(array, rename="tenant2,tenant3", check_mode=True)
        assert "rename tenant2,tenant3 is not a name" in _failure(module)
        module.get_system.assert_not_called()

    def test_comma_in_a_reference_fails_before_login(self):
        for option in (
            "qos_policy",
            "default_object_server",
            "default_inbound_tls_policy",
        ):
            array = _Array()
            module = _run(array, **{option: "one,two"})
            assert "{0} one,two is not a name".format(option) in _failure(module)
            module.get_system.assert_not_called()
            assert array.writes == []

    def test_rename_equal_to_name_is_noop(self):
        array = _Array()
        for check_mode in (True, False):
            module = _run(array, rename="tenant1", check_mode=check_mode)
            assert _changed(module) is False
        assert array.writes == []

    def test_rename_equal_to_name_creates_a_missing_realm(self):
        array = _Array(realms=())
        assert _changed(_run(array, rename="tenant1")) is True
        assert array.writes == [("create", "tenant1")]

    def test_rename_to_the_name_the_array_keeps_is_noop(self):
        array = _Array(realms=("tenant1",))
        assert _changed(_run(array, name="TENANT1", rename="tenant1")) is False
        assert array.writes == []

    def test_rename_that_differs_only_in_case_is_refused(self):
        array = _Array()
        for check_mode in (True, False):
            module = _run(array, rename="Tenant1", check_mode=check_mode)
            assert "only in letter case" in _failure(module)
        assert array.writes == []

    def test_rename_onto_existing_realm_is_refused(self):
        array = _Array(realms=("tenant1", "tenant2"))
        for check_mode in (True, False):
            module = _run(array, rename="TENANT2", check_mode=check_mode)
            message = _failure(module)
            assert "a realm named tenant2 already exists." in message
        assert array.writes == []

    def test_rename_onto_destroyed_realm_is_refused(self):
        array = _Array(destroyed=("tenant2",))
        message = _failure(_run(array, rename="tenant2", check_mode=True))
        assert "tenant2 already exists and is pending eradication" in message
        assert array.writes == []

    def test_rename_is_refused_before_other_options_are_applied(self):
        array = _Array(realms=("tenant1", "tenant2"), qos={"tenant1": "gold"})
        _failure(_run(array, rename="tenant2", qos_policy="silver"))
        assert array.writes == []
        assert array.qos_of("tenant1") == "gold"

    def test_rename_of_a_missing_realm_creates_it_with_the_new_name(self):
        array = _Array(realms=())
        assert _changed(_run(array, rename="tenant2", check_mode=True)) is True
        assert array.writes == []
        assert _changed(_run(array, rename="tenant2")) is True
        assert array.writes == [("create", "tenant2")]
        array.writes = []
        module = _run(array, rename="tenant2")
        assert _changed(module) is False
        assert array.writes == []
        assert _warnings(module) == []

    def test_missing_name_and_destroyed_new_name_is_refused(self):
        array = _Array(realms=(), destroyed=("tenant2",))
        message = _failure(_run(array, rename="tenant2"))
        assert "Realm tenant1 does not exist and realm tenant2 is destroyed" in message
        assert array.writes == []

    def test_rename_sends_the_name_the_array_keeps(self):
        array = _Array(realms=("Tenant1",))
        assert _changed(_run(array, name="TENANT1", rename="tenant2")) is True
        assert array.writes == [("rename", "Tenant1", "tenant2")]

    def test_recover_and_rename_in_one_run(self):
        array = _Array(realms=(), destroyed=("tenant1",))
        assert _changed(_run(array, rename="tenant2")) is True
        assert array.writes == [
            ("recover", "tenant1"),
            ("rename", "tenant1", "tenant2"),
        ]
        assert not array.is_destroyed("tenant2")
        array.writes = []
        assert _changed(_run(array, rename="tenant2")) is False
        assert array.writes == []

    def test_recover_and_rename_check_mode(self):
        array = _Array(realms=(), destroyed=("tenant1",))
        assert _changed(_run(array, rename="tenant2", check_mode=True)) is True
        assert array.writes == []


class TestPurefbRealmQos:
    """qos_policy"""

    def test_attach(self):
        array = _Array()
        assert _changed(_run(array, qos_policy="gold")) is True
        assert array.writes == [("attach", "tenant1", "gold")]
        module = _run(array, qos_policy="gold")
        assert _changed(module) is False
        module.blade.post_qos_policies_members.assert_not_called()

    def test_attach_check_mode(self):
        array = _Array()
        assert _changed(_run(array, qos_policy="gold", check_mode=True)) is True
        assert array.writes == []

    def test_switch_detaches_then_attaches(self):
        array = _Array(qos={"tenant1": "gold"})
        assert _changed(_run(array, qos_policy="silver")) is True
        assert array.writes == [
            ("detach", "tenant1", "gold"),
            ("attach", "tenant1", "silver"),
        ]
        assert array.qos_of("tenant1") == "silver"

    def test_omitted_leaves_the_policy_alone(self):
        array = _Array(qos={"tenant1": "gold"})
        module = _run(array)
        assert _changed(module) is False
        assert array.writes == []
        module.blade.get_qos_policies_members.assert_not_called()

    def test_empty_string_detaches(self):
        array = _Array(qos={"tenant1": "gold"})
        assert _changed(_run(array, qos_policy="", check_mode=True)) is True
        assert array.writes == []
        assert _changed(_run(array, qos_policy="")) is True
        assert array.writes == [("detach", "tenant1", "gold")]
        assert array.qos_of("tenant1") is None

    def test_empty_string_without_policy_is_noop(self):
        array = _Array()
        assert _changed(_run(array, qos_policy="")) is False
        assert array.writes == []

    def test_policy_in_other_case_is_noop(self):
        array = _Array(qos={"tenant1": "gold"})
        for check_mode in (True, False):
            module = _run(array, qos_policy="GOLD", check_mode=check_mode)
            assert _changed(module) is False
        assert array.writes == []

    def test_requests_carry_the_names_the_array_keeps(self):
        array = _Array(realms=("Tenant1",), qos={"Tenant1": "gold"})
        assert _changed(_run(array, name="TENANT1", qos_policy="SILVER")) is True
        assert array.writes == [
            ("detach", "Tenant1", "gold"),
            ("attach", "Tenant1", "silver"),
        ]

    def test_unknown_policy_fails_before_any_write(self):
        array = _Array(qos={"tenant1": "gold"})
        for check_mode in (True, False):
            module = _run(array, qos_policy="bronze", check_mode=check_mode)
            message = _failure(module)
            assert "QoS policy bronze was not found or is not visible" in message
        assert array.writes == []
        assert array.qos_of("tenant1") == "gold"

    def test_refused_policy_read_is_reported(self):
        array = _Array()
        array.fail["get_qos_policies"] = DENIED
        message = _failure(_run(array, qos_policy="gold"))
        assert "Failed to read QoS policy gold" in message
        assert DENIED in message
        assert array.writes == []

    def test_refused_membership_read_is_reported(self):
        array = _Array()
        array.fail["get_qos_policies_members"] = DENIED
        message = _failure(_run(array, qos_policy="gold"))
        assert "Failed to read the QoS policy of realm tenant1" in message
        assert DENIED in message
        assert array.writes == []

    def test_attach_failure_is_reported(self):
        array = _Array()
        array.fail["post_qos_policies_members"] = DENIED
        message = _failure(_run(array, qos_policy="gold"))
        assert "QoS policy assignment failed for realm tenant1" in message
        assert DENIED in message

    def test_detach_failure_is_reported(self):
        array = _Array(qos={"tenant1": "gold"})
        array.fail["delete_qos_policies_members"] = DENIED
        message = _failure(_run(array, qos_policy="silver"))
        assert "Existing QoS policy removal failed for realm tenant1" in message
        assert array.writes == [("detach", "tenant1", "gold")]

    def test_create_with_policy(self):
        array = _Array(realms=())
        assert _changed(_run(array, qos_policy="gold")) is True
        assert array.writes == [("create", "tenant1"), ("attach", "tenant1", "gold")]

    def test_create_with_unknown_policy_creates_nothing(self):
        array = _Array(realms=())
        _failure(_run(array, qos_policy="bronze"))
        assert array.writes == []

    def test_rename_with_another_policy(self):
        array = _Array(qos={"tenant1": "gold"})
        params = {"rename": "tenant2", "qos_policy": "silver"}
        assert _changed(_run(array, check_mode=True, **params)) is True
        assert array.writes == []
        assert _changed(_run(array, **params)) is True
        assert array.writes == [
            ("rename", "tenant1", "tenant2"),
            ("detach", "tenant2", "gold"),
            ("attach", "tenant2", "silver"),
        ]
        array.writes = []
        module = _run(array, **params)
        assert _changed(module) is False
        assert array.writes == []
        assert array.qos_of("tenant2") == "silver"
        assert _warnings(module) == []

    def test_already_renamed_realm_gets_the_policy_and_a_warning(self):
        array = _Array(realms=("tenant2",), qos={"tenant2": "gold"})
        params = {"rename": "tenant2", "qos_policy": "silver"}
        for check_mode in (True, False):
            module = _run(array, check_mode=check_mode, **params)
            assert _changed(module) is True
            warnings = _warnings(module)
            assert len(warnings) == 1
            assert (
                "Realm tenant1 does not exist. Realm tenant2 was taken" in warnings[0]
            )
        assert array.qos_of("tenant2") == "silver"

    def test_recover_with_policy_in_one_run(self):
        array = _Array(realms=(), destroyed=("tenant1",))
        assert _changed(_run(array, qos_policy="gold")) is True
        assert array.writes == [("recover", "tenant1"), ("attach", "tenant1", "gold")]
        array.writes = []
        assert _changed(_run(array, qos_policy="gold")) is False
        assert array.writes == []

    def test_recover_rename_and_policy_in_one_run(self):
        array = _Array(realms=(), destroyed=("tenant1",))
        params = {"rename": "tenant2", "qos_policy": "gold"}
        assert _changed(_run(array, **params)) is True
        assert array.writes == [
            ("recover", "tenant1"),
            ("rename", "tenant1", "tenant2"),
            ("attach", "tenant2", "gold"),
        ]
        array.writes = []
        assert _changed(_run(array, **params)) is False
        assert array.writes == []

    def test_destroy_detaches_the_policy_first(self):
        array = _Array(qos={"tenant1": "gold"})
        assert _changed(_run(array, state="absent")) is True
        assert array.writes == [("detach", "tenant1", "gold"), ("destroy", "tenant1")]
        assert array.is_destroyed("tenant1")

    def test_destroy_with_policy_check_mode(self):
        array = _Array(qos={"tenant1": "gold"})
        assert _changed(_run(array, state="absent", check_mode=True)) is True
        assert array.writes == []

    def test_destroy_and_eradicate_with_policy(self):
        array = _Array(qos={"tenant1": "gold"})
        assert _changed(_run(array, state="absent", eradicate=True)) is True
        assert array.name_of("tenant1") is None
        assert array.qos_of("tenant1") is None

    def test_refused_destroy_attaches_the_policy_again(self):
        array = _Array(qos={"tenant1": "gold"}, entities=("tenant1",))
        message = _failure(_run(array, state="absent"))
        assert CONTAINS in message
        assert "could not be attached again" not in message
        assert array.writes == [
            ("detach", "tenant1", "gold"),
            ("destroy", "tenant1"),
            ("attach", "tenant1", "gold"),
        ]
        assert array.qos_of("tenant1") == "gold"

    def test_refused_destroy_says_when_the_policy_stays_detached(self):
        array = _Array(qos={"tenant1": "gold"}, entities=("tenant1",))
        array.fail["post_qos_policies_members"] = DENIED
        message = _failure(_run(array, state="absent"))
        assert CONTAINS in message
        assert "QoS policy gold was detached from the realm" in message

    def test_destroy_with_refused_detach_is_reported(self):
        array = _Array(qos={"tenant1": "gold"})
        array.fail["delete_qos_policies_members"] = DENIED
        message = _failure(_run(array, state="absent"))
        assert "Existing QoS policy removal failed for realm tenant1" in message
        assert array.writes == [("detach", "tenant1", "gold")]
        assert not array.is_destroyed("tenant1")

    def test_qos_policy_needs_rest_2_20(self):
        array = _Array()
        message = _failure(_run(array, qos_policy="gold", api_version="2.19"))
        assert "qos_policy requires Purity//FB 4.6.3 (REST API 2.20)" in message
        assert array.writes == []

    def test_rest_2_19_manages_a_realm_without_qos_requests(self):
        array = _Array()
        module = _run(array, api_version="2.19")
        assert _changed(module) is False
        module.blade.get_qos_policies_members.assert_not_called()
        module = _run(array, state="absent", api_version="2.19")
        assert _changed(module) is True
        module.blade.get_qos_policies_members.assert_not_called()

    def test_realm_administrator_is_told_it_cannot_see_qos_policies(self):
        array = _Array(qos={"tenant1": "gold"})
        array.realm_admin = True
        for check_mode in (True, False):
            module = _run(array, qos_policy="gold", check_mode=check_mode)
            message = _failure(module)
            assert "not visible to a realm-scoped administrator" in message
        assert array.writes == []

    def test_realm_administrator_destroy_gets_the_answer_of_the_array(self):
        array = _Array(qos={"tenant1": "gold"})
        array.realm_admin = True
        message = _failure(_run(array, state="absent"))
        assert CONTAINS in message
        assert array.writes == [("destroy", "tenant1")]


class TestPurefbRealmDestroyGuards:
    """What still refers to a realm that is to be destroyed"""

    def test_resource_access_blocks_destroy(self):
        array = _Array(accesses=[("dns", "shared-dns", "tenant1")])
        for check_mode in (True, False):
            module = _run(array, state="absent", eradicate=True, check_mode=check_mode)
            message = _failure(module)
            assert "Realm tenant1 cannot be destroyed" in message
            assert "the resource access of dns shared-dns" in message
        assert array.writes == []

    def test_management_access_policy_rule_blocks_destroy(self):
        array = _Array(rules=[("tenant-admins", "Tenant1")])
        for check_mode in (True, False):
            module = _run(array, state="absent", check_mode=check_mode)
            message = _failure(module)
            assert "a rule of management access policy tenant-admins" in message
        assert array.writes == []

    def test_everything_found_is_named(self):
        array = _Array(
            accesses=[("dns", "shared-dns", "tenant1")],
            rules=[("tenant-admins", "tenant1")],
            qos={"tenant1": "gold"},
        )
        message = _failure(_run(array, state="absent"))
        assert (
            "the resource access of dns shared-dns and a rule of management "
            "access policy tenant-admins"
        ) in message
        assert array.writes == []
        assert array.qos_of("tenant1") == "gold"

    def test_what_refers_to_another_realm_does_not_block(self):
        array = _Array(
            realms=("tenant1", "tenant2"),
            accesses=[("dns", "shared-dns", "tenant2")],
            rules=[("tenant-admins", "tenant2")],
        )
        assert _changed(_run(array, state="absent")) is True
        assert array.writes == [("destroy", "tenant1")]

    def test_refused_reads_leave_the_answer_to_the_array(self):
        array = _Array(accesses=[("dns", "shared-dns", "tenant1")])
        array.fail["get_resource_accesses"] = DENIED
        array.fail["get_management_access_policies"] = DENIED
        assert _changed(_run(array, state="absent", check_mode=True)) is True
        message = _failure(_run(array, state="absent"))
        assert "Deleting realm tenant1 failed" in message
        assert CONTAINS in message

    def test_destroyed_realm_is_eradicated_without_these_reads(self):
        array = _Array(realms=(), destroyed=("tenant1",))
        module = _run(array, state="absent", eradicate=True)
        assert _changed(module) is True
        module.blade.get_resource_accesses.assert_not_called()
        module.blade.get_management_access_policies.assert_not_called()


class TestPurefbRealmDefaultObjectServer:
    """default_object_server"""

    @staticmethod
    def _array(**kwargs):
        kwargs.setdefault("servers", ("tenant1::s3srv", "tenant1::other"))
        return _Array(**kwargs)

    def test_set_qualifies_bare_name(self):
        array = self._array()
        module = _run(array, default_object_server="s3srv")
        assert _changed(module) is True
        assert array.writes == [("default", "tenant1", "tenant1::s3srv")]
        module.blade.patch_realms_defaults.assert_called_once_with(
            realm_names=["tenant1"],
            default_realm_configuration={
                "object_store": [{"server": {"name": "tenant1::s3srv"}}]
            },
        )

    def test_already_set_is_noop(self):
        array = self._array(defaults={"tenant1": "tenant1::s3srv"})
        for value in ("s3srv", "tenant1::s3srv"):
            assert _changed(_run(array, default_object_server=value)) is False
        assert array.writes == []

    def test_other_letter_case_is_noop(self):
        array = self._array(defaults={"tenant1": "tenant1::s3srv"})
        for name, value in (
            ("TENANT1", "s3srv"),
            ("tenant1", "TENANT1::s3srv"),
            ("tenant1", "S3SRV"),
        ):
            module = _run(array, name=name, default_object_server=value)
            assert _changed(module) is False
        assert array.writes == []

    def test_replace(self):
        array = self._array(defaults={"tenant1": "tenant1::s3srv"})
        assert _changed(_run(array, default_object_server="other")) is True
        assert array.default_of("tenant1") == "tenant1::other"

    def test_clear_sends_empty_object_store(self):
        array = self._array(defaults={"tenant1": "tenant1::s3srv"})
        module = _run(array, default_object_server="")
        assert _changed(module) is True
        module.blade.patch_realms_defaults.assert_called_once_with(
            realm_names=["tenant1"],
            default_realm_configuration={"object_store": []},
        )
        assert array.default_of("tenant1") is None

    def test_clear_when_already_clear_is_noop(self):
        array = self._array()
        assert _changed(_run(array, default_object_server="")) is False
        assert array.writes == []

    def test_check_mode_reports_change_without_patch(self):
        array = self._array()
        module = _run(array, default_object_server="s3srv", check_mode=True)
        assert _changed(module) is True
        assert array.writes == []

    def test_missing_server_fails_before_patch(self):
        array = self._array()
        for check_mode in (True, False):
            module = _run(array, default_object_server="nosrv", check_mode=check_mode)
            message = _failure(module)
            assert message == "Server tenant1::nosrv does not exist in realm tenant1."
        assert array.writes == []

    def test_refused_server_read_is_reported(self):
        array = self._array()
        array.fail["get_servers"] = DENIED
        message = _failure(_run(array, default_object_server="s3srv"))
        assert "Failed to read server tenant1::s3srv" in message
        assert DENIED in message

    def test_server_of_another_realm_is_refused(self):
        array = self._array(realms=("tenant1", "tenant2"), servers=("tenant2::s3srv",))
        for check_mode in (True, False):
            module = _run(
                array, default_object_server="tenant2::s3srv", check_mode=check_mode
            )
            message = _failure(module)
            assert "tenant2::s3srv is not in realm tenant1" in message
        assert array.writes == []
        module.blade.get_servers.assert_not_called()

    def test_requires_rest_2_20(self):
        array = self._array()
        module = _run(array, default_object_server="s3srv", api_version="2.19")
        assert "default_object_server requires Purity//FB 4.6.3" in _failure(module)
        assert array.writes == []

    def test_patch_failure_is_reported(self):
        array = self._array()
        array.fail["patch_realms_defaults"] = DENIED
        message = _failure(_run(array, default_object_server="s3srv"))
        assert "Setting default object store server for realm tenant1" in message
        assert DENIED in message

    def test_defaults_read_failure_is_reported(self):
        array = self._array()
        array.fail["get_realms_defaults"] = DENIED
        message = _failure(_run(array, default_object_server="s3srv"))
        assert "Failed to read defaults for realm tenant1" in message
        assert array.writes == []

    def test_create_with_default_server_fails_before_post(self):
        array = self._array(realms=(), servers=())
        for check_mode in (True, False):
            module = _run(array, default_object_server="s3srv", check_mode=check_mode)
            assert "does not exist in realm tenant1" in _failure(module)
        assert array.writes == []

    def test_recover_with_default_server_fails_before_recover(self):
        array = self._array(realms=(), destroyed=("tenant1",), servers=())
        for check_mode in (True, False):
            module = _run(array, default_object_server="s3srv", check_mode=check_mode)
            assert "does not exist in realm tenant1" in _failure(module)
        assert array.writes == []

    def test_rename_sets_the_default_under_the_new_name(self):
        array = self._array()
        params = {"rename": "tenant2", "default_object_server": "s3srv"}
        assert _changed(_run(array, check_mode=True, **params)) is True
        assert array.writes == []
        assert _changed(_run(array, **params)) is True
        assert array.writes == [
            ("rename", "tenant1", "tenant2"),
            ("default", "tenant2", "tenant2::s3srv"),
        ]
        array.writes = []
        for value in ("s3srv", "tenant1::s3srv", "tenant2::s3srv"):
            params["default_object_server"] = value
            module = _run(array, **params)
            assert _changed(module) is False
            assert _warnings(module) == []
        assert array.writes == []

    def test_rename_accepts_server_qualified_with_old_name(self):
        array = self._array()
        params = {"rename": "tenant2", "default_object_server": "tenant1::s3srv"}
        assert _changed(_run(array, **params)) is True
        assert array.default_of("tenant2") == "tenant2::s3srv"

    def test_rename_refuses_missing_server_before_the_rename(self):
        array = self._array()
        params = {"rename": "tenant2", "default_object_server": "nosrv"}
        for check_mode in (True, False):
            module = _run(array, check_mode=check_mode, **params)
            assert "Server tenant1::nosrv does not exist" in _failure(module)
        assert array.writes == []

    def test_already_renamed_realm_gets_the_default_and_a_warning(self):
        array = self._array(
            realms=("tenant2",),
            servers=("tenant2::s3srv",),
            defaults={"tenant2": "tenant2::s3srv"},
        )
        params = {"rename": "tenant2", "default_object_server": ""}
        for check_mode in (True, False):
            module = _run(array, check_mode=check_mode, **params)
            assert _changed(module) is True
            assert len(_warnings(module)) == 1
        assert array.default_of("tenant2") is None
        module = _run(array, **params)
        assert _changed(module) is False
        assert _warnings(module) == []

    def test_absent_ignores_default_object_server(self):
        array = _Array()
        module = _run(array, state="absent", default_object_server="s3srv")
        assert _changed(module) is True
        assert array.writes == [("destroy", "tenant1")]


class TestPurefbRealmDefaultInboundTlsPolicy:
    """default_inbound_tls_policy"""

    @staticmethod
    def _array(**kwargs):
        kwargs.setdefault("tls_policies", ("tenant1::strict", "tenant1::legacy"))
        return _Array(**kwargs)

    def test_set_qualifies_bare_name(self):
        array = self._array()
        module = _run(array, default_inbound_tls_policy="strict")
        assert _changed(module) is True
        module.blade.patch_realms.assert_called_once_with(
            names=["tenant1"],
            realm={"default_inbound_tls_policy": {"name": "tenant1::strict"}},
        )
        assert array.tls_of("tenant1") == "tenant1::strict"

    def test_already_set_is_noop(self):
        array = self._array(tls={"tenant1": "tenant1::strict"})
        for name, value in (
            ("tenant1", "strict"),
            ("tenant1", "tenant1::strict"),
            ("TENANT1", "STRICT"),
            ("tenant1", "TENANT1::strict"),
        ):
            module = _run(array, name=name, default_inbound_tls_policy=value)
            assert _changed(module) is False
        assert array.writes == []

    def test_replace(self):
        array = self._array(tls={"tenant1": "tenant1::strict"})
        assert _changed(_run(array, default_inbound_tls_policy="legacy")) is True
        assert array.writes == [("tls", "tenant1", "tenant1::legacy")]

    def test_clear_sends_an_empty_name(self):
        array = self._array(tls={"tenant1": "tenant1::strict"})
        module = _run(array, default_inbound_tls_policy="")
        assert _changed(module) is True
        module.blade.patch_realms.assert_called_once_with(
            names=["tenant1"], realm={"default_inbound_tls_policy": {"name": ""}}
        )
        assert array.tls_of("tenant1") is None

    def test_clear_when_already_clear_is_noop(self):
        array = self._array()
        assert _changed(_run(array, default_inbound_tls_policy="")) is False
        assert array.writes == []

    def test_check_mode_reports_change_without_patch(self):
        array = self._array(tls={"tenant1": "tenant1::strict"})
        for value in ("legacy", ""):
            module = _run(array, default_inbound_tls_policy=value, check_mode=True)
            assert _changed(module) is True
        assert array.writes == []

    def test_missing_policy_fails_before_patch(self):
        array = self._array()
        for check_mode in (True, False):
            module = _run(
                array, default_inbound_tls_policy="nope", check_mode=check_mode
            )
            message = _failure(module)
            assert (
                message == "TLS policy tenant1::nope does not exist in realm tenant1."
            )
        assert array.writes == []

    def test_policy_of_another_realm_is_refused(self):
        array = self._array(tls_policies=("tenant2::strict",))
        module = _run(array, default_inbound_tls_policy="tenant2::strict")
        assert "tenant2::strict is not in realm tenant1" in _failure(module)
        assert array.writes == []

    def test_patch_failure_is_reported(self):
        array = self._array()
        array.realm_admin = True
        message = _failure(_run(array, default_inbound_tls_policy="strict"))
        assert "Setting default inbound TLS policy for realm tenant1" in message
        assert DENIED in message

    def test_create_with_policy_fails_before_post(self):
        array = self._array(realms=(), tls_policies=())
        module = _run(array, default_inbound_tls_policy="strict")
        assert "does not exist in realm tenant1" in _failure(module)
        assert array.writes == []

    def test_absent_ignores_the_option(self):
        array = _Array()
        module = _run(array, state="absent", default_inbound_tls_policy="strict")
        assert _changed(module) is True
        assert array.writes == [("destroy", "tenant1")]

    def test_rename_carries_the_policy_over(self):
        array = self._array(tls={"tenant1": "tenant1::strict"})
        assert _changed(_run(array, rename="tenant2", check_mode=True)) is True
        assert array.writes == []
        assert _changed(_run(array, rename="tenant2")) is True
        assert array.writes == [
            ("tls", "tenant1", ""),
            ("rename", "tenant1", "tenant2"),
            ("tls", "tenant2", "tenant2::strict"),
        ]
        assert array.tls_of("tenant2") == "tenant2::strict"
        array.writes = []
        assert _changed(_run(array, rename="tenant2")) is False
        assert array.writes == []

    def test_rename_with_another_policy(self):
        array = self._array(tls={"tenant1": "tenant1::strict"})
        params = {"rename": "tenant2", "default_inbound_tls_policy": "legacy"}
        assert _changed(_run(array, **params)) is True
        assert array.writes == [
            ("tls", "tenant1", ""),
            ("rename", "tenant1", "tenant2"),
            ("tls", "tenant2", "tenant2::legacy"),
        ]
        array.writes = []
        for value in ("legacy", "tenant1::legacy", "tenant2::legacy"):
            params["default_inbound_tls_policy"] = value
            assert _changed(_run(array, **params)) is False
        assert array.writes == []

    def test_rename_with_clear(self):
        array = self._array(tls={"tenant1": "tenant1::strict"})
        params = {"rename": "tenant2", "default_inbound_tls_policy": ""}
        assert _changed(_run(array, **params)) is True
        assert array.writes == [
            ("tls", "tenant1", ""),
            ("rename", "tenant1", "tenant2"),
        ]
        assert array.tls_of("tenant2") is None

    def test_rename_without_policy_sets_the_one_given(self):
        array = self._array()
        params = {"rename": "tenant2", "default_inbound_tls_policy": "strict"}
        assert _changed(_run(array, **params)) is True
        assert array.writes == [
            ("rename", "tenant1", "tenant2"),
            ("tls", "tenant2", "tenant2::strict"),
        ]

    def test_refused_rename_sets_the_policy_again(self):
        array = self._array(tls={"tenant1": "tenant1::strict"})
        array.fail["patch_realms.name"] = DENIED
        message = _failure(_run(array, rename="tenant2"))
        assert "Rename to tenant2 failed" in message
        assert "could not be set again" not in message
        assert array.writes == [
            ("tls", "tenant1", ""),
            ("rename", "tenant1", "tenant2"),
            ("tls", "tenant1", "tenant1::strict"),
        ]
        assert array.tls_of("tenant1") == "tenant1::strict"

    def test_refused_rename_says_when_the_policy_stays_cleared(self):
        array = self._array(tls={"tenant1": "tenant1::strict"})
        array.fail["patch_realms.name"] = DENIED
        array.fail["patch_realms.tls"] = [None, DENIED]
        message = _failure(_run(array, rename="tenant2"))
        assert "Rename to tenant2 failed" in message
        assert "tenant1::strict was cleared for the rename" in message

    def test_policy_that_cannot_be_set_after_the_rename_is_reported(self):
        array = self._array(tls={"tenant1": "tenant1::strict"})
        array.fail["patch_realms.tls"] = [None, DENIED]
        message = _failure(_run(array, rename="tenant2", qos_policy="gold"))
        assert "Realm tenant1 was renamed to tenant2" in message
        assert "could not be set to tenant2::strict" in message
        assert DENIED in message
        assert array.writes == [
            ("tls", "tenant1", ""),
            ("rename", "tenant1", "tenant2"),
            ("tls", "tenant2", "tenant2::strict"),
        ]

    def test_refused_clear_stops_the_rename(self):
        array = self._array(tls={"tenant1": "tenant1::strict"})
        array.realm_admin = True
        message = _failure(_run(array, rename="tenant2"))
        assert "Clearing default inbound TLS policy tenant1::strict" in message
        assert array.writes == [("tls", "tenant1", "")]

    def test_policy_kept_from_before_a_rename_cannot_be_changed(self):
        array = self._array(
            realms=("tenant2",),
            tls_policies=("tenant2::strict", "tenant2::legacy"),
            tls={"tenant2": "tenant1::strict"},
        )
        for value in ("legacy", ""):
            for check_mode in (True, False):
                module = _run(
                    array,
                    name="tenant2",
                    default_inbound_tls_policy=value,
                    check_mode=check_mode,
                )
                message = _failure(module)
                assert "Rename the realm back to tenant1 first" in message
        module = _run(
            array, name="tenant2", rename="tenant3", default_inbound_tls_policy=""
        )
        assert "Rename the realm back to tenant1 first" in _failure(module)
        assert array.writes == []

    def test_policy_kept_from_before_a_rename_is_noop_when_unchanged(self):
        array = self._array(
            realms=("tenant2",),
            tls_policies=("tenant2::strict",),
            tls={"tenant2": "tenant1::strict"},
        )
        for params in ({}, {"default_inbound_tls_policy": "strict"}):
            assert _changed(_run(array, name="tenant2", **params)) is False
        assert array.writes == []

    def test_rename_back_is_a_plain_rename(self):
        array = self._array(
            realms=("tenant2",),
            tls_policies=("tenant2::strict", "tenant2::legacy"),
            tls={"tenant2": "tenant1::strict"},
        )
        module = _run(
            array, name="tenant2", rename="tenant1", default_inbound_tls_policy="legacy"
        )
        assert _changed(module) is True
        assert array.writes == [
            ("rename", "tenant2", "tenant1"),
            ("tls", "tenant1", "tenant1::legacy"),
        ]
        assert array.tls_of("tenant1") == "tenant1::legacy"

    def test_rename_elsewhere_without_the_option_is_a_plain_rename(self):
        array = self._array(
            realms=("tenant2",),
            tls_policies=("tenant2::strict",),
            tls={"tenant2": "tenant1::strict"},
        )
        assert _changed(_run(array, name="tenant2", rename="tenant3")) is True
        assert array.writes == [("rename", "tenant2", "tenant3")]
