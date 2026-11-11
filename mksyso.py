import struct
import sys


def build(ico_path, out_path):
    ico = open(ico_path, "rb").read()
    n = struct.unpack("<H", ico[4:6])[0]
    entries = []
    for i in range(n):
        w, h, c, _, pl, bpp, sz, off = struct.unpack("<BBBBHHII", ico[6 + 16 * i:22 + 16 * i])
        entries.append((w, h, c, pl, bpp, ico[off:off + sz]))

    root_size = 16 + 2 * 8
    icon_dir = root_size
    icon_dir_size = 16 + 8 * n
    grp_dir = icon_dir + icon_dir_size
    grp_dir_size = 16 + 8
    lang_base = grp_dir + grp_dir_size
    lang_size = 16 + 8
    data_ent_base = lang_base + lang_size * (n + 1)
    data_base = data_ent_base + 16 * (n + 1)

    def hdr(count):
        return struct.pack("<IIHHHH", 0, 0, 0, 0, 0, count)

    def ent(a, b):
        return struct.pack("<II", a, b)

    sec = hdr(2) + ent(3, 0x80000000 | icon_dir) + ent(14, 0x80000000 | grp_dir)
    sec += hdr(n) + b"".join(ent(i + 1, 0x80000000 | (lang_base + lang_size * i)) for i in range(n))
    sec += hdr(1) + ent(1, 0x80000000 | (lang_base + lang_size * n))
    for i in range(n + 1):
        sec += hdr(1) + ent(0x409, data_ent_base + 16 * i)
    assert len(sec) == data_ent_base

    pos = data_base
    blobs = []
    for e in entries:
        pad = (8 - pos % 8) % 8
        pos += pad
        blobs.append((pos, pad, e[5]))
        pos += len(e[5])
    pad = (8 - pos % 8) % 8
    pos += pad
    grp_off = pos
    grp = struct.pack("<HHH", 0, 1, n)
    for i, e in enumerate(entries):
        grp += struct.pack("<BBBBHHIH", e[0], e[1], e[2], 0, e[3], e[4], len(e[5]), i + 1)
    ents = [(off, len(b)) for off, _, b in blobs] + [(grp_off, len(grp))]
    for off, ln in ents:
        sec += struct.pack("<IIII", off, ln, 0, 0)
    for off, p, b in blobs:
        sec += b"\0" * p + b
    sec += b"\0" * pad + grp
    assert len(sec) == grp_off + len(grp)

    size = len(sec)
    ptr_sec = 20 + 40
    ptr_rel = ptr_sec + size
    nrel = n + 1
    ptr_sym = ptr_rel + 10 * nrel
    coff = struct.pack("<HHIIIHH", 0x8664, 1, 0, ptr_sym, 1, 0, 0)
    shdr = struct.pack("<8sIIIIIIHHI", b".rsrc", 0, 0, size, ptr_sec, ptr_rel, 0, nrel, 0, 0xC0300040)
    rel = b"".join(struct.pack("<IIH", data_ent_base + 16 * i, 0, 3) for i in range(nrel))
    sym = struct.pack("<8sIhHBB", b".rsrc", 0, 1, 0, 3, 0)
    open(out_path, "wb").write(coff + shdr + sec + rel + sym + struct.pack("<I", 4))


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
