#include <chrono>
#include <iostream>
#include <memory>
#include <string>

#include <rclcpp/rclcpp.hpp>
#include <weld_interfaces/srv/at_string_generic.hpp>

namespace {
std::string endpoint(std::string prefix, const std::string &path) {
  if (prefix.empty())
    return path;
  if (prefix.front() != '/')
    prefix.insert(prefix.begin(), '/');
  while (!prefix.empty() && prefix.back() == '/')
    prefix.pop_back();
  return prefix + path;
}
} // namespace

int main(int argc, char **argv) {
  rclcpp::init(argc, argv);
  int exit_code = 3;
  try {
    auto node = std::make_shared<rclcpp::Node>("aotai_raw_robot_status_demo");
    const auto prefix = node->declare_parameter<std::string>("endpoint_prefix", "");
    const auto request_data =
        node->declare_parameter<std::string>("request_data", "robot_status");
    const auto discovery_timeout_ms =
        node->declare_parameter<int>("service_timeout_ms", 3000);
    const auto response_timeout_ms = node->declare_parameter<int>(
        "response_timeout_ms", discovery_timeout_ms);
    if (discovery_timeout_ms <= 0 || response_timeout_ms <= 0) {
      std::cerr << "service_timeout_ms and response_timeout_ms must be positive\n";
      rclcpp::shutdown();
      return 64;
    }

    const auto service_name = endpoint(prefix, "/at/robot/status");
    auto client = node->create_client<weld_interfaces::srv::ATStringGeneric>(service_name);
    const auto discovery_timeout = std::chrono::milliseconds(discovery_timeout_ms);
    const auto response_timeout = std::chrono::milliseconds(response_timeout_ms);
    if (!client->wait_for_service(discovery_timeout)) {
      std::cerr << "service unavailable after " << discovery_timeout_ms << " ms: "
                << service_name << "\n";
      rclcpp::shutdown();
      return 3;
    }

    // ATStringGeneric has exactly id and data. id is not used by the actual
    // robot-status handler; data must be the literal "robot_status".
    auto request = std::make_shared<weld_interfaces::srv::ATStringGeneric::Request>();
    request->id = "";
    request->data = request_data;
    auto future = client->async_send_request(request);
    rclcpp::executors::SingleThreadedExecutor executor;
    executor.add_node(node);
    const auto result = executor.spin_until_future_complete(future, response_timeout);
    executor.remove_node(node);
    if (result != rclcpp::FutureReturnCode::SUCCESS) {
      client->remove_pending_request(future);
      std::cerr << "response timeout after " << response_timeout_ms
                << " ms; server outcome is unknown\n";
      rclcpp::shutdown();
      return 3;
    }
    const auto response = future.get();
    std::cout << "status=" << response->status << " data=" << response->data
              << " message=" << response->message << "\n";
    exit_code = response->status == 200 ? 0 : 2;
  } catch (const std::exception &error) {
    std::cerr << "ROS query failed: " << error.what() << "\n";
  }
  rclcpp::shutdown();
  return exit_code;
}
