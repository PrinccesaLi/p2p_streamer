import json
import ctypes
from ctypes import wintypes

# --- WIN32 API СТРУКТУРЫ И КОНСТАНТЫ ---
user32 = ctypes.WinDLL('user32', use_last_error=True)
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.MapVirtualKeyW.restype = wintypes.UINT

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

# Флаги клавиатуры
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP       = 0x0002
KEYEVENTF_UNICODE     = 0x0004
KEYEVENTF_SCANCODE    = 0x0008

# Флаги мыши
MOUSEEVENTF_MOVE       = 0x0001
MOUSEEVENTF_LEFTDOWN   = 0x0002
MOUSEEVENTF_LEFTUP     = 0x0004
MOUSEEVENTF_RIGHTDOWN  = 0x0008
MOUSEEVENTF_RIGHTUP    = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP   = 0x0040
MOUSEEVENTF_ABSOLUTE   = 0x8000

# Структуры C для SendInput
class MOUSEINPUT(ctypes.Structure):
    _fields_ = (("dx",          wintypes.LONG),
                ("dy",          wintypes.LONG),
                ("mouseData",   wintypes.DWORD),
                ("dwFlags",     wintypes.DWORD),
                ("time",        wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)))

class KEYBDINPUT(ctypes.Structure):
    _fields_ = (("wVk",         wintypes.WORD),
                ("wScan",       wintypes.WORD),
                ("dwFlags",     wintypes.DWORD),
                ("time",        wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)))

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (("uMsg",    wintypes.DWORD),
                ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD))

class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = (("ki", KEYBDINPUT),
                    ("mi", MOUSEINPUT),
                    ("hi", HARDWAREINPUT))
    _anonymous_ = ("_input",)
    _fields_ = (("type",   wintypes.DWORD),
                ("_input", _INPUT))

VK_CODE_MAP = {
    "KeyA": 0x41, "KeyB": 0x42, "KeyC": 0x43, "KeyD": 0x44, "KeyE": 0x45, "KeyF": 0x46, "KeyG": 0x47,
    "KeyH": 0x48, "KeyI": 0x49, "KeyJ": 0x4A, "KeyK": 0x4B, "KeyL": 0x4C, "KeyM": 0x4D, "KeyN": 0x4E,
    "KeyO": 0x4F, "KeyP": 0x50, "KeyQ": 0x51, "KeyR": 0x52, "KeyS": 0x53, "KeyT": 0x54, "KeyU": 0x55,
    "KeyV": 0x56, "KeyW": 0x57, "KeyX": 0x58, "KeyY": 0x59, "KeyZ": 0x5A,
    "Digit1": 0x31, "Digit2": 0x32, "Digit3": 0x33, "Digit4": 0x34, "Digit5": 0x35,
    "Digit6": 0x36, "Digit7": 0x37, "Digit8": 0x38, "Digit9": 0x39, "Digit0": 0x30,
    "Space": 0x20, "Enter": 0x0D, "Escape": 0x1B, "Backspace": 0x08, "Tab": 0x09,
    "ShiftLeft": 0xA0, "ShiftRight": 0xA1, "ControlLeft": 0xA2, "ControlRight": 0xA3,
    "AltLeft": 0xA4, "AltRight": 0xA5, "ArrowUp": 0x26, "ArrowDown": 0x28, "ArrowLeft": 0x25, "ArrowRight": 0x27,
}

class RemoteController:
    def __init__(self, width=None, height=None):
        self.pressed_keys = set()

    def _send_input(self, *inputs):
        nInputs = len(inputs)
        LPINPUT = INPUT * nInputs
        pInputs = LPINPUT(*inputs)
        user32.SendInput(nInputs, pInputs, ctypes.sizeof(INPUT))

    def _create_mouse_input(self, flags, x=0, y=0, data=0):
        mi = MOUSEINPUT(dx=x, dy=y, mouseData=data, dwFlags=flags, time=0, dwExtraInfo=None)
        return INPUT(type=INPUT_MOUSE, mi=mi)

    def _create_key_input(self, vk=0, scan=0, flags=0):
        ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=None)
        return INPUT(type=INPUT_KEYBOARD, ki=ki)

    def handle_message(self, message):
        try:
            data = json.loads(message)
            action = data.get("action")
            
            if action in ["mousedown", "mouseup", "mousemove", "mouse_delta"]:
                button = data.get("button", "left")

                if action == "mouse_delta":
                    SENSITIVITY = 1.0 
                    dx = int(data.get("dx", 0) * SENSITIVITY)
                    dy = int(data.get("dy", 0) * SENSITIVITY)
                    
                    if dx != 0 or dy != 0:
                        self._send_input(self._create_mouse_input(MOUSEEVENTF_MOVE, dx, dy))

                elif action == "mousemove":
                    dx = int(data.get("x", 0) * 65535)
                    dy = int(data.get("y", 0) * 65535)
                    self._send_input(self._create_mouse_input(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, dx, dy))
                
                elif action == "mousedown":
                    flag = MOUSEEVENTF_LEFTDOWN
                    if button == "right": flag = MOUSEEVENTF_RIGHTDOWN
                    elif button == "middle": flag = MOUSEEVENTF_MIDDLEDOWN
                    self._send_input(self._create_mouse_input(flag, 0, 0))
                    
                elif action == "mouseup":
                    flag = MOUSEEVENTF_LEFTUP
                    if button == "right": flag = MOUSEEVENTF_RIGHTUP
                    elif button == "middle": flag = MOUSEEVENTF_MIDDLEUP
                    self._send_input(self._create_mouse_input(flag, 0, 0))

            elif action in ["keydown", "keyup"]:
                code = data.get("code", "")  
                raw_key = data.get("key", "") 
                vk_code = None

                if code in VK_CODE_MAP:
                    vk_code = VK_CODE_MAP[code]
                elif raw_key in VK_CODE_MAP:
                    vk_code = VK_CODE_MAP[raw_key]
                elif len(raw_key) == 1:
                    vk_code = ord(raw_key.upper())

                if vk_code:
                    flags = 0
                    if code in ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "PageUp", "PageDown", "Home", "End", "Insert", "Delete"]:
                        flags |= KEYEVENTF_EXTENDEDKEY

                    scan_code = user32.MapVirtualKeyW(vk_code, 0)
                    flags |= KEYEVENTF_SCANCODE

                    if action == "keydown":
                        self._send_input(self._create_key_input(vk=0, scan=scan_code, flags=flags))
                        self.pressed_keys.add((scan_code, flags))
                    elif action == "keyup":
                        self._send_input(self._create_key_input(vk=0, scan=scan_code, flags=flags | KEYEVENTF_KEYUP))
                        if (scan_code, flags) in self.pressed_keys:
                            self.pressed_keys.remove((scan_code, flags))

        except Exception as e:
            pass

        
    def release_all(self):
        inputs = []
        for scan_code, flags in list(self.pressed_keys):
            inputs.append(self._create_key_input(vk=0, scan=scan_code, flags=flags | KEYEVENTF_KEYUP))
        if inputs:
            self._send_input(*inputs)
        self.pressed_keys.clear()