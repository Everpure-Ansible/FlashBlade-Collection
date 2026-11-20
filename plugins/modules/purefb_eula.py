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
module: purefb_eula
version_added: '1.6.0'
short_description: Sign Everpure FlashBlade EULA
description:
- Sign the FlashBlade EULA for Day 0 config, or change signatory.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  company:
    description:
    - Full legal name of the entity.
    - The value must be between 1 and 64 characters in length.
    type: str
    required: true
  name:
    description:
    - Full legal name of the individual at the company who has the authority to accept the terms of the agreement.
    - The value must be between 1 and 64 characters in length.
    type: str
    required: true
  title:
    description:
    - Individual's job title at the company.
    - The value must be between 1 and 64 characters in length.
    type: str
    required: true
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Sign EULA for FlashBlade
  everpure.flashblade.purefb_eula:
    company: "ACME Storage, Inc."
    name: "Fred Bloggs"
    title: "Storage Manager"
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592
"""

RETURN = r"""
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import Eula, EulaSignature
except ImportError:
    HAS_PYPURECLIENT = False


from ansible.module_utils.basic import AnsibleModule
from ansible_collections.everpure.flashblade.plugins.module_utils.purefb import (
    get_system,
    purefb_argument_spec,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.common import (
    get_error_message,
)


def _get_signature(module, blade):
    """Return the signature of the EULA.

    A read the array refuses or fails is reported with the message of the
    array.
    """
    res = blade.get_arrays_eula()
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read the EULA. Error: {0}".format(get_error_message(res))
        )
    items = list(res.items)
    if not items:
        module.fail_json(msg="The array returned no EULA.")
    return items[0].signature


def set_eula(module, blade):
    """Sign EULA"""
    changed = False
    current_eula = _get_signature(module, blade)
    if not current_eula.accepted:
        if (
            current_eula.company != module.params["company"]
            or current_eula.title != module.params["title"]
            or current_eula.name != module.params["name"]
        ):
            changed = True
            if not module.check_mode:
                signature = EulaSignature(
                    company=module.params["company"],
                    title=module.params["title"],
                    name=module.params["name"],
                )
                eula_body = Eula(signature=signature)
                rc = blade.patch_arrays_eula(eula=eula_body)
                if rc.status_code != 200:
                    module.fail_json(
                        msg="Signing EULA failed. Error: {0}".format(
                            get_error_message(rc)
                        )
                    )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            company=dict(type="str", required=True),
            name=dict(type="str", required=True),
            title=dict(type="str", required=True),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    blade = get_system(module)
    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client SDK required to support this module.")
    blade = get_system(module)
    set_eula(module, blade)
    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
