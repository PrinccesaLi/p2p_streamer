import asyncio
import numpy as np
import fractions
from av import AudioFrame
from aiortc import AudioStreamTrack
from aidio_core.audio_engine import AudioCaptureEngine

class SystemAudioTrack(AudioStreamTrack):
    def __init__(self, config_state):
        super().__init__()
        self.config_state = config_state
        self._timestamp = 0 
        self.sample_rate = 48000
        self.channels = 2
        
        # WebRTC (Opus) 
        self.chunk_samples = 960 
        self.chunk_bytes = self.chunk_samples * self.channels * 2 # 3840 
        
        self.engines = {}  #  DLL {pid: engine}
        self.queues = {}   # 20мс {pid: queue}
        self.loop = asyncio.get_event_loop()

    def _start_engine(self, pid):
        engine = AudioCaptureEngine("bin/ProcessAudioCapture.dll")
        q = asyncio.Queue()
    
        buffer = bytearray()
        
        def on_audio_data(pcm_bytes):
            nonlocal buffer
            buffer.extend(pcm_bytes)
            
            while len(buffer) >= self.chunk_bytes:
                chunk = bytes(buffer[:self.chunk_bytes])
                del buffer[:self.chunk_bytes]
                
                if q.qsize() < 10:
                    self.loop.call_soon_threadsafe(q.put_nowait, chunk)
                
        if engine.start(pid, 0, on_audio_data):
            self.engines[pid] = engine
            self.queues[pid] = q
            print(f"🔊 [МИКШЕР] Подключен источник: PID {pid}")
        else:
            print(f"❌ [МИКШЕР] Ошибка захвата PID {pid}")

    def _stop_engine(self, pid):
        if pid in self.engines:
            self.engines[pid].stop()
            del self.engines[pid]
            del self.queues[pid]
            print(f"🔇 [МИКШЕР] Отключен источник: PID {pid}")

    async def recv(self):
        active_pids = self.config_state.get("active_audio_pids", [])
        
        for pid in active_pids:
            if pid not in self.engines:
                self._start_engine(pid)
                
        for pid in list(self.engines.keys()):
            if pid not in active_pids:
                self._stop_engine(pid)

        frames = []
        active_queues = list(self.queues.values())
        
        if active_queues:
            try:

                first_frame = await active_queues[0].get()
                frames.append(first_frame)
                
                for q in active_queues[1:]:
                    try:
                        frames.append(q.get_nowait())
                    except asyncio.QueueEmpty:
                        pass
            except Exception:
                pass
        else:
            await asyncio.sleep(0.02)

        if not frames or not self.config_state.get("audio_enabled", True):
            mixed_audio = np.zeros((1, self.chunk_samples * self.channels), dtype=np.int16)
        else:
            mixed_audio = np.zeros(self.chunk_samples * self.channels, dtype=np.int32) 
            
            for frame_bytes in frames:
                arr = np.frombuffer(frame_bytes, dtype=np.int16)
                if len(arr) == len(mixed_audio):
                    mixed_audio += arr
                    
            mixed_audio = np.clip(mixed_audio, -32768, 32767).astype(np.int16).reshape(1, -1)

        frame = AudioFrame.from_ndarray(mixed_audio, format='s16', layout='stereo')
        frame.sample_rate = self.sample_rate
        frame.pts = self._timestamp
        frame.time_base = fractions.Fraction(1, self.sample_rate)
        
        self._timestamp += self.chunk_samples 
        return frame

    def stop(self):
        for pid in list(self.engines.keys()):
            self._stop_engine(pid)
        super().stop()
        print("[МИКШЕР] Полностью остановлен.")