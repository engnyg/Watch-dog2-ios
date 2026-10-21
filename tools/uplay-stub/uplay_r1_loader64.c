/*
 * Stub uplay_r1_loader64.dll for Watch Dogs 2 under Madeira/FEX-on-iOS.
 *
 * Problem: RunGameEx (Disrupt_64.dll) loads this DLL and calls UPLAY_Start, which
 * tries to authenticate via upc.exe over a named pipe.  Under FEX/Wine on iOS
 * upc.exe exits 0xDEADC0DE (SteamInfoReceiver fails, pipe never created), so
 * UPLAY_Start never returns and the game hangs/exits.
 *
 * This stub exports every function the game calls, returns a plausible offline
 * success value for each, and never spawns or contacts upc.exe.
 *
 * Fake IDs are chosen to be obviously synthetic (not real Ubisoft IDs).
 */

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>

/* ── WD2 uplay_game_id passed to UPLAY_Start ─────────────────────────── */
#define WD2_UPLAY_ID 3619

/* ── Fake offline user ───────────────────────────────────────────────── */
static const char  FAKE_USER_NAME[]    = "OfflineUser";
static const char  FAKE_USER_ID_HEX[]  = "DEADBEEFCAFEBABE";
static const uint32_t FAKE_USER_ID     = 0xCAFEBABEu;
static const char  FAKE_CD_KEY[]       = "XXXXX-XXXXX-XXXXX-XXXXX-XXXXX";

/* ── DLL entry ───────────────────────────────────────────────────────── */
BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved)
{
    (void)hinstDLL; (void)fdwReason; (void)lpvReserved;
    return TRUE;
}

/* ─────────────────────────────────────────────────────────────────────
 * Core lifecycle
 * ──────────────────────────────────────────────────────────────────── */

/* UPLAY_Start: main entry point called from RunGameEx.
 * Real impl connects to upc.exe, waits for auth, returns FALSE on failure.
 * We return TRUE immediately so RunGameEx can proceed. */
__declspec(dllexport) BOOL UPLAY_Start(uint32_t uplay_id, uint32_t sdk_version, HWND hwnd)
{
    (void)uplay_id; (void)sdk_version; (void)hwnd;
    return TRUE;
}

__declspec(dllexport) BOOL UPLAY_StartWithOverlayEnabled(uint32_t uplay_id, uint32_t sdk_version, HWND hwnd, BOOL overlay)
{
    (void)overlay;
    return UPLAY_Start(uplay_id, sdk_version, hwnd);
}

__declspec(dllexport) void UPLAY_Stop(void) {}

/* UPLAY_Update: pumps the Uplay event loop; called once per frame.
 * Returns number of pending events (0 = idle). */
__declspec(dllexport) uint32_t UPLAY_Update(void) { return 0; }

/* ─────────────────────────────────────────────────────────────────────
 * User / ownership
 * ──────────────────────────────────────────────────────────────────── */

__declspec(dllexport) uint32_t UPLAY_User_GetId(void)             { return FAKE_USER_ID; }
__declspec(dllexport) const char* UPLAY_User_GetIdHex(void)        { return FAKE_USER_ID_HEX; }
__declspec(dllexport) const char* UPLAY_User_GetNameUtf8(void)     { return FAKE_USER_NAME; }
__declspec(dllexport) const char* UPLAY_User_GetCdKeyUtf8(void)    { return FAKE_CD_KEY; }
__declspec(dllexport) BOOL UPLAY_User_HasOnlineAccess(void)        { return FALSE; }

/* UPLAY_User_IsOwned / UPLAY_IsOwned: must return TRUE or the game exits. */
__declspec(dllexport) BOOL UPLAY_User_IsOwned(uint32_t game_id)   { (void)game_id; return TRUE; }
__declspec(dllexport) BOOL UPLAY_IsOwned(uint32_t game_id)        { (void)game_id; return TRUE; }

/* ─────────────────────────────────────────────────────────────────────
 * DRM / protection
 * ──────────────────────────────────────────────────────────────────── */

/* Returns 0 = no protection (offline). */
__declspec(dllexport) uint32_t UPLAY_DRM_GetProtectionType(void)  { return 0; }

/* ─────────────────────────────────────────────────────────────────────
 * Overlay – disabled; game must not block on overlay focus
 * ──────────────────────────────────────────────────────────────────── */

__declspec(dllexport) BOOL  UPLAY_Overlay_IsEnabled(void)          { return FALSE; }
__declspec(dllexport) BOOL  UPLAY_Overlay_IsFocused(void)          { return FALSE; }
__declspec(dllexport) BOOL  UPLAY_Overlay_IsExclusive(void)        { return FALSE; }
__declspec(dllexport) uint32_t UPLAY_Overlay_GetState(void)        { return 0; }
__declspec(dllexport) uint32_t UPLAY_Overlay_GetFocusState(void)   { return 0; }
__declspec(dllexport) void  UPLAY_Overlay_Init(void *hwnd)         { (void)hwnd; }
__declspec(dllexport) void  UPLAY_Overlay_Activate(void)           {}
__declspec(dllexport) void  UPLAY_Overlay_HideNotifications(BOOL b){ (void)b; }
__declspec(dllexport) void  UPLAY_Overlay_ShowNotifications(BOOL b){ (void)b; }
__declspec(dllexport) BOOL  UPLAY_Overlay_ShowPage(uint32_t page)  { (void)page; return FALSE; }
__declspec(dllexport) BOOL  UPLAY_Overlay_ShowUrlPage(const char *u){ (void)u; return FALSE; }
__declspec(dllexport) BOOL  UPLAY_Overlay_ShowPSNPage(const char *u){ (void)u; return FALSE; }

/* ─────────────────────────────────────────────────────────────────────
 * Achievements
 * ──────────────────────────────────────────────────────────────────── */

__declspec(dllexport) BOOL UPLAY_Achievement_HasAchievement(uint32_t id)   { (void)id; return FALSE; }
__declspec(dllexport) BOOL UPLAY_Achievement_UnlockAchievement(uint32_t id){ (void)id; return TRUE; }
__declspec(dllexport) BOOL UPLAY_Achievement_PostAchievements(void)         { return TRUE; }
__declspec(dllexport) BOOL UPLAY_Achievement_ReadAchievements(void)         { return TRUE; }
__declspec(dllexport) BOOL UPLAY_Achievement_GetAchievements(uint32_t *cnt, void **out)
{
    if (cnt) *cnt = 0;
    if (out) *out = NULL;
    return TRUE;
}

/* ─────────────────────────────────────────────────────────────────────
 * Actions / Rewards (Uplay points / virtual currency)
 * ──────────────────────────────────────────────────────────────────── */

__declspec(dllexport) BOOL UPLAY_Action_GetActions(uint32_t *cnt, void **out)
{
    if (cnt) *cnt = 0;
    if (out) *out = NULL;
    return TRUE;
}
__declspec(dllexport) BOOL UPLAY_Action_EarnReward(uint32_t id, void *action)
{
    (void)id; (void)action;
    return TRUE;
}
__declspec(dllexport) BOOL UPLAY_GetActionByIndex(uint32_t idx, void **out)
{
    (void)idx;
    if (out) *out = NULL;
    return FALSE;
}
__declspec(dllexport) BOOL UPLAY_GetActionsForProduct(uint32_t id, uint32_t *cnt, void **out)
{
    (void)id;
    if (cnt) *cnt = 0;
    if (out) *out = NULL;
    return TRUE;
}

/* ─────────────────────────────────────────────────────────────────────
 * Products / catalogue
 * ──────────────────────────────────────────────────────────────────── */

__declspec(dllexport) BOOL UPLAY_Product_GetProductList(uint32_t *cnt, void **out)
{
    if (cnt) *cnt = 0;
    if (out) *out = NULL;
    return TRUE;
}
__declspec(dllexport) BOOL UPLAY_GetProductList(uint32_t *cnt, void **out)
{
    return UPLAY_Product_GetProductList(cnt, out);
}
__declspec(dllexport) BOOL UPLAY_GetLocalUsers(uint32_t *cnt, void **out)
{
    if (cnt) *cnt = 0;
    if (out) *out = NULL;
    return TRUE;
}

/* ─────────────────────────────────────────────────────────────────────
 * Leaderboards
 * ──────────────────────────────────────────────────────────────────── */

__declspec(dllexport) BOOL UPLAY_Leaderboard_GetList(uint32_t *cnt, void **out)
{
    if (cnt) *cnt = 0; if (out) *out = NULL; return TRUE;
}
__declspec(dllexport) BOOL UPLAY_Leaderboard_GetGlobalList(uint32_t *cnt, void **out)
{
    if (cnt) *cnt = 0; if (out) *out = NULL; return TRUE;
}
__declspec(dllexport) BOOL UPLAY_Leaderboard_GetScore(uint32_t id, void **out)
{
    (void)id; if (out) *out = NULL; return TRUE;
}
__declspec(dllexport) BOOL UPLAY_Leaderboard_ReadScore(uint32_t id)    { (void)id; return TRUE; }
__declspec(dllexport) BOOL UPLAY_Leaderboard_SetScore(uint32_t id, int64_t score)
{
    (void)id; (void)score; return TRUE;
}
__declspec(dllexport) BOOL UPLAY_Leaderboard_WriteScore(uint32_t id, int64_t score)
{
    return UPLAY_Leaderboard_SetScore(id, score);
}
__declspec(dllexport) BOOL UPLAY_Leaderboard_GetScoresAroundPlayer(uint32_t id, uint32_t cnt, void **out)
{
    (void)id; (void)cnt; if (out) *out = NULL; return TRUE;
}
__declspec(dllexport) BOOL UPLAY_Leaderboard_GetScoresForFriends(uint32_t id, uint32_t cnt, void **out)
{
    (void)id; (void)cnt; if (out) *out = NULL; return TRUE;
}

/* ─────────────────────────────────────────────────────────────────────
 * Cloud storage / PcSave
 * ──────────────────────────────────────────────────────────────────── */

__declspec(dllexport) BOOL UPLAY_Storage_GetStorageList(uint32_t *cnt, void **out)
{
    if (cnt) *cnt = 0; if (out) *out = NULL; return TRUE;
}
__declspec(dllexport) BOOL UPLAY_Storage_Open(uint32_t id, BOOL write)   { (void)id; (void)write; return TRUE; }
__declspec(dllexport) BOOL UPLAY_Storage_Close(uint32_t id)              { (void)id; return TRUE; }
__declspec(dllexport) BOOL UPLAY_Storage_FileExists(uint32_t id, const char *p){ (void)id; (void)p; return FALSE; }
__declspec(dllexport) BOOL UPLAY_Storage_GetFileSize(uint32_t id, const char *p, uint32_t *sz)
{
    (void)id; (void)p; if (sz) *sz = 0; return FALSE;
}
__declspec(dllexport) BOOL UPLAY_Storage_ReadFile(uint32_t id, const char *p, void *buf, uint32_t sz, uint32_t *rd)
{
    (void)id; (void)p; (void)buf; (void)sz; if (rd) *rd = 0; return FALSE;
}
__declspec(dllexport) BOOL UPLAY_Storage_WriteFile(uint32_t id, const char *p, const void *buf, uint32_t sz)
{
    (void)id; (void)p; (void)buf; (void)sz; return TRUE;
}
__declspec(dllexport) BOOL UPLAY_Storage_DeleteFile(uint32_t id, const char *p)
{
    (void)id; (void)p; return TRUE;
}
__declspec(dllexport) BOOL UPLAY_Storage_GetFileList(uint32_t id, const char *dir, uint32_t *cnt, char **files)
{
    (void)id; (void)dir; if (cnt) *cnt = 0; if (files) *files = NULL; return TRUE;
}

/* PcSave (older name used in some Uplay versions) */
__declspec(dllexport) BOOL UPLAY_PcSave_GetSharedSaveFileList(uint32_t *cnt, void **out)
{
    if (cnt) *cnt = 0; if (out) *out = NULL; return TRUE;
}
__declspec(dllexport) BOOL UPLAY_PcSave_OpenSharedSaveFile(uint32_t id)     { (void)id; return TRUE; }
__declspec(dllexport) BOOL UPLAY_PcSave_CloseSharedSaveFile(uint32_t id)    { (void)id; return TRUE; }
__declspec(dllexport) BOOL UPLAY_PcSave_ReadSharedSaveFile(uint32_t id, void *buf, uint32_t sz, uint32_t *rd)
{
    (void)id; (void)buf; (void)sz; if (rd) *rd = 0; return FALSE;
}
__declspec(dllexport) BOOL UPLAY_PcSave_WriteSharedSaveFile(uint32_t id, const void *buf, uint32_t sz)
{
    (void)id; (void)buf; (void)sz; return TRUE;
}
__declspec(dllexport) BOOL UPLAY_PcSave_DeleteSharedSaveFile(uint32_t id)   { (void)id; return TRUE; }

/* ─────────────────────────────────────────────────────────────────────
 * Friends / relationships
 * ──────────────────────────────────────────────────────────────────── */

__declspec(dllexport) BOOL UPLAY_Friends_GetFriends(uint32_t *cnt, void **out)
{
    if (cnt) *cnt = 0; if (out) *out = NULL; return TRUE;
}
__declspec(dllexport) BOOL UPLAY_Friends_GetFriendIds(uint32_t *cnt, void **out)
{
    if (cnt) *cnt = 0; if (out) *out = NULL; return TRUE;
}
__declspec(dllexport) BOOL UPLAY_Friends_FriendInvite(uint32_t id)         { (void)id; return TRUE; }
__declspec(dllexport) BOOL UPLAY_FriendList_GetList(uint32_t *cnt, void **out)
{
    if (cnt) *cnt = 0; if (out) *out = NULL; return TRUE;
}
__declspec(dllexport) BOOL UPLAY_Relationship_GetFriendList(uint32_t *cnt, void **out)
{
    if (cnt) *cnt = 0; if (out) *out = NULL; return TRUE;
}
__declspec(dllexport) BOOL UPLAY_Relationship_GetFriendFocus(uint32_t id, void **out)
{
    (void)id; if (out) *out = NULL; return FALSE;
}
__declspec(dllexport) BOOL UPLAY_Relationship_GetRecentPlayers(uint32_t *cnt, void **out)
{
    if (cnt) *cnt = 0; if (out) *out = NULL; return TRUE;
}

/* ─────────────────────────────────────────────────────────────────────
 * Game badges
 * ──────────────────────────────────────────────────────────────────── */

__declspec(dllexport) BOOL UPLAY_GameBadge_GetBadges(uint32_t *cnt, void **out)
{
    if (cnt) *cnt = 0; if (out) *out = NULL; return TRUE;
}
__declspec(dllexport) BOOL UPLAY_GameBadge_GetBadgeState(uint32_t id, uint32_t *state)
{
    (void)id; if (state) *state = 0; return FALSE;
}
__declspec(dllexport) BOOL UPLAY_GameBadge_SetBadgeState(uint32_t id, uint32_t state)
{
    (void)id; (void)state; return TRUE;
}

/* ─────────────────────────────────────────────────────────────────────
 * ACL / entitlements
 * ──────────────────────────────────────────────────────────────────── */

__declspec(dllexport) BOOL UPLAY_ACL_GetAcls(uint32_t *cnt, void **out)
{
    if (cnt) *cnt = 0; if (out) *out = NULL; return TRUE;
}
__declspec(dllexport) BOOL UPLAY_ACL_GetAccessStatus(uint32_t id, uint32_t *status)
{
    (void)id;
    /* 1 = access granted */
    if (status) *status = 1;
    return TRUE;
}

/* ─────────────────────────────────────────────────────────────────────
 * Club / subscription / fingerprint (stubs only)
 * ──────────────────────────────────────────────────────────────────── */

__declspec(dllexport) BOOL UPLAY_Club_GrantActivision(const char *token)    { (void)token; return TRUE; }
__declspec(dllexport) BOOL UPLAY_Fingerprint_CreatePendingAccountSync(void) { return TRUE; }
__declspec(dllexport) BOOL UPLAY_Fingerprint_SetSyncResult(uint32_t res)    { (void)res; return TRUE; }
__declspec(dllexport) BOOL UPLAY_Fingerprint_SyncData(void *data, uint32_t sz)
{
    (void)data; (void)sz; return TRUE;
}
