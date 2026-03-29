import { State } from './state.js';
import { UI, updateRemoteCursor } from './ui.js';

export function requestRestart() {
    if (State.gracePeriod > 0) return; 
    
    State.isStreamActive = false; 
    State.gracePeriod = 10; 
    State.freezeCounter = 0;
    
    if (State.ws && State.ws.readyState === WebSocket.OPEN) {
        State.ws.send(JSON.stringify({ action: "request_restart", code: State.currentCode }));
        UI.loginBox.style.display = 'block';
        UI.playerContainer.style.display = 'none';
        UI.statusEl.innerText = "Попытка восстановления потока...";
        UI.statusEl.style.color = "#ffaa00";
    } else {
        connectWS(State.currentCode);
    }
}

export function initPC() {
    if (State.pc) State.pc.close();
    State.pc = new RTCPeerConnection({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] });

    State.pc.ondatachannel = (event) => {
        State.dataChannel = event.channel;
        State.dataChannel.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                if (data.action === 'cursor' && !State.isGameMode) {
                    updateRemoteCursor(data.x, data.y);
                } else if (data.action === 'init_preset') {
                    State.streamPreset = data.preset;
                    State.pc.getReceivers().forEach(receiver => {
                        if ('playoutDelayHint' in receiver) {
                            if (data.preset === "super_duper") receiver.playoutDelayHint = 2.0;
                            else if (data.preset === "super_quality") receiver.playoutDelayHint = 1.0;
                            else receiver.playoutDelayHint = 0.0;
                        }
                    });
                }
            } catch (err) {}
        };
    };

    State.pc.ontrack = (event) => {
        UI.loginBox.style.display = 'none';
        UI.playerContainer.style.display = 'flex';
        UI.videoPlayer.focus(); 
        
        const newStream = event.streams[0];
        if (UI.videoPlayer.srcObject !== newStream) {
            UI.videoPlayer.srcObject = null; 
            UI.videoPlayer.srcObject = newStream;
            
            let playPromise = UI.videoPlayer.play();
            if (playPromise !== undefined) {
                playPromise.then(() => {
                    UI.playOverlay.style.display = 'none';
                    State.isStreamActive = true;
                    State.gracePeriod = 5;
                    State.freezeCounter = 0;
                }).catch(error => {
                    console.log("Auto-play blocked:", error);
                    UI.playOverlay.style.display = 'flex';
                    State.isStreamActive = false; 
                });
            }
        }
    };
}

export function connectWS(code) {
    State.currentCode = code;
    UI.statusEl.innerText = "Подключение к серверу...";
    UI.statusEl.style.color = "#ffaa00";
    
    window.history.pushState({}, '', '/' + code);

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    State.ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws`);
    
    State.ws.onopen = () => {
        State.ws.send(JSON.stringify({ action: "join", code: code }));
        
        setInterval(() => {
            if (State.ws.readyState === WebSocket.OPEN) {
                State.ws.send(JSON.stringify({ action: "ping" }));
            }
        }, 30000);
    };

    State.ws.onclose = () => {
        if (State.isStreamActive || UI.playOverlay.style.display === 'flex') {
            UI.statusEl.innerText = "Переподключение к серверу...";
            setTimeout(() => connectWS(State.currentCode), 2000);
        }
    };

    State.ws.onerror = () => State.ws.close();

    State.ws.onmessage = async (event) => {
        const msg = JSON.parse(event.data);
        if (msg.action === "error") {
            UI.statusEl.innerText = msg.message;
            UI.statusEl.style.color = "#ff0000";
        }
        if (msg.action === "offer") {
            State.streamPreset = msg.preset;
            initPC(); 
            
            UI.statusEl.innerText = "Установка P2P соединения...";
            await State.pc.setRemoteDescription(new RTCSessionDescription(msg.data));
            const answer = await State.pc.createAnswer();
            await State.pc.setLocalDescription(answer);
            
            setTimeout(() => {
                if(State.ws.readyState === WebSocket.OPEN) {
                    State.ws.send(JSON.stringify({ 
                        action: "answer", 
                        code: State.currentCode, 
                        data: { type: State.pc.localDescription.type, sdp: State.pc.localDescription.sdp } 
                    }));
                    UI.statusEl.innerText = "Видео загружается...";
                }
            }, 1000); 
        }
    };
}

export function startWatchdog() {
    UI.videoPlayer.addEventListener('playing', () => {
        State.gracePeriod = 5; 
        console.log("▶️ Видеопоток успешно пошел!");
    });
    
    setInterval(async () => {
        // 1. Обновляем пинг (зеленая лампочка)
        if (State.pc && State.pc.connectionState === 'connected') {
            const stats = await State.pc.getStats();
            stats.forEach(report => {
                if (report.type === 'candidate-pair' && report.state === 'succeeded') {
                    const ping = (report.currentRoundTripTime * 1000).toFixed(0);
                    if (!isNaN(ping)) {
                        UI.pingText.innerText = `${ping} ms`;
                        UI.pingDot.style.background = ping < 50 ? '#00ff00' : (ping < 100 ? '#ffaa00' : '#ff0000');
                        UI.pingDot.style.boxShadow = `0 0 5px ${UI.pingDot.style.background}`;
                    }
                }
            });
        }

        if (!State.isStreamActive || !State.pc) return;

        if (State.gracePeriod > 0) {
            State.gracePeriod--;
            return;
        }
        if (State.pc.connectionState === 'failed' || State.pc.connectionState === 'disconnected' || State.pc.connectionState === 'closed') {
            console.log("⚠️ Соединение разорвано на уровне сети. Требую рестарт...");
            requestRestart();
        }
    }, 1000);
}