"""Blender integration smoke test for the Flow Field Painter extension."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[2]
BLENDER_DIR = REPO_ROOT / "blender"
OUTPUT_DIR = BLENDER_DIR / "output" / "ui_smoke_test"
sys.path.insert(0, str(BLENDER_DIR))

import flow_field_painter  # noqa: E402


def main() -> None:
    flow_field_painter.register()
    scene = bpy.context.scene
    props = scene.flow_field_settings

    # Prove regeneration is scoped: an ordinary user object must survive.
    bpy.ops.mesh.primitive_cube_add()
    user_object = bpy.context.object
    user_object.name = "User Object Must Survive"

    props.seed = 123
    props.agents = 12
    props.steps = 30
    props.mark_spacing = 3
    props.paint_coverage = 0.8
    props.render_size = 128
    props.output_dir = str(OUTPUT_DIR)

    assert bpy.ops.flow_field.generate() == {"FINISHED"}
    live = next(
        collection
        for collection in bpy.data.collections
        if collection.get("generator") == "flow_field_painter"
        and collection.get("role") == "live"
    )
    curves = [obj for obj in live.objects if obj.type == "CURVE"]
    assert len(curves) == 1
    painted_marks = sum(len(obj.data.splines) for obj in curves)
    assert 1 <= painted_marks <= props.agents * props.steps
    assert len([obj for obj in live.objects if obj.get("role") == "canvas"]) == 1
    assert bpy.data.objects.get(user_object.name) is user_object

    props.seed = 124
    assert bpy.ops.flow_field.generate() == {"FINISHED"}
    live_collections = [
        collection
        for collection in bpy.data.collections
        if collection.get("generator") == "flow_field_painter"
        and collection.get("role") == "live"
    ]
    assert len(live_collections) == 1
    assert bpy.data.objects.get(user_object.name) is user_object

    scene.frame_set(1)
    assert bpy.ops.flow_field.freeze() == {"FINISHED"}
    captures = [
        collection
        for collection in bpy.data.collections
        if collection.get("generator") == "flow_field_painter"
        and collection.get("role") == "capture"
    ]
    assert len(captures) == 1
    frozen_meshes = [obj for obj in captures[0].objects if obj.type == "MESH"]
    assert len(frozen_meshes) == 1
    assert sum(len(obj.data.vertices) for obj in frozen_meshes) > 0

    assert bpy.ops.flow_field.render() == {"FINISHED"}
    render_path = Path(scene["flow_field_last_render"])
    recipe_path = render_path.with_suffix(".json")
    assert render_path.is_file()
    assert recipe_path.is_file()
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    assert recipe["seed"] == 124
    assert recipe["opacity_mode"] == props.opacity_mode

    print(
        "FLOW_FIELD_UI_VERIFIED",
        {
            "live_curves": len(curves),
            "painted_marks": painted_marks,
            "frozen_meshes": 1,
            "user_object_preserved": True,
            "render": str(render_path),
        },
    )


if __name__ == "__main__":
    main()
