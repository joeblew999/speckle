"""
Inspect a Speckle project to see what geometry was extracted from a SketchUp upload.

Usage:
    export SPECKLE_TOKEN="your-token-here"

    # Inspect the default project (opcua-howick-test)
    python -m speckle_watcher.inspect_skp

    # Inspect a specific project and model
    python -m speckle_watcher.inspect_skp <project_id> [model_id]
"""

import os
import sys

from specklepy.api.client import SpeckleClient
from specklepy.transports.server import ServerTransport
from specklepy.api import operations


# Default IDs from our Speckle setup
DEFAULT_PROJECT_ID = "f3318660fc"
DEFAULT_MODEL_ID = "c6539853c0"


def get_client():
    """Connect to Speckle server."""
    server = os.environ.get("SPECKLE_SERVER", "https://app.speckle.systems")
    token = os.environ.get("SPECKLE_TOKEN")

    if not token:
        print("Error: Set SPECKLE_TOKEN environment variable.")
        print("Get a token from: https://app.speckle.systems/settings/user/developer")
        sys.exit(1)

    client = SpeckleClient(host=server)
    client.authenticate_with_token(token)
    user = client.active_user.get()
    print(f"Connected to {server} as {user.name}")
    return client


def inspect_project(client, project_id: str, model_id: str = None):
    """Inspect a Speckle project's geometry."""
    # Get project info
    project = client.project.get_with_models(project_id=project_id)
    print(f"\nProject: {project.name}")
    print(f"Models:")
    for model in project.models.items:
        print(f"  {model.name} (id={model.id})")

    # Use specified model or first available
    if model_id:
        target_model_id = model_id
    elif project.models.items:
        target_model_id = project.models.items[0].id
        print(f"\nUsing first model: {target_model_id}")
    else:
        print("No models found in project.")
        return

    # Get latest version
    versions = client.version.get_versions(
        model_id=target_model_id, project_id=project_id
    )
    if not versions.items:
        print("No versions found. Upload a .skp file to the project first.")
        return

    latest = versions.items[0]
    ref_obj = latest.referenced_object
    print(f"\nLatest version: {latest.id}")
    print(f"Referenced object: {ref_obj}")

    # Receive the object tree
    print(f"\nReceiving object tree...")
    transport = ServerTransport(stream_id=project_id, client=client)
    root = operations.receive(obj_id=ref_obj, remote_transport=transport)

    # Walk and print
    print(f"\n{'='*60}")
    print(f"OBJECT TREE")
    print(f"{'='*60}")
    walk_object(root, depth=0, max_depth=4)


def walk_object(obj, depth=0, max_depth=4):
    """Recursively walk a Speckle object and print its structure."""
    indent = "  " * depth

    if depth > max_depth:
        print(f"{indent}... (max depth reached)")
        return

    speckle_type = getattr(obj, "speckle_type", None) or type(obj).__name__
    members = []
    if hasattr(obj, "get_member_names"):
        members = [
            m for m in obj.get_member_names()
            if not m.startswith("_")
            and m not in ("id", "speckle_type", "totalChildrenCount", "applicationId")
        ]

    print(f"{indent}[{speckle_type}] members={len(members)}")

    for name in members[:20]:
        val = getattr(obj, name, None)
        if val is None:
            continue

        if isinstance(val, (str, int, float, bool)):
            s = repr(val)
            if len(s) > 100:
                s = s[:100] + "..."
            print(f"{indent}  {name} = {s}")
        elif isinstance(val, list):
            print(f"{indent}  {name} = list[{len(val)}]")
            for i, item in enumerate(val[:3]):
                if hasattr(item, "speckle_type") or hasattr(item, "get_member_names"):
                    walk_object(item, depth + 2, max_depth)
                else:
                    print(f"{indent}    [{i}] {type(item).__name__}: {str(item)[:80]}")
            if len(val) > 3:
                print(f"{indent}    ... and {len(val) - 3} more")
        elif hasattr(val, "speckle_type") or hasattr(val, "get_member_names"):
            print(f"{indent}  {name}:")
            walk_object(val, depth + 1, max_depth)
        else:
            print(f"{indent}  {name} = {type(val).__name__}")


def main():
    client = get_client()

    if len(sys.argv) >= 3:
        project_id = sys.argv[1]
        model_id = sys.argv[2]
    elif len(sys.argv) == 2:
        project_id = sys.argv[1]
        model_id = None
    else:
        project_id = DEFAULT_PROJECT_ID
        model_id = DEFAULT_MODEL_ID
        print(f"Using default project: {project_id}, model: {model_id}")

    inspect_project(client, project_id, model_id)


if __name__ == "__main__":
    main()
