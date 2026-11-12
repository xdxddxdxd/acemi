# Paketli temel değerlendirme: 100 ms / tek 100 maç

12 Kasım 2026. **Bu iş yükünde hız kazancı var; oyun gücü artışı gösterilmedi.**
Paketli toplama aynı sabit aramayı yaklaşık %5,73 daha kısa sürede tamamladı.
100 maçta 34/33/33 (%50,5) alındı. Değişiklik, performans iyileştirmesi olarak
main'e alma adayıdır; sonuç bir Elo artışı veya bütün donanımlarda aynı hız vaadi değildir.

## Kaynak ve doğrulama

Aday ve kontrol aynı `fccb8643a8dac51213ef34deb661129483fcf0b6` commit'ini,
`64f05084fb717f14ba6c7e58a9f9100da080fbab` motor ağacını kullanmış.
Tek fark EvalPackedBase=true/false. İki tarafta TTTwoContexts=true,
QuiescenceSEE=false, NextIterationPct=150, Hash=16, Threads=1, kitap kapalı.
Sabit referans TT'nin etkin olduğu main `b22b8597dcdf40fa632d9585cd4901c87d97b306`.
[Protokol](../data/ab/packed-eval-100ms-100games-v1/protocol.json).

Kaggle'da **466 test 116,340 saniyede geçti**. Yoğun terfiler/negatif alanlar,
diğer değerlendirme seçenekleri, yasal hamle akışları, null/undo/FEN yükleme,
özel hamle konumlarında sabit işli arama ve ayar değişiminde TT temizliği
kontrolleri bu pakette. Referans ile adayın açık/kapalı bütün depth-4
geçişlerinde skor, hamle, tamamlanan/başlatılan derinlik, mat ve düğüm aynı.
[Test ve eşdeğerlik durumu](../data/ab/packed-eval-100ms-100games-v1/validation/status.json).

Bu incelemede 35 benzersiz Git blob'unun ilan edilen SHA-256 değerleri,
protokol özeti, ham dosya checkpoint'i, benchmark kaynak kimlikleri, UCI
seçenekleri ve maça geçiş kararının hesabı kontrol edildi. Windows satır sonu
dönüşümünden etkilenmemek için Git blob içerikleri kullanıldı. Yeni test,
motor araması, benchmark veya maç başlatılmadı.

## Hız ölçümü

Aynı Kaggle oturumunda sayaçsız Searcher, depth=4, 10 sabit pozisyon.
Sıra düz/paketli, paketli/düz, düz/paketli; her geçiş **173.729 düğüm**:

- Düz toplama: 11,0952 / 11,0999 / 11,0489 saniye.
- Paketli toplama: 10,5329 / 10,4591 / 10,4485 saniye.
- Medyan: 11,0952 → 10,4591 saniye; **%5,733 daha kısa süre**.
  Aynı iş için bu, yaklaşık **%6,082 daha yüksek düğüm/saniye** demektir.

Üç paketli geçişin her biri üç düz geçişin hepsinden kısa; sonuç tek hızlı
geçişe dayanmıyor. Pozisyonların medyanları ayrı alındığında 10/10'unda süre
kısalmış: başlangıç %5,98, İtalyan %4,94, Kiwipete %5,77, terfi %6,51,
taktik %5,56, açık oyun ortası %3,53, kapalı konum %5,58, hafif taş sonu %2,03,
kale sonu %0,42 ve vezir sonu %3,95. Sonuncusu yaklaşık 1 ms olduğundan yüzdesi
özellikle gürültüye duyarlıdır. Kiwipete toplam zamanın büyük bölümünü oluşturur;
toplam hız oranı her pozisyonda aynı hızlanma anlamına gelmez.

Önceden belirlenen en az %2 medyan süre azalması şartı geçmiş ve maçlar başlamış.
[Maça geçiş ölçümleri](../data/ab/packed-eval-100ms-100games-v1/eligibility.json).
Üç tekrar, 10 pozisyon, CPython 3.13.15 / Xeon 2,20 GHz ile sınırlıyız.
Diğer derinlikler, donanımlar, PyPy ve uzun süreli aramalar ayrıca ölçülmedi.
Eski deneylerdeki farklı düğüm sayıları/oturumların süreleriyle doğrudan kıyas yapılmadı.

## 100 maçın sonucu

100 ms/hamle, tek toplu 100 oyun, 50 renk değiştirmeli açılış çifti,
Seed=1, concurrency=2, 400 ply sınırı, SPRT kapalı:
**34 galibiyet / 33 beraberlik / 33 mağlubiyet = %50,5 puan**.
Beyazda 18/14/18 (%50), siyahta 16/19/15 (%51).
İki tarafta da süre aşımı, geçersiz hamle ve çökme yok; iptal, tahta uyuşmazlığı
ve eksik renk çifti yok.
[Maç özeti](../data/ab/packed-eval-100ms-100games-v1/SUMMARY.md).

50 çiftin 10'u puanla kazanıldı, 27'si eşit, 13'ü kaybedildi.
Çift toplam puanı dağılımı: 0 puan 1 çift; 0,5 puan 12; 1 puan 27;
1,5 puan 5; 2 puan 5. Toplam eşitlikten yalnız 0,5 puan fazla.
Çift içindeki sonucu koruyan tam işaret çevirme hesabında, bağımsız çiftler
ve sıfır hipotezinde simetri varsayımıyla iki taraflı p=1,0. Gözlenen
fark bu ayrık dağılımda sıfıra en yakın olası farktır. Bu, motorların eşit
güçte olduğunun kanıtı değil; bu örneklem üstünlük göstermiyor.

Ham raporun lojistik Elo tahmini +3,5, yaklaşık %95 Wilson aralığı
−64,2…+71,1. Bu aralık oyunları tek tek sayar ve renk çiftlerini modellemez;
mutlak Elo değildir. “+3,5 Elo güçlendi” veya “gerileme yokluğu kanıtlandı” denemez.
Önceki TT deneyinin %52,5 puanıyla %50,5'i kıyaslayıp düşüş ilan etmeyin:
o deneyin kontrolü TT kapalıydı; bu deneyin iki tarafında TT açıktır.

Gerçek maçta aday/kontrol ortalamaları: arama 82,075 / 82,222 ms;
tamamlanan derinlik 2,583 / 2,563; kesilen son iterasyon %44,94 / %46,60;
arama zamanına göre düğüm/saniye 15.750 / 15.223. Mat skorlarını çıkarınca
derinlik 2,599 / 2,574. Taraflar farklı konumlar araştırdığından bu ortalamalar
tek başına neden-sonuç ölçümü değildir; hız için esas dayanak sabit işli ölçümdür.
Yaklaşık %6 daha fazla düğüm/saniye bir tam derinlik daha arama garantisi vermez.

## Sıradaki geliştirme

Hız optimizasyonu puanlama mantığını değiştirmiyor. Erken taktik kayıplar
sürüyor: **19. oyun**, önceki TT deneyindekiyle aynı hamle dizisiyle 20 ply'de
mat bitmiş: `6.cxd5 exd5 7.Nb5 Bb4+ 8.Nd2 Ne4 9.a3 Qh4 10.axb4 Qxf2#`.
55. oyun 42 ply'de mat; şah kanadındaki piyon ilerlemeleri sonrası saldırı
gelmiş. Bunlar gözlemdir; ilk kaybettiren hamle veya hatanın arama/değerlendirme
nedeni Stockfish/oracle incelemesi yapılmadan kesinleştirilmemelidir.
33 kaybın 30'u oyun sonunda bitmiş olsa da hatanın oyun sonunda başladığı söylenemez.
33 beraberliğin 31'i tekrar, ikisi yetersiz materyal; hakem politikası değişmedi.

**Öneri:** EvalPackedBase'i ölçülmüş bir performans iyileştirmesi olarak main'e
alma adayı kabul et; Elo iddiası ekleme. Kabul edilirse sonraki deneylerin iki
tarafında TT ve bu optimizasyon aynı ayarda sabitlensin. Sıradaki asıl oyun gücü
çalışması için 19 ve 55'in kritik pozisyonlarını, farklı oyunlardan diğer erken
kayıpları ve bir kontrol grubunu önceden belirlenmiş Kaggle Stockfish teşhisinde
etiketle. İlk hata, mat tehdidi ve daha derin aramayla düzelip düzelmediği
görüldükten sonra tek bir arama veya şah güvenliği değişikliği seç.
Şah güvenliği/beraberlik seçeneklerini topluca açmak için bu ölçüm kanıt sağlamıyor.

Bu analizde yalnız bu rapor ve NEXT güncellendi. Motor, varsayılanlar,
notebook, ham veriler ve main değiştirilmedi; yerel bilgisayarda maç başlatılmadı.
