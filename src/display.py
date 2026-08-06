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

        # One strip buffer, reused sequentially for every strip in show().
        # Four separate pre-allocated strips used ~220KB total and left too
        # little heap for the WiFi stack (connect() started reliably
        # ETIMEDOUT-ing once free memory dropped that low - verified on
        # hardware). Extracting via FrameBuffer.blit() (C implementation)
        # instead of a per-row Python copy loop is what makes this fast
        # (~590ms/frame -> ~50ms/frame) even with a single reused buffer.
        self._strip_buf = bytearray(self.STRIP_WIDTH * self.DISPLAY_HEIGHT * 2)
        self._strip_fb = framebuf.FrameBuffer(self._strip_buf, self.STRIP_WIDTH, self.DISPLAY_HEIGHT, framebuf.RGB565)

        # Reused scratch space for scaled text() calls - allocating a fresh
        # buffer per call (every redraw, every loop iteration) fragmented the
        # heap enough to reliably break WiFi connect() (verified on hardware).
        self._scale_scratch_buf = bytearray(self.MAX_SCALED_CHARS * 8 * 8 * 2)

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

    # Longest string ever passed to text(..., scale>1) - the scratch buffer
    # sized off this is allocated once and reused for every scaled draw.
    MAX_SCALED_CHARS = 24

    def clear(self):
        self._fb.fill(0)

    def show(self):
        for tx in range(0, self.DISPLAY_WIDTH, self.STRIP_WIDTH):
            w = min(self.STRIP_WIDTH, self.DISPLAY_WIDTH - tx)
            self._strip_fb.blit(self._fb, -tx, 0)
            self.tft.blit_buffer(self._strip_buf, tx, 0, w, self.DISPLAY_HEIGHT)

    def text(self, text, line=0, offset_x=0, color=None, scale=1):
        color = color if color is not None else self.color565(255, 255, 255)
        x = self.DISPLAY_X_OFFSET + offset_x
        y = self.DISPLAY_Y_OFFSET + line * self.LINE_HEIGHT
        if scale == 1:
            self._fb.text(text, x, y, color)
            return

        # framebuf has no built-in scaled text: render into a small scratch
        # buffer at 1x, then blow each source pixel up into a scale x scale
        # block. Fine for the short single-line labels this is used for.
        text = text[:self.MAX_SCALED_CHARS]
        glyph_w, glyph_h = 8 * len(text), 8
        scratch_mv = memoryview(self._scale_scratch_buf)[:glyph_w * glyph_h * 2]
        scratch = framebuf.FrameBuffer(scratch_mv, glyph_w, glyph_h, framebuf.RGB565)
        scratch.fill(0)
        scratch.text(text, 0, 0, color)
        for sy in range(glyph_h):
            for sx in range(glyph_w):
                if scratch.pixel(sx, sy):
                    self._fb.fill_rect(x + sx * scale, y + sy * scale, scale, scale, color)

    def wrapped_text(self, text, start_line=0, offset_x=0, color=None, scale=1):
        line = start_line
        line_width = self.LINE_WIDTH // scale

        for paragraph in text.split("\n"):
            while paragraph:
                self.text(paragraph[:line_width], line, offset_x=offset_x, color=color, scale=scale)
                paragraph = paragraph[line_width:]
                line += scale

        return line

    def show_message(self, text, start_line=0, clear=True, offset_x=0, wrapped=True, color=None, scale=1):
        if clear:
            self.clear()
        if wrapped:
            next_line = self.wrapped_text(text, start_line=start_line, offset_x=offset_x, color=color, scale=scale)
        else:
            self.text(text, line=start_line, offset_x=offset_x, color=color, scale=scale)
            next_line = start_line + scale
        self.show()
        return next_line

    def clear_text_bg(self, line, scale=1):
        self._fb.fill_rect(self.DISPLAY_X_OFFSET, self.DISPLAY_Y_OFFSET + line * self.LINE_HEIGHT, self.DISPLAY_WIDTH, self.LINE_HEIGHT * scale, 0)

    def clear_text_bg_after_text(self, line, text, scale=1):
        text_width = len(text) * self.CHAR_WIDTH * scale
        self._fb.fill_rect(self.DISPLAY_X_OFFSET + text_width, self.DISPLAY_Y_OFFSET + line * self.LINE_HEIGHT, self.DISPLAY_WIDTH - text_width, self.LINE_HEIGHT * scale, 0)

    def swatch(self, x, y, w, h, color_hex):
        """Draw a filled rectangle in an actual filament color, e.g. '#RRGGBB' or 'RRGGBB'."""
        color_hex = color_hex.lstrip('#')
        r = int(color_hex[0:2], 16)
        g = int(color_hex[2:4], 16)
        b = int(color_hex[4:6], 16)
        self._fb.fill_rect(x, y, w, h, self.color565(r, g, b))
