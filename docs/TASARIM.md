# Tasarım: repo-ratchet ilk kullanım ve README (30 Eylül 2026)

## Hedef

İlk dakikada: ne yaptığını tek cümlede anlamak, tek komutla ilk ölçümü almak, yanlış yazınca doğrusunu görmek.
Çekirdek (üç kayıt kuralı, fence, çıkış kodları, `durum/`/`kayitlar/` biçimi) değişmedi; sürüm 0.2.0 kaldı.

## Önce / sonra

| Konu | Önce | Sonra |
|---|---|---|
| README ilk ekranı | banner, sesli reel, iki paragraf; kurulum = klon + venv + pip | banner, tek cümle, tek `uvx` komutu (ölçülmüş 15 s), gerçek çıktılı demo, "ne zaman kullanılır / kullanılmaz" |
| Demo | üreticisi depoda olmayan reel (GIF+MP4) | `docs/demo/kaydet.py` komutları geçici git deposunda gerçekten koşar → `demo.json`; `uret.py` onu çizer (gif/mp4) |
| Yanlış yol | `ratchet: C:\...` / yanıltıcı "no manifest" | "is not a directory" |
| Bozuk `--verifications` | traceback, çıkış 1 | `refused: ...`, çıkış 2 |
| `queue` boşken | "run `ratchet survey`" | hangi dosya, `survey --path .`, `discover`, `--state` |
| `--help` | komut listesi | + akış ve çıkış kodları |
| Test | 163 | 167 |

## CLI akışı

```
tek komut   uvx --from git+https://github.com/Furkiozknn/repo-ratchet ratchet survey --path .
tur         discover <owner> -> survey -> queue -> check <repo> --out v.json -> record ... --verifications v.json -> report
çıkış       0 tamam | 1 bir check başarısız (ya da queue --next boş) | 2 reddedildi / çalışamadı
```

## Görsel dil

FRK-OS, video sisteminden (`sosyal/uret/tema.mjs` akis: zemin `#0e0d0b`, vurgu `#ffc21a`, yazı `#f1ece2`); demo bunları aynen kullanır,
hata satırı için `#ff7a6b`, sönük metin `#9a958b`. Yazı tipi JetBrains Mono (OFL, `docs/demo/fonts/`, yerel kopya; indirme yok).
Kontrast (siyah zemin üstünde, hesaplandı): krem 16,5:1; sarı 12,0:1; sönük 6,5:1; kırmızı 7,6:1 - hepsi ≥ 4,5:1.

## Kayıt

`D:\Claude Projeleri\sosyal\medya\projeler\repo-ratchet\{komutlar.txt,terminal.mp4}` (1080x1920, H.264 yuv420p, faststart, sessiz).
