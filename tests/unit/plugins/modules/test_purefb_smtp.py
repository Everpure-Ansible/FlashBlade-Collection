# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_smtp module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from contextlib import ExitStack
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

from plugins.module_utils.version import LooseVersion as RealLooseVersion
from plugins.modules.purefb_smtp import main

MOD = "plugins.modules.purefb_smtp"
REFUSED = "Operation not permitted."
RATE_LIMITED = "API rate limit exceeded"
READ_FAILED = "Failed to read the SMTP configuration. Error: {0}"
WRITE_FAILED = "Failed to set SMTP configuration. Error: {0}"
NO_CONFIGURATION = "The array returned no SMTP configuration."
DOMAIN = "example.com"
OTHER_DOMAIN = "example.org"
RELAY = "smtp.example.com"
OTHER_RELAY = "relay.example.net:2525"


class ExitJson(Exception):
    """Raised by the exit_json stand-in: the real one ends the module."""


class FailJson(Exception):
    """Raised by the fail_json stand-in: the real one ends the module."""


def _module(check_mode=False, **params):
    module = Mock()
    module.params = {"host": None, "domain": DOMAIN, "encryption": None}
    module.params.update(params)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=ExitJson)
    module.fail_json = Mock(side_effect=FailJson)
    return module


def _smtp(sender_domain=DOMAIN, relay_host=None, encryption_mode=None):
    """The SMTP configuration as the array returns it.

    A relay host or an encryption mode that is not set is null.
    """
    return SimpleNamespace(
        id="10000000-0000-4000-8000-000000000001",
        name="management",
        encryption_mode=encryption_mode,
        relay_host=relay_host,
        sender_domain=sender_domain,
    )


def _valid(items):
    """A response to a request the array accepted."""
    res = Mock(spec=["status_code", "items", "total_item_count", "headers"])
    res.status_code = 200
    res.items = list(items)
    res.total_item_count = len(res.items)
    res.headers = {}
    return res


def _error(message=REFUSED, status_code=400):
    """A response to a request the array refused: it carries no items."""
    res = Mock(spec=["status_code", "errors", "headers"])
    res.status_code = status_code
    res.errors = []
    if message is not None:
        res.errors = [
            SimpleNamespace(context=None, location_context=None, message=message)
        ]
    res.headers = {}
    return res


def _error_message(response, default="Unknown error"):
    """What get_error_message of module_utils returns for a response."""
    errors = list(getattr(response, "errors", None) or [])
    return errors[0].message if errors else default


def _blade(smtp=None, read=None, write=None):
    """An array that holds the SMTP configuration smtp.

    read replaces the answer of GET /smtp-servers, write the answer of PATCH
    /smtp-servers.
    """
    blade = Mock()
    blade.get_smtp_servers.return_value = (
        read if read is not None else _valid([smtp if smtp is not None else _smtp()])
    )
    blade.patch_smtp_servers.return_value = (
        write if write is not None else _valid([_smtp()])
    )
    return blade


def _run(module, blade, api_version="2.30", sdk=True):
    """Run main() against the stand-ins and return how the module ended.

    SmtpServer is replaced by a function that returns its keyword arguments,
    so the body of a PATCH can be compared.
    """
    with ExitStack() as stack:
        ansible_module = stack.enter_context(
            patch(MOD + ".AnsibleModule", return_value=module)
        )
        stack.enter_context(patch(MOD + ".purefb_argument_spec", return_value={}))
        stack.enter_context(patch(MOD + ".get_system", return_value=blade))
        stack.enter_context(
            patch(MOD + ".get_rest_api_version", return_value=api_version)
        )
        stack.enter_context(
            patch(MOD + ".get_error_message", side_effect=_error_message)
        )
        stack.enter_context(patch(MOD + ".LooseVersion", RealLooseVersion))
        stack.enter_context(patch(MOD + ".HAS_PYPURECLIENT", sdk))
        stack.enter_context(
            patch(MOD + ".SmtpServer", side_effect=lambda **kwargs: kwargs)
        )
        outcome = None
        try:
            main()
        except ExitJson:
            outcome = "exit"
        except FailJson:
            outcome = "fail"
    assert outcome is not None, "main() ended without exit_json or fail_json"
    return SimpleNamespace(outcome=outcome, ansible_module=ansible_module)


def _failure(module):
    """The message of the single fail_json call of a run that failed."""
    module.fail_json.assert_called_once()
    module.exit_json.assert_not_called()
    return module.fail_json.call_args[1]["msg"]


def _result(module):
    """The keyword arguments of the single exit_json call of a run."""
    module.exit_json.assert_called_once()
    module.fail_json.assert_not_called()
    return module.exit_json.call_args[1]


def _sent(blade):
    """The body of the single PATCH /smtp-servers of a run."""
    blade.patch_smtp_servers.assert_called_once()
    assert list(blade.patch_smtp_servers.call_args[1]) == ["smtp"]
    return blade.patch_smtp_servers.call_args[1]["smtp"]


# Tasks of every kind: each of them starts with the same read.
TASKS = [
    {},
    {"domain": OTHER_DOMAIN},
    {"host": RELAY},
    {"host": ""},
    {"encryption": "starttls"},
    {"encryption": ""},
]


class TestPurefbSmtpRead:
    """A read of the SMTP configuration the array refuses or fails is reported."""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("params", TASKS)
    def test_refused_read_reports_the_answer_of_the_array(self, params, check_mode):
        """An identity that may not read the SMTP configuration is refused."""
        module = _module(check_mode=check_mode, **params)
        blade = _blade(read=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == READ_FAILED.format(REFUSED)
        blade.patch_smtp_servers.assert_not_called()

    # The SDK builds one error from the message of a 403 or 429 answer; any
    # other answer without an error list carries no errors.
    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize(
        "message, status_code, reported",
        [
            (REFUSED, 403, REFUSED),
            (RATE_LIMITED, 429, RATE_LIMITED),
            (None, 500, "Unknown error"),
            ("Service unavailable.", 503, "Service unavailable."),
        ],
    )
    def test_failed_read_sends_nothing(
        self, message, status_code, reported, check_mode
    ):
        """A read that fails says nothing about the configuration."""
        module = _module(
            check_mode=check_mode,
            domain=OTHER_DOMAIN,
            host=RELAY,
            encryption="starttls",
        )
        blade = _blade(read=_error(message, status_code=status_code))
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == READ_FAILED.format(reported)
        blade.patch_smtp_servers.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_read_without_configuration(self, check_mode):
        """An answer that holds no configuration is not compared with the task."""
        module = _module(check_mode=check_mode, domain=OTHER_DOMAIN)
        blade = _blade(read=_valid([]))
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == NO_CONFIGURATION
        blade.patch_smtp_servers.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("params", TASKS)
    def test_configuration_is_read_once_by_name(self, params, check_mode):
        module = _module(check_mode=check_mode, **params)
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        blade.get_smtp_servers.assert_called_once_with(names=["management"])


class TestPurefbSmtpUnchanged:
    """A task that asks for what the array holds sends nothing."""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize(
        "held, params",
        [
            ({}, {}),
            ({}, {"host": ""}),
            ({}, {"encryption": ""}),
            ({"relay_host": RELAY}, {"host": RELAY}),
            ({"encryption_mode": "starttls"}, {"encryption": "starttls"}),
            # an option the task leaves out keeps what the array holds
            ({"relay_host": RELAY, "encryption_mode": "starttls"}, {}),
            (
                {"relay_host": RELAY, "encryption_mode": "starttls"},
                {"host": RELAY, "encryption": "starttls"},
            ),
        ],
    )
    def test_no_difference(self, held, params, check_mode):
        module = _module(check_mode=check_mode, **params)
        blade = _blade(smtp=_smtp(**held))
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": False}
        blade.patch_smtp_servers.assert_not_called()


# (what the array holds, the task, the body of the PATCH)
CHANGES = [
    ({}, {"domain": OTHER_DOMAIN}, {"sender_domain": OTHER_DOMAIN}),
    (
        {"relay_host": RELAY, "encryption_mode": "starttls"},
        {"domain": OTHER_DOMAIN},
        {
            "sender_domain": OTHER_DOMAIN,
            "relay_host": RELAY,
            "encryption_mode": "starttls",
        },
    ),
    ({}, {"host": RELAY}, {"sender_domain": DOMAIN, "relay_host": RELAY}),
    (
        {"relay_host": RELAY},
        {"host": OTHER_RELAY},
        {"sender_domain": DOMAIN, "relay_host": OTHER_RELAY},
    ),
    (
        {"relay_host": RELAY},
        {"host": ""},
        {"sender_domain": DOMAIN, "relay_host": ""},
    ),
    (
        {},
        {"encryption": "starttls"},
        {"sender_domain": DOMAIN, "encryption_mode": "starttls"},
    ),
    (
        {"encryption_mode": "starttls"},
        {"encryption": ""},
        {"sender_domain": DOMAIN, "encryption_mode": ""},
    ),
    (
        {},
        {"domain": OTHER_DOMAIN, "host": RELAY, "encryption": "starttls"},
        {
            "sender_domain": OTHER_DOMAIN,
            "relay_host": RELAY,
            "encryption_mode": "starttls",
        },
    ),
]


class TestPurefbSmtpChange:
    """A difference is sent in one PATCH, and only predicted in check mode."""

    @pytest.mark.parametrize("held, params, body", CHANGES)
    def test_real_run_sends_the_difference(self, held, params, body):
        """The body holds the sender domain and each field asked for or held."""
        module = _module(**params)
        blade = _blade(smtp=_smtp(**held))
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        assert _sent(blade) == body

    @pytest.mark.parametrize("held, params, body", CHANGES)
    def test_check_mode_sends_nothing(self, held, params, body):
        module = _module(check_mode=True, **params)
        blade = _blade(smtp=_smtp(**held))
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        blade.patch_smtp_servers.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_encryption_needs_rest_2_15(self, check_mode):
        """The version is checked before the configuration is read."""
        module = _module(check_mode=check_mode, encryption="starttls")
        blade = _blade()
        assert _run(module, blade, api_version="2.14").outcome == "fail"
        assert _failure(module) == "Purity//FB must be upgraded to support encryption."
        blade.get_smtp_servers.assert_not_called()
        blade.patch_smtp_servers.assert_not_called()

    def test_encryption_is_not_sent_before_rest_2_15(self):
        module = _module(domain=OTHER_DOMAIN, encryption="")
        blade = _blade()
        assert _run(module, blade, api_version="2.14").outcome == "exit"
        assert _result(module) == {"changed": True}
        assert _sent(blade) == {"sender_domain": OTHER_DOMAIN}


class TestPurefbSmtpWrite:
    """A write the array refuses or fails is reported with its message."""

    @pytest.mark.parametrize(
        "message, status_code, reported",
        [
            (REFUSED, 400, REFUSED),
            (None, 500, "Unknown error"),
            ("Service unavailable.", 503, "Service unavailable."),
        ],
    )
    def test_failed_write(self, message, status_code, reported):
        module = _module(domain=OTHER_DOMAIN)
        blade = _blade(write=_error(message, status_code=status_code))
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == WRITE_FAILED.format(reported)
        blade.patch_smtp_servers.assert_called_once()


class TestPurefbSmtpMain:
    """Argument handling and the SDK requirement."""

    def test_argument_spec(self):
        module = _module()
        run = _run(module, _blade())
        args, kwargs = run.ansible_module.call_args
        assert args == (
            {
                "host": {"type": "str"},
                "domain": {"type": "str", "required": True},
                "encryption": {"type": "str", "choices": ["starttls", ""]},
            },
        )
        assert kwargs == {"supports_check_mode": True}

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_sdk_is_required(self, check_mode):
        module = _module(check_mode=check_mode, domain=OTHER_DOMAIN)
        blade = _blade()
        assert _run(module, blade, sdk=False).outcome == "fail"
        assert _failure(module) == "py-pure-client SDK is required for this module"
        blade.get_smtp_servers.assert_not_called()
        blade.patch_smtp_servers.assert_not_called()
