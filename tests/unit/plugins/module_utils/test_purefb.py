# Copyright: (c) 2026, Pure Storage Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb module utilities."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import importlib.util
import sys
from unittest.mock import Mock, patch, MagicMock

import pytest

# Mock external dependencies before importing purefb
sys.modules["pypureclient"] = MagicMock()
sys.modules["pypureclient.flashblade"] = MagicMock()
sys.modules["urllib3"] = MagicMock()
sys.modules["distro"] = MagicMock()

from plugins.module_utils import purefb
from plugins.module_utils.purefb import get_system, purefb_argument_spec

API_TOKEN = {"api_token": "T-11111111-2222-3333-4444-555555555555"}
ID_TOKEN = {"api_token": None, "id_token": "eyJhbGciOiJSUzI1NiJ9.payload.sig"}
PRIVATE_KEY = {
    "api_token": None,
    "id_token": None,
    "private_key_file": "/run/secrets/aap.pem",
    "private_key_password": None,
    "username": "realm-svc",
    "client_id": "cid-123",
    "key_id": "kid-456",
    "issuer": "AAP",
}
AUTH_MODES = pytest.mark.parametrize(
    "credentials",
    [API_TOKEN, ID_TOKEN, PRIVATE_KEY],
    ids=["api_token", "id_token", "private_key"],
)
API_CLIENT_MODES = pytest.mark.parametrize(
    "credentials", [ID_TOKEN, PRIVATE_KEY], ids=["id_token", "private_key"]
)

# The reason py-pure-client gives when Client() is refused by the array: the
# session login of an API token and the token exchange of an API client.
REFUSED_API_TOKEN = (
    'Failed to retrieve session token with error: {"error":[{"code": 401, '
    '"path": "/api/login", "message": "Authentication failed: Invalid API '
    'token."}]} (401)'
)
REFUSED_API_CLIENT = (
    "Could not retrieve a new access token: (403)\nReason: \n"
    "HTTP response headers: HTTPHeaderDict({'Server': 'nginx'})\n"
    'HTTP response body: {"error":"invalid_issuer","error_description":'
    '"Invalid issuer: Unknown Issuer: %s"}\n'
)
REFUSED_LOGINS = pytest.mark.parametrize(
    "credentials, reason, detail",
    [
        (API_TOKEN, REFUSED_API_TOKEN, "Authentication failed: Invalid API token."),
        (ID_TOKEN, REFUSED_API_CLIENT % "null", "Unknown Issuer: null"),
        (PRIVATE_KEY, REFUSED_API_CLIENT % "AAP", "Unknown Issuer: AAP"),
    ],
    ids=["api_token", "id_token", "private_key"],
)


class FakePureError(Exception):
    """pypureclient.PureError, which is mocked in this file: same text."""

    def __init__(self, reason=None):
        self.reason = reason
        super().__init__()

    def __str__(self):
        return "PureError: {0}".format(self.reason)


class FakeHTTPError(Exception):
    """Stands in for urllib3.exceptions.HTTPError, which is mocked in this file."""


def login_module(credentials):
    """Mock module that asks for a login with the given credentials."""
    module = Mock()
    module.params = {"fb_url": "flashblade.example.com", "disable_warnings": False}
    module.params.update(credentials)
    module.fail_json.side_effect = SystemExit("fail_json called")
    return module


def answered():
    """The answer of the array to a request the identity may make."""
    response = Mock()
    response.status_code = 200
    return response


def refused(message):
    """The answer of the array to a request the identity may not make."""
    response = Mock()
    response.status_code = 400
    error = Mock()
    error.message = message
    response.errors = [error]
    return response


class TestPurefbArgumentSpec:
    """Tests for purefb_argument_spec function."""

    def test_returns_dict(self):
        """Test that function returns a dictionary."""
        result = purefb_argument_spec()
        assert isinstance(result, dict)

    def test_contains_fb_url(self):
        """Test that spec contains fb_url."""
        result = purefb_argument_spec()
        assert "fb_url" in result
        assert result["fb_url"] == {}

    def test_contains_api_token(self):
        """Test that spec contains api_token with no_log."""
        result = purefb_argument_spec()
        assert "api_token" in result
        assert result["api_token"]["no_log"] is True

    def test_contains_disable_warnings(self):
        """Test that spec contains disable_warnings with defaults."""
        result = purefb_argument_spec()
        assert "disable_warnings" in result
        assert result["disable_warnings"]["type"] == "bool"
        assert result["disable_warnings"]["default"] is False

    def test_all_expected_keys(self):
        """Test that spec contains exactly the expected keys."""
        result = purefb_argument_spec()
        expected_keys = {
            "fb_url",
            "api_token",
            "id_token",
            "private_key_file",
            "private_key_password",
            "username",
            "client_id",
            "key_id",
            "issuer",
            "disable_warnings",
        }
        assert set(result.keys()) == expected_keys

    def test_token_auth_secrets_no_log(self):
        """Secret token-auth params must be marked no_log."""
        result = purefb_argument_spec()
        assert result["id_token"]["no_log"] is True
        assert result["private_key_password"]["no_log"] is True

    def test_non_secret_params_no_log_false(self):
        """Non-secret params that trip the no_log heuristic are silenced."""
        result = purefb_argument_spec()
        assert result["private_key_file"]["no_log"] is False
        assert result["key_id"]["no_log"] is False


class TestGetSystem:
    """Tests for get_system function."""

    @patch("plugins.module_utils.purefb.flashblade.Client")
    @patch("plugins.module_utils.purefb.HAS_PYPURECLIENT", True)
    def test_with_module_params(self, mock_client_class):
        """Test get_system with module parameters."""
        # Setup mock module
        mock_module = Mock()
        mock_module.params = {
            "fb_url": "https://flashblade.example.com",
            "api_token": "test-token-123",
            "disable_warnings": False,
        }

        # Setup mock FlashBlade client
        mock_client = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.get_hardware.return_value = mock_response
        mock_client_class.return_value = mock_client

        # Call function
        result = get_system(mock_module)

        # Verify client was created with correct params
        mock_client_class.assert_called_once()
        call_kwargs = mock_client_class.call_args[1]
        assert call_kwargs["target"] == "https://flashblade.example.com"
        assert call_kwargs["api_token"] == "test-token-123"
        assert "user_agent" in call_kwargs

        # Verify result is the client
        assert result == mock_client

    @patch("plugins.module_utils.purefb.flashblade.Client")
    @patch("plugins.module_utils.purefb.HAS_PYPURECLIENT", True)
    @patch("plugins.module_utils.purefb.environ")
    def test_with_environment_vars(self, mock_environ, mock_client_class):
        """Test get_system with environment variables."""
        # Setup mock module without params
        mock_module = Mock()
        mock_module.params = {
            "fb_url": None,
            "api_token": None,
            "disable_warnings": False,
        }

        # Setup environment variables
        env_vars = {
            "PUREFB_URL": "https://env-flashblade.example.com",
            "PUREFB_API": "env-token-456",
        }
        mock_environ.get.side_effect = env_vars.get

        # Setup mock FlashBlade client
        mock_client = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.get_hardware.return_value = mock_response
        mock_client_class.return_value = mock_client

        # Call function
        result = get_system(mock_module)

        # Verify client was created with env vars
        mock_client_class.assert_called_once()
        call_kwargs = mock_client_class.call_args[1]
        assert call_kwargs["target"] == "https://env-flashblade.example.com"
        assert call_kwargs["api_token"] == "env-token-456"

        # Verify result is the client
        assert result == mock_client

    @patch("plugins.module_utils.purefb.HAS_PYPURECLIENT", True)
    @patch("plugins.module_utils.purefb.environ")
    def test_missing_credentials(self, mock_environ):
        """Test that missing credentials causes failure."""
        # Setup mock module without params
        mock_module = Mock()
        mock_module.params = {
            "fb_url": None,
            "api_token": None,
            "disable_warnings": False,
        }
        # Make fail_json raise an exception to stop execution
        mock_module.fail_json.side_effect = SystemExit("fail_json called")

        # No environment variables
        mock_environ.get.return_value = None

        # Call function - should fail
        try:
            get_system(mock_module)
        except SystemExit:
            pass

        # Verify fail_json was called
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "PUREFB_URL" in call_args["msg"]
        assert "PUREFB_API" in call_args["msg"]

    @patch("plugins.module_utils.purefb.HAS_PYPURECLIENT", False)
    def test_missing_pypureclient(self):
        """Test that missing pypureclient causes failure."""
        mock_module = Mock()
        mock_module.params = {
            "fb_url": "https://flashblade.example.com",
            "api_token": "test-token",
            "disable_warnings": False,
        }
        # Make fail_json raise an exception to stop execution
        mock_module.fail_json.side_effect = SystemExit("fail_json called")

        # Call function - should fail
        try:
            get_system(mock_module)
        except SystemExit:
            pass

        # Verify fail_json was called
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "pypureclient SDK not installed" in call_args["msg"]

    @patch("plugins.module_utils.purefb.urllib3.disable_warnings")
    @patch("plugins.module_utils.purefb.flashblade.Client")
    @patch("plugins.module_utils.purefb.HAS_PYPURECLIENT", True)
    def test_disable_warnings(self, mock_client_class, mock_disable_warnings):
        """Test that warnings can be disabled."""
        # Setup mock module with disable_warnings=True
        mock_module = Mock()
        mock_module.params = {
            "fb_url": "https://flashblade.example.com",
            "api_token": "test-token",
            "disable_warnings": True,
        }

        # Setup mock FlashBlade client
        mock_client = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.get_hardware.return_value = mock_response
        mock_client_class.return_value = mock_client

        # Call function
        get_system(mock_module)

        # Verify urllib3.disable_warnings was called
        mock_disable_warnings.assert_called_once()

    @patch("plugins.module_utils.purefb.distro.name")
    @patch("plugins.module_utils.purefb.flashblade.Client")
    @patch("plugins.module_utils.purefb.HAS_PYPURECLIENT", True)
    @patch("plugins.module_utils.purefb.HAS_DISTRO", True)
    def test_user_agent_with_distro(self, mock_client_class, mock_distro_name):
        """Test user agent string includes distro info when available."""
        # Setup mock module
        mock_module = Mock()
        mock_module.params = {
            "fb_url": "https://flashblade.example.com",
            "api_token": "test-token",
            "disable_warnings": False,
        }

        # Setup mock distro
        mock_distro_name.return_value = "Ubuntu 22.04"

        # Setup mock FlashBlade client
        mock_client = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.get_hardware.return_value = mock_response
        mock_client_class.return_value = mock_client

        # Call function
        get_system(mock_module)

        # Verify user_agent contains distro info
        call_kwargs = mock_client_class.call_args[1]
        assert "Ubuntu 22.04" in call_kwargs["user_agent"]
        assert "Ansible" in call_kwargs["user_agent"]

    @patch("plugins.module_utils.purefb.flashblade.Client")
    @patch("plugins.module_utils.purefb.HAS_PYPURECLIENT", True)
    @patch("plugins.module_utils.purefb.environ")
    def test_with_id_token(self, mock_environ, mock_client_class):
        """Test get_system authenticates with a pre-signed id_token."""
        mock_environ.get.return_value = None
        mock_module = Mock()
        mock_module.params = {
            "fb_url": "https://flashblade.example.com",
            "api_token": None,
            "id_token": "eyJhbGciOiJSUzI1NiJ9.payload.sig",
            "disable_warnings": False,
        }
        mock_client = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.get_hardware.return_value = mock_response
        mock_client_class.return_value = mock_client

        result = get_system(mock_module)

        call_kwargs = mock_client_class.call_args[1]
        assert call_kwargs["target"] == "https://flashblade.example.com"
        assert call_kwargs["id_token"] == "eyJhbGciOiJSUzI1NiJ9.payload.sig"
        assert "api_token" not in call_kwargs
        assert result == mock_client

    @patch("plugins.module_utils.purefb.flashblade.Client")
    @patch("plugins.module_utils.purefb.HAS_PYPURECLIENT", True)
    @patch("plugins.module_utils.purefb.environ")
    def test_with_private_key(self, mock_environ, mock_client_class):
        """Test get_system authenticates with the private-key app flow."""
        mock_environ.get.return_value = None
        mock_module = Mock()
        mock_module.params = {
            "fb_url": "https://flashblade.example.com",
            "api_token": None,
            "id_token": None,
            "private_key_file": "/run/secrets/aap.pem",
            "private_key_password": "s3cret",
            "username": "automation",
            "client_id": "cid-123",
            "key_id": "kid-456",
            "issuer": "AAP",
            "disable_warnings": False,
        }
        mock_client = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.get_hardware.return_value = mock_response
        mock_client_class.return_value = mock_client

        result = get_system(mock_module)

        call_kwargs = mock_client_class.call_args[1]
        assert call_kwargs["target"] == "https://flashblade.example.com"
        assert call_kwargs["private_key_file"] == "/run/secrets/aap.pem"
        assert call_kwargs["private_key_password"] == "s3cret"
        assert call_kwargs["username"] == "automation"
        assert call_kwargs["client_id"] == "cid-123"
        assert call_kwargs["key_id"] == "kid-456"
        assert call_kwargs["issuer"] == "AAP"
        assert "api_token" not in call_kwargs
        assert result == mock_client

    @patch("plugins.module_utils.purefb.flashblade.Client")
    @patch("plugins.module_utils.purefb.HAS_PYPURECLIENT", True)
    @patch("plugins.module_utils.purefb.environ")
    def test_incomplete_private_key_set_fails(self, mock_environ, mock_client_class):
        """An incomplete private-key set (no username) must fail cleanly."""
        mock_module = Mock()
        mock_module.params = {
            "fb_url": "https://flashblade.example.com",
            "api_token": None,
            "id_token": None,
            "private_key_file": "/run/secrets/aap.pem",
            "private_key_password": None,
            "username": None,  # missing -> not a complete set
            "client_id": "cid-123",
            "key_id": "kid-456",
            "issuer": "AAP",
            "disable_warnings": False,
        }
        mock_module.fail_json.side_effect = SystemExit("fail_json called")
        mock_environ.get.return_value = None

        try:
            get_system(mock_module)
        except SystemExit:
            pass

        mock_module.fail_json.assert_called_once()
        mock_client_class.assert_not_called()


@patch("plugins.module_utils.purefb.urllib3.exceptions.HTTPError", FakeHTTPError)
@patch("plugins.module_utils.purefb.HAS_URLLIB3", True)
@patch("plugins.module_utils.purefb.HAS_PYPURECLIENT", True)
@patch("plugins.module_utils.purefb.environ")
@patch("plugins.module_utils.purefb.flashblade.Client")
class TestGetSystemLogin:
    """The login is the creation of the client, for every kind of identity."""

    @AUTH_MODES
    def test_array_admin_is_logged_in(
        self, mock_client_class, mock_environ, credentials
    ):
        """An array administrator gets the client, with no request sent."""
        mock_environ.get.return_value = None
        mock_module = login_module(credentials)
        mock_client = Mock()
        mock_client.get_hardware.return_value = answered()
        mock_client.get_arrays.return_value = answered()
        mock_client_class.return_value = mock_client

        result = get_system(mock_module)

        assert result == mock_client
        mock_client_class.assert_called_once()
        mock_module.fail_json.assert_not_called()

    @AUTH_MODES
    def test_login_sends_no_request(self, mock_client_class, mock_environ, credentials):
        """Creating the client is the login, nothing is read to verify it."""
        mock_environ.get.return_value = None
        mock_module = login_module(credentials)
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        get_system(mock_module)

        assert mock_client.mock_calls == []

    @AUTH_MODES
    def test_realm_scoped_identity_is_logged_in(
        self, mock_client_class, mock_environ, credentials
    ):
        """An administrator scoped to a realm may not read the hardware."""
        mock_environ.get.return_value = None
        mock_module = login_module(credentials)
        mock_client = Mock()
        mock_client.get_hardware.return_value = refused("Operation not permitted.")
        mock_client.get_arrays.return_value = answered()
        mock_client_class.return_value = mock_client

        result = get_system(mock_module)

        assert result == mock_client
        assert mock_client.mock_calls == []
        mock_module.fail_json.assert_not_called()

    @AUTH_MODES
    def test_custom_role_identity_is_logged_in(
        self, mock_client_class, mock_environ, credentials
    ):
        """A custom role may grant neither the hardware nor the array."""
        mock_environ.get.return_value = None
        mock_module = login_module(credentials)
        mock_client = Mock()
        mock_client.get_hardware.return_value = refused(
            "Operation not permitted. Authorization for 'get' on "
            "'purestorage.com/api/v2/hardware' is required."
        )
        mock_client.get_arrays.return_value = refused(
            "Operation not permitted. Authorization for 'get' on "
            "'purestorage.com/api/v2/arrays' is required."
        )
        mock_client_class.return_value = mock_client

        result = get_system(mock_module)

        assert result == mock_client
        assert mock_client.mock_calls == []
        mock_module.fail_json.assert_not_called()

    @REFUSED_LOGINS
    def test_refused_login_fails_cleanly(
        self, mock_client_class, mock_environ, credentials, reason, detail
    ):
        """The SDK raises while it creates the client for bad credentials."""
        mock_environ.get.return_value = None
        mock_module = login_module(credentials)
        mock_client_class.side_effect = FakePureError(reason)

        with pytest.raises(SystemExit):
            get_system(mock_module)

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert msg.startswith(
            "Failed to log in to FlashBlade flashblade.example.com. "
            "Error: PureError: "
        )
        assert detail in msg
        assert "Failed to connect" not in msg

    @AUTH_MODES
    def test_unreachable_array_fails_cleanly(
        self, mock_client_class, mock_environ, credentials
    ):
        """urllib3 errors escape the SDK for a wrong or unreachable address."""
        mock_environ.get.return_value = None
        mock_module = login_module(credentials)
        mock_client_class.side_effect = FakeHTTPError(
            "HTTPSConnectionPool(host='flashblade.example.com', port=443): "
            "Max retries exceeded with url: /api/api_version"
        )

        with pytest.raises(SystemExit):
            get_system(mock_module)

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert msg.startswith(
            "Failed to connect to FlashBlade flashblade.example.com. Error: "
        )
        assert "Max retries exceeded" in msg
        assert "log in" not in msg

    def test_no_common_rest_version_fails_cleanly(
        self, mock_client_class, mock_environ
    ):
        """The SDK raises ValueError when it shares no REST version."""
        mock_environ.get.return_value = None
        mock_module = login_module(API_TOKEN)
        mock_client_class.side_effect = ValueError(
            "No compatible REST version found between the client SDK and "
            "the target array."
        )

        with pytest.raises(SystemExit):
            get_system(mock_module)

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert msg.startswith("Failed to log in to FlashBlade flashblade.example.com.")
        assert "No compatible REST version" in msg

    @API_CLIENT_MODES
    def test_unwritable_token_cache_fails_cleanly(
        self, mock_client_class, mock_environ, credentials
    ):
        """The SDK saves the access token of an API client to a file."""
        mock_environ.get.return_value = None
        mock_module = login_module(credentials)
        mock_client_class.side_effect = PermissionError(
            13, "Permission denied", "oauth21.0token.access_token"
        )

        with pytest.raises(SystemExit):
            get_system(mock_module)

        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert msg.startswith("Failed to log in to FlashBlade flashblade.example.com.")
        assert "Permission denied: 'oauth21.0token.access_token'" in msg

    def test_connection_error_without_urllib3(self, mock_client_class, mock_environ):
        """Without urllib3 every failure is reported as a failed login."""
        mock_environ.get.return_value = None
        mock_module = login_module(API_TOKEN)
        mock_client_class.side_effect = FakeHTTPError("connection refused")

        with patch("plugins.module_utils.purefb.HAS_URLLIB3", False):
            with pytest.raises(SystemExit):
                get_system(mock_module)

        msg = mock_module.fail_json.call_args[1]["msg"]
        assert msg.startswith("Failed to log in to FlashBlade flashblade.example.com.")

    def test_missing_credentials_are_not_a_login_failure(
        self, mock_client_class, mock_environ
    ):
        """No login is attempted without a complete set of credentials."""
        mock_environ.get.return_value = None
        mock_module = login_module({"api_token": None})

        with pytest.raises(SystemExit):
            get_system(mock_module)

        mock_client_class.assert_not_called()
        mock_module.fail_json.assert_called_once()
        assert "PUREFB_URL" in mock_module.fail_json.call_args[1]["msg"]


class TestImportGuard:
    """The module must load, and say so, when the SDK is missing."""

    def test_missing_sdk_is_reported(self):
        """A failed SDK import clears the flag get_system() checks."""
        spec = importlib.util.spec_from_file_location(
            "purefb_without_sdk", purefb.__file__
        )
        module_copy = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"pypureclient": None}):
            spec.loader.exec_module(module_copy)

        assert module_copy.HAS_PYPURECLIENT is False

        mock_module = login_module(API_TOKEN)
        with pytest.raises(SystemExit):
            module_copy.get_system(mock_module)

        mock_module.fail_json.assert_called_once()
        assert (
            "pypureclient SDK not installed"
            in mock_module.fail_json.call_args[1]["msg"]
        )
