# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for the purefb_fleet module."""

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
sys.modules["pypureclient.flasharray"] = MagicMock()
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

from ansible.module_utils.compat.version import LooseVersion as RealLooseVersion

from plugins.modules.purefb_fleet import (
    main,
    _current_fleet_name,
    _get_fleet_members,
    _remote_array_name,
    _batch_entry,
    _batch_result_dict,
    _wait_for_join,
)

MODULE = "plugins.modules.purefb_fleet"


def _base_params(**overrides):
    params = {
        "name": None,
        "state": "present",
        "member_url": None,
        "member_api": None,
        "rename": None,
        "members": None,
        "member_username": None,
        "member_password": None,
        "validate_certificates": True,
        "wait": True,
        "timeout": 300,
        "member_name": None,
        "disable_warnings": False,
    }
    params.update(overrides)
    return params


def _response(items=None, status_code=200):
    response = Mock()
    response.status_code = status_code
    response.items = items or []
    response.errors = []
    return response


def _fleet(name="fleet1", is_local=True):
    fleet = Mock()
    fleet.name = name
    fleet.is_local = is_local
    return fleet


def _member(name, status="joined", is_local=False, status_details=None):
    member = Mock()
    member.member = Mock()
    member.member.name = name
    member.member.is_local = is_local
    member.status = status
    member.status_details = status_details
    return member


def _batch_result(address, name=None, status="joining", details=None, cert=None):
    result = Mock()
    result.management_address = address
    result.member = None
    if name:
        result.member = Mock()
        result.member.name = name
    result.status = status
    result.status_details = details
    result.certificate_details = cert
    return result


def _module(params, check_mode=False):
    module = Mock()
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.params = params
    module.check_mode = check_mode
    return module


def _run_main(params, blade, api_version="2.30", check_mode=False, time_values=None):
    """Run main() with the module, SDK session and version patched"""
    module = _module(params, check_mode)
    with patch(MODULE + ".AnsibleModule", return_value=module), patch(
        MODULE + ".get_system", return_value=blade
    ), patch(MODULE + ".get_rest_api_version", return_value=api_version), patch(
        MODULE + ".LooseVersion", RealLooseVersion
    ), patch(
        MODULE + ".HAS_PYPURECLIENT", True
    ), patch(
        MODULE + ".time"
    ) as mock_time:
        if time_values:
            mock_time.time.side_effect = time_values
        else:
            mock_time.time.return_value = 0.0
        try:
            main()
        except SystemExit:
            pass
    return module


class TestFleetHelpers:
    """Helper-function unit tests"""

    def test_current_fleet_name_returns_local_fleet(self):
        module = _module(_base_params())
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        assert _current_fleet_name(module, blade) == "fleet1"

    def test_current_fleet_name_honours_matching_name(self):
        module = _module(_base_params(name="fleet1"))
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        assert _current_fleet_name(module, blade) == "fleet1"

    def test_current_fleet_name_fails_on_mismatch(self):
        module = _module(_base_params(name="other"))
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        try:
            _current_fleet_name(module, blade)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "member of fleet fleet1" in module.fail_json.call_args[1]["msg"]

    def test_current_fleet_name_fails_without_fleet(self):
        module = _module(_base_params())
        blade = Mock()
        blade.get_fleets.return_value = _response([])
        try:
            _current_fleet_name(module, blade)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "not a member of a fleet" in module.fail_json.call_args[1]["msg"]

    def test_current_fleet_name_fails_on_api_error(self):
        module = _module(_base_params())
        blade = Mock()
        blade.get_fleets.return_value = _response([], status_code=400)
        try:
            _current_fleet_name(module, blade)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "Failed to read fleets" in module.fail_json.call_args[1]["msg"]

    def test_get_fleet_members_keys_by_name(self):
        module = _module(_base_params())
        blade = Mock()
        blade.get_fleets_members.return_value = _response(
            [_member("local", is_local=True), _member("array2", "joining")]
        )
        members = _get_fleet_members(module, blade)
        assert sorted(members) == ["array2", "local"]
        assert members["array2"].status == "joining"

    def test_get_fleet_members_fails_on_api_error(self):
        module = _module(_base_params())
        blade = Mock()
        blade.get_fleets_members.return_value = _response([], status_code=400)
        try:
            _get_fleet_members(module, blade)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "Failed to list fleet members" in module.fail_json.call_args[1]["msg"]

    @patch(MODULE + ".ReferenceWritable")
    @patch(MODULE + ".AuthenticationCredentials")
    @patch(MODULE + ".FleetMemberBatchPost")
    def test_batch_entry_uses_member_credentials(self, mock_post, mock_creds, mock_ref):
        module = _module(_base_params(member_username="dflt", member_password="dpw"))
        _batch_entry(
            module,
            {
                "management_address": "10.0.0.2",
                "name": "array2",
                "username": "admin",
                "password": "pw",
                "ca_certificate": None,
                "ca_certificate_group": None,
            },
        )
        mock_creds.assert_called_once_with(username="admin", password="pw")
        mock_ref.assert_not_called()
        kwargs = mock_post.call_args[1]
        assert kwargs["management_address"] == "10.0.0.2"
        assert "ca_certificate" not in kwargs
        assert "ca_certificate_group" not in kwargs

    @patch(MODULE + ".ReferenceWritable")
    @patch(MODULE + ".AuthenticationCredentials")
    @patch(MODULE + ".FleetMemberBatchPost")
    def test_batch_entry_defaults_credentials_and_ca_certificate(
        self, mock_post, mock_creds, mock_ref
    ):
        module = _module(_base_params(member_username="dflt", member_password="dpw"))
        _batch_entry(
            module,
            {
                "management_address": "10.0.0.2",
                "name": None,
                "username": None,
                "password": None,
                "ca_certificate": "ca1",
                "ca_certificate_group": None,
            },
        )
        mock_creds.assert_called_once_with(username="dflt", password="dpw")
        mock_ref.assert_called_once_with(name="ca1", resource_type="certificates")
        assert "ca_certificate" in mock_post.call_args[1]

    @patch(MODULE + ".ReferenceWritable")
    @patch(MODULE + ".AuthenticationCredentials")
    @patch(MODULE + ".FleetMemberBatchPost")
    def test_batch_entry_ca_certificate_group(self, mock_post, mock_creds, mock_ref):
        module = _module(_base_params())
        _batch_entry(
            module,
            {
                "management_address": "10.0.0.2",
                "name": None,
                "username": "admin",
                "password": "pw",
                "ca_certificate": None,
                "ca_certificate_group": "grp1",
            },
        )
        mock_ref.assert_called_once_with(
            name="grp1", resource_type="certificate-groups"
        )
        assert "ca_certificate_group" in mock_post.call_args[1]

    @patch(MODULE + ".FleetMemberBatchPost")
    def test_batch_entry_fails_without_credentials(self, mock_post):
        module = _module(_base_params())
        try:
            _batch_entry(
                module,
                {
                    "management_address": "10.0.0.2",
                    "name": None,
                    "username": "admin",
                    "password": None,
                    "ca_certificate": None,
                    "ca_certificate_group": None,
                },
            )
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "needs a username and password" in module.fail_json.call_args[1]["msg"]
        mock_post.assert_not_called()

    def test_batch_result_dict_flattens_member_and_certificate(self):
        cert = Mock()
        cert.issuer = "CN=ca"
        cert.subject = "CN=array2"
        cert.not_before = 1
        cert.not_after = 2
        info = _batch_result_dict(
            _batch_result("10.0.0.2", "array2", "joining", "sent", cert)
        )
        assert info == {
            "management_address": "10.0.0.2",
            "member": "array2",
            "status": "joining",
            "status_details": "sent",
            "certificate_details": {
                "issuer": "CN=ca",
                "subject": "CN=array2",
                "not_before": 1,
                "not_after": 2,
            },
        }

    def test_batch_result_dict_without_member(self):
        info = _batch_result_dict(
            _batch_result("10.0.0.2", None, "failed", "login failed")
        )
        assert info["member"] is None
        assert info["status"] == "failed"
        assert info["certificate_details"] is None

    @patch(MODULE + ".time")
    def test_wait_for_join_polls_until_joined(self, mock_time):
        mock_time.time.return_value = 0.0
        module = _module(_base_params(timeout=300))
        blade = Mock()
        blade.get_fleets_members.side_effect = [
            _response([_member("local", is_local=True), _member("array2", "joining")]),
            _response([_member("local", is_local=True), _member("array2", "joined")]),
        ]
        results = [
            {
                "management_address": "10.0.0.2",
                "member": "array2",
                "status": "joining",
                "status_details": None,
                "certificate_details": None,
            }
        ]
        out = _wait_for_join(module, blade, ["array2"], {"local"}, results)
        assert out[0]["status"] == "joined"
        assert blade.get_fleets_members.call_count == 2
        mock_time.sleep.assert_called_once_with(5)
        module.fail_json.assert_not_called()

    @patch(MODULE + ".time")
    def test_wait_for_join_times_out_with_details(self, mock_time):
        mock_time.time.side_effect = [0.0, 1000.0]
        module = _module(_base_params(timeout=300))
        blade = Mock()
        blade.get_fleets_members.return_value = _response(
            [_member("array2", "joining", status_details="waiting for target")]
        )
        results = [
            {
                "management_address": "10.0.0.2",
                "member": "array2",
                "status": "joining",
                "status_details": None,
                "certificate_details": None,
            }
        ]
        try:
            _wait_for_join(module, blade, ["array2"], {"local"}, results)
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Timed out after 300s" in msg
        assert "array2 (joining: waiting for target)" in msg
        assert module.fail_json.call_args[1]["members"] == results

    @patch(MODULE + ".time")
    def test_wait_for_join_tracks_unidentified_targets(self, mock_time):
        mock_time.time.return_value = 0.0
        module = _module(_base_params(timeout=300))
        blade = Mock()
        blade.get_fleets_members.side_effect = [
            _response([_member("mystery", "joining")]),
            _response([_member("mystery", "joined")]),
        ]
        results = [
            {
                "management_address": "10.0.0.9",
                "member": None,
                "status": "joining",
                "status_details": None,
                "certificate_details": None,
            }
        ]
        out = _wait_for_join(module, blade, [], {"local"}, results)
        assert blade.get_fleets_members.call_count == 2
        module.fail_json.assert_not_called()
        # the single new member is matched to the unnamed target
        assert out[0]["member"] == "mystery"
        assert out[0]["status"] == "joined"

    @patch(MODULE + ".time")
    def test_wait_for_join_ignores_members_already_joining_before(self, mock_time):
        mock_time.time.return_value = 0.0
        module = _module(_base_params(timeout=300))
        blade = Mock()
        blade.get_fleets_members.return_value = _response(
            [
                _member("local", is_local=True),
                _member("other", "joining"),
                _member("array2", "joined"),
            ]
        )
        results = [
            {
                "management_address": "10.0.0.2",
                "member": "array2",
                "status": "joining",
                "status_details": None,
                "certificate_details": None,
            },
            {
                "management_address": "10.0.0.9",
                "member": None,
                "status": "joining",
                "status_details": None,
                "certificate_details": None,
            },
        ]
        out = _wait_for_join(module, blade, ["array2"], {"local", "other"}, results)
        # "other" was joining before the request: not waited for, not matched
        assert blade.get_fleets_members.call_count == 1
        mock_time.sleep.assert_not_called()
        assert out[0]["status"] == "joined"
        assert out[1]["member"] is None
        assert out[1]["status"] == "joining"

    @patch(MODULE + ".time")
    def test_wait_for_join_leaves_ambiguous_targets_unmatched(self, mock_time):
        mock_time.time.return_value = 0.0
        module = _module(_base_params(timeout=300))
        blade = Mock()
        blade.get_fleets_members.return_value = _response(
            [_member("new1", "joined"), _member("new2", "joined")]
        )
        results = [
            {
                "management_address": "10.0.0.8",
                "member": None,
                "status": "joining",
                "status_details": None,
                "certificate_details": None,
            },
            {
                "management_address": "10.0.0.9",
                "member": None,
                "status": "joining",
                "status_details": None,
                "certificate_details": None,
            },
        ]
        out = _wait_for_join(module, blade, [], set(), results)
        module.fail_json.assert_not_called()
        assert [r["member"] for r in out] == [None, None]
        assert [r["status"] for r in out] == ["joining", "joining"]


class TestFleetBatchMain:
    """main() flows for members (batch join)"""

    def _members(self):
        return [
            {
                "management_address": "10.0.0.2",
                "name": "array2",
                "username": None,
                "password": None,
                "ca_certificate": None,
                "ca_certificate_group": None,
            },
            {
                "management_address": "10.0.0.3",
                "name": "array3",
                "username": None,
                "password": None,
                "ca_certificate": None,
                "ca_certificate_group": None,
            },
        ]

    @patch(MODULE + ".ReferenceWritable")
    @patch(MODULE + ".AuthenticationCredentials")
    @patch(MODULE + ".FleetMemberBatchPost")
    def test_batch_join_two_targets_and_wait(self, mock_post, mock_creds, mock_ref):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        local = _member("local", is_local=True)
        blade.get_fleets_members.side_effect = [
            _response([local]),
            _response(
                [local, _member("array2", "joining"), _member("array3", "joined")]
            ),
            _response(
                [local, _member("array2", "joined"), _member("array3", "joined")]
            ),
        ]
        blade.post_fleets_members_batch.return_value = _response(
            [
                _batch_result("10.0.0.2", "array2", "joining"),
                _batch_result("10.0.0.3", "array3", "joining"),
            ]
        )
        module = _run_main(
            _base_params(
                name="fleet1",
                members=self._members(),
                member_username="admin",
                member_password="pw",
                validate_certificates=False,
            ),
            blade,
        )
        blade.post_fleets_members_batch.assert_called_once()
        kwargs = blade.post_fleets_members_batch.call_args[1]
        assert kwargs["fleet_names"] == ["fleet1"]
        assert kwargs["validate_target_certificates"] is False
        assert len(kwargs["fleet_member_batch_post"]) == 2
        assert mock_post.call_count == 2
        assert mock_creds.call_count == 2
        module.exit_json.assert_called_once()
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert [m["status"] for m in result["members"]] == ["joined", "joined"]
        assert blade.get_fleets_members.call_count == 3

    @patch(MODULE + ".AuthenticationCredentials")
    @patch(MODULE + ".FleetMemberBatchPost")
    def test_batch_join_skips_members_already_joined(self, mock_post, mock_creds):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        blade.get_fleets_members.return_value = _response(
            [
                _member("local", is_local=True),
                _member("array2", "joined"),
                _member("array3", "joining"),
            ]
        )
        module = _run_main(
            _base_params(
                members=self._members(), member_username="admin", member_password="pw"
            ),
            blade,
        )
        blade.post_fleets_members_batch.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False, members=[])

    @patch(MODULE + ".AuthenticationCredentials")
    @patch(MODULE + ".FleetMemberBatchPost")
    def test_batch_join_only_sends_missing_members(self, mock_post, mock_creds):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        local = _member("local", is_local=True)
        blade.get_fleets_members.side_effect = [
            _response([local, _member("array2", "joined")]),
            _response([local, _member("array2", "joined"), _member("array3")]),
        ]
        blade.post_fleets_members_batch.return_value = _response(
            [_batch_result("10.0.0.3", "array3", "joining")]
        )
        module = _run_main(
            _base_params(
                members=self._members(), member_username="admin", member_password="pw"
            ),
            blade,
        )
        kwargs = blade.post_fleets_members_batch.call_args[1]
        assert len(kwargs["fleet_member_batch_post"]) == 1
        assert mock_post.call_args[1]["management_address"] == "10.0.0.3"
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["members"][0]["member"] == "array3"
        assert result["members"][0]["status"] == "joined"

    def test_members_with_other_states_refused_before_any_call(self):
        for state in ["absent", "create"]:
            for check_mode in [False, True]:
                blade = Mock()
                blade.get_fleets.return_value = _response([_fleet("fleet1")])
                module = _run_main(
                    _base_params(
                        state=state,
                        members=self._members(),
                        member_username="admin",
                        member_password="pw",
                    ),
                    blade,
                    check_mode=check_mode,
                )
                module.fail_json.assert_called_once()
                msg = module.fail_json.call_args[1]["msg"]
                assert "members is only valid with state=present" in msg
                blade.get_fleets.assert_not_called()
                blade.delete_fleets.assert_not_called()
                blade.post_fleets_members_batch.assert_not_called()
                module.exit_json.assert_not_called()

    def test_batch_join_check_mode_without_credentials_fails(self):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        blade.get_fleets_members.return_value = _response(
            [_member("local", is_local=True)]
        )
        module = _run_main(
            _base_params(members=self._members()), blade, check_mode=True
        )
        module.fail_json.assert_called_once()
        assert "needs a username and password" in module.fail_json.call_args[1]["msg"]
        blade.post_fleets_members_batch.assert_not_called()
        module.exit_json.assert_not_called()

    @patch(MODULE + ".AuthenticationCredentials")
    @patch(MODULE + ".FleetMemberBatchPost")
    def test_batch_join_resolves_unnamed_target_after_wait(self, mock_post, mock_creds):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        local = _member("local", is_local=True)
        blade.get_fleets_members.side_effect = [
            _response([local]),
            _response([local, _member("mystery", "joined")]),
        ]
        blade.post_fleets_members_batch.return_value = _response(
            [_batch_result("10.0.0.2", None, "joining")]
        )
        module = _run_main(
            _base_params(
                members=self._members()[:1],
                member_username="admin",
                member_password="pw",
            ),
            blade,
        )
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["members"][0]["member"] == "mystery"
        assert result["members"][0]["status"] == "joined"

    def test_batch_join_check_mode_reports_targets(self):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        blade.get_fleets_members.return_value = _response(
            [_member("local", is_local=True)]
        )
        module = _run_main(
            _base_params(
                members=self._members(), member_username="admin", member_password="pw"
            ),
            blade,
            check_mode=True,
        )
        blade.post_fleets_members_batch.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert [m["member"] for m in result["members"]] == ["array2", "array3"]
        assert [m["status"] for m in result["members"]] == [None, None]

    @patch(MODULE + ".AuthenticationCredentials")
    @patch(MODULE + ".FleetMemberBatchPost")
    def test_batch_join_without_wait_returns_joining(self, mock_post, mock_creds):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        blade.get_fleets_members.return_value = _response(
            [_member("local", is_local=True)]
        )
        blade.post_fleets_members_batch.return_value = _response(
            [
                _batch_result("10.0.0.2", "array2", "joining"),
                _batch_result("10.0.0.3", "array3", "joining"),
            ]
        )
        module = _run_main(
            _base_params(
                members=self._members(),
                member_username="admin",
                member_password="pw",
                wait=False,
            ),
            blade,
        )
        assert blade.get_fleets_members.call_count == 1
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert [m["status"] for m in result["members"]] == ["joining", "joining"]

    @patch(MODULE + ".AuthenticationCredentials")
    @patch(MODULE + ".FleetMemberBatchPost")
    def test_batch_join_fails_when_a_target_fails(self, mock_post, mock_creds):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        blade.get_fleets_members.return_value = _response(
            [_member("local", is_local=True)]
        )
        blade.post_fleets_members_batch.return_value = _response(
            [
                _batch_result("10.0.0.2", "array2", "joining"),
                _batch_result("10.0.0.3", None, "failed", "Authentication failed"),
            ]
        )
        module = _run_main(
            _base_params(
                members=self._members(), member_username="admin", member_password="pw"
            ),
            blade,
        )
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "1 of 2 targets failed to join fleet fleet1" in msg
        assert "10.0.0.3 (Authentication failed)" in msg
        assert len(module.fail_json.call_args[1]["members"]) == 2
        # no polling after a failure
        assert blade.get_fleets_members.call_count == 1

    @patch(MODULE + ".AuthenticationCredentials")
    @patch(MODULE + ".FleetMemberBatchPost")
    def test_batch_join_fails_on_api_error(self, mock_post, mock_creds):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        blade.get_fleets_members.return_value = _response(
            [_member("local", is_local=True)]
        )
        blade.post_fleets_members_batch.return_value = _response([], status_code=400)
        module = _run_main(
            _base_params(
                members=self._members(), member_username="admin", member_password="pw"
            ),
            blade,
        )
        module.fail_json.assert_called_once()
        assert (
            "Batch join to fleet fleet1 failed" in module.fail_json.call_args[1]["msg"]
        )

    def test_batch_join_requires_rest_2_27(self):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        module = _run_main(
            _base_params(
                members=self._members(), member_username="admin", member_password="pw"
            ),
            blade,
            api_version="2.26",
        )
        module.fail_json.assert_called_once()
        assert "REST API 2.27" in module.fail_json.call_args[1]["msg"]
        blade.get_fleets.assert_not_called()
        blade.post_fleets_members_batch.assert_not_called()

    def test_batch_join_fails_without_fleet(self):
        blade = Mock()
        blade.get_fleets.return_value = _response([])
        module = _run_main(
            _base_params(
                members=self._members(), member_username="admin", member_password="pw"
            ),
            blade,
        )
        module.fail_json.assert_called_once()
        assert "not a member of a fleet" in module.fail_json.call_args[1]["msg"]
        blade.post_fleets_members_batch.assert_not_called()

    @patch(MODULE + ".AuthenticationCredentials")
    @patch(MODULE + ".FleetMemberBatchPost")
    def test_batch_join_times_out(self, mock_post, mock_creds):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        local = _member("local", is_local=True)
        blade.get_fleets_members.side_effect = [
            _response([local]),
            _response([local, _member("array2", "joining")]),
        ]
        blade.post_fleets_members_batch.return_value = _response(
            [_batch_result("10.0.0.2", "array2", "joining")]
        )
        module = _run_main(
            _base_params(
                members=self._members()[:1],
                member_username="admin",
                member_password="pw",
                timeout=60,
            ),
            blade,
            time_values=[0.0, 100.0],
        )
        module.fail_json.assert_called_once()
        assert "Timed out after 60s" in module.fail_json.call_args[1]["msg"]


class TestFleetMemberNameMain:
    """main() flows for state=absent with member_name"""

    def test_member_name_with_other_states_refused_before_any_call(self):
        for state in ["present", "create"]:
            blade = Mock()
            blade.get_fleets.return_value = _response([_fleet("fleet1")])
            module = _run_main(_base_params(state=state, member_name=["array2"]), blade)
            module.fail_json.assert_called_once()
            msg = module.fail_json.call_args[1]["msg"]
            assert "member_name is only valid with state=absent" in msg
            blade.get_fleets.assert_not_called()
            blade.delete_fleets_members.assert_not_called()
            blade.post_fleets_fleet_key.assert_not_called()
            module.exit_json.assert_not_called()

    def test_remove_joined_member_by_name(self):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        blade.get_fleets_members.return_value = _response(
            [_member("local", is_local=True), _member("array2", "joined")]
        )
        blade.delete_fleets_members.return_value = _response([])
        module = _run_main(_base_params(state="absent", member_name=["array2"]), blade)
        blade.delete_fleets_members.assert_called_once_with(member_names=["array2"])
        module.exit_json.assert_called_once_with(changed=True)

    def test_remove_joining_member_uses_unreachable(self):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        blade.get_fleets_members.return_value = _response(
            [_member("local", is_local=True), _member("array2", "joining")]
        )
        blade.delete_fleets_members.return_value = _response([])
        module = _run_main(_base_params(state="absent", member_name=["array2"]), blade)
        blade.delete_fleets_members.assert_called_once_with(
            member_names=["array2"], unreachable=True
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_remove_missing_member_is_idempotent(self):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        blade.get_fleets_members.return_value = _response(
            [_member("local", is_local=True)]
        )
        module = _run_main(_base_params(state="absent", member_name=["array2"]), blade)
        blade.delete_fleets_members.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_remove_without_fleet_is_idempotent(self):
        blade = Mock()
        blade.get_fleets.return_value = _response([])
        blade.get_fleets_members.return_value = _response([])
        module = _run_main(_base_params(state="absent", member_name=["array2"]), blade)
        blade.delete_fleets_members.assert_not_called()
        blade.delete_fleets.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_remove_member_check_mode(self):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        blade.get_fleets_members.return_value = _response(
            [_member("local", is_local=True), _member("array2", "joined")]
        )
        module = _run_main(
            _base_params(state="absent", member_name=["array2"]),
            blade,
            check_mode=True,
        )
        blade.delete_fleets_members.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_remove_local_array_refused(self):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        blade.get_fleets_members.return_value = _response(
            [_member("local", is_local=True), _member("array2", "joined")]
        )
        module = _run_main(_base_params(state="absent", member_name=["local"]), blade)
        blade.delete_fleets_members.assert_not_called()
        module.fail_json.assert_called_once()
        assert "local is this array" in module.fail_json.call_args[1]["msg"]

    def test_remove_member_api_error(self):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        blade.get_fleets_members.return_value = _response(
            [_member("local", is_local=True), _member("array2", "joined")]
        )
        blade.delete_fleets_members.return_value = _response([], status_code=400)
        module = _run_main(_base_params(state="absent", member_name=["array2"]), blade)
        module.fail_json.assert_called_once()
        assert (
            "Failed to remove array2 from the fleet"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_remove_two_members_mixed_states(self):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        blade.get_fleets_members.return_value = _response(
            [
                _member("local", is_local=True),
                _member("array2", "joined"),
                _member("array3", "joining"),
            ]
        )
        blade.delete_fleets_members.return_value = _response([])
        module = _run_main(
            _base_params(state="absent", member_name=["array2", "array3", "array4"]),
            blade,
        )
        assert blade.delete_fleets_members.call_count == 2
        calls = blade.delete_fleets_members.call_args_list
        assert calls[0][1] == {"member_names": ["array2"]}
        assert calls[1][1] == {"member_names": ["array3"], "unreachable": True}
        module.exit_json.assert_called_once_with(changed=True)


class TestFleetDeleteMain:
    """main() flows for state=absent without member_url or member_name"""

    def test_delete_fleet(self):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        blade.delete_fleets.return_value = _response([])
        module = _run_main(_base_params(state="absent", name="fleet1"), blade)
        blade.delete_fleets.assert_called_once_with(names=["fleet1"])
        module.exit_json.assert_called_once_with(changed=True)

    def test_delete_fleet_check_mode_does_not_delete(self):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        module = _run_main(
            _base_params(state="absent", name="fleet1"), blade, check_mode=True
        )
        blade.delete_fleets.assert_not_called()
        blade.delete_fleets_members.assert_not_called()
        module.fail_json.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_delete_fleet_api_error(self):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        blade.delete_fleets.return_value = _response([], status_code=400)
        module = _run_main(_base_params(state="absent", name="fleet1"), blade)
        module.fail_json.assert_called_once()
        assert "Fleet fleet1 deletion failed" in module.fail_json.call_args[1]["msg"]

    def test_delete_without_fleet_is_idempotent(self):
        blade = Mock()
        blade.get_fleets.return_value = _response([])
        for check_mode in [False, True]:
            module = _run_main(
                _base_params(state="absent", name="fleet1"),
                blade,
                check_mode=check_mode,
            )
            blade.delete_fleets.assert_not_called()
            module.exit_json.assert_called_once_with(changed=False)


class TestFleetRenameMain:
    """main() flows for state=present with rename"""

    @patch(MODULE + ".FleetPatch")
    def test_rename_fleet_resolves_local_fleet(self, mock_patch):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        blade.patch_fleets.return_value = _response([])
        module = _run_main(_base_params(rename="fleet2"), blade)
        mock_patch.assert_called_once_with(name="fleet2")
        blade.patch_fleets.assert_called_once_with(
            names=["fleet1"], fleet=mock_patch.return_value
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".FleetPatch")
    def test_rename_fleet_honours_matching_name(self, mock_patch):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        blade.patch_fleets.return_value = _response([])
        module = _run_main(_base_params(name="fleet1", rename="fleet2"), blade)
        blade.patch_fleets.assert_called_once_with(
            names=["fleet1"], fleet=mock_patch.return_value
        )
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE + ".FleetPatch")
    def test_rename_fleet_skips_remote_fleets(self, mock_patch):
        blade = Mock()
        blade.get_fleets.return_value = _response(
            [_fleet("remote", is_local=False), _fleet("fleet1")]
        )
        blade.patch_fleets.return_value = _response([])
        module = _run_main(_base_params(rename="fleet2"), blade)
        blade.patch_fleets.assert_called_once_with(
            names=["fleet1"], fleet=mock_patch.return_value
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_rename_fleet_same_name_is_idempotent(self):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        module = _run_main(_base_params(rename="fleet1"), blade)
        blade.patch_fleets.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_rename_fleet_check_mode(self):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        module = _run_main(_base_params(rename="fleet2"), blade, check_mode=True)
        blade.patch_fleets.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_rename_without_fleet_fails_cleanly(self):
        blade = Mock()
        blade.get_fleets.return_value = _response([])
        module = _run_main(_base_params(rename="fleet2"), blade)
        blade.patch_fleets.assert_not_called()
        module.fail_json.assert_called_once()
        assert "not a member of a fleet" in module.fail_json.call_args[1]["msg"]

    def test_rename_fleet_name_mismatch_fails(self):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        module = _run_main(_base_params(name="other", rename="fleet2"), blade)
        blade.patch_fleets.assert_not_called()
        module.fail_json.assert_called_once()
        assert "member of fleet fleet1" in module.fail_json.call_args[1]["msg"]

    def test_rename_fleet_read_error(self):
        blade = Mock()
        blade.get_fleets.return_value = _response([], status_code=400)
        module = _run_main(_base_params(rename="fleet2"), blade)
        blade.patch_fleets.assert_not_called()
        module.fail_json.assert_called_once()
        assert "Failed to read fleets" in module.fail_json.call_args[1]["msg"]

    @patch(MODULE + ".FleetPatch")
    def test_rename_fleet_api_error(self, mock_patch):
        blade = Mock()
        blade.get_fleets.return_value = _response([_fleet("fleet1")])
        blade.patch_fleets.return_value = _response([], status_code=400)
        module = _run_main(_base_params(rename="fleet2"), blade)
        module.fail_json.assert_called_once()
        assert "Fleet rename failed" in module.fail_json.call_args[1]["msg"]


def _error_text(response, default="Unknown error"):
    """Stand-in for get_error_message: the first message of an error response"""
    errors = getattr(response, "errors", None)
    return errors[0].message if errors else default


def _error_response(message="Operation not permitted.", status_code=400):
    """A refused request as the SDK returns it: errors and no items attribute"""
    error = Mock(spec=["context", "message", "location_context"])
    error.context = None
    error.message = message
    error.location_context = None
    response = Mock(spec=["status_code", "errors", "headers"])
    response.status_code = status_code
    response.errors = [error]
    response.headers = None
    return response


def _array(name):
    array = Mock()
    array.name = name
    return array


def _fleet_key(value="fleet-key-1"):
    key = Mock()
    key.fleet_key = value
    return key


def _fleet_blade(members=None):
    """Local array that is in fleet1, with a fleet key ready to be issued"""
    blade = Mock()
    blade.get_fleets.return_value = _response([_fleet("fleet1")])
    blade.get_fleets_members.return_value = _response(
        members if members is not None else [_member("local", is_local=True)]
    )
    blade.post_fleets_fleet_key.return_value = _response([_fleet_key()])
    blade.delete_fleets_members.return_value = _response([])
    return blade


def _remote(name="array2", rest_version="2.42"):
    """Client of the array at member_url"""
    remote = Mock()
    remote.get_arrays.return_value = _response([_array(name)])
    remote.get_rest_version.return_value = rest_version
    remote.post_fleets_members.return_value = _response([])
    return remote


def _member_url_params(**overrides):
    params = _base_params(
        name="fleet1",
        member_url="array2.example.com",
        member_api="T-11111111-2222-3333-4444-555555555555",
    )
    params.update(overrides)
    return params


def _run_refused(params, blade, check_mode=False):
    """Run main() with the text of the array's answer passed through"""
    with patch(MODULE + ".get_error_message", _error_text):
        return _run_main(params, blade, check_mode=check_mode)


def _run_member_url(params, blade, remote, check_mode=False, remote_version="2.30"):
    """Run main() for the member_url paths with the remote client patched"""
    module = _module(params, check_mode)

    def _version(system):
        return remote_version if system is remote else "2.30"

    with patch(MODULE + ".AnsibleModule", return_value=module), patch(
        MODULE + ".get_system", return_value=blade
    ), patch(MODULE + ".get_rest_api_version", side_effect=_version), patch(
        MODULE + ".LooseVersion", RealLooseVersion
    ), patch(
        MODULE + ".HAS_PYPURECLIENT", True
    ), patch(
        MODULE + ".get_error_message", _error_text
    ), patch(
        MODULE + ".flashblade"
    ) as mock_fb, patch(
        MODULE + ".flasharray"
    ) as mock_fa:
        mock_fb.Client.return_value = remote
        mock_fa.Client.return_value = remote
        try:
            main()
        except SystemExit:
            pass
    return module, mock_fb, mock_fa


def _assert_no_write(blade):
    blade.post_fleets.assert_not_called()
    blade.patch_fleets.assert_not_called()
    blade.delete_fleets.assert_not_called()
    blade.delete_fleets_members.assert_not_called()
    blade.post_fleets_members_batch.assert_not_called()
    blade.post_fleets_fleet_key.assert_not_called()


class TestFleetRefusedRead:
    """A read of the fleets that the array refuses is reported, not raised"""

    def _cases(self):
        batch = [
            {
                "management_address": "10.0.0.2",
                "name": "array2",
                "username": "admin",
                "password": "secret",
                "ca_certificate": None,
                "ca_certificate_group": None,
            }
        ]
        return [
            _base_params(state="absent"),
            _base_params(state="absent", name="fleet1"),
            _base_params(state="create", name="fleet1"),
            _base_params(rename="fleet2"),
            _base_params(state="absent", member_name=["array2"]),
            _base_params(members=batch),
            _member_url_params(),
            _member_url_params(state="absent"),
        ]

    def test_refused_fleet_read_reports_the_array_message(self):
        for params in self._cases():
            for check_mode in [False, True]:
                blade = Mock()
                blade.get_fleets.return_value = _error_response()
                module = _run_refused(params, blade, check_mode=check_mode)
                module.fail_json.assert_called_once_with(
                    msg="Failed to read fleets. Error: Operation not permitted."
                )
                module.exit_json.assert_not_called()
                blade.get_fleets_members.assert_not_called()
                _assert_no_write(blade)

    def test_failed_fleet_read_reports_the_array_message(self):
        blade = Mock()
        blade.get_fleets.return_value = _error_response("Internal error", 500)
        module = _run_refused(_base_params(state="absent"), blade)
        module.fail_json.assert_called_once_with(
            msg="Failed to read fleets. Error: Internal error"
        )
        module.exit_json.assert_not_called()
        _assert_no_write(blade)

    def test_fleet_read_404_still_reports_fusion_not_enabled(self):
        blade = Mock()
        blade.get_fleets.return_value = _error_response("Not found", 404)
        module = _run_refused(_base_params(state="absent"), blade)
        module.fail_json.assert_called_once()
        assert "Fusion is not enabled" in module.fail_json.call_args[1]["msg"]
        module.exit_json.assert_not_called()
        _assert_no_write(blade)

    def test_remote_array_name_returns_name(self):
        module = _module(_member_url_params())
        assert _remote_array_name(module, _remote("array2")) == "array2"
        module.fail_json.assert_not_called()

    def test_remote_array_name_fails_on_refused_read(self):
        module = _module(_member_url_params())
        remote = _remote()
        remote.get_arrays.return_value = _error_response()
        with patch(MODULE + ".get_error_message", _error_text):
            try:
                _remote_array_name(module, remote)
            except SystemExit:
                pass
        module.fail_json.assert_called_once_with(
            msg="Failed to read the array name from array2.example.com. "
            "Error: Operation not permitted."
        )


class TestFleetMemberUrlAdd:
    """main() flows for state=present with member_url and member_api"""

    def test_add_member_check_mode_requests_no_fleet_key(self):
        blade = _fleet_blade()
        remote = _remote("array2")
        module, mock_fb, mock_fa = _run_member_url(
            _member_url_params(), blade, remote, check_mode=True
        )
        _assert_no_write(blade)
        remote.post_fleets_members.assert_not_called()
        mock_fb.Client.assert_called_once()
        mock_fa.Client.assert_not_called()
        module.fail_json.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_add_existing_member_requests_no_fleet_key(self):
        for check_mode in [False, True]:
            blade = _fleet_blade(
                [_member("local", is_local=True), _member("array2", "joined")]
            )
            remote = _remote("array2")
            module = _run_member_url(
                _member_url_params(), blade, remote, check_mode=check_mode
            )[0]
            _assert_no_write(blade)
            remote.post_fleets_members.assert_not_called()
            module.fail_json.assert_not_called()
            module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE + ".FleetMemberPostMembers")
    def test_add_member_requests_key_after_the_reads_and_joins(self, mock_entry):
        blade = _fleet_blade()
        remote = _remote("array2")

        def _issue_key():
            assert remote.get_arrays.called
            assert blade.get_fleets_members.called
            return _response([_fleet_key("fleet-key-1")])

        blade.post_fleets_fleet_key.side_effect = _issue_key
        module = _run_member_url(_member_url_params(), blade, remote)[0]
        blade.post_fleets_fleet_key.assert_called_once_with()
        assert mock_entry.call_args[1]["key"] == "fleet-key-1"
        remote.post_fleets_members.assert_called_once()
        assert remote.post_fleets_members.call_args[1]["fleet_names"] == ["fleet1"]
        module.fail_json.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_add_flashblade_below_minimum_version_requests_no_fleet_key(self):
        for check_mode in [False, True]:
            blade = _fleet_blade()
            remote = _remote("array2")
            module = _run_member_url(
                _member_url_params(),
                blade,
                remote,
                check_mode=check_mode,
                remote_version="2.16",
            )[0]
            module.fail_json.assert_called_once()
            msg = module.fail_json.call_args[1]["msg"]
            assert "Remote FlashBlade must be a minimum of REST API 2.17" in msg
            _assert_no_write(blade)
            remote.post_fleets_members.assert_not_called()
            module.exit_json.assert_not_called()

    def test_add_flasharray_member_check_mode_requests_no_fleet_key(self):
        blade = _fleet_blade()
        remote = _remote("fa1")
        module, mock_fb, mock_fa = _run_member_url(
            _member_url_params(member_api="11111111-2222-3333-4444-555555555555"),
            blade,
            remote,
            check_mode=True,
        )
        mock_fa.Client.assert_called_once()
        mock_fb.Client.assert_not_called()
        _assert_no_write(blade)
        remote.post_fleets_members.assert_not_called()
        module.fail_json.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_add_flasharray_below_minimum_version_requests_no_fleet_key(self):
        blade = _fleet_blade()
        remote = _remote("fa1", rest_version="2.41")
        module = _run_member_url(
            _member_url_params(member_api="11111111-2222-3333-4444-555555555555"),
            blade,
            remote,
        )[0]
        module.fail_json.assert_called_once()
        assert "Purity//FA 6.8.5" in module.fail_json.call_args[1]["msg"]
        _assert_no_write(blade)
        remote.post_fleets_members.assert_not_called()

    def test_add_member_refused_member_list_reports_the_array_message(self):
        for check_mode in [False, True]:
            blade = _fleet_blade()
            blade.get_fleets_members.return_value = _error_response()
            remote = _remote("array2")
            module = _run_member_url(
                _member_url_params(), blade, remote, check_mode=check_mode
            )[0]
            module.fail_json.assert_called_once_with(
                msg="Failed to list fleet members. Error: Operation not permitted."
            )
            _assert_no_write(blade)
            remote.post_fleets_members.assert_not_called()
            module.exit_json.assert_not_called()

    def test_add_member_refused_remote_read_reports_the_array_message(self):
        for check_mode in [False, True]:
            blade = _fleet_blade()
            remote = _remote("array2")
            remote.get_arrays.return_value = _error_response()
            module = _run_member_url(
                _member_url_params(), blade, remote, check_mode=check_mode
            )[0]
            module.fail_json.assert_called_once_with(
                msg="Failed to read the array name from array2.example.com. "
                "Error: Operation not permitted."
            )
            _assert_no_write(blade)
            remote.post_fleets_members.assert_not_called()
            module.exit_json.assert_not_called()

    def test_add_member_refused_fleet_key(self):
        blade = _fleet_blade()
        blade.post_fleets_fleet_key.return_value = _error_response()
        remote = _remote("array2")
        module = _run_member_url(_member_url_params(), blade, remote)[0]
        module.fail_json.assert_called_once_with(
            msg="Fleet key generation failed. Error: Operation not permitted."
        )
        remote.post_fleets_members.assert_not_called()
        module.exit_json.assert_not_called()

    def test_add_member_refused_join(self):
        blade = _fleet_blade()
        remote = _remote("array2")
        remote.post_fleets_members.return_value = _error_response("Invalid fleet key.")
        module = _run_member_url(_member_url_params(), blade, remote)[0]
        blade.post_fleets_fleet_key.assert_called_once_with()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[0][0]
        assert (
            msg == "Array array2 failed to join fleet fleet1. Error: Invalid fleet key."
        )
        module.exit_json.assert_not_called()

    def test_add_member_without_fleet_is_unchanged(self):
        for check_mode in [False, True]:
            blade = _fleet_blade()
            blade.get_fleets.return_value = _response([])
            remote = _remote("array2")
            module, mock_fb, mock_fa = _run_member_url(
                _member_url_params(), blade, remote, check_mode=check_mode
            )
            mock_fb.Client.assert_not_called()
            mock_fa.Client.assert_not_called()
            _assert_no_write(blade)
            module.exit_json.assert_called_once_with(changed=False)


class TestFleetMemberUrlDelete:
    """main() flows for state=absent with member_url and member_api"""

    def _params(self):
        return _member_url_params(state="absent")

    def test_remove_member_refused_member_list_reports_the_array_message(self):
        for check_mode in [False, True]:
            blade = _fleet_blade()
            blade.get_fleets_members.return_value = _error_response()
            remote = _remote("array2")
            module = _run_member_url(
                self._params(), blade, remote, check_mode=check_mode
            )[0]
            module.fail_json.assert_called_once_with(
                msg="Failed to list fleet members. Error: Operation not permitted."
            )
            _assert_no_write(blade)
            module.exit_json.assert_not_called()

    def test_remove_member_refused_remote_read_reports_the_array_message(self):
        for check_mode in [False, True]:
            blade = _fleet_blade(
                [_member("local", is_local=True), _member("array2", "joined")]
            )
            remote = _remote("array2")
            remote.get_arrays.return_value = _error_response()
            module = _run_member_url(
                self._params(), blade, remote, check_mode=check_mode
            )[0]
            module.fail_json.assert_called_once_with(
                msg="Failed to read the array name from array2.example.com. "
                "Error: Operation not permitted."
            )
            _assert_no_write(blade)
            module.exit_json.assert_not_called()

    def test_remove_joined_member(self):
        blade = _fleet_blade(
            [_member("local", is_local=True), _member("array2", "joined")]
        )
        module = _run_member_url(self._params(), blade, _remote("array2"))[0]
        blade.delete_fleets_members.assert_called_once_with(member_names=["array2"])
        blade.post_fleets_fleet_key.assert_not_called()
        module.fail_json.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_remove_member_that_is_not_joined_uses_unreachable(self):
        blade = _fleet_blade(
            [_member("local", is_local=True), _member("array2", "joining")]
        )
        module = _run_member_url(self._params(), blade, _remote("array2"))[0]
        blade.delete_fleets_members.assert_called_once_with(
            member_names=["array2"], unreachable=True
        )
        module.exit_json.assert_called_once_with(changed=True)

    def test_remove_member_check_mode(self):
        blade = _fleet_blade(
            [_member("local", is_local=True), _member("array2", "joined")]
        )
        module = _run_member_url(
            self._params(), blade, _remote("array2"), check_mode=True
        )[0]
        _assert_no_write(blade)
        module.exit_json.assert_called_once_with(changed=True)

    def test_remove_array_that_is_not_a_member_is_unchanged(self):
        blade = _fleet_blade()
        module = _run_member_url(self._params(), blade, _remote("array2"))[0]
        _assert_no_write(blade)
        module.fail_json.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_remove_member_api_error(self):
        blade = _fleet_blade(
            [_member("local", is_local=True), _member("array2", "joined")]
        )
        blade.delete_fleets_members.return_value = _error_response()
        module = _run_member_url(self._params(), blade, _remote("array2"))[0]
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[0][0]
        assert msg == (
            "Array array2.example.com failed to be removed from fleet. "
            "Error: Operation not permitted."
        )
