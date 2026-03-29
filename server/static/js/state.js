// state.js
export const State = {
    ws: null,
    pc: null,
    dataChannel: null,
    isStreamActive: false,
    isGameMode: false,
    isMobile: 'ontouchstart' in window || navigator.maxTouchPoints > 0,
    currentCode: "",
    gracePeriod: 10,
    freezeCounter: 0,
    lastVideoTime: -1,
    streamPreset: "balance"
};