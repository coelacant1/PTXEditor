# src/ui/gif_converter_panel.py
import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, 
                               QPushButton, QLabel, QFileDialog, QMessageBox, QSplitter)
from PyQt6.QtGui import QMovie
from PyQt6.QtCore import Qt
from PyQt6.Qsci import QsciScintilla, QsciLexerCPP
from PyQt6.QtGui import QFont, QColor

class GifPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.input_file_path = ""

        # --- Layouts ---
        main_layout = QVBoxLayout(self)
        top_form_layout = QFormLayout()
        top_form_layout.setContentsMargins(10, 10, 10, 10)
        
        # A splitter to divide the preview and the code output
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Widgets ---
        # Left side (controls and preview)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        self.name_input = QLineEdit("myGifAnimation")
        self.select_input_button = QPushButton("Select Input GIF...")
        self.convert_button = QPushButton("Convert to C++ Header")
        self.convert_button.setStyleSheet("background-color: #007ACC; color: white; padding: 5px;")

        top_form_layout.addRow("C++ Variable Name:", self.name_input)
        top_form_layout.addRow("Input GIF File:", self.select_input_button)

        # GIF Previewer
        self.gif_preview_label = QLabel("No GIF selected.")
        self.gif_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gif_preview_label.setMinimumSize(200, 200)
        self.gif_preview_label.setStyleSheet("background-color: #1E1E1E; border: 1px solid #555;")
        self.movie = None

        left_layout.addLayout(top_form_layout)
        left_layout.addWidget(self.gif_preview_label, 1)
        left_layout.addWidget(self.convert_button)

        # Right side (C++ code output)
        self.code_output = QsciScintilla()
        self.setup_code_editor()

        # Add panels to splitter
        splitter.addWidget(left_panel)
        splitter.addWidget(self.code_output)
        splitter.setSizes([400, 600]) # Initial size ratio

        main_layout.addWidget(splitter)

        # --- Connections ---
        self.select_input_button.clicked.connect(self.select_input_file)
        self.convert_button.clicked.connect(self.perform_conversion)

    def setup_code_editor(self):
        """Configures the QScintilla widget for read-only C++ display."""
        lexer = QsciLexerCPP()
        lexer.setDefaultFont(QFont("Courier New", 11))
        self.code_output.setLexer(lexer)
        self.code_output.setReadOnly(True)
        self.code_output.setMarginsBackgroundColor(QColor("#333333"))

    def select_input_file(self):
        """Opens a dialog to select the input GIF file and starts the preview."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Input GIF", "", "GIF Files (*.gif)")
        if file_path:
            self.input_file_path = file_path
            
            # Stop any previous animation
            if self.movie:
                self.movie.stop()

            self.movie = QMovie(self.input_file_path)
            self.gif_preview_label.setMovie(self.movie)
            self.movie.start()

    def perform_conversion(self):
        """Reads the GIF data and generates the C++ byte array."""
        variable_name = self.name_input.text()
        
        if not variable_name:
            QMessageBox.warning(self, "Input Error", "Please enter a C++ variable name.")
            return
        if not self.input_file_path:
            QMessageBox.warning(self, "Input Error", "Please select an input GIF file.")
            return

        try:
            with open(self.input_file_path, 'rb') as f:
                gif_data = f.read()

            # --- Generate C++ Code ---
            hex_values = [f"0x{byte:02x}" for byte in gif_data]
            
            cpp_code = f"// Generated from: {os.path.basename(self.input_file_path)}\n"
            cpp_code += "#pragma once\n\n"
            cpp_code += f"const unsigned char {variable_name}[] = {{\n    "
            
            # Format into lines of 12 bytes for readability
            for i, hex_val in enumerate(hex_values):
                cpp_code += hex_val + ", "
                if (i + 1) % 12 == 0:
                    cpp_code += "\n    "
            
            cpp_code = cpp_code.rstrip(", \n    ") + "\n};"
            cpp_code += f"\n\nconst int {variable_name}_len = {len(gif_data)};"

            self.code_output.setText(cpp_code)
            QMessageBox.information(self, "Success", "GIF data converted successfully.")

        except Exception as e:
            QMessageBox.critical(self, "Conversion Error", f"An error occurred: {e}")
            self.code_output.setText(f"// Error: {e}")
