# src/ui/opengl_viewer.py
import numpy as np
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QMouseEvent, QWheelEvent, QMatrix4x4, QSurfaceFormat, QOpenGLContext
from OpenGL.GL import *
import pywavefront

# --- GLSL Shader Code (Updated) ---
VERTEX_SHADER = """
#version 330 core
layout (location = 0) in vec3 aPos;
layout (location = 1) in vec3 aNormal;
layout (location = 2) in vec3 aColor; // New vertex color attribute

out vec3 FragPos;
out vec3 Normal;
out vec3 VertColor; // Pass color to fragment shader

uniform mat4 model;
uniform mat4 view;
uniform mat4 projection;

void main() {
    FragPos = vec3(model * vec4(aPos, 1.0));
    Normal = mat3(transpose(inverse(model))) * aNormal;
    gl_Position = projection * view * vec4(FragPos, 1.0);
    gl_PointSize = 3.0;
    VertColor = aColor;
}
"""

# --- FRAGMENT_SHADER remains the same ---
FRAGMENT_SHADER = """
#version 330 core
out vec4 FragColor;

in vec3 FragPos;
in vec3 Normal;
in vec3 VertColor; // Receive color from vertex shader

uniform vec3 lightPos1;
uniform vec3 lightPos2;

void main() {
    vec3 norm = normalize(Normal);
    
    // Ambient light
    float ambientStrength = 0.3;
    vec3 ambient = ambientStrength * vec3(1.0, 1.0, 1.0);
    
    // Diffuse lighting
    vec3 lightDir1 = normalize(lightPos1 - FragPos);
    float diff1 = max(dot(norm, lightDir1), 0.0);
    vec3 diffuse1 = diff1 * vec3(1.0, 1.0, 1.0);
    
    vec3 lightDir2 = normalize(lightPos2 - FragPos);
    float diff2 = max(dot(norm, lightDir2), 0.0);
    vec3 diffuse2 = diff2 * vec3(0.8, 0.8, 0.8);

    vec3 lighting = (ambient + diffuse1 + diffuse2);
    vec3 result = lighting * VertColor; // Use the vertex color
    FragColor = vec4(result, 1.0);
}
"""


def compile_shader(source, shader_type):
    shader = glCreateShader(shader_type)
    glShaderSource(shader, source)
    glCompileShader(shader)
    if not glGetShaderiv(shader, GL_COMPILE_STATUS):
        raise Exception(f"Shader compilation error: {glGetShaderInfoLog(shader).decode()}")
    return shader

class OpenGLViewer(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        self.new_model_data = None
        self.model_needs_upload = False
        self.model_vao = None
        self.model_vbo = None
        self.model_vertex_count = 0
        self.model_center = np.array([0.0, 0.0, 0.0])
        self.model_scale = 1.0
        self.shader_program = None
        self.camera_azimuth = 45.0
        self.camera_elevation = 30.0
        self.camera_distance = 5.0
        self.last_mouse_pos = None
        self.auto_rotate_angle = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(16)
        self.render_mode = GL_TRIANGLES # New state for toggling
        self.meshes = [] # Will hold a list of meshes, each with its own data

    def set_render_mode(self, mode):
        """Public method to switch between GL_TRIANGLES and GL_POINTS."""
        self.render_mode = mode
        self.update()

    def _palette_color(self, i: int):
        # Deterministic bright colors for debugging
        pal = [
            (1.0, 0.2, 0.2),
            (0.2, 1.0, 0.2),
            (0.2, 0.4, 1.0),
            (1.0, 0.7, 0.2),
            (0.8, 0.2, 1.0),
            (0.3, 0.9, 0.9),
        ]
        return pal[i % len(pal)]

    def _compute_normals(self, positions: np.ndarray, faces: np.ndarray) -> np.ndarray:
        normals = np.zeros_like(positions, dtype=np.float32)
        p = positions
        for i0, i1, i2 in faces:
            v0, v1, v2 = p[i0], p[i1], p[i2]
            n = np.cross(v1 - v0, v2 - v0)
            normals[i0] += n; normals[i1] += n; normals[i2] += n
        lens = np.linalg.norm(normals, axis=1)
        mask = lens > 1e-12
        normals[mask] /= lens[mask][:, None]
        normals[~mask] = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        return normals

    def _build_flat_submesh(self, local_pos: np.ndarray, faces: np.ndarray, color3: tuple[float,float,float]):
        # faces: (N,3) of local indices
        tri_pos = local_pos[faces]                    # (N,3,3)
        v0 = tri_pos[:, 0, :]
        v1 = tri_pos[:, 1, :]
        v2 = tri_pos[:, 2, :]
        n = np.cross(v1 - v0, v2 - v0)                # (N,3)
        lens = np.linalg.norm(n, axis=1)
        mask = lens > 1e-12
        n[mask] /= lens[mask][:, None]
        n[~mask] = np.array([0,0,1], dtype=np.float32)

        # Repeat each face normal for its 3 vertices
        tri_nrm = np.repeat(n[:, None, :], 3, axis=1) # (N,3,3)

        tri_col = np.tile(np.array(color3, np.float32), (faces.shape[0]*3, 1))  # (N*3,3)

        # Interleave pos|norm|color
        pos_flat = tri_pos.reshape(-1, 3).astype(np.float32)
        nrm_flat = tri_nrm.reshape(-1, 3).astype(np.float32)
        packed = np.hstack((pos_flat, nrm_flat, tri_col)).astype(np.float32).ravel()

        return {
            "data": np.ascontiguousarray(packed),
            "vbo": None, "vao": None, "ibo": None,
            "vertex_count": pos_flat.shape[0],
            "index_count": 0,
            "positions_for_bounds": pos_flat,  # for bounds/centering
            "flat": True,
        }

    def load_model(self, obj_file_path: str):
        try:
            scene = pywavefront.Wavefront(
                obj_file_path,
                create_materials=True,
                parse=True,
                collect_faces=True,   # get indexed faces
            )

            positions = np.array(scene.vertices, dtype=np.float32).reshape(-1, 3)

            # Collect all faces (material-level and mesh-level) to compute normals
            all_faces = []
            for mesh in scene.mesh_list:
                for m in getattr(mesh, "materials", []):
                    mf = getattr(m, "faces", None)
                    if mf: all_faces.extend(mf)
                mf2 = getattr(mesh, "faces", None)
                if mf2: all_faces.extend(mf2)

            if not all_faces:
                print("No faces found in OBJ.")
                self.meshes = []
                self.update()
                return

            all_faces = np.array(all_faces, dtype=np.uint32).reshape(-1, 3)
            normals = self._compute_normals(positions, all_faces)

            self.meshes = []
            debug_idx = 0  # for palette colors

            for mesh in scene.mesh_list:
                built_any = False

                # Prefer per-material submeshes
                for m in getattr(mesh, "materials", []):
                    faces = np.array(getattr(m, "faces", []), dtype=np.uint32).reshape(-1, 3)
                    if faces.size == 0:
                        continue

                    used = np.unique(faces.ravel())
                    g2l = {int(g): i for i, g in enumerate(used)}

                    local_pos = positions[used]
                    local_nrm = normals[used]

                    # Try MTL diffuse; if missing/white, apply a debug color so you SEE it
                    diff = tuple(getattr(m, "diffuse", (1.0, 1.0, 1.0)))[:3]
                    if diff == (1.0, 1.0, 1.0) or any(np.isnan(diff)):
                        diff = self._palette_color(debug_idx); debug_idx += 1

                    local_col = np.tile(np.array(diff, dtype=np.float32), (local_pos.shape[0], 1))
                    packed = np.hstack((local_pos, local_nrm, local_col)).astype(np.float32).ravel()
                    local_idx = np.array([g2l[int(x)] for x in faces.ravel()], dtype=np.uint32)

                    self.meshes.append({
                        "data": np.ascontiguousarray(packed),
                        "indices": np.ascontiguousarray(local_idx),
                        "vbo": None, "vao": None, "ibo": None,
                        "vertex_count": local_pos.shape[0],
                        "index_count": local_idx.size,
                        "positions_for_bounds": local_pos,
                    })
                    built_any = True

                # Fallback: one submesh for the whole mesh
                if not built_any:
                    faces = np.array(getattr(mesh, "faces", []), dtype=np.uint32).reshape(-1, 3)
                    if faces.size == 0:
                        continue

                    used = np.unique(faces.ravel())
                    g2l = {int(g): i for i, g in enumerate(used)}

                    local_pos = positions[used]
                    local_nrm = normals[used]
                    diff = self._palette_color(debug_idx); debug_idx += 1
                    local_col = np.tile(np.array(diff, dtype=np.float32), (local_pos.shape[0], 1))
                    packed = np.hstack((local_pos, local_nrm, local_col)).astype(np.float32).ravel()
                    local_idx = np.array([g2l[int(x)] for x in faces.ravel()], dtype=np.uint32)

                    self.meshes.append({
                        "data": np.ascontiguousarray(packed),
                        "indices": np.ascontiguousarray(local_idx),
                        "vbo": None, "vao": None, "ibo": None,
                        "vertex_count": local_pos.shape[0],
                        "index_count": local_idx.size,
                        "positions_for_bounds": local_pos,
                    })

            # Bounds / center / scale (for your translate→scale→rotate order)
            if self.meshes:
                all_pos = np.concatenate([m["positions_for_bounds"] for m in self.meshes], axis=0)
                minc, maxc = all_pos.min(axis=0), all_pos.max(axis=0)
                self.model_center = (minc + maxc) / 2.0
                size = np.linalg.norm(maxc - minc)
                self.model_scale = 2.0 / (size if size > 0 else 1.0)

            self.model_needs_upload = True
            self.update()

        except Exception as e:
            print(f"Failed to load model (indexed path): {e}")

            
    def _upload_model_to_gpu(self):
        if not self.meshes:
            return

        for mesh in self.meshes:
            if mesh.get("vao") is None:
                mesh["vao"] = glGenVertexArrays(1)
            glBindVertexArray(mesh["vao"])

            # VBO
            if mesh.get("vbo") is None:
                mesh["vbo"] = glGenBuffers(1)
            glBindBuffer(GL_ARRAY_BUFFER, mesh["vbo"])
            glBufferData(GL_ARRAY_BUFFER, mesh["data"].nbytes, mesh["data"], GL_STATIC_DRAW)

            stride = 9 * 4  # 9 floats * 4 bytes
            # pos
            glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
            glEnableVertexAttribArray(0)
            # normal
            glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(12))
            glEnableVertexAttribArray(1)
            # color
            glVertexAttribPointer(2, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(24))
            glEnableVertexAttribArray(2)

            # IBO/EBO (if present)
            if "indices" in mesh:
                if mesh.get("ibo") is None:
                    mesh["ibo"] = glGenBuffers(1)
                glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, mesh["ibo"])
                glBufferData(GL_ELEMENT_ARRAY_BUFFER, mesh["indices"].nbytes, mesh["indices"], GL_STATIC_DRAW)

            # Unbind VAO (keeps element array binding inside VAO state)
            glBindVertexArray(0)

        self.model_needs_upload = False


    def initializeGL(self):
        glClearColor(0.1, 0.1, 0.15, 1.0)
        glEnable(GL_DEPTH_TEST)

        # Only enable on desktop GL
        ctx = QOpenGLContext.currentContext()
        if ctx and not ctx.isOpenGLES():
            try:
                glEnable(GL_PROGRAM_POINT_SIZE)
            except Exception:
                pass  # ignore on drivers that don't like it

        vs = compile_shader(VERTEX_SHADER, GL_VERTEX_SHADER)
        fs = compile_shader(FRAGMENT_SHADER, GL_FRAGMENT_SHADER)
        self.shader_program = glCreateProgram()
        glAttachShader(self.shader_program, vs)
        glAttachShader(self.shader_program, fs)
        glLinkProgram(self.shader_program)

        # Good practice: check link status and print log on failure
        ok = glGetProgramiv(self.shader_program, GL_LINK_STATUS)
        if not ok:
            log = glGetProgramInfoLog(self.shader_program).decode()
            raise RuntimeError(f"Program link failed:\n{log}")

        glUseProgram(self.shader_program)
        glUniform3f(glGetUniformLocation(self.shader_program, "lightPos1"), 5.0, 5.0, 5.0)
        glUniform3f(glGetUniformLocation(self.shader_program, "lightPos2"), -5.0, 5.0, -5.0)


    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        
        if self.model_needs_upload:
            self._upload_model_to_gpu()

        if not self.shader_program: return
        glUseProgram(self.shader_program)

        projection = QMatrix4x4()
        projection.perspective(45.0, self.width() / self.height() if self.height() > 0 else 0, 0.1, 100.0)

        view = QMatrix4x4()
        view.translate(0.0, 0.0, -self.camera_distance)
        view.rotate(self.camera_elevation, 1.0, 0.0, 0.0)
        view.rotate(self.camera_azimuth, 0.0, 1.0, 0.0)

        model = QMatrix4x4()
        model.translate(-self.model_center[0], -self.model_center[1], -self.model_center[2])
        model.scale(self.model_scale)
        model.rotate(self.auto_rotate_angle, 0.0, 1.0, 0.0)

        glUniformMatrix4fv(glGetUniformLocation(self.shader_program, "projection"), 1, GL_FALSE, projection.data())
        glUniformMatrix4fv(glGetUniformLocation(self.shader_program, "view"), 1, GL_FALSE, view.data())
        glUniformMatrix4fv(glGetUniformLocation(self.shader_program, "model"), 1, GL_FALSE, model.data())

        self._draw_model()
        
    def _draw_model(self):
        if self.model_needs_upload:
            return

        for mesh in self.meshes:
            glBindVertexArray(mesh["vao"])
            if mesh.get("ibo") is not None:
                glDrawElements(self.render_mode, mesh["index_count"], GL_UNSIGNED_INT, ctypes.c_void_p(0))
            else:
                glDrawArrays(self.render_mode, 0, mesh["vertex_count"])
            glBindVertexArray(0)

        
    def update_animation(self):
        self.auto_rotate_angle += 0.5
        if self.auto_rotate_angle > 360: self.auto_rotate_angle -= 360
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        self.last_mouse_pos = event.position()
    def mouseMoveEvent(self, event: QMouseEvent):
        if self.last_mouse_pos:
            dx = event.position().x() - self.last_mouse_pos.x()
            dy = event.position().y() - self.last_mouse_pos.y()
            self.camera_azimuth += dx * 0.25
            self.camera_elevation += dy * 0.25
            self.camera_elevation = max(-90, min(90, self.camera_elevation))
            self.last_mouse_pos = event.position()
            self.update()
    def mouseReleaseEvent(self, event: QMouseEvent):
        self.last_mouse_pos = None
    def wheelEvent(self, event: QWheelEvent):
        self.camera_distance -= event.angleDelta().y() / 120.0
        self.camera_distance = max(1.0, min(20.0, self.camera_distance))
        self.update()
