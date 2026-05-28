// Minimal streaming JSON writer. Avoids pulling nlohmann/json so the binary
// stays small and dependency-free beyond hwloc/sensors/NVML.
#pragma once

#include <cstdint>
#include <ostream>
#include <string>
#include <string_view>

namespace ac {

class JsonWriter {
public:
    explicit JsonWriter(std::ostream& out) : out_(out) {}

    void begin_object();
    void end_object();
    void begin_array();
    void end_array();

    void key(std::string_view k);

    // Append a value in current container (handles comma-separation).
    void value_null();
    void value_bool(bool v);
    void value_int(std::int64_t v);
    void value_uint(std::uint64_t v);
    void value_string(std::string_view s);
    // Number written as a string so we never lose precision for 128-bit sizes.
    void value_raw_number_string(std::string_view s);

    // Shorthand: key + value in one call.
    void kv_string(std::string_view k, std::string_view v);
    void kv_int(std::string_view k, std::int64_t v);
    void kv_uint(std::string_view k, std::uint64_t v);
    void kv_bool(std::string_view k, bool v);

private:
    void maybe_comma();
    void write_string(std::string_view s);

    std::ostream& out_;
    // Stack of "first element" flags per nesting level.
    std::string container_stack_; // 'o' or 'a'
    std::string first_flag_;      // '1' = next element is first, '0' = needs comma
    bool pending_key_ = false;
};

} // namespace ac
