# Snapmaker U1 Remote RFID Reader — ESP32-S3 + PN532 (I2C) + Spoolman (ESPHome)

Repo: [github.com/FizykPSX/snapmaker-rfid-esp32-s3-scanner](https://github.com/FizykPSX/snapmaker-rfid-esp32-s3-scanner)

Reads OpenSpool-format RFID tags from filament spools and sends the data to a Snapmaker U1 3D
printer over the network, with an optional [Spoolman](https://github.com/Donkie/Spoolman) lookup
for remaining weight. On the printer side,
[SnapmakerU1-Extended-Firmware](https://github.com/paxx12/SnapmakerU1-Extended-Firmware) is
required to accept the remote RFID data.

Originally forked from [wasikuss/snapmaker-u1-remote-rfid-reader](https://github.com/wasikuss/snapmaker-u1-remote-rfid-reader)
(MicroPython, ESP32-C6) and later rewritten from scratch on **ESP32-S3 + ESPHome** — see
[MIGRATION.md](MIGRATION.md) for why. This repo now contains only the ESP32-S3/
ESPHome version. Proposed back upstream as a new hardware variant:
[wasikuss/snapmaker-u1-remote-rfid-reader#4](https://github.com/wasikuss/snapmaker-u1-remote-rfid-reader/issues/4).

## Hardware variants

Both run the same ESP32-S3R8 (dual-core, 8MB PSRAM, 16MB flash) and the same application logic —
they differ only in the board, the display driver, and how you drive the UI.

| | **A — Touch** | **B — Buttons** (budget) |
|---|---|---|
| Board | [Waveshare ESP32-S3-Touch-LCD-2](https://www.waveshare.com/wiki/ESP32-S3-Touch-LCD-2) | [Waveshare ESP32-S3-LCD-1.47B](https://www.waveshare.com/wiki/ESP32-S3-LCD-1.47B) |
| Display | ST7789T3 240×320 IPS, SPI | ST7789 172×320, SPI |
| Input | CST816D capacitive touch | 3 soldered tact switches |
| Battery | MX1.25 + on-board charger | pads, no charger |
| Config | [`esphome/snapmaker-rfid-touch2.yaml`](esphome/snapmaker-rfid-touch2.yaml) | [`esphome/snapmaker-rfid-s3.yaml`](esphome/snapmaker-rfid-s3.yaml) |

Variant A is the one to build if you're starting now: no buttons to solder, bigger screen, and
battery charging is handled on-board. Variant B stays supported as the cheaper option and needs
no touch calibration.

Neither board is mechanically tough. The 1.47B's display sits on a folded FPC ribbon and cracks if
the board is press-fitted into an enclosure — screw it down with clearance instead. See
[BOM.md](BOM.md) for the full parts list.

## Software

[ESPHome](https://esphome.io/), `esp-idf` framework. All device logic lives in one YAML per
variant — [`esphome/snapmaker-rfid-touch2.yaml`](esphome/snapmaker-rfid-touch2.yaml) (A) or
[`esphome/snapmaker-rfid-s3.yaml`](esphome/snapmaker-rfid-s3.yaml) (B). The RFID, Spoolman and
printer logic is identical between them; only the display, input and I2C blocks differ.

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
3. Build and flash over USB — `esphome run esphome/snapmaker-rfid-touch2.yaml` for variant A, or
   `esphome run esphome/snapmaker-rfid-s3.yaml` for variant B.
4. On the device's local web panel (or via Home Assistant), set the **Printer Host** and
   **Spoolman Host** text fields to your printer's/Spoolman's IP. Leave **Spoolman Host** blank to
   disable the Spoolman lookup.

### Wiring — variant A (Touch-LCD-2)

| Signal | GPIO | Notes |
|---|---|---|
| LCD SCK / MOSI | 39 / 38 | on-board, fixed |
| LCD CS / DC / RST / BL | 45 / 42 / 0 / 1 | on-board. **GPIO0 is shared with the BOOT button** |
| Touch + IMU I2C (SDA / SCL) | 48 / 47 | on-board, pulled up. CST816D 0x15, QMI8658 0x6B |
| Touch INT | 46 | on-board |
| PN532 SDA / SCL | GPIO18 / GPIO17 | own I2C bus, 3.3V logic only |
| Battery ADC | 5 | on-board divider, unused by this config |
| USB (native) | 19 / 20 | do not reuse |

PN532 gets a second I2C bus rather than sharing the on-board one. Its address doesn't clash, but
it stretches the clock hard enough to stall a shared bus — and touch is the only input here, so a
wedged bus would mean no UI at all. GPIO17/18 are free on the 22-pin header.

Only four wires leave the board: PN532 SDA, SCL, 3V3, GND. The bistable power switch goes in the
battery **"+"** lead and is the single physical control on the device.

### Wiring — variant B (LCD-1.47B)

| Signal | GPIO | Notes |
|---|---|---|
| LCD SCK/MOSI/CS/DC/RST/BL | 40 / 45 / 42 / 41 / 39 / 46 | on-board, fixed |
| PN532 SDA / SCL | GPIO8 / GPIO9 | I2C, 3.3V logic only |
| Button Up | GPIO4 | INPUT_PULLUP, other leg to GND |
| Button Down | GPIO5 | INPUT_PULLUP, other leg to GND |
| Button OK | GPIO6 | INPUT_PULLUP, other leg to GND |

GPIO4/5/6/8/9 were picked because they're free on this board and not strapping/SDIO/USB-JTAG pins.

## Interface

### Variant A — touch

Tap a row, that's it. No cursor to move.

- **Tap CH1–CH4**: arm that channel for a 10s scan, or clear it if it already has data.
- **Tap "Send Data"**: send every channel that has data to the printer.

### Variant B — buttons

- **Up / Down**: move the cursor (CH1 → CH2 → CH3 → CH4 → Send Data → CH1 ...).
- **OK**: on a channel — arm it for a 10s scan, or clear it if it already has data; on "Send
  Data" — send every channel that has data to the printer.

On both, after a successful scan the channel line shows brand/type and a color swatch; the detail
panel below shows the tag UID and the Spoolman remaining weight (if matched).

## Known quirks (found the hard way, worth keeping in mind)

- **`CARD_UID` in the printer payload must be an array of byte integers, not a hyphenated hex
  string.** The printer firmware does `[int(b) for b in CARD_UID]`, so `"04-E5-43-4D-C7-2A-81"`
  raises `invalid literal for int(): '-'`; the correct format is `[4, 229, 67, 77, 199, 42, 129]`.
- **WiFi power-save is disabled** (`power_save_mode: none`). This board is dual-core so it doesn't
  suffer the single-core WiFi/SPI contention the old ESP32-C6 MicroPython build had, but leaving
  power-save off avoids radio-doze connect flakiness regardless.
- **Variant A: the touch panel is not rotated with the display.** The display runs `rotation: 90°`
  to get a 320×240 landscape frame; the CST816D still reports in its native 240×320 portrait
  frame, so the `touchscreen: transform:` block does the mapping by hand. If taps land on the
  wrong row on first boot, flip `mirror_x` / `mirror_y` there — that's the only calibration knob
  this build needs.
- **Variant A: touch row geometry is duplicated.** The `y_min`/`y_max` of the five touchscreen
  binary sensors must match the `ROW_H` / `ROW_Y0` / `SEND_Y` constants in the display lambda.
  Change one, change the other.
- **Variant A: `invert_colors: true`.** ST7789 panels are split on this. If the screen comes up as
  a photo negative, set it to `false`.

## TODO

- [ ] Design and print an enclosure — screws + ~0.5mm clearance, not a press fit
- [ ] Wire up the LiPo battery + bistable power switch (see [BOM.md](BOM.md))
- [ ] Variant A: expose battery level (GPIO5 has an on-board divider; the ratio is undocumented,
      so it needs measuring against a known cell voltage before it's worth showing)
- [ ] Variant B: solder buttons permanently (currently loose wires on the bench)

## License

[MIT](LICENSE), same as the upstream project.
