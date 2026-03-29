// input.js
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

// --- ЛОГИКА ТРЕКПАДА ДЛЯ ТЕЛЕФОНА ---
function initTouchpad() {
    let lastX = 0, lastY = 0;
    let isTap = false;

    UI.videoPlayer.addEventListener('touchstart', (e) => {
        if (e.touches.length === 1) {
            lastX = e.touches[0].clientX;
            lastY = e.touches[0].clientY;
            isTap = true; // Предполагаем, что это может быть тап
        } else if (e.touches.length === 2) {
            isTap = false;
            // Тап двумя пальцами = правый клик
            if (State.dataChannel && State.dataChannel.readyState === 'open') {
                State.dataChannel.send(JSON.stringify({ action: 'mousedown', button: 'right' }));
                setTimeout(() => State.dataChannel.send(JSON.stringify({ action: 'mouseup', button: 'right' })), 50);
            }
        }
    }, { passive: false });

    UI.videoPlayer.addEventListener('touchmove', (e) => {
        if (e.touches.length === 1) {
            e.preventDefault(); // Блокируем прокрутку страницы
            
            let dx = e.touches[0].clientX - lastX;
            let dy = e.touches[0].clientY - lastY;
            
            // Если палец сдвинулся больше чем на 3 пикселя, это уже не тап, а движение мыши
            if (Math.abs(dx) > 3 || Math.abs(dy) > 3) isTap = false;

            if (State.dataChannel && State.dataChannel.readyState === 'open') {
                State.dataChannel.send(JSON.stringify({ action: 'mouse_delta', dx: dx, dy: dy }));
            }

            lastX = e.touches[0].clientX;
            lastY = e.touches[0].clientY;
        }
    }, { passive: false });

    UI.videoPlayer.addEventListener('touchend', (e) => {
        if (isTap && e.changedTouches.length === 1) {
            // Если палец не двигался, это короткий тап = левый клик
            if (State.dataChannel && State.dataChannel.readyState === 'open') {
                State.dataChannel.send(JSON.stringify({ action: 'mousedown', button: 'left' }));
                setTimeout(() => State.dataChannel.send(JSON.stringify({ action: 'mouseup', button: 'left' })), 50);
            }
        }
    });
}

// --- ЛОГИКА МОБИЛЬНОЙ КЛАВИАТУРЫ ---
function initMobileKeyboard() {
    // Ловим реальные символы (решает проблему Т9 на Android)
    UI.mobileInput.addEventListener('input', (e) => {
        const char = e.data; // Получаем введенный символ
        if (char && State.dataChannel && State.dataChannel.readyState === 'open') {
            State.dataChannel.send(JSON.stringify({ action: 'keydown', key: char, code: 'Key' + char.toUpperCase() }));
            setTimeout(() => {
                State.dataChannel.send(JSON.stringify({ action: 'keyup', key: char, code: 'Key' + char.toUpperCase() }));
            }, 20);
        }
        UI.mobileInput.value = ''; // Сразу очищаем, чтобы поле не переполнялось
    });

    // Ловим спец. клавиши (Backspace, Enter), которые могут не попадать в 'input'
    UI.mobileInput.addEventListener('keydown', (e) => {
        if (e.key === 'Backspace' || e.key === 'Enter') {
            handleKey(e, 'keydown');
        }
    });
    
    UI.mobileInput.addEventListener('keyup', (e) => {
        if (e.key === 'Backspace' || e.key === 'Enter') {
            handleKey(e, 'keyup');
        }
    });
}

export function initInputListeners() {
    if (State.isMobile) {
        initTouchpad();
        initMobileKeyboard();
        // На мобилках скрываем кнопку игрового режима (она там не нужна, мышь залочить нельзя)
        UI.btnGameMode.style.display = 'none';
    } else {
        // --- СТАНДАРТНАЯ ЛОГИКА ДЛЯ ПК ---
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
    }

    // Слушатели реальной клавиатуры (для ПК или подключенных Bluetooth-клавиатур)
    window.addEventListener('keydown', (e) => {
        if (e.target !== UI.mobileInput) handleKey(e, 'keydown');
    });
    window.addEventListener('keyup', (e) => {
        if (e.target !== UI.mobileInput) handleKey(e, 'keyup');
    });
}