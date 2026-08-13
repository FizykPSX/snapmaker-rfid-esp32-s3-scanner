#pragma once

#include <vector>

#include "esphome/components/nfc/automation.h"
#include "esphome/components/nfc/nfc.h"
#include "esphome/components/nfc/nfc_tag.h"
#include "esphome/components/rc522/rc522.h"
#include "esphome/components/spi/spi.h"

// ESPHome's stock rc522/rc522_spi components only expose the tag UID -- there's no NDEF support
// (unlike pn532, which does Type 2 Tag reading for MIFARE Ultralight/NTAG). This component bolts
// that on: it reuses rc522::RC522 for reset/anticollision/UID (its state machine and
// register-level helpers are all `protected`, so a subclass gets them for free) and implements the
// SPI register read/write itself (copied from rc522_spi -- inheriting RC522Spi directly would pull
// in its own CONFIG_SCHEMA/required cs_pin as a second, separately-instantiated component whenever
// this one is AUTO_LOADed). On top of that it adds one extra phase after a UID is found: read
// pages 3.. via the same PICC_CMD_MF_READ (0x30) command PN532 uses for Ultralight, locate the
// NDEF TLV the same way pn532_mifare_ultralight.cpp does, and hand the raw message bytes to
// nfc::NdefMessage. The tag stays selected/antenna-on for this extra exchange, so no re-select is
// needed.
//
// buffer_[9] in the base RC522 class is too small for an 18-byte MIFARE Read response (16 data +
// 2 CRC_A), so this can't just call the inherited pcd_transceive_data_()/await_transceive_() for
// the page reads -- those are reimplemented here against a dedicated 18-byte buffer. CRC_A
// calculation *is* reused via the inherited pcd_calculate_crc_()/await_crc_(), since those only
// need a data pointer/length in and leave the 2-byte result in the (unrelated, still-free) base
// buffer_.

namespace esphome::rc522_ndef {

class RC522Ndef : public rc522::RC522,
                   public spi::SPIDevice<spi::BIT_ORDER_MSB_FIRST, spi::CLOCK_POLARITY_LOW,
                                         spi::CLOCK_PHASE_LEADING, spi::DATA_RATE_4MHZ> {
 public:
  void setup() override;
  void dump_config() override;
  void loop() override;

  void register_ontag_trigger(nfc::NfcOnTagTrigger *trig) { this->ndef_triggers_ontag_.push_back(trig); }
  void register_ontagremoved_trigger(nfc::NfcOnTagTrigger *trig) {
    this->ndef_triggers_ontagremoved_.push_back(trig);
  }

 protected:
  // Copied from rc522_spi::RC522Spi -- see the note above the class for why this isn't just
  // inherited from RC522Spi.
  uint8_t pcd_read_register(PcdRegister reg) override;
  void pcd_read_register(PcdRegister reg, uint8_t count, uint8_t *values, uint8_t rx_align) override;
  void pcd_write_register(PcdRegister reg, uint8_t value) override;
  void pcd_write_register(PcdRegister reg, uint8_t count, uint8_t *values) override;

  enum NdefPhase : uint8_t {
    NDEF_NONE = 0,
    NDEF_CALC_CRC,    // pcd_calculate_crc_() issued for the next page-read command, awaiting result
    NDEF_TRANSCEIVE,  // page-read command sent, awaiting the tag's response
  };
  enum NdefStep : uint8_t {
    STEP_INITIAL = 0,  // reading pages 3-6 (capability container + first NDEF bytes)
    STEP_EXTRA,        // message is longer than what pages 3-6 held, reading more pages
  };

  void ndef_begin_read_(std::vector<uint8_t> &&rfid_uid);
  void ndef_request_page_(uint8_t page);
  void ndef_transceive_(uint8_t send_len);
  StatusCode ndef_await_transceive_();
  void ndef_on_block_done_();
  void ndef_start_extra_read_();
  void ndef_finish_();

  NdefPhase ndef_phase_{NDEF_NONE};
  NdefStep ndef_step_{STEP_INITIAL};
  std::vector<uint8_t> ndef_uid_;
  std::vector<uint8_t> ndef_data_;
  uint8_t ndef_next_page_{0};
  uint16_t ndef_bytes_needed_{0};
  uint8_t ndef_message_length_{0};
  uint8_t ndef_message_start_{0};

  uint8_t ndef_buf_[18];  // 16 data bytes + 2 CRC_A bytes returned by a MIFARE/Ultralight Read
  uint8_t ndef_send_len_{0};
  uint8_t ndef_back_length_{0};

  std::vector<nfc::NfcOnTagTrigger *> ndef_triggers_ontag_;
  std::vector<nfc::NfcOnTagTrigger *> ndef_triggers_ontagremoved_;
  std::vector<uint8_t> ndef_current_uid_;
};

}  // namespace esphome::rc522_ndef
