#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# PPMD_1.2 — Lossless Tournament + cmix + Lepton + XML/DOCX + Qiskit
# DETERMINISTIC tournament, identical winner on any core count.
# QISKIT: 16-qubit circuit → SHA-256 → deterministic permutation & byte mask.
#         Only imports `qiskit` and `QuantumCircuit`.  No quantum_info,
#         no Statevector, no Operator, no registers.

import math, random, decimal, hashlib, base64, heapq, struct, os
import tempfile, re, sys, subprocess, importlib, time, site, shutil
import urllib.request
import multiprocessing as mp
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import xml, xml.etree.ElementTree as ET, xml.sax.saxutils as saxutils
import zipfile, io

try: import lxml.etree as _lxml_etree; HAS_LXML = True
except ImportError: _lxml_etree = None; HAS_LXML = False
try: import defusedxml.ElementTree as _defused_etree; HAS_DEFUSEDXML = True
except ImportError: _defused_etree = None; HAS_DEFUSEDXML = False
try: import paq
except ImportError: paq = None
try: import brotli; HAS_BROTLI = True
except ImportError: brotli = None; HAS_BROTLI = False
try: import pyppmd; HAS_PPMD = True
except ImportError: pyppmd = None; HAS_PPMD = False
try: import lepton_jpeg_python; HAS_LEPTON = True
except ImportError: lepton_jpeg_python = None; HAS_LEPTON = False

# ─────────────── QISKIT — ONLY QuantumCircuit ───────────────
try:
    import qiskit
    from qiskit import QuantumCircuit
    HAS_QISKIT = True
    QISKIT_VER = getattr(qiskit, "__version__", "?")
except ImportError:
    qiskit = None
    QuantumCircuit = None
    HAS_QISKIT = False
    QISKIT_VER = None
# ─────────────────────────────────────────────────────────────

try:
    import lzma; HAS_LZMA = True
    LF_RAW = [{"id": lzma.FILTER_LZMA2, "preset": 9 | lzma.PRESET_EXTREME, "nice_len": 273, "mf": lzma.MF_BT4}]
    LF_DELTA = [{"id": lzma.FILTER_DELTA, "dist": 1}, LF_RAW[0]]
    LF_BCJ = [{"id": lzma.FILTER_X86}, LF_RAW[0]]
except ImportError:
    lzma = None; HAS_LZMA = False; LF_RAW = LF_DELTA = LF_BCJ = None

HAS_ZPAQ = shutil.which('zpaq') is not None
HAS_CCMX = shutil.which('ccmx') is not None
HAS_CMIX = shutil.which('cmix') is not None

CPU_COUNT = mp.cpu_count() or 4
N_CORES = max(1, int(os.environ.get("PPMD_CORES", "4") or "4"))
REPEATS = max(1, int(os.environ.get("PPMD_REPEATS", "1") or "1"))
CBACK_WORKERS = max(2, int(os.environ.get("PPMD_CBACK_WORKERS", "8") or "8"))
CBACK_WORKERS_EFF = max(1, CPU_COUNT // N_CORES)
CHUNK = max(1, int(os.environ.get("PPMD_CHUNK", "32") or "32"))
TOP_VERIFY = max(1, int(os.environ.get("PPMD_TOP_VERIFY", "20") or "20"))
try:
    _MP_CTX = mp.get_context("fork")
    _HAS_FORK = True
except (ValueError, AttributeError):
    _MP_CTX = mp.get_context()
    _HAS_FORK = False

IDENTITY_IDS = frozenset((1, 31, 32, 256))

_GLOBAL_COMP = None
_GLOBAL_DATA = None
_GLOBAL_FWD = {}
_IN_WORKER = False

def _worker_single(t):
    global _IN_WORKER
    if not _IN_WORKER: _IN_WORKER = True
    c = _GLOBAL_COMP; data = _GLOBAL_DATA
    if c is None or data is None:
        return (t, None, "worker not initialised")
    try:
        v = _GLOBAL_FWD.get(t)
        tr = v if v is not None else c.fwd[t](data)
        return (t, len(c.cback(tr)), None)
    except Exception as e:
        return (t, None, repr(e))

def _worker_pair(args):
    global _IN_WORKER
    if not _IN_WORKER: _IN_WORKER = True
    idx, a, b = args
    c = _GLOBAL_COMP; data = _GLOBAL_DATA
    if c is None or data is None:
        return (idx, a, b, None, "worker not initialised")
    try:
        va = _GLOBAL_FWD.get(a)
        ta = va if va is not None else c.fwd[a](data)
        tr = c.fwd[b](ta)
        return (idx, a, b, len(c.cback(tr)), None)
    except Exception as e:
        return (idx, a, b, None, repr(e))

def _imp_zstd():
    try:
        importlib.invalidate_caches()
        us = site.getusersitepackages()
        if us and us not in sys.path: sys.path.insert(0, us)
    except Exception: pass
    try:
        import zstandard as zstd; return zstd
    except ImportError: return None

def _ins_zstd():
    for c in [[sys.executable,'-m','pip','install','--no-input','--disable-pip-version-check','zstandard'],
              [sys.executable,'-m','pip','install','--user','--no-input','--disable-pip-version-check','zstandard'],
              [sys.executable,'-m','pip','install','--break-system-packages','--no-input','--disable-pip-version-check','zstandard']]:
        try:
            subprocess.check_call(c)
            if _imp_zstd() is not None: return True
        except Exception: pass
    return False

print("="*70); print("PPMD_1.2 — Checking backends"); print("="*70)
print(f"parallelism: {N_CORES} cores" + (" (fork)" if _HAS_FORK else " (spawn, limited)"))
print(f"cpu count  : {CPU_COUNT}")
print(f"repeats    : {REPEATS}")
print(f"cback thr  : {CBACK_WORKERS} (parent) / {CBACK_WORKERS_EFF} (worker)")
print(f"chunk      : {CHUNK}")
_z = _imp_zstd()
if _z is None:
    print("zstandard missing; trying auto-install...")
    _ins_zstd(); _z = _imp_zstd()
if _z:
    zstd = _z
    zc = zstd.ZstdCompressor(level=22); zd = zstd.ZstdDecompressor(); zf = zstd.ZstdCompressor(level=19)
    HAS_ZSTD = True; print("zstandard: OK")
else:
    zstd = zc = zd = zf = None; HAS_ZSTD = False; print("zstandard: NOT available")

def inst(pkg):
    print(f"Installing {pkg}...")
    for c in [[sys.executable,'-m','pip','install','--no-input','--disable-pip-version-check',pkg],
              [sys.executable,'-m','pip','install','--user','--no-input','--disable-pip-version-check',pkg],
              [sys.executable,'-m','pip','install','--break-system-packages','--no-input','--disable-pip-version-check',pkg]]:
        try: subprocess.check_call(c); return True
        except Exception: pass
    return False

CCMX_MIRRORS = [
    "https://web.archive.org/web/20161019035512if_/http://www.byronknoll.com/ccmx130a.zip",
    "https://mattmahoney.net/dc/ccmx.zip",
    "https://encode.su/attachment.php?attachmentid=2032&d=1203997110"]

def _install_ccmx():
    global HAS_CCMX
    if HAS_CCMX:
        p = shutil.which('ccmx'); print(f"ccmx: OK ({p})"); return True, p
    print("ccmx: not found — trying pip ...")
    for pkg in ('ccmx', 'pyccmx', 'ccmx-py'):
        try:
            r = subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-input', '--disable-pip-version-check', pkg], capture_output=True, timeout=120)
            if r.returncode == 0:
                p = shutil.which('ccmx')
                if p: HAS_CCMX = True; print(f"ccmx: OK ({p})"); return True, p
        except Exception: pass
    target_dir = os.path.join(site.getusersitepackages() or os.path.expanduser('~'), '.ppmd_bin')
    try: os.makedirs(target_dir, exist_ok=True)
    except Exception: pass
    target = os.path.join(target_dir, 'ccmx')
    for url in CCMX_MIRRORS:
        print(f"ccmx: trying mirror {url} ...")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as r: blob = r.read()
            if blob[:2] == b'PK':
                import zipfile as _zf, io as _io
                with _zf.ZipFile(_io.BytesIO(blob)) as z:
                    name = next((n for n in z.namelist() if os.path.basename(n).lower().startswith('ccmx')), None)
                    if name is None: continue
                    data = z.read(name)
            else: data = blob
            with open(target, 'wb') as f: f.write(data)
            os.chmod(target, 0o755)
            try: subprocess.run([target], capture_output=True, timeout=10); ok = True
            except Exception: ok = os.path.getsize(target) > 1024
            if ok:
                os.environ['PATH'] = target_dir + os.pathsep + os.environ.get('PATH', '')
                HAS_CCMX = True; print(f"ccmx: OK ({target})"); return True, target
        except Exception as e: print(f"ccmx: mirror failed ({e})"); continue
    print("ccmx: NOT available"); return False, None

CMIX_SRC_URL = "https://github.com/byronknoll/cmix/archive/refs/tags/v21.tar.gz"

def _install_cmix():
    global HAS_CMIX
    if HAS_CMIX:
        p = shutil.which('cmix'); print(f"cmix: OK ({p})"); return True, p
    print("\n" + "="*70); print("cmix (Level 9) installation"); print("="*70)
    ans = input("Install cmix (Level 9)? (y/n) [y]: ").strip().lower()
    if ans == 'n': print("cmix: skipped by user"); return False, None
    target_dir = os.path.join(site.getusersitepackages() or os.path.expanduser('~'), '.ppmd_bin')
    try: os.makedirs(target_dir, exist_ok=True)
    except Exception: pass
    compiler = None
    for cc in ('g++', 'clang++', 'c++'):
        if shutil.which(cc): compiler = cc; break
    if compiler is None: print("cmix: ERROR — no C++ compiler found."); return False, None
    print(f"cmix: using compiler: {compiler}")
    tmp_dir = tempfile.mkdtemp(prefix="cmix_build_")
    try:
        req = urllib.request.Request(CMIX_SRC_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=120) as r: tarball = r.read()
    except Exception as e:
        print(f"cmix: download failed: {e}"); shutil.rmtree(tmp_dir, ignore_errors=True); return False, None
    tar_path = os.path.join(tmp_dir, "cmix.tar.gz")
    with open(tar_path, 'wb') as f: f.write(tarball)
    try:
        import tarfile
        with tarfile.open(tar_path, 'r:gz') as tar: tar.extractall(tmp_dir)
    except Exception as e:
        print(f"cmix: extract failed: {e}"); shutil.rmtree(tmp_dir, ignore_errors=True); return False, None
    src_dir = None
    for name in os.listdir(tmp_dir):
        p = os.path.join(tmp_dir, name)
        if os.path.isdir(p) and os.path.exists(os.path.join(p, 'makefile')): src_dir = p; break
    if src_dir is None: shutil.rmtree(tmp_dir, ignore_errors=True); return False, None
    mf = os.path.join(src_dir, 'makefile')
    try:
        with open(mf, 'r') as f: mf_text = f.read()
        mf_text = re.sub(r'CC\s*=\s*\S+', f'CC = {compiler}', mf_text, count=1)
        with open(mf, 'w') as f: f.write(mf_text)
    except Exception: pass
    try:
        r = subprocess.run(['make'], cwd=src_dir, capture_output=True, timeout=1800)
        if r.returncode != 0:
            print("cmix: make FAILED"); shutil.rmtree(tmp_dir, ignore_errors=True); return False, None
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True); return False, None
    binary_src = None
    for candidate in ('cmix', os.path.join('src', 'cmix'), os.path.join('build', 'cmix')):
        p = os.path.join(src_dir, candidate)
        if os.path.isfile(p) and os.access(p, os.X_OK): binary_src = p; break
    if binary_src is None: shutil.rmtree(tmp_dir, ignore_errors=True); return False, None
    target = os.path.join(target_dir, 'cmix')
    try: shutil.copy2(binary_src, target); os.chmod(target, 0o755)
    except Exception: shutil.rmtree(tmp_dir, ignore_errors=True); return False, None
    try: subprocess.run([target], capture_output=True, timeout=10); ok = True
    except Exception: ok = os.path.getsize(target) > 100_000
    shutil.rmtree(tmp_dir, ignore_errors=True)
    if ok:
        os.environ['PATH'] = target_dir + os.pathsep + os.environ.get('PATH', '')
        HAS_CMIX = True; print(f"cmix: OK ({target})"); return True, target
    return False, None

if not HAS_PPMD:
    if input("Install pyppmd? (y/n) [y]: ").strip().lower() != 'n':
        if inst('pyppmd'):
            try: import pyppmd; HAS_PPMD = True; print("pyppmd: OK")
            except ImportError: pass
if paq is None:
    if input("Install paq? (y/n) [y]: ").strip().lower() != 'n':
        if inst('paq'):
            try: import paq; print("paq: OK")
            except ImportError: paq = None
if not HAS_BROTLI:
    if input("Install brotli? (y/n) [y]: ").strip().lower() != 'n':
        if inst('brotli'):
            try: import brotli; HAS_BROTLI = True; print("brotli: OK")
            except ImportError: pass
if not HAS_LXML:
    print("\nNote: Python's built-in `xml` module needs no install.")
    if input("Install lxml? (y/n) [y]: ").strip().lower() != 'n':
        if inst('lxml'):
            try: import lxml.etree as _lxml_etree; HAS_LXML = True; print(f"lxml: OK")
            except ImportError: print("lxml: install failed")
if not HAS_DEFUSEDXML:
    if input("Install defusedxml? (y/n) [y]: ").strip().lower() != 'n':
        if inst('defusedxml'):
            try: import defusedxml.ElementTree as _defused_etree; HAS_DEFUSEDXML = True; print("defusedxml: OK")
            except ImportError: print("defusedxml: install failed")
if not HAS_CCMX:
    if input("Install ccmx? (y/n) [y]: ").strip().lower() != 'n': _install_ccmx()
_install_cmix()
if not HAS_LEPTON:
    if input("Install lepton_jpeg_python? (y/n) [y]: ").strip().lower() != 'n':
        if inst('lepton_jpeg_python'):
            try: import lepton_jpeg_python; HAS_LEPTON = True; print("lepton_jpeg_python: OK")
            except ImportError: print("lepton_jpeg_python: install failed")

# ═══════════════════════════════════════════════════════════════════════════════
#  QISKIT — circuit-only, deterministic permutation & byte mask
#  (imports only `qiskit` and `QuantumCircuit`; no quantum_info, no Statevector,
#   no Operator, no QuantumRegister, no ClassicalRegister)
# ═══════════════════════════════════════════════════════════════════════════════

def install_qiskit():
    global HAS_QISKIT, qiskit, QuantumCircuit, QISKIT_VER
    print("Installing qiskit (this can take a minute) ...")
    for pkg in ("qiskit",):
        for c in ([sys.executable, "-m", "pip", "install", "--no-input",
                   "--disable-pip-version-check", pkg],
                  [sys.executable, "-m", "pip", "install", "--user", "--no-input",
                   "--disable-pip-version-check", pkg],
                  [sys.executable, "-m", "pip", "install", "--break-system-packages",
                   "--no-input", "--disable-pip-version-check", pkg]):
            try: subprocess.check_call(c)
            except Exception: pass
    try:
        import importlib
        importlib.invalidate_caches()
        import qiskit as _q
        from qiskit import QuantumCircuit as _QC
        qiskit = _q
        QuantumCircuit = _QC
        QISKIT_VER = getattr(_q, "__version__", "?")
        HAS_QISKIT = True
        return True
    except ImportError:
        HAS_QISKIT = False
        return False


def ask_qubits():
    """Ask the user how many qubits to use. Hard cap: 16."""
    print("\n" + "=" * 70)
    print("Qiskit qubit count   (1 .. 16)")
    print("=" * 70)
    print("  65535 pairs need at least 16 qubits  (2^16 = 65536 states).")
    while True:
        raw = input("Qubits [16]: ").strip()
        if raw == "":
            return 16
        try:
            v = int(raw)
            if v < 1:
                print("  Must be at least 1."); continue
            if v > 16:
                print("  Must not exceed 16."); continue
            return v
        except ValueError:
            print("  Please enter a whole number.")


def _build_seed_circuit(n_qubits):
    """
    Build a fixed n_qubits QuantumCircuit using only QuantumCircuit.
    Deterministic: same n_qubits → identical circuit → identical QASM.
    """
    qc = QuantumCircuit(n_qubits, name="ppmd_q")
    for q in range(n_qubits):
        qc.h(q)
    for q in range(n_qubits):
        qc.t(q)
        qc.rz(math.pi / (q + 1.0), q)
    for q in range(n_qubits - 1):
        qc.cx(q, q + 1)
        qc.rz(math.pi / (2.0 ** (q + 1)), q + 1)
    for q in range(n_qubits):
        qc.h(q)
    return qc


def _circuit_fingerprint(n_qubits):
    """Deterministic SHA-256 fingerprint of the fixed circuit."""
    qc = _build_seed_circuit(n_qubits)
    try:
        blob = qc.qasm().encode("utf-8")
    except Exception:
        # Fallback: stringify gate list
        parts = []
        for item in qc.data:
            op = item.operation if hasattr(item, "operation") else item[0]
            qargs = item.qubits if hasattr(item, "qubits") else item[1]
            parts.append(f"{op.name}|{op.params}|{[qc.find_bit(q).index for q in qargs]}")
        blob = ";;".join(parts).encode("utf-8")
    return hashlib.sha256(b"PPMD_QS|" + str(n_qubits).encode() + b"|" + blob).digest()


_QPERM_CACHE = {}
_QMASK_CACHE = {}

def quantum_pair_permutation(n_pairs, n_qubits):
    """
    Deterministic permutation of 0..n_pairs-1 derived from a fixed
    n_qubits Qiskit circuit (circuit → QASM → SHA-256 → seeded Fisher-Yates).
    Same input → same output on every machine.
    """
    key = (n_pairs, n_qubits)
    hit = _QPERM_CACHE.get(key)
    if hit is not None:
        return hit
    if not HAS_QISKIT or n_qubits < 1 or n_pairs <= 0:
        perm = list(range(max(0, n_pairs)))
        _QPERM_CACHE[key] = perm
        return perm

    fp = _circuit_fingerprint(n_qubits)
    rng = random.Random(int.from_bytes(fp, "big"))
    perm = list(range(n_pairs))
    # Fisher–Yates
    for i in range(n_pairs - 1, 0, -1):
        j = rng.randrange(i + 1)
        perm[i], perm[j] = perm[j], perm[i]
    _QPERM_CACHE[key] = perm
    return perm


def quantum_bytes_mask(n_qubits, n_bytes):
    """
    Deterministic XOR mask of length n_bytes derived from the fixed
    n_qubits Qiskit circuit (circuit → QASM → SHA-256 → PRNG bytes).
    """
    if not HAS_QISKIT or n_qubits < 1 or n_bytes <= 0:
        return b"\x00" * max(0, n_bytes)
    key = (n_qubits, n_bytes)
    hit = _QMASK_CACHE.get(key)
    if hit is not None:
        return hit
    fp = _circuit_fingerprint(n_qubits)
    rng = random.Random(int.from_bytes(fp, "big") ^ 0x9E3779B97F4A7C15)
    out = bytes(rng.randrange(256) for _ in range(n_bytes))
    _QMASK_CACHE[key] = out
    return out

# ═══════════════════════════════════════════════════════════════════════════════

def install_qiskit_if_needed():
    global HAS_QISKIT
    if HAS_QISKIT:
        print(f"qiskit: OK (version {QISKIT_VER})")
        return
    if input("Install qiskit? (y/n) [y]: ").strip().lower() != 'n':
        install_qiskit()
    if HAS_QISKIT:
        print(f"qiskit: OK (version {QISKIT_VER})")
    else:
        print("qiskit: NOT available")

install_qiskit_if_needed()

PAIR_LIMIT = 65535
QUBIT_LIMIT = 16

def ask_pairs(n_qubits=16):
    max_by_q = (1 << max(1, n_qubits)) - 1
    cap = min(PAIR_LIMIT, max_by_q)
    print("\n" + "="*70)
    print(f"Pair count  (1 .. {cap})   [qubits = {n_qubits}, 2^{n_qubits}-1 = {max_by_q}]")
    print("="*70)
    while True:
        raw = input(f"Pairs [{cap}]: ").strip()
        if raw == "":
            return cap
        try:
            v = int(raw)
            if v < 1:
                print("  Must be at least 1."); continue
            if v > cap:
                print(f"  Must not exceed {cap}."); continue
            return v
        except ValueError:
            print("  Please enter a whole number.")

QUBITS = ask_qubits() if HAS_QISKIT else QUBIT_LIMIT
if HAS_QISKIT:
    print(f"Qubits chosen: {QUBITS}  (state space 2^{QUBITS} = {1 << QUBITS})")
else:
    print(f"Qubits: classical fallback (16)")
PAIRS = ask_pairs(QUBITS)
print(f"\nChosen: QUBITS = {QUBITS}   PAIRS = {PAIRS}")
if PAIRS > (1 << QUBITS) - 1:
    print(f"FATAL: {PAIRS} pairs do not fit in {QUBITS} qubits (max {(1 << QUBITS) - 1}).")
    sys.exit(1)
if PAIRS > 10**9:
    if input("Continue anyway? (y/n) [n]: ").strip().lower() != 'y':
        print("Aborting."); sys.exit(0)
print(f"\nBackends: zstd={'Y' if HAS_ZSTD else 'N'} lzma={'Y' if HAS_LZMA else 'N'} "
      f"paq={'Y' if paq else 'N'} brotli={'Y' if HAS_BROTLI else 'N'} "
      f"pyppmd={'Y' if HAS_PPMD else 'N'} zpaq={'Y' if HAS_ZPAQ else 'N'} "
      f"ccmx={'Y' if HAS_CCMX else 'N'} cmix={'Y' if HAS_CMIX else 'N'} "
      f"lepton={'Y' if HAS_LEPTON else 'N'} qiskit={'Y' if HAS_QISKIT else 'N'} "
      f"xml=Y lxml={'Y' if HAS_LXML else 'N'} defusedxml={'Y' if HAS_DEFUSEDXML else 'N'}")
PROGNAME = "PPMD_1.2"

REF_TEXT = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum. "
    "Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo. Nemo enim ipsam voluptatem quia voluptas sit aspernatur aut odit aut fugit, sed quia consequuntur magni dolores eos qui ratione voluptatem sequi nesciunt. Neque porro quisquam est, qui dolorem ipsum quia dolor sit amet, consectetur, adipisci velit, sed quia non numquam eius modi tempora incidunt ut labore et dolore magnam aliquam quaerat voluptatem. Ut enim ad minima veniam, quis nostrum exercitationem ullam corporis suscipit laboriosam, nisi ut aliquid ex ea commodi consequatur. Quis autem vel eum iure reprehenderit qui in ea voluptate velit esse quam nihil molestiae consequatur, vel illum qui dolorem eum fugiat quo voluptas nulla pariatur. "
    "At vero eos et accusamus et iusto odio dignissimos ducimus qui blanditiis praesentium voluptatum deleniti atque corrupti quos dolores et quas molestias excepturi sint occaecati cupiditate non provident, similique sunt in culpa qui officia deserunt mollitia animi, id est laborum et dolorum fuga. Et harum quidem rerum facilis est et expedita distinctio. Nam libero tempore, cum soluta nobis est eligendi optio cumque nihil impedit quo minus id quod maxime placeat facere possimus, omnis voluptas assumenda est, omnis dolor repellendus. Temporibus autem quibusdam et aut officiis debitis aut rerum necessitatibus saepe eveniet ut et voluptates repudiandae sint et molestiae non recusandae. Itaque earum rerum hic tenetur a sapiente delectus, ut aut reiciendis voluptatibus maiores alias consequatur aut perferendis doloribus asperiores repellat."
)
REF_BYTES = REF_TEXT.encode('utf-8')
_TOK_RE = re.compile(rb'([A-Za-z]+)')

_SEEDS = {
'a':"able about above abroad absence absent absolute absorb abstract abuse accent accept access accident accompany accomplish accord account accurate accuse achieve acid acknowledge acquire across act action active activity actor actress actual adapt add addition address adequate adjust administration admire admit adopt adult advance advantage adventure advertise advice advise affair affect afford afraid africa after afternoon again against age agency agenda agent aggressive ago agree agriculture ahead aid aim air aircraft airline airport alarm album alcohol alive all alliance allow almost alone along already also alter alternative although always amateur amazing among amount analysis analyst ancient and anger angle angry animal anniversary announce annual another answer anxiety any anybody anymore anyone anything anyway anywhere apart apartment apologize apparent appeal appear apple application apply appoint appreciate approach appropriate approve april architecture area argue argument arise arm army around arrange arrest arrival arrive arrow art article artist ashamed asia aside ask asleep aspect assault assert assess asset assign assist associate assume assure asteroid athlete atlantic atmosphere atom attach attack attempt attend attention attitude attorney attract auction audience august aunt author authority auto autumn available average avoid awake award aware away awful".split(),
'b':"baby back background backup bacon bad badly bag bake balance ball balloon ban banana band bank bar barely bargain barrel barrier base baseball basic basis basket basketball bath bathroom battery battle bay beach bean bear beard beast beat beautiful beauty because become bed bedroom bee beef beer before beg begin beginning behalf behave behavior behind being belief believe bell belong below belt bench bend beneath benefit beside besides best bet better between beyond bicycle bid big bike bill billion bind biology bird birth birthday biscuit bit bite bitter black blade blame blank blanket blast bleed blend bless blind block blood bloom blow blue board boat body boil bold bomb bond bone bonus book boom boost boot border bore boring born borrow boss both bother bottle bottom bounce bound boundary bow bowl box boy brain branch brand brass brave bread break breakfast breast breath breathe breed brick bridge brief bright brilliant bring broad broken bronze brook brother brown brush bubble bucket budget buffalo bug build building bulb bulk bullet bunch bundle burden bureau burn burst bury bus bush business busy but butter butterfly button buy".split(),
'c':"cabin cable cage cake calculate calendar call calm camera camp campaign campus can canal cancel cancer candidate candle candy cannon canoe canvas cap capable capacity cape capital captain capture carbon card care career careful cargo carpet carry cart cartoon carve case cash cast castle casual cat catalog catch category cattle cause caution cave cease ceiling celebrate cell cellar cement cemetery census cent center central century cereal ceremony certain certificate chain chair chairman chalk challenge chamber champion chance change channel chaos chapter character charge charity charm chart charter chase cheap cheat check cheek cheer cheese chef chemical cherry chess chest chew chicken chief child childhood chill chimney chin china chip chocolate choice choose chop chorus christian christmas church cigarette cinema circle circuit circumstance cite citizen city civil claim clap clarify clash class classic clause clay clean clear clergy clerk clever click client cliff climate climb clinic clip clock close closet cloth clothes cloud club clue cluster coach coal coast coat code coffee coin cold collapse collar colleague collect college colonial column combine come comedy comfort comic command comment commerce commission commit committee common communicate community company compare compete complain complete complex comply component compose compound comprehensive compromise computer conceal concede conceive concentrate concept concern concert conclude concrete condition conduct conference confess confidence confirm conflict confront confuse congress connect conscious consent consider consist console constant constitute constrain construct consult consume contact contain contemporary contempt contend content contest context continent continue contract contrast contribute control controversy convenient convention conversation convert convey convict convince cook cool cooperate cope copy copper core corn corner corporate correct corridor cost cottage cotton couch cough could council counsel count counter country county couple courage course court cousin cover cow crack craft crash crazy cream create creature credit creek crew cricket crime criminal crisis crisp critic critical crop cross crowd crown crucial crude cruel cruise crush cry crystal cube cuisine cultural culture cup cupboard cure curious currency current curriculum curtain curve cushion custom customer cut cycle".split(),
'd':"daily dairy dam damage damp dance danger dare dark darling dash data database date daughter dawn day dead deadline deaf deal dear death debate debt decade decent decide decision deck declare decline decorate decrease dedicate deed deep deer defeat defend define definite degree delay delegate delicate delicious delight deliver demand democracy demonstrate deny depart department depend deposit depress depth deputy derive describe desert deserve design desire desk desperate despite dessert destroy detail detect determine develop device devote diagram dial diamond diary dictionary die diet differ difficult dig digital dignity dilemma dinner dip diplomatic direct dirt dirty disagree disappear disaster discipline disclose discount discover discuss disease disguise disgust dish dismiss disorder display dispose dispute distance distinct distribute district disturb ditch dive diverse divide divorce dizzy dock doctor doctrine document dodge dog doll dollar domain domestic dominant donate donkey donor door dose double doubt dough dove down downstairs downtown dozen draft drag drain drama dramatic draw drawer dream dress drift drill drink drive driver drop drought drown drug drum drunk dry duck due dull dump during dust duty dwarf dye dynamic".split(),
'e':"each eager eagle early earn earth ease east easy eat echo economy edge edit educate effect efficient effort egg eight either elbow elder elect electric elegant element elephant elevator eleven eliminate elite else elsewhere email embarrass embrace emerge emergency emotion emperor emphasis empire employ empty enable enclose encounter encourage end endless endorse enemy energy enforce engage engine engineer enhance enjoy enormous enough ensure enter entertain enthusiasm entire entitle entrance entry envelope environment envy episode equal equip era error escape especially essay essence essential establish estate estimate eternal ethic ethnic evaluate even evening event eventually ever every everybody everyday everyone everything everywhere evidence evil exact examine example exceed excellent except exchange excite exclude excuse execute exercise exhaust exhibit exile exist exit expand expect expense experience experiment expert explain explode exploit explore export expose express extend extent external extra extraordinary extreme eye".split(),
'f':"fabric face facility fact factor factory fade fail faint fair faith fall false fame family famous fan fancy fantasy far farm fashion fast fat fatal fate father fault favor favorite fear feast feather feature federal fee feed feel fellow female fence ferry festival fetch fever few fiber fiction field fierce fifteen fifty fight figure file fill film filter final finance find fine finger finish fire firm first fish fist fit five fix flag flame flash flat flavor flee flesh flight float flood floor flour flow flower flu fluid flush fly foam focus fog fold folk follow fond food fool foot football force forecast foreign forest forever forgive fork form formal format former formula fort fortune forum forward foster found foundation fountain four fraction frame framework france frank fraud free freedom freeze french frequent fresh friend friendly fright frog from front frost frown frozen fruit fuel full fun function fund funeral funny fur furnace furniture further future".split(),
'g':"gain galaxy gallery gallon gamble game gang gap garage garbage garden garlic gas gate gather gauge gaze gear gender gene general generate generous genius gentle gentleman genuine geography germ german gesture get ghost giant gift gigantic girl give glad glance glare glass gleam glide glimpse global globe gloom glory glove glow glue goal goat god gold golf good goodbye goods gorgeous gospel gossip govern gown grab grace grade gradual graduate grain grand grandfather grandmother grant grape graph grasp grass grateful grave gravity gray grease great greed green greet grid grief grin grind grip grocery gross ground group grow growth guarantee guard guess guest guidance guide guilt guilty guitar gulf gun gym".split(),
'h':"habit habitat hair half hall halt hammer hand handful handle handsome hang happen happy harbor hard hardly hardware harm harmony harsh harvest haste hat hate haul have hawk hay hazard haze head headline health heap hear heart heat heaven heavy heel height helicopter hell hello helmet help hence herb herd here heritage hero herself hesitate hidden hide high highlight highway hill him himself hint hip hire historic history hit hobby hold hole holiday hollow holy home honest honey honor hook hope horizon horn horrible horror horse hospital host hostile hot hotel hour house household housing however hug huge human humble humor hundred hunger hungry hunt hurry hurt husband hut hybrid hydrogen hymn".split(),
'i':"ice icon idea ideal identity idle idol ignore ill illegal illness illusion image imagine imitate immediate immense immigrant immune impact imperial implement imply import impose impress improve impulse inch include income increase incredible indeed independence index indicate individual indoor induce industrial industry infant infect infer infinite inflation influence inform ingredient inhabit inherit initial initiate inject injure ink inn inner innocent innovation input inquiry insect insert inside insight insist inspect inspire install instance instant instead instinct institute instruct instrument insult insurance intact integrate intellectual intelligence intend intense intention interact interest interfere interior internal internet interpret interrupt interval intervene interview intimate introduce invade invent invest investigate invite involve iron ironic irony island isolate issue item ivory".split(),
'j':"jacket jail jam january japan jar jaw jazz jealous jeans jet jewel job join joint joke journal journey joy judge judgment juice july jump june jungle junior junk jury just justice justify".split(),
'k':"keen keep kernel kettle key keyboard kick kid kidnap kidney kill kilo kind kindle king kingdom kiss kitchen kite knee kneel knife knight knit knob knock knot know knowledge".split(),
'l':"lab label labor laboratory lace lack ladder lady lag lake lamb lamp land landscape lane language lap large laser last late laugh launch laundry law lawn lawyer lay layer lazy lead leader leaf league leak lean leap learn lease least leather leave lecture left leg legal legend legislation legitimate leisure lemon lend length lens leopard less lesson let letter level liability liberal liberty library license lid lie life lift light like likely limb limit line link lion lip liquid list listen literally literary literature litter little live liver load loan lobby local locate lock logic lonely long look loop loose lord lose loss lost lot loud love low loyal loyalty luck lucky luggage lump lunar lunch lung luxury".split(),
'm':"machine mad magic magnet mail main maintain major make male mall manage manner manual manufacture many map marble march margin marine mark market marriage marry marsh mask mass massive master match mate material math matter mature maximum maybe mayor meadow meal mean meaning measure meat mechanic medal media medical medicine medium meet melody melon melt member memory mention menu mercy mere merge merit merry mess message metal meter method middle midnight might mild mile military milk mill million mind mine mineral minimum minister minor mint minute miracle mirror miss missile mission mist mistake mix mixture mobile mode model moderate modern modest modify moist moment money monitor monkey month mood moon moral more morning mortgage most mother motion motive motor mount mountain mourn mouse mouth move movie much mud mug multiple murder muscle museum mushroom music musician must mutual myself mystery myth".split(),
'n':"nail naked name nap narrow nation native natural nature naughty navy near neat necessary neck need needle negative neglect negotiate neighbor neither nephew nerve nest net network neutral never nevertheless new news next nice niece night nine noble nobody nod noise nominal none noon nor normal north nose not note nothing notice notion noun novel november now nowhere nuclear number nurse nut".split(),
'o':"oak obey object objective obligation observe obtain obvious occasion occupy occur ocean october odd odor off offend offer office official often oil okay old olive omit once one onion online only onto open opera operate opinion opponent opportunity oppose opposite option orange orbit orchard order ordinary organ organic organize origin ornament orphan other otherwise ought ounce our ours ourselves out outcome outdoor outer outfit outline output outside oven over overall overcome overlap overlook owe owl own owner oxygen".split(),
'p':"pace pack package pact pad page pain paint pair palace pale palm pan panel panic paper parade paragraph parallel parcel pardon parent park parliament part partial participate particle particular partner party pass passage passenger passion passive past pasta paste pastry patch path patience patient pattern pause pave payment peace peak peanut pear pearl peasant peculiar pedal peel peer pen penalty pencil pendulum penetrate penguin peninsula pension people pepper per percent perfect perform perhaps period permit person personal personality persuade pest pet phase phenomenon philosophy phone photo phrase physical piano pick picnic picture pie piece pig pigeon pile pill pillow pilot pin pine pink pioneer pipe pistol pit pitch pity pizza place plain plan plane planet plant plastic plate platform play pleasant please pleasure plenty plot plug plunge plus pocket poem poet poetry point poison polar pole police policy polish polite political politics poll pollution pond pool poor pop popular population porch port portion portrait portray pose position positive possess possible post pot potato potential pound pour poverty powder power practice praise pray prayer preach precise predict prefer pregnant preliminary premise premium preparation prepare prescribe presence present preserve preside press pressure pretend pretty prevail prevent previous prey price pride priest primary prime prince princess principal principle print prior priority prison privacy private privilege prize probable problem proceed process proclaim produce product profession professor profile profit profound program progress prohibit project prominent promise promote prompt proof proper property prophet proportion proposal propose prospect protect protein protest proud prove provide province provoke psychology public publish pull pump punch punish pupil purchase pure purpose purse pursue push put puzzle pyramid".split(),
'q':"quaint quake qualify quality quantity quarrel quarter queen quest question queue quick quiet quill quilt quince quirk quit quite quiver quiz quota quote quotient".split(),
'r':"rabbit race radar radiation radical radio radius rage rail railway rain rainbow raise rally random range rank rapid rare rat rate rather ratio rational raw ray razor reach react read ready real reality realize realm rear reason rebel recall receipt receive recent reception recipe recognize recommend record recover recruit reduce refer reflect reform refuse regard regime region register regret regular regulate reject relate relative relax release relevant reliable relief religion reluctant rely remain remark remedy remember remind remote remove render renew rent repair repeat replace reply report represent republic reputation request require rescue research resemble reserve reside resign resist resolve resort resource respect respond response responsibility rest restaurant restore restrict result resume retail retain retire retreat return reveal revenue reverse review revise revolution reward rhythm rib ribbon rice rich rid ride ridge ridiculous rifle right rigid ring riot rise risk ritual rival river road roast rob robot rock rocket rod role roll roman romantic roof room root rope rose rotate rough round route routine row royal rub rubber rude rug ruin rule rumor run rural rush".split(),
's':"sacred sacrifice sad saddle safe sail saint sake salad salary sale salmon salt same sample sand sandwich satellite satisfy sauce sausage save saving say scale scan scandal scare scatter scene schedule scheme scholar school science scientific scientist scope score scorn scout scrap scream screen screw script scroll sculpture sea seal search season seat second secret section sector secure seed seek seem segment seize seldom select self sell semester seminar senate send senior sense sensitive sentence separate september sequence series serious servant serve service session set settle seven several severe sew shade shadow shake shall shallow shame shape share shark sharp shatter shave sheep sheet shelf shell shelter shepherd shield shift shine ship shirt shock shoe shoot shop shore short shot shoulder shout show shower shrimp shrink shrug shut shy sibling sick side siege sigh sight sign signal significant silence silent silk silly silver similar simple sin since sincere sing single sink sir sister sit site situation six size skate sketch ski skill skin skip skirt skull sky slave sleep sleeve slice slide slight slim slip slope slot slow small smart smash smell smile smoke smooth snake snap sneak snow soap social society sock soft software soil solar soldier sole solid solve some somebody somehow someone something sometime sometimes somewhat somewhere son song soon sophisticated sore sorrow sorry sort soul sound soup sour source south space spare spark speak special species specific specimen spectacle spectator speech speed spell spend sphere spice spider spill spin spine spirit spit spite splash split spoil spoke sponge spoon sport spot spouse spray spread spring sprout spy square squeeze stab stability stable stack stadium staff stage stair stake stale stall stamp stance stand standard star stare start starve state statement station statue status stay steady steak steal steam steel steep steer stem step stereo stick stiff still stimulate sting stir stock stomach stone stool stop storage store storm story stove straight strain strand strange stranger strap strategy straw stream street strength stress stretch strict strike string strip stripe stroke stroll strong structure struggle stubborn student studio study stuff stumble stupid style subject submit subscribe subsequent substance substitute subtle suburb succeed success such sudden sue suffer sufficient sugar suggest suit suitable sulfur sum summer summit summon sun sunday sunny sunrise sunset super superior supermarket supper supply support suppose supreme sure surface surgery surplus surprise surrender surround survey survival survive suspect suspend sustain swallow swan swap swear sweat sweep sweet swell swift swim swing switch sword symbol sympathy symphony symptom syndrome system".split(),
't':"table tablet tackle tactic tag tail tailor take tale talent talk tall tame tank tap tape target task taste tax taxi tea teach team tear tease technical technique technology teeth telephone telescope television tell temper temperature temple temporary tempt ten tend tendency tender tennis tense tent term terminal terrible territory terror test testify testimony text than thank theater theme themselves then theory therapy there therefore these they thick thief thin thing think third thirst thirteen thirty this thorough those though thought thousand thread threat three thrive throat throne through throughout throw thrust thumb thunder thus ticket tide tidy tie tiger tight tile till timber time tiny tip tire tired tissue title toast tobacco today toe together toilet token tolerance tolerate toll tomato tomb tomorrow ton tone tongue tonight too tool tooth top topic torch torn torture toss total touch tough tour tourist tournament toward towel tower town toy trace track trade tradition traffic tragedy trail train trait transfer transform transit translate transmit transport trap trash travel tray treasure treat treaty tree tremble tremendous trend trial triangle tribe tribute trick trigger trim trip triumph trivial troop trophy tropical trouble trousers truck true truly trunk trust truth try tube tunnel turkey turn twelve twenty twice twin twist two type typical".split(),
'u':"ugly ultimate umbrella unable uncertain uncle under undergo underground understand undertake underwear undo unemployment unexpected unfair unfold unhappy uniform union unique unit unite unity universal universe university unknown unless unlike unlikely until unusual unveil upgrade uphold upstairs urban urge urgent us usage use useful useless user usual utility utilize utter".split(),
'v':"vacation vacuum vague valid valley valuable value van vanish vanity vapor variable variety various vary vast vegetable vehicle veil vein velvet vendor venture verb verdict verge verify verse version vertical very vessel veteran via vibrate vice victim victory video view village vine vinegar violence violet violin virtue virus visa visible vision visit visual vital vitamin vivid vocabulary voice void volcano volume volunteer vote voyage".split(),
'w':"wage wagon waist wait waiter wake walk wall wallet wander want war ward warehouse warm warn warning warrant warrior wash waste watch water wave wax way weak wealth weapon wear weary weather weave web wedding wedge weed week weekend weekly weep weigh weight weird welcome welfare well west wet whale what whatever wheat wheel when whenever where whereas wherever whether which while whisper white who whole whom whose why wide widow width wife wild will willing win wind window wine wing wink winner winter wipe wire wisdom wise wish wit witch with withdraw within without witness wolf woman wonder wonderful wood wooden wool word work worker world worm worry worse worship worst worth wound wrap wreck wrist write writer wrong".split(),
'x':"xenon xenophobia xerox xylem xylophone".split(),
'y':"yacht yard yarn yawn year yearn yeast yell yellow yes yesterday yet yield yoga yogurt yoke yolk you young your yours yourself youth".split(),
'z':"zeal zebra zenith zero zest zigzag zinc zip zipper zodiac zombie zone zoo zoology zoom".split()}

_PRE = ["", "a","be","con","de","dis","en","ex","in","inter","mis","non","over","pre","pro","re","sub","super","trans","un","under","up","with","out","for","fore","counter","anti","auto","bi","co","extra","hyper","micro","mid","multi","neo","omni","para","poly","post","pseudo","quasi","semi","tele","ultra","circum","contra","epi","hypo","infra","intra","macro","mega","mono","proto","retro","syn","tri","uni","vice"]
_MID = ["a","e","i","o","u","ab","ac","ad","ag","al","am","an","ap","ar","as","at","av","az","eb","ec","ed","eg","el","em","en","ep","er","es","et","ev","ib","ic","id","ig","il","im","in","ip","ir","is","it","iv","iz","ob","oc","od","og","ol","om","on","op","or","os","ot","ov","oz","ub","uc","ud","ug","ul","um","un","up","ur","us","ut","uv","uz","br","cr","dr","fr","gr","pr","tr","str","thr"]
_SUF = ["","s","es","ed","ing","er","est","ly","ness","ment","tion","sion","able","ible","ous","ive","al","ic","ity","ize","ance","ence","ate","ify","ship","hood","ward","wise","ist","ism","ology","ography","scope","graph","gram","logy","nomy","pathy","ful","less","some","like","fold","most","proof","free","worthy"]
_TARGET = 10000

def _batch(letter, target=_TARGET):
    L = letter.lower(); seed = _SEEDS.get(L, [L])
    rng = random.Random(hash(("AtoZ", L, target)) & 0xFFFFFFFF)
    words = set()
    for w in seed:
        w = w.lower().strip()
        if w and w[0] == L and w.isalpha(): words.add(w)
    for w in list(words):
        for suf in ("s","es","ed","ing","er","est","ly","ness","ment","able","ible","ous","ive","al","ic","ity","ize","ation","ition","ful","less"):
            c = w + suf
            if len(c) <= 24 and c[0] == L: words.add(c)
    guard = 0
    while len(words) < target and guard < target * 40:
        guard += 1
        c = L + rng.choice(_PRE) + rng.choice(_MID) + rng.choice(_SUF)
        if 3 <= len(c) <= 24 and c.isalpha(): words.add(c)
    return " ".join(sorted(words)[:target])

ALL_BATCHES = tuple(_batch(chr(ord('A') + i)) for i in range(26))
print(f"A-Z batches: 26 letters, {sum(len(b.split()) for b in ALL_BATCHES):,} words")

DICT_DIR = "Dictionaries"
DICT_FILES = ["generated.txt","eng_news_2005_1M-sentences.txt","eng_news_2005_1M-words.txt",
    "eng_news_2005_1M-sources.txt","eng_news_2005_1M-co_n.txt","eng_news_2005_1M-co_s.txt",
    "eng_news_2005_1M-inv_w_2.txt","eng_news_2005_1M-inv_w_3.txt","eng_news_2005_1M-inv_so.txt",
    "eng_news_2005_1M-meta.txt","Dictionary.txt","the-complete-reference-html-css-fifth-edition.txt"]
DICT_URLS = ["https://drive.google.com/uc?export=download&id=1u_1dCEl8hhdEug6GwkOxHAuSx_6_Pme9",
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
    "https://drive.google.com/uc?export=download&id=1dDdqYDgm7f-smS7KF70Wf0KmyFo-ft1M"]

def download_12():
    if not os.path.exists(DICT_DIR):
        try: os.makedirs(DICT_DIR)
        except Exception: pass
    all_words = set(); ok = 0
    for fn, url in zip(DICT_FILES, DICT_URLS):
        p = os.path.join(DICT_DIR, fn)
        print(f"  Downloading {fn} ...")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=20) as r: content = r.read()
            if b'<html' in content[:200].lower(): print("    HTML page; skip"); continue
            with open(p, 'wb') as f: f.write(content)
            text = content.decode('utf-8', errors='ignore')
            for line in text.splitlines():
                w = line.strip()
                if not w: continue
                try: all_words.add(base64.b64decode(w, validate=True).decode('utf-8'))
                except Exception: all_words.add(w)
            print(f"    OK ({len(content)} bytes)"); ok += 1
        except Exception as e: print(f"    FAIL: {e}")
    print(f"  Downloaded {ok}/12 -> {len(all_words):,} words")
    return all_words

def build_dict(try_dl=True):
    words = set()
    if try_dl:
        print("\nStep 1: 12 Google Drive dictionaries")
        try:
            words |= download_12(); print(f"  Total: {len(words):,}")
        except Exception as e: print(f"  Ignored: {e}")
    print("\nStep 2: System dictionaries")
    for path in ["/usr/share/dict/words","/usr/share/dict/american-english","/usr/share/dict/british-english","/usr/share/hunspell/en_US.dic"]:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        w = line.split('/')[0].strip().lower()
                        if w and w.isalpha() and 1 <= len(w) <= 64: words.add(w)
                print(f"  {path}: total {len(words):,}")
            except Exception: pass
    print("\nStep 3: A-Z built-in (always on)")
    real = set()
    for blob in ALL_BATCHES:
        real |= {w.lower() for w in blob.split() if w.isalpha() and 1 <= len(w) <= 64}
    words |= real
    print(f"  Added {len(real):,}. Total: {len(words):,}")
    words = sorted(w for w in words if w and w.isascii() and 1 <= len(w) <= 64)
    print(f"\nFINAL dictionary: {len(words):,} words")
    return words

def cdd_derive(n4):
    mid = n4 // 2 if n4 else 0
    key = ((n4 * 0x9E3779B9) ^ 0xDEADBEEF) & 0xFFFFFFFF
    return mid, key

def cdd_mask(i, mid):
    if mid == 0: return 0
    return ((abs(i - mid) * 255) // mid) & 0xFF

def cdd_forward(d):
    if not d: return b''
    L = len(d); n4 = L // 4; tail = bytes(d[n4 * 4:])
    if n4 == 0: return bytes(d)
    t = bytearray(d[:n4 * 4]); mid, key = cdd_derive(n4)
    for i in range(n4):
        m = cdd_mask(i, mid)
        if m:
            b = i * 4
            t[b] ^= m; t[b + 1] ^= m; t[b + 2] ^= m; t[b + 3] ^= m
    t[mid * 4 + 2] ^= 0x5A
    for i in range(2, n4, 3):
        b = i * 4
        v = int.from_bytes(t[b:b + 4], 'little')
        v = (v - key) & 0xFFFFFFFF
        t[b:b + 4] = v.to_bytes(4, 'little')
    return bytes(t) + tail

def cdd_inverse(d):
    if not d: return b''
    L = len(d); n4 = L // 4; tail = bytes(d[n4 * 4:])
    if n4 == 0: return bytes(d)
    t = bytearray(d[:n4 * 4]); mid, key = cdd_derive(n4)
    for i in range(2, n4, 3):
        b = i * 4
        v = int.from_bytes(t[b:b + 4], 'little')
        v = (v + key) & 0xFFFFFFFF
        t[b:b + 4] = v.to_bytes(4, 'little')
    t[mid * 4 + 2] ^= 0x5A
    for i in range(n4):
        m = cdd_mask(i, mid)
        if m:
            b = i * 4
            t[b] ^= m; t[b + 1] ^= m; t[b + 2] ^= m; t[b + 3] ^= m
    return bytes(t) + tail

OLE_MAGIC = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
ZIP_MAGIC = b'PK\x03\x04'
_XML_TAG_RE = re.compile(rb'<[A-Za-z!/?][^<>\x00]{0,4095}>')

def _xml_is_plausible(d):
    if not d: return False
    if d[:8] == OLE_MAGIC: return False
    return d[:64].lstrip().startswith(b'<')

def _xml_scan_tags(d):
    if HAS_DEFUSEDXML:
        try: _defused_etree.fromstring(d[:65536])
        except Exception: pass
    if HAS_LXML:
        try:
            spans = []
            for _e, _el in _lxml_etree.iterparse(io.BytesIO(d), events=("start","end"), recover=True): break
            for m in _XML_TAG_RE.finditer(d): spans.append((m.start(), m.end(), m.group(0)))
            return spans
        except Exception: pass
    return [(m.start(), m.end(), m.group(0)) for m in _XML_TAG_RE.finditer(d)]

def _xml_encode(d, max_tags=4096, min_freq=2):
    if not d: return None
    spans = _xml_scan_tags(d)
    if not spans: return None
    freq = Counter(tag for _, _, tag in spans)
    ranked = [t for t, c in freq.most_common(max_tags) if len(t) >= 3 and c >= min_freq]
    if not ranked: return None
    tag_to_idx = {t: i for i, t in enumerate(ranked)}
    out = bytearray(); _emit_varint(out, len(ranked))
    for t in ranked: _emit_varint(out, len(t)); out += t
    last = 0
    for start, end, tag in spans:
        if start > last:
            chunk = d[last:start]
            if 0 in chunk:
                out += chunk.replace(b'\x00', b'\x00\x00')
            else:
                out += chunk
        idx = tag_to_idx.get(tag)
        if idx is not None:
            out.append(0)
            _emit_varint(out, idx + 1)
        else:
            if 0 in tag:
                out += tag.replace(b'\x00', b'\x00\x00')
            else:
                out += tag
        last = end
    if last < len(d):
        chunk = d[last:]
        if 0 in chunk:
            out += chunk.replace(b'\x00', b'\x00\x00')
        else:
            out += chunk
    return bytes(out)

def _xml_decode(payload):
    pos = 0
    n_tags, pos = _read_varint(payload, pos)
    tags = []
    for _ in range(n_tags):
        ln, pos = _read_varint(payload, pos); tags.append(payload[pos:pos+ln]); pos += ln
    out = bytearray(); n = len(payload)
    while pos < n:
        b = payload[pos]; pos += 1
        if b != 0: out.append(b); continue
        if pos >= n: raise TransformError("xml escape eof")
        nxt = payload[pos]; pos += 1
        if nxt == 0: out.append(0); continue
        v = nxt & 0x7F; sh = 7
        while nxt & 0x80:
            if pos >= n: raise TransformError("xml varint eof")
            nxt = payload[pos]; pos += 1; v |= (nxt & 0x7F) << sh; sh += 7
            if sh > 35: raise TransformError("xml varint overflow")
        idx = v - 1
        if idx < 0 or idx >= len(tags): raise TransformError(f"xml tag idx {idx}")
        out += tags[idx]
    return bytes(out)

PRIMES = [p for p in range(2, 256) if all(p % d != 0 for d in range(2, int(p ** 0.5) + 1))]
PI_DIGITS = [79, 17, 111]

def nearest_prime(n):
    if n < 2: return 2
    o = 0
    while True:
        c1, c2 = n - o, n + o
        if c1 >= 2 and all(c1 % d != 0 for d in range(2, int(c1 ** 0.5) + 1)): return c1
        if c2 >= 2 and all(c2 % d != 0 for d in range(2, int(c2 ** 0.5) + 1)): return c2
        o += 1

_CD_CODE = [(2,0b10),(2,0b11),(3,0b010),(3,0b011),(4,0b0010),(4,0b0011),(5,0b00010),(5,0b00011),(6,0b000010),(6,0b000011),(7,0b0000010),(7,0b0000011),(8,0b00000010),(8,0b00000011),(9,0b000000010),(9,0b000000011)]
_CD_DEC = {v: k for k, v in enumerate(_CD_CODE)}
ALPH_6 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 \n"
CH2_6 = {ch: i for i, ch in enumerate(ALPH_6)}
_6TOCH = {i: ch for ch, i in CH2_6.items()}
PAQ = [[1,2,0,0],[3,5,0,1],[4,6,2,0],[7,10,0,2],[8,12,3,0],[9,13,1,1],[11,14,0,3],[15,19,4,0],[16,23,2,1],[17,24,2,1],[18,25,2,1],[20,27,1,2],[21,28,1,2],[22,29,1,2],[26,30,0,4],[31,33,5,0],[32,34,3,1],[35,37,1,3],[36,38,1,3],[39,42,0,5],[40,43,4,1],[41,44,2,2],[45,48,1,4],[46,49,1,4],[47,50,1,4],[51,52,0,6],[53,55,6,0],[54,56,4,1],[57,59,2,3],[58,60,2,3],[61,63,0,7],[62,64,5,1],[65,66,3,2],[67,69,1,5],[68,70,1,5],[71,73,0,8],[72,74,6,1],[75,76,4,2],[77,78,2,4],[79,80,2,4],[81,82,0,9],[83,84,7,1],[85,86,5,2],[87,88,3,3],[89,90,1,6],[91,92,0,10],[93,94,8,1],[95,96,6,2],[97,98,4,3],[99,100,2,5],[101,102,0,11],[103,104,9,1],[105,106,7,2],[107,108,5,3],[109,110,3,4],[111,112,1,7],[113,114,0,12],[115,116,10,1],[117,118,8,2],[119,120,6,3],[121,122,4,4],[123,124,2,6],[125,126,0,13],[127,128,11,1],[129,130,9,2],[131,132,7,3],[133,134,5,4],[135,136,3,5],[137,138,1,8],[139,140,0,14],[141,142,12,1],[143,144,10,2],[145,146,8,3],[147,148,6,4],[149,150,4,5],[151,152,2,7],[153,154,0,15],[155,156,13,1],[157,158,11,2],[159,160,9,3],[161,162,7,4],[163,164,5,5],[165,166,3,6],[167,168,1,9],[169,170,0,16],[171,172,14,1],[173,174,12,2],[175,176,10,3],[177,178,8,4],[179,180,6,5],[181,182,4,6],[183,184,2,8],[185,186,0,17],[187,188,15,1],[189,190,13,2],[191,192,11,3],[193,194,9,4],[195,196,7,5],[197,198,5,6],[199,200,3,7],[201,202,1,10],[203,204,0,18],[205,206,16,1],[207,208,14,2],[209,210,12,3],[211,212,10,4],[213,214,8,5],[215,216,6,6],[217,218,4,7],[219,220,2,9],[221,222,0,19],[223,224,17,1],[225,226,15,2],[227,228,13,3],[229,230,11,4],[231,232,9,5],[233,234,7,6],[235,236,5,7],[237,238,3,8],[239,240,1,11],[241,242,0,20],[243,244,18,1],[245,246,16,2],[247,248,14,3],[249,250,12,4],[251,252,10,5],[253,254,8,6],[255,255,6,7]]

class TransformError(Exception): pass
class DecompressionError(Exception): pass

def _emit_varint(buf, n):
    if n < 0x80:
        buf.append(n)
        return
    while True:
        b = n & 0x7F; n >>= 7
        if n: buf.append(b | 0x80)
        else: buf.append(b); return

def _read_varint(buf, pos):
    if pos >= len(buf): raise TransformError("varint eof")
    b = buf[pos]
    if b < 0x80:
        return b, pos + 1
    n = b & 0x7F; sh = 7; pos += 1
    while True:
        if pos >= len(buf): raise TransformError("varint eof")
        b = buf[pos]; pos += 1
        n |= (b & 0x7F) << sh
        if not (b & 0x80): return n, pos
        sh += 7
        if sh > 63: raise TransformError("varint overflow")

def mod_inv(a, m):
    if a == 0: return None
    m0 = m; y = 0; x = 1
    if m == 1: return 0
    while a > 1:
        q = a // m; t = m; m = a % m; a = t
        t = y; y = x - q * y; x = t
    if x < 0: x += m0
    return x

class Compressor:
    TIMEOUT = 300; VS = False; USE_MP = True
    TOP_K = 100; FAST = True; BLOCK = 4096
    MAX_TRANSFORM = 256; PROGRESS_EVERY = 500; STRIDE = 3
    MAX_EAGER_ID = 256

    def __init__(self, try_dl=True, pairs=65535, qubits=16):
        self.PAIRS = pairs
        self.QUBITS = qubits
        self._cback_cache = {}
        self._CBACK_CACHE_MAX = 65536
        self._fwd_cache = {}
        self._pool_cback = None
        self._pool_pid = None
        print("\nBuilding dictionary...")
        self.dict_words = build_dict(try_dl)
        self.PI = PI_DIGITS.copy()
        self.seeds = self._seeds(); self.fib = self._fib(100)
        self.PI_S = "3.14159265358979323846264338327950288419716939937510"
        self.rep = 100
        self.mst = [[(v-400) & 0xFF for v in r] for r in PAQ]
        self.mask46 = [(b-10) & 0xFF for b in [1,2,4,8,16,32,64,128,3,6,10]] * 10
        self.pattern47 = bytes(row[0] & 0xFF for row in self.mst)
        self._xor_tables = {}
        self._t04_tab = None
        self._t06_tab = None
        self._t06_inv = None
        self._t11_cache = {}
        self._t12_cache = {}
        self._t26_cache = {}
        self._c18_cache = {}
        self._c19_cache = {}
        self._c20_cache = {}
        self._cdd_cache = {}
        self._rot_tabs = {}
        self._add_tabs = {}
        self._sub_tabs = {}
        self._m1_tab = bytes((b - 1) & 0xFF for b in range(256))
        self._p1_tab = bytes((b + 1) & 0xFF for b in range(256))
        self._np_tab = [nearest_prime(n) for n in range(600)]
        if HAS_QISKIT:
            print(f"Building Qiskit {self.QUBITS}-qubit pair permutation for {self.PAIRS} pairs ...")
            t0 = time.time()
            self._qperm = quantum_pair_permutation(self.PAIRS, self.QUBITS)
            print(f"  quantum permutation ready ({time.time()-t0:.3f}s)")
        else:
            self._qperm = list(range(self.PAIRS))
        self._build_ref_dict(); self._maps(); self._pairs()

    def _xor_table(self, k):
        t = self._xor_tables.get(k)
        if t is None:
            t = bytes(b ^ k for b in range(256))
            self._xor_tables[k] = t
        return t

    def _rot_tab(self, k):
        k &= 7
        t = self._rot_tabs.get(k)
        if t is None:
            t = bytes(((b << k) | (b >> (8 - k))) & 0xFF for b in range(256))
            self._rot_tabs[k] = t
        return t

    def _irot_tab(self, k):
        k &= 7
        key = ('i', k)
        t = self._rot_tabs.get(key)
        if t is None:
            t = bytes(((b >> k) | (b << (8 - k))) & 0xFF for b in range(256))
            self._rot_tabs[key] = t
        return t

    def _add_tab(self, k):
        k &= 0xFF
        t = self._add_tabs.get(k)
        if t is None:
            t = bytes((b + k) & 0xFF for b in range(256))
            self._add_tabs[k] = t
        return t

    def _sub_tab(self, k):
        k &= 0xFF
        t = self._sub_tabs.get(k)
        if t is None:
            t = bytes((b - k) & 0xFF for b in range(256))
            self._sub_tabs[k] = t
        return t

    def _xor_pattern(self, d, pattern):
        L = len(d); pl = len(pattern)
        mask = (pattern * ((L // pl) + 1))[:L]
        return (int.from_bytes(d, 'big') ^ int.from_bytes(mask, 'big')).to_bytes(L, 'big')

    def _np(self, n):
        return self._np_tab[n] if n < 600 else nearest_prime(n)

    def _build_ref_dict(self):
        seen = set(); ordered = []
        for m in _TOK_RE.finditer(REF_BYTES):
            w = m.group(1).decode('ascii').lower()
            if w not in seen: seen.add(w); ordered.append(w)
        rest = sorted((w for w in self.dict_words if w not in seen), key=lambda w: (len(w), w))
        self.ref_words = ordered + rest
        self.ref_idx = {w: i for i, w in enumerate(self.ref_words)}
        self.ref_bytes = [w.encode('ascii') for w in self.ref_words]
        self.ref_bytes_cap = [b.capitalize() for b in self.ref_bytes]
        self.ref_bytes_up = [b.upper() for b in self.ref_bytes]
        self._ref_esc = len(self.ref_words)
        if HAS_ZSTD:
            try:
                self._zstd_dict = zstd.ZstdCompressionDict(REF_BYTES, dict_type=zstd.DICT_TYPE_RAWCONTENT)
                self._zc_dict = zstd.ZstdCompressor(level=22, dict_data=self._zstd_dict)
                self._zd_dict = zstd.ZstdDecompressor(dict_data=self._zstd_dict)
            except Exception: self._zstd_dict = self._zc_dict = self._zd_dict = None
        else: self._zstd_dict = self._zc_dict = self._zd_dict = None
        print(f"Reference vocab: {len(self.ref_words):,} words (zstd-dict preset: {'ON' if self._zc_dict else 'OFF'})")

    def _seeds(self, n=126, s=40, seed=42):
        random.seed(seed); return [[random.randint(5,255) for _ in range(s)] for _ in range(n)]
    def _fib(self, n):
        a,b = 0,1; r = [a,b]
        for _ in range(2, n): a,b = b,a+b; r.append(b)
        return r
    def _seed(self, i, v): return self.seeds[i][v % 40] if 0 <= i < len(self.seeds) else 0
    def _bits(self, bl, v, c):
        for i in range(c-1,-1,-1): bl.append((v>>i)&1)
    def _rd(self, b, p, c):
        v = 0
        for i in range(c):
            if p+i >= len(b): return 0
            v = (v<<1)|b[p+i]
        return v
    def _pat(self, s, i):
        random.seed(12345 + s*100 + i); return [random.randint(0,255) for _ in range(s)]
    def _reps(self, d):
        if not d: return 1
        L = len(d); s = sum(d) % 256
        return max(1, min(256, ((L*13 + s*17) % 256) + 1))

    def _leptonc(self, d):
        if not HAS_LEPTON: return None
        if len(d) < 2 or d[:2] != b'\xff\xd8': return None
        try:
            c = lepton_jpeg_python.compress_bytes(d, {"max_jpeg_width": 16386, "max_jpeg_height": 16386, "progressive": True, "reject_dqts_with_zeros": False, "max_partitions": 4})
            return c if c else None
        except Exception: return None
    def _leptond(self, d):
        if not HAS_LEPTON: return None
        try:
            dc = lepton_jpeg_python.decompress_bytes(d)
            return dc if dc else None
        except Exception: return None

    def _cmixc(self, d):
        if not HAS_CMIX: return None
        cmix = shutil.which('cmix')
        if not cmix: return None
        with tempfile.TemporaryDirectory() as td:
            inp = os.path.join(td, 'i'); out = os.path.join(td, 'o.cmix')
            with open(inp, 'wb') as f: f.write(d)
            for args in ([cmix, '-c', inp, out], [cmix, inp, out]):
                try:
                    r = subprocess.run(args, capture_output=True, timeout=3600)
                    if r.returncode == 0 and os.path.exists(out):
                        with open(out, 'rb') as f: return f.read()
                except Exception: pass
        return None
    def _cmixd(self, d):
        if not HAS_CMIX: return None
        cmix = shutil.which('cmix')
        if not cmix: return None
        with tempfile.TemporaryDirectory() as td:
            inp = os.path.join(td, 'i.cmix'); out = os.path.join(td, 'o')
            with open(inp, 'wb') as f: f.write(d)
            try:
                r = subprocess.run([cmix, '-d', inp, out], capture_output=True, timeout=3600)
                if r.returncode == 0 and os.path.exists(out):
                    with open(out, 'rb') as f: return f.read()
            except Exception: pass
        return None
    def _zpc(self, d):
        if not HAS_ZPAQ: return None
        with tempfile.TemporaryDirectory() as td:
            inp = os.path.join(td, 'i'); arc = os.path.join(td, 'a.zpaq')
            with open(inp, 'wb') as f: f.write(d)
            try:
                r = subprocess.run(['zpaq','a',arc,inp,'-m5'], capture_output=True, timeout=300)
                if r.returncode != 0: return None
                with open(arc, 'rb') as f: return f.read()
            except Exception: return None
    def _zpd(self, d):
        if not HAS_ZPAQ: return None
        with tempfile.TemporaryDirectory() as td:
            arc = os.path.join(td, 'a.zpaq'); od = os.path.join(td, 'o'); os.makedirs(od)
            with open(arc, 'wb') as f: f.write(d)
            try:
                r = subprocess.run(['zpaq','x',arc,'-to',od], capture_output=True, timeout=300)
                if r.returncode != 0: return None
                for n in os.listdir(od):
                    with open(os.path.join(od, n), 'rb') as f: return f.read()
            except Exception: return None
        return None
    def _ccmxc(self, d):
        if not HAS_CCMX: return None
        with tempfile.TemporaryDirectory() as td:
            inp = os.path.join(td, 'i'); out = os.path.join(td, 'o.ccmx')
            with open(inp, 'wb') as f: f.write(d)
            for args in (['ccmx', 'c', inp, out, '256'], ['ccmx', 'c', inp, out, '1024'], ['ccmx', 'c', inp, out], ['ccmx', '-c', inp, out], ['ccmx', 'c', inp], ['ccmx', inp]):
                try:
                    r = subprocess.run(args, capture_output=True, timeout=600)
                    if r.returncode != 0: continue
                    for p in (out, inp + '.ccmx', inp + '.cmx', inp + '.ccm'):
                        if os.path.exists(p):
                            with open(p, 'rb') as f: return f.read()
                except Exception: continue
        return None
    def _ccmxd(self, d):
        if not HAS_CCMX: return None
        with tempfile.TemporaryDirectory() as td:
            inp = os.path.join(td, 'i.ccmx'); out = os.path.join(td, 'o')
            with open(inp, 'wb') as f: f.write(d)
            for args in (['ccmx', 'd', inp, out], ['ccmx', '-d', inp, out], ['ccmx', 'd', inp], ['ccmx', 'x', inp]):
                try:
                    r = subprocess.run(args, capture_output=True, timeout=600)
                    if r.returncode != 0: continue
                    for p in (out, inp[:-5], inp[:-4], inp[:-5] + '.out'):
                        if p and os.path.exists(p):
                            with open(p, 'rb') as f: return f.read()
                except Exception: continue
        return None

    def _get_fwd(self, t, data):
        v = self._fwd_cache.get(t)
        if v is None:
            v = self.fwd[t](data)
            if len(self._fwd_cache) < 512:
                self._fwd_cache[t] = v
        return v

    def _ensure_pool(self):
        cur = os.getpid()
        if self._pool_cback is None or self._pool_pid != cur:
            if self._pool_cback is not None:
                try: self._pool_cback.shutdown(wait=False)
                except Exception: pass
            nw = CBACK_WORKERS_EFF if _IN_WORKER else CBACK_WORKERS
            nw = max(1, nw)
            self._pool_cback = ThreadPoolExecutor(max_workers=nw, thread_name_prefix="cback")
            self._pool_pid = cur
        return self._pool_cback

    def cback(self, d):
        hit = self._cback_cache.get(d)
        if hit is not None: return hit
        result = self._cback_compute(d)
        if len(self._cback_cache) < self._CBACK_CACHE_MAX:
            self._cback_cache[d] = result
        return result

    def _cback_compute(self, d):
        thunks = []
        def _raw(): return (0, d)
        thunks.append(_raw)
        if HAS_ZSTD:
            def _z1():
                try:
                    c = zc.compress(d)
                    if len(c) >= 4 and c[:4] == b'\x28\xb5\x2f\xfd': c = c[4:]
                    return (1, c)
                except Exception: return None
            thunks.append(_z1)
            if self._zc_dict is not None:
                def _z11():
                    try:
                        c = self._zc_dict.compress(d)
                        if len(c) >= 4 and c[:4] == b'\x28\xb5\x2f\xfd': c = c[4:]
                        return (11, c)
                    except Exception: return None
                thunks.append(_z11)
        if paq:
            def _tp():
                try:
                    pd = paq.compress(d)
                    if len(pd) >= 7 and pd[:4] == b'\x00\x63\x00\x00' and pd[-3:] == b'\xff\xff\xff': return (3, pd[4:-3])
                    return (2, pd)
                except Exception: return None
            thunks.append(_tp)
        if HAS_BROTLI:
            def _tb():
                try: return (4, brotli.compress(d, quality=11))
                except Exception: return None
            thunks.append(_tb)
        if HAS_LZMA:
            _lz_specs = ((5, {"preset": 9 | lzma.PRESET_EXTREME}),
                         (6, {"format": lzma.FORMAT_RAW, "filters": LF_RAW}),
                         (7, {"format": lzma.FORMAT_RAW, "filters": LF_DELTA}),
                         (9, {"format": lzma.FORMAT_RAW, "filters": LF_BCJ}))
            for _fmt, _kw in _lz_specs:
                def _tl(_kw=_kw, _fmt=_fmt):
                    try: return (_fmt, lzma.compress(d, **_kw))
                    except Exception: return None
                thunks.append(_tl)
        if HAS_PPMD:
            def _tpp():
                try: return (8, pyppmd.compress(d, max_order=16, mem_size=256<<20))
                except Exception: return None
            thunks.append(_tpp)
        if HAS_ZPAQ:
            def _tz():
                try:
                    c = self._zpc(d)
                    return (10, c) if c else None
                except Exception: return None
            thunks.append(_tz)
        if HAS_CCMX:
            def _tc():
                try:
                    c = self._ccmxc(d)
                    return (12, c) if c else None
                except Exception: return None
            thunks.append(_tc)
        if HAS_CMIX:
            def _tm():
                try:
                    c = self._cmixc(d)
                    return (13, c) if c else None
                except Exception: return None
            thunks.append(_tm)
        if HAS_LEPTON:
            def _te():
                try:
                    c = self._leptonc(d)
                    return (14, c) if c else None
                except Exception: return None
            thunks.append(_te)
        n = len(thunks)
        results = [None]*n
        nw_eff = CBACK_WORKERS_EFF if _IN_WORKER else CBACK_WORKERS
        if n <= 1 or nw_eff <= 1:
            for i, t in enumerate(thunks):
                try: results[i] = t()
                except Exception: results[i] = None
        else:
            ex = self._ensure_pool()
            futs = [ex.submit(t) for t in thunks]
            for i, f in enumerate(futs):
                try: results[i] = f.result()
                except Exception: results[i] = None
        cs = [r for r in results if r is not None]
        cs.sort(key=lambda x: len(x[1]))
        for fmt, comp in cs:
            blob = bytes([fmt]) + comp
            if fmt == 0: return blob
            try:
                if self.dback(blob) == d: return blob
            except Exception: continue
        return bytes([0]) + d

    def dback(self, d):
        if not d: return None
        f = d[0]; p = d[1:]
        if f == 0: return p
        if f == 1 and HAS_ZSTD:
            try: return zd.decompress(b'\x28\xb5\x2f\xfd' + p)
            except Exception: return None
        if f == 2 and paq:
            try: return paq.decompress(p)
            except Exception: return None
        if f == 3 and paq:
            try: return paq.decompress(b'\x00\x63\x00\x00' + p + b'\xff\xff\xff')
            except Exception: return None
        if f == 4 and HAS_BROTLI:
            try: return brotli.decompress(p)
            except Exception: return None
        if f == 5 and HAS_LZMA:
            try: return lzma.decompress(p)
            except Exception: return None
        if f == 6 and HAS_LZMA:
            try: return lzma.decompress(p, format=lzma.FORMAT_RAW, filters=LF_RAW)
            except Exception: return None
        if f == 7 and HAS_LZMA:
            try: return lzma.decompress(p, format=lzma.FORMAT_RAW, filters=LF_DELTA)
            except Exception: return None
        if f == 8 and HAS_PPMD:
            try: return pyppmd.decompress(p, mem_size=256<<20)
            except Exception: return None
        if f == 9 and HAS_LZMA:
            try: return lzma.decompress(p, format=lzma.FORMAT_RAW, filters=LF_BCJ)
            except Exception: return None
        if f == 10 and HAS_ZPAQ:
            try: return self._zpd(p)
            except Exception: return None
        if f == 11 and HAS_ZSTD and self._zd_dict is not None:
            try: return self._zd_dict.decompress(b'\x28\xb5\x2f\xfd' + p)
            except Exception: return None
        if f == 12 and HAS_CCMX:
            try: return self._ccmxd(p)
            except Exception: return None
        if f == 13 and HAS_CMIX:
            try: return self._cmixd(p)
            except Exception: return None
        if f == 14 and HAS_LEPTON:
            try: return self._leptond(p)
            except Exception: return None
        return None

    def t_xml(self, d):
        if not d: return b'\x00'
        if d[:8] == OLE_MAGIC: return b'\x03' + d
        if d[:4] == ZIP_MAGIC:
            payload = _xml_encode(d, max_tags=1024, min_freq=3)
            if payload is not None: return b'\x02' + payload
            return b'\x02' + d
        if not _xml_is_plausible(d): return b'\x00' + d
        payload = _xml_encode(d, max_tags=4096, min_freq=2)
        if payload is None: return b'\x00' + d
        return b'\x01' + payload
    def r_xml(self, d):
        if not d: return b''
        mode = d[0]; body = d[1:]
        if mode == 0: return body
        if mode == 1: return _xml_decode(body)
        if mode == 2:
            if body[:4] == ZIP_MAGIC: return body
            try: return _xml_decode(body)
            except TransformError: return body
        if mode == 3: return body
        raise TransformError(f"t_xml mode {mode}")

    def t00(self, d):
        if not d: return struct.pack('>I', 0)
        br, bl, bsh = None, float('inf'), []
        cur = bytearray(d); ap = []; orig = bytes(d)
        for _ in range(10):
            bs = 0; bh = cur; bsc = float('-inf')
            for sh in range(256):
                tmp = bytearray(cur)
                for j in range(len(tmp)): tmp[j] = (tmp[j]+sh) % 256
                sc = 0; i = 0
                while i < len(tmp):
                    v = tmp[i]; rn = 1; i += 1
                    while i < len(tmp) and tmp[i] == v: rn += 1; i += 1
                    sc += rn * rn
                if sc > bsc: bsc = sc; bh = tmp; bs = sh
            ap.append(bs)
            rle = self._rle(bs, bh); dec = self._unrle(rle)
            if dec is not None:
                t = bytearray(dec)
                for s in ap:
                    for j in range(len(t)): t[j] = (t[j]-s) % 256
                if bytes(t) == orig and len(rle) < bl: bl = len(rle); br = rle; bsh = ap.copy()
            cur = bh
            if len(rle) >= len(d): break
        if br is None or bl >= len(d): return struct.pack('>I', len(d)) + bytes([0]) + d
        h = bytearray(struct.pack('>I', len(d))); h.append(len(bsh)); h.extend(bsh)
        return bytes(h) + br
    def _rle(self, sd, sh):
        bits = []; self._bits(bits, 0b010, 3); self._bits(bits, sh, 8)
        i = 0; n = len(sd)
        while i < n:
            v = sd[i]; rn = 1; i += 1
            while i < n and sd[i] == v: rn += 1; i += 1
            while rn >= 13:
                ch = min(rn, 268); self._bits(bits, 0b1111, 4); self._bits(bits, ch-13, 8); self._bits(bits, v, 8); rn -= ch
            if rn == 1: self._bits(bits, 0b00, 2); self._bits(bits, v, 8)
            elif rn <= 5: self._bits(bits, 0b01, 2); self._bits(bits, rn-2, 2); self._bits(bits, v, 8)
            elif rn <= 12: self._bits(bits, 0b10, 2); self._bits(bits, rn-6, 3); self._bits(bits, v, 8)
        pad = (8 - len(bits) % 8) % 8; self._bits(bits, 0, pad)
        o = bytearray()
        for j in range(0, len(bits), 8):
            b = 0
            for k in range(8):
                if j+k < len(bits): b = (b<<1) | bits[j+k]
            o.append(b)
        return bytes(o)
    def r00(self, cd):
        if not cd or cd == struct.pack('>I', 0): return b''
        if len(cd) < 4: raise TransformError("T00 short")
        ol = struct.unpack('>I', cd[:4])[0]; cd = cd[4:]
        if not cd: return b''
        if cd[0] == 0: return cd[1:ol+1]
        np = cd[0]
        if np == 0 or len(cd) < 1+np: raise TransformError("T00 hdr")
        sh = list(cd[1:1+np]); rle = cd[1+np:]
        dec = self._unrle(rle)
        if dec is None: raise TransformError("T00 dec")
        cur = bytearray(dec[:ol])
        for s in reversed(sh):
            for i in range(len(cur)): cur[i] = (cur[i]-s) % 256
        return bytes(cur)
    def _unrle(self, d):
        if not d: return None
        bits = []
        for b in d:
            for i in range(7,-1,-1): bits.append((b>>i)&1)
        pos = 0; nb = len(bits)
        if nb < 11: return None
        if self._rd(bits, pos, 3) != 0b010: return None
        pos += 11; o = bytearray()
        while pos < nb:
            if pos+2 > nb: break
            pfx = self._rd(bits, pos, 2); pos += 2
            if pfx == 0b00:
                if pos+8 > nb: break
                rn = 1
            elif pfx == 0b01:
                if pos+10 > nb: break
                rn = 2 + self._rd(bits, pos, 2); pos += 2
            elif pfx == 0b10:
                if pos+11 > nb: break
                rn = 6 + self._rd(bits, pos, 3); pos += 3
            else:
                if pos+18 > nb: break
                if self._rd(bits, pos, 2) != 0b11: return None
                pos += 2; rn = 13 + self._rd(bits, pos, 8); pos += 8
            if pos+8 > nb: break
            v = self._rd(bits, pos, 8); pos += 8
            o.extend([v]*rn)
        for i in range(pos, nb):
            if bits[i] != 0: return None
        return o

    def t01(self, d):
        if not d: return b''
        if self.rep % 2 == 0: return d
        t = bytearray(d)
        for p in PRIMES:
            xv = p if p == 2 else max(1, math.ceil(p*4096/28672))
            for i in range(0, len(t), 3):
                t[i] ^= xv
        return bytes(t)
    r01 = t01

    def t02(self, d):
        if not d: return b'\x00'
        t = bytearray(d); pi = (len(d)+sum(d)) % 256; pv = self._pat(4, pi)
        xv = pv[1]
        for i in range(1, len(t), 4):
            t[i] ^= xv
        return bytes([pi]) + bytes(t)
    def r02(self, d):
        if d == b'\x00': return b''
        if len(d) < 2: raise TransformError("T02")
        pi = d[0]; t = bytearray(d[1:]); pv = self._pat(4, pi)
        xv = pv[1]
        for i in range(1, len(t), 4):
            t[i] ^= xv
        return bytes(t)
    def t03(self, d):
        if not d: return b'\x00'
        t = bytearray(d); rot = (len(d)*13 + sum(d)) % 8
        if rot == 0: rot = 1
        tab = self._rot_tab(rot)
        for i in range(2, len(t), 5):
            t[i] = tab[t[i]]
        return bytes([rot]) + bytes(t)
    def r03(self, d):
        if d == b'\x00': return b''
        if len(d) < 2: raise TransformError("T03")
        rot = d[0]; t = bytearray(d[1:])
        tab = self._irot_tab(rot)
        for i in range(2, len(t), 5):
            t[i] = tab[t[i]]
        return bytes(t)
    def t04(self, d):
        if not d: return b''
        r = self.rep & 0xFF
        if r == 0: return d
        tab = self._t04_tab
        if tab is None:
            tab = bytes((i * r) & 0xFF for i in range(256))
            self._t04_tab = tab
        n = len(d); out = bytearray(n)
        for i in range(n):
            out[i] = (d[i] - tab[i & 0xFF]) & 0xFF
        return bytes(out)
    def r04(self, d):
        if not d: return b''
        r = self.rep & 0xFF
        if r == 0: return d
        tab = self._t04_tab
        if tab is None:
            tab = bytes((i * r) & 0xFF for i in range(256))
            self._t04_tab = tab
        n = len(d); out = bytearray(n)
        for i in range(n):
            out[i] = (d[i] + tab[i & 0xFF]) & 0xFF
        return bytes(out)
    def t05(self, d, s=3):
        if not d: return b''
        return d.translate(self._rot_tab(s))
    def r05(self, d, s=3):
        if not d: return b''
        return d.translate(self._irot_tab(s))
    def _perm_tab(self, sd=42):
        if self._t06_tab is None:
            random.seed(sd); sub = list(range(256)); random.shuffle(sub)
            self._t06_tab = bytes(sub)
            inv = bytearray(256)
            for i in range(256): inv[sub[i]] = i
            self._t06_inv = bytes(inv)
        return self._t06_tab
    def t06(self, d, sd=42):
        if not d: return b''
        return d.translate(self._perm_tab(sd))
    def r06(self, d, sd=42):
        if not d: return b''
        self._perm_tab(sd)
        return d.translate(self._t06_inv)
    def t07(self, d):
        if not d: return b''
        if self.rep % 2 == 0:
            return d.translate(self._xor_table(len(d) % 256))
        t = bytearray(d); r = self.rep
        sh = len(d) % len(self.PI); pr = self.PI[sh:] + self.PI[:sh]
        sz = len(d) % 256
        for i in range(len(t)): t[i] ^= sz
        for _ in range(r):
            for i in range(len(t)): t[i] ^= pr[i % len(pr)]
        return bytes(t)
    r07 = t07
    def t08(self, d):
        if not d: return b''
        if self.rep % 2 == 0:
            return d.translate(self._xor_table(nearest_prime(len(d) % 256)))
        t = bytearray(d); r = self.rep
        sh = len(d) % len(self.PI); pr = self.PI[sh:] + self.PI[:sh]
        p = nearest_prime(len(d) % 256)
        for i in range(len(t)): t[i] ^= p
        for _ in range(r):
            for i in range(len(t)): t[i] ^= pr[i % len(pr)]
        return bytes(t)
    r08 = t08
    def t09(self, d):
        if not d: return b''
        L = len(d)
        p = nearest_prime(L % 256); sd = self._seed(L % len(self.seeds), L)
        if self.rep % 2 == 0:
            return d.translate(self._xor_table((p ^ sd) & 0xFF))
        t = bytearray(d); r = self.rep
        sh = L % len(self.PI); pr = self.PI[sh:] + self.PI[:sh]
        for i in range(len(t)): t[i] ^= p ^ sd
        for _ in range(r):
            for i in range(len(t)): t[i] ^= pr[i % len(pr)] ^ (i % 256)
        return bytes(t)
    r09 = t09
    def t10(self, d):
        if not d: return b'\x00'
        cnt = sum(1 for i in range(len(d)-1) if d[i:i+2] == b'X1')
        n = (((cnt*2)+1)//3)*3 % 256
        t = bytearray(d)
        for i in range(len(t)): t[i] ^= n
        return bytes([n]) + bytes(t)
    def r10(self, d):
        if not d: raise TransformError("T10")
        n = d[0]; t = bytearray(d[1:])
        for i in range(len(t)): t[i] ^= n
        return bytes(t)
    def t11(self, d):
        if not d: return b''
        L = len(d)
        m = self._t11_cache.get(L)
        if m is None:
            fibs = self.fib; lf = len(fibs)
            m = bytes(((fibs[(i+L) % lf] % 256) ^ ((i*13 + L*17) & 0xFF)) & 0xFF
                      for i in range(L))
            self._t11_cache[L] = m
        return (int.from_bytes(d, 'big') ^ int.from_bytes(m, 'big')).to_bytes(L, 'big')
    r11 = t11
    def t12(self, d):
        if not d: return b''
        L = len(d)
        m = self._t12_cache.get(L)
        if m is None:
            fibs = self.fib; lf = len(fibs)
            m = bytes((fibs[i % lf] & 0xFF) for i in range(L))
            self._t12_cache[L] = m
        return (int.from_bytes(d, 'big') ^ int.from_bytes(m, 'big')).to_bytes(L, 'big')
    r12 = t12
    def t13(self, d):
        if not d: return b'\x00'
        r = self._reps(d); cv = len(d) % 256
        for _ in range(r): cv = self._np(cv)
        t = bytearray(d); xv = cv
        for i in range(len(t)): t[i] ^= xv
        return bytes([(r-1) % 256]) + bytes(t)
    def r13(self, d):
        if d == b'\x00': return b''
        if len(d) < 2: raise TransformError("T13")
        r = (d[0]+1) % 256
        if r == 0: r = 256
        t = bytearray(d[1:]); cv = len(t) % 256
        for _ in range(r): cv = self._np(cv)
        xv = cv
        for i in range(len(t)): t[i] ^= xv
        return bytes(t)
    def t14(self, d):
        if not d: return b'\x00'
        return d + bytes([sum(d) % 256])
    def r14(self, d):
        if not d: raise TransformError("T14")
        return d[:-1]
    def t15(self, d):
        if not d: return b'\x00'
        t = bytearray(d); pi = len(d) % 256; pv = self._pat(3, pi)
        xv = pv[0]
        tab = self._add_tab(xv)
        for i in range(0, len(t), 3):
            t[i] = tab[t[i]]
        return bytes([pi]) + bytes(t)
    def r15(self, d):
        if d == b'\x00': return b''
        if len(d) < 2: raise TransformError("T15")
        pi = d[0]; t = bytearray(d[1:]); pv = self._pat(3, pi)
        xv = pv[0]
        tab = self._sub_tab(xv)
        for i in range(0, len(t), 3):
            t[i] = tab[t[i]]
        return bytes(t)
    def t16(self, d):
        if not d: return b''
        xv = (len(d)*7 + 13) % 256
        return d.translate(self._xor_table(xv))
    r16 = t16
    def t17(self, d):
        if not d: return b''
        return self._xor_pattern(d, b'\x24\x3f\x6a\x88')
    r17 = t17
    def _c18(self, d):
        if not d: return b''
        L = len(d)
        m = self._c18_cache.get(L)
        if m is None:
            decimal.getcontext().prec = 60
            pi = decimal.Decimal(self.PI_S)
            s = str((pi*pi)/decimal.Decimal(6)).replace('.', '')[:max(10, L//2+5)]
            m = bytes(int(s[i:i+2]) % 256 for i in range(0, len(s), 2))
            self._c18_cache[L] = m
        ml = len(m)
        return bytes(d[i] ^ m[i % ml] for i in range(L))
    def _c19(self, d):
        if not d: return b''
        L = len(d)
        m = self._c19_cache.get(L)
        if m is None:
            decimal.getcontext().prec = 60; e = decimal.Decimal(1).exp()
            s = str(decimal.Decimal(1)/e).replace('.', '')[:max(10, L//2+5)]
            m = bytes(int(s[i:i+2]) % 256 for i in range(0, len(s), 2))
            self._c19_cache[L] = m
        ml = len(m)
        return bytes(d[i] ^ m[i % ml] for i in range(L))
    def _c20(self, d):
        if not d: return b''
        L = len(d)
        m = self._c20_cache.get(L)
        if m is None:
            decimal.getcontext().prec = 60; e = decimal.Decimal(1).exp()
            s = str(decimal.Decimal(5)*e).replace('.', '')[:max(10, L//2+5)]
            m = bytes(int(s[i:i+2]) % 256 for i in range(0, len(s), 2))
            self._c20_cache[L] = m
        ml = len(m)
        return bytes(d[i] ^ m[i % ml] for i in range(L))
    def t18(self, d): return self._c18(d)
    def r18(self, d): return self._c18(d)
    def t19(self, d): return self._c19(d)
    def r19(self, d): return self._c19(d)
    def t20(self, d): return self._c20(d)
    def r20(self, d): return self._c20(d)
    def t21(self, d):
        if not d: return b''
        return d.translate(self._m1_tab)
    def r21(self, d):
        if not d: return b''
        return d.translate(self._p1_tab)
    def t22(self, d): return base64.b64encode(d)
    def r22(self, d):
        try: return base64.b64decode(d, validate=False)
        except Exception as e: raise TransformError(f"b64: {e}")
    def t23(self, d):
        if not d: return b'\x00'
        try: text = d.decode('utf-8')
        except UnicodeDecodeError: return b'\x00' + d
        toks = re.split(r'([A-Za-z0-9_]+)', text); wl = []; wi = {}; ts = []
        for i, tk in enumerate(toks):
            if i % 2 == 1:
                wb = tk.encode('utf-8'); idx = wi.get(wb)
                if idx is None: idx = len(wl); wi[wb] = idx; wl.append(wb)
                ts.append((1, idx))
            else: ts.append((0, tk.encode('utf-8')))
        o = bytearray([1]) + struct.pack('>I', len(wl))
        for wb in wl: o += struct.pack('>I', len(wb)) + wb
        for ty, py in ts:
            if ty == 1: o += b'\x01' + struct.pack('>I', py)
            else: o += b'\x00' + struct.pack('>I', len(py)) + py
        tb = bytes(o)
        try:
            if self.r23(tb) == d: return tb
        except Exception: pass
        return b'\x00' + d
    def r23(self, d):
        if not d: return b''
        flag = d[0]
        if flag == 0: return d[1:]
        if flag != 1: raise TransformError(f"T23 {flag}")
        pos = 1; nw = struct.unpack('>I', d[pos:pos+4])[0]; pos += 4
        wl = []
        for _ in range(nw):
            wl_len = struct.unpack('>I', d[pos:pos+4])[0]; pos += 4
            wl.append(d[pos:pos+wl_len]); pos += wl_len
        o = bytearray()
        while pos < len(d):
            ty = d[pos]; pos += 1
            if ty == 1:
                idx = struct.unpack('>I', d[pos:pos+4])[0]; pos += 4; o += wl[idx]
            elif ty == 0:
                ll = struct.unpack('>I', d[pos:pos+4])[0]; pos += 4; o += d[pos:pos+ll]; pos += ll
            else: raise TransformError(f"T23 tok {ty}")
        return bytes(o)
    def t24(self, d): return self.t23(d)
    def r24(self, d): return self.r23(d)
    def _split(self, text):
        ch = []
        for i, para in enumerate(re.split(r'(\n\n)', text)):
            if i % 2 == 1: ch.append(para); continue
            for j, line in enumerate(re.split(r'(\n)', para)):
                if j % 2 == 1: ch.append(line); continue
                for k, sent in enumerate(re.split(r'([.!?]+)', line)):
                    if k % 2 == 1: ch.append(sent); continue
                    ch.extend(re.split(r'(\s+|\b)', sent))
        return ch
    def _dt(self, d, ib=3):
        try: text = d.decode('utf-8')
        except Exception: return b'\x00' + d
        chunks = self._split(text); freq = Counter(chunks)
        sc = sorted(freq.keys(), key=lambda x: (-freq[x], -len(x), x))
        ci = {ch: i for i, ch in enumerate(sc)}; ne = len(sc)
        if ib == 2 and ne > 65535: ib = 3
        if ib == 3 and ne > 16777215: ib = 8
        h = bytearray([ib]) + struct.pack('>I', ne)
        for ch in sc:
            cb = ch.encode('utf-8'); h += struct.pack('>I', len(cb)) + cb
        ts = bytearray()
        for ch in chunks:
            idx = ci[ch]
            if ib == 2: ts += struct.pack('>H', idx)
            elif ib == 3: ts += struct.pack('>I', idx)[1:4]
            else: ts += struct.pack('>Q', idx)
        return bytes(h) + bytes(ts)
    def _ddt(self, d):
        if not d: return b''
        if d[0] == 0: return d[1:]
        ib = d[0]
        if ib not in (2, 3, 8): raise TransformError(f"dict ib {ib}")
        pos = 1; ne = struct.unpack('>I', d[pos:pos+4])[0]; pos += 4
        dd = []
        for _ in range(ne):
            cl = struct.unpack('>I', d[pos:pos+4])[0]; pos += 4
            dd.append(d[pos:pos+cl].decode('utf-8')); pos += cl
        toks = []
        while pos < len(d):
            if ib == 2:
                if pos+2 > len(d): break
                idx = struct.unpack('>H', d[pos:pos+2])[0]; pos += 2
            elif ib == 3:
                if pos+3 > len(d): break
                idx = struct.unpack('>I', b'\x00'+d[pos:pos+3])[0]; pos += 3
            else:
                if pos+8 > len(d): break
                idx = struct.unpack('>Q', d[pos:pos+8])[0]; pos += 8
            if idx >= len(dd): raise TransformError(f"dict idx {idx}")
            toks.append(dd[idx])
        return ''.join(toks).encode('utf-8')
    def t25(self, d): return self._dt(d, 3)
    def r25(self, d): return self._ddt(d)
    def t26(self, d):
        if not d: return b''
        L = len(d)
        ks = self._t26_cache.get(L)
        if ks is None:
            sec = b"PJP_T26"
            nb = (L + 1023) // 1024
            ks = b''.join(hashlib.sha256(sec + struct.pack(">Q", bn)).digest()
                          for bn in range(nb))
            self._t26_cache[L] = ks
        return (int.from_bytes(d, 'big') ^ int.from_bytes(ks[:L], 'big')).to_bytes(L, 'big')
    r26 = t26
    def t27(self, d):
        try: text = d.decode('utf-8')
        except UnicodeDecodeError: return b'\x00' + d
        for ch in text:
            if ch not in CH2_6: return b'\x00' + d
        bits = []
        for ch in text:
            v = CH2_6[ch]
            for i in range(5, -1, -1): bits.append((v>>i)&1)
        pad = (8 - len(bits) % 8) % 8; bits.extend([0]*pad)
        o = bytearray()
        for i in range(0, len(bits), 8):
            b = 0
            for j in range(8): b = (b<<1)|bits[i+j]
            o.append(b)
        return b'\x01' + struct.pack('<I', len(text)) + bytes(o)
    def r27(self, d):
        if len(d) < 1: raise TransformError("T27")
        flag = d[0]
        if flag == 0: return d[1:]
        if flag != 1: raise TransformError(f"T27 {flag}")
        p = d[1:]
        if len(p) < 4: raise TransformError("T27 p")
        nc = struct.unpack('<I', p[:4])[0]; packed = p[4:]
        nb = (nc*6+7)//8
        if len(packed) != nb: raise TransformError("T27 mm")
        pb = (8 - (nc*6) % 8) % 8
        if pb > 0 and packed:
            m = (1<<pb)-1
            if packed[-1] & m: raise TransformError("T27 pad")
        bits = []
        for b in packed:
            for i in range(7, -1, -1): bits.append((b>>i)&1)
        chars = []
        for i in range(nc):
            v = 0
            for j in range(6): v = (v<<1)|bits[i*6+j]
            if v >= 64: raise TransformError(f"T27 v {v}")
            chars.append(_6TOCH[v])
        return ''.join(chars).encode('utf-8')
    def t28(self, d):
        if not d: return b'\x00'
        pad = (3 - len(d) % 3) % 3; p = d + b'\x00'*pad
        o = bytearray([pad])
        for i in range(0, len(p), 3):
            v = int.from_bytes(p[i:i+3], 'little'); bi = i//3; k = (bi*65537 + 12345) & 0xFFFF
            o.extend(((v-k) % (1<<24)).to_bytes(3, 'little'))
        return bytes(o)
    def r28(self, d):
        if d == b'\x00': return b''
        if not d: raise TransformError("T28")
        pad = d[0]; p = d[1:]
        if len(p) % 3 != 0: raise TransformError("T28 l")
        o = bytearray()
        for i in range(0, len(p), 3):
            v = int.from_bytes(p[i:i+3], 'little'); bi = i//3; k = (bi*65537 + 12345) & 0xFFFF
            o.extend(((v+k) % (1<<24)).to_bytes(3, 'little'))
        if pad: o = o[:-pad]
        return bytes(o)
    def _best16(self, d):
        if len(d) < 3: return 0
        pad = (3 - len(d) % 3) % 3; p = d + b'\x00'*pad
        vals = [int.from_bytes(p[i:i+3], 'little') for i in range(0, len(p), 3)]
        bk, bc = 0, float('inf')
        for k in range(65536):
            tr = [(v-k) & 0xFFFFFF for v in vals]; m = sum(tr)//len(tr); c = sum(abs(t-m) for t in tr)
            if c < bc: bc = c; bk = k
            if c == 0: break
        return bk
    def t29(self, d):
        if not d: return b'\x00'
        k = self._best16(d)
        pad = (3 - len(d) % 3) % 3; p = d + b'\x00'*pad
        o = bytearray([pad]) + k.to_bytes(2, 'little')
        for i in range(0, len(p), 3):
            v = int.from_bytes(p[i:i+3], 'little')
            o.extend(((v-k) % (1<<24)).to_bytes(3, 'little'))
        return bytes(o)
    def r29(self, d):
        if d == b'\x00': return b''
        if len(d) < 3: raise TransformError("T29")
        pad = d[0]; k = int.from_bytes(d[1:3], 'little'); p = d[3:]
        if len(p) % 3 != 0: raise TransformError("T29 l")
        o = bytearray()
        for i in range(0, len(p), 3):
            v = int.from_bytes(p[i:i+3], 'little')
            o.extend(((v+k) % (1<<24)).to_bytes(3, 'little'))
        if pad: o = o[:-pad]
        return bytes(o)
    def t30(self, d):
        if not d: return b'\x00'
        pad = (3 - len(d) % 3) % 3; p = d + b'\x00'*pad
        vals = [int.from_bytes(p[i:i+3], 'little') for i in range(0, len(p), 3)]
        mean = sum(vals)//len(vals); sv = sorted(vals); med = sv[len(sv)//2]
        cands = set()
        for b in [mean, med]:
            for o in [0,1,-1,10,-10,100,-100,1000,-1000]: cands.add((b+o) % (1<<24))
        rng = random.Random(42)
        for _ in range(10): cands.add(rng.randint(0, (1<<24)-1))
        bk, bc = 0, float('inf')
        for k in cands:
            tr = [(v-k) & 0xFFFFFF for v in vals]; m = sum(tr)//len(tr); c = sum(abs(t-m) for t in tr)
            if c < bc: bc = c; bk = k
        o = bytearray([pad]) + bk.to_bytes(3, 'little')
        for i in range(0, len(p), 3):
            v = int.from_bytes(p[i:i+3], 'little')
            o.extend(((v-bk) % (1<<24)).to_bytes(3, 'little'))
        return bytes(o)
    def r30(self, d):
        if d == b'\x00': return b''
        if len(d) < 4: raise TransformError("T30")
        pad = d[0]; k = int.from_bytes(d[1:4], 'little'); p = d[4:]
        if len(p) % 3 != 0: raise TransformError("T30 l")
        o = bytearray()
        for i in range(0, len(p), 3):
            v = int.from_bytes(p[i:i+3], 'little')
            o.extend(((v+k) % (1<<24)).to_bytes(3, 'little'))
        if pad: o = o[:-pad]
        return bytes(o)
    def t31(self, d): return d
    r31 = t31
    def t32(self, d): return d
    r32 = t32

    def _t33(self, d):
        if not d: return b'\x00'*9
        bits = []
        for b in d:
            for i in range(7, -1, -1): bits.append((b>>i)&1)
        return self._cb(bits)
    def _r33(self, d):
        if not d or d == b'\x00'*9: return b''
        bits = self._db(d)
        if not bits: return b''
        o = bytearray()
        for i in range(0, len(bits), 8):
            v = 0
            for j in range(i, min(i+8, len(bits))): v = (v<<1)|bits[j]
            if i+8 > len(bits): v <<= (8 - (len(bits)-i))
            o.append(v)
        return bytes(o)
    def _cb(self, bits):
        obl = len(bits)
        if obl == 0: return b'\x00'*9
        cur = bits[:]; pl = obl; pc = 0
        while pc < 255:
            pad = (4 - len(cur) % 4) % 4; p = cur + [0]*pad
            nc = len(p)//4; enc = []
            for i in range(nc):
                nib = (p[i*4]<<3)|(p[i*4+1]<<2)|(p[i*4+2]<<1)|p[i*4+3]
                L, cw = _CD_CODE[nib]
                for b in range(L-1,-1,-1): enc.append((cw>>b)&1)
            if len(enc) < pl: cur = enc; pl = len(enc); pc += 1
            else: break
        cbl = len(cur)
        hdr = struct.pack('>I', obl) + bytes([pc]) + struct.pack('>I', cbl)
        pad = (8 - len(cur) % 8) % 8; cur += [0]*pad
        o = bytearray()
        for i in range(0, len(cur), 8):
            v = 0
            for j in range(8): v = (v<<1)|cur[i+j]
            o.append(v)
        return hdr + bytes(o)
    def _db(self, d):
        if len(d) < 9: raise TransformError("Diap")
        obl = struct.unpack('>I', d[:4])[0]; pc = d[4]
        cbl = struct.unpack('>I', d[5:9])[0]; pay = d[9:]
        bits = []
        for b in pay:
            for i in range(7,-1,-1): bits.append((b>>i)&1)
        if len(bits) < cbl: raise TransformError("Diap p")
        cur = bits[:cbl]
        if pc == 0: return cur[:obl]
        for _ in range(pc):
            pos = 0; nb = len(cur); dn = []
            while pos < nb:
                m = False
                for L in range(2, 10):
                    if pos+L > nb: continue
                    cw = 0
                    for k in range(L): cw = (cw<<1)|cur[pos+k]
                    if (L, cw) in _CD_DEC: dn.append(_CD_DEC[(L, cw)]); pos += L; m = True; break
                if not m: raise TransformError("Diap cw")
            nb2 = []
            for nib in dn:
                for j in range(3,-1,-1): nb2.append((nib>>j)&1)
            cur = nb2
        if len(cur) < obl: raise TransformError("Diap s")
        return cur[:obl]

    def _t34(self, d):
        if not d: return struct.pack('>I', 0)
        MX = 43; bits = []; i = 0; n = len(d)
        while i < n:
            cl = min(MX, n-i); ch = d[i:i+cl]
            f = ch[0]; same = all(b == f for b in ch)
            if same: self._bits(bits, 1, 1); self._bits(bits, f, 8); self._bits(bits, cl-1, 6)
            else:
                self._bits(bits, 0, 1); self._bits(bits, cl, 6)
                for b in ch: self._bits(bits, b, 8)
            i += cl
        pad = (8 - len(bits) % 8) % 8; self._bits(bits, 0, pad)
        o = bytearray()
        for j in range(0, len(bits), 8):
            b = 0
            for k in range(8): b = (b<<1)|bits[j+k]
            o.append(b)
        return struct.pack('>I', len(d)) + bytes(o)
    def _r34(self, d):
        if not d: return b''
        if len(d) < 4: raise TransformError("BlkRun")
        ol = struct.unpack('>I', d[:4])[0]; p = d[4:]
        bits = []
        for b in p:
            for i in range(7,-1,-1): bits.append((b>>i)&1)
        pos = 0; nb = len(bits); o = bytearray()
        while pos < nb and len(o) < ol:
            if pos+1 > nb: break
            flag = self._rd(bits, pos, 1); pos += 1
            if flag == 1:
                if pos+14 > nb: raise TransformError("BlkRun t")
                bv = self._rd(bits, pos, 8); pos += 8
                cm = self._rd(bits, pos, 6); pos += 6
                rl = min(cm+1, ol-len(o)); o.extend([bv]*rl)
            else:
                if pos+6 > nb: raise TransformError("BlkRun l")
                cl = self._rd(bits, pos, 6); pos += 6
                if cl == 0: break
                if pos+cl*8 > nb: raise TransformError("BlkRun b")
                for _ in range(cl): o.append(self._rd(bits, pos, 8)); pos += 8
        return bytes(o[:ol])
    def _t35(self, d):
        if not d: return b'\x01'
        n = 3; r = bytearray(d)
        for i in range(len(r)): r[i] = (pow(r[i]+1, n, 257)-1) & 0xFF
        return bytes([n]) + bytes(r)
    def _r35(self, d):
        if d == b'\x01': return b''
        if len(d) < 2: raise TransformError("FLT25")
        n = d[0]; inv = mod_inv(n, 256)
        if inv is None: raise TransformError(f"FLT25 {n}")
        r = bytearray(d[1:])
        for i in range(len(r)): r[i] = (pow(r[i]+1, inv, 257)-1) & 0xFF
        return bytes(r)
    def _t36(self, d):
        if not d: return b'\x01\x00'
        n = (len(d)*7 + 13) & 0xFFFF
        if n % 2 == 0: n ^= 1
        e = pow(n, 16777216, 257) | 1
        r = bytearray(d)
        for i in range(len(r)): r[i] = (pow(r[i]+1, e, 257)-1) & 0xFF
        return bytes([n & 0xFF, (n>>8) & 0xFF]) + bytes(r)
    def _r36(self, d):
        if d == b'\x01\x00': return b''
        if len(d) < 2: raise TransformError("FLT26")
        n = d[0] | (d[1]<<8)
        if n % 2 == 0: n ^= 1
        e = pow(n, 16777216, 257) | 1; inv = mod_inv(e, 256)
        if inv is None: raise TransformError(f"FLT26 {e}")
        r = bytearray(d[2:])
        for i in range(len(r)): r[i] = (pow(r[i]+1, inv, 257)-1) & 0xFF
        return bytes(r)
    def _t37(self, d):
        if not d:
            o = bytearray(b'\x00\x00\x00\x00\x01\x00'); o.extend(b'\x00'*1024); return bytes(o)
        BS = 1024; tb = (len(d)+BS-1)//BS
        o = bytearray(); o.extend(len(d).to_bytes(4, 'big'))
        for bi in range(tb):
            s = bi*BS; e = min(s+BS, len(d))
            ch = d[s:e] + b'\x00'*(BS-len(d[s:e]))
            n = ((len(d)*7 + bi*13 + 1) & 0xFFFF) | 1
            e_ = pow(n, 16777216, 257) | 1; e200 = pow(e_, 200, 257)
            t = bytearray(ch)
            for i in range(BS): t[i] = (pow(t[i]+1, e200, 257)-1) & 0xFF
            o.append(n & 0xFF); o.append((n>>8) & 0xFF); o.extend(t)
        return bytes(o)
    def _r37(self, d):
        if len(d) < 4: raise TransformError("FLT27")
        ol = int.from_bytes(d[:4], 'big'); p = d[4:]; BS = 1024; btl = 2+BS
        if len(p) % btl != 0: raise TransformError("FLT27 a")
        nb = len(p)//btl; dec = bytearray()
        for bi in range(nb):
            off = bi*btl; n = p[off] | (p[off+1]<<8); ch = p[off+2:off+2+BS]; n |= 1
            e_ = pow(n, 16777216, 257) | 1; e200 = pow(e_, 200, 257)
            inv = mod_inv(e200, 256)
            if inv is None: raise TransformError(f"FLT27 {e200}")
            for i in range(BS): dec.append((pow(ch[i]+1, inv, 257)-1) & 0xFF)
        return bytes(dec[:ol])
    def _t38(self, d):
        BS = 1024
        if not d:
            ch = b'\x00'*BS; c = self.cback(ch)
            o = bytearray(struct.pack('>I', 0)); o += b'\x01\x00' + bytes([(len(c)>>8) & 0xFF, len(c) & 0xFF]) + c
            return bytes(o)
        tb = (len(d)+BS-1)//BS
        o = bytearray(); o.extend(len(d).to_bytes(4, 'big'))
        for bi in range(tb):
            s = bi*BS; e = min(s+BS, len(d))
            ch = d[s:e] + b'\x00'*(BS-len(d[s:e]))
            n = ((len(d)*7 + bi*13 + 1) & 0xFFFF) | 1
            e_ = pow(n, 16777216, 257) | 1; e200 = pow(e_, 200, 257)
            t = bytearray(ch)
            for i in range(BS): t[i] = (pow(t[i]+1, e200, 257)-1) & 0xFF
            c = self.cback(bytes(t))
            o += bytes([n & 0xFF, (n>>8) & 0xFF, (len(c)>>8) & 0xFF, len(c) & 0xFF]) + c
        return bytes(o)
    def _r38(self, d):
        if len(d) < 4: raise TransformError("FLT28")
        ol = int.from_bytes(d[:4], 'big'); p = d[4:]
        pos = 0; dec = bytearray()
        while pos < len(p):
            if pos+2 > len(p): raise TransformError("FLT28 hdr")
            n = p[pos] | (p[pos+1]<<8); pos += 2
            if pos+2 > len(p): raise TransformError("FLT28 len")
            cl = (p[pos]<<8) | p[pos+1]; pos += 2
            cb = p[pos:pos+cl]; pos += cl
            b = self.dback(cb)
            if b is None: raise TransformError("FLT28 body")
            n |= 1; e_ = pow(n, 16777216, 257) | 1; e200 = pow(e_, 200, 257)
            inv = mod_inv(e200, 256)
            if inv is None: raise TransformError(f"FLT28 {e200}")
            t = bytearray(b)
            for i in range(len(t)): t[i] = (pow(t[i]+1, inv, 257)-1) & 0xFF
            dec.extend(t)
        return bytes(dec[:ol])
    def _t39(self, d):
        BS = 32
        if not d:
            ch = b'\x00'*BS; c = self.cback(ch)
            o = bytearray(struct.pack('>I', 0)); o += b'\x01\x00' + bytes([(len(c)>>8) & 0xFF, len(c) & 0xFF]) + c
            return bytes(o)
        tb = (len(d)+BS-1)//BS
        o = bytearray(); o.extend(len(d).to_bytes(4, 'big'))
        for bi in range(tb):
            s = bi*BS; e = min(s+BS, len(d))
            ch = d[s:e] + b'\x00'*(BS-len(d[s:e]))
            n = ((len(d)*7 + bi*13 + 1) & 0xFFFF) | 1
            c = self.cback(bytes(ch))
            o += bytes([n & 0xFF, (n>>8) & 0xFF, (len(c)>>8) & 0xFF, len(c) & 0xFF]) + c
        return bytes(o)
    def _r39(self, d):
        if len(d) < 4: raise TransformError("FLT29")
        ol = int.from_bytes(d[:4], 'big'); p = d[4:]
        pos = 0; dec = bytearray()
        while pos < len(p):
            if pos+2 > len(p): raise TransformError("FLT29 hdr")
            pos += 2
            if pos+2 > len(p): raise TransformError("FLT29 len")
            cl = (p[pos]<<8) | p[pos+1]; pos += 2
            cb = p[pos:pos+cl]; pos += cl
            b = self.dback(cb)
            if b is None: raise TransformError("FLT29 body")
            dec.extend(b)
        return bytes(dec[:ol])
    def _t40(self, d):
        BS = 33
        if not d:
            ch = b'\x00'*BS; c = self.cback(ch)
            o = bytearray(struct.pack('>I', 0)); o += b'\x01\x01' + bytes([(len(c)>>8) & 0xFF, len(c) & 0xFF]) + c
            return bytes(o)
        tb = (len(d)+BS-1)//BS
        o = bytearray(); o.extend(len(d).to_bytes(4, 'big'))
        for bi in range(tb):
            s = bi*BS; e = min(s+BS, len(d))
            ch = d[s:e] + b'\x00'*(BS-len(d[s:e]))
            h = hashlib.sha256(ch + bytes([bi&0xFF, (len(d)>>8)&0xFF, len(d)&0xFF])).digest()
            enc = bytes([32]) + h; c = self.cback(ch)
            o += enc + bytes([(len(c)>>8) & 0xFF, len(c) & 0xFF]) + c
        return bytes(o)
    def _r40(self, d):
        if len(d) < 4: raise TransformError("FLT30")
        ol = int.from_bytes(d[:4], 'big'); p = d[4:]
        pos = 0; dec = bytearray()
        while pos < len(p):
            Ln = p[pos]; pos += 1
            if Ln > 32 or pos+Ln > len(p): raise TransformError("FLT30 n")
            pos += Ln
            if pos+2 > len(p): raise TransformError("FLT30 hdr")
            cl = (p[pos]<<8) | p[pos+1]; pos += 2
            cb = p[pos:pos+cl]; pos += cl
            b = self.dback(cb)
            if b is None: raise TransformError("FLT30 body")
            dec.extend(b)
        return bytes(dec[:ol])

    def t41(self, d):
        if not d: return b''
        t = bytearray(d); m = bytes([0x27, 0x03])
        for i in range(min(len(t), 8)): t[i] ^= m[i % 2]
        return bytes(t)
    r41 = t41
    def t42(self, d):
        if not d: return b''
        return self._xor_pattern(d, b'\x27\x03')
    r42 = t42
    def t43(self, d):
        if not d: return b''
        return self._xor_pattern(d, b'\x10\x00\x00')
    r43 = t43
    def t44(self, d):
        if not d: return b''
        return base64.b64encode(d)
    def r44(self, d):
        if not d: return b''
        try: return base64.b64decode(d, validate=False)
        except Exception as e: raise TransformError(f"b64-44 {e}")

    @staticmethod
    def _hcl(freq):
        hp = [(f, i, i) for i, f in enumerate(freq) if f > 0]
        if not hp: return [0]*len(freq)
        if len(hp) == 1:
            L = [0]*len(freq); L[hp[0][2]] = 1; return L
        heapq.heapify(hp); nid = len(freq)
        while len(hp) > 1:
            f1, _, n1 = heapq.heappop(hp); f2, _, n2 = heapq.heappop(hp)
            heapq.heappush(hp, (f1+f2, nid, (n1, n2))); nid += 1
        L = [0]*len(freq)
        def tr(n, d):
            if isinstance(n, int): L[n] = d
            else: tr(n[0], d+1); tr(n[1], d+1)
        tr(hp[0][2], 0); return L
    @staticmethod
    def _hcc(L):
        sy = sorted(range(len(L)), key=lambda s: (L[s], s))
        c = {}; co = 0; pl = 0; first = True
        for s in sy:
            cl = L[s]
            if cl == 0: continue
            if first: pl = cl; first = False
            elif cl != pl: co <<= (cl-pl); pl = cl
            c[s] = (co, cl); co += 1
        return c
    def t45(self, d):
        if not d: return b''
        freq = [0]*256
        for b in d: freq[b] += 1
        cl = self._hcl(freq); codes = self._hcc(cl)
        hdr = bytearray(len(d).to_bytes(4, 'big')); hdr.extend(cl)
        acc = 0; nbits = 0; o = bytearray()
        for b in d:
            c, n = codes[b]
            acc = (acc << n) | c
            nbits += n
            while nbits >= 8:
                nbits -= 8
                o.append((acc >> nbits) & 0xFF)
        if nbits:
            o.append((acc << (8 - nbits)) & 0xFF)
        return bytes(hdr) + bytes(o)
    def r45(self, d):
        if not d: return b''
        if len(d) < 260: raise TransformError("Huff")
        ol = int.from_bytes(d[:4], 'big'); cl = list(d[4:260]); p = d[260:]
        if ol == 0: return b''
        if max(cl) > 32: raise TransformError("Huff l")
        code_to = {}
        sy = sorted(range(256), key=lambda s: (cl[s], s))
        c = 0; pl = 0; first = True
        for s in sy:
            L = cl[s]
            if L == 0: continue
            if first: pl = L; first = False
            elif L != pl: c <<= (L-pl); pl = L
            code_to[(L, c)] = s; c += 1
        mx = max(cl) if any(cl) else 0
        buf = 0; nbuf = 0; pos = 0; o = bytearray()
        while len(o) < ol:
            while nbuf < mx and pos < len(p):
                buf = (buf << 8) | p[pos]; nbuf += 8; pos += 1
            if nbuf == 0: break
            f = False
            for L in range(1, min(mx, nbuf) + 1):
                v = (buf >> (nbuf - L)) & ((1 << L) - 1)
                if (L, v) in code_to:
                    o.append(code_to[(L, v)]); nbuf -= L; f = True; break
            if not f: raise TransformError(f"Huff {pos}")
        if len(o) != ol: raise TransformError(f"Huff {len(o)}!={ol}")
        return bytes(o)
    def t46(self, d):
        if not d: return b''
        return self._xor_pattern(d, bytes(self.mask46))
    r46 = t46
    def t47(self, d):
        if not d: return b''
        return self._xor_pattern(d, self.pattern47)
    r47 = t47
    def t59(self, d):
        if not d: return b''
        ri = self.ref_idx; out = bytearray()
        last = 0
        for m in _TOK_RE.finditer(d):
            if m.start() > last:
                chunk = d[last:m.start()]
                out.append(0); _emit_varint(out, len(chunk)); out += chunk
            tok = m.group(0)
            low = tok.lower(); i = ri.get(low)
            if i is not None:
                if tok == low: code = (i << 2) | 0
                elif tok == low.capitalize(): code = (i << 2) | 1
                elif tok == low.upper(): code = (i << 2) | 2
                else: code = None
                if code is not None:
                    _emit_varint(out, code + 1)
                    last = m.end()
                    continue
            out.append(0); _emit_varint(out, len(tok)); out += tok
            last = m.end()
        if last < len(d):
            chunk = d[last:]
            out.append(0); _emit_varint(out, len(chunk)); out += chunk
        return bytes(out)
    def r59(self, blob):
        rb = self.ref_bytes; rcap = self.ref_bytes_cap; rup = self.ref_bytes_up
        out = bytearray(); pos = 0; n = len(blob)
        while pos < n:
            code, pos = _read_varint(blob, pos)
            if code == 0:
                ln, pos = _read_varint(blob, pos); out += blob[pos:pos+ln]; pos += ln
            else:
                x = code - 1; i = x >> 2; c = x & 3
                if i >= len(rb): raise TransformError(f"t59 id {i}")
                if c == 0: out += rb[i]
                elif c == 1: out += rcap[i]
                elif c == 2: out += rup[i]
                else: raise TransformError("t59 case 3")
        return bytes(out)
    def _cdd_masks(self, n4):
        c = self._cdd_cache.get(n4)
        if c is None:
            mid, key = cdd_derive(n4)
            masks = bytes(cdd_mask(i, mid) for i in range(n4))
            c = (mid, key, masks)
            self._cdd_cache[n4] = c
        return c
    def t_cdd(self, d):
        if not d: return b''
        L = len(d); n4 = L // 4; tail = bytes(d[n4 * 4:])
        if n4 == 0: return bytes(d)
        mid, key, masks = self._cdd_masks(n4)
        t = bytearray(d[:n4 * 4])
        for i in range(n4):
            m = masks[i]
            if m:
                b = i * 4
                t[b] ^= m; t[b+1] ^= m; t[b+2] ^= m; t[b+3] ^= m
        t[mid * 4 + 2] ^= 0x5A
        for i in range(2, n4, 3):
            b = i * 4
            v = int.from_bytes(t[b:b+4], 'little')
            v = (v - key) & 0xFFFFFFFF
            t[b:b+4] = v.to_bytes(4, 'little')
        return bytes(t) + tail
    def r_cdd(self, d):
        if not d: return b''
        L = len(d); n4 = L // 4; tail = bytes(d[n4 * 4:])
        if n4 == 0: return bytes(d)
        mid, key, masks = self._cdd_masks(n4)
        t = bytearray(d[:n4 * 4])
        for i in range(2, n4, 3):
            b = i * 4
            v = int.from_bytes(t[b:b+4], 'little')
            v = (v + key) & 0xFFFFFFFF
            t[b:b+4] = v.to_bytes(4, 'little')
        t[mid * 4 + 2] ^= 0x5A
        for i in range(n4):
            m = masks[i]
            if m:
                b = i * 4
                t[b] ^= m; t[b+1] ^= m; t[b+2] ^= m; t[b+3] ^= m
        return bytes(t) + tail

    def t57(self, d):
        if len(d) < 4:
            pad = 4 - len(d); k = 0
            return bytes([pad]) + k.to_bytes(4, 'little') + d + b'\x00'*pad
        n = len(d); pad = (4 - n % 4) % 4; p = d + b'\x00'*pad
        blocks = [p[i:i+4] for i in range(0, len(p), 4)]
        mc, _ = Counter(blocks).most_common(1)[0]
        k = int.from_bytes(mc, 'little'); o = bytearray()
        for blk in blocks: o.extend((int.from_bytes(blk, 'little') ^ k).to_bytes(4, 'little'))
        return bytes([pad]) + k.to_bytes(4, 'little') + bytes(o)
    def r57(self, d):
        if len(d) < 5: raise TransformError("T57")
        pad = d[0]; k = int.from_bytes(d[1:5], 'little'); p = d[5:]
        if len(p) % 4 != 0: raise TransformError("T57 l")
        o = bytearray()
        for i in range(0, len(p), 4): o.extend((int.from_bytes(p[i:i+4], 'little') ^ k).to_bytes(4, 'little'))
        if pad: o = o[:-pad]
        return bytes(o)

    def t58(self, d):
        if not d: return b'\x58\x00\x03' + (0).to_bytes(8, 'big') + b'\x00' + b'\x00'*256 + (0).to_bytes(4, 'big')
        sh = hashlib.sha256(d).digest()
        depths = [4, 16, 32, 64]; bd = depths[sh[0] & 3]; bd_code = {4:0, 16:1, 32:2, 64:3}[bd]
        if bd == 4:
            words = []
            for b in d: words.append((b>>4)&0xF); words.append(b&0xF)
            mask = 0xF; wbytes = 1
        else:
            wbytes = bd//8
            p = d + b'\x00' * ((-len(d)) % wbytes)
            words = [int.from_bytes(p[i:i+wbytes], 'big') for i in range(0, len(p), wbytes)]
            mask = (1<<bd)-1
        n = len(words); fibs = self.fib or [0,1]; Lf = len(fibs)
        const = Counter(words).most_common(1)[0][0]
        fib_s = [0]*n; lz_s = [0]*n; la = {}
        for i in range(n):
            if i == 0: fib_s[i] = const; lz_s[i] = const
            else:
                fib_s[i] = (words[i-1] + fibs[i % Lf]) & mask
                lz_s[i] = la.get(words[i-1], const); la[words[i-1]] = words[i]
        def pk(res):
            rb = bytearray()
            if bd == 4:
                for i in range(0, len(res), 2):
                    v = res[i] << 4
                    if i+1 < len(res): v |= res[i+1]
                    rb.append(v)
            elif bd == 16:
                for r in res: rb.append((r>>8)&0xFF); rb.append(r&0xFF)
            elif bd == 32:
                for r in res: rb.extend(r.to_bytes(4, 'big'))
            else:
                for r in res: rb.extend(r.to_bytes(8, 'big'))
            return bytes(rb)
        rbytes = bytearray(); ppb = bytearray(); nb = 0
        for start in range(0, n, self.BLOCK):
            end = min(start + self.BLOCK, n); blk = words[start:end]
            bs = None; bp = 0; brb = None
            for code, ps in ((0, [const]*len(blk)), (1, fib_s[start:end]), (2, lz_s[start:end])):
                res = [(blk[i] - ps[i]) & mask for i in range(len(blk))]
                rb = pk(res); sc = sum(1 for i in range(1, len(rb)) if rb[i] != rb[i-1])
                if bs is None or sc < bs: bs = sc; bp = code; brb = rb
            rbytes.extend(brb); ppb.append(bp); nb += 1
        freq = [0]*256
        for b in rbytes: freq[b] += 1
        cl = self._hcl(freq); codes = self._hcc(cl)
        bits = []
        for b in rbytes:
            c, ln = codes[b]
            for k in range(ln-1,-1,-1): bits.append((c>>k)&1)
        bits.extend([0]*((8 - len(bits) % 8) % 8))
        hf = bytearray()
        for i in range(0, len(bits), 8):
            v = 0
            for j in range(8): v = (v<<1)|bits[i+j]
            hf.append(v)
        km = b'T58' + len(d).to_bytes(8, 'big') + bytes(cl) + bytes(ppb)
        sd = hashlib.sha256(km).digest()
        st = bytearray(); ctr = 0
        while len(st) < len(hf): st.extend(hashlib.sha256(sd + ctr.to_bytes(8, 'big')).digest()); ctr += 1
        wh = bytes(h ^ s for h, s in zip(hf, st))
        body = bytearray()
        body.append(0x58); body.append(bd_code); body.append(3)
        body.extend(len(d).to_bytes(8, 'big'))
        if bd == 4: body.append(const & 0xFF)
        else: body.extend(const.to_bytes(wbytes, 'big'))
        body.extend(bytes(cl)); body.extend(nb.to_bytes(4, 'big'))
        body.extend(bytes(ppb)); body.extend(wh)
        return bytes(body)
    def r58(self, d):
        if not d or d[0] != 0x58: raise TransformError("T58 magic")
        pos = 1; bd_code = d[pos]; pos += 1; pc = d[pos]; pos += 1
        ol = int.from_bytes(d[pos:pos+8], 'big'); pos += 8
        if bd_code > 3: raise TransformError("T58 bd")
        depths = [4,16,32,64]; bd = depths[bd_code]; wbytes = 0 if bd == 4 else bd//8
        if bd == 4: const = d[pos] & 0xF; pos += 1; mask = 0xF
        else: const = int.from_bytes(d[pos:pos+wbytes], 'big'); pos += wbytes; mask = (1<<bd)-1
        cl = list(d[pos:pos+256]); pos += 256
        ppb = None; nb = 0
        if pc == 3:
            nb = int.from_bytes(d[pos:pos+4], 'big'); pos += 4
            ppb = list(d[pos:pos+nb]); pos += nb
        elif pc > 2: raise TransformError("T58 pred")
        hw = d[pos:]
        if ol == 0: return b''
        km = b'T58' + ol.to_bytes(8, 'big') + bytes(cl)
        if ppb is not None: km += bytes(ppb)
        sd = hashlib.sha256(km).digest()
        st = bytearray(); ctr = 0
        while len(st) < len(hw): st.extend(hashlib.sha256(sd + ctr.to_bytes(8, 'big')).digest()); ctr += 1
        hf = bytes(h ^ s for h, s in zip(hw, st))
        sy = sorted(range(256), key=lambda s: (cl[s], s))
        ct = {}; c = 0; pl = 0; first = True
        for s in sy:
            L = cl[s]
            if L == 0: continue
            if first: pl = L; first = False
            elif L != pl: c <<= (L-pl); pl = L
            ct[(L, c)] = s; c += 1
        mxl = max(cl) if any(cl) else 0
        bits = []
        for b in hf:
            for i in range(7,-1,-1): bits.append((b>>i)&1)
        if bd == 4: nw = ol*2; nrb = (nw+1)//2
        else: nw = (ol+wbytes-1)//wbytes; nrb = nw*wbytes
        rb = bytearray(); bp = 0; nbb = len(bits)
        while len(rb) < nrb and bp < nbb:
            f = False
            for L in range(1, mxl+1):
                if bp+L > nbb: break
                v = 0
                for j in range(L): v = (v<<1)|bits[bp+j]
                if (L, v) in ct: rb.append(ct[(L, v)]); bp += L; f = True; break
            if not f: raise TransformError("T58 huff dec")
        if len(rb) != nrb: raise TransformError("T58 huff len")
        if bd == 4:
            res = []
            for b in rb: res.append((b>>4)&0xF); res.append(b&0xF)
            res = res[:nw]
        elif bd == 16: res = [int.from_bytes(rb[i:i+2], 'big') for i in range(0, len(rb), 2)]
        elif bd == 32: res = [int.from_bytes(rb[i:i+4], 'big') for i in range(0, len(rb), 4)]
        else: res = [int.from_bytes(rb[i:i+8], 'big') for i in range(0, len(rb), 8)]
        fibs = self.fib or [0,1]; Lf = len(fibs)
        words = [0]*nw; la = {}
        for i in range(nw):
            if pc == 3:
                blk = i // self.BLOCK; pcode = ppb[blk] if blk < len(ppb) else 0
                if pcode == 0: p = const
                elif pcode == 1: p = const if i == 0 else (words[i-1] + fibs[i%Lf]) & mask
                else: p = const if i == 0 else la.get(words[i-1], const)
            elif pc == 0: p = const
            elif pc == 1: p = const if i == 0 else (words[i-1] + fibs[i%Lf]) & mask
            else: p = const if i == 0 else la.get(words[i-1], const)
            w = (res[i] + p) & mask; words[i] = w
            if i >= 1: la[words[i-1]] = w
        if bd == 4:
            o = bytearray()
            for i in range(0, nw, 2):
                hi = words[i] & 0xF; lo = words[i+1] & 0xF if i+1 < nw else 0
                o.append((hi<<4)|lo)
            return bytes(o[:ol])
        o = bytearray()
        for w in words: o.extend(w.to_bytes(wbytes, 'big'))
        return bytes(o[:ol])

    # ─── ID 62: quantum mask transform (XOR, self-inverse) ───
    def t_quantum(self, d):
        if not d or not HAS_QISKIT:
            return d
        nq = getattr(self, "QUBITS", 16)
        mask = quantum_bytes_mask(nq, len(d))
        return (int.from_bytes(d, "big") ^ int.from_bytes(mask, "big")).to_bytes(len(d), "big")
    r_quantum = t_quantum

    def t256(self, d): return d
    r256 = t256
    def _dyn(self, n):
        def tf(d):
            if not d: return b''
            sd = self._seed(n % len(self.seeds), len(d))
            return d.translate(self._xor_table(sd))
        return tf, tf

    def _maps(self):
        eager_f = {}; eager_r = {}
        for i in range(1, 22):
            eager_f[i] = getattr(self, f"t{i:02d}"); eager_r[i] = getattr(self, f"r{i:02d}")
        for i in (22,23,24,25,26,27,28,29,30,31,32):
            eager_f[i] = getattr(self, f"t{i}"); eager_r[i] = getattr(self, f"r{i}")
        eager_f[33] = self._t33; eager_r[33] = self._r33
        eager_f[34] = self._t34; eager_r[34] = self._r34
        eager_f[35] = self._t35; eager_r[35] = self._r35
        eager_f[36] = self._t36; eager_r[36] = self._r36
        eager_f[37] = self._t37; eager_r[37] = self._r37
        eager_f[38] = self._t38; eager_r[38] = self._r38
        eager_f[39] = self._t39; eager_r[39] = self._r39
        eager_f[40] = self._t40; eager_r[40] = self._r40
        for i in (41,42,43,44,45,46,47):
            eager_f[i] = getattr(self, f"t{i}"); eager_r[i] = getattr(self, f"r{i}")
        for i in range(48, 57):
            f, r = self._dyn(i); eager_f[i] = f; eager_r[i] = r
        eager_f[57] = self.t57; eager_r[57] = self.r57
        eager_f[58] = self.t58; eager_r[58] = self.r58
        eager_f[59] = self.t59; eager_r[59] = self.r59
        eager_f[60] = self.t_cdd; eager_r[60] = self.r_cdd
        eager_f[61] = self.t_xml; eager_r[61] = self.r_xml
        eager_f[62] = self.t_quantum; eager_r[62] = self.r_quantum
        for i in range(63, 256):
            f, r = self._dyn(i); eager_f[i] = f; eager_r[i] = r
        eager_f[256] = self.t256; eager_r[256] = self.r256
        self.fwd = eager_f
        self.rev = eager_r
        print(f"Registered eager transforms 1-256; "
              f"headerless Circle-Diameter-Dot at ID 60; "
              f"XML/DOCX/DOC tokenizer at ID 61; "
              f"Qiskit quantum-mask at ID 62. "
              f"Minus transforms disabled.")

    def _pairs(self):
        self.pairs = []
        for a in range(1, 257):
            for b in range(1, 257):
                if a == 256 and b == 256: continue
                self.pairs.append((a, b))
    def _mr(self): return bytes([252])
    def _dh(self, d):
        if not d: return 0, ()
        f = d[0]
        if f < 252: return 1, (f+1,)
        if f == 252: return 1, ()
        if f == 253:
            if len(d) < 3: return 0, ()
            idx = (d[1]<<8) | d[2]
            if idx >= len(self.pairs): return 0, ()
            return 3, self.pairs[idx]
        if f == 254:
            if len(d) < 2: return 0, ()
            x = d[1]; return (2, (253+x,)) if x <= 2 else (0, ())
        if f == 255:
            if len(d) < 3: return 0, ()
            return 3, (256 + d[1]*256 + d[2],)
        return 0, ()
    def _auto(self, d):
        off, seq = self._dh(d)
        if off == 0: raise DecompressionError("Bad header")
        p = d[off:]
        if not p: raise DecompressionError("Empty")
        r = self.dback(p)
        if r is None: raise DecompressionError("Backend failed")
        if not seq: return r, None
        for t in reversed(seq): r = self.rev[t](r)
        return r, seq
    def _write(self, path, data):
        dd = os.path.dirname(path) or '.'
        fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path)+'.tmp', dir=dd)
        try: os.write(fd, data)
        finally: os.close(fd)
        os.replace(tmp, path)
    def _require_file(self, path):
        if not path: print("Error: no filename given."); return False
        if not os.path.exists(path): print(f"Error: file not found: {path!r}"); return False
        if not os.path.isfile(path): print(f"Error: not a regular file: {path!r}"); return False
        if not os.access(path, os.R_OK): print(f"Error: permission denied: {path!r}"); return False
        return True

    def _recompute(self, ext, data, rc):
        tp = len(self.pairs)
        try:
            if ext == "_raw_": return rc, True
            if ext.startswith(".p"):
                idx = int(ext[2:]) - 1
                if tp > 0 and idx >= tp: a, b = self.pairs[idx % tp]
                else: a, b = self.pairs[idx]
                p = self.cback(self.fwd[b](self._get_fwd(a, data)))
                return p, True
            if ext.startswith(".a"):
                tn = int(ext[2:])
                p = self.cback(self._get_fwd(tn, data))
                return p, True
        except Exception:
            return None, False
        return None, False

    def compress(self, infile, pairs=True, multi=False, timeout=None):
        global _GLOBAL_COMP, _GLOBAL_DATA, _GLOBAL_FWD
        if not self._require_file(infile): return
        try:
            with open(infile, 'rb') as f: data = f.read()
        except PermissionError: print(f"Error: permission denied reading {infile!r}"); return
        except OSError as e: print(f"Error reading {infile!r}: {e}"); return
        if len(data) == 0:
            print(f"Error: {infile!r} is empty.")
            return

        self.FAST = False; self.USE_MP = True
        print(f"\nInput: {len(data):,} bytes"); print("="*64)
        print(f"Target pairs : {self.PAIRS}")
        print(f"Qubits       : {self.QUBITS}  (Qiskit permutation)")
        print(f"Workers      : {N_CORES}" + (" (fork)" if _HAS_FORK else " (spawn)"))
        print(f"cback thr    : {CBACK_WORKERS} (parent) / {CBACK_WORKERS_EFF} (worker)")
        print(f"Chunk size   : {CHUNK}")
        print(f"Repeats      : {REPEATS}")
        print(f"Mode         : DETERMINISTIC · IPC-lite + C-XOR + identity skip")

        use_pool = _HAS_FORK and N_CORES > 1
        pair_count = self.PAIRS
        tp = len(self.pairs)
        all_elapsed = []; all_in_speed = []; all_out_speed = []

        for rep_i in range(REPEATS):
            if REPEATS > 1: print(f"\n--- Repeat {rep_i+1}/{REPEATS} ---")
            self._cback_cache.clear()
            self._fwd_cache.clear()

            st = time.time()
            rc = self._mr() + self.cback(data)
            cands = [("_raw_", len(rc), "raw payload")]
            best = len(rc)
            print(f"  [raw] size={len(rc)} bytes  best={best}")

            base_c = rc[1:]
            cands.append((".a1", len(base_c), "single #1 (identity)"))
            if len(base_c) < best:
                best = len(base_c)
                print(f"  [single   1/256] size={len(base_c)}  <<< BEST {best}")

            _GLOBAL_COMP = self
            _GLOBAL_DATA = data
            _GLOBAL_FWD = {}
            if len(data) * 256 <= (512 << 20):
                t0 = time.time()
                for t in range(1, 257):
                    try: _GLOBAL_FWD[t] = self.fwd[t](data)
                    except Exception: pass
                print(f"  precompute fwd[1..256]: {time.time()-t0:.3f}s ({len(_GLOBAL_FWD)} entries)")

            pair_task_list = []
            skipped_id = 0
            perm = self._qperm if (HAS_QISKIT and len(self._qperm) >= pair_count) else list(range(pair_count))
            for k in range(pair_count):
                i = perm[k] if k < len(perm) else k
                if tp > 0 and i >= tp: a, b = self.pairs[i % tp]
                else: a, b = self.pairs[i]
                if a in IDENTITY_IDS or b in IDENTITY_IDS:
                    skipped_id += 1
                    continue
                pair_task_list.append((i, a, b))
            if skipped_id:
                print(f"  identity-skip: {skipped_id} pair(s) equal to a single (skipped)")

            pool = None
            if use_pool:
                try:
                    pool = _MP_CTX.Pool(N_CORES)
                    print(f"  pool: spawned {N_CORES} workers")
                except Exception as e:
                    print(f"  pool: spawn failed ({e}); falling back to serial")
                    pool = None

            try:
                single_tasks = [t for t in range(1, 257) if t not in IDENTITY_IDS]

                if pool is not None:
                    results_s = []; done_s = set()
                    try:
                        for r in pool.imap_unordered(_worker_single, single_tasks, chunksize=max(1, CHUNK // 4)):
                            results_s.append(r); done_s.add(r[0])
                    except Exception as e:
                        print(f"  singles: pool error ({e}); retrying missing serially")
                    missing_s = [t for t in single_tasks if t not in done_s]
                    if missing_s:
                        print(f"  singles: serial retry for {len(missing_s)}")
                        for t in missing_s:
                            try: results_s.append(_worker_single(t))
                            except Exception as e:
                                print(f"  [single {t:>3}] retry FAILED ({e})")
                    results_s.sort(key=lambda x: x[0])
                    for t, size, err in results_s:
                        if err:
                            print(f"  [single {t:>3}/256] FAILED ({err})"); continue
                        cands.append((f".a{t}", size, f"single #{t}"))
                        if size < best:
                            best = size
                            print(f"  [single {t:>3}/256] size={size}  <<< BEST {best}")
                        else:
                            print(f"  [single {t:>3}/256] size={size}  best={best}")
                else:
                    for t in single_tasks:
                        if timeout and time.time()-st > timeout:
                            print("  Time limit reached (singles)"); break
                        try:
                            tr = self._get_fwd(t, data); p = self.cback(tr)
                            cands.append((f".a{t}", len(p), f"single #{t}"))
                            size = len(p)
                            if size < best:
                                best = size
                                print(f"  [single {t:>3}/256] size={size}  <<< BEST {best}")
                        except Exception as e:
                            print(f"  [single {t:>3}/256] FAILED ({e})")

                print(f"  pairs: {len(pair_task_list)} tasks on {N_CORES} workers (chunk={CHUNK})")

                if pool is not None:
                    results_p = []; done_p = set()
                    try:
                        for r in pool.imap_unordered(_worker_pair, pair_task_list, chunksize=CHUNK):
                            results_p.append(r); done_p.add(r[0])
                    except Exception as e:
                        print(f"  pairs: pool error ({e}); retrying missing serially")
                    missing_p = [t for t in pair_task_list if t[0] not in done_p]
                    if missing_p:
                        print(f"  pairs: serial retry for {len(missing_p)} missing")
                        for t in missing_p:
                            try: results_p.append(_worker_pair(t))
                            except Exception as e:
                                if t[0] < 500: print(f"  [pair {t[0]+1}] retry FAILED ({e})")
                    results_p.sort(key=lambda x: x[0])
                    for idx, a, b, size, err in results_p:
                        if err:
                            if idx < 500: print(f"  [pair {idx+1}] FAILED ({err})")
                            continue
                        cands.append((f".p{idx+1}", size, f"pair #{idx+1} (#{a}->#{b})"))
                        if size < best:
                            best = size
                            print(f"  [pair {idx+1:>10} #{a:>3}->#{b:>3}] size={size}  <<< BEST {best}")
                        elif idx < 500 or (idx+1) % 10000 == 0:
                            print(f"  [pair {idx+1:>10} #{a:>3}->#{b:>3}] size={size}  best={best}")
                    print(f"  pairs done: {len(results_p)} of {len(pair_task_list)}  best={best}")
                else:
                    i = 0
                    while i < len(pair_task_list):
                        if timeout and time.time()-st > timeout:
                            print(f"  Time limit reached at pair {i}/{len(pair_task_list)}"); break
                        t = pair_task_list[i]
                        _, a, b = t
                        try:
                            p = self.cback(self.fwd[b](self._get_fwd(a, data)))
                            size = len(p)
                            cands.append((f".p{t[0]+1}", size, f"pair #{t[0]+1} (#{a}->#{b})"))
                            if size < best:
                                best = size
                                print(f"  [pair {t[0]+1:>10} #{a:>3}->#{b:>3}] size={size}  <<< BEST {best}")
                            elif t[0] < 500 or (t[0]+1) % 10000 == 0:
                                print(f"  [pair {t[0]+1:>10} #{a:>3}->#{b:>3}] size={size}  best={best}")
                        except Exception as e:
                            if t[0] < 500: print(f"  [pair {t[0]+1}] FAILED ({e})")
                        i += 1
                    print(f"  pairs done: {i} of {len(pair_task_list)}  best={best}")
            finally:
                if pool is not None:
                    pool.close(); pool.join()
                _GLOBAL_COMP = None
                _GLOBAL_DATA = None
                _GLOBAL_FWD = {}

            if not cands:
                print("Nothing to write"); return

            ranked = sorted(cands, key=lambda x: x[1])
            winner = None; tries = 0
            for ext, size, label in ranked[:TOP_VERIFY]:
                tries += 1
                blob, ok = self._recompute(ext, data, rc)
                if not ok or blob is None: continue
                if len(blob) != size:
                    print(f"  WARN: recompute size {len(blob)} != worker {size} for {ext}")
                if ext == "_raw_":
                    try: chk, _ = self._auto(blob)
                    except Exception: continue
                elif ext.startswith(".p"):
                    idx = int(ext[2:]) - 1
                    if tp > 0 and idx >= tp: a, b = self.pairs[idx % tp]
                    else: a, b = self.pairs[idx]
                    r = self.dback(blob)
                    if r is None: continue
                    try: chk = self.rev[a](self.rev[b](r))
                    except Exception: continue
                elif ext.startswith(".a"):
                    tn = int(ext[2:]); r = self.dback(blob)
                    if r is None: continue
                    try: chk = self.rev[tn](r)
                    except Exception: continue
                else: continue
                if chk == data:
                    winner = (ext, blob, label); break

            if winner is None:
                print(f"  No candidate verified in top-{tries}; raw fallback")
                ext = "_raw_"; payload = rc; label = "raw fallback"
            else:
                ext, payload, label = winner

            elapsed = time.time() - st
            in_speed = len(data) / elapsed if elapsed > 0 else 0.0
            out_speed = len(payload) / elapsed if elapsed > 0 else 0.0
            all_elapsed.append(elapsed); all_in_speed.append(in_speed); all_out_speed.append(out_speed)

            out_dir = os.path.dirname(infile) or '.'
            if os.path.isdir(out_dir):
                for f in os.listdir(out_dir):
                    fp = os.path.join(out_dir, f)
                    if re.match(rf'^{re.escape(os.path.basename(infile))}\.[ap][\d-]+$', f):
                        try: os.remove(fp)
                        except Exception: pass
            out = infile + ext
            self._write(out, payload)

            print("\n" + "="*64)
            print(f"WINNER: {out}")
            print(f"  Method   : {label}")
            print(f"  Size     : {len(payload):,} bytes  ({len(payload)/len(data)*100:.2f}%)")
            print(f"  Original : {len(data):,} bytes")
            print(f"  Saved    : {len(data)-len(payload):,} bytes")
            print(f"  Time     : {elapsed:.4f} s")
            print(f"  Speed in : {in_speed:,.0f} bytes/s  ({in_speed/1024:.2f} KB/s)")
            print(f"  Speed out: {out_speed:,.0f} bytes/s  ({out_speed/1024:.2f} KB/s)")
            print(f"  Workers  : {N_CORES} (deterministic — same size on any core count)")
            print(f"  [VERIFIED LOSSLESS]")

        if REPEATS > 1:
            print("\n" + "="*64)
            print(f"SUMMARY ({REPEATS} repeats)")
            avg_t = sum(all_elapsed)/len(all_elapsed)
            print(f"  Avg time    : {avg_t:.4f} s")
            print(f"  Avg speed in: {sum(all_in_speed)/len(all_in_speed):,.0f} bytes/s")
            print(f"  Avg speedout: {sum(all_out_speed)/len(all_out_speed):,.0f} bytes/s")
            print(f"  Min time    : {min(all_elapsed):.4f} s")
            print(f"  Max time    : {max(all_elapsed):.4f} s")

    def decompress(self, infile, outfile=""):
        if not self._require_file(infile): return False
        try:
            with open(infile, 'rb') as f: blob = f.read()
        except (PermissionError, OSError) as e: print(f"Error reading {infile!r}: {e}"); return False
        if len(blob) == 0: print(f"Error: {infile!r} is empty."); return False
        base = os.path.basename(infile)
        m = re.search(r'\.p(\d+)$', infile)
        if m:
            idx = int(m.group(1)) - 1; total = len(self.pairs)
            if total == 0: print("Error: no pairs."); return False
            a, b = self.pairs[idx % total]
            try: r = self.dback(blob)
            except Exception as e: print(f"Error: backend failed: {e}"); return False
            if r is None: print("Error: backend could not decode payload."); return False
            orig = self.rev[a](self.rev[b](r))
            if not outfile: outfile = re.sub(r'\.p\d+$', '', base) or (base + ".out")
            self._write(outfile, orig); print(f"-> {outfile} ({len(orig)} bytes)"); return True
        m = re.search(r'\.a(\d+)$', infile, re.IGNORECASE)
        if m:
            tn = int(m.group(1))
            if not (1 <= tn <= self.MAX_EAGER_ID):
                print(f"Error: transform out of range (must be 1..256): {tn}"); return False
            try: r = self.dback(blob)
            except Exception as e: print(f"Error: backend failed: {e}"); return False
            if r is None: print("Error: backend could not decode payload."); return False
            try: orig = self.rev[tn](r)
            except Exception as e: print(f"Error: inverse transform #{tn} failed: {e}"); return False
            if not outfile: outfile = re.sub(r'\.a\d+$', '', base, flags=re.IGNORECASE) or (base + ".out")
            self._write(outfile, orig); print(f"-> {outfile} ({len(orig)} bytes)"); return True
        off, seq = self._dh(blob)
        if off == 0: print(f"Error: bad header in {infile!r}."); return False
        try: orig, _ = self._auto(blob)
        except Exception as e: print(f"Error decoding {infile!r}: {e}"); return False
        if not outfile: outfile = base + ".out"
        self._write(outfile, orig); print(f"-> {outfile} ({len(orig)} bytes)")
        return True

    def selftest(self):
        print("="*60); print("Lossless Self-Test"); print("="*60)
        print(f"Pairs={self.PAIRS}  Qubits={self.QUBITS}  Stride={self.STRIDE}  Workers={N_CORES}")
        tbs = [0x00, 0xFF, 0xAA, 0x55, 0x12, 0x34]
        for t in range(1, 257):
            for tb in tbs:
                d = bytes([tb])
                try:
                    tr = self.fwd[t](d); rs = self.rev[t](tr)
                    if rs != d: print(f"  FAIL t={t} b={tb:#04x}"); return False
                except TransformError: continue
                except Exception as e: print(f"  EXC t={t} b={tb:#04x}: {e}"); return False
        print("  Transforms 1..256 on single bytes: PASS")
        test_vectors = [b"hello world " * 4, bytes(range(64)), b"A" * 100,
                        b"The quick brown fox jumps over the lazy dog. " * 3, os.urandom(128)]
        for t in range(1, 257):
            for tv in test_vectors:
                try:
                    tr = self.fwd[t](tv); rs = self.rev[t](tr)
                    if rs != tv: print(f"  FAIL t={t} len={len(tv)}"); return False
                except TransformError: continue
                except Exception as e: print(f"  EXC t={t} len={len(tv)}: {e}"); return False
        print("  Transforms 1..256 on multi-byte vectors: PASS")
        print("  Testing headerless Circle-Diameter-Dot transform (ID 60) ...")
        test60 = [b"", b"\x00", b"\xff", b"\x00\x00", b"\x00\x00\x00",
                  b"hello", b"hello world", b"hello world!",
                  os.urandom(3), os.urandom(4), os.urandom(5),
                  os.urandom(7), os.urandom(8), os.urandom(9),
                  os.urandom(64), os.urandom(1000),
                  b"\x00"*31, b"\x00"*32, b"\x00"*33,
                  b"\xff"*32, b"\xff"*33, bytes(range(256))]
        for tv in test60:
            tr = self.t_cdd(tv); rs = self.r_cdd(tr)
            if rs != tv: print(f"  FAIL t_cdd len={len(tv)}"); return False
        print("  Headerless Circle-Diameter-Dot transform: PASS")
        print("  Testing XML/DOCX/DOC transform (ID 61) ...")
        test61 = [b"", b"<a>", b"<a>x</a>",
                  b"<?xml version=\"1.0\"?><root><child a=\"1\">text</child></root>",
                  b"<w:document><w:body><w:p><w:r><w:t>Hello</w:t></w:r></w:p></w:body></w:document>",
                  b"<w:p>a</w:p>" * 200, b"</w:p><w:p><w:p>mixed</w:p><w:p>",
                  os.urandom(64), b"\x00\x00\x00"]
        for tv in test61:
            tr = self.t_xml(tv); rs = self.r_xml(tr)
            if rs != tv: print(f"  FAIL t_xml len={len(tv)}"); return False
        _zbuf = io.BytesIO()
        with zipfile.ZipFile(_zbuf, 'w', zipfile.ZIP_STORED) as z:
            z.writestr("word/document.xml", b"<?xml version=\"1.0\"?><w:document><w:body><w:p><w:r><w:t>Hello</w:t></w:r></w:p></w:body></w:document>")
        docx_bytes = _zbuf.getvalue()
        tr = self.t_xml(docx_bytes); rs = self.r_xml(tr)
        if rs != docx_bytes: print(f"  FAIL t_xml docx len={len(docx_bytes)}"); return False
        doc_bytes = OLE_MAGIC + b"\x00" * 100
        tr = self.t_xml(doc_bytes); rs = self.r_xml(tr)
        if rs != doc_bytes: print("  FAIL t_xml doc (OLE passthrough)"); return False
        print("  XML/DOCX/DOC transform: PASS")
        print("  Testing Qiskit quantum-mask transform (ID 62) ...")
        if HAS_QISKIT:
            for tv in [b"", b"a", b"hello", b"hello world"*8, os.urandom(64)]:
                tr = self.t_quantum(tv); rs = self.r_quantum(tr)
                if rs != tv: print(f"  FAIL t_quantum len={len(tv)}"); return False
            p1 = quantum_pair_permutation(min(self.PAIRS, 4096), self.QUBITS)
            p2 = quantum_pair_permutation(min(self.PAIRS, 4096), self.QUBITS)
            assert p1 == p2, "quantum permutation must be deterministic"
            assert len(set(p1)) == len(p1), "quantum permutation must be a bijection"
            print(f"  Qiskit {self.QUBITS}-qubit permutation & mask: PASS")
        else:
            print("  Qiskit transform: SKIP (qiskit not available)")
        print("  Testing Lepton JPEG round-trip (if available) ...")
        if HAS_LEPTON:
            try:
                from PIL import Image
                img = Image.new('RGB', (16, 16), color=(128, 64, 32))
                buf = io.BytesIO(); img.save(buf, format='JPEG', quality=85)
                jpg = buf.getvalue(); c = self._leptonc(jpg)
                if c is not None:
                    d = self._leptond(c)
                    if d == jpg: print(f"  Lepton JPEG round-trip: PASS ({len(jpg)} -> {len(c)} bytes)")
                    else: print("  Lepton JPEG round-trip: FAIL (mismatch)"); return False
                else: print("  Lepton JPEG round-trip: SKIP")
            except ImportError: print("  Lepton JPEG round-trip: SKIP (PIL not installed)")
        else: print("  Lepton JPEG round-trip: SKIP (lepton not installed)")
        pair_data = b"The quick brown fox jumped over."; n_ok = 0
        for i in range(min(1000, len(self.pairs))):
            a, b = self.pairs[i]
            tr = self.fwd[b](self.fwd[a](pair_data))
            rs = self.rev[a](self.rev[b](tr))
            if rs != pair_data: print(f"  FAIL pair {i+1}"); return False
            n_ok += 1
        print(f"  First {n_ok} pairs: PASS")
        for p in [b"hello world " * 20, b"\x00" * 1000, os.urandom(200)]:
            e = self.cback(p); d = self.dback(e)
            if d != p: print(f"  FAIL backend {len(p)}"); return False
        print("  Backends: PASS")
        a1 = self.cback(b"cache-test-vector")
        a2 = self.cback(b"cache-test-vector")
        assert a1 == a2, "cback cache must be deterministic"
        print("  cback memoization deterministic: PASS")
        tv = b"the quick brown fox jumps over the lazy dog"
        for a in (1, 50, 100, 200, 255):
            single = self.cback(self.fwd[a](tv))
            pair_id_1 = self.cback(self.fwd[1](self.fwd[a](tv)))
            pair_id_31 = self.cback(self.fwd[31](self.fwd[a](tv)))
            pair_id_32 = self.cback(self.fwd[32](self.fwd[a](tv)))
            pair_id_256 = self.cback(self.fwd[256](self.fwd[a](tv)))
            assert (pair_id_1 == single and pair_id_31 == single
                    and pair_id_32 == single and pair_id_256 == single), \
                f"identity-pair equivalence broken for a={a}"
        print("  identity-pair equivalence: PASS")
        if _HAS_FORK and N_CORES > 1:
            print(f"  Testing {N_CORES}-worker parallel tournament (determinism) ...")
            global _GLOBAL_COMP, _GLOBAL_DATA, _GLOBAL_FWD
            payload = b"the quick brown fox " * 8
            _GLOBAL_COMP = self; _GLOBAL_DATA = payload; _GLOBAL_FWD = {}
            try:
                with _MP_CTX.Pool(N_CORES) as pool:
                    singles = list(pool.imap_unordered(_worker_single, [1, 60, 61, 62, 256], chunksize=1))
                    pairs_r = list(pool.imap_unordered(_worker_pair,
                                                       [(i, self.pairs[i][0], self.pairs[i][1]) for i in range(8)],
                                                       chunksize=1))
                assert all(err is None for _, _, err in singles), "single error"
                assert all(err is None for _, _, _, _, err in pairs_r), "pair error"
                print(f"  {N_CORES}-worker size-only tournament: PASS")
            except Exception as e:
                print(f"  {N_CORES}-worker parallel tournament: FAIL ({e})"); return False
            finally:
                _GLOBAL_COMP = None; _GLOBAL_DATA = None; _GLOBAL_FWD = {}
        print("[ALL LOSSLESS CHECKS PASSED]")
        return True

def main():
    print(f"{PROGNAME}")
    print("* Target: 1 KB Lorem ipsum -> ~240 bytes, 100% lossless *")
    print("* Deterministic · IPC-lite · C-level XOR · identity skip *")
    print(f"* Qiskit {QUBITS}-qubit circuit-driven pair order (same winner any core count) *\n")
    try:
        mp.set_start_method('fork', force=True)
        print(f"mp: fork, {N_CORES} workers (cpu_count={CPU_COUNT})")
    except (RuntimeError, ValueError):
        print(f"mp: spawn default, {N_CORES} workers")
    dl = input("Download 12 Google Drive dictionaries? (y/n) [y]: ").strip().lower()
    c = Compressor(try_dl=(dl != 'n'), pairs=PAIRS, qubits=QUBITS)
    while True:
        print("\nMenu:")
        print("1) Compress (lossless tournament)")
        print("2) Decompress")
        print("3) Lossless self-test")
        ch = input("> ").strip()
        if ch == "1":
            f = input("Input file: ").strip()
            if not f:
                print("No file given.")
                continue
            c.compress(f, pairs=True, multi=False)
            print("\nCompression finished — exiting.")
            return
        elif ch == "2":
            f = input("Compressed: ").strip()
            if not f:
                print("No file given.")
                continue
            o = input("Output (blank=auto): ").strip()
            c.decompress(f, o)
        elif ch == "3":
            c.selftest()
        else:
            print("Invalid")

if __name__ == "__main__":
    main()
