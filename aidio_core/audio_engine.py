import ctypes
import numpy as np
import os

# Структура C++ для получения списка программ со звуком
class PacProcessInfo(ctypes.Structure):
    _fields_ = [
        ("processId", ctypes.c_ulong),
        ("processName", ctypes.c_wchar * 260),
        ("windowTitle", ctypes.c_wchar * 260)
    ]

class AudioCaptureEngine:
    def __init__(self, dll_path):
        if not os.path.exists(dll_path):
            raise FileNotFoundError(f"DLL не найдена по пути: {dll_path}")
            
        self.lib = ctypes.CDLL(dll_path)
        self.handle = ctypes.c_void_p()
        self._setup_ctypes()
        self._data_cb_ptr = None
        self._level_cb_ptr = None

    def _setup_ctypes(self):
        self.DATA_CB = ctypes.CFUNCTYPE(None, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32, ctypes.c_void_p)
        self.LEVEL_CB = ctypes.CFUNCTYPE(None, ctypes.c_float, ctypes.c_void_p)
        self.lib.PacStartCapture.argtypes = [
            ctypes.c_ulong, ctypes.c_int, ctypes.c_wchar_p,
            self.LEVEL_CB, self.DATA_CB, ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p)
        ]

    def get_audio_processes(self):
        """Возвращает список запущенных процессов, которые сейчас могут издавать звук"""
        self.lib.PacEnumerateAudioProcesses.argtypes = [ctypes.POINTER(PacProcessInfo), ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        processes = (PacProcessInfo * 64)()
        actual_count = ctypes.c_int(0)
        
        res = self.lib.PacEnumerateAudioProcesses(processes, 64, ctypes.byref(actual_count))
        apps = []
        if res == 0:
            for i in range(actual_count.value):
                pid = processes[i].processId
                name = processes[i].processName
                apps.append(f"[{pid}] {name}")
                
        return apps if apps else ["[0] Звуковых процессов не найдено"]

    def start(self, pid, mode, on_data_callback):
        """
        pid: ID процесса
        mode: 0 = захватывать ТОЛЬКО этот процесс, 1 = захватывать систему КРОМЕ этого процесса
        """
        def internal_data_handler(data_ptr, size, user_data):
            raw_bytes = ctypes.string_at(data_ptr, size)
            floats = np.frombuffer(raw_bytes, dtype=np.float32)
            ints = (floats * 32767).astype(np.int16)
            on_data_callback(ints.tobytes())

        self._data_cb_ptr = self.DATA_CB(internal_data_handler)
        self._level_cb_ptr = self.LEVEL_CB(lambda lvl, ud: None) 

        res = self.lib.PacStartCapture(
            pid, mode, None, 
            self._level_cb_ptr, self._data_cb_ptr, 
            None, ctypes.byref(self.handle)
        )
        return res == 0

    def stop(self):
        if self.handle:
            self.lib.PacStopCapture(self.handle)
            self.handle = ctypes.c_void_p()