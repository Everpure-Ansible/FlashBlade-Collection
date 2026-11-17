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
module: purefb_telemetry_target
version_added: '1.30.0'
short_description: Manage FlashBlade telemetry metrics targets
description:
- Create, modify, rename, test or delete the OpenTelemetry (OTLP) metrics
  targets of a FlashBlade.
- A target describes the receiver that the array exports metrics to. Which
  metrics are exported, and at what resolution, is defined by the telemetry
  metrics policies that reference the target.
- Targets are array-wide objects. An array supports up to 10 targets.
- Requires FlashBlade REST API version 2.29 or later (Purity//FB 4.8.6+).
- A new target stays disabled until I(enabled=true) is set. The array also
  disables a target itself after repeated failed health checks (alert 10176);
  running the module with I(enabled=true) re-enables it.
- A target that is still referenced by a telemetry metrics policy cannot be
  deleted. The array rejects the request and the module reports the error.
- Arrays with phone home enabled carry a system-managed target named
  C(_pure1_target) that cannot be created, modified or deleted.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - Name of the telemetry target.
    type: str
    required: true
  state:
    description:
    - Create or update the target (C(present)), delete it (C(absent)) or run
      the array connectivity test for it (C(test)).
    - I(state=test) checks TCP connectivity to the receiver and delivers one
      dummy metric (C(dummy_metric_milliseconds)) to it; both results are
      returned in C(test_response).
    type: str
    default: present
    choices: [ absent, present, test ]
  endpoint:
    description:
    - Receiver endpoint in the form C(host:port) or C(host:port/path), where
      the host is an IP address or a DNS name.
    - Do not include a scheme. TLS is selected by I(transport).
    - Required when creating a target. Endpoints are unique across the
      targets of an array; the array rejects a second target with the
      endpoint of an existing one.
    type: str
  transport:
    description:
    - Protocol used to export the metrics.
    - A new target uses C(otlp-http-protobuf) when the option is omitted. An
      existing target keeps its current transport.
    - The C(*-without-tls) transports send in clear text and take no
      certificate references; remove any configured certificate reference in
      the same task when switching to one.
    type: str
    choices:
    - otlp-http-protobuf
    - otlp-http-protobuf-without-tls
    - otlp-grpc
    - otlp-grpc-without-tls
  vendor:
    description:
    - Vendor of the receiver. Selects the vendor-specific authentication
      and payload conventions, including how I(target_api_token) is sent.
    - A new target uses C(generic-otlp) when the option is omitted. An
      existing target keeps its current vendor.
    type: str
    choices: [ generic-otlp, datadog, dynatrace, splunk ]
  source:
    description:
    - Name of the network interface (data VIP) the metrics are exported from.
    - Required when creating a target. Every target needs a source, so it can
      be changed but not removed; the module rejects an empty string.
    type: str
  enabled:
    description:
    - Whether export to the target is enabled.
    - A new target is created disabled, the array default, unless
      I(enabled=true) is given. An existing target keeps its current state
      when the option is omitted. The usual workflow is create, test, then
      enable.
    type: bool
  target_api_token:
    description:
    - API token the receiver expects, as issued by the target vendor. Omit it
      when the receiver requires no authentication.
    - This is the token of the target, not the FlashBlade API token used by
      I(api_token) to connect to the array.
    - The array never returns the token, so the module cannot compare it. When
      given, the token is always sent and the task reports C(changed).
    - Use an empty string to remove a configured token.
    type: str
  ca_certificate:
    description:
    - Name of an existing certificate on the array used to validate the
      identity of the receiver for the TLS transports.
    - Mutually exclusive with I(ca_certificate_group); setting one replaces
      the other on the array.
    - Use an empty string to remove a configured certificate.
    - Use M(everpure.flashblade.purefb_certs) to create certificates.
    type: str
  ca_certificate_group:
    description:
    - Name of an existing certificate group on the array whose CA certificates
      validate the identity of the receiver for the TLS transports.
    - Mutually exclusive with I(ca_certificate); setting one replaces the
      other on the array. The group must contain at least one certificate.
    - Use an empty string to remove a configured certificate group.
    - Use M(everpure.flashblade.purefb_certgrp) to create certificate groups.
    type: str
  client_certificate:
    description:
    - Name of an existing certificate on the array that is presented to the
      receiver as the client certificate for mutual TLS.
    - Use an empty string to remove a configured client certificate.
    type: str
  resource_attributes:
    description:
    - Resource attributes added to every metric exported to the target.
    - A target supports at most 10 attributes. Keys and values must be
      alphanumeric and may include C(_) and C(.); the module rejects any
      other character before contacting the array.
    - The list given replaces the whole list on the array. Order is not
      significant; an empty list removes all attributes.
    type: list
    elements: dict
    suboptions:
      key:
        description:
        - Attribute key.
        type: str
        required: true
      value:
        description:
        - Attribute value.
        type: str
        required: true
  rename:
    description:
    - New name for the target.
    - The module fails when neither I(name) nor I(rename) exists.
    type: str
  context:
    description:
    - Name of fleet member on which to perform the operation.
    - This requires the array receiving the request is a member of a fleet
      and the context name to be a member of the same fleet.
    - Not supported with I(state=test).
    type: str
    default: ""
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Create a disabled target for a plain OTLP/HTTP receiver
  everpure.flashblade.purefb_telemetry_target:
    name: otel-collector
    endpoint: collector.example.com:4318/v1/metrics
    transport: otlp-http-protobuf-without-tls
    source: data-vip
    resource_attributes:
      - key: deployment.environment
        value: production
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Test the target connectivity
  everpure.flashblade.purefb_telemetry_target:
    name: otel-collector
    state: test
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
  register: result

- name: Enable the target once the test succeeds
  everpure.flashblade.purefb_telemetry_target:
    name: otel-collector
    enabled: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Export to a vendor receiver over TLS with an API token
  everpure.flashblade.purefb_telemetry_target:
    name: datadog
    endpoint: otlp.datadoghq.com:443
    transport: otlp-http-protobuf
    vendor: datadog
    source: data-vip
    ca_certificate_group: public-cas
    target_api_token: "{{ vault_datadog_api_key }}"
    enabled: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Remove the client certificate from a target
  everpure.flashblade.purefb_telemetry_target:
    name: datadog
    client_certificate: ""
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Rename a target
  everpure.flashblade.purefb_telemetry_target:
    name: otel-collector
    rename: otel-collector-prod
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete a target
  everpure.flashblade.purefb_telemetry_target:
    name: otel-collector-prod
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = r"""
test_response:
  description:
  - Results of the array tests for the target, one entry per check
    (TCP connectivity and OTLP metric delivery).
  returned: when I(state=test)
  type: list
  elements: dict
  contains:
    component_address:
      description: Address of the array component that ran the test.
      type: str
    component_name:
      description: Name of the array component that ran the test.
      type: str
    description:
      description: What the check did.
      type: str
    destination:
      description: URI of the receiver that was tested.
      type: str
    enabled:
      description: Whether export to the target is enabled.
      type: bool
    result_details:
      description: Additional information about the test result.
      type: str
    success:
      description: Whether the test succeeded.
      type: bool
    test_type:
      description: Type of check performed.
      type: str
    resource_name:
      description: Name of the target that was tested.
      type: str
"""


HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        ReferenceWritable,
        TelemetryTargetPatch,
        TelemetryTargetPost,
        TelemetryTargetResourceAttributes,
    )
except ImportError:
    HAS_PYPURECLIENT = False


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

# py-pure-client exposes the telemetry target methods from FB_2_29 only,
# although the REST path itself is older.
MIN_REQUIRED_API_VERSION = "2.29"
MAX_RESOURCE_ATTRIBUTES = 10
# The array answers a bare "Unexpected error" to any other character in an
# attribute key or value, so the module checks them first.
ATTRIBUTE_PATTERN = re.compile(r"^[A-Za-z0-9_.]+$")
# Array defaults applied on create when the play omits the option. On an
# existing target an omitted option leaves the current value alone.
DEFAULT_TRANSPORT = "otlp-http-protobuf"
DEFAULT_VENDOR = "generic-otlp"
TRANSPORTS = [
    "otlp-http-protobuf",
    "otlp-http-protobuf-without-tls",
    "otlp-grpc",
    "otlp-grpc-without-tls",
]
VENDORS = ["generic-otlp", "datadog", "dynatrace", "splunk"]
# Options that are references to objects that must already exist on the
# array (a network interface or a certificate). The module sends
# ReferenceWritable(name=...) and compares against the name on the target.
# A certificate reference is removed with ReferenceWritable(name="").
CERTIFICATE_PARAMS = ("ca_certificate", "ca_certificate_group", "client_certificate")
REFERENCE_PARAMS = ("source",) + CERTIFICATE_PARAMS
SCALAR_PARAMS = ("endpoint", "transport", "vendor", "enabled")


def _context_kwargs(module):
    """Return context_names kwargs when a fleet context is set, else {}."""
    if module.params["context"]:
        return {"context_names": [module.params["context"]]}
    return {}


def _reference_name(obj, field):
    """Name held by a reference field, or None when the reference is unset."""
    return getattr(getattr(obj, field, None), "name", None)


def _attribute_set(attributes):
    """(key, value) pairs of a resource attribute list, order-insensitive."""
    pairs = set()
    for attr in attributes or []:
        if isinstance(attr, dict):
            pairs.add((attr.get("key"), attr.get("value")))
        else:
            pairs.add((getattr(attr, "key", None), getattr(attr, "value", None)))
    return pairs


def _attribute_models(attributes):
    """Build the SDK attribute objects for the attribute list of the play."""
    return [
        TelemetryTargetResourceAttributes(key=attr["key"], value=attr["value"])
        for attr in attributes
    ]


def _get_target(module, blade, name):
    """Return the target called name, or None when it does not exist."""
    res = blade.get_telemetry_targets(names=[name], **_context_kwargs(module))
    if res.status_code == 200:
        items = list(res.items)
        if items:
            return items[0]
    return None


def delete_target(module, blade):
    """Delete the target."""
    changed = True
    if not module.check_mode:
        res = blade.delete_telemetry_targets(
            names=[module.params["name"]], **_context_kwargs(module)
        )
        if res.status_code != 200:
            error = get_error_message(res)
            msg = "Failed to delete telemetry target {0}. Error: {1}".format(
                module.params["name"], error
            )
            if "polic" in str(error).lower():
                msg += (
                    " Remove the target from every telemetry metrics policy "
                    "before deleting it."
                )
            module.fail_json(msg=msg)
    module.exit_json(changed=changed)


def create_target(module, blade):
    """Create the target with the fields given in the play."""
    for param in ("endpoint", "source"):
        if not module.params[param]:
            module.fail_json(
                msg="{0} is required to create a new telemetry target".format(param)
            )
    body = {
        "endpoint": module.params["endpoint"],
        "transport": module.params["transport"] or DEFAULT_TRANSPORT,
        "vendor": module.params["vendor"] or DEFAULT_VENDOR,
    }
    # Sent only when given: an omitted enabled leaves the array default
    # (disabled) in force instead of asserting false explicitly.
    if module.params["enabled"] is not None:
        body["enabled"] = module.params["enabled"]
    if module.params["target_api_token"]:
        body["api_token"] = module.params["target_api_token"]
    for param in REFERENCE_PARAMS:
        if module.params[param]:
            body[param] = ReferenceWritable(name=module.params[param])
    if module.params["resource_attributes"] is not None:
        body["resource_attributes"] = _attribute_models(
            module.params["resource_attributes"]
        )
    changed = True
    if not module.check_mode:
        res = blade.post_telemetry_targets(
            names=[module.params["name"]],
            telemetry_targets=TelemetryTargetPost(**body),
            **_context_kwargs(module)
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to create telemetry target {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def update_target(module, blade, target):
    """PATCH the fields of the existing target that differ from the play."""
    patch = {}
    if module.params["rename"] and module.params["rename"] != target.name:
        patch["name"] = module.params["rename"]
    for param in SCALAR_PARAMS:
        wanted = module.params[param]
        if wanted is not None and wanted != getattr(target, param, None):
            patch[param] = wanted
    # A target always has a source; "" is refused in main(), so only a new
    # name is ever sent.
    source = module.params["source"]
    if source and source != _reference_name(target, "source"):
        patch["source"] = ReferenceWritable(name=source)
    for param in CERTIFICATE_PARAMS:
        wanted = module.params[param]
        # "" removes a configured reference; an unset one reads back as {}
        if wanted is not None and (wanted or None) != _reference_name(target, param):
            patch[param] = ReferenceWritable(name=wanted)
    wanted_attrs = module.params["resource_attributes"]
    if wanted_attrs is not None and _attribute_set(wanted_attrs) != _attribute_set(
        getattr(target, "resource_attributes", None)
    ):
        patch["resource_attributes"] = _attribute_models(wanted_attrs)
    if module.params["target_api_token"] is not None:
        # The array only ever returns "***" for a configured token, so a
        # token given in the play is always sent and reported as a change.
        patch["api_token"] = module.params["target_api_token"]

    changed = bool(patch)
    if changed and not module.check_mode:
        res = blade.patch_telemetry_targets(
            names=[target.name],
            telemetry_targets=TelemetryTargetPatch(**patch),
            **_context_kwargs(module)
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to update telemetry target {0}. Error: {1}".format(
                    target.name, get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def test_target(module, blade):
    """Run the array connectivity test for the target and report it."""
    res = blade.get_telemetry_targets_test(names=[module.params["name"]])
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to test telemetry target {0}. Error: {1}".format(
                module.params["name"], get_error_message(res)
            )
        )
    test_response = []
    for component in list(res.items):
        test_response.append(
            {
                "component_address": getattr(component, "component_address", None),
                "component_name": getattr(component, "component_name", None),
                "description": getattr(component, "description", None),
                "destination": getattr(component, "destination", None),
                "enabled": getattr(component, "enabled", None),
                "result_details": getattr(component, "result_details", ""),
                "success": getattr(component, "success", None),
                "test_type": getattr(component, "test_type", None),
                "resource_name": _reference_name(component, "resource"),
            }
        )
    module.exit_json(changed=False, test_response=test_response)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str", required=True),
            state=dict(
                type="str", default="present", choices=["absent", "present", "test"]
            ),
            endpoint=dict(type="str"),
            transport=dict(type="str", choices=TRANSPORTS),
            vendor=dict(type="str", choices=VENDORS),
            source=dict(type="str"),
            enabled=dict(type="bool"),
            target_api_token=dict(type="str", no_log=True),
            ca_certificate=dict(type="str"),
            ca_certificate_group=dict(type="str"),
            client_certificate=dict(type="str"),
            resource_attributes=dict(
                type="list",
                elements="dict",
                options=dict(
                    key=dict(type="str", required=True, no_log=False),
                    value=dict(type="str", required=True),
                ),
            ),
            rename=dict(type="str"),
            context=dict(type="str", default=""),
        )
    )

    mutually_exclusive = [["ca_certificate", "ca_certificate_group"]]

    module = AnsibleModule(
        argument_spec,
        mutually_exclusive=mutually_exclusive,
        supports_check_mode=True,
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    state = module.params["state"]
    if state == "test" and module.params["context"]:
        module.fail_json(
            msg="context is not supported with state=test; "
            "the telemetry target test is not fleet-aware"
        )
    if module.params["endpoint"] and "://" in module.params["endpoint"]:
        module.fail_json(
            msg="endpoint must be host:port or host:port/path without a scheme"
        )
    attributes = module.params["resource_attributes"]
    if attributes is not None and len(attributes) > MAX_RESOURCE_ATTRIBUTES:
        module.fail_json(
            msg="A telemetry target supports at most {0} resource attributes".format(
                MAX_RESOURCE_ATTRIBUTES
            )
        )
    for attribute in attributes or []:
        for field in ("key", "value"):
            if not ATTRIBUTE_PATTERN.match(attribute[field]):
                module.fail_json(
                    msg=(
                        "Invalid resource attribute {0} '{1}': keys and values "
                        "must be alphanumeric and may include '_' and '.'"
                    ).format(field, attribute[field])
                )
    if module.params["source"] == "":
        module.fail_json(
            msg="source cannot be removed; every telemetry target exports from "
            "a network interface, give a different one instead"
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

    target = _get_target(module, blade, module.params["name"])

    if state == "absent":
        if target:
            delete_target(module, blade)
        module.exit_json(changed=False)
    if state == "test":
        if not target:
            module.fail_json(
                msg="Telemetry target {0} does not exist".format(module.params["name"])
            )
        test_target(module, blade)
    if target:
        update_target(module, blade, target)
    if module.params["rename"]:
        renamed = _get_target(module, blade, module.params["rename"])
        if renamed:
            # The rename already happened on an earlier run; keep the
            # remaining fields of the renamed target in line with the play.
            update_target(module, blade, renamed)
        module.fail_json(
            msg="Telemetry target {0} does not exist, cannot rename it to {1}".format(
                module.params["name"], module.params["rename"]
            )
        )
    create_target(module, blade)


if __name__ == "__main__":
    main()
