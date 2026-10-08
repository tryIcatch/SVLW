#!/usr/bin/env python3
"""Display the latest JPEG frame on a remote X11 virtual desktop.
Run with system /usr/bin/python3 after installing python3-tk and python3-pil.imagetk.
"""
import os
from pathlib import Path
import tkinter as tk
from PIL import Image, ImageTk

IMAGE = Path(os.environ.get('SIM_PREVIEW_FRAME', str(Path.home() / 'remote-sim-viz' / 'frames' / 'latest.jpg')))
INTERVAL_MS = 100

root = tk.Tk()
root.title('Remote MuJoCo Simulation')
root.configure(bg='#202020')
label = tk.Label(root, text='等待仿真画面 / Waiting for frames...', bg='#202020', fg='white', font=('Sans', 15))
label.pack(padx=15, pady=15)
last_mtime = -1

def refresh():
    global last_mtime
    try:
        current_mtime = IMAGE.stat().st_mtime_ns
        if current_mtime != last_mtime:
            with Image.open(IMAGE) as src:
                rgb = src.convert('RGB')
            rgb.thumbnail((1400, 800))
            photo = ImageTk.PhotoImage(rgb)
            label.configure(image=photo, text='')
            label.image = photo  # Prevent GC
            last_mtime = current_mtime
    except (FileNotFoundError, OSError, ValueError):
        pass
    root.after(INTERVAL_MS, refresh)

refresh()
root.mainloop()
