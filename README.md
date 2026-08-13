# Snapmaker U1 Remote RFID Reader — ESP32-S3 + PN532/RC522 + Spoolman (ESPHome)

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

| | **A — Touch, PN532** | **B — Buttons** (budget) | **C — Touch, RC522** |
|---|---|---|---|
| Board | [Waveshare ESP32-S3-Touch-LCD-2](https://www.waveshare.com/wiki/ESP32-S3-Touch-LCD-2) | [Waveshare ESP32-S3-LCD-1.47B](https://www.waveshare.com/wiki/ESP32-S3-LCD-1.47B) | same as A |
| Display | ST7789T3 240×320 IPS, SPI | ST7789 172×320, SPI | same as A |
| Input | CST816D capacitive touch | 3 soldered tact switches | same as A |
| Battery | MX1.25 + on-board charger | pads, no charger | same as A |
| RFID reader | PN532, I2C | PN532, I2C | RC522, SPI |
| Config | [`esphome/snapmaker-rfid-touch2.yaml`](esphome/snapmaker-rfid-touch2.yaml) | [`esphome/snapmaker-rfid-s3.yaml`](esphome/snapmaker-rfid-s3.yaml) | [`esphome/snapmaker-rfid-touch2-rc522.yaml`](esphome/snapmaker-rfid-touch2-rc522.yaml) |

Variant A is the one to build if you're starting now: no buttons to solder, bigger screen, and
battery charging is handled on-board. Variant B stays supported as the cheaper option and needs
no touch calibration. Variant C is the same board as A with the reader swapped for RC522 — mainly
useful if you dislike the common PN532 breakout's PCB loop antenna (traced around the board edge,
same layer as the chip) and want a module with a physically separate antenna instead.

**Variant A is confirmed working end-to-end on real hardware**: touch input, PN532 scan, Spoolman
lookup, and the printer POST all round-trip correctly. **Variant C is untested on real hardware** —
see the "RC522 NDEF" note under Known quirks below before building it.

Neither board is mechanically tough. The 1.47B's display sits on a folded FPC ribbon and cracks if
the board is press-fitted into an enclosure — screw it down with clearance instead. See
[BOM.md](BOM.md) for the full parts list.

## Software

[ESPHome](https://esphome.io/), `esp-idf` framework. All device logic lives in one YAML per
variant — [`esphome/snapmaker-rfid-touch2.yaml`](esphome/snapmaker-rfid-touch2.yaml) (A),
[`esphome/snapmaker-rfid-s3.yaml`](esphome/snapmaker-rfid-s3.yaml) (B), or
[`esphome/snapmaker-rfid-touch2-rc522.yaml`](esphome/snapmaker-rfid-touch2-rc522.yaml) (C). The
RFID, Spoolman and printer logic is identical across all three; only the display, input and
RFID-reader blocks differ.

- **`pn532_i2c`** (A, B) — built-in ESPHome component handles Mifare/NDEF parsing; no custom RFID
  driver code needed.
- **`rc522_ndef`** (C) — custom `external_component` in
  [`esphome/components/rc522_ndef/`](esphome/components/rc522_ndef/). Stock ESPHome `rc522`/
  `rc522_spi` only expose the tag UID, not its NDEF content, so it can't read OpenSpool tags
  as-is. This subclasses the driver and bolts on a Type 2 Tag NDEF read (same
  `PICC_CMD_MF_READ`/page-read approach the `pn532` component uses for MIFARE
  Ultralight/NTAG), exposing the same `x` (uid) / `tag` (`nfc::NfcTag`) shape in `on_tag` that
  `pn532` does — the touch UI's `on_tag` lambda is unchanged between variant A and C. See the
  comment at the top of `rc522_ndef.h` for how it's wired into the base driver's state machine.
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

### Wiring — variant C (Touch-LCD-2, RC522)

Same board as variant A. RC522 gets its **own** SPI bus (`spi_rc522` in the YAML), not a shared one
with the display: LCD_SCLK/LCD_MOSI (GPIO39/38) only run to the display and the on-board SD card
slot internally — per Waveshare's schematic they're never brought out to the 22-pin header, so
there's no pad to tap into (confirmed against the real board, not just the schematic).

| Signal | GPIO | Notes |
|---|---|---|
| LCD SCK / MOSI / CS / DC / RST / BL | 39 / 38 / 45 / 42 / 0 / 1 | on-board, fixed, own bus. **GPIO0 is shared with the BOOT button** |
| Touch + IMU I2C (SDA / SCL) | 48 / 47 | on-board, pulled up. CST816D 0x15, QMI8658 0x6B |
| Touch INT | 46 | on-board |
| RC522 SCK | GPIO2 | header pad nominally CAM_D7 — free, no camera module populated |
| RC522 MOSI | GPIO4 | header pad nominally CAM_HREF — free, same reason |
| RC522 MISO | GPIO18 | free header pad, same one variant A used for PN532 SDA |
| RC522 SDA (= CS) | GPIO17 | free header pad, same one variant A used for PN532 SCL (nominally CAM_PWDN) |
| RC522 RST | leave unconnected | module has an on-board ~3.3kΩ pull-up to VCC, measured on the actual unit — no GPIO needed |
| RC522 IRQ | leave unconnected | unused |
| Battery ADC | 5 | on-board divider, unused by this config |
| USB (native) | 19 / 20 | do not reuse |

Six wires leave the board: RC522 3V3, GND, SCK, MOSI, MISO, SDA. GPIO2/4/17/18 are all "camera"
pins on Waveshare's silkscreen/schematic (CAM_D7, CAM_HREF, CAM_PWDN, and an unlabeled camera-bus
pin) — free to reuse since this board has no camera module attached.

## Interface

### Variant A — touch

The top ~70% of the landscape frame (y=0–168) is the menu (CH1–CH4, Send Data) and is
display-only — tapping it does nothing. The bottom 30% (y=168–240) is an invisible button strip
split left/right at the midpoint; nothing is drawn there.

- **Bottom-left**: cycle the highlighted row, CH1 → CH2 → CH3 → CH4 → Send Data → CH1 ...
- **Bottom-right**: act on the highlighted row — arm it for a 10s scan, clear it if it already has
  data, or (on "Send Data") send every channel that has data to the printer.

Same select-then-confirm pattern as variant B's Up/Down/OK below, just moved onto two touch zones
instead of three physical buttons — not a tap-any-row design.

### Variant B — buttons

- **Up / Down**: move the cursor (CH1 → CH2 → CH3 → CH4 → Send Data → CH1 ...).
- **OK**: on a channel — arm it for a 10s scan, or clear it if it already has data; on "Send
  Data" — send every channel that has data to the printer.

On both, after a successful scan the channel line shows brand/type and a color swatch. Variant B
also shows a detail panel below with the tag UID and the Spoolman remaining weight; variant A has
no room for that once the button strip takes the bottom 30%, so it appends the Spoolman result
inline instead (`...` while checking, `n/a` if no match, `NNNg` if found) and only logs the UID.

## Known quirks (found the hard way, worth keeping in mind)

- **`CARD_UID` in the printer payload must be an array of byte integers, not a hyphenated hex
  string.** The printer firmware does `[int(b) for b in CARD_UID]`, so `"04-E5-43-4D-C7-2A-81"`
  raises `invalid literal for int(): '-'`; the correct format is `[4, 229, 67, 77, 199, 42, 129]`.
- **WiFi power-save is disabled** (`power_save_mode: none`). This board is dual-core so it doesn't
  suffer the single-core WiFi/SPI contention the old ESP32-C6 MicroPython build had, but leaving
  power-save off avoids radio-doze connect flakiness regardless.
- **Variant A: the touch panel is not rotated with the display.** The display runs `rotation: 90°`
  to get a 320×240 landscape frame; the CST816D still reports in its native 240×320 portrait
  frame, so the `touchscreen: transform:` block does the mapping by hand. Confirmed on real
  hardware: `swap_xy: true`, `mirror_x: false`, `mirror_y: true`. Found by logging raw
  `touch.x`/`touch.y` from an `on_touch:` lambda and tapping known screen edges until the numbers
  lined up — worth doing again if a different physical unit comes up mirrored.
- **Variant A: two colour knobs, not one.** `invert_colors: true` — ST7789 panels are split on
  this, so if the screen comes up as a photo negative, set it to `false`. Separately, the
  `ST7789V` model defaults to `color_order: BGR`; if red and blue are swapped (the CH colour
  swatch is the giveaway) add `color_order: rgb`. A negative image and swapped channels are
  different faults with different fixes — check which one you actually have before changing both.
- **Variant A: battery ADC divider ratio confirmed at ~3.078:1.** GPIO5's on-board divider ratio
  isn't documented by Waveshare. Measured on real hardware with USB disconnected (charging skews
  the reading): a multimeter at the battery connector read 3.961V while the raw ADC read 1.287V.
  Close enough to a clean 3:1 divider to just be one, plus resistor/ADC tolerance. The displayed
  battery percentage is a straight-line 3.3–4.2V map, not a real LiPo discharge curve — good enough
  for "roughly how full", not for a precise reading.
- **Variant C: RC522 NDEF support is a custom, untested `external_component`.** Stock ESPHome
  `rc522`/`rc522_spi` only read the tag UID — no NDEF, unlike `pn532`. `rc522_ndef` (see Software
  above) bolts that on by reimplementing the Type 2 Tag page-read/TLV-locate logic against RC522's
  raw SPI registers. It compiles and links cleanly but **has not been run against a real RC522 or
  a real tag** — variant A's touch transform and battery divider both needed real-hardware
  correction despite looking right on paper, so budget for the same here. Debugging entry points:
  `logger:` is already enabled, and the component logs at `TAG = "rc522_ndef"` — bump to `DEBUG`/
  `VERBOSE` in the `logger:` block to see per-page read attempts if a tag scans but never reports
  NDEF data (`tag.has_ndef_message()` false, "Channel N: tag ... has no NDEF message" in the
  printer log). Likely failure points if it doesn't work first try: wrong `cs_pin`/wiring, an
  RC522 module needing its RST pin actively toggled rather than tied high, or the raw MIFARE Read
  (`0x30`) CRC/timing not matching what a particular RC522 clone expects.

## TODO

- [ ] Design and print an enclosure — screws + ~0.5mm clearance, not a press fit
- [ ] Wire up the LiPo battery + bistable power switch (see [BOM.md](BOM.md))
- [ ] Variant B: solder buttons permanently (currently loose wires on the bench)
- [ ] Variant C: wire up RC522 and confirm `rc522_ndef` actually reads NDEF on real hardware

## License

[MIT](LICENSE), same as the upstream project.
