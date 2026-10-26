#include <algorithm>
#include <aotai_sdk/client.hpp>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

// Default mode does not create database rows. --execute only accepts the
// isolated mock prefix; this example does not create process aggregates.
int main(int argc, char **argv) {
  bool execute = false;
  std::string prefix;
  for (int i = 1; i < argc; ++i) {
    if (std::string(argv[i]) == "--execute")
      execute = true;
    else if (std::string(argv[i]) == "--prefix" && i + 1 < argc)
      prefix = argv[++i];
    else {
      std::cerr
          << "usage: process_workflow [--execute --prefix /api_process_mock]\n";
      return 2;
    }
  }
  if (!execute) {
    std::cout
        << "Offline: example class_add data={\\\"name\\\":\\\"平角焊\\\"}; "
           "this example does not submit process_add/update requests.\n";
    return 0;
  }
  if (prefix != "/api_process_mock") {
    std::cerr << "--execute is restricted to --prefix /api_process_mock in "
                 "this delivery\n";
    return 2;
  }
  try {
    aotai_sdk::Client client(prefix);
    const auto add = client.process_class_add({{"name", "平角焊"}});
    if (!add.accepted())
      throw std::runtime_error(add.message);
    const auto id_text =
        aotai_sdk::json::parse(add.data).at("id").get<std::string>();
    if (id_text.empty() ||
        !std::all_of(id_text.begin(), id_text.end(),
                     [](unsigned char ch) { return ch >= '0' && ch <= '9'; }))
      throw std::invalid_argument(
          "process_class_add returned invalid decimal data.id");
    std::size_t consumed = 0;
    const long long parsed_id = std::stoll(id_text, &consumed);
    if (consumed != id_text.size() || parsed_id <= 0 ||
        parsed_id > std::numeric_limits<int>::max())
      throw std::invalid_argument(
          "process_class_add returned invalid positive data.id");
    const int id = static_cast<int>(parsed_id);
    const auto update =
        client.process_class_update({{"id", id}, {"name", "平焊"}});
    if (!update.accepted())
      throw std::runtime_error(update.message);
    const auto rows = client.process_class_list();
    if (!rows.accepted())
      throw std::runtime_error(rows.message);
    std::cout << "created/updated class id=" << id
              << "; group management only; no process_add sent\n";
    const auto remove = client.process_class_delete(id);
    if (!remove.accepted())
      throw std::runtime_error(remove.message);
    client.close();
    return 0;
  } catch (const std::exception &e) {
    std::cerr << "process workflow failed: " << e.what() << "\n";
    return 3;
  }
}
