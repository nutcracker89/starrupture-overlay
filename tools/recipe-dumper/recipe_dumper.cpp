// RecipeDumper.dll  -  StarRupture recipe extractor
// Reads UAuItemRecipeData from the live game and writes real recipes to JSON.
// Offsets are from AlienX's StarRupture SDK (Dumper7) for the current build.
// Raw memory reads are isolated in SEH-guarded POD-only helpers so a wrong
// offset writes an error instead of crashing the game.  Inject, get in-game, F10.

#include <windows.h>
#include <cstdint>
#include <string>
#include <cstdio>

typedef int32_t  i32;
typedef uintptr_t u64;

static const char* OUT_PATH = "F:\\starrupture_timer\\recipes_final2.json";

// --- RVA offsets for this build (AlienX SDK) ---
static const u64 OFF_GObjects     = 0x0E1DAF40;
static const u64 OFF_AppendString = 0x014A8040;

// --- struct field offsets ---
enum {
    UObj_Class    = 0x10, UObj_Name = 0x18,
    UClass_CDO    = 0x110,
    Arr_Objects   = 0x00, Arr_Num = 0x14, ChunkSize = 0x10000, ItemStride = 0x18,
    IRD_Needed    = 0x30, IRD_Output = 0x40,
    Order_Item    = 0x00, Order_Count = 0x08, Order_Stride = 0x10,
    IDB_ItemName  = 0x2E0, IDB_UniqueName = 0x2F0,
    IRD_Display   = 0x110,    // CrItemRecipeData.DisplayText (FText)
    FTextData_Str = 0x20,
};

#pragma pack(push, 1)
struct FString { wchar_t* Data; i32 Num; i32 Max; };   // POD
#pragma pack(pop)

typedef void(__fastcall* AppendStringFn)(const void* fname, FString* out);

static u64            g_Base = 0;
static AppendStringFn g_AppendString = nullptr;

// ---- SEH-guarded POD-only readers (no C++ objects here) ----
__declspec(noinline) static bool RD8(u64 addr, u64* out) {
    __try { *out = *(u64*)addr; return true; } __except (EXCEPTION_EXECUTE_HANDLER) { return false; }
}
__declspec(noinline) static bool RD4(u64 addr, i32* out) {
    __try { *out = *(i32*)addr; return true; } __except (EXCEPTION_EXECUTE_HANDLER) { return false; }
}
__declspec(noinline) static bool ReadFStr(const FString* fs, wchar_t* buf, int cap, int* outLen) {
    __try {
        if (!fs->Data) { *outLen = 0; return false; }
        int n = fs->Num; if (n > 0 && fs->Data[n - 1] == 0) n--;
        if (n < 0) n = 0; if (n > cap - 1) n = cap - 1;
        for (int i = 0; i < n; i++) buf[i] = fs->Data[i];
        buf[n] = 0; *outLen = n; return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) { *outLen = 0; return false; }
}
__declspec(noinline) static bool NameToBuf(const void* fname, wchar_t* buf, int cap, int* outLen) {
    __try {
        FString s{ nullptr, 0, 0 };
        g_AppendString(fname, &s);
        return ReadFStr(&s, buf, cap, outLen);
    } __except (EXCEPTION_EXECUTE_HANDLER) { *outLen = 0; return false; }
}
__declspec(noinline) static bool FTextToBuf(u64 ftextAddr, wchar_t* buf, int cap, int* outLen) {
    __try {
        u64 td = *(u64*)(ftextAddr);                   // FText -> FTextData*
        if (!td) { *outLen = 0; return false; }
        return ReadFStr((const FString*)(td + FTextData_Str), buf, cap, outLen);
    } __except (EXCEPTION_EXECUTE_HANDLER) { *outLen = 0; return false; }
}

// ---- std::string layer (no SEH) ----
static std::string W2U(const wchar_t* w, int len) {
    if (!w || len <= 0) return "";
    int n = WideCharToMultiByte(CP_UTF8, 0, w, len, nullptr, 0, nullptr, nullptr);
    std::string s(n, 0);
    WideCharToMultiByte(CP_UTF8, 0, w, len, &s[0], n, nullptr, nullptr);
    return s;
}
static std::string Esc(const std::string& s) {
    std::string o; o.reserve(s.size() + 4);
    for (char c : s) { if (c == '"' || c == '\\') o += '\\'; o += c; }
    return o;
}
static std::string FNameStr(const void* fname) {
    wchar_t buf[256]; int len = 0;
    if (NameToBuf(fname, buf, 256, &len)) return W2U(buf, len);
    return "";
}
static std::string ItemName(u64 itemClass) {
    if (!itemClass) return "?";
    u64 cdo = 0;
    if (!RD8(itemClass + UClass_CDO, &cdo) || !cdo) return "?";
    wchar_t buf[256]; int len = 0;
    if (NameToBuf((const void*)(cdo + IDB_UniqueName), buf, 256, &len) && len > 0) return W2U(buf, len);
    if (FTextToBuf(cdo + IDB_ItemName, buf, 256, &len) && len > 0) return W2U(buf, len);
    return "?";
}

static void DoDump() {
    std::string out = "[\n";
    int count = 0;
    char buf[2048];

    u64 objectsPtr = 0; i32 num = 0;
    u64 gobj = g_Base + OFF_GObjects;
    if (!RD8(gobj + Arr_Objects, &objectsPtr) || !RD4(gobj + Arr_Num, &num) || !objectsPtr) {
        MessageBoxA(NULL, "Could not read GObjects (offset mismatch for this build?).",
                    "RecipeDumper", MB_OK | MB_ICONWARNING);
        return;
    }
    if (num < 0 || num > 4000000) num = 0;

    for (i32 i = 0; i < num; i++) {
        u64 chunkPtr = 0;
        if (!RD8(objectsPtr + (u64)(i / ChunkSize) * 8, &chunkPtr) || !chunkPtr) continue;
        u64 obj = 0;
        if (!RD8(chunkPtr + (u64)(i % ChunkSize) * ItemStride, &obj) || !obj) continue;
        u64 cls = 0;
        if (!RD8(obj + UObj_Class, &cls) || !cls) continue;
        if (FNameStr((const void*)(cls + UObj_Name)) != "CrItemRecipeData") continue;

        u64 outCls = 0; i32 outQty = 0;
        RD8(obj + IRD_Output + Order_Item, &outCls);
        RD4(obj + IRD_Output + Order_Count, &outQty);
        std::string outName = ItemName(outCls);
        if (outName == "?") {                                  // fallback: recipe DisplayText
            wchar_t db[256]; int dl = 0;
            if (FTextToBuf(obj + IRD_Display, db, 256, &dl) && dl > 0) outName = W2U(db, dl);
        }

        u64 nrData = 0; i32 nrNum = 0;
        RD8(obj + IRD_Needed + 0x0, &nrData);
        RD4(obj + IRD_Needed + 0x8, &nrNum);
        if (nrNum < 0 || nrNum > 64) nrNum = 0;

        std::string ins;
        for (i32 k = 0; k < nrNum; k++) {
            u64 elem = nrData + (u64)k * Order_Stride;
            u64 inCls = 0; i32 inQty = 0;
            RD8(elem + Order_Item, &inCls);
            RD4(elem + Order_Count, &inQty);
            std::string inName = ItemName(inCls);
            sprintf_s(buf, "{\"item\":\"%s\",\"qty\":%d}", Esc(inName).c_str(), inQty);
            if (k) ins += ",";
            ins += buf;
        }
        sprintf_s(buf, "%s  {\"output\":\"%s\",\"output_qty\":%d,\"inputs\":[%s]}",
                  count ? ",\n" : "", Esc(outName).c_str(), outQty, ins.c_str());
        out += buf; count++;
    }
    out += "\n]\n";
    FILE* f = nullptr; fopen_s(&f, OUT_PATH, "wb");
    if (f) { fwrite(out.data(), 1, out.size(), f); fclose(f); }
    sprintf_s(buf, "Wrote %d recipes to:\n%s", count, OUT_PATH);
    MessageBoxA(NULL, buf, "RecipeDumper", MB_OK | MB_ICONINFORMATION);
}

static bool ci_has(const std::string& h, const char* n) {
    std::string H = h; for (auto& c : H) c = (char)tolower((unsigned char)c);
    return H.find(n) != std::string::npos;
}

// Diagnostic: list every object whose class/name relates to recipes/crafting/tables,
// so we can locate where recipe data actually lives.
static void DiagDump() {
    std::string out; char buf[1024];
    u64 objectsPtr = 0; i32 num = 0; u64 gobj = g_Base + OFF_GObjects;
    if (!RD8(gobj + Arr_Objects, &objectsPtr) || !RD4(gobj + Arr_Num, &num) || !objectsPtr) return;
    if (num < 0 || num > 4000000) num = 0;
    int total = 0, lines = 0, ird = 0;
    for (i32 i = 0; i < num; i++) {
        u64 chunkPtr = 0; if (!RD8(objectsPtr + (u64)(i / ChunkSize) * 8, &chunkPtr) || !chunkPtr) continue;
        u64 obj = 0; if (!RD8(chunkPtr + (u64)(i % ChunkSize) * ItemStride, &obj) || !obj) continue;
        u64 cls = 0; if (!RD8(obj + UObj_Class, &cls) || !cls) continue;
        total++;
        std::string cn = FNameStr((const void*)(cls + UObj_Name));
        if (cn == "AuItemRecipeData") ird++;
        std::string on = FNameStr((const void*)(obj + UObj_Name));
        if (lines < 1200 && (ci_has(cn, "recipe") || ci_has(cn, "craft") || ci_has(cn, "datatable")
                             || ci_has(on, "recipe") || ci_has(on, "craft"))) {
            sprintf_s(buf, "%s : %s\n", on.c_str(), cn.c_str()); out += buf; lines++;
        }
    }
    char h[256];
    sprintf_s(h, "total objects: %d\nAuItemRecipeData instances: %d\nmatched lines: %d\n\n", total, ird, lines);
    std::string full = h + out;
    FILE* f = nullptr; fopen_s(&f, "F:\\starrupture_timer\\diag.txt", "wb");
    if (f) { fwrite(full.data(), 1, full.size(), f); fclose(f); }
}

static DWORD WINAPI Thread(LPVOID) {
    g_Base = (u64)GetModuleHandleW(NULL);
    g_AppendString = (AppendStringFn)(g_Base + OFF_AppendString);
    MessageBoxA(NULL, "RecipeDumper loaded.\nGet in-game (in a save), then press F10 to dump.",
                "RecipeDumper", MB_OK | MB_ICONINFORMATION);
    for (;;) {
        if (GetAsyncKeyState(VK_F10) & 0x8000) { DoDump(); Sleep(800); }
        Sleep(40);
    }
}

BOOL APIENTRY DllMain(HMODULE h, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        CreateThread(nullptr, 0, Thread, nullptr, 0, nullptr);
    }
    return TRUE;
}
