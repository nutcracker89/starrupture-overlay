// inject.exe  -  LoadLibrary injector for RecipeDumper.dll
// Finds the StarRupture client process and loads RecipeDumper.dll into it.
// Usage: run inject.exe from the folder containing RecipeDumper.dll, while
// the game is running and you're in-game.

#include <windows.h>
#include <tlhelp32.h>
#include <cstdio>

static DWORD FindPid(const wchar_t* name) {
    DWORD pid = 0;
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    PROCESSENTRY32W pe{ sizeof(pe) };
    if (Process32FirstW(snap, &pe)) {
        do { if (_wcsicmp(pe.szExeFile, name) == 0) { pid = pe.th32ProcessID; break; } }
        while (Process32NextW(snap, &pe));
    }
    CloseHandle(snap);
    return pid;
}

int wmain() {
    const wchar_t* proc = L"StarRuptureGameSteam-Win64-Shipping.exe";
    wchar_t dll[MAX_PATH];
    GetFullPathNameW(L"rdf2.dll", MAX_PATH, dll, nullptr);
    if (GetFileAttributesW(dll) == INVALID_FILE_ATTRIBUTES) {
        wprintf(L"rdf2.dll not found next to inject.exe\n"); return 1;
    }
    DWORD pid = FindPid(proc);
    if (!pid) { wprintf(L"Game not running: %s\n", proc); return 1; }

    HANDLE h = OpenProcess(PROCESS_ALL_ACCESS, FALSE, pid);
    if (!h) { wprintf(L"OpenProcess failed: %lu\n", GetLastError()); return 1; }

    SIZE_T sz = (wcslen(dll) + 1) * sizeof(wchar_t);
    void* rem = VirtualAllocEx(h, nullptr, sz, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!rem) { wprintf(L"VirtualAllocEx failed: %lu\n", GetLastError()); return 1; }
    WriteProcessMemory(h, rem, dll, sz, nullptr);

    auto ll = (LPTHREAD_START_ROUTINE)GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "LoadLibraryW");
    HANDLE t = CreateRemoteThread(h, nullptr, 0, ll, rem, 0, nullptr);
    if (!t) { wprintf(L"CreateRemoteThread failed: %lu\n", GetLastError()); return 1; }
    WaitForSingleObject(t, 8000);

    wprintf(L"Injected RecipeDumper.dll into pid %lu.\nGet in-game, then press F10 to dump.\n", pid);
    return 0;
}
