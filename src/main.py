import sys
import json
import time
from config import Config
from display import LCDDisplay
from event_wrapper import Action, EventWrapper
from rfid import RFIDReader
from printer import PrinterClient
from spoolman import SpoolmanClient
from button_handler import ButtonHandler
from channel_control import ChannelControl, ChannelState

cfg = Config()

display = LCDDisplay(cfg.lcd())
rfid = RFIDReader(cfg.rfid())
printer = PrinterClient(cfg.printer())
spoolman = SpoolmanClient(cfg.spoolman())
btn_config = cfg.button()
btn_1 = ButtonHandler(button_pin=btn_config['pin'])
btn_2 = None
if 'pin2' in btn_config:
    btn_2 = ButtonHandler(button_pin=cfg.button()['pin2'])
event_wrapper = EventWrapper(btn_1, btn_2)

cursor_position = 0

# Initialize channel controls
channels = [ChannelControl(i + 1, display, spoolman) for i in range(4)]

APP_NAME = "U1 RFID Reader"
MENU_ITEMS = ["CH 1", "CH 2", "CH 3", "CH 4", "Send Data"]

SEND_DATA_LINE = 10
DETAIL_START_LINE = 11
DETAIL_SWATCH_X = display.DISPLAY_WIDTH - 40
DETAIL_SWATCH_Y = DETAIL_START_LINE * display.LINE_HEIGHT
DETAIL_SWATCH_SIZE = 30


def render_detail_panel(selected_channel):
    for line in (DETAIL_START_LINE, DETAIL_START_LINE + 1, DETAIL_START_LINE + 2):
        display.clear_text_bg(line)
    display.swatch(DETAIL_SWATCH_X, DETAIL_SWATCH_Y, DETAIL_SWATCH_SIZE, DETAIL_SWATCH_SIZE, '#000000')

    if selected_channel is None or selected_channel.state != ChannelState.DATA:
        return

    try:
        data = json.loads(selected_channel.last_data['payload'])
    except Exception:
        data = {}

    name_line = ' '.join(str(data[k]) for k in ('brand', 'type', 'subtype') if k in data)
    display.show_message(name_line, start_line=DETAIL_START_LINE, clear=False, wrapped=False)

    if 'color_hex' in data:
        try:
            display.swatch(DETAIL_SWATCH_X, DETAIL_SWATCH_Y, DETAIL_SWATCH_SIZE, DETAIL_SWATCH_SIZE, data['color_hex'])
        except Exception:
            pass

    uid_hex = bytes(selected_channel.last_data['uid']).hex()
    display.show_message(f"UID: {uid_hex}", start_line=DETAIL_START_LINE + 1, clear=False, wrapped=False)

    spool = selected_channel.last_data.get('spoolman')
    if not spoolman.enabled:
        spool_line = "Spoolman: off"
    elif spool is None:
        spool_line = "Spoolman: not found"
    else:
        weight = spool.get('remaining_weight')
        spool_line = f"Spoolman: {weight}g left" if weight is not None else "Spoolman: found"
    display.show_message(spool_line, start_line=DETAIL_START_LINE + 2, clear=False, wrapped=False)


try:
    while True:
        action = event_wrapper.handle_event()

        if action == Action.SOFT_RESET:
            import machine
            machine.soft_reset()
            break

        display.show_message(APP_NAME, start_line=0, clear=False, wrapped=False, scale=2)

        for i, channel in enumerate(channels):
            selected = (cursor_position == i)
            channel.update(selected, action, rfid)
            channel.render(selected)

        send_data_selected = (cursor_position == 4)
        send_data_text = "> Send Data" if send_data_selected else "  Send Data"
        display.clear_text_bg(SEND_DATA_LINE)
        display.show_message(send_data_text, start_line=SEND_DATA_LINE, clear=False)

        selected_channel = channels[cursor_position] if cursor_position < len(channels) else None
        render_detail_panel(selected_channel)

        if action == Action.NEXT:
            cursor_position = (cursor_position + 1) % len(MENU_ITEMS)
        elif action == Action.ACTIVATE:
            if cursor_position == 4:
                send_data_text = "> Sending "
                display.clear_text_bg(SEND_DATA_LINE)
                display.show_message(send_data_text, start_line=SEND_DATA_LINE, clear=False)

                for i, channel in enumerate(channels):
                    if channel.state == ChannelState.EMPTY:
                        send_data_text += '.'
                        display.clear_text_bg(SEND_DATA_LINE)
                        display.show_message(send_data_text, start_line=SEND_DATA_LINE, clear=False)
                    elif channel.state == ChannelState.DATA:
                        send_data_text += 'D'
                        display.clear_text_bg(SEND_DATA_LINE)
                        display.show_message(send_data_text, start_line=SEND_DATA_LINE, clear=False)

                        ok = printer.send_filament_data(i, channel.last_data)

                        send_data_text = send_data_text[:-1] + ('O' if ok else 'X')
                        display.clear_text_bg(SEND_DATA_LINE)
                        display.show_message(send_data_text, start_line=SEND_DATA_LINE, clear=False)
                        time.sleep(1)

        time.sleep_ms(30)

except Exception as e:
    print("Fatal error:", e)
    sys.print_exception(e)
    display.show_message("FATAL")
