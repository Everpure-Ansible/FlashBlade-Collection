# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_legal_hold module."""

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

from plugins.modules.purefb_legal_hold import (
    main,
    _get_hold,
    _get_held_entities,
    _get_entity,
    _norm_path,
    _hold_dict,
    _entity_dict,
)


def _base_params(**overrides):
    params = {
        "name": "case-42",
        "state": "present",
        "description": None,
        "file_system": None,
        "path": None,
        "recursive": False,
        "release": False,
    }
    params.update(overrides)
    return params


def _response(status_code=200, items=None):
    response = Mock()
    response.status_code = status_code
    response.items = items if items is not None else []
    response.errors = []
    return response


def _hold(name="case-42", description="", realms=None):
    hold = Mock(spec=["name", "description", "realms"])
    hold.name = name
    hold.description = description
    hold.realms = realms or []
    return hold


def _entity(file_system="evidence", path="/case-42", status="applied"):
    fs_ref = Mock(spec=["name"])
    fs_ref.name = file_system
    hold_ref = Mock(spec=["name"])
    hold_ref.name = "case-42"
    entity = Mock(spec=["file_system", "legal_hold", "path", "status"])
    entity.file_system = fs_ref
    entity.legal_hold = hold_ref
    entity.path = path
    entity.status = status
    return entity


def _module(params, check_mode=False):
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.params = params
    module.check_mode = check_mode
    return module


def _blade(hold=None, entities=None):
    blade = Mock()
    blade.get_versions.return_value.items = ["2.17", "2.30"]
    blade.get_file_systems.return_value = _response(200, [Mock()])
    blade.get_legal_holds.return_value = _response(
        200 if hold is not None else 400, [hold] if hold is not None else []
    )
    blade.get_legal_holds_held_entities.return_value = _response(200, entities or [])
    blade.post_legal_holds.return_value = _response(200)
    blade.patch_legal_holds.return_value = _response(200)
    blade.delete_legal_holds.return_value = _response(200)
    blade.post_legal_holds_held_entities.return_value = _response(200)
    blade.patch_legal_holds_held_entities.return_value = _response(200)
    return blade


def _run():
    try:
        main()
    except SystemExit:
        pass


class TestPurefbLegalHoldHelpers:
    """Helper-function unit tests."""

    def test_norm_path(self):
        assert _norm_path("/") == "/"
        assert _norm_path("//") == "/"
        assert _norm_path("/a/b/") == "/a/b"
        assert _norm_path("/a/b") == "/a/b"
        assert _norm_path(None) is None

    def test_get_hold_returns_first_item(self):
        module = Mock()
        module.params = _base_params()
        hold = _hold()
        blade = Mock()
        blade.get_legal_holds.return_value = _response(200, [hold])

        assert _get_hold(module, blade) is hold
        blade.get_legal_holds.assert_called_once_with(names=["case-42"])

    def test_get_hold_returns_none_when_missing(self):
        module = Mock()
        module.params = _base_params()
        blade = Mock()
        blade.get_legal_holds.return_value = _response(400)

        assert _get_hold(module, blade) is None

    def test_get_hold_returns_none_when_empty(self):
        module = Mock()
        module.params = _base_params()
        blade = Mock()
        blade.get_legal_holds.return_value = _response(200, [])

        assert _get_hold(module, blade) is None

    def test_get_hold_fails_on_api_error(self):
        module = Mock()
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params()
        blade = Mock()
        blade.get_legal_holds.return_value = _response(500)

        try:
            _get_hold(module, blade)
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        assert "Failed to read legal hold" in module.fail_json.call_args[1]["msg"]

    def test_get_held_entities_filters_by_file_system_and_path(self):
        module = Mock()
        module.params = _base_params()
        entity = _entity()
        blade = Mock()
        blade.get_legal_holds_held_entities.return_value = _response(200, [entity])

        assert _get_held_entities(module, blade, "evidence", "/case-42") == [entity]
        blade.get_legal_holds_held_entities.assert_called_once_with(
            names=["case-42"], file_system_names=["evidence"], paths=["/case-42"]
        )

    def test_get_held_entities_unfiltered(self):
        module = Mock()
        module.params = _base_params()
        blade = Mock()
        blade.get_legal_holds_held_entities.return_value = _response(200, [])

        assert _get_held_entities(module, blade) == []
        blade.get_legal_holds_held_entities.assert_called_once_with(names=["case-42"])

    def test_get_held_entities_fails_on_api_error(self):
        module = Mock()
        module.fail_json = Mock(side_effect=SystemExit)
        module.params = _base_params()
        blade = Mock()
        blade.get_legal_holds_held_entities.return_value = _response(400)

        try:
            _get_held_entities(module, blade, "ghost", "/")
        except SystemExit:
            pass

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to read held entities for legal hold case-42 at ghost:/" in msg

    def test_get_entity_matches_exact_path_only(self):
        module = Mock()
        module.params = _base_params(file_system="evidence", path="/case-42/")
        wanted = _entity(path="/case-42")
        other = _entity(path="/case-42/sub")
        blade = Mock()
        blade.get_legal_holds_held_entities.return_value = _response(
            200, [other, wanted]
        )

        assert _get_entity(module, blade) is wanted

    def test_get_entity_returns_none_when_not_held(self):
        module = Mock()
        module.params = _base_params(file_system="evidence", path="/case-42")
        blade = Mock()
        blade.get_legal_holds_held_entities.return_value = _response(200, [])

        assert _get_entity(module, blade) is None

    def test_hold_and_entity_dicts(self):
        realm = Mock(spec=["name"])
        realm.name = "legal"
        hold = _hold(description="desc", realms=[realm])
        assert _hold_dict(hold) == {
            "name": "case-42",
            "description": "desc",
            "realms": ["legal"],
        }
        assert _entity_dict(_entity(status="applying")) == {
            "file_system": "evidence",
            "path": "/case-42",
            "status": "applying",
        }


class TestPurefbLegalHoldMain:
    """main() flows."""

    # ---------------- hold object: create / update / delete ----------------

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.LegalHold")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_create_hold_with_description(
        self, mock_ansible_module, mock_get_system, mock_legal_hold, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(description="Litigation hold"))
        mock_ansible_module.return_value = module
        blade = _blade(hold=None)
        mock_get_system.return_value = blade

        _run()

        mock_legal_hold.assert_called_once_with(description="Litigation hold")
        blade.post_legal_holds.assert_called_once_with(
            names=["case-42"], hold=mock_legal_hold.return_value
        )
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        # the hold does not exist on the (mocked) array after the POST
        assert "legal_hold" not in result

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.LegalHold")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_create_hold_without_description(
        self, mock_ansible_module, mock_get_system, mock_legal_hold, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params())
        mock_ansible_module.return_value = module
        blade = _blade(hold=None)
        mock_get_system.return_value = blade

        _run()

        mock_legal_hold.assert_called_once_with()
        blade.post_legal_holds.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_create_hold_check_mode(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(description="x"), check_mode=True)
        mock_ansible_module.return_value = module
        blade = _blade(hold=None)
        mock_get_system.return_value = blade

        _run()

        blade.post_legal_holds.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_create_hold_api_error(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params())
        mock_ansible_module.return_value = module
        blade = _blade(hold=None)
        blade.post_legal_holds.return_value = _response(400)
        mock_get_system.return_value = blade

        _run()

        module.fail_json.assert_called_once()
        assert "Failed to create legal hold" in module.fail_json.call_args[1]["msg"]
        module.exit_json.assert_not_called()

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.LegalHold")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_update_description(
        self, mock_ansible_module, mock_get_system, mock_legal_hold, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(description="new text"))
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold(description="old text"))
        mock_get_system.return_value = blade

        _run()

        mock_legal_hold.assert_called_once_with(description="new text")
        blade.patch_legal_holds.assert_called_once_with(
            names=["case-42"], hold=mock_legal_hold.return_value
        )
        blade.post_legal_holds.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["legal_hold"]["name"] == "case-42"
        assert result["held_entities"] == []

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_update_description_idempotent(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(description="same"))
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold(description="same"))
        mock_get_system.return_value = blade

        _run()

        blade.patch_legal_holds.assert_not_called()
        blade.post_legal_holds.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is False
        assert result["legal_hold"]["description"] == "same"

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_update_without_description_is_noop(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params())
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold(description="keep me"))
        mock_get_system.return_value = blade

        _run()

        blade.patch_legal_holds.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_update_description_check_mode(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(description="new"), check_mode=True)
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold(description="old"))
        mock_get_system.return_value = blade

        _run()

        blade.patch_legal_holds.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_update_description_api_error(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(description="new"))
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold(description="old"))
        blade.patch_legal_holds.return_value = _response(400)
        mock_get_system.return_value = blade

        _run()

        module.fail_json.assert_called_once()
        assert "Failed to update legal hold" in module.fail_json.call_args[1]["msg"]

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_delete_hold(self, mock_ansible_module, mock_get_system, mock_loose):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(state="absent"))
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold())
        mock_get_system.return_value = blade

        _run()

        blade.get_legal_holds_held_entities.assert_called_once_with(names=["case-42"])
        blade.delete_legal_holds.assert_called_once_with(names=["case-42"])
        assert module.exit_json.call_args[1] == {"changed": True}

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_delete_hold_refused_while_held(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(state="absent"))
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold(), entities=[_entity(path="/case-42")])
        mock_get_system.return_value = blade

        _run()

        blade.delete_legal_holds.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "evidence:/case-42" in msg
        assert "Release" in msg

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_delete_hold_check_mode(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(state="absent"), check_mode=True)
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold())
        mock_get_system.return_value = blade

        _run()

        blade.delete_legal_holds.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_delete_missing_hold_is_noop(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(state="absent"))
        mock_ansible_module.return_value = module
        blade = _blade(hold=None)
        mock_get_system.return_value = blade

        _run()

        blade.delete_legal_holds.assert_not_called()
        blade.get_legal_holds_held_entities.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_delete_hold_api_error(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(state="absent"))
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold())
        blade.delete_legal_holds.return_value = _response(400)
        mock_get_system.return_value = blade

        _run()

        module.fail_json.assert_called_once()
        assert "Failed to delete legal hold" in module.fail_json.call_args[1]["msg"]

    # ---------------- held entities: apply ----------------

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_apply_entity_to_existing_hold(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(file_system="evidence", path="/case-42", recursive=True)
        )
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold())
        mock_get_system.return_value = blade

        _run()

        blade.post_legal_holds.assert_not_called()
        blade.get_file_systems.assert_called_once_with(names=["evidence"])
        blade.post_legal_holds_held_entities.assert_called_once_with(
            names=["case-42"],
            file_system_names=["evidence"],
            paths=["/case-42"],
            recursive=True,
        )
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.LegalHold")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_apply_entity_creates_missing_hold_first(
        self, mock_ansible_module, mock_get_system, mock_legal_hold, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(
                description="auto", file_system="evidence", path="/case-42/a.pdf"
            )
        )
        mock_ansible_module.return_value = module
        blade = _blade(hold=None)
        mock_get_system.return_value = blade

        _run()

        blade.get_file_systems.assert_called_once_with(names=["evidence"])
        mock_legal_hold.assert_called_once_with(description="auto")
        blade.post_legal_holds.assert_called_once()
        # no pre-check GET against a hold that does not exist yet
        blade.get_legal_holds_held_entities.assert_not_called()
        blade.post_legal_holds_held_entities.assert_called_once_with(
            names=["case-42"],
            file_system_names=["evidence"],
            paths=["/case-42/a.pdf"],
            recursive=False,
        )
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_apply_entity_idempotent_when_applied(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(file_system="evidence", path="/case-42"))
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold(), entities=[_entity(status="applied")])
        mock_get_system.return_value = blade

        _run()

        blade.post_legal_holds_held_entities.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is False
        assert result["held_entities"] == [
            {"file_system": "evidence", "path": "/case-42", "status": "applied"}
        ]

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_apply_entity_idempotent_while_applying(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(file_system="evidence", path="/case-42"))
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold(), entities=[_entity(status="applying")])
        mock_get_system.return_value = blade

        _run()

        blade.post_legal_holds_held_entities.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_apply_entity_reapplies_while_releasing(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(file_system="evidence", path="/case-42"))
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold(), entities=[_entity(status="releasing")])
        mock_get_system.return_value = blade

        _run()

        blade.post_legal_holds_held_entities.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_apply_entity_check_mode(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(file_system="evidence", path="/case-42"), check_mode=True
        )
        mock_ansible_module.return_value = module
        blade = _blade(hold=None)
        mock_get_system.return_value = blade

        _run()

        blade.get_file_systems.assert_called_once_with(names=["evidence"])
        blade.post_legal_holds.assert_not_called()
        blade.post_legal_holds_held_entities.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_apply_entity_api_error(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(file_system="evidence", path="/case-42"))
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold())
        blade.post_legal_holds_held_entities.return_value = _response(400)
        mock_get_system.return_value = blade

        _run()

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to apply legal hold case-42 to evidence:/case-42" in msg

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_apply_entity_fails_when_entity_query_rejected(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(file_system="ghost", path="/"))
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold())
        blade.get_legal_holds_held_entities.return_value = _response(400)
        mock_get_system.return_value = blade

        _run()

        blade.get_file_systems.assert_called_once_with(names=["ghost"])
        blade.post_legal_holds_held_entities.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to read held entities for legal hold case-42 at ghost:/" in msg

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_apply_entity_missing_file_system_does_not_create_hold(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(file_system="ghost", path="/"))
        mock_ansible_module.return_value = module
        blade = _blade(hold=None)
        blade.get_file_systems.return_value = _response(400)
        mock_get_system.return_value = blade

        _run()

        blade.get_file_systems.assert_called_once_with(names=["ghost"])
        blade.post_legal_holds.assert_not_called()
        blade.post_legal_holds_held_entities.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to read file system ghost for legal hold case-42" in msg

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_apply_entity_existing_hold_missing_file_system(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(file_system="ghost", path="/"))
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold())
        blade.get_file_systems.return_value = _response(400)
        mock_get_system.return_value = blade

        _run()

        blade.get_file_systems.assert_called_once_with(names=["ghost"])
        # the file system is validated before any held-entity read or write
        blade.get_legal_holds_held_entities.assert_not_called()
        blade.patch_legal_holds.assert_not_called()
        blade.post_legal_holds_held_entities.assert_not_called()
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to read file system ghost for legal hold case-42" in msg
        assert "held entities" not in msg

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_apply_entity_existing_hold_missing_file_system_check_mode(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(file_system="ghost", path="/"), check_mode=True)
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold())
        blade.get_file_systems.return_value = _response(400)
        mock_get_system.return_value = blade

        _run()

        blade.get_file_systems.assert_called_once_with(names=["ghost"])
        blade.get_legal_holds_held_entities.assert_not_called()
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to read file system ghost for legal hold case-42" in msg

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_apply_entity_normalises_trailing_slash(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(file_system="evidence", path="/case-42/", recursive=True)
        )
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold())
        mock_get_system.return_value = blade

        _run()

        blade.get_legal_holds_held_entities.assert_any_call(
            names=["case-42"], file_system_names=["evidence"], paths=["/case-42"]
        )
        blade.post_legal_holds_held_entities.assert_called_once_with(
            names=["case-42"],
            file_system_names=["evidence"],
            paths=["/case-42"],
            recursive=True,
        )
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_apply_entity_idempotent_with_trailing_slash(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(file_system="evidence", path="/case-42/"))
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold(), entities=[_entity(status="applied")])
        mock_get_system.return_value = blade

        _run()

        blade.post_legal_holds_held_entities.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    # ---------------- held entities: release ----------------

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_release_entity_normalises_trailing_slash(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(file_system="evidence", path="/case-42/", release=True)
        )
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold(), entities=[_entity(status="applied")])
        mock_get_system.return_value = blade

        _run()

        blade.patch_legal_holds_held_entities.assert_called_once_with(
            names=["case-42"],
            file_system_names=["evidence"],
            paths=["/case-42"],
            released=True,
            recursive=False,
        )
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_release_entity(self, mock_ansible_module, mock_get_system, mock_loose):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(
                file_system="evidence", path="/case-42", recursive=True, release=True
            )
        )
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold(), entities=[_entity(status="applied")])
        mock_get_system.return_value = blade

        _run()

        blade.patch_legal_holds_held_entities.assert_called_once_with(
            names=["case-42"],
            file_system_names=["evidence"],
            paths=["/case-42"],
            released=True,
            recursive=True,
        )
        blade.post_legal_holds_held_entities.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_state_absent_with_path_releases(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(state="absent", file_system="evidence", path="/case-42")
        )
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold(), entities=[_entity(status="applied")])
        mock_get_system.return_value = blade

        _run()

        blade.patch_legal_holds_held_entities.assert_called_once()
        blade.delete_legal_holds.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_release_entity_idempotent_when_not_held(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(file_system="evidence", path="/case-42", release=True)
        )
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold(), entities=[])
        mock_get_system.return_value = blade

        _run()

        blade.patch_legal_holds_held_entities.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_release_entity_idempotent_while_releasing(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(file_system="evidence", path="/case-42", release=True)
        )
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold(), entities=[_entity(status="releasing")])
        mock_get_system.return_value = blade

        _run()

        blade.patch_legal_holds_held_entities.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_release_entity_missing_hold_is_noop(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(file_system="evidence", path="/case-42", release=True)
        )
        mock_ansible_module.return_value = module
        blade = _blade(hold=None)
        mock_get_system.return_value = blade

        _run()

        blade.get_legal_holds_held_entities.assert_not_called()
        blade.patch_legal_holds_held_entities.assert_not_called()
        assert module.exit_json.call_args[1] == {"changed": False}

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_release_entity_missing_file_system(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(file_system="ghost", path="/", release=True))
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold())
        blade.get_file_systems.return_value = _response(400)
        mock_get_system.return_value = blade

        _run()

        blade.get_file_systems.assert_called_once_with(names=["ghost"])
        blade.get_legal_holds_held_entities.assert_not_called()
        blade.patch_legal_holds_held_entities.assert_not_called()
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to read file system ghost for legal hold case-42" in msg
        assert "held entities" not in msg

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_release_entity_missing_file_system_without_hold(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(file_system="ghost", path="/", state="absent"))
        mock_ansible_module.return_value = module
        blade = _blade(hold=None)
        blade.get_file_systems.return_value = _response(400)
        mock_get_system.return_value = blade

        _run()

        # the file system is validated even when there is no hold to release
        blade.get_file_systems.assert_called_once_with(names=["ghost"])
        module.exit_json.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to read file system ghost for legal hold case-42" in msg

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_release_entity_check_mode(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(file_system="evidence", path="/case-42", release=True),
            check_mode=True,
        )
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold(), entities=[_entity(status="applied")])
        mock_get_system.return_value = blade

        _run()

        blade.patch_legal_holds_held_entities.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_release_entity_api_error(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(
            _base_params(file_system="evidence", path="/case-42", release=True)
        )
        mock_ansible_module.return_value = module
        blade = _blade(hold=_hold(), entities=[_entity(status="applied")])
        blade.patch_legal_holds_held_entities.return_value = _response(400)
        mock_get_system.return_value = blade

        _run()

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to release legal hold case-42 from evidence:/case-42" in msg

    # ---------------- validation and gates ----------------

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_fails_on_unsupported_api_version(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=True)
        module = _module(_base_params())
        mock_ansible_module.return_value = module
        blade = _blade(hold=None)
        blade.get_versions.return_value.items = ["2.15", "2.16"]
        mock_get_system.return_value = blade

        _run()

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "REST version not supported" in msg
        assert "2.17" in msg
        blade.get_legal_holds.assert_not_called()
        blade.post_legal_holds.assert_not_called()

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", False)
    def test_fails_without_sdk(self, mock_ansible_module, mock_get_system, mock_loose):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params())
        mock_ansible_module.return_value = module

        _run()

        module.fail_json.assert_called_once()
        assert "py-pure-client" in module.fail_json.call_args[1]["msg"]
        mock_get_system.assert_not_called()

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_name_too_long(self, mock_ansible_module, mock_get_system, mock_loose):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(name="h" * 65))
        mock_ansible_module.return_value = module

        _run()

        module.fail_json.assert_called_once()
        assert "64 characters" in module.fail_json.call_args[1]["msg"]
        mock_get_system.assert_not_called()

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_description_too_long(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(description="d" * 129))
        mock_ansible_module.return_value = module

        _run()

        module.fail_json.assert_called_once()
        assert "128 characters" in module.fail_json.call_args[1]["msg"]
        mock_get_system.assert_not_called()

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_release_requires_path(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(release=True))
        mock_ansible_module.return_value = module

        _run()

        module.fail_json.assert_called_once()
        assert "release=true requires" in module.fail_json.call_args[1]["msg"]
        mock_get_system.assert_not_called()

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_relative_path_rejected(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params(file_system="evidence", path="case-42"))
        mock_ansible_module.return_value = module

        _run()

        module.fail_json.assert_called_once()
        assert "absolute" in module.fail_json.call_args[1]["msg"]
        mock_get_system.assert_not_called()

    @patch("plugins.modules.purefb_legal_hold.LooseVersion")
    @patch("plugins.modules.purefb_legal_hold.get_system")
    @patch("plugins.modules.purefb_legal_hold.AnsibleModule")
    @patch("plugins.modules.purefb_legal_hold.HAS_PYPURECLIENT", True)
    def test_argument_spec_constraints(
        self, mock_ansible_module, mock_get_system, mock_loose
    ):
        mock_loose.return_value.__gt__ = Mock(return_value=False)
        module = _module(_base_params())
        mock_ansible_module.return_value = module
        mock_get_system.return_value = _blade(hold=_hold())

        _run()

        kwargs = mock_ansible_module.call_args[1]
        assert kwargs["supports_check_mode"] is True
        assert kwargs["required_together"] == [["file_system", "path"]]
