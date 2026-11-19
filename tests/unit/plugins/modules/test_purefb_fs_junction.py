# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_fs_junction module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
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

from plugins.modules.purefb_fs_junction import (
    main,
    _context_kwargs,
    _norm_path,
    _realm,
    _leaf,
    _qualify,
    _same_fs,
    _same_name,
    _get_junction,
    _junction_facts,
    _name_holders,
    _name_refused,
    _stored_realm,
)

REALM_REFUSED = "Realms for File system (projects) and File system (alpha) don't match"

NAME_REFUSED = "Cannot create the filesystem junction since it already exists"


def _base_params(**overrides):
    params = {
        "name": "projects-alpha",
        "state": "present",
        "origin_fs": "projects",
        "destination_fs": "alpha",
        "path": "/alpha",
        "use_existing_directory": False,
        "recreate": False,
        "context": "",
    }
    params.update(overrides)
    return params


def _junction(name="projects-alpha", origin="projects", dest="alpha", path="/alpha"):
    origin_ref = Mock(spec=["name"])
    origin_ref.name = origin
    dest_ref = Mock(spec=["name"])
    dest_ref.name = dest
    junction = Mock(
        spec=[
            "name",
            "origin_file_system",
            "destination_file_system",
            "junction_origin_path",
            "status",
        ]
    )
    junction.name = name
    junction.origin_file_system = origin_ref
    junction.destination_file_system = dest_ref
    junction.junction_origin_path = path
    junction.status = "CONNECTED"
    return junction


def _module(params, check_mode=False):
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.params = params
    module.check_mode = check_mode
    return module


def _blade(existing=None, get_status=200, holders=None, holders_status=200):
    """Return a client mock.

    A lookup by names answers with ``existing``; the lookup by filter, which
    searches every scope for the leaf name, answers with ``holders``.
    """
    blade = Mock()
    blade.get_versions.return_value.items = ["2.25", "2.30"]

    def _get(**kwargs):
        if "filter" in kwargs:
            return Mock(status_code=holders_status, items=list(holders or []))
        return Mock(status_code=get_status, items=[existing] if existing else [])

    blade.get_file_system_junctions.side_effect = _get
    post_response = Mock()
    post_response.status_code = 200
    post_response.items = [_junction()]
    blade.post_file_system_junctions.return_value = post_response
    delete_response = Mock()
    delete_response.status_code = 200
    blade.delete_file_system_junctions.return_value = delete_response
    return blade


def _run_main():
    try:
        main()
    except SystemExit:
        pass


class TestPurefbFsJunction:
    """Test cases for purefb_fs_junction module"""

    # ---------------- helper-function unit tests ----------------

    def test_context_kwargs_returns_empty_without_context(self):
        module = Mock()
        module.params = {"context": ""}
        assert _context_kwargs(module) == {}

    def test_context_kwargs_returns_kwargs_when_set(self):
        module = Mock()
        module.params = {"context": "peer1"}
        assert _context_kwargs(module) == {"context_names": ["peer1"]}

    def test_norm_path_adds_leading_slash_and_strips_trailing(self):
        assert _norm_path("alpha") == "/alpha"
        assert _norm_path("/alpha") == "/alpha"
        assert _norm_path("/alpha/") == "/alpha"
        assert _norm_path("a/b") == "/a/b"
        assert _norm_path(None) is None

    def test_realm_prefix(self):
        assert _realm("realm1::fs1") == "realm1"
        assert _realm("fs1") == ""
        assert _realm(None) == ""

    def test_leaf_strips_realm_prefix(self):
        assert _leaf("realm1::j1") == "j1"
        assert _leaf("j1") == "j1"

    def test_qualify_adds_the_realm_of_the_junction(self):
        assert _qualify("fs1", "realm1") == "realm1::fs1"
        assert _qualify("realm1::fs1", "realm1") == "realm1::fs1"
        assert _qualify("fs1", "") == "fs1"
        assert _qualify(None, "realm1") is None

    def test_junction_facts_qualifies_file_systems_of_a_realm_junction(self):
        """The array reports the references bare; the facts carry the realm"""
        facts = _junction_facts(_junction(name="realm1::projects-alpha"))
        assert facts == {
            "name": "realm1::projects-alpha",
            "origin_fs": "realm1::projects",
            "destination_fs": "realm1::alpha",
            "path": "/alpha",
            "status": "CONNECTED",
        }
        # references that already carry the prefix are left alone
        facts = _junction_facts(
            _junction(
                name="realm1::projects-alpha",
                origin="realm1::projects",
                dest="realm1::alpha",
            )
        )
        assert facts["origin_fs"] == "realm1::projects"
        assert facts["destination_fs"] == "realm1::alpha"

    def test_name_refused_tells_the_name_from_the_path(self):
        assert _name_refused(NAME_REFUSED)
        assert not _name_refused(
            "Local junction origin path already exists, "
            "--use-existing-directory flag is required"
        )
        assert not _name_refused(
            "Local junction already exists on provided path, "
            "please provide another path"
        )
        assert not _name_refused("File system does not exist.")
        assert not _name_refused(None)

    def test_name_holders_searches_every_scope_for_the_leaf(self):
        module = Mock()
        module.params = _base_params(name="realm1::projects-alpha", context="peer1")
        blade = _blade(holders=[_junction(name="realm2::projects-alpha")])

        assert _name_holders(module, blade) == ["realm2::projects-alpha"]
        blade.get_file_system_junctions.assert_called_once_with(
            filter="name='projects-alpha' or name='*::projects-alpha'",
            context_names=["peer1"],
        )

    def test_name_holders_returns_none_when_the_lookup_fails(self):
        module = Mock()
        module.params = _base_params()
        assert _name_holders(module, _blade(holders_status=400)) is None

    def test_junction_facts_reads_references(self):
        facts = _junction_facts(_junction())
        assert facts == {
            "name": "projects-alpha",
            "origin_fs": "projects",
            "destination_fs": "alpha",
            "path": "/alpha",
            "status": "CONNECTED",
        }

    def test_get_junction_returns_first_item(self):
        module = Mock()
        module.params = _base_params()
        existing = _junction()
        blade = _blade(existing=existing)

        assert _get_junction(module, blade) is existing
        blade.get_file_system_junctions.assert_called_once_with(
            names=["projects-alpha"]
        )

    def test_get_junction_passes_context(self):
        module = Mock()
        module.params = _base_params(context="peer1")
        blade = _blade(existing=_junction())

        _get_junction(module, blade)
        blade.get_file_system_junctions.assert_called_once_with(
            names=["projects-alpha"], context_names=["peer1"]
        )

    def test_get_junction_returns_none_when_empty(self):
        module = Mock()
        module.params = _base_params()
        assert _get_junction(module, _blade()) is None

    @patch(
        "plugins.modules.purefb_fs_junction.get_error_message",
        return_value="Cannot find array in fleet",
    )
    def test_get_junction_fails_on_error(self, mock_get_error_message):
        """A failed read fails the task instead of reading as absent"""
        module = _module(_base_params(context="nosucharray"))
        blade = _blade(get_status=400)

        try:
            _get_junction(module, blade)
        except SystemExit:
            pass

        module.fail_json.assert_called_once_with(
            msg=(
                "Failed to read file system junction projects-alpha. "
                "Error: Cannot find array in fleet"
            )
        )

    # ---------------- main() flows ----------------

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.Reference")
    @patch("plugins.modules.purefb_fs_junction.FileSystemJunction")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_creates_junction(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_fsj,
        mock_reference,
        mock_loose_version,
    ):
        """A missing junction is created with the array creating the directory"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(path="alpha"))
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run_main()

        mock_reference.assert_called_once_with(name="alpha")
        mock_fsj.assert_called_once_with(
            destination_file_system=mock_reference.return_value,
            junction_origin_path="/alpha",
        )
        blade.post_file_system_junctions.assert_called_once_with(
            names=["projects-alpha"],
            origin_file_system_names=["projects"],
            file_system_junction=mock_fsj.return_value,
            use_existing_directory=False,
        )
        blade.delete_file_system_junctions.assert_not_called()
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True
        assert module.exit_json.call_args[1]["junction"]["status"] == "CONNECTED"
        assert module.exit_json.call_args[1]["junction"]["path"] == "/alpha"

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.Reference")
    @patch("plugins.modules.purefb_fs_junction.FileSystemJunction")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_creates_junction_on_existing_directory_with_context(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_fsj,
        mock_reference,
        mock_loose_version,
    ):
        """use_existing_directory and context are passed through to the POST"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(use_existing_directory=True, context="peer1"))
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run_main()

        blade.post_file_system_junctions.assert_called_once_with(
            names=["projects-alpha"],
            origin_file_system_names=["projects"],
            file_system_junction=mock_fsj.return_value,
            use_existing_directory=True,
            context_names=["peer1"],
        )
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_create_check_mode_skips_post(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Check mode reports changed with the requested values and no POST"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(path="alpha"), check_mode=True)
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run_main()

        blade.post_file_system_junctions.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True
        assert module.exit_json.call_args[1]["junction"] == {
            "name": "projects-alpha",
            "origin_fs": "projects",
            "destination_fs": "alpha",
            "path": "/alpha",
            "status": None,
        }

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.Reference")
    @patch("plugins.modules.purefb_fs_junction.FileSystemJunction")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_create_fails_on_api_error(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_fsj,
        mock_reference,
        mock_loose_version,
    ):
        """A failed POST is surfaced through fail_json"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params())
        mock_ansible_module.return_value = module
        blade = _blade()
        blade.post_file_system_junctions.return_value = Mock(status_code=400, errors=[])
        mock_get_system.return_value = blade

        _run_main()

        module.fail_json.assert_called_once()
        assert (
            "Failed to create file system junction projects-alpha"
            in module.fail_json.call_args[1]["msg"]
        )
        module.exit_json.assert_not_called()

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_idempotent_when_junction_matches(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """A matching junction (path given without a leading slash) is a no-op"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(path="alpha/"))
        mock_ansible_module.return_value = module
        blade = _blade(existing=_junction(path="/alpha"))
        mock_get_system.return_value = blade

        _run_main()

        blade.post_file_system_junctions.assert_not_called()
        blade.delete_file_system_junctions.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False
        assert module.exit_json.call_args[1]["junction"]["status"] == "CONNECTED"

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_drift_without_recreate_fails(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """A differing junction fails because junctions are immutable"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(path="/beta", destination_fs="beta"))
        mock_ansible_module.return_value = module
        blade = _blade(existing=_junction())
        mock_get_system.return_value = blade

        _run_main()

        blade.post_file_system_junctions.assert_not_called()
        blade.delete_file_system_junctions.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "cannot be modified" in msg
        assert "recreate=true" in msg
        assert "destination_fs alpha -> beta" in msg
        assert "path /alpha -> /beta" in msg

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.Reference")
    @patch("plugins.modules.purefb_fs_junction.FileSystemJunction")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_drift_with_recreate_deletes_then_creates(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_fsj,
        mock_reference,
        mock_loose_version,
    ):
        """recreate=true deletes the junction and creates it again"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(path="/beta", recreate=True))
        mock_ansible_module.return_value = module
        blade = _blade(existing=_junction())
        blade.post_file_system_junctions.return_value.items = [_junction(path="/beta")]
        mock_get_system.return_value = blade
        calls = []
        blade.delete_file_system_junctions.side_effect = lambda **kw: (
            calls.append("delete"),
            Mock(status_code=200),
        )[1]
        blade.post_file_system_junctions.side_effect = lambda **kw: (
            calls.append("post"),
            Mock(status_code=200, items=[_junction(path="/beta")]),
        )[1]

        _run_main()

        assert calls == ["delete", "post"]
        blade.delete_file_system_junctions.assert_called_once_with(
            names=["projects-alpha"]
        )
        mock_fsj.assert_called_once_with(
            destination_file_system=mock_reference.return_value,
            junction_origin_path="/beta",
        )
        # a new path means a new directory, so the requested flag is kept
        post_kwargs = blade.post_file_system_junctions.call_args[1]
        assert post_kwargs["use_existing_directory"] is False
        assert module.exit_json.call_args[1]["changed"] is True
        assert module.exit_json.call_args[1]["junction"]["path"] == "/beta"

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.Reference")
    @patch("plugins.modules.purefb_fs_junction.FileSystemJunction")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_recreate_on_same_directory_reuses_it(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_fsj,
        mock_reference,
        mock_loose_version,
    ):
        """A destination-only recreate POSTs with use_existing_directory=True

        The DELETE leaves the junction directory in the origin file system,
        so re-creating on the same origin and path must reuse it even though
        the caller left use_existing_directory at its default.
        """
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(destination_fs="beta", recreate=True))
        mock_ansible_module.return_value = module
        blade = _blade(existing=_junction())
        mock_get_system.return_value = blade
        calls = []
        blade.delete_file_system_junctions.side_effect = lambda **kw: (
            calls.append("delete"),
            Mock(status_code=200),
        )[1]
        blade.post_file_system_junctions.side_effect = lambda **kw: (
            calls.append("post"),
            Mock(status_code=200, items=[_junction(dest="beta")]),
        )[1]

        _run_main()

        assert calls == ["delete", "post"]
        mock_reference.assert_called_once_with(name="beta")
        blade.post_file_system_junctions.assert_called_once_with(
            names=["projects-alpha"],
            origin_file_system_names=["projects"],
            file_system_junction=mock_fsj.return_value,
            use_existing_directory=True,
        )
        assert module.exit_json.call_args[1]["changed"] is True
        assert module.exit_json.call_args[1]["junction"]["destination_fs"] == "beta"

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.Reference")
    @patch("plugins.modules.purefb_fs_junction.FileSystemJunction")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_recreate_post_failure_reports_deleted_junction(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_fsj,
        mock_reference,
        mock_loose_version,
    ):
        """A failed POST after the DELETE says the old junction is gone"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(path="/beta", recreate=True))
        mock_ansible_module.return_value = module
        blade = _blade(existing=_junction())
        blade.post_file_system_junctions.return_value = Mock(status_code=400, errors=[])
        mock_get_system.return_value = blade

        _run_main()

        blade.delete_file_system_junctions.assert_called_once()
        blade.post_file_system_junctions.assert_called_once()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert (
            "File system junction projects-alpha was deleted but re-creating it "
            "failed" in msg
        )
        module.exit_json.assert_not_called()
        # the name was the junction's own, so no other scope is searched
        assert blade.get_file_system_junctions.call_count == 1

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_idempotent_when_array_reports_bare_realm_names(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Realm-scoped request matches references reported without the prefix"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(
                name="realm1::projects-alpha",
                origin_fs="realm1::projects",
                destination_fs="realm1::alpha",
            )
        )
        mock_ansible_module.return_value = module
        blade = _blade(existing=_junction(name="realm1::projects-alpha"))
        mock_get_system.return_value = blade

        _run_main()

        blade.post_file_system_junctions.assert_not_called()
        blade.delete_file_system_junctions.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False
        assert module.exit_json.call_args[1]["junction"] == {
            "name": "realm1::projects-alpha",
            "origin_fs": "realm1::projects",
            "destination_fs": "realm1::alpha",
            "path": "/alpha",
            "status": "CONNECTED",
        }

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_drift_detected_with_bare_realm_names(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """A different destination is still drift when the array omits the prefix"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(
                name="realm1::projects-alpha",
                origin_fs="realm1::projects",
                destination_fs="realm1::beta",
            )
        )
        mock_ansible_module.return_value = module
        blade = _blade(existing=_junction(name="realm1::projects-alpha"))
        mock_get_system.return_value = blade

        _run_main()

        blade.post_file_system_junctions.assert_not_called()
        blade.delete_file_system_junctions.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "destination_fs realm1::alpha -> realm1::beta" in msg
        assert "origin_fs" not in msg

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_drift_with_recreate_check_mode(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """recreate in check mode reports changed without any write"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(origin_fs="archive", recreate=True), check_mode=True
        )
        mock_ansible_module.return_value = module
        blade = _blade(existing=_junction())
        mock_get_system.return_value = blade

        _run_main()

        blade.delete_file_system_junctions.assert_not_called()
        blade.post_file_system_junctions.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True
        assert module.exit_json.call_args[1]["junction"]["origin_fs"] == "archive"
        assert module.exit_json.call_args[1]["junction"]["status"] is None

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_recreate_delete_failure_is_surfaced(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """A failed DELETE during recreate stops before the POST"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(path="/beta", recreate=True))
        mock_ansible_module.return_value = module
        blade = _blade(existing=_junction())
        blade.delete_file_system_junctions.return_value = Mock(
            status_code=400, errors=[]
        )
        mock_get_system.return_value = blade

        _run_main()

        blade.post_file_system_junctions.assert_not_called()
        module.fail_json.assert_called_once()
        assert (
            "Failed to delete file system junction projects-alpha"
            in module.fail_json.call_args[1]["msg"]
        )

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_absent_deletes_junction(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """state=absent deletes an existing junction"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(state="absent", origin_fs=None, destination_fs=None, path=None)
        )
        mock_ansible_module.return_value = module
        blade = _blade(existing=_junction())
        mock_get_system.return_value = blade

        _run_main()

        blade.delete_file_system_junctions.assert_called_once_with(
            names=["projects-alpha"]
        )
        blade.post_file_system_junctions.assert_not_called()
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_absent_check_mode_skips_delete(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """state=absent in check mode reports changed without DELETE"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(state="absent"), check_mode=True)
        mock_ansible_module.return_value = module
        blade = _blade(existing=_junction())
        mock_get_system.return_value = blade

        _run_main()

        blade.delete_file_system_junctions.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_absent_idempotent_when_missing(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """state=absent on a missing junction is a no-op"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(state="absent"))
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run_main()

        blade.delete_file_system_junctions.assert_not_called()
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_absent_fails_on_api_error(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """A failed DELETE is surfaced verbatim through fail_json"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(state="absent"))
        mock_ansible_module.return_value = module
        blade = _blade(existing=_junction())
        blade.delete_file_system_junctions.return_value = Mock(
            status_code=400, errors=[]
        )
        mock_get_system.return_value = blade

        _run_main()

        module.fail_json.assert_called_once()
        assert (
            "Failed to delete file system junction projects-alpha"
            in module.fail_json.call_args[1]["msg"]
        )

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_version_gate(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """An array below REST 2.25 is refused before any junction call"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)
        module = _module(_base_params())
        mock_ansible_module.return_value = module
        blade = _blade()
        blade.get_versions.return_value.items = ["2.24"]
        mock_get_system.return_value = blade

        _run_main()

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "FlashBlade REST version not supported" in msg
        assert "2.25" in msg
        blade.get_file_system_junctions.assert_not_called()
        blade.post_file_system_junctions.assert_not_called()

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_realm_prefix_required_on_junction_name(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """A bare junction name on realm-scoped file systems fails clearly"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(origin_fs="realm1::projects", destination_fs="realm1::alpha")
        )
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run_main()

        blade.post_file_system_junctions.assert_not_called()
        module.fail_json.assert_called_once()
        assert "realm1::projects-alpha" in module.fail_json.call_args[1]["msg"]

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_realm_mismatch_between_file_systems(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Origin and destination in different realms fail before the POST"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(name="realm1::projects-alpha", origin_fs="realm1::projects")
        )
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run_main()

        blade.post_file_system_junctions.assert_not_called()
        module.fail_json.assert_called_once()
        assert "must be in the same realm" in module.fail_json.call_args[1]["msg"]

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.Reference")
    @patch("plugins.modules.purefb_fs_junction.FileSystemJunction")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_realm_scoped_create(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_fsj,
        mock_reference,
        mock_loose_version,
    ):
        """Consistently realm-scoped names pass validation and are created"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(
                name="realm1::projects-alpha",
                origin_fs="realm1::projects",
                destination_fs="realm1::alpha",
            )
        )
        mock_ansible_module.return_value = module
        blade = _blade()
        mock_get_system.return_value = blade

        _run_main()

        blade.post_file_system_junctions.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", False)
    def test_main_requires_sdk(self, mock_ansible_module, mock_get_system):
        """Missing py-pure-client fails before contacting the array"""
        module = _module(_base_params())
        mock_ansible_module.return_value = module

        _run_main()

        module.fail_json.assert_called_once()
        assert "py-pure-client" in module.fail_json.call_args[1]["msg"]
        mock_get_system.assert_not_called()

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_absent_fails_when_read_fails(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """A failed GET with state=absent fails instead of reporting ok"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(state="absent", context="nosucharray"))
        mock_ansible_module.return_value = module
        blade = _blade(get_status=400)
        mock_get_system.return_value = blade

        _run_main()

        blade.get_file_system_junctions.assert_called_once_with(
            names=["projects-alpha"], context_names=["nosucharray"]
        )
        blade.delete_file_system_junctions.assert_not_called()
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once()
        assert (
            "Failed to read file system junction projects-alpha"
            in module.fail_json.call_args[1]["msg"]
        )

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_present_fails_when_read_fails(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """A failed GET with state=present fails instead of creating"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params())
        mock_ansible_module.return_value = module
        blade = _blade(get_status=500)
        mock_get_system.return_value = blade

        _run_main()

        blade.post_file_system_junctions.assert_not_called()
        blade.delete_file_system_junctions.assert_not_called()
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once()
        assert (
            "Failed to read file system junction projects-alpha"
            in module.fail_json.call_args[1]["msg"]
        )

    # ---------------- realm-qualified file system names ----------------

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.Reference")
    @patch("plugins.modules.purefb_fs_junction.FileSystemJunction")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_realm_create_reports_the_same_names_as_check_mode(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_fsj,
        mock_reference,
        mock_loose_version,
    ):
        """A real run qualifies the bare references the array returns"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        params = _base_params(
            name="realm1::projects-alpha",
            origin_fs="realm1::projects",
            destination_fs="realm1::alpha",
        )
        blade = _blade()
        blade.post_file_system_junctions.return_value.items = [
            _junction(name="realm1::projects-alpha")
        ]
        mock_get_system.return_value = blade

        check = _module(dict(params), check_mode=True)
        mock_ansible_module.return_value = check
        _run_main()
        blade.post_file_system_junctions.assert_not_called()

        real = _module(dict(params))
        mock_ansible_module.return_value = real
        _run_main()

        blade.post_file_system_junctions.assert_called_once_with(
            names=["realm1::projects-alpha"],
            origin_file_system_names=["realm1::projects"],
            file_system_junction=mock_fsj.return_value,
            use_existing_directory=False,
        )
        mock_reference.assert_called_once_with(name="realm1::alpha")
        check_facts = check.exit_json.call_args[1]["junction"]
        real_facts = real.exit_json.call_args[1]["junction"]
        assert real_facts == {
            "name": "realm1::projects-alpha",
            "origin_fs": "realm1::projects",
            "destination_fs": "realm1::alpha",
            "path": "/alpha",
            "status": "CONNECTED",
        }
        assert dict(real_facts, status=None) == check_facts

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.Reference")
    @patch("plugins.modules.purefb_fs_junction.FileSystemJunction")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_realm_recreate_reports_qualified_names(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_fsj,
        mock_reference,
        mock_loose_version,
    ):
        """A destination-only recreate in a realm keeps the directory and
        reports the realm-qualified file systems"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(
                name="realm1::projects-alpha",
                origin_fs="realm1::projects",
                destination_fs="realm1::beta",
                recreate=True,
            )
        )
        mock_ansible_module.return_value = module
        blade = _blade(existing=_junction(name="realm1::projects-alpha"))
        blade.post_file_system_junctions.return_value.items = [
            _junction(name="realm1::projects-alpha", dest="beta")
        ]
        mock_get_system.return_value = blade

        _run_main()

        blade.delete_file_system_junctions.assert_called_once_with(
            names=["realm1::projects-alpha"]
        )
        post_kwargs = blade.post_file_system_junctions.call_args[1]
        assert post_kwargs["use_existing_directory"] is True
        assert module.exit_json.call_args[1]["changed"] is True
        facts = module.exit_json.call_args[1]["junction"]
        assert facts["origin_fs"] == "realm1::projects"
        assert facts["destination_fs"] == "realm1::beta"

    # ---------------- leaf name taken in another scope ----------------

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_create_check_mode_predicts_a_name_held_in_another_scope(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Check mode fails, naming the junction that holds the leaf name"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        cases = [
            # requested junction and file system realm, junction in the way
            ("projects-alpha", "", "realm1::projects-alpha"),
            ("realm1::projects-alpha", "realm1::", "projects-alpha"),
            ("realm2::projects-alpha", "realm2::", "realm1::projects-alpha"),
        ]
        for name, prefix, holder in cases:
            module = _module(
                _base_params(
                    name=name,
                    origin_fs=prefix + "projects",
                    destination_fs=prefix + "alpha",
                ),
                check_mode=True,
            )
            mock_ansible_module.return_value = module
            blade = _blade(holders=[_junction(name=holder)])
            mock_get_system.return_value = blade

            _run_main()

            blade.post_file_system_junctions.assert_not_called()
            module.exit_json.assert_not_called()
            module.fail_json.assert_called_once_with(
                msg=(
                    "File system junction {0} cannot be created because "
                    "junction {1} already uses the name projects-alpha. A "
                    "junction name must be unique across the array and all "
                    "of its realms."
                ).format(name, holder)
            )

        # a failed search, or one that only finds the requested name, does
        # not stand in the way of the create
        for blade in (_blade(holders_status=400), _blade(holders=[_junction()])):
            module = _module(_base_params(), check_mode=True)
            mock_ansible_module.return_value = module
            mock_get_system.return_value = blade

            _run_main()

            module.fail_json.assert_not_called()
            assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_fs_junction.get_error_message")
    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.Reference")
    @patch("plugins.modules.purefb_fs_junction.FileSystemJunction")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_create_explains_a_refused_name(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_fsj,
        mock_reference,
        mock_loose_version,
        mock_get_error_message,
    ):
        """A name the array refuses is explained; other refusals are relayed"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        plain = "Failed to create file system junction projects-alpha. Error: {0}"
        no_fs = "File system does not exist."
        cases = [
            # array error, junctions found by the search, its status,
            # number of lookups, expected message
            (
                NAME_REFUSED,
                [_junction(name="realm1::projects-alpha")],
                200,
                2,
                "File system junction projects-alpha cannot be created because "
                "junction realm1::projects-alpha already uses the name "
                "projects-alpha. A junction name must be unique across the "
                "array and all of its realms.",
            ),
            (
                NAME_REFUSED,
                [],
                200,
                2,
                plain.format(NAME_REFUSED)
                + ". No junction named projects-alpha is visible to this user, "
                "so the name is in use in another realm or at array level. A "
                "junction name must be unique across the array and all of its "
                "realms.",
            ),
            # the search failed, or the name was created meanwhile
            (NAME_REFUSED, [], 400, 2, plain.format(NAME_REFUSED)),
            (NAME_REFUSED, [_junction()], 200, 2, plain.format(NAME_REFUSED)),
            # another cause: no search, although the leaf name is also taken
            (
                no_fs,
                [_junction(name="realm1::projects-alpha")],
                200,
                1,
                plain.format(no_fs),
            ),
        ]
        for error, holders, holders_status, lookups, expected in cases:
            mock_get_error_message.return_value = error
            module = _module(_base_params())
            mock_ansible_module.return_value = module
            blade = _blade(holders=holders, holders_status=holders_status)
            blade.post_file_system_junctions.return_value = Mock(status_code=400)
            mock_get_system.return_value = blade

            _run_main()

            blade.post_file_system_junctions.assert_called_once()
            assert blade.get_file_system_junctions.call_count == lookups
            module.exit_json.assert_not_called()
            module.fail_json.assert_called_once_with(msg=expected)

    # ---------------- review repairs ----------------

    def test_same_fs_compares_inside_the_realm_of_the_junction(self):
        assert _same_fs("fs1", "fs1")
        assert _same_fs("realm1::fs1", "realm1::fs1")
        # the realm is the junction's, however the request spells its prefix
        assert _same_fs("realm1::fs1", "REALM1::fs1")
        assert not _same_fs("realm1::fs2", "realm1::fs1")
        assert not _same_fs("fs2", "fs1")
        assert not _same_fs(None, "fs1")
        assert not _same_fs("fs1", None)
        assert _same_fs(None, None)

    def test_name_holders_does_not_search_for_a_name_no_junction_can_have(self):
        """A wildcard or a quote never reaches the filter"""
        for name in ("proj*", "realm1::proj*", "it's", "two words", "realm1::"):
            module = Mock()
            module.params = _base_params(name=name)
            blade = _blade(holders=[_junction(name="projects-alpha")])

            assert _name_holders(module, blade) is None
            blade.get_file_system_junctions.assert_not_called()

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_unchanged_when_the_realm_prefix_is_spelled_in_another_case(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """A junction the array returns under the stored spelling of its realm
        is not drift, so recreate does not delete it"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(
                name="REALM1::projects-alpha",
                origin_fs="REALM1::projects",
                destination_fs="REALM1::alpha",
                recreate=True,
            )
        )
        mock_ansible_module.return_value = module
        blade = _blade(existing=_junction(name="realm1::projects-alpha"))
        mock_get_system.return_value = blade

        _run_main()

        blade.delete_file_system_junctions.assert_not_called()
        blade.post_file_system_junctions.assert_not_called()
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False
        assert module.exit_json.call_args[1]["junction"] == {
            "name": "realm1::projects-alpha",
            "origin_fs": "realm1::projects",
            "destination_fs": "realm1::alpha",
            "path": "/alpha",
            "status": "CONNECTED",
        }

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_drift_in_a_realm_spelled_in_another_case_is_still_drift(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Only the realm prefix is exempt from the comparison"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(
                name="REALM1::projects-alpha",
                origin_fs="REALM1::projects",
                destination_fs="REALM1::beta",
            )
        )
        mock_ansible_module.return_value = module
        blade = _blade(existing=_junction(name="realm1::projects-alpha"))
        mock_get_system.return_value = blade

        _run_main()

        blade.delete_file_system_junctions.assert_not_called()
        blade.post_file_system_junctions.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "destination_fs realm1::alpha -> REALM1::beta" in msg
        assert "origin_fs" not in msg

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.Reference")
    @patch("plugins.modules.purefb_fs_junction.FileSystemJunction")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_create_asks_the_array_before_any_search(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_fsj,
        mock_reference,
        mock_loose_version,
    ):
        """A real run never refuses a name itself: a create the array accepts
        succeeds without the search of the other scopes"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params())
        mock_ansible_module.return_value = module
        blade = _blade(holders=[_junction(name="realm1::projects-alpha")])
        mock_get_system.return_value = blade

        _run_main()

        blade.post_file_system_junctions.assert_called_once()
        blade.get_file_system_junctions.assert_called_once_with(
            names=["projects-alpha"]
        )
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_create_check_mode_cannot_see_a_holder_outside_the_realm(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """A user limited to a realm gets an empty search, so check mode
        reports the create although the array would refuse the name"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(
                name="realm1::projects-alpha",
                origin_fs="realm1::projects",
                destination_fs="realm1::alpha",
            ),
            check_mode=True,
        )
        mock_ansible_module.return_value = module
        blade = _blade(holders=[])
        mock_get_system.return_value = blade

        _run_main()

        blade.post_file_system_junctions.assert_not_called()
        module.fail_json.assert_not_called()
        assert blade.get_file_system_junctions.call_count == 2
        assert module.exit_json.call_args[1]["changed"] is True

    # ---------------- names compared as the array does ----------------

    def test_same_name_ignores_case(self):
        assert _same_name("realm1", "REALM1")
        assert _same_name("", "")
        assert not _same_name("realm1", "realm2")
        assert not _same_name("realm1", "")

    def test_same_fs_ignores_the_case_of_a_file_system_name(self):
        assert _same_fs("fs1", "FS1")
        assert _same_fs("realm1::fs1", "REALM1::Fs1")
        assert _same_fs("realm1::FS1", "realm1::fs1")
        assert not _same_fs("fs1", "FS2")
        assert not _same_fs("realm1::fs1", "realm1::FS2")

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_unchanged_when_a_file_system_is_spelled_in_another_case(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """The array resolves a file system name in any case to the same
        file system, so it is not drift: nothing fails without recreate and
        nothing is deleted and re-created with it, at array level and in a
        realm, in a real run and in check mode"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        cases = [
            # junction on the array, requested name, origin and destination
            (_junction(), "PROJECTS-ALPHA", "PROJECTS", "Alpha"),
            (
                _junction(name="realm1::projects-alpha"),
                "realm1::projects-alpha",
                "realm1::PROJECTS",
                "realm1::ALPHA",
            ),
            (
                _junction(name="realm1::projects-alpha"),
                "Realm1::Projects-Alpha",
                "REALM1::Projects",
                "realm1::alphA",
            ),
        ]
        for existing, name, origin, destination in cases:
            for recreate in (False, True):
                for check_mode in (False, True):
                    module = _module(
                        _base_params(
                            name=name,
                            origin_fs=origin,
                            destination_fs=destination,
                            recreate=recreate,
                        ),
                        check_mode=check_mode,
                    )
                    mock_ansible_module.return_value = module
                    blade = _blade(existing=existing)
                    mock_get_system.return_value = blade

                    _run_main()

                    blade.delete_file_system_junctions.assert_not_called()
                    blade.post_file_system_junctions.assert_not_called()
                    module.fail_json.assert_not_called()
                    result = module.exit_json.call_args[1]
                    assert result["changed"] is False
                    # the spelling the array stores is returned
                    prefix = "realm1::" if "::" in existing.name else ""
                    assert result["junction"] == {
                        "name": prefix + "projects-alpha",
                        "origin_fs": prefix + "projects",
                        "destination_fs": prefix + "alpha",
                        "path": "/alpha",
                        "status": "CONNECTED",
                    }

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.Reference")
    @patch("plugins.modules.purefb_fs_junction.FileSystemJunction")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_realm_prefixes_that_differ_only_in_case_are_one_realm(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_fsj,
        mock_reference,
        mock_loose_version,
    ):
        """The array accepts a realm prefix in any case, so the module does
        not refuse three names whose prefixes differ only in case; the names
        are sent as they were given"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(
                name="REALM1::projects-alpha",
                origin_fs="realm1::projects",
                destination_fs="Realm1::alpha",
            )
        )
        mock_ansible_module.return_value = module
        blade = _blade()
        blade.post_file_system_junctions.return_value.items = [
            _junction(name="realm1::projects-alpha")
        ]
        mock_get_system.return_value = blade

        _run_main()

        module.fail_json.assert_not_called()
        blade.post_file_system_junctions.assert_called_once()
        kwargs = blade.post_file_system_junctions.call_args[1]
        assert kwargs["names"] == ["REALM1::projects-alpha"]
        assert kwargs["origin_file_system_names"] == ["realm1::projects"]
        mock_reference.assert_called_once_with(name="Realm1::alpha")
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["junction"]["name"] == "realm1::projects-alpha"
        assert result["junction"]["origin_fs"] == "realm1::projects"
        assert result["junction"]["destination_fs"] == "realm1::alpha"

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_realms_that_differ_in_more_than_case_are_still_refused(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        cases = [
            ("REALM1::projects-alpha", "realm1::projects", "realm2::alpha"),
            ("REALM2::projects-alpha", "realm1::projects", "Realm1::alpha"),
            ("projects-alpha", "realm1::projects", "REALM1::alpha"),
            ("realm1::projects-alpha", "projects", "alpha"),
        ]
        for name, origin, destination in cases:
            module = _module(
                _base_params(name=name, origin_fs=origin, destination_fs=destination)
            )
            mock_ansible_module.return_value = module
            blade = _blade()
            mock_get_system.return_value = blade

            _run_main()

            blade.post_file_system_junctions.assert_not_called()
            module.exit_json.assert_not_called()
            module.fail_json.assert_called_once()

    @patch("plugins.modules.purefb_fs_junction.get_error_message")
    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.Reference")
    @patch("plugins.modules.purefb_fs_junction.FileSystemJunction")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_a_holder_spelled_in_another_case_is_named_as_it_is_stored(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_fsj,
        mock_reference,
        mock_loose_version,
        mock_get_error_message,
    ):
        """The search of the other scopes ignores case on the array, so the
        junction in the way may be spelled differently from the request; the
        message gives its stored name, in check mode and in a real run"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_get_error_message.return_value = NAME_REFUSED
        expected = (
            "File system junction PROJECTS-ALPHA cannot be created because "
            "junction realm1::projects-alpha already uses the name "
            "projects-alpha. A junction name must be unique across the array "
            "and all of its realms."
        )
        for check_mode in (True, False):
            module = _module(_base_params(name="PROJECTS-ALPHA"), check_mode=check_mode)
            mock_ansible_module.return_value = module
            blade = _blade(holders=[_junction(name="realm1::projects-alpha")])
            blade.post_file_system_junctions.return_value = Mock(status_code=400)
            mock_get_system.return_value = blade

            _run_main()

            module.exit_json.assert_not_called()
            module.fail_json.assert_called_once_with(msg=expected)

    @patch("plugins.modules.purefb_fs_junction.get_error_message")
    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.Reference")
    @patch("plugins.modules.purefb_fs_junction.FileSystemJunction")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_the_requested_name_in_another_case_is_not_another_scope(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_fsj,
        mock_reference,
        mock_loose_version,
        mock_get_error_message,
    ):
        """A search that only finds the requested name, however it is
        spelled, found no junction of another scope: check mode reports the
        create and a refused create is relayed in the array's words"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_get_error_message.return_value = NAME_REFUSED

        module = _module(_base_params(name="Projects-Alpha"), check_mode=True)
        mock_ansible_module.return_value = module
        mock_get_system.return_value = _blade(holders=[_junction()])

        _run_main()

        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

        module = _module(_base_params(name="Projects-Alpha"))
        mock_ansible_module.return_value = module
        blade = _blade(holders=[_junction()])
        blade.post_file_system_junctions.return_value = Mock(status_code=400)
        mock_get_system.return_value = blade

        _run_main()

        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once_with(
            msg="Failed to create file system junction Projects-Alpha. Error: "
            + NAME_REFUSED
        )

    # ---------------- the spelling the array stores ----------------

    def test_stored_realm_reads_the_origin_file_system(self):
        module = Mock()
        module.params = _base_params(origin_fs="REALM1::projects", context="member1")
        blade = Mock()
        stored = Mock(spec=["name"])
        stored.name = "realm1::projects"
        blade.get_file_systems.return_value = Mock(status_code=200, items=[stored])

        assert _stored_realm(module, blade) == "realm1"
        blade.get_file_systems.assert_called_once_with(
            names=["REALM1::projects"], context_names=["member1"]
        )

        blade.get_file_systems.return_value = Mock(status_code=200, items=[])
        assert _stored_realm(module, blade) is None
        blade.get_file_systems.return_value = Mock(status_code=400, items=[stored])
        assert _stored_realm(module, blade) is None

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.Reference")
    @patch("plugins.modules.purefb_fs_junction.FileSystemJunction")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_recreate_keeps_the_name_the_array_stores(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_fsj,
        mock_reference,
        mock_loose_version,
    ):
        """The array finds a junction under a name in any case but refuses
        a new junction whose realm prefix is not spelled as it stores the
        realm. A junction found under another spelling is therefore deleted
        and re-created under its stored name, never under the requested one,
        which would leave it deleted"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        params = dict(
            name="REALM1::Projects-Alpha",
            origin_fs="REALM1::projects",
            destination_fs="REALM1::beta",
            recreate=True,
        )

        module = _module(_base_params(**params), check_mode=True)
        mock_ansible_module.return_value = module
        blade = _blade(existing=_junction(name="realm1::projects-alpha"))
        mock_get_system.return_value = blade

        _run_main()

        blade.delete_file_system_junctions.assert_not_called()
        blade.post_file_system_junctions.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["junction"]["name"] == "realm1::projects-alpha"

        module = _module(_base_params(**params))
        mock_ansible_module.return_value = module
        blade = _blade(existing=_junction(name="realm1::projects-alpha"))
        blade.post_file_system_junctions.return_value.items = [
            _junction(name="realm1::projects-alpha", dest="beta")
        ]
        mock_get_system.return_value = blade

        _run_main()

        blade.delete_file_system_junctions.assert_called_once_with(
            names=["realm1::projects-alpha"]
        )
        blade.post_file_system_junctions.assert_called_once()
        kwargs = blade.post_file_system_junctions.call_args[1]
        assert kwargs["names"] == ["realm1::projects-alpha"]
        assert kwargs["origin_file_system_names"] == ["REALM1::projects"]
        # same origin and path: the directory left behind is reused
        assert kwargs["use_existing_directory"] is True
        module.fail_json.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["junction"]["name"] == "realm1::projects-alpha"
        assert result["junction"]["destination_fs"] == "realm1::beta"

    @patch("plugins.modules.purefb_fs_junction.get_error_message")
    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.Reference")
    @patch("plugins.modules.purefb_fs_junction.FileSystemJunction")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_recreate_failure_names_the_stored_junction(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_fsj,
        mock_reference,
        mock_loose_version,
        mock_get_error_message,
    ):
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        mock_get_error_message.return_value = "File system does not exist."
        module = _module(
            _base_params(name="PROJECTS-ALPHA", destination_fs="beta", recreate=True)
        )
        mock_ansible_module.return_value = module
        blade = _blade(existing=_junction())
        blade.post_file_system_junctions.return_value = Mock(status_code=400)
        mock_get_system.return_value = blade

        _run_main()

        blade.delete_file_system_junctions.assert_called_once_with(
            names=["projects-alpha"]
        )
        module.fail_json.assert_called_once_with(
            msg="File system junction projects-alpha was deleted but re-creating "
            "it failed. Error: File system does not exist."
        )

    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_absent_deletes_under_the_name_the_array_stores(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(name="REALM1::PROJECTS-ALPHA", state="absent"))
        mock_ansible_module.return_value = module
        blade = _blade(existing=_junction(name="realm1::projects-alpha"))
        mock_get_system.return_value = blade

        _run_main()

        blade.delete_file_system_junctions.assert_called_once_with(
            names=["realm1::projects-alpha"]
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch("plugins.modules.purefb_fs_junction.get_error_message")
    @patch("plugins.modules.purefb_fs_junction.LooseVersion")
    @patch("plugins.modules.purefb_fs_junction.Reference")
    @patch("plugins.modules.purefb_fs_junction.FileSystemJunction")
    @patch("plugins.modules.purefb_fs_junction.get_system")
    @patch("plugins.modules.purefb_fs_junction.AnsibleModule")
    @patch("plugins.modules.purefb_fs_junction.HAS_PYPURECLIENT", True)
    def test_main_create_explains_a_realm_prefix_the_array_stores_otherwise(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_fsj,
        mock_reference,
        mock_loose_version,
        mock_get_error_message,
    ):
        """The array refuses a new junction whose realm prefix is not in the
        spelling it stores, in words about the file systems. The module
        names the stored spelling when it differs from the request in case
        only, and relays the array's words in every other case"""
        mock_loose_version.return_value.__gt__ = Mock(return_value=False)
        plain = "Failed to create file system junction {0}. Error: {1}"
        upper = dict(
            name="REALM1::projects-alpha",
            origin_fs="REALM1::projects",
            destination_fs="REALM1::alpha",
        )
        stored = dict(
            name="realm1::projects-alpha",
            origin_fs="realm1::projects",
            destination_fs="realm1::alpha",
        )
        cases = [
            # request, array error, stored origin name, status of its read,
            # reads of the file system, expected message
            (
                upper,
                REALM_REFUSED,
                "realm1::projects",
                200,
                1,
                plain.format(upper["name"], REALM_REFUSED)
                + ". The array stores the realm as realm1 and accepts only that "
                "spelling in the name of a new junction: use "
                "realm1::projects-alpha.",
            ),
            # the prefix is spelled as stored: the array's words stand
            (
                stored,
                REALM_REFUSED,
                "realm1::projects",
                200,
                1,
                plain.format(stored["name"], REALM_REFUSED),
            ),
            # the file system cannot be read or is not found
            (
                upper,
                REALM_REFUSED,
                "realm1::projects",
                400,
                1,
                plain.format(upper["name"], REALM_REFUSED),
            ),
            (
                upper,
                REALM_REFUSED,
                None,
                200,
                1,
                plain.format(upper["name"], REALM_REFUSED),
            ),
            # another cause: the file system is not read
            (
                upper,
                "File system does not exist.",
                "realm1::projects",
                200,
                0,
                plain.format(upper["name"], "File system does not exist."),
            ),
            # array level: no realm prefix to explain
            (
                {},
                REALM_REFUSED,
                "projects",
                200,
                0,
                plain.format("projects-alpha", REALM_REFUSED),
            ),
        ]
        for params, error, stored_name, status, reads, expected in cases:
            mock_get_error_message.return_value = error
            module = _module(_base_params(**params))
            mock_ansible_module.return_value = module
            blade = _blade()
            blade.post_file_system_junctions.return_value = Mock(status_code=400)
            origin = Mock(spec=["name"])
            origin.name = stored_name
            blade.get_file_systems.return_value = Mock(
                status_code=status, items=[origin] if stored_name else []
            )
            mock_get_system.return_value = blade

            _run_main()

            blade.post_file_system_junctions.assert_called_once()
            assert blade.get_file_systems.call_count == reads
            # the search of the other scopes is for a taken name only
            assert blade.get_file_system_junctions.call_count == 1
            module.exit_json.assert_not_called()
            module.fail_json.assert_called_once_with(msg=expected)
