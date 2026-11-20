# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_target module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from unittest.mock import Mock, patch, MagicMock

import yaml

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

from plugins.modules import purefb_target
from plugins.modules.purefb_target import main

MOD = "plugins.modules.purefb_target"
NOT_PERMITTED = "Operation not permitted."
SAME_ADDRESS = "Target already exists with same connection address"
ARRAY_INTERFACES = (
    ("vir0", ["management"]),
    ("datavip", ["data"]),
    ("replication", ["replication"]),
)


def _module(check_mode=False, **overrides):
    module = Mock()
    module.params = {"name": "acme-s3", "state": "present", "address": "10.10.10.20"}
    module.params.update(overrides)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _target(name, address):
    """A target as GET /targets returns it."""
    target = Mock()
    target.name = name
    target.address = address
    target.status = "connecting"
    return target


def _interface(name, services):
    """A network interface as GET /network-interfaces returns it."""
    interface = Mock()
    interface.name = name
    interface.services = services
    return interface


def _valid(items=None):
    res = Mock()
    res.status_code = 200
    res.items = iter(items or [])
    return res


def _error(message, status_code=400):
    """An error answer of the SDK: it has errors and no items."""
    error = Mock()
    error.message = message
    res = Mock(spec=["status_code", "errors"])
    res.status_code = status_code
    res.errors = [error]
    return res


def _blade(targets=(), interfaces=ARRAY_INTERFACES):
    """The array as an array administrator sees it."""
    blade = Mock()
    blade.get_targets.side_effect = lambda **kw: _valid(
        [_target(name, address) for name, address in targets]
    )
    blade.get_network_interfaces.side_effect = lambda **kw: _valid(
        [_interface(name, services) for name, services in interfaces]
    )
    blade.post_targets.return_value = _valid()
    blade.patch_targets.return_value = _valid()
    blade.delete_targets.return_value = _valid()
    return blade


def _realm_blade(shared=()):
    """The array as an administrator limited to a realm sees it.

    It lists the targets shared with the realm and no network interface.
    """
    return _blade(targets=shared, interfaces=())


def _run(module, blade, has_sdk=True):
    """Run main() with the module and blade mocks; return the get_system mock."""
    with patch(MOD + ".AnsibleModule", return_value=module), patch(
        MOD + ".get_system", return_value=blade
    ) as get_system, patch(MOD + ".HAS_PYPURECLIENT", has_sdk), patch(
        MOD + ".TargetPost", side_effect=lambda **kw: kw
    ), patch(
        MOD + ".Target", side_effect=lambda **kw: kw
    ), patch(
        MOD + ".get_error_message", side_effect=lambda res: res.errors[0].message
    ):
        try:
            main()
        except SystemExit:
            pass
    return get_system


def _changed(module):
    module.fail_json.assert_not_called()
    module.exit_json.assert_called_once()
    return module.exit_json.call_args[1]["changed"]


def _failure(module):
    """The message of the one and only fail_json; nothing may exit after it."""
    module.fail_json.assert_called_once()
    module.exit_json.assert_not_called()
    return module.fail_json.call_args[1]["msg"]


def _no_writes(blade):
    blade.post_targets.assert_not_called()
    blade.patch_targets.assert_not_called()
    blade.delete_targets.assert_not_called()


class TestCreate:
    """state=present for a target that does not exist"""

    def test_create(self):
        module = _module()
        blade = _blade()
        _run(module, blade)
        assert _changed(module) is True
        blade.post_targets.assert_called_once_with(
            names=["acme-s3"], target={"address": "10.10.10.20"}
        )
        blade.patch_targets.assert_not_called()
        blade.delete_targets.assert_not_called()

    def test_create_check_mode_sends_nothing(self):
        module = _module(check_mode=True)
        blade = _blade(targets=[("other", "10.10.10.99")])
        _run(module, blade)
        assert _changed(module) is True
        _no_writes(blade)

    def test_create_refused_by_the_array(self):
        module = _module()
        blade = _blade()
        blade.post_targets.return_value = _error("Target limit reached.")
        _run(module, blade)
        assert _failure(module) == (
            "Failed to connect to remote target acme-s3. Error: Target limit reached."
        )

    def test_create_refused_when_the_address_is_in_use(self):
        module = _module()
        blade = _blade(targets=[("other", "10.10.10.20")])
        _run(module, blade)
        assert _failure(module) == SAME_ADDRESS
        _no_writes(blade)

    def test_create_check_mode_refused_when_the_address_is_in_use(self):
        """Check mode predicts the refusal of the real run."""
        module = _module(check_mode=True)
        blade = _blade(targets=[("other", "10.10.10.20")])
        _run(module, blade)
        assert _failure(module) == SAME_ADDRESS
        _no_writes(blade)

    def test_create_needs_a_replication_interface(self):
        module = _module()
        blade = _blade(interfaces=[("vir0", ["management"]), ("datavip", ["data"])])
        _run(module, blade)
        assert "Replication network interface required" in _failure(module)
        _no_writes(blade)

    def test_create_check_mode_needs_a_replication_interface(self):
        module = _module(check_mode=True)
        blade = _blade(interfaces=[("vir0", ["management"])])
        _run(module, blade)
        assert "Replication network interface required" in _failure(module)
        _no_writes(blade)

    def test_interface_without_services_is_not_a_replication_interface(self):
        """services is optional in the SDK model."""
        module = _module()
        blade = _blade(interfaces=[("fm1.admin0", None)])
        _run(module, blade)
        assert "Replication network interface required" in _failure(module)
        _no_writes(blade)

    def test_interface_with_several_services(self):
        module = _module()
        blade = _blade(interfaces=[("multi", ["data", "replication"])])
        _run(module, blade)
        assert _changed(module) is True
        blade.post_targets.assert_called_once()


class TestUpdate:
    """state=present for a target that exists"""

    def test_same_address_is_unchanged(self):
        module = _module()
        blade = _blade(targets=[("acme-s3", "10.10.10.20")])
        _run(module, blade)
        assert _changed(module) is False
        _no_writes(blade)

    def test_address_change(self):
        module = _module(address="10.10.10.21")
        blade = _blade(targets=[("other", "10.10.10.99"), ("acme-s3", "10.10.10.20")])
        _run(module, blade)
        assert _changed(module) is True
        blade.patch_targets.assert_called_once_with(
            names=["acme-s3"], target={"address": "10.10.10.21"}
        )
        blade.post_targets.assert_not_called()
        blade.delete_targets.assert_not_called()

    def test_address_change_check_mode_sends_nothing(self):
        module = _module(check_mode=True, address="10.10.10.21")
        blade = _blade(targets=[("acme-s3", "10.10.10.20")])
        _run(module, blade)
        assert _changed(module) is True
        _no_writes(blade)

    def test_address_change_refused_by_the_array(self):
        module = _module(address="10.10.10.21")
        blade = _blade(targets=[("acme-s3", "10.10.10.20")])
        blade.patch_targets.return_value = _error("Invalid address.")
        _run(module, blade)
        assert _failure(module) == (
            "Failed to change address for target acme-s3. Error: Invalid address."
        )

    def test_address_of_another_target_is_refused(self):
        module = _module(address="10.10.10.99")
        blade = _blade(targets=[("other", "10.10.10.99"), ("acme-s3", "10.10.10.20")])
        _run(module, blade)
        assert _failure(module) == SAME_ADDRESS
        _no_writes(blade)

    def test_address_of_another_target_is_refused_in_check_mode(self):
        module = _module(check_mode=True, address="10.10.10.99")
        blade = _blade(targets=[("other", "10.10.10.99"), ("acme-s3", "10.10.10.20")])
        _run(module, blade)
        assert _failure(module) == SAME_ADDRESS
        _no_writes(blade)

    def test_existing_target_needs_no_replication_interface(self):
        """Only a new target depends on the replication interface."""
        module = _module(address="10.10.10.21")
        blade = _blade(targets=[("acme-s3", "10.10.10.20")], interfaces=())
        _run(module, blade)
        assert _changed(module) is True
        blade.patch_targets.assert_called_once()
        blade.get_network_interfaces.assert_not_called()


class TestDelete:
    """state=absent"""

    def test_delete(self):
        module = _module(state="absent", address=None)
        blade = _blade(targets=[("acme-s3", "10.10.10.20")])
        _run(module, blade)
        assert _changed(module) is True
        blade.delete_targets.assert_called_once_with(names=["acme-s3"])
        blade.post_targets.assert_not_called()
        blade.patch_targets.assert_not_called()

    def test_delete_check_mode_sends_nothing(self):
        module = _module(check_mode=True, state="absent", address=None)
        blade = _blade(targets=[("acme-s3", "10.10.10.20")])
        _run(module, blade)
        assert _changed(module) is True
        _no_writes(blade)

    def test_delete_missing_target_is_unchanged(self):
        module = _module(state="absent", address=None)
        blade = _blade(targets=[("other", "10.10.10.99")])
        _run(module, blade)
        assert _changed(module) is False
        _no_writes(blade)

    def test_delete_refused_by_the_array(self):
        module = _module(state="absent", address=None)
        blade = _blade(targets=[("acme-s3", "10.10.10.20")])
        blade.delete_targets.return_value = _error("Target is in use.")
        _run(module, blade)
        assert _failure(module) == (
            "Failed to disconnect target acme-s3. Error: Target is in use."
        )

    def test_delete_needs_no_replication_interface(self):
        module = _module(state="absent", address=None)
        blade = _blade(targets=[("acme-s3", "10.10.10.20")], interfaces=())
        _run(module, blade)
        assert _changed(module) is True
        blade.delete_targets.assert_called_once_with(names=["acme-s3"])
        blade.get_network_interfaces.assert_not_called()


class TestLetterCase:
    """The array matches names without regard to case and returns the stored one"""

    def test_same_target_in_another_case_is_unchanged(self):
        module = _module(name="ACME-S3")
        blade = _blade(targets=[("acme-s3", "10.10.10.20")])
        _run(module, blade)
        assert _changed(module) is False
        _no_writes(blade)

    def test_address_change_uses_the_stored_name(self):
        module = _module(name="Acme-S3", address="10.10.10.21")
        blade = _blade(targets=[("acme-s3", "10.10.10.20")])
        _run(module, blade)
        assert _changed(module) is True
        blade.patch_targets.assert_called_once_with(
            names=["acme-s3"], target={"address": "10.10.10.21"}
        )
        blade.post_targets.assert_not_called()

    def test_delete_uses_the_stored_name(self):
        module = _module(name="ACME-S3", state="absent", address=None)
        blade = _blade(targets=[("acme-s3", "10.10.10.20")])
        _run(module, blade)
        assert _changed(module) is True
        blade.delete_targets.assert_called_once_with(names=["acme-s3"])

    def test_stored_name_in_upper_case(self):
        module = _module(name="acme-s3")
        blade = _blade(targets=[("ACME-S3", "10.10.10.20")])
        _run(module, blade)
        assert _changed(module) is False
        _no_writes(blade)


class TestRefusedReads:
    """A read that does not answer 200 is reported with the message of the array"""

    def test_refused_read_of_the_targets(self):
        module = _module()
        blade = _blade()
        blade.get_targets.side_effect = lambda **kw: _error(NOT_PERMITTED)
        _run(module, blade)
        assert _failure(module) == (
            "Failed to read the targets. Error: Operation not permitted."
        )
        _no_writes(blade)

    def test_refused_read_of_the_targets_for_absent(self):
        """A refused read is not taken for an array without the target."""
        module = _module(state="absent", address=None)
        blade = _blade(targets=[("acme-s3", "10.10.10.20")])
        blade.get_targets.side_effect = lambda **kw: _error(NOT_PERMITTED)
        _run(module, blade)
        assert _failure(module) == (
            "Failed to read the targets. Error: Operation not permitted."
        )
        _no_writes(blade)

    def test_failed_read_of_the_targets_in_check_mode(self):
        module = _module(check_mode=True)
        blade = _blade()
        blade.get_targets.side_effect = lambda **kw: _error(
            "Internal error.", status_code=500
        )
        _run(module, blade)
        assert _failure(module) == "Failed to read the targets. Error: Internal error."
        _no_writes(blade)

    def test_refused_read_of_the_network_interfaces(self):
        module = _module()
        blade = _blade()
        blade.get_network_interfaces.side_effect = lambda **kw: _error(NOT_PERMITTED)
        _run(module, blade)
        assert _failure(module) == (
            "Failed to read the network interfaces. Error: Operation not permitted."
        )
        _no_writes(blade)

    def test_refused_read_of_the_network_interfaces_in_check_mode(self):
        module = _module(check_mode=True)
        blade = _blade()
        blade.get_network_interfaces.side_effect = lambda **kw: _error(NOT_PERMITTED)
        _run(module, blade)
        assert _failure(module) == (
            "Failed to read the network interfaces. Error: Operation not permitted."
        )
        _no_writes(blade)

    def test_network_interfaces_are_not_read_for_absent(self):
        module = _module(state="absent", address=None)
        blade = _blade(targets=[("acme-s3", "10.10.10.20")])
        blade.get_network_interfaces.side_effect = lambda **kw: _error(NOT_PERMITTED)
        _run(module, blade)
        assert _changed(module) is True
        blade.delete_targets.assert_called_once_with(names=["acme-s3"])


class TestRealmScopedAdministrator:
    """An administrator limited to a realm: shared targets, no interface"""

    def test_shared_target_with_its_address_is_unchanged(self):
        module = _module()
        blade = _realm_blade(shared=[("acme-s3", "10.10.10.20")])
        _run(module, blade)
        assert _changed(module) is False
        _no_writes(blade)

    def test_check_mode_absent_of_a_shared_target(self):
        module = _module(check_mode=True, state="absent", address=None)
        blade = _realm_blade(shared=[("acme-s3", "10.10.10.20")])
        _run(module, blade)
        assert _changed(module) is True
        _no_writes(blade)

    def test_absent_of_a_target_it_cannot_see_is_unchanged(self):
        module = _module(state="absent", address=None)
        blade = _realm_blade()
        _run(module, blade)
        assert _changed(module) is False
        _no_writes(blade)

    def test_refused_change_reports_the_answer_of_the_array(self):
        module = _module(address="10.10.10.21")
        blade = _realm_blade(shared=[("acme-s3", "10.10.10.20")])
        blade.patch_targets.return_value = _error(NOT_PERMITTED)
        _run(module, blade)
        assert _failure(module) == (
            "Failed to change address for target acme-s3. "
            "Error: Operation not permitted."
        )
        blade.patch_targets.assert_called_once_with(
            names=["acme-s3"], target={"address": "10.10.10.21"}
        )

    def test_refused_delete_reports_the_answer_of_the_array(self):
        module = _module(state="absent", address=None)
        blade = _realm_blade(shared=[("acme-s3", "10.10.10.20")])
        blade.delete_targets.return_value = _error(NOT_PERMITTED)
        _run(module, blade)
        assert _failure(module) == (
            "Failed to disconnect target acme-s3. Error: Operation not permitted."
        )

    def test_create_explains_that_targets_are_array_level(self):
        module = _module(name="acme-new")
        blade = _realm_blade(shared=[("acme-s3", "10.10.10.20")])
        _run(module, blade)
        msg = _failure(module)
        assert "none is visible to this user" in msg
        assert "array-level" in msg
        assert "purefb_resource_access" in msg
        _no_writes(blade)

    def test_create_check_mode_fails_like_the_real_run(self):
        module = _module(check_mode=True, name="acme-new")
        blade = _realm_blade()
        _run(module, blade)
        assert "purefb_resource_access" in _failure(module)
        _no_writes(blade)


class TestRealmQualifiedName:
    """Targets are array-level: a realm::name cannot be created"""

    def test_create_is_refused_before_any_request(self):
        module = _module(name="tenant1::acme-s3")
        blade = _blade()
        get_system = _run(module, blade)
        msg = _failure(module)
        assert "tenant1::acme-s3" in msg
        assert "array-level" in msg
        assert "purefb_resource_access" in msg
        get_system.assert_not_called()
        blade.get_targets.assert_not_called()
        _no_writes(blade)

    def test_create_check_mode_is_refused_like_the_real_run(self):
        module = _module(check_mode=True, name="tenant1::acme-s3")
        blade = _blade()
        get_system = _run(module, blade)
        assert "tenant1::acme-s3" in _failure(module)
        get_system.assert_not_called()
        _no_writes(blade)

    def test_absent_is_a_no_op(self):
        """No target has such a name, so there is nothing to delete."""
        module = _module(name="tenant1::acme-s3", state="absent", address=None)
        blade = _blade(targets=[("acme-s3", "10.10.10.20")])
        _run(module, blade)
        assert _changed(module) is False
        _no_writes(blade)

    def test_unqualified_namesake_is_not_touched(self):
        module = _module(name="tenant1::acme-s3", address="10.10.10.21")
        blade = _blade(targets=[("acme-s3", "10.10.10.20")])
        _run(module, blade)
        assert "tenant1::acme-s3" in _failure(module)
        _no_writes(blade)


class TestNameIsOneName:
    """The name is compared as a whole, in the module: it reaches one target"""

    def test_comma_separated_name_matches_no_target(self):
        """The targets are listed and compared here, never looked up by names."""
        module = _module(name="acme-s3,other", state="absent", address=None)
        blade = _blade(targets=[("acme-s3", "10.10.10.20"), ("other", "10.10.10.99")])
        _run(module, blade)
        assert _changed(module) is False
        blade.get_targets.assert_called_once_with()
        _no_writes(blade)

    def test_blank_name_matches_no_target(self):
        module = _module(name="", state="absent", address=None)
        blade = _blade(targets=[("acme-s3", "10.10.10.20")])
        _run(module, blade)
        assert _changed(module) is False
        _no_writes(blade)


class TestModule:
    """Module plumbing and documentation"""

    def test_missing_sdk(self):
        module = _module()
        blade = _blade()
        get_system = _run(module, blade, has_sdk=False)
        assert _failure(module) == "py-pure-client sdk is required for this module"
        get_system.assert_not_called()

    def test_targets_are_read_once(self):
        module = _module(address="10.10.10.21")
        blade = _blade(targets=[("acme-s3", "10.10.10.20")])
        _run(module, blade)
        assert blade.get_targets.call_count == 1

    def test_examples_use_documented_options_only(self):
        documented = set(yaml.safe_load(purefb_target.DOCUMENTATION)["options"])
        documented.update(["fb_url", "api_token"])
        examples = yaml.safe_load(purefb_target.EXAMPLES)
        tasks = [
            task["everpure.flashblade.purefb_target"]
            for task in examples
            if "everpure.flashblade.purefb_target" in task
        ]
        assert len(tasks) >= 2
        for task in tasks:
            assert set(task) <= documented

    def test_documentation_points_to_the_realm_share(self):
        description = " ".join(
            yaml.safe_load(purefb_target.DOCUMENTATION)["description"]
        )
        assert "array-level" in description
        assert "purefb_resource_access" in description
