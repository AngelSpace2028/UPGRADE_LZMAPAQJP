#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified PAQJP+PJP – Simplified (Lossless, 256 transforms only)
==============================================================
FIXED: find_nearest_prime_around now caps at 255 (was returning 257).
Fast self-test added as menu option 3.
"""

import math, random, decimal, hashlib, base64, heapq, struct, os, tempfile
import re, urllib.request, sys, subprocess, importlib, time
from typing import Optional, List, Tuple, Dict, Callable, Any
from collections import Counter

try:
    import paq
except ImportError:
    paq = None

USE_QUANTUM = False
HAS_QISKIT = False
HAS_ZSTD = False

def install_package(pkg: str) -> bool:
    print(f"Installing {pkg}...")
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install',
                              '--no-input', '--disable-pip-version-check', pkg])
        return True
    except Exception:
        return False

# ---------- Prompt 1: Quantum ----------
try:
    quantum_choice = input("Enable quantum transforms? (y/n) [n]: ").strip().lower()
except EOFError:
    quantum_choice = 'n'
if quantum_choice == 'y':
    try:
        from qiskit import QuantumCircuit
        HAS_QISKIT = True; USE_QUANTUM = True
        print("Quantum transforms ENABLED.")
    except ImportError:
        if install_package('qiskit'):
            try:
                from qiskit import QuantumCircuit
                HAS_QISKIT = True; USE_QUANTUM = True
                print("Quantum transforms ENABLED.")
            except ImportError:
                print("Qiskit failed. Disabled.")
        else:
            print("Qiskit failed. Disabled.")
else:
    print("Quantum transforms disabled.")

# ---------- Prompt 2: Optional backends ----------
try:
    other_choice = input("Install optional backends (mpmath, cython, paq, python-docx)? (y/n) [n]: ").strip().lower()
except EOFError:
    other_choice = 'n'
if other_choice == 'y':
    for pkg in ['mpmath', 'cython', 'paq', 'python-docx']:
        try:
            importlib.import_module(pkg)
            print(f"{pkg} already installed.")
        except ImportError:
            install_package(pkg)

# ---------- Prompt 3: Zstandard (mandatory) ----------
try:
    zstd_choice = input("Install zstandard? (mandatory, y/n) [y]: ").strip().lower()
except EOFError:
    zstd_choice = 'y'
if zstd_choice == 'n':
    print("ERROR: zstandard mandatory. Exiting."); sys.exit(1)
try:
    import zstandard as zstd
    zstd_cctx = zstd.ZstdCompressor(level=22)
    zstd_dctx = zstd.ZstdDecompressor()
    HAS_ZSTD = True
    print("zstandard loaded.")
except ImportError:
    if install_package('zstandard'):
        try:
            import zstandard as zstd
            zstd_cctx = zstd.ZstdCompressor(level=22)
            zstd_dctx = zstd.ZstdDecompressor()
            HAS_ZSTD = True
            print("zstandard installed.")
        except ImportError:
            print("CRITICAL: zstandard failed."); sys.exit(1)
    else:
        print("CRITICAL: install zstandard manually."); sys.exit(1)

PROGNAME = "UnifiedPAQJP+PJP (Single Transforms)"

# ---------- Dictionaries ----------
DICT_DIR = "Dictionaries"
COMBINED_DICTIONARY_FILE = os.path.join(DICT_DIR, "dictionary_combined.txt")

DICTIONARY_FILES = [
    "generated.txt", "eng_news_2005_1M-sentences.txt", "eng_news_2005_1M-words.txt",
    "eng_news_2005_1M-sources.txt", "eng_news_2005_1M-co_n.txt", "eng_news_2005_1M-co_s.txt",
    "eng_news_2005_1M-inv_w_2.txt", "eng_news_2005_1M-inv_w_3.txt", "eng_news_2005_1M-inv_so.txt",
    "eng_news_2005_1M-meta.txt", "Dictionary.txt",
    "the-complete-reference-html-css-fifth-edition.txt",
]
DICTIONARY_URLS = [
    "https://drive.google.com/uc?export=download&id=1u_1dCEl8hhdEug6GwkOxHAuSx_6_Pme9",
    "https://drive.google.com/uc?export=download&id=1pVqNN5JZ2AeOCgRaHkv4Vv6Byr4zK20e",
    "https://drive.google.com/uc?export=download&id=1ZSC-Tn76x8itdN0rCp-Zw17hGudxbjxo",
    "https://drive.google.com/uc?export=download&id=1VB_7tzngs4GxjclSRyRDnxgS8znT2w2S",
    "https://drive.google.com/uc?export=download&id=1KVIRgiMrhCUCqQZJ3UT67ztls2GqGJzz",
    "https://drive.google.com/uc?export=download&id=1Z3Lx6SqL4HWsnmbJCez4kXWRQQhUXWKL",
    "https://drive.google.com/uc?export=download&id=1br2bdRMkZEVVRPKYmC4IIaZuAjxFJE4N",
    "https://drive.google.com/uc?export=download&id=1aE6ubPZiJ8rr3lEVk8fFJYjDQ1y1rU0X",
    "https://drive.google.com/uc?export=download&id=1uro3TZe-t5zPx2Qu2xrTL3lU8N0melk9",
    "https://drive.google.com/uc?export=download&id=1HqsTH1DqpWNpGbn9VtD7-SB6wVqA90R2",
    "https://drive.google.com/uc?export=download&id=1zZ8iMeBC3605NZhuc4UE9jx_w_lZFg5B",
    "https://drive.google.com/uc?export=download&id=1dDdqYDgm7f-smS7KF70Wf0KmyFo-ft1M",
]
MAX_LINE_ENTRIES = 1024

def download_and_merge_dictionaries():
    if not os.path.exists(DICT_DIR):
        os.makedirs(DICT_DIR)
    if os.path.exists(COMBINED_DICTIONARY_FILE):
        print(f"Combined dictionary exists. Skipping download.")
        return True
    all_words = set(); success_count = 0
    for filename, url in zip(DICTIONARY_FILES, DICTIONARY_URLS):
        local_path = os.path.join(DICT_DIR, filename)
        print(f"Downloading {filename} ...")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=20) as response:
                content = response.read()
            if b'<html' in content[:200].lower():
                print(f"  HTML page. Skipping."); continue
            with open(local_path, 'wb') as f: f.write(content)
            with open(local_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    w = line.strip()
                    if not w: continue
                    try:
                        decoded = base64.b64decode(w, validate=True).decode('utf-8')
                        all_words.add(decoded)
                    except Exception:
                        all_words.add(w)
            print(f"  OK ({os.path.getsize(local_path)} bytes)")
            success_count += 1
        except Exception as e:
            print(f"  FAIL: {e}")
            if os.path.exists(local_path): os.remove(local_path)
    if success_count == 0:
        print("No dictionaries downloaded. Proceeding without.")
        return False
    try:
        with open(COMBINED_DICTIONARY_FILE, 'w', encoding='utf-8') as f:
            for word in sorted(all_words): f.write(word + '\n')
        print(f"Merged {len(all_words)} words.")
        return True
    except Exception as e:
        print(f"Write failed: {e}"); return False

# ---------- Constants ----------
PRIMES = [p for p in range(2, 256) if all(p % d != 0 for d in range(2, int(p ** 0.5) + 1))]
PI_DIGITS = [79, 17, 111]

# ★★★ FIXED: caps at 255 so it can never overflow a bytearray ★★★
def find_nearest_prime_around(n: int) -> int:
    """Nearest prime ≤ 255 to n. Never returns > 255."""
    n = n & 0xFF
    if n < 2:
        return 2
    o = 0
    while o < 256:
        c1, c2 = n - o, n + o
        if c1 >= 2 and all(c1 % d != 0 for d in range(2, int(c1 ** 0.5) + 1)):
            return c1
        if c2 <= 255 and all(c2 % d != 0 for d in range(2, int(c2 ** 0.5) + 1)):
            return c2
        o += 1
    return 251

def sha256_8bytes(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()[:8]

def xor_prime_hash(word: str) -> bytes:
    prime = 2147483647
    total = sum(ord(c) for c in word)
    transformed = total ^ prime
    return transformed.to_bytes(8, 'big')

_CONST_DIAPASON_ITER_CODE = [
    (2, 0b10), (2, 0b11), (3, 0b010), (3, 0b011),
    (4, 0b0010), (4, 0b0011), (5, 0b00010), (5, 0b00011),
    (6, 0b000010), (6, 0b000011), (7, 0b0000010), (7, 0b0000011),
    (8, 0b00000010), (8, 0b00000011), (9, 0b000000010), (9, 0b000000011),
]
_CONST_DIAPASON_ITER_DECODE = {}
for nibble, (length, bits) in enumerate(_CONST_DIAPASON_ITER_CODE):
    _CONST_DIAPASON_ITER_DECODE[(length, bits)] = nibble

ALPHABET_6BIT = ("ABCDEFGHIJKLMNOPQRSTUVWXYZ" "abcdefghijklmnopqrstuvwxyz"
                 "0123456789" " \n")
assert len(ALPHABET_6BIT) == 64
CHAR_TO_6BIT = {ch: i for i, ch in enumerate(ALPHABET_6BIT)}
SIXBIT_TO_CHAR = {i: ch for ch, i in CHAR_TO_6BIT.items()}

PAQ_STATE_TABLE = [
    [1,2,0,0],[3,5,0,1],[4,6,2,0],[7,10,0,2],[8,12,3,0],[9,13,1,1],[11,14,0,3],
    [15,19,4,0],[16,23,2,1],[17,24,2,1],[18,25,2,1],[20,27,1,2],[21,28,1,2],
    [22,29,1,2],[26,30,0,4],[31,33,5,0],[32,34,3,1],[35,37,1,3],[36,38,1,3],
    [39,42,0,5],[40,43,4,1],[41,44,2,2],[45,48,1,4],[46,49,1,4],[47,50,1,4],
    [51,52,0,6],[53,55,6,0],[54,56,4,1],[57,59,2,3],[58,60,2,3],[61,63,0,7],
    [62,64,5,1],[65,66,3,2],[67,69,1,5],[68,70,1,5],[71,73,0,8],[72,74,6,1],
    [75,76,4,2],[77,78,2,4],[79,80,2,4],[81,82,0,9],[83,84,7,1],[85,86,5,2],
    [87,88,3,3],[89,90,1,6],[91,92,0,10],[93,94,8,1],[95,96,6,2],[97,98,4,3],
    [99,100,2,5],[101,102,0,11],[103,104,9,1],[105,106,7,2],[107,108,5,3],
    [109,110,3,4],[111,112,1,7],[113,114,0,12],[115,116,10,1],[117,118,8,2],
    [119,120,6,3],[121,122,4,4],[123,124,2,6],[125,126,0,13],[127,128,11,1],
    [129,130,9,2],[131,132,7,3],[133,134,5,4],[135,136,3,5],[137,138,1,8],
    [139,140,0,14],[141,142,12,1],[143,144,10,2],[145,146,8,3],[147,148,6,4],
    [149,150,4,5],[151,152,2,7],[153,154,0,15],[155,156,13,1],[157,158,11,2],
    [159,160,9,3],[161,162,7,4],[163,164,5,5],[165,166,3,6],[167,168,1,9],
    [169,170,0,16],[171,172,14,1],[173,174,12,2],[175,176,10,3],[177,178,8,4],
    [179,180,6,5],[181,182,4,6],[183,184,2,8],[185,186,0,17],[187,188,15,1],
    [189,190,13,2],[191,192,11,3],[193,194,9,4],[195,196,7,5],[197,198,5,6],
    [199,200,3,7],[201,202,1,10],[203,204,0,18],[205,206,16,1],[207,208,14,2],
    [209,210,12,3],[211,212,10,4],[213,214,8,5],[215,216,6,6],[217,218,4,7],
    [219,220,2,9],[221,222,0,19],[223,224,17,1],[225,226,15,2],[227,228,13,3],
    [229,230,11,4],[231,232,9,5],[233,234,7,6],[235,236,5,7],[237,238,3,8],
    [239,240,1,11],[241,242,0,20],[243,244,18,1],[245,246,16,2],[247,248,14,3],
    [249,250,12,4],[251,252,10,5],[253,254,8,6],[255,255,6,7],
]

class TransformError(Exception): pass
class DecompressionError(Exception): pass

def mod_inv(a: int, m: int) -> Optional[int]:
    if a == 0: return None
    m0 = m; y = 0; x = 1
    if m == 1: return 0
    while a > 1:
        q = a // m; t = m; m = a % m; a = t
        t = y; y = x - q * y; x = t
    if x < 0: x = x + m0
    return x

class UnifiedCompressor:
    ULTRA_TIME_LIMIT = 300
    QUANTUM_QUBITS = 8
    WINDOW_SIZE = 2048
    MIN_MATCH = 3
    MAX_MATCH = 2048
    MAX_DIST = 2048

    def __init__(self):
        download_and_merge_dictionaries()
        self.PI_DIGITS = PI_DIGITS.copy()
        self.seed_tables = self._gen_seed_tables(num=126, size=40, seed=42)
        self.fibonacci = self._gen_fib(100)
        self.PI_STR = "3.14159265358979323846264338327950288419716939937510"
        self.repeat_count = 100
        self.mod_state_table = [[(v - 400) & 0xFF for v in row] for row in PAQ_STATE_TABLE]
        self._build_mask_46()
        self._build_transform_maps()
        self.static_dict, self.word_to_index = self._load_static_dictionary()
        self.line_dict, self.line_to_index = self._load_line_dictionary()
        self.quantum_transforms_built = False
        if USE_QUANTUM and HAS_QISKIT:
            self._precompute_quantum_transforms()

    def set_quantum_qubits(self, q: int):
        if not USE_QUANTUM or not HAS_QISKIT:
            print("Quantum not enabled."); return
        if q < 1 or q > 49:
            print("Qubits must be 1-49."); return
        self.QUANTUM_QUBITS = q
        self.quantum_transforms_built = False
        self._precompute_quantum_transforms()
        print(f"Quantum qubits = {q}.")

    def get_quantum_variation_count(self) -> int:
        if USE_QUANTUM and HAS_QISKIT:
            return 1 << self.QUANTUM_QUBITS
        return 0

    def _build_mask_46(self):
        base = [1, 2, 4, 8, 16, 32, 64, 128, 3, 6]
        self.mask_46 = [(b - 10) & 0xFF for b in base] * 10

    def get_pi_digits(self, n: int) -> str:
        if n < 1: return ""
        return self.PI_STR[2:2 + n]

    def find_lossless_k(self, n: int):
        if n < 1: return 0, True
        true_digits = self.get_pi_digits(n)
        true_scaled = int(self.PI_STR.replace('.', '')[:n + 1])
        D = 16777216
        decimal.getcontext().prec = 50
        pi_dec = decimal.Decimal(self.PI_STR)
        k_float = (pi_dec - 3) * D
        k_candidate = int(round(k_float))
        k_candidate = max(0, min(k_candidate, D - 1))
        approx_scaled = (3 * 10 ** n * D + k_candidate * 10 ** n) // D
        return k_candidate, approx_scaled == true_scaled

    def to_bin(self, value: int, bits: int) -> str:
        return format(value, 'b').zfill(bits)

    def get_bit_size(self, k: int) -> int:
        return 23 if k <= 0x7FFFFF else 25

    def transform_17(self, data: bytes) -> bytes:
        if not data: return b''
        k, _ = self.find_lossless_k(7)
        bits_used = self.get_bit_size(k)
        bit_str = self.to_bin(k, bits_used)
        mask_bytes = []
        for i in range(0, len(bit_str), 8):
            bb = bit_str[i:i + 8]
            if len(bb) < 8: bb = bb.ljust(8, '0')
            mask_bytes.append(int(bb, 2))
        mask = bytes(mask_bytes)
        if not mask: return data
        t = bytearray(data)
        for i in range(len(t)): t[i] ^= mask[i % len(mask)]
        return bytes(t)
    reverse_transform_17 = transform_17

    def get_basel_digits(self, n: int) -> str:
        decimal.getcontext().prec = n + 5
        pi = decimal.Decimal(self.PI_STR)
        basel = (pi * pi) / decimal.Decimal(6)
        return str(basel).replace('.', '')[:n]

    def get_one_over_e_digits(self, n: int) -> str:
        decimal.getcontext().prec = n + 5
        e = decimal.Decimal(1).exp()
        inv_e = decimal.Decimal(1) / e
        return str(inv_e).replace('.', '')[:n]

    def get_5e_digits(self, n: int) -> str:
        decimal.getcontext().prec = n + 5
        e = decimal.Decimal(1).exp()
        five_e = decimal.Decimal(5) * e
        return str(five_e).replace('.', '')[:n]

    def _gen_seed_tables(self, num=126, size=40, seed=42):
        random.seed(seed)
        return [[random.randint(5, 255) for _ in range(size)] for _ in range(num)]

    def _gen_fib(self, n):
        a, b = 0, 1; res = [a, b]
        for _ in range(2, n): a, b = b, a + b; res.append(b)
        return res

    def get_seed(self, idx: int, val: int) -> int:
        if 0 <= idx < len(self.seed_tables):
            return self.seed_tables[idx][val % 40]
        return 0

    def _append_bits(self, bitlist, value, count):
        for i in range(count - 1, -1, -1): bitlist.append((value >> i) & 1)

    def _read_bits(self, bits, pos, count) -> int:
        val = 0
        for i in range(count):
            if pos + i >= len(bits): return 0
            val = (val << 1) | bits[pos + i]
        return val

    # ---- Transform 00 ----
    def transform_00(self, data: bytes) -> bytes:
        if not data: return struct.pack('>I', 0)
        best_result = None; best_length = float('inf'); best_shifts = []
        MAX_PASSES = 10; current = bytearray(data); applied = []
        original = bytes(data)
        for _ in range(MAX_PASSES):
            best_shift = 0; best_shifted = current; best_score = float('-inf')
            for shift in range(256):
                tmp = bytearray(current)
                for j in range(len(tmp)): tmp[j] = (tmp[j] + shift) % 256
                score = 0; i = 0
                while i < len(tmp):
                    val = tmp[i]; run = 1; i += 1
                    while i < len(tmp) and tmp[i] == val: run += 1; i += 1
                    score += run * run
                if score > best_score:
                    best_score = score; best_shifted = tmp; best_shift = shift
            applied.append(best_shift)
            rle = self._apply_rle_to_shifted(best_shifted, best_shift)
            dec = self._rle_decode(rle)
            if dec is not None:
                test = bytearray(dec)
                for s in applied:
                    for j in range(len(test)): test[j] = (test[j] - s) % 256
                if bytes(test) == original and len(rle) < best_length:
                    best_length = len(rle); best_result = rle; best_shifts = applied.copy()
            current = best_shifted
            if len(rle) >= len(data): break
        if best_result is None or best_length >= len(data):
            return struct.pack('>I', len(data)) + bytes([0]) + data
        header = bytearray()
        header.extend(struct.pack('>I', len(data)))
        header.append(len(best_shifts))
        header.extend(best_shifts)
        return header + best_result

    def _apply_rle_to_shifted(self, shifted, shift):
        bits = []
        self._append_bits(bits, 0b010, 3); self._append_bits(bits, shift, 8)
        i = 0; n = len(shifted)
        while i < n:
            val = shifted[i]; run = 1; i += 1
            while i < n and shifted[i] == val: run += 1; i += 1
            while run >= 13:
                chunk = min(run, 268)
                self._append_bits(bits, 0b1111, 4)
                self._append_bits(bits, chunk - 13, 8)
                self._append_bits(bits, val, 8)
                run -= chunk
            if run == 1:
                self._append_bits(bits, 0b00, 2); self._append_bits(bits, val, 8)
            elif run <= 5:
                self._append_bits(bits, 0b01, 2)
                self._append_bits(bits, run - 2, 2); self._append_bits(bits, val, 8)
            elif run <= 12:
                self._append_bits(bits, 0b10, 2)
                self._append_bits(bits, run - 6, 3); self._append_bits(bits, val, 8)
        pad = (8 - len(bits) % 8) % 8; self._append_bits(bits, 0, pad)
        out = bytearray()
        for j in range(0, len(bits), 8):
            byte = 0
            for k in range(8):
                if j + k < len(bits): byte = (byte << 1) | bits[j + k]
            out.append(byte)
        return bytes(out)

    def reverse_transform_00(self, cdata: bytes) -> bytes:
        if not cdata or cdata == struct.pack('>I', 0): return b''
        if len(cdata) < 4: raise TransformError("RLE reverse: too short")
        orig_len = struct.unpack('>I', cdata[:4])[0]; cdata = cdata[4:]
        if not cdata: return b''
        if cdata[0] == 0: return cdata[1:orig_len+1]
        num_passes = cdata[0]
        if num_passes == 0 or len(cdata) < 1 + num_passes:
            raise TransformError("Invalid RLE header")
        shifts = list(cdata[1:1 + num_passes])
        rle_data = cdata[1 + num_passes:]
        decoded = self._rle_decode(rle_data)
        if decoded is None: raise TransformError("RLE decode failed")
        current = bytearray(decoded[:orig_len])
        for shift in reversed(shifts):
            for i in range(len(current)): current[i] = (current[i] - shift) % 256
        return bytes(current)

    def _rle_decode(self, data: bytes):
        if not data: return None
        bits = []
        for b in data:
            for i in range(7, -1, -1): bits.append((b >> i) & 1)
        pos = 0; nbits = len(bits)
        if nbits < 11: return None
        marker = self._read_bits(bits, pos, 3); pos += 3
        if marker != 0b010: return None
        pos += 8
        out = bytearray()
        while pos < nbits:
            if pos + 2 > nbits: break
            prefix = self._read_bits(bits, pos, 2); pos += 2
            if prefix == 0b00:
                if pos + 8 > nbits: break
                run = 1
            elif prefix == 0b01:
                if pos + 2 + 8 > nbits: break
                run = 2 + self._read_bits(bits, pos, 2); pos += 2
            elif prefix == 0b10:
                if pos + 3 + 8 > nbits: break
                run = 6 + self._read_bits(bits, pos, 3); pos += 3
            else:
                if pos + 2 + 8 + 8 > nbits: break
                if self._read_bits(bits, pos, 2) != 0b11: return None
                pos += 2
                run = 13 + self._read_bits(bits, pos, 8); pos += 8
            if pos + 8 > nbits: break
            val = self._read_bits(bits, pos, 8); pos += 8
            out.extend([val] * run)
        for i in range(pos, nbits):
            if bits[i] != 0: return None
        return out

    # ---- Transforms 01-21 ----
    def transform_01(self, d):
        t = bytearray(d); r = self.repeat_count
        for prime in PRIMES:
            xv = prime if prime == 2 else max(1, math.ceil(prime * 4096 / 28672))
            for _ in range(r):
                for i in range(0, len(t), 3):
                    if i < len(t): t[i] ^= xv
        return bytes(t)
    reverse_transform_01 = transform_01

    def transform_02(self, d):
        if not d: return b'\x00'
        t = bytearray(d)
        pi = (len(d) + sum(d)) % 256
        pv = self._get_pattern(4, pi)
        for i in range(1, len(t), 4):
            if i < len(t): t[i] ^= pv[i % len(pv)]
        return bytes([pi]) + bytes(t)
    def reverse_transform_02(self, d):
        if d == b'\x00': return b''
        if len(d) < 2: raise TransformError("T02 too short")
        pi = d[0]; t = bytearray(d[1:])
        pv = self._get_pattern(4, pi)
        for i in range(1, len(t), 4):
            if i < len(t): t[i] ^= pv[i % len(pv)]
        return bytes(t)

    def transform_03(self, d):
        if not d: return b'\x00'
        t = bytearray(d)
        rot = (len(d) * 13 + sum(d)) % 8
        if rot == 0: rot = 1
        for i in range(2, len(t), 5):
            if i < len(t): t[i] = ((t[i] << rot) | (t[i] >> (8 - rot))) & 0xFF
        return bytes([rot]) + bytes(t)
    def reverse_transform_03(self, d):
        if d == b'\x00': return b''
        if len(d) < 2: raise TransformError("T03 too short")
        rot = d[0]; t = bytearray(d[1:])
        for i in range(2, len(t), 5):
            if i < len(t): t[i] = ((t[i] >> rot) | (t[i] << (8 - rot))) & 0xFF
        return bytes(t)

    def transform_04(self, d):
        t = bytearray(d); r = self.repeat_count
        for _ in range(r):
            for i in range(len(t)): t[i] = (t[i] - (i % 256)) % 256
        return bytes(t)
    def reverse_transform_04(self, d):
        t = bytearray(d); r = self.repeat_count
        for _ in range(r):
            for i in range(len(t)): t[i] = (t[i] + (i % 256)) % 256
        return bytes(t)

    def transform_05(self, d, s=3):
        return bytes(((b << s) | (b >> (8 - s))) & 0xFF for b in d)
    def reverse_transform_05(self, d, s=3):
        return bytes(((b >> s) | (b << (8 - s))) & 0xFF for b in d)

    def transform_06(self, d, sd=42):
        random.seed(sd); sub = list(range(256)); random.shuffle(sub)
        return bytes(sub[b] for b in d)
    def reverse_transform_06(self, d, sd=42):
        random.seed(sd); sub = list(range(256)); random.shuffle(sub)
        inv = [0]*256
        for i in range(256): inv[sub[i]] = i
        return bytes(inv[b] for b in d)

    def transform_07(self, d):
        t = bytearray(d); r = self.repeat_count
        sh = len(d) % len(self.PI_DIGITS)
        pi_rot = self.PI_DIGITS[sh:] + self.PI_DIGITS[:sh]
        sz = len(d) % 256
        for i in range(len(t)): t[i] ^= sz
        for _ in range(r):
            for i in range(len(t)): t[i] ^= pi_rot[i % len(pi_rot)]
        return bytes(t)
    reverse_transform_07 = transform_07

    def transform_08(self, d):
        t = bytearray(d); r = self.repeat_count
        sh = len(d) % len(self.PI_DIGITS)
        pi_rot = self.PI_DIGITS[sh:] + self.PI_DIGITS[:sh]
        p = find_nearest_prime_around(len(d) % 256)
        for i in range(len(t)): t[i] ^= p
        for _ in range(r):
            for i in range(len(t)): t[i] ^= pi_rot[i % len(pi_rot)]
        return bytes(t)
    reverse_transform_08 = transform_08

    def transform_09(self, d):
        t = bytearray(d); r = self.repeat_count
        sh = len(d) % len(self.PI_DIGITS)
        pi_rot = self.PI_DIGITS[sh:] + self.PI_DIGITS[:sh]
        p = find_nearest_prime_around(len(d) % 256)
        seed = self.get_seed(len(d) % len(self.seed_tables), len(d))
        for i in range(len(t)): t[i] ^= (p ^ seed) & 0xFF
        for _ in range(r):
            for i in range(len(t)): t[i] ^= pi_rot[i % len(pi_rot)] ^ (i % 256)
        return bytes(t)
    reverse_transform_09 = transform_09

    def transform_10(self, data):
        if not data: return b'\x00'
        cnt = sum(1 for i in range(len(data)-1) if data[i:i+2] == b'X1')
        n = (((cnt * 2) + 1) // 3) * 3 % 256
        t = bytearray(data)
        for i in range(len(t)): t[i] ^= n
        return bytes([n]) + bytes(t)
    def reverse_transform_10(self, data):
        if len(data) < 1: raise TransformError("T10 too short")
        n = data[0]; t = bytearray(data[1:])
        for i in range(len(t)): t[i] ^= n
        return bytes(t)

    def transform_11(self, data):
        if not data: return b''
        t = bytearray(data); L = len(t)
        for i in range(L):
            fi = (i + L) % len(self.fibonacci)
            fv = self.fibonacci[fi] % 256
            pv = (i * 13 + L * 17) % 256
            t[i] ^= (fv ^ pv) % 256
        return bytes(t)
    reverse_transform_11 = transform_11

    def transform_12(self, data):
        t = bytearray(data)
        for i in range(len(t)): t[i] ^= self.fibonacci[i % len(self.fibonacci)] % 256
        return bytes(t)
    reverse_transform_12 = transform_12

    def transform_13(self, d):
        if not d: return b'\x00'
        repeats = self._calculate_repeats(d)
        cv = len(d) % 256; primes = []
        for _ in range(repeats):
            cv = find_nearest_prime_around(cv); primes.append(cv)
        t = bytearray(d); xv = primes[-1] if primes else 0
        for i in range(len(t)): t[i] ^= xv
        return bytes([(repeats - 1) % 256]) + bytes(t)
    def reverse_transform_13(self, d):
        if d == b'\x00': return b''
        if len(d) < 2: raise TransformError("T13 too short")
        rb = d[0]; repeats = (rb + 1) % 256
        if repeats == 0: repeats = 256
        t = bytearray(d[1:]); cv = len(t) % 256; primes = []
        for _ in range(repeats):
            cv = find_nearest_prime_around(cv); primes.append(cv)
        xv = primes[-1] if primes else 0
        for i in range(len(t)): t[i] ^= xv
        return bytes(t)

    def transform_14(self, d):
        if not d: return b'\x00'
        return d + bytes([sum(d) % 256])
    def reverse_transform_14(self, d):
        if not d: raise TransformError("T14 too short")
        return d[:-1]

    def transform_15(self, d):
        if not d: return b'\x00'
        t = bytearray(d); pi = len(d) % 256
        pv = self._get_pattern(3, pi)
        for i in range(0, len(t), 3):
            if i < len(t): t[i] = (t[i] + pv[i % len(pv)]) % 256
        return bytes([pi]) + bytes(t)
    def reverse_transform_15(self, d):
        if d == b'\x00': return b''
        if len(d) < 2: raise TransformError("T15 too short")
        pi = d[0]; t = bytearray(d[1:])
        pv = self._get_pattern(3, pi)
        for i in range(0, len(t), 3):
            if i < len(t): t[i] = (t[i] - pv[i % len(pv)]) % 256
        return bytes(t)

    def transform_16(self, data):
        if not data: return b''
        xv = (len(data) * 7 + 13) % 256
        return bytes(b ^ xv for b in data)
    reverse_transform_16 = transform_16

    def transform_18(self, data):
        if not data: return b''
        digits = self.get_basel_digits(max(10, len(data)//2 + 5))
        mask = bytes(int(digits[i:i+2]) % 256 for i in range(0, len(digits), 2))
        t = bytearray(data)
        for i in range(len(t)): t[i] ^= mask[i % len(mask)]
        return bytes(t)
    reverse_transform_18 = transform_18

    def transform_19(self, data):
        if not data: return b''
        digits = self.get_one_over_e_digits(max(10, len(data)//2 + 5))
        mask = bytes(int(digits[i:i+2]) % 256 for i in range(0, len(digits), 2))
        t = bytearray(data)
        for i in range(len(t)): t[i] ^= mask[i % len(mask)]
        return bytes(t)
    reverse_transform_19 = transform_19

    def transform_20(self, data):
        if not data: return b''
        digits = self.get_5e_digits(max(10, len(data)//2 + 5))
        mask = bytes(int(digits[i:i+2]) % 256 for i in range(0, len(digits), 2))
        t = bytearray(data)
        for i in range(len(t)): t[i] ^= mask[i % len(mask)]
        return bytes(t)
    reverse_transform_20 = transform_20

    def transform_21(self, data):
        if not data: return b''
        t = bytearray(data)
        for i in range(len(t)): t[i] = (t[i] + 255) % 256
        return bytes(t)
    def reverse_transform_21(self, data):
        if not data: return b''
        t = bytearray(data)
        for i in range(len(t)): t[i] = (t[i] - 255) % 256
        return bytes(t)

    # ---- 22-27 ----
    def transform_22(self, data): return base64.b64encode(data)
    def reverse_transform_22(self, data):
        try: return base64.b64decode(data, validate=False)
        except Exception as e: raise TransformError(f"b64: {e}")

    def transform_23(self, data: bytes) -> bytes:
        if not data: return b'\x00'
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            return b'\x00' + data
        tokens = re.split(r'([A-Za-z0-9_]+)', text)
        word_list = []; word_to_idx = {}; token_stream = []
        for i, tok in enumerate(tokens):
            if i % 2 == 1:
                wb = tok.encode('utf-8')
                idx = word_to_idx.get(wb)
                if idx is None:
                    idx = len(word_list); word_to_idx[wb] = idx; word_list.append(wb)
                token_stream.append((1, idx))
            else:
                token_stream.append((0, tok.encode('utf-8')))
        out = bytearray()
        out.append(1)
        out += struct.pack('>I', len(word_list))
        for wb in word_list:
            out += struct.pack('>I', len(wb)); out += wb
        for typ, payload in token_stream:
            if typ == 1:
                out += b'\x01'; out += struct.pack('>I', payload)
            else:
                out += b'\x00'; out += struct.pack('>I', len(payload)); out += payload
        tokenized = bytes(out)
        try:
            if self.reverse_transform_23(tokenized) == data:
                return tokenized
        except Exception:
            pass
        return b'\x00' + data

    def reverse_transform_23(self, data: bytes) -> bytes:
        if not data: return b''
        flag = data[0]
        if flag == 0: return data[1:]
        if flag != 1: raise TransformError(f"T23 flag {flag}")
        pos = 1
        if len(data) < pos + 4: raise TransformError("T23 too short")
        num_words = struct.unpack('>I', data[pos:pos+4])[0]; pos += 4
        word_list = []
        for _ in range(num_words):
            if pos + 4 > len(data): raise TransformError("T23 trunc")
            wlen = struct.unpack('>I', data[pos:pos+4])[0]; pos += 4
            if pos + wlen > len(data): raise TransformError("T23 trunc word")
            word_list.append(data[pos:pos+wlen]); pos += wlen
        out = bytearray()
        while pos < len(data):
            typ = data[pos]; pos += 1
            if typ == 1:
                if pos + 4 > len(data): raise TransformError("T23 idx trunc")
                idx = struct.unpack('>I', data[pos:pos+4])[0]; pos += 4
                if idx >= len(word_list): raise TransformError("T23 idx oob")
                out += word_list[idx]
            elif typ == 0:
                if pos + 4 > len(data): raise TransformError("T23 lit trunc")
                ll = struct.unpack('>I', data[pos:pos+4])[0]; pos += 4
                if pos + ll > len(data): raise TransformError("T23 lit trunc")
                out += data[pos:pos+ll]; pos += ll
            else:
                raise TransformError(f"T23 typ {typ}")
        return bytes(out)

    def transform_24(self, data): return self.transform_23(data)
    def reverse_transform_24(self, data): return self.reverse_transform_23(data)

    def _split_text_into_chunks(self, text, level='all'):
        if level == 'paragraph': return re.split(r'(\n\n)', text)
        if level == 'line': return re.split(r'(\n)', text)
        if level == 'sentence': return re.split(r'([.!?]+)', text)
        if level == 'word': return re.split(r'(\s+|\b)', text)
        chunks = []
        for i, para in enumerate(re.split(r'(\n\n)', text)):
            if i % 2 == 1: chunks.append(para); continue
            for j, line in enumerate(re.split(r'(\n)', para)):
                if j % 2 == 1: chunks.append(line); continue
                for k, sent in enumerate(re.split(r'([.!?]+)', line)):
                    if k % 2 == 1: chunks.append(sent); continue
                    chunks.extend(re.split(r'(\s+|\b)', sent))
        return chunks

    def _dynamic_dict_tokenize(self, data, index_bytes=3):
        try: text = data.decode('utf-8')
        except Exception: return b'\x00' + data
        chunks = self._split_text_into_chunks(text, 'all')
        freq = Counter(chunks)
        sc = sorted(freq.keys(), key=lambda x: (-freq[x], -len(x), x))
        c2i = {ch: i for i, ch in enumerate(sc)}
        ne = len(sc)
        if index_bytes == 2 and ne > 65535: index_bytes = 3
        if index_bytes == 3 and ne > 16777215: index_bytes = 8
        header = bytearray(); header.append(index_bytes); header += struct.pack('>I', ne)
        for chunk in sc:
            cb = chunk.encode('utf-8')
            header += struct.pack('>I', len(cb)); header += cb
        ts = bytearray()
        for chunk in chunks:
            idx = c2i[chunk]
            if index_bytes == 2: ts += struct.pack('>H', idx)
            elif index_bytes == 3: ts += struct.pack('>I', idx)[1:4]
            else: ts += struct.pack('>Q', idx)
        return bytes(header) + bytes(ts)

    def _dynamic_dict_detokenize(self, data):
        if not data: return b''
        if data[0] == 0: return data[1:]
        index_bytes = data[0]
        if index_bytes not in (2, 3, 8): raise TransformError(f"dict ib {index_bytes}")
        pos = 1
        if pos + 4 > len(data): raise TransformError("dict trunc")
        ne = struct.unpack('>I', data[pos:pos+4])[0]; pos += 4
        dictionary = []
        for _ in range(ne):
            if pos + 4 > len(data): raise TransformError("dict trunc")
            cl = struct.unpack('>I', data[pos:pos+4])[0]; pos += 4
            if pos + cl > len(data): raise TransformError("dict trunc")
            dictionary.append(data[pos:pos+cl].decode('utf-8')); pos += cl
        tokens = []
        while pos < len(data):
            if index_bytes == 2:
                if pos + 2 > len(data): raise TransformError("dict trunc")
                idx = struct.unpack('>H', data[pos:pos+2])[0]; pos += 2
            elif index_bytes == 3:
                if pos + 3 > len(data): raise TransformError("dict trunc")
                idx = struct.unpack('>I', b'\x00' + data[pos:pos+3])[0]; pos += 3
            else:
                if pos + 8 > len(data): raise TransformError("dict trunc")
                idx = struct.unpack('>Q', data[pos:pos+8])[0]; pos += 8
            if idx >= len(dictionary): raise TransformError(f"dict idx {idx}")
            tokens.append(dictionary[idx])
        return ''.join(tokens).encode('utf-8')

    def transform_25(self, data): return self._dynamic_dict_tokenize(data, 3)
    def reverse_transform_25(self, data): return self._dynamic_dict_detokenize(data)

    def transform_26(self, data):
        if not data: return b''
        secret = b"PJP_TRANSFORM26_SECRET"
        result = bytearray()
        for idx in range(0, len(data), 1024):
            chunk = data[idx:idx+1024]
            bn = idx // 1024
            h = hashlib.sha256(secret + struct.pack(">Q", bn)).digest()
            m = (h * ((len(chunk) // len(h)) + 1))[:len(chunk)]
            result.extend(a ^ b for a, b in zip(chunk, m))
        return bytes(result)
    reverse_transform_26 = transform_26

    def transform_27(self, data):
        try: text = data.decode('utf-8')
        except UnicodeDecodeError: return b'\x00' + data
        for ch in text:
            if ch not in CHAR_TO_6BIT: return b'\x00' + data
        bits = []
        for ch in text:
            v = CHAR_TO_6BIT[ch]
            for i in range(5, -1, -1): bits.append((v >> i) & 1)
        pad = (8 - len(bits) % 8) % 8; bits.extend([0] * pad)
        out = bytearray()
        for i in range(0, len(bits), 8):
            byte = 0
            for j in range(8): byte = (byte << 1) | bits[i + j]
            out.append(byte)
        return b'\x01' + struct.pack('<I', len(text)) + bytes(out)
    def reverse_transform_27(self, data):
        if len(data) < 1: raise TransformError("T27 too short")
        flag = data[0]
        if flag == 0: return data[1:]
        if flag != 1: raise TransformError(f"T27 flag {flag}")
        payload = data[1:]
        if len(payload) < 4: raise TransformError("T27 short")
        nc = struct.unpack('<I', payload[:4])[0]
        packed = payload[4:]
        nb = (nc * 6 + 7) // 8
        if len(packed) != nb: raise TransformError("T27 mismatch")
        pb = (8 - (nc * 6) % 8) % 8
        if pb > 0 and packed:
            m = (1 << pb) - 1
            if (packed[-1] & m) != 0: raise TransformError("T27 pad")
        bits = []
        for b in packed:
            for i in range(7, -1, -1): bits.append((b >> i) & 1)
        chars = []
        for i in range(nc):
            v = 0
            for j in range(6): v = (v << 1) | bits[i*6 + j]
            if v >= 64: raise TransformError(f"T27 v {v}")
            chars.append(SIXBIT_TO_CHAR[v])
        return ''.join(chars).encode('utf-8')

    # ---- 28-30 ----
    def transform_28(self, data):
        if not data: return b'\x00'
        pl = (3 - len(data) % 3) % 3
        padded = data + b'\x00' * pl
        out = bytearray([pl])
        for i in range(0, len(padded), 3):
            v = int.from_bytes(padded[i:i+3], 'little')
            bi = i // 3; k = (bi * 65537 + 12345) & 0xFFFF
            out.extend(((v - k) % (1 << 24)).to_bytes(3, 'little'))
        return bytes(out)
    def reverse_transform_28(self, data):
        if data == b'\x00': return b''
        if not data: raise TransformError("T28 empty")
        pl = data[0]; payload = data[1:]
        if len(payload) % 3 != 0: raise TransformError("T28 not mult of 3")
        out = bytearray()
        for i in range(0, len(payload), 3):
            v = int.from_bytes(payload[i:i+3], 'little')
            bi = i // 3; k = (bi * 65537 + 12345) & 0xFFFF
            out.extend(((v + k) % (1 << 24)).to_bytes(3, 'little'))
        if pl > 0: out = out[:-pl]
        return bytes(out)

    def _find_best_16bit_key(self, data, time_limit=60.0):
        if len(data) < 3: return 0
        pl = (3 - len(data) % 3) % 3
        padded = data + b'\x00' * pl
        vals = [int.from_bytes(padded[i:i+3], 'little') for i in range(0, len(padded), 3)]
        st = time.time()
        bk, bc = 0, float('inf')
        for k in range(65536):
            if k % 4096 == 0 and time.time() - st > time_limit: break
            tr = [((v - k) & 0xFFFFFF) for v in vals]
            m = sum(tr) // len(tr)
            c = sum(abs(t - m) for t in tr)
            if c < bc:
                bc = c; bk = k
                if c == 0: break
        return bk

    def transform_29(self, data):
        if not data: return b'\x00'
        k = self._find_best_16bit_key(data)
        pl = (3 - len(data) % 3) % 3
        padded = data + b'\x00' * pl
        out = bytearray([pl]) + k.to_bytes(2, 'little')
        for i in range(0, len(padded), 3):
            v = int.from_bytes(padded[i:i+3], 'little')
            out.extend(((v - k) % (1 << 24)).to_bytes(3, 'little'))
        return bytes(out)
    def reverse_transform_29(self, data):
        if data == b'\x00': return b''
        if len(data) < 3: raise TransformError("T29 short")
        pl = data[0]; k = int.from_bytes(data[1:3], 'little')
        payload = data[3:]
        if len(payload) % 3 != 0: raise TransformError("T29 not mult of 3")
        out = bytearray()
        for i in range(0, len(payload), 3):
            v = int.from_bytes(payload[i:i+3], 'little')
            out.extend(((v + k) % (1 << 24)).to_bytes(3, 'little'))
        if pl > 0: out = out[:-pl]
        return bytes(out)

    def _find_best_24bit_key_heuristic(self, data):
        if len(data) < 3: return 0
        pl = (3 - len(data) % 3) % 3
        padded = data + b'\x00' * pl
        vals = [int.from_bytes(padded[i:i+3], 'little') for i in range(0, len(padded), 3)]
        mean = sum(vals) // len(vals)
        sv = sorted(vals); med = sv[len(sv)//2]
        cands = set()
        for base in [mean, med]:
            for off in [0, 1, -1, 10, -10, 100, -100, 1000, -1000]:
                cands.add((base + off) % (1 << 24))
        rng = random.Random(42)
        for _ in range(10): cands.add(rng.randint(0, (1 << 24) - 1))
        bk, bc = 0, float('inf')
        for k in cands:
            tr = [((v - k) & 0xFFFFFF) for v in vals]
            m = sum(tr) // len(tr)
            c = sum(abs(t - m) for t in tr)
            if c < bc: bc = c; bk = k
        return bk

    def transform_30(self, data):
        if not data: return b'\x00'
        k = self._find_best_24bit_key_heuristic(data)
        pl = (3 - len(data) % 3) % 3
        padded = data + b'\x00' * pl
        out = bytearray([pl]) + k.to_bytes(3, 'little')
        for i in range(0, len(padded), 3):
            v = int.from_bytes(padded[i:i+3], 'little')
            out.extend(((v - k) % (1 << 24)).to_bytes(3, 'little'))
        return bytes(out)
    def reverse_transform_30(self, data):
        if data == b'\x00': return b''
        if len(data) < 4: raise TransformError("T30 short")
        pl = data[0]; k = int.from_bytes(data[1:4], 'little')
        payload = data[4:]
        if len(payload) % 3 != 0: raise TransformError("T30 not mult of 3")
        out = bytearray()
        for i in range(0, len(payload), 3):
            v = int.from_bytes(payload[i:i+3], 'little')
            out.extend(((v + k) % (1 << 24)).to_bytes(3, 'little'))
        if pl > 0: out = out[:-pl]
        return bytes(out)

    def transform_31(self, data): return data
    reverse_transform_31 = transform_31
    def transform_32(self, data): return data
    reverse_transform_32 = transform_32

    # ---- PAQJP 33-40 ----
    def _paqjp_transform_23(self, data):
        if not data: return b'\x00\x00\x00\x00\x00'
        bits = []
        for byte in data:
            for i in range(7, -1, -1): bits.append((byte >> i) & 1)
        return self._compress_bits(bits)
    def _paqjp_reverse_23(self, data):
        if not data or data == b'\x00\x00\x00\x00\x00': return b''
        bits = self._decompress_bits(data)
        if not bits: return b''
        out = bytearray()
        for i in range(0, len(bits), 8):
            v = 0
            for j in range(i, min(i+8, len(bits))): v = (v << 1) | bits[j]
            if i+8 > len(bits): v <<= (8 - (len(bits) - i))
            out.append(v)
        return bytes(out)

    def _compress_bits(self, bits):
        obl = len(bits)
        if obl == 0: return b'\x00\x00\x00\x00\x00'
        cur = bits[:]; pl = obl; pc = 0
        while pc < 255:
            pad = (4 - len(cur) % 4) % 4
            padded = cur + [0] * pad
            nc = len(padded) // 4
            enc = []
            for i in range(nc):
                nib = (padded[i*4] << 3) | (padded[i*4+1] << 2) | (padded[i*4+2] << 1) | padded[i*4+3]
                L, cw = _CONST_DIAPASON_ITER_CODE[nib]
                for b in range(L-1, -1, -1): enc.append((cw >> b) & 1)
            if len(enc) < pl: cur = enc; pl = len(enc); pc += 1
            else: break
        cbl = len(cur)
        hdr = struct.pack('>H', obl) + bytes([pc]) + struct.pack('>H', cbl)
        pad = (8 - len(cur) % 8) % 8; cur += [0] * pad
        out = bytearray()
        for i in range(0, len(cur), 8):
            v = 0
            for j in range(8): v = (v << 1) | cur[i+j]
            out.append(v)
        return hdr + bytes(out)

    def _decompress_bits(self, data):
        if len(data) < 5: raise TransformError("Diap too short")
        obl = struct.unpack('>H', data[:2])[0]
        pc = data[2]
        cbl = struct.unpack('>H', data[3:5])[0]
        payload = data[5:]
        bits = []
        for byte in payload:
            for i in range(7, -1, -1): bits.append((byte >> i) & 1)
        if len(bits) < cbl: raise TransformError("Diap short")
        cur = bits[:cbl]
        if pc == 0: return cur[:obl]
        for _ in range(pc):
            pos = 0; nb = len(cur); dn = []
            while pos < nb:
                m = False
                for length in range(2, 10):
                    if pos + length > nb: continue
                    cw = 0
                    for k in range(length): cw = (cw << 1) | cur[pos+k]
                    if (length, cw) in _CONST_DIAPASON_ITER_DECODE:
                        dn.append(_CONST_DIAPASON_ITER_DECODE[(length, cw)])
                        pos += length; m = True; break
                if not m: raise TransformError("Diap invalid")
            nb2 = []
            for nib in dn:
                for j in range(3, -1, -1): nb2.append((nib >> j) & 1)
            cur = nb2
        if len(cur) < obl: raise TransformError("Diap short")
        return cur[:obl]

    def _paqjp_transform_24(self, data):
        if not data: return struct.pack('>I', 0)
        MAX = 43; bits = []; i = 0; n = len(data)
        while i < n:
            cl = min(MAX, n - i); ch = data[i:i+cl]
            f = ch[0]; same = all(b == f for b in ch)
            if same:
                self._append_bits(bits, 1, 1); self._append_bits(bits, f, 8)
                self._append_bits(bits, cl - 1, 6)
            else:
                self._append_bits(bits, 0, 1); self._append_bits(bits, cl, 6)
                for b in ch: self._append_bits(bits, b, 8)
            i += cl
        pad = (8 - len(bits) % 8) % 8; self._append_bits(bits, 0, pad)
        out = bytearray()
        for j in range(0, len(bits), 8):
            b = 0
            for k in range(8): b = (b << 1) | bits[j+k]
            out.append(b)
        return struct.pack('>I', len(data)) + bytes(out)

    def _paqjp_reverse_24(self, data):
        if not data: return b''
        if len(data) < 4: raise TransformError("BlkRun short")
        ol = struct.unpack('>I', data[:4])[0]
        payload = data[4:]
        bits = []
        for byte in payload:
            for i in range(7, -1, -1): bits.append((byte >> i) & 1)
        pos = 0; nb = len(bits); out = bytearray()
        while pos < nb and len(out) < ol:
            if pos + 1 > nb: break
            flag = self._read_bits(bits, pos, 1); pos += 1
            if flag == 1:
                if pos + 8 + 6 > nb: raise TransformError("BlkRun trunc")
                bv = self._read_bits(bits, pos, 8); pos += 8
                cm = self._read_bits(bits, pos, 6); pos += 6
                rl = min(cm + 1, ol - len(out))
                out.extend([bv] * rl)
            else:
                if pos + 6 > nb: raise TransformError("BlkRun trunc")
                cl = self._read_bits(bits, pos, 6); pos += 6
                if cl == 0: break
                if pos + cl * 8 > nb: raise TransformError("BlkRun trunc")
                for _ in range(cl):
                    out.append(self._read_bits(bits, pos, 8)); pos += 8
        return bytes(out[:ol])

    def _paqjp_transform_25(self, data):
        if not data: return b'\x01'
        n = 3; res = bytearray(data)
        for i in range(len(res)): res[i] = (pow(res[i] + 1, n, 257) - 1) & 0xFF
        return bytes([n]) + bytes(res)
    def _paqjp_reverse_25(self, data):
        if data == b'\x01': return b''
        if not data or len(data) < 2: raise TransformError("FLT25 short")
        n = data[0]; inv = mod_inv(n, 256)
        if inv is None: raise TransformError(f"FLT25 {n}")
        res = bytearray(data[1:])
        for i in range(len(res)): res[i] = (pow(res[i] + 1, inv, 257) - 1) & 0xFF
        return bytes(res)

    def _paqjp_transform_26(self, data):
        if not data: return b'\x01\x00'
        n = (len(data) * 7 + 13) & 0xFFFF
        if n % 2 == 0: n ^= 1
        e = pow(n, 16777216, 256) | 1
        res = bytearray(data)
        for i in range(len(res)): res[i] = (pow(res[i] + 1, e, 257) - 1) & 0xFF
        return bytes([n & 0xFF, (n >> 8) & 0xFF]) + bytes(res)
    def _paqjp_reverse_26(self, data):
        if data == b'\x01\x00': return b''
        if not data or len(data) < 2: raise TransformError("FLT26 short")
        n = data[0] | (data[1] << 8)
        if n % 2 == 0: n ^= 1
        e = pow(n, 16777216, 256) | 1
        inv = mod_inv(e, 256)
        if inv is None: raise TransformError(f"FLT26 {e}")
        res = bytearray(data[2:])
        for i in range(len(res)): res[i] = (pow(res[i] + 1, inv, 257) - 1) & 0xFF
        return bytes(res)

    def _paqjp_transform_27(self, data):
        if not data:
            out = bytearray(b'\x00\x00\x00\x00'); out.extend(b'\x01\x00')
            out.extend(b'\x00' * 1024); return bytes(out)
        BS = 1024; tb = (len(data) + BS - 1) // BS
        out = bytearray(); out.extend(len(data).to_bytes(4, 'big'))
        for bi in range(tb):
            s = bi * BS; e = min(s + BS, len(data))
            ch = data[s:e]
            if BS - len(ch): ch = ch + b'\x00' * (BS - len(ch))
            n = ((len(data) * 7 + bi * 13 + 1) & 0xFFFF) | 1
            e_ = pow(n, 16777216, 256) | 1
            e200 = pow(e_, 200, 256)
            t = bytearray(ch)
            for i in range(BS): t[i] = (pow(t[i] + 1, e200, 257) - 1) & 0xFF
            out.append(n & 0xFF); out.append((n >> 8) & 0xFF); out.extend(t)
        return bytes(out)
    def _paqjp_reverse_27(self, data):
        if not data or len(data) < 4: raise TransformError("FLT27 short")
        ol = int.from_bytes(data[:4], 'big')
        payload = data[4:]; BS = 1024; btl = 2 + BS
        if len(payload) % btl != 0: raise TransformError("FLT27 align")
        nb = len(payload) // btl; dec = bytearray()
        for bi in range(nb):
            off = bi * btl
            n = payload[off] | (payload[off+1] << 8)
            ch = payload[off+2:off+2+BS]
            if len(ch) < BS: raise TransformError("FLT27 trunc")
            n |= 1
            e_ = pow(n, 16777216, 256) | 1
            e200 = pow(e_, 200, 256)
            inv = mod_inv(e200, 256)
            if inv is None: raise TransformError(f"FLT27 {e200}")
            for i in range(BS): dec.append((pow(ch[i] + 1, inv, 257) - 1) & 0xFF)
        return bytes(dec[:ol])

    def _compress_backend_with_flag(self, data):
        candidates = []
        if HAS_ZSTD:
            try: candidates.append((1, zstd_cctx.compress(data)))
            except: pass
        if paq is not None:
            try: candidates.append((2, paq.compress(data)))
            except: pass
        candidates.append((0, data))
        bf, bd = min(candidates, key=lambda x: len(x[1]))
        return bytes([bf]) + bd
    def _decompress_backend_with_flag(self, data):
        if not data: return b''
        f = data[0]; payload = data[1:]
        if f == 0: return payload
        if f == 1 and HAS_ZSTD: return zstd_dctx.decompress(payload)
        if f == 2 and paq is not None: return paq.decompress(payload)
        raise TransformError("Backend flag invalid")

    def _paqjp_transform_28(self, data):
        BS = 1024
        if not data:
            block = b'\x00' * BS
            transformed = block
            compressed = self._compress_backend_with_flag(transformed)
            out = bytearray(struct.pack('>I', 0))
            out += bytes([1, 0])
            out += bytes([(len(compressed) >> 8) & 0xFF, len(compressed) & 0xFF])
            out += compressed
            return bytes(out)
        tb = (len(data) + BS - 1) // BS
        out = bytearray(); out.extend(len(data).to_bytes(4, 'big'))
        for bi in range(tb):
            s = bi * BS; e = min(s + BS, len(data))
            ch = data[s:e]
            if BS - len(ch): ch = ch + b'\x00' * (BS - len(ch))
            n = ((len(data) * 7 + bi * 13 + 1) & 0xFFFF) | 1
            e_ = pow(n, 16777216, 256) | 1
            e200 = pow(e_, 200, 256)
            t = bytearray(ch)
            for i in range(BS): t[i] = (pow(t[i] + 1, e200, 257) - 1) & 0xFF
            compressed = self._compress_backend_with_flag(bytes(t))
            out.append(n & 0xFF); out.append((n >> 8) & 0xFF)
            out.append((len(compressed) >> 8) & 0xFF); out.append(len(compressed) & 0xFF)
            out.extend(compressed)
        return bytes(out)
    def _paqjp_reverse_28(self, data):
        if not data or len(data) < 4: raise TransformError("FLT28 short")
        ol = int.from_bytes(data[:4], 'big')
        payload = data[4:]; pos = 0; dec = bytearray()
        while pos < len(payload):
            if pos + 2 > len(payload): raise TransformError("FLT28 trunc")
            n = payload[pos] | (payload[pos+1] << 8); pos += 2
            if pos + 2 > len(payload): raise TransformError("FLT28 trunc")
            cl = (payload[pos] << 8) | payload[pos+1]; pos += 2
            if pos + cl > len(payload): raise TransformError("FLT28 trunc")
            cb = payload[pos:pos+cl]; pos += cl
            block = self._decompress_backend_with_flag(cb)
            n |= 1
            e_ = pow(n, 16777216, 256) | 1
            e200 = pow(e_, 200, 256)
            inv = mod_inv(e200, 256)
            if inv is None: raise TransformError(f"FLT28 {e200}")
            t = bytearray(block)
            for i in range(len(t)): t[i] = (pow(t[i] + 1, inv, 257) - 1) & 0xFF
            dec.extend(t)
        return bytes(dec[:ol])

    def _paqjp_transform_29(self, data):
        BS = 32
        if not data:
            block = b'\x00' * BS
            compressed = self._compress_backend_with_flag(block)
            out = bytearray(struct.pack('>I', 0))
            out += bytes([1, 0])
            out += bytes([(len(compressed) >> 8) & 0xFF, len(compressed) & 0xFF])
            out += compressed
            return bytes(out)
        tb = (len(data) + BS - 1) // BS
        out = bytearray(); out.extend(len(data).to_bytes(4, 'big'))
        for bi in range(tb):
            s = bi * BS; e = min(s + BS, len(data))
            ch = data[s:e]
            if BS - len(ch): ch = ch + b'\x00' * (BS - len(ch))
            n = ((len(data) * 7 + bi * 13 + 1) & 0xFFFF) | 1
            compressed = self._compress_backend_with_flag(ch)
            out.append(n & 0xFF); out.append((n >> 8) & 0xFF)
            out.append((len(compressed) >> 8) & 0xFF); out.append(len(compressed) & 0xFF)
            out.extend(compressed)
        return bytes(out)
    def _paqjp_reverse_29(self, data):
        if not data or len(data) < 4: raise TransformError("FLT29 short")
        ol = int.from_bytes(data[:4], 'big')
        payload = data[4:]; pos = 0; dec = bytearray()
        while pos < len(payload):
            if pos + 2 > len(payload): raise TransformError("FLT29 trunc")
            pos += 2
            if pos + 2 > len(payload): raise TransformError("FLT29 trunc")
            cl = (payload[pos] << 8) | payload[pos+1]; pos += 2
            if pos + cl > len(payload): raise TransformError("FLT29 trunc")
            cb = payload[pos:pos+cl]; pos += cl
            block = self._decompress_backend_with_flag(cb)
            dec.extend(block)
        return bytes(dec[:ol])

    def _paqjp_transform_30(self, data):
        BS = 33
        if not data:
            block = b'\x00' * BS
            _, enc_n = self._paqjp_compute_n_for_block(block, 0, 0)
            compressed = self._compress_backend_with_flag(block)
            out = bytearray(struct.pack('>I', 0))
            out += enc_n
            out.append((len(compressed) >> 8) & 0xFF); out.append(len(compressed) & 0xFF)
            out += compressed
            return bytes(out)
        tb = (len(data) + BS - 1) // BS
        out = bytearray(); out.extend(len(data).to_bytes(4, 'big'))
        for bi in range(tb):
            s = bi * BS; e = min(s + BS, len(data))
            ch = data[s:e]
            if BS - len(ch): ch = ch + b'\x00' * (BS - len(ch))
            _, enc_n = self._paqjp_compute_n_for_block(ch, bi, len(data))
            compressed = self._compress_backend_with_flag(ch)
            out.extend(enc_n)
            out.append((len(compressed) >> 8) & 0xFF); out.append(len(compressed) & 0xFF)
            out.extend(compressed)
        return bytes(out)

    def _paqjp_compute_n_for_block(self, block, block_idx, total_len):
        if not block: return (1, b'\x01\x01')
        d = block[0]
        x = (block_idx % 33) + 1
        try:
            t = (d*d - d**x) // 256
        except OverflowError:
            t = 0
        if 0 <= t <= 255:
            n = t | 1
            return (n, bytes([1, n]))
        h = hashlib.sha256(block + bytes([block_idx & 0xFF,
                                          (total_len>>8)&0xFF, total_len&0xFF])).digest()
        nb = bytearray(h); nb[0] |= 1
        encoded = bytes([len(nb)]) + bytes(nb)
        return (int.from_bytes(nb, 'big'), encoded)

    def _paqjp_reverse_30(self, data):
        if not data or len(data) < 4: raise TransformError("FLT30 short")
        ol = int.from_bytes(data[:4], 'big')
        payload = data[4:]; pos = 0; dec = bytearray()
        while pos < len(payload):
            if pos >= len(payload): raise TransformError("FLT30 trunc")
            Ln = payload[pos]; pos += 1
            if Ln > 32 or pos + Ln > len(payload): raise TransformError("FLT30 bad n")
            pos += Ln
            if pos + 2 > len(payload): raise TransformError("FLT30 trunc")
            cl = (payload[pos] << 8) | payload[pos+1]; pos += 2
            if pos + cl > len(payload): raise TransformError("FLT30 trunc")
            cb = payload[pos:pos+cl]; pos += cl
            block = self._decompress_backend_with_flag(cb)
            dec.extend(block)
        return bytes(dec[:ol])

    # ---- 41-47 ----
    def transform_41(self, data):
        if not data: return b''
        mask = bytes([0x27, 0x03]); t = bytearray(data)
        for i in range(min(len(t), 8)): t[i] ^= mask[i % 2]
        return bytes(t)
    reverse_transform_41 = transform_41

    def transform_42(self, data):
        if not data: return b''
        t = bytearray(data); mask = bytes([0x27, 0x03])
        for i in range(len(t)): t[i] ^= mask[i % 2]
        return bytes(t)
    reverse_transform_42 = transform_42

    def transform_43(self, data):
        if not data: return b''
        t = bytearray(data); mask = bytes([0x10, 0x00, 0x00])
        for i in range(0, len(t), 3):
            for j in range(min(3, len(t) - i)): t[i+j] ^= mask[j]
        return bytes(t)
    reverse_transform_43 = transform_43

    def transform_44(self, data):
        if not data: return b''
        return base64.b64encode(data)
    def reverse_transform_44(self, data):
        if not data: return b''
        try: return base64.b64decode(data, validate=False)
        except Exception as e: raise TransformError(f"b64-44 {e}")

    @staticmethod
    def _huffman_code_lengths(freq):
        heap = [(f, i, i) for i, f in enumerate(freq) if f > 0]
        if not heap: return [0] * len(freq)
        if len(heap) == 1:
            lengths = [0] * len(freq); lengths[heap[0][2]] = 1; return lengths
        heapq.heapify(heap); nid = len(freq)
        while len(heap) > 1:
            f1, _, n1 = heapq.heappop(heap); f2, _, n2 = heapq.heappop(heap)
            heapq.heappush(heap, (f1 + f2, nid, (n1, n2))); nid += 1
        lengths = [0] * len(freq)
        def traverse(node, depth):
            if isinstance(node, int): lengths[node] = depth
            else:
                traverse(node[0], depth + 1); traverse(node[1], depth + 1)
        traverse(heap[0][2], 0)
        return lengths

    @staticmethod
    def _huffman_canonical_codes(code_lengths):
        symbols = list(range(len(code_lengths)))
        symbols.sort(key=lambda s: (code_lengths[s], s))
        codes = {}; code = 0; prev_len = 0; first = True
        for sym in symbols:
            cl = code_lengths[sym]
            if cl == 0: continue
            if first: prev_len = cl; first = False
            elif cl != prev_len: code <<= (cl - prev_len); prev_len = cl
            codes[sym] = (code, cl); code += 1
        return codes

    def transform_45(self, data):
        if not data: return b''
        freq = [0]*256
        for b in data: freq[b] += 1
        cl = self._huffman_code_lengths(freq)
        codes = self._huffman_canonical_codes(cl)
        header = bytearray()
        header.extend(len(data).to_bytes(4, 'big'))
        header.extend(cl)
        bits = []
        for b in data:
            c, l = codes[b]
            for i in range(l - 1, -1, -1): bits.append((c >> i) & 1)
        pad = (8 - len(bits) % 8) % 8; bits.extend([0] * pad)
        out = bytearray()
        for i in range(0, len(bits), 8):
            v = 0
            for j in range(8): v = (v << 1) | bits[i+j]
            out.append(v)
        return bytes(header) + bytes(out)

    def reverse_transform_45(self, data):
        if not data: return b''
        if len(data) < 4 + 256: raise TransformError("Huff short")
        ol = int.from_bytes(data[:4], 'big')
        cl = list(data[4:4+256])
        payload = data[4+256:]
        if ol == 0: return b''
        if max(cl) > 32: raise TransformError("Huff code > 32")
        code_to_sym = {}
        symbols = list(range(256))
        symbols.sort(key=lambda s: (cl[s], s))
        code = 0; pl = 0; first = True
        for sym in symbols:
            L = cl[sym]
            if L == 0: continue
            if first: pl = L; first = False
            elif L != pl: code <<= (L - pl); pl = L
            code_to_sym[(L, code)] = sym; code += 1
        bits = []
        for byte in payload:
            for i in range(7, -1, -1): bits.append((byte >> i) & 1)
        pos = 0; nb = len(bits); out = bytearray()
        maxL = max(cl) if any(cl) else 0
        while pos < nb and len(out) < ol:
            found = False
            for L in range(1, maxL + 1):
                if pos + L > nb: break
                v = 0
                for j in range(L): v = (v << 1) | bits[pos+j]
                if (L, v) in code_to_sym:
                    out.append(code_to_sym[(L, v)]); pos += L; found = True; break
            if not found: raise TransformError(f"Huff bad bit at {pos}")
        if len(out) != ol: raise TransformError("Huff length mismatch")
        return bytes(out)

    def transform_46(self, data):
        if not data: return b''
        t = bytearray(data); m = self.mask_46
        for i in range(len(t)): t[i] ^= m[i % len(m)]
        return bytes(t)
    reverse_transform_46 = transform_46

    def transform_47(self, data):
        if not data: return b''
        t = bytearray(data); tl = len(self.mod_state_table)
        if tl == 0: return data
        for i in range(len(t)): t[i] ^= self.mod_state_table[i % tl][0]
        return bytes(t)
    reverse_transform_47 = transform_47

    def transform_57(self, data):
        if len(data) < 4:
            pl = 4 - len(data); key = 0
            header = bytes([pl]) + key.to_bytes(4, 'little')
            return header + data + b'\x00' * pl
        n = len(data); pl = (4 - n % 4) % 4
        padded = data + b'\x00' * pl
        blocks = [padded[i:i+4] for i in range(0, len(padded), 4)]
        mc, _ = Counter(blocks).most_common(1)[0]
        key = int.from_bytes(mc, 'little')
        tr = bytearray()
        for block in blocks:
            v = int.from_bytes(block, 'little') ^ key
            tr.extend(v.to_bytes(4, 'little'))
        return bytes([pl]) + key.to_bytes(4, 'little') + bytes(tr)

    def reverse_transform_57(self, data):
        if len(data) < 5: raise TransformError("T57 short")
        pl = data[0]; key = int.from_bytes(data[1:5], 'little')
        payload = data[5:]
        if len(payload) % 4 != 0: raise TransformError("T57 not mult of 4")
        tr = bytearray()
        for i in range(0, len(payload), 4):
            v = int.from_bytes(payload[i:i+4], 'little') ^ key
            tr.extend(v.to_bytes(4, 'little'))
        if pl > 0: tr = tr[:-pl]
        return bytes(tr)

    def _dynamic_transform(self, n):
        def tf(data):
            if not data: return b''
            seed = self.get_seed(n % len(self.seed_tables), len(data))
            return bytes(b ^ seed for b in data)
        return tf, tf

    def transform_256(self, d): return d
    reverse_transform_256 = transform_256

    def _decompress_static_dict(self, data): return None
    def _decompress_dynamic_dict(self, data): return None
    def _decompress_line_dict(self, data): return None

    def _build_transform_maps(self):
        self.fwd_transforms = {}
        self.rev_transforms = {}
        for i in range(1, 22):
            self.fwd_transforms[i] = getattr(self, f"transform_{i:02d}")
            self.rev_transforms[i] = getattr(self, f"reverse_transform_{i:02d}")
        self.fwd_transforms[22] = self.transform_22; self.rev_transforms[22] = self.reverse_transform_22
        self.fwd_transforms[23] = self.transform_23; self.rev_transforms[23] = self.reverse_transform_23
        self.fwd_transforms[24] = self.transform_24; self.rev_transforms[24] = self.reverse_transform_24
        self.fwd_transforms[25] = self.transform_25; self.rev_transforms[25] = self.reverse_transform_25
        self.fwd_transforms[26] = self.transform_26; self.rev_transforms[26] = self.reverse_transform_26
        self.fwd_transforms[27] = self.transform_27; self.rev_transforms[27] = self.reverse_transform_27
        self.fwd_transforms[28] = self.transform_28; self.rev_transforms[28] = self.reverse_transform_28
        self.fwd_transforms[29] = self.transform_29; self.rev_transforms[29] = self.reverse_transform_29
        self.fwd_transforms[30] = self.transform_30; self.rev_transforms[30] = self.reverse_transform_30
        self.fwd_transforms[31] = self.transform_31; self.rev_transforms[31] = self.reverse_transform_31
        self.fwd_transforms[32] = self.transform_32; self.rev_transforms[32] = self.reverse_transform_32
        self.fwd_transforms[33] = self._paqjp_transform_23; self.rev_transforms[33] = self._paqjp_reverse_23
        self.fwd_transforms[34] = self._paqjp_transform_24; self.rev_transforms[34] = self._paqjp_reverse_24
        self.fwd_transforms[35] = self._paqjp_transform_25; self.rev_transforms[35] = self._paqjp_reverse_25
        self.fwd_transforms[36] = self._paqjp_transform_26; self.rev_transforms[36] = self._paqjp_reverse_26
        self.fwd_transforms[37] = self._paqjp_transform_27; self.rev_transforms[37] = self._paqjp_reverse_27
        self.fwd_transforms[38] = self._paqjp_transform_28; self.rev_transforms[38] = self._paqjp_reverse_28
        self.fwd_transforms[39] = self._paqjp_transform_29; self.rev_transforms[39] = self._paqjp_reverse_29
        self.fwd_transforms[40] = self._paqjp_transform_30; self.rev_transforms[40] = self._paqjp_reverse_30
        self.fwd_transforms[41] = self.transform_41; self.rev_transforms[41] = self.reverse_transform_41
        self.fwd_transforms[42] = self.transform_42; self.rev_transforms[42] = self.reverse_transform_42
        self.fwd_transforms[43] = self.transform_43; self.rev_transforms[43] = self.reverse_transform_43
        self.fwd_transforms[44] = self.transform_44; self.rev_transforms[44] = self.reverse_transform_44
        self.fwd_transforms[45] = self.transform_45; self.rev_transforms[45] = self.reverse_transform_45
        self.fwd_transforms[46] = self.transform_46; self.rev_transforms[46] = self.reverse_transform_46
        self.fwd_transforms[47] = self.transform_47; self.rev_transforms[47] = self.reverse_transform_47
        for i in range(48, 57):
            fwd, rev = self._dynamic_transform(i)
            self.fwd_transforms[i] = fwd; self.rev_transforms[i] = rev
        self.fwd_transforms[57] = self.transform_57; self.rev_transforms[57] = self.reverse_transform_57
        for i in range(58, 256):
            fwd, rev = self._dynamic_transform(i)
            self.fwd_transforms[i] = fwd; self.rev_transforms[i] = rev
        self.fwd_transforms[256] = self.transform_256; self.rev_transforms[256] = self.reverse_transform_256

    def _load_static_dictionary(self):
        if not os.path.exists(COMBINED_DICTIONARY_FILE): return [], {}
        words_set = set()
        try:
            with open(COMBINED_DICTIONARY_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    w = line.strip()
                    if w: words_set.add(w)
        except Exception: return [], {}
        sorted_words = sorted(words_set)
        return sorted_words, {w: i for i, w in enumerate(sorted_words)}

    def _load_line_dictionary(self):
        if not os.path.exists(COMBINED_DICTIONARY_FILE): return [], {}
        lines = []
        try:
            with open(COMBINED_DICTIONARY_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                for raw in f:
                    p = raw.strip()
                    if p and p not in lines:
                        lines.append(p)
                        if len(lines) >= MAX_LINE_ENTRIES: break
        except Exception: return [], {}
        if not lines: return [], {}
        lines.sort(key=len, reverse=True)
        return lines, {p: i for i, p in enumerate(lines)}

    def _generate_permutation_from_circuit(self, num_qubits, seed):
        if not USE_QUANTUM or not HAS_QISKIT:
            rng = random.Random(seed); size = 1 << num_qubits
            perm = list(range(size)); rng.shuffle(perm); return perm
        try:
            qc = QuantumCircuit(num_qubits)
            rng = random.Random(seed)
            for q in range(num_qubits):
                qc.h(q); qc.rz(rng.random() * 2 * math.pi, q); qc.rx(rng.random() * 2 * math.pi, q)
            for _ in range(num_qubits):
                for i in range(num_qubits - 1): qc.cx(i, i+1)
                qc.barrier()
                for i in range(num_qubits):
                    qc.rz(rng.random() * 2 * math.pi, i); qc.rx(rng.random() * 2 * math.pi, i)
            try: qasm_str = qc.qasm()
            except AttributeError: qasm_str = qc.draw('text')
            final_seed = seed + hash(qasm_str) % 1000000
            rng2 = random.Random(final_seed); size = 1 << num_qubits
            perm = list(range(size)); rng2.shuffle(perm); return perm
        except Exception:
            rng = random.Random(seed); size = 1 << num_qubits
            perm = list(range(size)); rng.shuffle(perm); return perm

    def _precompute_quantum_transforms(self):
        if not USE_QUANTUM or not HAS_QISKIT: return
        q = self.QUANTUM_QUBITS
        if q > 49: q = 49; self.QUANTUM_QUBITS = q
        size = 1 << q
        block_size = size if q <= 12 else 1024
        self.quantum_fast_transforms = []
        for i in range(8):
            seed = 1000 + i
            perm = self._generate_permutation_from_circuit(q, seed)
            if len(perm) > block_size: perm = perm[:block_size]
            fwd, rev = self._make_substitution_transform(perm, block_size)
            self.quantum_fast_transforms.append((fwd, rev))
        for idx, (fwd, rev) in enumerate(self.quantum_fast_transforms, start=1):
            self.fwd_transforms[256 + idx] = fwd
            self.rev_transforms[256 + idx] = rev
        self.quantum_transforms_built = True
        print(f"Quantum transforms built: 8 with block {block_size}, {q} qubits.")

    def _make_substitution_transform(self, perm, size):
        if size < 256:
            inv = [0] * size
            for i, p in enumerate(perm): inv[p] = i
            def fwd(data):
                return bytes(perm[b] if b < size else b for b in data)
            def rev(data):
                return bytes(inv[b] if b < size else b for b in data)
        else:
            inv = [0] * size
            for i, p in enumerate(perm): inv[p] = i
            def fwd(data): return bytes(perm[b] for b in data)
            def rev(data): return bytes(inv[b] for b in data)
        return fwd, rev

    def _get_pattern(self, size, index):
        random.seed(12345 + size * 100 + index)
        return [random.randint(0, 255) for _ in range(size)]

    def _calculate_repeats(self, data):
        if not data: return 1
        L = len(data); s = sum(data) % 256
        return max(1, min(256, ((L * 13 + s * 17) % 256) + 1))

    def _verify_lossless(self, orig, trans, rev):
        try: return rev(trans) == orig
        except Exception: return False

    def _lz77_tokenize(self, data):
        tokens = []; i = 0; n = len(data)
        while i < n:
            bl = 0; bd = 0
            sw = max(0, i - self.WINDOW_SIZE)
            for j in range(sw, i):
                if data[j] != data[i]: continue
                k = 0
                while i + k < n and j + k < i and data[j+k] == data[i+k]:
                    k += 1
                    if k >= self.MAX_MATCH: break
                if k >= self.MIN_MATCH and k > bl:
                    bl = k; bd = i - j
                    if bl == self.MAX_MATCH: break
            if bl >= self.MIN_MATCH:
                tokens.append(('M', bd, bl)); i += bl
            else:
                tokens.append(('L', data[i], None)); i += 1
        return tokens

    def _lz77_untokenize(self, tokens):
        out = bytearray()
        for t in tokens:
            if t[0] == 'L': out.append(t[1])
            else:
                d, l = t[1], t[2]
                st = len(out) - d
                for k in range(l): out.append(out[st+k])
        return bytes(out)

    def _encode_lzh(self, data):
        tokens = self._lz77_tokenize(data)
        lf = [0]*256; df = [0]*(self.MAX_DIST+1); nf = [0]*(self.MAX_MATCH+1)
        for t in tokens:
            if t[0] == 'L': lf[t[1]] += 1
            else: df[t[1]] += 1; nf[t[2]] += 1
        lcl = self._huffman_code_lengths(lf)
        dcl = self._huffman_code_lengths(df)
        ncl = self._huffman_code_lengths(nf)
        lcs = self._huffman_canonical_codes(lcl)
        dcs = self._huffman_canonical_codes(dcl)
        ncs = self._huffman_canonical_codes(ncl)
        bits = []
        tc = len(tokens)
        for b in struct.pack('>I', tc):
            for i in range(8): bits.append((b >> (7-i)) & 1)
        for t in tokens:
            if t[0] == 'L':
                bits.append(0)
                c, l = lcs[t[1]]
                for i in range(l-1, -1, -1): bits.append((c >> i) & 1)
            else:
                bits.append(1)
                cd, ld = dcs[t[1]]
                for i in range(ld-1, -1, -1): bits.append((cd >> i) & 1)
                cl, ll = ncs[t[2]]
                for i in range(ll-1, -1, -1): bits.append((cl >> i) & 1)
        pad = (8 - len(bits) % 8) % 8; bits.extend([0] * pad)
        def pk(L): return b''.join(struct.pack('>H', x) for x in L)
        header = bytearray(); header.extend(pk(lcl)); header.extend(pk(dcl)); header.extend(pk(ncl))
        out = bytearray(header)
        for i in range(0, len(bits), 8):
            b = 0
            for j in range(8): b = (b << 1) | bits[i+j]
            out.append(b)
        return bytes(out)

    def _decode_lzh(self, data):
        LL = 256 * 2; DL = 2049 * 2; NL = 2049 * 2
        if len(data) < LL + DL + NL: raise TransformError("LZH short")
        pos = 0
        lcl = [struct.unpack('>H', data[i:i+2])[0] for i in range(pos, pos+LL, 2)]; pos += LL
        dcl = [struct.unpack('>H', data[i:i+2])[0] for i in range(pos, pos+DL, 2)]; pos += DL
        ncl = [struct.unpack('>H', data[i:i+2])[0] for i in range(pos, pos+NL, 2)]; pos += NL
        def bdt(L):
            syms = sorted(range(len(L)), key=lambda s: (L[s], s))
            d = {}; c = 0; pl = 0; first = True
            for s in syms:
                cl = L[s]
                if cl == 0: continue
                if first: pl = cl; first = False
                elif cl != pl: c <<= (cl - pl); pl = cl
                d[(cl, c)] = s; c += 1
            return d
        ld = bdt(lcl); dd = bdt(dcl); nd = bdt(ncl)
        mlb = max(lcl) if any(lcl) else 0
        mdb = max(dcl) if any(dcl) else 0
        mnb = max(ncl) if any(ncl) else 0
        payload = data[pos:]
        if len(payload) < 4: raise TransformError("LZH empty")
        tc = struct.unpack('>I', payload[:4])[0]
        bits = []
        for byte in payload[4:]:
            for i in range(7, -1, -1): bits.append((byte >> i) & 1)
        bpos = 0; tokens = []
        for _ in range(tc):
            if bpos >= len(bits): raise TransformError("LZH eof")
            flag = bits[bpos]; bpos += 1
            if flag == 0:
                found = False
                for cl in range(1, mlb + 1):
                    if bpos + cl > len(bits): break
                    v = 0
                    for j in range(cl): v = (v << 1) | bits[bpos+j]
                    if (cl, v) in ld:
                        tokens.append(('L', ld[(cl, v)], None)); bpos += cl; found = True; break
                if not found: raise TransformError("LZH lit")
            else:
                fd = False
                for cl in range(1, mdb + 1):
                    if bpos + cl > len(bits): break
                    v = 0
                    for j in range(cl): v = (v << 1) | bits[bpos+j]
                    if (cl, v) in dd:
                        dist = dd[(cl, v)]; bpos += cl; fd = True; break
                if not fd: raise TransformError("LZH dist")
                fn = False
                for cl in range(1, mnb + 1):
                    if bpos + cl > len(bits): break
                    v = 0
                    for j in range(cl): v = (v << 1) | bits[bpos+j]
                    if (cl, v) in nd:
                        length = nd[(cl, v)]; bpos += cl; fn = True; break
                if not fn: raise TransformError("LZH len")
                tokens.append(('M', dist, length))
        return self._lz77_untokenize(tokens)

    def _encode_marker_single(self, t):
        if t <= 252: return bytes([t - 1])
        if t <= 255: return bytes([254, t - 253])
        return bytes([255, (t - 256) // 256, (t - 256) % 256])
    def _encode_marker_raw(self): return bytes([252])
    def _decode_header(self, data):
        if len(data) < 1: return 0, ()
        f = data[0]
        if f < 252: return 1, (f + 1,)
        if f == 252: return 1, ()
        if f == 254:
            if len(data) < 2: return 0, ()
            x = data[1]
            return (2, (253 + x,)) if x <= 3 else (0, ())
        if f == 255:
            if len(data) < 3: return 0, ()
            t = 256 + data[1] * 256 + data[2]
            return 3, (t,)
        return 0, ()

    def _compress_backend(self, data):
        candidates = []
        if HAS_ZSTD:
            try: candidates.append(zstd_cctx.compress(data))
            except: pass
        if paq is not None:
            try: candidates.append(paq.compress(data))
            except: pass
        candidates.append(data)
        return min(candidates, key=len)

    def _decompress_backend(self, data):
        if len(data) == 0: return b''
        if HAS_ZSTD:
            try: return zstd_dctx.decompress(data)
            except: pass
        if paq is not None:
            try: return paq.decompress(data)
            except: pass
        return data

    def compress_with_verification(self, data, time_limit=None):
        if time_limit is None: time_limit = self.ULTRA_TIME_LIMIT
        st = time.time(); best = None; bl = float('inf')
        def try_c(h, t):
            nonlocal best, bl
            c = h + self._compress_backend(t)
            if len(c) < bl: best = c; bl = len(c)
        try_c(self._encode_marker_raw(), data)
        for t in range(1, 257):
            if time_limit and time.time() - st > time_limit: break
            try:
                tr = self.fwd_transforms[t](data)
                if not self._verify_lossless(data, tr, self.rev_transforms[t]): continue
                try_c(self._encode_marker_single(t), tr)
            except Exception: continue
        if best is None: best = self._encode_marker_raw() + self._compress_backend(data)
        try:
            decomp, _ = self._decompress_auto(best)
        except Exception: decomp = None
        if decomp == data: return best
        return self._encode_marker_raw() + self._compress_backend(data)

    def compress_with_lzh(self, data, time_limit=None):
        if time_limit is None: time_limit = self.ULTRA_TIME_LIMIT
        st = time.time(); best = None; bl = float('inf')
        def try_c(h, t):
            nonlocal best, bl
            lzh = self._encode_lzh(t); c = h + b'\xFF' + lzh
            if len(c) < bl: best = c; bl = len(c)
        try_c(self._encode_marker_raw(), data)
        for t in range(1, 257):
            if time_limit and time.time() - st > time_limit: break
            try:
                tr = self.fwd_transforms[t](data)
                if not self._verify_lossless(data, tr, self.rev_transforms[t]): continue
                try_c(self._encode_marker_single(t), tr)
            except Exception: continue
        if best is None: best = self._encode_marker_raw() + self._compress_backend(data)
        return best

    def _decompress_lzh_pipeline(self, data):
        offset, seq = self._decode_header(data)
        if offset == 0: return None
        if len(data) <= offset or data[offset] != 0xFF: return None
        lzh = data[offset+1:]
        tr = self._decode_lzh(lzh)
        if tr is None: return None
        if not seq: return tr
        return self._reverse_sequence(tr, seq)

    def _decompress_auto(self, data):
        offset, seq = self._decode_header(data)
        if offset == 0: raise DecompressionError("Invalid header")
        payload = data[offset:]
        if not payload: raise DecompressionError("Empty payload")
        res = self._decompress_backend(payload)
        if res is None: raise DecompressionError("Backend failed")
        if not seq: return res, None
        return self._reverse_sequence(res, seq), seq

    def _reverse_sequence(self, data, seq):
        r = data
        for t in reversed(seq): r = self.rev_transforms[t](r)
        return r

    def _auto_output_name(self, infile, suffix=".pjp"):
        return f"{os.path.basename(infile)}{suffix}"

    def _atomic_write(self, path, data):
        d = os.path.dirname(path) or '.'
        fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + '.tmp', dir=d)
        try: os.write(fd, data); os.fsync(fd)
        finally: os.close(fd)
        os.replace(tmp, path)

    def compress_file(self, infile, outfile="", use_lzh=False, time_limit=None):
        try:
            with open(infile, 'rb') as f: data = f.read()
        except Exception as e:
            print(f"Error reading: {e}"); return
        try:
            if use_lzh:
                compressed = self.compress_with_lzh(data, time_limit=time_limit)
                suffix = ".pjp.lzh"
            else:
                compressed = self.compress_with_verification(data, time_limit=time_limit)
                suffix = ".pjp"
        except RuntimeError as e:
            print(f"Compression failed: {e}"); return
        if not outfile: outfile = self._auto_output_name(infile, suffix)
        try: self._atomic_write(outfile, compressed)
        except Exception as e:
            print(f"Write failed: {e}"); return
        print(f"Compressed {len(data)} → {len(compressed)} bytes → {outfile}")

    def decompress_file(self, infile, outfile=""):
        try:
            with open(infile, 'rb') as f: data = f.read()
        except Exception as e:
            print(f"Error reading: {e}"); return False
        try:
            offset, seq = self._decode_header(data)
            if offset == 0:
                print("Invalid header."); return False
            if offset < len(data) and data[offset] == 0xFF:
                original = self._decompress_lzh_pipeline(data)
            else:
                try: original, _ = self._decompress_auto(data)
                except DecompressionError as e:
                    print(f"Decompression failed: {e}"); return False
        except Exception as e:
            print(f"Error: {e}"); return False
        if original is None:
            print("Produced None"); return False
        if not outfile:
            base = os.path.basename(infile)
            outfile = re.sub(r'\.pjp(\.lzh)?$', '', base)
        try: self._atomic_write(outfile, original)
        except Exception as e:
            print(f"Write failed: {e}"); return False
        print(f"Decompressed → {outfile} ({len(original)} bytes)")
        return True

    # ================================================================
    # FAST self-test (~30 seconds)
    # ================================================================
    def fast_self_test(self) -> bool:
        print("=" * 60)
        print("FAST Self-Test (256 transforms)")
        print("=" * 60)
        t0 = time.time()
        all_ok = True

        # Phase 1: focused test on the "dangerous" transforms
        # (those using find_nearest_prime_around and other fragile ones)
        print("\n[1/3] Focused test on 7 key transforms (500 random cases each) ...")
        key_transforms = [8, 9, 13, 23, 27, 45, 57]
        rng = random.Random(0xC0FFEE)
        cases = [b"", b"\x00", b"\xff", b"A", b"AB", b"AB"*100,
                 b"\x00"*1000, b"\xff"*1000, bytes(range(256)),
                 bytes(range(256))*8, b"hello world "*200,
                 b"a1b2c3_XYZ "*200,
                 "héllo wörld — ünïcode ✓\n".encode("utf-8")*50]
        try:
            for t in key_transforms:
                for i, d0 in enumerate(cases):
                    tr = self.fwd_transforms[t](d0)
                    rt = self.rev_transforms[t](tr)
                    if rt != d0:
                        print(f"  FAIL t={t} case={i} len={len(d0)}")
                        all_ok = False; break
                if not all_ok: break
                for _ in range(500):
                    n = rng.randint(0, 1024)
                    d0 = bytes(rng.randint(0, 255) for _ in range(n))
                    tr = self.fwd_transforms[t](d0)
                    rt = self.rev_transforms[t](tr)
                    if rt != d0:
                        print(f"  FAIL t={t} n={n} (random)")
                        all_ok = False; break
                if not all_ok: break
            if all_ok:
                print(f"  PASS {len(key_transforms)} key transforms "
                      f"({len(cases)} structured + 500 random each)")
        except Exception as e:
            print(f"  FAIL focused: {e}"); all_ok = False

        # Phase 2: sample all 256 transforms
        if all_ok:
            print("\n[2/3] Sample all 256 transforms (50 random cases each) ...")
            rng = random.Random(0xF00D)
            failed = []
            for t in range(1, 257):
                try:
                    for _ in range(50):
                        n = rng.randint(0, 256)
                        d0 = bytes(rng.randint(0, 255) for _ in range(n))
                        tr = self.fwd_transforms[t](d0)
                        rt = self.rev_transforms[t](tr)
                        if rt != d0:
                            failed.append((t, n, "mismatch")); break
                except Exception as e:
                    failed.append((t, -1, f"{type(e).__name__}: {e}"))
            if not failed:
                print("  PASS 12 800 fuzz round-trips (256 × 50)")
            else:
                all_ok = False
                print(f"  FAIL: {len(failed)} transform(s) failed:")
                for t, n, why in failed[:10]:
                    print(f"    t={t} n={n}: {why}")

        # Phase 3: backend sanity
        if all_ok:
            print("\n[3/3] Backend sanity ...")
            try:
                d0 = b"The quick brown fox jumps over the lazy dog. " * 20
                comp = self.compress_with_verification(d0, time_limit=20)
                decomp, _ = self._decompress_auto(comp)
                if decomp != d0:
                    print("  FAIL compress/decompress round-trip")
                    all_ok = False
                else:
                    print(f"  PASS full pipeline ({len(d0)} → {len(comp)})")
            except Exception as e:
                print(f"  FAIL backend: {e}"); all_ok = False

        elapsed = time.time() - t0
        print()
        print("=" * 60)
        if all_ok:
            print(f"[All checks passed — 256/256 lossless]  ({elapsed:.1f}s)")
        else:
            print(f"[SOME CHECKS FAILED]  ({elapsed:.1f}s)")
        return all_ok

    # ================================================================
    # DEEP self-test (~2 minutes)
    # ================================================================
    def full_self_test(self) -> bool:
        print("=" * 60)
        print("DEEP Self-Test (256 transforms)")
        print("=" * 60)
        t0 = time.time()
        all_ok = True

        print("\n[1/3] Deep test on 7 key transforms (5000 random cases each) ...")
        key_transforms = [8, 9, 13, 23, 27, 45, 57]
        rng = random.Random(0xC0FFEE)
        try:
            for t in key_transforms:
                for _ in range(5000):
                    n = rng.randint(0, 2048)
                    d0 = bytes(rng.randint(0, 255) for _ in range(n))
                    tr = self.fwd_transforms[t](d0)
                    rt = self.rev_transforms[t](tr)
                    if rt != d0:
                        print(f"  FAIL t={t} n={n}"); all_ok = False; break
                if not all_ok: break
            if all_ok: print(f"  PASS {len(key_transforms)} × 5000 cases")
        except Exception as e:
            print(f"  FAIL focused: {e}"); all_ok = False

        if all_ok:
            print("\n[2/3] Fuzz all 256 transforms (2000 random cases each) ...")
            rng = random.Random(0xF00D)
            for t in range(1, 257):
                try:
                    for _ in range(2000):
                        n = rng.randint(0, 512)
                        d0 = bytes(rng.randint(0, 255) for _ in range(n))
                        tr = self.fwd_transforms[t](d0)
                        rt = self.rev_transforms[t](tr)
                        if rt != d0:
                            print(f"  FAIL t={t} n={n}"); all_ok = False; break
                except Exception as e:
                    print(f"  FAIL t={t}: {type(e).__name__}: {e}")
                    all_ok = False
                if not all_ok: break
            if all_ok: print("  PASS 512 000 fuzz round-trips")

        if all_ok:
            print("\n[3/3] Extended pipeline tests ...")
            extended = [b"", b"A", b"AB", b"hello world",
                        b"The quick brown fox jumps over the lazy dog.\n" * 20,
                        bytes(range(256)), bytes(range(256)) * 4,
                        os.urandom(64), os.urandom(1024),
                        "Héllo wörld – UTF-8 test ✓".encode('utf-8') * 10]
            try:
                for idx, case in enumerate(extended):
                    for use_lzh in (False, True):
                        if use_lzh:
                            comp = self.compress_with_lzh(case, time_limit=20)
                            decomp = self._decompress_lzh_pipeline(comp)
                        else:
                            comp = self.compress_with_verification(case, time_limit=20)
                            decomp, _ = self._decompress_auto(comp)
                        if decomp != case:
                            print(f"  FAIL case {idx} (lzh={use_lzh})")
                            all_ok = False; break
                    if not all_ok: break
                if all_ok: print("  PASS extended pipeline tests")
            except Exception as e:
                print(f"  FAIL extended: {e}"); all_ok = False

        elapsed = time.time() - t0
        print()
        print("=" * 60)
        if all_ok:
            print(f"[All checks passed — 256/256 lossless]  ({elapsed:.1f}s)")
        else:
            print(f"[SOME CHECKS FAILED]  ({elapsed:.1f}s)")
        return all_ok

# ------------------------------------------------------------
# Main menu — 3 options
# ------------------------------------------------------------
def main():
    print(f"{PROGNAME} – Unified compression with 256 single transforms")
    print("Compressed output: input.txt.pjp (or input.txt.pjp.lzh)")
    print("Lossless output guaranteed via per-input verification + raw fallback.\n")
    c = UnifiedCompressor()

    while True:
        print("\n" + "=" * 50)
        print("Menu (3 options):")
        print("  1) Compress (Fast)")
        print("  2) Decompress")
        print("  3) Fast self-test  ← 256 transforms, ~30 seconds")
        print("  (Ctrl+C or Ctrl+D to exit)")
        print("=" * 50)
        try:
            choice = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if choice == "1":
            try: infile = input("Input file: ").strip()
            except (EOFError, KeyboardInterrupt): break
            if not infile: continue
            c.compress_file(infile, use_lzh=False)
        elif choice == "2":
            try: infile = input("Compressed file (.pjp / .pjp.lzh): ").strip()
            except (EOFError, KeyboardInterrupt): break
            if not infile: continue
            if not (infile.lower().endswith('.pjp') or infile.lower().endswith('.pjp.lzh')):
                print("Only .pjp and .pjp.lzh supported."); continue
            try: outfile = input("Output file (blank=auto): ").strip()
            except (EOFError, KeyboardInterrupt): break
            c.decompress_file(infile, outfile)
        elif choice == "3":
            c.fast_self_test()
        else:
            print("Invalid. Enter 1, 2, or 3.")

if __name__ == "__main__":
    main()
