import customtkinter as ctk
import threading
import asyncio
import multiprocessing
import json
import os
from screeninfo import get_monitors

from utils import resource_path
from main import run_signaling 
from aidio_core.audio_engine import AudioCaptureEngine 

ctk.set_appearance_mode("dark")

BG_COLOR = "#0B0F19"         
PANEL_BG = "#151A28"         
ACCENT_CYAN = "#00E5FF"      
ACCENT_CYAN_HOVER = "#00B8D4"
ACCENT_PURPLE = "#536DFE"    
ACCENT_PURPLE_HOVER = "#3D5AFE"
SUCCESS = "#00E676"          
DANGER = "#FF1744"           
DANGER_HOVER = "#D50000"
TEXT_MAIN = "#FFFFFF"        
TEXT_MUTED = "#8A9AAB"       
INPUT_BG = "#0B0F19"         

class StreamerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("HARDCORE P2P STREAMER")
        self.geometry("920x620") 
        self.resizable(False, False)
        self.configure(fg_color=BG_COLOR)
        
        try: self.iconbitmap(resource_path("icon.ico"))
        except: pass 
            
        self.is_streaming = False
        self.settings_file = "streamer_settings.json"
        
        self.audio_scanner = AudioCaptureEngine(resource_path("bin/ProcessAudioCapture.dll"))
        self.audio_switches = {} 
        self.audio_vars = {}     

        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=20, pady=15)


        self.title_label = ctk.CTkLabel(
            self.main_container, 
            text="P2P STREAMER PRO", 
            font=ctk.CTkFont(family="Segoe UI Black", size=26, weight="bold"), 
            text_color=ACCENT_CYAN
        )
        self.title_label.pack(pady=(0, 15))

        self.columns_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.columns_frame.pack(fill="both", expand=True)

        self.left_pane = ctk.CTkFrame(self.columns_frame, fg_color="transparent")
        self.left_pane.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.right_pane = ctk.CTkFrame(self.columns_frame, fg_color="transparent")
        self.right_pane.pack(side="right", fill="both", expand=True, padx=(10, 0))

        self.frame_network = ctk.CTkFrame(self.left_pane, corner_radius=15, fg_color=PANEL_BG)
        self.frame_network.pack(fill="x", pady=(0, 15), ipadx=10, ipady=10)
        
        ctk.CTkLabel(self.frame_network, text="🌐 СЕРВЕР ПОДКЛЮЧЕНИЯ", font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT_MUTED).pack(anchor="w", padx=15, pady=(5, 5))
        
        self.server_var = ctk.StringVar(value="")
        self.server_inner_frame = ctk.CTkFrame(self.frame_network, fg_color="transparent")
        self.server_inner_frame.pack(fill="x", padx=15, pady=(0, 5))
        
        self.server_entry = ctk.CTkEntry(
            self.server_inner_frame, textvariable=self.server_var, 
            placeholder_text="wss://твой-сервер.com/ws", height=35,
            fg_color=INPUT_BG, border_color="#2A3441", text_color=TEXT_MAIN
        )
        self.server_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.paste_btn = ctk.CTkButton(
            self.server_inner_frame, text="📋 Вставить", width=90, height=35, 
            command=self.paste_server, fg_color=ACCENT_PURPLE, hover_color=ACCENT_PURPLE_HOVER,
            font=ctk.CTkFont(weight="bold")
        )
        self.paste_btn.pack(side="right")


        self.frame_video = ctk.CTkFrame(self.left_pane, corner_radius=15, fg_color=PANEL_BG)
        self.frame_video.pack(fill="x", pady=(0, 15), ipadx=10, ipady=10)
        
        ctk.CTkLabel(self.frame_video, text="⚙️ ПАРАМЕТРЫ ВИДЕО", font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT_MUTED).grid(row=0, column=0, columnspan=2, sticky="w", padx=15, pady=(5, 10))
        self.frame_video.grid_columnconfigure(1, weight=1)

        dropdown_kwargs = {
            "fg_color": INPUT_BG, "button_color": "#2A3441", 
            "button_hover_color": ACCENT_PURPLE, "dropdown_fg_color": PANEL_BG,
            "text_color": TEXT_MAIN, "dynamic_resizing": False, "height": 30
        }

        ctk.CTkLabel(self.frame_video, text="Экран:", text_color=TEXT_MAIN).grid(row=1, column=0, sticky="w", padx=15, pady=6)
        self.available_monitors = self.scan_monitors()
        self.monitor_var = ctk.StringVar(value=self.available_monitors[0])
        self.monitor_dropdown = ctk.CTkOptionMenu(self.frame_video, variable=self.monitor_var, values=self.available_monitors, **dropdown_kwargs)
        self.monitor_dropdown.grid(row=1, column=1, sticky="ew", padx=15, pady=6)

        ctk.CTkLabel(self.frame_video, text="Разрешение:", text_color=TEXT_MAIN).grid(row=2, column=0, sticky="w", padx=15, pady=6)
        self.res_var = ctk.StringVar(value="1920x1080 (FHD)")
        self.res_dropdown = ctk.CTkOptionMenu(self.frame_video, variable=self.res_var, values=["2560x1440 (2K)", "1920x1080 (FHD)", "1280x720 (HD)", "854x480 (SD)"], **dropdown_kwargs)
        self.res_dropdown.grid(row=2, column=1, sticky="ew", padx=15, pady=6)

        ctk.CTkLabel(self.frame_video, text="Качество:", text_color=TEXT_MAIN).grid(row=3, column=0, sticky="w", padx=15, pady=6)
        self.preset_var = ctk.StringVar(value="Balance")
        self.preset_dropdown = ctk.CTkOptionMenu(self.frame_video, variable=self.preset_var, values=["Speed", "Balance", "Quality", "Super Quality", "Super Duper"], **dropdown_kwargs)
        self.preset_dropdown.grid(row=3, column=1, sticky="ew", padx=15, pady=6)

        ctk.CTkLabel(self.frame_video, text="Рендер (CPU):", text_color=TEXT_MAIN).grid(row=4, column=0, sticky="w", padx=15, pady=6)
        self.resize_var = ctk.StringVar(value="Быстрый (Без нагрузки CPU)")
        self.resize_dropdown = ctk.CTkOptionMenu(self.frame_video, variable=self.resize_var, values=["Быстрый (Без нагрузки CPU)", "Качественный (Нагрузка CPU)", "Отключен (Оригинал)"], **dropdown_kwargs)
        self.resize_dropdown.grid(row=4, column=1, sticky="ew", padx=15, pady=6)

        self.gamma_label = ctk.CTkLabel(self.frame_video, text="Гамма: 2.2", text_color=TEXT_MAIN)
        self.gamma_label.grid(row=5, column=0, sticky="w", padx=15, pady=6)
        
        self.gamma_var = ctk.DoubleVar(value=2.2)
        self.gamma_slider = ctk.CTkSlider(
            self.frame_video, from_=0.5, to=3.5, variable=self.gamma_var, 
            number_of_steps=30, command=self.update_gamma_label,
            button_color=ACCENT_PURPLE, button_hover_color=ACCENT_PURPLE_HOVER, progress_color=ACCENT_CYAN
        )
        self.gamma_slider.grid(row=5, column=1, sticky="ew", padx=15, pady=6)

        self.frame_control = ctk.CTkFrame(self.left_pane, corner_radius=15, fg_color=PANEL_BG)
        self.frame_control.pack(fill="x", ipadx=10, ipady=10)

        self.toggles_frame = ctk.CTkFrame(self.frame_control, fg_color="transparent")
        self.toggles_frame.pack(fill="x", pady=(5, 5), padx=15)

        self.video_enabled_var = ctk.BooleanVar(value=True)
        self.video_switch = ctk.CTkSwitch(self.toggles_frame, text="🎥 Видео", variable=self.video_enabled_var, command=self.update_live_toggles, progress_color=ACCENT_CYAN)
        self.video_switch.pack(side="left", padx=(0, 20))

        self.audio_enabled_var = ctk.BooleanVar(value=True)
        self.audio_switch = ctk.CTkSwitch(self.toggles_frame, text="🔊 Глоб. звук", variable=self.audio_enabled_var, command=self.update_live_toggles, progress_color=ACCENT_CYAN)
        self.audio_switch.pack(side="left")

        self.control_var = ctk.BooleanVar(value=True)
        self.control_switch = ctk.CTkSwitch(
            self.frame_control, text="Разрешить зрителю управлять ПК", 
            font=ctk.CTkFont(weight="bold"), variable=self.control_var, command=self.update_live_toggles,
            progress_color=SUCCESS
        )
        self.control_switch.pack(pady=10, padx=15, anchor="w")

        self.apply_btn = ctk.CTkButton(
            self.frame_control, text="🔄 ПРИМЕНИТЬ (РЕСТАРТ ЯДРА)", height=38, 
            command=self.apply_hot_settings, state="disabled", 
            fg_color="#1E2532", text_color=TEXT_MUTED, font=ctk.CTkFont(weight="bold")
        )
        self.apply_btn.pack(pady=(0, 5), padx=15, fill="x")

        self.frame_audio = ctk.CTkFrame(self.right_pane, corner_radius=15, fg_color=PANEL_BG)
        self.frame_audio.pack(fill="x", pady=(0, 15), ipadx=10, ipady=10)
        
        ctk.CTkLabel(self.frame_audio, text="🎛️ МИКШЕР ПРИЛОЖЕНИЙ", font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT_MUTED).pack(anchor="w", padx=15, pady=(5, 5))
        
        self.scrollable_audio = ctk.CTkScrollableFrame(self.frame_audio, height=140, fg_color=INPUT_BG, corner_radius=10)
        self.scrollable_audio.pack(fill="x", padx=15, pady=(0, 5))

        self.status_frame = ctk.CTkFrame(self.right_pane, fg_color=INPUT_BG, border_width=1, border_color="#2A3441", corner_radius=15)
        self.status_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        ctk.CTkLabel(self.status_frame, text="КОД КОМНАТЫ", font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT_MUTED).pack(pady=(20, 0))
        
        self.code_label = ctk.CTkLabel(self.status_frame, text="----", font=ctk.CTkFont(family="Consolas", size=55, weight="bold"), text_color=SUCCESS)
        self.code_label.pack(expand=True)


        self.action_button = ctk.CTkButton(
            self.right_pane, text="ЗАПУСТИТЬ СТРИМ", height=60, corner_radius=15,
            font=ctk.CTkFont(size=18, weight="bold"), 
            fg_color=ACCENT_CYAN, hover_color=ACCENT_CYAN_HOVER, text_color="#000000",
            command=self.toggle_stream
        )
        self.action_button.pack(fill="x", side="bottom")

        self.config_state = {
            "active_audio_pids": [],
            "video_enabled": True,
            "audio_enabled": True,
            "allow_control": True
        }

        self.load_settings()
        self.refresh_audio_sources()

    def update_gamma_label(self, value):
        self.gamma_label.configure(text=f"Гамма: {value:.1f}")

    def refresh_audio_sources(self):
        try: processes = self.audio_scanner.get_audio_processes()
        except: processes = []

        current_pids = {}
        for p in processes:
            if p.startswith("[") and "]" in p:
                try:
                    pid = int(p.split("]")[0][1:])
                    name = p.split("] ")[1]
                    if pid != 0: current_pids[pid] = name
                except: pass

        for pid in list(self.audio_switches.keys()):
            if pid not in current_pids:
                self.audio_switches[pid].destroy()
                del self.audio_switches[pid]
                del self.audio_vars[pid]

        for pid, name in current_pids.items():
            if pid not in self.audio_switches:
                var = ctk.BooleanVar(value=False)
                switch = ctk.CTkSwitch(
                    self.scrollable_audio, 
                    text=f"{name} (PID: {pid})", 
                    variable=var, 
                    command=self.update_live_toggles,
                    progress_color=ACCENT_CYAN
                )
                switch.pack(anchor="w", pady=5, padx=5)
                self.audio_vars[pid] = var
                self.audio_switches[pid] = switch

        self.after(3000, self.refresh_audio_sources)

    def update_live_toggles(self):
        active_pids = [pid for pid, var in self.audio_vars.items() if var.get()]
        self.config_state["active_audio_pids"] = active_pids
        self.config_state["video_enabled"] = self.video_enabled_var.get()
        self.config_state["audio_enabled"] = self.audio_enabled_var.get()
        self.config_state["allow_control"] = self.control_var.get()

    def apply_hot_settings(self):
        if self.is_streaming and hasattr(self, 'restart_event'):
            self.config_state["monitor_idx"] = int(self.monitor_var.get().split(']')[0].replace('[', ''))
            self.config_state["width"] = int(self.res_var.get().split(' ')[0].split('x')[0])
            self.config_state["height"] = int(self.res_var.get().split(' ')[0].split('x')[1])
            self.config_state["preset"] = self.preset_var.get().lower().replace(" ", "_")
            self.config_state["resize_mode"] = {
                "Быстрый (Без нагрузки CPU)": "fast", 
                "Качественный (Нагрузка CPU)": "quality", 
                "Отключен (Оригинал)": "disabled"
            }[self.resize_var.get()]

            self.config_state["gamma"] = round(self.gamma_var.get(), 1)
            self.loop.call_soon_threadsafe(self.restart_event.set)

    def paste_server(self):
        try: self.server_var.set(self.clipboard_get().strip())
        except Exception: pass

    def load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    self.server_var.set(json.load(f).get("server_url", ""))
            except Exception: pass

    def save_settings(self, url):
        try:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump({"server_url": url}, f)
        except Exception: pass

    def format_server_url(self, url):
        url = url.strip()
        if url.startswith("https://"): url = url.replace("https://", "wss://", 1)
        elif url.startswith("http://"): url = url.replace("http://", "ws://", 1)
        if url.endswith("/"): url = url[:-1]
        if not url.endswith("/ws"): url += "/ws"
        return url

    def scan_monitors(self):
        try:
            monitors = get_monitors()
            return [f"[{i}] {m.width}x{m.height}{' [ОСНОВНОЙ]' if m.is_primary else ''}" for i, m in enumerate(monitors)]
        except Exception: return ["[0] Автоматический выбор"]

    def start_stream(self):
        raw_url = self.server_var.get().strip()
        if not raw_url: return
        server_url = self.format_server_url(raw_url)
        self.server_var.set(server_url) 
        self.save_settings(server_url)

        self.is_streaming = True
        self.server_entry.configure(state="disabled")
        self.action_button.configure(text="🛑 ОСТАНОВИТЬ СТРИМ", fg_color=DANGER, hover_color=DANGER_HOVER, text_color="white")
        
        self.apply_btn.configure(state="normal", fg_color=ACCENT_PURPLE, hover_color=ACCENT_PURPLE_HOVER, text_color="white")
        self.status_frame.configure(border_color=ACCENT_PURPLE) 
        
        self.config_state["monitor_idx"] = int(self.monitor_var.get().split(']')[0].replace('[', ''))
        self.config_state["width"] = int(self.res_var.get().split(' ')[0].split('x')[0])
        self.config_state["height"] = int(self.res_var.get().split(' ')[0].split('x')[1])
        self.config_state["preset"] = self.preset_var.get().lower().replace(" ", "_")
        self.config_state["resize_mode"] = {
            "Быстрый (Без нагрузки CPU)": "fast", 
            "Качественный (Нагрузка CPU)": "quality", 
            "Отключен (Оригинал)": "disabled"
        }[self.resize_var.get()]
        self.config_state["gamma"] = round(self.gamma_var.get(), 1)
        self.stream_thread = threading.Thread(target=self.run_asyncio_loop, args=(server_url, self.config_state), daemon=True)
        self.stream_thread.start()

    def stop_stream(self):
        self.is_streaming = False
        self.server_entry.configure(state="normal")
        self.action_button.configure(text="ЗАПУСТИТЬ СТРИМ", fg_color=ACCENT_CYAN, hover_color=ACCENT_CYAN_HOVER, text_color="#000000")
        
        self.apply_btn.configure(state="disabled", fg_color="#1E2532", text_color=TEXT_MUTED)
        self.status_frame.configure(border_color="#2A3441")
        self.code_label.configure(text="----", text_color=SUCCESS)
        
        if hasattr(self, 'stop_event') and self.stop_event:
            self.loop.call_soon_threadsafe(self.stop_event.set)

    def update_ui_code(self, room_code):
        self.code_label.configure(text=room_code if room_code != "ERROR" else "ОШИБКА", text_color=SUCCESS if room_code != "ERROR" else DANGER)

    def toggle_stream(self):
        if not self.is_streaming: self.start_stream()
        else: self.stop_stream()

    def run_asyncio_loop(self, server_url, config_state):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.stop_event = asyncio.Event()
        self.restart_event = asyncio.Event()
        try:
            self.loop.run_until_complete(run_signaling(server_url, config_state, self.update_ui_code, self.stop_event, self.restart_event))
        except Exception as e: print(f"Ошибка WebRTC: {e}")
        finally:
            self.loop.close()
            asyncio.set_event_loop(None)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = StreamerApp()
    app.mainloop()