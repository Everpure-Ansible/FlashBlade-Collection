# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_apiclient module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from unittest.mock import Mock, patch, MagicMock

import yaml

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

from plugins.modules.purefb_apiclient import (
    DOCUMENTATION,
    EXAMPLES,
    main,
    create_client,
    update_client,
    delete_client,
    _requested_policies,
    _current_policies,
    _get_client,
    MIN_ACCESS_POLICIES_API_VERSION,
)

FQCN = "everpure.flashblade.purefb_apiclient"
# A management access policy whose rules are scoped to a realm. The policy
# itself is an array-level object, named without a realm prefix.
REALM_POLICY = "tenant1-admins"
# Messages of the array, as Purity//FB 4.8.8 sends them
NO_CLIENT = "API client does not exist."
NO_POLICY = "Management access policy not exist."
NOT_PERMITTED = "Operation not permitted."
PUB_KEY = "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A\n-----END PUBLIC KEY-----\n"


def _base_params(**overrides):
    """Return a full params dict with sane defaults, patched by overrides."""
    params = {
        "name": "ansible-client",
        "state": "present",
        "enabled": True,
        "role": None,
        "access_policies": None,
        "public_key": None,
        "token_ttl": None,
        "issuer": None,
    }
    params.update(overrides)
    return params


def _module(**overrides):
    module = Mock()
    module.params = _base_params(**overrides)
    module.check_mode = False
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.warn = Mock()
    return module


def _ref(name):
    ref = Mock()
    ref.name = name
    return ref


def _client(
    policies=("readonly",),
    enabled=True,
    public_key=PUB_KEY,
    issuer="ansible-client",
    ttl_ms=86400000,
    max_role="readonly",
):
    client = Mock()
    client.enabled = enabled
    client.access_policies = (
        [_ref(policy) for policy in policies] if policies is not None else None
    )
    client.public_key = public_key
    client.issuer = issuer
    client.access_token_ttl_in_ms = ttl_ms
    client.max_role = _ref(max_role) if max_role else None
    return client


def _response(status=200, items=None):
    res = Mock()
    res.status_code = status
    res.items = items if items is not None else []
    return res


def _run(func, *args):
    try:
        func(*args)
    except SystemExit:
        pass


def _fake_ref(name):
    return ("ref", name)


class TestPurefbApiclientHelpers:
    """Pure-function helpers."""

    def test_requested_policies_prefers_access_policies_and_dedupes(self):
        module = _module(
            access_policies=["readonly", "storage_admin", "readonly"], role=None
        )
        assert _requested_policies(module) == ["readonly", "storage_admin"]

    def test_requested_policies_falls_back_to_role(self):
        module = _module(role="ops_admin")
        assert _requested_policies(module) == ["ops_admin"]

    def test_requested_policies_none_when_neither_given(self):
        module = _module(access_policies=[], role=None)
        assert _requested_policies(module) is None

    def test_current_policies_reads_access_policies(self):
        client = _client(policies=("storage_admin", "readonly"), max_role=None)
        assert _current_policies(client) == ["storage_admin", "readonly"]

    def test_current_policies_falls_back_to_max_role(self):
        client = _client(policies=None, max_role="readonly")
        assert _current_policies(client) == ["readonly"]

    def test_current_policies_empty_when_nothing_reported(self):
        client = _client(policies=None, max_role=None)
        assert _current_policies(client) == []


@patch("plugins.modules.purefb_apiclient.get_error_message", return_value="boom")
@patch("plugins.modules.purefb_apiclient.ApiClient")
@patch("plugins.modules.purefb_apiclient.ReferenceWritable", side_effect=_fake_ref)
@patch("plugins.modules.purefb_apiclient.ApiClientsPost")
@patch("plugins.modules.purefb_apiclient.LooseVersion")
class TestPurefbApiclientCreate:
    """create_client paths."""

    @staticmethod
    def _supported(mock_loose_version, supported):
        mock_loose_version.return_value.__le__ = Mock(return_value=supported)

    def test_create_with_access_policies_sends_references(
        self, mock_lv, mock_post_model, mock_ref, mock_api_client, mock_err
    ):
        self._supported(mock_lv, True)
        module = _module(
            access_policies=["readonly", "storage_admin"], public_key=PUB_KEY
        )
        blade = Mock()
        blade.post_api_clients.return_value = _response(200)
        blade.patch_api_clients.return_value = _response(200)

        _run(create_client, module, blade, "2.30")

        kwargs = mock_post_model.call_args[1]
        assert kwargs["access_policies"] == [
            ("ref", "readonly"),
            ("ref", "storage_admin"),
        ]
        assert "max_role" not in kwargs
        assert kwargs["issuer"] == "ansible-client"
        assert kwargs["access_token_ttl_in_ms"] == 86400000
        assert kwargs["public_key"] == PUB_KEY
        blade.post_api_clients.assert_called_once_with(
            names=["ansible-client"], api_client=mock_post_model.return_value
        )
        mock_api_client.assert_called_once_with(enabled=True)
        blade.patch_api_clients.assert_called_once_with(
            api_clients=mock_api_client.return_value, names=["ansible-client"]
        )
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()

    def test_create_with_role_on_new_api_sends_access_policies(
        self, mock_lv, mock_post_model, mock_ref, mock_api_client, mock_err
    ):
        self._supported(mock_lv, True)
        module = _module(role="ops_admin", public_key=PUB_KEY)
        blade = Mock()
        blade.post_api_clients.return_value = _response(200)
        blade.patch_api_clients.return_value = _response(200)

        _run(create_client, module, blade, "2.19")

        kwargs = mock_post_model.call_args[1]
        assert kwargs["access_policies"] == [("ref", "ops_admin")]
        assert "max_role" not in kwargs
        module.exit_json.assert_called_once_with(changed=True)

    def test_create_with_role_on_old_api_sends_max_role(
        self, mock_lv, mock_post_model, mock_ref, mock_api_client, mock_err
    ):
        self._supported(mock_lv, False)
        module = _module(role="readonly", public_key=PUB_KEY)
        blade = Mock()
        blade.post_api_clients.return_value = _response(200)
        blade.patch_api_clients.return_value = _response(200)

        _run(create_client, module, blade, "2.17")

        kwargs = mock_post_model.call_args[1]
        assert kwargs["max_role"] == ("ref", "readonly")
        assert "access_policies" not in kwargs
        module.exit_json.assert_called_once_with(changed=True)

    def test_create_requires_public_key(
        self, mock_lv, mock_post_model, mock_ref, mock_api_client, mock_err
    ):
        self._supported(mock_lv, True)
        module = _module(access_policies=["readonly"])
        blade = Mock()

        _run(create_client, module, blade, "2.30")

        module.fail_json.assert_called_once()
        assert "public_key" in module.fail_json.call_args[1]["msg"]
        blade.post_api_clients.assert_not_called()

    def test_create_requires_policies_or_role(
        self, mock_lv, mock_post_model, mock_ref, mock_api_client, mock_err
    ):
        self._supported(mock_lv, True)
        module = _module(public_key=PUB_KEY, access_policies=[])
        blade = Mock()

        _run(create_client, module, blade, "2.30")

        module.fail_json.assert_called_once()
        assert "access_policies or role" in module.fail_json.call_args[1]["msg"]
        blade.post_api_clients.assert_not_called()

    def test_create_rejects_ttl_out_of_range(
        self, mock_lv, mock_post_model, mock_ref, mock_api_client, mock_err
    ):
        self._supported(mock_lv, True)
        for ttl in (0, 86401):
            module = _module(access_policies=["readonly"], public_key=PUB_KEY)
            module.params["token_ttl"] = ttl
            blade = Mock()

            _run(create_client, module, blade, "2.30")

            module.fail_json.assert_called_once()
            assert "token_ttl" in module.fail_json.call_args[1]["msg"]
            blade.post_api_clients.assert_not_called()

    def test_create_passes_custom_ttl_and_issuer(
        self, mock_lv, mock_post_model, mock_ref, mock_api_client, mock_err
    ):
        self._supported(mock_lv, True)
        module = _module(
            access_policies=["readonly"],
            public_key=PUB_KEY,
            token_ttl=3000,
            issuer="my-idp",
            enabled=False,
        )
        blade = Mock()
        blade.post_api_clients.return_value = _response(200)

        _run(create_client, module, blade, "2.30")

        kwargs = mock_post_model.call_args[1]
        assert kwargs["access_token_ttl_in_ms"] == 3000000
        assert kwargs["issuer"] == "my-idp"
        # enabled=False means no enable PATCH after the POST
        blade.patch_api_clients.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_create_check_mode_sends_nothing(
        self, mock_lv, mock_post_model, mock_ref, mock_api_client, mock_err
    ):
        self._supported(mock_lv, True)
        module = _module(access_policies=["readonly"], public_key=PUB_KEY)
        module.check_mode = True
        blade = Mock()

        _run(create_client, module, blade, "2.30")

        blade.post_api_clients.assert_not_called()
        blade.patch_api_clients.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_create_post_error_fails(
        self, mock_lv, mock_post_model, mock_ref, mock_api_client, mock_err
    ):
        self._supported(mock_lv, True)
        module = _module(access_policies=["readonly"], public_key=PUB_KEY)
        blade = Mock()
        blade.post_api_clients.return_value = _response(400)

        _run(create_client, module, blade, "2.30")

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to create API Client ansible-client" in msg
        assert "boom" in msg
        blade.patch_api_clients.assert_not_called()

    def test_create_enable_failure_warns(
        self, mock_lv, mock_post_model, mock_ref, mock_api_client, mock_err
    ):
        self._supported(mock_lv, True)
        module = _module(access_policies=["readonly"], public_key=PUB_KEY)
        blade = Mock()
        blade.post_api_clients.return_value = _response(200)
        blade.patch_api_clients.return_value = _response(400)

        _run(create_client, module, blade, "2.30")

        module.warn.assert_called_once()
        assert "enable failed" in module.warn.call_args[0][0]
        module.exit_json.assert_called_once_with(changed=True)


@patch("plugins.modules.purefb_apiclient.get_error_message", return_value="boom")
@patch("plugins.modules.purefb_apiclient.ApiClient")
class TestPurefbApiclientUpdate:
    """update_client paths."""

    def test_update_noop_when_everything_matches(self, mock_api_client, mock_err):
        module = _module(
            access_policies=["readonly"],
            public_key=PUB_KEY,
            issuer="ansible-client",
            token_ttl=86400,
        )
        blade = Mock()

        _run(update_client, module, blade, _client())

        module.warn.assert_not_called()
        blade.patch_api_clients.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_update_policy_drift_warns_and_does_not_patch(
        self, mock_api_client, mock_err
    ):
        module = _module(access_policies=["storage_admin"])
        blade = Mock()

        _run(update_client, module, blade, _client())

        module.warn.assert_called_once()
        msg = module.warn.call_args[0][0]
        assert "access_policies" in msg
        assert "Delete and recreate" in msg
        blade.patch_api_clients.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_update_role_drift_names_role(self, mock_api_client, mock_err):
        module = _module(role="array_admin")
        blade = Mock()

        _run(update_client, module, blade, _client())

        module.warn.assert_called_once()
        msg = module.warn.call_args[0][0]
        assert "role" in msg
        assert "access_policies" not in msg
        module.exit_json.assert_called_once_with(changed=False)

    def test_update_role_matches_single_policy_client(self, mock_api_client, mock_err):
        module = _module(role="readonly")
        blade = Mock()

        _run(update_client, module, blade, _client(policies=("readonly",)))

        module.warn.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_update_role_against_multi_policy_client_warns(
        self, mock_api_client, mock_err
    ):
        module = _module(role="readonly")
        blade = Mock()

        _run(
            update_client,
            module,
            blade,
            _client(policies=("readonly", "storage_admin"), max_role=None),
        )

        module.warn.assert_called_once()
        assert "role" in module.warn.call_args[0][0]

    def test_update_policy_order_is_ignored(self, mock_api_client, mock_err):
        module = _module(access_policies=["storage_admin", "readonly", "readonly"])
        blade = Mock()

        _run(
            update_client,
            module,
            blade,
            _client(policies=("readonly", "storage_admin"), max_role=None),
        )

        module.warn.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_update_old_array_falls_back_to_max_role(self, mock_api_client, mock_err):
        blade = Mock()

        module = _module(role="readonly")
        _run(update_client, module, blade, _client(policies=None, max_role="readonly"))
        module.warn.assert_not_called()

        module = _module(role="ops_admin")
        _run(update_client, module, blade, _client(policies=None, max_role="readonly"))
        module.warn.assert_called_once()
        assert "role" in module.warn.call_args[0][0]

    def test_update_key_issuer_ttl_drift_warns(self, mock_api_client, mock_err):
        module = _module(
            public_key="-----BEGIN PUBLIC KEY-----\nOTHER\n-----END PUBLIC KEY-----",
            issuer="someone-else",
            token_ttl=3000,
        )
        blade = Mock()

        _run(update_client, module, blade, _client())

        module.warn.assert_called_once()
        msg = module.warn.call_args[0][0]
        for field in ("public_key", "issuer", "token_ttl"):
            assert field in msg
        assert "access_policies" not in msg
        module.exit_json.assert_called_once_with(changed=False)

    def test_update_public_key_whitespace_is_ignored(self, mock_api_client, mock_err):
        module = _module(public_key=PUB_KEY.replace("\n", " ") + "\n\n")
        blade = Mock()

        _run(update_client, module, blade, _client())

        module.warn.assert_not_called()

    def test_update_toggles_enabled(self, mock_api_client, mock_err):
        module = _module(enabled=False)
        blade = Mock()
        blade.patch_api_clients.return_value = _response(200)

        _run(update_client, module, blade, _client(enabled=True))

        mock_api_client.assert_called_once_with(enabled=False)
        blade.patch_api_clients.assert_called_once_with(
            names=["ansible-client"], api_clients=mock_api_client.return_value
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_update_toggle_check_mode_does_not_patch(self, mock_api_client, mock_err):
        module = _module(enabled=False)
        module.check_mode = True
        blade = Mock()

        _run(update_client, module, blade, _client(enabled=True))

        blade.patch_api_clients.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_update_patch_error_fails(self, mock_api_client, mock_err):
        module = _module(enabled=False)
        blade = Mock()
        blade.patch_api_clients.return_value = _response(400)

        _run(update_client, module, blade, _client(enabled=True))

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to update API Client ansible-client" in msg
        assert "boom" in msg


@patch("plugins.modules.purefb_apiclient.get_error_message", return_value="boom")
class TestPurefbApiclientDelete:
    """delete_client paths."""

    def test_delete_calls_api(self, mock_err):
        module = _module(state="absent")
        blade = Mock()
        blade.delete_api_clients.return_value = _response(200)

        _run(delete_client, module, blade)

        blade.delete_api_clients.assert_called_once_with(names=["ansible-client"])
        module.exit_json.assert_called_once_with(changed=True)

    def test_delete_check_mode(self, mock_err):
        module = _module(state="absent")
        module.check_mode = True
        blade = Mock()

        _run(delete_client, module, blade)

        blade.delete_api_clients.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_delete_error_fails(self, mock_err):
        module = _module(state="absent")
        blade = Mock()
        blade.delete_api_clients.return_value = _response(400)

        _run(delete_client, module, blade)

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to delete API Client ansible-client" in msg
        assert "boom" in msg


@patch("plugins.modules.purefb_apiclient.get_error_message", return_value="boom")
@patch("plugins.modules.purefb_apiclient.ApiClient")
@patch("plugins.modules.purefb_apiclient.ReferenceWritable", side_effect=_fake_ref)
@patch("plugins.modules.purefb_apiclient.ApiClientsPost")
@patch("plugins.modules.purefb_apiclient.LooseVersion")
@patch("plugins.modules.purefb_apiclient.get_rest_api_version", return_value="2.30")
@patch("plugins.modules.purefb_apiclient.get_system")
@patch("plugins.modules.purefb_apiclient.AnsibleModule")
class TestPurefbApiclientMain:
    """main() routing."""

    @staticmethod
    def _setup(mock_ansible_module, mock_get_system, mock_lv, **overrides):
        mock_lv.return_value.__le__ = Mock(return_value=True)
        module = _module(**overrides)
        mock_ansible_module.return_value = module
        blade = Mock()
        mock_get_system.return_value = blade
        return module, blade

    @patch("plugins.modules.purefb_apiclient.HAS_PYPURECLIENT", True)
    def test_main_creates_when_missing(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_lv,
        mock_post_model,
        mock_ref,
        mock_api_client,
        mock_err,
    ):
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_lv,
            access_policies=["readonly"],
            public_key=PUB_KEY,
        )
        mock_err.return_value = "API client does not exist."
        blade.get_api_clients.return_value = _response(400)
        blade.post_api_clients.return_value = _response(200)
        blade.patch_api_clients.return_value = _response(200)

        _run(main)

        mock_version.assert_called_once_with(blade)
        blade.get_api_clients.assert_called_once_with(names=["ansible-client"])
        assert mock_post_model.call_args[1]["access_policies"] == [("ref", "readonly")]
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_apiclient.HAS_PYPURECLIENT", True)
    def test_main_updates_when_present(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_lv,
        mock_post_model,
        mock_ref,
        mock_api_client,
        mock_err,
    ):
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_lv,
            access_policies=["readonly"],
        )
        blade.get_api_clients.return_value = _response(200, [_client()])

        _run(main)

        blade.post_api_clients.assert_not_called()
        blade.patch_api_clients.assert_not_called()
        module.warn.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_apiclient.HAS_PYPURECLIENT", True)
    def test_main_deletes_when_absent(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_lv,
        mock_post_model,
        mock_ref,
        mock_api_client,
        mock_err,
    ):
        module, blade = self._setup(
            mock_ansible_module, mock_get_system, mock_lv, state="absent"
        )
        blade.get_api_clients.return_value = _response(200, [_client()])
        blade.delete_api_clients.return_value = _response(200)

        _run(main)

        blade.delete_api_clients.assert_called_once_with(names=["ansible-client"])
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_apiclient.HAS_PYPURECLIENT", True)
    def test_main_absent_when_missing_is_noop(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_lv,
        mock_post_model,
        mock_ref,
        mock_api_client,
        mock_err,
    ):
        module, blade = self._setup(
            mock_ansible_module, mock_get_system, mock_lv, state="absent"
        )
        mock_err.return_value = "API client does not exist."
        blade.get_api_clients.return_value = _response(400)

        _run(main)

        blade.delete_api_clients.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_apiclient.HAS_PYPURECLIENT", True)
    def test_main_rejects_bad_name(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_lv,
        mock_post_model,
        mock_ref,
        mock_api_client,
        mock_err,
    ):
        module, blade = self._setup(
            mock_ansible_module, mock_get_system, mock_lv, name="bad name!"
        )

        _run(main)

        module.fail_json.assert_called_once()
        assert "naming convention" in module.fail_json.call_args[1]["msg"]
        mock_get_system.assert_not_called()

    @patch("plugins.modules.purefb_apiclient.HAS_PYPURECLIENT", True)
    def test_main_rejects_bad_issuer(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_lv,
        mock_post_model,
        mock_ref,
        mock_api_client,
        mock_err,
    ):
        module, blade = self._setup(
            mock_ansible_module, mock_get_system, mock_lv, issuer="-leading-dash"
        )

        _run(main)

        module.fail_json.assert_called_once()
        assert "Issuer" in module.fail_json.call_args[1]["msg"]
        mock_get_system.assert_not_called()

    @patch("plugins.modules.purefb_apiclient.HAS_PYPURECLIENT", True)
    def test_main_refuses_access_policies_on_old_api_before_create(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_lv,
        mock_post_model,
        mock_ref,
        mock_api_client,
        mock_err,
    ):
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_lv,
            access_policies=["readonly"],
            public_key=PUB_KEY,
        )
        mock_version.return_value = "2.17"
        mock_lv.return_value.__le__ = Mock(return_value=False)
        blade.get_api_clients.return_value = _response(400)

        _run(main)

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "2.17" in msg
        assert MIN_ACCESS_POLICIES_API_VERSION in msg
        blade.post_api_clients.assert_not_called()

    @patch("plugins.modules.purefb_apiclient.HAS_PYPURECLIENT", True)
    def test_main_refuses_access_policies_on_old_api_before_update(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_lv,
        mock_post_model,
        mock_ref,
        mock_api_client,
        mock_err,
    ):
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_lv,
            access_policies=["storage_admin"],
        )
        mock_version.return_value = "2.17"
        mock_lv.return_value.__le__ = Mock(return_value=False)
        blade.get_api_clients.return_value = _response(
            200, [_client(policies=None, max_role="readonly")]
        )

        _run(main)

        module.fail_json.assert_called_once()
        assert MIN_ACCESS_POLICIES_API_VERSION in module.fail_json.call_args[1]["msg"]
        module.warn.assert_not_called()
        blade.patch_api_clients.assert_not_called()

    @patch("plugins.modules.purefb_apiclient.HAS_PYPURECLIENT", True)
    def test_main_role_on_old_api_creates_with_max_role(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_lv,
        mock_post_model,
        mock_ref,
        mock_api_client,
        mock_err,
    ):
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_lv,
            role="readonly",
            public_key=PUB_KEY,
        )
        mock_version.return_value = "2.17"
        mock_lv.return_value.__le__ = Mock(return_value=False)
        mock_err.return_value = "API client does not exist."
        blade.get_api_clients.return_value = _response(400)
        blade.post_api_clients.return_value = _response(200)
        blade.patch_api_clients.return_value = _response(200)

        _run(main)

        kwargs = mock_post_model.call_args[1]
        assert kwargs["max_role"] == ("ref", "readonly")
        assert "access_policies" not in kwargs
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_apiclient.HAS_PYPURECLIENT", False)
    def test_main_fails_when_sdk_missing(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_lv,
        mock_post_model,
        mock_ref,
        mock_api_client,
        mock_err,
    ):
        module, blade = self._setup(mock_ansible_module, mock_get_system, mock_lv)

        _run(main)

        module.fail_json.assert_called_once()
        assert "py-pure-client" in module.fail_json.call_args[1]["msg"]
        mock_get_system.assert_not_called()

    @patch("plugins.modules.purefb_apiclient.HAS_PYPURECLIENT", True)
    def test_main_empty_get_creates_without_index_error(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_lv,
        mock_post_model,
        mock_ref,
        mock_api_client,
        mock_err,
    ):
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_lv,
            access_policies=["readonly"],
            public_key=PUB_KEY,
        )
        blade.get_api_clients.return_value = _response(200, [])
        blade.post_api_clients.return_value = _response(200)
        blade.patch_api_clients.return_value = _response(200)

        _run(main)

        blade.post_api_clients.assert_called_once()
        module.fail_json.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_apiclient.HAS_PYPURECLIENT", True)
    def test_main_get_error_fails_instead_of_creating(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_lv,
        mock_post_model,
        mock_ref,
        mock_api_client,
        mock_err,
    ):
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_lv,
            access_policies=["readonly"],
            public_key=PUB_KEY,
        )
        blade.get_api_clients.return_value = _response(500)

        _run(main)

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to get API Client ansible-client" in msg
        assert "boom" in msg
        blade.post_api_clients.assert_not_called()
        module.exit_json.assert_not_called()

    @patch("plugins.modules.purefb_apiclient.HAS_PYPURECLIENT", True)
    def test_main_absent_get_error_fails_instead_of_ok(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_lv,
        mock_post_model,
        mock_ref,
        mock_api_client,
        mock_err,
    ):
        module, blade = self._setup(
            mock_ansible_module, mock_get_system, mock_lv, state="absent"
        )
        blade.get_api_clients.return_value = _response(400)

        _run(main)

        module.fail_json.assert_called_once()
        assert "boom" in module.fail_json.call_args[1]["msg"]
        blade.delete_api_clients.assert_not_called()
        module.exit_json.assert_not_called()


@patch("plugins.modules.purefb_apiclient.get_error_message", return_value="boom")
class TestPurefbApiclientGetClient:
    """_get_client: only the array's not-found answer reads as None."""

    def test_get_client_returns_item(self, mock_err):
        module = _module()
        blade = Mock()
        client = _client()
        blade.get_api_clients.return_value = _response(200, [client])

        assert _get_client(module, blade) is client
        blade.get_api_clients.assert_called_once_with(names=["ansible-client"])
        module.fail_json.assert_not_called()

    def test_get_client_empty_list_is_none(self, mock_err):
        module = _module()
        blade = Mock()
        blade.get_api_clients.return_value = _response(200, [])

        assert _get_client(module, blade) is None
        module.fail_json.assert_not_called()

    def test_get_client_not_found_is_none(self, mock_err):
        mock_err.return_value = "API client does not exist."
        module = _module()
        blade = Mock()
        blade.get_api_clients.return_value = _response(400)

        assert _get_client(module, blade) is None
        module.fail_json.assert_not_called()

    def test_get_client_other_error_fails(self, mock_err):
        module = _module()
        blade = Mock()
        for status in (400, 403, 500):
            module.fail_json.reset_mock()
            blade.get_api_clients.return_value = _response(status)

            _run(_get_client, module, blade)

            module.fail_json.assert_called_once()
            msg = module.fail_json.call_args[1]["msg"]
            assert "Failed to get API Client ansible-client" in msg
            assert "boom" in msg


@patch("plugins.modules.purefb_apiclient.get_error_message", return_value="boom")
@patch("plugins.modules.purefb_apiclient.ApiClient")
@patch("plugins.modules.purefb_apiclient.ReferenceWritable", side_effect=_fake_ref)
@patch("plugins.modules.purefb_apiclient.ApiClientsPost")
@patch("plugins.modules.purefb_apiclient.LooseVersion")
@patch("plugins.modules.purefb_apiclient.get_rest_api_version", return_value="2.30")
@patch("plugins.modules.purefb_apiclient.get_system")
@patch("plugins.modules.purefb_apiclient.AnsibleModule")
@patch("plugins.modules.purefb_apiclient.HAS_PYPURECLIENT", True)
class TestPurefbApiclientArrayLevel:
    """API clients are array-level: realm names, realm-scoped policies and
    the answers an administrator limited to a realm gets."""

    _setup = staticmethod(TestPurefbApiclientMain._setup)

    def test_main_refuses_realm_qualified_name_before_login(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_lv,
        mock_post_model,
        mock_ref,
        mock_api_client,
        mock_err,
    ):
        for name in ("tenant1::ansible-client", "tenant1::", "::ansible-client"):
            for state in ("present", "absent"):
                for check_mode in (False, True):
                    module, blade = self._setup(
                        mock_ansible_module,
                        mock_get_system,
                        mock_lv,
                        name=name,
                        state=state,
                        access_policies=["readonly"],
                        public_key=PUB_KEY,
                    )
                    module.check_mode = check_mode

                    _run(main)

                    module.fail_json.assert_called_once_with(
                        msg="API Client name {0} does not conform to required "
                        "naming convention".format(name)
                    )
                    module.exit_json.assert_not_called()
        mock_get_system.assert_not_called()

    def test_main_refused_read_fails_in_every_state(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_lv,
        mock_post_model,
        mock_ref,
        mock_api_client,
        mock_err,
    ):
        mock_err.return_value = NOT_PERMITTED
        for params in (
            {},
            {"enabled": False},
            {"access_policies": ["readonly"], "public_key": PUB_KEY},
            {"state": "absent"},
        ):
            for check_mode in (False, True):
                module, blade = self._setup(
                    mock_ansible_module, mock_get_system, mock_lv, **params
                )
                module.check_mode = check_mode
                blade.get_api_clients.return_value = _response(400)

                _run(main)

                module.fail_json.assert_called_once_with(
                    msg="Failed to get API Client ansible-client. "
                    "Error: Operation not permitted."
                )
                blade.post_api_clients.assert_not_called()
                blade.patch_api_clients.assert_not_called()
                blade.delete_api_clients.assert_not_called()
                module.exit_json.assert_not_called()

    def test_main_creates_with_policy_scoped_to_a_realm(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_lv,
        mock_post_model,
        mock_ref,
        mock_api_client,
        mock_err,
    ):
        for check_mode in (True, False):
            module, blade = self._setup(
                mock_ansible_module,
                mock_get_system,
                mock_lv,
                access_policies=[REALM_POLICY],
                public_key=PUB_KEY,
            )
            module.check_mode = check_mode
            mock_err.return_value = NO_CLIENT
            blade.get_api_clients.return_value = _response(400)
            blade.post_api_clients.return_value = _response(200)
            blade.patch_api_clients.return_value = _response(200)

            _run(main)

            module.exit_json.assert_called_once_with(changed=True)
            if check_mode:
                blade.post_api_clients.assert_not_called()
        blade.post_api_clients.assert_called_once()
        assert blade.post_api_clients.call_args[1]["names"] == ["ansible-client"]
        assert mock_post_model.call_args[1]["access_policies"] == [
            ("ref", REALM_POLICY)
        ]

    def test_main_existing_client_with_realm_scoped_policy_is_unchanged(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_lv,
        mock_post_model,
        mock_ref,
        mock_api_client,
        mock_err,
    ):
        for check_mode in (False, True):
            module, blade = self._setup(
                mock_ansible_module,
                mock_get_system,
                mock_lv,
                access_policies=[REALM_POLICY],
                public_key=PUB_KEY,
            )
            module.check_mode = check_mode
            # The array reports no max_role for a client with a custom policy
            blade.get_api_clients.return_value = _response(
                200, [_client(policies=(REALM_POLICY,), max_role=None)]
            )

            _run(main)

            module.warn.assert_not_called()
            blade.post_api_clients.assert_not_called()
            blade.patch_api_clients.assert_not_called()
            module.exit_json.assert_called_once_with(changed=False)

    def test_main_sends_realm_qualified_policy_name_as_given(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_lv,
        mock_post_model,
        mock_ref,
        mock_api_client,
        mock_err,
    ):
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_lv,
            access_policies=["tenant1::" + REALM_POLICY],
            public_key=PUB_KEY,
        )
        mock_err.side_effect = [NO_CLIENT, NO_POLICY]
        blade.get_api_clients.return_value = _response(400)
        blade.post_api_clients.return_value = _response(400)

        _run(main)

        assert mock_post_model.call_args[1]["access_policies"] == [
            ("ref", "tenant1::" + REALM_POLICY)
        ]
        module.fail_json.assert_called_once_with(
            msg="Failed to create API Client ansible-client. Error message: "
            "Management access policy not exist."
        )
        blade.patch_api_clients.assert_not_called()
        module.exit_json.assert_not_called()

    def test_main_realm_qualified_policy_name_never_matches_the_policy(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        mock_lv,
        mock_post_model,
        mock_ref,
        mock_api_client,
        mock_err,
    ):
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_lv,
            access_policies=["tenant1::" + REALM_POLICY],
        )
        blade.get_api_clients.return_value = _response(
            200, [_client(policies=(REALM_POLICY,), max_role=None)]
        )

        _run(main)

        module.warn.assert_called_once()
        assert "access_policies cannot be changed" in module.warn.call_args[0][0]
        blade.patch_api_clients.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)


class TestPurefbApiclientDocumentation:
    """The documentation says where API clients live and what a policy
    scoped to a realm does not do."""

    @staticmethod
    def _text(lines):
        return " ".join(" ".join(lines).split())

    def test_description_says_api_clients_are_array_level(self):
        text = self._text(yaml.safe_load(DOCUMENTATION)["description"])
        assert "array-level objects" in text
        assert "cannot be placed in a realm" in text
        assert "limited to a realm may not read or change them" in text

    def test_name_says_a_realm_prefix_is_refused(self):
        option = yaml.safe_load(DOCUMENTATION)["options"]["name"]
        text = self._text(option["description"])
        assert "C(realm::name)" in text
        assert "refused" in text

    def test_access_policies_say_where_the_realm_scope_comes_from(self):
        option = yaml.safe_load(DOCUMENTATION)["options"]["access_policies"]
        text = self._text(option["description"])
        assert "comes from the policies of the user named in it" in text
        assert "does not confine the tokens of this API client" in text
        assert "named without a realm prefix" in text

    def test_examples_stay_at_array_level(self):
        tasks = [task[FQCN] for task in yaml.safe_load(EXAMPLES)]
        assert tasks
        for args in tasks:
            assert "::" not in args["name"]
            for policy in args.get("access_policies", []):
                assert "::" not in policy

    def test_examples_use_documented_options(self):
        documented = set(yaml.safe_load(DOCUMENTATION)["options"])
        documented.update(["fb_url", "api_token"])
        for task in yaml.safe_load(EXAMPLES):
            assert set(task[FQCN]) <= documented
