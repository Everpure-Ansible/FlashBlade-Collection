# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_resource_access module."""

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

from plugins.modules import purefb_resource_access as resource_access
from plugins.modules.purefb_resource_access import (
    main,
    get_resource_access,
    delete_resource_access,
)


class TestPurefbResourceAccess:
    """Test cases for purefb_resource_access module"""

    @patch("plugins.modules.purefb_resource_access.get_resource_access")
    @patch("plugins.modules.purefb_resource_access.LooseVersion")
    @patch("plugins.modules.purefb_resource_access.get_system")
    @patch("plugins.modules.purefb_resource_access.AnsibleModule")
    def test_main_create_resource_access(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_resource_access,
    ):
        """Test creating a resource access"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "resource_type": "dns",
            "resource_name": "management",
            "scope_type": "realms",
            "scope_name": "test-realm",
            "state": "present",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.19"]
        mock_get_system.return_value = mock_blade

        # Mock API version check
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        # Resource Access doesn't exist
        mock_get_resource_access.return_value = False, None

        # Mock successful resource access
        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_blade.post_resource_accesses_batch.return_value = mock_post_response

        try:
            main()
        except SystemExit:
            pass

        # Verify post_resource_accesses_batch was called
        mock_blade.post_resource_accesses_batch.assert_called_once()

        kwargs = mock_blade.post_resource_accesses_batch.call_args.kwargs
        assert "items" in kwargs
        assert len(kwargs["items"]) == 1
        # Verify exit_json wa called with changed=True
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is True

    @patch("plugins.modules.purefb_resource_access.get_resource_access")
    @patch("plugins.modules.purefb_resource_access.LooseVersion")
    @patch("plugins.modules.purefb_resource_access.get_system")
    @patch("plugins.modules.purefb_resource_access.AnsibleModule")
    def test_main_delete_resource_access(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_loose_version,
        mock_get_resource_access,
    ):
        """Test deleting a resource access"""
        # Setup mock module
        mock_module = Mock()
        mock_module.exit_json = Mock(side_effect=SystemExit)
        mock_module.fail_json = Mock(side_effect=SystemExit)
        mock_module.params = {
            "resource_type": "dns",
            "resource_name": "management",
            "scope_type": "realms",
            "scope_name": "test-realm",
            "state": "absent",
        }
        mock_module.check_mode = False
        mock_ansible_module.return_value = mock_module

        # Mock blade
        mock_blade = Mock()
        mock_blade.get_versions.return_value.items = ["2.19"]
        mock_get_system.return_value = mock_blade

        # Mock API version check
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)

        # Resource Access exist
        mock_get_resource_access.return_value = True, "1234"

        # Mock successful resource access deletion
        mock_delete_response = Mock()
        mock_delete_response.status_code = 200
        mock_blade.delete_resource_accesses.return_value = mock_delete_response

        # Call main
        try:
            main()
        except SystemExit:
            pass

        # Verify delete_resource_accesses was called
        mock_blade.delete_resource_accesses.assert_called_once()

        # Verify exit_json wa called with changed=True
        mock_module.exit_json.assert_called_once()
        call_args = mock_module.exit_json.call_args[1]
        assert call_args["changed"] is True

    def test_get_resource_access(self):
        """Test get_resource_access function"""
        # Setup mock module
        mock_module = Mock()
        mock_module.params = {
            "resource_type": "dns",
            "resource_name": "management",
            "scope_type": "realms",
            "scope_name": "test-realm",
        }

        # Setup mock blade
        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.items = [mock_module]

        mock_blade.get_resource_accesses.return_value = mock_response

        get_resource_access(mock_module, mock_blade)
        # Filter search

        filter_string = (
            "resource.resource_type='"
            + "dns"
            + "' and scope.name='"
            + "test-realm"
            + "' and scope.resource_type='"
            + "realms"
            + "'"
        )

        mock_blade.get_resource_accesses.assert_called_once_with(filter=filter_string)

    def test_delete_resource_access(self):
        """Test delete_resource_access function"""
        # Setup mock module
        mock_module = Mock()
        mock_module.params = {
            "resource_type": "dns",
            "resource_name": "management",
            "scope_type": "realms",
            "scope_name": "test-realm",
        }
        mock_module.check_mode = False

        # Setup mock blade
        mock_blade = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_blade.delete_resource_accesses.return_value = mock_response

        # Call delete_resource_access
        delete_resource_access(mock_module, mock_blade, access_id="1234")

        # Verify delete_resource_accesses was called with correct ID
        mock_blade.delete_resource_accesses.assert_called_once_with(ids=["1234"])


MODULE = "plugins.modules.purefb_resource_access"
OIDC = "sso/oidc/idps"
SAML = "sso/saml2/idps"
ACCESS_ID = "10314f42-020d-7080-8013-000000000001"
ACCESS_ID_2 = "10314f42-020d-7080-8013-000000000002"
IDP_ID = "10314f42-020d-7080-8013-0000000000a1"
REALM_ID = "10314f42-020d-7080-8013-0000000000b1"

# What a Purity//FB 4.8 array answers
ERR_NO_IDP = "Sso OIDC IdP configuration does not exist."
ERR_IN_USE = (
    "Resource access cannot be deleted while " + IDP_ID + " 'SsoOidc' is in use"
    " by trust policies."
)
ERR_BAD_TYPE = "Invalid resource type: telemetry-targets"


def _params(**overrides):
    params = {
        "resource_type": OIDC,
        "resource_name": "okta",
        "scope_type": "realms",
        "scope_name": "realm1",
        "state": "present",
    }
    params.update(overrides)
    return params


def _module(params, check_mode=False):
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.params = params
    module.check_mode = check_mode
    return module


def _reference(name, resource_type, ref_id):
    ref = Mock(spec=["id", "name", "resource_type"])
    ref.id = ref_id
    ref.name = name
    ref.resource_type = resource_type
    return ref


def _access(access_id, resource_name, resource_type=OIDC, scope_name="realm1"):
    """A resource access as the array returns it: an id and two references"""
    access = Mock(spec=["id", "resource", "scope"])
    access.id = access_id
    access.resource = _reference(resource_name, resource_type, IDP_ID)
    access.scope = _reference(scope_name, "realms", REALM_ID)
    return access


def _listing(items=None):
    """A valid GET response; the filter leaves one resource type and one scope"""
    items = items or []
    res = Mock(spec=["status_code", "items", "total_item_count"])
    res.status_code = 200
    res.items = items
    res.total_item_count = len(items)
    return res


def _valid():
    res = Mock(spec=["status_code", "items"])
    res.status_code = 200
    res.items = []
    return res


def _error(message, status_code=400):
    """An error response carrying the message of the array"""
    err = Mock(spec=["context", "message"])
    err.context = None
    err.message = message
    res = Mock(spec=["status_code", "errors"])
    res.status_code = status_code
    res.errors = [err]
    return res


def _error_message(response, default="Unknown error"):
    """What module_utils.common.get_error_message does (it is mocked here)"""
    if hasattr(response, "errors") and response.errors:
        errors = list(response.errors)
        if errors:
            return errors[0].message
    return default


def _version(value):
    return tuple(int(part) for part in value.split("."))


# The read that finds a realm or a shareable resource by name, and what a
# Purity//FB 4.8 array answers to it for a name it does not hold
NAME_READS = {
    "realms": ("get_realms", "Realm does not exist."),
    "subnets": ("get_subnets", "Subnet does not exist."),
    "dns": ("get_dns", "DNS does not exist."),
    "targets": ("get_targets", "Target does not exist."),
    OIDC: ("get_sso_oidc_idps", ERR_NO_IDP),
    SAML: ("get_sso_saml2_idps", "SsoSaml2 configuration does not exist."),
}


def _named(name, destroyed=None):
    """An object as a read by name returns it; a realm says if it is destroyed"""
    if destroyed is None:
        item = Mock(spec=["id", "name"])
    else:
        item = Mock(spec=["id", "name", "destroyed"])
        item.destroyed = destroyed
    item.id = IDP_ID
    item.name = name
    return item


def _name_read(held, missing, exact=False):
    """A read by name as the array serves it

    A name is found whatever its case, a SAML2 identity provider only in its
    own case, and a name the array does not hold is an error response, not
    an empty list.
    """

    def read(names=None):
        for item in held:
            if item.name == names[0]:
                return _listing([item])
            if not exact and item.name.lower() == names[0].lower():
                return _listing([item])
        return _error(missing)

    return Mock(side_effect=read)


def _blade(accesses=None, post=None, delete=None, held=None):
    """An array that holds realm1 and the OIDC provider okta, or what held says"""
    blade = Mock()
    blade.get_resource_accesses.return_value = _listing(accesses)
    blade.post_resource_accesses_batch.return_value = post or _valid()
    blade.delete_resource_accesses.return_value = delete or _valid()
    if held is None:
        held = {"realms": ["realm1"], OIDC: ["okta"]}
    for resource_type, (method, missing) in NAME_READS.items():
        items = [
            _named(name, destroyed=False if resource_type == "realms" else None)
            for name in held.get(resource_type, [])
        ]
        setattr(blade, method, _name_read(items, missing, resource_type == SAML))
    return blade


def _run(params, blade, check_mode=False, api_version="2.30"):
    """Run main() with the SDK model and the module_utils helpers stood in"""
    module = _module(params, check_mode)
    with patch(MODULE + ".AnsibleModule", return_value=module), patch(
        MODULE + ".get_system", return_value=blade
    ), patch(MODULE + ".get_rest_api_version", return_value=api_version), patch(
        MODULE + ".LooseVersion", side_effect=_version
    ), patch(
        MODULE + ".get_error_message", side_effect=_error_message
    ), patch(
        MODULE + ".ResourceAccessPost", side_effect=lambda **kwargs: kwargs
    ):
        try:
            main()
        except SystemExit:
            pass
    return module


def _filter(resource_type, scope_name):
    return (
        "resource.resource_type='{0}' and scope.name='{1}'"
        " and scope.resource_type='realms'".format(resource_type, scope_name)
    )


class TestResourceAccessFailureMessages:
    """Every failure names the resource type, the resource and the scope"""

    def test_create_failure_names_both_ends(self):
        blade = _blade(post=_error(ERR_BAD_TYPE))
        module = _run(
            _params(resource_type="telemetry-targets", resource_name="tt1"), blade
        )

        blade.post_resource_accesses_batch.assert_called_once()
        module.fail_json.assert_called_once_with(
            msg="Create resource access between realms realm1 and"
            " telemetry-targets tt1 failed. Error: " + ERR_BAD_TYPE
        )
        module.exit_json.assert_not_called()

    def test_create_failure_realm_qualified_name_gets_hint(self):
        # the provider is shared under its array-level name; the array does not
        # find it under the realm-qualified one
        blade = _blade(accesses=[_access(ACCESS_ID, "okta")], post=_error(ERR_NO_IDP))
        module = _run(_params(resource_name="realm1::okta"), blade)

        blade.post_resource_accesses_batch.assert_called_once()
        module.fail_json.assert_called_once_with(
            msg="Create resource access between realms realm1 and sso/oidc/idps"
            " realm1::okta failed. Error: " + ERR_NO_IDP + " An array-level"
            " resource is shared under its own name, without a realm prefix."
        )
        module.exit_json.assert_not_called()

    def test_hint_follows_an_error_without_a_full_stop(self):
        blade = _blade(post=_error(ERR_BAD_TYPE))
        module = _run(
            _params(resource_type="telemetry-targets", resource_name="realm1::tt1"),
            blade,
        )

        module.fail_json.assert_called_once_with(
            msg="Create resource access between realms realm1 and"
            " telemetry-targets realm1::tt1 failed. Error: " + ERR_BAD_TYPE + "."
            " An array-level resource is shared under its own name, without a"
            " realm prefix."
        )

    def test_delete_failure_names_both_ends(self):
        blade = _blade(accesses=[_access(ACCESS_ID, "okta")], delete=_error(ERR_IN_USE))
        module = _run(_params(state="absent"), blade)

        blade.delete_resource_accesses.assert_called_once_with(ids=[ACCESS_ID])
        module.fail_json.assert_called_once_with(
            msg="Delete resource access between realms realm1 and sso/oidc/idps"
            " okta failed. Error: " + ERR_IN_USE
        )
        module.exit_json.assert_not_called()

    def test_access_text(self):
        module = _module(_params(resource_name="realm1::okta"))
        assert (
            resource_access._access_text(module)
            == "realms realm1 and sso/oidc/idps realm1::okta"
        )

    def test_hint_only_for_a_realm_prefix_in_a_realm_scope(self):
        hint = resource_access._realm_prefix_hint
        assert (
            hint(_module(_params(resource_name="realm1::okta")))
            == resource_access.REALM_PREFIX_HINT
        )
        assert hint(_module(_params())) == ""
        # the scope types are defined by the array; any other one gets no hint
        other = _params(resource_name="realm1::okta", scope_type="other-scope")
        assert hint(_module(other)) == ""


class TestResourceAccessOidcShare:
    """An OIDC identity provider shared with a realm"""

    def test_share_creates_the_access(self):
        blade = _blade()
        module = _run(_params(), blade)

        blade.get_resource_accesses.assert_called_once_with(
            filter=_filter(OIDC, "realm1")
        )
        blade.post_resource_accesses_batch.assert_called_once_with(
            items=[
                {
                    "resource": {"name": "okta", "resource_type": OIDC},
                    "scope": {"name": "realm1", "resource_type": "realms"},
                }
            ]
        )
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()

    def test_share_again_is_unchanged(self):
        blade = _blade(accesses=[_access(ACCESS_ID, "okta")])
        module = _run(_params(), blade)

        blade.post_resource_accesses_batch.assert_not_called()
        blade.delete_resource_accesses.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_share_check_mode_sends_nothing(self):
        blade = _blade()
        module = _run(_params(), blade, check_mode=True)

        blade.post_resource_accesses_batch.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_revoke_deletes_by_id(self):
        blade = _blade(accesses=[_access(ACCESS_ID, "okta")])
        module = _run(_params(state="absent"), blade)

        blade.delete_resource_accesses.assert_called_once_with(ids=[ACCESS_ID])
        blade.post_resource_accesses_batch.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()

    def test_revoke_again_is_unchanged(self):
        blade = _blade()
        module = _run(_params(state="absent"), blade)

        blade.delete_resource_accesses.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_revoke_check_mode_sends_nothing(self):
        blade = _blade(accesses=[_access(ACCESS_ID, "okta")])
        module = _run(_params(state="absent"), blade, check_mode=True)

        blade.delete_resource_accesses.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_lookup_matches_the_exact_resource_name(self):
        blade = _blade(
            accesses=[_access(ACCESS_ID, "okta"), _access(ACCESS_ID_2, "okta-prod")]
        )

        found = get_resource_access(_module(_params(resource_name="okta-prod")), blade)
        assert found == (True, ACCESS_ID_2)
        # the access is listed under the array-level name of the provider
        missing = get_resource_access(
            _module(_params(resource_name="realm1::okta")), blade
        )
        assert missing == (False, False)

    def test_revoke_realm_qualified_name_is_unchanged(self):
        blade = _blade(accesses=[_access(ACCESS_ID, "okta")])
        module = _run(_params(resource_name="realm1::okta", state="absent"), blade)

        blade.delete_resource_accesses.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)


class TestResourceAccessNameCase:
    """An existing resource access is found whatever the case of the name

    Purity//FB 4.8 refuses to create OKTA beside okta ("... with the given
    name already exists."), answers a GET of OKTA with the provider okta and
    lists a resource access under the name the resource was created with.
    """

    def test_share_under_another_case_is_unchanged(self):
        blade = _blade(accesses=[_access(ACCESS_ID, "okta")])
        module = _run(_params(resource_name="OKTA"), blade)

        blade.post_resource_accesses_batch.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)
        module.fail_json.assert_not_called()

    def test_share_under_another_case_check_mode_is_unchanged(self):
        blade = _blade(accesses=[_access(ACCESS_ID, "Okta")])
        module = _run(_params(resource_name="okta"), blade, check_mode=True)

        blade.post_resource_accesses_batch.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_revoke_under_another_case_deletes_the_access(self):
        blade = _blade(
            accesses=[_access(ACCESS_ID, "Partner-2065", resource_type="subnets")]
        )
        module = _run(
            _params(
                resource_type="subnets", resource_name="partner-2065", state="absent"
            ),
            blade,
        )

        blade.delete_resource_accesses.assert_called_once_with(ids=[ACCESS_ID])
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()

    def test_revoke_under_another_case_check_mode_predicts_the_change(self):
        blade = _blade(accesses=[_access(ACCESS_ID, "okta")])
        module = _run(
            _params(resource_name="OKTA", state="absent"), blade, check_mode=True
        )

        blade.delete_resource_accesses.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_the_exact_spelling_wins(self):
        blade = _blade(
            accesses=[_access(ACCESS_ID, "OKTA"), _access(ACCESS_ID_2, "okta")]
        )

        found = get_resource_access(_module(_params(resource_name="okta")), blade)
        assert found == (True, ACCESS_ID_2)
        found = get_resource_access(_module(_params(resource_name="Okta")), blade)
        assert found == (True, ACCESS_ID)

    def test_another_name_is_still_another_resource(self):
        blade = _blade(accesses=[_access(ACCESS_ID, "okta-prod")])

        missing = get_resource_access(_module(_params(resource_name="OKTA")), blade)
        assert missing == (False, False)


class TestResourceAccessArrayLevelRegression:
    """Subnets and DNS configurations are shared as before"""

    def test_dns_share_request(self):
        blade = _blade()
        module = _run(_params(resource_type="dns", resource_name="management"), blade)

        blade.get_resource_accesses.assert_called_once_with(
            filter=_filter("dns", "realm1")
        )
        blade.post_resource_accesses_batch.assert_called_once_with(
            items=[
                {
                    "resource": {"name": "management", "resource_type": "dns"},
                    "scope": {"name": "realm1", "resource_type": "realms"},
                }
            ]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_subnet_revoke_request(self):
        blade = _blade(
            accesses=[_access(ACCESS_ID, "subnet_foo", resource_type="subnets")]
        )
        module = _run(
            _params(
                resource_type="subnets", resource_name="subnet_foo", state="absent"
            ),
            blade,
        )

        blade.get_resource_accesses.assert_called_once_with(
            filter=_filter("subnets", "realm1")
        )
        blade.delete_resource_accesses.assert_called_once_with(ids=[ACCESS_ID])
        module.exit_json.assert_called_once_with(changed=True)

    def test_access_of_another_resource_is_left_alone(self):
        blade = _blade(
            accesses=[_access(ACCESS_ID, "subnet_bar", resource_type="subnets")]
        )
        module = _run(
            _params(
                resource_type="subnets", resource_name="subnet_foo", state="absent"
            ),
            blade,
        )

        blade.delete_resource_accesses.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_rest_version_gate(self):
        blade = _blade()
        module = _run(_params(), blade, api_version="2.18")

        module.fail_json.assert_called_once_with(
            msg="Resource Access is not supported. Purity//FB 4.6.1, or higher,"
            " is required."
        )
        blade.get_resource_accesses.assert_not_called()
        blade.post_resource_accesses_batch.assert_not_called()

    def test_first_supported_rest_version(self):
        blade = _blade()
        module = _run(_params(), blade, api_version="2.19")

        module.fail_json.assert_not_called()
        blade.post_resource_accesses_batch.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)


# What the array answers when it does not serve the read of the resource accesses
ERR_NOT_PERMITTED = "Operation not permitted."
ERR_RESTARTING = (
    "Services are restarting and most operations are not available. This may"
    " take some time. Try again later."
)
GET_FAILED = "Get resource access between realms realm1 and sso/oidc/idps okta failed."


def _blade_refusing_the_read(lookup, post=None):
    """The GET answers an error response, which has no items and no count"""
    blade = _blade(post=post)
    blade.get_resource_accesses.return_value = lookup
    return blade


class TestResourceAccessFailedRead:
    """A read the array refuses does not mean that nothing is shared

    Purity//FB 4.8 answers 400 "Operation not permitted." to an administrator
    whose management access is limited to a realm.
    """

    def test_revoke_fails_instead_of_reporting_no_change(self):
        blade = _blade_refusing_the_read(_error(ERR_NOT_PERMITTED))
        module = _run(_params(state="absent"), blade)

        module.fail_json.assert_called_once_with(
            msg=GET_FAILED + " Error: " + ERR_NOT_PERMITTED
        )
        module.exit_json.assert_not_called()
        blade.delete_resource_accesses.assert_not_called()
        blade.post_resource_accesses_batch.assert_not_called()

    def test_revoke_check_mode_fails_too(self):
        blade = _blade_refusing_the_read(_error(ERR_NOT_PERMITTED))
        module = _run(_params(state="absent"), blade, check_mode=True)

        module.fail_json.assert_called_once_with(
            msg=GET_FAILED + " Error: " + ERR_NOT_PERMITTED
        )
        module.exit_json.assert_not_called()
        blade.delete_resource_accesses.assert_not_called()

    def test_revoke_fails_while_the_services_restart(self):
        blade = _blade_refusing_the_read(_error(ERR_RESTARTING, status_code=503))
        module = _run(_params(state="absent"), blade)

        module.fail_json.assert_called_once_with(
            msg=GET_FAILED + " Error: " + ERR_RESTARTING
        )
        module.exit_json.assert_not_called()
        blade.delete_resource_accesses.assert_not_called()

    def test_share_check_mode_fails_instead_of_predicting_a_change(self):
        blade = _blade_refusing_the_read(_error(ERR_NOT_PERMITTED))
        module = _run(_params(), blade, check_mode=True)

        module.fail_json.assert_called_once_with(
            msg=GET_FAILED + " Error: " + ERR_NOT_PERMITTED
        )
        module.exit_json.assert_not_called()
        blade.post_resource_accesses_batch.assert_not_called()

    def test_share_is_still_sent_and_the_array_decides(self):
        blade = _blade_refusing_the_read(
            _error(ERR_NOT_PERMITTED), post=_error(ERR_NOT_PERMITTED)
        )
        module = _run(_params(), blade)

        blade.post_resource_accesses_batch.assert_called_once_with(
            items=[
                {
                    "resource": {"name": "okta", "resource_type": OIDC},
                    "scope": {"name": "realm1", "resource_type": "realms"},
                }
            ]
        )
        module.fail_json.assert_called_once_with(
            msg="Create resource access between realms realm1 and sso/oidc/idps"
            " okta failed. Error: " + ERR_NOT_PERMITTED
        )
        module.exit_json.assert_not_called()

    def test_share_the_array_accepts_is_reported_as_changed(self):
        blade = _blade_refusing_the_read(_error(ERR_RESTARTING, status_code=503))
        module = _run(_params(), blade)

        blade.post_resource_accesses_batch.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()

    def test_read_that_matches_nothing_is_not_a_failure(self):
        # a filter that matches nothing answers 200 with an empty list
        blade = _blade()
        module = _run(_params(state="absent"), blade, check_mode=True)

        module.fail_json.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)


WOULD_FAIL = "Create resource access between {0} would fail. {1}"
NOT_VERIFIED = (
    "Check mode did not verify the resource access between {0}: {1} The array"
    " decides when the request is sent."
)
# One resource of each type the array shares with a realm
SHAREABLE = [
    ("subnets", "Partner-2065"),
    ("dns", "dns1"),
    ("targets", "target1"),
    (OIDC, "okta"),
    (SAML, "PureSSO"),
]


def _check(params, held, **reads):
    """Run a share in check mode on an array that holds what held says

    A keyword names a read and the response it gives instead.
    """
    blade = _blade(held=held)
    for method, response in reads.items():
        setattr(blade, method, Mock(return_value=response))
    return blade, _run(params, blade, check_mode=True)


def _nothing_sent(blade):
    blade.post_resource_accesses_batch.assert_not_called()
    blade.delete_resource_accesses.assert_not_called()


class TestResourceAccessCheckModeRefusals:
    """Check mode fails for a share the array would refuse

    Purity//FB 4.8 answers a create that names a realm or a resource it does
    not hold with the error it gives to a read of that name, and it finds
    both only under the names as it holds them.
    """

    @pytest.mark.parametrize("resource_type, resource_name", SHAREABLE)
    def test_resource_the_array_does_not_hold(self, resource_type, resource_name):
        params = _params(resource_type=resource_type, resource_name=resource_name)
        blade, module = _check(params, {"realms": ["realm1"]})

        method, missing = NAME_READS[resource_type]
        getattr(blade, method).assert_called_once_with(names=[resource_name])
        module.fail_json.assert_called_once_with(
            msg=WOULD_FAIL.format(
                "realms realm1 and {0} {1}".format(resource_type, resource_name),
                "Error: " + missing,
            )
        )
        module.exit_json.assert_not_called()
        _nothing_sent(blade)

    def test_realm_the_array_does_not_hold(self):
        params = _params(resource_type="dns", resource_name="dns1", scope_name="r2")
        blade, module = _check(params, {"realms": ["realm1"], "dns": ["dns1"]})

        blade.get_realms.assert_called_once_with(names=["r2"])
        module.fail_json.assert_called_once_with(
            msg=WOULD_FAIL.format(
                "realms r2 and dns dns1", "Error: Realm does not exist."
            )
        )
        module.exit_json.assert_not_called()
        _nothing_sent(blade)

    def test_realm_qualified_resource_name_gets_the_hint(self):
        params = _params(resource_name="realm1::okta")
        blade, module = _check(params, {"realms": ["realm1"], OIDC: ["okta"]})

        module.fail_json.assert_called_once_with(
            msg=WOULD_FAIL.format(
                "realms realm1 and sso/oidc/idps realm1::okta",
                "Error: " + ERR_NO_IDP + " " + resource_access.REALM_PREFIX_HINT,
            )
        )
        module.exit_json.assert_not_called()
        _nothing_sent(blade)

    def test_realm_named_in_another_case(self):
        params = _params(scope_name="REALM1")
        blade, module = _check(params, {"realms": ["realm1"], OIDC: ["okta"]})

        module.fail_json.assert_called_once_with(
            msg=WOULD_FAIL.format(
                "realms REALM1 and sso/oidc/idps okta",
                "The array holds realms REALM1 as realm1 and creates a resource"
                " access only under the name as it holds it.",
            )
        )
        module.exit_json.assert_not_called()
        _nothing_sent(blade)

    @pytest.mark.parametrize(
        "resource_type, held_name",
        [("dns", "dns1"), ("targets", "target1"), (OIDC, "okta")],
    )
    def test_resource_named_in_another_case(self, resource_type, held_name):
        given = held_name.upper()
        params = _params(resource_type=resource_type, resource_name=given)
        blade, module = _check(
            params, {"realms": ["realm1"], resource_type: [held_name]}
        )

        module.fail_json.assert_called_once_with(
            msg=WOULD_FAIL.format(
                "realms realm1 and {0} {1}".format(resource_type, given),
                "The array holds {0} {1} as {2} and creates a resource access"
                " only under the name as it holds it.".format(
                    resource_type, given, held_name
                ),
            )
        )
        module.exit_json.assert_not_called()
        _nothing_sent(blade)

    def test_saml_provider_is_read_in_its_own_case(self):
        params = _params(resource_type=SAML, resource_name="puresso")
        blade, module = _check(params, {"realms": ["realm1"], SAML: ["PureSSO"]})

        module.fail_json.assert_called_once_with(
            msg=WOULD_FAIL.format(
                "realms realm1 and sso/saml2/idps puresso",
                "Error: SsoSaml2 configuration does not exist.",
            )
        )
        module.exit_json.assert_not_called()

    def test_missing_realm_fails_for_any_resource_type(self):
        params = _params(
            resource_type="telemetry-targets", resource_name="tt1", scope_name="r2"
        )
        blade, module = _check(params, {"realms": ["realm1"]})

        module.fail_json.assert_called_once_with(
            msg=WOULD_FAIL.format(
                "realms r2 and telemetry-targets tt1", "Error: Realm does not exist."
            )
        )
        module.warn.assert_not_called()
        module.exit_json.assert_not_called()


class TestResourceAccessCheckModePredictions:
    """Check mode predicts the share when the array holds both ends

    What the reads do not settle is left to the array and reported with a
    warning; it never fails a share the array might accept.
    """

    @pytest.mark.parametrize("resource_type, resource_name", SHAREABLE)
    def test_realm_and_resource_are_held(self, resource_type, resource_name):
        params = _params(resource_type=resource_type, resource_name=resource_name)
        blade, module = _check(
            params, {"realms": ["realm1"], resource_type: [resource_name]}
        )

        blade.get_realms.assert_called_once_with(names=["realm1"])
        getattr(blade, NAME_READS[resource_type][0]).assert_called_once_with(
            names=[resource_name]
        )
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()
        module.warn.assert_not_called()
        _nothing_sent(blade)

    def test_subnet_named_in_another_case_is_a_warning(self):
        # not measured on an array: no failure is predicted for it
        params = _params(resource_type="subnets", resource_name="partner-2065")
        blade, module = _check(
            params, {"realms": ["realm1"], "subnets": ["Partner-2065"]}
        )

        module.warn.assert_called_once_with(
            NOT_VERIFIED.format(
                "realms realm1 and subnets partner-2065",
                "the array holds subnets partner-2065 as Partner-2065 and may"
                " not find it under another case.",
            )
        )
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()
        _nothing_sent(blade)

    def test_resource_type_the_module_does_not_know(self):
        params = _params(resource_type="telemetry-targets", resource_name="tt1")
        blade, module = _check(params, {"realms": ["realm1"]})

        blade.get_realms.assert_called_once_with(names=["realm1"])
        module.warn.assert_called_once_with(
            NOT_VERIFIED.format(
                "realms realm1 and telemetry-targets tt1",
                "the module can only check a resource of type dns,"
                " sso/oidc/idps, sso/saml2/idps, subnets, targets.",
            )
        )
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()
        _nothing_sent(blade)

    def test_scope_type_the_module_does_not_know(self):
        params = _params(scope_type="other-scope")
        blade, module = _check(params, {})

        blade.get_realms.assert_not_called()
        blade.get_sso_oidc_idps.assert_not_called()
        module.warn.assert_called_once_with(
            NOT_VERIFIED.format(
                "other-scope realm1 and sso/oidc/idps okta",
                "the module can only check a scope of type realms.",
            )
        )
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()

    def test_destroyed_realm(self):
        blade = _blade()
        blade.get_realms = Mock(
            return_value=_listing([_named("realm1", destroyed=True)])
        )
        module = _run(_params(), blade, check_mode=True)

        module.warn.assert_called_once_with(
            NOT_VERIFIED.format(
                "realms realm1 and sso/oidc/idps okta", "realm realm1 is destroyed."
            )
        )
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()
        _nothing_sent(blade)

    def test_resource_that_belongs_to_a_realm(self):
        params = _params(resource_type="dns", resource_name="realm1::dns1")
        blade, module = _check(params, {"realms": ["realm1"], "dns": ["realm1::dns1"]})

        module.warn.assert_called_once_with(
            NOT_VERIFIED.format(
                "realms realm1 and dns realm1::dns1",
                "dns realm1::dns1 belongs to a realm, and the array is only"
                " known to share array-level resources.",
            )
        )
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()

    def test_realm_read_the_array_refuses(self):
        blade, module = _check(
            _params(),
            {"realms": ["realm1"], OIDC: ["okta"]},
            get_realms=_error(ERR_NOT_PERMITTED),
        )

        # the resource is still looked up
        blade.get_sso_oidc_idps.assert_called_once_with(names=["okta"])
        module.warn.assert_called_once_with(
            NOT_VERIFIED.format(
                "realms realm1 and sso/oidc/idps okta",
                "the read of realms realm1 failed. Error: " + ERR_NOT_PERMITTED,
            )
        )
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()
        _nothing_sent(blade)

    def test_resource_read_the_array_refuses(self):
        blade, module = _check(
            _params(),
            {"realms": ["realm1"], OIDC: ["okta"]},
            get_sso_oidc_idps=_error(ERR_RESTARTING, status_code=503),
        )

        module.warn.assert_called_once_with(
            NOT_VERIFIED.format(
                "realms realm1 and sso/oidc/idps okta",
                "the read of sso/oidc/idps okta failed. Error: " + ERR_RESTARTING,
            )
        )
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()

    def test_read_that_returns_nothing(self):
        blade, module = _check(
            _params(resource_type="dns", resource_name="dns1"),
            {"realms": ["realm1"]},
            get_dns=_listing([]),
        )

        module.warn.assert_called_once_with(
            NOT_VERIFIED.format(
                "realms realm1 and dns dns1", "the array returned no dns dns1."
            )
        )
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()

    def test_realm_name_that_is_read_as_several_names(self):
        # a name with a comma in it is read as a list of names, and the array
        # answers with the realms of that list: none is the realm asked for
        params = _params(
            resource_type="dns", resource_name="dns1", scope_name="realm1,realm2"
        )
        blade, module = _check(
            params,
            {"dns": ["dns1"]},
            get_realms=_listing(
                [_named("realm1", destroyed=False), _named("realm2", destroyed=False)]
            ),
        )

        blade.get_realms.assert_called_once_with(names=["realm1,realm2"])
        module.warn.assert_called_once_with(
            NOT_VERIFIED.format(
                "realms realm1,realm2 and dns dns1",
                "the array returned no realms realm1,realm2.",
            )
        )
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()
        _nothing_sent(blade)

    @pytest.mark.parametrize("resource_type", ["dns", "subnets", "targets"])
    def test_resource_name_that_is_read_as_several_names(self, resource_type):
        params = _params(resource_type=resource_type, resource_name="other,name1")
        answer = _listing([_named("other"), _named("name1")])
        blade, module = _check(
            params, {"realms": ["realm1"]}, **{NAME_READS[resource_type][0]: answer}
        )

        # the first object of the answer is not reported as the one asked for
        module.warn.assert_called_once_with(
            NOT_VERIFIED.format(
                "realms realm1 and {0} other,name1".format(resource_type),
                "the array returned no {0} other,name1.".format(resource_type),
            )
        )
        module.exit_json.assert_called_once_with(changed=True)
        module.fail_json.assert_not_called()
        _nothing_sent(blade)

    def test_error_without_a_full_stop_still_ends_the_sentence(self):
        blade, module = _check(
            _params(),
            {"realms": ["realm1"], OIDC: ["okta"]},
            get_realms=_error("Internal error"),
        )

        module.warn.assert_called_once_with(
            NOT_VERIFIED.format(
                "realms realm1 and sso/oidc/idps okta",
                "the read of realms realm1 failed. Error: Internal error.",
            )
        )


class TestResourceAccessCheckModeReads:
    """The realm and the resource are read only to predict a new share"""

    def test_existing_share_is_unchanged_without_the_reads(self):
        blade = _blade(accesses=[_access(ACCESS_ID, "okta")], held={})
        module = _run(_params(), blade, check_mode=True)

        blade.get_realms.assert_not_called()
        blade.get_sso_oidc_idps.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)
        module.fail_json.assert_not_called()

    def test_revoke_in_check_mode_makes_no_reads(self):
        blade = _blade(accesses=[_access(ACCESS_ID, "okta")], held={})
        module = _run(_params(state="absent"), blade, check_mode=True)

        blade.get_realms.assert_not_called()
        blade.get_sso_oidc_idps.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)
        module.warn.assert_not_called()

    def test_real_share_is_sent_without_the_reads(self):
        # outside check mode the array is asked and its answer is reported
        blade = _blade(held={}, post=_error(ERR_NO_IDP))
        module = _run(_params(), blade)

        blade.get_realms.assert_not_called()
        blade.get_sso_oidc_idps.assert_not_called()
        blade.post_resource_accesses_batch.assert_called_once()
        module.fail_json.assert_called_once_with(
            msg="Create resource access between realms realm1 and sso/oidc/idps"
            " okta failed. Error: " + ERR_NO_IDP
        )
        module.warn.assert_not_called()

    def test_with_realm_prefix_hint(self):
        hint = resource_access._with_realm_prefix_hint
        qualified = _module(_params(resource_name="realm1::okta"))
        assert (
            hint(qualified, "It failed")
            == "It failed. " + resource_access.REALM_PREFIX_HINT
        )
        assert (
            hint(qualified, "It failed.")
            == "It failed. " + resource_access.REALM_PREFIX_HINT
        )
        assert hint(_module(_params()), "It failed") == "It failed"


class TestResourceAccessDocumentation:
    """What the module says about the resources that are shared with a realm"""

    @pytest.mark.parametrize("resource_type", ["subnets", "dns", "targets", OIDC, SAML])
    def test_shareable_resource_type_is_documented(self, resource_type):
        assert "C({0})".format(resource_type) in resource_access.DOCUMENTATION
        assert "resource_type: " + resource_type in resource_access.EXAMPLES
        assert resource_type in resource_access.REALM_SHAREABLE

    def test_no_example_shares_the_management_dns_configuration(self):
        assert "resource_name: management" not in resource_access.EXAMPLES

    def test_a_shared_dns_configuration_can_be_changed_from_the_realm(self):
        text = " ".join(resource_access.DOCUMENTATION.split())
        assert "A shared DNS configuration can also be changed from the realm" in text
        assert "shared with several realms can be changed" in text
