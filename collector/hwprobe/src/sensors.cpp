// Thermals via libsensors. Compiled only when AC_HAVE_SENSORS is defined.
#include "json_writer.hpp"

#ifdef AC_HAVE_SENSORS
#include <sensors/sensors.h>
#include <cstdio>

namespace ac {

void write_thermals(JsonWriter& w) {
    if (sensors_init(nullptr) != 0) {
        w.kv_string("thermals_error", "sensors_init failed");
        return;
    }
    w.key("thermals");
    w.begin_array();

    const sensors_chip_name* chip;
    int chip_nr = 0;
    while ((chip = sensors_get_detected_chips(nullptr, &chip_nr)) != nullptr) {
        char chip_name[256];
        sensors_snprintf_chip_name(chip_name, sizeof(chip_name), chip);

        const sensors_feature* feat;
        int feat_nr = 0;
        while ((feat = sensors_get_features(chip, &feat_nr)) != nullptr) {
            if (feat->type != SENSORS_FEATURE_TEMP) continue;
            const sensors_subfeature* sub =
                sensors_get_subfeature(chip, feat, SENSORS_SUBFEATURE_TEMP_INPUT);
            if (!sub) continue;
            double val = 0.0;
            if (sensors_get_value(chip, sub->number, &val) != 0) continue;

            char* label = sensors_get_label(chip, feat);
            w.begin_object();
            w.kv_string("chip",  chip_name);
            w.kv_string("label", label ? label : "");
            // Two-decimal Celsius.
            char tbuf[32];
            std::snprintf(tbuf, sizeof(tbuf), "%.2f", val);
            w.key("temp_c");
            w.value_raw_number_string(tbuf);
            w.end_object();
            free(label);
        }
    }

    w.end_array();
    sensors_cleanup();
}

} // namespace ac
#endif
