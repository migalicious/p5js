# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running sketches

No build step. Open any HTML file directly in a browser:

```
open index.html               # visual gallery of all sketches
open color_flow_field.html    # individual sketch
```

There are no npm scripts, package.json, or dependencies to install.

## Repository structure

```
index.html                  — gallery page (JS-driven card grid)
shared.css                  — design system: CSS variables + reusable UI components
color_flow_field.html       — interactive particle flow field (fullscreen canvas)
batch_flow_field.html       — batch image generator derived from color_flow_field
3d_geometries.html          — p5.js sketch using shared.css
koch_layers.html            — Koch fractal layers
lsystem_tree_interactive.html
strange_attractor_interactive.html
thumbnails/                 — PNG previews named after each sketch file
_archive/                   — old versions, not shown in gallery
sketches/                   — standalone p5.js sketch files (e.g. for WCC challenges)
```

## Two sketch archetypes

**Vanilla Canvas 2D (most sketches):** Self-contained HTML files with all CSS and JS inlined. They do not `<link>` to `shared.css`; instead they copy-paste the relevant CSS variables and component styles directly into `<style>`. The fullscreen-canvas + sliding side panel UI pattern (used in `color_flow_field.html`) is the main template to follow for new interactive sketches.

**p5.js sketches:** `3d_geometries.html` and files under `sketches/` use p5.js loaded from CDN. `3d_geometries.html` is the one exception that does `<link rel="stylesheet" href="shared.css">` rather than inlining.

## Design system (`shared.css`)

All CSS variables live in `shared.css` and should be kept in sync when inlining into new sketches:

| Variable | Purpose |
|---|---|
| `--bg`, `--surface`, `--surface2` | Background layers |
| `--border`, `--border2` | Subtle / visible borders |
| `--text`, `--text-muted`, `--text-dim` | Text hierarchy |
| `--accent` | `#7c6cfc` — purple, used for focus/hover/active states |
| `--font-ui` / `--font-mono` | DM Sans / DM Mono (Google Fonts) |
| `--panel-w` | `300px` side panel width |

`shared.css` also defines the reusable components: `#header` pill, `#toggle-panel` button, `#panel` with `.hidden` slide-out, `.section`, `.ctrl`, `.ctrl-row`, `.val`, `button` variants (`.primary`, `.export-btn`, `#pauseBtn.active`), `kbd`, `select`, `input[type=range]`.

## Adding a new sketch

1. Create a self-contained HTML file (inline styles + script, no external CSS unless using p5.js pattern).
2. Add an entry to the `sketches` array in `index.html`:
   ```js
   { file: 'my_sketch.html', title: 'My Sketch', desc: '…', tags: ['Tag1', 'Tag2'] }
   ```
3. Optionally add `thumbnails/my_sketch.png` (screenshot); the gallery shows a styled placeholder automatically if it's missing.

## Noise implementation

The value-noise implementation used across the vanilla sketches is a simple hash-based smoothstep approach — not p5.js noise, not a library:

```js
function hash(x, y) { let n = Math.sin(x*127.1+y*311.7)*43758.5453; return n-(n|0); }
function noise(x, y) {
  const ix=Math.floor(x), iy=Math.floor(y), fx=x-ix, fy=y-iy;
  const s=fx*fx*(3-2*fx), t=fy*fy*(3-2*fy);
  return hash(ix,iy)*(1-s)*(1-t)+hash(ix+1,iy)*s*(1-t)+hash(ix,iy+1)*(1-s)*t+hash(ix+1,iy+1)*s*t;
}
```

Copy this verbatim when adding new field-based sketches.

## `batch_flow_field.html` engine pattern

`batch_flow_field.html` extracts the flow field engine from `color_flow_field.html` into a module-level `activeCfg` / `activeSeed` pattern so engine functions (`fieldAngle`, `fieldCurl`, `colorForParticle`, `makeParticle`, `drawFrame`) read from a config object instead of DOM inputs. This is the right pattern if you need to drive the same engine from code (batch, animation export, etc.) rather than from sliders.
