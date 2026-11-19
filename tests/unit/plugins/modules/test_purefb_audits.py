# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_audits module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import datetime
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

from ansible.module_utils.compat.version import LooseVersion

from plugins.modules import purefb_audits as audits_module
from plugins.modules.purefb_audits import (
    main,
    _build_filter,
    _format_audit,
    _resolve_timezone,
    _to_timestamp,
    _tzinfo,
    _validate_filter_values,
    AUDIT_CONTEXT_VERSION,
)

MODULE = "plugins.modules.purefb_audits"

# 2024-10-31 06:23:13 UTC == 2024-10-30 23:23:13 PDT
RECORD_TIME_MS = 1730355793000
# 2024-10-31 06:23:00 UTC and 06:23:30 UTC
WINDOW_START_MS = 1730355780000
WINDOW_END_MS = 1730355810000
# 2024-11-17 12:00:00 PST == 2024-11-17 20:00:00 UTC
PST_NOON_MS = 1731873600000


class _Audit:
    """Stand-in for an SDK audit record: an absent field raises AttributeError."""

    def __init__(self, **fields):
        self.__dict__.update(fields)


def _ref(name):
    return _Audit(id="id-" + name, name=name, resource_type="arrays")


def _record(name="1", **fields):
    base = dict(
        name=name,
        time=RECORD_TIME_MS,
        user="pureuser",
        user_interface="GUI",
        ip_address="10.0.0.1",
        user_agent="Google-HTTP-Java-Client/1.44.1 (gzip)",
        command="purearray",
        subcommand="eula accept",
        arguments="",
        origin=_ref("array1"),
    )
    base.update(fields)
    return _Audit(**base)


def _full_record(name="9228"):
    return _record(
        name=name,
        user="svc-ansible",
        user_interface="REST",
        command="purefs",
        subcommand="create",
        arguments="--size 10G fs1",
        context=_ref("array1"),
        scopes=[_ref("array1"), _ref("realm1")],
        system_event=False,
        correlation_id="6f1c0b9e",
    )


# The array keeps only the ID of a realm once the realm is eradicated
ERADICATED_REALM_ID = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"


def _realm_record(name="14075", realm="realm1"):
    """A record of a command run on an object inside a realm"""
    return _record(
        name=name,
        user="svc-ansible",
        user_interface="REST",
        command="purefs",
        subcommand="create",
        arguments="--size '1G' {0}::fs1".format(realm),
        scopes=[_Audit(id="id-" + realm, name=realm, resource_type="realms")],
    )


def _base_params(**overrides):
    params = {
        "start": None,
        "end": None,
        "timezone": None,
        "user": None,
        "command": None,
        "user_interface": None,
        "correlation_id": None,
        "scopes": None,
        "include_system_events": False,
        "newest_first": False,
        "limit": None,
        "context": "",
    }
    params.update(overrides)
    return params


def _module(check_mode=False, **overrides):
    module = Mock()
    module.params = _base_params(**overrides)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _blade(audits=None, status=200, time_zone="UTC", arrays_status=200):
    blade = Mock()
    arrays_res = Mock()
    arrays_res.status_code = arrays_status
    array = Mock()
    array.time_zone = time_zone
    arrays_res.items = [array]
    blade.get_arrays.return_value = arrays_res
    audits_res = Mock()
    audits_res.status_code = status
    audits_res.items = audits or []
    audits_res.errors = []
    blade.get_audits.return_value = audits_res
    return blade


def _run_main(module, blade, api_version="2.30"):
    with patch(MODULE + ".AnsibleModule", return_value=module), patch(
        MODULE + ".get_system", return_value=blade
    ), patch(MODULE + ".get_rest_api_version", return_value=api_version), patch(
        MODULE + ".LooseVersion", LooseVersion
    ):
        try:
            main()
        except SystemExit:
            pass


class TestPurefbAudits:
    """Test cases for purefb_audits module"""

    # ---------------- _tzinfo ----------------

    def test_tzinfo_utc_needs_no_timezone_database(self):
        """UTC is served by the standard library, not by a zoneinfo lookup"""
        assert _tzinfo("UTC") is datetime.timezone.utc

    def test_tzinfo_resolves_iana_names(self):
        """Any other name is resolved through zoneinfo"""
        assert _tzinfo("America/Los_Angeles").key == "America/Los_Angeles"

    def test_module_does_not_depend_on_pytz(self):
        """The module never imports pytz, which the test environment lacks"""
        assert not hasattr(audits_module, "pytz")
        assert not hasattr(audits_module, "HAS_PYTZ")

    # ---------------- _to_timestamp ----------------

    def test_to_timestamp_utc(self):
        """A UTC date/time converts to epoch milliseconds"""
        module = _module(start="2024-10-31 06:23:13")
        assert _to_timestamp(module, "start", "UTC") == RECORD_TIME_MS

    def test_to_timestamp_localizes_for_the_date_given(self):
        """The offset follows the date given, on both sides of a DST change"""
        module = _module(start="2024-10-30 23:23:13", end="2024-11-17 12:00:00")
        assert _to_timestamp(module, "start", "America/Los_Angeles") == RECORD_TIME_MS
        assert _to_timestamp(module, "end", "America/Los_Angeles") == PST_NOON_MS

    def test_to_timestamp_rejects_bad_format(self):
        """A date/time in the wrong format fails the module"""
        module = _module(start="31/10/2024 06:23")
        try:
            _to_timestamp(module, "start", "UTC")
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "start value 31/10/2024 06:23 is not a valid date/time" in msg

    # ---------------- _build_filter ----------------

    @patch(MODULE + ".LooseVersion", LooseVersion)
    def test_build_filter_none_on_old_array_without_options(self):
        """No options and no system_event field gives no filter at all"""
        assert _build_filter(_module(), "2.27", "UTC") is None

    @patch(MODULE + ".LooseVersion", LooseVersion)
    def test_build_filter_hides_system_events_from_2_28(self):
        """From 2.28 the quoted system_event filter is sent by default"""
        assert _build_filter(_module(), "2.28", "UTC") == "system_event='false'"
        assert _build_filter(_module(), "2.30", "UTC") == "system_event='false'"

    @patch(MODULE + ".LooseVersion", LooseVersion)
    def test_build_filter_none_when_system_events_included(self):
        """include_system_events drops the system_event filter"""
        assert _build_filter(_module(include_system_events=True), "2.30", "UTC") is None

    @patch(MODULE + ".LooseVersion", LooseVersion)
    def test_build_filter_composes_every_part(self):
        """All filters are AND-ed in a fixed order with the API quoting"""
        module = _module(
            start="2024-10-31 06:23:00",
            end="2024-10-31 06:23:30",
            user="pureuser",
            command="purefs",
            user_interface="REST",
            correlation_id="6f1c",
            scopes=["realm1"],
        )
        expected = (
            "time>={0} and time<={1} and user='pureuser' and command='purefs' "
            "and user_interface='REST' and correlation_id='6f1c*' "
            "and scopes.name='realm1' and system_event='false'"
        ).format(WINDOW_START_MS, WINDOW_END_MS)
        assert _build_filter(module, "2.30", "UTC") == expected

    @patch(MODULE + ".LooseVersion", LooseVersion)
    def test_build_filter_one_scope(self):
        """One realm name becomes a scopes.name filter, with no parentheses"""
        assert (
            _build_filter(_module(scopes=["realm1"]), "2.30", "UTC")
            == "scopes.name='realm1' and system_event='false'"
        )
        # Scopes arrived in 2.20, before the system_event field
        assert (
            _build_filter(_module(scopes=["realm1"]), "2.20", "UTC")
            == "scopes.name='realm1'"
        )

    @patch(MODULE + ".LooseVersion", LooseVersion)
    def test_build_filter_several_scopes_match_any(self):
        """Several names are OR-ed inside parentheses and AND-ed with the rest"""
        module = _module(command="purefs", scopes=["realm1", "array1"])
        assert _build_filter(module, "2.30", "UTC") == (
            "command='purefs' and (scopes.name='realm1' or scopes.name='array1') "
            "and system_event='false'"
        )

    @patch(MODULE + ".LooseVersion", LooseVersion)
    def test_build_filter_ignores_empty_and_repeated_scopes(self):
        """Empty entries and repeats are dropped; nothing left means no filter"""
        module = _module(scopes=["realm1", "", "realm1"])
        assert _build_filter(module, "2.20", "UTC") == "scopes.name='realm1'"
        assert _build_filter(_module(scopes=[""]), "2.20", "UTC") is None
        assert _build_filter(_module(scopes=[]), "2.20", "UTC") is None
        assert _build_filter(_module(scopes=None), "2.20", "UTC") is None

    @patch(MODULE + ".LooseVersion", LooseVersion)
    def test_build_filter_passes_wildcard_and_qualified_scope_unchanged(self):
        """A wildcard or a realm::object value is sent as given, never split"""
        module = _module(scopes=["tenant*", "realm1::fs1"])
        assert _build_filter(module, "2.20", "UTC") == (
            "(scopes.name='tenant*' or scopes.name='realm1::fs1')"
        )

    @patch(MODULE + ".LooseVersion", LooseVersion)
    def test_build_filter_rejects_end_before_start(self):
        """An end earlier than start fails the module"""
        module = _module(start="2024-10-31 06:23:30", end="2024-10-31 06:23:00")
        try:
            _build_filter(module, "2.30", "UTC")
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "earlier than start" in module.fail_json.call_args[1]["msg"]

    # ---------------- _validate_filter_values ----------------

    def test_validate_filter_values_rejects_single_quote(self):
        """A filter value containing a single quote is refused"""
        module = _module(correlation_id="6f1c'")
        try:
            _validate_filter_values(module)
        except SystemExit:
            pass
        module.fail_json.assert_called_once_with(
            msg="correlation_id value 6f1c' must not contain a single quote"
        )

    def test_validate_filter_values_accepts_plain_values(self):
        """Ordinary filter values pass"""
        module = _module(user="svc-ansible", command="purefs", user_interface="REST")
        _validate_filter_values(module)
        module.fail_json.assert_not_called()

    def test_validate_filter_values_rejects_single_quote_in_a_scope(self):
        """A scope name containing a single quote is refused"""
        module = _module(scopes=["realm1", "o'realm"])
        try:
            _validate_filter_values(module)
        except SystemExit:
            pass
        module.fail_json.assert_called_once_with(
            msg="scopes value o'realm must not contain a single quote"
        )

    # ---------------- _resolve_timezone ----------------

    def test_resolve_timezone_prefers_the_option(self):
        """The timezone option is used without reading the array"""
        module = _module(timezone="Europe/London")
        blade = _blade(time_zone="America/Los_Angeles")
        assert _resolve_timezone(module, blade) == "Europe/London"
        blade.get_arrays.assert_not_called()

    def test_resolve_timezone_reads_the_array(self):
        """Without the option the array timezone is used"""
        module = _module()
        blade = _blade(time_zone="America/Los_Angeles")
        assert _resolve_timezone(module, blade) == "America/Los_Angeles"
        blade.get_arrays.assert_called_once_with()
        module.warn.assert_not_called()

    @patch(MODULE + ".get_local_tz", return_value="Europe/Paris")
    def test_resolve_timezone_falls_back_to_local(self, mock_local_tz):
        """When the array timezone cannot be read the local timezone is used"""
        module = _module()
        blade = _blade(arrays_status=400)
        assert _resolve_timezone(module, blade) == "Europe/Paris"
        mock_local_tz.assert_called_once_with(module)
        module.warn.assert_called_once_with(
            "Could not read the array timezone, using Europe/Paris"
        )

    @patch(MODULE + ".get_local_tz", return_value="Europe/Paris")
    def test_resolve_timezone_falls_back_when_time_zone_unset(self, mock_local_tz):
        """An array answer without a time_zone value also falls back with a warning"""
        module = _module()
        blade = _blade(time_zone=None)
        assert _resolve_timezone(module, blade) == "Europe/Paris"
        mock_local_tz.assert_called_once_with(module)
        module.warn.assert_called_once()

    def test_resolve_timezone_rejects_unknown_zone(self):
        """An unknown timezone fails the module"""
        module = _module(timezone="Mars/Olympus")
        try:
            _resolve_timezone(module, _blade())
        except SystemExit:
            pass
        module.fail_json.assert_called_once_with(
            msg="Timezone Mars/Olympus is not valid"
        )

    def test_resolve_timezone_rejects_malformed_zone(self):
        """A name zoneinfo refuses as a key also fails the module"""
        module = _module(timezone="../Europe/London")
        try:
            _resolve_timezone(module, _blade())
        except SystemExit:
            pass
        module.fail_json.assert_called_once_with(
            msg="Timezone ../Europe/London is not valid"
        )

    # ---------------- _format_audit ----------------

    def test_format_audit_full_record(self):
        """Every field of a 2.28+ record is returned, time in the zone given"""
        assert _format_audit(_full_record(), "UTC") == {
            "name": "9228",
            "time": "2024-10-31 06:23:13 UTC",
            "user": "svc-ansible",
            "user_interface": "REST",
            "ip_address": "10.0.0.1",
            "user_agent": "Google-HTTP-Java-Client/1.44.1 (gzip)",
            "command": "purefs",
            "subcommand": "create",
            "arguments": "--size 10G fs1",
            "origin": "array1",
            "context": "array1",
            "scopes": ["array1", "realm1"],
            "system_event": False,
            "correlation_id": "6f1c0b9e",
        }

    def test_format_audit_reports_time_in_array_zone(self):
        """The record time is reported in the resolved timezone"""
        result = _format_audit(_record(), "America/Los_Angeles")
        assert result["time"] == "2024-10-30 23:23:13 PDT"

    def test_format_audit_defaults_absent_fields(self):
        """Fields older arrays do not record come back as defaults"""
        result = _format_audit(_record(), "UTC")
        assert result["context"] is None
        assert result["scopes"] == []
        assert result["system_event"] is False
        assert result["correlation_id"] is None
        assert result["origin"] == "array1"

    def test_format_audit_eradicated_realm_scope_is_reported_by_id(self):
        """A scope the array returns without a name is reported by its ID"""
        nameless = _Audit(id=ERADICATED_REALM_ID, resource_type="realms")
        null_name = _Audit(id=ERADICATED_REALM_ID, name=None, resource_type="realms")
        for scope in (nameless, null_name):
            audit = _record(
                command="purerealm",
                subcommand="create",
                arguments="--without-default-access-list realm1",
                scopes=[_ref("array1"), scope],
            )
            result = _format_audit(audit, "UTC")
            assert result["scopes"] == ["array1", ERADICATED_REALM_ID]

    def test_format_audit_only_scope_of_eradicated_realm(self):
        """A record scoped only to an eradicated realm keeps the realm::name arguments"""
        audit = _realm_record()
        audit.scopes = [_Audit(id=ERADICATED_REALM_ID, resource_type="realms")]
        result = _format_audit(audit, "UTC")
        assert result["scopes"] == [ERADICATED_REALM_ID]
        assert result["arguments"] == "--size '1G' realm1::fs1"

    def test_format_audit_never_returns_a_null_scope(self):
        """A scope with neither a name nor an ID, or a null entry, is left out"""
        audit = _record(
            scopes=[_ref("array1"), _Audit(resource_type="realms"), None],
        )
        assert _format_audit(audit, "UTC")["scopes"] == ["array1"]
        assert _format_audit(_record(scopes=[None]), "UTC")["scopes"] == []

    def test_format_audit_without_time_or_origin(self):
        """A record with no time or origin does not crash the module"""
        audit = _Audit(name="7", command="purefs")
        result = _format_audit(audit, "UTC")
        assert result["time"] is None
        assert result["origin"] is None
        assert result["user"] is None
        assert result["command"] == "purefs"

    # ---------------- main() flows ----------------

    def test_main_lists_audits_never_changed(self):
        """Listing returns every record and always reports changed=False"""
        module = _module()
        blade = _blade(audits=[_record("1"), _full_record("2")])
        _run_main(module, blade)

        blade.get_audits.assert_called_once_with(filter="system_event='false'")
        module.exit_json.assert_called_once()
        result = module.exit_json.call_args[1]
        assert result["changed"] is False
        assert [a["name"] for a in result["purefb_audits"]] == ["1", "2"]
        assert result["purefb_audits"][0]["time"] == "2024-10-31 06:23:13 UTC"

    def test_main_idempotent_rerun(self):
        """A second identical run reads again and still reports no change"""
        module = _module(user="pureuser")
        blade = _blade(audits=[_record("1")])
        _run_main(module, blade)
        _run_main(module, blade)

        assert blade.get_audits.call_count == 2
        assert module.exit_json.call_count == 2
        for call in module.exit_json.call_args_list:
            assert call[1]["changed"] is False
            assert len(call[1]["purefb_audits"]) == 1

    def test_main_check_mode_reads_the_trail(self):
        """Check mode performs the read-only listing too"""
        module = _module(check_mode=True)
        blade = _blade(audits=[_record("1")])
        _run_main(module, blade)

        blade.get_audits.assert_called_once()
        result = module.exit_json.call_args[1]
        assert result["changed"] is False
        assert len(result["purefb_audits"]) == 1

    def test_main_passes_limit_sort_and_context(self):
        """newest_first, limit and context map onto the SDK call"""
        module = _module(newest_first=True, limit=10, context="fleet1")
        blade = _blade(audits=[_record("9228")])
        _run_main(module, blade)

        blade.get_audits.assert_called_once_with(
            filter="system_event='false'",
            limit=10,
            sort=["time-"],
            context_names=["fleet1"],
        )
        assert module.exit_json.call_args[1]["changed"] is False

    def test_main_window_uses_the_array_timezone(self):
        """start/end are interpreted and times reported in the array timezone"""
        module = _module(start="2024-10-30 23:23:00", end="2024-10-30 23:23:30")
        blade = _blade(audits=[_record("1")], time_zone="America/Los_Angeles")
        _run_main(module, blade)

        blade.get_audits.assert_called_once_with(
            filter="time>={0} and time<={1} and system_event='false'".format(
                WINDOW_START_MS, WINDOW_END_MS
            )
        )
        result = module.exit_json.call_args[1]
        assert result["purefb_audits"][0]["time"] == "2024-10-30 23:23:13 PDT"

    def test_main_old_array_sends_no_system_event_filter(self):
        """Before 2.28 only the user filter is sent"""
        module = _module(user="pureuser")
        blade = _blade(audits=[_record("1")])
        _run_main(module, blade, api_version="2.27")

        blade.get_audits.assert_called_once_with(filter="user='pureuser'")
        result = module.exit_json.call_args[1]
        assert result["changed"] is False
        assert result["purefb_audits"][0]["system_event"] is False

    def test_main_context_requires_2_28(self):
        """The context option is refused before REST 2.28"""
        module = _module(context="fleet1")
        blade = _blade()
        _run_main(module, blade, api_version="2.27")

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "context option requires FlashBlade REST version 2.28" in msg
        blade.get_audits.assert_not_called()

    def test_main_correlation_id_requires_2_28(self):
        """The correlation_id option is refused before REST 2.28"""
        module = _module(correlation_id="6f1c")
        blade = _blade()
        _run_main(module, blade, api_version="2.27")

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "correlation_id option requires FlashBlade REST version 2.28" in msg
        blade.get_audits.assert_not_called()

    def test_main_reads_newest_records_of_one_realm(self):
        """scopes, newest_first and limit read the newest records of a realm"""
        module = _module(scopes=["realm1"], newest_first=True, limit=3)
        blade = _blade(audits=[_realm_record("14075"), _realm_record("14071")])
        _run_main(module, blade)

        blade.get_audits.assert_called_once_with(
            filter="scopes.name='realm1' and system_event='false'",
            limit=3,
            sort=["time-"],
        )
        result = module.exit_json.call_args[1]
        assert result["changed"] is False
        assert [a["scopes"] for a in result["purefb_audits"]] == [["realm1"]] * 2
        assert result["purefb_audits"][0]["arguments"] == "--size '1G' realm1::fs1"

    def test_main_scopes_idempotent_rerun_and_check_mode(self):
        """A scoped read is repeated unchanged, in check mode as well"""
        blade = _blade(audits=[_realm_record()])
        results = []
        for check_mode in (False, False, True):
            module = _module(check_mode=check_mode, scopes=["realm1", "array1"])
            _run_main(module, blade)
            results.append(module.exit_json.call_args[1])

        assert blade.get_audits.call_count == 3
        for call in blade.get_audits.call_args_list:
            assert call[1] == {
                "filter": "(scopes.name='realm1' or scopes.name='array1') "
                "and system_event='false'"
            }
        assert results[0] == results[1] == results[2]
        assert results[0]["changed"] is False

    def test_main_array_scope_selects_array_level_records(self):
        """The array name selects the records of array-level objects"""
        audit = _full_record("14071")
        audit.scopes = [_ref("array1")]
        module = _module(scopes=["array1"], command="purefs")
        blade = _blade(audits=[audit])
        _run_main(module, blade)

        blade.get_audits.assert_called_once_with(
            filter="command='purefs' and scopes.name='array1' "
            "and system_event='false'"
        )
        result = module.exit_json.call_args[1]
        assert result["changed"] is False
        assert result["purefb_audits"][0]["scopes"] == ["array1"]
        assert "::" not in result["purefb_audits"][0]["arguments"]

    def test_main_without_scopes_sends_the_request_unchanged(self):
        """No scopes, or an empty list, leaves the request as it always was"""
        for scopes in (None, []):
            module = _module(scopes=scopes, user="pureuser")
            blade = _blade(audits=[_record("1"), _full_record("2")])
            _run_main(module, blade)

            module.fail_json.assert_not_called()
            blade.get_audits.assert_called_once_with(
                filter="user='pureuser' and system_event='false'"
            )
            result = module.exit_json.call_args[1]
            assert result["changed"] is False
            assert [a["scopes"] for a in result["purefb_audits"]] == [
                [],
                ["array1", "realm1"],
            ]

    def test_main_scopes_requires_2_20(self):
        """The scopes option is refused before REST 2.20, before any read"""
        module = _module(scopes=["realm1"])
        blade = _blade()
        _run_main(module, blade, api_version="2.19")

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "scopes option requires FlashBlade REST version 2.20" in msg
        blade.get_arrays.assert_not_called()
        blade.get_audits.assert_not_called()

    def test_main_scopes_allowed_from_2_20(self):
        """From REST 2.20 the scope filter is sent; empty scopes need no gate"""
        module = _module(scopes=["realm1"])
        blade = _blade(audits=[_realm_record()])
        _run_main(module, blade, api_version="2.20")

        module.fail_json.assert_not_called()
        blade.get_audits.assert_called_once_with(filter="scopes.name='realm1'")

        module = _module(scopes=[""])
        blade = _blade(audits=[_record("1")])
        _run_main(module, blade, api_version="2.19")

        module.fail_json.assert_not_called()
        blade.get_audits.assert_called_once_with()

    def test_main_rejects_quoted_scope_before_contacting_the_array(self):
        """A scope name with a single quote fails before any array request"""
        module = _module(scopes=["o'realm"])
        blade = _blade()
        _run_main(module, blade)

        module.fail_json.assert_called_once_with(
            msg="scopes value o'realm must not contain a single quote"
        )
        blade.get_arrays.assert_not_called()
        blade.get_audits.assert_not_called()

    def test_main_returns_eradicated_realm_scope_by_id(self):
        """Records of an eradicated realm are listed without a null scope"""
        audit = _realm_record()
        audit.scopes = [_Audit(id=ERADICATED_REALM_ID, resource_type="realms")]
        module = _module()
        blade = _blade(audits=[audit, _full_record("2")])
        _run_main(module, blade)

        result = module.exit_json.call_args[1]
        assert result["changed"] is False
        assert [a["scopes"] for a in result["purefb_audits"]] == [
            [ERADICATED_REALM_ID],
            ["array1", "realm1"],
        ]

    def test_main_scopes_gate_is_the_same_in_check_mode(self):
        """Check mode refuses the option before REST 2.20 as a real run does"""
        module = _module(check_mode=True, scopes=["realm1"])
        blade = _blade()
        _run_main(module, blade, api_version="2.19")

        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "scopes option requires FlashBlade REST version 2.20" in msg
        module.exit_json.assert_not_called()
        blade.get_arrays.assert_not_called()
        blade.get_audits.assert_not_called()

    def test_main_rejects_quoted_scope_without_logging_in(self):
        """A quoted scope name is refused before the login, in check mode too"""
        for check_mode in (False, True):
            module = _module(check_mode=check_mode, scopes=["realm1", "o'realm"])
            with patch(MODULE + ".AnsibleModule", return_value=module), patch(
                MODULE + ".get_system"
            ) as get_system, patch(MODULE + ".get_rest_api_version") as get_version:
                try:
                    main()
                except SystemExit:
                    pass

            module.fail_json.assert_called_once_with(
                msg="scopes value o'realm must not contain a single quote"
            )
            module.exit_json.assert_not_called()
            get_system.assert_not_called()
            get_version.assert_not_called()

    def test_main_scoped_read_refused_by_the_array_fails(self):
        """A scope filter the array refuses fails; no unfiltered read follows"""
        module = _module(scopes=["realm1"], newest_first=True, limit=5)
        blade = _blade(status=400)
        _run_main(module, blade)

        blade.get_audits.assert_called_once_with(
            filter="scopes.name='realm1' and system_event='false'",
            limit=5,
            sort=["time-"],
        )
        module.fail_json.assert_called_once()
        assert "Failed to get audit records" in module.fail_json.call_args[1]["msg"]
        module.exit_json.assert_not_called()

    def test_main_rejects_limit_below_one(self):
        """limit must be at least 1"""
        module = _module(limit=0)
        blade = _blade()
        _run_main(module, blade)

        module.fail_json.assert_called_once_with(msg="limit must be at least 1")
        blade.get_audits.assert_not_called()

    def test_main_rejects_quote_before_contacting_the_array(self):
        """A quoted filter value fails before any array request"""
        module = _module(user="o'brien")
        blade = _blade()
        _run_main(module, blade)

        module.fail_json.assert_called_once_with(
            msg="user value o'brien must not contain a single quote"
        )
        blade.get_arrays.assert_not_called()
        blade.get_audits.assert_not_called()

    def test_main_api_error(self):
        """An API error on the listing is surfaced via fail_json"""
        module = _module()
        blade = _blade(status=400)
        _run_main(module, blade)

        module.fail_json.assert_called_once()
        assert "Failed to get audit records" in module.fail_json.call_args[1]["msg"]
        module.exit_json.assert_not_called()

    def test_audit_context_version_constant(self):
        """The 2.28 gate is the version that introduced the fleet context"""
        assert AUDIT_CONTEXT_VERSION == "2.28"

    def test_audit_scopes_version_constant(self):
        """The 2.20 gate is the version that introduced the scopes field"""
        assert audits_module.AUDIT_SCOPES_VERSION == "2.20"
