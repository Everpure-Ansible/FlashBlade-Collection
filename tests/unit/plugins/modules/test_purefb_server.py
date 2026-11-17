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


def _response(status_code=200, items=None):
    res = Mock()
    res.status_code = status_code
    res.items = items if items is not None else []
    return res


def _ref(name):
    ref = Mock(spec=["name"])
    ref.name = name
    return ref


def _server(dns=("management",), directory_services=("myserver_nfs",), lds=None):
    """A Server as the SDK returns it from REST 2.24 onwards."""
    server = Mock(
        spec=["name", "created", "dns", "directory_services", "local_directory_service"]
    )
    server.name = "myserver"
    server.created = 1700000000000
    server.dns = [_ref(name) for name in dns]
    server.directory_services = [_ref(name) for name in directory_services]
    server.local_directory_service = _ref(lds) if lds else None
    return server


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
        blade.get_servers.return_value = _response(400)
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
        blade.get_servers.return_value = _response(400)
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
        blade.get_servers.return_value = _response(400)
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
        blade.get_servers.return_value = _response(400)
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
        blade.get_servers.return_value = _response(400)

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
        blade.get_servers.return_value = _response(400)
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
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server()])
        blade.delete_servers.return_value = _response(200)

        module = _run_main(_base_params(state="absent"), blade)

        blade.delete_servers.assert_called_once_with(
            names=["myserver"], cascade_delete="directory-services"
        )
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_nonexistent_is_noop(self):
        """Deleting a server that is already gone reports no change"""
        blade = Mock()
        blade.get_servers.return_value = _response(400)

        module = _run_main(_base_params(state="absent"), blade)

        blade.delete_servers.assert_not_called()
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_delete_check_mode_skips_call(self):
        """Check mode reports the delete without calling DELETE"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server()])

        module = _run_main(_base_params(state="absent"), blade, check_mode=True)

        blade.delete_servers.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_fails_on_api_error(self):
        """A failed DELETE surfaces as fail_json"""
        blade = Mock()
        blade.get_servers.return_value = _response(200, [_server()])
        blade.delete_servers.return_value = _response(400)

        module = _run_main(_base_params(state="absent"), blade)

        module.fail_json.assert_called_once()
        assert (
            "Failed to delete server myserver" in module.fail_json.call_args[1]["msg"]
        )

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
        blade.get_servers.return_value = _response(400)
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
        blade.get_servers.return_value = _response(400)
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
