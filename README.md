# 从 Linux 远程服务器到 Windows VNC：MuJoCo EGL 实时可视化复现教程

> **适用对象**：通过 SSH 使用 Linux 远程计算服务器，希望在 Windows 电脑上查看机器人、物理引擎或机器学习仿真过程。  
> **适用系统**：以 Ubuntu 22.04/24.04 Server（GPU EGL 路线假定已安装可用的 NVIDIA 驱动）和 Windows 10/11 为例。  
> **核心方案**：MuJoCo EGL → RGB 帧 → Xvfb 虚拟屏幕 → x11vnc → SSH 隧道 → Windows TigerVNC Viewer。按照以下步骤从零实现，不依赖某个特定 VLA 项目。

---

## 一、最终要实现的效果与完整路线

本教程只采用一条与服务器实际仿真工作流一致的方案：**Linux 远程服务器使用 MuJoCo 的 EGL 后端输出 RGB 图像，Xvfb 在服务器上提供虚拟桌面，x11vnc + SSH 端口转发让 Windows VNC Viewer 看到这些图像。** 即使远程服务器没有显示器，也能通过本地 Windows 看仿真画面。

```text
  Linux 远程服务器（通过 SSH 管理）
  ┌──────────────────────────────────────────────────────┐
  │ MuJoCo 物理仿真 / 模型评估 / 训练进程                  │
  │                 ↓                                    │
  │       GPU EGL 离屏渲染 → RGB 图像 → latest.jpg        │
  │                                         ↓            │
  │                                图像预览窗口 (Tk)     │
  │                                         ↓            │
  │                 Xvfb :1 + Openbox 虚拟桌面            │
  │                                         ↓            │
  │                      x11vnc 127.0.0.1:5901          │
  └─────────────────────────────────────────┼────────────┘
                                            │
                                    SSH 加密端口转发
                                            │
                                Windows TigerVNC Viewer
```

关键原理：EGL 负责 GPU 离屏渲染；Xvfb 负责虚拟桌面；x11vnc 负责传输桌面画面。**EGL 渲染出的图像不会自动出现在 Xvfb 上**，所以我们增加一个很轻量的图像桥接器。这个方案用于观看仿真与训练效果，不提供自动的机器人交互控制；如果要在 VNC 里操控机器人，还需要仿真程序自己的输入处理代码。

## 二、前提条件

1. 一台可以通过 SSH 登录的 Ubuntu Linux 服务器（具有安装软件的权限）。
2. 一台 Windows 10/11 电脑，能够通过 SSH 访问服务器。
3. 服务器不需要连接物理显示器，也不强制要求 NVIDIA GPU。**GPU 仅在需要 EGL 硬件渲染时才是必要条件。**
4. 推荐使用普通 Linux 用户操作，只有安装系统依赖时使用 `sudo`。下文中的 `用户名`、`服务器IP` 均需替换。

首次登录：

```powershell
ssh 用户名@服务器IP
```

若 SSH 使用自定义端口（例如 `2222`）：

```powershell
ssh -p 2222 用户名@服务器IP
```

## 三、Linux 端：安装虚拟显示与 VNC 组件

在 SSH 登录后的 Linux 终端执行：

```bash
sudo apt update
sudo apt install -y \
  xvfb x11vnc openbox xterm x11-utils xauth \
  tmux util-linux mesa-utils libegl1 libgl1 libglvnd0 libgles2 \
  python3 python3-venv python3-pip python3-tk \
  python3-pil python3-pil.imagetk
```

各组件作用：

| 组件 | 作用 |
|---|---|
| `Xvfb` | 在内存中创建虚拟 X11 显示器，不依赖物理屏幕 |
| `Openbox` | 管理窗口，使桌面和应用窗口可正常显示 |
| `x11vnc` | 将已有的 X11 显示器画面通过 VNC 提供出去 |
| `xterm` | 用来验证虚拟桌面上是否能够弹出窗口 |
| `tmux` | 让显示器、VNC 与仿真进程在 SSH 退出后继续运行 |
| `python3-tk`、`Pillow ImageTk` | 在虚拟桌面上显示 EGL 程序输出的实时图片 |

> 仅安装这些组件，不等于安装了具体的机器人仿真平台。仿真器与模型环境应根据项目要求单独安装。

## 四、Linux 端：创建虚拟显示器 `:1`

以下统一使用：

- X11 显示号：`:1`
- 虚拟屏幕分辨率：`1600x900`，24 位色深
- VNC 端口：`5901`

### 4.1 创建 X11 访问凭证

```bash
# 保护当前用户的 X11 授权文件
AUTHFILE="$HOME/.Xauthority-sim"
touch "$AUTHFILE"
chmod 600 "$AUTHFILE"

# 为显示器 :1 生成随机授权令牌
xauth -f "AUTHFILE" add :1 . "AUTHFILE" add :1 . "(mcookie)"
```

### 4.2 后台启动 Xvfb

```bash
tmux new-session -d -s sim-xvfb \
  "Xvfb :1 -screen 0 1600x900x24 -nolisten tcp -auth $HOME/.Xauthority-sim"
```

等待进程启动并检测：

```bash
export DISPLAY=:1
export XAUTHORITY="$HOME/.Xauthority-sim"
xdpyinfo -display :1 | grep dimensions
```

成功的典型输出：

```text
  dimensions:    1600x900 pixels
```

这里 `-nolisten tcp` 禁止 X 服务器直接开启网络 TCP 监听；稍后 VNC 也仅在服务器回环地址提供服务。

### 4.3 启动窗口管理器

```bash
tmux new-session -d -s sim-openbox \
  "DISPLAY=:1 XAUTHORITY=$HOME/.Xauthority-sim openbox"
```

### 4.4 打开一个测试窗口

```bash
tmux new-session -d -s sim-test-window \
  "DISPLAY=:1 XAUTHORITY=$HOME/.Xauthority-sim xterm -geometry 100x28+80+80"
```

稍后 Windows 连上 VNC 后，应该能够看到 `xterm` 终端窗口。

## 五、Linux 端：设置 VNC 密码并启动服务

### 5.1 设置独立的 VNC 密码

```bash
mkdir -p "$HOME/.vnc"
chmod 700 "$HOME/.vnc"
x11vnc -storepasswd "$HOME/.vnc/passwd"
chmod 600 "$HOME/.vnc/passwd"
```

根据屏幕提示输入并确认密码。VNC 密码不能替代 SSH 的安全保护，**务必同时使用下面的 SSH 隧道**。

### 5.2 启动 VNC 服务

```bash
tmux new-session -d -s sim-vnc \
  "x11vnc -display :1 -auth $HOME/.Xauthority-sim -rfbauth $HOME/.vnc/passwd -rfbport 5901 -localhost -forever -shared -noxdamage"
```

检测本地监听情况：

```bash
ss -ltn | grep 5901
```

预期能看到 `127.0.0.1:5901`（有些系统还会显示 IPv6 回环地址）。**不应看到公开网卡地址的 `:5901` 监听**。

参数解释：

- `-display :1`：VNC 对应 Xvfb 虚拟显示器 `:1`。
- `-rfbauth`：启用前面生成的 VNC 密码文件。
- `-rfbport 5901`：使用端口 `5901`。
- `-localhost`：只允许从服务器本机连接 VNC。
- `-forever`：VNC 客户端断开后服务仍保持。
- `-shared`：允许多个客户端查看同一个桌面。
- `-noxdamage`：在部分桌面或驱动环境中缓解刷新异常；若无问题也可去掉。

## 六、Windows 端：通过 SSH 隧道连接 VNC

### 6.1 下载 VNC Viewer

建议安装 TigerVNC Viewer：

- 官方仓库：<https://github.com/TigerVNC/tigervnc>
- 发布页面：<https://github.com/TigerVNC/tigervnc/releases>

只需要 Windows 上的 **Viewer**，无需在 Windows 上安装 VNC Server。

### 6.2 建立 SSH 端口转发

在 **Windows PowerShell** 输入：

```powershell
ssh -o ExitOnForwardFailure=yes -N -L 15901:127.0.0.1:5901 用户名@服务器IP
```

若 SSH 端口不是 `22`：

```powershell
ssh -p 2222 -o ExitOnForwardFailure=yes -N -L 15901:127.0.0.1:5901 用户名@服务器IP
```

其中 `-N` 表示只建立隧道、不打开远程交互 shell。建立成功后，**这个 PowerShell 窗口通常会保持运行且没有新提示符，这是正常现象**。使用 VNC 期间不要关闭它。

若本地 `15901` 已被占用，可改成其他未占用的本地端口，例如：

```powershell
ssh -o ExitOnForwardFailure=yes -N -L 15902:127.0.0.1:5901 用户名@服务器IP
```

### 6.3 连接虚拟桌面

在 TigerVNC Viewer 地址框输入：

```text
127.0.0.1::15901
```

注意**双冒号 `::` 表示直接指定 TCP 端口**。如果本地隧道端口改成 `15902`，这里应填 `127.0.0.1::15902`。

输入第五节设置的 VNC 密码，即可打开 Linux 虚拟桌面。此时如果一切正常，会看到第四节启动的 `xterm` 测试窗口。

**到此，远程 Linux 虚拟屏幕 → SSH → Windows VNC 的基础链路已搭建完成。**

## 七、MuJoCo EGL 离屏仿真 + VNC 实时预览（本教程采用的路线）

使用 EGL 时，画面被渲染成内存中的像素数组，不会自动创建桌面窗口。所以需要一个**图像桥接器**：

```text
仿真器 render() → RGB 像素 → latest.jpg
                                  ↓
                            Tk 预览窗口
                                  ↓
                             Xvfb / VNC
                                  ↓
                               Windows
```

这里的桥接器是一个**观察窗口**，并不会把 VNC 的键盘鼠标自动回传给机器人控制器。若需要交互控制，须由具体仿真程序额外实现输入事件或控制接口。

### 7.1 创建通用预览目录

```bash
mkdir -p "$HOME/remote-sim-viz/frames"
chmod 700 "$HOME/remote-sim-viz" "$HOME/remote-sim-viz/frames"
```

### 7.2 在虚拟桌面创建实时图片查看器

用下面的命令建立文件：

```bash
cat > "$HOME/remote-sim-viz/frame_viewer.py" <<'PY'
from pathlib import Path
import tkinter as tk
from PIL import Image, ImageTk

FRAME_PATH = Path.home() / "remote-sim-viz" / "frames" / "latest.jpg"
REFRESH_MS = 100  # 约每 100 ms 检查一次是否有新帧

root = tk.Tk()
root.title("Remote Simulation Preview")
root.configure(bg="#202020")
label = tk.Label(root, text="等待仿真画面...", bg="#202020", fg="white")
label.pack(padx=12, pady=12)
last_mtime = None


def refresh():
    global last_mtime
    try:
        stat = FRAME_PATH.stat()
        if stat.st_mtime_ns != last_mtime:
            with Image.open(FRAME_PATH) as src:
                img = src.convert("RGB")
            img.thumbnail((1280, 760))
            photo = ImageTk.PhotoImage(img)
            label.configure(image=photo, text="")
            label.image = photo  # 保持 Tk 图像引用
            last_mtime = stat.st_mtime_ns
    except (FileNotFoundError, OSError, ValueError):
        pass  # 首帧尚未写入或文件更新中，下次再检查
    root.after(REFRESH_MS, refresh)


refresh()
root.mainloop()
PY
```

启动查看器：

```bash
tmux new-session -d -s sim-preview \
  "DISPLAY=:1 XAUTHORITY=HOME/.Xauthority−sim/usr/bin/python3HOME/.Xauthority-sim /usr/bin/python3 HOME/remote-sim-viz/frame_viewer.py"
```

在 Windows VNC 中应该能看到标题为 `Remote Simulation Preview` 的窗口，它最初显示“等待仿真画面...”。

### 7.3 准备单独的 MuJoCo Python 环境并测试 EGL

为避免仿真依赖覆盖现有训练项目，先在**独立虚拟环境**中运行演示。下列示例使用 MuJoCo 3.13.0 和 NumPy 1.26.4，如已有兼容环境可以沿用自己项目的版本，但不要在正式训练环境中盲目升级依赖。

```bash
python3 -m venv "$HOME/remote-sim-viz/.venv"
"$HOME/remote-sim-viz/.venv/bin/python" -m pip install --upgrade pip
"$HOME/remote-sim-viz/.venv/bin/python" -m pip install \
  'numpy==1.26.4' 'mujoco==3.13.0' 'Pillow>=10,<12'
```

先测试 EGL 是否能返回 RGB 图像，**不需要把 `DISPLAY` 设置成 `:1`**：

```bash
MUJOCO_GL=egl PYOPENGL_PLATFORM=egl \
"$HOME/remote-sim-viz/.venv/bin/python" - <<'EGL_TEST'
import mujoco
xml = """<mujoco><worldbody>
<light pos="0 0 3"/>
<geom type="plane" size="2 2 0.1"/>
<geom type="sphere" pos="0 0 0.5" size="0.15"/>
</worldbody></mujoco>"""
model = mujoco.MjModel.from_xml_string(xml)
data = mujoco.MjData(model)
renderer = mujoco.Renderer(model, height=256, width=256)
try:
    renderer.update_scene(data)
    image = renderer.render()
    print('MuJoCo:', mujoco.__version__)
    print('Render result:', image.shape)
    print('EGL rendering PASS')
finally:
    renderer.close()
EGL_TEST
```

**成功标志**：`Render result: (256, 256, 3)` 和 `EGL rendering PASS`。如果失败，先检查 GPU 驱动、EGL 库、运行环境，不要反复重装 VNC。多 GPU 机器可另行设置 `MUJOCO_EGL_DEVICE_ID` 指定 EGL 枚举设备，但这个编号**未必与 CUDA 可见设备编号一致**。

### 7.3.1 运行能在 Windows 上看到的真实 MuJoCo 场景

下面的程序用 MuJoCo 生成一颗移动的球，并将 `mujoco.Renderer.render()` 的真实 RGB 图像持续写入 `latest.jpg`。为了让预览程序不会读到半写入的文件，使用 `os.replace` 原子替换。

在远程 Linux 执行整段命令建立脚本：

```bash
cat > "$HOME/remote-sim-viz/demo_mujoco_egl.py" <<'MUJOCO_SCRIPT'
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
MUJOCO_SCRIPT
```

启动仿真后台会话：

```bash
tmux new-session -d -s sim-render \
  "MUJOCO_GL=egl PYOPENGL_PLATFORM=egl '$HOME/remote-sim-viz/.venv/bin/python' '$HOME/remote-sim-viz/demo_mujoco_egl.py'"
```

检查帧文件和日志：

```bash
ls -lh "$HOME/remote-sim-viz/frames/latest.jpg"
tmux capture-pane -pt sim-render | tail -n 15
```

**成功标志**：Windows VNC 的 `Remote Simulation Preview` 窗口里，看到由 MuJoCo GPU 离屏渲染的球体连续移动。此时从 Linux 仿真到 Windows 观看的全链路才算真正搭好。

> 演示约以 10 FPS 输出预览图像，实际训练更建议限频至 2–5 FPS，避免频繁 JPEG 编码或 I/O 拖慢训练。显示预览只用于观察，并不会让模型的训练速度等于 VNC 显示帧率。

### 7.4 接入自己的仿真代码

在仿真器已经得到一帧 `RGB uint8` 格式图像时，将其保存为同一路径：

```python
# 这一段应放进已有仿真/评估程序，不是独立可运行的脚本。
from pathlib import Path
from PIL import Image
import os
import time

PREVIEW_DIR = Path.home() / "remote-sim-viz" / "frames"
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
PREVIEW_FILE = PREVIEW_DIR / "latest.jpg"
PREVIEW_TMP = PREVIEW_DIR / "latest.tmp.jpg"
_last_preview_time = 0.0


def publish_preview_frame(rgb_array, fps_limit=5):
    """rgb_array: H×W×3, uint8, RGB 顺序的 NumPy 数组。"""
    global _last_preview_time
    now = time.monotonic()
    if now - _last_preview_time < 1.0 / fps_limit:
        return
    _last_preview_time = now
    Image.fromarray(rgb_array).save(PREVIEW_TMP, format="JPEG", quality=80)
    os.replace(PREVIEW_TMP, PREVIEW_FILE)

# 在仿真主循环中：
# rgb_frame = simulator.render()  # 按对应仿真 API 获取 RGB 帧
# publish_preview_frame(rgb_frame, fps_limit=5)
```

注意：

- `rgb_array` 必须是真实的 RGB 图像。如果来源是 OpenCV 的 BGR，需要先转换颜色通道。
- `fps_limit` 是预览写盘频率上限，不等于仿真或训练频率。建议初次采用 2–5 FPS，在网络和磁盘允许时增加。
- 不要在每一个高速物理时间步都编码 JPEG，避免拖慢训练。
- 查看器与仿真进程使用同一 Linux 用户时，默认文件路径最简单；使用不同用户时要单独解决目录权限。
- 如果对延迟、帧率要求较高，应该用共享内存、视频编码或流媒体替代逐帧 JPEG。

## 八、训练进程与可视化进程分开运行

建议把各组件拆开管理：

| 进程 | 功能 | 断开 SSH 后是否应继续运行 |
|---|---|---|
| `sim-xvfb` | 虚拟屏幕 | 是 |
| `sim-openbox` | 窗口管理器 | 是 |
| `sim-vnc` | VNC 服务 | 是 |
| `sim-preview` | 显示仿真预览图 | 是 |
| 自己的训练任务 | 模型训练、策略评估、仿真 | 是 |
| Windows SSH 隧道 | 访问 VNC | Windows 断开后不需要维持 |

训练示例：

```bash
# 在 Linux 端启动持久终端
tmux new -s simulation-training

# 在 tmux 中激活项目对应的 Python 环境并启动任务
# source /path/to/venv/bin/activate
# python train_or_evaluate.py
```

训练中按下 `Ctrl+B`、松开后按 `D`，可退出 tmux 而不中断任务。重新连接：

```bash
tmux attach -t simulation-training
```

检查所有 tmux 会话：

```bash
tmux ls
```

查看服务器当前 GPU、CPU 和内存负载时可使用项目适配的监控命令，例如 `nvidia-smi`（仅适用于已安装 NVIDIA 驱动的机器）或 `top`。

**特别说明：**VNC 看到了仿真画面，不代表仿真画面正在由 GPU 直接驱动桌面窗口。EGL 方案中，GPU/仿真计算与 Tk/VNC 预览是两条独立执行链，预览只消费仿真输出帧。

## 九、常见问题及处理

| 现象 | 可能原因 | 排查方式 |
|---|---|---|
| VNC 连接被拒绝 | VNC 服务没有运行或 SSH 隧道没有建立 | Linux：`ss -ltn \| grep 5901`；Windows 检查 `ssh -N -L` 窗口是否存活 |
| VNC 画面全黑/空白 | Xvfb 未启动、Openbox/测试窗口未运行，或 EGL 未将帧送入预览窗口 | `tmux ls`；`DISPLAY=:1 xdpyinfo`；检查 `latest.jpg` 更新时间 |
| `Can't open display :1` | `DISPLAY`、`XAUTHORITY` 不一致或 Xvfb 未启动 | `echo "$DISPLAY"`；`echo "$XAUTHORITY"`；`xdpyinfo -display :1` |
| `Address already in use` | `:1` 或 `5901` 被其他进程占用 | `ps aux \| grep Xvfb`；`ss -ltn \| grep 5901`；换显示号或端口 |
| 已连接 VNC，但看不到仿真 | 程序使用 EGL 离屏模式，未创建 X11 窗口 | 使用第七节图片桥接，不要只改 VNC 配置 |
| VNC 能看到 GUI，但 3D 很慢 | Xvfb 走 Mesa 软件 OpenGL | 走 EGL 离屏渲染 + 图片桥接，或评估 VirtualGL/TurboVNC |
| `ModuleNotFoundError: PIL` | 混用了 Conda Python 与系统 Python | 使用 `/usr/bin/python3` 运行教程的查看器；仿真程序使用自己的虚拟环境 |
| 图像颜色异常 | BGR/RGB 顺序不一致 | OpenCV 图像在发布前转换为 RGB |
| 仿真卡顿 | JPEG 编码太频繁、磁盘慢、网络差 | 降低预览帧率和画面分辨率；必要时改用视频流 |

### 查看后台日志或进程

```bash
tmux ls
ps aux | grep -E 'Xvfb|x11vnc|openbox|frame_viewer' | grep -v grep
```

如果某个会话没有创建成功，可以尝试把对应命令**暂时放到前台运行**，这样报错会直接显示出来，例如：

```bash
DISPLAY=:1 XAUTHORITY="$HOME/.Xauthority-sim" openbox
```

退出前台测试按 `Ctrl+C`；不要重复启动已存在的同名进程。

### 停止所有虚拟桌面组件

```bash
for session in sim-preview sim-test-window sim-vnc sim-openbox sim-xvfb; do
    tmux kill-session -t "$session" 2>/dev/null || true
done
```

这不会自动终止其他 tmux 会话中的训练任务。

## 十、安全及部署建议

1. **不要直接暴露 TCP 5901 到公网。** x11vnc 使用 `-localhost`，Windows 通过 SSH 端口转发连接即可。
2. 不建议为了可视化而关闭防火墙、允许匿名 VNC 或将 `Xvfb` 配置成对网络开放访问。
3. 使用 Linux 普通用户运行显示服务和训练作业，避免图形应用默认以 root 权限运行。
4. 在多人共享服务器上，每位用户应使用各自的显示号、VNC 端口、VNC 密码和 X11 授权文件。
5. `Xvfb` 与 `x11vnc` 会话适合调试和研究使用；需要开机自动运行时，可进一步整理为用户级 `systemd` 服务。
