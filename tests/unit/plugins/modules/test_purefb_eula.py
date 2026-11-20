# Copyright: (c) 2026, Pure Storage Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_eula module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
from unittest.mock import Mock, patch, MagicMock

# Mock external dependencies before importing module
sys.modules["pypureclient"] = MagicMock()
sys.modules["pypureclient.flashblade"] = MagicMock()
sys.modules["urllib3"] = MagicMock()
sys.modules["distro"] = MagicMock()

import pytest

from plugins.module_utils.common import get_error_message as real_get_error_message
from plugins.modules.purefb_eula import main, set_eula

MOD = "plugins.modules.purefb_eula"
REFUSAL = "Operation not permitted."
ACCEPTED = 1700000000000


@pytest.fixture(autouse=True)
def real_error_message():
    """Use the get_error_message of the collection, whatever was mocked before"""
    with patch(MOD + ".get_error_message", real_get_error_message):
        yield


def _module(check_mode=False):
    """A module whose exit_json and fail_json end the run, as the real ones do"""
    module = Mock()
    module.check_mode = check_mode
    module.params = {
        "company": "ACME Storage, Inc.",
        "name": "Fred Bloggs",
        "title": "Storage Manager",
    }
    module.exit_json = Mock(side_effect=SystemExit("exit_json"))
    module.fail_json = Mock(side_effect=SystemExit("fail_json"))
    return module


def _error_response(status_code=400, message=REFUSAL):
    """The SDK answer to a refused or failed call: a status and errors, no items"""
    res = Mock(spec=["status_code", "errors", "headers"])
    res.status_code = status_code
    res.errors = []
    if message:
        error = Mock(spec=["context", "message", "location_context"])
        error.message = message
        res.errors.append(error)
    return res


def _signature(accepted=None):
    """An SDK EulaSignature: the deprecated signatory fields are null"""
    signature = Mock(spec=["accepted", "company", "name", "title"])
    signature.accepted = accepted
    signature.company = None
    signature.name = None
    signature.title = None
    return signature


def _eula_response(*signatures):
    """The SDK answer to a successful read of the EULA"""
    items = []
    for signature in signatures:
        eula = Mock(spec=["agreement", "signature"])
        eula.signature = signature
        items.append(eula)
    res = Mock(spec=["status_code", "items", "errors", "headers"])
    res.status_code = 200
    res.items = iter(items)
    return res


class TestPurefbEula:
    """Test cases for purefb_eula module"""

    @patch("plugins.modules.purefb_eula.EulaSignature")
    @patch("plugins.modules.purefb_eula.Eula")
    @patch("plugins.modules.purefb_eula.get_system")
    @patch("plugins.modules.purefb_eula.AnsibleModule")
    @patch("plugins.modules.purefb_eula.HAS_PYPURECLIENT", True)
    def test_set_eula_success(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_eula_class,
        mock_signature_class,
    ):
        """Test successful EULA signing"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = {
            "company": "ACME Storage, Inc.",
            "name": "Fred Bloggs",
            "title": "Storage Manager",
        }
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_current_signature = Mock()
        mock_current_signature.accepted = False
        mock_current_signature.company = "Different Company"
        mock_current_signature.name = "Different Name"
        mock_current_signature.title = "Different Title"
        mock_eula_response = Mock()
        mock_eula_response.signature = mock_current_signature
        mock_blade.get_arrays_eula.return_value.status_code = 200
        mock_blade.get_arrays_eula.return_value.items = [mock_eula_response]

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_arrays_eula.return_value = mock_response
        mock_get_system.return_value = mock_blade

        # Call function
        set_eula(mock_module, mock_blade)

        # Verify
        mock_blade.patch_arrays_eula.assert_called_once()
        mock_signature_class.assert_called_once_with(
            company="ACME Storage, Inc.",
            name="Fred Bloggs",
            title="Storage Manager",
        )
        mock_eula_class.assert_called_once()
        mock_module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_eula.get_system")
    @patch("plugins.modules.purefb_eula.AnsibleModule")
    @patch("plugins.modules.purefb_eula.HAS_PYPURECLIENT", True)
    def test_set_eula_check_mode(self, mock_ansible_module, mock_get_system):
        """Test EULA signing in check mode reports the change without patching"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = True
        mock_module.params = {
            "company": "ACME Storage, Inc.",
            "name": "Fred Bloggs",
            "title": "Storage Manager",
        }
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_current_signature = Mock()
        mock_current_signature.accepted = False
        mock_current_signature.company = "Different Company"
        mock_current_signature.name = "Different Name"
        mock_current_signature.title = "Different Title"
        mock_eula_response = Mock()
        mock_eula_response.signature = mock_current_signature
        mock_blade.get_arrays_eula.return_value.status_code = 200
        mock_blade.get_arrays_eula.return_value.items = [mock_eula_response]
        mock_get_system.return_value = mock_blade

        # Call function
        set_eula(mock_module, mock_blade)

        # Verify - check mode reads the current state but never patches
        mock_blade.get_arrays_eula.assert_called_once()
        mock_blade.patch_arrays_eula.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_eula.get_system")
    @patch("plugins.modules.purefb_eula.AnsibleModule")
    @patch("plugins.modules.purefb_eula.HAS_PYPURECLIENT", True)
    def test_set_eula_check_mode_already_accepted(
        self, mock_ansible_module, mock_get_system
    ):
        """Test check mode on a signed EULA reports no change"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = True
        mock_module.params = {
            "company": "ACME Storage, Inc.",
            "name": "Fred Bloggs",
            "title": "Storage Manager",
        }
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_current_signature = Mock()
        mock_current_signature.accepted = True
        mock_eula_response = Mock()
        mock_eula_response.signature = mock_current_signature
        mock_blade.get_arrays_eula.return_value.status_code = 200
        mock_blade.get_arrays_eula.return_value.items = [mock_eula_response]
        mock_get_system.return_value = mock_blade

        # Call function
        set_eula(mock_module, mock_blade)

        # Verify
        mock_blade.patch_arrays_eula.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_eula.EulaSignature")
    @patch("plugins.modules.purefb_eula.Eula")
    @patch("plugins.modules.purefb_eula.get_system")
    @patch("plugins.modules.purefb_eula.AnsibleModule")
    @patch("plugins.modules.purefb_eula.HAS_PYPURECLIENT", True)
    def test_set_eula_failure(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_eula_class,
        mock_signature_class,
    ):
        """Test EULA signing failure"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = {
            "company": "ACME Storage, Inc.",
            "name": "Fred Bloggs",
            "title": "Storage Manager",
        }
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_current_signature = Mock()
        mock_current_signature.accepted = False
        mock_current_signature.company = "Different Company"
        mock_current_signature.name = "Different Name"
        mock_current_signature.title = "Different Title"
        mock_eula_response = Mock()
        mock_eula_response.signature = mock_current_signature
        mock_blade.get_arrays_eula.return_value.status_code = 200
        mock_blade.get_arrays_eula.return_value.items = [mock_eula_response]

        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.errors = [Mock(message=REFUSAL)]
        mock_blade.patch_arrays_eula.return_value = mock_response
        mock_get_system.return_value = mock_blade

        # Call function
        set_eula(mock_module, mock_blade)

        # Verify
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "Signing EULA failed" in call_args["msg"]

    @patch("plugins.modules.purefb_eula.get_system")
    @patch("plugins.modules.purefb_eula.AnsibleModule")
    @patch("plugins.modules.purefb_eula.HAS_PYPURECLIENT", True)
    def test_eula_already_accepted(self, mock_ansible_module, mock_get_system):
        """Test when EULA is already accepted"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = {
            "company": "ACME Storage, Inc.",
            "name": "Fred Bloggs",
            "title": "Storage Manager",
        }
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_current_signature = Mock()
        mock_current_signature.accepted = True  # Already accepted
        mock_eula_response = Mock()
        mock_eula_response.signature = mock_current_signature
        mock_blade.get_arrays_eula.return_value.status_code = 200
        mock_blade.get_arrays_eula.return_value.items = [mock_eula_response]
        mock_get_system.return_value = mock_blade

        # Call function
        set_eula(mock_module, mock_blade)

        # Verify - should not patch if already accepted
        mock_blade.patch_arrays_eula.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_eula.get_system")
    @patch("plugins.modules.purefb_eula.AnsibleModule")
    @patch("plugins.modules.purefb_eula.HAS_PYPURECLIENT", True)
    def test_eula_signature_unchanged(self, mock_ansible_module, mock_get_system):
        """Test when EULA signature matches current values"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = {
            "company": "ACME Storage, Inc.",
            "name": "Fred Bloggs",
            "title": "Storage Manager",
        }
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_current_signature = Mock()
        mock_current_signature.accepted = False
        mock_current_signature.company = "ACME Storage, Inc."  # Same
        mock_current_signature.name = "Fred Bloggs"  # Same
        mock_current_signature.title = "Storage Manager"  # Same
        mock_eula_response = Mock()
        mock_eula_response.signature = mock_current_signature
        mock_blade.get_arrays_eula.return_value.status_code = 200
        mock_blade.get_arrays_eula.return_value.items = [mock_eula_response]
        mock_get_system.return_value = mock_blade

        # Call function
        set_eula(mock_module, mock_blade)

        # Verify - should not patch if signature is unchanged
        mock_blade.patch_arrays_eula.assert_not_called()
        mock_module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_eula.EulaSignature")
    @patch("plugins.modules.purefb_eula.Eula")
    @patch("plugins.modules.purefb_eula.get_system")
    @patch("plugins.modules.purefb_eula.AnsibleModule")
    @patch("plugins.modules.purefb_eula.HAS_PYPURECLIENT", True)
    def test_update_eula_company(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_eula_class,
        mock_signature_class,
    ):
        """Test updating EULA when company changes"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = {
            "company": "New Company Name",
            "name": "Fred Bloggs",
            "title": "Storage Manager",
        }
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_current_signature = Mock()
        mock_current_signature.accepted = False
        mock_current_signature.company = "Old Company Name"  # Different
        mock_current_signature.name = "Fred Bloggs"
        mock_current_signature.title = "Storage Manager"
        mock_eula_response = Mock()
        mock_eula_response.signature = mock_current_signature
        mock_blade.get_arrays_eula.return_value.status_code = 200
        mock_blade.get_arrays_eula.return_value.items = [mock_eula_response]

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_arrays_eula.return_value = mock_response
        mock_get_system.return_value = mock_blade

        # Call function
        set_eula(mock_module, mock_blade)

        # Verify - should update when company changes
        mock_blade.patch_arrays_eula.assert_called_once()
        mock_signature_class.assert_called_once_with(
            company="New Company Name",
            name="Fred Bloggs",
            title="Storage Manager",
        )
        mock_module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_eula.EulaSignature")
    @patch("plugins.modules.purefb_eula.Eula")
    @patch("plugins.modules.purefb_eula.get_system")
    @patch("plugins.modules.purefb_eula.AnsibleModule")
    @patch("plugins.modules.purefb_eula.HAS_PYPURECLIENT", True)
    def test_update_eula_name(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_eula_class,
        mock_signature_class,
    ):
        """Test updating EULA when name changes"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = {
            "company": "ACME Storage, Inc.",
            "name": "Jane Smith",
            "title": "Storage Manager",
        }
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_current_signature = Mock()
        mock_current_signature.accepted = False
        mock_current_signature.company = "ACME Storage, Inc."
        mock_current_signature.name = "Fred Bloggs"  # Different
        mock_current_signature.title = "Storage Manager"
        mock_eula_response = Mock()
        mock_eula_response.signature = mock_current_signature
        mock_blade.get_arrays_eula.return_value.status_code = 200
        mock_blade.get_arrays_eula.return_value.items = [mock_eula_response]

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_arrays_eula.return_value = mock_response
        mock_get_system.return_value = mock_blade

        # Call function
        set_eula(mock_module, mock_blade)

        # Verify - should update when name changes
        mock_blade.patch_arrays_eula.assert_called_once()
        mock_signature_class.assert_called_once_with(
            company="ACME Storage, Inc.",
            name="Jane Smith",
            title="Storage Manager",
        )
        mock_module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_eula.EulaSignature")
    @patch("plugins.modules.purefb_eula.Eula")
    @patch("plugins.modules.purefb_eula.get_system")
    @patch("plugins.modules.purefb_eula.AnsibleModule")
    @patch("plugins.modules.purefb_eula.HAS_PYPURECLIENT", True)
    def test_update_eula_title(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_eula_class,
        mock_signature_class,
    ):
        """Test updating EULA when title changes"""
        # Setup mocks
        mock_module = Mock()
        mock_module.check_mode = False
        mock_module.params = {
            "company": "ACME Storage, Inc.",
            "name": "Fred Bloggs",
            "title": "CTO",
        }
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_current_signature = Mock()
        mock_current_signature.accepted = False
        mock_current_signature.company = "ACME Storage, Inc."
        mock_current_signature.name = "Fred Bloggs"
        mock_current_signature.title = "Storage Manager"  # Different
        mock_eula_response = Mock()
        mock_eula_response.signature = mock_current_signature
        mock_blade.get_arrays_eula.return_value.status_code = 200
        mock_blade.get_arrays_eula.return_value.items = [mock_eula_response]

        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.patch_arrays_eula.return_value = mock_response
        mock_get_system.return_value = mock_blade

        # Call function
        set_eula(mock_module, mock_blade)

        # Verify - should update when title changes
        mock_blade.patch_arrays_eula.assert_called_once()
        mock_signature_class.assert_called_once_with(
            company="ACME Storage, Inc.",
            name="Fred Bloggs",
            title="CTO",
        )
        mock_module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_eula.get_system")
    @patch("plugins.modules.purefb_eula.AnsibleModule")
    @patch("plugins.modules.purefb_eula.HAS_PYPURECLIENT", False)
    def test_main_missing_sdk(self, mock_ansible_module, mock_get_system):
        """Test main when pypureclient SDK is missing"""
        # Setup mocks
        mock_module = Mock()
        mock_module.params = {
            "company": "ACME Storage, Inc.",
            "name": "Fred Bloggs",
            "title": "Storage Manager",
        }
        # Make fail_json raise exception to stop execution
        mock_module.fail_json.side_effect = SystemExit("fail_json called")
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_get_system.return_value = mock_blade

        # Call main - should raise SystemExit
        try:
            main()
        except SystemExit:
            pass

        # Verify - should fail with SDK missing message
        mock_module.fail_json.assert_called_once()
        call_args = mock_module.fail_json.call_args[1]
        assert "py-pure-client SDK required" in call_args["msg"]

    @patch("plugins.modules.purefb_eula.set_eula")
    @patch("plugins.modules.purefb_eula.get_system")
    @patch("plugins.modules.purefb_eula.AnsibleModule")
    @patch("plugins.modules.purefb_eula.HAS_PYPURECLIENT", True)
    def test_main_calls_set_eula(
        self, mock_ansible_module, mock_get_system, mock_set_eula
    ):
        """Test main function calls set_eula"""
        # Setup mocks
        mock_module = Mock()
        mock_module.params = {
            "company": "ACME Storage, Inc.",
            "name": "Fred Bloggs",
            "title": "Storage Manager",
        }
        # Make exit_json raise exception to stop execution
        mock_module.exit_json.side_effect = SystemExit("exit_json called")
        mock_ansible_module.return_value = mock_module

        mock_blade = Mock()
        mock_get_system.return_value = mock_blade

        # Call main - should raise SystemExit when set_eula calls exit_json
        try:
            main()
        except SystemExit:
            pass

        # Verify - should call set_eula with module and blade
        mock_set_eula.assert_called_once_with(mock_module, mock_blade)


class TestPurefbEulaRefusedRead:
    """A read of the EULA that the array refuses or fails"""

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_refused_read_reports_the_array_message(self, check_mode):
        """An administrator limited to a realm may not read the EULA"""
        module = _module(check_mode=check_mode)
        blade = Mock()
        blade.get_arrays_eula.return_value = _error_response()

        with pytest.raises(SystemExit):
            set_eula(module, blade)

        module.fail_json.assert_called_once_with(
            msg="Failed to read the EULA. Error: Operation not permitted."
        )
        blade.patch_arrays_eula.assert_not_called()
        module.exit_json.assert_not_called()

    @pytest.mark.parametrize(
        "status_code, message, reported",
        [
            (500, "Unexpected error.", "Unexpected error."),
            (429, None, "Unknown error"),
            (503, None, "Unknown error"),
        ],
    )
    def test_failed_read_reports_the_answer(self, status_code, message, reported):
        """Any status but 200 is a failed read, with or without an error text"""
        module = _module()
        blade = Mock()
        blade.get_arrays_eula.return_value = _error_response(status_code, message)

        with pytest.raises(SystemExit):
            set_eula(module, blade)

        module.fail_json.assert_called_once_with(
            msg="Failed to read the EULA. Error: {0}".format(reported)
        )
        blade.patch_arrays_eula.assert_not_called()
        module.exit_json.assert_not_called()

    def test_answer_without_an_eula(self):
        """A successful answer that holds no EULA is reported"""
        module = _module()
        blade = Mock()
        blade.get_arrays_eula.return_value = _eula_response()

        with pytest.raises(SystemExit):
            set_eula(module, blade)

        module.fail_json.assert_called_once_with(msg="The array returned no EULA.")
        blade.patch_arrays_eula.assert_not_called()
        module.exit_json.assert_not_called()

    @patch(MOD + ".get_system")
    @patch(MOD + ".AnsibleModule")
    @patch(MOD + ".HAS_PYPURECLIENT", True)
    def test_main_refused_read(self, mock_ansible_module, mock_get_system):
        """The refusal reaches the user through main, in check mode too"""
        module = _module(check_mode=True)
        mock_ansible_module.return_value = module
        blade = Mock()
        blade.get_arrays_eula.return_value = _error_response()
        mock_get_system.return_value = blade

        with pytest.raises(SystemExit):
            main()

        module.fail_json.assert_called_once_with(
            msg="Failed to read the EULA. Error: Operation not permitted."
        )
        blade.patch_arrays_eula.assert_not_called()
        module.exit_json.assert_not_called()


class TestPurefbEulaRefusedSignature:
    """A signature that the array refuses"""

    def test_refused_signature_reports_the_array_message(self):
        """The reason of the array follows the fixed text"""
        module = _module()
        blade = Mock()
        blade.get_arrays_eula.return_value = _eula_response(_signature())
        blade.patch_arrays_eula.return_value = _error_response()

        with pytest.raises(SystemExit):
            set_eula(module, blade)

        blade.patch_arrays_eula.assert_called_once()
        module.fail_json.assert_called_once_with(
            msg="Signing EULA failed. Error: Operation not permitted."
        )
        module.exit_json.assert_not_called()


class TestPurefbEulaSignedArray:
    """An administrator who may read the EULA sees no difference"""

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_signed_eula_is_left_alone(self, check_mode):
        """A signed EULA carries its acceptance time and is never signed again"""
        module = _module(check_mode=check_mode)
        blade = Mock()
        blade.get_arrays_eula.return_value = _eula_response(
            _signature(accepted=ACCEPTED)
        )

        with pytest.raises(SystemExit):
            set_eula(module, blade)

        blade.get_arrays_eula.assert_called_once_with()
        blade.patch_arrays_eula.assert_not_called()
        module.fail_json.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)
