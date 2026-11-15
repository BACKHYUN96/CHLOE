"""Make isolated APK copies without recompiling DEX/resources/native code.

The binary manifest and META-INF signature/metadata entries change. DEX, assets,
native libraries, resources.arsc and res/ entries are preserved. Inputs must be trusted
APK backups; never use this to update an installed original package. Outputs are
new files. This is experiment packaging, not a reproducible source build.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile

U32 = lambda b, p=0: struct.unpack_from('<I', b, p)[0]
ANDROID = 'http://schemas.android.com/apk/res/android'
NONE = 0xffffffff


def verify_payloads(source, signed):
    def included(name):
        return not name.endswith('/') and name not in ('AndroidManifest.xml', 'stamp-cert-sha256') and not name.startswith('META-INF/')
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(signed) as clone:
        names = {name for name in original.namelist() if included(name)}
        assert names == {name for name in clone.namelist() if included(name)}, 'Added or missing payload entries'
        hashes = {}
        for name in sorted(names):
            payload = original.read(name)
            assert payload == clone.read(name), 'Changed payload: ' + name
            hashes[name] = hashlib.sha256(payload).hexdigest()
    return {'source_sha256': hashlib.sha256(Path(source).read_bytes()).hexdigest(),
            'clone_sha256': hashlib.sha256(Path(signed).read_bytes()).hexdigest(),
            'unchanged_entries': hashes,
            'exceptions': ['AndroidManifest.xml', 'META-INF/* (including version metadata)', 'stamp-cert-sha256 (signing provenance)']}


def chunks(data, start=8):
    while start < len(data):
        kind, header, size = struct.unpack_from('<HHI', data, start)
        assert size >= header >= 8 and start + size <= len(data)
        yield kind, header, data[start:start + size]
        start += size


def length(data, pos, utf8):
    unit = 1 if utf8 else 2
    value = data[pos] if utf8 else struct.unpack_from('<H', data, pos)[0]
    flag = 0x80 if utf8 else 0x8000
    pos += unit
    if value & flag:
        nxt = data[pos] if utf8 else struct.unpack_from('<H', data, pos)[0]
        return ((value & (flag - 1)) << (8 if utf8 else 16)) | nxt, pos + unit
    return value, pos


def patch_manifest(data, package):
    parts = list(chunks(data))
    pool = next(b for t, h, b in parts if t == 1)
    count, styles, flags, offset, style_offset = struct.unpack_from('<5I', pool, 8)
    assert styles == 0, 'Styled manifest strings are unsupported'
    utf8 = bool(flags & 0x100)
    strings = []
    for i in range(count):
        p = offset + U32(pool, 28 + i * 4)
        n, p = length(pool, p, utf8)
        if utf8:
            n, p = length(pool, p, True)
        strings.append(pool[p:p + n * (1 if utf8 else 2)].decode('utf-8' if utf8 else 'utf-16le'))

    def idx(s):
        if s not in strings:
            strings.append(s)
        return strings.index(s)

    resource = next((b for t, h, b in parts if t == 0x180), None)
    resources = [U32(resource, p) for p in range(8, len(resource), 4)] if resource else []
    def resource_name(s, rid):
        i = idx(s)
        resources.extend([0] * max(0, i + 1 - len(resources)))
        assert resources[i] in (0, rid)
        resources[i] = rid
        return i

    resource_name('debuggable', 0x0101000f)
    resource_name('allowBackup', 0x01010280)
    old_package = None
    result = []
    for kind, header, blob in parts:
        if kind in (1, 0x180):
            continue
        if kind == 0x102:
            b = bytearray(blob)
            tag = strings[U32(b, 20)]
            attr_start, attr_size, attr_count = struct.unpack_from('<HHH', b, 24)
            assert attr_size == 20
            attrs = [bytearray(b[16 + attr_start + i * 20:16 + attr_start + (i + 1) * 20]) for i in range(attr_count)]
            for a in attrs:
                name = strings[U32(a, 4)]
                typ = a[15]
                val = strings[U32(a, 16)] if typ == 3 else None
                new = None
                if tag == 'manifest' and name == 'package':
                    old_package = val
                    new = package
                elif old_package and val:
                    if name in ('authorities', 'taskAffinity') or (name == 'name' and tag in ('permission', 'uses-permission')):
                        new = val.replace(old_package, package)
                    elif name in ('name', 'targetActivity') and tag in ('application', 'activity', 'activity-alias', 'provider', 'service', 'receiver'):
                        if val.startswith('.'):
                            new = old_package + val
                        elif '.' not in val:
                            new = old_package + '.' + val
                if new is not None:
                    struct.pack_into('<I', a, 8, idx(new))
                    struct.pack_into('<I', a, 16, idx(new))
            if tag == 'application':
                for name, boolean in [('debuggable', 1), ('allowBackup', 0)]:
                    found = next((a for a in attrs if strings[U32(a, 4)] == name), None)
                    if found is None:
                        # ResXMLTree_attribute: ns, name, rawValue, Res_value.
                        attrs.append(bytearray(struct.pack('<IIIHBBI', idx(ANDROID), idx(name), NONE, 8, 0, 0x12, boolean)))
                    else:
                        struct.pack_into('<I', found, 8, NONE)
                        found[15] = 0x12
                        struct.pack_into('<I', found, 16, boolean)
                # Preserve resource-valued theme/icon and all original component code.
            attrs.sort(key=lambda a: resources[U32(a, 4)] if U32(a, 4) < len(resources) and resources[U32(a, 4)] else 0xffffffff)
            prefix = b[:16 + attr_start]
            struct.pack_into('<H', prefix, 28, len(attrs))
            b = prefix + b''.join(attrs)
            struct.pack_into('<I', b, 4, len(b))
            result.append(bytes(b))
        else:
            result.append(blob)
    assert old_package and package != old_package
    assert (old_package, package) in {
        ('ai.chloe.voicelab.performance', 'ai.chloe.match.chloe'),
        ('com.pocketpalai', 'ai.chloe.match.pocketpal'),
    }, 'Only the two isolated experiment package mappings are supported'
    encoded, offsets = bytearray(), []
    for s in strings:
        offsets.append(len(encoded))
        raw = s.encode('utf-16le')
        n = len(raw) // 2
        assert n < 0x8000
        encoded += struct.pack('<H', n) + raw + b'\0\0'
    encoded += b'\0' * (-len(encoded) % 4)
    start = 28 + 4 * len(strings)
    new_pool = struct.pack('<HHI5I', 1, 28, start + len(encoded), len(strings), 0, flags & ~0x101, start, 0)
    new_pool += struct.pack('<' + 'I' * len(offsets), *offsets) + encoded
    new_map = struct.pack('<HHI', 0x180, 8, 8 + len(resources) * 4) + struct.pack('<' + 'I' * len(resources), *resources)
    body = new_pool + new_map + b''.join(result)
    return struct.pack('<HHI', 3, 8, len(body) + 8) + body


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--package', required=True)
    args = ap.parse_args()
    assert not args.output.exists(), 'Refusing to overwrite output'
    proof = {}
    with zipfile.ZipFile(args.source) as original, zipfile.ZipFile(args.output, 'x') as clone:
        for info in original.infolist():
            if info.filename.startswith('META-INF/'):
                continue
            raw = original.read(info)
            if info.filename == 'AndroidManifest.xml':
                raw = patch_manifest(raw, args.package)
            elif not info.is_dir():
                proof[info.filename] = hashlib.sha256(raw).hexdigest()
            clone.writestr(info, raw)
    with zipfile.ZipFile(args.source) as a, zipfile.ZipFile(args.output) as b:
        assert all(a.read(n) == b.read(n) for n in proof)
    args.output.with_suffix('.proof.json').write_text(json.dumps({'source_sha256': hashlib.sha256(args.source.read_bytes()).hexdigest(), 'package': args.package, 'unchanged_entries': proof}, indent=2), encoding='utf-8')
    print('Preserved entries:', len(proof), args.output.name)


if __name__ == '__main__':
    main()
