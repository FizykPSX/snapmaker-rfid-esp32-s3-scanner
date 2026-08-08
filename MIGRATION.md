# Migration history: ESP32-C6-LCD-1.47 (MicroPython) → Waveshare ESP32-S3-LCD-1.47B (ESPHome)

**Board note:** a touch-capable board (Waveshare ESP32-S3-Touch-LCD-2, CST816D touch, 2" 240×320
screen) was originally considered as the migration target and is referenced below as such. The
board actually used is the **Waveshare ESP32-S3-LCD-1.47B**, which has **no touch controller** —
the UI runs on 3 physical buttons instead, same as the old ESP32-C6 board. The screen is also the
same size, **1.47" 172×320**, not the 2" 240×320 of the touch board. The reasoning below (dual-core
→ end of WiFi/SPI contention, ESPHome instead of hand-rolled drivers) still applies regardless;
the touch/LVGL-specific notes just don't apply to the board actually used.

## Why switch boards

The ESP32-C6 is single-core — WiFi shares one core with everything else (SPI to the display, I2C
to the RFID reader), which caused persistent, sporadic `socket.connect()` timeouts on Spoolman
requests right after an RFID read. We tried all the standard workarounds (throttled redraws,
retries, longer delays, disabling WiFi power-save) — the problem was reduced but never fully
eliminated. **The ESP32-S3 is dual-core** — WiFi can have a dedicated core, independent of how
busy the other core is with our code. This fixes the problem architecturally instead of patching
around it. Confirmed on real hardware after the move: no trace of the C6's WiFi timeouts.

For the originally-considered touch board, capacitive touch (CST816D) would also have replaced
the physical buttons. Since the actual board has no touch, that part didn't apply — see the board
note above.

## Why switch frameworks (MicroPython → ESPHome)

Most of the time spent on the C6 board went into debugging low-level issues in our own minimal
ST7789 driver written in MicroPython (SPI mode, `framebuf` endianness, corrupted transfers at full
width, buffer memory budget). ESPHome already solves this with mature components tested by
thousands of users — notably `pn532_i2c` (handles Mifare/NDEF parsing, removing all the manual
TLV/NDEF parsing the old `rfid.py`/`PN532.py` needed), plus built-in WiFi, `http_request`, and
Home Assistant integration. Our UI/business logic (4-channel state, Spoolman lookup order, printer
payload) is specific enough that it needed a fair amount of `lambda:` (C++ pasted into YAML) — not
100% declarative, but it saved us from writing display/RFID drivers from scratch.

Confirmed on real hardware: `pn532_i2c` parsed a real OpenSpool tag's NDEF message with zero
custom code needed.
