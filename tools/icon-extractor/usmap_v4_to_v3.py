"""Convert StarRupture's usmap v4 (ExplicitEnumValues) -> v3 (LargeEnums) so the
nuget CUE4Parse 1.2.2 (max v3) can read it. The ONLY format difference is the enum
entry encoding: v4 = (u64 value, i32 nameRef) per entry; v3 = i32 nameRef in
sequential order. Names + structs are spliced byte-for-byte.

Header layout (verified against the file + CUE4Parse): magic u16, version u8,
bHasVersioning u32 (CUE4Parse ReadBoolean reads 4 bytes), compMethod u8,
compSize u32, decompSize u32 => 16-byte header, body follows.
Source CL118258/Client.usmap is uncompressed (compMethod=None)."""
import struct

SRC = r"F:\sr_dump\sdk\usmap\CL118258\Client.usmap"
DST = r"F:\sr_dump\sdk\usmap\client_v3.usmap"

b = open(SRC, "rb").read()
magic, version, bHasVer, comp = struct.unpack_from("<HBIB", b, 0)
assert magic == 0x30C4 and version == 4 and bHasVer == 0 and comp == 0, (hex(magic), version, bHasVer, comp)
compSize, decompSize = struct.unpack_from("<II", b, 8)
body = b[16:16 + decompSize]
assert len(body) == decompSize and compSize == decompSize, (len(body), compSize, decompSize)

o = 0
def rd(fmt):
    global o; v = struct.unpack_from(fmt, body, o); o += struct.calcsize(fmt); return v

names_start = o
(nameSize,) = rd("<I")
for _ in range(nameSize):
    (ln,) = rd("<H"); o += ln
names_end = o

(enumCount,) = rd("<I")
out = bytearray(struct.pack("<I", enumCount))
for _ in range(enumCount):
    enumNameRef, size = rd("<iH")
    refs = []
    for _ in range(size):
        _val, ref = rd("<qi")          # u64 value (read as signed, value unused) + i32 nameRef
        refs.append(ref)
    out += struct.pack("<iH", enumNameRef, size)
    out += b"".join(struct.pack("<i", r) for r in refs)
structs_start = o

new_body = body[names_start:names_end] + bytes(out) + body[structs_start:]
hdr = struct.pack("<HBIBII", 0x30C4, 3, 0, 0, len(new_body), len(new_body))  # 16-byte header, ver=3
open(DST, "wb").write(hdr + new_body)
print(f"ok: names={nameSize} enums={enumCount} | body {decompSize}->{len(new_body)} "
      f"(saved {decompSize-len(new_body)} enum-value bytes) | wrote {DST}")
