from esphome import automation
import esphome.codegen as cg
from esphome.components import nfc, rc522, spi
import esphome.config_validation as cv
from esphome.const import CONF_ID, CONF_ON_TAG, CONF_ON_TAG_REMOVED, CONF_TRIGGER_ID

# Stock rc522/rc522_spi only expose the tag UID -- no NDEF support (pn532 has it, rc522 doesn't).
# This component subclasses rc522::RC522 + spi::SPIDevice directly in C++ (not RC522Spi -- that has
# its own CONFIG_SCHEMA requiring cs_pin, which would try to instantiate a second, unconfigured
# component if pulled in via AUTO_LOAD) and adds a Type 2 Tag NDEF read after each UID find, so
# on_tag/on_tag_removed behave like pn532's: `x` is the UID string, `tag` is an nfc::NfcTag with
# has_ndef_message()/get_ndef_message() available.

CODEOWNERS = ["@FizykPSX"]
DEPENDENCIES = ["spi"]
AUTO_LOAD = ["rc522", "nfc"]
MULTI_CONF = True

rc522_ndef_ns = cg.esphome_ns.namespace("rc522_ndef")
RC522Ndef = rc522_ndef_ns.class_("RC522Ndef", rc522.RC522, spi.SPIDevice)

CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(RC522Ndef),
            cv.Optional(CONF_ON_TAG): automation.validate_automation(
                {
                    cv.GenerateID(CONF_TRIGGER_ID): cv.declare_id(nfc.NfcOnTagTrigger),
                }
            ),
            cv.Optional(CONF_ON_TAG_REMOVED): automation.validate_automation(
                {
                    cv.GenerateID(CONF_TRIGGER_ID): cv.declare_id(nfc.NfcOnTagTrigger),
                }
            ),
        }
    )
    .extend(cv.polling_component_schema("1s"))
    .extend(spi.spi_device_schema(cs_pin_required=True))
)

FINAL_VALIDATE_SCHEMA = spi.final_validate_device_schema(
    "rc522_ndef", require_miso=True, require_mosi=True
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await spi.register_spi_device(var, config)

    for conf in config.get(CONF_ON_TAG, []):
        trigger = cg.new_Pvariable(conf[CONF_TRIGGER_ID])
        cg.add(var.register_ontag_trigger(trigger))
        await automation.build_automation(
            trigger, [(cg.std_string, "x"), (nfc.NfcTag, "tag")], conf
        )

    for conf in config.get(CONF_ON_TAG_REMOVED, []):
        trigger = cg.new_Pvariable(conf[CONF_TRIGGER_ID])
        cg.add(var.register_ontagremoved_trigger(trigger))
        await automation.build_automation(
            trigger, [(cg.std_string, "x"), (nfc.NfcTag, "tag")], conf
        )
