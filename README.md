# Acemi

Acemi, Python ile sıfırdan geliştirilen bir satranç motorudur. Öncelik sırası doğruluk, güç ve hızdır. Motor çekirdeği `engine/` altında yalnızca standart kütüphaneyle çalışır; `python-chess` yalnızca `tools/` ve testlerde kullanılır.

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

## Maç çalıştırma

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

## Lisans

Bu proje **GPL-3.0** ile lisanslanmıştır; tam metin [LICENSE](LICENSE). `python-chess` yalnızca araçlar/testlerde kullanılır (GPL-3.0). Açılış kitabı ve test setleri Stockfish (GPL-3.0) ile üretildi; Stockfish depoda paketlenmez.
