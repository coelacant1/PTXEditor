# src/ui/obj_converter_panel.py
import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QLineEdit, 
                               QPushButton, QFileDialog, QMessageBox, QSplitter)
from PyQt6.QtCore import Qt
from PyQt6.Qsci import QsciScintilla, QsciLexerCPP
from PyQt6.QtGui import QFont, QColor
import pywavefront

from OpenGL.GL import GL_POINTS, GL_TRIANGLES

# Import the new viewer
from .opengl_viewer import OpenGLViewer

class ObjPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.obj_file_path = ""

        # --- Layouts & Splitters ---
        main_layout = QVBoxLayout(self)
        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        bottom_splitter = QSplitter(Qt.Orientation.Vertical)

        # --- Widgets ---
        controls_panel = QWidget()
        controls_layout = QFormLayout(controls_panel)
        self.class_name_input = QLineEdit("MyObjectModel")
        self.select_obj_button = QPushButton("Select OBJ File...")
        self.convert_button = QPushButton("Convert to C++ Class")
        controls_layout.addRow("C++ Class Name:", self.class_name_input)
        controls_layout.addRow("OBJ File:", self.select_obj_button)
        controls_layout.addWidget(self.convert_button)
        self.toggle_view_button = QPushButton("Switch to Vertex View")
        self.toggle_view_button.setCheckable(True) # Make it a toggle button
        controls_layout.addWidget(self.toggle_view_button)

        # Replace the placeholder with our new functional viewer
        self.viewport = OpenGLViewer()
        self.viewport.setMinimumSize(400, 300)

        self.code_output = QsciScintilla()
        self.setup_code_editor()

        # --- Assemble Layout ---
        top_splitter.addWidget(controls_panel)
        top_splitter.addWidget(self.viewport)
        top_splitter.setSizes([350, 650])
        bottom_splitter.addWidget(top_splitter)
        bottom_splitter.addWidget(self.code_output)
        bottom_splitter.setSizes([400, 600])
        main_layout.addWidget(bottom_splitter)

        # --- Connections ---
        self.select_obj_button.clicked.connect(self.select_obj_file)
        self.convert_button.clicked.connect(self.perform_conversion)
        self.toggle_view_button.toggled.connect(self.on_toggle_view)

    def select_obj_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select OBJ File", "", "OBJ Files (*.obj)")
        if path:
            self.obj_file_path = path
            # When a file is selected, tell the viewport to load it
            self.viewport.load_model(path)

    def setup_code_editor(self):
        lexer = QsciLexerCPP()
        lexer.setDefaultFont(QFont("Courier New", 10))
        self.code_output.setLexer(lexer)
        self.code_output.setReadOnly(True)
        self.code_output.setMarginsBackgroundColor(QColor("#333333"))

    def on_toggle_view(self, checked):
        if checked:
            self.toggle_view_button.setText("Switch to Face View")
            self.viewport.set_render_mode(GL_POINTS)
        else:
            self.toggle_view_button.setText("Switch to Vertex View")
            self.viewport.set_render_mode(GL_TRIANGLES)

    def perform_conversion(self):
        class_name = self.class_name_input.text()
        if not class_name or not self.obj_file_path:
            QMessageBox.warning(self, "Input Error", "Please provide a Class Name and select an OBJ file.")
            return

        try:
            # PyWavefront automatically finds and parses the .mtl file
            scene = pywavefront.Wavefront(self.obj_file_path, create_materials=True, parse=True)
            
            # --- Generate C++ Code ---
            output_code = self._generate_cpp_header(class_name, scene)
            
            self.code_output.setText(output_code)
            QMessageBox.information(self, "Success", "OBJ class generated successfully.")

        except Exception as e:
            QMessageBox.critical(self, "Conversion Error", f"An error occurred: {e}")
            self.code_output.setText(f"// Error: {e}")

    def _generate_cpp_header(self, class_name, scene):
        """Generates the entire C++ header file content."""
        
        # --- 1. Generate Material Definitions ---
        material_defs = ""
        material_map = {} # Maps MTL name to C++ variable name
        material_count = 0
        
        for mat_name, material in scene.materials.items():
            cpp_var_name = f"mat_{material_count}_{mat_name.replace(' ', '_')}"
            material_map[mat_name] = cpp_var_name
            
            # Kd holds the diffuse color (R, G, B, A)
            r = int(material.diffuse[0] * 255)
            g = int(material.diffuse[1] * 255)
            b = int(material.diffuse[2] * 255)
            
            material_defs += f"\tSimpleMaterial {cpp_var_name} = SimpleMaterial(RGBColor({r}, {g}, {b}));\n"
            material_count += 1
            
        # --- 2. Generate Vertex and Index Data ---
        vert_str = ",\n\t\t".join([f"Vector3D({v[0]:.4f}f, {v[1]:.4f}f, {v[2]:.4f}f)" for v in scene.vertices])
        vertices_def = f"\tVector3D basisVertices[{len(scene.vertices)}] = {{\n\t\t{vert_str}\n\t}};\n\n"

        # --- 3. Generate Triangle Groups (one per material) ---
        triangle_groups = ""
        object_assignments = ""
        group_count = 0
        for mat_name, mesh in scene.meshes.items():
            if not mesh.materials: continue
            
            # PyWavefront stores vertices in a flat list: [v1_idx, t1_idx, n1_idx, v2_idx, ...]
            # We need to extract just the vertex indices.
            vert_indices = mesh.materials[0].vertices[::3]
            num_faces = len(vert_indices) // 3
            
            index_group_name = f"indexGroup_{group_count}"
            triangle_group_name = f"triangleGroup_{group_count}"
            
            face_str = ",\n\t\t".join([f"IndexGroup({vert_indices[i*3]}, {vert_indices[i*3+1]}, {vert_indices[i*3+2]})" for i in range(num_faces)])
            triangle_groups += f"\tIndexGroup {index_group_name}[{num_faces}] = {{\n\t\t{face_str}\n\t}};\n"
            
            # Link the triangle group to the vertices and material
            cpp_mat_name = material_map.get(mesh.materials[0].name, "simpleMaterial") # Fallback
            triangle_groups += f"\tTriangleGroup {triangle_group_name} = TriangleGroup(&basisVertices[0], &{index_group_name}[0], {len(scene.vertices)}, {num_faces});\n"
            
            # Create an Object3D for this group
            object_assignments += f"\tObject3D obj_{group_count} = Object3D(&{triangle_group_name}, &{cpp_mat_name});\n"
            group_count += 1

        # --- 4. Assemble the Final Class ---
        header = (
            f"#pragma once\n\n"
            f'#include "Scene/Materials/Static/SimpleMaterial.h"\n'
            f'#include "Scene/Objects/Object3D.h"\n'
            f'#include "Renderer/Utils/IndexGroup.h"\n\n'
            f"class {class_name} {{\nprivate:\n"
        )
        
        footer = (
            "public:\n"
            f"\t{class_name}() {{}}\n\n"
            f"\tvoid AddToScene(Scene& scene) {{\n"
            + "".join([f"\t\tscene.AddObject(&obj_{i});\n" for i in range(group_count)])
            + "\t}\n};"
        )
        
        return header + material_defs + "\n" + vertices_def + triangle_groups + "\n" + object_assignments + "\n" + footer
    