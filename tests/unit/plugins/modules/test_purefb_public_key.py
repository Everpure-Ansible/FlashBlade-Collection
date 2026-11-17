# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_public_key module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import sys
import multiprocessing
import ctypes
from unittest.mock import Mock, call, patch, MagicMock

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

from plugins.modules.purefb_public_key import (
    main,
    _key_material,
    get_key,
    get_uses,
    key_facts,
)

MODULE = "plugins.modules.purefb_public_key"

# One throw-away ed25519 key in both formats the array accepts
OPENSSH_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMnh9Xz7yvwyQpkfzqieUtBdemUGSmOoxdt+s0Onq/sM "
    "unit-test"
)
PEM_KEY = (
    "-----BEGIN PUBLIC KEY-----\n"
    "MCowBQYDK2VwAyEAyeH1fPvK/DJCmR/OqJ5S0F16ZQZKY6jF236zQ6er+ww=\n"
    "-----END PUBLIC KEY-----"
)
OTHER_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)


def _base_params(**overrides):
    params = {
        "name": "ca-signer",
        "state": "present",
        "public_key": None,
        "force": False,
    }
    params.update(overrides)
    return params


NOT_FOUND = "Public key does not exist."


def _response(status_code=200, items=None, message=None):
    response = Mock()
    response.status_code = status_code
    response.items = items if items is not None else []
    response.errors = []
    if message is not None:
        error = Mock(spec=["message"])
        error.message = message
        response.errors = [error]
    return response


def _absent():
    """The array's answer for a key that does not exist: a 400, not an empty list"""
    return _response(400, message=NOT_FOUND)


def _error_message(response, default="Unknown error"):
    """Stand-in for module_utils.common.get_error_message, which the preamble mocks"""
    errors = getattr(response, "errors", None) or []
    return errors[0].message if errors else default


def _key(name="ca-signer", public_key=OPENSSH_KEY, algorithm="ed25519", key_size=256):
    key = Mock(spec=["name", "public_key", "algorithm", "key_size"])
    key.name = name
    key.public_key = public_key
    key.algorithm = algorithm
    key.key_size = key_size
    return key


def _use(name="ca-policy", resource_type="ssh-certificate-authority-policies"):
    ref = Mock(spec=["name", "resource_type"])
    ref.name = name
    ref.resource_type = resource_type
    use = Mock(spec=["name", "use"])
    use.name = "ca-signer"
    use.use = ref
    return use


def _module(params, check_mode=False):
    module = Mock()
    module.params = params
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _blade(get_response, versions=None):
    blade = Mock()
    blade.get_versions.return_value.items = versions or ["2.14", "2.30"]
    blade.get_public_keys.return_value = get_response
    blade.get_public_keys_uses.return_value = _response()
    blade.post_public_keys.return_value = _response(items=[_key()])
    blade.delete_public_keys.return_value = _response()
    blade.delete_ssh_certificate_authority_policies.return_value = _response()
    return blade


def _run_main(module, blade, mock_ansible_module, mock_get_system, mock_loose_version):
    mock_ansible_module.return_value = module
    mock_get_system.return_value = blade
    mock_loose_version.return_value.__gt__ = Mock(return_value=False)
    try:
        main()
    except SystemExit:
        pass


class TestKeyMaterial:
    """_key_material canonicalises keys for comparison"""

    def test_openssh_comment_and_whitespace_do_not_count_without_cryptography(self):
        with patch(MODULE + ".HAS_CRYPTOGRAPHY", False):
            assert _key_material("  " + OPENSSH_KEY + "\n") == _key_material(
                OPENSSH_KEY.rsplit(" ", 1)[0]
            )
            assert _key_material(OPENSSH_KEY) != _key_material(OTHER_KEY)

    def test_pem_text_is_compared_stripped_without_cryptography(self):
        with patch(MODULE + ".HAS_CRYPTOGRAPHY", False):
            assert _key_material(PEM_KEY + "\n\n") == _key_material(PEM_KEY)
            # formats differ, so without a parser the texts differ
            assert _key_material(PEM_KEY) != _key_material(OPENSSH_KEY)
            assert _key_material(None) == ""

    def test_same_key_in_openssh_and_pem_form_is_equal_with_cryptography(self):
        pytest.importorskip("cryptography")
        assert _key_material(OPENSSH_KEY) == _key_material(PEM_KEY)
        assert _key_material(OPENSSH_KEY) != _key_material(OTHER_KEY)

    def test_unparseable_text_falls_back_to_text_compare_with_cryptography(self):
        pytest.importorskip("cryptography")
        assert _key_material(" garbage \n") == "garbage"
        assert _key_material("garbage") != _key_material(OPENSSH_KEY)


@patch(MODULE + ".get_error_message", _error_message)
class TestHelpers:
    """get_key, get_uses and key_facts"""

    def test_get_key_returns_item(self):
        module = _module(_base_params())
        key = _key()
        blade = Mock()
        blade.get_public_keys.return_value = _response(items=[key])
        assert get_key(module, blade) is key
        blade.get_public_keys.assert_called_once_with(names=["ca-signer"])

    def test_get_key_treats_does_not_exist_as_absent(self):
        module = _module(_base_params())
        blade = Mock()
        blade.get_public_keys.return_value = _absent()
        assert get_key(module, blade) is None
        module.fail_json.assert_not_called()

    def test_get_key_fails_on_other_400(self):
        # only the not-found 400 reads as absent; a bad request must not
        module = _module(_base_params())
        blade = Mock()
        blade.get_public_keys.return_value = _response(
            400, message="Syntax error in query."
        )
        with pytest.raises(SystemExit):
            get_key(module, blade)
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to read public key ca-signer" in msg
        assert "Syntax error in query." in msg

    def test_get_key_fails_on_other_errors(self):
        module = _module(_base_params())
        blade = Mock()
        blade.get_public_keys.return_value = _response(500)
        with pytest.raises(SystemExit):
            get_key(module, blade)
        assert (
            "Failed to read public key ca-signer"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_get_uses_maps_references(self):
        module = _module(_base_params())
        blade = Mock()
        blade.get_public_keys_uses.return_value = _response(items=[_use()])
        assert get_uses(module, blade) == [
            {"name": "ca-policy", "resource_type": "ssh-certificate-authority-policies"}
        ]
        blade.get_public_keys_uses.assert_called_once_with(names=["ca-signer"])

    def test_get_uses_fails_on_error(self):
        module = _module(_base_params())
        blade = Mock()
        blade.get_public_keys_uses.return_value = _response(400)
        with pytest.raises(SystemExit):
            get_uses(module, blade)
        assert "Failed to read the uses" in module.fail_json.call_args[1]["msg"]

    def test_key_facts(self):
        assert key_facts(_key(), []) == {
            "name": "ca-signer",
            "algorithm": "ed25519",
            "key_size": 256,
            "uses": [],
        }


@patch(MODULE + ".get_error_message", _error_message)
@patch(MODULE + ".LooseVersion")
@patch(MODULE + ".get_system")
@patch(MODULE + ".AnsibleModule")
@patch(MODULE + ".HAS_PYPURECLIENT", True)
class TestMain:
    """main() flows"""

    def test_version_gate_blocks_before_any_read(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(_base_params(public_key=OPENSSH_KEY))
        blade = _blade(_absent(), versions=["2.13"])
        mock_ansible_module.return_value = module
        mock_get_system.return_value = blade
        mock_loose_version.return_value.__gt__ = Mock(return_value=True)
        try:
            main()
        except SystemExit:
            pass
        module.fail_json.assert_called_once()
        assert "Minimum version required: 2.14" in module.fail_json.call_args[1]["msg"]
        blade.get_public_keys.assert_not_called()
        blade.post_public_keys.assert_not_called()

    @patch(MODULE + ".PublicKeyPost")
    def test_create_posts_stripped_key(
        self, mock_post, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(_base_params(public_key="\n" + OPENSSH_KEY + "\n"))
        blade = _blade(_absent())
        _run_main(
            module, blade, mock_ansible_module, mock_get_system, mock_loose_version
        )
        mock_post.assert_called_once_with(public_key=OPENSSH_KEY)
        blade.post_public_keys.assert_called_once_with(
            names=["ca-signer"], public_key=mock_post.return_value
        )
        module.exit_json.assert_called_once()
        result = module.exit_json.call_args[1]
        assert result["changed"] is True
        assert result["public_key"] == {
            "name": "ca-signer",
            "algorithm": "ed25519",
            "key_size": 256,
            "uses": [],
        }

    def test_create_reads_back_when_post_returns_no_items(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(_base_params(public_key=PEM_KEY))
        blade = _blade(_absent())
        blade.post_public_keys.return_value = _response(items=[])
        blade.get_public_keys.side_effect = [
            _absent(),
            _response(items=[_key(public_key=PEM_KEY)]),
        ]
        _run_main(
            module, blade, mock_ansible_module, mock_get_system, mock_loose_version
        )
        assert blade.get_public_keys.call_count == 2
        assert module.exit_json.call_args[1]["public_key"]["algorithm"] == "ed25519"

    def test_create_check_mode_skips_post(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(_base_params(public_key=OPENSSH_KEY), check_mode=True)
        blade = _blade(_absent())
        _run_main(
            module, blade, mock_ansible_module, mock_get_system, mock_loose_version
        )
        blade.post_public_keys.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_create_requires_public_key(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(_base_params(public_key="  "))
        blade = _blade(_absent())
        _run_main(
            module, blade, mock_ansible_module, mock_get_system, mock_loose_version
        )
        blade.post_public_keys.assert_not_called()
        assert "public_key is required" in module.fail_json.call_args[1]["msg"]

    def test_create_fails_on_api_error(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(_base_params(public_key=OPENSSH_KEY))
        blade = _blade(_absent())
        blade.post_public_keys.return_value = _response(400)
        _run_main(
            module, blade, mock_ansible_module, mock_get_system, mock_loose_version
        )
        module.fail_json.assert_called_once()
        assert (
            "Failed to create public key ca-signer"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_present_existing_same_key_is_idempotent(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        # a different comment on the requested key must not count
        module = _module(_base_params(public_key=OPENSSH_KEY.replace("unit-test", "x")))
        blade = _blade(_response(items=[_key()]))
        blade.get_public_keys_uses.return_value = _response(items=[_use()])
        _run_main(
            module, blade, mock_ansible_module, mock_get_system, mock_loose_version
        )
        blade.post_public_keys.assert_not_called()
        blade.delete_public_keys.assert_not_called()
        result = module.exit_json.call_args[1]
        assert result["changed"] is False
        assert result["public_key"]["uses"] == [
            {"name": "ca-policy", "resource_type": "ssh-certificate-authority-policies"}
        ]

    def test_present_existing_pem_on_array_matches_openssh_request(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        pytest.importorskip("cryptography")
        module = _module(_base_params(public_key=OPENSSH_KEY))
        blade = _blade(_response(items=[_key(public_key=PEM_KEY)]))
        _run_main(
            module, blade, mock_ansible_module, mock_get_system, mock_loose_version
        )
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False

    def test_present_existing_without_public_key_is_idempotent(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(_base_params())
        blade = _blade(_response(items=[_key()]))
        _run_main(
            module, blade, mock_ansible_module, mock_get_system, mock_loose_version
        )
        module.fail_json.assert_not_called()
        assert module.exit_json.call_args[1]["changed"] is False
        assert module.exit_json.call_args[1]["public_key"]["name"] == "ca-signer"

    def test_present_existing_different_key_fails(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(_base_params(public_key=OTHER_KEY))
        blade = _blade(_response(items=[_key()]))
        _run_main(
            module, blade, mock_ansible_module, mock_get_system, mock_loose_version
        )
        module.fail_json.assert_called_once()
        assert "cannot be modified" in module.fail_json.call_args[1]["msg"]
        blade.post_public_keys.assert_not_called()
        blade.delete_public_keys.assert_not_called()

    def test_absent_deletes_unused_key(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(_base_params(state="absent"))
        blade = _blade(_response(items=[_key()]))
        _run_main(
            module, blade, mock_ansible_module, mock_get_system, mock_loose_version
        )
        blade.get_public_keys_uses.assert_called_once_with(names=["ca-signer"])
        blade.delete_public_keys.assert_called_once_with(names=["ca-signer"])
        module.exit_json.assert_called_once_with(changed=True)

    def test_absent_check_mode_skips_delete(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(_base_params(state="absent"), check_mode=True)
        blade = _blade(_response(items=[_key()]))
        _run_main(
            module, blade, mock_ansible_module, mock_get_system, mock_loose_version
        )
        blade.delete_public_keys.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_absent_refuses_used_key_without_force(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(_base_params(state="absent"))
        blade = _blade(_response(items=[_key()]))
        blade.get_public_keys_uses.return_value = _response(items=[_use()])
        _run_main(
            module, blade, mock_ansible_module, mock_get_system, mock_loose_version
        )
        blade.delete_public_keys.assert_not_called()
        module.fail_json.assert_called_once()
        msg = module.fail_json.call_args[1]["msg"]
        assert "ca-policy (ssh-certificate-authority-policies)" in msg
        assert "force: true" in msg

    def test_absent_force_deletes_policies_then_key(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        # the array refuses to delete a key in use, so force deletes the
        # policies that use it first and then the key
        module = _module(_base_params(state="absent", force=True))
        blade = _blade(_response(items=[_key()]))
        blade.get_public_keys_uses.return_value = _response(
            items=[_use(), _use(name="other-policy")]
        )
        _run_main(
            module, blade, mock_ansible_module, mock_get_system, mock_loose_version
        )
        assert blade.delete_ssh_certificate_authority_policies.call_args_list == [
            call(names=["ca-policy"]),
            call(names=["other-policy"]),
        ]
        blade.delete_public_keys.assert_called_once_with(names=["ca-signer"])
        names = [str(c) for c in blade.mock_calls]
        last_policy_delete = max(
            i for i, c in enumerate(names) if "delete_ssh_certificate" in c
        )
        key_delete = names.index("call.delete_public_keys(names=['ca-signer'])")
        assert last_policy_delete < key_delete
        assert module.warn.call_count == 2
        assert "ca-policy" in module.warn.call_args_list[0][0][0]
        module.exit_json.assert_called_once_with(changed=True)

    def test_absent_force_check_mode_deletes_nothing(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(_base_params(state="absent", force=True), check_mode=True)
        blade = _blade(_response(items=[_key()]))
        blade.get_public_keys_uses.return_value = _response(items=[_use()])
        _run_main(
            module, blade, mock_ansible_module, mock_get_system, mock_loose_version
        )
        blade.delete_ssh_certificate_authority_policies.assert_not_called()
        blade.delete_public_keys.assert_not_called()
        module.warn.assert_not_called()
        module.exit_json.assert_called_once_with(changed=True)

    def test_absent_force_fails_when_policy_delete_fails(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(_base_params(state="absent", force=True))
        blade = _blade(_response(items=[_key()]))
        blade.get_public_keys_uses.return_value = _response(items=[_use()])
        blade.delete_ssh_certificate_authority_policies.return_value = _response(
            400, message="Policy has members."
        )
        _run_main(
            module, blade, mock_ansible_module, mock_get_system, mock_loose_version
        )
        blade.delete_public_keys.assert_not_called()
        msg = module.fail_json.call_args[1]["msg"]
        assert "Failed to delete SSH certificate authority policy ca-policy" in msg
        assert "Policy has members." in msg

    def test_absent_force_refuses_a_use_it_cannot_detach(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(_base_params(state="absent", force=True))
        blade = _blade(_response(items=[_key()]))
        blade.get_public_keys_uses.return_value = _response(
            items=[_use(), _use(name="thing", resource_type="widgets")]
        )
        _run_main(
            module, blade, mock_ansible_module, mock_get_system, mock_loose_version
        )
        blade.delete_ssh_certificate_authority_policies.assert_not_called()
        blade.delete_public_keys.assert_not_called()
        msg = module.fail_json.call_args[1]["msg"]
        assert "thing (widgets)" in msg
        assert "cannot detach" in msg

    def test_absent_other_400_on_read_fails(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        # a bad request is not "absent": state=absent must not report ok
        module = _module(_base_params(state="absent"))
        blade = _blade(_response(400, message="Syntax error in query."))
        _run_main(
            module, blade, mock_ansible_module, mock_get_system, mock_loose_version
        )
        blade.get_public_keys_uses.assert_not_called()
        blade.delete_public_keys.assert_not_called()
        module.exit_json.assert_not_called()
        assert "Syntax error in query." in module.fail_json.call_args[1]["msg"]

    def test_present_other_400_on_read_fails(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        # a bad request is not "absent": state=present must not try to create
        module = _module(_base_params(public_key=OPENSSH_KEY))
        blade = _blade(_response(400, message="Syntax error in query."))
        _run_main(
            module, blade, mock_ansible_module, mock_get_system, mock_loose_version
        )
        blade.post_public_keys.assert_not_called()
        assert "Failed to read public key" in module.fail_json.call_args[1]["msg"]

    def test_absent_missing_key_is_idempotent(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(_base_params(state="absent"))
        blade = _blade(_absent())
        _run_main(
            module, blade, mock_ansible_module, mock_get_system, mock_loose_version
        )
        blade.get_public_keys_uses.assert_not_called()
        blade.delete_public_keys.assert_not_called()
        module.exit_json.assert_called_once_with(changed=False)

    def test_absent_fails_on_delete_error(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(_base_params(state="absent"))
        blade = _blade(_response(items=[_key()]))
        blade.delete_public_keys.return_value = _response(400)
        _run_main(
            module, blade, mock_ansible_module, mock_get_system, mock_loose_version
        )
        module.fail_json.assert_called_once()
        assert (
            "Failed to delete public key ca-signer"
            in module.fail_json.call_args[1]["msg"]
        )

    def test_absent_fails_when_uses_cannot_be_read(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(_base_params(state="absent"))
        blade = _blade(_response(items=[_key()]))
        blade.get_public_keys_uses.return_value = _response(500)
        _run_main(
            module, blade, mock_ansible_module, mock_get_system, mock_loose_version
        )
        blade.delete_public_keys.assert_not_called()
        assert "Failed to read the uses" in module.fail_json.call_args[1]["msg"]

    def test_read_error_fails_before_any_write(
        self, mock_ansible_module, mock_get_system, mock_loose_version
    ):
        module = _module(_base_params(public_key=OPENSSH_KEY))
        blade = _blade(_response(503))
        _run_main(
            module, blade, mock_ansible_module, mock_get_system, mock_loose_version
        )
        blade.post_public_keys.assert_not_called()
        assert "Failed to read public key" in module.fail_json.call_args[1]["msg"]


@patch(MODULE + ".get_system")
@patch(MODULE + ".AnsibleModule")
@patch(MODULE + ".HAS_PYPURECLIENT", False)
def test_main_requires_pypureclient(mock_ansible_module, mock_get_system):
    module = _module(_base_params(public_key=OPENSSH_KEY))
    mock_ansible_module.return_value = module
    try:
        main()
    except SystemExit:
        pass
    assert "py-pure-client sdk is required" in module.fail_json.call_args[1]["msg"]
    mock_get_system.assert_not_called()
