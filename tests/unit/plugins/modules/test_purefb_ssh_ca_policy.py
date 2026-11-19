# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_ssh_ca_policy module."""

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

from plugins.modules.purefb_ssh_ca_policy import (
    main,
    _context_kwargs,
    _desired_member_changes,
    _get_members,
    _get_policy,
    _validate_admins,
    _validate_principals,
)

MODULE = "plugins.modules.purefb_ssh_ca_policy"


class _Version:
    """Minimal dotted-version comparator standing in for LooseVersion."""

    def __init__(self, version):
        self.parts = tuple(int(part) for part in str(version).split("."))

    def __gt__(self, other):
        return self.parts > other.parts

    def __le__(self, other):
        return self.parts <= other.parts


def _model_mock():
    """A model class stand-in that returns its kwargs as a plain dict."""
    return Mock(side_effect=lambda **kwargs: dict(kwargs))


def _base_params(**overrides):
    params = {
        "name": "ssh-ca",
        "state": "present",
        "enabled": None,
        "signing_authority": None,
        "signing_authority_type": None,
        "static_authorized_principals": None,
        "admins": None,
        "array": None,
        "context": "",
    }
    params.update(overrides)
    return params


def _make_module(params=None, check_mode=False):
    module = Mock()
    module.params = params if params is not None else _base_params()
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _resp(status=200, items=None):
    response = Mock()
    response.status_code = status
    response.items = items if items is not None else []
    return response


def _policy(
    name="ssh-ca",
    enabled=True,
    signer="ca-key",
    signer_type="public-keys",
    principals=None,
):
    signer_ref = Mock()
    signer_ref.name = signer
    signer_ref.resource_type = signer_type
    policy = Mock()
    policy.name = name
    policy.enabled = enabled
    policy.signing_authority = signer_ref
    policy.static_authorized_principals = principals
    return policy


def _member(name, resource_type):
    ref = Mock()
    ref.name = name
    ref.resource_type = resource_type
    item = Mock()
    item.member = ref
    return item


def _blade(existing=None, members=None):
    blade = Mock()
    blade.get_ssh_certificate_authority_policies.return_value = _resp(
        200, [existing] if existing is not None else []
    )
    blade.get_ssh_certificate_authority_policies_members.return_value = _resp(
        200, members or []
    )
    for method in (
        "post_ssh_certificate_authority_policies",
        "patch_ssh_certificate_authority_policies",
        "delete_ssh_certificate_authority_policies",
        "post_ssh_certificate_authority_policies_admins",
        "delete_ssh_certificate_authority_policies_admins",
        "post_ssh_certificate_authority_policies_arrays",
        "delete_ssh_certificate_authority_policies_arrays",
        "get_admins",
    ):
        getattr(blade, method).return_value = _resp(200)
    array = Mock()
    array.name = "myblade"
    blade.get_arrays.return_value = _resp(200, [array])
    return blade


def _run_main(params, blade, api_version="2.30", check_mode=False):
    module = _make_module(params, check_mode)
    with patch(MODULE + ".AnsibleModule", return_value=module), patch(
        MODULE + ".get_system", return_value=blade
    ), patch(MODULE + ".get_rest_api_version", return_value=api_version), patch(
        MODULE + ".LooseVersion", _Version
    ), patch(
        MODULE + ".HAS_PYPURECLIENT", True
    ), patch(
        MODULE + ".ReferenceWritable", _model_mock()
    ), patch(
        MODULE + ".SshCertificateAuthorityPolicyPost", _model_mock()
    ), patch(
        MODULE + ".SshCertificateAuthorityPolicy", _model_mock()
    ):
        try:
            main()
        except SystemExit:
            pass
    return module


def _fail_msg(module):
    module.fail_json.assert_called_once()
    return module.fail_json.call_args[1]["msg"]


class TestPurefbSshCaPolicy:
    """Test cases for purefb_ssh_ca_policy module"""

    # ---------------- helper-function unit tests ----------------

    def test_context_kwargs_returns_empty_without_context(self):
        """_context_kwargs returns {} when no context is set"""
        module = Mock()
        module.params = {"context": ""}
        assert _context_kwargs(module) == {}

    def test_context_kwargs_returns_kwargs_when_set(self):
        """_context_kwargs returns context_names when a context is set"""
        module = Mock()
        module.params = {"context": "peer1"}
        assert _context_kwargs(module) == {"context_names": ["peer1"]}

    def test_validate_principals_accepts_valid_list(self):
        """A short unique list of principals passes validation"""
        module = _make_module(_base_params(static_authorized_principals=["a", "b"]))
        _validate_principals(module)
        module.fail_json.assert_not_called()

    def test_validate_principals_rejects_too_many(self):
        """More than 16 principals is rejected before any API call"""
        principals = ["user{0}".format(index) for index in range(17)]
        module = _make_module(_base_params(static_authorized_principals=principals))
        try:
            _validate_principals(module)
        except SystemExit:
            pass
        assert "at most 16" in _fail_msg(module)

    def test_validate_principals_rejects_duplicates(self):
        """Duplicate principals are rejected"""
        module = _make_module(_base_params(static_authorized_principals=["a", "a"]))
        try:
            _validate_principals(module)
        except SystemExit:
            pass
        assert "Duplicate" in _fail_msg(module)

    def test_validate_principals_rejects_long_entry(self):
        """A principal longer than 128 characters is rejected"""
        module = _make_module(_base_params(static_authorized_principals=["x" * 129]))
        try:
            _validate_principals(module)
        except SystemExit:
            pass
        assert "1 to 128" in _fail_msg(module)

    def test_validate_admins_rejects_duplicates(self):
        """Duplicate admin names are rejected"""
        module = _make_module(_base_params(admins=["alice", "alice"]))
        try:
            _validate_admins(module)
        except SystemExit:
            pass
        assert "Duplicate" in _fail_msg(module)

    def test_validate_admins_rejects_protected_accounts(self):
        """ir and root cannot be attached, whatever the case"""
        for name in ("ir", "Root"):
            module = _make_module(_base_params(admins=[name]))
            try:
                _validate_admins(module)
            except SystemExit:
                pass
            assert "exempt" in _fail_msg(module)

    def test_validate_admins_rejects_duplicates_in_another_case(self):
        """The array resolves admin names without regard to case"""
        module = _make_module(_base_params(admins=["alice", "ALICE"]))
        try:
            _validate_admins(module)
        except SystemExit:
            pass
        assert "Duplicate" in _fail_msg(module)

    def test_get_policy_returns_first_item(self):
        """_get_policy returns the policy when the GET has an item"""
        policy = _policy()
        module = _make_module()
        result = _get_policy(module, _blade(existing=policy), "ssh-ca")
        assert result is policy

    def test_get_policy_returns_none_when_empty(self):
        """_get_policy returns None on a 200 with no items"""
        module = _make_module()
        assert _get_policy(module, _blade(), "ssh-ca") is None

    def test_get_policy_treats_does_not_exist_as_absent(self):
        """A 400 naming the policy as nonexistent reads as None"""
        module = _make_module()
        blade = _blade()
        blade.get_ssh_certificate_authority_policies.return_value = _resp(400)
        with patch(
            MODULE + ".get_error_message",
            return_value="SSH certificate authority policy does not exist.",
        ):
            assert _get_policy(module, blade, "ssh-ca") is None
        module.fail_json.assert_not_called()

    def test_get_policy_fails_on_other_error(self):
        """Any other GET failure fails the task instead of reading as absent"""
        module = _make_module()
        blade = _blade()
        blade.get_ssh_certificate_authority_policies.return_value = _resp(500)
        with patch(MODULE + ".get_error_message", return_value="Internal error"):
            try:
                _get_policy(module, blade, "ssh-ca")
            except SystemExit:
                pass
        assert "Failed to read SSH CA policy ssh-ca" in _fail_msg(module)

    def test_get_members_maps_resource_types(self):
        """Members are reported as (module_type, name) tuples"""
        module = _make_module()
        blade = _blade(members=[_member("alice", "admins"), _member("fb1", "arrays")])
        assert _get_members(module, blade) == {("admin", "alice"), ("array", "fb1")}
        blade.get_ssh_certificate_authority_policies_members.assert_called_once_with(
            policy_names=["ssh-ca"]
        )

    def test_get_members_fails_on_error(self):
        """A failed members GET fails the task"""
        module = _make_module()
        blade = _blade()
        blade.get_ssh_certificate_authority_policies_members.return_value = _resp(400)
        try:
            _get_members(module, blade)
        except SystemExit:
            pass
        assert "Failed to list members" in _fail_msg(module)

    def test_desired_member_changes_admins_only(self):
        """Admins are diffed, protected accounts are never detached"""
        module = _make_module(_base_params(admins=["alice"]))
        current = {("admin", "bob"), ("admin", "ir"), ("array", "myblade")}
        to_add, to_remove = _desired_member_changes(module, _blade(), current)
        assert to_add == {("admin", "alice")}
        assert to_remove == {("admin", "bob")}

    def test_desired_member_changes_array_attach_and_detach(self):
        """array=true attaches the array by name, array=false detaches it"""
        module = _make_module(_base_params(array=True))
        to_add, to_remove = _desired_member_changes(module, _blade(), set())
        assert to_add == {("array", "myblade")}
        assert to_remove == set()

        module = _make_module(_base_params(array=False))
        to_add, to_remove = _desired_member_changes(
            module, _blade(), {("array", "myblade"), ("admin", "alice")}
        )
        assert to_add == set()
        assert to_remove == {("array", "myblade")}

    def test_desired_member_changes_admins_ignore_case(self):
        """Admins are matched without regard to case; a detach uses the array spelling"""
        module = _make_module(_base_params(admins=["ALICE", "carol"]))
        current = {("admin", "Alice"), ("admin", "Bob"), ("admin", "IR")}
        to_add, to_remove = _desired_member_changes(module, _blade(), current)
        assert to_add == {("admin", "carol")}
        assert to_remove == {("admin", "Bob")}

    # ---------------- main(): version gates ----------------

    def test_main_fails_below_minimum_version(self):
        """REST versions below 2.14 are refused before any policy call"""
        blade = _blade()
        module = _run_main(
            _base_params(
                signing_authority="ca-key", signing_authority_type="public_key"
            ),
            blade,
            "2.13",
        )
        assert "requires 2.14+" in _fail_msg(module)
        blade.get_ssh_certificate_authority_policies.assert_not_called()

    def test_main_context_requires_2_30(self):
        """context is refused below REST 2.30"""
        blade = _blade()
        module = _run_main(_base_params(context="peer1"), blade, "2.24")
        assert "context" in _fail_msg(module)
        assert "2.30" in _fail_msg(module)
        blade.get_ssh_certificate_authority_policies.assert_not_called()

    def test_main_context_passed_when_supported(self):
        """context_names reaches the API calls at REST 2.30"""
        blade = _blade(existing=_policy())
        module = _run_main(_base_params(context="peer1"), blade, "2.30")
        blade.get_ssh_certificate_authority_policies.assert_called_once_with(
            names=["ssh-ca"], context_names=["peer1"]
        )
        module.exit_json.assert_called_once_with(changed=False)

    # ---------------- main(): create ----------------

    def test_main_create_posts_policy(self):
        """A missing policy is created with the signer, enabled and principals"""
        blade = _blade()
        module = _run_main(
            _base_params(
                signing_authority="ca-key",
                signing_authority_type="public_key",
                enabled=False,
                static_authorized_principals=["ops"],
            ),
            blade,
        )
        blade.post_ssh_certificate_authority_policies.assert_called_once()
        kwargs = blade.post_ssh_certificate_authority_policies.call_args[1]
        assert kwargs["names"] == ["ssh-ca"]
        assert kwargs["policy"] == {
            "signing_authority": {"name": "ca-key", "resource_type": "public-keys"},
            "enabled": False,
            "static_authorized_principals": ["ops"],
        }
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_create_certificate_signer(self):
        """signing_authority_type=certificate maps to the certificates endpoint"""
        blade = _blade()
        _run_main(
            _base_params(
                signing_authority="corp-ca", signing_authority_type="certificate"
            ),
            blade,
        )
        kwargs = blade.post_ssh_certificate_authority_policies.call_args[1]
        assert kwargs["policy"] == {
            "signing_authority": {"name": "corp-ca", "resource_type": "certificates"}
        }

    def test_main_create_realm_certificate_signer(self):
        """A certificate that lives in a realm is sent under its realm::name"""
        blade = _blade()
        module = _run_main(
            _base_params(
                signing_authority="realm1::corp-ca",
                signing_authority_type="certificate",
            ),
            blade,
        )
        blade.post_ssh_certificate_authority_policies.assert_called_once_with(
            names=["ssh-ca"],
            policy={
                "signing_authority": {
                    "name": "realm1::corp-ca",
                    "resource_type": "certificates",
                }
            },
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_create_requires_signing_authority(self):
        """Creating without a signer fails before the POST"""
        blade = _blade()
        module = _run_main(_base_params(), blade)
        assert "requires signing_authority." in _fail_msg(module)
        blade.post_ssh_certificate_authority_policies.assert_not_called()

    def test_main_create_requires_signing_authority_type(self):
        """Creating with a signer but no type fails before the POST"""
        blade = _blade()
        module = _run_main(_base_params(signing_authority="ca-key"), blade)
        assert "requires signing_authority_type" in _fail_msg(module)
        blade.post_ssh_certificate_authority_policies.assert_not_called()

    def test_main_create_check_mode_skips_post(self):
        """Check mode reports a change without creating anything"""
        blade = _blade()
        module = _run_main(
            _base_params(
                signing_authority="ca-key",
                signing_authority_type="public_key",
                admins=["alice"],
            ),
            blade,
            check_mode=True,
        )
        blade.post_ssh_certificate_authority_policies.assert_not_called()
        blade.post_ssh_certificate_authority_policies_admins.assert_not_called()
        # The admin existence preflight still runs in check mode.
        blade.get_admins.assert_called_once_with(names=["alice"])
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_create_attaches_members(self):
        """Admins and the array listed at create time are attached after the POST"""
        blade = _blade()
        module = _run_main(
            _base_params(
                signing_authority="ca-key",
                signing_authority_type="public_key",
                admins=["alice"],
                array=True,
            ),
            blade,
        )
        blade.post_ssh_certificate_authority_policies.assert_called_once()
        blade.post_ssh_certificate_authority_policies_admins.assert_called_once_with(
            policy_names=["ssh-ca"], member_names=["alice"]
        )
        blade.post_ssh_certificate_authority_policies_arrays.assert_called_once_with(
            policy_names=["ssh-ca"], member_names=["myblade"]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_create_fails_when_admin_missing(self):
        """A nonexistent admin fails the task before the policy POST"""
        blade = _blade()
        blade.get_admins.return_value = _resp(400)
        module = _run_main(
            _base_params(
                signing_authority="ca-key",
                signing_authority_type="public_key",
                admins=["ghost"],
            ),
            blade,
        )
        assert "Admin ghost does not exist" in _fail_msg(module)
        blade.post_ssh_certificate_authority_policies.assert_not_called()

    def test_main_create_fails_on_api_error(self):
        """A failed POST fails the task with the array error"""
        blade = _blade()
        blade.post_ssh_certificate_authority_policies.return_value = _resp(400)
        module = _run_main(
            _base_params(
                signing_authority="ca-key", signing_authority_type="public_key"
            ),
            blade,
        )
        assert "Failed to create SSH CA policy ssh-ca" in _fail_msg(module)

    # ---------------- main(): update ----------------

    def test_main_present_idempotent(self):
        """Matching settings produce no PATCH and changed=False"""
        blade = _blade(existing=_policy(principals=["a", "b"]))
        module = _run_main(
            _base_params(
                signing_authority="ca-key",
                signing_authority_type="public_key",
                enabled=True,
                static_authorized_principals=["b", "a"],
            ),
            blade,
        )
        blade.patch_ssh_certificate_authority_policies.assert_not_called()
        blade.post_ssh_certificate_authority_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_main_update_signer_type_inherited_is_idempotent(self):
        """Naming the current certificate signer without its type sends no PATCH"""
        blade = _blade(existing=_policy(signer="corp-ca", signer_type="certificates"))
        module = _run_main(_base_params(signing_authority="corp-ca"), blade)
        blade.patch_ssh_certificate_authority_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_main_update_signer_name_inherits_current_type(self):
        """A new signer name without a type keeps the current signer type"""
        blade = _blade(existing=_policy(signer="corp-ca", signer_type="certificates"))
        module = _run_main(_base_params(signing_authority="other-ca"), blade)
        blade.patch_ssh_certificate_authority_policies.assert_called_once_with(
            names=["ssh-ca"],
            policy={
                "signing_authority": {
                    "name": "other-ca",
                    "resource_type": "certificates",
                }
            },
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_update_signer_fails_when_type_unknown(self):
        """Without a type and with no current type to inherit the task fails"""
        blade = _blade(existing=_policy(signer="corp-ca", signer_type=None))
        module = _run_main(_base_params(signing_authority="other-ca"), blade)
        assert "signing_authority_type is required" in _fail_msg(module)
        blade.patch_ssh_certificate_authority_policies.assert_not_called()

    def test_main_update_enabled(self):
        """A changed enabled flag is sent alone"""
        blade = _blade(existing=_policy(enabled=True))
        module = _run_main(_base_params(enabled=False), blade)
        blade.patch_ssh_certificate_authority_policies.assert_called_once_with(
            names=["ssh-ca"], policy={"enabled": False}
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_update_signer(self):
        """A changed signing authority (name or type) is sent"""
        blade = _blade(existing=_policy(signer="ca-key"))
        _run_main(
            _base_params(
                signing_authority="ca-key", signing_authority_type="certificate"
            ),
            blade,
        )
        kwargs = blade.patch_ssh_certificate_authority_policies.call_args[1]
        assert kwargs["policy"] == {
            "signing_authority": {"name": "ca-key", "resource_type": "certificates"}
        }

    def test_main_update_signer_case_is_not_a_change(self):
        """The signer name is compared without regard to case, its type still counts"""
        for signer_type, check_mode in (
            (None, False),
            ("public_key", False),
            (None, True),
            ("public_key", True),
        ):
            blade = _blade(existing=_policy(signer="ca-key"))
            module = _run_main(
                _base_params(
                    signing_authority="CA-Key", signing_authority_type=signer_type
                ),
                blade,
                check_mode=check_mode,
            )
            blade.patch_ssh_certificate_authority_policies.assert_not_called()
            module.exit_json.assert_called_once_with(changed=False)

        blade = _blade(existing=_policy(signer="ca-key"))
        module = _run_main(
            _base_params(
                signing_authority="CA-Key", signing_authority_type="certificate"
            ),
            blade,
        )
        blade.patch_ssh_certificate_authority_policies.assert_called_once_with(
            names=["ssh-ca"],
            policy={
                "signing_authority": {"name": "CA-Key", "resource_type": "certificates"}
            },
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_update_realm_signer_case_is_not_a_change(self):
        """A realm certificate named in another case sends no PATCH"""
        for desired in (
            "realm1::corp-ca",
            "REALM1::corp-ca",
            "realm1::CORP-CA",
            "Realm1::Corp-Ca",
        ):
            blade = _blade(
                existing=_policy(signer="realm1::corp-ca", signer_type="certificates")
            )
            module = _run_main(_base_params(signing_authority=desired), blade)
            blade.patch_ssh_certificate_authority_policies.assert_not_called()
            module.exit_json.assert_called_once_with(changed=False)

    def test_main_update_realm_signer_case_check_mode(self):
        """Check mode reports no change for a realm certificate in another case"""
        blade = _blade(
            existing=_policy(signer="realm1::corp-ca", signer_type="certificates"),
            members=[_member("alice", "admins")],
        )
        module = _run_main(
            _base_params(
                signing_authority="REALM1::Corp-CA",
                signing_authority_type="certificate",
            ),
            blade,
            check_mode=True,
        )
        blade.patch_ssh_certificate_authority_policies.assert_not_called()
        module.warn.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_main_update_realm_prefix_of_signer_counts(self):
        """Only the case is ignored: the same leaf name outside the realm is another signer"""
        existing = _policy(signer="realm1::corp-ca", signer_type="certificates")
        blade = _blade(existing=existing)
        module = _run_main(_base_params(signing_authority="REALM1::CORP-CA"), blade)
        blade.patch_ssh_certificate_authority_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

        for desired in ("corp-ca", "CORP-CA", "realm2::corp-ca"):
            blade = _blade(existing=existing)
            module = _run_main(_base_params(signing_authority=desired), blade)
            blade.patch_ssh_certificate_authority_policies.assert_called_once_with(
                names=["ssh-ca"],
                policy={
                    "signing_authority": {
                        "name": desired,
                        "resource_type": "certificates",
                    }
                },
            )
            module.exit_json.assert_called_once_with(changed=True)

    def test_main_update_array_signer_to_realm_signer(self):
        """The certificate of the same leaf name inside a realm is another signer"""
        for desired, check_mode in (
            ("realm1::corp-ca", False),
            ("REALM1::CORP-CA", False),
            ("realm1::corp-ca", True),
        ):
            blade = _blade(
                existing=_policy(signer="corp-ca", signer_type="certificates")
            )
            module = _run_main(
                _base_params(signing_authority=desired), blade, check_mode=check_mode
            )
            if check_mode:
                blade.patch_ssh_certificate_authority_policies.assert_not_called()
            else:
                blade.patch_ssh_certificate_authority_policies.assert_called_once_with(
                    names=["ssh-ca"],
                    policy={
                        "signing_authority": {
                            "name": desired,
                            "resource_type": "certificates",
                        }
                    },
                )
            module.exit_json.assert_called_once_with(changed=True)

    def test_main_update_clears_principals(self):
        """An empty list clears principals that are currently set"""
        blade = _blade(existing=_policy(principals=["ops"]))
        module = _run_main(_base_params(static_authorized_principals=[]), blade)
        blade.patch_ssh_certificate_authority_policies.assert_called_once_with(
            names=["ssh-ca"], policy={"static_authorized_principals": []}
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_update_warns_when_members_attached(self):
        """Changing an attached policy warns about live SSH logins"""
        blade = _blade(
            existing=_policy(enabled=True), members=[_member("alice", "admins")]
        )
        module = _run_main(_base_params(enabled=False), blade)
        module.warn.assert_called_once()
        assert "attached" in module.warn.call_args[0][0]
        blade.get_ssh_certificate_authority_policies_members.assert_called_once()

    def test_main_update_no_warning_for_members_attached_this_run(self):
        """Attaching admins and changing settings in one run reads members once and does not warn"""
        blade = _blade(existing=_policy(enabled=True))
        module = _run_main(_base_params(enabled=False, admins=["alice"]), blade)
        blade.get_ssh_certificate_authority_policies_members.assert_called_once()
        blade.post_ssh_certificate_authority_policies_admins.assert_called_once_with(
            policy_names=["ssh-ca"], member_names=["alice"]
        )
        blade.patch_ssh_certificate_authority_policies.assert_called_once_with(
            names=["ssh-ca"], policy={"enabled": False}
        )
        module.warn.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_update_check_mode_skips_patch(self):
        """Check mode reports the change without a PATCH"""
        blade = _blade(existing=_policy(enabled=True))
        module = _run_main(_base_params(enabled=False), blade, check_mode=True)
        blade.patch_ssh_certificate_authority_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_update_fails_on_api_error(self):
        """A failed PATCH fails the task with the array error"""
        blade = _blade(existing=_policy(enabled=True))
        blade.patch_ssh_certificate_authority_policies.return_value = _resp(400)
        module = _run_main(_base_params(enabled=False), blade)
        assert "Failed to update SSH CA policy ssh-ca" in _fail_msg(module)

    # ---------------- main(): members ----------------

    def test_main_members_attach_and_detach(self):
        """The admins list attaches missing admins and detaches unlisted ones"""
        blade = _blade(
            existing=_policy(),
            members=[_member("bob", "admins"), _member("myblade", "arrays")],
        )
        module = _run_main(_base_params(admins=["alice"]), blade)
        blade.delete_ssh_certificate_authority_policies_admins.assert_called_once_with(
            policy_names=["ssh-ca"], member_names=["bob"]
        )
        blade.post_ssh_certificate_authority_policies_admins.assert_called_once_with(
            policy_names=["ssh-ca"], member_names=["alice"]
        )
        # The array attachment is untouched when `array` is omitted.
        blade.delete_ssh_certificate_authority_policies_arrays.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_members_idempotent(self):
        """A matching admins list makes no member calls"""
        blade = _blade(existing=_policy(), members=[_member("alice", "admins")])
        module = _run_main(_base_params(admins=["alice"]), blade)
        blade.post_ssh_certificate_authority_policies_admins.assert_not_called()
        blade.delete_ssh_certificate_authority_policies_admins.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_main_members_check_mode(self):
        """Check mode reports member changes without attach or detach calls"""
        blade = _blade(existing=_policy(), members=[_member("bob", "admins")])
        module = _run_main(_base_params(admins=["alice"]), blade, check_mode=True)
        blade.post_ssh_certificate_authority_policies_admins.assert_not_called()
        blade.delete_ssh_certificate_authority_policies_admins.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_members_admin_case_is_not_a_change(self):
        """An attached admin named in another case is neither detached nor attached again"""
        for check_mode in (False, True):
            blade = _blade(existing=_policy(), members=[_member("alice", "admins")])
            module = _run_main(
                _base_params(admins=["ALICE"]), blade, check_mode=check_mode
            )
            blade.post_ssh_certificate_authority_policies_admins.assert_not_called()
            blade.delete_ssh_certificate_authority_policies_admins.assert_not_called()
            blade.get_admins.assert_not_called()
            module.exit_json.assert_called_once_with(changed=False)

    def test_main_members_detach_uses_array_spelling(self):
        """Only the unlisted admin is detached, by the name the array reports"""
        blade = _blade(
            existing=_policy(),
            members=[_member("Alice", "admins"), _member("Bob", "admins")],
        )
        module = _run_main(_base_params(admins=["alice", "Carol"]), blade)
        blade.delete_ssh_certificate_authority_policies_admins.assert_called_once_with(
            policy_names=["ssh-ca"], member_names=["Bob"]
        )
        blade.get_admins.assert_called_once_with(names=["Carol"])
        blade.post_ssh_certificate_authority_policies_admins.assert_called_once_with(
            policy_names=["ssh-ca"], member_names=["Carol"]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_rejects_admin_duplicate_in_another_case(self):
        """The same admin in two spellings is refused before any API call"""
        blade = _blade(existing=_policy())
        module = _run_main(_base_params(admins=["alice", "Alice"]), blade)
        assert "Duplicate" in _fail_msg(module)
        blade.get_ssh_certificate_authority_policies.assert_not_called()
        blade.post_ssh_certificate_authority_policies_admins.assert_not_called()

    def test_main_members_realm_qualified_admin_is_another_name(self):
        """Admins are array-level: realm::admin is not the attached admin of that leaf name"""
        for check_mode in (False, True):
            blade = _blade(existing=_policy(), members=[_member("alice", "admins")])
            # The array answers a realm-qualified admin name as a missing admin.
            blade.get_admins.return_value = _resp(400)
            module = _run_main(
                _base_params(admins=["realm1::alice"]), blade, check_mode=check_mode
            )
            assert "Admin realm1::alice does not exist" in _fail_msg(module)
            blade.get_admins.assert_called_once_with(names=["realm1::alice"])
            blade.delete_ssh_certificate_authority_policies_admins.assert_not_called()
            blade.post_ssh_certificate_authority_policies_admins.assert_not_called()

    def test_main_array_detach(self):
        """array=false detaches the array and leaves admins alone"""
        blade = _blade(
            existing=_policy(),
            members=[_member("alice", "admins"), _member("myblade", "arrays")],
        )
        module = _run_main(_base_params(array=False), blade)
        blade.delete_ssh_certificate_authority_policies_arrays.assert_called_once_with(
            policy_names=["ssh-ca"], member_names=["myblade"]
        )
        blade.delete_ssh_certificate_authority_policies_admins.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_array_attach(self):
        """array=true attaches the local array by name when it is not attached"""
        blade = _blade(existing=_policy(), members=[_member("alice", "admins")])
        module = _run_main(_base_params(array=True), blade)
        blade.get_arrays.assert_called_once_with()
        blade.post_ssh_certificate_authority_policies_arrays.assert_called_once_with(
            policy_names=["ssh-ca"], member_names=["myblade"]
        )
        blade.delete_ssh_certificate_authority_policies_admins.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_array_attach_idempotent(self):
        """array=true on an already attached array makes no member calls"""
        blade = _blade(existing=_policy(), members=[_member("myblade", "arrays")])
        module = _run_main(_base_params(array=True), blade)
        blade.post_ssh_certificate_authority_policies_arrays.assert_not_called()
        blade.delete_ssh_certificate_authority_policies_arrays.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_main_array_attach_fails_when_array_unreadable(self):
        """A failed arrays GET fails the task before any attach"""
        blade = _blade(existing=_policy())
        blade.get_arrays.return_value = _resp(400)
        module = _run_main(_base_params(array=True), blade)
        assert "Failed to read the array name" in _fail_msg(module)
        blade.post_ssh_certificate_authority_policies_arrays.assert_not_called()

    def test_main_array_attach_fails_when_no_array_returned(self):
        """An empty arrays GET fails the task before any attach"""
        blade = _blade(existing=_policy())
        blade.get_arrays.return_value = _resp(200, [])
        module = _run_main(_base_params(array=True), blade)
        assert "no array returned" in _fail_msg(module)
        blade.post_ssh_certificate_authority_policies_arrays.assert_not_called()

    def test_main_attach_fails_on_api_error(self):
        """A refused attach fails the task naming the member"""
        blade = _blade(existing=_policy())
        blade.post_ssh_certificate_authority_policies_admins.return_value = _resp(400)
        module = _run_main(_base_params(admins=["alice"]), blade)
        assert "Failed to attach admin alice" in _fail_msg(module)

    # ---------------- main(): delete ----------------

    def test_main_delete(self):
        """An unattached policy is deleted"""
        blade = _blade(existing=_policy())
        module = _run_main(_base_params(state="absent"), blade)
        blade.delete_ssh_certificate_authority_policies.assert_called_once_with(
            names=["ssh-ca"]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_delete_check_mode(self):
        """Check mode reports the delete without issuing it"""
        blade = _blade(existing=_policy())
        module = _run_main(_base_params(state="absent"), blade, check_mode=True)
        blade.delete_ssh_certificate_authority_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_main_delete_refused_with_members(self):
        """A policy with attached members is not deleted"""
        blade = _blade(existing=_policy(), members=[_member("alice", "admins")])
        module = _run_main(_base_params(state="absent"), blade)
        assert "has attached members" in _fail_msg(module)
        blade.delete_ssh_certificate_authority_policies.assert_not_called()

    def test_main_absent_idempotent(self):
        """Deleting a missing policy is a no-op"""
        blade = _blade()
        module = _run_main(_base_params(state="absent"), blade)
        blade.delete_ssh_certificate_authority_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_main_delete_fails_on_api_error(self):
        """A failed DELETE fails the task with the array error"""
        blade = _blade(existing=_policy())
        blade.delete_ssh_certificate_authority_policies.return_value = _resp(400)
        module = _run_main(_base_params(state="absent"), blade)
        assert "Failed to delete SSH CA policy ssh-ca" in _fail_msg(module)
