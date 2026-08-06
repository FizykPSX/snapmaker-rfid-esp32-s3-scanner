import json
import time

from event_wrapper import Action
from one_shot_timer import OneShotTimer
from periodic_timer import PeriodicTimer
from char_text_scroller import CharTextScroller
from data_validator import DataValidator

class ChannelState:
    EMPTY = 0
    READING = 1
    DATA = 2
    NO_DATA = 3
    BAD_DATA = 4

class ChannelControl:
    def __init__(self, channel_num, display, spoolman_client=None):
        self.channel_num = channel_num
        self.state = ChannelState.EMPTY
        self.last_data = None
        self.display = display
        self.spoolman_client = spoolman_client
        self.no_data_timer = None
        self.last_data_text = CharTextScroller()
        self.last_data_text_timer = None

    def update(self, selected, action, rfid_reader):
        if selected and action == Action.ACTIVATE:
            if self.state in [ChannelState.NO_DATA, ChannelState.BAD_DATA, ChannelState.EMPTY]:
                self.no_data_timer = None
                self.state = ChannelState.READING
                self.render(selected)
                data, uid = rfid_reader.read_text_and_uid()
                if data is not None:
                    print(f"Data read from channel {self.channel_num}: {data} (UID: {bytes(uid).hex()})")
                    if DataValidator.validate(data):
                        self.state = ChannelState.DATA
                        self.last_data = {'payload': data, 'uid': uid, 'spoolman': None}
                        if self.spoolman_client is not None:
                            try:
                                # Let the WiFi radio settle right after RFID/I2C
                                # activity - button IRQs plus bus traffic here
                                # were seen to stall the first connect() attempt
                                # (SpoolmanClient retries internally too).
                                time.sleep_ms(1500)
                                spool_id = json.loads(data).get('spool_id')
                                self.last_data['spoolman'] = self.spoolman_client.find(bytes(uid).hex(), spool_id)
                            except Exception as e:
                                print("Spoolman lookup failed:", e)
                        self.last_data_text.set_text(self.parse_data_for_display())
                        self.last_data_text_timer = PeriodicTimer(200)
                    else:
                        self.state = ChannelState.BAD_DATA
                        self.last_data = None
                        self.no_data_timer = OneShotTimer(5000)
                else:
                    self.state = ChannelState.NO_DATA
                    self.last_data = None
                    self.no_data_timer = OneShotTimer(5000)
            elif self.state == ChannelState.DATA:
                self.state = ChannelState.EMPTY
                self.last_data = None
                self.last_data_text.set_text("")
                self.last_data_text_timer = None
                self.no_data_timer = None
        
        if self.state in [ChannelState.NO_DATA, ChannelState.BAD_DATA] and self.no_data_timer.ready():
            self.state = ChannelState.EMPTY
            self.no_data_timer = None

    def parse_data_for_display(self):
        try:
            json_data = json.loads(self.last_data['payload'])
            display_parts = []
            if 'brand' in json_data:
                display_parts.append(json_data['brand'])
            if 'type' in json_data:
                display_parts.append(json_data['type'])
            if 'subtype' in json_data:
                display_parts.append(json_data['subtype'])
            if 'color_hex' in json_data:
                display_parts.append(json_data['color_hex'])
            return ' '.join(display_parts)
        except Exception as e:
            print("Error parsing data for display:", e)
            return "Data"
    
    def state_to_text(self):
        if self.state == ChannelState.EMPTY:
            return ""
        elif self.state == ChannelState.READING:
            return "..."
        elif self.state == ChannelState.DATA:
            if self.last_data_text_timer.ready():
                self.last_data_text.scroll()
            return self.last_data_text.get_text(9)  # Show a preview of the data
        elif self.state == ChannelState.NO_DATA:
            return "No data"
        elif self.state == ChannelState.BAD_DATA:
            return "Bad data"

    # Two grid rows per channel (LINE_HEIGHT each) since it's rendered at 2x scale.
    ROWS_PER_CHANNEL = 2
    FIRST_ROW = 2

    def render(self, selected):
        line = self.FIRST_ROW + (self.channel_num - 1) * self.ROWS_PER_CHANNEL
        prefix = "> " if selected else "  "
        self.display.clear_text_bg(line, scale=2)
        self.display.show_message(f"{prefix}CH {self.channel_num} {self.state_to_text()}", start_line=line, clear=False, wrapped=False, scale=2)
