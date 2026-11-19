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


# ---------------- realm names, letter case and refused reads ----------------

REALM = "rzaudit"
REALM_BUCKET = REALM + "::foo"
REALM_CRED = REALM + "::" + CRED
NOT_SAME_REALM = "must be in the same realm"
MIXED_SCOPE_ERROR = (
    "The local realm of the bucket does not match the local realm of the "
    "realm connection."
)


def _error(message, status_code=400):
    """An error response as the SDK returns it: errors, but no items"""
    response = Mock(spec=["status_code", "errors"])
    response.status_code = status_code
    error = Mock()
    error.message = message
    response.errors = [error]
    return response


def _message(response, default="Unknown error"):
    """What get_error_message() returns for an SDK error response"""
    return response.errors[0].message


def _realm_blade(link=None):
    """The array holding bucket rzaudit::foo and credential rzaudit::cred_1"""
    blade = _blade(link=link)
    blade.get_buckets.return_value = _response([_ref(REALM_BUCKET)])
    blade.get_object_store_remote_credentials.return_value = _response(
        [_ref(REMOTE + "/" + REALM_CRED)]
    )
    return blade


@patch("plugins.modules.purefb_bucket_replica.get_error_message", _message)
@patch("plugins.modules.purefb_bucket_replica.HAS_PYPURECLIENT", True)
@patch("plugins.modules.purefb_bucket_replica.LooseVersion")
@patch("plugins.modules.purefb_bucket_replica.BucketReplicaLinkPost")
@patch("plugins.modules.purefb_bucket_replica.ReferenceWritable")
@patch("plugins.modules.purefb_bucket_replica.BucketReplicaLink")
@patch("plugins.modules.purefb_bucket_replica.get_system")
@patch("plugins.modules.purefb_bucket_replica.AnsibleModule")
def _main(
    mock_ansible_module,
    mock_get_system,
    mock_rl,
    mock_ref,
    mock_rl_post,
    mock_loose_version,
    params=None,
    blade=None,
    check_mode=False,
):
    """Run main() against blade; return the module and the patched names"""
    module = _module(params, check_mode=check_mode)
    _run(module, blade, mock_ansible_module, mock_get_system, mock_loose_version)
    mocks = {
        "get_system": mock_get_system,
        "link": mock_rl,
        "reference": mock_ref,
        "post": mock_rl_post,
    }
    return module, mocks


def _failure(module):
    """The message of the one fail_json call of a run"""
    module.fail_json.assert_called_once()
    return module.fail_json.call_args[1]["msg"]


def _no_write(blade):
    """Nothing was created, changed or deleted"""
    blade.post_bucket_replica_links.assert_not_called()
    blade.patch_bucket_replica_links.assert_not_called()
    blade.delete_bucket_replica_links.assert_not_called()


class TestPurefbBucketReplicaRealm:
    """A replica link follows the realm of its local bucket"""

    def test_realm_of(self):
        """The realm is the prefix before the last separator"""
        from plugins.modules.purefb_bucket_replica import _realm_of

        assert _realm_of("rzaudit::foo") == "rzaudit"
        assert _realm_of("foo") == ""
        assert _realm_of("rzaudit::cred_1") == "rzaudit"

    def test_main_creates_realm_link(self):
        """A realm bucket with a credential of its realm is created"""
        blade = _realm_blade()
        module, mocks = _main(
            params=_base_params(
                name=REALM_BUCKET,
                target=REMOTE,
                credential=REALM_CRED,
                target_bucket="bar",
                paused=True,
            ),
            blade=blade,
        )

        module.fail_json.assert_not_called()
        call_kwargs = blade.post_bucket_replica_links.call_args[1]
        assert call_kwargs["local_bucket_names"] == [REALM_BUCKET]
        assert call_kwargs["remote_bucket_names"] == [REMOTE_BUCKET]
        assert call_kwargs["remote_credentials_names"] == [REMOTE + "/" + REALM_CRED]
        blade.get_object_store_remote_credentials.assert_called_once_with(
            names=[REMOTE + "/" + REALM_CRED]
        )
        mocks["post"].assert_called_once_with(cascading_enabled=False, paused=True)
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_create_refuses_realm_bucket_with_array_credential(self):
        """A realm bucket and an array-level credential are never sent"""
        blade = _realm_blade()
        blade.get_object_store_remote_credentials.return_value = _response(
            [_ref(REMOTE + "/" + CRED)]
        )
        module, mocks = _main(
            params=_base_params(name=REALM_BUCKET, target=REMOTE, credential=CRED),
            blade=blade,
        )

        msg = _failure(module)
        assert NOT_SAME_REALM in msg
        assert REALM_BUCKET in msg
        assert "rzaudit::<credential>" in msg
        _no_write(blade)
        # decided from the names of the task, before the array is asked
        mocks["get_system"].assert_not_called()
        module.exit_json.assert_not_called()

    def test_main_create_refuses_mixed_scope_in_check_mode(self):
        """Check mode reports the refusal instead of a change"""
        blade = _realm_blade()
        module, mocks = _main(
            params=_base_params(name=REALM_BUCKET, target=REMOTE, credential=CRED),
            blade=blade,
            check_mode=True,
        )

        assert NOT_SAME_REALM in _failure(module)
        module.exit_json.assert_not_called()
        _no_write(blade)

    def test_main_create_refuses_array_bucket_with_realm_credential(self):
        """An array-level bucket and a realm credential are never sent"""
        blade = _blade()
        blade.get_object_store_remote_credentials.return_value = _response(
            [_ref(REMOTE + "/" + REALM_CRED)]
        )
        module, mocks = _main(
            params=_base_params(target=REMOTE, credential=REALM_CRED), blade=blade
        )

        msg = _failure(module)
        assert NOT_SAME_REALM in msg
        assert "rzaudit::<bucket>" in msg
        _no_write(blade)
        module.exit_json.assert_not_called()

    def test_main_refuses_credential_of_another_realm(self):
        """Two different realms are not the same realm"""
        blade = _realm_blade()
        module, mocks = _main(
            params=_base_params(
                name=REALM_BUCKET, target=REMOTE, credential="other::" + CRED
            ),
            blade=blade,
        )

        assert NOT_SAME_REALM in _failure(module)
        _no_write(blade)

    def test_main_update_refuses_bare_credential_on_realm_link(self):
        """A realm link is not re-pointed at an array-level credential"""
        blade = _realm_blade(link=_link(paused=True, credential=REALM_CRED))
        blade.get_object_store_remote_credentials.return_value = _response(
            [_ref(REMOTE + "/" + CRED)]
        )
        module, mocks = _main(
            params=_base_params(name=REALM_BUCKET, credential=CRED, paused=True),
            blade=blade,
        )

        assert NOT_SAME_REALM in _failure(module)
        _no_write(blade)
        module.exit_json.assert_not_called()

    def test_main_update_refuses_bare_credential_in_check_mode(self):
        """Check mode refuses the mixed pair on an existing link too"""
        blade = _realm_blade(link=_link(paused=True, credential=REALM_CRED))
        module, mocks = _main(
            params=_base_params(name=REALM_BUCKET, credential=CRED, paused=True),
            blade=blade,
            check_mode=True,
        )

        assert NOT_SAME_REALM in _failure(module)
        module.exit_json.assert_not_called()

    def test_main_realm_prefix_case_is_not_a_scope_difference(self):
        """The realm prefix is compared without regard to case"""
        blade = _realm_blade(link=_link(paused=True, credential=REALM_CRED))
        module, mocks = _main(
            params=_base_params(
                name="RZAUDIT::foo", credential="Rzaudit::" + CRED, paused=True
            ),
            blade=blade,
        )

        module.fail_json.assert_not_called()
        _no_write(blade)
        assert module.exit_json.call_args[1]["changed"] is False

    def test_main_pauses_realm_link_by_name(self):
        """With only the name the credential of the link is kept"""
        blade = _realm_blade(link=_link(credential=REALM_CRED))
        module, mocks = _main(
            params=_base_params(name=REALM_BUCKET, paused=True), blade=blade
        )

        module.fail_json.assert_not_called()
        call_kwargs = blade.patch_bucket_replica_links.call_args[1]
        assert call_kwargs["local_bucket_names"] == [REALM_BUCKET]
        mocks["reference"].assert_called_once_with(name=REMOTE + "/" + REALM_CRED)
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_changes_credential_of_realm_link(self):
        """Another credential of the same realm is sent"""
        blade = _realm_blade(link=_link(paused=True, credential=REALM_CRED))
        blade.get_object_store_remote_credentials.return_value = _response(
            [_ref(REMOTE + "/" + REALM + "::cred_2")]
        )
        module, mocks = _main(
            params=_base_params(
                name=REALM_BUCKET, credential=REALM + "::cred_2", paused=True
            ),
            blade=blade,
        )

        module.fail_json.assert_not_called()
        mocks["reference"].assert_called_once_with(name=REMOTE + "/rzaudit::cred_2")
        assert module.exit_json.call_args[1]["changed"] is True

    def test_main_absent_ignores_the_credential(self):
        """Deleting a link needs no credential, so none is checked"""
        blade = _realm_blade(link=_link(credential=REALM_CRED))
        module, mocks = _main(
            params=_base_params(name=REALM_BUCKET, credential=CRED, state="absent"),
            blade=blade,
        )

        module.fail_json.assert_not_called()
        blade.delete_bucket_replica_links.assert_called_once_with(
            remote_names=[REMOTE],
            local_bucket_names=[REALM_BUCKET],
            remote_bucket_names=[REMOTE_BUCKET],
        )
        assert module.exit_json.call_args[1]["changed"] is True

    # ---------------- letter case ----------------

    def test_main_credential_case_is_not_drift(self):
        """A credential written in another case is the credential of the link"""
        blade = _blade(link=_link(paused=True))
        module, mocks = _main(
            params=_base_params(credential=CRED.upper(), paused=True), blade=blade
        )

        module.fail_json.assert_not_called()
        blade.patch_bucket_replica_links.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_main_credential_case_keeps_the_stored_name(self):
        """Another change sends the credential as the array stores it"""
        blade = _blade(link=_link())
        module, mocks = _main(
            params=_base_params(credential=CRED.upper(), paused=True), blade=blade
        )

        module.fail_json.assert_not_called()
        blade.patch_bucket_replica_links.assert_called_once()
        mocks["reference"].assert_called_once_with(name=REMOTE + "/" + CRED)

    def test_blocked_changes_credential_case_is_not_a_change(self):
        """An unhealthy link is not refused for the case of its credential"""
        module = Mock()
        module.params = _base_params(paused=True, credential=CRED.upper())
        assert get_unhealthy_blocked_changes(module, _link(status="unhealthy")) == []

    def test_main_target_case_is_ignored(self):
        """A target written in another case is the connected target"""
        blade = _blade()
        module, mocks = _main(
            params=_base_params(
                target=REMOTE.upper(), credential=CRED, target_bucket="bar"
            ),
            blade=blade,
        )

        module.fail_json.assert_not_called()
        blade.get_object_store_remote_credentials.assert_called_once_with(
            names=[REMOTE + "/" + CRED]
        )
        blade.post_bucket_replica_links.assert_called_once()

    def test_main_s3_target_case_is_ignored(self):
        """The same holds for an S3 target"""
        blade = _blade()
        blade.get_array_connections.return_value = _response([])
        target = _ref("s3target")
        target.status = "connected"
        blade.get_targets.return_value = _response([target])
        blade.get_object_store_remote_credentials.return_value = _response(
            [_ref("s3target/" + CRED)]
        )
        module, mocks = _main(
            params=_base_params(target="S3Target", credential=CRED), blade=blade
        )

        module.fail_json.assert_not_called()
        call_kwargs = blade.post_bucket_replica_links.call_args[1]
        assert call_kwargs["remote_credentials_names"] == ["s3target/" + CRED]

    # ---------------- reads that do not answer 200 ----------------

    def test_main_create_failure_reports_the_array_error(self):
        """A refused create carries the reason the array gave"""
        blade = _realm_blade()
        blade.post_bucket_replica_links.return_value = _error(MIXED_SCOPE_ERROR)
        module, mocks = _main(
            params=_base_params(
                name=REALM_BUCKET, target=REMOTE, credential=REALM_CRED
            ),
            blade=blade,
        )

        msg = _failure(module)
        assert "Failed to create bucket replica link rzaudit::foo." in msg
        assert MIXED_SCOPE_ERROR in msg

    def test_main_absent_missing_bucket_is_unchanged(self):
        """A bucket that does not exist has no link to delete"""
        blade = _blade()
        blade.get_bucket_replica_links.return_value = _error("Bucket does not exist.")
        module, mocks = _main(params=_base_params(state="absent"), blade=blade)

        module.fail_json.assert_not_called()
        _no_write(blade)
        assert module.exit_json.call_args[1]["changed"] is False

    def test_main_refused_link_read_is_reported(self):
        """A refused read of the link is not read as no link"""
        blade = _blade()
        blade.get_bucket_replica_links.return_value = _error("Operation not permitted.")
        module, mocks = _main(params=_base_params(state="absent"), blade=blade)

        msg = _failure(module)
        assert "Failed to get replica link of bucket foo." in msg
        assert "Operation not permitted." in msg
        _no_write(blade)
        module.exit_json.assert_not_called()

    def test_main_missing_bucket(self):
        """A bucket the array does not know is reported as missing"""
        blade = _blade()
        blade.get_bucket_replica_links.return_value = _error("Bucket does not exist.")
        blade.get_buckets.return_value = _error("Bucket does not exist.")
        module, mocks = _main(
            params=_base_params(target=REMOTE, credential=CRED), blade=blade
        )

        assert _failure(module) == "Selected local bucket foo does not exist."
        _no_write(blade)

    def test_main_refused_bucket_read_is_reported(self):
        """A refused read of the bucket is not read as a missing bucket"""
        blade = _blade()
        blade.get_buckets.return_value = _error("Operation not permitted.")
        module, mocks = _main(
            params=_base_params(target=REMOTE, credential=CRED), blade=blade
        )

        msg = _failure(module)
        assert "Failed to get bucket foo." in msg
        assert "Operation not permitted." in msg
        _no_write(blade)

    def test_main_missing_credential(self):
        """A credential the array does not know is reported as missing"""
        blade = _blade()
        blade.get_object_store_remote_credentials.return_value = _error(
            "Remote credentials does not exist."
        )
        module, mocks = _main(
            params=_base_params(target=REMOTE, credential=CRED), blade=blade
        )

        assert _failure(module) == (
            "Selected remote credential cred_1 does not exist for target arrayb."
        )
        _no_write(blade)

    def test_main_refused_credential_read_is_reported(self):
        """A refused read of the credential is not read as a missing one"""
        blade = _blade()
        blade.get_object_store_remote_credentials.return_value = _error(
            "Operation not permitted."
        )
        module, mocks = _main(
            params=_base_params(target=REMOTE, credential=CRED), blade=blade
        )

        msg = _failure(module)
        assert "Failed to get remote credential arrayb/cred_1." in msg
        assert "Operation not permitted." in msg
        _no_write(blade)

    def test_main_refused_array_connections_read_is_reported(self):
        """A refused read of the array connections fails with its message"""
        blade = _blade()
        blade.get_array_connections.return_value = _error("Operation not permitted.")
        module, mocks = _main(
            params=_base_params(target=REMOTE, credential=CRED), blade=blade
        )

        msg = _failure(module)
        assert "Failed to get array connections." in msg
        assert "Operation not permitted." in msg
        _no_write(blade)

    def test_main_refused_targets_read_is_reported(self):
        """A refused read of the targets fails with its message"""
        blade = _blade()
        blade.get_array_connections.return_value = _response([])
        blade.get_targets.return_value = _error("Operation not permitted.")
        module, mocks = _main(
            params=_base_params(target=REMOTE, credential=CRED), blade=blade
        )

        msg = _failure(module)
        assert "Failed to get targets." in msg
        assert "Operation not permitted." in msg
        _no_write(blade)
