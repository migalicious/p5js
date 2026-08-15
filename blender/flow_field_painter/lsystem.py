"""Seeded three-dimensional L-system sculptures for Generative Art Lab."""

from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass

import bpy
from mathutils import Quaternion, Vector

from .generator import (
    GENERATOR_TAG,
    PALETTES,
    _tag,
    add_area_light,
    hex_rgba,
    look_at,
    remove_live_generation,
)


GENERATED_COLLECTION = "L-System Sculpture"
MAX_SYMBOLS = 200_000
MAX_SEGMENTS = 30_000

GRAMMARS = {
    "TREE": ("F", {"F": "F[+F]F[-F]F"}),
    "FERN": ("X", {"X": "F+[[X]-X]-F[-FX]+X", "F": "FF"}),
    "CORAL": ("F", {"F": "F[+F][-F]F[+F][-F]"}),
    "SNOWFLAKE": ("F++F++F", {"F": "F-F++F-F"}),
}


@dataclass(frozen=True)
class LSystemSettings:
    seed: int = 42
    preset: str = "TREE"
    iterations: int = 5
    branch_angle_deg: float = 25.0
    length_ratio: float = 0.68
    angle_randomness_deg: float = 8.0
    segment_length: float = 0.42
    spatial_spread_deg: float = 105.0
    branch_thickness: float = 0.075
    thickness_taper: float = 0.72
    palette: str = "GROVE"
    metallic: float = 0.2
    roughness: float = 0.42
    emission_strength: float = 0.08
    camera_lens: float = 58.0
    render_size: int = 768


def expand_grammar(settings: LSystemSettings) -> str:
    """Expand the selected p5.js grammar with a hard interactive-size limit."""
    axiom, rules = GRAMMARS.get(settings.preset, GRAMMARS["TREE"])
    result = axiom
    for _ in range(settings.iterations):
        result = "".join(rules.get(symbol, symbol) for symbol in result)
        if len(result) > MAX_SYMBOLS:
            raise ValueError(
                f"This recipe expands past {MAX_SYMBOLS:,} symbols; lower Iterations"
            )
    return result


def _planar_segments(
    program: str,
    settings: LSystemSettings,
) -> list[tuple[Vector, Vector, int]]:
    """Interpret the snowflake grammar in its original two-dimensional plane."""
    rng = random.Random(settings.seed)
    position = Vector((0.0, 0.0, 0.0))
    heading = 0.0
    angle = math.radians(settings.branch_angle_deg)
    segments: list[tuple[Vector, Vector, int]] = []
    stack: list[tuple[Vector, float]] = []

    for symbol in program:
        if symbol == "F":
            jitter = math.radians(rng.uniform(-settings.angle_randomness_deg, settings.angle_randomness_deg))
            direction = Vector((math.cos(heading + jitter), math.sin(heading + jitter), 0.0))
            end = position + direction * settings.segment_length
            segments.append((position.copy(), end.copy(), len(stack)))
            position = end
        elif symbol == "+":
            heading += angle
        elif symbol == "-":
            heading -= angle
        elif symbol == "[":
            stack.append((position.copy(), heading))
        elif symbol == "]" and stack:
            position, heading = stack.pop()
        if len(segments) > MAX_SEGMENTS:
            raise ValueError(f"This recipe creates over {MAX_SEGMENTS:,} branches; lower Iterations")
    return segments


def _spatial_segments(
    program: str,
    settings: LSystemSettings,
) -> list[tuple[Vector, Vector, int]]:
    """Interpret the original turtle commands with seeded three-dimensional turns."""
    rng = random.Random(settings.seed)
    position = Vector((0.0, 0.0, 0.0))
    orientation = Quaternion()
    depth = 0
    turn_index = 0
    segments: list[tuple[Vector, Vector, int]] = []
    stack: list[tuple[Vector, Quaternion, int]] = []
    base_angle = math.radians(settings.branch_angle_deg)

    for symbol in program:
        if symbol == "F":
            direction = orientation @ Vector((0.0, 0.0, 1.0))
            if settings.angle_randomness_deg > 0.0:
                tangent = orientation @ Vector((1.0, 0.0, 0.0))
                jitter = math.radians(
                    rng.uniform(-settings.angle_randomness_deg, settings.angle_randomness_deg)
                )
                direction.rotate(Quaternion(tangent, jitter))
            # The original 2D sketch scales all turtle steps together. In 3D we
            # let nesting taper length too, but gently enough that side growth
            # remains a visible part of the finished sculpture.
            length = settings.segment_length * settings.length_ratio ** (depth * 0.35)
            end = position + direction.normalized() * length
            segments.append((position.copy(), end.copy(), depth))
            position = end
        elif symbol in "+-":
            sign = 1.0 if symbol == "+" else -1.0
            random_angle = math.radians(
                rng.uniform(-settings.angle_randomness_deg, settings.angle_randomness_deg)
            )
            pitch = sign * (base_angle + random_angle)
            golden_turn = math.radians(137.507764)
            spread = settings.spatial_spread_deg / 180.0
            roll = sign * golden_turn * turn_index * spread
            roll += math.radians(rng.uniform(-settings.spatial_spread_deg * 0.18, settings.spatial_spread_deg * 0.18))
            orientation = orientation @ Quaternion(Vector((0.0, 0.0, 1.0)), roll)
            orientation = orientation @ Quaternion(Vector((0.0, 1.0, 0.0)), pitch)
            turn_index += 1
        elif symbol == "[":
            stack.append((position.copy(), orientation.copy(), depth))
            depth += 1
        elif symbol == "]" and stack:
            position, orientation, depth = stack.pop()
        if len(segments) > MAX_SEGMENTS:
            raise ValueError(f"This recipe creates over {MAX_SEGMENTS:,} branches; lower Iterations")
    return segments


def create_segments(settings: LSystemSettings) -> list[tuple[Vector, Vector, int]]:
    program = expand_grammar(settings)
    if settings.preset == "SNOWFLAKE":
        return _planar_segments(program, settings)
    return _spatial_segments(program, settings)


def _make_material(name: str, color_hex: str, settings: LSystemSettings) -> bpy.types.Material:
    color = hex_rgba(color_hex)
    material = bpy.data.materials.new(name)
    _tag(material)
    material.diffuse_color = color
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Metallic"].default_value = settings.metallic
    principled.inputs["Roughness"].default_value = settings.roughness
    principled.inputs["Coat Weight"].default_value = 0.16
    principled.inputs["Emission Color"].default_value = color
    principled.inputs["Emission Strength"].default_value = settings.emission_strength
    return material


def _build_curve(
    collection: bpy.types.Collection,
    segments: list[tuple[Vector, Vector, int]],
    settings: LSystemSettings,
) -> tuple[bpy.types.Object, Vector, float]:
    low = Vector((math.inf, math.inf, math.inf))
    high = Vector((-math.inf, -math.inf, -math.inf))
    for start, end, _depth in segments:
        low.x = min(low.x, start.x, end.x)
        low.y = min(low.y, start.y, end.y)
        low.z = min(low.z, start.z, end.z)
        high.x = max(high.x, start.x, end.x)
        high.y = max(high.y, start.y, end.y)
        high.z = max(high.z, start.z, end.z)
    center = (low + high) * 0.5
    raw_extent = max((high - low).x, (high - low).y, (high - low).z, 0.5)
    display_extent = 8.0
    display_scale = display_extent / raw_extent

    curve = bpy.data.curves.new("L-System Branches", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 1
    curve.bevel_depth = settings.branch_thickness
    curve.bevel_resolution = 3
    curve.use_fill_caps = True

    palette = PALETTES.get(settings.palette, PALETTES["GROVE"])
    for index, color in enumerate(palette):
        curve.materials.append(_make_material(f"Branch Color {index + 1}", color, settings))

    max_depth = max((depth for _, _, depth in segments), default=0)
    for start, end, depth in segments:
        start = (start - center) * display_scale
        end = (end - center) * display_scale
        spline = curve.splines.new("POLY")
        spline.points.add(1)
        spline.material_index = min(
            len(palette) - 1,
            1 + round(depth / max(1, max_depth) * (len(palette) - 2)),
        )
        spline.points[0].co = (*start, 1.0)
        spline.points[1].co = (*end, 1.0)
        spline.points[0].radius = max(0.08, settings.thickness_taper**depth)
        spline.points[1].radius = max(0.08, settings.thickness_taper ** (depth + 0.35))

    obj = bpy.data.objects.new(curve.name, curve)
    _tag(obj)
    obj["role"] = "lsystem_sculpture"
    obj["seed"] = settings.seed
    obj["preset"] = settings.preset
    obj["segment_count"] = len(segments)
    collection.objects.link(obj)
    return obj, Vector((0.0, 0.0, 0.0)), display_extent


def _configure_scene(scene: bpy.types.Scene, settings: LSystemSettings) -> None:
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
    background.inputs["Color"].default_value = (0.003, 0.005, 0.012, 1.0)
    background.inputs["Strength"].default_value = 0.1
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene["generator"] = GENERATOR_TAG
    scene["recipe"] = json.dumps({"generator_type": "LSYSTEM", **asdict(settings)}, sort_keys=True)


def _add_camera(
    scene: bpy.types.Scene,
    collection: bpy.types.Collection,
    settings: LSystemSettings,
    extent: float,
) -> bpy.types.Object:
    camera_data = bpy.data.cameras.new("L-System Camera")
    camera_data.lens = settings.camera_lens
    camera_data.sensor_width = 36.0
    camera = bpy.data.objects.new(camera_data.name, camera_data)
    _tag(camera)
    collection.objects.link(camera)
    distance = max(3.2, extent * 1.75)
    if settings.preset == "SNOWFLAKE":
        camera.location = (0.0, 0.0, distance)
    else:
        camera.location = (distance * 0.54, -distance * 0.75, distance * 0.39)
    look_at(camera, Vector((0.0, 0.0, 0.0)))
    scene.camera = camera
    return camera


def _add_stage(collection: bpy.types.Collection, extent: float) -> None:
    scale = max(1.0, extent / 5.0)
    add_area_light(collection, "L-System Key", (5.5, -4.0, 9.0), 1200 * scale, (0.72, 0.8, 1.0), 5.5 * scale)
    add_area_light(collection, "L-System Rim", (-6.0, 2.5, 5.0), 950 * scale, (1.0, 0.35, 0.5), 4.0 * scale)
    add_area_light(collection, "L-System Fill", (1.0, 7.0, -1.0), 700 * scale, (0.3, 0.8, 1.0), 3.5 * scale)


def build(scene: bpy.types.Scene, settings: LSystemSettings) -> bpy.types.Collection:
    segments = create_segments(settings)
    if not segments:
        raise ValueError("This L-system recipe produced no drawable branches")
    remove_live_generation(scene)
    _configure_scene(scene, settings)

    collection = bpy.data.collections.new(GENERATED_COLLECTION)
    _tag(collection)
    collection["role"] = "live"
    collection["generator_type"] = "LSYSTEM"
    scene.collection.children.link(collection)

    sculpture, target, extent = _build_curve(collection, segments, settings)
    _add_camera(scene, collection, settings, extent)
    _add_stage(collection, extent)
    scene.frame_set(1)
    scene["art_generator_type"] = "LSYSTEM"
    scene["flow_field_seed"] = settings.seed
    scene["flow_field_has_generation"] = True
    scene["lsystem_segment_count"] = int(sculpture["segment_count"])
    return collection
