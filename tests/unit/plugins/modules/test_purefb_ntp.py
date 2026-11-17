# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_ntp module."""

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

from plugins.modules.purefb_ntp import (
    main,
    create_ntp,
    delete_ntp,
    _context_kwargs,
    _get_ntp_servers,
    CONTEXT_API_VERSION,
)

MEMBER = "fleet-member-2"
SERVERS = ["0.pool.ntp.org", "1.pool.ntp.org"]


def _fake_version(value):
    """Stand-in for LooseVersion: a comparable tuple of ints"""
    return tuple(int(part) for part in str(value).split("."))


def _dedupe(items):
    """Stand-in for remove_duplicates"""
    return list(dict.fromkeys(items))


def _base_params(**overrides):
    params = {
        "state": "present",
        "ntp_servers": list(SERVERS),
        "context": "",
    }
    params.update(overrides)
    return params


def _module(params, check_mode=False):
    module = Mock()
    module.params = params
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _arrays_response(servers, status_code=200):
    item = Mock()
    item.ntp_servers = servers
    response = Mock()
    response.status_code = status_code
    response.items = [item]
    return response


def _ok_response():
    response = Mock()
    response.status_code = 200
    return response


def _error_response():
    response = Mock()
    response.status_code = 400
    return response


class TestPurefbNtp:
    """Test cases for purefb_ntp module"""

    # ---------------- _context_kwargs ----------------

    def test_context_kwargs_empty_without_context(self):
        """No context means no extra kwargs"""
        module = _module(_base_params())
        assert _context_kwargs(module) == {}

    def test_context_kwargs_with_context(self):
        """A context is sent as a single-element context_names list"""
        module = _module(_base_params(context=MEMBER))
        assert _context_kwargs(module) == {"context_names": [MEMBER]}

    # ---------------- _get_ntp_servers ----------------

    def test_get_ntp_servers_without_context(self):
        """Read without context sends no context_names"""
        module = _module(_base_params())
        blade = Mock()
        blade.get_arrays.return_value = _arrays_response(SERVERS)

        assert _get_ntp_servers(module, blade) == SERVERS
        blade.get_arrays.assert_called_once_with()

    def test_get_ntp_servers_with_context(self):
        """Read with context sends context_names"""
        module = _module(_base_params(context=MEMBER))
        blade = Mock()
        blade.get_arrays.return_value = _arrays_response(SERVERS)

        assert _get_ntp_servers(module, blade) == SERVERS
        blade.get_arrays.assert_called_once_with(context_names=[MEMBER])

    def test_get_ntp_servers_none_is_empty_list(self):
        """An array with no NTP servers reports an empty list"""
        module = _module(_base_params())
        blade = Mock()
        blade.get_arrays.return_value = _arrays_response(None)

        assert _get_ntp_servers(module, blade) == []

    def test_get_ntp_servers_fails_on_api_error(self):
        """An unknown context (or any read error) fails cleanly"""
        module = _module(_base_params(context=MEMBER))
        blade = Mock()
        blade.get_arrays.return_value = _arrays_response(SERVERS, status_code=400)

        try:
            _get_ntp_servers(module, blade)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert (
            "Failed to read array NTP settings" in module.fail_json.call_args[1]["msg"]
        )

    def test_get_ntp_servers_fails_on_multiple_arrays(self):
        """A context that matches more than one array is refused"""
        module = _module(_base_params(context="fleet-1"))
        blade = Mock()
        response = _arrays_response(SERVERS)
        response.items = [Mock(), Mock()]
        blade.get_arrays.return_value = response

        try:
            _get_ntp_servers(module, blade)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "single fleet member" in msg
        assert "fleet-1" in msg
        assert "2 arrays" in msg

    # ---------------- delete_ntp ----------------

    @patch("plugins.modules.purefb_ntp.Array")
    def test_delete_ntp_clears_servers(self, mock_array_class):
        """Configured servers are cleared with an empty list"""
        module = _module(_base_params(state="absent"))
        blade = Mock()
        blade.get_arrays.return_value = _arrays_response(SERVERS)
        blade.patch_arrays.return_value = _ok_response()

        try:
            delete_ntp(module, blade)
        except SystemExit:
            pass

        mock_array_class.assert_called_once_with(ntp_servers=[])
        blade.patch_arrays.assert_called_once_with(array=mock_array_class.return_value)
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_ntp.Array")
    def test_delete_ntp_with_context(self, mock_array_class):
        """Read and write both carry the context"""
        module = _module(_base_params(state="absent", context=MEMBER))
        blade = Mock()
        blade.get_arrays.return_value = _arrays_response(SERVERS)
        blade.patch_arrays.return_value = _ok_response()

        try:
            delete_ntp(module, blade)
        except SystemExit:
            pass

        blade.get_arrays.assert_called_once_with(context_names=[MEMBER])
        blade.patch_arrays.assert_called_once_with(
            array=mock_array_class.return_value, context_names=[MEMBER]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_delete_ntp_check_mode(self):
        """Check mode reports the change without patching"""
        module = _module(_base_params(state="absent", context=MEMBER), check_mode=True)
        blade = Mock()
        blade.get_arrays.return_value = _arrays_response(SERVERS)

        try:
            delete_ntp(module, blade)
        except SystemExit:
            pass

        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_delete_ntp_nothing_configured(self):
        """No servers configured is a no-op"""
        module = _module(_base_params(state="absent"))
        blade = Mock()
        blade.get_arrays.return_value = _arrays_response([])

        try:
            delete_ntp(module, blade)
        except SystemExit:
            pass

        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_ntp.Array")
    def test_delete_ntp_api_error(self, mock_array_class):
        """A failed PATCH fails the module"""
        module = _module(_base_params(state="absent"))
        blade = Mock()
        blade.get_arrays.return_value = _arrays_response(SERVERS)
        blade.patch_arrays.return_value = _error_response()

        try:
            delete_ntp(module, blade)
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "Deletion of NTP servers failed" in module.fail_json.call_args[1]["msg"]

    # ---------------- create_ntp ----------------

    @patch("plugins.modules.purefb_ntp.Array")
    def test_create_ntp_sets_first_four(self, mock_array_class):
        """Only the first four servers are sent, without context_names"""
        servers = ["s1", "s2", "s3", "s4", "s5"]
        module = _module(_base_params(ntp_servers=servers))
        blade = Mock()
        blade.patch_arrays.return_value = _ok_response()

        try:
            create_ntp(module, blade)
        except SystemExit:
            pass

        mock_array_class.assert_called_once_with(ntp_servers=["s1", "s2", "s3", "s4"])
        blade.patch_arrays.assert_called_once_with(array=mock_array_class.return_value)
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_ntp.Array")
    def test_create_ntp_with_context(self, mock_array_class):
        """The PATCH carries context_names when a context is set"""
        module = _module(_base_params(context=MEMBER))
        blade = Mock()
        blade.patch_arrays.return_value = _ok_response()

        try:
            create_ntp(module, blade)
        except SystemExit:
            pass

        mock_array_class.assert_called_once_with(ntp_servers=SERVERS)
        blade.patch_arrays.assert_called_once_with(
            array=mock_array_class.return_value, context_names=[MEMBER]
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_ntp.Array")
    def test_create_ntp_default_server(self, mock_array_class):
        """An empty list falls back to the documented default server"""
        module = _module(_base_params(ntp_servers=[]))
        blade = Mock()
        blade.patch_arrays.return_value = _ok_response()

        try:
            create_ntp(module, blade)
        except SystemExit:
            pass

        mock_array_class.assert_called_once_with(ntp_servers=["0.pool.ntp.org"])
        module.exit_json.assert_called_once_with(changed=True)

    def test_create_ntp_check_mode(self):
        """Check mode reports the change without patching"""
        module = _module(_base_params(context=MEMBER), check_mode=True)
        blade = Mock()

        try:
            create_ntp(module, blade)
        except SystemExit:
            pass

        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_ntp.Array")
    def test_create_ntp_api_error(self, mock_array_class):
        """A failed PATCH fails the module"""
        module = _module(_base_params())
        blade = Mock()
        blade.patch_arrays.return_value = _error_response()

        try:
            create_ntp(module, blade)
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "Update of NTP servers failed" in module.fail_json.call_args[1]["msg"]

    # ---------------- main() flows ----------------

    @patch("plugins.modules.purefb_ntp.Array")
    @patch("plugins.modules.purefb_ntp.get_rest_api_version")
    @patch("plugins.modules.purefb_ntp.get_system")
    @patch("plugins.modules.purefb_ntp.AnsibleModule")
    @patch("plugins.modules.purefb_ntp.remove_duplicates", _dedupe)
    @patch("plugins.modules.purefb_ntp.LooseVersion", _fake_version)
    @patch("plugins.modules.purefb_ntp.HAS_PYPURECLIENT", True)
    def test_main_present_unchanged(
        self, mock_ansible_module, mock_get_system, mock_api_version, mock_array_class
    ):
        """Same servers in a different order is idempotent"""
        module = _module(_base_params(ntp_servers=list(reversed(SERVERS))))
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_arrays.return_value = _arrays_response(SERVERS)
        mock_get_system.return_value = blade
        mock_api_version.return_value = "2.30"

        try:
            main()
        except SystemExit:
            pass

        blade.get_arrays.assert_called_once_with()
        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_ntp.Array")
    @patch("plugins.modules.purefb_ntp.get_rest_api_version")
    @patch("plugins.modules.purefb_ntp.get_system")
    @patch("plugins.modules.purefb_ntp.AnsibleModule")
    @patch("plugins.modules.purefb_ntp.remove_duplicates", _dedupe)
    @patch("plugins.modules.purefb_ntp.LooseVersion", _fake_version)
    @patch("plugins.modules.purefb_ntp.HAS_PYPURECLIENT", True)
    def test_main_present_changes_servers(
        self, mock_ansible_module, mock_get_system, mock_api_version, mock_array_class
    ):
        """Different servers are patched, duplicates removed, no context_names"""
        module = _module(
            _base_params(
                ntp_servers=["2.pool.ntp.org", "2.pool.ntp.org", "3.pool.ntp.org"]
            )
        )
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_arrays.return_value = _arrays_response(SERVERS)
        blade.patch_arrays.return_value = _ok_response()
        mock_get_system.return_value = blade
        mock_api_version.return_value = "2.17"

        try:
            main()
        except SystemExit:
            pass

        mock_array_class.assert_called_once_with(
            ntp_servers=["2.pool.ntp.org", "3.pool.ntp.org"]
        )
        blade.patch_arrays.assert_called_once_with(array=mock_array_class.return_value)
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_ntp.Array")
    @patch("plugins.modules.purefb_ntp.get_rest_api_version")
    @patch("plugins.modules.purefb_ntp.get_system")
    @patch("plugins.modules.purefb_ntp.AnsibleModule")
    @patch("plugins.modules.purefb_ntp.remove_duplicates", _dedupe)
    @patch("plugins.modules.purefb_ntp.LooseVersion", _fake_version)
    @patch("plugins.modules.purefb_ntp.HAS_PYPURECLIENT", True)
    def test_main_present_with_context(
        self, mock_ansible_module, mock_get_system, mock_api_version, mock_array_class
    ):
        """At REST 2.30 the read and the write both carry the context"""
        module = _module(_base_params(ntp_servers=["2.pool.ntp.org"], context=MEMBER))
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_arrays.return_value = _arrays_response(SERVERS)
        blade.patch_arrays.return_value = _ok_response()
        mock_get_system.return_value = blade
        mock_api_version.return_value = "2.30"

        try:
            main()
        except SystemExit:
            pass

        blade.get_arrays.assert_called_once_with(context_names=[MEMBER])
        blade.patch_arrays.assert_called_once_with(
            array=mock_array_class.return_value, context_names=[MEMBER]
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_ntp.Array")
    @patch("plugins.modules.purefb_ntp.get_rest_api_version")
    @patch("plugins.modules.purefb_ntp.get_system")
    @patch("plugins.modules.purefb_ntp.AnsibleModule")
    @patch("plugins.modules.purefb_ntp.remove_duplicates", _dedupe)
    @patch("plugins.modules.purefb_ntp.LooseVersion", _fake_version)
    @patch("plugins.modules.purefb_ntp.HAS_PYPURECLIENT", True)
    def test_main_present_with_context_idempotent(
        self, mock_ansible_module, mock_get_system, mock_api_version, mock_array_class
    ):
        """A matching member configuration is read with context and left alone"""
        module = _module(_base_params(context=MEMBER))
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_arrays.return_value = _arrays_response(SERVERS)
        mock_get_system.return_value = blade
        mock_api_version.return_value = "2.30"

        try:
            main()
        except SystemExit:
            pass

        blade.get_arrays.assert_called_once_with(context_names=[MEMBER])
        blade.patch_arrays.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_ntp.Array")
    @patch("plugins.modules.purefb_ntp.get_rest_api_version")
    @patch("plugins.modules.purefb_ntp.get_system")
    @patch("plugins.modules.purefb_ntp.AnsibleModule")
    @patch("plugins.modules.purefb_ntp.remove_duplicates", _dedupe)
    @patch("plugins.modules.purefb_ntp.LooseVersion", _fake_version)
    @patch("plugins.modules.purefb_ntp.HAS_PYPURECLIENT", True)
    def test_main_absent_with_context(
        self, mock_ansible_module, mock_get_system, mock_api_version, mock_array_class
    ):
        """state=absent with context clears the member's servers"""
        module = _module(_base_params(state="absent", ntp_servers=None, context=MEMBER))
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_arrays.return_value = _arrays_response(SERVERS)
        blade.patch_arrays.return_value = _ok_response()
        mock_get_system.return_value = blade
        mock_api_version.return_value = "2.30"

        try:
            main()
        except SystemExit:
            pass

        blade.get_arrays.assert_called_once_with(context_names=[MEMBER])
        mock_array_class.assert_called_once_with(ntp_servers=[])
        blade.patch_arrays.assert_called_once_with(
            array=mock_array_class.return_value, context_names=[MEMBER]
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_ntp.get_rest_api_version")
    @patch("plugins.modules.purefb_ntp.get_system")
    @patch("plugins.modules.purefb_ntp.AnsibleModule")
    @patch("plugins.modules.purefb_ntp.remove_duplicates", _dedupe)
    @patch("plugins.modules.purefb_ntp.LooseVersion", _fake_version)
    @patch("plugins.modules.purefb_ntp.HAS_PYPURECLIENT", True)
    def test_main_context_fails_below_patch_gate(
        self, mock_ansible_module, mock_get_system, mock_api_version
    ):
        """A context on a REST 2.29 array fails before any read or write"""
        module = _module(_base_params(context=MEMBER))
        mock_ansible_module.return_value = module
        blade = Mock()
        mock_get_system.return_value = blade
        mock_api_version.return_value = "2.29"

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert CONTEXT_API_VERSION in msg
        assert "2.30" in msg
        assert "2.29" in msg
        blade.get_arrays.assert_not_called()
        blade.patch_arrays.assert_not_called()

    @patch("plugins.modules.purefb_ntp.get_rest_api_version")
    @patch("plugins.modules.purefb_ntp.get_system")
    @patch("plugins.modules.purefb_ntp.AnsibleModule")
    @patch("plugins.modules.purefb_ntp.remove_duplicates", _dedupe)
    @patch("plugins.modules.purefb_ntp.LooseVersion", _fake_version)
    @patch("plugins.modules.purefb_ntp.HAS_PYPURECLIENT", True)
    def test_main_context_gate_applies_in_check_mode(
        self, mock_ansible_module, mock_get_system, mock_api_version
    ):
        """The gate also fails check mode and state=absent on an old array"""
        module = _module(
            _base_params(state="absent", ntp_servers=None, context=MEMBER),
            check_mode=True,
        )
        mock_ansible_module.return_value = module
        blade = Mock()
        mock_get_system.return_value = blade
        mock_api_version.return_value = "2.22"

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        blade.get_arrays.assert_not_called()
        blade.patch_arrays.assert_not_called()

    @patch("plugins.modules.purefb_ntp.Array")
    @patch("plugins.modules.purefb_ntp.get_rest_api_version")
    @patch("plugins.modules.purefb_ntp.get_system")
    @patch("plugins.modules.purefb_ntp.AnsibleModule")
    @patch("plugins.modules.purefb_ntp.remove_duplicates", _dedupe)
    @patch("plugins.modules.purefb_ntp.LooseVersion", _fake_version)
    @patch("plugins.modules.purefb_ntp.HAS_PYPURECLIENT", True)
    def test_main_old_array_without_context_still_works(
        self, mock_ansible_module, mock_get_system, mock_api_version, mock_array_class
    ):
        """No context on an old array is untouched by the gate"""
        module = _module(_base_params(ntp_servers=["2.pool.ntp.org"]))
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_arrays.return_value = _arrays_response(SERVERS)
        blade.patch_arrays.return_value = _ok_response()
        mock_get_system.return_value = blade
        mock_api_version.return_value = "2.0"

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_not_called()
        blade.get_arrays.assert_called_once_with()
        blade.patch_arrays.assert_called_once_with(array=mock_array_class.return_value)
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_ntp.get_rest_api_version")
    @patch("plugins.modules.purefb_ntp.get_system")
    @patch("plugins.modules.purefb_ntp.AnsibleModule")
    @patch("plugins.modules.purefb_ntp.LooseVersion", _fake_version)
    @patch("plugins.modules.purefb_ntp.HAS_PYPURECLIENT", False)
    def test_main_fails_without_sdk(
        self, mock_ansible_module, mock_get_system, mock_api_version
    ):
        """Missing py-pure-client fails before any array call"""
        module = _module(_base_params())
        mock_ansible_module.return_value = module

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "py-pure-client" in module.fail_json.call_args[1]["msg"]
        mock_get_system.assert_not_called()
