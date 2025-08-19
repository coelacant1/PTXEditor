# src/ui/code_editor.py
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtGui import QFont, QColor
from PyQt6.Qsci import QsciScintilla, QsciLexerCPP

class CodeEditor(QsciScintilla):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.current_file_path = None

        self.setUtf8(True)
        font = QFont("Courier New", 12)

        lexer = QsciLexerCPP()
        lexer.setDefaultFont(font)
        self.setLexer(lexer)

        fontmetrics = self.fontMetrics()
        self.setMarginsFont(font)
        self.setMarginWidth(0, fontmetrics.horizontalAdvance("00000") + 6)
        self.setMarginLineNumbers(0, True)
        self.setMarginsBackgroundColor(QColor("#333333"))
        self.setMarginsForegroundColor(QColor("#CCCCCC"))

        self.setAutoIndent(True)
        self.setCaretLineVisible(True)
        self.setCaretLineBackgroundColor(QColor("#404040"))
        self.setBraceMatching(QsciScintilla.BraceMatch.SloppyBraceMatch)

    def load_file(self, file_path):
        """Loads a file's content into the editor."""
        self.current_file_path = file_path
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.setText(content)
        except Exception as e:
            self.setText(f"// Could not load file: {e}")
            self.current_file_path = None

    def get_content(self):
        """Gets the current text content from the editor."""
        return self.text()