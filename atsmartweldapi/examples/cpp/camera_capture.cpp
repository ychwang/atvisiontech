#include <aotai_sdk/client.hpp>
#include <cmath>
#include <fstream>
#include <iostream>
#include <thread>
// cppcheck-suppress constParameter -- standard main signature.
int main(int argc, char **argv) {
  try {
    bool execute = false;
    std::string file, prefix;
    double seconds = 1.0;
    for (int i = 1; i < argc; ++i) {
      const std::string option = argv[i];
      if (option == "--execute")
        execute = true;
      else if (option == "--config" && i + 1 < argc)
        file = argv[++i];
      else if (option == "--prefix" && i + 1 < argc)
        prefix = argv[++i];
      else if (option == "--seconds" && i + 1 < argc) {
        const std::string value = argv[++i];
        std::size_t consumed;
        seconds = std::stod(value, &consumed);
        if (consumed != value.size())
          throw std::invalid_argument("invalid seconds");
      } else
        throw std::invalid_argument("unknown or incomplete option");
    }
    if (!std::isfinite(seconds) || seconds <= 0)
      throw std::invalid_argument("seconds must be finite and positive");
    if (!execute) {
      std::cout << "Offline: --execute --config CONFIG.json starts/stops "
                   "acquisition, without downloading.\n";
      return 0;
    }
    if (file.empty())
      throw std::invalid_argument("--config required");
    std::ifstream input(file);
    if (!input)
      throw std::runtime_error("cannot open config");
    aotai_sdk::json config;
    input >> config;
    if (!config.is_object() || config.value("command_type", "") != "connect" ||
        !config.contains("guid") || !config["guid"].is_string() ||
        config["guid"].get<std::string>().empty())
      throw std::invalid_argument(
          "config needs command_type=connect and actual guid from discovery");
    aotai_sdk::Client client(prefix);
    auto check = [](const aotai_sdk::GenericReply &reply) {
      std::cout << reply.message << '\n';
      if (!reply.accepted())
        throw std::runtime_error("camera rejected: " + reply.message);
    };
    check(client.camera_config(config.dump()));
    auto status = client.camera_config("{\"command_type\":\"connect_status\"}");
    check(status);
    if (aotai_sdk::json::parse(status.message).value("connect_status", 0) != 1)
      throw std::runtime_error("camera not connected: " + status.message);
    check(client.camera_control("{\"command_type\":\"start_capture\"}"));
    std::this_thread::sleep_for(std::chrono::duration<double>(seconds));
    check(client.camera_control("{\"command_type\":\"stop_capture\"}"));
    std::cout << "Capture stop acknowledged. Download separately; frame/unit "
                 "metadata is not inferred.\n";
    client.close();
    return 0;
  } catch (const std::exception &error) {
    std::cerr << error.what() << "; acquisition outcome may be unknown\n";
    return 2;
  }
}
