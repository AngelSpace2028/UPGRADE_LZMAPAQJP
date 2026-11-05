#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified PAQJP+PJP — 256/256 lossless transforms.
Menu: 1=Compress, 2=Decompress, 3=Self-test (fast).
FIXED: _wrap_single_rev no longer rejects the checksum key.
"""

import math, random, decimal, hashlib, base64, heapq, struct, os, tempfile
import re, sys, subprocess, importlib, time, urllib.request, site, lzma
from typing import Optional, List, Tuple, Dict, Callable, Any
from collections import Counter

# ============================ BACKENDS ============================
try: import paq
except ImportError: paq = None
try:
    import brotli; HAS_BROTLI = True
except ImportError:
    brotli = None; HAS_BROTLI = False

USE_QUANTUM = False
HAS_QISKIT = False
HAS_ZSTD = False
HAS_LZMA = True

def _try_import_zstd():
    try:
        importlib.invalidate_caches()
        user_site = site.getusersitepackages()
        if user_site and user_site not in sys.path:
            sys.path.insert(0, user_site)
    except Exception: pass
    try:
        import zstandard as zstd
        return zstd
    except ImportError:
        return None

def _try_install_zstd():
    for cmd in (
        [sys.executable, '-m', 'pip', 'install', '--no-input', '--disable-pip-version-check', 'zstandard'],
        [sys.executable, '-m', 'pip', 'install', '--user', '--no-input', '--disable-pip-version-check', 'zstandard'],
    ):
        try:
            subprocess.check_call(cmd)
            if _try_import_zstd() is not None: return True
        except Exception: pass
    return False

print("=" * 70); print("Checking zstandard..."); print("=" * 70)
_zstd = _try_import_zstd()
if _zstd is None:
    print("Trying to install zstandard...")
    if not _try_install_zstd():
        print("FATAL: pip install zstandard"); sys.exit(1)
    _zstd = _try_import_zstd()
    if _zstd is None:
        print("FATAL: zstandard not importable."); sys.exit(1)
zstd = _zstd
zstd_cctx = zstd.ZstdCompressor(level=22)
zstd_dctx = zstd.ZstdDecompressor()
HAS_ZSTD = True
print("zstandard loaded.")

def install_package(pkg):
    for cmd in (
        [sys.executable, '-m', 'pip', 'install', '--no-input', '--disable-pip-version-check', pkg],
        [sys.executable, '-m', 'pip', 'install', '--user', '--no-input', '--disable-pip-version-check', pkg],
    ):
        try: subprocess.check_call(cmd); return True
        except Exception: pass
    return False

try:
    ans = input("Quantum (8 qubits, Qiskit)? (y/n) [n]: ").strip().lower()
except EOFError:
    ans = 'n'
if ans == 'y':
    try:
        from qiskit import QuantumCircuit
        HAS_QISKIT = True; USE_QUANTUM = True; print("Quantum ENABLED.")
    except ImportError:
        if install_package('qiskit'):
            try:
                from qiskit import QuantumCircuit
                HAS_QISKIT = True; USE_QUANTUM = True; print("Quantum ENABLED.")
            except ImportError: print("Qiskit failed.")
        else: print("Qiskit failed.")

try:
    ans = input("Install paq + brotli? (y/n) [n]: ").strip().lower()
except EOFError:
    ans = 'n'
if ans == 'y':
    for pkg in ['paq', 'brotli']:
        try: importlib.import_module(pkg)
        except ImportError: install_package(pkg)
    try: import paq
    except ImportError: paq = None
    try: import brotli; HAS_BROTLI = True
    except ImportError: brotli = None; HAS_BROTLI = False

print(f"Backends: zstd=Y lzma=Y paq={'Y' if paq else 'N'} brotli={'Y' if HAS_BROTLI else 'N'} quantum={'Y' if USE_QUANTUM else 'N'}")

# ============================ WORD BANK ============================
_SEED_WORDS = {
'a':"able about above abroad absence absent absolute absorb abstract abuse accent accept access accident accompany accomplish accord account accurate accuse achieve acid acknowledge acquire across act action active activity actor actress actual adapt add addition address adequate adjust administration admire admit adopt adult advance advantage adventure advertise advice advise affair affect afford afraid africa after afternoon again against age agency agenda agent aggressive ago agree agriculture ahead aid aim air aircraft airline airport alarm album alcohol alive all alliance allow almost alone along already also alter alternative although always amateur amazing among amount analysis analyst ancient and anger angle angry animal anniversary announce annual another answer anxiety any anybody anymore anyone anything anyway anywhere apart apartment apologize apparent appeal appear apple application apply appoint appreciate approach appropriate approve april architecture area argue argument arise arm army around arrange arrest arrival arrive arrow art article artist as ashamed asia aside ask asleep aspect assault assert assess asset assign assist associate assume assure asteroid athlete atlantic atmosphere atom attach attack attempt attend attention attitude attorney attract auction audience august aunt author authority auto autumn available average avoid awake award aware away awful".split(),
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
'z':"zeal zebra zenith zero zest zigzag zinc zip zipper zodiac zombie zone zoo zoology zoom".split(),
}

_WORD_TARGET_PER_LETTER = 3000
_PRE = ["", "a", "be", "con", "de", "dis", "en", "ex", "in", "inter", "mis",
        "non", "over", "pre", "pro", "re", "sub", "super", "trans", "un",
        "under", "up", "with", "out", "fore", "counter", "anti", "auto", "bi",
        "co", "extra", "hyper", "micro", "mid", "multi", "neo", "omni", "para",
        "poly", "post", "pseudo", "quasi", "semi", "tele", "ultra", "circum",
        "contra", "epi", "hypo", "infra", "intra", "macro", "mega", "mono",
        "proto", "retro", "syn", "tri", "uni", "vice"]
_MID = ["a","e","i","o","u","ab","ac","ad","ag","al","am","an","ap","ar","as","at",
        "av","az","eb","ec","ed","eg","el","em","en","ep","er","es","et","ev",
        "ib","ic","id","ig","il","im","in","ip","ir","is","it","iv","iz","ob",
        "oc","od","og","ol","om","on","op","or","os","ot","ov","oz","ub","uc",
        "ud","ug","ul","um","un","up","ur","us","ut","uv","uz","br","cr","dr",
        "fr","gr","pr","tr","str","thr"]
_SUF = ["","s","es","ed","ing","er","est","ly","ness","ment","tion","sion","able",
        "ible","ous","ive","al","ic","ity","ize","ance","ence","ate","ify","ship",
        "hood","ward","wise","ist","ism","ology","ography","scope","graph","gram",
        "logy","nomy","pathy","ful","less","some","like","fold","most","proof"]

def _gen_batch(letter, target=_WORD_TARGET_PER_LETTER):
    L = letter.lower()
    seed = _SEED_WORDS.get(L, [L])
    rng = random.Random(hash(("AtoZ", L, target)) & 0xFFFFFFFF)
    words = set()
    for w in seed:
        w = w.lower().strip()
        if w and w[0] == L and w.isalpha(): words.add(w)
    for w in list(words):
        for suf in ("s","es","ed","ing","er","est","ly","ness","ment","able","ible",
                    "ous","ive","al","ic","ity","ize","ation","ition","ful","less"):
            c = w + suf
            if len(c) <= 24 and c[0] == L: words.add(c)
    guard = 0; mx = target * 40
    while len(words) < target and guard < mx:
        guard += 1
        c = L + rng.choice(_PRE) + rng.choice(_MID) + rng.choice(_SUF)
        if 3 <= len(c) <= 24 and c.isalpha(): words.add(c)
    return " ".join(sorted(words)[:target])

ALL_REAL_WORD_BATCHES = tuple(_gen_batch(chr(ord('A') + i)) for i in range(26))
print(f"A–Z batches: {sum(len(b.split()) for b in ALL_REAL_WORD_BATCHES):,} words")

def build_real_dictionary(try_download=True):
    words = set()
    for path in ["/usr/share/dict/words", "/usr/share/dict/american-english",
                 "/usr/share/dict/british-english", "/usr/share/hunspell/en_US.dic",
                 os.path.expanduser("~/.local/share/dict/words")]:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        w = line.split('/')[0].strip().lower()
                        if w and w.isalpha() and 1 <= len(w) <= 64: words.add(w)
            except Exception: pass
    for blob in ALL_REAL_WORD_BATCHES:
        words |= {w.lower() for w in blob.split() if w.isalpha() and 1 <= len(w) <= 64}
    words = sorted(w for w in words if w and w.isascii() and 1 <= len(w) <= 64)
    print(f"FINAL dictionary: {len(words):,} words")
    return words

PRIMES = [p for p in range(2, 256) if all(p % d != 0 for d in range(2, int(p ** 0.5) + 1))]
PI_DIGITS = [79, 17, 111]

def find_nearest_prime_around(n):
    n = n & 0xFF
    if n < 2: return 2
    o = 0
    while o < 256:
        c1, c2 = n - o, n + o
        if c1 >= 2 and all(c1 % d != 0 for d in range(2, int(c1 ** 0.5) + 1)): return c1
        if c2 <= 255 and all(c2 % d != 0 for d in range(2, int(c2 ** 0.5) + 1)): return c2
        o += 1
    return 251

_CONST_DIAPASON_ITER_CODE = [
    (2, 0b10), (2, 0b11), (3, 0b010), (3, 0b011), (4, 0b0010), (4, 0b0011),
    (5, 0b00010), (5, 0b00011), (6, 0b000010), (6, 0b000011), (7, 0b0000010),
    (7, 0b0000011), (8, 0b00000010), (8, 0b00000011), (9, 0b000000010), (9, 0b000000011),
]
_CONST_DIAPASON_ITER_DECODE = {v: k for k, v in enumerate(_CONST_DIAPASON_ITER_CODE)}

ALPHABET_6BIT = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 \n"
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
class IntegrityError(Exception): pass

def mod_inv(a, m):
    if a == 0: return None
    m0 = m; y = 0; x = 1
    if m == 1: return 0
    while a > 1:
        q = a // m; t = m; m = a % m; a = t
        t = y; y = x - q * y; x = t
    if x < 0: x += m0
    return x

def _tree_leaves(node):
    if isinstance(node, int):
        yield node
    else:
        yield from _tree_leaves(node[0])
        yield from _tree_leaves(node[1])

def _lossy_checksum(payload):
    s = 0
    for b in payload:
        s = (s + b) & 0xFF
        s = ((s << 1) | (s >> 7)) & 0xFF
    return s if s != 0 else 0x01

MAGIC = b'PJP4'; MAGIC_LEN = 4; HASH_LEN = 8; HEADER_LEN = MAGIC_LEN + HASH_LEN


class UnifiedCompressor:
    ULTRA_TIME_LIMIT = 300
    QUANTUM_QUBITS = 8
    WINDOW_SIZE = 2048
    MIN_MATCH = 3
    MAX_MATCH = 2048
    MAX_DIST = 2048

    def __init__(self, try_download=True):
        print("\n" + "=" * 60); print("BUILDING DICTIONARY"); print("=" * 60)
        words = build_real_dictionary(try_download=try_download)
        self.static_dict = words
        self.word_to_index = {w: i for i, w in enumerate(words)}
        self.PI_DIGITS = PI_DIGITS.copy()
        self.seed_tables = self._gen_seed_tables()
        self.fibonacci = self._gen_fib(100)
        self.repeat_count = 100
        self.mod_state_table = [[(v - 400) & 0xFF for v in row] for row in PAQ_STATE_TABLE]
        self._build_mask_46()
        self._build_transform_maps()
        if USE_QUANTUM and HAS_QISKIT:
            self._precompute_quantum_transforms()

    @staticmethod
    def _put_varint(buf, n):
        if n < 0: raise ValueError("varint negative")
        while True:
            b = n & 0x7F; n >>= 7
            if n: buf.append(b | 0x80)
            else: buf.append(b); return

    @staticmethod
    def _get_varint(data, pos):
        shift = 0; result = 0
        while True:
            if pos >= len(data): raise TransformError("varint trunc")
            b = data[pos]; pos += 1
            result |= (b & 0x7F) << shift
            if not (b & 0x80): return result, pos
            shift += 7
            if shift > 63: raise TransformError("varint too long")

    def _build_mask_46(self):
        base = [1, 2, 4, 8, 16, 32, 64, 128, 3, 6]
        self.mask_46 = [(b - 10) & 0xFF for b in base] * 10
    def _gen_seed_tables(self, num=126, size=40, seed=42):
        random.seed(seed)
        return [[random.randint(5, 255) for _ in range(size)] for _ in range(num)]
    def _gen_fib(self, n):
        a, b = 0, 1; res = [a, b]
        for _ in range(2, n): a, b = b, a + b; res.append(b)
        return res
    def get_seed(self, idx, val):
        return self.seed_tables[idx][val % 40] if 0 <= idx < len(self.seed_tables) else 0
    def _append_bits(self, bl, v, c):
        for i in range(c - 1, -1, -1): bl.append((v >> i) & 1)
    def _read_bits(self, bits, pos, cnt):
        v = 0
        for i in range(cnt):
            if pos + i >= len(bits): return 0
            v = (v << 1) | bits[pos + i]
        return v
    def _get_pattern(self, size, index):
        random.seed(12345 + size * 100 + index)
        return [random.randint(0, 255) for _ in range(size)]
    def _calculate_repeats(self, data):
        if not data: return 1
        L = len(data); s = sum(data) % 256
        return max(1, min(256, ((L * 13 + s * 17) % 256) + 1))

    # ---- 1..22 ----
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
        t = bytearray(d); pi = (len(d) + sum(d)) % 256
        pv = self._get_pattern(4, pi)
        for i in range(1, len(t), 4):
            if i < len(t): t[i] ^= pv[i % len(pv)]
        return bytes([pi]) + bytes(t)
    def reverse_transform_02(self, d):
        if d == b'\x00': return b''
        if len(d) < 2: raise TransformError("T02")
        pi = d[0]; t = bytearray(d[1:]); pv = self._get_pattern(4, pi)
        for i in range(1, len(t), 4):
            if i < len(t): t[i] ^= pv[i % len(pv)]
        return bytes(t)

    def transform_03(self, d):
        if not d: return b'\x00'
        t = bytearray(d); rot = (len(d) * 13 + sum(d)) % 8
        if rot == 0: rot = 1
        for i in range(2, len(t), 5):
            if i < len(t): t[i] = ((t[i] << rot) | (t[i] >> (8 - rot))) & 0xFF
        return bytes([rot]) + bytes(t)
    def reverse_transform_03(self, d):
        if d == b'\x00': return b''
        if len(d) < 2: raise TransformError("T03")
        rot = d[0]; t = bytearray(d[1:])
        for i in range(2, len(t), 5):
            if i < len(t): t[i] = ((t[i] >> rot) | (t[i] << (8 - rot))) & 0xFF
        return bytes(t)

    def transform_04(self, d):
        t = bytearray(d)
        for _ in range(self.repeat_count):
            for i in range(len(t)): t[i] = (t[i] - (i % 256)) % 256
        return bytes(t)
    def reverse_transform_04(self, d):
        t = bytearray(d)
        for _ in range(self.repeat_count):
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
        inv = [0] * 256
        for i in range(256): inv[sub[i]] = i
        return bytes(inv[b] for b in d)

    def transform_07(self, d):
        t = bytearray(d); r = self.repeat_count
        sh = len(d) % len(self.PI_DIGITS)
        pr = self.PI_DIGITS[sh:] + self.PI_DIGITS[:sh]
        sz = len(d) % 256
        for i in range(len(t)): t[i] ^= sz
        for _ in range(r):
            for i in range(len(t)): t[i] ^= pr[i % len(pr)]
        return bytes(t)
    reverse_transform_07 = transform_07

    def transform_08(self, d):
        t = bytearray(d); r = self.repeat_count
        sh = len(d) % len(self.PI_DIGITS)
        pr = self.PI_DIGITS[sh:] + self.PI_DIGITS[:sh]
        p = find_nearest_prime_around(len(d) % 256)
        for i in range(len(t)): t[i] ^= p
        for _ in range(r):
            for i in range(len(t)): t[i] ^= pr[i % len(pr)]
        return bytes(t)
    reverse_transform_08 = transform_08

    def transform_09(self, d):
        t = bytearray(d); r = self.repeat_count
        sh = len(d) % len(self.PI_DIGITS)
        pr = self.PI_DIGITS[sh:] + self.PI_DIGITS[:sh]
        p = find_nearest_prime_around(len(d) % 256)
        sd = self.get_seed(len(d) % len(self.seed_tables), len(d))
        for i in range(len(t)): t[i] ^= (p ^ sd) & 0xFF
        for _ in range(r):
            for i in range(len(t)): t[i] ^= pr[i % len(pr)] ^ (i % 256)
        return bytes(t)
    reverse_transform_09 = transform_09

    def transform_10(self, data):
        if not data: return b'\x00'
        cnt = sum(1 for i in range(len(data) - 1) if data[i:i + 2] == b'X1')
        n = (((cnt * 2) + 1) // 3) * 3 % 256
        t = bytearray(data)
        for i in range(len(t)): t[i] ^= n
        return bytes([n]) + bytes(t)
    def reverse_transform_10(self, data):
        if len(data) < 1: raise TransformError("T10")
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
        r = self._calculate_repeats(d); cv = len(d) % 256; pv = []
        for _ in range(r):
            cv = find_nearest_prime_around(cv); pv.append(cv)
        t = bytearray(d); xv = pv[-1] if pv else 0
        for i in range(len(t)): t[i] ^= xv
        return bytes([(r - 1) % 256]) + bytes(t)
    def reverse_transform_13(self, d):
        if d == b'\x00': return b''
        if len(d) < 2: raise TransformError("T13")
        r = (d[0] + 1) % 256
        if r == 0: r = 256
        t = bytearray(d[1:]); cv = len(t) % 256; pv = []
        for _ in range(r):
            cv = find_nearest_prime_around(cv); pv.append(cv)
        xv = pv[-1] if pv else 0
        for i in range(len(t)): t[i] ^= xv
        return bytes(t)

    def transform_14(self, d):
        if not d: return b'\x00'
        return d + bytes([sum(d) % 256])
    def reverse_transform_14(self, d):
        if not d: raise TransformError("T14")
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
        if len(d) < 2: raise TransformError("T15")
        pi = d[0]; t = bytearray(d[1:]); pv = self._get_pattern(3, pi)
        for i in range(0, len(t), 3):
            if i < len(t): t[i] = (t[i] - pv[i % len(pv)]) % 256
        return bytes(t)

    def transform_16(self, data):
        if not data: return b''
        xv = (len(data) * 7 + 13) % 256
        return bytes(b ^ xv for b in data)
    reverse_transform_16 = transform_16

    def transform_17(self, data):
        if not data: return b''
        mask = bytes([0x24, 0x3F, 0x6A, 0x88])
        t = bytearray(data)
        for i in range(len(t)): t[i] ^= mask[i % len(mask)]
        return bytes(t)
    reverse_transform_17 = transform_17

    def transform_18(self, data):
        if not data: return b''
        decimal.getcontext().prec = 60
        pi = decimal.Decimal("3.14159265358979323846264338327950288419716939937510")
        basel = (pi * pi) / decimal.Decimal(6)
        s = str(basel).replace('.', '')[:max(10, len(data) // 2 + 5)]
        mask = bytes(int(s[i:i + 2]) % 256 for i in range(0, len(s), 2))
        t = bytearray(data)
        for i in range(len(t)): t[i] ^= mask[i % len(mask)]
        return bytes(t)
    reverse_transform_18 = transform_18

    def transform_19(self, data):
        if not data: return b''
        decimal.getcontext().prec = 60
        e = decimal.Decimal(1).exp(); five_e = decimal.Decimal(5) * e
        s = str(five_e).replace('.', '')[:max(10, len(data) // 2 + 5)]
        mask = bytes(int(s[i:i + 2]) % 256 for i in range(0, len(s), 2))
        t = bytearray(data)
        for i in range(len(t)): t[i] ^= mask[i % len(mask)]
        return bytes(t)
    reverse_transform_19 = transform_19

    def transform_20(self, data): return self.transform_19(data)
    reverse_transform_20 = transform_20

    def transform_21(self, data):
        if not data: return b''
        return bytes((b + 255) % 256 for b in data)
    def reverse_transform_21(self, data):
        if not data: return b''
        return bytes((b - 255) % 256 for b in data)

    def transform_22(self, data): return base64.b64encode(data)
    def reverse_transform_22(self, data):
        try: return base64.b64decode(data, validate=False)
        except Exception as e: raise TransformError(f"b64: {e}")

    # ---- 23 ----
    def transform_23(self, data):
        if not data: return b'\x00', 0x00
        try: text = data.decode('utf-8')
        except UnicodeDecodeError: return b'\x00' + data, 0x00
        tokens = re.split(r'([A-Za-z0-9_]+)', text)
        wl = []; wi = {}; st = bytearray()
        for i, tok in enumerate(tokens):
            tb = tok.encode('utf-8')
            if i % 2 == 1:
                idx = wi.get(tb)
                if idx is None:
                    idx = len(wl); wi[tb] = idx; wl.append(tb)
                self._put_varint(st, (idx << 1) | 1)
            else:
                self._put_varint(st, (len(tb) << 1) | 0); st.extend(tb)
        out = bytearray(); out.append(0x01)
        self._put_varint(out, len(wl))
        for wb in wl:
            self._put_varint(out, len(wb)); out.extend(wb)
        out.extend(st)
        return bytes(out), 0x00

    def reverse_transform_23(self, data, lossy_key=0x00):
        if not data: raise TransformError("T23 empty")
        tag = data[0]
        if tag == 0x00: return data[1:]
        if tag != 0x01: raise TransformError(f"T23 tag {tag}")
        pos = 1
        n, pos = self._get_varint(data, pos)
        wl = []
        for _ in range(n):
            wlen, pos = self._get_varint(data, pos)
            if pos + wlen > len(data): raise TransformError("T23 word trunc")
            wl.append(data[pos:pos + wlen]); pos += wlen
        out = bytearray()
        while pos < len(data):
            code, pos = self._get_varint(data, pos)
            if code & 1:
                idx = code >> 1
                if idx >= len(wl): raise TransformError(f"T23 idx {idx}")
                out.extend(wl[idx])
            else:
                ln = code >> 1
                if pos + ln > len(data): raise TransformError("T23 lit trunc")
                out.extend(data[pos:pos + ln]); pos += ln
        return bytes(out)

    # ---- 24 ----
    def transform_24(self, data):
        inner, _ = self.transform_23(data)
        xk = (len(inner) * 0x9E3779B1) & 0xFF
        return bytes([xk]) + bytes(b ^ xk for b in inner), 0x00
    def reverse_transform_24(self, data, lossy_key=0x00):
        if not data: raise TransformError("T24 empty")
        xk = data[0]
        inner = bytes(b ^ xk for b in data[1:])
        return self.reverse_transform_23(inner, lossy_key)

    # ---- 25..30 ----
    def _split_chunks(self, text):
        chunks = []
        for i, para in enumerate(re.split(r'(\n\n)', text)):
            if i % 2 == 1: chunks.append(para); continue
            for j, line in enumerate(re.split(r'(\n)', para)):
                if j % 2 == 1: chunks.append(line); continue
                for k, sent in enumerate(re.split(r'([.!?]+)', line)):
                    if k % 2 == 1: chunks.append(sent); continue
                    chunks.extend(re.split(r'(\s+|\b)', sent))
        return chunks
    def _dyn_tok(self, data, ib=3):
        try: text = data.decode('utf-8')
        except Exception: return b'\x00' + data
        chunks = self._split_chunks(text)
        freq = Counter(chunks)
        sc = sorted(freq.keys(), key=lambda x: (-freq[x], -len(x), x))
        ci = {ch: i for i, ch in enumerate(sc)}
        ne = len(sc)
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
    def _dyn_detok(self, data):
        if not data: return b''
        if data[0] == 0: return data[1:]
        ib = data[0]
        if ib not in (2, 3, 8): raise TransformError(f"dict ib {ib}")
        pos = 1
        if pos + 4 > len(data): raise TransformError("dict s")
        ne = struct.unpack('>I', data[pos:pos + 4])[0]; pos += 4
        dd = []
        for _ in range(ne):
            if pos + 4 > len(data): raise TransformError("dict t1")
            cl = struct.unpack('>I', data[pos:pos + 4])[0]; pos += 4
            if pos + cl > len(data): raise TransformError("dict t2")
            dd.append(data[pos:pos + cl].decode('utf-8')); pos += cl
        toks = []
        while pos < len(data):
            if ib == 2:
                if pos + 2 > len(data): break
                idx = struct.unpack('>H', data[pos:pos + 2])[0]; pos += 2
            elif ib == 3:
                if pos + 3 > len(data): break
                idx = struct.unpack('>I', b'\x00' + data[pos:pos + 3])[0]; pos += 3
            else:
                if pos + 8 > len(data): break
                idx = struct.unpack('>Q', data[pos:pos + 8])[0]; pos += 8
            if idx >= len(dd): raise TransformError(f"dict idx {idx}")
            toks.append(dd[idx])
        return ''.join(toks).encode('utf-8')
    def transform_25(self, data): return self._dyn_tok(data, 3)
    def reverse_transform_25(self, data): return self._dyn_detok(data)

    def transform_26(self, data):
        if not data: return b''
        secret = b"PJP_T26"; r = bytearray()
        for idx in range(0, len(data), 1024):
            ch = data[idx:idx + 1024]; bn = idx // 1024
            h = hashlib.sha256(secret + struct.pack(">Q", bn)).digest()
            m = (h * ((len(ch) // len(h)) + 1))[:len(ch)]
            r.extend(a ^ b for a, b in zip(ch, m))
        return bytes(r)
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
            b = 0
            for j in range(8): b = (b << 1) | bits[i + j]
            out.append(b)
        return b'\x01' + struct.pack('<I', len(text)) + bytes(out)
    def reverse_transform_27(self, data):
        if len(data) < 1: raise TransformError("T27")
        flag = data[0]
        if flag == 0: return data[1:]
        if flag != 1: raise TransformError(f"T27 {flag}")
        p = data[1:]
        if len(p) < 4: raise TransformError("T27 p")
        nc = struct.unpack('<I', p[:4])[0]; packed = p[4:]
        nb = (nc * 6 + 7) // 8
        if len(packed) != nb: raise TransformError("T27 mm")
        pb = (8 - (nc * 6) % 8) % 8
        if pb > 0 and packed:
            m = (1 << pb) - 1
            if packed[-1] & m: raise TransformError("T27 pad")
        bits = []
        for b in packed:
            for i in range(7, -1, -1): bits.append((b >> i) & 1)
        chars = []
        for i in range(nc):
            v = 0
            for j in range(6): v = (v << 1) | bits[i * 6 + j]
            if v >= 64: raise TransformError(f"T27 v {v}")
            chars.append(SIXBIT_TO_CHAR[v])
        return ''.join(chars).encode('utf-8')

    def transform_28(self, data):
        if not data: return b'\x00'
        pad = (3 - len(data) % 3) % 3
        padded = data + b'\x00' * pad
        out = bytearray([pad])
        for i in range(0, len(padded), 3):
            v = int.from_bytes(padded[i:i + 3], 'little')
            bi = i // 3; k = (bi * 65537 + 12345) & 0xFFFF
            out.extend(((v - k) % (1 << 24)).to_bytes(3, 'little'))
        return bytes(out)
    def reverse_transform_28(self, data):
        if data == b'\x00': return b''
        if not data: raise TransformError("T28")
        pad = data[0]; p = data[1:]
        if len(p) % 3 != 0: raise TransformError("T28 l")
        out = bytearray()
        for i in range(0, len(p), 3):
            v = int.from_bytes(p[i:i + 3], 'little')
            bi = i // 3; k = (bi * 65537 + 12345) & 0xFFFF
            out.extend(((v + k) % (1 << 24)).to_bytes(3, 'little'))
        if pad: out = out[:-pad]
        return bytes(out)

    def transform_29(self, data):
        if not data: return b'\x00'
        pad = (3 - len(data) % 3) % 3
        padded = data + b'\x00' * pad
        vals = [int.from_bytes(padded[i:i + 3], 'little') for i in range(0, len(padded), 3)]
        bk, bc = 0, float('inf')
        for k in range(65536):
            tr = [(v - k) & 0xFFFFFF for v in vals]
            m = sum(tr) // len(tr)
            c = sum(abs(t - m) for t in tr)
            if c < bc: bc = c; bk = k
            if c == 0: break
        out = bytearray([pad]) + bk.to_bytes(2, 'little')
        for i in range(0, len(padded), 3):
            v = int.from_bytes(padded[i:i + 3], 'little')
            out.extend(((v - bk) % (1 << 24)).to_bytes(3, 'little'))
        return bytes(out)
    def reverse_transform_29(self, data):
        if data == b'\x00': return b''
        if len(data) < 3: raise TransformError("T29")
        pad = data[0]; k = int.from_bytes(data[1:3], 'little')
        p = data[3:]
        if len(p) % 3 != 0: raise TransformError("T29 l")
        out = bytearray()
        for i in range(0, len(p), 3):
            v = int.from_bytes(p[i:i + 3], 'little')
            out.extend(((v + k) % (1 << 24)).to_bytes(3, 'little'))
        if pad: out = out[:-pad]
        return bytes(out)

    def transform_30(self, data):
        if not data: return b'\x00'
        pad = (3 - len(data) % 3) % 3
        padded = data + b'\x00' * pad
        vals = [int.from_bytes(padded[i:i + 3], 'little') for i in range(0, len(padded), 3)]
        mean = sum(vals) // len(vals)
        sv = sorted(vals); med = sv[len(sv) // 2]
        cands = set()
        for b in [mean, med]:
            for o in [0, 1, -1, 10, -10, 100, -100, 1000, -1000]:
                cands.add((b + o) % (1 << 24))
        rng = random.Random(42)
        for _ in range(10): cands.add(rng.randint(0, (1 << 24) - 1))
        bk, bc = 0, float('inf')
        for k in cands:
            tr = [(v - k) & 0xFFFFFF for v in vals]
            m = sum(tr) // len(tr)
            c = sum(abs(t - m) for t in tr)
            if c < bc: bc = c; bk = k
        out = bytearray([pad]) + bk.to_bytes(3, 'little')
        for i in range(0, len(padded), 3):
            v = int.from_bytes(padded[i:i + 3], 'little')
            out.extend(((v - bk) % (1 << 24)).to_bytes(3, 'little'))
        return bytes(out)
    def reverse_transform_30(self, data):
        if data == b'\x00': return b''
        if len(data) < 4: raise TransformError("T30")
        pad = data[0]; k = int.from_bytes(data[1:4], 'little')
        p = data[4:]
        if len(p) % 3 != 0: raise TransformError("T30 l")
        out = bytearray()
        for i in range(0, len(p), 3):
            v = int.from_bytes(p[i:i + 3], 'little')
            out.extend(((v + k) % (1 << 24)).to_bytes(3, 'little'))
        if pad: out = out[:-pad]
        return bytes(out)

    def transform_31(self, d): return d
    reverse_transform_31 = transform_31
    def transform_32(self, d): return d
    reverse_transform_32 = transform_32

    # ---- 33..40 ----
    def _paqjp_t23(self, data):
        if not data: return b'\x00' * 5
        bits = []
        for b in data:
            for i in range(7, -1, -1): bits.append((b >> i) & 1)
        return self._compress_bits(bits)
    def _paqjp_r23(self, data):
        if not data or data == b'\x00' * 5: return b''
        bits = self._decompress_bits(data)
        if not bits: return b''
        out = bytearray()
        for i in range(0, len(bits), 8):
            v = 0
            for j in range(i, min(i + 8, len(bits))): v = (v << 1) | bits[j]
            if i + 8 > len(bits): v <<= (8 - (len(bits) - i))
            out.append(v)
        return bytes(out)
    def _compress_bits(self, bits):
        obl = len(bits)
        if obl == 0: return b'\x00' * 5
        cur = bits[:]; pl = obl; pc = 0
        while pc < 255:
            pad = (4 - len(cur) % 4) % 4
            padded = cur + [0] * pad
            nc = len(padded) // 4; enc = []
            for i in range(nc):
                nib = (padded[i*4] << 3) | (padded[i*4+1] << 2) | (padded[i*4+2] << 1) | padded[i*4+3]
                L, cw = _CONST_DIAPASON_ITER_CODE[nib]
                for b in range(L - 1, -1, -1): enc.append((cw >> b) & 1)
            if len(enc) < pl: cur = enc; pl = len(enc); pc += 1
            else: break
        cbl = len(cur)
        hdr = struct.pack('>H', obl) + bytes([pc]) + struct.pack('>H', cbl)
        pad = (8 - len(cur) % 8) % 8; cur += [0] * pad
        out = bytearray()
        for i in range(0, len(cur), 8):
            v = 0
            for j in range(8): v = (v << 1) | cur[i + j]
            out.append(v)
        return hdr + bytes(out)
    def _decompress_bits(self, data):
        if len(data) < 5: raise TransformError("Diap")
        obl = struct.unpack('>H', data[:2])[0]
        pc = data[2]
        cbl = struct.unpack('>H', data[3:5])[0]
        pay = data[5:]
        bits = []
        for b in pay:
            for i in range(7, -1, -1): bits.append((b >> i) & 1)
        if len(bits) < cbl: raise TransformError("Diap p")
        cur = bits[:cbl]
        if pc == 0: return cur[:obl]
        for _ in range(pc):
            pos = 0; nb = len(cur); dn = []
            while pos < nb:
                m = False
                for L in range(2, 10):
                    if pos + L > nb: continue
                    cw = 0
                    for k in range(L): cw = (cw << 1) | cur[pos + k]
                    if (L, cw) in _CONST_DIAPASON_ITER_DECODE:
                        dn.append(_CONST_DIAPASON_ITER_DECODE[(L, cw)])
                        pos += L; m = True; break
                if not m: raise TransformError("Diap cw")
            nb2 = []
            for nib in dn:
                for j in range(3, -1, -1): nb2.append((nib >> j) & 1)
            cur = nb2
        if len(cur) < obl: raise TransformError("Diap s")
        return cur[:obl]
    def _paqjp_t24(self, data):
        if not data: return struct.pack('>I', 0)
        MAX = 43; bits = []; i = 0; n = len(data)
        while i < n:
            cl = min(MAX, n - i); ch = data[i:i + cl]
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
            for k in range(8): b = (b << 1) | bits[j + k]
            out.append(b)
        return struct.pack('>I', len(data)) + bytes(out)
    def _paqjp_r24(self, data):
        if not data: return b''
        if len(data) < 4: raise TransformError("BlkRun")
        ol = struct.unpack('>I', data[:4])[0]
        p = data[4:]
        bits = []
        for b in p:
            for i in range(7, -1, -1): bits.append((b >> i) & 1)
        pos = 0; nb = len(bits); out = bytearray()
        while pos < nb and len(out) < ol:
            if pos + 1 > nb: break
            flag = self._read_bits(bits, pos, 1); pos += 1
            if flag == 1:
                if pos + 14 > nb: raise TransformError("BlkRun t")
                bv = self._read_bits(bits, pos, 8); pos += 8
                cm = self._read_bits(bits, pos, 6); pos += 6
                rl = min(cm + 1, ol - len(out))
                out.extend([bv] * rl)
            else:
                if pos + 6 > nb: raise TransformError("BlkRun l")
                cl = self._read_bits(bits, pos, 6); pos += 6
                if cl == 0: break
                if pos + cl * 8 > nb: raise TransformError("BlkRun b")
                for _ in range(cl):
                    out.append(self._read_bits(bits, pos, 8)); pos += 8
        return bytes(out[:ol])
    def _paqjp_t25(self, data):
        if not data: return b'\x01'
        n = 3; res = bytearray(data)
        for i in range(len(res)): res[i] = (pow(res[i] + 1, n, 257) - 1) & 0xFF
        return bytes([n]) + bytes(res)
    def _paqjp_r25(self, data):
        if data == b'\x01': return b''
        if len(data) < 2: raise TransformError("FLT25")
        n = data[0]; inv = mod_inv(n, 256)
        if inv is None: raise TransformError(f"FLT25 {n}")
        res = bytearray(data[1:])
        for i in range(len(res)): res[i] = (pow(res[i] + 1, inv, 257) - 1) & 0xFF
        return bytes(res)
    def _paqjp_t26(self, data):
        if not data: return b'\x01\x00'
        n = (len(data) * 7 + 13) & 0xFFFF
        if n % 2 == 0: n ^= 1
        e = pow(n, 16777216, 256) | 1
        res = bytearray(data)
        for i in range(len(res)): res[i] = (pow(res[i] + 1, e, 257) - 1) & 0xFF
        return bytes([n & 0xFF, (n >> 8) & 0xFF]) + bytes(res)
    def _paqjp_r26(self, data):
        if data == b'\x01\x00': return b''
        if len(data) < 2: raise TransformError("FLT26")
        n = data[0] | (data[1] << 8)
        if n % 2 == 0: n ^= 1
        e = pow(n, 16777216, 256) | 1
        inv = mod_inv(e, 256)
        if inv is None: raise TransformError(f"FLT26 {e}")
        res = bytearray(data[2:])
        for i in range(len(res)): res[i] = (pow(res[i] + 1, inv, 257) - 1) & 0xFF
        return bytes(res)
    def _paqjp_t27(self, data):
        if not data:
            o = bytearray(b'\x00\x00\x00\x00\x01\x00'); o.extend(b'\x00' * 1024)
            return bytes(o)
        BS = 1024; tb = (len(data) + BS - 1) // BS
        out = bytearray(); out.extend(len(data).to_bytes(4, 'big'))
        for bi in range(tb):
            s = bi * BS; e = min(s + BS, len(data))
            ch = data[s:e]; pad = BS - len(ch)
            if pad: ch = ch + b'\x00' * pad
            n = ((len(data) * 7 + bi * 13 + 1) & 0xFFFF) | 1
            e_ = pow(n, 16777216, 256) | 1
            e200 = pow(e_, 200, 256)
            t = bytearray(ch)
            for i in range(BS): t[i] = (pow(t[i] + 1, e200, 257) - 1) & 0xFF
            out.append(n & 0xFF); out.append((n >> 8) & 0xFF); out.extend(t)
        return bytes(out)
    def _paqjp_r27(self, data):
        if len(data) < 4: raise TransformError("FLT27")
        ol = int.from_bytes(data[:4], 'big')
        p = data[4:]; BS = 1024; btl = 2 + BS
        if len(p) % btl != 0: raise TransformError("FLT27 a")
        nb = len(p) // btl; dec = bytearray()
        for bi in range(nb):
            off = bi * btl
            n = p[off] | (p[off + 1] << 8); ch = p[off + 2:off + 2 + BS]
            n |= 1
            e_ = pow(n, 16777216, 256) | 1
            e200 = pow(e_, 200, 256)
            inv = mod_inv(e200, 256)
            if inv is None: raise TransformError(f"FLT27 {e200}")
            for i in range(BS): dec.append((pow(ch[i] + 1, inv, 257) - 1) & 0xFF)
        return bytes(dec[:ol])
    def _compress_backend_with_flag(self, data):
        cands = []
        try: cands.append((1, zstd_cctx.compress(data)))
        except Exception: pass
        if paq is not None:
            try: cands.append((2, paq.compress(data)))
            except Exception: pass
        if HAS_BROTLI:
            try: cands.append((3, brotli.compress(data, quality=11)))
            except Exception: pass
        if HAS_LZMA:
            try: cands.append((4, lzma.compress(data, preset=9 | lzma.PRESET_EXTREME)))
            except Exception: pass
        cands.append((0, data))
        bf, bd = min(cands, key=lambda x: len(x[1]))
        return bytes([bf]) + bd
    def _decompress_backend_with_flag(self, data):
        if not data: return b''
        f = data[0]; p = data[1:]
        if f == 0: return p
        if f == 1: return zstd_dctx.decompress(p)
        if f == 2 and paq is not None: return paq.decompress(p)
        if f == 3 and HAS_BROTLI: return brotli.decompress(p)
        if f == 4 and HAS_LZMA: return lzma.decompress(p)
        raise TransformError(f"bkf {f}")
    def _paqjp_t28(self, data):
        BS = 1024
        if not data:
            ch = b'\x00' * BS; c = self._compress_backend_with_flag(ch)
            o = bytearray(struct.pack('>I', 0))
            o += b'\x01\x00' + bytes([(len(c) >> 8) & 0xFF, len(c) & 0xFF]) + c
            return bytes(o)
        tb = (len(data) + BS - 1) // BS
        out = bytearray(); out.extend(len(data).to_bytes(4, 'big'))
        for bi in range(tb):
            s = bi * BS; e = min(s + BS, len(data))
            ch = data[s:e] + b'\x00' * (BS - len(data[s:e]))
            n = ((len(data) * 7 + bi * 13 + 1) & 0xFFFF) | 1
            e_ = pow(n, 16777216, 256) | 1; e200 = pow(e_, 200, 256)
            t = bytearray(ch)
            for i in range(BS): t[i] = (pow(t[i] + 1, e200, 257) - 1) & 0xFF
            c = self._compress_backend_with_flag(bytes(t))
            out += bytes([n & 0xFF, (n >> 8) & 0xFF,
                          (len(c) >> 8) & 0xFF, len(c) & 0xFF]) + c
        return bytes(out)
    def _paqjp_r28(self, data):
        if len(data) < 4: raise TransformError("FLT28")
        ol = int.from_bytes(data[:4], 'big'); p = data[4:]
        pos = 0; dec = bytearray()
        while pos < len(p):
            n = p[pos] | (p[pos + 1] << 8); pos += 2
            cl = (p[pos] << 8) | p[pos + 1]; pos += 2
            cb = p[pos:pos + cl]; pos += cl
            b = self._decompress_backend_with_flag(cb)
            n |= 1
            e_ = pow(n, 16777216, 256) | 1
            e200 = pow(e_, 200, 256)
            inv = mod_inv(e200, 256)
            if inv is None: raise TransformError(f"FLT28 {e200}")
            t = bytearray(b)
            for i in range(len(t)): t[i] = (pow(t[i] + 1, inv, 257) - 1) & 0xFF
            dec.extend(t)
        return bytes(dec[:ol])
    def _paqjp_t29(self, data):
        BS = 32
        if not data:
            ch = b'\x00' * BS; c = self._compress_backend_with_flag(ch)
            o = bytearray(struct.pack('>I', 0))
            o += b'\x01\x00' + bytes([(len(c) >> 8) & 0xFF, len(c) & 0xFF]) + c
            return bytes(o)
        tb = (len(data) + BS - 1) // BS
        out = bytearray(); out.extend(len(data).to_bytes(4, 'big'))
        for bi in range(tb):
            s = bi * BS; e = min(s + BS, len(data))
            ch = data[s:e] + b'\x00' * (BS - len(data[s:e]))
            n = ((len(data) * 7 + bi * 13 + 1) & 0xFFFF) | 1
            c = self._compress_backend_with_flag(bytes(ch))
            out += bytes([n & 0xFF, (n >> 8) & 0xFF,
                          (len(c) >> 8) & 0xFF, len(c) & 0xFF]) + c
        return bytes(out)
    def _paqjp_r29(self, data):
        if len(data) < 4: raise TransformError("FLT29")
        ol = int.from_bytes(data[:4], 'big'); p = data[4:]
        pos = 0; dec = bytearray()
        while pos < len(p):
            n = p[pos] | (p[pos + 1] << 8); pos += 2
            cl = (p[pos] << 8) | p[pos + 1]; pos += 2
            cb = p[pos:pos + cl]; pos += cl
            dec.extend(self._decompress_backend_with_flag(cb))
        return bytes(dec[:ol])
    def _paqjp_t30(self, data):
        BS = 33
        if not data:
            ch = b'\x00' * BS; c = self._compress_backend_with_flag(ch)
            o = bytearray(struct.pack('>I', 0))
            o += b'\x01\x01' + bytes([(len(c) >> 8) & 0xFF, len(c) & 0xFF]) + c
            return bytes(o)
        tb = (len(data) + BS - 1) // BS
        out = bytearray(); out.extend(len(data).to_bytes(4, 'big'))
        for bi in range(tb):
            s = bi * BS; e = min(s + BS, len(data))
            ch = data[s:e] + b'\x00' * (BS - len(data[s:e]))
            h = hashlib.sha256(ch + bytes([bi & 0xFF, (len(data) >> 8) & 0xFF,
                                           len(data) & 0xFF])).digest()
            enc = bytes([32]) + h
            c = self._compress_backend_with_flag(ch)
            out += enc + bytes([(len(c) >> 8) & 0xFF, len(c) & 0xFF]) + c
        return bytes(out)
    def _paqjp_r30(self, data):
        if len(data) < 4: raise TransformError("FLT30")
        ol = int.from_bytes(data[:4], 'big'); p = data[4:]
        pos = 0; dec = bytearray()
        while pos < len(p):
            Ln = p[pos]; pos += 1
            if Ln > 32 or pos + Ln > len(p): raise TransformError("FLT30 n")
            pos += Ln
            cl = (p[pos] << 8) | p[pos + 1]; pos += 2
            cb = p[pos:pos + cl]; pos += cl
            dec.extend(self._decompress_backend_with_flag(cb))
        return bytes(dec[:ol])

    # ---- 41..44 ----
    def transform_41(self, data):
        if not data: return b''
        t = bytearray(data); m = bytes([0x27, 0x03])
        for i in range(min(len(t), 8)): t[i] ^= m[i % 2]
        return bytes(t)
    reverse_transform_41 = transform_41
    def transform_42(self, data):
        if not data: return b''
        t = bytearray(data); m = bytes([0x27, 0x03])
        for i in range(len(t)): t[i] ^= m[i % 2]
        return bytes(t)
    reverse_transform_42 = transform_42
    def transform_43(self, data):
        if not data: return b''
        t = bytearray(data); m = bytes([0x10, 0x00, 0x00])
        for i in range(0, len(t), 3):
            for j in range(min(3, len(t) - i)): t[i + j] ^= m[j]
        return bytes(t)
    reverse_transform_43 = transform_43
    def transform_44(self, data):
        if not data: return b''
        return base64.b64encode(data)
    def reverse_transform_44(self, data):
        if not data: return b''
        try: return base64.b64decode(data, validate=False)
        except Exception as e: raise TransformError(f"b64-44 {e}")

    # ---- 45 ----
    @staticmethod
    def _huffman_code_lengths(freq):
        heap = [(f, i, i) for i, f in enumerate(freq) if f > 0]
        if not heap: return [0] * len(freq)
        if len(heap) == 1:
            L = [0] * len(freq); L[heap[0][2]] = 1; return L
        heapq.heapify(heap); nid = len(freq)
        while len(heap) > 1:
            f1, _, n1 = heapq.heappop(heap); f2, _, n2 = heapq.heappop(heap)
            heapq.heappush(heap, (f1 + f2, nid, (n1, n2))); nid += 1
        L = [0] * len(freq)
        def trav(n, d):
            if isinstance(n, int): L[n] = d
            else: trav(n[0], d + 1); trav(n[1], d + 1)
        trav(heap[0][2], 0); return L
    @staticmethod
    def _huffman_canonical_codes(L):
        syms = sorted(range(len(L)), key=lambda s: (L[s], s))
        codes = {}; c = 0; pl = 0; first = True
        for s in syms:
            cl = L[s]
            if cl == 0: continue
            if first: pl = cl; first = False
            elif cl != pl: c <<= (cl - pl); pl = cl
            codes[s] = (c, cl); c += 1
        return codes
    @staticmethod
    def _huffman_lengths_limited(freq, max_bits=15):
        used = [i for i, f in enumerate(freq) if f > 0]
        if not used: return [0] * len(freq)
        if len(used) == 1:
            L = [0] * len(freq); L[used[0]] = 1; return L
        heap = [(freq[i], i, i) for i in used]
        heapq.heapify(heap); nid = len(freq)
        depth = {i: 0 for i in used}
        while len(heap) > 1:
            f1, _, n1 = heapq.heappop(heap); f2, _, n2 = heapq.heappop(heap)
            for leaf in _tree_leaves(n1): depth[leaf] += 1
            for leaf in _tree_leaves(n2): depth[leaf] += 1
            heapq.heappush(heap, (f1 + f2, nid, (n1, n2))); nid += 1
        depths = [min(depth[i], max_bits) for i in used]
        def kraft(ds): return sum(2.0 ** (-d) for d in ds)
        order = sorted(range(len(depths)), key=lambda k: depths[k])
        while True:
            moved = False
            for k in order:
                d = depths[k]
                if d >= max_bits: continue
                if kraft(depths) + 2.0 ** (-(d + 1)) <= 1.0 + 1e-12:
                    depths[k] = d + 1
                    order.sort(key=lambda k: depths[k])
                    moved = True; break
            if not moved: break
        L = [0] * len(freq)
        for i, d in zip(used, depths): L[i] = d
        return L
    def transform_45(self, data):
        if not data:
            header = bytearray((0).to_bytes(4, 'big'))
            header.extend(bytes(256))
            return bytes(header), 0x00
        freq = [0] * 256
        for b in data: freq[b] += 1
        cl = self._huffman_lengths_limited(freq, max_bits=15)
        if max(cl) > 15: raise TransformError("Huff45 cap")
        codes = self._huffman_canonical_codes(cl)
        hdr = bytearray(len(data).to_bytes(4, 'big'))
        hdr.extend(cl)
        bits = []
        for b in data:
            c, n = codes[b]
            for i in range(n - 1, -1, -1): bits.append((c >> i) & 1)
        pad = (8 - len(bits) % 8) % 8; bits.extend([0] * pad)
        out = bytearray(hdr)
        for i in range(0, len(bits), 8):
            v = 0
            for j in range(8): v = (v << 1) | bits[i + j]
            out.append(v)
        return bytes(out), 0x00
    def reverse_transform_45(self, data, lossy_key=0x00):
        if len(data) < 4 + 256: raise TransformError("Huff45 short")
        ol = int.from_bytes(data[:4], 'big')
        cl = list(data[4:260]); payload = data[260:]
        if ol == 0:
            if any(cl): raise TransformError("Huff45 empty table")
            return b''
        if max(cl) > 15: raise TransformError("Huff45 cap")
        syms = sorted(range(256), key=lambda s: (cl[s], s))
        code_to = {}; c = 0; pl = 0; first = True
        for s in syms:
            L = cl[s]
            if L == 0: continue
            if first: pl = L; first = False
            elif L != pl: c <<= (L - pl); pl = L
            code_to[(L, c)] = s; c += 1
        bits = []
        for b in payload:
            for i in range(7, -1, -1): bits.append((b >> i) & 1)
        out = bytearray(); pos = 0; nb = len(bits)
        maxL = max(cl) if any(cl) else 0
        while pos < nb and len(out) < ol:
            found = False
            for L in range(1, maxL + 1):
                if pos + L > nb: break
                v = 0
                for j in range(L): v = (v << 1) | bits[pos + j]
                if (L, v) in code_to:
                    out.append(code_to[(L, v)]); pos += L; found = True; break
            if not found: raise TransformError(f"Huff45 bad bit at {pos}")
        if len(out) != ol: raise TransformError("Huff45 len mismatch")
        for i in range(pos, nb):
            if bits[i] != 0: raise TransformError("Huff45 nonzero padding")
        return bytes(out)

    # ---- 46..47 ----
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

    # ---- 57 ----
    def transform_57(self, data):
        if len(data) < 4:
            pad = 4 - len(data); k = 0
            return bytes([pad]) + k.to_bytes(4, 'little') + data + b'\x00' * pad
        n = len(data); pad = (4 - n % 4) % 4
        padded = data + b'\x00' * pad
        blocks = [padded[i:i + 4] for i in range(0, len(padded), 4)]
        mc, _ = Counter(blocks).most_common(1)[0]
        k = int.from_bytes(mc, 'little')
        out = bytearray()
        for blk in blocks:
            out.extend((int.from_bytes(blk, 'little') ^ k).to_bytes(4, 'little'))
        return bytes([pad]) + k.to_bytes(4, 'little') + bytes(out)
    def reverse_transform_57(self, data):
        if len(data) < 5: raise TransformError("T57")
        pad = data[0]; k = int.from_bytes(data[1:5], 'little')
        p = data[5:]
        if len(p) % 4 != 0: raise TransformError("T57 l")
        out = bytearray()
        for i in range(0, len(p), 4):
            out.extend((int.from_bytes(p[i:i + 4], 'little') ^ k).to_bytes(4, 'little'))
        if pad: out = out[:-pad]
        return bytes(out)

    # ---- 58 ----
    def transform_58(self, data):
        if not data:
            return (b'\x58' + b'\x00' + b'\x00' + (0).to_bytes(8, 'big')
                    + b'\x00' + b'\x00' * 256)
        sha_h = hashlib.sha256(data).digest()
        depths = [4, 16, 32, 64]; bd = depths[sha_h[0] & 0x03]
        bd_code = {4: 0, 16: 1, 32: 2, 64: 3}[bd]
        if bd == 4:
            words = []
            for b in data:
                words.append((b >> 4) & 0xF); words.append(b & 0xF)
            mask = 0xF; wbytes = 1
        else:
            wbytes = bd // 8
            padded = data + b'\x00' * ((-len(data)) % wbytes)
            words = [int.from_bytes(padded[i:i + wbytes], 'big')
                     for i in range(0, len(padded), wbytes)]
            mask = (1 << bd) - 1
        n = len(words)
        fibs = self.fibonacci or [0, 1]; Lf = len(fibs)
        const = Counter(words).most_common(1)[0][0]
        lz_pred = [0] * n; last_after = {}
        for i in range(n):
            if i == 0: lz_pred[i] = const
            else:
                lz_pred[i] = last_after.get(words[i - 1], const)
                last_after[words[i - 1]] = words[i]
        def pred_const(i): return const
        def pred_fib(i):
            if i == 0: return const
            return (words[i - 1] + fibs[i % Lf]) & mask
        def pred_lz(i): return lz_pred[i]
        def pack_residuals(res):
            rb = bytearray()
            if bd == 4:
                for i in range(0, len(res), 2):
                    v = res[i] << 4
                    if i + 1 < len(res): v |= res[i + 1]
                    rb.append(v)
            elif bd == 16:
                for r in res:
                    rb.append((r >> 8) & 0xFF); rb.append(r & 0xFF)
            elif bd == 32:
                for r in res: rb.extend(r.to_bytes(4, 'big'))
            else:
                for r in res: rb.extend(r.to_bytes(8, 'big'))
            return bytes(rb)
        best = None
        for code, fn in ((0, pred_const), (1, pred_fib), (2, pred_lz)):
            res = [(words[i] - fn(i)) & mask for i in range(n)]
            rb = pack_residuals(res)
            sc = sum(1 for i in range(1, len(rb)) if rb[i] != rb[i - 1])
            if best is None or sc < best[0]: best = (sc, code, rb)
        _, pred_code, rbytes = best
        freq = [0] * 256
        for b in rbytes: freq[b] += 1
        cl = self._huffman_code_lengths(freq)
        codes = self._huffman_canonical_codes(cl)
        bits = []
        for b in rbytes:
            c, ln = codes[b]
            for k in range(ln - 1, -1, -1): bits.append((c >> k) & 1)
        bits.extend([0] * ((8 - len(bits) % 8) % 8))
        huff = bytearray()
        for i in range(0, len(bits), 8):
            v = 0
            for j in range(8): v = (v << 1) | bits[i + j]
            huff.append(v)
        key_mat = b'T58' + len(data).to_bytes(8, 'big') + bytes(cl)
        seed = hashlib.sha256(key_mat).digest()
        stream = bytearray(); ctr = 0
        while len(stream) < len(huff):
            stream.extend(hashlib.sha256(seed + ctr.to_bytes(8, 'big')).digest()); ctr += 1
        whitened = bytes(h ^ s for h, s in zip(huff, stream))
        body = bytearray()
        body.append(0x58); body.append(bd_code); body.append(pred_code)
        body.extend(len(data).to_bytes(8, 'big'))
        if bd == 4: body.append(const & 0xFF)
        else: body.extend(const.to_bytes(wbytes, 'big'))
        body.extend(bytes(cl)); body.extend(whitened)
        return bytes(body)
    def reverse_transform_58(self, data):
        if not data or data[0] != 0x58: raise TransformError("T58 magic")
        pos = 1
        bd_code = data[pos]; pos += 1
        pred_code = data[pos]; pos += 1
        orig_len = int.from_bytes(data[pos:pos + 8], 'big'); pos += 8
        if bd_code > 3 or pred_code > 2: raise TransformError("T58 hdr")
        depths = [4, 16, 32, 64]; bd = depths[bd_code]
        wbytes = 0 if bd == 4 else bd // 8
        if bd == 4:
            if pos + 1 > len(data): raise TransformError("T58 short")
            const = data[pos] & 0xF; pos += 1; mask = 0xF
        else:
            if pos + wbytes > len(data): raise TransformError("T58 short")
            const = int.from_bytes(data[pos:pos + wbytes], 'big')
            pos += wbytes; mask = (1 << bd) - 1
        if pos + 256 > len(data): raise TransformError("T58 short cl")
        cl = list(data[pos:pos + 256]); pos += 256
        huff_w = data[pos:]
        if orig_len == 0: return b''
        key_mat = b'T58' + orig_len.to_bytes(8, 'big') + bytes(cl)
        seed = hashlib.sha256(key_mat).digest()
        stream = bytearray(); ctr = 0
        while len(stream) < len(huff_w):
            stream.extend(hashlib.sha256(seed + ctr.to_bytes(8, 'big')).digest()); ctr += 1
        huff = bytes(h ^ s for h, s in zip(huff_w, stream))
        syms = sorted(range(256), key=lambda s: (cl[s], s))
        code_to = {}; c = 0; pl = 0; first = True
        for s in syms:
            L = cl[s]
            if L == 0: continue
            if first: pl = L; first = False
            elif L != pl: c <<= (L - pl); pl = L
            code_to[(L, c)] = s; c += 1
        maxL = max(cl) if any(cl) else 0
        bits = []
        for b in huff:
            for i in range(7, -1, -1): bits.append((b >> i) & 1)
        if bd == 4:
            n = orig_len * 2; n_rbytes = (n + 1) // 2
        else:
            n = (orig_len + wbytes - 1) // wbytes; n_rbytes = n * wbytes
        rbytes = bytearray(); bpos = 0; nb = len(bits)
        while len(rbytes) < n_rbytes and bpos < nb:
            found = False
            for L in range(1, maxL + 1):
                if bpos + L > nb: break
                v = 0
                for j in range(L): v = (v << 1) | bits[bpos + j]
                if (L, v) in code_to:
                    rbytes.append(code_to[(L, v)]); bpos += L; found = True; break
            if not found: raise TransformError("T58 huff dec")
        if len(rbytes) != n_rbytes: raise TransformError("T58 huff len")
        if bd == 4:
            residuals = []
            for b in rbytes:
                residuals.append((b >> 4) & 0xF); residuals.append(b & 0xF)
            residuals = residuals[:n]
        elif bd == 16:
            residuals = [int.from_bytes(rbytes[i:i + 2], 'big') for i in range(0, len(rbytes), 2)]
        elif bd == 32:
            residuals = [int.from_bytes(rbytes[i:i + 4], 'big') for i in range(0, len(rbytes), 4)]
        else:
            residuals = [int.from_bytes(rbytes[i:i + 8], 'big') for i in range(0, len(rbytes), 8)]
        fibs = self.fibonacci or [0, 1]; Lf = len(fibs)
        words = [0] * n; last_after = {}
        for i in range(n):
            if pred_code == 0: p = const
            elif pred_code == 1: p = const if i == 0 else (words[i - 1] + fibs[i % Lf]) & mask
            else: p = const if i == 0 else last_after.get(words[i - 1], const)
            w = (residuals[i] + p) & mask
            words[i] = w
            if i >= 1: last_after[words[i - 1]] = w
        if bd == 4:
            out = bytearray()
            for i in range(0, n, 2):
                hi = words[i] & 0xF
                lo = words[i + 1] & 0xF if i + 1 < n else 0
                out.append((hi << 4) | lo)
            return bytes(out[:orig_len])
        out = bytearray()
        for w in words: out.extend(w.to_bytes(wbytes, 'big'))
        return bytes(out[:orig_len])

    def _dynamic(self, n):
        def tf(data):
            if not data: return b''
            sd = self.get_seed(n % len(self.seed_tables), len(data))
            return bytes(b ^ sd for b in data)
        def rf(data, lossy_key=0x00):
            if not data: return b''
            sd = self.get_seed(n % len(self.seed_tables), len(data))
            return bytes(b ^ sd for b in data)
        return tf, rf

    def transform_256(self, d): return d
    reverse_transform_256 = transform_256

    # ============================================================
    # WRAPPERS  ← ★ FIXED _wrap_single_rev ★
    # ============================================================
    def _wrap_single_fwd(self, fn):
        def fwd(data): return fn(data), 0x00
        return fwd

    def _wrap_single_rev(self, fn):
        # ★ FIX: accept ANY lossy_key. The key is only a checksum that
        #   _wrap_rev_with_checksum has already verified. Do not re-check.
        def rev(data, lossy_key=0x00):
            return fn(data)
        return rev

    def _wrap_rev_with_checksum(self, fn):
        def rev(data, lossy_key=0x00):
            if lossy_key != 0x00:
                got = _lossy_checksum(data)
                if got != lossy_key:
                    raise TransformError(
                        f"checksum {lossy_key:#04x} != {got:#04x}"
                    )
            return fn(data, lossy_key)
        return rev

    def _build_transform_maps(self):
        self.fwd_transforms = {}
        self.rev_transforms = {}
        EXPLICIT = {
            1:  ("transform_01", "reverse_transform_01"),
            2:  ("transform_02", "reverse_transform_02"),
            3:  ("transform_03", "reverse_transform_03"),
            4:  ("transform_04", "reverse_transform_04"),
            5:  ("transform_05", "reverse_transform_05"),
            6:  ("transform_06", "reverse_transform_06"),
            7:  ("transform_07", "reverse_transform_07"),
            8:  ("transform_08", "reverse_transform_08"),
            9:  ("transform_09", "reverse_transform_09"),
            10: ("transform_10", "reverse_transform_10"),
            11: ("transform_11", "reverse_transform_11"),
            12: ("transform_12", "reverse_transform_12"),
            13: ("transform_13", "reverse_transform_13"),
            14: ("transform_14", "reverse_transform_14"),
            15: ("transform_15", "reverse_transform_15"),
            16: ("transform_16", "reverse_transform_16"),
            17: ("transform_17", "reverse_transform_17"),
            18: ("transform_18", "reverse_transform_18"),
            19: ("transform_19", "reverse_transform_19"),
            20: ("transform_20", "reverse_transform_20"),
            21: ("transform_21", "reverse_transform_21"),
            22: ("transform_22", "reverse_transform_22"),
            23: ("transform_23", "reverse_transform_23"),
            24: ("transform_24", "reverse_transform_24"),
            25: ("transform_25", "reverse_transform_25"),
            26: ("transform_26", "reverse_transform_26"),
            27: ("transform_27", "reverse_transform_27"),
            28: ("transform_28", "reverse_transform_28"),
            29: ("transform_29", "reverse_transform_29"),
            30: ("transform_30", "reverse_transform_30"),
            31: ("transform_31", "reverse_transform_31"),
            32: ("transform_32", "reverse_transform_32"),
            33: ("_paqjp_t23",   "_paqjp_r23"),
            34: ("_paqjp_t24",   "_paqjp_r24"),
            35: ("_paqjp_t25",   "_paqjp_r25"),
            36: ("_paqjp_t26",   "_paqjp_r26"),
            37: ("_paqjp_t27",   "_paqjp_r27"),
            38: ("_paqjp_t28",   "_paqjp_r28"),
            39: ("_paqjp_t29",   "_paqjp_r29"),
            40: ("_paqjp_t30",   "_paqjp_r30"),
            41: ("transform_41", "reverse_transform_41"),
            42: ("transform_42", "reverse_transform_42"),
            43: ("transform_43", "reverse_transform_43"),
            44: ("transform_44", "reverse_transform_44"),
            45: ("transform_45", "reverse_transform_45"),
            46: ("transform_46", "reverse_transform_46"),
            47: ("transform_47", "reverse_transform_47"),
            57: ("transform_57", "reverse_transform_57"),
            58: ("transform_58", "reverse_transform_58"),
            256:("transform_256","reverse_transform_256"),
        }
        for t, (fname, rname) in EXPLICIT.items():
            fwd_raw = getattr(self, fname)
            rev_raw = getattr(self, rname)
            if t in (23, 24, 45):
                self.fwd_transforms[t] = fwd_raw
                self.rev_transforms[t] = rev_raw
            else:
                self.fwd_transforms[t] = self._wrap_single_fwd(fwd_raw)
                self.rev_transforms[t] = self._wrap_single_rev(rev_raw)
        for t in range(1, 257):
            if t in self.fwd_transforms: continue
            fwd_dyn, rev_dyn = self._dynamic(t)
            self.fwd_transforms[t] = self._wrap_single_fwd(fwd_dyn)
            self.rev_transforms[t] = self._wrap_single_rev(rev_dyn)
        for t in range(1, 257):
            self.rev_transforms[t] = self._wrap_rev_with_checksum(self.rev_transforms[t])

    def _precompute_quantum_transforms(self):
        if not USE_QUANTUM or not HAS_QISKIT: return
        size = 1 << self.QUANTUM_QUBITS
        for i in range(8):
            rng = random.Random(1000 + i)
            perm = list(range(size)); rng.shuffle(perm)
            inv = [0] * size
            for j, p in enumerate(perm): inv[p] = j
            def fwd(data, p=perm): return bytes(p[b] for b in data)
            def rev(data, iv=inv): return bytes(iv[b] for b in data)
            self.fwd_transforms[256 + i + 1] = self._wrap_single_fwd(fwd)
            self.rev_transforms[256 + i + 1] = self._wrap_single_rev(rev)

    def _encode_marker_single(self, t, lossy_key=0x00):
        if t <= 252: m = bytes([t - 1])
        elif t <= 255: m = bytes([254, t - 253])
        else: m = bytes([255, (t - 256) // 256, (t - 256) % 256])
        return m + bytes([lossy_key & 0xFF])
    def _encode_marker_raw(self):
        return bytes([252, 0x00])
    def _decode_header(self, data):
        if len(data) < 2: return 0, (), 0x00
        f = data[0]
        if f < 252: return 2, (f + 1,), data[1]
        if f == 252: return 2, (), data[1]
        if f == 254:
            if len(data) < 3: return 0, (), 0x00
            x = data[1]
            return (3, (253 + x,), data[2]) if x <= 3 else (0, (), 0x00)
        if f == 255:
            if len(data) < 4: return 0, (), 0x00
            return 3, (256 + data[1] * 256 + data[2],), data[3]
        return 0, (), 0x00

    def _compress_backend(self, data):
        cands = [(0, data)]
        try:
            c = zstd_cctx.compress(data)
            if len(c) >= 4 and c[:4] == b'\x28\xb5\x2f\xfd': c = c[4:]
            cands.append((1, c))
        except Exception: pass
        if paq is not None:
            try:
                pd = paq.compress(data)
                if len(pd) >= 7 and pd[:4] == b'\x00\x63\x00\x00' and pd[-3:] == b'\xff\xff\xff':
                    cands.append((3, pd[4:-3]))
                else: cands.append((2, pd))
            except Exception: pass
        if HAS_BROTLI:
            try: cands.append((4, brotli.compress(data, quality=11)))
            except Exception: pass
        if HAS_LZMA:
            try: cands.append((5, lzma.compress(data, preset=9 | lzma.PRESET_EXTREME)))
            except Exception: pass
        bf, bd = min(cands, key=lambda x: len(x[1]))
        return bytes([bf]) + bd
    def _decompress_backend(self, data):
        if len(data) < 1: return None
        f = data[0]; p = data[1:]
        if f == 0: return p
        if f == 1:
            try: return zstd_dctx.decompress(b'\x28\xb5\x2f\xfd' + p)
            except Exception: return None
        if f == 2 and paq is not None:
            try: return paq.decompress(p)
            except Exception: return None
        if f == 3 and paq is not None:
            try: return paq.decompress(b'\x00\x63\x00\x00' + p + b'\xff\xff\xff')
            except Exception: return None
        if f == 4 and HAS_BROTLI:
            try: return brotli.decompress(p)
            except Exception: return None
        if f == 5 and HAS_LZMA:
            try: return lzma.decompress(p)
            except Exception: return None
        return None

    def _probe_transform(self, t, data, want_checksum=True):
        try: tr, _ = self.fwd_transforms[t](data)
        except Exception: return False, None, 0x00
        try: rt = self.rev_transforms[t](tr, 0x00)
        except Exception: return False, None, 0x00
        if rt != data: return False, None, 0x00
        if want_checksum: return True, tr, _lossy_checksum(tr)
        return True, tr, 0x00

    def _decompress_auto(self, data):
        off, seq, lossy_key = self._decode_header(data)
        if off == 0: raise DecompressionError("Bad header")
        p = data[off:]
        if not p: raise DecompressionError("Empty")
        r = self._decompress_backend(p)
        if r is None: raise DecompressionError("Backend failed")
        if not seq: return r, None
        return self._reverse_sequence(r, seq, lossy_key), seq
    def _reverse_sequence(self, data, seq, lossy_key=0x00):
        r = data
        if seq:
            r = self.rev_transforms[seq[-1]](r, lossy_key)
            for t in reversed(seq[:-1]):
                r = self.rev_transforms[t](r, 0x00)
        return r

    def _atomic_write(self, path, data):
        d = os.path.dirname(path) or '.'
        fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + '.tmp', dir=d)
        try: os.write(fd, data); os.fsync(fd)
        finally: os.close(fd)
        os.replace(tmp, path)

    # ================================================================
    # FAST self-test
    # ================================================================
    def fast_self_test(self):
        print("=" * 60); print("Self-Test (fast)"); print("=" * 60)
        t0 = time.time()
        all_ok = True

        print("\n[1/3] Deep test: transforms 23, 24, 45 (500 random each) ...")
        try:
            rng = random.Random(0xC0FFEE)
            cases = [b"", b"\x00", b"\xff", b"A", b"AB", b"AB"*100,
                     b"\x00"*1000, b"\xff"*1000, bytes(range(256)),
                     bytes(range(256))*8, b"hello world "*200,
                     b"a1b2c3_XYZ "*200,
                     "héllo wörld — ünïcode ✓\n".encode("utf-8")*50]
            for t in (23, 24, 45):
                for i, d0 in enumerate(cases):
                    tr, key = self.fwd_transforms[t](d0)
                    rt = self.rev_transforms[t](tr, key)
                    if rt != d0:
                        print(f"  FAIL t={t} case={i} len={len(d0)}")
                        all_ok = False; break
                if not all_ok: break
                for _ in range(500):
                    n = rng.randint(0, 1024)
                    d0 = bytes(rng.randint(0, 255) for _ in range(n))
                    tr, key = self.fwd_transforms[t](d0)
                    rt = self.rev_transforms[t](tr, key)
                    if rt != d0:
                        print(f"  FAIL t={t} n={n}")
                        all_ok = False; break
                if not all_ok: break
            if all_ok:
                print(f"  PASS 23/24/45 ({len(cases)} structured + 500 random each)")
        except Exception as e:
            print(f"  FAIL focused: {e}"); all_ok = False

        if all_ok:
            print("\n[2/3] Sample all 256 transforms (50 random each) ...")
            rng = random.Random(0xF00D)
            failed = []
            for t in range(1, 257):
                try:
                    for _ in range(50):
                        n = rng.randint(0, 256)
                        d0 = bytes(rng.randint(0, 255) for _ in range(n))
                        tr, key = self.fwd_transforms[t](d0)
                        rt = self.rev_transforms[t](tr, key)
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

        if all_ok:
            print("\n[3/3] Backend sanity ...")
            try:
                d0 = b"The quick brown fox jumps over the lazy dog. " * 20
                c = lzma.compress(d0, preset=9 | lzma.PRESET_EXTREME)
                if lzma.decompress(c) != d0: raise AssertionError()
                print(f"  PASS lzma ({len(d0)} → {len(c)})")
            except Exception as e:
                print(f"  FAIL lzma: {e}"); all_ok = False

        elapsed = time.time() - t0
        print()
        print("=" * 60)
        if all_ok:
            print(f"[All checks passed — 256/256 lossless]  ({elapsed:.1f}s)")
        else:
            print(f"[SOME CHECKS FAILED]  ({elapsed:.1f}s)")
        return all_ok


def main():
    print("UnifiedPAQJP+PJP (256/256 lossless)")
    try:
        dl = input("Download dictionaries? (y/n) [n]: ").strip().lower()
    except EOFError:
        dl = 'n'
    try_download = (dl == 'y')
    c = UnifiedCompressor(try_download=try_download)

    while True:
        print("\n" + "=" * 50)
        print("Menu (3 options):")
        print("  1) Compress")
        print("  2) Decompress")
        print("  3) Self-test")
        print("  (Ctrl+C or Ctrl+D to exit)")
        print("=" * 50)
        try:
            ch = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if ch == "1":
            try: f = input("Input file: ").strip()
            except (EOFError, KeyboardInterrupt): break
            if not f: continue
            try:
                with open(f, 'rb') as fh: data = fh.read()
            except Exception as e:
                print(f"Error: {e}"); continue
            print(f"\nInput: {len(data)} bytes")
            print("Evaluating all 256 transforms ...")
            cands = []
            t_start = time.time()
            for t in range(1, 257):
                ok, tr, key = c._probe_transform(t, data)
                if not ok: continue
                payload = c._compress_backend(tr)
                marker = c._encode_marker_single(t, key)
                cands.append((f".a{t}", marker + payload, f"transform #{t}"))
            if not cands:
                print("No candidates."); continue
            best_ext, best_payload, best_label = min(cands, key=lambda x: len(x[1]))
            outpath = f + best_ext
            c._atomic_write(outpath, best_payload)
            print(f"\nEvaluated {len(cands)} candidates in {time.time()-t_start:.1f}s")
            print(f"WINNER: {outpath}")
            print(f"  Size: {len(best_payload)} bytes  "
                  f"ratio: {len(best_payload)/max(1,len(data))*100:.2f}%")
            print(f"  Method: {best_label}")

        elif ch == "2":
            try: f = input("Compressed file (.aN): ").strip()
            except (EOFError, KeyboardInterrupt): break
            if not f: continue
            try:
                with open(f, 'rb') as fh: blob = fh.read()
            except Exception as e:
                print(f"Error: {e}"); continue
            m = re.search(r'\.a(\d+)$', f)
            if not m:
                print("Only .aN files supported here."); continue
            tnum = int(m.group(1))
            if not (1 <= tnum <= 256):
                print("Invalid transform number."); continue
            try:
                off, seq, lossy_key = c._decode_header(blob)
                r = c._decompress_backend(blob[off:])
                if r is None:
                    print("Backend decode failed."); continue
                orig = c.rev_transforms[tnum](r, lossy_key)
            except Exception as e:
                print(f"Decompression failed: {e}"); continue
            outfile = re.sub(r'\.a\d+$', '', os.path.basename(f))
            c._atomic_write(outfile, orig)
            print(f"Decompressed → {outfile} ({len(orig)} bytes)")

        elif ch == "3":
            c.fast_self_test()

        else:
            print("Invalid. Enter 1, 2, or 3.")


if __name__ == "__main__":
    main()
