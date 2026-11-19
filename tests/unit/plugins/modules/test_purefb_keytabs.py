# Copyright: (c) 2026, Everpure Ansible Team <pure-ansible-team@everpuredata.com>
# GNU General Public License v3.0+ (see COPYING.GPLv3 or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Unit tests for purefb_keytabs module."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import base64
import os
import re
import stat
import struct
import sys
import multiprocessing
import ctypes
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
from plugins.modules.purefb_keytabs import (
    main,
    _keytab_entries,
    _private_call,
    DOWNLOAD_BATCH,
)

MOD = "plugins.modules.purefb_keytabs"
DEFAULT_SERVER = "_array_server"
REALM_SERVER = "realm1::srv1"
ARRAY_SERVER = "srv1"
REALM_PREFIX = "realm1::srv1::kt"
ARRAY_PREFIX = "kt"
SERVER_PREFIX = "srv1::kt"
NOT_FOUND = "Keytab does not exist."
SERVER_NOT_FOUND = "Server does not exist."
UNEXPECTED = "Unexpected error."
posix_only = pytest.mark.skipif(os.name != "posix", reason="file modes are POSIX")


# ---------------------------------------------------------------- keytab files


def _counted(data):
    return struct.pack(">H", len(data)) + data


def _entry(
    host,
    kvno=2,
    etype=18,
    key=b"k" * 32,
    realm=b"EXAMPLE.COM",
    timestamp=1700000000,
    kvno32=True,
):
    """One entry of a keytab file in the binary format, for nfs/<host>@<realm>."""
    body = struct.pack(">H", 2) + _counted(realm) + _counted(b"nfs") + _counted(host)
    body += struct.pack(">II", 1, timestamp)
    body += struct.pack(">B", kvno & 0xFF) + struct.pack(">H", etype) + _counted(key)
    if kvno32:
        body += struct.pack(">I", kvno)
    return struct.pack(">i", len(body)) + body


def _keytab(*entries):
    return b"\x05\x02" + b"".join(entries)


def _split(data):
    """The raw entries of a keytab file, as the array stores them in slots."""
    if not isinstance(data, bytes):
        data = data.encode("utf-8")
    if data[:2] != b"\x05\x02":
        data = base64.b64decode(data)
    pos, entries = 2, []
    while pos + 4 <= len(data):
        (size,) = struct.unpack(">i", data[pos : pos + 4])
        entries.append(data[pos : pos + 4 + size])
        pos += 4 + size
    return entries


ENTRY_Z = _entry(b"z.example.com", key=b"z" * 32)
ENTRY_Z_NEXT = _entry(b"z.example.com", kvno=3, key=b"y" * 32)
ENTRY_Z_REKEYED = _entry(b"z.example.com", key=b"x" * 32)
ENTRY_A = _entry(b"a.example.com", key=b"a" * 32)


# ------------------------------------------------------------------- the array


def _response(items=None):
    """A successful answer of the SDK."""
    res = Mock(spec=["status_code", "items", "total_item_count", "headers"])
    res.status_code = 200
    res.items = items if items is not None else []
    res.total_item_count = len(res.items)
    return res


def _error(status_code, message):
    """A failed answer of the SDK: it has errors and no items."""
    res = Mock(spec=["status_code", "errors", "headers"])
    res.status_code = status_code
    error = Mock()
    error.message = message
    res.errors = [error]
    return res


def _error_message(res, default="Unknown error"):
    """What module_utils.common.get_error_message returns."""
    errors = getattr(res, "errors", None)
    if errors:
        return list(errors)[0].message
    return default


def _named(name):
    item = Mock()
    item.name = name
    return item


def _server_of(prefix):
    return prefix.rpartition("::")[0] or DEFAULT_SERVER


def _blade(tmp_path, servers=(DEFAULT_SERVER, ARRAY_SERVER, REALM_SERVER), accounts=()):
    """A small stateful stand-in for the array.

    Keytabs live in blade.slots (name -> slot with name, prefix, suffix,
    server and the raw entry). An upload adds one slot for every entry of the
    file, numbered after the slots the prefix already has, and answers with
    the uploaded file, which the SDK saves in its temporary directory
    (blade.tmp). A download answers with a keytab file of the named slots.
    Names match without regard to case and a missing name answers 400.

    blade.saved lists (path, mode) of every file the SDK saved.
    blade.quirks makes a request fail: keytabs, download, upload, delete,
    servers, accounts or rotate map to (status, message). loose_filter makes
    the keytab list ignore its filter.
    """
    tmp = tmp_path / "sdk"
    tmp.mkdir()
    slots = {}
    blade = Mock()
    blade.slots = slots
    blade.tmp = str(tmp)
    blade.saved = []
    blade.quirks = {}

    def _save(data):
        path = os.path.join(blade.tmp, "pure_krb{0}.keytab".format(len(blade.saved)))
        with open(path, "wb") as saved:
            saved.write(data if isinstance(data, bytes) else data.encode("utf-8"))
        blade.saved.append((path, stat.S_IMODE(os.stat(path).st_mode)))
        return path

    def _find(name):
        for slot in slots.values():
            if slot.name.lower() == name.lower():
                return slot
        return None

    def _get_keytabs(**kwargs):
        if "keytabs" in blade.quirks:
            return _error(*blade.quirks["keytabs"])
        if kwargs.get("names") is not None:
            slot = _find(kwargs["names"][0])
            return _response([slot]) if slot else _error(400, NOT_FOUND)
        found = list(slots.values())
        if kwargs.get("filter") and not blade.quirks.get("loose_filter"):
            wanted = re.match(r"prefix='(.*)'$", kwargs["filter"]).group(1)
            found = [slot for slot in found if slot.prefix.lower() == wanted.lower()]
        return _response(found)

    def _upload(**kwargs):
        if "upload" in blade.quirks:
            return _error(*blade.quirks["upload"])
        prefix = kwargs["name_prefixes"]
        data = kwargs["keytab_file"][1]
        if _server_of(prefix) not in servers:
            return _error(400, SERVER_NOT_FOUND)
        used = [slot.suffix for slot in slots.values() if slot.prefix == prefix]
        for number, raw in enumerate(_split(data), start=max(used + [0]) + 1):
            slot = _named("{0}.{1}".format(prefix, number))
            slot.prefix = prefix
            slot.suffix = number
            slot.server = _named(_server_of(prefix))
            slot.raw = raw
            slots[slot.name] = slot
        return _response([_save(data)])

    def _download(**kwargs):
        if "download" in blade.quirks:
            return _error(*blade.quirks["download"])
        found = [_find(name) for name in kwargs["keytab_names"]]
        if None in found:
            return _error(400, NOT_FOUND)
        return _response([_save(_keytab(*[slot.raw for slot in found]))])

    def _delete(**kwargs):
        if "delete" in blade.quirks:
            return _error(*blade.quirks["delete"])
        if kwargs["names"][0] not in slots:
            return _error(400, NOT_FOUND)
        del slots[kwargs["names"][0]]
        return _response()

    def _get_servers(**kwargs):
        if "servers" in blade.quirks:
            return _error(*blade.quirks["servers"])
        if kwargs["names"][0] not in servers:
            return _error(400, SERVER_NOT_FOUND)
        return _response([_named(kwargs["names"][0])])

    def _get_active_directory(**kwargs):
        if "accounts" in blade.quirks:
            return _error(*blade.quirks["accounts"])
        return _response([_named(account) for account in accounts])

    def _rotate(**kwargs):
        if "rotate" in blade.quirks:
            return _error(*blade.quirks["rotate"])
        return _response()

    blade.get_keytabs.side_effect = _get_keytabs
    blade.post_keytabs_upload.side_effect = _upload
    blade.get_keytabs_download.side_effect = _download
    blade.delete_keytabs.side_effect = _delete
    blade.get_servers.side_effect = _get_servers
    blade.get_active_directory.side_effect = _get_active_directory
    blade.post_keytabs.side_effect = _rotate
    return blade


def _keytab_file(tmp_path, data, name="in.keytab"):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def _module(check_mode=False, **overrides):
    module = Mock()
    module.params = {
        "state": "import",
        "name": None,
        "prefix": None,
        "ad_account": None,
        "keytab_file": None,
        "filetype": None,
    }
    module.params.update(overrides)
    module.check_mode = check_mode
    module.exit_json = Mock(side_effect=SystemExit)
    module.fail_json = Mock(side_effect=SystemExit)
    return module


def _run(blade, check_mode=False, api_version="2.30", sdk=True, **params):
    """Run main() against the array stand-in and return the module mock."""
    module = _module(check_mode=check_mode, **params)
    with patch(MOD + ".AnsibleModule", return_value=module) as ansible_module, patch(
        MOD + ".get_system", return_value=blade
    ), patch(MOD + ".get_rest_api_version", return_value=api_version), patch(
        MOD + ".LooseVersion", RealLooseVersion
    ), patch(
        MOD + ".HAS_PYPURECLIENT", sdk
    ), patch(
        MOD + ".get_error_message", side_effect=_error_message
    ), patch(
        MOD + ".Reference", side_effect=lambda **kwargs: kwargs
    ), patch(
        MOD + ".KeytabPost", side_effect=lambda **kwargs: kwargs
    ), patch(
        MOD + ".purefb_argument_spec", return_value={}
    ):
        with pytest.raises(SystemExit):
            main()
    module.ansible_module = ansible_module
    return module


def _import(blade, path, prefix=ARRAY_PREFIX, check_mode=False, **params):
    params.setdefault("filetype", "binary")
    return _run(
        blade,
        check_mode=check_mode,
        state="import",
        prefix=prefix,
        keytab_file=path,
        **params
    )


def _changed(module):
    """The changed value of a task that did not fail."""
    module.fail_json.assert_not_called()
    return module.exit_json.call_args[1]["changed"]


def _failure(module):
    """The message of a task that failed."""
    module.exit_json.assert_not_called()
    return module.fail_json.call_args[1]["msg"]


@pytest.fixture(autouse=True)
def _umask():
    """Run every test with the usual umask, and put the old one back."""
    old = os.umask(0o022)
    yield
    os.umask(old)


# ------------------------------------------------------------------- the tests


class TestKeytabEntries:
    """Reading a keytab file into comparable entries"""

    def test_binary_file(self):
        entries = _keytab_entries(_keytab(ENTRY_Z, ENTRY_A))
        assert entries == {
            (b"EXAMPLE.COM", (b"nfs", b"z.example.com"), 2, 18, b"z" * 32),
            (b"EXAMPLE.COM", (b"nfs", b"a.example.com"), 2, 18, b"a" * 32),
        }

    def test_base64_file_as_text_and_as_bytes(self):
        binary = _keytab(ENTRY_Z, ENTRY_Z_NEXT)
        encoded = base64.b64encode(binary)
        assert _keytab_entries(encoded + b"\n") == _keytab_entries(binary)
        assert _keytab_entries(encoded.decode("ascii") + "\n") == _keytab_entries(
            binary
        )

    def test_timestamp_is_not_part_of_an_entry(self):
        later = _entry(b"z.example.com", key=b"z" * 32, timestamp=1800000000)
        assert _keytab_entries(_keytab(later)) == _keytab_entries(_keytab(ENTRY_Z))

    def test_key_and_key_version_are_part_of_an_entry(self):
        assert _keytab_entries(_keytab(ENTRY_Z_REKEYED)) != _keytab_entries(
            _keytab(ENTRY_Z)
        )
        assert _keytab_entries(_keytab(ENTRY_Z_NEXT)) != _keytab_entries(
            _keytab(ENTRY_Z)
        )

    def test_wide_key_version_replaces_the_narrow_one(self):
        wide = _keytab_entries(_keytab(_entry(b"z.example.com", kvno=300)))
        narrow = _keytab_entries(
            _keytab(_entry(b"z.example.com", kvno=44, kvno32=False))
        )
        assert [entry[2] for entry in wide] == [300]
        assert [entry[2] for entry in narrow] == [44]

    def test_holes_are_skipped_and_an_empty_record_ends_the_file(self):
        hole = struct.pack(">i", -6) + b"\0" * 6
        end = struct.pack(">i", 0)
        data = _keytab(ENTRY_Z) + hole + ENTRY_A + end + ENTRY_Z_NEXT
        assert _keytab_entries(data) == _keytab_entries(_keytab(ENTRY_Z, ENTRY_A))

    @pytest.mark.parametrize(
        "data",
        [
            b"this is not a keytab file\n",
            "this is not a keytab file\n",
            b"\x05\x01" + ENTRY_Z,
            _keytab(ENTRY_Z)[:-10],
            _keytab(ENTRY_Z[:20]),
            base64.b64encode(b"\x05\x01" + ENTRY_Z),
            b"\xff\xfe\x00",
        ],
    )
    def test_anything_else_is_not_a_keytab(self, data):
        assert _keytab_entries(data) is None


class TestPrivateCall:
    """Files the SDK saves are created for their owner only"""

    def test_umask_is_tight_during_the_call_and_restored_after(self):
        seen = []

        def func(**kwargs):
            current = os.umask(0)
            os.umask(current)
            seen.append((current, kwargs))
            return "result"

        assert _private_call(func, names=["a"]) == "result"
        assert seen == [(0o077, {"names": ["a"]})]
        current = os.umask(0)
        os.umask(current)
        assert current == 0o022

    def test_umask_is_restored_when_the_call_raises(self):
        def func(**kwargs):
            raise ValueError("boom")

        with pytest.raises(ValueError):
            _private_call(func)
        current = os.umask(0)
        os.umask(current)
        assert current == 0o022


class TestImport:
    """state=import"""

    def test_first_import_uploads_the_file(self, tmp_path):
        blade = _blade(tmp_path)
        data = _keytab(ENTRY_Z)
        module = _import(blade, _keytab_file(tmp_path, data))
        assert _changed(module) is True
        blade.post_keytabs_upload.assert_called_once_with(
            name_prefixes=ARRAY_PREFIX, keytab_file=("in.keytab", data)
        )
        assert sorted(blade.slots) == ["kt.1"]
        # nothing under the prefix yet, so no keytab was downloaded
        blade.get_keytabs_download.assert_not_called()

    def test_same_import_again_changes_nothing(self, tmp_path):
        blade = _blade(tmp_path)
        path = _keytab_file(tmp_path, _keytab(ENTRY_Z))
        _import(blade, path)
        module = _import(blade, path)
        assert _changed(module) is False
        assert blade.post_keytabs_upload.call_count == 1
        assert sorted(blade.slots) == ["kt.1"]

    def test_keytab_list_is_filtered_by_the_prefix(self, tmp_path):
        blade = _blade(tmp_path)
        path = _keytab_file(tmp_path, _keytab(ENTRY_Z))
        _import(blade, path, prefix=REALM_PREFIX)
        blade.get_keytabs.assert_called_once_with(filter="prefix='realm1::srv1::kt'")

    @pytest.mark.parametrize("prefix", ["k't", "k*", "k t", "k\\t"])
    def test_prefix_that_is_not_plain_is_matched_without_a_filter(
        self, tmp_path, prefix
    ):
        """A filter has wildcards and no escape for a quote"""
        blade = _blade(tmp_path)
        path = _keytab_file(tmp_path, _keytab(ENTRY_Z))
        _import(blade, path, prefix=ARRAY_PREFIX)
        blade.get_keytabs.reset_mock()
        assert _changed(_import(blade, path, prefix=prefix)) is True
        blade.get_keytabs.assert_called_once_with()
        # the keytab of the other prefix was not taken for one of this prefix
        blade.get_keytabs_download.assert_not_called()
        assert _changed(_import(blade, path, prefix=prefix)) is False
        blade.get_keytabs_download.assert_called_once_with(keytab_names=[prefix + ".1"])
        assert sorted(blade.slots) == sorted(["kt.1", prefix + ".1"])

    def test_check_mode_predicts_both_runs_and_uploads_nothing(self, tmp_path):
        blade = _blade(tmp_path)
        path = _keytab_file(tmp_path, _keytab(ENTRY_Z))
        assert _changed(_import(blade, path, check_mode=True)) is True
        blade.post_keytabs_upload.assert_not_called()
        _import(blade, path)
        assert _changed(_import(blade, path, check_mode=True)) is False
        assert blade.post_keytabs_upload.call_count == 1

    def test_file_with_every_entry_spread_over_slots_changes_nothing(self, tmp_path):
        blade = _blade(tmp_path)
        _import(blade, _keytab_file(tmp_path, _keytab(ENTRY_Z), "one.keytab"))
        _import(blade, _keytab_file(tmp_path, _keytab(ENTRY_A), "two.keytab"))
        both = _keytab_file(tmp_path, _keytab(ENTRY_A, ENTRY_Z), "both.keytab")
        assert _changed(_import(blade, both)) is False
        assert sorted(blade.slots) == ["kt.1", "kt.2"]

    def test_file_with_a_new_entry_is_uploaded(self, tmp_path):
        blade = _blade(tmp_path)
        _import(blade, _keytab_file(tmp_path, _keytab(ENTRY_Z), "one.keytab"))
        more = _keytab_file(tmp_path, _keytab(ENTRY_Z, ENTRY_Z_NEXT), "more.keytab")
        assert _changed(_import(blade, more, check_mode=True)) is True
        assert _changed(_import(blade, more)) is True
        assert sorted(blade.slots) == ["kt.1", "kt.2", "kt.3"]
        assert _changed(_import(blade, more)) is False

    def test_another_key_under_the_same_key_version_is_uploaded(self, tmp_path):
        blade = _blade(tmp_path)
        _import(blade, _keytab_file(tmp_path, _keytab(ENTRY_Z), "one.keytab"))
        rekeyed = _keytab_file(tmp_path, _keytab(ENTRY_Z_REKEYED), "rekeyed.keytab")
        assert _changed(_import(blade, rekeyed)) is True
        assert sorted(blade.slots) == ["kt.1", "kt.2"]

    def test_prefix_in_another_case_is_the_same_prefix(self, tmp_path):
        blade = _blade(tmp_path)
        path = _keytab_file(tmp_path, _keytab(ENTRY_Z))
        _import(blade, path)
        assert _changed(_import(blade, path, prefix="KT")) is False
        assert sorted(blade.slots) == ["kt.1"]

    def test_realm_server_prefix_and_its_namesakes(self, tmp_path):
        """The same leaf prefix on three servers: each import is its own"""
        blade = _blade(tmp_path)
        path = _keytab_file(tmp_path, _keytab(ENTRY_Z))
        for prefix in (ARRAY_PREFIX, SERVER_PREFIX, REALM_PREFIX):
            assert _changed(_import(blade, path, prefix=prefix)) is True
            assert _changed(_import(blade, path, prefix=prefix)) is False
        assert sorted(blade.slots) == ["kt.1", "realm1::srv1::kt.1", "srv1::kt.1"]
        assert blade.slots["realm1::srv1::kt.1"].server.name == REALM_SERVER
        assert blade.slots["srv1::kt.1"].server.name == ARRAY_SERVER
        assert blade.slots["kt.1"].server.name == DEFAULT_SERVER
        # the comparison read the keytabs of the prefix only
        downloads = [
            call[1]["keytab_names"]
            for call in blade.get_keytabs_download.call_args_list
        ]
        assert downloads == [["kt.1"], ["srv1::kt.1"], ["realm1::srv1::kt.1"]]
        blade.get_servers.assert_any_call(names=[REALM_SERVER])
        blade.get_servers.assert_any_call(names=[ARRAY_SERVER])

    def test_keytabs_of_other_prefixes_are_not_compared(self, tmp_path):
        """A list that returns more than the prefix does not widen the read"""
        blade = _blade(tmp_path)
        path = _keytab_file(tmp_path, _keytab(ENTRY_Z))
        _import(blade, path, prefix=REALM_PREFIX)
        blade.quirks["loose_filter"] = True
        assert _changed(_import(blade, path, prefix=ARRAY_PREFIX)) is True
        blade.get_keytabs_download.assert_not_called()
        assert sorted(blade.slots) == ["kt.1", "realm1::srv1::kt.1"]

    def test_many_slots_are_downloaded_in_batches(self, tmp_path):
        blade = _blade(tmp_path)
        count = 2 * DOWNLOAD_BATCH + 5
        hosts = ["h{0}.example.com".format(number).encode() for number in range(count)]
        for number, host in enumerate(hosts):
            name = "one{0}.keytab".format(number)
            _import(blade, _keytab_file(tmp_path, _keytab(_entry(host)), name))
        blade.get_keytabs_download.reset_mock()
        last = _keytab_file(tmp_path, _keytab(_entry(hosts[-1])), "last.keytab")
        assert _changed(_import(blade, last)) is False
        sizes = [
            len(call[1]["keytab_names"])
            for call in blade.get_keytabs_download.call_args_list
        ]
        assert sizes == [DOWNLOAD_BATCH, DOWNLOAD_BATCH, 5]
        # an entry found in the first batch ends the comparison there
        blade.get_keytabs_download.reset_mock()
        first = _keytab_file(tmp_path, _keytab(_entry(hosts[0])), "first.keytab")
        assert _changed(_import(blade, first)) is False
        assert blade.get_keytabs_download.call_count == 1

    def test_base64_file_is_sent_as_text_and_compared(self, tmp_path):
        blade = _blade(tmp_path)
        text = base64.b64encode(_keytab(ENTRY_Z)).decode("ascii") + "\n"
        path = _keytab_file(tmp_path, text.encode("ascii"), "in.keytab.mime")
        assert _changed(_import(blade, path, filetype="base64")) is True
        blade.post_keytabs_upload.assert_called_once_with(
            name_prefixes=ARRAY_PREFIX, keytab_file=("in.keytab.mime", text)
        )
        assert _changed(_import(blade, path, filetype="base64")) is False
        # the binary form of the same entry is already there as well
        binary = _keytab_file(tmp_path, _keytab(ENTRY_Z), "in.keytab")
        assert _changed(_import(blade, binary)) is False
        assert sorted(blade.slots) == ["kt.1"]

    def test_file_that_is_not_a_keytab_is_left_to_the_array(self, tmp_path):
        blade = _blade(tmp_path)
        _import(blade, _keytab_file(tmp_path, _keytab(ENTRY_Z), "one.keytab"))
        blade.get_keytabs.reset_mock()
        junk = _keytab_file(tmp_path, b"this is not a keytab file\n", "junk.keytab")
        assert _changed(_import(blade, junk, check_mode=True)) is True
        blade.quirks["upload"] = (400, "The keytab file data could not be parsed.")
        module = _import(blade, junk)
        assert "could not be parsed" in _failure(module)
        assert "junk.keytab" in _failure(module)
        blade.get_keytabs.assert_not_called()
        blade.get_keytabs_download.assert_not_called()

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_missing_file_fails_in_both_modes(self, tmp_path, check_mode):
        blade = _blade(tmp_path)
        path = str(tmp_path / "missing.keytab")
        module = _import(blade, path, check_mode=check_mode)
        assert "Failed to read keytab file " + path in _failure(module)
        blade.post_keytabs_upload.assert_not_called()

    def test_file_that_is_not_text_fails_cleanly_without_a_filetype(self, tmp_path):
        blade = _blade(tmp_path)
        path = _keytab_file(tmp_path, _keytab(ENTRY_Z))
        not_text = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
        with patch(MOD + ".open", create=True, side_effect=not_text) as opened:
            module = _import(blade, path, filetype=None, check_mode=True)
        opened.assert_called_once_with(path, "r")
        assert "Failed to read keytab file " + path in _failure(module)
        assert "invalid start byte" in _failure(module)

    @pytest.mark.parametrize("check_mode", [True, False])
    @pytest.mark.parametrize(
        "prefix,server",
        [
            ("realm1::nosrv::kt", "realm1::nosrv"),
            ("nosrv::kt", "nosrv"),
            ("realm1::kt", "realm1"),
            ("norealm::srv1::kt", "norealm::srv1"),
        ],
    )
    def test_server_that_does_not_exist_fails_in_both_modes(
        self, tmp_path, check_mode, prefix, server
    ):
        blade = _blade(tmp_path)
        path = _keytab_file(tmp_path, _keytab(ENTRY_Z))
        module = _import(blade, path, prefix=prefix, check_mode=check_mode)
        assert _failure(module) == (
            "Server {0} named in prefix {1} does not exist.".format(server, prefix)
        )
        blade.get_servers.assert_called_once_with(names=[server])
        blade.get_keytabs.assert_not_called()
        blade.post_keytabs_upload.assert_not_called()

    def test_default_server_prefix_reads_no_server(self, tmp_path):
        blade = _blade(tmp_path)
        _import(blade, _keytab_file(tmp_path, _keytab(ENTRY_Z)))
        blade.get_servers.assert_not_called()

    def test_server_read_refused_is_reported(self, tmp_path):
        blade = _blade(tmp_path)
        blade.quirks["servers"] = (403, "Operation not permitted.")
        path = _keytab_file(tmp_path, _keytab(ENTRY_Z))
        module = _import(blade, path, prefix=REALM_PREFIX, check_mode=True)
        assert _failure(module) == (
            "Failed to read server realm1::srv1. Error: Operation not permitted."
        )

    def test_array_without_servers_is_not_asked_for_one(self, tmp_path):
        blade = _blade(tmp_path)
        path = _keytab_file(tmp_path, _keytab(ENTRY_Z))
        module = _run(
            blade,
            api_version="2.15",
            state="import",
            prefix=SERVER_PREFIX,
            keytab_file=path,
            filetype="binary",
        )
        assert _changed(module) is True
        blade.get_servers.assert_not_called()

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_keytab_list_that_fails_is_reported(self, tmp_path, check_mode):
        blade = _blade(tmp_path)
        blade.quirks["keytabs"] = (500, UNEXPECTED)
        path = _keytab_file(tmp_path, _keytab(ENTRY_Z))
        module = _import(blade, path, prefix=REALM_PREFIX, check_mode=check_mode)
        assert _failure(module) == (
            "Failed to read the keytabs of prefix realm1::srv1::kt. "
            "Error: Unexpected error."
        )
        blade.post_keytabs_upload.assert_not_called()

    def test_download_that_fails_is_reported(self, tmp_path):
        blade = _blade(tmp_path)
        path = _keytab_file(tmp_path, _keytab(ENTRY_Z))
        _import(blade, path)
        blade.quirks["download"] = (403, "Operation not permitted.")
        module = _import(blade, path)
        assert _failure(module) == (
            "Failed to read the keytabs of prefix kt. Error: Operation not permitted."
        )
        assert blade.post_keytabs_upload.call_count == 1

    def test_upload_refused_is_reported(self, tmp_path):
        blade = _blade(tmp_path)
        blade.quirks["upload"] = (400, "Keytab files may only contain server keytabs.")
        path = _keytab_file(tmp_path, _keytab(ENTRY_Z))
        module = _import(blade, path)
        assert _failure(module) == (
            "Failed to import keytab file {0}. "
            "Error: Keytab files may only contain server keytabs.".format(path)
        )

    @posix_only
    def test_no_copy_of_the_keys_is_left_behind(self, tmp_path):
        """Upload answer and comparison downloads: private, then removed"""
        blade = _blade(tmp_path)
        path = _keytab_file(tmp_path, _keytab(ENTRY_Z))
        _import(blade, path)
        _import(blade, path)
        _import(blade, path, check_mode=True)
        # one upload answer and two downloads were saved by the SDK
        assert len(blade.saved) == 3
        assert [mode for saved, mode in blade.saved] == [0o600, 0o600, 0o600]
        assert os.listdir(blade.tmp) == []
        # the file of the task is not touched
        assert os.path.isfile(path)


class TestAbsent:
    """state=absent"""

    def _array(self, tmp_path):
        blade = _blade(tmp_path)
        path = _keytab_file(tmp_path, _keytab(ENTRY_Z, ENTRY_A))
        for prefix in (ARRAY_PREFIX, SERVER_PREFIX, REALM_PREFIX):
            _import(blade, path, prefix=prefix)
        return blade

    def test_delete_twice(self, tmp_path):
        blade = self._array(tmp_path)
        module = _run(blade, state="absent", name="realm1::srv1::kt.1")
        assert _changed(module) is True
        blade.delete_keytabs.assert_called_once_with(names=["realm1::srv1::kt.1"])
        module = _run(blade, state="absent", name="realm1::srv1::kt.1")
        assert _changed(module) is False
        assert blade.delete_keytabs.call_count == 1
        # the other slot and the namesakes on the other servers are untouched
        assert sorted(blade.slots) == [
            "kt.1",
            "kt.2",
            "realm1::srv1::kt.2",
            "srv1::kt.1",
            "srv1::kt.2",
        ]

    def test_check_mode_deletes_nothing(self, tmp_path):
        blade = self._array(tmp_path)
        module = _run(blade, check_mode=True, state="absent", name="kt.1")
        assert _changed(module) is True
        blade.delete_keytabs.assert_not_called()

    def test_name_in_another_case_deletes_the_stored_name(self, tmp_path):
        blade = self._array(tmp_path)
        module = _run(blade, state="absent", name="REALM1::SRV1::KT.2")
        assert _changed(module) is True
        blade.delete_keytabs.assert_called_once_with(names=["realm1::srv1::kt.2"])

    @pytest.mark.parametrize(
        "name", ["kt.9", "nosrv::kt.1", "realm1::nosrv::kt.1", "norealm::srv1::kt.1"]
    )
    def test_keytab_that_does_not_exist_is_absent(self, tmp_path, name):
        blade = self._array(tmp_path)
        assert _changed(_run(blade, state="absent", name=name)) is False
        blade.delete_keytabs.assert_not_called()

    @pytest.mark.parametrize("check_mode", [True, False])
    @pytest.mark.parametrize(
        "status,message", [(500, UNEXPECTED), (403, "Operation not permitted.")]
    )
    def test_failed_read_is_not_absent(self, tmp_path, check_mode, status, message):
        blade = self._array(tmp_path)
        blade.quirks["keytabs"] = (status, message)
        module = _run(
            blade, check_mode=check_mode, state="absent", name="realm1::srv1::kt.1"
        )
        assert _failure(module) == (
            "Failed to read keytab realm1::srv1::kt.1. Error: " + message
        )
        blade.delete_keytabs.assert_not_called()

    def test_needs_neither_a_prefix_nor_an_active_directory_account(self, tmp_path):
        blade = self._array(tmp_path)
        module = _run(blade, check_mode=True, state="absent", name="kt.1")
        assert _changed(module) is True
        blade.get_active_directory.assert_not_called()

    def test_delete_refused_is_reported(self, tmp_path):
        blade = self._array(tmp_path)
        blade.quirks["delete"] = (403, "Operation not permitted.")
        module = _run(blade, state="absent", name="kt.1")
        assert _failure(module) == (
            "Failed to delete keytab kt.1. Error: Operation not permitted."
        )


class TestExport:
    """state=export"""

    def _array(self, tmp_path):
        blade = _blade(tmp_path)
        path = _keytab_file(tmp_path, _keytab(ENTRY_Z, ENTRY_A))
        for prefix in (ARRAY_PREFIX, REALM_PREFIX):
            _import(blade, path, prefix=prefix)
        blade.saved[:] = []
        return blade

    def test_export_returns_the_file_of_the_named_keytab(self, tmp_path):
        blade = self._array(tmp_path)
        module = _run(blade, state="export", name="REALM1::srv1::kt.2")
        assert _changed(module) is False
        blade.get_keytabs_download.assert_called_once_with(
            keytab_names=["realm1::srv1::kt.2"]
        )
        download_file = module.exit_json.call_args[1]["download_file"]
        with open(download_file, "rb") as exported:
            assert exported.read() == _keytab(ENTRY_A)

    @posix_only
    def test_exported_file_is_private(self, tmp_path):
        blade = self._array(tmp_path)
        module = _run(blade, state="export", name="kt.1")
        download_file = module.exit_json.call_args[1]["download_file"]
        assert blade.saved == [(download_file, 0o600)]
        assert stat.S_IMODE(os.stat(download_file).st_mode) == 0o600

    @posix_only
    def test_file_that_was_there_before_is_made_private(self, tmp_path):
        blade = self._array(tmp_path)
        before = os.path.join(blade.tmp, "pure_krb0.keytab")
        with open(before, "wb") as existing:
            existing.write(b"old")
        os.chmod(before, 0o644)
        module = _run(blade, state="export", name="kt.1")
        assert module.exit_json.call_args[1]["download_file"] == before
        assert stat.S_IMODE(os.stat(before).st_mode) == 0o600

    def test_check_mode_downloads_nothing(self, tmp_path):
        blade = self._array(tmp_path)
        module = _run(blade, check_mode=True, state="export", name="kt.1")
        module.exit_json.assert_called_once_with(changed=False, download_file="")
        blade.get_keytabs_download.assert_not_called()

    def test_keytab_that_does_not_exist_gives_no_file(self, tmp_path):
        blade = self._array(tmp_path)
        module = _run(blade, state="export", name="kt.9")
        module.exit_json.assert_called_once_with(changed=False, download_file="")
        blade.get_keytabs_download.assert_not_called()

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_failed_read_is_not_an_empty_export(self, tmp_path, check_mode):
        blade = self._array(tmp_path)
        blade.quirks["keytabs"] = (500, UNEXPECTED)
        module = _run(blade, check_mode=check_mode, state="export", name="kt.1")
        assert (
            _failure(module) == "Failed to read keytab kt.1. Error: Unexpected error."
        )
        blade.get_keytabs_download.assert_not_called()

    def test_needs_neither_a_prefix_nor_an_active_directory_account(self, tmp_path):
        blade = self._array(tmp_path)
        module = _run(blade, state="export", name="kt.1")
        assert module.exit_json.call_args[1]["download_file"]
        blade.get_active_directory.assert_not_called()

    def test_download_refused_is_reported(self, tmp_path):
        blade = self._array(tmp_path)
        blade.quirks["download"] = (403, "Operation not permitted.")
        module = _run(blade, state="export", name="kt.1")
        assert _failure(module) == (
            "Failed to export keytab kt.1. Error: Operation not permitted."
        )


def _source(account):
    return {"source": {"name": account, "resource_type": "active-directory"}}


class TestRotate:
    """state=rotate"""

    DEFAULT_ACCOUNT = "acct-default"
    REALM_ACCOUNT = "realm1::srv1::acct"

    def test_only_account_is_rotated_under_its_own_name(self, tmp_path):
        blade = _blade(tmp_path, accounts=[self.DEFAULT_ACCOUNT])
        module = _run(blade, state="rotate")
        assert _changed(module) is True
        blade.post_keytabs.assert_called_once_with(
            keytab=_source(self.DEFAULT_ACCOUNT), name_prefixes=self.DEFAULT_ACCOUNT
        )

    def test_only_account_is_rotated_under_a_prefix(self, tmp_path):
        blade = _blade(tmp_path, accounts=[self.DEFAULT_ACCOUNT])
        module = _run(blade, state="rotate", prefix="next")
        assert _changed(module) is True
        blade.post_keytabs.assert_called_once_with(
            keytab=_source(self.DEFAULT_ACCOUNT), name_prefixes="next"
        )

    @pytest.mark.parametrize("check_mode", [True, False])
    @pytest.mark.parametrize("prefix", [None, "realm1::srv1::kt"])
    def test_several_accounts_and_none_named_is_refused(
        self, tmp_path, check_mode, prefix
    ):
        blade = _blade(tmp_path, accounts=[self.DEFAULT_ACCOUNT, self.REALM_ACCOUNT])
        module = _run(blade, check_mode=check_mode, state="rotate", prefix=prefix)
        assert _failure(module) == (
            "The array has more than one Active Directory account "
            "(acct-default, realm1::srv1::acct). "
            "Name the account to rotate in ad_account."
        )
        blade.post_keytabs.assert_not_called()

    @pytest.mark.parametrize(
        "account,prefix,expected",
        [
            ("realm1::srv1::acct", None, "realm1::srv1::acct"),
            ("realm1::srv1::acct", "realm1::srv1::kt", "realm1::srv1::kt"),
            ("acct-default", None, "acct-default"),
        ],
    )
    def test_named_account_is_the_one_rotated(
        self, tmp_path, account, prefix, expected
    ):
        blade = _blade(tmp_path, accounts=[self.DEFAULT_ACCOUNT, self.REALM_ACCOUNT])
        module = _run(blade, state="rotate", ad_account=account, prefix=prefix)
        assert _changed(module) is True
        blade.post_keytabs.assert_called_once_with(
            keytab=_source(account), name_prefixes=expected
        )

    def test_named_account_in_another_case_uses_the_stored_name(self, tmp_path):
        blade = _blade(tmp_path, accounts=[self.DEFAULT_ACCOUNT, self.REALM_ACCOUNT])
        module = _run(blade, state="rotate", ad_account="REALM1::SRV1::ACCT")
        assert _changed(module) is True
        blade.post_keytabs.assert_called_once_with(
            keytab=_source(self.REALM_ACCOUNT), name_prefixes=self.REALM_ACCOUNT
        )

    @pytest.mark.parametrize("check_mode", [True, False])
    def test_named_account_that_does_not_exist_is_refused(self, tmp_path, check_mode):
        blade = _blade(tmp_path, accounts=[self.DEFAULT_ACCOUNT])
        module = _run(
            blade, check_mode=check_mode, state="rotate", ad_account="realm1::srv1::no"
        )
        assert _failure(module) == (
            "Active Directory account realm1::srv1::no does not exist"
        )
        blade.post_keytabs.assert_not_called()

    def test_no_account_is_refused(self, tmp_path):
        blade = _blade(tmp_path)
        module = _run(blade, check_mode=True, state="rotate", prefix="next")
        assert _failure(module) == "No active directory account configured to rotate"

    @pytest.mark.parametrize("prefix", [None, "next"])
    def test_account_list_that_fails_is_reported(self, tmp_path, prefix):
        blade = _blade(tmp_path, accounts=[self.DEFAULT_ACCOUNT])
        blade.quirks["accounts"] = (403, "Operation not permitted.")
        module = _run(blade, state="rotate", prefix=prefix)
        assert _failure(module) == (
            "Failed to read the Active Directory accounts. "
            "Error: Operation not permitted."
        )
        blade.post_keytabs.assert_not_called()

    def test_check_mode_rotates_nothing(self, tmp_path):
        blade = _blade(tmp_path, accounts=[self.DEFAULT_ACCOUNT])
        module = _run(blade, check_mode=True, state="rotate")
        assert _changed(module) is True
        blade.post_keytabs.assert_not_called()

    def test_rotation_refused_is_reported(self, tmp_path):
        blade = _blade(tmp_path, accounts=[self.DEFAULT_ACCOUNT])
        blade.quirks["rotate"] = (400, "Could not contact the domain.")
        module = _run(blade, state="rotate", prefix="next")
        assert _failure(module) == (
            "Failed to rotate the keytabs of AD account acct-default, prefix next. "
            "Error: Could not contact the domain."
        )


class TestMain:
    """Argument handling"""

    def test_sdk_is_required(self, tmp_path):
        blade = _blade(tmp_path)
        module = _run(blade, sdk=False, state="absent", name="kt.1")
        assert _failure(module) == "py-pure-client sdk is required for this module"
        blade.get_keytabs.assert_not_called()

    def test_each_state_requires_what_it_needs(self, tmp_path):
        module = _run(_blade(tmp_path), state="absent", name="kt.1")
        args, kwargs = module.ansible_module.call_args
        assert kwargs["supports_check_mode"] is True
        assert kwargs["required_if"] == [
            ["state", "import", ["prefix", "keytab_file"]],
            ["state", "absent", ["name"]],
            ["state", "export", ["name"]],
        ]
        assert args[0]["ad_account"] == {"type": "str"}
        assert args[0]["state"]["default"] == "import"
