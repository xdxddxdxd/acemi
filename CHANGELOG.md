# Değişiklik günlüğü

## 0.1.0 — Aşama 0

- Proje dizin yapısı ve veri şeması v1 eklendi.
- Sentetik koşu kaydı ve Kaggle çalıştırıcısı eklendi.
- Motor, hamle üretimi ve gerçek maç altyapısı sonraki aşamalara bırakıldı.

## 0.2.0 — Aşama 2 (UCI ve maç altyapısı)

- `engine/uci.py` ve `python -m engine`: UCI protokolü (uci, isready, ucinewgame, position, go, stop, quit, setoption: Hash/Threads/Seed). Arama ve eval henüz yoktu: `go` tohumlu rastgele yasal hamle döndürüyordu.
- `tools/uci_client.py`, `tools/match.py`, `tools/elo.py`, `tools/sprt.py`, `tools/record.py`, `tools/summarize.py`.
- Notebook: Stage 2 duman maçı.

## 0.3.0 — Aşama 3 (İlk arama)

- `engine/eval/classic.py`: sadece materyal değerlendirme (P=100, N=320, B=330, R=500, Q=900, K=20000), taraf sırası olan açısından.
- `engine/eval/base.py`: `evaluate(board) -> int` arayüzü.
- `engine/search.py`: negamax + alpha-beta. Mat skoru `±(100000 − ply)`. Beraberlik = 0. Varsayılan derinlik 3. `movetime` ile yumuşak erken durma.
- `engine/uci.py`: `go depth` / `go movetime` / `infinite`+`stop` aramayı çalıştırır; `info depth … score … nodes … time …` basar.
- `tools/random_uci.py`: Stage 3 geçiş testi için rastgele UCI rakip.
- Unit testler: eval, arama (asılı vezir, mat-1, pat), UCI cevapları.
- PST, quiescence, iterative deepening, TT yok (sonraki aşamalar).

## Aşama 1 — Tahta ve hamle üretimi

- 0x88 tahta, FEN, hamle üretimi, make/unmake, Zobrist ve temel beraberlik kuralları eklendi.
- Referans perft paketi ve Kaggle notebook'unda çalıştırma hücresi eklendi.
- Perft derinliği şimdilik 4 ile sınırlandı (Kaggle pratikliği için). Depth 5–6 sayıları yorumda saklanıyor; ileride tam doğrulama için açılacak.
