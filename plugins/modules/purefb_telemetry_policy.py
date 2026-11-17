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
module: purefb_telemetry_policy
version_added: '1.30.0'
short_description: Manage FlashBlade telemetry metrics policies
description:
- Create, update, rename or delete FlashBlade telemetry metrics policies
  and their rules.
- A telemetry metrics policy exports one or more metrics collections, each
  at a chosen resolution, to one or more telemetry targets.
- Requires FlashBlade REST API version 2.29 or later (Purity//FB 4.8.6+).
- Each metrics collection may appear once per policy. Resolutions are
  validated against the collection's supported resolutions before anything
  is sent to the array. Use the C(telemetry) subset of
  M(everpure.flashblade.purefb_info) to list the collections, their default
  and supported resolutions, and the configured targets.
- Telemetry metrics policies are always enabled on the array; the module
  reports the state in its return value but cannot change it.
- A policy whose name matches a metrics collection without its leading
  underscore (for example C(fs_perf_metrics)) is treated as one of the
  policies shipped with Purity//FB and requires I(force=true) to be
  modified or deleted. The system-managed C(_internal_pure1_policy) is
  never modified or deleted.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - Name of the telemetry metrics policy.
    type: str
    required: true
  state:
    description:
    - Whether the policy should exist or not.
    - I(state=absent) detaches the policy from its member arrays and
      deletes it together with its rules.
    type: str
    default: present
    choices: [ absent, present ]
  targets:
    description:
    - Names of the telemetry targets the policy exports to.
    - Required when creating a policy. On an existing policy the list
      replaces the current targets.
    - At least one target is required; an empty list is rejected.
    type: list
    elements: str
  rules:
    description:
    - Rules of the policy, one per metrics collection.
    - On an existing policy the rules are reconciled with this list - rules
      for new collections are added, rules for collections no longer listed
      are removed and a changed resolution is updated in place.
    - Omit to leave the current rules untouched. An empty list removes
      every rule.
    type: list
    elements: dict
    suboptions:
      collection:
        description:
        - Name of the metrics collection, with or without its leading
          underscore (C(_device_perf_metrics) and C(device_perf_metrics)
          are equivalent).
        type: str
        required: true
      resolution:
        description:
        - Export resolution, either in milliseconds or as a number with a
          C(ms), C(s), C(m), C(h) or C(d) suffix, for example C(30s),
          C(5m) or C(1h).
        - Must be one of the collection's supported resolutions.
        - Defaults to the collection's default resolution.
        type: raw
  arrays:
    description:
    - Names of the arrays the policy is attached to when it is created.
    - Defaults to the local array, or to the I(context) array when
      I(context) is set.
    - Attachment can only be set at creation. When this list differs from
      the current membership of an existing policy a warning is issued and
      the membership is left unchanged.
    type: list
    elements: str
  rename:
    description:
    - New name for the policy.
    - Rule names follow the policy name.
    type: str
  force:
    description:
    - Set to C(true) to modify or delete a policy whose name matches one
      of the telemetry policies shipped with Purity//FB.
    type: bool
    default: false
  context:
    description:
    - Name of fleet member on which to perform the operation.
    - This requires the array receiving the request is a member of a fleet
      and the context name to be a member of the same fleet.
    type: str
    default: ""
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Create a policy exporting two collections to a Prometheus target
  everpure.flashblade.purefb_telemetry_policy:
    name: prod-metrics
    targets:
      - prometheus
    rules:
      - collection: device_perf_metrics
        resolution: 30s
      - collection: fs_space_metrics
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Change the resolution of one rule and drop the other
  everpure.flashblade.purefb_telemetry_policy:
    name: prod-metrics
    rules:
      - collection: device_perf_metrics
        resolution: 5m
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Export to a second target as well
  everpure.flashblade.purefb_telemetry_policy:
    name: prod-metrics
    targets:
      - prometheus
      - datadog
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Point a shipped policy at your own target
  everpure.flashblade.purefb_telemetry_policy:
    name: fs_perf_metrics
    targets:
      - prometheus
    force: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Rename a policy
  everpure.flashblade.purefb_telemetry_policy:
    name: prod-metrics
    rename: production-metrics
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete a policy
  everpure.flashblade.purefb_telemetry_policy:
    name: production-metrics
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = r"""
policy:
  description: The telemetry metrics policy after the task has run.
  returned: when the policy exists and the task did not run in check mode
  type: dict
  contains:
    name:
      description: Name of the policy.
      type: str
      sample: prod-metrics
    enabled:
      description: Whether the policy is enabled.
      type: bool
      sample: true
    targets:
      description: Names of the telemetry targets the policy exports to.
      type: list
      elements: str
      sample: ["prometheus"]
    rules:
      description: Rules of the policy.
      type: list
      elements: dict
      contains:
        collection:
          description: Name of the metrics collection.
          type: str
          sample: _device_perf_metrics
        resolution:
          description: Export resolution in milliseconds.
          type: int
          sample: 30000
    arrays:
      description: Names of the arrays the policy is attached to.
      type: list
      elements: str
      sample: ["flashblade1"]
    version:
      description: Version hash of the policy, used for concurrency control.
      type: str
      sample: 00000000-7d19-7685-0000-000aa85b8f52
"""

import re

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        Reference,
        TelemetryMetricsPolicyPatch,
        TelemetryMetricsPolicyPost,
        TelemetryMetricsPolicyRule,
        TelemetryMetricsPolicyRulePatch,
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

MIN_REQUIRED_API_VERSION = "2.29"
# System-managed policy that feeds Pure1; it can never be changed or deleted.
PURE1_POLICY = "_internal_pure1_policy"
_UNITS = {"ms": 1, "s": 1000, "m": 60000, "h": 3600000, "d": 86400000}
_RESOLUTION_RE = re.compile(r"^(\d+)\s*(ms|s|m|h|d)?$")


def _context_kwargs(module):
    """Return context_names kwargs when a context is set.

    Telemetry policies require REST 2.29, well above the 2.17 fleet-context
    floor, so the array always accepts context_names here.
    """
    if module.params["context"]:
        return {"context_names": [module.params["context"]]}
    return {}


def _resolution_to_ms(value):
    """Convert a resolution given in ms or with a unit suffix to milliseconds."""
    if isinstance(value, bool):
        raise ValueError("Invalid resolution {0!r}".format(value))
    if isinstance(value, int):
        return value
    match = _RESOLUTION_RE.match(str(value).strip().lower())
    if not match:
        raise ValueError(
            "Invalid resolution {0!r}: use milliseconds or a number with a "
            "ms, s, m, h or d suffix".format(value)
        )
    return int(match.group(1)) * _UNITS[match.group(2) or "ms"]


def _ms_to_human(ms):
    """Render a millisecond resolution with its shortest exact unit."""
    for unit, factor in (("d", 86400000), ("h", 3600000), ("m", 60000), ("s", 1000)):
        if ms and ms % factor == 0:
            return "{0} ({1}{2})".format(ms, ms // factor, unit)
    return str(ms)


def _get_collections(module, blade):
    """Return the metrics collections keyed by their REST name."""
    res = blade.get_telemetry_metrics_collections(**_context_kwargs(module))
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to list telemetry metrics collections. Error: {0}".format(
                get_error_message(res)
            )
        )
    return dict((item.name, item) for item in res.items)


def _normalise_collection(name, collections):
    """Map a collection name, with or without the leading '_', to its REST name."""
    if name in collections:
        return name
    prefixed = "_" + name
    if prefixed in collections:
        return prefixed
    return None


def _desired_rules(module, collections):
    """Validate the rules parameter and return {collection: resolution_ms}."""
    desired = {}
    for rule in module.params["rules"] or []:
        collection = _normalise_collection(rule["collection"], collections)
        if collection is None:
            module.fail_json(
                msg="Unknown telemetry metrics collection {0}. Valid collections: {1}".format(
                    rule["collection"], ", ".join(sorted(collections))
                )
            )
        if collection in desired:
            module.fail_json(
                msg=(
                    "Collection {0} is listed more than once; each collection "
                    "may appear once per policy."
                ).format(collection)
            )
        item = collections[collection]
        if rule.get("resolution") is None:
            resolution = getattr(item, "default_resolution", None)
            if resolution is None:
                module.fail_json(
                    msg="Collection {0} has no default resolution; specify one.".format(
                        collection
                    )
                )
        else:
            try:
                resolution = _resolution_to_ms(rule["resolution"])
            except ValueError as err:
                module.fail_json(msg=str(err))
        supported = list(getattr(item, "supported_resolutions", None) or [])
        if supported and resolution not in supported:
            module.fail_json(
                msg=(
                    "Resolution {0} is not supported by collection {1}. "
                    "Supported resolutions: {2}"
                ).format(
                    _ms_to_human(resolution),
                    collection,
                    ", ".join(_ms_to_human(res) for res in supported),
                )
            )
        desired[collection] = resolution
    return desired


def _get_policy(module, blade, name):
    res = blade.get_telemetry_metrics_policies(names=[name], **_context_kwargs(module))
    if res.status_code == 200:
        items = list(res.items)
        if items:
            return items[0]
    return None


def _get_members(module, blade, name):
    """Return the names of the arrays the policy is attached to."""
    res = blade.get_telemetry_metrics_policies_arrays(
        policy_names=[name], **_context_kwargs(module)
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to list arrays for telemetry metrics policy {0}. Error: {1}".format(
                name, get_error_message(res)
            )
        )
    members = []
    for item in res.items:
        member = getattr(getattr(item, "member", None), "name", None)
        if member:
            members.append(member)
    return members


def _policy_to_dict(policy, members):
    if policy is None:
        return None
    return {
        "name": getattr(policy, "name", None),
        "enabled": getattr(policy, "enabled", None),
        "targets": [
            getattr(target, "name", None)
            for target in getattr(policy, "targets", None) or []
        ],
        "rules": [
            {
                "collection": getattr(getattr(rule, "collection", None), "name", None),
                "resolution": getattr(rule, "resolution", None),
            }
            for rule in getattr(policy, "rules", None) or []
        ],
        "arrays": members,
        "version": getattr(policy, "version", None),
    }


def _builtin_names(collections):
    """Names reserved for shipped policies: each collection without its leading "_"."""
    return set(name[1:] if name.startswith("_") else name for name in collections)


def _check_protected(module, name, collections):
    """Refuse to touch the Pure1 policy, and shipped policies without force."""
    if name == PURE1_POLICY:
        module.fail_json(
            msg="Telemetry metrics policy {0} is system-managed and cannot be "
            "modified or deleted.".format(name)
        )
    if name in _builtin_names(collections) and not module.params["force"]:
        module.fail_json(
            msg=(
                "Telemetry metrics policy {0} matches a policy shipped with "
                "Purity//FB. Set force: true to modify or delete it."
            ).format(name)
        )


def _rule_index(rule):
    """Position of a rule within its policy, 0 when the array did not report one."""
    return getattr(rule, "index", None) or 0


def _rule_selector(rule):
    """Query parameters addressing one existing rule.

    Rules are named <policy>.<index> and the array renumbers the survivors
    after every delete, so a name read before a delete may address another
    rule afterwards. The id never changes and is used whenever present.
    """
    rule_id = getattr(rule, "id", None)
    if rule_id:
        return {"ids": [rule_id]}
    return {"names": [getattr(rule, "name", None)]}


def _rule_changes(policy, desired):
    """Diff the current rules against desired {collection: ms}.

    Returns (rules to delete, highest index first; [(rule, ms)] to patch;
    [(collection, ms)] to add).
    """
    current = {}
    for rule in getattr(policy, "rules", None) or []:
        collection = getattr(getattr(rule, "collection", None), "name", None)
        if collection:
            current[collection] = rule
    to_delete = sorted(
        (current[c] for c in current if c not in desired),
        key=_rule_index,
        reverse=True,
    )
    to_patch = [
        (current[c], desired[c])
        for c in desired
        if c in current and getattr(current[c], "resolution", None) != desired[c]
    ]
    to_add = [(c, desired[c]) for c in desired if c not in current]
    return to_delete, to_patch, to_add


def _apply_rule_changes(module, blade, name, changes):
    """Patch first, then delete from the highest index down, then add.

    Rules are addressed as they were read, so the patches go before any
    delete can renumber them, and each delete then only renumbers rules
    that are already gone.
    """
    ctx = _context_kwargs(module)
    to_delete, to_patch, to_add = changes
    for rule, resolution in to_patch:
        res = blade.patch_telemetry_metrics_policies_rules(
            rule=TelemetryMetricsPolicyRulePatch(resolution=resolution),
            **dict(_rule_selector(rule), **ctx)
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to update rule {0} of telemetry metrics policy {1}. "
                "Error: {2}".format(
                    getattr(rule, "name", None), name, get_error_message(res)
                )
            )
    for rule in to_delete:
        res = blade.delete_telemetry_metrics_policies_rules(
            **dict(_rule_selector(rule), **ctx)
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete rule {0} from telemetry metrics policy {1}. "
                "Error: {2}".format(
                    getattr(rule, "name", None), name, get_error_message(res)
                )
            )
    for collection, resolution in to_add:
        res = blade.post_telemetry_metrics_policies_rules(
            policy_names=[name],
            rule=TelemetryMetricsPolicyRule(
                collection=Reference(name=collection), resolution=resolution
            ),
            **ctx
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to add rule for collection {0} to telemetry metrics "
                "policy {1}. Error: {2}".format(
                    collection, name, get_error_message(res)
                )
            )


def create_policy(module, blade, collections):
    name = module.params["name"]
    if not module.params["targets"]:
        module.fail_json(
            msg="targets is required when creating telemetry metrics policy {0}.".format(
                name
            )
        )
    desired = _desired_rules(module, collections)
    ctx = _context_kwargs(module)
    arrays = module.params["arrays"]
    if not arrays:
        res = blade.get_arrays(**ctx)
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to get local array name. Error: {0}".format(
                    get_error_message(res)
                )
            )
        arrays = [list(res.items)[0].name]
    if module.check_mode:
        module.exit_json(changed=True)
    res = blade.post_telemetry_metrics_policies(
        names=[name],
        policy=TelemetryMetricsPolicyPost(
            targets=[Reference(name=target) for target in module.params["targets"]]
        ),
        attach_member_array_names=arrays,
        **ctx
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to create telemetry metrics policy {0}. Error: {1}".format(
                name, get_error_message(res)
            )
        )
    _apply_rule_changes(module, blade, name, ([], [], list(desired.items())))
    policy = _get_policy(module, blade, name)
    module.exit_json(
        changed=True, policy=_policy_to_dict(policy, _get_members(module, blade, name))
    )


def update_policy(module, blade, policy, collections):
    name = module.params["name"]
    ctx = _context_kwargs(module)
    changes = ([], [], [])
    if module.params["rules"] is not None:
        changes = _rule_changes(policy, _desired_rules(module, collections))
    rules_changed = any(changes)

    patch_kwargs = {}
    if module.params["targets"] is not None:
        current_targets = set(
            getattr(target, "name", None)
            for target in getattr(policy, "targets", None) or []
        )
        if set(module.params["targets"]) != current_targets:
            patch_kwargs["targets"] = [
                Reference(name=target) for target in module.params["targets"]
            ]
    if module.params["rename"] and module.params["rename"] != name:
        patch_kwargs["name"] = module.params["rename"]

    members = _get_members(module, blade, name)
    if module.params["arrays"] is not None and set(module.params["arrays"]) != set(
        members
    ):
        module.warn(
            "Telemetry metrics policy {0} is attached to {1}; array membership "
            "can only be set when the policy is created.".format(
                name, ", ".join(members) or "no arrays"
            )
        )

    if not (rules_changed or patch_kwargs):
        module.exit_json(changed=False, policy=_policy_to_dict(policy, members))

    _check_protected(module, name, collections)
    if module.check_mode:
        module.exit_json(changed=True)

    if rules_changed:
        _apply_rule_changes(module, blade, name, changes)
    if patch_kwargs:
        version = getattr(policy, "version", None)
        if rules_changed:
            # Every rule change bumps the policy version; refresh it so the
            # concurrency check below reflects our own writes.
            refreshed = _get_policy(module, blade, name)
            version = getattr(refreshed, "version", version)
        version_kwargs = {"versions": [version]} if version else {}
        res = blade.patch_telemetry_metrics_policies(
            names=[name],
            policy=TelemetryMetricsPolicyPatch(**patch_kwargs),
            **dict(version_kwargs, **ctx)
        )
        if res.status_code != 200:
            error = get_error_message(res)
            hint = ""
            if res.status_code == 412 or "changed by other request" in str(error):
                hint = " The policy was modified concurrently; re-run the task."
            module.fail_json(
                msg="Failed to update telemetry metrics policy {0}. Error: {1}.{2}".format(
                    name, error, hint
                )
            )
        if "name" in patch_kwargs:
            name = patch_kwargs["name"]
    policy = _get_policy(module, blade, name)
    module.exit_json(
        changed=True, policy=_policy_to_dict(policy, _get_members(module, blade, name))
    )


def delete_policy(module, blade, collections):
    name = module.params["name"]
    _check_protected(module, name, collections)
    members = _get_members(module, blade, name)
    if not module.check_mode:
        kwargs = {"names": [name]}
        if members:
            kwargs["detach_member_array_names"] = members
        kwargs.update(_context_kwargs(module))
        res = blade.delete_telemetry_metrics_policies(**kwargs)
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete telemetry metrics policy {0}. Error: {1}".format(
                    name, get_error_message(res)
                )
            )
    module.exit_json(changed=True)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str", required=True),
            state=dict(type="str", default="present", choices=["absent", "present"]),
            targets=dict(type="list", elements="str"),
            rules=dict(
                type="list",
                elements="dict",
                options=dict(
                    collection=dict(type="str", required=True),
                    resolution=dict(type="raw"),
                ),
            ),
            arrays=dict(type="list", elements="str"),
            rename=dict(type="str"),
            force=dict(type="bool", default=False),
            context=dict(type="str", default=""),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    if module.params["targets"] is not None and not module.params["targets"]:
        module.fail_json(
            msg="targets cannot be empty; a telemetry metrics policy needs at "
            "least one target."
        )

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg=(
                "FlashBlade REST version not supported. "
                "Minimum version required: {0} (Purity//FB 4.8.6+)"
            ).format(MIN_REQUIRED_API_VERSION)
        )

    collections = _get_collections(module, blade)
    state = module.params["state"]
    policy = _get_policy(module, blade, module.params["name"])

    if state == "present" and module.params["rename"] and policy is None:
        # The rename may already have happened on an earlier run: if a policy
        # with the new name exists, manage it under that name and treat the
        # rename as done, so a repeated rename task is idempotent.
        renamed = _get_policy(module, blade, module.params["rename"])
        if renamed is None:
            module.fail_json(
                msg="Cannot rename telemetry metrics policy {0}: policy does not exist.".format(
                    module.params["name"]
                )
            )
        module.params["name"] = module.params["rename"]
        module.params["rename"] = None
        policy = renamed

    if state == "absent":
        if policy is None:
            module.exit_json(changed=False)
        delete_policy(module, blade, collections)
    elif policy is None:
        create_policy(module, blade, collections)
    else:
        update_policy(module, blade, policy, collections)


if __name__ == "__main__":
    main()
