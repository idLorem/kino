import hashlib
import os
import sys
import zipfile


def main(root, out_zip, out_ver):
    names = []
    for d, _, files in os.walk(root):
        for f in files:
            names.append(os.path.relpath(os.path.join(d, f), root).replace("\\", "/"))
    names.sort()
    h = hashlib.sha256()
    for n in names:
        h.update(n.encode())
    h.update(open(os.path.join(root, "main.py"), "rb").read())
    h.update(open(os.path.join(root, "icon.ico"), "rb").read())
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for n in names:
            z.write(os.path.join(root, n), n)
    open(out_ver, "w").write(h.hexdigest()[:12])
    print(len(names), "files", h.hexdigest()[:12])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
