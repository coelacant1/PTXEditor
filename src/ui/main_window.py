# src/ui/main_window.py
import os
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QSplitter, 
                               QStackedWidget, QMessageBox, QPushButton)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction

from .viewport import Viewport
from .log_panel import LogPanel
from .camera_importer import CameraPanel
from .gif_importer import GifPanel
from .image_importer import ImagePanel
from .obj_importer import ObjPanel

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("PTX Project Editor")
        self.setGeometry(100, 100, 1600, 900)
        self.current_project_path = None
        self.recompile_needed = False

        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
        self.projects_root = os.path.join(project_root, "projects")
        os.makedirs(self.projects_root, exist_ok=True)

        self.create_actions()
        self.create_toolbar()

        self.viewport = Viewport()
        self.log_panel = LogPanel()
        self.camera_panel = CameraPanel()
        self.gif_panel = GifPanel()
        self.image_panel = ImagePanel()
        self.obj_panel = ObjPanel()

        self.panel_stack = QStackedWidget()
        self.panel_stack.addWidget(self.viewport)
        self.panel_stack.addWidget(self.camera_panel)
        self.panel_stack.addWidget(self.gif_panel)
        self.panel_stack.addWidget(self.image_panel)
        self.panel_stack.addWidget(self.obj_panel)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        bottom_splitter = QSplitter(Qt.Orientation.Vertical)
        
        top_splitter.addWidget(self.panel_stack)
        top_splitter.setSizes([300, 1300])

        bottom_splitter.addWidget(top_splitter)
        bottom_splitter.addWidget(self.log_panel)
        bottom_splitter.setSizes([800, 100])
        
        main_layout.addWidget(bottom_splitter)

    def create_actions(self):
        self.action_compile  = QAction("Compile", self)
        self.action_run      = QAction("Run", self)
        self.action_pause    = QAction("Pause", self)
        self.action_viewport = QAction("Viewport", self)
        self.action_camera   = QAction("Camera Importer", self)
        self.action_fbx      = QAction("FBX Importer", self)
        self.action_gif      = QAction("GIF Importer", self)
        self.action_image    = QAction("Image Importer", self)
        self.action_obj      = QAction("OBJ Importer", self)

        self.action_compile.triggered.connect(self.on_compile)
        self.action_run.triggered.connect(self.on_run)
        self.action_pause.triggered.connect(self.on_pause)
        self.action_viewport.triggered.connect(self.on_viewport)
        self.action_camera.triggered.connect(self.on_camera)
        self.action_fbx.triggered.connect(self.on_fbx)
        self.action_gif.triggered.connect(self.on_gif)
        self.action_image.triggered.connect(self.on_image)
        self.action_obj.triggered.connect(self.on_obj)

    def create_toolbar(self):
        toolbar = self.addToolBar("Main Toolbar")
        toolbar.addAction(self.action_compile)
        toolbar.addAction(self.action_run)
        toolbar.addAction(self.action_pause)

        toolbar.addSeparator()
        toolbar.addAction(self.action_viewport)
        toolbar.addAction(self.action_camera)
        toolbar.addAction(self.action_fbx)
        toolbar.addAction(self.action_gif)
        toolbar.addAction(self.action_image)
        toolbar.addAction(self.action_obj)

    def on_compile(self):
        self.log_panel.log_message("Placeholder: Kicking off build...")
    
    def on_run(self):
        self.log_panel.log_message("Placeholder: Run...")
    
    def on_pause(self):
        self.log_panel.log_message("Placeholder: Pausing...")
    
    def on_viewport(self):
        self.panel_stack.setCurrentIndex(0)
        self.log_panel.log_message("Placeholder: Opening viewport...")
    
    def on_camera(self):
        self.panel_stack.setCurrentIndex(1)
        self.log_panel.log_message("Placeholder: Opening camera importer...")
    
    def on_fbx(self):
        self.panel_stack.setCurrentIndex(2)
        self.log_panel.log_message("Placeholder: Opening fbx importer...")
    
    def on_gif(self):
        self.panel_stack.setCurrentIndex(3)
        self.log_panel.log_message("Placeholder: Opening gif importer...")
    
    def on_image(self):
        self.panel_stack.setCurrentIndex(4)
        self.log_panel.log_message("Placeholder: Opening image importer...")
    
    def on_obj(self):
        self.panel_stack.setCurrentIndex(5)
        self.log_panel.log_message("Placeholder: Opening obj importer...")
