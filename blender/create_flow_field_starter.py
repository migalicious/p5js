"""Create the ready-to-open Flow Field Painter starter scene and preview."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy


BLENDER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BLENDER_DIR))

import flow_field_painter  # noqa: E402


def main() -> None:
    flow_field_painter.register()

    # The distributed starter is intentionally empty before the extension adds
    # its own managed collection. The add-on itself remains non-destructive.
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    scene = bpy.context.scene
    props = scene.flow_field_settings
    props.seed = 42
    props.agents = 150
    props.steps = 280
    props.growth_frames = 180
    props.waves = 9
    props.palette = "ELECTRIC"
    props.render_size = 768
    props.output_dir = ""

    result = bpy.ops.flow_field.generate()
    if result != {"FINISHED"}:
        raise RuntimeError(f"Starter generation failed: {result}")

    scene.frame_set(132)
    props.status = "Paused at frame 132 — replay it or start changing knobs"

    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.show_region_ui = True
                area.spaces.active.region_3d.view_perspective = "CAMERA"

    starter_path = BLENDER_DIR / "flow_field_painter_starter.blend"
    preview_dir = BLENDER_DIR / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview_path = preview_dir / "flow_field_painter_v2.png"
    scene.render.filepath = str(preview_path)

    bpy.ops.wm.save_as_mainfile(filepath=str(starter_path))
    bpy.ops.render.render(write_still=True)
    print(f"FLOW_FIELD_STARTER={starter_path}")
    print(f"FLOW_FIELD_PREVIEW={preview_path}")
    flow_field_painter.unregister()


if __name__ == "__main__":
    main()
