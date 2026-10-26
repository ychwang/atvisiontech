#include <aotai_sdk/client.hpp>
#include <weld_interfaces/srv/at_string_generic.hpp>

#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

namespace {
using aotai_sdk::json;

int positive_source_id(const char *text) {
  try {
    std::size_t parsed = 0;
    const int value = std::stoi(text, &parsed);
    if (parsed != std::string(text).size() || value <= 0)
      throw std::invalid_argument("not positive");
    return value;
  } catch (const std::exception &) {
    throw std::invalid_argument("--source-id must be a positive integer");
  }
}

const std::string &require_json_object(const std::string &raw, const char *label) {
  try {
    if (!json::parse(raw).is_object())
      throw std::invalid_argument("not an object");
  } catch (const std::exception &) {
    // Quote rather than normalize the server string, so diagnostics preserve
    // malformed/non-object data without making it executable JSON input.
    throw std::invalid_argument(std::string(label) +
                                " response data must be a JSON object; raw=" +
                                json(raw).dump());
  }
  return raw;
}

void usage() {
  std::cerr << "usage: process_inspect [--connect --source-id ID] [--prefix /mock]\n";
}
}  // namespace

// Default is offline. --connect only reads /at/data/process_detail and
// /at/data/system_config_detail_by_process; it never creates, updates, or
// retries a process database operation.
// cppcheck-suppress constParameter -- preserve the standard C++ main signature.
int main(int argc, char **argv) {
  bool connect = false;
  std::string prefix;
  const char *source_text = nullptr;
  for (int i = 1; i < argc; ++i) {
    const std::string argument = argv[i];
    if (argument == "--connect")
      connect = true;
    else if (argument == "--source-id" && i + 1 < argc)
      source_text = argv[++i];
    else if (argument == "--prefix" && i + 1 < argc)
      prefix = argv[++i];
    else {
      usage();
      return 2;
    }
  }
  if (!connect) {
    std::cout << "Offline: use --connect --source-id ID to read two process "
                 "responses; no DB write is available.\n";
    return 0;
  }
  if (!source_text) {
    usage();
    return 2;
  }

  try {
    const int source_id = positive_source_id(source_text);
    aotai_sdk::Client client(prefix);
    const auto detail = client.process_detail(source_id);
    if (!detail.accepted()) {
      std::cerr << "process_detail rejected: " << detail.status << " "
                << detail.message << " raw=" << detail.data << "\n";
      return 3;
    }
    auto request = std::make_shared<weld_interfaces::srv::ATStringGeneric::Request>();
    request->id = std::to_string(source_id);
    request->data = "";
    const auto config = client.call<weld_interfaces::srv::ATStringGeneric>(
        "/at/data/system_config_detail_by_process", request);
    if (config->status != 200) {
      std::cerr << "system_config_detail_by_process rejected: " << config->status
                << " " << config->message << " raw=" << config->data << "\n";
      return 3;
    }
    const auto &detail_raw = require_json_object(detail.data, "process_detail");
    const auto &config_raw =
        require_json_object(config->data, "system_config_detail_by_process");
    // Keep the two server-returned documents separate and byte-for-byte intact.
    std::cout << "process_detail.data=" << detail_raw << "\n";
    std::cout << "system_config_detail_by_process.data=" << config_raw << "\n";
    client.close();
    return 0;
  } catch (const std::exception &error) {
    std::cerr << "process inspection failed: " << error.what() << "\n";
    return 3;
  }
}
