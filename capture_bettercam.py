import asyncio
import cv2
import bettercam
import multiprocessing
import ctypes
import time
import queue
import numpy as np
from av import VideoFrame
from aiortc import VideoStreamTrack

GAMMA = 2.2
INV_GAMMA = 1.0 / GAMMA
GAMMA_LUT = np.array([((i / 255.0) ** INV_GAMMA) * 255 for i in np.arange(0, 256)]).astype("uint8")

def bettercam_worker(queue_obj, stop_event, fps, target_size, monitor_idx, dev_idx, resize_mode):
    ctypes.windll.winmm.timeBeginPeriod(1)
    camera = None
    
    def init_cam():
        try:
            if camera: camera.stop()
        except: pass
        cam = bettercam.create(device_idx=dev_idx, output_idx=monitor_idx, output_color="RGB")
        if cam: cam.start(target_fps=fps)
        return cam

    camera = init_cam()
    last_frame = np.zeros((target_size[1], target_size[0], 3), dtype=np.uint8)
    frame_time = 1.0 / fps

    try:
        while not stop_event.is_set():
            try:
                start_time = time.time()
                
                if not camera:
                    time.sleep(0.5)
                    camera = init_cam()
                    if not camera: continue
                    
                frame = camera.get_latest_frame()
                
                if frame is not None:
                    if resize_mode != "disabled" and (frame.shape[1] != target_size[0] or frame.shape[0] != target_size[1]):
                        interp_method = cv2.INTER_NEAREST if resize_mode == "fast" else cv2.INTER_LINEAR
                        frame = cv2.resize(frame, target_size, interpolation=interp_method)
                    last_frame = frame
                    
                if queue_obj.full():
                    try: queue_obj.get_nowait()
                    except: pass
                queue_obj.put(last_frame)
                
                if frame is None:
                    elapsed = time.time() - start_time
                    if frame_time > elapsed:
                        time.sleep(frame_time - elapsed)
                else:
                    time.sleep(0.001)

            except Exception as e:
                time.sleep(0.5)
                camera = init_cam()
                
    except KeyboardInterrupt:
        pass
    finally:
        if camera: camera.stop()
        ctypes.windll.winmm.timeEndPeriod(1)

class BetterCamTrack(VideoStreamTrack):
    def __init__(self, fps=60, target_width=1920, target_height=1080, monitor_idx=0, dev_idx=0, resize_mode="fast", config_state=None):
        super().__init__()
        self.config_state = config_state or {}
        self.queue = multiprocessing.Queue(maxsize=2)
        self.stop_event = multiprocessing.Event()
        self.process = multiprocessing.Process(
            target=bettercam_worker,
            args=(self.queue, self.stop_event, fps, (target_width, target_height), monitor_idx, dev_idx, resize_mode),
            daemon=True
        )
        self.process.start()

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        loop = asyncio.get_event_loop()
        
        frame_numpy = None
        while self.readyState != "ended":
            try:
                frame_numpy = await loop.run_in_executor(None, self.queue.get, True, 0.1)
                break
            except queue.Empty:
                continue
                
        if frame_numpy is None:
            raise Exception("Трек остановлен")

        if not self.config_state.get("video_enabled", True):
            frame_numpy = np.zeros_like(frame_numpy)

        frame_numpy = cv2.LUT(frame_numpy, GAMMA_LUT)
        video_frame = VideoFrame.from_ndarray(frame_numpy, format="rgb24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame

    def stop(self):
        self.stop_event.set() 
        while not self.queue.empty():
            try: self.queue.get_nowait()
            except: break
            
        super().stop()