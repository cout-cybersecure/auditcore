#include "json_writer.hpp"

#include <cstdio>

namespace ac {

void JsonWriter::begin_object() {
    maybe_comma();
    out_ << '{';
    container_stack_.push_back('o');
    first_flag_.push_back('1');
    pending_key_ = false;
}

void JsonWriter::end_object() {
    out_ << '}';
    container_stack_.pop_back();
    first_flag_.pop_back();
}

void JsonWriter::begin_array() {
    maybe_comma();
    out_ << '[';
    container_stack_.push_back('a');
    first_flag_.push_back('1');
}

void JsonWriter::end_array() {
    out_ << ']';
    container_stack_.pop_back();
    first_flag_.pop_back();
}

void JsonWriter::key(std::string_view k) {
    if (!first_flag_.empty() && first_flag_.back() == '0') {
        out_ << ',';
    }
    if (!first_flag_.empty()) {
        first_flag_.back() = '0';
    }
    write_string(k);
    out_ << ':';
    pending_key_ = true;
}

void JsonWriter::maybe_comma() {
    if (pending_key_) {
        pending_key_ = false;
        return;
    }
    if (!first_flag_.empty()) {
        if (first_flag_.back() == '0') {
            out_ << ',';
        } else {
            first_flag_.back() = '0';
        }
    }
}

void JsonWriter::value_null() { maybe_comma(); out_ << "null"; }
void JsonWriter::value_bool(bool v) { maybe_comma(); out_ << (v ? "true" : "false"); }
void JsonWriter::value_int(std::int64_t v) { maybe_comma(); out_ << v; }
void JsonWriter::value_uint(std::uint64_t v) { maybe_comma(); out_ << v; }
void JsonWriter::value_string(std::string_view s) { maybe_comma(); write_string(s); }
void JsonWriter::value_raw_number_string(std::string_view s) { maybe_comma(); out_ << s; }

void JsonWriter::kv_string(std::string_view k, std::string_view v) { key(k); value_string(v); }
void JsonWriter::kv_int(std::string_view k, std::int64_t v)        { key(k); value_int(v); }
void JsonWriter::kv_uint(std::string_view k, std::uint64_t v)      { key(k); value_uint(v); }
void JsonWriter::kv_bool(std::string_view k, bool v)               { key(k); value_bool(v); }

void JsonWriter::write_string(std::string_view s) {
    out_ << '"';
    for (char c : s) {
        switch (c) {
            case '"':  out_ << "\\\""; break;
            case '\\': out_ << "\\\\"; break;
            case '\n': out_ << "\\n";  break;
            case '\r': out_ << "\\r";  break;
            case '\t': out_ << "\\t";  break;
            case '\b': out_ << "\\b";  break;
            case '\f': out_ << "\\f";  break;
            default:
                if (static_cast<unsigned char>(c) < 0x20) {
                    char buf[8];
                    std::snprintf(buf, sizeof(buf), "\\u%04x", c);
                    out_ << buf;
                } else {
                    out_ << c;
                }
        }
    }
    out_ << '"';
}

} // namespace ac
