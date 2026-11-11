# Sonraki önerilen deney

## Güncel: Quiescence SEE v1 sonucu

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
