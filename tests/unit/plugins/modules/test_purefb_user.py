# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for the public key, role, policy, service-account and
authorization-model handling of the purefb_user module."""

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
    get_user,
    get_role_name,
    get_policy_names,
    role_change,
    requested_policy_names,
    policy_change,
    converge_policies,
    validate_account_params,
    check_version_gates,
    check_admin_type,
    new_admin_post,
    set_authorization_model,
    update_ad_user,
    main,
)


class _Version:
    """Comparable stand-in for LooseVersion, which the mocked module_utils hides"""

    def __init__(self, text):
        self.parts = tuple(int(part) for part in str(text).split("."))

    def __gt__(self, other):
        return self.parts > other.parts

    def __le__(self, other):
        return self.parts <= other.parts


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
        "admin_type": None,
        "management_access_policies": None,
        "authorization_model": None,
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


def _user(
    public_key=None,
    role="storage_admin",
    policies=None,
    admin_type="local-user",
    authorization_model="static",
):
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
    user.admin_type = admin_type
    user.authorization_model = authorization_model
    return user


def _remote_user(policies=("array_admin",), authorization_model="dynamic", token=False):
    """A remote (directory service) admin as GET admins returns it"""
    user = _user(
        role=None,
        policies=list(policies),
        admin_type="remote-user",
        authorization_model=authorization_model,
    )
    user.is_local = False
    if token:
        user.api_token = Mock()
        user.api_token.created_at = 1700000000000
        user.api_token.expires_at = None
    return user


def _policy_calls(blade):
    """The attach/detach calls made on the blade, in order"""
    return [
        name
        for name, args, kwargs in blade.mock_calls
        if name
        in (
            "post_management_access_policies_admins",
            "delete_management_access_policies_admins",
        )
    ]


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


def _fails(func, module, *args):
    """Run func and return the fail_json message, or None when it passed"""
    try:
        func(module, *args)
    except SystemExit:
        pass
    if module.fail_json.called:
        return module.fail_json.call_args[1]["msg"]
    return None


class TestValidateAccountParams:
    def test_service_account_alone_passes(self):
        module = _module(admin_type="service-account")
        assert _fails(validate_account_params, module) is None

    def test_service_account_with_policies_and_api_passes(self):
        module = _module(
            admin_type="service-account",
            management_access_policies=["readonly"],
            api=True,
        )
        assert _fails(validate_account_params, module) is None

    def test_service_account_with_password_fails(self):
        module = _module(admin_type="service-account", password="secret")
        assert "REST-only" in _fails(validate_account_params, module)

    def test_service_account_with_old_password_fails(self):
        module = _module(admin_type="service-account", old_password="secret")
        assert "REST-only" in _fails(validate_account_params, module)

    def test_service_account_with_public_key_fails(self):
        module = _module(admin_type="service-account", public_key=RSA_KEY)
        assert "REST-only" in _fails(validate_account_params, module)

    def test_service_account_cannot_be_remote(self):
        module = _module(admin_type="service-account", ad_user=True)
        assert "remote" in _fails(validate_account_params, module)

    def test_authorization_model_needs_ad_user(self):
        module = _module(authorization_model="static", management_access_policies=[])
        assert "ad_user" in _fails(validate_account_params, module)

    def test_remote_policies_need_static(self):
        module = _module(ad_user=True, management_access_policies=["readonly"])
        assert "authorization_model static" in _fails(validate_account_params, module)
        module = _module(
            ad_user=True,
            authorization_model="dynamic",
            management_access_policies=["readonly"],
        )
        assert "authorization_model static" in _fails(validate_account_params, module)

    def test_static_needs_policies(self):
        module = _module(ad_user=True, authorization_model="static")
        assert "requires management_access_policies" in _fails(
            validate_account_params, module
        )

    def test_static_with_empty_list_passes(self):
        module = _module(
            ad_user=True, authorization_model="static", management_access_policies=[]
        )
        assert _fails(validate_account_params, module) is None

    def test_static_refuses_api_and_public_key(self):
        module = _module(
            ad_user=True,
            authorization_model="static",
            management_access_policies=["readonly"],
            api=True,
        )
        assert "API token" in _fails(validate_account_params, module)
        module = _module(
            ad_user=True,
            authorization_model="static",
            management_access_policies=["readonly"],
            public_key=RSA_KEY,
        )
        assert "API token" in _fails(validate_account_params, module)

    def test_static_allows_clearing_a_public_key(self):
        module = _module(
            ad_user=True,
            authorization_model="static",
            management_access_policies=["readonly"],
            public_key="",
        )
        assert _fails(validate_account_params, module) is None

    def test_dynamic_without_policies_passes(self):
        module = _module(ad_user=True, authorization_model="dynamic", api=True)
        assert _fails(validate_account_params, module) is None

    def test_local_empty_policies_fails(self):
        module = _module(management_access_policies=[])
        assert "at least one policy" in _fails(validate_account_params, module)

    def test_local_user_with_policies_and_password_passes(self):
        module = _module(management_access_policies=["readonly"], password="secret")
        assert _fails(validate_account_params, module) is None


@patch("plugins.modules.purefb_user.LooseVersion", _Version)
class TestVersionGates:
    def test_local_user_gate(self):
        module = _module()
        assert "upgraded" in _fails(check_version_gates, module, "2.14")
        assert _fails(check_version_gates, _module(), "2.15") is None

    def test_policies_gate(self):
        module = _module(management_access_policies=["readonly"])
        msg = _fails(check_version_gates, module, "2.18")
        assert "management_access_policies" in msg and "2.19" in msg and "2.18" in msg
        module = _module(management_access_policies=["readonly"])
        assert _fails(check_version_gates, module, "2.19") is None

    def test_authorization_model_gate(self):
        module = _module(ad_user=True, authorization_model="dynamic")
        msg = _fails(check_version_gates, module, "2.23")
        assert "authorization_model" in msg and "2.24" in msg
        module = _module(ad_user=True, authorization_model="dynamic")
        assert _fails(check_version_gates, module, "2.24") is None

    def test_service_account_gate(self):
        module = _module(admin_type="service-account")
        msg = _fails(check_version_gates, module, "2.25")
        assert "service-account" in msg and "2.26" in msg
        module = _module(admin_type="service-account")
        assert _fails(check_version_gates, module, "2.26") is None

    def test_local_user_type_is_not_gated(self):
        module = _module(admin_type="local-user")
        assert _fails(check_version_gates, module, "2.15") is None


class TestPolicyHelpers:
    def test_requested_names_drop_duplicates_without_regard_to_case(self):
        module = _module(
            management_access_policies=["Readonly", "readonly", "ops_admin"]
        )
        assert requested_policy_names(module) == ["Readonly", "ops_admin"]
        assert requested_policy_names(_module()) == []

    def test_same_set_in_other_case_and_order_is_no_change(self):
        module = _module(management_access_policies=["Storage_Admin", "READONLY"])
        user = _user(role=None, policies=["readonly", "storage_admin"])
        assert policy_change(module, user) == ([], [])

    def test_add_and_remove_are_sorted_and_use_the_array_spelling(self):
        module = _module(management_access_policies=["ops_admin", "Array_Admin"])
        user = _user(role=None, policies=["storage_admin", "Readonly"])
        assert policy_change(module, user) == (
            ["Array_Admin", "ops_admin"],
            ["Readonly", "storage_admin"],
        )

    def test_converge_without_request_is_no_change(self):
        blade = Mock()
        assert converge_policies(_module(), blade, _user()) is False
        assert _policy_calls(blade) == []


class TestNewAdminPost:
    @patch("plugins.modules.purefb_user.ReferenceWritable")
    @patch("plugins.modules.purefb_user.AdminPost")
    def test_local_user_gets_default_role_and_password(self, mock_post, mock_ref):
        new_admin_post(_module(password="secret"))
        mock_ref.assert_called_once_with(name="readonly")
        assert mock_post.call_args[1] == {
            "role": mock_ref.return_value,
            "password": "secret",
        }

    @patch("plugins.modules.purefb_user.ReferenceWritable")
    @patch("plugins.modules.purefb_user.AdminPost")
    def test_local_user_with_policies_sends_no_role(self, mock_post, mock_ref):
        new_admin_post(
            _module(management_access_policies=["ops_admin", "readonly"], password="s")
        )
        assert [c[1]["name"] for c in mock_ref.call_args_list] == [
            "ops_admin",
            "readonly",
        ]
        body = mock_post.call_args[1]
        assert "role" not in body and "admin_type" not in body
        assert body["password"] == "s"
        assert body["management_access_policies"] == [mock_ref.return_value] * 2

    @patch("plugins.modules.purefb_user.ReferenceWritable")
    @patch("plugins.modules.purefb_user.AdminPost")
    def test_service_account_sends_type_and_no_password(self, mock_post, mock_ref):
        new_admin_post(
            _module(
                admin_type="service-account", management_access_policies=["readonly"]
            )
        )
        body = mock_post.call_args[1]
        assert body["admin_type"] == "service-account"
        assert "password" not in body and "role" not in body
        assert body["management_access_policies"] == [mock_ref.return_value]

    @patch("plugins.modules.purefb_user.ReferenceWritable")
    @patch("plugins.modules.purefb_user.AdminPost")
    def test_service_account_with_role(self, mock_post, mock_ref):
        new_admin_post(_module(admin_type="service-account", role="storage_admin"))
        mock_ref.assert_called_once_with(name="storage_admin")
        assert mock_post.call_args[1] == {
            "role": mock_ref.return_value,
            "admin_type": "service-account",
        }


class TestCreateAccount:
    @patch("plugins.modules.purefb_user.new_admin_post")
    def test_new_account_is_posted_from_the_body_helper(self, mock_body):
        module = _module(
            admin_type="service-account", management_access_policies=["readonly"]
        )
        blade = Mock()
        blade.post_admins.return_value.status_code = 200
        try:
            create_local_user(module, blade, None)
        except SystemExit:
            pass
        blade.post_admins.assert_called_once_with(
            names=["qa-admin"], admin=mock_body.return_value
        )
        blade.post_admins_api_tokens.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True
        assert module.exit_json.call_args[1]["user_info"] == "No API token created"

    @patch("plugins.modules.purefb_user.new_admin_post")
    def test_new_service_account_with_api_gets_a_token_after_the_post(self, mock_body):
        module = _module(admin_type="service-account", api=True)
        blade = Mock()
        blade.post_admins.return_value.status_code = 200
        blade.post_admins_api_tokens.return_value.status_code = 200
        token = Mock()
        token.api_token.token = "T-secret"
        blade.post_admins_api_tokens.return_value.items = [token]
        try:
            create_local_user(module, blade, None)
        except SystemExit:
            pass
        names = [
            c[0]
            for c in blade.mock_calls
            if c[0] in ("post_admins", "post_admins_api_tokens")
        ]
        assert names == ["post_admins", "post_admins_api_tokens"]
        assert blade.post_admins_api_tokens.call_args[1]["admin_names"] == ["qa-admin"]
        assert module.exit_json.call_args[1]["user_info"] == "T-secret"

    @patch("plugins.modules.purefb_user.new_admin_post")
    def test_new_account_check_mode_posts_nothing(self, mock_body):
        module = _module(admin_type="service-account")
        module.check_mode = True
        blade = Mock()
        try:
            create_local_user(module, blade, None)
        except SystemExit:
            pass
        blade.post_admins.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_user.new_admin_post")
    def test_new_account_post_error_fails(self, mock_body):
        module = _module(management_access_policies=["readonly"])
        blade = Mock()
        blade.post_admins.return_value.status_code = 400
        try:
            create_local_user(module, blade, None)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "Failed to create user qa-admin" in module.fail_json.call_args[1]["msg"]


class TestExistingAccountPolicies:
    def test_same_policies_is_idempotent(self):
        module = _module(management_access_policies=["readonly", "Storage_Admin"])
        blade = Mock()
        user = _user(role=None, policies=["storage_admin", "readonly"])
        try:
            create_local_user(module, blade, user)
        except SystemExit:
            pass
        assert _policy_calls(blade) == []
        assert module.exit_json.call_args[1]["changed"] is False

    def test_policy_change_attaches_before_detaching(self):
        module = _module(management_access_policies=["ops_admin"])
        blade = Mock()
        blade.post_management_access_policies_admins.return_value.status_code = 200
        blade.delete_management_access_policies_admins.return_value.status_code = 200
        user = _user(role=None, policies=["readonly", "storage_admin"])
        try:
            create_local_user(module, blade, user)
        except SystemExit:
            pass
        assert _policy_calls(blade) == [
            "post_management_access_policies_admins",
            "delete_management_access_policies_admins",
        ]
        assert blade.post_management_access_policies_admins.call_args[1] == {
            "member_names": ["qa-admin"],
            "policy_names": ["ops_admin"],
        }
        assert blade.delete_management_access_policies_admins.call_args[1] == {
            "member_names": ["qa-admin"],
            "policy_names": ["readonly", "storage_admin"],
        }
        blade.patch_admins.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_adding_a_policy_detaches_nothing(self):
        module = _module(management_access_policies=["readonly", "storage_admin"])
        blade = Mock()
        blade.post_management_access_policies_admins.return_value.status_code = 200
        try:
            create_local_user(module, blade, _user(role="readonly"))
        except SystemExit:
            pass
        assert _policy_calls(blade) == ["post_management_access_policies_admins"]
        assert blade.post_management_access_policies_admins.call_args[1][
            "policy_names"
        ] == ["storage_admin"]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_policy_change_check_mode(self):
        module = _module(management_access_policies=["ops_admin"])
        module.check_mode = True
        blade = Mock()
        try:
            create_local_user(module, blade, _user(role="readonly"))
        except SystemExit:
            pass
        assert _policy_calls(blade) == []
        assert module.exit_json.call_args[1]["changed"] is True

    def test_attach_error_fails_before_detaching(self):
        module = _module(management_access_policies=["ops_admin"])
        blade = Mock()
        blade.post_management_access_policies_admins.return_value.status_code = 400
        try:
            create_local_user(module, blade, _user(role="readonly"))
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "attach" in module.fail_json.call_args[1]["msg"]
        blade.delete_management_access_policies_admins.assert_not_called()

    def test_detach_error_fails(self):
        module = _module(management_access_policies=["readonly"])
        blade = Mock()
        blade.delete_management_access_policies_admins.return_value.status_code = 400
        user = _user(role=None, policies=["readonly", "storage_admin"])
        try:
            create_local_user(module, blade, user)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "detach" in module.fail_json.call_args[1]["msg"]

    def test_remote_user_without_ad_user_is_refused(self):
        module = _module(management_access_policies=["readonly"])
        blade = Mock()
        try:
            create_local_user(module, blade, _remote_user())
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "remote user" in module.fail_json.call_args[1]["msg"]
        assert _policy_calls(blade) == []
        blade.patch_admins.assert_not_called()

    def test_password_without_old_password_exits_before_comparing(self):
        module = _module(password="secret", management_access_policies=["ops_admin"])
        blade = Mock()
        try:
            create_local_user(module, blade, _user(role="readonly"))
        except SystemExit:
            pass
        assert _policy_calls(blade) == []
        assert module.exit_json.call_args[1] == {
            "changed": False,
            "user_info": "No API token created",
        }

    def test_pureuser_policies_are_warned_not_changed(self):
        module = _module(name="pureuser", management_access_policies=["readonly"])
        blade = Mock()
        try:
            create_local_user(module, blade, _user(role="array_admin"))
        except SystemExit:
            pass
        assert _policy_calls(blade) == []
        module.warn.assert_called_once()
        assert "pureuser" in module.warn.call_args[0][0]
        assert module.exit_json.call_args[1]["changed"] is False

    def test_pureuser_same_policies_is_silent(self):
        module = _module(name="pureuser", management_access_policies=["array_admin"])
        blade = Mock()
        try:
            create_local_user(module, blade, _user(role="array_admin"))
        except SystemExit:
            pass
        module.warn.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False


class TestExistingAccountType:
    def test_type_mismatch_fails_before_any_call(self):
        module = _module(admin_type="service-account")
        blade = Mock()
        try:
            create_local_user(module, blade, _user(admin_type="local-user"))
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "cannot be changed" in module.fail_json.call_args[1]["msg"]
        assert blade.mock_calls == []
        module.exit_json.assert_not_called()

    def test_matching_type_passes(self):
        module = _module(admin_type="service-account")
        assert (
            _fails(check_admin_type, module, _user(admin_type="service-account"))
            is None
        )

    def test_unknown_type_on_an_old_array_passes(self):
        module = _module(admin_type="local-user")
        assert _fails(check_admin_type, module, _user(admin_type=None)) is None

    def test_service_account_rejects_a_password_without_admin_type(self):
        module = _module(password="new", old_password="old")
        blade = Mock()
        try:
            create_local_user(module, blade, _user(admin_type="service-account"))
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "REST-only" in module.fail_json.call_args[1]["msg"]
        blade.patch_admins.assert_not_called()

    def test_service_account_rejects_a_public_key(self):
        module = _module(public_key=RSA_KEY)
        assert "REST-only" in _fails(
            check_admin_type, module, _user(admin_type="service-account")
        )

    def test_service_account_token_rotation_is_allowed(self):
        module = _module(api=True)
        blade = Mock()
        blade.post_admins_api_tokens.return_value.status_code = 200
        token = Mock()
        token.api_token.token = "T-new"
        blade.post_admins_api_tokens.return_value.items = [token]
        try:
            create_local_user(module, blade, _user(admin_type="service-account"))
        except SystemExit:
            pass
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True
        assert module.exit_json.call_args[1]["user_info"] == "T-new"


class TestAuthorizationModel:
    @patch("plugins.modules.purefb_user.ReferenceWritable")
    @patch("plugins.modules.purefb_user.AdminPatch")
    def test_static_on_dynamic_user_patches_model_with_policies(
        self, mock_patch, mock_ref
    ):
        module = _module(
            ad_user=True,
            authorization_model="static",
            management_access_policies=["ops_admin", "readonly"],
        )
        blade = Mock()
        blade.patch_admins.return_value.status_code = 200
        assert set_authorization_model(module, blade, _remote_user()) is True
        blade.patch_admins.assert_called_once()
        assert blade.patch_admins.call_args[1]["names"] == ["qa-admin"]
        assert mock_patch.call_args[1] == {
            "authorization_model": "static",
            "management_access_policies": [mock_ref.return_value] * 2,
        }
        assert [c[1]["name"] for c in mock_ref.call_args_list] == [
            "ops_admin",
            "readonly",
        ]
        assert _policy_calls(blade) == []

    @patch("plugins.modules.purefb_user.AdminPatch")
    def test_static_on_unknown_user_patches(self, mock_patch):
        module = _module(
            ad_user=True, authorization_model="static", management_access_policies=[]
        )
        blade = Mock()
        blade.patch_admins.return_value.status_code = 200
        assert set_authorization_model(module, blade, None) is True
        assert mock_patch.call_args[1]["management_access_policies"] == []

    def test_static_on_user_with_token_fails_before_patching(self):
        module = _module(
            ad_user=True, authorization_model="static", management_access_policies=[]
        )
        blade = Mock()
        msg = _fails(set_authorization_model, module, blade, _remote_user(token=True))
        assert "API token or public key" in msg
        blade.patch_admins.assert_not_called()

    def test_static_on_user_with_public_key_fails_before_patching(self):
        module = _module(
            ad_user=True, authorization_model="static", management_access_policies=[]
        )
        blade = Mock()
        user = _remote_user()
        user.public_key = "****"
        msg = _fails(set_authorization_model, module, blade, user)
        assert "API token or public key" in msg
        blade.patch_admins.assert_not_called()

    def test_static_on_static_user_with_same_policies_is_idempotent(self):
        module = _module(
            ad_user=True,
            authorization_model="static",
            management_access_policies=["Array_Admin"],
        )
        blade = Mock()
        user = _remote_user(authorization_model="static")
        assert set_authorization_model(module, blade, user) is False
        assert blade.mock_calls == []

    def test_static_on_static_user_converges_through_membership(self):
        module = _module(
            ad_user=True,
            authorization_model="static",
            management_access_policies=["readonly"],
        )
        blade = Mock()
        blade.post_management_access_policies_admins.return_value.status_code = 200
        blade.delete_management_access_policies_admins.return_value.status_code = 200
        user = _remote_user(authorization_model="static")
        assert set_authorization_model(module, blade, user) is True
        blade.patch_admins.assert_not_called()
        assert _policy_calls(blade) == [
            "post_management_access_policies_admins",
            "delete_management_access_policies_admins",
        ]
        assert blade.delete_management_access_policies_admins.call_args[1][
            "policy_names"
        ] == ["array_admin"]

    def test_static_check_mode_writes_nothing(self):
        module = _module(
            ad_user=True, authorization_model="static", management_access_policies=[]
        )
        module.check_mode = True
        blade = Mock()
        assert set_authorization_model(module, blade, _remote_user()) is True
        assert blade.mock_calls == []

    @patch("plugins.modules.purefb_user.AdminPatch")
    def test_static_patch_error_fails(self, mock_patch):
        module = _module(
            ad_user=True, authorization_model="static", management_access_policies=[]
        )
        blade = Mock()
        blade.patch_admins.return_value.status_code = 400
        msg = _fails(set_authorization_model, module, blade, _remote_user())
        assert "statically authorized" in msg

    @patch("plugins.modules.purefb_user.AdminPatch")
    def test_dynamic_on_static_user_patches_model_alone(self, mock_patch):
        module = _module(ad_user=True, authorization_model="dynamic")
        blade = Mock()
        blade.patch_admins.return_value.status_code = 200
        user = _remote_user(authorization_model="static")
        assert set_authorization_model(module, blade, user) is True
        mock_patch.assert_called_once_with(authorization_model="dynamic")
        blade.patch_admins.assert_called_once()

    def test_dynamic_on_dynamic_or_unknown_user_is_idempotent(self):
        module = _module(ad_user=True, authorization_model="dynamic")
        blade = Mock()
        assert set_authorization_model(module, blade, _remote_user()) is False
        assert set_authorization_model(module, blade, None) is False
        assert blade.mock_calls == []

    @patch("plugins.modules.purefb_user.AdminPatch")
    def test_dynamic_patch_error_fails(self, mock_patch):
        module = _module(ad_user=True, authorization_model="dynamic")
        blade = Mock()
        blade.patch_admins.return_value.status_code = 400
        user = _remote_user(authorization_model="static")
        msg = _fails(set_authorization_model, module, blade, user)
        assert "dynamic authorization" in msg

    @patch("plugins.modules.purefb_user.AdminPatch")
    def test_update_ad_user_reverts_before_issuing_a_token(self, mock_patch):
        module = _module(ad_user=True, authorization_model="dynamic", api=True)
        blade = Mock()
        blade.patch_admins.return_value.status_code = 200
        blade.post_admins_api_tokens.return_value.status_code = 200
        token = Mock()
        token.api_token.token = "T-new"
        blade.post_admins_api_tokens.return_value.items = [token]
        user = _remote_user(authorization_model="static")
        try:
            update_ad_user(module, blade, user)
        except SystemExit:
            pass
        names = [
            c[0]
            for c in blade.mock_calls
            if c[0] in ("patch_admins", "post_admins_api_tokens")
        ]
        assert names == ["patch_admins", "post_admins_api_tokens"]
        assert module.exit_json.call_args[1]["changed"] is True
        assert module.exit_json.call_args[1]["user_info"] == "T-new"

    def test_update_ad_user_without_model_is_unchanged(self):
        module = _module(ad_user=True)
        blade = Mock()
        try:
            update_ad_user(module, blade, _remote_user())
        except SystemExit:
            pass
        assert blade.mock_calls == []
        assert module.exit_json.call_args[1]["changed"] is False


class TestGetUser:
    def _blade(self, status_code, items=None):
        blade = Mock()
        blade.get_admins.return_value.status_code = status_code
        if items is not None:
            blade.get_admins.return_value.items = items
        return blade

    def test_returns_the_admin(self):
        module = _module()
        user = _user()
        blade = self._blade(200, [user])
        assert get_user(module, blade) is user
        blade.get_admins.assert_called_once_with(names=["qa-admin"])
        module.fail_json.assert_not_called()

    def test_empty_answer_is_absent(self):
        module = _module()
        assert get_user(module, self._blade(200, [])) is None
        module.fail_json.assert_not_called()

    @patch("plugins.modules.purefb_user.get_error_message")
    def test_missing_admin_is_absent(self, mock_gem):
        mock_gem.return_value = "Admin does not exist."
        module = _module()
        assert get_user(module, self._blade(400)) is None
        module.fail_json.assert_not_called()

    @patch("plugins.modules.purefb_user.get_error_message")
    def test_other_error_fails_with_the_array_message(self, mock_gem):
        mock_gem.return_value = "Service unavailable."
        module = _module()
        try:
            get_user(module, self._blade(503))
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "qa-admin" in msg
        assert "Service unavailable." in msg

    @patch("plugins.modules.purefb_user.get_error_message")
    def test_unknown_error_fails(self, mock_gem):
        mock_gem.return_value = "Unknown error"
        module = _module()
        try:
            get_user(module, self._blade(500))
        except SystemExit:
            pass
        module.fail_json.assert_called_once()


@patch("plugins.modules.purefb_user.LooseVersion", _Version)
@patch("plugins.modules.purefb_user.get_rest_api_version")
@patch("plugins.modules.purefb_user.get_system")
@patch("plugins.modules.purefb_user.AnsibleModule")
class TestMain:
    def _run(
        self, mock_ansible_module, mock_get_system, mock_api_version, version, **params
    ):
        module = _module(**params)
        mock_ansible_module.return_value = module
        blade = Mock()
        mock_get_system.return_value = blade
        mock_api_version.return_value = version
        return module, blade

    @patch("plugins.modules.purefb_user.get_error_message")
    def test_mutually_exclusive_role_and_policies(
        self, mock_gem, mock_ansible_module, mock_get_system, mock_api_version
    ):
        mock_gem.return_value = "Admin does not exist."
        module, blade = self._run(
            mock_ansible_module, mock_get_system, mock_api_version, "2.30"
        )
        blade.get_admins.return_value.status_code = 400
        blade.post_admins.return_value.status_code = 200
        try:
            main()
        except SystemExit:
            pass
        kwargs = mock_ansible_module.call_args[1]
        assert ["role", "management_access_policies"] in kwargs["mutually_exclusive"]
        assert kwargs["supports_check_mode"] is True

    def test_validation_fails_before_connecting(
        self, mock_ansible_module, mock_get_system, mock_api_version
    ):
        module, blade = self._run(
            mock_ansible_module,
            mock_get_system,
            mock_api_version,
            "2.30",
            admin_type="service-account",
            password="secret",
        )
        try:
            main()
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        mock_get_system.assert_not_called()

    def test_service_account_gate_fails_before_any_read_or_write(
        self, mock_ansible_module, mock_get_system, mock_api_version
    ):
        module, blade = self._run(
            mock_ansible_module,
            mock_get_system,
            mock_api_version,
            "2.25",
            admin_type="service-account",
        )
        try:
            main()
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "2.26" in module.fail_json.call_args[1]["msg"]
        assert blade.mock_calls == []

    def test_policies_gate_fails_in_check_mode_too(
        self, mock_ansible_module, mock_get_system, mock_api_version
    ):
        module, blade = self._run(
            mock_ansible_module,
            mock_get_system,
            mock_api_version,
            "2.18",
            management_access_policies=["readonly"],
        )
        module.check_mode = True
        try:
            main()
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "2.19" in module.fail_json.call_args[1]["msg"]
        assert blade.mock_calls == []

    @patch("plugins.modules.purefb_user.get_error_message")
    @patch("plugins.modules.purefb_user.new_admin_post")
    def test_creates_a_service_account(
        self,
        mock_body,
        mock_gem,
        mock_ansible_module,
        mock_get_system,
        mock_api_version,
    ):
        mock_gem.return_value = "Admin does not exist."
        module, blade = self._run(
            mock_ansible_module,
            mock_get_system,
            mock_api_version,
            "2.30",
            admin_type="service-account",
            management_access_policies=["readonly"],
        )
        blade.get_admins.return_value.status_code = 400
        blade.post_admins.return_value.status_code = 200
        try:
            main()
        except SystemExit:
            pass
        blade.post_admins.assert_called_once_with(
            names=["qa-admin"], admin=mock_body.return_value
        )
        assert module.exit_json.call_args[1]["changed"] is True

    def test_remote_user_static_conversion_path(
        self, mock_ansible_module, mock_get_system, mock_api_version
    ):
        module, blade = self._run(
            mock_ansible_module,
            mock_get_system,
            mock_api_version,
            "2.30",
            ad_user=True,
            authorization_model="static",
            management_access_policies=["readonly"],
        )
        blade.get_admins.return_value.status_code = 200
        blade.get_admins.return_value.items = [_remote_user()]
        blade.patch_admins.return_value.status_code = 200
        try:
            main()
        except SystemExit:
            pass
        blade.patch_admins.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_absent_service_account_is_deleted(
        self, mock_ansible_module, mock_get_system, mock_api_version
    ):
        module, blade = self._run(
            mock_ansible_module,
            mock_get_system,
            mock_api_version,
            "2.30",
            state="absent",
        )
        blade.get_admins.return_value.status_code = 200
        blade.get_admins.return_value.items = [_user(admin_type="service-account")]
        blade.delete_admins.return_value.status_code = 200
        try:
            main()
        except SystemExit:
            pass
        blade.delete_admins.assert_called_once_with(names=["qa-admin"])
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_user.get_error_message")
    def test_read_error_fails_instead_of_creating(
        self, mock_gem, mock_ansible_module, mock_get_system, mock_api_version
    ):
        mock_gem.return_value = "Service unavailable."
        module, blade = self._run(
            mock_ansible_module, mock_get_system, mock_api_version, "2.30"
        )
        blade.get_admins.return_value.status_code = 503
        try:
            main()
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "Service unavailable." in module.fail_json.call_args[1]["msg"]
        blade.post_admins.assert_not_called()
        module.exit_json.assert_not_called()

    @patch("plugins.modules.purefb_user.get_error_message")
    def test_read_error_fails_absent_instead_of_reporting_ok(
        self, mock_gem, mock_ansible_module, mock_get_system, mock_api_version
    ):
        mock_gem.return_value = "Service unavailable."
        module, blade = self._run(
            mock_ansible_module,
            mock_get_system,
            mock_api_version,
            "2.30",
            state="absent",
        )
        blade.get_admins.return_value.status_code = 500
        try:
            main()
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        blade.delete_admins.assert_not_called()
        module.exit_json.assert_not_called()

    @patch("plugins.modules.purefb_user.get_error_message")
    def test_absent_missing_admin_is_unchanged(
        self, mock_gem, mock_ansible_module, mock_get_system, mock_api_version
    ):
        mock_gem.return_value = "Admin does not exist."
        module, blade = self._run(
            mock_ansible_module,
            mock_get_system,
            mock_api_version,
            "2.30",
            state="absent",
        )
        blade.get_admins.return_value.status_code = 400
        try:
            main()
        except SystemExit:
            pass
        module.fail_json.assert_not_called()
        blade.delete_admins.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False
