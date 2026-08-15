"""Dense strange-attractor point art for Generative Art Lab."""

from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass

import bpy
from mathutils import Vector

from .generator import GENERATOR_TAG, PALETTES, _tag, add_area_light, hex_rgba, look_at, remove_live_generation


GENERATED_COLLECTION = "Strange Attractor Points"


@dataclass(frozen=True)
class AttractorSettings:
    seed: int = 42
    attractor_type: str = "CLIFFORD"
    iterations: int = 180_000
    a: float = -1.7
    b: float = 1.8
    c: float = -1.9
    d: float = 0.4
    color_mode: str = "POSITION"
    depth_mode: str = "FLAT"
    depth_amount: float = 1.8
    point_size: float = 0.018
    opacity: float = 0.16
    palette: str = "ELECTRIC"
    metallic: float = 0.1
    roughness: float = 0.48
    emission_strength: float = 0.35
    camera_lens: float = 54.0
    render_size: int = 768


def _next_clifford(x: float, y: float, settings: AttractorSettings) -> tuple[float, float]:
    return (
        math.sin(settings.a * y) + settings.c * math.cos(settings.a * x),
        math.sin(settings.b * x) + settings.d * math.cos(settings.b * y),
    )


def _next_dejong(x: float, y: float, settings: AttractorSettings) -> tuple[float, float]:
    return (
        math.sin(settings.a * y) - math.cos(settings.b * x),
        math.sin(settings.c * x) - math.cos(settings.d * y),
    )


def calculate_orbit(settings: AttractorSettings) -> list[tuple[float, float, float, float]]:
    """Return x, y, speed, and normalized age using the original p5.js equations."""
    rng = random.Random(settings.seed)
    points: list[tuple[float, float, float, float]] = []
    if settings.attractor_type == "LORENZ":
        x = 0.1 + rng.uniform(-0.02, 0.02)
        y = rng.uniform(-0.02, 0.02)
        z = rng.uniform(-0.02, 0.02)
        dt = 0.005
        sigma = settings.a * 3.0 + 10.0
        rho = settings.b * 14.0 + 28.0
        beta = settings.c * 0.5 + 2.67
        limit = min(settings.iterations, 500_000)
        for index in range(limit + 1_000):
            dx = sigma * (y - x)
            dy = x * (rho - z) - y
            dz = x * y - beta * z
            x += dx * dt
            y += dy * dt
            z += dz * dt
            if index >= 1_000:
                speed = math.sqrt(dx * dx + dy * dy + dz * dz) * dt
                age = (index - 1_000) / max(1, limit - 1)
                points.append((x, z, speed, age))
        return points

    x = 0.1 + rng.uniform(-0.2, 0.2)
    y = 0.1 + rng.uniform(-0.2, 0.2)
    advance = _next_dejong if settings.attractor_type == "DEJONG" else _next_clifford
    for index in range(settings.iterations + 1_000):
        new_x, new_y = advance(x, y, settings)
        speed = math.hypot(new_x - x, new_y - y)
        x, y = new_x, new_y
        if index >= 1_000:
            age = (index - 1_000) / max(1, settings.iterations - 1)
            points.append((x, y, speed, age))
    return points


def _normalize_and_bucket(
    orbit: list[tuple[float, float, float, float]],
    settings: AttractorSettings,
    bucket_count: int,
) -> list[list[tuple[float, float, float]]]:
    if not orbit:
        raise ValueError("This attractor recipe produced no points")
    min_x = min(point[0] for point in orbit)
    max_x = max(point[0] for point in orbit)
    min_y = min(point[1] for point in orbit)
    max_y = max(point[1] for point in orbit)
    min_speed = min(point[2] for point in orbit)
    max_speed = max(point[2] for point in orbit)
    span = max(max_x - min_x, max_y - min_y, 1e-8)
    center_x = (min_x + max_x) * 0.5
    center_y = (min_y + max_y) * 0.5
    phase = random.Random(settings.seed ^ 0xA771AC7).uniform(0.0, math.tau)
    buckets: list[list[tuple[float, float, float]]] = [[] for _ in range(bucket_count)]

    for x, y, speed, age in orbit:
        normalized_x = (x - center_x) / span * 8.0
        normalized_y = (y - center_y) / span * 8.0
        speed_amount = (speed - min_speed) / max(1e-8, max_speed - min_speed)
        if settings.depth_mode == "ITERATION":
            z = (age - 0.5) * settings.depth_amount
        elif settings.depth_mode == "SPEED":
            z = (speed_amount - 0.5) * settings.depth_amount
        elif settings.depth_mode == "WAVE":
            polar = math.atan2(normalized_y, normalized_x)
            z = math.sin(age * math.tau * 8.0 + polar * 3.0 + phase) * settings.depth_amount * 0.5
        else:
            z = 0.0

        if settings.color_mode == "ITERATION":
            color_amount = age
        elif settings.color_mode == "SPEED":
            color_amount = speed_amount
        elif settings.color_mode == "POSITION":
            color_amount = ((normalized_x + 4.0) / 8.0 + (normalized_y + 4.0) / 8.0) * 0.5
        else:
            color_amount = 0.5
        bucket = max(0, min(bucket_count - 1, int(color_amount * bucket_count)))
        buckets[bucket].append((normalized_x, normalized_y, z))
    return buckets


def _make_material(name: str, color_hex: str, settings: AttractorSettings) -> bpy.types.Material:
    color = hex_rgba(color_hex)
    rgba = (*color[:3], settings.opacity)
    material = bpy.data.materials.new(name)
    _tag(material)
    material.diffuse_color = rgba
    material.surface_render_method = "DITHERED"
    material.use_transparency_overlap = False
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Metallic"].default_value = settings.metallic
    principled.inputs["Roughness"].default_value = settings.roughness
    principled.inputs["Emission Color"].default_value = color
    principled.inputs["Emission Strength"].default_value = settings.emission_strength
    principled.inputs["Alpha"].default_value = settings.opacity
    return material


def _add_point_object(
    collection: bpy.types.Collection,
    points: list[tuple[float, float, float]],
    index: int,
    material: bpy.types.Material,
    settings: AttractorSettings,
) -> bpy.types.Object | None:
    if not points:
        return None
    mesh = bpy.data.meshes.new(f"Attractor Points {index + 1}")
    _tag(mesh)
    mesh.from_pydata(points, [], [])
    mesh.update()
    obj = bpy.data.objects.new(mesh.name, mesh)
    _tag(obj)
    obj["role"] = "attractor_points"
    obj["point_count"] = len(points)
    collection.objects.link(obj)
    obj.data.materials.append(material)

    modifier = obj.modifiers.new("Render Points", "NODES")
    node_group = bpy.data.node_groups.new(f"Attractor Point Style {index + 1}", "GeometryNodeTree")
    _tag(node_group)
    modifier.node_group = node_group
    node_group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    node_group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    group_input = node_group.nodes.new("NodeGroupInput")
    to_points = node_group.nodes.new("GeometryNodeMeshToPoints")
    set_material = node_group.nodes.new("GeometryNodeSetMaterial")
    group_output = node_group.nodes.new("NodeGroupOutput")
    to_points.mode = "VERTICES"
    to_points.inputs["Radius"].default_value = settings.point_size
    set_material.inputs["Material"].default_value = material
    node_group.links.new(group_input.outputs["Geometry"], to_points.inputs["Mesh"])
    node_group.links.new(to_points.outputs["Points"], set_material.inputs["Geometry"])
    node_group.links.new(set_material.outputs["Geometry"], group_output.inputs["Geometry"])
    return obj


def _configure_scene(scene: bpy.types.Scene, settings: AttractorSettings) -> None:
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
    world = bpy.data.worlds.get("Generative Art World") or bpy.data.worlds.new("Generative Art World")
    _tag(world)
    scene.world = world
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.002, 0.003, 0.009, 1.0)
    background.inputs["Strength"].default_value = 0.08
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene["generator"] = GENERATOR_TAG
    scene["recipe"] = json.dumps({"generator_type": "ATTRACTOR", **asdict(settings)}, sort_keys=True)


def _add_camera(scene: bpy.types.Scene, collection: bpy.types.Collection, settings: AttractorSettings) -> None:
    data = bpy.data.cameras.new("Attractor Camera")
    data.lens = settings.camera_lens
    data.sensor_width = 36.0
    camera = bpy.data.objects.new(data.name, data)
    _tag(camera)
    collection.objects.link(camera)
    if settings.depth_mode == "FLAT" or settings.depth_amount == 0.0:
        camera.location = (0.0, 0.0, 13.8)
    else:
        camera.location = (5.5, -8.5, 10.0)
    look_at(camera, Vector((0.0, 0.0, 0.0)))
    scene.camera = camera


def _add_stage(collection: bpy.types.Collection) -> None:
    add_area_light(collection, "Attractor Key", (5.5, -4.0, 9.0), 900, (0.65, 0.76, 1.0), 5.0)
    add_area_light(collection, "Attractor Rim", (-5.0, 2.5, 6.0), 700, (1.0, 0.3, 0.55), 4.0)


def build(scene: bpy.types.Scene, settings: AttractorSettings) -> bpy.types.Collection:
    orbit = calculate_orbit(settings)
    palette = PALETTES.get(settings.palette, PALETTES["ELECTRIC"])
    buckets = _normalize_and_bucket(orbit, settings, len(palette))
    remove_live_generation(scene)
    _configure_scene(scene, settings)

    collection = bpy.data.collections.new(GENERATED_COLLECTION)
    _tag(collection)
    collection["role"] = "live"
    collection["generator_type"] = "ATTRACTOR"
    collection["point_count"] = len(orbit)
    scene.collection.children.link(collection)

    for index, (color, points) in enumerate(zip(palette, buckets, strict=True)):
        material = _make_material(f"Attractor Color {index + 1}", color, settings)
        _add_point_object(collection, points, index, material, settings)
    _add_camera(scene, collection, settings)
    _add_stage(collection)
    scene.frame_set(1)
    scene["art_generator_type"] = "ATTRACTOR"
    scene["flow_field_seed"] = settings.seed
    scene["flow_field_has_generation"] = True
    scene["attractor_point_count"] = len(orbit)
    return collection
