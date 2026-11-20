# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_saml module."""

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

import plugins.modules.purefb_saml as saml
from plugins.modules.purefb_saml import (
    main,
    _check_option_versions,
    _effective_services,
    _facts_from,
    _ref_name,
    _ref_update,
)

MODULE = "plugins.modules.purefb_saml"
IDP_NAME = "myidp"
AUTO_SP_ENTITY = "https://fb.example.com/saml2/service-provider-metadata/myidp"
PRN = "prn::iam:array-id/local::saml-provider/myidp"
# what the array answers for a provider that is not configured, or that is not
# shared with the realm of an administrator limited to a realm
ABSENT = "SsoSaml2 configuration does not exist."
REFUSED = "Operation not permitted."


class _Version:
    """Minimal LooseVersion stand-in so the gates compare real numbers"""

    def __init__(self, text):
        self.parts = tuple(int(part) for part in str(text).split("."))

    def __gt__(self, other):
        return self.parts > other.parts

    def __lt__(self, other):
        return self.parts < other.parts

    def __ge__(self, other):
        return self.parts >= other.parts

    def __le__(self, other):
        return self.parts <= other.parts

    def __eq__(self, other):
        return self.parts == other.parts


def _fake_ref(name=None):
    """Stand-in for ReferenceWritable that is easy to compare"""
    return ("ref", name)


def _base_params(**overrides):
    params = {
        "name": IDP_NAME,
        "state": "present",
        "url": None,
        "array_url": None,
        "entity_id": None,
        "metadata_url": None,
        "x509_cert": None,
        "signing_credential": None,
        "decryption_credential": None,
        "enabled": None,
        "encrypt_asserts": None,
        "sign_request": None,
        "services": None,
        "binding": None,
        "metadata_url_ca_certificate": None,
        "metadata_url_ca_certificate_group": None,
        "sp_entity_id": None,
        "trust_other_saml_sps_in_fleet": None,
    }
    params.update(overrides)
    return params


def _reference(name):
    ref = Mock(spec=["name"])
    ref.name = name
    return ref


def _current_idp(
    services=None,
    binding="http-redirect",
    trust=False,
    sp_entity_id=AUTO_SP_ENTITY,
    verification_certificate=None,
    metadata_url_ca_certificate=None,
    metadata_url_ca_certificate_group=None,
    enabled=False,
    sign_request=False,
    encrypt_asserts=False,
):
    """A GET item shaped like the array's response"""
    idp = Mock(
        spec=[
            "name",
            "array_url",
            "enabled",
            "idp",
            "sp",
            "services",
            "binding",
            "management",
            "prn",
        ]
    )
    idp.name = IDP_NAME
    idp.array_url = "https://fb.example.com"
    idp.enabled = enabled
    idp.services = ["management"] if services is None else services
    idp.binding = binding
    idp.prn = PRN
    idp.management = Mock(spec=["trust_other_saml_sps_in_fleet"])
    idp.management.trust_other_saml_sps_in_fleet = trust
    idp.idp = Mock(
        spec=[
            "url",
            "entity_id",
            "metadata_url",
            "sign_request_enabled",
            "encrypt_assertion_enabled",
            "verification_certificate",
            "metadata_url_ca_certificate",
            "metadata_url_ca_certificate_group",
        ]
    )
    idp.idp.url = "https://idp.example.com/sso"
    idp.idp.entity_id = "https://idp.example.com/idp"
    idp.idp.metadata_url = None
    idp.idp.sign_request_enabled = sign_request
    idp.idp.encrypt_assertion_enabled = encrypt_asserts
    idp.idp.verification_certificate = _reference(verification_certificate)
    idp.idp.metadata_url_ca_certificate = _reference(metadata_url_ca_certificate)
    idp.idp.metadata_url_ca_certificate_group = _reference(
        metadata_url_ca_certificate_group
    )
    idp.sp = Mock(
        spec=[
            "decryption_credential",
            "signing_credential",
            "entity_id",
            "assertion_consumer_url",
            "metadata_url",
        ]
    )
    idp.sp.decryption_credential = _reference(None)
    idp.sp.signing_credential = _reference(None)
    idp.sp.entity_id = sp_entity_id
    idp.sp.assertion_consumer_url = "https://fb.example.com/login/saml2/sso/myidp"
    idp.sp.metadata_url = AUTO_SP_ENTITY
    return idp


def _error_message(res, default="Unknown error"):
    """Stand-in for get_error_message: the first error message of a response"""
    errors = getattr(res, "errors", None)
    if errors:
        return errors[0].message
    return default


def _response(status_code, items=None, error=None):
    """A response shaped like the SDK's: items on 200, errors and no items otherwise"""
    if status_code == 200:
        res = Mock(spec=["status_code", "items"])
        res.items = items or []
    else:
        res = Mock(spec=["status_code", "errors"])
        res.errors = []
        if error:
            entry = Mock(spec=["message"])
            entry.message = error
            res.errors.append(entry)
    res.status_code = status_code
    return res


def _run(
    params,
    api_version="2.30",
    current=None,
    check_mode=False,
    post_status=200,
    patch_status=200,
    delete_status=200,
    get_side_effect=None,
    test_items=None,
    test_response=None,
    patch_error=None,
):
    """Run main() against a mocked module and blade; return (module, blade, models)"""
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.params = params
    module.check_mode = check_mode

    blade = Mock()
    if get_side_effect is not None:
        blade.get_sso_saml2_idps.side_effect = get_side_effect
    elif current is None:
        blade.get_sso_saml2_idps.return_value = _response(400, error=ABSENT)
    else:
        blade.get_sso_saml2_idps.return_value = _response(200, [current])
    blade.get_sso_saml2_idps_test.return_value = test_response or _response(
        200, test_items
    )
    blade.post_sso_saml2_idps.return_value = _response(post_status)
    blade.patch_sso_saml2_idps.return_value = _response(patch_status, error=patch_error)
    blade.delete_sso_saml2_idps.return_value = _response(delete_status)

    models = {}
    patchers = [
        patch(MODULE + ".AnsibleModule", return_value=module),
        patch(MODULE + ".get_system", return_value=blade),
        patch(MODULE + ".get_rest_api_version", return_value=api_version),
        patch(MODULE + ".LooseVersion", _Version),
        patch(MODULE + ".HAS_PYPURECLIENT", True),
        patch(MODULE + ".ReferenceWritable", side_effect=_fake_ref),
    ]
    for name in ("Saml2Sso", "Saml2SsoPost", "Saml2SsoSp", "Saml2SsoIdp"):
        patchers.append(patch(MODULE + "." + name))
    patchers.append(patch(MODULE + ".Saml2SsoManagement"))
    patchers.append(patch(MODULE + ".get_error_message", side_effect=_error_message))
    started = [p.start() for p in patchers]
    try:
        models["Saml2Sso"] = started[6]
        models["Saml2SsoPost"] = started[7]
        models["Saml2SsoSp"] = started[8]
        models["Saml2SsoIdp"] = started[9]
        models["Saml2SsoManagement"] = started[10]
        try:
            main()
        except SystemExit:
            pass
    finally:
        for p in reversed(patchers):
            p.stop()
    return module, blade, models


def _no_writes(blade):
    blade.post_sso_saml2_idps.assert_not_called()
    blade.patch_sso_saml2_idps.assert_not_called()
    blade.delete_sso_saml2_idps.assert_not_called()


class TestPurefbSamlHelpers:
    """Helper-function tests"""

    def test_ref_name_returns_name(self):
        idp = Mock()
        idp.verification_certificate = _reference("idp-cert")
        assert _ref_name(idp, "verification_certificate") == "idp-cert"

    def test_ref_name_none_when_reference_empty(self):
        idp = Mock()
        idp.verification_certificate = _reference(None)
        assert _ref_name(idp, "verification_certificate") is None

    def test_ref_name_none_when_attribute_missing(self):
        idp = Mock(spec=["url"])
        assert _ref_name(idp, "metadata_url_ca_certificate") is None

    def test_ref_update_new_name_clear_or_omit(self):
        with patch(MODULE + ".ReferenceWritable", side_effect=_fake_ref):
            assert _ref_update("new", "old") == ("ref", "new")
            assert _ref_update("new", None) == ("ref", "new")
            assert _ref_update(None, "old") == ("ref", "")
            assert _ref_update(None, None) is None

    def test_effective_services_prefers_option(self):
        module = Mock()
        module.params = {"services": ["object"]}
        assert _effective_services(module, _current_idp()) == ["object"]

    def test_effective_services_uses_current(self):
        module = Mock()
        module.params = {"services": None}
        current = _current_idp(services=["object"])
        assert _effective_services(module, current) == ["object"]

    def test_effective_services_defaults_to_management(self):
        module = Mock()
        module.params = {"services": None}
        assert _effective_services(module, None) == ["management"]
        old_array = Mock(spec=["name"])
        assert _effective_services(module, old_array) == ["management"]

    def test_facts_from_reads_prn_and_sp_entity_id(self):
        facts = _facts_from(_current_idp(sp_entity_id="https://sp.example.com"))
        assert facts == {"prn": PRN, "sp_entity_id": "https://sp.example.com"}

    def test_facts_from_tolerates_old_array(self):
        assert _facts_from(Mock(spec=["name"])) == {
            "prn": None,
            "sp_entity_id": None,
        }

    def test_check_option_versions_passes_when_supported(self):
        module = Mock()
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(services=["object"], sp_entity_id="x")
        with patch(MODULE + ".LooseVersion", _Version):
            _check_option_versions(module, "2.24")
        module.fail_json.assert_not_called()

    def test_check_option_versions_fails_naming_version(self):
        module = Mock()
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(binding="none")
        with patch(MODULE + ".LooseVersion", _Version):
            try:
                _check_option_versions(module, "2.16")
            except SystemExit:
                pass
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "binding" in msg
        assert "2.17" in msg


class TestPurefbSamlCreate:
    """Create path"""

    def test_create_sends_new_fields(self):
        params = _base_params(
            array_url="https://fb.example.com",
            url="https://idp.example.com/sso",
            entity_id="https://idp.example.com/idp",
            x509_cert="idp-cert",
            metadata_url_ca_certificate="idp-ca",
            services=["object", "management"],
            binding="none",
            sp_entity_id="https://sp.example.com",
            trust_other_saml_sps_in_fleet=True,
        )
        module, blade, models = _run(params)

        blade.post_sso_saml2_idps.assert_called_once()
        assert blade.post_sso_saml2_idps.call_args[1]["names"] == [IDP_NAME]
        post_kwargs = models["Saml2SsoPost"].call_args[1]
        assert post_kwargs["array_url"] == "https://fb.example.com"
        assert post_kwargs["services"] == ["object", "management"]
        assert post_kwargs["binding"] == "none"
        assert post_kwargs["management"] is models["Saml2SsoManagement"].return_value
        models["Saml2SsoManagement"].assert_called_once_with(
            trust_other_saml_sps_in_fleet=True
        )
        sp_kwargs = models["Saml2SsoSp"].call_args[1]
        assert sp_kwargs["entity_id"] == "https://sp.example.com"
        assert sp_kwargs["decryption_credential"] is None
        idp_kwargs = models["Saml2SsoIdp"].call_args[1]
        assert idp_kwargs["verification_certificate"] == ("ref", "idp-cert")
        assert idp_kwargs["metadata_url_ca_certificate"] == ("ref", "idp-ca")
        assert idp_kwargs["metadata_url_ca_certificate_group"] is None
        assert idp_kwargs["url"] == "https://idp.example.com/sso"
        # enabled is not given, so no enable PATCH follows the POST
        blade.patch_sso_saml2_idps.assert_not_called()
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_without_new_options_omits_them(self):
        params = _base_params(
            array_url="https://fb.example.com",
            metadata_url="https://idp.example.com/metadata",
        )
        module, blade, models = _run(params)

        post_kwargs = models["Saml2SsoPost"].call_args[1]
        for key in ("services", "binding", "management"):
            assert key not in post_kwargs
        assert "entity_id" not in models["Saml2SsoSp"].call_args[1]
        models["Saml2SsoManagement"].assert_not_called()
        idp_kwargs = models["Saml2SsoIdp"].call_args[1]
        assert idp_kwargs["verification_certificate"] is None
        assert idp_kwargs["metadata_url_ca_certificate"] is None
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_services_only_carries_default_binding(self):
        """The array wants services and binding together on creation too, so
        the array default binding stands in for the one not given"""
        params = _base_params(array_url="https://fb.example.com", services=["object"])
        module, blade, models = _run(params)

        blade.post_sso_saml2_idps.assert_called_once()
        post_kwargs = models["Saml2SsoPost"].call_args[1]
        assert post_kwargs["services"] == ["object"]
        assert post_kwargs["binding"] == "http-redirect"
        assert "management" not in post_kwargs

    def test_create_binding_only_carries_default_services(self):
        params = _base_params(array_url="https://fb.example.com", binding="none")
        module, blade, models = _run(params)

        blade.post_sso_saml2_idps.assert_called_once()
        post_kwargs = models["Saml2SsoPost"].call_args[1]
        assert post_kwargs["services"] == ["management"]
        assert post_kwargs["binding"] == "none"

    def test_create_when_get_returns_no_items(self):
        """A 200 with an empty item list means the provider is absent"""
        params = _base_params(array_url="https://fb.example.com")
        module, blade, models = _run(
            params,
            get_side_effect=[_response(200, []), _response(200, [_current_idp()])],
        )

        blade.post_sso_saml2_idps.assert_called_once()
        blade.patch_sso_saml2_idps.assert_not_called()
        kwargs = module.exit_json.call_args[1]
        assert kwargs["changed"] is True
        assert kwargs["prn"] == PRN

    def test_create_returns_prn_and_sp_entity_id(self):
        params = _base_params(array_url="https://fb.example.com")
        created = _current_idp()
        module, blade, models = _run(
            params,
            get_side_effect=[_response(400, error=ABSENT), _response(200, [created])],
        )

        blade.post_sso_saml2_idps.assert_called_once()
        kwargs = module.exit_json.call_args[1]
        assert kwargs["changed"] is True
        assert kwargs["prn"] == PRN
        assert kwargs["sp_entity_id"] == AUTO_SP_ENTITY

    def test_create_enabled_patches_after_post(self):
        params = _base_params(array_url="https://fb.example.com", enabled=True)
        module, blade, models = _run(params)

        blade.post_sso_saml2_idps.assert_called_once()
        blade.patch_sso_saml2_idps.assert_called_once()
        models["Saml2Sso"].assert_called_once_with(enabled=True)
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_omits_unset_flags(self):
        """Unset signing and encryption flags are left to the array default
        rather than sent as false, and no enable PATCH follows"""
        params = _base_params(array_url="https://fb.example.com")
        module, blade, models = _run(params)

        blade.post_sso_saml2_idps.assert_called_once()
        idp_kwargs = models["Saml2SsoIdp"].call_args[1]
        assert idp_kwargs["sign_request_enabled"] is None
        assert idp_kwargs["encrypt_assertion_enabled"] is None
        blade.patch_sso_saml2_idps.assert_not_called()

    def test_create_check_mode_skips_post(self):
        params = _base_params(array_url="https://fb.example.com", services=["object"])
        module, blade, models = _run(params, check_mode=True)

        _no_writes(blade)
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_create_api_error_fails(self):
        params = _base_params(array_url="https://fb.example.com")
        module, blade, models = _run(params, post_status=400)

        module.fail_json.assert_called_once()
        assert "Failed to create SAML2 Identity Provider" in (
            module.fail_json.call_args[1]["msg"]
        )
        module.exit_json.assert_not_called()


class TestPurefbSamlUpdate:
    """Update path"""

    def test_update_sp_entity_id(self):
        params = _base_params(sp_entity_id="https://sp.example.com")
        updated = _current_idp(sp_entity_id="https://sp.example.com")
        module, blade, models = _run(
            params,
            get_side_effect=[
                _response(200, [_current_idp()]),
                _response(200, [updated]),
            ],
        )

        blade.patch_sso_saml2_idps.assert_called_once()
        assert blade.patch_sso_saml2_idps.call_args[1]["names"] == [IDP_NAME]
        sp_kwargs = models["Saml2SsoSp"].call_args[1]
        assert sp_kwargs["entity_id"] == "https://sp.example.com"
        body = models["Saml2Sso"].call_args[1]
        for key in ("services", "binding", "management"):
            assert key not in body
        kwargs = module.exit_json.call_args[1]
        assert kwargs["changed"] is True
        assert kwargs["sp_entity_id"] == "https://sp.example.com"
        assert kwargs["prn"] == PRN

    def test_update_idempotent_when_everything_matches(self):
        params = _base_params(
            array_url="https://fb.example.com",
            url="https://idp.example.com/sso",
            entity_id="https://idp.example.com/idp",
            x509_cert="idp-cert",
            services=["object", "management"],
            binding="none",
            sp_entity_id=AUTO_SP_ENTITY,
            trust_other_saml_sps_in_fleet=True,
        )
        current = _current_idp(
            services=["management", "object"],
            binding="none",
            trust=True,
            verification_certificate="idp-cert",
        )
        module, blade, models = _run(params, current=current)

        _no_writes(blade)
        kwargs = module.exit_json.call_args[1]
        assert kwargs["changed"] is False
        assert kwargs["prn"] == PRN
        assert kwargs["sp_entity_id"] == AUTO_SP_ENTITY

    def test_update_binding_carries_current_services(self):
        """The array wants services and binding together, so binding alone
        is sent with the current services, and nothing else new"""
        params = _base_params(binding="none")
        module, blade, models = _run(params, current=_current_idp())

        blade.patch_sso_saml2_idps.assert_called_once()
        assert "entity_id" not in models["Saml2SsoSp"].call_args[1]
        body = models["Saml2Sso"].call_args[1]
        assert body["binding"] == "none"
        assert body["services"] == ["management"]
        assert "management" not in body
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_services_compared_as_set(self):
        params = _base_params(services=["object", "management"])
        current = _current_idp(services=["management", "object"])
        module, blade, models = _run(params, current=current)

        _no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_services_carries_current_binding(self):
        params = _base_params(services=["object"])
        module, blade, models = _run(params, current=_current_idp())

        blade.patch_sso_saml2_idps.assert_called_once()
        body = models["Saml2Sso"].call_args[1]
        assert body["services"] == ["object"]
        assert body["binding"] == "http-redirect"
        assert "management" not in body
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_sp_entity_id_omits_services_and_binding(self):
        params = _base_params(sp_entity_id="https://sp.example.com")
        module, blade, models = _run(params, current=_current_idp())

        body = models["Saml2Sso"].call_args[1]
        assert "services" not in body
        assert "binding" not in body

    def test_update_trust_flag(self):
        params = _base_params(trust_other_saml_sps_in_fleet=True)
        module, blade, models = _run(params, current=_current_idp(trust=False))

        blade.patch_sso_saml2_idps.assert_called_once()
        models["Saml2SsoManagement"].assert_called_once_with(
            trust_other_saml_sps_in_fleet=True
        )
        body = models["Saml2Sso"].call_args[1]
        assert body["management"] is models["Saml2SsoManagement"].return_value
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_trust_flag_idempotent(self):
        params = _base_params(trust_other_saml_sps_in_fleet=False)
        module, blade, models = _run(params, current=_current_idp(trust=False))

        _no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_x509_cert_compares_by_name(self):
        params = _base_params(x509_cert="idp-cert")
        current = _current_idp(verification_certificate="idp-cert")
        module, blade, models = _run(params, current=current)

        _no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_x509_cert_sends_reference(self):
        params = _base_params(x509_cert="new-cert")
        current = _current_idp(verification_certificate="old-cert")
        module, blade, models = _run(params, current=current)

        blade.patch_sso_saml2_idps.assert_called_once()
        idp_kwargs = models["Saml2SsoIdp"].call_args[1]
        assert idp_kwargs["verification_certificate"] == ("ref", "new-cert")
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_ca_certificate_group_reference(self):
        params = _base_params(metadata_url_ca_certificate_group="idp-cas")
        module, blade, models = _run(params, current=_current_idp())

        blade.patch_sso_saml2_idps.assert_called_once()
        idp_kwargs = models["Saml2SsoIdp"].call_args[1]
        assert idp_kwargs["metadata_url_ca_certificate_group"] == ("ref", "idp-cas")
        assert idp_kwargs["metadata_url_ca_certificate"] is None
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_ca_certificate_idempotent(self):
        params = _base_params(metadata_url_ca_certificate="idp-ca")
        current = _current_idp(metadata_url_ca_certificate="idp-ca")
        module, blade, models = _run(params, current=current)

        _no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_ca_group_clears_ca_certificate(self):
        """The array refuses both CA references at once, so switching to the
        group sends an empty certificate reference"""
        params = _base_params(metadata_url_ca_certificate_group="idp-cas")
        current = _current_idp(metadata_url_ca_certificate="idp-ca")
        module, blade, models = _run(params, current=current)

        blade.patch_sso_saml2_idps.assert_called_once()
        idp_kwargs = models["Saml2SsoIdp"].call_args[1]
        assert idp_kwargs["metadata_url_ca_certificate_group"] == ("ref", "idp-cas")
        assert idp_kwargs["metadata_url_ca_certificate"] == ("ref", "")
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_ca_certificate_clears_ca_group(self):
        params = _base_params(metadata_url_ca_certificate="idp-ca")
        current = _current_idp(metadata_url_ca_certificate_group="idp-cas")
        module, blade, models = _run(params, current=current)

        blade.patch_sso_saml2_idps.assert_called_once()
        idp_kwargs = models["Saml2SsoIdp"].call_args[1]
        assert idp_kwargs["metadata_url_ca_certificate"] == ("ref", "idp-ca")
        assert idp_kwargs["metadata_url_ca_certificate_group"] == ("ref", "")
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_ca_certificate_clears_group_the_array_also_holds(self):
        """The array can hold both references; asking for the certificate it
        already has still clears the group"""
        params = _base_params(metadata_url_ca_certificate="idp-ca")
        current = _current_idp(
            metadata_url_ca_certificate="idp-ca",
            metadata_url_ca_certificate_group="idp-cas",
        )
        module, blade, models = _run(params, current=current)

        blade.patch_sso_saml2_idps.assert_called_once()
        idp_kwargs = models["Saml2SsoIdp"].call_args[1]
        assert idp_kwargs["metadata_url_ca_certificate"] == ("ref", "idp-ca")
        assert idp_kwargs["metadata_url_ca_certificate_group"] == ("ref", "")
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_new_field_keeps_enabled_provider_enabled(self):
        """A task that gives only a new option on an enabled provider sends
        neither enabled nor the signing and encryption flags, so the provider
        stays as it is"""
        params = _base_params(sp_entity_id="https://sp.example.com")
        current = _current_idp(enabled=True, sign_request=True, encrypt_asserts=True)
        module, blade, models = _run(params, current=current)

        blade.patch_sso_saml2_idps.assert_called_once()
        body = models["Saml2Sso"].call_args[1]
        assert "enabled" not in body
        idp_kwargs = models["Saml2SsoIdp"].call_args[1]
        assert "sign_request_enabled" not in idp_kwargs
        assert "encrypt_assertion_enabled" not in idp_kwargs
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_enabled_true_idempotent_on_enabled_provider(self):
        params = _base_params(enabled=True)
        module, blade, models = _run(params, current=_current_idp(enabled=True))

        _no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_enabled_false_disables_provider(self):
        params = _base_params(enabled=False)
        module, blade, models = _run(params, current=_current_idp(enabled=True))

        blade.patch_sso_saml2_idps.assert_called_once()
        body = models["Saml2Sso"].call_args[1]
        assert body["enabled"] is False
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_sign_request_sent_only_when_given(self):
        params = _base_params(sign_request=True, signing_credential="sp-signing")
        module, blade, models = _run(params, current=_current_idp())

        blade.patch_sso_saml2_idps.assert_called_once()
        idp_kwargs = models["Saml2SsoIdp"].call_args[1]
        assert idp_kwargs["sign_request_enabled"] is True
        assert "encrypt_assertion_enabled" not in idp_kwargs
        sp_kwargs = models["Saml2SsoSp"].call_args[1]
        assert sp_kwargs["signing_credential"] == ("ref", "sp-signing")
        assert "enabled" not in models["Saml2Sso"].call_args[1]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_flags_idempotent_when_matching(self):
        params = _base_params(enabled=False, sign_request=False, encrypt_asserts=False)
        module, blade, models = _run(params, current=_current_idp())

        _no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_check_mode_skips_patch(self):
        params = _base_params(sp_entity_id="https://sp.example.com")
        module, blade, models = _run(params, current=_current_idp(), check_mode=True)

        _no_writes(blade)
        kwargs = module.exit_json.call_args[1]
        assert kwargs["changed"] is True
        # facts come from the current object in check mode
        assert kwargs["sp_entity_id"] == AUTO_SP_ENTITY

    def test_update_api_error_fails(self):
        params = _base_params(binding="none")
        module, blade, models = _run(params, current=_current_idp(), patch_status=400)

        module.fail_json.assert_called_once()
        assert "Failed to update SAML2 IdP" in module.fail_json.call_args[1]["msg"]
        module.exit_json.assert_not_called()


class TestPurefbSamlGates:
    """Version gates and option rules, all before any write"""

    def test_services_gate(self):
        params = _base_params(services=["object"])
        module, blade, models = _run(params, api_version="2.16")

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "services" in msg
        assert "2.17" in msg
        blade.get_sso_saml2_idps.assert_not_called()
        _no_writes(blade)

    def test_ca_certificate_gate(self):
        params = _base_params(metadata_url_ca_certificate="idp-ca")
        module, blade, models = _run(params, api_version="2.16")

        module.fail_json.assert_called_once()
        assert "2.17" in module.fail_json.call_args[1]["msg"]
        _no_writes(blade)

    def test_services_allowed_at_2_17(self):
        params = _base_params(array_url="https://fb.example.com", services=["object"])
        module, blade, models = _run(params, api_version="2.17")

        module.fail_json.assert_not_called()
        blade.post_sso_saml2_idps.assert_called_once()

    def test_sp_entity_id_gate(self):
        params = _base_params(sp_entity_id="https://sp.example.com")
        module, blade, models = _run(params, api_version="2.23", current=_current_idp())

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "sp_entity_id" in msg
        assert "2.24" in msg
        _no_writes(blade)

    def test_trust_flag_gate(self):
        params = _base_params(trust_other_saml_sps_in_fleet=True)
        module, blade, models = _run(params, api_version="2.23", current=_current_idp())

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "trust_other_saml_sps_in_fleet" in msg
        assert "2.24" in msg
        _no_writes(blade)

    def test_trust_flag_allowed_at_2_24(self):
        params = _base_params(trust_other_saml_sps_in_fleet=True)
        module, blade, models = _run(params, api_version="2.24", current=_current_idp())

        module.fail_json.assert_not_called()
        blade.patch_sso_saml2_idps.assert_called_once()

    def test_trust_flag_requires_management_service_option(self):
        params = _base_params(services=["object"], trust_other_saml_sps_in_fleet=False)
        module, blade, models = _run(params, current=_current_idp())

        module.fail_json.assert_called_once()
        assert "management" in module.fail_json.call_args[1]["msg"]
        _no_writes(blade)

    def test_trust_flag_requires_management_service_current(self):
        params = _base_params(trust_other_saml_sps_in_fleet=True)
        current = _current_idp(services=["object"])
        module, blade, models = _run(params, current=current)

        module.fail_json.assert_called_once()
        assert "management" in module.fail_json.call_args[1]["msg"]
        _no_writes(blade)

    def test_empty_services_rejected(self):
        params = _base_params(services=[])
        module, blade, models = _run(params)

        module.fail_json.assert_called_once()
        assert "services" in module.fail_json.call_args[1]["msg"]
        _no_writes(blade)

    def test_minimum_version_gate(self):
        params = _base_params()
        module, blade, models = _run(params, api_version="2.14")

        module.fail_json.assert_called_once()
        assert "2.15" in module.fail_json.call_args[1]["msg"]
        blade.get_sso_saml2_idps.assert_not_called()

    def test_state_test_gate_names_test_version(self):
        params = _base_params(state="test")
        module, blade, models = _run(params, api_version="2.15")

        module.fail_json.assert_called_once()
        assert "2.16" in module.fail_json.call_args[1]["msg"]
        blade.get_sso_saml2_idps_test.assert_not_called()


class TestPurefbSamlDeleteAndTest:
    """Delete and test paths"""

    def test_delete(self):
        params = _base_params(state="absent")
        module, blade, models = _run(params, current=_current_idp())

        blade.delete_sso_saml2_idps.assert_called_once_with(names=[IDP_NAME])
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_absent_is_noop(self):
        params = _base_params(state="absent")
        module, blade, models = _run(params)

        _no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is False

    def test_delete_check_mode(self):
        params = _base_params(state="absent")
        module, blade, models = _run(params, current=_current_idp(), check_mode=True)

        _no_writes(blade)
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_api_error_fails(self):
        params = _base_params(state="absent")
        module, blade, models = _run(params, current=_current_idp(), delete_status=400)

        module.fail_json.assert_called_once()
        assert "Failed to delete SAML2 IdP" in module.fail_json.call_args[1]["msg"]

    def test_state_test_reports_components(self):
        params = _base_params(state="test")
        component = Mock()
        component.enabled = True
        component.success = False
        component.component_address = "10.0.0.1"
        component.component_name = "CH1.FM1"
        component.description = "metadata fetch"
        component.destination = "https://idp.example.com"
        component.result_details = "timeout"
        component.test_type = "connectivity"
        component.resource = _reference(IDP_NAME)
        module, blade, models = _run(
            params, current=_current_idp(), test_items=[component]
        )

        blade.get_sso_saml2_idps_test.assert_called_once_with(names=[IDP_NAME])
        _no_writes(blade)
        kwargs = module.exit_json.call_args[1]
        assert kwargs["changed"] is False
        assert kwargs["test_response"] == [
            {
                "component_address": "10.0.0.1",
                "component_name": "CH1.FM1",
                "description": "metadata fetch",
                "destination": "https://idp.example.com",
                "enabled": "true",
                "result_details": "timeout",
                "success": "false",
                "test_type": "connectivity",
                "resource_name": IDP_NAME,
            }
        ]


def _read(response):
    """Call _get_idp against one GET answer; return (result, module)"""
    module = Mock()
    module.fail_json = Mock(side_effect=SystemExit)
    blade = Mock()
    blade.get_sso_saml2_idps.return_value = response
    result = None
    with patch(MODULE + ".get_error_message", side_effect=_error_message):
        try:
            result = saml._get_idp(module, blade, IDP_NAME)
        except SystemExit:
            pass
    return result, module


class TestPurefbSamlRead:
    """Only the array's "does not exist" answer means the provider is absent"""

    def test_get_idp_returns_the_provider(self):
        current = _current_idp()
        result, module = _read(_response(200, [current]))

        assert result is current
        module.fail_json.assert_not_called()

    def test_get_idp_none_when_the_array_says_it_does_not_exist(self):
        for message in (ABSENT, ABSENT.upper()):
            result, module = _read(_response(400, error=message))

            assert result is None
            module.fail_json.assert_not_called()

    def test_get_idp_none_on_empty_item_list(self):
        result, module = _read(_response(200, []))

        assert result is None
        module.fail_json.assert_not_called()

    def test_get_idp_fails_with_the_array_message(self):
        custom_role = (
            "Operation not permitted. Authorization for 'get' on "
            "'purestorage.com/api/v2/sso/saml2/idps' is required."
        )
        for status, message in (
            (400, REFUSED),
            (400, custom_role),
            (500, "Internal error"),
        ):
            result, module = _read(_response(status, error=message))

            assert result is None
            module.fail_json.assert_called_once_with(
                msg="Failed to read SAML2 IdP myidp. Error: " + message
            )

    def test_get_idp_fails_when_the_array_gives_no_message(self):
        result, module = _read(_response(503))

        module.fail_json.assert_called_once_with(
            msg="Failed to read SAML2 IdP myidp. Error: Unknown error"
        )

    def test_refused_read_is_not_a_create(self):
        params = _base_params(array_url="https://fb.example.com")
        for check_mode in (False, True):
            module, blade, models = _run(
                params,
                check_mode=check_mode,
                get_side_effect=[_response(400, error=REFUSED)],
            )

            _no_writes(blade)
            module.exit_json.assert_not_called()
            module.fail_json.assert_called_once_with(
                msg="Failed to read SAML2 IdP myidp. Error: Operation not permitted."
            )

    def test_failed_read_is_not_absent_for_state_absent(self):
        params = _base_params(state="absent")
        module, blade, models = _run(
            params, get_side_effect=[_response(500, error="Internal error")]
        )

        _no_writes(blade)
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once_with(
            msg="Failed to read SAML2 IdP myidp. Error: Internal error"
        )

    def test_failed_read_is_reported_for_state_test(self):
        params = _base_params(state="test")
        module, blade, models = _run(
            params, get_side_effect=[_response(400, error=REFUSED)]
        )

        blade.get_sso_saml2_idps_test.assert_not_called()
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once_with(
            msg="Failed to read SAML2 IdP myidp. Error: Operation not permitted."
        )

    def test_failed_read_back_after_create_is_reported(self):
        params = _base_params(array_url="https://fb.example.com")
        module, blade, models = _run(
            params,
            get_side_effect=[
                _response(400, error=ABSENT),
                _response(500, error="Internal error"),
            ],
        )

        blade.post_sso_saml2_idps.assert_called_once()
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once_with(
            msg="Failed to read SAML2 IdP myidp. Error: Internal error"
        )

    def test_failed_read_back_after_update_is_reported(self):
        params = _base_params(entity_id="https://idp.example.com/other")
        module, blade, models = _run(
            params,
            get_side_effect=[
                _response(200, [_current_idp()]),
                _response(500, error="Internal error"),
            ],
        )

        blade.patch_sso_saml2_idps.assert_called_once()
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once_with(
            msg="Failed to read SAML2 IdP myidp. Error: Internal error"
        )


class TestPurefbSamlTestState:
    """state=test: a refused test and a missing provider are failures"""

    def test_refused_test_reports_the_array_message(self):
        """An administrator limited to a realm reads a shared provider, but
        the array refuses it the test and answers without items"""
        params = _base_params(state="test")
        module, blade, models = _run(
            params,
            current=_current_idp(),
            test_response=_response(400, error=REFUSED),
        )

        blade.get_sso_saml2_idps_test.assert_called_once_with(names=[IDP_NAME])
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once_with(
            msg="Failed to test SAML2 IdP myidp. Error: Operation not permitted."
        )

    def test_missing_provider_fails(self):
        """Also what an administrator limited to a realm gets for a provider
        that is not shared with its realm"""
        params = _base_params(state="test")
        for check_mode in (False, True):
            module, blade, models = _run(params, check_mode=check_mode)

            blade.get_sso_saml2_idps_test.assert_not_called()
            module.exit_json.assert_not_called()
            module.fail_json.assert_called_once_with(
                msg="SAML2 IdP myidp does not exist"
            )

    def test_check_mode_runs_the_read_only_test(self):
        params = _base_params(state="test")
        module, blade, models = _run(params, current=_current_idp(), check_mode=True)

        blade.get_sso_saml2_idps_test.assert_called_once_with(names=[IDP_NAME])
        _no_writes(blade)
        module.exit_json.assert_called_once_with(changed=False, test_response=[])


REALM_IDP = "realm1::myidp"
REALM_CERT = "realm1::idp-signing-cert"
# references for which the array accepts a certificate in another letter case
CERT_OPTIONS = ("x509_cert", "signing_credential", "decryption_credential")
REFERENCE_OPTIONS = CERT_OPTIONS + (
    "metadata_url_ca_certificate",
    "metadata_url_ca_certificate_group",
)


class TestPurefbSamlRealm:
    """Providers are array-level: a realm-qualified name never reaches the array"""

    def test_realm_qualified_name_refused_in_every_state(self):
        for state in ("present", "absent", "test"):
            for check_mode in (False, True):
                params = _base_params(
                    name=REALM_IDP, state=state, array_url="https://fb.example.com"
                )
                module, blade, models = _run(params, check_mode=check_mode)

                blade.get_sso_saml2_idps.assert_not_called()
                blade.get_sso_saml2_idps_test.assert_not_called()
                _no_writes(blade)
                module.exit_json.assert_not_called()
                msg = module.fail_json.call_args[1]["msg"]
                assert "Invalid name 'realm1::myidp'" in msg
                assert "realm-qualified" in msg
                assert "sso/saml2/idps" in msg

    def test_realm_qualified_reference_refused_on_create(self):
        for option in REFERENCE_OPTIONS:
            for check_mode in (False, True):
                params = _base_params(
                    array_url="https://fb.example.com", **{option: REALM_CERT}
                )
                module, blade, models = _run(params, check_mode=check_mode)

                blade.get_sso_saml2_idps.assert_not_called()
                _no_writes(blade)
                module.exit_json.assert_not_called()
                msg = module.fail_json.call_args[1]["msg"]
                assert "Invalid {0} '{1}'".format(option, REALM_CERT) in msg
                assert "array-level" in msg

    def test_realm_qualified_reference_refused_on_update(self):
        for option in REFERENCE_OPTIONS:
            for check_mode in (False, True):
                params = _base_params(**{option: REALM_CERT})
                module, blade, models = _run(
                    params, current=_current_idp(), check_mode=check_mode
                )

                _no_writes(blade)
                module.exit_json.assert_not_called()
                msg = module.fail_json.call_args[1]["msg"]
                assert "Invalid {0} '{1}'".format(option, REALM_CERT) in msg

    def test_references_are_not_read_for_absent(self):
        params = _base_params(state="absent", x509_cert=REALM_CERT)
        module, blade, models = _run(params, current=_current_idp())

        blade.delete_sso_saml2_idps.assert_called_once_with(names=[IDP_NAME])
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_array_level_names_pass(self):
        module = Mock()
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(
            x509_cert="idp-signing-cert",
            signing_credential="sp-cert",
            metadata_url_ca_certificate_group="ca-group",
        )

        saml._refuse_realm_names(module)

        module.fail_json.assert_not_called()

    def test_shared_provider_is_read_without_a_change(self):
        """What an administrator limited to a realm gets for a provider that
        is shared with its realm"""
        params = _base_params()
        module, blade, models = _run(params, current=_current_idp())

        _no_writes(blade)
        module.exit_json.assert_called_once_with(
            changed=False, prn=PRN, sp_entity_id=AUTO_SP_ENTITY
        )

    def test_refused_update_reports_the_array_message(self):
        params = _base_params(entity_id="https://idp.example.com/other")
        module, blade, models = _run(
            params, current=_current_idp(), patch_status=400, patch_error=REFUSED
        )

        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once_with(
            msg="Failed to update SAML2 IdP myidp. Error: Operation not permitted."
        )


class TestPurefbSamlLetterCase:
    """The array accepts the verification certificate and the service provider
    credentials in another letter case and returns the stored spelling"""

    @staticmethod
    def _current():
        current = _current_idp(
            verification_certificate="idp-signing-cert",
            metadata_url_ca_certificate="idp-signing-cert",
        )
        current.sp.signing_credential = _reference("idp-signing-cert")
        current.sp.decryption_credential = _reference("idp-signing-cert")
        return current

    def test_same_name(self):
        assert saml._same_name("IdP-Cert", "idp-cert") is True
        assert saml._same_name("idp-cert", "idp-cert") is True
        assert saml._same_name("idp-cert", "other") is False
        assert saml._same_name(None, "idp-cert") is False
        assert saml._same_name("idp-cert", None) is False

    def test_certificate_in_another_case_is_not_a_change(self):
        for option in CERT_OPTIONS:
            for check_mode in (False, True):
                params = _base_params(**{option: "IDP-Signing-Cert"})
                module, blade, models = _run(
                    params, current=self._current(), check_mode=check_mode
                )

                _no_writes(blade)
                module.exit_json.assert_called_once_with(
                    changed=False, prn=PRN, sp_entity_id=AUTO_SP_ENTITY
                )

    def test_stored_spelling_is_sent_with_another_change(self):
        params = _base_params(
            x509_cert="IDP-SIGNING-CERT", entity_id="https://idp.example.com/other"
        )
        module, blade, models = _run(params, current=self._current())

        blade.patch_sso_saml2_idps.assert_called_once()
        idp_kwargs = models["Saml2SsoIdp"].call_args[1]
        assert idp_kwargs["verification_certificate"] == ("ref", "idp-signing-cert")
        assert idp_kwargs["entity_id"] == "https://idp.example.com/other"

    def test_another_certificate_is_a_change(self):
        params = _base_params(x509_cert="other-cert")
        module, blade, models = _run(params, current=self._current())

        blade.patch_sso_saml2_idps.assert_called_once()
        idp_kwargs = models["Saml2SsoIdp"].call_args[1]
        assert idp_kwargs["verification_certificate"] == ("ref", "other-cert")
        assert module.exit_json.call_args[1]["changed"] is True

    def test_ca_references_are_matched_exactly(self):
        """The array resolves the CA certificate and the CA certificate group
        by their exact names, so another case is sent and the array decides"""
        for option, value in (
            ("metadata_url_ca_certificate", "IDP-SIGNING-CERT"),
            ("metadata_url_ca_certificate_group", "CA-GROUP"),
        ):
            current = _current_idp(
                metadata_url_ca_certificate=(
                    "idp-signing-cert" if option.endswith("certificate") else None
                ),
                metadata_url_ca_certificate_group=(
                    "ca-group" if option.endswith("group") else None
                ),
            )
            params = _base_params(**{option: value})
            module, blade, models = _run(params, current=current)

            blade.patch_sso_saml2_idps.assert_called_once()
            idp_kwargs = models["Saml2SsoIdp"].call_args[1]
            assert idp_kwargs[option] == ("ref", value)


class TestPurefbSamlNamePatterns:
    """The array reads * in a name as a pattern and a comma as a separator of
    names, so such a name never reaches the array"""

    def test_pattern_or_list_refused_in_every_state(self):
        for name in ("*", "my*", "*idp", "myidp,otheridp", "myidp,"):
            for state in ("present", "absent", "test"):
                for check_mode in (False, True):
                    params = _base_params(
                        name=name, state=state, array_url="https://fb.example.com"
                    )
                    # what the array answers: the providers that match
                    module, blade, models = _run(
                        params, current=_current_idp(), check_mode=check_mode
                    )

                    blade.get_sso_saml2_idps.assert_not_called()
                    blade.get_sso_saml2_idps_test.assert_not_called()
                    _no_writes(blade)
                    module.exit_json.assert_not_called()
                    msg = module.fail_json.call_args[1]["msg"]
                    assert "Invalid name '{0}'".format(name) in msg
                    assert "pattern" in msg
                    assert "separator" in msg

    def test_pattern_is_refused_before_the_realm_check(self):
        params = _base_params(name="realm1::*", state="absent")
        module, blade, models = _run(params, current=_current_idp())

        blade.get_sso_saml2_idps.assert_not_called()
        _no_writes(blade)
        assert "pattern" in module.fail_json.call_args[1]["msg"]

    def test_plain_names_pass(self):
        for name in ("myidp", "My_IdP-2", "PureSSO"):
            module = Mock()
            module.fail_json = Mock(side_effect=SystemExit)
            module.params = _base_params(name=name)

            saml._refuse_name_patterns(module)

            module.fail_json.assert_not_called()

    def test_the_lookup_uses_the_exact_name(self):
        params = _base_params(state="absent")
        module, blade, models = _run(params, current=_current_idp())

        blade.get_sso_saml2_idps.assert_called_once_with(names=[IDP_NAME])
        blade.delete_sso_saml2_idps.assert_called_once_with(names=[IDP_NAME])
