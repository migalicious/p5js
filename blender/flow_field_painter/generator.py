"""Reusable scene builder for the Flow Field Painter Blender extension."""

from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass

import bpy
from mathutils import Vector
from mathutils.noise import noise_vector


GENERATOR_TAG = "flow_field_painter"
GENERATED_COLLECTION = "Flow Field Painting"
CAPTURES_COLLECTION = "Flow Field Captures"

PALETTES = {
    "ELECTRIC": (
        "3B1C59",
        "6C4DF6",
        "2BC4C9",
        "F4C95D",
        "F26A8D",
    ),
    "EMBER": (
        "351414",
        "9D2D21",
        "E85D2A",
        "FFB000",
        "FFE6A7",
    ),
    "TIDAL": (
        "082F49",
        "0369A1",
        "06B6D4",
        "67E8F9",
        "ECFEFF",
    ),
    "GROVE": (
        "14281D",
        "355834",
        "6E9F52",
        "B7D77A",
        "F0F3BD",
    ),
    "MONO": (
        "171717",
        "404040",
        "737373",
        "D4D4D4",
        "FAFAFA",
    ),
}


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
    palette: str = "ELECTRIC"
    metallic: float = 0.28
    roughness: float = 0.3
    emission_strength: float = 0.14
    camera_azimuth: float = 50.3
    camera_elevation: float = 31.5
    camera_distance: float = 16.9
    camera_lens: float = 57.0
    render_size: int = 768


def recipe_json(settings: FlowSettings, *, indent: int | None = None) -> str:
    return json.dumps(asdict(settings), indent=indent, sort_keys=True)


def hex_rgba(value: str) -> tuple[float, float, float, float]:
    return tuple(int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)) + (1.0,)


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def _tag(datablock: object) -> None:
    datablock["generator"] = GENERATOR_TAG


def _find_generated_collection() -> bpy.types.Collection | None:
    for collection in bpy.data.collections:
        if collection.get("generator") == GENERATOR_TAG and collection.get("role") == "live":
            return collection
    return None


def remove_live_generation(scene: bpy.types.Scene) -> None:
    """Remove only the extension's live generation, preserving captures and user art."""
    collection = _find_generated_collection()
    if collection is None:
        return

    objects = list(collection.all_objects)
    materials = {
        slot.material
        for obj in objects
        for slot in obj.material_slots
        if slot.material and slot.material.get("generator") == GENERATOR_TAG
    }

    if scene.camera in objects:
        scene.camera = None
    for obj in objects:
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(collection)

    for material in materials:
        if material.users == 0:
            bpy.data.materials.remove(material)


def make_material(
    name: str,
    color_hex: str,
    settings: FlowSettings,
) -> bpy.types.Material:
    color = hex_rgba(color_hex)
    material = bpy.data.materials.new(name)
    _tag(material)
    material.diffuse_color = color
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Metallic"].default_value = settings.metallic
    principled.inputs["Roughness"].default_value = settings.roughness
    principled.inputs["Coat Weight"].default_value = 0.25
    principled.inputs["Emission Color"].default_value = color
    principled.inputs["Emission Strength"].default_value = settings.emission_strength
    return material


def initial_position(rng: random.Random, radius: float) -> Vector:
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
    )
    if velocity.length_squared < 1e-10:
        velocity = Vector((1.0, 0.0, 0.0))
    else:
        velocity.normalize()
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
        _tag(obj)
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


def add_camera(
    scene: bpy.types.Scene,
    collection: bpy.types.Collection,
    settings: FlowSettings,
) -> bpy.types.Object:
    camera_data = bpy.data.cameras.new("Flow Camera")
    camera_data.lens = settings.camera_lens
    camera_data.sensor_width = 36
    camera_data.dof.use_dof = True
    camera_data.dof.focus_distance = settings.camera_distance
    camera_data.dof.aperture_fstop = 5.0
    camera = bpy.data.objects.new("Flow Camera", camera_data)
    _tag(camera)
    collection.objects.link(camera)

    azimuth = math.radians(settings.camera_azimuth)
    elevation = math.radians(settings.camera_elevation)
    planar = settings.camera_distance * math.cos(elevation)
    camera.location = (
        planar * math.cos(azimuth),
        -planar * math.sin(azimuth),
        settings.camera_distance * math.sin(elevation),
    )
    look_at(camera, Vector((0.0, 0.0, 0.0)))
    scene.camera = camera
    return camera


def add_area_light(
    collection: bpy.types.Collection,
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
    _tag(light)
    collection.objects.link(light)
    light.location = location
    look_at(light, Vector((0.0, 0.0, 0.0)))


def add_stage(collection: bpy.types.Collection) -> None:
    add_area_light(collection, "Key Light", (5.5, -4.0, 9.0), 1200, (0.72, 0.8, 1.0), 5.5)
    add_area_light(collection, "Rim Light", (-6.0, 2.5, 5.0), 950, (1.0, 0.35, 0.5), 4.0)
    add_area_light(collection, "Fill Light", (1.0, 7.0, -1.0), 700, (0.3, 0.8, 1.0), 3.5)


def configure_scene(scene: bpy.types.Scene, settings: FlowSettings) -> None:
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = settings.render_size
    scene.render.resolution_y = settings.render_size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.frame_start = 1
    scene.frame_end = settings.growth_frames + settings.waves * 3

    world = bpy.data.worlds.get("Flow Field World") or bpy.data.worlds.new("Flow Field World")
    _tag(world)
    scene.world = world
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.003, 0.005, 0.012, 1.0)
    background.inputs["Strength"].default_value = 0.12

    scene.view_settings.look = "AgX - Medium High Contrast"
    scene["generator"] = GENERATOR_TAG
    scene["recipe"] = recipe_json(settings)


def build(scene: bpy.types.Scene, settings: FlowSettings) -> bpy.types.Collection:
    remove_live_generation(scene)
    configure_scene(scene, settings)

    collection = bpy.data.collections.new(GENERATED_COLLECTION)
    _tag(collection)
    collection["role"] = "live"
    scene.collection.children.link(collection)

    palette = PALETTES.get(settings.palette, PALETTES["ELECTRIC"])
    materials = [
        make_material(f"Flow {index + 1:02d} #{color}", color, settings)
        for index, color in enumerate(palette)
    ]
    build_trails(settings, collection, materials)
    add_camera(scene, collection, settings)
    add_stage(collection)
    scene.frame_set(min(max(settings.capture_frame, scene.frame_start), scene.frame_end))
    return collection


def freeze_current_frame(
    scene: bpy.types.Scene,
    depsgraph: bpy.types.Depsgraph,
) -> bpy.types.Collection:
    source = _find_generated_collection()
    if source is None:
        raise RuntimeError("Generate a flow painting before freezing a frame")

    root = bpy.data.collections.get(CAPTURES_COLLECTION)
    if root is None:
        root = bpy.data.collections.new(CAPTURES_COLLECTION)
        _tag(root)
        root["role"] = "captures"
        scene.collection.children.link(root)

    seed = int(scene.get("flow_field_seed", 0))
    name = f"Capture seed {seed} frame {scene.frame_current}"
    capture = bpy.data.collections.new(name)
    _tag(capture)
    capture["role"] = "capture"
    capture["seed"] = seed
    capture["frame"] = scene.frame_current
    capture["recipe"] = scene.get("recipe", "")
    root.children.link(capture)

    for obj in source.objects:
        if obj.type != "CURVE":
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = bpy.data.meshes.new_from_object(evaluated, depsgraph=depsgraph)
        frozen = bpy.data.objects.new(f"{obj.name} frozen", mesh)
        _tag(frozen)
        frozen["role"] = "capture"
        frozen["seed"] = seed
        frozen["frame"] = scene.frame_current
        frozen.matrix_world = obj.matrix_world.copy()
        capture.objects.link(frozen)

    return capture
