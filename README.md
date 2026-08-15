# Generative Art Sketches

A collection of interactive generative art sketches built with the HTML5 Canvas API, plus experiments that carry the same seeded, parameter-driven process into Blender. The browser sketches require no build step or local dependencies beyond what's loaded from CDN.

Open `index.html` for a visual gallery of all sketches.

## Sketches

| File | Title | Description |
|------|-------|-------------|
| [color_flow_field.html](color_flow_field.html) | Color Flow Field | Feature-rich particle system driven by Perlin noise with extensive color and export controls |
| [flow_field_interactive.html](flow_field_interactive.html) | Flow Field (Lite) | Lightweight particle flow field with a minimal control bar |
| [koch_layers.html](koch_layers.html) | Koch Layers | Multiple layered Koch curve fractals with per-layer color, rotation, and blend mode controls |
| [lsystem_tree_interactive.html](lsystem_tree_interactive.html) | L-System Tree | Procedural branching structures (tree, fern, coral, snowflake) using L-system expansion |
| [strange_attractor_interactive.html](strange_attractor_interactive.html) | Strange Attractors | Clifford, De Jong, and Lorenz attractors rendered as iterated point clouds |

---

## Color Flow Field

Particles follow vectors determined by layered Perlin noise. A floating control panel gives fine-grained control over the field, color mapping, and export.

**Color modes:** angle · position · age · curl · speed
**Palettes:** neon · fire · ocean · sunset · mono · split complementary

**Controls:**
- Field: noise scale, angle multiplier, octaves, particle count, step length, line width, lifetime, opacity, fade trails
- Color: hue range/offset, saturation, lightness, gradient direction, curl sensitivity
- Export: PNG / JPEG / WebP with quality slider

**Keyboard shortcuts:** `n` new field · `c` clear · `Space` pause · `f` fullscreen

---

## Flow Field (Lite)

A simpler, theme-aware version of the flow field sketch on a fixed 640×420 canvas. Good starting point for experimentation.

**Controls:** particle count · noise scale · step length · lifetime · opacity · re-seed · clear

---

## Koch Layers

Overlays up to six independent Koch curve fractals on a single canvas. Each layer has its own color, iteration depth, scale, angle, and rotation offset. Global blend mode and animated rotation are also supported.

**Blend modes:** normal · screen · lighter (additive) · difference · multiply · overlay
**Per-layer:** enable/disable · color · iterations (1–6) · scale · angle · rotation offset · opacity · line width

---

## L-System Tree

Generates fractal plant structures by expanding L-system strings and drawing them with turtle graphics. Four built-in presets cover common forms.

**Presets:** Tree · Fern · Coral · Snowflake (Koch)
**Controls:** iterations · branch angle · length ratio · randomness (stochastic variation)

---

## Strange Attractors

Plots millions of iterated points for three classic strange attractors, revealing the underlying chaotic geometry.

**Attractors:**
- **Clifford:** `x' = sin(a·y) + c·cos(a·x)` / `y' = sin(b·x) + d·cos(b·y)`
- **De Jong:** `x' = sin(a·y) − cos(b·x)` / `y' = sin(c·x) − cos(d·y)`
- **Lorenz:** 3-D system projected onto the X–Z plane

**Controls:** iterations (0.5–5 M) · point size · opacity · parameters a/b/c/d · randomize

---

## Running Locally

All sketches are self-contained HTML files. Just open any file directly in a modern browser — no server required.

```
open index.html          # gallery
open color_flow_field.html
```

## Blender experiments

The [Blender prototypes](blender/README.md) turn the sketches' generative rules
into editable scenes and geometry. The first prototype is an animated 3D
flow-field painting: seeded agents leave tapered trails that accumulate across
Blender's timeline and can be captured at any frame.

## Thumbnails

The gallery page (`index.html`) looks for thumbnail images in a `thumbnails/` folder named after each sketch file:

```
thumbnails/
  color_flow_field.png
  flow_field_interactive.png
  koch_layers.png
  lsystem_tree_interactive.png
  strange_attractor_interactive.png
```

Missing thumbnails fall back to a styled placeholder automatically. To capture a screenshot, open the sketch, get it looking how you want, and save it as a PNG into `thumbnails/`.

## Technologies

- HTML5 Canvas 2D API
- Vanilla JavaScript (no frameworks)
- Perlin / value noise (hash-based, inline implementation)
- L-system string expansion with stack-based turtle graphics
- CSS Grid / Flexbox for UI layout
- Google Fonts (DM Mono, DM Sans)
- Blender Python API and native curve geometry
