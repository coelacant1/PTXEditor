import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QSurfaceFormat
from ui.main_window import MainWindow

if __name__ == "__main__":
    fmt = QSurfaceFormat()
    fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setVersion(3, 3)
    QSurfaceFormat.setDefaultFormat(fmt)
    
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
