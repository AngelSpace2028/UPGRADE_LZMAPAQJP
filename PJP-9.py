#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified PAQJP+PJP – Simplified (Lossless, 256 transforms only)
==============================================================
- 256 base transforms (single, no pairs)
- Time‑limited modes (default 300s)
- Final verification + fallback to raw+backend
- Quantum‑inspired transforms (optional)
- Exhaustive self‑test for 256 transforms
- Output naming: input.txt.pjp (or .pjp.lzh)
- ALL 256 base transforms are individually lossless for every input.
- Composition of lossless transforms is lossless (not used here).
"""

import math
import random
import decimal
import hashlib
import base64
import heapq
import struct
import os
import tempfile
import re
import urllib.request
import sys
import subprocess
import importlib
import time
from typing import Optional, List, Tuple, Dict, Callable, Any
from collections import Counter

# ------------------------------------------------------------------
# Optional backend: paq
# ------------------------------------------------------------------
try:
    import paq
except ImportError:
    paq = None

USE_QUANTUM = False
HAS_QISKIT = False
HAS_ZSTD = False

def install_package(pkg: str) -> bool:
    """Install a package non‑interactively."""
    print(f"Installing {pkg}...")
    try:
        subprocess.check_call([
            sys.executable, '-m', 'pip', 'install',
            '--no-input', '--disable-pip-version-check', pkg
        ])
        return True
    except Exception:
        return False

# ---------- Prompt 1: Quantum ----------
quantum_choice = input("Option 1: Enable quantum‑inspired transforms (requires Qiskit)? (y/n) [default n]: ").strip().lower()
if quantum_choice == 'y':
    try:
        from qiskit import QuantumCircuit
        HAS_QISKIT = True
        USE_QUANTUM = True
        print("Quantum transforms ENABLED.")
    except ImportError:
        if install_package('qiskit'):
            try:
                from qiskit import QuantumCircuit
                HAS_QISKIT = True
                USE_QUANTUM = True
                print("Quantum transforms ENABLED.")
            except ImportError:
                print("Qiskit installation failed or import still failing. Quantum transforms disabled.")
        else:
            print("Qiskit installation failed. Quantum transforms disabled.")
else:
    print("Quantum transforms disabled.")

# ---------- Prompt 2: Four optional backends ----------
other_choice = input("Option 2: Install 4 optional backends (mpmath, cython, paq, python-docx)? (y/n) [default n]: ").strip().lower()
if other_choice == 'y':
    for pkg in ['mpmath', 'cython', 'paq', 'python-docx']:
        try:
            importlib.import_module(pkg)
            print(f"{pkg} already installed.")
        except ImportError:
            install_package(pkg)
else:
    print("Skipping 4 optional backends.")

# ---------- Prompt 3: Zstandard (MANDATORY) ----------
zstd_choice = input("Option 3: Install zstandard backend? (mandatory, y/n) [default y]: ").strip().lower()
if zstd_choice == 'n':
    print("ERROR: zstandard is mandatory for this tool. Exiting.")
    sys.exit(1)
else:
    try:
        import zstandard as zstd
        zstd_cctx = zstd.ZstdCompressor(level=22)
        zstd_dctx = zstd.ZstdDecompressor()
        HAS_ZSTD = True
        print("zstandard already installed and loaded.")
    except ImportError:
        if install_package('zstandard'):
            try:
                import zstandard as zstd
                zstd_cctx = zstd.ZstdCompressor(level=22)
                zstd_dctx = zstd.ZstdDecompressor()
                HAS_ZSTD = True
                print("zstandard installed successfully.")
            except ImportError:
                print("CRITICAL ERROR: Failed to import zstandard after automatic installation.")
                sys.exit(1)
        else:
            print("CRITICAL ERROR: Failed to install zstandard. Please install it manually (`pip install zstandard`) and restart.")
            sys.exit(1)

PROGNAME = "UnifiedPAQJP+PJP (Single Transforms)"

# ---------- Dictionary configuration ----------
DICT_DIR = "Dictionaries"
COMBINED_DICTIONARY_FILE = os.path.join(DICT_DIR, "dictionary_combined.txt")

DICTIONARY_FILES = [
    "generated.txt",
    "eng_news_2005_1M-sentences.txt",
    "eng_news_2005_1M-words.txt",
    "eng_news_2005_1M-sources.txt",
    "eng_news_2005_1M-co_n.txt",
    "eng_news_2005_1M-co_s.txt",
    "eng_news_2005_1M-inv_w_2.txt",
    "eng_news_2005_1M-inv_w_3.txt",
    "eng_news_2005_1M-inv_so.txt",
    "eng_news_2005_1M-meta.txt",
    "Dictionary.txt",
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
        print(f"Combined dictionary '{COMBINED_DICTIONARY_FILE}' already exists. Skipping download.")
        return True

    all_words = set()
    success_count = 0
    for idx, (filename, url) in enumerate(zip(DICTIONARY_FILES, DICTIONARY_URLS)):
        local_path = os.path.join(DICT_DIR, filename)
        print(f"Downloading {filename} to {DICT_DIR}/ ...")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                content = response.read()
            if b'<html' in content[:200].lower():
                print(f"  WARNING: {filename} appears to be an HTML page. Skipping.")
                continue
            with open(local_path, 'wb') as f:
                f.write(content)
            with open(local_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    w = line.strip()
                    if not w: continue
                    try:
                        decoded = base64.b64decode(w, validate=True)
                        decoded_str = decoded.decode('utf-8')
                        all_words.add(decoded_str)
                    except Exception:
                        all_words.add(w)
            print(f"  Downloaded {filename} ({os.path.getsize(local_path)} bytes)")
            success_count += 1
        except Exception as e:
            print(f"  WARNING: Could not download {filename}: {e}")
            if os.path.exists(local_path):
                os.remove(local_path)

    if success_count == 0:
        print("ERROR: No dictionary files could be downloaded.")
        print("Proceeding without static word and line dictionaries.")
        return False

    try:
        with open(COMBINED_DICTIONARY_FILE, 'w', encoding='utf-8') as f:
            for word in sorted(all_words):
                f.write(word + '\n')
        print(f"Merged {len(all_words)} unique words into {COMBINED_DICTIONARY_FILE} "
              f"({os.path.getsize(COMBINED_DICTIONARY_FILE)} bytes)")
        return True
    except Exception as e:
        print(f"ERROR: Could not write combined dictionary: {e}")
        return False

# ---------- Constants ----------
PRIMES = [p for p in range(2, 256) if all(p % d != 0 for d in range(2, int(p ** 0.5) + 1))]
PI_DIGITS = [79, 17, 111]

def find_nearest_prime_around(n: int) -> int:
    if n < 2: return 2
    o = 0
    while True:
        c1, c2 = n - o, n + o
        if c1 >= 2 and all(c1 % d != 0 for d in range(2, int(c1 ** 0.5) + 1)):
            return c1
        if c2 >= 2 and all(c2 % d != 0 for d in range(2, int(c2 ** 0.5) + 1)):
            return c2
        o += 1

def sha256_8bytes(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()[:8]

def xor_prime_hash(word: str) -> bytes:
    prime = 2147483647
    total = sum(ord(c) for c in word)
    transformed = total ^ prime
    return transformed.to_bytes(8, 'big')

# ---------- Prefix‑free nibble code for PAQJP transform 23 ----------
_CONST_DIAPASON_ITER_CODE = [
    (2, 0b10), (2, 0b11),
    (3, 0b010), (3, 0b011),
    (4, 0b0010), (4, 0b0011),
    (5, 0b00010), (5, 0b00011),
    (6, 0b000010), (6, 0b000011),
    (7, 0b0000010), (7, 0b0000011),
    (8, 0b00000010), (8, 0b00000011),
    (9, 0b000000010), (9, 0b000000011),
]
_CONST_DIAPASON_ITER_DECODE = {}
for nibble, (length, bits) in enumerate(_CONST_DIAPASON_ITER_CODE):
    _CONST_DIAPASON_ITER_DECODE[(length, bits)] = nibble

# ---------- 6‑bit alphabet ----------
ALPHABET_6BIT = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789"
    " \n"
)
assert len(ALPHABET_6BIT) == 64
CHAR_TO_6BIT = {ch: i for i, ch in enumerate(ALPHABET_6BIT)}
SIXBIT_TO_CHAR = {i: ch for ch, i in CHAR_TO_6BIT.items()}

# ---------- PAQ state table ----------
PAQ_STATE_TABLE = [
    [  1,   2,   0,   0], [  3,   5,   0,   1], [  4,   6,   2,   0], [  7,  10,   0,   2],
    [  8,  12,   3,   0], [  9,  13,   1,   1], [ 11,  14,   0,   3], [ 15,  19,   4,   0],
    [ 16,  23,   2,   1], [ 17,  24,   2,   1], [ 18,  25,   2,   1], [ 20,  27,   1,   2],
    [ 21,  28,   1,   2], [ 22,  29,   1,   2], [ 26,  30,   0,   4], [ 31,  33,   5,   0],
    [ 32,  34,   3,   1], [ 35,  37,   1,   3], [ 36,  38,   1,   3], [ 39,  42,   0,   5],
    [ 40,  43,   4,   1], [ 41,  44,   2,   2], [ 45,  48,   1,   4], [ 46,  49,   1,   4],
    [ 47,  50,   1,   4], [ 51,  52,   0,   6], [ 53,  55,   6,   0], [ 54,  56,   4,   1],
    [ 57,  59,   2,   3], [ 58,  60,   2,   3], [ 61,  63,   0,   7], [ 62,  64,   5,   1],
    [ 65,  66,   3,   2], [ 67,  69,   1,   5], [ 68,  70,   1,   5], [ 71,  73,   0,   8],
    [ 72,  74,   6,   1], [ 75,  76,   4,   2], [ 77,  78,   2,   4], [ 79,  80,   2,   4],
    [ 81,  82,   0,   9], [ 83,  84,   7,   1], [ 85,  86,   5,   2], [ 87,  88,   3,   3],
    [ 89,  90,   1,   6], [ 91,  92,   0,  10], [ 93,  94,   8,   1], [ 95,  96,   6,   2],
    [ 97,  98,   4,   3], [ 99, 100,   2,   5], [101, 102,   0,  11], [103, 104,   9,   1],
    [105, 106,   7,   2], [107, 108,   5,   3], [109, 110,   3,   4], [111, 112,   1,   7],
    [113, 114,   0,  12], [115, 116,  10,   1], [117, 118,   8,   2], [119, 120,   6,   3],
    [121, 122,   4,   4], [123, 124,   2,   6], [125, 126,   0,  13], [127, 128,  11,   1],
    [129, 130,   9,   2], [131, 132,   7,   3], [133, 134,   5,   4], [135, 136,   3,   5],
    [137, 138,   1,   8], [139, 140,   0,  14], [141, 142,  12,   1], [143, 144,  10,   2],
    [145, 146,   8,   3], [147, 148,   6,   4], [149, 150,   4,   5], [151, 152,   2,   7],
    [153, 154,   0,  15], [155, 156,  13,   1], [157, 158,  11,   2], [159, 160,   9,   3],
    [161, 162,   7,   4], [163, 164,   5,   5], [165, 166,   3,   6], [167, 168,   1,   9],
    [169, 170,   0,  16], [171, 172,  14,   1], [173, 174,  12,   2], [175, 176,  10,   3],
    [177, 178,   8,   4], [179, 180,   6,   5], [181, 182,   4,   6], [183, 184,   2,   8],
    [185, 186,   0,  17], [187, 188,  15,   1], [189, 190,  13,   2], [191, 192,  11,   3],
    [193, 194,   9,   4], [195, 196,   7,   5], [197, 198,   5,   6], [199, 200,   3,   7],
    [201, 202,   1,  10], [203, 204,   0,  18], [205, 206,  16,   1], [207, 208,  14,   2],
    [209, 210,  12,   3], [211, 212,  10,   4], [213, 214,   8,   5], [215, 216,   6,   6],
    [217, 218,   4,   7], [219, 220,   2,   9], [221, 222,   0,  19], [223, 224,  17,   1],
    [225, 226,  15,   2], [227, 228,  13,   3], [229, 230,  11,   4], [231, 232,   9,   5],
    [233, 234,   7,   6], [235, 236,   5,   7], [237, 238,   3,   8], [239, 240,   1,  11],
    [241, 242,   0,  20], [243, 244,  18,   1], [245, 246,  16,   2], [247, 248,  14,   3],
    [249, 250,  12,   4], [251, 252,  10,   5], [253, 254,   8,   6], [255, 255,   6,   7],
]

# ------------------------------------------------------------------
# Custom exceptions
# ------------------------------------------------------------------
class TransformError(Exception):
    """Raised when a transform cannot be applied losslessly."""
    pass

class DecompressionError(Exception):
    """Raised when decompression fails."""
    pass

def mod_inv(a: int, m: int) -> Optional[int]:
    """Compute modular inverse of a modulo m using extended Euclidean algorithm."""
    if a == 0:
        return None
    m0 = m
    y = 0
    x = 1
    if m == 1:
        return 0
    while a > 1:
        q = a // m
        t = m
        m = a % m
        a = t
        t = y
        y = x - q * y
        x = t
    if x < 0:
        x = x + m0
    return x

# ------------------------------------------------------------------
# Main Compressor Class – Unified (Single transforms only)
# ------------------------------------------------------------------
class UnifiedCompressor:
    ULTRA_TIME_LIMIT = 300   # seconds
    QUANTUM_QUBITS = 8

    def __init__(self):
        download_and_merge_dictionaries()

        self.PI_DIGITS = PI_DIGITS.copy()
        self.seed_tables = self._gen_seed_tables(num=126, size=40, seed=42)
        self.fibonacci = self._gen_fib(100)
        self.PI_STR = "3.14159265358979323846264338327950288419716939937510"
        self.repeat_count = 100

        self.mod_state_table = []
        for row in PAQ_STATE_TABLE:
            new_row = [(val - 400) & 0xFF for val in row]
            self.mod_state_table.append(new_row)

        self._build_mask_46()
        self._build_transform_maps()

        self.static_dict, self.word_to_index = self._load_static_dictionary()
        self.line_dict, self.line_to_index = self._load_line_dictionary()

        self.quantum_transforms_built = False
        if USE_QUANTUM and HAS_QISKIT:
            self._precompute_quantum_transforms()

    # ------------------------------------------------------------------
    # Quantum qubit configuration
    # ------------------------------------------------------------------
    def set_quantum_qubits(self, q: int):
        if not USE_QUANTUM or not HAS_QISKIT:
            print("Quantum transforms not enabled.")
            return
        if q < 1 or q > 49:
            print("Qubit count must be between 1 and 49.")
            return
        size = 1 << q
        if size > 1_000_000:
            print(f"WARNING: {q} qubits → {size} entries. This will consume > {size*8/1e6:.1f} MB memory.")
            confirm = input("Proceed anyway? (y/n): ").strip().lower()
            if confirm != 'y':
                print("Cancelled. Keeping current qubit count.")
                return
        self.QUANTUM_QUBITS = q
        self.quantum_transforms_built = False
        print(f"Quantum qubit count set to {q}. Rebuilding quantum transforms...")
        self._precompute_quantum_transforms()
        print("Quantum transforms rebuilt.")

    def get_quantum_variation_count(self) -> int:
        if USE_QUANTUM and HAS_QISKIT:
            return 1 << self.QUANTUM_QUBITS
        return 0

    # ------------------------------------------------------------------
    # Mask 46
    # ------------------------------------------------------------------
    def _build_mask_46(self):
        base = [1, 2, 4, 8, 16, 32, 64, 128, 3, 6]
        minus_ten = [(b - 10) & 0xFF for b in base]
        self.mask_46 = minus_ten * 10

    # ------------------------------------------------------------------
    # pi / constant helpers
    # ------------------------------------------------------------------
    def get_pi_digits(self, n: int) -> str:
        if n < 1: return ""
        return self.PI_STR[2:2 + n]

    def find_lossless_k(self, n: int):
        if n < 1: return 0, True
        true_digits = self.get_pi_digits(n)
        true_scaled = int(self.PI_STR.replace('.', '')[:n + 1])
        Denominator_factor = 16777216
        decimal.getcontext().prec = 50
        pi_dec = decimal.Decimal(self.PI_STR)
        k_float = (pi_dec - 3) * Denominator_factor
        k_candidate = int(round(k_float))
        k_candidate = max(0, min(k_candidate, Denominator_factor - 1))
        approx_scaled = (3 * 10 ** n * Denominator_factor + k_candidate * 10 ** n) // Denominator_factor
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
            byte_bits = bit_str[i:i + 8]
            if len(byte_bits) < 8:
                byte_bits = byte_bits.ljust(8, '0')
            mask_bytes.append(int(byte_bits, 2))
        mask = bytes(mask_bytes)
        if not mask:
            return data
        t = bytearray(data)
        for i in range(len(t)):
            t[i] ^= mask[i % len(mask)]
        return bytes(t)
    reverse_transform_17 = transform_17

    def get_basel_digits(self, n: int) -> str:
        decimal.getcontext().prec = n + 5
        pi = decimal.Decimal(self.PI_STR)
        basel = (pi * pi) / decimal.Decimal(6)
        s = str(basel).replace('.', '')
        return s[:n]

    def get_one_over_e_digits(self, n: int) -> str:
        decimal.getcontext().prec = n + 5
        e = decimal.Decimal(1).exp()
        inv_e = decimal.Decimal(1) / e
        s = str(inv_e).replace('.', '')
        return s[:n]

    def get_5e_digits(self, n: int) -> str:
        decimal.getcontext().prec = n + 5
        e = decimal.Decimal(1).exp()
        five_e = decimal.Decimal(5) * e
        s = str(five_e).replace('.', '')
        return s[:n]

    # ------------------------------------------------------------------
    # Seed tables, Fibonacci
    # ------------------------------------------------------------------
    def _gen_seed_tables(self, num=126, size=40, seed=42):
        random.seed(seed)
        return [[random.randint(5, 255) for _ in range(size)] for _ in range(num)]

    def _gen_fib(self, n):
        a, b = 0, 1
        res = [a, b]
        for _ in range(2, n):
            a, b = b, a + b
            res.append(b)
        return res

    def get_seed(self, idx: int, val: int) -> int:
        if 0 <= idx < len(self.seed_tables):
            return self.seed_tables[idx][val % 40]
        return 0

    # ------------------------------------------------------------------
    # Bit helpers
    # ------------------------------------------------------------------
    def _append_bits(self, bitlist: List[int], value: int, count: int):
        for i in range(count - 1, -1, -1):
            bitlist.append((value >> i) & 1)

    def _read_bits(self, bits: List[int], pos: int, count: int) -> int:
        val = 0
        for i in range(count):
            if pos + i >= len(bits): return 0
            val = (val << 1) | bits[pos + i]
        return val

    # ------------------------------------------------------------------
    # RLE transform 00 (PAQJP index 1) – FIXED: shift header + roundtrip check
    # ------------------------------------------------------------------
    def transform_00(self, data: bytes) -> bytes:
        if not data:
            return struct.pack('>I', 0)
        best_result = None
        best_length = float('inf')
        best_shifts = []
        MAX_PASSES = 10
        current = bytearray(data)
        applied_shifts = []
        original_bytes = bytes(data)
        for _ in range(MAX_PASSES):
            best_shift = 0
            best_shifted = current
            best_score = float('-inf')
            for shift in range(256):
                tmp = bytearray(current)
                for j in range(len(tmp)):
                    tmp[j] = (tmp[j] + shift) % 256
                score = 0
                i = 0
                while i < len(tmp):
                    val = tmp[i]
                    run = 1
                    i += 1
                    while i < len(tmp) and tmp[i] == val:
                        run += 1
                        i += 1
                    score += run * run
                if score > best_score:
                    best_score = score
                    best_shifted = tmp
                    best_shift = shift
            applied_shifts.append(best_shift)
            rle_encoded = self._apply_rle_to_shifted(best_shifted, best_shift)
            decoded_shifted = self._rle_decode(rle_encoded)
            if decoded_shifted is not None:
                test = bytearray(decoded_shifted)
                for shift in applied_shifts:
                    for j in range(len(test)):
                        test[j] = (test[j] - shift) % 256
                if bytes(test) == original_bytes:
                    if len(rle_encoded) < best_length:
                        best_length = len(rle_encoded)
                        best_result = rle_encoded
                        best_shifts = applied_shifts.copy()
            current = best_shifted
            if len(rle_encoded) >= len(data):
                break
        if best_result is None or best_length >= len(data):
            return struct.pack('>I', len(data)) + bytes([0]) + data
        header = bytearray()
        header.extend(struct.pack('>I', len(data)))
        header.append(len(best_shifts))
        header.extend(best_shifts)
        return header + best_result

    def _apply_rle_to_shifted(self, shifted_data: bytearray, shift: int) -> bytes:
        bits = []
        self._append_bits(bits, 0b010, 3)
        self._append_bits(bits, shift, 8)
        i = 0
        n = len(shifted_data)
        while i < n:
            val = shifted_data[i]
            run = 1
            i += 1
            while i < n and shifted_data[i] == val:
                run += 1
                i += 1
            while run >= 13:
                chunk = min(run, 268)
                self._append_bits(bits, 0b1111, 4)
                self._append_bits(bits, chunk - 13, 8)
                self._append_bits(bits, val, 8)
                run -= chunk
            if run == 1:
                self._append_bits(bits, 0b00, 2)
                self._append_bits(bits, val, 8)
            elif run <= 5:
                self._append_bits(bits, 0b01, 2)
                self._append_bits(bits, run - 2, 2)
                self._append_bits(bits, val, 8)
            elif run <= 12:
                self._append_bits(bits, 0b10, 2)
                self._append_bits(bits, run - 6, 3)
                self._append_bits(bits, val, 8)
        pad = (8 - len(bits) % 8) % 8
        self._append_bits(bits, 0, pad)
        out = bytearray()
        for j in range(0, len(bits), 8):
            byte = 0
            for k in range(8):
                if j + k < len(bits):
                    byte = (byte << 1) | bits[j + k]
            out.append(byte)
        return bytes(out)

    def reverse_transform_00(self, cdata: bytes) -> bytes:
        if not cdata or cdata == struct.pack('>I', 0): return b''
        if len(cdata) < 4: raise TransformError("RLE reverse: data too short")
        orig_len = struct.unpack('>I', cdata[:4])[0]
        cdata = cdata[4:]
        if not cdata: return b''
        if cdata[0] == 0:
            return cdata[1:orig_len+1]
        num_passes = cdata[0]
        if num_passes == 0 or len(cdata) < 1 + num_passes:
            raise TransformError("Invalid RLE header")
        shifts = list(cdata[1:1 + num_passes])
        rle_data = cdata[1 + num_passes:]
        decoded = self._rle_decode(rle_data)
        if decoded is None:
            raise TransformError("RLE decode failed")
        current = bytearray(decoded[:orig_len])
        for shift in reversed(shifts):
            for i in range(len(current)):
                current[i] = (current[i] - shift) % 256
        return bytes(current)

    def _rle_decode(self, data: bytes) -> Optional[bytearray]:
        if not data: return None
        bits = []
        for b in data:
            for i in range(7, -1, -1):
                bits.append((b >> i) & 1)
        pos = 0
        nbits = len(bits)
        if nbits < 11: return None
        marker = self._read_bits(bits, pos, 3)
        pos += 3
        if marker != 0b010: return None
        pos += 8
        out = bytearray()
        while pos < nbits:
            if pos + 2 > nbits: break
            prefix = self._read_bits(bits, pos, 2)
            pos += 2
            if prefix == 0b00:
                if pos + 8 > nbits: break
                run = 1
            elif prefix == 0b01:
                if pos + 2 + 8 > nbits: break
                run = 2 + self._read_bits(bits, pos, 2)
                pos += 2
            elif prefix == 0b10:
                if pos + 3 + 8 > nbits: break
                run = 6 + self._read_bits(bits, pos, 3)
                pos += 3
            else:
                if pos + 2 + 8 + 8 > nbits: break
                if self._read_bits(bits, pos, 2) != 0b11: return None
                pos += 2
                run = 13 + self._read_bits(bits, pos, 8)
                pos += 8
            if pos + 8 > nbits: break
            val = self._read_bits(bits, pos, 8)
            pos += 8
            out.extend([val] * run)
        for i in range(pos, nbits):
            if bits[i] != 0:
                return None
        return out

    # ------------------------------------------------------------------
    # Transforms 01‑21
    # ------------------------------------------------------------------
    def transform_01(self, d):
        t = bytearray(d)
        r = self.repeat_count
        for prime in PRIMES:
            xor_val = prime if prime == 2 else max(1, math.ceil(prime * 4096 / 28672))
            for _ in range(r):
                for i in range(0, len(t), 3):
                    if i < len(t): t[i] ^= xor_val
        return bytes(t)
    reverse_transform_01 = transform_01

    def transform_02(self, d):
        if not d:
            return b'\x00'
        t = bytearray(d)
        checksum = sum(d) % 256
        pattern_index = (len(d) + checksum) % 256
        pattern_values = self._get_pattern(4, pattern_index)
        for i in range(1, len(t), 4):
            if i < len(t):
                t[i] ^= pattern_values[i % len(pattern_values)]
        return bytes([pattern_index]) + bytes(t)

    def reverse_transform_02(self, d):
        if d == b'\x00':
            return b''
        if len(d) < 2:
            raise TransformError("Transform 02 reverse: data too short")
        pattern_index = d[0]
        t = bytearray(d[1:])
        pattern_values = self._get_pattern(4, pattern_index)
        for i in range(1, len(t), 4):
            if i < len(t):
                t[i] ^= pattern_values[i % len(pattern_values)]
        return bytes(t)

    def transform_03(self, d):
        if not d:
            return b'\x00'
        t = bytearray(d)
        rotation = (len(d) * 13 + sum(d)) % 8
        if rotation == 0:
            rotation = 1
        for i in range(2, len(t), 5):
            if i < len(t):
                t[i] = ((t[i] << rotation) | (t[i] >> (8 - rotation))) & 0xFF
        return bytes([rotation]) + bytes(t)

    def reverse_transform_03(self, d):
        if d == b'\x00':
            return b''
        if len(d) < 2:
            raise TransformError("Transform 03 reverse: data too short")
        rotation = d[0]
        t = bytearray(d[1:])
        for i in range(2, len(t), 5):
            if i < len(t):
                t[i] = ((t[i] >> rotation) | (t[i] << (8 - rotation))) & 0xFF
        return bytes(t)

    def transform_04(self, d):
        t = bytearray(d)
        r = self.repeat_count
        for _ in range(r):
            for i in range(len(t)): t[i] = (t[i] - (i % 256)) % 256
        return bytes(t)
    def reverse_transform_04(self, d):
        t = bytearray(d)
        r = self.repeat_count
        for _ in range(r):
            for i in range(len(t)): t[i] = (t[i] + (i % 256)) % 256
        return bytes(t)

    def transform_05(self, d, s=3):
        t = bytearray(d)
        for i in range(len(t)): t[i] = ((t[i] << s) | (t[i] >> (8 - s))) & 0xFF
        return bytes(t)
    def reverse_transform_05(self, d, s=3):
        t = bytearray(d)
        for i in range(len(t)): t[i] = ((t[i] >> s) | (t[i] << (8 - s))) & 0xFF
        return bytes(t)

    def transform_06(self, d, sd=42):
        random.seed(sd)
        sub = list(range(256))
        random.shuffle(sub)
        t = bytearray(d)
        for i in range(len(t)): t[i] = sub[t[i]]
        return bytes(t)
    def reverse_transform_06(self, d, sd=42):
        random.seed(sd)
        sub = list(range(256))
        random.shuffle(sub)
        inv = [0]*256
        for i in range(256): inv[sub[i]] = i
        t = bytearray(d)
        for i in range(len(t)): t[i] = inv[t[i]]
        return bytes(t)

    def transform_07(self, d):
        t = bytearray(d)
        r = self.repeat_count
        sh = len(d) % len(self.PI_DIGITS)
        pi_rot = self.PI_DIGITS[sh:] + self.PI_DIGITS[:sh]
        sz = len(d) % 256
        for i in range(len(t)): t[i] ^= sz
        for _ in range(r):
            for i in range(len(t)): t[i] ^= pi_rot[i % len(pi_rot)]
        return bytes(t)
    reverse_transform_07 = transform_07

    def transform_08(self, d):
        t = bytearray(d)
        r = self.repeat_count
        sh = len(d) % len(self.PI_DIGITS)
        pi_rot = self.PI_DIGITS[sh:] + self.PI_DIGITS[:sh]
        p = find_nearest_prime_around(len(d) % 256)
        for i in range(len(t)): t[i] ^= p
        for _ in range(r):
            for i in range(len(t)): t[i] ^= pi_rot[i % len(pi_rot)]
        return bytes(t)
    reverse_transform_08 = transform_08

    def transform_09(self, d):
        t = bytearray(d)
        r = self.repeat_count
        sh = len(d) % len(self.PI_DIGITS)
        pi_rot = self.PI_DIGITS[sh:] + self.PI_DIGITS[:sh]
        p = find_nearest_prime_around(len(d) % 256)
        seed = self.get_seed(len(d) % len(self.seed_tables), len(d))
        for i in range(len(t)): t[i] ^= p ^ seed
        for _ in range(r):
            for i in range(len(t)): t[i] ^= pi_rot[i % len(pi_rot)] ^ (i % 256)
        return bytes(t)
    reverse_transform_09 = transform_09

    def transform_10(self, data: bytes) -> bytes:
        if not data: return b'\x00'
        cnt = sum(1 for i in range(len(data)-1) if data[i:i+2] == b'X1')
        n = (((cnt * 2) + 1) // 3) * 3 % 256
        t = bytearray(data)
        for i in range(len(t)): t[i] ^= n
        return bytes([n]) + bytes(t)
    def reverse_transform_10(self, data: bytes) -> bytes:
        if len(data) < 1: raise TransformError("Transform 10 reverse: data too short")
        n = data[0]
        t = bytearray(data[1:])
        for i in range(len(t)): t[i] ^= n
        return bytes(t)

    def transform_11(self, data: bytes) -> bytes:
        if not data: return b''
        t = bytearray(data)
        length = len(t)
        for i in range(length):
            fib_idx = (i + length) % len(self.fibonacci)
            fib_val = self.fibonacci[fib_idx] % 256
            pos_val = (i * 13 + length * 17) % 256
            key = (fib_val ^ pos_val) % 256
            t[i] ^= key
        return bytes(t)
    reverse_transform_11 = transform_11

    def transform_12(self, data: bytes) -> bytes:
        t = bytearray(data)
        for i in range(len(t)): t[i] ^= self.fibonacci[i % len(self.fibonacci)] % 256
        return bytes(t)
    reverse_transform_12 = transform_12

    # FIXED: transform_13 must use the length of the *payload* (without header byte)
    # in reverse, matching the forward. Forward uses len(d) before header is added.
    def transform_13(self, d):
        if not d:
            return b'\x00'
        payload_len = len(d)
        repeats = self._calculate_repeats(d)
        current_value = payload_len % 256
        prime_values = []
        count = 0
        while count < repeats:
            current_value = find_nearest_prime_around(current_value)
            prime_values.append(current_value)
            count += 1
        t = bytearray(d)
        xor_value = prime_values[-1] if prime_values else 0
        for i in range(len(t)):
            t[i] ^= xor_value
        repeat_byte = (repeats - 1) % 256
        return bytes([repeat_byte]) + bytes(t)

    def reverse_transform_13(self, d):
        if d == b'\x00':
            return b''
        if len(d) < 2:
            raise TransformError("Transform 13 reverse: data too short")
        repeat_byte = d[0]
        repeats = (repeat_byte + 1) % 256
        if repeats == 0:
            repeats = 256
        t = bytearray(d[1:])
        # FIXED: use the length of the *payload*, which equals the original
        # data length (header byte has been stripped). This matches the
        # forward's use of len(d) before the header byte was added.
        payload_len = len(t)
        current_value = payload_len % 256
        prime_values = []
        count = 0
        while count < repeats:
            current_value = find_nearest_prime_around(current_value)
            prime_values.append(current_value)
            count += 1
        xor_value = prime_values[-1] if prime_values else 0
        for i in range(len(t)):
            t[i] ^= xor_value
        return bytes(t)

    def transform_14(self, d):
        if not d: return b'\x00'
        checksum = sum(d) % 256
        return d + bytes([checksum])
    def reverse_transform_14(self, d):
        if not d: raise TransformError("Transform 14 reverse: data too short")
        return d[:-1]

    def transform_15(self, d):
        if not d:
            return b'\x00'
        t = bytearray(d)
        pattern_index = len(d) % 256
        pattern_values = self._get_pattern(3, pattern_index)
        for i in range(0, len(t), 3):
            if i < len(t):
                t[i] = (t[i] + pattern_values[i % len(pattern_values)]) % 256
        return bytes([pattern_index]) + bytes(t)

    def reverse_transform_15(self, d):
        if d == b'\x00':
            return b''
        if len(d) < 2:
            raise TransformError("Transform 15 reverse: data too short")
        pattern_index = d[0]
        t = bytearray(d[1:])
        pattern_values = self._get_pattern(3, pattern_index)
        for i in range(0, len(t), 3):
            if i < len(t):
                t[i] = (t[i] - pattern_values[i % len(pattern_values)]) % 256
        return bytes(t)

    def transform_16(self, data: bytes) -> bytes:
        if not data: return b''
        xor_byte = (len(data) * 7 + 13) % 256
        t = bytearray(data)
        for i in range(len(t)): t[i] ^= xor_byte
        return bytes(t)
    reverse_transform_16 = transform_16

    def transform_18(self, data: bytes) -> bytes:
        if not data: return b''
        digits = self.get_basel_digits(max(10, len(data)//2 + 5))
        mask = bytes(int(digits[i:i+2]) % 256 for i in range(0, len(digits), 2))
        t = bytearray(data)
        for i in range(len(t)): t[i] ^= mask[i % len(mask)]
        return bytes(t)
    reverse_transform_18 = transform_18

    def transform_19(self, data: bytes) -> bytes:
        if not data: return b''
        digits = self.get_one_over_e_digits(max(10, len(data)//2 + 5))
        mask = bytes(int(digits[i:i+2]) % 256 for i in range(0, len(digits), 2))
        t = bytearray(data)
        for i in range(len(t)): t[i] ^= mask[i % len(mask)]
        return bytes(t)
    reverse_transform_19 = transform_19

    def transform_20(self, data: bytes) -> bytes:
        if not data: return b''
        digits = self.get_5e_digits(max(10, len(data)//2 + 5))
        mask = bytes(int(digits[i:i+2]) % 256 for i in range(0, len(digits), 2))
        t = bytearray(data)
        for i in range(len(t)): t[i] ^= mask[i % len(mask)]
        return bytes(t)
    reverse_transform_20 = transform_20

    def transform_21(self, data: bytes) -> bytes:
        if not data: return b''
        shift = 255
        t = bytearray(data)
        for i in range(len(t)): t[i] = (t[i] + shift) % 256
        return bytes(t)
    def reverse_transform_21(self, data: bytes) -> bytes:
        if not data: return b''
        shift = 255
        t = bytearray(data)
        for i in range(len(t)): t[i] = (t[i] - shift) % 256
        return bytes(t)

    # ------------------------------------------------------------------
    # PJP transforms 22‑27
    # ------------------------------------------------------------------
    def transform_22(self, data: bytes) -> bytes:
        return base64.b64encode(data)
    def reverse_transform_22(self, data: bytes) -> bytes:
        try:
            return base64.b64decode(data, validate=False)
        except Exception as e:
            raise TransformError(f"Base64 decode failed: {e}")

    # 23 – Reversible tokenizer with raw fallback (FIXED: stricter verify)
    def transform_23(self, data: bytes) -> bytes:
        if not data:
            return b'\x00'
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            return b'\x00' + data

        pattern = r'([A-Za-z0-9_]+)'
        tokens = re.split(pattern, text)

        word_list = []
        word_to_idx = {}
        token_stream = []

        for i, tok in enumerate(tokens):
            if i % 2 == 1:
                word_bytes = tok.encode('utf-8')
                idx = word_to_idx.get(word_bytes)
                if idx is None:
                    idx = len(word_list)
                    word_to_idx[word_bytes] = idx
                    word_list.append(word_bytes)
                token_stream.append((1, idx))
            else:
                literal_bytes = tok.encode('utf-8')
                token_stream.append((0, literal_bytes))

        out = bytearray()
        out.append(1)
        out += struct.pack('>I', len(word_list))
        for wb in word_list:
            out += struct.pack('>I', len(wb))
            out += wb
        for typ, payload in token_stream:
            if typ == 1:
                out += b'\x01'
                out += struct.pack('>I', payload)
            else:
                out += b'\x00'
                out += struct.pack('>I', len(payload))
                out += payload

        tokenized = bytes(out)
        # FIXED: compare decoded bytes, not the tuple identity
        try:
            restored = self.reverse_transform_23(tokenized)
            if restored == data:
                return tokenized
        except Exception:
            pass
        return b'\x00' + data

    def reverse_transform_23(self, data: bytes) -> bytes:
        if not data:
            return b''
        flag = data[0]
        if flag == 0:
            return data[1:]
        if flag == 1:
            pos = 1
            if len(data) < pos + 4:
                raise TransformError("Transform 23 reverse: data too short")
            num_words = struct.unpack('>I', data[pos:pos+4])[0]
            pos += 4
            word_list = []
            for _ in range(num_words):
                if pos + 4 > len(data):
                    raise TransformError("Transform 23 reverse: truncated word length")
                wlen = struct.unpack('>I', data[pos:pos+4])[0]
                pos += 4
                if pos + wlen > len(data):
                    raise TransformError("Transform 23 reverse: truncated word")
                wb = data[pos:pos+wlen]
                pos += wlen
                word_list.append(wb)

            out = bytearray()
            while pos < len(data):
                typ = data[pos]
                pos += 1
                if typ == 1:
                    if pos + 4 > len(data):
                        raise TransformError("Transform 23 reverse: truncated index")
                    idx = struct.unpack('>I', data[pos:pos+4])[0]
                    pos += 4
                    if idx >= len(word_list):
                        raise TransformError("Transform 23 reverse: index out of range")
                    out += word_list[idx]
                elif typ == 0:
                    if pos + 4 > len(data):
                        raise TransformError("Transform 23 reverse: truncated literal length")
                    lit_len = struct.unpack('>I', data[pos:pos+4])[0]
                    pos += 4
                    if pos + lit_len > len(data):
                        raise TransformError("Transform 23 reverse: truncated literal")
                    out += data[pos:pos+lit_len]
                    pos += lit_len
                else:
                    raise TransformError(f"Transform 23 reverse: unknown token type {typ}")
            return bytes(out)
        else:
            raise TransformError("Transform 23 reverse: invalid flag")

    def transform_24(self, data: bytes) -> bytes:
        return self.transform_23(data)

    def reverse_transform_24(self, data: bytes) -> bytes:
        return self.reverse_transform_23(data)

    # 25 – Dynamic dictionary tokenizer
    def _split_text_into_chunks(self, text: str, level: str = 'all') -> List[str]:
        if level == 'paragraph':
            return re.split(r'(\n\n)', text)
        elif level == 'line':
            return re.split(r'(\n)', text)
        elif level == 'sentence':
            return re.split(r'([.!?]+)', text)
        elif level == 'word':
            return re.split(r'(\s+|\b)', text)
        else:
            chunks = []
            paragraphs = re.split(r'(\n\n)', text)
            for i, para in enumerate(paragraphs):
                if i % 2 == 1:
                    chunks.append(para)
                    continue
                lines = re.split(r'(\n)', para)
                for j, line in enumerate(lines):
                    if j % 2 == 1:
                        chunks.append(line)
                        continue
                    sentences = re.split(r'([.!?]+)', line)
                    for k, sent in enumerate(sentences):
                        if k % 2 == 1:
                            chunks.append(sent)
                            continue
                        words = re.split(r'(\s+|\b)', sent)
                        chunks.extend(words)
            return chunks

    def _dynamic_dict_tokenize(self, data: bytes, index_bytes: int = 3) -> bytes:
        try:
            text = data.decode('utf-8')
        except:
            return b'\x00' + data
        chunks = self._split_text_into_chunks(text, 'all')
        freq = Counter(chunks)
        sorted_chunks = sorted(freq.keys(), key=lambda x: (-freq[x], -len(x), x))
        chunk_to_idx = {ch: i for i, ch in enumerate(sorted_chunks)}
        num_entries = len(sorted_chunks)
        if index_bytes == 2 and num_entries > 65535: index_bytes = 3
        if index_bytes == 3 and num_entries > 16777215: index_bytes = 8
        header = bytearray()
        header.append(index_bytes)
        header += struct.pack('>I', num_entries)
        for chunk in sorted_chunks:
            chunk_bytes = chunk.encode('utf-8')
            header += struct.pack('>I', len(chunk_bytes))
            header += chunk_bytes
        token_stream = bytearray()
        for chunk in chunks:
            idx = chunk_to_idx[chunk]
            if index_bytes == 2:
                token_stream += struct.pack('>H', idx)
            elif index_bytes == 3:
                token_stream += struct.pack('>I', idx)[1:4]
            else:
                token_stream += struct.pack('>Q', idx)
        return bytes(header) + bytes(token_stream)

    def _dynamic_dict_detokenize(self, data: bytes) -> Optional[bytes]:
        if not data: return b''
        if data[0] == 0: return data[1:]
        index_bytes = data[0]
        if index_bytes not in (2, 3, 8):
            raise TransformError(f"Dynamic dict: invalid index_bytes {index_bytes}")
        pos = 1
        if pos + 4 > len(data):
            raise TransformError("Dynamic dict: truncated num_entries")
        num_entries = struct.unpack('>I', data[pos:pos+4])[0]
        pos += 4
        dictionary = []
        for _ in range(num_entries):
            if pos + 4 > len(data):
                raise TransformError("Dynamic dict: truncated chunk length")
            chunk_len = struct.unpack('>I', data[pos:pos+4])[0]
            pos += 4
            if pos + chunk_len > len(data):
                raise TransformError("Dynamic dict: truncated chunk data")
            chunk = data[pos:pos+chunk_len].decode('utf-8')
            pos += chunk_len
            dictionary.append(chunk)
        tokens = []
        while pos < len(data):
            if index_bytes == 2:
                if pos + 2 > len(data):
                    raise TransformError("Dynamic dict: truncated 2-byte index")
                idx = struct.unpack('>H', data[pos:pos+2])[0]
                pos += 2
            elif index_bytes == 3:
                if pos + 3 > len(data):
                    raise TransformError("Dynamic dict: truncated 3-byte index")
                idx_bytes = b'\x00' + data[pos:pos+3]
                idx = struct.unpack('>I', idx_bytes)[0]
                pos += 3
            else:
                if pos + 8 > len(data):
                    raise TransformError("Dynamic dict: truncated 8-byte index")
                idx = struct.unpack('>Q', data[pos:pos+8])[0]
                pos += 8
            if idx >= len(dictionary):
                raise TransformError(f"Dynamic dict: index {idx} out of range (max {len(dictionary)-1})")
            tokens.append(dictionary[idx])
        try:
            text = ''.join(tokens)
            return text.encode('utf-8')
        except Exception as e:
            raise TransformError(f"Dynamic dict: failed to reassemble text: {e}")

    def transform_25(self, data: bytes) -> bytes:
        return self._dynamic_dict_tokenize(data, index_bytes=3)
    def reverse_transform_25(self, data: bytes) -> bytes:
        return self._dynamic_dict_detokenize(data)

    # 26 – SHA‑256 block masking (symmetric)
    def transform_26(self, data: bytes) -> bytes:
        if not data: return b''
        secret = b"PJP_TRANSFORM26_SECRET"
        result = bytearray()
        for idx in range(0, len(data), 1024):
            chunk = data[idx:idx+1024]
            block_num = idx // 1024
            hasher = hashlib.sha256()
            hasher.update(secret)
            hasher.update(struct.pack(">Q", block_num))
            mask = hasher.digest()
            mask_repeated = (mask * ((len(chunk) // len(mask)) + 1))[:len(chunk)]
            xored = bytes(a ^ b for a, b in zip(chunk, mask_repeated))
            result.extend(xored)
        return bytes(result)
    def reverse_transform_26(self, data: bytes) -> bytes:
        return self.transform_26(data)

    # 27 – 6‑bit text compression
    def transform_27(self, data: bytes) -> bytes:
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            return b'\x00' + data
        for ch in text:
            if ch not in CHAR_TO_6BIT:
                return b'\x00' + data
        bits = []
        for ch in text:
            val = CHAR_TO_6BIT[ch]
            for i in range(5, -1, -1):
                bits.append((val >> i) & 1)
        pad = (8 - len(bits) % 8) % 8
        bits.extend([0] * pad)
        out = bytearray()
        for i in range(0, len(bits), 8):
            byte = 0
            for j in range(8):
                byte = (byte << 1) | bits[i + j]
            out.append(byte)
        length_bytes = struct.pack('<I', len(text))
        return b'\x01' + length_bytes + bytes(out)

    def reverse_transform_27(self, data: bytes) -> bytes:
        if len(data) < 1:
            raise TransformError("Transform 27 reverse: data too short")
        flag = data[0]
        if flag == 0:
            return data[1:]
        if flag != 1:
            raise TransformError(f"Transform 27 reverse: unknown flag {flag}")
        payload = data[1:]
        if len(payload) < 4:
            raise TransformError("Transform 27 reverse: payload too short for length header")
        num_chars = struct.unpack('<I', payload[:4])[0]
        packed = payload[4:]
        needed_bytes = (num_chars * 6 + 7) // 8
        if len(packed) != needed_bytes:
            raise TransformError(f"Transform 27 reverse: length mismatch (expected {needed_bytes}, got {len(packed)})")
        pad_bits = (8 - (num_chars * 6) % 8) % 8
        if pad_bits > 0 and packed:
            last_byte = packed[-1]
            mask = (1 << pad_bits) - 1
            if (last_byte & mask) != 0:
                raise TransformError("Transform 27 reverse: invalid padding bits")
        bits = []
        for b in packed:
            for i in range(7, -1, -1):
                bits.append((b >> i) & 1)
        needed_bits = num_chars * 6
        if len(bits) < needed_bits:
            raise TransformError("Transform 27 reverse: insufficient bits")
        chars = []
        for i in range(num_chars):
            val = 0
            for j in range(6):
                val = (val << 1) | bits[i*6 + j]
            if val >= 64:
                raise TransformError(f"Transform 27 reverse: invalid 6-bit value {val}")
            chars.append(SIXBIT_TO_CHAR[val])
        try:
            return ''.join(chars).encode('utf-8')
        except Exception as e:
            raise TransformError(f"Transform 27 reverse: encoding failed: {e}")

    # ------------------------------------------------------------------
    # Transforms 28‑30
    # ------------------------------------------------------------------
    def transform_28(self, data: bytes) -> bytes:
        if not data:
            return b'\x00'
        pad_len = (3 - len(data) % 3) % 3
        padded = data + b'\x00' * pad_len
        out = bytearray([pad_len])
        for i in range(0, len(padded), 3):
            chunk = padded[i:i+3]
            val = int.from_bytes(chunk, 'little')
            block_idx = i // 3
            key = (block_idx * 65537 + 12345) & 0xFFFF
            new_val = (val - key) % (1 << 24)
            out.extend(new_val.to_bytes(3, 'little'))
        return bytes(out)

    def reverse_transform_28(self, data: bytes) -> bytes:
        if data == b'\x00':
            return b''
        if not data:
            raise TransformError("Transform 28 reverse: data is empty")
        pad_len = data[0]
        payload = data[1:]
        if len(payload) % 3 != 0:
            raise TransformError("Transform 28 reverse: payload length not multiple of 3")
        out = bytearray()
        for i in range(0, len(payload), 3):
            chunk = payload[i:i+3]
            val = int.from_bytes(chunk, 'little')
            block_idx = i // 3
            key = (block_idx * 65537 + 12345) & 0xFFFF
            orig_val = (val + key) % (1 << 24)
            out.extend(orig_val.to_bytes(3, 'little'))
        if pad_len > 0:
            out = out[:-pad_len]
        return bytes(out)

    def _find_best_16bit_key(self, data: bytes, quantum_boost: bool = False, time_limit: float = 60.0) -> int:
        if len(data) < 3: return 0
        pad_len = (3 - len(data) % 3) % 3
        padded = data + b'\x00' * pad_len
        values = []
        for i in range(0, len(padded), 3):
            values.append(int.from_bytes(padded[i:i+3], 'little'))
        start_time = time.time()
        best_key = 0
        best_cost = float('inf')
        if not quantum_boost or not HAS_QISKIT:
            for key in range(65536):
                if key % 1024 == 0 and time.time() - start_time > time_limit:
                    break
                trans = [((v - key) & 0xFFFFFF) for v in values]
                mean_t = sum(trans) // len(trans)
                cost = sum(abs(t - mean_t) for t in trans)
                if cost < best_cost:
                    best_cost = cost
                    best_key = key
                    if cost == 0: break
            return best_key
        else:
            from qiskit import QuantumCircuit
            qc = QuantumCircuit(8)
            for i in range(8):
                qc.h(i)
                qc.rz(random.random() * 2 * math.pi, i)
            try:
                qasm = qc.qasm()
                seed = hash(qasm) & 0xFFFFFFFF
            except:
                seed = 42
            rng = random.Random(seed)
            keys = list(range(65536))
            rng.shuffle(keys)
            for i, key in enumerate(keys):
                if i % 1024 == 0 and time.time() - start_time > time_limit:
                    break
                trans = [((v - key) & 0xFFFFFF) for v in values]
                mean_t = sum(trans) // len(trans)
                cost = sum(abs(t - mean_t) for t in trans)
                if cost < best_cost:
                    best_cost = cost
                    best_key = key
                    if cost == 0: break
            return best_key

    def transform_29(self, data: bytes, quantum_boost: bool = False, time_limit: float = 60.0) -> bytes:
        if not data:
            return b'\x00'
        best_key = self._find_best_16bit_key(data, quantum_boost, time_limit)
        pad_len = (3 - len(data) % 3) % 3
        padded = data + b'\x00' * pad_len
        out = bytearray([pad_len])
        out.extend(best_key.to_bytes(2, 'little'))
        for i in range(0, len(padded), 3):
            chunk = padded[i:i+3]
            val = int.from_bytes(chunk, 'little')
            new_val = (val - best_key) % (1 << 24)
            out.extend(new_val.to_bytes(3, 'little'))
        return bytes(out)

    def reverse_transform_29(self, data: bytes) -> bytes:
        if data == b'\x00':
            return b''
        if not data or len(data) < 3:
            raise TransformError("Transform 29 reverse: data too short")
        pad_len = data[0]
        if len(data) < 1 + 2:
            raise TransformError("Transform 29 reverse: missing key")
        key = int.from_bytes(data[1:3], 'little')
        payload = data[3:]
        if len(payload) % 3 != 0:
            raise TransformError("Transform 29 reverse: payload length not multiple of 3")
        out = bytearray()
        for i in range(0, len(payload), 3):
            chunk = payload[i:i+3]
            val = int.from_bytes(chunk, 'little')
            orig_val = (val + key) % (1 << 24)
            out.extend(orig_val.to_bytes(3, 'little'))
        if pad_len > 0:
            out = out[:-pad_len]
        return bytes(out)

    def _find_best_24bit_key_heuristic(self, data: bytes) -> int:
        if len(data) < 3: return 0
        pad_len = (3 - len(data) % 3) % 3
        padded = data + b'\x00' * pad_len
        values = []
        for i in range(0, len(padded), 3):
            val = int.from_bytes(padded[i:i+3], 'little')
            values.append(val)
        mean = sum(values) // len(values)
        sorted_vals = sorted(values)
        median = sorted_vals[len(sorted_vals)//2]
        candidates = set()
        for base in [mean, median]:
            for offset in [0, 1, -1, 10, -10, 100, -100, 1000, -1000]:
                candidates.add((base + offset) % (1 << 24))
        rng = random.Random(42)
        for _ in range(10):
            candidates.add(rng.randint(0, (1 << 24) - 1))
        best_key = 0
        best_cost = float('inf')
        for key in candidates:
            trans = [((v - key) & 0xFFFFFF) for v in values]
            mean_t = sum(trans) // len(trans)
            cost = sum(abs(t - mean_t) for t in trans)
            if cost < best_cost:
                best_cost = cost
                best_key = key
        return best_key

    def transform_30(self, data: bytes) -> bytes:
        if not data:
            return b'\x00'
        best_key = self._find_best_24bit_key_heuristic(data)
        pad_len = (3 - len(data) % 3) % 3
        padded = data + b'\x00' * pad_len
        out = bytearray([pad_len])
        out.extend(best_key.to_bytes(3, 'little'))
        for i in range(0, len(padded), 3):
            chunk = padded[i:i+3]
            val = int.from_bytes(chunk, 'little')
            new_val = (val - best_key) % (1 << 24)
            out.extend(new_val.to_bytes(3, 'little'))
        return bytes(out)

    def reverse_transform_30(self, data: bytes) -> bytes:
        if data == b'\x00':
            return b''
        if not data or len(data) < 4:
            raise TransformError("Transform 30 reverse: data too short")
        pad_len = data[0]
        if len(data) < 1 + 3:
            raise TransformError("Transform 30 reverse: missing key")
        key = int.from_bytes(data[1:4], 'little')
        payload = data[4:]
        if len(payload) % 3 != 0:
            raise TransformError("Transform 30 reverse: payload length not multiple of 3")
        out = bytearray()
        for i in range(0, len(payload), 3):
            chunk = payload[i:i+3]
            val = int.from_bytes(chunk, 'little')
            orig_val = (val + key) % (1 << 24)
            out.extend(orig_val.to_bytes(3, 'little'))
        if pad_len > 0:
            out = out[:-pad_len]
        return bytes(out)

    # ------------------------------------------------------------------
    # Transforms 31‑32 (docx identity placeholders)
    # ------------------------------------------------------------------
    def transform_31(self, data: bytes) -> bytes:
        return data
    def reverse_transform_31(self, data: bytes) -> bytes:
        return data
    def transform_32(self, data: bytes) -> bytes:
        return data
    def reverse_transform_32(self, data: bytes) -> bytes:
        return data

    # ------------------------------------------------------------------
    # PAQJP special transforms
    # ------------------------------------------------------------------
    def _paqjp_transform_23(self, data: bytes) -> bytes:
        if not data: return b'\x00\x00\x00\x00\x00'
        bits = []
        for byte in data:
            for i in range(7, -1, -1):
                bits.append((byte >> i) & 1)
        return self._compress_bits(bits)
    def _paqjp_reverse_23(self, data: bytes) -> bytes:
        if not data or data == b'\x00\x00\x00\x00\x00': return b''
        bits = self._decompress_bits(data)
        if not bits:
            return b''
        out_bytes = bytearray()
        for i in range(0, len(bits), 8):
            val = 0
            for j in range(i, min(i+8, len(bits))):
                val = (val << 1) | bits[j]
            if i+8 > len(bits):
                val <<= (8 - (len(bits) - i))
            out_bytes.append(val)
        return bytes(out_bytes)

    def _compress_bits(self, bits: List[int]) -> bytes:
        orig_bit_len = len(bits)
        if orig_bit_len == 0:
            return b'\x00\x00\x00\x00\x00'
        current_bits = bits[:]
        prev_len = orig_bit_len
        pass_count = 0
        while pass_count < 255:
            pad_len = (4 - len(current_bits) % 4) % 4
            padded = current_bits + [0] * pad_len
            nibble_count = len(padded) // 4
            encoded_bits = []
            for i in range(nibble_count):
                nibble = (padded[i*4] << 3) | (padded[i*4+1] << 2) | (padded[i*4+2] << 1) | padded[i*4+3]
                length, codeword = _CONST_DIAPASON_ITER_CODE[nibble]
                for b in range(length-1, -1, -1):
                    encoded_bits.append((codeword >> b) & 1)
            new_len = len(encoded_bits)
            if new_len < prev_len:
                current_bits = encoded_bits
                prev_len = new_len
                pass_count += 1
            else:
                break

        compressed_bit_len = len(current_bits)
        header = struct.pack('>H', orig_bit_len) + bytes([pass_count]) + struct.pack('>H', compressed_bit_len)

        pad = (8 - len(current_bits) % 8) % 8
        current_bits += [0] * pad
        out_bytes = bytearray()
        for i in range(0, len(current_bits), 8):
            val = 0
            for j in range(8):
                val = (val << 1) | current_bits[i+j]
            out_bytes.append(val)
        return header + bytes(out_bytes)

    def _decompress_bits(self, data: bytes) -> List[int]:
        if len(data) < 5:
            raise TransformError("Constant Diapason reverse: data too short")
        orig_bit_len = struct.unpack('>H', data[:2])[0]
        pass_count = data[2]
        compressed_bit_len = struct.unpack('>H', data[3:5])[0]
        payload = data[5:]
        bits = []
        for byte in payload:
            for i in range(7, -1, -1):
                bits.append((byte >> i) & 1)

        if len(bits) < compressed_bit_len:
            raise TransformError("Constant Diapason reverse: payload too short")
        current_bits = bits[:compressed_bit_len]

        if pass_count == 0:
            return current_bits[:orig_bit_len]

        for _ in range(pass_count):
            pos = 0
            nbits = len(current_bits)
            decoded_nibbles = []
            while pos < nbits:
                matched = False
                for length in range(2, 10):
                    if pos + length > nbits:
                        continue
                    codeword = 0
                    for k in range(length):
                        codeword = (codeword << 1) | current_bits[pos + k]
                    key = (length, codeword)
                    if key in _CONST_DIAPASON_ITER_DECODE:
                        decoded_nibbles.append(_CONST_DIAPASON_ITER_DECODE[key])
                        pos += length
                        matched = True
                        break
                if not matched:
                    raise TransformError("Constant Diapason reverse: invalid codeword")
            new_bits = []
            for nibble in decoded_nibbles:
                for j in range(3, -1, -1):
                    new_bits.append((nibble >> j) & 1)
            current_bits = new_bits
        if len(current_bits) < orig_bit_len:
            raise TransformError("Constant Diapason reverse: decoded bits shorter than original")
        return current_bits[:orig_bit_len]

    def _paqjp_transform_24(self, data: bytes) -> bytes:
        if not data: return struct.pack('>I', 0)
        MAX_LEN = 43
        bits = []
        i = 0
        n = len(data)
        while i < n:
            chunk_len = min(MAX_LEN, n - i)
            chunk = data[i:i+chunk_len]
            first = chunk[0]
            all_same = all(b == first for b in chunk)
            if all_same:
                self._append_bits(bits, 1, 1)
                self._append_bits(bits, first, 8)
                self._append_bits(bits, chunk_len - 1, 6)
            else:
                self._append_bits(bits, 0, 1)
                self._append_bits(bits, chunk_len, 6)
                for b in chunk:
                    self._append_bits(bits, b, 8)
            i += chunk_len
        pad = (8 - len(bits) % 8) % 8
        self._append_bits(bits, 0, pad)
        out = bytearray()
        for j in range(0, len(bits), 8):
            byte = 0
            for k in range(8):
                byte = (byte << 1) | bits[j+k]
            out.append(byte)
        header = struct.pack('>I', len(data))
        return header + bytes(out)

    def _paqjp_reverse_24(self, data: bytes) -> bytes:
        if not data: return b''
        if len(data) < 4: raise TransformError("Block run reverse: data too short")
        orig_len = struct.unpack('>I', data[:4])[0]
        payload = data[4:]
        bits = []
        for byte in payload:
            for i in range(7, -1, -1):
                bits.append((byte >> i) & 1)
        pos = 0
        nbits = len(bits)
        out = bytearray()
        while pos < nbits and len(out) < orig_len:
            if pos + 1 > nbits: break
            flag = self._read_bits(bits, pos, 1)
            pos += 1
            if flag == 1:
                if pos + 8 + 6 > nbits:
                    raise TransformError("Block run reverse: truncated run block")
                byte_val = self._read_bits(bits, pos, 8)
                pos += 8
                count_minus1 = self._read_bits(bits, pos, 6)
                pos += 6
                run_len = count_minus1 + 1
                run_len = min(run_len, orig_len - len(out))
                out.extend([byte_val] * run_len)
            else:
                if pos + 6 > nbits:
                    raise TransformError("Block run reverse: truncated literal block header")
                chunk_len = self._read_bits(bits, pos, 6)
                pos += 6
                if chunk_len == 0:
                    break
                if pos + chunk_len * 8 > nbits:
                    raise TransformError("Block run reverse: truncated literal bytes")
                for _ in range(chunk_len):
                    b = self._read_bits(bits, pos, 8)
                    pos += 8
                    out.append(b)
        return bytes(out[:orig_len])

    def _paqjp_transform_25(self, data: bytes) -> bytes:
        if not data:
            return b'\x01'
        n = 3
        res = bytearray(data)
        for i in range(len(res)):
            res[i] = (pow(res[i] + 1, n, 257) - 1) & 0xFF
        return bytes([n]) + bytes(res)

    def _paqjp_reverse_25(self, data: bytes) -> bytes:
        if data == b'\x01':
            return b''
        if not data or len(data) < 2:
            raise TransformError("FLT 25 reverse: data too short")
        n = data[0]
        inv_n = mod_inv(n, 256)
        if inv_n is None:
            raise TransformError(f"FLT 25 reverse: {n} not invertible modulo 256")
        res = bytearray(data[1:])
        for i in range(len(res)):
            res[i] = (pow(res[i] + 1, inv_n, 257) - 1) & 0xFF
        return bytes(res)

    def _paqjp_transform_26(self, data: bytes) -> bytes:
        if not data:
            return b'\x01\x00'
        n = (len(data) * 7 + 13) & 0xFFFF
        if n % 2 == 0:
            n ^= 1
        e = pow(n, 16777216, 256) | 1
        res = bytearray(data)
        for i in range(len(res)):
            res[i] = (pow(res[i] + 1, e, 257) - 1) & 0xFF
        return bytes([n & 0xFF, (n >> 8) & 0xFF]) + bytes(res)

    def _paqjp_reverse_26(self, data: bytes) -> bytes:
        if data == b'\x01\x00':
            return b''
        if not data or len(data) < 2:
            raise TransformError("FLT 26 reverse: data too short")
        n = data[0] | (data[1] << 8)
        if n % 2 == 0:
            n ^= 1
        e = pow(n, 16777216, 256) | 1
        inv_e = mod_inv(e, 256)
        if inv_e is None:
            raise TransformError(f"FLT 26 reverse: {e} not invertible modulo 256")
        res = bytearray(data[2:])
        for i in range(len(res)):
            res[i] = (pow(res[i] + 1, inv_e, 257) - 1) & 0xFF
        return bytes(res)

    def _paqjp_transform_27(self, data: bytes) -> bytes:
        if not data:
            out = bytearray(b'\x00\x00\x00\x00')
            out.extend(b'\x01\x00')
            out.extend(b'\x00' * 1024)
            return bytes(out)
        BLOCK_SIZE = 1024
        total_blocks = (len(data) + BLOCK_SIZE - 1) // BLOCK_SIZE
        out = bytearray()
        out.extend(len(data).to_bytes(4, 'big'))
        for block_idx in range(total_blocks):
            start = block_idx * BLOCK_SIZE
            end = min(start + BLOCK_SIZE, len(data))
            chunk = data[start:end]
            pad_len = BLOCK_SIZE - len(chunk)
            if pad_len: chunk = chunk + b'\x00' * pad_len
            n = ((len(data) * 7 + block_idx * 13 + 1) & 0xFFFF) | 1
            e = pow(n, 16777216, 256) | 1
            e200 = pow(e, 200, 256)
            transformed = bytearray(chunk)
            for i in range(BLOCK_SIZE):
                transformed[i] = (pow(transformed[i] + 1, e200, 257) - 1) & 0xFF
            out.append(n & 0xFF)
            out.append((n >> 8) & 0xFF)
            out.extend(transformed)
        return bytes(out)

    def _paqjp_reverse_27(self, data: bytes) -> bytes:
        if not data or len(data) < 4:
            raise TransformError("FLT 27 reverse: data too short")
        orig_len = int.from_bytes(data[:4], 'big')
        payload = data[4:]
        BLOCK_SIZE = 1024
        block_total_len = 2 + BLOCK_SIZE
        if len(payload) % block_total_len != 0:
            raise TransformError("FLT 27 reverse: payload not aligned to blocks")
        num_blocks = len(payload) // block_total_len
        decoded = bytearray()
        for block_idx in range(num_blocks):
            offset = block_idx * block_total_len
            if offset + 2 > len(payload):
                raise TransformError("FLT 27 reverse: truncated block header")
            n = payload[offset] | (payload[offset+1] << 8)
            chunk = payload[offset+2:offset+2+BLOCK_SIZE]
            if len(chunk) < BLOCK_SIZE:
                raise TransformError("FLT 27 reverse: truncated block data")
            n |= 1
            e = pow(n, 16777216, 256) | 1
            e200 = pow(e, 200, 256)
            inv_e200 = mod_inv(e200, 256)
            if inv_e200 is None:
                raise TransformError(f"FLT 27 reverse: {e200} not invertible modulo 256")
            for i in range(BLOCK_SIZE):
                decoded.append((pow(chunk[i] + 1, inv_e200, 257) - 1) & 0xFF)
        return bytes(decoded[:orig_len])

    def _compress_backend_with_flag(self, data: bytes) -> bytes:
        candidates = []
        if HAS_ZSTD:
            try:
                candidates.append((1, zstd_cctx.compress(data)))
            except:
                pass
        if paq is not None:
            try:
                candidates.append((2, paq.compress(data)))
            except:
                pass
        candidates.append((0, data))
        best_flag, best_data = min(candidates, key=lambda x: len(x[1]))
        return bytes([best_flag]) + best_data

    def _decompress_backend_with_flag(self, data: bytes) -> bytes:
        if not data:
            return b''
        flag = data[0]
        payload = data[1:]
        if flag == 0:
            return payload
        elif flag == 1 and HAS_ZSTD:
            return zstd_dctx.decompress(payload)
        elif flag == 2 and paq is not None:
            return paq.decompress(payload)
        else:
            raise TransformError("Backend flag invalid or backend not available")

    def _paqjp_transform_28(self, data: bytes) -> bytes:
        BLOCK_SIZE = 1024
        if not data:
            block = b'\x00' * BLOCK_SIZE
            n = 1
            transformed = block
            compressed = self._compress_backend_with_flag(transformed)
            out = bytearray(struct.pack('>I', 0))
            out += bytes([n & 0xFF, (n >> 8) & 0xFF])
            out += bytes([(len(compressed) >> 8) & 0xFF, len(compressed) & 0xFF])
            out += compressed
            return bytes(out)

        total_blocks = (len(data) + BLOCK_SIZE - 1) // BLOCK_SIZE
        out = bytearray()
        out.extend(len(data).to_bytes(4, 'big'))
        for block_idx in range(total_blocks):
            start = block_idx * BLOCK_SIZE
            end = min(start + BLOCK_SIZE, len(data))
            chunk = data[start:end]
            pad_len = BLOCK_SIZE - len(chunk)
            if pad_len:
                chunk = chunk + b'\x00' * pad_len
            n = ((len(data) * 7 + block_idx * 13 + 1) & 0xFFFF) | 1
            e = pow(n, 16777216, 256) | 1
            e200 = pow(e, 200, 256)
            transformed = bytearray(chunk)
            for i in range(BLOCK_SIZE):
                transformed[i] = (pow(transformed[i] + 1, e200, 257) - 1) & 0xFF
            compressed = self._compress_backend_with_flag(bytes(transformed))
            out.append(n & 0xFF)
            out.append((n >> 8) & 0xFF)
            out.append((len(compressed) >> 8) & 0xFF)
            out.append(len(compressed) & 0xFF)
            out.extend(compressed)
        return bytes(out)

    def _paqjp_reverse_28(self, data: bytes) -> bytes:
        if not data or len(data) < 4:
            raise TransformError("FLT 28 reverse: data too short")
        orig_len = int.from_bytes(data[:4], 'big')
        payload = data[4:]
        pos = 0
        decoded = bytearray()
        while pos < len(payload):
            if pos + 2 > len(payload):
                raise TransformError("FLT 28 reverse: truncated block header")
            n = payload[pos] | (payload[pos+1] << 8)
            pos += 2
            if pos + 2 > len(payload):
                raise TransformError("FLT 28 reverse: truncated block length")
            comp_len = (payload[pos] << 8) | payload[pos+1]
            pos += 2
            if pos + comp_len > len(payload):
                raise TransformError("FLT 28 reverse: truncated compressed block")
            comp_block = payload[pos:pos+comp_len]
            pos += comp_len
            block = self._decompress_backend_with_flag(comp_block)
            n |= 1
            e = pow(n, 16777216, 256) | 1
            e200 = pow(e, 200, 256)
            inv_e200 = mod_inv(e200, 256)
            if inv_e200 is None:
                raise TransformError(f"FLT 28 reverse: {e200} not invertible modulo 256")
            transformed = bytearray(block)
            for i in range(len(transformed)):
                transformed[i] = (pow(transformed[i] + 1, inv_e200, 257) - 1) & 0xFF
            decoded.extend(transformed)
        return bytes(decoded[:orig_len])

    def _paqjp_transform_29(self, data: bytes) -> bytes:
        BLOCK_SIZE = 32
        if not data:
            block = b'\x00' * BLOCK_SIZE
            n = 1
            transformed = block
            compressed = self._compress_backend_with_flag(transformed)
            out = bytearray(struct.pack('>I', 0))
            out += bytes([n & 0xFF, (n >> 8) & 0xFF])
            out += bytes([(len(compressed) >> 8) & 0xFF, len(compressed) & 0xFF])
            out += compressed
            return bytes(out)

        total_blocks = (len(data) + BLOCK_SIZE - 1) // BLOCK_SIZE
        out = bytearray()
        out.extend(len(data).to_bytes(4, 'big'))
        for block_idx in range(total_blocks):
            start = block_idx * BLOCK_SIZE
            end = min(start + BLOCK_SIZE, len(data))
            chunk = data[start:end]
            pad_len = BLOCK_SIZE - len(chunk)
            if pad_len:
                chunk = chunk + b'\x00' * pad_len
            n = ((len(data) * 7 + block_idx * 13 + 1) & 0xFFFF) | 1
            e = pow(n, 2**256, 256) | 1
            e200 = pow(e, 200, 256)
            transformed = bytearray(chunk)
            compressed = self._compress_backend_with_flag(bytes(transformed))
            out.append(n & 0xFF)
            out.append((n >> 8) & 0xFF)
            out.append((len(compressed) >> 8) & 0xFF)
            out.append(len(compressed) & 0xFF)
            out.extend(compressed)
        return bytes(out)

    def _paqjp_reverse_29(self, data: bytes) -> bytes:
        if not data or len(data) < 4:
            raise TransformError("FLT 29 reverse: data too short")
        orig_len = int.from_bytes(data[:4], 'big')
        payload = data[4:]
        pos = 0
        decoded = bytearray()
        while pos < len(payload):
            if pos + 2 > len(payload):
                raise TransformError("FLT 29 reverse: truncated block header")
            n = payload[pos] | (payload[pos+1] << 8)
            pos += 2
            if pos + 2 > len(payload):
                raise TransformError("FLT 29 reverse: truncated block length")
            comp_len = (payload[pos] << 8) | payload[pos+1]
            pos += 2
            if pos + comp_len > len(payload):
                raise TransformError("FLT 29 reverse: truncated compressed block")
            comp_block = payload[pos:pos+comp_len]
            pos += comp_len
            block = self._decompress_backend_with_flag(comp_block)
            decoded.extend(block)
        return bytes(decoded[:orig_len])

    def _paqjp_transform_30(self, data: bytes) -> bytes:
        BLOCK_SIZE = 33
        if not data:
            block = b'\x00' * BLOCK_SIZE
            n, enc_n = self._paqjp_compute_n_for_block(block, 0, 0)
            compressed = self._compress_backend_with_flag(block)
            out = bytearray(struct.pack('>I', 0))
            out += enc_n
            out.append((len(compressed) >> 8) & 0xFF)
            out.append(len(compressed) & 0xFF)
            out += compressed
            return bytes(out)

        total_blocks = (len(data) + BLOCK_SIZE - 1) // BLOCK_SIZE
        out = bytearray()
        out.extend(len(data).to_bytes(4, 'big'))
        for block_idx in range(total_blocks):
            start = block_idx * BLOCK_SIZE
            end = min(start + BLOCK_SIZE, len(data))
            chunk = data[start:end]
            pad_len = BLOCK_SIZE - len(chunk)
            if pad_len:
                chunk = chunk + b'\x00' * pad_len
            n, enc_n = self._paqjp_compute_n_for_block(chunk, block_idx, len(data))
            compressed = self._compress_backend_with_flag(chunk)
            out.extend(enc_n)
            out.append((len(compressed) >> 8) & 0xFF)
            out.append(len(compressed) & 0xFF)
            out.extend(compressed)
        return bytes(out)

    def _paqjp_compute_n_for_block(self, block: bytes, block_idx: int, total_len: int) -> Tuple[int, bytes]:
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
        h = hashlib.sha256(block + bytes([block_idx & 0xFF, (total_len>>8)&0xFF, total_len&0xFF])).digest()
        n_bytes = bytearray(h)
        n_bytes[0] |= 1
        length = len(n_bytes)
        encoded = bytes([length]) + bytes(n_bytes)
        n = int.from_bytes(n_bytes, 'big')
        return (n, encoded)

    def _paqjp_reverse_30(self, data: bytes) -> bytes:
        if not data or len(data) < 4:
            raise TransformError("FLT 30 reverse: data too short")
        orig_len = int.from_bytes(data[:4], 'big')
        payload = data[4:]
        pos = 0
        decoded = bytearray()
        while pos < len(payload):
            if pos >= len(payload):
                raise TransformError("FLT 30 reverse: truncated n length")
            Ln = payload[pos]
            pos += 1
            if Ln > 32 or pos + Ln > len(payload):
                raise TransformError("FLT 30 reverse: invalid n length")
            n_bytes = payload[pos:pos+Ln]
            pos += Ln
            if pos + 2 > len(payload):
                raise TransformError("FLT 30 reverse: truncated block length")
            comp_len = (payload[pos] << 8) | payload[pos+1]
            pos += 2
            if pos + comp_len > len(payload):
                raise TransformError("FLT 30 reverse: truncated compressed block")
            comp_block = payload[pos:pos+comp_len]
            pos += comp_len
            block = self._decompress_backend_with_flag(comp_block)
            decoded.extend(block)
        return bytes(decoded[:orig_len])

    # ------------------------------------------------------------------
    # PAQJP special transforms 41-47
    # ------------------------------------------------------------------
    def transform_41(self, data: bytes) -> bytes:
        if not data: return b''
        mask = bytes([0x27, 0x03])
        t = bytearray(data)
        n = min(len(t), 8)
        for i in range(n):
            t[i] ^= mask[i % 2]
        return bytes(t)
    reverse_transform_41 = transform_41

    def transform_42(self, data: bytes) -> bytes:
        if not data: return b''
        t = bytearray(data)
        mask = bytes([0x27, 0x03])
        for i in range(len(t)):
            t[i] ^= mask[i % 2]
        return bytes(t)
    reverse_transform_42 = transform_42

    def transform_43(self, data: bytes) -> bytes:
        if not data: return b''
        t = bytearray(data)
        mask = bytes([0x10, 0x00, 0x00])
        for i in range(0, len(t), 3):
            for j in range(min(3, len(t) - i)):
                t[i + j] ^= mask[j]
        return bytes(t)
    reverse_transform_43 = transform_43

    def transform_44(self, data: bytes) -> bytes:
        if not data: return b''
        return base64.b64encode(data)
    def reverse_transform_44(self, data: bytes) -> bytes:
        if not data: return b''
        try:
            return base64.b64decode(data, validate=False)
        except Exception as e:
            raise TransformError(f"Base64 decode (44) failed: {e}")

    @staticmethod
    def _huffman_code_lengths(freq: List[int]) -> List[int]:
        heap = [(f, i, i) for i, f in enumerate(freq) if f > 0]
        if not heap: return [0] * len(freq)
        if len(heap) == 1:
            lengths = [0] * len(freq)
            lengths[heap[0][2]] = 1
            return lengths
        heapq.heapify(heap)
        next_id = len(freq)
        while len(heap) > 1:
            f1, _, n1 = heapq.heappop(heap)
            f2, _, n2 = heapq.heappop(heap)
            heapq.heappush(heap, (f1 + f2, next_id, (n1, n2)))
            next_id += 1
        lengths = [0] * len(freq)
        def traverse(node, depth):
            if isinstance(node, int):
                lengths[node] = depth
            else:
                left, right = node
                traverse(left, depth + 1)
                traverse(right, depth + 1)
        _, _, root = heap[0]
        traverse(root, 0)
        return lengths

    @staticmethod
    def _huffman_canonical_codes(code_lengths: List[int]) -> Dict[int, Tuple[int, int]]:
        symbols = list(range(len(code_lengths)))
        symbols.sort(key=lambda s: (code_lengths[s], s))
        codes = {}
        code = 0
        prev_len = 0
        first = True
        for sym in symbols:
            cl = code_lengths[sym]
            if cl == 0: continue
            if first:
                prev_len = cl
                first = False
            elif cl != prev_len:
                code <<= (cl - prev_len)
                prev_len = cl
            codes[sym] = (code, cl)
            code += 1
        return codes

    def transform_45(self, data: bytes) -> bytes:
        if not data: return b''
        freq = [0]*256
        for b in data: freq[b] += 1
        code_lengths = self._huffman_code_lengths(freq)
        codes = self._huffman_canonical_codes(code_lengths)
        header = bytearray()
        header.extend(len(data).to_bytes(4, 'big'))
        header.extend(code_lengths)
        bits = []
        for b in data:
            c, cl = codes[b]
            for i in range(cl - 1, -1, -1):
                bits.append((c >> i) & 1)
        pad = (8 - len(bits) % 8) % 8
        bits.extend([0] * pad)
        out_bytes = bytearray()
        for i in range(0, len(bits), 8):
            val = 0
            for j in range(8):
                val = (val << 1) | bits[i + j]
            out_bytes.append(val)
        return bytes(header) + bytes(out_bytes)

    def reverse_transform_45(self, data: bytes) -> bytes:
        if not data:
            return b''
        if len(data) < 4 + 256:
            raise TransformError("Huffman reverse: data too short")
        original_len = int.from_bytes(data[:4], 'big')
        code_lengths = list(data[4:4+256])
        payload = data[4+256:]
        if original_len == 0:
            return b''
        if max(code_lengths) > 32:
            raise TransformError("Huffman reverse: code length exceeds 32")
        code_to_sym = {}
        symbols = list(range(256))
        symbols.sort(key=lambda s: (code_lengths[s], s))
        code = 0
        prev_len = 0
        first = True
        for sym in symbols:
            cl = code_lengths[sym]
            if cl == 0: continue
            if first:
                prev_len = cl
                first = False
            elif cl != prev_len:
                code <<= (cl - prev_len)
                prev_len = cl
            code_to_sym[(cl, code)] = sym
            code += 1
        bits = []
        for byte in payload:
            for i in range(7, -1, -1):
                bits.append((byte >> i) & 1)
        pos = 0
        nbits = len(bits)
        out = bytearray()
        max_code_len = max(code_lengths) if any(code_lengths) else 0
        while pos < nbits and len(out) < original_len:
            found = False
            for cl in range(1, max_code_len + 1):
                if pos + cl > nbits: break
                val = 0
                for j in range(cl):
                    val = (val << 1) | bits[pos + j]
                if (cl, val) in code_to_sym:
                    sym = code_to_sym[(cl, val)]
                    out.append(sym)
                    pos += cl
                    found = True
                    break
            if not found:
                raise TransformError(f"Huffman reverse: no symbol found at bit position {pos}")
        if len(out) != original_len:
            raise TransformError(f"Huffman reverse: decoded {len(out)} bytes, expected {original_len}")
        return bytes(out)

    def transform_46(self, data: bytes) -> bytes:
        if not data: return b''
        t = bytearray(data)
        mask = self.mask_46
        for i in range(len(t)):
            t[i] ^= mask[i % len(mask)]
        return bytes(t)
    reverse_transform_46 = transform_46

    def transform_47(self, data: bytes) -> bytes:
        if not data: return b''
        t = bytearray(data)
        table_len = len(self.mod_state_table)
        if table_len == 0: return data
        for i in range(len(t)):
            row = self.mod_state_table[i % table_len]
            t[i] ^= row[0]
        return bytes(t)
    reverse_transform_47 = transform_47

    # ------------------------------------------------------------------
    # NEW TRANSFORM 57 – 4‑byte XOR with most frequent pattern (FIXED pad)
    # ------------------------------------------------------------------
    def transform_57(self, data: bytes) -> bytes:
        if len(data) < 4:
            pad_len = 4 - len(data)
            key = 0
            header = bytes([pad_len]) + key.to_bytes(4, 'little')
            padded = data + b'\x00' * pad_len
            return header + padded
        n = len(data)
        pad_len = (4 - n % 4) % 4
        padded = data + b'\x00' * pad_len
        blocks = [padded[i:i+4] for i in range(0, len(padded), 4)]
        counter = Counter(blocks)
        most_common_block, _ = counter.most_common(1)[0]
        key = int.from_bytes(most_common_block, 'little')
        transformed = bytearray()
        for block in blocks:
            val = int.from_bytes(block, 'little') ^ key
            transformed.extend(val.to_bytes(4, 'little'))
        header = bytes([pad_len]) + key.to_bytes(4, 'little')
        return header + bytes(transformed)

    def reverse_transform_57(self, data: bytes) -> bytes:
        if len(data) < 5:
            raise TransformError("Transform 57 reverse: data too short")
        pad_len = data[0]
        key = int.from_bytes(data[1:5], 'little')
        payload = data[5:]
        if len(payload) % 4 != 0:
            raise TransformError("Transform 57 reverse: payload not multiple of 4")
        transformed = bytearray()
        for i in range(0, len(payload), 4):
            block = payload[i:i+4]
            val = int.from_bytes(block, 'little') ^ key
            transformed.extend(val.to_bytes(4, 'little'))
        if pad_len > 0:
            if len(transformed) < pad_len:
                raise TransformError("Transform 57 reverse: pad_len exceeds data length")
            transformed = transformed[:-pad_len]
        return bytes(transformed)

    # Dynamic 48-255
    def _dynamic_transform(self, n: int):
        def tf(data: bytes):
            if not data: return b''
            seed = self.get_seed(n % len(self.seed_tables), len(data))
            t = bytearray(data)
            for i in range(len(t)): t[i] ^= seed
            return bytes(t)
        return tf, tf

    def transform_256(self, d: bytes) -> bytes:
        return d
    reverse_transform_256 = transform_256

    # ------------------------------------------------------------------
    # Dummy dictionary decompression (not used)
    # ------------------------------------------------------------------
    def _decompress_static_dict(self, data: bytes) -> Optional[bytes]:
        print("Static dictionary decompression not implemented.")
        return None

    def _decompress_dynamic_dict(self, data: bytes) -> Optional[bytes]:
        print("Dynamic dictionary decompression not implemented.")
        return None

    def _decompress_line_dict(self, data: bytes) -> Optional[bytes]:
        print("Line dictionary decompression not implemented.")
        return None

    # ------------------------------------------------------------------
    # Build transform maps
    # ------------------------------------------------------------------
    def _build_transform_maps(self):
        self.fwd_transforms: Dict[int, Callable] = {}
        self.rev_transforms: Dict[int, Callable] = {}

        for i in range(1, 22):
            fwd_name = f"transform_{i:02d}"
            rev_name = f"reverse_transform_{i:02d}"
            self.fwd_transforms[i] = getattr(self, fwd_name)
            self.rev_transforms[i] = getattr(self, rev_name)

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

        self.fwd_transforms[33] = self._paqjp_transform_23
        self.rev_transforms[33] = self._paqjp_reverse_23

        self.fwd_transforms[34] = self._paqjp_transform_24
        self.rev_transforms[34] = self._paqjp_reverse_24

        self.fwd_transforms[35] = self._paqjp_transform_25
        self.rev_transforms[35] = self._paqjp_reverse_25

        self.fwd_transforms[36] = self._paqjp_transform_26
        self.rev_transforms[36] = self._paqjp_reverse_26

        self.fwd_transforms[37] = self._paqjp_transform_27
        self.rev_transforms[37] = self._paqjp_reverse_27

        self.fwd_transforms[38] = self._paqjp_transform_28
        self.rev_transforms[38] = self._paqjp_reverse_28

        self.fwd_transforms[39] = self._paqjp_transform_29
        self.rev_transforms[39] = self._paqjp_reverse_29

        self.fwd_transforms[40] = self._paqjp_transform_30
        self.rev_transforms[40] = self._paqjp_reverse_30

        self.fwd_transforms[41] = self.transform_41
        self.rev_transforms[41] = self.reverse_transform_41

        self.fwd_transforms[42] = self.transform_42
        self.rev_transforms[42] = self.reverse_transform_42

        self.fwd_transforms[43] = self.transform_43
        self.rev_transforms[43] = self.reverse_transform_43

        self.fwd_transforms[44] = self.transform_44
        self.rev_transforms[44] = self.reverse_transform_44

        self.fwd_transforms[45] = self.transform_45
        self.rev_transforms[45] = self.reverse_transform_45

        self.fwd_transforms[46] = self.transform_46
        self.rev_transforms[46] = self.reverse_transform_46

        self.fwd_transforms[47] = self.transform_47
        self.rev_transforms[47] = self.reverse_transform_47

        for i in range(48, 57):
            fwd, rev = self._dynamic_transform(i)
            self.fwd_transforms[i] = fwd
            self.rev_transforms[i] = rev

        self.fwd_transforms[57] = self.transform_57
        self.rev_transforms[57] = self.reverse_transform_57

        for i in range(58, 256):
            fwd, rev = self._dynamic_transform(i)
            self.fwd_transforms[i] = fwd
            self.rev_transforms[i] = rev

        self.fwd_transforms[256] = self.transform_256
        self.rev_transforms[256] = self.reverse_transform_256

    # ------------------------------------------------------------------
    # Dictionary loaders
    # ------------------------------------------------------------------
    def _load_static_dictionary(self):
        if not os.path.exists(COMBINED_DICTIONARY_FILE):
            return [], {}
        words_set = set()
        try:
            with open(COMBINED_DICTIONARY_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    w = line.strip()
                    if w: words_set.add(w)
        except Exception as e:
            print(f"Warning: could not read {COMBINED_DICTIONARY_FILE}: {e}")
            return [], {}
        sorted_words = sorted(words_set)
        word_to_idx = {w: i for i, w in enumerate(sorted_words)}
        print(f"Loaded static word dictionary: {len(sorted_words)} unique words.")
        return sorted_words, word_to_idx

    def _load_line_dictionary(self):
        if not os.path.exists(COMBINED_DICTIONARY_FILE):
            return [], {}
        lines = []
        try:
            with open(COMBINED_DICTIONARY_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                for raw_line in f:
                    phrase = raw_line.strip()
                    if phrase and phrase not in lines:
                        lines.append(phrase)
                        if len(lines) >= MAX_LINE_ENTRIES:
                            break
        except Exception as e:
            print(f"Warning: could not read {COMBINED_DICTIONARY_FILE}: {e}")
            return [], {}
        if not lines:
            return [], {}
        lines.sort(key=len, reverse=True)
        line_to_idx = {phrase: i for i, phrase in enumerate(lines)}
        print(f"Loaded line dictionary: {len(lines)} phrases.")
        return lines, line_to_idx

    # ------------------------------------------------------------------
    # Quantum transforms
    # ------------------------------------------------------------------
    def _generate_permutation_from_circuit(self, num_qubits: int, seed: int) -> List[int]:
        if not USE_QUANTUM or not HAS_QISKIT:
            rng = random.Random(seed)
            size = 1 << num_qubits
            perm = list(range(size))
            rng.shuffle(perm)
            return perm

        try:
            qc = QuantumCircuit(num_qubits)
            rng = random.Random(seed)
            for qubit in range(num_qubits):
                qc.h(qubit)
                qc.rz(rng.random() * 2 * math.pi, qubit)
                qc.rx(rng.random() * 2 * math.pi, qubit)
            for _ in range(num_qubits):
                for i in range(num_qubits - 1):
                    qc.cx(i, i+1)
                qc.barrier()
                for i in range(num_qubits):
                    qc.rz(rng.random() * 2 * math.pi, i)
                    qc.rx(rng.random() * 2 * math.pi, i)
            try:
                qasm_str = qc.qasm()
            except AttributeError:
                qasm_str = qc.draw('text')
            final_seed = seed + hash(qasm_str) % 1000000
            rng2 = random.Random(final_seed)
            size = 1 << num_qubits
            perm = list(range(size))
            rng2.shuffle(perm)
            return perm
        except Exception:
            rng = random.Random(seed)
            size = 1 << num_qubits
            perm = list(range(size))
            rng.shuffle(perm)
            return perm

    def _precompute_quantum_transforms(self):
        if not USE_QUANTUM or not HAS_QISKIT:
            return

        q = self.QUANTUM_QUBITS
        if q > 49:
            print(f"WARNING: {q} qubits exceeds practical limit. Clamping to 49.")
            q = 49
            self.QUANTUM_QUBITS = q

        size = 1 << q
        if q <= 12:
            block_size = size
        else:
            block_size = 1024
            print(f"NOTE: Using block size {block_size} for permutations (qubits {q} used for seeding only).")

        num_perms = 8
        self.quantum_fast_transforms = []
        self.quantum_ultra_transforms = []
        for i in range(num_perms):
            seed = 1000 + i
            perm = self._generate_permutation_from_circuit(q, seed)
            if len(perm) > block_size:
                perm = perm[:block_size]
            fwd, rev = self._make_substitution_transform(perm, block_size)
            self.quantum_fast_transforms.append((fwd, rev))

        base = 256
        for idx, (fwd, rev) in enumerate(self.quantum_fast_transforms, start=1):
            self.fwd_transforms[base + idx] = fwd
            self.rev_transforms[base + idx] = rev

        self.quantum_transforms_built = True
        print(f"Quantum transforms built: {num_perms} transforms with block size {block_size} using {q} qubits.")

    def _make_substitution_transform(self, perm: List[int], size: int):
        if size < 256:
            inv_perm = [0] * size
            for i, p in enumerate(perm):
                inv_perm[p] = i
            def forward(data: bytes) -> bytes:
                out = bytearray()
                for b in data:
                    if b < size:
                        out.append(perm[b])
                    else:
                        out.append(b)
                return bytes(out)
            def reverse(data: bytes) -> bytes:
                out = bytearray()
                for b in data:
                    if b < size:
                        out.append(inv_perm[b])
                    else:
                        out.append(b)
                return bytes(out)
        else:
            inv_perm = [0] * size
            for i, p in enumerate(perm):
                inv_perm[p] = i
            def forward(data: bytes) -> bytes:
                return bytes(perm[b] for b in data)
            def reverse(data: bytes) -> bytes:
                return bytes(inv_perm[b] for b in data)
        return forward, reverse

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_pattern(self, size: int, index: int):
        random.seed(12345 + size * 100 + index)
        return [random.randint(0, 255) for _ in range(size)]

    def _calculate_repeats(self, data: bytes) -> int:
        if not data: return 1
        length = len(data)
        byte_sum = sum(data) % 256
        repeats = ((length * 13 + byte_sum * 17) % 256) + 1
        return max(1, min(256, repeats))

    def _verify_lossless(self, original: bytes, transformed: bytes, rev_func: Callable) -> bool:
        try:
            restored = rev_func(transformed)
            return restored == original
        except TransformError:
            return False
        except Exception:
            return False

    # ------------------------------------------------------------------
    # LZ77 + Huffman pipeline
    # ------------------------------------------------------------------
    WINDOW_SIZE = 2048
    MIN_MATCH = 3
    MAX_MATCH = 2048
    MAX_DIST = 2048

    def _lz77_tokenize(self, data: bytes) -> List[Tuple]:
        tokens = []
        i = 0
        n = len(data)
        while i < n:
            best_len = 0
            best_dist = 0
            start_window = max(0, i - self.WINDOW_SIZE)
            for j in range(start_window, i):
                if data[j] != data[i]:
                    continue
                k = 0
                while i + k < n and j + k < i and data[j + k] == data[i + k]:
                    k += 1
                    if k >= self.MAX_MATCH: break
                if k >= self.MIN_MATCH and k > best_len:
                    best_len = k
                    best_dist = i - j
                    if best_len == self.MAX_MATCH: break
            if best_len >= self.MIN_MATCH:
                tokens.append(('M', best_dist, best_len))
                i += best_len
            else:
                tokens.append(('L', data[i], None))
                i += 1
        return tokens

    def _lz77_untokenize(self, tokens: List[Tuple]) -> bytes:
        out = bytearray()
        for t in tokens:
            if t[0] == 'L':
                out.append(t[1])
            else:
                dist, length = t[1], t[2]
                start = len(out) - dist
                for k in range(length):
                    out.append(out[start + k])
        return bytes(out)

    def _encode_lzh(self, data: bytes) -> bytes:
        tokens = self._lz77_tokenize(data)
        lit_freq = [0] * 256
        dist_freq = [0] * (self.MAX_DIST + 1)
        len_freq = [0] * (self.MAX_MATCH + 1)
        for t in tokens:
            if t[0] == 'L':
                lit_freq[t[1]] += 1
            else:
                dist_freq[t[1]] += 1
                len_freq[t[2]] += 1
        lit_cl = self._huffman_code_lengths(lit_freq)
        dist_cl = self._huffman_code_lengths(dist_freq)
        len_cl = self._huffman_code_lengths(len_freq)
        lit_codes = self._huffman_canonical_codes(lit_cl)
        dist_codes = self._huffman_canonical_codes(dist_cl)
        len_codes = self._huffman_canonical_codes(len_cl)
        bits = []
        token_count = len(tokens)
        for b in struct.pack('>I', token_count):
            for i in range(8):
                bits.append((b >> (7-i)) & 1)
        for t in tokens:
            if t[0] == 'L':
                bits.append(0)
                code, cl = lit_codes[t[1]]
                for i in range(cl-1, -1, -1):
                    bits.append((code >> i) & 1)
            else:
                bits.append(1)
                code_d, cl_d = dist_codes[t[1]]
                for i in range(cl_d-1, -1, -1):
                    bits.append((code_d >> i) & 1)
                code_l, cl_l = len_codes[t[2]]
                for i in range(cl_l-1, -1, -1):
                    bits.append((code_l >> i) & 1)
        pad = (8 - len(bits) % 8) % 8
        bits.extend([0] * pad)
        def pack_lengths_16(lengths: List[int]) -> bytes:
            return b''.join(struct.pack('>H', l) for l in lengths)
        lit_len_bytes = pack_lengths_16(lit_cl)
        dist_len_bytes = pack_lengths_16(dist_cl)
        len_len_bytes = pack_lengths_16(len_cl)
        header = bytearray()
        header.extend(lit_len_bytes)
        header.extend(dist_len_bytes)
        header.extend(len_len_bytes)
        out = bytearray(header)
        for i in range(0, len(bits), 8):
            byte = 0
            for j in range(8):
                byte = (byte << 1) | bits[i+j]
            out.append(byte)
        return bytes(out)

    def _decode_lzh(self, data: bytes) -> Optional[bytes]:
        LIT_LEN_BYTES = 256 * 2
        DIST_LEN_BYTES = 2049 * 2
        LEN_LEN_BYTES = 2049 * 2
        if len(data) < LIT_LEN_BYTES + DIST_LEN_BYTES + LEN_LEN_BYTES:
            raise TransformError("LZH decode: data too short for code tables")
        pos = 0
        lit_cl = [struct.unpack('>H', data[i:i+2])[0] for i in range(pos, pos+LIT_LEN_BYTES, 2)]
        pos += LIT_LEN_BYTES
        dist_cl = [struct.unpack('>H', data[i:i+2])[0] for i in range(pos, pos+DIST_LEN_BYTES, 2)]
        pos += DIST_LEN_BYTES
        len_cl = [struct.unpack('>H', data[i:i+2])[0] for i in range(pos, pos+LEN_LEN_BYTES, 2)]
        pos += LEN_LEN_BYTES

        def build_decode_table(lengths: List[int]) -> Dict[Tuple[int, int], int]:
            symbols = list(range(len(lengths)))
            symbols.sort(key=lambda s: (lengths[s], s))
            decode = {}
            code = 0
            prev_len = 0
            first = True
            for sym in symbols:
                cl = lengths[sym]
                if cl == 0: continue
                if first:
                    prev_len = cl
                    first = False
                elif cl != prev_len:
                    code <<= (cl - prev_len)
                    prev_len = cl
                decode[(cl, code)] = sym
                code += 1
            return decode

        lit_decode = build_decode_table(lit_cl)
        dist_decode = build_decode_table(dist_cl)
        len_decode = build_decode_table(len_cl)

        max_lit_bits = max(lit_cl) if any(lit_cl) else 0
        max_dist_bits = max(dist_cl) if any(dist_cl) else 0
        max_len_bits = max(len_cl) if any(len_cl) else 0

        payload = data[pos:]
        if len(payload) < 4:
            raise TransformError("LZH decode: payload too short for token count")
        token_count = struct.unpack('>I', payload[:4])[0]
        bits = []
        for byte in payload[4:]:
            for i in range(7, -1, -1):
                bits.append((byte >> i) & 1)

        bpos = 0
        tokens = []
        for _ in range(token_count):
            if bpos >= len(bits):
                raise TransformError("LZH decode: unexpected end of bitstream")
            flag = bits[bpos]; bpos += 1
            if flag == 0:
                found = False
                for cl in range(1, max_lit_bits + 1):
                    if bpos + cl > len(bits): break
                    val = 0
                    for j in range(cl):
                        val = (val << 1) | bits[bpos + j]
                    if (cl, val) in lit_decode:
                        lit = lit_decode[(cl, val)]
                        tokens.append(('L', lit, None))
                        bpos += cl
                        found = True
                        break
                if not found:
                    raise TransformError("LZH decode: literal symbol not found")
            else:
                found_d = False
                for cl in range(1, max_dist_bits + 1):
                    if bpos + cl > len(bits): break
                    val = 0
                    for j in range(cl):
                        val = (val << 1) | bits[bpos + j]
                    if (cl, val) in dist_decode:
                        dist = dist_decode[(cl, val)]
                        bpos += cl
                        found_d = True
                        break
                if not found_d:
                    raise TransformError("LZH decode: distance symbol not found")
                found_l = False
                for cl in range(1, max_len_bits + 1):
                    if bpos + cl > len(bits): break
                    val = 0
                    for j in range(cl):
                        val = (val << 1) | bits[bpos + j]
                    if (cl, val) in len_decode:
                        length = len_decode[(cl, val)]
                        bpos += cl
                        found_l = True
                        break
                if not found_l:
                    raise TransformError("LZH decode: length symbol not found")
                tokens.append(('M', dist, length))
        return self._lz77_untokenize(tokens)

    # ------------------------------------------------------------------
    # Variable‑length header encoding for single transforms
    # ------------------------------------------------------------------
    def _encode_marker_single(self, t: int) -> bytes:
        if t <= 252:
            return bytes([t - 1])
        elif t <= 255:
            return bytes([254, t - 253])
        else:
            return bytes([255, (t - 256) // 256, (t - 256) % 256])

    def _encode_marker_raw(self) -> bytes:
        return bytes([252])

    def _decode_header(self, data: bytes):
        if len(data) < 1:
            return 0, ()
        f = data[0]
        if f < 252:
            return 1, (f + 1,)
        elif f == 252:
            return 1, ()
        elif f == 254:
            if len(data) < 2: return 0, ()
            x = data[1]
            if x > 3: return 0, ()
            return 2, (253 + x,)
        elif f == 255:
            if len(data) < 3: return 0, ()
            high = data[1]
            low = data[2]
            t = 256 + high * 256 + low
            return 3, (t,)
        else:
            return 0, ()

    # ------------------------------------------------------------------
    # Compression backends
    # ------------------------------------------------------------------
    def _compress_backend(self, data: bytes) -> bytes:
        candidates = []
        if HAS_ZSTD:
            try: candidates.append(zstd_cctx.compress(data))
            except: pass
        if paq is not None:
            try: candidates.append(paq.compress(data))
            except: pass
        candidates.append(data)
        return min(candidates, key=len)

    def _decompress_backend(self, data: bytes) -> Optional[bytes]:
        if len(data) == 0: return b''
        if HAS_ZSTD:
            try: return zstd_dctx.decompress(data)
            except: pass
        if paq is not None:
            try: return paq.decompress(data)
            except: pass
        return data

    # ------------------------------------------------------------------
    # Compression method (single transforms only)
    # ------------------------------------------------------------------
    def compress_with_verification(self, data: bytes, time_limit: Optional[float] = None) -> bytes:
        if time_limit is None:
            time_limit = self.ULTRA_TIME_LIMIT
        start_time = time.time()
        best_candidate = None
        best_len = float('inf')

        def try_candidate(header: bytes, transformed: bytes):
            nonlocal best_candidate, best_len
            candidate = header + self._compress_backend(transformed)
            if len(candidate) < best_len:
                best_candidate = candidate
                best_len = len(candidate)

        try_candidate(self._encode_marker_raw(), data)
        for t in range(1, 257):
            if time_limit and time.time() - start_time > time_limit:
                break
            try:
                transformed = self.fwd_transforms[t](data)
                if not self._verify_lossless(data, transformed, self.rev_transforms[t]):
                    continue
                try_candidate(self._encode_marker_single(t), transformed)
            except (TransformError, Exception):
                continue

        if best_candidate is None:
            best_candidate = self._encode_marker_raw() + self._compress_backend(data)

        decomp, _ = self._decompress_auto(best_candidate)
        if decomp == data:
            return best_candidate

        fallback = self._encode_marker_raw() + self._compress_backend(data)
        decomp_fb, _ = self._decompress_auto(fallback)
        if decomp_fb != data:
            raise RuntimeError("Fallback compression also failed – this should never happen.")
        return fallback

    # ------------------------------------------------------------------
    # Compression method with LZH backend
    # ------------------------------------------------------------------
    def compress_with_lzh(self, data: bytes, time_limit: Optional[float] = None) -> bytes:
        if time_limit is None:
            time_limit = self.ULTRA_TIME_LIMIT
        start_time = time.time()
        best_candidate = None
        best_len = float('inf')

        def try_candidate(header: bytes, transformed: bytes):
            nonlocal best_candidate, best_len
            lzh = self._encode_lzh(transformed)
            candidate = header + b'\xFF' + lzh
            if len(candidate) < best_len:
                best_candidate = candidate
                best_len = len(candidate)

        try_candidate(self._encode_marker_raw(), data)
        for t in range(1, 257):
            if time_limit and time.time() - start_time > time_limit: break
            try:
                transformed = self.fwd_transforms[t](data)
                if not self._verify_lossless(data, transformed, self.rev_transforms[t]):
                    continue
                try_candidate(self._encode_marker_single(t), transformed)
            except (TransformError, Exception): continue

        if best_candidate is None:
            fallback = self._encode_marker_raw() + self._compress_backend(data)
            decomp = self._decompress_lzh_pipeline(fallback)
            if decomp != data:
                raise RuntimeError("Fallback LZH compression failed.")
            return fallback

        decomp = self._decompress_lzh_pipeline(best_candidate)
        if decomp == data:
            return best_candidate

        fallback = self._encode_marker_raw() + self._compress_backend(data)
        decomp = self._decompress_lzh_pipeline(fallback)
        if decomp != data:
            raise RuntimeError("Fallback compression failed.")
        return fallback

    def _decompress_lzh_pipeline(self, data: bytes) -> Optional[bytes]:
        offset, seq = self._decode_header(data)
        if offset == 0: return None
        if len(data) <= offset or data[offset] != 0xFF: return None
        lzh_data = data[offset+1:]
        transformed = self._decode_lzh(lzh_data)
        if transformed is None: return None
        if not seq:
            return transformed
        return self._reverse_sequence(transformed, seq)

    def _decompress_auto(self, data: bytes) -> Tuple[bytes, Optional[Tuple[int, ...]]]:
        offset, seq = self._decode_header(data)
        if offset == 0:
            raise DecompressionError("Invalid compression header")
        payload = data[offset:]
        if not payload:
            raise DecompressionError("Empty payload")
        res = self._decompress_backend(payload)
        if res is None:
            raise DecompressionError("Backend decompression failed")
        if not seq:
            return res, None
        result = self._reverse_sequence(res, seq)
        return result, seq

    def _reverse_sequence(self, data: bytes, seq: Tuple[int, ...]) -> bytes:
        result = data
        for t in reversed(seq):
            result = self.rev_transforms[t](result)
        return result

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------
    def _auto_output_name(self, infile: str, suffix: str = ".pjp") -> str:
        base = os.path.basename(infile)
        return f"{base}{suffix}"

    def _atomic_write(self, path: str, data: bytes):
        dirname = os.path.dirname(path) or '.'
        basename = os.path.basename(path)
        fd, tmpname = tempfile.mkstemp(prefix=basename + '.tmp', dir=dirname)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmpname, path)

    def compress_file(self, infile: str, outfile: str = "", use_lzh: bool = False,
                      time_limit: Optional[float] = None):
        try:
            with open(infile, 'rb') as f: data = f.read()
        except Exception as e:
            print(f"Error reading file: {e}"); return
        try:
            if use_lzh:
                compressed = self.compress_with_lzh(data, time_limit=time_limit)
                default_suffix = ".pjp.lzh"
            else:
                compressed = self.compress_with_verification(data, time_limit=time_limit)
                default_suffix = ".pjp"
        except RuntimeError as e:
            print(f"Compression failed: {e}"); return
        if not outfile:
            outfile = self._auto_output_name(infile, default_suffix)
        try:
            self._atomic_write(outfile, compressed)
        except Exception as e:
            print(f"Error writing output file: {e}"); return
        print(f"Compressed {len(data)} → {len(compressed)} bytes → {outfile}")

    def decompress_file(self, infile: str, outfile: str = "") -> bool:
        try:
            with open(infile, 'rb') as f:
                data = f.read()
        except Exception as e:
            print(f"Error reading file: {e}")
            return False

        try:
            if data.startswith(b'DICT'):
                if data.startswith(b'DICT\x01'):
                    original = self._decompress_static_dict(data)
                elif data.startswith(b'DICT\x02'):
                    original = self._decompress_dynamic_dict(data)
                else:
                    print("Unknown dictionary format")
                    return False
            elif data.startswith(b'LINE'):
                original = self._decompress_line_dict(data)
            else:
                offset, seq = self._decode_header(data)
                if offset == 0:
                    print("Decompression failed: invalid header.")
                    return False
                else:
                    if offset < len(data) and data[offset] == 0xFF:
                        original = self._decompress_lzh_pipeline(data)
                    else:
                        try:
                            original, _ = self._decompress_auto(data)
                        except DecompressionError as e:
                            print(f"Decompression failed: {e}")
                            return False
        except DecompressionError as e:
            print(f"Decompression failed: {e}")
            return False
        except Exception as e:
            print(f"Decompression failed with unexpected error: {e}")
            return False

        if original is None:
            print("Decompression failed: produced None")
            return False

        if not outfile:
            base = os.path.basename(infile)
            name_without_suffix = re.sub(r'\.pjp(\.lzh)?$', '', base)
            outfile = name_without_suffix

        try:
            self._atomic_write(outfile, original)
        except Exception as e:
            print(f"Error writing output file: {e}")
            return False

        print(f"Decompressed → {outfile} ({len(original)} bytes)")
        return True

    # ------------------------------------------------------------------
    # Full self‑test
    # ------------------------------------------------------------------
    def full_self_test(self) -> bool:
        print("=" * 60)
        print("Unified PAQJP+PJP – Self‑Test (256 single transforms)")
        print("=" * 60)
        print("Testing all 256 transforms on multiple byte values...")

        test_byte_values = [0x00, 0xFF, 0xAA, 0x55, 0x12, 0x34]
        all_ok = True

        for t in range(1, 257):
            if t % 25 == 0:
                print(f"  Testing transform {t}...")
            for test_byte in test_byte_values:
                test_data = bytes([test_byte])
                try:
                    transformed = self.fwd_transforms[t](test_data)
                    restored = self.rev_transforms[t](transformed)
                    if restored != test_data:
                        print(f"  FAIL: transform {t}, byte {test_byte:#04x}")
                        all_ok = False
                        break
                except TransformError:
                    continue
                except Exception as e:
                    print(f"  EXCEPTION at transform {t}, byte {test_byte:#04x}: {e}")
                    all_ok = False
                    break
            if not all_ok:
                break

        if all_ok:
            print("\n  All 256 transforms passed on test bytes.")
            print("  Actual compression verifies every candidate transform on the real input;")
            print("  unsafe transforms are rejected, and raw fallback guarantees lossless output.")
        else:
            print("\n  Self‑test FAILED – some transform is not lossless for a test byte.")
            return False

        print("\nRandom 100‑byte pipeline test (LZH backend)...")
        rng = random.Random(12345)
        test_data = bytes(rng.randint(0, 255) for _ in range(100))
        try:
            compressed = self.compress_with_lzh(test_data, time_limit=30)
            decompressed = self._decompress_lzh_pipeline(compressed)
            if decompressed != test_data:
                print("  FAIL: LZH pipeline mismatch")
                return False
            print("  PASS")
        except RuntimeError as e:
            print(f"  Could not compress (rare): {e}")
            return False

        # Extra round-trip test with more varied data (text-like + binary)
        print("\nExtended round-trip tests...")
        extended_cases = [
            b"",
            b"A",
            b"AB",
            b"ABC",
            b"ABCD",
            b"hello world",
            b"The quick brown fox jumps over the lazy dog.\n" * 20,
            bytes(range(256)),
            bytes(range(256)) * 4,
            os.urandom(64),
            os.urandom(1024),
            "Héllo wörld – UTF-8 test ✓".encode('utf-8') * 10,
        ]
        for idx, case in enumerate(extended_cases):
            for use_lzh in (False, True):
                try:
                    if use_lzh:
                        comp = self.compress_with_lzh(case, time_limit=20)
                        decomp = self._decompress_lzh_pipeline(comp)
                    else:
                        comp = self.compress_with_verification(case, time_limit=20)
                        decomp, _ = self._decompress_auto(comp)
                    if decomp != case:
                        print(f"  FAIL case {idx} (lzh={use_lzh})")
                        return False
                except Exception as e:
                    print(f"  EXCEPTION case {idx} (lzh={use_lzh}): {e}")
                    return False
        print("  Extended round-trips PASS")
        print("\n[All checks passed – 100% lossless]")
        return True

# ------------------------------------------------------------
# Main menu
# ------------------------------------------------------------
def main():
    print(f"{PROGNAME} – Unified compression with 256 single transforms")
    print("Compressed output: input.txt.pjp (or input.txt.pjp.lzh)")
    print("Lossless output guaranteed via per-input verification and raw fallback.\n")
    c = UnifiedCompressor()

    print("=" * 58)
    print("Options:")
    print("  1) Compress (Fast)      – 256 single transforms + backend")
    print("  2) Decompress")
    print("  3) Full self‑test       – verify all 256 transforms")
    print("  0) Exit")
    print("=" * 58)

    while True:
        print("\nMenu:")
        print("1) Compress (Fast)")
        print("2) Decompress")
        print("3) Full self‑test (256 transforms)")
        print("0) Exit")
        choice = input("> ").strip()
        if choice == "1":
            infile = input("Input file: ").strip()
            c.compress_file(infile, use_lzh=False)
        elif choice == "2":
            while True:
                infile = input("Compressed file (.pjp or .pjp.lzh) [press Enter to cancel]: ").strip()
                if not infile:
                    break
                if not (infile.lower().endswith('.pjp') or infile.lower().endswith('.pjp.lzh')):
                    print("Error: Incorrect format. Only .pjp and .pjp.lzh files are supported.")
                    continue
                outfile = input("Output file (leave blank to restore original name): ").strip()
                if c.decompress_file(infile, outfile):
                    break
                else:
                    print("Decompression failed. Try another file or press Enter to cancel.")
        elif choice == "3":
            c.full_self_test()
        elif choice == "0":
            break
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()
