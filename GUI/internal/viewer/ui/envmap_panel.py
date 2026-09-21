import math
import os
import cv2
import threading
from typing import Optional
import numpy as np
import viser
from internal.utils.envmap_hdr import infer_hdr, estimate_qmax_from_ldr_envmap

class EnvMapPanel:
    def __init__(self, server, viewer):
        self.viewer = viewer
        self.server : viser.ViserServer = server

        self.envmap_output_dir = "env_map"
        self.envmap_cubemap_size = 450
        self.envmap_pano_width = 1024
        self.envmap_pano_height = 512
        self.envmap_scene_idx = 0
        self.envmap_object_idx = 1
        self._capture_lock = threading.Lock()
        self._capture_pending = False
        # Locked qmax: calibrated once from the first capture or the source HDR,
        # then held fixed for all subsequent captures in the same session so that
        # moving the object around the scene does not cause sudden brightness jumps.
        # Reset to None whenever the source HDR changes or the user clicks "Reset".
        self._locked_qmax: Optional[float] = None
        self._locked_qmax_label: str = ""

        if len(self.viewer.model_ranges) < 2:
            return
        self._init_envmap_defaults()
        self._setup_envmap_section()

    def _init_envmap_defaults(self):
        counts = [end - start for start, end in self.viewer.model_ranges]
        scene_idx = int(np.argmax(counts))
        object_idx = int(np.argmin(counts))
        if scene_idx == object_idx and len(counts) > 1:
            object_idx = 1 if scene_idx == 0 else 0

        self.envmap_scene_idx = scene_idx
        self.envmap_object_idx = object_idx
        self.envmap_model_labels = [
            f"{i}: {name} ({count} pts)"
            for i, (name, count) in enumerate(zip(self.viewer.model_names, counts))
        ]
        self.envmap_label_to_index = {
            label: idx for idx, label in enumerate(self.envmap_model_labels)
        }

    def _setup_envmap_section(self):
        """Attach Env Map capture + preview UI into the current folder context.
        This mirrors the Env Map tab UI but is intended to live as its own
        section inside the General tab.
        """
        def _load_env_map_preview(env_map_path: Optional[str]) -> np.ndarray:
            if not env_map_path or not os.path.exists(env_map_path):
                return np.zeros((512, 512, 3), dtype=np.uint8)

            env_map = cv2.imread(env_map_path, cv2.IMREAD_COLOR)
            if env_map is None:
                return np.zeros((512, 512, 3), dtype=np.uint8)
            return cv2.cvtColor(env_map, cv2.COLOR_BGR2RGB)

        gui = self.server.gui

        self.envmap_output_dir_text = gui.add_text(
            "Output Dir",
            initial_value=self.envmap_output_dir,
        )
        self.envmap_cubemap_size_number = gui.add_number(
            "Cubemap Size",
            min=64,
            step=1,
            initial_value=int(self.envmap_cubemap_size),
        )
        self.envmap_pano_width_number = gui.add_number(
            "Pano Width",
            min=128,
            step=1,
            initial_value=int(self.envmap_pano_width),
        )
        self.envmap_pano_height_number = gui.add_number(
            "Pano Height",
            min=64,
            step=1,
            initial_value=int(self.envmap_pano_height),
        )
        model_labels = tuple(getattr(self, "envmap_model_labels", []))
        self.envmap_scene_model_dropdown = gui.add_dropdown(
            "Scene Model",
            model_labels,
        )
        self.envmap_object_model_dropdown = gui.add_dropdown(
            "Object Model",
            model_labels,
        )
        if model_labels:
            self.envmap_scene_model_dropdown.value = model_labels[self.envmap_scene_idx]
            self.envmap_object_model_dropdown.value = model_labels[self.envmap_object_idx]
            
        self.qmax_scene_label = gui.add_markdown("*Lighting: — (not calibrated yet)*")
        self.envmap_capture_button = gui.add_button("Capture Env Map + Relight", color="green")
        self.qmax_reset_button = gui.add_button("Reset Lighting Calibration")
            
        self.envmap_preview_image = gui.add_image(
            np.zeros((512, 512, 3), dtype=np.uint8),
            label="Sampled Envmap Preview",  # Gen by Cursor
            format="png",
        )

        @self.qmax_reset_button.on_click
        def _(_event):
            self._locked_qmax = None
            self._locked_qmax_label = ""
            with self.server.atomic():
                self.qmax_scene_label.content = "*Lighting: — (reset, will recalibrate on next capture)*"

        def _calibrate_qmax(ldr_path: str, source_hdr_path: str):
            """Return (qmax, label) for this session.

            Two strategies tried in order:
            1. Source-HDR anchor: derive qmax so that the peak of the target HDR
               aligns with the peak of the source HDR.  This is physically correct
               because the source HDR is already in calibrated linear-light units —
               the same scale we want for the target.
            2. Scene classifier fallback: used when the source HDR is unavailable
               or unreadable.
            """
            # Strategy 1 — source HDR anchor
            if source_hdr_path and os.path.exists(source_hdr_path):
                src = cv2.imread(source_hdr_path, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_COLOR)
                if src is not None:
                    src = src.astype(np.float32)
                    src_lum = (
                        0.2126 * src[:, :, 2]
                        + 0.7152 * src[:, :, 1]
                        + 0.0722 * src[:, :, 0]
                    )
                    valid = src_lum[src_lum > 1e-6]
                    src_p99 = float(np.percentile(valid, 99)) if len(valid) else 1.0
                    # qmax = log2(source_p99) makes the brightest 1 % of the target HDR
                    # match the brightest 1 % of the source HDR when gain_map ≈ 1.
                    qmax = round(math.log2(max(src_p99, 1.0)), 1)
                    qmax = float(np.clip(qmax, 1.0, 24.0))
                    label = f"source-anchored (src p99={src_p99:.1f} nits)"
                    return qmax, label

            # Strategy 2 — scene classifier
            est = estimate_qmax_from_ldr_envmap(ldr_path)
            return est.qmax, est.scene_type

        def _set_envmap_status(text, color=None):
            clients = list(self.server.get_clients().values())
            if clients:
                kwargs = {}
                if color is not None:
                    kwargs["color"] = color
                clients[0].add_notification(
                    title="EnvMap",
                    body=text,
                    auto_close_seconds=5,
                    **kwargs,
                )
            else:
                print(f"[EnvMap] {text}")

        def _run_capture_once():
            if not self.viewer.edit_panel.env_map_source_path_text.value:
                _set_envmap_status(
                    "A source environment map is required before capturing.",
                    color="red",
                )
                return

            output_dir = self.envmap_output_dir_text.value
            cubemap_size = int(self.envmap_cubemap_size_number.value)
            pano_width = int(self.envmap_pano_width_number.value)
            pano_height = int(self.envmap_pano_height_number.value)
            scene_label = self.envmap_scene_model_dropdown.value
            object_label = self.envmap_object_model_dropdown.value
            scene_idx = self.envmap_label_to_index.get(scene_label, 0)
            object_idx = self.envmap_label_to_index.get(object_label, 1)
            self.viewer.selected_model_idx = object_idx
            if scene_idx == object_idx:
                with self.server.atomic():
                    _set_envmap_status("Scene and object models must be different.")
                return

            with self.server.atomic():
                _set_envmap_status("Capturing env map...")

            try:
                from internal.utils.envmap_sampling import generate_env_map

                out_pano = generate_env_map(
                    self.viewer.gaussian_model,
                    self.viewer.model_ranges,
                    self.viewer.background_color,
                    output_dir=output_dir,
                    scene_idx=scene_idx,
                    object_idx=object_idx,
                    cubemap_size=cubemap_size,
                    pano_width=pano_width,
                    pano_height=pano_height,
                )

                equirect_ldr = os.path.join(output_dir, "out_equirect.png")
                if self._locked_qmax is None:
                    # First capture in this session: calibrate qmax and lock it.
                    # Prefer calibrating from the source HDR so the scale is anchored
                    # to the same luminance units as the source environment.
                    source_path = self.viewer.edit_panel.env_map_source_path_text.value
                    chosen_qmax, cal_label = _calibrate_qmax(equirect_ldr, source_path)
                    self._locked_qmax = chosen_qmax
                    self._locked_qmax_label = cal_label
                    with self.server.atomic():
                        self.qmax_scene_label.content = (
                            f"*Lighting calibrated: **{cal_label}** "
                            f"→ qmax={chosen_qmax} (locked)*"
                        )
                else:
                    # Subsequent captures: reuse locked qmax to keep brightness stable.
                    chosen_qmax = self._locked_qmax
                    with self.server.atomic():
                        self.qmax_scene_label.content = (
                            f"*Lighting: **{self._locked_qmax_label}** "
                            f"→ qmax={chosen_qmax} (locked — click Reset to recalibrate)*"
                        )

                infer_hdr(
                    input_path=output_dir,
                    out_dir=output_dir,
                    preset="synthetic",
                    qmax=chosen_qmax,
                )
                with self.server.atomic():
                    _set_envmap_status(f"Saved images (SDR + HDR) to {output_dir}")
                    self.envmap_preview_image.image = _load_env_map_preview(out_pano)
                
                target_hdr_path = os.path.join(output_dir, "out_equirect.hdr")
                self.viewer.edit_panel.env_map_target_path_text.value = target_hdr_path
                self.viewer.edit_panel.register_object_local_target_env(target_hdr_path)
                if self.viewer.edit_panel.env_map_source_path_text.value:
                    self.viewer.edit_panel.trigger_relight(target_env_object_local=True)

            except Exception as exc:
                with self.server.atomic():
                    print("Failed")
                    _set_envmap_status(f"Env map failed: {exc}", color="red")

        def trigger_capture_and_relight(client=None):
            if not self._capture_lock.acquire(blocking=False):
                self._capture_pending = True
                return

            try:
                while True:
                    self._capture_pending = False
                    _run_capture_once()
                    if not self._capture_pending:
                        break
            finally:
                self._capture_lock.release()

        self.trigger_capture_and_relight = trigger_capture_and_relight

        @self.envmap_capture_button.on_click
        def _(_event: viser.GuiEvent) -> None:
            trigger_capture_and_relight(_event.client)

        # When the user loads a different source HDR the scale anchor changes,
        # so drop the cached qmax so the next capture recalibrates.
        @self.viewer.edit_panel.env_map_source_path_text.on_update
        def _(_event) -> None:
            if self._locked_qmax is not None:
                self._locked_qmax = None
                self._locked_qmax_label = ""
                with self.server.atomic():
                    self.qmax_scene_label.content = (
                        "*Lighting: — (source changed, will recalibrate on next capture)*"
                    )
