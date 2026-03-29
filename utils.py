import sys
import os

def resource_path(relative_path):
    """Возвращает абсолютный путь к файлу, учитывая временную папку PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
        
    return os.path.join(base_path, relative_path)