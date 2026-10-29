#include <aotai_sdk/client.hpp>
#include <fstream>
#include <iomanip>
#include <iostream>
using aotai_sdk::Client;
using aotai_sdk::json;
static void check(const aotai_sdk::GenericReply &r, const char *step) {
  std::cout << step << ": status=" << r.status << " result=" << r.result
            << " message=" << r.message << "\n";
  if (r.status != 200)
    throw std::runtime_error(std::string(step) + " rejected");
}
static void
check_float(const weld_interfaces::srv::ATFloat::Response::SharedPtr &r,
            const char *step) {
  std::cout << step << ": status=" << r->status
            << " result=" << std::setprecision(17) << r->result
            << " message=" << r->message << "\n";
  if (r->status != 200)
    throw std::runtime_error(std::string(step) + " rejected");
}
// cppcheck-suppress constParameter -- keep the ISO C++ main signature.
int main(int argc, char **argv) {
  bool execute = false;
  std::string prefix, input = "../../examples/data/device-control.json";
  for (int i = 1; i < argc; ++i) {
    std::string a = argv[i];
    if (a == "--execute")
      execute = true;
    else if (a == "--endpoint-prefix" && i + 1 < argc)
      prefix = argv[++i];
    else if (a == "--input" && i + 1 < argc)
      input = argv[++i];
    else {
      std::cerr << "usage: welder [--execute --endpoint-prefix PREFIX] "
                   "[--input FILE]\n";
      return 64;
    }
  }
  if (!execute) {
    std::cout << "offline: no welder request is sent\n";
    return 0;
  }
  try {
    std::ifstream file(input);
    if (!file)
      throw std::runtime_error("cannot open input");
    json spec;
    file >> spec;
    if (!spec.contains("demonstration_only") ||
        !spec["demonstration_only"].is_boolean())
      throw std::runtime_error(
          "demonstration_only must be an explicit boolean");
    if (spec.value("demonstration_only", false) && prefix != "/api_device_mock")
      throw std::runtime_error("demonstration input is mock-only");
    if (!spec.value("demonstration_only", false) &&
        !spec.value("site_confirmed", false))
      throw std::runtime_error("field input requires site_confirmed:true");
    const auto &w = spec.at("welder");
    Client c(prefix);
    check(c.welder_config("", w.at("config_data")), "config");
    check(c.welder_connect(w.at("weld_ip"), true), "connect");
    auto certified = c.welder_certify(w.at("certificate"));
    check(certified, "certify");
    if (certified.result != 1)
      throw std::runtime_error("certify result is not 1");
    check(c.welder_robot_ready(true), "robot_ready");
    check_float(c.welder_current(w.at("current")), "current");
    check(c.welder_synergic_mode(w.at("synergic_mode")), "synergic_mode");
    check_float(c.welder_voltage(w.at("voltage")), "voltage");
    auto enabled = c.welder_enable(w.at("enable"));
    check(enabled, "enable");
    if (enabled.result != w.at("enable").get<long long>())
      throw std::runtime_error("enable cache bit mismatch");
    check(c.welder_welding(true), "welding_accept");
    auto arc = c.welder_status("is_arcing");
    check(arc, "is_arcing");
    if (arc.result != 1)
      throw std::runtime_error("start was accepted but arc is not confirmed");
    check(c.welder_welding(false), "welding_stop_accept");
    auto stopped = c.welder_status("weld_operate");
    check(stopped, "weld_operate");
    if (stopped.result != 0)
      throw std::runtime_error(
          "stop was accepted but weld_operate is not zero");
    auto disabled = c.welder_enable(0);
    check(disabled, "disable");
    if (disabled.result != 0)
      throw std::runtime_error("disable cache bit is not 0");
    check(c.welder_robot_ready(false), "robot_not_ready");
    c.close();
    return 0;
  } catch (const std::exception &e) {
    std::cerr << "SDK/input error: " << e.what() << "\n";
    return 2;
  }
}
