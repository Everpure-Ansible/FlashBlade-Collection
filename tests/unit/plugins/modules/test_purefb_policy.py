# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_policy rule idempotency and context_names/fleet handling."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
from collections import defaultdict
from unittest.mock import Mock, MagicMock, patch

import pytest

# Mock external dependencies before importing module
sys.modules["pypureclient"] = MagicMock()
sys.modules["pypureclient.flashblade"] = MagicMock()
sys.modules["urllib3"] = MagicMock()
sys.modules["distro"] = MagicMock()
sys.modules["grp"] = MagicMock()
sys.modules["fcntl"] = MagicMock()
sys.modules["pwd"] = MagicMock()
sys.modules["syslog"] = MagicMock()
mock_termios = MagicMock()
mock_termios.TCSAFLUSH = 2
sys.modules["termios"] = mock_termios
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
sys.modules["ansible_collections.everpure.flashblade.plugins.module_utils.version"] = (
    MagicMock()
)
sys.modules[
    "ansible_collections.everpure.flashblade.plugins.module_utils.time_utils"
] = MagicMock()

from plugins.modules.purefb_policy import (
    _check_worm_autocommit_version,
    _OS_ACCESS_ACTIONS_FALLBACK,
    _check_os_actions,
    _nfs_rule,
    _share_rule_patch,
    _share_rule_perms,
    _worm_autocommit_config,
    _worm_autocommit_params,
    _valid_os_actions,
    copy_os_policy_rule,
    copy_policy,
    main,
    create_network_access_policy,
    create_os_policy,
    create_smb_client_policy,
    create_smb_share_policy,
    create_snap_policy,
    create_worm_data_policy,
    delete_network_access_policy,
    delete_smb_share_policy,
    rename_smb_share_policy,
    rename_snap_policy,
    update_network_access_policy,
    update_nfs_policy,
    update_os_policy,
    update_smb_share_policy,
    update_snap_policy,
    update_worm_data_policy,
)
from plugins.module_utils.version import LooseVersion as RealLooseVersion

# The WORM tests compare real millisecond values and real REST versions, so
# they use the collection's own helpers instead of the module_utils mocks.
from plugins.module_utils.time_utils import (
    TimeConversionError as _RealTimeConversionError,
    time_to_milliseconds as _real_ttm,
)
from plugins.module_utils.version import LooseVersion as _RealLooseVersion


def _array_message(res):
    """What get_error_message returns for an SDK error response."""
    return res.errors[0].message


def _error_response(message, status=400):
    """An SDK ErrorResponse: a status and the errors, no items."""
    res = Mock(spec=["status_code", "errors"])
    res.status_code = status
    error = Mock()
    error.message = message
    res.errors = [error]
    return res


def _found(*items):
    """An SDK ValidResponse holding the given items."""
    res = Mock()
    res.status_code = 200
    res.items = list(items)
    res.total_item_count = len(items)
    return res


def _existing_rule(access="root-squash"):
    """Build a mock SDK NFS export policy rule for client 10.0.10.42."""
    rule = Mock()
    rule.access = access
    rule.anongid = "100021"
    rule.anonuid = "20000021"
    rule.atime = True
    rule.client = "10.0.10.42"
    rule.fileid_32bit = False
    rule.permission = "rw"
    rule.secure = False
    rule.security = ["krb5", "krb5i", "krb5p", "sys"]
    rule.index = 1
    return rule


def _module(access):
    """Build a mock AnsibleModule whose desired rule has the given access."""
    module = Mock()
    module.check_mode = False
    module.params = {
        "name": "project96_nfs_policy",
        "client": "10.0.10.42",
        "permission": "rw",
        "access": access,
        # anonuid/anongid are type=int in the argspec; the array (REST 2.21)
        # reports them as strings, see _existing_rule.
        "anonuid": 20000021,
        "anongid": 100021,
        "fileid_32bit": False,
        "atime": True,
        "secure": False,
        "security": ["krb5", "krb5i", "krb5p", "sys"],
        "before_rule": None,
        "context": "",
        "enabled": True,
    }
    module.fail_json = Mock(side_effect=SystemExit("fail_json called"))
    module.exit_json = Mock()
    return module


def _blade(existing_rule):
    """Build a mock blade returning the given existing rule."""
    blade = Mock()
    blade.get_versions.return_value.items = []  # no context API version

    rules_resp = Mock()
    rules_resp.status_code = 200
    rules_resp.total_item_count = 1
    rules_resp.items = [existing_rule]
    blade.get_nfs_export_policies_rules.return_value = rules_resp

    ok = Mock()
    ok.status_code = 200
    blade.patch_nfs_export_policies_rules.return_value = ok

    policy = Mock()
    policy.enabled = True
    policy_resp = Mock()
    policy_resp.items = [policy]
    blade.get_nfs_export_policies.return_value = policy_resp
    return blade


class TestUpdateNfsPolicyRule:
    """Regression tests for NFS export policy rule idempotency."""

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_access_change_triggers_patch(self, mock_loose_version):
        """Changing only access (root-squash -> no-squash) must PATCH the rule."""
        # Context API version absent: context feature gate OFF
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _module(access="no-squash")
        blade = _blade(_existing_rule(access="root-squash"))

        update_nfs_policy(module, blade)

        blade.patch_nfs_export_policies_rules.assert_called_once()
        # rule name targeted is "<policy>.<index>"
        call_kwargs = blade.patch_nfs_export_policies_rules.call_args[1]
        assert call_kwargs["names"] == ["project96_nfs_policy.1"]
        # Below REST 2.22 the rule body is a plain dict (see _nfs_rule).
        # client/permission must reach the array as the original strings, not
        # the sorted() char lists used only for the idempotency comparison.
        rule_body = call_kwargs["rule"]
        assert isinstance(rule_body, dict)
        assert rule_body["client"] == "10.0.10.42"
        assert rule_body["permission"] == "rw"
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_no_change_is_idempotent(self, mock_loose_version):
        """Identical desired state (incl. access) must not PATCH the rule."""
        # Context API version absent: context feature gate OFF
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _module(access="root-squash")
        blade = _blade(_existing_rule(access="root-squash"))

        update_nfs_policy(module, blade)

        blade.patch_nfs_export_policies_rules.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_access_change_preserves_unspecified_anon(self, mock_loose_version):
        """An access-only change must not reset anonuid/anongid left unset."""
        # Context API version absent: context feature gate OFF
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _module(access="no-squash")
        # Task changes access only and does not re-specify the anon mappings.
        module.params["anonuid"] = None
        module.params["anongid"] = None
        blade = _blade(_existing_rule(access="root-squash"))

        update_nfs_policy(module, blade)

        blade.patch_nfs_export_policies_rules.assert_called_once()
        # The patched rule must keep the existing anon ids, not null them out,
        # and client/permission must be the original strings (not sorted lists).
        # Below REST 2.22 the anon ids go back to the array as strings, which
        # is how it declares (and reported) them.
        rule_body = blade.patch_nfs_export_policies_rules.call_args[1]["rule"]
        assert rule_body["access"] == "no-squash"
        assert rule_body["anonuid"] == "20000021"
        assert rule_body["anongid"] == "100021"
        assert rule_body["client"] == "10.0.10.42"
        assert rule_body["permission"] == "rw"

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_anon_ids_are_strings_below_rest_2_22(self, mock_loose_version):
        """A task anonuid (int) is compared against the array's string value
        and, on an array below REST 2.22, sent back as a string: those arrays
        reject an integer anonuid on PATCH with "invalid value for anonuid"."""
        import plugins.modules.purefb_policy as pol

        pol.NfsExportPolicyRule.reset_mock()
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _module(access="root-squash")
        module.params["anonuid"] = 1000
        blade = _blade(_existing_rule(access="root-squash"))

        update_nfs_policy(module, blade)

        blade.patch_nfs_export_policies_rules.assert_called_once()
        rule_body = blade.patch_nfs_export_policies_rules.call_args[1]["rule"]
        assert rule_body["anonuid"] == "1000"
        assert rule_body["anongid"] == "100021"
        # The SDK model is not used at all: it only accepts integers.
        pol.NfsExportPolicyRule.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_patch_sends_string_anon_ids_from_rest_2_22(self, mock_loose_version):
        """From REST 2.22 the array still rejects integer anon ids on PATCH
        ("invalid value for anonuid", seen on 2.21 and 2.24), so the PATCH
        body is a plain dict with the ids as strings, never the SDK model
        (#600)."""
        import plugins.modules.purefb_policy as pol

        pol.NfsExportPolicyRule.reset_mock()
        # Every version gate ON (context stays off: module.params["context"]
        # is empty).
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        module = _module(access="root-squash")
        module.params["anonuid"] = 1000
        existing = _existing_rule(access="root-squash")
        existing.anonuid = 20000021
        existing.anongid = 100021
        blade = _blade(existing)

        update_nfs_policy(module, blade)

        blade.patch_nfs_export_policies_rules.assert_called_once()
        rule_body = blade.patch_nfs_export_policies_rules.call_args[1]["rule"]
        assert isinstance(rule_body, dict)
        assert rule_body["anonuid"] == "1000"
        assert rule_body["anongid"] == "100021"
        pol.NfsExportPolicyRule.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_unrelated_change_keeps_existing_anon_ids_as_strings(
        self, mock_loose_version
    ):
        """The reporter's case in #600: a rule with anon ids, a task that
        only changes atime. The ids are filled from the current rule and go
        back as strings, so the array accepts the PATCH."""
        import plugins.modules.purefb_policy as pol

        pol.NfsExportPolicyRule.reset_mock()
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        module = _module(access=None)
        module.params.update(
            {
                "permission": None,
                "anonuid": None,
                "anongid": None,
                "fileid_32bit": None,
                "atime": False,
                "secure": None,
                "security": None,
            }
        )
        existing = _existing_rule(access="all-squash")
        existing.anonuid = 1234
        existing.anongid = 5678
        blade = _blade(existing)

        update_nfs_policy(module, blade)

        rule_body = blade.patch_nfs_export_policies_rules.call_args[1]["rule"]
        assert rule_body["atime"] is False
        assert rule_body["anonuid"] == "1234"
        assert rule_body["anongid"] == "5678"
        assert rule_body["access"] == "all-squash"
        pol.NfsExportPolicyRule.assert_not_called()

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_security_order_is_kept_when_task_leaves_it_unset(self, mock_loose_version):
        """The stored sec= order is a client preference: an unrelated update
        must send it back unchanged, not sorted (#600)."""
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _module(access="no-squash")
        module.params["security"] = None
        existing = _existing_rule(access="root-squash")
        existing.security = ["sys", "krb5"]
        blade = _blade(existing)

        update_nfs_policy(module, blade)

        rule_body = blade.patch_nfs_export_policies_rules.call_args[1]["rule"]
        assert rule_body["security"] == ["sys", "krb5"]

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_security_compares_order_insensitively(self, mock_loose_version):
        """The same flavours in another order are not a change."""
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _module(access="root-squash")
        module.params["security"] = ["krb5", "sys"]
        existing = _existing_rule(access="root-squash")
        existing.security = ["sys", "krb5"]
        blade = _blade(existing)

        update_nfs_policy(module, blade)

        blade.patch_nfs_export_policies_rules.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)


class TestNfsRuleBody:
    """_nfs_rule: integers on POST from REST 2.22, strings on every PATCH."""

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_post_uses_sdk_model_with_ints_from_rest_2_22(self, mock_loose_version):
        import plugins.modules.purefb_policy as pol

        pol.NfsExportPolicyRule.reset_mock()
        mock_loose_version.return_value.__le__ = Mock(return_value=True)

        body = _nfs_rule("2.24", client="10.0.0.1", anonuid=1234, anongid=None)

        assert body is pol.NfsExportPolicyRule.return_value
        assert pol.NfsExportPolicyRule.call_args[1] == {
            "client": "10.0.0.1",
            "anonuid": 1234,
        }

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_patch_is_a_dict_with_string_ids_from_rest_2_22(self, mock_loose_version):
        import plugins.modules.purefb_policy as pol

        pol.NfsExportPolicyRule.reset_mock()
        mock_loose_version.return_value.__le__ = Mock(return_value=True)

        body = _nfs_rule(
            "2.24", patch=True, client="10.0.0.1", anonuid=1234, anongid=5678
        )

        assert body == {"client": "10.0.0.1", "anonuid": "1234", "anongid": "5678"}
        pol.NfsExportPolicyRule.assert_not_called()

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_post_below_rest_2_22_is_a_dict_with_string_ids(self, mock_loose_version):
        mock_loose_version.return_value.__le__ = Mock(return_value=False)

        body = _nfs_rule("2.21", client="10.0.0.1", anonuid=1234)

        assert body == {"client": "10.0.0.1", "anonuid": "1234"}


def _main_network_module(**overrides):
    """Params for main() on a network policy task, as AnsibleModule would
    hand them over: context unset, so the fleet default applies."""
    module = Mock()
    module.check_mode = False
    module.params = {
        "state": "absent",
        "policy_type": "network",
        "enabled": True,
        "name": "default-network-access-policy",
        "rename": None,
        "client": "192.0.2.10",
        "effect": None,
        "interfaces": ["management-ssh"],
        "before_rule": None,
        "context": "",
        "account": None,
        "user": None,
    }
    module.params.update(overrides)
    module.fail_json = Mock(side_effect=SystemExit("fail_json called"))
    module.exit_json = Mock()
    return module


def _fleet_member_blade():
    """A blade that reports fleet membership, whose network policy lookups
    reject any keyword other than names, as the SDK does."""
    blade = Mock()
    fleet = Mock()
    fleet.status_code = 200
    fleet.items = [Mock()]
    blade.get_fleets.return_value = fleet
    array = Mock()
    array.name = "fb-member"
    blade.get_arrays.return_value.items = [array]

    lookups = []

    def get_policies(names, **kwargs):
        lookups.append(kwargs)
        if kwargs:
            raise TypeError(
                "Client.get_network_access_policies() got an unexpected "
                "keyword argument 'context_names'"
            )
        resp = Mock()
        resp.status_code = 200
        resp.items = [Mock()]
        return resp

    def get_rules(policy_names, names, **kwargs):
        lookups.append(kwargs)
        if kwargs:
            raise TypeError(
                "Client.get_network_access_policies_rules() got an unexpected "
                "keyword argument 'context_names'"
            )
        resp = Mock()
        resp.status_code = 200
        return resp

    blade.get_network_access_policies.side_effect = get_policies
    blade.get_network_access_policies_rules.side_effect = get_rules
    blade.lookups = lookups
    return blade


class TestNetworkPolicyOnFleetMember:
    """main() defaults context to the array name on a fleet member, but the
    network-access-policies endpoints take no context (#599).  main() also
    gates on the optional pytz import, so these tests force HAS_PYTZ the way
    the other main() tests force HAS_PYPURECLIENT: a unit test must not depend
    on an optional library being installed."""

    @patch("plugins.modules.purefb_policy.delete_network_access_policy")
    @patch("plugins.modules.purefb_policy.get_rest_api_version")
    @patch("plugins.modules.purefb_policy.get_system")
    @patch("plugins.modules.purefb_policy.AnsibleModule")
    @patch("plugins.modules.purefb_policy.HAS_PYTZ", True)
    @patch("plugins.modules.purefb_policy.LooseVersion", side_effect=lambda v: v)
    def test_lookup_sends_no_context(
        self, _lv, mock_ansible_module, mock_get_system, mock_version, mock_delete
    ):
        import plugins.modules.purefb_policy as pol

        module = _main_network_module()
        mock_ansible_module.return_value = module
        blade = _fleet_member_blade()
        mock_get_system.return_value = blade
        mock_version.return_value = "2.24"

        pol.main()

        # The fleet default did run ...
        assert module.params["context"] == "fb-member"
        # ... and the lookup was made without it
        assert blade.lookups == [{}]
        mock_delete.assert_called_once_with(module, blade)
        module.fail_json.assert_not_called()

    @patch("plugins.modules.purefb_policy.update_network_access_policy")
    @patch("plugins.modules.purefb_policy.get_rest_api_version")
    @patch("plugins.modules.purefb_policy.get_system")
    @patch("plugins.modules.purefb_policy.AnsibleModule")
    @patch("plugins.modules.purefb_policy.HAS_PYTZ", True)
    @patch("plugins.modules.purefb_policy.LooseVersion", side_effect=lambda v: v)
    def test_before_rule_lookup_sends_no_context(
        self, _lv, mock_ansible_module, mock_get_system, mock_version, mock_update
    ):
        import plugins.modules.purefb_policy as pol

        module = _main_network_module(state="present", before_rule=2)
        mock_ansible_module.return_value = module
        blade = _fleet_member_blade()
        mock_get_system.return_value = blade
        mock_version.return_value = "2.24"

        pol.main()

        assert module.params["context"] == "fb-member"
        assert blade.lookups == [{}, {}]
        mock_update.assert_called_once_with(module, blade)
        module.fail_json.assert_not_called()


def _snap_rule(every=86400000, keep_for=86400000, at=None, time_zone=None):
    """Build a mock SDK snapshot policy rule (values in milliseconds)."""
    rule = Mock()
    rule.every = every
    rule.keep_for = keep_for
    rule.at = at
    rule.time_zone = time_zone
    return rule


def _snap_module(keep_for=None, every=None, at=None, timezone=None):
    """Build a mock AnsibleModule for update_snap_policy.

    keep_for/every are in seconds (the task's units), matching the argspec.
    """
    module = Mock()
    module.check_mode = False
    module.params = {
        "name": "daily_snap_policy",
        "keep_for": keep_for,
        "every": every,
        "at": at,
        "timezone": timezone,
        "enabled": True,
        "context": "",
        "state": "present",
        "filesystem": None,
        "replica_link": None,
    }
    module.fail_json = Mock(side_effect=SystemExit("fail_json called"))
    module.exit_json = Mock()
    return module


def _snap_blade(existing_rule, enabled=True):
    """Build a mock blade whose policy has the given schedule rule(s)."""
    blade = Mock()
    blade.get_versions.return_value.items = []  # no context API version

    policy = Mock()
    policy.enabled = enabled
    if isinstance(existing_rule, list):
        policy.rules = existing_rule
    else:
        policy.rules = [existing_rule]
    policies_resp = Mock()
    policies_resp.items = [policy]
    blade.get_policies.return_value = policies_resp

    ok = Mock()
    ok.status_code = 200
    blade.patch_policies.return_value = ok
    return blade


class TestUpdateSnapPolicy:
    """Regression tests for snapshot policy rule partial updates."""

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_retention_change_preserves_at_schedule(self, mock_loose_version):
        """Updating every/keep_for on an at-scheduled policy must preserve the
        existing ``at`` time and timezone, not drop them to an interval rule."""
        import plugins.modules.purefb_policy as pol

        # Context API version absent: context feature gate OFF
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        # Existing rule keeps snapshots taken daily at 10:00 in a named tz.
        # The task changes retention/interval but does not re-specify at/timezone
        # (the guards require every and keep_for to be supplied together).
        module = _snap_module(keep_for=259200, every=86400)
        blade = _snap_blade(
            _snap_rule(
                every=86400000,
                keep_for=86400000,
                at=36000000,
                time_zone="America/New_York",
            )
        )

        update_snap_policy(module, blade)

        blade.patch_policies.assert_called_once()
        module.fail_json.assert_not_called()
        # The re-added rule must keep the at time and timezone, not drop them.
        rule_kwargs = pol.PolicyRule.call_args[1]
        assert rule_kwargs["keep_for"] == 259200 * 1000
        assert rule_kwargs["every"] == 86400 * 1000
        assert rule_kwargs["at"] == 36000000
        assert rule_kwargs["time_zone"] == "America/New_York"
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_no_change_is_idempotent(self, mock_loose_version):
        """Identical desired schedule must not PATCH the policy."""
        # Context API version absent: context feature gate OFF
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _snap_module(keep_for=86400, every=86400)
        blade = _snap_blade(_snap_rule(every=86400000, keep_for=86400000))

        update_snap_policy(module, blade)

        blade.patch_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_disable_existing_policy_patches_enabled(self, mock_loose_version):
        """enabled=false on an existing policy must PATCH enabled even though
        no rule is added (#12)."""
        import plugins.modules.purefb_policy as pol

        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _snap_module()
        module.params["enabled"] = False
        blade = _snap_blade(_snap_rule(every=3600000, keep_for=86400000))

        update_snap_policy(module, blade)

        blade.patch_policies.assert_called_once()
        patch_kwargs = pol.SnapshotPolicyPatch.call_args[1]
        assert patch_kwargs["enabled"] is False
        assert "add_rules" not in patch_kwargs
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_disable_already_disabled_is_idempotent(self, mock_loose_version):
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _snap_module()
        module.params["enabled"] = False
        blade = _snap_blade(_snap_rule(every=3600000, keep_for=86400000), enabled=False)

        update_snap_policy(module, blade)

        blade.patch_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_matching_second_rule_is_not_readded(self, mock_loose_version):
        """When the task's rule already exists as the policy's second rule it
        must not be added again on every run."""
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _snap_module(keep_for=172800, every=86400)
        blade = _snap_blade(
            [
                _snap_rule(every=3600000, keep_for=86400000),
                _snap_rule(every=86400000, keep_for=172800000),
            ]
        )

        update_snap_policy(module, blade)

        blade.patch_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_new_rule_added_next_to_existing_rule(self, mock_loose_version):
        import plugins.modules.purefb_policy as pol

        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _snap_module(keep_for=172800, every=86400)
        blade = _snap_blade([_snap_rule(every=3600000, keep_for=86400000)])

        update_snap_policy(module, blade)

        blade.patch_policies.assert_called_once()
        rule_kwargs = pol.PolicyRule.call_args[1]
        assert rule_kwargs == {"keep_for": 172800000, "every": 86400000}
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_rule_added_to_policy_without_rules(self, mock_loose_version):
        import plugins.modules.purefb_policy as pol

        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _snap_module(keep_for=86400, every=3600)
        blade = _snap_blade([])

        update_snap_policy(module, blade)

        blade.patch_policies.assert_called_once()
        rule_kwargs = pol.PolicyRule.call_args[1]
        assert rule_kwargs == {"keep_for": 86400000, "every": 3600000}
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_member_detach_does_not_touch_enabled(self, mock_loose_version):
        """state=absent with a filesystem list only detaches members; the
        default enabled=true must not re-enable a disabled policy."""
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _snap_module()
        module.params["state"] = "absent"
        module.params["filesystem"] = ["fs1"]
        blade = _snap_blade(_snap_rule(every=3600000, keep_for=86400000), enabled=False)
        blade.get_policies_file_systems.return_value = _found()

        update_snap_policy(module, blade)

        blade.patch_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)


class TestRenameSnapPolicy:
    """Snapshot policy rename must carry the new name on the wire and must be
    checked afterwards: Purity//FB 4.6.4 (REST 2.21) answers 200 to
    {"name": ...} on PATCH /policies and keeps the old name, while 4.8.8
    (REST 2.30) rejects the PATCH outright."""

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_rename_sends_name_in_policy_body(self, mock_loose_version):
        """SnapshotPolicyPatch strips `name` from the request body (read-only
        in the SDK model), so the body must be built from Policy, which keeps
        it. When the array honours it the new name reads back and the module
        reports changed."""
        import plugins.modules.purefb_policy as pol

        pol.Policy.reset_mock()
        pol.SnapshotPolicyPatch.reset_mock()
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _snap_module()
        module.params["rename"] = "weekly_snap_policy"
        blade = _snap_blade(_snap_rule())
        blade.get_policies.return_value.status_code = 200

        rename_snap_policy(module, blade)

        pol.Policy.assert_called_once_with(name="weekly_snap_policy")
        pol.SnapshotPolicyPatch.assert_not_called()
        blade.patch_policies.assert_called_once_with(
            names=["daily_snap_policy"], policy=pol.Policy.return_value
        )
        blade.get_policies.assert_called_once_with(names=["weekly_snap_policy"])
        module.fail_json.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_rename_ignored_by_array_fails(self, mock_loose_version):
        """A 200 that leaves the old name in place must fail, not report a
        rename that never happened (the QA rename step repeated forever)."""
        import plugins.modules.purefb_policy as pol

        pol.Policy.reset_mock()
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _snap_module()
        module.params["rename"] = "weekly_snap_policy"
        blade = _snap_blade(_snap_rule())
        # The new name does not exist after the PATCH: FlashBlade answers 400
        # to a GET for an unknown policy name.
        blade.get_policies.return_value.status_code = 400

        with pytest.raises(SystemExit):
            rename_snap_policy(module, blade)

        blade.patch_policies.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "kept the old name" in msg
        assert "does not support renaming snapshot policies" in msg
        module.exit_json.assert_not_called()

    @patch(
        "plugins.modules.purefb_policy.get_error_message",
        return_value="Missing or invalid parameter.",
    )
    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_rename_rejected_by_array_fails_clearly(
        self, mock_loose_version, _get_error_message
    ):
        """Purity//FB 4.8.8 (REST 2.30) answers 400 "Missing or invalid
        parameter" to the rename PATCH. The module must still say that
        snapshot policies cannot be renamed, not just echo the array."""
        import plugins.modules.purefb_policy as pol

        pol.Policy.reset_mock()
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _snap_module()
        module.params["rename"] = "weekly_snap_policy"
        blade = _snap_blade(_snap_rule())
        rejected = Mock()
        rejected.status_code = 400
        blade.patch_policies.return_value = rejected

        with pytest.raises(SystemExit):
            rename_snap_policy(module, blade)

        blade.patch_policies.assert_called_once()
        blade.get_policies.assert_not_called()
        msg = module.fail_json.call_args[1]["msg"]
        assert "does not support renaming snapshot policies" in msg
        assert "Missing or invalid parameter" in msg
        module.exit_json.assert_not_called()

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_rename_check_mode_fails_without_touching_array(self, mock_loose_version):
        """Check mode must not predict a rename no release performs."""
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _snap_module()
        module.check_mode = True
        module.params["rename"] = "weekly_snap_policy"
        blade = _snap_blade(_snap_rule())

        with pytest.raises(SystemExit):
            rename_snap_policy(module, blade)

        blade.patch_policies.assert_not_called()
        blade.get_policies.assert_not_called()
        msg = module.fail_json.call_args[1]["msg"]
        assert "does not support renaming snapshot policies" in msg
        module.exit_json.assert_not_called()


def _ctx_module(context):
    module = Mock()
    module.check_mode = False
    module.params = {
        "name": "share_pol",
        "rename": "share_pol2",
        "context": context,
    }
    module.fail_json = Mock(side_effect=SystemExit("fail_json called"))
    module.exit_json = Mock()
    return module


def _ctx_blade():
    blade = Mock()
    # Array supports the context API version (2.17+)
    blade.get_versions.return_value.items = ["2.17"]
    ok = Mock()
    ok.status_code = 200
    blade.patch_smb_share_policies.return_value = ok
    return blade


class TestPolicyContextGating:
    """context_names must only be sent when a context is set."""

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_no_context_omits_context_names(self, mock_loose_version):
        """Standalone array (no context) must not send context_names."""
        # Context API version present (2.17): gate ON, context param decides
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        module = _ctx_module(context="")
        blade = _ctx_blade()

        rename_smb_share_policy(module, blade)

        blade.patch_smb_share_policies.assert_called_once()
        assert "context_names" not in blade.patch_smb_share_policies.call_args[1]
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_with_context_sends_context_names(self, mock_loose_version):
        """When a context is set, context_names must be sent."""
        # Context API version present (2.17): gate ON, context param decides
        mock_loose_version.return_value.__le__ = Mock(return_value=True)
        module = _ctx_module(context="member-array")
        blade = _ctx_blade()

        rename_smb_share_policy(module, blade)

        blade.patch_smb_share_policies.assert_called_once()
        assert blade.patch_smb_share_policies.call_args[1]["context_names"] == [
            "member-array"
        ]


def _share_rule(read="allow", change="allow", full_control=None):
    """Build a mock SDK SMB share policy rule for principal Everyone.

    The default is what Purity//FB 4.6.4 stores for the QA scenario's
    create task (read/change allow, full_control deny): the array keeps one
    effect per rule and reports the ungranted full_control as None.
    """
    rule = Mock()
    # The array names a share rule after its principal; there is no index.
    rule.id = "10314f42-020d-7080-8013-000000000001"
    rule.name = "Everyone"
    rule.principal = "Everyone"
    rule.read = read
    rule.change = change
    rule.full_control = full_control
    return rule


def _share_module(**overrides):
    """Build a mock AnsibleModule for the SMB share policy functions."""
    module = Mock()
    module.check_mode = False
    module.params = {
        "name": "share_pol",
        "principal": "Everyone",
        "read": None,
        "change": None,
        "full_control": None,
        "before_rule": None,
        "context": "",
        "enabled": True,
    }
    module.params.update(overrides)
    module.fail_json = Mock(side_effect=SystemExit("fail_json called"))
    module.exit_json = Mock()
    return module


def _share_blade(rules):
    """Build a mock blade whose principal filter returns the given rules."""
    blade = Mock()
    blade.get_versions.return_value.items = []

    rules_resp = Mock()
    rules_resp.status_code = 200
    rules_resp.total_item_count = len(rules)
    rules_resp.items = rules
    blade.get_smb_share_policies_rules.return_value = rules_resp

    ok = Mock()
    ok.status_code = 200
    blade.patch_smb_share_policies_rules.return_value = ok
    blade.delete_smb_share_policies_rules.return_value = ok

    policy = Mock()
    policy.enabled = True
    policy_resp = Mock()
    policy_resp.items = [policy]
    blade.get_smb_share_policies.return_value = policy_resp
    return blade


class TestUpdateSmbSharePolicy:
    """Regression tests for SMB share policy rule reconciliation (#10)."""

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_present_without_permissions_is_idempotent(self, mock_loose_version):
        """A second `present` with read/change/full_control unset used to
        crash in sorted(None); it must be a no-op."""
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _share_module()
        blade = _share_blade([_share_rule()])

        update_smb_share_policy(module, blade)

        blade.patch_smb_share_policies_rules.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_same_permissions_are_idempotent(self, mock_loose_version):
        """The QA scenario's create task repeated: full_control=deny next to
        read/change=allow is "not granted", which the array stores as None.
        Comparing the raw strings reported a change and the PATCH it sent
        (full_control=deny) flipped the rule to deny-all."""
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _share_module(read="allow", change="allow", full_control="deny")
        blade = _share_blade([_share_rule()])

        update_smb_share_policy(module, blade)

        blade.patch_smb_share_policies_rules.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_live_rule_is_normalised_too(self, mock_loose_version):
        """A live rule in a shape the array no longer produces compares by
        its ladder as well."""
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _share_module(read="allow", change="allow", full_control="deny")
        blade = _share_blade([_share_rule(full_control="deny")])

        update_smb_share_policy(module, blade)

        blade.patch_smb_share_policies_rules.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_principal_case_is_not_a_change(self, mock_loose_version):
        """The principal filter is case-insensitive on the array while the
        stored name keeps its case; PATCH cannot change it, so it is not
        compared."""
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _share_module(principal="everyone")
        blade = _share_blade([_share_rule()])

        update_smb_share_policy(module, blade)

        blade.patch_smb_share_policies_rules.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_permission_change_patches_rule(self, mock_loose_version):
        import plugins.modules.purefb_policy as pol

        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _share_module(read="allow", change="allow", full_control="allow")
        blade = _share_blade([_share_rule()])

        update_smb_share_policy(module, blade)

        blade.patch_smb_share_policies_rules.assert_called_once()
        # Addressed by the id of the rule, never by a "<policy>.<index>"
        # name (share rules have no index) and not by principal and policy
        # name either: that form does not find the rule of a policy in a
        # realm for an administrator limited to that realm.
        call_kwargs = blade.patch_smb_share_policies_rules.call_args[1]
        assert call_kwargs["ids"] == ["10314f42-020d-7080-8013-000000000001"]
        assert "names" not in call_kwargs
        assert "policy_names" not in call_kwargs
        assert "context_names" not in call_kwargs
        # PATCH smb-share-policies/rules rejects `principal` ("Invalid body
        # parameter: principal") and derives implied permissions itself, so
        # only the permission that actually changes goes on the wire.
        rule_kwargs = pol.SmbSharePolicyRule.call_args[1]
        assert rule_kwargs == {"full_control": "allow"}
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_blank_clears_permission(self, mock_loose_version):
        """An empty string clears a set permission and is sent to the SDK as ""."""
        import plugins.modules.purefb_policy as pol

        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _share_module(full_control="")
        blade = _share_blade([_share_rule(full_control="allow")])

        update_smb_share_policy(module, blade)

        blade.patch_smb_share_policies_rules.assert_called_once()
        rule_kwargs = pol.SmbSharePolicyRule.call_args[1]
        # Unset and unchanged fields stay off the wire; "" clears the one set.
        assert rule_kwargs == {"full_control": ""}
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_deny_full_control_alone_denies_everything(self, mock_loose_version):
        """full_control=deny on its own is a deny rule; the array cascades
        the effect down, so only the top level goes on the wire."""
        import plugins.modules.purefb_policy as pol

        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _share_module(full_control="deny")
        blade = _share_blade([_share_rule()])

        update_smb_share_policy(module, blade)

        blade.patch_smb_share_policies_rules.assert_called_once()
        rule_kwargs = pol.SmbSharePolicyRule.call_args[1]
        assert rule_kwargs == {"full_control": "deny"}
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_effect_change_sends_the_new_top_level(self, mock_loose_version):
        """read=allow on a deny-all rule: the array drops the denied levels
        above read itself, so read=allow alone is the whole body."""
        import plugins.modules.purefb_policy as pol

        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _share_module(read="allow")
        blade = _share_blade(
            [_share_rule(read="deny", change="deny", full_control="deny")]
        )

        update_smb_share_policy(module, blade)

        blade.patch_smb_share_policies_rules.assert_called_once()
        rule_kwargs = pol.SmbSharePolicyRule.call_args[1]
        assert rule_kwargs == {"read": "allow"}
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_clearing_read_fails(self, mock_loose_version):
        """A share rule cannot be empty (the array rejects read=""); the
        module says so before calling the array."""
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _share_module(read="")
        blade = _share_blade([_share_rule()])

        with pytest.raises(SystemExit):
            update_smb_share_policy(module, blade)

        module.fail_json.assert_called_once()
        assert "state=absent" in module.fail_json.call_args[1]["msg"]
        blade.patch_smb_share_policies_rules.assert_not_called()

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_missing_rule_is_posted_in_stored_form(self, mock_loose_version):
        """A new rule is POSTed as the array stores it (the raw task values
        can mix allow and deny, which POST rejects)."""
        import plugins.modules.purefb_policy as pol

        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _share_module(read="allow", change="allow", full_control="deny")
        blade = _share_blade([])
        ok = Mock()
        ok.status_code = 200
        blade.post_smb_share_policies_rules.return_value = ok

        update_smb_share_policy(module, blade)

        blade.post_smb_share_policies_rules.assert_called_once()
        rule_kwargs = pol.SmbSharePolicyRule.call_args[1]
        assert rule_kwargs == {
            "principal": "Everyone",
            "read": "allow",
            "change": "allow",
        }
        module.exit_json.assert_called_once_with(changed=True)


class TestShareRuleLadder:
    """The permission ladder as Purity//FB 4.6.4 (REST 2.21) stores it.

    The POST table is the array's own answer to every allow/deny
    combination, read back after creation; 400 rows are what the module
    interprets instead of sending them."""

    # (read, change, full_control) requested -> stored
    POST_MATRIX = [
        ((None, None, "allow"), ("allow", "allow", "allow")),
        ((None, None, "deny"), ("deny", "deny", "deny")),
        ((None, "allow", None), ("allow", "allow", None)),
        ((None, "allow", "allow"), ("allow", "allow", "allow")),
        ((None, "allow", "deny"), ("allow", "allow", None)),
        ((None, "deny", None), ("deny", "deny", None)),
        ((None, "deny", "allow"), ("deny", "deny", None)),
        ((None, "deny", "deny"), ("deny", "deny", "deny")),
        (("allow", None, None), ("allow", None, None)),
        (("allow", None, "allow"), ("allow", "allow", "allow")),
        (("allow", "allow", None), ("allow", "allow", None)),
        (("allow", "allow", "allow"), ("allow", "allow", "allow")),
        (("allow", "allow", "deny"), ("allow", "allow", None)),
        (("deny", None, None), ("deny", None, None)),
        (("deny", None, "deny"), ("deny", "deny", "deny")),
        (("deny", "deny", None), ("deny", "deny", None)),
        (("deny", "deny", "allow"), ("deny", "deny", None)),
        (("deny", "deny", "deny"), ("deny", "deny", "deny")),
        # Rejected by POST ("Cannot have different SMB share permissions
        # within the same rule"): a contrary level above the granted ones
        # is read as "not granted".
        (("allow", None, "deny"), ("allow", None, None)),
        (("allow", "deny", None), ("allow", None, None)),
        (("deny", "allow", None), ("deny", None, None)),
    ]

    @staticmethod
    def _perms(values):
        return dict(zip(("read", "change", "full_control"), values))

    @pytest.mark.parametrize("requested,stored", POST_MATRIX)
    def test_new_rule_matches_array_storage(self, requested, stored):
        assert _share_rule_perms({}, self._perms(requested)) == self._perms(stored)

    # (live, task) -> stored after PATCH, as observed on the array
    PATCH_MATRIX = [
        (("allow", "allow", "allow"), {"read": "deny"}, ("deny", None, None)),
        (("allow", "allow", "allow"), {"change": "deny"}, ("deny", "deny", None)),
        (("allow", "allow", "allow"), {"change": ""}, ("allow", None, None)),
        (("allow", "allow", "allow"), {"full_control": ""}, ("allow", "allow", None)),
        (("allow", "allow", "allow"), {"read": "allow"}, ("allow", "allow", "allow")),
        (("allow", None, None), {"full_control": "allow"}, ("allow", "allow", "allow")),
        (("allow", None, None), {"change": "allow"}, ("allow", "allow", None)),
        (("allow", None, None), {"change": "deny"}, ("deny", "deny", None)),
        (("allow", None, None), {"full_control": "deny"}, ("deny", "deny", "deny")),
        (("allow", "allow", None), {"full_control": "deny"}, ("deny", "deny", "deny")),
        (("deny", None, None), {"full_control": "allow"}, ("allow", "allow", "allow")),
        (("deny", "deny", "deny"), {"read": "allow"}, ("allow", None, None)),
        (("deny", "deny", "deny"), {"change": "allow"}, ("allow", "allow", None)),
        (("deny", "deny", "deny"), {"full_control": ""}, ("deny", "deny", None)),
    ]

    @pytest.mark.parametrize("live,task,stored", PATCH_MATRIX)
    def test_update_matches_array_storage(self, live, task, stored):
        requested = {"read": None, "change": None, "full_control": None}
        requested.update(task)
        assert _share_rule_perms(self._perms(live), requested) == self._perms(stored)

    @pytest.mark.parametrize("live,task,stored", PATCH_MATRIX)
    def test_patch_body_is_the_single_moving_field(self, live, task, stored):
        """The body the module sends is the one field that was proven to
        move the ladder from live to stored."""
        current = self._perms(live)
        desired = self._perms(stored)
        if current == desired:
            pytest.skip("no change")
        assert _share_rule_patch(current, desired) == task

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_blank_on_unset_permission_is_idempotent(self, mock_loose_version):
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _share_module(full_control="")
        blade = _share_blade([_share_rule(full_control=None)])

        update_smb_share_policy(module, blade)

        blade.patch_smb_share_policies_rules.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_delete_missing_principal_rule_is_idempotent(self, mock_loose_version):
        """Deleting a principal rule that is already gone used to raise
        IndexError on the empty filter result."""
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _share_module()
        blade = _share_blade([])

        delete_smb_share_policy(module, blade)

        blade.delete_smb_share_policies_rules.assert_not_called()
        blade.delete_smb_share_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_delete_principal_rule(self, mock_loose_version):
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _share_module()
        blade = _share_blade([_share_rule()])

        delete_smb_share_policy(module, blade)

        blade.delete_smb_share_policies_rules.assert_called_once_with(
            ids=["10314f42-020d-7080-8013-000000000001"]
        )
        blade.delete_smb_share_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)


def _os_rule(effect="allow", actions=None, resources=None, ips=None, prefixes=None):
    """Build a mock SDK object store access policy rule."""
    rule = Mock()
    rule.name = "rule1"
    rule.effect = effect
    rule.actions = actions if actions is not None else ["s3:ListBucket"]
    rule.resources = resources if resources is not None else ["*"]
    rule.conditions = Mock()
    rule.conditions.source_ips = ips
    rule.conditions.s3_prefixes = prefixes
    rule.conditions.s3_delimiters = None
    return rule


def _os_module(**overrides):
    """Build a mock AnsibleModule for update_os_policy."""
    module = Mock()
    module.check_mode = False
    module.params = {
        "name": "ospol",
        "account": "acc",
        "rule": "rule1",
        "effect": None,
        "actions": ["s3:ListBucket"],
        "object_resources": ["*"],
        "source_ips": None,
        "s3_prefixes": None,
        "s3_delimiters": None,
        "ignore_enforcement": True,
        "user": None,
        "context": "",
    }
    module.params.update(overrides)
    module.fail_json = Mock(side_effect=SystemExit("fail_json called"))
    module.exit_json = Mock()
    return module


def _os_blade(rule):
    """Build a mock blade returning the given existing access policy rule."""
    blade = Mock()
    blade.get_versions.return_value.items = []

    rules_resp = Mock()
    rules_resp.status_code = 200
    rules_resp.total_item_count = 1
    rules_resp.items = [rule]
    blade.get_object_store_access_policies_rules.return_value = rules_resp

    ok = Mock()
    ok.status_code = 200
    blade.patch_object_store_access_policies_rules.return_value = ok
    return blade


class TestUpdateOsPolicyRule:
    """Regression tests for object store access policy rule updates (#29)."""

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_effect_change_patches_rule(self, mock_loose_version):
        import plugins.modules.purefb_policy as pol

        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _os_module(effect="deny")
        blade = _os_blade(_os_rule(effect="allow"))

        update_os_policy(module, blade)

        blade.patch_object_store_access_policies_rules.assert_called_once()
        # The PATCH body must be the request model: PolicyRuleObjectAccess (the
        # response model) drops `effect` from the body, so the effect change
        # never reached the array and the task was never idempotent.
        assert (
            blade.patch_object_store_access_policies_rules.call_args[1]["rule"]
            is pol.PolicyRuleObjectAccessPost.return_value
        )
        rule_kwargs = pol.PolicyRuleObjectAccessPost.call_args[1]
        assert rule_kwargs["effect"] == "deny"
        assert rule_kwargs["actions"] == ["s3:ListBucket"]
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_same_effect_is_idempotent(self, mock_loose_version):
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _os_module(effect="deny")
        blade = _os_blade(_os_rule(effect="deny"))

        update_os_policy(module, blade)

        blade.patch_object_store_access_policies_rules.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_unset_effect_keeps_live_effect(self, mock_loose_version):
        """effect has no argspec default, so a task that omits it must not
        flip a deny rule back to allow."""
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _os_module(effect=None)
        blade = _os_blade(_os_rule(effect="deny"))

        update_os_policy(module, blade)

        blade.patch_object_store_access_policies_rules.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_list_order_is_ignored(self, mock_loose_version):
        """The array may return lists in any order; only content matters."""
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _os_module(
            actions=["s3:ListBucket", "s3:GetObject"],
            source_ips=["198.51.100.0/24", "192.0.2.0/24"],
        )
        blade = _os_blade(
            _os_rule(
                actions=["s3:GetObject", "s3:ListBucket"],
                ips=["192.0.2.0/24", "198.51.100.0/24"],
            )
        )

        update_os_policy(module, blade)

        blade.patch_object_store_access_policies_rules.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)


def _net_rule(client="192.0.2.0/24", effect="allow", interfaces=None, index=2):
    rule = Mock()
    rule.name = "default-network-access-policy." + str(index)
    rule.client = client
    rule.effect = effect
    rule.interfaces = interfaces if interfaces is not None else ["management-ssh"]
    rule.index = index
    return rule


def _net_module(**overrides):
    module = Mock()
    module.check_mode = False
    module.params = {
        "name": "default-network-access-policy",
        "client": "192.0.2.0/24",
        "effect": None,
        "interfaces": ["management-ssh"],
        "before_rule": None,
        "enabled": True,
        "context": "",
    }
    module.params.update(overrides)
    module.fail_json = Mock(side_effect=SystemExit("fail_json called"))
    module.exit_json = Mock()
    return module


def _net_blade(rules):
    blade = Mock()
    blade.get_versions.return_value.items = []

    rules_resp = Mock()
    rules_resp.status_code = 200
    rules_resp.total_item_count = len(rules)
    rules_resp.items = rules
    blade.get_network_access_policies_rules.return_value = rules_resp

    ok = Mock()
    ok.status_code = 200
    blade.post_network_access_policies_rules.return_value = ok
    blade.patch_network_access_policies_rules.return_value = ok
    blade.delete_network_access_policies_rules.return_value = ok

    policy = Mock()
    policy.enabled = True
    policy_resp = Mock()
    policy_resp.items = [policy]
    blade.get_network_access_policies.return_value = policy_resp
    return blade


class TestNetworkAccessPolicy:
    """Network access policies can only have their rules managed (#11)."""

    def test_create_is_refused_with_clear_message(self):
        module = _net_module(name="new-net-policy")
        blade = _net_blade([])

        try:
            create_network_access_policy(module, blade)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "cannot be created" in module.fail_json.call_args[1]["msg"]
        # No SDK call is attempted (the old code called a non-existent
        # post_network_access_policies).
        assert not blade.method_calls

    def test_whole_policy_delete_is_refused(self):
        module = _net_module(client=None)
        blade = _net_blade([])

        try:
            delete_network_access_policy(module, blade)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "cannot be deleted" in module.fail_json.call_args[1]["msg"]
        blade.delete_network_access_policies_rules.assert_not_called()

    def test_rule_delete(self):
        module = _net_module()
        blade = _net_blade([_net_rule()])

        delete_network_access_policy(module, blade)

        blade.delete_network_access_policies_rules.assert_called_once_with(
            names=["default-network-access-policy.2"]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_rule_delete_is_idempotent(self):
        module = _net_module()
        blade = _net_blade([])

        delete_network_access_policy(module, blade)

        blade.delete_network_access_policies_rules.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_wildcard_client_filter_is_applied_client_side(self):
        """client='*' is a wildcard to the REST filter; only a rule whose
        client really is '*' may be deleted."""
        module = _net_module(client="*")
        blade = _net_blade([_net_rule(client="192.0.2.0/24")])

        delete_network_access_policy(module, blade)

        blade.delete_network_access_policies_rules.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_rule_create_defaults_effect_to_allow(self):
        import plugins.modules.purefb_policy as pol

        module = _net_module(effect=None)
        blade = _net_blade([])

        update_network_access_policy(module, blade)

        blade.post_network_access_policies_rules.assert_called_once()
        post_kwargs = blade.post_network_access_policies_rules.call_args[1]
        assert post_kwargs["policy_names"] == ["default-network-access-policy"]
        assert "context_names" not in post_kwargs
        rule_kwargs = pol.NetworkAccessPolicyRule.call_args[1]
        assert rule_kwargs["effect"] == "allow"
        module.exit_json.assert_called_once_with(changed=True)

    def test_interfaces_order_is_ignored(self):
        module = _net_module(interfaces=["snmp", "management-ssh"])
        blade = _net_blade(
            [_net_rule(interfaces=["management-ssh", "snmp"])],
        )

        update_network_access_policy(module, blade)

        blade.patch_network_access_policies_rules.assert_not_called()
        blade.patch_network_access_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_effect_change_patches_rule(self):
        import plugins.modules.purefb_policy as pol

        module = _net_module(effect="deny")
        blade = _net_blade([_net_rule(effect="allow")])

        update_network_access_policy(module, blade)

        blade.patch_network_access_policies_rules.assert_called_once()
        patch_kwargs = blade.patch_network_access_policies_rules.call_args[1]
        assert patch_kwargs["names"] == ["default-network-access-policy.2"]
        rule_kwargs = pol.NetworkAccessPolicyRule.call_args[1]
        assert rule_kwargs["effect"] == "deny"
        assert rule_kwargs["interfaces"] == ["management-ssh"]
        module.exit_json.assert_called_once_with(changed=True)


def _copy_module(policy_type="nfs", target="pol_copy", **overrides):
    module = Mock()
    module.check_mode = False
    module.params = {
        "name": "pol",
        "policy_type": policy_type,
        "target": target,
        "context": "",
    }
    module.params.update(overrides)
    module.fail_json = Mock(side_effect=SystemExit("fail_json called"))
    module.exit_json = Mock()
    return module


def _nfs_source(enabled=True):
    source = Mock()
    source.name = "pol"
    source.enabled = enabled
    return source


def _copy_blade(target_exists=False, rules=None):
    blade = Mock()
    blade.get_versions.return_value.items = []
    ok = Mock()
    ok.status_code = 200
    missing = Mock()
    missing.status_code = 400

    blade.get_nfs_export_policies.return_value = ok if target_exists else missing
    blade.post_nfs_export_policies.return_value = ok
    blade.patch_nfs_export_policies.return_value = ok
    blade.post_nfs_export_policies_rules.return_value = ok

    rules_resp = Mock()
    rules_resp.status_code = 200
    rules_resp.items = rules or []
    blade.get_nfs_export_policies_rules.return_value = rules_resp
    return blade


class TestCopyPolicy:
    """state=copy for non-access policy types (#13)."""

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_nfs_copy_creates_target_and_rules_in_order(self, mock_loose_version):
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        second = _existing_rule()
        second.client = "10.0.2.0/24"
        second.index = 2
        first = _existing_rule()
        first.client = "10.0.1.0/24"
        first.index = 1
        module = _copy_module()
        blade = _copy_blade(rules=[second, first])

        copy_policy(module, blade, _nfs_source())

        blade.post_nfs_export_policies.assert_called_once_with(names=["pol_copy"])
        blade.patch_nfs_export_policies.assert_not_called()
        blade.get_nfs_export_policies_rules.assert_called_once_with(
            policy_names=["pol"]
        )
        assert blade.post_nfs_export_policies_rules.call_count == 2
        assert all(
            call[1]["policy_names"] == ["pol_copy"]
            for call in blade.post_nfs_export_policies_rules.call_args_list
        )
        # Below REST 2.22 the rule bodies are plain dicts with string anon ids.
        bodies = [
            call[1]["rule"]
            for call in blade.post_nfs_export_policies_rules.call_args_list
        ]
        assert [body["client"] for body in bodies] == ["10.0.1.0/24", "10.0.2.0/24"]
        assert bodies[-1]["anonuid"] == "20000021"
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_disabled_source_gives_disabled_target(self, mock_loose_version):
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _copy_module()
        blade = _copy_blade()

        copy_policy(module, blade, _nfs_source(enabled=False))

        blade.patch_nfs_export_policies.assert_called_once()
        assert blade.patch_nfs_export_policies.call_args[1]["names"] == ["pol_copy"]
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_existing_target_is_refused(self, mock_loose_version):
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _copy_module()
        blade = _copy_blade(target_exists=True)

        try:
            copy_policy(module, blade, _nfs_source())
        except SystemExit:
            pass
        assert "already exists" in module.fail_json.call_args[1]["msg"]
        blade.post_nfs_export_policies.assert_not_called()

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_missing_source_is_refused(self, mock_loose_version):
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _copy_module()
        blade = _copy_blade()

        try:
            copy_policy(module, blade, None)
        except SystemExit:
            pass
        assert "does not exist" in module.fail_json.call_args[1]["msg"]
        blade.post_nfs_export_policies.assert_not_called()

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_missing_target_is_refused(self, mock_loose_version):
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _copy_module(target=None)
        blade = _copy_blade()

        try:
            copy_policy(module, blade, _nfs_source())
        except SystemExit:
            pass
        assert "target" in module.fail_json.call_args[1]["msg"]
        blade.post_nfs_export_policies.assert_not_called()

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_unsupported_type_is_refused(self, mock_loose_version):
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _copy_module(policy_type="access")
        blade = _copy_blade()

        try:
            copy_policy(module, blade, _nfs_source())
        except SystemExit:
            pass
        assert "not supported" in module.fail_json.call_args[1]["msg"]
        assert not blade.method_calls

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_check_mode_makes_no_changes(self, mock_loose_version):
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _copy_module()
        module.check_mode = True
        blade = _copy_blade()

        copy_policy(module, blade, _nfs_source())

        blade.post_nfs_export_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)


# ---------------------------------------------------------------------------
# WORM data policies: commit_mode and the autocommit configuration (REST 2.29)
# ---------------------------------------------------------------------------


def _as_dict(**kwargs):
    """Stand-in for an SDK model: the body is kept as a plain dict so the
    tests can assert exactly which fields were sent."""
    return dict(kwargs)


def worm_env(version="2.30"):
    """Patch the SDK models to dicts and use the real version/time helpers."""

    def decorator(fn):
        for target, new in (
            ("WormAutocommitConfig", _as_dict),
            ("WormDataPolicy", _as_dict),
            ("time_to_milliseconds", _real_ttm),
            ("TimeConversionError", _RealTimeConversionError),
            ("LooseVersion", _RealLooseVersion),
            ("get_rest_api_version", lambda blade: version),
        ):
            fn = patch("plugins.modules.purefb_policy." + target, new=new)(fn)
        return fn

    return decorator


WORM_PARAMS = {
    "name": "worm_pol",
    "policy_type": "worm",
    "state": "present",
    "enabled": True,
    "context": "",
    "rename": None,
    "before_rule": None,
    "target": None,
    "min_retention": "1m",
    "max_retention": "1d",
    "default_retention": "1h",
    "retention_lock": None,
    "commit_mode": None,
    "autocommit_delay_on": None,
    "autocommit_delay_period": None,
}

LEGACY_BODY = {
    "enabled": True,
    "retention_lock": None,
    "min_retention": 60000,
    "max_retention": 86400000,
    "default_retention": 3600000,
}


def _worm_module(**overrides):
    module = Mock()
    module.check_mode = False
    module.params = dict(WORM_PARAMS)
    module.params.update(overrides)
    module.fail_json = Mock(side_effect=SystemExit("fail_json called"))
    module.exit_json = Mock()
    return module


def _worm_policy(
    commit_mode="manual",
    delay_on="last_modification",
    delay_period=86400000,
    legacy=False,
):
    """A WORM policy as the SDK returns it (retentions in milliseconds).

    legacy=True models a policy read from an array below REST 2.29, which has
    neither commit_mode nor autocommit_config."""
    attrs = [
        "enabled",
        "mode",
        "min_retention",
        "max_retention",
        "default_retention",
        "retention_lock",
    ]
    if not legacy:
        attrs += ["commit_mode", "autocommit_config"]
    policy = Mock(spec=attrs)
    policy.enabled = True
    policy.mode = "compliance"
    policy.min_retention = 60000
    policy.max_retention = 86400000
    policy.default_retention = 3600000
    policy.retention_lock = "unlocked"
    if not legacy:
        policy.commit_mode = commit_mode
        policy.autocommit_config = Mock(spec=["delay_on", "delay_period"])
        policy.autocommit_config.delay_on = delay_on
        policy.autocommit_config.delay_period = delay_period
    return policy


def _worm_blade(policy=None):
    """A blade whose WORM policy lookup returns I(policy), or an error
    response without items (the SDK shape for a missing policy)."""
    blade = Mock()
    blade.get_versions.return_value.items = ["2.30"]
    blade.get_fleets.return_value.status_code = 400
    ok = Mock()
    ok.status_code = 200
    if policy is None:
        blade.get_worm_data_policies.return_value = _error_response(
            "Worm data policy does not exist."
        )
    else:
        found = Mock()
        found.status_code = 200
        found.items = [policy]
        blade.get_worm_data_policies.return_value = found
    blade.post_worm_data_policies.return_value = ok
    blade.patch_worm_data_policies.return_value = ok
    blade.delete_worm_data_policies.return_value = ok
    return blade


class TestWormAutocommitHelpers:
    @worm_env()
    def test_config_is_none_when_nothing_is_set(self):
        assert _worm_autocommit_config(None, None) is None

    @worm_env()
    def test_config_carries_only_the_set_fields(self):
        assert _worm_autocommit_config(None, 7200000) == {"delay_period": 7200000}
        assert _worm_autocommit_config("creation", None) == {"delay_on": "creation"}

    @worm_env()
    def test_params_convert_the_period_and_keep_zero(self):
        assert _worm_autocommit_params(
            _worm_module(commit_mode="autocommit", autocommit_delay_period="2h")
        ) == ("autocommit", None, 7200000)
        assert _worm_autocommit_params(_worm_module(autocommit_delay_period="0s")) == (
            None,
            None,
            0,
        )
        assert _worm_autocommit_params(_worm_module()) == (None, None, None)

    @worm_env()
    def test_params_fail_on_a_malformed_period(self):
        for period in ("1y", "2 hours", "abc"):
            module = _worm_module(autocommit_delay_period=period)

            with pytest.raises(SystemExit):
                _worm_autocommit_params(module)
            msg = module.fail_json.call_args[1]["msg"]
            assert period in msg
            assert "autocommit_delay_period" in msg

    @worm_env()
    def test_gate_fails_below_2_29_when_an_option_is_set(self):
        module = _worm_module(autocommit_delay_period="2h")

        with pytest.raises(SystemExit):
            _check_worm_autocommit_version(module, "2.28")
        assert "2.29" in module.fail_json.call_args[1]["msg"]

    @worm_env()
    def test_gate_passes_below_2_29_when_no_option_is_set(self):
        module = _worm_module()

        _check_worm_autocommit_version(module, "2.28")

        module.fail_json.assert_not_called()

    @worm_env()
    def test_gate_passes_at_2_29(self):
        module = _worm_module(commit_mode="hybrid")

        _check_worm_autocommit_version(module, "2.29")

        module.fail_json.assert_not_called()


class TestCreateWormPolicy:
    @worm_env()
    def test_body_without_autocommit_options_is_unchanged(self):
        module = _worm_module()
        blade = _worm_blade()

        create_worm_data_policy(module, blade)

        call = blade.post_worm_data_policies.call_args[1]
        assert call["names"] == ["worm_pol"]
        assert "context_names" not in call
        # the array requires retention_lock on creation; unlocked is the default
        assert call["policy"] == dict(
            LEGACY_BODY, mode="compliance", retention_lock="unlocked"
        )
        module.exit_json.assert_called_once_with(changed=True)

    @worm_env()
    def test_retention_lock_is_passed_through(self):
        module = _worm_module(retention_lock="locked")
        blade = _worm_blade()

        create_worm_data_policy(module, blade)

        policy = blade.post_worm_data_policies.call_args[1]["policy"]
        assert policy["retention_lock"] == "locked"

    @worm_env()
    def test_autocommit_options_are_sent(self):
        module = _worm_module(
            commit_mode="autocommit",
            autocommit_delay_on="creation",
            autocommit_delay_period="2h",
        )
        blade = _worm_blade()

        create_worm_data_policy(module, blade)

        policy = blade.post_worm_data_policies.call_args[1]["policy"]
        assert policy["commit_mode"] == "autocommit"
        assert policy["autocommit_config"] == {
            "delay_on": "creation",
            "delay_period": 7200000,
        }
        module.exit_json.assert_called_once_with(changed=True)

    @worm_env()
    def test_only_delay_period_sends_a_partial_config(self):
        module = _worm_module(autocommit_delay_period="2h")
        blade = _worm_blade()

        create_worm_data_policy(module, blade)

        policy = blade.post_worm_data_policies.call_args[1]["policy"]
        assert "commit_mode" not in policy
        assert policy["autocommit_config"] == {"delay_period": 7200000}

    @worm_env()
    def test_check_mode_posts_nothing(self):
        module = _worm_module(commit_mode="autocommit")
        module.check_mode = True
        blade = _worm_blade()

        create_worm_data_policy(module, blade)

        blade.post_worm_data_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @worm_env()
    def test_context_is_sent_when_set(self):
        module = _worm_module(context="fb-member")
        blade = _worm_blade()

        create_worm_data_policy(module, blade)

        call = blade.post_worm_data_policies.call_args[1]
        assert call["context_names"] == ["fb-member"]

    @worm_env()
    def test_api_error_fails_with_the_array_message(self):
        module = _worm_module(commit_mode="autocommit")
        blade = _worm_blade()
        blade.post_worm_data_policies.return_value.status_code = 400

        with pytest.raises(SystemExit):
            create_worm_data_policy(module, blade)
        assert "Failed to create" in module.fail_json.call_args[1]["msg"]
        module.exit_json.assert_not_called()


class TestUpdateWormPolicy:
    @worm_env()
    def test_same_values_make_no_patch(self):
        module = _worm_module(
            commit_mode="autocommit",
            autocommit_delay_on="creation",
            autocommit_delay_period="2h",
        )
        blade = _worm_blade(
            _worm_policy(
                commit_mode="autocommit", delay_on="creation", delay_period=7200000
            )
        )

        update_worm_data_policy(module, blade)

        blade.patch_worm_data_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @worm_env()
    def test_unset_options_never_patch(self):
        """A task without the new options leaves an autocommit policy alone."""
        module = _worm_module()
        blade = _worm_blade(
            _worm_policy(
                commit_mode="autocommit", delay_on="creation", delay_period=7200000
            )
        )

        update_worm_data_policy(module, blade)

        blade.patch_worm_data_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @worm_env()
    def test_delay_period_change_sends_the_whole_config(self):
        module = _worm_module(autocommit_delay_period="4h")
        blade = _worm_blade(
            _worm_policy(
                commit_mode="autocommit", delay_on="creation", delay_period=7200000
            )
        )

        update_worm_data_policy(module, blade)

        call = blade.patch_worm_data_policies.call_args[1]
        assert call["names"] == ["worm_pol"]
        assert "context_names" not in call
        assert call["policy"] == dict(
            LEGACY_BODY,
            retention_lock="unlocked",
            autocommit_config={"delay_on": "creation", "delay_period": 14400000},
        )
        module.exit_json.assert_called_once_with(changed=True)

    @worm_env()
    def test_delay_on_change_keeps_the_current_period(self):
        module = _worm_module(autocommit_delay_on="creation")
        blade = _worm_blade(_worm_policy())

        update_worm_data_policy(module, blade)

        policy = blade.patch_worm_data_policies.call_args[1]["policy"]
        assert policy["autocommit_config"] == {
            "delay_on": "creation",
            "delay_period": 86400000,
        }
        assert "commit_mode" not in policy

    @worm_env()
    def test_commit_mode_change_sends_only_commit_mode(self):
        module = _worm_module(commit_mode="hybrid")
        blade = _worm_blade(_worm_policy())

        update_worm_data_policy(module, blade)

        policy = blade.patch_worm_data_policies.call_args[1]["policy"]
        assert policy["commit_mode"] == "hybrid"
        assert "autocommit_config" not in policy
        module.exit_json.assert_called_once_with(changed=True)

    @worm_env()
    def test_legacy_policy_gets_a_legacy_body(self):
        """A policy from an array below REST 2.29 has no autocommit attributes;
        a retention change must still work and send no new fields."""
        module = _worm_module(default_retention="2h")
        blade = _worm_blade(_worm_policy(legacy=True))

        update_worm_data_policy(module, blade)

        policy = blade.patch_worm_data_policies.call_args[1]["policy"]
        assert policy == dict(
            LEGACY_BODY, retention_lock="unlocked", default_retention=7200000
        )
        module.exit_json.assert_called_once_with(changed=True)

    @worm_env()
    def test_check_mode_reports_the_change_without_a_patch(self):
        module = _worm_module(commit_mode="hybrid")
        module.check_mode = True
        blade = _worm_blade(_worm_policy())

        update_worm_data_policy(module, blade)

        blade.patch_worm_data_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @worm_env()
    def test_context_is_sent_on_read_and_patch(self):
        module = _worm_module(commit_mode="hybrid", context="fb-member")
        blade = _worm_blade(_worm_policy())

        update_worm_data_policy(module, blade)

        assert blade.get_worm_data_policies.call_args[1]["context_names"] == [
            "fb-member"
        ]
        assert blade.patch_worm_data_policies.call_args[1]["context_names"] == [
            "fb-member"
        ]

    @worm_env()
    def test_api_error_fails_with_the_array_message(self):
        module = _worm_module(commit_mode="hybrid")
        blade = _worm_blade(_worm_policy())
        blade.patch_worm_data_policies.return_value.status_code = 400

        with pytest.raises(SystemExit):
            update_worm_data_policy(module, blade)
        assert "Failed to update" in module.fail_json.call_args[1]["msg"]
        module.exit_json.assert_not_called()


class TestCopyWormPolicy:
    @worm_env()
    def test_copy_carries_commit_mode_and_autocommit(self):
        module = _copy_module(policy_type="worm")
        blade = _worm_blade()
        source = _worm_policy(
            commit_mode="autocommit", delay_on="creation", delay_period=7200000
        )

        copy_policy(module, blade, source)

        call = blade.post_worm_data_policies.call_args[1]
        assert call["names"] == ["pol_copy"]
        assert call["policy"] == dict(
            LEGACY_BODY,
            mode="compliance",
            retention_lock="unlocked",
            commit_mode="autocommit",
            autocommit_config={"delay_on": "creation", "delay_period": 7200000},
        )
        module.exit_json.assert_called_once_with(changed=True)

    @worm_env()
    def test_copy_of_a_legacy_source_sends_no_autocommit(self):
        module = _copy_module(policy_type="worm")
        blade = _worm_blade()

        copy_policy(module, blade, _worm_policy(legacy=True))

        policy = blade.post_worm_data_policies.call_args[1]["policy"]
        assert policy == dict(LEGACY_BODY, mode="compliance", retention_lock="unlocked")


class TestWormMainDispatch:
    """main() gates the autocommit options at REST 2.29 and no longer looks
    up WORM policy rules (an SDK method that does not exist)."""

    def _run(self, version, module, blade):
        import plugins.modules.purefb_policy as pol

        with patch("plugins.modules.purefb_policy.AnsibleModule") as ansible_module:
            ansible_module.return_value = module
            with patch("plugins.modules.purefb_policy.get_system", return_value=blade):
                with patch("plugins.modules.purefb_policy.HAS_PYTZ", True):
                    with patch("plugins.modules.purefb_policy.HAS_PYPURECLIENT", True):
                        with patch(
                            "plugins.modules.purefb_policy.get_rest_api_version",
                            return_value=version,
                        ):
                            with patch(
                                "plugins.modules.purefb_policy.LooseVersion",
                                new=_RealLooseVersion,
                            ):
                                with patch(
                                    "plugins.modules.purefb_policy.get_error_message",
                                    new=_array_message,
                                ):
                                    pol.main()

    @patch("plugins.modules.purefb_policy.create_worm_data_policy")
    def test_autocommit_option_is_rejected_below_2_29(self, mock_create):
        module = _worm_module(commit_mode="autocommit")
        blade = _worm_blade()

        with pytest.raises(SystemExit):
            self._run("2.28", module, blade)
        assert "2.29" in module.fail_json.call_args[1]["msg"]
        mock_create.assert_not_called()

    @patch("plugins.modules.purefb_policy.create_worm_data_policy")
    def test_autocommit_option_is_accepted_at_2_29(self, mock_create):
        module = _worm_module(commit_mode="autocommit")
        blade = _worm_blade()

        self._run("2.29", module, blade)

        mock_create.assert_called_once_with(module, blade)
        module.fail_json.assert_not_called()

    @patch("plugins.modules.purefb_policy.create_worm_data_policy")
    def test_legacy_task_still_creates_below_2_29(self, mock_create):
        module = _worm_module()
        blade = _worm_blade()

        self._run("2.28", module, blade)

        mock_create.assert_called_once_with(module, blade)
        module.fail_json.assert_not_called()

    @patch("plugins.modules.purefb_policy.update_worm_data_policy")
    def test_existing_policy_with_before_rule_updates_without_rule_lookup(
        self, mock_update
    ):
        module = _worm_module(before_rule=1)
        blade = _worm_blade(_worm_policy())

        self._run("2.30", module, blade)

        mock_update.assert_called_once_with(module, blade)
        assert not blade.get_worm_data_policies_rules.called
        module.fail_json.assert_not_called()


# A cut-down array catalogue (GET /object-store-access-policy-actions).
_CATALOGUE = ["s3:*", "s3:GetObject", "s3:PutObjectTagging", "s3:GetBucketPolicy"]

# Actions Purity//FB 4.8.8 publishes that the old static choices list lacked.
_NEWER_ACTIONS = [
    "s3:DeleteObjectTagging",
    "s3:DeleteObjectVersionTagging",
    "s3:GetBucketCORS",
    "s3:GetBucketPolicy",
    "s3:GetBucketPolicyStatus",
    "s3:GetBucketPublicAccessBlock",
    "s3:PutObjectTagging",
    "s3:PutObjectVersionTagging",
]


def _actions_module(actions, context=""):
    """Build a mock AnsibleModule for an access policy task with the given actions."""
    module = Mock()
    module.check_mode = False
    module.params = defaultdict(
        lambda: None,
        {
            "state": "present",
            "policy_type": "access",
            "name": "ospol",
            "account": "acc",
            "rule": "rule1",
            "actions": actions,
            "object_resources": ["*"],
            "ignore_enforcement": True,
            "context": context,
        },
    )
    module.fail_json = Mock(side_effect=SystemExit("fail_json called"))
    module.exit_json = Mock(side_effect=SystemExit("exit_json called"))
    return module


def _actions_blade(names=None, status=200):
    """Build a mock blade whose action catalogue holds the given names."""
    blade = Mock()
    res = Mock()
    res.status_code = status
    items = []
    for name in names or []:
        action = Mock()
        action.name = name
        items.append(action)
    res.items = items
    blade.get_object_store_access_policy_actions.return_value = res
    return blade


@patch("plugins.modules.purefb_policy.LooseVersion", RealLooseVersion)
class TestOsPolicyActions:
    """Rule actions are validated against the array's catalogue, not a frozen list."""

    def test_actions_in_the_array_catalogue_are_accepted(self):
        module = _actions_module(["s3:PutObjectTagging", "s3:GetBucketPolicy"])
        blade = _actions_blade(_CATALOGUE)

        _check_os_actions(module, blade, "2.30")

        module.fail_json.assert_not_called()
        module.warn.assert_not_called()
        blade.get_object_store_access_policy_actions.assert_called_once_with()

    def test_unknown_actions_are_named(self):
        module = _actions_module(["s3:PutObjectTagging", "s3:Bogus", "s3:Nope"])
        blade = _actions_blade(_CATALOGUE)

        with pytest.raises(SystemExit):
            _check_os_actions(module, blade, "2.30")

        msg = module.fail_json.call_args[1]["msg"]
        assert msg.startswith(
            "Unknown object store access policy action(s): s3:Bogus, s3:Nope. "
        )
        assert "Valid actions: s3:*, s3:GetBucketPolicy, s3:GetObject" in msg

    def test_catalogue_error_falls_back_to_the_built_in_list(self):
        """The built-in list knows the object tagging and bucket policy actions."""
        module = _actions_module(["s3:PutObjectTagging", "s3:GetBucketCORS"])
        blade = _actions_blade(status=400)

        _check_os_actions(module, blade, "2.30")

        module.fail_json.assert_not_called()
        module.warn.assert_called_once()
        warning = module.warn.call_args[0][0]
        assert warning.startswith(
            "Could not read the array's access policy action list, "
            "validating against the collection's built-in list. Error: "
        )

    def test_built_in_list_still_rejects_unknown_actions(self):
        module = _actions_module(["s3:GetObject", "s3:Bogus"])
        blade = _actions_blade(status=400)

        with pytest.raises(SystemExit):
            _check_os_actions(module, blade, "2.30")

        assert "s3:Bogus" in module.fail_json.call_args[1]["msg"]

    def test_empty_catalogue_falls_back_to_the_built_in_list(self):
        module = _actions_module(["s3:GetObject"])
        blade = _actions_blade([])

        valid = _valid_os_actions(module, blade, "2.30")

        assert valid == list(_OS_ACCESS_ACTIONS_FALLBACK)
        module.warn.assert_called_once()
        assert module.warn.call_args[0][0].endswith(
            "built-in list. The array returned an empty list."
        )

    def test_below_rest_2_2_never_asks_the_array(self):
        module = _actions_module(["s3:GetObject"])
        blade = _actions_blade(_CATALOGUE)

        _check_os_actions(module, blade, "2.1")

        blade.get_object_store_access_policy_actions.assert_not_called()
        module.fail_json.assert_not_called()
        module.warn.assert_not_called()

    def test_no_actions_means_no_lookup(self):
        module = _actions_module(None)
        blade = _actions_blade(_CATALOGUE)

        _check_os_actions(module, blade, "2.30")

        blade.get_object_store_access_policy_actions.assert_not_called()
        module.fail_json.assert_not_called()

    def test_fleet_context_is_sent_with_the_lookup(self):
        module = _actions_module(["s3:GetObject"], context="array-b")
        blade = _actions_blade(_CATALOGUE)

        _check_os_actions(module, blade, "2.30")

        blade.get_object_store_access_policy_actions.assert_called_once_with(
            context_names=["array-b"]
        )

    def test_context_is_not_sent_below_rest_2_17(self):
        module = _actions_module(["s3:GetObject"], context="array-b")
        blade = _actions_blade(_CATALOGUE)

        _check_os_actions(module, blade, "2.16")

        blade.get_object_store_access_policy_actions.assert_called_once_with()

    @pytest.mark.parametrize("action", _NEWER_ACTIONS)
    def test_built_in_list_knows_the_newer_actions(self, action):
        assert action in _OS_ACCESS_ACTIONS_FALLBACK


@patch("plugins.modules.purefb_policy.get_error_message", new=_array_message)
@patch("plugins.modules.purefb_policy.LooseVersion", RealLooseVersion)
@patch("plugins.modules.purefb_policy.HAS_PYTZ", True)
@patch("plugins.modules.purefb_policy.HAS_PYPURECLIENT", True)
@patch("plugins.modules.purefb_policy.get_rest_api_version", return_value="2.30")
@patch("plugins.modules.purefb_policy.purefb_argument_spec", return_value={})
@patch("plugins.modules.purefb_policy.get_system")
@patch("plugins.modules.purefb_policy.AnsibleModule")
class TestOsPolicyMainActions:
    """main() asks the array about the actions before any rule write."""

    @staticmethod
    def _blade(policy_exists):
        blade = _actions_blade(_CATALOGUE)
        blade.get_fleets.return_value.status_code = 400
        if policy_exists:
            blade.get_object_store_access_policies.return_value = _found(Mock())
        else:
            # A missing policy is an ErrorResponse: no ``items`` at all.
            blade.get_object_store_access_policies.return_value = _error_response(
                "Policy does not exist."
            )
        return blade

    def test_argspec_has_no_static_action_choices(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _actions_module(["s3:PutObjectTagging"])
        mock_ansible_module.return_value = module
        blade = self._blade(policy_exists=True)
        blade.get_object_store_access_policies_rules.return_value.status_code = 400
        blade.post_object_store_access_policies_rules.return_value.status_code = 200
        mock_get_system.return_value = blade

        with pytest.raises(SystemExit, match="exit_json"):
            main()

        spec = mock_ansible_module.call_args[0][0]
        assert spec["actions"] == {"type": "list", "elements": "str"}
        blade.get_object_store_access_policy_actions.assert_called_once()
        blade.post_object_store_access_policies_rules.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    def test_unknown_action_fails_before_any_write_on_update(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _actions_module(["s3:Bogus"])
        mock_ansible_module.return_value = module
        blade = self._blade(policy_exists=True)
        mock_get_system.return_value = blade

        with pytest.raises(SystemExit, match="fail_json"):
            main()

        assert "s3:Bogus" in module.fail_json.call_args[1]["msg"]
        blade.post_object_store_access_policies_rules.assert_not_called()
        blade.patch_object_store_access_policies_rules.assert_not_called()

    def test_unknown_action_fails_before_the_policy_is_created(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _actions_module(["s3:Bogus"])
        mock_ansible_module.return_value = module
        blade = self._blade(policy_exists=False)
        mock_get_system.return_value = blade

        with pytest.raises(SystemExit, match="fail_json"):
            main()

        assert "s3:Bogus" in module.fail_json.call_args[1]["msg"]
        blade.post_object_store_access_policies.assert_not_called()
        blade.post_object_store_access_policies_rules.assert_not_called()

    def test_delete_does_not_consult_the_catalogue(
        self, mock_ansible_module, mock_get_system, mock_spec, mock_version
    ):
        module = _actions_module(["s3:Bogus"])
        module.params["state"] = "absent"
        module.params["rule"] = None
        module.params["force_delete"] = False
        mock_ansible_module.return_value = module
        blade = self._blade(policy_exists=True)
        blade.get_object_store_access_policies_object_store_users.return_value.items = (
            []
        )
        blade.delete_object_store_access_policies.return_value.status_code = 200
        mock_get_system.return_value = blade

        with pytest.raises(SystemExit, match="exit_json"):
            main()

        blade.get_object_store_access_policy_actions.assert_not_called()
        blade.delete_object_store_access_policies.assert_called_once()


# ---------------------------------------------------------------------------
# Realm names, checked reads, rename decisions and check mode.
#
# A policy is in a realm when it is named realm::policy; an access policy is
# in the realm of its account (realm::account). The array matches names
# without regard to case and answers 400 "... does not exist." for a missing
# object, which is the only answer that means absent.
# ---------------------------------------------------------------------------


@pytest.fixture
def no_context():
    """Run a module function as on an array that takes no fleet context,
    with the array's own text as the error message."""
    with patch("plugins.modules.purefb_policy.LooseVersion") as loose_version:
        loose_version.return_value.__le__ = Mock(return_value=False)
        with patch(
            "plugins.modules.purefb_policy.get_error_message", new=_array_message
        ):
            yield


def _sdk_policy(name, policy_id):
    """A policy as the SDK returns it: the stored name and an id."""
    policy = Mock()
    policy.name = name
    policy.id = policy_id
    policy.enabled = True
    return policy


def _by_name(policies, missing="Policy does not exist."):
    """A lookup that answers like the array: 200 for a name it has (matched
    without regard to case), 400 "does not exist" for any other name."""

    def lookup(names=None, **kwargs):
        policy = policies.get(names[0].lower())
        if policy is None:
            return _error_response(missing)
        return _found(policy)

    return lookup


def _main_module(check_mode=False, **params):
    """A mock AnsibleModule for main(): every option unset unless given."""
    module = Mock()
    module.check_mode = check_mode
    module.params = defaultdict(
        lambda: None, {"state": "present", "enabled": True, "context": ""}
    )
    module.params.update(params)
    module.fail_json = Mock(side_effect=SystemExit("fail_json called"))
    module.exit_json = Mock()
    return module


def _main_blade():
    """A blade that is not a fleet member."""
    blade = Mock()
    blade.get_fleets.return_value = _error_response("Fleet does not exist.")
    return blade


def _run_main(module, blade, **replaced):
    """Run main() against the mocks. Keyword arguments replace module
    functions (the create, update, rename and delete entry points)."""
    import plugins.modules.purefb_policy as pol

    targets = {
        "AnsibleModule": Mock(return_value=module),
        "get_system": Mock(return_value=blade),
        "purefb_argument_spec": Mock(return_value={}),
        "get_rest_api_version": Mock(return_value="2.30"),
        "HAS_PYTZ": True,
        "HAS_PYPURECLIENT": True,
        "LooseVersion": _RealLooseVersion,
        "get_error_message": _array_message,
    }
    targets.update(replaced)
    patches = [patch.object(pol, name, new) for name, new in targets.items()]
    for item in patches:
        item.start()
    try:
        pol.main()
    finally:
        for item in reversed(patches):
            item.stop()


class TestRealmNameHelpers:
    @pytest.mark.parametrize(
        "name,realm,leaf",
        [
            ("pol", "", "pol"),
            ("rzaudit::pol", "rzaudit", "pol"),
            ("RZAUDIT::Pol", "RZAUDIT", "Pol"),
            (None, "", ""),
        ],
    )
    def test_realm_and_leaf(self, name, realm, leaf):
        import plugins.modules.purefb_policy as pol

        assert pol._realm_of(name) == realm
        assert pol._leaf(name) == leaf


@patch("plugins.modules.purefb_policy.get_error_message", new=_array_message)
class TestLookup:
    """Only "does not exist" means absent."""

    def test_found_item_is_returned(self):
        import plugins.modules.purefb_policy as pol

        policy = _sdk_policy("rzaudit::pol", "id-1")
        module = _main_module()
        assert (
            pol._lookup(module, _found(policy), "NFS export policy", "rzaudit::pol")
            is policy
        )

    def test_empty_answer_is_absent(self):
        import plugins.modules.purefb_policy as pol

        assert pol._lookup(_main_module(), _found(), "file system", "fs1") is None

    def test_does_not_exist_is_absent(self):
        import plugins.modules.purefb_policy as pol

        res = _error_response("NFS export policy does not exist.")
        module = _main_module()
        assert pol._lookup(module, res, "NFS export policy", "pol") is None
        module.fail_json.assert_not_called()

    def test_refused_read_fails_with_the_array_message(self):
        import plugins.modules.purefb_policy as pol

        res = _error_response("Operation not permitted.", status=403)
        module = _main_module()
        with pytest.raises(SystemExit):
            pol._lookup(module, res, "NFS export policy", "pol")
        msg = module.fail_json.call_args[1]["msg"]
        assert "Operation not permitted." in msg
        assert "NFS export policy pol" in msg


# policy_type, lookup, creator, the array's text for a missing policy
POLICY_TYPES = [
    ("snapshot", "get_policies", "create_snap_policy", "Policy does not exist."),
    (
        "nfs",
        "get_nfs_export_policies",
        "create_nfs_policy",
        "NFS export policy does not exist.",
    ),
    (
        "smb_client",
        "get_smb_client_policies",
        "create_smb_client_policy",
        "SMB client policy does not exist.",
    ),
    (
        "smb_share",
        "get_smb_share_policies",
        "create_smb_share_policy",
        "SMB share policy does not exist.",
    ),
    (
        "worm",
        "get_worm_data_policies",
        "create_worm_data_policy",
        "Worm data policy does not exist.",
    ),
    (
        "network",
        "get_network_access_policies",
        "create_network_access_policy",
        "Network access policy does not exist.",
    ),
    (
        "access",
        "get_object_store_access_policies",
        "create_os_policy",
        "Policy does not exist.",
    ),
]


@pytest.mark.parametrize("policy_type,getter,creator,missing", POLICY_TYPES)
class TestMainLookups:
    """main() takes a policy for absent only when the array says so."""

    @staticmethod
    def _module(policy_type, name="rzaudit::pol"):
        params = {"policy_type": policy_type, "name": name}
        if policy_type == "access":
            params.update(name="pol", account="rzaudit::acc")
        if policy_type == "network":
            params.update(
                name="default-network-access-policy", interfaces=["management-ssh"]
            )
        return _main_module(**params)

    def test_refused_read_is_not_taken_for_absent(
        self, policy_type, getter, creator, missing
    ):
        module = self._module(policy_type)
        blade = _main_blade()
        getattr(blade, getter).return_value = _error_response(
            "Operation not permitted.", status=403
        )
        create = Mock()

        with pytest.raises(SystemExit):
            _run_main(module, blade, **{creator: create})

        create.assert_not_called()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Operation not permitted." in msg
        assert "cannot be created" not in msg

    def test_missing_policy_is_created(self, policy_type, getter, creator, missing):
        module = self._module(policy_type)
        blade = _main_blade()
        getattr(blade, getter).return_value = _error_response(missing)
        create = Mock()

        _run_main(module, blade, **{creator: create})

        create.assert_called_once_with(module, blade)
        module.fail_json.assert_not_called()

    def test_absent_of_a_missing_policy_is_unchanged(
        self, policy_type, getter, creator, missing
    ):
        module = self._module(policy_type)
        module.params["state"] = "absent"
        blade = _main_blade()
        getattr(blade, getter).return_value = _error_response(missing)

        _run_main(module, blade)

        module.fail_json.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)


RENAME_TYPES = [
    ("nfs", "get_nfs_export_policies", "rename_nfs_policy"),
    ("smb_client", "get_smb_client_policies", "rename_smb_client_policy"),
    ("smb_share", "get_smb_share_policies", "rename_smb_share_policy"),
    ("snapshot", "get_policies", "rename_snap_policy"),
]


@pytest.mark.parametrize("policy_type,getter,renamer", RENAME_TYPES)
class TestRenameInMain:
    """A rename is settled in main(), before the check-mode branch: it never
    crosses a realm boundary, and it reports ok only when nothing is left
    to rename."""

    @staticmethod
    def _run(policy_type, getter, renamer, policies, check_mode=False, **params):
        module = _main_module(check_mode=check_mode, policy_type=policy_type, **params)
        blade = _main_blade()
        lookup = getattr(blade, getter)
        lookup.side_effect = _by_name(policies)
        rename = Mock()
        try:
            _run_main(module, blade, **{renamer: rename})
            failed = False
        except SystemExit:
            failed = True
        return module, lookup, rename, failed

    def test_bare_new_name_stays_in_the_realm(self, policy_type, getter, renamer):
        policies = {"rzaudit::pol": _sdk_policy("rzaudit::pol", "id-1")}

        module, lookup, rename, failed = self._run(
            policy_type, getter, renamer, policies, name="rzaudit::pol", rename="pol2"
        )

        assert not failed
        assert module.params["rename"] == "rzaudit::pol2"
        assert [call[1]["names"] for call in lookup.call_args_list] == [
            ["rzaudit::pol"],
            ["rzaudit::pol2"],
        ]
        rename.assert_called_once()

    def test_new_name_takes_the_realm_as_name_spells_it(
        self, policy_type, getter, renamer
    ):
        """The array compares the realm of the two names as written."""
        policies = {"rzaudit::pol": _sdk_policy("rzaudit::pol", "id-1")}

        module, lookup, rename, failed = self._run(
            policy_type,
            getter,
            renamer,
            policies,
            name="RZAUDIT::pol",
            rename="rzaudit::pol2",
        )

        assert not failed
        assert module.params["rename"] == "RZAUDIT::pol2"
        rename.assert_called_once()

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize(
        "name,new_name",
        [
            ("rzaudit::pol", "other::pol2"),
            ("pol", "rzaudit::pol2"),
        ],
    )
    def test_rename_across_a_realm_boundary_is_refused(
        self, policy_type, getter, renamer, name, new_name, check_mode
    ):
        policies = {name.lower(): _sdk_policy(name, "id-1")}

        module, lookup, rename, failed = self._run(
            policy_type,
            getter,
            renamer,
            policies,
            check_mode=check_mode,
            name=name,
            rename=new_name,
        )

        assert failed
        assert "into, out of or between realms" in module.fail_json.call_args[1]["msg"]
        # decided from the names alone: nothing read, nothing written
        lookup.assert_not_called()
        rename.assert_not_called()

    def test_array_level_namesake_is_not_the_new_name(
        self, policy_type, getter, renamer
    ):
        """A policy outside the realm that has the bare new name is another
        policy: the realm policy is still to be renamed."""
        policies = {
            "rzaudit::pol": _sdk_policy("rzaudit::pol", "id-1"),
            "pol2": _sdk_policy("pol2", "id-2"),
        }

        module, lookup, rename, failed = self._run(
            policy_type, getter, renamer, policies, name="rzaudit::pol", rename="pol2"
        )

        assert not failed
        rename.assert_called_once()

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_neither_name_exists_fails(self, policy_type, getter, renamer, check_mode):
        module, lookup, rename, failed = self._run(
            policy_type,
            getter,
            renamer,
            {},
            check_mode=check_mode,
            name="rzaudit::pol",
            rename="pol2",
        )

        assert failed
        msg = module.fail_json.call_args[1]["msg"]
        assert "rzaudit::pol does not exist" in msg
        rename.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_new_name_of_another_policy_fails(
        self, policy_type, getter, renamer, check_mode
    ):
        policies = {
            "rzaudit::pol": _sdk_policy("rzaudit::pol", "id-1"),
            "rzaudit::pol2": _sdk_policy("rzaudit::pol2", "id-2"),
        }

        module, lookup, rename, failed = self._run(
            policy_type,
            getter,
            renamer,
            policies,
            check_mode=check_mode,
            name="rzaudit::pol",
            rename="pol2",
        )

        assert failed
        assert "rzaudit::pol2 already exists" in module.fail_json.call_args[1]["msg"]
        rename.assert_not_called()

    def test_new_name_that_differs_only_in_case_fails(
        self, policy_type, getter, renamer
    ):
        """The array finds the policy itself under the new name and does not
        rename a policy to its own name."""
        policies = {"pol": _sdk_policy("pol", "id-1")}

        module, lookup, rename, failed = self._run(
            policy_type, getter, renamer, policies, name="pol", rename="POL"
        )

        assert failed
        assert "only in case" in module.fail_json.call_args[1]["msg"]
        rename.assert_not_called()

    def test_already_renamed_is_unchanged(self, policy_type, getter, renamer):
        policies = {"rzaudit::pol2": _sdk_policy("rzaudit::pol2", "id-1")}

        module, lookup, rename, failed = self._run(
            policy_type, getter, renamer, policies, name="rzaudit::pol", rename="pol2"
        )

        assert not failed
        rename.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_own_name_is_unchanged(self, policy_type, getter, renamer):
        policies = {"rzaudit::pol": _sdk_policy("rzaudit::pol", "id-1")}

        module, lookup, rename, failed = self._run(
            policy_type, getter, renamer, policies, name="rzaudit::pol", rename="pol"
        )

        assert not failed
        rename.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_array_level_rename_is_sent(self, policy_type, getter, renamer):
        policies = {"pol": _sdk_policy("pol", "id-1")}

        module, lookup, rename, failed = self._run(
            policy_type, getter, renamer, policies, name="pol", rename="pol2"
        )

        assert not failed
        assert module.params["rename"] == "pol2"
        rename.assert_called_once()


class TestWormRenameInMain:
    def test_rename_of_a_missing_policy_fails(self):
        module = _main_module(policy_type="worm", name="rzaudit::worm", rename="w2")
        blade = _main_blade()
        blade.get_worm_data_policies.side_effect = _by_name({})
        rename = Mock()

        with pytest.raises(SystemExit):
            _run_main(module, blade, rename_worm_data_policy=rename)

        assert "does not exist" in module.fail_json.call_args[1]["msg"]
        rename.assert_not_called()

    def test_rename_of_an_existing_policy_still_warns(self):
        module = _main_module(policy_type="worm", name="rzaudit::worm", rename="w2")
        blade = _main_blade()
        blade.get_worm_data_policies.side_effect = _by_name(
            {"rzaudit::worm": _sdk_policy("rzaudit::worm", "id-1")}
        )
        rename = Mock()

        _run_main(module, blade, rename_worm_data_policy=rename)

        rename.assert_called_once_with(module)
        module.fail_json.assert_not_called()


class TestSnapMemberRealmsInMain:
    """A snapshot policy and its members share a scope. A member of another
    scope is refused before anything is read, so no empty policy is left
    behind and check mode agrees with the real run."""

    @staticmethod
    def _run(check_mode=False, **params):
        module = _main_module(check_mode=check_mode, policy_type="snapshot", **params)
        blade = _main_blade()
        blade.get_policies.side_effect = _by_name({})
        create = Mock()
        try:
            _run_main(module, blade, create_snap_policy=create)
            failed = False
        except SystemExit:
            failed = True
        return module, blade, create, failed

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("option", ["filesystem", "replica_link"])
    @pytest.mark.parametrize(
        "name,member",
        [
            ("rzaudit::snap", "fs1"),
            ("rzaudit::snap", "other::fs1"),
            ("snap", "rzaudit::fs1"),
        ],
    )
    def test_member_of_another_scope_is_refused(self, name, member, option, check_mode):
        module, blade, create, failed = self._run(
            check_mode=check_mode, name=name, **{option: [member]}
        )

        assert failed
        msg = module.fail_json.call_args[1]["msg"]
        assert member in msg and name in msg
        assert "same realm" in msg
        blade.get_policies.assert_not_called()
        create.assert_not_called()

    @pytest.mark.parametrize("option", ["filesystem", "replica_link"])
    @pytest.mark.parametrize(
        "name,member",
        [
            ("rzaudit::snap", "fs1"),
            ("rzaudit::snap", "other::fs1"),
            ("snap", "rzaudit::fs1"),
        ],
    )
    def test_absent_with_a_member_of_another_scope_is_not_refused(
        self, name, member, option
    ):
        """Only an attach can cross a realm boundary. A member of another
        scope cannot be attached to the policy, so state=absent has nothing
        to detach and nothing to refuse."""
        module, blade, create, failed = self._run(
            name=name, state="absent", **{option: [member]}
        )

        assert not failed
        module.fail_json.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_absent_hands_a_member_of_another_scope_to_the_detach_path(self):
        """With an existing policy the member list is still reconciled."""
        module = _main_module(
            policy_type="snapshot",
            name="rzaudit::snap",
            state="absent",
            filesystem=["fs1"],
        )
        blade = _main_blade()
        blade.get_policies.side_effect = _by_name(
            {"rzaudit::snap": _sdk_policy("rzaudit::snap", "id-1")}
        )
        update = Mock()
        delete = Mock()

        _run_main(module, blade, update_snap_policy=update, delete_snap_policy=delete)

        module.fail_json.assert_not_called()
        update.assert_called_once_with(module, blade)
        delete.assert_not_called()

    @pytest.mark.parametrize(
        "name,member",
        [
            ("snap", "fs1"),
            ("rzaudit::snap", "rzaudit::fs1"),
            ("rzaudit::snap", "RZAUDIT::fs1"),
        ],
    )
    def test_member_of_the_same_scope_is_accepted(self, name, member):
        module, blade, create, failed = self._run(name=name, filesystem=[member])

        assert not failed
        create.assert_called_once_with(module, blade)


def _snap_create_module(check_mode=False, **overrides):
    module = _snap_module()
    module.check_mode = check_mode
    module.params.update(overrides)
    return module


def _replica_link_obj(local, remote):
    """A FileSystemReplicaLink as GET /file-system-replica-links returns it."""
    link = Mock(spec=["id", "local_file_system", "remote", "remote_file_system"])
    link.local_file_system.name = local
    link.remote.name = remote
    return link


def _fs_member(name, policy="daily_snap_policy"):
    """A member as GET /policies/file-systems returns it."""
    member = Mock(spec=["member", "policy"])
    member.member.name = name
    member.policy.name = policy
    return member


def _link_member(local, remote, policy="daily_snap_policy"):
    """A member as GET /policies/file-system-replica-links returns it."""
    member = Mock(spec=["context", "member", "policy", "link"])
    member.member.name = local
    member.policy.name = policy
    member.link = Mock(spec=["local_file_system", "remote", "remote_file_system"])
    member.link.local_file_system.name = local
    member.link.remote.name = remote
    return member


@pytest.mark.usefixtures("no_context")
class TestCreateSnapPolicyMembers:
    """Members are looked up before the policy is created."""

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_missing_file_system_fails_before_the_policy_is_created(self, check_mode):
        module = _snap_create_module(
            check_mode=check_mode,
            name="rzaudit::snap",
            filesystem=["rzaudit::nofs"],
        )
        blade = Mock()
        blade.get_file_systems.return_value = _error_response(
            "File system does not exist."
        )

        with pytest.raises(SystemExit):
            create_snap_policy(module, blade)

        msg = module.fail_json.call_args[1]["msg"]
        assert "rzaudit::nofs" in msg and "does not exist" in msg
        blade.post_policies.assert_not_called()
        blade.post_policies_file_systems.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_file_system_without_a_replica_link_fails_before_the_policy_is_created(
        self, check_mode
    ):
        """A file system without a replica link is a 200 with no items."""
        module = _snap_create_module(
            check_mode=check_mode, name="snap", replica_link=["fs1"]
        )
        blade = Mock()
        blade.get_file_system_replica_links.return_value = _found()

        with pytest.raises(SystemExit):
            create_snap_policy(module, blade)

        assert "has no replica link" in module.fail_json.call_args[1]["msg"]
        blade.post_policies.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_destroyed_file_system_fails_before_the_policy_is_created(self, check_mode):
        """The array answers a read of a destroyed file system that asks
        for live ones with an error of its own."""
        module = _snap_create_module(
            check_mode=check_mode, name="snap", filesystem=["fs1"]
        )
        blade = Mock()
        blade.get_file_systems.return_value = _error_response(
            "File system has been destroyed."
        )

        with pytest.raises(SystemExit):
            create_snap_policy(module, blade)

        blade.get_file_systems.assert_called_once_with(names=["fs1"], destroyed=False)
        msg = module.fail_json.call_args[1]["msg"]
        assert "fs1" in msg and "File system has been destroyed." in msg
        blade.post_policies.assert_not_called()

    def test_refused_file_system_read_fails_with_the_array_message(self):
        module = _snap_create_module(name="rzaudit::snap", filesystem=["rzaudit::fs1"])
        blade = Mock()
        blade.get_file_systems.return_value = _error_response(
            "Operation not permitted.", status=403
        )

        with pytest.raises(SystemExit):
            create_snap_policy(module, blade)

        assert "Operation not permitted." in module.fail_json.call_args[1]["msg"]
        blade.post_policies.assert_not_called()

    def test_members_are_attached_after_the_policy_is_created(self):
        module = _snap_create_module(
            name="rzaudit::snap",
            filesystem=["rzaudit::fs1"],
            replica_link=["rzaudit::fs2"],
        )
        blade = Mock()
        blade.get_file_systems.return_value = _found(Mock())
        blade.get_file_system_replica_links.return_value = _found(
            _replica_link_obj("rzaudit::fs2", "remote-array")
        )
        for call in (
            blade.post_policies,
            blade.post_policies_file_systems,
            blade.post_policies_file_system_replica_links,
        ):
            call.return_value.status_code = 200

        create_snap_policy(module, blade)

        blade.get_file_system_replica_links.assert_called_once_with(
            local_file_system_names=["rzaudit::fs2"]
        )
        blade.post_policies_file_systems.assert_called_once_with(
            policy_names=["rzaudit::snap"], member_names=["rzaudit::fs1"]
        )
        blade.post_policies_file_system_replica_links.assert_called_once_with(
            policy_names=["rzaudit::snap"],
            local_file_system_names=["rzaudit::fs2"],
            remote_names=["remote-array"],
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_check_mode_reads_the_members_and_writes_nothing(self):
        module = _snap_create_module(
            check_mode=True, name="snap", filesystem=["fs1"], replica_link=["fs2"]
        )
        blade = Mock()
        blade.get_file_systems.return_value = _found(Mock())
        blade.get_file_system_replica_links.return_value = _found(
            _replica_link_obj("fs2", "remote-array")
        )

        create_snap_policy(module, blade)

        blade.get_file_systems.assert_called_once()
        blade.get_file_system_replica_links.assert_called_once()
        blade.post_policies.assert_not_called()
        blade.post_policies_file_systems.assert_not_called()
        blade.post_policies_file_system_replica_links.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)


def _member_blade(file_systems=(), links=()):
    """A blade for update_snap_policy whose policy has the given members.
    Like the SDK client, it has no get_file_systems_replica_links."""
    blade = _snap_blade(_snap_rule())
    del blade.get_file_systems_replica_links
    blade.get_policies_file_systems.return_value = _found(*file_systems)
    blade.get_policies_file_system_replica_links.return_value = _found(*links)
    blade.get_file_systems.return_value = _found(Mock())
    for call in (
        blade.post_policies_file_systems,
        blade.delete_policies_file_systems,
        blade.post_policies_file_system_replica_links,
        blade.delete_policies_file_system_replica_links,
    ):
        call.return_value.status_code = 200
    return blade


def _member_module(check_mode=False, **overrides):
    """An update_snap_policy task that only names members."""
    module = _snap_module()
    module.check_mode = check_mode
    module.params.update(overrides)
    return module


@pytest.mark.usefixtures("no_context")
class TestSnapPolicyFileSystemMembers:
    def test_check_mode_attach_writes_nothing(self):
        module = _member_module(
            check_mode=True, name="rzaudit::snap", filesystem=["rzaudit::fs1"]
        )
        blade = _member_blade()

        update_snap_policy(module, blade)

        blade.get_file_systems.assert_called_once()
        blade.post_policies_file_systems.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_check_mode_detach_writes_nothing(self):
        module = _member_module(
            check_mode=True,
            name="rzaudit::snap",
            state="absent",
            filesystem=["rzaudit::fs1"],
        )
        blade = _member_blade(file_systems=[_fs_member("rzaudit::fs1")])

        update_snap_policy(module, blade)

        blade.delete_policies_file_systems.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_attach(self):
        module = _member_module(name="rzaudit::snap", filesystem=["rzaudit::fs1"])
        blade = _member_blade()

        update_snap_policy(module, blade)

        blade.post_policies_file_systems.assert_called_once_with(
            policy_names=["rzaudit::snap"], member_names=["rzaudit::fs1"]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_detach(self):
        module = _member_module(
            name="rzaudit::snap", state="absent", filesystem=["rzaudit::fs1"]
        )
        blade = _member_blade(file_systems=[_fs_member("rzaudit::fs1")])

        update_snap_policy(module, blade)

        blade.delete_policies_file_systems.assert_called_once_with(
            policy_names=["rzaudit::snap"], member_names=["rzaudit::fs1"]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_member_in_another_case_is_already_attached(self):
        """The array returns the stored spelling of a member."""
        module = _member_module(name="rzaudit::snap", filesystem=["RZAUDIT::FS1"])
        blade = _member_blade(file_systems=[_fs_member("rzaudit::fs1")])

        update_snap_policy(module, blade)

        blade.post_policies_file_systems.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_member_in_another_case_is_detached(self):
        module = _member_module(
            name="rzaudit::snap", state="absent", filesystem=["RZAUDIT::FS1"]
        )
        blade = _member_blade(file_systems=[_fs_member("rzaudit::fs1")])

        update_snap_policy(module, blade)

        blade.delete_policies_file_systems.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    def test_namesake_outside_the_realm_is_not_detached(self):
        """The member of a policy in a realm is realm::filesystem. The same
        name without the realm is another file system: nothing is detached."""
        module = _member_module(
            name="rzaudit::snap", state="absent", filesystem=["fs1"]
        )
        blade = _member_blade(file_systems=[_fs_member("rzaudit::fs1")])

        update_snap_policy(module, blade)

        blade.delete_policies_file_systems.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_same_member_twice_is_attached_once(self):
        module = _member_module(name="snap", filesystem=["fs1", "FS1"])
        blade = _member_blade()

        update_snap_policy(module, blade)

        blade.post_policies_file_systems.assert_called_once()

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_missing_file_system_fails(self, check_mode):
        module = _member_module(check_mode=check_mode, name="snap", filesystem=["fs1"])
        blade = _member_blade()
        blade.get_file_systems.return_value = _error_response(
            "File system does not exist."
        )

        with pytest.raises(SystemExit):
            update_snap_policy(module, blade)

        assert "fs1" in module.fail_json.call_args[1]["msg"]
        blade.post_policies_file_systems.assert_not_called()

    def test_refused_member_read_fails_with_the_array_message(self):
        module = _member_module(name="snap", filesystem=["fs1"])
        blade = _member_blade()
        blade.get_policies_file_systems.return_value = _error_response(
            "Operation not permitted.", status=403
        )

        with pytest.raises(SystemExit):
            update_snap_policy(module, blade)

        assert "Operation not permitted." in module.fail_json.call_args[1]["msg"]


@pytest.mark.usefixtures("no_context")
class TestSnapPolicyReplicaLinkMembers:
    """A replica link is addressed by its local file system and its remote."""

    def test_attach_looks_the_link_up_and_names_its_remote(self):
        module = _member_module(name="snap", replica_link=["fs1"])
        blade = _member_blade()
        blade.get_file_system_replica_links.return_value = _found(
            _replica_link_obj("fs1", "remote-array")
        )

        update_snap_policy(module, blade)

        blade.get_file_system_replica_links.assert_called_once_with(
            local_file_system_names=["fs1"]
        )
        blade.post_policies_file_system_replica_links.assert_called_once_with(
            policy_names=["snap"],
            local_file_system_names=["fs1"],
            remote_names=["remote-array"],
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_check_mode_attach_writes_nothing(self):
        module = _member_module(check_mode=True, name="snap", replica_link=["fs1"])
        blade = _member_blade()
        blade.get_file_system_replica_links.return_value = _found(
            _replica_link_obj("fs1", "remote-array")
        )

        update_snap_policy(module, blade)

        blade.post_policies_file_system_replica_links.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_attached_link_is_unchanged(self):
        module = _member_module(name="rzaudit::snap", replica_link=["RZAUDIT::fs1"])
        blade = _member_blade(links=[_link_member("rzaudit::fs1", "remote-array")])

        update_snap_policy(module, blade)

        blade.get_file_system_replica_links.assert_not_called()
        blade.post_policies_file_system_replica_links.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_detach_names_the_remote_of_the_link(self):
        module = _member_module(name="snap", state="absent", replica_link=["fs1"])
        blade = _member_blade(links=[_link_member("fs1", "remote-array")])

        update_snap_policy(module, blade)

        blade.delete_policies_file_system_replica_links.assert_called_once_with(
            policy_names=["snap"],
            local_file_system_names=["fs1"],
            remote_names=["remote-array"],
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_check_mode_detach_writes_nothing(self):
        module = _member_module(
            check_mode=True, name="snap", state="absent", replica_link=["fs1"]
        )
        blade = _member_blade(links=[_link_member("fs1", "remote-array")])

        update_snap_policy(module, blade)

        blade.delete_policies_file_system_replica_links.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_detach_of_a_link_that_is_not_attached_is_unchanged(self):
        module = _member_module(name="snap", state="absent", replica_link=["fs1"])
        blade = _member_blade()

        update_snap_policy(module, blade)

        blade.delete_policies_file_system_replica_links.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_file_system_without_a_replica_link_fails(self, check_mode):
        module = _member_module(
            check_mode=check_mode, name="snap", replica_link=["fs1"]
        )
        blade = _member_blade()
        blade.get_file_system_replica_links.return_value = _found()

        with pytest.raises(SystemExit):
            update_snap_policy(module, blade)

        assert "has no replica link" in module.fail_json.call_args[1]["msg"]
        blade.post_policies_file_system_replica_links.assert_not_called()

    def test_missing_file_system_fails(self):
        module = _member_module(name="snap", replica_link=["fs1"])
        blade = _member_blade()
        blade.get_file_system_replica_links.return_value = _error_response(
            "File system does not exist."
        )

        with pytest.raises(SystemExit):
            update_snap_policy(module, blade)

        assert "fs1" in module.fail_json.call_args[1]["msg"]

    def test_member_without_link_details_is_matched_by_its_reference(self):
        """The remote is then read from the replica link itself."""
        import plugins.modules.purefb_policy as pol

        member = Mock(spec=["member", "policy"])
        member.member.name = "fs1"
        assert pol._member_link(member) == ("fs1", None)

        module = _member_module(name="snap", state="absent", replica_link=["fs1"])
        blade = _member_blade(links=[member])
        blade.get_file_system_replica_links.return_value = _found(
            _replica_link_obj("fs1", "remote-array")
        )

        update_snap_policy(module, blade)

        blade.delete_policies_file_system_replica_links.assert_called_once_with(
            policy_names=["snap"],
            local_file_system_names=["fs1"],
            remote_names=["remote-array"],
        )


@pytest.mark.usefixtures("no_context")
class TestSmbShareRuleInRealm:
    """A share rule is addressed by its id for every administrator."""

    def test_rule_of_a_realm_policy_is_patched_by_id(self):
        module = _share_module(
            name="rzaudit::share_pol",
            read="allow",
            change="allow",
            full_control="allow",
        )
        blade = _share_blade([_share_rule()])

        update_smb_share_policy(module, blade)

        blade.get_smb_share_policies_rules.assert_called_once_with(
            policy_names=["rzaudit::share_pol"], filter="principal='Everyone'"
        )
        call_kwargs = blade.patch_smb_share_policies_rules.call_args[1]
        assert call_kwargs["ids"] == ["10314f42-020d-7080-8013-000000000001"]
        assert "names" not in call_kwargs and "policy_names" not in call_kwargs
        module.exit_json.assert_called_once_with(changed=True)

    def test_rule_of_a_realm_policy_is_deleted_by_id(self):
        module = _share_module(name="rzaudit::share_pol")
        blade = _share_blade([_share_rule()])

        delete_smb_share_policy(module, blade)

        blade.delete_smb_share_policies_rules.assert_called_once_with(
            ids=["10314f42-020d-7080-8013-000000000001"]
        )
        blade.delete_smb_share_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_check_mode_sends_no_rule_write(self):
        module = _share_module(name="rzaudit::share_pol", full_control="allow")
        module.check_mode = True
        blade = _share_blade([_share_rule()])

        update_smb_share_policy(module, blade)

        blade.patch_smb_share_policies_rules.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)


@pytest.mark.usefixtures("no_context")
class TestSmbPolicyCreateNeedsItsRule:
    """A new SMB policy is created with its first rule: without the rule
    field nothing is created, in check mode too."""

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_share_policy_without_principal_creates_nothing(self, check_mode):
        module = _share_module(name="rzaudit::share_pol", principal=None)
        module.check_mode = check_mode
        blade = Mock()

        with pytest.raises(SystemExit):
            create_smb_share_policy(module, blade)

        assert "principal is required" in module.fail_json.call_args[1]["msg"]
        blade.post_smb_share_policies.assert_not_called()
        module.exit_json.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_client_policy_without_client_creates_nothing(self, check_mode):
        module = _share_module(name="rzaudit::client_pol", client=None)
        module.check_mode = check_mode
        blade = Mock()

        with pytest.raises(SystemExit):
            create_smb_client_policy(module, blade)

        assert "client is required" in module.fail_json.call_args[1]["msg"]
        blade.post_smb_client_policies.assert_not_called()
        module.exit_json.assert_not_called()

    def test_share_policy_with_principal_is_created_with_its_rule(self):
        module = _share_module(name="rzaudit::share_pol", read="allow")
        blade = Mock()
        blade.post_smb_share_policies.return_value.status_code = 200
        blade.post_smb_share_policies_rules.return_value.status_code = 200

        create_smb_share_policy(module, blade)

        blade.post_smb_share_policies.assert_called_once_with(
            names=["rzaudit::share_pol"]
        )
        blade.post_smb_share_policies_rules.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize(
        "perms",
        [
            {},
            {"read": "", "change": "", "full_control": ""},
        ],
    )
    def test_share_policy_whose_rule_grants_nothing_creates_nothing(
        self, perms, check_mode
    ):
        """A principal without a permission is no rule: the array has no
        such rule, so the policy is not created for it either."""
        module = _share_module(name="rzaudit::share_pol", **perms)
        module.check_mode = check_mode
        blade = Mock()

        with pytest.raises(SystemExit):
            create_smb_share_policy(module, blade)

        assert "at least read" in module.fail_json.call_args[1]["msg"]
        blade.post_smb_share_policies.assert_not_called()
        blade.post_smb_share_policies_rules.assert_not_called()
        module.exit_json.assert_not_called()

    def test_share_policy_check_mode_with_principal_is_changed(self):
        module = _share_module(name="rzaudit::share_pol", read="allow")
        module.check_mode = True
        blade = Mock()

        create_smb_share_policy(module, blade)

        blade.post_smb_share_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)


@pytest.mark.usefixtures("no_context")
class TestAccessPolicyInRealm:
    """An access policy is in the realm of its account."""

    def test_create_failure_carries_the_array_message(self):
        module = _os_module(
            account="zznorealm::acc", name="pol", rule=None, desc="", user=None
        )
        blade = Mock()
        blade.post_object_store_access_policies.return_value = _error_response(
            "Realm does not exist."
        )

        with pytest.raises(SystemExit):
            create_os_policy(module, blade)

        msg = module.fail_json.call_args[1]["msg"]
        assert "zznorealm::acc/pol" in msg
        assert "Realm does not exist." in msg

    @pytest.mark.parametrize("state", ["present", "absent", "copy"])
    @pytest.mark.parametrize("check_mode", [False, True])
    def test_realm_on_the_policy_name_is_refused(self, state, check_mode):
        module = _main_module(
            check_mode=check_mode,
            policy_type="access",
            state=state,
            account="acc",
            name="rzaudit::pol",
        )
        blade = _main_blade()
        create = Mock()

        with pytest.raises(SystemExit):
            _run_main(module, blade, create_os_policy=create)

        msg = module.fail_json.call_args[1]["msg"]
        assert "realm::account" in msg
        blade.get_object_store_access_policies.assert_not_called()
        create.assert_not_called()

    def test_realm_on_the_account_is_looked_up_and_created(self):
        module = _main_module(policy_type="access", account="rzaudit::acc", name="pol")
        blade = _main_blade()
        blade.get_object_store_access_policies.return_value = _error_response(
            "Policy does not exist."
        )
        create = Mock()

        _run_main(module, blade, create_os_policy=create)

        blade.get_object_store_access_policies.assert_called_once_with(
            names=["rzaudit::acc/pol"]
        )
        create.assert_called_once_with(module, blade)

    def test_existing_target_rule_message_names_the_target_policy(self):
        module = _os_module(
            account="rzaudit::acc",
            name="pol",
            rule="r1",
            target="other::acc/pol",
            target_rule=None,
        )
        blade = Mock()
        blade.get_object_store_access_policies_rules.return_value = _found(_os_rule())

        with pytest.raises(SystemExit):
            copy_os_policy_rule(module, blade)

        msg = module.fail_json.call_args[1]["msg"]
        assert "Target rule r1 already exists in policy other::acc/pol" in msg
        assert "rzaudit::acc/pol" not in msg
        blade.post_object_store_access_policies_rules.assert_not_called()


class TestCopyWormPolicyCommitMode:
    """The array reports an autocommit configuration for every WORM policy
    and accepts one only with commit_mode autocommit or hybrid."""

    @worm_env()
    def test_copy_of_a_manual_policy_sends_no_autocommit_config(self):
        module = _copy_module(policy_type="worm", target="rzaudit::worm_copy")
        blade = _worm_blade()

        copy_policy(module, blade, _worm_policy(commit_mode="manual"))

        call = blade.post_worm_data_policies.call_args[1]
        assert call["names"] == ["rzaudit::worm_copy"]
        assert call["policy"] == dict(
            LEGACY_BODY,
            mode="compliance",
            retention_lock="unlocked",
            commit_mode="manual",
        )
        module.exit_json.assert_called_once_with(changed=True)

    @worm_env()
    def test_copy_of_a_hybrid_policy_keeps_the_autocommit_config(self):
        module = _copy_module(policy_type="worm")
        blade = _worm_blade()
        source = _worm_policy(
            commit_mode="hybrid", delay_on="creation", delay_period=7200000
        )

        copy_policy(module, blade, source)

        policy = blade.post_worm_data_policies.call_args[1]["policy"]
        assert policy["commit_mode"] == "hybrid"
        assert policy["autocommit_config"] == {
            "delay_on": "creation",
            "delay_period": 7200000,
        }
