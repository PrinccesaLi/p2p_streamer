// Process-specific audio capture DLL
// Original wrapper by tsubome: https://github.com/tsubome/ProcessAudioCapture
// Based on Microsoft ApplicationLoopback Sample
// 
// Modified for real-time PCM byte streaming via callbacks.
#ifndef NOMINMAX
#define NOMINMAX
#endif

#define PROCESSAUDIOCAPTURE_EXPORTS
#include "ProcessAudioCapture.h"
#include "LoopbackCapture.h"

#include <Windows.h>
#include <VersionHelpers.h>
#include <Psapi.h>
#include <mmdeviceapi.h>
#include <audiopolicy.h>
#include <vector>
#include <string>
#include <mutex>

#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "Psapi.lib")

// Global variables
static wchar_t g_lastError[512] = { 0 };
static std::mutex g_mutex;
static const char* VERSION = "1.0.0";

// DLL entry point
// Note: Do NOT call CoInitialize in DllMain (loader lock issues)
BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved)
{
    (void)hModule;
    (void)lpReserved;
    switch (ul_reason_for_call)
    {
    case DLL_PROCESS_ATTACH:
    case DLL_PROCESS_DETACH:
    case DLL_THREAD_ATTACH:
    case DLL_THREAD_DETACH:
        break;
    }
    return TRUE;
}

// Check if Windows 10 Build 19041 (2004) or later
PAC_API BOOL PacIsSupported(void)
{
    // Use RtlGetVersion directly (not affected by manifest)
    OSVERSIONINFOEXW osvi = { sizeof(osvi) };
    typedef LONG(WINAPI* RtlGetVersionPtr)(PRTL_OSVERSIONINFOW);
    HMODULE hNtdll = GetModuleHandleW(L"ntdll.dll");
    if (hNtdll)
    {
        RtlGetVersionPtr pRtlGetVersion = (RtlGetVersionPtr)GetProcAddress(hNtdll, "RtlGetVersion");
        if (pRtlGetVersion)
        {
            pRtlGetVersion((PRTL_OSVERSIONINFOW)&osvi);
            // Check Windows 10+ (major version 10) and Build 19041+
            if (osvi.dwMajorVersion >= 10 && osvi.dwBuildNumber >= 19041)
            {
                return TRUE;
            }
        }
    }

    return FALSE;
}

// Get list of processes outputting audio
PAC_API PacErrorCode PacEnumerateAudioProcesses(
    PacProcessInfo* processes,
    int maxCount,
    int* actualCount)
{
    if (!processes || !actualCount || maxCount <= 0)
    {
        wcscpy_s(g_lastError, L"Invalid parameters");
        return PAC_ERROR_INVALID_PARAM;
    }

    *actualCount = 0;

    // Initialize COM
    HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    bool needUninit = SUCCEEDED(hr);

    // Get device enumerator
    IMMDeviceEnumerator* pEnumerator = nullptr;
    hr = CoCreateInstance(
        __uuidof(MMDeviceEnumerator),
        nullptr,
        CLSCTX_ALL,
        __uuidof(IMMDeviceEnumerator),
        (void**)&pEnumerator
    );

    if (FAILED(hr))
    {
        wcscpy_s(g_lastError, L"Failed to create device enumerator");
        if (needUninit) CoUninitialize();
        return PAC_ERROR_AUDIO_INIT_FAILED;
    }

    // Get default output device
    IMMDevice* pDevice = nullptr;
    hr = pEnumerator->GetDefaultAudioEndpoint(eRender, eConsole, &pDevice);
    if (FAILED(hr))
    {
        pEnumerator->Release();
        wcscpy_s(g_lastError, L"Failed to get default audio endpoint");
        if (needUninit) CoUninitialize();
        return PAC_ERROR_AUDIO_INIT_FAILED;
    }

    // Get session manager
    IAudioSessionManager2* pSessionManager = nullptr;
    hr = pDevice->Activate(__uuidof(IAudioSessionManager2), CLSCTX_ALL, nullptr, (void**)&pSessionManager);
    if (FAILED(hr))
    {
        pDevice->Release();
        pEnumerator->Release();
        wcscpy_s(g_lastError, L"Failed to activate session manager");
        if (needUninit) CoUninitialize();
        return PAC_ERROR_AUDIO_INIT_FAILED;
    }

    // Get session enumerator
    IAudioSessionEnumerator* pSessionList = nullptr;
    hr = pSessionManager->GetSessionEnumerator(&pSessionList);
    if (FAILED(hr))
    {
        pSessionManager->Release();
        pDevice->Release();
        pEnumerator->Release();
        wcscpy_s(g_lastError, L"Failed to get session enumerator");
        if (needUninit) CoUninitialize();
        return PAC_ERROR_AUDIO_INIT_FAILED;
    }

    // Get session count
    int sessionCount = 0;
    hr = pSessionList->GetCount(&sessionCount);
    if (FAILED(hr))
    {
        sessionCount = 0;
    }

    // Enumerate sessions
    std::vector<DWORD> foundPids;
    for (int i = 0; i < sessionCount && *actualCount < maxCount; i++)
    {
        IAudioSessionControl* pSessionControl = nullptr;
        hr = pSessionList->GetSession(i, &pSessionControl);
        if (FAILED(hr))
        {
            continue;
        }

        IAudioSessionControl2* pSessionControl2 = nullptr;
        hr = pSessionControl->QueryInterface(__uuidof(IAudioSessionControl2), (void**)&pSessionControl2);
        if (SUCCEEDED(hr))
        {
            DWORD pid = 0;
            hr = pSessionControl2->GetProcessId(&pid);
            if (SUCCEEDED(hr) && pid != 0)
            {
                // Check for duplicates
                bool found = false;
                for (DWORD p : foundPids)
                {
                    if (p == pid)
                    {
                        found = true;
                        break;
                    }
                }

                if (!found)
                {
                    foundPids.push_back(pid);

                    // Get process info
                    PacProcessInfo& info = processes[*actualCount];
                    info.processId = pid;
                    info.processName[0] = L'\0';
                    info.windowTitle[0] = L'\0';

                    // Get process name
                    HANDLE hProcess = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
                    if (hProcess)
                    {
                        wchar_t exePath[MAX_PATH] = { 0 };
                        DWORD size = MAX_PATH;
                        if (QueryFullProcessImageNameW(hProcess, 0, exePath, &size))
                        {
                            // Extract filename only
                            wchar_t* fileName = wcsrchr(exePath, L'\\');
                            if (fileName)
                            {
                                wcscpy_s(info.processName, fileName + 1);
                            }
                            else
                            {
                                wcscpy_s(info.processName, exePath);
                            }
                        }
                        CloseHandle(hProcess);
                    }

                    // Get window title (first window)
                    struct EnumData {
                        DWORD pid;
                        wchar_t* title;
                        int titleSize;
                    } enumData = { pid, info.windowTitle, 260 };

                    EnumWindows([](HWND hwnd, LPARAM lParam) -> BOOL {
                        EnumData* data = (EnumData*)lParam;
                        DWORD windowPid = 0;
                        GetWindowThreadProcessId(hwnd, &windowPid);
                        if (windowPid == data->pid && IsWindowVisible(hwnd))
                        {
                            GetWindowTextW(hwnd, data->title, data->titleSize);
                            if (wcslen(data->title) > 0)
                            {
                                return FALSE; // Found, stop enumeration
                            }
                        }
                        return TRUE;
                    }, (LPARAM)&enumData);

                    (*actualCount)++;
                }
            }
            pSessionControl2->Release();
        }
        pSessionControl->Release();
    }

    pSessionList->Release();
    pSessionManager->Release();
    pDevice->Release();
    pEnumerator->Release();

    if (needUninit) CoUninitialize();

    return PAC_SUCCESS;
}

// Start capture
PAC_API PacErrorCode PacStartCapture(
    DWORD processId,
    PacCaptureMode mode,
    const wchar_t* outputPath,
    PacLevelCallback levelCallback,
    PacDataCallback dataCallback,
    void* userData,
    PacHandle* handle)
{
    if (!handle)
    {
        wcscpy_s(g_lastError, L"Invalid handle pointer");
        return PAC_ERROR_INVALID_PARAM;
    }

    *handle = nullptr;

    // Initialize COM for this thread
    HRESULT hrCom = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    bool comInitialized = SUCCEEDED(hrCom) || hrCom == RPC_E_CHANGED_MODE;

    if (!PacIsSupported())
    {
        wcscpy_s(g_lastError, L"Windows 10 version 2004 or later required");
        if (comInitialized && hrCom != RPC_E_CHANGED_MODE) CoUninitialize();
        return PAC_ERROR_NOT_SUPPORTED;
    }

    // Check if process exists
    HANDLE hProcess = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, processId);
    if (!hProcess)
    {
        wcscpy_s(g_lastError, L"Process not found");
        return PAC_ERROR_PROCESS_NOT_FOUND;
    }
    CloseHandle(hProcess);

    // Create CLoopbackCapture instance
    CLoopbackCapture* capture = new CLoopbackCapture();

    // Initialize FTM for cross-apartment COM calls
    HRESULT hr = capture->Initialize();
    if (FAILED(hr))
    {
        wcscpy_s(g_lastError, L"Failed to initialize COM marshaling");
        delete capture;
        return PAC_ERROR_AUDIO_INIT_FAILED;
    }

    // Callback wrapper
    LevelCallback callback = nullptr;
    if (levelCallback)
    {
        callback = [levelCallback, userData](float levelDb) {
            levelCallback(levelDb, userData);
        };
    }

    // НОВОЕ: Обертка для передачи байтов
    DataCallback dCallback = nullptr;
    if (dataCallback)
    {
        dCallback = [dataCallback, userData](const BYTE* data, UINT32 bytes) {
            dataCallback(data, bytes, userData);
        };
    }

    // Start capture
    hr = capture->StartCapture(
        processId,
        mode == PAC_MODE_INCLUDE,
        outputPath,
        callback,
        dCallback // <-- ПЕРЕДАЕМ НАШ КОЛЛБЭК СЮДА
    );

    if (FAILED(hr))
    {
        std::wstring err = capture->GetLastErrorMsg();
        wcscpy_s(g_lastError, err.c_str());
        delete capture;
        return PAC_ERROR_AUDIO_INIT_FAILED;
    }

    *handle = static_cast<PacHandle>(capture);
    return PAC_SUCCESS;
}

// Stop capture
PAC_API PacErrorCode PacStopCapture(PacHandle handle)
{
    if (!handle)
    {
        wcscpy_s(g_lastError, L"Invalid handle");
        return PAC_ERROR_INVALID_PARAM;
    }

    CLoopbackCapture* capture = static_cast<CLoopbackCapture*>(handle);
    HRESULT hr = capture->StopCapture();
    delete capture;

    if (FAILED(hr))
    {
        wcscpy_s(g_lastError, L"Failed to stop capture");
        return PAC_ERROR_UNKNOWN;
    }

    return PAC_SUCCESS;
}

// Get audio level
PAC_API PacErrorCode PacGetLevel(PacHandle handle, float* levelDb)
{
    if (!handle || !levelDb)
    {
        wcscpy_s(g_lastError, L"Invalid parameters");
        return PAC_ERROR_INVALID_PARAM;
    }

    CLoopbackCapture* capture = static_cast<CLoopbackCapture*>(handle);
    *levelDb = capture->GetCurrentLevel();
    return PAC_SUCCESS;
}

// Check if capturing
PAC_API BOOL PacIsCapturing(PacHandle handle)
{
    if (!handle)
    {
        return FALSE;
    }

    CLoopbackCapture* capture = static_cast<CLoopbackCapture*>(handle);
    return capture->IsCapturing() ? TRUE : FALSE;
}

// Pause capture
PAC_API PacErrorCode PacPauseCapture(PacHandle handle)
{
    if (!handle)
    {
        wcscpy_s(g_lastError, L"Invalid handle");
        return PAC_ERROR_INVALID_PARAM;
    }

    CLoopbackCapture* capture = static_cast<CLoopbackCapture*>(handle);
    HRESULT hr = capture->PauseCapture();

    if (FAILED(hr))
    {
        wcscpy_s(g_lastError, L"Failed to pause capture");
        return PAC_ERROR_NOT_RECORDING;
    }

    return PAC_SUCCESS;
}

// Resume capture
PAC_API PacErrorCode PacResumeCapture(PacHandle handle)
{
    if (!handle)
    {
        wcscpy_s(g_lastError, L"Invalid handle");
        return PAC_ERROR_INVALID_PARAM;
    }

    CLoopbackCapture* capture = static_cast<CLoopbackCapture*>(handle);
    HRESULT hr = capture->ResumeCapture();

    if (FAILED(hr))
    {
        wcscpy_s(g_lastError, L"Failed to resume capture");
        return PAC_ERROR_NOT_RECORDING;
    }

    return PAC_SUCCESS;
}

// Check if paused
PAC_API BOOL PacIsPaused(PacHandle handle)
{
    if (!handle)
    {
        return FALSE;
    }

    CLoopbackCapture* capture = static_cast<CLoopbackCapture*>(handle);
    return capture->IsPaused() ? TRUE : FALSE;
}

// Get last error message
PAC_API void PacGetLastErrorMessage(wchar_t* buffer, int bufferSize)
{
    if (buffer && bufferSize > 0)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        wcsncpy_s(buffer, bufferSize, g_lastError, _TRUNCATE);
    }
}

// Get version
PAC_API const char* PacGetVersion(void)
{
    return VERSION;
}
