#!/usr/bin/env python3
"""Report whether an OpenSSH private key is passphrase-protected, without
needing the passphrase itself.

Usage: python3 ssh_key_cipher.py <path-to-private-key> [more-paths...]

Prints the cipher name declared in the key's own header. "none" means the
key is unencrypted; anything else (aes256-ctr, aes256-gcm@openssh.com,
chacha20-poly1305@openssh.com, ...) confirms a passphrase is set.

On Windows/git-bash, pass a native C:/... path, not /c/... — the python3
on PATH there may not resolve MSYS-style paths (see the MSYS-path-mangling
pitfall in SKILL.md).
"""
import base64
import sys


def cipher_of(path: str) -> str:
    with open(path) as fh:
        data = fh.read()
    body = "".join(l for l in data.splitlines() if not l.startswith("-----"))
    raw = base64.b64decode(body)
    idx = raw.find(b"openssh-key-v1")
    if idx == -1:
        raise ValueError("not an OpenSSH-format private key")
    after = raw[idx + 15:]  # skip magic + its NUL terminator
    cipher_len = int.from_bytes(after[0:4], "big")
    return after[4:4 + cipher_len].decode()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    for p in sys.argv[1:]:
        try:
            print(f"{p}: {cipher_of(p)}")
        except Exception as e:
            print(f"{p}: ERROR ({e})")
