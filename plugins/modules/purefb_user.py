#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2019, Simon Dodsley (simon@everpuredata.com)
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
module: purefb_user
version_added: '1.0.0'
short_description: Create, modify or delete FlashBlade user accounts
description:
- Create, modify or delete local users and service accounts on a FlashBlade,
  and manage the API token, SSH key and authorization model of remote users.
- User accounts are array-level objects and cannot be placed in a realm. An
  account is confined to a realm by the management access policies it holds
  (see I(management_access_policies)), not by its name.
- An account that is confined to a realm is shown no account but its own, so
  to it every other account looks absent. The array refuses its requests to
  create an account, to delete itself, to change its own management access
  policies and to replace its own API token. The task then fails with the
  message of the array; check mode does not predict the refusal. Run this
  module as an administrator with array-wide access.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  state:
    description:
    - Create, delete or update local user account
    default: present
    type: str
    choices: [ absent, present ]
    version_added: "1.21.0"
  name:
    description:
    - The name of the user account
    - A name has 1 to 32 characters (lower-case letters, digits and C(-))
      and begins and ends with a letter or digit.
    - User accounts are array-level objects, so a realm-qualified name
      (C(realm::name)) is refused.
    type: str
    required: true
  role:
    description:
    - Sets the local user's access level to the system
    - A new local user is created with C(readonly) when neither I(role) nor
      I(management_access_policies) is given.
    - When omitted for an existing user the current role is left unchanged.
    - Mutually exclusive with I(management_access_policies).
    - Each of the four roles applies to the whole array. Use
      I(management_access_policies) to confine an account to a realm.
    - A user that holds several management access policies, or a custom one,
      has no legacy role. The requested role is then satisfied when it is one
      of the user's policies; the policy set is left alone and a warning names
      the other policies the user holds. Otherwise the module fails, because
      the array refuses a role change on such a user.
      Use M(everpure.flashblade.purefb_mgmt_role) to change its policies.
    type: str
    choices: [ readonly, ops_admin, storage_admin, array_admin ]
    version_added: "1.21.0"
  password:
    description:
    - Password for the local user.
    - Changing the password of an existing account also needs
      I(old_password). Without it the task returns unchanged and no other
      option is applied either.
    - Not allowed for a service account.
    type: str
  old_password:
    description:
    - If changing an existing password, you must provide the old password for security
    type: str
  api:
    description:
    - Define whether to create an API token for this user
    - An existing token is replaced, so this is not idempotent.
    - Token can be exposed using the I(debug) module
    type: bool
    default: false
    version_added: "1.21.0"
  timeout:
    description:
      - The duration of API token validity.
      - Valid values are weeks (w), days(d), hours(h), minutes(m) and seconds(s).
      - The default of C("0") creates a token that does not expire.
    type: str
    default: "0"
    version_added: "1.21.0"
  public_key:
    description:
    - SSH public key for the user in OpenSSH C(authorized_keys) format, for
      example C(ssh-rsa AAAA... comment) or C(ssh-ed25519 AAAA... comment).
    - The array accepts at most two keys, one per line.
    - PEM blocks (I(-----BEGIN PUBLIC KEY-----)) are rejected. That is the
      key format of M(everpure.flashblade.purefb_apiclient); the array treats
      every line of a PEM block as a separate SSH key.
    - Keys are compared by type and key material, so a different comment or
      whitespace is not a change. When the array masks the stored key
      (reported as C(****)) only its presence can be checked; clear it with
      C("") before setting a different key.
    - An empty string removes the user's public key.
    type: str
    version_added: "1.8.0"
  clear_lock:
    description:
    - Clear user lockout flag
    type: bool
    default: false
    version_added: "1.8.0"
  ad_user:
    description:
      - Whether the user is in the AD system
      - Not required for local users
    type: bool
    default: false
    version_added: "1.21.0"
  admin_type:
    description:
    - The type of account to create. A C(local-user) is a regular local
      account. A C(service-account) is a local account intended only for
      REST API access, for automation.
    - A service account has no password and cannot hold an SSH public key,
      so I(password), I(old_password) and I(public_key) are refused for it.
      It cannot log in to the GUI or CLI, and password policy and lockout do
      not apply to it. Its API token is not created automatically; request
      one with I(api).
    - A service account cannot be a member of an SSH certificate authority
      policy or a management authentication policy and, like every local
      account, cannot run remote operations on other fleet members.
    - Set when the account is created and never changed. The module fails
      when an existing account has a different type. A new account is a
      C(local-user) when omitted.
    - C(service-account) requires Purity//FB 4.8.1 or higher (REST 2.26).
    type: str
    choices: [ local-user, service-account ]
    version_added: '1.30.0'
  management_access_policies:
    description:
    - Names of the management access policies that give the account its
      permissions, instead of a legacy I(role).
    - A local user or service account becomes a member of exactly these
      policies. Missing policies are added before surplus ones are removed,
      so the account is never left without one. Names are compared without
      regard to case. The policies of C(pureuser) cannot be changed. The
      list is not compared when I(password) is given without
      I(old_password) for an existing account (see I(password)).
    - An account that holds only policies whose rules are all scoped to
      realms is confined to those realms, with the role each rule grants
      there. Such a policy is made with
      M(everpure.flashblade.purefb_mgmt_policy), by a rule whose scope has
      I(resource_type=realms). The policies themselves are array-level
      objects, so they are named without a realm.
    - For a remote user (I(ad_user=true)) the list is applied only together
      with I(authorization_model=static) and may be empty. A remote user
      addressed without I(ad_user) is refused.
    - Mutually exclusive with I(role).
    - Requires Purity//FB 4.6.1 or higher (REST 2.19).
    type: list
    elements: str
    version_added: '1.30.0'
  authorization_model:
    description:
    - Where the management access policies of a remote user (I(ad_user=true))
      are decided. With C(dynamic), the array default, they come from the
      directory service or identity provider at every login. With C(static)
      they are fixed on the array to I(management_access_policies).
    - C(static) requires I(management_access_policies). The array does not
      convert a remote user that holds an API token or SSH public key, and a
      static user cannot be given either afterwards, so the module fails
      before the call when the user holds one or when I(api) or
      I(public_key) is requested in the same task. For a user that is already
      static the policy set is converged as for a local user.
    - C(dynamic) returns a static user to directory-service authorization.
    - Requires Purity//FB 4.6.8 or higher (REST 2.24).
    type: str
    choices: [ static, dynamic ]
    version_added: '1.30.0'
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Change password for local user (NOT IDEMPOTENT)
  everpure.flashblade.purefb_user:
    name: pureuser
    password: anewpassword
    old_password: apassword
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Set public key for user
  everpure.flashblade.purefb_user:
    name: fred
    public_key: "{{lookup('file', 'public_pem_file') }}"
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Clear user lockout
  everpure.flashblade.purefb_user:
    name: fred
    clear_lock: true
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Create an API token (TTL of 2 days) and assign a public key to an AD user
  everpure.flashblade.purefb_user:
    name: ansible-ad
    ad_user: true
    public_key: "{{lookup('file', 'id_rsa.pub') }}"
    api: true
    timeout: 2d
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Create a service account for automation with an API token
  everpure.flashblade.purefb_user:
    name: svc-backup
    admin_type: service-account
    management_access_policies:
      - storage_admin
    api: true
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
  register: result
  no_log: true

- name: Create a local user that holds two management access policies
  everpure.flashblade.purefb_user:
    name: ops
    password: apassword
    management_access_policies:
      - ops_admin
      - readonly
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Create a management access policy that grants the admin role in one realm
  everpure.flashblade.purefb_mgmt_policy:
    name: realm-a-admins
    rules:
      - role: admin
        scope:
          name: realm-a
          resource_type: realms
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Create a realm administrator, a service account confined to that realm
  everpure.flashblade.purefb_user:
    name: realm-a-svc
    admin_type: service-account
    management_access_policies:
      - realm-a-admins
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Fix the policies of a remote user on the array
  everpure.flashblade.purefb_user:
    name: ad-ops
    ad_user: true
    authorization_model: static
    management_access_policies:
      - ops_admin
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6

- name: Return a remote user to directory-service authorization
  everpure.flashblade.purefb_user:
    name: ad-ops
    ad_user: true
    authorization_model: dynamic
    fb_url: 10.10.10.2
    api_token: T-9f276a18-50ab-446e-8a0c-666a3529a1b6
"""

RETURN = r"""
user_info:
  description:
  - The new API token when I(api) is true, otherwise
    C(No API token created).
  - The token is a secret; register the result with C(no_log) and never
    print it.
  returned: when I(state) is C(present)
  type: str
  sample: "No API token created"
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        AdminPatch,
        AdminPost,
        ReferenceWritable,
    )
except ImportError:
    HAS_PYPURECLIENT = False

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.everpure.flashblade.plugins.module_utils.time_utils import (
    time_to_milliseconds,
    TimeConversionError,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.purefb import (
    get_system,
    purefb_argument_spec,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.version import (
    LooseVersion,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.common import (
    get_error_message,
    get_rest_api_version,
)
import re
import time

MIN_LOCAL_USER = "2.15"
MIN_EXPOSE_API = "2.18"
MIN_POLICIES = "2.19"
MIN_AUTH_MODEL = "2.24"
MIN_SERVICE_ACCOUNT = "2.26"
DEFAULT_ROLE = "readonly"
SERVICE_ACCOUNT = "service-account"
STATIC = "static"
DYNAMIC = "dynamic"
# Value the array reports for a stored public key when it masks it.
PUBLIC_KEY_MASK = "****"
MAX_PUBLIC_KEYS = 2
# The names the module accepts for a user account.
NAME_PATTERN = re.compile("^[a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?$")
REALM_NAME_MSG = (
    "Invalid name '{0}': user accounts are array-level objects and their names "
    "cannot be realm-qualified (realm::name). Use the unqualified account "
    "name. To confine an account to a realm, give it only management access "
    "policies whose rules are scoped to that realm "
    "(management_access_policies)."
)
# One OpenSSH authorized_keys entry: "<type> <base64 key> [comment]"
OPENSSH_KEY_LINE = re.compile(r"^(\S+)\s+([A-Za-z0-9+/=]+)(?:\s+.*)?$")


def parse_public_keys(text):
    """Return the (type, key) pairs found in an OpenSSH authorized_keys string.

    Blank lines are ignored. Returns None when any non-empty line is not an
    OpenSSH public key entry (for example a PEM block).
    """
    keys = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        match = OPENSSH_KEY_LINE.match(line)
        if not match:
            return None
        keys.append((match.group(1), match.group(2)))
    return keys


def validate_name(module):
    """Fail before the array is contacted when the name cannot be an account's.

    User accounts are array-level objects: none can be created in a realm,
    so a realm-qualified name (``realm::name``) names nothing. It is refused
    with a message that says how an account is confined to a realm; the
    general name rule does not mention realms.
    """
    name = module.params["name"]
    if "::" in name:
        module.fail_json(msg=REALM_NAME_MSG.format(name))
    if not NAME_PATTERN.match(name):
        module.fail_json(
            msg="name must contain a minimum of 1 and a maximum of 32 characters "
            "(alphanumeric or `-`). All letters must be lowercase."
        )


def validate_public_key(module):
    """Fail early when public_key is not in the format the array accepts.

    The array wants OpenSSH format (``ssh-rsa AAAA...``) and reads one key
    per line, so a PEM block is seen as many keys and rejected with the
    unhelpful "At most 2 public keys can be uploaded for a user".
    """
    text = module.params["public_key"]
    if not text or not text.strip():
        return
    keys = parse_public_keys(text)
    if keys is None:
        module.fail_json(
            msg=(
                "public_key must be in OpenSSH authorized_keys format "
                "('ssh-rsa AAAA...' or 'ssh-ed25519 AAAA...', one key per "
                "line). PEM blocks are the purefb_apiclient key format and "
                "are not accepted for SSH access."
            )
        )
    if len(keys) > MAX_PUBLIC_KEYS:
        module.fail_json(
            msg="At most {0} public keys can be set for a user".format(MAX_PUBLIC_KEYS)
        )


def public_key_changed(module, user):
    """Return True when the requested public key differs from the user's.

    Keys are compared by type and key material only, so comments and
    whitespace do not count. An empty request clears the key and is a
    change only while a key is set. A masked value (``****``) means the
    array does not return stored keys; only presence can be compared then.
    """
    desired = module.params["public_key"]
    if desired is None:
        return False
    current = getattr(user, "public_key", None) or ""
    if not desired.strip():
        return bool(current.strip())
    if current.strip() == PUBLIC_KEY_MASK:
        return False
    return sorted(parse_public_keys(desired)) != sorted(
        parse_public_keys(current) or []
    )


def set_public_key(module, blade, action="change"):
    """PATCH the user's public key (an empty string clears it)"""
    res = blade.patch_admins(
        names=[module.params["name"]],
        admin=AdminPatch(public_key=module.params["public_key"].strip()),
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to {0} SSH key. Error: {1}".format(
                action, get_error_message(res)
            )
        )


def get_user(module, blade):
    """Return the admin as GET admins reports it, or None when it does not exist.

    The array answers a GET for a missing name with a 400 "Admin does not
    exist.", so only that error reads as None. Any other failure (an expired
    token, a busy or restarting array) fails the task with the array's message
    rather than reading as "absent", which would drive a POST that fails with
    "already exists" or let ``state=absent`` report ok.
    """
    res = blade.get_admins(names=[module.params["name"]])
    if res.status_code == 200:
        items = list(res.items)
        return items[0] if items else None
    error = get_error_message(res)
    if error and "does not exist" in str(error).lower():
        return None
    module.fail_json(
        msg="Failed to read admin {0}. Error: {1}".format(module.params["name"], error)
    )


def get_role_name(user):
    """Return the admin's legacy role name, or None.

    The array sets ``role`` only when the admin holds exactly one management
    access policy that corresponds to a legacy role of the same name. It is
    null for an admin with no, several, or a custom policy.
    """
    return getattr(getattr(user, "role", None), "name", None)


def get_policy_names(user):
    """Return the sorted names of the admin's management access policies"""
    policies = getattr(user, "management_access_policies", None) or []
    return sorted(policy.name for policy in policies if getattr(policy, "name", None))


def role_change(module, user):
    """Return True when the requested role has to be set on the local admin.

    An admin without a legacy role is managed through management access
    policies and the array refuses a role PATCH on it. The requested role
    counts as satisfied when it is one of those policies, with a warning
    when the admin holds others too; the policy set itself belongs to
    purefb_mgmt_role. Any other role fails here, before a call the array
    would reject.
    """
    requested = module.params["role"]
    if not requested or not getattr(user, "is_local", False):
        return False
    current = get_role_name(user)
    if current is not None:
        return requested != current
    policies = get_policy_names(user)
    if requested.lower() in [policy.lower() for policy in policies]:
        others = [policy for policy in policies if policy.lower() != requested.lower()]
        if others:
            module.warn(
                "Local User {0} also holds management access policies {1}; role "
                "{2} is satisfied but not exclusive. Use purefb_mgmt_role to "
                "change its policies.".format(module.params["name"], others, requested)
            )
        return False
    module.fail_json(
        msg=(
            "Local User {0} is managed by management access policies {1} and "
            "has no legacy role, so role {2} cannot be set. Use "
            "purefb_mgmt_role to change its policies."
        ).format(module.params["name"], policies, requested)
    )
    return False


def requested_policy_names(module):
    """Return the requested policy names, duplicates removed without regard to case"""
    names = {}
    for name in module.params["management_access_policies"] or []:
        names.setdefault(name.lower(), name)
    return list(names.values())


def policy_references(module):
    """Return the requested policies as references for a POST or PATCH body"""
    return [ReferenceWritable(name=name) for name in requested_policy_names(module)]


def policy_change(module, user):
    """Return the policies to attach to and to detach from the admin.

    Names are compared without regard to case; detaching uses the array's
    spelling. Both lists are sorted and empty when the sets already match.
    """
    current = {name.lower(): name for name in get_policy_names(user)}
    desired = {name.lower(): name for name in requested_policy_names(module)}
    to_add = sorted(name for key, name in desired.items() if key not in current)
    to_remove = sorted(name for key, name in current.items() if key not in desired)
    return to_add, to_remove


def set_policies(module, blade, to_add, to_remove):
    """Attach, then detach, management access policies of the admin.

    Attaching first means the admin is never left without a policy.
    """
    name = module.params["name"]
    if to_add:
        res = blade.post_management_access_policies_admins(
            member_names=[name], policy_names=to_add
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to attach management access policies {0} to {1}. "
                "Error: {2}".format(to_add, name, get_error_message(res))
            )
    if to_remove:
        res = blade.delete_management_access_policies_admins(
            member_names=[name], policy_names=to_remove
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to detach management access policies {0} from {1}. "
                "Error: {2}".format(to_remove, name, get_error_message(res))
            )


def converge_policies(module, blade, user):
    """Make the admin a member of exactly the requested policies.

    Returns True when the policy set differs; the attach and detach calls
    are skipped in check mode. A remote user is refused: its policies are
    managed with ``ad_user`` and ``authorization_model``.
    """
    if module.params["management_access_policies"] is None:
        return False
    if not getattr(user, "is_local", False):
        module.fail_json(
            msg="User {0} is a remote user; use ad_user true with "
            "authorization_model static to manage its policies".format(
                module.params["name"]
            )
        )
    to_add, to_remove = policy_change(module, user)
    if not to_add and not to_remove:
        return False
    if not module.check_mode:
        set_policies(module, blade, to_add, to_remove)
    return True


def validate_account_params(module):
    """Fail early on option combinations the array refuses.

    A service account has no password or SSH key. A remote user takes a
    policy list only when it is made statically authorized, and a static
    remote user may hold neither an API token nor a public key.
    """
    params = module.params
    policies = params["management_access_policies"]
    model = params["authorization_model"]
    if params["admin_type"] == SERVICE_ACCOUNT:
        if params["ad_user"]:
            module.fail_json(
                msg="A service account is a local account and cannot be a "
                "remote (ad_user) user"
            )
        if (
            params["password"]
            or params["old_password"]
            or params["public_key"] is not None
        ):
            module.fail_json(
                msg="A service account is REST-only: password, old_password and "
                "public_key cannot be set on it"
            )
    if params["ad_user"]:
        if policies is not None and model != STATIC:
            module.fail_json(
                msg="management_access_policies of a remote user are only applied "
                "with authorization_model static"
            )
        if model == STATIC:
            if policies is None:
                module.fail_json(
                    msg="authorization_model static requires "
                    "management_access_policies (an empty list is allowed)"
                )
            if params["api"] or (params["public_key"] and params["public_key"].strip()):
                module.fail_json(
                    msg="A statically authorized remote user cannot hold an API "
                    "token or public key; do not request api or public_key "
                    "with authorization_model static"
                )
    else:
        if model:
            module.fail_json(
                msg="authorization_model applies only to remote users (ad_user: true)"
            )
        if policies is not None and not requested_policy_names(module):
            module.fail_json(
                msg="management_access_policies must name at least one policy for "
                "a local user or service account"
            )


def check_version_gates(module, api_version):
    """Fail before any write when an option needs a newer REST version"""
    if LooseVersion(MIN_LOCAL_USER) > LooseVersion(api_version):
        module.fail_json(
            msg="Purity//FB must be upgraded to support managing local users."
        )
    gates = [
        (
            module.params["management_access_policies"] is not None,
            MIN_POLICIES,
            "management_access_policies",
        ),
        (
            module.params["authorization_model"] is not None,
            MIN_AUTH_MODEL,
            "authorization_model",
        ),
        (
            module.params["admin_type"] == SERVICE_ACCOUNT,
            MIN_SERVICE_ACCOUNT,
            "admin_type service-account",
        ),
    ]
    for requested, minimum, option in gates:
        if requested and LooseVersion(minimum) > LooseVersion(api_version):
            module.fail_json(
                msg="{0} requires Purity//FB REST {1} or higher; the array "
                "supports {2}".format(option, minimum, api_version)
            )


def check_admin_type(module, user):
    """Fail when the request contradicts the type of an existing account.

    ``admin_type`` is fixed when the account is created. A service account
    is REST-only, so a password or public key can never be set on it.
    """
    current = getattr(user, "admin_type", None)
    requested = module.params["admin_type"]
    if requested and current and requested != current:
        module.fail_json(
            msg="User {0} is a {1}; admin_type is set when the account is created "
            "and cannot be changed".format(module.params["name"], current)
        )
    if current == SERVICE_ACCOUNT and (
        module.params["password"]
        or module.params["old_password"]
        or module.params["public_key"] is not None
    ):
        module.fail_json(
            msg="Service account {0} is REST-only: password, old_password and "
            "public_key cannot be set on it".format(module.params["name"])
        )


def new_admin_post(module):
    """Return the POST body for a new local user or service account.

    The account gets the requested management access policies, or else the
    requested legacy role (readonly by default). A service account is sent
    with its type and no password; the type is left out for a local user,
    which older arrays create without the field.
    """
    body = {}
    if module.params["management_access_policies"] is not None:
        body["management_access_policies"] = policy_references(module)
    else:
        body["role"] = ReferenceWritable(name=module.params["role"] or DEFAULT_ROLE)
    if module.params["admin_type"] == SERVICE_ACCOUNT:
        body["admin_type"] = SERVICE_ACCOUNT
    else:
        body["password"] = module.params["password"]
    return AdminPost(**body)


def set_authorization_model(module, blade, user):
    """Converge a remote user's authorization model; return True when changed.

    ``static`` sends the model with the full policy list in one PATCH; on a
    user that is already static only the policy set is converged, through
    the policy membership endpoints. ``dynamic`` sends the model alone and
    is a no-op on a user the array does not report as static.
    """
    requested = module.params["authorization_model"]
    current = getattr(user, "authorization_model", None) if user else None
    name = module.params["name"]
    if requested == DYNAMIC:
        if current != STATIC:
            return False
        if not module.check_mode:
            res = blade.patch_admins(
                names=[name], admin=AdminPatch(authorization_model=DYNAMIC)
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to return remote user {0} to dynamic authorization. "
                    "Error: {1}".format(name, get_error_message(res))
                )
        return True
    if current == STATIC:
        to_add, to_remove = policy_change(module, user)
        if not to_add and not to_remove:
            return False
        if not module.check_mode:
            set_policies(module, blade, to_add, to_remove)
        return True
    if user is not None and (
        has_api_token(user) or (getattr(user, "public_key", None) or "").strip()
    ):
        module.fail_json(
            msg="Remote user {0} holds an API token or public key, which the array "
            "does not allow on a statically authorized user. Remove them first "
            "(state absent clears both).".format(name)
        )
    if not module.check_mode:
        res = blade.patch_admins(
            names=[name],
            admin=AdminPatch(
                authorization_model=STATIC,
                management_access_policies=policy_references(module),
            ),
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to make remote user {0} statically authorized. "
                "Error: {1}".format(name, get_error_message(res))
            )
    return True


def has_api_token(user):
    """Return True if the admin currently holds an API token.

    The token value itself is never returned by GET admins, only its
    ``created_at``/``expires_at`` timestamps, so test those.
    """
    token = getattr(user, "api_token", None)
    return bool(
        getattr(token, "created_at", None) or getattr(token, "expires_at", None)
    )


def get_token_ttl(module):
    """Return the API token validity in milliseconds, or None for no expiry"""
    timeout = module.params["timeout"]
    if timeout in (None, "", "0", 0):
        return None
    try:
        return time_to_milliseconds(timeout)
    except TimeConversionError as err:
        module.fail_json(msg="Invalid timeout {0}: {1}".format(timeout, err))


def delete_api_token(module, blade):
    """Delete the admin's API token"""
    res = blade.delete_admins_api_tokens(admin_names=[module.params["name"]])
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to delete original API token. Error: {0}".format(
                get_error_message(res)
            )
        )


def create_api_token(module, blade):
    """Create an API token for the admin and return it"""
    res = blade.post_admins_api_tokens(
        admin_names=[module.params["name"]], timeout=get_token_ttl(module)
    )
    if res.status_code != 200 and "already created" in (get_error_message(res) or ""):
        # Purity//FB 4.8.8 can still report the token that was deleted a
        # moment ago; give the array a moment and ask once more.
        module.warn(
            "API token create retried: the array still reported the token "
            "deleted a moment ago"
        )
        time.sleep(2)
        res = blade.post_admins_api_tokens(
            admin_names=[module.params["name"]], timeout=get_token_ttl(module)
        )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to create API token. Error: {0}".format(get_error_message(res))
        )
    return list(res.items)[0].api_token.token


def create_local_user(module, blade, user):
    """Create or Update Local User Account or Service Account"""
    changed = key_changed = api_changed = role_changed = passwd_changed = False
    lock_changed = policy_changed = False
    api_token = "No API token created"
    if not user:
        changed = True
        if not module.check_mode:
            res = blade.post_admins(
                names=[module.params["name"]], admin=new_admin_post(module)
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to create user {0}. Error: {1}".format(
                        module.params["name"], get_error_message(res)
                    )
                )
            if module.params["api"]:
                api_token = create_api_token(module, blade)
            if module.params["public_key"] and module.params["public_key"].strip():
                set_public_key(module, blade, action="add")
    else:
        check_admin_type(module, user)
        if module.params["password"] and not module.params["old_password"]:
            module.exit_json(changed=changed, user_info=api_token)
        if (
            module.params["password"]
            and module.params["old_password"]
            and module.params["password"] != module.params["old_password"]
        ):
            passwd_changed = True
            if not module.check_mode:
                res = blade.patch_admins(
                    names=[module.params["name"]],
                    admin=AdminPatch(
                        password=module.params["password"],
                        old_password=module.params["old_password"],
                    ),
                )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Local User {0} password reset failed. Error: {1}"
                        "Check old password.".format(
                            module.params["name"], get_error_message(res)
                        )
                    )
        if module.params["api"]:
            api_changed = True
            if not module.check_mode:
                if has_api_token(user):
                    delete_api_token(module, blade)
                api_token = create_api_token(module, blade)
        if module.params["name"] == "pureuser":
            # the role and policies of pureuser are fixed, whether it is a
            # legacy role or the account is managed by management access
            # policies
            if module.params["role"] and module.params["role"] != get_role_name(user):
                module.warn("Role for 'pureuser' cannot be modified.")
            if module.params["management_access_policies"] is not None and any(
                policy_change(module, user)
            ):
                module.warn(
                    "Management access policies for 'pureuser' cannot be modified."
                )
        elif role_change(module, user):
            role_changed = True
            if not module.check_mode:
                res = blade.patch_admins(
                    names=[module.params["name"]],
                    admin=AdminPatch(
                        role=ReferenceWritable(name=module.params["role"])
                    ),
                )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Local User {0} role changed failed. Error: {1}".format(
                            module.params["name"], get_error_message(res)
                        )
                    )
        elif converge_policies(module, blade, user):
            policy_changed = True
        if public_key_changed(module, user):
            key_changed = True
            if not module.check_mode:
                set_public_key(module, blade)
        if module.params["clear_lock"] and getattr(user, "locked", False):
            lock_changed = True
            if not module.check_mode:
                res = blade.patch_admins(
                    names=[module.params["name"]],
                    admin=AdminPatch(locked=False),
                )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Failed to unlock user {0}. Error: {1}".format(
                            module.params["name"], get_error_message(res)
                        )
                    )
        changed = bool(
            passwd_changed
            or role_changed
            or policy_changed
            or api_changed
            or key_changed
            or lock_changed
        )
    module.exit_json(changed=changed, user_info=api_token)


def update_ad_user(module, blade, user):
    """Update AD user authorization model, API token and/or SSH key"""
    api_token = "No API token created"
    api_changed = ssh_changed = model_changed = False
    if module.params["authorization_model"]:
        model_changed = set_authorization_model(module, blade, user)
    if module.params["api"]:
        api_changed = True
        if not module.check_mode:
            if user and has_api_token(user):
                delete_api_token(module, blade)
            api_token = create_api_token(module, blade)
    if module.params["public_key"] is not None:
        if user is None:
            # An AD user with no array-side state yet: nothing to compare
            # against, and nothing to clear.
            ssh_changed = bool(module.params["public_key"].strip())
        else:
            ssh_changed = public_key_changed(module, user)
        if ssh_changed and not module.check_mode:
            set_public_key(module, blade, action="add")
    changed = bool(model_changed or api_changed or ssh_changed)
    module.exit_json(changed=changed, user_info=api_token)


def delete_ad_user(module, blade, user):
    """Delete AD User Account references"""
    changed = False
    if not module.check_mode:
        if user:
            changed = True
            if has_api_token(user):
                res = blade.delete_admins_api_tokens(
                    admin_names=[module.params["name"]]
                )
                if res.status_code != 200:
                    module.fail_json(
                        msg="AD Account {0} API token deletion failed. Error: {1}".format(
                            module.params["name"], get_error_message(res)
                        )
                    )
            if getattr(user, "public_key", None):
                res = blade.patch_admins(
                    names=[module.params["name"]],
                    admin=AdminPatch(public_key=""),
                )
                if res.status_code != 200:
                    module.fail_json(
                        msg="AD Account {0} public key deletion failed. Error: {1}".format(
                            module.params["name"], get_error_message(res)
                        )
                    )
        res = blade.delete_admins_cache(names=[module.params["name"]])
        if res.status_code != 200:
            module.fail_json(
                msg="Admin Cache deleteion failed for AD user {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def delete_local_user(module, blade):
    """Delete Local User Account"""
    changed = True
    if not module.check_mode:
        res = blade.delete_admins(names=[module.params["name"]])
        if res.status_code != 200:
            module.fail_json(
                msg="User Account {0} deletion failed. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str", required=True),
            public_key=dict(type="str", no_log=True),
            password=dict(type="str", no_log=True),
            old_password=dict(type="str", no_log=True),
            clear_lock=dict(type="bool", default=False),
            role=dict(
                type="str",
                choices=["readonly", "ops_admin", "storage_admin", "array_admin"],
            ),
            state=dict(type="str", default="present", choices=["absent", "present"]),
            api=dict(type="bool", default=False),
            ad_user=dict(type="bool", default=False),
            timeout=dict(type="str", default="0"),
            admin_type=dict(type="str", choices=["local-user", SERVICE_ACCOUNT]),
            management_access_policies=dict(type="list", elements="str"),
            authorization_model=dict(type="str", choices=[STATIC, DYNAMIC]),
        )
    )

    module = AnsibleModule(
        argument_spec,
        supports_check_mode=True,
        mutually_exclusive=[["role", "management_access_policies"]],
    )

    validate_name(module)
    validate_public_key(module)
    validate_account_params(module)
    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    check_version_gates(module, api_version)

    state = module.params["state"]
    user = get_user(module, blade)
    local_user = getattr(user, "is_local", False)

    if state == "present" and not local_user and module.params["ad_user"]:
        update_ad_user(module, blade, user)
    if state == "absent" and local_user:
        delete_local_user(module, blade)
    if state == "absent" and not local_user:
        if user is None and not module.params["ad_user"]:
            # Nothing to delete: the local user does not exist
            module.exit_json(changed=False)
        delete_ad_user(module, blade, user)
    elif state == "present" and not module.params["ad_user"]:
        create_local_user(module, blade, user)
    else:
        module.exit_json(changed=False)


if __name__ == "__main__":
    main()
