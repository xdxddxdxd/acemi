# Sonraki önerilen deney

## Güncel: İki TT context'i / 100 ms sonucu

[TT iki context raporu](tt-two-contexts-100ms-100games-v1.md).

458 Kaggle testi geçti. Tek toplu 100 maçta aday 40/25/35 (%52,5);
iki tarafta da teknik hata yok. 50 açılış çiftinin 16'sı kazanıldı,
24'ü eşit, 10'u kaybedildi. Güç artışı henüz kanıtlanmadı.

20 kayıtlı oyun / 1.057 konumda ikinci kayıt 661 kesme sağlamış;
toplam TT kesmesi 10.645 → 11.430 (+%7,37), context reddi −%8,09.
Aynı düğüm bütçesinde 37 konumda daha fazla derinlik, hiçbirinde daha azı yok.
Bu sayılar gerçek maç sayaçları veya hız yüzdesi değildir.
Normal depth-3 medyan süre farkı +%0,28; düğüm ve sonuçlar aynı.
Ölçülmüş hız artışı yok. Her iki tablo da kapasitenin çok altında kalmış.

Öneri: adayı koru; TTTwoContexts varsayılan kapalı ve main değişmeden kalsın.
Sonraki küçük teyit Kaggle'da yeni kimlik ve farklı açılış seçimi/seed ile
yine 100 ms / tek toplu 100 maç. 64 açılıştan 50 seçildiğinden kümelerin
örtüşmesi kaçınılmaz; daha geniş açılış doğrulaması daha sonra gerekir.
Aynı deneyde süre/beraberlik/eval politikasını değiştirme.
Teyit belirsiz kalırsa erken matları (özellikle oyun 19) teşhis et ve
temel değerlendirme maliyetini ayrı aday olarak incele.
Bu incelemede yeni arama/maç/test, motor/notebook değişikliği veya main merge yok.

## Önceki: TT kullanım teşhisi v1

[TT raporu](tt-usage-node-replay-v1.md).

437 test geçti; 100 kayıtlı oyun / 5.076 pozisyonda normal ve sayaçlı arama
eşdeğer. TT 635.667 sorguda 211.732 hit ve 45.575 gerçek kesme sağlamış.
Tablo hiç dolmamış; en yüksek giriş sayısı 13.550 / 80.000 (%16,94).
Hash büyütme veya full-clear değiştirme bu iş yükünde öncelik değil.

64.583 context reddinin 36.800'ünde saat aynı, geçmiş farklı.
64.317 kez farklı context kaydı eskisinin üstüne yazılmış. Sonraki küçük aday:
aynı konum için en fazla iki context kaydını koruyup kaç kurtarılabilir sorgu
olduğunu ve ek maliyeti ölçmek. Tam context/derinlik/pencere güvenliğini koru;
tekrar ve elli hamle koşullarını gevşetme. Güç kazancı henüz gösterilmiş değil.
Sonra uygun doğruluk kontrolleri, sabit iş yükü ve ayrı 100 ms / tek 100 maç A/B.
Bu incelemede kod/politika/main değişikliği veya yeni arama/maç yapılmadı.

## Önceki: Süre politikası v1 sonucu

[100 / 150 raporu](20261112T054659Z_0.8.2_acemi-0.8.2-ownbook-false-nextiterationpct-150-quiescencesee-false_72a0d1c_time-policy-100vs150-100ms-100games-v1_c01.md).

427 Kaggle testi geçti. NextIterationPct=100, 100 ms / tek 100 maçta
28/37/35 (%46,5) aldı. Güç artışı gösterilmedi; mevcut **150 korunmalı**.
Arama ortalaması 88,9 / 82,7 ms; son iterasyon kesilme oranı %58,43 / %46,45.
Daha fazla süre ve daha çok başlatılan derinlik maç puanını iyileştirmedi.
100 oyunla kesin gerileme ilan edilmedi; varsayılanı değiştirmek için kanıt yok.

Sonraki öneri: yeni eşikleri körlemesine deneme. Önce somut kayıp pozisyonları
veya üçüncü adım için TT probe/context/cutoff/full-clear sayaçlarıyla ölçüm.
Ölçülen soruna göre tek değişkenli aday çıkar; tekrar/elli hamle güvenliğini koru.
Beraberlik politikası ve oyun sonu eğitimi ayrı deneyler olarak kalmalı.
Bu incelemede yeni arama/maç, motor/notebook değişikliği veya main merge yapılmadı.

## Önceki: Quiescence SEE v1 sonucu

[SEE v1 raporu](20261111T172641Z_0.8.2_acemi-0.8.2-ownbook-false-quiescencesee-false_d0bbfe2_quiescence-see-100ms-100games-v1_c01.md).

422 Kaggle testi geçti; SEE kapalı, `4068a04` referansıyla eşdeğer.
100 ms / tek 100 maç: SEE açık 34/36/30 (%52), güç kazancı belirsiz.
Sabit depth-3 teşhisinde düğüm %20,3 azaldı fakat tek geçişte süre %14,6 uzadı.
Bu haliyle SEE varsayılan kapalı kalmalı; main'e iyileştirme diye alınmamalı.

Sonraki öneri: yalnız Kaggle'da aynı oturumda dönüşümlü, tekrarlı sabit görev
ölçümü ve ayrı açık/kapalı profil. Özellikle SEE saldırgan listesi/sıralama,
şah güvenliği ve terfi maliyetlerini ayır. Profil desteklerse daha ucuz veya
daha seyrek SEE hesaplayan ikinci sıralama adayı; ardından yeni kimlikle
100 ms / tek 100 maç. Bu aşamada eleme/delta pruning ekleme.
Maliyet düzelmiyorsa SEE'yi kapalı tutup süre veya beraberlik politikasına geç.
Mevcut `claim_draw=True` politikasını SEE deneyiyle birlikte değiştirme.
Bu incelemede yeni arama/maç başlatılmadı; motor, notebook ve main değiştirilmedi.

## Önceki genel yol haritası

11 Kasım 2026 incelemesi:
[100 ms / 500 ms karşılaştırması](20261111T160948Z_0.8.2_acemi-0.8.2-ownbook-false_4068a04_eight-steps-500ms-100games_c01.md).

Mevcut 100 ms %52 ve 500 ms %49,5 sonuçları belirgin güç artışı veya gerileme
kanıtı değil. İki testte de teknik hata yok. Yeni motorun 500 ms arama ortalaması
405 ms; mevcut profilde quiescence düğümleri toplamın %98,2'si.

1. Yalnız Kaggle'da oyun 14, 52, 97'nin erken matları ile oyun 25 ply 81,
   oyun 74 ply 132 ve 100 ms global oyun 96 ply 98 adaylarını sabit teşhis
   setinde Stockfish ile etiketle. Kendi eval düşüşünü cp loss diye etiketleme.
2. En küçük ilk A/B: `4068a04` motorunda yalnız NextIterationPct=100 / 150,
   iki tarafa 500 ms, tek 100 oyun, 50 renk değiştirmeli açılış çifti.
   Yeni kimlik; aynı donanım, Hash 16 MB, tek thread, kitap/SPRT kapalı.
   Süre dolması, erken çıkış nedeni, tamamlanan/başlatılan derinlik ve puan ayrı ölçülsün.
3. Sonraki kod adayı: quiescence için önce yalnız SEE sıralaması; sonra gerekirse
   ayrı deneyde kontrollü eleme. Pat/terfi/şah kaçışı doğruluğunu koru.
4. TT'ye önce probe/context/cutoff/full-clear sayaçları ekle. Kanıt olmadan
   tekrar geçmişi güvenliğini kaldırma veya tüm tablo politikasını değiştirme.
5. Artımlı temel eval ve pozisyonlarla desteklenen tekil eval terimleri daha sonra.

Bu dosya öneri kaydıdır. Motor kodu veya notebook değiştirilmedi; bilgisayarda
ve Kaggle'da bu inceleme adına yeni maç/arama başlatılmadı. `main` değiştirilmedi.
