import { State } from './state.js';
import { UI, updateRemoteCursor } from './ui.js';

export function sendControlData(action, clientX, clientY, button = 'left') {
    if (!State.dataChannel || State.dataChannel.readyState !== 'open') return;
    
    const rect = UI.videoPlayer.getBoundingClientRect();
    const videoRatio = UI.videoPlayer.videoWidth / UI.videoPlayer.videoHeight;
    const elementRatio = rect.width / rect.height;
    let actualWidth = rect.width, actualHeight = rect.height, startX = 0, startY = 0;

    if (elementRatio > videoRatio) {
        actualWidth = actualHeight * videoRatio;
        startX = (rect.width - actualWidth) / 2;
    } else {
        actualHeight = actualWidth / videoRatio;
        startY = (rect.height - actualHeight) / 2;
    }

    let x = (clientX - rect.left - startX) / actualWidth;
    let y = (clientY - rect.top - startY) / actualHeight;

    if (x < 0 || x > 1 || y < 0 || y > 1) return;
    
    if (action === 'mousemove' && !State.isGameMode) updateRemoteCursor(x, y);
    State.dataChannel.send(JSON.stringify({ action: action, x: x, y: y, button: button }));
}

function handleKey(e, actionType) {
    if (!State.dataChannel || State.dataChannel.readyState !== 'open') return;
    if (['F5', 'F12'].includes(e.key)) return; 
    if (e.key !== 'Escape') e.preventDefault(); 
    State.dataChannel.send(JSON.stringify({ action: actionType, key: e.key, code: e.code }));
}

export function initInputListeners() {
    document.addEventListener('pointerlockchange', () => {
        if (document.pointerLockElement === UI.videoPlayer) {
            State.isGameMode = true;
            UI.btnGameMode.classList.add('active');
            UI.remoteCursor.style.display = 'none';
        } else {
            State.isGameMode = false;
            UI.btnGameMode.classList.remove('active');
        }
    });

    UI.videoPlayer.addEventListener('dblclick', () => {
        if (!document.fullscreenElement) UI.playerContainer.requestFullscreen();
        else document.exitFullscreen();
    });
    
    UI.videoPlayer.addEventListener('contextmenu', e => e.preventDefault());

    document.addEventListener('mousedown', (e) => {
        if (State.isGameMode && State.dataChannel && State.dataChannel.readyState === 'open') {
            State.dataChannel.send(JSON.stringify({ action: 'mousedown', button: {0:'left', 1:'middle', 2:'right'}[e.button] }));
        } else if (e.target === UI.videoPlayer || e.target === UI.playOverlay) {
            sendControlData('mousedown', e.clientX, e.clientY, {0:'left', 1:'middle', 2:'right'}[e.button]);
        }
    });

    document.addEventListener('mouseup', (e) => {
        if (State.isGameMode && State.dataChannel && State.dataChannel.readyState === 'open') {
            State.dataChannel.send(JSON.stringify({ action: 'mouseup', button: {0:'left', 1:'middle', 2:'right'}[e.button] }));
        } else if (e.target === UI.videoPlayer || e.target === UI.playOverlay) {
            sendControlData('mouseup', e.clientX, e.clientY, {0:'left', 1:'middle', 2:'right'}[e.button]);
        }
    });
    
    let lastMoveTime = 0;
    document.addEventListener('mousemove', (e) => {
        if (State.isGameMode) {
            if (State.dataChannel && State.dataChannel.readyState === 'open' && (e.movementX !== 0 || e.movementY !== 0)) {
                State.dataChannel.send(JSON.stringify({ action: 'mouse_delta', dx: e.movementX, dy: e.movementY }));
            }
        } else {
            let now = Date.now();
            if (now - lastMoveTime > 30) {
                if (e.target === UI.videoPlayer || e.target === UI.playOverlay) sendControlData('mousemove', e.clientX, e.clientY, 'none');
                lastMoveTime = now;
            }
        }
    });

    window.addEventListener('keydown', (e) => handleKey(e, 'keydown'));
    window.addEventListener('keyup', (e) => handleKey(e, 'keyup'));
}