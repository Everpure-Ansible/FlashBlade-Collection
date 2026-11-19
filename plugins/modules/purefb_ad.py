#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2021, Simon Dodsley (simon@everpuredata.com)
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
module: purefb_ad
version_added: '1.6.0'
short_description: Manage FlashBlade Active Directory Account
description:
- Add or delete FlashBlade Active Directory Account
- FlashBlade allows the creation of one AD computer account, or joining of an
  existing AD computer account.
- An account belongs to a server. An account of the default server
  C(_array_server) has a plain name, an account of any other server is named
  C(server::account), and an account of a server in a realm is named
  C(realm::server::account).
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - Name of the AD account
    - Either the plain account name, with I(server) naming the server when it
      is not the default one, or the full name C(server::account) or
      C(realm::server::account).
    - A realm-scoped administrator must name a server of its realm, in the
      full name or in I(server); a plain name on its own is not placed in,
      or resolved to, the administrator's realm.
    type: str
    required: true
  existing:
    description:
    - Does the account I(name) already exist in the AD environment
    type: bool
    default: false
  state:
    description:
    - Define whether the AD sccount is deleted or not
    - Test state will perform a test against the suppied account name
    - Rotate will force a keytab rotation for the specified account
    - C(test) and C(rotate) fail when the account does not exist
    - With I(ca_certificate) or I(ca_certificate_group), C(test) runs the tests
      using that CA in place of the configured one and leaves the stored
      configuration unchanged
    default: present
    choices: [ absent, present, test, rotate ]
    type: str
  computer:
    description:
    -  The common name of the computer account to be created in the Active Directory domain.
    - If not specified, defaults to the account part of I(name), without the
      server and realm it may carry, with underscores replaced by hyphens.
    type: str
  domain:
    description:
    - The Active Directory domain to join
    - Required to create the account.
    type: str
  username:
    description:
    - A user capable of creating a computer account within the domain
    - Required to create the account.
    type: str
  password:
    description:
    - Password string for I(username)
    - Required to create the account.
    type: str
  encryption:
    description:
    - The encryption types that will be supported for use by clients for Kerberos authentication
    type: list
    elements: str
    choices: [ aes256-sha1, aes128-sha1, aes256-cts-hmac-sha1-96, aes128-cts-hmac-sha1-96, arcfour-hmac ]
    default: aes256-sha1
  join_ou:
    description:
    - Location where the Computer account will be created. e.g. OU=Arrays,OU=Storage.
    - If left empty, defaults to B(CN=Computers).
    type: str
  directory_servers:
    description:
    - A list of directory servers that will be used for lookups related to user authorization
    - Accepted server formats are IP address and DNS name
    - All specified servers must be registered to the domain appropriately in the array
      configured DNS and will only be communicated with over the secure LDAP (LDAPS) protocol.
      If not specified, servers are resolved for the domain in DNS
    - The specified list can have a maximum length of 5. If more are provided only the first
      5 are used.
    type: list
    elements: str
  kerberos_servers:
    description:
    - A list of key distribution servers to use for Kerberos protocol
    - Accepted server formats are IP address and DNS name
    - All specified servers must be registered to the domain appropriately in the array
      configured DNS. If not specified, servers are resolved for the domain in DNS.
    - The specified list can have a maximum length of 5. If more are provided only the first
      5 are used.
    type: list
    elements: str
  service_principals:
    description:
    - A list of SPNs for registering services with the domain.
    - The service must be provided with the FQDN. See examples below.
    - If not specified B(Computer Name.Domain) is used
    type: list
    elements: str
  global_catalog_servers:
    description:
    - A list of global catalog servers that will be used for lookups related to user authorization.
    - Accepted server formats are IP address and DNS name with optional @domain suffix.
      If the suffix is ommited, the joined domain is assumed.
    - All specified servers must be registered to the domain appropriately in the arrays
      configured DNS and will only be communicated with over the secure LDAP (LDAPS) protocol.
    type: list
    elements: str
    version_added: 1.20.0
  service:
    description:
    - Service protocol for Active Directory principals
    - This parameter is now IGNORED.
    - Refer to FlashBlade User Guide for more details
    - Use the I(service_principals) parameter instead to correctly define the service type to be used
      for each principal.
    type: list
    elements: str
    choices: ['nfs', 'cifs', 'HOST', '']
    default: ''
  server:
    description:
    - Name of the local array server into which the AD account is added
    - Do not provide if the AD account is to connect to the default server
    - A server in a realm is named C(realm::server).
    - The module addresses the account as C(server::name). When I(name)
      already is a full name, its server must be the one given here.
    version_added: "1.23.0"
    type: str
  local_only:
    description:
    - Do a local-only delete of an active directory account
    type: bool
    default: false
  ca_certificate:
    description:
    - Name of an existing certificate on the array for the Certificate Authority
      that signed the certificates of the configured directory, global catalog
      and Kerberos servers. The array uses it to validate those servers when it
      connects over LDAPS and Kerberos.
    - Use the M(everpure.flashblade.purefb_certs) module to create certificates.
    - Mutually exclusive with I(ca_certificate_group).
    - When omitted the array's current setting is left unchanged. If neither a
      CA certificate nor a certificate group is configured the array does not
      validate server certificates. The module does not clear a configured CA.
    - Switching from a configured I(ca_certificate_group) to a certificate sends
      only the new reference. Check the result with M(everpure.flashblade.purefb_info)
      and clear the old reference on the array if it is still reported.
    - Requires REST API 2.27 or later (Purity//FB 4.8.3) and a py-pure-client
      release that includes FlashBlade REST 2.27 support.
    type: str
    version_added: '1.30.0'
  ca_certificate_group:
    description:
    - Name of an existing certificate group on the array containing CA
      certificates that can validate the configured directory, global catalog
      and Kerberos servers.
    - Use the M(everpure.flashblade.purefb_certgrp) module to create
      certificate groups.
    - Mutually exclusive with I(ca_certificate).
    - When omitted the array's current setting is left unchanged. The module
      does not clear a configured CA.
    - Switching from a configured I(ca_certificate) to a certificate group sends
      only the new reference. Check the result with M(everpure.flashblade.purefb_info)
      and clear the old reference on the array if it is still reported.
    - Requires REST API 2.27 or later (Purity//FB 4.8.3) and a py-pure-client
      release that includes FlashBlade REST 2.27 support.
    type: str
    version_added: '1.30.0'
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Create new AD account
  everpure.flashblade.purefb_ad:
    name: ad_account
    server: local_server
    computer: FLASHBLADE
    domain: acme.com
    username: Administrator
    password: Password
    join_ou: "CN=FakeOU"
    encryption:
      - aes128-cts-hmac-sha1-96
      - aes256-cts-hmac-sha1-96
    kerberos_servers:
      - kdc.acme.com
    directory_servers:
      - ldap.acme.com
    service_principals:
      - "nfs/vip1.flashblade.acme.com"
      - "HOST/vip2.flashblade.acme.com"
    global_catalog_servers:
      - gc1.flashblade.acme.com
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create new AD account for a server in a realm
  everpure.flashblade.purefb_ad:
    name: realm1::server1::ad_account
    computer: FLASHBLADE-R1
    domain: acme.com
    username: Administrator
    password: Password
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Test the AD account of a server in a realm
  everpure.flashblade.purefb_ad:
    name: ad_account
    server: realm1::server1
    state: test
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Connect to existing AD account
  everpure.flashblade.purefb_ad:
    name: ad_account
    computer: FLASHBLADE
    domain: acme.com
    username: Administrator
    password: Password
    existing: true
    kerberos_servers:
      - kdc.acme.com
    directory_servers:
      - ldap.acme.com
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Update existing AD account
  everpure.flashblade.purefb_ad:
    name: ad_account
    server: local_server
    encryption:
      - aes256-cts-hmac-sha1-96
    kerberos_servers:
      - kdc.acme.com
    directory_servers:
      - ldap.acme.com
    service_principals:
      - "HOST/vip1.flashblade.acme.com"
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete local AD account
  everpure.flashblade.purefb_ad:
    name: ad_account
    local_only: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Fully delete AD account
  everpure.flashblade.purefb_ad:
    name: ad_account
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Test AD account
  everpure.flashblade.purefb_ad:
    name: ad_account
    state: test
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Rotate AD account keytabs
  everpure.flashblade.purefb_ad:
    name: ad_account
    state: rotate
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create new AD account validating the domain controllers with a CA group
  everpure.flashblade.purefb_ad:
    name: ad_account
    computer: FLASHBLADE
    domain: acme.com
    username: Administrator
    password: Password
    ca_certificate_group: domain_ca_group
    kerberos_servers:
      - kdc.acme.com
    directory_servers:
      - ldap.acme.com
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Test an existing AD account against a candidate CA without applying it
  everpure.flashblade.purefb_ad:
    name: ad_account
    state: test
    ca_certificate: new_domain_ca
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Apply the CA certificate to an existing AD account
  everpure.flashblade.purefb_ad:
    name: ad_account
    ca_certificate: new_domain_ca
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = r"""
test_response:
  description:
  - Result of each test the array ran against the servers of the account.
  - With I(ca_certificate) or I(ca_certificate_group) the tests used that CA
    in place of the configured one.
  returned: when C(state=test)
  type: list
  elements: dict
  contains:
    component_name:
      description: Name of the array component that ran the test.
      type: str
      sample: CH1.FM1
    description:
      description: What the test checked.
      type: str
      sample: Validating connectivity to the directory server
    destination:
      description: URI of the server the test connected to.
      type: str
      sample: ldaps://ldap.acme.com:636
    enabled:
      description: Whether the tested service is enabled, as C(true) or C(false).
      type: str
      sample: "true"
    success:
      description: Whether the test passed, as C(true) or C(false).
      type: str
      sample: "true"
    test_type:
      description: Type of test the array ran.
      type: str
      sample: connectivity
    resource_name:
      description: Name of the Active Directory account that was tested.
      type: str
      sample: ad_account
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        ActiveDirectoryPost,
        ActiveDirectoryPatch,
        Reference,
        KeytabPost,
    )
except ImportError:
    HAS_PYPURECLIENT = False

# ActiveDirectoryTestPatch entered py-pure-client with the FlashBlade REST
# 2.27 models, so when it is present ActiveDirectoryPost and
# ActiveDirectoryPatch also carry the CA reference fields. Older releases
# (py-pure-client 1.88.0, the collection's floor, stops at REST 2.26) lack
# it and their models would silently drop the references, so the CA options
# are refused when this import fails while the rest of the module keeps
# working.
HAS_AD_TEST_PATCH = True
try:
    from pypureclient.flashblade import ActiveDirectoryTestPatch
except ImportError:
    HAS_AD_TEST_PATCH = False

from ansible.module_utils.basic import AnsibleModule
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

GC_SERVERS_API_VERSION = "2.12"
SERVERS_API_VERSION = "2.16"
CA_CERT_API_VERSION = "2.27"

# Module option -> Active Directory field. Both name a certificate object that
# must already exist on the array, so the module sends Reference(name=...)
# and compares against the name held by the current configuration.
REFERENCE_PARAMS = {
    "ca_certificate": "ca_certificate",
    "ca_certificate_group": "ca_certificate_group",
}

# An account of this server has a plain name; an account of any other server
# is named server::account, or realm::server::account for a server in a realm.
DEFAULT_SERVER = "_array_server"
JOIN_PARAMS = ("domain", "username", "password")


def _server_of(name):
    """Server an account name places the account on, or "" for the default."""
    return name.rpartition("::")[0]


def _leaf(name):
    """Account part of an account name, without its server and realm."""
    return name.rpartition("::")[2]


def _account_name(module, api_version):
    """Full name of the account the task addresses.

    The server option goes in front of a plain name with the :: separator.
    A name that already carries a server has to agree with the option, and
    the default server adds nothing. Names are compared without regard to
    case, as the array does. Servers need REST 2.16; before that the option
    is not used. A name without an account part is refused: behind a server
    it would read as an account that does not exist and go on to a join.
    """
    name = module.params["name"]
    server = module.params["server"]
    if not _leaf(name).strip():
        module.fail_json(
            msg=(
                "name '{0}' holds no account name. Use account, "
                "server::account or realm::server::account."
            ).format(name)
        )
    if not server or LooseVersion(SERVERS_API_VERSION) > LooseVersion(api_version):
        return name
    named_server = _server_of(name)
    if named_server:
        if named_server.lower() != server.lower():
            module.fail_json(
                msg=(
                    "Active Directory Account {0} is named for server {1}, "
                    "but server is {2}. Give the server once, or the same "
                    "server in both."
                ).format(name, named_server, server)
            )
        return name
    if server.lower() == DEFAULT_SERVER:
        return name
    return "{0}::{1}".format(server, name)


def _get_account(module, blade, name):
    """Return the account called name, or None when it does not exist.

    Only the array's "does not exist" answer reads as absent. Any other
    failed read fails the task, so that a refused or failed lookup is never
    followed by an attempt to join the domain again.
    """
    res = blade.get_active_directory(names=[name])
    if res.status_code == 200:
        items = list(res.items)
        return items[0] if items else None
    error = get_error_message(res)
    if "does not exist" in str(error).lower():
        return None
    module.fail_json(
        msg="Failed to read Active Directory Account {0}. Error: {1}".format(
            name, error
        )
    )


def _check_server(module, blade):
    """Fail unless the server a new account is to belong to exists.

    The server is the one the full name carries, or the default server when
    the task names it in the server option. A plain name on its own is not
    checked.
    """
    server = _server_of(module.params["name"]) or module.params["server"]
    if not server:
        return
    res = blade.get_servers(names=[server])
    if res.status_code == 200:
        return
    error = get_error_message(res)
    if "does not exist" in str(error).lower():
        module.fail_json(
            msg="Server {0} does not exist on this FlashBlade.".format(server)
        )
    module.fail_json(msg="Failed to read server {0}. Error: {1}".format(server, error))


def _check_join_params(module):
    """Fail when an account is to be created without what a join needs."""
    missing = [param for param in JOIN_PARAMS if not module.params[param]]
    if missing:
        module.fail_json(
            msg=(
                "Active Directory Account {0} does not exist. Creating it "
                "requires {1}."
            ).format(module.params["name"], ", ".join(missing))
        )


def _reference_name(obj, field):
    """Name held by a reference field on an AD configuration, or None."""
    return getattr(getattr(obj, field, None), "name", None)


def _check_certificate(module, blade, param):
    """Fail unless the named certificate or certificate group exists."""
    name = module.params[param]
    if not name:
        return
    if param == "ca_certificate_group":
        res = blade.get_certificate_groups(names=[name])
        kind = "Certificate group"
    else:
        res = blade.get_certificates(names=[name])
        kind = "Certificate"
    if res.status_code != 200:
        module.fail_json(
            msg="{0} {1} does not exist. Error: {2}".format(
                kind, name, get_error_message(res)
            )
        )


def _ca_reference_kwargs(module):
    """Reference kwargs for the CA option that was given, if any."""
    kwargs = {}
    for param, field in REFERENCE_PARAMS.items():
        if module.params[param]:
            kwargs[field] = Reference(name=module.params[param])
    return kwargs


def delete_account(module, blade):
    """Delete Active directory Account"""
    changed = True
    if not module.check_mode:
        res = blade.delete_active_directory(
            names=[module.params["name"]], local_only=module.params["local_only"]
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete AD Account {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def create_account(module, blade):
    """Create Active Directory Account"""
    changed = True
    api_version = get_rest_api_version(blade)
    # CA references need REST 2.27; main() has already rejected them on
    # older arrays, so they only ever reach the >= 2.12 constructors below.
    ca_kwargs = _ca_reference_kwargs(module)
    if not module.params["existing"]:
        if LooseVersion(GC_SERVERS_API_VERSION) <= LooseVersion(api_version):
            ad_config = ActiveDirectoryPost(
                computer_name=module.params["computer"],
                directory_servers=module.params["directory_servers"],
                kerberos_servers=module.params["kerberos_servers"],
                domain=module.params["domain"],
                encryption_types=module.params["encryption"],
                service_principal_names=module.params["service_principals"],
                join_ou=module.params["join_ou"],
                user=module.params["username"],
                password=module.params["password"],
                global_catalog_servers=module.params["global_catalog_servers"],
                **ca_kwargs
            )
        else:
            ad_config = ActiveDirectoryPost(
                computer_name=module.params["computer"],
                directory_servers=module.params["directory_servers"],
                kerberos_servers=module.params["kerberos_servers"],
                domain=module.params["domain"],
                encryption_types=module.params["encryption"],
                service_principal_names=module.params["service_principals"],
                join_ou=module.params["join_ou"],
                user=module.params["username"],
                password=module.params["password"],
            )
        if not module.check_mode:
            res = blade.post_active_directory(
                names=[module.params["name"]], active_directory=ad_config
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to add Active Directory Account {0}. Error: {1}".format(
                        module.params["name"], get_error_message(res)
                    )
                )
    else:
        if LooseVersion(GC_SERVERS_API_VERSION) <= LooseVersion(api_version):
            ad_config = ActiveDirectoryPost(
                computer_name=module.params["computer"],
                directory_servers=module.params["directory_servers"],
                kerberos_servers=module.params["kerberos_servers"],
                domain=module.params["domain"],
                encryption_types=module.params["encryption"],
                user=module.params["username"],
                password=module.params["password"],
                global_catalog_servers=module.params["global_catalog_servers"],
                **ca_kwargs
            )
        else:
            ad_config = ActiveDirectoryPost(
                computer_name=module.params["computer"],
                directory_servers=module.params["directory_servers"],
                kerberos_servers=module.params["kerberos_servers"],
                domain=module.params["domain"],
                encryption_types=module.params["encryption"],
                user=module.params["username"],
                password=module.params["password"],
            )
        if not module.check_mode:
            res = blade.post_active_directory(
                names=[module.params["name"]],
                active_directory=ad_config,
                join_existing_account=True,
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to add Active Directory Account {0}. Error: {1}".format(
                        module.params["name"], get_error_message(res)
                    )
                )
    module.exit_json(changed=changed)


def update_account(module, blade, current_ad):
    """Update Active Directory Account

    current_ad is the account as main() read it under its full name.
    """
    api_version = get_rest_api_version(blade)
    changed = False
    mod_ad = False
    attr = {}
    # join_ou is only compared when it was given: the array reports its
    # own default (e.g. CN=Computers) which an omitted option must not undo.
    join_ou_changed = (
        module.params["join_ou"] is not None
        and module.params["join_ou"] != current_ad.join_ou
    )
    encryption_changed = sorted(module.params["encryption"]) != sorted(
        current_ad.encryption_types or []
    )
    if join_ou_changed and encryption_changed:
        module.fail_json(msg="Cannot make changes to OU when changing encryption types")
    if module.params["directory_servers"]:
        if current_ad.directory_servers:
            if sorted(module.params["directory_servers"]) != sorted(
                current_ad.directory_servers
            ):
                attr["directory_servers"] = module.params["directory_servers"]
                mod_ad = True
    if module.params["kerberos_servers"]:
        if current_ad.kerberos_servers:
            if sorted(module.params["kerberos_servers"]) != sorted(
                current_ad.kerberos_servers
            ):
                attr["kerberos_servers"] = module.params["kerberos_servers"]
                mod_ad = True
    if join_ou_changed:
        attr["join_ou"] = module.params["join_ou"]
        mod_ad = True
    if encryption_changed:
        attr["encryption_types"] = module.params["encryption"]
        mod_ad = True
    if module.params["service"] and module.params["service"] != [""]:
        module.fail_json(
            msg="Please incorporate the service parameter into the "
            "service_principals parameter for better security control."
        )
    if module.params["service_principals"]:
        if current_ad.service_principal_names:
            if sorted(module.params["service_principals"]) != sorted(
                current_ad.service_principal_names
            ):
                attr["service_principal_names"] = module.params["service_principals"]
                mod_ad = True
    if LooseVersion(GC_SERVERS_API_VERSION) <= LooseVersion(api_version):
        if module.params["global_catalog_servers"]:
            if current_ad.global_catalog_servers:
                if sorted(current_ad.global_catalog_servers) != sorted(
                    module.params["global_catalog_servers"]
                ):
                    attr["global_catalog_servers"] = module.params[
                        "global_catalog_servers"
                    ]
                    mod_ad = True
    # CA references: main() has already gated them on REST 2.27 and checked
    # that the named object exists. Only the given option is sent; an
    # omitted option never clears what the array holds.
    for param, field in REFERENCE_PARAMS.items():
        wanted = module.params[param]
        if wanted and wanted != _reference_name(current_ad, field):
            attr[field] = Reference(name=wanted)
            mod_ad = True
    if mod_ad:
        changed = True
        if not module.check_mode:
            ad_attr = ActiveDirectoryPatch(**attr)
            res = blade.patch_active_directory(
                names=[module.params["name"]], active_directory=ad_attr
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to update Active Directory Account {0}. Error: {1}".format(
                        module.params["name"], get_error_message(res)
                    )
                )
    module.exit_json(changed=changed)


def test_account(module, blade):
    """Test AD account configuration

    With a CA certificate or certificate group the array runs the tests
    using that reference in place of the configured one (PATCH
    /active-directory/test); the stored configuration is never changed.
    """
    test_response = []
    ca_kwargs = _ca_reference_kwargs(module)
    if ca_kwargs:
        res = blade.patch_active_directory_test(
            names=[module.params["name"]],
            active_directory=ActiveDirectoryTestPatch(**ca_kwargs),
        )
    else:
        res = blade.get_active_directory_test(names=[module.params["name"]])
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to test Active Directory Account {0}. Error: {1}".format(
                module.params["name"], get_error_message(res)
            )
        )
    response = list(res.items)
    for component in response:
        if component.enabled:
            enabled = "true"
        else:
            enabled = "false"
        if component.success:
            success = "true"
        else:
            success = "false"
        test_response.append(
            {
                "component_name": component.component_name,
                "description": component.description,
                "destination": component.destination,
                "enabled": enabled,
                "success": success,
                "test_type": component.test_type,
                "resource_name": component.resource.name,
            }
        )
    module.exit_json(changed=False, test_response=test_response)


def rotate_account(module, blade):
    """Rotate AD account keytabs"""
    account = Reference(name=module.params["name"], resource_type="active-directory")
    keytab = KeytabPost(source=account)
    if not module.check_mode:
        res = blade.post_keytabs(keytab=keytab)
        if res.status_code != 200:
            module.fail_json(
                msg="Keytab rotation failed for account {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=True)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(
                type="str",
                default="present",
                choices=["absent", "present", "test", "rotate"],
            ),
            username=dict(type="str"),
            password=dict(type="str", no_log=True),
            name=dict(type="str", required=True),
            computer=dict(type="str"),
            service=dict(
                type="list",
                elements="str",
                default="",
                choices=["nfs", "cifs", "HOST", ""],
            ),
            existing=dict(type="bool", default=False),
            local_only=dict(type="bool", default=False),
            domain=dict(type="str"),
            join_ou=dict(type="str"),
            server=dict(type="str"),
            directory_servers=dict(type="list", elements="str"),
            kerberos_servers=dict(type="list", elements="str"),
            service_principals=dict(type="list", elements="str"),
            global_catalog_servers=dict(type="list", elements="str"),
            ca_certificate=dict(type="str"),
            ca_certificate_group=dict(type="str"),
            encryption=dict(
                type="list",
                elements="str",
                choices=[
                    "aes256-sha1",
                    "aes128-sha1",
                    "aes256-cts-hmac-sha1-96",
                    "aes128-cts-hmac-sha1-96",
                    "arcfour-hmac",
                ],
                default=["aes256-sha1"],
            ),
        )
    )

    module = AnsibleModule(
        argument_spec,
        supports_check_mode=True,
        mutually_exclusive=[["ca_certificate", "ca_certificate_group"]],
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")
    # The CA options need the REST 2.27 models; an older SDK would drop the
    # references silently, so refuse them before the array is contacted.
    ca_params = [param for param in REFERENCE_PARAMS if module.params[param]]
    if ca_params and not HAS_AD_TEST_PATCH:
        module.fail_json(
            msg=(
                "{0} requires a py-pure-client release with FlashBlade REST "
                "{1} support (ActiveDirectoryTestPatch is missing from the "
                "installed SDK)"
            ).format(", ".join(ca_params), CA_CERT_API_VERSION)
        )

    blade = get_system(module)
    module.params["encryption"] = [
        crypt.replace("aes256-sha1", "aes256-cts-hmac-sha1-96").replace(
            "aes128-sha1", "aes128-cts-hmac-sha1-96"
        )
        for crypt in module.params["encryption"]
    ]
    state = module.params["state"]
    api_version = get_rest_api_version(blade)
    # The full name is settled before the first read, so that the lookup and
    # every later request address the same account.
    module.params["name"] = _account_name(module, api_version)
    if not module.params["computer"]:
        module.params["computer"] = _leaf(module.params["name"]).replace("_", "-")
    current_ad = _get_account(module, blade, module.params["name"])
    if current_ad is None and state in ("test", "rotate"):
        module.fail_json(
            msg="Active Directory Account {0} does not exist.".format(
                module.params["name"]
            )
        )
    if module.params["kerberos_servers"]:
        module.params["kerberos_servers"] = module.params["kerberos_servers"][0:5]
    if module.params["directory_servers"]:
        module.params["directory_servers"] = module.params["directory_servers"][0:5]

    # CA references: gate on the array's REST 2.27 and confirm the named
    # object exists before any POST, PATCH or test is issued.
    if ca_params and LooseVersion(CA_CERT_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg=(
                "{0} requires FlashBlade REST version {1} or later "
                "(Purity//FB 4.8.3+)"
            ).format(", ".join(ca_params), CA_CERT_API_VERSION)
        )
    if state in ("present", "test"):
        for param in ca_params:
            _check_certificate(module, blade, param)

    if state == "present" and current_ad is None:
        # Refusals the module can foresee are settled before the check-mode
        # branch, so a check-mode run does not predict a join that fails.
        if LooseVersion(SERVERS_API_VERSION) <= LooseVersion(api_version):
            _check_server(module, blade)
        _check_join_params(module)
        create_account(module, blade)
    elif state == "present":
        update_account(module, blade, current_ad)
    elif state == "test":
        test_account(module, blade)
    elif state == "rotate":
        rotate_account(module, blade)
    elif current_ad is not None:
        delete_account(module, blade)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
