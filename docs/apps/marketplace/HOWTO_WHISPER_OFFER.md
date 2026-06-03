# How to Use aitbc3's Whisper Transcription Service

aitbc3 offers GPU-accelerated speech-to-text (Whisper base, CUDA) at **0.02 AIT per audio minute**.

---

## 1. Discover the offer

```bash
# List all software offers on the marketplace
aitbc market list

# Or query the plugin registry directly
curl http://localhost:8109/plugins/whisper-base
curl http://localhost:8109/plugins/whisper-base/offer   # latest offer_id only
```

Latest confirmed offer on hub:
```
offer_id : sw_offer_20260603125540_49d92c3c
service  : whisper / base
price    : 0.02 AIT/per_audio_min
provider : aitbc1c10f0e4fb1d162bb27af88a698b8c2e6e39a844f
```

---

## 2. Transcribe an audio file

```bash
aitbc market transcribe sw_offer_20260603125540_49d92c3c /path/to/audio.mp3
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--language en` | auto-detect | Force language (faster) |
| `--task translate` | transcribe | Translate to English |
| `--output-format srt` | text | Output as SRT subtitles |
| `--output-format json` | text | Full JSON with timestamps |

### Examples

```bash
# Basic transcription
aitbc market transcribe sw_offer_20260603125540_49d92c3c interview.mp3

# Force German, output SRT subtitles
aitbc market transcribe sw_offer_20260603125540_49d92c3c podcast.mp3 \
  --language de --output-format srt

# Translate Spanish audio to English
aitbc market transcribe sw_offer_20260603125540_49d92c3c meeting.mp4 \
  --task translate

# Full JSON with segment timestamps
aitbc market transcribe sw_offer_20260603125540_49d92c3c lecture.wav \
  --output-format json
```

---

## 3. What happens under the hood

1. `ffprobe` measures audio duration → estimates cost
2. Escrow locked on aitbc3's blockchain node (buyer's funds held)
3. Audio uploaded to `http://aitbc3:8110/transcribe` (GPU inference)
4. Transcript returned — actual audio duration measured
5. Metered escrow release: `actual_minutes × 0.02 AIT` → provider wallet
6. On-chain TX confirms payment (visible on hub chain)

---

## 4. Always get the latest offer_id

Offers are re-published on node restart. Always resolve the current one:

```bash
# From plugin registry (live hub chain lookup)
curl http://localhost:8109/plugins/whisper-base/offer

# Or from market list
aitbc market list | grep whisper
```

---

## 5. What to prompt the hub

Tell the hub agent:

> "Use `aitbc market transcribe` with offer ID `sw_offer_20260603125540_49d92c3c` to transcribe my audio file. The provider is aitbc3 (`aitbc1c10f0e4fb1d162bb27af88a698b8c2e6e39a844f`), running Whisper base on an RTX 4060 Ti. Price is 0.02 AIT per audio minute. Payment is metered via blockchain escrow and released automatically after transcription."

The hub can also discover the offer programmatically:
```
GET https://hub.aitbc.bubuit.net/v1/plugin/plugins?service_type=whisper
```
