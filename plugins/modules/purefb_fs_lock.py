#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2026, Simon Dodsley (simon@everpuredata.com)
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

ANSIBLE_METADATA = {
    "metadata_version": "1.1",
    "status": ["preview"],
    "supported_by": "community",
}

DOCUMENTATION = r"""
---
module: purefb_fs_lock
version_added: '1.30.0'
short_description: List and clear FlashBlade file locks, file sessions and open files
description:
- List the active file locks, the clients holding them, the NFS and SMB file
  sessions and the SMB open files on a FlashBlade, narrowed to a file system,
  path, inode, client or user.
- With I(state=absent) the matching locks, sessions or open files of the
  selected I(target) are cleared, and I(nlm_reclaim=true) starts an
  array-wide NLM lock reclamation.
- Clearing a lock, session or open file is a last resort. The application
  holding it is not consulted and may corrupt its data when another client
  is granted the lock, so only clear locks whose client has gone away, and
  only with the agreement of the owner of the data.
- A I(file_system) that does not exist fails the task. The array also
  rejects a lock request for a I(path) or I(inode) that does not exist.
- Requires FlashBlade REST API version 2.8 or later for locks and NLM
  reclamation, 2.10 or later for sessions and for clearing locks by file
  system, path or inode, 2.17 or later for open files and 2.22 or later for
  I(context).
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  state:
    description:
    - C(query) returns the matching locks, lock clients, sessions and open
      files without changing anything.
    - C(absent) clears the matching objects of I(target), or starts an NLM
      reclamation when I(nlm_reclaim=true).
    type: str
    default: query
    choices: [ absent, query ]
  target:
    description:
    - The kind of object to list or clear.
    - When omitted with I(state=query), every kind the array supports is
      listed, each narrowed by the filter options that apply to it. A kind
      is skipped when a supplied filter does not apply to it, so
      I(file_system) skips sessions, I(user) skips locks and I(protocols)
      skips locks. Open files are skipped when I(protocols) excludes C(smb)
      or I(context) is set. The task fails when the supplied options leave
      no kind to list.
    - Required with I(state=absent) unless I(nlm_reclaim=true).
    type: str
    choices: [ locks, sessions, open_files ]
  file_system:
    description:
    - Name of the file system whose locks or open files to list or clear.
    - A file system in a realm is named C(realm::name). The bare name matches
      only a file system outside every realm.
    - The array can refuse a lock request narrowed to a file system in a
      realm as if the file system did not exist. The task then fails with a
      message that says the file system exists and names its realm.
    - Clearing locks by I(file_system) also needs I(path) or I(inode),
      because the array does not clear locks by file system alone.
      I(path=/) with I(recursive=true) covers the whole file system.
    - Does not apply to sessions, which belong to a client, not a file system.
    type: str
  path:
    description:
    - Paths, relative to the root of I(file_system), of the files whose
      locks or open files to list or clear.
    - Requires I(file_system) and is mutually exclusive with I(inode).
    type: list
    elements: str
  inode:
    description:
    - Inodes, within I(file_system), of the files whose locks to list or
      clear.
    - Requires I(file_system), is mutually exclusive with I(path) and does
      not apply to open files.
    type: list
    elements: int
  client:
    description:
    - IP addresses of the clients whose locks, sessions or open files to
      list or clear.
    type: list
    elements: str
  user:
    description:
    - Names of the users whose sessions or open files to list or clear.
    - Does not apply to locks.
    type: list
    elements: str
  protocols:
    description:
    - File protocols of the sessions or open files to list or clear.
    - Open files are only tracked for SMB. When I(protocols) is omitted the
      module lists and clears SMB open files; the array rejects C(nfs) for
      them.
    - Does not apply to locks, which are returned for every protocol.
    type: list
    elements: str
    choices: [ nfs, smb ]
  recursive:
    description:
    - When I(path) names a directory, also list or clear the locks held on
      every file and subdirectory below it.
    - Applies to locks only. Clearing recursively requires REST API 2.10 or
      later.
    - The listing is narrowed by the path the array reports for each lock,
      so a lock whose path the array cannot report is not listed and is not
      counted when deciding whether there is anything to clear.
    type: bool
    default: false
  disruptive:
    description:
    - Clearing sessions with only one of I(client), I(user) or I(protocols)
      can disconnect a wide set of clients, so the array and this module
      refuse to do it unless this is C(true).
    type: bool
    default: false
  nlm_reclaim:
    description:
    - With I(state=absent), start an NLM lock reclamation. Every NLM (NFSv3)
      lock on the array is dropped and clients are given a grace period in
      which to reclaim their locks.
    - This affects every NFSv3 client, cannot be narrowed by the filter
      options or combined with I(target), and only one reclamation can run
      at a time. The task always reports a change.
    type: bool
    default: false
  context:
    description:
    - Name of fleet member on which to perform the operation.
    - This requires the array receiving the request is a member of a fleet
      and the context name to be a member of the same fleet.
    - Requires REST API 2.22 or later and is not supported for open files.
    type: str
    default: ""
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: List every lock, lock client, session and SMB open file on the array
  everpure.flashblade.purefb_fs_lock:
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
  register: holders

- name: List the locks held on one file
  everpure.flashblade.purefb_fs_lock:
    target: locks
    file_system: projects
    path: /build/output.db
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: List the locks one client holds under a directory
  everpure.flashblade.purefb_fs_lock:
    target: locks
    file_system: projects
    path: /build
    recursive: true
    client: 192.0.2.15
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Clear the stale locks a client that has gone away held on one file
  everpure.flashblade.purefb_fs_lock:
    state: absent
    target: locks
    file_system: projects
    path: /build/output.db
    client: 192.0.2.15
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Close the SMB sessions of one user from one client
  everpure.flashblade.purefb_fs_lock:
    state: absent
    target: sessions
    protocols: smb
    client: 192.0.2.15
    user: alice
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Close every session of one client (a single filter needs disruptive)
  everpure.flashblade.purefb_fs_lock:
    state: absent
    target: sessions
    client: 192.0.2.15
    disruptive: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Close the SMB open files on one file
  everpure.flashblade.purefb_fs_lock:
    state: absent
    target: open_files
    file_system: projects
    path: /build/output.db
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: List the SMB open files on a file system in a realm
  everpure.flashblade.purefb_fs_lock:
    target: open_files
    file_system: tenant1::projects
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Start an array-wide NLM lock reclamation
  everpure.flashblade.purefb_fs_lock:
    state: absent
    nlm_reclaim: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = r"""
locks:
  description:
  - Matching file locks, keyed by lock name. With I(state=absent) these are
    the locks that were cleared, or would be cleared in check mode.
  - C(created_at) is in milliseconds since the UNIX epoch.
  returned: when locks are listed or cleared
  type: dict
  sample:
    "projects-42-1":
      access_type: exclusive
      client: 192.0.2.15
      created_at: 1760000000000
      file_system: projects
      inode: 42
      path: /build/output.db
      protocol: NLM
      range:
        length: 0
        offset: 0
lock_clients:
  description:
  - IP addresses of every client holding a file lock on the array. This
    list is not narrowed by the filter options.
  returned: when locks are listed
  type: list
  elements: str
  sample: ["192.0.2.15"]
sessions:
  description:
  - Matching file sessions, keyed by session name. With I(state=absent)
    these are the sessions that were closed, or would be closed in check
    mode.
  - C(connection_time) is in milliseconds since the UNIX epoch and
    C(idle_time) is a duration in milliseconds.
  returned: when sessions are listed or cleared
  type: dict
  sample:
    "smb-192.0.2.15-51234":
      authentication: NTLMv2
      client: 192.0.2.15
      connection_time: 1760000000000
      idle_time: 5000
      opens: 2
      port: 51234
      protocol: smb
      user: alice
open_files:
  description:
  - Matching SMB open files, keyed by open file ID. With I(state=absent)
    these are the files that were closed, or would be closed in check mode.
  returned: when open files are listed or closed
  type: dict
  sample:
    "11111111-2222-3333-4444-555555555555":
      client: 192.0.2.15
      file_system: projects
      lock_count: 1
      mode: rw
      path: /build/output.db
      session: smb-192.0.2.15-51234
      user: alice
nlm_reclamation:
  description:
  - Start and end of the NLM reclamation, in milliseconds since the UNIX
    epoch. Empty in check mode.
  returned: when I(nlm_reclaim=true)
  type: dict
  sample:
    start: 1760000000000
    end: 1760000090000
"""

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

# Locks, lock clients and NLM reclamation.
MIN_REQUIRED_API_VERSION = "2.8"
# Sessions, and clearing locks by file system, path, inode or recursively
# (REST 2.8 only clears locks by client).
SESSIONS_API_VERSION = "2.10"
OPEN_FILES_API_VERSION = "2.17"
CONTEXT_API_VERSION = "2.22"

FILTERS = ("file_system", "path", "inode", "client", "user", "protocols")
# The filter options each kind of object can be narrowed by.
APPLICABLE_FILTERS = {
    "locks": ("file_system", "path", "inode", "client"),
    "sessions": ("client", "user", "protocols"),
    "open_files": ("file_system", "path", "client", "user", "protocols"),
}


def _context_kwargs(module):
    """Return context_names kwargs when a fleet context is set."""
    if module.params["context"]:
        return {"context_names": [module.params["context"]]}
    return {}


def _ref_name(ref):
    """Name of a reference object, or None when the reference is unset."""
    if ref is None:
        return None
    return getattr(ref, "name", None)


def _filters_set(module):
    """Names of the filter options the task supplied."""
    return [name for name in FILTERS if module.params[name]]


def _filters_apply(module, kind):
    """True when every supplied filter option narrows the given kind of object."""
    return all(name in APPLICABLE_FILTERS[kind] for name in _filters_set(module))


def _under_path(lock_path, paths):
    """True when lock_path is one of paths or lies below one of them.

    Both sides are compared with one leading slash and no trailing slash, so
    a lock path the array reports without a leading slash still matches. A
    lock whose path the array cannot report never matches.
    """
    if not lock_path:
        return False
    lock_path = "/" + lock_path.strip("/")
    for path in paths:
        base = "/" + path.strip("/")
        if base == "/" or lock_path == base or lock_path.startswith(base + "/"):
            return True
    return False


def _lock_kwargs(module, for_delete=False):
    """Query parameters for the lock GET or DELETE built from the filter options.

    A recursive GET is made without paths and narrowed client side, because
    the GET has no recursive flag; the DELETE carries paths and recursive.
    """
    params = module.params
    kwargs = {}
    if params["client"]:
        kwargs["client_names"] = params["client"]
    if params["file_system"]:
        kwargs["file_system_names"] = [params["file_system"]]
    if params["inode"]:
        kwargs["inodes"] = params["inode"]
    if params["path"] and (for_delete or not params["recursive"]):
        kwargs["paths"] = params["path"]
    if for_delete and params["recursive"]:
        kwargs["recursive"] = True
    return kwargs


def _session_kwargs(module):
    """Query parameters for the session GET or DELETE built from the filter options."""
    params = module.params
    kwargs = {}
    if params["client"]:
        kwargs["client_names"] = params["client"]
    if params["user"]:
        kwargs["user_names"] = params["user"]
    if params["protocols"]:
        kwargs["protocols"] = params["protocols"]
    return kwargs


def _open_file_kwargs(module, protocols=None):
    """Query parameters for the open-files GET; protocols is mandatory there."""
    params = module.params
    kwargs = {"protocols": protocols or params["protocols"] or ["smb"]}
    if params["client"]:
        kwargs["client_names"] = params["client"]
    if params["file_system"]:
        kwargs["file_system_names"] = [params["file_system"]]
    if params["path"]:
        kwargs["paths"] = params["path"]
    if params["user"]:
        kwargs["user_names"] = params["user"]
    return kwargs


def _find_file_system(module, blade):
    """Look up the file system named by file_system.

    Returns the file system and None, or None and the array's reason for not
    returning it (None when the array answered with no items).
    """
    res = blade.get_file_systems(
        names=[module.params["file_system"]], **_context_kwargs(module)
    )
    if res.status_code != 200:
        return None, get_error_message(res)
    items = list(res.items)
    return (items[0] if items else None), None


def _realm_name(file_system):
    """Name of the realm a file system is in, or None when it is in no realm."""
    realms = getattr(file_system, "realms", None) or []
    return _ref_name(realms[0]) if realms else None


def fail_locks(module, blade, action, res):
    """Fail a lock request the array refused.

    The array answers a lock request narrowed to a file system in a realm as
    if the file system were missing. When it says the file system does not
    exist the name is looked up, and a file system that is there, in a realm,
    is reported as such.
    """
    error = get_error_message(res)
    msg = "Failed to {0} file locks. Error: {1}".format(action, error)
    file_system = module.params["file_system"]
    if file_system and "file system does not exist" in str(error).lower():
        realm = _realm_name(_find_file_system(module, blade)[0])
        if realm:
            msg += (
                " File system {0} does exist, in realm {1}: the array refused "
                "a lock request narrowed to a file system in a realm.".format(
                    file_system, realm
                )
            )
    module.fail_json(msg=msg)


def check_file_system(module, blade):
    """Fail when file_system names no file system on the array.

    The open-files GET does not check the name: it answers with no items for
    a file system the array does not have, which would read as no open files.
    """
    name = module.params["file_system"]
    file_system, error = _find_file_system(module, blade)
    if file_system is None:
        msg = "Failed to list open files. File system {0} does not exist.".format(name)
        if error:
            msg = (
                "Failed to list open files. File system {0} was not found. "
                "Error: {1}".format(name, error)
            )
        module.fail_json(msg=msg)


def list_locks(module, blade):
    """Return the matching locks keyed by lock name."""
    res = blade.get_file_systems_locks(
        **_lock_kwargs(module), **_context_kwargs(module)
    )
    if res.status_code != 200:
        fail_locks(module, blade, "list", res)
    recursive = module.params["recursive"] and module.params["path"]
    locks = {}
    for lock in list(res.items):
        if recursive and not _under_path(lock.path, module.params["path"]):
            continue
        lock_range = getattr(lock, "range", None)
        locks[lock.name] = {
            "access_type": getattr(lock, "access_type", None),
            "client": _ref_name(getattr(lock, "client", None)),
            "created_at": getattr(lock, "created_at", None),
            "file_system": _ref_name(getattr(lock, "source", None)),
            "inode": getattr(lock, "inode", None),
            "path": getattr(lock, "path", None),
            "protocol": getattr(lock, "protocol", None),
            "range": (
                None
                if lock_range is None
                else {
                    "length": getattr(lock_range, "length", None),
                    "offset": getattr(lock_range, "offset", None),
                }
            ),
        }
    return locks


def list_lock_clients(module, blade):
    """Return the IP addresses of every client holding a file lock."""
    res = blade.get_file_systems_locks_clients(**_context_kwargs(module))
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to list file lock clients. Error: {0}".format(
                get_error_message(res)
            )
        )
    names = [_ref_name(client) for client in list(res.items)]
    return sorted(name for name in names if name)


def list_sessions(module, blade):
    """Return the matching file sessions keyed by session name."""
    res = blade.get_file_systems_sessions(
        **_session_kwargs(module), **_context_kwargs(module)
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to list file sessions. Error: {0}".format(
                get_error_message(res)
            )
        )
    sessions = {}
    for session in list(res.items):
        sessions[session.name] = {
            "authentication": getattr(session, "authentication", None),
            "client": _ref_name(getattr(session, "client", None)),
            "connection_time": getattr(session, "connection_time", None),
            "idle_time": getattr(session, "idle_time", None),
            "opens": getattr(session, "opens", None),
            "port": getattr(session, "port", None),
            "protocol": getattr(session, "protocol", None),
            "user": _ref_name(getattr(session, "user", None)),
        }
    return sessions


def list_open_files(module, blade, protocols=None):
    """Return the matching open files keyed by open file ID."""
    if module.params["file_system"]:
        check_file_system(module, blade)
    res = blade.get_file_systems_open_files(**_open_file_kwargs(module, protocols))
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to list open files. Error: {0}".format(get_error_message(res))
        )
    open_files = {}
    for open_file in list(res.items):
        open_files[open_file.id] = {
            "client": _ref_name(getattr(open_file, "client", None)),
            "file_system": _ref_name(getattr(open_file, "source", None)),
            "lock_count": getattr(open_file, "lock_count", None),
            "mode": getattr(open_file, "mode", None),
            "path": getattr(open_file, "path", None),
            "session": _ref_name(getattr(open_file, "session", None)),
            "user": _ref_name(getattr(open_file, "user", None)),
        }
    return open_files


def list_all(module, blade, api_version):
    """List every kind the array supports that all supplied filters apply to."""
    result = {}
    if _filters_apply(module, "locks"):
        result["locks"] = list_locks(module, blade)
        result["lock_clients"] = list_lock_clients(module, blade)
    if LooseVersion(SESSIONS_API_VERSION) <= LooseVersion(
        api_version
    ) and _filters_apply(module, "sessions"):
        result["sessions"] = list_sessions(module, blade)
    protocols = module.params["protocols"]
    if (
        LooseVersion(OPEN_FILES_API_VERSION) <= LooseVersion(api_version)
        and not module.params["context"]
        and (not protocols or "smb" in protocols)
        and _filters_apply(module, "open_files")
    ):
        result["open_files"] = list_open_files(module, blade, protocols=["smb"])
    if not result:
        module.fail_json(
            msg="None of locks, sessions or open files accept the supplied "
            "options on this array"
        )
    module.exit_json(changed=False, **result)


def clear_locks(module, blade):
    """Clear the matching locks; a no-op when none match."""
    locks = list_locks(module, blade)
    changed = bool(locks)
    if changed and not module.check_mode:
        res = blade.delete_file_systems_locks(
            **_lock_kwargs(module, for_delete=True), **_context_kwargs(module)
        )
        if res.status_code != 200:
            fail_locks(module, blade, "clear", res)
    module.exit_json(changed=changed, locks=locks)


def clear_sessions(module, blade):
    """Close the matching file sessions; a no-op when none match."""
    sessions = list_sessions(module, blade)
    changed = bool(sessions)
    if changed and not module.check_mode:
        kwargs = _session_kwargs(module)
        if module.params["disruptive"]:
            kwargs["disruptive"] = True
        res = blade.delete_file_systems_sessions(**kwargs, **_context_kwargs(module))
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to close file sessions. Error: {0}".format(
                    get_error_message(res)
                )
            )
    module.exit_json(changed=changed, sessions=sessions)


def close_open_files(module, blade):
    """Close the matching open files by ID; a no-op when none match."""
    open_files = list_open_files(module, blade)
    changed = bool(open_files)
    if changed and not module.check_mode:
        res = blade.delete_file_systems_open_files(ids=sorted(open_files))
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to close open files. Error: {0}".format(
                    get_error_message(res)
                )
            )
    module.exit_json(changed=changed, open_files=open_files)


def start_nlm_reclamation(module, blade):
    """Start an NLM reclamation. Always a change: it is a one-shot action."""
    reclamation = {}
    if not module.check_mode:
        res = blade.post_file_systems_locks_nlm_reclamations(**_context_kwargs(module))
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to start NLM reclamation. Error: {0}".format(
                    get_error_message(res)
                )
            )
        items = list(res.items)
        if items:
            reclamation = {
                "end": getattr(items[0], "end", None),
                "start": getattr(items[0], "start", None),
            }
    module.exit_json(changed=True, nlm_reclamation=reclamation)


def check_options(module):
    """Reject option combinations the array cannot act on, before any call."""
    params = module.params
    state = params["state"]
    target = params["target"]
    supplied = _filters_set(module)
    if params["nlm_reclaim"]:
        if state != "absent":
            module.fail_json(msg="nlm_reclaim requires state=absent")
        if target or supplied:
            module.fail_json(
                msg="nlm_reclaim is array-wide and cannot be combined with "
                "target or the filter options"
            )
        return
    if state == "absent" and not target:
        module.fail_json(
            msg="target is required with state=absent unless nlm_reclaim is true"
        )
    if target:
        unsupported = [
            name for name in supplied if name not in APPLICABLE_FILTERS[target]
        ]
        if unsupported:
            module.fail_json(
                msg="{0} does not apply to target={1}".format(
                    ", ".join(unsupported), target
                )
            )
    if params["recursive"]:
        if not params["path"]:
            module.fail_json(msg="recursive requires path")
        if target and target != "locks":
            module.fail_json(msg="recursive applies to locks only")
    if target == "open_files" and params["context"]:
        module.fail_json(msg="context is not supported for open files")
    if state != "absent":
        return
    if target == "locks":
        if not (params["client"] or params["file_system"]):
            module.fail_json(msg="Clearing locks requires client or file_system")
        if params["file_system"] and not (params["path"] or params["inode"]):
            module.fail_json(
                msg="Clearing locks by file_system also requires path or inode: "
                "the array does not clear locks by file system alone. Use "
                "path=/ with recursive=true to cover the whole file system"
            )
    if target == "sessions":
        if not supplied:
            module.fail_json(
                msg="Clearing sessions requires at least one of client, user "
                "or protocols"
            )
        if len(supplied) == 1 and not params["disruptive"]:
            module.fail_json(
                msg="Clearing sessions by {0} alone can disconnect many clients; "
                "set disruptive=true to confirm".format(supplied[0])
            )
    if target == "open_files" and not [
        name for name in supplied if name != "protocols"
    ]:
        module.fail_json(
            msg="Closing open files requires at least one of file_system, path, "
            "client or user"
        )


def check_versions(module, api_version):
    """Fail before any call when an option needs a newer REST API than the array has."""
    params = module.params
    target = params["target"]
    needed = []
    if params["context"]:
        needed.append(("context", CONTEXT_API_VERSION))
    if target == "sessions":
        needed.append(("target=sessions", SESSIONS_API_VERSION))
    if target == "open_files":
        needed.append(("target=open_files", OPEN_FILES_API_VERSION))
    if (
        target == "locks"
        and params["state"] == "absent"
        and (params["file_system"] or params["recursive"])
    ):
        needed.append(
            (
                "Clearing locks by file_system, path, inode or recursive",
                SESSIONS_API_VERSION,
            )
        )
    for option, version in needed:
        if LooseVersion(version) > LooseVersion(api_version):
            module.fail_json(
                msg="{0} requires FlashBlade REST API version {1} or later".format(
                    option, version
                )
            )


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(type="str", default="query", choices=["absent", "query"]),
            target=dict(type="str", choices=["locks", "sessions", "open_files"]),
            file_system=dict(type="str"),
            path=dict(type="list", elements="str"),
            inode=dict(type="list", elements="int"),
            client=dict(type="list", elements="str"),
            user=dict(type="list", elements="str"),
            protocols=dict(type="list", elements="str", choices=["nfs", "smb"]),
            recursive=dict(type="bool", default=False),
            disruptive=dict(type="bool", default=False),
            nlm_reclaim=dict(type="bool", default=False),
            context=dict(type="str", default=""),
        )
    )

    module = AnsibleModule(
        argument_spec,
        supports_check_mode=True,
        mutually_exclusive=[["path", "inode"]],
        required_by={"path": "file_system", "inode": "file_system"},
    )

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg="FlashBlade REST version not supported. "
            "Minimum version required: {0}".format(MIN_REQUIRED_API_VERSION)
        )
    check_options(module)
    check_versions(module, api_version)

    state = module.params["state"]
    target = module.params["target"]
    if module.params["nlm_reclaim"]:
        start_nlm_reclamation(module, blade)
    if state == "query":
        if target is None:
            list_all(module, blade, api_version)
        elif target == "locks":
            module.exit_json(
                changed=False,
                locks=list_locks(module, blade),
                lock_clients=list_lock_clients(module, blade),
            )
        elif target == "sessions":
            module.exit_json(changed=False, sessions=list_sessions(module, blade))
        else:
            module.exit_json(changed=False, open_files=list_open_files(module, blade))
    elif target == "locks":
        clear_locks(module, blade)
    elif target == "sessions":
        clear_sessions(module, blade)
    else:
        close_open_files(module, blade)


if __name__ == "__main__":
    main()
