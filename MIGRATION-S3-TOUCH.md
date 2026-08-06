# Plan migracji: ESP32-C6-LCD-1.47 → Waveshare ESP32-S3-Touch-LCD-2

## Dlaczego

ESP32-C6 jest jednordzeniowy — WiFi dzieli jeden rdzeń z całą resztą kodu (SPI do ekranu, I2C do RFID), co powodowało uporczywe, sporadyczne timeouty `socket.connect()` przy zapytaniach do Spoolmana zaraz po odczycie RFID. Testowaliśmy wszystkie standardowe obejścia (throttling odświeżania, retry, dłuższe opóźnienia, wyłączenie WiFi power-save) — problem został złagodzony, ale nie wyeliminowany do zera. **ESP32-S3 jest dwurdzeniowy** — WiFi może mieć dedykowany rdzeń, niezależny od tego jak bardzo drugi rdzeń jest zajęty naszym kodem. To rozwiązuje problem architekturalnie, nie łatkami.

Przy okazji: **dotyk pojemnościowy (CST816D) zastępuje fizyczne przyciski** — nie trzeba nic lutować poza samym PN532.

## Docelowy sprzęt

**[Waveshare ESP32-S3-Touch-LCD-2](https://www.waveshare.com/esp32-s3-touch-lcd-2.htm)**
- ESP32-S3R8, dwurdzeniowy LX7, 240MHz, 8MB PSRAM, 16MB flash
- Ekran: 2", 240×320, IPS, sterownik **ST7789T3** (SPI) — ta sama rodzina co obecny ST7789, więc podejście z `st7789py.py` powinno się przenieść, ale piny/offsety/init trzeba będzie zweryfikować od zera na żywym sprzęcie
- Dotyk: **CST816D**, I2C
- Bonus (niepotrzebne nam, ale obecne): IMU (QMI8658), złącze baterii

## Co przenosi się bez zmian

- `PN532.py`, `rfid.py` — sterownik i logika RFID, I2C-agnostyczne co do pinów
- `spoolman.py` — logika zapytań, cache'owanie po `spool_id`, retry
- `printer.py` — wysyłka do Snapmakera
- `data_validator.py`, `char_text_scroller.py`, `one_shot_timer.py`, `periodic_timer.py`
- `config.py` / `config.json` — struktura, tylko nowe wartości pinów

## Co trzeba zrobić od nowa

1. **Bring-up wyświetlacza** — dokładnie ten sam proces diagnostyczny co poprzednio, tym razem *proaktywnie* wiedząc czego szukać:
   - piny SPI (SCK/MOSI/DC/CS/RST/BL) — sprawdzić dokumentację, potem zweryfikować fizycznie
   - tryb SPI (zacząć od Mode 0, sprawdzić inne jeśli czarny ekran)
   - `xstart`/`ystart` offset dla panelu 240×320 (może być zerowy, bo to już "pełny" rozmiar sterownika ST7789, bez potrzeby centrowania jak przy 172-szerokim panelu)
   - **Od razu testować przy pełnej szerokości/wysokości pojedynczym du≥żym `blit_buffer()`** — sprawdzić czy to konkretne urządzenie ma ten sam problem z uszkodzeniem przy pełnej szerokości, zanim zaimplementujemy obejście na sztywno
   - **Od razu mierzyć czas `show()`** i użyć `framebuf.blit()` do ekstrakcji kawałków zamiast pętli Pythona — wiemy już że to jest properly szybkie podejście
   - **Od razu pilnować budżetu pamięci** — nie alokować dużych buforów per-wywołanie, nie trzymać więcej niż jednego bufora paska na raz
2. **Sterownik dotyku** — nowy plik, np. `touch.py`, driver dla CST816D po I2C (community drivery istnieją dla MicroPython, np. w projektach LVGL/CST816 — do zweryfikowania po otrzymaniu płytki)
3. **UI pod dotyk zamiast przycisków** — `button_handler.py`/`event_wrapper.py` prawdopodobnie do wyrzucenia, zastąpione obsługą dotknięć w konkretne obszary ekranu (np. cały wiersz kanału = dotyk aktywuje ten kanał, przycisk "Send Data" jako osobny dotykalny obszar)
4. **Przeprojektowanie layoutu pod 240×320** — inne proporcje niż obecny landscape 320×172, więcej miejsca pionowo. Prawdopodobnie zostajemy w orientacji portret (naturalna dla tego panelu) zamiast wymuszać landscape jak poprzednio (unikamy w ten sposób całej gimnastyki z MADCTL/MV/MX którą robiliśmy dla C6)
5. **Zasilanie z baterii** — patrz niżej

## Zasilanie z baterii LiPo (żeby nie trzymać na powerbanku)

Potwierdzone z dokumentacji Waveshare:
- Złącze: **MX1.25, 2-pin**, na pojedynczy ogniwo **3.7V Li-Po/Li-ion**
- Zalecana pojemność: **≤2000mAh** (jedno ogniwo, nie podłączać kilku naraz)
- Regulator 3.3V na płytce (ME6217C33M5G), obsługa ładowania na pokładzie

**Niepewne, do zweryfikowania fizycznie po otrzymaniu płytki:** czy TEN konkretny model ma wbudowany przełącznik ON/OFF zasilania z baterii (niektóre płytki z tej samej rodziny Waveshare go mają, dokumentacja tego konkretnego modelu tego nie potwierdza jednoznacznie).

**Rekomendacja niezależna od tego:** kup baterię LiPo z **wbudowanym przełącznikiem suwakowym na przewodzie** (bardzo standardowy, tani akcesorium — szukaj "LiPo battery with switch MX1.25" lub kup goły przełącznik suwakowy i wepnij go w przewód od baterii między ogniwem a złączem) — to gwarantuje kontrolę wł/wył niezależnie od tego czy płytka ma własny przełącznik.

**Przed podłączeniem baterii:** zweryfikować multimetrem/schematem polaryzację złącza MX1.25 na tej konkretnej płytce — to nie jest w 100% ustandaryzowane między producentami, a odwrotna polaryzacja może uszkodzić płytkę.

## Kolejność prac po otrzymaniu sprzętu

1. Zweryfikować pinout fizycznie (multimetr + dokumentacja, jak poprzednio)
2. Zainstalować/zflashować MicroPython (ten sam `ESP32_GENERIC_S3` firmware)
3. Bring-up ekranu (patrz lista wyżej) — celowo szybciej niż poprzednio, bo znamy już pułapki
4. Bring-up dotyku (nowy element)
5. Przenieść RFID/Spoolman/printer bez zmian, tylko nowe piny w configu
6. Przeprojektować UI pod dotyk
7. Test end-to-end, ze szczególnym naciskiem na powtórzenie testu "ciągła pętla renderowania + Spoolman" żeby potwierdzić że dwurdzeniowość faktycznie rozwiązuje problem
8. Bateria + obudowa
