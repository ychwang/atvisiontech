#include <aotai_sdk/client.hpp>
#include <iostream>
// Run `aotai_cpp_control status|current` for a query, or a control plus UID.
// Explicit task control only. Never called by basic/multipass examples.
int main(int argc, char **argv) {
  const std::string command = argc > 1 ? argv[1] : "";
  const bool query = command == "status" || command == "current";
  const bool control = command == "start" || command == "pause" ||
                       command == "continue" || command == "stop" ||
                       command == "recover";
  if ((!query && !control) || (query ? argc != 2 : argc != 3)) {
    std::cerr << "usage: control <start|pause|continue|stop|recover> "
                 "<expected-project-uid>\n";
    return 2;
  }
  try {
    aotai_sdk::Client c;
    if (query) {
      auto response = c.task_command(command == "status" ? "get_task_status"
                                                         : "get_current_task");
      std::cout << response.status << " " << response.message << " "
                << response.data << "\n";
      return response.accepted() ? 0 : 3;
    }
    auto current = c.task_command("get_current_task");
    if (!current.accepted())
      throw std::runtime_error(current.message);
    auto j = aotai_sdk::json::parse(current.data);
    if (j.value("project", aotai_sdk::json::object()).value("uid", "") !=
        argv[2])
      throw std::runtime_error(
          "current task UID mismatch: no control command was sent");
    aotai_sdk::GenericReply reply;
    if (command == "recover") {
      auto status = c.task_command("get_task_status");
      std::cout << status.status << " " << status.message << " " << status.data
                << "\n";
      return status.accepted() ? 0 : 3; // Never resend/resume automatically.
    }
    if (command == "start")
      reply = c.task_start();
    else if (command == "pause")
      reply = c.task_pause();
    else if (command == "continue")
      reply = c.task_continue();
    else if (command == "stop")
      reply = c.task_stop(); // task_destroy, not ROS Action cancel.
    else
      throw std::runtime_error("unknown explicit control command");
    std::cout << reply.status << " " << reply.message << "\n";
    return reply.accepted() ? 0 : 3;
  } catch (const std::exception &e) {
    std::cerr << e.what() << "\n";
    return 1;
  }
}
