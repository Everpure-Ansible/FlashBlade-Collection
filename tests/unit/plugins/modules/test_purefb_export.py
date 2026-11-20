# Copyright: (c) 2026, Pure Storage Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_export module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import re
import sys
from unittest.mock import Mock, patch, MagicMock

import pytest

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
sys.modules["ansible_collections.everpure.flashblade.plugins.module_utils.version"] = (
    MagicMock()
)

from plugins.modules.purefb_export import (
    _warn_fs_policy_collision,
    _warn_type_transition,
    create_export,
    main,
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

    def test_create_export_check_mode_makes_no_request(self):
        """In check mode no POST is made and the (undefined) response must
        not be inspected. The old shape raised NameError on ``res``.
        """
        module = self._mk_module(export_policy="nfs_pol1")
        module.check_mode = True
        blade = Mock()
        fs_res = Mock()
        fs_res.status_code = 200
        fs_res.items = iter([self._mk_fs()])
        blade.get_file_systems.return_value = fs_res
        module.exit_json.side_effect = SystemExit
        try:
            create_export(module, blade)
        except SystemExit:
            pass

        blade.post_file_system_exports.assert_not_called()
        module.fail_json.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)


# ==== main(): realms, checked reads and check mode ====

MOD = "plugins.modules.purefb_export"
SAME_REALM = (
    "SMB Share or NFS export policies for the export must belong to the same realm"
)
_FILTER = re.compile(
    "export_name='(.*)' and policy_type='(.*)' and member.name='(.*)'"
    " and server.name='(.*)'"
)


def _version(value):
    return tuple(int(part) for part in str(value).split("."))


def _message(res):
    """Stand-in for get_error_message, which lives in the mocked module_utils."""
    return res.errors[0].message


def _response(items=None):
    res = Mock()
    res.status_code = 200
    res.items = items if items is not None else []
    res.total_item_count = len(res.items)
    res.errors = []
    return res


def _error(message, status_code=400):
    res = Mock()
    res.status_code = status_code
    error = Mock(spec=["message"])
    error.message = message
    res.errors = [error]
    return res


def _named(name):
    """A server, file system or policy as the array returns it."""
    item = Mock(spec=["id", "name", "realms", "nfs", "smb"])
    item.id = "id-of-{0}".format(name)
    item.name = name
    realm = name.rpartition("::")[0]
    item.realms = [Mock(spec=["name"])] if realm else []
    if realm:
        item.realms[0].name = realm
    item.nfs = None
    item.smb = None
    return item


def _reference(name):
    ref = Mock(spec=["id", "name", "resource_type"])
    ref.id = "id-of-{0}".format(name) if name else None
    ref.name = name
    return ref


def _export(
    export_name="exp1",
    filesystem="fs1",
    server="_array_server",
    protocol="NFS",
    policy="nfs1",
    share_policy=None,
):
    """An export as the array returns it: every reference carries the realm."""
    export = Mock(
        spec=["name", "export_name", "policy_type", "member", "server", "policy"]
        + (["share_policy"] if protocol == "SMB" else [])
    )
    export.name = "{0}::{1}::{2}".format(server, protocol, export_name)
    export.export_name = export_name
    export.policy_type = protocol
    export.member = _reference(filesystem)
    export.server = _reference(server)
    export.policy = _reference(policy)
    if protocol == "SMB":
        export.share_policy = _reference(share_policy)
    return export


def _by_name(existing, missing):
    """Side effect for a GET by names, matched without regard to case.

    C(missing) is the array's message for a name it does not find; None
    stands for the empty list a realm-scoped administrator gets instead.
    The client joins the names with commas and the array splits them
    there, so one name that holds a comma is read as several names.
    """

    def _get(names=None, **kwargs):
        if not names:
            return _response(items=list(existing))
        wanted = set(",".join(names).lower().split(","))
        if [name for name in wanted if not name.strip()]:
            return _error("Missing or invalid parameter.")
        items = [item for item in existing if item.name.lower() in wanted]
        if missing and len(items) < len(wanted):
            return _error(missing)
        return _response(items=items)

    return _get


def _exports_by_filter(exports):
    """Side effect for the export lookup: applies the filter main() sends."""

    def _get(**kwargs):
        wanted = _FILTER.match(kwargs["filter"]).groups()
        items = [
            export
            for export in exports
            if (
                export.export_name,
                export.policy_type,
                export.member.name,
                export.server.name,
            )
            == wanted
        ]
        return _response(items=items)

    return _get


FILE_SYSTEMS = ["fs1", "tenant1::fs1"]
SERVERS = ["_array_server", "srv1", "tenant1::srv1"]
NFS_POLICIES = ["nfs1", "nfs2", "tenant1::nfs1", "tenant1::nfs2"]
CLIENT_POLICIES = ["_smb_client_allow_everyone", "tenant1::client1"]
SHARE_POLICIES = ["_smb_share_allow_everyone", "share1", "tenant1::share1"]


def _blade(exports=None, fs_missing="File system does not exist."):
    """A blade holding the same leaf names at array level and in realm tenant1."""
    blade = Mock()
    blade.get_fleets.return_value = _response()
    blade.get_servers.side_effect = _by_name(
        [_named(name) for name in SERVERS], "Server does not exist."
    )
    blade.get_file_systems.side_effect = _by_name(
        [_named(name) for name in FILE_SYSTEMS], fs_missing
    )
    blade.get_nfs_export_policies.side_effect = _by_name(
        [_named(name) for name in NFS_POLICIES], "NFS export policy does not exist."
    )
    blade.get_smb_client_policies.side_effect = _by_name(
        [_named(name) for name in CLIENT_POLICIES], "SMB client policy does not exist."
    )
    blade.get_smb_share_policies.side_effect = _by_name(
        [_named(name) for name in SHARE_POLICIES], "SMB share policy does not exist."
    )
    blade.get_file_system_exports.side_effect = _exports_by_filter(exports or [])
    blade.post_file_system_exports.return_value = _response()
    blade.patch_file_system_exports.return_value = _response()
    blade.delete_file_system_exports.return_value = _response()
    return blade


def _run(blade, check_mode=False, **overrides):
    """Run main() and return (module, FileSystemExport mock, get_system mock)."""
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
    module.params = params
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    with patch(MOD + ".AnsibleModule", return_value=module), patch(
        MOD + ".get_system", return_value=blade
    ) as login, patch(MOD + ".get_rest_api_version", return_value="2.30"), patch(
        MOD + ".LooseVersion", side_effect=_version
    ), patch(
        MOD + ".get_error_message", side_effect=_message
    ), patch(
        MOD + ".Reference", side_effect=lambda **kwargs: kwargs
    ), patch(
        MOD + ".FileSystemExportPost", side_effect=lambda **kwargs: kwargs
    ), patch(
        MOD + ".FileSystemExport", side_effect=lambda **kwargs: kwargs
    ) as body:
        try:
            main()
        except SystemExit:
            pass
    return module, body, login


def _failed(module):
    """Return the failure message of a run that has to fail."""
    assert module.fail_json.called, "no failure, exit_json{0}".format(
        module.exit_json.call_args
    )
    module.exit_json.assert_not_called()
    return module.fail_json.call_args[1]["msg"]


def _changed(module):
    """Return the changed flag of a run that has to succeed."""
    assert not module.fail_json.called, module.fail_json.call_args
    module.exit_json.assert_called_once()
    return module.exit_json.call_args[1]["changed"]


def _writes(blade):
    """Names of the write calls a run made."""
    return [
        call[0]
        for call in blade.method_calls
        if call[0].split("_")[0] in ("post", "patch", "delete")
    ]


REALM = {"filesystem": "tenant1::fs1", "server": "tenant1::srv1"}


class TestFileSystemAndServerScope:
    """The file system and the server of an export are in one realm, or in none."""

    @pytest.mark.parametrize("check_mode", [True, False])
    @pytest.mark.parametrize(
        "task",
        [
            {"export_policy": "tenant1::nfs1"},
            {"state": "absent"},
            {"rename": "exp2"},
        ],
    )
    def test_realm_file_system_on_default_server_fails(self, task, check_mode):
        """The default server is not in a realm: every state is refused
        before the login, instead of a create the array refuses or an
        unchanged result while the realm export stays as it is."""
        realm_export = _export(
            filesystem="tenant1::fs1", server="tenant1::srv1", policy="tenant1::nfs1"
        )
        blade = _blade([realm_export])
        module, body, login = _run(
            blade, check_mode=check_mode, filesystem="tenant1::fs1", **task
        )
        msg = _failed(module)
        assert "File system tenant1::fs1 is in realm tenant1" in msg
        assert "server _array_server is not in a realm" in msg
        assert "tenant1::<server>" in msg
        login.assert_not_called()
        assert blade.method_calls == []

    @pytest.mark.parametrize(
        "filesystem, server, said",
        [
            ("tenant1::fs1", "srv1", "server srv1 is not in a realm"),
            ("fs1", "tenant1::srv1", "File system fs1 is not in a realm"),
            ("tenant2::fs1", "tenant1::srv1", "File system tenant2::fs1 is in realm"),
        ],
    )
    def test_file_system_and_server_of_two_scopes_fail(self, filesystem, server, said):
        blade = _blade()
        module, body, login = _run(
            blade,
            check_mode=True,
            filesystem=filesystem,
            server=server,
            export_policy="nfs1",
        )
        msg = _failed(module)
        assert said in msg
        assert "must be in the same realm, or both outside of any realm" in msg
        # only the default server gets the advice about the default
        assert "default server" not in msg
        assert blade.method_calls == []

    def test_realm_spelled_in_another_case_is_the_same_realm(self):
        blade = _blade()
        module, body, login = _run(
            blade,
            filesystem="tenant1::fs1",
            server="TENANT1::srv1",
            export_policy="tenant1::nfs1",
        )
        assert _changed(module) is True
        assert _writes(blade) == ["post_file_system_exports"]

    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize("option", ["name", "rename"])
    def test_realm_qualified_export_name_fails(self, option, state):
        """The array refuses a colon in an export name; check mode said
        changed and state=absent said unchanged."""
        blade = _blade()
        task = dict(REALM, export_policy="tenant1::nfs1", state=state)
        task[option] = "tenant1::exp1"
        module, body, login = _run(blade, check_mode=True, **task)
        msg = _failed(module)
        assert "{0} tenant1::exp1 is not valid".format(option) in msg
        assert "never realm-qualified" in msg
        assert blade.method_calls == []

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_realm_export_lifecycle_with_qualified_names(self, check_mode):
        """Create, rerun and delete of a realm export next to an array-level
        export of the same name: only the realm export is addressed."""
        twin = _export()
        blade = _blade([twin])
        task = dict(REALM, export_policy="tenant1::nfs1")
        module, body, login = _run(blade, check_mode=check_mode, **task)
        assert _changed(module) is True
        assert _writes(blade) == ([] if check_mode else ["post_file_system_exports"])
        if not check_mode:
            sent = blade.post_file_system_exports.call_args[1]
            assert sent["member_names"] == ["tenant1::fs1"]
            assert sent["policy_names"] == ["tenant1::nfs1"]
            assert sent["file_system_export"]["server"] == {"name": "tenant1::srv1"}

        realm_export = _export(
            filesystem="tenant1::fs1", server="tenant1::srv1", policy="tenant1::nfs1"
        )
        blade = _blade([twin, realm_export])
        module, body, login = _run(blade, check_mode=check_mode, **task)
        assert _changed(module) is False
        assert _writes(blade) == []

        module, body, login = _run(
            blade, check_mode=check_mode, state="absent", **REALM
        )
        assert _changed(module) is True
        if not check_mode:
            blade.delete_file_system_exports.assert_called_once_with(
                names=["tenant1::srv1::NFS::exp1"]
            )

    def test_array_level_export_is_handled_as_before(self):
        blade = _blade()
        module, body, login = _run(blade, export_policy="nfs1")
        assert _changed(module) is True
        sent = blade.post_file_system_exports.call_args[1]
        assert sent["member_names"] == ["fs1"]
        assert sent["policy_names"] == ["nfs1"]
        assert sent["file_system_export"] == {
            "export_name": "exp1",
            "server": {"name": "_array_server"},
        }

        blade = _blade([_export()])
        module, body, login = _run(blade, export_policy="nfs1")
        assert _changed(module) is False
        module, body, login = _run(blade, state="absent")
        assert _changed(module) is True
        blade.delete_file_system_exports.assert_called_once_with(
            names=["_array_server::NFS::exp1"]
        )


class TestNfsCreateNeedsPolicy:
    """An NFS export is created with an NFS export policy."""

    @pytest.mark.parametrize("check_mode", [True, False])
    @pytest.mark.parametrize("scope", [{}, REALM])
    def test_nfs_create_without_policy_fails(self, scope, check_mode):
        """The SDK sent the policy name "None" ("Policy does not exist.")
        and check mode reported changed."""
        blade = _blade()
        module, body, login = _run(blade, check_mode=check_mode, **scope)
        msg = _failed(module)
        assert "export_policy is required to create NFS export exp1" in msg
        assert _writes(blade) == []

    def test_existing_nfs_export_needs_no_policy_in_the_task(self):
        blade = _blade([_export()])
        module, body, login = _run(blade)
        assert _changed(module) is False
        assert _writes(blade) == []

    def test_smb_create_defaults_to_the_built_in_policies(self):
        """The built-in policies serve every realm and are not looked up."""
        blade = _blade()
        module, body, login = _run(blade, type="SMB", **REALM)
        assert _changed(module) is True
        sent = blade.post_file_system_exports.call_args[1]
        assert sent["policy_names"] == ["_smb_client_allow_everyone"]
        assert sent["file_system_export"]["share_policy"] == {
            "name": "_smb_share_allow_everyone"
        }
        blade.get_smb_client_policies.assert_not_called()
        blade.get_smb_share_policies.assert_not_called()


class TestPolicyIsLookedUp:
    """A policy that does not exist fails the task before a change is reported."""

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_create_with_the_bare_name_of_a_realm_policy_fails(self, check_mode):
        blade = _blade()
        blade.get_nfs_export_policies.side_effect = _by_name(
            [_named("tenant1::nfs3")], "NFS export policy does not exist."
        )
        module, body, login = _run(
            blade, check_mode=check_mode, export_policy="nfs3", **REALM
        )
        msg = _failed(module)
        assert msg.startswith("NFS export policy nfs3 does not exist.")
        assert "a policy of that realm is named tenant1::nfs3" in msg
        assert _writes(blade) == []

    def test_create_with_a_missing_policy_at_array_level_has_no_realm_advice(self):
        blade = _blade()
        module, body, login = _run(blade, check_mode=True, export_policy="nfs9")
        assert _failed(module) == "NFS export policy nfs9 does not exist."

    @pytest.mark.parametrize(
        "task, said",
        [
            ({"client_policy": "client9"}, "SMB client policy client9 does not exist."),
            ({"share_policy": "share9"}, "SMB share policy share9 does not exist."),
        ],
    )
    def test_smb_create_with_a_missing_policy_fails(self, task, said):
        blade = _blade()
        module, body, login = _run(blade, check_mode=True, type="SMB", **task)
        assert _failed(module) == said

    def test_policy_read_refused_is_reported_with_the_array_message(self):
        blade = _blade()
        blade.get_nfs_export_policies.side_effect = None
        blade.get_nfs_export_policies.return_value = _error(
            "Operation not permitted.", 403
        )
        module, body, login = _run(blade, check_mode=True, export_policy="nfs1")
        assert _failed(module) == (
            "Failed to read NFS export policy nfs1. Error: Operation not permitted."
        )

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_nfs_policy_change_to_a_missing_policy_fails(self, check_mode):
        """Check mode reported changed; the array answers a real run with
        "Policy does not exist."."""
        blade = _blade(
            [
                _export(
                    filesystem="tenant1::fs1",
                    server="tenant1::srv1",
                    policy="tenant1::nfs1",
                )
            ]
        )
        module, body, login = _run(
            blade, check_mode=check_mode, export_policy="nfs3", **REALM
        )
        msg = _failed(module)
        assert msg.startswith("NFS export policy nfs3 does not exist.")
        assert "tenant1::nfs3" in msg
        assert _writes(blade) == []

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_nfs_policy_change_to_an_existing_policy(self, check_mode):
        blade = _blade(
            [
                _export(
                    filesystem="tenant1::fs1",
                    server="tenant1::srv1",
                    policy="tenant1::nfs1",
                )
            ]
        )
        module, body, login = _run(
            blade, check_mode=check_mode, export_policy="tenant1::nfs2", **REALM
        )
        assert _changed(module) is True
        blade.get_nfs_export_policies.assert_called_once_with(names=["tenant1::nfs2"])
        if check_mode:
            assert _writes(blade) == []
        else:
            body.assert_called_with(policy={"name": "tenant1::nfs2"})
            blade.patch_file_system_exports.assert_called_once_with(
                names=["tenant1::srv1::NFS::exp1"],
                file_system_export={"policy": {"name": "tenant1::nfs2"}},
            )

    def test_policy_named_in_another_case_is_not_a_change(self):
        """The array matches names without regard to case."""
        blade = _blade(
            [
                _export(
                    filesystem="tenant1::fs1",
                    server="tenant1::srv1",
                    policy="tenant1::nfs1",
                )
            ]
        )
        module, body, login = _run(blade, export_policy="Tenant1::NFS1", **REALM)
        assert _changed(module) is False
        assert _writes(blade) == []
        blade.get_nfs_export_policies.assert_not_called()

        smb = _export(
            protocol="SMB",
            policy="_smb_client_allow_everyone",
            share_policy="_smb_share_allow_everyone",
        )
        blade = _blade([smb])
        module, body, login = _run(
            blade,
            type="SMB",
            client_policy="_SMB_client_allow_everyone",
            share_policy="_SMB_share_allow_everyone",
        )
        assert _changed(module) is False
        assert _writes(blade) == []

    @pytest.mark.parametrize(
        "task, said",
        [
            ({"client_policy": "client1"}, "SMB client policy client1 does not exist."),
            ({"share_policy": "share9"}, "SMB share policy share9 does not exist."),
        ],
    )
    def test_smb_policy_change_to_a_missing_policy_fails(self, task, said):
        smb = _export(
            filesystem="tenant1::fs1",
            server="tenant1::srv1",
            protocol="SMB",
            policy="_smb_client_allow_everyone",
            share_policy="_smb_share_allow_everyone",
        )
        blade = _blade([smb])
        module, body, login = _run(
            blade, check_mode=True, type="SMB", **dict(REALM, **task)
        )
        msg = _failed(module)
        assert msg.startswith(said)
        assert "tenant1::" + said.split()[3] in msg

    def test_smb_policy_change_to_existing_policies(self):
        smb = _export(
            filesystem="tenant1::fs1",
            server="tenant1::srv1",
            protocol="SMB",
            policy="_smb_client_allow_everyone",
            share_policy="_smb_share_allow_everyone",
        )
        blade = _blade([smb])
        task = dict(
            REALM,
            type="SMB",
            client_policy="tenant1::client1",
            share_policy="tenant1::share1",
        )
        module, body, login = _run(blade, check_mode=True, **task)
        assert _changed(module) is True
        assert _writes(blade) == []
        module, body, login = _run(blade, **task)
        assert _changed(module) is True
        blade.patch_file_system_exports.assert_called_once_with(
            names=["tenant1::srv1::SMB::exp1"],
            file_system_export={
                "share_policy": {"name": "tenant1::share1"},
                "policy": {"name": "tenant1::client1"},
            },
        )


class TestArrayRefusalOfAPolicy:
    """The array decides which existing policy may serve an export; its
    refusal is completed with the form of the names that it accepts."""

    def test_update_refused_for_a_realm_export(self):
        blade = _blade(
            [
                _export(
                    filesystem="tenant1::fs1",
                    server="tenant1::srv1",
                    policy="tenant1::nfs1",
                )
            ]
        )
        blade.patch_file_system_exports.return_value = _error(SAME_REALM)
        module, body, login = _run(blade, export_policy="nfs1", **REALM)
        assert _failed(module) == (
            "Failed to update export tenant1::srv1::NFS::exp1. Error: "
            + SAME_REALM
            + ". "
            "The export is in realm tenant1: use a policy of that realm, named "
            "tenant1::<policy>."
        )

    def test_smb_update_refused_names_the_built_in_policies_too(self):
        smb = _export(
            filesystem="tenant1::fs1",
            server="tenant1::srv1",
            protocol="SMB",
            policy="_smb_client_allow_everyone",
            share_policy="_smb_share_allow_everyone",
        )
        blade = _blade([smb])
        blade.patch_file_system_exports.return_value = _error(SAME_REALM)
        module, body, login = _run(blade, type="SMB", share_policy="share1", **REALM)
        assert _failed(module).endswith(
            "use a policy of that realm, named tenant1::<policy>, or a built-in policy."
        )

    def test_create_refused_for_an_array_level_export(self):
        blade = _blade()
        blade.post_file_system_exports.return_value = _error(SAME_REALM)
        module, body, login = _run(blade, export_policy="tenant1::nfs1")
        assert _failed(module) == (
            "Failed to create export exp1 for fs1. Error: " + SAME_REALM + ". "
            "The export is not in a realm: use a policy that is not in a realm either."
        )

    def test_any_other_refusal_is_relayed_as_it_is(self):
        blade = _blade()
        blade.post_file_system_exports.return_value = _error("Export name is in use.")
        module, body, login = _run(blade, export_policy="nfs1")
        assert _failed(module) == (
            "Failed to create export exp1 for fs1. Error: Export name is in use."
        )


class TestReadsAreChecked:
    """A read that fails is reported; only "does not exist" means absent."""

    @pytest.mark.parametrize("fs_missing", ["File system does not exist.", None])
    def test_create_for_a_missing_file_system_fails_in_check_mode(self, fs_missing):
        """A missing name is an error for one administrator and an empty
        list for a realm-scoped one; check mode reported changed for both."""
        blade = _blade(fs_missing=fs_missing)
        module, body, login = _run(
            blade, check_mode=True, filesystem="fs9", export_policy="nfs1"
        )
        assert _failed(module) == "File system fs9 does not exist."

    def test_file_system_read_refused_is_reported(self):
        blade = _blade(fs_missing="Operation not permitted.")
        module, body, login = _run(
            blade, check_mode=True, filesystem="fs9", export_policy="nfs1"
        )
        assert _failed(module) == (
            "Failed to read file system fs9. Error: Operation not permitted."
        )

    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_export_read_failure_is_not_an_absent_export(self, state):
        """A failed lookup led to a create attempt, or to an unchanged
        state=absent while the export may exist."""
        blade = _blade([_export()])
        blade.get_file_system_exports.side_effect = None
        blade.get_file_system_exports.return_value = _error("Syntax error in query.")
        module, body, login = _run(blade, state=state, export_policy="nfs1")
        assert _failed(module) == (
            "Failed to read export exp1 of file system fs1. Error: "
            "Syntax error in query."
        )
        assert _writes(blade) == []

    def test_export_lookup_goes_by_the_items_returned(self):
        """An answer can count items it does not return."""
        blade = _blade()
        res = _response()
        res.total_item_count = 1
        blade.get_file_system_exports.side_effect = None
        blade.get_file_system_exports.return_value = res
        module, body, login = _run(blade, state="absent")
        assert _changed(module) is False

    def test_missing_server_keeps_its_message(self):
        blade = _blade()
        module, body, login = _run(blade, server="srv9", export_policy="nfs1")
        assert _failed(module) == "Server srv9 does not exist."

    def test_server_read_refused_is_reported(self):
        """Any failed read used to be reported as a server that does not exist."""
        blade = _blade()
        blade.get_servers.side_effect = None
        blade.get_servers.return_value = _error("Internal error.", 500)
        module, body, login = _run(blade, export_policy="nfs1")
        assert _failed(module) == (
            "Failed to read server _array_server. Error: Internal error."
        )


class TestFleetContext:
    """The lookups made before a change is reported follow the fleet context."""

    def test_lookups_before_a_create_carry_the_context(self):
        blade = _blade()
        module, body, login = _run(
            blade, check_mode=True, export_policy="nfs1", context="array2"
        )
        assert _changed(module) is True
        blade.get_file_systems.assert_any_call(names=["fs1"], context_names=["array2"])
        blade.get_nfs_export_policies.assert_called_once_with(
            names=["nfs1"], context_names=["array2"]
        )
        assert _writes(blade) == []

    def test_policy_lookup_before_an_update_carries_the_context(self):
        smb = _export(
            protocol="SMB",
            policy="_smb_client_allow_everyone",
            share_policy="_smb_share_allow_everyone",
        )
        blade = _blade([smb])
        module, body, login = _run(
            blade, check_mode=True, type="SMB", share_policy="share1", context="array2"
        )
        assert _changed(module) is True
        blade.get_smb_share_policies.assert_called_once_with(
            names=["share1"], context_names=["array2"]
        )
        blade.get_smb_client_policies.assert_not_called()
        assert _writes(blade) == []

    def test_missing_policy_in_a_context_fails(self):
        blade = _blade()
        module, body, login = _run(
            blade, check_mode=True, export_policy="nfs9", context="array2"
        )
        assert _failed(module) == "NFS export policy nfs9 does not exist."


class TestNamesAddressOneObject:
    """The file system, the server and each policy of an export are one
    object each, and an empty name addresses nothing."""

    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize(
        "task, said",
        [
            ({"filesystem": "fs1,fs1"}, "filesystem fs1,fs1 is not valid"),
            (
                {"server": "srv1,_array_server"},
                "server srv1,_array_server is not valid",
            ),
            ({"export_policy": "nfs1,nfs2"}, "export_policy nfs1,nfs2 is not valid"),
            (
                {"type": "SMB", "client_policy": "tenant1::client1,tenant1::client1"},
                "client_policy tenant1::client1,tenant1::client1 is not valid",
            ),
            (
                {"type": "SMB", "share_policy": "share1,_smb_share_allow_everyone"},
                "share_policy share1,_smb_share_allow_everyone is not valid",
            ),
        ],
    )
    def test_a_list_of_names_fails(self, task, said, state):
        """The array reads a comma as the separator of a list. Where every
        name of the list exists the lookups passed, so check mode reported
        a create for a name that is not one object."""
        blade = _blade()
        params = dict({"export_policy": "nfs1", "state": state}, **task)
        module, body, login = _run(blade, check_mode=True, **params)
        msg = _failed(module)
        assert said in msg
        assert "an export has one" in msg
        login.assert_not_called()
        assert blade.method_calls == []

    def test_a_policy_of_the_other_protocol_is_not_judged(self):
        """An NFS task does not use share_policy, as before."""
        blade = _blade([_export()])
        module, body, login = _run(blade, export_policy="nfs1", share_policy="a,b")
        assert _changed(module) is False
        assert _writes(blade) == []

    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize("option", ["name", "filesystem", "server"])
    @pytest.mark.parametrize("value", ["", "  "])
    def test_an_empty_name_fails(self, option, value, state):
        """An empty export name was reported as a create in check mode, and
        an empty file system or server as a failed read without a name."""
        blade = _blade()
        task = {"export_policy": "nfs1", "state": state, option: value}
        module, body, login = _run(blade, check_mode=True, **task)
        assert _failed(module) == "{0} cannot be empty.".format(option)
        login.assert_not_called()
        assert blade.method_calls == []
