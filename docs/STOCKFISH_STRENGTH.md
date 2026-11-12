# Güncel main: Stockfish 1320 / 1500, 500 ms

`codex/stockfish-500ms` dalından `notebooks/kaggle_stockfish_strength.ipynb`
dosyasını Kaggle'a içe alın. Internet ve Contents yazma yetkili GITHUB_TOKEN
secret'ı açık olsun. Run All çalıştırın; hiçbir maç yerel bilgisayarda başlamaz.

## Sabit test

- Acemi: en son onaylı main `38b0722b084552d8e94eb62e3558d447b641969c`.
  Ayrı temiz checkout; TTTwoContexts=true ve EvalPackedBase=true.
  NullMove/LMR/Killers açık, SEE ve diğer deneysel özellikler kapalı.
- Stockfish UCI_Elo=1320'ye **tek toplu 100 maç**, sonra UCI_Elo=1500'e
  **tek toplu 100 maç**. Her iki motora **500 ms/hamle**. Toplam 200 oyun.
  Onar oyunluk alt gruplar veya SPRT ile erken duruş yoktur.
- İki seviyede aynı seed=1 ile seçilen 50 farklı dengeli acemi-64 açılışı;
  her açılışta renk değişimi, seviye başına 50 beyaz / 50 siyah.
- Hash=16 MB, motor başına Threads=1, concurrency=2 (tek çekirdekte 1),
  OwnBook=false. 400 ply sınırı ve mevcut `claim_draw=True` hakem politikası
  değişmez. Zaman/geçersiz hamle/çökme iki taraf için de mağlubiyet sayılır.

Stockfish'in [resmî seçenekleri](https://official-stockfish.github.io/docs/stockfish-wiki/UCI-Protocol-and-Stockfish-Commands.html)
UCI_Elo alt sınırını 1320 verir; 1300 civarı bu yüzden 1320 ile sınanır.
Kurulu binary'nin ilan ettiği aralık hazırlıkta ayrıca doğrulanır. Desteklenmeyen
seviye sessizce değiştirilmez. UCI_LimitStrength=true iki seviye için zorunludur;
Skill Level ile sahte bir Elo eşlemesi kullanılmaz. Sürüm, binary SHA-256,
Elo aralığı ve ayarlar protokole yazılır. Acemi'nin Seed seçeneği Stockfish'in
zayıf hamle rastgeleliğini tekrar üretme garantisi vermez.

## Çalışma ve kayıtlar

Hazırlık ayrı Python sürecinde çalışır; eski Kaggle tools/engine importları
kullanılmaz. Kısa fixture testleri, UCI el sıkışması ve seçenek denetimi yapılır.
Hazırlıkta `go` gönderilmez. Yeni bir kod değişikliği denenmez; sabit main
sürümünün mevcut gücü ölçülür.

`data/strength/main-stockfish-500ms-100each-v1/`:
protocol.json, tek ortak açılış dosyası, setup.log, seviye başına başlangıç
işareti, çalışma logu ve altı ham dosyanın SHA-256 checkpoint'i, results.json
ve SUMMARY.md. Oyunlar/hamleler/motor logu ve ayrıntılı sonuçlar her seviye
için ayrı `data/runs/` kaydındadır; index ve pozisyon deposu normal kaydedilir.
İlk 100 maç bitince kayıtlar gönderilir; ikinci grup tamamlanınca tekrar gönderilir.

Tamamlanan bir grup hash ve protokol karşılaştırmasıyla atlanır; checkpoint
push öncesi kaybolmuşsa finalize edilmiş ham kayıt benimsenir. Tamamlanmış
grup tekrar oynanmaz. Yarım grupta eski oturumu durdurduktan sonra
RETRY_INCOMPLETE=True kullanılabilir. **Henüz finalize edilmemiş 100'lük grup
baştan oynanır**; oyun başına devam yoktur. Loglar korunur. İptal oyun içeren
veya ayarı uymayan ham kayıt başarılı 100 maç sayılmaz; otomatik yeniden
örneklenmez. Önce hatayı inceleyin, gerekiyorsa yeni SESSION_ID kullanın.
Kaynak/runtime/binary/açılış değişirse de yeni oturum gerekir.

Son notebook hücresi yalnız push tekrarlar; motor/maç başlatmaz. Sonuçlar iki
rakip seviyesi için ayrı W/D/L, puan, Elo farkı/güven aralığı ve teknik hata
sayılarıyla analiz edilir. İki grubun puanı tek bir Elo gibi birleştirilmez.
UCI_Elo 120s+1s koşulunda kalibre edilmiş bir sınırlama hedefidir; bu 500 ms
ölçümünden doğrudan FIDE, Chess.com veya Lichess puanı çıkartılmaz.
