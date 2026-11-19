# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_resource_access module."""

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


def _blade(accesses=None, post=None, delete=None):
    blade = Mock()
    blade.get_resource_accesses.return_value = _listing(accesses)
    blade.post_resource_accesses_batch.return_value = post or _valid()
    blade.delete_resource_accesses.return_value = delete or _valid()
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
            " realm1::okta failed. A resource that is shared with a realm is an"
            " array-level object and is named without a realm prefix. Error: "
            + ERR_NO_IDP
        )
        module.exit_json.assert_not_called()

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
        assert hint(_module(_params(resource_name="realm1::okta"))) == (
            " " + resource_access.REALM_PREFIX_HINT
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
