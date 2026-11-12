# Kayıtlı erken kayıpların pozisyon teşhisi

`codex/tactical-diagnostics` dalından `notebooks/kaggle_tactical_diagnostics.ipynb`
dosyasını Kaggle'a içe alın. Internet ve Contents yazma yetkili GITHUB_TOKEN
secret'ı açıkken Run All çalıştırın. Yeni maç oynanmaz; bütün gerçek aramalar
Kaggle'dadır. Kod veya motor politikası bu teşhisle değiştirilmez.

## Sabit girdiler

Kaynak `packed-eval-100ms-100games-v1` deneyinin tamamlanmış 100 oyunudur.
Ham dosyaların checkpoint özetleri, kaynak protokolü, PGN ve hareket kaydındaki
FEN/hamleler karşılaştırılır. Sonuç gruplarında en kısa oyunlar, eşitlikte
oyun numarası seçilir: dört kayıp (19,55,77,76), iki galibiyet (20,56) ve
iki beraberlik (96,37). Bunlar amaçlı karşılaştırma kayıtlarıdır; genel oyun
gücünü temsil eden rastgele örneklem veya istatistiksel kontrol grubu değildir.

Kayıplarda bütün kayıtlı aday hamleleri incelenir; oyunların 80 ply içinde
bitmesi şarttır. Diğerlerinde ilk sekiz aday hamlesi alınır. Her pozisyonun
başlangıç FEN'i ve o ana kadarki **bütün hamleleri** saklanır. Açılıştaki
zorlanmış hamleler adayın seçimi sayılmaz. Girdiler hazırlıkta dondurulur.

Acemi referansı `38b0722b084552d8e94eb62e3558d447b641969c` main commit'idir.
TTTwoContexts ve EvalPackedBase açık, SEE kapalı, NextIterationPct=150,
kitap kapalı, Hash=16, Threads=1, Contempt=0, Seed=1.

## Ölçüm

1. Stockfish'in bütün yasal hamlelerle araması ve yalnız **kaydedilmiş hamleye**
   izin verilen root araması alınır. İstenen derinlikler 12 ve 18, her aramada
   düğüm bütçesi 100.000. Gerçek ulaşılan depth/nodes ayrı saklanır.
2. Aynı geçmişli konumu Acemi iki politikayla inceler: normal ve yalnız
   NullMove+LMR kapalı. Her biri 12.000 düğüm / en fazla depth=8 kullanır.
   Gerçek tamamlanan derinlik kaydedilir; daha derine ulaşma garantisi yoktur.
3. Acemi'nin seçtiği hamleler de ikinci Stockfish bütçesiyle zorlanmış root
   aramasında değerlendirilir. Aynı hamleye ait sonuç tekrar kullanılır.

Her probda yeni oyun kimliğiyle temiz TT kullanılır. Tam hamle geçmişi
korunur; gerçek maçın sıcak TT'si ve ilerlemiş RNG durumu yeniden kurulmaz.
Kaydedilmiş 100 ms hamlesi ve arama bilgisi esas alınır; yeni süreli 100 ms
araması yapılmaz. Bu, sabit pozisyon teşhisidir; bir maç tekrarı değildir.

Skorların tamamı pozisyonda hamle sırası olan tarafın bakışındandır.
Mat skorları ayrı tutulur, sahte centipawn değerlerine dönüştürülmez.
Yalnız iki sayısal cp skoru da alt/üst sınır işareti taşımıyorsa fark alınır;
negatif fark sıfıra sınırlanır. Mat ve cp etiketlerinin kesinliği sınırlı arama
bütçesine bağlıdır. “İlk kaybettiren hamle” veya eleme hatası otomatik ilan edilmez.
Seçici elemeler kapalı arama aynı düğüm bütçesinde daha az derinlik bitirebilir;
iki sonucun farklılığı tek başına bir pruning hatası kanıtı değildir.

## Kayıt, kesilme ve devam

`data/tactics/tactical-losses-v1/`: protocol.json, inputs.json,
runtime.json, pozisyon başına JSON, checkpoints.json, sonuç ve SUMMARY.md.
Pozisyonlar tamamlandıkça ayrı dosya ve SHA-256 checkpoint'i yazılır.
Tamamlanan konumlar değiştirilmez; yetim dosya doğrulanarak checkpoint'e alınır.
Tamamı bittiyse tekrar çalıştırmak motor başlatmaz. Hatalar ayrı tarihli
error-*.log dosyalarına kaydedilir. Notebook son hücresi yalnız push tekrarlar.

Kesintide önce eski Kaggle oturumunu durdurun, sonra RETRY_INCOMPLETE=True
ile devam edin. Kaynak kod/girdi, main commit'i, Python/chess sürümü veya
Stockfish binary'si değişirse yeni SESSION_ID kullanın. Stockfish paket kurulumu
ve sabit engine checkout'u hazırlık hücresindedir; kernel'daki eski tools/engine
importları kullanılmaz. Sonuçlar ham gözlemdir; analiz ve sonraki kod değişikliği
ayrı yapılır. Bu ölçümden Elo veya güç kararı çıkartılmaz.
