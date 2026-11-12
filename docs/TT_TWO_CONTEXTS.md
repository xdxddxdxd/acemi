# TT iki geçmiş deneyi

Dal `codex/tt-two-contexts`, notebook `notebooks/kaggle_tt_two_contexts.ipynb`.
Kaggle'a içe alın; Internet ve Contents yazma yetkili GITHUB_TOKEN secret'ını
açıp yeni oturumda Run All çalıştırın. Gerçek test, arama ve maçlar yalnız Kaggle'da.

## Değişiklik

12 Kasım 2026 kullanıcı kararıyla `TTTwoContexts` UCI motorunda varsayılan açıktır.
100 maç sonucu 40/25/35 (%52,5); bu tercih kanıtlanmış Elo artışı anlamına gelmez.
Araçların eski sabit referanslarını korumak için doğrudan `Searcher()` API'si
tek-context varsayılanını korur; yeni deneyler iki tarafa da açık ayarı belirtir.
UCI'de seçenek kapatılabilir. Açılınca aynı Zobrist konumu için en fazla
iki **tam geçmiş context'i** saklanır. Yarım hamle sayacı, bütün geri alınabilir
geçmiş, contempt ve gerektiğinde kök rengi aynen eşleşmelidir. Derinlik ve
pencere şartları gevşetilmez. Null-move alt ağacı yine skor okuyamaz/yazamaz.

Bir context güncellenirken daha derin aynı-context kaydı korunur. Üçüncü bir
context geldiğinde, iki eski kayıttan daha derini tutulur; eşit derinlikte en
son yazılan birincil kayıt tercih edilir. Yeni yazılan context birincil olur.
Kök hamle sıralaması varsa kendi tam context'inin ipucunu tercih eder.

İki kaydın toplamı aynı giriş kapasitesine sayılır: Hash=16 için her iki tarafta
80.000 giriş sınırı vardır; kapasite ikiye katlanmaz. Gerektiğinde mevcut tam
temizleme davranışı her iki sözlüğü birlikte temizler. Seçeneği açıp kapatmak,
Hash değiştirmek veya yeni oyun başlatmak her iki tabloyu temizler.
Python'daki gerçek bellek maliyeti giriş sayısının yanında ayrıca değerlendirilmelidir.

## Sabit ayarlar

- Aynı tam kaynak commit'i: aday TTTwoContexts=true, kontrol false.
- SEE iki tarafta kapalı; NextIterationPct=150, Contempt=0, kitap kapalı.
- Aynı beraberlik politikası (`claim_draw=True`), Hash 16, Threads 1.
- Maç aşaması: **100 ms/hamle, tek toplu 100 oyun**, 50 renk değiştirmeli
  açılış çifti, Seed 1, concurrency 2, 400 ply sınırı, SPRT kapalı.

## Maça geçiş kontrolleri

1. Tüm testler Kaggle'da çalışır. Yeni tablo birim testleri yanında mevcut
   tekrar/elli hamle regresyonları yeni seçenekle tekrar çalışır. Seçici eleme
   kapalıyken TT kapalı oracle skorlarıyla karşılaştırma da vardır.
2. Süre sınırı olmayan depth-3 / 10 pozisyonda kapalı seçenek, doğrulanmış
   `4068a04` ile skor/hamle/derinlik/düğüm açısından aynı olmalıdır.
   Adayın düğüm ve hamlesi seçici arama nedeniyle değişebilir; ayrıca kaydedilir.
3. Her politika için üç normal sabit derinlik ölçümü dönüşümlü sırada alınır:
   tek/çift, çift/tek, tek/çift. Her politikanın skor/hamle/düğüm sonuçları kendi
   tekrarlarında aynı olmalıdır. Ölçüm sayaçsız Searcher ile yapılır.
4. Önceki 100 kayıtlı oyunun 1,6,11,...,96 numaralı **20 kaydı** iki politika
   için tekrar incelenir. Bu yeni maç veya 10'ar oyunluk maç bölümü değildir.
   Her pozisyonda normal ve sayaçlı arama aynı düğüm bütçesinde sonuç/tahta/iki
   TT açısından eşleşmelidir. Geçmiş akışı ve per-game sıcak TT korunur.
5. İkinci kayıttan en az bir gerçek kesme gelmeli, aday sabit derinlikte daha
   fazla düğüm araştırmamalı ve aday medyan süresi kontrolden %10'dan fazla
   uzun olmamalıdır. Bunlar önceden tanımlı küçük maliyet/kullanım kontrolleridir;
   güç veya main'e alma kararı değildir. 3 geçiş süre belirsizliğini tamamen kaldırmaz.
6. Kontroller geçerse **tek 100 maç** başlar. Geçmezse yeni maç oynanmaz;
   bütün kontrollerin sonuçları ve gerekçeler GitHub'a gönderilir.

Kaynak girişler önceki TT teşhisinin hash ile doğrulanan sabit girdileridir.
Yeni engine ağacında eski davranışın eşdeğerliği ikinci aşamada kontrol edilir;
kayıtlı eski hamleyle aynı yeni hamle zorunlu değildir. Her politikanın normal
ve sayaçlı sonuçları kendi arasında eşit olmak zorundadır. Sayaçlı süreler
normal hız ölçümü olarak kullanılmaz.

## Kayıtlar ve tekrar çalıştırma

`data/ab/tt-two-contexts-100ms-100games-v1/` protokolü, doğruluk/benchmark
çıktılarını, `eligibility.json` gerekçelerini ve maç olursa checkpoint'i tutar.
`data/tt/<id>-replay-single/` ve `-replay-pair/` 20'şer kayıtlı oyun teşhisidir.
Bu klasörlerde ikinci kayıt kabul/derinlik/kesme, yeni slot ve context atma
sayaçları eklenir. Eski tek-context üzerine-yazma sayaçlarıyla isimlerin anlamını
karıştırmayın: yeni context yazılması her zaman eski context'in kaybı değildir.

Bitmiş testler/teşhis/maçlar hash ile doğrulanıp atlanır. Kesilmiş teşhiste önce
eski Kaggle oturumunu durdurup RETRY_INCOMPLETE açın. Değişmiş kaynak/girdi veya
başarısız doğruluk için yeni SESSION_ID kullanın. Son hücre yalnız yayınlamayı
tekrarlar. Mevcut ham kayıtlar, eski notebook'lar ve main değiştirilmez.
Deney protokolü açık/kapalı ayarını açıkça sabitler; UCI varsayılanından etkilenmez.
