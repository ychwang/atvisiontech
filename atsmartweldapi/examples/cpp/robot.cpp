// The example subtype i7 must be replaced with the configured robot model.
// This is not model certification. Default execution remains offline.
#include <aotai_sdk/client.hpp>
#include <fstream>
#include <iostream>
using aotai_sdk::Client;
using aotai_sdk::json;
static void check(const aotai_sdk::GenericReply &r, const char *step) {
  std::cout << step << ": status=" << r.status << " result=" << r.result
            << " message=" << r.message << "\n";
  if (r.status != 200)
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
      std::cerr << "usage: robot [--execute --endpoint-prefix PREFIX] [--input "
                   "FILE]\n";
      return 64;
    }
  }
  if (!execute) {
    std::cout << "offline: no robot request is sent\n";
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
    const auto &r = spec.at("robot");
    const auto &step = r.at("step");
    Client c(prefix);
    // Initialize/configure, then check every stage before sending a motion
    // request.
    check(c.robot_init(r.at("robot_type"), r.at("robot_subtype"),
                       r.at("robot_ip"), r.at("local_ip"), r.at("robot_scope")),
          "init");
    check(c.robot_connect(true), "connect");
    auto power = c.robot_power(true);
    check(power, "power");
    if (!power.message.empty())
      throw std::runtime_error(
          "power succeeded with a load/TCP warning; no motion is sent: " +
          power.message);
    check(c.robot_subscribe(), "subscribe");
    auto state = c.robot_status();
    check(state, "status");
    auto j = json::parse(state.data);
    if (!j.value("connect_status", false) || !j.value("power_status", false) ||
        !j.value("subscribe_status", false))
      throw std::runtime_error("robot state does not confirm prerequisites");
    auto pose = c.robot_pose();
    if (pose->cur_pos.size() != 6 || pose->joint_pos.size() != 6 ||
        pose->flan_pos.size() != 6)
      throw std::runtime_error("robot pose shape is invalid");
    check(c.robot_move_step(step.at("move_type"), step.at("direction"),
                            step.at("speed")),
          "move_step");
    check(c.robot_stop(), "move_stop");
    auto stopped = c.robot_status();
    check(stopped, "status_after_stop");
    const auto stop_state = json::parse(stopped.data);
    if (!stop_state.contains("motion_status") ||
        !stop_state["motion_status"].is_number_integer() ||
        stop_state["motion_status"].get<int>() != 0)
      throw std::runtime_error(
          "move_stop accepted but motion status is not confirmed idle; raw=" +
          stopped.data);
    c.close();
    return 0;
  } catch (const std::exception &e) {
    std::cerr << "SDK/input error: " << e.what() << "\n";
    return 2;
  }
}
