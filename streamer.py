import time

_DXGI_CACHE = {}

def _test_bettercam(monitor_idx):
    if monitor_idx in _DXGI_CACHE:
        return _DXGI_CACHE[monitor_idx]
        
    try:
        import bettercam
        for dev_idx in range(3):
            cam = bettercam.create(device_idx=dev_idx, output_idx=monitor_idx, output_color="BGR")
            if cam:
                cam.start(target_fps=10)
                time.sleep(0.3)
                frame = cam.get_latest_frame()
                cam.stop()
                if frame is not None and frame.any():
                    _DXGI_CACHE[monitor_idx] = dev_idx
                    return dev_idx 
    except Exception:
        pass
        
    _DXGI_CACHE[monitor_idx] = None
    return None


def create_screen_track(fps=60, target_width=1920, target_height=1080, monitor_idx=0, resize_mode="fast", config_state=None):
    print("\n[СИСТЕМА] Выполняю диагностику захвата экрана...")
    dev_idx = _test_bettercam(monitor_idx)
    
    if dev_idx is not None:
        print(f"[СИСТЕМА] Включен АППАРАТНЫЙ захват DXGI (GPU {dev_idx}).")
        from capture_bettercam import BetterCamTrack
        return BetterCamTrack(fps, target_width, target_height, monitor_idx, dev_idx, resize_mode, config_state)
    else:
        print("[СИСТЕМА] Аппаратный захват недоступен.")
        print("[СИСТЕМА] Включен ПРОГРАММНЫЙ захват (MSS).")
        from capture_mss import MSSTrack
        return MSSTrack(fps, target_width, target_height, monitor_idx, resize_mode, config_state)