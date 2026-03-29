import asyncio
import json
import websockets
import ctypes
import traceback
from screeninfo import get_monitors
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer, RTCRtpSender

from streamer import create_screen_track
from audio_capture import SystemAudioTrack
from codec_setup import setup_universal_encoder
from remote_control import RemoteController
from config import EncoderConfig

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

def get_mouse_pos():
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

async def run_signaling(server_url, config_state, update_ui_callback, stop_event, restart_event):
    config = RTCConfiguration(iceServers=[RTCIceServer(urls=["stun:stun.l.google.com:19302"])])
    
    pc = None
    active_pc = None  
    video_track = None
    audio_track = None
    controller = None
    cursor_task = None
    channel = None
    room_code = None
    ws_connection = None

    setup_lock = asyncio.Lock()

    async def cleanup_webrtc():
        nonlocal pc, video_track, audio_track, controller, cursor_task, active_pc
        
        active_pc = None 
        
        try:
            if cursor_task: cursor_task.cancel()
        except: pass
        try:
            if controller: controller.release_all()
        except: pass
        try:
            if video_track: video_track.stop()
        except: pass
        try:
            if audio_track: audio_track.stop()
        except: pass
        try:
            if pc: await pc.close()
        except: pass
        
        await asyncio.sleep(1.5)

    async def setup_webrtc():
        nonlocal pc, video_track, audio_track, controller, cursor_task, channel, active_pc

        if setup_lock.locked(): return
            
        async with setup_lock:
            print("\n" + "="*50)
            print("[СИСТЕМА] 1/5 - Очистка старых процессов...")
            await cleanup_webrtc()

            preset = config_state["preset"]
            width = config_state["width"]
            height = config_state["height"]
            monitor_idx = config_state["monitor_idx"]
            resize_mode = config_state["resize_mode"]

            print("[СИСТЕМА] 2/5 - Создание кодека...")
            setup_universal_encoder(preset, width, height)

            print("[СИСТЕМА] 3/5 - Инициализация WebRTC...")
            pc = RTCPeerConnection(configuration=config)
            active_pc = pc 

            @pc.on("connectionstatechange")
            async def on_connectionstatechange():
                if pc != active_pc: return 
                print(f"[WebRTC] Статус P2P соединения: {pc.connectionState}")
                if pc.connectionState in ["failed", "closed", "disconnected"]:
                    print("[WATCHDOG] Связь разорвана! Выполняю экстренный рестарт...")
                    restart_event.set()

            video_track = create_screen_track(fps=60, target_width=width, target_height=height, monitor_idx=monitor_idx, resize_mode=resize_mode, config_state=config_state)
            audio_track = SystemAudioTrack(config_state=config_state)
            
            pc.addTrack(video_track)
            pc.addTrack(audio_track)

            video_transceiver = next(t for t in pc.getTransceivers() if t.kind == "video")
            capabilities = RTCRtpSender.getCapabilities("video")
            video_transceiver.setCodecPreferences([codec for codec in capabilities.codecs if codec.name == "H264"])

            controller = RemoteController()
            channel = pc.createDataChannel("control")
            
            @channel.on("open")
            def on_open():
                try: channel.send(json.dumps({"action": "init_preset", "preset": preset}))
                except Exception: pass
                    
            @channel.on("message")
            def on_message(message):
                if config_state.get("allow_control", True):
                    asyncio.create_task(asyncio.to_thread(controller.handle_message, message))

            async def send_cursor_loop():
                monitors = get_monitors()
                mon = monitors[monitor_idx] if monitor_idx < len(monitors) else monitors[0]
                last_x, last_y = -1, -1
                was_control_allowed = config_state.get("allow_control", True)
                
                while not stop_event.is_set():
                    current_control_allowed = config_state.get("allow_control", True)
                    if was_control_allowed and not current_control_allowed:
                        if controller: controller.release_all()
                    was_control_allowed = current_control_allowed

                    if channel and channel.readyState == "open":
                        mx, my = get_mouse_pos()
                        rel_x = (mx - mon.x) / mon.width
                        rel_y = (my - mon.y) / mon.height
                        
                        if 0 <= rel_x <= 1 and 0 <= rel_y <= 1:
                            if rel_x != last_x or rel_y != last_y:
                                try:
                                    channel.send(json.dumps({"action": "cursor", "x": rel_x, "y": rel_y}))
                                    last_x, last_y = rel_x, rel_y
                                except Exception: pass
                    await asyncio.sleep(1/30)
                    
            cursor_task = asyncio.create_task(send_cursor_loop())

            offer = await pc.createOffer()
            target_kbps = EncoderConfig.get_bitrate(preset, width, height) // 1000
            sdp_lines = offer.sdp.split("\r\n")
            new_sdp_lines = [line if not line.startswith("m=video") else f"{line}\r\nb=AS:{target_kbps}" for line in sdp_lines]
            offer = RTCSessionDescription(sdp="\r\n".join(new_sdp_lines), type=offer.type)
            
            await pc.setLocalDescription(offer)
            
            print("[СИСТЕМА] 4/5 - Сбор сетевых маршрутов (ICE)...")
            await asyncio.sleep(1.5) 
            
            print("[СИСТЕМА] 5/5 - Отправка нового видео-пакета (Offer) на сервер...")
            try:
                if room_code and ws_connection:
                    await ws_connection.send(json.dumps({
                        "action": "offer", 
                        "code": room_code, 
                        "data": {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type},
                        "preset": preset
                    }))
                    print("[СИСТЕМА] Оффер успешно отправлен зрителю!")
                else:
                    print("[СИСТЕМА] Пропуск отправки")
            except websockets.exceptions.ConnectionClosed:
                pass
            except Exception as e:
                print(f"[СИСТЕМА] Ошибка отправки оффера: {e}")

    await setup_webrtc()

    async def signaling_loop():
        nonlocal ws_connection, room_code
        while not stop_event.is_set():
            try:
                # 1. ВКЛЮЧАЕМ ПИНГИ, чтобы роутер не убивал соединение через 2 минуты
                async with websockets.connect(server_url, ping_interval=20, ping_timeout=20) as ws:
                    ws_connection = ws
                    
                    create_payload = {"action": "create"}
                    if room_code: create_payload["code"] = room_code
                    await ws.send(json.dumps(create_payload))

                    async for msg in ws:
                        data = json.loads(msg)
                        if data["action"] == "created":
                            room_code = data["code"]
                            update_ui_callback(room_code)
                            
                            # 2. ФАТАЛЬНЫЙ БАГ БЫЛ ТУТ! 
                            # Раньше мы здесь слепо кидали оффер зрителю. 
                            # Теперь мы этого НЕ ДЕЛАЕМ. Оффер отправляется ТОЛЬКО при реальном рестарте видеоядра.
                            print(f"[СИСТЕМА] Связь с сервером установлена. Комната: {room_code}")

                        elif data["action"] == "answer":
                            answer = RTCSessionDescription(sdp=data["data"]["sdp"], type=data["data"]["type"])
                            await pc.setRemoteDescription(answer)
                            print("🚀 ЗРИТЕЛЬ УСПЕШНО ПОДКЛЮЧЕН!")
                            
                        elif data["action"] == "viewer_request_restart":
                            print("⚠️ [WATCHDOG] Зритель запросил видеопоток. Выполняю горячий старт...")
                            restart_event.set()
                            
            except Exception as e:
                if stop_event.is_set(): break
                print(f"⚠️ Потеряна связь с сигнальным сервером. Авто-реконнект через 3 сек...")
                await asyncio.sleep(3)

    async def watch_restart():
        while not stop_event.is_set():
            await restart_event.wait()
            if stop_event.is_set(): break
            restart_event.clear()
            await asyncio.sleep(0.5) 
            restart_event.clear() 
            
            try:
                await setup_webrtc()
                print("[СИСТЕМА]Рестарт ядра WebRTC завершен!")
            except Exception as e:
                print(f"[КРИТИЧЕСКАЯ ОШИБКА РЕСТАРТА] Ядро упало: {e}")
                traceback.print_exc()

    listener_task = asyncio.create_task(signaling_loop())
    restart_task = asyncio.create_task(watch_restart())
    
    await stop_event.wait()
    listener_task.cancel()
    restart_task.cancel()
    await cleanup_webrtc()
    print("[СИСТЕМА] WebRTC полностью остановлен.")