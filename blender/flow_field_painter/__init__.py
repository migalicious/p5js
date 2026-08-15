"""Beginner-facing controls for growing and capturing 3D flow paintings."""

from __future__ import annotations

import json
import random
from dataclasses import asdict
from pathlib import Path

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup

from .generator import FlowSettings, build, freeze_current_frame


bl_info = {
    "name": "Flow Field Painter",
    "author": "migalicious",
    "version": (0, 2, 0),
    "blender": (5, 2, 0),
    "location": "3D Viewport > Sidebar > Generative Art",
    "description": "Grow and capture seeded three-dimensional flow paintings",
    "category": "3D View",
}


PALETTE_ITEMS = (
    ("ELECTRIC", "Electric", "Purple, turquoise, yellow, and coral"),
    ("EMBER", "Ember", "Deep red, orange, gold, and cream"),
    ("TIDAL", "Tidal", "Deep blue through bright cyan"),
    ("GROVE", "Grove", "Forest green through pale yellow-green"),
    ("MONO", "Monochrome", "Black, gray, and white"),
)


class FLOWFIELD_PG_settings(PropertyGroup):
    seed: IntProperty(
        name="Seed",
        description="The repeatable identity of this painting",
        default=42,
        min=0,
        max=999_999,
    )
    agents: IntProperty(
        name="Trail Count",
        description="How many agents paint trails; higher values take more memory",
        default=150,
        min=5,
        max=800,
    )
    steps: IntProperty(
        name="Trail Length",
        description="How many simulation steps each trail can paint",
        default=280,
        min=20,
        max=1200,
    )
    growth_frames: IntProperty(
        name="Cooking Time",
        description="Frames required for each wave to finish growing",
        default=180,
        min=20,
        max=1000,
    )
    waves: IntProperty(
        name="Start Waves",
        description="Stagger trails into groups that begin at slightly different times",
        default=9,
        min=1,
        max=30,
    )
    field_scale: FloatProperty(
        name="Flow Scale",
        description="Size of the broad bends in the flow field",
        default=0.31,
        min=0.03,
        max=1.5,
        precision=3,
    )
    step_size: FloatProperty(
        name="Step Size",
        description="Distance painted on each simulation step",
        default=0.067,
        min=0.005,
        max=0.3,
        precision=3,
    )
    inertia: FloatProperty(
        name="Momentum",
        description="How strongly trails resist sudden changes in direction",
        default=0.84,
        min=0.0,
        max=0.98,
        subtype="FACTOR",
    )
    noise_strength: FloatProperty(
        name="Turbulence",
        description="Strength of the three-dimensional noise field",
        default=1.0,
        min=0.0,
        max=3.0,
    )
    orbit_strength: FloatProperty(
        name="Orbit",
        description="How strongly trails circle the center",
        default=0.42,
        min=-2.0,
        max=2.0,
    )
    center_strength: FloatProperty(
        name="Center Pull",
        description="How strongly wandering trails are drawn back inward",
        default=0.23,
        min=0.0,
        max=2.0,
    )
    lift_strength: FloatProperty(
        name="Vertical Lift",
        description="Adds rising and falling motion through the volume",
        default=0.16,
        min=-1.0,
        max=1.0,
    )
    bounds_radius: FloatProperty(
        name="Painting Size",
        description="Approximate radius of the space where trails begin",
        default=4.8,
        min=0.5,
        max=20.0,
    )
    trail_radius: FloatProperty(
        name="Trail Thickness",
        description="Radius of the painted tubes",
        default=0.023,
        min=0.002,
        max=0.2,
        precision=3,
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
    camera_distance: FloatProperty(name="Camera Distance", default=16.9, min=3.0, max=50.0)
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
    status: StringProperty(name="Status", default="Ready for a first generation")


def settings_from_scene(scene: bpy.types.Scene) -> FlowSettings:
    props = scene.flow_field_settings
    return FlowSettings(
        seed=props.seed,
        agents=props.agents,
        steps=props.steps,
        growth_frames=props.growth_frames,
        capture_frame=scene.frame_current,
        waves=props.waves,
        field_scale=props.field_scale,
        step_size=props.step_size,
        inertia=props.inertia,
        noise_strength=props.noise_strength,
        orbit_strength=props.orbit_strength,
        center_strength=props.center_strength,
        lift_strength=props.lift_strength,
        bounds_radius=props.bounds_radius,
        trail_radius=props.trail_radius,
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


def set_view_to_camera(context: bpy.types.Context) -> None:
    screen = context.screen
    if screen is None:
        return
    for area in screen.areas:
        if area.type == "VIEW_3D":
            area.spaces.active.region_3d.view_perspective = "CAMERA"


def play_from_start(context: bpy.types.Context) -> None:
    context.scene.frame_set(context.scene.frame_start)
    if context.screen is not None and not context.screen.is_animation_playing:
        bpy.ops.screen.animation_play()


def generate_and_play(context: bpy.types.Context) -> None:
    scene = context.scene
    props = scene.flow_field_settings
    settings = settings_from_scene(scene)
    build(scene, settings)
    scene["flow_field_seed"] = props.seed
    scene["flow_field_has_generation"] = True
    scene.frame_set(scene.frame_start)
    set_view_to_camera(context)
    props.status = f"Seed {props.seed} is cooking"
    if context.screen is not None and not context.screen.is_animation_playing:
        bpy.ops.screen.animation_play()


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for number in range(2, 10_000):
        candidate = path.with_name(f"{path.stem}_{number:02d}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not choose a unique filename near {path}")


class FLOWFIELD_OT_generate(Operator):
    bl_idname = "flow_field.generate"
    bl_label = "Generate & Play"
    bl_description = "Rebuild the painting from these controls and start cooking at frame 1"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        try:
            generate_and_play(context)
        except Exception as exc:
            context.scene.flow_field_settings.status = f"Generation failed: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "Flow painting generated; press Pause whenever it looks right")
        return {"FINISHED"}


class FLOWFIELD_OT_new_seed(Operator):
    bl_idname = "flow_field.new_seed"
    bl_label = "New Seed"
    bl_description = "Choose a fresh seed, rebuild, and play from the beginning"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        context.scene.flow_field_settings.seed = random.SystemRandom().randint(0, 999_999)
        return FLOWFIELD_OT_generate.execute(self, context)


class FLOWFIELD_OT_mutate(Operator):
    bl_idname = "flow_field.mutate"
    bl_label = "Mutate Knobs"
    bl_description = "Nudge several motion controls while keeping the current seed"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        props = context.scene.flow_field_settings
        rng = random.Random(props.seed + context.scene.frame_current * 7919)
        props.field_scale = max(0.03, min(1.5, props.field_scale * rng.uniform(0.78, 1.22)))
        props.inertia = max(0.0, min(0.98, props.inertia + rng.uniform(-0.08, 0.08)))
        props.orbit_strength = max(-2.0, min(2.0, props.orbit_strength + rng.uniform(-0.22, 0.22)))
        props.center_strength = max(0.0, min(2.0, props.center_strength * rng.uniform(0.75, 1.3)))
        props.lift_strength = max(-1.0, min(1.0, props.lift_strength + rng.uniform(-0.12, 0.12)))
        return FLOWFIELD_OT_generate.execute(self, context)


class FLOWFIELD_OT_replay(Operator):
    bl_idname = "flow_field.replay"
    bl_label = "Replay"
    bl_description = "Return to frame 1 and play the current painting again"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(context.scene.get("flow_field_has_generation"))

    def execute(self, context: bpy.types.Context) -> set[str]:
        play_from_start(context)
        context.scene.flow_field_settings.status = "Replaying from frame 1"
        return {"FINISHED"}


class FLOWFIELD_OT_pause_resume(Operator):
    bl_idname = "flow_field.pause_resume"
    bl_label = "Pause / Resume"
    bl_description = "Pause at an interesting moment or continue cooking"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(context.scene.get("flow_field_has_generation")) and context.screen is not None

    def execute(self, context: bpy.types.Context) -> set[str]:
        if context.screen.is_animation_playing:
            bpy.ops.screen.animation_cancel(restore_frame=False)
            context.scene.flow_field_settings.status = f"Paused at frame {context.scene.frame_current}"
        else:
            bpy.ops.screen.animation_play()
            context.scene.flow_field_settings.status = "Cooking"
        return {"FINISHED"}


class FLOWFIELD_OT_freeze(Operator):
    bl_idname = "flow_field.freeze"
    bl_label = "Freeze This Moment"
    bl_description = "Preserve the visible trails at this frame as separate editable mesh objects"
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
        context.scene.flow_field_settings.status = f"Saved {capture.name} inside this Blender file"
        self.report({"INFO"}, f"Frozen as {capture.name}")
        return {"FINISHED"}


class FLOWFIELD_OT_render(Operator):
    bl_idname = "flow_field.render"
    bl_label = "Render PNG"
    bl_description = "Render the current cooking frame and save its exact recipe"

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
            stem = f"flow_seed_{props.seed:06d}_frame_{scene.frame_current:04d}"
            render_path = unique_path(output_dir / f"{stem}.png")
            recipe_path = render_path.with_suffix(".json")
            settings = settings_from_scene(scene)
            recipe_path.write_text(json.dumps(asdict(settings), indent=2) + "\n", encoding="utf-8")
            scene.render.filepath = str(render_path)
            bpy.ops.render.render(write_still=True)
        except Exception as exc:
            props.status = f"Render failed: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        scene["flow_field_last_render"] = str(render_path)
        props.status = f"Rendered frame {scene.frame_current} to {render_path.name}"
        self.report({"INFO"}, f"Saved {render_path}")
        return {"FINISHED"}


class FLOWFIELD_PT_main(Panel):
    bl_idname = "FLOWFIELD_PT_main"
    bl_label = "Flow Field Painter"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Generative Art"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        scene = context.scene
        props = scene.flow_field_settings
        has_generation = bool(scene.get("flow_field_has_generation"))

        intro = layout.box()
        intro.label(text="Same seed + same knobs = same painting", icon="INFO")

        choose = layout.box()
        choose.label(text="1. Choose the starting conditions")
        choose.prop(props, "seed")
        row = choose.row(align=True)
        row.scale_y = 1.35
        row.operator("flow_field.generate", icon="PLAY")
        row.operator("flow_field.new_seed", text="New Seed", icon="FILE_REFRESH")
        choose.operator("flow_field.mutate", icon="MOD_NOISE")

        cook = layout.box()
        cook.enabled = has_generation
        cook.label(text="2. Let it cook, then pause")
        cook.prop(scene, "frame_current", text="Cooking Frame", slider=True)
        row = cook.row(align=True)
        row.operator("flow_field.replay", icon="LOOP_BACK")
        playing = bool(context.screen and context.screen.is_animation_playing)
        row.operator(
            "flow_field.pause_resume",
            text="Pause" if playing else "Resume",
            icon="PAUSE" if playing else "PLAY",
        )

        keep = layout.box()
        keep.enabled = has_generation
        keep.label(text="3. Keep what you like")
        keep.operator("flow_field.freeze", icon="OUTLINER_DATA_MESH")
        keep.prop(props, "output_dir")
        keep.operator("flow_field.render", icon="RENDER_STILL")

        status = layout.box()
        status.label(text=props.status, icon="DOT")


class FLOWFIELD_PT_motion(Panel):
    bl_idname = "FLOWFIELD_PT_motion"
    bl_label = "Motion Knobs"
    bl_parent_id = "FLOWFIELD_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Generative Art"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: bpy.types.Context) -> None:
        props = context.scene.flow_field_settings
        layout = self.layout
        layout.prop(props, "agents")
        layout.prop(props, "steps")
        layout.prop(props, "growth_frames")
        layout.prop(props, "waves")
        layout.separator()
        layout.prop(props, "field_scale")
        layout.prop(props, "step_size")
        layout.prop(props, "inertia")
        layout.prop(props, "noise_strength")
        layout.prop(props, "orbit_strength")
        layout.prop(props, "center_strength")
        layout.prop(props, "lift_strength")
        layout.prop(props, "bounds_radius")


class FLOWFIELD_PT_look(Panel):
    bl_idname = "FLOWFIELD_PT_look"
    bl_label = "Look Knobs"
    bl_parent_id = "FLOWFIELD_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Generative Art"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: bpy.types.Context) -> None:
        props = context.scene.flow_field_settings
        layout = self.layout
        layout.prop(props, "palette")
        layout.prop(props, "trail_radius")
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

    def draw(self, context: bpy.types.Context) -> None:
        props = context.scene.flow_field_settings
        layout = self.layout
        layout.prop(props, "camera_azimuth")
        layout.prop(props, "camera_elevation")
        layout.prop(props, "camera_distance")
        layout.prop(props, "camera_lens")
        layout.prop(props, "render_size")
        layout.label(text="Camera changes apply on Generate")


CLASSES = (
    FLOWFIELD_PG_settings,
    FLOWFIELD_OT_generate,
    FLOWFIELD_OT_new_seed,
    FLOWFIELD_OT_mutate,
    FLOWFIELD_OT_replay,
    FLOWFIELD_OT_pause_resume,
    FLOWFIELD_OT_freeze,
    FLOWFIELD_OT_render,
    FLOWFIELD_PT_main,
    FLOWFIELD_PT_motion,
    FLOWFIELD_PT_look,
    FLOWFIELD_PT_camera,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.flow_field_settings = PointerProperty(type=FLOWFIELD_PG_settings)


def unregister() -> None:
    del bpy.types.Scene.flow_field_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
