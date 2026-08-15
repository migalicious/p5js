"""Build an animated, seeded 3D flow-field painting in Blender.

Run with Blender, not the system Python:

    blender --background --factory-startup \
      --python blender/flow_field_prototype.py -- --render

Everything after ``--`` is handled by this script. The generated .blend and its
JSON recipe are written to blender/output by default.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.noise import noise_vector


PALETTE = (
    "3B1C59",  # violet shadow
    "6C4DF6",  # electric purple
    "2BC4C9",  # turquoise
    "F4C95D",  # warm yellow
    "F26A8D",  # coral pink
)


@dataclass(frozen=True)
class FlowSettings:
    seed: int = 42
    agents: int = 150
    steps: int = 280
    growth_frames: int = 180
    capture_frame: int = 132
    waves: int = 9
    field_scale: float = 0.31
    step_size: float = 0.067
    inertia: float = 0.84
    noise_strength: float = 1.0
    orbit_strength: float = 0.42
    center_strength: float = 0.23
    lift_strength: float = 0.16
    bounds_radius: float = 4.8
    trail_radius: float = 0.023
    render_size: int = 768


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--agents", type=int, default=150)
    parser.add_argument("--steps", type=int, default=280)
    parser.add_argument("--capture-frame", type=int, default=132)
    parser.add_argument("--growth-frames", type=int, default=180)
    parser.add_argument("--render-size", type=int, default=768)
    parser.add_argument("--output-dir", default="blender/output")
    parser.add_argument("--render", action="store_true")
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def hex_rgba(value: str) -> tuple[float, float, float, float]:
    return tuple(int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)) + (1.0,)


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (
        bpy.data.curves,
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        for datablock in tuple(datablocks):
            datablocks.remove(datablock)


def make_material(name: str, color_hex: str) -> bpy.types.Material:
    color = hex_rgba(color_hex)
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Metallic"].default_value = 0.28
    principled.inputs["Roughness"].default_value = 0.3
    principled.inputs["Coat Weight"].default_value = 0.25
    principled.inputs["Emission Color"].default_value = color
    principled.inputs["Emission Strength"].default_value = 0.14
    return material


def initial_position(rng: random.Random, radius: float) -> Vector:
    # A flattened volume fills the camera composition while retaining depth.
    angle = rng.uniform(0, math.tau)
    radial = radius * math.sqrt(rng.random()) * 0.78
    return Vector(
        (
            math.cos(angle) * radial,
            math.sin(angle) * radial,
            rng.uniform(-radius * 0.48, radius * 0.48),
        )
    )


def field_direction(position: Vector, settings: FlowSettings, seed_offset: Vector) -> Vector:
    sample_position = position * settings.field_scale + seed_offset
    field = noise_vector(sample_position, noise_basis="PERLIN_ORIGINAL")
    field *= settings.noise_strength

    planar = Vector((-position.y, position.x, 0.0))
    if planar.length_squared > 1e-8:
        field += planar.normalized() * settings.orbit_strength

    distance = position.length
    if distance > 1e-8:
        # Gentle containment keeps trails painting the shared volume instead of
        # terminating abruptly at an invisible box.
        center_weight = 0.3 + (distance / settings.bounds_radius) ** 2
        field -= position.normalized() * settings.center_strength * center_weight

    field.z += math.sin(position.x * 0.72 + position.y * 0.37) * settings.lift_strength
    return field


def trace_agent(
    rng: random.Random,
    settings: FlowSettings,
    seed_offset: Vector,
) -> list[Vector]:
    position = initial_position(rng, settings.bounds_radius)
    velocity = Vector(
        (rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.45, 0.45))
    ).normalized()
    points = [position.copy()]

    for _ in range(settings.steps - 1):
        desired = field_direction(position, settings, seed_offset)
        if desired.length_squared < 1e-10:
            desired = velocity
        else:
            desired.normalize()

        velocity = velocity * settings.inertia + desired * (1.0 - settings.inertia)
        velocity.normalize()
        position = position + velocity * settings.step_size
        points.append(position.copy())

    return points


def add_trail_spline(
    curve: bpy.types.Curve,
    points: list[Vector],
    material_index: int,
    width_variation: float,
) -> None:
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    spline.material_index = material_index
    last = max(1, len(points) - 1)

    for index, (spline_point, position) in enumerate(zip(spline.points, points)):
        progress = index / last
        # Fine at both ends and fuller through the middle, like a drawn gesture.
        taper = max(0.08, math.sin(math.pi * progress) ** 0.42)
        spline_point.co = (*position, 1.0)
        spline_point.radius = taper * width_variation


def build_trails(
    settings: FlowSettings,
    collection: bpy.types.Collection,
    materials: list[bpy.types.Material],
) -> list[bpy.types.Object]:
    rng = random.Random(settings.seed)
    seed_rng = random.Random(settings.seed ^ 0x5F3759DF)
    seed_offset = Vector(tuple(seed_rng.uniform(-200, 200) for _ in range(3)))

    curves: list[bpy.types.Curve] = []
    objects: list[bpy.types.Object] = []
    for wave_index in range(settings.waves):
        curve = bpy.data.curves.new(f"Flow Trails {wave_index + 1:02d}", "CURVE")
        curve.dimensions = "3D"
        curve.resolution_u = 2
        curve.bevel_depth = settings.trail_radius
        curve.bevel_resolution = 3
        curve.use_fill_caps = True
        curve.bevel_factor_start = 0.0
        curve.bevel_factor_end = 0.0
        for material in materials:
            curve.materials.append(material)

        obj = bpy.data.objects.new(curve.name, curve)
        collection.objects.link(obj)
        obj["flow_seed"] = settings.seed
        obj["wave"] = wave_index
        curves.append(curve)
        objects.append(obj)

    for agent_index in range(settings.agents):
        wave_index = agent_index % settings.waves
        palette_index = rng.randrange(len(materials))
        width_variation = rng.uniform(0.62, 1.42)
        points = trace_agent(rng, settings, seed_offset)
        add_trail_spline(curves[wave_index], points, palette_index, width_variation)

    # Staggered waves retain the sense of a process unfolding instead of a
    # finished object simply scaling into view.
    for wave_index, curve in enumerate(curves):
        start_frame = 1 + wave_index * 3
        end_frame = start_frame + settings.growth_frames
        curve.bevel_factor_end = 0.0
        curve.keyframe_insert("bevel_factor_end", frame=start_frame)
        curve.bevel_factor_end = 1.0
        curve.keyframe_insert("bevel_factor_end", frame=end_frame)

        animation_data = curve.animation_data
        action = animation_data.action if animation_data else None
        if action and action.layers:
            strip = action.layers[0].strips[0]
            channelbag = strip.channelbag(animation_data.action_slot)
            for fcurve in channelbag.fcurves:
                for keyframe in fcurve.keyframe_points:
                    keyframe.interpolation = "LINEAR"

    return objects


def add_camera(scene: bpy.types.Scene) -> bpy.types.Object:
    camera_data = bpy.data.cameras.new("Flow Camera")
    camera_data.lens = 57
    camera_data.sensor_width = 36
    camera_data.dof.use_dof = True
    camera_data.dof.focus_distance = 14.2
    camera_data.dof.aperture_fstop = 5.0
    camera = bpy.data.objects.new("Flow Camera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = (9.8, -11.8, 7.4)
    look_at(camera, Vector((0.0, 0.0, 0.0)))
    scene.camera = camera
    return camera


def add_area_light(
    scene: bpy.types.Scene,
    name: str,
    location: tuple[float, float, float],
    energy: float,
    color: tuple[float, float, float],
    size: float,
) -> None:
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.color = color
    data.shape = "DISK"
    data.size = size
    light = bpy.data.objects.new(name, data)
    scene.collection.objects.link(light)
    light.location = location
    look_at(light, Vector((0.0, 0.0, 0.0)))


def add_stage(scene: bpy.types.Scene) -> None:
    add_area_light(scene, "Key Light", (5.5, -4.0, 9.0), 1200, (0.72, 0.8, 1.0), 5.5)
    add_area_light(scene, "Rim Light", (-6.0, 2.5, 5.0), 950, (1.0, 0.35, 0.5), 4.0)
    add_area_light(scene, "Fill Light", (1.0, 7.0, -1.0), 700, (0.3, 0.8, 1.0), 3.5)


def configure_scene(scene: bpy.types.Scene, settings: FlowSettings) -> None:
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = settings.render_size
    scene.render.resolution_y = settings.render_size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.render.image_settings.color_depth = "8"
    scene.render.filepath = ""
    scene.frame_start = 1
    scene.frame_end = settings.growth_frames + settings.waves * 3
    scene.frame_set(min(max(settings.capture_frame, scene.frame_start), scene.frame_end))

    scene.world.color = (0.004, 0.006, 0.012)
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.003, 0.005, 0.012, 1.0)
    background.inputs["Strength"].default_value = 0.12

    scene.view_settings.look = "AgX - Medium High Contrast"
    scene["generator"] = "flow_field_prototype"
    scene["recipe"] = json.dumps(asdict(settings), sort_keys=True)


def build(settings: FlowSettings) -> bpy.types.Scene:
    clear_scene()
    scene = bpy.context.scene
    configure_scene(scene, settings)

    collection = bpy.data.collections.new("Generated Flow Painting")
    scene.collection.children.link(collection)
    materials = [
        make_material(f"Flow {index + 1:02d} #{color}", color)
        for index, color in enumerate(PALETTE)
    ]
    build_trails(settings, collection, materials)
    add_camera(scene)
    add_stage(scene)
    scene.frame_set(settings.capture_frame)
    return scene


def main() -> None:
    args = parse_args()
    settings = FlowSettings(
        seed=args.seed,
        agents=max(1, args.agents),
        steps=max(2, args.steps),
        growth_frames=max(2, args.growth_frames),
        capture_frame=max(1, args.capture_frame),
        render_size=max(64, args.render_size),
    )
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"flow_field_seed_{settings.seed:04d}_frame_{settings.capture_frame:04d}"
    blend_path = output_dir / f"{stem}.blend"
    recipe_path = output_dir / f"{stem}.json"
    render_path = output_dir / f"{stem}.png"

    scene = build(settings)
    scene.render.filepath = str(render_path)
    recipe_path.write_text(json.dumps(asdict(settings), indent=2) + "\n", encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

    if args.render:
        bpy.ops.render.render(write_still=True)

    print(f"FLOW_FIELD_BLEND={blend_path}")
    print(f"FLOW_FIELD_RECIPE={recipe_path}")
    if args.render:
        print(f"FLOW_FIELD_RENDER={render_path}")


if __name__ == "__main__":
    main()
