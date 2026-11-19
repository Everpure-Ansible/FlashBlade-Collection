# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_server module."""

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

from plugins.modules.purefb_server import main


class _Version:
    """Minimal LooseVersion stand-in.

    main() has two REST gates (2.16 for the module, 2.24 for the local
    directory service options), so the tests compare real version strings
    instead of sharing one mocked __gt__.
    """

    def __init__(self, vstring):
        self.parts = tuple(int(part) for part in str(vstring).split("."))

    def __gt__(self, other):
        return self.parts > other.parts

    def __le__(self, other):
        return self.parts <= other.parts


def _base_params(**overrides):
    params = {
        "name": "myserver",
        "state": "present",
        "dns": None,
        "directory_service": None,
        "local_directory_service": None,
        "create_local_directory_service": None,
    }
    params.update(overrides)
    return params


def _response(status_code=200, items=None, message=None):
    """An SDK response: the items of a 200, the error of the array otherwise."""
    res = Mock()
    res.status_code = status_code
    res.items = items if items is not None else []
    if status_code != 200:
        error = Mock(spec=["message"])
        error.message = message or "Internal error."
        res.errors = [error]
    return res


def _absent():
    """What GET /servers answers for a name that matches no server."""
    return _response(400, message="Server does not exist.")


def _error_message(response, default="Unknown error"):
    """get_error_message of module_utils.common, which is mocked here."""
    errors = getattr(response, "errors", None)
    if isinstance(errors, list) and errors:
        return errors[0].message
    return default


def _ref(name):
    ref = Mock(spec=["name"])
    ref.name = name
    return ref


SERVER_ID = "0a0a0a0a-1111-2222-3333-444444444444"
OTHER_ID = "0b0b0b0b-1111-2222-3333-444444444444"
WILDCARD_ID = "0c0c0c0c-1111-2222-3333-444444444444"
THIRD_ID = "0d0d0d0d-1111-2222-3333-444444444444"
FOURTH_ID = "0e0e0e0e-1111-2222-3333-444444444444"


def _server(
    dns=("management",),
    directory_services=("myserver_nfs",),
    lds=None,
    name="myserver",
    server_id=SERVER_ID,
):
    """A Server as the SDK returns it from REST 2.24 onwards."""
    server = Mock(
        spec=[
            "id",
            "name",
            "created",
            "dns",
            "directory_services",
            "local_directory_service",
            "realms",
        ]
    )
    server.id = server_id
    server.name = name
    server.created = 1700000000000
    server.dns = [_ref(name) for name in dns]
    server.directory_services = [_ref(name) for name in directory_services]
    server.local_directory_service = _ref(lds) if lds else None
    server.realms = [_ref(name.rpartition("::")[0])] if "::" in name else []
    return server


def _realm_server(dns=("rzaudit::dns1",), lds=None):
    """Server rzaudit::srv as the array returns a server in a realm."""
    return _server(
        dns=dns,
        directory_services=("rzaudit::srv_nfs",),
        lds=lds,
        name="rzaudit::srv",
    )


def _attached(name, ref_id=None):
    """A server reference as a virtual host lists it in attached_servers."""
    ref = Mock(spec=["id", "name", "resource_type"])
    ref.id = ref_id
    ref.name = name
    ref.resource_type = "servers"
    return ref


def _vhost(name, *attached):
    """An ObjectStoreVirtualHost as the SDK returns it from REST 2.20 onwards."""
    vhost = Mock(spec=["id", "name", "hostname", "attached_servers", "realms"])
    vhost.name = name
    vhost.hostname = name + ".example.com"
    vhost.attached_servers = list(attached)
    vhost.realms = []
    return vhost


def _builtin_vhost():
    """The built-in virtual host, attached to the wildcard pseudo-server."""
    return _vhost("s3.amazonaws.com", _attached("*", WILDCARD_ID))


def _delete_blade(vhosts=None, vhost_status=200, name="myserver"):
    """A blade holding the server to delete and the given virtual hosts."""
    blade = Mock()
    blade.get_servers.return_value = _response(200, [_server(name=name)])
    blade.get_object_store_virtual_hosts.return_value = _response(
        vhost_status, [_builtin_vhost()] if vhosts is None else vhosts
    )
    blade.delete_servers.return_value = _response(200)
    return blade


def _run_main(params, blade, api_version="2.30", check_mode=False, has_sdk=True):
    """Run main() with the module plumbing patched.

    Returns the module mock; the AnsibleModule mock is on module.ansible_module.
    """
    module = Mock()
    module.params = params
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    with patch(
        "plugins.modules.purefb_server.AnsibleModule", return_value=module
    ) as mock_ansible_module, patch(
        "plugins.modules.purefb_server.get_system", return_value=blade
    ), patch(
        "plugins.modules.purefb_server.get_rest_api_version", return_value=api_version
    ), patch(
        "plugins.modules.purefb_server.get_error_message", _error_message
    ), patch(
        "plugins.modules.purefb_server.LooseVersion", _Version
    ), patch(
        "plugins.modules.purefb_server.HAS_PYPURECLIENT", has_sdk
    ):
        try:
            main()
        except SystemExit:
            pass
    module.ansible_module = mock_ansible_module
    return module


class TestPurefbServer:
    """Test cases for purefb_server module"""

    # ---------------- argument spec ----------------

    def test_lds_options_are_mutually_exclusive(self):
        """The two local directory service options are declared mutually exclusive"""
        blade = Mock()
        blade.get_servers.return_value = _absent()
        blade.post_servers.return_value = _response(200)

        module = _run_main(_base_params(), blade)

        kwargs = module.ansible_module.call_args[1]
        assert kwargs["supports_check_mode"] is True
        assert kwargs["mutually_exclusive"] == [
            ["local_directory_service", "create_local_directory_service"]
        ]

    # ---------------- create ----------------

    @patch("plugins.modules.purefb_server.ServerPost")
    def test_create_with_create_lds_sends_query_parameter(self, mock_server_post):
        """create_local_directory_service goes to POST as a query kwarg, never
        as the ServerPost local_directory_service body reference"""
        blade = Mock()
        blade.get_servers.return_value = _absent()
        blade.post_servers.return_value = _response(200)

        module = _run_main(
            _base_params(create_local_directory_service="myserver_local"), blade
        )

        blade.post_servers.assert_called_once()
        kwargs = blade.post_servers.call_args[1]
        assert kwargs["names"] == ["myserver"]
        assert kwargs["create_ds"] == "myserver_nfs"
        assert kwargs["create_local_directory_service"] == "myserver_local"
        mock_server_post.assert_called_once_with()
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_server.ServerPost")
    def test_create_without_create_lds_omits_query_parameter(self, mock_server_post):
        """A plain create does not send create_local_directory_service at all"""
        blade = Mock()
        blade.get_servers.return_value = _absent()
        blade.post_servers.return_value = _response(200)

        module = _run_main(_base_params(dns=["mydns"]), blade)

        kwargs = blade.post_servers.call_args[1]
        assert "create_local_directory_service" not in kwargs
        assert kwargs["create_ds"] == "myserver_nfs"
        assert "dns" in mock_server_post.call_args[1]
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_server.Reference")
    @patch("plugins.modules.purefb_server.ServerPost")
    def test_create_with_existing_lds_sets_body_reference(
        self, mock_server_post, mock_reference
    ):
        """local_directory_service attaches an existing LDS through the body"""
        blade = Mock()
        blade.get_servers.return_value = _absent()
        blade.post_servers.return_value = _response(200)

        _run_main(_base_params(local_directory_service="myserver_local"), blade)

        mock_reference.assert_called_once_with(name="myserver_local")
        assert (
            mock_server_post.call_args[1]["local_directory_service"]
            is mock_reference.return_value
        )
        assert "create_local_directory_service" not in blade.post_servers.call_args[1]

    def test_create_check_mode_skips_post(self):
        """Check mode reports a change without calling POST"""
        blade = Mock()
        blade.get_servers.return_value = _absent()

        module = _run_main(
            _base_params(create_local_directory_service="myserver_local"),
            blade,
            check_mode=True,
        )

        blade.post_servers.assert_not_called()
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_fails_on_api_error(self):
        """A failed POST surfaces as fail_json naming the server"""
        blade = Mock()
        blade.get_servers.return_value = _absent()
        blade.post_servers.return_value = _response(400)

        module = _run_main(
            _base_params(create_local_directory_service="myserver_local"), blade
        )

        module.fail_json.assert_called_once()
        assert "Failed to add server myserver" in module.fail_json.call_args[1]["msg"]
        module.exit_json.assert_not_called()

    # ---------------- update ----------------

    def test_update_create_lds_matching_is_idempotent(self):
        """Rerunning with create_local_directory_service on a server that
        already has that LDS reports no change and sends nothing"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server(lds="myserver_local")])

        module = _run_main(
            _base_params(create_local_directory_service="myserver_local"), blade
        )

        blade.patch_servers.assert_not_called()
        blade.post_servers.assert_not_called()
        module.fail_json.assert_not_called()
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_create_lds_mismatch_fails(self):
        """An existing server with a different LDS fails with guidance instead
        of hiding the drift"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server(lds="other_local")])

        module = _run_main(
            _base_params(create_local_directory_service="myserver_local"), blade
        )

        blade.patch_servers.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "other_local" in msg
        assert "myserver_local" in msg
        assert "purefb_local_ds" in msg

    def test_update_create_lds_unset_fails(self):
        """An existing server without any LDS fails: the array cannot create
        and attach one after the fact"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server()])

        module = _run_main(
            _base_params(create_local_directory_service="myserver_local"), blade
        )

        blade.patch_servers.assert_not_called()
        module.fail_json.assert_called_once()
        assert "not set" in module.fail_json.call_args[1]["msg"]

    def test_update_dns_change_patches(self):
        """A DNS change is sent as a PATCH and reported as changed"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server()])
        blade.patch_servers.return_value = _response(200)

        module = _run_main(_base_params(dns=["mydns"]), blade)

        blade.patch_servers.assert_called_once()
        assert blade.patch_servers.call_args[1]["names"] == ["myserver"]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_dns_same_is_noop(self):
        """Matching DNS sends nothing"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server()])

        module = _run_main(_base_params(dns=["management"]), blade)

        blade.patch_servers.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_attaches_existing_lds(self):
        """local_directory_service on an unattached server is PATCHed"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server()])
        blade.patch_servers.return_value = _response(200)

        module = _run_main(
            _base_params(local_directory_service="myserver_local"), blade
        )

        blade.patch_servers.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_lds_already_attached_is_noop(self):
        """local_directory_service matching the attached LDS sends nothing"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server(lds="myserver_local")])

        module = _run_main(
            _base_params(local_directory_service="myserver_local"), blade
        )

        blade.patch_servers.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_check_mode_reports_without_patch(self):
        """Check mode reports the DNS change without sending the PATCH"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server()])

        module = _run_main(_base_params(dns=["mydns"]), blade, check_mode=True)

        blade.patch_servers.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_fails_on_api_error(self):
        """A failed PATCH surfaces as fail_json"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server()])
        blade.patch_servers.return_value = _response(400)

        module = _run_main(_base_params(dns=["mydns"]), blade)

        module.fail_json.assert_called_once()
        assert "Failed to update DNS config" in module.fail_json.call_args[1]["msg"]

    # ---------------- delete ----------------

    def test_delete_cascades_directory_services(self):
        """Delete removes the server and its NFS directory service"""
        blade = _delete_blade()

        module = _run_main(_base_params(state="absent"), blade)

        blade.delete_servers.assert_called_once_with(
            names=["myserver"], cascade_delete="directory-services"
        )
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_nonexistent_is_noop(self):
        """Deleting a server that is already gone reports no change"""
        blade = Mock()
        blade.get_servers.return_value = _absent()

        module = _run_main(_base_params(state="absent"), blade)

        blade.delete_servers.assert_not_called()
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_delete_check_mode_skips_call(self):
        """Check mode reports the delete without calling DELETE"""
        blade = _delete_blade()

        module = _run_main(_base_params(state="absent"), blade, check_mode=True)

        blade.delete_servers.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_fails_on_api_error(self):
        """A failed DELETE surfaces as fail_json"""
        blade = _delete_blade()
        blade.delete_servers.return_value = _response(400)

        module = _run_main(_base_params(state="absent"), blade)

        module.fail_json.assert_called_once()
        assert (
            "Failed to delete server myserver" in module.fail_json.call_args[1]["msg"]
        )

    # ---------------- delete: virtual host guard ----------------

    def test_delete_reads_virtual_hosts_before_deleting(self):
        """The virtual hosts are read first; the built-in wildcard host does not block"""
        blade = _delete_blade()

        module = _run_main(_base_params(state="absent"), blade)

        blade.get_object_store_virtual_hosts.assert_called_once_with()
        blade.delete_servers.assert_called_once_with(
            names=["myserver"], cascade_delete="directory-services"
        )
        calls = [call[0] for call in blade.mock_calls]
        assert calls.index("get_object_store_virtual_hosts") < calls.index(
            "delete_servers"
        )
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_check_mode_still_reads_virtual_hosts(self):
        """Check mode runs the same read-only guard and sends no delete"""
        blade = _delete_blade()

        module = _run_main(_base_params(state="absent"), blade, check_mode=True)

        blade.get_object_store_virtual_hosts.assert_called_once_with()
        blade.delete_servers.assert_not_called()
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_refused_for_only_server_of_virtual_host(self):
        """A server that is the only one attached to a virtual host is kept"""
        blade = _delete_blade(
            [_builtin_vhost(), _vhost("acme-s3", _attached("myserver", SERVER_ID))]
        )

        module = _run_main(_base_params(state="absent"), blade)

        blade.delete_servers.assert_not_called()
        blade.patch_object_store_virtual_hosts.assert_not_called()
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Server myserver was not deleted" in msg
        assert "at least one object store server" in msg
        assert "only server attached to acme-s3:" in msg
        assert "attach another server" in msg
        assert "along with other servers" not in msg
        assert "s3.amazonaws.com" not in msg

    def test_delete_refused_for_only_server_in_check_mode(self):
        """Check mode reports the same refusal instead of a change"""
        blade = _delete_blade([_vhost("acme-s3", _attached("myserver", SERVER_ID))])

        module = _run_main(_base_params(state="absent"), blade, check_mode=True)

        blade.delete_servers.assert_not_called()
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once()
        assert (
            "only server attached to acme-s3:" in module.fail_json.call_args[1]["msg"]
        )

    def test_delete_refused_for_one_of_several_servers(self):
        """A server sharing a virtual host is kept too, and the host is not touched"""
        blade = _delete_blade(
            [
                _vhost(
                    "acme-s3",
                    _attached("otherserver", OTHER_ID),
                    _attached("myserver", SERVER_ID),
                )
            ]
        )

        module = _run_main(_base_params(state="absent"), blade)

        blade.delete_servers.assert_not_called()
        blade.patch_object_store_virtual_hosts.assert_not_called()
        blade.delete_object_store_virtual_hosts.assert_not_called()
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "along with other servers to acme-s3:" in msg
        assert "purefb_virtualhost" in msg
        assert "only server attached" not in msg

    def test_delete_refused_for_one_of_several_servers_in_check_mode(self):
        """Check mode refuses the shared case as well"""
        blade = _delete_blade(
            [
                _vhost(
                    "acme-s3",
                    _attached("myserver", SERVER_ID),
                    _attached("otherserver", OTHER_ID),
                )
            ]
        )

        module = _run_main(_base_params(state="absent"), blade, check_mode=True)

        blade.delete_servers.assert_not_called()
        blade.patch_object_store_virtual_hosts.assert_not_called()
        module.fail_json.assert_called_once()
        assert (
            "along with other servers to acme-s3:"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_delete_refusal_names_every_virtual_host(self):
        """Both kinds of attachment are listed, sorted, and nothing else is"""
        mine = _attached("myserver", SERVER_ID)
        other = _attached("otherserver", OTHER_ID)
        blade = _delete_blade(
            [
                _builtin_vhost(),
                _vhost("zeta", mine),
                _vhost("shared-b", mine, other),
                _vhost("unrelated", other),
                _vhost("alpha", mine),
                _vhost("shared-a", other, mine),
            ]
        )

        module = _run_main(_base_params(state="absent"), blade)

        blade.delete_servers.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "only server attached to alpha, zeta:" in msg
        assert "along with other servers to shared-a, shared-b:" in msg
        assert "unrelated" not in msg
        assert "s3.amazonaws.com" not in msg

    def test_delete_allowed_when_virtual_hosts_use_other_servers(self):
        """Virtual hosts of other servers, or with no server list, do not block"""
        no_list = _vhost("old-shape")
        no_list.attached_servers = None
        blade = _delete_blade(
            [
                _builtin_vhost(),
                _vhost("acme-s3", _attached("otherserver", OTHER_ID)),
                _vhost("detached"),
                no_list,
            ]
        )

        module = _run_main(_base_params(state="absent"), blade)

        blade.get_object_store_virtual_hosts.assert_called_once_with()
        blade.delete_servers.assert_called_once_with(
            names=["myserver"], cascade_delete="directory-services"
        )
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_matches_attached_server_by_id(self):
        """An attachment carrying the server's ID blocks whatever name it shows"""
        blade = _delete_blade(
            [_vhost("acme-s3", _attached("somerealm::myserver", SERVER_ID))]
        )

        module = _run_main(_base_params(state="absent"), blade)

        blade.delete_servers.assert_not_called()
        module.fail_json.assert_called_once()
        assert (
            "only server attached to acme-s3:" in module.fail_json.call_args[1]["msg"]
        )

    def test_delete_matches_attached_server_by_name_without_ids(self):
        """Without IDs on either side the server name alone identifies it"""
        blade = _delete_blade([_vhost("acme-s3", _attached("myserver"))])
        blade.get_servers.return_value = _response(200, [_server(server_id=None)])

        module = _run_main(_base_params(state="absent"), blade)

        blade.delete_servers.assert_not_called()
        module.fail_json.assert_called_once()
        assert (
            "only server attached to acme-s3:" in module.fail_json.call_args[1]["msg"]
        )

    def test_delete_realm_server_refused(self):
        """A realm-qualified server attached to a realm virtual host is kept"""
        blade = _delete_blade(
            [
                _builtin_vhost(),
                _vhost("realm1::acme", _attached("realm1::srv", SERVER_ID)),
            ],
            name="realm1::srv",
        )

        module = _run_main(_base_params(name="realm1::srv", state="absent"), blade)

        blade.get_servers.assert_called_once_with(names=["realm1::srv"])
        blade.delete_servers.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Server realm1::srv was not deleted" in msg
        assert "only server attached to realm1::acme:" in msg

    def test_delete_array_server_not_blocked_by_realm_namesake(self):
        """realm1::srv attached to a virtual host does not protect array server srv"""
        blade = _delete_blade(
            [_vhost("realm1::acme", _attached("realm1::srv", OTHER_ID))], name="srv"
        )

        module = _run_main(_base_params(name="srv", state="absent"), blade)

        blade.get_object_store_virtual_hosts.assert_called_once_with()
        blade.delete_servers.assert_called_once_with(
            names=["srv"], cascade_delete="directory-services"
        )
        module.fail_json.assert_not_called()

    def test_delete_wildcard_is_not_another_server(self):
        """The wildcard next to the server does not make the host a shared one"""
        blade = _delete_blade(
            [
                _vhost(
                    "acme-s3",
                    _attached("*", WILDCARD_ID),
                    _attached("myserver", SERVER_ID),
                )
            ]
        )

        module = _run_main(_base_params(state="absent"), blade)

        blade.delete_servers.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "only server attached to acme-s3:" in msg
        assert "along with other servers" not in msg

    def test_delete_unidentified_attached_server_blocks(self):
        """An attachment with neither name nor ID is taken to be this server"""
        blade = _delete_blade([_vhost("acme-s3", _attached(None))])

        module = _run_main(_base_params(state="absent"), blade)

        blade.delete_servers.assert_not_called()
        module.fail_json.assert_called_once()
        assert "acme-s3" in module.fail_json.call_args[1]["msg"]

    def test_delete_reads_dict_references(self):
        """Attached servers given as plain dicts are matched the same way"""
        vhost = _vhost("acme-s3")
        vhost.attached_servers = [
            {"id": OTHER_ID, "name": "otherserver", "resource_type": "servers"},
            {"id": SERVER_ID, "name": "myserver", "resource_type": "servers"},
        ]
        blade = _delete_blade([vhost])

        module = _run_main(_base_params(state="absent"), blade)

        blade.delete_servers.assert_not_called()
        module.fail_json.assert_called_once()
        assert (
            "along with other servers to acme-s3:"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_delete_refused_when_virtual_hosts_cannot_be_read(self):
        """Without the virtual host list nothing is deleted"""
        blade = _delete_blade(vhost_status=400)

        module = _run_main(_base_params(state="absent"), blade)

        blade.delete_servers.assert_not_called()
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Server myserver was not deleted" in msg
        assert "failed to list the object store virtual hosts" in msg

    def test_delete_check_mode_fails_when_virtual_hosts_cannot_be_read(self):
        """Check mode does not report a delete it could not vouch for"""
        blade = _delete_blade(vhost_status=400)

        module = _run_main(_base_params(state="absent"), blade, check_mode=True)

        blade.delete_servers.assert_not_called()
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once()

    def test_delete_guard_starts_at_rest_2_20(self):
        """Before REST 2.20 virtual hosts have no attached servers to check"""
        vhosts = [_vhost("acme-s3", _attached("myserver", SERVER_ID))]
        old_blade = _delete_blade(vhosts)

        _run_main(_base_params(state="absent"), old_blade, api_version="2.19")

        old_blade.get_object_store_virtual_hosts.assert_not_called()
        old_blade.delete_servers.assert_called_once_with(
            names=["myserver"], cascade_delete="directory-services"
        )

        blade = _delete_blade(vhosts)

        module = _run_main(_base_params(state="absent"), blade, api_version="2.20")

        blade.get_object_store_virtual_hosts.assert_called_once_with()
        blade.delete_servers.assert_not_called()
        module.fail_json.assert_called_once()

    def test_refused_delete_sends_no_write(self):
        """Only a delete consults the virtual hosts, and a refusal writes nothing"""
        blade = _delete_blade([_vhost("acme-s3", _attached("myserver", SERVER_ID))])

        module = _run_main(_base_params(dns=["management"]), blade)

        blade.get_object_store_virtual_hosts.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

        _run_main(_base_params(state="absent"), blade)

        blade.get_object_store_virtual_hosts.assert_called_once_with()
        written = [
            call[0]
            for call in blade.mock_calls
            if call[0].startswith(("post_", "patch_", "delete_", "put_"))
        ]
        assert written == []

    # ---------------- delete: every server the name resolves to ----------------

    def test_delete_checks_every_server_the_name_matches(self):
        """A name holding a comma matches several servers and each one is checked"""
        vhosts = [_vhost("acme-s3", _attached("myserver", SERVER_ID))]
        params = _base_params(name="aserver,myserver", state="absent")
        for found in (
            [_server(name="aserver", server_id=OTHER_ID), _server()],
            [_server(), _server(name="zserver", server_id=OTHER_ID)],
        ):
            for check_mode in (False, True):
                blade = _delete_blade(vhosts)
                blade.get_servers.return_value = _response(200, found)

                module = _run_main(params, blade, check_mode=check_mode)

                blade.get_servers.assert_called_once_with(names=["aserver,myserver"])
                blade.delete_servers.assert_not_called()
                module.exit_json.assert_not_called()
                module.fail_json.assert_called_once()
                msg = module.fail_json.call_args[1]["msg"]
                assert "Server aserver,myserver was not deleted" in msg
                assert "only server attached to acme-s3:" in msg

    def test_delete_of_all_servers_of_a_virtual_host_leaves_it_none(self):
        """Servers deleted together are not each other's remaining server"""
        blade = _delete_blade(
            [
                _vhost(
                    "acme-s3",
                    _attached("aserver", OTHER_ID),
                    _attached("myserver", SERVER_ID),
                )
            ]
        )
        blade.get_servers.return_value = _response(
            200, [_server(name="aserver", server_id=OTHER_ID), _server()]
        )

        module = _run_main(_base_params(name="aserver,myserver", state="absent"), blade)

        blade.delete_servers.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "only server attached to acme-s3:" in msg
        assert "along with other servers" not in msg

    def test_delete_matches_server_name_whatever_the_case(self):
        """Server names are not case sensitive, so the reported name counts too"""
        blade = _delete_blade([_vhost("acme-s3", _attached("myserver"))])
        blade.get_servers.return_value = _response(200, [_server(server_id=None)])

        module = _run_main(_base_params(name="MYSERVER", state="absent"), blade)

        blade.get_servers.assert_called_once_with(names=["MYSERVER"])
        blade.delete_servers.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Server MYSERVER was not deleted" in msg
        assert "only server attached to acme-s3:" in msg

        blade = _delete_blade([_vhost("acme-s3", _attached("MyServer"))])
        blade.get_servers.return_value = _response(200, [_server(server_id=None)])

        module = _run_main(_base_params(state="absent"), blade)

        blade.delete_servers.assert_not_called()
        module.fail_json.assert_called_once()
        assert "acme-s3" in module.fail_json.call_args[1]["msg"]

    def test_delete_allowed_under_other_spelling_without_attachment(self):
        """The wider match leaves a server no virtual host is attached to alone"""
        blade = _delete_blade(
            [
                _builtin_vhost(),
                _vhost("acme-s3", _attached("otherserver", OTHER_ID)),
                _vhost("realm1::acme", _attached("realm1::myserver", THIRD_ID)),
                _vhost("acme-2", _attached("myserver2", FOURTH_ID)),
            ]
        )

        module = _run_main(_base_params(name="MYSERVER", state="absent"), blade)

        blade.get_object_store_virtual_hosts.assert_called_once_with()
        blade.delete_servers.assert_called_once_with(
            names=["MYSERVER"], cascade_delete="directory-services"
        )
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_id_only_reference_needs_a_server_id(self):
        """A reference with only an ID blocks when the server has no ID to compare"""
        vhosts = [_vhost("acme-s3", _attached(None, OTHER_ID))]
        blade = _delete_blade(vhosts)
        blade.get_servers.return_value = _response(200, [_server(server_id=None)])

        module = _run_main(_base_params(state="absent"), blade)

        blade.delete_servers.assert_not_called()
        module.fail_json.assert_called_once()
        assert "acme-s3" in module.fail_json.call_args[1]["msg"]

        blade = _delete_blade(vhosts)

        module = _run_main(_base_params(state="absent"), blade)

        blade.delete_servers.assert_called_once_with(
            names=["myserver"], cascade_delete="directory-services"
        )
        module.fail_json.assert_not_called()

    # ---------------- delete: attachments that cannot be read ----------------

    def test_delete_refused_when_attached_servers_are_not_reported(self):
        """A client speaking REST before 2.20 to a newer array sees no attachments"""
        for check_mode in (False, True):
            old_shape = Mock(spec=["id", "name"])
            old_shape.name = "acme-s3"
            builtin = Mock(spec=["id", "name"])
            builtin.name = "s3.amazonaws.com"
            blade = _delete_blade([builtin, old_shape])

            module = _run_main(
                _base_params(state="absent"), blade, check_mode=check_mode
            )

            blade.delete_servers.assert_not_called()
            module.exit_json.assert_not_called()
            module.fail_json.assert_called_once()
            msg = module.fail_json.call_args[1]["msg"]
            assert "Server myserver was not deleted" in msg
            assert "acme-s3, s3.amazonaws.com are not reported" in msg
            assert "py-pure-client release that supports REST 2.20" in msg

    def test_delete_reads_dict_virtual_hosts(self):
        """Virtual hosts given as plain dicts are read the same way"""
        blade = _delete_blade(
            [
                {
                    "name": "acme-s3",
                    "attached_servers": [{"id": SERVER_ID, "name": "myserver"}],
                }
            ]
        )

        module = _run_main(_base_params(state="absent"), blade)

        blade.delete_servers.assert_not_called()
        module.fail_json.assert_called_once()
        assert (
            "only server attached to acme-s3:" in module.fail_json.call_args[1]["msg"]
        )

        blade = _delete_blade([{"name": "acme-s3"}])

        module = _run_main(_base_params(state="absent"), blade)

        blade.delete_servers.assert_not_called()
        module.fail_json.assert_called_once()
        assert "acme-s3 are not reported" in module.fail_json.call_args[1]["msg"]

    def test_delete_not_sent_when_virtual_host_read_raises(self):
        """An exception while reading the virtual hosts leaves the server alone"""
        blade = _delete_blade()
        blade.get_object_store_virtual_hosts.side_effect = RuntimeError("lost")
        raised = False

        try:
            _run_main(_base_params(state="absent"), blade)
        except RuntimeError:
            raised = True

        assert raised
        blade.delete_servers.assert_not_called()

    def test_delete_not_sent_when_a_later_page_cannot_be_read(self):
        """A page of virtual hosts that fails to load stops the module first"""

        def _pages():
            yield _builtin_vhost()
            raise RuntimeError("next page failed")

        blade = _delete_blade()
        blade.get_object_store_virtual_hosts.return_value = _response(200, _pages())
        raised = False

        try:
            _run_main(_base_params(state="absent"), blade)
        except RuntimeError:
            raised = True

        assert raised
        blade.delete_servers.assert_not_called()

    # ---------------- gates ----------------

    def test_fails_on_unsupported_api_version(self):
        """REST older than 2.16 is refused"""
        blade = Mock()

        module = _run_main(_base_params(), blade, api_version="2.15")

        module.fail_json.assert_called_once()
        assert "REST version not supported" in module.fail_json.call_args[1]["msg"]
        blade.get_servers.assert_not_called()

    def test_create_lds_requires_rest_2_24(self):
        """create_local_directory_service is refused below REST 2.24"""
        blade = Mock()

        module = _run_main(
            _base_params(create_local_directory_service="myserver_local"),
            blade,
            api_version="2.23",
        )

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "create_local_directory_service" in msg
        assert "2.24" in msg
        blade.get_servers.assert_not_called()

    def test_local_directory_service_requires_rest_2_24(self):
        """local_directory_service is refused below REST 2.24"""
        blade = Mock()

        module = _run_main(
            _base_params(local_directory_service="myserver_local"),
            blade,
            api_version="2.23",
        )

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "local_directory_service" in msg
        assert "2.24" in msg

    def test_plain_create_allowed_below_rest_2_24(self):
        """Without either LDS option the module works on REST 2.16"""
        blade = Mock()
        blade.get_servers.return_value = _absent()
        blade.post_servers.return_value = _response(200)

        module = _run_main(_base_params(), blade, api_version="2.16")

        module.fail_json.assert_not_called()
        blade.post_servers.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_server.ServerPost")
    def test_create_lds_empty_string_is_omitted(self, mock_server_post):
        """create_local_directory_service: "" is treated as omitted, so it
        passes the 2.24 gate and is never sent to POST"""
        blade = Mock()
        blade.get_servers.return_value = _absent()
        blade.post_servers.return_value = _response(200)

        module = _run_main(
            _base_params(create_local_directory_service=""),
            blade,
            api_version="2.16",
        )

        module.fail_json.assert_not_called()
        kwargs = blade.post_servers.call_args[1]
        assert "create_local_directory_service" not in kwargs
        mock_server_post.assert_called_once_with()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_local_directory_service_empty_string_still_gated(self):
        """local_directory_service: "" means clear, so it still needs REST
        2.24 even though create_local_directory_service: "" does not"""
        blade = Mock()

        module = _run_main(
            _base_params(local_directory_service=""), blade, api_version="2.23"
        )

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "local_directory_service" in msg
        assert "2.24" in msg
        blade.get_servers.assert_not_called()

    def test_fails_without_sdk(self):
        """Missing py-pure-client is reported before any API call"""
        blade = Mock()

        module = _run_main(_base_params(), blade, has_sdk=False)

        module.fail_json.assert_called_once()
        assert "py-pure-client" in module.fail_json.call_args[1]["msg"]
        blade.get_servers.assert_not_called()

    # ---------------- reading the server ----------------

    def test_refused_read_is_reported_and_creates_nothing(self):
        """A read the array refuses is not taken for an absent server"""
        blade = Mock()
        blade.get_servers.return_value = _response(
            403, message="Operation not permitted."
        )

        module = _run_main(_base_params(dns=["mydns"]), blade)

        blade.post_servers.assert_not_called()
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once()
        assert module.fail_json.call_args[1]["msg"] == (
            "Failed to read server myserver. Error: Operation not permitted."
        )

    def test_refused_read_fails_state_absent_in_check_mode(self):
        """A failed read is not reported as a server that is already gone"""
        blade = Mock()
        blade.get_servers.return_value = _response(500, message="Internal error.")

        module = _run_main(_base_params(state="absent"), blade, check_mode=True)

        blade.delete_servers.assert_not_called()
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once()
        assert module.fail_json.call_args[1]["msg"] == (
            "Failed to read server myserver. Error: Internal error."
        )

    def test_answer_without_a_server_means_absent(self):
        """Should the array answer 200 and list no server, the server is
        absent and is created"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [])
        blade.post_servers.return_value = _response(200)

        module = _run_main(_base_params(), blade)

        blade.post_servers.assert_called_once()
        blade.patch_servers.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_reads_the_server_once(self):
        """The update works on the server the first read returned"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server()])

        module = _run_main(_base_params(dns=["management"]), blade)

        blade.get_servers.assert_called_once_with(names=["myserver"])
        assert module.exit_json.call_args[1]["changed"] is False

    # ---------------- directory_service ----------------

    def test_directory_service_matching_is_unchanged(self):
        """Naming the directory service of the server sends nothing"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server()])

        module = _run_main(_base_params(directory_service=["myserver_nfs"]), blade)

        blade.patch_servers.assert_not_called()
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_directory_service_in_another_case_is_unchanged(self):
        """The array matches names whatever their case, so does the module"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server()])

        module = _run_main(_base_params(directory_service=["MyServer_NFS"]), blade)

        blade.patch_servers.assert_not_called()
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_directory_service_bare_name_on_realm_server_is_unchanged(self):
        """On a server in a realm a name without a realm is compared in the
        realm of the server"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_realm_server()])

        module = _run_main(
            _base_params(name="rzaudit::srv", directory_service=["srv_nfs"]), blade
        )

        blade.patch_servers.assert_not_called()
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_directory_service_qualified_name_on_realm_server_is_unchanged(self):
        """The full name of the directory service of a realm server matches"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_realm_server()])

        module = _run_main(
            _base_params(name="rzaudit::srv", directory_service=["rzaudit::srv_nfs"]),
            blade,
        )

        blade.patch_servers.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_directory_service_difference_fails_and_sends_nothing(self):
        """Another name is refused: the array would accept and ignore it"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server()])
        blade.patch_servers.return_value = _response(200)

        module = _run_main(_base_params(directory_service=["other_nfs"]), blade)

        blade.patch_servers.assert_not_called()
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert msg.startswith(
            "The directory services of server myserver are myserver_nfs, not "
            "other_nfs."
        )
        assert "cannot be changed with purefb_server" in msg

    def test_directory_service_difference_fails_in_check_mode(self):
        """Check mode predicts the refusal instead of a change"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server()])

        module = _run_main(
            _base_params(directory_service=["other_nfs"]), blade, check_mode=True
        )

        blade.patch_servers.assert_not_called()
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once()
        assert "not other_nfs." in module.fail_json.call_args[1]["msg"]

    def test_directory_service_empty_list_fails(self):
        """An empty list is not what the server has, and is never sent"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server()])

        module = _run_main(_base_params(directory_service=[]), blade)

        blade.patch_servers.assert_not_called()
        module.fail_json.assert_called_once()
        assert "are myserver_nfs, not none." in module.fail_json.call_args[1]["msg"]

    def test_directory_service_extra_name_fails(self):
        """The whole list is compared, not only its first name"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server()])

        module = _run_main(
            _base_params(directory_service=["myserver_nfs", "nfs"]), blade
        )

        blade.patch_servers.assert_not_called()
        module.fail_json.assert_called_once()
        assert "not myserver_nfs, nfs." in module.fail_json.call_args[1]["msg"]

    def test_directory_service_of_another_realm_fails_on_realm_server(self):
        """A name in another realm is not completed with the realm of the
        server"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_realm_server()])

        module = _run_main(
            _base_params(name="rzaudit::srv", directory_service=["other::srv_nfs"]),
            blade,
        )

        blade.patch_servers.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "are rzaudit::srv_nfs, not other::srv_nfs." in msg

    def test_directory_service_realm_name_fails_on_array_server(self):
        """An array-level server does not have the directory service of its
        namesake in a realm"""
        blade = Mock()
        blade.get_servers.return_value = _response(
            200, [_server(directory_services=("srv_nfs",), name="srv")]
        )

        module = _run_main(
            _base_params(name="srv", directory_service=["rzaudit::srv_nfs"]), blade
        )

        blade.patch_servers.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "are srv_nfs, not rzaudit::srv_nfs." in msg

    def test_directory_service_difference_fails_before_the_dns_change(self):
        """The refusal is decided before any other change is sent"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server()])
        blade.patch_servers.return_value = _response(200)

        module = _run_main(
            _base_params(dns=["mydns"], directory_service=["other_nfs"]), blade
        )

        blade.patch_servers.assert_not_called()
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once()

    @patch("plugins.modules.purefb_server.Server")
    def test_directory_service_is_not_sent_with_a_dns_change(self, mock_server):
        """A matching directory_service next to a DNS change sends the DNS
        only"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server()])
        blade.patch_servers.return_value = _response(200)

        module = _run_main(
            _base_params(dns=["mydns"], directory_service=["myserver_nfs"]), blade
        )

        blade.patch_servers.assert_called_once()
        mock_server.assert_called_once()
        assert list(mock_server.call_args[1]) == ["dns"]
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_server.ServerPost")
    def test_create_does_not_send_directory_services(self, mock_server_post):
        """The array creates the directory service itself: the request
        names it in create_ds only"""
        blade = Mock()
        blade.get_servers.return_value = _absent()
        blade.post_servers.return_value = _response(200)

        module = _run_main(
            _base_params(dns=["mydns"], directory_service=["myserver_nfs"]), blade
        )

        blade.post_servers.assert_called_once()
        assert list(mock_server_post.call_args[1]) == ["dns"]
        assert blade.post_servers.call_args[1]["create_ds"] == "myserver_nfs"
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_server.ServerPost")
    def test_create_realm_server_accepts_bare_directory_service(self, mock_server_post):
        """A new server in a realm is created with realm::server_nfs, which a
        name without a realm stands for"""
        blade = Mock()
        blade.get_servers.return_value = _absent()
        blade.post_servers.return_value = _response(200)

        module = _run_main(
            _base_params(
                name="rzaudit::srv",
                dns=["rzaudit::dns1"],
                directory_service=["srv_nfs"],
            ),
            blade,
        )

        module.fail_json.assert_not_called()
        assert list(mock_server_post.call_args[1]) == ["dns"]
        assert blade.post_servers.call_args[1]["create_ds"] == "rzaudit::srv_nfs"
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_with_another_directory_service_is_refused(self):
        """A server cannot be created with a directory service other than
        its own, so nothing is created"""
        blade = Mock()
        blade.get_servers.return_value = _absent()
        blade.post_servers.return_value = _response(200)

        module = _run_main(_base_params(directory_service=["nfs"]), blade)

        blade.post_servers.assert_not_called()
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once()
        assert module.fail_json.call_args[1]["msg"].startswith(
            "Server myserver is created with the directory service myserver_nfs, "
            "not nfs."
        )

    def test_create_with_another_directory_service_is_refused_in_check_mode(self):
        """Check mode predicts the refusal of the create"""
        blade = Mock()
        blade.get_servers.return_value = _absent()

        module = _run_main(
            _base_params(directory_service=["nfs"]), blade, check_mode=True
        )

        blade.post_servers.assert_not_called()
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once()

    # ---------------- references of a server in a realm ----------------

    def test_realm_server_dns_without_realm_gets_the_rule(self):
        """The array says the DNS does not exist; the module adds what a
        server in a realm can use"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_realm_server()])
        blade.patch_servers.return_value = _response(400, message="DNS does not exist.")

        module = _run_main(_base_params(name="rzaudit::srv", dns=["mydns"]), blade)

        msg = module.fail_json.call_args[1]["msg"]
        assert msg.startswith(
            "Failed to update DNS config for server rzaudit::srv. Error: DNS "
            "does not exist. A server in realm rzaudit can only use a DNS "
            "configuration of that realm, named rzaudit::<name>"
        )
        assert "shared with the realm through purefb_resource_access." in msg
        assert "local directory service" not in msg

    def test_realm_server_dns_of_another_realm_gets_the_rule(self):
        """A DNS configuration named in another realm gets the same rule"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_realm_server()])
        blade.patch_servers.return_value = _response(
            400, message="Cannot modify server. DNS is not accessible to the server."
        )

        module = _run_main(
            _base_params(name="rzaudit::srv", dns=["other::dns1"]), blade
        )

        msg = module.fail_json.call_args[1]["msg"]
        assert "DNS is not accessible to the server. A server in realm rzaudit" in msg

    def test_realm_server_dns_realm_in_another_case_gets_the_rule(self):
        """The realm of a DNS configuration is given as the array reports it"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_realm_server()])
        blade.patch_servers.return_value = _response(
            400, message="Cannot modify server. DNS is not accessible to the server."
        )

        module = _run_main(
            _base_params(name="rzaudit::srv", dns=["RZAUDIT::dns2"]), blade
        )

        msg = module.fail_json.call_args[1]["msg"]
        assert "with the realm in the case the array reports it" in msg

    def test_realm_server_dns_in_its_realm_gets_no_rule(self):
        """A reference that is named in the realm fails for another reason"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_realm_server()])
        blade.patch_servers.return_value = _response(400, message="DNS does not exist.")

        module = _run_main(
            _base_params(name="rzaudit::srv", dns=["rzaudit::nodns"]), blade
        )

        assert module.fail_json.call_args[1]["msg"] == (
            "Failed to update DNS config for server rzaudit::srv. Error: DNS "
            "does not exist."
        )

    def test_realm_of_the_rule_is_the_stored_one(self):
        """The realm of the server is read from the name the array returned,
        not from the spelling of the task"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_realm_server()])
        blade.patch_servers.return_value = _response(400, message="DNS does not exist.")

        module = _run_main(
            _base_params(name="RZAUDIT::SRV", dns=["rzaudit::nodns"]), blade
        )

        assert module.fail_json.call_args[1]["msg"] == (
            "Failed to update DNS config for server RZAUDIT::SRV. Error: DNS "
            "does not exist."
        )

    def test_array_server_dns_failure_gets_no_rule(self):
        """Array-level servers keep the message of the array as it is"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server()])
        blade.patch_servers.return_value = _response(400, message="DNS does not exist.")

        module = _run_main(_base_params(dns=["nodns"]), blade)

        assert module.fail_json.call_args[1]["msg"] == (
            "Failed to update DNS config for server myserver. Error: DNS does "
            "not exist."
        )

    def test_realm_server_local_ds_without_realm_gets_the_rule(self):
        """The local directory service of a realm server is in its realm"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_realm_server()])
        blade.patch_servers.return_value = _response(
            400,
            message="Cannot update server. Local directory service is not "
            "accessible to the server.",
        )

        module = _run_main(
            _base_params(name="rzaudit::srv", local_directory_service="lds1"), blade
        )

        msg = module.fail_json.call_args[1]["msg"]
        assert msg.startswith(
            "Failed to update local directory service for server rzaudit::srv. "
            "Error: Cannot update server. Local directory service is not "
            "accessible to the server. A server in realm rzaudit can only use "
            "a local directory service of that realm, named rzaudit::lds1."
        )
        assert "DNS configuration" not in msg

    def test_realm_server_local_ds_in_its_realm_gets_no_rule(self):
        """A local directory service named in the realm fails as the array
        says"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_realm_server()])
        blade.patch_servers.return_value = _response(
            400, message="Local directory service does not exist."
        )

        module = _run_main(
            _base_params(name="rzaudit::srv", local_directory_service="rzaudit::nolds"),
            blade,
        )

        assert module.fail_json.call_args[1]["msg"] == (
            "Failed to update local directory service for server rzaudit::srv. "
            "Error: Local directory service does not exist."
        )

    def test_realm_server_failed_clear_gets_no_rule(self):
        """Clearing the local directory service names no reference"""
        blade = Mock()
        blade.get_servers.return_value = _response(
            200, [_realm_server(lds="rzaudit::lds1")]
        )
        blade.patch_servers.return_value = _response(400, message="Not now.")

        module = _run_main(
            _base_params(name="rzaudit::srv", local_directory_service=""), blade
        )

        assert module.fail_json.call_args[1]["msg"] == (
            "Failed to update local directory service for server rzaudit::srv. "
            "Error: Not now."
        )

    def test_create_realm_server_without_dns_gets_the_rule(self):
        """A new server in a realm needs a DNS configuration: the module adds
        which ones it can use"""
        blade = Mock()
        blade.get_servers.return_value = _absent()
        blade.post_servers.return_value = _response(
            400, message="DNS is required for servers inside a realm."
        )

        module = _run_main(_base_params(name="rzaudit::srv"), blade)

        msg = module.fail_json.call_args[1]["msg"]
        assert msg.startswith(
            "Failed to add server rzaudit::srv. Error: DNS is required for "
            "servers inside a realm. A server in realm rzaudit can only use a "
            "DNS configuration of that realm"
        )
        assert "purefb_resource_access" in msg

    def test_create_realm_server_with_bare_create_lds_gets_the_rule(self):
        """create_local_directory_service of a realm server carries the realm"""
        blade = Mock()
        blade.get_servers.return_value = _absent()
        blade.post_servers.return_value = _response(
            400,
            message="Cannot create server. Local directory service is not "
            "accessible to the server.",
        )

        module = _run_main(
            _base_params(
                name="rzaudit::srv",
                dns=["rzaudit::dns1"],
                create_local_directory_service="lds2",
            ),
            blade,
        )

        msg = module.fail_json.call_args[1]["msg"]
        assert msg.endswith(
            "accessible to the server. A server in realm rzaudit can only use "
            "a local directory service of that realm, named rzaudit::lds2."
        )
        assert "DNS configuration" not in msg

    def test_shared_dns_gets_no_rule_when_the_local_ds_is_refused(self):
        """An array-level DNS configuration shared with the realm is a valid
        reference: a refusal of the local directory service says nothing
        about it"""
        blade = Mock()
        blade.get_servers.return_value = _absent()
        blade.post_servers.return_value = _response(
            400,
            message="Cannot create server. Local directory service is not "
            "accessible to the server.",
        )

        module = _run_main(
            _base_params(
                name="rzaudit::srv",
                dns=["shareddns"],
                create_local_directory_service="lds2",
            ),
            blade,
        )

        assert module.fail_json.call_args[1]["msg"] == (
            "Failed to add server rzaudit::srv. Error: Cannot create server. "
            "Local directory service is not accessible to the server. A server "
            "in realm rzaudit can only use a local directory service of that "
            "realm, named rzaudit::lds2."
        )

    def test_refused_dns_gets_no_local_ds_rule(self):
        """A refusal of the DNS configuration gets the DNS rule only"""
        blade = Mock()
        blade.get_servers.return_value = _absent()
        blade.post_servers.return_value = _response(400, message="DNS does not exist.")

        module = _run_main(
            _base_params(
                name="rzaudit::srv", dns=["mydns"], local_directory_service="lds1"
            ),
            blade,
        )

        msg = module.fail_json.call_args[1]["msg"]
        assert "named rzaudit::<name>" in msg
        assert msg.endswith("through purefb_resource_access.")
        assert "local directory service" not in msg

    def test_other_refusal_of_a_realm_server_gets_no_rule(self):
        """A message about neither kind of reference stays as it is"""
        blade = Mock()
        blade.get_servers.return_value = _absent()
        blade.post_servers.return_value = _response(
            400, message="Realm does not exist."
        )

        module = _run_main(
            _base_params(
                name="norealm::srv", dns=["mydns"], local_directory_service="lds1"
            ),
            blade,
        )

        assert module.fail_json.call_args[1]["msg"] == (
            "Failed to add server norealm::srv. Error: Realm does not exist."
        )

    def test_create_array_server_failure_gets_no_rule(self):
        """An array-level create fails with the message of the array alone"""
        blade = Mock()
        blade.get_servers.return_value = _absent()
        blade.post_servers.return_value = _response(400, message="DNS does not exist.")

        module = _run_main(
            _base_params(dns=["nodns"], local_directory_service="lds1"), blade
        )

        assert module.fail_json.call_args[1]["msg"] == (
            "Failed to add server myserver. Error: DNS does not exist."
        )

    # ---------------- letter case ----------------

    def test_update_dns_in_another_case_is_noop(self):
        """The array stores the name of the DNS configuration in its own
        case; another case in the task is not a change"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server()])

        module = _run_main(_base_params(dns=["MANAGEMENT"]), blade)

        blade.patch_servers.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_lds_in_another_case_is_noop(self):
        """The attached local directory service is matched whatever the case"""
        blade = Mock()
        blade.get_servers.return_value = _response(
            200, [_realm_server(lds="rzaudit::lds1")]
        )

        module = _run_main(
            _base_params(name="rzaudit::srv", local_directory_service="rzaudit::LDS1"),
            blade,
        )

        blade.patch_servers.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_create_lds_in_another_case_is_idempotent(self):
        """create_local_directory_service on an existing server accepts the
        attached local directory service whatever the case"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server(lds="myserver_local")])

        module = _run_main(
            _base_params(create_local_directory_service="MyServer_Local"), blade
        )

        module.fail_json.assert_not_called()
        blade.patch_servers.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_clears_attached_lds(self):
        """An empty string still clears the attached local directory service"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server(lds="myserver_local")])
        blade.patch_servers.return_value = _response(200)

        module = _run_main(_base_params(local_directory_service=""), blade)

        blade.patch_servers.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_clear_of_unset_lds_is_noop(self):
        """Clearing a local directory service that is not set sends nothing"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server()])

        module = _run_main(_base_params(local_directory_service=""), blade)

        blade.patch_servers.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False
