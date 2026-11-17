# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_software module."""

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

from plugins.modules.purefb_software import (
    main,
    _check_matches,
    _latest,
    _check_to_dict,
    _software_to_dict,
    _bundle_to_dict,
)

MODULE = "plugins.modules.purefb_software"


def _fake_poll(fetch, finished, timeout, interval=None):
    """Stand-in for module_utils.common.poll_until: polls without sleeping.

    Gives up after a handful of fetches so a never-finishing object exercises
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
        "state": "check",
        "name": "Purity//FB",
        "version": "4.8.9",
        "local": False,
        "bundle_source": None,
        "force": False,
        "wait": None,
        "timeout": 600,
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


def _check_task(
    task_id="t1", status="passed", version="4.8.9", start_time=100, checks=None
):
    task = Mock()
    task.id = task_id
    task.name = "Purity//FB_{0}".format(version)
    task.status = status
    task.software_name = "Purity//FB"
    task.software_version = "4.8.8"
    task.software_upgrade_hops = ["4.8.8", version]
    task.start_time = start_time
    task.end_time = None if start_time is None else start_time + 300
    task.details = None
    task.checks = checks if checks is not None else []
    return task


def _check_item(name, status, details="-"):
    item = Mock()
    item.name = name
    item.status = status
    item.details = details
    return item


def _package(status="downloaded", version="4.8.9"):
    package = Mock()
    package.id = "679"
    package.name = "Purity//FB"
    package.version = version
    package.status = status
    package.progress = 1.0 if status == "downloaded" else 0.0
    package.details = (
        "Software download failed" if status == "download_failed" else None
    )
    package.payload_id = "abc"
    package.upgrade_hops = ["4.8.8", version]
    return package


def _bundle(status="ready", source="https://repo.example.com/fb.tar", created=1):
    bundle = Mock()
    bundle.id = "b-{0}".format(created)
    bundle.source = source
    bundle.status = status
    bundle.software_name = "Purity//FB"
    bundle.software_version = "4.8.9"
    bundle.download_progress = 1.0
    bundle.bytes_downloaded = 10
    bundle.bytes_total = 10
    bundle.created = created
    bundle.details = None
    return bundle


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
    blade.get_versions.return_value.items = ["2.16", "2.24", "2.30"]
    mock_get_system.return_value = blade
    return module, blade


def _run():
    try:
        main()
    except SystemExit:
        pass


class TestHelpers:
    """Helper-function unit tests."""

    def test_check_matches_on_task_name(self):
        task = _check_task(version="4.8.9")
        task.software_upgrade_hops = None
        assert _check_matches(task, "Purity//FB", "4.8.9") is True

    def test_check_matches_on_last_upgrade_hop(self):
        task = _check_task(version="4.8.9")
        task.name = "something else"
        assert _check_matches(task, "Purity//FB", "4.8.9") is True

    def test_check_matches_ignores_source_version(self):
        """software_version holds the version the checks ran from, never the target."""
        task = _check_task(version="4.8.9")
        assert task.software_version == "4.8.8"
        assert _check_matches(task, "Purity//FB", "4.8.8") is False

    def test_check_matches_rejects_other_software(self):
        task = _check_task(version="4.8.9")
        task.software_name = "Other"
        assert _check_matches(task, "Purity//FB", "4.8.9") is False

    def test_latest_picks_highest_field(self):
        old = _check_task("old", start_time=10)
        new = _check_task("new", start_time=20)
        assert _latest([new, old], "start_time") is new

    def test_latest_tie_prefers_last_listed(self):
        first = _check_task("first", start_time=None)
        second = _check_task("second", start_time=None)
        assert _latest([first, second], "start_time") is second

    def test_latest_empty_is_none(self):
        assert _latest([], "start_time") is None

    def test_to_dict_helpers_handle_none(self):
        assert _check_to_dict(None) == {}
        assert _software_to_dict(None) == {}
        assert _bundle_to_dict(None) == {}

    def test_check_to_dict_flattens_checks(self):
        task = _check_task(checks=[_check_item("Firmware check", "passed", "ok")])
        result = _check_to_dict(task)
        assert result["software_upgrade_hops"] == ["4.8.8", "4.8.9"]
        assert result["checks"] == [
            {"name": "Firmware check", "status": "passed", "details": "ok"}
        ]


@patch(MODULE + ".poll_until", new=_fake_poll)
@patch(MODULE + ".LooseVersion")
@patch(MODULE + ".get_system")
@patch(MODULE + ".AnsibleModule")
@patch(MODULE + ".HAS_PYPURECLIENT", True)
class TestCheckState:
    """state=check flows."""

    def test_runs_check_when_none_exists_and_waits(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        running = _check_task(status="running")
        passed = _check_task(status="passed")
        blade.get_software_check.side_effect = [
            _response([]),  # no task yet
            _response([running]),  # first poll
            _response([passed]),  # second poll
        ]
        blade.post_software_check.return_value = _response([running])

        _run()

        blade.post_software_check.assert_called_once_with(
            software_names=["Purity//FB"], software_versions=["4.8.9"]
        )
        assert blade.get_software_check.call_args_list[1][1] == {"ids": ["t1"]}
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True
        assert module.exit_json.call_args[1]["software_check"]["status"] == "passed"

    def test_existing_passed_check_is_idempotent(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_check.return_value = _response(
            [_check_task(status="passed")]
        )

        _run()

        blade.post_software_check.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False
        assert module.exit_json.call_args[1]["software_check"]["id"] == "t1"

    def test_force_reruns_a_passed_check(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(force=True, wait=False),
        )
        blade.get_software_check.return_value = _response(
            [_check_task(status="passed")]
        )
        blade.post_software_check.return_value = _response(
            [_check_task("t2", status="queued")]
        )

        _run()

        blade.post_software_check.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True
        assert module.exit_json.call_args[1]["software_check"]["status"] == "queued"

    def test_failed_check_is_rerun_and_newest_task_wins(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(wait=False),
        )
        older_passed = _check_task("old", status="passed", start_time=10)
        newer_failed = _check_task("new", status="failed", start_time=20)
        blade.get_software_check.return_value = _response([older_passed, newer_failed])
        blade.post_software_check.return_value = _response(
            [_check_task("t3", status="queued")]
        )

        _run()

        blade.post_software_check.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_other_version_task_is_ignored(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(wait=False),
        )
        blade.get_software_check.return_value = _response(
            [_check_task(status="passed", version="4.8.8")]
        )
        blade.post_software_check.return_value = _response(
            [_check_task("t2", status="queued")]
        )

        _run()

        blade.post_software_check.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_running_check_is_waited_on_not_duplicated(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_check.side_effect = [
            _response([_check_task(status="running")]),
            _response([_check_task(status="passed")]),
        ]

        _run()

        blade.post_software_check.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False
        assert module.exit_json.call_args[1]["software_check"]["status"] == "passed"

    def test_running_check_without_wait_returns_immediately(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(wait=False),
        )
        blade.get_software_check.return_value = _response(
            [_check_task(status="running")]
        )

        _run()

        assert blade.get_software_check.call_count == 1
        assert module.exit_json.call_args[1]["changed"] is False
        assert module.exit_json.call_args[1]["software_check"]["status"] == "running"

    def test_failed_result_fails_module_with_changed(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        failed = _check_task(
            status="failed",
            checks=[
                _check_item("Firmware check", "passed"),
                _check_item("Drive move check", "failed", "reseat"),
            ],
        )
        blade.get_software_check.side_effect = [_response([]), _response([failed])]
        blade.post_software_check.return_value = _response(
            [_check_task(status="running")]
        )

        _run()

        module.fail_json.assert_called_once()
        kwargs = module.fail_json.call_args[1]
        assert kwargs["changed"] is True
        assert "Drive move check" in kwargs["msg"]
        assert "Firmware check" not in kwargs["msg"]
        assert kwargs["software_check"]["status"] == "failed"

    def test_timeout_fails_module(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_check.side_effect = [_response([])] + [
            _response([_check_task(status="running")]) for _ in range(10)
        ]
        blade.post_software_check.return_value = _response(
            [_check_task(status="queued")]
        )

        _run()

        module.fail_json.assert_called_once()
        assert "Timed out" in module.fail_json.call_args[1]["msg"]
        assert module.fail_json.call_args[1]["changed"] is True

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
        blade.get_software_check.return_value = _response([])

        _run()

        blade.post_software_check.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True
        assert module.exit_json.call_args[1]["software_check"] == {}

    def test_local_flag_is_sent(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(local=True, wait=False),
        )
        blade.get_software_check.return_value = _response([])
        blade.post_software_check.return_value = _response(
            [_check_task(status="queued")]
        )

        _run()

        blade.post_software_check.assert_called_once_with(
            software_names=["Purity//FB"], software_versions=["4.8.9"], local=True
        )

    def test_local_requires_rest_2_30(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(local=True),
        )
        # the check gate (2.16) passes, the local gate (2.30) fails
        mock_loose_version.return_value.__gt__ = Mock(side_effect=[False, True])

        _run()

        module.fail_json.assert_called_once()
        assert "local option requires" in module.fail_json.call_args[1]["msg"]
        blade.get_software_check.assert_not_called()

    def test_post_api_error_is_reported(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_check.return_value = _response([])
        blade.post_software_check.return_value = _response(
            status_code=400, message="task already running"
        )

        _run()

        module.fail_json.assert_called_once()
        assert "Failed to start software check" in module.fail_json.call_args[1]["msg"]
        assert module.fail_json.call_args[1]["changed"] is False

    def test_refused_check_recorded_as_failed_task_reports_change(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(force=True),
        )
        passed = _check_task(task_id="t1", status="passed", start_time=100)
        refused = _check_task(task_id="t2", status="failed", start_time=200)
        refused.details = "Internal error: incompatible upgrade path."
        blade.get_software_check.side_effect = [
            _response([passed]),
            _response([refused]),
        ]
        blade.post_software_check.return_value = _response(
            status_code=400, message="Internal error: incompatible upgrade path."
        )

        _run()

        module.fail_json.assert_called_once()
        kwargs = module.fail_json.call_args[1]
        assert kwargs["changed"] is True
        assert "Failed to start software check" in kwargs["msg"]
        assert kwargs["software_check"]["id"] == "t2"
        assert kwargs["software_check"]["status"] == "failed"

    def test_post_api_error_survives_reread_failure(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_check.side_effect = [
            _response([]),
            _response(status_code=500),
        ]
        blade.post_software_check.return_value = _response(
            status_code=400, message="task already running"
        )

        _run()

        module.fail_json.assert_called_once()
        assert "Failed to start software check" in module.fail_json.call_args[1]["msg"]
        assert module.fail_json.call_args[1]["changed"] is False

    def test_get_api_error_is_reported(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_check.return_value = _response(status_code=500)

        _run()

        module.fail_json.assert_called_once()
        assert (
            "Failed to get software check tasks" in module.fail_json.call_args[1]["msg"]
        )
        blade.post_software_check.assert_not_called()


@patch(MODULE + ".poll_until", new=_fake_poll)
@patch(MODULE + ".SoftwarePost")
@patch(MODULE + ".LooseVersion")
@patch(MODULE + ".get_system")
@patch(MODULE + ".AnsibleModule")
@patch(MODULE + ".HAS_PYPURECLIENT", True)
class TestDownloadedState:
    """state=downloaded flows."""

    def test_downloads_without_waiting_by_default(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_post
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="downloaded"),
        )
        blade.get_software.return_value = _response([])
        blade.post_software.return_value = _response([_package(status="new")])

        _run()

        mock_post.assert_called_once_with(name="Purity//FB", version="4.8.9")
        blade.post_software.assert_called_once_with(software=mock_post.return_value)
        blade.delete_software.assert_not_called()
        assert blade.get_software.call_count == 1
        assert module.exit_json.call_args[1]["changed"] is True
        assert module.exit_json.call_args[1]["software"]["status"] == "new"

    def test_downloads_and_waits_when_asked(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_post
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="downloaded", wait=True),
        )
        blade.get_software.side_effect = [
            _response([]),
            _response([_package(status="downloading")]),
            _response([_package(status="downloaded")]),
        ]
        blade.post_software.return_value = _response([_package(status="new")])

        _run()

        assert module.exit_json.call_args[1]["changed"] is True
        assert module.exit_json.call_args[1]["software"]["status"] == "downloaded"

    def test_downloaded_package_is_idempotent(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_post
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="downloaded"),
        )
        blade.get_software.return_value = _response([_package(status="downloaded")])

        _run()

        blade.post_software.assert_not_called()
        blade.delete_software.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_other_version_package_does_not_match(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_post
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="downloaded"),
        )
        blade.get_software.return_value = _response(
            [_package(status="downloaded", version="4.8.8")]
        )
        blade.post_software.return_value = _response([_package(status="new")])

        _run()

        # the array itself refuses a second uninstalled package; the module
        # does not second-guess it
        blade.post_software.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_in_progress_download_is_waited_on(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_post
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="downloaded", wait=True),
        )
        blade.get_software.side_effect = [
            _response([_package(status="downloading")]),
            _response([_package(status="downloaded")]),
        ]

        _run()

        blade.post_software.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False
        assert module.exit_json.call_args[1]["software"]["status"] == "downloaded"

    def test_failed_download_without_force_fails(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_post
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="downloaded"),
        )
        blade.get_software.return_value = _response(
            [_package(status="download_failed")]
        )

        _run()

        module.fail_json.assert_called_once()
        assert "Set force" in module.fail_json.call_args[1]["msg"]
        assert module.fail_json.call_args[1]["software"]["status"] == "download_failed"
        blade.delete_software.assert_not_called()
        blade.post_software.assert_not_called()

    def test_failed_download_with_force_deletes_then_downloads(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_post
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="downloaded", force=True),
        )
        blade.get_software.return_value = _response(
            [_package(status="download_failed")]
        )
        blade.delete_software.return_value = _response()
        blade.post_software.return_value = _response([_package(status="new")])

        _run()

        blade.delete_software.assert_called_once_with(
            names=["Purity//FB"], software_versions=["4.8.9"]
        )
        blade.post_software.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_wait_reports_download_failure(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_post
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="downloaded", wait=True),
        )
        blade.get_software.side_effect = [
            _response([]),
            _response([_package(status="download_failed")]),
        ]
        blade.post_software.return_value = _response([_package(status="new")])

        _run()

        module.fail_json.assert_called_once()
        assert module.fail_json.call_args[1]["changed"] is True
        assert (
            "Download of Purity//FB 4.8.9 failed"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_check_mode_with_force_touches_nothing(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_post
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="downloaded", force=True),
            check_mode=True,
        )
        blade.get_software.return_value = _response(
            [_package(status="download_failed")]
        )

        _run()

        blade.delete_software.assert_not_called()
        blade.post_software.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_post_api_error_is_reported(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_post
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="downloaded"),
        )
        blade.get_software.return_value = _response([])
        blade.post_software.return_value = _response(
            status_code=400, message="another package present"
        )

        _run()

        module.fail_json.assert_called_once()
        assert "Failed to start the download" in module.fail_json.call_args[1]["msg"]
        assert module.fail_json.call_args[1]["changed"] is False

    def test_post_failure_after_forced_delete_reports_change(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_post
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="downloaded", force=True),
        )
        blade.get_software.return_value = _response(
            [_package(status="download_failed")]
        )
        blade.delete_software.return_value = _response()
        blade.post_software.return_value = _response(
            status_code=400, message="phone home disabled"
        )

        _run()

        blade.delete_software.assert_called_once()
        module.fail_json.assert_called_once()
        assert module.fail_json.call_args[1]["changed"] is True
        assert "Failed to start the download" in module.fail_json.call_args[1]["msg"]

    def test_version_gate(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_post
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="downloaded"),
        )
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)

        _run()

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "REST version not supported" in msg
        assert "state=downloaded" in msg
        assert "2.30" in msg
        blade.get_software.assert_not_called()


@patch(MODULE + ".poll_until", new=_fake_poll)
@patch(MODULE + ".SoftwareBundlePost")
@patch(MODULE + ".LooseVersion")
@patch(MODULE + ".get_system")
@patch(MODULE + ".AnsibleModule")
@patch(MODULE + ".HAS_PYPURECLIENT", True)
class TestStagedState:
    """state=staged flows."""

    SOURCE = "https://repo.example.com/fb.tar"

    def test_stages_bundle_without_waiting_by_default(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_post
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="staged", version=None, bundle_source=self.SOURCE),
        )
        blade.get_software_bundle.return_value = _response([])
        blade.post_software_bundle.return_value = _response(
            [_bundle(status="downloading")]
        )

        _run()

        mock_post.assert_called_once_with(source=self.SOURCE)
        blade.post_software_bundle.assert_called_once_with(
            source=mock_post.return_value
        )
        assert blade.get_software_bundle.call_count == 1
        assert module.exit_json.call_args[1]["changed"] is True
        assert (
            module.exit_json.call_args[1]["software_bundle"]["status"] == "downloading"
        )

    def test_ready_bundle_from_same_source_is_idempotent(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_post
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="staged", version=None, bundle_source=self.SOURCE),
        )
        blade.get_software_bundle.return_value = _response(
            [_bundle(status="ready", source=self.SOURCE)]
        )

        _run()

        blade.post_software_bundle.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_ready_bundle_from_other_source_is_restaged(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_post
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="staged", version=None, bundle_source=self.SOURCE),
        )
        blade.get_software_bundle.return_value = _response(
            [_bundle(status="ready", source="ftp://other/fb.tar")]
        )
        blade.post_software_bundle.return_value = _response(
            [_bundle(status="downloading")]
        )

        _run()

        blade.post_software_bundle.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_newest_failed_bundle_is_restaged(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_post
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="staged", version=None, bundle_source=self.SOURCE),
        )
        blade.get_software_bundle.return_value = _response(
            [
                _bundle(status="ready", source=self.SOURCE, created=1),
                _bundle(status="failed", source=self.SOURCE, created=2),
            ]
        )
        blade.post_software_bundle.return_value = _response(
            [_bundle(status="downloading", created=3)]
        )

        _run()

        blade.post_software_bundle.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_verifying_bundle_is_waited_on(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_post
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(
                state="staged", version=None, bundle_source=self.SOURCE, wait=True
            ),
        )
        blade.get_software_bundle.side_effect = [
            _response([_bundle(status="verifying", source=self.SOURCE)]),
            _response([_bundle(status="ready", source=self.SOURCE)]),
        ]

        _run()

        blade.post_software_bundle.assert_not_called()
        assert blade.get_software_bundle.call_args_list[1][1] == {"ids": ["b-1"]}
        assert module.exit_json.call_args[1]["changed"] is False
        assert module.exit_json.call_args[1]["software_bundle"]["status"] == "ready"

    def test_wait_reports_bundle_failure(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_post
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(
                state="staged", version=None, bundle_source=self.SOURCE, wait=True
            ),
        )
        blade.get_software_bundle.side_effect = [
            _response([]),
            _response([_bundle(status="failed", source=self.SOURCE)]),
        ]
        blade.post_software_bundle.return_value = _response(
            [_bundle(status="downloading", source=self.SOURCE)]
        )

        _run()

        module.fail_json.assert_called_once()
        assert module.fail_json.call_args[1]["changed"] is True
        assert "bundle download" in module.fail_json.call_args[1]["msg"]

    def test_check_mode_does_not_post(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_post
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="staged", version=None, bundle_source=self.SOURCE),
            check_mode=True,
        )
        blade.get_software_bundle.return_value = _response([])

        _run()

        blade.post_software_bundle.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_post_api_error_is_reported(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_post
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="staged", version=None, bundle_source=self.SOURCE),
        )
        blade.get_software_bundle.return_value = _response([])
        blade.post_software_bundle.return_value = _response(
            status_code=400, message="unreachable"
        )

        _run()

        module.fail_json.assert_called_once()
        assert (
            "Failed to start the software bundle download"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_version_gate(
        self, mock_ansible_module, mock_get_system, mock_loose_version, mock_post
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="staged", version=None, bundle_source=self.SOURCE),
        )
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)

        _run()

        module.fail_json.assert_called_once()
        assert "2.24" in module.fail_json.call_args[1]["msg"]
        blade.get_software_bundle.assert_not_called()


@patch(MODULE + ".LooseVersion")
@patch(MODULE + ".get_system")
@patch(MODULE + ".AnsibleModule")
@patch(MODULE + ".HAS_PYPURECLIENT", True)
class TestAbsentState:
    """state=absent flows."""

    def test_deletes_existing_package(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="absent"),
        )
        blade.get_software.return_value = _response(
            [_package(status="download_failed")]
        )
        blade.delete_software.return_value = _response()

        _run()

        blade.delete_software.assert_called_once_with(
            names=["Purity//FB"], software_versions=["4.8.9"]
        )
        assert module.exit_json.call_args[1]["changed"] is True

    def test_missing_package_is_idempotent(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="absent"),
        )
        blade.get_software.return_value = _response(
            [_package(status="downloaded", version="4.8.8")]
        )

        _run()

        blade.delete_software.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_check_mode_does_not_delete(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="absent"),
            check_mode=True,
        )
        blade.get_software.return_value = _response([_package()])

        _run()

        blade.delete_software.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    def test_delete_api_error_is_reported(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="absent"),
        )
        blade.get_software.return_value = _response([_package()])
        blade.delete_software.return_value = _response(
            status_code=400, message="installing"
        )

        _run()

        module.fail_json.assert_called_once()
        assert "Failed to delete software" in module.fail_json.call_args[1]["msg"]


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

    @patch(MODULE + ".purefb_argument_spec", new=dict)
    @patch(MODULE + ".LooseVersion")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_argument_spec_and_required_if(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module,
            mock_get_system,
            mock_loose_version,
            _base_params(state="absent"),
        )
        blade.get_software.return_value = _response([])

        _run()

        kwargs = mock_ansible_module.call_args[1]
        assert kwargs["supports_check_mode"] is True
        assert ["state", "check", ["version"]] in kwargs["required_if"]
        assert ["state", "downloaded", ["version"]] in kwargs["required_if"]
        assert ["state", "absent", ["version"]] in kwargs["required_if"]
        assert ["state", "staged", ["bundle_source"]] in kwargs["required_if"]
        spec = mock_ansible_module.call_args[0][0]
        assert spec["state"]["choices"] == ["check", "downloaded", "staged", "absent"]
        assert spec["name"]["default"] == "Purity//FB"
        assert spec["timeout"]["default"] == 600
        assert "default" not in spec["wait"]

    @patch(MODULE + ".poll_until", new=_fake_poll)
    @patch(MODULE + ".LooseVersion")
    @patch(MODULE + ".get_system")
    @patch(MODULE + ".AnsibleModule")
    @patch(MODULE + ".HAS_PYPURECLIENT", True)
    def test_wait_defaults_to_true_for_check(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module, blade = _setup(
            mock_ansible_module, mock_get_system, mock_loose_version, _base_params()
        )
        blade.get_software_check.side_effect = [
            _response([_check_task(status="running")]),
            _response([_check_task(status="passed")]),
        ]

        _run()

        assert module.params["wait"] is True
        assert blade.get_software_check.call_count == 2
