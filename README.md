# Acemi

Acemi, Python ile sıfırdan geliştirilen bir satranç motorudur. Öncelik sırası doğruluk, güç ve hızdır. Motor çekirdeği `engine/` altında yalnızca standart kütüphaneyle çalışır; `python-chess` yalnızca `tools/` ve testlerde kullanılır.

[![CI](https://github.com/xdxddxdxd/acemi/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/xdxddxdxd/acemi/actions/workflows/ci.yml)

## Durum

**Aşama 8 (0.8.2) tamam:** Polyglot açılış kitabı okuyucu ve 90 hatlık, 18 ply kitap. Motor araması 0.8.1 ile aynı; bu sürüm ağırlıklı olarak kitap verisi ve cilalama içerir.

- **Güç:** Kayıtlı ölçümlerde SF1500 500 ms'ye karşı 200 oyunun birleşiği %51,5 (+10,4 Elo; %95 GA −37,6..+58,4), yaklaşık **1510 UCI_Elo**. SF1320 250 ms'ye karşı %68,5. Ölçümlerde kitap kapalı ve `openings/acemi-64.txt` kullanıldı.
- **Kitap:** 90 hat, 18 ply, 1117 pozisyon, 3124 hamle. Test/bench'te varsayılan kapalı; gerçek oyunda `OwnBook=true` ile açılır.
- **Bilinen sınırlar:** KBBK/KBNK dönüştürme zayıf (sentetik 3/10 ve 1/10); Syzygy yok; tek iş parçacığı (`Threads` en fazla 1); saf Python hızı. Eval mikro-terimleri ve Contempt ölçülebilir kazanç vermedi.

## Hızlı başlangıç

Motor UCI protokolüyle çalışır:

```powershell
python -m engine
```

Bir GUI'ye motor olarak eklerken komut `python -m engine`, çalışma dizini depo kökü olmalı.

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

`tests/test_shipped_book.py` kitabın yasallığını, kökten erişilebilirliğini ve seed kapsamını doğrular. Kitaplı maçlarda `OwnBook` açıkça verilir; test protokolünde kitap kapalıdır.

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

`--sprt` erken durdurma, `--no-record` kayıtsız deneme, `--seed` RNG tohumu, `--concurrency` paralel oyun sayısıdır. Sonuçlar `data/runs/` altına yazılır.

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
