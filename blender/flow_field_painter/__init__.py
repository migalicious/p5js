"""Beginner-facing controls for a collection of seeded generative art tools."""

from __future__ import annotations

import json
import random
from dataclasses import asdict
from pathlib import Path

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup

from .generator import FlowSettings, build as build_flow, freeze_current_frame
from .lsystem import LSystemSettings, build as build_lsystem


bl_info = {
    "name": "Generative Art Lab",
    "author": "migalicious",
    "version": (0, 4, 0),
    "blender": (5, 2, 0),
    "location": "3D Viewport > Sidebar > Generative Art",
    "description": "Tweak and render seeded flow paintings and L-system sculptures",
    "category": "3D View",
}


PALETTE_ITEMS = (
    ("ELECTRIC", "Electric", "Purple, turquoise, yellow, and coral"),
    ("EMBER", "Ember", "Deep red, orange, gold, and cream"),
    ("TIDAL", "Tidal", "Deep blue through bright cyan"),
    ("GROVE", "Grove", "Forest green through pale yellow-green"),
    ("MONO", "Monochrome", "Black, gray, and white"),
)

GENERATOR_ITEMS = (
    ("FLOW", "Surface Flow Painter", "Deposit disconnected marks along invisible paths on an object"),
    ("LSYSTEM", "L-System Sculpture", "Grow seeded branching structures from rewriting rules"),
)

PRESET_ITEMS = (
    ("CALM", "Calm Currents", "Broad, smooth paths with soft fading marks"),
    ("BRAIDED", "Braided Orbit", "Long coordinated strokes wrapping around the canvas"),
    ("STORM", "Broken Storm", "Shorter, restless marks with turbulent motion"),
    ("CONSTELLATION", "Constellation", "Sparse points and tiny dashes with open space"),
)

OPACITY_ITEMS = (
    ("UNIFORM", "Even", "Every paint mark has the same opacity"),
    ("FADE_PATH", "Fade Along Paths", "Marks fade near the beginning and end of each guide path"),
    ("FIELD", "Clouds", "A second noise field creates spatial patches of strong and faint paint"),
    ("PULSE", "Pulse", "Opacity rises and falls repeatedly along each guide path"),
)

LSYSTEM_PRESET_ITEMS = (
    ("TREE", "Tree", "Repeated trunk and paired branches"),
    ("FERN", "Fern", "Nested asymmetric fronds"),
    ("CORAL", "Coral", "Dense repeated branching in many directions"),
    ("SNOWFLAKE", "Snowflake", "Planar Koch snowflake from the original sketch"),
)


class FLOWFIELD_PG_settings(PropertyGroup):
    generator_type: EnumProperty(
        name="Generator",
        description="Choose which kind of generative artwork these controls build",
        items=GENERATOR_ITEMS,
        default="FLOW",
    )
    preset: EnumProperty(name="Starting Style", items=PRESET_ITEMS, default="CALM")
    seed: IntProperty(
        name="Seed",
        description="The repeatable identity of this painting",
        default=42,
        min=0,
        max=999_999,
    )
    agents: IntProperty(
        name="Painters",
        description="How many invisible brushes travel over the canvas surface",
        default=70,
        min=5,
        max=800,
    )
    steps: IntProperty(
        name="Path Length",
        description="How far each invisible brush travels before stopping",
        default=260,
        min=20,
        max=1200,
    )
    field_scale: FloatProperty(
        name="Pattern Scale",
        description="Low values make broad bends; high values make smaller, busier turns",
        default=0.22,
        min=0.03,
        max=1.5,
        precision=3,
    )
    step_size: FloatProperty(
        name="Travel Speed",
        description="Distance an invisible brush advances on each step",
        default=0.065,
        min=0.005,
        max=0.3,
        precision=3,
    )
    inertia: FloatProperty(
        name="Flow Smoothness",
        description="Higher values make graceful paths; lower values turn more abruptly",
        default=0.93,
        min=0.0,
        max=0.98,
        subtype="FACTOR",
    )
    noise_strength: FloatProperty(
        name="Wander",
        description="How strongly paths follow irregular noise instead of circling",
        default=0.85,
        min=0.0,
        max=3.0,
    )
    orbit_strength: FloatProperty(
        name="Around the Canvas",
        description="How strongly paths wrap around the canvas in a shared direction",
        default=0.65,
        min=-2.0,
        max=2.0,
    )
    trail_radius: FloatProperty(
        name="Brush Width",
        description="Thickness of each disconnected paint mark",
        default=0.035,
        min=0.002,
        max=0.2,
        precision=3,
    )
    canvas_radius: FloatProperty(
        name="Canvas Size",
        description="Radius of the spherical object being painted",
        default=4.0,
        min=1.0,
        max=12.0,
    )
    show_canvas: BoolProperty(
        name="Show Canvas Object",
        description="Render the dark object beneath the paint marks",
        default=True,
    )
    mark_spacing: IntProperty(
        name="Mark Spacing",
        description="Steps between deposited marks; higher values leave more empty space",
        default=4,
        min=1,
        max=30,
    )
    mark_length: FloatProperty(
        name="Stroke Length",
        description="Length of each separate dash; very low values look like dots",
        default=0.16,
        min=0.005,
        max=0.8,
        precision=3,
    )
    paint_coverage: FloatProperty(
        name="Mark Chance",
        description="Chance that a passing brush actually deposits a mark",
        default=0.82,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )
    opacity_mode: EnumProperty(name="Opacity Pattern", items=OPACITY_ITEMS, default="FADE_PATH")
    opacity_min: FloatProperty(
        name="Faintest Mark",
        default=0.15,
        min=0.02,
        max=1.0,
        subtype="FACTOR",
    )
    opacity_max: FloatProperty(
        name="Strongest Mark",
        default=0.95,
        min=0.02,
        max=1.0,
        subtype="FACTOR",
    )
    opacity_scale: FloatProperty(
        name="Opacity Patch Size",
        description="Size of faint and strong regions when Opacity Pattern is Clouds",
        default=0.72,
        min=0.05,
        max=3.0,
    )
    palette: EnumProperty(name="Palette", items=PALETTE_ITEMS, default="ELECTRIC")
    metallic: FloatProperty(name="Metallic", default=0.28, min=0.0, max=1.0, subtype="FACTOR")
    roughness: FloatProperty(name="Roughness", default=0.3, min=0.0, max=1.0, subtype="FACTOR")
    emission_strength: FloatProperty(
        name="Glow",
        description="Light emitted by the trails themselves",
        default=0.14,
        min=0.0,
        max=5.0,
    )
    camera_azimuth: FloatProperty(
        name="Camera Around (deg)",
        default=50.3,
        min=-180.0,
        max=180.0,
    )
    camera_elevation: FloatProperty(
        name="Camera Height (deg)",
        default=31.5,
        min=-80.0,
        max=80.0,
    )
    camera_distance: FloatProperty(name="Camera Distance", default=13.8, min=3.0, max=50.0)
    camera_lens: FloatProperty(name="Camera Lens", default=57.0, min=18.0, max=150.0)
    render_size: IntProperty(
        name="Image Size",
        description="Width and height of the square PNG render",
        default=768,
        min=128,
        max=4096,
    )
    output_dir: StringProperty(
        name="Save To",
        description="Folder for PNG renders and recipes; blank means a renders folder beside the Blender file",
        default="",
        subtype="DIR_PATH",
    )
    lsystem_preset: EnumProperty(name="Growth Rule", items=LSYSTEM_PRESET_ITEMS, default="TREE")
    lsystem_iterations: IntProperty(
        name="Growth Rounds",
        description="How many times the rewriting rule expands; each round can multiply the branch count",
        default=5,
        min=1,
        max=7,
    )
    lsystem_angle: FloatProperty(
        name="Branch Angle",
        description="How sharply new growth turns away from its parent",
        default=25.0,
        min=2.0,
        max=90.0,
    )
    lsystem_length_ratio: FloatProperty(
        name="Branch Shrink",
        description="Length retained at each deeper nesting level",
        default=0.68,
        min=0.2,
        max=0.95,
        subtype="FACTOR",
    )
    lsystem_randomness: FloatProperty(
        name="Angle Wander",
        description="Seeded irregularity added to branch directions",
        default=8.0,
        min=0.0,
        max=40.0,
    )
    lsystem_segment_length: FloatProperty(
        name="Growth Step",
        description="Length of one forward turtle step",
        default=0.42,
        min=0.02,
        max=2.0,
    )
    lsystem_spatial_spread: FloatProperty(
        name="3D Spread",
        description="How much branches twist around the trunk instead of staying flat",
        default=105.0,
        min=0.0,
        max=180.0,
    )
    lsystem_thickness: FloatProperty(
        name="Branch Width",
        description="Thickness of the root branches",
        default=0.075,
        min=0.005,
        max=0.35,
        precision=3,
    )
    lsystem_taper: FloatProperty(
        name="Thickness Taper",
        description="Width retained at each deeper branch level",
        default=0.72,
        min=0.25,
        max=1.0,
        subtype="FACTOR",
    )
    lsystem_camera_lens: FloatProperty(name="Sculpture Camera Lens", default=58.0, min=18.0, max=150.0)
    status: StringProperty(name="Status", default="Ready for a first generation")


def flow_settings_from_scene(scene: bpy.types.Scene) -> FlowSettings:
    props = scene.flow_field_settings
    return FlowSettings(
        seed=props.seed,
        agents=props.agents,
        steps=props.steps,
        field_scale=props.field_scale,
        step_size=props.step_size,
        inertia=props.inertia,
        noise_strength=props.noise_strength,
        orbit_strength=props.orbit_strength,
        trail_radius=props.trail_radius,
        canvas_radius=props.canvas_radius,
        mark_spacing=props.mark_spacing,
        mark_length=props.mark_length,
        paint_coverage=props.paint_coverage,
        opacity_mode=props.opacity_mode,
        opacity_min=min(props.opacity_min, props.opacity_max),
        opacity_max=max(props.opacity_min, props.opacity_max),
        opacity_scale=props.opacity_scale,
        show_canvas=props.show_canvas,
        palette=props.palette,
        metallic=props.metallic,
        roughness=props.roughness,
        emission_strength=props.emission_strength,
        camera_azimuth=props.camera_azimuth,
        camera_elevation=props.camera_elevation,
        camera_distance=props.camera_distance,
        camera_lens=props.camera_lens,
        render_size=props.render_size,
    )


def lsystem_settings_from_scene(scene: bpy.types.Scene) -> LSystemSettings:
    props = scene.flow_field_settings
    return LSystemSettings(
        seed=props.seed,
        preset=props.lsystem_preset,
        iterations=props.lsystem_iterations,
        branch_angle_deg=props.lsystem_angle,
        length_ratio=props.lsystem_length_ratio,
        angle_randomness_deg=props.lsystem_randomness,
        segment_length=props.lsystem_segment_length,
        spatial_spread_deg=props.lsystem_spatial_spread,
        branch_thickness=props.lsystem_thickness,
        thickness_taper=props.lsystem_taper,
        palette=props.palette,
        metallic=props.metallic,
        roughness=props.roughness,
        emission_strength=props.emission_strength,
        camera_lens=props.lsystem_camera_lens,
        render_size=props.render_size,
    )


def settings_from_scene(scene: bpy.types.Scene) -> FlowSettings | LSystemSettings:
    if scene.flow_field_settings.generator_type == "LSYSTEM":
        return lsystem_settings_from_scene(scene)
    return flow_settings_from_scene(scene)


def set_view_to_camera(context: bpy.types.Context) -> None:
    screen = context.screen
    if screen is None:
        return
    for area in screen.areas:
        if area.type == "VIEW_3D":
            area.spaces.active.region_3d.view_perspective = "CAMERA"


def generate_artwork(context: bpy.types.Context) -> None:
    scene = context.scene
    props = scene.flow_field_settings
    settings = settings_from_scene(scene)
    if props.generator_type == "LSYSTEM":
        build_lsystem(scene, settings)
        noun = "sculpture"
    else:
        build_flow(scene, settings)
        noun = "painting"
    scene["flow_field_seed"] = props.seed
    scene["flow_field_has_generation"] = True
    scene.frame_set(1)
    set_view_to_camera(context)
    props.status = f"Seed {props.seed} {noun} is complete"


def generate_full_painting(context: bpy.types.Context) -> None:
    """Backward-compatible entry point used by the starter-scene script."""
    generate_artwork(context)


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for number in range(2, 10_000):
        candidate = path.with_name(f"{path.stem}_{number:02d}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not choose a unique filename near {path}")


def apply_flow_preset(props: FLOWFIELD_PG_settings) -> None:
    if props.preset == "BRAIDED":
        values = {
            "agents": 48,
            "steps": 420,
            "field_scale": 0.18,
            "step_size": 0.06,
            "inertia": 0.965,
            "noise_strength": 0.68,
            "orbit_strength": 0.92,
            "mark_spacing": 3,
            "mark_length": 0.22,
            "paint_coverage": 0.9,
            "trail_radius": 0.026,
            "opacity_mode": "PULSE",
            "opacity_min": 0.12,
            "opacity_max": 0.95,
        }
    elif props.preset == "STORM":
        values = {
            "agents": 120,
            "steps": 300,
            "field_scale": 0.58,
            "step_size": 0.075,
            "inertia": 0.74,
            "noise_strength": 1.65,
            "orbit_strength": 0.18,
            "mark_spacing": 5,
            "mark_length": 0.085,
            "paint_coverage": 0.62,
            "trail_radius": 0.03,
            "opacity_mode": "FIELD",
            "opacity_min": 0.08,
            "opacity_max": 0.88,
        }
    elif props.preset == "CONSTELLATION":
        values = {
            "agents": 90,
            "steps": 220,
            "field_scale": 0.4,
            "step_size": 0.085,
            "inertia": 0.84,
            "noise_strength": 1.15,
            "orbit_strength": 0.38,
            "mark_spacing": 9,
            "mark_length": 0.012,
            "paint_coverage": 0.46,
            "trail_radius": 0.055,
            "opacity_mode": "FIELD",
            "opacity_min": 0.2,
            "opacity_max": 1.0,
        }
    else:
        values = {
            "agents": 70,
            "steps": 260,
            "field_scale": 0.22,
            "step_size": 0.065,
            "inertia": 0.93,
            "noise_strength": 0.85,
            "orbit_strength": 0.65,
            "mark_spacing": 4,
            "mark_length": 0.16,
            "paint_coverage": 0.82,
            "trail_radius": 0.035,
            "opacity_mode": "FADE_PATH",
            "opacity_min": 0.15,
            "opacity_max": 0.95,
        }
    for name, value in values.items():
        setattr(props, name, value)


def apply_lsystem_preset(props: FLOWFIELD_PG_settings) -> None:
    if props.lsystem_preset == "FERN":
        values = {
            "lsystem_iterations": 5,
            "lsystem_angle": 22.0,
            "lsystem_length_ratio": 0.65,
            "lsystem_randomness": 3.0,
            "lsystem_segment_length": 0.28,
            "lsystem_spatial_spread": 72.0,
            "lsystem_thickness": 0.055,
            "lsystem_taper": 0.76,
            "palette": "GROVE",
        }
    elif props.lsystem_preset == "CORAL":
        values = {
            "lsystem_iterations": 4,
            "lsystem_angle": 28.0,
            "lsystem_length_ratio": 0.70,
            "lsystem_randomness": 12.0,
            "lsystem_segment_length": 0.30,
            "lsystem_spatial_spread": 132.0,
            "lsystem_thickness": 0.06,
            "lsystem_taper": 0.73,
            "palette": "EMBER",
        }
    elif props.lsystem_preset == "SNOWFLAKE":
        values = {
            "lsystem_iterations": 4,
            "lsystem_angle": 60.0,
            "lsystem_length_ratio": 0.33,
            "lsystem_randomness": 0.0,
            "lsystem_segment_length": 0.15,
            "lsystem_spatial_spread": 0.0,
            "lsystem_thickness": 0.035,
            "lsystem_taper": 1.0,
            "palette": "TIDAL",
        }
    else:
        values = {
            "lsystem_iterations": 5,
            "lsystem_angle": 25.0,
            "lsystem_length_ratio": 0.68,
            "lsystem_randomness": 8.0,
            "lsystem_segment_length": 0.42,
            "lsystem_spatial_spread": 105.0,
            "lsystem_thickness": 0.075,
            "lsystem_taper": 0.72,
            "palette": "GROVE",
        }
    for name, value in values.items():
        setattr(props, name, value)


def apply_preset(props: FLOWFIELD_PG_settings) -> None:
    if props.generator_type == "LSYSTEM":
        apply_lsystem_preset(props)
    else:
        apply_flow_preset(props)


class FLOWFIELD_OT_apply_preset(Operator):
    bl_idname = "flow_field.apply_preset"
    bl_label = "Apply Preset & Generate"
    bl_description = "Load a curated group of understandable settings and generate the full result"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        apply_preset(context.scene.flow_field_settings)
        return FLOWFIELD_OT_generate.execute(self, context)


class FLOWFIELD_OT_generate(Operator):
    bl_idname = "flow_field.generate"
    bl_label = "Generate Full Artwork"
    bl_description = "Rebuild the complete artwork from these controls"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        try:
            generate_full_painting(context)
        except Exception as exc:
            context.scene.flow_field_settings.status = f"Generation failed: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "Complete generative artwork built")
        return {"FINISHED"}


class FLOWFIELD_OT_new_seed(Operator):
    bl_idname = "flow_field.new_seed"
    bl_label = "New Seed"
    bl_description = "Choose a fresh seed and rebuild the complete artwork"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        context.scene.flow_field_settings.seed = random.SystemRandom().randint(0, 999_999)
        return FLOWFIELD_OT_generate.execute(self, context)


class FLOWFIELD_OT_mutate(Operator):
    bl_idname = "flow_field.mutate"
    bl_label = "Mutate Knobs"
    bl_description = "Nudge several understandable controls while keeping the current seed"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        props = context.scene.flow_field_settings
        rng = random.Random(props.seed + context.scene.frame_current * 7919)
        if props.generator_type == "LSYSTEM":
            props.lsystem_angle = max(2.0, min(90.0, props.lsystem_angle + rng.uniform(-6.0, 6.0)))
            props.lsystem_length_ratio = max(
                0.2, min(0.95, props.lsystem_length_ratio + rng.uniform(-0.07, 0.07))
            )
            props.lsystem_randomness = max(
                0.0, min(40.0, props.lsystem_randomness + rng.uniform(-4.0, 4.0))
            )
            props.lsystem_spatial_spread = max(
                0.0, min(180.0, props.lsystem_spatial_spread + rng.uniform(-20.0, 20.0))
            )
            props.lsystem_taper = max(0.25, min(1.0, props.lsystem_taper + rng.uniform(-0.07, 0.07)))
        else:
            props.field_scale = max(0.03, min(1.5, props.field_scale * rng.uniform(0.78, 1.22)))
            props.inertia = max(0.0, min(0.98, props.inertia + rng.uniform(-0.08, 0.08)))
            props.orbit_strength = max(-2.0, min(2.0, props.orbit_strength + rng.uniform(-0.22, 0.22)))
            props.mark_spacing = max(1, min(30, props.mark_spacing + rng.choice((-1, 0, 1))))
            props.mark_length = max(0.005, min(0.8, props.mark_length * rng.uniform(0.8, 1.25)))
            props.paint_coverage = max(0.05, min(1.0, props.paint_coverage + rng.uniform(-0.12, 0.12)))
        return FLOWFIELD_OT_generate.execute(self, context)


class FLOWFIELD_OT_freeze(Operator):
    bl_idname = "flow_field.freeze"
    bl_label = "Make Mesh Copy"
    bl_description = "Preserve a converted mesh copy while leaving the editable generated curves intact"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(context.scene.get("flow_field_has_generation"))

    def execute(self, context: bpy.types.Context) -> set[str]:
        if context.screen is not None and context.screen.is_animation_playing:
            bpy.ops.screen.animation_cancel(restore_frame=False)
        try:
            capture = freeze_current_frame(context.scene, context.evaluated_depsgraph_get())
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        context.scene.flow_field_settings.status = f"Saved mesh copy {capture.name}"
        self.report({"INFO"}, f"Mesh copy saved as {capture.name}")
        return {"FINISHED"}


class FLOWFIELD_OT_render(Operator):
    bl_idname = "flow_field.render"
    bl_label = "Render PNG"
    bl_description = "Render the full artwork and save its exact recipe"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(context.scene.get("flow_field_has_generation"))

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        props = scene.flow_field_settings
        if context.screen is not None and context.screen.is_animation_playing:
            bpy.ops.screen.animation_cancel(restore_frame=False)

        try:
            if props.output_dir.strip():
                output_dir = Path(bpy.path.abspath(props.output_dir)).resolve()
            elif bpy.data.filepath:
                output_dir = Path(bpy.data.filepath).resolve().parent / "renders"
            else:
                output_dir = Path(bpy.app.tempdir).resolve() / "flow_field_renders"
            output_dir.mkdir(parents=True, exist_ok=True)
            kind = "lsystem" if props.generator_type == "LSYSTEM" else "surface_paint"
            stem = f"{kind}_seed_{props.seed:06d}"
            render_path = unique_path(output_dir / f"{stem}.png")
            recipe_path = render_path.with_suffix(".json")
            settings = settings_from_scene(scene)
            recipe = {"generator_type": props.generator_type, **asdict(settings)}
            recipe_path.write_text(json.dumps(recipe, indent=2) + "\n", encoding="utf-8")
            scene.render.filepath = str(render_path)
            bpy.ops.render.render(write_still=True)
        except Exception as exc:
            props.status = f"Render failed: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        scene["flow_field_last_render"] = str(render_path)
        props.status = f"Rendered full artwork to {render_path.name}"
        self.report({"INFO"}, f"Saved {render_path}")
        return {"FINISHED"}


class FLOWFIELD_PT_main(Panel):
    bl_idname = "FLOWFIELD_PT_main"
    bl_label = "Generative Art Lab"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Generative Art"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        scene = context.scene
        props = scene.flow_field_settings
        has_generation = bool(scene.get("flow_field_has_generation"))

        intro = layout.box()
        intro.prop(props, "generator_type")
        if props.generator_type == "LSYSTEM":
            intro.label(text="Rules grow a complete branching sculpture", icon="INFO")
        else:
            intro.label(text="Invisible paths deposit separate paint marks", icon="INFO")
        intro.label(text="Every Generate makes the full result")

        choose = layout.box()
        choose.label(text="1. Start from something understandable")
        if props.generator_type == "LSYSTEM":
            choose.prop(props, "lsystem_preset")
        else:
            choose.prop(props, "preset")
        choose.operator("flow_field.apply_preset", icon="PRESET")
        choose.prop(props, "seed")
        row = choose.row(align=True)
        row.operator("flow_field.new_seed", text="New Seed", icon="FILE_REFRESH")
        row.operator("flow_field.mutate", text="Mutate", icon="MOD_NOISE")

        shape = layout.box()
        if props.generator_type == "LSYSTEM":
            shape.label(text="2. Adjust the visible growth")
            shape.prop(props, "lsystem_iterations")
            shape.prop(props, "lsystem_angle")
            shape.prop(props, "lsystem_spatial_spread")
            shape.prop(props, "lsystem_thickness")
            shape.prop(props, "palette")
            shape.label(text="Growth Rounds multiplies the branch count")
            generate_text = "Generate Full Sculpture"
            generate_icon = "OUTLINER_OB_CURVE"
        else:
            shape.label(text="2. Adjust the visible paint marks")
            shape.prop(props, "palette")
            shape.prop(props, "trail_radius")
            shape.prop(props, "mark_length")
            shape.prop(props, "mark_spacing")
            shape.prop(props, "opacity_mode")
            shape.label(text="Spacing high = fewer marks")
            generate_text = "Generate Full Painting"
            generate_icon = "BRUSH_DATA"
        generate = shape.row()
        generate.scale_y = 1.5
        generate.operator("flow_field.generate", text=generate_text, icon=generate_icon)

        keep = layout.box()
        keep.enabled = has_generation
        keep.label(text="3. Save the full artwork")
        keep.prop(props, "output_dir")
        keep.operator("flow_field.render", icon="RENDER_STILL")
        keep.operator("flow_field.freeze", icon="OUTLINER_DATA_MESH")

        status = layout.box()
        status.label(text=props.status, icon="DOT")


class FLOWFIELD_PT_motion(Panel):
    bl_idname = "FLOWFIELD_PT_motion"
    bl_label = "Invisible Path Shape"
    bl_parent_id = "FLOWFIELD_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Generative Art"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.scene.flow_field_settings.generator_type == "FLOW"

    def draw(self, context: bpy.types.Context) -> None:
        props = context.scene.flow_field_settings
        layout = self.layout
        layout.prop(props, "agents")
        layout.prop(props, "steps")
        layout.label(text="More painters and longer paths add coverage")
        layout.prop(props, "field_scale")
        layout.label(text="Low scale = broad bends; high = busy turns")
        layout.prop(props, "inertia")
        layout.label(text="High smoothness = graceful curves")
        layout.prop(props, "noise_strength")
        layout.prop(props, "orbit_strength")
        layout.prop(props, "step_size")


class FLOWFIELD_PT_look(Panel):
    bl_idname = "FLOWFIELD_PT_look"
    bl_label = "Paint, Opacity & Canvas"
    bl_parent_id = "FLOWFIELD_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Generative Art"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.scene.flow_field_settings.generator_type == "FLOW"

    def draw(self, context: bpy.types.Context) -> None:
        props = context.scene.flow_field_settings
        layout = self.layout
        layout.prop(props, "palette")
        layout.prop(props, "canvas_radius")
        layout.prop(props, "show_canvas")
        layout.separator()
        layout.prop(props, "trail_radius")
        layout.prop(props, "mark_length")
        layout.prop(props, "mark_spacing")
        layout.prop(props, "paint_coverage")
        layout.separator()
        layout.prop(props, "opacity_mode")
        layout.prop(props, "opacity_min")
        layout.prop(props, "opacity_max")
        if props.opacity_mode == "FIELD":
            layout.prop(props, "opacity_scale")
        layout.separator()
        layout.prop(props, "metallic")
        layout.prop(props, "roughness")
        layout.prop(props, "emission_strength")


class FLOWFIELD_PT_camera(Panel):
    bl_idname = "FLOWFIELD_PT_camera"
    bl_label = "Camera & Output"
    bl_parent_id = "FLOWFIELD_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Generative Art"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.scene.flow_field_settings.generator_type == "FLOW"

    def draw(self, context: bpy.types.Context) -> None:
        props = context.scene.flow_field_settings
        layout = self.layout
        layout.prop(props, "camera_azimuth")
        layout.prop(props, "camera_elevation")
        layout.prop(props, "camera_distance")
        layout.prop(props, "camera_lens")
        layout.prop(props, "render_size")
        layout.label(text="Camera changes apply on Generate")


class FLOWFIELD_PT_lsystem_growth(Panel):
    bl_idname = "FLOWFIELD_PT_lsystem_growth"
    bl_label = "Growth Rule & 3D Shape"
    bl_parent_id = "FLOWFIELD_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Generative Art"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.scene.flow_field_settings.generator_type == "LSYSTEM"

    def draw(self, context: bpy.types.Context) -> None:
        props = context.scene.flow_field_settings
        layout = self.layout
        layout.prop(props, "lsystem_iterations")
        layout.label(text="Each round rewrites every symbol")
        layout.prop(props, "lsystem_angle")
        layout.prop(props, "lsystem_length_ratio")
        layout.label(text="Low shrink = short twigs; high = long twigs")
        layout.prop(props, "lsystem_randomness")
        layout.prop(props, "lsystem_segment_length")
        layout.prop(props, "lsystem_spatial_spread")
        layout.label(text="0 spread stays flat; high spread wraps in 3D")


class FLOWFIELD_PT_lsystem_look(Panel):
    bl_idname = "FLOWFIELD_PT_lsystem_look"
    bl_label = "Branches, Material & Camera"
    bl_parent_id = "FLOWFIELD_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Generative Art"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.scene.flow_field_settings.generator_type == "LSYSTEM"

    def draw(self, context: bpy.types.Context) -> None:
        props = context.scene.flow_field_settings
        layout = self.layout
        layout.prop(props, "lsystem_thickness")
        layout.prop(props, "lsystem_taper")
        layout.label(text="Low taper makes tips thin quickly")
        layout.prop(props, "palette")
        layout.prop(props, "metallic")
        layout.prop(props, "roughness")
        layout.prop(props, "emission_strength")
        layout.separator()
        layout.prop(props, "lsystem_camera_lens")
        layout.prop(props, "render_size")
        layout.label(text="The camera frames new growth automatically")


CLASSES = (
    FLOWFIELD_PG_settings,
    FLOWFIELD_OT_apply_preset,
    FLOWFIELD_OT_generate,
    FLOWFIELD_OT_new_seed,
    FLOWFIELD_OT_mutate,
    FLOWFIELD_OT_freeze,
    FLOWFIELD_OT_render,
    FLOWFIELD_PT_main,
    FLOWFIELD_PT_motion,
    FLOWFIELD_PT_look,
    FLOWFIELD_PT_camera,
    FLOWFIELD_PT_lsystem_growth,
    FLOWFIELD_PT_lsystem_look,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.flow_field_settings = PointerProperty(type=FLOWFIELD_PG_settings)


def unregister() -> None:
    del bpy.types.Scene.flow_field_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
