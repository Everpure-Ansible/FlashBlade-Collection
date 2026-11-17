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
    blade.get_policies.return_value = _response()
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


def _run_main(module, blade, api_version="2.30"):
    """Run main() with the module, SDK client and REST version patched in."""
    with patch(MODULE + ".AnsibleModule", return_value=module), patch(
        MODULE + ".get_system", return_value=blade
    ), patch(MODULE + ".get_rest_api_version", return_value=api_version), patch(
        MODULE + ".LooseVersion", RealLooseVersion
    ), patch(
        MODULE + ".HAS_PYPURECLIENT", True
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

    def test_returns_none_on_api_error(self):
        module = _module(_params())
        blade = _blade()
        blade.get_file_system_replica_links.return_value = _response(status=400)
        assert get_local_rl(module, blade) is None


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
        blade.get_policies.return_value = _response(status=400)
        _run_main(module, blade)
        assert "does not exist" in _fail_msg(module)

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
