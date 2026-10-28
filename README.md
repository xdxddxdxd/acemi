# Acemi

Acemi, Python ile sıfırdan geliştirilen bir satranç motorudur. Öncelik sırası doğruluk, güç ve hızdır. Motor çekirdeği `engine/` altında standart kütüphane ile yazılır; `python-chess` yalnızca `tools/` içindeki araçlarda kullanılabilir.

## Aşama durumu

**Aşama 5 (0.5.0):** Hamle sıralama (MVV-LVA, TT hamlesi, PST) ve transposition table (Hash seçeneği, `ucinewgame`'de temizlenir). Aşama 4 özellikleri (PST eval, quiescence, iterative deepening, saat yönetimi) korunur. Null move/LMR yok (Aşama 6).

**Aşama 3 (0.3.0):** materyal eval + negamax/alpha-beta. Varsayılan en fazla derinlik 3 (kökte iterative deepening; süre dolarsa son tamamlanan derinlik döner ve `info depth` o derinliktir). Eşit hamleler `Seed` ile tohumlanan RNG ile seçilir. `go depth` / `go movetime` desteklenir. PST, quiescence ve iterative deepening henüz yok.

Geçiş kriteri (plan): rastgele UCI rakibi 100/100 yenmek. 0.3.1'in kayıtlı 100 maçlık sonucu 91 galibiyet, 9 beraberlik, 0 mağlubiyet (%95,5) olduğundan bu kriter henüz karşılanmamıştır. Notebook kısa duman maçı oynatır; tam 100’lük koşu ayrıca çalıştırılabilir.

## Dizinler

- `engine/`: satranç motoru, arama ve değerlendirme
- `tests/`: doğruluk ve arama testleri
- `tools/`: maç, ölçüm, rastgele UCI rakip ve veri kayıt araçları
- `notebooks/kaggle_runner.ipynb`: Kaggle’da test + duman maçı + GitHub push
- `data/`: sürümlü test verileri ve koşu indeksi
- `analysis/`: yalnızca analiz ajanının raporları

## Yerel test

```powershell
python -m unittest discover -v
```

## Maç çalıştırma

```powershell
python -m pip install -r requirements-tools.txt

# Stockfish’e karşı
python -m tools.match --games 4 --movetime-ms 300 --uci-elo 1320

# Rastgele rakibe karşı (Stage 3 geçiş testi)
python -m tools.match --games 100 --movetime-ms 200 --opponent-cmd "python -u tools/random_uci.py"
```

`--sprt` ile SPRT erken durdurma, `--openings dosya.epd` ile kendi açılış seti, `--no-record` ile yazmadan deneme yapılır.

## Kaggle hazırlığı

1. Public depo: [xdxddxdxd/acemi](https://github.com/xdxddxdxd/acemi). Varsayılan dal `main`.
2. Kaggle’da `notebooks/kaggle_runner.ipynb` dosyasının güncel sürümünü açın. Internet açık olsun.
3. **Add-ons → Secrets** içinde `GITHUB_TOKEN` (Contents: Read and write).
4. Notebook hücrelerini sırayla çalıştırın.

Token hiçbir dosyaya veya hücre çıktısına yazılmaz.

## Araç bağımlılığı

`python-chess` yalnızca araçlar içindir. `python -m pip install -r requirements-tools.txt`

## Veri ve analiz

[AGENT_GUIDE.md](AGENT_GUIDE.md). Her veri dosyası `schema_version` taşır. Gerçek sonuçlar ile sentetik demo kayıtlarını karıştırmayın.
