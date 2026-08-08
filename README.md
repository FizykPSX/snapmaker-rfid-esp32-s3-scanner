# Snapmaker U1 Remote RFID Reader — ESP32-S3 + PN532 (I2C) + Spoolman (ESPHome)

Repo: [github.com/FizykPSX/snapmaker-rfid-esp32-s3-scanner](https://github.com/FizykPSX/snapmaker-rfid-esp32-s3-scanner)

Reads OpenSpool-format RFID tags from filament spools and sends the data to a Snapmaker U1 3D
printer over the network, with an optional [Spoolman](https://github.com/Donkie/Spoolman) lookup
for remaining weight. On the printer side,
[SnapmakerU1-Extended-Firmware](https://github.com/paxx12/SnapmakerU1-Extended-Firmware) is
required to accept the remote RFID data.

Originally forked from [wasikuss/snapmaker-u1-remote-rfid-reader](https://github.com/wasikuss/snapmaker-u1-remote-rfid-reader)
(MicroPython, ESP32-C6) and later rewritten from scratch on **ESP32-S3 + ESPHome** — see
[MIGRATION-S3-TOUCH.md](MIGRATION-S3-TOUCH.md) for why. This repo now contains only the ESP32-S3/
ESPHome version.

## Hardware

Board: [Waveshare ESP32-S3-LCD-1.47B](https://www.waveshare.com/wiki/ESP32-S3-LCD-1.47B) —
ESP32-S3R8 (dual-core, 8MB PSRAM, 16MB flash), ST7789 172×320 color LCD on-board. No touch
controller on this variant — UI runs on 3 physical buttons instead.

See [BOM.md](BOM.md) for the full parts list and wiring.

## Software

[ESPHome](https://esphome.io/), `esp-idf` framework. All device logic lives in
[`esphome/snapmaker-rfid-s3.yaml`](esphome/snapmaker-rfid-s3.yaml).

- **`pn532_i2c`** — built-in ESPHome component handles Mifare/NDEF parsing; no custom RFID driver
  code needed.
- **WiFi** with captive portal + fallback AP, plus a local web panel (`web_server: local: true`)
  to set the printer/Spoolman host IPs at runtime without recompiling.
- **Spoolman lookup**: tries the tag's own `spool_id` field first, falls back to matching by RFID
  UID against a Spoolman **Extra Field** named `card_uids` (Settings → Extra fields → Spool).
- **Printer payload**: `POST /printer/filament_detect/set` with brand/type/color/temps and the
  tag UID as a byte array (see "Known quirks" below).

### Setup

1. Install [ESPHome](https://esphome.io/) (CLI or the Home Assistant add-on).
2. `cp esphome/secrets.yaml.example esphome/secrets.yaml` and fill in WiFi SSID/password, an API
   encryption key (`openssl rand -base64 32`), an OTA password (`openssl rand -hex 16`), and a
   fallback AP password.
3. `esphome run esphome/snapmaker-rfid-s3.yaml` to build and flash over USB.
4. On the device's local web panel (or via Home Assistant), set the **Printer Host** and
   **Spoolman Host** text fields to your printer's/Spoolman's IP. Leave **Spoolman Host** blank to
   disable the Spoolman lookup.

### Wiring

| Signal | GPIO | Notes |
|---|---|---|
| LCD SCK/MOSI/CS/DC/RST/BL | 40 / 45 / 42 / 41 / 39 / 46 | on-board, fixed |
| PN532 SDA / SCL | GPIO8 / GPIO9 | I2C, 3.3V logic only |
| Button Up | GPIO4 | INPUT_PULLUP, other leg to GND |
| Button Down | GPIO5 | INPUT_PULLUP, other leg to GND |
| Button OK | GPIO6 | INPUT_PULLUP, other leg to GND |

GPIO4/5/6/8/9 were picked because they're free on this board and not strapping/SDIO/USB-JTAG pins.

## Interface

- **Up / Down**: move the cursor (CH1 → CH2 → CH3 → CH4 → Send Data → CH1 ...).
- **OK**: on a channel — arm it for a 10s scan, or clear it if it already has data; on "Send
  Data" — send every channel that has data to the printer.

After a successful scan, the channel line shows brand/type and a color swatch; the detail panel
below shows the tag UID and the Spoolman remaining weight (if matched).

## Known quirks (found the hard way, worth keeping in mind)

- **`CARD_UID` in the printer payload must be an array of byte integers, not a hyphenated hex
  string.** The printer firmware does `[int(b) for b in CARD_UID]`, so `"04-E5-43-4D-C7-2A-81"`
  raises `invalid literal for int(): '-'`; the correct format is `[4, 229, 67, 77, 199, 42, 129]`.
- **WiFi power-save is disabled** (`power_save_mode: none`). This board is dual-core so it doesn't
  suffer the single-core WiFi/SPI contention the old ESP32-C6 MicroPython build had, but leaving
  power-save off avoids radio-doze connect flakiness regardless.

## TODO

- [ ] Solder buttons permanently (currently loose wires on the bench)
- [ ] Design and print an enclosure
- [ ] Wire up the LiPo battery + bistable power switch (see [BOM.md](BOM.md))
