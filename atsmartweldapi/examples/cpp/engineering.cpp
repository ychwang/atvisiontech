#include <aotai_sdk/client.hpp>
#include <iostream>
#include <optional>
#include <weld_interfaces/srv/at_query.hpp>
#include <weld_interfaces/srv/at_string_generic.hpp>
// cppcheck-suppress constParameter -- standard main signature.
int main(int argc, char **argv) {
  try {
    bool connect = false;
    std::string kind = "project", prefix;
    std::optional<int> id;
    for (int i = 1; i < argc; ++i) {
      const std::string option = argv[i];
      if (option == "--connect")
        connect = true;
      else if (option == "--kind" && i + 1 < argc)
        kind = argv[++i];
      else if (option == "--prefix" && i + 1 < argc)
        prefix = argv[++i];
      else if (option == "--id" && i + 1 < argc) {
        const std::string value = argv[++i];
        std::size_t consumed;
        id = std::stoi(value, &consumed);
        if (consumed != value.size() || *id <= 0)
          throw std::invalid_argument("--id must be positive");
      } else
        throw std::invalid_argument("unknown or incomplete option");
    }
    if (kind != "project" && kind != "workpiece")
      throw std::invalid_argument("--kind project|workpiece");
    if (!connect) {
      std::cout << "Offline. --connect lists the library; --connect --id ID "
                   "reads detail. No write path.\n";
      return 0;
    }
    const std::string stem =
        kind == "project" ? "/at/data/workpiece_task" : "/at/data/workpiece";
    aotai_sdk::Client client(prefix);
    std::string raw, message;
    int status;
    if (id) {
      auto request =
          std::make_shared<weld_interfaces::srv::ATStringGeneric::Request>();
      request->id = std::to_string(*id);
      request->data = "";
      auto reply = client.call<weld_interfaces::srv::ATStringGeneric>(
          stem + "_detail", request);
      status = reply->status;
      raw = reply->data;
      message = reply->message;
    } else {
      auto request = std::make_shared<weld_interfaces::srv::ATQuery::Request>();
      request->page_number = 1;
      request->items_per_page = 20;
      request->sort_field = "id";
      request->sort_descending = true;
      auto reply =
          client.call<weld_interfaces::srv::ATQuery>(stem + "_list", request);
      status = reply->status;
      raw = reply->data;
      message = reply->message;
    }
    if (status != 200)
      throw std::runtime_error("status=" + std::to_string(status) +
                               " message=" + message + " raw=" + raw);
    try {
      if (!aotai_sdk::json::parse(raw).is_object())
        throw std::invalid_argument("expected object");
    } catch (const std::exception &) {
      throw std::runtime_error("malformed library response; raw=" + raw);
    }
    std::cout
        << raw
        << "\nRead only: verify complete inverse mapping before update.\n";
    client.close();
    return 0;
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 2;
  }
}
