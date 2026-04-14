import sys
import os

# ── Windows DLL search path ────────────────────────────────────────────────
# Must be done BEFORE importing PyQt5 (or any extension module).
# In conda envs the Qt runtime DLLs live in <env>/Library/bin/ and
# the Qt platform / imageformat plugins in <env>/Library/plugins/.
def _setup_dll_paths():
    """Add conda Qt DLL and plugin directories to the process DLL search."""
    # Detect conda env root: go up from site-packages/PyQt5 → env root
    try:
        import PyQt5
        pyqt5_dir = os.path.dirname(PyQt5.__file__)
        env_root = os.path.normpath(os.path.join(pyqt5_dir, "..", "..", ".."))
    except Exception:
        env_root = None

    added = False
    if env_root and os.path.isdir(env_root):
        lib_dir = os.path.join(env_root, "Library", "bin")
        plugins_dir = os.path.join(env_root, "Library", "plugins")
        for d in (lib_dir, plugins_dir):
            if os.path.isdir(d):
                os.add_dll_directory(d)   # Python 3.8+ on Windows
                added = True
        # Also register Qt plugin path for QCoreApplication
        if os.path.isdir(plugins_dir):
            from PyQt5.QtCore import QCoreApplication
            QCoreApplication.addLibraryPath(plugins_dir)
    return added


_setup_dll_paths()
# ── Qt / app init ──────────────────────────────────────────────────────────
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from ui.main_window import MainWindow


def main():
    # high-DPI support
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("标注审核工具")
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
