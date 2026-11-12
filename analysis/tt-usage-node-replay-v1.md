# TT kullanım teşhisi v1

Kaynak veri commit'i: `0405f6320833febcee35a1418d75a699077f5ba5`.
Dal: `codex/tt-diagnostics`. Üretim motoru ve TT politikası değiştirilmedi.

## Karar

Ölçüm tamamlandı ve tutarlı. TT kullanılmayan bir mekanizma değil: 45.575
skor kesmesi sağlamış. Bu iş yükünde kapasite sorunu gözlenmedi; tablo hiç
dolmadığından Hash büyütmek veya dolunca temizleme politikasını değiştirmek
öncelikli bir aday değil.

İncelenecek alan, aynı konuma ait farklı geçmişlerin birbirini ezmesi ve
kayıtların yeni arama derinliğine yetmemesi. Bu gözlemler tek başına hata veya
kolay Elo kazancı kanıtı değildir. Geçmiş/derinlik güvenliğini kaldırmak önerilmiyor.

## Veri ve doğrulama

- Kaggle'da **437 test / 109,418 saniye / OK**.
- 100 kayıtlı oyun, **5.076 kontrol pozisyonu**, 6.479.970 araştırılan düğüm.
- Yeni güç maçı yok. Kaynak son zaman politikası deneyinin 150 ayarlı kontrol tarafı.
- SEE kapalı; aynı oyun içinde TT sıcak, yeni oyunda yeni Searcher/TT.
- Her pozisyonda normal/sayaçlı arama aynı kayıtlı düğüm sınırında çalışmış;
  hamle, skor, tamamlanan/başlatılan derinlik, düğüm, mat ve TT içeriği eşleşmiş.
- Kayıtlı düğüm bütçeleri toplamı 6.480.048. Bir pozisyon sınırından önce
  döndüğü için araştırılan toplam 78 düğüm daha az; üst sınır ihlali yok.
- Protokol kimliği ve 110 Git blob SHA-256 değeri doğrulandı: 100 oyun dosyası,
  girdiler, test günlüğü, iki teşhis kaynak dosyası ve altı özgün maç dosyası.
- 5.076 satırın sayaç bölüşümleri, kimlikleri, bütçeleri ve oyun/deney toplamları
  bağımsız yeniden hesaplanıp results.json ile eşleştirildi.

Kaynak: `data/tt/tt-usage-node-replay-v1/`. Önce SUMMARY.md, ardından
results.json, validation.json, protokol, checkpoints ve oyun satırları okundu.
İnceleme sırasında yeni test, motor araması, benchmark veya maç başlatılmadı.

Bu bir 100 ms duvar süresi tekrarı değildir: sayaç maliyeti arama ağacını
daraltmasın diye eski kontrolün düğüm bütçeleri kullanılmıştır. Eski kaydın
hamlesiyle birebir eşleşme aranmaz; normal/sayaçlı çift kendi arasında eşleşir.
Elo veya gerçek hız sonucu çıkarılmamalıdır.

## Sorgudan kesmeye

- İç düğüm TT sorgusu: **635.667**.
- Bulunamayan kayıt: 423.935.
- Bulunan kayıt: **211.732 (%33,309)**.
- Geçmiş/clock context'i reddedilen: **64.583**, bulunanların **%30,502**'si.
- Context'i kabul edilen: **147.149**.
- Kabul edilen fakat derinliği yetersiz: **99.712 (%67,763)**.
- Derinliği yeterli: **47.437**.
- Gerçek skor kesmesi: **45.575**, tüm sorguların **%7,170**'i;
  derinliği yeterli kayıtların **%96,075**'i.
- Derinliği yeterli fakat pencere sınırı kesmeye yetmeyen: 1.862.

Kesme türleri: exact 2.216; lower 40.556; upper 2.803.
95 oyunda en az bir TT kesmesi görülmüş; 5 oyunda görülmemiş.
189 pozisyonda hiç iç düğüm TT sorgusu yok; medyan pozisyon sorgusu 97.

Yorum: geçerli ve yeterli derinlikte kayıt bulunduğunda çoğu zaten kullanılıyor.
Kesme şartlarını gevşetmek için veri yok. Bir kesme bütün bir alt ağacı
aramadan döndürebileceğinden %7,17 kesme oranı %7,17 hız kazancı anlamına gelmez.
%33,3 hit oranını başka motorlardan bağımsız bir iyi/kötü eşikle yargılamıyorum.

Bu sayaçlar `_probe` çağrılarının paydasıdır. Kökün doğrudan hamle ipucu okuması
dahil değildir; yazma sayaçlarına kök iterasyon kayıtları dahildir.
211.732 ipucu kullanılabilir bulunmuş, fakat bu ipuçlarının gerçekten sıralamada
kullanıldığı veya bir kesmeye neden olduğu ayrıca ölçülmemiştir.

## Geçmiş retleri

64.583 context reddinin tamamında geçmiş dizisi farklı. Bunların:

- 27.783'ünde yarım hamle sayacı da farklı.
- **36.800'ünde sayaç aynı, geçmiş dizisi farklı**; context retlerinin %56,981'i.
- Diğer context alanlarından kaynaklanan ret yok.

Bu nedenler örtüşür; clock ve history sayaçları toplanıp toplam ret sayısı
sanılmamalıdır. Sıfır null ret/yazma sayacı da null-move'un hiç çağrılmadığını
kanıtlamaz; o yolun TT hit/yazma engelleme olayları bu veri içinde görülmemiştir.

Mevcut kod tam geri alınabilir geçmiş dizisini eşleştiriyor. Bu, tekrar ve
elli hamleye bağlı skorları yanlış bağlamda kullanmamak için güvenlik kuralı.
Aynı sayaçla farklı geçmişten gelen 36.800 reddin tamamının gereksiz veya
güvenle kullanılabilir olduğu söylenemez. Eski tekrar/elli hamle testleri korunmalı.

## Yazma ve kapasite

- Yazma girişimi 590.474; gerçekleşen yazma 588.880.
- Yeni ekleme 420.766; aynı context'i güncelleme 103.797.
- **Farklı context kaydının üzerine yazma: 64.317**.
- Aynı context'teki daha derin kaydı koruma: 1.594.
- Kapasite nedeniyle tüm tabloyu temizleme: **0**.
- Açık clear_tt çağrısı: 0.
- En yüksek giriş sayısı: **13.550 / 80.000 (%16,938)**.
- Saklanan en uzun geçmiş dizisi: 100 konum.

Bu ölçüm Hash=16 ayarının mevcut yaklaşık giriş sınırını kullanır; gerçek
Python bellek tüketiminin %17'si veya gerçek 16 MB RAM kullanımı değildir.
Sadece bu düğüm bütçeli veri için kapasite temizliğinin kayıplara neden olduğu
iddiasını dışlar; daha uzun/derin aramalara otomatik genellenmez.

Derinliği yetersiz kayıt sayısının yüksek olması da doğrudan hata değil:
iteratif derinleştirmede daha derin iterasyon eski girişin derinliğini aşabilir.
Derinlik koşulunu kaldırmak önerilmiyor.

## Kodla ilişkisi ve sonraki aday

`engine/search.py` içindeki TT tek Zobrist anahtarına tek giriş saklıyor.
Farklı context gelince, eski giriş daha derin olsa da yerine yenisi yazılabiliyor.
64.317 farklı-context üzerine yazma bunun bu iş yükünde gerçekleştiğini gösteriyor;
kaçının daha sonra tekrar işe yarayacağı henüz ölçülmedi.

Bir sonraki küçük aday, **aynı konum için en fazla iki context kaydı tutarak**
eski yararlı/derin girişin hemen kaybolmasını azaltmak olabilir. Skor yine yalnız
tam güvenlik context'i eşleşince ve derinlik/pencere şartı sağlanınca kullanılmalı.
Bu henüz uygulanmış veya kazandırdığı kanıtlanmış bir değişiklik değildir.

Önce ek kaydın kaç sorguyu kurtardığını ve hesap/bellek maliyetini ölçmek gerekir.
Sonra tekrar/elli hamle regresyonları, uygun sabit iş yükü ve yalnız Kaggle'da
100 ms / tek 100 maç karşılaştırması. Veri kazanç göstermiyorsa mevcut TT korunur.
Geçmiş imzasını körlemesine gevşetmek, sığ skoru yeterli saymak veya sırf
kapasite doluyor varsayımıyla Hash büyütmek bu sonuçların desteklediği adımlar değil.

Bu rapor yalnız teşhis ve sonraki aday önerisidir. TT politikası, varsayılanlar,
beraberlik politikası, üretim kodu ve main değiştirilmedi; yeni deney başlatılmadı.
