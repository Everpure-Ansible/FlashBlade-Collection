# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for the public key and role handling of the purefb_user module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
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
sys.modules[
    "ansible_collections.everpure.flashblade.plugins.module_utils.time_utils"
] = MagicMock()

from plugins.modules.purefb_user import (
    parse_public_keys,
    validate_public_key,
    public_key_changed,
    create_local_user,
    get_role_name,
    get_policy_names,
    role_change,
)

RSA_KEY = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC7fbqa0" + "A" * 40 + "= qa@lab"
RSA_KEY_NO_COMMENT = " ".join(RSA_KEY.split()[:2])
OTHER_RSA_KEY = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDothr" + "B" * 40 + "= qa@lab"
ED25519_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIG" + "C" * 40 + " qa@lab"
PEM_KEY = (
    "-----BEGIN PUBLIC KEY-----\n"
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA0Z3VS5JJcds3xfn/ygWy\n"
    "F8yn4b1PHWt0u2B9Nwm3UJDCSXxTRIkqQyjfZ6E7T3vb9mx1gV/qXrvXGm4K7zzj\n"
    "QIDAQAB\n"
    "-----END PUBLIC KEY-----"
)


def _params(**overrides):
    params = {
        "name": "qa-admin",
        "state": "present",
        "role": None,
        "password": None,
        "old_password": None,
        "api": False,
        "timeout": "0",
        "public_key": None,
        "clear_lock": False,
        "ad_user": False,
    }
    params.update(overrides)
    return params


def _module(**overrides):
    module = Mock()
    module.params = _params(**overrides)
    module.check_mode = False
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _reference(name):
    reference = Mock()
    reference.name = name
    return reference


def _user(public_key=None, role="storage_admin", policies=None):
    """A local admin as GET admins returns it.

    ``role`` is the legacy role name, or None for an admin managed by
    management access policies; ``policies`` are the policy names.
    """
    user = Mock()
    user.is_local = True
    user.locked = False
    user.role = _reference(role) if role else None
    if policies is None:
        policies = [role] if role else []
    user.management_access_policies = [_reference(name) for name in policies]
    user.public_key = public_key
    user.api_token = None
    return user


def _token_module(name="svc-ansible"):
    module = Mock()
    module.check_mode = False
    module.params = {"name": name, "timeout": "0"}
    module.fail_json = Mock(side_effect=SystemExit("fail_json called"))
    return module


def _token_response(status, token=None):
    res = Mock()
    res.status_code = status
    if token is not None:
        res.items = [Mock(api_token=Mock(token=token))]
    return res


class TestCreateApiToken:
    """Purity//FB 4.8.8 was seen to answer "API token already created" to a
    create that followed the delete of the previous token; the module waits
    and asks once more before giving up."""

    @patch("plugins.modules.purefb_user.time.sleep")
    @patch("plugins.modules.purefb_user.get_error_message")
    def test_first_try_succeeds(self, mock_err, mock_sleep):
        from plugins.modules.purefb_user import create_api_token

        blade = Mock()
        blade.post_admins_api_tokens.return_value = _token_response(200, "T-1")

        assert create_api_token(_token_module(), blade) == "T-1"
        assert blade.post_admins_api_tokens.call_count == 1
        mock_sleep.assert_not_called()
        mock_err.assert_not_called()

    @patch("plugins.modules.purefb_user.time.sleep")
    @patch(
        "plugins.modules.purefb_user.get_error_message",
        return_value="API token already created",
    )
    def test_already_created_is_retried_once(self, _err, mock_sleep):
        from plugins.modules.purefb_user import create_api_token

        blade = Mock()
        blade.post_admins_api_tokens.side_effect = [
            _token_response(400),
            _token_response(200, "T-2"),
        ]

        assert create_api_token(_token_module(), blade) == "T-2"
        calls = blade.post_admins_api_tokens.call_args_list
        assert len(calls) == 2 and calls[0] == calls[1]
        mock_sleep.assert_called_once()

    @patch("plugins.modules.purefb_user.time.sleep")
    @patch(
        "plugins.modules.purefb_user.get_error_message",
        return_value="API token already created",
    )
    def test_still_present_after_retry_fails(self, _err, mock_sleep):
        from plugins.modules.purefb_user import create_api_token

        module = _token_module()
        blade = Mock()
        blade.post_admins_api_tokens.return_value = _token_response(400)

        with pytest.raises(SystemExit):
            create_api_token(module, blade)
        assert blade.post_admins_api_tokens.call_count == 2
        assert "Failed to create API token" in module.fail_json.call_args[1]["msg"]

    @patch("plugins.modules.purefb_user.time.sleep")
    @patch(
        "plugins.modules.purefb_user.get_error_message",
        return_value="Permission denied",
    )
    def test_other_errors_are_not_retried(self, _err, mock_sleep):
        from plugins.modules.purefb_user import create_api_token

        module = _token_module()
        blade = Mock()
        blade.post_admins_api_tokens.return_value = _token_response(400)

        with pytest.raises(SystemExit):
            create_api_token(module, blade)
        assert blade.post_admins_api_tokens.call_count == 1
        mock_sleep.assert_not_called()


class TestParsePublicKeys:
    def test_single_key_with_comment(self):
        assert parse_public_keys(RSA_KEY) == [
            ("ssh-rsa", RSA_KEY.split()[1]),
        ]

    def test_two_keys_and_blank_lines(self):
        text = "\n" + RSA_KEY + "\n\n" + ED25519_KEY + "\n"
        assert parse_public_keys(text) == [
            ("ssh-rsa", RSA_KEY.split()[1]),
            ("ssh-ed25519", ED25519_KEY.split()[1]),
        ]

    def test_pem_block_is_not_openssh(self):
        assert parse_public_keys(PEM_KEY) is None

    def test_empty_and_none(self):
        assert parse_public_keys("") == []
        assert parse_public_keys(None) == []


class TestValidatePublicKey:
    def test_pem_is_rejected_with_a_format_message(self):
        module = _module(public_key=PEM_KEY)
        try:
            validate_public_key(module)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "OpenSSH" in module.fail_json.call_args[1]["msg"]

    def test_more_than_two_keys_is_rejected(self):
        module = _module(public_key="\n".join([RSA_KEY, ED25519_KEY, OTHER_RSA_KEY]))
        try:
            validate_public_key(module)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()

    def test_openssh_keys_pass(self):
        module = _module(public_key=RSA_KEY + "\n" + ED25519_KEY)
        validate_public_key(module)
        module.fail_json.assert_not_called()

    def test_none_and_empty_pass(self):
        module = _module(public_key=None)
        validate_public_key(module)
        module.params["public_key"] = ""
        validate_public_key(module)
        module.fail_json.assert_not_called()


class TestPublicKeyChanged:
    def test_not_requested(self):
        assert public_key_changed(_module(public_key=None), _user(RSA_KEY)) is False

    def test_same_key_different_comment_or_whitespace(self):
        module = _module(public_key=RSA_KEY_NO_COMMENT + "\n")
        assert public_key_changed(module, _user(RSA_KEY)) is False

    def test_same_two_keys_in_other_order(self):
        module = _module(public_key=ED25519_KEY + "\n" + RSA_KEY)
        assert public_key_changed(module, _user(RSA_KEY + "\n" + ED25519_KEY)) is False

    def test_different_key(self):
        module = _module(public_key=OTHER_RSA_KEY)
        assert public_key_changed(module, _user(RSA_KEY)) is True

    def test_first_key_on_user_without_one(self):
        module = _module(public_key=RSA_KEY)
        assert public_key_changed(module, _user(None)) is True

    def test_clearing(self):
        module = _module(public_key="")
        assert public_key_changed(module, _user(None)) is False
        assert public_key_changed(module, _user(RSA_KEY)) is True

    def test_masked_key_counts_as_present(self):
        module = _module(public_key=RSA_KEY)
        assert public_key_changed(module, _user("****")) is False
        module.params["public_key"] = ""
        assert public_key_changed(module, _user("****")) is True


class TestCreateLocalUserPublicKey:
    def test_existing_user_same_key_is_idempotent(self):
        module = _module(public_key=RSA_KEY)
        blade = Mock()
        try:
            create_local_user(module, blade, _user(RSA_KEY_NO_COMMENT))
        except SystemExit:
            pass
        blade.patch_admins.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_user.AdminPatch")
    def test_existing_user_new_key_is_patched_once(self, mock_admin_patch):
        module = _module(public_key=RSA_KEY + "\n")
        blade = Mock()
        blade.patch_admins.return_value.status_code = 200
        try:
            create_local_user(module, blade, _user(None))
        except SystemExit:
            pass
        blade.patch_admins.assert_called_once()
        assert mock_admin_patch.call_args[1]["public_key"] == RSA_KEY
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_user.AdminPatch")
    def test_check_mode_reports_without_patching(self, mock_admin_patch):
        module = _module(public_key=RSA_KEY)
        module.check_mode = True
        blade = Mock()
        try:
            create_local_user(module, blade, _user(None))
        except SystemExit:
            pass
        blade.patch_admins.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True


class TestRoleHelpers:
    def test_legacy_role_name(self):
        assert get_role_name(_user(role="array_admin")) == "array_admin"

    def test_null_role_name(self):
        assert get_role_name(_user(role=None, policies=["readonly"])) is None
        assert get_role_name(Mock(spec=[])) is None

    def test_policy_names_are_sorted(self):
        user = _user(role=None, policies=["storage_admin", "readonly"])
        assert get_policy_names(user) == ["readonly", "storage_admin"]

    def test_policy_names_tolerate_none_and_unnamed(self):
        assert get_policy_names(Mock(spec=[])) == []
        user = _user(role=None, policies=[])
        user.management_access_policies = None
        assert get_policy_names(user) == []
        user.management_access_policies = [_reference("readonly"), Mock(spec=[])]
        assert get_policy_names(user) == ["readonly"]


class TestRoleChange:
    def test_no_role_requested(self):
        assert role_change(_module(role=None), _user()) is False

    def test_remote_user_is_ignored(self):
        user = _user(role=None, policies=["readonly", "storage_admin"])
        user.is_local = False
        assert role_change(_module(role="array_admin"), user) is False

    def test_legacy_role_differs(self):
        assert role_change(_module(role="array_admin"), _user()) is True

    def test_legacy_role_same(self):
        assert role_change(_module(role="storage_admin"), _user()) is False

    def test_null_role_with_requested_policy_is_satisfied_with_a_warning(self):
        module = _module(role="readonly")
        user = _user(role=None, policies=["readonly", "storage_admin"])
        assert role_change(module, user) is False
        module.fail_json.assert_not_called()
        module.warn.assert_called_once()
        msg = module.warn.call_args[0][0]
        assert "['storage_admin']" in msg
        assert "purefb_mgmt_role" in msg

    def test_null_role_with_only_the_requested_policy_does_not_warn(self):
        module = _module(role="readonly")
        user = _user(role=None, policies=["readonly"])
        assert role_change(module, user) is False
        module.fail_json.assert_not_called()
        module.warn.assert_not_called()

    def test_null_role_without_requested_policy_fails(self):
        module = _module(role="array_admin")
        user = _user(role=None, policies=["readonly", "storage_admin"])
        try:
            role_change(module, user)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "purefb_mgmt_role" in msg
        assert "readonly" in msg and "storage_admin" in msg

    def test_null_role_without_policies_fails(self):
        module = _module(role="readonly")
        user = _user(role=None, policies=[])
        try:
            role_change(module, user)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()


class TestCreateLocalUserRole:
    def test_null_role_same_policy_is_idempotent(self):
        module = _module(role="readonly")
        blade = Mock()
        try:
            create_local_user(
                module, blade, _user(role=None, policies=["readonly", "storage_admin"])
            )
        except SystemExit:
            pass
        blade.patch_admins.assert_not_called()
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_null_role_other_role_fails_before_any_patch(self):
        module = _module(role="array_admin")
        blade = Mock()
        try:
            create_local_user(
                module, blade, _user(role=None, policies=["readonly", "storage_admin"])
            )
        except SystemExit:
            pass
        blade.patch_admins.assert_not_called()
        module.fail_json.assert_called_once()
        module.exit_json.assert_not_called()

    @patch("plugins.modules.purefb_user.ReferenceWritable")
    @patch("plugins.modules.purefb_user.AdminPatch")
    def test_legacy_role_change_is_patched_once(self, mock_patch, mock_reference):
        module = _module(role="array_admin")
        blade = Mock()
        blade.patch_admins.return_value.status_code = 200
        try:
            create_local_user(module, blade, _user(role="readonly"))
        except SystemExit:
            pass
        blade.patch_admins.assert_called_once()
        assert blade.patch_admins.call_args[1]["names"] == ["qa-admin"]
        mock_reference.assert_called_once_with(name="array_admin")
        assert mock_patch.call_args[1]["role"] is mock_reference.return_value
        assert module.exit_json.call_args[1]["changed"] is True

    def test_legacy_role_same_is_idempotent(self):
        module = _module(role="readonly")
        blade = Mock()
        try:
            create_local_user(module, blade, _user(role="readonly"))
        except SystemExit:
            pass
        blade.patch_admins.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_legacy_role_change_check_mode(self):
        module = _module(role="array_admin")
        module.check_mode = True
        blade = Mock()
        try:
            create_local_user(module, blade, _user(role="readonly"))
        except SystemExit:
            pass
        blade.patch_admins.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_user.AdminPatch")
    def test_legacy_role_patch_error_fails(self, mock_patch):
        module = _module(role="array_admin")
        blade = Mock()
        blade.patch_admins.return_value.status_code = 400
        try:
            create_local_user(module, blade, _user(role="readonly"))
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "role" in module.fail_json.call_args[1]["msg"]

    def test_pureuser_role_is_warned_not_patched(self):
        module = _module(name="pureuser", role="readonly")
        blade = Mock()
        try:
            create_local_user(module, blade, _user(role="array_admin"))
        except SystemExit:
            pass
        blade.patch_admins.assert_not_called()
        module.warn.assert_called_once_with("Role for 'pureuser' cannot be modified.")
        assert module.exit_json.call_args[1]["changed"] is False

    def test_pureuser_null_role_is_warned_not_failed(self):
        module = _module(name="pureuser", role="storage_admin")
        blade = Mock()
        try:
            create_local_user(
                module, blade, _user(role=None, policies=["array_admin", "readonly"])
            )
        except SystemExit:
            pass
        blade.patch_admins.assert_not_called()
        module.fail_json.assert_not_called()
        module.warn.assert_called_once_with("Role for 'pureuser' cannot be modified.")
        assert module.exit_json.call_args[1]["changed"] is False

    def test_pureuser_same_legacy_role_is_silent(self):
        module = _module(name="pureuser", role="array_admin")
        blade = Mock()
        try:
            create_local_user(module, blade, _user(role="array_admin"))
        except SystemExit:
            pass
        blade.patch_admins.assert_not_called()
        module.warn.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False
