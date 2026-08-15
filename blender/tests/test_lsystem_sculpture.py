"""Blender integration test for the L-system sculpture generator."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[2]
BLENDER_DIR = REPO_ROOT / "blender"
OUTPUT_DIR = BLENDER_DIR / "output" / "lsystem_smoke_test"
sys.path.insert(0, str(BLENDER_DIR))

import flow_field_painter  # noqa: E402


def live_collection() -> bpy.types.Collection:
    return next(
        collection
        for collection in bpy.data.collections
        if collection.get("generator") == "flow_field_painter"
        and collection.get("role") == "live"
    )


def main() -> None:
    # Test the generator in the same empty-artwork condition as the starter file.
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    flow_field_painter.register()
    scene = bpy.context.scene
    props = scene.flow_field_settings
    props.generator_type = "LSYSTEM"
    props.render_size = 128
    props.output_dir = str(OUTPUT_DIR)

    expected_segments = {"TREE": 3125, "FERN": 1488, "CORAL": 1296, "SNOWFLAKE": 768}
    observed = {}
    for preset, expected in expected_segments.items():
        props.lsystem_preset = preset
        flow_field_painter.apply_lsystem_preset(props)
        props.seed = 400 + len(observed)
        assert bpy.ops.flow_field.generate() == {"FINISHED"}
        live = live_collection()
        assert live.get("generator_type") == "LSYSTEM"
        sculpture = next(obj for obj in live.objects if obj.get("role") == "lsystem_sculpture")
        assert sculpture.type == "CURVE"
        assert len(sculpture.data.splines) == expected
        assert sculpture["segment_count"] == expected
        assert scene.frame_end == 1
        observed[preset] = expected

    # Generation replacement remains scoped and rendering writes the exact recipe.
    assert len(
        [collection for collection in bpy.data.collections if collection.get("role") == "live"]
    ) == 1
    props.lsystem_preset = "TREE"
    flow_field_painter.apply_lsystem_preset(props)
    props.seed = 444
    assert bpy.ops.flow_field.generate() == {"FINISHED"}
    assert bpy.ops.flow_field.render() == {"FINISHED"}
    render_path = Path(scene["flow_field_last_render"])
    recipe = json.loads(render_path.with_suffix(".json").read_text(encoding="utf-8"))
    assert recipe["generator_type"] == "LSYSTEM"
    assert recipe["preset"] == "TREE"
    assert recipe["seed"] == 444
    assert render_path.is_file()

    assert bpy.ops.flow_field.freeze() == {"FINISHED"}
    captures = [collection for collection in bpy.data.collections if collection.get("role") == "capture"]
    assert len(captures) == 1
    assert any(obj.type == "MESH" for obj in captures[0].objects)

    print(
        "LSYSTEM_SCULPTURE_VERIFIED",
        {"segments": observed, "render": str(render_path), "mesh_copy": True},
    )


if __name__ == "__main__":
    main()
