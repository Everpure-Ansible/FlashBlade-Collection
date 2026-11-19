# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_certs module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
from unittest.mock import Mock, patch, MagicMock

# Mock multiprocessing context for Windows
if sys.platform == "win32":
    original_get_context = multiprocessing.get_context

    def mock_get_context(method=None):
        if method == "fork":
            return original_get_context("spawn")
        return original_get_context(method)

    multiprocessing.get_context = mock_get_context

# Mock external dependencies before importing module
sys.modules["pypureclient"] = MagicMock()
sys.modules["pypureclient.flashblade"] = MagicMock()
sys.modules["urllib3"] = MagicMock()
sys.modules["distro"] = MagicMock()
sys.modules["pycountry"] = MagicMock()
# Mock Unix-specific modules for Windows compatibility
sys.modules["grp"] = MagicMock()
sys.modules["fcntl"] = MagicMock()
sys.modules["pwd"] = MagicMock()
sys.modules["syslog"] = MagicMock()
# Mock termios with required constants
mock_termios = MagicMock()
mock_termios.TCSAFLUSH = 2
sys.modules["termios"] = mock_termios
# Mock Ansible display module to avoid ctypes issues on Windows
sys.modules["ansible.utils.display"] = MagicMock()
sys.modules["ansible.utils.multiprocessing"] = MagicMock()
# Mock ansible_collections module
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

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import mock_open

import pytest

from plugins.module_utils.version import LooseVersion as RealLooseVersion
from plugins.modules import purefb_certs as certs_module
from plugins.modules.purefb_certs import main

MOD = "plugins.modules.purefb_certs"
MISSING = "Certificate does not exist."
NO_REALM = "Realm does not exist."
NOT_PERMITTED = "Operation not permitted."
ARRAY_TYPE_ONLY = (
    "Certificate signing request is only supported for array-type certificates."
)
PEM = "-----BEGIN CERTIFICATE-----\nREALM\n-----END CERTIFICATE-----"
CSR = "-----BEGIN CERTIFICATE REQUEST-----\nCSR\n-----END CERTIFICATE REQUEST-----"


def _error_text(response, default="Unknown error"):
    """get_error_message as module_utils.common implements it."""
    errors = getattr(response, "errors", None)
    if isinstance(errors, (list, tuple)) and errors:
        return errors[0].message
    return default


@pytest.fixture(autouse=True)
def array_error_text():
    """Report the message an error response carries, as the collection does."""
    with patch(MOD + ".get_error_message", side_effect=_error_text):
        yield


def _error_response(message, status_code=400):
    """An error response of the SDK: a status and the errors, no items."""
    res = Mock(spec=["status_code", "errors"])
    res.status_code = status_code
    res.errors = [SimpleNamespace(message=message)] if message else []
    return res


def _valid_response(items=None):
    """A successful response of the SDK."""
    res = Mock(spec=["status_code", "items"])
    res.status_code = 200
    res.items = list(items or [])
    return res


def _body(**kwargs):
    """Stand-in for the SDK models so request bodies are comparable."""
    return kwargs


def _cert(name, certificate_type="array", **fields):
    """A certificate as the array returns it."""
    realm = name.rsplit("::", 1)[0] if "::" in name else None
    cert = dict(
        name=name,
        realms=[SimpleNamespace(name=realm)] if realm else [],
        certificate=PEM,
        certificate_type=certificate_type,
        common_name="s3.example.com",
        country="US",
        email=None,
        intermediate_certificate=None,
        key_algorithm="rsa",
        key_size=2048,
        locality=None,
        organization="Acme Inc",
        organizational_unit="DevOps",
        state=None,
        status="self-signed" if certificate_type == "array" else "imported",
        subject_alternative_names=None,
    )
    cert.update(fields)
    return SimpleNamespace(**cert)


def _blade(certs=(), realms=None, read_error=None, csr_error=None):
    """A FlashBlade that holds I(certs) and I(realms) (name: destroyed).

    The array matches names without regard to case and answers a name it
    does not have with an error.
    """
    blade = Mock()
    stored = dict((cert.name.lower(), cert) for cert in certs)
    known_realms = {"realm1": False} if realms is None else realms

    def get_certificates(names=None, **kwargs):
        if read_error is not None:
            return read_error
        cert = stored.get(names[0].lower())
        if cert is None:
            return _error_response(MISSING)
        return _valid_response([cert])

    def get_realms(names=None, **kwargs):
        if not isinstance(known_realms, dict):
            return known_realms
        realm = names[0].lower()
        if realm not in known_realms:
            return _error_response(NO_REALM)
        return _valid_response(
            [SimpleNamespace(name=realm, destroyed=known_realms[realm])]
        )

    def post_csr(certificate=None, **kwargs):
        if csr_error is not None:
            return _error_response(csr_error)
        if certificate["certificate"]["name"].lower() not in stored:
            return _error_response(MISSING)
        return _valid_response([SimpleNamespace(certificate_signing_request=CSR)])

    blade.get_certificates.side_effect = get_certificates
    blade.get_realms.side_effect = get_realms
    blade.post_certificates_certificate_signing_requests.side_effect = post_csr
    blade.post_certificates.return_value = _valid_response()
    blade.patch_certificates.return_value = _valid_response()
    blade.delete_certificates.return_value = _valid_response()
    return blade


def _module(check_mode=False, **overrides):
    module = Mock()
    module.params = {
        "state": "present",
        "name": "realm1::cert",
        "generate": False,
        "certificate_type": None,
        "country": None,
        "province": None,
        "locality": None,
        "organization": None,
        "org_unit": None,
        "common_name": None,
        "email": None,
        "key_size": None,
        "certificate": None,
        "intermediate_cert": None,
        "key": None,
        "export_file": None,
        "passphrase": None,
        "days": None,
        "key_algorithm": None,
        "subject_alternative_names": None,
    }
    module.params.update(overrides)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _run(module, blade, api_version="2.30"):
    """Run main() against I(blade) and return the mock that stands for open()."""
    opened = mock_open()
    patches = [
        patch(MOD + ".AnsibleModule", return_value=module),
        patch(MOD + ".get_system", return_value=blade),
        patch(MOD + ".get_rest_api_version", return_value=api_version),
        patch(MOD + ".LooseVersion", RealLooseVersion),
        patch(MOD + ".HAS_PYPURECLIENT", True),
        patch(MOD + ".HAS_PYCOUNTRY", True),
        patch(MOD + ".pycountry"),
        patch(MOD + ".CertificatePost", side_effect=_body),
        patch(MOD + ".CertificatePatch", side_effect=_body),
        patch(MOD + ".CertificateSigningRequestPost", side_effect=_body),
        patch(MOD + ".Reference", side_effect=_body),
        patch("builtins.open", opened),
    ]
    with ExitStack() as stack:
        for item in patches:
            stack.enter_context(item)
        try:
            main()
        except SystemExit:
            pass
    return opened


def _changed(module):
    module.fail_json.assert_not_called()
    module.exit_json.assert_called_once()
    return module.exit_json.call_args[1]["changed"]


def _failure(module):
    module.exit_json.assert_not_called()
    module.fail_json.assert_called_once()
    return module.fail_json.call_args[1]["msg"]


def _no_writes(blade):
    blade.post_certificates.assert_not_called()
    blade.patch_certificates.assert_not_called()
    blade.delete_certificates.assert_not_called()
    blade.post_certificates_certificate_signing_requests.assert_not_called()


class TestPurefbCerts:
    """Test cases for purefb_certs module"""

    @patch("plugins.modules.purefb_certs.pycountry")
    @patch("plugins.modules.purefb_certs.LooseVersion")
    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_create_cert_with_intermediate(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_pycountry
    ):
        """Test creating a certificate with intermediate certificate"""
        # Setup mock module
        mock_module = Mock()
        # Make exit_json and fail_json raise exceptions to stop execution
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "present",
            "name": "test-cert",
            "common_name": "test.example.com",
            "country": "US",
            "province": "CA",
            "locality": "SF",
            "organization": "Test",
            "org_unit": "IT",
            "email": "test@example.com",
            "key_size": 2048,
            "certificate": None,
            "intermediate_cert": "-----BEGIN CERTIFICATE-----\nINTER\n-----END CERTIFICATE-----",
            "key": None,
            "passphrase": None,
            "generate": False,
            "days": 3650,
            "key_algorithm": None,
            "export_file": None,
            "certificate_type": None,
            "subject_alternative_names": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.15"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock API version checks - all feature gates OFF (pre-2.15 behavior)
        mock_loose_version.return_value.__le__ = Mock(return_value=False)

        # Mock array name
        mock_array = Mock()
        mock_array.name = "test-array"
        mock_blade.get_arrays.return_value.items = [mock_array]

        # Certificate doesn't exist
        mock_blade.get_certificates.return_value = _error_response(MISSING)

        # Mock successful creation
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.post_certificates.return_value = mock_response

        mock_get_system.return_value = mock_blade

        # Mock pycountry
        mock_country = Mock()
        mock_pycountry.countries.get.return_value = mock_country

        # Call main - expect SystemExit from exit_json
        try:
            main()
        except SystemExit:
            pass

        # Verify certificate was created
        mock_blade.post_certificates.assert_called_once()
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is True

    @patch("plugins.modules.purefb_certs.pycountry")
    @patch("plugins.modules.purefb_certs.LooseVersion")
    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_update_cert_uses_patch(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_pycountry
    ):
        """Test BUG #4 fix: update_cert uses CertificatePatch, not CertificatePost"""
        # Setup mock module
        mock_module = Mock()
        # Make exit_json and fail_json raise exceptions to stop execution
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "present",
            "name": "management",
            "common_name": None,
            "country": None,
            "province": None,
            "locality": None,
            "organization": None,
            "org_unit": None,
            "email": None,
            "key_size": None,
            "certificate": "-----BEGIN CERTIFICATE-----\nNEW\n-----END CERTIFICATE-----",
            "intermediate_cert": "-----BEGIN CERTIFICATE-----\nINTER\n-----END CERTIFICATE-----",
            "key": "-----BEGIN PRIVATE KEY-----\nKEY\n-----END PRIVATE KEY-----",
            "passphrase": "secret",
            "generate": False,
            "days": 3650,
            "key_algorithm": None,
            "export_file": None,
            "certificate_type": None,
            "subject_alternative_names": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.20"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock API version check - CSR feature gate OFF (old unconfigured-mock behavior)
        mock_loose_version.return_value.__le__ = Mock(return_value=False)

        # Mock array name
        mock_array = Mock()
        mock_array.name = "test-array"
        mock_blade.get_arrays.return_value.items = [mock_array]

        # Certificate exists
        mock_blade.get_certificates.return_value.status_code = 200

        # Mock existing certificate
        mock_cert = Mock()
        mock_cert.certificate = (
            "-----BEGIN CERTIFICATE-----\nOLD\n-----END CERTIFICATE-----"
        )
        mock_cert.intermediate_certificate = None
        mock_cert.common_name = "old.example.com"
        mock_cert.country = "US"
        mock_cert.email = "old@example.com"
        mock_cert.key_size = 2048
        mock_cert.locality = "SF"
        mock_cert.state = "CA"
        mock_cert.organization = "Old Org"
        mock_cert.organizational_unit = "IT"
        mock_cert.key_algorithm = "rsa"

        # Mock copy method to return a new object
        new_cert = Mock()
        new_cert.certificate = mock_module.params["certificate"]
        new_cert.intermediate_certificate = mock_module.params["intermediate_cert"]
        new_cert.common_name = "old.example.com"
        new_cert.country = "US"
        new_cert.email = "old@example.com"
        new_cert.key_size = 2048
        new_cert.locality = "SF"
        new_cert.state = "CA"
        new_cert.organization = "Old Org"
        new_cert.organizational_unit = "IT"
        new_cert.key_algorithm = "rsa"
        new_cert.__ne__ = Mock(return_value=True)  # new_cert != current_cert

        mock_cert.copy = Mock(return_value=new_cert)
        mock_blade.get_certificates.return_value.items = [mock_cert]

        # Mock successful update
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_certificates.return_value = mock_response

        mock_get_system.return_value = mock_blade

        # Call main - expect SystemExit from exit_json
        try:
            main()
        except SystemExit:
            pass

        # Verify patch_certificates was called (not post_certificates)
        mock_blade.patch_certificates.assert_called_once()
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is True

    @patch("plugins.modules.purefb_certs.LooseVersion")
    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_import_cert_check_mode(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test BUG #3 fix: import_cert doesn't raise NameError in check_mode"""
        # Setup mock module
        mock_module = Mock()
        # Make exit_json and fail_json raise exceptions to stop execution
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "import",
            "name": "test-cert",
            "common_name": None,
            "country": None,
            "province": None,
            "locality": None,
            "organization": None,
            "org_unit": None,
            "email": None,
            "key_size": 2048,
            "certificate": "-----BEGIN CERTIFICATE-----\nCERT\n-----END CERTIFICATE-----",
            "intermediate_cert": None,
            "key": None,
            "passphrase": None,
            "generate": False,
            "days": 3650,
            "key_algorithm": None,
            "export_file": None,
            "certificate_type": None,
            "subject_alternative_names": None,
        }
        mock_module.check_mode = True  # This is the key - check_mode enabled
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.10"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Mock API version checks - all feature gates OFF (pre-2.15 behavior)
        mock_loose_version.return_value.__le__ = Mock(return_value=False)

        # Certificate doesn't exist
        mock_blade.get_certificates.return_value = _error_response(MISSING)

        mock_get_system.return_value = mock_blade

        # Call main - should NOT raise NameError, expect SystemExit from exit_json
        try:
            main()
        except SystemExit:
            pass

        # Verify post_certificates was NOT called in check mode
        mock_blade.post_certificates.assert_not_called()

        # Verify exit_json was called with changed=True (no error)
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is True

    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_delete_cert_global_fails(self, mock_ansible_module, mock_get_system):
        """Test delete_cert fails when trying to delete global certificate"""
        # Setup mock module
        mock_module = Mock()
        # Make exit_json and fail_json raise exceptions to stop execution
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "absent",
            "name": "global",
            "common_name": None,
            "country": None,
            "province": None,
            "locality": None,
            "organization": None,
            "org_unit": None,
            "email": None,
            "key_size": 2048,
            "certificate": None,
            "intermediate_cert": None,
            "key": None,
            "passphrase": None,
            "generate": False,
            "days": 3650,
            "key_algorithm": None,
            "export_file": None,
            "certificate_type": None,
            "subject_alternative_names": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.10"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Certificate exists
        mock_blade.get_certificates.return_value.status_code = 200

        mock_get_system.return_value = mock_blade

        # Call main - expect SystemExit from fail_json
        try:
            main()
        except SystemExit:
            pass

        # Verify fail_json was called
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "Global certificate cannot be deleted" in call_args["msg"]

    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_delete_cert_success(self, mock_ansible_module, mock_get_system):
        """Test delete_cert successfully deletes non-management certificate"""
        # Setup mock module
        mock_module = Mock()
        # Make exit_json and fail_json raise exceptions to stop execution
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "absent",
            "name": "test-cert",
            "common_name": None,
            "country": None,
            "province": None,
            "locality": None,
            "organization": None,
            "org_unit": None,
            "email": None,
            "key_size": 2048,
            "certificate": None,
            "intermediate_cert": None,
            "key": None,
            "passphrase": None,
            "generate": False,
            "days": 3650,
            "key_algorithm": None,
            "export_file": None,
            "certificate_type": None,
            "subject_alternative_names": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.10"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Certificate exists
        mock_blade.get_certificates.return_value.status_code = 200

        # Mock successful deletion
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.delete_certificates.return_value = mock_response

        mock_get_system.return_value = mock_blade

        # Call main - expect SystemExit from exit_json
        try:
            main()
        except SystemExit:
            pass

        # Verify delete_certificates was called
        mock_blade.delete_certificates.assert_called_once_with(names=["test-cert"])

        # Verify exit_json was called with changed=True
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is True

    @patch("plugins.modules.purefb_certs.pycountry")
    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_export_cert_success(
        self, mock_ansible_module, mock_get_system, mock_pycountry
    ):
        """Test export_cert successfully exports certificate"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "export",
            "name": "test-cert",
            "export_file": "test_cert.pem",
            "common_name": None,
            "country": None,
            "province": None,
            "locality": None,
            "organization": None,
            "org_unit": None,
            "email": None,
            "key_size": None,
            "certificate": None,
            "intermediate_cert": None,
            "key": None,
            "passphrase": None,
            "generate": False,
            "days": None,
            "key_algorithm": None,
            "certificate_type": None,
            "subject_alternative_names": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.15"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Certificate exists
        mock_cert_response = Mock()
        mock_cert_response.status_code = 200
        mock_cert = Mock()
        mock_cert.certificate = (
            "-----BEGIN CERTIFICATE-----\nTEST\n-----END CERTIFICATE-----"
        )
        mock_cert_response.items = [mock_cert]
        mock_blade.get_certificates.return_value = mock_cert_response

        mock_get_system.return_value = mock_blade

        # Mock file operations
        with patch("builtins.open", create=True) as mock_open:
            mock_file = Mock()
            mock_open.return_value.__enter__.return_value = mock_file

            # Call main
            try:
                main()
            except SystemExit:
                pass

            # Verify file was written
            mock_open.assert_called_once_with("test_cert.pem", "w", encoding="utf-8")
            mock_file.write.assert_called_once_with(
                "-----BEGIN CERTIFICATE-----\nTEST\n-----END CERTIFICATE-----"
            )

        # Verify exit_json was called with changed=True
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is True

    @patch("plugins.modules.purefb_certs.pycountry")
    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_export_cert_failure(
        self, mock_ansible_module, mock_get_system, mock_pycountry
    ):
        """Test export_cert fails when certificate doesn't exist"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "export",
            "name": "nonexistent-cert",
            "export_file": "test_cert.pem",
            "common_name": None,
            "country": None,
            "province": None,
            "locality": None,
            "organization": None,
            "org_unit": None,
            "email": None,
            "key_size": None,
            "certificate": None,
            "intermediate_cert": None,
            "key": None,
            "passphrase": None,
            "generate": False,
            "days": None,
            "key_algorithm": None,
            "certificate_type": None,
            "subject_alternative_names": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.15"
        mock_blade.get_versions.return_value.items = [mock_version]

        # Certificate doesn't exist
        mock_cert_response = Mock()
        mock_cert_response.status_code = 400
        mock_error = Mock()
        mock_error.message = MISSING
        mock_cert_response.errors = [mock_error]
        mock_blade.get_certificates.return_value = mock_cert_response

        mock_get_system.return_value = mock_blade

        # Call main - expect failure
        try:
            main()
        except SystemExit:
            pass

        # Verify fail_json was called
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "Exporting Certificate failed" in call_args["msg"]

    @patch("plugins.modules.purefb_certs.pycountry")
    @patch("plugins.modules.purefb_certs.LooseVersion")
    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_create_csr_success(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_pycountry
    ):
        """Test create_csr successfully creates CSR"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "sign",
            "name": "test-cert",
            "export_file": "test_csr.pem",
            "common_name": "test.example.com",
            "country": "US",
            "province": "CA",
            "locality": "SF",
            "organization": "Test Org",
            "org_unit": "IT",
            "email": "test@example.com",
            "key_size": None,
            "certificate": None,
            "intermediate_cert": None,
            "key": None,
            "passphrase": None,
            "generate": False,
            "days": None,
            "key_algorithm": None,
            "certificate_type": None,
            "subject_alternative_names": ["alt.example.com"],
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade with CSR API support
        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.20"
        mock_blade.get_versions.return_value.items = ["2.20"]

        # Mock API version check - CSR min-version gate passes (API >= 2.20)
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        # Certificate exists
        mock_blade.get_certificates.return_value.status_code = 200

        # Mock CSR response
        mock_csr_item = Mock()
        mock_csr_item.certificate_signing_request = [
            "-----BEGIN CERTIFICATE REQUEST-----\n",
            "CSR_CONTENT\n",
            "-----END CERTIFICATE REQUEST-----\n",
        ]
        mock_csr_response = Mock()
        mock_csr_response.status_code = 200
        mock_csr_response.items = [mock_csr_item]
        mock_blade.post_certificates_certificate_signing_requests.return_value = (
            mock_csr_response
        )

        mock_get_system.return_value = mock_blade

        # Mock pycountry
        mock_country = Mock()
        mock_pycountry.countries.get.return_value = mock_country

        # Mock file operations
        with patch("builtins.open", create=True) as mock_open:
            mock_file = Mock()
            mock_open.return_value.__enter__.return_value = mock_file

            # Call main
            try:
                main()
            except SystemExit:
                pass

            # Verify file was written
            mock_open.assert_called_once_with("test_csr.pem", "w", encoding="utf-8")
            mock_file.write.assert_called_once()

        # Verify exit_json was called with changed=True
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is True

    @patch("plugins.modules.purefb_certs.LooseVersion")
    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_create_csr_old_api_fails(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test create_csr fails on old API version"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "sign",
            "name": "test-cert",
            "export_file": "test_csr.pem",
            "common_name": None,
            "country": None,
            "province": None,
            "locality": None,
            "organization": None,
            "org_unit": None,
            "email": None,
            "key_size": None,
            "certificate": None,
            "intermediate_cert": None,
            "key": None,
            "passphrase": None,
            "generate": False,
            "days": None,
            "key_algorithm": None,
            "certificate_type": None,
            "subject_alternative_names": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade with old API version
        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.15"
        mock_blade.get_versions.return_value.items = ["2.15"]

        # Mock API version check - CSR min-version gate fails (API < 2.20)
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)

        mock_get_system.return_value = mock_blade

        # Call main - expect failure
        try:
            main()
        except SystemExit:
            pass

        # Verify fail_json was called
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "Purity//FB 4.6.3+ is required for CSRs" in call_args["msg"]

    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_invalid_email(self, mock_ansible_module, mock_get_system):
        """Test validation fails for invalid email"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "sign",
            "name": "test-cert",
            "export_file": "test_csr.pem",
            "common_name": "test.example.com",
            "country": None,
            "province": None,
            "locality": None,
            "organization": None,
            "org_unit": None,
            "email": "invalid-email",  # Invalid email
            "key_size": None,
            "certificate": None,
            "intermediate_cert": None,
            "key": None,
            "passphrase": None,
            "generate": False,
            "days": None,
            "key_algorithm": None,
            "certificate_type": None,
            "subject_alternative_names": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        mock_get_system.return_value = mock_blade

        # Call main - expect failure
        try:
            main()
        except SystemExit:
            pass

        # Verify fail_json was called
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "is not valid" in call_args["msg"]

    @patch("plugins.modules.purefb_certs.pycountry")
    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_invalid_country_length(
        self, mock_ansible_module, mock_get_system, mock_pycountry
    ):
        """Test validation fails for invalid country code length"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "sign",
            "name": "test-cert",
            "export_file": "test_csr.pem",
            "common_name": "test.example.com",
            "country": "USA",  # Invalid - should be 2 letters
            "province": None,
            "locality": None,
            "organization": None,
            "org_unit": None,
            "email": None,
            "key_size": None,
            "certificate": None,
            "intermediate_cert": None,
            "key": None,
            "passphrase": None,
            "generate": False,
            "days": None,
            "key_algorithm": None,
            "certificate_type": None,
            "subject_alternative_names": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        mock_get_system.return_value = mock_blade

        # Call main - expect failure
        try:
            main()
        except SystemExit:
            pass

        # Verify fail_json was called
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "two-letter country" in call_args["msg"]

    @patch("plugins.modules.purefb_certs.pycountry")
    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_invalid_country_code(
        self, mock_ansible_module, mock_get_system, mock_pycountry
    ):
        """Test validation fails for invalid country code"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "sign",
            "name": "test-cert",
            "export_file": "test_csr.pem",
            "common_name": "test.example.com",
            "country": "XX",  # Invalid ISO code
            "province": None,
            "locality": None,
            "organization": None,
            "org_unit": None,
            "email": None,
            "key_size": None,
            "certificate": None,
            "intermediate_cert": None,
            "key": None,
            "passphrase": None,
            "generate": False,
            "days": None,
            "key_algorithm": None,
            "certificate_type": None,
            "subject_alternative_names": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]
        mock_get_system.return_value = mock_blade

        # Mock pycountry - return None for invalid code
        mock_pycountry.countries.get.return_value = None

        # Call main - expect failure
        try:
            main()
        except SystemExit:
            pass

        # Verify fail_json was called
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "ISO 3166-1 code" in call_args["msg"]

    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", False)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_no_pypureclient(self, mock_ansible_module):
        """Test module fails when pypureclient is not installed"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "present",
            "name": "test-cert",
            "export_file": None,
            "common_name": None,
            "country": None,
            "province": None,
            "locality": None,
            "organization": None,
            "org_unit": None,
            "email": None,
            "key_size": None,
            "certificate": "cert_content",
            "intermediate_cert": None,
            "key": "key_content",
            "passphrase": None,
            "generate": False,
            "days": None,
            "key_algorithm": None,
            "certificate_type": None,
            "subject_alternative_names": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Call main - expect failure
        try:
            main()
        except SystemExit:
            pass

        # Verify fail_json was called
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "py-pure-client sdk is required" in call_args["msg"]

    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", False)
    def test_main_no_pycountry(self, mock_ansible_module):
        """Test module fails when pycountry is not installed"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "present",
            "name": "test-cert",
            "export_file": None,
            "common_name": None,
            "country": None,
            "province": None,
            "locality": None,
            "organization": None,
            "org_unit": None,
            "email": None,
            "key_size": None,
            "certificate": "cert_content",
            "intermediate_cert": None,
            "key": "key_content",
            "passphrase": None,
            "generate": False,
            "days": None,
            "key_algorithm": None,
            "certificate_type": None,
            "subject_alternative_names": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Call main - expect failure
        try:
            main()
        except SystemExit:
            pass

        # Verify fail_json was called
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "pycountry sdk is required" in call_args["msg"]

    @patch("plugins.modules.purefb_certs.pycountry")
    @patch("plugins.modules.purefb_certs.LooseVersion")
    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_update_cert_old_api(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_pycountry
    ):
        """Test update_cert with old API version (< 2.20)"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "present",
            "name": "existing-cert",
            "export_file": None,
            "common_name": None,
            "country": None,
            "province": None,
            "locality": None,
            "organization": None,
            "org_unit": None,
            "email": None,
            "key_size": None,
            "certificate": "new_cert_content",
            "intermediate_cert": "intermediate_content",
            "key": "new_key_content",
            "passphrase": "secret",
            "generate": False,
            "days": None,
            "key_algorithm": None,
            "certificate_type": None,
            "subject_alternative_names": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade with old API version
        mock_blade = Mock()
        mock_version = Mock()
        mock_version.version = "2.15"
        mock_blade.get_versions.return_value.items = ["2.15"]

        # Mock API version check - CSR feature gate OFF (API < 2.20)
        mock_loose_version.return_value.__le__ = Mock(return_value=False)

        # Certificate exists
        mock_blade.get_certificates.return_value.status_code = 200
        mock_cert = Mock()
        mock_cert.certificate = "old_cert_content"
        mock_cert.intermediate_certificate = None
        mock_cert.subject_alternative_names = []
        mock_blade.get_certificates.return_value.items = [mock_cert]

        # Mock successful patch
        mock_patch_response = Mock()
        mock_patch_response.status_code = 200
        mock_blade.patch_certificates.return_value = mock_patch_response

        mock_get_system.return_value = mock_blade

        # Call main
        try:
            main()
        except SystemExit:
            pass

        # Verify patch_certificates was called (old API path)
        mock_blade.patch_certificates.assert_called_once()
        call_args = mock_blade.patch_certificates.call_args

        # Verify it was called with basic parameters (not extended)
        assert "names" in call_args[1]
        assert "certificate" in call_args[1]
        # Should NOT have generate_new_key (that's only for new API)
        assert "generate_new_key" not in call_args[1]

        # Verify exit_json was called with changed=True
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is True

    @patch("plugins.modules.purefb_certs.CertificatePatch")
    @patch("plugins.modules.purefb_certs.pycountry")
    @patch("plugins.modules.purefb_certs.LooseVersion")
    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_update_cert_new_api(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_pycountry,
        mock_certificate_patch,
    ):
        """Test update_cert with new API version (>= 2.20)"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "present",
            "name": "existing-cert",
            "export_file": None,
            "common_name": "test.example.com",
            "country": "US",
            "province": "CA",
            "locality": "SF",
            "organization": "Test Org",
            "org_unit": "IT",
            "email": "test@example.com",
            "key_size": 2048,
            "certificate": "new_cert_content",
            "intermediate_cert": "intermediate_content",
            "key": "new_key_content",
            "passphrase": "secret",
            "generate": True,
            "days": 365,
            "key_algorithm": None,
            "certificate_type": None,
            "subject_alternative_names": ["alt.example.com"],
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade with new API version
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]

        # Mock API version check - CSR feature gate ON (API >= 2.20)
        mock_loose_version.return_value.__le__ = Mock(return_value=True)

        # Certificate exists
        mock_blade.get_certificates.return_value.status_code = 200
        mock_cert = Mock()
        mock_cert.certificate = "old_cert_content"
        mock_cert.intermediate_certificate = None
        mock_cert.subject_alternative_names = []
        mock_blade.get_certificates.return_value.items = [mock_cert]

        # Mock successful patch
        mock_patch_response = Mock()
        mock_patch_response.status_code = 200
        mock_blade.patch_certificates.return_value = mock_patch_response

        mock_get_system.return_value = mock_blade

        # Mock pycountry
        mock_country = Mock()
        mock_pycountry.countries.get.return_value = mock_country

        # Call main
        try:
            main()
        except SystemExit:
            pass

        # Verify patch_certificates was called (new API path)
        mock_blade.patch_certificates.assert_called_once()
        call_args = mock_blade.patch_certificates.call_args

        # Verify it was called with extended parameters
        assert "names" in call_args[1]
        assert "certificate" in call_args[1]
        assert "generate_new_key" in call_args[1]
        assert call_args[1]["generate_new_key"] is True
        # key parameters only travel together with generate_new_key
        mock_certificate_patch.assert_called_once()
        assert mock_certificate_patch.call_args[1]["key_size"] == 2048

        # Verify exit_json was called with changed=True
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is True

    @patch("plugins.modules.purefb_certs.pycountry")
    @patch("plugins.modules.purefb_certs.LooseVersion")
    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_update_cert_new_api_fails(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_pycountry
    ):
        """Test update_cert fails with new API version"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "present",
            "name": "existing-cert",
            "export_file": None,
            "common_name": "test.example.com",
            "country": "US",
            "province": None,
            "locality": None,
            "organization": None,
            "org_unit": None,
            "email": "test@example.com",
            "key_size": None,
            "certificate": "new_cert_content",
            "intermediate_cert": None,
            "key": "new_key_content",
            "passphrase": None,
            "generate": False,
            "days": None,
            "key_algorithm": None,
            "certificate_type": None,
            "subject_alternative_names": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade with new API version
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]

        # Mock API version check - CSR feature gate ON (API >= 2.20)
        mock_loose_version.return_value.__le__ = Mock(return_value=True)

        # Certificate exists
        mock_blade.get_certificates.return_value.status_code = 200
        mock_cert = Mock()
        mock_cert.certificate = "old_cert_content"
        mock_cert.intermediate_certificate = None
        mock_cert.subject_alternative_names = []
        mock_blade.get_certificates.return_value.items = [mock_cert]

        # Mock failed patch
        mock_patch_response = Mock()
        mock_patch_response.status_code = 400
        mock_error = Mock()
        mock_error.message = "Invalid certificate"
        mock_patch_response.errors = [mock_error]
        mock_blade.patch_certificates.return_value = mock_patch_response

        mock_get_system.return_value = mock_blade

        # Mock pycountry
        mock_country = Mock()
        mock_pycountry.countries.get.return_value = mock_country

        # Call main - expect failure
        try:
            main()
        except SystemExit:
            pass

        # Verify fail_json was called
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "Updating existing SSL certificate" in call_args["msg"]

    @patch("plugins.modules.purefb_certs.pycountry")
    @patch("plugins.modules.purefb_certs.LooseVersion")
    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_update_cert_old_api_fails(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_pycountry
    ):
        """Test update_cert fails with old API version"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "present",
            "name": "existing-cert",
            "export_file": None,
            "common_name": None,
            "country": None,
            "province": None,
            "locality": None,
            "organization": None,
            "org_unit": None,
            "email": None,
            "key_size": None,
            "certificate": "new_cert_content",
            "intermediate_cert": None,
            "key": "new_key_content",
            "passphrase": None,
            "generate": False,
            "days": None,
            "key_algorithm": None,
            "certificate_type": None,
            "subject_alternative_names": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade with old API version
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.15"]

        # Mock API version check - CSR feature gate OFF (API < 2.20)
        mock_loose_version.return_value.__le__ = Mock(return_value=False)

        # Certificate exists
        mock_blade.get_certificates.return_value.status_code = 200
        mock_cert = Mock()
        mock_cert.certificate = "old_cert_content"
        mock_cert.intermediate_certificate = None
        mock_cert.subject_alternative_names = []
        mock_blade.get_certificates.return_value.items = [mock_cert]

        # Mock failed patch
        mock_patch_response = Mock()
        mock_patch_response.status_code = 400
        mock_error = Mock()
        mock_error.message = "Invalid certificate"
        mock_patch_response.errors = [mock_error]
        mock_blade.patch_certificates.return_value = mock_patch_response

        mock_get_system.return_value = mock_blade

        # Call main - expect failure
        try:
            main()
        except SystemExit:
            pass

        # Verify fail_json was called
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "Updating existing SSL certificate" in call_args["msg"]

    @patch("plugins.modules.purefb_certs.pycountry")
    @patch("plugins.modules.purefb_certs.LooseVersion")
    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_create_cert_new_api_fails(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_pycountry
    ):
        """Test create_cert fails with new API version"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "present",
            "name": "new-cert",
            "export_file": None,
            "common_name": "test.example.com",
            "country": "US",
            "province": None,
            "locality": None,
            "organization": None,
            "org_unit": None,
            "email": "test@example.com",
            "key_size": None,
            "certificate": "cert_content",
            "intermediate_cert": None,
            "key": "key_content",
            "passphrase": None,
            "generate": False,
            "days": None,
            "key_algorithm": None,
            "certificate_type": "self-signed",
            "subject_alternative_names": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade with new API version
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.20"]

        # Mock API version check - CSR feature gate ON (API >= 2.20)
        mock_loose_version.return_value.__le__ = Mock(return_value=True)

        # Certificate doesn't exist
        mock_blade.get_certificates.return_value = _error_response(MISSING)

        # Mock failed post
        mock_post_response = Mock()
        mock_post_response.status_code = 400
        mock_error = Mock()
        mock_error.message = "Invalid certificate"
        mock_post_response.errors = [mock_error]
        mock_blade.post_certificates.return_value = mock_post_response

        mock_get_system.return_value = mock_blade

        # Mock pycountry
        mock_country = Mock()
        mock_pycountry.countries.get.return_value = mock_country

        # Call main - expect failure
        try:
            main()
        except SystemExit:
            pass

        # Verify fail_json was called
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "Creating SSL certificate" in call_args["msg"]

    @patch("plugins.modules.purefb_certs.pycountry")
    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_delete_cert_fails(
        self, mock_ansible_module, mock_get_system, mock_pycountry
    ):
        """Test delete_cert fails"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "absent",
            "name": "test-cert",
            "export_file": None,
            "common_name": None,
            "country": None,
            "province": None,
            "locality": None,
            "organization": None,
            "org_unit": None,
            "email": None,
            "key_size": None,
            "certificate": None,
            "intermediate_cert": None,
            "key": None,
            "passphrase": None,
            "generate": False,
            "days": None,
            "key_algorithm": None,
            "certificate_type": None,
            "subject_alternative_names": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.15"]

        # Certificate exists
        mock_blade.get_certificates.return_value.status_code = 200

        # Mock failed delete
        mock_delete_response = Mock()
        mock_delete_response.status_code = 400
        mock_error = Mock()
        mock_error.message = "Cannot delete certificate"
        mock_delete_response.errors = [mock_error]
        mock_blade.delete_certificates.return_value = mock_delete_response

        mock_get_system.return_value = mock_blade

        # Call main - expect failure
        try:
            main()
        except SystemExit:
            pass

        # Verify fail_json was called
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "Failed to delete" in call_args["msg"]

    @patch("plugins.modules.purefb_certs.pycountry")
    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_reimport_external_cert_fails(
        self, mock_ansible_module, mock_get_system, mock_pycountry
    ):
        """Test reimporting external certificate fails"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "import",
            "name": "external-cert",
            "export_file": None,
            "common_name": None,
            "country": None,
            "province": None,
            "locality": None,
            "organization": None,
            "org_unit": None,
            "email": None,
            "key_size": None,
            "certificate": "cert_content",
            "intermediate_cert": None,
            "key": None,  # No key - will be auto-detected as external
            "passphrase": None,
            "generate": False,
            "days": None,
            "key_algorithm": None,
            "certificate_type": None,
            "subject_alternative_names": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.15"]

        # Certificate exists and is external
        mock_cert_response = Mock()
        mock_cert_response.status_code = 200
        mock_cert = Mock()
        mock_cert.certificate_type = "external"
        mock_cert_response.items = [mock_cert]
        mock_blade.get_certificates.return_value = mock_cert_response

        mock_get_system.return_value = mock_blade

        # Call main - expect failure
        try:
            main()
        except SystemExit:
            pass

        # Verify fail_json was called
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "External Certificates cannot be reimported" in call_args["msg"]

    @patch("plugins.modules.purefb_certs.pycountry")
    @patch("plugins.modules.purefb_certs.LooseVersion")
    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_import_existing_cert(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_pycountry
    ):
        """Test importing over existing non-external certificate"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "import",
            "name": "existing-cert",
            "export_file": None,
            "common_name": None,
            "country": None,
            "province": None,
            "locality": None,
            "organization": None,
            "org_unit": None,
            "email": None,
            "key_size": None,
            "certificate": "cert_content",
            "intermediate_cert": None,
            "key": "key_content",
            "passphrase": None,
            "generate": False,
            "days": None,
            "key_algorithm": None,
            "certificate_type": None,
            "subject_alternative_names": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.15"]

        # Mock API version check - CSR feature gate OFF (API < 2.20)
        mock_loose_version.return_value.__le__ = Mock(return_value=False)

        # Certificate exists and is NOT external
        mock_cert_response = Mock()
        mock_cert_response.status_code = 200
        mock_cert = Mock()
        mock_cert.certificate_type = "self-signed"
        mock_cert_response.items = [mock_cert]
        mock_blade.get_certificates.return_value = mock_cert_response

        # Mock successful patch
        mock_patch_response = Mock()
        mock_patch_response.status_code = 200
        mock_blade.patch_certificates.return_value = mock_patch_response

        mock_get_system.return_value = mock_blade

        # Call main
        try:
            main()
        except SystemExit:
            pass

        # Verify patch_certificates was called (update path)
        mock_blade.patch_certificates.assert_called_once()

        # Verify exit_json was called with changed=True
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is True

    @patch("plugins.modules.purefb_certs.pycountry")
    @patch("plugins.modules.purefb_certs.LooseVersion")
    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_update_cert_unchanged_is_noop(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_pycountry
    ):
        """Test re-declaring an existing self-signed certificate with the same
        attributes reports no change and sends no PATCH"""
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "present",
            "name": "existing-cert",
            "export_file": None,
            "common_name": "test.example.com",
            "country": "US",
            "province": "CA",
            "locality": "SF",
            "organization": "Test Org",
            "org_unit": "IT",
            "email": "test@example.com",
            "key_size": 2048,
            "certificate": None,
            "intermediate_cert": None,
            "key": None,
            "passphrase": None,
            "generate": False,
            "days": 30,
            "key_algorithm": None,
            "certificate_type": "array",
            "subject_alternative_names": ["test.example.com"],
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.21"]
        mock_loose_version.return_value.__le__ = Mock(return_value=True)

        mock_cert = Mock()
        mock_cert.certificate = (
            "-----BEGIN CERTIFICATE-----\nX\n-----END CERTIFICATE-----"
        )
        mock_cert.intermediate_certificate = None
        mock_cert.common_name = "test.example.com"
        mock_cert.country = "US"
        mock_cert.state = "CA"
        mock_cert.locality = "SF"
        mock_cert.organization = "Test Org"
        mock_cert.organizational_unit = "IT"
        mock_cert.email = "test@example.com"
        mock_cert.key_size = 2048
        mock_cert.key_algorithm = "rsa"
        mock_cert.subject_alternative_names = ["test.example.com"]
        mock_blade.get_certificates.return_value.status_code = 200
        mock_blade.get_certificates.return_value.items = [mock_cert]

        mock_get_system.return_value = mock_blade
        mock_pycountry.countries.get.return_value = Mock()

        try:
            main()
        except SystemExit:
            pass

        mock_blade.patch_certificates.assert_not_called()
        mock_module.fail_json.assert_not_called()
        mock_module.exit_json.assert_called_once()
        assert mock_module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_certs.pycountry")
    @patch("plugins.modules.purefb_certs.LooseVersion")
    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_update_cert_key_size_change_requires_generate(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_pycountry
    ):
        """Test a different key_size without generate=true fails before any PATCH"""
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "present",
            "name": "existing-cert",
            "export_file": None,
            "common_name": None,
            "country": None,
            "province": None,
            "locality": None,
            "organization": None,
            "org_unit": None,
            "email": None,
            "key_size": 4096,
            "certificate": None,
            "intermediate_cert": None,
            "key": None,
            "passphrase": None,
            "generate": False,
            "days": None,
            "key_algorithm": None,
            "certificate_type": "array",
            "subject_alternative_names": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.21"]
        mock_loose_version.return_value.__le__ = Mock(return_value=True)

        mock_cert = Mock()
        mock_cert.key_size = 2048
        mock_blade.get_certificates.return_value.status_code = 200
        mock_blade.get_certificates.return_value.items = [mock_cert]

        mock_get_system.return_value = mock_blade

        try:
            main()
        except SystemExit:
            pass

        mock_blade.patch_certificates.assert_not_called()
        mock_module.fail_json.assert_called_once()
        msg = mock_module.fail_json.call_args[1]["msg"]
        assert "key_size" in msg
        assert "generate: true" in msg

    @patch("plugins.modules.purefb_certs.CertificatePatch")
    @patch("plugins.modules.purefb_certs.pycountry")
    @patch("plugins.modules.purefb_certs.LooseVersion")
    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_update_cert_generate_regenerates_key(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_pycountry,
        mock_certificate_patch,
    ):
        """Test generate=true alone re-keys the certificate with generate_new_key=True"""
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "state": "present",
            "name": "existing-cert",
            "export_file": None,
            "common_name": None,
            "country": None,
            "province": None,
            "locality": None,
            "organization": None,
            "org_unit": None,
            "email": None,
            "key_size": 4096,
            "certificate": None,
            "intermediate_cert": None,
            "key": None,
            "passphrase": None,
            "generate": True,
            "days": None,
            "key_algorithm": None,
            "certificate_type": "array",
            "subject_alternative_names": None,
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.21"]
        mock_loose_version.return_value.__le__ = Mock(return_value=True)

        mock_cert = Mock()
        mock_cert.key_size = 2048
        mock_blade.get_certificates.return_value.status_code = 200
        mock_blade.get_certificates.return_value.items = [mock_cert]

        mock_patch_response = Mock()
        mock_patch_response.status_code = 200
        mock_blade.patch_certificates.return_value = mock_patch_response

        mock_get_system.return_value = mock_blade

        try:
            main()
        except SystemExit:
            pass

        mock_blade.patch_certificates.assert_called_once()
        assert mock_blade.patch_certificates.call_args[1]["generate_new_key"] is True
        assert mock_certificate_patch.call_args[1]["key_size"] == 4096
        mock_module.exit_json.assert_called_once()
        assert mock_module.exit_json.call_args[1]["changed"] is True


class TestRealmNames:
    """A certificate in a realm is addressed by its full name, realm::certificate"""

    @pytest.mark.parametrize(
        "name, realm",
        [
            ("cert", ""),
            ("realm1::cert", "realm1"),
            ("outer::inner::cert", "outer::inner"),
            ("", ""),
            (None, ""),
        ],
    )
    def test_realm_of(self, name, realm):
        assert certs_module._realm_of(name) == realm

    def test_create_sends_the_realm_name(self):
        module = _module(common_name="s3.realm1.example.com", country="US")
        blade = _blade()

        _run(module, blade)

        assert _changed(module) is True
        blade.get_certificates.assert_called_once_with(names=["realm1::cert"])
        blade.post_certificates.assert_called_once()
        call = blade.post_certificates.call_args[1]
        assert call["names"] == ["realm1::cert"]
        assert call["certificate"]["common_name"] == "s3.realm1.example.com"
        assert call["certificate"]["certificate_type"] == "array"
        blade.get_realms.assert_not_called()

    def test_update_changes_only_the_named_certificate(self):
        """A namesake outside the realm is neither read nor changed"""
        module = _module(org_unit="Storage")
        blade = _blade([_cert("realm1::cert"), _cert("cert")])

        _run(module, blade)

        assert _changed(module) is True
        for call in blade.get_certificates.call_args_list:
            assert call[1]["names"] == ["realm1::cert"]
        blade.patch_certificates.assert_called_once()
        call = blade.patch_certificates.call_args[1]
        assert call["names"] == ["realm1::cert"]
        assert call["certificate"]["organizational_unit"] == "Storage"
        blade.post_certificates.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_same_values_change_nothing(self, check_mode):
        module = _module(check_mode=check_mode, org_unit="DevOps", country="US")
        blade = _blade([_cert("realm1::cert"), _cert("cert", country="GB")])

        _run(module, blade)

        assert _changed(module) is False
        _no_writes(blade)

    def test_another_letter_case_is_not_a_difference(self):
        """The array matches names without regard to case"""
        module = _module(name="REALM1::Cert", org_unit="DevOps")
        blade = _blade([_cert("realm1::cert")])

        _run(module, blade)

        assert _changed(module) is False
        _no_writes(blade)

    def test_delete_sends_the_realm_name(self):
        module = _module(state="absent")
        blade = _blade([_cert("realm1::cert"), _cert("cert")])

        _run(module, blade)

        assert _changed(module) is True
        blade.delete_certificates.assert_called_once_with(names=["realm1::cert"])

    def test_bare_name_does_not_reach_into_the_realm(self):
        """state=absent with the bare name of a certificate that is only in a realm"""
        module = _module(name="cert", state="absent")
        blade = _blade([_cert("realm1::cert")])

        _run(module, blade)

        assert _changed(module) is False
        blade.get_certificates.assert_called_once_with(names=["cert"])
        _no_writes(blade)

    def test_sign_references_the_realm_certificate(self):
        module = _module(state="sign", export_file="/tmp/cert.csr", org_unit="CA")
        blade = _blade([_cert("realm1::cert"), _cert("cert")])

        opened = _run(module, blade)

        assert _changed(module) is True
        request = blade.post_certificates_certificate_signing_requests.call_args[1]
        assert request["certificate"]["certificate"] == {"name": "realm1::cert"}
        assert request["certificate"]["organizational_unit"] == "CA"
        opened.assert_called_once_with("/tmp/cert.csr", "w", encoding="utf-8")
        opened().write.assert_called_once_with(CSR)

    def test_export_writes_the_realm_certificate(self):
        module = _module(state="export", export_file="/tmp/cert.pem")
        blade = _blade([_cert("realm1::cert", certificate="REALM PEM"), _cert("cert")])

        opened = _run(module, blade)

        assert _changed(module) is True
        for call in blade.get_certificates.call_args_list:
            assert call[1]["names"] == ["realm1::cert"]
        opened.assert_called_once_with("/tmp/cert.pem", "w", encoding="utf-8")
        opened().write.assert_called_once_with("REALM PEM")


class TestMissingCertificate:
    """state=sign and state=export need a certificate that exists"""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize(
        "state, action",
        [
            ("sign", "Creating a Certificate Signing Request failed."),
            ("export", "Exporting Certificate failed."),
        ],
    )
    @pytest.mark.parametrize(
        "name, hint", [("realm1::nope", False), ("cert", True), ("nope", True)]
    )
    def test_missing_certificate_fails(self, name, hint, state, action, check_mode):
        """The same answer in check mode and in a real run, and no request"""
        module = _module(
            check_mode=check_mode, name=name, state=state, export_file="/tmp/out"
        )
        blade = _blade([_cert("realm1::cert")])

        opened = _run(module, blade)

        msg = _failure(module)
        assert msg.startswith(action)
        assert "Error: Certificate {0} does not exist.".format(name) in msg
        assert ("named realm::certificate" in msg) is hint
        blade.get_certificates.assert_called_once_with(names=[name])
        _no_writes(blade)
        opened.assert_not_called()

    def test_refused_signing_request_reports_the_array_message(self):
        """An error answer to the request is reported, not read for items"""
        module = _module(name="realm1::ca", state="sign", export_file="/tmp/out")
        blade = _blade(
            [_cert("realm1::ca", certificate_type="external")],
            csr_error=ARRAY_TYPE_ONLY,
        )

        opened = _run(module, blade)

        msg = _failure(module)
        assert msg == (
            "Creating a Certificate Signing Request for realm1::ca failed. "
            "Error: " + ARRAY_TYPE_ONLY
        )
        blade.post_certificates_certificate_signing_requests.assert_called_once()
        opened.assert_not_called()

    def test_check_mode_predicts_the_refusal_for_an_external_certificate(self):
        module = _module(
            check_mode=True, name="realm1::ca", state="sign", export_file="/tmp/out"
        )
        blade = _blade([_cert("realm1::ca", certificate_type="external")])

        opened = _run(module, blade)

        msg = _failure(module)
        assert msg == (
            "Creating a Certificate Signing Request for realm1::ca failed. "
            "Error: " + ARRAY_TYPE_ONLY
        )
        _no_writes(blade)
        opened.assert_not_called()

    def test_check_mode_sign_of_an_array_certificate_reports_changed(self):
        module = _module(check_mode=True, state="sign", export_file="/tmp/out")
        blade = _blade([_cert("realm1::cert")])

        opened = _run(module, blade)

        assert _changed(module) is True
        _no_writes(blade)
        opened.assert_not_called()

    def test_check_mode_export_of_an_existing_certificate_reports_changed(self):
        module = _module(check_mode=True, state="export", export_file="/tmp/out")
        blade = _blade([_cert("realm1::cert")])

        opened = _run(module, blade)

        assert _changed(module) is True
        _no_writes(blade)
        opened.assert_not_called()

    def test_sign_on_an_old_array_fails_before_the_read(self):
        module = _module(state="sign", export_file="/tmp/out")
        blade = _blade([_cert("realm1::cert")])

        _run(module, blade, api_version="2.19")

        assert _failure(module) == "Purity//FB 4.6.3+ is required for CSRs"
        blade.get_certificates.assert_not_called()
        _no_writes(blade)


class TestCheckedRead:
    """Only "does not exist" means the certificate is absent"""

    @pytest.mark.parametrize("status_code", [400, 403])
    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("state", ["present", "absent", "import", "export", "sign"])
    def test_refused_read_fails_with_the_array_message(
        self, state, check_mode, status_code
    ):
        module = _module(
            check_mode=check_mode,
            state=state,
            certificate=PEM if state == "import" else None,
            export_file="/tmp/out",
        )
        blade = _blade(read_error=_error_response(NOT_PERMITTED, status_code))

        opened = _run(module, blade)

        assert _failure(module) == (
            "Failed to read SSL certificate realm1::cert. Error: " + NOT_PERMITTED
        )
        _no_writes(blade)
        blade.get_realms.assert_not_called()
        opened.assert_not_called()

    def test_error_without_a_message_is_not_read_as_absent(self):
        module = _module(state="absent")
        blade = _blade(read_error=_error_response(None, 500))

        _run(module, blade)

        assert _failure(module) == (
            "Failed to read SSL certificate realm1::cert. Error: Unknown error"
        )
        _no_writes(blade)


class TestCheckModeRealm:
    """Check mode reads the realm a new certificate is to be created in"""

    @pytest.mark.parametrize("state", ["present", "import"])
    def test_unknown_realm_fails(self, state):
        module = _module(
            check_mode=True,
            name="nowhere::cert",
            state=state,
            certificate=PEM if state == "import" else None,
        )
        blade = _blade()

        _run(module, blade)

        assert _failure(module) == (
            "Creating SSL certificate nowhere::cert failed. Error: " + NO_REALM
        )
        blade.get_realms.assert_called_once_with(names=["nowhere"])
        _no_writes(blade)

    def test_destroyed_realm_fails(self):
        module = _module(check_mode=True, name="old::cert")
        blade = _blade(realms={"old": True})

        _run(module, blade)

        assert _failure(module) == (
            "Creating SSL certificate old::cert failed. "
            "Error: Realm has been destroyed."
        )
        _no_writes(blade)

    @pytest.mark.parametrize("name", ["realm1::new", "REALM1::new"])
    def test_existing_realm_reports_changed(self, name):
        module = _module(check_mode=True, name=name)
        blade = _blade()

        _run(module, blade)

        assert _changed(module) is True
        blade.get_realms.assert_called_once()
        _no_writes(blade)

    @pytest.mark.parametrize(
        "answer",
        [
            _error_response(NOT_PERMITTED),
            _error_response(NOT_PERMITTED, 403),
            _error_response(None, 500),
        ],
    )
    def test_only_a_definite_answer_fails(self, answer):
        """A realm read that says nothing about the realm leaves the prediction"""
        module = _module(check_mode=True, name="realm1::new")
        blade = _blade(realms=answer)

        _run(module, blade)

        assert _changed(module) is True
        _no_writes(blade)

    def test_realm_outside_the_scope_of_the_caller_fails(self):
        """Such a realm is read as an empty list, and the create is refused"""
        module = _module(check_mode=True, name="other::cert")
        blade = _blade(realms=_valid_response())

        _run(module, blade)

        assert _failure(module) == (
            "Creating SSL certificate other::cert failed. Error: " + NO_REALM
        )
        blade.get_realms.assert_called_once_with(names=["other"])
        _no_writes(blade)

    def test_array_level_name_reads_no_realm(self):
        module = _module(check_mode=True, name="new")
        blade = _blade()

        _run(module, blade)

        assert _changed(module) is True
        blade.get_realms.assert_not_called()
        _no_writes(blade)

    def test_array_without_realms_reads_no_realm(self):
        module = _module(check_mode=True, name="nowhere::cert")
        blade = _blade()

        _run(module, blade, api_version="2.18")

        assert _changed(module) is True
        blade.get_realms.assert_not_called()
        _no_writes(blade)

    def test_existing_certificate_reads_no_realm(self):
        module = _module(check_mode=True, org_unit="Storage")
        blade = _blade([_cert("realm1::cert")])

        _run(module, blade)

        assert _changed(module) is True
        blade.get_realms.assert_not_called()
        _no_writes(blade)

    def test_real_run_leaves_the_answer_to_the_array(self):
        module = _module(name="nowhere::cert")
        blade = _blade()
        blade.post_certificates.return_value = _error_response(NO_REALM)

        _run(module, blade)

        assert _failure(module) == (
            "Creating SSL certificate nowhere::cert failed. Error: " + NO_REALM
        )
        blade.get_realms.assert_not_called()
        blade.post_certificates.assert_called_once()


class TestBuiltInCertificate:
    """The certificate named global is never deleted"""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("name", ["global", "Global", "GLOBAL"])
    def test_any_letter_case_is_refused(self, name, check_mode):
        module = _module(check_mode=check_mode, name=name, state="absent")
        blade = _blade([_cert("global")])

        _run(module, blade)

        assert _failure(module) == "Global certificate cannot be deleted"
        _no_writes(blade)

    def test_realm_certificate_called_global_is_deleted(self):
        module = _module(name="realm1::global", state="absent")
        blade = _blade([_cert("global"), _cert("realm1::global")])

        _run(module, blade)

        assert _changed(module) is True
        blade.delete_certificates.assert_called_once_with(names=["realm1::global"])
