// Process-specific audio capture DLL
// Original wrapper by tsubome: https://github.com/tsubome/ProcessAudioCapture
// Based on Microsoft ApplicationLoopback Sample
// 
// Modified for real-time PCM byte streaming via callbacks.
#pragma once

#include <Windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <audioclientactivationparams.h>
#include <mfapi.h>
#include <atomic>
#include <string>
#include <functional>

// Callback function type
using LevelCallback = std::function<void(float levelDb)>;
using DataCallback = std::function<void(const BYTE* data, UINT32 numBytes)>; // <-- ДОБАВИТЬ

// Async activation completion handler with Free Threaded Marshaler support
class CLoopbackCapture : public IActivateAudioInterfaceCompletionHandler
{
public:
    CLoopbackCapture();
    ~CLoopbackCapture();

    // Initialize FTM (must call before using)
    HRESULT Initialize();

    // IUnknown
    STDMETHOD(QueryInterface)(REFIID riid, void** ppvObject) override;
    STDMETHOD_(ULONG, AddRef)() override;
    STDMETHOD_(ULONG, Release)() override;

    // IActivateAudioInterfaceCompletionHandler
    STDMETHOD(ActivateCompleted)(IActivateAudioInterfaceAsyncOperation* operation) override;

    // Start capture
    HRESULT StartCapture(
        DWORD processId,
        bool includeProcessTree,
        const wchar_t* outputPath,
        LevelCallback callback,
        DataCallback dataCallback
    );

    // Stop capture
    HRESULT StopCapture();

    // Pause/Resume capture
    HRESULT PauseCapture();
    HRESULT ResumeCapture();
    bool IsPaused() const { return m_isPaused; }

    // State getters
    bool IsCapturing() const { return m_isCapturing; }
    float GetCurrentLevel() const { return m_currentLevelDb; }
    std::wstring GetLastErrorMsg() const { return m_lastError; }

private:
    // Capture thread
    static DWORD WINAPI CaptureThreadProc(LPVOID param);
    DWORD CaptureThread();

    // WAV file writing
    HRESULT WriteWavHeader();
    HRESULT WriteWavData(BYTE* data, UINT32 numFrames);
    HRESULT FinalizeWavFile();

    // Level calculation
    float CalculateLevelDb(BYTE* data, UINT32 numFrames);

    // Reference count
    std::atomic<ULONG> m_refCount{ 1 };

    // Free Threaded Marshaler for cross-apartment calls
    IUnknown* m_ftm{ nullptr };

    // State
    std::atomic<bool> m_isCapturing{ false };
    std::atomic<bool> m_isPaused{ false };
    std::atomic<float> m_currentLevelDb{ -60.0f };
    std::wstring m_lastError;

    // Events
    HANDLE m_activationCompleteEvent{ nullptr };
    HANDLE m_captureStopEvent{ nullptr };
    HANDLE m_captureThread{ nullptr };

    // Audio interfaces
    IAudioClient* m_audioClient{ nullptr };
    IAudioCaptureClient* m_captureClient{ nullptr };
    WAVEFORMATEX* m_waveFormat{ nullptr };
    UINT32 m_bufferFrameCount{ 0 };

    // File output
    HANDLE m_outputFile{ INVALID_HANDLE_VALUE };
    std::wstring m_outputPath;
    DWORD m_dataChunkPos{ 0 };
    DWORD m_totalBytesWritten{ 0 };

    // Callback
    LevelCallback m_levelCallback;
    DataCallback m_dataCallback;

    // Activation result
    HRESULT m_activationResult{ E_FAIL };

    // Activation thread parameters
    DWORD m_targetProcessId{ 0 };
    bool m_includeProcessTree{ true };

    // Activation thread
    static DWORD WINAPI ActivationThreadProc(LPVOID param);
    DWORD ActivationThread();
};
