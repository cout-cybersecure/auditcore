// NVIDIA GPU inventory via NVML. Compiled only when AC_HAVE_NVML is defined.
#include "json_writer.hpp"

#ifdef AC_HAVE_NVML
#include <nvml.h>
#include <cstdio>

namespace ac {

void write_gpus(JsonWriter& w) {
    if (nvmlInit_v2() != NVML_SUCCESS) {
        // Driver not installed / no GPUs — emit empty array.
        w.key("gpus");
        w.begin_array(); w.end_array();
        return;
    }
    unsigned count = 0;
    nvmlDeviceGetCount_v2(&count);

    w.key("gpus");
    w.begin_array();
    for (unsigned i = 0; i < count; ++i) {
        nvmlDevice_t dev;
        if (nvmlDeviceGetHandleByIndex_v2(i, &dev) != NVML_SUCCESS) continue;

        char name[NVML_DEVICE_NAME_BUFFER_SIZE] = {0};
        nvmlDeviceGetName(dev, name, sizeof(name));

        nvmlMemory_t mem{};
        nvmlDeviceGetMemoryInfo(dev, &mem);

        unsigned temp = 0;
        nvmlDeviceGetTemperature(dev, NVML_TEMPERATURE_GPU, &temp);

        unsigned power_mw = 0;
        nvmlDeviceGetPowerUsage(dev, &power_mw);

        char uuid[NVML_DEVICE_UUID_V2_BUFFER_SIZE] = {0};
        nvmlDeviceGetUUID(dev, uuid, sizeof(uuid));

        w.begin_object();
        w.kv_uint("index", i);
        w.kv_string("name", name);
        w.kv_string("uuid", uuid);
        w.kv_uint("memory_total_bytes", mem.total);
        w.kv_uint("memory_used_bytes",  mem.used);
        w.kv_uint("temperature_c", temp);
        w.kv_uint("power_milliwatts", power_mw);
        w.end_object();
    }
    w.end_array();
    nvmlShutdown();
}

} // namespace ac
#endif
