// Process-specific audio capture DLL
// Original wrapper by tsubome: https://github.com/tsubome/ProcessAudioCapture
// Based on Microsoft ApplicationLoopback Sample
// 
// Modified for real-time PCM byte streaming via callbacks.
#pragma once

#ifdef PROCESSAUDIOCAPTURE_EXPORTS
#define PAC_API __declspec(dllexport)
#else
#define PAC_API __declspec(dllimport)
#endif

#include <Windows.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// Error codes
typedef enum {
    PAC_SUCCESS = 0,
    PAC_ERROR_INVALID_PARAM = -1,
    PAC_ERROR_NOT_SUPPORTED = -2,      // Windows version not supported
    PAC_ERROR_PROCESS_NOT_FOUND = -3,
    PAC_ERROR_AUDIO_INIT_FAILED = -4,
    PAC_ERROR_FILE_CREATE_FAILED = -5,
    PAC_ERROR_ALREADY_RECORDING = -6,
    PAC_ERROR_NOT_RECORDING = -7,
    PAC_ERROR_UNKNOWN = -100
} PacErrorCode;

// Capture mode
typedef enum {
    PAC_MODE_INCLUDE = 0,  // Capture only the specified process audio
    PAC_MODE_EXCLUDE = 1   // Capture all audio except the specified process
} PacCaptureMode;

// Capture handle (opaque type)
typedef void* PacHandle;

// Process info structure
typedef struct {
    DWORD processId;
    wchar_t processName[260];
    wchar_t windowTitle[260];
} PacProcessInfo;

// Callback function type (for audio level notification)
typedef void (*PacLevelCallback)(float levelDb, void* userData);
typedef void (*PacDataCallback)(const uint8_t* pcmData, uint32_t bytesCount, void* userData);

// ========== API Functions ==========

/// Check if Windows version is supported (Windows 10 2004 or later required)
/// @return TRUE: supported, FALSE: not supported
PAC_API BOOL PacIsSupported(void);

/// Get list of processes that are outputting audio
/// @param[out] processes Array of process info (caller allocated)
/// @param[in] maxCount Maximum size of array
/// @param[out] actualCount Actual number of processes found
/// @return Error code
PAC_API PacErrorCode PacEnumerateAudioProcesses(
    PacProcessInfo* processes,
    int maxCount,
    int* actualCount
);

/// Start process-specific audio capture
/// @param[in] processId Target process ID
/// @param[in] mode Capture mode (INCLUDE/EXCLUDE)
/// @param[in] outputPath Output WAV file path (NULL for no file output)
/// @param[in] levelCallback Audio level callback (NULL for no notification)
/// @param[in] userData User data to pass to callback
/// @param[out] handle Capture handle
/// @return Error code
PAC_API PacErrorCode PacStartCapture(
    DWORD processId,
    PacCaptureMode mode,
    const wchar_t* outputPath,
    PacLevelCallback levelCallback,
    PacDataCallback dataCallback,
    void* userData,
    PacHandle* handle
);

/// Stop capture
/// @param[in] handle Capture handle
/// @return Error code
PAC_API PacErrorCode PacStopCapture(PacHandle handle);

/// Get current audio level (dB)
/// @param[in] handle Capture handle
/// @param[out] levelDb Audio level (dB, -60 to 0)
/// @return Error code
PAC_API PacErrorCode PacGetLevel(PacHandle handle, float* levelDb);

/// Check if capturing
/// @param[in] handle Capture handle
/// @return TRUE: capturing, FALSE: stopped or invalid handle
PAC_API BOOL PacIsCapturing(PacHandle handle);

/// Pause capture (stop writing to file, continue level monitoring)
/// @param[in] handle Capture handle
/// @return Error code
PAC_API PacErrorCode PacPauseCapture(PacHandle handle);

/// Resume capture
/// @param[in] handle Capture handle
/// @return Error code
PAC_API PacErrorCode PacResumeCapture(PacHandle handle);

/// Check if paused
/// @param[in] handle Capture handle
/// @return TRUE: paused, FALSE: not paused or invalid handle
PAC_API BOOL PacIsPaused(PacHandle handle);

/// Get last error message
/// @param[out] buffer Error message buffer
/// @param[in] bufferSize Buffer size (in characters)
PAC_API void PacGetLastErrorMessage(wchar_t* buffer, int bufferSize);

/// Get version info
/// @return Version string
PAC_API const char* PacGetVersion(void);

#ifdef __cplusplus
}
#endif
