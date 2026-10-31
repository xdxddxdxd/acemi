# Acemi — mevcut oyun kayıtlarının Stockfish analizi

- Stockfish: **Stockfish 16 by the Stockfish developers (see AUTHORS file)**, sabit derinlik **10**, tek iş parçacığı.
- Kullanılan oyun: **2447** (benzersiz), bunların **2440** tanesi sonuç örnekleminde sayıldı; A/B **1973**, Stockfish **474**.
- Tekilleştirme: manifestte **13** yinelenen oyun atıldı; demo/AcemiRandom dışlandı.
- Pozisyon satırı: **254653**; Acemi hamlesi: **213326**; blunder (>150 cp): **23751**.
- Örnekleme: yok; tüm benzersiz oyunlar tam olarak tarandı (süre yetersiz kalsaydı raporda belirtilecekti).
- A/B ve Stockfish sonuçları ayrı raporlanır; asla birleştirilmedi.

> Sınırlama: `post_decision_games_excluded` oyun bazında işaretli değil. PGN'deki oyun sayısı ile sayılan oyun sayısı arasındaki fark (post-decision + eşleşmemiş oyunlar toplamı) kadar **game_no sırasındaki son oyun** sonuç örnekleminden çıkarıldı (vekil). Bu, gerçek karar anıyla birebir aynı olmayabilir; pozisyon istatistiklerinde tüm oyunlar kullanıldı.

## 10 maddelik özet

**İlk üç yatırım (sayıyla):** 1) oyun sonu dönüştürme/tablebase adayı: A/B kaçırılan 18, SF 0; 2) tekrar/contempt: A/B üstünken berabere 176, SF 6; 3) arama derinliği: A/B blunder 21955, SF 1796; pratik kitap adayı: A/B kötü hat 23, SF 7.
**Yatırım yapılmayacaklar (Elo için, sayıyla):** 1) kitap genişletme (Elo için): A/B kötü hat **23**, SF **7** (eşik ≥6 oyun); 2) Syzygy: ≤5 taşta kaçırılan A/B **18**, SF **0**; 3) ölçülemeyen mikro-eval terimleri: tema sayısı **10**.

1. **≤5 taşta kaçırılan sonuç:** A/B kazanç/beraberlik **18/0**, SF **0/0** (sonuç örneklemi).
2. **Üstünken üç tekrar/50 hamle beraberliği:** A/B **176**, SF **6** oyun.
3. **Açılış ilk 24 ply:** A/B ortalama cp loss **52.5**, >150 hata **2490**; SF **50.1**, **294**; açılışta biten kayıp A/B **0**, SF **1**.
4. **Kötü açılış hatları (≥6 oyun):** A/B **23**, SF **7**.
5. **Blunder temaları:** A/B vezir oyun sonu (11139), kale oyun sonu (6649), fil/at oyun sonu (1676); SF vezir oyun sonu (946), kale oyun sonu (513), pozisyonel (116).
6. **Syzygy:** yalnızca ≤5 taşta kaçırılan kazanç/beraberlik sayısı anlamlıysa düşünülmeli; tahmini etki B bölümünde.
7. **Kitap genişletme:** pratik oyun için evet, ölçülen Elo için hayır; açılışta kayıp 1, kötü hat 20. Test maçlarında kitap kapalı.
8. **Oyun sonu eval:** temalar ve eval/arama ayrımı C bölümünde; ölçülemeyen kısımlar açıkça yazıldı.
9. **Teşhis seti:** D bölümünde gerçek hata pozisyonları ve sentetik sonuçlar var; sentetik ölçüm yoksa 'ölçülemedi'.
10. **Yatırım yapılmayacaklar (Elo için):** kitap genişletme (testlerde kapalı), Syzygy (≤5 taş kaybı azsa) ve ölçülemeyen mikro-eval terimleri.


## A. Açılış kitabı

**Ölçülenler:** (kapsam: ilk motor hamlesinden 24. ply'e; zorunlu açılış plyleri Acemi'nin seçimi olmadığı için sayılmaz)
- AB: ilk 24 ply'de 29868 Acemi hamlesi; ortalama cp loss **52.5**, >150 cp hata **2490**.
- SF: ilk 24 ply'de 3615 Acemi hamlesi; ortalama cp loss **50.1**, >150 cp hata **294**.

**Kitap sonrası ilk 10 hamle (ply 13–22):**
- AB: 19721 hamle; ortalama cp loss **54.2**, >150 cp hata **1700**.
- SF: 2368 hamle; ortalama cp loss **49.9**, >150 cp hata **196**.

**Sistematik kötü açılış hatları (10 ply sonrası, SF ≤ −50 cp, en az 6 oyun):**
- **AB:**
  - e2e4 e7e6 d2d4 d7d5 b1c3 g8f6 — 32 oyun
  - e2e4 c7c5 g1f3 d7d6 d2d4 c5d4 f3d4 g8f6 — 30 oyun
  - d2d4 g8f6 c2c4 g7g6 b1c3 f8g7 — 29 oyun
  - e2e4 e7e5 b1c3 g8f6 f1c4 f6e4 c3e4 d7d5 c4d3 d5e4 — 24 oyun
  - e2e4 c7c5 g1f3 e7e6 d2d4 c5d4 f3d4 b8c6 b1c3 d8c7 — 20 oyun
  - e2e4 e7e5 g1f3 b8c6 f1b5 a7a6 — 19 oyun
  - c2c4 e7e5 b1c3 g8f6 g1f3 b8c6 — 19 oyun
  - d2d4 d7d5 c2c4 e7e6 b1c3 g8f6 — 19 oyun
  - e2e4 e7e6 d2d4 d7d5 b1d2 g8f6 e4e5 f6d7 f1d3 c7c5 — 18 oyun
  - e2e4 d7d5 e4d5 d8d5 b1c3 d5a5 d2d4 g8f6 g1f3 c7c6 — 18 oyun
  - e2e4 d7d6 d2d4 g8f6 b1c3 g7g6 g1f3 f8g7 f1e2 e8g8 — 18 oyun
  - d2d4 f7f5 g2g3 g8f6 f1g2 e7e6 g1f3 f8e7 e1g1 e8g8 — 16 oyun
  - e2e4 e7e6 d2d4 d7d5 b1c3 g8f6 c1g5 f8e7 e4e5 f6d7 — 15 oyun
  - d2d4 g8f6 c2c4 g7g6 b1c3 f8g7 e2e4 d7d6 g1f3 e8g8 — 14 oyun
  - e2e4 c7c5 g1f3 b8c6 d2d4 c5d4 f3d4 g8f6 b1c3 e7e5 — 13 oyun
- **SF:**
  - e2e4 e7e6 d2d4 d7d5 b1c3 g8f6 — 9 oyun
  - d2d4 d7d5 c2c4 e7e6 b1c3 g8f6 — 6 oyun
  - d2d4 g8f6 c2c4 g7g6 b1c3 f8g7 — 6 oyun
  - e2e4 c7c5 g1f3 e7e6 d2d4 c5d4 f3d4 b8c6 b1c3 d8c7 — 6 oyun
  - e2e4 e7e6 d2d4 d7d5 b1c3 g8f6 c1g5 f8e7 e4e5 f6d7 — 6 oyun
  - e2e4 e7e6 d2d4 d7d5 b1d2 g8f6 e4e5 f6d7 f1d3 c7c5 — 6 oyun
  - e2e4 d7d5 e4d5 d8d5 b1c3 d5a5 d2d4 g8f6 g1f3 c7c6 — 6 oyun

**Sonuç:** Kitap genişletme **pratik oyun için evet; ölçülen Elo için hayır**. Gerekçe: açılışta biten kayıp 1; ≥6 oyunluk kötü hat 20; ilk 24 ply ortalama cp loss 52.2. Test protokolünde kitap kapalı olduğu için bu yatırım Elo ölçümüne yansımaz.


## B. Syzygy / tablebase

- ≤5 taşa inen oyun: **403 / 2440 (16.5%)**.
- ≤6 taşa inen oyun: **573 / 2440 (23.5%)**.
- ≤7 taşa inen oyun: **734 / 2440 (30.1%)**.

**≤5 taşa inen oyunlarda Acemi sonuçları (sonuç örneklemi):**
- AB: 363 oyun; W/D/L = 127/121/115.
- SF: 40 oyun; W/D/L = 4/16/20.

- ≤5 taşta kaçırılan kazanç (etiket: kazanç iken berabere/kayıp): **18**.
- ≤5 taşta kaçırılan beraberlik (etiket: beraberlik iken kayıp): **0**.
- Etiket kaynağı (≤5 taşa inen oyunlar): Syzygy WDL **0**, Stockfish derinlik 10 **403**. Syzygy etiketinde ±1 (50 hamle kuralıyla beraberlik) beraberlik sayıldı.
  - syzygy: kaçırılan kazanç **0**, kaçırılan beraberlik **0**.
  - stockfish: kaçırılan kazanç **18**, kaçırılan beraberlik **0**.

**Oyunun bittiği taş sayısına göre kayıplar:**
- ≤5 taşta biten kayıp: **138**.
- ≤6 taşta biten kayıp: **198**.
- 6+ taşta biten kayıp: **562**.

**Tahmini Syzygy etkisi:** ≤5 taşta kaçırılan kazanç/beraberlik toplamı **18** oyun; Syzygy 3–5 taş kapsar. Bu bir **üst sınır tahminidir**: WDL etiketi DTZ'yi içermez (teorik kazanç pratikte dönüştürülemeyebilir), tabloda olmayan pozisyonlarda Stockfish etiketi kullanıldı ve dönüştürme hataları sonucu değiştirebilir. Kesin etki için ayrı maç gerekir.

**Kaçırılan kazanç/beraberlik temaları:**
- diğer oyun sonu: 7
- fil/at oyun sonu: 6
- kale oyun sonu: 5


## C. Oyun sonu eval paketi

**Blunder temaları (Acemi hamleleri, >150 cp; A/B+SF toplamı):**
- vezir oyun sonu: 12085 hamle, ortalama cp loss 641.3.
- kale oyun sonu: 7162 hamle, ortalama cp loss 552.4.
- fil/at oyun sonu: 1783 hamle, ortalama cp loss 1031.7.
- pozisyonel: 1313 hamle, ortalama cp loss 297.4.
- diğer oyun sonu: 862 hamle, ortalama cp loss 1205.8.
- taktik: 410 hamle, ortalama cp loss 289.8.
- KQK (mat dönüştürme): 65 hamle, ortalama cp loss 1890.6.
- KRK (mat dönüştürme): 40 hamle, ortalama cp loss 1778.8.
- KPK: 29 hamle, ortalama cp loss 850.3.
- KBNK (mat dönüştürme): 2 hamle, ortalama cp loss 196.0.

**Eval mi, arama mı?** Blunderlarda Acemi eval'i ile SF aynı taraf skoru >100 cp ayrışan: **15532** (eval hatası), ayrışmayan: **6569** (arama/derinlik), ölçülemeyen: **1650**. Acemi eval derinliği ~3; SF depth 10.

| tema | blunder | eval hatası | arama hatası | ort. eval farkı |
|---|---|---|---|---|
| vezir oyun sonu | 12085 | 7855 | 2938 | 867.7 |
| kale oyun sonu | 7162 | 4658 | 2374 | 735.2 |
| fil/at oyun sonu | 1783 | 1419 | 315 | 1838.7 |
| pozisyonel | 1313 | 520 | 683 | 143.4 |
| diğer oyun sonu | 862 | 701 | 112 | 2048.4 |
| taktik | 410 | 259 | 137 | 233.2 |
| KQK (mat dönüştürme) | 65 | 61 | 0 | 5898.2 |
| KRK (mat dönüştürme) | 40 | 28 | 10 | 5249.3 |
| KPK | 29 | 29 | 0 | 767.9 |
| KBNK (mat dönüştürme) | 2 | 2 | 0 | 224.0 |
**Depth-4 yeniden arama:** 29 / 50 pozisyonda aynı hata yapılmadı (ölçülen örnek).
Örnek tabakalı ve deterministik: tohum 20261031, oyun başına en fazla 2 pozisyon, havuz {'AB': 21955, 'SF': 1796}, örneklenen {'AB': 25, 'SF': 25}.

**Her tema için öneri:**
- vezir oyun sonu: Şah güvenliği ve vezir-piyon dönüştürme; eval terimi.
- kale oyun sonu: Kale arkada/önde kuralı + Lucena/Philidor teşhis seti.
- fil/at oyun sonu: Fil rengi/kötü fil ve mat dönüştürme alıştırmaları.
- pozisyonel: Eval terimi; önce SF etiketli pozisyonlarla doğrula.
- diğer oyun sonu: Şah aktivitesi ve piyon yarışı eval terimi.
- taktik: Arama derinliği/uzatma; eval değil.
- KQK (mat dönüştürme): Şah-piyon mat rutini; KQK teşhis pozisyonları.
- KRK (mat dönüştürme): Kale mat rutini; KRK teşhis pozisyonları.
- KPK: KPK bitbase veya kral muhalefeti kuralı (ucuz eval).
- KBNK (mat dönüştürme): Fil+at mat rutini; KBNK teşhis pozisyonları.


## D. Oyun sonu teşhis seti

`data/analysis/endgame_candidates.csv` için seçilen gerçek hata pozisyonları (her temadan en fazla 10):
- pozisyonel: 10 pozisyon
- kale oyun sonu: 10 pozisyon
- taktik: 10 pozisyon
- fil/at oyun sonu: 10 pozisyon
- vezir oyun sonu: 10 pozisyon
- diğer oyun sonu: 10 pozisyon
- KRK (mat dönüştürme): 10 pozisyon
- KQK (mat dönüştürme): 10 pozisyon
- KPK: 10 pozisyon
- KBNK (mat dönüştürme): 2 pozisyon

**Sentetik standart pozisyonlar (Acemi 500 ms):**

> KRPKR kategorisi SF-etiketli rastgele pozisyonlardır; Lucena/Philidor isimli standart FEN'ler ayrıca doğrulanmadı.
- KBBK: 10 başlangıç; başarı **3/10 (30.0%)**, ortalama ply 71.7.
- KBNK: 10 başlangıç; başarı **1/10 (10.0%)**, ortalama ply 76.7.
- KPK: 10 başlangıç; başarı **10/10 (100.0%)**, ortalama ply 25.5.
- KQK: 10 başlangıç; başarı **10/10 (100.0%)**, ortalama ply 31.8.
- KRK: 10 başlangıç; başarı **10/10 (100.0%)**, ortalama ply 37.8.
- KRPKR: 10 başlangıç; başarı **6/10 (60.0%)**, ortalama ply 73.6.


## Üç tekrar ve 50 hamle

- Üç tekrar/50 hamle ile biten oyun: **744 / 2447 (30.4%)**.
- AB: 675 oyun.
- SF: 69 oyun.
- Bunlarda Acemi SF'ye göre üstünken (final_sf_cp ≥ +200) berabere: **182**.
- Tekrar öncesi son Acemi hamlesi ≤30 cp kayıpla SF'nin farklı bir hamlesine izin veriyorsa 'kaçınılabilir' sayıldı; bu yaklaşık bir ölçüdür (son 10 hamlenin tamamı taranmadı).
- Kaçınılabilir tekrar (yaklaşık): **193**.

| oyun | tür | sonuç | bitiş | final SF |
|---|---|---|---|---|
| 20261028T064103Z_0.4.1_acemi-0.4.0_e23cad0#14 | AB | draw | threefold_repetition | 0 |
| 20261028T064103Z_0.4.1_acemi-0.4.0_e23cad0#27 | AB | draw | threefold_repetition | 518 |
| 20261028T064103Z_0.4.1_acemi-0.4.0_e23cad0#28 | AB | draw | threefold_repetition | 9994 |
| 20261028T064103Z_0.4.1_acemi-0.4.0_e23cad0#35 | AB | draw | threefold_repetition | -209 |
| 20261028T064103Z_0.4.1_acemi-0.4.0_e23cad0#36 | AB | draw | threefold_repetition | -123 |
| 20261028T064103Z_0.4.1_acemi-0.4.0_e23cad0#46 | AB | draw | threefold_repetition | 1750 |
| 20261028T064103Z_0.4.1_acemi-0.4.0_e23cad0#48 | AB | draw | threefold_repetition | -466 |
| 20261028T064103Z_0.4.1_acemi-0.4.0_e23cad0#6 | AB | draw | threefold_repetition | 948 |
| 20261028T064103Z_0.4.1_acemi-0.4.0_e23cad0#9 | AB | draw | threefold_repetition | 425 |
| 20261028T094439Z_0.4.2_acemi-0.4.1_03adad2#10 | AB | draw | threefold_repetition | -1641 |
| 20261028T094439Z_0.4.2_acemi-0.4.1_03adad2#104 | AB | draw | threefold_repetition | -332 |
| 20261028T094439Z_0.4.2_acemi-0.4.1_03adad2#111 | AB | draw | threefold_repetition | 453 |
| 20261028T094439Z_0.4.2_acemi-0.4.1_03adad2#14 | AB | draw | threefold_repetition | 62 |
| 20261028T094439Z_0.4.2_acemi-0.4.1_03adad2#24 | AB | draw | threefold_repetition | 9997 |
| 20261028T094439Z_0.4.2_acemi-0.4.1_03adad2#28 | AB | draw | threefold_repetition | -1147 |
| 20261028T094439Z_0.4.2_acemi-0.4.1_03adad2#29 | AB | draw | threefold_repetition | 9995 |
| 20261028T094439Z_0.4.2_acemi-0.4.1_03adad2#35 | AB | draw | threefold_repetition | -9999 |
| 20261028T094439Z_0.4.2_acemi-0.4.1_03adad2#39 | AB | draw | threefold_repetition | -2005 |
| 20261028T094439Z_0.4.2_acemi-0.4.1_03adad2#42 | AB | draw | threefold_repetition | 0 |
| 20261028T094439Z_0.4.2_acemi-0.4.1_03adad2#44 | AB | draw | threefold_repetition | -1673 |


## Veri kapsamı ve sözlük

| koşu | tür | oyun | post_decision |
|---|---|---|---|
| 20261027T161419Z_0.2.0_stockfish-16-uci-elo-1320_5920575 | SF | 4 | 0 |
| 20261028T051028Z_0.4.0_acemi-0.3.1_c62fc27 | AB | 17 | 0 |
| 20261028T064103Z_0.4.1_acemi-0.4.0_e23cad0 | AB | 54 | 0 |
| 20261028T064916Z_0.4.1_stockfish-16-uci-elo-1320_753d788 | SF | 20 | 0 |
| 20261028T094439Z_0.4.2_acemi-0.4.1_03adad2 | AB | 136 | 0 |
| 20261028T100022Z_0.4.2_stockfish-16-uci-elo-1320_79c9cb5 | SF | 20 | 0 |
| 20261028T101934Z_0.5.0_acemi-0.4.2_e985c10 | AB | 50 | 0 |
| 20261028T102745Z_0.5.0_stockfish-16-uci-elo-1320_d5e4024 | SF | 20 | 0 |
| 20261029T074834Z_0.6.0_acemi-0.5.0_acecedb | AB | 300 | 0 |
| 20261029T084703Z_0.6.0_stockfish-16-uci-elo-1320_071551d | SF | 60 | 0 |
| 20261029T090639Z_0.6.1_acemi-0.6.0_071152a | AB | 100 | 0 |
| 20261029T092851Z_0.6.1_stockfish-16-uci-elo-1320_f935add | SF | 50 | 0 |
| 20261030T042612Z_0.6.2_acemi-0.6.2-killers-false_10bcec0 | AB | 24 | 0 |
| 20261030T045117Z_0.6.3_acemi-0.6.3-pvs-false-nullmove-false_fcd1d64 | AB | 150 | 0 |
| 20261030T052840Z_0.6.3_acemi-0.6.3-pvs-true-nullmove-false_f84f517 | AB | 150 | 0 |
| 20261030T091540Z_0.6.4_acemi-0.6.3_78c4cb2 | AB | 87 | 2 |
| 20261030T093702Z_0.6.4_acemi-0.6.4_1997dd7 | AB | 74 | 2 |
| 20261030T104120Z_0.7.0_acemi-0.7.0-evalpassedpawns-false_df23248 | AB | 150 | 0 |
| 20261030T115210Z_0.7.1_acemi-0.7.1-evalpassedpawns-false-evalpawnstructure-false-evalbishoppair-false_a7a38c2 | AB | 150 | 0 |
| 20261030T124401Z_0.7.2_acemi-0.7.2-evalkingsafety-false_eb7558d | AB | 150 | 0 |
| 20261030T135123Z_0.7.3_acemi-0.7.3-checkextension-false_94aac84 | AB | 150 | 0 |
| 20261030T145056Z_0.7.4_acemi-0.7.4-checkextension-false-latemovepruning-false-nextiterationpct-150_26058e0 | AB | 244 | 2 |
| 20261030T155811Z_0.7.4_stockfish-16-uci-elo-1320_504003c | SF | 100 | 0 |
| 20261030T161545Z_0.7.4_stockfish-16-uci-elo-1500_1662e5e | SF | 100 | 0 |
| 20261030T171911Z_0.7.4_stockfish-16-uci-elo-1500_6f5dbee | SF | 100 | 0 |

- Koşu türleri: A/B = iki taraf da Acemi; SF = Acemi vs Stockfish. Karıştırılmadı.
- Demo ve AcemiRandom koşuları dışlandı; manifest `runs_total` ve `excluded_demo_other` alanlarında sayıları var.
- Faz tanımı: ply ≤ 20 açılış; piyon dışı materyal toplamı ≤ 26 oyun sonu; diğerleri orta oyun. SUMMARY'deki oyun-sonu tanımından pozisyona uyarlanmıştır.
- `cp_loss`: Acemi hamlesinde, SF depth 10 öncesi/sonrası beyaz bakışı skor farkı; SF en iyi hamlesi oynandıysa 0. >150 cp 'blunder'.
- `sf_cp`: beyaz bakışı; mat ±10000'e sınırlandırıldı. `acemi_eval_cp`: moves.jsonl'deki motor skoru (hamle sırasındaki taraf bakışı), `acemi_depth` onun derinliği.
- `in_result_sample`: PGN'deki oyun sayısı ile sayılan oyun sayısı farkına (post-decision + eşleşmemiş) göre son oyunların dışlanması (vekil). Pozisyon analizinde tüm oyunlar var.
- A/B'de iki taraf da Acemi olduğu için `is_acemi` iki tarafta da doğru; oyun sonucu `focus_color` (engine) bakışındandır. SF'de yalnızca Acemi tarafı.
- Sentetik sonuçlar için 'beklenen' etiket `synthetic_endgames.csv` içindeki `label_source` sütunundadır (Syzygy WDL varsa o, yoksa Stockfish derinliği).
- `tb_wdl`: beyaz bakışı Syzygy WDL (2 kazanç … -2 kayıp; ±1 = 50 hamle kuralıyla beraberlik); yalnızca ≤5 taşlı, rok hakkı olmayan, tablosu bulunan pozisyonlarda dolu. `label_source` bu etiketin kaynağıdır (`syzygy`/`stockfish`).
- İlk 10 ply zorunlu açılıştır ve Acemi'nin seçimi değildir; açılış ply sayısı oyunun ilk kayıtlı hamlesinden (`opening_plies`, en çok 20) türetilir, bu yüzden A bölümündeki "ilk 24 ply" aslında ilk motor hamlesinden 24. ply'e kadardır.
- `n<20` olan hücrelerde oranlar gürültülüdür; raporda sayılar verildiği için ayrıca işaretlenmedi.

Dosyalar: `parts/` (değişmez pozisyon/oyun/blunder parçaları) ve `parts.json`, `games.csv`, `blunders.csv`, `manifest.json`, `config.json`, `endgame_candidates.csv`, `synthetic_endgames.csv` (varsa), `recheck.csv` ve `recheck_meta.json` (varsa).
