from PyQt6.QtCore import QTimer, Qt, QSize
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QFormLayout
import numpy as np
import math

from ipc.shm_protocol import RegistryReader, FrameShmReader, CtrlShmWriter, GeoShmReader


class Viewport(QWidget):
    def __init__(self, fb_name=None, ctrl_name=None, geom_name=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Viewport")

        # --- UI ---
        from PyQt6.QtWidgets import QComboBox
        self.canvas = QLabel()
        self.canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas.setMinimumSize(320, 200)

        controls = QHBoxLayout()
        self.cmb_cam  = QComboBox()
        self.btn_pause = QPushButton("Pause")
        self.btn_run   = QPushButton("Run")
        self.slider_dt = QSlider(Qt.Orientation.Horizontal)
        self.slider_dt.setRange(0, 200)  # 0..2x
        self.slider_dt.setValue(100)
        controls.addWidget(self.cmb_cam)
        controls.addWidget(self.btn_pause)
        controls.addWidget(self.btn_run)
        controls.addWidget(self.slider_dt)

        layout = QVBoxLayout(self)
        layout.addWidget(self.canvas, stretch=1)
        layout.addLayout(controls)

        # --- SHM objects (lazy connect after registry) ---
        self.ctrl = CtrlShmWriter(ctrl_name) if ctrl_name else CtrlShmWriter()

        self._connected = False
        self._retry_timer = QTimer(self)
        self._retry_timer.timeout.connect(self._try_connect)
        self._retry_timer.start(250)

        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._tick)
        self._frame_timer.start(1000 // 120)

        self.btn_pause.clicked.connect(self._on_pause)
        self.btn_run.clicked.connect(self._on_run)
        self.slider_dt.valueChanged.connect(self._on_dt)
        self.cmb_cam.currentIndexChanged.connect(self._on_cam_changed)

        self.splat_radius = 1

        self.slider_radius = QSlider(Qt.Orientation.Horizontal)
        self.slider_radius.setRange(0, 4)   # 0: 1x1, 1: 3x3, 2: 5x5 ...
        self.slider_radius.setValue(self.splat_radius)

        self.lbl_radius_val = QLabel(str(self.splat_radius))

        # put labels + sliders in a tidy form row
        form = QFormLayout()
        row_radius = QHBoxLayout()
        row_radius.addWidget(self.slider_radius)
        row_radius.addWidget(self.lbl_radius_val)
        form.addRow("Fill radius", row_radius)

        layout.addLayout(form)

        # hooks
        self.slider_radius.valueChanged.connect(self._on_radius_changed)

        # runtime
        self._view_keepalive = None
        self._fb = None
        self._geom = None
        self._cams_meta = []  # [{name, index, count, width, height}, ...]
        self._active_idx = -1

    def _try_connect(self):
        if self._connected:
            return

        # Connect ctrl (optional)
        if not getattr(self, "_ctrl_ok", False):
            try:
                self.ctrl.connect()
                self._ctrl_ok = True
                print("CTRL connected")
            except FileNotFoundError:
                pass

        # Discover cameras via registry
        if not getattr(self, "_reg_ok", False):
            try:
                reg = RegistryReader("/uc3d_reg")
                reg.connect()
                cams = reg.list_cameras()
                reg.close()
                if cams:
                    self._cams_meta = cams
                    self.cmb_cam.blockSignals(True)
                    self.cmb_cam.clear()
                    for c in cams:
                        label = f'{c["name"]} (#{c["index"]}, N={c["count"]})'
                        self.cmb_cam.addItem(label, c)
                    self.cmb_cam.blockSignals(False)
                    self._reg_ok = True
                    print(f"REG: {len(cams)} cameras")

                    # auto-select first
                    self._open_camera_by_index(cams[0]["index"])
                    self._connected = True
                    self._retry_timer.stop()
            except FileNotFoundError:
                pass

    def _release_current_buffers(self):
        # drop any exported pointers
        self._view_keepalive = None
        self.canvas.clear()
        try:
            import gc; gc.collect()
        except Exception:
            pass

    def _open_camera_by_index(self, idx: int):
        old_fb   = getattr(self, "_fb", None)
        old_geom = getattr(self, "_geom", None)

        self._release_current_buffers()

        def _delayed_close():
            # Close FB first
            if old_fb:
                try:
                    old_fb.close()
                except BufferError:
                    # try again shortly if a memoryview is still alive
                    QTimer.singleShot(50, _delayed_close)
                    return
                except AttributeError:
                    pass  # no close() method

            # Then GEOM
            if old_geom:
                try:
                    # only call if present
                    if hasattr(old_geom, "close"):
                        old_geom.close()
                except BufferError:
                    QTimer.singleShot(50, _delayed_close)
                    return
                except AttributeError:
                    pass

        # schedule the close after this event loop turn
        QTimer.singleShot(0, _delayed_close)

        # Open the new camera pair
        fb_name   = f"/uc3d_fb{idx}"
        geom_name = f"/uc3d_geom{idx}"

        self._fb = FrameShmReader(fb_name);   self._fb.connect()
        self._geom = GeoShmReader(geom_name); self._geom.connect()

        self._active_idx = idx
        print(f"Opened camera #{idx}: {self._fb.width}x{self._fb.height} stride={self._fb.stride}, geom N={self._geom.count}")

    def _on_cam_changed(self, combo_index: int):
        if combo_index < 0 or combo_index >= len(self._cams_meta):
            return
        meta = self._cams_meta[combo_index]
        idx = meta["index"]

        # Avoid reopening same cam
        if idx == self._active_idx:
            return
        try:
            self._open_camera_by_index(idx)
        except FileNotFoundError:
            print(f"Camera #{idx} channels not ready yet")
    
    def _on_radius_changed(self, v: int):
        self.splat_radius = int(v)
        self.lbl_radius_val.setText(str(v))

    def _on_pause(self):
        if not self._connected: return
        self.ctrl.pause = 1
        self.ctrl.write()

    def _on_run(self):
        if not self._connected: return
        self.ctrl.pause = 0
        self.ctrl.write()

    def _on_dt(self, v):
        if not self._connected: return
        self.ctrl.dt_scale = v / 100.0
        self.ctrl.write()

    def _tick(self):
        # need at least one camera
        if not self._fb or not self._geom:
            return

        xy_view, meta, gseq = self._geom.latest_fast()
        if xy_view is None:
            return
        count = meta["count"]
        W = max(1, int(meta.get("width",  self._geom.width or 192)))
        H = max(1, int(meta.get("height", self._geom.height or 96)))

        view, fseq = self._fb.latest_frame_view_fast()
        if view is None:
            return
        if len(view) < count * 3:
            return

        # Build a tight RGB888 (W x H) from scatter
        img = QImage(W, H, QImage.Format.Format_RGB888)
        img.fill(0)
        ptr = img.bits()
        ptr.setsize(W * H * 3)
        outbuf = bytearray(W * H * 3)
        buf = memoryview(outbuf)

        # Interpret xy_view (float32 pairs)
        mvf = memoryview(xy_view).cast("f")
        # Determine if xy are already in pixel space
        xs = mvf[0::2]; ys = mvf[1::2]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        pixel_space = (
            minx >= -0.5 and maxx <= (W - 1 + 0.5) and
            miny >= -0.5 and maxy <= (H - 1 + 0.5)
        )

        r = int(self.splat_radius)

        if pixel_space:
            # Direct pixel-space splat
            for i in range(count):
                x = mvf[2*i]; y = mvf[2*i + 1]
                ix = int(round(x))
                iy = int(round((H - 1) - y))
                if 0 <= ix < W and 0 <= iy < H:
                    p = i * 3
                    R = view[p+0]; G = view[p+1]; B = view[p+2]
                    x0 = max(0, ix - r); x1 = min(W - 1, ix + r)
                    y0 = max(0, iy - r); y1 = min(H - 1, iy + r)
                    for yy in range(y0, y1 + 1):
                        row_o = (yy * W) * 3
                        for xx in range(x0, x1 + 1):
                            o = row_o + xx * 3
                            buf[o+0] = R; buf[o+1] = G; buf[o+2] = B
        else:
            # Normalize world coords to framebuffer space, then splat
            dx = max(maxx - minx, 1e-6)
            dy = max(maxy - miny, 1e-6)
            for i in range(count):
                x = mvf[2*i]; y = mvf[2*i + 1]
                nx = (x - minx) / dx
                ny = (y - miny) / dy
                ix = int(nx * (W - 1) + 0.5)
                iy = int((1.0 - ny) * (H - 1) + 0.5)
                if 0 <= ix < W and 0 <= iy < H:
                    p = i * 3
                    R = view[p+0]; G = view[p+1]; B = view[p+2]
                    x0 = max(0, ix - r); x1 = min(W - 1, ix + r)
                    y0 = max(0, iy - r); y1 = min(H - 1, iy + r)
                    for yy in range(y0, y1 + 1):
                        row_o = (yy * W) * 3
                        for xx in range(x0, x1 + 1):
                            o = row_o + xx * 3
                            buf[o+0] = R; buf[o+1] = G; buf[o+2] = B

        # Build QImage
        img = QImage(bytes(outbuf), W, H, QImage.Format.Format_RGB888)

        # nearest-neighbor upscale to fit canvas
        pix = QPixmap.fromImage(img).scaled(
            self.canvas.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation # FastTransformation for nearest
        )
        self._view_keepalive = view  # keep SHM mv alive
        self.canvas.setPixmap(pix)

    def _draw_scatter(self, xy, rgb_view, target_size):
        """Render XY (+Y up) with interleaved RGB888 to a QImage that fits the canvas."""

        W = target_size.width()
        H = target_size.height()
        if W < 2 or H < 2:
            W, H = 640, 360  # fallback; will be replaced as soon as the widget lays out

        try:
            N_xy = len(xy)
        except Exception:
            return None
        if N_xy <= 0:
            return None

        rgb = memoryview(rgb_view)
        N_rgb = len(rgb) // 3
        N = min(N_xy, N_rgb)
        if N == 0:
            return None

        def _get_xy(i):
            p = xy[i]
            if isinstance(p, (tuple, list)) and len(p) >= 2:
                return float(p[0]), float(p[1])
            try:
                return float(p[0]), float(p[1])
            except Exception:
                pass
            for a, b in (("x", "y"), ("X", "Y")):
                if hasattr(p, a) and hasattr(p, b):
                    return float(getattr(p, a)), float(getattr(p, b))
            raise TypeError("Unsupported XY element type")

        import math
        minx = math.inf; maxx = -math.inf
        miny = math.inf; maxy = -math.inf
        for i in range(N):
            x, y = _get_xy(i)
            if x < minx: minx = x
            if x > maxx: maxx = x
            if y < miny: miny = y
            if y > maxy: maxy = y
        dx = max(1e-6, maxx - minx)
        dy = max(1e-6, maxy - miny)

        buf = bytearray(W * H * 3)

        mv = memoryview(buf)

        for i in range(N):
            x, y = _get_xy(i)
            nx = (x - minx) / dx
            ny = (y - miny) / dy
            ix = int(nx * (W - 1) + 0.5)
            iy = int((1.0 - ny) * (H - 1) + 0.5)
            if 0 <= ix < W and 0 <= iy < H:
                o = (iy * W + ix) * 3
                b = i * 3
                mv[o + 0] = rgb[b + 0]  # R
                mv[o + 1] = rgb[b + 1]  # G
                mv[o + 2] = rgb[b + 2]  # B

        from PyQt6.QtGui import QImage
        img = QImage(bytes(buf), W, H, QImage.Format.Format_RGB888)
        self._img_keepalive = buf  # keep Python buffer alive in case of platform differences
        return img

    def closeEvent(self, e):
        try:
            self._frame_timer.stop()
            self._retry_timer.stop()
            if self._fb:   self._fb.close()
            if self._geom: self._geom.close()
            if self.ctrl:  self.ctrl.close()
        finally:
            super().closeEvent(e)

