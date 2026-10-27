# Değişiklik günlüğü

## 0.1.0 — Aşama 0

- Proje dizin yapısı ve veri şeması v1 eklendi.
- Sentetik koşu kaydı ve Kaggle çalıştırıcısı eklendi.
- Motor, hamle üretimi ve gerçek maç altyapısı sonraki aşamalara bırakıldı.

## 0.2.0 — Aşama 2 (UCI ve maç altyapısı)

- `engine/uci.py` ve `python -m engine`: UCI protokolü (uci, isready, ucinewgame, position, go, stop, quit, setoption: Hash/Threads/Seed). Arama ve eval henüz yok: `go`, tohumlu rastgele yasal hamle döndüren yer tutucudur. Güç ölçümü değildir.
- `tools/uci_client.py`: UCI istemcisi; zaman aşımı, çökme ve kurulum hatasını ayrı ayırır.
- `tools/match.py`: paralel maç yöneticisi (renk eşlenmiş açılış çiftleri, python-chess hakem, SPRT ile erken durdurma, Stockfish `UCI_LimitStrength`/`UCI_Elo`).
- `tools/elo.py`, `tools/sprt.py`: Elo farkı + güven aralığı ve SPRT (GSPRT yaklaşımı).
- `tools/record.py`, `tools/summarize.py`: şema v1 kaydı, `index.csv`, pozisyon veritabanı birleştirme ve olgusal SUMMARY.md.
- Notebook: sahte demo hücresi yerine küçük Stage 2 duman maçı.
- Bu sürümün testleri yazıldı ama yazan tarafta ÇALIŞTIRILMADI; Kaggle'da ilk koşuda doğrulanacak.

## Aşama 1 — Tahta ve hamle üretimi

- 0x88 tahta, FEN, hamle üretimi, make/unmake, Zobrist ve temel beraberlik kuralları eklendi.
- Referans perft paketi ve Kaggle notebook'unda çalıştırma hücresi eklendi.
- Perft derinliği şimdilik 4 ile sınırlandı (Kaggle pratikliği için). Depth 5–6 sayıları yorumda saklanıyor; ileride tam doğrulama için açılacak.
