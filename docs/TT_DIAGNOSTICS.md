# TT kullanım ölçümü

Dal `codex/tt-diagnostics`, notebook `notebooks/kaggle_tt_diagnostics.ipynb`.
Kaggle'a içe alın; Internet ve yazma yetkili GITHUB_TOKEN secret'ını açıp
Run All çalıştırın. Bilgisayarda gerçek arama/test/maç başlatılmaz.

## Bu aşama neyi ölçer?

TT politikası ve `engine/` dosyaları değiştirilmez. Sayaçlar yalnız
`tools/tt_stats.py` içindeki teşhis Searcher alt sınıfındadır; normal UCI motoru
bu sınıfı kullanmaz ve sayaç maliyeti ödemez. SEE kapalı, mevcut süre ayarı 150.

Yeni güç maçı oynatmak yerine son zaman politikası deneyindeki **100 kayıtlı
oyunun kontrol tarafındaki bütün arama pozisyonları** kullanılır. Eski ham
PGN/JSONL dosyaları hash ile doğrulanır, ayrı `inputs.json` hazırlanır.
Tahta başlangıçtan gerçek kayıtlı hamlelerle ilerletilir; hamle geçmişi ve sıcak
TT bir oyun içinde korunur. Her yeni oyun ayrı Searcher ve TT ile başlar.

Her pozisyonda normal ve sayaçlı Searcher ayrı fakat eşit başlangıç/RNG/TT
ile, o hamlede kaydedilen **düğüm sayısı üst sınırında** çalıştırılır. Hamle,
skor, tamamlanan/başlatılan derinlik, düğüm, mat, tahta restorasyonu ve TT içeriği
eşleşmelidir. Farkta kayıt tamamlanmaz, teşhis durur. Kayıtlı gerçek hamle
oynatılır; teşhisin önerdiği hamle veri dizisini değiştirmez.

Bu, eski 100 ms aramasının aynı duvar süresiyle tekrarı değildir. Sayaç ek yükü
zamanlı arama ağacını daraltmasın diye **duvar süresi sınırı kullanılmaz**.
Eski hamleyle aynı hamle veya skor zorunlu değildir; aynı iş sınırındaki normal
ve sayaçlı sonuçlar birbirine eşit olmalıdır. Bu veri Elo, güç veya gerçek hız
ölçümü olarak yorumlanmamalıdır. İki paralel kayıtlı oyun işlenir; 10'ar maçlık
bölümler veya yeni maç yoktur.

## Sayaçlar

- `probes`, `misses`, `hits`: yalnız iç düğümlerdeki `_probe` sorguları.
  Kökün doğrudan hamle ipucu okuması bu paydaya dahil değildir.
- `null_rejected`, `context_rejected`, `accepted`: bulunan kaydın neden skor
  için kullanılıp kullanılamadığı. Ret durumunda eski hamle ipucu korunur.
- `clock_mismatch`, `history_mismatch`, `same_clock_history_mismatch`,
  `other_context_mismatch`: ret alt nedenleri. Bir ret birden fazla nedenle
  işaretlenebilir; bunlar toplanıp toplam ret sayısı sanılmamalıdır.
- `too_shallow`, `sufficient_depth`, `bound_no_cutoff`: context'i kabul edilen
  kaydın derinlik ve pencere bakımından yeterliliği.
- `cutoff_exact`, `cutoff_lower`, `cutoff_upper`: üretim kodunun aynı pencere,
  derinlik ve mate-distance dönüşümüyle doğrudan skor döndürdüğü durumlar.
- `hints_available`: döndürülebilen hamle ipucu. İpucunun gerçekten sıralamada
  kullanıldığı veya kesme yaptığı anlamına gelmez.
- `stores`, `insertions`, `replacements_same_context`, `replacements_new_context`,
  `deeper_preserved`, `store_null`, `store_disabled`: yazma ve atlama sonuçları.
  Yazmalara kök iterasyonlarının kayıtları da dahildir.
- `capacity_clears`, `capacity_entries_discarded`: tablo dolunca tam temizleme.
  `explicit_clears` ayrı sayaçtır; kapasite olayıyla karıştırılmaz.
- `max_occupancy`, `max_stored_history`: en büyük giriş ve saklanan geçmiş
  uzunluğu. Toplamalarda maksimum alınır, toplanmaz. Hash MB -> kapasite dönüşümü
  mevcut motorun yaklaşık giriş sınırıdır; gerçek Python bellek ölçümü değildir.

Ölçüm her pozisyonda sıfırlanır fakat TT sıfırlanmaz. Oyun ve deney toplamları
ayrıca tutulur. Sayaç bölüşümleri her pozisyonda doğrulanır; bilinmeyen/null
oranlar sıfır başarı gibi sunulmaz.

## Kaggle akışı ve kayıtlar

1. `tt-usage-node-replay-v1` kimliğiyle kaynak dosyalar ve girdiler sabitlenir.
   Önceki `time-policy-100vs150-100ms-100games-v1` verisi yalnız okunur.
2. Tüm doğruluk testleri Kaggle'da geçer. Soğuk/sıcak TT için sayaçlı/normal
   arama eşdeğerliği de test edilir. Geçmezse kayıtlı pozisyon araması başlamaz.
3. 100 kayıtlı oyun incelenir; her kontrol pozisyonunda eşdeğerlik ve TT
   sayaçları kaydedilir. Normal ve sayaçlı arama birlikte çalıştığı için bu
   aşama önceki tek arama yükünden uzun sürebilir; yalnız Kaggle'da çalışır.
4. `data/tt/<id>/games/game_001.json` vb. tamamlanan oyun dosyaları değişmez.
   Hash'leri checkpoints.json içindedir. Başarılı kayıtlar tekrar hesaplanmaz.
   Eksik checkpoint'i olan tamamlanmış dosya kimliği doğrulanıp benimsenebilir.
5. `results.json` ve SUMMARY.md yalnız ölçümleri toplar. Test günlüğü,
   validation.json, kaynak kimliği ve hata varsa error.log korunur.
   Son notebook hücresi yalnız GitHub'a yayınlar; yeni arama başlatmaz.

Kesilmiş çalışmada `.running` kilidi varsa önce eski Kaggle oturumu tamamen
durdurulmalıdır; sonra RETRY_INCOMPLETE=True ile bitmemiş kayıtlar sürdürülebilir.
Başarısız doğruluk testini veya değişmiş kaynak/girdiyi sessizce tekrar denemek
yerine yeni SESSION_ID kullanın. Üretim motoru, main, eski maç kayıtları ve
beraberlik politikası değişmez. Notebook `analysis/` klasörüne yazmaz.
