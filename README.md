<h1 align="center">Acemi</h1>

<p align="center">
  <strong>Python ile sıfırdan geliştirilen UCI satranç motoru.</strong><br>
  Kendi hamle üretimi, arama algoritması ve klasik değerlendirmesiyle.
</p>

<p align="center">
  <a href="https://github.com/xdxddxdxd/acemi/actions/workflows/ci.yml"><img src="https://github.com/xdxddxdxd/acemi/actions/workflows/ci.yml/badge.svg?branch=main" alt="main dalı CI durumu"></a>
  <a href="engine/"><img src="https://img.shields.io/badge/engine-Python%20stdlib-3776AB?logo=python&amp;logoColor=white" alt="Motor çekirdeği: Python standart kütüphanesi"></a>
  <a href="CHANGELOG.md"><img src="https://img.shields.io/badge/version-0.8.2-64748b" alt="Sürüm 0.8.2"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0-64748b" alt="GPL-3.0 lisansı"></a>
</p>

<p align="center">
  <a href="#baslangic">Başlangıç</a> ·
  <a href="#ozellikler">Özellikler</a> ·
  <a href="#olcumler">Ölçümler</a> ·
  <a href="#kaggle">Kaggle</a> ·
  <a href="#belgeler">Belgeler</a>
</p>

---

Acemi; satranç kurallarını, hamle üretimini, aramayı ve konum değerlendirmesini
kendi koduyla uygulayan bir motor projesidir. Geliştirmeler doğruluk testleri,
tekrarlanabilir ölçümler ve eşit süreli maçlarla değerlendirilir.

**Motor çekirdeği yalnız Python standart kütüphanesini kullanır.** `python-chess`
ve NumPy; test, analiz ve ölçüm araçlarına aittir. Proje UCI üzerinden çalışır;
grafik satranç arayüzü ayrıca sağlanmalıdır.

<a id="baslangic"></a>
## Hızlı başlangıç

Depoyu indirip motoru başlatın:

```bash
git clone --depth 1 --branch main https://github.com/xdxddxdxd/acemi.git
cd acemi
python -u -m engine
```

Motor açıldıktan sonra aşağıdaki UCI komutlarını satır satır gönderebilirsiniz:

```text
uci
isready
ucinewgame
position startpos
go movetime 500
```

Motor, 500 ms arama bütçesiyle seçtiği hamleyi `bestmove` satırında döndürür.
Aramayı durdurmak için `stop`, motoru kapatmak için `quit` gönderin.

Bir UCI arayüzüne eklerken **çalıştırılacak programı Python**, argümanları
`-u -m engine`, çalışma dizinini depo kökü olarak ayarlayın.
[Kurulum, açılış kitabı ve seçenekler →](docs/USAGE.md)

<a id="ozellikler"></a>
## Motorun içinde

- **Kendi satranç tahtası:** 0x88 gösterimi, yasal hamle üretimi, rok, geçerken
  alma, dört terfi seçeneği ve artımlı Zobrist hash.
- **Arama:** iteratif derinleştirme, negamax/alpha-beta, sakinleştirme araması,
  transpozisyon tablosu, killer/history sıralaması ve seçici arama seçenekleri.
- **Değerlendirme:** materyal ve taş-kare puanları; oyun evresine göre harmanlama
  ve aynı puanı daha az toplama işlemiyle üreten paketli temel değerlendirme.
- **UCI iletişimi:** arama sırasında yanıt veren `isready`, kesilebilir arama
  ve tek seferlik `bestmove` çıktısı.
- **Açılış kitabı:** Polyglot desteği, yalnız yasal hamleler arasında ağırlıklı
  seçim. İsteğe bağlıdır; varsayılan kapalıdır.
- **Ölçüm araçları:** renk değişimli açılış çiftleri, maç/hamle kayıtları,
  PGN/JSON çıktıları, kaynak kimlikleri ve Kaggle deneyleri.

`main` üzerinde `TTTwoContexts` ve `EvalPackedBase` varsayılan açıktır.
Diğer deneysel seçenekler ve sınırlar [kullanım rehberinde](docs/USAGE.md#uci-secenekleri)
açıklanır.

<a id="olcumler"></a>
## Ölçümler ve güncel durum

**Main — paketli değerlendirme:** Aynı sabit arama işinde medyan süre **%5,73
kısaldı**; ilgili deneyde 466 doğruluk testi geçti. 100 ms/hamle ile 100 maçta
34 galibiyet, 33 beraberlik, 33 mağlubiyet alındı. Bu sonuç hız kazanımını
destekliyor; oyun gücü artışını kesinleştirmiyor.
[Yöntem ve kayıtlar →](docs/PACKED_EVAL.md)

**Deney dalı — RootMateGuard:** 500 ms/hamle ile 100 maçta **32 galibiyet,
41 beraberlik, 27 mağlubiyet (%52,5 puan)**; 498 test başarılı, iki tarafta
teknik hata yok. Kritik 100 ms konumunda mat savunması iyileşti; genel güç
artışı henüz kanıtlanmadı. **Bu özellik main'e alınmadı.**
[Sonuçlar](https://github.com/xdxddxdxd/acemi/blob/98d7a80ea08e7a8f0cf99b3d98889439110bcb82/data/ab/root-mate-guard-500ms-100games-v1/SUMMARY.md)
· [Deney açıklaması](https://github.com/xdxddxdxd/acemi/blob/codex/root-mate-guard/docs/ROOT_MATE_GUARD.md)

<details>
<summary>Önceki deneyler ve sonuçları nasıl okumalı?</summary>

- [İki TT bağlamı](docs/TT_TWO_CONTEXTS.md): önbellekte farklı beraberlik
  bağlamlarının korunması; seçenek main'de açık.
- [Süre politikası](docs/TIME_POLICY.md): `NextIterationPct=100 / 150`
  karşılaştırması; main varsayılanı 150.
- [Quiescence SEE](docs/QUIESCENCE_SEE.md): taktik hamle sıralaması deneyi;
  seçenek varsayılan kapalı.
- [Önce/sonra A/B](docs/AB_100.md) ve [sabit referans](docs/BASELINE.md):
  geçmiş geliştirme adımlarının karşılaştırılması.

Farklı deneylerin kontrol sürümleri ve koşulları farklıdır; yüzdeler doğrudan
sıralanamaz. Küçük örneklemler kesin Elo artışı göstermez. Stockfish'in
`UCI_Elo` ayarı da FIDE, Lichess veya CCRL puanının yerine geçmez. Ham kayıtlar
ve kaynak kimlikleri [data/](data/) altında korunur.

</details>

<a id="kaggle"></a>
## Kaggle ile geliştirme

Kısa kontroller PC'de; tam test paketi, tekrarlı ölçümler, yoğun analizler ve
maçlar Kaggle'da çalıştırılır. GitHub Actions ayrıca Ubuntu ve Windows üzerinde
doğruluk testleri ve benchmark duman kontrolü yapar.

1. Çalıştırmak istediğiniz deneyin notebook'unu doğru dalından Kaggle'a aktarın.
2. Internet'i açın. Sonuçları GitHub'a göndermek için `GITHUB_TOKEN` secret'ını
   Contents yazma yetkisiyle tanımlayın.
3. Deney başlığındaki kaynak, süre ve devam koşullarını kontrol edip hücreleri çalıştırın.

[Kaggle ve doğrulama rehberi](docs/USAGE.md#kaggle)
· [Ana daldaki notebook'lar](notebooks/)
· [RootMateGuard notebook'u](https://github.com/xdxddxdxd/acemi/blob/codex/root-mate-guard/notebooks/kaggle_root_mate_guard.ipynb)

<a id="belgeler"></a>
## Projeyi keşfet

- [Kullanım rehberi](docs/USAGE.md) — UCI, GUI bağlantısı, kitap, test ve maç komutları.
- [Motor](engine/) — tahta, hamle üretimi, arama ve değerlendirme.
- [Testler](tests/) ve [test rehberi](tests/README.md) — doğruluk ve regresyon kontrolleri.
- [Araçlar](tools/) ve [araç mimarisi](docs/TOOLS.md) — maç, analiz, kitap üretimi ve ölçüm.
- [Veri şeması](AGENT_GUIDE.md) ve [analiz rehberi](docs/ANALYSIS.md) — kayıtlar ve güvenli devam.
- [Sürüm geçmişi](CHANGELOG.md) — özellikler, deneyler ve geçmiş kararlar.

<details>
<summary>English summary</summary>

Acemi is a Python UCI chess engine with its own board representation, legal
move generation, search and classical evaluation. The engine core uses only
the Python standard library; analysis and test tools use python-chess and NumPy.

Run `python -u -m engine` from the repository root, or connect it to a UCI
chess GUI. Polyglot opening-book support is optional. The engine is single-threaded.
Strength changes are evaluated with reproducible tests and paired matches;
reported experimental scores are not a certified chess rating.

</details>

## Lisans

[GPL-3.0](LICENSE). `python-chess` yalnız araçlar ve testlerde kullanılır.
Açılış kitabı ve test setleri Stockfish ile üretilmiştir; Stockfish motor
dosyası bu depoda paketlenmez.
