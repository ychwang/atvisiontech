#pragma once
#include "aotai_api/json.hpp"
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <stdexcept>
#include <string>
#include <thread>
#include <weld_interfaces/action/at_all_point_cloud.hpp>
#include <weld_interfaces/action/at_weld_task.hpp>
#include <weld_interfaces/srv/at_bool.hpp>
#include <weld_interfaces/srv/at_connect.hpp>
#include <weld_interfaces/srv/at_empty.hpp>
#include <weld_interfaces/srv/at_float.hpp>
#include <weld_interfaces/srv/at_int.hpp>
#include <weld_interfaces/srv/at_query.hpp>
#include <weld_interfaces/srv/at_robot_get_config.hpp>
#include <weld_interfaces/srv/at_robot_get_pos.hpp>
#include <weld_interfaces/srv/at_robot_init.hpp>
#include <weld_interfaces/srv/at_robot_move_jog.hpp>
#include <weld_interfaces/srv/at_string.hpp>
#include <weld_interfaces/srv/at_string_generic.hpp>
#include <weld_interfaces/srv/laser_config.hpp>
#include <weld_interfaces/srv/laser_control.hpp>

namespace aotai::api {
using json = nlohmann::json;
enum class ErrorKind {
  communication,
  timeout,
  rejected,
  execution,
  closed,
  reentrant,
  validation
};
class Error : public std::runtime_error {
public:
  Error(ErrorKind k, const std::string &s) : std::runtime_error(s), kind(k) {}
  ErrorKind kind;
};
struct GenericReply {
  int status{};
  std::string data, message;
  std::int64_t result{};
  bool accepted() const { return status == 200; }
};
struct TaskResult {
  bool ros_accepted{};
  int action_code{};
  std::string status_message;
  std::string project_status;
  bool business_success{};
};

class Client {
public:
  explicit Client(std::string endpoint_prefix = "",
                  std::string node_name = "aotai_api_sdk");
  ~Client();
  Client(const Client &) = delete;
  Client &operator=(const Client &) = delete;
  void close();
  bool closed() const noexcept { return closed_; }
  template <class ServiceT>
  typename ServiceT::Response::SharedPtr
  call_service(const std::string &endpoint,
               typename ServiceT::Request::SharedPtr request,
               std::chrono::milliseconds timeout = std::chrono::seconds(3));
  template <class ServiceT>
  typename ServiceT::Response::SharedPtr
  call(const std::string &endpoint,
       typename ServiceT::Request::SharedPtr request,
       std::chrono::milliseconds timeout = std::chrono::seconds(3)) {
    return call_service<ServiceT>(endpoint, request, timeout);
  }
  template <class MsgT>
  rclcpp::SubscriptionBase::SharedPtr
  subscribe(const std::string &topic, size_t depth,
            std::function<void(typename MsgT::SharedPtr)> callback);
  GenericReply robot_init(const std::string &robot_type,
                          const std::string &robot_subtype,
                          const std::string &robot_ip,
                          const std::string &local_ip, double robot_scope);
  GenericReply robot_connect(bool enable);
  GenericReply robot_power(bool enable);
  GenericReply robot_subscribe();
  GenericReply robot_move_step(const std::string &move_type, double direction,
                               double speed);
  // `data` is sent unchanged.  The default exists only for source
  // compatibility.
  GenericReply robot_status(const std::string &data = "robot_status");
  weld_interfaces::srv::ATRobotGetPos::Response::SharedPtr robot_pose();
  GenericReply welder_config(const std::string &config_id,
                             const std::string &data); // legacy id overload
  GenericReply welder_config(const std::string &data); // id is currently unused
  GenericReply
  welder_connect(const std::string &weld_ip, bool on,
                 std::chrono::milliseconds timeout = std::chrono::seconds(5));
  GenericReply welder_certify(const std::string &data);
  GenericReply welder_robot_ready(bool enable);
  weld_interfaces::srv::ATFloat::Response::SharedPtr
  welder_current(double value);
  weld_interfaces::srv::ATFloat::Response::SharedPtr
  welder_voltage(double value);
  GenericReply welder_synergic_mode(std::int64_t value);
  GenericReply welder_enable(std::int64_t value);
  GenericReply welder_welding(bool enable);
  GenericReply welder_status(const std::string &data);
  GenericReply welder_data();
  weld_interfaces::srv::ATRobotGetConfig::Response::SharedPtr robot_config();
  GenericReply workpiece_group_list(const json &filters = json::array(),
                                    std::uint32_t page_number = 1,
                                    std::uint32_t items_per_page = 0,
                                    const std::string &sort_field = "",
                                    bool sort_descending = false);
  GenericReply workpiece_group_detail(int group_id);
  GenericReply workpiece_group_add(const json &payload);
  GenericReply workpiece_group_update(const json &payload);
  GenericReply workpiece_group_delete(int group_id);
  GenericReply current_task();
  GenericReply robot_stop();
  GenericReply camera_search(bool enable);
  GenericReply camera_config(const std::string &config);
  GenericReply camera_control(const std::string &control);
  // Direct ATStringGeneric process-management mappings. JSON arguments are
  // serialized unchanged except for json::dump(); IDs belong in Request.id
  // only for list/detail/delete endpoints whose handlers read that field.
  GenericReply process_class_list();
  GenericReply process_class_add(const json &payload);
  GenericReply process_class_update(const json &payload);
  GenericReply process_class_delete(int class_id);
  GenericReply process_class_assoc_update(int process_class_id, int process_id);
  GenericReply process_list_by_class(int class_id);
  GenericReply process_add(const json &payload);
  GenericReply process_update(const json &payload);
  GenericReply process_delete(int process_id);
  GenericReply process_detail(int process_id);
  GenericReply task_command(const std::string &service_name,
                            const json &extra = json::object());
  GenericReply task_start();
  GenericReply task_pause();
  GenericReply task_continue();
  GenericReply task_stop();
  static json assemble_task(const json &input);
  static void validate_executable(const json &input,
                                  const json &process_detail);
  using TaskFeedback = std::function<void(const std::string &)>;
  using TaskHandle =
      rclcpp_action::ClientGoalHandle<weld_interfaces::action::ATWeldTask>;
  std::shared_ptr<TaskHandle>
  submit_task(const json &task, TaskFeedback feedback = {},
              std::chrono::milliseconds timeout = std::chrono::seconds(3));
  TaskResult wait_result(const std::shared_ptr<TaskHandle> &handle,
                         std::chrono::milliseconds timeout);
  bool cancel(const std::shared_ptr<TaskHandle>
                  &handle); // ROS cancellation only, NOT task_stop.
  using CloudSink = std::function<void(
      const weld_interfaces::action::ATAllPointCloud::Feedback &)>;
  std::shared_ptr<
      rclcpp_action::ClientGoalHandle<weld_interfaces::action::ATAllPointCloud>>
  download_cloud(const json &, CloudSink,
                 std::chrono::milliseconds timeout = std::chrono::seconds(3));
  void wait_cloud_result(const std::shared_ptr<rclcpp_action::ClientGoalHandle<
                             weld_interfaces::action::ATAllPointCloud>> &,
                         std::chrono::milliseconds timeout);

private:
  // The external owner may call synchronous APIs from one thread only.  close()
  // is deliberately allowed from another thread so it can interrupt that owner.
  std::string endpoint(const std::string &) const;
  void assert_not_callback() const;
  void assert_owner_thread();
  rclcpp::Node::SharedPtr acquire_node();
  void begin_callback();
  void end_callback();
  void record_callback_error(std::exception_ptr error);
  void throw_callback_error() const;
  struct CloudStreamState {
    std::mutex mutex;
    std::condition_variable changed;
    std::exception_ptr feedback_error;
    uint32_t received{0};
    uint32_t total{0};
  };
  rclcpp_action::Client<weld_interfaces::action::ATWeldTask>::SharedPtr
      task_client_;
  rclcpp_action::Client<weld_interfaces::action::ATAllPointCloud>::SharedPtr
      cloud_client_;
  rclcpp::Context::SharedPtr context_;
  rclcpp::Node::SharedPtr node_;
  std::unique_ptr<rclcpp::executors::SingleThreadedExecutor> executor_;
  std::thread executor_thread_;
  std::string prefix_;
  std::atomic_bool closed_{false};
  mutable std::mutex lifecycle_mutex_;
  std::thread::id owner_thread_{};
  std::shared_ptr<CloudStreamState> cloud_stream_;
  std::thread::id callback_thread_{};
  mutable std::mutex callback_mutex_;
  mutable std::mutex callback_error_mutex_;
  std::exception_ptr callback_error_;
  std::atomic_bool callback_failed_{false};
};

template <class ServiceT>
typename ServiceT::Response::SharedPtr
Client::call_service(const std::string &name,
                     typename ServiceT::Request::SharedPtr request,
                     std::chrono::milliseconds timeout) {
  assert_not_callback();
  assert_owner_thread();
  auto node = acquire_node();
  auto client = node->create_client<ServiceT>(endpoint(name));
  if (!client->wait_for_service(timeout))
    throw Error(ErrorKind::communication,
                "service unavailable: " + endpoint(name));
  auto future = client->async_send_request(request);
  auto deadline = std::chrono::steady_clock::now() + timeout;
  while (future.wait_for(std::chrono::milliseconds(10)) !=
         std::future_status::ready) {
    if (closed_) {
      client->remove_pending_request(future);
      throw Error(ErrorKind::closed,
                  "client closed while waiting; server outcome unknown");
    }
    if (callback_failed_)
      throw Error(ErrorKind::execution, "an SDK callback threw while waiting");
    if (std::chrono::steady_clock::now() >= deadline) {
      client->remove_pending_request(future);
      throw Error(ErrorKind::timeout, "service timeout: " + endpoint(name));
    }
  }
  throw_callback_error();
  return future.get();
}
template <class MsgT>
rclcpp::SubscriptionBase::SharedPtr
Client::subscribe(const std::string &topic, size_t depth,
                  std::function<void(typename MsgT::SharedPtr)> cb) {
  assert_not_callback();
  assert_owner_thread();
  auto node = acquire_node();
  return node->create_subscription<MsgT>(
      endpoint(topic), depth,
      [this, cb = std::move(cb)](typename MsgT::SharedPtr m) {
        begin_callback();
        try {
          cb(m);
        } catch (...) {
          record_callback_error(std::current_exception());
        }
        end_callback();
      });
}
} // namespace aotai::api
namespace aotai_sdk {
using Client = aotai::api::Client;
using Error = aotai::api::Error;
using ErrorKind = aotai::api::ErrorKind;
using GenericReply = aotai::api::GenericReply;
using TaskResult = aotai::api::TaskResult;
using json = aotai::api::json;
} // namespace aotai_sdk
