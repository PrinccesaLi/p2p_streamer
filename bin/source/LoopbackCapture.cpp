// Process-specific audio capture DLL
// Original wrapper by tsubome: https://github.com/tsubome/ProcessAudioCapture
// Based on Microsoft ApplicationLoopback Sample
// 
// Modified for real-time PCM byte streaming via callbacks.
#ifndef NOMINMAX
#define NOMINMAX
#endif

#include <algorithm>
#include "LoopbackCapture.h"
#include <functiondiscoverykeys_devpkey.h>
#include <propvarutil.h>
#include <objidl.h>
#include <ks.h>
#include <ksmedia.h>
#include <cmath>
#include <algorithm>
#include <vector>

#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "mfplat.lib")
#pragma comment(lib, "propsys.lib")

// Virtual audio device ID for process loopback
static constexpr PCWSTR PROCESS_LOOPBACK_DEVICE_ID = L"VAD\\Process_Loopback";

CLoopbackCapture::CLoopbackCapture()
{
    m_activationCompleteEvent = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    m_captureStopEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
}

CLoopbackCapture::~CLoopbackCapture()
{
    StopCapture();

    if (m_ftm)
    {
        m_ftm->Release();
        m_ftm = nullptr;
    }
    if (m_activationCompleteEvent)
    {
        CloseHandle(m_activationCompleteEvent);
    }
    if (m_captureStopEvent)
    {
        CloseHandle(m_captureStopEvent);
    }
}

HRESULT CLoopbackCapture::Initialize()
{
    // Create Free Threaded Marshaler for cross-apartment callback support
    return CoCreateFreeThreadedMarshaler(
        static_cast<IActivateAudioInterfaceCompletionHandler*>(this),
        &m_ftm
    );
}

// IUnknown implementation
STDMETHODIMP CLoopbackCapture::QueryInterface(REFIID riid, void** ppvObject)
{
    if (riid == IID_IUnknown || riid == __uuidof(IActivateAudioInterfaceCompletionHandler))
    {
        *ppvObject = static_cast<IActivateAudioInterfaceCompletionHandler*>(this);
        AddRef();
        return S_OK;
    }

    // Support IAgileObject for free-threaded marshaling (required by ActivateAudioInterfaceAsync)
    if (riid == __uuidof(IAgileObject))
    {
        *ppvObject = static_cast<IActivateAudioInterfaceCompletionHandler*>(this);
        AddRef();
        return S_OK;
    }

    // Forward IMarshal requests to the Free Threaded Marshaler
    if (riid == IID_IMarshal && m_ftm)
    {
        return m_ftm->QueryInterface(riid, ppvObject);
    }

    *ppvObject = nullptr;
    return E_NOINTERFACE;
}

STDMETHODIMP_(ULONG) CLoopbackCapture::AddRef()
{
    return ++m_refCount;
}

STDMETHODIMP_(ULONG) CLoopbackCapture::Release()
{
    ULONG count = --m_refCount;
    if (count == 0)
    {
        delete this;
    }
    return count;
}

// IActivateAudioInterfaceCompletionHandler implementation
STDMETHODIMP CLoopbackCapture::ActivateCompleted(IActivateAudioInterfaceAsyncOperation* operation)
{
    HRESULT hrActivateResult = E_UNEXPECTED;
    IUnknown* punkAudioInterface = nullptr;

    // Get activation result
    HRESULT hr = operation->GetActivateResult(&hrActivateResult, &punkAudioInterface);
    if (SUCCEEDED(hr) && SUCCEEDED(hrActivateResult))
    {
        // Get IAudioClient
        hr = punkAudioInterface->QueryInterface(IID_PPV_ARGS(&m_audioClient));
        if (SUCCEEDED(hr))
        {
            // Get audio format
            hr = m_audioClient->GetMixFormat(&m_waveFormat);
            if (FAILED(hr))
            {
                // GetMixFormat returns E_NOTIMPL for process loopback
                // Use system default format: 48kHz, 32bit float, 2ch
                m_waveFormat = (WAVEFORMATEX*)CoTaskMemAlloc(sizeof(WAVEFORMATEXTENSIBLE));
                if (m_waveFormat)
                {
                    WAVEFORMATEXTENSIBLE* wfext = (WAVEFORMATEXTENSIBLE*)m_waveFormat;
                    wfext->Format.wFormatTag = WAVE_FORMAT_EXTENSIBLE;
                    wfext->Format.nChannels = 2;
                    wfext->Format.nSamplesPerSec = 48000;
                    wfext->Format.wBitsPerSample = 32;
                    wfext->Format.nBlockAlign = wfext->Format.nChannels * wfext->Format.wBitsPerSample / 8;
                    wfext->Format.nAvgBytesPerSec = wfext->Format.nSamplesPerSec * wfext->Format.nBlockAlign;
                    wfext->Format.cbSize = sizeof(WAVEFORMATEXTENSIBLE) - sizeof(WAVEFORMATEX);
                    wfext->Samples.wValidBitsPerSample = 32;
                    wfext->dwChannelMask = SPEAKER_FRONT_LEFT | SPEAKER_FRONT_RIGHT;
                    wfext->SubFormat = KSDATAFORMAT_SUBTYPE_IEEE_FLOAT;
                    hr = S_OK;
                }
                else
                {
                    hr = E_OUTOFMEMORY;
                }
            }

            if (SUCCEEDED(hr))
            {
                // Initialize audio client
                hr = m_audioClient->Initialize(
                    AUDCLNT_SHAREMODE_SHARED,
                    AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_EVENTCALLBACK,
                    0,  // Buffer size (0 = default)
                    0,  // Period
                    m_waveFormat,
                    nullptr
                );
            }

            if (SUCCEEDED(hr))
            {
                // Get buffer size
                hr = m_audioClient->GetBufferSize(&m_bufferFrameCount);
            }

            if (SUCCEEDED(hr))
            {
                // Get capture client
                hr = m_audioClient->GetService(IID_PPV_ARGS(&m_captureClient));
            }
        }
    }
    else if (FAILED(hrActivateResult))
    {
        hr = hrActivateResult;
    }

    if (punkAudioInterface)
    {
        punkAudioInterface->Release();
    }

    m_activationResult = hr;
    SetEvent(m_activationCompleteEvent);
    return S_OK;
}

HRESULT CLoopbackCapture::StartCapture(
    DWORD processId,
    bool includeProcessTree,
    const wchar_t* outputPath,
    LevelCallback callback,
    DataCallback dataCallback)
{
    if (m_isCapturing)
    {
        m_lastError = L"Already capturing";
        return E_FAIL;
    }

    m_levelCallback = callback;
    m_dataCallback = dataCallback;

    if (outputPath)
    {
        m_outputPath = outputPath;
    }
    else
    {
        m_outputPath.clear();
    }

    // Store parameters for activation thread
    m_targetProcessId = processId;
    m_includeProcessTree = includeProcessTree;
    m_activationResult = E_FAIL;

    // Run activation on a separate MTA thread
    HANDLE hActivationThread = CreateThread(
        nullptr, 0, ActivationThreadProc, this, 0, nullptr);

    if (!hActivationThread)
    {
        m_lastError = L"Failed to create activation thread";
        return HRESULT_FROM_WIN32(::GetLastError());
    }

    // Wait for activation thread to complete
    WaitForSingleObject(hActivationThread, INFINITE);
    CloseHandle(hActivationThread);

    if (FAILED(m_activationResult))
    {
        wchar_t errBuf[256];
        swprintf_s(errBuf, L"Audio activation failed: 0x%08X", m_activationResult);
        m_lastError = errBuf;
        return m_activationResult;
    }

    // Create output file
    if (!m_outputPath.empty())
    {
        m_outputFile = CreateFileW(
            m_outputPath.c_str(),
            GENERIC_WRITE,
            0,
            nullptr,
            CREATE_ALWAYS,
            FILE_ATTRIBUTE_NORMAL,
            nullptr
        );

        if (m_outputFile == INVALID_HANDLE_VALUE)
        {
            DWORD err = ::GetLastError();
            m_lastError = L"Failed to create output file";
            return HRESULT_FROM_WIN32(err);
        }

        HRESULT hr = WriteWavHeader();
        if (FAILED(hr))
        {
            CloseHandle(m_outputFile);
            m_outputFile = INVALID_HANDLE_VALUE;
            m_lastError = L"Failed to write WAV header";
            return hr;
        }
    }

    // Reset stop event
    ResetEvent(m_captureStopEvent);

    // Start capture thread
    m_captureThread = CreateThread(
        nullptr,
        0,
        CaptureThreadProc,
        this,
        0,
        nullptr
    );

    if (!m_captureThread)
    {
        DWORD err = ::GetLastError();
        m_lastError = L"Failed to create capture thread";
        if (m_outputFile != INVALID_HANDLE_VALUE)
        {
            CloseHandle(m_outputFile);
            m_outputFile = INVALID_HANDLE_VALUE;
        }
        return HRESULT_FROM_WIN32(err);
    }

    m_isCapturing = true;
    return S_OK;
}

HRESULT CLoopbackCapture::PauseCapture()
{
    if (!m_isCapturing)
    {
        m_lastError = L"Not capturing";
        return E_FAIL;
    }
    m_isPaused = true;
    return S_OK;
}

HRESULT CLoopbackCapture::ResumeCapture()
{
    if (!m_isCapturing)
    {
        m_lastError = L"Not capturing";
        return E_FAIL;
    }
    m_isPaused = false;
    return S_OK;
}

HRESULT CLoopbackCapture::StopCapture()
{
    if (!m_isCapturing)
    {
        return S_OK;
    }

    // Set stop event
    SetEvent(m_captureStopEvent);

    // Wait for capture thread to finish
    if (m_captureThread)
    {
        WaitForSingleObject(m_captureThread, 5000);
        CloseHandle(m_captureThread);
        m_captureThread = nullptr;
    }

    // Finalize WAV file
    if (m_outputFile != INVALID_HANDLE_VALUE)
    {
        FinalizeWavFile();
        CloseHandle(m_outputFile);
        m_outputFile = INVALID_HANDLE_VALUE;
    }

    // Release resources
    if (m_captureClient)
    {
        m_captureClient->Release();
        m_captureClient = nullptr;
    }
    if (m_audioClient)
    {
        m_audioClient->Release();
        m_audioClient = nullptr;
    }
    if (m_waveFormat)
    {
        CoTaskMemFree(m_waveFormat);
        m_waveFormat = nullptr;
    }

    m_isCapturing = false;
    m_isPaused = false;
    m_totalBytesWritten = 0;
    m_currentLevelDb = -60.0f;

    return S_OK;
}

DWORD WINAPI CLoopbackCapture::CaptureThreadProc(LPVOID param)
{
    CLoopbackCapture* capture = static_cast<CLoopbackCapture*>(param);
    return capture->CaptureThread();
}

DWORD CLoopbackCapture::CaptureThread()
{
    // Initialize COM
    HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (FAILED(hr))
    {
        return 1;
    }

    // Start audio client
    hr = m_audioClient->Start();
    if (FAILED(hr))
    {
        CoUninitialize();
        return 1;
    }

    // Capture loop
    while (WaitForSingleObject(m_captureStopEvent, 10) == WAIT_TIMEOUT)
    {
        UINT32 packetLength = 0;
        hr = m_captureClient->GetNextPacketSize(&packetLength);
        if (FAILED(hr))
        {
            break;
        }

        while (packetLength > 0)
        {
            BYTE* data = nullptr;
            UINT32 numFrames = 0;
            DWORD flags = 0;

            hr = m_captureClient->GetBuffer(&data, &numFrames, &flags, nullptr, nullptr);
            if (FAILED(hr))
            {
                break;
            }

            if (numFrames > 0)
            {
                // Check pause state once
                bool isPaused = m_isPaused.load();

                // Calculate volume level
                if (!(flags & AUDCLNT_BUFFERFLAGS_SILENT))
                {
                    m_currentLevelDb = CalculateLevelDb(data, numFrames);

                    // Call callback (skip when paused)
                    if (m_levelCallback && !isPaused)
                    {
                        m_levelCallback(m_currentLevelDb);
                    }

                    // Write to file (skip when paused)
                    if (m_outputFile != INVALID_HANDLE_VALUE && !isPaused)
                    {
                        WriteWavData(data, numFrames);
                    }

                    // НОВОЕ: Отправляем байты звука в Python!
                    if (m_dataCallback && !isPaused)
                    {
                        m_dataCallback(data, numFrames * m_waveFormat->nBlockAlign);
                    }
                }
                else
                {
                    m_currentLevelDb = -60.0f;

                    DWORD bytesToWrite = numFrames * m_waveFormat->nBlockAlign;
                    std::vector<BYTE> silence(bytesToWrite, 0);

                    // Write silence to file (skip when paused)
                    if (m_outputFile != INVALID_HANDLE_VALUE && !isPaused)
                    {
                        DWORD bytesWritten = 0;
                        WriteFile(m_outputFile, silence.data(), bytesToWrite, &bytesWritten, nullptr);
                        m_totalBytesWritten += bytesWritten;
                    }

                    // НОВОЕ: Отправляем сгенерированную тишину в Python (чтобы WebRTC не рвал связь)
                    if (m_dataCallback && !isPaused)
                    {
                        m_dataCallback(silence.data(), bytesToWrite);
                    }
                }
            }

            hr = m_captureClient->ReleaseBuffer(numFrames);
            if (FAILED(hr))
            {
                break;
            }

            hr = m_captureClient->GetNextPacketSize(&packetLength);
            if (FAILED(hr))
            {
                break;
            }
        }
    }

    // Stop audio client
    m_audioClient->Stop();

    CoUninitialize();
    return 0;
}

float CLoopbackCapture::CalculateLevelDb(BYTE* data, UINT32 numFrames)
{
    if (!m_waveFormat || numFrames == 0)
    {
        return -60.0f;
    }

    UINT32 totalSamples = numFrames * m_waveFormat->nChannels;
    double sum = 0.0;

    // Check if format is float (WAVEFORMATEXTENSIBLE with IEEE_FLOAT)
    bool isFloat = false;
    if (m_waveFormat->wFormatTag == WAVE_FORMAT_IEEE_FLOAT)
    {
        isFloat = true;
    }
    else if (m_waveFormat->wFormatTag == WAVE_FORMAT_EXTENSIBLE)
    {
        WAVEFORMATEXTENSIBLE* wfext = (WAVEFORMATEXTENSIBLE*)m_waveFormat;
        if (IsEqualGUID(wfext->SubFormat, KSDATAFORMAT_SUBTYPE_IEEE_FLOAT))
        {
            isFloat = true;
        }
    }

    if (isFloat && m_waveFormat->wBitsPerSample == 32)
    {
        // 32-bit float: values are in range [-1.0, 1.0]
        float* samples = reinterpret_cast<float*>(data);
        for (UINT32 i = 0; i < totalSamples; i++)
        {
            double sample = static_cast<double>(samples[i]);
            sum += sample * sample;
        }
        double rms = std::sqrt(sum / totalSamples);
        if (rms < 0.000001)
        {
            return -60.0f;
        }
        float db = static_cast<float>(20.0 * std::log10(rms));
        return std::max(-60.0f, std::min(0.0f, db));
    }
    else
    {
        // 16-bit PCM
        int16_t* samples = reinterpret_cast<int16_t*>(data);
        for (UINT32 i = 0; i < totalSamples; i++)
        {
            double sample = static_cast<double>(samples[i]);
            sum += sample * sample;
        }
        double rms = std::sqrt(sum / totalSamples);
        if (rms < 1.0)
        {
            return -60.0f;
        }
        float db = static_cast<float>(20.0 * std::log10(rms / 32767.0));
        return std::max(-60.0f, std::min(0.0f, db));
    }
}

HRESULT CLoopbackCapture::WriteWavHeader()
{
    DWORD bytesWritten = 0;
    DWORD placeholder = 0;

    // Calculate fmt chunk size
    DWORD fmtSize = sizeof(WAVEFORMATEX) + m_waveFormat->cbSize;

    // "RIFF"
    WriteFile(m_outputFile, "RIFF", 4, &bytesWritten, nullptr);

    // File size (updated later)
    WriteFile(m_outputFile, &placeholder, 4, &bytesWritten, nullptr);

    // "WAVE"
    WriteFile(m_outputFile, "WAVE", 4, &bytesWritten, nullptr);

    // "fmt "
    WriteFile(m_outputFile, "fmt ", 4, &bytesWritten, nullptr);

    // fmt chunk size (18 for WAVEFORMATEX, 40 for WAVEFORMATEXTENSIBLE)
    WriteFile(m_outputFile, &fmtSize, 4, &bytesWritten, nullptr);

    // Write WAVEFORMATEX + extension
    WriteFile(m_outputFile, m_waveFormat, fmtSize, &bytesWritten, nullptr);

    // "data"
    WriteFile(m_outputFile, "data", 4, &bytesWritten, nullptr);

    // Record data chunk position
    m_dataChunkPos = SetFilePointer(m_outputFile, 0, nullptr, FILE_CURRENT);

    // Data size (updated later)
    WriteFile(m_outputFile, &placeholder, 4, &bytesWritten, nullptr);

    return S_OK;
}

HRESULT CLoopbackCapture::WriteWavData(BYTE* data, UINT32 numFrames)
{
    DWORD bytesToWrite = numFrames * m_waveFormat->nBlockAlign;
    DWORD bytesWritten = 0;

    if (WriteFile(m_outputFile, data, bytesToWrite, &bytesWritten, nullptr))
    {
        m_totalBytesWritten += bytesWritten;
        return S_OK;
    }
    DWORD err = ::GetLastError();
    return HRESULT_FROM_WIN32(err);
}

HRESULT CLoopbackCapture::FinalizeWavFile()
{
    // Update RIFF file size (total file size - 8)
    // Header size = m_dataChunkPos + 4 (for data size field)
    DWORD fileSize = m_dataChunkPos + 4 + m_totalBytesWritten - 8;
    SetFilePointer(m_outputFile, 4, nullptr, FILE_BEGIN);
    DWORD bytesWritten = 0;
    WriteFile(m_outputFile, &fileSize, 4, &bytesWritten, nullptr);

    // Update data chunk size
    SetFilePointer(m_outputFile, m_dataChunkPos, nullptr, FILE_BEGIN);
    WriteFile(m_outputFile, &m_totalBytesWritten, 4, &bytesWritten, nullptr);

    return S_OK;
}

DWORD WINAPI CLoopbackCapture::ActivationThreadProc(LPVOID param)
{
    CLoopbackCapture* capture = static_cast<CLoopbackCapture*>(param);
    return capture->ActivationThread();
}

DWORD CLoopbackCapture::ActivationThread()
{
    // Initialize COM as MTA (required for ActivateAudioInterfaceAsync)
    HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (FAILED(hr) && hr != RPC_E_CHANGED_MODE)
    {
        m_activationResult = hr;
        SetEvent(m_activationCompleteEvent);
        return 1;
    }

    // Initialize Media Foundation
    hr = MFStartup(MF_VERSION, MFSTARTUP_LITE);
    if (FAILED(hr))
    {
        m_activationResult = hr;
        SetEvent(m_activationCompleteEvent);
        CoUninitialize();
        return 1;
    }

    // Set up process loopback parameters
    AUDIOCLIENT_ACTIVATION_PARAMS audioclientActivationParams = {};
    audioclientActivationParams.ActivationType = AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK;
    audioclientActivationParams.ProcessLoopbackParams.ProcessLoopbackMode =
        m_includeProcessTree ? PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE
                             : PROCESS_LOOPBACK_MODE_EXCLUDE_TARGET_PROCESS_TREE;
    audioclientActivationParams.ProcessLoopbackParams.TargetProcessId = m_targetProcessId;

    PROPVARIANT activateParams = {};
    activateParams.vt = VT_BLOB;
    activateParams.blob.cbSize = sizeof(audioclientActivationParams);
    activateParams.blob.pBlobData = (BYTE*)&audioclientActivationParams;

    // Reset completion event before async call
    ResetEvent(m_activationCompleteEvent);

    // AddRef before passing to async operation
    AddRef();

    // Activate audio interface asynchronously
    IActivateAudioInterfaceAsyncOperation* asyncOp = nullptr;
    hr = ActivateAudioInterfaceAsync(
        VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK,
        __uuidof(IAudioClient),
        &activateParams,
        this,
        &asyncOp
    );

    if (FAILED(hr))
    {
        Release(); // Balance the AddRef
        m_activationResult = hr;
        SetEvent(m_activationCompleteEvent);
        MFShutdown();
        CoUninitialize();
        return 1;
    }

    // Wait for activation to complete (ActivateCompleted callback will signal)
    WaitForSingleObject(m_activationCompleteEvent, INFINITE);

    if (asyncOp)
    {
        asyncOp->Release();
    }

    MFShutdown();
    CoUninitialize();
    return 0;
}
