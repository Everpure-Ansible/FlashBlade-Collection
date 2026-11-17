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
module: purefb_public_key
version_added: '1.30.0'
short_description: Manage FlashBlade public keys
description:
- Create or delete named public keys on a FlashBlade.
- A public key is an immutable copy of an SSH or PEM public key that an
  SSH certificate authority policy can use as its signing authority.
- Requires FlashBlade REST API version 2.14 or later (Purity//FB 4.4.2+).
- The array does not allow the key material of an existing public key to
  be changed. To replace it, delete the key and create it again.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - Name of the public key.
    type: str
    required: true
  state:
    description:
    - Whether the public key should exist.
    type: str
    default: present
    choices: [ absent, present ]
  public_key:
    description:
    - Text of the public key in OpenSSH format (C(ssh-ed25519 AAAA...))
      or PEM format (C(-----BEGIN PUBLIC KEY-----)).
    - Required when the key does not exist yet.
    - On an existing key the supplied text is compared with the key on the
      array by its key material, so the format, an OpenSSH comment and
      surrounding whitespace do not count. The module fails when the
      material differs because public keys cannot be modified.
    - Comparing a key supplied in one format with a key the array stores
      in the other (OpenSSH against PEM) needs the Python C(cryptography)
      package on the host that runs the module. Without it only an
      OpenSSH comment and surrounding whitespace are ignored, so the same
      key supplied in the other format is reported as different material.
    - Supported algorithms are RSA, RSASSA-PSS, ED25519 and ECDSA
      (P-256, P-384 and P-521).
    type: str
  force:
    description:
    - Allow deletion of a public key that an SSH certificate authority
      policy still uses.
    - Deleting such a key removes it from the policy and inactivates every
      user that authenticates through it, so without this option the
      module refuses and lists the policies.
    type: bool
    default: false
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Create a public key from an OpenSSH public key file
  everpure.flashblade.purefb_public_key:
    name: ca-signer
    public_key: "{{ lookup('file', 'ca.pub') }}"
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create a public key from PEM text
  everpure.flashblade.purefb_public_key:
    name: ca-signer
    public_key: |
      -----BEGIN PUBLIC KEY-----
      MCowBQYDK2VwAyEAyeH1fPvK/DJCmR/OqJ5S0F16ZQZKY6jF236zQ6er+ww=
      -----END PUBLIC KEY-----
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete a public key that no policy uses
  everpure.flashblade.purefb_public_key:
    name: ca-signer
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete a public key although an SSH certificate authority policy uses it
  everpure.flashblade.purefb_public_key:
    name: ca-signer
    state: absent
    force: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = r"""
public_key:
  description: The public key as the array reports it.
  returned: when C(state=present), except for a key created in check mode
  type: dict
  contains:
    name:
      description: Name of the public key.
      type: str
      sample: ca-signer
    algorithm:
      description:
      - Cryptographic algorithm of the key as reported by the array, such as
        C(rsa), C(rsassa-pss), C(ec) or C(ed25519).
      type: str
      sample: ed25519
    key_size:
      description: Size of the key in bits.
      type: int
      sample: 256
    uses:
      description: Objects that use this public key.
      type: list
      elements: dict
      contains:
        name:
          description: Name of the object.
          type: str
          sample: ca-policy
        resource_type:
          description: REST resource type of the object.
          type: str
          sample: ssh-certificate-authority-policies
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import PublicKeyPost
except ImportError:
    HAS_PYPURECLIENT = False

HAS_CRYPTOGRAPHY = True
try:
    from cryptography.exceptions import UnsupportedAlgorithm
    from cryptography.hazmat.primitives import serialization
except ImportError:
    HAS_CRYPTOGRAPHY = False

import re
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

MIN_REQUIRED_API_VERSION = "2.14"

# "<type> <base64 body> [comment]" - one OpenSSH public key line
OPENSSH_KEY_LINE = re.compile(r"^(\S+)\s+([A-Za-z0-9+/=]+)(?:\s+.*)?$")


def _key_material(text):
    """Return a canonical form of a public key for comparison.

    With ``cryptography`` available the text is parsed as an OpenSSH or a
    PEM public key and its DER-encoded SubjectPublicKeyInfo is returned, so
    the same key compares equal whatever format either side uses. Without
    it an OpenSSH line is reduced to its type and base64 body (the comment
    does not count) and any other text is compared stripped.
    """
    text = (text or "").strip()
    if HAS_CRYPTOGRAPHY:
        data = text.encode("utf-8")
        for loader in (
            serialization.load_ssh_public_key,
            serialization.load_pem_public_key,
        ):
            try:
                key = loader(data)
            except (ValueError, TypeError, UnsupportedAlgorithm):
                continue
            return key.public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
    match = OPENSSH_KEY_LINE.match(text)
    if match:
        return match.group(1) + " " + match.group(2)
    return text


def _first_item(response):
    """Return the first item of a response, or None"""
    items = list(response.items)
    if items:
        return items[0]
    return None


def get_key(module, blade):
    """Return the public key object, or None when the array has none by that name.

    The array answers a GET for an unknown name with a 400 (``Public key
    does not exist.``) rather than an empty list, so a 400 means absent and
    any other failure is reported.
    """
    res = blade.get_public_keys(names=[module.params["name"]])
    if res.status_code == 200:
        return _first_item(res)
    if res.status_code != 400:
        module.fail_json(
            msg="Failed to read public key {0}. Error: {1}".format(
                module.params["name"], get_error_message(res)
            )
        )
    return None


def get_uses(module, blade):
    """Return the objects using the key as a list of name/resource_type dicts"""
    res = blade.get_public_keys_uses(names=[module.params["name"]])
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read the uses of public key {0}. Error: {1}".format(
                module.params["name"], get_error_message(res)
            )
        )
    uses = []
    for item in list(res.items):
        ref = getattr(item, "use", None)
        uses.append(
            {
                "name": getattr(ref, "name", None),
                "resource_type": getattr(ref, "resource_type", None),
            }
        )
    return uses


def key_facts(key, uses):
    """Return the public_key return value for a key object"""
    return {
        "name": getattr(key, "name", None),
        "algorithm": getattr(key, "algorithm", None),
        "key_size": getattr(key, "key_size", None),
        "uses": uses,
    }


def create_key(module, blade):
    """Create the public key"""
    text = (module.params["public_key"] or "").strip()
    if not text:
        module.fail_json(
            msg="public_key is required to create public key {0}".format(
                module.params["name"]
            )
        )
    if not module.check_mode:
        res = blade.post_public_keys(
            names=[module.params["name"]],
            public_key=PublicKeyPost(public_key=text),
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to create public key {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
        key = _first_item(res)
        if key is None:
            key = get_key(module, blade)
        module.exit_json(changed=True, public_key=key_facts(key, []))
    module.exit_json(changed=True)


def check_key(module, blade, key):
    """Report an existing key, failing when different key material is requested"""
    requested = module.params["public_key"]
    if requested is not None and requested.strip():
        if _key_material(requested) != _key_material(getattr(key, "public_key", None)):
            module.fail_json(
                msg=(
                    "Public key {0} exists with different key material. Public "
                    "keys cannot be modified; delete the key (state: absent) and "
                    "create it again."
                ).format(module.params["name"])
            )
    module.exit_json(changed=False, public_key=key_facts(key, get_uses(module, blade)))


def delete_key(module, blade):
    """Delete the public key unless a policy still uses it"""
    uses = get_uses(module, blade)
    if uses and not module.params["force"]:
        module.fail_json(
            msg=(
                "Public key {0} is used by {1}. Deleting it removes the key from "
                "those policies and inactivates the users that authenticate "
                "through them. Set force: true to delete it anyway."
            ).format(
                module.params["name"],
                ", ".join(
                    "{0} ({1})".format(use["name"], use["resource_type"])
                    for use in uses
                ),
            )
        )
    if not module.check_mode:
        res = blade.delete_public_keys(names=[module.params["name"]])
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete public key {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=True)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str", required=True),
            state=dict(type="str", default="present", choices=["absent", "present"]),
            public_key=dict(type="str", no_log=True),
            force=dict(type="bool", default=False),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg=(
                "FlashBlade REST version not supported. "
                "Minimum version required: {0} (Purity//FB 4.4.2+)"
            ).format(MIN_REQUIRED_API_VERSION)
        )

    key = get_key(module, blade)
    state = module.params["state"]

    if state == "absent" and key:
        delete_key(module, blade)
    elif state == "absent":
        module.exit_json(changed=False)
    elif key:
        check_key(module, blade, key)
    else:
        create_key(module, blade)


if __name__ == "__main__":
    main()
