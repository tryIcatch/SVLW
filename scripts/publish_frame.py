"""Drop-in frame publisher for a project that already outputs HxWx3 RGB uint8 arrays."""
import os
import time
from pathlib import Path
from PIL import Image

FRAME = Path(os.environ.get('SIM_PREVIEW_FRAME', str(Path.home() / 'remote-sim-viz' / 'frames' / 'latest.jpg')))
FRAME.parent.mkdir(parents=True, exist_ok=True)
TMP = FRAME.with_name('latest.tmp.jpg')
_last_emit = 0.0

def publish_frame(rgb, fps_limit=5):
    global _last_emit
    if fps_limit <= 0:
        raise ValueError('fps_limit must be positive')
    now = time.monotonic()
    if now - _last_emit < 1 / fps_limit:
        return False
    Image.fromarray(rgb).save(TMP, format='JPEG', quality=80)
    os.replace(TMP, FRAME)
    _last_emit = now
    return True
