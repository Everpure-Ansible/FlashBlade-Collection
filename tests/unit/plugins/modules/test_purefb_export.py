# Copyright: (c) 2026, Pure Storage Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_export module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
from unittest.mock import Mock, patch, MagicMock

# Mock external dependencies before importing the module under test
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

from plugins.modules.purefb_export import (
    _warn_fs_policy_collision,
    _warn_type_transition,
    create_export,
)


class TestPurefbExport:
    """Test cases for purefb_export module."""

    # ==== helpers ====

    def _mk_module(self, **overrides):
        """Minimal AnsibleModule mock with the params purefb_export reads."""
        params = {
            "name": "exp1",
            "server": "_array_server",
            "filesystem": "fs1",
            "type": "NFS",
            "state": "present",
            "export_policy": None,
            "share_policy": None,
            "client_policy": None,
            "rename": None,
            "context": "",
        }
        params.update(overrides)
        module = Mock()
        module.check_mode = False
        module.params = params
        return module

    def _mk_fs(self, export_policy=None, share_policy=None, client_policy=None):
        """Mock filesystem carrying zero or more legacy FS-level policy refs."""
        fs = Mock()
        nfs = Mock()
        nfs.export_policy = None
        if export_policy:
            ep = Mock()
            ep.name = export_policy
            nfs.export_policy = ep
        smb = Mock()
        smb.share_policy = None
        smb.client_policy = None
        if share_policy:
            sp = Mock()
            sp.name = share_policy
            smb.share_policy = sp
        if client_policy:
            cp = Mock()
            cp.name = client_policy
            smb.client_policy = cp
        fs.nfs = nfs
        fs.smb = smb
        return fs

    # ==== _warn_fs_policy_collision ====

    def test_collision_helper_survives_iterator_res_items(self):
        """res.items in pypureclient is an ItemIterator - a single-pass
        generator. The helper must not consume it twice. Feeding iter([fs])
        instead of a plain list would blow up as IndexError under the old
        double-list() shape.
        """
        module = self._mk_module(export_policy="new_pol")
        blade = Mock()
        res = Mock()
        res.status_code = 200
        res.items = iter([self._mk_fs(export_policy="legacy_pol")])
        blade.get_file_systems.return_value = res

        _warn_fs_policy_collision(module, blade)

        assert module.warn.called
        assert "nfs.export_policy=legacy_pol" in module.warn.call_args[0][0]

    def test_collision_warns_for_smb_shadow_even_when_share_policy_omitted(self):
        """
        purefb_export for SMB always writes both client_policy and
        share_policy on create - defaulting to _smb_*_allow_everyone
        when the caller omits them. Any legacy FS-level smb.share_policy
        or smb.client_policy is silently shadowed by that default write.

        The helper must therefore warn on legacy SMB values regardless of
        whether the caller supplied the matching field. Under the old
        shape, this scenario (SMB, client_policy supplied, share_policy
        omitted, FS carries legacy share_policy) emitted no warning at
        all - operators lost strict share permissions to allow-everyone
        with no signal.
        """
        module = self._mk_module(type="SMB", client_policy="new_client_pol")
        # Deliberately no share_policy passed. FS carries a legacy
        # share_policy that would be shadowed by _smb_share_allow_everyone.
        blade = Mock()
        res = Mock()
        res.status_code = 200
        res.items = iter([self._mk_fs(share_policy="legacy_share_pol")])
        blade.get_file_systems.return_value = res

        _warn_fs_policy_collision(module, blade)

        warn_messages = [c.args[0] for c in module.warn.call_args_list]
        assert any(
            "smb.share_policy=legacy_share_pol" in msg for msg in warn_messages
        ), (
            "Expected a warning about the legacy FS-level share_policy that "
            "the SMB export default write is about to shadow. Got: {0}".format(
                warn_messages
            )
        )

    # ==== _warn_type_transition ====

    def test_type_transition_filter_targets_other_protocol(self):
        """When the caller asks for type=NFS, the transition-check filter
        must query for the SMB other-protocol export at the same address
        (and vice versa). Reusing the requested type here would silently
        disable the guard.
        """
        blade = Mock()
        res = Mock()
        res.status_code = 200
        res.total_item_count = 1
        blade.get_file_system_exports.return_value = res

        _warn_type_transition(self._mk_module(type="NFS"), blade)
        assert (
            "policy_type='SMB'" in blade.get_file_system_exports.call_args[1]["filter"]
        )

        blade.reset_mock()
        blade.get_file_system_exports.return_value = res

        _warn_type_transition(self._mk_module(type="SMB"), blade)
        assert (
            "policy_type='NFS'" in blade.get_file_system_exports.call_args[1]["filter"]
        )

    # ==== create_export POST body ====

    @patch("plugins.modules.purefb_export.Reference")
    @patch("plugins.modules.purefb_export.FileSystemExportPost")
    def test_create_export_nfs_posts_expected_body(self, mock_post_obj, mock_ref):
        """NFS create must POST with member_names=[filesystem] and
        policy_names=[export_policy], and set export_name/server on the
        FileSystemExportPost body. Guards the wire shape of the create call.
        """
        module = self._mk_module(export_policy="nfs_pol1")
        blade = Mock()
        # No legacy FS-level policy - collision helper short-circuits harmlessly
        fs_res = Mock()
        fs_res.status_code = 200
        fs_res.items = iter([self._mk_fs()])
        blade.get_file_systems.return_value = fs_res
        post_res = Mock()
        post_res.status_code = 200
        blade.post_file_system_exports.return_value = post_res
        # exit_json raises SystemExit in real Ansible; catch to observe the POST
        module.exit_json.side_effect = SystemExit
        try:
            create_export(module, blade)
        except SystemExit:
            pass

        call_kwargs = blade.post_file_system_exports.call_args[1]
        assert call_kwargs["member_names"] == ["fs1"]
        assert call_kwargs["policy_names"] == ["nfs_pol1"]

        post_kwargs = mock_post_obj.call_args[1]
        assert post_kwargs["export_name"] == "exp1"
        # server was wrapped in a Reference(name=…) call
        mock_ref.assert_any_call(name="_array_server")
