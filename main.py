"""Startpunkt von Proteus-BLE-Terminal-MK1."""
import os
import sys


def resource(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def main():
    if sys.platform == "win32":
        # Eigene Taskleisten-Gruppe (sonst erscheint das Python-Symbol)
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ProteusBLETerminal.MK1")
        except Exception:
            pass

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from app.theme import build_qss
    from app.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(build_qss(resource("assets")))
    icon = QIcon(resource(os.path.join("assets", "icon.ico")))
    app.setWindowIcon(icon)
    win = MainWindow(icon)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
