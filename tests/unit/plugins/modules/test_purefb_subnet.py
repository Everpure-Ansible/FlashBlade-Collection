# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_subnet module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
import ipaddress
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, call, patch, MagicMock

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

from plugins.modules.purefb_subnet import main

MOD = "plugins.modules.purefb_subnet"
REFUSED = "Operation not permitted."
NO_SUBNET = "Subnet does not exist."
NAME_RULE = (
    "Subnet name must be between 1 and 63 characters (alphanumeric, '_' and "
    "'-') in length and begin and end with a letter or number. The name must "
    "include at least one letter."
)
READ_FAILED = "Failed to read subnet {0}. Error: {1}"
LIST_FAILED = "Failed to read the subnets. Error: {0}"
LAG_FAILED = "Failed to read LAG {0}. Error: {1}"
LAG_MISSING = "LAG {0} does not exist."
REALM_NAME = (
    "Subnet name {0} is not valid: a subnet is an array-level object and its "
    "name takes no realm prefix. Use the purefb_resource_access module to "
    "share a subnet with a realm."
)
ONE_NAME = (
    "name must be the name of one subnet: in {0} the array reads a comma as "
    "a separator of names."
)

NAME = "prod-net"
PREFIX = "192.168.10.0/24"
GATEWAY = "192.168.10.1"
VLAN = 310


class ExitJson(Exception):
    """Raised by the exit_json stand-in: the real one ends the module."""


class FailJson(Exception):
    """Raised by the fail_json stand-in: the real one ends the module."""


class FakeNetaddr:
    """The netaddr calls of the module, answered with the standard library.

    The unit test environment does not install netaddr, so the module is
    given this stand-in whether netaddr is installed or not.
    """

    @staticmethod
    def IPAddress(address):
        return ipaddress.ip_address(address)

    @staticmethod
    def IPNetwork(prefix):
        return ipaddress.ip_network(prefix, strict=False)

    class IPSet:
        def __init__(self, prefixes):
            self.networks = [
                ipaddress.ip_network(prefix, strict=False) for prefix in prefixes
            ]

        def __and__(self, other):
            return [
                network
                for network in self.networks
                if any(network.overlaps(theirs) for theirs in other.networks)
            ]


def _module(check_mode=False, **params):
    module = Mock()
    module.params = {
        "name": NAME,
        "state": "present",
        "lag": "uplink",
        "gateway": None,
        "mtu": None,
        "prefix": None,
        "vlan": None,
    }
    module.params.update(params)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=ExitJson)
    module.fail_json = Mock(side_effect=FailJson)
    return module


def _subnet(name, prefix, vlan, mtu=1500, gateway=None, lag="uplink"):
    """A subnet as the array returns it."""
    return SimpleNamespace(
        id="10000000-0000-4000-8000-{0:012d}".format(vlan),
        name=name,
        enabled=True,
        gateway=gateway,
        interfaces=[],
        link_aggregation_group=SimpleNamespace(
            id="20000000-0000-4000-8000-000000000001",
            name=lag,
            resource_type="link-aggregation-groups",
        ),
        mtu=mtu,
        prefix=prefix,
        services=[],
        vlan=vlan,
    )


def _others():
    """The subnets of other networks that the array holds."""
    return [
        _subnet("mgmt", "10.0.1.0/24", 2200, mtu=9000, gateway="10.0.1.1"),
        _subnet("Tenant-2065", "10.0.2.0/24", 2065, gateway="10.0.2.1"),
    ]


def _own(**changes):
    """The subnet of the task as the array holds it."""
    fields = {"prefix": PREFIX, "vlan": VLAN, "mtu": 1500, "gateway": GATEWAY}
    fields.update(changes)
    return _subnet(NAME, **fields)


def _valid(items):
    """A response to a request the array accepted."""
    res = Mock(spec=["status_code", "items", "total_item_count", "headers"])
    res.status_code = 200
    res.items = list(items)
    res.total_item_count = len(res.items)
    res.headers = {}
    return res


def _error(message=REFUSED, status_code=400):
    """A response to a request the array refused: it carries no items."""
    res = Mock(spec=["status_code", "errors", "headers"])
    res.status_code = status_code
    res.errors = []
    if message is not None:
        res.errors = [
            SimpleNamespace(context=None, location_context=None, message=message)
        ]
    res.headers = {}
    return res


def _error_message(response, default="Unknown error"):
    """What get_error_message of module_utils returns for a response."""
    errors = list(getattr(response, "errors", None) or [])
    return errors[0].message if errors else default


def _blade(
    subnets=None,
    lags=("uplink",),
    named_read=None,
    list_read=None,
    lag_read=None,
    write=None,
):
    """An array holding the given subnets (two other networks by default).

    A read of subnets by name answers as the array does: a comma separates
    names, white space around a name and its letter case are ignored, the
    stored spelling is returned and a name the array does not hold answers
    400 "Subnet does not exist.". A change finds a subnet only under its
    stored spelling and answers 400 "Subnet <name> does not exist." to any
    other, a delete finds it whatever the letter case. A LAG is matched by
    its exact name and a missing one answers 400 "LAG <name> does not
    exist.". named_read, list_read and lag_read replace the answer of the
    read of the subnet by name, of all subnets and of the LAG, write the
    answer of POST, PATCH and DELETE.
    """
    held = _others() if subnets is None else list(subnets)
    blade = Mock()

    def _get_subnets(**kwargs):
        names = kwargs.get("names")
        if names is None:
            return list_read if list_read is not None else _valid(held)
        if named_read is not None:
            return named_read
        found = []
        for asked in ",".join(names).split(","):
            match = [
                subnet
                for subnet in held
                if subnet.name.lower() == asked.strip().lower()
            ]
            if not match:
                return _error(NO_SUBNET)
            found.extend(match)
        return _valid(found)

    def _get_lags(**kwargs):
        if lag_read is not None:
            return lag_read
        for asked in kwargs["names"]:
            if asked not in lags:
                return _error(LAG_MISSING.format(asked))
        return _valid([SimpleNamespace(name=asked) for asked in kwargs["names"]])

    def _patch(**kwargs):
        if write is not None:
            return write
        for asked in kwargs["names"]:
            if asked not in [subnet.name for subnet in held]:
                return _error("Subnet {0} does not exist.".format(asked))
        return _valid([])

    def _delete(**kwargs):
        if write is not None:
            return write
        for asked in kwargs["names"]:
            if asked.lower() not in [subnet.name.lower() for subnet in held]:
                return _error(NO_SUBNET)
        return _valid([])

    blade.get_subnets.side_effect = _get_subnets
    blade.get_link_aggregation_groups.side_effect = _get_lags
    blade.post_subnets.return_value = write if write is not None else _valid([])
    blade.patch_subnets.side_effect = _patch
    blade.delete_subnets.side_effect = _delete
    return blade


def _run(module, blade, sdk=True, has_netaddr=True):
    """Run main() against the stand-ins and return how the module ended.

    Subnet and Reference are replaced by functions that return their keyword
    arguments, so the body of a POST or PATCH can be compared.
    """
    with ExitStack() as stack:
        ansible_module = stack.enter_context(
            patch(MOD + ".AnsibleModule", return_value=module)
        )
        get_system = stack.enter_context(patch(MOD + ".get_system", return_value=blade))
        stack.enter_context(
            patch(MOD + ".get_error_message", side_effect=_error_message)
        )
        stack.enter_context(patch(MOD + ".HAS_PYPURECLIENT", sdk))
        stack.enter_context(patch(MOD + ".HAS_NETADDR", has_netaddr))
        stack.enter_context(patch(MOD + ".netaddr", FakeNetaddr, create=True))
        stack.enter_context(patch(MOD + ".Subnet", side_effect=lambda **kwargs: kwargs))
        stack.enter_context(
            patch(MOD + ".Reference", side_effect=lambda **kwargs: kwargs)
        )
        outcome = None
        try:
            main()
        except ExitJson:
            outcome = "exit"
        except FailJson:
            outcome = "fail"
    assert outcome is not None, "main() ended without exit_json or fail_json"
    return SimpleNamespace(
        outcome=outcome, ansible_module=ansible_module, get_system=get_system
    )


def _failure(module):
    """The message of the single fail_json call of a run that failed."""
    module.fail_json.assert_called_once()
    module.exit_json.assert_not_called()
    return module.fail_json.call_args[1]["msg"]


def _result(module):
    """The keyword arguments of the single exit_json call of a run."""
    module.exit_json.assert_called_once()
    module.fail_json.assert_not_called()
    return module.exit_json.call_args[1]


def _no_write(blade):
    blade.post_subnets.assert_not_called()
    blade.patch_subnets.assert_not_called()
    blade.delete_subnets.assert_not_called()


class TestPurefbSubnetLagRead:
    """Only a create reads the LAG, and a read the array refuses is reported.

    The array refuses the read of the LAGs to an administrator whose
    management access is limited to a realm.
    """

    def test_change_does_not_read_the_lag(self):
        module = _module(prefix=PREFIX, mtu=1400)
        blade = _blade(subnets=_others() + [_own()], lag_read=_error())
        _run(module, blade)
        assert _result(module) == {"changed": True}
        blade.get_link_aggregation_groups.assert_not_called()
        blade.patch_subnets.assert_called_once_with(names=[NAME], subnet={"mtu": 1400})

    def test_change_the_array_refuses_fails_with_its_message(self):
        module = _module(prefix=PREFIX, mtu=1400)
        blade = _blade(subnets=_others() + [_own()], lag_read=_error(), write=_error())
        _run(module, blade)
        assert _failure(module) == (
            "Failed to change subnet prod-net MTU to 1400. Error: " + REFUSED
        )
        blade.get_link_aggregation_groups.assert_not_called()

    def test_check_mode_change_does_not_read_the_lag(self):
        module = _module(check_mode=True, prefix=PREFIX, mtu=1400)
        blade = _blade(subnets=_others() + [_own()], lag_read=_error())
        _run(module, blade)
        assert _result(module) == {"changed": True}
        blade.get_link_aggregation_groups.assert_not_called()
        _no_write(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_nothing_to_change_is_unchanged(self, check_mode):
        module = _module(
            check_mode=check_mode, prefix=PREFIX, gateway=GATEWAY, vlan=VLAN, mtu=1500
        )
        blade = _blade(subnets=_others() + [_own()], lag_read=_error())
        _run(module, blade)
        assert _result(module) == {"changed": False}
        blade.get_link_aggregation_groups.assert_not_called()
        _no_write(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_absent_of_a_missing_subnet_is_unchanged(self, check_mode):
        module = _module(check_mode=check_mode, state="absent")
        blade = _blade(lag_read=_error())
        _run(module, blade)
        assert _result(module) == {"changed": False}
        blade.get_link_aggregation_groups.assert_not_called()
        _no_write(blade)

    def test_delete_does_not_read_the_lag(self):
        module = _module(state="absent")
        blade = _blade(subnets=_others() + [_own()], lag_read=_error())
        _run(module, blade)
        assert _result(module) == {"changed": True}
        blade.get_link_aggregation_groups.assert_not_called()
        blade.delete_subnets.assert_called_once_with(names=[NAME])

    def test_lag_of_an_existing_subnet_is_not_looked_up(self):
        """lag is only used by a create, so a change never fails on it."""
        module = _module(prefix=PREFIX, mtu=1500, lag="other-lag")
        blade = _blade(subnets=_others() + [_own()])
        _run(module, blade)
        assert _result(module) == {"changed": False}
        blade.get_link_aggregation_groups.assert_not_called()
        _no_write(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize(
        "answer, message",
        [
            (_error(), REFUSED),
            (_error("Internal error.", 500), "Internal error."),
            (_error(None, 429), "Unknown error"),
        ],
    )
    def test_create_reports_a_lag_read_the_array_refuses(
        self, answer, message, check_mode
    ):
        module = _module(check_mode=check_mode, prefix=PREFIX, vlan=VLAN)
        blade = _blade(lag_read=answer)
        _run(module, blade)
        assert _failure(module) == LAG_FAILED.format("uplink", message)
        _no_write(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_create_with_a_lag_that_does_not_exist(self, check_mode):
        module = _module(check_mode=check_mode, prefix=PREFIX, vlan=VLAN, lag="lag9")
        blade = _blade()
        _run(module, blade)
        assert _failure(module) == LAG_MISSING.format("lag9")
        blade.get_link_aggregation_groups.assert_called_once_with(names=["lag9"])
        _no_write(blade)

    def test_lag_name_is_matched_as_given(self):
        """The array matches the name of a LAG by its exact letter case."""
        module = _module(prefix=PREFIX, vlan=VLAN, lag="UPLINK")
        blade = _blade()
        _run(module, blade)
        assert _failure(module) == LAG_MISSING.format("UPLINK")
        _no_write(blade)


class TestPurefbSubnetRefusedRead:
    """A read the array refuses or fails is reported, never taken for absent."""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize(
        "answer, message",
        [
            (_error(), REFUSED),
            (_error("Internal error.", 500), "Internal error."),
            (_error(None, 429), "Unknown error"),
        ],
    )
    def test_read_of_the_subnet(self, answer, message, state, check_mode):
        module = _module(check_mode=check_mode, state=state, prefix=PREFIX, vlan=VLAN)
        blade = _blade(named_read=answer)
        _run(module, blade)
        assert _failure(module) == READ_FAILED.format(NAME, message)
        blade.get_link_aggregation_groups.assert_not_called()
        _no_write(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("existing", [False, True])
    @pytest.mark.parametrize(
        "answer, message",
        [
            (_error(), REFUSED),
            (_error("Internal error.", 500), "Internal error."),
        ],
    )
    def test_read_of_all_subnets(self, answer, message, existing, check_mode):
        module = _module(check_mode=check_mode, prefix=PREFIX, vlan=VLAN, mtu=1400)
        blade = _blade(
            subnets=_others() + ([_own()] if existing else []), list_read=answer
        )
        _run(module, blade)
        assert _failure(module) == LIST_FAILED.format(message)
        _no_write(blade)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_only_a_subnet_that_does_not_exist_is_absent(self, check_mode):
        module = _module(check_mode=check_mode, state="absent")
        blade = _blade(named_read=_error(NO_SUBNET))
        _run(module, blade)
        assert _result(module) == {"changed": False}
        _no_write(blade)

    def test_answer_without_a_subnet_is_absent(self):
        """Guard of the index: the array answers a missing name with an error."""
        module = _module(state="absent")
        blade = _blade(named_read=_valid([]))
        _run(module, blade)
        assert _result(module) == {"changed": False}
        _no_write(blade)

    def test_subnet_is_read_once(self):
        module = _module(prefix=PREFIX, mtu=1400)
        blade = _blade(subnets=_others() + [_own()])
        _run(module, blade)
        assert _result(module) == {"changed": True}
        assert blade.get_subnets.call_args_list == [call(names=[NAME]), call()]


class TestPurefbSubnetName:
    """Names the array does not read as the name of one array-level subnet."""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_realm_prefix_is_refused_before_any_request(self, state, check_mode):
        name = "realm1::prod-net"
        module = _module(
            check_mode=check_mode, state=state, name=name, prefix=PREFIX, vlan=VLAN
        )
        blade = _blade(write=_error(NAME_RULE))
        run = _run(module, blade)
        assert _failure(module) == REALM_NAME.format(name)
        run.get_system.assert_not_called()
        assert blade.mock_calls == []

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_list_of_names_is_refused_before_any_request(self, state, check_mode):
        """Both subnets exist: the array would return, change or delete both."""
        name = "prod-net,mgmt"
        module = _module(
            check_mode=check_mode, state=state, name=name, prefix=PREFIX, mtu=1400
        )
        blade = _blade(subnets=_others() + [_own()])
        run = _run(module, blade)
        assert _failure(module) == ONE_NAME.format(name)
        run.get_system.assert_not_called()
        assert blade.mock_calls == []

    @pytest.mark.parametrize("name", ["PROD-NET", "Prod-Net", " prod-net "])
    def test_other_spelling_of_the_name_is_the_same_subnet(self, name):
        """A read finds the subnet and the change names it as it is stored."""
        module = _module(name=name, prefix=PREFIX, vlan=VLAN, mtu=1400)
        blade = _blade(subnets=_others() + [_own()])
        _run(module, blade)
        assert _result(module) == {"changed": True}
        blade.patch_subnets.assert_called_once_with(names=[NAME], subnet={"mtu": 1400})

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_other_spelling_with_nothing_to_change(self, check_mode):
        module = _module(
            check_mode=check_mode,
            name="PROD-NET",
            prefix=PREFIX,
            gateway=GATEWAY,
            vlan=VLAN,
            mtu=1500,
        )
        blade = _blade(subnets=_others() + [_own()])
        _run(module, blade)
        assert _result(module) == {"changed": False}
        _no_write(blade)


class TestPurefbSubnetCreate:
    """Create of an array-level subnet."""

    def test_create_with_gateway(self):
        module = _module(prefix=PREFIX, gateway=GATEWAY, vlan=VLAN, mtu=9000)
        blade = _blade()
        _run(module, blade)
        assert _result(module) == {"changed": True}
        blade.get_link_aggregation_groups.assert_called_once_with(names=["uplink"])
        blade.post_subnets.assert_called_once_with(
            names=[NAME],
            subnet={
                "prefix": PREFIX,
                "vlan": VLAN,
                "mtu": 9000,
                "gateway": GATEWAY,
                "link_aggregation_group": {"name": "uplink"},
            },
        )

    def test_create_with_defaults_and_no_gateway(self):
        module = _module(prefix=PREFIX, lag="lag2")
        blade = _blade(lags=("uplink", "lag2"))
        _run(module, blade)
        assert _result(module) == {"changed": True}
        blade.post_subnets.assert_called_once_with(
            names=[NAME],
            subnet={
                "prefix": PREFIX,
                "vlan": 0,
                "mtu": 1500,
                "link_aggregation_group": {"name": "lag2"},
            },
        )

    def test_create_in_check_mode_sends_nothing(self):
        module = _module(check_mode=True, prefix=PREFIX, gateway=GATEWAY, vlan=VLAN)
        blade = _blade()
        _run(module, blade)
        assert _result(module) == {"changed": True}
        _no_write(blade)

    def test_create_the_array_refuses(self):
        module = _module(prefix=PREFIX, vlan=VLAN)
        blade = _blade(write=_error("Subnet already exists."))
        _run(module, blade)
        assert _failure(module) == (
            "Failed to create subnet prod-net. Error: Subnet already exists."
        )

    @pytest.mark.parametrize(
        "params, message",
        [
            ({"mtu": 1000}, "MTU 1000 is out of range (1280 to 9216)"),
            ({"vlan": 5000}, "VLAN ID 5000 is out of range (0 to 4094)"),
            ({"gateway": "192.168.11.1"}, "Gateway and subnet are not compatible."),
            ({"vlan": 2200}, "VLAN ID 2200 is already in use."),
            ({"prefix": "10.0.2.128/25"}, "Prefix CIDR overlaps with existing subnet."),
        ],
    )
    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("existing", [False, True])
    def test_values_refused_before_the_request(
        self, existing, check_mode, params, message
    ):
        module = _module(check_mode=check_mode, prefix=PREFIX, vlan=VLAN)
        module.params.update(params)
        blade = _blade(subnets=_others() + ([_own()] if existing else []))
        _run(module, blade)
        assert _failure(module) == message
        _no_write(blade)


class TestPurefbSubnetModify:
    """Change of an existing subnet."""

    @pytest.mark.parametrize(
        "params, body",
        [
            ({"prefix": "192.168.10.0/25"}, {"prefix": "192.168.10.0/25"}),
            ({"prefix": PREFIX, "vlan": 311}, {"vlan": 311}),
            (
                {"prefix": PREFIX, "gateway": "192.168.10.254"},
                {"gateway": "192.168.10.254"},
            ),
            ({"prefix": PREFIX, "mtu": 9000}, {"mtu": 9000}),
        ],
    )
    @pytest.mark.parametrize("check_mode", [False, True])
    def test_each_value_is_changed_on_its_own(self, check_mode, params, body):
        module = _module(check_mode=check_mode, **params)
        blade = _blade(subnets=_others() + [_own()])
        _run(module, blade)
        assert _result(module) == {"changed": True}
        if check_mode:
            _no_write(blade)
        else:
            blade.patch_subnets.assert_called_once_with(names=[NAME], subnet=body)
            blade.post_subnets.assert_not_called()

    def test_several_values_are_changed_one_after_the_other(self):
        module = _module(prefix=PREFIX, vlan=311, mtu=9000)
        blade = _blade(subnets=_others() + [_own()])
        _run(module, blade)
        assert _result(module) == {"changed": True}
        assert blade.patch_subnets.call_args_list == [
            call(names=[NAME], subnet={"vlan": 311}),
            call(names=[NAME], subnet={"mtu": 9000}),
        ]

    def test_omitted_values_are_left_alone(self):
        module = _module(prefix=PREFIX)
        blade = _blade(subnets=_others() + [_own(mtu=9000, vlan=311)])
        _run(module, blade)
        assert _result(module) == {"changed": False}
        _no_write(blade)

    @pytest.mark.parametrize(
        "params, message",
        [
            (
                {"prefix": "192.168.10.0/25"},
                "Failed to change subnet prod-net prefix to 192.168.10.0/25. Error: ",
            ),
            (
                {"prefix": PREFIX, "vlan": 311},
                "Failed to change subnet prod-net VLAN to 311. Error: ",
            ),
            (
                {"prefix": PREFIX, "gateway": "192.168.10.254"},
                "Failed to change subnet prod-net gateway to 192.168.10.254. Error: ",
            ),
            (
                {"prefix": PREFIX, "mtu": 9000},
                "Failed to change subnet prod-net MTU to 9000. Error: ",
            ),
        ],
    )
    def test_change_the_array_refuses(self, params, message):
        module = _module(**params)
        blade = _blade(subnets=_others() + [_own()], write=_error())
        _run(module, blade)
        assert _failure(module) == message + REFUSED


class TestPurefbSubnetDelete:
    """Delete of a subnet."""

    def test_delete(self):
        module = _module(state="absent")
        blade = _blade(subnets=_others() + [_own()])
        _run(module, blade)
        assert _result(module) == {"changed": True}
        blade.delete_subnets.assert_called_once_with(names=[NAME])
        assert blade.get_subnets.call_args_list == [call(names=[NAME])]

    def test_delete_in_check_mode_sends_nothing(self):
        module = _module(check_mode=True, state="absent")
        blade = _blade(subnets=_others() + [_own()])
        _run(module, blade)
        assert _result(module) == {"changed": True}
        _no_write(blade)

    @pytest.mark.parametrize("name", ["PROD-NET", " prod-net "])
    def test_delete_names_the_subnet_as_it_is_stored(self, name):
        module = _module(state="absent", name=name)
        blade = _blade(subnets=_others() + [_own()])
        _run(module, blade)
        assert _result(module) == {"changed": True}
        blade.delete_subnets.assert_called_once_with(names=[NAME])

    def test_delete_the_array_refuses(self):
        module = _module(state="absent")
        blade = _blade(subnets=_others() + [_own()], write=_error())
        _run(module, blade)
        assert _failure(module) == (
            "Failed to delete subnet prod-net. Error: " + REFUSED
        )


class TestPurefbSubnetRequirements:
    """What the module needs before it reaches the array."""

    def test_module_supports_check_mode(self):
        module = _module(state="absent")
        run = _run(module, _blade())
        assert run.ansible_module.call_args[1]["supports_check_mode"] is True
        assert run.ansible_module.call_args[1]["required_if"] == [
            ["state", "present", ["prefix"]]
        ]

    def test_sdk_is_required(self):
        module = _module(state="absent")
        blade = _blade()
        run = _run(module, blade, sdk=False)
        assert _failure(module) == "py-pure-client sdk is required for this module"
        run.get_system.assert_not_called()

    def test_netaddr_is_required(self):
        module = _module(state="absent")
        blade = _blade()
        run = _run(module, blade, has_netaddr=False)
        assert _failure(module) == "netaddr module is required"
        run.get_system.assert_not_called()
