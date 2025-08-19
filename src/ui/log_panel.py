from PyQt6.QtWidgets import QTextEdit

class LogPanel(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setStyleSheet("""
            QTextEdit {
                font-family: 'Courier New', monospace;
                background-color: #1E1E1E;
                color: #CCCCCC;
            }
        """)

    def log_message(self, message):
        """Public slot to append a message to the log."""
        self.append(message)
