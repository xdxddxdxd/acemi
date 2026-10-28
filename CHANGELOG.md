# Değişiklik günlüğü

## 0.5.0 — Aşama 5 (hamle sıralama + transposition table)

- `engine/search.py`: hamle sıralama (TT hamlesi, MVV-LVA ile alma hamleleri, terfiler, sakin hamleler için PST kazancı) negamax, quiescence ve kökte kullanılır.
- Transposition table: Zobrist anahtarlı sözlük; EXACT/LOWER/UPPER sınırları, derinlik öncelikli değiştirme, mat skoru ply düzeltmesi (`to_tt_score`/`from_tt_score`). Kapasite UCI `Hash` değerinden gelir (MB başına ~5000 kayıt); dolunca temizlenir.
- Arama kesilirse yedek hamle artık sıralamanın en iyisidir (önce alma hamleleri), listenin ilk rastgele hamlesi değil.
- `engine/uci.py`: kalıcı `Searcher`; TT hamleler arasında korunur, `ucinewgame` ile temizlenir, `setoption Hash` ile yeniden boyutlanır.
- `engine/eval/classic.py`: `pst_delta` eklendi.
- `tests/test_stage5.py` eklendi. Kod yazan tarafta test ÇALIŞTIRILMADI; Kaggle doğrulaması bekleniyor.
- Notebook: 0.5.0, 0.4.2'ye (commit `03adad2`) karşı 500 ms'de SPRT ve Stockfish UCI_Elo 1320 ölçümü.

## 0.4.2 — UCI ve ölçüm düzeltmeleri

- `engine/uci.py`: `go infinite` artık aramayı ayrı iş parçacığında hemen başlatır; `stop` yeni depth-3 arama açmak yerine çalışan aramayı durdurup sonucunu döndürür. `go nodes` sınırı uygulanır.
- `engine/search.py`: ilk iterasyonun 2× süre aşımı kaldırıldı. Süre kontrolü 64 düğümde bir, kök hamlelerde ve hamle listesi sonrasında yapılır; dış `stop_event` ve düğüm sınırı desteklenir.
- Arama hiçbir skor üretmeden kesilirse `cp 0` yerine skor `None` olur ve UCI skor alanı yayınlamaz; pozisyon veritabanına sahte eval girmez.
- `tools/match.py`: SPRT ve W/D/L yalnızca iki rengi de tamamlanmış açılış çiftlerini kullanır. Eksik çiftler ham PGN/hamle kaydında kalır, sonuçtan çıkarılır ve sayısı raporlanır.
- Bağımsız tahta aynası artık yalnızca taş dizilimi/sıra yerine tam FEN'i (rok, en passant ve sayaçlar dahil) karşılaştırır ve incremental Zobrist'i yeniden hesaplayarak doğrular.
- Notebook: 0.4.2, önceki 0.4.1 sürümüne (commit `4c1ef84`) karşı SPRT ve Stockfish UCI_Elo 1320 ölçümü yapar. Kod yazan tarafta test ÇALIŞTIRILMADI; Kaggle doğrulaması bekleniyor.

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

## 0.4.1 — Aşama 4 iyileştirmesi

0.4.0 kayıtlarında rastgele rakibe karşı hamlelerin %50'si derinlik 0 çıktı (200 ms'de 1. iterasyon bitmiyor, kod listedeki ilk hamleyi oynuyordu).

- 1. iterasyon süre bütçesinin 2 katına kadar uzayabilir (`FIRST_ITERATION_LIMIT`), sonraki iterasyonlar normal bütçede durur.
- 1. iterasyon o limitte de kesilirse, o ana kadar bulunan en iyi kök hamle kullanılır (hâlâ derinlik 0 olarak raporlanır, çünkü tamamlanan iterasyon yok).
- Yeni test: süre 0 iken yasal hamle ve en fazla derinlik 1.
- Notebook: 0.4.0'a (commit c62fc27) karşı SPRT (200 ms/hamle) ve Stockfish UCI_Elo 1320'ye karşı ilk Elo ölçümü.

## 0.4.0 — Aşama 4 (temel güç)

- `engine/eval/classic.py`: materyal + piece-square tabloları (Simplified Evaluation Function), açılış/oyun sonu harmanlı (taper). Piyon ve şahın ayrı oyun sonu tablosu var; oyun sonunda şah merkeze çekilir, rakip şah kenara itilir (kazanılmış oyun sonlarını bitirmek için).
- `engine/search.py`: quiescence (yakalamalar, en passant, vezir terfisi; şahtayken tüm kaçışlar), yaprakta tam hamle listesi üretilmiyor, iterasyon süresi tahmini (bitmeyecek iterasyon başlatılmıyor). Zaman limitli aramada derinlik üst sınırı 64, süre belirler.
- `engine/uci.py`: `wtime`/`btime`/`winc`/`binc`/`movestogo` ile hamle süresi (`time_budget_ms`: kalan/30 + artışın %75'i, en fazla kalanın yarısı, 30 ms pay).
- Hız: `engine/movegen.py` artık 128 kareyi taramak yerine taş listesinden üretiyor (sıralı, make/unmake geçmişinden bağımsız) ve `captures_only` seçeneği var. `Board.is_insufficient_material` piyon/kale/vezir varsa hemen çıkıyor. Perft sayıları değişmemeli (testler Kaggle'da doğrulayacak).
- Hakem/kayıt değişmedi (şema v1).
- Notebook: rastgele rakibe 20 maçlık duman testi + önceki sürüme (0.3.1, commit f2d8798) karşı SPRT (elo0=0, elo1=10, en fazla 200 maç, 500 ms/hamle).
- Yeni testler `tests/test_stage4.py`; `test_search.py` PST eval'e uyarlandı. Yazan tarafta ÇALIŞTIRILMADI.
- Hâlâ yok: hamle sıralama (MVV-LVA) ve transposition table (Aşama 5).

## 0.3.1 — Aşama 3 düzeltmeleri

Aşama 3'ün 100 maçlık rastgele-rakip koşusu (16/79/5, %55,5) geçiş kriterini (100/100) sağlamadı. Verideki iki hata düzeltildi:

- Süre dolunca arama yarım kalıyor, derinlik yine de 3 raporlanıyordu (hamlelerin %64'ü <300 düğümle oynanmıştı). Artık kökte iterative deepening var: süre dolarsa son TAMAMLANAN derinliğin hamlesi döner ve `info depth` gerçek tamamlanan derinliktir.
- Eşit skorlu hamlelerde hep ilk üretilen hamle seçildiği için motor ileri geri oynuyordu (79 beraberlik). Artık eşit en iyi kök hamleler arasında `Seed` opsiyonuyla tohumlanan RNG seçer; `ucinewgame` RNG'yi yeniden tohumlar (aynı seed = aynı oyun).
- Yeni testler: tamamlanan derinlik, süre limiti, seed'li eşitlik bozma.
- Not: Aşama 4'ün iterative deepening'inin yalnızca kök sürümü öne çekildi; PST, quiescence ve zaman yönetimi hâlâ Aşama 4'te. Hız (~1000 düğüm/sn) bu sürümde değişmedi.

## Aşama 1 — Tahta ve hamle üretimi

- 0x88 tahta, FEN, hamle üretimi, make/unmake, Zobrist ve temel beraberlik kuralları eklendi.
- Referans perft paketi ve Kaggle notebook'unda çalıştırma hücresi eklendi.
- Perft derinliği şimdilik 4 ile sınırlandı (Kaggle pratikliği için). Depth 5–6 sayıları yorumda saklanıyor; ileride tam doğrulama için açılacak.
