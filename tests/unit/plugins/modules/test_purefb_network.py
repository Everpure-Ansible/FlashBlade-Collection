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
    get_iface,
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


# ---------------------------------------------------------------------------
# Interfaces in a realm, checked reads and the name of one interface
# ---------------------------------------------------------------------------


def _message(res):
    """Stand-in for get_error_message (module_utils is mocked)."""
    return res.errors[0].message


def _error(text):
    """An error answer of the array: HTTP 400 and one message."""
    res = Mock()
    res.status_code = 400
    res.errors = [Mock(message=text)]
    return res


def _found(*names):
    """A 200 answer that holds one object per name."""
    res = Mock()
    res.status_code = 200
    res.items = []
    for name in names:
        item = Mock(spec=["name"])
        item.name = name
        res.items.append(item)
    return res


def _realm_iface(
    name="tenant1::vip1",
    address="10.0.0.10",
    attached="tenant1::srv1",
    services=None,
    rdma=False,
):
    """An interface in a realm as the array returns it: the name and the
    attached server both carry the realm."""
    iface = Mock(
        spec=[
            "name",
            "realms",
            "address",
            "services",
            "type",
            "attached_servers",
            "rdma_enabled",
        ]
    )
    iface.name = name
    realm = Mock(spec=["name"])
    realm.name = name.rpartition("::")[0]
    iface.realms = [realm]
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


def _server_blade(*existing):
    """A blade that holds the given servers and answers a look-up as the
    array does: the stored names, or "Server does not exist."."""
    blade = _blade()
    known = dict((name.lower(), name) for name in existing)

    def get_servers(names):
        if [name for name in names if name.lower() not in known]:
            return _error("Server does not exist.")
        return _found(*[known[name.lower()] for name in names])

    blade.get_servers.side_effect = get_servers
    return blade


def test_server_name_in_another_case_is_in_sync():
    """The array matches a server name without regard to case."""
    assert _server_in_sync("TENANT1::srv1", "tenant1::srv1", ["data"])
    assert _server_in_sync("Fred", "fred", ["replication"])


@patch(MODULE_PATH + ".get_error_message", _message)
class TestGetIface:
    def test_returns_the_interface_of_that_name(self):
        module = _module()
        blade = _blade()
        blade.get_network_interfaces.return_value = _found("vip1")
        assert get_iface(module, blade).name == "vip1"
        blade.get_network_interfaces.assert_called_once_with(names=["vip1"])

    def test_name_in_another_case_is_the_same_interface(self):
        """The array answers with the name as it holds it."""
        module = _module(name="TENANT1::vip1")
        blade = _blade()
        blade.get_network_interfaces.return_value = _found("tenant1::vip1")
        assert get_iface(module, blade).name == "tenant1::vip1"

    def test_does_not_exist_is_absent(self):
        module = _module(name="tenant1::vip1")
        blade = _blade()
        blade.get_network_interfaces.return_value = _error("Network does not exist.")
        assert get_iface(module, blade) is None
        module.fail_json.assert_not_called()

    def test_answer_without_items_is_absent(self):
        module = _module()
        blade = _blade()
        blade.get_network_interfaces.return_value = _found()
        assert get_iface(module, blade) is None
        module.fail_json.assert_not_called()

    def test_refused_read_fails_with_the_message_of_the_array(self):
        module = _module()
        blade = _blade()
        blade.get_network_interfaces.return_value = _error("Operation not permitted.")
        with pytest.raises(SystemExit):
            get_iface(module, blade)
        msg = module.fail_json.call_args[1]["msg"]
        assert "Operation not permitted." in msg
        assert "vip1" in msg

    def test_answer_with_interfaces_of_another_name_fails(self):
        """None of them is the interface the task names."""
        module = _module()
        blade = _blade()
        blade.get_network_interfaces.return_value = _found("vip10", "vip11")
        with pytest.raises(SystemExit):
            get_iface(module, blade)
        assert "vip10" in module.fail_json.call_args[1]["msg"]


@patch(MODULE_PATH + ".get_error_message", _message)
@patch(MODULE_PATH + ".NetworkInterfacePatch")
@patch(MODULE_PATH + ".get_iface")
class TestModifyRealmServer:
    """attached_server on an interface in a realm."""

    def test_bare_name_of_the_attached_server_is_not_a_change(
        self, mock_get, mock_patch
    ):
        """The array holds the server of a realm interface as realm::server."""
        mock_get.return_value = _realm_iface()
        module = _module(name="tenant1::vip1", attached_server="srv1")
        blade = _server_blade("tenant1::srv1", "srv1")
        _run(modify_iface, module, blade)
        blade.patch_network_interfaces.assert_not_called()
        blade.get_servers.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_bare_name_of_another_server_is_sent_with_the_realm(
        self, mock_get, mock_patch
    ):
        mock_get.return_value = _realm_iface()
        module = _module(name="tenant1::vip1", attached_server="srv2")
        blade = _server_blade("tenant1::srv1", "tenant1::srv2", "srv2")
        _run(modify_iface, module, blade)
        mock_patch.assert_called_once_with(attached_servers=[{"name": "tenant1::srv2"}])
        blade.get_servers.assert_called_once_with(names=["tenant1::srv2"])
        module.exit_json.assert_called_once_with(changed=True)

    def test_realm_is_the_one_of_the_name_the_array_holds(self, mock_get, mock_patch):
        mock_get.return_value = _realm_iface()
        module = _module(name="TENANT1::vip1", attached_server="srv1")
        blade = _server_blade("tenant1::srv1")
        _run(modify_iface, module, blade)
        blade.patch_network_interfaces.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_qualified_name_in_another_case_is_not_a_change(self, mock_get, mock_patch):
        mock_get.return_value = _realm_iface()
        module = _module(name="tenant1::vip1", attached_server="TENANT1::SRV1")
        blade = _server_blade("tenant1::srv1")
        _run(modify_iface, module, blade)
        blade.patch_network_interfaces.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_array_level_name_in_another_case_is_not_a_change(
        self, mock_get, mock_patch
    ):
        mock_get.return_value = _iface(attached="fred")
        module = _module(attached_server="FRED")
        blade = _server_blade("fred")
        _run(modify_iface, module, blade)
        blade.patch_network_interfaces.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_array_level_bare_name_is_sent_as_given(self, mock_get, mock_patch):
        """Nothing is completed for an interface outside of a realm."""
        mock_get.return_value = _iface(attached="_array_server")
        module = _module(attached_server="fred")
        blade = _server_blade("fred", "tenant1::fred")
        _run(modify_iface, module, blade)
        mock_patch.assert_called_once_with(attached_servers=[{"name": "fred"}])
        module.exit_json.assert_called_once_with(changed=True)

    def test_default_server_is_never_completed_with_the_realm(
        self, mock_get, mock_patch
    ):
        """The array reads _array_server as the array-level server whatever
        the interface, and main() refuses it for an interface in a realm."""
        mock_get.return_value = _realm_iface()
        module = _module(name="tenant1::vip1", attached_server="_array_server")
        blade = _server_blade("_array_server", "tenant1::srv1")
        _run(modify_iface, module, blade)
        blade.get_servers.assert_called_once_with(names=["_array_server"])
        mock_patch.assert_called_once_with(attached_servers=[{"name": "_array_server"}])

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_server_that_does_not_exist_fails_before_the_request(
        self, mock_get, mock_patch, check_mode
    ):
        """A bare name is not looked up at array level."""
        mock_get.return_value = _realm_iface()
        module = _module(name="tenant1::vip1", attached_server="srv9")
        module.check_mode = check_mode
        blade = _server_blade("tenant1::srv1", "srv9")
        _run(modify_iface, module, blade)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "tenant1::srv9" in msg
        assert "does not exist" in msg
        assert "attached_server srv9 was looked up as tenant1::srv9" in msg
        blade.patch_network_interfaces.assert_not_called()
        module.exit_json.assert_not_called()

    def test_array_level_server_that_does_not_exist_fails_in_check_mode(
        self, mock_get, mock_patch
    ):
        mock_get.return_value = _iface(attached="_array_server")
        module = _module(attached_server="fred")
        module.check_mode = True
        blade = _server_blade("_array_server")
        _run(modify_iface, module, blade)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "fred" in msg
        assert "looked up as" not in msg
        module.exit_json.assert_not_called()

    def test_lookup_answered_with_other_servers_fails(self, mock_get, mock_patch):
        """The array reads a comma as a separator of names; no server has
        the name given."""
        mock_get.return_value = _iface(attached="_array_server")
        module = _module(attached_server="fred,barney")
        blade = _blade()
        blade.get_servers.return_value = _found("fred", "barney")
        _run(modify_iface, module, blade)
        module.fail_json.assert_called_once()
        blade.patch_network_interfaces.assert_not_called()

    def test_lookup_the_array_refuses_is_left_to_the_request(
        self, mock_get, mock_patch
    ):
        mock_get.return_value = _realm_iface()
        module = _module(name="tenant1::vip1", attached_server="tenant1::srv2")
        blade = _blade()
        blade.get_servers.return_value = _error("Operation not permitted.")
        _run(modify_iface, module, blade)
        mock_patch.assert_called_once_with(attached_servers=[{"name": "tenant1::srv2"}])
        module.exit_json.assert_called_once_with(changed=True)

    def test_no_lookup_when_no_server_is_attached(self, mock_get, mock_patch):
        mock_get.return_value = _iface(attached="fred")
        module = _module(attached_server="")
        blade = _server_blade("fred")
        _run(modify_iface, module, blade)
        mock_patch.assert_called_once_with(attached_servers=[])
        blade.get_servers.assert_not_called()

    def test_refused_request_says_how_the_server_was_looked_up(
        self, mock_get, mock_patch
    ):
        mock_get.return_value = _realm_iface()
        module = _module(name="tenant1::vip1", attached_server="srv2")
        blade = _server_blade("tenant1::srv2")
        blade.patch_network_interfaces.return_value = _error("Operation not permitted.")
        _run(modify_iface, module, blade)
        msg = module.fail_json.call_args[1]["msg"]
        assert "Operation not permitted." in msg
        assert "attached_server srv2 was looked up as tenant1::srv2" in msg

    def test_refused_request_for_a_qualified_server_adds_nothing(
        self, mock_get, mock_patch
    ):
        mock_get.return_value = _realm_iface()
        module = _module(name="tenant1::vip1", attached_server="tenant1::srv2")
        blade = _server_blade("tenant1::srv2")
        blade.patch_network_interfaces.return_value = _error("Operation not permitted.")
        _run(modify_iface, module, blade)
        msg = module.fail_json.call_args[1]["msg"]
        assert msg.endswith("Error: Operation not permitted.")


@patch(MODULE_PATH + ".get_error_message", _message)
class TestRealmDataInterfaceNeedsAServer:
    """A data interface in a realm has no default server."""

    @pytest.mark.parametrize("check_mode", [True, False])
    @pytest.mark.parametrize(
        "params",
        [
            {},
            {"services": "data"},
            {"attached_server": ""},
            {"services": "data", "attached_server": ""},
        ],
    )
    @patch(MODULE_PATH + ".NetworkInterface")
    def test_create_without_a_server_is_refused(self, mock_ni, check_mode, params):
        module = _module(name="tenant1::vip1", **params)
        module.check_mode = check_mode
        blade = _blade()
        _run(create_iface, module, blade)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "tenant1::vip1" in msg
        assert "a server of realm tenant1" in msg
        assert "egress-only" in msg
        blade.post_network_interfaces.assert_not_called()
        module.exit_json.assert_not_called()

    @patch(MODULE_PATH + ".NetworkInterface")
    def test_create_egress_only_without_a_server_is_sent(self, mock_ni):
        module = _module(name="tenant1::vip1", services="egress-only")
        blade = _blade()
        _run(create_iface, module, blade)
        module.fail_json.assert_not_called()
        assert "attached_servers" not in mock_ni.call_args[1]
        assert blade.post_network_interfaces.call_args[1]["names"] == ["tenant1::vip1"]
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".NetworkInterface")
    def test_create_with_a_bare_server_sends_it_with_the_realm(self, mock_ni):
        module = _module(name="tenant1::vip1", attached_server="srv1")
        blade = _server_blade("tenant1::srv1", "srv1")
        _run(create_iface, module, blade)
        assert mock_ni.call_args[1]["attached_servers"] == [{"name": "tenant1::srv1"}]
        blade.get_servers.assert_called_once_with(names=["tenant1::srv1"])
        module.exit_json.assert_called_once_with(changed=True)

    @pytest.mark.parametrize("check_mode", [True, False])
    @patch(MODULE_PATH + ".NetworkInterface")
    def test_create_with_a_server_that_does_not_exist_fails(self, mock_ni, check_mode):
        module = _module(name="tenant1::vip1", attached_server="srv9")
        module.check_mode = check_mode
        blade = _server_blade("tenant1::srv1", "srv9")
        _run(create_iface, module, blade)
        module.fail_json.assert_called_once()
        assert "tenant1::srv9" in module.fail_json.call_args[1]["msg"]
        blade.post_network_interfaces.assert_not_called()
        module.exit_json.assert_not_called()

    @patch(MODULE_PATH + ".NetworkInterface")
    def test_refused_create_says_how_the_server_was_looked_up(self, mock_ni):
        module = _module(name="tenant1::vip1", attached_server="srv1")
        blade = _server_blade("tenant1::srv1")
        blade.post_network_interfaces.return_value = _error("No matching subnet found.")
        _run(create_iface, module, blade)
        msg = module.fail_json.call_args[1]["msg"]
        assert "No matching subnet found." in msg
        assert "attached_server srv1 was looked up as tenant1::srv1" in msg

    @patch(MODULE_PATH + ".NetworkInterface")
    def test_array_level_create_without_a_server_is_sent(self, mock_ni):
        """The array hands an array-level data interface to _array_server."""
        module = _module()
        blade = _blade()
        _run(create_iface, module, blade)
        module.fail_json.assert_not_called()
        blade.get_servers.assert_not_called()
        blade.post_network_interfaces.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    @pytest.mark.parametrize("check_mode", [True, False])
    @patch(MODULE_PATH + ".NetworkInterfacePatch")
    @patch(MODULE_PATH + ".get_iface")
    def test_detach_on_a_data_interface_is_refused(
        self, mock_get, mock_patch, check_mode
    ):
        mock_get.return_value = _realm_iface()
        module = _module(name="tenant1::vip1", attached_server="")
        module.check_mode = check_mode
        blade = _blade()
        _run(modify_iface, module, blade)
        module.fail_json.assert_called_once()
        assert "a server of realm tenant1" in module.fail_json.call_args[1]["msg"]
        blade.patch_network_interfaces.assert_not_called()
        module.exit_json.assert_not_called()

    @pytest.mark.parametrize("check_mode", [True, False])
    @pytest.mark.parametrize("server", [None, ""])
    @patch(MODULE_PATH + ".NetworkInterfacePatch")
    @patch(MODULE_PATH + ".get_iface")
    def test_switch_to_data_without_a_server_is_refused(
        self, mock_get, mock_patch, server, check_mode
    ):
        mock_get.return_value = _realm_iface(attached=None, services=["egress-only"])
        module = _module(name="tenant1::vip1", services="data", attached_server=server)
        module.check_mode = check_mode
        blade = _blade()
        _run(modify_iface, module, blade)
        module.fail_json.assert_called_once()
        assert "egress-only" in module.fail_json.call_args[1]["msg"]
        blade.patch_network_interfaces.assert_not_called()
        module.exit_json.assert_not_called()

    @patch(MODULE_PATH + ".NetworkInterfacePatch")
    @patch(MODULE_PATH + ".get_iface")
    def test_switch_to_data_with_a_server_is_one_patch(self, mock_get, mock_patch):
        mock_get.return_value = _realm_iface(attached=None, services=["egress-only"])
        module = _module(name="tenant1::vip1", services="data", attached_server="srv1")
        blade = _server_blade("tenant1::srv1")
        _run(modify_iface, module, blade)
        mock_patch.assert_called_once_with(
            services=["data"], attached_servers=[{"name": "tenant1::srv1"}]
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".NetworkInterfacePatch")
    @patch(MODULE_PATH + ".get_iface")
    def test_switch_to_egress_only_is_sent(self, mock_get, mock_patch):
        """The array detaches the server with the services change."""
        mock_get.return_value = _realm_iface()
        module = _module(
            name="tenant1::vip1", services="egress-only", attached_server=""
        )
        blade = _blade()
        _run(modify_iface, module, blade)
        module.fail_json.assert_not_called()
        mock_patch.assert_called_once_with(services=["egress-only"])

    @patch(MODULE_PATH + ".NetworkInterfacePatch")
    @patch(MODULE_PATH + ".get_iface")
    def test_other_changes_of_a_data_interface_are_sent(self, mock_get, mock_patch):
        mock_get.return_value = _realm_iface(address="10.0.0.9")
        module = _module(name="tenant1::vip1", address="10.0.0.10", services="data")
        blade = _blade()
        _run(modify_iface, module, blade)
        module.fail_json.assert_not_called()
        mock_patch.assert_called_once_with(address="10.0.0.10")

    @patch(MODULE_PATH + ".NetworkInterfacePatch")
    @patch(MODULE_PATH + ".get_iface")
    def test_detach_on_another_service_is_left_to_the_array(self, mock_get, mock_patch):
        mock_get.return_value = _realm_iface(services=["replication"])
        module = _module(name="tenant1::vip1", attached_server="")
        blade = _blade()
        _run(modify_iface, module, blade)
        module.fail_json.assert_not_called()
        mock_patch.assert_called_once_with(attached_servers=[])


@patch(MODULE_PATH + ".get_error_message", _message)
@patch(MODULE_PATH + ".LooseVersion", _version)
@patch(MODULE_PATH + ".delete_iface")
@patch(MODULE_PATH + ".modify_iface")
@patch(MODULE_PATH + ".create_iface")
@patch(MODULE_PATH + ".get_iface")
@patch(MODULE_PATH + ".get_rest_api_version")
@patch(MODULE_PATH + ".get_system")
@patch(MODULE_PATH + ".AnsibleModule")
class TestMainRealm:
    """Checks made in main() before an interface is created or modified."""

    def _setup(self, mock_am, mock_gs, mock_ver, mock_get, iface, **params):
        version = params.pop("version", "2.30")
        module = _module(**params)
        blade = _blade()
        blade.get_realms.side_effect = lambda names: _found(*names)
        mock_am.return_value = module
        mock_gs.return_value = blade
        mock_ver.return_value = version
        mock_get.return_value = iface
        return module, blade

    def _main(self):
        try:
            main()
        except SystemExit:
            pass

    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize("name", ["vip*", "*", "vip1,vip2", "tenant1::*"])
    def test_name_of_more_than_one_interface_is_refused_before_any_request(
        self,
        mock_am,
        mock_gs,
        mock_ver,
        mock_get,
        mock_create,
        mock_modify,
        mock_delete,
        name,
        state,
    ):
        module, blade = self._setup(
            mock_am, mock_gs, mock_ver, mock_get, _iface(), name=name, state=state
        )
        self._main()
        module.fail_json.assert_called_once()
        assert name in module.fail_json.call_args[1]["msg"]
        mock_gs.assert_not_called()
        mock_get.assert_not_called()
        mock_create.assert_not_called()
        mock_modify.assert_not_called()
        mock_delete.assert_not_called()

    @pytest.mark.parametrize("check_mode", [True, False])
    @pytest.mark.parametrize("existing", [True, False])
    def test_realm_server_on_an_array_level_interface_is_refused(
        self,
        mock_am,
        mock_gs,
        mock_ver,
        mock_get,
        mock_create,
        mock_modify,
        mock_delete,
        existing,
        check_mode,
    ):
        iface = None
        if existing:
            iface = _iface(attached=None, services=["egress-only"], rdma=False)
        module, blade = self._setup(
            mock_am,
            mock_gs,
            mock_ver,
            mock_get,
            iface,
            services="data",
            attached_server="tenant1::srv1",
        )
        module.check_mode = check_mode
        self._main()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "vip1" in msg and "tenant1::srv1" in msg
        assert "tenant1::<interface>" in msg
        mock_create.assert_not_called()
        mock_modify.assert_not_called()

    @pytest.mark.parametrize("check_mode", [True, False])
    @pytest.mark.parametrize("existing", [True, False])
    @pytest.mark.parametrize(
        "server", ["tenant2::srv1", "_array_server", "_ARRAY_SERVER"]
    )
    def test_server_outside_the_realm_of_the_interface_is_refused(
        self,
        mock_am,
        mock_gs,
        mock_ver,
        mock_get,
        mock_create,
        mock_modify,
        mock_delete,
        server,
        existing,
        check_mode,
    ):
        """A server of another realm, and the default _array_server, which
        the array always reads as the array-level server."""
        module, blade = self._setup(
            mock_am,
            mock_gs,
            mock_ver,
            mock_get,
            _realm_iface() if existing else None,
            name="tenant1::vip1",
            attached_server=server,
        )
        module.check_mode = check_mode
        self._main()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert server in msg
        assert "tenant1::<server>" in msg
        blade.get_realms.assert_not_called()
        mock_create.assert_not_called()
        mock_modify.assert_not_called()

    def test_default_server_on_an_array_level_interface_is_accepted(
        self,
        mock_am,
        mock_gs,
        mock_ver,
        mock_get,
        mock_create,
        mock_modify,
        mock_delete,
    ):
        module, blade = self._setup(
            mock_am,
            mock_gs,
            mock_ver,
            mock_get,
            _iface(attached="fred"),
            attached_server="_array_server",
        )
        self._main()
        module.fail_json.assert_not_called()
        mock_modify.assert_called_once()

    @pytest.mark.parametrize(
        "name,server",
        [
            ("tenant1::vip1", "tenant1::srv1"),
            ("tenant1::vip1", "TENANT1::srv1"),
            ("TENANT1::vip1", "tenant1::srv1"),
            ("tenant1::vip1", "srv1"),
            ("tenant1::vip1", ""),
        ],
    )
    def test_server_of_the_realm_of_the_interface_is_accepted(
        self,
        mock_am,
        mock_gs,
        mock_ver,
        mock_get,
        mock_create,
        mock_modify,
        mock_delete,
        name,
        server,
    ):
        module, blade = self._setup(
            mock_am,
            mock_gs,
            mock_ver,
            mock_get,
            _realm_iface(),
            name=name,
            attached_server=server,
        )
        self._main()
        module.fail_json.assert_not_called()
        mock_modify.assert_called_once()

    def test_realm_of_the_name_the_array_holds_decides(
        self,
        mock_am,
        mock_gs,
        mock_ver,
        mock_get,
        mock_create,
        mock_modify,
        mock_delete,
    ):
        """An array-level interface found under a name the task wrote with
        blanks around it stays an array-level interface."""
        module, blade = self._setup(
            mock_am,
            mock_gs,
            mock_ver,
            mock_get,
            _iface(),
            name=" vip1 ",
            attached_server="tenant1::srv1",
        )
        self._main()
        module.fail_json.assert_called_once()
        assert "interface vip1 to" in module.fail_json.call_args[1]["msg"]
        mock_modify.assert_not_called()

    def test_absent_does_not_look_at_the_server(
        self,
        mock_am,
        mock_gs,
        mock_ver,
        mock_get,
        mock_create,
        mock_modify,
        mock_delete,
    ):
        module, blade = self._setup(
            mock_am,
            mock_gs,
            mock_ver,
            mock_get,
            _iface(),
            state="absent",
            attached_server="tenant1::srv1",
        )
        self._main()
        module.fail_json.assert_not_called()
        mock_delete.assert_called_once()

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_create_in_a_realm_that_does_not_exist_fails(
        self,
        mock_am,
        mock_gs,
        mock_ver,
        mock_get,
        mock_create,
        mock_modify,
        mock_delete,
        check_mode,
    ):
        module, blade = self._setup(
            mock_am,
            mock_gs,
            mock_ver,
            mock_get,
            None,
            name="tenant9::vip1",
            services="egress-only",
        )
        module.check_mode = check_mode
        blade.get_realms.side_effect = None
        blade.get_realms.return_value = _error("Realm does not exist.")
        self._main()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "realm tenant9 does not exist" in msg
        mock_create.assert_not_called()

    def test_create_in_a_realm_that_exists_goes_on(
        self,
        mock_am,
        mock_gs,
        mock_ver,
        mock_get,
        mock_create,
        mock_modify,
        mock_delete,
    ):
        module, blade = self._setup(
            mock_am,
            mock_gs,
            mock_ver,
            mock_get,
            None,
            name="TENANT1::vip1",
            services="egress-only",
        )
        blade.get_realms.side_effect = None
        blade.get_realms.return_value = _found("tenant1")
        self._main()
        module.fail_json.assert_not_called()
        blade.get_realms.assert_called_once_with(names=["TENANT1"])
        mock_create.assert_called_once()

    def test_realm_lookup_the_array_refuses_is_left_to_the_create(
        self,
        mock_am,
        mock_gs,
        mock_ver,
        mock_get,
        mock_create,
        mock_modify,
        mock_delete,
    ):
        module, blade = self._setup(
            mock_am,
            mock_gs,
            mock_ver,
            mock_get,
            None,
            name="tenant1::vip1",
            services="egress-only",
        )
        blade.get_realms.side_effect = None
        blade.get_realms.return_value = _error("Operation not permitted.")
        self._main()
        module.fail_json.assert_not_called()
        mock_create.assert_called_once()

    def test_no_realm_lookup_below_the_rest_version_of_realms(
        self,
        mock_am,
        mock_gs,
        mock_ver,
        mock_get,
        mock_create,
        mock_modify,
        mock_delete,
    ):
        module, blade = self._setup(
            mock_am,
            mock_gs,
            mock_ver,
            mock_get,
            None,
            name="tenant1::vip1",
            version="2.18",
        )
        blade.get_realms.side_effect = None
        blade.get_realms.return_value = _error("Realm does not exist.")
        self._main()
        blade.get_realms.assert_not_called()
        module.fail_json.assert_not_called()
        mock_create.assert_called_once()

    @pytest.mark.parametrize("existing", [True, False])
    def test_no_realm_lookup_for_other_tasks(
        self,
        mock_am,
        mock_gs,
        mock_ver,
        mock_get,
        mock_create,
        mock_modify,
        mock_delete,
        existing,
    ):
        """Only a create in a realm reads the realm."""
        module, blade = self._setup(
            mock_am,
            mock_gs,
            mock_ver,
            mock_get,
            _realm_iface() if existing else None,
            name="tenant1::vip1" if existing else "vip1",
        )
        self._main()
        blade.get_realms.assert_not_called()
        module.fail_json.assert_not_called()
        assert mock_modify.call_count + mock_create.call_count == 1


@patch(MODULE_PATH + ".get_error_message", _message)
@patch(MODULE_PATH + ".LooseVersion", _version)
@patch(MODULE_PATH + ".delete_iface")
@patch(MODULE_PATH + ".modify_iface")
@patch(MODULE_PATH + ".create_iface")
@patch(MODULE_PATH + ".get_rest_api_version")
@patch(MODULE_PATH + ".get_system")
@patch(MODULE_PATH + ".AnsibleModule")
class TestMainRead:
    """A read of the interface that the array refuses, through main()."""

    def _main(self, mock_am, mock_gs, mock_ver, answer, **params):
        module = _module(**params)
        blade = _blade()
        blade.get_network_interfaces.return_value = answer
        mock_am.return_value = module
        mock_gs.return_value = blade
        mock_ver.return_value = "2.30"
        try:
            main()
        except SystemExit:
            pass
        return module

    def test_absent_with_a_refused_read_fails(
        self, mock_am, mock_gs, mock_ver, mock_create, mock_modify, mock_delete
    ):
        module = self._main(
            mock_am,
            mock_gs,
            mock_ver,
            _error("Operation not permitted."),
            state="absent",
        )
        module.fail_json.assert_called_once()
        assert "Operation not permitted." in module.fail_json.call_args[1]["msg"]
        module.exit_json.assert_not_called()
        mock_delete.assert_not_called()

    def test_present_with_a_refused_read_does_not_create(
        self, mock_am, mock_gs, mock_ver, mock_create, mock_modify, mock_delete
    ):
        module = self._main(
            mock_am, mock_gs, mock_ver, _error("Operation not permitted.")
        )
        module.fail_json.assert_called_once()
        mock_create.assert_not_called()

    def test_absent_of_an_interface_that_does_not_exist_is_unchanged(
        self, mock_am, mock_gs, mock_ver, mock_create, mock_modify, mock_delete
    ):
        module = self._main(
            mock_am,
            mock_gs,
            mock_ver,
            _error("Network does not exist."),
            name="tenant1::vip1",
            state="absent",
        )
        module.fail_json.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)
        mock_delete.assert_not_called()


@patch(MODULE_PATH + ".get_error_message", _message)
class TestAddressedByTheStoredName:
    """The array finds an interface under a name in another case, but
    refuses to change one whose realm is written in another case, so a
    write names the interface as the array holds it."""

    @pytest.mark.parametrize(
        "given,stored",
        [("TENANT1::vip1", "tenant1::vip1"), ("VIP1", "vip1"), ("vip1", "vip1")],
    )
    @patch(MODULE_PATH + ".NetworkInterfacePatch")
    @patch(MODULE_PATH + ".get_iface")
    def test_modify_names_the_interface_as_the_array_holds_it(
        self, mock_get, mock_patch, given, stored
    ):
        if "::" in stored:
            mock_get.return_value = _realm_iface(name=stored, address="10.0.0.9")
        else:
            mock_get.return_value = _iface(address="10.0.0.9")
        module = _module(name=given, address="10.0.0.10")
        blade = _blade()
        _run(modify_iface, module, blade)
        assert blade.patch_network_interfaces.call_args[1]["names"] == [stored]
        mock_patch.assert_called_once_with(address="10.0.0.10")
        module.exit_json.assert_called_once_with(changed=True)

    def test_delete_names_the_interface_as_the_array_holds_it(self):
        module = _module(name="TENANT1::vip1", state="absent")
        blade = _blade()
        _run(lambda mod, bld: delete_iface(mod, bld, "tenant1::vip1"), module, blade)
        blade.delete_network_interfaces.assert_called_once_with(names=["tenant1::vip1"])
        module.exit_json.assert_called_once_with(changed=True)

    def test_refused_delete_is_reported_under_the_name_of_the_task(self):
        module = _module(name="TENANT1::vip1", state="absent")
        blade = _blade()
        blade.delete_network_interfaces.return_value = _error(
            "Operation not permitted."
        )
        _run(lambda mod, bld: delete_iface(mod, bld, "tenant1::vip1"), module, blade)
        msg = module.fail_json.call_args[1]["msg"]
        assert "TENANT1::vip1" in msg
        assert "Operation not permitted." in msg

    @patch(MODULE_PATH + ".LooseVersion", _version)
    @patch(MODULE_PATH + ".delete_iface")
    @patch(MODULE_PATH + ".get_iface")
    @patch(MODULE_PATH + ".get_rest_api_version")
    @patch(MODULE_PATH + ".get_system")
    @patch(MODULE_PATH + ".AnsibleModule")
    def test_main_hands_the_stored_name_to_the_delete(
        self, mock_am, mock_gs, mock_ver, mock_get, mock_delete
    ):
        module = _module(name="TENANT1::vip1", state="absent")
        blade = _blade()
        mock_am.return_value = module
        mock_gs.return_value = blade
        mock_ver.return_value = "2.30"
        mock_get.return_value = _realm_iface()
        try:
            main()
        except SystemExit:
            pass
        mock_delete.assert_called_once_with(module, blade, "tenant1::vip1")


@patch(MODULE_PATH + ".get_error_message", _message)
@patch(MODULE_PATH + ".NetworkInterfacePatch")
@patch(MODULE_PATH + ".get_iface")
class TestServerOnAnEgressOnlyInterface:
    """The array refuses a server on an egress-only interface
    ("Egress-only network interfaces cannot have a server specified."), so
    a task that leaves services out is judged by the service of the
    interface."""

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_attach_with_services_left_out_is_refused(
        self, mock_get, mock_patch, check_mode
    ):
        mock_get.return_value = _iface(
            attached=None, services=["egress-only"], rdma=False
        )
        module = _module(attached_server="fred")
        module.check_mode = check_mode
        blade = _server_blade("fred")
        _run(modify_iface, module, blade)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "vip1 is an egress-only interface" in msg
        assert "services to data" in msg
        assert "fred" in msg
        blade.get_servers.assert_not_called()
        blade.patch_network_interfaces.assert_not_called()
        module.exit_json.assert_not_called()

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_attach_in_a_realm_with_services_left_out_is_refused(
        self, mock_get, mock_patch, check_mode
    ):
        """The last step of a realm bring-up without services data."""
        mock_get.return_value = _realm_iface(attached=None, services=["egress-only"])
        module = _module(name="tenant1::vip1", attached_server="srv1")
        module.check_mode = check_mode
        blade = _server_blade("tenant1::srv1")
        _run(modify_iface, module, blade)
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "tenant1::vip1 is an egress-only interface" in msg
        assert "tenant1::srv1" in msg
        blade.patch_network_interfaces.assert_not_called()
        module.exit_json.assert_not_called()

    def test_other_changes_are_not_sent_with_the_refused_server(
        self, mock_get, mock_patch
    ):
        mock_get.return_value = _iface(
            address="10.0.0.9", attached=None, services=["egress-only"], rdma=False
        )
        module = _module(address="10.0.0.10", attached_server="fred")
        blade = _server_blade("fred")
        _run(modify_iface, module, blade)
        module.fail_json.assert_called_once()
        blade.patch_network_interfaces.assert_not_called()

    @pytest.mark.parametrize("server", [None, ""])
    def test_no_server_on_an_egress_only_interface_is_unchanged(
        self, mock_get, mock_patch, server
    ):
        mock_get.return_value = _iface(
            attached=None, services=["egress-only"], rdma=False
        )
        module = _module(attached_server=server)
        blade = _blade()
        _run(modify_iface, module, blade)
        module.fail_json.assert_not_called()
        blade.patch_network_interfaces.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_switch_to_data_with_the_server_is_sent(self, mock_get, mock_patch):
        """Naming the data service in the same task is the way to attach."""
        mock_get.return_value = _iface(
            attached=None, services=["egress-only"], rdma=False
        )
        module = _module(services="data", attached_server="fred")
        blade = _server_blade("fred")
        _run(modify_iface, module, blade)
        module.fail_json.assert_not_called()
        mock_patch.assert_called_once_with(
            services=["data"], attached_servers=[{"name": "fred"}]
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_named_server_on_an_sts_interface_is_left_to_the_array(
        self, mock_get, mock_patch
    ):
        """With services left out the array accepts a named server on an
        existing sts interface, so the request is sent."""
        mock_get.return_value = _iface(
            attached="_array_server", services=["sts"], rdma=False
        )
        module = _module(attached_server="fred")
        blade = _server_blade("fred")
        _run(modify_iface, module, blade)
        module.fail_json.assert_not_called()
        mock_patch.assert_called_once_with(attached_servers=[{"name": "fred"}])
        module.exit_json.assert_called_once_with(changed=True)
