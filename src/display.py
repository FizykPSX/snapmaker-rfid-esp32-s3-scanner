from machine import Pin, SPI
import framebuf
import st7789py as st7789

class LCDDisplay:
    # Waveshare ESP32-C6-LCD-1.47: 172x320 ST7789 panel, driven rotated (MADCTL MV|MX)
    # to present as a 320x172 landscape screen.
    LINE_HEIGHT = 11
    DISPLAY_WIDTH = 320
    DISPLAY_HEIGHT = 172
    # Physical panel has rounded corners under an opaque bezel; inset the usable
    # text area so glyphs near the edges aren't clipped (verified on hardware).
    DISPLAY_X_OFFSET = 8
    DISPLAY_Y_OFFSET = 6
    CHAR_WIDTH = 8
    LINE_WIDTH = int((DISPLAY_WIDTH - 2 * DISPLAY_X_OFFSET) / CHAR_WIDTH)

    def __init__(self, cfg):
        bl = Pin(cfg["bl"], Pin.OUT)
        bl.value(1)

        spi = SPI(
            1,
            baudrate=cfg.get("baudrate", 40000000),
            polarity=0,
            phase=0,
            sck=Pin(cfg["sck"]),
            mosi=Pin(cfg["mosi"]),
        )

        self.tft = st7789.ST7789(
            spi,
            self.DISPLAY_WIDTH, self.DISPLAY_HEIGHT,
            reset=Pin(cfg["rst"], Pin.OUT),
            dc=Pin(cfg["dc"], Pin.OUT),
            cs=Pin(cfg["cs"], Pin.OUT),
            backlight=bl,
            xstart=cfg.get("xstart", 0),
            ystart=cfg.get("ystart", 34),
        )
        self.tft.init()
        # st7789py's own init() hardcodes a portrait-oriented MADCTL; override it
        # for our rotated landscape layout (verified on hardware: MV alone mirrors
        # the image, MV|MX is the correct orientation for this panel).
        self.tft.write(
            st7789.ST7789_MADCTL,
            bytes([st7789.ST7789_MADCTL_MV | st7789.ST7789_MADCTL_MX]),
        )

        self._buf = bytearray(self.DISPLAY_WIDTH * self.DISPLAY_HEIGHT * 2)
        self._fb = framebuf.FrameBuffer(self._buf, self.DISPLAY_WIDTH, self.DISPLAY_HEIGHT, framebuf.RGB565)

        # Pre-allocated once and reused every show() - extracting strips via
        # FrameBuffer.blit() (C implementation) instead of a per-row Python copy
        # loop turned a ~590ms redraw into ~50ms.
        self._strips = []
        for tx in range(0, self.DISPLAY_WIDTH, self.STRIP_WIDTH):
            w = min(self.STRIP_WIDTH, self.DISPLAY_WIDTH - tx)
            buf = bytearray(w * self.DISPLAY_HEIGHT * 2)
            fb = framebuf.FrameBuffer(buf, w, self.DISPLAY_HEIGHT, framebuf.RGB565)
            self._strips.append((tx, w, buf, fb))

        self.clear()
        self.show()

    @staticmethod
    def color565(r, g, b):
        # framebuf.RGB565 stores pixels little-endian, but the ST7789 panel
        # expects big-endian (MSB-first) pixel data over SPI - pre-swap here so
        # blit_buffer() can send the raw framebuf bytes unmodified.
        v = st7789.color565(r, g, b)
        return ((v & 0xFF) << 8) | (v >> 8)

    # A single blit_buffer() spanning the full 320px width reproducibly corrupts
    # the left column and bottom row on this panel (verified on hardware, root
    # cause unclear - likely a CASET/RAMWR quirk of this ST7789 unit at full
    # width). Splitting into vertical strips narrower than the full width avoids
    # it entirely, so show() always sends the frame in strips of this width.
    STRIP_WIDTH = 80

    def clear(self):
        self._fb.fill(0)

    def show(self):
        for tx, w, buf, fb in self._strips:
            fb.blit(self._fb, -tx, 0)
            self.tft.blit_buffer(buf, tx, 0, w, self.DISPLAY_HEIGHT)

    def text(self, text, line=0, offset_x=0, color=None):
        self._fb.text(
            text,
            self.DISPLAY_X_OFFSET + offset_x,
            self.DISPLAY_Y_OFFSET + line * self.LINE_HEIGHT,
            color if color is not None else self.color565(255, 255, 255),
        )

    def wrapped_text(self, text, start_line=0, offset_x=0, color=None):
        line = start_line

        for paragraph in text.split("\n"):
            while paragraph:
                self.text(paragraph[:self.LINE_WIDTH], line, offset_x=offset_x, color=color)
                paragraph = paragraph[self.LINE_WIDTH:]
                line += 1

        return line

    def show_message(self, text, start_line=0, clear=True, offset_x=0, wrapped=True, color=None):
        if clear:
            self.clear()
        if wrapped:
            next_line = self.wrapped_text(text, start_line=start_line, offset_x=offset_x, color=color)
        else:
            self.text(text, line=start_line, offset_x=offset_x, color=color)
            next_line = start_line + 1
        self.show()
        return next_line

    def clear_text_bg(self, line):
        self._fb.fill_rect(self.DISPLAY_X_OFFSET, self.DISPLAY_Y_OFFSET + line * self.LINE_HEIGHT, self.DISPLAY_WIDTH, self.LINE_HEIGHT, 0)

    def clear_text_bg_after_text(self, line, text):
        text_width = len(text) * self.CHAR_WIDTH
        self._fb.fill_rect(self.DISPLAY_X_OFFSET + text_width, self.DISPLAY_Y_OFFSET + line * self.LINE_HEIGHT, self.DISPLAY_WIDTH - text_width, self.LINE_HEIGHT, 0)

    def swatch(self, x, y, w, h, color_hex):
        """Draw a filled rectangle in an actual filament color, e.g. '#RRGGBB' or 'RRGGBB'."""
        color_hex = color_hex.lstrip('#')
        r = int(color_hex[0:2], 16)
        g = int(color_hex[2:4], 16)
        b = int(color_hex[4:6], 16)
        self._fb.fill_rect(x, y, w, h, self.color565(r, g, b))
