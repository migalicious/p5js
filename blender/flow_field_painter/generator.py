"""Reusable scene builder for the Flow Field Painter Blender extension."""

from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass

import bmesh
import bpy
from mathutils import Vector
from mathutils.noise import noise, noise_vector


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
    agents: int = 70
    steps: int = 260
    field_scale: float = 0.22
    step_size: float = 0.065
    inertia: float = 0.93
    noise_strength: float = 0.85
    orbit_strength: float = 0.65
    trail_radius: float = 0.035
    canvas_radius: float = 4.0
    mark_spacing: int = 4
    mark_length: float = 0.16
    paint_coverage: float = 0.82
    opacity_mode: str = "FADE_PATH"
    opacity_min: float = 0.15
    opacity_max: float = 0.95
    opacity_scale: float = 0.72
    opacity_buckets: int = 6
    show_canvas: bool = True
    palette: str = "ELECTRIC"
    metallic: float = 0.28
    roughness: float = 0.3
    emission_strength: float = 0.14
    camera_azimuth: float = 50.3
    camera_elevation: float = 31.5
    camera_distance: float = 13.8
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
    object_data = [(obj.type, obj.data) for obj in objects if obj.data is not None]
    node_groups = {
        modifier.node_group
        for obj in objects
        for modifier in obj.modifiers
        if modifier.type == "NODES" and modifier.node_group is not None
    }
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

    data_collections = {
        "MESH": bpy.data.meshes,
        "CURVE": bpy.data.curves,
        "CAMERA": bpy.data.cameras,
        "LIGHT": bpy.data.lights,
    }
    for object_type, datablock in object_data:
        owner = data_collections.get(object_type)
        if owner is not None and datablock.users == 0:
            owner.remove(datablock)
    for node_group in node_groups:
        if node_group.users == 0:
            bpy.data.node_groups.remove(node_group)

    for material in materials:
        if material.users == 0:
            bpy.data.materials.remove(material)


def make_paint_material(
    name: str,
    color_hex: str,
    opacity: float,
    settings: FlowSettings,
) -> bpy.types.Material:
    color = hex_rgba(color_hex)
    rgba = (*color[:3], opacity)
    material = bpy.data.materials.new(name)
    _tag(material)
    material.diffuse_color = rgba
    material.surface_render_method = "DITHERED"
    material.use_transparency_overlap = False
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Metallic"].default_value = settings.metallic
    principled.inputs["Roughness"].default_value = settings.roughness
    principled.inputs["Coat Weight"].default_value = 0.18
    principled.inputs["Emission Color"].default_value = color
    principled.inputs["Emission Strength"].default_value = settings.emission_strength
    principled.inputs["Alpha"].default_value = opacity
    return material


def make_canvas_material() -> bpy.types.Material:
    material = bpy.data.materials.new("Flow Canvas")
    _tag(material)
    color = (0.008, 0.012, 0.022, 1.0)
    material.diffuse_color = color
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Metallic"].default_value = 0.12
    principled.inputs["Roughness"].default_value = 0.68
    return material


def _random_surface_position(rng: random.Random, radius: float) -> Vector:
    z = rng.uniform(-1.0, 1.0)
    angle = rng.uniform(0.0, math.tau)
    planar = math.sqrt(max(0.0, 1.0 - z * z))
    return Vector((planar * math.cos(angle), planar * math.sin(angle), z)) * radius


def _surface_direction(
    position: Vector,
    velocity: Vector,
    settings: FlowSettings,
    seed_offset: Vector,
) -> Vector:
    normal = position.normalized()
    sampled = noise_vector(position * settings.field_scale + seed_offset, noise_basis="PERLIN_ORIGINAL")
    tangent_noise = sampled - normal * sampled.dot(normal)

    around_axis = Vector((0.0, 0.0, 1.0)).cross(normal)
    if around_axis.length_squared < 1e-8:
        around_axis = Vector((1.0, 0.0, 0.0)).cross(normal)

    desired = tangent_noise * settings.noise_strength + around_axis * settings.orbit_strength
    desired -= normal * desired.dot(normal)
    if desired.length_squared < 1e-10:
        desired = around_axis
    desired.normalize()

    velocity -= normal * velocity.dot(normal)
    if velocity.length_squared < 1e-10:
        velocity = desired
    else:
        velocity.normalize()
    blended = velocity * settings.inertia + desired * (1.0 - settings.inertia)
    blended -= normal * blended.dot(normal)
    blended.normalize()
    return blended


def _mark_opacity(
    position: Vector,
    progress: float,
    phase: float,
    settings: FlowSettings,
    opacity_offset: Vector,
) -> float:
    if settings.opacity_mode == "UNIFORM":
        amount = 1.0
    elif settings.opacity_mode == "FADE_PATH":
        amount = math.sin(math.pi * progress) ** 0.55
    elif settings.opacity_mode == "PULSE":
        amount = 0.5 + 0.5 * math.sin(progress * math.tau * 5.0 + phase)
    else:
        sampled = noise(
            position * settings.opacity_scale + opacity_offset,
            noise_basis="PERLIN_ORIGINAL",
        )
        amount = max(0.0, min(1.0, sampled * 0.5 + 0.5))
    return settings.opacity_min + amount * (settings.opacity_max - settings.opacity_min)


def add_surface_mark(
    curve: bpy.types.Curve,
    position: Vector,
    tangent: Vector,
    material_index: int,
    length: float,
    width: float,
    surface_radius: float,
) -> None:
    half = tangent.normalized() * (length * 0.5)
    start = (position - half).normalized() * surface_radius
    end = (position + half).normalized() * surface_radius
    spline = curve.splines.new("POLY")
    spline.points.add(1)
    spline.material_index = material_index
    spline.points[0].co = (*start, 1.0)
    spline.points[1].co = (*end, 1.0)
    spline.points[0].radius = width
    spline.points[1].radius = width


def build_surface_paint(
    settings: FlowSettings,
    collection: bpy.types.Collection,
    materials: list[bpy.types.Material],
) -> bpy.types.Object:
    rng = random.Random(settings.seed)
    offset_rng = random.Random(settings.seed ^ 0x5F3759DF)
    seed_offset = Vector(tuple(offset_rng.uniform(-200, 200) for _ in range(3)))
    opacity_offset = Vector(tuple(offset_rng.uniform(-200, 200) for _ in range(3)))
    surface_radius = settings.canvas_radius + settings.trail_radius * 1.8

    curve = bpy.data.curves.new("Surface Paint Marks", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 1
    curve.bevel_depth = settings.trail_radius
    curve.bevel_resolution = 2
    curve.use_fill_caps = True
    for material in materials:
        curve.materials.append(material)

    obj = bpy.data.objects.new(curve.name, curve)
    _tag(obj)
    obj["flow_seed"] = settings.seed
    obj["role"] = "surface_paint"
    collection.objects.link(obj)

    bucket_count = max(2, settings.opacity_buckets)
    for agent_index in range(settings.agents):
        position = _random_surface_position(rng, settings.canvas_radius)
        normal = position.normalized()
        velocity = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
        velocity -= normal * velocity.dot(normal)
        if velocity.length_squared < 1e-10:
            velocity = Vector((0.0, 0.0, 1.0)).cross(normal)
        velocity.normalize()
        palette_index = rng.randrange(len(PALETTES.get(settings.palette, PALETTES["ELECTRIC"])))
        phase = rng.uniform(0.0, math.tau)

        for step_index in range(settings.steps):
            velocity = _surface_direction(position, velocity, settings, seed_offset)
            position = (position + velocity * settings.step_size).normalized() * settings.canvas_radius

            if step_index % max(1, settings.mark_spacing) != 0:
                continue
            if rng.random() > settings.paint_coverage:
                continue

            progress = step_index / max(1, settings.steps - 1)
            opacity = _mark_opacity(position, progress, phase, settings, opacity_offset)
            opacity_t = (opacity - settings.opacity_min) / max(
                1e-8,
                settings.opacity_max - settings.opacity_min,
            )
            bucket = max(0, min(bucket_count - 1, round(opacity_t * (bucket_count - 1))))
            material_index = palette_index * bucket_count + bucket
            mark_length = settings.mark_length * rng.uniform(0.72, 1.28)
            mark_width = rng.uniform(0.72, 1.25)
            add_surface_mark(
                curve,
                position,
                velocity,
                material_index,
                mark_length,
                mark_width,
                surface_radius,
            )

    return obj


def add_canvas(
    collection: bpy.types.Collection,
    settings: FlowSettings,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new("Flow Canvas")
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(
        bm,
        u_segments=96,
        v_segments=64,
        radius=settings.canvas_radius,
        calc_uvs=True,
    )
    bm.to_mesh(mesh)
    bm.free()
    for polygon in mesh.polygons:
        polygon.use_smooth = True

    canvas = bpy.data.objects.new("Flow Canvas", mesh)
    _tag(canvas)
    canvas["role"] = "canvas"
    collection.objects.link(canvas)
    canvas.data.materials.append(make_canvas_material())
    return canvas


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
    scene.frame_end = 1

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
    bucket_count = max(2, settings.opacity_buckets)
    materials = []
    for color_index, color in enumerate(palette):
        for bucket in range(bucket_count):
            opacity = settings.opacity_min + (bucket / (bucket_count - 1)) * (
                settings.opacity_max - settings.opacity_min
            )
            materials.append(
                make_paint_material(
                    f"Paint {color_index + 1:02d} opacity {bucket + 1:02d}",
                    color,
                    opacity,
                    settings,
                )
            )
    if settings.show_canvas:
        add_canvas(collection, settings)
    build_surface_paint(settings, collection, materials)
    add_camera(scene, collection, settings)
    add_stage(collection)
    scene.frame_set(1)
    scene["paint_model"] = "surface_marks"
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
