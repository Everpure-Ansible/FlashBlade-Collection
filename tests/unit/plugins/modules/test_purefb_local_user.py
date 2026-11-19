# Copyright: (c) 2026, Pure Storage Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_local_user module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from contextlib import ExitStack
from unittest.mock import Mock, patch, MagicMock

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

from plugins.modules.purefb_local_user import (
    main,
    _get_user,
    _get_current_groups,
    _reconcile_memberships,
    _get_local_ds,
    _membership_plan,
    _require_groups,
)

MODULE = "plugins.modules.purefb_local_user."
REALM_LDS = "myrealm::myserver_local"
USERS_POST = "post_directory_services_local_users"
USERS_PATCH = "patch_directory_services_local_users"
USERS_DELETE = "delete_directory_services_local_users"
MEMBERS_POST = "post_directory_services_local_users_members"
MEMBERS_DELETE = "delete_directory_services_local_users_members"


def _base_params(**overrides):
    params = {
        "name": "alice",
        "state": "present",
        "local_directory_service": "myserver_local",
        "new_name": None,
        "uid": None,
        "email": None,
        "enabled": True,
        "password": "s3cret!",
        "force_password_reset": False,
        "primary_group": None,
        "groups": None,
        "context": "",
    }
    params.update(overrides)
    return params


def _ok(items):
    """A 200 answer holding ``items``"""
    response = Mock()
    response.status_code = 200
    response.items = list(items)
    return response


def _error(message, status_code=400):
    """An error answer in the shape the SDK returns it (errors[0].message)"""
    error = Mock()
    error.message = message
    response = Mock()
    response.status_code = status_code
    response.errors = [error]
    return response


def _message(response, default="Unknown error"):
    """Stand-in for module_utils.common.get_error_message, mocked away above"""
    errors = getattr(response, "errors", None)
    return errors[0].message if errors else default


def _ref(name):
    ref = Mock()
    ref.name = name
    return ref


def _lds_response(name="myserver_local"):
    """GET of a Local Directory Service that exists"""
    return _ok([_ref(name)])


def _user(name, lds, primary_group, **fields):
    """A LocalUser as GET /directory-services/local/users returns it"""
    user = Mock()
    user.name = name
    user.built_in = fields.get("built_in", False)
    user.email = fields.get("email")
    user.enabled = fields.get("enabled", False)
    user.uid = fields.get("uid", 1000)
    user.sid = "S-1-5-21-1943874365-4244124768-3581963543-1003"
    user.primary_group = _ref(primary_group)
    user.local_directory_service = _ref(lds)
    user.realms = [_ref(lds.split("::")[0])] if "::" in lds else []
    return user


def _edge(group, primary=False):
    """A LocalMember as GET /directory-services/local/users/members returns it"""
    edge = Mock()
    edge.group = _ref(group)
    edge.is_primary_group = primary
    return edge


def _array(visible_lds=(), users=(), groups=None, memberships=None):
    """A client that answers like the array for the local directory objects given.

    visible_lds names the LDSes the caller can read: the array answers "does
    not exist" for any other one, yet it lists the users of every LDS.
    groups is {lds: [group names]} and memberships is {(lds, user): [edges]}.
    Names are matched without regard to case, as the array matches them.
    """
    groups = dict((k.lower(), v) for k, v in (groups or {}).items())
    memberships = dict(
        ((k[0].lower(), k[1].lower()), v) for k, v in (memberships or {}).items()
    )
    blade = Mock()
    blade.get_versions.return_value.items = ["2.30"]
    blade.get_fleets.return_value = _ok([])

    def lds_of(kwargs):
        return kwargs["filter"][len("local_directory_service.name='") : -1].lower()

    def get_lds(names, **kwargs):
        found = [n for n in visible_lds if n.lower() == names[0].lower()]
        if found:
            return _lds_response(found[0])
        return _error("Local directory service does not exist.")

    def get_users(names, **kwargs):
        found = [
            u
            for u in users
            if u.name.lower() == names[0].lower()
            and u.local_directory_service.name.lower() == lds_of(kwargs)
        ]
        return _ok(found) if found else _error("Local user was not found.")

    def get_groups(names, **kwargs):
        found = [
            _ref(g)
            for g in groups.get(lds_of(kwargs), [])
            if g.lower() == names[0].lower()
        ]
        return _ok(found) if found else _error("Local group was not found.")

    def get_members(member_names, **kwargs):
        return _ok(memberships.get((lds_of(kwargs), member_names[0].lower()), []))

    blade.get_directory_services_local_directory_services.side_effect = get_lds
    blade.get_directory_services_local_users.side_effect = get_users
    blade.get_directory_services_local_groups.side_effect = get_groups
    blade.get_directory_services_local_users_members.side_effect = get_members
    for write in (USERS_POST, USERS_PATCH, USERS_DELETE, MEMBERS_POST, MEMBERS_DELETE):
        getattr(blade, write).return_value = _ok([])
    return blade


def _run(params, blade, check_mode=False):
    """Run main() against ``blade`` and return the module mock.

    The SDK models are replaced by plain data, so a request body can be
    compared as a dict (LocalUserPost, LocalUserPatch), a name
    (ReferenceWritable) or a list of group names (LocalUserMembershipPost).
    """
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.params = params
    module.check_mode = check_mode
    with ExitStack() as stack:
        stack.enter_context(patch(MODULE + "AnsibleModule", return_value=module))
        stack.enter_context(patch(MODULE + "get_system", return_value=blade))
        stack.enter_context(patch(MODULE + "HAS_PYPURECLIENT", True))
        loose = stack.enter_context(patch(MODULE + "LooseVersion"))
        loose.return_value.__gt__ = Mock(return_value=False)
        stack.enter_context(patch(MODULE + "get_error_message", side_effect=_message))
        stack.enter_context(
            patch(MODULE + "ReferenceWritable", side_effect=lambda name: name)
        )
        stack.enter_context(
            patch(MODULE + "LocalUserPost", side_effect=lambda **fields: fields)
        )
        stack.enter_context(
            patch(MODULE + "LocalUserPatch", side_effect=lambda **fields: fields)
        )
        stack.enter_context(
            patch(
                MODULE + "LocalUserMembershipPostGroups",
                side_effect=lambda group: group,
            )
        )
        stack.enter_context(
            patch(MODULE + "LocalUserMembershipPost", side_effect=lambda groups: groups)
        )
        try:
            main()
        except SystemExit:
            pass
    return module


def _writes(blade):
    """Names of the write requests sent to the array, in order"""
    return [
        call[0]
        for call in blade.method_calls
        if call[0].startswith(("post_", "patch_", "delete_"))
    ]


class TestPurefbLocalUser:
    """Test cases for purefb_local_user module"""

    # ---------------- helper-function unit tests ----------------

    def test_get_user_returns_first_item(self):
        """_get_user returns the first hit"""
        module = Mock()
        module.params = {"name": "alice", "context": ""}

        existing = Mock()
        existing.name = "alice"
        response = Mock()
        response.status_code = 200
        response.items = [existing]

        blade = Mock()
        blade.get_directory_services_local_users.return_value = response

        assert _get_user(module, blade, "myserver_local") is existing
        blade.get_directory_services_local_users.assert_called_once_with(
            names=["alice"],
            filter="local_directory_service.name='myserver_local'",
        )

    def test_get_user_returns_none_when_empty(self):
        """_get_user returns None when items is empty"""
        module = Mock()
        module.params = {"name": "alice", "context": ""}

        response = Mock()
        response.status_code = 200
        response.items = []
        blade = Mock()
        blade.get_directory_services_local_users.return_value = response

        assert _get_user(module, blade, "myserver_local") is None

    def test_get_current_groups_extracts_names(self):
        """_get_current_groups returns the set of the user's current group names"""
        module = Mock()
        module.params = {"name": "alice", "context": ""}
        module.fail_json = Mock(side_effect=SystemExit)

        edge_a = Mock()
        edge_a.group = Mock()
        edge_a.group.name = "developers"
        edge_b = Mock()
        edge_b.group = Mock()
        edge_b.group.name = "infra"

        response = Mock()
        response.status_code = 200
        response.items = [edge_a, edge_b]
        blade = Mock()
        blade.get_directory_services_local_users_members.return_value = response

        result = _get_current_groups(module, blade, "myserver_local")
        assert result == {"developers", "infra"}

    # ---------------- _reconcile_memberships tests ----------------

    def test_reconcile_adds_missing(self):
        """_reconcile_memberships POSTs groups the user isn't in yet"""
        module = Mock()
        module.params = {
            "name": "alice",
            "groups": ["developers", "infra"],
            "context": "",
        }
        module.check_mode = False
        module.fail_json = Mock(side_effect=SystemExit)

        current_response = Mock()
        current_response.status_code = 200
        current_response.items = []
        post_response = Mock()
        post_response.status_code = 200

        blade = Mock()
        blade.get_directory_services_local_users_members.return_value = current_response
        blade.post_directory_services_local_users_members.return_value = post_response

        changed = _reconcile_memberships(module, blade, "myserver_local", "alice")
        assert changed is True
        blade.post_directory_services_local_users_members.assert_called_once()
        blade.delete_directory_services_local_users_members.assert_not_called()

    def test_reconcile_removes_extras(self):
        """_reconcile_memberships DELETEs groups the user should no longer be in"""
        module = Mock()
        module.params = {
            "name": "alice",
            "groups": ["developers"],
            "context": "",
        }
        module.check_mode = False
        module.fail_json = Mock(side_effect=SystemExit)

        keep = Mock()
        keep.group = Mock()
        keep.group.name = "developers"
        drop = Mock()
        drop.group = Mock()
        drop.group.name = "infra"

        current_response = Mock()
        current_response.status_code = 200
        current_response.items = [keep, drop]
        delete_response = Mock()
        delete_response.status_code = 200

        blade = Mock()
        blade.get_directory_services_local_users_members.return_value = current_response
        blade.delete_directory_services_local_users_members.return_value = (
            delete_response
        )

        changed = _reconcile_memberships(module, blade, "myserver_local", "alice")
        assert changed is True
        blade.delete_directory_services_local_users_members.assert_called_once_with(
            member_names=["alice"],
            group_names=["infra"],
            local_directory_service_names=["myserver_local"],
        )
        blade.post_directory_services_local_users_members.assert_not_called()

    def test_reconcile_excludes_primary_group(self):
        """_reconcile_memberships never touches the primary-group edge"""
        module = Mock()
        module.params = {
            "name": "alice",
            "groups": ["developers"],
            "context": "",
        }
        module.check_mode = False
        module.fail_json = Mock(side_effect=SystemExit)

        primary_edge = Mock()
        primary_edge.group = Mock()
        primary_edge.group.name = "alice"  # primary
        dev_edge = Mock()
        dev_edge.group = Mock()
        dev_edge.group.name = "developers"

        current_response = Mock()
        current_response.status_code = 200
        current_response.items = [primary_edge, dev_edge]

        blade = Mock()
        blade.get_directory_services_local_users_members.return_value = current_response

        changed = _reconcile_memberships(
            module, blade, "myserver_local", desired_primary_group="alice"
        )
        assert changed is False
        blade.post_directory_services_local_users_members.assert_not_called()
        blade.delete_directory_services_local_users_members.assert_not_called()

    def test_reconcile_check_mode_skips_writes(self):
        """_reconcile_memberships reports changed but skips writes in check mode"""
        module = Mock()
        module.params = {
            "name": "alice",
            "groups": ["developers"],
            "context": "",
        }
        module.check_mode = True
        module.fail_json = Mock(side_effect=SystemExit)

        current_response = Mock()
        current_response.status_code = 200
        current_response.items = []

        blade = Mock()
        blade.get_directory_services_local_users_members.return_value = current_response

        changed = _reconcile_memberships(module, blade, "myserver_local", "alice")
        assert changed is True
        blade.post_directory_services_local_users_members.assert_not_called()
        blade.delete_directory_services_local_users_members.assert_not_called()

    # ---------------- main() flows ----------------

    @patch("plugins.modules.purefb_local_user.LooseVersion")
    @patch("plugins.modules.purefb_local_user.ReferenceWritable")
    @patch("plugins.modules.purefb_local_user.LocalUserPost")
    @patch("plugins.modules.purefb_local_user.get_system")
    @patch("plugins.modules.purefb_local_user.AnsibleModule")
    @patch("plugins.modules.purefb_local_user.HAS_PYPURECLIENT", True)
    def test_main_creates_user(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_user_post,
        mock_reference_writable,
        mock_loose_version,
    ):
        """Test creating a new local user with primary_group and uid"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(
            uid=5001,
            email="alice@example.com",
            primary_group="alice",
        )
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        blade.get_directory_services_local_directory_services.return_value = (
            _lds_response()
        )
        mock_get_system.return_value = blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        blade.get_directory_services_local_users.return_value = get_response

        created = Mock()
        created.name = "alice"
        created.uid = 5001
        created.sid = "S-1-5-21-2"
        created.enabled = True
        created.primary_group = Mock()
        created.primary_group.name = "alice"

        post_response = Mock()
        post_response.status_code = 200
        post_response.items = [created]
        blade.post_directory_services_local_users.return_value = post_response

        try:
            main()
        except SystemExit:
            pass

        blade.post_directory_services_local_users.assert_called_once()
        call_kwargs = blade.post_directory_services_local_users.call_args[1]
        assert call_kwargs["names"] == ["alice"]
        assert call_kwargs["local_directory_service_names"] == ["myserver_local"]
        mock_user_post.assert_called_once()
        mock_reference_writable.assert_any_call(name="alice")
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_local_user.LooseVersion")
    @patch("plugins.modules.purefb_local_user.get_system")
    @patch("plugins.modules.purefb_local_user.AnsibleModule")
    @patch("plugins.modules.purefb_local_user.HAS_PYPURECLIENT", True)
    def test_main_create_fails_without_password_when_enabled(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test create fails when enabled=true and no password is provided"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(password=None, enabled=True)
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        blade.get_directory_services_local_directory_services.return_value = (
            _lds_response()
        )
        mock_get_system.return_value = blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        blade.get_directory_services_local_users.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "password" in module.fail_json.call_args[1]["msg"]
        blade.post_directory_services_local_users.assert_not_called()

    @patch("plugins.modules.purefb_local_user.LooseVersion")
    @patch("plugins.modules.purefb_local_user.get_system")
    @patch("plugins.modules.purefb_local_user.AnsibleModule")
    @patch("plugins.modules.purefb_local_user.HAS_PYPURECLIENT", True)
    def test_main_create_check_mode_skips_post(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test create reports changed but skips POST in check mode"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(primary_group="alice")
        module.check_mode = True
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        blade.get_directory_services_local_directory_services.return_value = (
            _lds_response()
        )
        mock_get_system.return_value = blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        blade.get_directory_services_local_users.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        blade.post_directory_services_local_users.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_local_user.LooseVersion")
    @patch("plugins.modules.purefb_local_user.get_system")
    @patch("plugins.modules.purefb_local_user.AnsibleModule")
    @patch("plugins.modules.purefb_local_user.HAS_PYPURECLIENT", True)
    def test_main_create_fails_on_api_error(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test create surfaces API error via fail_json"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(primary_group="alice")
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        blade.get_directory_services_local_directory_services.return_value = (
            _lds_response()
        )
        mock_get_system.return_value = blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        blade.get_directory_services_local_users.return_value = get_response

        post_response = Mock()
        post_response.status_code = 400
        post_response.errors = []
        blade.post_directory_services_local_users.return_value = post_response

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "Failed to create local user" in module.fail_json.call_args[1]["msg"]

    @patch("plugins.modules.purefb_local_user.LooseVersion")
    @patch("plugins.modules.purefb_local_user.LocalUserPatch")
    @patch("plugins.modules.purefb_local_user.get_system")
    @patch("plugins.modules.purefb_local_user.AnsibleModule")
    @patch("plugins.modules.purefb_local_user.HAS_PYPURECLIENT", True)
    def test_main_updates_email(
        self, mock_ansible_module, mock_get_system, mock_user_patch, mock_loose_version
    ):
        """Test updating email on an existing user"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(
            email="new@example.com", password=None, primary_group="alice"
        )
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        blade.get_directory_services_local_directory_services.return_value = (
            _lds_response()
        )
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "alice"
        existing.built_in = False
        existing.email = "old@example.com"
        existing.enabled = True
        existing.uid = 5001
        existing.primary_group = Mock()
        existing.primary_group.name = "alice"

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_users.return_value = get_response

        patch_response = Mock()
        patch_response.status_code = 200
        blade.patch_directory_services_local_users.return_value = patch_response

        try:
            main()
        except SystemExit:
            pass

        blade.patch_directory_services_local_users.assert_called_once()
        mock_user_patch.assert_called_once_with(email="new@example.com")
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_local_user.LooseVersion")
    @patch("plugins.modules.purefb_local_user.get_system")
    @patch("plugins.modules.purefb_local_user.AnsibleModule")
    @patch("plugins.modules.purefb_local_user.HAS_PYPURECLIENT", True)
    def test_main_update_idempotent_when_no_changes(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test update is a no-op when nothing changed"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(
            uid=5001,
            email="alice@example.com",
            password=None,
        )
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        blade.get_directory_services_local_directory_services.return_value = (
            _lds_response()
        )
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "alice"
        existing.built_in = False
        existing.email = "alice@example.com"
        existing.enabled = True
        existing.uid = 5001
        existing.primary_group = None

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_users.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        blade.patch_directory_services_local_users.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_local_user.LooseVersion")
    @patch("plugins.modules.purefb_local_user.LocalUserPatch")
    @patch("plugins.modules.purefb_local_user.get_system")
    @patch("plugins.modules.purefb_local_user.AnsibleModule")
    @patch("plugins.modules.purefb_local_user.HAS_PYPURECLIENT", True)
    def test_main_renames_user(
        self, mock_ansible_module, mock_get_system, mock_user_patch, mock_loose_version
    ):
        """Test renaming an existing user via new_name"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(new_name="alice2", password=None)
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        blade.get_directory_services_local_directory_services.return_value = (
            _lds_response()
        )
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "alice"
        existing.built_in = False
        existing.email = None
        existing.enabled = True
        existing.uid = 5001
        existing.primary_group = None

        # First call from _get_user, second from the rename-clash lookup
        first_response = Mock()
        first_response.status_code = 200
        first_response.items = [existing]
        clash_response = Mock()
        clash_response.status_code = 200
        clash_response.items = []
        blade.get_directory_services_local_users.side_effect = [
            first_response,
            clash_response,
        ]

        patch_response = Mock()
        patch_response.status_code = 200
        blade.patch_directory_services_local_users.return_value = patch_response

        try:
            main()
        except SystemExit:
            pass

        mock_user_patch.assert_called_once_with(name="alice2")
        blade.patch_directory_services_local_users.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_local_user.LooseVersion")
    @patch("plugins.modules.purefb_local_user.get_system")
    @patch("plugins.modules.purefb_local_user.AnsibleModule")
    @patch("plugins.modules.purefb_local_user.HAS_PYPURECLIENT", True)
    def test_main_rename_fails_when_target_exists(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test rename fails cleanly when the target name already exists"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(new_name="alice2", password=None)
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        blade.get_directory_services_local_directory_services.return_value = (
            _lds_response()
        )
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "alice"
        existing.built_in = False
        existing.email = None
        existing.enabled = True
        existing.uid = 5001
        existing.primary_group = None

        clash = Mock()
        clash.name = "alice2"
        first_response = Mock()
        first_response.status_code = 200
        first_response.items = [existing]
        clash_response = Mock()
        clash_response.status_code = 200
        clash_response.items = [clash]
        blade.get_directory_services_local_users.side_effect = [
            first_response,
            clash_response,
        ]

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "target name already exists" in module.fail_json.call_args[1]["msg"]
        blade.patch_directory_services_local_users.assert_not_called()

    @patch("plugins.modules.purefb_local_user.LooseVersion")
    @patch("plugins.modules.purefb_local_user.get_system")
    @patch("plugins.modules.purefb_local_user.AnsibleModule")
    @patch("plugins.modules.purefb_local_user.HAS_PYPURECLIENT", True)
    def test_main_refuses_to_rename_builtin(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test rename is refused on built-in users"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(
            name="Administrator", new_name="root", password=None
        )
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        blade.get_directory_services_local_directory_services.return_value = (
            _lds_response()
        )
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "Administrator"
        existing.built_in = True
        existing.email = None
        existing.enabled = True
        existing.uid = 500
        existing.primary_group = None

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_users.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "built-in" in module.fail_json.call_args[1]["msg"]
        blade.patch_directory_services_local_users.assert_not_called()

    @patch("plugins.modules.purefb_local_user.LooseVersion")
    @patch("plugins.modules.purefb_local_user.LocalUserPatch")
    @patch("plugins.modules.purefb_local_user.get_system")
    @patch("plugins.modules.purefb_local_user.AnsibleModule")
    @patch("plugins.modules.purefb_local_user.HAS_PYPURECLIENT", True)
    def test_main_disables_user(
        self, mock_ansible_module, mock_get_system, mock_user_patch, mock_loose_version
    ):
        """Test disabling an existing user"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(enabled=False, password=None)
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        blade.get_directory_services_local_directory_services.return_value = (
            _lds_response()
        )
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "alice"
        existing.built_in = False
        existing.email = None
        existing.enabled = True
        existing.uid = 5001
        existing.primary_group = None

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_users.return_value = get_response

        patch_response = Mock()
        patch_response.status_code = 200
        blade.patch_directory_services_local_users.return_value = patch_response

        try:
            main()
        except SystemExit:
            pass

        blade.patch_directory_services_local_users.assert_called_once()
        mock_user_patch.assert_called_once_with(enabled=False)
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_local_user.LooseVersion")
    @patch("plugins.modules.purefb_local_user.get_system")
    @patch("plugins.modules.purefb_local_user.AnsibleModule")
    @patch("plugins.modules.purefb_local_user.HAS_PYPURECLIENT", True)
    def test_main_reenable_requires_password(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test re-enabling a disabled user requires a password"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(enabled=True, password=None)
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        blade.get_directory_services_local_directory_services.return_value = (
            _lds_response()
        )
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "alice"
        existing.built_in = False
        existing.email = None
        existing.enabled = False
        existing.uid = 5001
        existing.primary_group = None

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_users.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "password" in module.fail_json.call_args[1]["msg"]
        blade.patch_directory_services_local_users.assert_not_called()

    @patch("plugins.modules.purefb_local_user.LooseVersion")
    @patch("plugins.modules.purefb_local_user.LocalUserPatch")
    @patch("plugins.modules.purefb_local_user.get_system")
    @patch("plugins.modules.purefb_local_user.AnsibleModule")
    @patch("plugins.modules.purefb_local_user.HAS_PYPURECLIENT", True)
    def test_main_force_password_reset_patches_password(
        self, mock_ansible_module, mock_get_system, mock_user_patch, mock_loose_version
    ):
        """Test force_password_reset=true includes the password in the PATCH body"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(force_password_reset=True, password="brandnew!")
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        blade.get_directory_services_local_directory_services.return_value = (
            _lds_response()
        )
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "alice"
        existing.built_in = False
        existing.email = None
        existing.enabled = True
        existing.uid = 5001
        existing.primary_group = None

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_users.return_value = get_response

        patch_response = Mock()
        patch_response.status_code = 200
        blade.patch_directory_services_local_users.return_value = patch_response

        try:
            main()
        except SystemExit:
            pass

        blade.patch_directory_services_local_users.assert_called_once()
        mock_user_patch.assert_called_once_with(password="brandnew!")
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_local_user.LooseVersion")
    @patch("plugins.modules.purefb_local_user.get_system")
    @patch("plugins.modules.purefb_local_user.AnsibleModule")
    @patch("plugins.modules.purefb_local_user.HAS_PYPURECLIENT", True)
    def test_main_force_password_reset_requires_password(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test force_password_reset=true without a password fails cleanly"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(force_password_reset=True, password=None)
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        blade.get_directory_services_local_directory_services.return_value = (
            _lds_response()
        )
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "alice"
        existing.built_in = False
        existing.email = None
        existing.enabled = True
        existing.uid = 5001
        existing.primary_group = None

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_users.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "force_password_reset" in module.fail_json.call_args[1]["msg"]
        blade.patch_directory_services_local_users.assert_not_called()

    @patch("plugins.modules.purefb_local_user.LooseVersion")
    @patch("plugins.modules.purefb_local_user.get_system")
    @patch("plugins.modules.purefb_local_user.AnsibleModule")
    @patch("plugins.modules.purefb_local_user.HAS_PYPURECLIENT", True)
    def test_main_deletes_user(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test deleting an existing user"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(state="absent", password=None)
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        blade.get_directory_services_local_directory_services.return_value = (
            _lds_response()
        )
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "alice"
        existing.built_in = False

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_users.return_value = get_response

        delete_response = Mock()
        delete_response.status_code = 200
        blade.delete_directory_services_local_users.return_value = delete_response

        try:
            main()
        except SystemExit:
            pass

        blade.delete_directory_services_local_users.assert_called_once_with(
            names=["alice"],
            local_directory_service_names=["myserver_local"],
        )
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_local_user.LooseVersion")
    @patch("plugins.modules.purefb_local_user.get_system")
    @patch("plugins.modules.purefb_local_user.AnsibleModule")
    @patch("plugins.modules.purefb_local_user.HAS_PYPURECLIENT", True)
    def test_main_delete_check_mode_skips_call(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test delete reports changed but skips DELETE in check mode"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(state="absent", password=None)
        module.check_mode = True
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        blade.get_directory_services_local_directory_services.return_value = (
            _lds_response()
        )
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "alice"
        existing.built_in = False

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_users.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        blade.delete_directory_services_local_users.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_local_user.LooseVersion")
    @patch("plugins.modules.purefb_local_user.get_system")
    @patch("plugins.modules.purefb_local_user.AnsibleModule")
    @patch("plugins.modules.purefb_local_user.HAS_PYPURECLIENT", True)
    def test_main_refuses_to_delete_builtin(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test delete is refused on built-in users"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(
            state="absent", name="Administrator", password=None
        )
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        blade.get_directory_services_local_directory_services.return_value = (
            _lds_response()
        )
        mock_get_system.return_value = blade

        existing = Mock()
        existing.name = "Administrator"
        existing.built_in = True

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = [existing]
        blade.get_directory_services_local_users.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "built-in" in module.fail_json.call_args[1]["msg"]
        blade.delete_directory_services_local_users.assert_not_called()

    @patch("plugins.modules.purefb_local_user.LooseVersion")
    @patch("plugins.modules.purefb_local_user.get_system")
    @patch("plugins.modules.purefb_local_user.AnsibleModule")
    @patch("plugins.modules.purefb_local_user.HAS_PYPURECLIENT", True)
    def test_main_delete_nonexistent_is_noop(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test state=absent on a nonexistent user reports changed=False"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(state="absent", name="ghost", password=None)
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        blade.get_directory_services_local_directory_services.return_value = (
            _lds_response()
        )
        mock_get_system.return_value = blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        blade.get_directory_services_local_users.return_value = get_response

        try:
            main()
        except SystemExit:
            pass

        blade.delete_directory_services_local_users.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_local_user.LooseVersion")
    @patch("plugins.modules.purefb_local_user.LocalUserPost")
    @patch("plugins.modules.purefb_local_user.get_system")
    @patch("plugins.modules.purefb_local_user.AnsibleModule")
    @patch("plugins.modules.purefb_local_user.HAS_PYPURECLIENT", True)
    def test_main_create_with_groups_reconciles(
        self, mock_ansible_module, mock_get_system, mock_user_post, mock_loose_version
    ):
        """Test create-with-groups POSTs the user then reconciles memberships"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(
            primary_group="alice",
            groups=["developers", "infra"],
        )
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.24"]
        blade.get_directory_services_local_directory_services.return_value = (
            _lds_response()
        )
        mock_get_system.return_value = blade

        get_response = Mock()
        get_response.status_code = 200
        get_response.items = []
        blade.get_directory_services_local_users.return_value = get_response

        created = Mock()
        created.name = "alice"
        created.uid = 5001
        created.sid = "S-1"
        created.enabled = True
        created.primary_group = Mock()
        created.primary_group.name = "alice"

        post_response = Mock()
        post_response.status_code = 200
        post_response.items = [created]
        blade.post_directory_services_local_users.return_value = post_response

        members_current = Mock()
        members_current.status_code = 200
        members_current.items = []
        blade.get_directory_services_local_users_members.return_value = members_current

        post_members = Mock()
        post_members.status_code = 200
        blade.post_directory_services_local_users_members.return_value = post_members

        try:
            main()
        except SystemExit:
            pass

        blade.post_directory_services_local_users.assert_called_once()
        blade.post_directory_services_local_users_members.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_local_user.LooseVersion")
    @patch("plugins.modules.purefb_local_user.get_system")
    @patch("plugins.modules.purefb_local_user.AnsibleModule")
    @patch("plugins.modules.purefb_local_user.HAS_PYPURECLIENT", True)
    def test_main_fails_on_unsupported_api_version(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test failure when the array API version is older than MIN_REQUIRED_API_VERSION"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params(primary_group="alice")
        module.check_mode = False
        mock_ansible_module.return_value = module

        blade = Mock()
        blade.get_versions.return_value.items = ["2.17", "2.18", "2.19"]
        mock_get_system.return_value = blade

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "REST version not supported" in module.fail_json.call_args[1]["msg"]

    @patch("plugins.modules.purefb_local_user.LooseVersion")
    @patch("plugins.modules.purefb_local_user.get_system")
    @patch("plugins.modules.purefb_local_user.AnsibleModule")
    @patch("plugins.modules.purefb_local_user.HAS_PYPURECLIENT", False)
    def test_main_fails_without_sdk(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Test failure when py-pure-client SDK is not installed"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = Mock()
        module.exit_json = Mock(side_effect=SystemExit)
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params()
        module.check_mode = False
        mock_ansible_module.return_value = module

        try:
            main()
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "py-pure-client" in module.fail_json.call_args[1]["msg"]


class TestLocalDirectoryServiceLookup:
    """The LDS is read before anything else, in a realm and at array level"""

    @patch(MODULE + "get_error_message", side_effect=_message)
    def test_get_local_ds_returns_the_lds(self, mock_message):
        """_get_local_ds returns the LDS under the realm-qualified name"""
        module = Mock()
        module.params = {"context": ""}
        blade = _array(visible_lds=[REALM_LDS])

        assert _get_local_ds(module, blade, REALM_LDS).name == REALM_LDS
        blade.get_directory_services_local_directory_services.assert_called_once_with(
            names=[REALM_LDS]
        )

    @patch(MODULE + "get_error_message", side_effect=_message)
    def test_get_local_ds_none_when_it_does_not_exist(self, mock_message):
        """_get_local_ds returns None for the array's "does not exist" answer"""
        module = Mock()
        module.params = {"context": ""}
        module.fail_json = Mock(side_effect=SystemExit)

        assert _get_local_ds(module, _array(), "myrealm::nolds") is None
        module.fail_json.assert_not_called()

    @patch(MODULE + "get_error_message", side_effect=_message)
    def test_get_local_ds_reports_a_refused_read(self, mock_message):
        """_get_local_ds fails with the array's message for any other answer"""
        module = Mock()
        module.params = {"context": ""}
        module.fail_json = Mock(side_effect=SystemExit)
        blade = Mock()
        blade.get_directory_services_local_directory_services.return_value = _error(
            "Operation not permitted.", 403
        )

        try:
            _get_local_ds(module, blade, "myserver_local")
        except SystemExit:
            pass

        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to read local directory service myserver_local" in msg
        assert "Operation not permitted." in msg

    @patch(MODULE + "get_error_message", side_effect=_message)
    def test_get_user_by_another_name(self, mock_message):
        """_get_user looks up the name it is given inside the LDS"""
        module = Mock()
        module.params = {"name": "alice", "context": ""}
        blade = _array(users=[_user("alice2", REALM_LDS, "staff")])

        assert _get_user(module, blade, REALM_LDS, "alice2").name == "alice2"
        blade.get_directory_services_local_users.assert_called_once_with(
            names=["alice2"],
            filter="local_directory_service.name='myrealm::myserver_local'",
        )
        assert _get_user(module, blade, REALM_LDS) is None

    @patch(MODULE + "get_error_message", side_effect=_message)
    def test_get_user_reports_a_refused_read(self, mock_message):
        """_get_user does not read a refused GET as "no such user" """
        module = Mock()
        module.params = {"name": "alice", "context": ""}
        module.fail_json = Mock(side_effect=SystemExit)
        blade = Mock()
        blade.get_directory_services_local_users.return_value = _error(
            "Operation not permitted. Authorization for 'get' on "
            "'directory-services/local/users' is required.",
            403,
        )

        try:
            _get_user(module, blade, "myserver_local")
        except SystemExit:
            pass

        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to read local user alice" in msg
        assert "Operation not permitted." in msg

    def test_create_in_missing_lds_fails_in_both_modes(self):
        """A create in an LDS that does not exist stops before the POST"""
        for check_mode in (True, False):
            blade = _array(visible_lds=[REALM_LDS])
            module = _run(
                _base_params(
                    name="bob",
                    local_directory_service="myrealm::nolds",
                    primary_group="staff",
                    enabled=False,
                    password=None,
                ),
                blade,
                check_mode=check_mode,
            )

            module.exit_json.assert_not_called()
            msg = module.fail_json.call_args[1]["msg"]
            assert "myrealm::nolds does not exist or cannot be managed" in msg
            assert "realm::name" in msg
            assert _writes(blade) == []

    def test_update_in_hidden_lds_fails_in_both_modes(self):
        """A user the array lists from an LDS it hides is not updated"""
        for check_mode in (True, False):
            # A realm-scoped administrator: only the LDS of its realm is
            # readable, but the users of the array-level LDS are listed.
            blade = _array(
                visible_lds=[REALM_LDS],
                users=[_user("alice", "myserver_local", "staff")],
            )
            module = _run(
                _base_params(primary_group="staff", uid=2000, enabled=None),
                blade,
                check_mode=check_mode,
            )

            module.exit_json.assert_not_called()
            msg = module.fail_json.call_args[1]["msg"]
            assert "myserver_local does not exist or cannot be managed" in msg
            assert _writes(blade) == []

    def test_delete_in_hidden_lds_fails_in_both_modes(self):
        """A user the array lists from an LDS it hides is not deleted"""
        for lds in ("myserver_local", "otherrealm::myserver_local"):
            for check_mode in (True, False):
                blade = _array(
                    visible_lds=[REALM_LDS], users=[_user("alice", lds, "staff")]
                )
                module = _run(
                    _base_params(state="absent", local_directory_service=lds),
                    blade,
                    check_mode=check_mode,
                )

                module.exit_json.assert_not_called()
                msg = module.fail_json.call_args[1]["msg"]
                assert "does not exist or cannot be managed" in msg
                assert _writes(blade) == []

    def test_delete_in_missing_lds_is_noop(self):
        """Nothing is left to delete when neither the LDS nor the user exists"""
        for lds in ("myserver_local", "myrealm::nolds"):
            blade = _array(visible_lds=[REALM_LDS])
            module = _run(
                _base_params(state="absent", local_directory_service=lds), blade
            )

            module.fail_json.assert_not_called()
            assert module.exit_json.call_args[1]["changed"] is False
            assert _writes(blade) == []

    def test_refused_lds_read_is_not_absent(self):
        """A refused read of the LDS fails, also for state=absent"""
        blade = _array()
        blade.get_directory_services_local_directory_services.side_effect = None
        blade.get_directory_services_local_directory_services.return_value = _error(
            "Operation not permitted.", 403
        )
        module = _run(_base_params(state="absent"), blade)

        module.exit_json.assert_not_called()
        assert "Operation not permitted." in module.fail_json.call_args[1]["msg"]
        assert _writes(blade) == []

    def test_refused_user_read_does_not_create(self):
        """A refused read of the user is reported, not taken for "absent" """
        blade = _array(visible_lds=["myserver_local"])
        blade.get_directory_services_local_users.side_effect = None
        blade.get_directory_services_local_users.return_value = _error(
            "Operation not permitted.", 403
        )
        module = _run(_base_params(primary_group="staff"), blade)

        module.exit_json.assert_not_called()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to read local user alice" in msg
        assert _writes(blade) == []

    def test_create_in_realm_lds(self):
        """A user of a realm LDS is created under bare user and group names"""
        blade = _array(
            visible_lds=[REALM_LDS], groups={REALM_LDS: ["staff", "developers"]}
        )
        module = _run(
            _base_params(
                name="bob",
                local_directory_service=REALM_LDS,
                primary_group="staff",
                groups=["developers"],
            ),
            blade,
        )

        module.fail_json.assert_not_called()
        assert _writes(blade) == [USERS_POST, MEMBERS_POST]
        assert blade.post_directory_services_local_users.call_args[1] == {
            "names": ["bob"],
            "local_directory_service_names": [REALM_LDS],
            "local_user": {
                "enabled": True,
                "password": "s3cret!",
                "primary_group": "staff",
            },
        }
        assert blade.post_directory_services_local_users_members.call_args[1] == {
            "local_membership": ["developers"],
            "member_names": ["bob"],
            "local_directory_service_names": [REALM_LDS],
        }
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_in_realm_lds_leaves_the_namesake_alone(self):
        """The delete names the realm LDS, not the array-level namesake"""
        blade = _array(
            visible_lds=[REALM_LDS, "myserver_local"],
            users=[
                _user("alice", REALM_LDS, "staff"),
                _user("alice", "myserver_local", "staff"),
            ],
        )
        module = _run(
            _base_params(state="absent", local_directory_service=REALM_LDS), blade
        )

        blade.delete_directory_services_local_users.assert_called_once_with(
            names=["alice"], local_directory_service_names=[REALM_LDS]
        )
        assert module.exit_json.call_args[1]["changed"] is True


class TestGroupChecks:
    """Groups that the LDS does not have stop the task before any write"""

    @patch(MODULE + "get_error_message", side_effect=_message)
    def test_require_groups_names_the_missing_group(self, mock_message):
        """_require_groups fails for a group the array does not find"""
        module = Mock()
        module.params = {"context": ""}
        module.fail_json = Mock(side_effect=SystemExit)
        blade = _array(groups={REALM_LDS: ["staff"]})

        _require_groups(module, blade, REALM_LDS, ["STAFF"])
        module.fail_json.assert_not_called()
        try:
            _require_groups(module, blade, REALM_LDS, ["staff", "myrealm::staff"])
        except SystemExit:
            pass

        msg = module.fail_json.call_args[1]["msg"]
        assert "Local group myrealm::staff does not exist" in msg
        assert "without a realm prefix" in msg

    @patch(MODULE + "get_error_message", side_effect=_message)
    def test_require_groups_leaves_a_refused_read_to_the_array(self, mock_message):
        """_require_groups only refuses on a definite "not found" """
        module = Mock()
        module.params = {"context": ""}
        module.fail_json = Mock(side_effect=SystemExit)
        blade = Mock()
        blade.get_directory_services_local_groups.return_value = _error(
            "Operation not permitted.", 403
        )

        _require_groups(module, blade, "myserver_local", ["staff"])
        module.fail_json.assert_not_called()

    def test_membership_plan_ignores_case_and_primary_groups(self):
        """_membership_plan adds the task's spelling, removes the array's"""
        module = Mock()
        module.params = {"groups": ["Developers", "infra", "STAFF", "Admins"]}

        add, remove = _membership_plan(
            module, {"developers", "staff", "old", "wheel"}, ("admins", "Wheel")
        )

        assert add == ["infra"]
        assert remove == ["old"]

    def test_create_with_missing_primary_group_fails_in_both_modes(self):
        """A create with a primary group the LDS lacks stops before the POST"""
        for check_mode in (True, False):
            blade = _array(visible_lds=[REALM_LDS], groups={REALM_LDS: ["staff"]})
            module = _run(
                _base_params(
                    local_directory_service=REALM_LDS, primary_group="myrealm::staff"
                ),
                blade,
                check_mode=check_mode,
            )

            module.exit_json.assert_not_called()
            msg = module.fail_json.call_args[1]["msg"]
            assert "Local group myrealm::staff does not exist" in msg
            assert _writes(blade) == []

    def test_create_with_missing_group_fails_before_the_post(self):
        """A create with a group the LDS lacks does not leave a user behind"""
        blade = _array(
            visible_lds=["myserver_local"], groups={"myserver_local": ["staff"]}
        )
        module = _run(_base_params(primary_group="staff", groups=["nogroup"]), blade)

        module.exit_json.assert_not_called()
        assert "Local group nogroup" in module.fail_json.call_args[1]["msg"]
        assert _writes(blade) == []

    def test_create_with_refused_group_read_is_left_to_the_array(self):
        """A group read the array refuses does not block the create"""
        blade = _array(visible_lds=["myserver_local"])
        blade.get_directory_services_local_groups.side_effect = None
        blade.get_directory_services_local_groups.return_value = _error(
            "Operation not permitted.", 403
        )
        module = _run(_base_params(primary_group="staff"), blade)

        module.fail_json.assert_not_called()
        assert _writes(blade) == [USERS_POST]

    def test_update_with_missing_group_fails_before_any_write(self):
        """An update whose groups the LDS lacks sends nothing, PATCH included"""
        for check_mode in (True, False):
            blade = _array(
                visible_lds=["myserver_local"],
                users=[_user("alice", "myserver_local", "staff")],
                groups={"myserver_local": ["staff"]},
                memberships={
                    ("myserver_local", "alice"): [_edge("staff", primary=True)]
                },
            )
            module = _run(
                _base_params(
                    primary_group="staff",
                    groups=["nogroup"],
                    email="alice@example.com",
                    enabled=None,
                ),
                blade,
                check_mode=check_mode,
            )

            module.exit_json.assert_not_called()
            assert "Local group nogroup" in module.fail_json.call_args[1]["msg"]
            assert _writes(blade) == []

    def test_groups_in_another_spelling_are_no_change(self):
        """A group named in another letter case is the membership the user has"""
        blade = _array(
            visible_lds=[REALM_LDS],
            users=[_user("alice", REALM_LDS, "staff")],
            groups={REALM_LDS: ["staff", "developers"]},
            memberships={
                (REALM_LDS, "alice"): [
                    _edge("staff", primary=True),
                    _edge("developers"),
                ]
            },
        )
        module = _run(
            _base_params(
                local_directory_service=REALM_LDS,
                primary_group="staff",
                groups=["Developers"],
                enabled=None,
            ),
            blade,
        )

        module.fail_json.assert_not_called()
        assert _writes(blade) == []
        assert module.exit_json.call_args[1]["changed"] is False


class TestPrimaryGroupChange:
    """The module makes the user a member of a new primary group first"""

    def _blade(self, edges, primary_group="staff", lds=REALM_LDS):
        return _array(
            visible_lds=[lds],
            users=[_user("alice", lds, primary_group)],
            groups={lds: ["staff", "admins", "developers", "old"]},
            memberships={(lds, "alice"): edges},
        )

    def test_membership_is_added_before_the_patch(self):
        """A new primary group the user is not in is added, then set"""
        blade = self._blade([_edge("staff", primary=True)])
        module = _run(
            _base_params(
                local_directory_service=REALM_LDS,
                primary_group="admins",
                enabled=None,
            ),
            blade,
        )

        module.fail_json.assert_not_called()
        assert _writes(blade) == [MEMBERS_POST, USERS_PATCH]
        assert blade.post_directory_services_local_users_members.call_args[1] == {
            "local_membership": ["admins"],
            "member_names": ["alice"],
            "local_directory_service_names": [REALM_LDS],
        }
        assert blade.patch_directory_services_local_users.call_args[1] == {
            "names": ["alice"],
            "local_directory_service_names": [REALM_LDS],
            "local_user": {"primary_group": "admins"},
        }
        assert module.exit_json.call_args[1]["changed"] is True

    def test_array_level_lds(self):
        """The same on an array-level LDS"""
        blade = self._blade([_edge("staff", primary=True)], lds="myserver_local")
        module = _run(_base_params(primary_group="admins", enabled=None), blade)

        assert _writes(blade) == [MEMBERS_POST, USERS_PATCH]
        post = blade.post_directory_services_local_users_members.call_args[1]
        assert post["local_directory_service_names"] == ["myserver_local"]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_check_mode_sends_nothing(self):
        """Check mode predicts the change and sends no write"""
        blade = self._blade([_edge("staff", primary=True)])
        module = _run(
            _base_params(
                local_directory_service=REALM_LDS,
                primary_group="admins",
                enabled=None,
            ),
            blade,
            check_mode=True,
        )

        module.fail_json.assert_not_called()
        assert _writes(blade) == []
        assert module.exit_json.call_args[1]["changed"] is True

    def test_missing_group_fails_in_both_modes(self):
        """A primary group the LDS lacks is refused before any write"""
        for check_mode in (True, False):
            blade = self._blade([_edge("staff", primary=True)])
            module = _run(
                _base_params(
                    local_directory_service=REALM_LDS,
                    primary_group="nogroup",
                    enabled=None,
                ),
                blade,
                check_mode=check_mode,
            )

            module.exit_json.assert_not_called()
            assert "Local group nogroup" in module.fail_json.call_args[1]["msg"]
            assert _writes(blade) == []

    def test_existing_membership_is_not_added_again(self):
        """A new primary group the user is already in needs the PATCH only"""
        blade = self._blade([_edge("staff", primary=True), _edge("admins")])
        module = _run(
            _base_params(
                local_directory_service=REALM_LDS,
                primary_group="admins",
                enabled=None,
            ),
            blade,
        )

        assert _writes(blade) == [USERS_PATCH]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_groups_converge_in_one_run(self):
        """With groups set, the former primary group goes in the same run"""
        blade = self._blade([_edge("staff", primary=True), _edge("old")])
        module = _run(
            _base_params(
                local_directory_service=REALM_LDS,
                primary_group="admins",
                groups=["admins", "developers"],
                enabled=None,
            ),
            blade,
        )

        module.fail_json.assert_not_called()
        assert _writes(blade) == [
            MEMBERS_POST,
            MEMBERS_DELETE,
            USERS_PATCH,
            MEMBERS_DELETE,
        ]
        post = blade.post_directory_services_local_users_members.call_args[1]
        assert post["local_membership"] == ["developers", "admins"]
        deletes = blade.delete_directory_services_local_users_members.call_args_list
        assert [call[1]["group_names"] for call in deletes] == [["old"], ["staff"]]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_second_run_is_unchanged(self):
        """The state the first run leaves is the state the task asks for"""
        blade = self._blade(
            [_edge("admins", primary=True), _edge("developers")],
            primary_group="admins",
        )
        module = _run(
            _base_params(
                local_directory_service=REALM_LDS,
                primary_group="admins",
                groups=["admins", "developers"],
                enabled=None,
            ),
            blade,
        )

        assert _writes(blade) == []
        assert module.exit_json.call_args[1]["changed"] is False

    def test_former_primary_group_is_kept_when_listed(self):
        """The former primary group stays when groups lists it"""
        blade = self._blade([_edge("staff", primary=True)])
        module = _run(
            _base_params(
                local_directory_service=REALM_LDS,
                primary_group="admins",
                groups=["Staff"],
                enabled=None,
            ),
            blade,
        )

        assert _writes(blade) == [MEMBERS_POST, USERS_PATCH]
        post = blade.post_directory_services_local_users_members.call_args[1]
        assert post["local_membership"] == ["admins"]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_former_primary_group_is_kept_without_groups(self):
        """Without groups the module leaves the former primary group alone"""
        blade = self._blade([_edge("staff", primary=True), _edge("admins")])
        _run(
            _base_params(
                local_directory_service=REALM_LDS,
                primary_group="admins",
                enabled=None,
            ),
            blade,
        )

        blade.delete_directory_services_local_users_members.assert_not_called()

    def test_another_spelling_is_no_change(self):
        """The current primary group in another letter case is not a change"""
        blade = self._blade([_edge("staff", primary=True)])
        module = _run(
            _base_params(
                local_directory_service=REALM_LDS, primary_group="STAFF", enabled=None
            ),
            blade,
        )

        module.fail_json.assert_not_called()
        assert _writes(blade) == []
        assert module.exit_json.call_args[1]["changed"] is False


class TestRenameIdempotency:
    """A rename that has already happened continues with the renamed user"""

    def _params(self, **overrides):
        # The form of the module's own rename example: no password, no enabled
        params = _base_params(
            new_name="alice2",
            local_directory_service=REALM_LDS,
            primary_group="staff",
            enabled=None,
            password=None,
        )
        params.update(overrides)
        return params

    def _renamed(self, **fields):
        return _array(
            visible_lds=[REALM_LDS],
            users=[_user("alice2", REALM_LDS, "staff", **fields)],
            groups={REALM_LDS: ["staff", "developers"]},
            memberships={(REALM_LDS, "alice2"): [_edge("staff", primary=True)]},
        )

    def test_second_run_is_unchanged(self):
        """The rename task run again finds the renamed user and changes nothing"""
        for check_mode in (True, False):
            blade = self._renamed()
            module = _run(self._params(), blade, check_mode=check_mode)

            module.fail_json.assert_not_called()
            assert _writes(blade) == []
            assert module.exit_json.call_args[1]["changed"] is False

    def test_second_run_does_not_recreate_the_old_name(self):
        """Other options are applied to the renamed user, nothing is created"""
        blade = self._renamed(enabled=True)
        module = _run(self._params(enabled=False, email="a2@example.com"), blade)

        module.fail_json.assert_not_called()
        assert _writes(blade) == [USERS_PATCH]
        assert blade.patch_directory_services_local_users.call_args[1] == {
            "names": ["alice2"],
            "local_directory_service_names": [REALM_LDS],
            "local_user": {"email": "a2@example.com", "enabled": False},
        }
        assert module.exit_json.call_args[1]["changed"] is True

    def test_second_run_reconciles_groups_of_the_renamed_user(self):
        """Memberships are read and written under the new name"""
        blade = self._renamed()
        module = _run(self._params(groups=["developers"]), blade)

        assert _writes(blade) == [MEMBERS_POST]
        post = blade.post_directory_services_local_users_members.call_args[1]
        assert post["member_names"] == ["alice2"]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_rename_then_memberships_use_the_new_name(self):
        """The first run renames, then writes memberships under the new name"""
        blade = _array(
            visible_lds=[REALM_LDS],
            users=[_user("alice", REALM_LDS, "staff")],
            groups={REALM_LDS: ["staff", "developers"]},
            memberships={(REALM_LDS, "alice"): [_edge("staff", primary=True)]},
        )
        module = _run(self._params(groups=["developers"]), blade)

        assert _writes(blade) == [USERS_PATCH, MEMBERS_POST]
        patched = blade.patch_directory_services_local_users.call_args[1]
        assert patched["names"] == ["alice"]
        assert patched["local_user"] == {"name": "alice2"}
        post = blade.post_directory_services_local_users_members.call_args[1]
        assert post["member_names"] == ["alice2"]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_another_spelling_of_the_name_is_no_rename(self):
        """The array keeps the stored spelling, so the module asks for nothing"""
        blade = _array(
            visible_lds=[REALM_LDS], users=[_user("alice", REALM_LDS, "staff")]
        )
        module = _run(self._params(new_name="ALICE"), blade)

        module.fail_json.assert_not_called()
        assert _writes(blade) == []
        assert module.exit_json.call_args[1]["changed"] is False

    def test_both_names_exist_fails(self):
        """A rename onto another user of the LDS is refused"""
        blade = _array(
            visible_lds=[REALM_LDS],
            users=[
                _user("alice", REALM_LDS, "staff"),
                _user("alice2", REALM_LDS, "staff"),
            ],
        )
        module = _run(self._params(), blade)

        assert "target name already exists" in module.fail_json.call_args[1]["msg"]
        assert _writes(blade) == []

    def test_namesake_in_another_lds_is_not_the_renamed_user(self):
        """A user called new_name in another LDS does not end the rename"""
        blade = _array(
            visible_lds=[REALM_LDS, "myserver_local"],
            users=[
                _user("alice", REALM_LDS, "staff"),
                _user("alice2", "myserver_local", "staff"),
            ],
        )
        module = _run(self._params(), blade)

        module.fail_json.assert_not_called()
        assert _writes(blade) == [USERS_PATCH]
        patched = blade.patch_directory_services_local_users.call_args[1]
        assert patched["local_directory_service_names"] == [REALM_LDS]
        assert patched["local_user"] == {"name": "alice2"}

    def test_neither_name_exists_creates_name(self):
        """A user that does not exist yet is created as name"""
        blade = _array(visible_lds=[REALM_LDS], groups={REALM_LDS: ["staff"]})
        module = _run(self._params(enabled=False), blade)

        assert _writes(blade) == [USERS_POST]
        created = blade.post_directory_services_local_users.call_args[1]
        assert created["names"] == ["alice"]
        assert module.exit_json.call_args[1]["changed"] is True

    def test_absent_does_not_follow_new_name(self):
        """state=absent deletes name only; the renamed user is left alone"""
        blade = self._renamed()
        module = _run(self._params(state="absent"), blade)

        assert _writes(blade) == []
        assert module.exit_json.call_args[1]["changed"] is False
