# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for the purefb_kmip module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
from unittest.mock import MagicMock, Mock, patch

import pytest

# Mock external dependencies before importing module
sys.modules["pypureclient"] = MagicMock()
sys.modules["pypureclient.flashblade"] = MagicMock()
sys.modules["urllib3"] = MagicMock()
sys.modules["distro"] = MagicMock()
sys.modules["grp"] = MagicMock()
sys.modules["fcntl"] = MagicMock()
sys.modules["pwd"] = MagicMock()
sys.modules["syslog"] = MagicMock()
sys.modules["tty"] = MagicMock()

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

from plugins.modules.purefb_kmip import (  # noqa: E402
    create_kmip,
    delete_kmip,
    get_kmip,
    main,
    report_kmip_test,
    update_kmip,
)

MODULE_PATH = "plugins.modules.purefb_kmip"

# What the array answers: a read of an unknown name is a 400 that says the
# object does not exist; a read the caller may not make is a 400 that says so.
NOT_FOUND = "KMIP server does not exist."
REFUSED = "Operation not permitted."


def _response(status_code=200, items=None, message=None):
    """A REST response shaped like the SDK's.

    A valid response carries ``items``. An error response carries ``errors``
    and has no ``items`` attribute at all, which is what turns an unchecked
    read into a traceback.
    """
    if status_code == 200:
        response = Mock(spec=["status_code", "items"])
        response.items = items if items is not None else []
    else:
        response = Mock(spec=["status_code", "errors"])
        response.errors = []
        if message is not None:
            error = Mock(spec=["message"])
            error.message = message
            response.errors = [error]
    response.status_code = status_code
    return response


def _error_message(response, default="Unknown error"):
    """Stand-in for module_utils.common.get_error_message, which the preamble mocks."""
    errors = getattr(response, "errors", None) or []
    return errors[0].message if errors else default


@pytest.fixture(autouse=True)
def _array_error_messages():
    with patch(MODULE_PATH + ".get_error_message", _error_message):
        yield


def _params(**overrides):
    params = {
        "name": "kmip1",
        "state": "present",
        "ca_certificate": None,
        "ca_certificate_group": None,
        "uris": None,
    }
    params.update(overrides)
    return params


def _module(**overrides):
    module = Mock()
    module.params = _params(**overrides)
    module.check_mode = False
    module.fail_json = Mock(side_effect=SystemExit)
    module.exit_json = Mock(side_effect=SystemExit)
    return module


def _reference(name):
    ref = Mock(spec=["name"])
    ref.name = name
    return ref


def _current(uris=None, ca_certificate="ca1", ca_certificate_group=None):
    """A KMIP object shaped like a GET result.

    ``spec`` matters: the real KmipServer raises AttributeError for anything
    outside its field set, which is how the previous implementation broke.
    """
    obj = Mock(spec=["name", "uris", "ca_certificate", "ca_certificate_group", "id"])
    obj.name = "kmip1"
    obj.uris = uris if uris is not None else ["1.1.1.1:5696"]
    obj.ca_certificate = _reference(ca_certificate) if ca_certificate else None
    obj.ca_certificate_group = (
        _reference(ca_certificate_group) if ca_certificate_group else None
    )
    return obj


def _blade(status_code=200, items=None, message=None):
    blade = Mock()
    response = _response(status_code, items=items, message=message)
    for call in (
        "get_kmip",
        "post_kmip",
        "patch_kmip",
        "delete_kmip",
        "get_certificates",
        "get_certificate_groups",
        "get_kmip_test",
    ):
        getattr(blade, call).return_value = response
    return blade


class TestGetKmip:
    """Only the array's "does not exist" answer reads as an absent object."""

    def test_returns_object_when_present(self):
        current = _current()
        blade = _blade(items=[current])
        assert get_kmip(_module(), blade) is current

    def test_returns_none_when_the_array_says_it_does_not_exist(self):
        """An unknown name is answered with a 400, not an empty list."""
        module = _module()
        blade = _blade(status_code=400, message=NOT_FOUND)
        assert get_kmip(module, blade) is None
        blade.get_kmip.assert_called_once_with(names=["kmip1"])
        module.fail_json.assert_not_called()

    def test_returns_none_on_empty_items(self):
        blade = _blade(items=[])
        assert get_kmip(_module(), blade) is None


class TestCreateKmip:
    """Create requires uris and one CA, and sends references."""

    def test_requires_uris(self):
        module = _module(ca_certificate="ca1")
        try:
            create_kmip(module, _blade())
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "uris is required" in module.fail_json.call_args[1]["msg"]

    def test_requires_a_ca(self):
        """The array rejects a KMIP object with neither CA field."""
        module = _module(uris=["1.1.1.1:5696"])
        try:
            create_kmip(module, _blade())
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "ca_certificate or ca_certificate_group" in msg

    @patch(MODULE_PATH + ".Reference")
    @patch(MODULE_PATH + ".KmipServer")
    def test_sends_sorted_uris_and_ca_reference(self, mock_kmip, mock_reference):
        module = _module(uris=["2.2.2.2:5696", "1.1.1.1:5696"], ca_certificate="ca1")
        blade = _blade()
        try:
            create_kmip(module, blade)
        except SystemExit:
            pass
        mock_reference.assert_called_once_with(name="ca1")
        mock_kmip.assert_called_once_with(
            uris=["1.1.1.1:5696", "2.2.2.2:5696"],
            ca_certificate=mock_reference.return_value,
        )
        blade.post_kmip.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".Reference")
    @patch(MODULE_PATH + ".KmipServer")
    def test_uses_certificate_group_when_given(self, mock_kmip, mock_reference):
        module = _module(uris=["1.1.1.1:5696"], ca_certificate_group="grp1")
        try:
            create_kmip(module, _blade())
        except SystemExit:
            pass
        mock_reference.assert_called_once_with(name="grp1")
        assert "ca_certificate_group" in mock_kmip.call_args[1]

    def test_fails_when_named_certificate_is_absent(self):
        module = _module(uris=["1.1.1.1:5696"], ca_certificate="nope")
        blade = _blade()
        blade.get_certificates.return_value = _response(
            400, message="Certificate does not exist."
        )
        try:
            create_kmip(module, blade)
        except SystemExit:
            pass
        module.fail_json.assert_called_once_with(msg="Certificate nope does not exist.")
        blade.post_kmip.assert_not_called()

    @patch(MODULE_PATH + ".KmipServer")
    def test_check_mode_makes_no_call(self, mock_kmip):
        module = _module(uris=["1.1.1.1:5696"], ca_certificate="ca1")
        module.check_mode = True
        blade = _blade()
        try:
            create_kmip(module, blade)
        except SystemExit:
            pass
        blade.post_kmip.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)


class TestUpdateKmip:
    """Update must diff against the real fields and PATCH only what differs."""

    def test_no_change_when_everything_matches(self):
        module = _module(uris=["1.1.1.1:5696"], ca_certificate="ca1")
        blade = _blade()
        try:
            update_kmip(module, blade, _current())
        except SystemExit:
            pass
        blade.patch_kmip.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_no_change_when_nothing_supplied(self):
        module = _module()
        blade = _blade()
        try:
            update_kmip(module, blade, _current())
        except SystemExit:
            pass
        blade.patch_kmip.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_uri_order_does_not_count_as_a_change(self):
        module = _module(uris=["2.2.2.2:5696", "1.1.1.1:5696"])
        blade = _blade()
        current = _current(uris=["1.1.1.1:5696", "2.2.2.2:5696"])
        try:
            update_kmip(module, blade, current)
        except SystemExit:
            pass
        blade.patch_kmip.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE_PATH + ".KmipServer")
    def test_patches_only_the_changed_field(self, mock_kmip):
        """A uris-only change must not resend the CA reference."""
        module = _module(uris=["9.9.9.9:5696"], ca_certificate="ca1")
        blade = _blade()
        try:
            update_kmip(module, blade, _current())
        except SystemExit:
            pass
        mock_kmip.assert_called_once_with(uris=["9.9.9.9:5696"])
        blade.patch_kmip.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)

    @patch(MODULE_PATH + ".Reference")
    @patch(MODULE_PATH + ".KmipServer")
    def test_patches_ca_certificate_change(self, mock_kmip, mock_reference):
        module = _module(ca_certificate="ca2")
        blade = _blade()
        try:
            update_kmip(module, blade, _current(ca_certificate="ca1"))
        except SystemExit:
            pass
        mock_reference.assert_called_once_with(name="ca2")
        mock_kmip.assert_called_once_with(ca_certificate=mock_reference.return_value)
        module.exit_json.assert_called_once_with(changed=True)

    def test_handles_absent_ca_reference_on_current(self):
        """A KMIP object may carry a group instead of a certificate."""
        module = _module(ca_certificate_group="grp1")
        blade = _blade()
        current = _current(ca_certificate=None, ca_certificate_group="grp1")
        try:
            update_kmip(module, blade, current)
        except SystemExit:
            pass
        blade.patch_kmip.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    @patch(MODULE_PATH + ".KmipServer")
    def test_check_mode_reports_change_without_patching(self, mock_kmip):
        module = _module(uris=["9.9.9.9:5696"])
        module.check_mode = True
        blade = _blade()
        try:
            update_kmip(module, blade, _current())
        except SystemExit:
            pass
        blade.patch_kmip.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)


class TestDeleteKmip:
    def test_deletes(self):
        module = _module()
        blade = _blade()
        try:
            delete_kmip(module, blade)
        except SystemExit:
            pass
        blade.delete_kmip.assert_called_once_with(names=["kmip1"])
        module.exit_json.assert_called_once_with(changed=True)

    def test_check_mode_makes_no_call(self):
        module = _module()
        module.check_mode = True
        blade = _blade()
        try:
            delete_kmip(module, blade)
        except SystemExit:
            pass
        blade.delete_kmip.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)


class TestTestKmip:
    def test_reports_components_without_claiming_a_change(self):
        """state=test is read-only, so it must not report changed."""
        component = Mock(
            spec=[
                "component_address",
                "component_name",
                "description",
                "destination",
                "enabled",
                "result_details",
                "success",
                "test_type",
                "resource",
            ]
        )
        component.component_address = "1.1.1.1"
        component.component_name = "fm1"
        component.description = "KMIP server connection"
        component.destination = "1.1.1.1:5696"
        component.enabled = True
        component.result_details = "detail"
        component.success = False
        component.test_type = "connectivity"
        component.resource = _reference("kmip1")

        module = _module(state="test")
        blade = _blade(items=[component])
        try:
            report_kmip_test(module, blade)
        except SystemExit:
            pass
        module.exit_json.assert_called_once()
        kwargs = module.exit_json.call_args[1]
        assert kwargs["changed"] is False
        assert kwargs["test_response"][0]["component_name"] == "fm1"
        assert kwargs["test_response"][0]["success"] is False
        assert kwargs["test_response"][0]["resource_name"] == "kmip1"


# A failed read other than "does not exist": the refusal a realm-scoped
# administrator gets, and an error that carries no message.
FAILED_READS = [
    (400, REFUSED, REFUSED),
    (500, None, "Unknown error"),
]


class TestGetKmipFailedRead:
    """A read that fails for another reason is reported, never read as absent."""

    @pytest.mark.parametrize("status_code, message, reported", FAILED_READS)
    def test_failed_read_fails_with_the_array_message(
        self, status_code, message, reported
    ):
        module = _module()
        blade = _blade(status_code=status_code, message=message)
        with pytest.raises(SystemExit):
            get_kmip(module, blade)
        module.fail_json.assert_called_once_with(
            msg="Failed to read KMIP object kmip1. Error: " + reported
        )

    def test_does_not_exist_is_matched_without_regard_to_case(self):
        blade = _blade(status_code=400, message="KMIP Server Does Not Exist.")
        module = _module()
        assert get_kmip(module, blade) is None
        module.fail_json.assert_not_called()

    def test_realm_style_name_is_read_as_given(self):
        """The name is passed through and the refusal names it."""
        module = _module(name="realm1::kmip1")
        blade = _blade(status_code=400, message=REFUSED)
        with pytest.raises(SystemExit):
            get_kmip(module, blade)
        blade.get_kmip.assert_called_once_with(names=["realm1::kmip1"])
        module.fail_json.assert_called_once_with(
            msg="Failed to read KMIP object realm1::kmip1. Error: " + REFUSED
        )


class TestCertificateRead:
    """The CA lookup tells a missing object from a read that failed."""

    def test_missing_certificate_group_is_reported_as_missing(self):
        module = _module(uris=["1.1.1.1:5696"], ca_certificate_group="nope")
        blade = _blade()
        blade.get_certificate_groups.return_value = _response(
            400, message="Certificate group does not exist."
        )
        with pytest.raises(SystemExit):
            create_kmip(module, blade)
        module.fail_json.assert_called_once_with(
            msg="Certificate group nope does not exist."
        )
        blade.post_kmip.assert_not_called()

    @pytest.mark.parametrize("status_code, message, reported", FAILED_READS)
    def test_failed_certificate_read_stops_the_create(
        self, status_code, message, reported
    ):
        module = _module(uris=["1.1.1.1:5696"], ca_certificate="ca1")
        blade = _blade()
        blade.get_certificates.return_value = _response(status_code, message=message)
        with pytest.raises(SystemExit):
            create_kmip(module, blade)
        module.fail_json.assert_called_once_with(
            msg="Failed to read certificate ca1. Error: " + reported
        )
        blade.post_kmip.assert_not_called()

    @pytest.mark.parametrize("status_code, message, reported", FAILED_READS)
    def test_failed_certificate_group_read_stops_the_create(
        self, status_code, message, reported
    ):
        module = _module(uris=["1.1.1.1:5696"], ca_certificate_group="grp1")
        blade = _blade()
        blade.get_certificate_groups.return_value = _response(
            status_code, message=message
        )
        with pytest.raises(SystemExit):
            create_kmip(module, blade)
        module.fail_json.assert_called_once_with(
            msg="Failed to read certificate group grp1. Error: " + reported
        )
        blade.post_kmip.assert_not_called()


class TestCertificateReadOnUpdate:
    """The same lookup guards a change of the CA on an existing object."""

    def test_failed_certificate_read_stops_the_update(self):
        module = _module(ca_certificate="ca2")
        blade = _blade()
        blade.get_certificates.return_value = _response(400, message=REFUSED)
        with pytest.raises(SystemExit):
            update_kmip(module, blade, _current(ca_certificate="ca1"))
        module.fail_json.assert_called_once_with(
            msg="Failed to read certificate ca2. Error: " + REFUSED
        )
        blade.patch_kmip.assert_not_called()

    def test_missing_certificate_stops_the_update(self):
        module = _module(ca_certificate="nope")
        blade = _blade()
        blade.get_certificates.return_value = _response(
            400, message="Certificate does not exist."
        )
        with pytest.raises(SystemExit):
            update_kmip(module, blade, _current(ca_certificate="ca1"))
        module.fail_json.assert_called_once_with(msg="Certificate nope does not exist.")
        blade.patch_kmip.assert_not_called()

    @patch(MODULE_PATH + ".Reference")
    @patch(MODULE_PATH + ".KmipServer")
    def test_realm_style_reference_is_sent_as_given(self, mock_kmip, mock_reference):
        """A reference is passed through; the array decides whether it fits."""
        module = _module(ca_certificate="realm1::ca2")
        blade = _blade()
        with pytest.raises(SystemExit):
            update_kmip(module, blade, _current(ca_certificate="ca1"))
        blade.get_certificates.assert_called_once_with(names=["realm1::ca2"])
        mock_reference.assert_called_once_with(name="realm1::ca2")
        blade.patch_kmip.assert_called_once()
        module.exit_json.assert_called_once_with(changed=True)


class TestKmipTestFailedRead:
    """state=test reports a refused or failed test instead of a traceback."""

    @pytest.mark.parametrize("status_code, message, reported", FAILED_READS)
    def test_failed_test_read_fails_with_the_array_message(
        self, status_code, message, reported
    ):
        module = _module(state="test")
        blade = _blade()
        blade.get_kmip_test.return_value = _response(status_code, message=message)
        with pytest.raises(SystemExit):
            report_kmip_test(module, blade)
        blade.get_kmip_test.assert_called_once_with(names=["kmip1"])
        module.fail_json.assert_called_once_with(
            msg="Failed to test KMIP object kmip1. Error: " + reported
        )
        module.exit_json.assert_not_called()

    def test_no_components_is_an_empty_report(self):
        module = _module(state="test")
        blade = _blade()
        with pytest.raises(SystemExit):
            report_kmip_test(module, blade)
        module.exit_json.assert_called_once_with(changed=False, test_response=[])


def _run_main(module, blade):
    with patch(MODULE_PATH + ".AnsibleModule", return_value=module), patch(
        MODULE_PATH + ".get_system", return_value=blade
    ):
        with pytest.raises(SystemExit):
            main()


WRITES = ("post_kmip", "patch_kmip", "delete_kmip")


class TestMainFailedRead:
    """A failed read of the object stops every state, check mode included."""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("state", ["absent", "present", "test"])
    @pytest.mark.parametrize("status_code, message, reported", FAILED_READS)
    def test_failed_read_fails_the_task_and_sends_nothing(
        self, status_code, message, reported, state, check_mode
    ):
        module = _module(state=state, uris=["1.1.1.1:5696"], ca_certificate="ca1")
        module.check_mode = check_mode
        blade = _blade()
        blade.get_kmip.return_value = _response(status_code, message=message)
        _run_main(module, blade)
        module.fail_json.assert_called_once_with(
            msg="Failed to read KMIP object kmip1. Error: " + reported
        )
        module.exit_json.assert_not_called()
        for call in WRITES + ("get_kmip_test", "get_certificates"):
            getattr(blade, call).assert_not_called()


class TestMainArrayLevel:
    """An object the array says does not exist is absent, as before."""

    def _absent_blade(self):
        blade = _blade()
        blade.get_kmip.return_value = _response(400, message=NOT_FOUND)
        return blade

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_absent_is_unchanged_when_the_object_does_not_exist(self, check_mode):
        module = _module(state="absent")
        module.check_mode = check_mode
        blade = self._absent_blade()
        _run_main(module, blade)
        module.fail_json.assert_not_called()
        blade.delete_kmip.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_test_fails_when_the_object_does_not_exist(self):
        module = _module(state="test")
        blade = self._absent_blade()
        _run_main(module, blade)
        module.fail_json.assert_called_once_with(
            msg="KMIP object kmip1 does not exist."
        )
        blade.get_kmip_test.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    @patch(MODULE_PATH + ".KmipServer")
    def test_present_creates_when_the_object_does_not_exist(
        self, mock_kmip, check_mode
    ):
        module = _module(uris=["1.1.1.1:5696"], ca_certificate="ca1")
        module.check_mode = check_mode
        blade = self._absent_blade()
        _run_main(module, blade)
        module.fail_json.assert_not_called()
        assert blade.post_kmip.call_count == (0 if check_mode else 1)
        module.exit_json.assert_called_once_with(changed=True)

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_absent_deletes_an_existing_object(self, check_mode):
        module = _module(state="absent")
        module.check_mode = check_mode
        blade = _blade(items=[_current()])
        _run_main(module, blade)
        assert blade.delete_kmip.call_count == (0 if check_mode else 1)
        module.exit_json.assert_called_once_with(changed=True)

    @pytest.mark.parametrize("check_mode", [False, True])
    @patch(MODULE_PATH + ".KmipServer")
    def test_present_updates_an_existing_object(self, mock_kmip, check_mode):
        module = _module(uris=["9.9.9.9:5696"])
        module.check_mode = check_mode
        blade = _blade(items=[_current()])
        _run_main(module, blade)
        assert blade.patch_kmip.call_count == (0 if check_mode else 1)
        blade.post_kmip.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)
