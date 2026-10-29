#include <chrono>
#include <condition_variable>
#include <iostream>
#include <memory>
#include <mutex>
#include <string>

#include <aotai_sdk/client.hpp>
#include <weld_interfaces/msg/at_robot_status.hpp>
#include <weld_interfaces/srv/at_string_generic.hpp>

namespace {
int usage() {
  std::cerr << "Usage: aotai_ros2_sdk_query --connect [--prefix PREFIX] "
               "[--request robot_status] [--timeout-ms N] [--topic]\n";
  return 64;
}
} // namespace

int main(int argc, char **argv) {
  bool connect = false;
  bool topic = false;
  std::string prefix;
  std::string request_data = "robot_status";
  int timeout_ms = 3000;
  for (int index = 1; index < argc; ++index) {
    const std::string argument(argv[index]);
    const auto value = [&](const char *flag, std::string &output) -> bool {
      if (argument != flag || ++index >= argc)
        return false;
      output = argv[index];
      return true;
    };
    if (argument == "--connect")
      connect = true;
    else if (argument == "--topic")
      topic = true;
    else if (value("--prefix", prefix) || value("--request", request_data)) {
    } else if (argument == "--timeout-ms" && ++index < argc) {
      try {
        timeout_ms = std::stoi(argv[index]);
      } catch (...) {
        return usage();
      }
    } else
      return usage();
  }
  if (!connect || timeout_ms <= 0)
    return usage();

  try {
    // These callback-owned objects intentionally precede Client: if an
    // exception unwinds, Client joins its callback thread before they die.
    // cppcheck-suppress variableScope -- must outlive Client callback during unwind.
    bool received = false;
    std::mutex mutex;
    std::condition_variable changed;
    rclcpp::SubscriptionBase::SharedPtr subscription;

    // Client owns a private ROS Context, node and SingleThreadedExecutor.
    // It intentionally has no external node/executor injection API.
    aotai_sdk::Client client(prefix, "aotai_sdk_robot_status_demo");
    auto request = std::make_shared<weld_interfaces::srv::ATStringGeneric::Request>();
    request->id = "";
    request->data = request_data;
    const auto response = client.call<weld_interfaces::srv::ATStringGeneric>(
        "/at/robot/status", request, std::chrono::milliseconds(timeout_ms));
    const aotai_sdk::GenericReply reply{response->status, response->data,
                                        response->message};
    std::cout << "status=" << reply.status << " data=" << reply.data
              << " message=" << reply.message << "\n";

    if (topic) {
      subscription = client.subscribe<weld_interfaces::msg::ATRobotStatus>(
          "/at/robot/get_real_time_status", 10,
          [&](weld_interfaces::msg::ATRobotStatus::SharedPtr message) {
            std::cout << "topic connect_status=" << message->connect_status << "\n";
            {
              std::lock_guard<std::mutex> lock(mutex);
              received = true;
            }
            changed.notify_one();
          });
      std::unique_lock<std::mutex> lock(mutex);
      const bool topic_received = changed.wait_for(
          lock, std::chrono::milliseconds(timeout_ms), [&] { return received; });
      // Never join Client's callback thread while this mutex is held: a queued
      // callback may be waiting to set received.
      lock.unlock();
      if (!topic_received) {
        subscription.reset();
        client.close();
        std::cerr << "topic feedback timeout\n";
        return 3;
      }
      subscription.reset(); // Releases this subscription before Client::close().
    }
    client.close(); // Joins the SDK callback thread before this process exits.
    std::cout << "SDK client closed\n";
    return reply.accepted() ? 0 : 2;
  } catch (const aotai_sdk::Error &error) {
    std::cerr << "SDK error kind=" << static_cast<int>(error.kind)
              << ": " << error.what() << "\n";
  } catch (const std::exception &error) {
    std::cerr << "SDK query failed: " << error.what() << "\n";
  }
  return 3;
}
