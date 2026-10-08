#!/usr/bin/env python3
"""Minimal GPU EGL simulator publishing JPEG frames for VNC preview.
Keep MUJOCO_GL=egl and PYOPENGL_PLATFORM=egl set before Python starts.
"""
import math
import os
import time
from pathlib import Path
import mujoco
from PIL import Image

FRAME = Path(os.environ.get('SIM_PREVIEW_FRAME', str(Path.home() / 'remote-sim-viz' / 'frames' / 'latest.jpg')))
FRAME.parent.mkdir(parents=True, exist_ok=True)
TMP = FRAME.with_name('latest.tmp.jpg')

xml = '''
<mujoco>
  <option gravity="0 0 0" timestep="0.01"/>
  <visual><global offwidth="800" offheight="500"/></visual>
  <worldbody>
    <light pos="0 0 3" diffuse="1 1 1"/>
    <geom type="plane" size="3 3 0.1" rgba="0.25 0.3 0.4 1"/>
    <body name="ball" pos="0 0 0.6">
      <geom type="sphere" size="0.17" rgba="0.9 0.25 0.18 1"/>
    </body>
  </worldbody>
</mujoco>
'''
model = mujoco.MjModel.from_xml_string(xml)
data = mujoco.MjData(model)
ball_id = model.body('ball').id
print('MuJoCo:', mujoco.__version__, '| Preview file:', FRAME, flush=True)
renderer = mujoco.Renderer(model, height=480, width=640)
try:
    count = 0
    while True:
        t = count / 10.0
        model.body_pos[ball_id, 0] = 0.65 * math.sin(t)
        model.body_pos[ball_id, 2] = 0.5 + 0.28 * abs(math.sin(t * 1.5))
        mujoco.mj_forward(model, data)
        renderer.update_scene(data)
        rgb = renderer.render()
        Image.fromarray(rgb).save(TMP, format='JPEG', quality=82)
        os.replace(TMP, FRAME)  # Atomic: viewer never reads a half-written JPEG
        count += 1
        if count % 20 == 0:
            print('Published', count, 'frames', flush=True)
        time.sleep(0.1)
except KeyboardInterrupt:
    print('Stopped by user')
finally:
    renderer.close()
