#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2021, Simon Dodsley (simon@everpuredata.com)
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: purefb_keytabs
version_added: '1.6.0'
short_description: Manage FlashBlade Kerberos Keytabs
description:
- Manage Kerberos Keytabs for FlashBlades
- A keytab belongs to a server and the prefix of its name says which one.
  A plain C(prefix) is on the default server C(_array_server),
  C(server::prefix) is on another server and C(realm::server::prefix) is on
  a server in a realm.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  state:
    description:
    - Manage Kerberos Keytabs
    - C(import) uploads a keytab file. The file is uploaded only when at least
      one of its entries is missing from the keytabs of I(prefix), so a repeated
      import adds no further slots. The entries are compared with their keys,
      for which the keytabs of I(prefix) are downloaded to a temporary file
      that is removed again. A file that cannot be read as a keytab is always
      uploaded.
    - C(export) downloads one keytab to a file.
    - C(rotate) rotates the keys of an Active Directory account and creates new
      keytabs from them. Every run rotates the keys again.
      M(everpure.flashblade.purefb_ad) with I(state=rotate) does the same for
      the account it names.
    - C(absent) deletes one keytab.
    default: import
    type: str
    choices: [ absent, import, export, rotate ]
  name:
    description:
    - Name of the Keytab
    - Must include prefix and suffix
    - The prefix carries the server of the keytab, for example C(example.3) on
      the default server, C(server::example.3) on another server and
      C(realm::server::example.3) on a server in a realm.
    - A name that names the default server, C(_array_server::example.3), is
      read as C(example.3).
    - Required for I(state=absent) and I(state=export).
    type: str
  prefix:
    description:
    - Required for I(state=import), optional for I(state=rotate)
    - Prefix to use for naming the files slots
    - Specifying a file entry prefix is required because a single keytab file can contain
      multiple keytab entries in multiple slots.
    - The keytabs are created on the default server C(_array_server). Use
      C(server::prefix) to create them on another server and
      C(realm::server::prefix) to create them on a server in a realm. The
      server must exist.
    - A prefix that names the default server, C(_array_server::prefix), is the
      plain C(prefix).
    - The text before the last C(::) is always read as the name of a server, so
      a realm name without a server (C(realm::prefix)) does not address a realm.
    - If not provided for I(state=rotate) the name of the Active Directory
      account is used.
    type: str
  ad_account:
    description:
    - Name of the Active Directory account whose keys I(state=rotate) rotates,
      as the array reports it. The account of a server in a realm is named
      C(realm::server::account).
    - Required when the array has more than one Active Directory account.
      Without it the only account of the array is rotated, and the task fails
      when there are several.
    - Only used with I(state=rotate).
    type: str
    version_added: '1.30.0'
  keytab_file:
    description:
    - Name of file holding Keytab
    - Required for I(state=import).
    type: str
  filetype:
    description:
    - Format of the keytab file
    type: str
    choices: [ binary, base64 ]
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Import a binary keytab
  everpure.flashblade.purefb_keytabs:
    state: import
    prefix: example
    keytab_file: pure_krb.keytab
    filetype: binary
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Import a base64 keytab
  everpure.flashblade.purefb_keytabs:
    state: import
    prefix: example
    keytab_file: pure_krb.keytab.mime
    filetype: base64
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Import a binary keytab for a server in a realm
  everpure.flashblade.purefb_keytabs:
    state: import
    prefix: myrealm::myserver::example
    keytab_file: pure_krb.keytab
    filetype: binary
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Export a keytab
  everpure.flashblade.purefb_keytabs:
    state: export
    name: example.3
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
  register: download_file

- name: Delete a keytab
  everpure.flashblade.purefb_keytabs:
    state: absent
    name: example.3
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Delete a keytab of a server in a realm
  everpure.flashblade.purefb_keytabs:
    state: absent
    name: myrealm::myserver::example.1
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Rotate current AD account keytabs
  everpure.flashblade.purefb_keytabs:
    state: rotate
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Rotate AD account keytabs by creating new series
  everpure.flashblade.purefb_keytabs:
    state: rotate
    prefix: next_prefix
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Rotate the keytabs of one AD account when the array has several
  everpure.flashblade.purefb_keytabs:
    state: rotate
    ad_account: myrealm::myserver::myaccount
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
"""

RETURN = r"""
download_file:
  description:
  - Name of file containing exported keytab
  - The file is created in the temporary directory of the host that runs the
    module and is readable by its owner only. It holds keys and the module
    does not remove it.
  returned: When using I(export) option
  type: str
  sample: "/tmp/pure_krb8939478070214877726.keytab"
"""

import base64
import binascii
import os
import re
import struct

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import KeytabPost, Reference
except ImportError:
    HAS_PYPURECLIENT = False

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.everpure.flashblade.plugins.module_utils.purefb import (
    get_system,
    purefb_argument_spec,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.common import (
    get_error_message,
    get_rest_api_version,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.version import (
    LooseVersion,
)

SERVERS_API_VERSION = "2.16"
# The first two bytes of a keytab file in the binary format
KEYTAB_MAGIC = b"\x05\x02"
# Keytabs downloaded in one request when an import is compared with the array
DOWNLOAD_BATCH = 50
# A filter has wildcards and no escape for a quote, so only a prefix of these
# characters is used in one. Any other prefix is matched in the module.
FILTER_SAFE = re.compile(r"^[A-Za-z0-9_.:-]+$")
# The server of a keytab whose prefix names no server
DEFAULT_SERVER = "_array_server"


def _is_missing(res):
    """Return True when the array answered that the object does not exist.

    Only that answer means absent. A refusal or a failure of the array is
    not one.
    """
    return "does not exist" in str(get_error_message(res, "")).lower()


def _stored_name(name):
    """Return a prefix or a keytab name as the array stores it.

    The keytabs of the default server are stored under the plain prefix,
    also when the prefix of an import names that server, and the array does
    not find them under a name that names it.
    """
    server, leaf = name.rpartition("::")[0::2]
    if server.lower() == DEFAULT_SERVER:
        return leaf
    return name


def _get_keytabs(module, blade, name):
    """Return the keytabs the array has for name, none when there is no such keytab.

    The array matches a name without regard to case and reads a name that
    holds a comma as a list of names, so every keytab it returns is one the
    task names and none of them is left out. Any answer other than keytabs
    or "does not exist" fails the task with the message of the array.
    """
    res = blade.get_keytabs(names=[_stored_name(name)])
    if res.status_code == 200:
        return list(res.items)
    if _is_missing(res):
        return []
    module.fail_json(
        msg="Failed to read keytab {0}. Error: {1}".format(name, get_error_message(res))
    )


def _private_call(func, **kwargs):
    """Run an SDK call that saves a keytab file, keeping that file private.

    The SDK writes the file the array returns into the temporary directory
    with the permissions the umask allows. A keytab holds keys, so the file
    is created readable by its owner only.
    """
    old_umask = os.umask(0o077)
    try:
        return func(**kwargs)
    finally:
        os.umask(old_umask)


def _saved_files(res):
    """Return the files the SDK saved for a keytab upload or download."""
    return [
        path
        for path in list(res.items)
        if isinstance(path, str) and os.path.isfile(path)
    ]


def _remove_files(paths):
    """Remove files, ignoring those that are already gone."""
    for path in paths:
        try:
            os.remove(path)
        except OSError:
            pass


def _keytab_entry(entry):
    """Return what identifies one entry of a keytab file.

    That is the Kerberos realm, the components of the principal, the key
    version, the encryption type and the key. The name type and the
    timestamp are left out.
    """
    (count,) = struct.unpack(">H", entry[0:2])
    pos = 2
    names = []
    # the Kerberos realm comes first, then the components of the principal
    while len(names) <= count:
        (length,) = struct.unpack(">H", entry[pos : pos + 2])
        pos += 2
        names.append(entry[pos : pos + length])
        pos += length
    # skip the name type and the timestamp, four bytes each
    pos += 8
    kvno, etype, length = struct.unpack(">BHH", entry[pos : pos + 5])
    pos += 5
    key = entry[pos : pos + length]
    if len(key) != length:
        raise struct.error("truncated key")
    pos += length
    # a 32-bit key version, when present and not zero, replaces the 8-bit one
    if len(entry) - pos >= 4:
        (kvno32,) = struct.unpack(">I", entry[pos : pos + 4])
        kvno = kvno32 or kvno
    return (names[0], tuple(names[1:]), kvno, etype, key)


def _keytab_entries(data):
    """Return the entries of a keytab file as a set.

    data is the content of the file, in the binary format or base64 encoded.
    Returns None when it cannot be read as a keytab.
    """
    if not isinstance(data, bytes):
        data = data.encode("utf-8")
    if not data.startswith(KEYTAB_MAGIC):
        try:
            data = base64.b64decode(data)
        except (TypeError, ValueError, binascii.Error):
            return None
        if not data.startswith(KEYTAB_MAGIC):
            return None
    entries = set()
    pos = len(KEYTAB_MAGIC)
    try:
        while pos + 4 <= len(data):
            (size,) = struct.unpack(">i", data[pos : pos + 4])
            pos += 4
            if size == 0:
                break
            if size < 0:
                # a hole left by a removed entry
                pos -= size
                continue
            if pos + size > len(data):
                return None
            entries.add(_keytab_entry(data[pos : pos + size]))
            pos += size
    except struct.error:
        return None
    return entries


def _read_keytab_file(module):
    """Return the content of the keytab file as it is uploaded.

    A binary file is read as bytes and any other file as text. A file that
    cannot be read fails the task, in check mode as well.
    """
    path = module.params["keytab_file"]
    mode = "rb" if module.params["filetype"] == "binary" else "r"
    try:
        with open(path, mode) as keytab_file:
            return keytab_file.read()
    except (IOError, OSError, ValueError) as exc:
        module.fail_json(
            msg="Failed to read keytab file {0}. Error: {1}".format(path, exc)
        )


def _check_server(module, blade):
    """Fail when the server named in the prefix does not exist.

    A prefix is prefix, server::prefix or realm::server::prefix. The array
    refuses an import for a server it does not have, so the task fails
    before anything is sent, in check mode as well.
    """
    prefix = module.params["prefix"]
    server = prefix.rpartition("::")[0]
    if not server:
        return
    if LooseVersion(SERVERS_API_VERSION) > LooseVersion(get_rest_api_version(blade)):
        return
    res = blade.get_servers(names=[server])
    if res.status_code == 200:
        return
    if _is_missing(res):
        module.fail_json(
            msg="Server {0} named in prefix {1} does not exist.".format(server, prefix)
        )
    module.fail_json(
        msg="Failed to read server {0}. Error: {1}".format(
            server, get_error_message(res)
        )
    )


def _already_imported(module, blade, data):
    """Return True when the keytabs of the prefix hold every entry of the file.

    The entries are compared with their keys. The array returns the keys of
    its keytabs only as a keytab file, so the keytabs of the prefix are
    downloaded, read and removed again. Nothing is written to the array.
    A file that cannot be read as a keytab is never reported as imported.
    """
    wanted = _keytab_entries(data)
    if not wanted:
        return False
    prefix = _stored_name(module.params["prefix"])
    kwargs = {}
    if FILTER_SAFE.match(prefix):
        kwargs["filter"] = "prefix='{0}'".format(prefix)
    res = blade.get_keytabs(**kwargs)
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read the keytabs of prefix {0}. Error: {1}".format(
                prefix, get_error_message(res)
            )
        )
    # the array matches names without regard to case
    names = [
        item.name
        for item in list(res.items)
        if str(item.prefix).lower() == prefix.lower()
    ]
    for start in range(0, len(names), DOWNLOAD_BATCH):
        res = _private_call(
            blade.get_keytabs_download,
            keytab_names=names[start : start + DOWNLOAD_BATCH],
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to read the keytabs of prefix {0}. Error: {1}".format(
                    prefix, get_error_message(res)
                )
            )
        files = _saved_files(res)
        try:
            for path in files:
                with open(path, "rb") as keytab_file:
                    wanted -= _keytab_entries(keytab_file.read()) or set()
        finally:
            _remove_files(files)
        if not wanted:
            return True
    return False


def _rotate_account(module, blade):
    """Return the name of the Active Directory account to rotate.

    The account named in ad_account, or the only account of the array. With
    several accounts and none named the task fails rather than pick one.
    """
    res = blade.get_active_directory()
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read the Active Directory accounts. Error: {0}".format(
                get_error_message(res)
            )
        )
    accounts = [item.name for item in list(res.items)]
    wanted = module.params["ad_account"]
    if wanted:
        # the array matches names without regard to case
        for account in accounts:
            if account.lower() == wanted.lower():
                return account
        module.fail_json(
            msg="Active Directory account {0} does not exist".format(wanted)
        )
    if not accounts:
        module.fail_json(msg="No active directory account configured to rotate")
    if len(accounts) > 1:
        module.fail_json(
            msg="The array has more than one Active Directory account ({0}). "
            "Name the account to rotate in ad_account.".format(
                ", ".join(sorted(accounts))
            )
        )
    return accounts[0]


def rotate_keytab(module, blade):
    """Rotate keytab"""
    changed = True
    account = _rotate_account(module, blade)
    prefix = module.params["prefix"] or account
    keytab = KeytabPost(
        source=Reference(name=account, resource_type="active-directory")
    )
    if not module.check_mode:
        res = blade.post_keytabs(keytab=keytab, name_prefixes=prefix)
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to rotate the keytabs of AD account {0}, prefix {1}. "
                "Error: {2}".format(account, prefix, get_error_message(res))
            )
    module.exit_json(changed=changed)


def delete_keytab(module, blade):
    """Delete keytab"""
    changed = False
    name = module.params["name"]
    keytabs = _get_keytabs(module, blade, name)
    if len(keytabs) > 1 or len([part for part in name.split(",") if part.strip()]) > 1:
        # The array reads a comma in a name as a separator, deletes one keytab
        # in a request and answers "does not exist" for a list with one name
        # that is gone. Deleting the first keytab only, or taking that answer
        # for the whole list, would report keytabs absent that are still there.
        module.fail_json(
            msg="{0} names more than one keytab. state=absent deletes one "
            "keytab: name one.".format(name)
        )
    if keytabs:
        changed = True
        if not module.check_mode:
            res = blade.delete_keytabs(names=[keytabs[0].name])
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to delete keytab {0}. Error: {1}".format(
                        module.params["name"], get_error_message(res)
                    )
                )
    module.exit_json(changed=changed)


def import_keytab(module, blade):
    """Import keytab"""
    if not module.params["prefix"]:
        module.fail_json(msg="prefix must not be empty for state=import")
    keytab_data = _read_keytab_file(module)
    _check_server(module, blade)
    changed = not _already_imported(module, blade, keytab_data)
    if changed and not module.check_mode:
        short_name = module.params["keytab_file"].split("/")[-1]
        res = _private_call(
            blade.post_keytabs_upload,
            name_prefixes=module.params["prefix"],
            keytab_file=(short_name, keytab_data),
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to import keytab file {0}. Error: {1}".format(
                    module.params["keytab_file"], get_error_message(res)
                )
            )
        # The array answers with the uploaded file and the SDK saves it in
        # the temporary directory, where it would stay as a copy of the keys.
        _remove_files(_saved_files(res))

    module.exit_json(changed=changed)


def export_keytab(module, blade):
    """Export keytab"""
    # Exporting is a read; it never changes the array.
    changed = False
    download_file = ""
    keytabs = _get_keytabs(module, blade, module.params["name"])
    if keytabs and not module.check_mode:
        res = _private_call(
            blade.get_keytabs_download,
            keytab_names=[keytab.name for keytab in keytabs],
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to export keytab {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
        download_file = list(res.items)[0]
        # a file of that name may have been there before with other permissions
        try:
            os.chmod(download_file, 0o600)
        except (OSError, TypeError):
            pass
    module.exit_json(changed=changed, download_file=download_file)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(
                type="str",
                default="import",
                choices=["absent", "rotate", "import", "export"],
            ),
            name=dict(type="str"),
            prefix=dict(type="str"),
            ad_account=dict(type="str"),
            keytab_file=dict(type="str"),
            filetype=dict(type="str", choices=["binary", "base64"]),
        )
    )

    required_if = [
        ["state", "import", ["prefix", "keytab_file"]],
        ["state", "absent", ["name"]],
        ["state", "export", ["name"]],
    ]
    module = AnsibleModule(
        argument_spec, required_if=required_if, supports_check_mode=True
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    state = module.params["state"]
    blade = get_system(module)

    if state == "import":
        import_keytab(module, blade)
    elif state == "export":
        export_keytab(module, blade)
    elif state == "rotate":
        rotate_keytab(module, blade)
    elif state == "absent":
        delete_keytab(module, blade)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
