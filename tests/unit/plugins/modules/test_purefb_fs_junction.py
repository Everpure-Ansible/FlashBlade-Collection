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
    _same_fs,
    _get_junction,
    _junction_facts,
)


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


def _blade(existing=None, get_status=200):
    blade = Mock()
    blade.get_versions.return_value.items = ["2.25", "2.30"]
    get_response = Mock()
    get_response.status_code = get_status
    get_response.items = [existing] if existing else []
    blade.get_file_system_junctions.return_value = get_response
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

    def test_same_fs_accepts_bare_or_prefixed_realm_names(self):
        assert _same_fs("fs1", "fs1")
        assert _same_fs("realm1::fs1", "realm1::fs1")
        assert _same_fs("fs1", "realm1::fs1")
        assert _same_fs("realm1::fs1", "fs1")
        assert not _same_fs("fs2", "fs1")
        assert not _same_fs("fs2", "realm1::fs1")
        assert not _same_fs(None, "fs1")
        assert not _same_fs("fs1", None)

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

    def test_get_junction_returns_none_on_error(self):
        module = Mock()
        module.params = _base_params()
        assert _get_junction(module, _blade(get_status=400)) is None

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
        assert "destination_fs alpha -> realm1::beta" in msg
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
