# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_certgrp module."""

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

from plugins.module_utils.version import LooseVersion as RealLooseVersion
from plugins.modules import purefb_certgrp

MOD = "plugins.modules.purefb_certgrp"

# The array's own messages on Purity//FB 4.8.8
GROUP_NOT_FOUND = "Certificate group does not exist."
CERT_NOT_FOUND = "Certificate does not exist."
REALM_NOT_FOUND = "Realm does not exist."
REALM_DESTROYED = "Realm has been destroyed."
REALM_MISMATCH = "Realms for Certificate ({0}) and Certificate group ({1}) don't match"

GROUP = "ca-group"
REALM_GROUP = "realm1::ca-group"
OTHER_GROUP = "realm2::ca-group"
CERTIFICATES = (
    "ca1",
    "ca2",
    "ca3",
    "realm1::ca1",
    "realm1::ca2",
    "realm1::ca3",
    "realm1::only",
    "realm2::ca1",
)


def _realm(name):
    return name.rpartition("::")[0]


def _ok(items=None):
    """A 200 answer; items can be read once, like the SDK's ItemIterator."""
    res = Mock(spec=["status_code", "items"])
    res.status_code = 200
    res.items = iter(items or [])
    return res


def _error(message, status_code=400):
    """A failed answer; like the SDK's ErrorResponse it has no items."""
    res = Mock(spec=["status_code", "errors"])
    res.status_code = status_code
    error = Mock(spec=["message"])
    error.message = message
    res.errors = [error]
    return res


def _named(name, **fields):
    item = Mock(spec=["name"] + list(fields))
    item.name = name
    for key, value in fields.items():
        setattr(item, key, value)
    return item


def _member(group, certificate):
    """A group membership as GET /certificate-groups/certificates lists it."""
    item = Mock(spec=["group", "member"])
    item.group = _named(group)
    item.member = _named(certificate)
    return item


def _read(names):
    """The names of a request as the array reads them.

    A comma separates names, white space around a name is ignored and an
    empty name is skipped.
    """
    found = []
    for entry in names:
        for name in entry.split(","):
            if name.strip():
                found.append(name.strip())
    return found


def _blade(groups=None, realms=("realm1", "realm2"), destroyed=(), hidden=()):
    """A small stateful stand-in for the array.

    groups maps a group name to the names of its members, as the array
    stores them. Names are matched without regard to case and reported in
    the stored spelling. A lookup of something that does not exist answers
    400 with the array's message. A group is created only in a realm that
    exists and is not destroyed, and it takes only certificates that exist
    and are in its own realm. Adding a certificate that is already a member
    is accepted. Writes change the state so that a later read sees them.
    A hidden realm exists but is not open to the caller: its lookup answers
    200 without items and a create in it "Realm does not exist.".
    """
    state = dict((name, list(members)) for name, members in (groups or {}).items())
    blade = Mock()
    blade.groups = state

    def _find(name, names):
        for stored in names:
            if stored.lower() == name.lower():
                return stored
        return None

    def _get_groups(names):
        stored = _find(_read(names)[0], state)
        if stored is None:
            return _error(GROUP_NOT_FOUND)
        return _ok([_named(stored, realms=[])])

    def _get_members(certificate_group_names):
        stored = _find(_read(certificate_group_names)[0], state)
        if stored is None:
            return _error(GROUP_NOT_FOUND)
        return _ok([_member(stored, cert) for cert in state[stored]])

    def _get_realms(names):
        if _find(names[0], hidden):
            return _ok()
        if _find(names[0], destroyed):
            return _ok([_named(_find(names[0], destroyed), destroyed=True)])
        if _find(names[0], realms):
            return _ok([_named(_find(names[0], realms), destroyed=False)])
        return _error(REALM_NOT_FOUND)

    def _post_groups(names):
        name = _read(names)[0]
        realm = _realm(name)
        if realm and _find(realm, destroyed):
            return _error(REALM_DESTROYED)
        if realm and (_find(realm, hidden) or not _find(realm, realms)):
            return _error(REALM_NOT_FOUND)
        assert _find(name, state) is None, "create of a group that exists"
        state[name] = []
        return _ok([_named(name, realms=[])])

    def _delete_groups(names):
        stored = _find(_read(names)[0], state)
        if stored is None:
            return _error(GROUP_NOT_FOUND)
        del state[stored]
        return _ok()

    def _post_members(certificate_names, certificate_group_names):
        stored = _find(_read(certificate_group_names)[0], state)
        if stored is None:
            return _error(GROUP_NOT_FOUND)
        certificates = _read(certificate_names)
        assert certificates, "membership request that names no certificate"
        known = []
        for cert in certificates:
            certificate = _find(cert, CERTIFICATES)
            if certificate is None:
                return _error(CERT_NOT_FOUND)
            if _realm(certificate).lower() != _realm(stored).lower():
                return _error(REALM_MISMATCH.format(cert, certificate_group_names[0]))
            known.append(certificate)
        for certificate in known:
            if _find(certificate, state[stored]) is None:
                state[stored].append(certificate)
        return _ok()

    def _delete_members(certificate_names, certificate_group_names):
        stored = _find(_read(certificate_group_names)[0], state)
        if stored is None:
            return _error(GROUP_NOT_FOUND)
        certificates = _read(certificate_names)
        assert certificates, "membership request that names no certificate"
        for cert in certificates:
            member = _find(cert, state[stored])
            assert member is not None, "removal of a certificate that is no member"
            state[stored].remove(member)
        return _ok()

    blade.get_certificate_groups.side_effect = _get_groups
    blade.get_certificate_groups_certificates.side_effect = _get_members
    blade.get_realms.side_effect = _get_realms
    blade.post_certificate_groups.side_effect = _post_groups
    blade.delete_certificate_groups.side_effect = _delete_groups
    blade.post_certificate_groups_certificates.side_effect = _post_members
    blade.delete_certificate_groups_certificates.side_effect = _delete_members
    return blade


def _twins():
    """The same group and member leaf at array level and in two realms."""
    return _blade(
        {
            GROUP: ["ca1"],
            REALM_GROUP: ["realm1::ca1"],
            OTHER_GROUP: ["realm2::ca1"],
        }
    )


def _fake_error_message(response, default="Unknown error"):
    """What module_utils.common.get_error_message does."""
    errors = getattr(response, "errors", None)
    if errors:
        return errors[0].message
    return default


def _run(blade, check_mode=False, api_version="2.30", **params):
    """Run main() against a blade; returns the module mock.

    The names the fix imports are patched with create=True so that the same
    tests can be run against the module as it was before the fix.
    """
    module = Mock()
    module.params = {"name": GROUP, "state": "present", "certificates": None}
    module.params.update(params)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    with patch(MOD + ".AnsibleModule", return_value=module), patch(
        MOD + ".get_system", return_value=blade
    ) as get_system, patch(
        MOD + ".get_error_message", side_effect=_fake_error_message
    ), patch(
        MOD + ".get_rest_api_version", return_value=api_version, create=True
    ), patch(
        MOD + ".LooseVersion", RealLooseVersion, create=True
    ):
        try:
            purefb_certgrp.main()
        except SystemExit:
            pass
    module.logins = get_system.call_count
    return module


def _changed(module):
    """The changed value of a run that ended without a failure."""
    module.fail_json.assert_not_called()
    module.exit_json.assert_called_once()
    return module.exit_json.call_args[1]["changed"]


def _failure(module):
    """The message of a run that failed."""
    module.exit_json.assert_not_called()
    module.fail_json.assert_called_once()
    return module.fail_json.call_args[1]["msg"]


def _writes(blade):
    """The write requests the module sent, in order."""
    return [
        call[0]
        for call in blade.method_calls
        if call[0].startswith(("post_", "delete_", "patch_"))
    ]


class TestPurefbCertgrp:
    """Certificate groups at array level"""

    def test_create_empty_group(self):
        blade = _blade()
        module = _run(blade)
        assert _changed(module) is True
        blade.post_certificate_groups.assert_called_once_with(names=[GROUP])
        blade.post_certificate_groups_certificates.assert_not_called()
        blade.get_realms.assert_not_called()
        assert blade.groups == {GROUP: []}

    def test_create_group_with_certificates(self):
        blade = _blade()
        module = _run(blade, certificates=["ca1", "ca2"])
        assert _changed(module) is True
        blade.post_certificate_groups_certificates.assert_called_once_with(
            certificate_names=["ca1", "ca2"], certificate_group_names=[GROUP]
        )
        assert blade.groups == {GROUP: ["ca1", "ca2"]}

    def test_create_is_idempotent(self):
        blade = _blade()
        assert _changed(_run(blade, certificates=["ca1"])) is True
        blade.reset_mock()
        assert _changed(_run(blade, certificates=["ca1"])) is False
        assert _writes(blade) == []

    def test_create_check_mode_sends_nothing(self):
        blade = _blade()
        module = _run(blade, check_mode=True, certificates=["ca1"])
        assert _changed(module) is True
        assert _writes(blade) == []
        # an array-level name has no realm to read
        blade.get_realms.assert_not_called()
        assert blade.groups == {}

    def test_create_failure_reports_the_array_message(self):
        blade = _blade()
        blade.post_certificate_groups.side_effect = None
        blade.post_certificate_groups.return_value = _error("boom")
        module = _run(blade)
        assert _failure(module) == (
            "Failed to create certificate group ca-group. Error: boom"
        )

    def test_create_removes_the_group_when_a_member_is_refused(self):
        blade = _blade()
        module = _run(blade, certificates=["ca1", "nope"])
        assert _failure(module) == (
            "Failed to add certificates ['ca1', 'nope']. Error: " + CERT_NOT_FOUND
        )
        blade.delete_certificate_groups.assert_called_once_with(names=[GROUP])
        assert blade.groups == {}

    def test_existing_group_without_certificates_is_left_alone(self):
        blade = _blade({GROUP: ["ca1"]})
        module = _run(blade)
        assert _changed(module) is False
        assert _writes(blade) == []
        blade.get_certificate_groups_certificates.assert_not_called()

    def test_add_sends_only_the_missing_certificates(self):
        blade = _blade({GROUP: ["ca1"]})
        module = _run(blade, certificates=["ca1", "ca2", "ca3"])
        assert _changed(module) is True
        blade.post_certificate_groups_certificates.assert_called_once_with(
            certificate_names=["ca2", "ca3"], certificate_group_names=[GROUP]
        )
        blade.reset_mock()
        assert _changed(_run(blade, certificates=["ca1", "ca2", "ca3"])) is False
        assert _writes(blade) == []

    def test_add_check_mode_sends_nothing(self):
        blade = _blade({GROUP: ["ca1"]})
        module = _run(blade, check_mode=True, certificates=["ca1", "ca2"])
        assert _changed(module) is True
        assert _writes(blade) == []
        assert _changed(_run(blade, check_mode=True, certificates=["ca1"])) is False

    def test_add_failure_reports_the_array_message(self):
        blade = _blade({GROUP: ["ca1"]})
        module = _run(blade, certificates=["nope"])
        assert _failure(module) == (
            "Failed to add certificates ['nope'] to group ca-group. Error: "
            + CERT_NOT_FOUND
        )
        assert blade.groups == {GROUP: ["ca1"]}

    def test_remove_sends_only_members(self):
        blade = _blade({GROUP: ["ca1", "ca2"]})
        module = _run(blade, state="absent", certificates=["ca2", "ca3"])
        assert _changed(module) is True
        blade.delete_certificate_groups_certificates.assert_called_once_with(
            certificate_names=["ca2"], certificate_group_names=[GROUP]
        )
        blade.delete_certificate_groups.assert_not_called()
        assert blade.groups == {GROUP: ["ca1"]}
        blade.reset_mock()
        module = _run(blade, state="absent", certificates=["ca2", "ca3"])
        assert _changed(module) is False
        assert _writes(blade) == []

    def test_remove_check_mode_sends_nothing(self):
        blade = _blade({GROUP: ["ca1", "ca2"]})
        module = _run(blade, check_mode=True, state="absent", certificates=["ca2"])
        assert _changed(module) is True
        assert _writes(blade) == []

    def test_remove_failure_reports_the_array_message(self):
        blade = _blade({GROUP: ["ca1"]})
        blade.delete_certificate_groups_certificates.side_effect = None
        blade.delete_certificate_groups_certificates.return_value = _error("boom")
        module = _run(blade, state="absent", certificates=["ca1"])
        assert _failure(module) == (
            "Failed to delete certificates ['ca1'] from group ca-group. Error: boom"
        )

    def test_remove_from_a_missing_group_is_unchanged(self):
        blade = _blade()
        module = _run(blade, state="absent", certificates=["ca1"])
        assert _changed(module) is False
        assert _writes(blade) == []

    def test_member_read_failure_reports_the_array_message(self):
        blade = _blade({GROUP: ["ca1"]})
        blade.get_certificate_groups_certificates.side_effect = None
        blade.get_certificate_groups_certificates.return_value = _error("boom", 500)
        module = _run(blade, certificates=["ca2"])
        assert _failure(module) == (
            "Failed to get certificate list for group ca-group. Error: boom"
        )
        assert _writes(blade) == []

    def test_delete_group(self):
        blade = _blade({GROUP: ["ca1"], "other": ["ca2"]})
        module = _run(blade, state="absent")
        assert _changed(module) is True
        blade.delete_certificate_groups.assert_called_once_with(names=[GROUP])
        assert blade.groups == {"other": ["ca2"]}
        blade.reset_mock()
        assert _changed(_run(blade, state="absent")) is False
        assert _writes(blade) == []

    def test_delete_group_check_mode_sends_nothing(self):
        blade = _blade({GROUP: ["ca1"]})
        module = _run(blade, check_mode=True, state="absent")
        assert _changed(module) is True
        assert _writes(blade) == []

    def test_delete_failure_reports_the_array_message(self):
        blade = _blade({GROUP: []})
        blade.delete_certificate_groups.side_effect = None
        blade.delete_certificate_groups.return_value = _error("boom")
        module = _run(blade, state="absent")
        assert _failure(module) == (
            "Failed to delete certificate group ca-group. Error: boom"
        )


class TestPurefbCertgrpGroupRead:
    """Only "does not exist" means that the group is absent"""

    def test_refused_read_fails_instead_of_creating(self):
        blade = _blade({GROUP: ["ca1"]})
        blade.get_certificate_groups.side_effect = None
        blade.get_certificate_groups.return_value = _error("Internal error", 500)
        module = _run(blade, certificates=["ca2"])
        assert _failure(module) == (
            "Failed to read certificate group ca-group. Error: Internal error"
        )
        assert _writes(blade) == []

    def test_refused_read_fails_instead_of_reporting_absent(self):
        blade = _blade({GROUP: ["ca1"]})
        blade.get_certificate_groups.side_effect = None
        blade.get_certificate_groups.return_value = _error(
            "Operation not permitted.", 403
        )
        module = _run(blade, state="absent")
        assert _failure(module) == (
            "Failed to read certificate group ca-group. Error: "
            "Operation not permitted."
        )
        assert _writes(blade) == []

    def test_missing_group_is_absent(self):
        blade = _blade({"other": []})
        assert _changed(_run(blade, state="absent")) is False
        assert _changed(_run(blade)) is True
        assert sorted(blade.groups) == [GROUP, "other"]


class TestPurefbCertgrpLetterCase:
    """The array matches names without regard to case"""

    def test_member_in_another_case_is_not_added_again(self):
        blade = _blade({GROUP: ["ca1"]})
        module = _run(blade, certificates=["CA1"])
        assert _changed(module) is False
        assert _writes(blade) == []

    def test_realm_member_in_another_case_is_not_added_again(self):
        blade = _twins()
        module = _run(blade, name=REALM_GROUP, certificates=["REALM1::CA1"])
        assert _changed(module) is False
        assert _writes(blade) == []

    def test_member_in_another_case_is_removed_by_its_stored_name(self):
        blade = _blade({GROUP: ["ca1", "ca2"]})
        module = _run(blade, state="absent", certificates=["CA2"])
        assert _changed(module) is True
        blade.delete_certificate_groups_certificates.assert_called_once_with(
            certificate_names=["ca2"], certificate_group_names=[GROUP]
        )
        assert blade.groups == {GROUP: ["ca1"]}

    def test_realm_member_in_another_case_is_removed_by_its_stored_name(self):
        blade = _twins()
        module = _run(
            blade, name=REALM_GROUP, state="absent", certificates=["Realm1::CA1"]
        )
        assert _changed(module) is True
        blade.delete_certificate_groups_certificates.assert_called_once_with(
            certificate_names=["realm1::ca1"], certificate_group_names=[REALM_GROUP]
        )
        assert blade.groups == {
            GROUP: ["ca1"],
            REALM_GROUP: [],
            OTHER_GROUP: ["realm2::ca1"],
        }

    def test_a_certificate_listed_twice_is_removed_once(self):
        blade = _blade({GROUP: ["ca1", "ca2"]})
        module = _run(blade, state="absent", certificates=["ca2", "CA2"])
        assert _changed(module) is True
        blade.delete_certificate_groups_certificates.assert_called_once_with(
            certificate_names=["ca2"], certificate_group_names=[GROUP]
        )

    def test_group_in_another_case_is_found(self):
        blade = _twins()
        module = _run(blade, name="REALM1::CA-GROUP", certificates=["realm1::ca1"])
        assert _changed(module) is False
        assert _writes(blade) == []

    def test_realm_prefix_in_another_case_is_the_same_realm(self):
        blade = _twins()
        module = _run(blade, name=REALM_GROUP, certificates=["REALM1::ca2"])
        assert _changed(module) is True
        blade.post_certificate_groups_certificates.assert_called_once_with(
            certificate_names=["REALM1::ca2"], certificate_group_names=[REALM_GROUP]
        )
        assert blade.groups[REALM_GROUP] == ["realm1::ca1", "realm1::ca2"]


class TestPurefbCertgrpNameForms:
    """A comma separates names and white space around a name is ignored"""

    def test_names(self):
        assert purefb_certgrp._names(None) == []
        assert purefb_certgrp._names("ca-group") == ["ca-group"]
        assert purefb_certgrp._names(["ca1", " ca2 ", "ca3,ca4", "", " , "]) == [
            "ca1",
            "ca2",
            "ca3",
            "ca4",
        ]

    def test_list_written_as_one_string_is_added_to_a_realm_group(self):
        # "realm1::ca1, realm1::ca2" reaches the module as two entries, the
        # second one with a leading space
        blade = _twins()
        certificates = ["realm1::ca1", " realm1::ca2"]
        module = _run(blade, name=REALM_GROUP, certificates=certificates)
        assert _changed(module) is True
        blade.post_certificate_groups_certificates.assert_called_once_with(
            certificate_names=["realm1::ca2"], certificate_group_names=[REALM_GROUP]
        )
        blade.reset_mock()
        module = _run(blade, name=REALM_GROUP, certificates=certificates)
        assert _changed(module) is False
        assert _writes(blade) == []

    def test_list_written_as_one_string_is_idempotent_at_array_level(self):
        blade = _blade({GROUP: ["ca1"]})
        module = _run(blade, certificates=["ca1", " ca2"])
        assert _changed(module) is True
        blade.post_certificate_groups_certificates.assert_called_once_with(
            certificate_names=["ca2"], certificate_group_names=[GROUP]
        )
        blade.reset_mock()
        assert _changed(_run(blade, certificates=["ca1", " ca2"])) is False
        assert _writes(blade) == []

    def test_entry_holding_two_names_is_two_certificates(self):
        blade = _twins()
        certificates = ["realm1::ca2,realm1::ca3"]
        module = _run(blade, name=REALM_GROUP, certificates=certificates)
        assert _changed(module) is True
        blade.post_certificate_groups_certificates.assert_called_once_with(
            certificate_names=["realm1::ca2", "realm1::ca3"],
            certificate_group_names=[REALM_GROUP],
        )
        blade.reset_mock()
        module = _run(blade, name=REALM_GROUP, certificates=certificates)
        assert _changed(module) is False
        assert _writes(blade) == []

    def test_entry_holding_a_name_of_another_scope_is_refused(self):
        blade = _twins()
        for check_mode in (True, False):
            module = _run(
                blade,
                check_mode=check_mode,
                name=REALM_GROUP,
                certificates=["realm1::ca2,ca2"],
            )
            assert _failure(module) == (
                "Certificate ca2 is not in realm realm1. Certificate group "
                "realm1::ca-group can only hold certificates of its own realm, "
                "named realm1::<certificate>."
            )
        assert blade.method_calls == []

    def test_members_written_with_white_space_are_removed(self):
        blade = _blade({REALM_GROUP: ["realm1::ca1", "realm1::ca2", "realm1::ca3"]})
        certificates = ["realm1::ca1", " realm1::ca2"]
        module = _run(
            blade, name=REALM_GROUP, state="absent", certificates=certificates
        )
        assert _changed(module) is True
        blade.delete_certificate_groups_certificates.assert_called_once_with(
            certificate_names=["realm1::ca1", "realm1::ca2"],
            certificate_group_names=[REALM_GROUP],
        )
        assert blade.groups == {REALM_GROUP: ["realm1::ca3"]}
        blade.reset_mock()
        module = _run(
            blade, name=REALM_GROUP, state="absent", certificates=certificates
        )
        assert _changed(module) is False
        assert _writes(blade) == []

    def test_group_name_with_white_space_is_the_same_group(self):
        blade = _twins()
        module = _run(blade, name=" realm1::ca-group", certificates=["realm1::ca1"])
        assert _changed(module) is False
        assert _writes(blade) == []

    def test_new_group_takes_the_names_as_the_array_reads_them(self):
        blade = _blade()
        module = _run(
            blade, name=REALM_GROUP, certificates=["realm1::ca1", " realm1::ca2"]
        )
        assert _changed(module) is True
        blade.post_certificate_groups_certificates.assert_called_once_with(
            certificate_names=["realm1::ca1", "realm1::ca2"],
            certificate_group_names=[REALM_GROUP],
        )
        assert blade.groups == {REALM_GROUP: ["realm1::ca1", "realm1::ca2"]}

    def test_empty_name_names_no_certificate(self):
        # a templated list that comes out as one empty string adds and
        # removes nothing, and is not taken for "no certificates", which
        # deletes the group
        for group in (GROUP, REALM_GROUP):
            for state in ("present", "absent"):
                blade = _twins()
                module = _run(blade, name=group, state=state, certificates=[""])
                assert _changed(module) is False
                assert _writes(blade) == []
                assert sorted(blade.groups) == sorted([GROUP, REALM_GROUP, OTHER_GROUP])

    def test_new_group_with_an_empty_name_gets_no_member_request(self):
        blade = _blade()
        module = _run(blade, certificates=[""])
        assert _changed(module) is True
        blade.post_certificate_groups.assert_called_once_with(names=[GROUP])
        blade.post_certificate_groups_certificates.assert_not_called()
        assert blade.groups == {GROUP: []}

    def test_every_group_the_name_addresses_is_held_to_the_rule(self):
        module = Mock()
        module.params = {
            "name": "realm1::ca-group, realm1::other",
            "certificates": ["realm1::ca1"],
        }
        purefb_certgrp._check_certificate_realms(module)
        module.fail_json.assert_not_called()
        blade = _twins()
        module = _run(
            blade, name="realm1::ca-group,ca-group", certificates=["realm1::ca1"]
        )
        assert _failure(module) == (
            "Certificate realm1::ca1 is in a realm. Certificate group ca-group is "
            "not in a realm and can only hold certificates that are not in one "
            "either."
        )
        assert blade.method_calls == []


class TestPurefbCertgrpRealms:
    """Groups in a realm, named realm::group, next to array-level namesakes"""

    def test_realm_of(self):
        assert purefb_certgrp._realm_of("ca-group") == ""
        assert purefb_certgrp._realm_of("realm1::ca-group") == "realm1"

    def test_create_realm_group_with_a_realm_certificate(self):
        blade = _blade({GROUP: ["ca1"]})
        module = _run(blade, name=REALM_GROUP, certificates=["realm1::ca1"])
        assert _changed(module) is True
        blade.post_certificate_groups.assert_called_once_with(names=[REALM_GROUP])
        blade.post_certificate_groups_certificates.assert_called_once_with(
            certificate_names=["realm1::ca1"], certificate_group_names=[REALM_GROUP]
        )
        # a real run leaves the realm to the create request
        blade.get_realms.assert_not_called()
        assert blade.groups == {GROUP: ["ca1"], REALM_GROUP: ["realm1::ca1"]}
        blade.reset_mock()
        module = _run(blade, name=REALM_GROUP, certificates=["realm1::ca1"])
        assert _changed(module) is False
        assert _writes(blade) == []

    def test_add_and_remove_touch_only_the_realm_group(self):
        blade = _twins()
        module = _run(blade, name=REALM_GROUP, certificates=["realm1::ca2"])
        assert _changed(module) is True
        blade.post_certificate_groups_certificates.assert_called_once_with(
            certificate_names=["realm1::ca2"], certificate_group_names=[REALM_GROUP]
        )
        module = _run(
            blade, name=REALM_GROUP, state="absent", certificates=["realm1::ca1"]
        )
        assert _changed(module) is True
        blade.delete_certificate_groups_certificates.assert_called_once_with(
            certificate_names=["realm1::ca1"], certificate_group_names=[REALM_GROUP]
        )
        assert blade.groups == {
            GROUP: ["ca1"],
            REALM_GROUP: ["realm1::ca2"],
            OTHER_GROUP: ["realm2::ca1"],
        }
        blade.reset_mock()
        module = _run(
            blade, name=REALM_GROUP, state="absent", certificates=["realm1::ca1"]
        )
        assert _changed(module) is False
        assert _writes(blade) == []

    def test_delete_realm_group_keeps_the_namesakes(self):
        blade = _twins()
        module = _run(blade, name=REALM_GROUP, state="absent")
        assert _changed(module) is True
        blade.delete_certificate_groups.assert_called_once_with(names=[REALM_GROUP])
        assert blade.groups == {GROUP: ["ca1"], OTHER_GROUP: ["realm2::ca1"]}

    def test_bare_certificate_is_refused_for_a_realm_group(self):
        # realm1::only exists and only is its leaf: the array would answer
        # "Certificate does not exist."
        blade = _twins()
        module = _run(blade, name=REALM_GROUP, certificates=["realm1::ca1", "only"])
        assert _failure(module) == (
            "Certificate only is not in realm realm1. Certificate group "
            "realm1::ca-group can only hold certificates of its own realm, named "
            "realm1::<certificate>."
        )
        assert module.logins == 0
        assert blade.method_calls == []

    def test_bare_certificate_is_refused_in_check_mode(self):
        blade = _twins()
        module = _run(blade, check_mode=True, name=REALM_GROUP, certificates=["ca2"])
        assert "is not in realm realm1" in _failure(module)
        assert blade.method_calls == []

    def test_bare_leaf_of_a_member_is_refused_on_removal(self):
        # the member realm1::ca1 would stay in the group
        blade = _twins()
        module = _run(blade, name=REALM_GROUP, state="absent", certificates=["ca1"])
        assert _failure(module) == (
            "Certificate ca1 is not in realm realm1. Certificate group "
            "realm1::ca-group can only hold certificates of its own realm, named "
            "realm1::<certificate>."
        )
        assert blade.method_calls == []
        assert blade.groups[REALM_GROUP] == ["realm1::ca1"]
        assert blade.groups[GROUP] == ["ca1"]

    def test_certificate_of_another_realm_is_refused(self):
        blade = _twins()
        for state in ("present", "absent"):
            module = _run(
                blade, name=REALM_GROUP, state=state, certificates=["realm2::ca1"]
            )
            assert _failure(module) == (
                "Certificate realm2::ca1 is not in realm realm1. Certificate group "
                "realm1::ca-group can only hold certificates of its own realm, "
                "named realm1::<certificate>."
            )
        assert blade.method_calls == []

    def test_realm_certificate_is_refused_for_an_array_level_group(self):
        blade = _twins()
        for state in ("present", "absent"):
            for check_mode in (True, False):
                module = _run(
                    blade,
                    check_mode=check_mode,
                    state=state,
                    certificates=["ca2", "realm1::ca2"],
                )
                assert _failure(module) == (
                    "Certificate realm1::ca2 is in a realm. Certificate group "
                    "ca-group is not in a realm and can only hold certificates "
                    "that are not in one either."
                )
        assert blade.method_calls == []

    def test_new_realm_group_is_not_created_for_a_bare_certificate(self):
        blade = _blade()
        module = _run(blade, name=REALM_GROUP, certificates=["ca1"])
        assert "is not in realm realm1" in _failure(module)
        assert blade.method_calls == []
        assert blade.groups == {}

    def test_delete_of_a_realm_group_names_no_certificate(self):
        blade = _twins()
        module = _run(blade, name=REALM_GROUP, state="absent", certificates=[])
        assert _changed(module) is True
        assert REALM_GROUP not in blade.groups


class TestPurefbCertgrpCheckModeRealm:
    """Check mode reads the realm a new group is named into"""

    def test_unknown_realm_fails_like_the_real_run(self):
        blade = _blade()
        messages = []
        for check_mode in (True, False):
            module = _run(blade, check_mode=check_mode, name="nowhere::ca-group")
            messages.append(_failure(module))
        assert messages[0] == (
            "Failed to create certificate group nowhere::ca-group. Error: "
            + REALM_NOT_FOUND
        )
        assert messages[1] == messages[0]
        blade.get_realms.assert_called_once_with(names=["nowhere"])
        blade.post_certificate_groups.assert_called_once_with(
            names=["nowhere::ca-group"]
        )
        assert blade.groups == {}

    def test_destroyed_realm_fails_like_the_real_run(self):
        blade = _blade(destroyed=("realm3",))
        messages = []
        for check_mode in (True, False):
            module = _run(blade, check_mode=check_mode, name="realm3::ca-group")
            messages.append(_failure(module))
        assert messages[0] == (
            "Failed to create certificate group realm3::ca-group. Error: "
            + REALM_DESTROYED
        )
        assert messages[1] == messages[0]
        assert blade.groups == {}

    def test_existing_realm_reports_changed(self):
        blade = _blade()
        module = _run(
            blade, check_mode=True, name=REALM_GROUP, certificates=["realm1::ca1"]
        )
        assert _changed(module) is True
        blade.get_realms.assert_called_once_with(names=["realm1"])
        assert _writes(blade) == []
        assert blade.groups == {}

    def test_realm_not_open_to_the_caller_fails_like_the_real_run(self):
        # a realm-scoped administrator naming a realm that is not its own:
        # the realm is read as 200 without items, the create is refused
        blade = _blade(hidden=("realm3",))
        messages = []
        for check_mode in (True, False):
            module = _run(blade, check_mode=check_mode, name="realm3::ca-group")
            messages.append(_failure(module))
        assert messages[0] == (
            "Failed to create certificate group realm3::ca-group. Error: "
            + REALM_NOT_FOUND
        )
        assert messages[1] == messages[0]
        assert blade.groups == {}

    def test_every_realm_the_name_addresses_is_read(self):
        blade = _blade()
        name = "realm1::ca-group,nowhere::ca-group"
        module = _run(blade, check_mode=True, name=name)
        assert _failure(module) == (
            "Failed to create certificate group " + name + ". Error: " + REALM_NOT_FOUND
        )
        assert [call[1]["names"] for call in blade.get_realms.call_args_list] == [
            ["realm1"],
            ["nowhere"],
        ]
        assert _writes(blade) == []

    def test_refused_realm_read_is_no_answer(self):
        blade = _blade()
        blade.get_realms.side_effect = None
        blade.get_realms.return_value = _error(
            "Operation not permitted. Authorization for 'read' on 'realms' is "
            "required.",
            403,
        )
        module = _run(blade, check_mode=True, name=REALM_GROUP)
        assert _changed(module) is True
        assert _writes(blade) == []

    def test_array_without_realms_is_not_asked(self):
        blade = _blade()
        module = _run(blade, check_mode=True, api_version="2.18", name=REALM_GROUP)
        assert _changed(module) is True
        blade.get_realms.assert_not_called()

    def test_existing_group_does_not_read_the_realm(self):
        blade = _twins()
        module = _run(
            blade, check_mode=True, name=REALM_GROUP, certificates=["realm1::ca2"]
        )
        assert _changed(module) is True
        blade.get_realms.assert_not_called()
