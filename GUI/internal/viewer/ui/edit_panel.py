import traceback
import datetime
import os
import os.path

import torch
from torch import nn
import numpy as np
import viser
import viser.transforms as vtf
import re
import threading
import time
import trimesh
from typing import Optional
from internal.viewer import MeshExporter, GaussianModelforViewer as GaussianModel
from internal.utils import relight
import cv2

class EditPanel:
    def __init__(
        self,
        server: viser.ViserServer,
        viewer,
        only_relight: bool = False,
    ):
        self.server = server
        self.viewer = viewer
        self.C0 = 0.28209479177387814
        self.mesh = None
        self.mesh_path = None
        self.env_map_preview_image = None
        self.env_map_preview_status = None
        self._dynamic_relight_thread = None
        self._dynamic_relight_last_request = 0.0
        self._dynamic_relight_lock = threading.Lock()
        self._relight_processing_lock = threading.Lock()
        self._object_local_target_env_paths = set()
        self.auto_relight_enabled = False

        if only_relight:
            self._setup_relight_folder()
            self._capture_original()
            return

        # build the GUI sections
        self._setup_gaussian_edit_folder()
        self._setup_save_gaussian_folder()
        # self._setup_mesh_export_folder()
        self._setup_relight_folder()
        # self.export_mesh_block()

        # save baseline state after GUI is ready
        self._capture_original()

    # ------------------------------------------------------------------------
    # model backup/restore utilities
    # ------------------------------------------------------------------------
    def _capture_original(self):
        """Store a deep copy of the current gaussian model state.

        This snapshot is used for both the automatic reset before each relight
        and the manual "Reset Model" button. It should be called whenever the
        user intentionally changes the model (e.g. after deletion) so that the
        backup matches the editable state.
        """
        gm = self.viewer.gaussian_model
        self._orig_gaussians = {
            "xyz": gm.get_xyz.detach().clone(),
            "features_dc": gm._features_dc.detach().clone(),
            "features_rest": gm._features_rest.detach().clone(),
            "opacity": gm._opacity.detach().clone(),
            "scaling": gm._scaling.detach().clone(),
            "rotation": gm._rotation.detach().clone(),
        }

    def _restore_original(self):
        """Restore the gaussian model parameters from the saved snapshot."""
        if not hasattr(self, "_orig_gaussians"):
            return
        gm = self.viewer.gaussian_model
        gm._features_dc = nn.Parameter(
            self._orig_gaussians["features_dc"].clone().requires_grad_(True)
        )
        gm._features_rest = nn.Parameter(
            self._orig_gaussians["features_rest"].clone().requires_grad_(True)
        )
        gm._opacity = nn.Parameter(
            self._orig_gaussians["opacity"].clone().requires_grad_(True)
        )
        gm._scaling = nn.Parameter(
            self._orig_gaussians["scaling"].clone().requires_grad_(True)
        )
        gm._rotation = nn.Parameter(
            self._orig_gaussians["rotation"].clone().requires_grad_(True)
        )
        # geometry is normally static but restore for completeness
        gm._xyz = nn.Parameter(self._orig_gaussians["xyz"].clone().requires_grad_(True))

    def _resize_grid(self, idx):
        exist_grid = self.grids[idx][0]
        exist_grid.remove()
        self.grids[idx][0] = self.server.add_grid(
            "/grid/{}".format(idx),
            width=self.grids[idx][2].value[0],
            height=self.grids[idx][2].value[1],
            wxyz=self.grids[idx][1].wxyz,
            position=self.grids[idx][1].position,
        )
        self._update_scene()

    def _setup_gaussian_edit_folder(self):
        server = self.server

        self.edit_histories = []

        with server.gui.add_folder("Edit", visible=False):
            # initialize a list to store panel(grid)'s information
            self.grids: dict[
                int,
                list[
                    viser.MeshHandle,
                    viser.TransformControlsHandle,
                    viser.GuiInputHandle,
                ],
            ] = {}
            self.grid_idx = 0

            add_grid_button = server.gui.add_button("Add Panel")
            self.delete_gaussians_button = server.gui.add_button(
                "Delete Gaussians",
                color="red",
            )

        self.grid_folders = {}

        # create panel(grid)
        def new_grid(idx):
            with self.server.gui.add_folder("Grid {}".format(idx)) as folder:
                self.grid_folders[idx] = folder

                # TODO: add height
                grid_size = server.gui.add_vector2(
                    "Size", initial_value=(10.0, 10.0), min=(0.0, 0.0), step=0.01
                )

                grid = server.add_grid(
                    "/grid/{}".format(idx),
                    height=grid_size.value[0],
                    width=grid_size.value[1],
                )
                grid_transform = server.add_transform_controls(
                    "/grid_transform_control/{}".format(idx),
                    wxyz=grid.wxyz,
                    position=grid.position,
                )

                # resize panel on size value changed
                @grid_size.on_update
                def _(event: viser.GuiEvent):
                    with event.client.atomic():
                        self._resize_grid(idx)

                # handle panel deletion
                grid_delete_button = server.gui.add_button("Delete")

                @grid_delete_button.on_click
                def _(_):
                    with server.atomic():
                        try:
                            self.grids[idx][0].remove()
                            self.grids[idx][1].remove()
                            self.grids[idx][2].remove()
                            self.grid_folders[idx].remove()  # bug
                        except Exception as e:
                            traceback.print_exc()
                        finally:
                            del self.grids[idx]
                            del self.grid_folders[idx]

                    self._update_scene()

            # update the pose of panel(grid) when grid_transform updated
            @grid_transform.on_update
            def _(_):
                self.grids[idx][0].wxyz = grid_transform.wxyz
                self.grids[idx][0].position = grid_transform.position
                self._update_scene()

            self.grids[self.grid_idx] = [grid, grid_transform, grid_size]
            self._update_scene()

        # setup callbacks
        @add_grid_button.on_click
        def _(_):
            with server.atomic():
                new_grid(self.grid_idx)
                self.grid_idx += 1

        @self.delete_gaussians_button.on_click
        def _(_):
            with server.atomic():
                gaussian_to_be_deleted, pose_and_size_list = (
                    self._get_selected_gaussians_mask(return_pose_and_size_list=True)
                )
                self.edit_histories.append(pose_and_size_list)
                self.viewer.gaussian_model.delete_gaussians(gaussian_to_be_deleted)
                self._update_pcd()
                # update baseline so future relights start from the edited model
                self._capture_original()
            self.viewer.viewer_renderer.gaussian_model = self.viewer.gaussian_model
            self.viewer.viewer_renderer.update_pc_features()
            self.viewer.rerender_for_all_client()

    def _setup_save_gaussian_folder(self):
        with self.server.gui.add_folder("Save"):
            name_text = self.server.gui.add_text(
                "Name",
                initial_value=datetime.datetime.now().strftime("%Y%m%d_%H%M%S"),
            )
            save_button = self.server.gui.add_button("Save")

            @save_button.on_click
            def _(event: viser.GuiEvent):
                # skip if not triggered by client
                if event.client is None:
                    return
                try:
                    save_button.disabled = True

                    with self.server.atomic():
                        try:
                            # check whether is a valid name
                            name = name_text.value
                            match = re.search("^[a-zA-Z0-9_\-]+$", name)
                            if match:
                                output_directory = "edited"
                                os.makedirs(output_directory, exist_ok=True)
                                try:
                                    if len(self.edit_histories) > 0:
                                        torch.save(
                                            self.edit_histories,
                                            os.path.join(
                                                output_directory,
                                                f"{name}-edit_histories.ckpt",
                                            ),
                                        )
                                except:
                                    traceback.print_exc()

                                # save ply
                                ply_save_path = os.path.join(
                                    output_directory, "{}.ply".format(name)
                                )
                                self.viewer.gaussian_model.save_ply(ply_save_path)
                                message_text = "Saved to {}".format(ply_save_path)
                            else:
                                message_text = "Invalid name"
                        except:
                            traceback.print_exc()

                    # show message
                    with event.client.add_gui_modal("Message") as modal:
                        event.client.add_gui_markdown(message_text)
                        close_button = event.client.add_gui_button("Close")

                        @close_button.on_click
                        def _(_) -> None:
                            modal.close()

                finally:
                    save_button.disabled = False

    def _get_selected_gaussians_mask(self, return_pose_and_size_list: bool = False):
        xyz = self.viewer.gaussian_model.get_xyz

        # if no grid exists, do not delete any gaussians
        if len(self.grids) == 0:
            mask = torch.zeros(xyz.shape[0], device=xyz.device, dtype=torch.bool)
            if return_pose_and_size_list:
                return mask, []
            return mask

        pose_and_size_list = []
        # initialize mask with True
        is_gaussian_selected = torch.ones(
            xyz.shape[0], device=xyz.device, dtype=torch.bool
        )
        for i in self.grids:
            # get the pose of grid, and build world-to-grid transform matrix
            grid = self.grids[i][0]
            se3 = torch.linalg.inv(
                torch.tensor(
                    vtf.SE3.from_rotation_and_translation(
                        vtf.SO3(grid.wxyz),
                        grid.position,
                    ).as_matrix()
                ).to(xyz)
            )
            # transform xyz from world to grid
            new_xyz = torch.matmul(xyz, se3[:3, :3].T) + se3[:3, 3]
            # find the gaussians to be deleted based on the new_xyz
            grid_size = self.grids[i][2].value
            x_mask = torch.abs(new_xyz[:, 0]) < grid_size[0] / 2
            y_mask = torch.abs(new_xyz[:, 1]) < grid_size[1] / 2
            z_mask = new_xyz[:, 2] > 0
            # update mask
            is_gaussian_selected = torch.bitwise_and(is_gaussian_selected, x_mask)
            is_gaussian_selected = torch.bitwise_and(is_gaussian_selected, y_mask)
            is_gaussian_selected = torch.bitwise_and(is_gaussian_selected, z_mask)

            # add to history
            pose_and_size_list.append((se3.cpu(), grid_size))

        if return_pose_and_size_list is True:
            return is_gaussian_selected, pose_and_size_list
        return is_gaussian_selected

    def _get_selected_gaussians_indices(self):
        """
        get the index of the gaussians which in the range of grids
        :return:
        """
        selected_gaussian = torch.where(self._get_selected_gaussians_mask())
        return selected_gaussian

    def _update_pcd(self, selected_gaussians_indices=None):
        self.remove_point_cloud()
        if self.show_point_cloud_checkbox.value is False:
            return
        xyz = self.viewer.gaussian_model.get_xyz

        # get SH0 colors
        dc = self.viewer.gaussian_model._features_dc.clone()
        dc = (self.C0 * dc + 0.5).clip(min=0.0, max=1.0)
        dc = (255 * dc[:, 0]).to(torch.uint8)
        colors = dc
        if selected_gaussians_indices is None:
            selected_gaussians_indices = self._get_selected_gaussians_indices()
        colors[selected_gaussians_indices] = 255 - colors[selected_gaussians_indices]

        point_sparsify = int(self.point_sparsify.value)
        self.show_point_cloud(
            xyz[::point_sparsify].cpu().detach().numpy(),
            colors[::point_sparsify].cpu().detach().numpy(),
        )

    def remove_point_cloud(self):
        if self.pcd is not None:
            self.pcd.remove()
            self.pcd = None

    def show_point_cloud(self, xyz, colors):
        self.pcd = self.server.add_point_cloud(
            "/pcd",
            points=xyz,
            colors=colors,
            point_size=self.point_size.value,
        )

    def _update_scene(self):
        selected_gaussians_indices = self._get_selected_gaussians_mask()
        self.viewer.gaussian_model.select(selected_gaussians_indices)
        self._update_pcd(selected_gaussians_indices)

        self.viewer.rerender_for_all_client()

    def _setup_mesh_export_folder(self):
        with self.server.gui.add_folder("Mesh Export"):
            self.unbounded = self.server.gui.add_checkbox(
                "unbounded",
                initial_value=False,
            )
            self.num_cluster = self.server.gui.add_slider(
                "Num Cluster",
                min=10,
                max=200,
                step=10,
                initial_value=50,
            )
            self.mesh_res = self.server.gui.add_slider(
                "Mesh Res",
                min=128,
                max=2048,
                step=128,
                initial_value=1024,
            )
            self.export_button = self.server.gui.add_button(
                "Export Mesh", color="green", icon=viser.Icon.FILE_EXPORT
            )
            self.show_mesh_button = self.server.gui.add_button(
                "Show Mesh Result", color="yellow", icon=viser.Icon.PLAYER_PLAY
            )
            self.unshow_mesh_button = self.server.gui.add_button(
                "unshow Mesh",
                color="yellow",
                icon=viser.Icon.PLAYER_PLAY,
                visible=False,
            )

    def _setup_relight_folder(self):
        gui = self.server.gui
        with gui.add_folder("Relight", expand_by_default=False):
            # if multiple models were loaded, allow the user to pick which one
            if len(self.viewer.model_paths) > 1:
                self.model_selector = gui.add_dropdown(
                    "Target Model",
                    tuple(self.viewer.model_names),
                )
                self.model_selector.value = self.viewer.model_names[
                    getattr(self.viewer, "selected_model_idx", 0)
                ]

                @self.model_selector.on_update
                def _(event: viser.GuiEvent):
                    # store index on viewer for later use
                    if event.client is None:
                        return
                    try:
                        self.viewer.selected_model_idx = self.viewer.model_names.index(
                            self.model_selector.value
                        )
                    except ValueError:
                        pass

            default_env_path = getattr(self.viewer, "env_map_path", "")
            self.env_map_source_path_text = gui.add_text(
                "HDR Source Env Path (not displayed)",
                initial_value=default_env_path,
            )
            self.env_map_target_path_text = gui.add_text(
                "HDR Target Env Path (displayed)",
                initial_value=default_env_path,
            )

            @self.env_map_target_path_text.on_update
            def _(_event: viser.GuiEvent):
                self.viewer.env_map_path = self.env_map_target_path_text.value

            self.apply_relight_button = gui.add_button(
                "Apply Relight",
                color="green",
            )

            self.reset_button = gui.add_button("Reset Model", color="red")

            @self.reset_button.on_click
            def _reset_model(_):
                self.auto_relight_enabled = False
                gm = self.viewer.gaussian_model
                saved_transform_states = {}
                if (
                    hasattr(gm, "_model_transform_states")
                    and gm._model_transform_states is not None
                ):
                    for k, v in gm._model_transform_states.items():
                        saved_transform_states[int(k)] = {
                            "scale": float(v["scale"]),
                            "wxyz": v["wxyz"].detach().clone(),
                            "position": v["position"].detach().clone(),
                        }

                self._restore_original()
                
                gm.backup()
                if len(saved_transform_states) > 0:
                    gm._model_transform_states = saved_transform_states
                    gm.apply_all_model_transforms()

                with self.server.atomic():
                    self.viewer.viewer_renderer.gaussian_model = gm
                    self.viewer.viewer_renderer.update_pc_features()
                self.viewer.rerender_for_all_client()
                
                if len(self.server.get_clients()) > 0:
                    client = list(self.server.get_clients().values())[0]
                    client.add_notification(title="Reset", body="Model reset to original.", auto_close_seconds=3)


        self._capture_original()

        self._envmap_relight_thread = None
        self._envmap_relight_last_request = 0.0
        self._envmap_relight_lock = threading.Lock()
        @self.env_map_target_path_text.on_update
        def _(_event: viser.GuiEvent):
            if hasattr(self.viewer, "enable_env_background"):
                self.viewer.enable_env_background.value = True

        @self.apply_relight_button.on_click
        def run_relight(_):
            try:
                self.trigger_relight()
            except Exception:
                traceback.print_exc()

        def _set_relight_status(text):
            clients = list(self.server.get_clients().values())
            if clients:
                clients[0].add_notification(
                    title="Relight", body=text, auto_close_seconds=5
                )
            else:
                print(f"[Relight] {text}")

        def _start_relight(source_env_path, target_env_path):
            if not getattr(self, "_relight_processing_lock", None):
                self._relight_processing_lock = threading.Lock()
            
            if not self._relight_processing_lock.acquire(blocking=False):
                return
            
            try:
                self._is_relighting_active = True
                gm = self.viewer.gaussian_model

                # Preserve active transform states, then rebuild relight from base model.
                saved_transform_states = {}
                if (
                    hasattr(gm, "_model_transform_states")
                    and gm._model_transform_states is not None
                ):
                    for k, v in gm._model_transform_states.items():
                        saved_transform_states[int(k)] = {
                            "scale": float(v["scale"]),
                            "wxyz": v["wxyz"].detach().clone(),
                            "position": v["position"].detach().clone(),
                        }

                # before a new relight always start from the preserved original
                self._restore_original()
                if hasattr(self.viewer, "enable_env_background"):
                    self.viewer.enable_env_background.value = True
                
                if not source_env_path or not target_env_path:
                    _set_relight_status(
                        "<sub>Please specify both source and target environment map paths.</sub>"
                    )
                    return

                tmp_dir = os.path.join(os.getcwd(), "temp")
                os.makedirs(tmp_dir, exist_ok=True)
                out_path = os.path.join(tmp_dir, "relit.ply")

                # build mask for selected sub‑model, used by relight helper
                mask = None
                if hasattr(self.viewer, "model_ranges"):
                    idx = getattr(self.viewer, "selected_model_idx", 0)
                    mask = self.viewer.get_model_mask(idx)

                stop_event = threading.Event()

                def progress_notif():
                    clients = list(self.server.get_clients().values())
                    if not clients:
                        return
                    relight_prog_notif = clients[0].add_notification(title="Relighting", body="", loading=True)

                    while not stop_event.is_set():
                        time.sleep(0.5)
                    
                    relight_prog_notif.remove()

                spinner_thread = threading.Thread(target=progress_notif)
                spinner_thread.start()

                try:
                    idx = getattr(self.viewer, "selected_model_idx", 0)
                    rotation_matrix = np.eye(3, dtype=np.float32)
                    target_env_is_object_local = (
                        os.path.abspath(target_env_path)
                        in self._object_local_target_env_paths
                    )
                    if idx in saved_transform_states and not target_env_is_object_local:
                        wxyz = saved_transform_states[idx]["wxyz"].cpu().numpy()
                        rotation_matrix = vtf.SO3(wxyz).as_matrix().astype(np.float32)

                    relight.relight_gaussian_model(
                        self.viewer.gaussian_model,
                        env_map_source_path=source_env_path,
                        env_map_target_path=target_env_path,
                        num_samples=getattr(self.viewer, "relight_num_samples", 1200),
                        visibility_res=getattr(self.viewer, "relight_visibility_res", 1024),
                        rotation_matrix=rotation_matrix,
                        mask=mask,
                    )
                    # Capture latest states in case the user dragged during relighting
                    latest_transform_states = {}
                    if (
                        hasattr(gm, "_model_transform_states")
                        and gm._model_transform_states is not None
                    ):
                        for k, v in gm._model_transform_states.items():
                            latest_transform_states[int(k)] = {
                                "scale": float(v["scale"]),
                                "wxyz": v["wxyz"].detach().clone(),
                                "position": v["position"].detach().clone(),
                            }

                    # Rebuild transform baseline from relit result, then re-apply active transforms.
                    self.viewer.gaussian_model.backup()
                    if len(latest_transform_states) > 0:
                        self.viewer.gaussian_model._model_transform_states = (
                            latest_transform_states
                        )
                        self.viewer.gaussian_model.apply_all_model_transforms()
                    with self.server.atomic():
                        self.viewer.viewer_renderer.gaussian_model = (
                            self.viewer.gaussian_model
                        )
                        self.viewer.viewer_renderer.update_pc_features()

                    self.viewer.rerender_for_all_client()
                    _set_relight_status("Relight completed.")
                except Exception as e:
                    _set_relight_status(f"Relight failed: {e}")
                finally:
                    stop_event.set()
                    spinner_thread.join()
                    time.sleep(1.0)
            finally:
                self._is_relighting_active = False
                self._relight_processing_lock.release()
            
        self._start_relight_func = _start_relight

    def register_object_local_target_env(self, env_map_path: str):
        if env_map_path:
            self._object_local_target_env_paths.add(os.path.abspath(env_map_path))

    def trigger_relight(self, target_env_object_local: bool = False):
        if not self.env_map_target_path_text.value or not self.env_map_source_path_text.value:
            return
        if target_env_object_local:
            self.register_object_local_target_env(self.env_map_target_path_text.value)
        self.auto_relight_enabled = True
        if hasattr(self, "_start_relight_func"):
            self._start_relight_func(self.env_map_source_path_text.value, self.env_map_target_path_text.value)

    def request_dynamic_relight(self):
        if not getattr(self, "auto_relight_enabled", False):
            return
        
        # Debounce relight requests
        if getattr(self, "_dynamic_relight_timer", None) is not None:
            self._dynamic_relight_timer.cancel()
        
        if hasattr(self.viewer, "envmap_panel") and hasattr(
            self.viewer.envmap_panel, "trigger_capture_and_relight"
        ):
            target_func = lambda: self.viewer.envmap_panel.trigger_capture_and_relight(None)
        else:
            target_func = self.trigger_relight
        
        self._dynamic_relight_timer = threading.Timer(0.5, target_func)
        self._dynamic_relight_timer.start()

    def _setup_env_map_preview_folder(self):
        with self.server.gui.add_folder("Env Map Preview", expand_by_default=True):
            self.env_map_preview_status = self.server.gui.add_markdown(
                "<sub>No env map captured yet.</sub>",
                visible=True,
            )
            self.env_map_preview_image = self.server.gui.add_image(
                np.zeros((512, 512, 3), dtype=np.uint8),
                label="Sampled Envmap Preview",  # Gen by Cursor
                format="png",
            )

        def _sample_env_map_rgb(env_map: np.ndarray, directions: np.ndarray) -> np.ndarray:
            env_map = np.asarray(env_map, dtype=np.float32)
            directions = np.asarray(directions, dtype=np.float32)
            h, w = env_map.shape[:2]

            x = directions[..., 0]
            y = directions[..., 1]
            z = directions[..., 2]

            theta = np.arccos(np.clip(z, -1.0, 1.0))
            phi = np.arctan2(y, x)
            phi = np.where(phi < 0, phi + 2 * np.pi, phi)

            u = (phi / (2.0 * np.pi) * (w - 1)) % (w - 1)
            v = (theta / np.pi * (h - 1))

            u0 = np.floor(u).astype(np.int32)
            v0 = np.floor(v).astype(np.int32)
            u1 = (u0 + 1) % w
            v1 = np.clip(v0 + 1, 0, h - 1)

            fu = (u - u0)[..., None]
            fv = (v - v0)[..., None]

            c00 = env_map[v0, u0]
            c10 = env_map[v0, u1]
            c01 = env_map[v1, u0]
            c11 = env_map[v1, u1]

            return (
                c00 * (1.0 - fu) * (1.0 - fv)
                + c10 * fu * (1.0 - fv)
                + c01 * (1.0 - fu) * fv
                + c11 * fu * fv
            )

        def _tone_map_env_map(env_map: np.ndarray) -> np.ndarray:
            env_map = np.asarray(env_map, dtype=np.float32)
            env_map = np.clip(env_map, 0.0, None)
            return 1.0 - np.exp(-env_map)

        def _build_env_map_preview_image(
            env_map: Optional[np.ndarray], size: int = 512
        ) -> np.ndarray:
            if env_map is None:
                canvas = np.zeros((size, size, 3), dtype=np.uint8)
                cv2.putText(
                    canvas,
                    "Capture an env map to preview",
                    (24, size // 2),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (200, 200, 200),
                    2,
                    cv2.LINE_AA,
                )
                return canvas

            env_map = _tone_map_env_map(env_map)
            ys, xs = np.mgrid[-1.0:1.0:complex(size), -1.0:1.0:complex(size)]
            radius_sq = xs ** 2 + ys ** 2
            mask = radius_sq <= 1.0
            z = np.zeros_like(xs)
            z[mask] = np.sqrt(1.0 - radius_sq[mask])

            directions = np.stack([xs, -ys, z], axis=-1)
            norm = np.linalg.norm(directions, axis=-1, keepdims=True)
            norm[norm == 0.0] = 1.0
            directions = directions / norm

            rgb = np.zeros((size, size, 3), dtype=np.float32)
            rgb[mask] = _sample_env_map_rgb(env_map, directions[mask])
            rgb = np.clip(rgb, 0.0, 1.0)
            return (rgb * 255.0).astype(np.uint8)

        def _load_env_map_preview(env_map_path: Optional[str]) -> np.ndarray:
            if not env_map_path or not os.path.exists(env_map_path):
                return _build_env_map_preview_image(None)

            env_map = cv2.imread(
                env_map_path,
                cv2.IMREAD_ANYDEPTH | cv2.IMREAD_COLOR,
            )
            if env_map is None:
                return _build_env_map_preview_image(None)
            env_map = cv2.cvtColor(env_map, cv2.COLOR_BGR2RGB)
            return _build_env_map_preview_image(env_map)

        def _update_env_map_preview(env_map_path: Optional[str]) -> None:
            if self.env_map_preview_image is None:
                return
            self.env_map_preview_image.image = _load_env_map_preview(env_map_path)
            if self.env_map_preview_status is not None:
                if env_map_path:
                    preview_name = os.path.basename(env_map_path)
                    self.env_map_preview_status.content = (
                        f"<sub>Previewing {preview_name}</sub>"
                    )
                else:
                    self.env_map_preview_status.content = (
                        "<sub>No env map captured yet.</sub>"
                    )

        self.update_env_map_preview = _update_env_map_preview
        self.update_env_map_preview(None)

    def export_mesh_block(self):
        self._default_export_log = f"**Model path**: {self.viewer.model_paths} \\\n  **Data path**: {self.viewer.source_path})"
        self._mesh_export_log_dir = os.path.join(os.getcwd(), "temp/mesh_log.txt")
        if os.path.exists(self._mesh_export_log_dir):
            os.remove(self._mesh_export_log_dir)
        dir_path = os.path.dirname(self._mesh_export_log_dir)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

        # Mesh Export !!!
        def read_last_lines(file_path, num_lines):
            with open(file_path, "r") as file:
                lines = file.readlines()
                formatted_lines = [
                    " \\\n [Info]" + line.rstrip() for line in lines[-num_lines:-1]
                ]
                return "".join(formatted_lines)

        @self.export_button.on_click
        def _(event: viser.GuiEvent) -> None:
            with self.server.atomic():
                with event.client.add_gui_modal("[Mesh Export]") as modal:
                    self.export_mesh_text = event.client.add_gui_markdown(
                        self._default_export_log
                    )
                    close_button = event.client.add_gui_button("Close", visible=False)

                    @close_button.on_click
                    def _(_) -> None:
                        modal.close()

            # Update the GUI first before starting the thread
            def update_gui_and_start_export():
                def export() -> None:
                    with open(self._mesh_export_log_dir, "w") as file:
                        file.write("mesh exporting... \\\n ")
                    ex_args, model_params, export_pipe_params = (
                        MeshExporter.parse_args_mesh(
                            self.viewer.model_paths,
                            self.viewer.source_path,
                            self.viewer.args,
                            unbounded=self.unbounded.value,
                            mesh_res=self.mesh_res.value,
                            num_cluster=self.num_cluster.value,
                        )
                    )
                    mesh_exporter = MeshExporter(
                        ex_args,
                        self.viewer.gaussian_model,
                        self.viewer.iteration,
                        model_params,
                        export_pipe_params,
                    )
                    mesh_exporter.start_logging(self._mesh_export_log_dir)
                    self.mesh_path = mesh_exporter.export_mesh()
                    mesh_exporter.stop_logging()

                def update_log() -> None:
                    while export_thread.is_alive():
                        self.export_mesh_text.content = (
                            self._default_export_log
                            + read_last_lines(self._mesh_export_log_dir, 15)
                        )
                        time.sleep(0.1)

                export_thread = threading.Thread(target=export)
                log_thread = threading.Thread(target=update_log)
                export_thread.start()
                log_thread.start()
                export_thread.join()
                log_thread.join()
                self.export_mesh_text.content = (
                    f"Done! \n Your Mesh is saved at: {self.mesh_path}"
                )
                close_button.visible = True

            # Call the function to update the GUI and start the export process
            update_gui_and_start_export()

        @self.show_mesh_button.on_click
        def _(event: viser.GuiEvent) -> None:
            with self.server.atomic():
                self.show_mesh_button.visible = False
                self.unshow_mesh_button.visible = True

                if self.mesh is None and self.mesh_path is not None:
                    mesh = trimesh.load_mesh(self.mesh_path)
                    mesh.apply_transform(
                        np.linalg.inv(self.viewer.camera_transform.cpu().numpy())
                    )
                    self.mesh = self.server.add_mesh_trimesh(
                        name="/trimesh",
                        mesh=mesh,
                        scale=1,
                        wxyz=event.client.camera.wxyz,
                        position=tuple(self.viewer.camera_center),
                    )
                    self.mesh_control = event.client.add_transform_controls(
                        f"/mesh_control",
                        scale=0.5,
                        wxyz=self.mesh.wxyz,
                        position=self.mesh.position,
                    )

                    def _make_mesh_controls_callback(
                        trimesh_obj,
                        control: viser.TransformControlsHandle,
                    ) -> None:
                        @control.on_update
                        def _(_) -> None:
                            trimesh_obj.wxyz = control.wxyz
                            trimesh_obj.position = control.position
                            print(control.wxyz, control.position)

                    _make_mesh_controls_callback(self.mesh, self.mesh_control)
                else:
                    with event.client.add_gui_modal("[Alert]") as modal:
                        self.export_mesh_text = event.client.add_gui_markdown(
                            "<sub> There is no exported mesh </sub>"
                        )
                        close_button = event.client.add_gui_button(
                            "Close", visible=True
                        )

                        @close_button.on_click
                        def _(_) -> None:
                            modal.close()

        @self.unshow_mesh_button.on_click
        def _(event: viser.GuiEvent) -> None:
            with self.server.atomic():
                self.show_mesh_button.visible = True
                self.unshow_mesh_button.visible = False
                if self.mesh is not None:
                    self.mesh.remove()
                    self.mesh_control.remove()
                    self.mesh = None
