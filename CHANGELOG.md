# Değişiklik günlüğü

## 0.6.4 — Hız (aynı arama, daha az iş)

Kod yazan tarafta ne test ne benchmark çalıştırıldı; doğrulama Kaggle'da. İlk Kaggle ölçümü (CPython, depth 4, 10 pozisyon): 8208 → 14419 nps, **1,76x**, skor/derinlik/düğüm sayısı/en iyi hamle birebir aynı.

- Python 3.9 uyumu: `slots=True` yalnızca Python 3.10+'da kullanılır (`DATACLASS_SLOTS`); Kaggle'ın apt ile kurduğu PyPy 3.9 motoru import edemiyordu. Notebook'ta PyPy sorunları artık notebook'u durdurmaz.

- `engine/board.py`: `is_square_attacked` aynı sonucu verir, ama her kare için `is_valid_square` çağırmak yerine 0x88 bit testi kullanır, taş sabitlerini bir kez hesaplar, kayan taşları `piece == bishop/rook/queen` ile kontrol eder.
- `engine/movegen.py`: `generate_legal_moves` artık her pseudo-legal hamleyi oynayıp geri almıyor. Yalnızca şah çekiliyorsa, şah hamlesi (rok dahil), bağlı (pinned) taş veya olası en passant varsa oynayıp test eder; diğer hamleler şahtaki olmayan taraf için zaten legaldir. Aynı hamleler aynı sırayla döner. Eski yöntem `generate_legal_moves_reference` olarak testler için korundu. İsteğe bağlı `known_in_check` parametresi aramanın zaten bildiği şah bilgisini kullanır.
- `engine/search.py`: negamax ve quiescence `known_in_check` geçirir.
- `tools/bench.py`: sabit derinlikte 10 pozisyonlu benchmark. İki sürüm (veya CPython/PyPy) karşılaştırılır; skor, derinlik, düğüm sayısı ve en iyi hamle birebir aynı olmak zorundadır, yalnızca süre farklı olabilir. `--engine-root` eski bir commit'i ölçer.
- `tests/test_movegen_equivalence.py`: yeni üretici = eski üretici (özel pozisyonlar: bağlı taşlar, en passant, çifte şah, rok, terfi; depth 2 ağaçları; rastgele oyunlar).
- Notebook: benchmark (önceki commit `fcd1d64` / yeni / PyPy), 100 oyunluk iki doğrulama maçı (yeni vs önceki, PyPy vs CPython).
- Beklenti (tahmin, ölçülmedi): CPython'da 1,4x-2x; PyPy'de çok daha fazla. Yapılmayanlar: `make_move` doğrulamalarının hafifletilmesi, üç tekrar taraması (kazancı küçük, risk/fayda düşük).


## 0.6.3 — PVS (varsayılan KAPALI, ölçüm bekliyor)

- `engine/search.py`: Principal Variation Search (`Searcher(pvs=...)`, UCI `PVS` seçeneği, varsayılan `false`). İlk hamle tam pencerede, sonrakiler sıfır pencerede aranır; alpha'yı aşıp beta'ya ulaşmayan hamle tam pencerede yeniden aranır (LMR ile birlikte: indirgenmiş deneme alpha'yı aşarsa önce tam derinlikte sıfır pencere, sonra gerekirse tam pencere). Kök arama değişmedi (kendi beraberlik penceresi var).
- Neden: null move `beta - alpha == 1` koşuluyla yalnızca sıfır pencereli düğümlerde çalışıyor, PVS yokken pratikte hiç tetiklenmiyordu (bir pozisyonda depth 5'te 0 çağrı, PVS ile 60). Bu yüzden 0.6.0'ın null move'u fiilen ölçülmemişti.
- Doğrulama: null move ve LMR kapalıyken PVS, alpha-beta ile aynı skoru verir (7 pozisyon, depth 2-4; yeniden arama koşulu bozulursa test başarısız olur — mutasyonla denendi). Düğüm sayısı pozisyona göre azalıyor ya da artıyor; kazanç ancak maçla ölçülür.
- `tests/test_pvs.py`: eşdeğerlik, null move'un PVS ile devreye girmesi, yalnızca piyon+şah pozisyonunda null yok, UCI seçeneği.
- Notebook: deney A (`PVS=true NullMove=false` / `PVS=false NullMove=false`) ve deney B (`PVS=true NullMove=true` / `PVS=true NullMove=false`), 150 oyun sınırı, 500 ms, 32 açılış, SPRT 0/20. Sonuçlara göre varsayılanlar değiştirilecek; kazanmayan özellik geri alınır (PLAN kuralı).

## 0.6.2 — Ölçüm altyapısı onarımı (motor gücü değişmedi)

Harici bir inceleme raporunun bulguları tek tek koda karşı doğrulandı; doğrulananlar düzeltildi, doğrulanmayan veya zarar verecek olanlar bilerek yapılmadı.

- `tools/sprt.py`: LLR artık her hipotez için beraberlik olasılığını en olabilir seçen trinomial genelleştirilmiş SPRT. Eski formül gözlenen varyansa bölüyordu ve uç skorlarda şişiyordu (16-0-0: 3.34, doğrusu 0.45; 42-9-3: 3.28, doğrusu 1.32). Smoothing yok. Sonuç: tek tarafa çok kayan kısa koşular artık "kabul" edilmez; büyük kazançlar için `--elo1 30` gibi daha yüksek bir H1 kullanın. 0.4.0, 0.4.1 ve 0.5.0 için kayıtlı `accept_h1` kararları eski formülün ürünüdür, `data/` değişmedi.
- `tools/match.py`, `tools/pairing.py`: SPRT kararı verildiği andaki oyun örneği dondurulur; karardan sonra biten oyunlar PGN/hamle kayıtlarında kalır ama sonuçtan çıkarılır (`post_decision_games_excluded`). Böylece kayıtlı W/D/L, LLR ve karar aynı örneği anlatır.
- `engine/search.py`, `engine/board.py`: 100. yarım hamlede mat artık beraberlik değil mat sayılır (negamax, quiescence, `is_draw`). Yeni testler eski kodda başarısız, yenisinde geçer.
- Telemetri: skorsuz `info` satırlarından depth/nodes/time kaydedilir; motorun kendi `info time` değeri `search_time_ms`, en derin başlanan iterasyon `attempted_depth` olarak kaydedilir (`SearchResult.depth` hâlâ son tamamlanan iterasyondur); `results.json` bitiş türlerini, skorsuz hamle sayısını ve `nodes_per_second_search` değerini içerir; `meta` CPU modelini ve çalıştırılan komutu içerir.
- `tools/elo.py`: güven aralığı Wilson skor aralığı; yanlış "her zaman muhafazakâr" iddiası kaldırıldı.
- A/B altyapısı: motor `NullMove`, `LMR`, `Killers` (check) ve `NextIterationPct` (spin, varsayılan 150) UCI seçeneklerini sunar; `tools.match` `--engine-option NAME=VALUE` ve `--opponent-option NAME=VALUE` alır (tekrarlanabilir; motorun tanımlamadığı seçenek kurulumu durdurur). Seçenekler `meta.json` ve `SUMMARY.md`'de görünür. Varsayılan davranış değişmedi.
- `openings/acemi-32.txt`: 32 satırlık açılış seti (`--openings openings/acemi-32.txt`). Denge yalnızca motorun kendi sığ aramasıyla kabaca kontrol edildi; Stockfish ±100 cp filtresi henüz uygulanmadı.
- Notebook: `checkout_commit` eski sürüm dizini varsa bile `fetch` + `checkout` yapar ve HEAD'i doğrular; ana hücre 0.6.2 ölçüm duman testi (24 oyun, Killers açık/kapalı, SPRT 0/20).
- Testler: `test_stats` (SPRT/Wilson referansları), `test_pairing`, `test_telemetry`, `test_ab_options`, 50 hamle/mat testleri. Bu ortamda tam paket çalıştırıldı (aşağıdaki commit'te sonuç); Kaggle doğrulaması bekleniyor.
- Bilerek yapılmayanlar: `grace_ms` düşürme (paralel gecikmede haksız kayıp riski), qsearch pat tespiti (hız maliyeti), TT/null+tekrar teorik riskleri, perft d5/6, tarihsel `data/` düzeltmeleri.

## 0.6.1 — Süre kullanımı düzeltmesi

- 0.6.0 SPRT verisi (300 maç): motorlar 500 ms bütçenin yalnızca ~%70'ini kullanıyordu (hamle başına ~347 ms); `NEXT_ITERATION_FACTOR = 3` yeni iterasyonu çok erken engelliyordu.
- `engine/search.py`: faktör 3.0 → 1.5. Yarım kalan iterasyon artık atılmıyor: en az bir kök hamle aranmışsa, o iterasyonun o ana kadarki en iyi kök hamlesi kullanılır (önceki en iyi hamle önce aranır, onu geçen hamle yeni derinlikte tam aranmış demektir). `SearchResult.depth` hâlâ yalnızca tamamlanan son iterasyonu bildirir.
- `tests/test_stage6.py`: yarım iterasyon testleri (sahte kök arama ile).
- Notebook: 0.6.1, 0.6.0'a (commit `acecedb`) karşı 500 ms'de SPRT (300 maç sınırı); Stockfish ölçümü 60 oyun. Kod yazan tarafta test ÇALIŞTIRILMADI.

## 0.6.0 — Aşama 6 (ileri budama ve sıralama sezgileri)

- `engine/search.py`: null-move pruning (PV olmayan düğümler, şahta değil, yalnızca piyon+şah değilken, art arda iki kez değil; derinlik ≥3, R=2).
- Late move reductions: ilk 3 hamleden sonraki sakin hamleler (alma/terfi/şah veren değil) bir ply az aranır, alpha'yı geçerse tam derinlikte yeniden aranır.
- Killer hamleler (ply başına 2) ve history tablosu (derinlik² ile artar, sıralamada 400 ile sınırlı) sakin hamle sıralamasını iyileştirir. Her arama başında sıfırlanır.
- Her sezgi `Searcher(null_move=, lmr=, killers=)` ile kapatılabilir (test ve hata ayıklama için).
- `engine/board.py`: `make_null_move` / `unmake_null_move` (ep, halfmove, Zobrist ve tekrar geçmişi tutarlı).
- Aspiration window bu sürümde YOK (kök beraberlik pencerelemesiyle çakışmaması için ertelendi).
- `tests/test_stage6.py` eklendi. Kod yazan tarafta test ÇALIŞTIRILMADI; Kaggle doğrulaması bekleniyor.
- Notebook: 0.6.0, 0.5.0'a (commit `e985c10`) karşı 500 ms'de SPRT; Stockfish UCI_Elo 1320 ölçümü 60 oyuna çıkarıldı.

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
