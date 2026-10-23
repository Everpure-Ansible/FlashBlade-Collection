# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_policy rule idempotency and context_names/fleet handling."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
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
    _nfs_rule,
    _share_rule_patch,
    _share_rule_perms,
    copy_policy,
    create_network_access_policy,
    delete_network_access_policy,
    delete_smb_share_policy,
    rename_smb_share_policy,
    rename_snap_policy,
    update_network_access_policy,
    update_nfs_policy,
    update_os_policy,
    update_smb_share_policy,
    update_snap_policy,
)


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
    network-access-policies endpoints take no context (#599)."""

    @patch("plugins.modules.purefb_policy.delete_network_access_policy")
    @patch("plugins.modules.purefb_policy.get_rest_api_version")
    @patch("plugins.modules.purefb_policy.get_system")
    @patch("plugins.modules.purefb_policy.AnsibleModule")
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
        blade.get_policies_file_systems.return_value.items = []

        update_snap_policy(module, blade)

        blade.patch_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)


class TestRenameSnapPolicy:
    """Snapshot policy rename must carry the new name on the wire and must be
    checked afterwards: Purity//FB 4.6.4 (REST 2.21) answers 200 to
    {"name": ...} on PATCH /policies and keeps the old name."""

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

    @patch("plugins.modules.purefb_policy.LooseVersion")
    def test_rename_check_mode_does_not_touch_array(self, mock_loose_version):
        mock_loose_version.return_value.__le__ = Mock(return_value=False)
        module = _snap_module()
        module.check_mode = True
        module.params["rename"] = "weekly_snap_policy"
        blade = _snap_blade(_snap_rule())

        rename_snap_policy(module, blade)

        blade.patch_policies.assert_not_called()
        blade.get_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)


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
        # Addressed by rule name (the principal) within the policy, never by
        # a "<policy>.<index>" name: share rules have no index.
        call_kwargs = blade.patch_smb_share_policies_rules.call_args[1]
        assert call_kwargs["names"] == ["Everyone"]
        assert call_kwargs["policy_names"] == ["share_pol"]
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
            policy_names=["share_pol"], names=["Everyone"]
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
