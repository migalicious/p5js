"""Blender integration test for dense strange-attractor point art."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[2]
BLENDER_DIR = REPO_ROOT / "blender"
OUTPUT_DIR = BLENDER_DIR / "output" / "attractor_smoke_test"
sys.path.insert(0, str(BLENDER_DIR))

import flow_field_painter  # noqa: E402


def generated_point_count() -> int:
    return sum(
        int(obj.get("point_count", 0))
        for obj in bpy.data.objects
        if obj.get("role") == "attractor_points"
    )


def main() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    flow_field_painter.register()
    scene = bpy.context.scene
    props = scene.flow_field_settings
    props.generator_type = "ATTRACTOR"
    props.attractor_iterations = 12_000
    props.attractor_point_size = 0.025
    props.attractor_opacity = 0.3
    props.render_size = 192
    props.output_dir = str(OUTPUT_DIR)

    observed = {}
    for preset, equation in (
        ("CLIFFORD_RIBBONS", "CLIFFORD"),
        ("DEJONG_LACE", "DEJONG"),
        ("LORENZ", "LORENZ"),
    ):
        props.attractor_preset = preset
        flow_field_painter.apply_attractor_preset(props)
        props.attractor_iterations = 12_000
        assert bpy.ops.flow_field.generate() == {"FINISHED"}
        assert props.attractor_type == equation
        assert generated_point_count() == 12_000
        point_objects = [obj for obj in bpy.data.objects if obj.get("role") == "attractor_points"]
        assert 1 <= len(point_objects) <= 5
        assert all(obj.type == "MESH" for obj in point_objects)
        assert all(any(modifier.type == "NODES" for modifier in obj.modifiers) for obj in point_objects)
        observed[equation] = generated_point_count()

    # A second generation replaces data and node groups instead of leaking them.
    props.attractor_preset = "CLIFFORD_RIBBONS"
    flow_field_painter.apply_attractor_preset(props)
    props.attractor_iterations = 45_000
    props.seed = 818
    assert bpy.ops.flow_field.generate() == {"FINISHED"}
    assert generated_point_count() == 45_000
    tagged_groups = [group for group in bpy.data.node_groups if group.get("generator") == "flow_field_painter"]
    assert len(tagged_groups) <= 5

    assert bpy.ops.flow_field.render() == {"FINISHED"}
    render_path = Path(scene["flow_field_last_render"])
    recipe = json.loads(render_path.with_suffix(".json").read_text(encoding="utf-8"))
    assert recipe["generator_type"] == "ATTRACTOR"
    assert recipe["attractor_type"] == "CLIFFORD"
    assert recipe["iterations"] == 45_000
    assert recipe["seed"] == 818
    assert render_path.is_file()

    print(
        "STRANGE_ATTRACTOR_VERIFIED",
        {"equations": observed, "dense_points": 45_000, "render": str(render_path)},
    )


if __name__ == "__main__":
    main()
