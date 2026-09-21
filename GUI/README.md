<!-- Gen by Cursor -->
# TranSplat Interactive Viser Viewer

Interactive web-based viewer for **TranSplat** (2D Gaussian Splatting), built on [Viser](https://viser.studio). Supports real-time rendering, multi-model composition, interactive rigid-body transforms, camera animation, local environment map extraction via GMNet, and instant SH radiance transfer relighting powered by cached visibility precomputation.

![Preview of the interactive relighting GUI](../assets/gui_preview.gif)

---

## ⚡ Quick Start

### 1. Installation

If you are using the `surfel_splatting` environment, install the viewer requirements:

```bash
conda activate surfel_splatting
pip install -r GUI/requirements.txt
```

*(Installs `viser==0.1.29` and `splines`. No changes to your PyTorch CUDA environment are required.)*

---

## 🚀 Running the Viewer

You can launch the viewer using the top-level `viewer.py` wrapper or directly via `GUI/viewer.py`:

### Single Model
```bash
# View a trained 2DGS model
python viewer.py output/ficus/point_cloud/iteration_30000/point_cloud.ply

# With custom port and host
python viewer.py output/ficus/point_cloud/iteration_30000/point_cloud.ply --port 8080 --host 0.0.0.0
```

### Multi-Model Composition, Insertion & Auto-Centering
Load multiple models into a unified coordinate frame:
- **2DGS models (`scale_0`, `scale_1`)**: Fully relightable, editable foreground objects.
- **3DGS models (`scale_0`, `scale_1`, `scale_2`)**: Static background environment / room.

```bash
# Object insertion and relighting in a target scene (automatically centers object to room)
python viewer.py output/ficus/point_cloud/iteration_30000/point_cloud.ply classroom.ply --auto_center

# Apply an initial 4×4 row-major transform matrix (16 floats)
python viewer.py object.ply background.ply \
    -t 1 0 0 0  0 1 0 0  0 0 1 0.5  0 0 0 1
```

Open `http://localhost:8080` in your web browser.

---

## 🎛️ Features & UI Panels

### 1. Status & Image Options
- **Status**: Live GPU memory usage, FPS, and frame time tracking.
- **Image Options**: Sliders for max resolution and JPEG compression quality during camera motion vs. static frames.
- **Fast Image Encoder**: OpenCV-accelerated base64 JPEG/PNG encoding for ultra-low latency frame delivery.
- **WebRTC Fast Preview**: Optional experimental high-framerate stream (`--fast-preview`).
- **Use HDR Env Background**: Toggles panoramic sky background rendering using the target HDR map.

### 2. Instant Decoupled Relighting (Edit Panel)
Matches TranSplat's exact official `phase_2_decoupled_relight` algorithm:
- **Visibility Caching**: The viewer bakes Phase 1 visibility ($V_{lm}$) once into GPU memory upon launch (`--relight-visibility-res 1024`, `--relight-num-samples 1200`). Subsequent target relights reuse this cache, executing in **under 0.1 seconds**.
- **HDR Source Env Path**: The illumination environment under which the model was originally trained (e.g. `city.hdr`).
- **HDR Target Env Path**: The target environment map to relight into (e.g. `fireplace.hdr` or `envmaps/<scene>.hdr`).
- **Apply Relight**: Computes Gaunt tensor self-shadowed diffuse irradiance (DC band) and applies data-driven BRDF attenuation ($A_l$) with reflection-space SH convolution for higher-order specular bands.
- **Reset Model**: Restores the baseline SH features while preserving the current transform pose.

### 3. Transform Panel
- **3D Gizmo**: Interactive translate/rotate gizmo in the 3D viewport.
- **Translation & Euler Angles**: Numerical inputs for precise positioning.
- **Rotation-Aware Relighting**: Relighting dynamically rotates the environment map relative to the object's active transform.
- **Copy 4×4 Matrix**: Modal popup allowing one-click copy of the active 4×4 row-major transform matrix for driver scripts.

### 4. Local Environment Map Extraction (`Env Map` Panel)
When composing an object inside a reconstructed background scene:
- Renders 6 cube faces from the object's center without self-occlusion.
- Reprojects the cube faces to a 2:1 equirectangular panorama.
- Uses **GMNet** (`GUI/GMNet`) to perform inverse tone mapping from LDR to linear HDR.
- Automatically sets the captured HDR as the target environment and triggers instant relighting.

---

## 🛠️ CLI Arguments Reference

| Argument | Default | Description |
|---|---|---|
| `model_paths` | *(required)* | One or more paths to `.ply` files |
| `-t`, `--model-transform` | `None` | 16 floats (4×4 row-major matrix) per model (repeatable) |
| `-s`, `--source_path` | `""` | Source dataset path (for `cameras.json` lookup) |
| `-a`, `--host` | `0.0.0.0` | Server bind host |
| `-p`, `--port` | `8080` | Server port |
| `--env-map-path` | `""` | Initial HDR environment map |
| `--auto_center` | `False` | Automatically centers foreground object to background scene |
| `--no-relight-precompute` | `False` | Skip startup relight visibility baking |
| `--relight-num-samples` | `1200` | Fibonacci SH sample count for visibility and lighting |
| `--relight-visibility-res`| `1024` | Resolution for shadow-depth visibility baking |
| `--fast-preview` | `False` | Start WebRTC stream server |
| `--show_cameras` | `False` | Display training camera frustums |
