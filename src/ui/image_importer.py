# src/ui/image_converter_panel.py
import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, 
                               QPushButton, QLabel, QFileDialog, QMessageBox, 
                               QSplitter, QSpinBox)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt
from PyQt6.Qsci import QsciScintilla, QsciLexerCPP
from PyQt6.QtGui import QFont, QColor
from PIL import Image

class ImagePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.input_file_path = ""
        self.image_for_conversion = None

        main_layout = QVBoxLayout(self)
        top_form_layout = QFormLayout()
        top_form_layout.setContentsMargins(10, 10, 10, 10)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        self.class_name_input = QLineEdit("MyImage")
        self.num_colors_input = QSpinBox()
        self.num_colors_input.setRange(2, 256)
        self.num_colors_input.setValue(16)
        self.select_input_button = QPushButton("Select Input Image...")
        self.convert_button = QPushButton("Convert to C++ Class")
        self.convert_button.setStyleSheet("background-color: #007ACC; color: white; padding: 5px;")
        top_form_layout.addRow("C++ Class Name:", self.class_name_input)
        top_form_layout.addRow("Number of Colors:", self.num_colors_input)
        top_form_layout.addRow("Input Image:", self.select_input_button)
        self.image_preview_label = QLabel("No image selected.")
        self.image_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview_label.setMinimumSize(200, 200)
        self.image_preview_label.setStyleSheet("background-color: #1E1E1E; border: 1px solid #555;")
        left_layout.addLayout(top_form_layout)
        left_layout.addWidget(self.image_preview_label, 1)
        left_layout.addWidget(self.convert_button)
        self.code_output = QsciScintilla()
        self.setup_code_editor()
        splitter.addWidget(left_panel)
        splitter.addWidget(self.code_output)
        splitter.setSizes([400, 600])
        main_layout.addWidget(splitter)
        self.select_input_button.clicked.connect(self.select_input_file)
        self.convert_button.clicked.connect(self.perform_conversion)
        self.num_colors_input.valueChanged.connect(self.update_preview)

    def setup_code_editor(self):
        lexer = QsciLexerCPP()
        lexer.setDefaultFont(QFont("Courier New", 11))
        self.code_output.setLexer(lexer)
        self.code_output.setReadOnly(True)
        self.code_output.setMarginsBackgroundColor(QColor("#333333"))

    def select_input_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Input Image", "", "Image Files (*.png *.jpg *.bmp)")
        if file_path:
            self.input_file_path = file_path
            self.update_preview()
            
    def update_preview(self):
        if not self.input_file_path:
            return
        try:
            num_colors = self.num_colors_input.value()
            image = Image.open(self.input_file_path)

            self.image_for_conversion = image.convert("P", palette=Image.ADAPTIVE, colors=num_colors)
            
            image_for_display = self.image_for_conversion.convert("RGBA")
            
            pixmap = QPixmap.fromImage(image_for_display.toqimage())
            self.image_preview_label.setPixmap(pixmap.scaled(
                self.image_preview_label.size(), 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            ))
        except Exception as e:
            self.image_preview_label.setText(f"Error: {e}")
            self.image_for_conversion = None

    def perform_conversion(self):
        class_name = self.class_name_input.text()
        num_colors = self.num_colors_input.value()

        if not class_name:
            QMessageBox.warning(self, "Input Error", "Please enter a C++ class name.")
            return
        if not self.image_for_conversion:
            QMessageBox.warning(self, "Input Error", "Please select a valid input image.")
            return

        try:
            image = self.image_for_conversion
            w, h = image.size
            palette = image.getpalette()

            # --- Generate C++ Code ---
            data = f"#pragma once\n\n"
            data += f'#include "Materials/Image.h" // Assumed path\n\n'
            data += f"class {class_name} : public Image {{\n"
            data += "private:\n"
            data += f"\tstatic const uint8_t rgbMemory[{w * h}];\n"
            data += f"\tstatic const uint8_t rgbColors[{num_colors * 3}];\n\n"
            data += "public:\n"
            data += f"\t{class_name}(Vector2D size, Vector2D offset) : Image(rgbMemory, rgbColors, {w}, {h}, {num_colors}) {{\n"
            data += "\t\tSetSize(size);\n"
            data += "\t\tSetPosition(offset);\n"
            data += "\t}\n}};\n\n"

            pixel_indices = list(image.getdata())
            pixel_data_str = ", ".join(map(str, pixel_indices))
            data += f"const uint8_t {class_name}::rgbMemory[] PROGMEM = {{{pixel_data_str}}};\n\n"
            
            palette_data_str = ", ".join(map(str, palette[:num_colors * 3]))
            data += f"const uint8_t {class_name}::rgbColors[] PROGMEM = {{{palette_data_str}}};\n"
            
            self.code_output.setText(data)
            QMessageBox.information(self, "Success", "Image class generated successfully.")

        except Exception as e:
            QMessageBox.critical(self, "Conversion Error", f"An error occurred: {e}")
            self.code_output.setText(f"// Error: {e}")
