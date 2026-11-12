# Acemi

Acemi, Python ile sıfırdan geliştirilen bir satranç motorudur. Öncelik sırası doğruluk, güç ve hızdır. Motor çekirdeği `engine/` altında yalnızca standart kütüphaneyle çalışır; `python-chess` yalnızca `tools/` ve testlerde kullanılır.

Quiescence için deneysel SEE sıralaması: [deney açıklaması](docs/QUIESCENCE_SEE.md).
`codex/quiescence-see` dalındaki `notebooks/kaggle_quiescence_see.ipynb`, önce
Kaggle doğruluk kontrollerini, sonra SEE açık/kapalı **100 ms, tek toplu 100 maç**
karşılaştırmasını çalıştırır. `QuiescenceSEE` varsayılan olarak kapalıdır.

Süre kullanımı için [ikinci deney](docs/TIME_POLICY.md): `codex/time-policy`
dalındaki `notebooks/kaggle_time_policy.ipynb`, SEE kapalıyken
`NextIterationPct=100 / 150` ayarlarını **100 ms, tek toplu 100 maç** ile
karşılaştırır. Mevcut motor varsayılanı 150 olarak kalır.

Üçüncü adım [TT kullanım teşhisi](docs/TT_DIAGNOSTICS.md): `codex/tt-diagnostics`
dalındaki `notebooks/kaggle_tt_diagnostics.ipynb`, kayıtlı 100 oyunun kontrol
pozisyonlarını aynı düğüm sınırında normal/sayaçlı aramayla inceler. Yeni maç
oynatmaz ve TT politikasını değiştirmez; bütün aramalar Kaggle'dadır.

Ölçüm sonrası [iki TT context adayı](docs/TT_TWO_CONTEXTS.md),
`codex/tt-two-contexts` dalındaki `notebooks/kaggle_tt_two_contexts.ipynb`
ile denenir. Doğruluk, kayıtlı pozisyon ve maliyet kontrolleri geçerse
**100 ms, tek toplu 100 maç** başlar. `TTTwoContexts` varsayılan kapalıdır.

[![CI](https://github.com/xdxddxdxd/acemi/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/xdxddxdxd/acemi/actions/workflows/ci.yml)

## English summary

Acemi is a pure-Python UCI chess engine (the engine core uses only the standard library). This is an **early-access** release: UCI-only, no GUI, roughly 1500 UCI_Elo against Stockfish's UCI_Elo scale. On the 64-line balanced set it scored 53.7% vs Stockfish 1500 (500 ms) and 62.0% vs Stockfish 1320 (250 ms); 400 validation games had no timeouts, illegal moves, or crashes. The 90-line Polyglot book is off by default (`OwnBook=true` to enable). Known limits: weak KBBK/KBNK conversion, no Syzygy, single-threaded, pure-Python speed. Licensed GPL-3.0.

> **Erken erişim:** UCI-only; GUI/paket yok. Davranış ve UCI seçenekleri değişebilir. Güç ~1500 UCI_Elo; kitap varsayılan kapalı. Bilinen sınırlar aşağıda.

## Durum

**Aşama 8 (0.8.2) tamam:** Polyglot açılış kitabı okuyucu ve 90 hatlık, 18 ply kitap. Motor araması 0.8.1 ile aynı; bu sürüm ağırlıklı olarak kitap verisi ve cilalama içerir.

- **Güç (`acemi-64`, kitap kapalı):** SF1500 500 ms'ye karşı 150 oyun **%53,7** (+25,5 Elo; %95 GA −30,0..+81,0); SF1320 250 ms'ye karşı 150 oyun **%62,0** (+85,0; GA +28,0..+142,1). SF1500 nokta tahmini ~1525 UCI_Elo; GA geniş ve 1500'ü içeriyor, SF1320'ye karşı üstünlük net.
- **Eski baseline (0.7.4):** `acemi-32` setiyle SF1500 500 ms'de 200 oyunun birleşiği %51,5 (+10,4; GA −37,6..+58,4), SF1320 250 ms'de 100 oyun %68,5 idi. Set değiştiği için yeni sonuçlarla birleştirilmedi.
- **Sağlamlık:** 400 oyunluk doğrulamada 0 timeout, 0 yasadışı hamle, 0 çökme, 0 tahta uyuşmazlığı. Kayıpların ~%44–46'sı oyun sonunda; `English` ailesi iki SF koşusunda da %50 altında (24 oyun, %43,8; örnek küçük).
- **Kitap:** 90 hat, 18 ply, 1117 pozisyon, 3124 hamle. Test/bench'te varsayılan kapalı; gerçek oyunda `OwnBook=true` ile açılır.
- **Bilinen sınırlar:** KBBK/KBNK dönüştürme zayıf (sentetik 3/10 ve 1/10); Syzygy yok; tek iş parçacığı (`Threads` en fazla 1); saf Python hızı. Eval mikro-terimleri ve Contempt ölçülebilir kazanç vermedi.

## Hızlı başlangıç

Motor UCI protokolüyle çalışır:

```powershell
python -m engine
```

Bir GUI'ye motor olarak eklerken komut `python -m engine`, çalışma dizini depo kökü olmalı. İlk klon yavaşsa `git clone --depth 1 https://github.com/xdxddxdxd/acemi.git` kullanın; `data/` yaklaşık 49 MB’tır.

Gerçek oyunda açılış kitabı:

```text
setoption name OwnBook value true
setoption name BookFile value openings/book.bin
```

`BookFile` göreli yolu çalışma dizinine göre çözülür; GUI farklı bir dizinden başlatıyorsa mutlak yol verin.

## UCI seçenekleri

Geliştirme dalındaki UCI düzeltmesi: süreli, derinlikli ve düğüm sınırlı aramalar
protokol döngüsünü bloke etmeden worker'da çalışır. `isready` arama sürerken
yanıtlanır; `stop` aynı aramanın sonucunu döndürür. Doğal bitiş veya tekrarlanan
`stop` ikinci bir `bestmove` üretmez. `position`, `setoption`, `ucinewgame`,
`quit` ve girişin kapanması önce eski worker'ı durdurur. Doğrudan Python'da
`UciSession()` kullanan kodun sonlu arama çağrıları önceki gibi sonucu bekler.
Tam protokol ve doğruluk doğrulaması Kaggle'da yapılır (`tests/test_uci_async.py`).

Geliştirme adımı 3'te TT skorları aynı 50 hamle sayacı ve son piyon hamlesi/alımından
sonraki aynı bilinen geçmişle sınırlıdır. Geçmiş farklıysa kayıt yalnızca hamle
sıralama ipucu olabilir; null-move alt ağaçları TT skoru okumaz/yazmaz. Tekrar için
kullanılan Zobrist anahtarı ve mevcut veri kayıtları değiştirilmez. Bu ihtiyatlı
eşleşme önbellek isabetlerini azaltabilir; hız etkisi Kaggle ölçümünü bekler.

Geliştirme adımı 4'te her UCI oturumu kendi değerlendirme ayarlarını taşır.
`Eval*`, arama sezgiselleri veya `Contempt` değişince eski TT skorları temizlenir;
aynı değer ve hatalı değerler geçerli önbelleği bozmaz. `Hash`, `Threads`, `Seed`,
`NextIterationPct` ve `Contempt` ilan edilen sınırlarla doğrulanır. Seed yeniden
verildiğinde rastgele akış önceki gibi sıfırlanır; Seed/süre politikası değişimi
tek başına TT'yi temizlemez. Doğrudan `evaluate(board)` ve `Searcher()` eski global
varsayılanı korur; açık ayar için `evaluate(board, flags)` ve `Searcher(eval_flags=flags)`
kullanılabilir. `Searcher.search()` çağrılar arasında değişen yapılandırmayı denetler.

| Seçenek | Varsayılan | Not |
|---|---:|---|
| `Hash` | 16 | MB; 1–4096 |
| `Threads` | 1 | En fazla 1 (tek iş parçacığı) |
| `Seed` | 1 | Eşit hamlelerde RNG tohumu |
| `NullMove`, `LMR`, `Killers` | true | Varsayılan arama özellikleri |
| `PVS`, `CheckExtension`, `LateMovePruning` | false | Deneysel; ölçülebilir kazanç yok |
| `OwnBook`, `BookFile` | false, `openings/book.bin` | Polyglot kitap |
| `EvalPassedPawns`, `EvalPawnStructure`, `EvalBishopPair`, `EvalKingSafety`, `EvalEndgameMate` | false | Deneysel eval terimleri |
| `NextIterationPct` | 150 | Iteratif derinleştirme bütçesi |
| `Contempt` | 0 | Beraberlik kontemptu; maçta kazanç yok |

## Açılış kitabı

- `openings/acemi-64.txt`: sabit 64 satırlık dengeli test seti. Ölçümlerde değiştirilmez.
- `openings/book_seeds.txt`: 64 test hattı + 12 ek Fransız dalı + 14 popüler hat = 90 hat.
- `openings/book.bin`: `tools/bookgen.py` ile üretilir.

```powershell
python -m pip install -r requirements-tools.txt
python -m tools.bookgen --stockfish C:\path\to\stockfish.exe `
  --openings openings/book_seeds.txt --branches 90 --max-plies 18 --depth 12 --cp-window 40
```

`tests/test_shipped_book.py` kitabın yasallığını, kökten erişilebilirliğini ve seed kapsamını doğrular. Kitaplı maçlarda `OwnBook` açıkça verilir; test protokolünde kitap kapalıdır. Açılış kitabı ve test setleri Stockfish (GPL-3.0) ile üretildi; Stockfish depoda paketlenmez.

## Test ve CI

```powershell
python -m pip install -r requirements-tools.txt
python -m unittest discover -s tests -v
python -m tools.bench --depth 3
```

GitHub Actions her push/PR'da Ubuntu ve Windows üzerinde tam test paketini ve bench duman testini çalıştırır: `.github/workflows/ci.yml`.

### Kaggle'da sabit referans (geliştirme adımı 1)

`notebooks/kaggle_runner.ipynb` sabit referans ve güncel kaynak için kayıt toplar.
İlk referans `db058b3` idi; güncel aşamanın sabit commit'i aşağıda belirtilir.
İki kaynak için test paketi ile aynı derinlikte benchmark ayrı ayrı çalışır.
Test özeti/günlükleri, benchmark, commit, motor ağacı ve ortam bilgisi yeni
`data/baselines/<oturum>/reference` ve `current` klasörlerine kaydedilip GitHub'a gönderilir.
Testler başarısız olduğunda da oluşan günlükler gönderilmeye çalışılır; önceki kayıtlar değiştirilmez.

Bu adımda aramanın değişmemesi beklenir; karşılaştırma konum kümesi, FEN, skor, derinlik,
düğüm ve en iyi hamleyi kontrol eder. Varsayılan `RUN_VALIDATION_MATCHES=False` ayarıyla
self-play/Stockfish maçları çalışmaz. Açılırsa kısa kontroller 10 self-play, 20 SF1500
ve 20 SF1320 oyunudur; bu sayılar Elo ölçümü için kullanılmaz. Ayrıntılar ve sonraki karşılaştırma komutları:
[docs/BASELINE.md](docs/BASELINE.md).

Sekiz geliştirme adımı Kaggle'da doğrulandı. Son aşamada 396 test geçti; motor
ağacı ve 10 konumun hamle/skor/derinlik/düğüm sonuçları 7b ile aynı kaldı.
Güncel notebook `main-validation` etiketiyle, doğrulanmış 8. adımın `2c3312b`
commit'ine karşı çalıştırır ve sonuçları `main` dalına gönderir;
hamle/skor/derinlik/düğüm eşitliği zorunludur (`REQUIRE_IDENTICAL_SEARCH=True`).
Normal benchmark hız karşılaştırması içindir; ek cProfile kaydı bu adımda varsayılan
kapalıdır. Önceki kayıtlar korunur, maçlar kapalıdır. Araçların modül yapısı ve
korunan import yolları: [docs/TOOLS.md](docs/TOOLS.md).

## Maç çalıştırma

Sekiz adım öncesi/sonrası **100 oyunluk Kaggle A/B** için
`codex/ab-100` dalındaki `notebooks/kaggle_ab_100.ipynb` dosyasını içe alın ve
Run All çalıştırın. Eski kaynak `db058b3`, yeni kaynak `4068a04` olarak sabittir.
50 açılış renk değiştirilerek oynanır; iki motora 100 ms/hamle, Hash 16 MB,
Threads 1 ve OwnBook=false uygulanır. 10 oyunluk bölümler GitHub'a gönderilir;
tamamlanan bölümler tekrar oynatılmaz. Skor yeni sürüm açısından okunur.
Bu notebook ek Stockfish maçı, benchmark veya tam test paketi başlatmaz.
Bkz. [docs/AB_100.md](docs/AB_100.md).

İkinci deney için aynı daldaki `notebooks/kaggle_ab_100_500ms.ipynb` dosyasını
kullanın: **500 ms/hamle, tek toplu koşuda 100 oyun**. İlk deneyden ayrı kaydedilir;
10'ar oyunluk bölümler kullanılmaz.

```powershell
# SF1320, 250 ms, 150 oyun
python -m tools.match --games 150 --movetime-ms 250 --uci-elo 1320 --openings openings/acemi-64.txt

# SF1500, 500 ms, 150 oyun
python -m tools.match --games 150 --movetime-ms 500 --uci-elo 1500 --openings openings/acemi-64.txt

# A/B motor seçeneği (iki taraf da Acemi)
python -m tools.match --games 150 --movetime-ms 500 `
  --opponent-cmd "python -u -m engine" `
  --engine-option Contempt=15 --opponent-option Contempt=0 `
  --openings openings/acemi-64.txt
```

`--sprt` erken durdurma, `--no-record` kayıtsız deneme, `--seed` RNG tohumu, `--concurrency` paralel oyun sayısıdır. Sonuçlar `data/runs/` altına yazılır. Kaggle runner kod yollarına dokunan son commit'i `--git-commit` ile her maça sabitler; araya giren `data:` commit'leri motor commit'i olarak kaydedilmez.

## Dizinler

- `engine/`: motor, arama ve değerlendirme
- `tests/`: doğruluk, arama, kitap ve analiz testleri
- `tools/`: maç, ölçüm, kitap üretimi ve analiz araçları
- `openings/`: test açılış seti, kitap seed'leri ve `book.bin`
- `notebooks/`: Kaggle test/analiz koşucuları
- `data/`: sürümlü koşu kayıtları ve analiz çıktıları
- `.github/workflows/ci.yml`: Ubuntu + Windows CI

## Kaggle hazırlığı

1. Public depo: [xdxddxdxd/acemi](https://github.com/xdxddxdxd/acemi), varsayılan dal `main`.
2. `notebooks/kaggle_runner.ipynb` test/maç, `notebooks/kaggle_analysis.ipynb` analiz içindir. Internet açık olsun.
3. **Add-ons → Secrets** içinde `GITHUB_TOKEN` (Contents: Read and write) tanımlayın.
4. Hücreleri sırayla çalıştırın. Token hiçbir dosyaya veya çıktıya yazılmaz.

## Veri ve analiz

[AGENT_GUIDE.md](AGENT_GUIDE.md). Her veri dosyası `schema_version` taşır. Gerçek sonuçlar ile sentetik demo kayıtlarını karıştırmayın.

Analiz önbelleği ve parçalar doğrulanmış ayar kimliğiyle devam eder; farklı
Stockfish/derinlik/Syzygy veya analiz kodu için yeni çıktı klasörü gerekir.
Eski sonuçları değiştirmeden devam etme kuralları: [docs/ANALYSIS.md](docs/ANALYSIS.md).

## Lisans

Bu proje **GPL-3.0** ile lisanslanmıştır; tam metin [LICENSE](LICENSE). `python-chess` yalnızca araçlar/testlerde kullanılır (GPL-3.0). Açılış kitabı ve test setleri Stockfish (GPL-3.0) ile üretildi; Stockfish depoda paketlenmez.
