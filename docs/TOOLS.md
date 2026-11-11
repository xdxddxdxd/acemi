# Maç ve analiz araçlarının modülleri

Komutlar aynı kalır: `python -m tools.match`, `python -m tools.analyze_games`
ve `python -m tools.analyze_report`. Modül ayrımı motor algoritmasını, CLI
varsayılanlarını veya ham maç kayıtlarının biçimini değiştirmez.

Maç aracı:

- `match.py`: koşu hazırlama, eşli işlerin planlanması, SPRT örneklemi, sonuç
  toplama ve kaydetme. CLI açıklaması ve `_parse_args` giriş noktası burada kalır.
- `match_config.py`: argümanlar, seçenek değerleri, komut ayrıştırma ve donanım/Git bilgisi.
- `match_openings.py`: `Opening`, yerleşik açılışlar ve FEN/UCI açılış dosyası okuma.
- `match_game.py`: bir oyunun UCI yaşam döngüsü, bağımsız hakem, tahta eşleştirme,
  PGN ve hamle kayıtları. `play_game` modül düzeyinde ve pickle ile taşınabilir
  kalır; süreç havuzu işçisi yeni modülünden yüklenir.

Analiz aracı:

- `analyze_games.py`: Stockfish işçileri, konum/oyun değerlendirmesi, cache görevleri,
  tanı kontrolleri ve CLI koordinasyonu. İşçi durumu burada kalır.
- `analysis_inputs.py`: ham koşuları okuma, sınıflandırma, açılış uzunluğu,
  sonuç örneklemi vekili ve tekrar oyunların ayıklanması.
- `analysis_schema.py`: sıralı pozisyon/oyun/blunder sütunları; biçim aynı kalır.
- `analysis_artifacts.py`: atomik yazma, parça kimlikleri, SHA-256/analiz kimliği
  denetimi, değişmez parçaları mühürleme ve küçük CSV dosyalarını birleştirme.
- `analysis_config.py`: analiz kimliği ve eski/uyumsuz çıktıya devam etmeyi engelleme.
- `analyze_report.py`: rapor üretimi; parçaları doğrudan saklama modülünden doğrular.

Önceki `tools.match.Opening`, `tools.match.play_game`, seçenek/açılış yardımcıları
ve `tools.analyze_games` içindeki girdi/şema/parça yardımcıları yeniden dışa
aktarılır. Mevcut import yolları korunur. Yardımcıları testte yamalarken gerçek
uygulama modülünü hedefleyin; işçi bağımlılıkları `tools.match_game` içindedir.
CLI yardım metinleri, varsayılanlar ve taşınan işlevlerin gövdeleri önceki sürümle
karşılaştırılmıştır; `_parse_args` açıklamayı eski CLI modülünden alan ince bir
sarmalayıcıdır.

Taşınan analiz dosyaları kaynak fingerprint'ine eklenmiştir. Eski analiz
kayıtları değiştirilmez; yeni üretim için analiz notebook'u
`data/analysis/step8` kullanır. Yeni bir analiz modülü çıktıyı etkiliyorsa
`analysis_config.ANALYSIS_SOURCES` listesine de eklenmelidir.

Yerel kontroller sahte işçi, küçük geçici dosyalar, CLI/import ve serileştirme
testleridir. Gerçek maç, arama, perft, benchmark ve tam test paketi Kaggle'da
çalışır. 8. adım runner'ı 7b sürümüne karşı aynı motor ağacı ve aynı aramayı
bekler; maçlar ve ek profil koşusu varsayılan kapalıdır.
