# Snapmaker U1 Remote RFID Reader — ESP32-C6-LCD-1.47 + PN532 (I2C) + Spoolman

Fork of [wasikuss/snapmaker-u1-remote-rfid-reader](https://github.com/wasikuss/snapmaker-u1-remote-rfid-reader) ported to different hardware, plus a Spoolman integration. Reads OpenSpool-format RFID tags from filament spools and sends the data to a Snapmaker U1 3D printer over the network. On the printer side, [SnapmakerU1-Extended-Firmware](https://github.com/paxx12/SnapmakerU1-Extended-Firmware) is required to accept the remote RFID data.

## What's different from upstream

- **Board**: [Waveshare ESP32-C6-LCD-1.47](https://www.waveshare.com/wiki/ESP32-C6-LCD-1.47) (ST7789 172x320 color LCD, wired on-board) instead of ESP32-C3 + mono OLED.
- **RFID**: same [PN532](https://github.com/snwng/MPY_PN532) driver, over I2C, just different pins.
- **Spoolman**: after a successful scan, looks up the spool in [Spoolman](https://github.com/Donkie/Spoolman) (by the tag's own `spool_id` field if present, else by UID) and shows remaining weight.
- **Display**: full custom `LCDDisplay` driver (`display.py` + vendored `st7789py.py`) — color, landscape, 2x-scaled title/menu text, a real color swatch for the filament color.

## Hardware

- Waveshare ESP32-C6-LCD-1.47(-M) — chip confirmed on this unit: **ESP32-C6FH8**, 8MB flash.
- PN532 NFC/RFID V3 module (I2C/SPI/HSU selectable via 2 DIP switches) — **must be set to I2C**: switch 1 = ON, switch 2 = OFF (per the silkscreen table on the module).
- 2x momentary push button (tact switch, 2-pin) — **not yet soldered**, currently only bench-tested.

### Wiring

| Signal | GPIO | Notes |
|---|---|---|
| LCD (all fixed, on-board) | SCK 7, MOSI 6, CS 14, DC 15, RST 21, BL 22 | not user-wired, built into the board |
| PN532 SDA | GPIO23 | 3.3V logic — do **not** power the module from 5V |
| PN532 SCL | GPIO20 | |
| PN532 VCC | 3V3 | |
| PN532 GND | GND | |
| Button 1 (NEXT) | GPIO18 | other leg to GND, internal pull-up in code |
| Button 2 (ACTIVATE) | GPIO19 | other leg to GND, internal pull-up in code |

GPIO18/19/20/23 were picked because they're free on this board: not strapping pins (4, 5, 8, 9, 15 are), not used by the on-board LCD/microSD/RGB LED, not USB-Serial-JTAG (12, 13).

## Software

- **MicroPython**: `ESP32_GENERIC_C6` firmware, v1.28.0+ (from [micropython.org](https://micropython.org/download/ESP32_GENERIC_C6/)).
- Everything under `src/` gets uploaded to the device as-is (e.g. via `mpremote cp <file> :<file>` or the webrepl upload page from `boot.py`).
- `st7789py.py` and `PN532.py` are vendored third-party drivers, uploaded like any other file — no custom firmware build needed.

### Setup

1. Flash MicroPython:
   ```
   esptool erase-flash
   esptool --baud 460800 write-flash 0x0 ESP32_GENERIC_C6-*.bin
   ```
2. Edit `src/config.json`: WiFi is set in `boot.py` (SSID/password), printer/Spoolman hosts in `config.json`. Set `"spoolman": {"enabled": false}` if you don't have a Spoolman instance.
3. Upload every file in `src/` to the device root (`mpremote connect /dev/ttyACM0 fs cp <file> :<file>`, or webrepl once `boot.py` is on the device and WiFi connects).
4. Power-cycle. `main.py` runs automatically on boot.

### Spoolman setup (optional)

- The tag's own `spool_id` field (written by whatever tool wrote your tags) is tried first — no Spoolman-side setup needed if your tags have it.
- As a fallback, spools can be matched by RFID UID: add an **Extra Field** named `card_uids` to Spoolman (Settings → Extra fields → Spool) and put the tag's UID hex in it. The UID is shown on-screen (and printed over serial) after every scan.

## Interface

- **Button 1 (GPIO18)**: short press = move cursor (CH1 → CH2 → CH3 → CH4 → Send Data → CH1...).
- **Button 2 (GPIO19)**: activate — on a channel, starts a scan (or clears it if it already has data); on "Send Data", sends every channel with data to the printer.
- **Both together**: soft reset.

After a successful scan, the detail panel shows brand/type/subtype, a color swatch, the tag's UID, and the Spoolman remaining weight (if matched).

## Known quirks (found the hard way, worth keeping in mind)

- **SPI must be Mode 0** (`polarity=0, phase=0`). The upstream `st7789py_mpy` README example uses `polarity=1`, which renders a blank black screen on this panel.
- **`framebuf.RGB565` is little-endian**, the panel wants big-endian pixel data over SPI — `LCDDisplay.color565()` pre-swaps the bytes so `blit_buffer()` can send the framebuffer unmodified.
- **A single `blit_buffer()` spanning the full 320px width corrupts the left column and bottom row.** Root cause not fully pinned down (possibly a CASET/RAMWR quirk of this specific ST7789 unit); reliably avoided by sending the frame in ≤80px-wide vertical strips (`LCDDisplay.STRIP_WIDTH`).
- **WiFi and continuous SPI/LCD activity don't coexist well on this single-core chip.** Redrawing the whole screen unconditionally every ~30ms (a common MicroPython UI pattern) made `socket.connect()` to Spoolman fail intermittently but often (sometimes on every retry). Fixed by throttling redraws to 150ms / only-on-input instead of every loop iteration — see `REDRAW_INTERVAL_MS` in `main.py`. If you extend the UI, keep this in mind before adding more per-frame drawing work.
- Large, frequently-reallocated buffers (a first attempt at multi-buffer strip rendering used 4 separate ~27KB buffers, and an earlier version of the 2x-scaled text allocated a fresh scratch buffer per draw call) fragment the heap enough on their own to break WiFi even without any of the above. `LCDDisplay` now allocates its buffers once at init and reuses them.

## TODO

- [ ] Solder buttons permanently (currently loose wires on the bench)
- [ ] Design and print an enclosure
- [ ] Populate `boot.py`'s WiFi retry/offline behavior if it turns out to matter in practice
