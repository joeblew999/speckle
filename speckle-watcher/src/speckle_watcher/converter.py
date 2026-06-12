"""
Convert SketchUp framing geometry from Speckle into Howick CSV machine files.

Reads the FrameBuilderMRD layer structure (Stud, Nog, BottomPlate, TopPlate, etc.)
and extracts member positions, lengths, and punch operation positions from mesh vertices.

Usage:
    export SPECKLE_TOKEN="your-token"
    PYTHONPATH=tools/speckle-watcher/src python3 -m speckle_watcher.converter <project_id> <model_id>
"""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from specklepy.api.client import SpeckleClient
from specklepy.transports.server import ServerTransport
from specklepy.api import operations


# ── Howick CSV types ──────────────────────────────────────────────────────────


@dataclass
class Operation:
    """A single machine operation at a position along a component."""
    name: str   # DIMPLE, LIP_CUT, SWAGE, WEB, END_TRUSS, NOTCH, SERVICE_HOLE
    position: float  # mm from start of component


@dataclass
class Component:
    """One steel member to roll-form."""
    id: str          # e.g. W-G1-1
    label: str       # LABEL_NRM or LABEL_INV
    qty: int
    length: float    # mm
    operations: list[Operation] = field(default_factory=list)


@dataclass
class Frameset:
    """A complete job — one CSV file."""
    name: str               # e.g. wall1
    job_name: str           # e.g. 25062026
    unit: str = "MILLIMETRE"
    profile: str = "S8908"
    profile_desc: str = "Standard Profile"
    components: list[Component] = field(default_factory=list)

    def to_csv(self) -> str:
        """Generate Howick CSV content."""
        lines = []
        lines.append(f"UNIT,{self.unit}")
        lines.append(f"PROFILE,{self.profile},{self.profile_desc}")
        lines.append(f"FRAMESET,{self.name},{self.job_name}")

        for comp in self.components:
            parts = [
                "COMPONENT",
                comp.id,
                comp.label,
                str(comp.qty),
                f"{comp.length:.1f}",
            ]
            # Group operations by type, maintaining order
            for op in comp.operations:
                parts.append(op.name)
                parts.append(f"{op.position:.2f}")
            lines.append(",".join(parts))

        return "\n".join(lines) + "\n"


# ── Geometry extraction ───────────────────────────────────────────────────────


# Known operation types and how to detect them from mesh geometry.
# Punch features create extra vertices at specific Z positions along the member.
# We classify based on the cross-section shape at each Z cluster.

# For now: extract all unique Z positions as potential operation sites,
# then classify using heuristics based on the feature geometry.

PROFILE_WEB = 88.9      # S8908 web depth (Y axis)
PROFILE_FLANGE = 41.3   # S8908 flange width (X axis)
PROFILE_LIP = 10.0      # S8908 lip


def extract_mesh_data(elem):
    """Extract vertices from a Speckle mesh element."""
    verts = getattr(elem, "vertices", None)
    if not verts or len(verts) < 3:
        return None

    n = len(verts) // 3
    points = [(verts[j * 3], verts[j * 3 + 1], verts[j * 3 + 2]) for j in range(n)]
    return points


def points_to_bbox(points):
    """Get bounding box from a list of (x, y, z) tuples."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return {
        "min_x": min(xs), "max_x": max(xs),
        "min_y": min(ys), "max_y": max(ys),
        "min_z": min(zs), "max_z": max(zs),
        "dx": max(xs) - min(xs),
        "dy": max(ys) - min(ys),
        "dz": max(zs) - min(zs),
    }


def detect_member_axis(bbox):
    """Determine which axis the member runs along (longest dimension)."""
    dims = {"x": bbox["dx"], "y": bbox["dy"], "z": bbox["dz"]}
    return max(dims, key=dims.get)


def extract_operations(points, bbox, axis):
    """
    Extract punch operations from mesh vertices.

    FrameBuilderMRD models punch features (dimples, swages, service holes, etc.)
    as geometry on the mesh. Each feature creates a cluster of extra vertices at
    its position along the member axis.

    Strategy:
    1. Bin vertices along the member axis (0.5mm resolution)
    2. Find the baseline vertex count per position (plain C-section)
    3. Positions with MORE vertices than baseline are punch features
    4. Classify by vertex count in cluster:
       - SERVICE_HOLE: many vertices (circular hole, 10+ extra)
       - DIMPLE/LIP_CUT/SWAGE: few vertices (2-8 extra)
    5. Classify by position:
       - SWAGE: near ends (~27.5mm from start/end)
       - LIP_CUT: near dimples (~23mm from start/end)
       - DIMPLE: everywhere else
    """
    from collections import Counter

    if axis == "z":
        positions = [p[2] for p in points]
        start = bbox["min_z"]
        length = bbox["dz"]
    elif axis == "x":
        positions = [p[0] for p in points]
        start = bbox["min_x"]
        length = bbox["dx"]
    else:
        positions = [p[1] for p in points]
        start = bbox["min_y"]
        length = bbox["dy"]

    if length < 5.0:
        return []

    # Bin to 0.5mm resolution
    binned = [round((p - start) * 2) / 2 for p in positions]
    bin_counts = Counter(binned)

    # Baseline: the most common count (plain profile cross-section)
    if not bin_counts:
        return []

    count_freq = Counter(bin_counts.values())
    baseline = count_freq.most_common(1)[0][0]

    # Find feature positions: bins with more than baseline vertices
    feature_bins = sorted([pos for pos, count in bin_counts.items()
                           if count > baseline and 0.5 < pos < length - 0.5])

    # Cluster nearby feature bins (within 2mm) into single operations
    clusters = []
    current_cluster = []
    for pos in feature_bins:
        if current_cluster and pos - current_cluster[-1] > 2.0:
            clusters.append(current_cluster)
            current_cluster = []
        current_cluster.append(pos)
    if current_cluster:
        clusters.append(current_cluster)

    # Classify each cluster
    ops = []
    for cluster in clusters:
        center = round(sum(cluster) / len(cluster), 2)
        total_extra_verts = sum(bin_counts[b] - baseline for b in cluster)

        # SERVICE_HOLE: large cluster (many extra vertices = circle of points)
        if total_extra_verts > 10 or len(cluster) > 6:
            ops.append(Operation("SERVICE_HOLE", center))
        # SWAGE: near ends (~27.5mm)
        elif 25.0 <= center <= 30.0 or length - 30.0 <= center <= length - 25.0:
            ops.append(Operation("SWAGE", center))
        # LIP_CUT: at ~23mm from ends
        elif 21.0 <= center <= 25.0 or length - 25.0 <= center <= length - 21.0:
            ops.append(Operation("LIP_CUT", center))
        # DIMPLE: near ends (~18-20mm)
        elif 16.0 <= center <= 21.0 or length - 21.0 <= center <= length - 16.0:
            ops.append(Operation("DIMPLE", center))
        # Interior: classify by cluster size
        elif total_extra_verts > 6:
            ops.append(Operation("SERVICE_HOLE", center))
        else:
            # Default for small interior features
            ops.append(Operation("DIMPLE", center))

    return ops


# ── Layer processing ──────────────────────────────────────────────────────────

# Map FrameBuilderMRD layer names to component ID prefixes
LAYER_ROLE = {
    "Stud": "S",
    "Nog": "N",
    "BottomPlate": "B",
    "TopPlate": "T",
    "window": "W",
    "generic_frame": "GF",
    "lateralbrace": "LB",
}

# Layers that are not machine components (skip these)
SKIP_LAYERS = {
    "wall_external_cladding_1",
    "wall_internal_cladding_1",
}

# Minimum vertex count for a real member (vs. a punch marker)
MIN_MEMBER_VERTS = 20


def collect_meshes(elem, min_verts=MIN_MEMBER_VERTS):
    """Recursively collect all meshes with enough vertices to be real members."""
    results = []
    verts = getattr(elem, "vertices", None)
    if verts and len(verts) // 3 >= min_verts:
        results.append(elem)
    if hasattr(elem, "elements"):
        for sub in elem.elements:
            results.extend(collect_meshes(sub, min_verts))
    return results


def process_layer(layer_name, elements, frameset_name):
    """Process all members in a layer, returning Component objects."""
    components = []
    prefix = LAYER_ROLE.get(layer_name, "X")
    count = 0

    # Recursively collect real meshes (skip tiny punch markers)
    real_meshes = []
    for elem in elements:
        real_meshes.extend(collect_meshes(elem))

    for elem in real_meshes:
        points = extract_mesh_data(elem)
        if not points:
            continue

        count += 1
        bbox = points_to_bbox(points)
        axis = detect_member_axis(bbox)

        if axis == "z":
            length = bbox["dz"]
        elif axis == "x":
            length = bbox["dx"]
        else:
            length = bbox["dy"]

        if length < 5.0:
            continue  # skip tiny fragments

        # Determine label orientation based on position
        label = "LABEL_NRM" if count % 2 == 1 else "LABEL_INV"

        # Extract operations from vertex clustering patterns
        ops = extract_operations(points, bbox, axis)

        comp = Component(
            id=f"{frameset_name}-{prefix}{count}",
            label=label,
            qty=1,
            length=round(length, 2),
            operations=ops,
        )
        components.append(comp)

    return components


# ── Main ──────────────────────────────────────────────────────────────────────


def convert_speckle_to_csv(project_id: str, model_id: str, output_dir: Path = None):
    """
    Fetch geometry from Speckle and convert to Howick CSV.
    """
    server = os.environ.get("SPECKLE_SERVER", "https://app.speckle.systems")
    token = os.environ.get("SPECKLE_TOKEN")
    if not token:
        print("Error: Set SPECKLE_TOKEN environment variable.")
        sys.exit(1)

    client = SpeckleClient(host=server)
    client.authenticate_with_token(token)
    print(f"Connected to {server}")

    # Get latest version
    versions = client.version.get_versions(model_id=model_id, project_id=project_id)
    if not versions.items:
        print("No versions found.")
        sys.exit(1)

    latest = versions.items[0]
    ref_obj = latest.referenced_object
    print(f"Latest version: {latest.id}, object: {ref_obj}")

    # Receive the object tree
    transport = ServerTransport(stream_id=project_id, client=client)
    root = operations.receive(obj_id=ref_obj, remote_transport=transport)
    print(f"Received: {getattr(root, 'name', 'unnamed')}, units={getattr(root, 'units', '?')}")

    # Find the wall layer
    wall_layer = None
    for layer in root.elements:
        if getattr(layer, "name", "") == "wall":
            wall_layer = layer
            break

    if not wall_layer:
        print("Error: No 'wall' layer found in model.")
        print(f"Available layers: {[getattr(l, 'name', '?') for l in root.elements]}")
        sys.exit(1)

    # Process each sub-layer
    frameset_name = "wall1"  # derive from model name
    all_components = []

    for sub in wall_layer.elements:
        layer_name = getattr(sub, "name", "")

        if layer_name in SKIP_LAYERS:
            print(f"  Skipping cladding: {layer_name}")
            continue

        if layer_name not in LAYER_ROLE:
            print(f"  Skipping unknown layer: {layer_name}")
            continue

        elems = sub.elements if hasattr(sub, "elements") else []
        components = process_layer(layer_name, elems, frameset_name)
        print(f"  {layer_name}: {len(elems)} elements → {len(components)} components")
        all_components.extend(components)

    # Build frameset
    frameset = Frameset(
        name=frameset_name,
        job_name="25062026",
        components=all_components,
    )

    csv_content = frameset.to_csv()

    # Output
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{frameset_name}.csv"
        out_path.write_text(csv_content)
        print(f"\nWrote {out_path} ({len(all_components)} components)")
    else:
        print(f"\n--- Generated CSV ({len(all_components)} components) ---")
        # Print first 10 lines
        lines = csv_content.split("\n")
        for line in lines[:13]:
            print(line)
        if len(lines) > 13:
            print(f"... ({len(lines) - 13} more lines)")

    return frameset


def main():
    if len(sys.argv) < 3:
        print("Usage: python -m speckle_watcher.converter <project_id> <model_id> [output_dir]")
        print()
        print("Example:")
        print("  SPECKLE_TOKEN=xxx python -m speckle_watcher.converter f3318660fc c6539853c0")
        print("  SPECKLE_TOKEN=xxx python -m speckle_watcher.converter f3318660fc c6539853c0 output/")
        sys.exit(1)

    project_id = sys.argv[1]
    model_id = sys.argv[2]
    output_dir = Path(sys.argv[3]) if len(sys.argv) > 3 else None

    convert_speckle_to_csv(project_id, model_id, output_dir)


if __name__ == "__main__":
    main()
