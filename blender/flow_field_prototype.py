"""Command-line entry point for the reusable Flow Field Painter generator.

Run with Blender, not the system Python:

    blender --background --factory-startup \
      --python blender/flow_field_prototype.py -- --render

Everything after ``--`` is handled by this script. The generated .blend and its
JSON recipe are written to blender/output by default.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy

BLENDER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BLENDER_DIR))

from flow_field_painter.generator import FlowSettings, build, recipe_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--agents", type=int, default=70)
    parser.add_argument("--steps", type=int, default=260)
    parser.add_argument("--render-size", type=int, default=768)
    parser.add_argument("--output-dir", default="blender/output")
    parser.add_argument("--render", action="store_true")
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    settings = FlowSettings(
        seed=args.seed,
        agents=max(1, args.agents),
        steps=max(2, args.steps),
        render_size=max(64, args.render_size),
    )
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"surface_paint_seed_{settings.seed:04d}"
    blend_path = output_dir / f"{stem}.blend"
    recipe_path = output_dir / f"{stem}.json"
    render_path = output_dir / f"{stem}.png"

    scene = bpy.context.scene
    build(scene, settings)
    scene.render.filepath = str(render_path)
    recipe_path.write_text(recipe_json(settings, indent=2) + "\n", encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

    if args.render:
        bpy.ops.render.render(write_still=True)

    print(f"FLOW_FIELD_BLEND={blend_path}")
    print(f"FLOW_FIELD_RECIPE={recipe_path}")
    if args.render:
        print(f"FLOW_FIELD_RENDER={render_path}")


if __name__ == "__main__":
    main()
