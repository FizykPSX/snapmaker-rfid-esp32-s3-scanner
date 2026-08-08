# Plan migracji: ESP32-C6-LCD-1.47 (MicroPython) → Waveshare ESP32-S3-LCD-1.47B (ESPHome)

> **Update (2026-08-08):** faktycznie zamówiona i otrzymana płytka to **ESP32-S3-LCD-1.47B**, nie
> ESP32-S3-Touch-LCD-2 opisany niżej jako "docelowy sprzęt". Różnice mają znaczenie:
> - Ekran **1.47" 172×320** (jak na starej płytce C6), nie 2" 240×320.
> - **Brak dotyku** — CST816D nie występuje na tej płytce. UI zostaje oparte o **fizyczne przyciski**
>   (dokładnie jak na C6), nie LVGL+touch. Zamówione 400 tact switchy na zapas.
> - Dodatkowo na pokładzie: **QMI8658 6-axis IMU** (niepotrzebny, ignorujemy) i gniazdo TF/SD (SDIO,
>   zajmuje GPIO 14/15/16/17/18/21 — nieużywane w projekcie, ale trzeba pamiętać że te piny są zajęte).
> - Potwierdzony pinout LCD z dokumentacji Waveshare: MOSI=45, SCLK=40, CS=42, DC=41, RST=39, BL=46.
>   RGB LED (WS2812-style) na GPIO38.
> - Reszta rozumowania (dual-core → koniec kolizji WiFi/SPI, ESPHome zamiast własnych sterowników)
>   zostaje bez zmian — patrz sekcje niżej. Sekcje dot. LVGL/dotyku poniżej są nieaktualne w tej
>   części, ale zostawione jako dokumentacja pierwotnego rozumowania.
>
> **Status bring-up (2026-08-08): potwierdzone na żywym sprzęcie.** WiFi (z `power_save_mode: none`,
> bez śladu po problemach z C6), ekran ST7789 (`model: "Waveshare 1.47in 172X320"`, offset 34/0 z
> ESPHome działa od razu poprawnie), PN532 przez I2C na GPIO8/GPIO9 (odczyt prawdziwego taga OpenSpool
> ze szpuli — zero custom parsowania NDEF potrzebne, patrz niżej), 3 przyciski góra/dół/OK na
> GPIO4/5/6, captive portal + lokalny panel web (`web_server: local: true`) do konfiguracji WiFi i
> IP drukarki/Spoolmana bez rekompilacji. Config: `esphome/snapmaker-rfid-s3.yaml` w tym repo.
>
> **Status integracji (2026-08-08): działa end-to-end na żywym sprzęcie.** UI 4-kanałowe (góra/dół
> nawiguje, OK uzbraja kanał z timeoutem 10s i licznikiem na ekranie, PN532 śpi poza tym oknem —
> `stop_poller()`/`start_poller()` na komponencie), Spoolman lookup (spool_id → fallback UID po
> `extra.card_uids`, tak jak w oryginale), wysyłka do drukarki przez `http_request.post` na
> `/printer/filament_detect/set`. **Ważna pułapka znaleziona przy debugowaniu:** `CARD_UID` w
> payloadzie do drukarki musi być tablicą liczb (bajtów UID), nie stringiem z myślnikami — firmware
> (`SnapmakerU1-Extended-Firmware`, plik `filament_detect.py`) robi `[int(b) for b in CARD_UID]`,
> więc string typu `"04-E5-43-4D-C7-2A-81"` wywala `invalid literal for int(): '-'`. Poprawny format:
> `[4, 229, 67, 77, 199, 42, 129]`. Potwierdzone na żywo: drukarka realnie zmieniła przypisany
> filament po wysyłce danych ze szpuli.

## Dlaczego zmiana płytki

ESP32-C6 jest jednordzeniowy — WiFi dzieli jeden rdzeń z całą resztą kodu (SPI do ekranu, I2C do RFID), co powodowało uporczywe, sporadyczne timeouty `socket.connect()` przy zapytaniach do Spoolmana zaraz po odczycie RFID. Testowaliśmy wszystkie standardowe obejścia (throttling odświeżania, retry, dłuższe opóźnienia, wyłączenie WiFi power-save) — problem został złagodzony, ale nie wyeliminowany do zera. **ESP32-S3 jest dwurdzeniowy** — WiFi może mieć dedykowany rdzeń, niezależny od tego jak bardzo drugi rdzeń jest zajęty naszym kodem. To rozwiązuje problem architekturalnie, nie łatkami.

Przy okazji: **dotyk pojemnościowy (CST816D) zastępuje fizyczne przyciski** — nie trzeba nic lutować poza samym PN532.

## Dlaczego zmiana frameworku (MicroPython → ESPHome)

Większość czasu spędzonego na obecnej płytce poszła na debugowanie niskopoziomowych problemów naszego własnego, minimalnego sterownika ST7789 w MicroPythonie (tryb SPI, endianness `framebuf`, uszkodzone transfery przy pełnej szerokości, budżet pamięci na bufory). ESPHome ma to już rozwiązane w dojrzałych, testowanych przez tysiące userów komponentach:

- **`pn532_i2c`** — gotowy komponent RFID, obsługuje Mifare Classic, czytanie bloków, parsowanie rekordów NDEF/tekstowych (`on_tag`). Potencjalnie zdejmuje z nas całe ręczne parsowanie TLV/NDEF z obecnego `rfid.py`/`PN532.py`.
  **Potwierdzone na żywym sprzęcie (2026-08-08):** prawdziwy tag ze szpuli (Mifare Ultralight) odczytany bezbłędnie, `pn532_i2c` samo sparsowało NDEF i zwróciło gotowy JSON: `{"protocol":"openspool","version":"1.0","type":"PETG","color_hex":"40AA98","brand":"SUNLU","min_temp":"190","max_temp":"220","spool_id":"9","subtype":"Basic"}`. Zero custom kodu parsującego potrzebne. (Losowa karta Mifare Classic z szuflady dała `Authentication failed` — to spodziewane, karta nie jest sformatowana pod NDEF, nie problem z configiem.)
- **WiFi** — jedna z flagowych mocnych stron ESPHome, dokładnie nasz dzisiejszy ból.
- **LVGL + dotyk (CST816)** — oficjalne wsparcie, są gotowe configi społeczności dla podobnych płytek Waveshare S3 z dotykiem.
- **`http_request`** — komponent do GET/POST, załatwia komunikację ze Spoolmanem i drukarką.
- **Integracja z Home Assistant** — natywna, użytkownik ma HA.

Nasza logika (stan 4 kanałów, przewijający się tekst, panel szczegółów z próbką koloru, kolejność spool_id→UID w Spoolmanie, wysyłka do drukarki) jest dość specyficzna i będzie wymagać sporo `lambda:` (C++ wklejony w YAML) — to nie będzie w 100% czysto deklaratywne, ale zdejmuje z nas pisanie sterowników od zera.

**Plan B**, gdyby ESPHome okazał się zbyt ograniczający dla naszej logiki: czyste **Arduino/PlatformIO + TFT_eSPI/LVGL + Adafruit_PN532** — też mature biblioteki, więcej kontroli, więcej własnego kodu.

## Docelowy sprzęt

**[Waveshare ESP32-S3-Touch-LCD-2](https://www.waveshare.com/esp32-s3-touch-lcd-2.htm)**
- ESP32-S3R8, dwurdzeniowy LX7, 240MHz, 8MB PSRAM, 16MB flash
- Ekran: 2", 240×320, IPS, sterownik **ST7789T3** (SPI)
- Dotyk: **CST816D**, I2C
- Bonus: IMU (QMI8658, niepotrzebne nam), złącze baterii MX1.25

## Co przenosi się (jako logika/koncepcja, nie 1:1 kod)

- Format tagów: OpenSpool-JSON (`brand`, `type`, `subtype`, `color_hex`, `spool_id`, ...) — parsowanie w `lambda:`
- Logika Spoolman: `spool_id` najpierw (GET `/api/v1/spool/{id}`), fallback po `card_uids` extra field
- Payload do drukarki Snapmaker (POST `/printer/filament_detect/set`)
- Koncepcja UI: 4 kanały + Send Data + panel szczegółów z próbką koloru

## Kolejność prac po otrzymaniu sprzętu

1. Zainstalować ESPHome (dodatek do Home Assistant albo CLI) i podstawowy config: WiFi + logi + OTA
2. Zweryfikować pinout ekranu/dotyku fizycznie (multimetr + dokumentacja Waveshare, jak poprzednio)
3. Bring-up ekranu (LVGL + sterownik ST7789) — sprawdzić od razu przy starcie: pełna szerokość jednym blitem (czy ten model ma ten sam problem co C6?), zużycie pamięci, czas odświeżania
4. Bring-up dotyku (CST816D)
5. Bring-up PN532 (`pn532_i2c`) — sprawdzić czy wbudowane parsowanie NDEF/tekstu poradzi sobie z naszym formatem JSON, czy potrzebny będzie własny lambda-parser
6. UI w LVGL pod dotyk (zamiast przycisków fizycznych)
7. `http_request` do Spoolmana i drukarki, logika spool_id→UID
8. Integracja z Home Assistant (opcjonalnie: sensor stanu szpul, przycisk wysyłki)
9. Test end-to-end, ze szczególnym naciskiem na powtórzenie testu "ciągła aktywność ekranu/RFID + zapytanie WiFi" żeby potwierdzić że dwurdzeniowość + ESPHome faktycznie rozwiązują problem z dzisiaj
10. Bateria (patrz niżej) + obudowa

## Zasilanie z baterii LiPo (żeby nie trzymać na powerbanku)

Zamówiono: bateria **1000mAh**, przełącznik bistabilny (self-locking, DPDT, użyjemy jednej pary pinów) do wstawienia na przewód "+".

Potwierdzone z dokumentacji Waveshare:
- Złącze/pady: **MX1.25 / lutowane pady, 3.7V Li-Po/Li-ion, jedno ogniwo**
- Limit: **≤2000mAh** (nie przekraczać, nie łączyć kilku ogniw)
- Regulator 3.3V na płytce (ME6217C33M5G), obsługa ładowania na pokładzie

**Przed lutowaniem:** zweryfikować multimetrem polaryzację padów "BAT"/"G" na fizycznie otrzymanej płytce (nie ufać samemu sitodrukowi) — podłączyć USB, zmierzyć napięcie DC między padami, potwierdzić który jest "+".

**Update (2026-08-08):** oprócz zamówionej płaskiej 1000mAh, mamy też fizycznie na stanie 2x płaską 1000mAh i 2x 18650 2000mAh. Wszystkie mieszczą się w limicie ≤2000mAh/jedno ogniwo — **ale nadal tylko jedno ogniwo na raz**, nie łączyć dwóch cel równolegle/szeregowo. 18650 nie ma fabrycznego złącza pod pady płytki — potrzebny uchwyt/holder na 18650 i dolutowanie przewodów do padów "+"/"-", tak samo jak przy płaskiej baterii. Płaska 1000mAh jest wygodniejsza mechanicznie (mieści się w obudowie), 18650 da dłuższy czas pracy — decyzja do podjęcia na etapie projektowania obudowy.

Przełącznik bistabilny idzie w przewód "+" między ogniwem a płytką, nigdy nie przerywamy "-"/GND.
