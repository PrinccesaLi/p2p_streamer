import { UI, forcePlay, toggleGameMode, toggleFullscreen, showMobileKeyboard } from './ui.js';
import { connectWS, startWatchdog } from './network.js';
import { initInputListeners } from './input.js';

// Прокидываем функции в глобальный объект window, 
// чтобы атрибуты onclick в HTML могли их найти
window.forcePlay = forcePlay;
window.toggleGameMode = toggleGameMode;
window.toggleFullscreen = toggleFullscreen;
window.showMobileKeyboard = showMobileKeyboard;
window.joinStream = () => {
    const code = UI.roomCodeInput.value;
    if (code.length < 4) return alert("Введите 4 цифры");
    connectWS(code);
};

// Выполняется после полной загрузки страницы
window.onload = () => {
    initInputListeners();
    startWatchdog();
    
    // Проверка кода в URL (авто-вход)
    const pathCode = window.location.pathname.replace('/', '');
    if (pathCode.length >= 4 && !isNaN(pathCode)) {
        UI.roomCodeInput.value = pathCode;
        window.joinStream();
    }
};

window.sendEsc = () => {
    if (State.dataChannel) {
        State.dataChannel.send(JSON.stringify({ action: 'keydown', key: 'Escape', code: 'Escape' }));
        setTimeout(() => {
            State.dataChannel.send(JSON.stringify({ action: 'keyup', key: 'Escape', code: 'Escape' }));
        }, 50);
    }
};