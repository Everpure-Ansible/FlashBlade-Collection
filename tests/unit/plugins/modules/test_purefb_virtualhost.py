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


def _vhost(name, hostname=None, servers=()):
    vhost = Mock()
    vhost.name = name
    vhost.hostname = hostname if hostname is not None else name
    refs = []
    for srv in servers:
        ref = Mock()
        ref.name = srv
        refs.append(ref)
    vhost.attached_servers = refs
    return vhost


def _response(status_code=200, items=None, total=None):
    res = Mock()
    res.status_code = status_code
    res.items = items if items is not None else []
    if total is not None:
        res.total_item_count = total
    return res


def _blade(existing=None, total=1):
    """A blade whose virtual-host GET answers by name.

    existing maps vhost name -> vhost object; unknown names return 400 (the
    array's behaviour for a names= filter on a missing object). A GET with no
    names returns the count for the MAX_HOST_COUNT check.
    """
    existing = existing or {}
    blade = Mock()
    blade.get_fleets.return_value = _response(200, items=[])

    def _get(**kwargs):
        names = kwargs.get("names")
        if names is None:
            return _response(200, items=list(existing.values()), total=total)
        vhost = existing.get(names[0])
        if vhost is None:
            return _response(400, items=[])
        return _response(200, items=[vhost])

    blade.get_object_store_virtual_hosts.side_effect = _get
    blade.post_object_store_virtual_hosts.return_value = _response(200)
    blade.patch_object_store_virtual_hosts.return_value = _response(200)
    blade.delete_object_store_virtual_hosts.return_value = _response(200)
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

    def test_create_bare_name_without_new_options(self):
        """No hostname/servers: POST by name only so the array applies defaults"""
        module = _module()
        blade = _blade()
        _run(module, blade)
        blade.post_object_store_virtual_hosts.assert_called_once_with(names=["acme-s3"])
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
        """attached_servers omitted so the array attaches the default server"""
        module = _module(hostname="s3.acme.com")
        blade = _blade()
        _run(module, blade)
        blade.post_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"],
            object_store_virtual_host={"hostname": "s3.acme.com"},
        )

    def test_create_with_empty_servers_sends_empty_list(self):
        """servers: [] on create must reach the array as attached_servers=[]"""
        module = _module(servers=[])
        blade = _blade()
        _run(module, blade)
        blade.post_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"],
            object_store_virtual_host={"attached_servers": []},
        )

    def test_create_with_context(self):
        module = _module(hostname="s3.acme.com", context="peer1")
        blade = _blade()
        _run(module, blade)
        blade.get_object_store_virtual_hosts.assert_any_call(
            names=["acme-s3"], context_names=["peer1"]
        )
        blade.post_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"],
            object_store_virtual_host={"hostname": "s3.acme.com"},
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
            names=["acme-s3"], context_names=["local-array"]
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
        vhost = Mock(spec=["name"])
        vhost.name = "acme-s3"
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
        blade.patch_object_store_virtual_hosts.return_value = _response(400)
        _run(module, blade)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "set hostname" in msg and "array error" in msg

    # ---------------- update: servers ----------------

    def test_update_servers_sends_exact_delta(self):
        module = _module(servers=["tenant_b", "tenant_c"])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["tenant_a", "tenant_b"])})
        _run(module, blade)
        blade.patch_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"],
            object_store_virtual_host={
                "add_attached_servers": [_ref("tenant_c")],
                "remove_attached_servers": [_ref("tenant_a")],
            },
        )
        assert _changed(module) is True

    def test_update_servers_add_only(self):
        module = _module(servers=["_array_server", "tenant_a"])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["_array_server"])})
        _run(module, blade)
        blade.patch_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"],
            object_store_virtual_host={"add_attached_servers": [_ref("tenant_a")]},
        )

    def test_update_servers_empty_detaches_all(self):
        module = _module(servers=[])
        blade = _blade(
            {"acme-s3": _vhost("acme-s3", servers=["_array_server", "tenant_a"])}
        )
        _run(module, blade)
        blade.patch_object_store_virtual_hosts.assert_called_once_with(
            names=["acme-s3"],
            object_store_virtual_host={
                "remove_attached_servers": [_ref("_array_server"), _ref("tenant_a")]
            },
        )
        assert _changed(module) is True

    def test_update_servers_same_set_is_noop(self):
        """Order does not matter; same set means no PATCH"""
        module = _module(servers=["tenant_b", "tenant_a"])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=["tenant_a", "tenant_b"])})
        _run(module, blade)
        blade.patch_object_store_virtual_hosts.assert_not_called()
        assert _changed(module) is False

    def test_update_servers_empty_on_empty_is_noop(self):
        module = _module(servers=[])
        blade = _blade({"acme-s3": _vhost("acme-s3", servers=[])})
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
        blade.patch_object_store_virtual_hosts.return_value = _response(400)
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

    def test_hostname_servers_rename_three_patches_in_order(self):
        """hostname, then the server delta, then the rename, all on the old name"""
        module = _module(
            hostname="s3.acme.com", servers=["tenant_b"], rename="acme-object"
        )
        blade = _blade(
            {"acme-s3": _vhost("acme-s3", hostname="acme-s3", servers=["tenant_a"])}
        )
        _run(module, blade)
        calls = blade.patch_object_store_virtual_hosts.call_args_list
        assert [c[1]["object_store_virtual_host"] for c in calls] == [
            {"hostname": "s3.acme.com"},
            {
                "add_attached_servers": [_ref("tenant_b")],
                "remove_attached_servers": [_ref("tenant_a")],
            },
            {"name": "acme-object"},
        ]
        assert all(c[1]["names"] == ["acme-s3"] for c in calls)
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
        blade.post_object_store_virtual_hosts.assert_called_once_with(names=["acme-s3"])
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
        blade.patch_object_store_virtual_hosts.return_value = _response(400)
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
        blade.delete_object_store_virtual_hosts.return_value = _response(400)
        _run(module, blade)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to delete" in msg and "array error" in msg
