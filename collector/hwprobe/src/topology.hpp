#pragma once

#include "json_writer.hpp"

namespace ac {

// Emits the "topology" section + top-level summary keys into `w`.
// Uses libhwloc for NUMA / cache / PCI tree discovery.
void write_topology(JsonWriter& w);

} // namespace ac
