# Blender generative-art prototypes

## Flow-field painting

`flow_field_prototype.py` turns the accumulating flow-field idea into animated
3D curve geometry. Seeded agents travel through a noise field, leaving tapered
trails behind them. The trails grow across Blender's timeline, so changing the
current frame changes the captured moment.

The script produces two or three files in `blender/output/`:

- an editable `.blend` scene;
- a JSON recipe containing the exact seed and parameter values;
- optionally, a rendered PNG of the capture frame.

The recipe is also embedded in the Blender scene as the `recipe` custom
property. Generated output is ignored by Git.

### Run on mini (zsh)

```zsh
/Applications/Blender.app/Contents/MacOS/Blender \
  --background --factory-startup \
  --python blender/flow_field_prototype.py -- \
  --seed 42 --capture-frame 132 --render
```

Open the resulting `.blend`, switch to camera view, and scrub the timeline to
watch the painting grow.

The same script is intended to run on desktop once the same Blender version is
installed there. Its Windows invocation has not yet been verified, so it is not
documented here as a paste-ready command.

### Useful variations

```zsh
# A nearby seed at the default complexity
/Applications/Blender.app/Contents/MacOS/Blender \
  --background --factory-startup \
  --python blender/flow_field_prototype.py -- \
  --seed 43 --capture-frame 132 --render

# A lighter preview
/Applications/Blender.app/Contents/MacOS/Blender \
  --background --factory-startup \
  --python blender/flow_field_prototype.py -- \
  --seed 44 --agents 70 --steps 180 --render-size 512 --render
```

Available command-line controls:

```text
--seed INTEGER
--agents INTEGER
--steps INTEGER
--capture-frame INTEGER
--growth-frames INTEGER
--render-size INTEGER
--output-dir PATH
--render
```
