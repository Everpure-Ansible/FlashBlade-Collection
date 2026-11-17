# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for the purefb_network module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
from unittest.mock import MagicMock, Mock, patch

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

from plugins.modules.purefb_network import (  # noqa: E402
    _attached_server_name,
    _server_in_sync,
    create_iface,
    delete_iface,
    main,
    modify_iface,
)

MODULE_PATH = "plugins.modules.purefb_network"


def _version(value):
    """Comparable stand-in for LooseVersion (module_utils is mocked)."""
    return tuple(int(part) for part in value.split("."))


def _module(**overrides):
    params = {
        "name": "vip1",
        "state": "present",
        "address": "10.0.0.10",
        "services": None,
        "itype": "vip",
        "attached_server": None,
        "rdma_enabled": None,
    }
    params.update(overrides)
    module = Mock()
    module.params = params
    module.check_mode = False
    module.fail_json = Mock(side_effect=SystemExit)
    module.exit_json = Mock(side_effect=SystemExit)
    return module


def _iface(address="10.0.0.10", attached="_array_server", services=None, rdma=True):
    """An interface shaped like a GET result on a REST 2.28+ array.

    ``spec`` matters: the real NetworkInterface raises AttributeError for
    anything outside its field set, and there is no singular
    ``attached_server`` field. Using a bare Mock here would hide that.
    """
    iface = Mock(
        spec=[
            "name",
            "address",
            "services",
            "type",
            "attached_servers",
            "rdma_enabled",
        ]
    )
    iface.name = "vip1"
    iface.address = address
    iface.services = ["data"] if services is None else services
    iface.type = "vip"
    iface.rdma_enabled = rdma
    if attached is None:
        iface.attached_servers = []
    else:
        ref = Mock(spec=["name"])
        ref.name = attached
        iface.attached_servers = [ref]
    return iface


def _old_iface(address="10.0.0.10"):
    """An interface from an array below REST 2.28: no rdma_enabled field."""
    iface = Mock(spec=["name", "address", "services", "type", "attached_servers"])
    iface.name = "vip1"
    iface.address = address
    iface.services = ["data"]
    iface.type = "vip"
    iface.attached_servers = []
    return iface


def _blade(status_code=200):
    blade = Mock()
    response = Mock()
    response.status_code = status_code
    response.items = []
    for call in (
        "get_network_interfaces",
        "post_network_interfaces",
        "patch_network_interfaces",
        "delete_network_interfaces",
    ):
        getattr(blade, call).return_value = response
    return blade


def _run(func, module, blade):
    try:
        func(module, blade)
    except SystemExit:
        pass


class TestAttachedServerName:
    def test_reads_the_name_out_of_the_list(self):
        assert _attached_server_name(_iface(attached="fred")) == "fred"

    def test_none_when_no_server_attached(self):
        assert _attached_server_name(_iface(attached=None)) is None

    def test_none_when_the_field_is_absent(self):
        assert _attached_server_name(Mock(spec=["name"])) is None


class TestServerInSync:
    def test_same_name_is_in_sync(self):
        assert _server_in_sync("fred", "fred", ["data"])

    def test_different_name_is_not(self):
        assert not _server_in_sync("fred", "_array_server", ["data"])

    def test_detach_with_nothing_attached_is_in_sync(self):
        assert _server_in_sync("", None, ["replication"])

    def test_detach_from_default_server_on_data_is_in_sync(self):
        """PATCH [] on a data VIP comes straight back as _array_server."""
        assert _server_in_sync("", "_array_server", ["data"])

    def test_detach_from_default_server_on_sts_is_in_sync(self):
        assert _server_in_sync("", "_array_server", ["sts"])

    def test_detach_from_a_named_server_on_data_is_not(self):
        assert not _server_in_sync("", "fred", ["data"])

    def test_detach_when_moving_to_egress_only_is_in_sync(self):
        """The array detaches on the services change itself."""
        assert _server_in_sync("", "_array_server", ["egress-only"])
        assert _server_in_sync("", "fred", ["egress-only"])

    def test_detach_from_default_server_on_replication_is_not(self):
        assert not _server_in_sync("", "_array_server", ["replication"])


class TestCreateIface:
    @patch(MODULE_PATH + ".NetworkInterface")
    def test_defaults_to_data_with_nothing_else_set(self, mock_ni):
        """Omitted services means data; unset options are not sent so the
        array defaults (RDMA on, _array_server) apply."""
        module = _module()
        blade = _blade()
        _run(create_iface, module, blade)
        mock_ni.assert_called_once_with(
            address="10.0.0.10", services=["data"], type="vip"
        )
        blade.post_network_interfaces.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".NetworkInterface")
    def test_attached_server_is_sent_as_a_list_of_references(self, mock_ni):
        """The API field is attached_servers, plural, and a list."""
        module = _module(attached_server="realm-1::server-1")
        blade = _blade()
        _run(create_iface, module, blade)
        assert mock_ni.call_args[1]["attached_servers"] == [
            {"name": "realm-1::server-1"}
        ]
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".NetworkInterface")
    def test_empty_attached_server_is_not_sent(self, mock_ni):
        """'' is the array default on create, so nothing is sent for it."""
        module = _module(attached_server="", services="egress-only")
        blade = _blade()
        _run(create_iface, module, blade)
        assert "attached_servers" not in mock_ni.call_args[1]
        assert mock_ni.call_args[1]["services"] == ["egress-only"]

    @patch(MODULE_PATH + ".NetworkInterface")
    def test_rdma_enabled_false_is_sent(self, mock_ni):
        module = _module(services="data", rdma_enabled=False)
        blade = _blade()
        _run(create_iface, module, blade)
        assert mock_ni.call_args[1]["rdma_enabled"] is False

    @patch(MODULE_PATH + ".NetworkInterface")
    def test_sts_service_is_sent(self, mock_ni):
        module = _module(services="sts")
        blade = _blade()
        _run(create_iface, module, blade)
        assert mock_ni.call_args[1]["services"] == ["sts"]
        assert "rdma_enabled" not in mock_ni.call_args[1]

    @patch(MODULE_PATH + ".NetworkInterface")
    def test_check_mode_makes_no_call(self, mock_ni):
        module = _module(attached_server="fred")
        module.check_mode = True
        blade = _blade()
        _run(create_iface, module, blade)
        blade.post_network_interfaces.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".get_error_message")
    @patch(MODULE_PATH + ".NetworkInterface")
    def test_fails_on_error_response(self, mock_ni, mock_gem):
        mock_gem.return_value = "boom"
        module = _module()
        blade = _blade(status_code=400)
        _run(create_iface, module, blade)
        module.fail_json.assert_called_once()
        assert "creation failed" in module.fail_json.call_args[1]["msg"]


class TestModifyIface:
    @patch(MODULE_PATH + ".get_iface")
    def test_no_change_when_nothing_differs(self, mock_get):
        mock_get.return_value = _iface()
        module = _module(services="data", attached_server="_array_server")
        blade = _blade()
        _run(modify_iface, module, blade)
        blade.patch_network_interfaces.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE_PATH + ".get_iface")
    def test_omitted_options_change_nothing(self, mock_get):
        """A task with only name and address leaves services, server and
        RDMA alone, whatever they are."""
        mock_get.return_value = _iface(
            attached="fred", services=["replication"], rdma=False
        )
        module = _module()
        blade = _blade()
        _run(modify_iface, module, blade)
        blade.patch_network_interfaces.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE_PATH + ".get_iface")
    def test_attached_server_already_correct_is_not_a_change(self, mock_get):
        """Re-running an unchanged task must not report changed."""
        mock_get.return_value = _iface(attached="fred")
        module = _module(attached_server="fred")
        blade = _blade()
        _run(modify_iface, module, blade)
        blade.patch_network_interfaces.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE_PATH + ".NetworkInterfacePatch")
    @patch(MODULE_PATH + ".get_iface")
    def test_moves_to_a_different_server(self, mock_get, mock_patch):
        mock_get.return_value = _iface(attached="_array_server")
        module = _module(attached_server="fred")
        blade = _blade()
        _run(modify_iface, module, blade)
        mock_patch.assert_called_once_with(attached_servers=[{"name": "fred"}])
        blade.patch_network_interfaces.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".NetworkInterfacePatch")
    @patch(MODULE_PATH + ".get_iface")
    def test_attaches_when_nothing_is_attached_yet(self, mock_get, mock_patch):
        mock_get.return_value = _iface(attached=None)
        module = _module(attached_server="fred")
        blade = _blade()
        _run(modify_iface, module, blade)
        mock_patch.assert_called_once_with(attached_servers=[{"name": "fred"}])
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".NetworkInterfacePatch")
    @patch(MODULE_PATH + ".get_iface")
    def test_detach_sends_an_empty_list(self, mock_get, mock_patch):
        mock_get.return_value = _iface(attached="fred")
        module = _module(attached_server="")
        blade = _blade()
        _run(modify_iface, module, blade)
        mock_patch.assert_called_once_with(attached_servers=[])
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".get_iface")
    def test_detach_from_default_server_on_data_is_not_a_change(self, mock_get):
        """The array would hand _array_server straight back."""
        mock_get.return_value = _iface(attached="_array_server")
        module = _module(attached_server="")
        blade = _blade()
        _run(modify_iface, module, blade)
        blade.patch_network_interfaces.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE_PATH + ".get_iface")
    def test_detach_from_default_server_on_sts_is_not_a_change(self, mock_get):
        mock_get.return_value = _iface(
            attached="_array_server", services=["sts"], rdma=False
        )
        module = _module(services="sts", attached_server="")
        blade = _blade()
        _run(modify_iface, module, blade)
        blade.patch_network_interfaces.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE_PATH + ".NetworkInterfacePatch")
    @patch(MODULE_PATH + ".get_iface")
    def test_address_change_alone(self, mock_get, mock_patch):
        mock_get.return_value = _iface(address="10.0.0.9")
        module = _module(address="10.0.0.10")
        blade = _blade()
        _run(modify_iface, module, blade)
        mock_patch.assert_called_once_with(address="10.0.0.10")
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".NetworkInterfacePatch")
    @patch(MODULE_PATH + ".get_iface")
    def test_services_change_is_applied(self, mock_get, mock_patch):
        """The shipped module ignored a services change on an existing VIP."""
        mock_get.return_value = _iface(
            attached=None, services=["egress-only"], rdma=False
        )
        module = _module(services="data")
        blade = _blade()
        _run(modify_iface, module, blade)
        mock_patch.assert_called_once_with(services=["data"])
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".NetworkInterfacePatch")
    @patch(MODULE_PATH + ".get_iface")
    def test_leaving_data_with_rdma_on_disables_rdma_in_the_same_patch(
        self, mock_get, mock_patch
    ):
        """The array rejects the services change otherwise."""
        mock_get.return_value = _iface(rdma=True)
        module = _module(services="egress-only")
        blade = _blade()
        _run(modify_iface, module, blade)
        mock_patch.assert_called_once_with(services=["egress-only"], rdma_enabled=False)
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".NetworkInterfacePatch")
    @patch(MODULE_PATH + ".get_iface")
    def test_leaving_data_with_rdma_off_sends_services_only(self, mock_get, mock_patch):
        mock_get.return_value = _iface(rdma=False)
        module = _module(services="egress-only")
        blade = _blade()
        _run(modify_iface, module, blade)
        mock_patch.assert_called_once_with(services=["egress-only"])

    @patch(MODULE_PATH + ".NetworkInterfacePatch")
    @patch(MODULE_PATH + ".get_iface")
    def test_leaving_data_on_an_old_array_never_mentions_rdma(
        self, mock_get, mock_patch
    ):
        """Below REST 2.28 the model has no rdma_enabled; sending one would
        be rejected."""
        mock_get.return_value = _old_iface()
        module = _module(services="replication")
        blade = _blade()
        _run(modify_iface, module, blade)
        mock_patch.assert_called_once_with(services=["replication"])

    @patch(MODULE_PATH + ".NetworkInterfacePatch")
    @patch(MODULE_PATH + ".get_iface")
    def test_leaving_data_for_egress_only_does_not_also_detach(
        self, mock_get, mock_patch
    ):
        """attached_server '' with egress-only: the array detaches itself."""
        mock_get.return_value = _iface(attached="_array_server", rdma=True)
        module = _module(services="egress-only", attached_server="")
        blade = _blade()
        _run(modify_iface, module, blade)
        mock_patch.assert_called_once_with(services=["egress-only"], rdma_enabled=False)

    @patch(MODULE_PATH + ".NetworkInterfacePatch")
    @patch(MODULE_PATH + ".get_iface")
    def test_rdma_toggle(self, mock_get, mock_patch):
        mock_get.return_value = _iface(rdma=True)
        module = _module(rdma_enabled=False)
        blade = _blade()
        _run(modify_iface, module, blade)
        mock_patch.assert_called_once_with(rdma_enabled=False)
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".get_iface")
    def test_rdma_already_set_is_not_a_change(self, mock_get):
        mock_get.return_value = _iface(rdma=False)
        module = _module(rdma_enabled=False)
        blade = _blade()
        _run(modify_iface, module, blade)
        blade.patch_network_interfaces.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE_PATH + ".get_iface")
    def test_rdma_true_on_a_non_data_interface_is_refused(self, mock_get):
        """services omitted, so the current (egress-only) service decides."""
        mock_get.return_value = _iface(
            attached=None, services=["egress-only"], rdma=False
        )
        module = _module(rdma_enabled=True)
        blade = _blade()
        _run(modify_iface, module, blade)
        module.fail_json.assert_called_once()
        assert "data service" in module.fail_json.call_args[1]["msg"]
        blade.patch_network_interfaces.assert_not_called()

    @patch(MODULE_PATH + ".NetworkInterfacePatch")
    @patch(MODULE_PATH + ".get_iface")
    def test_everything_changes_in_one_patch(self, mock_get, mock_patch):
        mock_get.return_value = _iface(
            address="10.0.0.9", attached=None, services=["egress-only"], rdma=False
        )
        module = _module(
            address="10.0.0.10",
            services="data",
            attached_server="fred",
            rdma_enabled=True,
        )
        blade = _blade()
        _run(modify_iface, module, blade)
        assert blade.patch_network_interfaces.call_count == 1
        mock_patch.assert_called_once_with(
            address="10.0.0.10",
            services=["data"],
            rdma_enabled=True,
            attached_servers=[{"name": "fred"}],
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".get_iface")
    def test_omitting_attached_server_never_detaches(self, mock_get):
        """An unset option must not strip the interface's current server."""
        mock_get.return_value = _iface(attached="fred")
        module = _module(attached_server=None)
        blade = _blade()
        _run(modify_iface, module, blade)
        blade.patch_network_interfaces.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE_PATH + ".NetworkInterfacePatch")
    @patch(MODULE_PATH + ".get_iface")
    def test_check_mode_reports_change_without_patching(self, mock_get, mock_patch):
        mock_get.return_value = _iface(attached="_array_server")
        module = _module(attached_server="fred", rdma_enabled=False)
        module.check_mode = True
        blade = _blade()
        _run(modify_iface, module, blade)
        blade.patch_network_interfaces.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".get_error_message")
    @patch(MODULE_PATH + ".NetworkInterfacePatch")
    @patch(MODULE_PATH + ".get_iface")
    def test_fails_on_error_response(self, mock_get, mock_patch, mock_gem):
        mock_gem.return_value = "boom"
        mock_get.return_value = _iface(rdma=True)
        module = _module(rdma_enabled=False)
        blade = _blade(status_code=400)
        _run(modify_iface, module, blade)
        module.fail_json.assert_called_once()
        assert "boom" in module.fail_json.call_args[1]["msg"]


class TestDeleteIface:
    def test_deletes(self):
        module = _module()
        blade = _blade()
        _run(delete_iface, module, blade)
        blade.delete_network_interfaces.assert_called_once_with(names=["vip1"])
        module.exit_json.assert_called_once_with(changed=True)

    def test_check_mode_makes_no_call(self):
        module = _module()
        module.check_mode = True
        blade = _blade()
        _run(delete_iface, module, blade)
        blade.delete_network_interfaces.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)


@patch(MODULE_PATH + ".LooseVersion", _version)
@patch(MODULE_PATH + ".delete_iface")
@patch(MODULE_PATH + ".modify_iface")
@patch(MODULE_PATH + ".create_iface")
@patch(MODULE_PATH + ".get_iface")
@patch(MODULE_PATH + ".get_rest_api_version")
@patch(MODULE_PATH + ".get_system")
@patch(MODULE_PATH + ".AnsibleModule")
class TestMain:
    """Version gates, option checks and dispatch."""

    def _setup(self, mock_am, mock_gs, mock_ver, mock_get, version, iface, **params):
        module = _module(**params)
        mock_am.return_value = module
        mock_gs.return_value = _blade()
        mock_ver.return_value = version
        mock_get.return_value = iface
        return module

    def _main(self):
        try:
            main()
        except SystemExit:
            pass

    @pytest.mark.parametrize(
        "params,version,option",
        [
            ({"attached_server": ""}, "2.15", "attached_server"),
            ({"attached_server": "fred"}, "2.15", "attached_server"),
            ({"services": "sts"}, "2.16", "services sts"),
            ({"services": "egress-only"}, "2.18", "services egress-only"),
            ({"rdma_enabled": False}, "2.27", "rdma_enabled"),
        ],
    )
    def test_option_below_its_rest_version_fails(
        self,
        mock_am,
        mock_gs,
        mock_ver,
        mock_get,
        mock_create,
        mock_modify,
        mock_delete,
        params,
        version,
        option,
    ):
        module = self._setup(
            mock_am, mock_gs, mock_ver, mock_get, version, None, **params
        )
        self._main()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert option in msg and version in msg
        mock_create.assert_not_called()

    @pytest.mark.parametrize(
        "params,version",
        [
            ({"attached_server": ""}, "2.16"),
            ({"services": "sts"}, "2.17"),
            ({"services": "egress-only"}, "2.19"),
            ({"rdma_enabled": True, "services": "data"}, "2.28"),
            ({"rdma_enabled": True}, "2.30"),
        ],
    )
    def test_option_at_its_rest_version_creates(
        self,
        mock_am,
        mock_gs,
        mock_ver,
        mock_get,
        mock_create,
        mock_modify,
        mock_delete,
        params,
        version,
    ):
        module = self._setup(
            mock_am, mock_gs, mock_ver, mock_get, version, None, **params
        )
        self._main()
        module.fail_json.assert_not_called()
        mock_create.assert_called_once()

    @pytest.mark.parametrize(
        "params,text",
        [
            ({"rdma_enabled": True, "services": "egress-only"}, "data service"),
            ({"rdma_enabled": True, "services": "sts"}, "data service"),
            ({"rdma_enabled": True, "services": "replication"}, "data service"),
            ({"services": "egress-only", "attached_server": "fred"}, "egress-only"),
            ({"services": "sts", "attached_server": "fred"}, "_array_server"),
        ],
    )
    def test_combinations_the_array_rejects_fail_early(
        self,
        mock_am,
        mock_gs,
        mock_ver,
        mock_get,
        mock_create,
        mock_modify,
        mock_delete,
        params,
        text,
    ):
        module = self._setup(
            mock_am, mock_gs, mock_ver, mock_get, "2.30", None, **params
        )
        self._main()
        module.fail_json.assert_called_once()
        assert text in module.fail_json.call_args[1]["msg"]
        mock_create.assert_not_called()

    def test_sts_with_the_default_server_is_allowed(
        self,
        mock_am,
        mock_gs,
        mock_ver,
        mock_get,
        mock_create,
        mock_modify,
        mock_delete,
    ):
        module = self._setup(
            mock_am,
            mock_gs,
            mock_ver,
            mock_get,
            "2.30",
            None,
            services="sts",
            attached_server="_array_server",
        )
        self._main()
        module.fail_json.assert_not_called()
        mock_create.assert_called_once()

    def test_existing_interface_is_modified(
        self,
        mock_am,
        mock_gs,
        mock_ver,
        mock_get,
        mock_create,
        mock_modify,
        mock_delete,
    ):
        self._setup(mock_am, mock_gs, mock_ver, mock_get, "2.30", _iface())
        self._main()
        mock_modify.assert_called_once()
        mock_create.assert_not_called()

    def test_absent_deletes_an_existing_interface(
        self,
        mock_am,
        mock_gs,
        mock_ver,
        mock_get,
        mock_create,
        mock_modify,
        mock_delete,
    ):
        self._setup(
            mock_am, mock_gs, mock_ver, mock_get, "2.30", _iface(), state="absent"
        )
        self._main()
        mock_delete.assert_called_once()

    def test_absent_without_interface_is_unchanged(
        self,
        mock_am,
        mock_gs,
        mock_ver,
        mock_get,
        mock_create,
        mock_modify,
        mock_delete,
    ):
        """No version gate applies to absent, even with options set."""
        module = self._setup(
            mock_am,
            mock_gs,
            mock_ver,
            mock_get,
            "2.15",
            None,
            state="absent",
            rdma_enabled=True,
        )
        self._main()
        module.exit_json.assert_called_once_with(changed=False)
        module.fail_json.assert_not_called()
        mock_delete.assert_not_called()
