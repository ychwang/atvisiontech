#include <aotai_sdk/client.hpp>
#include <std_msgs/msg/string.hpp>
#include <weld_interfaces/msg/at_point_cloud.hpp>
#include <weld_interfaces/msg/at_robot_status.hpp>
#include <weld_interfaces/msg/at_welder_real_time_data.hpp>

#include <chrono>
#include <cmath>
#include <condition_variable>
#include <iostream>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>

// Default is offline. --connect subscribes only; it never controls a device.
// --prefix is for an isolated mock namespace, e.g. /api_sdk_mock.
// cppcheck-suppress constParameter -- preserve the standard C++ main signature.
int main(int argc, char **argv) {
  bool connect = false;
  std::string topic = "robot";
  std::string prefix;
  double seconds = 10.0;
  const auto usage = [] {
    std::cerr << "usage: subscribe [--connect] [--topic robot|welder|task|"
                 "camera-status|camera-points] [--seconds N] "
                 "[--prefix /isolated_mock]\n";
  };
  for (int i = 1; i < argc; ++i) {
    const std::string argument = argv[i];
    if (argument == "--connect")
      connect = true;
    else if (argument == "--topic" && i + 1 < argc)
      topic = argv[++i];
    else if (argument == "--prefix" && i + 1 < argc)
      prefix = argv[++i];
    else if (argument == "--seconds" && i + 1 < argc) {
      try {
        const std::string value = argv[++i];
        size_t parsed = 0;
        seconds = std::stod(value, &parsed);
        if (parsed != value.size())
          throw std::invalid_argument("trailing characters");
      } catch (const std::exception &) {
        std::cerr << "--seconds must be a finite positive number\n";
        usage();
        return 2;
      }
    } else {
      usage();
      return 2;
    }
  }
  const bool valid_topic =
      topic == "robot" || topic == "welder" || topic == "task" ||
      topic == "camera-status" || topic == "camera-points";
  if (!valid_topic || !std::isfinite(seconds) || seconds <= 0.0) {
    std::cerr << "--topic must be supported and --seconds must be finite and positive\n";
    usage();
    return 2;
  }
  if (!connect) {
    std::cout << "Offline: pass --connect to subscribe for up to 10 seconds; "
                 "no device command was sent.\n";
    return 0;
  }
  std::mutex mutex;
  std::condition_variable received;
  bool got_message = false;
  auto seen = [&] {
    std::lock_guard<std::mutex> lock(mutex);
    got_message = true;
    received.notify_one();
  };
  try {
    aotai_sdk::Client client(prefix);
    rclcpp::SubscriptionBase::SharedPtr subscription;
    if (topic == "robot") {
      subscription = client.subscribe<weld_interfaces::msg::ATRobotStatus>(
          "/at/robot/get_real_time_status", 10,
          [&](weld_interfaces::msg::ATRobotStatus::SharedPtr msg) {
            std::cout << "robot_mode=" << msg->robot_mode << " connect_status="
                      << msg->connect_status << " timestamp=" << msg->timestamp << "\n";
            seen();
          });
    } else if (topic == "welder") {
      subscription = client.subscribe<weld_interfaces::msg::ATWelderRealTimeData>(
          "/at/welder/welder_realtime_data", 10,
          [&](weld_interfaces::msg::ATWelderRealTimeData::SharedPtr msg) {
            std::cout << "enable=" << msg->enable << " voltage="
                      << msg->real_time_voltage << " current=" << msg->real_time_current
                      << " timestamp=" << msg->timestamp << "\n";
            seen();
          });
    } else if (topic == "task") {
      subscription = client.subscribe<std_msgs::msg::String>(
          "/at/task/task_feedback", 10,
          [&](std_msgs::msg::String::SharedPtr msg) {
            std::cout << "feedback=" << msg->data << "\n";
            seen();
          });
    } else if (topic == "camera-status") {
      subscription = client.subscribe<std_msgs::msg::String>(
          "/at/camera_node/status", 10,
          [&](std_msgs::msg::String::SharedPtr msg) {
            std::cout << "camera_status=" << msg->data << "\n";
            seen();
          });
    } else {
      subscription = client.subscribe<weld_interfaces::msg::ATPointCloud>(
          "/at/camera_node/points_raw", 10,
          [&](weld_interfaces::msg::ATPointCloud::SharedPtr msg) {
            std::cout << "timestamp=" << msg->timestamp
                      << " point_count=" << msg->points.size() << "\n";
            seen();
          });
    }
    {
      std::unique_lock<std::mutex> lock(mutex);
      if (!received.wait_for(lock, std::chrono::duration<double>(seconds),
                             [&] { return got_message; }))
        throw std::runtime_error("no message before timeout; check publisher/namespace");
    }
    subscription.reset();  // Explicitly release before Client::close().
    client.close();
    std::cout << "received one read-only message; subscription released\n";
    return 0;
  } catch (const std::exception &error) {
    std::cerr << "subscription failed: " << error.what() << "\n";
    return 3;
  }
}
