# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_snmp_agent module."""

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

from plugins.modules.purefb_snmp_agent import _readable, main

MOD = "plugins.modules.purefb_snmp_agent"
REFUSED = "Operation not permitted."
READ_FAILED = "Failed to get configuration for SNMP agent. Error: {0}"
NO_AGENT = "The array returned no SNMP agent."
V2C_FAILED = "Failed to update v2c SNMP agent. Error: {0}"
V3_FAILED = "Failed to update v3 SNMP agent. Error: {0}"
MASKED = "****"
USER = "snmp-user"
OTHER_USER = "other-user"
COMMUNITY = "example-community"
AUTH_PASSPHRASE = "auth-passphrase"
PRIVACY_PASSPHRASE = "privacy-passphrase"


class ExitJson(Exception):
    """Raised by the exit_json stand-in: the real one ends the module."""


class FailJson(Exception):
    """Raised by the fail_json stand-in: the real one ends the module."""


def _module(check_mode=False, **params):
    module = Mock()
    module.params = {
        "user": None,
        "auth_passphrase": None,
        "auth_protocol": None,
        "privacy_passphrase": None,
        "privacy_protocol": None,
        "version": None,
        "community": None,
    }
    module.params.update(params)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=ExitJson)
    module.fail_json = Mock(side_effect=FailJson)
    return module


def _agent(
    version="v3",
    user=USER,
    auth_protocol="SHA",
    privacy_protocol="DES",
    community=MASKED,
):
    """The SNMP agent as the array returns it.

    The secrets are masked: the passphrases of a protocol that is set and
    the community string read "****". The block of the version that is not
    in use holds nothing.
    """
    v2c = {}
    v3 = {}
    if version == "v3":
        v3["user"] = user
        if auth_protocol:
            v3["auth_protocol"] = auth_protocol
            v3["auth_passphrase"] = MASKED
        if privacy_protocol:
            v3["privacy_protocol"] = privacy_protocol
            v3["privacy_passphrase"] = MASKED
    else:
        v2c["community"] = community
    return SimpleNamespace(
        id="10000000-0000-4000-8000-000000000001",
        name="management",
        engine_id="80009e2205158554fcc5ba07e43b8ace",
        v2c=SimpleNamespace(**v2c),
        v3=SimpleNamespace(**v3),
        version=version,
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


def _blade(agent=None, read=None, write=None):
    """An array that holds the SNMP agent agent.

    read replaces the answer of GET /snmp-agents, write the answer of PATCH
    /snmp-agents.
    """
    blade = Mock()
    blade.get_snmp_agents.return_value = (
        read if read is not None else _valid([agent if agent is not None else _agent()])
    )
    blade.patch_snmp_agents.return_value = (
        write if write is not None else _valid([_agent()])
    )
    return blade


def _run(module, blade, sdk=True):
    """Run main() against the stand-ins and return how the module ended.

    SnmpAgent, SnmpV2c and SnmpV3 are replaced by functions that return
    their keyword arguments, so the body of a PATCH can be compared.
    """
    with ExitStack() as stack:
        ansible_module = stack.enter_context(
            patch(MOD + ".AnsibleModule", return_value=module)
        )
        stack.enter_context(patch(MOD + ".purefb_argument_spec", return_value={}))
        stack.enter_context(patch(MOD + ".get_system", return_value=blade))
        stack.enter_context(
            patch(MOD + ".get_error_message", side_effect=_error_message)
        )
        stack.enter_context(patch(MOD + ".HAS_PYPURECLIENT", sdk))
        for model in ("SnmpAgent", "SnmpV2c", "SnmpV3"):
            stack.enter_context(
                patch(MOD + "." + model, side_effect=lambda **kwargs: kwargs)
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
    """The body of the single PATCH /snmp-agents of a run."""
    blade.patch_snmp_agents.assert_called_once()
    assert list(blade.patch_snmp_agents.call_args[1]) == ["snmp_agent"]
    return blade.patch_snmp_agents.call_args[1]["snmp_agent"]


def _v3_body(
    user=None,
    auth_protocol=None,
    auth_passphrase=None,
    privacy_protocol=None,
    privacy_passphrase=None,
):
    """The body of a PATCH that sets the v3 agent: the options of the task."""
    return {
        "version": "v3",
        "v3": {
            "auth_protocol": auth_protocol,
            "auth_passphrase": auth_passphrase,
            "privacy_protocol": privacy_protocol,
            "privacy_passphrase": privacy_passphrase,
            "user": user,
        },
    }


def _v2c_body(community):
    """The body of a PATCH that sets the v2c agent."""
    return {"version": "v2c", "v2c": {"community": community}}


V3_FULL = {
    "version": "v3",
    "user": USER,
    "auth_protocol": "SHA",
    "auth_passphrase": AUTH_PASSPHRASE,
    "privacy_protocol": "DES",
    "privacy_passphrase": PRIVACY_PASSPHRASE,
}

# Tasks of every kind: each of them starts with the same read.
TASKS = [
    {},
    {"version": "v3", "user": USER},
    {"version": "v3", "user": OTHER_USER},
    {"version": "v2c", "community": COMMUNITY},
    V3_FULL,
]


class TestPurefbSnmpAgentRead:
    """A read of the SNMP agent the array refuses or fails is reported."""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("params", TASKS)
    def test_refused_read_reports_the_answer_of_the_array(self, params, check_mode):
        """An identity that may not read the SNMP agent is told so."""
        module = _module(check_mode=check_mode, **params)
        blade = _blade(read=_error())
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == READ_FAILED.format(REFUSED)
        blade.patch_snmp_agents.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize(
        "message, status_code, reported",
        [
            (REFUSED, 403, REFUSED),
            (None, 429, "Unknown error"),
            (None, 500, "Unknown error"),
            ("Service unavailable.", 503, "Service unavailable."),
        ],
    )
    def test_failed_read_sends_nothing(
        self, message, status_code, reported, check_mode
    ):
        """A read that fails says nothing about the agent."""
        module = _module(check_mode=check_mode, version="v3", user=OTHER_USER)
        blade = _blade(read=_error(message, status_code=status_code))
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == READ_FAILED.format(reported)
        blade.patch_snmp_agents.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("params", TASKS)
    def test_read_without_agent(self, params, check_mode):
        """An answer that holds no agent is not compared with the task."""
        module = _module(check_mode=check_mode, **params)
        blade = _blade(read=_valid([]))
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == NO_AGENT
        blade.patch_snmp_agents.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize("params", TASKS)
    def test_agent_is_read_once(self, params, check_mode):
        module = _module(check_mode=check_mode, **params)
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        blade.get_snmp_agents.assert_called_once_with()


class TestPurefbSnmpAgentUnchanged:
    """A task that asks for what the array holds sends nothing."""

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize(
        "held, params",
        [
            ({}, {}),
            ({}, {"version": "v3", "user": USER}),
            # the version left out is the version in use
            ({}, {"user": USER}),
            ({}, {"auth_protocol": "SHA", "auth_passphrase": AUTH_PASSPHRASE}),
            # the passphrases are masked and cannot be compared
            ({}, V3_FULL),
            (
                {"auth_protocol": None, "privacy_protocol": None},
                {"version": "v3", "user": USER},
            ),
            ({"version": "v2c"}, {}),
            # the community string is masked and cannot be compared
            ({"version": "v2c"}, {"version": "v2c", "community": COMMUNITY}),
            ({"version": "v2c"}, {"community": COMMUNITY}),
            # a community string the array returns readable is compared
            (
                {"version": "v2c", "community": COMMUNITY},
                {"version": "v2c", "community": COMMUNITY},
            ),
            ({"version": "v2c", "community": COMMUNITY}, {}),
        ],
    )
    def test_no_difference(self, held, params, check_mode):
        module = _module(check_mode=check_mode, **params)
        blade = _blade(agent=_agent(**held))
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": False}
        blade.patch_snmp_agents.assert_not_called()


# (what the array holds, the task, the body of the PATCH)
CHANGES = [
    ({}, {"version": "v3", "user": OTHER_USER}, _v3_body(user=OTHER_USER)),
    ({}, {"user": OTHER_USER}, _v3_body(user=OTHER_USER)),
    (
        {},
        {
            "version": "v3",
            "user": USER,
            "auth_protocol": "MD5",
            "auth_passphrase": AUTH_PASSPHRASE,
        },
        _v3_body(user=USER, auth_protocol="MD5", auth_passphrase=AUTH_PASSPHRASE),
    ),
    (
        {},
        {
            "version": "v3",
            "user": USER,
            "privacy_protocol": "AES",
            "privacy_passphrase": PRIVACY_PASSPHRASE,
        },
        _v3_body(
            user=USER, privacy_protocol="AES", privacy_passphrase=PRIVACY_PASSPHRASE
        ),
    ),
    # the secrets are sent with a readable setting that changes
    (
        {"auth_protocol": None, "privacy_protocol": None},
        V3_FULL,
        _v3_body(
            user=USER,
            auth_protocol="SHA",
            auth_passphrase=AUTH_PASSPHRASE,
            privacy_protocol="DES",
            privacy_passphrase=PRIVACY_PASSPHRASE,
        ),
    ),
    ({}, {"version": "v2c", "community": COMMUNITY}, _v2c_body(COMMUNITY)),
    ({"version": "v2c"}, {"version": "v3", "user": USER}, _v3_body(user=USER)),
    (
        {"version": "v2c"},
        V3_FULL,
        _v3_body(
            user=USER,
            auth_protocol="SHA",
            auth_passphrase=AUTH_PASSPHRASE,
            privacy_protocol="DES",
            privacy_passphrase=PRIVACY_PASSPHRASE,
        ),
    ),
    (
        {"version": "v2c", "community": "another-community"},
        {"version": "v2c", "community": COMMUNITY},
        _v2c_body(COMMUNITY),
    ),
]


class TestPurefbSnmpAgentChange:
    """A difference is sent in one PATCH, and only predicted in check mode."""

    @pytest.mark.parametrize("held, params, body", CHANGES)
    def test_real_run_sends_the_difference(self, held, params, body):
        module = _module(**params)
        blade = _blade(agent=_agent(**held))
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        assert _sent(blade) == body

    @pytest.mark.parametrize("held, params, body", CHANGES)
    def test_check_mode_sends_nothing(self, held, params, body):
        module = _module(check_mode=True, **params)
        blade = _blade(agent=_agent(**held))
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        blade.patch_snmp_agents.assert_not_called()


class TestPurefbSnmpAgentWrite:
    """A write the array refuses or fails is reported with its message."""

    @pytest.mark.parametrize(
        "message, status_code, reported",
        [
            (REFUSED, 400, REFUSED),
            (None, 500, "Unknown error"),
            ("Service unavailable.", 503, "Service unavailable."),
        ],
    )
    @pytest.mark.parametrize(
        "params, failed",
        [
            ({"version": "v3", "user": OTHER_USER}, V3_FAILED),
            ({"version": "v2c", "community": COMMUNITY}, V2C_FAILED),
        ],
    )
    def test_failed_write(self, params, failed, message, status_code, reported):
        module = _module(**params)
        blade = _blade(write=_error(message, status_code=status_code))
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == failed.format(reported)
        blade.patch_snmp_agents.assert_called_once()


class TestPurefbSnmpAgentMain:
    """Argument handling and the SDK requirement."""

    def test_argument_spec(self):
        module = _module()
        run = _run(module, _blade())
        args, kwargs = run.ansible_module.call_args
        assert args == (
            {
                "user": {"type": "str"},
                "auth_passphrase": {"type": "str", "no_log": True},
                "auth_protocol": {"type": "str", "choices": ["MD5", "SHA"]},
                "privacy_passphrase": {"type": "str", "no_log": True},
                "privacy_protocol": {"type": "str", "choices": ["AES", "DES"]},
                "version": {"type": "str", "choices": ["v2c", "v3"]},
                "community": {"type": "str"},
            },
        )
        assert kwargs == {
            "required_together": [
                ["auth_passphrase", "auth_protocol"],
                ["privacy_passphrase", "privacy_protocol"],
            ],
            "required_if": [
                ["version", "v2c", ["community"]],
                ["version", "v3", ["user"]],
            ],
            "supports_check_mode": True,
        }

    @pytest.mark.parametrize("check_mode", [False, True])
    def test_sdk_is_required(self, check_mode):
        module = _module(check_mode=check_mode, version="v3", user=OTHER_USER)
        blade = _blade()
        assert _run(module, blade, sdk=False).outcome == "fail"
        assert _failure(module) == "py-pure-client SDK is required for this module"
        blade.get_snmp_agents.assert_not_called()
        blade.patch_snmp_agents.assert_not_called()

    @pytest.mark.parametrize("check_mode", [False, True])
    @pytest.mark.parametrize(
        "option, length, message",
        [
            ("auth_passphrase", 7, "auth_password must be between 8 and 32 characters"),
            (
                "auth_passphrase",
                33,
                "auth_password must be between 8 and 32 characters",
            ),
            (
                "privacy_passphrase",
                7,
                "privacy_password must be between 8 and 63 characters",
            ),
            (
                "privacy_passphrase",
                64,
                "privacy_password must be between 8 and 63 characters",
            ),
        ],
    )
    def test_passphrase_length_is_checked_before_the_read(
        self, option, length, message, check_mode
    ):
        params = {"version": "v3", "user": OTHER_USER, option: "p" * length}
        module = _module(check_mode=check_mode, **params)
        blade = _blade()
        assert _run(module, blade).outcome == "fail"
        assert _failure(module) == message
        blade.get_snmp_agents.assert_not_called()
        blade.patch_snmp_agents.assert_not_called()

    @pytest.mark.parametrize(
        "option, length",
        [
            ("auth_passphrase", 8),
            ("auth_passphrase", 32),
            ("privacy_passphrase", 8),
            ("privacy_passphrase", 63),
        ],
    )
    def test_passphrase_length_accepted(self, option, length):
        params = {"version": "v3", "user": OTHER_USER, option: "p" * length}
        module = _module(**params)
        blade = _blade()
        assert _run(module, blade).outcome == "exit"
        assert _result(module) == {"changed": True}
        assert _sent(blade)["v3"][option] == "p" * length


class TestReadable:
    """A value the array omits or masks cannot be compared."""

    @pytest.mark.parametrize("value", [None, "*", MASKED, "********"])
    def test_omitted_or_masked(self, value):
        assert _readable(value) is None

    @pytest.mark.parametrize("value", ["", COMMUNITY, "**community**", "a*"])
    def test_readable(self, value):
        assert _readable(value) == value
