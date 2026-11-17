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
module: purefb_quota_settings
version_added: '1.30.0'
short_description: Manage FlashBlade user and group quota notification settings
description:
- Manage the array-wide notification settings for the user and group quotas
  created with M(everpure.flashblade.purefb_userquota) and
  M(everpure.flashblade.purefb_groupquota).
- The settings object is a singleton that always exists; the module only
  changes the fields that differ from the requested values.
- Direct notifications are emailed to the users and groups approaching or
  exceeding their quota and need an SMTP relay configured with
  M(everpure.flashblade.purefb_smtp).
- Requires FlashBlade REST API version 2.0 or later (Purity//FB 3.2.0+).
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  direct_notifications:
    description:
    - Whether notifications about space usage and quotas are sent directly
      to the affected users and groups.
    type: bool
  contact:
    description:
    - Contact information included in the notifications sent directly to
      users and groups, such as an email address, a phone number or a name.
    - At most 256 characters; the module refuses a longer value before
      contacting the array.
    - An empty string clears the contact.
    type: str
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Enable direct quota notifications with a contact address
  everpure.flashblade.purefb_quota_settings:
    direct_notifications: true
    contact: storage-admins@example.com
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Change only the contact
  everpure.flashblade.purefb_quota_settings:
    contact: "Storage team, extension 1234"
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Disable direct quota notifications
  everpure.flashblade.purefb_quota_settings:
    direct_notifications: false
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Clear the contact
  everpure.flashblade.purefb_quota_settings:
    contact: ""
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = r"""
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import QuotaSetting
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

MIN_REQUIRED_API_VERSION = "2.0"
# The array rejects a longer contact with
# "Contact parameter must be 256 characters or less."
MAX_CONTACT_LENGTH = 256


def get_settings(module, blade):
    """Return the quota settings singleton."""
    res = blade.get_quotas_settings()
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read quota settings. Error: {0}".format(
                get_error_message(res)
            )
        )
    items = list(res.items)
    if not items:
        module.fail_json(msg="No quota settings object found.")
    return items[0]


def _wanted_changes(module, settings):
    """Return the QuotaSetting fields that differ from the array.

    The array omits contact from the response while it is unset, so an
    absent contact compares as an empty string.
    """
    patch_fields = {}
    wanted_enabled = module.params["direct_notifications"]
    if wanted_enabled is not None:
        current_enabled = bool(getattr(settings, "direct_notifications_enabled", False))
        if wanted_enabled != current_enabled:
            patch_fields["direct_notifications_enabled"] = wanted_enabled
    wanted_contact = module.params["contact"]
    if wanted_contact is not None:
        current_contact = getattr(settings, "contact", None) or ""
        if wanted_contact != current_contact:
            patch_fields["contact"] = wanted_contact
    return patch_fields


def update_settings(module, blade, settings):
    """PATCH only the fields that differ from the current settings."""
    patch_fields = _wanted_changes(module, settings)
    changed = bool(patch_fields)
    if changed and not module.check_mode:
        res = blade.patch_quotas_settings(quota_setting=QuotaSetting(**patch_fields))
        if res.status_code != 200:
            module.fail_json(
                msg="Updating quota settings {0} failed. Error: {1}".format(
                    settings.name, get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            direct_notifications=dict(type="bool"),
            contact=dict(type="str"),
        )
    )

    module = AnsibleModule(
        argument_spec,
        required_one_of=[["direct_notifications", "contact"]],
        supports_check_mode=True,
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    contact = module.params["contact"]
    if contact is not None and len(contact) > MAX_CONTACT_LENGTH:
        module.fail_json(
            msg="contact must be {0} characters or less ({1} given).".format(
                MAX_CONTACT_LENGTH, len(contact)
            )
        )

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg="FlashBlade REST version not supported. "
            "Minimum version required: {0}".format(MIN_REQUIRED_API_VERSION)
        )

    settings = get_settings(module, blade)
    update_settings(module, blade, settings)


if __name__ == "__main__":
    main()
