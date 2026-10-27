# Acemi: Nihai Proje Planı ve Başlangıç Promptu

Bu dosya iki bölümden oluşur:

- **Bölüm A:** Planın tamamı (kararlar, mimari, veri şeması, test protokolü, aşamalar, riskler)
- **Bölüm B:** Kod yazacak yapay zekaya yapıştırılacak tek parça prompt

---

# BÖLÜM A: NİHAİ PLAN

## 1. Projenin özeti

**Acemi**, Python ile sıfırdan yazılan, klasik (alpha-beta tabanlı) bir satranç motoru. Hedef 1500 Elo ve üzeri. Üç ayrı rol vardır ve birbirine karışmaz:

| Rol | Kim | Ne yapar |
|---|---|---|
| Kod yazıcı | Yapay zeka | Motoru, test araçlarını, notebook'u yazar |
| Test koşucu | Kaggle | Sadece maçları ve testleri oynatır, ham sonucu GitHub'a gönderir |
| Analizci | Ayrı analiz ajanı | GitHub'daki sonuçları okur, analiz eder, sonraki adımı önerir |

Proje sahibi karar verici ve köprüdür: kodu GitHub'a yükler, Kaggle'da hücreleri çalıştırır, ajanın raporunu ve önerilerini onaylar.

## 2. Kesinleşen kararlar

| Konu | Karar |
|---|---|
| Proje adı | Acemi |
| Dil | Python. Kod yorumları ve isimler İngilizce, README Türkçe |
| Çekirdek bağımlılığı | Yok. Motor saf Python (PyPy'ye geçilebilsin diye ağır numpy yok) |
| `python-chess` | Motor çekirdeğinde yasak. Sadece `tools/` altında (Stockfish ile konuşma, PGN yazma) serbest |
| Board | Kendi 0x88 mailbox board'umuz |
| Ortam | Kaggle notebook (GUI yok) |
| Saklama | GitHub, public repo, token Kaggle Secrets'ta |
| Arama | Tek çekirdek, sade |
| Test maçları | Paralel, her çekirdekte bir maç |
| Test istatistiği | SPRT, 200+ maç, eşlenmiş açılışlar (her açılış iki renkle) |
| Elo ölçümü | Stockfish `UCI_LimitStrength` + `UCI_Elo` (en düşük ~1320) ve botun kendi eski sürümleri |
| Taktik testi | Evet (WAC, sonra STS) |
| Rastgelelik | Açılışta ve eşit hamlelerde hafif, ayarlanabilir, seed ile tekrarlanabilir |
| Açılış kitabı | Polyglot okuyucu. Testlerde kapalı |
| Pondering | Sonra |
| Syzygy | En sonda |
| Texel tuning | Eval oturunca |
| Sinir ağı | İleride NNUE benzeri küçük ağ, eval arayüzüne takılacak |
| Arayüz | Yok, sadece PGN/log |
| Çalışma düzeni | Her aşama sonunda dur, raporla, proje sahibi onaylasın |
| Analiz | Kaggle'da değil, GitHub'daki sonuçlar üzerinden ayrı ajan yapar |

**Dürüst notlar**

- Stockfish'in `UCI_Elo` ölçeği Lichess/CCRL puanıyla birebir örtüşmez. Elo takibi için kaba ama tutarlı bir ölçüdür.
- Saf Python'da motor birkaç bin ile birkaç on bin düğüm/saniye arasında çalışır. 1500 bu hızla zor ama mümkündür. PyPy'ye geçmek genelde belirgin hız kazandırır.
- Kaggle'da internet için telefon doğrulaması gerekir. Oturumların süre sınırı vardır, uzun koşular parçalanmalıdır.

## 3. Repo yapısı

```
acemi/
├── engine/
│   ├── board.py          # 0x88 board, make/unmake, FEN, Zobrist
│   ├── movegen.py        # pseudo-legal + legal hamle üretimi
│   ├── search.py         # negamax, alpha-beta, quiescence, ID, TT, pruning
│   ├── book.py           # Polyglot opening book okuyucu
│   ├── uci.py            # UCI protokolü
│   └── eval/
│       ├── base.py       # evaluate(board) arayüzü
│       └── classic.py    # materyal, PST, piyon yapısı vb.
├── tests/                # perft, birim testler, taktik pozisyon testleri
├── tools/
│   ├── match.py          # paralel maç yöneticisi
│   ├── sprt.py           # SPRT hesaplayıcı
│   ├── elo.py            # Elo farkı / güven aralığı
│   ├── tactics.py        # WAC/STS koşucusu
│   ├── summarize.py      # SUMMARY.md üreticisi (sadece olgular)
│   ├── record.py         # data/ kaydedici + index.csv + positions
│   └── position_lookup.py# "bu pozisyon oynandı mı" sorgusu
├── notebooks/
│   └── kaggle_runner.ipynb  # SADECE: çek, koştur, kaydet, push et
├── data/
│   ├── index.csv
│   ├── runs/<tarih>_<sürüm>_<rakip>_<hash>/
│   │   ├── meta.json
│   │   ├── results.json
│   │   ├── SUMMARY.md
│   │   ├── games.pgn.gz
│   │   ├── moves.jsonl.gz
│   │   └── engine.log.gz
│   ├── tactics/
│   └── positions/        # parça parça .gz
├── analysis/             # SADECE ajanın yazma alanı (kod buraya dokunmaz)
│   ├── <koşu-adı>.md
│   └── NEXT.md
├── AGENT_GUIDE.md        # ajan için: veri şeması, analiz protokolü, kurallar
├── CHANGELOG.md
└── README.md
```

## 4. Uçtan uca akış

```
1. Yapay zeka kodu yazar -> proje sahibi GitHub'a yükler
2. Kaggle notebook'u repoyu çeker -> testleri/maçları oynatır
3. Ham sonuçlar + SUMMARY.md otomatik data/runs/ altına yazılır -> GitHub'a push
4. Analiz ajanı repoyu çeker -> SUMMARY.md'yi okur -> gerekirse ham veriye iner
5. Ajan analysis/<koşu>.md ve analysis/NEXT.md yazar (GitHub'a push)
6. Proje sahibi NEXT.md'yi okur, kod yazıcıya götürür -> döngü tekrar eder
```

Kaggle notebook'unda **analiz, yorum veya karar mantığı yoktur.** `SUMMARY.md` sadece olgulardır, yorum içermez.

## 5. Veri şeması

Her dosyada `schema_version` alanı olur, böylece eski koşular ileride de okunabilir.

**`meta.json`:** schema_version, koşu adı, tarih, motor sürümü, git commit hash, motor ayarları (süre, hash boyutu, rastgelelik seed'i, kitap açık/kapalı), rakip bilgisi (Stockfish sürümü ve UCI_Elo), açılış seti adı, donanım (çekirdek sayısı, RAM, Python/PyPy sürümü), başlangıç ve bitiş zamanı.

**`results.json`:** maç sayısı, W/D/L, skor yüzdesi, Elo farkı tahmini ve güven aralığı, SPRT durumu (elo0, elo1, alpha, beta, LLR, karar), renk bazlı sonuçlar, taktik test oranı (varsa).

**`SUMMARY.md`** (sadece olgular):

- Skor, W/D/L, SPRT sonucu
- Biten maç sayısı ve ortalama hamle sayısı
- Zaman aşımı, illegal hamle, motor çökmesi sayısı
- Ortalama derinlik, nodes/saniye
- Açılış bazlı sonuçlar (en çok kaybedilen 10 açılış)
- Oyun evresine göre kayıp dağılımı (açılış/orta oyun/oyun sonu), olgu olarak
- Kullanılan sürüm ve karşılaştırılan sürüm

**`games.pgn.gz`:** tüm maçlar, açılış bilgisi ve sonuç etiketleriyle.

**`moves.jsonl.gz`:** her hamle için bir satır: maç no, hamle no, taraf, FEN, Zobrist hash, oynanan hamle, eval (cp), derinlik, düğüm sayısı, süre (ms).

**`engine.log.gz`:** motor logu.

**`data/positions/`:** pozisyon başına hash + FEN, görülme sayısı, W/D/L dağılımı, oynanan hamleler ve sayıları, ortalama eval. Yeni koşular mevcut veriyi birleştirerek günceller.

**`data/index.csv`:** her koşu için tek satır: koşu adı, tarih, sürüm, rakip, maç sayısı, skor, Elo farkı, SPRT sonucu.

**Boyut kuralı:** repo yaklaşık 500 MB'a yaklaşırsa kaba veri (`moves.jsonl.gz`, `games.pgn.gz`) Kaggle Dataset'e taşınır, özetler ve `index.csv` GitHub'da kalır. Bu kararı proje sahibi verir, kod yazıcı sadece uyarır.

## 6. Test ve ölçüm protokolü

1. **Açılış seti:** küçük, dengeli bir açılış seti (EPD veya PGN) kullanılır. Her açılış iki renkle oynanır (eşlenmiş çiftler). Botun kendi kitabı testlerde kapalıdır, aksi halde sonuçlar kitaba bağlı olur.
2. **Süre:** test maçlarında hamle başı 0.5-1 sn. Sürüm karşılaştırmasında süre tabanlı oynanır, çünkü bir özellik hızı değiştirdiğinde adil olan budur.
3. **Gürültü azaltma:** paralel maç sayısı çekirdek sayısını geçmez. Mümkünse bir çekirdek boş bırakılır. Stockfish tek thread ve küçük hash ile çalışır.
4. **SPRT:** alpha = beta = 0.05. Büyük kazanım beklenen aşamalarda elo0=0, elo1=10. Rafine aşamalarda elo0=0, elo1=5. Maç sayısı üst sınırı konur (örn. 1000) ve sınırda karar çıkmazsa "belirsiz" raporlanır.
5. **Stockfish ölçümü:** `UCI_LimitStrength=true`, `UCI_Elo` farklı seviyelerde (1320, 1500, 1700 ...). Bot hangi seviyeyle %50'ye yakın skor alıyorsa kaba Elo tahmini odur. Her raporda bu tahminin kaba olduğu yazılır.
6. **Taktik testleri:** WAC ve sonra STS, her sürümde sabit süreyle koşulur. Çözülen oran `data/tactics/` altına sürüm bazlı yazılır.
7. **Kural:** yeni sürüm anlamlı şekilde kazanmıyorsa özellik geri alınır. "İyileştirdim hissi" kanıt sayılmaz.

## 7. Aşamalar ve geçiş kriterleri

Bir aşama bitmeden bir sonrakine geçilmez. Her aşama sonunda yapay zeka durur, raporlar, proje sahibi onaylar.

| # | Aşama | İçerik | Bitti sayılma kriteri |
|---|---|---|---|
| 0 | Altyapı | Repo iskeleti, Kaggle notebook'u, push hattı (token Secrets'tan), veri şeması, `AGENT_GUIDE.md`, Stockfish kurulumu, sahte bir koşunun uçtan uca kaydı | Notebook repoyu çekiyor, sahte bir koşuyu `data/runs/` altına yazıp GitHub'a push ediyor. Token hiçbir yerde görünmüyor |
| 1 | Board ve hamle üretimi | 0x88 board, FEN, make/unmake, Zobrist, rok, en passant, terfi, 50 hamle, 3 tekrar, legal hamle filtresi | Perft: tüm referans pozisyonlarda sayılar tam tutuyor |
| 2 | UCI ve maç altyapısı | UCI protokolü, `match.py` (paralel), `sprt.py`, `elo.py`, `summarize.py`, `record.py`, pozisyon veri tabanı yazımı | Bot Stockfish'e karşı hatasız tam maç oynuyor, illegal hamle ve çökme yok, tüm veri şemaya uygun kaydediliyor |
| 3 | İlk arama | Materyal eval, negamax, alpha-beta | Rastgele oyuncuyu 100/100 yeniyor |
| 4 | Temel güç | PST (açılış/oyun sonu), quiescence, iterative deepening, zaman yönetimi | SPRT: önceki sürümden anlamlı üstün |
| 5 | Arama verimi | Move ordering (MVV-LVA), transposition table | SPRT: önceki sürümden üstün |
| 6 | İleri arama | Null move, LMR, killer ve history heuristics | SPRT: önceki sürümden üstün |
| 7 | Eval geliştirme | Geçer piyon, piyon yapısı (izole/çift/geri), şah güvenliği, mobilite, fil çifti, kale açık hat. Her özellik ayrı eklenir ve ayrı ölçülür | Her özellik SPRT ile kanıtlı. Fark yaratmayan özellik koda girmez |
| 8 | Açılış kitabı | Polyglot okuyucu, kitap dışında sorunsuz devam | Kitapta oynuyor, kitap bitince çökmüyor, testlerde kapatılabiliyor |
| 9 | Hız | Profiling, PyPy/Numba değerlendirmesi, nodes/sn raporu | Ölçülmüş ve artmış nodes/sn, perft hâlâ doğru, SPRT'de gerileme yok |
| 10 | Pozisyon sorgusu | `position_lookup.py`: hash/FEN ile "oynandı mı, sonuç ne" | Bilinen bir pozisyon için doğru istatistik dönüyor |
| 11 | İleri | Texel tuning, Syzygy, sonrasında NNUE benzeri eval | Ölçümle kanıtlı |

**Beklenen güç (kaba tahmin):** aşama 3 sonrası ~800-1000, aşama 4 ~1100-1300, aşama 5 ve 6 sonrası ~1300-1500, aşama 7 ve sonrası 1500+. Bunlar tahmindir, gerçek sayıyı ölçümler verecek.

## 8. Teknik tasarım notları

- **Board:** 0x88, taşlar sayısal kodlarla, taşların konum listesi tutulur (hızlı taş döngüsü için), make/unmake'te undo stack. Zobrist hash artımlı güncellenir.
- **Legal kontrol:** pseudo-legal üret, hamleyi yap, şah saldırı altındaysa geri al. Sade ve doğru, optimizasyon sonra.
- **Arama:** negamax + alpha-beta, aspiration window sonra. Zaman kontrolü her N düğümde bir.
- **Eval arayüzü:** `evaluate(board) -> int` (centipawn, hamle sırası olan taraf açısından). NNUE benzeri bir eval aynı arayüzle takılır.
- **Rastgelelik:** varsayılan açık, küçük eşik içindeki eşit hamleler arasında seçim, seed parametresiyle tekrarlanabilir. Testlerde seed sabitlenir.
- **UCI:** `uci, isready, ucinewgame, position, go (wtime/btime/winc/binc/movetime/depth/nodes), stop, quit, setoption`.

## 9. Riskler ve önlemler

| Risk | Önlem |
|---|---|
| Board hataları sessizce botu zayıflatır | Perft tam tutmadan ilerlenmez, board'a dokunan her değişiklikte perft yeniden koşulur |
| "İyileştirdim" yanılgısı | SPRT şart, kazanmayan özellik geri alınır |
| Kaggle gürültüsü (paylaşılan CPU) | Paralel maç sayısı çekirdek sayısını geçmez, gerekirse sonuç tekrarlanır |
| Token sızıntısı | Sadece Kaggle Secrets, loga ve repoya yazılmaz. Repo public olduğu için kritik |
| Repo şişmesi | Boyut uyarısı, kaba veri Kaggle Dataset'e taşınır |
| Kaggle oturum süresi | Uzun koşular parçalanır, her parça kendi klasörüne yazılır |
| Ajan ve yazıcı aynı dosyaya yazıp çakışır | `analysis/` sadece ajanın, kod ve `data/` sadece koşucu ve yazıcının |
| Yapay zekanın test etmeden "çalışıyor" demesi | Promptta açık yasak, perft ve testler zorunlu |

## 10. Başlamadan önce yapılacaklar

1. GitHub'da `acemi` adında **public repo** aç.
2. O repoya yazma izni olan bir **fine-grained token** oluştur.
3. Kaggle hesabını **telefonla doğrula**, notebook'ta **Internet: On** yap.
4. Token'ı Kaggle'da **Add-ons → Secrets** bölümüne ekle (adı `GITHUB_TOKEN`).
5. Analiz ajanı repoyu okuyabilecek şekilde ayarla (public repo olduğu için klonlamak yeterli).

---

# BÖLÜM B: NİHAİ PROMPT

Aşağıdaki bloğun tamamını kod yazacak yapay zekaya yapıştır.

````
Sen deneyimli bir satranç motoru geliştiricisisin. Benimle birlikte Python ile
SIFIRDAN "Acemi" adında bir satranç motoru yazacaksın. Kodu tamamen sen
yazıyorsun; ben çalıştıran, test eden ve karar veren kişiyim. Python bilgim
yok denecek kadar az (vibe coder), o yüzden açıklamaların sade Türkçe olsun.
Kodun her satırını anlamam gerekmiyor ama her aşamada ne yapıldığını ve bot'un
güçlenip güçlenmediğini anlamam gerekiyor.

================================================================
1. HEDEF
================================================================
- Klasik (alpha-beta tabanlı) bir satranç motoru. Hedef: ~1500+ Elo.
- Öncelik sırası: önce DOĞRULUK, sonra GÜÇ, en son HIZ.
- Motor SIFIRDAN yazılır: kendi 0x88 mailbox board'umuz, kendi hamle üretimi.
  `python-chess` motor çekirdeğinde (engine/) KULLANILMAYACAK. Yalnızca tools/
  altında (Stockfish ile UCI üzerinden konuşmak, PGN yazmak vb.) kullanılabilir.
- Motor çekirdeği harici bağımlılık içermeyecek (ağır numpy yok), böylece PyPy'ye
  geçmek mümkün kalır.
- Arama tek çekirdekte çalışır. Test maçları ise çekirdek sayısı kadar paralel
  oynatılır (her maç ayrı süreç).
- Kod yorumları ve değişken/fonksiyon isimleri İngilizce, README Türkçe.
- Kod sade, küçük fonksiyonlardan oluşmalı, gereksiz "zeki" kod olmamalı.

================================================================
2. ROLLER (karıştırma)
================================================================
- SEN: motoru, test araçlarını ve notebook'u yazarsın.
- KAGGLE: SADECE test koşturur. Notebook'ta analiz, yorum veya karar mantığı
  OLMAYACAK. Yaptığı iş: repoyu çek -> testleri/maçları oynat -> ham sonuçları
  data/ altına yaz -> GitHub'a push et.
- ANALİZ AJANI: Ben ayrı bir ajan çalıştıracağım. O, GitHub'daki sonuçları
  okuyup analiz edecek ve analysis/ klasörüne yazacak. Kodun analysis/ klasörüne
  ASLA yazmaz.
- BEN: kodu GitHub'a yüklerim, Kaggle'da hücreleri çalıştırırım, ajanın
  önerilerini onaylarım.

================================================================
3. ORTAM
================================================================
- Kaggle notebook, GUI yok. İlk hücrede çekirdek sayısı, RAM ve Python sürümü
  raporlansın (paralel maç sayısı buna göre ayarlanır).
- Stockfish: Kaggle'da çalışan bir kurulum yolu bul (apt-get veya resmi binary
  indirme) ve gerçekten çalıştığını test et. Çalışmayan bir yolu "çalışır"
  diye verme.
- GitHub: public repo. Push için token Kaggle Secrets'tan okunur
  (UserSecretsClient, secret adı GITHUB_TOKEN). Token ASLA koda, loga, hata
  mesajına, commit'e veya repoya yazılmaz. Repo public olduğu için bu çok kritik.
- Kaggle oturumunda dosyalar kalıcı değildir; kalıcılık yalnızca GitHub'dır.
- Kaggle oturum süre sınırı vardır: uzun koşular parçalanmalı, her parça kendi
  klasörüne kaydedilip push edilmelidir.

================================================================
4. REPO YAPISI
================================================================
acemi/
  engine/
    board.py        # 0x88 board, make/unmake, FEN, Zobrist
    movegen.py      # pseudo-legal + legal hamle üretimi
    search.py       # negamax, alpha-beta, quiescence, ID, TT, pruning
    book.py         # Polyglot opening book okuyucu
    uci.py          # UCI protokolü
    eval/
      base.py       # evaluate(board) arayüzü
      classic.py    # materyal, PST, piyon yapısı vb.
  tests/            # perft, birim testler, taktik pozisyon testleri
  tools/
    match.py        # paralel maç yöneticisi
    sprt.py         # SPRT hesaplayıcı
    elo.py          # Elo farkı ve güven aralığı
    tactics.py      # WAC/STS koşucusu
    summarize.py    # SUMMARY.md üreticisi (sadece olgular)
    record.py       # data/ kaydedici, index.csv, positions güncelleyici
    position_lookup.py  # "bu pozisyon daha önce oynandı mı" sorgusu
  notebooks/kaggle_runner.ipynb
  data/             # index.csv, runs/, tactics/, positions/
  analysis/         # SADECE analiz ajanının yazma alanı
  AGENT_GUIDE.md    # ajan için veri şeması + analiz protokolü
  CHANGELOG.md
  README.md         # Türkçe

================================================================
5. MİMARİ KURALLARI
================================================================
BOARD
- 0x88 mailbox. make_move/unmake_move (undo stack). FEN okuma/yazma.
- Artımlı (incremental) Zobrist hash.
- Rok (hak kaybı dahil), en passant, terfi (4 taş), 50 hamle kuralı, 3 tekrar
  kuralı, yetersiz materyal, mat/pat tespiti doğru olacak.
- Legal hamle: pseudo-legal üret, yap, şah saldırı altındaysa geri al. Önce
  doğru ol, optimizasyon sonra.

ARAMA VE EVAL AYRIMI
- Search ile eval tamamen ayrı. Eval bir arayüzün arkasında:
  evaluate(board) -> int (centipawn, hamle sırası olan taraf açısından).
  Böylece ileride NNUE benzeri bir eval aynı arayüzle takılabilir.

UCI
- Tam destek: uci, isready, ucinewgame, position (startpos/fen + moves),
  go (wtime, btime, winc, binc, movetime, depth, nodes, infinite), stop, quit,
  setoption. Motor adı "Acemi". Lichess'e ileride lichess-bot ile
  bağlanabilecek şekilde standartlara uygun olsun.
- Hamle süresi bir parametre. Test maçlarında ~0.5-1 sn/hamle.

RASTGELELİK
- Açılışta ve eşit değerli hamleler arasında ayarlanabilir hafif rastgelelik
  (UCI option olarak). Varsayılan açık. Testlerde seed sabitlenir ve
  tekrarlanabilir olmalı.

================================================================
6. TEST VE ÖLÇÜM KURALLARI
================================================================
- Açılış seti: küçük, dengeli, bilinen bir set (EPD/PGN). İnternetten
  indirilebilen standart bir set bul; bulamazsan rastgele 6-8 yarım hamlelik
  açılışlar üretip Stockfish ile eval'i +-100cp içinde olanları filtrele.
  Her açılış İKİ renkle oynanır (eşlenmiş çiftler).
- Testlerde botun kendi opening book'u KAPALI olur.
- Süre tabanlı oynat (özellikler hızı değiştirdiği için adil olan budur).
  Paralel maç sayısı çekirdek sayısını geçmesin; mümkünse bir çekirdek boş.
  Stockfish tek thread, küçük hash ile çalışsın.
- Sürüm karşılaştırması SPRT ile yapılır: alpha=beta=0.05. Büyük kazanım
  beklenen aşamalarda elo0=0, elo1=10; rafine aşamalarda elo0=0, elo1=5.
  Üst sınır maç sayısı koy (örn. 1000); sınırda karar çıkmazsa "belirsiz"
  raporla. Sınırları seçerken gerekçeni kısaca açıkla.
- Stockfish karşılaştırması: UCI_LimitStrength=true ve UCI_Elo farklı
  seviyelerle (en düşük ~1320, sonra 1500, 1700 ...). Bu ölçümün kaba olduğunu
  ve Lichess/CCRL puanıyla birebir örtüşmediğini her raporda belirt.
- Taktik test seti (WAC, sonra STS) her sürümde sabit süreyle çalıştırılır;
  çözülen oran data/tactics/ altına sürüm bazlı yazılır.
- Yeni sürüm anlamlı kazanmıyorsa özellik GERİ ALINIR.

PERFT REFERANS DEĞERLERİ (Chess Programming Wiki'den doğrula, tutmazsa
hata senin kodunda demektir):
- Başlangıç pozisyonu: d1=20, d2=400, d3=8902, d4=197281, d5=4865609,
  d6=119060324
- Kiwipete (r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq -):
  d1=48, d2=2039, d3=97862, d4=4085603
- Pozisyon 3 (8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - -):
  d1=14, d2=191, d3=2812, d4=43238, d5=674624
- Pozisyon 4 (r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1):
  d1=6, d2=264, d3=9467, d4=422333
- Pozisyon 5 (rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8):
  d1=44, d2=1486, d3=62379, d4=2103487
- Pozisyon 6 (r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10):
  d1=46, d2=2079, d3=89890, d4=3894594
Perft sonuçlarını hamle tipine göre (yakalama, en passant, rok, terfi, şah)
kırılımıyla da hata ayıklamada kullan. Board'a dokunan her değişiklikten sonra
perft yeniden koşulur.

================================================================
7. VERİ KAYDI (çok önemli: tüm veriler saklanacak)
================================================================
Her test koşusu için data/runs/<tarih>_<sürüm>_<rakip>_<kısa-hash>/ klasörü:
- meta.json: schema_version, koşu adı, tarih, motor sürümü, git commit hash,
  motor ayarları (süre, hash boyutu, rastgelelik seed'i, kitap açık/kapalı),
  rakip bilgisi (Stockfish sürümü, UCI_Elo), açılış seti adı, donanım
  (çekirdek, RAM, Python/PyPy sürümü), başlangıç/bitiş zamanı.
- results.json: schema_version, maç sayısı, W/D/L, skor %, Elo farkı ve güven
  aralığı, SPRT durumu (elo0, elo1, alpha, beta, LLR, karar), renk bazlı
  sonuçlar, taktik oranı (varsa).
- SUMMARY.md: SADECE OLGULAR, yorum yok. İçerik: skor, W/D/L, SPRT sonucu,
  biten maç sayısı ve ortalama hamle sayısı, zaman aşımı/illegal hamle/çökme
  sayıları, ortalama derinlik, nodes/saniye, açılış bazlı sonuçlar (en çok
  kaybedilen 10 açılış), oyun evresine göre kayıp dağılımı (olgu olarak),
  kullanılan sürüm ve karşılaştırılan sürüm.
- games.pgn.gz: tüm maçlar (açılış bilgisi ve sonuç etiketli).
- moves.jsonl.gz: her hamle için bir satır: maç no, hamle no, taraf, FEN,
  Zobrist hash, oynanan hamle, eval (cp), derinlik, düğüm sayısı, süre (ms).
- engine.log.gz: motor logu.
Ayrıca:
- data/index.csv: her koşu için tek satır (koşu adı, tarih, sürüm, rakip,
  maç sayısı, skor, Elo farkı, SPRT sonucu).
- data/tactics/: taktik test sonuçları, sürüm bazlı.
- data/positions/: pozisyon veri tabanı. Pozisyon başına Zobrist hash + FEN,
  görülme sayısı, W/D/L dağılımı, oynanan hamleler ve sayıları, ortalama eval.
  Parça parça .gz dosyalar; yeni koşular mevcut veriyi birleştirerek günceller.
- Formatlar herkesin açabileceği türden: JSON/CSV/PGN + gzip. İleride başkaları
  da kullanabilir.
- Şema sabit ve sürümlüdür (schema_version). Şemayı değiştirirsen sürümü artır
  ve AGENT_GUIDE.md'yi güncelle.
- Repo boyutu ~500 MB'a yaklaşırsa bana HABER VER; kaba veriyi (moves, games)
  Kaggle Dataset'e taşıma kararını ben veririm.
- analysis/ klasörüne kod ASLA yazmaz.

AGENT_GUIDE.md (ajan için) şunları içersin: repo yapısı, tüm dosya şemaları ve
alanların anlamı, "önce SUMMARY.md'yi oku, gerekirse ham veriye in" protokolü,
analysis/<koşu-adı>.md ve analysis/NEXT.md'nin beklenen formatı, ajanın
yapmaması gerekenler (kod/ data/ dosyalarını değiştirmemek).

================================================================
8. AŞAMALAR (sırayla, atlama yok)
================================================================
0. Altyapı: repo iskeleti, Kaggle notebook'u, GitHub push hattı (token
   Secrets'tan), veri şeması, AGENT_GUIDE.md, Stockfish kurulumu, sahte bir
   koşunun uçtan uca kaydı.
   BİTTİ KRİTERİ: notebook repoyu çekiyor, sahte koşuyu data/runs/ altına
   yazıp push ediyor; token hiçbir çıktıda görünmüyor.
1. Board + movegen + make/unmake + Zobrist + perft.
   BİTTİ KRİTERİ: yukarıdaki tüm perft referansları tam tutuyor.
2. UCI + match.py (paralel) + sprt.py + elo.py + summarize.py + record.py +
   pozisyon veri tabanı yazımı.
   BİTTİ KRİTERİ: bot Stockfish'e karşı hatasız tam maç oynuyor, illegal hamle
   ve çökme yok, tüm veri şemaya uygun kaydediliyor.
3. Materyal eval + negamax + alpha-beta.
   BİTTİ KRİTERİ: rastgele oyuncuyu 100/100 yeniyor.
4. PST (açılış/oyun sonu ayrımlı) + quiescence + iterative deepening + zaman
   yönetimi.
   BİTTİ KRİTERİ: SPRT ile önceki sürümden anlamlı üstün.
5. Move ordering (MVV-LVA) + transposition table.
   BİTTİ KRİTERİ: SPRT ile önceki sürümden üstün.
6. Null move, LMR, killer/history heuristics (her biri ayrı commit ve ayrı
   ölçüm).
   BİTTİ KRİTERİ: SPRT ile önceki sürümden üstün.
7. Eval geliştirme: geçer piyon, piyon yapısı (izole/çift/geri), şah güvenliği,
   mobilite, fil çifti, kale açık hat. Her özellik AYRI eklenir ve AYRI
   ölçülür.
   BİTTİ KRİTERİ: her özellik SPRT ile kanıtlı; fark yaratmayan özellik koda
   alınmaz.
8. Polyglot opening book okuyucusu (UCI option ile açılıp kapanır).
   BİTTİ KRİTERİ: kitapta oynuyor, kitap bitince çökmeden devam ediyor.
9. Profiling ve hız optimizasyonu (PyPy/Numba değerlendirmesi, nodes/sn
   raporu).
   BİTTİ KRİTERİ: nodes/sn ölçülmüş ve artmış, perft hâlâ doğru, SPRT'de
   gerileme yok.
10. position_lookup.py ve pozisyon veri tabanını tamamlama.
    BİTTİ KRİTERİ: bilinen bir pozisyon için doğru istatistik dönüyor.
11. Texel tuning, Syzygy; sonrasında NNUE benzeri eval.
    BİTTİ KRİTERİ: ölçümle kanıtlı.

================================================================
9. ÇALIŞMA KURALLARI
================================================================
- SADECE mevcut aşamayı yap. Aşama bitince DUR ve raporla: ne eklendi (sade
  Türkçe), hangi testler geçti (gerçek çıktıyla), sonraki adım ne. Ben
  onaylamadan sonraki aşamaya geçme.
- Her özellik için commit mesajı öner ve CHANGELOG.md'ye ekle.
- "İyileştirdim" demek yetmez: yeni sürümü ölçecek komutları/Kaggle
  hücrelerini bana ver. Kazanmıyorsa özelliği geri alırız.
- Emin olmadığın tasarım kararında varsayım yapma, kısa soru sor ve seçenek
  sun.
- Test etmediğin kodun çalıştığını iddia etme. Çalıştırabiliyorsan testleri
  kendin koş ve gerçek çıktıyı göster.
- Kaggle hücrelerini bana kopyala-yapıştır hazır, adım adım ver. Hata çıkarsa
  hata mesajını yapıştıracağım, düzeltmeyi sen yapacaksın.
- Güvenlik: token'ı asla görünür kılma, bana token'ı koda yazdırma.

Şimdi AŞAMA 0'dan başla. Bitince DUR ve raporla.
````
