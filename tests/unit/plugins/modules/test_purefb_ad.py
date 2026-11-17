# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for the purefb_ad module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import importlib
import sys
import types
from unittest.mock import MagicMock, Mock, patch

# Mock external dependencies before importing module
sys.modules["pypureclient"] = MagicMock()
sys.modules["pypureclient.flashblade"] = MagicMock()
sys.modules["urllib3"] = MagicMock()
sys.modules["distro"] = MagicMock()
sys.modules["grp"] = MagicMock()
sys.modules["fcntl"] = MagicMock()
sys.modules["pwd"] = MagicMock()
sys.modules["syslog"] = MagicMock()
sys.modules["tty"] = MagicMock()

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

# The version gates must compare real version strings, so the vendored
# LooseVersion is wired in instead of a MagicMock.
from plugins.module_utils.version import LooseVersion  # noqa: E402

_version_module = MagicMock()
_version_module.LooseVersion = LooseVersion
sys.modules["ansible_collections.everpure.flashblade.plugins.module_utils.version"] = (
    _version_module
)

# test_account is imported under another name so pytest does not collect it.
from plugins.modules.purefb_ad import (  # noqa: E402
    _ca_reference_kwargs,
    _check_certificate,
    _reference_name,
    create_account,
    main,
    test_account as ad_test_account,
    update_account,
)

MODULE_PATH = "plugins.modules.purefb_ad"


def _params(**overrides):
    params = {
        "state": "present",
        "username": None,
        "password": None,
        "name": "ad1",
        "computer": None,
        "service": "",
        "existing": False,
        "local_only": False,
        "domain": None,
        "join_ou": None,
        "server": None,
        "directory_servers": None,
        "kerberos_servers": None,
        "service_principals": None,
        "global_catalog_servers": None,
        "encryption": ["aes256-cts-hmac-sha1-96"],
        "ca_certificate": None,
        "ca_certificate_group": None,
    }
    params.update(overrides)
    return params


def _join_params(**overrides):
    params = {
        "domain": "acme.com",
        "username": "Administrator",
        "password": "secret",
    }
    params.update(overrides)
    return _params(**params)


def _module(**overrides):
    module = Mock()
    module.params = _params(**overrides)
    module.check_mode = False
    module.fail_json = Mock(side_effect=SystemExit)
    module.exit_json = Mock(side_effect=SystemExit)
    return module


def _reference(name):
    ref = Mock(spec=["name"])
    ref.name = name
    return ref


def _current(ca_certificate=None, ca_certificate_group=None, **fields):
    """An AD configuration shaped like a GET result.

    ``spec`` matters: the real ActiveDirectory model raises AttributeError for
    anything outside its field set.
    """
    obj = Mock(
        spec=[
            "id",
            "name",
            "computer_name",
            "domain",
            "directory_servers",
            "kerberos_servers",
            "global_catalog_servers",
            "service_principal_names",
            "join_ou",
            "encryption_types",
            "ca_certificate",
            "ca_certificate_group",
            "server",
        ]
    )
    obj.name = "ad1"
    obj.computer_name = "AD1"
    obj.domain = "acme.com"
    obj.directory_servers = ["ldap.acme.com"]
    obj.kerberos_servers = ["kdc.acme.com"]
    obj.global_catalog_servers = ["gc.acme.com"]
    obj.service_principal_names = ["nfs/ad1.acme.com"]
    obj.join_ou = "CN=Computers"
    obj.encryption_types = ["aes256-cts-hmac-sha1-96"]
    obj.ca_certificate = _reference(ca_certificate) if ca_certificate else None
    obj.ca_certificate_group = (
        _reference(ca_certificate_group) if ca_certificate_group else None
    )
    obj.server = None
    for key, value in fields.items():
        setattr(obj, key, value)
    return obj


def _response(status_code=200, items=None):
    response = Mock()
    response.status_code = status_code
    response.items = items if items is not None else []
    return response


def _blade(status_code=200, items=None):
    blade = Mock()
    response = _response(status_code, items)
    for call in (
        "get_active_directory",
        "post_active_directory",
        "patch_active_directory",
        "delete_active_directory",
        "get_active_directory_test",
        "patch_active_directory_test",
        "get_certificates",
        "get_certificate_groups",
        "get_servers",
        "post_keytabs",
    ):
        getattr(blade, call).return_value = response
    return blade


def _component(success=True):
    component = Mock(
        spec=[
            "component_name",
            "description",
            "destination",
            "enabled",
            "success",
            "test_type",
            "resource",
        ]
    )
    component.component_name = "fm1"
    component.description = "LDAPS connection"
    component.destination = "ldap.acme.com:636"
    component.enabled = True
    component.success = success
    component.test_type = "connectivity"
    component.resource = _reference("ad1")
    return component


class TestCaHelpers:
    """Reference helpers shared by the create, update and test paths."""

    def test_reference_name_returns_name(self):
        assert (
            _reference_name(_current(ca_certificate="ca1"), "ca_certificate") == "ca1"
        )

    def test_reference_name_none_when_unset(self):
        current = _current(ca_certificate="ca1")
        assert _reference_name(current, "ca_certificate_group") is None

    def test_reference_name_none_when_field_missing(self):
        """Older models carry neither field."""
        assert _reference_name(Mock(spec=["name"]), "ca_certificate") is None

    def test_ca_reference_kwargs_empty_without_options(self):
        assert _ca_reference_kwargs(_module()) == {}

    @patch(MODULE_PATH + ".Reference")
    def test_ca_reference_kwargs_certificate(self, mock_reference):
        kwargs = _ca_reference_kwargs(_module(ca_certificate="ca1"))
        mock_reference.assert_called_once_with(name="ca1")
        assert kwargs == {"ca_certificate": mock_reference.return_value}

    @patch(MODULE_PATH + ".Reference")
    def test_ca_reference_kwargs_group(self, mock_reference):
        kwargs = _ca_reference_kwargs(_module(ca_certificate_group="grp1"))
        mock_reference.assert_called_once_with(name="grp1")
        assert kwargs == {"ca_certificate_group": mock_reference.return_value}

    def test_check_certificate_skips_when_unset(self):
        module = _module()
        blade = _blade()
        _check_certificate(module, blade, "ca_certificate")
        blade.get_certificates.assert_not_called()
        module.fail_json.assert_not_called()

    def test_check_certificate_passes_when_present(self):
        module = _module(ca_certificate="ca1")
        blade = _blade()
        _check_certificate(module, blade, "ca_certificate")
        blade.get_certificates.assert_called_once_with(names=["ca1"])
        module.fail_json.assert_not_called()

    @patch(MODULE_PATH + ".get_error_message", return_value="not found")
    def test_check_certificate_fails_when_missing(self, mock_error):
        module = _module(ca_certificate="nope")
        blade = _blade(status_code=400)
        try:
            _check_certificate(module, blade, "ca_certificate")
        except SystemExit:
            pass
        mock_error.assert_called_once_with(blade.get_certificates.return_value)
        module.fail_json.assert_called_once_with(
            msg="Certificate nope does not exist. Error: not found"
        )

    @patch(MODULE_PATH + ".get_error_message", return_value="not found")
    def test_check_certificate_group_fails_when_missing(self, mock_error):
        module = _module(ca_certificate_group="nope")
        blade = _blade(status_code=400)
        try:
            _check_certificate(module, blade, "ca_certificate_group")
        except SystemExit:
            pass
        blade.get_certificate_groups.assert_called_once_with(names=["nope"])
        module.fail_json.assert_called_once_with(
            msg="Certificate group nope does not exist. Error: not found"
        )


@patch(MODULE_PATH + ".get_rest_api_version", return_value="2.30")
class TestCreateAccount:
    """POST carries the CA reference in both the new and existing-account paths."""

    @patch(MODULE_PATH + ".Reference")
    @patch(MODULE_PATH + ".ActiveDirectoryPost")
    def test_new_account_sends_ca_certificate_reference(
        self, mock_post, mock_reference, _version
    ):
        module = _module(**_join_params(ca_certificate="ca1"))
        blade = _blade()
        try:
            create_account(module, blade)
        except SystemExit:
            pass
        mock_reference.assert_called_once_with(name="ca1")
        post_kwargs = mock_post.call_args[1]
        assert post_kwargs["ca_certificate"] is mock_reference.return_value
        assert "ca_certificate_group" not in post_kwargs
        assert post_kwargs["domain"] == "acme.com"
        blade.post_active_directory.assert_called_once_with(
            names=["ad1"], active_directory=mock_post.return_value
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".Reference")
    @patch(MODULE_PATH + ".ActiveDirectoryPost")
    def test_existing_account_sends_ca_certificate_group(
        self, mock_post, mock_reference, _version
    ):
        module = _module(**_join_params(existing=True, ca_certificate_group="grp1"))
        blade = _blade()
        try:
            create_account(module, blade)
        except SystemExit:
            pass
        mock_reference.assert_called_once_with(name="grp1")
        post_kwargs = mock_post.call_args[1]
        assert post_kwargs["ca_certificate_group"] is mock_reference.return_value
        assert "ca_certificate" not in post_kwargs
        # The existing-account body still omits what the domain already holds.
        assert "service_principal_names" not in post_kwargs
        assert "join_ou" not in post_kwargs
        blade.post_active_directory.assert_called_once_with(
            names=["ad1"],
            active_directory=mock_post.return_value,
            join_existing_account=True,
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".Reference")
    @patch(MODULE_PATH + ".ActiveDirectoryPost")
    def test_without_ca_sends_no_reference(self, mock_post, mock_reference, _version):
        module = _module(**_join_params())
        try:
            create_account(module, _blade())
        except SystemExit:
            pass
        mock_reference.assert_not_called()
        post_kwargs = mock_post.call_args[1]
        assert "ca_certificate" not in post_kwargs
        assert "ca_certificate_group" not in post_kwargs

    @patch(MODULE_PATH + ".ActiveDirectoryPost")
    def test_check_mode_makes_no_post(self, mock_post, _version):
        module = _module(**_join_params(ca_certificate="ca1"))
        module.check_mode = True
        blade = _blade()
        try:
            create_account(module, blade)
        except SystemExit:
            pass
        blade.post_active_directory.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".ActiveDirectoryPost")
    def test_api_error_fails(self, mock_post, _version):
        module = _module(**_join_params(ca_certificate="ca1"))
        blade = _blade(status_code=400)
        try:
            create_account(module, blade)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to add Active Directory Account ad1" in msg


@patch(MODULE_PATH + ".get_rest_api_version", return_value="2.30")
class TestUpdateAccount:
    """PATCH carries a CA reference only when the name differs."""

    def _blade_with(self, current):
        blade = _blade()
        blade.get_active_directory.return_value = _response(items=[current])
        return blade

    def test_no_change_when_ca_matches(self, _version):
        module = _module(ca_certificate="ca1")
        blade = self._blade_with(_current(ca_certificate="ca1"))
        try:
            update_account(module, blade)
        except SystemExit:
            pass
        blade.patch_active_directory.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_no_change_when_ca_omitted(self, _version):
        """An omitted option never clears the configured CA."""
        module = _module()
        blade = self._blade_with(_current(ca_certificate="ca1"))
        try:
            update_account(module, blade)
        except SystemExit:
            pass
        blade.patch_active_directory.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE_PATH + ".Reference")
    @patch(MODULE_PATH + ".ActiveDirectoryPatch")
    def test_patches_ca_certificate_change(self, mock_patch, mock_reference, _version):
        module = _module(ca_certificate="ca2")
        blade = self._blade_with(_current(ca_certificate="ca1"))
        try:
            update_account(module, blade)
        except SystemExit:
            pass
        mock_reference.assert_called_once_with(name="ca2")
        mock_patch.assert_called_once_with(ca_certificate=mock_reference.return_value)
        blade.patch_active_directory.assert_called_once_with(
            names=["ad1"], active_directory=mock_patch.return_value
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".Reference")
    @patch(MODULE_PATH + ".ActiveDirectoryPatch")
    def test_switch_to_group_sends_only_the_group(
        self, mock_patch, mock_reference, _version
    ):
        module = _module(ca_certificate_group="grp1")
        blade = self._blade_with(_current(ca_certificate="ca1"))
        try:
            update_account(module, blade)
        except SystemExit:
            pass
        mock_reference.assert_called_once_with(name="grp1")
        mock_patch.assert_called_once_with(
            ca_certificate_group=mock_reference.return_value
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_group_match_is_idempotent(self, _version):
        module = _module(ca_certificate_group="grp1")
        blade = self._blade_with(_current(ca_certificate_group="grp1"))
        try:
            update_account(module, blade)
        except SystemExit:
            pass
        blade.patch_active_directory.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE_PATH + ".ActiveDirectoryPatch")
    def test_check_mode_reports_change_without_patching(self, mock_patch, _version):
        module = _module(ca_certificate="ca2")
        module.check_mode = True
        blade = self._blade_with(_current(ca_certificate="ca1"))
        try:
            update_account(module, blade)
        except SystemExit:
            pass
        blade.patch_active_directory.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".ActiveDirectoryPatch")
    def test_api_error_fails(self, mock_patch, _version):
        module = _module(ca_certificate="ca2")
        blade = self._blade_with(_current(ca_certificate="ca1"))
        blade.patch_active_directory.return_value = _response(status_code=400)
        try:
            update_account(module, blade)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to update Active Directory Account ad1" in msg


class TestTestAccount:
    """state=test is read-only and picks GET or PATCH /test by the CA options."""

    def test_without_ca_uses_get(self):
        module = _module(state="test")
        blade = _blade(items=[_component(success=False)])
        try:
            ad_test_account(module, blade)
        except SystemExit:
            pass
        blade.get_active_directory_test.assert_called_once_with(names=["ad1"])
        blade.patch_active_directory_test.assert_not_called()
        kwargs = module.exit_json.call_args[1]
        assert kwargs["changed"] is False
        assert kwargs["test_response"][0]["component_name"] == "fm1"
        assert kwargs["test_response"][0]["success"] == "false"
        assert kwargs["test_response"][0]["enabled"] == "true"
        assert kwargs["test_response"][0]["resource_name"] == "ad1"

    @patch(MODULE_PATH + ".Reference")
    @patch(MODULE_PATH + ".ActiveDirectoryTestPatch")
    def test_with_certificate_uses_patch_test(self, mock_test_patch, mock_reference):
        module = _module(state="test", ca_certificate="ca2")
        blade = _blade(items=[_component()])
        try:
            ad_test_account(module, blade)
        except SystemExit:
            pass
        mock_reference.assert_called_once_with(name="ca2")
        mock_test_patch.assert_called_once_with(
            ca_certificate=mock_reference.return_value
        )
        blade.patch_active_directory_test.assert_called_once_with(
            names=["ad1"], active_directory=mock_test_patch.return_value
        )
        blade.get_active_directory_test.assert_not_called()
        # A test never touches the stored configuration.
        blade.patch_active_directory.assert_not_called()
        kwargs = module.exit_json.call_args[1]
        assert kwargs["changed"] is False
        assert kwargs["test_response"][0]["success"] == "true"

    @patch(MODULE_PATH + ".Reference")
    @patch(MODULE_PATH + ".ActiveDirectoryTestPatch")
    def test_with_group_uses_patch_test(self, mock_test_patch, mock_reference):
        module = _module(state="test", ca_certificate_group="grp1")
        blade = _blade(items=[_component()])
        try:
            ad_test_account(module, blade)
        except SystemExit:
            pass
        mock_test_patch.assert_called_once_with(
            ca_certificate_group=mock_reference.return_value
        )
        blade.patch_active_directory_test.assert_called_once()
        module.exit_json.assert_called_once()

    def test_api_error_fails(self):
        module = _module(state="test", ca_certificate="ca2")
        blade = _blade(status_code=400)
        try:
            ad_test_account(module, blade)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to test Active Directory Account ad1" in msg


@patch(MODULE_PATH + ".get_rest_api_version")
@patch(MODULE_PATH + ".get_system")
@patch(MODULE_PATH + ".AnsibleModule")
@patch(MODULE_PATH + ".HAS_PYPURECLIENT", True)
class TestMain:
    """Version gate and certificate validation run before any write."""

    def _setup(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_version,
        params,
        api_version="2.30",
        current=None,
    ):
        module = _module(**params)
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade
        mock_version.return_value = api_version
        if current is None:
            blade.get_active_directory.return_value = _response(status_code=400)
        else:
            blade.get_active_directory.return_value = _response(items=[current])
        return module, blade

    def _run(self):
        try:
            main()
        except SystemExit:
            pass

    def test_ca_options_are_mutually_exclusive(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        self._setup(mock_ansible_module, mock_get_system, mock_version, _params())
        self._run()
        assert mock_ansible_module.call_args[1]["mutually_exclusive"] == [
            ["ca_certificate", "ca_certificate_group"]
        ]

    def test_gate_blocks_create_on_old_rest(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_version,
            _join_params(ca_certificate="ca1"),
            api_version="2.26",
        )
        self._run()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "ca_certificate" in msg
        assert "2.27" in msg
        blade.post_active_directory.assert_not_called()
        blade.get_certificates.assert_not_called()

    def test_gate_blocks_update_on_old_rest(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_version,
            _params(ca_certificate="ca2"),
            api_version="2.26",
            current=_current(ca_certificate="ca1"),
        )
        self._run()
        module.fail_json.assert_called_once()
        blade.patch_active_directory.assert_not_called()

    def test_gate_blocks_test_on_old_rest(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_version,
            _params(state="test", ca_certificate_group="grp1"),
            api_version="2.26",
            current=_current(),
        )
        self._run()
        module.fail_json.assert_called_once()
        assert "ca_certificate_group" in module.fail_json.call_args[1]["msg"]
        blade.patch_active_directory_test.assert_not_called()
        blade.get_active_directory_test.assert_not_called()

    def test_gate_passes_at_2_27(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_version,
            _join_params(ca_certificate="ca1"),
            api_version="2.27",
        )
        self._run()
        blade.get_certificates.assert_called_once_with(names=["ca1"])
        blade.post_active_directory.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    def test_without_ca_old_rest_is_not_gated(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_version,
            _join_params(),
            api_version="2.16",
        )
        self._run()
        module.fail_json.assert_not_called()
        blade.post_active_directory.assert_called_once()

    @patch(MODULE_PATH + ".HAS_AD_TEST_PATCH", False)
    def test_old_sdk_without_ca_options_still_joins(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """An SDK without the REST 2.27 models still serves a plain join."""
        module, blade = self._setup(
            mock_ansible_module, mock_get_system, mock_version, _join_params()
        )
        self._run()
        module.fail_json.assert_not_called()
        blade.post_active_directory.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".HAS_AD_TEST_PATCH", False)
    def test_old_sdk_refuses_ca_before_post(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """The array gate cannot see the SDK, so the CA option is refused first."""
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_version,
            _join_params(ca_certificate="ca1"),
        )
        self._run()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "ca_certificate" in msg
        assert "py-pure-client" in msg
        assert "2.27" in msg
        mock_get_system.assert_not_called()
        blade.get_certificates.assert_not_called()
        blade.post_active_directory.assert_not_called()

    @patch(MODULE_PATH + ".HAS_AD_TEST_PATCH", False)
    def test_old_sdk_refuses_ca_before_patch(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_version,
            _params(ca_certificate_group="grp1"),
            current=_current(ca_certificate="ca1"),
        )
        self._run()
        module.fail_json.assert_called_once()
        assert "ca_certificate_group" in module.fail_json.call_args[1]["msg"]
        blade.patch_active_directory.assert_not_called()

    @patch(MODULE_PATH + ".HAS_AD_TEST_PATCH", False)
    def test_old_sdk_refuses_ca_test(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_version,
            _params(state="test", ca_certificate="ca2"),
            current=_current(),
        )
        self._run()
        module.fail_json.assert_called_once()
        blade.patch_active_directory_test.assert_not_called()
        blade.get_active_directory_test.assert_not_called()

    def test_missing_certificate_fails_before_post(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_version,
            _join_params(ca_certificate="nope"),
        )
        blade.get_certificates.return_value = _response(status_code=400)
        with patch(MODULE_PATH + ".get_error_message", return_value="not found"):
            self._run()
        module.fail_json.assert_called_once_with(
            msg="Certificate nope does not exist. Error: not found"
        )
        blade.post_active_directory.assert_not_called()

    def test_missing_group_fails_before_patch(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_version,
            _params(ca_certificate_group="nope"),
            current=_current(ca_certificate="ca1"),
        )
        blade.get_certificate_groups.return_value = _response(status_code=400)
        with patch(MODULE_PATH + ".get_error_message", return_value="not found"):
            self._run()
        module.fail_json.assert_called_once_with(
            msg="Certificate group nope does not exist. Error: not found"
        )
        blade.patch_active_directory.assert_not_called()

    def test_present_with_matching_ca_is_idempotent(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_version,
            _params(ca_certificate="ca1"),
            current=_current(ca_certificate="ca1"),
        )
        self._run()
        blade.patch_active_directory.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_test_state_with_ca_runs_patch_test(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_version,
            _params(state="test", ca_certificate="ca2"),
            current=_current(ca_certificate="ca1"),
        )
        blade.patch_active_directory_test.return_value = _response(items=[_component()])
        self._run()
        blade.get_certificates.assert_called_once_with(names=["ca2"])
        blade.patch_active_directory_test.assert_called_once()
        blade.patch_active_directory.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_test_state_on_missing_account_is_a_noop(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """No account: nothing to test, so the module exits unchanged as before."""
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_version,
            _params(state="test", ca_certificate="ca1"),
        )
        self._run()
        blade.patch_active_directory_test.assert_not_called()
        blade.get_active_directory_test.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_absent_does_not_validate_ca(
        self, mock_ansible_module, mock_get_system, mock_version
    ):
        """The CA options play no part in a delete."""
        module, blade = self._setup(
            mock_ansible_module,
            mock_get_system,
            mock_version,
            _params(state="absent", ca_certificate="nope"),
            current=_current(),
        )
        blade.get_certificates.return_value = _response(status_code=400)
        self._run()
        blade.get_certificates.assert_not_called()
        blade.delete_active_directory.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)


class TestOptionalImport:
    """An SDK without ActiveDirectoryTestPatch must still load the module."""

    def test_missing_model_keeps_sdk_usable(self):
        ad_module = sys.modules[MODULE_PATH]
        full_sdk = sys.modules["pypureclient.flashblade"]
        # An SDK that stops at REST 2.26: the four long-standing names exist,
        # ActiveDirectoryTestPatch does not, so its import raises ImportError.
        old_sdk = types.ModuleType("pypureclient.flashblade")
        for name in (
            "ActiveDirectoryPost",
            "ActiveDirectoryPatch",
            "Reference",
            "KeytabPost",
        ):
            setattr(old_sdk, name, MagicMock())
        sys.modules["pypureclient.flashblade"] = old_sdk
        try:
            importlib.reload(ad_module)
            assert ad_module.HAS_PYPURECLIENT is True
            assert ad_module.HAS_AD_TEST_PATCH is False
        finally:
            sys.modules["pypureclient.flashblade"] = full_sdk
            importlib.reload(ad_module)
        assert ad_module.HAS_PYPURECLIENT is True
        assert ad_module.HAS_AD_TEST_PATCH is True
