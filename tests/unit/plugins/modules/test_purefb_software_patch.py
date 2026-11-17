# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_software_patch module."""

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

from plugins.modules.purefb_software_patch import (
    main,
    _get_patch,
    _patch_to_dict,
    RETRY_GRACE_POLLS,
)

MODULE = "plugins.modules.purefb_software_patch"


def _fake_poll(fetch, finished, timeout, interval=None):
    """Stand-in for module_utils.common.poll_until: polls without sleeping.

    Gives up after a handful of fetches so a never-finishing patch exercises
    the timeout path.
    """
    result = fetch()
    attempts = 0
    while not finished(result) and attempts < 4:
        result = fetch()
        attempts += 1
    return result, not finished(result)


def _base_params(**overrides):
    params = {
        "name": "patch_1042",
        "state": "present",
        "allow_ha_reduction": False,
        "local": False,
        "retry": False,
        "wait": True,
        "timeout": 1800,
    }
    params.update(overrides)
    return params


def _response(items=None, status_code=200, message="boom"):
    response = Mock()
    response.status_code = status_code
    response.items = items if items is not None else []
    error = Mock()
    error.message = message
    response.errors = [error]
    return response


def _patch(status="available", name="patch_1042", ha_reduction=False, details=None):
    item = Mock()
    item.id = "p-{0}".format(name)
    item.name = name
    item.status = status
    item.progress = 1.0 if status == "installed" else 0.0
    item.description = "Fixes alert 1042"
    item.details = details
    item.alert_code = 1042
    item.ha_reduction_required = ha_reduction
    return item


def _setup(
    mock_ansible_module, mock_get_system, mock_loose_version, params, check_mode=False
):
    mock_loose_version.return_value.__gt__ = Mock(return_value=False)
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.params = params
    module.check_mode = check_mode
    mock_ansible_module.return_value = module
    blade = Mock()
    blade.get_versions.return_value.items = ["2.24", "2.29", "2.30"]
    mock_get_system.return_value = blade
    return module, blade


def _run():
    try:
        main()
    except SystemExit:
        pass


class TestHelpers:
    """Helper-function unit tests."""

    def test_patch_to_dict_handles_none(self):
        assert _patch_to_dict(None) == {}

    def test_patch_to_dict_reports_every_field(self):
        result = _patch_to_dict(_patch(status="installed", ha_reduction=True))
        assert result == {
            "id": "p-patch_1042",
            "name": "patch_1042",
            "status": "installed",
            "progress": 1.0,
            "description": "Fixes alert 1042",
            "details": None,
            "alert_code": 1042,
            "ha_reduction_required": True,
        }

    def test_get_patch_lists_all_and_matches_by_name(self):
        module = Mock()
        module.params = {"name": "patch_1042"}
        wanted = _patch()
        blade = Mock()
        blade.get_software_patches.return_value = _response(
            [_patch(name="patch_1000"), wanted, _patch(name="patch_2000")]
        )

        assert _get_patch(module, blade) is wanted
        # never names=: the array answers an unknown name with an error
        blade.get_software_patches.assert_called_once_with()

    def test_get_patch_returns_none_for_unknown_name(self):
        module = Mock()
        module.params = {"name": "patch_1042"}
        blade = Mock()
        blade.get_software_patches.return_value = _response([_patch(name="other")])

        assert _get_patch(module, blade) is None

    def test_get_patch_fails_on_api_error(self):
        module = Mock()
        module.params = {"name": "patch_1042"}
        module.fail_json = Mock(side_effect=SystemExit)
        blade = Mock()
        blade.get_software_patches.return_value = _response(
            status_code=500, message="internal"
        )

        # module_utils.common is mocked wholesale; give the message helper a body
        with patch(
            MODULE + ".get_error_message",
            side_effect=lambda res: list(res.errors)[0].message,
        ):
            try:
                _get_patch(module, blade)
            except SystemExit:
                pass

        module.fail_json.assert_called_once()
        assert "Failed to get software patches" in module.fail_json.call_args[1]["msg"]
        assert "internal" in module.fail_json.call_args[1]["msg"]


@patch(MODULE + ".poll_until", new=_fake_poll)
@patch(MODULE + ".LooseVersion")
@patch(MODULE + ".get_system")
@patch(MODULE + ".AnsibleModule")
@patch(MODULE + ".HAS_PYPURECLIENT", True)
class TestInstall:
    """state=present flows."""

    def test_available_patch_is_installed_and_waited_for(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_patches.side_effect = [
            _response([_patch(status="available")]),
            _response([_patch(status="downloading")]),
            _response([_patch(status="installing")]),
            _response([_patch(status="installed")]),
        ]
        blade.post_software_patches.return_value = _response(
            [_patch(status="downloading")]
        )

        _run()

        blade.post_software_patches.assert_called_once_with(name="patch_1042")
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True
        assert module.exit_json.call_args[1]["software_patch"]["status"] == "installed"
        module.warn.assert_not_called()

    def test_downloaded_patch_is_installed(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(wait=False),
        )
        blade.get_software_patches.return_value = _response(
            [_patch(status="downloaded")]
        )
        blade.post_software_patches.return_value = _response(
            [_patch(status="installing")]
        )

        _run()

        blade.post_software_patches.assert_called_once_with(name="patch_1042")
        assert module.exit_json.call_args[1]["changed"] is True
        # without wait the record from the POST response is returned as is
        assert module.exit_json.call_args[1]["software_patch"]["status"] == "installing"
        assert blade.get_software_patches.call_count == 1

    def test_installed_patch_is_idempotent(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_patches.return_value = _response(
            [_patch(status="installed")]
        )

        _run()

        blade.post_software_patches.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False
        assert module.exit_json.call_args[1]["software_patch"]["status"] == "installed"

    def test_not_applicable_patch_is_left_alone(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_patches.return_value = _response(
            [_patch(status="not_applicable")]
        )

        _run()

        blade.post_software_patches.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False
        module.warn.assert_not_called()

    def test_unknown_patch_fails_without_post(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_patches.return_value = _response([_patch(name="other")])

        _run()

        blade.post_software_patches.assert_not_called()
        module.fail_json.assert_called_once()
        assert "not known to the array" in module.fail_json.call_args[1]["msg"]

    def test_in_progress_patch_is_waited_on_not_requested_again(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_patches.side_effect = [
            _response([_patch(status="installing")]),
            _response([_patch(status="installing")]),
            _response([_patch(status="installed")]),
        ]

        _run()

        blade.post_software_patches.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False
        assert module.exit_json.call_args[1]["software_patch"]["status"] == "installed"

    def test_in_progress_patch_without_wait_returns_immediately(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(wait=False),
        )
        blade.get_software_patches.return_value = _response(
            [_patch(status="downloading")]
        )

        _run()

        blade.post_software_patches.assert_not_called()
        assert blade.get_software_patches.call_count == 1
        assert module.exit_json.call_args[1]["changed"] is False
        assert (
            module.exit_json.call_args[1]["software_patch"]["status"] == "downloading"
        )

    def test_in_progress_patch_waited_on_reports_failure(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_patches.side_effect = [
            _response([_patch(status="installing")]),
            _response([_patch(status="failed", details="blade 3 rebooted")]),
        ]

        _run()

        module.fail_json.assert_called_once()
        kwargs = module.fail_json.call_args[1]
        assert kwargs["changed"] is False
        assert "failed to install" in kwargs["msg"]
        assert "blade 3 rebooted" in kwargs["msg"]

    def test_failed_patch_without_retry_fails(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_patches.return_value = _response(
            [_patch(status="failed", details="checksum mismatch")]
        )

        _run()

        blade.post_software_patches.assert_not_called()
        module.fail_json.assert_called_once()
        kwargs = module.fail_json.call_args[1]
        assert "failed to install previously" in kwargs["msg"]
        assert "checksum mismatch" in kwargs["msg"]
        assert "Set retry" in kwargs["msg"]
        assert kwargs["software_patch"]["status"] == "failed"

    def test_download_failed_patch_without_retry_fails(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_patches.return_value = _response(
            [_patch(status="download_failed")]
        )

        _run()

        blade.post_software_patches.assert_not_called()
        assert "failed to download previously" in module.fail_json.call_args[1]["msg"]

    def test_failed_patch_with_retry_is_installed_again(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(retry=True),
        )
        blade.get_software_patches.side_effect = [
            _response([_patch(status="download_failed")]),
            _response([_patch(status="installing")]),
            _response([_patch(status="installed")]),
        ]
        blade.post_software_patches.return_value = _response(
            [_patch(status="downloading")]
        )

        _run()

        blade.post_software_patches.assert_called_once_with(name="patch_1042")
        assert module.exit_json.call_args[1]["changed"] is True
        assert module.exit_json.call_args[1]["software_patch"]["status"] == "installed"

    def test_wait_starts_from_the_install_response(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_patches.return_value = _response(
            [_patch(status="downloaded")]
        )
        blade.post_software_patches.return_value = _response(
            [_patch(status="installed")]
        )

        _run()

        # the record the request returned is final; no listing is read again
        assert blade.get_software_patches.call_count == 1
        assert module.exit_json.call_args[1]["changed"] is True
        assert module.exit_json.call_args[1]["software_patch"]["status"] == "installed"

    def test_retry_is_not_failed_by_its_own_previous_record(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(retry=True),
        )
        stale = _patch(status="failed", details="blade 3 rebooted")
        blade.get_software_patches.side_effect = [
            _response([stale]),
            _response([stale]),
            _response([_patch(status="installing")]),
            _response([_patch(status="installed")]),
        ]
        # the request answers with the record from before it was processed
        blade.post_software_patches.return_value = _response([stale])

        _run()

        blade.post_software_patches.assert_called_once_with(name="patch_1042")
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True
        assert module.exit_json.call_args[1]["software_patch"]["status"] == "installed"

    def test_retry_reports_a_new_failure_once_the_array_moved_on(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(retry=True),
        )
        blade.get_software_patches.side_effect = [
            _response([_patch(status="failed", details="first attempt")]),
            _response([_patch(status="failed", details="second attempt")]),
        ]
        blade.post_software_patches.return_value = _response(
            [_patch(status="installing")]
        )

        _run()

        kwargs = module.fail_json.call_args[1]
        assert kwargs["changed"] is True
        assert (
            kwargs["msg"]
            == "Software patch patch_1042 failed to install. second attempt"
        )

    def test_retry_reports_an_unchanged_failure_after_the_grace_polls(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(retry=True),
        )
        blade.get_software_patches.return_value = _response(
            [_patch(status="download_failed", details="no route to cloud")]
        )
        blade.post_software_patches.return_value = _response([])

        _run()

        # the listing before the request plus RETRY_GRACE_POLLS observations
        assert blade.get_software_patches.call_count == 1 + RETRY_GRACE_POLLS
        kwargs = module.fail_json.call_args[1]
        assert kwargs["changed"] is True
        assert (
            kwargs["msg"]
            == "Software patch patch_1042 failed to download. no route to cloud"
        )

    def test_unexpected_status_fails_without_post(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_patches.return_value = _response(
            [_patch(status="quarantined")]
        )

        _run()

        blade.post_software_patches.assert_not_called()
        assert "unexpected status" in module.fail_json.call_args[1]["msg"]

    def test_ha_reduction_refused_before_post(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_patches.return_value = _response(
            [_patch(status="available", ha_reduction=True)]
        )

        _run()

        blade.post_software_patches.assert_not_called()
        module.fail_json.assert_called_once()
        assert "allow_ha_reduction" in module.fail_json.call_args[1]["msg"]

    def test_ha_reduction_refused_in_check_mode_too(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(),
            check_mode=True,
        )
        blade.get_software_patches.return_value = _response(
            [_patch(status="available", ha_reduction=True)]
        )

        _run()

        blade.post_software_patches.assert_not_called()
        module.exit_json.assert_not_called()
        assert "allow_ha_reduction" in module.fail_json.call_args[1]["msg"]

    def test_ha_reduction_allowed_is_sent(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(allow_ha_reduction=True, wait=False),
        )
        blade.get_software_patches.return_value = _response(
            [_patch(status="available", ha_reduction=True)]
        )
        blade.post_software_patches.return_value = _response(
            [_patch(status="downloading")]
        )

        _run()

        blade.post_software_patches.assert_called_once_with(
            name="patch_1042", allow_ha_reduction=True
        )
        assert module.exit_json.call_args[1]["changed"] is True

    def test_local_flag_is_sent(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(local=True, wait=False),
        )
        blade.get_software_patches.return_value = _response(
            [_patch(status="available")]
        )
        blade.post_software_patches.return_value = _response(
            [_patch(status="downloading")]
        )

        _run()

        blade.post_software_patches.assert_called_once_with(
            name="patch_1042", local=True
        )

    def test_check_mode_reports_change_without_post(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(),
            check_mode=True,
        )
        blade.get_software_patches.return_value = _response(
            [_patch(status="available")]
        )

        _run()

        blade.post_software_patches.assert_not_called()
        assert blade.get_software_patches.call_count == 1
        assert module.exit_json.call_args[1]["changed"] is True
        assert module.exit_json.call_args[1]["software_patch"]["status"] == "available"

    def test_check_mode_does_not_poll_an_in_progress_patch(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(),
            check_mode=True,
        )
        blade.get_software_patches.return_value = _response(
            [_patch(status="installing")]
        )

        _run()

        blade.post_software_patches.assert_not_called()
        assert blade.get_software_patches.call_count == 1
        assert module.exit_json.call_args[1]["changed"] is False

    def test_wait_reports_install_failure_with_changed(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_patches.side_effect = [
            _response([_patch(status="available")]),
            _response([_patch(status="installing")]),
            _response([_patch(status="failed", details="blade 3 rebooted")]),
        ]
        blade.post_software_patches.return_value = _response(
            [_patch(status="downloading")]
        )

        _run()

        module.fail_json.assert_called_once()
        kwargs = module.fail_json.call_args[1]
        assert kwargs["changed"] is True
        assert (
            kwargs["msg"]
            == "Software patch patch_1042 failed to install. blade 3 rebooted"
        )
        assert kwargs["software_patch"]["status"] == "failed"

    def test_wait_reports_download_failure(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_patches.side_effect = [
            _response([_patch(status="available")]),
            _response([_patch(status="download_failed")]),
        ]
        blade.post_software_patches.return_value = _response(
            [_patch(status="downloading")]
        )

        _run()

        kwargs = module.fail_json.call_args[1]
        assert kwargs["changed"] is True
        assert kwargs["msg"] == "Software patch patch_1042 failed to download."

    def test_wait_warns_when_patch_turns_out_not_applicable(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_patches.side_effect = [
            _response([_patch(status="available")]),
            _response([_patch(status="not_applicable", details="already fixed")]),
        ]
        blade.post_software_patches.return_value = _response(
            [_patch(status="downloading")]
        )

        _run()

        module.warn.assert_called_once()
        assert "not applicable" in module.warn.call_args[0][0]
        assert "already fixed" in module.warn.call_args[0][0]
        assert module.exit_json.call_args[1]["changed"] is True
        assert (
            module.exit_json.call_args[1]["software_patch"]["status"]
            == "not_applicable"
        )

    def test_timeout_fails_module_with_changed(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        # the patch never leaves installing, so the fake poll gives up
        blade.get_software_patches.side_effect = [
            _response([_patch(status="available")])
        ] + [_response([_patch(status="installing")])] * 10
        blade.post_software_patches.return_value = _response(
            [_patch(status="downloading")]
        )

        _run()

        module.fail_json.assert_called_once()
        kwargs = module.fail_json.call_args[1]
        assert kwargs["changed"] is True
        assert "Timed out after 1800 seconds" in kwargs["msg"]
        assert "status: installing" in kwargs["msg"]
        assert kwargs["software_patch"]["status"] == "installing"

    def test_post_without_items_reads_the_patch_back(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(wait=False),
        )
        blade.get_software_patches.side_effect = [
            _response([_patch(status="available")]),
            _response([_patch(status="downloading")]),
        ]
        blade.post_software_patches.return_value = _response([])

        _run()

        assert blade.get_software_patches.call_count == 2
        assert module.exit_json.call_args[1]["changed"] is True
        assert (
            module.exit_json.call_args[1]["software_patch"]["status"] == "downloading"
        )

    def test_post_api_error_is_reported(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_patches.return_value = _response(
            [_patch(status="available")]
        )
        blade.post_software_patches.return_value = _response(
            status_code=400, message="phonehome is disabled"
        )

        with patch(
            MODULE + ".get_error_message",
            side_effect=lambda res: list(res.errors)[0].message,
        ):
            _run()

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to install software patch patch_1042" in msg
        assert "phonehome is disabled" in msg

    def test_get_api_error_is_reported(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_patches.return_value = _response(status_code=500)

        _run()

        blade.post_software_patches.assert_not_called()
        assert "Failed to get software patches" in module.fail_json.call_args[1]["msg"]


class TestMainGuards:
    """Argument handling and preconditions."""

    @patch(MODULE + ".LooseVersion")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", False)
    def test_fails_without_sdk(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )

        _run()

        module.fail_json.assert_called_once()
        assert "py-pure-client" in module.fail_json.call_args[1]["msg"]
        mock_get_system.assert_not_called()

    @patch(MODULE + ".LooseVersion")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_rejects_non_positive_timeout(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(timeout=0),
        )

        _run()

        module.fail_json.assert_called_once()
        assert "timeout" in module.fail_json.call_args[1]["msg"]
        mock_get_system.assert_not_called()

    @patch(MODULE + ".LooseVersion")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_version_gate_fails_before_any_call(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)

        _run()

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Minimum version required: 2.24" in msg
        blade.get_software_patches.assert_not_called()
        blade.post_software_patches.assert_not_called()

    @patch(MODULE + ".LooseVersion")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_local_requires_rest_2_29(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(local=True),
        )
        # the module gate (2.24) passes, the local gate (2.29) fails
        mock_loose_version.return_value.__gt__ = Mock(side_effect=[False, True])

        _run()

        module.fail_json.assert_called_once()
        assert (
            "local option requires version 2.29" in module.fail_json.call_args[1]["msg"]
        )
        blade.get_software_patches.assert_not_called()

    @patch(MODULE + ".LooseVersion")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_local_gate_is_skipped_when_local_is_false(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        mock_loose_version.return_value.__gt__ = Mock(side_effect=[False, True])
        blade.get_software_patches.return_value = _response(
            [_patch(status="installed")]
        )

        _run()

        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @patch(MODULE + ".purefb_argument_spec", new=dict)
    @patch(MODULE + ".LooseVersion")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_argument_spec(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_patches.return_value = _response(
            [_patch(status="installed")]
        )

        _run()

        assert mock_ansible_module.call_args[1]["supports_check_mode"] is True
        spec = mock_ansible_module.call_args[0][0]
        assert spec["name"]["required"] is True
        assert spec["state"]["choices"] == ["present"]
        assert spec["allow_ha_reduction"]["default"] is False
        assert spec["local"]["default"] is False
        assert spec["retry"]["default"] is False
        assert spec["wait"]["default"] is True
        assert spec["timeout"]["default"] == 1800
