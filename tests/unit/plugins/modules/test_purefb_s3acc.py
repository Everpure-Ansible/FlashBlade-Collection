# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_s3acc module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from unittest.mock import Mock, call, patch, MagicMock

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

import plugins.modules.purefb_s3acc as s3acc
from plugins.modules.purefb_s3acc import (
    main,
    get_s3acc,
    _context_kwargs,
    _requested_export_servers,
    _current_export_servers,
    _check_account_exports,
)
from plugins.module_utils.version import LooseVersion as RealLooseVersion

MOD = "plugins.modules.purefb_s3acc"


def _error_message(response, default="Unknown error"):
    """What get_error_message returns: the first error message of a response."""
    errors = getattr(response, "errors", None)
    if errors:
        return list(errors)[0].message
    return default


@pytest.fixture(autouse=True)
def _real_helpers():
    """The module compares versions and reads error messages for real."""
    with patch(MOD + ".get_error_message", side_effect=_error_message), patch(
        MOD + ".LooseVersion", RealLooseVersion
    ):
        yield


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


def _response(status_code=200, items=None, message=None):
    response = Mock()
    response.status_code = status_code
    response.items = items if items is not None else []
    response.errors = [Mock(message=message)] if message else []
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
    # the SDK client has no per-endpoint attribute such as object_store_accounts
    del blade.object_store_accounts
    if account is None:
        blade.get_object_store_accounts.return_value = _response(
            400, message="Object store account does not exist."
        )
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
    blade.get_buckets.return_value = _response(200, [])
    realm = Mock()
    realm.name = "realm1"
    realm.destroyed = False
    blade.get_realms.return_value = _response(200, [realm])
    blade.get_servers.return_value = _response(200, [Mock()])
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
        module.params = {
            "name": "acme",
            "account_exports": [{"server": "fb-02"}, {"server": "fb-01"}],
        }
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


MISSING_ACCOUNT = "Object store account does not exist."
MISSING_REALM = "Realm does not exist."
MISSING_SERVER = "Server does not exist."
NOT_PERMITTED = "Operation not permitted."


def _realm_account(quota=None, hard=False, default_quota=None, default_hard=False):
    """An account in realm1, as the array returns it."""
    account = _account()
    account.name = "realm1::acme"
    account.quota_limit = quota
    account.hard_limit_enabled = hard
    account.bucket_defaults.quota_limit = default_quota
    account.bucket_defaults.hard_limit_enabled = default_hard
    return account


def _realm(name="realm1", destroyed=False):
    realm = Mock()
    realm.name = name
    realm.destroyed = destroyed
    return realm


def _realm_export(server="realm1::fb-01", account="realm1::acme"):
    """An export of a realm account: the array names it server::account."""
    export = Mock()
    export.name = "{0}::{1}".format(server, account)
    export.server.name = server
    export.member.name = account
    return export


def _realm_params(**overrides):
    params = _base_params(name="realm1::acme")
    params.update(overrides)
    return params


def _main(params, blade, check_mode=False, api="2.30"):
    """Run main() with the SDK models mocked; return the module and the models."""
    module = _module(params, check_mode=check_mode)
    models = {}
    with patch(MOD + ".AnsibleModule", return_value=module), patch(
        MOD + ".get_system", return_value=blade
    ), patch(MOD + ".get_rest_api_version", Mock(return_value=api)), patch(
        MOD + ".HAS_PYPURECLIENT", True
    ), patch(
        MOD + ".ObjectStoreAccountPost"
    ) as post_model, patch(
        MOD + ".ObjectStoreAccountPatch"
    ) as patch_model, patch(
        MOD + ".BucketDefaults"
    ) as defaults_model, patch(
        MOD + ".PublicAccessConfig"
    ) as public_model, patch(
        MOD + ".Reference"
    ) as reference, patch(
        MOD + ".ServerForAccountExport"
    ) as export_model:
        models.update(
            post=post_model,
            patch=patch_model,
            defaults=defaults_model,
            public=public_model,
            reference=reference,
            export=export_model,
        )
        _run()
    return module, models


def _helper(function, module, *args):
    """Call a module helper; True when it ended in fail_json."""
    try:
        getattr(s3acc, function)(module, *args)
    except SystemExit:
        return True
    return False


def _fail_msg(module):
    module.fail_json.assert_called_once()
    module.exit_json.assert_not_called()
    return module.fail_json.call_args[1]["msg"]


class TestPurefbS3accRealms:
    """Realm names, refused reads, check mode and the rollback of a create"""

    # ---------------- names ----------------

    def test_realm_of(self):
        assert s3acc._realm_of("realm1::acme") == "realm1"
        assert s3acc._realm_of("acme") == ""

    def test_qualify_server_bare_name_takes_the_realm_of_the_account(self):
        module = _module(_realm_params())
        assert s3acc._qualify_server(module, "fb-01") == "realm1::fb-01"

    def test_qualify_server_keeps_a_qualified_name(self):
        module = _module(_realm_params())
        assert s3acc._qualify_server(module, "realm2::fb-01") == "realm2::fb-01"

    def test_qualify_server_keeps_the_array_server(self):
        module = _module(_realm_params())
        assert s3acc._qualify_server(module, "_array_server") == "_array_server"

    def test_qualify_server_array_level_account_keeps_a_bare_name(self):
        module = _module(_base_params())
        assert s3acc._qualify_server(module, "fb-01") == "fb-01"

    def test_requested_export_servers_qualifies_bare_names(self):
        module = _module(
            _realm_params(
                account_exports=[{"server": "fb-01"}, {"server": "realm1::fb-02"}]
            )
        )
        assert _requested_export_servers(module) == ["realm1::fb-01", "realm1::fb-02"]

    # ---------------- quota values ----------------

    @pytest.mark.parametrize("value", [None, ""])
    def test_quota_bytes_unset_is_unlimited(self, value):
        module = _module(_base_params())
        assert s3acc._quota_bytes(module, "quota", value) == ""
        module.fail_json.assert_not_called()

    def test_quota_bytes_converts_units(self):
        module = _module(_base_params())
        assert s3acc._quota_bytes(module, "quota", "1K") == "1024"
        assert s3acc._quota_bytes(module, "quota", "20480000") == "20480000"

    def test_quota_bytes_takes_the_largest_quota_exactly(self):
        module = _module(_base_params())
        assert (
            s3acc._quota_bytes(module, "quota", "9223372036854775807")
            == "9223372036854775807"
        )

    @pytest.mark.parametrize("value", ["0", "8E", "9999999P", "9223372036854775808"])
    def test_quota_bytes_out_of_range_fails(self, value):
        module = _module(_base_params())
        assert _helper("_quota_bytes", module, "quota", value)
        msg = _fail_msg(module)
        assert "out of range" in msg
        assert value in msg

    def test_quota_bytes_not_a_size_fails(self):
        module = _module(_base_params())
        assert _helper("_quota_bytes", module, "default_quota", "12 bananas")
        msg = _fail_msg(module)
        assert "default_quota 12 bananas is not a valid size" in msg

    def test_check_hard_limits_needs_a_quota(self):
        module = _module(_realm_params())
        assert _helper("_check_hard_limits", module, "", True, "1024", False)
        assert "hard_limit" in _fail_msg(module)

    def test_check_hard_limits_needs_a_default_quota(self):
        module = _module(_realm_params())
        assert _helper("_check_hard_limits", module, "1024", True, "", True)
        assert "default_hard_limit" in _fail_msg(module)

    def test_check_hard_limits_passes_with_quotas(self):
        module = _module(_realm_params())
        assert not _helper("_check_hard_limits", module, "1024", True, "1024", True)
        assert not _helper("_check_hard_limits", module, "", False, "", False)
        module.fail_json.assert_not_called()

    # ---------------- export scope ----------------

    @pytest.mark.parametrize(
        "name,server",
        [
            ("realm1::acme", "realm2::fb-01"),
            ("realm1::acme", "_array_server"),
            ("acme", "realm1::fb-01"),
        ],
    )
    def test_check_export_scope_refuses_another_realm(self, name, server):
        module = _module(_base_params(name=name))
        assert _helper("_check_export_scope", module, [server])
        msg = _fail_msg(module)
        assert name in msg
        assert server in msg

    @pytest.mark.parametrize(
        "name,server",
        [
            ("realm1::acme", "realm1::fb-01"),
            ("realm1::acme", "REALM1::FB-01"),
            ("acme", "fb-01"),
            ("acme", "_array_server"),
        ],
    )
    def test_check_export_scope_accepts_the_same_realm(self, name, server):
        module = _module(_base_params(name=name))
        assert not _helper("_check_export_scope", module, [server])
        module.fail_json.assert_not_called()

    def test_check_export_scope_without_servers(self):
        module = _module(_realm_params())
        assert not _helper("_check_export_scope", module, None)
        assert not _helper("_check_export_scope", module, [])

    # ---------------- reads ----------------

    def _get(self, blade, params, api="2.30"):
        module = _module(params)
        with patch(MOD + ".get_rest_api_version", Mock(return_value=api)):
            try:
                return module, get_s3acc(module, blade)
            except SystemExit:
                return module, "failed"

    def test_get_s3acc_returns_the_account(self):
        account = _realm_account()
        blade = _blade(account=account)
        module, found = self._get(blade, _realm_params())
        assert found is account
        blade.get_object_store_accounts.assert_called_once_with(names=["realm1::acme"])

    def test_get_s3acc_missing_account_is_none(self):
        module, found = self._get(_blade(), _realm_params())
        assert found is None
        module.fail_json.assert_not_called()

    def test_get_s3acc_refused_read_fails_with_the_array_message(self):
        blade = _blade()
        blade.get_object_store_accounts.return_value = _response(
            403, message=NOT_PERMITTED
        )
        module, found = self._get(blade, _realm_params())
        assert found == "failed"
        msg = _fail_msg(module)
        assert "realm1::acme" in msg
        assert NOT_PERMITTED in msg

    def test_get_s3acc_empty_answer_is_none(self):
        blade = _blade()
        blade.get_object_store_accounts.return_value = _response(200, [])
        module, found = self._get(blade, _realm_params())
        assert found is None

    def test_get_s3acc_context_only_from_rest_2_17(self):
        blade = _blade(account=_realm_account())
        self._get(blade, _realm_params(context="peer1"), api="2.16")
        blade.get_object_store_accounts.assert_called_once_with(names=["realm1::acme"])
        blade = _blade(account=_realm_account())
        self._get(blade, _realm_params(context="peer1"), api="2.17")
        blade.get_object_store_accounts.assert_called_once_with(
            names=["realm1::acme"], context_names=["peer1"]
        )

    # ---------------- check mode reads ----------------

    def test_check_realm_array_level_name_reads_nothing(self):
        blade = _blade()
        module = _module(_base_params())
        assert not _helper("_check_realm", module, blade, "2.30")
        blade.get_realms.assert_not_called()

    def test_check_realm_existing_realm_passes(self):
        blade = _blade()
        module = _module(_realm_params())
        assert not _helper("_check_realm", module, blade, "2.30")
        blade.get_realms.assert_called_once_with(names=["realm1"])

    def test_check_realm_missing_realm_fails(self):
        blade = _blade()
        blade.get_realms.return_value = _response(400, message=MISSING_REALM)
        module = _module(_realm_params())
        assert _helper("_check_realm", module, blade, "2.30")
        msg = _fail_msg(module)
        assert "cannot be created in realm realm1" in msg
        assert MISSING_REALM in msg

    def test_check_realm_destroyed_realm_fails(self):
        blade = _blade()
        blade.get_realms.return_value = _response(200, [_realm(destroyed=True)])
        module = _module(_realm_params())
        assert _helper("_check_realm", module, blade, "2.30")
        assert "Realm has been destroyed." in _fail_msg(module)

    def test_check_realm_refused_read_is_not_an_answer(self):
        blade = _blade()
        blade.get_realms.return_value = _response(403, message=NOT_PERMITTED)
        module = _module(_realm_params())
        assert not _helper("_check_realm", module, blade, "2.30")
        module.fail_json.assert_not_called()

    def test_check_realm_before_realms_exist_reads_nothing(self):
        blade = _blade()
        module = _module(_realm_params())
        assert not _helper("_check_realm", module, blade, "2.18")
        blade.get_realms.assert_not_called()

    def test_check_realm_context_only_from_rest_2_24(self):
        blade = _blade()
        module = _module(_realm_params(context="peer1"))
        assert not _helper("_check_realm", module, blade, "2.23")
        blade.get_realms.assert_not_called()
        assert not _helper("_check_realm", module, blade, "2.24")
        blade.get_realms.assert_called_once_with(
            names=["realm1"], context_names=["peer1"]
        )

    def test_check_export_servers_existing_servers_pass(self):
        blade = _blade()
        module = _module(_realm_params())
        servers = ["realm1::fb-01", "realm1::fb-02"]
        assert not _helper("_check_export_servers", module, blade, "2.30", servers)
        assert blade.get_servers.call_args_list == [
            call(names=["realm1::fb-01"]),
            call(names=["realm1::fb-02"]),
        ]

    def test_check_export_servers_missing_server_fails(self):
        blade = _blade()
        blade.get_servers.return_value = _response(400, message=MISSING_SERVER)
        module = _module(_realm_params())
        assert _helper(
            "_check_export_servers", module, blade, "2.30", ["realm1::fb-01"]
        )
        msg = _fail_msg(module)
        assert "cannot be exported on server realm1::fb-01" in msg
        assert MISSING_SERVER in msg

    def test_check_export_servers_refused_read_is_not_an_answer(self):
        blade = _blade()
        blade.get_servers.return_value = _response(403, message=NOT_PERMITTED)
        module = _module(_realm_params())
        assert not _helper(
            "_check_export_servers", module, blade, "2.30", ["realm1::fb-01"]
        )
        module.fail_json.assert_not_called()

    def test_check_export_servers_without_servers_reads_nothing(self):
        blade = _blade()
        module = _module(_realm_params())
        assert not _helper("_check_export_servers", module, blade, "2.30", None)
        assert not _helper("_check_export_servers", module, blade, "2.30", [])
        blade.get_servers.assert_not_called()

    # ---------------- exports of an existing account ----------------

    def test_check_account_exports_bare_server_matches_the_realm_export(self):
        module = _module(_realm_params(account_exports=[{"server": "fb-01"}]))
        blade = _blade(account=_realm_account())
        blade.get_object_store_account_exports.return_value = _response(
            200, [_realm_export()]
        )

        _check_account_exports(module, blade)

        module.warn.assert_not_called()
        blade.get_object_store_account_exports.assert_called_once_with(
            filter="member.name='realm1::acme'"
        )

    def test_check_account_exports_ignores_letter_case(self):
        module = _module(_realm_params(account_exports=[{"server": "REALM1::FB-01"}]))
        blade = _blade(account=_realm_account())
        blade.get_object_store_account_exports.return_value = _response(
            200, [_realm_export()]
        )

        _check_account_exports(module, blade)

        module.warn.assert_not_called()

    def test_check_account_exports_warns_with_the_qualified_name(self):
        module = _module(_realm_params(account_exports=[{"server": "fb-02"}]))
        blade = _blade(account=_realm_account())
        blade.get_object_store_account_exports.return_value = _response(
            200, [_realm_export()]
        )

        _check_account_exports(module, blade)

        module.warn.assert_called_once()
        message = module.warn.call_args[0][0]
        assert "is exported on realm1::fb-01" in message
        assert "lists realm1::fb-02" in message

    # ---------------- main(): create ----------------

    def test_create_realm_account(self):
        blade = _blade()
        module, models = _main(_realm_params(), blade)

        blade.get_object_store_accounts.assert_called_once_with(names=["realm1::acme"])
        blade.post_object_store_accounts.assert_called_once_with(names=["realm1::acme"])
        models["post"].assert_not_called()
        # only the public access settings are sent after the create
        blade.patch_object_store_accounts.assert_called_once_with(
            object_store_account=models["patch"].return_value, names=["realm1::acme"]
        )
        blade.get_realms.assert_not_called()
        blade.get_servers.assert_not_called()
        blade.delete_object_store_accounts.assert_not_called()
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_realm_account_bare_server_is_sent_with_the_realm(self):
        blade = _blade()
        module, models = _main(
            _realm_params(account_exports=[{"server": "fb-01"}]), blade
        )

        models["reference"].assert_called_once_with(name="realm1::fb-01")
        models["export"].assert_called_once_with(
            server=models["reference"].return_value
        )
        models["post"].assert_called_once_with(
            account_exports=[models["export"].return_value]
        )
        blade.post_object_store_accounts.assert_called_once_with(
            names=["realm1::acme"], object_store_account=models["post"].return_value
        )
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_upper_case_name_is_lowered_before_the_server_is_qualified(self):
        blade = _blade()
        module, models = _main(
            _base_params(name="REALM1::Acme", account_exports=[{"server": "fb-01"}]),
            blade,
        )

        module.warn.assert_called_once()
        models["reference"].assert_called_once_with(name="realm1::fb-01")
        assert blade.post_object_store_accounts.call_args[1]["names"] == [
            "realm1::acme"
        ]

    def test_create_realm_account_with_quotas(self):
        blade = _blade()
        module, models = _main(
            _realm_params(quota="2G", hard_limit=True, default_quota="1G"), blade
        )

        models["defaults"].assert_called_once_with(
            hard_limit_enabled=False, quota_limit="1073741824"
        )
        assert models["patch"].call_args_list[0] == call(
            hard_limit_enabled=True,
            quota_limit="2147483648",
            bucket_defaults=models["defaults"].return_value,
        )
        assert blade.patch_object_store_accounts.call_count == 2
        for sent in blade.patch_object_store_accounts.call_args_list:
            assert sent[1]["names"] == ["realm1::acme"]
        blade.delete_object_store_accounts.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_array_level_account_with_quota_is_unchanged(self):
        """The requests for an account outside of a realm stay as they were"""
        blade = _blade()
        module, models = _main(_base_params(quota="1G"), blade)

        blade.post_object_store_accounts.assert_called_once_with(names=["acme"])
        models["defaults"].assert_called_once_with(
            hard_limit_enabled=False, quota_limit=""
        )
        assert models["patch"].call_args_list[0] == call(
            hard_limit_enabled=False,
            quota_limit="1073741824",
            bucket_defaults=models["defaults"].return_value,
        )
        models["public"].assert_called_once_with(
            block_new_public_policies=False, block_public_access=False
        )
        assert blade.patch_object_store_accounts.call_args_list == [
            call(object_store_account=models["patch"].return_value, names=["acme"]),
            call(object_store_account=models["patch"].return_value, names=["acme"]),
        ]
        blade.get_buckets.assert_not_called()
        blade.get_realms.assert_not_called()
        blade.delete_object_store_accounts.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_largest_quota_is_sent_exactly(self):
        blade = _blade()
        module, models = _main(_realm_params(quota="9223372036854775807"), blade)

        assert (
            models["patch"].call_args_list[0][1]["quota_limit"] == "9223372036854775807"
        )
        module.fail_json.assert_not_called()

    def test_create_refused_quotas_remove_the_new_account(self):
        blade = _blade()
        blade.patch_object_store_accounts.return_value = _response(
            400, message=NOT_PERMITTED
        )
        module, models = _main(_realm_params(quota="1G"), blade)

        blade.post_object_store_accounts.assert_called_once()
        blade.patch_object_store_accounts.assert_called_once()
        blade.delete_object_store_accounts.assert_called_once_with(
            names=["realm1::acme"]
        )
        msg = _fail_msg(module)
        assert "Failed to set quotas correctly for account realm1::acme" in msg
        assert NOT_PERMITTED in msg
        assert "has been removed" in msg

    def test_create_refused_quotas_remove_the_new_account_in_a_context(self):
        blade = _blade()
        blade.patch_object_store_accounts.return_value = _response(
            400, message=NOT_PERMITTED
        )
        module, models = _main(_base_params(quota="1G", context="peer1"), blade)

        blade.delete_object_store_accounts.assert_called_once_with(
            names=["acme"], context_names=["peer1"]
        )
        assert "has been removed" in _fail_msg(module)

    def test_create_refused_quotas_report_an_account_that_stays(self):
        blade = _blade()
        blade.patch_object_store_accounts.return_value = _response(
            400, message=NOT_PERMITTED
        )
        blade.delete_object_store_accounts.return_value = _response(
            400, message="Account still has bucket(s)."
        )
        module, models = _main(_realm_params(quota="1G"), blade)

        msg = _fail_msg(module)
        assert NOT_PERMITTED in msg
        assert "could not be removed" in msg
        assert "Account still has bucket(s)." in msg

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("quota", ["9999999P", "0", "12 bananas"])
    def test_create_unusable_quota_fails_before_anything_is_sent(
        self, quota, check_mode
    ):
        blade = _blade()
        module, models = _main(_realm_params(quota=quota), blade, check_mode=check_mode)

        assert quota in _fail_msg(module)
        blade.get_object_store_accounts.assert_not_called()
        blade.post_object_store_accounts.assert_not_called()
        blade.patch_object_store_accounts.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_create_hard_limit_without_quota_fails_before_the_create(self, check_mode):
        blade = _blade()
        module, models = _main(
            _realm_params(default_quota="1G", hard_limit=True),
            blade,
            check_mode=check_mode,
        )

        assert "hard_limit" in _fail_msg(module)
        blade.post_object_store_accounts.assert_not_called()

    def test_absent_does_not_judge_the_quota(self):
        blade = _blade()
        module, models = _main(_realm_params(state="absent", quota="12 bananas"), blade)

        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize(
        "name,server",
        [
            ("realm1::acme", "_array_server"),
            ("realm1::acme", "realm2::fb-01"),
            ("acme", "realm1::fb-01"),
        ],
    )
    def test_create_export_outside_of_the_realm_fails_before_the_create(
        self, name, server, check_mode
    ):
        blade = _blade()
        module, models = _main(
            _base_params(name=name, account_exports=[{"server": server}]),
            blade,
            check_mode=check_mode,
        )

        msg = _fail_msg(module)
        assert "cannot be exported on server {0}".format(server) in msg
        blade.post_object_store_accounts.assert_not_called()

    @pytest.mark.parametrize(
        "name,servers",
        [
            ("acme", ["fb-01", "FB-01"]),
            ("realm1::acme", ["fb-01", "realm1::fb-01"]),
        ],
    )
    def test_same_server_twice_is_a_duplicate(self, name, servers):
        blade = _blade()
        module, models = _main(
            _base_params(
                name=name, account_exports=[{"server": server} for server in servers]
            ),
            blade,
        )

        assert "duplicate" in _fail_msg(module)
        blade.post_object_store_accounts.assert_not_called()

    def test_create_check_mode_realm_account_reads_the_realm(self):
        blade = _blade()
        module, models = _main(
            _realm_params(account_exports=[{"server": "fb-01"}]),
            blade,
            check_mode=True,
        )

        blade.get_realms.assert_called_once_with(names=["realm1"])
        blade.get_servers.assert_called_once_with(names=["realm1::fb-01"])
        blade.post_object_store_accounts.assert_not_called()
        blade.patch_object_store_accounts.assert_not_called()
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_check_mode_unknown_realm_fails(self):
        blade = _blade()
        blade.get_realms.return_value = _response(400, message=MISSING_REALM)
        module, models = _main(_realm_params(), blade, check_mode=True)

        assert MISSING_REALM in _fail_msg(module)
        blade.post_object_store_accounts.assert_not_called()

    def test_create_check_mode_destroyed_realm_fails(self):
        blade = _blade()
        blade.get_realms.return_value = _response(200, [_realm(destroyed=True)])
        module, models = _main(_realm_params(), blade, check_mode=True)

        assert "Realm has been destroyed." in _fail_msg(module)

    def test_create_check_mode_missing_server_fails(self):
        blade = _blade()
        blade.get_servers.return_value = _response(400, message=MISSING_SERVER)
        module, models = _main(
            _realm_params(account_exports=[{"server": "fb-01"}]),
            blade,
            check_mode=True,
        )

        msg = _fail_msg(module)
        assert "realm1::fb-01" in msg
        assert MISSING_SERVER in msg

    def test_refused_account_read_is_not_a_missing_account(self):
        blade = _blade()
        blade.get_object_store_accounts.return_value = _response(
            403, message=NOT_PERMITTED
        )
        module, models = _main(_realm_params(), blade)

        msg = _fail_msg(module)
        assert "Failed to get Object Store Account realm1::acme" in msg
        assert NOT_PERMITTED in msg
        blade.post_object_store_accounts.assert_not_called()

    # ---------------- main(): update ----------------

    def test_update_realm_account(self):
        blade = _blade(account=_realm_account())
        blade.get_object_store_account_exports.return_value = _response(
            200, [_realm_export()]
        )
        module, models = _main(
            _realm_params(quota="1G", account_exports=[{"server": "fb-01"}]), blade
        )

        # the account is read once and never read without its status checked
        blade.get_object_store_accounts.assert_called_once_with(names=["realm1::acme"])
        blade.get_object_store_account_exports.assert_called_once_with(
            filter="member.name='realm1::acme'"
        )
        module.warn.assert_not_called()
        blade.patch_object_store_accounts.assert_called_once_with(
            object_store_account=models["patch"].return_value, names=["realm1::acme"]
        )
        assert models["patch"].call_args[1]["quota_limit"] == "1073741824"
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_realm_account_unchanged(self):
        blade = _blade(
            account=_realm_account(quota=1073741824, hard=True, default_quota=1024)
        )
        module, models = _main(
            _realm_params(quota="1G", hard_limit=True, default_quota="1K"), blade
        )

        blade.patch_object_store_accounts.assert_not_called()
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_update_hard_limit_on_an_unlimited_account_fails(self, check_mode):
        blade = _blade(account=_realm_account())
        module, models = _main(
            _realm_params(hard_limit=True), blade, check_mode=check_mode
        )

        assert "hard_limit" in _fail_msg(module)
        blade.patch_object_store_accounts.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_update_clearing_the_quota_under_a_hard_limit_fails(self, check_mode):
        blade = _blade(account=_realm_account(quota=1073741824, hard=True))
        module, models = _main(_realm_params(quota=""), blade, check_mode=check_mode)

        assert "hard_limit" in _fail_msg(module)
        blade.patch_object_store_accounts.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_update_default_hard_limit_without_default_quota_fails(self, check_mode):
        blade = _blade(account=_realm_account())
        module, models = _main(
            _realm_params(default_hard_limit=True), blade, check_mode=check_mode
        )

        assert "default_hard_limit" in _fail_msg(module)
        blade.patch_object_store_accounts.assert_not_called()

    def test_update_clearing_quota_and_hard_limit_together(self):
        blade = _blade(account=_realm_account(quota=1073741824, hard=True))
        module, models = _main(_realm_params(quota="", hard_limit=False), blade)

        blade.patch_object_store_accounts.assert_called_once()
        assert models["patch"].call_args[1]["quota_limit"] == ""
        assert models["patch"].call_args[1]["hard_limit_enabled"] is False
        assert module.exit_json.call_args[1]["changed"] is True

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_update_out_of_range_quota_fails_before_the_patch(self, check_mode):
        blade = _blade(account=_realm_account())
        module, models = _main(_realm_params(quota="8E"), blade, check_mode=check_mode)

        assert "out of range" in _fail_msg(module)
        blade.patch_object_store_accounts.assert_not_called()

    # ---------------- main(): delete ----------------

    def test_delete_realm_account(self):
        blade = _blade(account=_realm_account())
        module, models = _main(_realm_params(state="absent"), blade)

        blade.get_object_store_users.assert_called_once_with(
            filter="name='realm1::acme/*'"
        )
        blade.get_buckets.assert_called_once_with(filter="account.name='realm1::acme'")
        blade.delete_object_store_accounts.assert_called_once_with(
            names=["realm1::acme"]
        )
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_check_mode_sends_nothing(self):
        blade = _blade(account=_realm_account())
        module, models = _main(_realm_params(state="absent"), blade, check_mode=True)

        blade.get_object_store_users.assert_called_once()
        blade.get_buckets.assert_called_once()
        blade.delete_object_store_accounts.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_delete_with_a_user_fails(self, check_mode):
        blade = _blade(account=_realm_account())
        user = Mock()
        user.name = "realm1::acme/joe"
        blade.get_object_store_users.return_value = _response(200, [user])
        module, models = _main(
            _realm_params(state="absent"), blade, check_mode=check_mode
        )

        assert "Remove all Users" in _fail_msg(module)
        blade.delete_object_store_accounts.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_delete_with_a_bucket_fails(self, check_mode):
        blade = _blade(account=_realm_account())
        bucket = Mock()
        bucket.name = "realm1::bucket1"
        bucket.destroyed = True
        blade.get_buckets.return_value = _response(200, [bucket])
        module, models = _main(
            _realm_params(state="absent"), blade, check_mode=check_mode
        )

        assert "Remove all Buckets" in _fail_msg(module)
        blade.delete_object_store_accounts.assert_not_called()

    @pytest.mark.parametrize("read", ["get_object_store_users", "get_buckets"])
    def test_delete_refused_read_fails_with_the_array_message(self, read):
        blade = _blade(account=_realm_account())
        getattr(blade, read).return_value = _response(403, message=NOT_PERMITTED)
        module, models = _main(_realm_params(state="absent"), blade)

        msg = _fail_msg(module)
        assert "of Object Store Account realm1::acme" in msg
        assert NOT_PERMITTED in msg
        blade.delete_object_store_accounts.assert_not_called()

    def test_delete_with_context(self):
        blade = _blade(account=_account())
        module, models = _main(_base_params(state="absent", context="peer1"), blade)

        blade.get_object_store_users.assert_called_once_with(
            filter="name='acme/*'", context_names=["peer1"]
        )
        blade.get_buckets.assert_called_once_with(
            filter="account.name='acme'", context_names=["peer1"]
        )
        blade.delete_object_store_accounts.assert_called_once_with(
            names=["acme"], context_names=["peer1"]
        )

    def test_delete_refused_by_the_array_reports_its_message(self):
        blade = _blade(account=_realm_account())
        blade.delete_object_store_accounts.return_value = _response(
            400, message=NOT_PERMITTED
        )
        module, models = _main(_realm_params(state="absent"), blade)

        msg = _fail_msg(module)
        assert "deletion failed" in msg
        assert NOT_PERMITTED in msg

    def test_absent_missing_realm_account_reads_no_members(self):
        blade = _blade()
        module, models = _main(_realm_params(state="absent"), blade)

        blade.get_object_store_users.assert_not_called()
        blade.get_buckets.assert_not_called()
        blade.delete_object_store_accounts.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False
