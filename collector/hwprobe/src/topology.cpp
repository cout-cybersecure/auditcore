#include "topology.hpp"

#include <hwloc.h>

#include <cstring>
#include <string>

namespace ac {

namespace {

const char* attr_or(const char* s) { return s ? s : ""; }

void write_pci(JsonWriter& w, hwloc_topology_t topo) {
    w.key("pci_devices");
    w.begin_array();
    hwloc_obj_t obj = nullptr;
    while ((obj = hwloc_get_next_pcidev(topo, obj)) != nullptr) {
        w.begin_object();
        w.kv_uint("domain",   obj->attr->pcidev.domain);
        w.kv_uint("bus",      obj->attr->pcidev.bus);
        w.kv_uint("dev",      obj->attr->pcidev.dev);
        w.kv_uint("func",     obj->attr->pcidev.func);
        w.kv_uint("class_id", obj->attr->pcidev.class_id);
        w.kv_uint("vendor_id", obj->attr->pcidev.vendor_id);
        w.kv_uint("device_id", obj->attr->pcidev.device_id);
        if (obj->name) w.kv_string("name", obj->name);
        w.end_object();
    }
    w.end_array();
}

} // namespace

void write_topology(JsonWriter& w) {
    hwloc_topology_t topo;
    if (hwloc_topology_init(&topo) != 0) {
        w.kv_string("error", "hwloc_topology_init failed");
        return;
    }
    // PCI + OS device discovery.
    hwloc_topology_set_io_types_filter(topo, HWLOC_TYPE_FILTER_KEEP_ALL);

    if (hwloc_topology_load(topo) != 0) {
        hwloc_topology_destroy(topo);
        w.kv_string("error", "hwloc_topology_load failed");
        return;
    }

    // Top-level summary keys.
    int numa = hwloc_get_nbobjs_by_type(topo, HWLOC_OBJ_NUMANODE);
    int pkgs = hwloc_get_nbobjs_by_type(topo, HWLOC_OBJ_PACKAGE);
    int cores = hwloc_get_nbobjs_by_type(topo, HWLOC_OBJ_CORE);
    int pus = hwloc_get_nbobjs_by_type(topo, HWLOC_OBJ_PU);

    w.kv_int("numa_nodes", numa < 0 ? 0 : numa);
    w.kv_int("packages",   pkgs < 0 ? 0 : pkgs);
    w.kv_int("cores",      cores < 0 ? 0 : cores);
    w.kv_int("pus",        pus < 0 ? 0 : pus);

    // L3 size.
    hwloc_obj_t l3 = hwloc_get_obj_by_type(topo, HWLOC_OBJ_L3CACHE, 0);
    if (l3 != nullptr) {
        w.kv_uint("l3_cache_bytes", l3->attr->cache.size);
    }

    // Machine identity from hwloc info strings.
    hwloc_obj_t root = hwloc_get_root_obj(topo);
    if (root != nullptr) {
        for (unsigned i = 0; i < root->infos_count; ++i) {
            const char* name = attr_or(root->infos[i].name);
            const char* val  = attr_or(root->infos[i].value);
            if (std::strcmp(name, "DMIProductName") == 0) {
                w.kv_string("machine_model", val);
            } else if (std::strcmp(name, "DMIBIOSVendor") == 0) {
                w.kv_string("bios_vendor", val);
            } else if (std::strcmp(name, "DMIBIOSVersion") == 0) {
                w.kv_string("bios_version", val);
            } else if (std::strcmp(name, "OSName") == 0) {
                w.kv_string("os_name", val);
            } else if (std::strcmp(name, "OSRelease") == 0) {
                w.kv_string("os_release", val);
            } else if (std::strcmp(name, "Architecture") == 0) {
                w.kv_string("architecture", val);
            }
        }
    }

    // NUMA detail.
    w.key("numa_detail");
    w.begin_array();
    for (int i = 0; i < numa; ++i) {
        hwloc_obj_t n = hwloc_get_obj_by_type(topo, HWLOC_OBJ_NUMANODE, i);
        if (n == nullptr) continue;
        w.begin_object();
        w.kv_int("index", static_cast<std::int64_t>(n->logical_index));
        w.kv_uint("memory_bytes", n->attr->numanode.local_memory);
        w.end_object();
    }
    w.end_array();

    write_pci(w, topo);
    hwloc_topology_destroy(topo);
}

} // namespace ac
