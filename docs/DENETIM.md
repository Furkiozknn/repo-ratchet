# Denetim: repo-ratchet ilk kullanım (30 Eylül 2026)

Yöntem: taze klon → temiz venv → README'deki her komut. Windows 11, Python 3.12, `uv` 0.x; ağ açık.
Ham çıktılar: `D:\Claude Projeleri\proje-yenileme\kanit\repo-ratchet\{once,sonra}\komutlar.txt`.

## Ölçümler

| Ne | Sonuç |
|---|---|
| `git clone` + `python -m venv` + `pip install .` (boş venv, 0 bağımlılık) | 23,3 s (klon 0,7 + kurulum 22,6) |
| `pip install git+https://github.com/Furkiozknn/repo-ratchet` (boş venv) | 24,3 s |
| `uvx --from git+... ratchet survey --path <klon>` (boş önbellek, tek komut) | **15,3 s**, ilk sonuç dahil |
| `ratchet queue` (klondaki `durum/` ile), kurulu araç | ilk sonuç 0,97 s |
| `ratchet discover Furkiozknn` | çalışıyor: 28 depo, 27 aralıkta |
| Test | 163 geçti (denetim başı) → 167 geçti, ~10 s |

README'nin sayıları: "163 tests" ve `project-meta.json` 163'ü koşudan geliyordu; 167 oldu (README güncellendi;
`project-meta.json` sayısı CI logunda `167 passed` görülünce değiştirilecek - kaynağı olmayan sayı yazılmaz).
"27 repositories / 106 checks" kayıtlardan (`kayitlar/`) geliyor, bu turda dokunulmadı.

## Bulgular

| # | Bulgu | Durum |
|---|---|---|
| 1 | README ilk ekranı: bir reel, sonra iki paragraf; tek komutla ilk sonuç yok (kurulum = klon + venv + pip + 3 komut). Reel/GIF'in üreticisi depoda yok. | Düzeltildi: tek cümle + tek `uvx` komutu + üreticisi depoda olan demo. Eski `docs/reel/` kaldırıldı (git geçmişinde). |
| 2 | `ratchet survey --path YOK` → `ratchet: C:\...\YOK` (sebep yok). `ratchet check YOK` → "no ratchet.toml..." (yanıltıcı: klasör yok). | Düzeltildi: "is not a directory" (çıkış 2). |
| 3 | `ratchet record ... --verifications bozuk.json` → **Python traceback, çıkış 1** (1 = "bir check başarısız" demek; sözleşmeyi bozuyor). Eksik alanlı JSON'da `TypeError` traceback'i. | Düzeltildi: `refused: ... is not a file from ratchet check --out (...)`, çıkış 2. |
| 4 | `ratchet queue` `durum/` yoksa (kurulumdan sonra başka klasörde) "no surveys yet - run `ratchet survey`" - yeni kullanıcı `survey`'in 27 depo klonlayacağını bilmez. | Düzeltildi: hangi dosyaya baktığını, `survey --path .` ve `discover` yolunu, `--state`'i söyler. |
| 5 | `ratchet --help` çıkış kodlarını ve akışı söylemiyor (yalnız README'de). | Düzeltildi: epilog. |
| 6 | Rapor: "1 repositories", "1 checks recorded". | Düzeltildi (tekil). |
| 7 | `ratchet check .` Windows'ta `python3` uv'nin Python'una çözülüyor, venv'e değil; pytest yoksa `No module named pytest` ile çıkış 1. README zaten belgeliyor. | Belgeli, kod değişmedi (fence PATH'ten çözüyor; tasarım gereği). |
| 8 | `ratchet survey` (argümansız) `durum/depolar.json` varsa 27 depoyu ağdan klonlar; hata değil ama sürpriz. | Belgeli ("A whole round"); değişmedi. |
| 9 | `queue --round 99` var olmayan turu sessizce "99 - 27 waiting" diye gösterir. | Değişmedi (kayıt sözleşmesine dokunmamak için); bilinen kalan. |

Hata mesajı sözleşmesi korundu: `refused:` = 2, `check` başarısız = 1, `queue --next` boş = 1, çalışamadı = 2. Mevcut 163 test gevşetilmedi; 4 yeni test eklendi.

## Ekosistem denetimi (#19)

Bu depoya ait açık bulgu tek: test sayısı `project-meta.json` 163 ↔ `meta-source.json` 131 (meta-source ayrışması). Talimat gereği kapatılmadı.
