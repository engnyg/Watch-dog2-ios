#!/usr/bin/env python3
"""wine dlls/wow64/system.c: implement wow64_NtRaiseHardError WoW64 thunk.

The stub FIXME-logs and returns STATUS_NOT_IMPLEMENTED without setting *Response.
upc.exe (Ubisoft .ubx packer) calls NtRaiseHardError(0x50000018, 4, 3, ...) after
its ICEBP self-check passes, then reads *Response to decide whether to continue.
Response=0 (ReturnToCaller, stub default) causes it to call NtTerminateProcess(0xDEADC0DE).

Fix: translate the 32-bit argument frame to 64-bit and call NtRaiseHardError.
UNICODE_STRING32 params (indicated by params_mask bits) are promoted via ULongToPtr.
If the 64-bit call leaves Response=0 (headless Wine/iOS, ResponseNotHandled path),
fall back to ResponseIgnore (4) so OptionAbortRetryIgnore callers don't abort.

Usage: patch-wine-wow64.py <wine/dlls/wow64/system.c>
"""
import sys, re

SENTINEL = "ml-wow64-raiseharderror"
path = sys.argv[1]
src = open(path, encoding="utf-8").read()

if SENTINEL in src:
    print("already patched"); sys.exit(0)

# Unique discriminant: the FIXME format string shared across all Wine forks
FIXME_MARKER = 'FIXME( "%08lx %lu %lx %p %u %p: stub\\n"'
if FIXME_MARKER not in src:
    sys.exit("FIXME marker not found in %s — check Wine version/path" % path)

fixme_pos = src.index(FIXME_MARKER)

# Find the function header (comment + signature) that precedes the FIXME
func_header_pat = re.compile(
    r'/\*\*+\s*\*\s+wow64_NtRaiseHardError\s*\*+/\s+'
    r'NTSTATUS WINAPI wow64_NtRaiseHardError\s*\(\s*UINT\s*\*args\s*\)'
)
m = func_header_pat.search(src, 0, fixme_pos)
if not m:
    sys.exit("function header not found before FIXME in %s" % path)

func_start = m.start()
open_brace = src.index('{', m.end())

# Find the matching closing brace
depth, pos = 1, open_brace + 1
while pos < len(src) and depth > 0:
    if src[pos] == '{':
        depth += 1
    elif src[pos] == '}':
        depth -= 1
    pos += 1
func_end = pos  # one past the closing '}'

OLD_FUNC = src[func_start:func_end]

NEW_FUNC = """\
/* ml-wow64-raiseharderror: 32-bit guest address -> host pointer, via the same get_ptr() the thunks use
   (it adds the WoW64 window base; plain ULongToPtr does not and faults) */
static void *ml_ptr32( ULONG v )
{
    UINT tmp = v, *p = &tmp;
    return get_ptr( &p );
}

/* wow64.dll links ntdll only, so debugstr_w* (needs kernel32) is unavailable: print ASCII by hand */
static void ml_dump_us( ULONG i, const UNICODE_STRING *us )
{
    char buf[257];
    ULONG n, len = us->Buffer ? us->Length / sizeof(WCHAR) : 0;
    if (len > 256) len = 256;
    for (n = 0; n < len; n++) buf[n] = (us->Buffer[n] >= 0x20 && us->Buffer[n] < 0x7f) ? (char)us->Buffer[n] : '?';
    buf[n] = 0;
    ERR( "ml-wow64   param %lu: [%s]\\n", i, buf );
}

/**********************************************************************
 *           wow64_NtRaiseHardError
 */
NTSTATUS WINAPI wow64_NtRaiseHardError( UINT *args )
{
    NTSTATUS status       = get_ulong( &args );
    ULONG count           = get_ulong( &args );
    ULONG params_mask     = get_ulong( &args );
    ULONG *params32       = get_ptr( &args );
    ULONG option          = get_ulong( &args );
    ULONG *response32     = get_ptr( &args );
    /* ml-wow64-raiseharderror: translate 32→64 bit frame; upc.exe reads *Response */
    PVOID params64[8] = {0};
    UNICODE_STRING strs64[8];
    HARDERROR_RESPONSE response = 0;
    NTSTATUS ret;
    ULONG i;

    for (i = 0; i < count && i < 8; i++)
    {
        if (params32 && ((params_mask >> i) & 1))
        {
            const UNICODE_STRING32 *s = ml_ptr32( params32[i] );
            if (!s) { params64[i] = NULL; continue; }
            strs64[i].Length        = s->Length;
            strs64[i].MaximumLength = s->MaximumLength;
            strs64[i].Buffer        = ml_ptr32( s->Buffer );
            params64[i] = &strs64[i];
        }
        else params64[i] = params32 ? (PVOID)(ULONG_PTR)params32[i] : NULL;
    }
    ERR( "ml-wow64 hard error: status %08lx count %lu mask %lx option %lu\\n", (ULONG)status, count, params_mask, option );
    for (i = 0; i < count && i < 8; i++)
    {
        if (((params_mask >> i) & 1) && params64[i])
            ml_dump_us( i, &strs64[i] );
        else ERR( "ml-wow64   param %lu: %p\\n", i, params64[i] );
    }
    ret = NtRaiseHardError( status, count, params_mask, params64, (HARDERROR_RESPONSE_OPTION)option, &response );
    ERR( "ml-wow64   NtRaiseHardError returned %08lx response %u\\n", (ULONG)ret, (UINT)response );
    /* Headless Wine/iOS: server returns ResponseNotHandled (1) or leaves 0; treat
       as ResponseIgnore (4) so OptionAbortRetryIgnore callers don't take Abort path. */
    if (!response) response = (HARDERROR_RESPONSE)4;
    if (response32) *response32 = response;
    if (ret == STATUS_NOT_IMPLEMENTED) ret = STATUS_SUCCESS;  /* a response was synthesized above */
    return ret;
}"""

open(path, "w", encoding="utf-8").write(src[:func_start] + NEW_FUNC + src[func_end:])
print("patched: wow64_NtRaiseHardError thunk implemented (ml-wow64-raiseharderror)")
