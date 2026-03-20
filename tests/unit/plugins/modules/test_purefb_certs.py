# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@purestorage.com>
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
sys.modules["ansible_collections.purestorage"] = MagicMock()
sys.modules["ansible_collections.purestorage.flashblade"] = MagicMock()
sys.modules["ansible_collections.purestorage.flashblade.plugins"] = MagicMock()
sys.modules["ansible_collections.purestorage.flashblade.plugins.module_utils"] = (
    MagicMock()
)
sys.modules[
    "ansible_collections.purestorage.flashblade.plugins.module_utils.purefb"
] = MagicMock()
sys.modules[
    "ansible_collections.purestorage.flashblade.plugins.module_utils.common"
] = MagicMock()

from plugins.modules.purefb_certs import main


class TestPurefbCerts:
    """Test cases for purefb_certs module"""

    @patch("plugins.modules.purefb_certs.pycountry")
    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_create_cert_with_intermediate(
        self, mock_ansible_module, mock_get_system, mock_pycountry
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

        # Mock array name
        mock_array = Mock()
        mock_array.name = "test-array"
        mock_blade.get_arrays.return_value.items = [mock_array]

        # Certificate doesn't exist
        mock_blade.get_certificates.return_value.status_code = 400

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
    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_update_cert_uses_patch(
        self, mock_ansible_module, mock_get_system, mock_pycountry
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

    @patch("plugins.modules.purefb_certs.get_system")
    @patch("plugins.modules.purefb_certs.AnsibleModule")
    @patch("plugins.modules.purefb_certs.HAS_PYPURECLIENT", True)
    @patch("plugins.modules.purefb_certs.HAS_PYCOUNTRY", True)
    def test_main_import_cert_check_mode(self, mock_ansible_module, mock_get_system):
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

        # Certificate doesn't exist
        mock_blade.get_certificates.return_value.status_code = 400

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
