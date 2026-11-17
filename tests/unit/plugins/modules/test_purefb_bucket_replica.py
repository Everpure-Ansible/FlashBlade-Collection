# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_bucket_replica module."""

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

from plugins.modules.purefb_bucket_replica import (
    main,
    get_unhealthy_blocked_changes,
)

REMOTE = "arrayb"
CRED = "cred_1"
REMOTE_BUCKET = "bar"


def _ref(name):
    ref = Mock()
    ref.name = name
    return ref


STATUS_DETAILS = (
    "Replica link set-up issue. Please enable versioning on the target bucket."
)


def _link(paused=False, status="replicating", credential=CRED, cascading=False):
    link = Mock()
    link.paused = paused
    link.status = status
    link.status_details = STATUS_DETAILS if status == "unhealthy" else None
    link.cascading_enabled = cascading
    link.remote = _ref(REMOTE)
    link.remote_bucket = _ref(REMOTE_BUCKET)
    link.remote_credentials = _ref(REMOTE + "/" + credential)
    return link


def _response(items=None, status_code=200):
    response = Mock()
    response.status_code = status_code
    response.items = items if items is not None else []
    return response


def _base_params(**overrides):
    params = {
        "name": "foo",
        "state": "present",
        "target": None,
        "target_bucket": None,
        "paused": False,
        "cascading": False,
        "credential": None,
        "context": "",
    }
    params.update(overrides)
    return params


def _module(params, check_mode=False):
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.params = params
    module.check_mode = check_mode
    return module


def _blade(link=None, patch_status=200):
    blade = Mock()
    blade.get_bucket_replica_links.return_value = _response([link] if link else [])
    blade.get_buckets.return_value = _response([_ref("foo")])
    blade.get_object_store_remote_credentials.return_value = _response(
        [_ref(REMOTE + "/" + CRED)]
    )
    connection = Mock()
    connection.remote = _ref(REMOTE)
    connection.status = "connected"
    blade.get_array_connections.return_value = _response([connection])
    blade.get_targets.return_value = _response([])
    blade.patch_bucket_replica_links.return_value = _response(status_code=patch_status)
    blade.post_bucket_replica_links.return_value = _response()
    blade.delete_bucket_replica_links.return_value = _response()
    return blade


def _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version):
    """Run main() with the array answering as blade; no context / fleet"""
    mock_loose_version.return_value.__le__ = Mock(return_value=False)
    mock_ansible_module.return_value = module
    mock_get_system.return_value = blade
    try:
        main()
    except SystemExit:
        pass


class TestPurefbBucketReplica:
    """Test cases for purefb_bucket_replica module"""

    # ---------------- helper-function unit tests ----------------

    def test_blocked_changes_pause_only_is_allowed(self):
        """Pausing an unhealthy running link needs no healthy link"""
        module = Mock()
        module.params = _base_params(paused=True, credential=CRED)
        assert get_unhealthy_blocked_changes(module, _link(status="unhealthy")) == []

    def test_blocked_changes_noop_is_allowed(self):
        """A request that changes nothing is not blocked"""
        module = Mock()
        module.params = _base_params(credential=CRED)
        assert get_unhealthy_blocked_changes(module, _link(status="unhealthy")) == []

    def test_blocked_changes_resume_refused(self):
        """Resuming a paused unhealthy link is blocked"""
        module = Mock()
        module.params = _base_params(paused=False, credential=CRED)
        link = _link(paused=True, status="unhealthy")
        assert get_unhealthy_blocked_changes(module, link) == ["resume"]

    def test_blocked_changes_credential_refused(self):
        """Changing the remote credential is blocked even when pausing"""
        module = Mock()
        module.params = _base_params(paused=True, credential="cred_2")
        link = _link(status="unhealthy")
        assert get_unhealthy_blocked_changes(module, link) == ["credential"]

    def test_blocked_changes_cascading_refused(self):
        """Changing cascading is blocked"""
        module = Mock()
        module.params = _base_params(credential=CRED, cascading=True)
        link = _link(status="unhealthy")
        assert get_unhealthy_blocked_changes(module, link) == ["cascading"]

    def test_blocked_changes_lists_every_refused_change(self):
        """All blocked changes are named"""
        module = Mock()
        module.params = _base_params(paused=False, credential="cred_2", cascading=True)
        link = _link(paused=True, status="unhealthy")
        assert get_unhealthy_blocked_changes(module, link) == [
            "resume",
            "credential",
            "cascading",
        ]

    # ---------------- main(): unhealthy link ----------------

    @patch("plugins.modules.purefb_bucket_replica.LooseVersion")
    @patch("plugins.modules.purefb_bucket_replica.ReferenceWritable")
    @patch("plugins.modules.purefb_bucket_replica.BucketReplicaLink")
    @patch("plugins.modules.purefb_bucket_replica.get_system")
    @patch("plugins.modules.purefb_bucket_replica.AnsibleModule")
    @patch("plugins.modules.purefb_bucket_replica.HAS_PYPURECLIENT", True)
    def test_main_pauses_unhealthy_link(
        self,
        mock_ansible_module,
        mock_get_system,
        mock_rl,
        mock_ref,
        mock_loose_version,
    ):
        """paused=true on an unhealthy link is sent to the array"""
        module = _module(_base_params(paused=True))
        blade = _blade(link=_link(status="unhealthy"))

        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        module.fail_json.assert_not_called()
        blade.patch_bucket_replica_links.assert_called_once()
        call_kwargs = blade.patch_bucket_replica_links.call_args[1]
        assert call_kwargs["local_bucket_names"] == ["foo"]
        assert call_kwargs["remote_bucket_names"] == [REMOTE_BUCKET]
        assert call_kwargs["remote_names"] == [REMOTE]
        mock_rl.assert_called_once_with(
            paused=True,
            remote_credentials=mock_ref.return_value,
            cascading_enabled=False,
        )
        mock_ref.assert_called_once_with(name=REMOTE + "/" + CRED)
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_bucket_replica.LooseVersion")
    @patch("plugins.modules.purefb_bucket_replica.get_system")
    @patch("plugins.modules.purefb_bucket_replica.AnsibleModule")
    @patch("plugins.modules.purefb_bucket_replica.HAS_PYPURECLIENT", True)
    def test_main_pause_unhealthy_link_check_mode(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Check mode reports the pause without a PATCH"""
        module = _module(_base_params(paused=True), check_mode=True)
        blade = _blade(link=_link(status="unhealthy"))

        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        module.fail_json.assert_not_called()
        blade.patch_bucket_replica_links.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_bucket_replica.LooseVersion")
    @patch("plugins.modules.purefb_bucket_replica.get_system")
    @patch("plugins.modules.purefb_bucket_replica.AnsibleModule")
    @patch("plugins.modules.purefb_bucket_replica.HAS_PYPURECLIENT", True)
    def test_main_unhealthy_link_rerun_is_idempotent(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Re-applying the current settings to an unhealthy link is a no-op"""
        module = _module(_base_params(target=REMOTE, credential=CRED))
        blade = _blade(link=_link(status="unhealthy"))

        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        module.fail_json.assert_not_called()
        blade.patch_bucket_replica_links.assert_not_called()
        module.exit_json.assert_called_once()
        assert module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_bucket_replica.LooseVersion")
    @patch("plugins.modules.purefb_bucket_replica.get_system")
    @patch("plugins.modules.purefb_bucket_replica.AnsibleModule")
    @patch("plugins.modules.purefb_bucket_replica.HAS_PYPURECLIENT", True)
    def test_main_refuses_cascading_change_on_unhealthy_link(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Changing cascading on an unhealthy link is refused before any write"""
        module = _module(_base_params(cascading=True))
        blade = _blade(link=_link(status="unhealthy"))

        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.patch_bucket_replica_links.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "unhealthy" in msg
        assert "cascading" in msg

    @patch("plugins.modules.purefb_bucket_replica.LooseVersion")
    @patch("plugins.modules.purefb_bucket_replica.get_system")
    @patch("plugins.modules.purefb_bucket_replica.AnsibleModule")
    @patch("plugins.modules.purefb_bucket_replica.HAS_PYPURECLIENT", True)
    def test_main_refuses_credential_change_on_unhealthy_link(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """A pause combined with a credential change is refused"""
        module = _module(_base_params(paused=True, credential="cred_2"))
        blade = _blade(link=_link(status="unhealthy"))

        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.patch_bucket_replica_links.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "unhealthy" in msg
        assert "credential" in msg

    @patch("plugins.modules.purefb_bucket_replica.LooseVersion")
    @patch("plugins.modules.purefb_bucket_replica.get_system")
    @patch("plugins.modules.purefb_bucket_replica.AnsibleModule")
    @patch("plugins.modules.purefb_bucket_replica.HAS_PYPURECLIENT", True)
    def test_main_refuses_resume_of_unhealthy_link(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Resuming a paused unhealthy link is refused"""
        module = _module(_base_params(paused=False))
        blade = _blade(link=_link(paused=True, status="unhealthy"))

        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.patch_bucket_replica_links.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "unhealthy" in msg
        assert "resume" in msg

    @patch("plugins.modules.purefb_bucket_replica.LooseVersion")
    @patch("plugins.modules.purefb_bucket_replica.get_system")
    @patch("plugins.modules.purefb_bucket_replica.AnsibleModule")
    @patch("plugins.modules.purefb_bucket_replica.HAS_PYPURECLIENT", True)
    def test_main_deletes_unhealthy_link(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """state=absent removes an unhealthy link"""
        module = _module(_base_params(state="absent"))
        blade = _blade(link=_link(status="unhealthy"))

        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        module.fail_json.assert_not_called()
        blade.delete_bucket_replica_links.assert_called_once_with(
            remote_names=[REMOTE],
            local_bucket_names=["foo"],
            remote_bucket_names=[REMOTE_BUCKET],
        )
        assert module.exit_json.call_args[1]["changed"] is True

    # ---------------- main(): healthy link ----------------

    @patch("plugins.modules.purefb_bucket_replica.LooseVersion")
    @patch("plugins.modules.purefb_bucket_replica.BucketReplicaLink")
    @patch("plugins.modules.purefb_bucket_replica.get_system")
    @patch("plugins.modules.purefb_bucket_replica.AnsibleModule")
    @patch("plugins.modules.purefb_bucket_replica.HAS_PYPURECLIENT", True)
    def test_main_updates_healthy_link(
        self, mock_ansible_module, mock_get_system, mock_rl, mock_loose_version
    ):
        """A healthy link accepts a cascading change"""
        module = _module(_base_params(cascading=True))
        blade = _blade(link=_link())

        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        module.fail_json.assert_not_called()
        blade.patch_bucket_replica_links.assert_called_once()
        assert mock_rl.call_args[1]["cascading_enabled"] is True
        assert mock_rl.call_args[1]["paused"] is False
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_bucket_replica.LooseVersion")
    @patch("plugins.modules.purefb_bucket_replica.get_system")
    @patch("plugins.modules.purefb_bucket_replica.AnsibleModule")
    @patch("plugins.modules.purefb_bucket_replica.HAS_PYPURECLIENT", True)
    def test_main_healthy_link_rerun_is_idempotent(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Re-applying the current settings to a healthy link is a no-op"""
        module = _module(_base_params(target=REMOTE, credential=CRED))
        blade = _blade(link=_link())

        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        module.fail_json.assert_not_called()
        blade.patch_bucket_replica_links.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    @patch("plugins.modules.purefb_bucket_replica.LooseVersion")
    @patch("plugins.modules.purefb_bucket_replica.get_system")
    @patch("plugins.modules.purefb_bucket_replica.AnsibleModule")
    @patch("plugins.modules.purefb_bucket_replica.HAS_PYPURECLIENT", True)
    def test_main_update_fails_on_api_error(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """A failed PATCH is surfaced via fail_json"""
        module = _module(_base_params(paused=True))
        blade = _blade(link=_link(), patch_status=400)

        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.patch_bucket_replica_links.assert_called_once()
        module.fail_json.assert_called_once()
        assert (
            "Failed to update bucket replica link foo"
            in module.fail_json.call_args[1]["msg"]
        )

    @patch("plugins.modules.purefb_bucket_replica.LooseVersion")
    @patch("plugins.modules.purefb_bucket_replica.get_system")
    @patch("plugins.modules.purefb_bucket_replica.AnsibleModule")
    @patch("plugins.modules.purefb_bucket_replica.HAS_PYPURECLIENT", True)
    def test_main_pause_refused_by_array_reports_status_details(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """When the array refuses to pause an unhealthy link the details are reported"""
        module = _module(_base_params(paused=True))
        blade = _blade(link=_link(status="unhealthy"), patch_status=400)

        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.patch_bucket_replica_links.assert_called_once()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to update bucket replica link foo" in msg
        assert "Link is unhealthy: " + STATUS_DETAILS in msg

    # ---------------- main(): create / absent ----------------

    @patch("plugins.modules.purefb_bucket_replica.LooseVersion")
    @patch("plugins.modules.purefb_bucket_replica.BucketReplicaLinkPost")
    @patch("plugins.modules.purefb_bucket_replica.get_system")
    @patch("plugins.modules.purefb_bucket_replica.AnsibleModule")
    @patch("plugins.modules.purefb_bucket_replica.HAS_PYPURECLIENT", True)
    def test_main_creates_link(
        self, mock_ansible_module, mock_get_system, mock_rl_post, mock_loose_version
    ):
        """A new link is created against the connected target"""
        module = _module(
            _base_params(target=REMOTE, credential=CRED, target_bucket="Bar")
        )
        blade = _blade()

        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        module.fail_json.assert_not_called()
        blade.post_bucket_replica_links.assert_called_once()
        call_kwargs = blade.post_bucket_replica_links.call_args[1]
        assert call_kwargs["local_bucket_names"] == ["foo"]
        assert call_kwargs["remote_bucket_names"] == [REMOTE_BUCKET]
        assert call_kwargs["remote_credentials_names"] == [REMOTE + "/" + CRED]
        mock_rl_post.assert_called_once_with(cascading_enabled=False, paused=False)
        assert module.exit_json.call_args[1]["changed"] is True

    @patch("plugins.modules.purefb_bucket_replica.LooseVersion")
    @patch("plugins.modules.purefb_bucket_replica.get_system")
    @patch("plugins.modules.purefb_bucket_replica.AnsibleModule")
    @patch("plugins.modules.purefb_bucket_replica.HAS_PYPURECLIENT", True)
    def test_main_create_requires_target(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """Creating a link without a target fails"""
        module = _module(_base_params(credential=CRED))
        blade = _blade()

        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        blade.post_bucket_replica_links.assert_not_called()
        module.fail_json.assert_called_once()
        assert "target parameter is required" in module.fail_json.call_args[1]["msg"]

    @patch("plugins.modules.purefb_bucket_replica.LooseVersion")
    @patch("plugins.modules.purefb_bucket_replica.get_system")
    @patch("plugins.modules.purefb_bucket_replica.AnsibleModule")
    @patch("plugins.modules.purefb_bucket_replica.HAS_PYPURECLIENT", True)
    def test_main_absent_without_link_is_idempotent(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        """state=absent on a missing link changes nothing"""
        module = _module(_base_params(state="absent"))
        blade = _blade()

        _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)

        module.fail_json.assert_not_called()
        blade.delete_bucket_replica_links.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False
