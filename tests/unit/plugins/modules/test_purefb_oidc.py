# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_oidc module."""

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

from plugins.modules.purefb_oidc import (
    main,
    _facts,
    _get_idp,
    _reference_name,
)

MODULE = "plugins.modules.purefb_oidc"
URL = "https://acme.okta.com/oauth2/default"
PRN = "prn::iam:array-id/local::oidc-provider/okta"


def _base_params(**overrides):
    params = {
        "name": "okta",
        "state": "present",
        "provider_url": URL,
        "services": ["object"],
        "ca_certificate": None,
        "ca_certificate_group": None,
        "enabled": None,
        "rename": None,
    }
    params.update(overrides)
    return params


def _ref(name):
    ref = Mock(spec=["name"])
    ref.name = name
    return ref


def _existing(**overrides):
    """A provider as the array returns it, matching _base_params by default."""
    cfg = Mock(
        spec=[
            "provider_url",
            "provider_url_ca_certificate",
            "provider_url_ca_certificate_group",
        ]
    )
    cfg.provider_url = URL
    # unset references come back as empty objects
    cfg.provider_url_ca_certificate = {}
    cfg.provider_url_ca_certificate_group = {}
    idp = Mock(spec=["name", "enabled", "prn", "services", "idp"])
    idp.name = "okta"
    idp.enabled = True
    idp.prn = PRN
    idp.services = ["object"]
    idp.idp = cfg
    for key, value in overrides.items():
        if key in ("provider_url", "ca_certificate", "ca_certificate_group"):
            field = {
                "provider_url": "provider_url",
                "ca_certificate": "provider_url_ca_certificate",
                "ca_certificate_group": "provider_url_ca_certificate_group",
            }[key]
            setattr(cfg, field, value)
        else:
            setattr(idp, key, value)
    return idp


def _response(status_code=200, items=None):
    res = Mock()
    res.status_code = status_code
    res.items = items if items is not None else []
    res.errors = []
    return res


def _module(params, check_mode=False):
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.params = params
    module.check_mode = check_mode
    return module


def _run():
    try:
        main()
    except SystemExit:
        pass


def _array_lookup(*providers):
    """get_sso_oidc_idps of an array that holds the given array-level providers.

    The array answers a realm-qualified name like any other name that is not
    configured: 400.
    """
    held = dict((idp.name, idp) for idp in providers)

    def lookup(names):
        idp = held.get(names[0])
        return _response(200, [idp]) if idp else _response(400)

    return lookup


class TestPurefbOidcHelpers:
    """Helper-function unit tests"""

    def test_reference_name_unset_reference(self):
        idp = _existing()
        assert _reference_name(idp.idp, "provider_url_ca_certificate") is None
        assert _reference_name(idp.idp, "missing") is None
        assert _reference_name(None, "provider_url_ca_certificate") is None

    def test_reference_name_set_reference(self):
        idp = _existing(ca_certificate=_ref("sso-root-ca"))
        assert _reference_name(idp.idp, "provider_url_ca_certificate") == "sso-root-ca"

    def test_get_idp_returns_item(self):
        module = _module(_base_params())
        blade = Mock()
        idp = _existing()
        blade.get_sso_oidc_idps.return_value = _response(200, [idp])

        assert _get_idp(module, blade, "okta") is idp
        blade.get_sso_oidc_idps.assert_called_once_with(names=["okta"])
        module.fail_json.assert_not_called()

    def test_get_idp_none_when_missing(self):
        module = _module(_base_params())
        blade = Mock()
        # the array answers 400 "configuration does not exist" for a missing name
        blade.get_sso_oidc_idps.return_value = _response(400)
        assert _get_idp(module, blade, "okta") is None

        blade.get_sso_oidc_idps.return_value = _response(200, [])
        assert _get_idp(module, blade, "okta") is None
        module.fail_json.assert_not_called()

    def test_get_idp_fails_on_unexpected_status(self):
        """Only the array's 400 means absent; anything else is an error."""
        module = _module(_base_params())
        blade = Mock()
        blade.get_sso_oidc_idps.return_value = _response(500)

        try:
            _get_idp(module, blade, "okta")
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to read OIDC identity provider okta" in msg

    def test_facts_reports_every_field(self):
        idp = _existing(
            ca_certificate=_ref("sso-root-ca"),
            ca_certificate_group=_ref("corporate-cas"),
            enabled=False,
        )
        assert _facts(idp) == {
            "name": "okta",
            "enabled": False,
            "prn": PRN,
            "provider_url": URL,
            "services": ["object"],
            "ca_certificate": "sso-root-ca",
            "ca_certificate_group": "corporate-cas",
        }

    def test_facts_unset_references_are_none(self):
        facts = _facts(_existing())
        assert facts["ca_certificate"] is None
        assert facts["ca_certificate_group"] is None
        assert facts["services"] == ["object"]


@patch(MODULE + ".LooseVersion")
@patch(MODULE + ".get_system")
@patch(MODULE + ".AnsibleModule")
@patch(MODULE + ".HAS_PYPURECLIENT", True)
class TestPurefbOidcMain:
    """main() flows; the version gate passes unless a test says otherwise"""

    @staticmethod
    def _setup(
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        params,
        check_mode=False,
    ):
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(params, check_mode)
        mock_ansible_module.return_value = module
        blade = Mock()
        mock_get_system.return_value = blade
        return module, blade

    # ---------------- create ----------------

    @patch(MODULE + ".Reference")
    @patch(MODULE + ".OidcSsoPostIdp")
    @patch(MODULE + ".OidcSsoPost")
    def test_create_idp(
        self, mock_post_model, mock_idp_model, mock_ref, mock_am, mock_gs, mock_lv
    ):
        module, blade = self._setup(mock_am, mock_gs, mock_lv, _base_params())
        created = _existing()
        blade.get_sso_oidc_idps.side_effect = [
            _response(400),
            _response(200, [created]),
        ]
        blade.post_sso_oidc_idps.return_value = _response(200, [created])

        _run()

        blade.post_sso_oidc_idps.assert_called_once()
        assert blade.post_sso_oidc_idps.call_args[1]["names"] == ["okta"]
        body = mock_post_model.call_args[1]
        # services is mandatory on the array and always sent
        assert body["services"] == ["object"]
        # enabled omitted -> array default, not sent
        assert "enabled" not in body
        mock_idp_model.assert_called_once_with(provider_url=URL)
        mock_ref.assert_not_called()
        module.exit_json.assert_called_once()
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["prn"] == PRN
        assert result["provider_url"] == URL
        assert result["enabled"] is True

    @patch(MODULE + ".Reference")
    @patch(MODULE + ".OidcSsoPostIdp")
    @patch(MODULE + ".OidcSsoPost")
    def test_create_idp_disabled_with_references(
        self, mock_post_model, mock_idp_model, mock_ref, mock_am, mock_gs, mock_lv
    ):
        params = _base_params(
            enabled=False,
            ca_certificate="sso-root-ca",
            ca_certificate_group="corporate-cas",
        )
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        blade.get_sso_oidc_idps.side_effect = [_response(400), _response(400)]
        blade.post_sso_oidc_idps.return_value = _response(200)

        _run()

        body = mock_post_model.call_args[1]
        assert body["enabled"] is False
        idp_cfg = mock_idp_model.call_args[1]
        assert idp_cfg["provider_url"] == URL
        assert "provider_url_ca_certificate" in idp_cfg
        assert "provider_url_ca_certificate_group" in idp_cfg
        mock_ref.assert_any_call(name="sso-root-ca")
        mock_ref.assert_any_call(name="corporate-cas")
        # the read-back after the POST found nothing, so the play values are reported
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["enabled"] is False
        assert result["ca_certificate"] == "sso-root-ca"
        assert result["ca_certificate_group"] == "corporate-cas"

    def test_create_check_mode_skips_post(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(), check_mode=True
        )
        blade.get_sso_oidc_idps.return_value = _response(400)

        _run()

        blade.post_sso_oidc_idps.assert_not_called()
        # only the existence lookup ran; no read-back in check mode
        blade.get_sso_oidc_idps.assert_called_once_with(names=["okta"])
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["prn"] is None
        assert result["name"] == "okta"
        assert result["provider_url"] == URL

    def test_create_requires_provider_url(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(provider_url=None)
        )
        blade.get_sso_oidc_idps.return_value = _response(400)

        _run()

        blade.post_sso_oidc_idps.assert_not_called()
        module.fail_json.assert_called_once()
        assert "provider_url is required" in module.fail_json.call_args[1]["msg"]

    def test_create_fails_on_api_error(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(mock_am, mock_gs, mock_lv, _base_params())
        blade.get_sso_oidc_idps.return_value = _response(400)
        blade.post_sso_oidc_idps.return_value = _response(400)

        _run()

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to create OIDC identity provider okta" in msg

    # ---------------- update ----------------

    def test_update_idempotent(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(mock_am, mock_gs, mock_lv, _base_params())
        blade.get_sso_oidc_idps.return_value = _response(200, [_existing()])

        _run()

        blade.patch_sso_oidc_idps.assert_not_called()
        blade.post_sso_oidc_idps.assert_not_called()
        # nothing was written, so nothing is read back either
        blade.get_sso_oidc_idps.assert_called_once_with(names=["okta"])
        result = module.exit_json.call_args[1]
        assert result["changed"] is False
        assert result["prn"] == PRN
        assert result["services"] == ["object"]

    def test_update_idempotent_with_references_and_enabled(
        self, mock_am, mock_gs, mock_lv
    ):
        params = _base_params(enabled=True, ca_certificate="sso-root-ca")
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        blade.get_sso_oidc_idps.return_value = _response(
            200, [_existing(ca_certificate=_ref("sso-root-ca"))]
        )

        _run()

        blade.patch_sso_oidc_idps.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_update_omitted_fields_are_left_alone(self, mock_am, mock_gs, mock_lv):
        """A play with only the name touches nothing on a disabled provider."""
        params = _base_params(provider_url=None)
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        blade.get_sso_oidc_idps.return_value = _response(
            200, [_existing(enabled=False, ca_certificate=_ref("sso-root-ca"))]
        )

        _run()

        blade.patch_sso_oidc_idps.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is False
        assert result["enabled"] is False
        assert result["ca_certificate"] == "sso-root-ca"

    @patch(MODULE + ".OidcSsoPatch")
    def test_update_enabled_only_sends_enabled(
        self, mock_patch_model, mock_am, mock_gs, mock_lv
    ):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(enabled=False)
        )
        blade.get_sso_oidc_idps.side_effect = [
            _response(200, [_existing()]),
            _response(200, [_existing(enabled=False)]),
        ]
        blade.patch_sso_oidc_idps.return_value = _response(200)

        _run()

        blade.patch_sso_oidc_idps.assert_called_once()
        assert blade.patch_sso_oidc_idps.call_args[1]["names"] == ["okta"]
        mock_patch_model.assert_called_once_with(enabled=False)
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["enabled"] is False

    @patch(MODULE + ".OidcSsoPostIdp")
    @patch(MODULE + ".OidcSsoPatch")
    def test_update_provider_url_sends_only_the_url(
        self, mock_patch_model, mock_idp_model, mock_am, mock_gs, mock_lv
    ):
        new_url = "https://login.example.com"
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(provider_url=new_url)
        )
        blade.get_sso_oidc_idps.side_effect = [
            _response(200, [_existing(ca_certificate=_ref("sso-root-ca"))]),
            _response(200, [_existing(provider_url=new_url)]),
        ]
        blade.patch_sso_oidc_idps.return_value = _response(200)

        _run()

        # a partial idp object leaves the CA references untouched on the array
        mock_idp_model.assert_called_once_with(provider_url=new_url)
        patch_kwargs = mock_patch_model.call_args[1]
        assert list(patch_kwargs) == ["idp"]
        assert module.exit_json.call_args[1]["provider_url"] == new_url

    @patch(MODULE + ".Reference")
    @patch(MODULE + ".OidcSsoPostIdp")
    @patch(MODULE + ".OidcSsoPatch")
    def test_update_sets_ca_certificate(
        self, mock_patch_model, mock_idp_model, mock_ref, mock_am, mock_gs, mock_lv
    ):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(ca_certificate="sso-root-ca")
        )
        blade.get_sso_oidc_idps.return_value = _response(200, [_existing()])
        blade.patch_sso_oidc_idps.return_value = _response(200)

        _run()

        mock_ref.assert_called_once_with(name="sso-root-ca")
        idp_cfg = mock_idp_model.call_args[1]
        assert list(idp_cfg) == ["provider_url_ca_certificate"]
        assert module.exit_json.call_args[1]["changed"] is True

    @patch(MODULE + ".Reference")
    @patch(MODULE + ".OidcSsoPostIdp")
    @patch(MODULE + ".OidcSsoPatch")
    def test_update_clears_ca_certificate_with_empty_string(
        self, mock_patch_model, mock_idp_model, mock_ref, mock_am, mock_gs, mock_lv
    ):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(ca_certificate="")
        )
        blade.get_sso_oidc_idps.side_effect = [
            _response(200, [_existing(ca_certificate=_ref("sso-root-ca"))]),
            _response(200, [_existing()]),
        ]
        blade.patch_sso_oidc_idps.return_value = _response(200)

        _run()

        # the array clears a reference when it is sent with an empty name
        mock_ref.assert_called_once_with(name="")
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["ca_certificate"] is None

    def test_update_clear_already_clear_is_idempotent(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(ca_certificate="")
        )
        blade.get_sso_oidc_idps.return_value = _response(200, [_existing()])

        _run()

        blade.patch_sso_oidc_idps.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @patch(MODULE + ".Reference")
    @patch(MODULE + ".OidcSsoPostIdp")
    @patch(MODULE + ".OidcSsoPatch")
    def test_update_switches_certificate_to_group_in_one_patch(
        self, mock_patch_model, mock_idp_model, mock_ref, mock_am, mock_gs, mock_lv
    ):
        params = _base_params(ca_certificate="", ca_certificate_group="corporate-cas")
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        blade.get_sso_oidc_idps.side_effect = [
            _response(200, [_existing(ca_certificate=_ref("sso-root-ca"))]),
            _response(200, [_existing(ca_certificate_group=_ref("corporate-cas"))]),
        ]
        blade.patch_sso_oidc_idps.return_value = _response(200)

        _run()

        blade.patch_sso_oidc_idps.assert_called_once()
        idp_cfg = mock_idp_model.call_args[1]
        assert sorted(idp_cfg) == [
            "provider_url_ca_certificate",
            "provider_url_ca_certificate_group",
        ]
        mock_ref.assert_any_call(name="")
        mock_ref.assert_any_call(name="corporate-cas")
        result = module.exit_json.call_args[1]
        assert result["ca_certificate"] is None
        assert result["ca_certificate_group"] == "corporate-cas"

    @patch(MODULE + ".OidcSsoPatch")
    def test_update_rename(self, mock_patch_model, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(rename="okta-prod")
        )
        renamed = _existing(name="okta-prod")
        renamed.prn = "prn::iam:array-id/local::oidc-provider/okta-prod"
        blade.get_sso_oidc_idps.side_effect = [
            _response(200, [_existing()]),
            # the rename target is looked up before the PATCH and must be absent
            _response(400),
            _response(200, [renamed]),
        ]
        blade.patch_sso_oidc_idps.return_value = _response(200)

        _run()

        # addressed by the current name; read back by the new one
        assert blade.patch_sso_oidc_idps.call_args[1]["names"] == ["okta"]
        mock_patch_model.assert_called_once_with(name="okta-prod")
        assert blade.get_sso_oidc_idps.call_count == 3
        blade.get_sso_oidc_idps.assert_any_call(names=["okta-prod"])
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["name"] == "okta-prod"
        assert result["prn"].endswith("/okta-prod")

    def test_rename_to_existing_name_fails_before_patch(
        self, mock_am, mock_gs, mock_lv
    ):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(rename="okta-prod")
        )
        blade.get_sso_oidc_idps.side_effect = [
            _response(200, [_existing()]),
            _response(200, [_existing(name="okta-prod")]),
        ]

        _run()

        blade.patch_sso_oidc_idps.assert_not_called()
        blade.post_sso_oidc_idps.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Cannot rename OIDC identity provider okta" in msg
        assert "okta-prod already exists" in msg

    def test_rename_already_done_is_idempotent(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(rename="okta-prod")
        )
        blade.get_sso_oidc_idps.side_effect = [
            _response(400),
            _response(200, [_existing(name="okta-prod")]),
        ]

        _run()

        assert blade.get_sso_oidc_idps.call_count == 2
        blade.get_sso_oidc_idps.assert_any_call(names=["okta-prod"])
        blade.patch_sso_oidc_idps.assert_not_called()
        blade.post_sso_oidc_idps.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is False
        assert result["name"] == "okta-prod"

    @patch(MODULE + ".OidcSsoPatch")
    def test_rename_already_done_still_applies_other_changes(
        self, mock_patch_model, mock_am, mock_gs, mock_lv
    ):
        params = _base_params(rename="okta-prod", enabled=False)
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        blade.get_sso_oidc_idps.side_effect = [
            _response(400),
            _response(200, [_existing(name="okta-prod")]),
            _response(200, [_existing(name="okta-prod", enabled=False)]),
        ]
        blade.patch_sso_oidc_idps.return_value = _response(200)

        _run()

        assert blade.patch_sso_oidc_idps.call_args[1]["names"] == ["okta-prod"]
        mock_patch_model.assert_called_once_with(enabled=False)
        assert module.exit_json.call_args[1]["changed"] is True

    def test_update_check_mode_skips_patch(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(enabled=False), check_mode=True
        )
        blade.get_sso_oidc_idps.return_value = _response(200, [_existing()])

        _run()

        blade.patch_sso_oidc_idps.assert_not_called()
        blade.get_sso_oidc_idps.assert_called_once_with(names=["okta"])
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        # the predicted state is reported, with the prn the array already has
        assert result["enabled"] is False
        assert result["prn"] == PRN

    def test_update_fails_on_api_error(self, mock_am, mock_gs, mock_lv):
        params = _base_params(ca_certificate_group="corporate-cas")
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        blade.get_sso_oidc_idps.return_value = _response(
            200, [_existing(ca_certificate=_ref("sso-root-ca"))]
        )
        # the array refuses a certificate and a group on the same provider
        blade.patch_sso_oidc_idps.return_value = _response(400)

        _run()

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to update OIDC identity provider okta" in msg

    # ---------------- delete ----------------

    def test_delete_idp(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(state="absent")
        )
        blade.get_sso_oidc_idps.return_value = _response(200, [_existing()])
        blade.delete_sso_oidc_idps.return_value = _response(200)

        _run()

        blade.delete_sso_oidc_idps.assert_called_once_with(names=["okta"])
        module.exit_json.assert_called_once_with(changed=True)

    def test_delete_missing_is_noop(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(state="absent")
        )
        blade.get_sso_oidc_idps.return_value = _response(400)

        _run()

        blade.delete_sso_oidc_idps.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_delete_check_mode_skips_call(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(state="absent"), check_mode=True
        )
        blade.get_sso_oidc_idps.return_value = _response(200, [_existing()])

        _run()

        blade.delete_sso_oidc_idps.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_delete_referenced_by_trust_policy_surfaces_400(
        self, mock_am, mock_gs, mock_lv
    ):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(state="absent")
        )
        blade.get_sso_oidc_idps.return_value = _response(200, [_existing()])
        blade.delete_sso_oidc_idps.return_value = _response(400)

        _run()

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to delete OIDC identity provider okta" in msg
        # the hint is phrased as a possibility; the array message precedes it
        assert "If an object store trust policy still references" in msg

    # ---------------- realm-qualified names ----------------

    @staticmethod
    def _assert_realm_refusal(module, blade, mock_gs, option, value):
        """The task failed on the realm-qualified name without contacting the array."""
        mock_gs.assert_not_called()
        blade.get_sso_oidc_idps.assert_not_called()
        blade.post_sso_oidc_idps.assert_not_called()
        blade.patch_sso_oidc_idps.assert_not_called()
        blade.delete_sso_oidc_idps.assert_not_called()
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Invalid {0} '{1}'".format(option, value) in msg
        assert "array-wide" in msg
        assert "Use the unqualified provider name" in msg
        assert "purefb_resource_access" in msg
        assert "resource_type sso/oidc/idps, scope_type realms" in msg

    def test_realm_name_refused_on_create(self, mock_am, mock_gs, mock_lv):
        params = _base_params(name="realm1::okta")
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        blade.get_sso_oidc_idps.side_effect = _array_lookup()
        # the array rejects the create with its name rule, which allows only
        # alphanumerics, underscores and hyphens
        blade.post_sso_oidc_idps.return_value = _response(400)

        _run()

        self._assert_realm_refusal(module, blade, mock_gs, "name", "realm1::okta")

    def test_realm_name_refused_on_create_in_check_mode(
        self, mock_am, mock_gs, mock_lv
    ):
        """Check mode must not predict a create the array always refuses."""
        params = _base_params(name="realm1::okta")
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params, check_mode=True)
        blade.get_sso_oidc_idps.side_effect = _array_lookup()

        _run()

        self._assert_realm_refusal(module, blade, mock_gs, "name", "realm1::okta")

    def test_realm_name_refused_for_absent(self, mock_am, mock_gs, mock_lv):
        """Deleting realm1::okta must not pass as unchanged while okta stays."""
        params = _base_params(name="realm1::okta", state="absent")
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        blade.get_sso_oidc_idps.side_effect = _array_lookup(_existing())

        _run()

        self._assert_realm_refusal(module, blade, mock_gs, "name", "realm1::okta")

    def test_realm_name_refused_for_absent_in_check_mode(
        self, mock_am, mock_gs, mock_lv
    ):
        params = _base_params(name="realm1::okta", state="absent")
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params, check_mode=True)
        blade.get_sso_oidc_idps.side_effect = _array_lookup(_existing())

        _run()

        self._assert_realm_refusal(module, blade, mock_gs, "name", "realm1::okta")

    def test_realm_name_refused_on_update(self, mock_am, mock_gs, mock_lv):
        """An update through realm1::okta is not reported as a create without a URL."""
        params = _base_params(name="realm1::okta", provider_url=None, enabled=False)
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        blade.get_sso_oidc_idps.side_effect = _array_lookup(_existing())

        _run()

        self._assert_realm_refusal(module, blade, mock_gs, "name", "realm1::okta")
        msg = module.fail_json.call_args[1]["msg"]
        assert "provider_url is required" not in msg

    def test_realm_rename_refused(self, mock_am, mock_gs, mock_lv):
        params = _base_params(rename="realm1::okta-prod")
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        blade.get_sso_oidc_idps.side_effect = _array_lookup(_existing())
        # the array rejects the new name with its name rule
        blade.patch_sso_oidc_idps.return_value = _response(400)

        _run()

        self._assert_realm_refusal(
            module, blade, mock_gs, "rename", "realm1::okta-prod"
        )

    def test_realm_rename_refused_in_check_mode(self, mock_am, mock_gs, mock_lv):
        """Check mode must not predict a rename the array always refuses."""
        params = _base_params(rename="realm1::okta-prod")
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params, check_mode=True)
        blade.get_sso_oidc_idps.side_effect = _array_lookup(_existing())

        _run()

        self._assert_realm_refusal(
            module, blade, mock_gs, "rename", "realm1::okta-prod"
        )

    def test_prn_given_as_name_is_refused(self, mock_am, mock_gs, mock_lv):
        """A PRN embeds the separator as well; the answer is the unqualified name."""
        params = _base_params(name=PRN, state="absent")
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        blade.get_sso_oidc_idps.side_effect = _array_lookup(_existing())

        _run()

        self._assert_realm_refusal(module, blade, mock_gs, "name", PRN)

    def test_realm_rename_is_not_read_for_absent(self, mock_am, mock_gs, mock_lv):
        """rename is unused by state=absent, so the delete goes ahead as before."""
        params = _base_params(state="absent", rename="realm1::okta-prod")
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        blade.get_sso_oidc_idps.side_effect = _array_lookup(_existing())
        blade.delete_sso_oidc_idps.return_value = _response(200)

        _run()

        module.fail_json.assert_not_called()
        blade.delete_sso_oidc_idps.assert_called_once_with(names=["okta"])
        module.exit_json.assert_called_once_with(changed=True)

    def test_single_colon_name_is_left_to_the_array(self, mock_am, mock_gs, mock_lv):
        """Only the realm separator is refused here; other names go to the array."""
        params = _base_params(name="ok:ta")
        module, blade = self._setup(mock_am, mock_gs, mock_lv, params)
        blade.get_sso_oidc_idps.side_effect = _array_lookup()
        blade.post_sso_oidc_idps.return_value = _response(400)

        _run()

        blade.post_sso_oidc_idps.assert_called_once()
        assert blade.post_sso_oidc_idps.call_args[1]["names"] == ["ok:ta"]
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to create OIDC identity provider ok:ta" in msg
        assert "array-wide" not in msg

    # ---------------- validation and gates ----------------

    def test_lookup_error_is_reported_not_treated_as_absent(
        self, mock_am, mock_gs, mock_lv
    ):
        module, blade = self._setup(mock_am, mock_gs, mock_lv, _base_params())
        blade.get_sso_oidc_idps.return_value = _response(503)

        _run()

        blade.post_sso_oidc_idps.assert_not_called()
        blade.patch_sso_oidc_idps.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to read OIDC identity provider okta" in msg

    def test_version_gate_blocks_before_any_call(self, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(mock_am, mock_gs, mock_lv, _base_params())
        mock_lv.return_value.__gt__ = Mock(return_value=True)

        _run()

        blade.get_sso_oidc_idps.assert_not_called()
        blade.post_sso_oidc_idps.assert_not_called()
        blade.patch_sso_oidc_idps.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "REST version not supported" in msg
        assert "2.17" in msg

    @patch(MODULE + ".purefb_argument_spec", return_value={})
    def test_argument_spec(self, mock_spec, mock_am, mock_gs, mock_lv):
        module, blade = self._setup(
            mock_am, mock_gs, mock_lv, _base_params(state="absent")
        )
        blade.get_sso_oidc_idps.return_value = _response(400)

        _run()

        kwargs = mock_am.call_args[1]
        assert kwargs["supports_check_mode"] is True
        # both CA references are accepted; the array decides whether they may coexist
        assert "mutually_exclusive" not in kwargs
        spec = mock_am.call_args[0][0]
        # "issuer" is already a shared connection option, so no alias here
        assert "aliases" not in spec["provider_url"]
        assert spec["services"]["default"] == ["object"]
        assert spec["services"]["choices"] == ["object"]
        assert spec["services"]["elements"] == "str"
        assert "default" not in spec["enabled"]
        assert spec["state"]["choices"] == ["absent", "present"]
        assert spec["name"]["required"] is True


@patch(MODULE + ".LooseVersion")
@patch(MODULE + ".get_system")
@patch(MODULE + ".AnsibleModule")
@patch(MODULE + ".HAS_PYPURECLIENT", False)
def test_main_fails_without_sdk(mock_am, mock_gs, mock_lv):
    module = _module(_base_params())
    mock_am.return_value = module

    _run()

    mock_gs.assert_not_called()
    module.fail_json.assert_called_once()
    assert "py-pure-client" in module.fail_json.call_args[1]["msg"]
