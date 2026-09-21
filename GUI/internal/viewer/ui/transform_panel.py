from dataclasses import dataclass
import numpy as np
import math
import torch
import viser
import viser.transforms as vst
from internal.viewer.ui.up_direction_folder import UpDirectionFolder
import time
import threading


@dataclass
class ModelPose:
    wxyz: np.ndarray
    position: np.ndarray

    def copy(self):
        return ModelPose(
            wxyz=self.wxyz.copy(),
            position=self.position.copy(),
        )

    def to_dict(self):
        return {
            "wxyz": self.wxyz.tolist(),
            "position": self.position.tolist(),
        }


class TransformPanel:
    def __init__(
        self,
        server: viser.ViserServer,
        viewer,
        i=0,
    ):
        self.server = server
        self.viewer = viewer
        self.model_count = len(self.viewer.model_paths)

        self.transform_control_no_handle_update = False

        # Identify target scene vs source objects (the target scene has the most points)  # Gen by Cursor
        if hasattr(self.viewer, "model_ranges") and len(self.viewer.model_ranges) > 1:  # Gen by Cursor
            counts = [end - start for start, end in self.viewer.model_ranges]  # Gen by Cursor
            self.scene_idx = int(np.argmax(counts))  # Gen by Cursor
        else:  # Gen by Cursor
            self.scene_idx = -1  # Gen by Cursor

        self.model_poses = []
        self.model_transform_controls: dict[int, viser.TransformControlsHandle] = {}
        self.model_proxy_controls: dict[int, viser.TransformControlsHandle] = {}
        self.model_size_sliders = []
        self.model_show_transform_control_checkboxes = []
        self.model_visible_checkboxes = []
        self.model_t_xyz_text_handle = []
        self.model_r_xyz_text_handle = []
        self.controls_size = None
        self.model_labels = list(self.viewer.model_names)

        # Backup current state once: this is the base state for transform composition.
        self.viewer.gaussian_model.backup()

        self.controls_size = server.gui.add_slider(
            "Transform Controls Size",
            min=0.0,
            max=10.0,
            step=0.01,
            initial_value=1.0,
        )
        self.controls_size.on_update(self._update_pose_control_size)

        for model_idx in range(self.model_count):
            self._build_model_transform_controls(model_idx)

        self.set_to_default = server.gui.add_button("Set to default")

        @self.set_to_default.on_click
        def _(event: viser.GuiEvent) -> None:
            gm = self.viewer.gaussian_model
            
            if hasattr(self.viewer, "edit_panel"):
                ep = self.viewer.edit_panel
                
                curr_xyz = gm._xyz.clone()
                curr_scaling = gm._scaling.clone()
                curr_rotation = gm._rotation.clone()
                curr_features_dc = gm._features_dc.clone()
                curr_features_rest = gm._features_rest.clone()
                
                tmp_org_xyz = gm.org_xyz
                tmp_org_scaling = gm.org_scaling
                tmp_org_rotation = gm.org_rotation
                tmp_org_features_dc = gm.org_features_dc
                tmp_org_features_rest = gm.org_features_rest
                
                gm.org_xyz = ep._orig_gaussians["xyz"]
                gm.org_scaling = ep._orig_gaussians["scaling"]
                gm.org_rotation = ep._orig_gaussians["rotation"]
                gm.org_features_dc = ep._orig_gaussians["features_dc"]
                gm.org_features_rest = ep._orig_gaussians["features_rest"]
                
                gm.apply_all_model_transforms()
                
                ep._orig_gaussians["xyz"] = gm._xyz.clone().detach()
                ep._orig_gaussians["scaling"] = gm._scaling.clone().detach()
                ep._orig_gaussians["rotation"] = gm._rotation.clone().detach()
                ep._orig_gaussians["features_dc"] = gm._features_dc.clone().detach()
                ep._orig_gaussians["features_rest"] = gm._features_rest.clone().detach()
                
                gm.org_xyz = tmp_org_xyz
                gm.org_scaling = tmp_org_scaling
                gm.org_rotation = tmp_org_rotation
                gm.org_features_dc = tmp_org_features_dc
                gm.org_features_rest = tmp_org_features_rest
                
                gm._xyz = curr_xyz
                gm._scaling = curr_scaling
                gm._rotation = curr_rotation
                gm._features_dc = curr_features_dc
                gm._features_rest = curr_features_rest

                if hasattr(gm, "_model_centers"):
                    for idx in range(self.model_count):
                        m = gm._model_ids == idx
                        import torch
                        if torch.any(m):
                            gm._model_centers[idx] = gm._xyz[m].mean(dim=0)

            # Bake current transformed state as the new base for subsequent transforms.
            self.viewer.gaussian_model.backup()
            self._reset_controls_to_identity_at_centers()
            self.viewer.viewer_renderer.gaussian_model = self.viewer.gaussian_model
            self.viewer.viewer_renderer.update_pc_features()
            self.viewer.rerender_for_all_client()

        # Backward compatibility with existing references in edit/render panels.
        self.model_show_transform_control_checkbox = (
            self.model_show_transform_control_checkboxes[0]
        )

        # UpDirectionFolder(viewer, server)  # Gen by Cursor

    def _get_model_center(self, idx: int) -> np.ndarray:
        gm = self.viewer.gaussian_model
        if hasattr(gm, "_model_centers") and idx in gm._model_centers:
            return gm._model_centers[idx].detach().cpu().numpy()
        return np.asarray(self.viewer.camera_center).copy()

    def _build_model_transform_controls(self, idx: int):
        server = self.server
        center = self._get_model_center(idx)

        is_target_scene = (idx == self.scene_idx)  # Gen by Cursor
        if is_target_scene:  # Gen by Cursor
            folder_name = f"Target Scene: {self.model_labels[idx]}"  # Gen by Cursor
        else:  # Gen by Cursor
            num_source_objects = sum(1 for i in range(self.model_count) if i != self.scene_idx)  # Gen by Cursor
            if num_source_objects > 1:  # Gen by Cursor
                folder_name = f"Source Object {idx}: {self.model_labels[idx]}"  # Gen by Cursor
            else:  # Gen by Cursor
                folder_name = f"Source Object: {self.model_labels[idx]}"  # Gen by Cursor
                                                                         # Gen by Cursor
        with server.gui.add_folder(folder_name, visible=not is_target_scene):  # Gen by Cursor
            show_checkbox = server.gui.add_checkbox(
                "use Transform",
                initial_value=False,
            )
            self._make_show_transform_control_checkbox_callback(idx, show_checkbox)
            self.model_show_transform_control_checkboxes.append(show_checkbox)

            visible_checkbox = server.gui.add_checkbox(
                "Visible",
                initial_value=True,
            )
            self._make_visible_checkbox_callback(idx, visible_checkbox)
            self.model_visible_checkboxes.append(visible_checkbox)

            size_slider = server.gui.add_number(
                "Splat Size",
                min=0.0,
                step=0.01,
                initial_value=1.0,
            )
            self._make_size_slider_callback(idx, size_slider)
            self.model_size_sliders.append(size_slider)

            self.model_poses.append(
                ModelPose(
                    np.asarray([1.0, 0.0, 0.0, 0.0]),
                    center.copy(),
                )
            )

            t_xyz_text_handle = server.gui.add_vector3(
                "Translation",
                initial_value=tuple(center.tolist()),
                step=0.01,
            )
            self._make_t_xyz_text_callback(idx, t_xyz_text_handle)
            self.model_t_xyz_text_handle.append(t_xyz_text_handle)

            r_xyz_text_handle = server.gui.add_vector3(
                "Rotation",
                initial_value=(0.0, 0.0, 0.0),
                step=0.01,
            )
            self._make_r_xyz_text_callback(idx, r_xyz_text_handle)
            self.model_r_xyz_text_handle.append(r_xyz_text_handle)

            if not is_target_scene:  # Gen by Cursor
                self._show_model_proxy_handle(idx)  # Gen by Cursor

            copy_transform_button = server.gui.add_button("Copy Transform 4x4")

            @copy_transform_button.on_click
            def _(event: viser.GuiEvent) -> None:
                matrix_text = self._matrix_to_text(
                    self._pose_to_matrix4(self.model_poses[idx])
                )
                copied = self._copy_text_to_clipboard(matrix_text)
                if event.client is None:
                    return
                with event.client.gui.add_modal("Transform Matrix") as modal:
                    if copied:
                        event.client.gui.add_markdown("Copied 4x4 matrix to clipboard.")
                    else:
                        event.client.gui.add_markdown(
                            "Clipboard copy unavailable; matrix shown below."
                        )
                    event.client.gui.add_markdown(f"```\n{matrix_text}\n```")
                    close_button = event.client.gui.add_button("Close")

                    @close_button.on_click
                    def _(_) -> None:
                        modal.close()

            focus_camera_button = server.gui.add_button("Focus Camera on Model")
            @focus_camera_button.on_click
            def _(event: viser.GuiEvent) -> None:
                if event.client is None:
                    return
                pos = self.model_poses[idx].position
                with event.client.atomic():
                    event.client.camera.look_at = np.array(pos)

            move_to_camera_button = server.gui.add_button("Move to Camera Center")
            @move_to_camera_button.on_click
            def _(event: viser.GuiEvent) -> None:
                if event.client is None:
                    return
                pos = np.array(event.client.camera.look_at)
                self.model_poses[idx].position = pos
                self.set_model_transform_control_value(idx, self.model_poses[idx].wxyz, pos)
                self.model_t_xyz_text_handle[idx].value = tuple(pos)
                self._transform_model(idx)
                self.viewer.rerender_for_all_client()

            align_to_camera_button = server.gui.add_button("Align Rotation to Camera")
            @align_to_camera_button.on_click
            def _(event: viser.GuiEvent) -> None:
                if event.client is None:
                    return
                cam_wxyz = np.array(event.client.camera.wxyz)
                self.model_poses[idx].wxyz = cam_wxyz
                self.set_model_transform_control_value(idx, cam_wxyz, self.model_poses[idx].position)
                self.model_r_xyz_text_handle[idx].value = self.quaternion_to_euler_angle_vectorized2(cam_wxyz)
                self._transform_model(idx)
                self.viewer.rerender_for_all_client()

    def any_transform_enabled(self) -> bool:
        return any(cb.value for cb in self.model_show_transform_control_checkboxes)

    def _reset_controls_to_identity_at_centers(self):
        for idx in range(self.model_count):
            center = self._get_model_center(idx)
            self.model_poses[idx] = ModelPose(np.asarray([1.0, 0.0, 0.0, 0.0]), center)
            self.model_size_sliders[idx].value = 1.0
            self.model_t_xyz_text_handle[idx].value = tuple(center.tolist())
            self.model_r_xyz_text_handle[idx].value = (0.0, 0.0, 0.0)
            if idx in self.model_transform_controls:
                self.set_model_transform_control_value(
                    idx, np.asarray([1.0, 0.0, 0.0, 0.0]), center
                )

    def _make_size_slider_callback(
        self,
        idx: int,
        slider: viser.GuiInputHandle,
    ):
        @slider.on_update
        def _(event: viser.GuiEvent) -> None:
            with self.server.atomic():
                self._transform_model(idx)
                self.viewer.rerender_for_all_client()

    def set_model_transform_control_value(
        self, idx, wxyz: np.ndarray, position: np.ndarray
    ):
        self.transform_control_no_handle_update = True
        try:
            if idx in self.model_transform_controls:
                self.model_transform_controls[idx].wxyz = wxyz
                self.model_transform_controls[idx].position = position
            if idx in self.model_proxy_controls:
                self.model_proxy_controls[idx].wxyz = wxyz
                self.model_proxy_controls[idx].position = position
        finally:
            self.transform_control_no_handle_update = False

    def _show_model_proxy_handle(self, idx: int):
        model_pose = self.model_poses[idx]
        try:
            controls = self.server.add_transform_controls(
                f"/model_proxy/{idx}",
                scale=self.controls_size.value,
                wxyz=model_pose.wxyz,
                position=model_pose.position,
                disable_axes=True,
                disable_sliders=True,
                disable_rotations=True,
            )
            self._make_transform_controls_callback(idx, controls, is_proxy=True)
            self.model_proxy_controls[idx] = controls
        except TypeError:
            pass # Older viser versions might not support disable_* args

    def _make_transform_controls_callback(
        self,
        idx,
        controls: viser.TransformControlsHandle,
        is_proxy: bool = False,
    ) -> None:
        throttle_timer = [None]
        last_update = [0.0]

        @controls.on_update
        def _(event: viser.GuiEvent) -> None:
            if self.transform_control_no_handle_update is True:
                return

            if is_proxy and not self.model_show_transform_control_checkboxes[idx].value:
                with self.server.atomic():
                    for i, cb in enumerate(self.model_show_transform_control_checkboxes):
                        cb.value = (i == idx)

            model_pose = self.model_poses[idx]
            model_pose.wxyz = controls.wxyz
            model_pose.position = controls.position

            if is_proxy and idx in self.model_transform_controls:
                self.transform_control_no_handle_update = True
                self.model_transform_controls[idx].position = controls.position
                self.model_transform_controls[idx].wxyz = controls.wxyz
                self.transform_control_no_handle_update = False
            elif not is_proxy and idx in self.model_proxy_controls:
                self.transform_control_no_handle_update = True
                self.model_proxy_controls[idx].position = controls.position
                self.model_proxy_controls[idx].wxyz = controls.wxyz
                self.transform_control_no_handle_update = False

            self.model_t_xyz_text_handle[idx].value = model_pose.position.tolist()
            self.model_r_xyz_text_handle[idx].value = (
                self.quaternion_to_euler_angle_vectorized2(model_pose.wxyz)
            )

            now = time.time()
            def do_update():
                last_update[0] = time.time()
                self._transform_model(idx)
                self.viewer.rerender_for_all_client()

            if now - last_update[0] > 0.08:  # approx 12.5 fps rate limit for heavy model transform
                if throttle_timer[0] is not None:
                    throttle_timer[0].cancel()
                do_update()
            else:
                if throttle_timer[0] is not None:
                    throttle_timer[0].cancel()
                throttle_timer[0] = threading.Timer(0.08, do_update)
                throttle_timer[0].start()

    def _show_model_transform_handle(
        self,
        idx: int,
    ):
        model_pose = self.model_poses[idx]
        controls = self.server.add_transform_controls(
            f"/model_transform/{idx}",
            scale=self.controls_size.value,
            wxyz=model_pose.wxyz,
            position=model_pose.position,
        )
        self._make_transform_controls_callback(idx, controls)
        self.model_transform_controls[idx] = controls

    def _make_show_transform_control_checkbox_callback(
        self,
        idx: int,
        checkbox: viser.GuiInputHandle,
    ):
        @checkbox.on_update
        def _(event: viser.GuiEvent) -> None:
            if checkbox.value is True:
                self._show_model_transform_handle(idx)
                if idx in self.model_proxy_controls:
                    self.model_proxy_controls[idx].remove()
                    del self.model_proxy_controls[idx]
            else:
                if idx in self.model_transform_controls:
                    self.model_transform_controls[idx].remove()
                    del self.model_transform_controls[idx]
                self._show_model_proxy_handle(idx)

    def _make_visible_checkbox_callback(
        self,
        idx: int,
        checkbox: viser.GuiInputHandle,
    ):
        @checkbox.on_update
        def _(event: viser.GuiEvent) -> None:
            if not hasattr(self.viewer.gaussian_model, "hidden_models"):
                self.viewer.gaussian_model.hidden_models = set()
            if checkbox.value:
                self.viewer.gaussian_model.hidden_models.discard(idx)
            else:
                self.viewer.gaussian_model.hidden_models.add(idx)
            
            self.viewer.viewer_renderer.update_pc_features()
            self.viewer.rerender_for_all_client()

    def _update_pose_control_size(self, _):
        with self.server.atomic():
            active_indices = list(self.model_transform_controls.keys())
            for i in active_indices:
                self.model_transform_controls[i].remove()
                self._show_model_transform_handle(i)

    def _transform_model(self, idx):
        model_pose = self.model_poses[idx]
        is_relighting = getattr(self.viewer.edit_panel, "_is_relighting_active", False)

        if is_relighting:
            self.viewer.gaussian_model._ensure_backup_and_states()
            device = self.viewer.gaussian_model.org_xyz.device
            dtype = self.viewer.gaussian_model.org_xyz.dtype
            self.viewer.gaussian_model._model_transform_states[int(idx)] = {
                "scale": float(self.model_size_sliders[idx].value),
                "wxyz": torch.tensor(model_pose.wxyz, device=device, dtype=dtype),
                "position": torch.tensor(model_pose.position, device=device, dtype=dtype),
            }
            # Skip updating _xyz and rerendering!
            return

        self.viewer.gaussian_model.transform_with_vectors(
            idx,
            scale=self.model_size_sliders[idx].value,
            r_wxyz=model_pose.wxyz,
            t_xyz=model_pose.position,
        )
        self.viewer.viewer_renderer.gaussian_model = self.viewer.gaussian_model
        self.viewer.viewer_renderer.update_pc_features()
        # Optional dynamic relight: if enabled in the relight panel, schedule
        # a debounced relight pass using the current HDR environment.
        if hasattr(self.viewer, "edit_panel") and hasattr(
            self.viewer.edit_panel, "request_dynamic_relight"
        ):
            self.viewer.edit_panel.request_dynamic_relight()

    def _make_t_xyz_text_callback(
        self,
        idx: int,
        handle: viser.GuiInputHandle,
    ):
        @handle.on_update
        def _(event: viser.GuiEvent) -> None:
            if event.client is None:
                return

            with self.server.atomic():
                t = np.asarray(handle.value)
                if idx in self.model_transform_controls:
                    self.model_transform_controls[idx].position = t
                self.model_poses[idx].position = t

                self._transform_model(idx)
                self.viewer.rerender_for_all_client()

    def _make_r_xyz_text_callback(
        self,
        idx: int,
        handle: viser.GuiInputHandle,
    ):
        @handle.on_update
        def _(event: viser.GuiEvent) -> None:
            if event.client is None:
                return

            with self.server.atomic():
                radians = np.radians(np.asarray(handle.value))
                so3 = vst.SO3.from_rpy_radians(*radians.tolist())
                wxyz = np.asarray(so3.wxyz)
                if idx in self.model_transform_controls:
                    self.model_transform_controls[idx].wxyz = wxyz
                self.model_poses[idx].wxyz = wxyz

            self._transform_model(idx)
            self.viewer.rerender_for_all_client()

    @staticmethod
    def quaternion_to_euler_angle_vectorized2(wxyz):
        xyzw = np.zeros_like(wxyz)
        xyzw[[0, 1, 2, 3]] = wxyz[[1, 2, 3, 0]]
        euler_radians = vst.SO3.from_quaternion_xyzw(xyzw).as_rpy_radians()
        return (
            math.degrees(euler_radians.roll),
            math.degrees(euler_radians.pitch),
            math.degrees(euler_radians.yaw),
        )

    @staticmethod
    def _pose_to_matrix4(model_pose: ModelPose) -> np.ndarray:
        R = np.asarray(vst.SO3(model_pose.wxyz).as_matrix())
        M = np.eye(4, dtype=np.float64)
        M[:3, :3] = R
        M[:3, 3] = np.asarray(model_pose.position)
        return M

    @staticmethod
    def _matrix_to_text(M: np.ndarray) -> str:
        rows = []
        for r in range(4):
            rows.append(" ".join([f"{float(M[r, c]):.9f}" for c in range(4)]))
        return "\n".join(rows)

    @staticmethod
    def _copy_text_to_clipboard(text: str) -> bool:
        try:
            pyperclip = __import__("pyperclip")
            pyperclip.copy(text)
            return True
        except Exception:
            return False