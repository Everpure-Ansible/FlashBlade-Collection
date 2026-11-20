# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_fs_replica module."""

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

from plugins.module_utils.version import LooseVersion as RealLooseVersion
from plugins.modules.purefb_fs_replica import (
    main,
    get_local_rl,
    _remote_default_exports,
)

MODULE = "plugins.modules.purefb_fs_replica"


def _params(**overrides):
    params = {
        "name": "fs1",
        "target_fs": None,
        "target_array": None,
        "policy": None,
        "in_progress": False,
        "state": "present",
        "link_type": None,
        "replicate_now": False,
        "remote_default_exports": None,
    }
    params.update(overrides)
    return params


def _response(status=200, items=None):
    res = Mock()
    res.status_code = status
    res.items = items if items is not None else []
    return res


def _link(remote="arrayB", remote_fs="fs1", link_type="full-replica"):
    link = Mock()
    link.remote = Mock()
    link.remote.name = remote
    link.remote_file_system = Mock()
    link.remote_file_system.name = remote_fs
    link.link_type = link_type
    return link


def _connection(name="arrayB", address="10.0.0.2", status="connected"):
    conn = Mock()
    conn.remote = Mock()
    conn.remote.name = name
    conn.management_address = address
    conn.status = status
    return conn


def _module(params, check_mode=False):
    module = Mock()
    module.params = params
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _blade(fs_exists=True, links=None, connections=None, policy_attached=False):
    blade = Mock()
    blade.get_file_systems.return_value = _response(items=[Mock()] if fs_exists else [])
    blade.get_file_system_replica_links.return_value = _response(items=links or [])
    blade.get_array_connections.return_value = _response(items=connections or [])
    blade.get_policies.return_value = _response(items=[Mock()])
    blade.get_file_system_replica_links_policies.return_value = _response(
        items=[Mock()] if policy_attached else []
    )
    for method in (
        "post_file_system_replica_links",
        "patch_file_system_replica_links",
        "delete_file_system_replica_links",
        "post_file_system_replica_links_policies",
        "delete_file_system_replica_links_policies",
    ):
        getattr(blade, method).return_value = _response()
    return blade


def _error_text(res, default="Unknown error"):
    """What get_error_message returns: the first message of an error response."""
    errors = getattr(res, "errors", None)
    if isinstance(errors, list) and errors:
        return errors[0].message
    return default


def _run_main(module, blade, api_version="2.30"):
    """Run main() with the module, SDK client and REST version patched in."""
    with patch(MODULE + ".AnsibleModule", return_value=module), patch(
        MODULE + ".get_system", return_value=blade
    ), patch(MODULE + ".get_rest_api_version", return_value=api_version), patch(
        MODULE + ".LooseVersion", RealLooseVersion
    ), patch(
        MODULE + ".HAS_PYPURECLIENT", True
    ), patch(
        MODULE + ".get_error_message", side_effect=_error_text
    ):
        with pytest.raises(SystemExit):
            main()


def _fail_msg(module):
    module.fail_json.assert_called_once()
    return module.fail_json.call_args.kwargs["msg"]


class TestRemoteDefaultExportsEncoding:
    def test_empty_list_becomes_quoted_empty_string(self):
        """[] must reach the array as the literal '""', not an empty parameter"""
        assert _remote_default_exports([]) == ['""']

    def test_protocols_are_normalised(self):
        assert _remote_default_exports(["smb", "nfs", "nfs"]) == ["nfs", "smb"]
        assert _remote_default_exports(["smb"]) == ["smb"]


class TestGetLocalRl:
    def test_returns_first_link_without_target_array(self):
        links = [_link("arrayB"), _link("arrayC")]
        module = _module(_params())
        blade = _blade(links=links)
        assert get_local_rl(module, blade) is links[0]

    def test_filters_by_target_array_name(self):
        links = [_link("arrayB"), _link("arrayC")]
        module = _module(_params(target_array="arrayC"))
        blade = _blade(links=links)
        assert get_local_rl(module, blade) is links[1]
        blade.get_array_connections.assert_not_called()

    def test_resolves_target_array_management_address(self):
        links = [_link("arrayB"), _link("arrayC")]
        module = _module(_params(target_array="10.0.0.3"))
        blade = _blade(
            links=links, connections=[_connection("arrayC", address="10.0.0.3")]
        )
        assert get_local_rl(module, blade) is links[1]

    def test_returns_none_when_target_array_has_no_link(self):
        module = _module(_params(target_array="arrayD"))
        blade = _blade(links=[_link("arrayB")])
        assert get_local_rl(module, blade) is None

    def test_returns_none_when_the_file_system_does_not_exist(self):
        """The array answers a missing file system with an error, not a list"""
        module = _module(_params())
        blade = _blade()
        blade.get_file_system_replica_links.return_value = _refused(
            400, "File system does not exist."
        )
        with patch(MODULE + ".get_error_message", side_effect=_error_text):
            assert get_local_rl(module, blade) is None
        module.fail_json.assert_not_called()

    def test_finds_the_link_in_another_letter_case(self):
        """The array matches the name of the remote array in any letter case"""
        links = [_link("arrayB"), _link("arrayC")]
        module = _module(_params(target_array="ARRAYC"))
        blade = _blade(links=links)
        assert get_local_rl(module, blade) is links[1]
        blade.get_array_connections.assert_not_called()


class TestCreate:
    @patch(MODULE + ".FileSystemReplicaLink")
    def test_create_minimal(self, mock_link_model):
        module = _module(_params(target_array="arrayB"))
        blade = _blade(connections=[_connection()])
        _run_main(module, blade)
        mock_link_model.assert_called_once_with()
        kwargs = blade.post_file_system_replica_links.call_args.kwargs
        assert kwargs["local_file_system_names"] == ["fs1"]
        assert kwargs["remote_file_system_names"] == ["fs1"]
        assert kwargs["remote_names"] == ["arrayB"]
        assert "remote_default_exports" not in kwargs
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".LocationReference")
    @patch(MODULE + ".FileSystemReplicaLink")
    def test_create_with_policy_and_link_type(self, mock_link_model, mock_location):
        module = _module(
            _params(
                target_array="arrayB",
                target_fs="fs1-dr",
                policy="daily",
                link_type="full-replica",
            )
        )
        blade = _blade(connections=[_connection()])
        _run_main(module, blade)
        mock_location.assert_called_once_with(name="daily")
        mock_link_model.assert_called_once_with(
            link_type="full-replica", policies=[mock_location.return_value]
        )
        kwargs = blade.post_file_system_replica_links.call_args.kwargs
        assert kwargs["remote_file_system_names"] == ["fs1-dr"]
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".FileSystemReplicaLink")
    def test_create_partial_replica(self, mock_link_model):
        module = _module(_params(target_array="arrayB", link_type="partial-replica"))
        blade = _blade(connections=[_connection()])
        _run_main(module, blade)
        mock_link_model.assert_called_once_with(link_type="partial-replica")
        module.exit_json.assert_called_once_with(changed=True)

    def test_create_with_empty_remote_default_exports(self):
        module = _module(_params(target_array="arrayB", remote_default_exports=[]))
        blade = _blade(connections=[_connection()])
        _run_main(module, blade)
        kwargs = blade.post_file_system_replica_links.call_args.kwargs
        assert kwargs["remote_default_exports"] == ['""']
        module.exit_json.assert_called_once_with(changed=True)

    def test_create_with_remote_default_exports_protocols(self):
        module = _module(
            _params(target_array="arrayB", remote_default_exports=["smb", "nfs"])
        )
        blade = _blade(connections=[_connection()])
        _run_main(module, blade)
        kwargs = blade.post_file_system_replica_links.call_args.kwargs
        assert kwargs["remote_default_exports"] == ["nfs", "smb"]

    def test_create_by_management_address(self):
        module = _module(_params(target_array="10.0.0.2"))
        blade = _blade(connections=[_connection(address="10.0.0.2")])
        _run_main(module, blade)
        kwargs = blade.post_file_system_replica_links.call_args.kwargs
        assert kwargs["remote_names"] == ["arrayB"]

    def test_create_check_mode(self):
        module = _module(
            _params(
                target_array="arrayB",
                link_type="partial-replica",
                remote_default_exports=[],
            ),
            check_mode=True,
        )
        blade = _blade(connections=[_connection()])
        _run_main(module, blade)
        blade.get_array_connections.assert_called_once()
        blade.post_file_system_replica_links.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_create_check_mode_target_not_connected(self):
        """Check mode must refuse a disconnected target like the real run"""
        module = _module(_params(target_array="arrayB"), check_mode=True)
        blade = _blade(connections=[_connection(status="disconnected")])
        _run_main(module, blade)
        assert "not connected" in _fail_msg(module)
        blade.post_file_system_replica_links.assert_not_called()
        module.exit_json.assert_not_called()

    def test_create_check_mode_unknown_target(self):
        """Check mode must refuse a target without an array connection"""
        module = _module(_params(target_array="arrayZ"), check_mode=True)
        blade = _blade(connections=[_connection("arrayB")])
        _run_main(module, blade)
        assert "not connected" in _fail_msg(module)
        blade.post_file_system_replica_links.assert_not_called()
        module.exit_json.assert_not_called()

    def test_existing_link_ignores_remote_default_exports(self):
        """remote_default_exports is create-only: an existing link is left alone"""
        module = _module(_params(target_array="arrayB", remote_default_exports=[]))
        blade = _blade(links=[_link()])
        _run_main(module, blade)
        blade.post_file_system_replica_links.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_create_requires_target_array(self):
        module = _module(_params())
        blade = _blade()
        _run_main(module, blade)
        assert "target_array is required" in _fail_msg(module)
        blade.post_file_system_replica_links.assert_not_called()

    def test_create_target_not_connected(self):
        module = _module(_params(target_array="arrayB"))
        blade = _blade(connections=[_connection(status="disconnected")])
        _run_main(module, blade)
        assert "not connected" in _fail_msg(module)
        blade.post_file_system_replica_links.assert_not_called()

    def test_create_api_error(self):
        module = _module(_params(target_array="arrayB"))
        blade = _blade(connections=[_connection()])
        blade.post_file_system_replica_links.return_value = _response(status=400)
        _run_main(module, blade)
        assert "Failed to create filesystem replica link" in _fail_msg(module)

    def test_missing_local_filesystem(self):
        module = _module(_params(target_array="arrayB"))
        blade = _blade(fs_exists=False)
        _run_main(module, blade)
        assert "does not exist" in _fail_msg(module)


class TestVersionGates:
    def test_remote_default_exports_requires_2_25(self):
        module = _module(_params(target_array="arrayB", remote_default_exports=[]))
        blade = _blade(connections=[_connection()])
        _run_main(module, blade, api_version="2.21")
        assert "remote_default_exports requires REST 2.25" in _fail_msg(module)
        blade.post_file_system_replica_links.assert_not_called()

    def test_link_type_requires_2_17(self):
        module = _module(_params(target_array="arrayB", link_type="full-replica"))
        blade = _blade(connections=[_connection()])
        _run_main(module, blade, api_version="2.16")
        assert "link_type requires REST 2.17" in _fail_msg(module)
        blade.post_file_system_replica_links.assert_not_called()

    def test_replicate_now_requires_2_17(self):
        module = _module(_params(replicate_now=True))
        blade = _blade(links=[_link(link_type="partial-replica")])
        _run_main(module, blade, api_version="2.16")
        assert "replicate_now requires REST 2.17" in _fail_msg(module)
        blade.patch_file_system_replica_links.assert_not_called()

    def test_gates_pass_on_exact_versions(self):
        module = _module(
            _params(
                target_array="arrayB",
                link_type="partial-replica",
                remote_default_exports=["nfs"],
            )
        )
        blade = _blade(connections=[_connection()])
        _run_main(module, blade, api_version="2.25")
        module.exit_json.assert_called_once_with(changed=True)

    def test_delete_requires_2_10(self):
        module = _module(_params(state="absent"))
        blade = _blade(links=[_link()])
        _run_main(module, blade, api_version="2.9")
        assert "requires REST 2.10" in _fail_msg(module)
        blade.delete_file_system_replica_links.assert_not_called()


class TestPartialReplicaGuards:
    def test_partial_replica_create_rejects_policy(self):
        module = _module(
            _params(target_array="arrayB", link_type="partial-replica", policy="d")
        )
        blade = _blade(connections=[_connection()])
        _run_main(module, blade)
        assert "cannot be attached to partial-replica" in _fail_msg(module)
        blade.post_file_system_replica_links.assert_not_called()

    def test_existing_link_type_mismatch(self):
        module = _module(_params(target_array="arrayB", link_type="partial-replica"))
        blade = _blade(links=[_link(link_type="full-replica")])
        _run_main(module, blade)
        assert "link_type cannot be changed" in _fail_msg(module)

    def test_existing_link_type_match_is_a_noop(self):
        module = _module(_params(target_array="arrayB", link_type="full-replica"))
        blade = _blade(links=[_link(link_type="full-replica")])
        _run_main(module, blade)
        module.exit_json.assert_called_once_with(changed=False)

    def test_existing_partial_link_rejects_policy(self):
        module = _module(_params(policy="daily"))
        blade = _blade(links=[_link(link_type="partial-replica")])
        _run_main(module, blade)
        assert "partial-replica" in _fail_msg(module)
        blade.post_file_system_replica_links_policies.assert_not_called()

    def test_absent_partial_link_fails_with_guidance(self):
        module = _module(_params(state="absent"))
        blade = _blade(links=[_link(link_type="partial-replica", remote_fs="fs1-dr")])
        _run_main(module, blade)
        msg = _fail_msg(module)
        assert "cannot be deleted" in msg
        assert "fs1-dr" in msg
        blade.delete_file_system_replica_links.assert_not_called()

    def test_link_without_link_type_attribute_is_treated_as_full(self):
        """Arrays below REST 2.17 return links without link_type"""
        link = Mock(spec=["remote", "remote_file_system"])
        link.remote = Mock()
        link.remote.name = "arrayB"
        link.remote_file_system = Mock()
        link.remote_file_system.name = "fs1"
        module = _module(_params(state="absent"))
        blade = _blade(links=[link])
        _run_main(module, blade, api_version="2.16")
        blade.delete_file_system_replica_links.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)


class TestReplicateNow:
    def test_replicate_now_patches_partial_link(self):
        module = _module(_params(target_array="arrayB", replicate_now=True))
        blade = _blade(links=[_link(link_type="partial-replica")])
        _run_main(module, blade)
        blade.patch_file_system_replica_links.assert_called_once_with(
            local_file_system_names=["fs1"],
            remote_names=["arrayB"],
            replicate_now=True,
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_replicate_now_check_mode(self):
        module = _module(_params(replicate_now=True), check_mode=True)
        blade = _blade(links=[_link(link_type="partial-replica")])
        _run_main(module, blade)
        blade.patch_file_system_replica_links.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_replicate_now_without_link_fails(self):
        module = _module(_params(target_array="arrayB", replicate_now=True))
        blade = _blade(connections=[_connection()])
        _run_main(module, blade)
        assert "requires an existing replica link" in _fail_msg(module)
        blade.post_file_system_replica_links.assert_not_called()

    def test_replicate_now_on_full_link_fails(self):
        module = _module(_params(replicate_now=True))
        blade = _blade(links=[_link(link_type="full-replica")])
        _run_main(module, blade)
        assert "only supported on partial-replica" in _fail_msg(module)
        blade.patch_file_system_replica_links.assert_not_called()

    def test_replicate_now_with_absent_fails(self):
        module = _module(_params(state="absent", replicate_now=True))
        blade = _blade(links=[_link(link_type="partial-replica")])
        _run_main(module, blade)
        assert "cannot be combined with state=absent" in _fail_msg(module)
        blade.delete_file_system_replica_links.assert_not_called()

    def test_replicate_now_api_error(self):
        module = _module(_params(replicate_now=True))
        blade = _blade(links=[_link(link_type="partial-replica")])
        blade.patch_file_system_replica_links.return_value = _response(status=400)
        _run_main(module, blade)
        assert "Failed to replicate" in _fail_msg(module)


class TestPoliciesAndDelete:
    def test_add_policy(self):
        module = _module(_params(policy="daily"))
        blade = _blade(links=[_link()])
        _run_main(module, blade)
        blade.post_file_system_replica_links_policies.assert_called_once_with(
            policy_names=["daily"],
            local_file_system_names=["fs1"],
            remote_names=["arrayB"],
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_add_policy_idempotent(self):
        module = _module(_params(policy="daily"))
        blade = _blade(links=[_link()], policy_attached=True)
        _run_main(module, blade)
        blade.post_file_system_replica_links_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_add_policy_unknown_policy(self):
        module = _module(_params(policy="nope"))
        blade = _blade(links=[_link()])
        blade.get_policies.return_value = _refused(400, "Policy does not exist.")
        _run_main(module, blade)
        assert _fail_msg(module) == "Selected policy nope does not exist."
        blade.post_file_system_replica_links_policies.assert_not_called()

    def test_remove_policy(self):
        module = _module(_params(policy="daily", state="absent"))
        blade = _blade(links=[_link()], policy_attached=True)
        _run_main(module, blade)
        blade.delete_file_system_replica_links_policies.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    def test_delete_link(self):
        module = _module(_params(state="absent", in_progress=True))
        blade = _blade(links=[_link(remote_fs="fs1-dr")])
        _run_main(module, blade)
        blade.delete_file_system_replica_links.assert_called_once_with(
            local_file_system_names=["fs1"],
            remote_file_system_names=["fs1-dr"],
            remote_names=["arrayB"],
            cancel_in_progress_transfers=True,
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_delete_link_check_mode(self):
        module = _module(_params(state="absent"), check_mode=True)
        blade = _blade(links=[_link()])
        _run_main(module, blade)
        blade.delete_file_system_replica_links.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_delete_selects_link_by_target_array(self):
        links = [_link("arrayB"), _link("arrayC", remote_fs="fs1-c")]
        module = _module(_params(state="absent", target_array="arrayC"))
        blade = _blade(links=links)
        _run_main(module, blade)
        kwargs = blade.delete_file_system_replica_links.call_args.kwargs
        assert kwargs["remote_names"] == ["arrayC"]
        assert kwargs["remote_file_system_names"] == ["fs1-c"]

    def test_absent_without_link_is_a_noop(self):
        module = _module(_params(state="absent"))
        blade = _blade()
        _run_main(module, blade)
        blade.delete_file_system_replica_links.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)


def _refused(status=403, message="Operation not permitted."):
    """An SDK ErrorResponse: it carries errors and has no items attribute."""
    res = Mock(spec=["status_code", "errors"])
    res.status_code = status
    error = Mock()
    error.message = message
    res.errors = [error]
    return res


def _first_error(res):
    return res.errors[0].message


REALM_HINT = (
    "File system rzaudit::fs1 is in a realm; target_array takes a connected "
    "array, a remote realm is not supported as the target"
)
NOT_VISIBLE = (
    "no array connection is visible to this identity (array connections are "
    "not visible to a realm-scoped administrator)"
)


class TestArrayConnectionsRead:
    """A refused read of the array connections is reported, not raised"""

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_create_reports_refused_read(self, check_mode):
        module = _module(_params(target_array="arrayB"), check_mode=check_mode)
        blade = _blade()
        blade.get_array_connections.return_value = _refused()
        with patch(MODULE + ".get_error_message", side_effect=_first_error):
            _run_main(module, blade)
        assert _fail_msg(module) == (
            "Failed to read the array connections. Error: Operation not permitted."
        )
        blade.post_file_system_replica_links.assert_not_called()
        module.exit_json.assert_not_called()

    def test_management_address_lookup_reports_refused_read(self):
        """get_local_rl falls back to the connections for a management address"""
        module = _module(_params(target_array="10.0.0.3", state="absent"))
        blade = _blade(links=[_link("arrayB")])
        blade.get_array_connections.return_value = _refused()
        with patch(MODULE + ".get_error_message", side_effect=_first_error):
            with pytest.raises(SystemExit):
                get_local_rl(module, blade)
        assert _fail_msg(module) == (
            "Failed to read the array connections. Error: Operation not permitted."
        )

    def test_absent_with_refused_read_deletes_nothing(self):
        module = _module(_params(target_array="10.0.0.3", state="absent"))
        blade = _blade(links=[_link("arrayB")])
        blade.get_array_connections.return_value = _refused()
        _run_main(module, blade)
        assert "Failed to read the array connections" in _fail_msg(module)
        blade.delete_file_system_replica_links.assert_not_called()
        module.exit_json.assert_not_called()


class TestNotConnectedMessage:
    """The refusal says what the module looked for and what it cannot see"""

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_realm_administrator_sees_no_connection(self, check_mode):
        """The array answers 200 with no items to a realm-scoped administrator"""
        module = _module(
            _params(name="rzaudit::fs1", target_array="arrayB"),
            check_mode=check_mode,
        )
        blade = _blade(connections=[])
        _run_main(module, blade)
        assert _fail_msg(module) == (
            "Target array arrayB is not connected: " + NOT_VISIBLE + ". " + REALM_HINT
        )
        blade.post_file_system_replica_links.assert_not_called()
        module.exit_json.assert_not_called()

    def test_no_connection_array_level_file_system(self):
        module = _module(_params(target_array="arrayB"))
        blade = _blade(connections=[])
        _run_main(module, blade)
        assert _fail_msg(module) == (
            "Target array arrayB is not connected: " + NOT_VISIBLE
        )
        blade.post_file_system_replica_links.assert_not_called()

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_realm_file_system_target_is_a_remote_realm(self, check_mode):
        """target_array is resolved against the array connections only"""
        module = _module(
            _params(name="rzaudit::fs1", target_array="remote-realm"),
            check_mode=check_mode,
        )
        blade = _blade(connections=[_connection("arrayB")])
        _run_main(module, blade)
        assert _fail_msg(module) == (
            "Target array remote-realm is not connected. " + REALM_HINT
        )
        blade.post_file_system_replica_links.assert_not_called()
        module.exit_json.assert_not_called()

    def test_realm_file_system_target_disconnected(self):
        module = _module(_params(name="rzaudit::fs1", target_array="arrayB"))
        blade = _blade(connections=[_connection(status="disconnected")])
        _run_main(module, blade)
        assert _fail_msg(module) == (
            "Target array arrayB is not connected. " + REALM_HINT
        )

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_array_level_message_is_unchanged(self, check_mode):
        module = _module(_params(target_array="arrayZ"), check_mode=check_mode)
        blade = _blade(connections=[_connection("arrayB")])
        _run_main(module, blade)
        assert _fail_msg(module) == "Target array arrayZ is not connected"
        blade.post_file_system_replica_links.assert_not_called()


class TestRealmNames:
    """realm::name is passed to the array as given, for name and policy"""

    @patch(MODULE + ".LocationReference")
    @patch(MODULE + ".FileSystemReplicaLink")
    def test_create_sends_qualified_names(self, mock_link_model, mock_location):
        module = _module(
            _params(name="rzaudit::fs1", target_array="arrayB", policy="rzaudit::daily")
        )
        blade = _blade(connections=[_connection()])
        _run_main(module, blade)
        blade.get_file_systems.assert_called_once_with(names=["rzaudit::fs1"])
        blade.get_file_system_replica_links.assert_called_once_with(
            local_file_system_names=["rzaudit::fs1"]
        )
        blade.get_policies.assert_called_once_with(names=["rzaudit::daily"])
        mock_location.assert_called_once_with(name="rzaudit::daily")
        kwargs = blade.post_file_system_replica_links.call_args.kwargs
        assert kwargs["local_file_system_names"] == ["rzaudit::fs1"]
        # target_fs defaults to name as given, realm included
        assert kwargs["remote_file_system_names"] == ["rzaudit::fs1"]
        assert kwargs["remote_names"] == ["arrayB"]
        module.exit_json.assert_called_once_with(changed=True)

    def test_create_with_target_fs(self):
        module = _module(
            _params(name="rzaudit::fs1", target_array="arrayB", target_fs="fs1")
        )
        blade = _blade(connections=[_connection()])
        _run_main(module, blade)
        kwargs = blade.post_file_system_replica_links.call_args.kwargs
        assert kwargs["local_file_system_names"] == ["rzaudit::fs1"]
        assert kwargs["remote_file_system_names"] == ["fs1"]

    def test_create_check_mode_sends_nothing(self):
        module = _module(
            _params(name="rzaudit::fs1", target_array="arrayB"), check_mode=True
        )
        blade = _blade(connections=[_connection()])
        _run_main(module, blade)
        blade.post_file_system_replica_links.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_missing_realm_file_system(self):
        """The array answers a missing name of any scope with an error"""
        module = _module(_params(name="rzaudit::fs1", target_array="arrayB"))
        blade = _blade(connections=[_connection()])
        blade.get_file_systems.return_value = _refused(
            400, "File system does not exist."
        )
        blade.get_file_system_replica_links.return_value = _refused(
            400, "File system does not exist."
        )
        _run_main(module, blade)
        assert _fail_msg(module) == (
            "Selected local filesystem rzaudit::fs1 does not exist."
        )
        blade.get_array_connections.assert_not_called()

    def test_add_policy_to_link_with_a_remote_realm(self):
        module = _module(_params(name="rzaudit::fs1", policy="rzaudit::daily"))
        blade = _blade(links=[_link(remote="remote-realm")])
        _run_main(module, blade)
        blade.get_file_system_replica_links_policies.assert_called_once_with(
            local_file_system_names=["rzaudit::fs1"],
            policy_names=["rzaudit::daily"],
            remote_names=["remote-realm"],
        )
        blade.post_file_system_replica_links_policies.assert_called_once_with(
            policy_names=["rzaudit::daily"],
            local_file_system_names=["rzaudit::fs1"],
            remote_names=["remote-realm"],
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_add_policy_idempotent(self):
        module = _module(_params(name="rzaudit::fs1", policy="rzaudit::daily"))
        blade = _blade(links=[_link(remote="remote-realm")], policy_attached=True)
        _run_main(module, blade)
        blade.post_file_system_replica_links_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_existing_link_is_selected_by_remote_name(self):
        """An existing link is found by the name of its remote, array or realm"""
        links = [_link("arrayB"), _link("remote-realm", remote_fs="fs1")]
        module = _module(
            _params(name="rzaudit::fs1", target_array="remote-realm", state="absent")
        )
        blade = _blade(links=links)
        _run_main(module, blade)
        blade.get_array_connections.assert_not_called()
        blade.delete_file_system_replica_links.assert_called_once_with(
            local_file_system_names=["rzaudit::fs1"],
            remote_file_system_names=["fs1"],
            remote_names=["remote-realm"],
            cancel_in_progress_transfers=False,
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_absent_without_link_is_a_noop(self):
        module = _module(
            _params(name="rzaudit::fs1", target_array="arrayB", state="absent")
        )
        blade = _blade(connections=[])
        _run_main(module, blade)
        blade.get_array_connections.assert_not_called()
        blade.delete_file_system_replica_links.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)


class TestTargetArrayLetterCase:
    """The array matches the name of a connected array in any letter case"""

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_create_uses_the_name_the_array_has(self, check_mode):
        module = _module(_params(target_array="ARRAYB"), check_mode=check_mode)
        blade = _blade(connections=[_connection("arrayB")])
        _run_main(module, blade)
        module.fail_json.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)
        if check_mode:
            blade.post_file_system_replica_links.assert_not_called()
        else:
            kwargs = blade.post_file_system_replica_links.call_args.kwargs
            assert kwargs["remote_names"] == ["arrayB"]

    def test_existing_link_is_not_created_again(self):
        module = _module(_params(target_array="ARRAYB"))
        blade = _blade(links=[_link("arrayB")], connections=[_connection("arrayB")])
        _run_main(module, blade)
        blade.get_array_connections.assert_not_called()
        blade.post_file_system_replica_links.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_delete_selects_the_link(self):
        links = [_link("arrayB"), _link("arrayC", remote_fs="fs1-c")]
        module = _module(_params(state="absent", target_array="ArrayC"))
        blade = _blade(links=links)
        _run_main(module, blade)
        blade.delete_file_system_replica_links.assert_called_once_with(
            local_file_system_names=["fs1"],
            remote_file_system_names=["fs1-c"],
            remote_names=["arrayC"],
            cancel_in_progress_transfers=False,
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_another_array_is_still_not_connected(self):
        module = _module(_params(target_array="ARRAYZ"))
        blade = _blade(connections=[_connection("arrayB")])
        _run_main(module, blade)
        assert _fail_msg(module) == "Target array ARRAYZ is not connected"
        blade.post_file_system_replica_links.assert_not_called()


ONE_NAME = "{0} {1} is not one name: the array reads * as a pattern and a comma as a separator of names."


class TestOneNamePerOption:
    """A pattern or a list is refused before anything is read"""

    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize(
        "option,value",
        [
            ("name", "fs*"),
            ("name", "fs1,fs2"),
            ("name", "rzaudit::*"),
            ("target_array", "array*"),
            ("target_array", "arrayB,arrayC"),
            ("target_fs", "fs1,fs2"),
            ("policy", "dai*"),
            ("policy", "daily,weekly"),
        ],
    )
    def test_pattern_or_list_is_refused(self, option, value, state):
        params = _params(target_array="arrayB", state=state)
        params[option] = value
        module = _module(params, check_mode=True)
        blade = _blade(links=[_link()], connections=[_connection()])
        _run_main(module, blade)
        assert _fail_msg(module) == ONE_NAME.format(option, value)
        assert blade.mock_calls == []
        module.exit_json.assert_not_called()

    @pytest.mark.parametrize("name", ["", "   "])
    def test_empty_name_is_refused(self, name):
        module = _module(_params(name=name, target_array="arrayB"))
        blade = _blade(connections=[_connection()])
        _run_main(module, blade)
        assert _fail_msg(module) == (
            "name is empty; it takes the name of one file system."
        )
        assert blade.mock_calls == []

    def test_blanks_around_names_are_dropped(self):
        """The array ignores blanks around a name; target_array is compared here"""
        module = _module(
            _params(
                name=" fs1 ",
                target_array=" arrayB ",
                target_fs=" fs1-dr ",
                policy=" daily ",
            )
        )
        blade = _blade(connections=[_connection()])
        _run_main(module, blade)
        blade.get_file_systems.assert_called_once_with(names=["fs1"])
        blade.get_policies.assert_called_once_with(names=["daily"])
        kwargs = blade.post_file_system_replica_links.call_args.kwargs
        assert kwargs["local_file_system_names"] == ["fs1"]
        assert kwargs["remote_file_system_names"] == ["fs1-dr"]
        assert kwargs["remote_names"] == ["arrayB"]
        module.exit_json.assert_called_once_with(changed=True)


class TestRefusedReads:
    """Only "does not exist" means absent; any other answer is reported"""

    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_file_system_read(self, state):
        module = _module(_params(target_array="arrayB", state=state))
        blade = _blade(links=[_link()], connections=[_connection()])
        blade.get_file_systems.return_value = _refused()
        _run_main(module, blade)
        assert _fail_msg(module) == (
            "Failed to read file system fs1. Error: Operation not permitted."
        )
        blade.get_file_system_replica_links.assert_not_called()
        module.exit_json.assert_not_called()

    def test_missing_file_system_reads_no_link(self):
        module = _module(_params(target_array="arrayB"))
        blade = _blade(connections=[_connection()])
        blade.get_file_systems.return_value = _refused(
            400, "File system does not exist."
        )
        _run_main(module, blade)
        assert _fail_msg(module) == "Selected local filesystem fs1 does not exist."
        blade.get_file_system_replica_links.assert_not_called()

    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_replica_link_read(self, state):
        module = _module(_params(target_array="arrayB", state=state))
        blade = _blade(connections=[_connection()])
        blade.get_file_system_replica_links.return_value = _refused()
        _run_main(module, blade)
        assert _fail_msg(module) == (
            "Failed to read the replica links of file system fs1. "
            "Error: Operation not permitted."
        )
        blade.post_file_system_replica_links.assert_not_called()
        blade.delete_file_system_replica_links.assert_not_called()
        module.exit_json.assert_not_called()

    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_link_policy_read(self, state):
        module = _module(_params(policy="daily", state=state))
        blade = _blade(links=[_link()], policy_attached=True)
        blade.get_file_system_replica_links_policies.return_value = _refused()
        _run_main(module, blade)
        assert _fail_msg(module) == (
            "Failed to read the policies of the replica link from fs1 to arrayB. "
            "Error: Operation not permitted."
        )
        blade.post_file_system_replica_links_policies.assert_not_called()
        blade.delete_file_system_replica_links_policies.assert_not_called()
        module.exit_json.assert_not_called()

    def test_link_policy_that_does_not_exist_is_not_attached(self):
        module = _module(_params(policy="daily", state="absent"))
        blade = _blade(links=[_link()])
        blade.get_file_system_replica_links_policies.return_value = _refused(
            400, "Policy does not exist."
        )
        _run_main(module, blade)
        module.fail_json.assert_not_called()
        blade.delete_file_system_replica_links_policies.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_policy_read(self, state):
        module = _module(_params(policy="daily", state=state))
        blade = _blade(links=[_link()], policy_attached=True)
        blade.get_policies.return_value = _refused()
        _run_main(module, blade)
        assert _fail_msg(module) == (
            "Failed to read policy daily. Error: Operation not permitted."
        )
        blade.post_file_system_replica_links_policies.assert_not_called()
        blade.delete_file_system_replica_links_policies.assert_not_called()

    def test_policy_answered_without_items_does_not_exist(self):
        module = _module(_params(policy="daily"))
        blade = _blade(links=[_link()])
        blade.get_policies.return_value = _response()
        _run_main(module, blade)
        assert _fail_msg(module) == "Selected policy daily does not exist."
        blade.post_file_system_replica_links_policies.assert_not_called()
