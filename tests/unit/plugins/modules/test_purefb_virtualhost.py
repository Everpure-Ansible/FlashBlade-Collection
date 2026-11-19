# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_virtualhost module."""

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
from plugins.modules.purefb_virtualhost import (
    main,
    _context_kwargs,
    _get_host,
)

MOD = "plugins.modules.purefb_virtualhost"
RESERVED = "s3.amazonaws.com"
DEFAULT_SERVER = "_array_server"
KNOWN_SERVERS = (
    DEFAULT_SERVER,
    "tenant_a",
    "tenant_b",
    "tenant_c",
    "tenant1::s3srv",
    "tenant1::s3srv2",
)


def _base_params(**overrides):
    params = {
        "name": "acme-s3",
        "state": "present",
        "hostname": None,
        "servers": None,
        "rename": None,
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


def _ref(name):
    """Stand-in for pypureclient Reference so bodies are comparable."""
    return {"name": name}


def _server_refs(servers):
    refs = []
    for srv in servers:
        ref = Mock()
        ref.name = srv
        refs.append(ref)
    return refs


def _vhost(name, hostname=None, servers=(DEFAULT_SERVER,)):
    """A virtual host as the array returns it, attached to servers."""
    vhost = Mock()
    vhost.name = name
    vhost.hostname = hostname if hostname is not None else name
    vhost.attached_servers = _server_refs(servers)
    return vhost


def _response(status_code=200, items=None, total=None):
    res = Mock()
    res.status_code = status_code
    res.items = items if items is not None else []
    if total is not None:
        res.total_item_count = total
    return res


def _realm_defaults(server):
    """A realms/defaults item; server None means no default is set."""
    defaults = Mock()
    defaults.object_store = []
    if server is not None:
        entry = Mock()
        entry.server.name = server
        defaults.object_store = [entry]
    return defaults


def _blade(existing=None, total=1, servers=KNOWN_SERVERS, realm_defaults=None):
    """A small stateful stand-in for the array.

    existing maps vhost name -> vhost object; unknown names return 400 (the
    array's behaviour for a names= filter on a missing object). A GET with no
    names returns the count for the MAX_HOST_COUNT check. POST, PATCH and
    DELETE change that state so that a later GET reads it back. servers are
    the server names GET /servers knows, realm_defaults maps a realm name to
    its default object store server (None for a realm without one).

    blade.quirks makes the array misbehave for the defence-in-depth tests:
    post_without_servers, hidden (names a GET cannot read), ignore_attach,
    detach_drops_all, fail_patch (callable on the PATCH body).
    """
    hosts = dict(existing or {})
    realm_defaults = realm_defaults or {}
    blade = Mock()
    blade.hosts = hosts
    blade.quirks = {}
    blade.get_fleets.return_value = _response(200, items=[])

    def _get(**kwargs):
        names = kwargs.get("names")
        if names is None:
            return _response(200, items=list(hosts.values()), total=total)
        vhost = hosts.get(names[0])
        if vhost is None or names[0] in blade.quirks.get("hidden", ()):
            return _response(400, items=[])
        return _response(200, items=[vhost])

    def _post(**kwargs):
        name = kwargs["names"][0]
        body = kwargs.get("object_store_virtual_host") or {}
        attached = [ref["name"] for ref in body.get("attached_servers", [])]
        if blade.quirks.get("post_without_servers"):
            attached = []
        hosts[name] = _vhost(name, hostname=body.get("hostname"), servers=attached)
        return _response(200)

    def _patch(**kwargs):
        name = kwargs["names"][0]
        body = kwargs["object_store_virtual_host"]
        fail_patch = blade.quirks.get("fail_patch")
        if fail_patch is not None and fail_patch(body):
            return _response(400)
        vhost = hosts[name]
        attached = [ref.name for ref in vhost.attached_servers]
        if not blade.quirks.get("ignore_attach"):
            attached += [ref["name"] for ref in body.get("add_attached_servers", [])]
        detach = [ref["name"] for ref in body.get("remove_attached_servers", [])]
        attached = [srv for srv in attached if srv not in detach]
        if detach and blade.quirks.get("detach_drops_all"):
            attached = []
        vhost.attached_servers = _server_refs(attached)
        if "hostname" in body:
            vhost.hostname = body["hostname"]
        if "name" in body:
            vhost.name = body["name"]
            hosts[body["name"]] = hosts.pop(name)
        return _response(200)

    def _delete(**kwargs):
        hosts.pop(kwargs["names"][0], None)
        return _response(200)

    def _get_servers(**kwargs):
        names = kwargs.get("names") or []
        if [srv for srv in names if srv not in servers]:
            return _response(400, items=[])
        return _response(200, items=_server_refs(names))

    def _get_realms_defaults(**kwargs):
        realm = kwargs["realm_names"][0]
        if realm not in realm_defaults:
            return _response(400, items=[])
        return _response(200, items=[_realm_defaults(realm_defaults[realm])])

    blade.get_object_store_virtual_hosts.side_effect = _get
    blade.post_object_store_virtual_hosts.side_effect = _post
    blade.patch_object_store_virtual_hosts.side_effect = _patch
    blade.delete_object_store_virtual_hosts.side_effect = _delete
    blade.get_servers.side_effect = _get_servers
    blade.get_realms_defaults.side_effect = _get_realms_defaults
    return blade


def _run(module, blade, api_version="2.30"):
    """Run main() with the module/blade mocks and the given REST version."""
    with patch(MOD + ".AnsibleModule", return_value=module), patch(
        MOD + ".get_system", return_value=blade
    ), patch(MOD + ".get_rest_api_version", return_value=api_version), patch(
        MOD + ".LooseVersion", RealLooseVersion
    ), patch(
        MOD + ".HAS_PYPURECLIENT", True
    ), patch(
        MOD + ".Reference", side_effect=_ref
    ), patch(
        MOD + ".ObjectStoreVirtualHost", side_effect=lambda **kw: kw
    ), patch(
        MOD + ".ObjectStoreVirtualHostPatch", side_effect=lambda **kw: kw
    ), patch(
        MOD + ".get_error_message", return_value="array error"
    ):
        try:
            main()
        except SystemExit:
            pass


def _changed(module):
    module.exit_json.assert_called_once()
    return module.exit_json.call_args[1]["changed"]


def _failure(module):
    """The message of the one and only fail_json; nothing may exit after it."""
    module.fail_json.assert_called_once()
    module.exit_json.assert_not_called()
    return module.fail_json.call_args[1]["msg"]


def _bodies(blade):
    """The bodies of the PATCH requests in the order they were sent."""
    return [
        call[1]["object_store_virtual_host"]
        for call in blade.patch_object_store_virtual_hosts.call_args_list
    ]


def _attached(blade, name):
    return sorted(ref.name for ref in blade.hosts[name].attached_servers)


def _no_writes(blade):
    blade.post_object_store_virtual_hosts.assert_not_called()
    blade.patch_object_store_virtual_hosts.assert_not_called()
    blade.delete_object_store_virtual_hosts.assert_not_called()


class TestPurefbVirtualhost:
    """Test cases for purefb_virtualhost module"""

    # ---------------- helper-function unit tests ----------------

    @patch(MOD + ".LooseVersion", RealLooseVersion)
    def test_context_kwargs_empty_without_context(self):
        module = Mock()
        module.params = {"context": ""}
        assert _context_kwargs(module, "2.30") == {}

    @patch(MOD + ".LooseVersion", RealLooseVersion)
    def test_context_kwargs_set_on_supported_version(self):
        module = Mock()
        module.params = {"context": "peer1"}
        assert _context_kwargs(module, "2.17") == {"context_names": ["peer1"]}

    @patch(MOD + ".LooseVersion", RealLooseVersion)
    def test_context_kwargs_ignored_below_fleet_version(self):
        module = Mock()
        module.params = {"context": "peer1"}
        assert _context_kwargs(module, "2.16") == {}

    def test_get_host_returns_item(self):
        vhost = _vhost("acme-s3")
        blade = Mock()
        blade.get_object_store_virtual_hosts.return_value = _response(200, [vhost])
        assert _get_host(blade, "acme-s3", {}) is vhost
        blade.get_object_store_virtual_hosts.assert_called_once_with(names=["acme-s3"])

    def test_get_host_returns_none_on_error(self):
        blade = Mock()
        blade.get_object_store_virtual_hosts.return_value = _response(400, [])
        assert _get_host(blade, "acme-s3", {}) is None

    def test_get_host_passes_context(self):
        blade = Mock()
        blade.get_object_store_virtual_hosts.return_value = _response(200, [])
        assert _get_host(blade, "acme-s3", {"context_names": ["peer1"]}) is None
        blade.get_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"], context_names=["peer1"]
        )

    # ---------------- create ----------------

    def test_create_bare_name_names_the_default_server(self):
        """No servers: the module names the default server in the POST itself"""
        module = _module()
        blade = _blade()
        _run(module, blade)
        blade.get_servers.assert_called_once_with(names=[DEFAULT_SERVER])
        blade.post_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"],
            object_store_virtual_host={"attached_servers": [_ref(DEFAULT_SERVER)]},
        )
        assert _changed(module) is True

    def test_create_bare_name_on_old_api(self):
        """REST 2.16 (no fleet context): the legacy POST by name still works"""
        module = _module()
        blade = _blade()
        _run(module, blade, api_version="2.16")
        blade.get_fleets.assert_not_called()
        blade.post_object_store_virtual_hosts.assert_called_once_with(names=["acme-s3"])
        assert _changed(module) is True

    def test_create_with_hostname_and_servers(self):
        module = _module(hostname="s3.acme.com", servers=["tenant_a", "tenant_b"])
        blade = _blade()
        _run(module, blade)
        blade.post_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"],
            object_store_virtual_host={
                "hostname": "s3.acme.com",
                "attached_servers": [_ref("tenant_a"), _ref("tenant_b")],
            },
        )
        assert _changed(module) is True

    def test_create_with_hostname_only(self):
        """servers omitted: the default server is named next to the hostname"""
        module = _module(hostname="s3.acme.com")
        blade = _blade()
        _run(module, blade)
        blade.post_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"],
            object_store_virtual_host={
                "hostname": "s3.acme.com",
                "attached_servers": [_ref(DEFAULT_SERVER)],
            },
        )
        assert _changed(module) is True

    def test_create_with_context(self):
        module = _module(hostname="s3.acme.com", context="peer1")
        blade = _blade()
        _run(module, blade)
        blade.get_object_store_virtual_hosts.assert_any_call(
            names=["acme-s3"], context_names=["peer1"]
        )
        blade.get_servers.assert_called_once_with(
            names=[DEFAULT_SERVER], context_names=["peer1"]
        )
        blade.post_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"],
            object_store_virtual_host={
                "hostname": "s3.acme.com",
                "attached_servers": [_ref(DEFAULT_SERVER)],
            },
            context_names=["peer1"],
        )

    def test_create_defaults_context_when_in_fleet(self):
        module = _module()
        blade = _blade()
        blade.get_fleets.return_value = _response(200, items=[Mock()])
        local = Mock()
        local.name = "local-array"
        blade.get_arrays.return_value = _response(200, items=[local])
        _run(module, blade)
        blade.post_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"],
            object_store_virtual_host={"attached_servers": [_ref(DEFAULT_SERVER)]},
            context_names=["local-array"],
        )

    def test_create_check_mode_skips_post(self):
        module = _module(check_mode=True, hostname="s3.acme.com")
        blade = _blade()
        _run(module, blade)
        blade.post_object_store_virtual_hosts.assert_not_called()
        assert _changed(module) is True

    def test_create_fails_at_max_host_count(self):
        module = _module()
        blade = _blade(total=10)
        _run(module, blade)
        blade.post_object_store_virtual_hosts.assert_not_called()
        module.fail_json.assert_called_once()
        assert "Maximum" in module.fail_json.call_args[1]["msg"]

    def test_create_api_error_fails(self):
        module = _module(hostname="s3.acme.com")
        blade = _blade()
        blade.post_object_store_virtual_hosts.side_effect = None
        blade.post_object_store_virtual_hosts.return_value = _response(400)
        _run(module, blade)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to add" in msg and "array error" in msg

    # ---------------- version gate ----------------

    def test_hostname_below_2_20_fails(self):
        module = _module(hostname="s3.acme.com")
        blade = _blade()
        _run(module, blade, api_version="2.19")
        module.fail_json.assert_called_once()
        assert "2.20" in module.fail_json.call_args[1]["msg"]
        blade.get_object_store_virtual_hosts.assert_not_called()

    def test_servers_below_2_20_fails(self):
        module = _module(servers=["tenant_a"])
        blade = _blade()
        _run(module, blade, api_version="2.19")
        module.fail_json.assert_called_once()
        assert "2.20" in module.fail_json.call_args[1]["msg"]

    def test_rename_below_2_20_fails(self):
        module = _module(rename="acme-object")
        blade = _blade()
        _run(module, blade, api_version="2.19")
        module.fail_json.assert_called_once()
        assert "2.20" in module.fail_json.call_args[1]["msg"]

    def test_sdk_missing_fails(self):
        module = _module()
        with patch(MOD + ".AnsibleModule", return_value=module), patch(
            MOD + ".HAS_PYPURECLIENT", False
        ), patch(MOD + ".get_system") as mock_get_system:
            try:
                main()
            except SystemExit:
                pass
        module.fail_json.assert_called_once()
        assert "py-pure-client" in module.fail_json.call_args[1]["msg"]
        mock_get_system.assert_not_called()

    # ---------------- update: hostname ----------------

    def test_update_hostname_changed(self):
        module = _module(hostname="s3.acme.com")
        blade = _blade({"acme-s3": _vhost("acme-s3", hostname="acme-s3")})
        _run(module, blade)
        blade.patch_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"], object_store_virtual_host={"hostname": "s3.acme.com"}
        )
        assert _changed(module) is True

    def test_update_hostname_unchanged_is_noop(self):
        module = _module(hostname="s3.acme.com")
        blade = _blade({"acme-s3": _vhost("acme-s3", hostname="s3.acme.com")})
        _run(module, blade)
        blade.patch_object_store_virtual_hosts.assert_not_called()
        blade.post_object_store_virtual_hosts.assert_not_called()
        assert _changed(module) is False

    def test_update_hostname_falls_back_to_name_pre_2_20_shape(self):
        """An object without a hostname attribute compares against its name"""
        vhost = Mock(spec=["name", "attached_servers"])
        vhost.name = "acme-s3"
        vhost.attached_servers = _server_refs([DEFAULT_SERVER])
        module = _module(hostname="acme-s3")
        blade = _blade({"acme-s3": vhost})
        _run(module, blade)
        blade.patch_object_store_virtual_hosts.assert_not_called()
        assert _changed(module) is False

    def test_update_hostname_check_mode(self):
        module = _module(check_mode=True, hostname="s3.acme.com")
        blade = _blade({"acme-s3": _vhost("acme-s3")})
        _run(module, blade)
        blade.patch_object_store_virtual_hosts.assert_not_called()
        assert _changed(module) is True

    def test_update_hostname_api_error_fails(self):
        module = _module(hostname="s3.acme.com")
        blade = _blade({"acme-s3": _vhost("acme-s3")})
        blade.quirks["fail_patch"] = lambda body: True
        _run(module, blade)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "set hostname" in msg and "array error" in msg

    # ---------------- update: servers ----------------

    def test_update_servers_add_only(self):
        module = _module(servers=["_array_server", "tenant_a"])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["_array_server"])})
        _run(module, blade)
        blade.patch_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"],
            object_store_virtual_host={"add_attached_servers": [_ref("tenant_a")]},
        )
        assert _changed(module) is True

    def test_update_servers_same_set_is_noop(self):
        """Order does not matter; same set means no PATCH"""
        module = _module(servers=["tenant_b", "tenant_a"])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["tenant_a", "tenant_b"])})
        _run(module, blade)
        blade.patch_object_store_virtual_hosts.assert_not_called()
        assert _changed(module) is False

    def test_update_servers_omitted_leaves_servers_alone(self):
        module = _module(hostname="acme-s3")
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["tenant_a"])})
        _run(module, blade)
        blade.patch_object_store_virtual_hosts.assert_not_called()
        assert _changed(module) is False

    def test_update_servers_wildcard_is_skipped_with_warning(self):
        """A '*' attachment is a pseudo-server and must never be reconciled"""
        module = _module(name="acme-s3", servers=["tenant_a"])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["*"])})
        _run(module, blade)
        blade.patch_object_store_virtual_hosts.assert_not_called()
        module.warn.assert_called_once()
        assert "*" in module.warn.call_args[0][0]
        assert _changed(module) is False

    def test_update_servers_check_mode(self):
        module = _module(check_mode=True, servers=["tenant_a"])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["_array_server"])})
        _run(module, blade)
        blade.patch_object_store_virtual_hosts.assert_not_called()
        assert _changed(module) is True

    def test_update_servers_api_error_fails(self):
        module = _module(servers=["tenant_a"])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=[])})
        blade.quirks["fail_patch"] = lambda body: True
        _run(module, blade)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "attached servers" in msg and "array error" in msg

    # ---------------- update: rename ----------------

    def test_rename_patches_name_last(self):
        module = _module(hostname="s3.acme.com", rename="acme-object")
        blade = _blade({"acme-s3": _vhost("acme-s3", hostname="acme-s3")})
        _run(module, blade)
        calls = blade.patch_object_store_virtual_hosts.call_args_list
        assert len(calls) == 2
        assert calls[0][1]["object_store_virtual_host"] == {"hostname": "s3.acme.com"}
        assert calls[1] == (
            (),
            {
                "names": ["acme-s3"],
                "object_store_virtual_host": {"name": "acme-object"},
            },
        )
        assert _changed(module) is True

    def test_rename_only(self):
        module = _module(rename="acme-object")
        blade = _blade({"acme-s3": _vhost("acme-s3")})
        _run(module, blade)
        blade.patch_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"], object_store_virtual_host={"name": "acme-object"}
        )
        assert _changed(module) is True

    def test_rename_to_same_name_is_noop(self):
        module = _module(rename="acme-s3")
        blade = _blade({"acme-s3": _vhost("acme-s3")})
        _run(module, blade)
        blade.patch_object_store_virtual_hosts.assert_not_called()
        assert _changed(module) is False

    def test_rename_already_done_is_noop(self):
        """Second run: name is gone, rename target exists -> nothing to do"""
        module = _module(rename="acme-object")
        blade = _blade({"acme-object": _vhost("acme-object")})
        _run(module, blade)
        blade.post_object_store_virtual_hosts.assert_not_called()
        blade.patch_object_store_virtual_hosts.assert_not_called()
        assert _changed(module) is False

    def test_rename_already_done_reconciles_renamed_host(self):
        """Second run with a new hostname: the renamed host is updated in place"""
        module = _module(
            hostname="s3.acme.com", servers=["tenant_a"], rename="acme-object"
        )
        blade = _blade(
            {
                "acme-object": _vhost(
                    "acme-object", hostname="acme-object", servers=["tenant_a"]
                )
            }
        )
        _run(module, blade)
        blade.post_object_store_virtual_hosts.assert_not_called()
        blade.patch_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-object"],
            object_store_virtual_host={"hostname": "s3.acme.com"},
        )
        assert _changed(module) is True

    def test_rename_with_neither_name_creates_source(self):
        """Neither name exists: create name as usual, rename happens next run"""
        module = _module(rename="acme-object")
        blade = _blade()
        _run(module, blade)
        blade.post_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"],
            object_store_virtual_host={"attached_servers": [_ref(DEFAULT_SERVER)]},
        )
        assert _changed(module) is True

    def test_rename_check_mode(self):
        module = _module(check_mode=True, rename="acme-object")
        blade = _blade({"acme-s3": _vhost("acme-s3")})
        _run(module, blade)
        blade.patch_object_store_virtual_hosts.assert_not_called()
        assert _changed(module) is True

    def test_rename_api_error_fails(self):
        module = _module(rename="acme-object")
        blade = _blade({"acme-s3": _vhost("acme-s3")})
        blade.quirks["fail_patch"] = lambda body: True
        _run(module, blade)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "rename to acme-object" in msg and "array error" in msg

    def test_update_with_context(self):
        module = _module(servers=["tenant_a"], context="peer1")
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=[])})
        _run(module, blade)
        blade.patch_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"],
            object_store_virtual_host={"add_attached_servers": [_ref("tenant_a")]},
            context_names=["peer1"],
        )

    # ---------------- reserved host ----------------

    def test_reserved_host_update_warns_and_is_noop(self):
        module = _module(name=RESERVED, servers=["tenant_a"])
        blade = _blade({RESERVED: _vhost(RESERVED, servers=["*"])})
        _run(module, blade)
        blade.patch_object_store_virtual_hosts.assert_not_called()
        module.warn.assert_called_once()
        assert "reserved" in module.warn.call_args[0][0]
        assert _changed(module) is False

    def test_reserved_host_hostname_change_warns_and_is_noop(self):
        module = _module(name=RESERVED, hostname="s3.acme.com")
        blade = _blade({RESERVED: _vhost(RESERVED, servers=["*"])})
        _run(module, blade)
        blade.patch_object_store_virtual_hosts.assert_not_called()
        module.warn.assert_called_once()
        assert "reserved" in module.warn.call_args[0][0]
        assert _changed(module) is False

    def test_reserved_host_rename_warns_and_is_noop(self):
        module = _module(name=RESERVED, rename="acme-object")
        blade = _blade({RESERVED: _vhost(RESERVED, servers=["*"])})
        _run(module, blade)
        blade.patch_object_store_virtual_hosts.assert_not_called()
        module.warn.assert_called_once()
        assert "reserved" in module.warn.call_args[0][0]
        assert _changed(module) is False

    def test_reserved_host_present_without_changes_is_silent(self):
        module = _module(name=RESERVED)
        blade = _blade({RESERVED: _vhost(RESERVED, servers=["*"])})
        _run(module, blade)
        module.warn.assert_not_called()
        assert _changed(module) is False

    def test_reserved_host_delete_warns_and_is_noop(self):
        module = _module(name=RESERVED, state="absent")
        blade = _blade({RESERVED: _vhost(RESERVED, servers=["*"])})
        _run(module, blade)
        blade.delete_object_store_virtual_hosts.assert_not_called()
        module.warn.assert_called_once()
        assert _changed(module) is False

    def test_reserved_host_empty_servers_keeps_its_warning(self):
        """The reserved host is never modified, so it keeps its own handling"""
        module = _module(name=RESERVED, servers=[])
        blade = _blade({RESERVED: _vhost(RESERVED, servers=["*"])})
        _run(module, blade)
        _no_writes(blade)
        module.warn.assert_called_once()
        assert "reserved" in module.warn.call_args[0][0]
        assert _changed(module) is False

    # ---------------- delete ----------------

    def test_delete_existing(self):
        module = _module(state="absent")
        blade = _blade({"acme-s3": _vhost("acme-s3")})
        _run(module, blade)
        blade.delete_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"]
        )
        assert _changed(module) is True

    def test_delete_with_context(self):
        module = _module(state="absent", context="peer1")
        blade = _blade({"acme-s3": _vhost("acme-s3")})
        _run(module, blade)
        blade.delete_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"], context_names=["peer1"]
        )

    def test_delete_missing_is_noop(self):
        module = _module(state="absent")
        blade = _blade()
        _run(module, blade)
        blade.delete_object_store_virtual_hosts.assert_not_called()
        assert _changed(module) is False

    def test_delete_check_mode(self):
        module = _module(check_mode=True, state="absent")
        blade = _blade({"acme-s3": _vhost("acme-s3")})
        _run(module, blade)
        blade.delete_object_store_virtual_hosts.assert_not_called()
        assert _changed(module) is True

    def test_delete_api_error_fails(self):
        module = _module(state="absent")
        blade = _blade({"acme-s3": _vhost("acme-s3")})
        blade.delete_object_store_virtual_hosts.side_effect = None
        blade.delete_object_store_virtual_hosts.return_value = _response(400)
        _run(module, blade)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to delete" in msg and "array error" in msg

    def test_delete_serverless_host_is_allowed(self):
        """state=absent is the way out for a host without an attached server"""
        module = _module(state="absent", servers=[])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=[])})
        _run(module, blade)
        blade.delete_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"]
        )
        assert _changed(module) is True


class TestAttachedServerGuardCreate:
    """A virtual host is never created without an attached server"""

    def test_empty_servers_refused(self):
        module = _module(hostname="s3.acme.com", servers=[])
        blade = _blade()
        _run(module, blade)
        msg = _failure(module)
        assert "empty list" in msg and "at least one object store server" in msg
        assert "state=absent" in msg
        _no_writes(blade)

    def test_empty_servers_refused_in_check_mode(self):
        module = _module(check_mode=True, servers=[])
        blade = _blade()
        _run(module, blade)
        assert "empty list" in _failure(module)
        _no_writes(blade)

    def test_blank_server_name_refused(self):
        module = _module(servers=["tenant_a", " "])
        blade = _blade()
        _run(module, blade)
        assert "empty server name" in _failure(module)
        _no_writes(blade)

    def test_unknown_server_refused_before_the_post(self):
        module = _module(servers=["tenant_a", "no_such_server"])
        blade = _blade()
        _run(module, blade)
        msg = _failure(module)
        assert "was not created" in msg and "no_such_server" in msg
        blade.get_servers.assert_called_once_with(names=["tenant_a", "no_such_server"])
        _no_writes(blade)

    def test_unknown_server_refused_in_check_mode(self):
        module = _module(check_mode=True, servers=["no_such_server"])
        blade = _blade()
        _run(module, blade)
        assert "was not created" in _failure(module)
        _no_writes(blade)

    def test_server_lookup_returning_too_few_refused(self):
        """A 200 that does not list every requested server is not trusted"""
        module = _module(servers=["tenant_a", "tenant_b"])
        blade = _blade()
        blade.get_servers.side_effect = None
        blade.get_servers.return_value = _response(200, _server_refs(["tenant_a"]))
        _run(module, blade)
        assert "could not all be found" in _failure(module)
        _no_writes(blade)

    def test_array_default_server_missing_refused(self):
        module = _module(hostname="s3.acme.com")
        blade = _blade(servers=("tenant_a",))
        _run(module, blade)
        msg = _failure(module)
        assert DEFAULT_SERVER in msg and "Pass servers" in msg
        _no_writes(blade)

    def test_array_default_server_missing_refused_in_check_mode(self):
        module = _module(check_mode=True)
        blade = _blade(servers=())
        _run(module, blade)
        assert "Pass servers" in _failure(module)
        _no_writes(blade)

    def test_realm_without_default_server_refused(self):
        """The array would create this host with nothing attached"""
        module = _module(name="tenant1::acme-s3", hostname="s3.acme.com")
        blade = _blade(realm_defaults={"tenant1": None})
        _run(module, blade)
        msg = _failure(module)
        assert "realm tenant1 has no default object store server" in msg
        assert "Pass servers" in msg and "default_object_server" in msg
        blade.get_realms_defaults.assert_called_once_with(realm_names=["tenant1"])
        _no_writes(blade)

    def test_realm_without_default_server_refused_in_check_mode(self):
        module = _module(
            check_mode=True, name="tenant1::acme-s3", hostname="s3.acme.com"
        )
        blade = _blade(realm_defaults={"tenant1": None})
        _run(module, blade)
        assert "has no default object store server" in _failure(module)
        _no_writes(blade)

    def test_realm_without_defaults_entry_refused(self):
        module = _module(name="tenant1::acme-s3", hostname="s3.acme.com")
        blade = _blade()
        blade.get_realms_defaults.side_effect = None
        blade.get_realms_defaults.return_value = _response(200, items=[])
        _run(module, blade)
        assert "has no default object store server" in _failure(module)
        _no_writes(blade)

    def test_realm_defaults_unreadable_refused(self):
        module = _module(name="nosuchrealm::acme-s3", hostname="s3.acme.com")
        blade = _blade()
        _run(module, blade)
        msg = _failure(module)
        assert "could not be read" in msg and "array error" in msg
        _no_writes(blade)

    def test_realm_default_server_not_found_refused(self):
        module = _module(name="tenant1::acme-s3", hostname="s3.acme.com")
        blade = _blade(realm_defaults={"tenant1": "tenant1::gone"})
        _run(module, blade)
        msg = _failure(module)
        assert "tenant1::gone was not found" in msg
        _no_writes(blade)

    def test_realm_default_server_is_named_in_the_post(self):
        module = _module(name="tenant1::acme-s3", hostname="s3.acme.com")
        blade = _blade(realm_defaults={"tenant1": "tenant1::s3srv"})
        _run(module, blade)
        blade.post_object_store_virtual_hosts.assert_called_once_with(
            names=["tenant1::acme-s3"],
            object_store_virtual_host={
                "hostname": "s3.acme.com",
                "attached_servers": [_ref("tenant1::s3srv")],
            },
        )
        assert _changed(module) is True
        assert _attached(blade, "tenant1::acme-s3") == ["tenant1::s3srv"]

    def test_realm_default_lookup_in_check_mode_reports_changed(self):
        module = _module(
            check_mode=True, name="tenant1::acme-s3", hostname="s3.acme.com"
        )
        blade = _blade(realm_defaults={"tenant1": "tenant1::s3srv"})
        _run(module, blade)
        blade.get_realms_defaults.assert_called_once_with(realm_names=["tenant1"])
        _no_writes(blade)
        assert _changed(module) is True

    def test_realm_explicit_servers_need_no_default(self):
        module = _module(
            name="tenant1::acme-s3", hostname="s3.acme.com", servers=["tenant1::s3srv2"]
        )
        blade = _blade(realm_defaults={"tenant1": None})
        _run(module, blade)
        blade.get_realms_defaults.assert_not_called()
        blade.get_servers.assert_called_once_with(names=["tenant1::s3srv2"])
        assert _changed(module) is True
        assert _attached(blade, "tenant1::acme-s3") == ["tenant1::s3srv2"]

    def test_default_lookups_use_the_context(self):
        module = _module(
            name="tenant1::acme-s3", hostname="s3.acme.com", context="peer1"
        )
        blade = _blade(realm_defaults={"tenant1": "tenant1::s3srv"})
        _run(module, blade)
        blade.get_realms_defaults.assert_called_once_with(
            realm_names=["tenant1"], context_names=["peer1"]
        )
        blade.get_servers.assert_called_once_with(
            names=["tenant1::s3srv"], context_names=["peer1"]
        )
        assert _changed(module) is True

    def test_empty_request_refused_without_the_parameter_check(self):
        """Second line of defence: no POST is built without a server to attach"""
        module = _module(servers=[])
        blade = _blade()
        with patch(MOD + "._validate_servers"):
            _run(module, blade)
        msg = _failure(module)
        assert "was not created" in msg and "at least one object store server" in msg
        _no_writes(blade)

    def test_duplicate_servers_are_sent_once(self):
        module = _module(servers=["tenant_a", "tenant_b", "tenant_a"])
        blade = _blade()
        _run(module, blade)
        blade.post_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"],
            object_store_virtual_host={
                "attached_servers": [_ref("tenant_a"), _ref("tenant_b")]
            },
        )
        blade.get_servers.assert_called_once_with(names=["tenant_a", "tenant_b"])

    def test_wildcard_is_left_to_the_array(self):
        module = _module(servers=["*"])
        blade = _blade()
        _run(module, blade)
        blade.get_servers.assert_not_called()
        blade.post_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"],
            object_store_virtual_host={"attached_servers": [_ref("*")]},
        )
        # the result is read back like any other create
        assert blade.get_object_store_virtual_hosts.call_count == 3
        blade.delete_object_store_virtual_hosts.assert_not_called()
        assert _changed(module) is True

    def test_old_api_create_is_unchanged(self):
        """Before REST 2.20 there are no attached servers and nothing to look up"""
        module = _module()
        blade = _blade()
        _run(module, blade, api_version="2.19")
        blade.get_servers.assert_not_called()
        blade.get_realms_defaults.assert_not_called()
        blade.post_object_store_virtual_hosts.assert_called_once_with(names=["acme-s3"])
        blade.delete_object_store_virtual_hosts.assert_not_called()
        assert _changed(module) is True

    # ---------------- read-back after create ----------------

    def test_created_host_is_read_back(self):
        module = _module(servers=["tenant_a"])
        blade = _blade()
        _run(module, blade)
        calls = [
            call[1].get("names")
            for call in blade.get_object_store_virtual_hosts.call_args_list
        ]
        # lookup, host count, read-back after the POST
        assert calls == [["acme-s3"], None, ["acme-s3"]]
        blade.delete_object_store_virtual_hosts.assert_not_called()
        assert _changed(module) is True

    def test_host_created_without_server_is_deleted_again(self):
        module = _module(servers=["tenant_a"])
        blade = _blade()
        blade.quirks["post_without_servers"] = True
        _run(module, blade)
        msg = _failure(module)
        assert "deleted again" in msg and "at least one object store server" in msg
        blade.delete_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"]
        )
        assert "acme-s3" not in blade.hosts

    def test_host_that_cannot_be_read_back_is_deleted_again(self):
        module = _module(servers=["tenant_a"], context="peer1")
        blade = _blade()
        blade.quirks["hidden"] = ("acme-s3",)
        _run(module, blade)
        assert "deleted again" in _failure(module)
        blade.delete_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"], context_names=["peer1"]
        )

    def test_failed_delete_after_create_is_reported(self):
        module = _module(servers=["tenant_a"])
        blade = _blade()
        blade.quirks["post_without_servers"] = True
        blade.delete_object_store_virtual_hosts.side_effect = None
        blade.delete_object_store_virtual_hosts.return_value = _response(400)
        _run(module, blade)
        msg = _failure(module)
        assert "deleting it again failed" in msg and "array error" in msg
        assert "Attach a server to it or delete it" in msg


class TestAttachedServerGuardUpdate:
    """The last server is never detached from a virtual host"""

    # ---------------- refusals ----------------

    def test_empty_servers_refused(self):
        module = _module(servers=[])
        blade = _blade(
            {"acme-s3": _vhost("acme-s3", servers=["_array_server", "tenant_a"])}
        )
        _run(module, blade)
        msg = _failure(module)
        assert "empty list" in msg and "at least one object store server" in msg
        assert "state=absent" in msg
        _no_writes(blade)
        assert _attached(blade, "acme-s3") == ["_array_server", "tenant_a"]

    def test_empty_servers_refused_in_check_mode(self):
        module = _module(check_mode=True, servers=[])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["tenant_a"])})
        _run(module, blade)
        assert "empty list" in _failure(module)
        _no_writes(blade)

    def test_empty_servers_refused_on_host_without_server(self):
        module = _module(servers=[])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=[])})
        _run(module, blade)
        assert "empty list" in _failure(module)
        _no_writes(blade)

    def test_empty_servers_refused_on_wildcard_host(self):
        module = _module(servers=[])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["*"])})
        _run(module, blade)
        assert "empty list" in _failure(module)
        _no_writes(blade)

    def test_empty_servers_refused_through_rename_fallback(self):
        """name is gone, rename exists: the renamed host is guarded as well"""
        module = _module(name="acme-old", rename="acme-s3", servers=[])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["tenant_a"])})
        _run(module, blade)
        assert "empty list" in _failure(module)
        _no_writes(blade)
        assert _attached(blade, "acme-s3") == ["tenant_a"]

    def test_blank_server_name_refused(self):
        module = _module(servers=[""])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["tenant_a"])})
        _run(module, blade)
        assert "empty server name" in _failure(module)
        _no_writes(blade)

    def test_empty_result_refused_without_the_parameter_check(self):
        """Second line of defence: the computed result is refused when empty"""
        module = _module(servers=[])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["tenant_a"])})
        with patch(MOD + "._validate_servers"):
            _run(module, blade)
        msg = _failure(module)
        assert "Detaching tenant_a would leave" in msg and "state=absent" in msg
        _no_writes(blade)

    def test_empty_result_refused_without_the_parameter_check_in_check_mode(self):
        module = _module(check_mode=True, servers=[])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["tenant_a"])})
        with patch(MOD + "._validate_servers"):
            _run(module, blade)
        assert "would leave" in _failure(module)
        _no_writes(blade)

    # ---------------- attach before detach ----------------

    def test_swap_attaches_before_it_detaches(self):
        module = _module(servers=["tenant_b", "tenant_c"])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["tenant_a", "tenant_b"])})
        _run(module, blade)
        assert _bodies(blade) == [
            {"add_attached_servers": [_ref("tenant_c")]},
            {"remove_attached_servers": [_ref("tenant_a")]},
        ]
        assert _changed(module) is True
        assert _attached(blade, "acme-s3") == ["tenant_b", "tenant_c"]

    def test_full_swap_never_empties_the_host(self):
        """Replace the only server: the new one is attached first"""
        seen = []
        module = _module(servers=["tenant_b"])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["tenant_a"])})
        inner = blade.patch_object_store_virtual_hosts.side_effect

        def _recording_patch(**kwargs):
            res = inner(**kwargs)
            seen.append(_attached(blade, "acme-s3"))
            return res

        blade.patch_object_store_virtual_hosts.side_effect = _recording_patch
        _run(module, blade)
        assert seen == [["tenant_a", "tenant_b"], ["tenant_b"]]
        assert _changed(module) is True

    def test_detach_keeping_one_server(self):
        module = _module(servers=["tenant_a"])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["tenant_a", "tenant_b"])})
        _run(module, blade)
        assert _bodies(blade) == [{"remove_attached_servers": [_ref("tenant_b")]}]
        # lookup, the read right before the detach, the read-back after it
        assert blade.get_object_store_virtual_hosts.call_count == 3
        assert _changed(module) is True
        assert _attached(blade, "acme-s3") == ["tenant_a"]

    def test_detach_not_sent_when_attach_took_no_effect(self):
        """The array answers 200 to the attach but attaches nothing"""
        module = _module(servers=["tenant_b"])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["tenant_a"])})
        blade.quirks["ignore_attach"] = True
        _run(module, blade)
        msg = _failure(module)
        assert "would leave" in msg and "nothing was detached" in msg
        assert _bodies(blade) == [{"add_attached_servers": [_ref("tenant_b")]}]
        assert _attached(blade, "acme-s3") == ["tenant_a"]

    def test_detach_not_sent_when_host_cannot_be_read_again(self):
        module = _module(servers=["tenant_b"])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["tenant_a"])})
        inner = blade.patch_object_store_virtual_hosts.side_effect

        def _patch_then_hide(**kwargs):
            res = inner(**kwargs)
            blade.quirks["hidden"] = ("acme-s3",)
            return res

        blade.patch_object_store_virtual_hosts.side_effect = _patch_then_hide
        _run(module, blade)
        msg = _failure(module)
        assert "could not be read again" in msg and "nothing was detached" in msg
        assert _bodies(blade) == [{"add_attached_servers": [_ref("tenant_b")]}]
        assert _attached(blade, "acme-s3") == ["tenant_a", "tenant_b"]

    def test_detach_not_sent_when_another_change_removed_the_rest(self):
        """The host lost its other server after the module first read it"""
        module = _module(servers=["tenant_a"])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["tenant_a", "tenant_b"])})
        inner = blade.get_object_store_virtual_hosts.side_effect
        reads = []

        def _get_then_lose_tenant_a(**kwargs):
            res = inner(**kwargs)
            reads.append(kwargs)
            if len(reads) == 1:
                # another client detaches tenant_a right after the first read
                blade.hosts["acme-s3"] = _vhost("acme-s3", servers=["tenant_b"])
            return res

        blade.get_object_store_virtual_hosts.side_effect = _get_then_lose_tenant_a
        _run(module, blade)
        msg = _failure(module)
        assert "would leave" in msg and "nothing was detached" in msg
        blade.patch_object_store_virtual_hosts.assert_not_called()
        assert _attached(blade, "acme-s3") == ["tenant_b"]

    def test_failed_attach_detaches_nothing(self):
        module = _module(servers=["tenant_b"])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["tenant_a"])})
        blade.quirks["fail_patch"] = lambda body: "add_attached_servers" in body
        _run(module, blade)
        msg = _failure(module)
        assert "attach tenant_b" in msg and "array error" in msg
        assert len(_bodies(blade)) == 1
        assert _attached(blade, "acme-s3") == ["tenant_a"]

    def test_failed_detach_leaves_the_host_attached(self):
        module = _module(servers=["tenant_b"])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["tenant_a"])})
        blade.quirks["fail_patch"] = lambda body: "remove_attached_servers" in body
        _run(module, blade)
        msg = _failure(module)
        assert "detach tenant_a" in msg and "array error" in msg
        assert _attached(blade, "acme-s3") == ["tenant_a", "tenant_b"]

    def test_servers_hostname_rename_in_order(self):
        """attach, detach, hostname, rename: all on the old name"""
        module = _module(
            hostname="s3.acme.com", servers=["tenant_b"], rename="acme-object"
        )
        blade = _blade(
            {"acme-s3": _vhost("acme-s3", hostname="acme-s3", servers=["tenant_a"])}
        )
        _run(module, blade)
        calls = blade.patch_object_store_virtual_hosts.call_args_list
        assert _bodies(blade) == [
            {"add_attached_servers": [_ref("tenant_b")]},
            {"remove_attached_servers": [_ref("tenant_a")]},
            {"hostname": "s3.acme.com"},
            {"name": "acme-object"},
        ]
        assert all(c[1]["names"] == ["acme-s3"] for c in calls)
        assert _changed(module) is True
        assert _attached(blade, "acme-object") == ["tenant_b"]

    # ---------------- existing host without an attached server ----------------

    def test_host_without_server_hostname_change_refused(self):
        module = _module(hostname="s3.acme.com")
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=[])})
        _run(module, blade)
        msg = _failure(module)
        assert "has no attached server" in msg and "servers" in msg
        assert "state=absent" in msg
        _no_writes(blade)

    def test_host_without_server_hostname_change_refused_in_check_mode(self):
        module = _module(check_mode=True, hostname="s3.acme.com")
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=[])})
        _run(module, blade)
        assert "has no attached server" in _failure(module)
        _no_writes(blade)

    def test_host_without_server_rename_refused(self):
        module = _module(rename="acme-object")
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=[])})
        _run(module, blade)
        assert "has no attached server" in _failure(module)
        _no_writes(blade)

    def test_host_without_server_and_nothing_to_do_warns(self):
        module = _module()
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=[])})
        _run(module, blade)
        _no_writes(blade)
        module.warn.assert_called_once()
        assert "has no attached server" in module.warn.call_args[0][0]
        assert _changed(module) is False

    def test_host_without_server_is_attached_before_other_changes(self):
        module = _module(hostname="s3.acme.com", servers=["tenant_a"])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=[])})
        _run(module, blade)
        assert _bodies(blade) == [
            {"add_attached_servers": [_ref("tenant_a")]},
            {"hostname": "s3.acme.com"},
        ]
        module.warn.assert_not_called()
        assert _changed(module) is True

    def test_old_api_host_is_not_judged(self):
        """Before REST 2.20 a host has no attached servers; nothing to warn about"""
        vhost = Mock(spec=["name"])
        vhost.name = "acme-s3"
        module = _module()
        blade = _blade({"acme-s3": vhost})
        _run(module, blade, api_version="2.19")
        _no_writes(blade)
        module.warn.assert_not_called()
        assert _changed(module) is False

    # ---------------- read-back after a server change ----------------

    def test_server_change_is_read_back(self):
        module = _module(servers=["tenant_a", "tenant_b"])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["tenant_a"])})
        _run(module, blade)
        # lookup, then the read-back after the attach
        assert blade.get_object_store_virtual_hosts.call_count == 2
        assert _changed(module) is True

    def test_host_left_without_server_gets_previous_servers_back(self):
        """Should be impossible: the detach removes every server on the array"""
        module = _module(servers=["tenant_a"])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["tenant_a", "tenant_b"])})
        blade.quirks["detach_drops_all"] = True
        _run(module, blade)
        msg = _failure(module)
        assert "had no attached server" in msg
        assert "tenant_a, tenant_b was attached again" in msg
        assert _bodies(blade) == [
            {"remove_attached_servers": [_ref("tenant_b")]},
            {"add_attached_servers": [_ref("tenant_a"), _ref("tenant_b")]},
        ]
        assert _attached(blade, "acme-s3") == ["tenant_a", "tenant_b"]
        blade.delete_object_store_virtual_hosts.assert_not_called()

    def test_repair_falls_back_to_the_requested_servers(self):
        module = _module(servers=["tenant_a"])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["tenant_a", "tenant_b"])})
        blade.quirks["detach_drops_all"] = True
        blade.quirks["fail_patch"] = lambda body: body.get("add_attached_servers") == [
            _ref("tenant_a"),
            _ref("tenant_b"),
        ]
        _run(module, blade)
        msg = _failure(module)
        assert "tenant_a was attached again" in msg
        assert _attached(blade, "acme-s3") == ["tenant_a"]
        blade.delete_object_store_virtual_hosts.assert_not_called()

    def test_failed_repair_is_reported_and_host_is_kept(self):
        module = _module(servers=["tenant_a"])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["tenant_a", "tenant_b"])})
        blade.quirks["detach_drops_all"] = True
        blade.quirks["fail_patch"] = lambda body: "add_attached_servers" in body
        _run(module, blade)
        msg = _failure(module)
        assert "has no attached server" in msg and "attaching one again failed" in msg
        assert "Attach a server to it or delete it" in msg
        blade.delete_object_store_virtual_hosts.assert_not_called()
        assert "acme-s3" in blade.hosts

    def test_unreadable_host_after_server_change_fails(self):
        module = _module(servers=["tenant_a", "tenant_b"])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["tenant_a"])})
        inner = blade.patch_object_store_virtual_hosts.side_effect

        def _patch_then_hide(**kwargs):
            res = inner(**kwargs)
            blade.quirks["hidden"] = ("acme-s3",)
            return res

        blade.patch_object_store_virtual_hosts.side_effect = _patch_then_hide
        _run(module, blade)
        assert "could not be read back" in _failure(module)
        blade.delete_object_store_virtual_hosts.assert_not_called()
