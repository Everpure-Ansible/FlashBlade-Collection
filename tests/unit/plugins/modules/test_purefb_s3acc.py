# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_s3acc module."""

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

from plugins.modules.purefb_s3acc import (
    main,
    _context_kwargs,
    _requested_export_servers,
    _current_export_servers,
    _check_account_exports,
)
from plugins.module_utils.version import LooseVersion as RealLooseVersion


def _base_params(**overrides):
    params = {
        "name": "acme",
        "state": "present",
        "quota": None,
        "default_quota": None,
        "hard_limit": None,
        "default_hard_limit": None,
        "block_new_public_policies": None,
        "block_public_access": None,
        "account_exports": None,
        "context": "",
    }
    params.update(overrides)
    return params


def _module(params, check_mode=False):
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.params = params
    module.check_mode = check_mode
    return module


def _response(status_code=200, items=None):
    response = Mock()
    response.status_code = status_code
    response.items = items if items is not None else []
    return response


def _account():
    """An account whose settings match a module call that sets no quota option."""
    account = Mock()
    account.name = "acme"
    account.quota_limit = None
    account.hard_limit_enabled = False
    account.bucket_defaults.quota_limit = None
    account.bucket_defaults.hard_limit_enabled = False
    account.public_access_config.block_new_public_policies = False
    account.public_access_config.block_public_access = False
    return account


def _export(server):
    export = Mock()
    export.name = "{0}::acme".format(server)
    export.server.name = server
    return export


def _blade(account=None, exports=None):
    """A blade where the account exists (or not) and has the given exports."""
    blade = Mock()
    if account is None:
        blade.get_object_store_accounts.return_value = _response(400)
    else:
        blade.get_object_store_accounts.return_value = _response(200, [account])
    blade.get_object_store_account_exports.return_value = _response(
        200, [_export(server) for server in (exports or [])]
    )
    blade.get_fleets.return_value = _response(200, [])
    blade.post_object_store_accounts.return_value = _response(200)
    blade.patch_object_store_accounts.return_value = _response(200)
    blade.delete_object_store_accounts.return_value = _response(200)
    blade.get_object_store_users.return_value = _response(200, [])
    return blade


def _run():
    try:
        main()
    except SystemExit:
        pass


class TestPurefbS3acc:
    """Test cases for purefb_s3acc module"""

    # ---------------- helper-function unit tests ----------------

    def test_context_kwargs_returns_empty_without_context(self):
        module = Mock()
        module.params = {"context": ""}
        assert _context_kwargs(module) == {}

    def test_context_kwargs_returns_kwargs_when_set(self):
        module = Mock()
        module.params = {"context": "peer1"}
        assert _context_kwargs(module) == {"context_names": ["peer1"]}

    def test_requested_export_servers_none_when_unset(self):
        module = Mock()
        module.params = {"account_exports": None}
        assert _requested_export_servers(module) is None

    def test_requested_export_servers_empty_list(self):
        module = Mock()
        module.params = {"account_exports": []}
        assert _requested_export_servers(module) == []

    def test_requested_export_servers_names(self):
        module = Mock()
        module.params = {"account_exports": [{"server": "fb-02"}, {"server": "fb-01"}]}
        assert _requested_export_servers(module) == ["fb-02", "fb-01"]

    def test_current_export_servers_sorted_and_filtered_by_account(self):
        module = Mock()
        module.params = {"name": "acme", "context": ""}
        blade = _blade(account=_account(), exports=["fb-02", "fb-01"])

        assert _current_export_servers(module, blade) == ["fb-01", "fb-02"]
        blade.get_object_store_account_exports.assert_called_once_with(
            filter="member.name='acme'"
        )

    def test_current_export_servers_passes_context(self):
        module = Mock()
        module.params = {"name": "acme", "context": "peer1"}
        blade = _blade(account=_account(), exports=["_array_server"])

        assert _current_export_servers(module, blade) == ["_array_server"]
        blade.get_object_store_account_exports.assert_called_once_with(
            filter="member.name='acme'", context_names=["peer1"]
        )

    def test_current_export_servers_fails_on_api_error(self):
        module = Mock()
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = {"name": "acme", "context": ""}
        blade = Mock()
        blade.get_object_store_account_exports.return_value = _response(400)

        try:
            _current_export_servers(module, blade)
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "Failed to get exports" in module.fail_json.call_args[1]["msg"]

    def test_check_account_exports_skips_when_unset(self):
        module = Mock()
        module.params = {"name": "acme", "context": "", "account_exports": None}
        blade = Mock()

        _check_account_exports(module, blade)

        blade.get_object_store_account_exports.assert_not_called()
        module.warn.assert_not_called()

    def test_check_account_exports_silent_when_equal(self):
        module = Mock()
        module.params = {
            "name": "acme",
            "context": "",
            "account_exports": [{"server": "fb-01"}, {"server": "_array_server"}],
        }
        blade = _blade(account=_account(), exports=["_array_server", "fb-01"])

        _check_account_exports(module, blade)

        module.warn.assert_not_called()

    def test_check_account_exports_warns_on_difference(self):
        module = Mock()
        module.params = {"name": "acme", "context": "", "account_exports": []}
        blade = _blade(account=_account(), exports=["_array_server"])

        _check_account_exports(module, blade)

        module.warn.assert_called_once()
        message = module.warn.call_args[0][0]
        assert "purefb_s3acc_export" in message
        assert "_array_server" in message
        assert "no server" in message

    # ---------------- main() create flows ----------------

    @patch("plugins.modules.purefb_s3acc.ServerForAccountExport")
    @patch("plugins.modules.purefb_s3acc.Reference")
    @patch("plugins.modules.purefb_s3acc.ObjectStoreAccountPost")
    @patch("plugins.modules.purefb_s3acc.get_system")
    @patch("plugins.modules.purefb_s3acc.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_s3acc.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_s3acc.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def test_main_creates_account_without_export(
        self, mock_ansible_module, mock_get_system, mock_post_model, mock_ref, mock_sfe
    ):
        """account_exports: [] sends an empty export list in the POST body"""
        module = _module(_base_params(account_exports=[]))
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run()

        blade.post_object_store_accounts.assert_called_once()
        call_kwargs = blade.post_object_store_accounts.call_args[1]
        assert call_kwargs["names"] == ["acme"]
        assert "context_names" not in call_kwargs
        assert call_kwargs["object_store_account"] is mock_post_model.return_value
        mock_post_model.assert_called_once_with(account_exports=[])
        mock_sfe.assert_not_called()
        mock_ref.assert_not_called()
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_s3acc.ServerForAccountExport")
    @patch("plugins.modules.purefb_s3acc.Reference")
    @patch("plugins.modules.purefb_s3acc.ObjectStoreAccountPost")
    @patch("plugins.modules.purefb_s3acc.get_system")
    @patch("plugins.modules.purefb_s3acc.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_s3acc.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_s3acc.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def test_main_creates_account_with_explicit_server(
        self, mock_ansible_module, mock_get_system, mock_post_model, mock_ref, mock_sfe
    ):
        """Each listed server becomes a ServerForAccountExport in the POST body"""
        module = _module(_base_params(account_exports=[{"server": "fb-01"}]))
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run()

        mock_ref.assert_called_once_with(name="fb-01")
        mock_sfe.assert_called_once_with(server=mock_ref.return_value)
        mock_post_model.assert_called_once_with(account_exports=[mock_sfe.return_value])
        call_kwargs = blade.post_object_store_accounts.call_args[1]
        assert call_kwargs["object_store_account"] is mock_post_model.return_value
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_s3acc.ObjectStoreAccountPost")
    @patch("plugins.modules.purefb_s3acc.get_system")
    @patch("plugins.modules.purefb_s3acc.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_s3acc.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_s3acc.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def test_main_creates_account_with_default_export_when_unset(
        self, mock_ansible_module, mock_get_system, mock_post_model
    ):
        """Without account_exports the POST carries no body (array default export)"""
        module = _module(_base_params())
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run()

        blade.post_object_store_accounts.assert_called_once_with(names=["acme"])
        mock_post_model.assert_not_called()
        blade.get_object_store_account_exports.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_s3acc.ObjectStoreAccountPost")
    @patch("plugins.modules.purefb_s3acc.get_system")
    @patch("plugins.modules.purefb_s3acc.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_s3acc.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_s3acc.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def test_main_creates_account_with_context(
        self, mock_ansible_module, mock_get_system, mock_post_model
    ):
        """A fleet context is forwarded alongside the export body"""
        module = _module(_base_params(account_exports=[], context="peer1"))
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run()

        call_kwargs = blade.post_object_store_accounts.call_args[1]
        assert call_kwargs["names"] == ["acme"]
        assert call_kwargs["context_names"] == ["peer1"]
        assert call_kwargs["object_store_account"] is mock_post_model.return_value

    @patch("plugins.modules.purefb_s3acc.get_system")
    @patch("plugins.modules.purefb_s3acc.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_s3acc.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_s3acc.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def test_main_create_check_mode_skips_post(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(_base_params(account_exports=[]), check_mode=True)
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run()

        blade.post_object_store_accounts.assert_not_called()
        blade.patch_object_store_accounts.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_s3acc.get_system")
    @patch("plugins.modules.purefb_s3acc.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_s3acc.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_s3acc.get_rest_api_version",
        Mock(return_value="2.19"),
    )
    def test_main_account_exports_rejected_on_old_api(
        self, mock_ansible_module, mock_get_system
    ):
        """REST below 2.20 fails before the account is even looked up"""
        module = _module(_base_params(account_exports=[]))
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run()

        module.fail_json.assert_called_once()
        assert "2.20" in module.fail_json.call_args[1]["msg"]
        blade.get_object_store_accounts.assert_not_called()
        blade.post_object_store_accounts.assert_not_called()

    @patch("plugins.modules.purefb_s3acc.get_system")
    @patch("plugins.modules.purefb_s3acc.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_s3acc.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_s3acc.get_rest_api_version",
        Mock(return_value="2.19"),
    )
    def test_main_old_api_without_account_exports_still_creates(
        self, mock_ansible_module, mock_get_system
    ):
        """The 2.20 gate only applies when account_exports is set"""
        module = _module(_base_params())
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run()

        module.fail_json.assert_not_called()
        blade.post_object_store_accounts.assert_called_once_with(names=["acme"])

    @patch("plugins.modules.purefb_s3acc.get_system")
    @patch("plugins.modules.purefb_s3acc.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_s3acc.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_s3acc.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def test_main_duplicate_servers_fail_before_write(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(
            _base_params(account_exports=[{"server": "fb-01"}, {"server": "fb-01"}])
        )
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run()

        module.fail_json.assert_called_once()
        assert "duplicate" in module.fail_json.call_args[1]["msg"]
        blade.post_object_store_accounts.assert_not_called()

    @patch("plugins.modules.purefb_s3acc.get_system")
    @patch("plugins.modules.purefb_s3acc.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc.HAS_PYPURECLIENT", False)
    @patch("plugins.modules.purefb_s3acc.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_s3acc.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def test_main_fails_when_sdk_missing_for_account_exports(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(_base_params(account_exports=[]))
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run()

        module.fail_json.assert_called_once()
        assert "py-pure-client" in module.fail_json.call_args[1]["msg"]
        blade.post_object_store_accounts.assert_not_called()

    @patch("plugins.modules.purefb_s3acc.ObjectStoreAccountPost")
    @patch("plugins.modules.purefb_s3acc.get_system")
    @patch("plugins.modules.purefb_s3acc.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_s3acc.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_s3acc.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def test_main_create_failure_calls_fail_json(
        self, mock_ansible_module, mock_get_system, mock_post_model
    ):
        module = _module(_base_params(account_exports=[]))
        mock_ansible_module.return_value = module
        blade = _blade()
        blade.post_object_store_accounts.return_value = _response(400)
        mock_get_system.return_value = blade

        _run()

        module.fail_json.assert_called_once()
        assert "creation failed" in module.fail_json.call_args[1]["msg"]
        blade.patch_object_store_accounts.assert_not_called()

    # ---------------- main() existing-account flows ----------------

    @patch("plugins.modules.purefb_s3acc.get_system")
    @patch("plugins.modules.purefb_s3acc.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_s3acc.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_s3acc.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def test_main_existing_account_matching_exports_is_silent(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(_base_params(account_exports=[{"server": "_array_server"}]))
        mock_ansible_module.return_value = module
        blade = _blade(account=_account(), exports=["_array_server"])
        mock_get_system.return_value = blade

        _run()

        module.warn.assert_not_called()
        blade.post_object_store_accounts.assert_not_called()
        blade.patch_object_store_accounts.assert_not_called()
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_s3acc.get_system")
    @patch("plugins.modules.purefb_s3acc.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_s3acc.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_s3acc.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def test_main_existing_account_different_exports_warns_without_change(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(_base_params(account_exports=[]))
        mock_ansible_module.return_value = module
        blade = _blade(account=_account(), exports=["_array_server"])
        mock_get_system.return_value = blade

        _run()

        module.warn.assert_called_once()
        assert "purefb_s3acc_export" in module.warn.call_args[0][0]
        blade.post_object_store_accounts.assert_not_called()
        blade.patch_object_store_accounts.assert_not_called()
        blade.delete_object_store_account_exports.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_s3acc.get_system")
    @patch("plugins.modules.purefb_s3acc.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_s3acc.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_s3acc.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def test_main_existing_account_without_option_skips_export_lookup(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(_base_params())
        mock_ansible_module.return_value = module
        blade = _blade(account=_account(), exports=["_array_server"])
        mock_get_system.return_value = blade

        _run()

        blade.get_object_store_account_exports.assert_not_called()
        module.warn.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_s3acc.get_system")
    @patch("plugins.modules.purefb_s3acc.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_s3acc.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_s3acc.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def test_main_deletes_existing_account(self, mock_ansible_module, mock_get_system):
        module = _module(_base_params(state="absent"))
        mock_ansible_module.return_value = module
        blade = _blade(account=_account(), exports=["_array_server"])
        mock_get_system.return_value = blade

        _run()

        blade.delete_object_store_accounts.assert_called_once_with(names=["acme"])
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_s3acc.get_system")
    @patch("plugins.modules.purefb_s3acc.AnsibleModule")
    @patch("plugins.modules.purefb_s3acc.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_s3acc.LooseVersion", RealLooseVersion)
    @patch(
        "plugins.modules.purefb_s3acc.get_rest_api_version",
        Mock(return_value="2.30"),
    )
    def test_main_absent_missing_account_is_noop(
        self, mock_ansible_module, mock_get_system
    ):
        module = _module(_base_params(state="absent", account_exports=[]))
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run()

        blade.delete_object_store_accounts.assert_not_called()
        blade.post_object_store_accounts.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False
