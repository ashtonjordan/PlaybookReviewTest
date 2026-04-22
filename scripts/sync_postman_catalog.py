#!/usr/bin/env python3
"""Sync Webex Postman collection into the ecosystem catalog.

Usage:
    # Parse a Postman collection v2.1 JSON export:
    python scripts/sync_postman_catalog.py --postman-export collection.json

    # Parse and merge into an existing catalog:
    python scripts/sync_postman_catalog.py --postman-export collection.json \
        --existing-catalog .github/rules/ecosystem-catalog.yaml

    # Write output to a specific path:
    python scripts/sync_postman_catalog.py --postman-export collection.json \
        --output .github/rules/ecosystem-catalog.yaml

    # Just generate the seed catalog (no Postman export needed):
    python scripts/sync_postman_catalog.py --seed-only \
        --output .github/rules/ecosystem-catalog.yaml

The script extracts REST API endpoint paths, methods, and descriptions from
a Postman collection v2.1 JSON export and writes them into the rest_endpoints
section of the ecosystem catalog YAML file.

When --existing-catalog is provided, the script merges new endpoints into the
existing catalog, preserving sdk_packages, manifest_patterns, and
integration_patterns sections. Duplicate endpoints (same path + method) are
skipped.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml


def parse_postman_collection(data: dict) -> list[dict]:
    """Extract REST endpoints from a Postman collection v2.1 JSON."""
    endpoints: list[dict] = []
    _walk_items(data.get("item", []), endpoints, technology="")
    return endpoints


def _walk_items(items: list, endpoints: list[dict], technology: str) -> None:
    """Recursively walk Postman collection items."""
    for item in items:
        if not isinstance(item, dict):
            continue

        # Folders have nested "item" arrays — use folder name as technology
        if "item" in item and isinstance(item["item"], list):
            folder_name = item.get("name", technology)
            _walk_items(item["item"], endpoints, technology=folder_name)
            continue

        # Leaf items have a "request" object
        request = item.get("request")
        if not isinstance(request, dict):
            continue

        method = request.get("method", "GET").upper()

        # URL can be a string or an object with path segments
        url = request.get("url", "")
        path = _extract_path(url)
        if not path:
            continue

        description = ""
        desc_obj = request.get("description", "")
        if isinstance(desc_obj, dict):
            description = desc_obj.get("content", "")
        elif isinstance(desc_obj, str):
            description = desc_obj

        # Truncate long descriptions
        if len(description) > 200:
            description = description[:197] + "..."

        name = item.get("name", "")

        endpoints.append(
            {
                "path": path,
                "method": method,
                "technology": technology,
                "description": name or description,
            }
        )


def _extract_path(url) -> str:
    """Extract the API path from a Postman URL object or string."""
    if isinstance(url, str):
        # Parse path from full URL string
        match = re.search(r"https?://[^/]+(/.+?)(?:\?|$)", url)
        if match:
            return match.group(1)
        return ""

    if isinstance(url, dict):
        # Postman v2.1 URL object has "path" as a list of segments
        path_segments = url.get("path", [])
        if isinstance(path_segments, list) and path_segments:
            # Join segments, replacing :param with {param} for readability
            parts = []
            for seg in path_segments:
                if isinstance(seg, str):
                    if seg.startswith(":"):
                        parts.append("{" + seg[1:] + "}")
                    else:
                        parts.append(seg)
            return "/" + "/".join(parts)

        # Fallback to raw string
        raw = url.get("raw", "")
        if raw:
            return _extract_path(raw)

    return ""


def _deduplicate_endpoints(endpoints: list[dict]) -> list[dict]:
    """Remove duplicate endpoints (same path + method)."""
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for ep in endpoints:
        key = (ep["path"].lower().rstrip("/"), ep["method"].upper())
        if key not in seen:
            seen.add(key)
            unique.append(ep)
    return unique


# ---------------------------------------------------------------------------
# Seed data: known Webex REST API endpoints
# These are used when no Postman export is available, or merged alongside one.
# Source: https://developer.webex.com/docs/api/v1/
# ---------------------------------------------------------------------------

SEED_REST_ENDPOINTS = [
    # Messaging
    {
        "path": "/v1/messages",
        "method": "GET",
        "technology": "Messaging",
        "description": "List messages in a room",
    },
    {
        "path": "/v1/messages",
        "method": "POST",
        "technology": "Messaging",
        "description": "Create a message",
    },
    {
        "path": "/v1/messages/{messageId}",
        "method": "GET",
        "technology": "Messaging",
        "description": "Get message details",
    },
    {
        "path": "/v1/messages/{messageId}",
        "method": "PUT",
        "technology": "Messaging",
        "description": "Edit a message",
    },
    {
        "path": "/v1/messages/{messageId}",
        "method": "DELETE",
        "technology": "Messaging",
        "description": "Delete a message",
    },
    {
        "path": "/v1/messages/direct",
        "method": "GET",
        "technology": "Messaging",
        "description": "List direct messages",
    },
    # Rooms (Spaces)
    {
        "path": "/v1/rooms",
        "method": "GET",
        "technology": "Messaging",
        "description": "List rooms",
    },
    {
        "path": "/v1/rooms",
        "method": "POST",
        "technology": "Messaging",
        "description": "Create a room",
    },
    {
        "path": "/v1/rooms/{roomId}",
        "method": "GET",
        "technology": "Messaging",
        "description": "Get room details",
    },
    {
        "path": "/v1/rooms/{roomId}",
        "method": "PUT",
        "technology": "Messaging",
        "description": "Update a room",
    },
    {
        "path": "/v1/rooms/{roomId}",
        "method": "DELETE",
        "technology": "Messaging",
        "description": "Delete a room",
    },
    {
        "path": "/v1/rooms/{roomId}/meetingInfo",
        "method": "GET",
        "technology": "Messaging",
        "description": "Get room meeting details",
    },
    # People
    {
        "path": "/v1/people",
        "method": "GET",
        "technology": "Admin",
        "description": "List people",
    },
    {
        "path": "/v1/people",
        "method": "POST",
        "technology": "Admin",
        "description": "Create a person",
    },
    {
        "path": "/v1/people/{personId}",
        "method": "GET",
        "technology": "Admin",
        "description": "Get person details",
    },
    {
        "path": "/v1/people/{personId}",
        "method": "PUT",
        "technology": "Admin",
        "description": "Update a person",
    },
    {
        "path": "/v1/people/{personId}",
        "method": "DELETE",
        "technology": "Admin",
        "description": "Delete a person",
    },
    {
        "path": "/v1/people/me",
        "method": "GET",
        "technology": "Admin",
        "description": "Get my own details",
    },
    # Teams
    {
        "path": "/v1/teams",
        "method": "GET",
        "technology": "Messaging",
        "description": "List teams",
    },
    {
        "path": "/v1/teams",
        "method": "POST",
        "technology": "Messaging",
        "description": "Create a team",
    },
    {
        "path": "/v1/teams/{teamId}",
        "method": "GET",
        "technology": "Messaging",
        "description": "Get team details",
    },
    {
        "path": "/v1/teams/{teamId}",
        "method": "PUT",
        "technology": "Messaging",
        "description": "Update a team",
    },
    {
        "path": "/v1/teams/{teamId}",
        "method": "DELETE",
        "technology": "Messaging",
        "description": "Delete a team",
    },
    # Team Memberships
    {
        "path": "/v1/team/memberships",
        "method": "GET",
        "technology": "Messaging",
        "description": "List team memberships",
    },
    {
        "path": "/v1/team/memberships",
        "method": "POST",
        "technology": "Messaging",
        "description": "Create a team membership",
    },
    {
        "path": "/v1/team/memberships/{membershipId}",
        "method": "GET",
        "technology": "Messaging",
        "description": "Get team membership details",
    },
    {
        "path": "/v1/team/memberships/{membershipId}",
        "method": "PUT",
        "technology": "Messaging",
        "description": "Update a team membership",
    },
    {
        "path": "/v1/team/memberships/{membershipId}",
        "method": "DELETE",
        "technology": "Messaging",
        "description": "Delete a team membership",
    },
    # Memberships
    {
        "path": "/v1/memberships",
        "method": "GET",
        "technology": "Messaging",
        "description": "List memberships",
    },
    {
        "path": "/v1/memberships",
        "method": "POST",
        "technology": "Messaging",
        "description": "Create a membership",
    },
    {
        "path": "/v1/memberships/{membershipId}",
        "method": "GET",
        "technology": "Messaging",
        "description": "Get membership details",
    },
    {
        "path": "/v1/memberships/{membershipId}",
        "method": "PUT",
        "technology": "Messaging",
        "description": "Update a membership",
    },
    {
        "path": "/v1/memberships/{membershipId}",
        "method": "DELETE",
        "technology": "Messaging",
        "description": "Delete a membership",
    },
    # Webhooks
    {
        "path": "/v1/webhooks",
        "method": "GET",
        "technology": "Messaging",
        "description": "List webhooks",
    },
    {
        "path": "/v1/webhooks",
        "method": "POST",
        "technology": "Messaging",
        "description": "Create a webhook",
    },
    {
        "path": "/v1/webhooks/{webhookId}",
        "method": "GET",
        "technology": "Messaging",
        "description": "Get webhook details",
    },
    {
        "path": "/v1/webhooks/{webhookId}",
        "method": "PUT",
        "technology": "Messaging",
        "description": "Update a webhook",
    },
    {
        "path": "/v1/webhooks/{webhookId}",
        "method": "DELETE",
        "technology": "Messaging",
        "description": "Delete a webhook",
    },
    # Attachment Actions (Adaptive Cards)
    {
        "path": "/v1/attachment/actions",
        "method": "POST",
        "technology": "Messaging",
        "description": "Create an attachment action",
    },
    {
        "path": "/v1/attachment/actions/{id}",
        "method": "GET",
        "technology": "Messaging",
        "description": "Get attachment action details",
    },
    # Events
    {
        "path": "/v1/events",
        "method": "GET",
        "technology": "Messaging",
        "description": "List events",
    },
    {
        "path": "/v1/events/{eventId}",
        "method": "GET",
        "technology": "Messaging",
        "description": "Get event details",
    },
    # Meetings
    {
        "path": "/v1/meetings",
        "method": "GET",
        "technology": "Meetings",
        "description": "List meetings",
    },
    {
        "path": "/v1/meetings",
        "method": "POST",
        "technology": "Meetings",
        "description": "Create a meeting",
    },
    {
        "path": "/v1/meetings/{meetingId}",
        "method": "GET",
        "technology": "Meetings",
        "description": "Get meeting details",
    },
    {
        "path": "/v1/meetings/{meetingId}",
        "method": "PUT",
        "technology": "Meetings",
        "description": "Update a meeting",
    },
    {
        "path": "/v1/meetings/{meetingId}",
        "method": "DELETE",
        "technology": "Meetings",
        "description": "Delete a meeting",
    },
    {
        "path": "/v1/meetings/{meetingId}/participants",
        "method": "GET",
        "technology": "Meetings",
        "description": "List meeting participants",
    },
    {
        "path": "/v1/meetings/{meetingId}/registrants",
        "method": "GET",
        "technology": "Meetings",
        "description": "List meeting registrants",
    },
    {
        "path": "/v1/meetings/{meetingId}/registrants",
        "method": "POST",
        "technology": "Meetings",
        "description": "Register for a meeting",
    },
    {
        "path": "/v1/meetings/preferences",
        "method": "GET",
        "technology": "Meetings",
        "description": "Get meeting preferences",
    },
    {
        "path": "/v1/meetings/preferences/sites",
        "method": "GET",
        "technology": "Meetings",
        "description": "Get meeting preference sites",
    },
    # Meeting Recordings
    {
        "path": "/v1/recordings",
        "method": "GET",
        "technology": "Meetings",
        "description": "List recordings",
    },
    {
        "path": "/v1/recordings/{recordingId}",
        "method": "GET",
        "technology": "Meetings",
        "description": "Get recording details",
    },
    {
        "path": "/v1/recordings/{recordingId}",
        "method": "DELETE",
        "technology": "Meetings",
        "description": "Delete a recording",
    },
    # Meeting Transcripts
    {
        "path": "/v1/meeting/transcripts",
        "method": "GET",
        "technology": "Meetings",
        "description": "List meeting transcripts",
    },
    {
        "path": "/v1/meeting/transcripts/{transcriptId}",
        "method": "GET",
        "technology": "Meetings",
        "description": "Get transcript details",
    },
    # Calling
    {
        "path": "/v1/telephony/calls",
        "method": "GET",
        "technology": "Calling",
        "description": "List calls",
    },
    {
        "path": "/v1/telephony/calls/dial",
        "method": "POST",
        "technology": "Calling",
        "description": "Dial a number",
    },
    {
        "path": "/v1/telephony/calls/answer",
        "method": "POST",
        "technology": "Calling",
        "description": "Answer a call",
    },
    {
        "path": "/v1/telephony/calls/hangup",
        "method": "POST",
        "technology": "Calling",
        "description": "Hang up a call",
    },
    {
        "path": "/v1/telephony/calls/hold",
        "method": "POST",
        "technology": "Calling",
        "description": "Hold a call",
    },
    {
        "path": "/v1/telephony/calls/resume",
        "method": "POST",
        "technology": "Calling",
        "description": "Resume a held call",
    },
    {
        "path": "/v1/telephony/calls/transfer",
        "method": "POST",
        "technology": "Calling",
        "description": "Transfer a call",
    },
    {
        "path": "/v1/telephony/calls/history",
        "method": "GET",
        "technology": "Calling",
        "description": "Get call history",
    },
    {
        "path": "/v1/telephony/config/locations",
        "method": "GET",
        "technology": "Calling",
        "description": "List calling locations",
    },
    {
        "path": "/v1/telephony/config/huntGroups",
        "method": "GET",
        "technology": "Calling",
        "description": "List hunt groups",
    },
    {
        "path": "/v1/telephony/config/autoAttendants",
        "method": "GET",
        "technology": "Calling",
        "description": "List auto attendants",
    },
    {
        "path": "/v1/telephony/config/callQueues",
        "method": "GET",
        "technology": "Calling",
        "description": "List call queues",
    },
    {
        "path": "/v1/telephony/voicemail/summary",
        "method": "GET",
        "technology": "Calling",
        "description": "Get voicemail summary",
    },
    # Contact Center
    {
        "path": "/v1/contactCenter/agents",
        "method": "GET",
        "technology": "Contact Center",
        "description": "List contact center agents",
    },
    {
        "path": "/v1/contactCenter/queues",
        "method": "GET",
        "technology": "Contact Center",
        "description": "List contact center queues",
    },
    # Devices
    {
        "path": "/v1/devices",
        "method": "GET",
        "technology": "Devices",
        "description": "List devices",
    },
    {
        "path": "/v1/devices",
        "method": "POST",
        "technology": "Devices",
        "description": "Create a device",
    },
    {
        "path": "/v1/devices/{deviceId}",
        "method": "GET",
        "technology": "Devices",
        "description": "Get device details",
    },
    {
        "path": "/v1/devices/{deviceId}",
        "method": "PUT",
        "technology": "Devices",
        "description": "Update a device",
    },
    {
        "path": "/v1/devices/{deviceId}",
        "method": "DELETE",
        "technology": "Devices",
        "description": "Delete a device",
    },
    {
        "path": "/v1/devices/{deviceId}/activationCode",
        "method": "POST",
        "technology": "Devices",
        "description": "Create device activation code",
    },
    # Workspaces
    {
        "path": "/v1/workspaces",
        "method": "GET",
        "technology": "Devices",
        "description": "List workspaces",
    },
    {
        "path": "/v1/workspaces",
        "method": "POST",
        "technology": "Devices",
        "description": "Create a workspace",
    },
    {
        "path": "/v1/workspaces/{workspaceId}",
        "method": "GET",
        "technology": "Devices",
        "description": "Get workspace details",
    },
    {
        "path": "/v1/workspaces/{workspaceId}",
        "method": "PUT",
        "technology": "Devices",
        "description": "Update a workspace",
    },
    {
        "path": "/v1/workspaces/{workspaceId}",
        "method": "DELETE",
        "technology": "Devices",
        "description": "Delete a workspace",
    },
    # Organizations
    {
        "path": "/v1/organizations",
        "method": "GET",
        "technology": "Admin",
        "description": "List organizations",
    },
    {
        "path": "/v1/organizations/{orgId}",
        "method": "GET",
        "technology": "Admin",
        "description": "Get organization details",
    },
    # Licenses
    {
        "path": "/v1/licenses",
        "method": "GET",
        "technology": "Admin",
        "description": "List licenses",
    },
    {
        "path": "/v1/licenses/{licenseId}",
        "method": "GET",
        "technology": "Admin",
        "description": "Get license details",
    },
    # Roles
    {
        "path": "/v1/roles",
        "method": "GET",
        "technology": "Admin",
        "description": "List roles",
    },
    {
        "path": "/v1/roles/{roleId}",
        "method": "GET",
        "technology": "Admin",
        "description": "Get role details",
    },
    # Admin Audit Events
    {
        "path": "/v1/adminAudit/events",
        "method": "GET",
        "technology": "Admin",
        "description": "List admin audit events",
    },
    # Resource Groups
    {
        "path": "/v1/resourceGroups",
        "method": "GET",
        "technology": "Admin",
        "description": "List resource groups",
    },
    {
        "path": "/v1/resourceGroups/{resourceGroupId}",
        "method": "GET",
        "technology": "Admin",
        "description": "Get resource group details",
    },
    {
        "path": "/v1/resourceGroup/memberships",
        "method": "GET",
        "technology": "Admin",
        "description": "List resource group memberships",
    },
    # Authorizations
    {
        "path": "/v1/authorizations",
        "method": "GET",
        "technology": "Admin",
        "description": "List authorizations",
    },
    {
        "path": "/v1/authorizations/{authorizationId}",
        "method": "GET",
        "technology": "Admin",
        "description": "Get authorization details",
    },
    {
        "path": "/v1/authorizations/{authorizationId}",
        "method": "DELETE",
        "technology": "Admin",
        "description": "Delete an authorization",
    },
    # Contents (file downloads)
    {
        "path": "/v1/contents/{contentId}",
        "method": "GET",
        "technology": "Messaging",
        "description": "Get file content",
    },
]

SEED_SDK_PACKAGES = [
    {
        "name": "webexteamssdk",
        "language": "python",
        "import_patterns": [
            "import\\s+webexteamssdk",
            "from\\s+webexteamssdk\\s+import",
        ],
        "technology": "Messaging",
    },
    {
        "name": "wxc_sdk",
        "language": "python",
        "import_patterns": [
            "import\\s+wxc_sdk",
            "from\\s+wxc_sdk\\s+import",
        ],
        "technology": "Calling",
    },
    {
        "name": "webex-js-sdk",
        "language": "javascript",
        "import_patterns": [
            "require\\s*\\(\\s*['\"]webex['\"]",
            "from\\s+['\"]webex['\"]",
            "import\\s+.*\\s+from\\s+['\"]webex['\"]",
        ],
        "technology": "Messaging",
    },
    {
        "name": "@webex/embedded-app-sdk",
        "language": "javascript",
        "import_patterns": [
            "@webex/embedded-app-sdk",
        ],
        "technology": "Embedded Apps",
    },
    {
        "name": "@webex/widgets",
        "language": "javascript",
        "import_patterns": [
            "@webex/widgets",
        ],
        "technology": "Messaging",
    },
    {
        "name": "webex-node-bot-framework",
        "language": "javascript",
        "import_patterns": [
            "webex-node-bot-framework",
        ],
        "technology": "Messaging",
    },
    {
        "name": "ciscosparkapi",
        "language": "python",
        "import_patterns": [
            "import\\s+ciscosparkapi",
            "from\\s+ciscosparkapi\\s+import",
        ],
        "technology": "Messaging",
    },
]

SEED_MANIFEST_PATTERNS = [
    {
        "pattern_type": "agent_desktop_layout",
        "detection_keys": ["area", "comp"],
        "technology": "Contact Center",
        "description": "Agent Desktop widget layout JSON for Contact Center",
    },
]

SEED_INTEGRATION_PATTERNS = [
    {
        "pattern_type": "byova_grpc",
        "detection_patterns": [
            "VoiceVirtualAgent",
            "ListVirtualAgents",
            "ProcessCallerInput",
            "voicevirtualagent\\.proto",
            "byova_common",
        ],
        "technology": "Contact Center",
        "description": "BYOVA gRPC service definitions for Contact Center virtual agents",
    },
    {
        "pattern_type": "connect_flow",
        "detection_patterns": [
            "webexconnect",
            "imiconnect",
            "WxCC_Flow",
        ],
        "technology": "Contact Center",
        "description": "Webex Connect flow references",
    },
    {
        "pattern_type": "mcp_tool",
        "detection_patterns": [
            "webex-mcp",
            "webex_mcp",
        ],
        "technology": "Messaging",
        "description": "MCP tool references for Webex services",
    },
]


def build_seed_catalog() -> dict:
    """Build the seed catalog with known Webex ecosystem entries."""
    return {
        "sdk_packages": SEED_SDK_PACKAGES,
        "rest_endpoints": SEED_REST_ENDPOINTS,
        "manifest_patterns": SEED_MANIFEST_PATTERNS,
        "integration_patterns": SEED_INTEGRATION_PATTERNS,
    }


def merge_catalogs(existing: dict, new_endpoints: list[dict]) -> dict:
    """Merge new REST endpoints into an existing catalog."""
    catalog = dict(existing)

    existing_eps = catalog.get("rest_endpoints", [])
    seen: set[tuple[str, str]] = set()
    for ep in existing_eps:
        seen.add((ep["path"].lower().rstrip("/"), ep["method"].upper()))

    added = 0
    for ep in new_endpoints:
        key = (ep["path"].lower().rstrip("/"), ep["method"].upper())
        if key not in seen:
            seen.add(key)
            existing_eps.append(ep)
            added += 1

    catalog["rest_endpoints"] = existing_eps
    return catalog, added


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync Webex Postman collection into ecosystem catalog"
    )
    parser.add_argument(
        "--postman-export",
        type=str,
        help="Path to a Postman collection v2.1 JSON export file",
    )
    parser.add_argument(
        "--existing-catalog",
        type=str,
        help="Path to an existing ecosystem-catalog.yaml to merge into",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=".github/rules/ecosystem-catalog.yaml",
        help="Output path for the catalog YAML (default: .github/rules/ecosystem-catalog.yaml)",
    )
    parser.add_argument(
        "--seed-only",
        action="store_true",
        help="Generate only the seed catalog without a Postman export",
    )
    args = parser.parse_args()

    if not args.postman_export and not args.seed_only:
        print("Error: provide --postman-export or --seed-only", file=sys.stderr)
        parser.print_help()
        sys.exit(1)

    # Start with seed catalog or existing catalog
    if args.existing_catalog:
        existing_path = Path(args.existing_catalog)
        if not existing_path.is_file():
            print(
                f"Error: existing catalog not found: {existing_path}", file=sys.stderr
            )
            sys.exit(1)
        with open(existing_path) as f:
            catalog = yaml.safe_load(f) or {}
        print(f"Loaded existing catalog from {existing_path}")
    else:
        catalog = build_seed_catalog()
        print(
            f"Starting with seed catalog ({len(SEED_REST_ENDPOINTS)} REST endpoints, "
            f"{len(SEED_SDK_PACKAGES)} SDK packages)"
        )

    # Parse Postman export if provided
    if args.postman_export:
        postman_path = Path(args.postman_export)
        if not postman_path.is_file():
            print(f"Error: Postman export not found: {postman_path}", file=sys.stderr)
            sys.exit(1)

        with open(postman_path) as f:
            postman_data = json.load(f)

        postman_endpoints = parse_postman_collection(postman_data)
        postman_endpoints = _deduplicate_endpoints(postman_endpoints)
        print(f"Parsed {len(postman_endpoints)} endpoints from Postman export")

        catalog, added = merge_catalogs(catalog, postman_endpoints)
        print(f"Merged {added} new endpoints into catalog")

    # Deduplicate final REST endpoints
    if "rest_endpoints" in catalog:
        catalog["rest_endpoints"] = _deduplicate_endpoints(catalog["rest_endpoints"])

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        yaml.dump(catalog, f, default_flow_style=False, sort_keys=False, width=120)

    ep_count = len(catalog.get("rest_endpoints", []))
    sdk_count = len(catalog.get("sdk_packages", []))
    manifest_count = len(catalog.get("manifest_patterns", []))
    integration_count = len(catalog.get("integration_patterns", []))

    print(f"\nWrote catalog to {output_path}")
    print(f"  REST endpoints:      {ep_count}")
    print(f"  SDK packages:        {sdk_count}")
    print(f"  Manifest patterns:   {manifest_count}")
    print(f"  Integration patterns: {integration_count}")


if __name__ == "__main__":
    main()
