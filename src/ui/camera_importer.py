import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QLineEdit, 
                               QPushButton, QLabel, QFileDialog, QMessageBox)

class CameraPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.input_file_path = ""
        self.output_file_path = ""

        # --- Layouts ---
        main_layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        form_layout.setContentsMargins(10, 10, 10, 10)
        form_layout.setSpacing(10)

        # --- Widgets ---
        self.name_input = QLineEdit("MyPixelArray")
        
        self.input_path_label = QLabel("No file selected.")
        self.select_input_button = QPushButton("Select Input CSV...")
        
        self.output_path_label = QLabel("No location selected.")
        self.select_output_button = QPushButton("Select Output Location...")

        self.convert_button = QPushButton("Convert to C++ Header")
        self.convert_button.setStyleSheet("background-color: #007ACC; color: white; padding: 5px;")

        # Add widgets to the form layout
        form_layout.addRow("C++ Variable Name:", self.name_input)
        form_layout.addRow("Input Altium P&P File:", self.select_input_button)
        form_layout.addRow("", self.input_path_label)
        form_layout.addRow("Output Header File (.hpp):", self.select_output_button)
        form_layout.addRow("", self.output_path_label)
        
        main_layout.addLayout(form_layout)
        main_layout.addStretch() # Pushes the convert button to the bottom
        main_layout.addWidget(self.convert_button)

        # --- Connections ---
        self.select_input_button.clicked.connect(self.select_input_file)
        self.select_output_button.clicked.connect(self.select_output_file)
        self.convert_button.clicked.connect(self.perform_conversion)

    def select_input_file(self):
        """Opens a dialog to select the input CSV file."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Input CSV", "", "CSV Files (*.csv);;All Files (*)")
        if file_path:
            self.input_file_path = file_path
            self.input_path_label.setText(os.path.basename(file_path))

    def select_output_file(self):
        """Opens a dialog to select the save location for the .hpp file."""
        file_path, _ = QFileDialog.getSaveFileName(self, "Select Output Location", "", "C++ Header Files (*.hpp)")
        if file_path:
            self.output_file_path = file_path
            self.output_path_label.setText(os.path.basename(file_path))

    def perform_conversion(self):
        """The main logic to read the CSV and write the C++ header."""
        variable_name = self.name_input.text()
        
        # --- Input Validation ---
        if not variable_name:
            QMessageBox.warning(self, "Input Error", "Please enter a C++ variable name.")
            return
        if not self.input_file_path:
            QMessageBox.warning(self, "Input Error", "Please select an input CSV file.")
            return
        if not self.output_file_path:
            QMessageBox.warning(self, "Input Error", "Please select an output file location.")
            return

        try:
            with open(self.input_file_path, 'r') as infile:
                lines = infile.read().splitlines()

            x_coords, y_coords = [], []
            for line in lines:
                parts = line.split(",")
                if len(parts) >= 3:
                    x_coords.append(float(parts[1]))
                    y_coords.append(float(parts[2]))

            # --- Generate C++ Code ---
            with open(self.output_file_path, "w") as outfile:
                outfile.write("#pragma once\n\n")
                outfile.write(f"// Generated from: {os.path.basename(self.input_file_path)}\n\n")
                outfile.write(f"Vector2D {variable_name}[{len(x_coords)}] = {{\n")

                for i in range(len(x_coords)):
                    line_end = "),\n" if i < len(x_coords) - 1 else ")\n}};\n"
                    outfile.write(f"\tVector2D({x_coords[i]:.2f}f, {y_coords[i]:.2f}f{line_end}")
            
            QMessageBox.information(self, "Success", f"Successfully generated {os.path.basename(self.output_file_path)}.")

        except Exception as e:
            QMessageBox.critical(self, "Conversion Error", f"An error occurred: {e}")
