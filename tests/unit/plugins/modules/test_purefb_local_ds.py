# Copyright: (c) 2026, Pure Storage Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_local_ds module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import re
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

import yaml

from plugins.modules.purefb_local_ds import (
    EXAMPLES,
    main,
    _get_lds,
    _find_attached_server,
    _context_kwargs,
)


def _base_params(**overrides):
    params = {
        "name": "myserver_local",
        "state": "present",
        "domain": None,
        "context": "",
    }
    params.update(overrides)
    return params


class TestPurefbLocalDs:
    """Test cases for purefb_local_ds module"""

    # ---------------- helper-function unit tests ----------------

    def test_context_kwargs_returns_empty_without_context(self):
        """_context_kwargs returns {} when no context is set"""
        module = Mock()
        module.params = {"context": ""}
        assert _context_kwargs(module) == {}

    def test_context_kwargs_returns_kwargs_when_set(self):
        """_context_kwargs returns context_names when a context is set"""
        module = Mock()
        module.params = {"context": "peer1"}
        assert _context_kwargs(module) == {"context_names": ["peer1"]}

    def test_get_lds_returns_first_item(self):
        """_get_lds returns the first item when present"""
        module = Mock()
        module.params = {"name": "myserver_local", "context": ""}

        lds = Mock()
        lds.name = "myserver_local"

        blade = Mock()
        response = Mock()
        response.status_code = 200
        response.items = [lds]
        blade.get_directory_services_local_directory_services.return_value = response

        assert _get_lds(module, blade) is lds
        blade.get_directory_services_local_directory_services.assert_called_once_with(
            names=["myserver_local"]
        )

    def test_get_lds_returns_none_when_empty(self):
        """_get_lds returns None when items is empty"""
        module = Mock()
        module.params = {"name": "myserver_local", "context": ""}

        blade = Mock()
        response = Mock()
        response.status_code = 200
        response.items = []
        blade.get_directory_services_local_directory_services.return_value = response

        assert _get_lds(module, blade) is None

    def test_get_lds_returns_none_on_error(self):
        """_get_lds returns None when status is non-200"""
        module = Mock()
        module.params = {"name": "myserver_local", "context": ""}

        blade = Mock()
        response = Mock()
        response.status_code = 400
        response.items = []
        blade.get_directory_services_local_directory_services.return_value = response

        assert _get_lds(module, blade) is None

    def test_find_attached_server_returns_name(self):
        """_find_attached_server returns server name when one is attached"""
        module = Mock()
        module.params = {"name": "myserver_local", "context": ""}

        server = Mock()
        server.name = "myserver"
        response = Mock()
        response.status_code = 200
        response.items = [server]

        blade = Mock()
        blade.get_servers.return_value = response

        assert _find_attached_server(module, blade) == "myserver"
        blade.get_servers.assert_called_once_with(
            filter="local_directory_service.name='myserver_local'"
        )

    def test_find_attached_server_returns_none_when_no_server(self):
        """_find_attached_server returns None when no server is attached"""
        module = Mock()
        module.params = {"name": "myserver_local", "context": ""}

        response = Mock()
        response.status_code = 200
        response.items = []

        blade = Mock()
        blade.get_servers.return_value = response

        assert _find_attached_server(module, blade) is None

    def test_find_attached_server_returns_none_on_error(self):
        """_find_attached_server returns None on API error"""
        module = Mock()
        module.params = {"name": "myserver_local", "context": ""}

        response = Mock()
        response.status_code = 400
        response.items = []

        blade = Mock()
        blade.get_servers.return_value = response

        assert _find_attached_server(module, blade) is None

    # ---------------- main() flows ----------------

    @patch("plugins.modules.purefb_local_ds.LooseVersion")
    @patch("plugins.modules.purefb_local_ds.LocalDirectoryServicePost")
    @patch("plugins.modules.purefb_local_ds.get_system")
    @patch("plugins.modules.purefb_local_ds.AnsibleModule")
    @patch("plugins.modules.purefb_local_ds.HAS_PYPURECLIENT", True)
    def test_main_creates_lds_with_domain(
        self, mock_ansible_module, mock_get_system, mock_lds_post, mock_loose_version
    ):
        """Test creating a new LDS with an explicit domain"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(domain="local")
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.17", "2.24"]
        mock_get_system.return_value = blade

        # LDS doesn't exist yet
        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        blade.get_directory_services_local_directory_services.return_value = (
            get_response
        )

        # Successful create
        post_response = Mock()
        post_response.status_code = 200
        post_response.items = []
        blade.post_directory_services_local_directory_services.return_value = (
            post_response
        )

        try:
            main()
        except SystemExit:
            pass

        blade.post_directory_services_local_directory_services.assert_called_once()
        call_kwargs = blade.post_directory_services_local_directory_services.call_args[
            1
        ]
        assert call_kwargs["names"] == ["myserver_local"]
        mock_lds_post.assert_called_once_with(domain="local")
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_local_ds.LooseVersion")
    @patch("plugins.modules.purefb_local_ds.LocalDirectoryServicePost")
    @patch("plugins.modules.purefb_local_ds.get_system")
    @patch("plugins.modules.purefb_local_ds.AnsibleModule")
    @patch("plugins.modules.purefb_local_ds.HAS_PYPURECLIENT", True)
    def test_main_creates_lds_without_domain(
        self, mock_ansible_module, mock_get_system, mock_lds_post, mock_loose_version
    ):
        """Test creating a new LDS without a domain (array default)"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params()
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        blade.get_directory_services_local_directory_services.return_value = (
            get_response
        )

        post_response = Mock()
        post_response.status_code = 200
        post_response.items = []
        blade.post_directory_services_local_directory_services.return_value = (
            post_response
        )

        try:
            main()
        except SystemExit:
            pass

        # domain omitted → body built with no arguments
        mock_lds_post.assert_called_once_with()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_local_ds.LooseVersion")
    @patch("plugins.modules.purefb_local_ds.get_system")
    @patch("plugins.modules.purefb_local_ds.AnsibleModule")
    @patch("plugins.modules.purefb_local_ds.HAS_PYPURECLIENT", True)
    def test_main_create_check_mode_skips_post(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test create reports changed but skips POST in check mode"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(domain="local")
        module.check_mode = True
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        blade.get_directory_services_local_directory_services.return_value = (
            get_response
        )

        try:
            main()
        except SystemExit:
            pass

        blade.post_directory_services_local_directory_services.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_local_ds.LooseVersion")
    @patch("plugins.modules.purefb_local_ds.get_system")
    @patch("plugins.modules.purefb_local_ds.AnsibleModule")
    @patch("plugins.modules.purefb_local_ds.HAS_PYPURECLIENT", True)
    def test_main_create_fails_on_api_error(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test create surfaces API error via fail_json"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(domain="local")
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        blade.get_directory_services_local_directory_services.return_value = (
            get_response
        )

        post_response = Mock()
        post_response.status_code = 400
        post_response.errors = []
        blade.post_directory_services_local_directory_services.return_value = (
            post_response
        )

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert (
            "Failed to create local directory service"
            in module.fail_json.call_args[1]["msg"]
        )

    @patch("plugins.modules.purefb_local_ds.LooseVersion")
    @patch("plugins.modules.purefb_local_ds.LocalDirectoryService")
    @patch("plugins.modules.purefb_local_ds.get_system")
    @patch("plugins.modules.purefb_local_ds.AnsibleModule")
    @patch("plugins.modules.purefb_local_ds.HAS_PYPURECLIENT", True)
    def test_main_updates_domain(
        self, mock_ansible_module, mock_get_system, mock_lds, mock_loose_version
    ):
        """Test PATCHing the domain of an existing LDS"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(domain="corp-local")
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "myserver_local"
        existing.domain = "local"
        existing.server = None
        existing.realms = []

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_directory_services.return_value = (
            get_response
        )

        patch_response = Mock()
        patch_response.status_code = 200
        patch_response.items = []
        blade.patch_directory_services_local_directory_services.return_value = (
            patch_response
        )

        try:
            main()
        except SystemExit:
            pass

        blade.patch_directory_services_local_directory_services.assert_called_once()
        mock_lds.assert_called_once_with(domain="corp-local")
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_local_ds.LooseVersion")
    @patch("plugins.modules.purefb_local_ds.get_system")
    @patch("plugins.modules.purefb_local_ds.AnsibleModule")
    @patch("plugins.modules.purefb_local_ds.HAS_PYPURECLIENT", True)
    def test_main_update_idempotent_when_domain_matches(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test update is a no-op when the domain already matches"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(domain="local")
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "myserver_local"
        existing.domain = "local"
        existing.server = None
        existing.realms = []

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_directory_services.return_value = (
            get_response
        )

        try:
            main()
        except SystemExit:
            pass

        blade.patch_directory_services_local_directory_services.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_local_ds.LooseVersion")
    @patch("plugins.modules.purefb_local_ds.get_system")
    @patch("plugins.modules.purefb_local_ds.AnsibleModule")
    @patch("plugins.modules.purefb_local_ds.HAS_PYPURECLIENT", True)
    def test_main_update_no_domain_is_noop(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test update is a no-op when domain param is omitted (never resets it)"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params()  # domain=None
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "myserver_local"
        existing.domain = "somedomain"
        existing.server = None
        existing.realms = []

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_directory_services.return_value = (
            get_response
        )

        try:
            main()
        except SystemExit:
            pass

        blade.patch_directory_services_local_directory_services.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_local_ds.LooseVersion")
    @patch("plugins.modules.purefb_local_ds.LocalDirectoryService")
    @patch("plugins.modules.purefb_local_ds.get_system")
    @patch("plugins.modules.purefb_local_ds.AnsibleModule")
    @patch("plugins.modules.purefb_local_ds.HAS_PYPURECLIENT", True)
    def test_main_update_warns_when_attached(
        self, mock_ansible_module, mock_get_system, mock_lds, mock_loose_version
    ):
        """Test update warns when patching domain on an LDS that is server-attached"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.warn = Mock()
        module.params = _base_params(domain="new.domain")
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        server = Mock()
        server.name = "myserver"
        existing = Mock()
        existing.name = "myserver_local"
        existing.domain = "local"
        existing.server = server
        existing.realms = []

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_directory_services.return_value = (
            get_response
        )

        patch_response = Mock()
        patch_response.status_code = 200
        patch_response.items = []
        blade.patch_directory_services_local_directory_services.return_value = (
            patch_response
        )

        try:
            main()
        except SystemExit:
            pass

        module.warn.assert_called_once()
        assert "myserver" in module.warn.call_args[0][0]
        blade.patch_directory_services_local_directory_services.assert_called_once()

    @patch("plugins.modules.purefb_local_ds.LooseVersion")
    @patch("plugins.modules.purefb_local_ds.LocalDirectoryService")
    @patch("plugins.modules.purefb_local_ds.get_system")
    @patch("plugins.modules.purefb_local_ds.AnsibleModule")
    @patch("plugins.modules.purefb_local_ds.HAS_PYPURECLIENT", True)
    def test_main_update_fails_with_attached_context_in_message(
        self, mock_ansible_module, mock_get_system, mock_lds, mock_loose_version
    ):
        """Test update failure mentions attached server name in error message"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.warn = Mock()
        module.params = _base_params(domain="new.domain")
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        server = Mock()
        server.name = "myserver"
        existing = Mock()
        existing.name = "myserver_local"
        existing.domain = "local"
        existing.server = server
        existing.realms = []

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_directory_services.return_value = (
            get_response
        )

        patch_response = Mock()
        patch_response.status_code = 400
        patch_response.errors = []
        blade.patch_directory_services_local_directory_services.return_value = (
            patch_response
        )

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "myserver" in msg
        assert "myserver_local" in msg

    @patch("plugins.modules.purefb_local_ds.LooseVersion")
    @patch("plugins.modules.purefb_local_ds.get_system")
    @patch("plugins.modules.purefb_local_ds.AnsibleModule")
    @patch("plugins.modules.purefb_local_ds.HAS_PYPURECLIENT", True)
    def test_main_deletes_lds(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test deleting an existing, detached LDS"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(state="absent")
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "myserver_local"

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_directory_services.return_value = (
            get_response
        )

        server_response = Mock()
        server_response.status_code = 200
        server_response.items = []
        blade.get_servers.return_value = server_response

        delete_response = Mock()
        delete_response.status_code = 200
        blade.delete_directory_services_local_directory_services.return_value = (
            delete_response
        )

        try:
            main()
        except SystemExit:
            pass

        blade.delete_directory_services_local_directory_services.assert_called_once_with(
            names=["myserver_local"]
        )
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_local_ds.LooseVersion")
    @patch("plugins.modules.purefb_local_ds.get_system")
    @patch("plugins.modules.purefb_local_ds.AnsibleModule")
    @patch("plugins.modules.purefb_local_ds.HAS_PYPURECLIENT", True)
    def test_main_delete_refused_when_attached(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test delete refuses when LDS is still attached to a server"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(state="absent")
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "myserver_local"

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_directory_services.return_value = (
            get_response
        )

        server = Mock()
        server.name = "myserver"
        server_response = Mock()
        server_response.status_code = 200
        server_response.items = [server]
        blade.get_servers.return_value = server_response

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "myserver" in msg
        assert "Detach" in msg or "detach" in msg
        blade.delete_directory_services_local_directory_services.assert_not_called()

    @patch("plugins.modules.purefb_local_ds.LooseVersion")
    @patch("plugins.modules.purefb_local_ds.get_system")
    @patch("plugins.modules.purefb_local_ds.AnsibleModule")
    @patch("plugins.modules.purefb_local_ds.HAS_PYPURECLIENT", True)
    def test_main_delete_nonexistent_is_noop(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test state=absent on a nonexistent LDS reports changed=False"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(state="absent", name="ghost")
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        blade.get_directory_services_local_directory_services.return_value = (
            get_response
        )

        try:
            main()
        except SystemExit:
            pass

        blade.delete_directory_services_local_directory_services.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_local_ds.LooseVersion")
    @patch("plugins.modules.purefb_local_ds.get_system")
    @patch("plugins.modules.purefb_local_ds.AnsibleModule")
    @patch("plugins.modules.purefb_local_ds.HAS_PYPURECLIENT", True)
    def test_main_delete_check_mode_skips_call(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test delete reports changed but skips the DELETE call in check mode"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(state="absent")
        module.check_mode = True
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "myserver_local"

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_directory_services.return_value = (
            get_response
        )

        server_response = Mock()
        server_response.status_code = 200
        server_response.items = []
        blade.get_servers.return_value = server_response

        try:
            main()
        except SystemExit:
            pass

        blade.delete_directory_services_local_directory_services.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_local_ds.LooseVersion")
    @patch("plugins.modules.purefb_local_ds.get_system")
    @patch("plugins.modules.purefb_local_ds.AnsibleModule")
    @patch("plugins.modules.purefb_local_ds.HAS_PYPURECLIENT", True)
    def test_main_fails_on_unsupported_api_version(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test failure when the array API version is older than MIN_REQUIRED_API_VERSION"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params()
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.17", "2.18", "2.19"]
        mock_get_system.return_value = blade

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "REST version not supported" in module.fail_json.call_args[1]["msg"]

    @patch("plugins.modules.purefb_local_ds.LooseVersion")
    @patch("plugins.modules.purefb_local_ds.get_system")
    @patch("plugins.modules.purefb_local_ds.AnsibleModule")
    @patch("plugins.modules.purefb_local_ds.HAS_PYPURECLIENT", False)
    def test_main_fails_without_sdk(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test failure when py-pure-client SDK is not installed"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params()
        module.check_mode = False
        mock_ansible_module.return_value = module

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "py-pure-client" in module.fail_json.call_args[1]["msg"]


# ---------------- realm names ----------------

REALM_LDS = "realm1::tenant_local"
REALM_SERVER = "realm1::tenant-srv"


def _reference(name):
    ref = Mock()
    ref.name = name
    return ref


def _lds(name, domain, server=None):
    """A local directory service as the array returns it"""
    lds = Mock()
    lds.name = name
    lds.domain = domain
    lds.server = _reference(server) if server else None
    lds.realms = [_reference(name.rpartition("::")[0])] if "::" in name else []
    return lds


def _response(items=None, status_code=200):
    res = Mock()
    res.status_code = status_code
    res.items = items if items is not None else []
    return res


@patch("plugins.modules.purefb_local_ds.LooseVersion")
@patch("plugins.modules.purefb_local_ds.LocalDirectoryService")
@patch("plugins.modules.purefb_local_ds.LocalDirectoryServicePost")
@patch("plugins.modules.purefb_local_ds.get_system")
@patch("plugins.modules.purefb_local_ds.AnsibleModule")
@patch("plugins.modules.purefb_local_ds.HAS_PYPURECLIENT", True)
def _run_main(
    mock_ansible_module,
    mock_get_system,
    mock_post_model,
    mock_patch_model,
    mock_loose_version,
    params=None,
    existing=None,
    servers=None,
    check_mode=False,
):
    """Run main() against a mocked array; return module, client and models"""
    mock_loose_version.return_value.__gt__ = Mock(return_value=False)
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.params = params
    module.check_mode = check_mode
    mock_ansible_module.return_value = module

    blade = Mock()
    blade.get_versions.return_value.items = ["2.24"]
    if not isinstance(existing, list):
        existing = [existing] if existing else []
    blade.get_directory_services_local_directory_services.return_value = _response(
        existing
    )
    blade.get_servers.return_value = _response(servers or [])
    blade.post_directory_services_local_directory_services.return_value = _response()
    blade.patch_directory_services_local_directory_services.return_value = _response()
    blade.delete_directory_services_local_directory_services.return_value = _response()
    mock_get_system.return_value = blade

    try:
        main()
    except SystemExit:
        pass
    return module, blade, mock_post_model, mock_patch_model


class TestPurefbLocalDsRealm:
    """A local directory service in a realm is addressed by its full name"""

    def test_get_lds_reads_the_realm_name_as_given(self):
        module = Mock()
        module.params = {"name": REALM_LDS, "context": ""}
        lds = _lds(REALM_LDS, "tenant1")
        blade = Mock()
        blade.get_directory_services_local_directory_services.return_value = _response(
            [lds]
        )

        assert _get_lds(module, blade) is lds
        blade.get_directory_services_local_directory_services.assert_called_once_with(
            names=[REALM_LDS]
        )

    def test_find_attached_server_filters_on_the_full_name(self):
        module = Mock()
        module.params = {"name": REALM_LDS, "context": ""}
        blade = Mock()
        blade.get_servers.return_value = _response([_reference(REALM_SERVER)])

        assert _find_attached_server(module, blade) == REALM_SERVER
        blade.get_servers.assert_called_once_with(
            filter="local_directory_service.name='realm1::tenant_local'"
        )

    def test_create_in_a_realm_sends_the_full_name(self):
        module, blade, post_model, _patch_model = _run_main(
            params=_base_params(name=REALM_LDS, domain="tenant1")
        )

        blade.get_directory_services_local_directory_services.assert_called_once_with(
            names=[REALM_LDS]
        )
        post = blade.post_directory_services_local_directory_services
        post.assert_called_once()
        assert post.call_args[1]["names"] == [REALM_LDS]
        post_model.assert_called_once_with(domain="tenant1")
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_in_a_realm_check_mode_sends_nothing(self):
        module, blade, _post_model, _patch_model = _run_main(
            params=_base_params(name=REALM_LDS, domain="tenant1"), check_mode=True
        )

        blade.post_directory_services_local_directory_services.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_domain_change_in_a_realm_sends_the_full_name(self):
        module, blade, _post_model, patch_model = _run_main(
            params=_base_params(name=REALM_LDS, domain="tenant2"),
            existing=_lds(REALM_LDS, "tenant1"),
        )

        patch_call = blade.patch_directory_services_local_directory_services
        patch_call.assert_called_once()
        assert patch_call.call_args[1]["names"] == [REALM_LDS]
        patch_model.assert_called_once_with(domain="tenant2")
        module.warn.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_domain_change_in_a_realm_warns_when_attached(self):
        module, blade, _post_model, _patch_model = _run_main(
            params=_base_params(name=REALM_LDS, domain="tenant2"),
            existing=_lds(REALM_LDS, "tenant1", server=REALM_SERVER),
        )

        module.warn.assert_called_once()
        assert REALM_SERVER in module.warn.call_args[0][0]
        blade.patch_directory_services_local_directory_services.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_realm_lds_unchanged_when_the_domain_matches(self):
        module, blade, _post_model, _patch_model = _run_main(
            params=_base_params(name=REALM_LDS, domain="tenant1"),
            existing=_lds(REALM_LDS, "tenant1"),
        )

        blade.patch_directory_services_local_directory_services.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_realm_lds_unchanged_when_the_domain_is_omitted(self):
        # the array defaulted the domain to the name without the realm
        module, blade, _post_model, _patch_model = _run_main(
            params=_base_params(name="realm1::tenant-local"),
            existing=_lds("realm1::tenant-local", "tenant-local"),
        )

        blade.patch_directory_services_local_directory_services.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_delete_in_a_realm_sends_the_full_name(self):
        module, blade, _post_model, _patch_model = _run_main(
            params=_base_params(name=REALM_LDS, state="absent"),
            existing=_lds(REALM_LDS, "tenant1"),
        )

        blade.get_servers.assert_called_once_with(
            filter="local_directory_service.name='realm1::tenant_local'"
        )
        blade.delete_directory_services_local_directory_services.assert_called_once_with(
            names=[REALM_LDS]
        )
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_in_a_realm_refused_while_attached(self):
        for check_mode in (False, True):
            module, blade, _post_model, _patch_model = _run_main(
                params=_base_params(name=REALM_LDS, state="absent"),
                existing=_lds(REALM_LDS, "tenant1", server=REALM_SERVER),
                servers=[_reference(REALM_SERVER)],
                check_mode=check_mode,
            )

            module.fail_json.assert_called_once()
            assert REALM_SERVER in module.fail_json.call_args[1]["msg"]
            blade.delete_directory_services_local_directory_services.assert_not_called()

    def test_bare_name_is_not_completed_with_a_realm(self):
        # the array-level namesake of a realm LDS is a different object
        module, blade, post_model, _patch_model = _run_main(
            params=_base_params(name="tenant_local", domain="tenant1")
        )

        blade.get_directory_services_local_directory_services.assert_called_once_with(
            names=["tenant_local"]
        )
        post = blade.post_directory_services_local_directory_services
        assert post.call_args[1]["names"] == ["tenant_local"]
        post_model.assert_called_once_with(domain="tenant1")
        assert module.exit_json.call_args[1]["changed"] is True


# ---------------- documented examples ----------------

# The array accepts a domain of at most 15 characters, alphanumerics and
# hyphens; without a domain it takes the first 15 characters of the name
# (without the realm) and refuses the create when they are no valid domain.
VALID_DOMAIN = re.compile(r"^[A-Za-z0-9-]{1,15}$")


def _example_tasks():
    """Arguments of every purefb_local_ds task in EXAMPLES, blocks included"""
    tasks = []
    pending = list(yaml.safe_load(EXAMPLES))
    while pending:
        task = pending.pop(0)
        pending.extend(task.get("block", []))
        if "everpure.flashblade.purefb_local_ds" in task:
            tasks.append(task["everpure.flashblade.purefb_local_ds"])
    return tasks


class TestPurefbLocalDsExamples:
    """The documented examples keep to what the array accepts"""

    def test_example_domains_are_valid(self):
        domains = [task["domain"] for task in _example_tasks() if "domain" in task]
        assert domains
        for domain in domains:
            assert VALID_DOMAIN.match(domain), domain

    def test_examples_without_a_domain_have_a_name_the_array_can_default(self):
        names = [
            task["name"]
            for task in _example_tasks()
            if "domain" not in task and task.get("state", "present") == "present"
        ]
        assert names
        for name in names:
            assert VALID_DOMAIN.match(name.rpartition("::")[2][:15]), name

    def test_examples_show_the_realm_form(self):
        realm_tasks = [task for task in _example_tasks() if "::" in task["name"]]
        assert realm_tasks
        for task in realm_tasks:
            realm, sep, leaf = task["name"].rpartition("::")
            assert realm and sep and leaf


# ---------------- one name per task ----------------


class TestPurefbLocalDsOneName:
    """The array reads a comma in a name as the separator of a list"""

    def _assert_refused(self, module, blade):
        module.fail_json.assert_called_once()
        assert "comma" in module.fail_json.call_args[1]["msg"]
        module.exit_json.assert_not_called()
        blade.get_directory_services_local_directory_services.assert_not_called()
        blade.get_servers.assert_not_called()
        blade.post_directory_services_local_directory_services.assert_not_called()
        blade.patch_directory_services_local_directory_services.assert_not_called()
        blade.delete_directory_services_local_directory_services.assert_not_called()

    def test_delete_of_two_names_refused_before_any_request(self):
        # the array answers the lookup with both; the server filter on the
        # text "lds-a,lds-b" matches no server although lds-a is attached
        for check_mode in (False, True):
            module, blade, _post_model, _patch_model = _run_main(
                params=_base_params(name="lds-a,lds-b", state="absent"),
                existing=[_lds("lds-a", "lds-a", server="srv-a"), _lds("lds-b", "b")],
                check_mode=check_mode,
            )

            self._assert_refused(module, blade)
            assert "lds-a,lds-b" in module.fail_json.call_args[1]["msg"]

    def test_domain_change_of_two_names_refused_before_any_request(self):
        for check_mode in (False, True):
            module, blade, _post_model, _patch_model = _run_main(
                params=_base_params(name="lds-b,lds-a", domain="corp-local"),
                existing=[_lds("lds-b", "b"), _lds("lds-a", "lds-a", server="srv-a")],
                check_mode=check_mode,
            )

            self._assert_refused(module, blade)

    def test_two_realm_names_refused_before_any_request(self):
        name = "tenant_local,{0}".format(REALM_LDS)
        for state in ("present", "absent"):
            module, blade, _post_model, _patch_model = _run_main(
                params=_base_params(name=name, state=state, domain="tenant1"),
                existing=[
                    _lds("tenant_local", "local"),
                    _lds(REALM_LDS, "tenant1", server=REALM_SERVER),
                ],
            )

            self._assert_refused(module, blade)

    def test_comma_name_refused_when_nothing_exists(self):
        module, blade, _post_model, _patch_model = _run_main(
            params=_base_params(name="lds-a,lds-b", domain="corp-local")
        )

        self._assert_refused(module, blade)

    def test_attached_domain_change_warning_does_not_say_refused(self):
        module, _blade, _post_model, _patch_model = _run_main(
            params=_base_params(name=REALM_LDS, domain="tenant2"),
            existing=_lds(REALM_LDS, "tenant1", server=REALM_SERVER),
        )

        text = module.warn.call_args[0][0]
        assert REALM_LDS in text and REALM_SERVER in text
        assert "only permitted when detached" not in text
        assert "may reject" in text
