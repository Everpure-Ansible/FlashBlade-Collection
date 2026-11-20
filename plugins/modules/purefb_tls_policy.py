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
module: purefb_tls_policy
version_added: '1.28.0'
short_description: Manage FlashBlade TLS policies
description:
- Create, update or delete FlashBlade TLS policies and manage the
  network interfaces they are applied to.
- A TLS policy controls the server certificate presented on a network
  interface, the TLS versions and ciphers permitted, and optional
  mutual-TLS settings for verifying client certificates.
- A TLS policy that lives in a realm is addressed by its full name
  C(realm::policy). A policy and the certificate, or certificate group, it
  names must be in the same realm, or both at array level.
author:
- Pure Storage Ansible Team (@avk) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - Name of the TLS policy.
    - A TLS policy that lives in a realm is named C(realm::policy).
    - A realm-scoped administrator must use the realm-qualified name; a
      bare name is not placed in, or resolved to, the administrator's
      realm.
    - This is the name of one policy. The array reads C(*) in a name as a
      pattern and a comma as a separator of names, so a name that holds
      either is refused.
    - The policy is found without regard to letter case. The module then
      uses the name as the array stores it, and creates a new policy in a
      realm with the realm prefix as the array stores it, because the array
      compares the realm of a certificate with the realm prefix as it is
      written in the request.
    type: str
    required: true
  state:
    description:
    - Define whether the TLS policy should exist or not.
    default: present
    choices: [ absent, present ]
    type: str
  enabled:
    description:
    - If C(true) the policy is enabled.
    - Defaults to C(true) on creation if not specified.
    type: bool
  appliance_certificate:
    description:
    - Name of the certificate to present as the server certificate during
      TLS negotiation with clients connecting to network interfaces
      covered by this policy.
    - Required when creating a policy; the array rejects a policy without
      an appliance certificate.
    - C(global) is the built-in certificate of the array and can only be
      used by an array-level policy. Use C(global) to create such a policy
      with the built-in certificate, or to reset one to it, which removes
      a previously assigned custom certificate.
    - A policy that lives in a realm needs a certificate of that realm,
      written C(realm::certificate). The array refuses C(global), any
      other array-level certificate and a certificate of another realm
      for such a policy, and a certificate of a realm for an array-level
      policy, so the module fails such a task before it changes anything.
    - The name is compared with the current certificate without regard to
      letter case, as the array does.
    type: str
  client_certificates_required:
    description:
    - If C(true), all clients must present a client certificate during
      TLS negotiation; failure to do so will be rejected.
    - If C(false), client certificates are optional.
    - The array only accepts C(true) when
      I(verify_client_certificate_trust) is also C(true), which in turn
      needs I(trusted_client_certificate_authority).
    - Requires Purity//FB REST API 2.18 or later.
    type: bool
  trusted_client_certificate_authority:
    description:
    - Name of a certificate, or certificate group, used to verify
      certificates presented by clients when
      I(verify_client_certificate_trust) is C(true).
    - Set to an empty string (C("")) to clear a previously assigned
      trusted CA reference. This only applies on update; on create an
      empty string is treated the same as omitting the parameter.
    - For a policy that lives in a realm, name a certificate or
      certificate group of that realm, written C(realm::name). An
      array-level policy can only use an array-level one. The module
      fails a task that names one from another scope before it changes
      anything.
    - The name is compared with the current reference without regard to
      letter case, as the array does.
    - Requires Purity//FB REST API 2.18 or later.
    type: str
  verify_client_certificate_trust:
    description:
    - If C(true), certificates presented by clients in TLS negotiation
      will undergo strict trust verification using the certificate(s)
      referenced by I(trusted_client_certificate_authority).
    - Requires Purity//FB REST API 2.18 or later.
    type: bool
  min_tls_version:
    description:
    - Minimum TLS version permitted for inbound connections.
    - C(default) lets the array pick a recommended minimum that may shift
      across software upgrades.
    type: str
    choices: [ default, '1.0', '1.1', '1.2', '1.3' ]
  enabled_tls_ciphers:
    description:
    - List of TLS ciphers to enable.
    - When supplied, only these ciphers will be enabled.
    type: list
    elements: str
  disabled_tls_ciphers:
    description:
    - List of TLS ciphers to disable.
    type: list
    elements: str
  network_interfaces:
    description:
    - Desired set of network interfaces this policy should be applied to.
    - On update, the set of attached interfaces is reconciled against
      this list - missing interfaces are attached, extras are detached.
    - Omit entirely to leave existing attachments untouched.
    - Use an empty list to detach the policy from all interfaces.
    - On create, an empty list creates the policy with no interfaces
      attached; this is equivalent to omitting the parameter.
    - A network interface that lives in a realm is named
      C(realm::interface) and must be given in that form.
    - Names are compared with the attached interfaces without regard to
      letter case, as the array does, and an interface is attached by the
      name the array stores.
    type: list
    elements: str
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Create TLS policy with a server cert and minimum TLS 1.2
  everpure.flashblade.purefb_tls_policy:
    name: secure_data_plane
    appliance_certificate: my_cert
    min_tls_version: '1.2'
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Require mutual TLS using a trusted CA group
  everpure.flashblade.purefb_tls_policy:
    name: secure_data_plane
    client_certificates_required: true
    verify_client_certificate_trust: true
    trusted_client_certificate_authority: corp_ca_group
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Apply the policy to a specific set of data network interfaces
  everpure.flashblade.purefb_tls_policy:
    name: secure_data_plane
    network_interfaces:
      - data1.eth0
      - data2.eth0
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Detach the TLS policy from all network interfaces
  everpure.flashblade.purefb_tls_policy:
    name: secure_data_plane
    network_interfaces: []
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Disable a TLS policy without deleting it
  everpure.flashblade.purefb_tls_policy:
    name: secure_data_plane
    enabled: false
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Reset an array-level policy to the built-in global cert and clear the trusted CA
  everpure.flashblade.purefb_tls_policy:
    name: secure_data_plane
    appliance_certificate: global
    trusted_client_certificate_authority: ""
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Create a TLS policy in a realm with a certificate and a trusted CA group of that realm
  everpure.flashblade.purefb_tls_policy:
    name: realm1::data-tls
    appliance_certificate: realm1::tls-cert
    trusted_client_certificate_authority: realm1::corp-ca-group
    verify_client_certificate_trust: true
    min_tls_version: '1.2'
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Delete a TLS policy
  everpure.flashblade.purefb_tls_policy:
    name: secure_data_plane
    state: absent
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3
"""

RETURN = r"""
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        TlsPolicy,
        TlsPolicyPost,
        ReferenceWritable,
    )
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

MIN_REQUIRED_API_VERSION = "2.17"
MIN_MUTUAL_TLS_API_VERSION = "2.18"
REALM_API_VERSION = "2.19"
MUTUAL_TLS_PARAMS = (
    "client_certificates_required",
    "trusted_client_certificate_authority",
    "verify_client_certificate_trust",
)
REFERENCE_PARAMS = (
    "appliance_certificate",
    "trusted_client_certificate_authority",
)


def _realm_of(name):
    """Return the realm of a realm::name name, empty for an array-level name."""
    return name.rpartition("::")[0].strip()


def _same_name(first, second):
    """Tell whether two names are the same name on the array.

    The array matches a name without regard to letter case and returns
    the stored spelling. White space around a name is not part of it.
    """
    return str(first or "").strip().lower() == str(second or "").strip().lower()


def _in_names(name, names):
    """Tell whether name is one of names, as the array compares names."""
    return any(_same_name(name, other) for other in names)


def _check_one_name(module):
    """Refuse a name that the array does not read as the name of one policy.

    In a request the array reads * in a name as a pattern and a comma as a
    separator of names, so such a name reaches every policy that matches
    it, or several at once. This module manages the one policy that has the
    name given, so the name is refused before anything is read.
    """
    name = module.params["name"]
    if "*" in name or "," in name:
        module.fail_json(
            msg="name must be the name of one TLS policy: in {0} the array "
            "reads * as a pattern and a comma as a separator of "
            "names.".format(name)
        )


def _check_reference_scope(module):
    """Fail when a certificate reference is outside the scope of the policy.

    A TLS policy and the certificate, or certificate group, it names are in
    one scope: both carry the same realm prefix, or neither does. The
    built-in certificate global belongs to the array. The array refuses any
    other pair when a policy is created or changed, so such a pair is
    refused before anything is read or written, in check mode too.
    """
    name = module.params["name"]
    realm = _realm_of(name)
    for option in REFERENCE_PARAMS:
        reference = module.params[option]
        if not reference:
            continue
        reference_realm = _realm_of(reference)
        if _same_name(realm, reference_realm):
            continue
        if not realm:
            reason = (
                "{0} is in realm {1} and {2} is an array-level policy. A TLS "
                "policy of that realm is named {1}::<policy>".format(
                    reference, reference_realm, name
                )
            )
        else:
            if reference_realm:
                where = "{0} is in realm {1}".format(reference, reference_realm)
            elif _same_name(reference, "global"):
                where = "global is the built-in certificate of the array"
            else:
                where = "{0} is an array-level name".format(reference)
            reason = (
                "{0} and {1} is in realm {2}. Name a certificate{3} of that "
                "realm, written {2}::<name>".format(
                    where,
                    name,
                    realm,
                    (
                        ""
                        if option == "appliance_certificate"
                        else " or certificate group"
                    ),
                )
            )
        module.fail_json(
            msg="{0} {1} cannot be used by TLS policy {2}: a TLS policy and "
            "the certificates it names must be in the same realm, or all at "
            "array level. {3}.".format(option, reference, name, reason)
        )


def _check_realm(module, blade, api_version):
    """Fail when a new policy is named into a realm that cannot take it.

    The array refuses to create a policy in a realm that does not exist or
    has been destroyed, which check mode cannot foresee, so the realm is
    read before a change is reported. Only a definite answer fails the
    task; anything else is left to the create request.

    The array finds a realm without regard to letter case, but it compares
    the realm of a certificate with the realm prefix as it is written in the
    name of the new policy. The new policy therefore takes the realm prefix
    as the array stores it.
    """
    name = module.params["name"]
    realm = _realm_of(name)
    if not realm or LooseVersion(REALM_API_VERSION) > LooseVersion(api_version):
        return
    res = blade.get_realms(names=[realm])
    if res.status_code == 200:
        items = list(res.items)
        if not items:
            return
        if getattr(items[0], "destroyed", False) is not True:
            stored = getattr(items[0], "name", None)
            if isinstance(stored, str) and _same_name(stored, realm):
                module.params["name"] = "{0}::{1}".format(
                    stored, name.rpartition("::")[2]
                )
            return
        reason = "Realm has been destroyed."
    else:
        reason = get_error_message(res)
        if "does not exist" not in str(reason).lower():
            return
    module.fail_json(
        msg="TLS policy {0} was not found and cannot be created in realm {1}. "
        "Error: {2}".format(name, realm, reason)
    )


def _fail_certificate_required(module):
    """Fail a create that names no appliance certificate.

    The array refuses a policy without one. The built-in certificate global
    is only offered for an array-level name, because the array refuses it
    for every policy in a realm.
    """
    name = module.params["name"]
    realm = _realm_of(name)
    if realm:
        hint = (
            "name a certificate of realm {0}, written {0}::<certificate>. The "
            "built-in certificate global belongs to the array and cannot be "
            "used by a TLS policy in a realm".format(realm)
        )
    else:
        hint = (
            "an array-level policy can use 'global', the built-in appliance "
            "certificate of the array. A TLS policy that lives in a realm is "
            "named <realm>::<policy>, and a realm-scoped administrator must "
            "use that form"
        )
    module.fail_json(
        msg="TLS policy {0} was not found and appliance_certificate is "
        "required to create it: {1}.".format(name, hint)
    )


def _check_mutual_tls_support(module, api_version):
    """Fail early if mutual-TLS options were set but the array does not advertise REST 2.18.

    pypureclient silently drops unknown fields when serialising TlsPolicyPost, so
    without this guard a user on 2.17 would get a successful create with the
    mutual-TLS settings missing from the policy.
    """
    if LooseVersion(MIN_MUTUAL_TLS_API_VERSION) > LooseVersion(api_version):
        used = [p for p in MUTUAL_TLS_PARAMS if module.params.get(p) is not None]
        if used:
            module.fail_json(
                msg=(
                    "Mutual TLS options ({0}) require Purity//FB REST API {1} or later."
                ).format(", ".join(used), MIN_MUTUAL_TLS_API_VERSION)
            )


def _validate_attachable(module, blade, interfaces):
    """Validate every interface in C(interfaces) exists and isn't bound to another TLS policy.

    Called for the to-attach subset only: interfaces already bound to *this* policy
    do not conflict and are left alone.

    Returns the interfaces by the names the array stores, each once, in the
    order given. The attach request carries these names, so that a name
    given in another letter case is sent as the array stores it.
    """
    if not interfaces:
        return []
    res = blade.get_network_interfaces(
        names=interfaces,
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Network interface(s) not found: {0}. Error: {1}".format(
                interfaces, get_error_message(res)
            )
        )
    found = [getattr(i, "name", None) for i in (res.items or [])]
    missing = [i for i in interfaces if not _in_names(i, found)]
    if missing:
        module.fail_json(msg="Network interface(s) not found: {0}".format(missing))

    res = blade.get_tls_policies_network_interfaces(
        member_names=interfaces,
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read the TLS policies of network interface(s) {0}. "
            "Error: {1}".format(interfaces, get_error_message(res))
        )
    our_name = module.params["name"]
    conflicts = []
    for item in res.items or []:
        policy_name = getattr(getattr(item, "policy", None), "name", None)
        member_name = getattr(getattr(item, "member", None), "name", None)
        if policy_name and not _same_name(policy_name, our_name):
            conflicts.append((member_name, policy_name))
    if conflicts:
        formatted = ", ".join("{0}=>{1}".format(m, p) for m, p in conflicts)
        module.fail_json(
            msg=(
                "Cannot attach TLS policy {0} - the following interface(s) already "
                "have a different TLS policy applied: {1}. Detach the existing "
                "policy before re-attaching."
            ).format(our_name, formatted)
        )
    stored = []
    for interface in interfaces:
        for name in found:
            if isinstance(name, str) and _same_name(interface, name):
                break
        else:
            name = interface
        if name not in stored:
            stored.append(name)
    return stored


def _get_policy(module, blade):
    """Return the TLS policy called name, or None when it does not exist.

    Only the array's "does not exist" means that there is no such policy.
    Any other answer fails the task with the array's message: read as absent
    it would let state=absent report that there is nothing to delete, and
    state=present ask for a policy to be created that may exist.
    """
    name = module.params["name"]
    res = blade.get_tls_policies(
        names=[name],
    )
    if res.status_code == 200:
        items = list(res.items)
        for item in items:
            if _same_name(getattr(item, "name", None), name):
                return item
        if items:
            module.fail_json(
                msg="Failed to read TLS policy {0}: the array answered with "
                "{1}, which does not have that name.".format(
                    name,
                    ", ".join(str(getattr(item, "name", None)) for item in items[:5]),
                )
            )
        return None
    error = get_error_message(res)
    if "does not exist" in str(error).lower():
        return None
    module.fail_json(
        msg="Failed to read TLS policy {0}. Error: {1}".format(name, error)
    )


def _get_attached_interfaces(module, blade):
    """Return a sorted list of network interface names this policy is applied to.

    A list the array does not return fails the task with the array's
    message: read as empty it would report that nothing is attached.
    """
    res = blade.get_tls_policies_network_interfaces(
        policy_names=[module.params["name"]],
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to list the network interfaces of TLS policy {0}. "
            "Error: {1}".format(module.params["name"], get_error_message(res))
        )
    names = []
    for item in res.items or []:
        member = getattr(item, "member", None)
        member_name = getattr(member, "name", None)
        if member_name:
            names.append(member_name)
    return sorted(names)


def _build_post_kwargs(module):
    """Build kwargs for TlsPolicyPost from module params."""
    kwargs = {}
    if module.params["enabled"] is not None:
        kwargs["enabled"] = module.params["enabled"]
    if module.params["appliance_certificate"]:
        kwargs["appliance_certificate"] = ReferenceWritable(
            name=module.params["appliance_certificate"]
        )
    if module.params["client_certificates_required"] is not None:
        kwargs["client_certificates_required"] = module.params[
            "client_certificates_required"
        ]
    if module.params["trusted_client_certificate_authority"]:
        kwargs["trusted_client_certificate_authority"] = ReferenceWritable(
            name=module.params["trusted_client_certificate_authority"]
        )
    if module.params["verify_client_certificate_trust"] is not None:
        kwargs["verify_client_certificate_trust"] = module.params[
            "verify_client_certificate_trust"
        ]
    if module.params["min_tls_version"]:
        kwargs["min_tls_version"] = module.params["min_tls_version"]
    if module.params["enabled_tls_ciphers"] is not None:
        kwargs["enabled_tls_ciphers"] = module.params["enabled_tls_ciphers"]
    if module.params["disabled_tls_ciphers"] is not None:
        kwargs["disabled_tls_ciphers"] = module.params["disabled_tls_ciphers"]
    return kwargs


def _reconcile_interfaces(module, blade):
    """Reconcile policy network-interface attachments to the desired set.

    Returns True if any attach/detach was needed. Names are compared as the
    array compares them, so an attached interface given in another letter
    case is neither attached again nor detached.
    """
    desired = sorted(module.params["network_interfaces"])
    current = _get_attached_interfaces(module, blade)
    to_attach = [i for i in desired if not _in_names(i, current)]
    to_detach = [i for i in current if not _in_names(i, desired)]

    if not (to_attach or to_detach):
        return False

    if to_attach:
        to_attach = _validate_attachable(module, blade, to_attach)

    if module.check_mode:
        return True

    attached = []
    for iface in to_attach:
        res = blade.post_tls_policies_network_interfaces(
            policy_names=[module.params["name"]],
            member_names=[iface],
        )
        if res.status_code != 200:
            note = " Already attached: {0}.".format(attached) if attached else ""
            module.fail_json(
                msg="Failed to attach TLS policy {0} to interface {1}. Error: {2}.{3}".format(
                    module.params["name"], iface, get_error_message(res), note
                )
            )
        attached.append(iface)

    detached = []
    for iface in to_detach:
        res = blade.delete_tls_policies_network_interfaces(
            policy_names=[module.params["name"]],
            member_names=[iface],
        )
        if res.status_code != 200:
            note = " Already detached: {0}.".format(detached) if detached else ""
            module.fail_json(
                msg="Failed to detach TLS policy {0} from interface {1}. Error: {2}.{3}".format(
                    module.params["name"], iface, get_error_message(res), note
                )
            )
        detached.append(iface)

    return True


def delete_policy(module, blade):
    """Delete a TLS policy, detaching it from any network interfaces first."""
    changed = True
    if not module.check_mode:
        attached = _get_attached_interfaces(module, blade)
        detached = []
        for iface in attached:
            res = blade.delete_tls_policies_network_interfaces(
                policy_names=[module.params["name"]],
                member_names=[iface],
            )
            if res.status_code != 200:
                note = " Already detached: {0}.".format(detached) if detached else ""
                module.fail_json(
                    msg="Failed to detach TLS policy {0} from interface {1}. Error: {2}.{3}".format(
                        module.params["name"], iface, get_error_message(res), note
                    )
                )
            detached.append(iface)
        res = blade.delete_tls_policies(
            names=[module.params["name"]],
        )
        if res.status_code != 200:
            detached_note = ""
            if attached:
                detached_note = (
                    " The policy has already been detached from interfaces {0};"
                    " re-run to retry deletion or reattach manually if needed."
                ).format(attached)
            module.fail_json(
                msg="Failed to delete TLS policy {0}. Error: {1}.{2}".format(
                    module.params["name"], get_error_message(res), detached_note
                )
            )
    module.exit_json(changed=changed)


def create_policy(module, blade, api_version):
    """Create a new TLS policy and optionally attach it to interfaces."""
    changed = True
    _check_realm(module, blade, api_version)
    if not module.params["appliance_certificate"]:
        _fail_certificate_required(module)
    interfaces = []
    if module.params["network_interfaces"]:
        interfaces = _validate_attachable(
            module, blade, module.params["network_interfaces"]
        )
    if not module.check_mode:
        res = blade.post_tls_policies(
            names=[module.params["name"]],
            policy=TlsPolicyPost(**_build_post_kwargs(module)),
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to create TLS policy {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
        attached = []
        for iface in interfaces:
            res = blade.post_tls_policies_network_interfaces(
                policy_names=[module.params["name"]],
                member_names=[iface],
            )
            if res.status_code != 200:
                note = " Already attached: {0}.".format(attached) if attached else ""
                module.fail_json(
                    msg="Failed to attach TLS policy {0} to interface {1}. Error: {2}.{3}".format(
                        module.params["name"], iface, get_error_message(res), note
                    )
                )
            attached.append(iface)
    module.exit_json(changed=changed)


def update_policy(module, blade, policy):
    """Update a TLS policy and reconcile its network-interface attachments."""
    changed = False
    patch_kwargs = {}

    if module.params["enabled"] is not None and module.params["enabled"] != getattr(
        policy, "enabled", None
    ):
        patch_kwargs["enabled"] = module.params["enabled"]

    if module.params["min_tls_version"] and module.params["min_tls_version"] != getattr(
        policy, "min_tls_version", None
    ):
        patch_kwargs["min_tls_version"] = module.params["min_tls_version"]

    if module.params["client_certificates_required"] is not None and module.params[
        "client_certificates_required"
    ] != getattr(policy, "client_certificates_required", None):
        patch_kwargs["client_certificates_required"] = module.params[
            "client_certificates_required"
        ]

    if module.params["verify_client_certificate_trust"] is not None and module.params[
        "verify_client_certificate_trust"
    ] != getattr(policy, "verify_client_certificate_trust", None):
        patch_kwargs["verify_client_certificate_trust"] = module.params[
            "verify_client_certificate_trust"
        ]

    if module.params["enabled_tls_ciphers"] is not None:
        current = list(getattr(policy, "enabled_tls_ciphers", None) or [])
        if sorted(module.params["enabled_tls_ciphers"]) != sorted(current):
            patch_kwargs["enabled_tls_ciphers"] = module.params["enabled_tls_ciphers"]

    if module.params["disabled_tls_ciphers"] is not None:
        current = list(getattr(policy, "disabled_tls_ciphers", None) or [])
        if sorted(module.params["disabled_tls_ciphers"]) != sorted(current):
            patch_kwargs["disabled_tls_ciphers"] = module.params["disabled_tls_ciphers"]

    if module.params["appliance_certificate"]:
        current = getattr(getattr(policy, "appliance_certificate", None), "name", None)
        if not _same_name(module.params["appliance_certificate"], current):
            patch_kwargs["appliance_certificate"] = ReferenceWritable(
                name=module.params["appliance_certificate"]
            )

    if module.params["trusted_client_certificate_authority"] is not None:
        current = (
            getattr(
                getattr(policy, "trusted_client_certificate_authority", None),
                "name",
                None,
            )
            or ""
        )
        if not _same_name(
            module.params["trusted_client_certificate_authority"], current
        ):
            patch_kwargs["trusted_client_certificate_authority"] = ReferenceWritable(
                name=module.params["trusted_client_certificate_authority"]
            )

    if module.params["network_interfaces"] is not None:
        if _reconcile_interfaces(module, blade):
            changed = True

    if patch_kwargs:
        changed = True
        if not module.check_mode:
            res = blade.patch_tls_policies(
                names=[module.params["name"]],
                policy=TlsPolicy(**patch_kwargs),
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to update TLS policy {0}. Error: {1}".format(
                        module.params["name"], get_error_message(res)
                    )
                )

    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(type="str", default="present", choices=["absent", "present"]),
            name=dict(type="str", required=True),
            enabled=dict(type="bool"),
            appliance_certificate=dict(type="str"),
            client_certificates_required=dict(type="bool"),
            trusted_client_certificate_authority=dict(type="str"),
            verify_client_certificate_trust=dict(type="bool"),
            min_tls_version=dict(
                type="str",
                choices=[
                    "default",
                    "1.0",
                    "1.1",
                    "1.2",
                    "1.3",
                ],
            ),
            enabled_tls_ciphers=dict(type="list", elements="str"),
            disabled_tls_ciphers=dict(type="list", elements="str"),
            network_interfaces=dict(type="list", elements="str"),
        )
    )

    module = AnsibleModule(
        argument_spec,
        required_if=[
            (
                "verify_client_certificate_trust",
                True,
                ["trusted_client_certificate_authority"],
            ),
        ],
        supports_check_mode=True,
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    state = module.params["state"]
    _check_one_name(module)
    if state == "present":
        _check_reference_scope(module)

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg="FlashBlade REST version not supported. "
            "Minimum version required: {0}".format(MIN_REQUIRED_API_VERSION)
        )
    _check_mutual_tls_support(module, api_version)

    policy = _get_policy(module, blade)
    if policy is not None and isinstance(getattr(policy, "name", None), str):
        # The array finds a policy without regard to letter case, but it
        # compares the realm of a certificate, or certificate group, with the
        # realm prefix as it is written in the name of the request. From here
        # on the policy goes by the name the array stores.
        module.params["name"] = policy.name

    if state == "present" and policy is None:
        create_policy(module, blade, api_version)
    elif state == "present" and policy is not None:
        update_policy(module, blade, policy)
    elif state == "absent" and policy is not None:
        delete_policy(module, blade)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
