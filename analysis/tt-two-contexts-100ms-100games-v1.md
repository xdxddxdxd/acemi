# TT iki context deneyi: 100 ms / tek 100 maç

12 Kasım 2026. **Teknik fayda ölçüldü; oyun gücü artışı henüz kanıtlanmadı.**
İkinci kayıt gerçekten kullanılabiliyor ve sabit düğüm bütçesinde bazı
pozisyonlarda daha fazla derinlik tamamlanıyor. Maç puanı hafif olumlu, fakat
varsayılanı değiştirmek veya main'e almak için yeterli değil.

## Deney ve kayıt doğrulaması

İki tarafta aynı kaynak `d693129287b8e55936a4760fe4473a3a32b8e5a0`,
aynı motor ağacı `1007701fafd83aec3282be64c7cd95b4678305b3` kullanılmış.
Tek fark `TTTwoContexts=true/false`. SEE kapalı, NextIterationPct=150,
Hash=16, tek thread, kitap ve SPRT kapalı. Aynı 50 açılış renk değiştirilerek
tek toplu 100 oyun oynanmış; hamle süresi iki tarafta 100 ms. Donanım Kaggle
Xeon 2,20 GHz, CPython 3.13.15, concurrency=2.
[Protokol](../data/ab/tt-two-contexts-100ms-100games-v1/protocol.json).

Kaggle'da **458 test / 108,915 saniye** başarılı. Kapalı seçenek, `4068a04`
referansıyla sabit depth-3 pozisyonlarında skor, hamle, derinlik ve düğüm
açısından aynı. Normal/sayaçlı aramanın eşdeğerliği her politikanın kendi
içinde doğrulanmış; iki politikanın her konumda aynı hamleyi seçmesi şart değil.
[Doğrulama](../data/ab/tt-two-contexts-100ms-100games-v1/validation/status.json).

İncelemede 94 benzersiz Git blob'unun ilan edilen SHA-256 değerleri kontrol
edildi: ham maç dosyaları, benchmark/test çıktıları, teşhis checkpoint'leri,
sabit girdiler ve ilgili toplayıcı kaynakları. Protokol özetleri, iki teşhisin
2.114 satırının sayaç denklikleri ve satır/oyun/toplam birikimleri doğrulandı.
Yerel Windows satır sonları yerine Git blob içerikleri kullanıldı.
Bu inceleme yalnız kayıt okuma ve hesaplamadır; yeni motor araması veya maç yok.

## Maç sonucu ve belirsizlik

Yeni seçenek **40 galibiyet / 25 beraberlik / 35 mağlubiyet: %52,5 puan**.
Beyazda 21/14/15 (%56), siyahta 19/11/20 (%49).
İki tarafta da zaman aşımı, geçersiz hamle ve çökme yok; iptal edilen oyun,
tahta uyuşmazlığı ve eksik renk çifti yok.
[Sonuç özeti](../data/ab/tt-two-contexts-100ms-100games-v1/SUMMARY.md).

50 açılış çiftinde aday 16 çifti puan olarak kazandı, 24'ünde eşit kaldı,
10'unu kaybetti. İki oyunun toplam puan dağılımı:
0 puan: 5 çift; 0,5: 5; 1: 24; 1,5: 12; 2: 4.
Toplam 52,5/100 puan, eşitlikten yalnız 2,5 puan fazla.
Çift içi sonucu koruyan tam işaret çevirme hesabı, çiftlerin bağımsızlığı ve
sıfır hipotezinde simetri varsayımıyla iki taraflı p≈0,587 veriyor.
Bu küçük örneklem güçlü bir üstünlük göstermiyor.

Ham raporun lojistik Elo tahmini +17,4; oyunları tek tek sayan yaklaşık
%95 Wilson aralığı −50,4…+85,1. Bu aralık renk çiftlerini modellemiyor ve
mutlak Elo değil; her iki yönde de anlamlı farkla uyumlu.
Bu nedenle “motor +17 Elo güçlendi” denemez.

## TT kullanımında ne değişti?

Bu bölüm yeni maçların sayaçları değildir. Önceden dondurulmuş 20 oyun
kaydındaki aynı **1.057 pozisyon**, aynı kayıtlı düğüm bütçeleriyle tekrar
incelenmiştir. Gerçek süre sınırlaması yoktur; sayaçlı süreler hız ölçümü değildir.
[Tek kayıt](../data/tt/tt-two-contexts-100ms-100games-v1-replay-single/results.json),
[iki kayıt](../data/tt/tt-two-contexts-100ms-100games-v1-replay-pair/results.json).

- Toplam TT kesmesi 10.645 → 11.430: **+%7,37**. Sorgu başına kesme
  %8,015 → %8,571; sorgu sayıları da değiştiğinden bu doğrudan hız oranı değildir.
- İkinci kayıttan 1.271 tam-context kabulü, 682 yeterli derinlikli kabul ve
  **661 gerçek kesme** geldi. Bu 661, ikinci kaydın kullanım sayısıdır;
  tek-kayıt aramasına karşı net fazladan kesme sayısıyla aynı kavram değildir.
- Context reddi 12.410 → 11.406: **−%8,09**. Tam geçmiş/saat eşleşmesi ve
  derinlik/pencere güvenliği korunmuştur.
- Aynı düğüm bütçesinde 37 pozisyonda (%3,50) daha fazla derinlik tamamlandı;
  hiçbirinde daha az tamamlanmadı. 1.020'sinde tamamlanan derinlik eşit.
  Yedi konumda hamle ve altısında skor değişti; daha iyi hamle olduğu ayrıca
  kanıtlanmış değildir. Ortalama tamamlanan derinlik 2,047 → 2,082.
- Tepe giriş sayısı 8.382 → 9.422 (**+%12,41**); iki tablo da 80.000 toplam
  giriş sınırını kullanıyor ve hiç kapasite temizlemesi olmamış. Adayda tepe
  doluluk %11,78. Gerçek Python bellek miktarı bu kayıtlarla ölçülmedi.

Toplam düğümler 1.327.361 / 1.327.150. Bütçe zaten düğümle sınırlandığı için
bu fark performans tasarrufu diye yorumlanamaz; erken dönüşler bütçeyi tüketmeyebilir.

## Hız ve gerçek maçtaki arama

Sayaçsız, aynı 10 pozisyonlu depth-3 işinde üç dönüşümlü geçiş:
tek kayıt 3,9902 / 4,0003 / 4,0508 saniye;
iki kayıt 4,0106 / 4,0115 / 4,0119 saniye.
Medyanlar 4,0003 / 4,0115 saniye: aday **%0,28 daha uzun**.
Her iki politikanın bütün geçişlerinde hamle/skor/derinlik/düğüm aynı,
toplam 66.798 düğüm. Bu dar iş yükünde ölçülebilir hız kazancı yok;
küçük süre farkını anlamlı yavaşlama diye de sunmuyoruz.
Üç geçiş ve soğuk/sığ konumlar, sıcak TT kullanılan uzun aramayı bütünüyle temsil etmez.
[Önceden tanımlı maliyet kontrolü](../data/ab/tt-two-contexts-100ms-100games-v1/eligibility.json)
geçmiş; bu kontrol güç veya birleştirme kararı değildir.

Gerçek maçta aday/kontrol ortalama arama süreleri 82,315 / 82,540 ms;
tamamlanan derinlikler 2,539 / 2,556; kesilmiş son iterasyon oranları
%46,27 / %46,59. Arama zamanına göre düğüm/saniye 15.345 / 15.396.
Tarafların aradığı pozisyonlar farklı olduğundan bu ortalamalar hızın veya
derinliğin aday nedeniyle arttığını/azaldığını izole etmez.

## Çözülmeyen sorunlar ve karar

25 beraberliğin 22'si tekrar, biri elli hamle, ikisi yetersiz materyal.
`claim_draw=True` hakem politikası değişmedi. Önceki deneylerdeki beraberlik
sayılarıyla fark, bu seçeneğin tekrar sorununu çözdüğünü göstermez.

Taktik zayıflıklar sürüyor: aday 19. oyunda 20 ply'de mat oluyor.
Açılıştan sonra `6.cxd5 exd5 7.Nb5 Bb4+ 8.Nd2 Ne4 9.a3 Qh4
10.axb4 Qxf2#`. Dokuzuncu hamlede yalnız bir derinlik tamamlanmış;
son hamlede ilk derinlik tamamlanamamış. Bu bir teşhis adayıdır;
hangi önceki hamlenin kaybettirdiği veya güvenli alternatifin ne olduğu
Stockfish/oracle incelemesi yapılmadan kesinleştirilemez.
35 kaybın 31'inin sonu oyun sonunda olsa da hatanın orada başladığı söylenemez.

**Öneri:** TTTwoContexts adayını koru, varsayılanı şimdilik kapalı bırak ve
main'e alma. Sonraki deneyde tek değişkeni koruyarak Kaggle'da yine
100 ms / tek toplu 100 maçla doğrula; yeni oturum kimliği ve farklı açılış
seçimi/seed kullan. Mevcut 64 açılıştan 50 seçildiği için yeni seçimin öncekiyle
örtüşeceğini açıkça kaydet. Aynı açılışları sürekli tekrarlamak yerine sonrasında
daha geniş, önceden belirlenmiş bir doğrulama kümesi gerekir.
Beraberlik, süre veya değerlendirme politikasını bu teyit deneyiyle birlikte değiştirme.
Teyit sonucu da belirsiz kalırsa daha fazla TT karmaşıklığı eklemek yerine,
erken mat pozisyonları ve temel değerlendirme maliyeti sonraki ayrı adaylardır.

Bu analizde yalnız bu rapor ve NEXT güncellendi. Motor, varsayılanlar,
notebook, ham kayıtlar ve main değiştirilmedi; bilgisayarda test maçı başlatılmadı.
