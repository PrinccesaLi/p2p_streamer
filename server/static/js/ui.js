import { State } from './state.js';

export const UI = {
    statusEl: document.getElementById('status'),
    loginBox: document.getElementById('login-box'),
    playerContainer: document.getElementById('player-container'),
    videoPlayer: document.getElementById('video-player'),
    remoteCursor: document.getElementById('remote-cursor'),
    pingText: document.getElementById('ping-text'),
    pingDot: document.getElementById('ping-dot'),
    mobileInput: document.getElementById('mobile-keyboard-input'),
    btnGameMode: document.getElementById('btn-gamemode'),
    playOverlay: document.getElementById('play-overlay'),
    roomCodeInput: document.getElementById('room-code')
};

export function updateRemoteCursor(x, y) {
    if (!UI.videoPlayer.videoWidth || State.isGameMode) return;
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

    const pixelX = rect.left + startX + (x * actualWidth);
    const pixelY = rect.top + startY + (y * actualHeight);

    UI.remoteCursor.style.display = 'block';
    UI.remoteCursor.style.transform = `translate(${pixelX}px, ${pixelY}px)`;
}

export function forcePlay() {
    UI.videoPlayer.play();
    UI.playOverlay.style.display = 'none';
    State.isStreamActive = true;
    State.gracePeriod = 5;
    State.freezeCounter = 0;
}

export function toggleGameMode() {
    if (!document.pointerLockElement) {
        let promise = UI.videoPlayer.requestPointerLock({ unadjustedMovement: true });
        if (promise) promise.catch(err => UI.videoPlayer.requestPointerLock());
    } else {
        document.exitPointerLock();
    }
}

export function toggleFullscreen() {
    if (!document.fullscreenElement) UI.playerContainer.requestFullscreen();
    else document.exitFullscreen();
}

export function showMobileKeyboard() { 
    UI.mobileInput.focus(); 
}