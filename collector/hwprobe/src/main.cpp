// AuditCore hwprobe: emit a single JSON document describing this host's
// hardware topology. Designed to be invoked by the Go collector as an
// allowlisted tool. Read-only; no privileges required beyond what hwloc
// needs to walk /sys.

#include "json_writer.hpp"
#include "topology.hpp"

#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <iostream>
#include <string>
#include <string_view>
#include <unistd.h>

namespace ac {
#ifdef AC_HAVE_SENSORS
void write_thermals(JsonWriter& w);
#endif
#ifdef AC_HAVE_NVML
void write_gpus(JsonWriter& w);
#endif
} // namespace ac

static std::string iso_now() {
    std::time_t t = std::time(nullptr);
    std::tm tm{};
    gmtime_r(&t, &tm);
    char buf[32];
    std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &tm);
    return buf;
}

static std::string hostname_or_unknown() {
    char buf[256] = {0};
    if (gethostname(buf, sizeof(buf) - 1) == 0) return buf;
    return "unknown";
}

int main(int argc, char** argv) {
    bool want_version = false;
    for (int i = 1; i < argc; ++i) {
        std::string_view a{argv[i]};
        if (a == "--version" || a == "-v") want_version = true;
        else if (a == "--help" || a == "-h") {
            std::cout << "auditcore hwprobe 0.1.0\n"
                         "Usage: hwprobe [--version]\n"
                         "Emits a JSON document describing host hardware.\n";
            return 0;
        }
    }
    if (want_version) {
        std::cout << "auditcore hwprobe 0.1.0\n";
        return 0;
    }

    ac::JsonWriter w{std::cout};
    w.begin_object();
    w.kv_string("schema", "auditcore.hwprobe.v1");
    w.kv_string("collected_at", iso_now());
    w.kv_string("hostname", hostname_or_unknown());
    w.kv_bool("has_sensors",
#ifdef AC_HAVE_SENSORS
              true
#else
              false
#endif
    );
    w.kv_bool("has_nvml",
#ifdef AC_HAVE_NVML
              true
#else
              false
#endif
    );

    ac::write_topology(w);

#ifdef AC_HAVE_SENSORS
    ac::write_thermals(w);
#endif
#ifdef AC_HAVE_NVML
    ac::write_gpus(w);
#endif

    w.end_object();
    std::cout << '\n';
    return 0;
}
