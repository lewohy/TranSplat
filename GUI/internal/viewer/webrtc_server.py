import asyncio
import json
import math
import fractions
import threading
import time
import traceback
from typing import Optional

import numpy as np
import torch

from internal.cameras.cameras import Cameras
from internal.utils.graphics_utils import fov2focal


HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>TranSplat WebRTC Preview</title>
  <style>
    html, body {
      margin: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: #111;
      color: #eee;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    video {
      width: 100vw;
      height: 100vh;
      object-fit: contain;
      background: #111;
      display: block;
    }
    #viserPanel {
      position: fixed;
      top: 0;
      right: 0;
      width: min(460px, 42vw);
      height: 100vh;
      border: 0;
      z-index: 10;
      box-shadow: -8px 0 24px rgba(0, 0, 0, 0.28);
      background: #111;
    }
    #togglePanel {
      position: fixed;
      top: 12px;
      right: min(472px, calc(42vw + 12px));
      z-index: 11;
      border: 0;
      border-radius: 4px;
      padding: 6px 8px;
      background: rgba(0, 0, 0, 0.62);
      color: #eee;
      font-size: 12px;
      cursor: pointer;
    }
    body.panelHidden #viserPanel {
      display: none;
    }
    body.panelHidden #togglePanel {
      right: 12px;
    }
    #status {
      position: fixed;
      left: 12px;
      bottom: 12px;
      padding: 6px 8px;
      border-radius: 4px;
      background: rgba(0, 0, 0, 0.55);
      font-size: 12px;
      color: #ddd;
    }
    #hint {
      position: fixed;
      right: 12px;
      bottom: 12px;
      padding: 6px 8px;
      border-radius: 4px;
      background: rgba(0, 0, 0, 0.55);
      font-size: 12px;
      color: #ddd;
      user-select: none;
    }
  </style>
</head>
<body>
  <video id="video" autoplay playsinline muted></video>
  <button id="togglePanel">Hide Viser</button>
  <iframe id="viserPanel" src="__VISER_URL__"></iframe>
  <div id="status">connecting</div>
  <div id="hint">drag orbit · wheel zoom · shift/right drag pan</div>
  <script>
    const statusEl = document.getElementById("status");
    const videoEl = document.getElementById("video");
    const togglePanel = document.getElementById("togglePanel");
    const initialCenter = __CENTER__;
    const initialDistance = __DISTANCE__;
    let dc = null;
    let yaw = 0.0;
    let pitch = 0.25;
    let distance = initialDistance;
    let target = [...initialCenter];
    const up = [0, 0, 1];
    const fov = 0.75;
    let pointerDown = false;
    let lastX = 0;
    let lastY = 0;
    let panMode = false;

    togglePanel.addEventListener("click", () => {
      document.body.classList.toggle("panelHidden");
      togglePanel.textContent = document.body.classList.contains("panelHidden")
        ? "Show Viser"
        : "Hide Viser";
    });

    function sub(a, b) { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; }
    function add(a, b) { return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]; }
    function mul(a, s) { return [a[0] * s, a[1] * s, a[2] * s]; }
    function cross(a, b) {
      return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
      ];
    }
    function norm(a) {
      const n = Math.hypot(a[0], a[1], a[2]) || 1.0;
      return [a[0] / n, a[1] / n, a[2] / n];
    }

    function cameraPosition() {
      const cp = Math.cos(pitch);
      const dir = [
        cp * Math.cos(yaw),
        cp * Math.sin(yaw),
        Math.sin(pitch),
      ];
      return add(target, mul(dir, distance));
    }

    function sendCamera() {
      if (dc === null || dc.readyState !== "open") return;
      const position = cameraPosition();
      dc.send(JSON.stringify({
        type: "camera",
        position,
        look_at: target,
        up,
        fov,
        aspect: Math.max(0.1, window.innerWidth / Math.max(1, window.innerHeight)),
      }));
    }

    function pan(dx, dy) {
      const position = cameraPosition();
      const forward = norm(sub(target, position));
      const right = norm(cross(forward, up));
      const cameraUp = norm(cross(right, forward));
      const scale = distance * 0.0015;
      target = add(target, add(mul(right, -dx * scale), mul(cameraUp, dy * scale)));
    }

    window.addEventListener("contextmenu", (event) => event.preventDefault());
    window.addEventListener("pointerdown", (event) => {
      pointerDown = true;
      lastX = event.clientX;
      lastY = event.clientY;
      panMode = event.shiftKey || event.button === 2;
      videoEl.setPointerCapture(event.pointerId);
    });
    window.addEventListener("pointerup", (event) => {
      pointerDown = false;
      try { videoEl.releasePointerCapture(event.pointerId); } catch (_) {}
    });
    window.addEventListener("pointermove", (event) => {
      if (!pointerDown) return;
      const dx = event.clientX - lastX;
      const dy = event.clientY - lastY;
      lastX = event.clientX;
      lastY = event.clientY;
      if (panMode || event.shiftKey) {
        pan(dx, dy);
      } else {
        yaw -= dx * 0.005;
        pitch = Math.max(-1.45, Math.min(1.45, pitch + dy * 0.005));
      }
      sendCamera();
    });
    window.addEventListener("wheel", (event) => {
      event.preventDefault();
      distance *= Math.exp(event.deltaY * 0.001);
      distance = Math.max(0.01, distance);
      sendCamera();
    }, { passive: false });
    window.addEventListener("resize", sendCamera);

    async function start() {
      const pc = new RTCPeerConnection();
      dc = pc.createDataChannel("camera");
      dc.onopen = () => {
        statusEl.textContent = "controls connected";
        sendCamera();
      };
      pc.addTransceiver("video", { direction: "recvonly" });
      pc.ontrack = (event) => {
        videoEl.srcObject = event.streams[0];
        statusEl.textContent = "streaming";
      };
      pc.onconnectionstatechange = () => {
        statusEl.textContent = pc.connectionState;
      };

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      const response = await fetch("/offer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(pc.localDescription),
      });
      const answer = await response.json();
      await pc.setRemoteDescription(answer);
      setInterval(sendCamera, 250);
    }

    start().catch((err) => {
      console.error(err);
      statusEl.textContent = String(err);
    });
  </script>
</body>
</html>
"""


class ViewerVideoTrack:
    def __new__(cls, *args, **kwargs):
        from aiortc import VideoStreamTrack

        class _Track(VideoStreamTrack):
            def __init__(self, server):
                super().__init__()
                self.server = server
                self.frame_index = 0

            async def recv(self):
                from av import VideoFrame

                await asyncio.sleep(max(0.0, 1.0 / self.server.fps))
                pts = self.frame_index
                self.frame_index += 1

                image = self.server.render_frame()
                frame = VideoFrame.from_ndarray(image, format="rgb24")
                frame.pts = pts
                frame.time_base = fractions.Fraction(1, self.server.fps)
                return frame

        return _Track(*args, **kwargs)


class FastPreviewServer:
    def __init__(
        self,
        viewer,
        host: str,
        port: int,
        max_res: int = 1024,
        fps: int = 60,
    ):
        self.viewer = viewer
        self.host = host
        self.port = int(port)
        self.max_res = int(max_res)
        self.fps = int(fps)
        self.thread: Optional[threading.Thread] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.runner = None
        self.peer_connections = set()
        self._last_status_message = None
        self.camera_state_lock = threading.Lock()
        self.camera_state = self._default_camera_state()

    @property
    def display_url(self) -> str:
        host = "127.0.0.1" if self.host in ("0.0.0.0", "::") else self.host
        return f"http://{host}:{self.port}"

    def start(self):
        self.thread = threading.Thread(target=self._run_thread, daemon=True)
        self.thread.start()

    def _run_thread(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._start_async())
        self.loop.run_forever()

    async def _start_async(self):
        from aiohttp import web

        app = web.Application()
        app.router.add_get("/", self._index)
        app.router.add_post("/offer", self._offer)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        print(f"[INFO] WebRTC fast preview available at {self.display_url}")

    async def _index(self, _request):
        from aiohttp import web

        center, distance = self._initial_view()
        html = (
            HTML.replace("__CENTER__", json.dumps(center.tolist()))
            .replace("__DISTANCE__", json.dumps(float(distance)))
            .replace("__VISER_URL__", self._viser_url())
        )
        return web.Response(text=html, content_type="text/html")

    async def _offer(self, request):
        from aiohttp import web
        from aiortc import RTCSessionDescription, RTCPeerConnection

        params = await request.json()
        offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
        pc = RTCPeerConnection()
        self.peer_connections.add(pc)

        @pc.on("datachannel")
        def _on_datachannel(channel):
            @channel.on("message")
            def _on_message(message):
                if isinstance(message, bytes):
                    message = message.decode("utf-8", errors="ignore")
                try:
                    data = json.loads(message)
                except Exception:
                    return
                if data.get("type") != "camera":
                    return
                self.update_camera_state(data)

        @pc.on("connectionstatechange")
        async def _on_connectionstatechange():
            if pc.connectionState in ("failed", "closed", "disconnected"):
                await pc.close()
                self.peer_connections.discard(pc)

        pc.addTransceiver(ViewerVideoTrack(self), direction="sendonly")

        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        return web.json_response(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        )

    def _initial_view(self):
        try:
            xyz = self.viewer.gaussian_model.get_xyz.detach()
            center = xyz.mean(dim=0).cpu().numpy().astype(float)
            radius = torch.linalg.norm(xyz - xyz.mean(dim=0), dim=1).max().item()
            distance = max(float(radius) * 2.5, 1.0)
            return center, distance
        except Exception:
            center = np.asarray(getattr(self.viewer, "camera_center", [0.0, 0.0, 0.0]), dtype=float)
            return center, 3.0

    def _viser_url(self):
        host = "127.0.0.1" if self.viewer.host in ("0.0.0.0", "::") else self.viewer.host
        return f"http://{host}:{self.viewer.port}"

    def _default_camera_state(self):
        center, distance = self._initial_view() if hasattr(self, "viewer") else (np.zeros(3), 3.0)
        return {
            "position": (center + np.asarray([distance, 0.0, distance * 0.25])).tolist(),
            "look_at": center.tolist(),
            "up": [0.0, 0.0, 1.0],
            "fov": 0.75,
            "aspect": 16.0 / 9.0,
        }

    def update_camera_state(self, data):
        def vec3(name, fallback):
            value = data.get(name, fallback)
            if not isinstance(value, list) or len(value) != 3:
                return fallback
            return [float(value[0]), float(value[1]), float(value[2])]

        with self.camera_state_lock:
            current = dict(self.camera_state)
            current["position"] = vec3("position", current["position"])
            current["look_at"] = vec3("look_at", current["look_at"])
            current["up"] = vec3("up", current["up"])
            current["fov"] = float(data.get("fov", current["fov"]))
            current["aspect"] = max(0.1, float(data.get("aspect", current["aspect"])))
            self.camera_state = current

    def _make_camera_from_state(self):
        with self.camera_state_lock:
            state = dict(self.camera_state)

        aspect = max(0.1, float(state["aspect"]))
        if aspect >= 1.0:
            image_width = self.max_res
            image_height = int(image_width / aspect)
        else:
            image_height = self.max_res
            image_width = int(image_height * aspect)
        image_width = max(2, image_width - (image_width % 2))
        image_height = max(2, image_height - (image_height % 2))

        position = torch.tensor(state["position"], dtype=torch.float32)
        look_at = torch.tensor(state["look_at"], dtype=torch.float32)
        up = torch.tensor(state["up"], dtype=torch.float32)
        forward = look_at - position
        forward = forward / torch.clamp(torch.linalg.norm(forward), min=1e-6)
        up = up / torch.clamp(torch.linalg.norm(up), min=1e-6)
        right = torch.linalg.cross(forward, up)
        right = right / torch.clamp(torch.linalg.norm(right), min=1e-6)
        down = torch.linalg.cross(forward, right)
        down = down / torch.clamp(torch.linalg.norm(down), min=1e-6)

        c2w = torch.eye(4, dtype=torch.float32)
        c2w[:3, 0] = right
        c2w[:3, 1] = down
        c2w[:3, 2] = forward
        c2w[:3, 3] = position
        w2c = torch.linalg.inv(c2w)
        R = w2c[:3, :3]
        T = w2c[:3, 3]

        fov = float(state["fov"])
        fx = torch.tensor([fov2focal(fov, image_width)], dtype=torch.float32)
        return Cameras(
            R=R.unsqueeze(0),
            T=T.unsqueeze(0),
            fx=fx,
            fy=fx,
            cx=torch.tensor([image_width // 2], dtype=torch.int),
            cy=torch.tensor([image_height // 2], dtype=torch.int),
            width=torch.tensor([image_width], dtype=torch.int),
            height=torch.tensor([image_height], dtype=torch.int),
            appearance_id=torch.tensor([0], dtype=torch.int),
            normalized_appearance_id=torch.tensor([0.0], dtype=torch.float),
            time=torch.tensor([0.0], dtype=torch.float),
            distortion_params=None,
            camera_type=torch.tensor([0], dtype=torch.int),
        )[0].to_device(self.viewer.device)

    def _get_active_client_thread(self):
        for client_thread in list(getattr(self.viewer, "clients", {}).values()):
            if client_thread.last_camera is not None:
                return client_thread
        return None

    def _status_frame(self, message: str) -> np.ndarray:
        h = max(2, self.max_res - (self.max_res % 2))
        w = h
        image = np.zeros((h, w, 3), dtype=np.uint8)
        image[..., 0] = 32
        image[..., 1] = 32
        image[..., 2] = 48
        image[: max(2, h // 24), :, :] = np.array([180, 64, 64], dtype=np.uint8)
        try:
            import cv2

            cv2.putText(
                image,
                message,
                (24, max(48, h // 2)),
                cv2.FONT_HERSHEY_SIMPLEX,
                max(0.6, h / 1400.0),
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
        except Exception:
            pass
        if message != self._last_status_message:
            print(f"[WARN] WebRTC preview: {message}")
            self._last_status_message = message
        return image

    def render_frame(self) -> np.ndarray:
        render_start = time.time()
        try:
            with torch.no_grad():
                with self.viewer.render_lock:
                    camera = self._make_camera_from_state()
                    image = self.viewer.viewer_renderer.get_outputs(
                        camera,
                        valid_range=None,
                        env_bg_enabled=(
                            hasattr(self.viewer, "enable_env_background")
                            and self.viewer.enable_env_background.value
                        ),
                        env_bg_path=self.viewer.env_map_path,
                        active_sh_degree=self.viewer.gaussian_model.max_sh_degree,
                    )
                    if image.is_cuda:
                        torch.cuda.synchronize(image.device)
                    render_time = time.time() - render_start

                    prep_start = time.time()
                    image = torch.permute(image, (1, 2, 0))
                    display_image = (
                        torch.clamp(image, 0.0, 1.0)
                        .mul(255.0)
                        .to(torch.uint8)
                        .cpu()
                        .numpy()
                    )
                    h, w = display_image.shape[:2]
                    display_image = display_image[: h - (h % 2), : w - (w % 2)]
                    prep_time = time.time() - prep_start
        except Exception:
            traceback.print_exc()
            return self._status_frame("WebRTC render error; see terminal")

        total_time = time.time() - render_start
        if hasattr(self.viewer, "frame_time"):
            self.viewer.frame_time.value = (
                f"{total_time * 1000.0:.1f} ms WebRTC "
                f"(render {render_time * 1000.0:.1f}, "
                f"prep {prep_time * 1000.0:.1f})"
            )
        if hasattr(self.viewer, "fps"):
            self.viewer.fps.value = f"{(1.0 / max(total_time, 1e-6)):.1f} frame/sec"
        return display_image
