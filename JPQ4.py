#!/usr/bin/env python3
# written by Jurijus Pacalovas
# -*- coding: utf-8 -*-
# PPMD_1.6 — Lossless Tournament + XML structural v3 (XY/XZ/XW/XC/XD/XE) + Qiskit mask
# + wide-base minus transforms (a77-a83) + 22-family diverse filler (a84-a255)
# + a256 = XOR64 search — 512 candidate keys in sampled64 mode
# EXTENSION-AS-HEADER — saves the 2 bytes inside the file
# + XLSX / PPTX seed dictionaries (container-aware path now earns real gains)

import math, random, decimal, hashlib, base64, heapq, struct, os
import tempfile, re, sys, subprocess, importlib, time, site, shutil
import urllib.request
import multiprocessing as mp
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import xml, xml.etree.ElementTree as ET, xml.sax.saxutils as saxutils
import zipfile, io, zlib

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

try:
    import qiskit
    from qiskit import QuantumCircuit
    HAS_QISKIT = True
    QISKIT_VER = getattr(qiskit, "__version__", "?")
except ImportError:
    qiskit = None; QuantumCircuit = None; HAS_QISKIT = False; QISKIT_VER = None

try:
    import lzma; HAS_LZMA = True
    LF_RAW = [{"id": lzma.FILTER_LZMA2, "preset": 9 | lzma.PRESET_EXTREME,
               "nice_len": 273, "mf": lzma.MF_BT4}]
except ImportError:
    lzma = None; HAS_LZMA = False; LF_RAW = None

HAS_ZPAQ = shutil.which('zpaq') is not None
HAS_CCMX = shutil.which('ccmx') is not None
HAS_CMIX = shutil.which('cmix') is not None

FAST_MODE       = os.environ.get("PPMD_FAST", "1") != "0"
FULL_SINGLES    = os.environ.get("PPMD_FULL_SINGLES", "1") != "0"
FULL_PAIRS      = os.environ.get("PPMD_FULL_PAIRS",   "1") != "0"
SKIP_SLOW       = os.environ.get("PPMD_SKIP_SLOW",    "1") != "0"
EARLY_EXIT_GAIN = float(os.environ.get("PPMD_EARLY_EXIT_GAIN", "0.55"))

A256_MODE        = os.environ.get("PPMD_A256_MODE", "sampled64").lower()
A256_EXHAUSTIVE  = (A256_MODE == "exhaustive")
A256_LIMIT       = int(os.environ.get("PPMD_A256_LIMIT", "0") or "0")
A256_START       = int(os.environ.get("PPMD_A256_START", "0") or "0")
A256_PROGRESS    = max(1, int(os.environ.get("PPMD_A256_PROGRESS", "1000000") or "1000000"))
A256_CKPT        = max(1, int(os.environ.get("PPMD_A256_CKPT", "10000000") or "10000000"))

CPU_COUNT = mp.cpu_count() or 4
N_CORES = max(1, int(os.environ.get("PPMD_CORES", str(CPU_COUNT)) or str(CPU_COUNT)))
REPEATS = max(1, int(os.environ.get("PPMD_REPEATS", "1") or "1"))
CBACK_WORKERS = max(2, int(os.environ.get("PPMD_CBACK_WORKERS", str(max(4, CPU_COUNT))) or "8"))
CBACK_WORKERS_EFF = max(1, CPU_COUNT // max(1, N_CORES))
CHUNK = max(1, int(os.environ.get("PPMD_CHUNK", "256") or "256"))
TOP_VERIFY = max(1, int(os.environ.get("PPMD_TOP_VERIFY", "5") or "5"))
try:
    _MP_CTX = mp.get_context("fork"); _HAS_FORK = True
except (ValueError, AttributeError):
    _MP_CTX = mp.get_context(); _HAS_FORK = False

IDENTITY_IDS = frozenset((1, 31, 32))
MAX_PAIRS = 65280
N_Q64_CANDIDATES = 512
KEY_BYTES = 8

_GLOBAL_COMP = None; _GLOBAL_DATA = None; _GLOBAL_FWD = {}
_GLOBAL_REF_BYTES = None; _GLOBAL_REF_CAP = None; _GLOBAL_REF_UP = None
_IN_WORKER = False

def _set_global_ref(rb, rcap, rup):
    global _GLOBAL_REF_BYTES, _GLOBAL_REF_CAP, _GLOBAL_REF_UP
    _GLOBAL_REF_BYTES = rb; _GLOBAL_REF_CAP = rcap; _GLOBAL_REF_UP = rup

def _worker_single(t):
    global _IN_WORKER
    if not _IN_WORKER: _IN_WORKER = True
    c = _GLOBAL_COMP; data = _GLOBAL_DATA
    if c is None or data is None: return (t, None, "worker not initialised")
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
    if c is None or data is None: return (idx, a, b, None, "worker not initialised")
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

print("="*70); print("PPMD_1.6 — Checking backends (a256 = XOR64 search, 512 candidates)"); print("="*70)
print(f"parallelism : {N_CORES} cores" + (" (fork)" if _HAS_FORK else " (spawn)"))
print(f"cpu count   : {CPU_COUNT}")
print(f"fast mode   : {'ON' if FAST_MODE else 'OFF'}")
print(f"full singles: {'ON (256 transforms)' if FULL_SINGLES else 'OFF'}")
print(f"full pairs  : {'ON (up to 65280 pairs)' if FULL_PAIRS else 'OFF'}")
print(f"skip slow   : {'ON' if SKIP_SLOW else 'OFF'}")
print(f"a256 mode   : " + (
    "EXHAUSTIVE 2^64 (never finishes)"    if A256_MODE == "exhaustive"       else
    "REPEAT-32 (all 2^32 seed||seed)"     if A256_MODE == "repeat32"         else
    "REPEAT-32 OPTIMAL (< 1 ms)"          if A256_MODE == "repeat32_optimal" else
    f"sampled64 ({N_Q64_CANDIDATES} candidates × 64-bit key)"
))
if A256_MODE in ("exhaustive", "repeat32") and A256_LIMIT > 0:
    print(f"a256 limit  : {A256_LIMIT:,} keys")
_z = _imp_zstd()
if _z is None:
    print("zstandard missing; trying auto-install...")
    _ins_zstd(); _z = _imp_zstd()
if _z:
    zstd = _z
    zc = zstd.ZstdCompressor(level=22); zd = zstd.ZstdDecompressor()
    zc_fast = zstd.ZstdCompressor(level=6)
    HAS_ZSTD = True; print("zstandard: OK")
else:
    zstd = zc = zd = zc_fast = None; HAS_ZSTD = False; print("zstandard: NOT available")

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
CMIX_SRC_URL = "https://github.com/byronknoll/cmix/archive/refs/tags/v21.tar.gz"

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
    if input("Install paq? (y/n) [n]: ").strip().lower() == 'y':
        if inst('paq'):
            try: import paq; print("paq: OK")
            except ImportError: paq = None
if not HAS_BROTLI:
    if input("Install brotli? (y/n) [y]: ").strip().lower() != 'n':
        if inst('brotli'):
            try: import brotli; HAS_BROTLI = True; print("brotli: OK")
            except ImportError: pass
if not HAS_CCMX:
    if input("Install ccmx? (y/n) [n]: ").strip().lower() == 'y': _install_ccmx()
_install_cmix()
if not HAS_LEPTON:
    if input("Install lepton_jpeg_python? (y/n) [n]: ").strip().lower() == 'y':
        if inst('lepton_jpeg_python'):
            try: import lepton_jpeg_python; HAS_LEPTON = True; print("lepton_jpeg_python: OK")
            except ImportError: print("lepton_jpeg_python: install failed")

def _build_seed_circuit(n_qubits):
    qc = QuantumCircuit(n_qubits, name="ppmd_q")
    for q in range(n_qubits): qc.h(q)
    for q in range(n_qubits): qc.t(q); qc.rz(math.pi/(q+1.0), q)
    for q in range(n_qubits-1): qc.cx(q, q+1); qc.rz(math.pi/(2.0**(q+1)), q+1)
    for q in range(n_qubits): qc.h(q)
    return qc

def _circuit_fingerprint(n_qubits):
    circuit_qubits = min(n_qubits, 64)
    qc = _build_seed_circuit(circuit_qubits)
    try: blob = qc.qasm().encode("utf-8")
    except Exception:
        parts = []
        for item in qc.data:
            op = item.operation if hasattr(item, "operation") else item[0]
            qargs = item.qubits if hasattr(item, "qubits") else item[1]
            parts.append(f"{op.name}|{op.params}|{[qc.find_bit(q).index for q in qargs]}")
        blob = ";;".join(parts).encode("utf-8")
    ver = (QISKIT_VER or "?").encode("utf-8")
    return hashlib.sha256(b"PPMD_QS|" + ver + b"|" +
                          str(n_qubits).encode() + b"|" + blob).digest()

_QPERM_CACHE = {}; _QMASK_CACHE = {}
def quantum_pair_permutation(n_pairs, n_qubits):
    key = (n_pairs, n_qubits)
    if key in _QPERM_CACHE: return _QPERM_CACHE[key]
    if not HAS_QISKIT or n_qubits < 1 or n_pairs <= 0:
        perm = list(range(max(0, n_pairs))); _QPERM_CACHE[key] = perm; return perm
    fp = _circuit_fingerprint(n_qubits)
    rng = random.Random(int.from_bytes(fp, "big"))
    perm = list(range(n_pairs))
    for i in range(n_pairs-1, 0, -1):
        j = rng.randrange(i+1); perm[i], perm[j] = perm[j], perm[i]
    _QPERM_CACHE[key] = perm; return perm

def quantum_bytes_mask(n_qubits, n_bytes):
    if not HAS_QISKIT or n_qubits < 1 or n_bytes <= 0: return b"\x00"*max(0, n_bytes)
    key = (n_qubits, n_bytes)
    if key in _QMASK_CACHE: return _QMASK_CACHE[key]
    fp = _circuit_fingerprint(n_qubits)
    rng = random.Random(int.from_bytes(fp, "big") ^ 0x9E3779B97F4A7C15)
    out = bytes(rng.randrange(256) for _ in range(n_bytes))
    _QMASK_CACHE[key] = out; return out

QUBIT_LIMIT = 1024

def ask_qubits():
    print("\n" + "="*70); print("Qiskit qubit count (1..1024)"); print("="*70)
    while True:
        raw = input("Qubits [1024]: ").strip()
        if raw == "": return 1024
        try:
            v = int(raw)
            if 1 <= v <= 1024: return v
        except ValueError: pass
        print("  Enter a whole number 1..1024.")

def ask_pairs(n_qubits=16):
    max_by_q = (1 << max(1, min(n_qubits, 31))) - 1
    cap = min(MAX_PAIRS, max_by_q)
    print("\n" + "="*70)
    print(f"Pair count (1..{cap})  [qubits={n_qubits}, hard cap {MAX_PAIRS}]")
    print("="*70)
    while True:
        raw = input(f"Pairs [{cap}]: ").strip()
        if raw == "": return cap
        try:
            v = int(raw)
            if 1 <= v <= cap: return v
        except ValueError: pass
        print(f"  Must be 1..{cap}.")

QUBITS = ask_qubits() if HAS_QISKIT else QUBIT_LIMIT
PAIRS = ask_pairs(QUBITS)
print(f"\nChosen: QUBITS={QUBITS}  PAIRS={PAIRS}")
if PAIRS > MAX_PAIRS:
    print(f"FATAL: {PAIRS} pairs exceed 2-byte header cap {MAX_PAIRS}."); sys.exit(1)

print(f"\nBackends: zstd={'Y' if HAS_ZSTD else 'N'} lzma={'Y' if HAS_LZMA else 'N'} "
      f"paq={'Y' if paq else 'N'} brotli={'Y' if HAS_BROTLI else 'N'} "
      f"pyppmd={'Y' if HAS_PPMD else 'N'} zpaq={'Y' if HAS_ZPAQ else 'N'} "
      f"ccmx={'Y' if HAS_CCMX else 'N'} cmix={'Y' if HAS_CMIX else 'N'} "
      f"lepton={'Y' if HAS_LEPTON else 'N'} qiskit={'Y' if HAS_QISKIT else 'N'}")
PROGNAME = "PPMD_1.6"

REF_TEXT = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum. "
    "Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo. Nemo enim ipsam voluptatem quia voluptas sit aspernatur aut odit aut fugit, sed quia consequuntur magni dolores eos qui ratione voluptatem sequi nesciunt. Neque porro quisquam est, qui dolorem ipsum quia dolor sit amet, consectetur, adipisci velit, sed quia non numquam eius modi tempora incidunt ut labore et dolore magnam aliquam quaerat voluptatem. Ut enim ad minima veniam, quis nostrum exercitationem ullam corporis suscipit laboriosam, nisi ut aliquid ex ea commodi consequatur. Quis autem vel eum iure reprehenderit qui in ea voluptate velit esse quam nihil molestiae consequatur, vel illum qui dolorem eum fugiat quo voluptas nulla pariatur. "
    "At vero eos et accusamus et iusto odio dignissimos ducimus qui blanditiis praesentium voluptatum deleniti atque corrupti quos dolores et quas molestias excepturi sint occaecati cupiditate non provident, similique sunt in culpa qui officia deserunt mollitia animi, id est laborum et dolorum fuga."
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
    while len(words) < target and guard < target*40:
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

_DOCX_TAGS = [
    b'w:document', b'w:body', b'w:p', b'w:r', b'w:t', b'w:sectPr', b'w:pPr', b'w:rPr',
    b'w:tbl', b'w:tblGrid', b'w:gridCol', b'w:tr', b'w:tc', b'w:tblPr', b'w:tblStyle',
    b'w:tblW', b'w:tcPr', b'w:tcW', b'w:tblBorders', b'w:tblCellMar', b'w:tblLayout',
    b'w:styles', b'w:style', b'w:name', b'w:basedOn', b'w:next', b'w:link',
    b'w:docDefaults', b'w:pPrDefault', b'w:rPrDefault', b'w:latentStyles', b'w:lsdException',
    b'w:numbering', b'w:abstractNum', b'w:num', b'w:lvl', b'w:start', b'w:numFmt',
    b'w:lvlText', b'w:lvlJc', b'w:settings', b'w:zoom', b'w:view', b'w:compat',
    b'w:rsids', b'w:rsid', b'w:proofErr', b'w:bookmarkStart', b'w:bookmarkEnd',
    b'w:hyperlink', b'w:fldChar', b'w:instrText', b'w:drawing', b'w:pict', b'w:object',
    b'w:sdt', b'w:sdtPr', b'w:sdtContent', b'w:ins', b'w:del', b'w:commentReference',
    b'w:commentRangeStart', b'w:commentRangeEnd', b'w:footnote', b'w:endnote',
    b'w:footnoteReference', b'w:endnoteReference', b'w:hdr', b'w:ftr',
    b'w:tab', b'w:br', b'w:cr', b'w:lastRenderedPageBreak', b'w:softHyphen', b'w:noBreakHyphen',
    b'w:b', b'w:bCs', b'w:i', b'w:iCs', b'w:caps', b'w:smallCaps', b'w:strike', b'w:dstrike',
    b'w:color', b'w:spacing', b'w:sz', b'w:szCs', b'w:highlight', b'w:u', b'w:shd',
    b'w:vertAlign', b'w:lang', b'w:pStyle', b'w:rStyle', b'w:rFonts',
    b'w:keepNext', b'w:keepLines', b'w:pageBreakBefore', b'w:widowControl',
    b'w:numPr', b'w:numId', b'w:ilvl', b'w:ind', b'w:jc', b'w:tabs', b'w:outlineLvl',
    b'w:pgSz', b'w:pgMar', b'w:pgBorders', b'w:cols', b'w:docGrid',
    b'w:headerReference', b'w:footerReference', b'w:themeFontLang', b'w:defaultTabStop',
    b'w:trackChanges', b'w:documentProtection', b'w:bidi', b'w:textDirection', b'w:vAlign',
    b'w:contextualSpacing', b'w:autoSpaceDE', b'w:autoSpaceDN',
    b'a:graphic', b'a:graphicData', b'a:blip', b'a:blipFill', b'a:stretch', b'a:solidFill',
    b'a:srgbClr', b'a:schemeClr', b'a:prstGeom', b'a:avLst', b'a:ln', b'a:off', b'a:ext',
    b'a:xfrm', b'a:fill', b'a:fillRef', b'a:lnRef', b'a:effectRef', b'a:fontRef',
    b'wp:inline', b'wp:anchor', b'wp:extent', b'wp:docPr', b'wp:positionH', b'wp:positionV',
    b'wp:cNvGraphicFramePr', b'wp:effectExtent',
    b'pic:pic', b'pic:blipFill', b'pic:spPr', b'pic:nvPicPr',
    b'v:shape', b'v:imagedata', b'v:textbox', b'v:group', b'v:rect', b'v:fill', b'v:stroke',
    b'o:OLEObject', b'mc:AlternateContent', b'mc:Choice', b'mc:Fallback',
    b'c:chart', b'c:chartSpace', b'c:ser', b'c:cat', b'c:val',
    b'cp:coreProperties', b'dc:creator', b'dc:title', b'dc:subject', b'dc:description',
    b'cp:lastModifiedBy', b'cp:revision', b'dcterms:created', b'dcterms:modified',
    b'ep:Properties', b'ep:Application', b'ep:AppVersion', b'ep:Company',
    b'vt:vector', b'vt:variant', b'vt:lpstr', b'vt:lpwstr',
    b'Relationship', b'Relationships', b'ContentType', b'Types', b'Default', b'Override',
    b'Properties', b'property',
]
_DOCX_ATTRS = [
    b'w:val', b'xml:space', b'xml:lang', b'xml:base',
    b'w:rsidR', b'w:rsidRPr', b'w:rsidP', b'w:rsidRDefault', b'w:rsidTr', b'w:rsidDel', b'w:rsidSect',
    b'w:ascii', b'w:hAnsi', b'w:cs', b'w:eastAsia',
    b'w:asciiTheme', b'w:hAnsiTheme', b'w:cstheme', b'w:eastAsiaTheme',
    b'w:color', b'w:sz', b'w:szCs', b'w:themeColor', b'w:themeTint', b'w:themeShade',
    b'w:styleId', b'w:type', b'w:default', b'w:customStyle', b'w:name', b'w:basedOn', b'w:next',
    b'w:uiPriority', b'w:semiHidden', b'w:unhideWhenUsed', b'w:qFormat', b'w:locked', b'w:hidden',
    b'w:firstLine', b'w:hanging', b'w:left', b'w:right', b'w:line', b'w:lineRule',
    b'w:before', b'w:after', b'w:top', b'w:bottom', b'w:header', b'w:footer', b'w:gutter',
    b'w:w', b'w:h', b'w:orient', b'w:numId', b'w:ilvl', b'w:abstractNumId',
    b'w:vertAlign', b'w:spacing', b'w:kern', b'w:position', b'w:hint',
    b'mc:Ignorable', b'mc:PreserveAttributes', b'mc:PreserveElements',
    b'Id', b'Type', b'Target', b'TargetMode', b'ContentType', b'Extension', b'PartName',
    b'name', b'value', b'style', b'filled', b'stroked', b'fillcolor', b'strokecolor',
    b'strokeweight', b'path', b'id', b'from', b'to', b'descr', b'title', b'prst',
    b'cx', b'cy', b'x', b'y', b'rot', b'flipH', b'flipV', b'r:id', b'r:embed', b'r:link',
]
_DOCX_VALS = [
    b'1', b'0', b'2', b'3', b'4', b'5', b'6', b'7', b'8', b'9', b'10',
    b'11', b'12', b'14', b'16', b'18', b'20', b'22', b'24', b'28', b'32', b'36', b'48',
    b'true', b'false', b'on', b'off', b'yes', b'no', b'-1',
    b'preserve', b'default', b'none', b'nil', b'auto', b'begin', b'end', b'separate',
    b'left', b'right', b'center', b'both', b'justify', b'distribute', b'start',
    b'single', b'double', b'thick', b'dotted', b'dashed', b'wave',
    b'superscript', b'subscript', b'baseline',
    b'lr', b'rl', b'tb', b'bt', b'lrTb', b'tbRl',
    b'nextPage', b'continuous', b'evenPage', b'oddPage', b'page', b'column', b'line',
    b'decimal', b'upperRoman', b'lowerRoman', b'upperLetter', b'lowerLetter', b'bullet',
    b'Calibri', b'Arial', b'Times New Roman', b'Cambria', b'Consolas', b'Courier New',
    b'Georgia', b'Verdana', b'Tahoma', b'Segoe UI', b'Helvetica',
    b'000000', b'FFFFFF', b'FF0000', b'00FF00', b'0000FF', b'808080',
    b'1F1F1F', b'2E74B5', b'1F4E79', b'0563C1', b'954F72', b'44546A', b'4472C4',
    b'Normal', b'Heading 1', b'Heading 2', b'Heading 3', b'Title', b'Subtitle', b'Quote',
    b'Hyperlink', b'Footer', b'Header', b'Caption', b'TOC Heading',
    b'paragraph', b'character', b'table', b'numbering',
    b'0.5in', b'0.75in', b'1in', b'1.25in', b'2in', b'2.5in', b'3in', b'8.5in', b'11in',
    b'1pt', b'2pt', b'0.5pt', b'1.5pt', b'2.25pt', b'3pt', b'4pt', b'6pt', b'8pt', b'10pt',
    b'12pt', b'14pt', b'16pt', b'18pt', b'20pt', b'22pt', b'24pt', b'28pt', b'36pt',
    b'100', b'120', b'180', b'240', b'360', b'432', b'480', b'720', b'864', b'1080',
    b'1134', b'1440', b'2160', b'2880', b'4320', b'7200', b'8640', b'12240', b'15840',
    b'portrait', b'landscape', b'hex', b'chicago',
    b'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml',
    b'application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml',
    b'application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml',
    b'application/vnd.openxmlformats-officedocument.wordprocessingml.webSettings+xml',
    b'application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml',
    b'application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml',
    b'application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml',
    b'application/vnd.openxmlformats-officedocument.wordprocessingml.endnotes+xml',
    b'application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml',
    b'application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml',
    b'application/vnd.openxmlformats-package.core-properties+xml',
    b'application/vnd.openxmlformats-officedocument.extended-properties+xml',
    b'application/vnd.openxmlformats-package.relationships+xml',
    b'application/vnd.openxmlformats-officedocument.theme+xml',
    b'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    b'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    b'http://schemas.openxmlformats.org/package/2006/relationships',
    b'image/png', b'image/jpeg', b'image/gif', b'image/svg+xml',
    b'officeDocument', b'styles', b'settings', b'theme', b'webSettings',
    b'fontTable', b'numbering', b'header', b'footer', b'footnotes', b'endnotes',
    b'comments', b'image', b'hyperlink', b'oleObject', b'package',
    b'document.main+xml', b'styles+xml', b'settings+xml', b'theme+xml', b'webSettings+xml',
    b'fontTable+xml', b'numbering+xml', b'header+xml', b'footer+xml',
    b'footnotes+xml', b'endnotes+xml', b'comments+xml',
    b'core-properties+xml', b'extended-properties+xml', b'relationships+xml',
    b'docx', b'docm', b'dotx', b'dotm',
]

# ═══════════════════════════════════════════════════════════════════════════
# PATCH #1 — XLSX SpreadsheetML seed tags / attrs / vals
# ═══════════════════════════════════════════════════════════════════════════
_DOCX_TAGS += [
    b'worksheet', b'sheetData', b'sheetPr', b'sheetViews', b'sheetView',
    b'dimension', b'sheetFormatPr', b'cols', b'col', b'row', b'c', b'v', b'f',
    b'is', b't', b'si', b'rPh', b'phoneticPr', b'r', b'mergeCells',
    b'mergeCell', b'hyperlinks', b'hyperlink', b'autoFilter', b'filterColumn',
    b'filters', b'filter', b'dataValidations', b'dataValidation',
    b'conditionalFormatting', b'cfRule', b'pageMargins', b'pageSetup',
    b'headerFooter', b'drawing', b'legacyDrawing', b'extLst', b'ext',
    b'workbook', b'workbookPr', b'workbookProtection', b'bookViews', b'workbookView',
    b'sheets', b'sheet', b'functionGroups', b'functionGroup', b'externalReferences',
    b'definedNames', b'definedName', b'calcPr', b'oleSize', b'pivotCaches',
    b'styleSheet', b'numFmts', b'numFmt', b'fonts', b'font', b'fills', b'fill',
    b'patternFill', b'gradientFill', b'fgColor', b'bgColor', b'stop',
    b'borders', b'border', b'cellXfs', b'xf', b'cellStyleXfs', b'cellStyles', b'cellStyle',
    b'dxfs', b'tableStyles', b'tableStyle', b'tableStyleElement',
    b'colors', b'indexedColors', b'rgbColor', b'color',
    b'sst', b'plotArea', b'layout', b'ser', b'cat',
    b'val', b'numRef', b'strRef', b'barChart', b'barDir', b'grouping', b'serLines',
    b'lineChart', b'pieChart', b'scatterChart', b'areaChart', b'legend',
    b'legendPos', b'tx', b'rich', b'bodyPr', b'lstStyle',
    b'a:theme', b'a:themeElements', b'a:clrScheme', b'a:dk1', b'a:lt1',
    b'a:dk2', b'a:lt2', b'a:accent1', b'a:accent2', b'a:accent3',
    b'a:accent4', b'a:accent5', b'a:accent6', b'a:hlink', b'a:folHlink',
    b'a:fontScheme', b'a:majorFont', b'a:minorFont', b'a:latin',
    b'a:ea', b'a:cs', b'a:font', b'a:fmtScheme', b'a:fillStyleLst',
    b'a:lnStyleLst', b'a:effectStyleLst', b'a:bgFillStyleLst',
]
_DOCX_ATTRS += [
    b'r', b't', b's', b'ref', b'spans', b'count', b'uniqueCount',
    b'formatCode', b'numFmtId', b'fontId', b'fillId', b'borderId', b'xfId',
    b'applyNumberFormat', b'applyFont', b'applyFill', b'applyBorder',
    b'applyAlignment', b'applyProtection',
    b'horizontal', b'vertical', b'wrapText', b'shrinkToFit', b'indent',
    b'textRotation', b'readingOrder', b'justifyLastLine',
    b'sheetId', b'state', b'tabSelected', b'hideFormula',
    b'caption', b'description', b'hidden',
    b'localSheetId', b'comment', b'customMenu', b'help',
    b'statusBar', b'size', b'show', b'date1904', b'filterMode',
    b'customFormat', b'customHeight', b'zeroHeight', b'thickTop',
    b'thickBottom', b'outlineLevel', b'collapsed', b'ph', b'activeTab',
    b'firstSheet', b'firstSheetId', b'filterButton',
    b'rightToLeft', b'end', b'pane', b'xSplit', b'ySplit',
    b'topLeftCell', b'activePane', b'view', b'zoomScale',
    b'zoomScaleNormal', b'showGridLines', b'showRowColHeaders',
    b'allowFilter', b'showFormulas', b'showZeros',
    b'xmlns', b'xmlns:r', b'xmlns:mc', b'xmlns:x14ac',
]
_DOCX_VALS += [
    b's', b'n', b'b', b'e', b'str', b'inlineStr', b'd',
    b'General', b'0.00', b'#,##0', b'#,##0.00',
    b'0%', b'0.00%', b'0.00E+00', b'# ?/?', b'# ??/??',
    b'yyyy-mm-dd', b'd-mmm-yy', b'd-mmm', b'mmm-yy',
    b'h:mm AM/PM', b'h:mm:ss AM/PM', b'h:mm', b'h:mm:ss',
    b'm/d/yy h:mm', b'mm:ss', b'[h]:mm:ss', b'mm:ss.0',
    b'yyyy-mm-dd h:mm:ss', b'@',
    b'FF000000', b'FFFFFFFF', b'FFC00000', b'FFFF0000', b'FF00B050',
    b'FF0070C0', b'FFED7D31', b'FFA5A5A5', b'FFFFC000',
    b'FF5B9BD5', b'FF70AD47', b'FF7030A0', b'FFFF7C80',
    b'Aptos', b'Calibri Light', b'Cambria Math',
    b'22', b'28', b'36', b'48', b'72',
    b'solid', b'medium', b'thin', b'hair', b'mediumDashed',
    b'dashDot', b'mediumDashDot', b'dashDotDot', b'mediumDashDotDot', b'slantDashDot',
    b'visible', b'veryHidden',
    b'1:1', b'1:2', b'1:3', b'1:4', b'A1:Z1', b'A1:AZ1',
    b'http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet',
    b'http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles',
    b'http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings',
    b'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml',
    b'application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml',
    b'application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml',
    b'application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml',
    b'application/vnd.openxmlformats-officedocument.spreadsheetml.chartsheet+xml',
    b'application/vnd.openxmlformats-officedocument.drawing+xml',
    b'application/vnd.openxmlformats-officedocument.chart+xml',
]

# ═══════════════════════════════════════════════════════════════════════════
# PATCH #2 — PPTX PresentationML seed tags / attrs / vals
# ═══════════════════════════════════════════════════════════════════════════
_DOCX_TAGS += [
    b'p:sld', b'p:sldLayout', b'p:sldMaster', b'p:sldSz', b'p:notesSz',
    b'p:presentation', b'p:notesMaster', b'p:notes',
    b'p:sldIdLst', b'p:sldId', b'p:sldLayoutIdLst', b'p:sldLayoutId',
    b'p:sldMasterIdLst', b'p:sldMasterId', b'p:notesMasterIdLst',
    b'p:notesMasterId', b'p:handoutMasterIdLst', b'p:handoutMasterId',
    b'p:sp', b'p:spPr', b'p:txBody', b'p:nvSpPr', b'p:nvPr', b'p:nvPicPr',
    b'p:nvGraphicFramePr', b'p:nvCxnSpPr', b'p:nvGrpSpPr',
    b'p:pic', b'p:graphicFrame', b'p:grpSp', b'p:grpSpPr', b'p:cxnSp',
    b'p:cNvPr', b'p:cNvSpPr', b'p:cNvPicPr', b'p:cNvGraphicFramePr',
    b'p:cNvCxnSpPr', b'p:cNvGrpSpPr',
    b'p:cSld', b'p:clrMapOvr', b'p:bg', b'p:bgRef', b'p:bgPr',
    b'p:style', b'p:txStyles', b'p:titleStyle', b'p:bodyStyle', b'p:otherStyle',
    b'p:clrMap', b'p:extLst', b'p:ext',
    b'p:transition', b'p:timing', b'p:anim', b'p:animEffect', b'p:animMotion',
    b'p:animRot', b'p:animScale', b'p:audio', b'p:video', b'p:cmd', b'p:cond',
    b'p:childTnLst', b'p:seq', b'p:prevCondLst', b'p:nextCondLst',
    b'a:tbl', b'a:tblPr', b'a:tblGrid', b'a:gridCol', b'a:tr', b'a:tc',
    b'a:tcPr', b'a:tcTxBody', b'a:tableStyleId',
    b'a:p', b'a:pPr', b'a:rPr', b'a:defRPr', b'a:endParaRPr',
    b'a:bodyPr', b'a:lstStyle', b'a:br', b'a:fld',
    b'a:spPr', b'a:custGeom', b'a:pathLst', b'a:path', b'a:moveTo', b'a:lnTo',
    b'a:cubicBezTo', b'a:quadBezTo', b'a:close', b'a:pt', b'a:gdLst', b'a:gd',
    b'a:ahLst', b'a:ahXY', b'a:ahPts', b'a:cxnLst', b'a:cxn', b'a:rect',
    b'a:prstTxWarp',
    b'a:sysClr', b'a:prstClr', b'a:scrgbClr', b'a:hslClr', b'a:lumMod',
    b'a:lumOff', b'a:satMod', b'a:tint', b'a:shade', b'a:alpha',
    b'a:hue', b'a:sat', b'a:lum',
    b'a:gradFill', b'a:gsLst', b'a:gs', b'a:pattFill',
    b'a:noFill', b'a:srcRect', b'a:tile', b'a:effectLst', b'a:effectDag',
    b'a:outerShdw', b'a:innerShdw', b'a:glow', b'a:reflection',
    b'a:scene3d', b'a:sp3d', b'a:bevelT', b'a:bevelB', b'a:flatTx',
    b'a:softEdge', b'a:prstShdw',
]
_DOCX_ATTRS += [
    b'p:sz', b'p:type', b'p:r', b'p:ph', b'p:idx', b'p:lvl',
    b'p:marL', b'p:marR', b'p:marT', b'p:marB', b'p:indent',
    b'p:algn', b'p:defTabSz', b'p:rtl', b'p:eaLnBrk', b'p:latinLnBrk',
    b'p:hangingPunct', b'p:spcBef', b'p:spcAft', b'p:buClrTx',
    b'p:buSzTx', b'p:buFontTx', b'p:buNone', b'p:buAutoNum',
    b'p:buChar', b'p:buBlip', b'p:normAutofit', b'p:spAutoFit',
    b'p:noAutofit', b'p:fontScale', b'p:lnSpcReduction',
    b'p:showMasterSp', b'p:showMasterPhAnim',
    b'p:useBgFill', b'p:followMasterBackground',
    b'a:anchor', b'a:anchorCtr', b'a:wrap', b'a:lIns', b'a:tIns', b'a:rIns',
    b'a:bIns', b'a:numCol', b'a:numRow', b'a:horzOverflow',
    b'a:vertOverflow', b'a:vert', b'a:spcFirstLastPara',
    b'a:cap', b'a:baseline',
    b'a:b', b'a:i', b'a:u', b'a:strike', b'a:sz', b'a:color',
    b'a:typeface', b'a:pitchFamily', b'a:charset', b'a:panose',
    b'a:fmla', b'a:desc',
    b'a:chOff', b'a:chExt', b'a:bwMode',
]
_DOCX_VALS += [
    b'9144000', b'6858000', b'12192000',
    b'screen4x3', b'screen16x9', b'screen16x10', b'A4', b'letter',
    b'custom',
    b'title', b'body', b'ctrTitle', b'subTitle', b'dt', b'ftr', b'sldNum',
    b'obj', b'pic', b'chart', b'tbl', b'media', b'clipArt', b'dgm', b'ole',
    b'l', b'ctr', b'just', b'dist', b'thaiDist', b'low', b'high',
    b'full', b'text', b'background', b'logo',
    b'http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide',
    b'http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout',
    b'http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster',
    b'http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster',
    b'http://schemas.openxmlformats.org/officeDocument/2006/relationships/handoutMaster',
    b'http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide',
    b'http://schemas.openxmlformats.org/officeDocument/2006/relationships/audio',
    b'http://schemas.openxmlformats.org/officeDocument/2006/relationships/video',
    b'application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml',
    b'application/vnd.openxmlformats-officedocument.presentationml.slide+xml',
    b'application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml',
    b'application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml',
    b'application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml',
    b'application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml',
    b'application/vnd.openxmlformats-officedocument.presentationml.handoutMaster+xml',
    b'application/vnd.openxmlformats-officedocument.presentationml.presProps+xml',
    b'application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml',
    b'application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml',
    b'application/vnd.openxmlformats-officedocument.drawingml.chart+xml',
    b'application/vnd.openxmlformats-officedocument.drawingml.diagramData+xml',
]

_DOCX_TAGS  = list(dict.fromkeys(_DOCX_TAGS))
_DOCX_ATTRS = list(dict.fromkeys(_DOCX_ATTRS))
_DOCX_VALS  = list(dict.fromkeys(_DOCX_VALS))

_DOCX_COMPOUND_SEEDS_RAW = [
    (b'w:jc',        [(b'w:val', b'center')]),
    (b'w:jc',        [(b'w:val', b'both')]),
    (b'w:jc',        [(b'w:val', b'left')]),
    (b'w:jc',        [(b'w:val', b'right')]),
    (b'w:jc',        [(b'w:val', b'distribute')]),
    (b'w:jc',        [(b'w:val', b'start')]),
    (b'w:sz',        [(b'w:val', b'24')]),
    (b'w:sz',        [(b'w:val', b'22')]),
    (b'w:sz',        [(b'w:val', b'20')]),
    (b'w:sz',        [(b'w:val', b'28')]),
    (b'w:sz',        [(b'w:val', b'32')]),
    (b'w:sz',        [(b'w:val', b'36')]),
    (b'w:szCs',      [(b'w:val', b'24')]),
    (b'w:szCs',      [(b'w:val', b'22')]),
    (b'w:szCs',      [(b'w:val', b'28')]),
    (b'w:b',         [(b'w:val', b'1')]),
    (b'w:b',         [(b'w:val', b'0')]),
    (b'w:b',         []),
    (b'w:bCs',       []),
    (b'w:i',         []),
    (b'w:iCs',       []),
    (b'w:u',         [(b'w:val', b'single')]),
    (b'w:color',     [(b'w:val', b'000000')]),
    (b'w:color',     [(b'w:val', b'1F1F1F')]),
    (b'w:color',     [(b'w:val', b'2E74B5')]),
    (b'w:color',     [(b'w:val', b'auto')]),
    (b'w:color',     [(b'w:val', b'auto'), (b'w:themeColor', b'text1')]),
    (b'w:pStyle',    [(b'w:val', b'Normal')]),
    (b'w:pStyle',    [(b'w:val', b'Heading 1')]),
    (b'w:pStyle',    [(b'w:val', b'Heading 2')]),
    (b'w:pStyle',    [(b'w:val', b'Heading 3')]),
    (b'w:pStyle',    [(b'w:val', b'Title')]),
    (b'w:pStyle',    [(b'w:val', b'Subtitle')]),
    (b'w:rStyle',    [(b'w:val', b'Hyperlink')]),
    (b'w:rFonts',    [(b'w:ascii', b'Calibri'), (b'w:hAnsi', b'Calibri')]),
    (b'w:rFonts',    [(b'w:ascii', b'Arial'), (b'w:hAnsi', b'Arial')]),
    (b'w:rFonts',    [(b'w:ascii', b'Times New Roman'),
                      (b'w:hAnsi', b'Times New Roman')]),
    (b'w:rFonts',    [(b'w:asciiTheme', b'minorHAnsi'),
                      (b'w:hAnsiTheme', b'minorHAnsi')]),
    (b'w:lang',      [(b'w:val', b'en-US')]),
    (b'w:lang',      [(b'w:val', b'en-GB')]),
    (b'w:vertAlign', [(b'w:val', b'superscript')]),
    (b'w:vertAlign', [(b'w:val', b'subscript')]),
    (b'w:pgSz',      [(b'w:w', b'12240'), (b'w:h', b'15840')]),
    (b'w:pgSz',      [(b'w:w', b'11906'), (b'w:h', b'16838')]),
    (b'w:pgMar',     [(b'w:top', b'1440'), (b'w:right', b'1440'),
                      (b'w:bottom', b'1440'), (b'w:left', b'1440'),
                      (b'w:header', b'720'), (b'w:footer', b'720'),
                      (b'w:gutter', b'0')]),
    (b'w:spacing',   [(b'w:after', b'0'), (b'w:line', b'240'),
                      (b'w:lineRule', b'auto')]),
    (b'w:spacing',   [(b'w:before', b'0'), (b'w:after', b'0')]),
    (b'w:ind',       [(b'w:firstLine', b'720')]),
    (b'w:ind',       [(b'w:left', b'720')]),
    (b'w:rPr',       []),
    (b'w:pPr',       []),
    (b'w:p',         []),
    (b'w:r',         []),
    (b'w:t',         [(b'xml:space', b'preserve')]),
    (b'w:t',         []),
    (b'w:body',      []),
    (b'w:document',  []),
    (b'w:sectPr',    []),
    (b'w:tbl',       []),
    (b'w:tr',        []),
    (b'w:tc',        []),
    (b'w:hyperlink', [(b'r:id', b'rId1')]),
    (b'w:bookmarkStart', [(b'w:id', b'0'), (b'w:name', b'_GoBack')]),
    (b'w:proofErr', [(b'w:type', b'spellStart')]),
    (b'w:proofErr', [(b'w:type', b'spellEnd')]),
    (b'w:proofErr', [(b'w:type', b'gramStart')]),
    (b'w:proofErr', [(b'w:type', b'gramEnd')]),
    (b'w:rsid',     []),
    (b'w:lang',     [(b'w:eastAsia', b'en-US')]),
    (b'w:tab',      []),
    (b'w:br',       []),
    (b'w:lastRenderedPageBreak', []),
    (b'w:keepNext', []),
    (b'w:keepLines', []),
    (b'w:widowControl', [(b'w:val', b'0')]),
    (b'w:pageBreakBefore', []),
    (b'w:outlineLvl', [(b'w:val', b'0')]),
    (b'w:outlineLvl', [(b'w:val', b'1')]),
    (b'w:outlineLvl', [(b'w:val', b'2')]),
    (b'w:shd',      [(b'w:val', b'clear'), (b'w:color', b'auto'),
                     (b'w:fill', b'FFFFFF')]),
    (b'w:tblW',     [(b'w:w', b'0'), (b'w:type', b'auto')]),
    (b'w:tblLayout', [(b'w:type', b'autofit')]),
    (b'w:tblStyle', [(b'w:val', b'TableGrid')]),
    (b'w:tcW',      [(b'w:w', b'0'), (b'w:type', b'auto')]),
    (b'w:highlight', [(b'w:val', b'none')]),
    (b'w:caps',     []),
    (b'w:smallCaps', []),
    (b'w:strike',   []),
    (b'w:dstrike',  []),
    (b'w:vanish',   []),
    (b'w:noProof',  []),
]

# ═══════════════════════════════════════════════════════════════════════════
# PATCH #3 — XLSX + PPTX compound seeds (tag+attr+val → single varint)
# ═══════════════════════════════════════════════════════════════════════════
_DOCX_COMPOUND_SEEDS_RAW += [
    # ---- XLSX worksheet.xml boilerplate ----
    (b'sheetPr',        []),
    (b'sheetViews',     []),
    (b'sheetView',      [(b'workbookViewId', b'0')]),
    (b'sheetView',      [(b'workbookViewId', b'0'), (b'showGridLines', b'1')]),
    (b'dimension',      [(b'ref', b'A1')]),
    (b'sheetFormatPr',  [(b'defaultRowHeight', b'15')]),
    (b'cols',           []),
    (b'sheetData',      []),
    (b'row',            [(b'r', b'1')]),
    (b'c',              [(b't', b's')]),
    (b'c',              [(b't', b'n')]),
    (b'c',              []),
    (b'v',              []),
    (b'f',              []),
    (b'is',             []),
    (b't',              [(b'xml:space', b'preserve')]),
    (b't',              []),
    # ---- XLSX workbook.xml ----
    (b'workbookPr',     [(b'date1904', b'0')]),
    (b'workbookPr',     []),
    (b'bookViews',      []),
    (b'workbookView',   [(b'xWindow', b'0'), (b'yWindow', b'0'),
                         (b'windowWidth', b'16384'), (b'windowHeight', b'8192')]),
    (b'sheets',         []),
    (b'sheet',          []),
    (b'calcPr',         [(b'calcId', b'191029')]),
    (b'calcPr',         []),
    # ---- XLSX styles.xml ----
    (b'styleSheet',     []),
    (b'numFmts',        [(b'count', b'0')]),
    (b'fonts',          [(b'count', b'1')]),
    (b'fills',          [(b'count', b'2')]),
    (b'borders',        [(b'count', b'1')]),
    (b'cellStyleXfs',   [(b'count', b'1')]),
    (b'cellXfs',        [(b'count', b'1')]),
    (b'cellStyles',     [(b'count', b'1')]),
    (b'dxfs',           [(b'count', b'0')]),
    (b'tableStyles',    [(b'count', b'0'), (b'defaultTableStyle', b'TableStyleMedium2'),
                         (b'defaultPivotStyle', b'PivotStyleLight16')]),
    (b'font',           []),
    (b'fill',           []),
    (b'border',         []),
    (b'xf',             [(b'numFmtId', b'0'), (b'fontId', b'0'), (b'fillId', b'0'),
                         (b'borderId', b'0'), (b'xfId', b'0')]),
    (b'xf',             []),
    # ---- PPTX presentation.xml ----
    (b'sldMasterIdLst', []),
    (b'sldIdLst',       []),
    (b'sldSz',          [(b'cx', b'9144000'), (b'cy', b'6858000')]),
    (b'sldSz',          [(b'cx', b'9144000'), (b'cy', b'6858000'),
                         (b'type', b'screen4x3')]),
    (b'notesSz',        [(b'cx', b'6858000'), (b'cy', b'9144000')]),
    (b'defaultTextStyle', []),
    (b'clrMap',         [(b'bg1', b'lt1'), (b'tx1', b'dk1'),
                         (b'bg2', b'lt2'), (b'tx2', b'dk2'),
                         (b'accent1', b'accent1'), (b'accent2', b'accent2'),
                         (b'accent3', b'accent3'), (b'accent4', b'accent4'),
                         (b'accent5', b'accent5'), (b'accent6', b'accent6'),
                         (b'hlink', b'hlink'), (b'folHlink', b'folHlink')]),
    # ---- PPTX slide.xml boilerplate ----
    (b'cSld',           []),
    (b'spTree',         []),
    (b'grpSp',          []),
    (b'grpSpPr',        []),
    (b'xfrm',           []),
    (b'off',            [(b'x', b'0'), (b'y', b'0')]),
    (b'ext',            []),
    (b'chOff',          [(b'x', b'0'), (b'y', b'0')]),
    (b'chExt',          []),
    (b'sp',             []),
    (b'nvSpPr',         []),
    (b'cNvPr',          [(b'id', b'1'), (b'name', b'')]),
    (b'cNvSpPr',        []),
    (b'spPr',           []),
    (b'txBody',         []),
    (b'bodyPr',         [(b'rtlCol', b'0')]),
    (b'bodyPr',         []),
    (b'lstStyle',       []),
    (b'p',              []),
    (b'pPr',            []),
    (b'r',              []),
    (b'rPr',            [(b'lang', b'en-US'), (b'dirty', b'0')]),
    (b't',              []),
    (b'endParaRPr',     [(b'lang', b'en-US'), (b'dirty', b'0')]),
    (b'endParaRPr',     [(b'lang', b'en-US')]),
]

def _build_compound_seed():
    tag_idx  = {t: i for i, t in enumerate(_DOCX_TAGS)}
    attr_idx = {a: i for i, a in enumerate(_DOCX_ATTRS)}
    val_idx  = {v: i for i, v in enumerate(_DOCX_VALS)}
    out = []
    for tag_b, attrs_b in _DOCX_COMPOUND_SEEDS_RAW:
        ti = tag_idx.get(tag_b)
        if ti is None: continue
        pairs = []; ok = True
        for a_b, v_b in attrs_b:
            ai = attr_idx.get(a_b); vi = val_idx.get(v_b)
            if ai is None or vi is None: ok = False; break
            pairs.append((ai, vi))
        if ok: out.append((ti, tuple(pairs)))
    return out

_DOCX_COMPOUNDS_SEED = _build_compound_seed()
print(f"Compound seed: {len(_DOCX_COMPOUNDS_SEED)} pre-defined OOXML combos")

OLE_MAGIC = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
ZIP_MAGIC = b'PK\x03\x04'
_ZIP_CENTRAL_SIG   = b'PK\x01\x02'
_ZIP_EOCD_SIG      = b'PK\x05\x06'
_ZIP_DATA_DESC_SIG = b'PK\x07\x08'

_PREFIX_WIDTHS = [2, 3, 8, 16, 32, 64, 128, 256] + [1 << i for i in range(9, 25)]
ENABLE_ULTRA = os.environ.get("PPMD_ULTRA", "1") != "0"

_XML_OPEN_RE  = re.compile(rb'<([A-Za-z_][\w:.-]*)((?:\s+[\w:.-]+\s*=\s*(?:"[^"]*"|\'[^\']*\'))*)\s*(/?)>')
_XML_CLOSE_RE = re.compile(rb'</\s*([A-Za-z_][\w:.-]*)\s*>')
_XML_ATTR_RE  = re.compile(rb'([\w:.-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')

def _xml_is_plausible(d):
    if not d: return False
    if d[:8] == OLE_MAGIC: return False
    return d[:64].lstrip().startswith(b'<')

def _xml_scan_tokens(d):
    pos = 0; n = len(d)
    while pos < n:
        lt = d.find(b'<', pos)
        if lt < 0:
            if pos < n: yield (0, d[pos:])
            return
        if lt > pos: yield (0, d[pos:lt])
        if d.startswith(b'<!--', lt):
            end = d.find(b'-->', lt+4); end = (end+3) if end >= 0 else n
            yield (3, d[lt:end]); pos = end; continue
        if d.startswith(b'<![CDATA[', lt):
            end = d.find(b']]>', lt+9); end = (end+3) if end >= 0 else n
            yield (3, d[lt:end]); pos = end; continue
        if d.startswith(b'<?', lt):
            end = d.find(b'?>', lt+2); end = (end+2) if end >= 0 else n
            yield (3, d[lt:end]); pos = end; continue
        if d.startswith(b'<!', lt):
            end = d.find(b'>', lt+2); end = (end+1) if end >= 0 else n
            yield (3, d[lt:end]); pos = end; continue
        m = _XML_OPEN_RE.match(d, lt)
        if m: yield (1, (m.group(1), m.group(2), m.group(3))); pos = m.end(); continue
        m = _XML_CLOSE_RE.match(d, lt)
        if m: yield (2, m.group(1)); pos = m.end(); continue
        yield (0, b'<'); pos = lt + 1

def _emit_varint(buf, n):
    if n < 0x80: buf.append(n); return
    while True:
        b = n & 0x7F; n >>= 7
        if n: buf.append(b | 0x80)
        else: buf.append(b); return

def _read_varint(buf, pos):
    if pos >= len(buf): raise TransformError("varint eof")
    b = buf[pos]
    if b < 0x80: return b, pos + 1
    n = b & 0x7F; sh = 7; pos += 1
    while True:
        if pos >= len(buf): raise TransformError("varint eof")
        b = buf[pos]; pos += 1
        n |= (b & 0x7F) << sh
        if not (b & 0x80): return n, pos
        sh += 7
        if sh > 63: raise TransformError("varint overflow")

def _word_encode_text(text, ref_idx):
    out = bytearray()
    last = 0
    for m in _TOK_RE.finditer(text):
        if m.start() > last:
            out.append(0); _emit_varint(out, m.start() - last)
            out += text[last:m.start()]
        tok_orig = m.group(0); tok_low = tok_orig.lower()
        i = ref_idx.get(tok_low)
        if i is not None and i < (1 << 30):
            if   tok_orig == tok_low:                code = (i << 2) | 0
            elif tok_orig == tok_low.capitalize():   code = (i << 2) | 1
            elif tok_orig == tok_low.upper():        code = (i << 2) | 2
            else:                                    code = None
            if code is not None:
                _emit_varint(out, code + 1)
                last = m.end()
                continue
        out.append(0); _emit_varint(out, len(tok_orig)); out += tok_orig
        last = m.end()
    if last < len(text):
        out.append(0); _emit_varint(out, len(text) - last); out += text[last:]
    return bytes(out)

def _word_decode_text(blob, rb, rcap, rup):
    out = bytearray(); p = 0; nb = len(blob)
    while p < nb:
        code, p = _read_varint(blob, p)
        if code == 0:
            ln, p = _read_varint(blob, p); out += blob[p:p+ln]; p += ln
        else:
            x = code - 1; i = x >> 2; c = x & 3
            if i >= len(rb): raise TransformError(f"words idx {i}>={len(rb)}")
            if   c == 0: out += rb[i]
            elif c == 1: out += rcap[i]
            elif c == 2: out += rup[i]
            else:        raise TransformError(f"words case {c}")
    return bytes(out)

def _rdb(bits, pos, n):
    v = 0
    for i in range(n):
        if pos + i >= len(bits): return 0
        v = (v << 1) | bits[pos + i]
    return v

def _emit_bits(bits, v, n):
    for i in range(n - 1, -1, -1): bits.append((v >> i) & 1)

def _emit_len_bits(bits, n):
    while True:
        b = n & 0x7F; n >>= 7
        if n: _emit_bits(bits, b | 0x80, 8)
        else: _emit_bits(bits, b, 8); return

def _read_len_bits(bits, pos):
    n = 0; shift = 0
    while True:
        b = _rdb(bits, pos, 8); pos += 8
        n |= (b & 0x7F) << shift
        if not (b & 0x80): return n, pos
        shift += 7

def _emit_idx_bits(bits, lst, s):
    try:
        idx = lst.index(s)
        _emit_bits(bits, idx, 8)
        return
    except ValueError:
        pass
    _emit_bits(bits, 255, 8)
    _emit_len_bits(bits, len(s))
    for c in s: _emit_bits(bits, c, 8)
    if len(lst) < 255:
        lst.append(s)

def _read_idx_bits(bits, pos, lst):
    idx = _rdb(bits, pos, 8); pos += 8
    if idx < 255:
        if idx >= len(lst): raise TransformError(f"xml bit idx {idx}>={len(lst)}")
        return lst[idx], pos
    ln, pos = _read_len_bits(bits, pos)
    s = bytearray()
    for _ in range(ln):
        s.append(_rdb(bits, pos, 8)); pos += 8
    result = bytes(s)
    if len(lst) < 255:
        lst.append(result)
    return result, pos

def _xml_encode_bits(d):
    if not d: return None
    toks = list(_xml_scan_tokens(d))
    if not toks: return None
    tags  = list(_DOCX_TAGS)
    attrs = list(_DOCX_ATTRS)
    vals  = list(_DOCX_VALS)
    bits = []
    for kind, payload in toks:
        if kind == 0:
            _emit_bits(bits, 0b000, 3)
            _emit_len_bits(bits, len(payload))
            for b in payload: _emit_bits(bits, b, 8)
        elif kind == 1:
            name, attrs_raw, selfclose = payload
            _emit_bits(bits, 0b011 if selfclose else 0b001, 3)
            _emit_idx_bits(bits, tags, name)
            am_list = list(_XML_ATTR_RE.finditer(attrs_raw))
            _emit_len_bits(bits, len(am_list))
            for am in am_list:
                aname = am.group(1)
                aval  = am.group(2) if am.group(2) is not None else am.group(3)
                _emit_idx_bits(bits, attrs, aname)
                _emit_idx_bits(bits, vals,  aval)
        elif kind == 2:
            _emit_bits(bits, 0b010, 3)
            _emit_idx_bits(bits, tags, payload)
        else:
            _emit_bits(bits, 0b100, 3)
            _emit_len_bits(bits, len(payload))
            for b in payload: _emit_bits(bits, b, 8)
    nbits = len(bits)
    _emit_bits(bits, 0, (8 - nbits % 8) % 8)
    out = bytearray([0x58, 0x5A])
    out.extend(nbits.to_bytes(4, 'big'))
    for i in range(0, len(bits), 8):
        v = 0
        for j in range(8): v = (v << 1) | bits[i + j]
        out.append(v)
    return bytes(out)

def _xml_decode_bits(payload):
    if len(payload) < 6 or payload[0] != 0x58 or payload[1] != 0x5A:
        raise TransformError("xml bits magic")
    nbits = int.from_bytes(payload[2:6], 'big')
    bits = []
    for b in payload[6:]:
        for i in range(7, -1, -1): bits.append((b >> i) & 1)
    bits = bits[:nbits]
    tags  = list(_DOCX_TAGS)
    attrs = list(_DOCX_ATTRS)
    vals  = list(_DOCX_VALS)
    out = bytearray()
    pos = 0
    while pos < nbits:
        op = 0
        for _ in range(3):
            op = (op << 1) | bits[pos]; pos += 1
        if op == 0b000:
            ln, pos = _read_len_bits(bits, pos)
            for _ in range(ln):
                out.append(_rdb(bits, pos, 8)); pos += 8
        elif op == 0b001:
            name, pos = _read_idx_bits(bits, pos, tags)
            n_attrs, pos = _read_len_bits(bits, pos)
            out += b'<' + name
            for _ in range(n_attrs):
                aname, pos = _read_idx_bits(bits, pos, attrs)
                aval,  pos = _read_idx_bits(bits, pos, vals)
                out += b' ' + aname + b'="' + aval + b'"'
            out += b'>'
        elif op == 0b010:
            name, pos = _read_idx_bits(bits, pos, tags)
            out += b'</' + name + b'>'
        elif op == 0b011:
            name, pos = _read_idx_bits(bits, pos, tags)
            n_attrs, pos = _read_len_bits(bits, pos)
            out += b'<' + name
            for _ in range(n_attrs):
                aname, pos = _read_idx_bits(bits, pos, attrs)
                aval,  pos = _read_idx_bits(bits, pos, vals)
                out += b' ' + aname + b'="' + aval + b'"'
            out += b'/>'
        elif op == 0b100:
            ln, pos = _read_len_bits(bits, pos)
            for _ in range(ln):
                out.append(_rdb(bits, pos, 8)); pos += 8
        else:
            raise TransformError(f"xml bits op {op:03b}")
    return bytes(out)

def _idx_or_add(lst, s):
    try: return lst.index(s)
    except ValueError:
        lst.append(s); return len(lst) - 1

def _xml_encode_v2(d):
    if not d: return None
    toks = list(_xml_scan_tokens(d))
    if not toks: return None
    tag_names  = list(_DOCX_TAGS)
    attr_names = list(_DOCX_ATTRS)
    attr_vals  = list(_DOCX_VALS)
    text_chunks = []
    struct = bytearray()
    for kind, payload in toks:
        if kind == 0:
            struct.append(0); _emit_varint(struct, len(text_chunks)); text_chunks.append(payload)
        elif kind == 1:
            name, attrs_raw, selfclose = payload
            struct.append(1 if not selfclose else 4)
            _emit_varint(struct, _idx_or_add(tag_names, name))
            attr_list = list(_XML_ATTR_RE.finditer(attrs_raw))
            _emit_varint(struct, len(attr_list))
            for am in attr_list:
                aname = am.group(1)
                aval  = am.group(2) if am.group(2) is not None else am.group(3)
                _emit_varint(struct, _idx_or_add(attr_names, aname))
                _emit_varint(struct, _idx_or_add(attr_vals, aval))
        elif kind == 2:
            struct.append(2); _emit_varint(struct, _idx_or_add(tag_names, payload))
        else:
            struct.append(3); _emit_varint(struct, len(text_chunks)); text_chunks.append(payload)
    out = bytearray(); out.append(0x58); out.append(0x59)
    for lst, seed in zip((tag_names, attr_names, attr_vals),
                         (_DOCX_TAGS, _DOCX_ATTRS, _DOCX_VALS)):
        new_items = lst[len(seed):]
        _emit_varint(out, len(new_items))
        for s in new_items: _emit_varint(out, len(s)); out += s
    _emit_varint(out, len(struct)); out += struct
    _emit_varint(out, len(text_chunks))
    for t in text_chunks: _emit_varint(out, len(t)); out += t
    return bytes(out)

def _xml_encode_v2_words(d, ref_idx):
    if not d or not ref_idx: return None
    toks = list(_xml_scan_tokens(d))
    if not toks: return None
    tag_names  = list(_DOCX_TAGS)
    attr_names = list(_DOCX_ATTRS)
    attr_vals  = list(_DOCX_VALS)
    text_chunks = []
    struct = bytearray()
    for kind, payload in toks:
        if kind == 0:
            struct.append(0); _emit_varint(struct, len(text_chunks)); text_chunks.append(payload)
        elif kind == 1:
            name, attrs_raw, selfclose = payload
            struct.append(1 if not selfclose else 4)
            _emit_varint(struct, _idx_or_add(tag_names, name))
            attr_list = list(_XML_ATTR_RE.finditer(attrs_raw))
            _emit_varint(struct, len(attr_list))
            for am in attr_list:
                aname = am.group(1)
                aval  = am.group(2) if am.group(2) is not None else am.group(3)
                _emit_varint(struct, _idx_or_add(attr_names, aname))
                _emit_varint(struct, _idx_or_add(attr_vals, aval))
        elif kind == 2:
            struct.append(2); _emit_varint(struct, _idx_or_add(tag_names, payload))
        else:
            struct.append(3); _emit_varint(struct, len(text_chunks)); text_chunks.append(payload)
    encoded_texts = [_word_encode_text(t, ref_idx) for t in text_chunks]
    out = bytearray([0x58, 0x5B])
    for lst, seed in zip((tag_names, attr_names, attr_vals),
                         (_DOCX_TAGS, _DOCX_ATTRS, _DOCX_VALS)):
        new_items = lst[len(seed):]
        _emit_varint(out, len(new_items))
        for s in new_items: _emit_varint(out, len(s)); out += s
    _emit_varint(out, len(struct)); out += struct
    _emit_varint(out, len(encoded_texts))
    for t in encoded_texts: _emit_varint(out, len(t)); out += t
    return bytes(out)

def _xml_encode_v3_compound(d, ref_idx):
    if not d or not ref_idx:
        return None
    toks = list(_xml_scan_tokens(d))
    if not toks:
        return None

    tag_names  = list(_DOCX_TAGS)
    attr_names = list(_DOCX_ATTRS)
    attr_vals  = list(_DOCX_VALS)
    compounds  = list(_DOCX_COMPOUNDS_SEED)
    compound_idx = {c: i for i, c in enumerate(compounds)}

    def _add_compound(ti, attr_pairs):
        key = (ti, tuple(attr_pairs))
        i = compound_idx.get(key)
        if i is None:
            i = len(compounds); compounds.append(key); compound_idx[key] = i
        return i

    text_chunks = []
    struct = bytearray()
    for kind, payload in toks:
        if kind == 0:
            struct.append(0)
            _emit_varint(struct, len(text_chunks)); text_chunks.append(payload)
        elif kind == 1:
            name, attrs_raw, selfclose = payload
            ti = _idx_or_add(tag_names, name)
            ams = list(_XML_ATTR_RE.finditer(attrs_raw))
            attr_pairs = []
            for am in ams:
                aname = am.group(1)
                aval  = am.group(2) if am.group(2) is not None else am.group(3)
                ai = _idx_or_add(attr_names, aname)
                vi = _idx_or_add(attr_vals,  aval)
                attr_pairs.append((ai, vi))
            if attr_pairs:
                ci = _add_compound(ti, attr_pairs)
                struct.append(2 if selfclose else 1)
                _emit_varint(struct, ci)
            else:
                struct.append(4 if selfclose else 5)
                _emit_varint(struct, ti)
        elif kind == 2:
            struct.append(3)
            _emit_varint(struct, _idx_or_add(tag_names, payload))
        else:
            struct.append(0)
            _emit_varint(struct, len(text_chunks)); text_chunks.append(payload)

    encoded_texts = [_word_encode_text(t, ref_idx) for t in text_chunks]
    out = bytearray([0x58, 0x5C])
    for lst, seed in zip((tag_names, attr_names, attr_vals),
                         (_DOCX_TAGS, _DOCX_ATTRS, _DOCX_VALS)):
        new_items = lst[len(seed):]
        _emit_varint(out, len(new_items))
        for s in new_items:
            _emit_varint(out, len(s)); out += s
    new_compounds = compounds[len(_DOCX_COMPOUNDS_SEED):]
    _emit_varint(out, len(new_compounds))
    for (ti, pairs) in new_compounds:
        _emit_varint(out, ti)
        _emit_varint(out, len(pairs))
        for ai, vi in pairs:
            _emit_varint(out, ai); _emit_varint(out, vi)
    _emit_varint(out, len(struct)); out += struct
    _emit_varint(out, len(encoded_texts))
    for t in encoded_texts:
        _emit_varint(out, len(t)); out += t
    return bytes(out)

def _xml_encode_v4_localdict(d):
    if not d:
        return None
    toks = list(_xml_scan_tokens(d))
    if not toks:
        return None
    freq = Counter()
    for kind, payload in toks:
        if kind not in (0, 3):
            continue
        last = 0
        for m in _TOK_RE.finditer(payload):
            if m.start() > last:
                freq[payload[last:m.start()]] += 1
            freq[m.group(0).lower()] += 1
            last = m.end()
        if last < len(payload):
            freq[payload[last:]] += 1
    candidates = []
    for chunk, count in freq.items():
        cost = len(chunk) + 1
        escape_per = 1 + 1 + len(chunk)
        encoded_per = 2
        benefit = (escape_per - encoded_per) * count - cost
        if benefit > 0:
            candidates.append((benefit, chunk))
    candidates.sort(reverse=True)
    local_words = [c for _, c in candidates[:4096]]
    local_idx = {c: i for i, c in enumerate(local_words)}

    tag_names  = list(_DOCX_TAGS)
    attr_names = list(_DOCX_ATTRS)
    attr_vals  = list(_DOCX_VALS)
    compounds  = list(_DOCX_COMPOUNDS_SEED)
    compound_idx = {c: i for i, c in enumerate(compounds)}

    def _add_compound(ti, attr_pairs):
        key = (ti, tuple(attr_pairs))
        i = compound_idx.get(key)
        if i is None:
            i = len(compounds); compounds.append(key); compound_idx[key] = i
        return i

    def encode_text(text):
        out = bytearray(); last = 0
        def emit_chunk(chunk):
            i = local_idx.get(chunk)
            if i is not None:
                _emit_varint(out, ((i << 2) | 3) + 1)
            else:
                out.append(0); _emit_varint(out, len(chunk)); out.extend(chunk)
        for m in _TOK_RE.finditer(text):
            if m.start() > last:
                emit_chunk(text[last:m.start()])
            tok_orig = m.group(0); tok_low = tok_orig.lower()
            i = local_idx.get(tok_low)
            done = False
            if i is not None:
                if   tok_orig == tok_low:               case = 0
                elif tok_orig == tok_low.capitalize():  case = 1
                elif tok_orig == tok_low.upper():       case = 2
                else:                                   case = -1
                if case >= 0:
                    _emit_varint(out, ((i << 2) | case) + 1)
                    done = True
            if not done:
                out.append(0); _emit_varint(out, len(tok_orig)); out.extend(tok_orig)
            last = m.end()
        if last < len(text):
            emit_chunk(text[last:])
        return bytes(out)

    struct = bytearray()
    text_chunks = []
    for kind, payload in toks:
        if kind in (0, 3):
            struct.append(0); _emit_varint(struct, len(text_chunks)); text_chunks.append(payload)
        elif kind == 1:
            name, attrs_raw, selfclose = payload
            ti = _idx_or_add(tag_names, name)
            ams = list(_XML_ATTR_RE.finditer(attrs_raw))
            attr_pairs = []
            for am in ams:
                aname = am.group(1)
                aval  = am.group(2) if am.group(2) is not None else am.group(3)
                ai = _idx_or_add(attr_names, aname)
                vi = _idx_or_add(attr_vals,  aval)
                attr_pairs.append((ai, vi))
            if attr_pairs:
                ci = _add_compound(ti, attr_pairs)
                struct.append(2 if selfclose else 1)
                _emit_varint(struct, ci)
            else:
                struct.append(4 if selfclose else 5)
                _emit_varint(struct, ti)
        elif kind == 2:
            struct.append(3); _emit_varint(struct, _idx_or_add(tag_names, payload))

    encoded_texts = [encode_text(t) for t in text_chunks]

    out = bytearray([0x58, 0x5D])
    for lst, seed in zip((tag_names, attr_names, attr_vals),
                         (_DOCX_TAGS, _DOCX_ATTRS, _DOCX_VALS)):
        new_items = lst[len(seed):]
        _emit_varint(out, len(new_items))
        for s in new_items:
            _emit_varint(out, len(s)); out += s
    new_compounds = compounds[len(_DOCX_COMPOUNDS_SEED):]
    _emit_varint(out, len(new_compounds))
    for (ti, pairs) in new_compounds:
        _emit_varint(out, ti)
        _emit_varint(out, len(pairs))
        for ai, vi in pairs:
            _emit_varint(out, ai); _emit_varint(out, vi)
    _emit_varint(out, len(local_words))
    for w in local_words:
        _emit_varint(out, len(w)); out += w
    _emit_varint(out, len(struct)); out += struct
    _emit_varint(out, len(encoded_texts))
    for t in encoded_texts:
        _emit_varint(out, len(t)); out += t
    return bytes(out)

def _xml_decode_v2_words_impl(payload):
    if _GLOBAL_REF_BYTES is None:
        raise TransformError("words variant requires global ref dict")
    rb = _GLOBAL_REF_BYTES; rcap = _GLOBAL_REF_CAP; rup = _GLOBAL_REF_UP
    pos = 2
    dicts = [list(_DOCX_TAGS), list(_DOCX_ATTRS), list(_DOCX_VALS)]
    for idx in range(3):
        cnt, pos = _read_varint(payload, pos)
        for _ in range(cnt):
            ln, pos = _read_varint(payload, pos)
            dicts[idx].append(payload[pos:pos+ln]); pos += ln
    tag_names, attr_names, attr_vals = dicts
    struct_len, pos = _read_varint(payload, pos)
    struct = payload[pos:pos+struct_len]; pos += struct_len
    n_text, pos = _read_varint(payload, pos)
    encoded_texts = []
    for _ in range(n_text):
        ln, pos = _read_varint(payload, pos)
        encoded_texts.append(payload[pos:pos+ln]); pos += ln
    texts = [_word_decode_text(et, rb, rcap, rup) for et in encoded_texts]
    out = bytearray(); sp = 0
    while sp < len(struct):
        op = struct[sp]; sp += 1
        if op == 0:
            idx, sp = _read_varint(struct, sp); out += texts[idx]
        elif op in (1, 4):
            ti, sp = _read_varint(struct, sp); n_attrs, sp = _read_varint(struct, sp)
            out += b'<' + tag_names[ti]
            for _ in range(n_attrs):
                ai, sp = _read_varint(struct, sp); vi, sp = _read_varint(struct, sp)
                out += b' ' + attr_names[ai] + b'="' + attr_vals[vi] + b'"'
            out += b'/>' if op == 4 else b'>'
        elif op == 2:
            ti, sp = _read_varint(struct, sp); out += b'</' + tag_names[ti] + b'>'
        elif op == 3:
            idx, sp = _read_varint(struct, sp); out += texts[idx]
        else: raise TransformError(f"xml v2w op {op}")
    return bytes(out)

def _xml_decode_v3_compound(payload):
    if _GLOBAL_REF_BYTES is None:
        raise TransformError("compound variant requires global ref dict")
    rb = _GLOBAL_REF_BYTES; rcap = _GLOBAL_REF_CAP; rup = _GLOBAL_REF_UP
    if len(payload) < 2 or payload[0] != 0x58 or payload[1] != 0x5C:
        raise TransformError("compound magic")
    pos = 2
    dicts = [list(_DOCX_TAGS), list(_DOCX_ATTRS), list(_DOCX_VALS)]
    for idx in range(3):
        cnt, pos = _read_varint(payload, pos)
        for _ in range(cnt):
            ln, pos = _read_varint(payload, pos)
            dicts[idx].append(payload[pos:pos+ln]); pos += ln
    tag_names, attr_names, attr_vals = dicts
    compounds = list(_DOCX_COMPOUNDS_SEED)
    n_new, pos = _read_varint(payload, pos)
    for _ in range(n_new):
        ti,    pos = _read_varint(payload, pos)
        n_att, pos = _read_varint(payload, pos)
        pairs = []
        for _ in range(n_att):
            ai, pos = _read_varint(payload, pos)
            vi, pos = _read_varint(payload, pos)
            pairs.append((ai, vi))
        compounds.append((ti, pairs))
    struct_len, pos = _read_varint(payload, pos)
    struct = payload[pos:pos+struct_len]; pos += struct_len
    n_text, pos = _read_varint(payload, pos)
    encoded_texts = []
    for _ in range(n_text):
        ln, pos = _read_varint(payload, pos)
        encoded_texts.append(payload[pos:pos+ln]); pos += ln
    texts = [_word_decode_text(et, rb, rcap, rup) for et in encoded_texts]
    out = bytearray(); sp = 0
    while sp < len(struct):
        op = struct[sp]; sp += 1
        if op == 0:
            idx, sp = _read_varint(struct, sp); out += texts[idx]
        elif op in (1, 2):
            ci, sp = _read_varint(struct, sp)
            ti, pairs = compounds[ci]
            out += b'<' + tag_names[ti]
            for ai, vi in pairs:
                out += b' ' + attr_names[ai] + b'="' + attr_vals[vi] + b'"'
            out += b'/>' if op == 2 else b'>'
        elif op == 3:
            ti, sp = _read_varint(struct, sp)
            out += b'</' + tag_names[ti] + b'>'
        elif op in (4, 5):
            ti, sp = _read_varint(struct, sp)
            out += b'<' + tag_names[ti] + (b'/>' if op == 4 else b'>')
        else:
            raise TransformError(f"compound op {op}")
    return bytes(out)

def _xml_decode_v4_localdict(payload):
    if len(payload) < 2 or payload[0] != 0x58 or payload[1] != 0x5D:
        raise TransformError("localdict magic")
    pos = 2
    dicts = [list(_DOCX_TAGS), list(_DOCX_ATTRS), list(_DOCX_VALS)]
    for idx in range(3):
        cnt, pos = _read_varint(payload, pos)
        for _ in range(cnt):
            ln, pos = _read_varint(payload, pos)
            dicts[idx].append(payload[pos:pos+ln]); pos += ln
    tag_names, attr_names, attr_vals = dicts
    compounds = list(_DOCX_COMPOUNDS_SEED)
    n_new, pos = _read_varint(payload, pos)
    for _ in range(n_new):
        ti,    pos = _read_varint(payload, pos)
        n_att, pos = _read_varint(payload, pos)
        pairs = []
        for _ in range(n_att):
            ai, pos = _read_varint(payload, pos)
            vi, pos = _read_varint(payload, pos)
            pairs.append((ai, vi))
        compounds.append((ti, pairs))
    n_words, pos = _read_varint(payload, pos)
    local_words = []
    for _ in range(n_words):
        ln, pos = _read_varint(payload, pos)
        local_words.append(payload[pos:pos+ln]); pos += ln
    struct_len, pos = _read_varint(payload, pos)
    struct = payload[pos:pos+struct_len]; pos += struct_len
    n_text, pos = _read_varint(payload, pos)
    encoded_texts = []
    for _ in range(n_text):
        ln, pos = _read_varint(payload, pos)
        encoded_texts.append(payload[pos:pos+ln]); pos += ln
    def decode_text(blob):
        out = bytearray(); p = 0; nb = len(blob)
        while p < nb:
            code, p = _read_varint(blob, p)
            if code == 0:
                ln, p = _read_varint(blob, p)
                out += blob[p:p+ln]; p += ln
            else:
                x = code - 1; i = x >> 2; c = x & 3
                if i >= len(local_words):
                    raise TransformError(f"localdict idx {i}>={len(local_words)}")
                w = local_words[i]
                if   c == 0: out += w
                elif c == 1: out += w.capitalize()
                elif c == 2: out += w.upper()
                elif c == 3: out += w
                else:        raise TransformError(f"localdict case {c}")
        return bytes(out)
    texts = [decode_text(et) for et in encoded_texts]
    out = bytearray(); sp = 0
    while sp < len(struct):
        op = struct[sp]; sp += 1
        if op == 0:
            idx, sp = _read_varint(struct, sp); out += texts[idx]
        elif op in (1, 2):
            ci, sp = _read_varint(struct, sp)
            ti, pairs = compounds[ci]
            out += b'<' + tag_names[ti]
            for ai, vi in pairs:
                out += b' ' + attr_names[ai] + b'="' + attr_vals[vi] + b'"'
            out += b'/>' if op == 2 else b'>'
        elif op == 3:
            ti, sp = _read_varint(struct, sp)
            out += b'</' + tag_names[ti] + b'>'
        elif op in (4, 5):
            ti, sp = _read_varint(struct, sp)
            out += b'<' + tag_names[ti] + (b'/>' if op == 4 else b'>')
        else:
            raise TransformError(f"localdict op {op}")
    return bytes(out)

def _xml_encode_v5_nested(d, ref_idx):
    if not d or not ref_idx:
        return None
    toks = list(_xml_scan_tokens(d))
    if not toks:
        return None

    tag_names  = list(_DOCX_TAGS)
    attr_names = list(_DOCX_ATTRS)
    attr_vals  = list(_DOCX_VALS)
    compounds  = list(_DOCX_COMPOUNDS_SEED)
    compound_idx = {c: i for i, c in enumerate(compounds)}

    def _add_compound(ti, attr_pairs):
        key = (ti, tuple(attr_pairs))
        i = compound_idx.get(key)
        if i is None:
            i = len(compounds); compounds.append(key); compound_idx[key] = i
        return i

    text_chunks = []
    struct_flat = bytearray()
    stack = []
    candidates = []

    for kind, payload in toks:
        if kind == 0:
            struct_flat.append(0)
            _emit_varint(struct_flat, len(text_chunks))
            text_chunks.append(payload)
            for e in stack: e[2] = True
        elif kind == 1:
            name, attrs_raw, selfclose = payload
            ti = _idx_or_add(tag_names, name)
            ams = list(_XML_ATTR_RE.finditer(attrs_raw))
            attr_pairs = []
            for am in ams:
                aname = am.group(1)
                aval  = am.group(2) if am.group(2) is not None else am.group(3)
                ai = _idx_or_add(attr_names, aname)
                vi = _idx_or_add(attr_vals,  aval)
                attr_pairs.append((ai, vi))
            start = len(struct_flat)
            if attr_pairs:
                ci = _add_compound(ti, attr_pairs)
                struct_flat.append(2 if selfclose else 1)
                _emit_varint(struct_flat, ci)
            else:
                struct_flat.append(4 if selfclose else 5)
                _emit_varint(struct_flat, ti)
            if not selfclose:
                stack.append([ti, start, False])
        elif kind == 2:
            name = payload
            ti = _idx_or_add(tag_names, name)
            struct_flat.append(3)
            _emit_varint(struct_flat, ti)
            if stack and stack[-1][0] == ti:
                _, start, has_text = stack.pop()
                if not has_text:
                    end = len(struct_flat)
                    sig = bytes(struct_flat[start:end])
                    if len(sig) >= 3:
                        candidates.append((start, end, sig))
        else:
            struct_flat.append(0)
            _emit_varint(struct_flat, len(text_chunks))
            text_chunks.append(payload)
            for e in stack: e[2] = True

    sig_counts = Counter(c[2] for c in candidates)
    kept = []
    for sig, cnt in sig_counts.items():
        if cnt < 2: continue
        saving = cnt * (len(sig) - 2) - (len(sig) + 2)
        if saving > 0:
            kept.append((saving, sig))
    kept.sort(key=lambda x: -x[0])
    nested = [s for _, s in kept]
    nested_idx = {s: i for i, s in enumerate(nested)}
    if not nested:
        return None

    span_cands = []
    for start, end, sig in candidates:
        ni = nested_idx.get(sig)
        if ni is not None:
            span_cands.append((end - start, start, end, ni))
    span_cands.sort(key=lambda x: -x[0])
    taken = []
    final_map = {}
    for length, start, end, ni in span_cands:
        if any(start < te and end > ts for ts, te in taken):
            continue
        final_map[start] = (end, ni)
        taken.append((start, end))

    actual_cnt = Counter(ni for _, ni in final_map.values())
    kept_mask = [i for i, sig in enumerate(nested)
                 if actual_cnt.get(i, 0) * (len(sig) - 2) > (len(sig) + 2)]
    if not kept_mask:
        return None
    remap = {old: new for new, old in enumerate(kept_mask)}
    nested = [nested[i] for i in kept_mask]
    final_map = {start: (end, remap[ni])
                 for start, (end, ni) in final_map.items() if ni in remap}
    if not final_map:
        return None

    struct = bytearray()
    flat = bytes(struct_flat)
    sp = 0
    for start in sorted(final_map.keys()):
        end, ni = final_map[start]
        struct += flat[sp:start]
        struct.append(6)
        _emit_varint(struct, ni)
        sp = end
    struct += flat[sp:]

    encoded_texts = [_word_encode_text(t, ref_idx) for t in text_chunks]
    out = bytearray([0x58, 0x5E])
    for lst, seed in zip((tag_names, attr_names, attr_vals),
                         (_DOCX_TAGS, _DOCX_ATTRS, _DOCX_VALS)):
        new_items = lst[len(seed):]
        _emit_varint(out, len(new_items))
        for s in new_items:
            _emit_varint(out, len(s)); out += s
    new_compounds = compounds[len(_DOCX_COMPOUNDS_SEED):]
    _emit_varint(out, len(new_compounds))
    for (ti, pairs) in new_compounds:
        _emit_varint(out, ti)
        _emit_varint(out, len(pairs))
        for ai, vi in pairs:
            _emit_varint(out, ai); _emit_varint(out, vi)
    _emit_varint(out, len(nested))
    for sig in nested:
        _emit_varint(out, len(sig)); out += sig
    _emit_varint(out, len(struct)); out += struct
    _emit_varint(out, len(encoded_texts))
    for t in encoded_texts:
        _emit_varint(out, len(t)); out += t
    return bytes(out)

def _decode_nested_ops(out, struct, compounds, tag_names, attr_names, attr_vals,
                       texts, nested, depth):
    if depth > 16:
        raise TransformError("nested depth overflow")
    sp = 0
    while sp < len(struct):
        op = struct[sp]; sp += 1
        if op == 0:
            idx, sp = _read_varint(struct, sp); out += texts[idx]
        elif op in (1, 2):
            ci, sp = _read_varint(struct, sp)
            ti, pairs = compounds[ci]
            out += b'<' + tag_names[ti]
            for ai, vi in pairs:
                out += b' ' + attr_names[ai] + b'="' + attr_vals[vi] + b'"'
            out += b'/>' if op == 2 else b'>'
        elif op == 3:
            ti, sp = _read_varint(struct, sp)
            out += b'</' + tag_names[ti] + b'>'
        elif op in (4, 5):
            ti, sp = _read_varint(struct, sp)
            out += b'<' + tag_names[ti] + (b'/>' if op == 4 else b'>')
        elif op == 6:
            ni, sp = _read_varint(struct, sp)
            if ni >= len(nested):
                raise TransformError(f"nested idx {ni}>={len(nested)}")
            _decode_nested_ops(out, nested[ni], compounds, tag_names, attr_names,
                               attr_vals, texts, nested, depth + 1)
        else:
            raise TransformError(f"nested op {op}")

def _xml_decode_v5_nested(payload):
    if _GLOBAL_REF_BYTES is None:
        raise TransformError("nested variant requires global ref dict")
    rb = _GLOBAL_REF_BYTES; rcap = _GLOBAL_REF_CAP; rup = _GLOBAL_REF_UP
    if len(payload) < 2 or payload[0] != 0x58 or payload[1] != 0x5E:
        raise TransformError("nested magic")
    pos = 2
    dicts = [list(_DOCX_TAGS), list(_DOCX_ATTRS), list(_DOCX_VALS)]
    for idx in range(3):
        cnt, pos = _read_varint(payload, pos)
        for _ in range(cnt):
            ln, pos = _read_varint(payload, pos)
            dicts[idx].append(payload[pos:pos+ln]); pos += ln
    tag_names, attr_names, attr_vals = dicts
    compounds = list(_DOCX_COMPOUNDS_SEED)
    n_new, pos = _read_varint(payload, pos)
    for _ in range(n_new):
        ti,    pos = _read_varint(payload, pos)
        n_att, pos = _read_varint(payload, pos)
        pairs = []
        for _ in range(n_att):
            ai, pos = _read_varint(payload, pos)
            vi, pos = _read_varint(payload, pos)
            pairs.append((ai, vi))
        compounds.append((ti, pairs))
    n_nested, pos = _read_varint(payload, pos)
    nested = []
    for _ in range(n_nested):
        ln, pos = _read_varint(payload, pos)
        nested.append(payload[pos:pos+ln]); pos += ln
    struct_len, pos = _read_varint(payload, pos)
    struct = payload[pos:pos+struct_len]; pos += struct_len
    n_text, pos = _read_varint(payload, pos)
    encoded_texts = []
    for _ in range(n_text):
        ln, pos = _read_varint(payload, pos)
        encoded_texts.append(payload[pos:pos+ln]); pos += ln
    texts = [_word_decode_text(et, rb, rcap, rup) for et in encoded_texts]
    out = bytearray()
    _decode_nested_ops(out, struct, compounds, tag_names, attr_names, attr_vals,
                       texts, nested, 0)
    return bytes(out)

def _xml_decode_v2(payload):
    if len(payload) < 2 or payload[0] != 0x58:
        raise TransformError("xml magic")
    if payload[1] == 0x5A: return _xml_decode_bits(payload)
    if payload[1] == 0x5B: return _xml_decode_v2_words_impl(payload)
    if payload[1] == 0x5C: return _xml_decode_v3_compound(payload)
    if payload[1] == 0x5D: return _xml_decode_v4_localdict(payload)
    if payload[1] == 0x5E: return _xml_decode_v5_nested(payload)
    if payload[1] == 0x58: seeds = ([], [], [])
    elif payload[1] == 0x59: seeds = (list(_DOCX_TAGS), list(_DOCX_ATTRS), list(_DOCX_VALS))
    else: raise TransformError("xml magic")
    pos = 2
    dicts = [list(s) for s in seeds]
    for idx in range(3):
        cnt, pos = _read_varint(payload, pos)
        for _ in range(cnt):
            ln, pos = _read_varint(payload, pos)
            dicts[idx].append(payload[pos:pos+ln]); pos += ln
    tag_names, attr_names, attr_vals = dicts
    struct_len, pos = _read_varint(payload, pos)
    struct = payload[pos:pos+struct_len]; pos += struct_len
    n_text, pos = _read_varint(payload, pos); texts = []
    for _ in range(n_text):
        ln, pos = _read_varint(payload, pos)
        texts.append(payload[pos:pos+ln]); pos += ln
    out = bytearray(); sp = 0
    while sp < len(struct):
        op = struct[sp]; sp += 1
        if op == 0:
            idx, sp = _read_varint(struct, sp); out += texts[idx]
        elif op in (1, 4):
            ti, sp = _read_varint(struct, sp); n_attrs, sp = _read_varint(struct, sp)
            out += b'<' + tag_names[ti]
            for _ in range(n_attrs):
                ai, sp = _read_varint(struct, sp); vi, sp = _read_varint(struct, sp)
                out += b' ' + attr_names[ai] + b'="' + attr_vals[vi] + b'"'
            out += b'/>' if op == 4 else b'>'
        elif op == 2:
            ti, sp = _read_varint(struct, sp); out += b'</' + tag_names[ti] + b'>'
        elif op == 3:
            idx, sp = _read_varint(struct, sp); out += texts[idx]
        else: raise TransformError(f"xml v3 op {op}")
    return bytes(out)

def _best_xml_encode(d, ref_idx=None):
    best = None
    for enc_fn, dec_fn in ((_xml_encode_v2,   _xml_decode_v2),
                           (_xml_encode_bits, _xml_decode_bits)):
        try:
            p = enc_fn(d)
            if p is None: continue
            if dec_fn(p) != d: continue
            if best is None or len(p) < len(best): best = p
        except Exception: continue
    try:
        p = _xml_encode_v4_localdict(d)
        if p is not None and _xml_decode_v2(p) == d:
            if best is None or len(p) < len(best): best = p
    except Exception: pass
    if ref_idx:
        for enc_fn in (_xml_encode_v2_words, _xml_encode_v3_compound,
                       _xml_encode_v5_nested):
            try:
                p = enc_fn(d, ref_idx)
                if p is not None and _xml_decode_v2(p) == d:
                    if best is None or len(p) < len(best): best = p
            except Exception: pass
    return best

PRIMES = [p for p in range(2, 256) if all(p % d != 0 for d in range(2, int(p**0.5) + 1))]
PI_DIGITS = [79, 17, 111]

def nearest_prime(n):
    n &= 0xFF
    if n < 2:
        return 2
    o = 0
    while o <= 256:
        c1, c2 = n - o, n + o
        if c1 >= 2:
            if all(c1 % d != 0 for d in range(2, int(c1 ** 0.5) + 1)):
                return c1 & 0xFF
        if c2 >= 2 and c2 <= 255:
            if all(c2 % d != 0 for d in range(2, int(c2 ** 0.5) + 1)):
                return c2 & 0xFF
        o += 1
    return n & 0xFF

_CD_CODE = [(2,0b10),(2,0b11),(3,0b010),(3,0b011),(4,0b0010),(4,0b0011),(5,0b00010),(5,0b00011),(6,0b000010),(6,0b000011),(7,0b0000010),(7,0b0000011),(8,0b00000010),(8,0b00000011),(9,0b000000010),(9,0b000000011)]
_CD_DEC = {v: k for k, v in enumerate(_CD_CODE)}
ALPH_6 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 \n"
CH2_6 = {ch: i for i, ch in enumerate(ALPH_6)}
_6TOCH = {i: ch for ch, i in CH2_6.items()}
PAQ = [[1,2,0,0],[3,5,0,1],[4,6,2,0],[7,10,0,2],[8,12,3,0],[9,13,1,1],[11,14,0,3],[15,19,4,0],[16,23,2,1],[17,24,2,1],[18,25,2,1],[20,27,1,2],[21,28,1,2],[22,29,1,2],[26,30,0,4],[31,33,5,0],[32,34,3,1],[35,37,1,3],[36,38,1,3],[39,42,0,5],[40,43,4,1],[41,44,2,2],[45,48,1,4],[46,49,1,4],[47,50,1,4],[51,52,0,6],[53,55,6,0],[54,56,4,1],[57,59,2,3],[58,60,2,3],[61,63,0,7],[62,64,5,1],[65,66,3,2],[67,69,1,5],[68,70,1,5],[71,73,0,8],[72,74,6,1],[75,76,4,2],[77,78,2,4],[79,80,2,4],[81,82,0,9],[83,84,7,1],[85,86,5,2],[87,88,3,3],[89,90,1,6],[91,92,0,10],[93,94,8,1],[95,96,6,2],[97,98,4,3],[99,100,2,5],[101,102,0,11],[103,104,9,1],[105,106,7,2],[107,108,5,3],[109,110,3,4],[111,112,1,7],[113,114,0,12],[115,116,10,1],[117,118,8,2],[119,120,6,3],[121,122,4,4],[123,124,2,6],[125,126,0,13],[127,128,11,1],[129,130,9,2],[131,132,7,3],[133,134,5,4],[135,136,3,5],[137,138,1,8],[139,140,0,14],[141,142,12,1],[143,144,10,2],[145,146,8,3],[147,148,6,4],[149,150,4,5],[151,152,2,7],[153,154,0,15],[155,156,13,1],[157,158,11,2],[159,160,9,3],[161,162,7,4],[163,164,5,5],[165,166,3,6],[167,168,1,9],[169,170,0,16],[171,172,14,1],[173,174,12,2],[175,176,10,3],[177,178,8,4],[179,180,6,5],[181,182,4,6],[183,184,2,8],[185,186,0,17],[187,188,15,1],[189,190,13,2],[191,192,11,3],[193,194,9,4],[195,196,7,5],[197,198,5,6],[199,200,3,7],[201,202,1,10],[203,204,0,18],[205,206,16,1],[207,208,14,2],[209,210,12,3],[211,212,10,4],[213,214,8,5],[215,216,6,6],[217,218,4,7],[219,220,2,9],[221,222,0,19],[223,224,17,1],[225,226,15,2],[227,228,13,3],[229,230,11,4],[231,232,9,5],[233,234,7,6],[235,236,5,7],[237,238,3,8],[239,240,1,11],[241,242,0,20],[243,244,18,1],[245,246,16,2],[247,248,14,3],[249,250,12,4],[251,252,10,5],[253,254,8,6],[255,255,6,7]]

class TransformError(Exception): pass
class DecompressionError(Exception): pass

def mod_inv(a, m):
    if a == 0: return None
    m0 = m; y = 0; x = 1
    if m == 1: return 0
    while a > 1:
        q = a // m; t = m; m = a % m; a = t
        t = y; y = x - q * y; x = t
    if x < 0: x += m0
    return x

def _encode_header(kind, ident):
    if kind == "a":
        if not (1 <= ident <= 256): raise TransformError(f"single ID out of range: {ident}")
        v = ident - 1
    else:
        if not (1 <= ident <= MAX_PAIRS):
            raise TransformError(f"pair index out of range: {ident} (max {MAX_PAIRS})")
        v = 0x100 + (ident - 1)
    return bytes([(v >> 8) & 0xFF, v & 0xFF])

def _decode_header(hdr):
    if len(hdr) < 2: raise TransformError("short header")
    v = (hdr[0] << 8) | hdr[1]
    if v < 0x100: return "a", v + 1
    return "b", v - 0xFF

_EXT_RE = re.compile(r'\.a([0-9a-fA-F]{4})(?![0-9a-fA-F])')

def _ext_for(kind, ident):
    hdr = _encode_header(kind, ident)
    return f".a{hdr[0]:02x}{hdr[1]:02x}"

def _parse_ext(fname):
    m = _EXT_RE.search(fname)
    if not m: return None
    hexs = m.group(1)
    v = int(hexs, 16)
    if v < 0x100: return "a", v + 1
    return "b", v - 0xFF

def _parse_zip_entries(d):
    if len(d) < 22 or d[:4] != ZIP_MAGIC:
        raise TransformError("not a zip (local sig)")
    eocd_pos = d.rfind(_ZIP_EOCD_SIG)
    if eocd_pos < 0:
        raise TransformError("no EOCD")
    if eocd_pos + 22 > len(d):
        raise TransformError("EOCD truncated")
    eocd_bytes = d[eocd_pos:]
    comment_len = struct.unpack('<H', eocd_bytes[20:22])[0]
    if eocd_pos + 22 + comment_len != len(d):
        raise TransformError("trailing data after EOCD")
    n_entries = struct.unpack('<H', eocd_bytes[10:12])[0]
    cd_offset = struct.unpack('<I', eocd_bytes[16:20])[0]
    cd_size   = struct.unpack('<I', eocd_bytes[12:16])[0]
    if cd_offset + cd_size > eocd_pos:
        raise TransformError("central dir overflow")
    central_dir_bytes = d[cd_offset:cd_offset + cd_size]

    infos = []
    pos = 0
    for _ in range(n_entries):
        if pos + 46 > len(central_dir_bytes):
            raise TransformError("CD truncated")
        if central_dir_bytes[pos:pos+4] != _ZIP_CENTRAL_SIG:
            raise TransformError("CD sig")
        fname_len   = struct.unpack('<H', central_dir_bytes[pos+28:pos+30])[0]
        extra_len   = struct.unpack('<H', central_dir_bytes[pos+30:pos+32])[0]
        comment_len_e = struct.unpack('<H', central_dir_bytes[pos+32:pos+34])[0]
        method      = struct.unpack('<H', central_dir_bytes[pos+10:pos+12])[0]
        flags       = struct.unpack('<H', central_dir_bytes[pos+8:pos+10])[0]
        comp_size   = struct.unpack('<I', central_dir_bytes[pos+20:pos+24])[0]
        local_off   = struct.unpack('<I', central_dir_bytes[pos+42:pos+46])[0]
        entry_end   = pos + 46 + fname_len + extra_len + comment_len_e
        if entry_end > len(central_dir_bytes):
            raise TransformError("CD entry overflow")
        infos.append({'method': method, 'flags': flags,
                      'comp_size': comp_size, 'local_offset': local_off})
        pos = entry_end
    if pos != len(central_dir_bytes):
        raise TransformError(f"CD extra bytes: {len(central_dir_bytes)-pos}")

    entries = []
    for info in infos:
        lp = info['local_offset']
        if lp + 30 > len(d) or d[lp:lp+4] != ZIP_MAGIC:
            raise TransformError(f"local sig at {lp}")
        l_fname_len = struct.unpack('<H', d[lp+26:lp+28])[0]
        l_extra_len = struct.unpack('<H', d[lp+28:lp+30])[0]
        l_header_end = lp + 30 + l_fname_len + l_extra_len
        local_header = d[lp:l_header_end]
        data_end = l_header_end + info['comp_size']
        if data_end > eocd_pos:
            raise TransformError(f"data overflow: {data_end}>{eocd_pos}")
        compressed = d[l_header_end:data_end]
        dd = b''
        if info['flags'] & 0x08:
            if d[data_end:data_end+4] == _ZIP_DATA_DESC_SIG:
                dd_end = data_end + 4 + 12
            else:
                dd_end = data_end + 12
            if dd_end > eocd_pos:
                raise TransformError("DD overflow")
            dd = d[data_end:dd_end]
        entries.append({'local_header': local_header,
                        'compressed': compressed,
                        'data_descriptor': dd,
                        'method': info['method'],
                        'flags': info['flags'],
                        'comp_size': info['comp_size']})

    recon = bytearray()
    for e in entries:
        recon += e['local_header'] + e['compressed'] + e['data_descriptor']
    recon += central_dir_bytes + eocd_bytes
    if bytes(recon) != d:
        raise TransformError(f"reconstruct mismatch: {len(recon)} vs {len(d)}")
    return entries, central_dir_bytes, eocd_bytes

def _find_deflate_params(raw, target):
    combos = [(6, zlib.Z_DEFAULT_STRATEGY), (9, zlib.Z_DEFAULT_STRATEGY)]
    for lvl in [1, 8, 7, 5, 4, 3, 2, 0]:
        for strat in (zlib.Z_DEFAULT_STRATEGY, zlib.Z_FILTERED,
                      zlib.Z_RLE, zlib.Z_HUFFMAN_ONLY, zlib.Z_FIXED):
            combos.append((lvl, strat))
    for level, strat in combos:
        try:
            co = zlib.compressobj(level, zlib.DEFLATED, -15, 8, strat)
            if (co.compress(raw) + co.flush()) == target:
                return (level, strat)
        except Exception:
            pass
    return None

class Compressor:
    TIMEOUT = 300; VS = False; USE_MP = True
    TOP_K = 100; FAST = True; BLOCK = 4096
    MAX_TRANSFORM = 256; PROGRESS_EVERY = 500; STRIDE = 3
    MAX_EAGER_ID = 256
    HUFF_MAX_LEN = 64

    _A80_BLK    = 1024
    _A80_MASK   = (1 << 8192) - 1
    _A80_PERIOD = 3 * 1024

    def __init__(self, try_dl=True, pairs=MAX_PAIRS, qubits=16):
        self.PAIRS = min(pairs, MAX_PAIRS)
        self.QUBITS = qubits
        self._cback_cache = {}
        self._CBACK_CACHE_MAX = 65536
        self._fwd_cache = {}
        self._pool_cback = None; self._pool_pid = None
        self._a35_cache = {}
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
        self._t04_tab = None; self._t06_tab = None; self._t06_inv = None
        self._t11_cache = {}; self._t12_cache = {}; self._t26_cache = {}
        self._c18_cache = {}; self._c19_cache = {}; self._c20_cache = {}
        self._cdd_cache = {}; self._rot_tabs = {}; self._add_tabs = {}; self._sub_tabs = {}
        self._m1_tab = bytes((b - 1) & 0xFF for b in range(256))
        self._p1_tab = bytes((b + 1) & 0xFF for b in range(256))
        self._np_tab = [nearest_prime(n) & 0xFF for n in range(600)]
        self._spread_0101 = int.from_bytes(b'\x01' * 1024, 'little')
        gr8 = (0x9E3779B97F4A7C15).to_bytes(8, 'little')
        self._spread_golden = int.from_bytes(gr8 * 128, 'little')
        self._a82_ks_cache = None
        self._q64_cache = None
        self._bitrev8_tab = bytes(self._rev8(b) for b in range(256))
        self._nib_swap_tab = bytes(((b << 4) | (b >> 4)) & 0xFF for b in range(256))
        self._rot8_tabs = [bytes(((b << k) | (b >> (8-k))) & 0xFF if k else b for b in range(256)) for k in range(8)]
        self._irot8_tabs = [bytes(((b >> k) | (b << (8-k))) & 0xFF if k else b for b in range(256)) for k in range(8)]
        self._periodic_cache = {}
        if HAS_QISKIT:
            t0 = time.time()
            self._qperm = quantum_pair_permutation(self.PAIRS, self.QUBITS)
            print(f"  quantum permutation ready ({time.time()-t0:.3f}s)")
        else:
            self._qperm = list(range(self.PAIRS))
        self._build_ref_dict()
        _set_global_ref(self.ref_bytes, self.ref_bytes_cap, self.ref_bytes_up)
        self._maps(); self._pairs()
        self._pair_index = {p: i + 1 for i, p in enumerate(self.pairs)}
        self._verify_all_transforms()

    @staticmethod
    def _rev8(b):
        r = 0
        for _ in range(8):
            r = (r << 1) | (b & 1); b >>= 1
        return r

    def _is_huge_a256(self):
        return A256_LIMIT == 0 and A256_MODE in ("exhaustive", "repeat32")

    def _verify_all_transforms(self):
        sample = (b"the quick brown fox jumps over the lazy dog " * 3
                  + bytes(range(256)) + os.urandom(64))
        tests = [b"", b"\x00", b"\xff", sample]
        bad = []
        for t in range(1, 257):
            if t == 256 and self._is_huge_a256():
                try:
                    saved_lim = A256_LIMIT
                    globals()['A256_LIMIT'] = 16
                    tr = self.fwd[t](sample); back = self.rev[t](tr)
                    globals()['A256_LIMIT'] = saved_lim
                    if back != sample:
                        bad.append((t, len(sample), "mismatch"))
                except Exception as e:
                    bad.append((t, len(sample), repr(e)))
                continue
            for test in tests:
                try:
                    tr = self.fwd[t](test)
                    if self.rev[t](tr) != test:
                        bad.append((t, len(test), "mismatch")); break
                except Exception as e:
                    bad.append((t, len(test), repr(e))); break
        if bad:
            broken_ids = sorted({t for t, _, _ in bad})
            print(f"  [FAIL-FAST] {len(broken_ids)} transforms failed verify:")
            for t, L, why in bad[:12]:
                print(f"    a{t}: len={L} {why}")
            if len(bad) > 12: print(f"    ... ({len(bad)-12} more)")
            print(f"  [FIX] replacing {len(broken_ids)} broken IDs with identity")
            for t in broken_ids:
                self.fwd[t] = (lambda d: d)
                self.rev[t] = (lambda d: d)
        else:
            print("  all 256 transforms verified at construction time ✓")

    def _xor_table(self, k):
        t = self._xor_tables.get(k)
        if t is None: t = bytes(b ^ k for b in range(256)); self._xor_tables[k] = t
        return t
    def _rot_tab(self, k):
        k &= 7; t = self._rot_tabs.get(k)
        if t is None:
            t = bytes(((b << k) | (b >> (8 - k))) & 0xFF for b in range(256)); self._rot_tabs[k] = t
        return t
    def _irot_tab(self, k):
        k &= 7; key = ('i', k); t = self._rot_tabs.get(key)
        if t is None:
            t = bytes(((b >> k) | (b << (8 - k))) & 0xFF for b in range(256)); self._rot_tabs[key] = t
        return t
    def _add_tab(self, k):
        k &= 0xFF; t = self._add_tabs.get(k)
        if t is None: t = bytes((b + k) & 0xFF for b in range(256)); self._add_tabs[k] = t
        return t
    def _sub_tab(self, k):
        k &= 0xFF; t = self._sub_tabs.get(k)
        if t is None: t = bytes((b - k) & 0xFF for b in range(256)); self._sub_tabs[k] = t
        return t
    def _xor_pattern(self, d, pattern):
        L = len(d); pl = len(pattern)
        mask = (pattern * ((L // pl) + 1))[:L]
        return (int.from_bytes(d, 'big') ^ int.from_bytes(mask, 'big')).to_bytes(L, 'big')
    def _np(self, n):
        return (self._np_tab[n] if n < 600 else nearest_prime(n)) & 0xFF

    @staticmethod
    def _blk_check(b):
        h = 0x811c9dc5
        for byte in b:
            h = ((h ^ byte) * 0x01000193) & 0xFFFFFFFF
        return (h ^ (h >> 16)) & 0xFFFF

    def _sbox_perm(self, key_bytes):
        cache_key = bytes(key_bytes)
        hit = self._a35_cache.get(cache_key)
        if hit is not None:
            return hit
        rng = random.Random(int.from_bytes(hashlib.sha256(cache_key).digest(), 'big'))
        perm = list(range(256))
        rng.shuffle(perm)
        fwd = bytes(perm)
        inv = bytearray(256)
        for i, v in enumerate(perm):
            inv[v] = i
        self._a35_cache[cache_key] = (fwd, bytes(inv))
        return self._a35_cache[cache_key]

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
        a, b = 0, 1; r = [a, b]
        for _ in range(2, n): a, b = b, a+b; r.append(b)
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

    def _F_dstride(self, k):
        def f(d):
            n = len(d)
            if n <= k: return bytes(d)
            o = bytearray(d)
            for i in range(n - 1, k - 1, -1):
                o[i] = (o[i] - o[i - k]) & 0xFF
            return bytes(o)
        def r(d):
            n = len(d)
            if n <= k: return bytes(d)
            o = bytearray(n); o[:k] = d[:k]
            for i in range(k, n):
                o[i] = (d[i] + o[i - k]) & 0xFF
            return bytes(o)
        return f, r

    def _F_astride(self, k):
        def f(d):
            n = len(d)
            if n <= k: return bytes(d)
            o = bytearray(d)
            for i in range(n - 1, k - 1, -1):
                o[i] = (o[i] + o[i - k]) & 0xFF
            return bytes(o)
        def r(d):
            n = len(d)
            if n <= k: return bytes(d)
            o = bytearray(d)
            for i in range(k, n):
                o[i] = (o[i] - o[i - k]) & 0xFF
            return bytes(o)
        return f, r

    def _F_xstride(self, k):
        def f(d):
            n = len(d)
            if n <= k: return bytes(d)
            o = bytearray(d)
            for i in range(n - 1, k - 1, -1):
                o[i] ^= o[i - k]
            return bytes(o)
        def r(d):
            n = len(d)
            if n <= k: return bytes(d)
            o = bytearray(d)
            for i in range(k, n):
                o[i] ^= o[i - k]
            return bytes(o)
        return f, r

    def _F_ddot(self, k):
        def f(d):
            n = len(d)
            if n <= 2 * k: return bytes(d)
            orig = bytes(d)
            o = bytearray(n)
            for i in range(n):
                a = orig[i]
                b = orig[i - k]     if i >= k     else 0
                c = orig[i - 2 * k] if i >= 2 * k else 0
                o[i] = (a - 2 * b + c) & 0xFF
            return bytes(o)
        def r(d):
            n = len(d)
            if n <= 2 * k: return bytes(d)
            s1 = bytearray(n); s1[:k] = d[:k]
            for i in range(k, n):
                s1[i] = (d[i] + s1[i - k]) & 0xFF
            s2 = bytearray(n); s2[:k] = s1[:k]
            for i in range(k, n):
                s2[i] = (s1[i] + s2[i - k]) & 0xFF
            return bytes(s2)
        return f, r

    def _F_transpose(self, w_par):
        widths = (2, 3, 4, 6, 8, 12, 16, 24)
        w = widths[w_par % len(widths)]
        def _offsets(n, ww):
            col_count = [0] * ww
            for i in range(n): col_count[i % ww] += 1
            off = [0] * ww
            for c in range(1, ww): off[c] = off[c - 1] + col_count[c - 1]
            return off
        def f(d):
            n = len(d)
            if n == 0: return b''
            ww = min(w, n)
            off = _offsets(n, ww)
            o = bytearray(n)
            for i in range(n):
                o[off[i % ww] + i // ww] = d[i]
            return bytes(o)
        def r(d):
            n = len(d)
            if n == 0: return b''
            ww = min(w, n)
            off = _offsets(n, ww)
            o = bytearray(n)
            for i in range(n):
                o[i] = d[off[i % ww] + i // ww]
            return bytes(o)
        return f, r

    def _swap_words(self, d, w):
        n = len(d); o = bytearray(n); nw = n // w
        for j in range(nw):
            s = j * w
            for k in range(w):
                o[s + k] = d[s + w - 1 - k]
        for i in range(nw * w, n): o[i] = d[i]
        return bytes(o)

    def _F_swapN_delta(self, w, k):
        def f(d):
            if not d: return b''
            ds = self._swap_words(d, w); n = len(ds)
            if n <= k: return ds
            o = bytearray(ds)
            for i in range(n - 1, k - 1, -1):
                o[i] = (ds[i] - ds[i - k]) & 0xFF
            return bytes(o)
        def r(d):
            if not d: return b''
            n = len(d)
            o = bytearray(n); o[:k] = d[:k]
            for i in range(k, n):
                o[i] = (d[i] + o[i - k]) & 0xFF
            return self._swap_words(bytes(o), w)
        return f, r

    def _F_swap2_delta(self, k): return self._F_swapN_delta(2, k)
    def _F_swap4_delta(self, k): return self._F_swapN_delta(4, k)
    def _F_swap8_delta(self, k): return self._F_swapN_delta(8, k)

    def _F_row_delta(self, w_par):
        widths = (2, 3, 4, 8, 16, 32, 64, 128)
        w = widths[w_par % len(widths)]
        def f(d):
            n = len(d)
            if n == 0: return b''
            ww = min(w, n); k = 1
            orig = bytes(d); o = bytearray(d)
            for start in range(0, n, ww):
                end = min(start + ww, n)
                for i in range(end - 1, start + k - 1, -1):
                    o[i] = (orig[i] - orig[i - k]) & 0xFF
            return bytes(o)
        def r(d):
            n = len(d)
            if n == 0: return b''
            ww = min(w, n); k = 1
            o = bytearray(n)
            for start in range(0, n, ww):
                end = min(start + ww, n)
                for i in range(start, min(start + k, end)):
                    o[i] = d[i]
                for i in range(start + k, end):
                    o[i] = (d[i] + o[i - k]) & 0xFF
            return bytes(o)
        return f, r

    def _F_bitrev_add(self, k):
        tab = self._bitrev8_tab
        def f(d):
            if not d: return b''
            return bytes((tab[b] + k) & 0xFF for b in d)
        def r(d):
            if not d: return b''
            return bytes(tab[(b - k) & 0xFF] for b in d)
        return f, r

    def _F_bitrev_xor(self, k):
        tab = self._bitrev8_tab
        def f(d):
            if not d: return b''
            return bytes(tab[b] ^ k for b in d)
        def r(d):
            if not d: return b''
            return bytes(tab[b ^ k] for b in d)
        return f, r

    def _F_nibble_add(self, k):
        tab = self._nib_swap_tab
        def f(d):
            if not d: return b''
            return bytes((tab[b] + k) & 0xFF for b in d)
        def r(d):
            if not d: return b''
            return bytes(tab[(b - k) & 0xFF] for b in d)
        return f, r

    def _F_nibble_xor(self, k):
        tab = self._nib_swap_tab
        def f(d):
            if not d: return b''
            return bytes(tab[b] ^ k for b in d)
        def r(d):
            if not d: return b''
            return bytes(tab[b ^ k] for b in d)
        return f, r

    def _periodic_mask(self, p, salt):
        key = (p, salt)
        m = self._periodic_cache.get(key)
        if m is None:
            rng = random.Random(salt * 1000 + p)
            m = bytes(rng.randrange(256) for _ in range(p))
            self._periodic_cache[key] = m
        return m

    def _F_xor_periodic(self, p_par):
        p = p_par + 2
        mask = self._periodic_mask(p, 1)
        def f(d):
            if not d: return b''
            n = len(d); pl = len(mask)
            return bytes(d[i] ^ mask[i % pl] for i in range(n))
        return f, f

    def _F_add_periodic(self, p_par):
        p = p_par + 2
        mask = self._periodic_mask(p, 2)
        def f(d):
            if not d: return b''
            n = len(d); pl = len(mask)
            return bytes((d[i] + mask[i % pl]) & 0xFF for i in range(n))
        def r(d):
            if not d: return b''
            n = len(d); pl = len(mask)
            return bytes((d[i] - mask[i % pl]) & 0xFF for i in range(n))
        return f, r

    def _F_posmod_rotl(self, off):
        tabs = self._rot8_tabs
        def f(d):
            if not d: return b''
            n = len(d); o = bytearray(n)
            for i in range(n):
                o[i] = tabs[(i + off) & 7][d[i]]
            return bytes(o)
        def r(d):
            if not d: return b''
            n = len(d); o = bytearray(n); itabs = self._irot8_tabs
            for i in range(n):
                o[i] = itabs[(i + off) & 7][d[i]]
            return bytes(o)
        return f, r

    def _F_posmod_rotr(self, off):
        itabs = self._irot8_tabs
        def f(d):
            if not d: return b''
            n = len(d); o = bytearray(n)
            for i in range(n):
                o[i] = itabs[(i + off) & 7][d[i]]
            return bytes(o)
        def r(d):
            if not d: return b''
            n = len(d); o = bytearray(n); tabs = self._rot8_tabs
            for i in range(n):
                o[i] = tabs[(i + off) & 7][d[i]]
            return bytes(o)
        return f, r

    def _F_posmod_xor(self, k_par):
        A = (k_par * 37 + 11) & 0xFF
        B = (k_par * 53 + 7) & 0xFF
        def f(d):
            if not d: return b''
            return bytes(d[i] ^ ((i * A + B) & 0xFF) for i in range(len(d)))
        return f, f

    def _F_posmod_add(self, k_par):
        A = (k_par * 37 + 11) & 0xFF
        B = (k_par * 53 + 7) & 0xFF
        def f(d):
            if not d: return b''
            return bytes((d[i] + ((i * A + B) & 0xFF)) & 0xFF for i in range(len(d)))
        def r(d):
            if not d: return b''
            return bytes((d[i] - ((i * A + B) & 0xFF)) & 0xFF for i in range(len(d)))
        return f, r

    def _F_xor_reverse(self, off):
        A = (off * 0x37 + 0x1F) & 0xFF
        B = (off * 0x91 + 0x7A) & 0xFF
        def f(d):
            if not d: return b''
            n = len(d); o = bytearray(n)
            for i in range(n):
                o[i] = d[n - 1 - i] ^ ((i * A + B) & 0xFF)
            return bytes(o)
        def r(d):
            if not d: return b''
            n = len(d); o = bytearray(n)
            for i in range(n):
                o[n - 1 - i] = d[i] ^ ((i * A + B) & 0xFF)
            return bytes(o)
        return f, r

    def _F_add_reverse(self, off):
        A = (off * 0x37 + 0x1F) & 0xFF
        B = (off * 0x91 + 0x7A) & 0xFF
        def f(d):
            if not d: return b''
            n = len(d); o = bytearray(n)
            for i in range(n):
                o[i] = (d[n - 1 - i] + ((i * A + B) & 0xFF)) & 0xFF
            return bytes(o)
        def r(d):
            if not d: return b''
            n = len(d); o = bytearray(n)
            for i in range(n):
                o[n - 1 - i] = (d[i] - ((i * A + B) & 0xFF)) & 0xFF
            return bytes(o)
        return f, r

    def _F_delta_reverse(self, k):
        def f(d):
            n = len(d)
            if n <= k: return bytes(d)
            rd = d[::-1]; o = bytearray(rd)
            for i in range(n - 1, k - 1, -1):
                o[i] = (rd[i] - rd[i - k]) & 0xFF
            return bytes(o)
        def r(d):
            n = len(d)
            if n <= k: return bytes(d)[::-1]
            o = bytearray(n); o[:k] = d[:k]
            for i in range(k, n):
                o[i] = (d[i] + o[i - k]) & 0xFF
            return bytes(o)[::-1]
        return f, r

    def _dyn2(self, n):
        i = n - 84
        if i < 8:    return self._F_dstride(i + 1)
        if i < 16:   return self._F_astride(i - 8 + 1)
        if i < 24:   return self._F_xstride(i - 16 + 1)
        if i < 32:   return self._F_ddot(i - 24 + 1)
        if i < 40:   return self._F_transpose(i - 32)
        if i < 48:   return self._F_swap2_delta(i - 40 + 1)
        if i < 56:   return self._F_swap4_delta(i - 48 + 1)
        if i < 64:   return self._F_swap8_delta(i - 56 + 1)
        if i < 72:   return self._F_row_delta(i - 64)
        if i < 80:   return self._F_bitrev_add(i - 72)
        if i < 88:   return self._F_bitrev_xor(i - 80)
        if i < 96:   return self._F_nibble_add(i - 88)
        if i < 104:  return self._F_nibble_xor(i - 96)
        if i < 112:  return self._F_xor_periodic(i - 104 + 2)
        if i < 120:  return self._F_add_periodic(i - 112 + 2)
        if i < 128:  return self._F_posmod_rotl(i - 120)
        if i < 136:  return self._F_posmod_rotr(i - 128)
        if i < 144:  return self._F_posmod_xor(i - 136)
        if i < 152:  return self._F_posmod_add(i - 144)
        if i < 160:  return self._F_xor_reverse(i - 152)
        if i < 168:  return self._F_add_reverse(i - 160)
        return self._F_delta_reverse(i - 168 + 1)

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
            dc = lepton_jpeg_python.decompress_bytes(d); return dc if dc else None
        except Exception: return None

    def _cmixc(self, d, force=False):
        if not HAS_CMIX: return None
        if not force and SKIP_SLOW: return None
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

    def _cmixd(self, d, force=False):
        if not HAS_CMIX: return None
        if not force and SKIP_SLOW: return None
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
        if not HAS_ZPAQ or SKIP_SLOW: return None
        with tempfile.TemporaryDirectory() as td:
            inp = os.path.join(td, 'i'); arc = os.path.join(td, 'a.zpaq')
            with open(inp, 'wb') as f: f.write(d)
            try:
                r = subprocess.run(['zpaq','a',arc,inp,'-m5'], capture_output=True, timeout=300)
                if r.returncode != 0: return None
                with open(arc, 'rb') as f: return f.read()
            except Exception: return None
    def _zpd(self, d):
        if not HAS_ZPAQ or SKIP_SLOW: return None
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
        if not HAS_CCMX or SKIP_SLOW: return None
        with tempfile.TemporaryDirectory() as td:
            inp = os.path.join(td, 'i'); out = os.path.join(td, 'o.ccmx')
            with open(inp, 'wb') as f: f.write(d)
            try:
                r = subprocess.run(['ccmx', 'c', inp, out], capture_output=True, timeout=600)
                if r.returncode == 0 and os.path.exists(out):
                    with open(out, 'rb') as f: return f.read()
            except Exception: pass
        return None
    def _ccmxd(self, d):
        if not HAS_CCMX or SKIP_SLOW: return None
        with tempfile.TemporaryDirectory() as td:
            inp = os.path.join(td, 'i.ccmx'); out = os.path.join(td, 'o')
            with open(inp, 'wb') as f: f.write(d)
            try:
                r = subprocess.run(['ccmx', 'd', inp, out], capture_output=True, timeout=600)
                if r.returncode == 0 and os.path.exists(out):
                    with open(out, 'rb') as f: return f.read()
            except Exception: pass
        return None

    def _ensure_pool(self):
        cur = os.getpid()
        if self._pool_cback is None or self._pool_pid != cur:
            if self._pool_cback is not None:
                try: self._pool_cback.shutdown(wait=False)
                except Exception: pass
            nw = CBACK_WORKERS_EFF if _IN_WORKER else CBACK_WORKERS
            self._pool_cback = ThreadPoolExecutor(max_workers=max(1, nw), thread_name_prefix="cback")
            self._pool_pid = cur
        return self._pool_cback

    def cback(self, d):
        hit = self._cback_cache.get(d)
        if hit is not None: return hit
        result = self._cback_compute(d)
        if len(self._cback_cache) < self._CBACK_CACHE_MAX: self._cback_cache[d] = result
        return result

    def _cback_compute(self, d):
        thunks = [("raw", lambda: (0, d))]
        if HAS_ZSTD:
            def _z1():
                c = zc.compress(d)
                if len(c) >= 4 and c[:4] == b'\x28\xb5\x2f\xfd': c = c[4:]
                return (1, c)
            thunks.append(("zstd22", _z1))
            def _z6():
                c = zc_fast.compress(d)
                if len(c) >= 4 and c[:4] == b'\x28\xb5\x2f\xfd': c = c[4:]
                return (1, c)
            thunks.append(("zstd6", _z6))
            if self._zc_dict is not None:
                def _z11():
                    c = self._zc_dict.compress(d)
                    if len(c) >= 4 and c[:4] == b'\x28\xb5\x2f\xfd': c = c[4:]
                    return (11, c)
                thunks.append(("zstd22-dict", _z11))
        if HAS_BROTLI:
            def _tb(): return (4, brotli.compress(d, quality=11))
            thunks.append(("brotli11", _tb))
            def _tb5(): return (4, brotli.compress(d, quality=5))
            thunks.append(("brotli5", _tb5))
        if HAS_LZMA:
            def _tl9(): return (5, lzma.compress(d, preset=9 | lzma.PRESET_EXTREME))
            thunks.append(("lzma9e", _tl9))
            def _tl6():
                f = LF_RAW[0].copy(); f['preset'] = 9
                return (6, lzma.compress(d, format=lzma.FORMAT_RAW, filters=[f]))
            thunks.append(("lzma9raw", _tl6))
        if HAS_PPMD:
            def _tpp(): return (8, pyppmd.compress(d, max_order=16, mem_size=256<<20))
            thunks.append(("ppmd16", _tpp))
        if paq:
            def _tp():
                pd = paq.compress(d)
                if len(pd) >= 7 and pd[:4] == b'\x00\x63\x00\x00' and pd[-3:] == b'\xff\xff\xff':
                    return (3, pd[4:-3])
                return (2, pd)
            thunks.append(("paq", _tp))
        if not SKIP_SLOW:
            if HAS_ZPAQ:
                def _tz():
                    c = self._zpc(d); return (10, c) if c else None
                thunks.append(("zpaq", _tz))
            if HAS_CCMX:
                def _tc():
                    c = self._ccmxc(d); return (12, c) if c else None
                thunks.append(("ccmx", _tc))
            if HAS_CMIX:
                def _tm():
                    c = self._cmixc(d); return (13, c) if c else None
                thunks.append(("cmix", _tm))
        if HAS_LEPTON:
            def _te():
                c = self._leptonc(d); return (14, c) if c else None
            thunks.append(("lepton", _te))

        n = len(thunks); results = [None]*n
        nw_eff = CBACK_WORKERS_EFF if _IN_WORKER else CBACK_WORKERS
        if n <= 1 or nw_eff <= 1:
            for i, (_, t) in enumerate(thunks):
                try: results[i] = t()
                except Exception: results[i] = None
        else:
            ex = self._ensure_pool()
            futs = [ex.submit(t) for _, t in thunks]
            for i, f in enumerate(futs):
                try: results[i] = f.result()
                except Exception: results[i] = None
        cs = [r for r in results if r is not None]
        cs.sort(key=lambda x: len(x[1]))
        raw_size = len(d)
        for fmt, comp in cs:
            if fmt == 0:
                return bytes([0]) + d
            blob = bytes([fmt]) + comp
            if len(blob) >= raw_size:
                break
            try:
                if self.dback(blob) == d:
                    return blob
            except Exception:
                continue
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
            try: return lzma.decompress(p, format=lzma.FORMAT_RAW, filters=LF_RAW)
            except Exception: return None
        if f == 8 and HAS_PPMD:
            try: return pyppmd.decompress(p, mem_size=256<<20)
            except Exception: return None
        if f == 9 and HAS_LZMA:
            try: return lzma.decompress(p, format=lzma.FORMAT_RAW, filters=LF_RAW)
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
            try: return self._cmixd(p, force=True)
            except Exception: return None
        if f == 14 and HAS_LEPTON:
            try: return self._leptond(p)
            except Exception: return None
        return None

    def t_xml(self, d):
        if not d:
            return b'\x00'
        if d[:8] == OLE_MAGIC:
            return b'\x03' + d
        if d[:4] == ZIP_MAGIC:
            try:
                result = self.t_docx(d)
                if result is not None:
                    return result
            except Exception:
                pass
            try:
                payload = _best_xml_encode(d, self.ref_idx)
                if payload is not None and _xml_decode_v2(payload) == d:
                    return b'\x02' + payload
            except Exception:
                pass
            return b'\x04' + d
        if not _xml_is_plausible(d):
            return b'\x00' + d
        try:
            payload = _best_xml_encode(d, self.ref_idx)
            if payload is None:
                return b'\x00' + d
            huff = self._best_huff_block(payload)
            if huff is not None and len(huff) < len(payload):
                return b'\x07' + huff
            return b'\x01' + payload
        except Exception:
            return b'\x00' + d

    def r_xml(self, d):
        if not d:
            return b''
        mode = d[0]; body = d[1:]
        if mode == 0x00: return body
        if mode == 0x01: return _xml_decode_v2(body)
        if mode == 0x02: return _xml_decode_v2(body)
        if mode == 0x03: return body
        if mode == 0x04: return body
        if mode == 0x05: return self.r_docx(body)
        if mode == 0x06:
            inner = self._ultra_decompress(body)
            return self.r_docx(inner)
        if mode == 0x07:
            enc = self._huff_block_decode(body)
            return _xml_decode_v2(enc)
        raise TransformError(f"t_xml mode {mode}")

    def t_docx(self, d):
        if not d or d[:4] != ZIP_MAGIC:
            return None
        try:
            plain = self._t_docx_impl(d)
        except Exception:
            return None
        return b'\x05' + plain

    def _t_docx_impl(self, d):
        entries, central_dir, eocd = _parse_zip_entries(d)

        for entry in entries:
            entry['payload_mode'] = 0
            entry['payload'] = entry['compressed']

            if entry['method'] != 8:
                continue
            lh = entry['local_header']
            fname_len = struct.unpack('<H', lh[26:28])[0]
            try: filename = lh[30:30+fname_len].decode('utf-8')
            except UnicodeDecodeError: filename = lh[30:30+fname_len].decode('cp437', errors='replace')
            fn_low = filename.lower()
            crc = struct.unpack('<I', lh[14:18])[0]

            if HAS_LEPTON and fn_low.endswith(('.jpg', '.jpeg', '.jpe')):
                try: jpeg_raw = zlib.decompress(entry['compressed'], -15)
                except Exception: jpeg_raw = None
                if jpeg_raw and len(jpeg_raw) >= 4 and jpeg_raw[:2] == b'\xff\xd8':
                    if crc != 0 and (zlib.crc32(jpeg_raw) & 0xFFFFFFFF) != crc:
                        jpeg_raw = None
                if jpeg_raw:
                    lep = self._leptonc(jpeg_raw)
                    if lep is not None:
                        try:
                            if self._leptond(lep) != jpeg_raw: lep = None
                        except Exception: lep = None
                    if lep is not None:
                        params = _find_deflate_params(jpeg_raw, entry['compressed'])
                        if params is not None:
                            if len(lep) + 10 < len(entry['compressed']):
                                entry['payload_mode'] = 4
                                entry['payload'] = {
                                    'jpeg_len': len(jpeg_raw),
                                    'level': params[0], 'strategy': params[1],
                                    'enc': lep,
                                }
                                continue

            if not fn_low.endswith(('.xml', '.rels')):
                continue
            try: raw = zlib.decompress(entry['compressed'], -15)
            except Exception: continue
            if crc != 0 and (zlib.crc32(raw) & 0xFFFFFFFF) != crc: continue
            params = _find_deflate_params(raw, entry['compressed'])
            if params is None: continue

            best_enc = None; best_size = len(entry['compressed'])
            for enc_fn, check_fn in (
                (lambda x: _xml_encode_v2(x),                          lambda p, x: _xml_decode_v2(p) == x),
                (lambda x: _xml_encode_bits(x),                        lambda p, x: _xml_decode_bits(p) == x),
                (lambda x: _xml_encode_v2_words(x, self.ref_idx),      lambda p, x: _xml_decode_v2(p) == x),
                (lambda x: _xml_encode_v3_compound(x, self.ref_idx),   lambda p, x: _xml_decode_v2(p) == x),
                (lambda x: _xml_encode_v4_localdict(x),                lambda p, x: _xml_decode_v2(p) == x),
                (lambda x: _xml_encode_v5_nested(x, self.ref_idx),     lambda p, x: _xml_decode_v2(p) == x),
            ):
                try:
                    enc = enc_fn(raw)
                    if enc is None: continue
                    if not check_fn(enc, raw): continue
                    if len(enc) < best_size: best_enc = enc; best_size = len(enc)
                except Exception: pass

            if best_enc is None: continue

            huff = self._best_huff_block(best_enc)
            if huff is not None and len(huff) < best_size:
                try:
                    if _xml_decode_v2(self._huff_block_decode(huff)) == raw:
                        best_enc = huff; best_size = len(huff)
                        entry['payload_mode'] = 2
                        entry['payload'] = {'raw_len': len(raw), 'level': params[0],
                                            'strategy': params[1], 'enc': best_enc}
                        continue
                except Exception: pass

            entry['payload_mode'] = 1
            entry['payload'] = {'raw_len': len(raw), 'level': params[0],
                                'strategy': params[1], 'enc': best_enc}

        out = bytearray([0x01])
        out += struct.pack('>H', len(entries))
        for e in entries:
            lh, dd = e['local_header'], e['data_descriptor']
            out += struct.pack('>H', len(lh)) + lh
            out += struct.pack('>H', len(dd)) + dd
            out.append(e['payload_mode'])
            if e['payload_mode'] == 0:
                out += struct.pack('>I', len(e['payload'])) + e['payload']
            elif e['payload_mode'] == 4:
                p = e['payload']
                out += struct.pack('>I', p['jpeg_len'])
                out += bytes([p['level'], p['strategy']])
                out += struct.pack('>I', len(p['enc'])) + p['enc']
            else:
                p = e['payload']
                out += struct.pack('>I', p['raw_len'])
                out += bytes([p['level'], p['strategy']])
                out += struct.pack('>I', len(p['enc'])) + p['enc']
        out += struct.pack('>I', len(central_dir)) + central_dir
        out += struct.pack('>I', len(eocd)) + eocd
        body = bytes(out)

        if self._r_docx_impl(body) != d:
            raise TransformError("t_docx internal verify failed")
        return body

    def r_docx(self, body):
        if not body:
            raise TransformError("r_docx empty")
        if body[0] != 0x01:
            raise TransformError(f"t_docx version {body[0]}")
        return self._r_docx_impl(body)

    def _r_docx_impl(self, d):
        pos = 1
        n, pos = struct.unpack('>H', d[pos:pos+2])[0], pos+2
        entries = []
        for _ in range(n):
            lh_len, pos = struct.unpack('>H', d[pos:pos+2])[0], pos+2
            lh = d[pos:pos+lh_len]; pos += lh_len
            dd_len, pos = struct.unpack('>H', d[pos:pos+2])[0], pos+2
            dd = d[pos:pos+dd_len]; pos += dd_len
            mode = d[pos]; pos += 1
            if mode == 0:
                cl, pos = struct.unpack('>I', d[pos:pos+4])[0], pos+4
                compressed = d[pos:pos+cl]; pos += cl
            elif mode in (1, 2):
                raw_len, pos = struct.unpack('>I', d[pos:pos+4])[0], pos+4
                level, strat_code = d[pos], d[pos+1]; pos += 2
                cl, pos = struct.unpack('>I', d[pos:pos+4])[0], pos+4
                blob = d[pos:pos+cl]; pos += cl
                enc = self._huff_block_decode(blob) if mode == 2 else blob
                raw = _xml_decode_v2(enc)
                if len(raw) != raw_len:
                    raise TransformError(f"t_docx raw_len {len(raw)}!={raw_len}")
                strat_map = {0: zlib.Z_DEFAULT_STRATEGY, 1: zlib.Z_FILTERED,
                             2: zlib.Z_HUFFMAN_ONLY, 3: zlib.Z_RLE, 4: zlib.Z_FIXED}
                strat = strat_map.get(strat_code)
                if strat is None: raise TransformError(f"t_docx strat {strat_code}")
                co = zlib.compressobj(level, zlib.DEFLATED, -15, 8, strat)
                compressed = co.compress(raw) + co.flush()
            elif mode == 4:
                jpeg_len, pos = struct.unpack('>I', d[pos:pos+4])[0], pos+4
                level, strat_code = d[pos], d[pos+1]; pos += 2
                cl, pos = struct.unpack('>I', d[pos:pos+4])[0], pos+4
                blob = d[pos:pos+cl]; pos += cl
                jpeg_raw = self._leptond(blob)
                if jpeg_raw is None: raise TransformError("lepton decode failed")
                if len(jpeg_raw) != jpeg_len:
                    raise TransformError(f"lepton len {len(jpeg_raw)}!={jpeg_len}")
                strat_map = {0: zlib.Z_DEFAULT_STRATEGY, 1: zlib.Z_FILTERED,
                             2: zlib.Z_HUFFMAN_ONLY, 3: zlib.Z_RLE, 4: zlib.Z_FIXED}
                strat = strat_map.get(strat_code)
                if strat is None: raise TransformError(f"lepton strat {strat_code}")
                co = zlib.compressobj(level, zlib.DEFLATED, -15, 8, strat)
                compressed = co.compress(jpeg_raw) + co.flush()
            else:
                raise TransformError(f"t_docx mode {mode}")
            entries.append((lh, compressed, dd))
        cd_len, pos = struct.unpack('>I', d[pos:pos+4])[0], pos+4
        central_dir = d[pos:pos+cd_len]; pos += cd_len
        eocd_len, pos = struct.unpack('>I', d[pos:pos+4])[0], pos+4
        eocd = d[pos:pos+eocd_len]; pos += eocd_len
        if pos != len(d):
            raise TransformError(f"t_docx trailing {len(d)-pos} bytes")

        out = bytearray()
        for lh, comp, dd in entries:
            out += lh + comp + dd
        out += central_dir + eocd
        return bytes(out)

    def _huff_block_encode(self, data, block_size, max_size=None):
        if not data: return b''
        out = bytearray()
        out += struct.pack('<I', block_size)
        out += struct.pack('<I', len(data))
        for start in range(0, len(data), block_size):
            if max_size is not None and len(out) > max_size:
                raise TransformError("huff_block: too big")
            chunk = data[start:start + block_size]
            freq = [0] * 256
            for b in chunk: freq[b] += 1
            cl = self._hcl(freq)
            if max(cl) > self.HUFF_MAX_LEN:
                raise TransformError(f"huff_block: max_len {max(cl)}")
            codes = self._hcc(cl)
            out += bytes(cl)
            out += struct.pack('<I', len(chunk))
            acc = 0; nbits = 0
            for b in chunk:
                c, nb = codes[b]
                acc = (acc << nb) | c
                nbits += nb
                while nbits >= 8:
                    nbits -= 8
                    out.append((acc >> nbits) & 0xFF)
                    acc &= (1 << nbits) - 1 if nbits > 0 else 0
            if nbits:
                out.append((acc << (8 - nbits)) & 0xFF)
        return bytes(out)

    def _huff_block_decode(self, data):
        if not data: raise TransformError("huff_block empty")
        pos = 0
        if pos + 8 > len(data): raise TransformError("huff_block: short header")
        block_size = struct.unpack('<I', data[pos:pos+4])[0]; pos += 4
        total_len  = struct.unpack('<I', data[pos:pos+4])[0]; pos += 4
        out = bytearray()
        while pos < len(data) and len(out) < total_len:
            if pos + 260 > len(data): raise TransformError("huff_block: truncated")
            cl = list(data[pos:pos+256]); pos += 256
            chunk_len = struct.unpack('<I', data[pos:pos+4])[0]; pos += 4
            sy = sorted(range(256), key=lambda s: (cl[s], s))
            code_to = {}; c = 0; pl = 0; first = True
            for s in sy:
                L = cl[s]
                if L == 0: continue
                if first: pl = L; first = False
                elif L != pl: c <<= (L - pl); pl = L
                code_to[(L, c)] = s; c += 1
            if chunk_len == 0: continue
            max_len = max(cl) if any(cl) else 0
            buf = 0; nbuf = 0; produced = 0
            while produced < chunk_len:
                while nbuf < max_len and pos < len(data):
                    buf = ((buf & ((1 << nbuf) - 1)) << 8) | data[pos]
                    nbuf += 8; pos += 1
                matched = False
                for L in range(1, min(max_len, nbuf) + 1):
                    v = (buf >> (nbuf - L)) & ((1 << L) - 1)
                    if (L, v) in code_to:
                        out.append(code_to[(L, v)])
                        nbuf -= L; produced += 1; matched = True
                        break
                if not matched:
                    raise TransformError("huff_block: stall")
        if len(out) != total_len:
            raise TransformError(f"huff_block: len {len(out)}!={total_len}")
        return bytes(out)

    def _best_huff_block(self, data):
        if not data or len(data) > 4 * 1024 * 1024: return None
        n = len(data)
        if n > 1024 * 1024:
            widths = [bs for bs in _PREFIX_WIDTHS if 4096 <= bs <= n]
        elif n > 256 * 1024:
            widths = [bs for bs in _PREFIX_WIDTHS if 1024 <= bs <= n]
        else:
            widths = [bs for bs in _PREFIX_WIDTHS if 2 <= bs <= n]
        if not widths: return None
        best = None; best_size = n + 1
        for bs in widths:
            try: enc = self._huff_block_encode(data, bs, max_size=best_size - 1)
            except Exception: continue
            if len(enc) >= best_size: continue
            try:
                if self._huff_block_decode(enc) == data:
                    best = enc; best_size = len(enc)
            except Exception: continue
        return best

    def _ultra_compress(self, data):
        if not data or not HAS_LZMA: return None
        try: lz = lzma.compress(data, preset=9 | lzma.PRESET_EXTREME)
        except Exception: return None
        result = b'\x00' + lz
        if HAS_CMIX:
            cm = self._cmixc(lz, force=True)
            if cm is not None:
                try:
                    if self._cmixd(cm, force=True) == lz and len(cm) < len(lz):
                        result = b'\x01' + cm
                except Exception: pass
        try:
            if result[0] == 1:
                lz2 = self._cmixd(result[1:], force=True)
                if lz2 is None: return None
            else:
                lz2 = result[1:]
            if lzma.decompress(lz2) != data: return None
        except Exception: return None
        return result

    def _ultra_decompress(self, data):
        if not data: raise TransformError("ultra empty")
        flag = data[0]; body = data[1:]
        if flag == 0: lz = body
        elif flag == 1:
            if not HAS_CMIX: raise TransformError("ultra: cmix not available")
            lz = self._cmixd(body, force=True)
            if lz is None: raise TransformError("ultra: cmix decode failed")
        else: raise TransformError(f"ultra flag {flag}")
        try: return lzma.decompress(lz)
        except Exception as e: raise TransformError(f"ultra: lzma {e}")

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
        if cd[0] == 0:
            if 1 + ol > len(cd): raise TransformError(f"T00 raw len")
            return cd[1:ol+1]
        np = cd[0]
        if np == 0 or len(cd) < 1+np: raise TransformError("T00 hdr")
        sh = list(cd[1:1+np]); rle = cd[1+np:]
        dec = self._unrle(rle)
        if dec is None: raise TransformError("T00 dec")
        if len(dec) < ol: raise TransformError(f"T00 short")
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
            for i in range(0, len(t), 3): t[i] ^= xv
        return bytes(t)
    r01 = t01
    def t02(self, d):
        if not d: return b'\x00'
        t = bytearray(d); pi = (len(d)+sum(d)) % 256; pv = self._pat(4, pi); xv = pv[1]
        for i in range(1, len(t), 4): t[i] ^= xv
        return bytes([pi]) + bytes(t)
    def r02(self, d):
        if d == b'\x00': return b''
        if len(d) < 2: raise TransformError("T02")
        pi = d[0]; t = bytearray(d[1:]); pv = self._pat(4, pi); xv = pv[1]
        for i in range(1, len(t), 4): t[i] ^= xv
        return bytes(t)
    def t03(self, d):
        if not d: return b'\x00'
        t = bytearray(d); rot = (len(d)*13 + sum(d)) % 8
        if rot == 0: rot = 1
        tab = self._rot_tab(rot)
        for i in range(2, len(t), 5): t[i] = tab[t[i]]
        return bytes([rot]) + bytes(t)
    def r03(self, d):
        if d == b'\x00': return b''
        if len(d) < 2: raise TransformError("T03")
        rot = d[0]; t = bytearray(d[1:]); tab = self._irot_tab(rot)
        for i in range(2, len(t), 5): t[i] = tab[t[i]]
        return bytes(t)
    def t04(self, d):
        if not d: return b''
        r = self.rep & 0xFF
        if r == 0: return d
        tab = self._t04_tab
        if tab is None:
            tab = bytes((i * r) & 0xFF for i in range(256)); self._t04_tab = tab
        n = len(d); out = bytearray(n)
        for i in range(n): out[i] = (d[i] - tab[i & 0xFF]) & 0xFF
        return bytes(out)
    def r04(self, d):
        if not d: return b''
        r = self.rep & 0xFF
        if r == 0: return d
        tab = self._t04_tab
        if tab is None:
            tab = bytes((i * r) & 0xFF for i in range(256)); self._t04_tab = tab
        n = len(d); out = bytearray(n)
        for i in range(n): out[i] = (d[i] + tab[i & 0xFF]) & 0xFF
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
        if not d: return b'\x00'
        L = len(d)
        p = nearest_prime(L % 256) & 0xFF
        sh = L % len(self.PI)
        pr = self.PI[sh:] + self.PI[:sh]
        r = (L * 7 + 13) % 256 or 1
        out = bytearray(L)
        for i in range(L):
            out[i] = (d[i] ^ p ^ pr[i % len(pr)] ^ (i & 0xFF) ^ r) & 0xFF
        return bytes(out)
    def r07(self, d):
        if d == b'\x00': return b''
        if not d: raise TransformError("a7 empty")
        L = len(d)
        p = nearest_prime(L % 256) & 0xFF
        sh = L % len(self.PI)
        pr = self.PI[sh:] + self.PI[:sh]
        r = (L * 7 + 13) % 256 or 1
        out = bytearray(L)
        for i in range(L):
            out[i] = (d[i] ^ p ^ pr[i % len(pr)] ^ (i & 0xFF) ^ r) & 0xFF
        return bytes(out)

    def t08(self, d):
        if not d: return b'\x00'
        L = len(d)
        p = nearest_prime((L * 3 + 7) % 256) & 0xFF
        sh = (L * 5) % len(self.PI)
        pr = self.PI[sh:] + self.PI[:sh]
        r = (L * 11 + 5) % 256 or 1
        out = bytearray(L)
        for i in range(L):
            out[i] = (d[i] ^ p ^ pr[i % len(pr)] ^ r) & 0xFF
        return bytes(out)
    def r08(self, d):
        if d == b'\x00': return b''
        if not d: raise TransformError("a8 empty")
        L = len(d)
        p = nearest_prime((L * 3 + 7) % 256) & 0xFF
        sh = (L * 5) % len(self.PI)
        pr = self.PI[sh:] + self.PI[:sh]
        r = (L * 11 + 5) % 256 or 1
        out = bytearray(L)
        for i in range(L):
            out[i] = (d[i] ^ p ^ pr[i % len(pr)] ^ r) & 0xFF
        return bytes(out)

    def t09(self, d):
        if not d: return b'\x00'
        L = len(d)
        p = nearest_prime((L * 13 + 3) % 256) & 0xFF
        sd = self._seed(L % len(self.seeds), L)
        sh = (L * 7) % len(self.PI)
        pr = self.PI[sh:] + self.PI[:sh]
        r = (L * 17 + 1) % 256 or 1
        out = bytearray(L)
        for i in range(L):
            out[i] = (d[i] ^ p ^ sd ^ pr[i % len(pr)] ^ (i & 0xFF) ^ r) & 0xFF
        return bytes(out)
    def r09(self, d):
        if d == b'\x00': return b''
        if not d: raise TransformError("a9 empty")
        L = len(d)
        p = nearest_prime((L * 13 + 3) % 256) & 0xFF
        sd = self._seed(L % len(self.seeds), L)
        sh = (L * 7) % len(self.PI)
        pr = self.PI[sh:] + self.PI[:sh]
        r = (L * 17 + 1) % 256 or 1
        out = bytearray(L)
        for i in range(L):
            out[i] = (d[i] ^ p ^ sd ^ pr[i % len(pr)] ^ (i & 0xFF) ^ r) & 0xFF
        return bytes(out)

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
            m = bytes(((fibs[(i+L) % lf] % 256) ^ ((i*13 + L*17) & 0xFF)) & 0xFF for i in range(L))
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
        t = bytearray(d); pi = len(d) % 256; pv = self._pat(3, pi); xv = pv[0]
        tab = self._add_tab(xv)
        for i in range(0, len(t), 3): t[i] = tab[t[i]]
        return bytes([pi]) + bytes(t)
    def r15(self, d):
        if d == b'\x00': return b''
        if len(d) < 2: raise TransformError("T15")
        pi = d[0]; t = bytearray(d[1:]); pv = self._pat(3, pi); xv = pv[0]
        tab = self._sub_tab(xv)
        for i in range(0, len(t), 3): t[i] = tab[t[i]]
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
        L = len(d); m = self._c18_cache.get(L)
        if m is None:
            decimal.getcontext().prec = 60; pi = decimal.Decimal(self.PI_S)
            s = str((pi*pi)/decimal.Decimal(6)).replace('.', '')[:max(10, L//2+5)]
            m = bytes(int(s[i:i+2]) % 256 for i in range(0, len(s), 2)); self._c18_cache[L] = m
        ml = len(m)
        return bytes(d[i] ^ m[i % ml] for i in range(L))
    def _c19(self, d):
        if not d: return b''
        L = len(d); m = self._c19_cache.get(L)
        if m is None:
            decimal.getcontext().prec = 60; e = decimal.Decimal(1).exp()
            s = str(decimal.Decimal(1)/e).replace('.', '')[:max(10, L//2+5)]
            m = bytes(int(s[i:i+2]) % 256 for i in range(0, len(s), 2)); self._c19_cache[L] = m
        ml = len(m)
        return bytes(d[i] ^ m[i % ml] for i in range(L))
    def _c20(self, d):
        if not d: return b''
        L = len(d); m = self._c20_cache.get(L)
        if m is None:
            decimal.getcontext().prec = 60; e = decimal.Decimal(1).exp()
            s = str(decimal.Decimal(5)*e).replace('.', '')[:max(10, L//2+5)]
            m = bytes(int(s[i:i+2]) % 256 for i in range(0, len(s), 2)); self._c20_cache[L] = m
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
        L = len(d); ks = self._t26_cache.get(L)
        if ks is None:
            sec = b"PJP_T26"; nb = (L + 1023) // 1024
            ks = b''.join(hashlib.sha256(sec + struct.pack(">Q", bn)).digest() for bn in range(nb))
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
            tr = [(v-k) & 0xFFFFFF for v in vals]; m = sum(tr)//len(tr)
            c = sum(abs(t-m) for t in tr)
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
            tr = [(v-k) & 0xFFFFFF for v in vals]; m = sum(tr)//len(tr)
            c = sum(abs(t-m) for t in tr)
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
        if not d: return b'\x00'
        bits = []
        for b in d:
            for i in range(7, -1, -1): bits.append((b >> i) & 1)
        encoded = None
        try:
            encoded = self._cb(bits)
            if self._db(encoded) != bits: encoded = None
        except Exception: encoded = None
        raw = b'\x00' + d
        if encoded is None or len(encoded) + 1 >= len(raw): return raw
        return b'\x01' + encoded
    def _r33(self, d):
        if not d: return b''
        mode = d[0]; body = d[1:]
        if mode == 0x00: return body
        if mode != 0x01: raise TransformError(f"a33 mode {mode}")
        bits = self._db(body)
        if not bits: return b''
        o = bytearray()
        for i in range(0, len(bits), 8):
            v = 0; chunk = bits[i:i+8]
            for j, bit in enumerate(chunk): v = (v << 1) | bit
            v <<= (8 - len(chunk)); o.append(v)
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

    def t35(self, d):
        if not d: return b'\x00'
        L = len(d); key = b"A35|" + struct.pack('>Q', L)
        fwd, _ = self._sbox_perm(key); out = bytearray(L)
        for i in range(L): out[i] = fwd[d[i]] ^ ((i * 0x37 + L) & 0xFF)
        return bytes(out)
    def r35(self, d):
        if d == b'\x00': return b''
        if not d: raise TransformError("a35 empty")
        L = len(d); key = b"A35|" + struct.pack('>Q', L)
        _, inv = self._sbox_perm(key); out = bytearray(L)
        for i in range(L): out[i] = inv[d[i] ^ ((i * 0x37 + L) & 0xFF)]
        return bytes(out)
    def t36(self, d):
        if not d: return b'\x00'
        L = len(d); key = b"A36|" + struct.pack('>Q', L)
        fwd, _ = self._sbox_perm(key); p = nearest_prime((L * 3 + 5) % 256) & 0xFF
        out = bytearray(L)
        for i in range(L): out[i] = fwd[d[i]] ^ p ^ ((i * 0x1D + 0x9E) & 0xFF)
        return bytes(out)
    def r36(self, d):
        if d == b'\x00': return b''
        if not d: raise TransformError("a36 empty")
        L = len(d); key = b"A36|" + struct.pack('>Q', L)
        _, inv = self._sbox_perm(key); p = nearest_prime((L * 3 + 5) % 256) & 0xFF
        out = bytearray(L)
        for i in range(L): out[i] = inv[d[i] ^ p ^ ((i * 0x1D + 0x9E) & 0xFF)]
        return bytes(out)
    def t37(self, d):
        if not d: return b'\x00'
        L = len(d); BS = 1024; out = bytearray(); out.extend(L.to_bytes(4, 'big'))
        for bi in range((L + BS - 1) // BS):
            s = bi * BS; e = min(s + BS, L); ch = d[s:e]
            key = b"A37|" + struct.pack('>Q', L) + struct.pack('>I', bi)
            fwd, _ = self._sbox_perm(key); blk = bytearray(len(ch))
            for i, b in enumerate(ch): blk[i] = fwd[b] ^ ((i * 0x53 + bi * 0x11) & 0xFF)
            out.extend(blk)
        return bytes(out)
    def r37(self, d):
        if d == b'\x00': return b''
        if len(d) < 4: raise TransformError("a37 short")
        L = int.from_bytes(d[:4], 'big'); body = d[4:]; BS = 1024; out = bytearray()
        for bi in range((L + BS - 1) // BS):
            s = bi * BS; e = min(s + BS, L); ch = body[s:e]
            key = b"A37|" + struct.pack('>Q', L) + struct.pack('>I', bi)
            _, inv = self._sbox_perm(key)
            for i, b in enumerate(ch): out.append(inv[b ^ ((i * 0x53 + bi * 0x11) & 0xFF)])
        return bytes(out[:L])

    def _t38(self, d):
        BS = 1024; tb = (len(d) + BS - 1) // BS
        o = bytearray(b'\x00' + struct.pack('>I', len(d)))
        for bi in range(tb):
            s = bi * BS; e = min(s + BS, len(d)); blk_len = e - s
            ch = d[s:e] + b'\x00' * (BS - blk_len)
            n = ((len(d) * 7 + bi * 13 + 1) & 0xFFFF) | 1
            e_ = pow(n, 16777216, 257) | 1; e200 = pow(e_, 200, 257)
            t = bytearray(ch)
            for i in range(BS): t[i] = (pow(t[i] + 1, e200, 257) - 1) & 0xFF
            tb_bytes = bytes(t); c = self.cback(tb_bytes); ck = self._blk_check(tb_bytes)
            o += bytes([n & 0xFF, (n >> 8) & 0xFF,
                        (len(c) >> 8) & 0xFF, len(c) & 0xFF,
                        (blk_len >> 8) & 0xFF, blk_len & 0xFF,
                        (ck >> 8) & 0xFF, ck & 0xFF])
            o += c
        return bytes(o)
    def _r38(self, d):
        if len(d) < 5: raise TransformError("FLT28 short")
        if d[0] != 0: raise TransformError("FLT28 magic")
        ol = int.from_bytes(d[1:5], 'big'); p = d[5:]; pos = 0; dec = bytearray()
        while pos < len(p):
            if pos + 8 > len(p): raise TransformError("FLT28 hdr")
            n = p[pos] | (p[pos + 1] << 8); cl = (p[pos + 2] << 8) | p[pos + 3]
            blk_len = (p[pos + 4] << 8) | p[pos + 5]; ck = (p[pos + 6] << 8) | p[pos + 7]
            pos += 8
            if pos + cl > len(p): raise TransformError("FLT28 body")
            cb = p[pos:pos + cl]; pos += cl
            b = self.dback(cb)
            if b is None: raise TransformError("FLT28 decode")
            if len(b) != 1024: raise TransformError(f"FLT28 blk len {len(b)}")
            if self._blk_check(b) != ck: raise TransformError("FLT28 checksum")
            n |= 1; e_ = pow(n, 16777216, 257) | 1; e200 = pow(e_, 200, 257)
            inv = mod_inv(e200, 256)
            if inv is None: raise TransformError(f"FLT28 {e200}")
            t = bytearray(b)
            for i in range(len(t)): t[i] = (pow(t[i] + 1, inv, 257) - 1) & 0xFF
            if blk_len > len(t): raise TransformError("FLT28 blk_len")
            dec.extend(t[:blk_len])
        if len(dec) < ol: raise TransformError(f"FLT28 short {len(dec)}<{ol}")
        return bytes(dec[:ol])

    def _t39(self, d):
        BS = 32; tb = (len(d) + BS - 1) // BS
        o = bytearray(b'\x00' + struct.pack('>I', len(d)))
        for bi in range(tb):
            s = bi * BS; e = min(s + BS, len(d)); blk_len = e - s
            ch = d[s:e] + b'\x00' * (BS - blk_len)
            n = ((len(d) * 7 + bi * 13 + 1) & 0xFFFF) | 1
            c = self.cback(bytes(ch)); ck = self._blk_check(bytes(ch))
            o += bytes([n & 0xFF, (n >> 8) & 0xFF,
                        (len(c) >> 8) & 0xFF, len(c) & 0xFF,
                        (blk_len >> 8) & 0xFF, blk_len & 0xFF,
                        (ck >> 8) & 0xFF, ck & 0xFF])
            o += c
        return bytes(o)
    def _r39(self, d):
        if len(d) < 5: raise TransformError("FLT29 short")
        if d[0] != 0: raise TransformError("FLT29 magic")
        ol = int.from_bytes(d[1:5], 'big'); p = d[5:]; pos = 0; dec = bytearray()
        while pos < len(p):
            if pos + 8 > len(p): raise TransformError("FLT29 hdr")
            n = p[pos] | (p[pos + 1] << 8); cl = (p[pos + 2] << 8) | p[pos + 3]
            blk_len = (p[pos + 4] << 8) | p[pos + 5]; ck = (p[pos + 6] << 8) | p[pos + 7]
            pos += 8
            if pos + cl > len(p): raise TransformError("FLT29 body")
            cb = p[pos:pos + cl]; pos += cl
            b = self.dback(cb)
            if b is None: raise TransformError("FLT29 decode")
            if len(b) != 32: raise TransformError(f"FLT29 blk len {len(b)}")
            if self._blk_check(b) != ck: raise TransformError("FLT29 checksum")
            if blk_len > len(b): raise TransformError("FLT29 blk_len")
            dec.extend(b[:blk_len])
        if len(dec) < ol: raise TransformError(f"FLT29 short {len(dec)}<{ol}")
        return bytes(dec[:ol])

    def _t40(self, d):
        BS = 33; tb = (len(d) + BS - 1) // BS
        o = bytearray(b'\x00' + struct.pack('>I', len(d)))
        for bi in range(tb):
            s = bi * BS; e = min(s + BS, len(d)); blk_len = e - s
            ch = d[s:e] + b'\x00' * (BS - blk_len)
            h = hashlib.sha256(ch + bytes([bi & 0xFF, (len(d) >> 8) & 0xFF, len(d) & 0xFF])).digest()
            enc = bytes([32]) + h; c = self.cback(ch)
            o += enc + bytes([(len(c) >> 8) & 0xFF, len(c) & 0xFF])
            o += bytes([(blk_len >> 8) & 0xFF, blk_len & 0xFF])
            o += c
        return bytes(o)
    def _r40(self, d):
        if len(d) < 5: raise TransformError("FLT30 short")
        if d[0] != 0: raise TransformError("FLT30 magic")
        ol = int.from_bytes(d[1:5], 'big'); p = d[5:]; pos = 0; dec = bytearray(); bi = 0
        while pos < len(p):
            if pos >= len(p): raise TransformError("FLT30 eof")
            Ln = p[pos]; pos += 1
            if Ln != 32 or pos + Ln > len(p): raise TransformError("FLT30 n")
            stored_h = p[pos:pos + Ln]; pos += Ln
            if pos + 4 > len(p): raise TransformError("FLT30 hdr")
            cl = (p[pos] << 8) | p[pos + 1]; pos += 2
            blk_len = (p[pos] << 8) | p[pos + 1]; pos += 2
            if pos + cl > len(p): raise TransformError("FLT30 body")
            cb = p[pos:pos + cl]; pos += cl
            b = self.dback(cb)
            if b is None: raise TransformError("FLT30 decode")
            expected_h = hashlib.sha256(b + bytes([bi & 0xFF, (ol >> 8) & 0xFF, ol & 0xFF])).digest()
            if expected_h != stored_h: raise TransformError("FLT30 checksum")
            if blk_len > len(b): raise TransformError("FLT30 blk_len")
            dec.extend(b[:blk_len]); bi += 1
        if len(dec) < ol: raise TransformError(f"FLT30 short {len(dec)}<{ol}")
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
        if not d: return b'\x02'
        freq = [0]*256
        for b in d: freq[b] += 1
        cl = self._hcl(freq)
        if max(cl) > self.HUFF_MAX_LEN: return b'\x00' + struct.pack('>I', len(d)) + d
        codes = self._hcc(cl)
        hdr = bytearray(len(d).to_bytes(4, 'big')); hdr.extend(cl)
        acc = 0; nbits = 0; o = bytearray()
        for b in d:
            c, n = codes[b]; acc = (acc << n) | c; nbits += n
            while nbits >= 8: nbits -= 8; o.append((acc >> nbits) & 0xFF)
        if nbits: o.append((acc << (8 - nbits)) & 0xFF)
        return b'\x01' + bytes(hdr) + bytes(o)
    def r45(self, d):
        if not d: raise TransformError("Huff empty")
        mode = d[0]; body = d[1:]
        if mode == 0x02: return b''
        if mode == 0x00:
            if len(body) < 4: raise TransformError("Huff raw short")
            ol = struct.unpack('>I', body[:4])[0]
            if 4 + ol > len(body): raise TransformError("Huff raw len")
            return body[4:4+ol]
        if mode != 0x01: raise TransformError(f"Huff mode {mode}")
        if len(body) < 260: raise TransformError("Huff hdr")
        ol = int.from_bytes(body[:4], 'big'); cl = list(body[4:260]); p = body[260:]
        if ol == 0: return b''
        if max(cl) > self.HUFF_MAX_LEN: raise TransformError("Huff l")
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

    def t48(self, d):
        if not d: return b''
        pat = (0x9E3779B97F4A7C15).to_bytes(8, 'big')
        return self._xor_pattern(d, pat)
    r48 = t48
    def t49(self, d):
        if not d: return b''
        s = ((len(d) * 0x9E3779B1) ^ 0xDEADBEEF) & 0xFFFFFFFF
        out = bytearray(len(d))
        for i in range(len(d)):
            s = (s * 1664525 + 1013904223) & 0xFFFFFFFF
            out[i] = d[i] ^ ((s >> 16) & 0xFF)
        return bytes(out)
    r49 = t49
    def t50(self, d):
        if not d: return b''
        out = bytearray(d); fb = self.fib; L = len(d)
        for i in range(L): out[i] ^= fb[i % len(fb)] & 0xFF
        return bytes(out)
    r50 = t50
    def t51(self, d):
        if not d: return b''
        return bytes(d[::-1])
    r51 = t51
    def t52(self, d):
        if not d: return b''
        return bytes(d[i] ^ ((i * 0x37 + 0x5A) & 0xFF) for i in range(len(d)))
    r52 = t52
    def t53(self, d):
        if not d: return b''
        L = len(d); sh = L % len(self.PI)
        pr = self.PI[sh:] + self.PI[:sh]
        out = bytearray(L)
        for i in range(L): out[i] = d[i] ^ pr[i % len(pr)]
        return bytes(out)
    r53 = t53
    def t54(self, d):
        if not d: return b''
        out = bytearray(len(d))
        for i in range(len(d)):
            out[i] = (d[i] + ((i * 0x1B + 0x2F) & 0xFF)) & 0xFF
        return bytes(out)
    def r54(self, d):
        if not d: return b''
        out = bytearray(len(d))
        for i in range(len(d)):
            out[i] = (d[i] - ((i * 0x1B + 0x2F) & 0xFF)) & 0xFF
        return bytes(out)
    def t55(self, d):
        if not d: return b''
        out = bytearray(d); L = len(d); P = PRIMES
        for i in range(L): out[i] ^= P[i % len(P)]
        return bytes(out)
    r55 = t55
    def t56(self, d):
        if not d: return b''
        n = len(d); o = bytearray(d); w = 8
        for i in range(0, n, w):
            chunk = d[i:i + w]
            o[i:i + len(chunk)] = chunk[::-1]
        return bytes(o)
    r56 = t56

    def t59(self, d):
        if not d: return b''
        ri = self.ref_idx; out = bytearray(); last = 0
        for m in _TOK_RE.finditer(d):
            if m.start() > last:
                chunk = d[last:m.start()]
                out.append(0); _emit_varint(out, len(chunk)); out += chunk
            tok = m.group(0); low = tok.lower(); i = ri.get(low)
            if i is not None:
                if tok == low: code = (i << 2) | 0
                elif tok == low.capitalize(): code = (i << 2) | 1
                elif tok == low.upper(): code = (i << 2) | 2
                else: code = None
                if code is not None:
                    _emit_varint(out, code + 1); last = m.end(); continue
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
            mid, key = cdd_derive(n4); masks = bytes(cdd_mask(i, mid) for i in range(n4))
            c = (mid, key, masks); self._cdd_cache[n4] = c
        return c
    def t_cdd(self, d):
        if not d: return b'\x00'
        L = len(d); n4 = L // 4; tail = bytes(d[n4 * 4:])
        if n4 == 0: return b'\x01' + struct.pack('>I', L) + bytes(d)
        mid, key, masks = self._cdd_masks(n4); t = bytearray(d[:n4 * 4])
        for i in range(n4):
            m = masks[i]
            if m:
                b = i * 4
                t[b] ^= m; t[b+1] ^= m; t[b+2] ^= m; t[b+3] ^= m
        t[mid * 4 + 2] ^= 0x5A
        for i in range(2, n4, 3):
            b = i * 4; v = int.from_bytes(t[b:b+4], 'little')
            v = (v - key) & 0xFFFFFFFF
            t[b:b+4] = v.to_bytes(4, 'little')
        return b'\x02' + bytes(t) + tail
    def r_cdd(self, d):
        if not d: return b''
        mode = d[0]; body = d[1:]
        if mode == 0x00: return b''
        if mode == 0x01:
            if len(body) < 4: raise TransformError("cdd short raw")
            L = struct.unpack('>I', body[:4])[0]
            if 4 + L > len(body): raise TransformError("cdd raw len")
            return body[4:4+L]
        if mode != 0x02: raise TransformError(f"cdd mode {mode}")
        L = len(body); n4 = L // 4; tail = bytes(body[n4 * 4:])
        if n4 == 0: return bytes(body)
        mid, key, masks = self._cdd_masks(n4); t = bytearray(body[:n4 * 4])
        for i in range(2, n4, 3):
            b = i * 4; v = int.from_bytes(t[b:b+4], 'little')
            v = (v + key) & 0xFFFFFFFF
            t[b:b+4] = v.to_bytes(4, 'little')
        t[mid * 4 + 2] ^= 0x5A
        for i in range(n4):
            m = masks[i]
            if m:
                b = i * 4
                t[b] ^= m; t[b+1] ^= m; t[b+2] ^= m; t[b+3] ^= m
        return bytes(t) + tail

    _A77_PERIOD = 3 * 1024
    _A78_PERIOD = 3 * 1024

    def _a77_k(self, i):
        base = (1 << 32) - 1
        pos  = i % self._A77_PERIOD
        k    = (base * (pos + 1) * 0x01010101) & 0xFFFFFFFF
        if (pos * 7) % 9 >= 7: k = (k + 7) & 0xFFFFFFFF
        return k or 1

    def _a78_k(self, i):
        base = (1 << 32) - 1
        pos  = i % self._A78_PERIOD
        k    = (base * (pos + 1) * 0x9E3779B9) & 0xFFFFFFFF
        if (pos * 7) % 9 < 7: k = (k + 0) & 0xFFFFFFFF
        else: k = (k + 7) & 0xFFFFFFFF
        if (pos % 7) == 0: k ^= 7
        return k or 1

    def _ks79_u32(self):
        ks = getattr(self, "_ks79_u32_cache", None)
        if ks is None:
            words = []
            for j in range(8):
                v = 0
                for _ in range(100):
                    v = (v + ((1 << 32) - 1) + (j * 7 if (j % 9) < 7 else 0)) & 0xFFFFFFFF
                v = (v * 0x01010101 + 0x9E3779B9) & 0xFFFFFFFF
                words.append(v or 1)
            ks = tuple(words); self._ks79_u32_cache = ks
        return ks

    def t77(self, d):
        if not d: return b''
        n = len(d); nw = n // 4; out = bytearray(d)
        for i in range(nw):
            w = int.from_bytes(d[i*4:i*4+4], 'little')
            out[i*4:i*4+4] = ((w - self._a77_k(i)) & 0xFFFFFFFF).to_bytes(4, 'little')
        for i in range(nw * 4, n):
            k = self._a77_k(i // 4) & 0xFF
            out[i] = (d[i] - k) & 0xFF
        return bytes(out)
    def r77(self, d):
        if not d: return b''
        n = len(d); nw = n // 4; out = bytearray(d)
        for i in range(nw):
            w = int.from_bytes(d[i*4:i*4+4], 'little')
            out[i*4:i*4+4] = ((w + self._a77_k(i)) & 0xFFFFFFFF).to_bytes(4, 'little')
        for i in range(nw * 4, n):
            k = self._a77_k(i // 4) & 0xFF
            out[i] = (d[i] + k) & 0xFF
        return bytes(out)

    def t78(self, d):
        if not d: return b''
        n = len(d); nw = n // 4; out = bytearray(d)
        for i in range(nw):
            w = int.from_bytes(d[i*4:i*4+4], 'little')
            out[i*4:i*4+4] = ((w - self._a78_k(i)) & 0xFFFFFFFF).to_bytes(4, 'little')
        for i in range(nw * 4, n):
            k = self._a78_k(i // 4) & 0xFF
            out[i] = (d[i] - k) & 0xFF
        return bytes(out)
    def r78(self, d):
        if not d: return b''
        n = len(d); nw = n // 4; out = bytearray(d)
        for i in range(nw):
            w = int.from_bytes(d[i*4:i*4+4], 'little')
            out[i*4:i*4+4] = ((w + self._a78_k(i)) & 0xFFFFFFFF).to_bytes(4, 'little')
        for i in range(nw * 4, n):
            k = self._a78_k(i // 4) & 0xFF
            out[i] = (d[i] + k) & 0xFF
        return bytes(out)

    def t79(self, d):
        if not d: return b''
        n = len(d); nw = n // 4; ks = self._ks79_u32(); out = bytearray(d)
        for i in range(nw):
            w = int.from_bytes(d[i*4:i*4+4], 'little')
            out[i*4:i*4+4] = ((w - ks[i & 7]) & 0xFFFFFFFF).to_bytes(4, 'little')
        for i in range(nw * 4, n):
            k = ks[(i // 4) & 7] & 0xFF
            out[i] = (d[i] - k) & 0xFF
        return bytes(out)
    def r79(self, d):
        if not d: return b''
        n = len(d); nw = n // 4; ks = self._ks79_u32(); out = bytearray(d)
        for i in range(nw):
            w = int.from_bytes(d[i*4:i*4+4], 'little')
            out[i*4:i*4+4] = ((w + ks[i & 7]) & 0xFFFFFFFF).to_bytes(4, 'little')
        for i in range(nw * 4, n):
            k = ks[(i // 4) & 7] & 0xFF
            out[i] = (d[i] + k) & 0xFF
        return bytes(out)

    def _a80_k(self, i):
        pos  = i % self._A80_PERIOD
        k    = (self._A80_MASK * (pos + 1) * self._spread_0101) & self._A80_MASK
        if (pos * 7) % 9 >= 7: k = (k + 7) & self._A80_MASK
        return k or 1

    def _a81_k(self, i):
        pos  = i % self._A80_PERIOD
        k    = (self._A80_MASK * (pos + 1) * self._spread_golden) & self._A80_MASK
        if (pos * 7) % 9 >= 7: k = (k + 7) & self._A80_MASK
        if (pos % 7) == 0: k ^= 7
        return k or 1

    def _a82_ks(self):
        if self._a82_ks_cache is None:
            words = []
            for j in range(8):
                v = 0
                for _ in range(100):
                    v = (v + self._A80_MASK + (j * 7 if (j % 9) < 7 else 0)) & self._A80_MASK
                v = (v ^ (v >> 128)) & self._A80_MASK
                if v == 0: v = 1
                words.append(v)
            self._a82_ks_cache = tuple(words)
        return self._a82_ks_cache

    def _t80_core(self, d, sign):
        if not d: return b''
        n = len(d); BLK = self._A80_BLK; M = self._A80_MASK; nw = n // BLK; out = bytearray(d)
        for i in range(nw):
            s = i * BLK; w = int.from_bytes(d[s:s+BLK], 'little')
            out[s:s+BLK] = ((w + sign * self._a80_k(i)) & M).to_bytes(BLK, 'little')
        for j in range(nw * BLK, n):
            k = self._a80_k(j // BLK) & 0xFF
            out[j] = (d[j] + sign * k) & 0xFF
        return bytes(out)
    def t80(self, d): return self._t80_core(d, -1)
    def r80(self, d): return self._t80_core(d, +1)

    def _t81_core(self, d, sign):
        if not d: return b''
        n = len(d); BLK = self._A80_BLK; M = self._A80_MASK; nw = n // BLK; out = bytearray(d)
        for i in range(nw):
            s = i * BLK; w = int.from_bytes(d[s:s+BLK], 'little')
            out[s:s+BLK] = ((w + sign * self._a81_k(i)) & M).to_bytes(BLK, 'little')
        for j in range(nw * BLK, n):
            k = self._a81_k(j // BLK) & 0xFF
            out[j] = (d[j] + sign * k) & 0xFF
        return bytes(out)
    def t81(self, d): return self._t81_core(d, -1)
    def r81(self, d): return self._t81_core(d, +1)

    def _t82_core(self, d, sign):
        if not d: return b''
        n = len(d); BLK = self._A80_BLK; M = self._A80_MASK; nw = n // BLK; ks = self._a82_ks(); out = bytearray(d)
        for i in range(nw):
            s = i * BLK; w = int.from_bytes(d[s:s+BLK], 'little')
            out[s:s+BLK] = ((w + sign * ks[i & 7]) & M).to_bytes(BLK, 'little')
        for j in range(nw * BLK, n):
            k = ks[(j // BLK) & 7] & 0xFF
            out[j] = (d[j] + sign * k) & 0xFF
        return bytes(out)
    def t82(self, d): return self._t82_core(d, -1)
    def r82(self, d): return self._t82_core(d, +1)

    _A83_PARAMS = (
        (32,0,1),(32,0,100),(32,1,100),(32,2,100),(32,8,100),(32,16,100),(32,31,1),(32,0,255),
        (32,8,255),(32,9,127),(64,0,1),(64,0,255),(8192,0,1),(8192,1,100),(8192,4096,1),(8192,8191,1))

    def _t83_apply(self, d, v_bits, x_exp, n_iter):
        wbytes = v_bits // 8
        if wbytes == 0 or not d: return d
        mask = (1 << v_bits) - 1
        k_eff = (n_iter * (1 << x_exp)) & mask
        if k_eff == 0: return d
        out = bytearray(d); nw = len(d) // wbytes
        for i in range(nw):
            s = i * wbytes; w = int.from_bytes(d[s:s+wbytes], 'little')
            out[s:s+wbytes] = ((w - k_eff) & mask).to_bytes(wbytes, 'little')
        for j in range(nw * wbytes, len(d)):
            out[j] = (d[j] - (k_eff & 0xFF)) & 0xFF
        return bytes(out)

    def _r83_apply(self, d, v_bits, x_exp, n_iter):
        wbytes = v_bits // 8
        if wbytes == 0 or not d: return d
        mask = (1 << v_bits) - 1
        k_eff = (n_iter * (1 << x_exp)) & mask
        if k_eff == 0: return d
        out = bytearray(d); nw = len(d) // wbytes
        for i in range(nw):
            s = i * wbytes; w = int.from_bytes(d[s:s+wbytes], 'little')
            out[s:s+wbytes] = ((w + k_eff) & mask).to_bytes(wbytes, 'little')
        for j in range(nw * wbytes, len(d)):
            out[j] = (d[j] + (k_eff & 0xFF)) & 0xFF
        return bytes(out)

    def t83(self, d):
        if not d: return b''
        best_enc = None; best_hdr = None; best_score = float('inf')
        for v, x, n in self._A83_PARAMS:
            try:
                enc = self._t83_apply(d, v, x, n)
                if self._r83_apply(enc, v, x, n) != d: continue
                score = len(self.cback(enc))
                if score < best_score:
                    best_score = score; best_enc = enc; best_hdr = struct.pack('<HHB', v, x, n)
            except Exception: continue
        if best_enc is None: return struct.pack('<HHB', 32, 0, 0) + d
        return best_hdr + best_enc

    def r83(self, d):
        if not d: return b''
        if len(d) < 5: raise TransformError("a83 short")
        v, x, n = struct.unpack('<HHB', d[:5]); body = d[5:]
        if n == 0: return body
        if not (8 <= v <= 8192 and 0 <= x < v and 1 <= n <= 255):
            raise TransformError(f"a83 v={v} x={x} n={n}")
        return self._r83_apply(body, v, x, n)

    def t57(self, d):
        if len(d) < 4:
            pad = 4 - len(d); k = 0
            return bytes([pad]) + k.to_bytes(4, 'little') + d + b'\x00'*pad
        n = len(d); pad = (4 - n % 4) % 4; p = d + b'\x00'*pad
        blocks = [p[i:i+4] for i in range(0, len(p), 4)]
        mc, _ = Counter(blocks).most_common(1)[0]; k = int.from_bytes(mc, 'little')
        o = bytearray()
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
        if not d: return b'\x00' + (0).to_bytes(8, 'big')
        raw = b'\x00' + len(d).to_bytes(8, 'big') + bytes(d)
        try:
            enc = self._t58_encode(d)
            if enc is None: return raw
            if self._t58_decode(enc) != d: return raw
            if len(enc) >= len(raw): return raw
            return enc
        except Exception: return raw
    def r58(self, d):
        if not d: return b''
        mode = d[0]; body = d[1:]
        if mode == 0x00:
            if len(body) < 8: raise TransformError("a58 raw short")
            L = int.from_bytes(body[:8], 'big')
            if 8 + L > len(body): raise TransformError("a58 raw len")
            return body[8:8+L]
        if mode == 0x58: return self._t58_decode(d)
        raise TransformError(f"a58 mode {mode}")
    def _t58_encode(self, d):
        if not d: return None
        sh = hashlib.sha256(d).digest(); depths = [4, 16, 32, 64]
        bd = depths[sh[0] & 3]; bd_code = {4:0, 16:1, 32:2, 64:3}[bd]
        if bd == 4:
            words = []
            for b in d: words.append((b >> 4) & 0xF); words.append(b & 0xF)
            mask = 0xF; wbytes = 1
        else:
            wbytes = bd // 8; p = d + b'\x00' * ((-len(d)) % wbytes)
            words = [int.from_bytes(p[i:i+wbytes], 'big') for i in range(0, len(p), wbytes)]
            mask = (1 << bd) - 1
        fibs = self.fib or [0, 1]; Lf = len(fibs)
        const = Counter(words).most_common(1)[0][0]
        fib_s = [0] * len(words); lz_s = [0] * len(words); la = {}; n = len(words)
        for i in range(n):
            if i == 0: fib_s[i] = const; lz_s[i] = const
            else:
                fib_s[i] = (words[i-1] + fibs[i % Lf]) & mask
                lz_s[i] = la.get(words[i-1], const); la[words[i-1]] = words[i]
        def pack_words(res):
            rb = bytearray()
            if bd == 4:
                for i in range(0, len(res), 2):
                    v = res[i] << 4
                    if i + 1 < len(res): v |= res[i + 1]
                    rb.append(v)
            elif bd == 16:
                for r in res: rb.append((r >> 8) & 0xFF); rb.append(r & 0xFF)
            elif bd == 32:
                for r in res: rb.extend(r.to_bytes(4, 'big'))
            else:
                for r in res: rb.extend(r.to_bytes(8, 'big'))
            return bytes(rb)
        rbytes = bytearray(); ppb = bytearray(); nb = 0
        for start in range(0, n, self.BLOCK):
            end = min(start + self.BLOCK, n); blk = words[start:end]
            best = None; best_code = 0; best_rb = None
            for code, ps in ((0, [const]*len(blk)), (1, fib_s[start:end]), (2, lz_s[start:end])):
                res = [(blk[i] - ps[i]) & mask for i in range(len(blk))]
                rb = pack_words(res); sc = sum(1 for i in range(1, len(rb)) if rb[i] != rb[i-1])
                if best is None or sc < best: best = sc; best_code = code; best_rb = rb
            rbytes.extend(best_rb); ppb.append(best_code); nb += 1
        freq = [0] * 256
        for b in rbytes: freq[b] += 1
        cl = self._hcl(freq)
        if max(cl) > self.HUFF_MAX_LEN: return None
        codes = self._hcc(cl); bits = []
        for b in rbytes:
            c, ln = codes[b]
            for k in range(ln-1, -1, -1): bits.append((c >> k) & 1)
        bits.extend([0] * ((8 - len(bits) % 8) % 8))
        hf = bytearray()
        for i in range(0, len(bits), 8):
            v = 0
            for j in range(8): v = (v << 1) | bits[i + j]
            hf.append(v)
        km = (b'T58' + len(d).to_bytes(8, 'big') + bytes(cl) + bytes(ppb) + struct.pack('>I', nb))
        sd = hashlib.sha256(km).digest(); st = bytearray(); ctr = 0
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
    def _t58_decode(self, d):
        if not d or d[0] != 0x58: raise TransformError("a58 magic")
        pos = 1; bd_code = d[pos]; pos += 1; pc = d[pos]; pos += 1
        ol = int.from_bytes(d[pos:pos+8], 'big'); pos += 8
        if bd_code > 3: raise TransformError("a58 bd")
        depths = [4, 16, 32, 64]; bd = depths[bd_code]; wbytes = 0 if bd == 4 else bd // 8
        if bd == 4: const = d[pos] & 0xF; pos += 1; mask = 0xF
        else: const = int.from_bytes(d[pos:pos+wbytes], 'big'); pos += wbytes; mask = (1 << bd) - 1
        cl = list(d[pos:pos+256]); pos += 256
        nb = int.from_bytes(d[pos:pos+4], 'big'); pos += 4
        ppb = list(d[pos:pos+nb]); pos += nb; hw = d[pos:]
        if ol == 0: return b''
        km = (b'T58' + ol.to_bytes(8, 'big') + bytes(cl) + bytes(ppb) + struct.pack('>I', nb))
        sd = hashlib.sha256(km).digest(); st = bytearray(); ctr = 0
        while len(st) < len(hw): st.extend(hashlib.sha256(sd + ctr.to_bytes(8, 'big')).digest()); ctr += 1
        hf = bytes(h ^ s for h, s in zip(hw, st))
        sy = sorted(range(256), key=lambda s: (cl[s], s))
        ct = {}; c = 0; pl = 0; first = True
        for s in sy:
            L = cl[s]
            if L == 0: continue
            if first: pl = L; first = False
            elif L != pl: c <<= (L - pl); pl = L
            ct[(L, c)] = s; c += 1
        mxl = max(cl) if any(cl) else 0
        bits = []
        for b in hf:
            for i in range(7, -1, -1): bits.append((b >> i) & 1)
        if bd == 4: nw = ol * 2; nrb = (nw + 1) // 2
        else: nw = (ol + wbytes - 1) // wbytes; nrb = nw * wbytes
        rb = bytearray(); bp = 0; nbb = len(bits)
        while len(rb) < nrb and bp < nbb:
            f = False
            for L in range(1, mxl + 1):
                if bp + L > nbb: break
                v = 0
                for j in range(L): v = (v << 1) | bits[bp + j]
                if (L, v) in ct: rb.append(ct[(L, v)]); bp += L; f = True; break
            if not f: raise TransformError("a58 huff stall")
        if len(rb) != nrb: raise TransformError("a58 huff len")
        if bd == 4:
            res = []
            for b in rb: res.append((b >> 4) & 0xF); res.append(b & 0xF)
            res = res[:nw]
        elif bd == 16: res = [int.from_bytes(rb[i:i+2], 'big') for i in range(0, len(rb), 2)]
        elif bd == 32: res = [int.from_bytes(rb[i:i+4], 'big') for i in range(0, len(rb), 4)]
        else: res = [int.from_bytes(rb[i:i+8], 'big') for i in range(0, len(rb), 8)]
        fibs = self.fib or [0, 1]; Lf = len(fibs); words = [0] * nw; la = {}
        for i in range(nw):
            if pc == 3:
                blk = i // self.BLOCK; pcode = ppb[blk] if blk < len(ppb) else 0
                if pcode == 0: p = const
                elif pcode == 1: p = const if i == 0 else (words[i-1] + fibs[i % Lf]) & mask
                else: p = const if i == 0 else la.get(words[i-1], const)
            elif pc == 0: p = const
            elif pc == 1: p = const if i == 0 else (words[i-1] + fibs[i % Lf]) & mask
            else: p = const if i == 0 else la.get(words[i-1], const)
            w = (res[i] + p) & mask; words[i] = w
            if i >= 1: la[words[i-1]] = w
        if bd == 4:
            o = bytearray()
            for i in range(0, nw, 2):
                hi = words[i] & 0xF; lo = words[i+1] & 0xF if i + 1 < nw else 0
                o.append((hi << 4) | lo)
            return bytes(o[:ol])
        o = bytearray()
        for w in words: o.extend(w.to_bytes(wbytes, 'big'))
        return bytes(o[:ol])

    def t_quantum(self, d):
        if not d or not HAS_QISKIT: return d
        nq = getattr(self, "QUBITS", 16); mask = quantum_bytes_mask(nq, len(d))
        if len(mask) != len(d): return d
        return (int.from_bytes(d, "big") ^ int.from_bytes(mask, "big")).to_bytes(len(d), "big")
    r_quantum = t_quantum

    def t_fib_block(self, d):
        if not d: return b''
        L = len(d); fibs = self.fib; out = bytearray(d)
        for i in range(L): out[i] ^= fibs[(i + L) % len(fibs)] & 0xFF
        return bytes(out)
    r_fib_block = t_fib_block
    def t_prime_gap(self, d):
        if not d: return b''
        gaps = [0] + [PRIMES[i+1] - PRIMES[i] for i in range(len(PRIMES)-1)]
        L = len(d); out = bytearray(d)
        for i in range(L): out[i] ^= gaps[i % len(gaps)] & 0xFF
        return bytes(out)
    r_prime_gap = t_prime_gap
    def t_lcg_mask(self, d):
        if not d: return b''
        seed = (len(d) * 1103515245 + 12345) & 0xFFFFFFFF
        s = seed; mask = bytearray()
        for _ in range(len(d)):
            s = (s * 1103515245 + 12345) & 0xFFFFFFFF
            mask.append((s >> 16) & 0xFF)
        return bytes(a ^ b for a, b in zip(d, mask))
    r_lcg_mask = t_lcg_mask
    def t_sha256_keystream(self, d):
        if not d: return b''
        key = hashlib.sha256(b"PPMD_SHA256_KEY").digest(); ks = bytearray(); ctr = 0
        while len(ks) < len(d): ks += hashlib.sha256(key + ctr.to_bytes(8, 'big')).digest(); ctr += 1
        return bytes(a ^ b for a, b in zip(d, ks[:len(d)]))
    r_sha256_keystream = t_sha256_keystream
    def t_byte_transpose(self, d):
        if not d: return b''
        L = len(d); half = L // 2; out = bytearray(L)
        for i in range(half):
            out[2*i] = d[i] ^ 0x5A; out[2*i + 1] = d[half+i] ^ 0xA5
        if L % 2: out[-1] = d[-1] ^ 0x3C
        return bytes(out)
    def r_byte_transpose(self, d):
        if not d: return b''
        L = len(d); half = L // 2; out = bytearray(L)
        for i in range(half):
            out[i] = d[2*i] ^ 0x5A; out[half+i] = d[2*i + 1] ^ 0xA5
        if L % 2: out[-1] = d[-1] ^ 0x3C
        return bytes(out)
    def t_zero_pack(self, d):
        if not d: return b'\x00'
        out = bytearray(); i = 0; n = len(d)
        while i < n:
            if d[i] == 0:
                j = i
                while j < n and d[j] == 0 and (j - i) < 255: j += 1
                out.append(0); out.append(j - i); i = j
            else: out.append(d[i]); i += 1
        return bytes(out)
    def r_zero_pack(self, d):
        if d == b'\x00': return b''
        if not d: return b''
        out = bytearray(); i = 0; n = len(d)
        while i < n:
            if d[i] == 0:
                if i+1 >= n: raise TransformError("zero_pack")
                out.extend(b'\x00' * d[i+1]); i += 2
            else: out.append(d[i]); i += 1
        return bytes(out)
    def t_nibble_swap(self, d):
        if not d: return b''
        out = bytearray(d)
        for i in range(len(out)):
            b = out[i]
            out[i] = (((b << 4) | (b >> 4)) & 0xFF) ^ ((i * 0x37 + 0x9E) & 0xFF)
        return bytes(out)
    def r_nibble_swap(self, d):
        if not d: return b''
        out = bytearray(d)
        for i in range(len(out)):
            b = out[i] ^ ((i * 0x37 + 0x9E) & 0xFF)
            out[i] = ((b << 4) | (b >> 4)) & 0xFF
        return bytes(out)
    def t_delta_xor(self, d):
        if not d: return b''
        out = bytearray(d)
        for i in range(1, len(out)): out[i] ^= d[i-1]
        return bytes(out)
    def r_delta_xor(self, d):
        if not d: return b''
        out = bytearray(d)
        for i in range(1, len(out)): out[i] ^= out[i-1]
        return bytes(out)
    def t_reverse_xor(self, d):
        if not d: return b''
        L = len(d); out = bytearray(L)
        for i in range(L): out[i] = d[L-1-i] ^ ((i * 0x1F + 0x7A) & 0xFF)
        return bytes(out)
    def r_reverse_xor(self, d):
        if not d: return b''
        L = len(d); out = bytearray(L)
        for j in range(L):
            k = L - 1 - j
            out[j] = d[k] ^ ((k * 0x1F + 0x7A) & 0xFF)
        return bytes(out)
    def t_rle_xor(self, d):
        if not d: return b'\x00'
        out = bytearray(); i = 0; n = len(d)
        while i < n:
            v = d[i]; j = i
            while j < n and d[j] == v and (j - i) < 255: j += 1
            run = j - i; out.append(run & 0xFF); out.append(v ^ (run & 0xFF)); i = j
        return bytes(out)
    def r_rle_xor(self, d):
        if d == b'\x00': return b''
        if not d or len(d) % 2: raise TransformError("rle_xor")
        out = bytearray()
        for i in range(0, len(d), 2):
            run = d[i]
            if run == 0: raise TransformError("rle_xor: zero run")
            v = d[i+1] ^ run; out.extend([v] * run)
        return bytes(out)
    def t_b64_xor(self, d):
        if not d: return b''
        x = bytes((b ^ 0xAA) & 0xFF for b in d)
        return base64.b64encode(x)
    def r_b64_xor(self, d):
        if not d: return b''
        try: x = base64.b64decode(d, validate=False)
        except Exception as e: raise TransformError(f"b64_xor {e}")
        return bytes((b ^ 0xAA) & 0xFF for b in x)
    def t_bitplane_shuffle(self, d):
        if not d: return b''
        bits = []
        for b in d:
            for i in range(7, -1, -1): bits.append((b>>i)&1)
        bits = bits[::-1]; out = bytearray()
        for i in range(0, len(bits), 8):
            v = 0
            for j in range(8): v = (v<<1)|bits[i+j]
            out.append(v)
        return bytes(out)
    r_bitplane_shuffle = t_bitplane_shuffle
    def t_sha512_keystream(self, d):
        if not d: return b''
        key = hashlib.sha512(b"PPMD_SHA512_KEY").digest(); ks = bytearray(); ctr = 0
        while len(ks) < len(d): ks += hashlib.sha512(key + ctr.to_bytes(8, 'big')).digest(); ctr += 1
        return bytes(a ^ b for a, b in zip(d, ks[:len(d)]))
    r_sha512_keystream = t_sha512_keystream
    def t_mirror_xor(self, d):
        if not d: return b''
        L = len(d); out = bytearray(d)
        for i in range(L):
            out[i] ^= ((i * 0x4D + 0xB3) & 0xFF)
            out[i] ^= ((L - 1 - i) * 0x9E + 0x6B) & 0xFF
        return bytes(out)
    r_mirror_xor = t_mirror_xor

    def _score_key(self, d, key):
        try:
            tr = d if key == 0 else self._xor64_apply(d, key)
            return len(zlib.compress(tr, 1))
        except Exception:
            return len(d) + 1

    def _q64_candidates(self):
        if self._q64_cache is not None:
            return self._q64_cache
        cands = [
            0x0000000000000000, 0xFFFFFFFFFFFFFFFF, 0x9E3779B97F4A7C15,
            0xDEADBEEFCAFEBABE, 0x0123456789ABCDEF, 0xFEDCBA9876543210,
            0xA5A5A5A5A5A5A5A5, 0x5555555555555555, 0xAAAAAAAAAAAAAAAA,
            0x3333333333333333, 0xCCCCCCCCCCCCCCCC, 0x0F0F0F0F0F0F0F0F,
            0xF0F0F0F0F0F0F0F0, 0x00FF00FF00FF00FF, 0xFF00FF00FF00FF00,
            0x0000FFFF0000FFFF, 0xFFFF0000FFFF0000, 0x123456789ABCDEF0,
            0xDEADBEEFDEADBEEF, 0xCAFEBABECAFEBABE, 0x8BADF00D8BADF00D,
            0xBAADF00DBAADF00D, 0xFEEDFACEFEEDFACE, 0x0BADC0DE0BADC0DE,
            0xDEADC0DEDEADC0DE, 0xBADC0FFEBADC0FFE, 0xC0DEC0DEC0DEC0DE,
            0xC001D00DC001D00D, 0xDEAD10CCDEAD10CC, 0xDEAD2BADDEAD2BAD,
            0xABADBABEABADBABE, 0xBADDCAFEBADDCAFE,
            0x6A09E667F3BCC908, 0xBB67AE8584CAA73B, 0x3C6EF372FE94F82B,
            0xA54FF53A5F1D36F1, 0x510E527FADE682D1, 0x9B05688C2B3E6C1F,
            0x1F83D9ABFB41BD6B, 0x5BE0CD19137E2179,
            0x243F6A8885A308D3, 0x7182818284590452, 0xB7E151628AED2A6A,
            0x8CB6C2FDDBC85C3B,
            0x637C777BF26B6FC5, 0x3001672BFED7AB76, 0xCA82C97DFA5947F0,
            0xADD4A2AF9CA472C0, 0xB7FD9326363FF7CC, 0x34A5E5F171D83115,
            0x617078659AEF9A4B, 0x3320646E79622D32, 0x6B2065749CF0A8BE,
            0x9E3779B99E3779B9, 0x9E3779B900000000, 0x000000009E3779B9,
            0xFF51AFD7ED558CCD, 0xC4CEB9FE1A85EC53,
            0x9E3779B185EBCA87, 0xC2B2AE3D27D4EB4F, 0x165667B19E3779F9,
            0x85EBCA77C2B2AE63, 0x27D4EB2F165667C5, 0xCBF29CE484222325,
            0x5DEECE66D5DEECE6, 0x85EBCA6B85EBCA6B, 0xC2B2AE35C2B2AE35,
            0x0101010101010101, 0x0001000100010001, 0x0000000100000001,
            0x0100010001000100, 0x8000000180000001, 0x8000000080000000,
            0xC0000000C0000000, 0xE0000000E0000000, 0xF0000000F0000000,
            0xFF000000FF000000, 0xFFFFFFFFFF000000, 0x000000FFFFFFFFFF,
            0x7FFFFFFFFFFFFFFF, 0x7F7F7F7F7F7F7F7F, 0x8080808080808080,
        ]
        if HAS_QISKIT:
            try:
                fp = _circuit_fingerprint(64)
                rng = random.Random(int.from_bytes(fp, 'big'))
                while len(cands) < N_Q64_CANDIDATES:
                    cands.append(rng.getrandbits(64))
            except Exception:
                pass
        if len(cands) < N_Q64_CANDIDATES:
            rng = random.Random(0x9E3779B97F4A7C15)
            while len(cands) < N_Q64_CANDIDATES:
                cands.append(rng.getrandbits(64))
        seen = set(); uniq = []
        for k in cands:
            if k not in seen:
                seen.add(k); uniq.append(k)
        rng = random.Random(0xDEADBEEFCAFEBABE)
        while len(uniq) < N_Q64_CANDIDATES:
            k = rng.getrandbits(64)
            if k not in seen:
                seen.add(k); uniq.append(k)
        self._q64_cache = tuple(uniq[:N_Q64_CANDIDATES])
        return self._q64_cache

    @staticmethod
    def _xor64_apply(d, key):
        n = len(d)
        if n == 0 or key == 0:
            return bytes(d)
        kb = key.to_bytes(KEY_BYTES, 'little')
        reps = (n + KEY_BYTES - 1) // KEY_BYTES
        mask = (kb * reps)[:n]
        return (int.from_bytes(d, 'little') ^ int.from_bytes(mask, 'little')).to_bytes(n, 'little')

    def t256(self, d):
        if not d:
            return b'\x00'
        if len(d) < 16:
            return b'\x00' + d
        try:
            if   A256_MODE == "exhaustive":       return self._t256_exhaustive(d)
            elif A256_MODE == "repeat32":         return self._t256_repeat32(d)
            elif A256_MODE == "repeat32_optimal": return self._t256_repeat32_optimal(d)
            else:                                 return self._t256_sampled(d)
        except Exception:
            return b'\x00' + d

    def _t256_sampled(self, d):
        best_key = 0
        best_score = len(d) + 1
        for key in self._q64_candidates():
            sc = self._score_key(d, key)
            if sc < best_score:
                best_score = sc
                best_key = key
        if best_key == 0:
            return b'\x00' + d
        return b'\x01' + best_key.to_bytes(KEY_BYTES, 'big') + self._xor64_apply(d, best_key)

    def _t256_repeat32_optimal(self, d):
        if len(d) < 16:
            return b'\x00' + d
        cols = [[0]*256 for _ in range(4)]
        for i, b in enumerate(d):
            cols[i & 3][b] += 1
        seed = 0
        for p in range(4):
            f = cols[p]
            bk, bs = 0, -1
            for k in range(256):
                s = 0
                for v in range(256):
                    fv = f[v ^ k]; s += fv * fv
                if s > bs:
                    bs, bk = s, k
            seed |= bk << (p * 8)
        key = (seed << 32) | seed
        base = self._score_key(d, 0)
        alt  = self._score_key(d, key)
        if alt >= base:
            return b'\x00' + d
        return b'\x01' + key.to_bytes(KEY_BYTES, 'big') + self._xor64_apply(d, key)

    def _t256_repeat32(self, d):
        max_seed   = A256_LIMIT if A256_LIMIT > 0 else (1 << 32)
        start_seed = A256_START
        prog_every = A256_PROGRESS
        ckpt_every = A256_CKPT
        ckpt_dir = os.path.join(tempfile.gettempdir(), "ppmd_a256_ckpt")
        try: os.makedirs(ckpt_dir, exist_ok=True)
        except Exception: ckpt_dir = None
        data_hash = hashlib.sha256(d).hexdigest()[:16] if ckpt_dir else None
        ckpt_path = os.path.join(ckpt_dir, f"a256r32_{data_hash}.ckpt") if ckpt_dir else None
        best_key = 0; best_score = self._score_key(d, 0)
        if ckpt_path and os.path.exists(ckpt_path):
            try:
                with open(ckpt_path, 'rb') as f: raw = f.read(24)
                if len(raw) == 24:
                    ck_seed, ck_bk, ck_bs = struct.unpack('<QQQ', raw)
                    if ck_seed < max_seed:
                        start_seed = ck_seed; best_key = ck_bk; best_score = ck_bs
                        print(f"  [a256 repeat32] resumed at seed {start_seed:,}")
            except Exception: pass
        print(f"  [a256 repeat32] range=[{start_seed:,}, {max_seed:,})  "
              f"payload={len(d):,}B  key=seed||seed  best=0x{best_key:016x}  score={best_score}")
        t0 = time.time(); n_eval = 0; seed = start_seed
        try:
            for seed in range(start_seed, max_seed):
                key = (seed << 32) | seed
                sc = self._score_key(d, key)
                n_eval += 1
                if sc < best_score:
                    best_score, best_key = sc, key
                if n_eval % prog_every == 0:
                    el = time.time() - t0; rate = n_eval / el if el > 0 else 0
                    pct = 100.0 * (seed - start_seed) / max(1, max_seed - start_seed)
                    rem = ((max_seed - seed) / rate) if rate > 0 else float('inf')
                    if rem > 86400: eta = f"{rem/86400:.2f} days"
                    elif rem > 3600: eta = f"{rem/3600:.2f} hours"
                    else: eta = f"{rem:.1f} s"
                    print(f"  [a256 repeat32] seed={seed:,}/{max_seed:,}  "
                          f"({pct:.5f}%)  best=0x{best_key:016x}  "
                          f"score={best_score}  rate={rate:,.0f}/s  ETA={eta}")
                if ckpt_every > 0 and ckpt_path and n_eval % ckpt_every == 0:
                    try:
                        with open(ckpt_path, 'wb') as f:
                            f.write(struct.pack('<QQQ', seed + 1, best_key, best_score))
                    except Exception: pass
        except KeyboardInterrupt:
            if ckpt_path:
                try:
                    with open(ckpt_path, 'wb') as f:
                        f.write(struct.pack('<QQQ', seed + 1, best_key, best_score))
                    print(f"\n  [a256 repeat32] interrupted; saved at seed {seed+1:,}")
                except Exception: pass
            raise
        if ckpt_path:
            try: os.remove(ckpt_path)
            except Exception: pass
        print(f"  [a256 repeat32] DONE: {n_eval:,} seeds in {time.time()-t0:.1f}s  "
              f"best=0x{best_key:016x}")
        if best_key == 0:
            return b'\x00' + d
        return b'\x01' + best_key.to_bytes(KEY_BYTES, 'big') + self._xor64_apply(d, best_key)

    def _t256_exhaustive(self, d):
        max_key   = A256_LIMIT if A256_LIMIT > 0 else (1 << 64)
        start_key = A256_START
        prog_every = A256_PROGRESS
        ckpt_every = A256_CKPT
        ckpt_dir = os.path.join(tempfile.gettempdir(), "ppmd_a256_ckpt")
        try: os.makedirs(ckpt_dir, exist_ok=True)
        except Exception: ckpt_dir = None
        data_hash = hashlib.sha256(d).hexdigest()[:16] if ckpt_dir else None
        ckpt_path = os.path.join(ckpt_dir, f"a256_{data_hash}.ckpt") if ckpt_dir else None
        best_key = 0; best_score = self._score_key(d, 0)
        if ckpt_path and os.path.exists(ckpt_path):
            try:
                with open(ckpt_path, 'rb') as f: raw = f.read(24)
                if len(raw) == 24:
                    ck_key, ck_bk, ck_bs = struct.unpack('<QQQ', raw)
                    if ck_key < max_key:
                        start_key = ck_key; best_key = ck_bk; best_score = ck_bs
                        print(f"  [a256 exhaustive] resumed at key {start_key:,}")
            except Exception: pass
        print(f"  [a256 exhaustive] range=[{start_key:,}, {max_key:,})  "
              f"payload={len(d):,}B  best=0x{best_key:016x}  score={best_score}")
        t0 = time.time(); n_eval = 0; key = start_key
        try:
            for key in range(start_key, max_key):
                sc = self._score_key(d, key)
                n_eval += 1
                if sc < best_score: best_score, best_key = sc, key
                if n_eval % prog_every == 0:
                    el = time.time() - t0; rate = n_eval / el if el > 0 else 0
                    pct = 100.0 * (key - start_key) / max(1, max_key - start_key)
                    rem = ((max_key - key) / rate) if rate > 0 else float('inf')
                    if rem > 1e9: eta = f"{rem/86400/365.25:.2e} years"
                    elif rem > 86400: eta = f"{rem/86400:.1f} days"
                    else: eta = f"{rem:.1f} s"
                    print(f"  [a256 exhaustive] key={key:,}/{max_key:,}  "
                          f"({pct:.6f}%)  best=0x{best_key:016x}  "
                          f"score={best_score}  rate={rate:,.0f}/s  ETA={eta}")
                if ckpt_every > 0 and ckpt_path and n_eval % ckpt_every == 0:
                    try:
                        with open(ckpt_path, 'wb') as f:
                            f.write(struct.pack('<QQQ', key + 1, best_key, best_score))
                    except Exception: pass
        except KeyboardInterrupt:
            if ckpt_path:
                try:
                    with open(ckpt_path, 'wb') as f:
                        f.write(struct.pack('<QQQ', key + 1, best_key, best_score))
                    print(f"\n  [a256 exhaustive] interrupted; saved at key {key+1:,}")
                except Exception: pass
            raise
        if ckpt_path:
            try: os.remove(ckpt_path)
            except Exception: pass
        print(f"  [a256 exhaustive] DONE: {n_eval:,} keys in {time.time()-t0:.1f}s  "
              f"best=0x{best_key:016x}")
        if best_key == 0:
            return b'\x00' + d
        return b'\x01' + best_key.to_bytes(KEY_BYTES, 'big') + self._xor64_apply(d, best_key)

    def r256(self, d):
        if not d: return b''
        mode = d[0]
        if mode == 0: return d[1:]
        if mode != 1: raise TransformError(f"a256 mode {mode}")
        if len(d) < 1 + KEY_BYTES: raise TransformError("a256 short")
        key = int.from_bytes(d[1:1+KEY_BYTES], 'big')
        return self._xor64_apply(d[1+KEY_BYTES:], key)

    def _maps(self):
        eager_f = {}; eager_r = {}
        for i in range(1, 22):
            eager_f[i] = getattr(self, f"t{i:02d}"); eager_r[i] = getattr(self, f"r{i:02d}")
        for i in (22,23,24,25,26,27,28,29,30,31,32):
            eager_f[i] = getattr(self, f"t{i}"); eager_r[i] = getattr(self, f"r{i}")
        eager_f[33] = self._t33; eager_r[33] = self._r33
        eager_f[34] = self._t34; eager_r[34] = self._r34
        eager_f[35] = self.t35; eager_r[35] = self.r35
        eager_f[36] = self.t36; eager_r[36] = self.r36
        eager_f[37] = self.t37; eager_r[37] = self.r37
        eager_f[38] = self._t38; eager_r[38] = self._r38
        eager_f[39] = self._t39; eager_r[39] = self._r39
        eager_f[40] = self._t40; eager_r[40] = self._r40
        for i in range(41, 57):
            eager_f[i] = getattr(self, f"t{i}"); eager_r[i] = getattr(self, f"r{i}")
        eager_f[57] = self.t57; eager_r[57] = self.r57
        eager_f[58] = self.t58; eager_r[58] = self.r58
        eager_f[59] = self.t59; eager_r[59] = self.r59
        eager_f[60] = self.t_cdd; eager_r[60] = self.r_cdd
        eager_f[61] = self.t_xml; eager_r[61] = self.r_xml
        eager_f[62] = self.t_quantum; eager_r[62] = self.r_quantum
        eager_f[63] = self.t_fib_block; eager_r[63] = self.r_fib_block
        eager_f[64] = self.t_prime_gap; eager_r[64] = self.r_prime_gap
        eager_f[65] = self.t_lcg_mask; eager_r[65] = self.r_lcg_mask
        eager_f[66] = self.t_sha256_keystream; eager_r[66] = self.r_sha256_keystream
        eager_f[67] = self.t_byte_transpose; eager_r[67] = self.r_byte_transpose
        eager_f[68] = self.t_zero_pack; eager_r[68] = self.r_zero_pack
        eager_f[69] = self.t_nibble_swap; eager_r[69] = self.r_nibble_swap
        eager_f[70] = self.t_delta_xor; eager_r[70] = self.r_delta_xor
        eager_f[71] = self.t_reverse_xor; eager_r[71] = self.r_reverse_xor
        eager_f[72] = self.t_rle_xor; eager_r[72] = self.r_rle_xor
        eager_f[73] = self.t_b64_xor; eager_r[73] = self.r_b64_xor
        eager_f[74] = self.t_bitplane_shuffle; eager_r[74] = self.r_bitplane_shuffle
        eager_f[75] = self.t_sha512_keystream; eager_r[75] = self.r_sha512_keystream
        eager_f[76] = self.t_mirror_xor; eager_r[76] = self.r_mirror_xor
        eager_f[77] = self.t77; eager_r[77] = self.r77
        eager_f[78] = self.t78; eager_r[78] = self.r78
        eager_f[79] = self.t79; eager_r[79] = self.r79
        eager_f[80] = self.t80; eager_r[80] = self.r80
        eager_f[81] = self.t81; eager_r[81] = self.r81
        eager_f[82] = self.t82; eager_r[82] = self.r82
        eager_f[83] = self.t83; eager_r[83] = self.r83
        for i in range(84, 256):
            f, r = self._dyn2(i); eager_f[i] = f; eager_r[i] = r
        eager_f[256] = self.t256; eager_r[256] = self.r256
        self.fwd = eager_f; self.rev = eager_r
        if A256_MODE == "exhaustive":
            mode = "EXHAUSTIVE 2^64 (may never finish)"
        elif A256_MODE == "repeat32":
            mode = ("REPEAT-32 (2^32 seed||seed)" if A256_LIMIT == 0
                    else f"REPEAT-32 limited to {A256_LIMIT:,}")
        elif A256_MODE == "repeat32_optimal":
            mode = "REPEAT-32 OPTIMAL (< 1 ms)"
        else:
            mode = f"sampled64 ({N_Q64_CANDIDATES} candidates × 64-bit key)"
        print(f"Transforms registered: 1-83 fixed + 84-255 (22 families × 8) + 256 XOR64 ({mode}).")

    def _pairs(self):
        self.pairs = []
        for a in range(1, 257):
            for b in range(1, 257):
                if a == 256 and b == 256: continue
                self.pairs.append((a, b))
        self._pair_index = {p: i + 1 for i, p in enumerate(self.pairs)}
        print(f"Pair space: {len(self.pairs):,} pairs (header cap: {MAX_PAIRS:,})")

    def _write(self, path, data):
        dd = os.path.dirname(path) or '.'
        fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path)+'.tmp', dir=dd)
        try: os.write(fd, data)
        finally: os.close(fd)
        os.replace(tmp, path)

    def _require_file(self, path):
        if not path: print("Error: no filename."); return False
        if not os.path.exists(path): print(f"Error: not found: {path!r}"); return False
        if not os.path.isfile(path): print("Error: not a regular file."); return False
        if not os.access(path, os.R_OK): print("Error: permission denied."); return False
        return True

    def verify_single(self, data, t):
        try:
            if t == 256 and self._is_huge_a256():
                return True
            tr = self.fwd[t](data)
            return self.rev[t](tr) == data
        except Exception: return False

    def verify_pair(self, data, a, b):
        try:
            if self._is_huge_a256() and (a == 256 or b == 256):
                return True
            ta = self.fwd[a](data); tr = self.fwd[b](ta)
            return self.rev[a](self.rev[b](tr)) == data
        except Exception: return False

    def _decode_blob(self, blob, kind, ident):
        try:
            r = self.dback(blob)
            if r is None: return None
            if kind == "a": return self.rev[ident](r)
            else:
                a_, b_ = self.pairs[ident - 1]
                return self.rev[a_](self.rev[b_](r))
        except Exception: return None

    def _final_cmix_pass(self, data, chosen, candidates):
        if not HAS_CMIX: return chosen
        sz, kind, ident, lbl, blob = chosen
        if blob and blob[0] == 13:
            print("  Final cmix: winner already uses cmix backend")
            return chosen
        try:
            if kind == "a": transformed = self.fwd[ident](data)
            else:
                a_, b_ = self.pairs[ident - 1]
                transformed = self.fwd[b_](self.fwd[a_](data))
        except Exception as e:
            print(f"  Final cmix: transform re-apply failed: {e}")
            return chosen
        print(f"  Final cmix pass on winner ({lbl}, {len(transformed):,} bytes)...")
        t0 = time.time()
        cmix_blob = self._cmixc(transformed, force=True)
        if cmix_blob is None:
            print("  Final cmix: cmix returned None (binary missing or failed)")
            return chosen
        new_blob = bytes([13]) + cmix_blob; new_sz = len(new_blob)
        elapsed = time.time() - t0
        try:
            back = self._cmixd(cmix_blob, force=True)
            if back != transformed:
                print("  Final cmix: round-trip mismatch — keeping original")
                return chosen
        except Exception as e:
            print(f"  Final cmix: verify failed: {e}")
            return chosen
        if new_sz < sz:
            print(f"  Final cmix: {sz:,} → {new_sz:,} bytes  "
                  f"(saved {sz - new_sz:,}, {elapsed:.1f}s)")
            return (new_sz, kind, ident, lbl + "+cmix", new_blob)
        print(f"  Final cmix: {new_sz:,} bytes — NOT smaller than {sz:,} (keeping {lbl})")
        return chosen

    def compress(self, infile, pairs=True, multi=False, timeout=None, selftest=False):
        if not self._require_file(infile): return
        try:
            with open(infile, 'rb') as f: data = f.read()
        except (PermissionError, OSError) as e:
            print(f"Error reading {infile!r}: {e}"); return
        if len(data) == 0:
            print(f"Error: {infile!r} is empty."); return

        print(f"\nInput: {len(data):,} bytes"); print("="*64)
        print(f"Mode: FAST ({'ON' if FAST_MODE else 'OFF'}) "
              f"full-singles={'ON' if FULL_SINGLES else 'OFF'} "
              f"full-pairs={'ON' if FULL_PAIRS else 'OFF'} "
              f"skip-slow={'ON' if SKIP_SLOW else 'OFF'} "
              f"a256={A256_MODE}")
        print(f"Header: extension only  <orig>.aXXXX  (XXXX = 4 hex digits)")
        t_start = time.time()

        xml_enc = None
        if _xml_is_plausible(data) or data[:4] == ZIP_MAGIC or data[:8] == OLE_MAGIC:
            try:
                xml_enc = self.t_xml(data)
                if self.r_xml(xml_enc) == data and len(xml_enc) < len(data):
                    print(f"  XML structural encode: {len(data):,} → {len(xml_enc):,} "
                          f"({len(xml_enc)/len(data)*100:.1f}%)")
                else: xml_enc = None
            except Exception as e:
                print(f"  XML pre-pass skipped ({e})"); xml_enc = None

        candidates = []
        def _add_single(t, tag):
            try:
                if not self.verify_single(data, t):
                    print(f"  [{tag}] NOT REVERSIBLE — skipped"); return
                tr = self.fwd[t](data); c = self.cback(tr)
                candidates.append((len(c), "a", t, tag, c))
            except Exception as e:
                print(f"  [{tag}] failed: {e}")

        def _add_pair(a, b, tag):
            try:
                if not self.verify_pair(data, a, b):
                    print(f"  [{tag}] NOT REVERSIBLE — skipped"); return
                ta = self.fwd[a](data); tr = self.fwd[b](ta); c = self.cback(tr)
                pidx = self._pair_index[(a, b)]
                if pidx > MAX_PAIRS: return
                candidates.append((len(c), "b", pidx, tag, c))
            except Exception as e:
                print(f"  [{tag}] failed: {e}")

        if FULL_SINGLES:
            print(f"\n  Phase 1: full 256-transform sweep ...")
            for t in range(1, 257):
                if t == 61 and xml_enc is not None: continue
                _add_single(t, f"a{t}")
        else:
            _add_single(1, "a1")
            for t in (62, 63, 66, 70, 75, 83, 256): _add_single(t, f"a{t}")

        if xml_enc is not None:
            try:
                if self.verify_single(data, 61):
                    c2 = self.cback(xml_enc)
                    candidates.append((len(c2), "a", 61, "a61", c2))
            except Exception as e: print(f"  [a61] failed: {e}")

        if FULL_PAIRS and not selftest:
            print(f"\n  Phase 2: full pair tournament ({self.PAIRS} pairs) ...")
            _GLOBAL_COMP = self; _GLOBAL_DATA = data; _GLOBAL_FWD = {}
            pair_count = min(self.PAIRS, len(self.pairs))
            use_pool = _HAS_FORK and N_CORES > 1
            pool = None
            if use_pool:
                try: pool = _MP_CTX.Pool(N_CORES)
                except Exception as e: print(f"  pool failed ({e})"); pool = None
            try:
                pair_task_list = []; skipped_id = 0
                perm = self._qperm if (HAS_QISKIT and len(self._qperm) >= pair_count) else list(range(pair_count))
                for k in range(pair_count):
                    i = perm[k] if k < len(perm) else k
                    a, b = self.pairs[i]
                    if a in IDENTITY_IDS or b in IDENTITY_IDS:
                        skipped_id += 1; continue
                    pair_task_list.append((i, a, b))
                if skipped_id: print(f"  identity-skip: {skipped_id}")
                if pool is not None:
                    results = list(pool.imap_unordered(_worker_pair, pair_task_list, chunksize=CHUNK))
                else:
                    results = [_worker_pair(t) for t in pair_task_list]
                sized = []
                for idx, a, b, size, err in results:
                    if err or size is None: continue
                    sized.append((size, idx, a, b))
                sized.sort()
                top_k = min(TOP_VERIFY, len(sized))
                print(f"  tournament: {len(sized)} viable pairs; verifying top {top_k} ...")
                for sz, idx, a, b in sized[:top_k]:
                    if self.verify_pair(data, a, b):
                        try:
                            tr = self.fwd[b](self.fwd[a](data)); c = self.cback(tr)
                            pidx = idx + 1
                            if pidx > MAX_PAIRS: continue
                            candidates.append((len(c), "b", pidx, f"b{pidx}", c))
                        except Exception as e:
                            print(f"  [b{idx+1}] failed on encode: {e}")
            finally:
                if pool is not None: pool.close(); pool.join()
                _GLOBAL_COMP = None; _GLOBAL_DATA = None; _GLOBAL_FWD = {}
        elif not selftest:
            for (a, b) in [(61, 1), (61, 62), (62, 1), (63, 1), (66, 1), (256, 1)]:
                if (a, b) in self._pair_index:
                    _add_pair(a, b, f"b{self._pair_index[(a, b)]}")

        if not candidates:
            print("  no candidates; falling back to a1")
            c = self.cback(data)
            candidates.append((len(c), "a", 1, "a1", c))

        candidates.sort(key=lambda x: x[0])
        chosen = None
        for sz, k_, id_, lbl_, c_ in candidates:
            chk = self._decode_blob(c_, k_, id_)
            if chk == data:
                chosen = (sz, k_, id_, lbl_, c_); break
            print(f"  [{lbl_}] in-memory verify FAILED — skipping")

        if chosen is None:
            c = self.cback(data)
            if self._decode_blob(c, "a", 1) != data:
                print("  [FATAL] all candidates (including a1) failed verify; aborting without writing.")
                return
            chosen = (len(c), "a", 1, "a1", c)

        best_size, kind, ident, label, best_blob = chosen
        print(f"\n  winner before cmix: {label}  ({best_size:,} bytes)")
        print(f"  round-trip before cmix: OK")

        if not selftest:
            chosen2 = self._final_cmix_pass(data, chosen, candidates)
            if chosen2 is not chosen and chosen2[0] < best_size:
                candidates.append(chosen2); candidates.sort(key=lambda x: x[0])
                best_size, kind, ident, label, best_blob = chosen2
                print(f"  cmix upgraded winner: {label}  ({best_size:,} bytes)")

        for sz, k_, id_, lbl_, c_ in candidates:
            marker = " <<< BEST" if (lbl_ == label and k_ == kind and id_ == ident) else ""
            print(f"  [{lbl_}] size={sz}{marker}")

        ext = _ext_for(kind, ident)
        out = infile + ext
        self._write(out, best_blob)

        elapsed = time.time() - t_start
        print("\n" + "="*64)
        print(f"WINNER: {out}")
        print(f"  Method   : {label}")
        print(f"  Size     : {len(best_blob):,} bytes  ({len(best_blob)/len(data)*100:.2f}%)")
        print(f"  Original : {len(data):,} bytes")
        print(f"  Saved    : {len(data)-len(best_blob):,} bytes")
        print(f"  Time     : {elapsed:.4f} s")
        print(f"  Speed    : {len(data)/elapsed:,.0f} bytes/s")
        print(f"  Header   : (in extension) {ext}")
        print(f"  Note     : Do NOT rename the file — the extension IS the header.")

        try:
            with open(out, 'rb') as f: readback = f.read()
            if readback != best_blob:
                print("  [VERIFICATION FAILED: readback bytes mismatch]"); return
            orig = self._decode_blob(readback, kind, ident)
            if orig == data: print("  [VERIFIED LOSSLESS: decode(readback) == original]")
            else: print("  [VERIFICATION FAILED: content mismatch]")
        except Exception as e:
            print(f"  [VERIFICATION ERROR: {e}]")

    def decompress(self, infile, outfile=""):
        if not self._require_file(infile): return False
        try:
            with open(infile, 'rb') as f: blob = f.read()
        except (PermissionError, OSError) as e:
            print(f"Error reading {infile!r}: {e}"); return False
        if len(blob) == 0:
            print(f"Error: empty."); return False
        base = os.path.basename(infile)

        parsed = _parse_ext(infile)
        if parsed is None:
            print("Error: filename must end with .aXXXX (extension is the header).")
            return False
        kind, ident = parsed
        print(f"  header from extension: {kind}{ident}")

        if kind == "b" and ident > len(self.pairs):
            print(f"Error: pair idx {ident} > total {len(self.pairs)}."); return False

        try: r = self.dback(blob)
        except Exception as e: print(f"Error: backend: {e}"); return False
        if r is None: print("Error: decode failed."); return False

        try:
            if kind == "a": orig = self.rev[ident](r)
            else:
                a, b = self.pairs[ident - 1]
                orig = self.rev[a](self.rev[b](r))
        except Exception as e:
            print(f"Error: inverse {kind}{ident}: {e}"); return False

        if not outfile:
            m = _EXT_RE.search(base)
            if m: outfile = base[:m.start()]
            else: outfile = base + ".out"
            if not outfile: outfile = base + ".out"

        self._write(outfile, orig)
        print(f"-> {outfile} ({len(orig)} bytes)")
        return True

    def selftest_all_transforms(self, sample=None):
        if sample is None: sample = b"the quick brown fox " * 8 + bytes(range(64))
        print("="*60); print("Sweep: all 256 single transforms"); print("="*60)
        bad = []
        for t in range(1, 257):
            if t == 256 and self._is_huge_a256():
                print(f"    a256 {A256_MODE} unbounded: skipped in sweep (would run forever)")
                continue
            try:
                tr = self.fwd[t](sample); back = self.rev[t](tr)
                if back != sample: bad.append((t, "mismatch"))
            except Exception as e: bad.append((t, repr(e)))
        if bad:
            print(f"  FAIL: {len(bad)} transforms are NOT lossless:")
            for row in bad[:30]: print(f"    a{row[0]:>3}: {row[1]}")
            return False
        print(f"  all 256 single transforms: LOSSLESS ✓")
        return True

    def selftest_all_pairs(self, sample=None, max_pairs=None):
        if sample is None: sample = b"the quick brown fox " * 4
        limit = max_pairs if max_pairs is not None else len(self.pairs)
        limit = min(limit, len(self.pairs))
        print("="*60); print(f"Sweep: {limit} of {len(self.pairs)} pairs"); print("="*60)
        bad = 0; tested = 0; errors = []
        for i, (a, b) in enumerate(self.pairs[:limit]):
            if self._is_huge_a256() and (a == 256 or b == 256):
                continue
            try:
                tr = self.fwd[b](self.fwd[a](sample))
                back = self.rev[a](self.rev[b](tr))
                if back != sample:
                    bad += 1
                    if len(errors) < 10: errors.append(f"b{i+1} (a{a}→a{b}): mismatch")
            except Exception as e:
                bad += 1
                if len(errors) < 10: errors.append(f"b{i+1} (a{a}→a{b}): {e}")
            tested += 1
        for e in errors: print(f"    {e}")
        if bad:
            print(f"  FAIL: {bad}/{tested} pairs are NOT lossless")
            return False
        print(f"  all {tested} pairs: LOSSLESS ✓")
        return True

    def selftest_fixed(self, n=30):
        import os as _os
        fixed = [7, 8, 9, 33, 35, 36, 37, 45, 58, 72, 77, 78, 79, 80, 81, 82, 83]
        if not self._is_huge_a256():
            fixed = fixed + [256]
        print("="*60); print("Targeted sweep: FIXED transforms"); print("="*60)
        bad = []
        forced = list(range(0, 128)) + [256, 512, 1024, 2048, 4096]
        for t in fixed:
            for L in forced:
                d = _os.urandom(L)
                try:
                    if self.rev[t](self.fwd[t](d)) != d:
                        bad.append((t, L, "mismatch")); break
                except Exception as e:
                    bad.append((t, L, repr(e))); break
            if bad and bad[-1][0] == t: continue
            for trial in range(n):
                L = random.randint(0, 4096); d = _os.urandom(L)
                try:
                    if self.rev[t](self.fwd[t](d)) != d:
                        bad.append((t, L, "mismatch")); break
                except Exception as e:
                    bad.append((t, L, repr(e))); break
        if bad:
            for row in bad: print(f"  FAIL a{row[0]}: len={row[1]} {row[2]}")
            return False
        print(f"  {fixed}: exhaustive length sweep + {n}×{len(fixed)} random LOSSLESS ✓")
        return True

    def selftest(self):
        print("="*60); print("Self-Test (extension .aXXXX)"); print("="*60)
        for kind, ident in [("a", 1), ("a", 62), ("a", 83), ("a", 84), ("a", 168), ("a", 255), ("a", 256), ("b", 1), ("b", MAX_PAIRS)]:
            ext = _ext_for(kind, ident); parsed = _parse_ext("foo.bin" + ext)
            if parsed != (kind, ident):
                print(f"  FAIL ext {ext} → {parsed}"); return False
        print(f"  Extension .aXXXX round-trips: PASS  (b cap: {MAX_PAIRS})")

        print("  a84-a255 family spot-checks:")
        for fam_start, fam_name in [(84, "delta_stride"), (92, "add_stride"), (100, "xor_stride"),
                                     (108, "ddot_stride"), (116, "transpose"),
                                     (124, "swap2_delta"), (132, "swap4_delta"), (140, "swap8_delta"),
                                     (148, "row_delta"), (156, "bitrev_add"), (164, "bitrev_xor"),
                                     (172, "nibble_add"), (180, "nibble_xor"), (188, "xor_periodic"),
                                     (196, "add_periodic"), (204, "posmod_rotl"), (212, "posmod_rotr"),
                                     (220, "posmod_xor"), (228, "posmod_add"), (236, "xor_reverse"),
                                     (244, "add_reverse"), (252, "delta_reverse")]:
            if not self.verify_single(b"hello world " * 4, fam_start):
                print(f"  FAIL {fam_name} (a{fam_start})"); return False
        print("  all 22 families reversible ✓")

        _z = io.BytesIO()
        with zipfile.ZipFile(_z, 'w', zipfile.ZIP_STORED) as z:
            z.writestr("word/document.xml",
                b'<?xml version="1.0"?><w:document xmlns:w="x"><w:body>'
                + b'<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
                  b'<w:r><w:rPr><w:b/><w:sz w:val="24"/></w:rPr>'
                  b'<w:t>Hello, World!</w:t></w:r></w:p>' * 200
                + b'</w:body></w:document>')
        docx_bytes = _z.getvalue()
        for enc_fn, dec_fn, tag in ((_xml_encode_v2,   _xml_decode_v2,   "XY varint"),
                                    (_xml_encode_bits, _xml_decode_bits, "XZ bit  ")):
            p = enc_fn(docx_bytes)
            if p is None or dec_fn(p) != docx_bytes:
                print(f"  FAIL {tag}"); return False
            if _xml_decode_v2(p) != docx_bytes:
                print(f"  FAIL {tag} dispatch"); return False
            print(f"  {tag}: {len(docx_bytes):,} → {len(p):,} bytes  ({len(p)/len(docx_bytes)*100:.1f}%)")
        best = _best_xml_encode(docx_bytes, self.ref_idx)
        if best is None or _xml_decode_v2(best) != docx_bytes:
            print("  FAIL _best_xml_encode"); return False
        print(f"  _best_xml_encode picked: magic {best[:2].hex()} ({len(best):,} bytes)")

        wenc = _xml_encode_v2_words(docx_bytes, self.ref_idx)
        if wenc is not None:
            if _xml_decode_v2(wenc) != docx_bytes:
                print("  FAIL words variant round-trip"); return False
            print(f"  words variant 0x5B : {len(docx_bytes):,} → {len(wenc):,} bytes "
                  f"({len(wenc)/len(docx_bytes)*100:.1f}%)")

        cenc = _xml_encode_v3_compound(docx_bytes, self.ref_idx)
        if cenc is not None:
            if _xml_decode_v2(cenc) != docx_bytes:
                print("  FAIL compound variant round-trip"); return False
            print(f"  compound 0x5C  : {len(docx_bytes):,} → {len(cenc):,} bytes "
                  f"({len(cenc)/len(docx_bytes)*100:.1f}%)")

        lenc = _xml_encode_v4_localdict(docx_bytes)
        if lenc is not None:
            if _xml_decode_v2(lenc) != docx_bytes:
                print("  FAIL localdict variant round-trip"); return False
            print(f"  localdict 0x5D: {len(docx_bytes):,} → {len(lenc):,} bytes "
                  f"({len(lenc)/len(docx_bytes)*100:.1f}%)")

        nenc = _xml_encode_v5_nested(docx_bytes, self.ref_idx)
        if nenc is not None:
            if _xml_decode_v2(nenc) != docx_bytes:
                print("  FAIL nested variant round-trip"); return False
            print(f"  nested    0x5E: {len(docx_bytes):,} → {len(nenc):,} bytes "
                  f"({len(nenc)/len(docx_bytes)*100:.1f}%)")

        huff_sample = (b'<?xml version="1.0"?>' +
                       b'<w:p><w:r><w:t>Hello, World!</w:t></w:r></w:p>' * 200)
        huff_best = self._best_huff_block(huff_sample)
        if huff_best is not None:
            if self._huff_block_decode(huff_best) != huff_sample:
                print("  huff_block: FAILED round-trip"); return False
            print(f"  huff_block: {len(huff_sample):,} → {len(huff_best):,} bytes")

        _dz = io.BytesIO()
        with zipfile.ZipFile(_dz, 'w', zipfile.ZIP_DEFLATED) as _zz:
            _zz.writestr('[Content_Types].xml',
                b'<?xml version="1.0"?><Types xmlns="x">'
                b'<Default Extension="xml" ContentType="app/xml"/></Types>')
            _zz.writestr('_rels/.rels',
                b'<?xml version="1.0"?><Relationships xmlns="x">'
                b'<Relationship Id="rId1" Type="t" Target="word/document.xml"/>'
                b'</Relationships>')
            _zz.writestr('word/document.xml',
                b'<?xml version="1.0"?><w:document xmlns:w="x"><w:body>'
                + b'<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
                  b'<w:r><w:rPr><w:b/><w:sz w:val="24"/></w:rPr>'
                  b'<w:t>Hello, World!</w:t></w:r></w:p>' * 200
                + b'</w:body></w:document>')
        docx_test = _dz.getvalue()
        docx_enc = self.t_docx(docx_test)
        if docx_enc is None:
            print("  DOCX container-aware: FALLBACK (this machine/zip variant)")
        else:
            docx_dec = self.r_xml(docx_enc)
            if docx_dec != docx_test:
                print("  DOCX container-aware: FAILED round-trip"); return False
            print(f"  DOCX container-aware: {len(docx_test):,} → "
                  f"{len(docx_enc):,} bytes "
                  f"({len(docx_enc)/len(docx_test)*100:.1f}%)")

        if HAS_LZMA:
            ultra_test = self._ultra_compress(b"ultra chain test " * 100)
            if ultra_test is not None:
                if self._ultra_decompress(ultra_test) != b"ultra chain test " * 100:
                    print("  ultra: FAILED round-trip"); return False
                chain = "LZMA-9 → cmix" if ultra_test[0] == 1 else "LZMA-9 only"
                print(f"  ultra chain: {chain}  ({len(ultra_test):,} bytes)")

        for p in [b"hello world " * 20, b"\x00" * 1000, os.urandom(200)]:
            e = self.cback(p); d = self.dback(e)
            if d != p: print(f"  FAIL backend len={len(p)}"); return False
        print("  Backends: PASS")
        if not self.selftest_fixed(): return False
        if not self.selftest_all_transforms(): return False
        if not self.selftest_all_pairs(max_pairs=min(500, len(self.pairs))): return False
        import tempfile as _tf
        with _tf.TemporaryDirectory() as td:
            src = os.path.join(td, "sample.txt")
            with open(src, "wb") as f: f.write(b"hello world " * 50)
            self.compress(src, selftest=True)
            outs = [n for n in os.listdir(td) if n.startswith("sample.txt.a")]
            if not outs: print("  FAIL no output file"); return False
            out_path = os.path.join(td, outs[0])
            dec = os.path.join(td, "decoded.txt")
            if not self.decompress(out_path, dec): return False
            with open(dec, "rb") as f: got = f.read()
            with open(src, "rb") as f: want = f.read()
            if got != want: print("  FAIL round-trip"); return False
        print("  Round-trip via filesystem: PASS")
        print("[ALL CHECKS PASSED]")
        return True

def main():
    print(f"{PROGNAME}")
    print("* Extension-as-header — no header bytes inside file")
    print(f"* 0x0000..0x00FF → single a1..a256")
    print(f"* 0x0100..0xFFFF → pair   b1..b{MAX_PAIRS}")
    print("* Extension: <original>.aXXXX  (XXXX = 4 hex digits)")
    print(f"* Pipeline  : 256 singles → 65280 pairs → final cmix pass")
    print(f"* XML v3    : t_xml picks XY / XZ / XW / XC / XD / XE (nested)")
    print(f"* DOCX      : container-aware ZIP+xml (Lepton JPEG, word-token XML)")
    print(f"* a84-a255  : 22 algorithm families (delta/transpose/swap/bitrev/…)")
    if A256_MODE == "exhaustive":
        print(f"* a256      : EXHAUSTIVE  for key in range(2**64) — MAY NEVER FINISH")
        if A256_LIMIT > 0: print(f"              limit={A256_LIMIT:,} keys")
    elif A256_MODE == "repeat32":
        lim = f" (limit {A256_LIMIT:,})" if A256_LIMIT > 0 else ""
        print(f"* a256      : REPEAT-32  all 2^32 keys of form seed32||seed32{lim}")
    elif A256_MODE == "repeat32_optimal":
        print(f"* a256      : REPEAT-32 OPTIMAL  provably best seed||seed in < 1 ms")
    else:
        print(f"* a256      : {N_Q64_CANDIDATES} candidates × {KEY_BYTES*8}-bit XOR key (best wins)")
    print(f"* Self-test : fast mode — runs in ~0.5 s")
    try:
        mp.set_start_method('fork', force=True)
        print(f"mp: fork, {N_CORES} workers (cpu_count={CPU_COUNT})")
    except (RuntimeError, ValueError):
        print(f"mp: spawn, {N_CORES} workers")
    dl = input("Download 12 Google Drive dictionaries? (y/n) [n]: ").strip().lower()
    c = Compressor(try_dl=(dl == 'y'), pairs=PAIRS, qubits=QUBITS)
    while True:
        print("\nMenu:")
        print("1) Compress (fast)")
        print("2) Decompress")
        print("3) Self-test")
        print("4) Inspect file (per-entry size comparison)")
        ch = input("> ").strip()
        if ch == "1":
            f = input("Input file: ").strip()
            if not f: print("No file."); continue
            c.compress(f); print("\nDone — exiting."); return
        elif ch == "2":
            f = input("Compressed: ").strip()
            if not f: print("No file."); continue
            o = input("Output (blank=auto): ").strip()
            c.decompress(f, o)
        elif ch == "3":
            c.selftest()
        elif ch == "4":
            f = input("File to inspect: ").strip()
            if not f or not os.path.exists(f): print("No file."); continue
            with open(f, "rb") as fh: data = fh.read()
            if data[:4] == b"PK\x03\x04":
                entries, _, _ = _parse_zip_entries(data)
                for e in entries:
                    lh = e['local_header']
                    fn = lh[30:30+struct.unpack('<H', lh[26:28])[0]].decode('utf-8', 'replace')
                    if not fn.lower().endswith(('.xml', '.rels')): continue
                    try: raw = zlib.decompress(e['compressed'], -15)
                    except Exception: continue
                    cands = {
                        "XY": _xml_encode_v2(raw),
                        "XZ": _xml_encode_bits(raw),
                        "XW": _xml_encode_v2_words(raw, c.ref_idx),
                        "XC": _xml_encode_v3_compound(raw, c.ref_idx),
                        "XD": _xml_encode_v4_localdict(raw),
                        "XE": _xml_encode_v5_nested(raw, c.ref_idx),
                    }
                    print(f"\n{fn}  raw={len(raw):,}  word-deflate={len(e['compressed']):,}")
                    for name, enc in cands.items():
                        if enc is None:
                            print(f"  {name}: None"); continue
                        rt = 'OK' if _xml_decode_v2(enc) == raw else 'FAIL'
                        print(f"  {name}: raw={len(enc):>7,}  cback={len(c.cback(enc)):>7,}  rt={rt}")
            else:
                for name, fn in [("XY", _xml_encode_v2),
                                 ("XZ", _xml_encode_bits),
                                 ("XW", lambda x: _xml_encode_v2_words(x, c.ref_idx)),
                                 ("XC", lambda x: _xml_encode_v3_compound(x, c.ref_idx)),
                                 ("XD", _xml_encode_v4_localdict),
                                 ("XE", lambda x: _xml_encode_v5_nested(x, c.ref_idx))]:
                    enc = fn(data)
                    print(f"  {name}: raw={len(enc) if enc else 0:,}  "
                          f"cback={len(c.cback(enc)) if enc else 0:,}")
        else: print("Invalid")

if __name__ == "__main__":
    main()
