# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_lifecycle module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from fnmatch import fnmatch
from types import SimpleNamespace
from unittest.mock import Mock, patch, MagicMock

import pytest

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

# Bind the real time helpers so that the durations under test are converted
# for real, not by a MagicMock that accepts anything.
from plugins.module_utils import time_utils as _real_time_utils

sys.modules[
    "ansible_collections.everpure.flashblade.plugins.module_utils.time_utils"
] = _real_time_utils

from plugins.module_utils.version import LooseVersion as RealLooseVersion
import plugins.modules.purefb_lifecycle as lifecycle
from plugins.modules.purefb_lifecycle import main

MOD = "plugins.modules.purefb_lifecycle"
DAY = 86400000
# 2031-01-01 as the module sends it
DATE_2031 = 1924992000000

# The messages of Purity//FB 4.8.8
NO_BUCKET = "Bucket does not exist."
NO_RULE = "Lifecycle rule does not exist."
NO_SUCH_BUCKET = (
    "The specified bucket does not exist. (Service: Amazon S3; Status Code: 404; "
    "Error Code: NoSuchBucket; Request ID: null; S3 Extended Request ID: null; "
    "Proxy: null)"
)
ZERO_PREVIOUS = (
    "'NoncurrentDays' for NoncurrentVersionExpiration action must be a positive "
    "integer (Service: Amazon S3; Status Code: 400; Error Code: InvalidArgument; "
    "Request ID: null; S3 Extended Request ID: null; Proxy: null)"
)
BOTH_CURRENT = (
    '"Keep Current Version For" value and "Keep Current Version Until" value '
    "are mutual exclusive."
)
MANY_NAMES = "Cannot process more than one name at a time."
REFUSED = "Operation not permitted."

SETTINGS = (
    "keep_previous_version_for",
    "keep_current_version_for",
    "keep_current_version_until",
    "abort_incomplete_multipart_uploads_after",
    "prefix",
    "enabled",
)


class _Body(dict):
    """Stand-in for an SDK request model.

    Keeps what it was given and, like the SDK models, reads a field that was
    not set as None.
    """

    def __getattr__(self, item):
        return self.get(item)


def _sent(body):
    """What the SDK puts into the request: fields that are None are left out"""
    return {key: value for key, value in body.items() if value is not None}


def _response(status_code=200, items=None, error=None):
    errors = [SimpleNamespace(message=error)] if error else []
    return SimpleNamespace(status_code=status_code, items=items or [], errors=errors)


def _error_message(res, default="Unknown error"):
    """The real get_error_message of module_utils.common"""
    if getattr(res, "errors", None):
        return res.errors[0].message
    return default


class _Array:
    """A small stateful stand-in for the array.

    It answers the bucket and lifecycle rule requests the way Purity//FB 4.8.8
    does: a bucket name is a pattern and is matched whatever its letter case,
    a comma separates names, a rule name is matched exactly, a rule is changed
    only under the stored spelling of its bucket name, the rules of a
    destroyed bucket are hidden, a zero for the previous versions is refused
    on create, a duration and a date for current versions exclude each other
    and a zero removes a setting on update. POST, PATCH and DELETE change the
    state so that a later GET reads it back. refuse maps a method name to the
    message of a refused request.
    """

    def __init__(self, buckets=("bkt",), destroyed=(), rules=None, fleet=False):
        self.buckets = {
            name: SimpleNamespace(name=name, destroyed=name in destroyed)
            for name in buckets
        }
        self.rules = {}
        for name, settings in (rules or {}).items():
            self.add_rule(name, **settings)
        self.refuse = {}
        self.fleet = fleet
        blade = Mock()
        blade.get_fleets = Mock(side_effect=self._get_fleets)
        blade.get_arrays = Mock(side_effect=self._get_arrays)
        blade.get_buckets = Mock(side_effect=self._get_buckets)
        blade.get_lifecycle_rules = Mock(side_effect=self._get_rules)
        blade.post_lifecycle_rules = Mock(side_effect=self._post)
        blade.patch_lifecycle_rules = Mock(side_effect=self._patch)
        blade.delete_lifecycle_rules = Mock(side_effect=self._delete)
        self.blade = blade

    def add_rule(self, name, **settings):
        """Store a rule as the array returns it; a setting not given is None"""
        bucket, rule_id = name.split("/", 1)
        rule = SimpleNamespace(
            name=name,
            rule_id=rule_id,
            bucket=SimpleNamespace(name=bucket, resource_type="buckets"),
            cleanup_expired_object_delete_marker=True,
        )
        for setting in SETTINGS:
            setattr(rule, setting, settings.get(setting))
        if rule.enabled is None:
            rule.enabled = True
        self.rules[name] = rule
        return rule

    def writes(self):
        """The number of requests that change the array"""
        return (
            self.blade.post_lifecycle_rules.call_count
            + self.blade.patch_lifecycle_rules.call_count
            + self.blade.delete_lifecycle_rules.call_count
        )

    def _bucket(self, name):
        for stored, bucket in self.buckets.items():
            if stored.lower() == name.lower():
                return bucket
        return None

    def _rule(self, name):
        """Return (rule, None) or (None, the message of the array)"""
        bucket_name, sep, rule_id = name.partition("/")
        bucket = self._bucket(bucket_name)
        if not sep or bucket is None:
            return None, NO_BUCKET
        if bucket.destroyed:
            return None, NO_RULE
        rule = self.rules.get(bucket.name + "/" + rule_id)
        if rule is None:
            return None, NO_RULE
        return rule, None

    def _get_fleets(self, **kwargs):
        if "get_fleets" in self.refuse:
            return _response(403, error=self.refuse["get_fleets"])
        return _response(items=[SimpleNamespace(name="fleet1")] if self.fleet else [])

    def _get_arrays(self, **kwargs):
        return _response(items=[SimpleNamespace(name="array1")])

    def _get_buckets(self, names=None, **kwargs):
        if "get_buckets" in self.refuse:
            return _response(403, error=self.refuse["get_buckets"])
        found = []
        for wanted in ",".join(names).split(","):
            matches = [
                bucket
                for stored, bucket in self.buckets.items()
                if fnmatch(stored.lower(), wanted.strip().lower())
            ]
            if not matches:
                return _response(400, error=NO_BUCKET)
            found.extend(matches)
        return _response(items=found)

    def _get_rules(self, names=None, **kwargs):
        if "get_lifecycle_rules" in self.refuse:
            return _response(403, error=self.refuse["get_lifecycle_rules"])
        found = []
        for wanted in ",".join(names).split(","):
            rule, error = self._rule(wanted)
            if rule is None:
                return _response(400, error=error)
            found.append(rule)
        return _response(items=found)

    def _post(self, rule=None, **kwargs):
        if "post_lifecycle_rules" in self.refuse:
            return _response(400, error=self.refuse["post_lifecycle_rules"])
        bucket = self._bucket(rule["bucket"]["name"])
        if bucket is None or bucket.destroyed:
            return _response(400, error=NO_SUCH_BUCKET)
        if rule.get("keep_previous_version_for") == 0:
            return _response(400, error=ZERO_PREVIOUS)
        if rule.get("keep_current_version_for") and rule.get(
            "keep_current_version_until"
        ):
            return _response(400, error=BOTH_CURRENT)
        settings = {key: rule.get(key) or None for key in SETTINGS}
        self.add_rule(bucket.name + "/" + rule["rule_id"], **settings)
        return _response()

    def _patch(self, names=None, lifecycle=None, **kwargs):
        if "patch_lifecycle_rules" in self.refuse:
            return _response(400, error=self.refuse["patch_lifecycle_rules"])
        if len(",".join(names).split(",")) > 1:
            return _response(400, error=MANY_NAMES)
        rule, error = self._rule(names[0])
        if rule is None:
            return _response(400, error=error)
        if rule.name != names[0]:
            return _response(400, error=NO_RULE)
        merged = {key: getattr(rule, key) for key in SETTINGS}
        for key in SETTINGS:
            value = lifecycle.get(key)
            if value is None:
                continue
            # a zero removes a duration or a date
            merged[key] = value if (value or key == "enabled") else None
        if merged["keep_current_version_for"] and merged["keep_current_version_until"]:
            return _response(400, error=BOTH_CURRENT)
        for key, value in merged.items():
            setattr(rule, key, value)
        return _response()

    def _delete(self, names=None, **kwargs):
        if "delete_lifecycle_rules" in self.refuse:
            return _response(400, error=self.refuse["delete_lifecycle_rules"])
        rule, error = self._rule(names[0])
        if rule is None:
            return _response(400, error=error)
        del self.rules[rule.name]
        return _response()


def _params(**overrides):
    params = {
        "state": "present",
        "enabled": True,
        "bucket": "bkt",
        "name": "rule1",
        "prefix": None,
        "keep_previous_for": None,
        "keep_current_for": None,
        "keep_current_until": None,
        "abort_uploads_after": None,
        "context": "",
    }
    params.update(overrides)
    return params


def _module(check_mode=False, **overrides):
    module = Mock()
    module.params = _params(**overrides)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    module.warn = Mock()
    return module


def _helpers(api_version="2.30"):
    """Patch the mocked shared helpers of the module with working ones"""
    return patch.multiple(
        MOD,
        get_rest_api_version=Mock(return_value=api_version),
        get_error_message=_error_message,
        LooseVersion=RealLooseVersion,
        LifecycleRulePost=_Body,
        LifecycleRulePatch=_Body,
        ReferenceWritable=_Body,
        HAS_PYPURECLIENT=True,
    )


def _run(array, check_mode=False, api_version="2.30", **params):
    """Run main() against the array stand-in and return the module"""
    module = _module(check_mode=check_mode, **params)
    with _helpers(api_version), patch(
        MOD + ".AnsibleModule", return_value=module
    ), patch(MOD + ".get_system", return_value=array.blade):
        with pytest.raises(SystemExit):
            main()
    return module


def _changed(module):
    assert not module.fail_json.called, module.fail_json.call_args
    return module.exit_json.call_args[1]["changed"]


def _failure(module):
    assert module.fail_json.called, "the task did not fail"
    return module.fail_json.call_args[1]["msg"]


def _post_body(array):
    return _sent(array.blade.post_lifecycle_rules.call_args[1]["rule"])


def _patch_body(array):
    return _sent(array.blade.patch_lifecycle_rules.call_args[1]["lifecycle"])


class TestHelpers:
    """The private helpers"""

    def test_context_kwargs_without_context(self):
        with _helpers():
            assert lifecycle._context_kwargs(_module(), "2.30") == {}

    def test_context_kwargs_with_context(self):
        with _helpers():
            assert lifecycle._context_kwargs(_module(context="array2"), "2.30") == {
                "context_names": ["array2"]
            }

    def test_context_kwargs_before_fleets(self):
        with _helpers():
            assert lifecycle._context_kwargs(_module(context="array2"), "2.16") == {}

    @pytest.mark.parametrize(
        "value, expected", [("2d", 2 * DAY), ("1w", 7 * DAY), (None, None), ("", None)]
    )
    def test_duration(self, value, expected):
        module = _module(keep_current_for=value)
        assert lifecycle._duration(module, "keep_current_for") == expected

    def test_check_one_name_refuses_a_comma(self):
        module = _module(name="rule1,bkt2/rule1")
        with pytest.raises(SystemExit):
            lifecycle._check_one_name(module, "name", "lifecycle rule")
        msg = module.fail_json.call_args[1]["msg"]
        assert "name rule1,bkt2/rule1 holds a comma" in msg
        assert "one lifecycle rule" in msg

    def test_check_one_name_accepts_one_name(self):
        module = _module(bucket="realm1::bkt")
        lifecycle._check_one_name(module, "bucket", "bucket")
        module.fail_json.assert_not_called()


class TestGetBucket:
    """The bucket look-up takes the bucket that has the name asked for"""

    def _get(self, array, api_version="2.30", **params):
        module = _module(**params)
        with _helpers(api_version):
            return module, lifecycle._get_bucket(module, array.blade, api_version)

    def test_found(self):
        array = _Array(buckets=("bkt", "realm1::bkt"))
        module, bucket = self._get(array, bucket="realm1::bkt")
        assert bucket.name == "realm1::bkt"
        array.blade.get_buckets.assert_called_once_with(names=["realm1::bkt"])

    def test_found_in_another_letter_case(self):
        array = _Array(buckets=("bkt", "realm1::bkt"))
        module, bucket = self._get(array, bucket="REALM1::BKT")
        assert bucket.name == "realm1::bkt"

    def test_missing_is_none(self):
        array = _Array(buckets=("bkt",))
        module, bucket = self._get(array, bucket="realm1::bkt")
        assert bucket is None
        module.fail_json.assert_not_called()

    def test_pattern_is_not_a_bucket(self):
        """The array answers a pattern with the buckets it matches"""
        array = _Array(buckets=("bkt", "bkt2"))
        module, bucket = self._get(array, bucket="bk*")
        assert bucket is None

    def test_pattern_that_matches_one_bucket_is_not_that_bucket(self):
        array = _Array(buckets=("bkt", "realm1::other"))
        module, bucket = self._get(array, bucket="bk*")
        assert bucket is None

    def test_empty_answer_is_none(self):
        array = _Array()
        array.blade.get_buckets = Mock(return_value=_response(200, items=[]))
        module, bucket = self._get(array)
        assert bucket is None

    def test_refused_read_is_reported(self):
        array = _Array()
        array.refuse["get_buckets"] = REFUSED
        module = _module()
        with _helpers(), pytest.raises(SystemExit):
            lifecycle._get_bucket(module, array.blade, "2.30")
        assert module.fail_json.call_args[1]["msg"] == (
            "Failed to read bucket bkt. Error: Operation not permitted."
        )

    def test_context_is_passed(self):
        array = _Array()
        module, bucket = self._get(array, context="array2")
        assert bucket.name == "bkt"
        array.blade.get_buckets.assert_called_once_with(
            names=["bkt"], context_names=["array2"]
        )


class TestGetRule:
    """The rule look-up"""

    def _get(self, array, api_version="2.30", **params):
        module = _module(**params)
        with _helpers(api_version):
            return module, lifecycle._get_rule(module, array.blade, api_version)

    def test_found_in_a_realm(self):
        array = _Array(
            buckets=("bkt", "realm1::bkt"),
            rules={
                "bkt/rule1": {"keep_previous_version_for": 9 * DAY},
                "realm1::bkt/rule1": {"keep_previous_version_for": 2 * DAY},
            },
        )
        module, rule = self._get(array, bucket="realm1::bkt")
        assert rule.name == "realm1::bkt/rule1"
        assert rule.keep_previous_version_for == 2 * DAY
        array.blade.get_lifecycle_rules.assert_called_once_with(
            names=["realm1::bkt/rule1"]
        )

    def test_missing_is_none(self):
        array = _Array()
        module, rule = self._get(array)
        assert rule is None
        module.fail_json.assert_not_called()

    def test_rule_names_differ_by_letter_case(self):
        array = _Array(rules={"bkt/rule1": {"keep_previous_version_for": DAY}})
        module, rule = self._get(array, name="RULE1")
        assert rule is None

    def test_empty_answer_is_none(self):
        array = _Array()
        array.blade.get_lifecycle_rules = Mock(return_value=_response(200, items=[]))
        module, rule = self._get(array)
        assert rule is None

    def test_refused_read_is_reported(self):
        array = _Array()
        array.refuse["get_lifecycle_rules"] = REFUSED
        module = _module(bucket="realm1::bkt")
        with _helpers(), pytest.raises(SystemExit):
            lifecycle._get_rule(module, array.blade, "2.30")
        assert module.fail_json.call_args[1]["msg"] == (
            "Failed to read lifecycle rule rule1 for bucket realm1::bkt. "
            "Error: Operation not permitted."
        )

    def test_context_is_passed(self):
        array = _Array(rules={"bkt/rule1": {"keep_previous_version_for": DAY}})
        module, rule = self._get(array, context="array2")
        assert rule.name == "bkt/rule1"
        array.blade.get_lifecycle_rules.assert_called_once_with(
            names=["bkt/rule1"], context_names=["array2"]
        )


class TestCreate:
    """A rule is created with the settings the task names, and no others"""

    def test_keep_current_for_alone_in_a_realm(self):
        array = _Array(buckets=("bkt", "realm1::bkt"))
        params = {"bucket": "realm1::bkt", "keep_current_for": "7d"}
        assert _changed(_run(array, **params)) is True
        assert _post_body(array) == {
            "bucket": {"name": "realm1::bkt"},
            "rule_id": "rule1",
            "keep_current_version_for": 7 * DAY,
        }
        assert array.rules["realm1::bkt/rule1"].keep_current_version_for == 7 * DAY
        assert "bkt/rule1" not in array.rules
        assert _changed(_run(array, **params)) is False
        assert array.writes() == 1

    def test_abort_uploads_after_alone(self):
        array = _Array()
        params = {"abort_uploads_after": "1d"}
        assert _changed(_run(array, **params)) is True
        assert _post_body(array) == {
            "bucket": {"name": "bkt"},
            "rule_id": "rule1",
            "abort_incomplete_multipart_uploads_after": DAY,
        }
        assert _changed(_run(array, **params)) is False
        assert array.writes() == 1

    def test_keep_current_until_alone(self):
        array = _Array(buckets=("realm1::bkt",))
        params = {"bucket": "realm1::bkt", "keep_current_until": "2031-01-01"}
        assert _changed(_run(array, **params)) is True
        assert _post_body(array) == {
            "bucket": {"name": "realm1::bkt"},
            "rule_id": "rule1",
            "keep_current_version_until": DATE_2031,
        }
        assert array.blade.post_lifecycle_rules.call_args[1]["confirm_date"] is True
        assert _changed(_run(array, **params)) is False
        assert array.writes() == 1

    def test_keep_previous_for_alone(self):
        array = _Array()
        params = {"keep_previous_for": "2d"}
        assert _changed(_run(array, **params)) is True
        assert _post_body(array) == {
            "bucket": {"name": "bkt"},
            "rule_id": "rule1",
            "keep_previous_version_for": 2 * DAY,
        }
        assert "confirm_date" not in array.blade.post_lifecycle_rules.call_args[1]
        assert _changed(_run(array, **params)) is False
        assert array.writes() == 1

    def test_every_setting(self):
        array = _Array()
        params = {
            "keep_previous_for": "2d",
            "keep_current_for": "1w",
            "abort_uploads_after": "1d",
            "prefix": "logs/",
        }
        assert _changed(_run(array, **params)) is True
        assert _post_body(array) == {
            "bucket": {"name": "bkt"},
            "rule_id": "rule1",
            "keep_previous_version_for": 2 * DAY,
            "keep_current_version_for": 7 * DAY,
            "abort_incomplete_multipart_uploads_after": DAY,
            "prefix": "logs/",
        }
        assert _changed(_run(array, **params)) is False

    def test_check_mode_sends_nothing(self):
        array = _Array(buckets=("realm1::bkt",))
        module = _run(
            array, check_mode=True, bucket="realm1::bkt", keep_current_for="7d"
        )
        assert _changed(module) is True
        assert array.writes() == 0
        assert not array.rules

    def test_no_duration_and_no_date_is_refused(self):
        array = _Array()
        module = _run(array, check_mode=True, prefix="logs/")
        assert "At least one parameter is required" in _failure(module)
        assert array.writes() == 0

    def test_created_disabled(self):
        array = _Array(buckets=("realm1::bkt",))
        params = {"bucket": "realm1::bkt", "keep_current_for": "3d", "enabled": False}
        assert _changed(_run(array, **params)) is True
        assert "enabled" not in _post_body(array)
        array.blade.patch_lifecycle_rules.assert_called_once()
        call = array.blade.patch_lifecycle_rules.call_args[1]
        assert call["names"] == ["realm1::bkt/rule1"]
        assert _sent(call["lifecycle"]) == {"enabled": False}
        assert array.rules["realm1::bkt/rule1"].enabled is False
        assert _changed(_run(array, **params)) is False
        assert array.writes() == 2

    def test_created_but_not_disabled_warns(self):
        array = _Array()
        array.refuse["patch_lifecycle_rules"] = REFUSED
        module = _run(array, keep_current_for="3d", enabled=False)
        assert _changed(module) is True
        module.warn.assert_called_once()

    def test_refused_create_is_reported(self):
        array = _Array()
        array.refuse["post_lifecycle_rules"] = REFUSED
        module = _run(array, keep_current_for="7d")
        assert _failure(module) == (
            "Failed to create lifecycle rule rule1 for bucket bkt. "
            "Error: Operation not permitted."
        )

    def test_context_is_passed(self):
        array = _Array()
        module = _run(array, keep_current_for="7d", context="array2")
        assert _changed(module) is True
        for method in ("get_buckets", "get_lifecycle_rules", "post_lifecycle_rules"):
            call = getattr(array.blade, method).call_args[1]
            assert call["context_names"] == ["array2"], method

    def test_context_is_left_out_before_fleets(self):
        array = _Array()
        module = _run(
            array, api_version="2.16", keep_current_for="7d", context="array2"
        )
        assert _changed(module) is True
        array.blade.get_fleets.assert_not_called()
        for method in ("get_buckets", "get_lifecycle_rules", "post_lifecycle_rules"):
            assert "context_names" not in getattr(array.blade, method).call_args[1]

    def test_fleet_member_uses_its_own_name_as_context(self):
        array = _Array(fleet=True)
        module = _run(array, keep_current_for="7d")
        assert _changed(module) is True
        assert module.params["context"] == "array1"
        call = array.blade.post_lifecycle_rules.call_args[1]
        assert call["context_names"] == ["array1"]


class TestUpdate:
    """An existing rule is changed in the settings the task names"""

    @staticmethod
    def _array():
        return _Array(
            buckets=("bkt", "realm1::bkt", "realm2::bkt"),
            rules={
                "bkt/rule1": {"keep_previous_version_for": 9 * DAY},
                "realm1::bkt/rule1": {"keep_previous_version_for": 2 * DAY},
                "realm2::bkt/rule1": {"keep_previous_version_for": 5 * DAY},
            },
        )

    def test_same_values_change_nothing(self):
        array = self._array()
        module = _run(array, bucket="realm1::bkt", keep_previous_for="2d")
        assert _changed(module) is False
        assert array.writes() == 0

    def test_duration_in_a_realm_leaves_the_namesakes_alone(self):
        array = self._array()
        params = {"bucket": "realm1::bkt", "keep_previous_for": "3d"}
        assert _changed(_run(array, **params)) is True
        call = array.blade.patch_lifecycle_rules.call_args[1]
        assert call["names"] == ["realm1::bkt/rule1"]
        assert "confirm_date" not in call
        assert _sent(call["lifecycle"]) == {
            "keep_previous_version_for": 3 * DAY,
            "enabled": True,
        }
        assert array.rules["realm1::bkt/rule1"].keep_previous_version_for == 3 * DAY
        assert array.rules["bkt/rule1"].keep_previous_version_for == 9 * DAY
        assert array.rules["realm2::bkt/rule1"].keep_previous_version_for == 5 * DAY
        assert _changed(_run(array, **params)) is False
        assert array.writes() == 1

    def test_array_level_rule_leaves_the_realm_rule_alone(self):
        array = self._array()
        params = {"keep_previous_for": "4d"}
        assert _changed(_run(array, **params)) is True
        assert array.blade.patch_lifecycle_rules.call_args[1]["names"] == ["bkt/rule1"]
        assert array.rules["bkt/rule1"].keep_previous_version_for == 4 * DAY
        assert array.rules["realm1::bkt/rule1"].keep_previous_version_for == 2 * DAY
        assert _changed(_run(array, **params)) is False

    def test_check_mode_sends_nothing(self):
        array = self._array()
        module = _run(
            array, check_mode=True, bucket="realm1::bkt", keep_previous_for="3d"
        )
        assert _changed(module) is True
        assert array.writes() == 0

    def test_settings_not_named_are_kept(self):
        array = self._array()
        params = {
            "bucket": "realm1::bkt",
            "keep_current_for": "7d",
            "abort_uploads_after": "1d",
        }
        assert _changed(_run(array, **params)) is True
        assert _patch_body(array) == {
            "keep_previous_version_for": 2 * DAY,
            "keep_current_version_for": 7 * DAY,
            "abort_incomplete_multipart_uploads_after": DAY,
            "enabled": True,
        }
        assert _changed(_run(array, **params)) is False
        rule = array.rules["realm1::bkt/rule1"]
        assert rule.keep_previous_version_for == 2 * DAY
        assert rule.keep_current_version_for == 7 * DAY

    def test_prefix(self):
        array = self._array()
        params = {"bucket": "realm1::bkt", "prefix": "logs/"}
        assert _changed(_run(array, **params)) is True
        assert array.rules["realm1::bkt/rule1"].prefix == "logs/"
        assert _changed(_run(array, **params)) is False

    def test_disable_and_enable(self):
        array = self._array()
        params = {"bucket": "realm1::bkt", "enabled": False}
        assert _changed(_run(array, **params)) is True
        assert array.rules["realm1::bkt/rule1"].enabled is False
        assert _changed(_run(array, **params)) is False
        params["enabled"] = True
        assert _changed(_run(array, **params)) is True
        assert array.rules["realm1::bkt/rule1"].enabled is True
        assert _changed(_run(array, **params)) is False

    def test_date_takes_the_place_of_a_duration(self):
        array = _Array(
            buckets=("realm1::bkt",),
            rules={
                "realm1::bkt/rule1": {
                    "keep_previous_version_for": 2 * DAY,
                    "keep_current_version_for": 7 * DAY,
                }
            },
        )
        params = {"bucket": "realm1::bkt", "keep_current_until": "2031-01-01"}
        assert _changed(_run(array, check_mode=True, **params)) is True
        assert array.writes() == 0
        assert _changed(_run(array, **params)) is True
        call = array.blade.patch_lifecycle_rules.call_args[1]
        assert call["confirm_date"] is True
        assert _sent(call["lifecycle"]) == {
            "keep_previous_version_for": 2 * DAY,
            "keep_current_version_for": 0,
            "keep_current_version_until": DATE_2031,
            "enabled": True,
        }
        rule = array.rules["realm1::bkt/rule1"]
        assert rule.keep_current_version_for is None
        assert rule.keep_current_version_until == DATE_2031
        assert _changed(_run(array, **params)) is False
        assert array.writes() == 1

    def test_duration_takes_the_place_of_a_date(self):
        array = _Array(
            rules={"bkt/rule1": {"keep_current_version_until": DATE_2031}},
        )
        params = {"keep_current_for": "5d"}
        assert _changed(_run(array, check_mode=True, **params)) is True
        assert array.writes() == 0
        assert _changed(_run(array, **params)) is True
        call = array.blade.patch_lifecycle_rules.call_args[1]
        assert "confirm_date" not in call
        assert _sent(call["lifecycle"]) == {
            "keep_current_version_for": 5 * DAY,
            "keep_current_version_until": 0,
            "enabled": True,
        }
        rule = array.rules["bkt/rule1"]
        assert rule.keep_current_version_for == 5 * DAY
        assert rule.keep_current_version_until is None
        assert _changed(_run(array, **params)) is False
        assert array.writes() == 1

    def test_same_date_changes_nothing(self):
        array = _Array(
            rules={"bkt/rule1": {"keep_current_version_until": DATE_2031}},
        )
        module = _run(array, keep_current_until="2031-01-01")
        assert _changed(module) is False
        assert array.writes() == 0

    def test_other_setting_of_a_rule_with_a_date_confirms_the_date(self):
        array = _Array(
            rules={"bkt/rule1": {"keep_current_version_until": DATE_2031}},
        )
        assert _changed(_run(array, keep_previous_for="2d")) is True
        call = array.blade.patch_lifecycle_rules.call_args[1]
        assert call["confirm_date"] is True
        assert _sent(call["lifecycle"]) == {
            "keep_previous_version_for": 2 * DAY,
            "keep_current_version_until": DATE_2031,
            "enabled": True,
        }

    def test_refused_update_is_reported(self):
        array = self._array()
        array.refuse["patch_lifecycle_rules"] = REFUSED
        module = _run(array, bucket="realm1::bkt", keep_previous_for="3d")
        assert _failure(module) == (
            "Failed to update lifecycle rule rule1 for bucket realm1::bkt. "
            "Error: Operation not permitted."
        )

    def test_context_is_passed(self):
        array = self._array()
        module = _run(array, keep_previous_for="4d", context="array2")
        assert _changed(module) is True
        call = array.blade.patch_lifecycle_rules.call_args[1]
        assert call["context_names"] == ["array2"]


class TestDelete:
    """state=absent"""

    @staticmethod
    def _array():
        return _Array(
            buckets=("bkt", "realm1::bkt"),
            rules={
                "bkt/rule1": {"keep_previous_version_for": 9 * DAY},
                "realm1::bkt/rule1": {"keep_previous_version_for": 2 * DAY},
            },
        )

    def test_delete_in_a_realm_twice(self):
        array = self._array()
        params = {"bucket": "realm1::bkt", "state": "absent"}
        assert _changed(_run(array, **params)) is True
        array.blade.delete_lifecycle_rules.assert_called_once_with(
            names=["realm1::bkt/rule1"]
        )
        assert sorted(array.rules) == ["bkt/rule1"]
        assert _changed(_run(array, **params)) is False
        assert array.writes() == 1

    def test_delete_at_array_level_twice(self):
        array = self._array()
        params = {"state": "absent"}
        assert _changed(_run(array, **params)) is True
        assert sorted(array.rules) == ["realm1::bkt/rule1"]
        assert _changed(_run(array, **params)) is False

    def test_check_mode_sends_nothing(self):
        array = self._array()
        module = _run(array, check_mode=True, bucket="realm1::bkt", state="absent")
        assert _changed(module) is True
        assert array.writes() == 0
        assert len(array.rules) == 2

    def test_refused_delete_is_reported(self):
        array = self._array()
        array.refuse["delete_lifecycle_rules"] = REFUSED
        module = _run(array, state="absent")
        assert _failure(module) == (
            "Failed to delete lifecycle rule rule1 for bucket bkt. "
            "Error: Operation not permitted."
        )

    def test_context_is_passed(self):
        array = self._array()
        module = _run(array, state="absent", context="array2")
        assert _changed(module) is True
        array.blade.delete_lifecycle_rules.assert_called_once_with(
            names=["bkt/rule1"], context_names=["array2"]
        )


class TestNames:
    """A task is about one rule of one bucket"""

    @staticmethod
    def _array():
        return _Array(
            buckets=("bkt", "bkt2", "realm1::bkt"),
            rules={
                "bkt/rule1": {"keep_previous_version_for": 2 * DAY},
                "bkt/rule2": {"keep_previous_version_for": 5 * DAY},
                "bkt2/rule1": {"keep_previous_version_for": 4 * DAY},
                "realm1::bkt/rule1": {"keep_previous_version_for": 3 * DAY},
            },
        )

    @pytest.mark.parametrize("check_mode", [True, False])
    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_list_in_the_rule_name_is_refused(self, state, check_mode):
        array = self._array()
        module = _module(
            check_mode=check_mode,
            state=state,
            name="rule1,bkt2/rule1",
            keep_previous_for="30d",
        )
        get_system = Mock(return_value=array.blade)
        with _helpers(), patch(MOD + ".AnsibleModule", return_value=module), patch(
            MOD + ".get_system", get_system
        ):
            with pytest.raises(SystemExit):
                main()
        assert "name rule1,bkt2/rule1 holds a comma" in _failure(module)
        get_system.assert_not_called()
        assert array.writes() == 0

    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_list_of_buckets_is_refused(self, state):
        array = self._array()
        module = _run(
            array,
            check_mode=True,
            state=state,
            bucket="bkt,bkt2",
            keep_previous_for="30d",
        )
        msg = _failure(module)
        assert "bucket bkt,bkt2 holds a comma" in msg
        assert "one bucket" in msg
        array.blade.get_buckets.assert_not_called()

    @pytest.mark.parametrize("check_mode", [True, False])
    @pytest.mark.parametrize("state", ["present", "absent"])
    @pytest.mark.parametrize("bucket", ["bk*", "*bkt", "realm1::*"])
    def test_pattern_for_the_bucket_is_refused(self, bucket, state, check_mode):
        array = self._array()
        module = _run(
            array,
            check_mode=check_mode,
            state=state,
            bucket=bucket,
            keep_previous_for="30d",
        )
        assert _failure(module) == "Specified bucket {0} does not exist".format(bucket)
        array.blade.get_lifecycle_rules.assert_not_called()
        assert array.writes() == 0

    def test_bucket_in_another_letter_case_is_the_same_bucket(self):
        """The array changes a rule only under the stored spelling"""
        array = self._array()
        module = _run(array, bucket="REALM1::BKT", keep_previous_for="3d")
        assert _changed(module) is False
        module = _run(array, bucket="REALM1::BKT", keep_previous_for="6d")
        assert _changed(module) is True
        assert module.params["bucket"] == "realm1::bkt"
        call = array.blade.patch_lifecycle_rules.call_args[1]
        assert call["names"] == ["realm1::bkt/rule1"]
        assert array.rules["realm1::bkt/rule1"].keep_previous_version_for == 6 * DAY
        assert array.rules["bkt/rule1"].keep_previous_version_for == 2 * DAY
        module = _run(array, bucket="REALM1::BKT", keep_previous_for="6d")
        assert _changed(module) is False

    def test_create_and_delete_use_the_stored_bucket_name(self):
        array = self._array()
        params = {"bucket": "Realm1::Bkt", "name": "rule9", "keep_current_for": "2d"}
        assert _changed(_run(array, **params)) is True
        assert _post_body(array)["bucket"] == {"name": "realm1::bkt"}
        assert "realm1::bkt/rule9" in array.rules
        assert _changed(_run(array, **params)) is False
        params["state"] = "absent"
        assert _changed(_run(array, **params)) is True
        array.blade.delete_lifecycle_rules.assert_called_once_with(
            names=["realm1::bkt/rule9"]
        )
        assert _changed(_run(array, **params)) is False

    def test_failure_names_the_bucket_as_the_array_stores_it(self):
        array = self._array()
        array.refuse["patch_lifecycle_rules"] = REFUSED
        module = _run(array, bucket="BKT", keep_previous_for="6d")
        assert _failure(module) == (
            "Failed to update lifecycle rule rule1 for bucket bkt. "
            "Error: Operation not permitted."
        )


class TestBucket:
    """The bucket has to exist, and to be live for a new or changed rule"""

    @pytest.mark.parametrize("bucket", ["nope", "realm1::bkt", "zznorealm::bkt"])
    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_missing_bucket(self, state, bucket):
        array = _Array(buckets=("bkt",))
        module = _run(array, state=state, bucket=bucket, keep_previous_for="2d")
        assert _failure(module) == "Specified bucket {0} does not exist".format(bucket)
        assert array.writes() == 0

    def test_bare_name_is_not_the_bucket_of_a_realm(self):
        """Only the realm bucket exists; the bare name is not resolved to it"""
        array = _Array(buckets=("realm1::bkt",))
        module = _run(array, bucket="bkt", keep_previous_for="2d")
        assert _failure(module) == "Specified bucket bkt does not exist"
        assert not array.rules

    @pytest.mark.parametrize("state", ["present", "absent"])
    def test_refused_read_of_the_bucket_is_not_a_missing_bucket(self, state):
        array = _Array()
        array.refuse["get_buckets"] = REFUSED
        module = _run(array, state=state, keep_previous_for="2d")
        assert _failure(module) == (
            "Failed to read bucket bkt. Error: Operation not permitted."
        )
        assert array.writes() == 0

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_refused_read_of_the_rule_is_not_a_missing_rule(self, check_mode):
        array = _Array(
            buckets=("realm1::bkt",),
            rules={"realm1::bkt/rule1": {"keep_previous_version_for": 2 * DAY}},
        )
        array.refuse["get_lifecycle_rules"] = REFUSED
        module = _run(
            array, check_mode=check_mode, bucket="realm1::bkt", keep_previous_for="3d"
        )
        assert _failure(module) == (
            "Failed to read lifecycle rule rule1 for bucket realm1::bkt. "
            "Error: Operation not permitted."
        )
        assert array.writes() == 0

    def test_refused_read_of_the_rule_with_state_absent(self):
        array = _Array(rules={"bkt/rule1": {"keep_previous_version_for": 2 * DAY}})
        array.refuse["get_lifecycle_rules"] = REFUSED
        module = _run(array, state="absent")
        assert "Failed to read lifecycle rule rule1 for bucket bkt" in _failure(module)

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_rule_for_a_destroyed_bucket_is_refused(self, check_mode):
        array = _Array(buckets=("bkt", "bkt2"), destroyed=("bkt2",))
        module = _run(
            array, check_mode=check_mode, bucket="bkt2", keep_previous_for="2d"
        )
        msg = _failure(module)
        assert msg.startswith("Specified bucket bkt2 is destroyed.")
        array.blade.get_lifecycle_rules.assert_not_called()
        assert array.writes() == 0

    def test_absent_on_a_destroyed_bucket_changes_nothing(self):
        array = _Array(
            buckets=("bkt", "bkt2"),
            destroyed=("bkt2",),
            rules={"bkt2/rule1": {"keep_previous_version_for": 2 * DAY}},
        )
        module = _run(array, bucket="bkt2", state="absent")
        assert _changed(module) is False
        assert array.writes() == 0

    def test_live_bucket_of_a_realm_with_a_destroyed_namesake(self):
        array = _Array(buckets=("bkt", "realm1::bkt"), destroyed=("bkt",))
        module = _run(array, bucket="realm1::bkt", keep_previous_for="2d")
        assert _changed(module) is True
        assert sorted(array.rules) == ["realm1::bkt/rule1"]


class TestOptions:
    """Option checks made before anything is read or written"""

    @pytest.mark.parametrize(
        "option", ["keep_previous_for", "keep_current_for", "abort_uploads_after"]
    )
    def test_duration_unit(self, option):
        array = _Array()
        module = _run(array, **{option: "3h"})
        assert _failure(module) == (
            "'{0}' format incorrect - specify as 'd' or 'w'".format(option)
        )
        array.blade.get_buckets.assert_not_called()

    def test_date_format(self):
        array = _Array()
        module = _run(array, keep_current_until="01/01/2031")
        assert _failure(module) == "Incorrect data format, should be YYYY-MM-DD"
        assert array.writes() == 0

    def test_date_in_the_past_warns(self):
        array = _Array()
        module = _run(array, keep_current_until="2020-01-01")
        assert _changed(module) is True
        module.warn.assert_called_once()

    def test_sdk_is_required(self):
        array = _Array()
        module = _module(keep_previous_for="2d")
        with _helpers(), patch(MOD + ".HAS_PYPURECLIENT", False), patch(
            MOD + ".AnsibleModule", return_value=module
        ), patch(MOD + ".get_system", return_value=array.blade):
            with pytest.raises(SystemExit):
                main()
        assert "py-pure-client sdk is required" in _failure(module)
