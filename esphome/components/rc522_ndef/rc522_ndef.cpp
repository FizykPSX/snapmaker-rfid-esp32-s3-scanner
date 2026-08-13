#include "rc522_ndef.h"
#include "esphome/core/helpers.h"
#include "esphome/core/log.h"

namespace esphome::rc522_ndef {

static const char *const TAG = "rc522_ndef";

// Mirrors pn532_mifare_ultralight.cpp's approach: page 3 is the capability container, the NDEF
// TLV starts somewhere in page 4, and pages are read 4 at a time (16 bytes) via the same
// PICC_CMD_MF_READ command PN532 uses for MIFARE Ultralight/NTAG.
static constexpr uint8_t P4_OFFSET = 4;         // page 4 begins 4 bytes into a page-3-first read
static constexpr uint8_t INITIAL_USABLE = 12;   // pages 4-6 minus the page-3 capability container

void RC522Ndef::setup() {
  this->spi_setup();
  RC522::setup();
}

void RC522Ndef::dump_config() {
  RC522::dump_config();
  LOG_PIN("  CS Pin: ", this->cs_);
}

// -- SPI register access, copied from rc522_spi::RC522Spi (see the class-level comment) --

uint8_t RC522Ndef::pcd_read_register(PcdRegister reg) {
  uint8_t value;
  enable();
  transfer_byte(0x80 | reg);
  value = read_byte();
  disable();
  return value;
}

void RC522Ndef::pcd_read_register(PcdRegister reg, uint8_t count, uint8_t *values, uint8_t rx_align) {
  if (count == 0)
    return;
  uint8_t address = 0x80 | reg;
  uint8_t index = 0;
  enable();
  count--;  // one read is performed outside of the loop
  write_byte(address);
  if (rx_align) {
    uint8_t mask = 0xFF << rx_align;
    uint8_t value = transfer_byte(address);
    values[0] = (values[0] & ~mask) | (value & mask);
    index++;
  }
  while (index < count) {
    values[index] = transfer_byte(address);
    index++;
  }
  values[index] = transfer_byte(0);  // read the final byte, send 0 to stop reading
  disable();
}

void RC522Ndef::pcd_write_register(PcdRegister reg, uint8_t value) {
  enable();
  transfer_byte(reg);
  transfer_byte(value);
  disable();
}

void RC522Ndef::pcd_write_register(PcdRegister reg, uint8_t count, uint8_t *values) {
  enable();
  transfer_byte(reg);
  for (uint8_t index = 0; index < count; index++)
    transfer_byte(values[index]);
  disable();
}

void RC522Ndef::loop() {
  if (this->reset_count_ > 0) {
    this->pcd_reset_();
    return;
  }
  if (this->state_ == STATE_SETUP) {
    this->initialize_();
    return;
  }

  StatusCode status = STATUS_ERROR;
  if (this->awaiting_comm_) {
    if (this->state_ == STATE_READ_SERIAL_DONE && this->ndef_phase_ == NDEF_CALC_CRC) {
      status = this->await_crc_();
    } else if (this->state_ == STATE_READ_SERIAL_DONE && this->ndef_phase_ == NDEF_TRANSCEIVE) {
      status = this->ndef_await_transceive_();
    } else if (this->state_ == STATE_SELECT_SERIAL_DONE) {
      status = this->await_crc_();
    } else {
      status = this->await_transceive_();
    }
    if (status == STATUS_WAITING) {
      return;
    }
    this->awaiting_comm_ = false;
  }

  switch (this->state_) {
    case STATE_PICC_REQUEST_A: {
      if (status == STATUS_TIMEOUT) {
        for (auto *obj : this->binary_sensors_)
          obj->on_scan_end();
        this->state_ = STATE_DONE;
      } else if (status != STATUS_OK) {
        ESP_LOGW(TAG, "CMD_REQA -> Not OK %d", status);
        this->state_ = STATE_DONE;
      } else if (this->back_length_ != 2) {
        ESP_LOGW(TAG, "CMD_REQA -> OK, but unexpected back_length_ of %d", this->back_length_);
        this->state_ = STATE_DONE;
      } else {
        this->state_ = STATE_READ_SERIAL;
      }
      if (this->state_ == STATE_DONE) {
        this->pcd_antenna_off_();
      }
      break;
    }
    case STATE_READ_SERIAL: {
      switch (this->uid_idx_) {
        case 0:
          this->buffer_[0] = PICC_CMD_SEL_CL1;
          break;
        case 3:
          this->buffer_[0] = PICC_CMD_SEL_CL2;
          break;
        case 6:
          this->buffer_[0] = PICC_CMD_SEL_CL3;
          break;
        default:
          ESP_LOGE(TAG, "uid_idx_ invalid, uid_idx_ = %d", this->uid_idx_);
          this->state_ = STATE_DONE;
          return;
      }
      this->buffer_[1] = 32;
      this->pcd_transceive_data_(2);
      this->state_ = STATE_SELECT_SERIAL;
      break;
    }
    case STATE_SELECT_SERIAL: {
      this->buffer_[1] = 0x70;
      this->buffer_[6] = this->buffer_[2] ^ this->buffer_[3] ^ this->buffer_[4] ^ this->buffer_[5];
      this->pcd_calculate_crc_(this->buffer_, 7);
      this->state_ = STATE_SELECT_SERIAL_DONE;
      break;
    }
    case STATE_SELECT_SERIAL_DONE: {
      this->pcd_transceive_data_(9);
      this->state_ = STATE_READ_SERIAL_DONE;
      break;
    }
    case STATE_READ_SERIAL_DONE: {
      // A UID was already found and we're mid NDEF-page-read: this tick's status/data belongs to
      // that follow-up exchange, not to a fresh SELECT response.
      if (this->ndef_phase_ != NDEF_NONE) {
        if (status != STATUS_OK) {
          ESP_LOGW(TAG, "NDEF page read failed (status %d), reporting tag with UID only", status);
          this->ndef_message_length_ = 0;
          this->ndef_data_.clear();
          this->ndef_finish_();
          break;
        }
        if (this->ndef_phase_ == NDEF_CALC_CRC) {
          // CRC_A for the pending MF_READ is ready in buffer_[7]/buffer_[8].
          this->ndef_buf_[0] = PICC_CMD_MF_READ;
          this->ndef_buf_[1] = this->ndef_next_page_;
          this->ndef_buf_[2] = this->buffer_[7];
          this->ndef_buf_[3] = this->buffer_[8];
          this->ndef_transceive_(4);
          break;
        }
        // NDEF_TRANSCEIVE finished successfully.
        this->ndef_on_block_done_();
        break;
      }

      if (status != STATUS_OK || this->back_length_ != 3) {
        if (status != STATUS_TIMEOUT) {
          char hex_buf[format_hex_pretty_size(10)];
          ESP_LOGW(TAG, "Unexpected response. Read status is %d. Read bytes: %d (%s)", status, this->back_length_,
                   format_hex_pretty_to(hex_buf, this->buffer_, this->back_length_, '-'));
        }
        this->state_ = STATE_DONE;
        this->uid_idx_ = 0;
        this->pcd_antenna_off_();
        return;
      }

      bool cascade = this->buffer_[2] == PICC_CMD_CT;
      for (uint8_t i = 2 + cascade; i < 6; i++)
        this->uid_buffer_[this->uid_idx_++] = this->buffer_[i];

      if (cascade) {
        this->state_ = STATE_READ_SERIAL;
        return;
      }

      std::vector<uint8_t> rfid_uid(std::begin(this->uid_buffer_), std::begin(this->uid_buffer_) + this->uid_idx_);
      this->uid_idx_ = 0;

      for (auto *tag : this->binary_sensors_)
        tag->process(rfid_uid);

      if (this->ndef_current_uid_ == rfid_uid) {
        // Same tag still present from a previous poll; nothing new to report.
        this->pcd_antenna_off_();
        this->state_ = STATE_INIT;
        return;
      }

      // Keep the tag selected (antenna stays on, state_ stays put) and read its NDEF content
      // before reporting anything.
      this->ndef_begin_read_(std::move(rfid_uid));
      break;
    }
    case STATE_DONE: {
      if (!this->ndef_current_uid_.empty()) {
        if (!this->ndef_triggers_ontagremoved_.empty()) {
          nfc::NfcTagUid uid(this->ndef_current_uid_.begin(), this->ndef_current_uid_.end());
          auto tag = make_unique<nfc::NfcTag>(uid, nfc::NFC_FORUM_TYPE_2);
          for (auto *trigger : this->ndef_triggers_ontagremoved_)
            trigger->process(tag);
        }
        char uid_buf[format_hex_pretty_size(10)];
        ESP_LOGV(TAG, "Tag '%s' removed",
                 format_hex_pretty_to(uid_buf, this->ndef_current_uid_.data(), this->ndef_current_uid_.size(), '-'));
      }
      this->ndef_current_uid_.clear();
      this->state_ = STATE_INIT;
      break;
    }
    default:
      break;
  }
}

void RC522Ndef::ndef_begin_read_(std::vector<uint8_t> &&rfid_uid) {
  this->ndef_uid_ = std::move(rfid_uid);
  this->ndef_data_.clear();
  this->ndef_step_ = STEP_INITIAL;
  this->ndef_message_length_ = 0;
  this->ndef_message_start_ = 0;
  this->ndef_bytes_needed_ = 16;
  this->ndef_request_page_(3);
}

void RC522Ndef::ndef_request_page_(uint8_t page) {
  this->ndef_next_page_ = page;
  uint8_t cmd[2] = {PICC_CMD_MF_READ, page};
  this->pcd_calculate_crc_(cmd, 2);
  this->ndef_phase_ = NDEF_CALC_CRC;
}

void RC522Ndef::ndef_transceive_(uint8_t send_len) {
  delayMicroseconds(1000);
  this->ndef_send_len_ = send_len;
  this->pcd_write_register(COMMAND_REG, PCD_IDLE);
  this->pcd_write_register(COM_IRQ_REG, 0x7F);
  this->pcd_write_register(FIFO_LEVEL_REG, 0x80);
  this->pcd_write_register(FIFO_DATA_REG, send_len, this->ndef_buf_);
  this->pcd_write_register(BIT_FRAMING_REG, 0x00);  // byte-aligned frame, not a REQA-style short frame
  this->pcd_write_register(COMMAND_REG, PCD_TRANSCEIVE);
  this->pcd_set_register_bit_mask_(BIT_FRAMING_REG, 0x80);  // StartSend=1
  this->awaiting_comm_ = true;
  this->awaiting_comm_time_ = millis();
  this->ndef_phase_ = NDEF_TRANSCEIVE;
}

RC522Ndef::StatusCode RC522Ndef::ndef_await_transceive_() {
  if (millis() - this->awaiting_comm_time_ < 2)
    return STATUS_WAITING;
  uint8_t n = this->pcd_read_register(COM_IRQ_REG);
  if (n & 0x01) {  // TimerIRq: nothing received in time
    this->ndef_back_length_ = 0;
    return STATUS_TIMEOUT;
  }
  if (!(n & 0x30)) {  // RxIRq | IdleIRq not yet set
    if (millis() - this->awaiting_comm_time_ < 40)
      return STATUS_WAITING;
    this->ndef_back_length_ = 0;
    return STATUS_TIMEOUT;
  }
  uint8_t error_reg_value = this->pcd_read_register(ERROR_REG);
  if (error_reg_value & 0x13) {  // BufferOvfl | ParityErr | ProtocolErr
    return STATUS_ERROR;
  }

  n = this->pcd_read_register(FIFO_LEVEL_REG);
  if (n > sizeof(this->ndef_buf_))
    return STATUS_NO_ROOM;
  this->ndef_back_length_ = n;
  this->pcd_read_register(FIFO_DATA_REG, n, this->ndef_buf_, 0);

  if (error_reg_value & 0x08)  // CollErr -- shouldn't happen once selected
    return STATUS_COLLISION;

  return STATUS_OK;
}

void RC522Ndef::ndef_on_block_done_() {
  if (this->ndef_back_length_ < 16) {
    ESP_LOGW(TAG, "Ultralight page read returned only %d bytes, giving up on NDEF for this tag",
             this->ndef_back_length_);
    this->ndef_message_length_ = 0;
    this->ndef_data_.clear();
    this->ndef_finish_();
    return;
  }

  uint16_t take = this->ndef_bytes_needed_ < 16 ? this->ndef_bytes_needed_ : 16;
  this->ndef_data_.insert(this->ndef_data_.end(), this->ndef_buf_, this->ndef_buf_ + take);
  this->ndef_bytes_needed_ -= take;

  if (this->ndef_bytes_needed_ > 0) {
    this->ndef_request_page_(this->ndef_next_page_ + 4);
    return;
  }

  if (this->ndef_step_ == STEP_INITIAL) {
    bool formatted = (this->ndef_data_[P4_OFFSET + 0] != 0xFF) || (this->ndef_data_[P4_OFFSET + 1] != 0xFF) ||
                      (this->ndef_data_[P4_OFFSET + 2] != 0xFF) || (this->ndef_data_[P4_OFFSET + 3] != 0xFF);
    bool found = false;
    if (formatted) {
      if (this->ndef_data_[P4_OFFSET + 0] == 0x03) {
        this->ndef_message_length_ = this->ndef_data_[P4_OFFSET + 1];
        this->ndef_message_start_ = 2;
        found = true;
      } else if (this->ndef_data_[P4_OFFSET + 5] == 0x03) {
        this->ndef_message_length_ = this->ndef_data_[P4_OFFSET + 6];
        this->ndef_message_start_ = 7;
        found = true;
      }
    }
    if (!found || this->ndef_message_length_ == 0) {
      ESP_LOGV(TAG, "No NDEF TLV found on tag");
      this->ndef_message_length_ = 0;
      this->ndef_finish_();
      return;
    }
    this->ndef_start_extra_read_();
    return;
  }

  // STEP_EXTRA finished -- trim off the page-3 capability container and everything before the
  // NDEF message payload, leaving exactly ndef_message_length_ bytes.
  this->ndef_data_.erase(this->ndef_data_.begin(), this->ndef_data_.begin() + this->ndef_message_start_ + 4);
  this->ndef_finish_();
}

void RC522Ndef::ndef_start_extra_read_() {
  uint16_t need_total = static_cast<uint16_t>(this->ndef_message_start_) + this->ndef_message_length_;
  if (need_total <= INITIAL_USABLE) {
    this->ndef_data_.erase(this->ndef_data_.begin(), this->ndef_data_.begin() + this->ndef_message_start_ + 4);
    this->ndef_finish_();
    return;
  }
  this->ndef_step_ = STEP_EXTRA;
  this->ndef_bytes_needed_ = need_total - INITIAL_USABLE;
  this->ndef_request_page_(7);  // MIFARE_ULTRALIGHT_DATA_START_PAGE (4) + 3
}

void RC522Ndef::ndef_finish_() {
  this->pcd_antenna_off_();
  this->state_ = STATE_INIT;
  this->ndef_phase_ = NDEF_NONE;

  nfc::NfcTagUid uid(this->ndef_uid_.begin(), this->ndef_uid_.end());
  std::unique_ptr<nfc::NfcTag> tag;
  if (this->ndef_message_length_ > 0 && !this->ndef_data_.empty()) {
    tag = make_unique<nfc::NfcTag>(uid, nfc::NFC_FORUM_TYPE_2, this->ndef_data_);
  } else {
    tag = make_unique<nfc::NfcTag>(uid, nfc::NFC_FORUM_TYPE_2);
  }

  char uid_buf[format_hex_pretty_size(10)];
  ESP_LOGD(TAG, "Found new tag '%s'%s", format_hex_pretty_to(uid_buf, this->ndef_uid_.data(), this->ndef_uid_.size(), '-'),
           tag->has_ndef_message() ? " (NDEF read)" : " (no NDEF)");

  this->ndef_current_uid_ = this->ndef_uid_;

  for (auto *trigger : this->ndef_triggers_ontag_)
    trigger->process(tag);

  this->ndef_uid_.clear();
  this->ndef_data_.clear();
}

}  // namespace esphome::rc522_ndef
