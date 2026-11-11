# Quiescence SEE deneyi

Dal: `codex/quiescence-see`. Kaggle'a `notebooks/kaggle_quiescence_see.ipynb`
dosyasını içe alın; Internet ve yazma yetkili `GITHUB_TOKEN` secret'ını açıp
Run All çalıştırın. Önce eski kernel importlarını temizlemek için Kaggle
oturumunu başından başlatın. Bilgisayarda gerçek arama veya maç çalıştırılmaz.

## Tek değişiklik

`QuiescenceSEE` varsayılan olarak kapalıdır. Açıldığında yalnız şah çekilmeyen
quiescence düğümlerinde alışlar ve terfiler, maddi değişim tahminine (SEE) göre
sıralanır. Bütün yasal adaylar korunur; kaybeden alış elemesi ve delta pruning yok.
Şah kaçışlarının, ana aramanın, TT güvenliğinin ve değerlendirme ağırlıklarının
mevcut davranışı korunur. Seçenek değiştiğinde TT temizlenir.

SEE, özel bir 0x88 kare kopyası üzerinde en düşük değerli yasal saldırganlarla
değişimi tahmin eder. Açmaz, şahın güvenli alış yapması, açılan hatlar,
geçerken alma ve ilk hamlenin dört terfi türü hesaba katılır. Sonraki piyon
alışlarında terfi vezir varsayılır. Bu tahmin uzak tehditleri veya aynı
değerdeki bütün saldırgan alternatiflerini araştıran bir taktik çözüm değildir.
Sadece sıralama için kullanılır. Birden az/tek adayda SEE maliyeti ödenmez.

Sıralama standardı: SEE yüksekten düşüğe, eşitlikte eski MVV-LVA/promosyon
sırası, tam eşitlikte kararlı üretim sırası.
Algoritma arka planı: [Static Exchange Evaluation in Chess](https://www.chessprogramming.net/static-exchange-evaluation-in-chess/).

## Kaggle sırası

1. İlk çalıştırmada dalın tam commit'i kaydedilir; SEE açık ve kapalı taraflar
   aynı commit'in iki ayrı detached checkout'undan başlatılır. Sonraki veri
   push'ları kaynak kimliğini değiştirmez. Devam ederken kayıtlı commit kullanılır.
2. Yeni kimlik: `quiescence-see-500ms-100games-v1`. Protokol GitHub'a gönderilir.
3. Tüm doğruluk testleri Kaggle'da çalışır. SEE'nin kendi pozisyonları,
   pat/mat, terfi ve tahta restorasyonu denetlenir. Ardından sabit depth-3,
   10 pozisyonluk üç teşhis ölçümü kaydedilir: eski `4068a04`, yeni SEE kapalı,
   yeni SEE açık. Kapalı sürümün skor/hamle/derinlik/düğüm değerleri `4068a04`
   ile aynı değilse deney durur. Açık sürümün düğümleri/hamlesi değişebilir;
   seçici aramada skor farkı ayrıca rapordan incelenir. Teşhis süreleri tek
   geçiştir; tek başına hız veya Elo kararı sayılmaz.
4. Kontroller geçerse **tek çağrıda 100 maç**, iki tarafa **500 ms/hamle**.
   50 farklı açılış dizisi, renk değişimli çiftler, Seed 1, Hash 16 MB,
   Threads 1, concurrency 2, kitap ve SPRT kapalı, 400 ply sınırı.
   SEE açık taraf yeni/engine; kapalı taraf eski/opponent rolündedir.
5. Tam ham sonuçlar, günlükler, iki tarafın seçenekleri ve bitiş nedenleri
   GitHub'a aynı dala gönderilir. Zaman aşımı/geçersiz hamle/çökmede iki taraf
   da kaybeder. Dahili hata ayrı aborted olarak kaydedilir.

Beraberlik politikası bu deneyde değiştirilmedi: mevcut `claim_draw=True`
iki tarafa da uygulanır. Böylece SEE etkisi ile kural politikası karıştırılmaz.
Contempt ve NextIterationPct de mevcut varsayılanlarında kalır.

## Kayıt ve tekrar çalıştırma

`data/ab/<SESSION_ID>/validation/`: test günlüğü, üç teşhis, kaynak kimliği ve
SHA-256 ile doğrulanan kontrol sonucu. Başarılı kontrol tekrar çalıştırılmaz;
başarısız veya kesilmiş kontrol için günlük incelenip yeni SESSION_ID seçilir.
Tamamlanan 100 maç tekrar oynatılmaz. Başlamış ama tamamlanmamış maç koşusu
kendiliğinden yeniden başlamaz. Eski Kaggle oturumunu durdurmadan
RETRY_INCOMPLETE açılmamalıdır. Son hücre sadece push'u tekrarlar.

Maç ham kayıtları `data/runs/` altında değişmez dosyalardır; protokol ve kontrol
kayıtları `data/ab/` altında tutulur. Önceki iki A/B deneyinin kayıtları ve
`main` değiştirilmez. `analysis/` yalnız sonraki insan/analiz incelemesi içindir;
notebook güç kararı vermez ve o klasöre yazmaz.

Başarı ölçütü yalnız daha az düğüm değildir: SEE hesaplaması Python'da ek
maliyet getirir. Doğruluk, toplam süre, ulaşılan derinlik, teknik hatalar ve maç
puanı birlikte incelenmelidir. 100 maç kesin küçük Elo farklarını ispatlamayabilir.
