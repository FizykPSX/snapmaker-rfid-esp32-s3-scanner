# Bill of Materials

Parts needed for one reader unit. Prices are rough, EU market, mid-2026.

| # | Part | Qty | Notes |
|---|------|-----|-------|
| 1 | [Waveshare ESP32-S3-LCD-1.47B](https://www.waveshare.com/wiki/ESP32-S3-LCD-1.47B) | 1 | ESP32-S3R8, 172×320 ST7789 LCD on-board, no touch |
| 2 | PN532 NFC/RFID V3 module | 1 | I2C/SPI/HSU selectable via 2 DIP switches — set to **I2C** (switch 1 = ON, switch 2 = OFF) |
| 3 | Momentary tact switch, 2-pin (6×6mm) | 3 | Up / Down / OK |
| 4 | LiPo/Li-ion battery, single cell 3.7V, ≤2000mAh | 1 | MX1.25 connector or bare pads. 1000mAh flat pack fits an enclosure more easily; an 18650 (2000mAh) needs a separate holder + pads soldered to leads for more runtime |
| 5 | Bistable (self-locking) DPDT power switch | 1 | Only one pole used, wired into the battery **"+"** lead — never interrupt "-"/GND |
| 6 | Hookup wire | — | PN532 I2C (4 wires) + 3× button (2 wires each) |
| 7 | Enclosure | 1 | Not yet designed/printed |

## Notes

- The LCD is wired on-board — no separate display wiring needed, see the pinout in
  [README.md](README.md#wiring).
- **Before soldering the battery**, verify the "BAT"/"G" pad polarity on the physically-received
  board with a multimeter (measure DC voltage on USB power) — don't trust the silkscreen alone.
- Only ever connect **one** cell at a time; don't parallel/series two cells even if both are within
  the ≤2000mAh limit.
