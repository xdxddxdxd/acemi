# Erken kayıplar: 107 pozisyonun teşhisi

12 Kasım 2026. **En somut ilk hedef, ilk kök arama turu kesildiğinde hamle
seçiminin güvenliği.** 19. oyunda Acemi, seçtiği hamlenin bir hamlede mat
kaybettirdiğini raporlarken ilk iterasyonu tamamlayamamış. Savunma hamlesi
mevcut. Daha geniş arama bazı başka taktik hataları da azaltıyor; bütün
sorunları çözmüyor. NullMove/LMR'yi topluca kapatmak için kanıt yok.

## Kayıt ve kapsam

107/107 pozisyon tamamlanmış; yeni maç yok. Kaynak motor main
`38b0722b084552d8e94eb62e3558d447b641969c`, toplayıcı
`01dca2e86416a953dc489e1ef3efeab1a507f9fa`; Stockfish 16, CPython 3.13.15.
TT ve paketli değerlendirme açık, SEE kapalı, NextIterationPct=150.
78 pozisyon dört kısa kayıptan; 13'ü iki galibiyetten, 16'sı iki beraberlikten.
Bu amaçlı seçilmiş bir gruptur; bütün motorun hata oranı değildir.
[Ham özet](../data/tactics/tactical-losses-v1/SUMMARY.md).

İncelemede protokol kimliği ve 115 Git blob'unun SHA-256 değeri doğrulandı:
107 pozisyon dosyası, dondurulmuş girdiler, toplayıcı ve altı ham kaynak dosyası.
Bütün konumlar tam hamle geçmişinden yeniden oluşturuldu; 642 kaydedilmiş
Stockfish PV'sindeki hamlelerin yasallığı kontrol edildi. Materyal/pozisyon
kayıtları ve checkpoint'ler değişmedi. Bu kontroller kayıt okuma ve yasallık
doğrulamasıdır; yeni motor araması, benchmark veya maç yapılmadı.

## Ölçümün sınırı

Stockfish'in ilk probunda 107 kök ve 107 zorlanmış-hamle araması depth=12'ye
ulaşmış; bu çiftlerde alt/üst sınır işareti yok. İkinci probda istenen depth=18,
100.000 düğüm bütçesi nedeniyle köklerin yalnız **20/107'sinde** tamamlanmış;
ulaşılan kök derinliği 13–18. İki skorunda da sınır işareti olmayan çift sayısı
**38/107**. Bu nedenle sonuçları “107 pozisyon depth-18 çözüldü” diye okumayın.

Sınır işaretli skorları kesin cp farkına çevirmedim. Mat skorları da cp'ye
dönüştürülmedi. Eksik/uygun olmayan cp farkı sıfır hata anlamına gelmez.
İlk probda 21 konumda en az 100 cp fark ve altı konumda yalnız kaydedilmiş
hamle zorlandığında kaybedilen mat etiketi var; bunlar bağımsız oyunlar veya
ilk hatalar sayılmaz. Kötü bir konumda sonraki kötü hamleler de bu sayılara girer.

## 19. oyun: somut bir hamlede mat hatası

Konum `g019-p019`, Beyazın 10. hamlesi:
`10.axb4? Qxf2#`. Kayıttaki bu iki hamle uygulandığında şah mat olduğu
ayrıca doğrulandı. Acemi'nin 100 ms kaydı:

- Tamamlanan depth **0**, başlatılan depth **1**.
- **1.366 düğüm**, raporlanan arama süresi **100 ms**.
- Seçilen hamle `a3b4`, motorun kendi skoru **mate −1**.

Stockfish depth-12 probu `g2g3` öneriyor (+42 cp); `a3b4` zorlandığında mat −1
buluyor. İkinci probun PV'si de `g2g3` ile başlıyor, fakat kök skoru üst sınır
işaretli olduğundan +35'i kesin skor kabul etmiyoruz. 12.000 düğümlük Acemi
aramaları normal ve NullMove+LMR kapalıyken `f4g3` seçmiş, depth=3 tamamlamış.
Dolayısıyla bu örnekte arama savunma adayına ulaşabiliyor.
[Konum kaydı](../data/tactics/tactical-losses-v1/positions/g019-p019.json).

Bir önceki `9.a3` konumunda Stockfish depth-12'nin ilk tercihi de `a2a3`.
Bu kayıtlar 9.a3'ü doğrudan matın nedeni ilan etmeyi desteklemiyor.
[Önceki konum](../data/tactics/tactical-losses-v1/positions/g019-p017.json).

Kodda [search.py](../engine/search.py) kök hamleleri sırayla araştırıyor;
`_partial`, o turda tamamlanmış çocuklardan en iyisini saklıyor. `_SearchStopped`
geldiğinde ilk iterasyon tamamlanmasa bile bu hamle/skor kullanılabiliyor.
Bu, görülen depth=0 / mate−1 çıktısıyla uyumlu. Mat skoru bulunduğunda bütün
yasal hamlelerin mat kaybettiği sonucuna varılamaz: tur tamamlanmamış.
Kayıt kök hamle başına süre/düğüm tutmadığından hangi dalın bütçeyi tükettiğini
kesin söyleyemiyoruz. Bu örnek, genel bir mat hesaplama hatasını kanıtlamıyor;
kesilen ilk turdaki seçim mekanizmasını somut hedef yapıyor.

## Diğer kayıplar aynı nedenle açıklanmıyor

- **55. oyun, 7.Bg5 (`g055-p013`)**: depth-12 Stockfish'in en iyi skoru
  +94 cp, oynanan hamleyi zorlayınca −98 cp; fark 192 cp. 12.000 düğümlük
  iki Acemi araması da Bg5'te kalıyor. Bütçeyi büyütmek tek başına bütün
  tercihleri düzeltemiyor.
  [Kayıt](../data/tactics/tactical-losses-v1/positions/g055-p013.json).
- **76. oyun, 8...Nd7 (`g076-p016`)**: Siyah açısından depth-12 skorları
  +102 / −99 cp, fark 201 cp. Daha geniş iki Acemi araması `e7e6` seçiyor;
  onun zorlanmış Stockfish etiketi +102 cp (ulaşılan depth=15, sınır işareti yok).
  Bu bir teşhis iyileşmesi; oyunun o anda geri dönülmez biçimde kaybedildiği
  anlamına gelmiyor.
  [Kayıt](../data/tactics/tactical-losses-v1/positions/g076-p016.json).
- **77. oyun, 23.Rf5 (`g077-p045`)**: depth-12 skorları +1 / −473 cp;
  ikinci probda iki arama da depth=16'da −4 / −498 cp, sınır işareti yok.
  Yaklaşık 4,7–4,9 piyonluk kayıp iki ölçümde de görülüyor. PV
  `Rf5 Rb5 Qxb5 axb5` taktik dizisini gösteriyor. Normal geniş arama Rg3,
  elemeler kapalı arama Rf4 seçiyor; bunların ikinci Stockfish etiketleri
  sınır işaretli olduğundan kesin cp kazancı yazmıyoruz.
  [Kayıt](../data/tactics/tactical-losses-v1/positions/g077-p045.json).

Daha çok aramanın sınırına örnek: 55. oyunun `g055-p035` konumunda pozisyon
zaten çok kötü; Stockfish kökte yaklaşık −5,69 piyon buluyor. İki geniş Acemi
araması `d6f8` seçiyor ve onun zorlanmış probu mat −6 veriyor. “Daha derin arama
her hatayı çözer” sonucu çıkmıyor.
[Kayıt](../data/tactics/tactical-losses-v1/positions/g055-p035.json).

## NullMove/LMR kararı

Normal ve iki elemenin birlikte kapalı olduğu arama **97/107 konumda (%90,65)**
aynı hamleyi seçmiş. Ortalama tamamlanan derinlik normalde **3,617**,
elemeler kapalıyken **3,346**. Ortalama harcanan düğüm 11.290 / 11.341;
her ikisinin üst bütçesi 12.000 ve derinlik sınırı 8. Aynı düğüm bütçesinde
elemeleri kaldırmak daha az tamamlanmış derinlik getirebilir. Farklı hamleler
tek başına pruning hatası kanıtı değildir; bu deney iki elemeyi ayrı ayrı ayırmıyor.
Mevcut NullMove ve LMR ayarları korunmalı.

Kayıtlı maç hamlelerinin ortalama derinliği 2,009, ortalama düğümü 1.201.
Geniş normal arama 41 konumda farklı hamle seçmiş. Bu, saf bir bütçe A/B'si
değildir: kayıtta sıcak TT ve ilerlemiş RNG var, teşhiste temiz TT ve Seed=1.
Skorları ikisi de sınır işaretsiz cp olan 40 karşılaştırmada üç en az 100 cp
iyileşme var: `g037-p015` +387, `g076-p046` +448, `g076-p054` +415 cp.
Bu alt grupta en az 100 cp kötüleşme yok; ancak mat skorları/diğer sınır
işaretli konumlar bu hesaba girmez. Bu sayıdan bütün konumlarda iyileşme veya
maç gücü artışı çıkarılamaz. Yeni maç/Elo ölçümü yapılmadı.

## Sonraki küçük çalışma

**İlk hedef:** 19. oyundaki gibi savunma varken ilk tur kesilmesi yüzünden
bilinen bir hamlede mat hamlesini seçme riskini azaltan, varsayılan kapalı
bir kök güvenliği adayı. Kök hamle başına tamamlanma/düğüm ve seçimin
tamamlanmış turdan mı `_partial`dan mı geldiği ayrıca ölçülsün; bu sayede
bütçeyi tüketen dal saptansın. Acil güvenlik incelemesi de süre/düğüm
bütçesine sayılmalı; hamle değiştirilirse eski hamlenin skoru taşınmamalı.
Kesinliği olmayan statik bir puan, “matdan güvenli” diye etiketlenmemeli.

Önce bu sabit pozisyonlar ve bağımsız mat/kaçış regresyonlarıyla doğruluk ve
ek maliyet ölçülmeli. Uygunsa aynı main'e karşı 100 ms / tek 100 maçlık ayrı
A/B hazırlanmalı. Bu aday genel şah güvenliği veya oyun sonu sorunlarının
tamamını çözme iddiası taşımaz. Kapsamlı değerlendirme değişiklikleri ve
beraberlik politikası ayrı deneyler olarak kalsın.

Bu analizde yalnız bu rapor ve NEXT güncellendi; motor, varsayılanlar,
notebook, ham veriler ve main değiştirilmedi. Bilgisayarda motor araması,
performans testi veya maç başlatılmadı.
