#include "aotai_api/client.hpp"
#include <cmath>
#include <type_traits>
#include <utility>
using namespace std::chrono_literals;
namespace aotai::api {
namespace {
template <class ActionClient>
bool wait_for_server(const std::shared_ptr<ActionClient> &client,
                     const std::atomic_bool &closed,
                     std::chrono::milliseconds timeout) {
  // Poll readiness against this Client's lifetime instead of depending on a
  // process-global ROS context inside an installed discovery wait helper.
  const auto deadline = std::chrono::steady_clock::now() + timeout;
  while (!closed) {
    if (client->action_server_is_ready())
      return true;
    if (std::chrono::steady_clock::now() >= deadline)
      return false;
    std::this_thread::sleep_for(10ms);
  }
  return false;
}
template <class Future>
void wait_for_future(Future &future, const std::atomic_bool &closed,
                     const std::atomic_bool &callback_failed,
                     std::chrono::milliseconds timeout,
                     const std::string &timeout_message) {
  const auto deadline = std::chrono::steady_clock::now() + timeout;
  while (future.wait_for(10ms) != std::future_status::ready) {
    if (closed)
      throw Error(ErrorKind::closed,
                  "client closed while waiting; server outcome unknown");
    if (callback_failed)
      throw Error(ErrorKind::execution, "an SDK callback threw while waiting");
    if (std::chrono::steady_clock::now() >= deadline)
      throw Error(ErrorKind::timeout, timeout_message);
  }
}
} // namespace
Client::Client(std::string prefix, std::string node_name)
    : prefix_(std::move(prefix)) {
  context_ = std::make_shared<rclcpp::Context>();
  context_->init(0, nullptr);
  node_ = std::make_shared<rclcpp::Node>(
      node_name, rclcpp::NodeOptions().context(context_));
  rclcpp::ExecutorOptions options;
  options.context = context_;
  executor_ =
      std::make_unique<rclcpp::executors::SingleThreadedExecutor>(options);
  executor_->add_node(node_);
  executor_thread_ = std::thread([this] {
    try {
      executor_->spin();
    } catch (...) {
      if (!closed_)
        record_callback_error(std::current_exception());
    }
  });
}
Client::~Client() {
  // Destroying this owner from its own callback violates the lifetime contract.
  // Do not hide that misuse behind a swallowed exception or detached raw-this
  // thread.
  if (executor_thread_.joinable() &&
      executor_thread_.get_id() == std::this_thread::get_id())
    std::terminate();
  close();
}
void Client::close() {
  try {
    assert_not_callback();
  } catch (const Error &error) {
    // A recorded user callback exception blocks further synchronous work, but
    // must never prevent the explicit/destructor cleanup path.
    if (error.kind != ErrorKind::execution)
      throw;
  }
  bool expected = false;
  if (!closed_.compare_exchange_strong(expected, true))
    return;
  if (executor_) {
    executor_->cancel();
  }
  if (executor_thread_.joinable())
    executor_thread_.join();
  std::lock_guard<std::mutex> lock(lifecycle_mutex_);
  if (executor_ && node_)
    executor_->remove_node(node_);
  task_client_.reset();
  cloud_client_.reset();
  cloud_stream_.reset();
  node_.reset();
  executor_.reset();
  if (context_)
    context_->shutdown("client closed");
}
std::string Client::endpoint(const std::string &n) const {
  if (prefix_.empty())
    return n;
  if (n.empty() || n[0] != '/')
    return prefix_ + "/" + n;
  return prefix_ + n;
}
void Client::assert_not_callback() const {
  std::lock_guard<std::mutex> l(callback_mutex_);
  if (callback_thread_ == std::this_thread::get_id())
    throw Error(ErrorKind::reentrant,
                "synchronous SDK calls or close in callback are forbidden");
  throw_callback_error();
}
void Client::assert_owner_thread() {
  std::lock_guard<std::mutex> lock(lifecycle_mutex_);
  if (owner_thread_ == std::thread::id{}) {
    owner_thread_ = std::this_thread::get_id();
  } else if (owner_thread_ != std::this_thread::get_id()) {
    throw Error(ErrorKind::validation,
                "synchronous Client APIs must use the owning thread");
  }
}
rclcpp::Node::SharedPtr Client::acquire_node() {
  std::lock_guard<std::mutex> lock(lifecycle_mutex_);
  if (closed_ || !node_)
    throw Error(ErrorKind::closed, "client is closed");
  return node_;
}
void Client::begin_callback() {
  std::lock_guard<std::mutex> lock(callback_mutex_);
  callback_thread_ = std::this_thread::get_id();
}
void Client::end_callback() {
  std::lock_guard<std::mutex> lock(callback_mutex_);
  callback_thread_ = {};
}
void Client::record_callback_error(std::exception_ptr error) {
  std::lock_guard<std::mutex> lock(callback_error_mutex_);
  if (!callback_error_)
    callback_error_ = error;
  callback_failed_ = true;
}
void Client::throw_callback_error() const {
  std::lock_guard<std::mutex> lock(callback_error_mutex_);
  if (callback_error_)
    throw Error(ErrorKind::execution,
                "an SDK callback threw; no further synchronous calls allowed");
}
template <class T, class = void> struct has_result : std::false_type {};
template <class T>
struct has_result<T, std::void_t<decltype(std::declval<T>().result)>>
    : std::true_type {};
template <class ResponseT>
static GenericReply generic(const std::shared_ptr<ResponseT> &r) {
  std::int64_t result = 0;
  if constexpr (has_result<ResponseT>::value)
    result = r->result;
  return {r->status, r->data, r->message, result};
}
GenericReply process_generic(Client &, const std::string &, const std::string &,
                             const std::string &);
static GenericReply inner_reply(const std::string &message) {
  try {
    auto j = json::parse(message);
    std::string data;
    if (const auto it = j.find("data"); it != j.end())
      data = it->is_string() ? it->get<std::string>() : it->dump();
    if (!j.is_object() || !j.contains("status") ||
        !j["status"].is_number_integer())
      throw std::runtime_error("missing integer status");
    return {j.at("status").get<int>(), std::move(data), message, 0};
  } catch (...) {
    throw Error(ErrorKind::execution,
                "camera response lacks valid JSON status: " + message);
  }
}
GenericReply Client::robot_init(const std::string &robot_type,
                                const std::string &robot_subtype,
                                const std::string &robot_ip,
                                const std::string &local_ip,
                                double robot_scope) {
  auto q = std::make_shared<weld_interfaces::srv::ATRobotInit::Request>();
  q->robot_type = robot_type;
  q->robot_subtype = robot_subtype;
  q->robot_ip = robot_ip;
  q->local_ip = local_ip;
  q->robot_scope = robot_scope;
  return generic(call_service<weld_interfaces::srv::ATRobotInit>(
      "/at/robot/init_robot", q));
}
GenericReply Client::robot_connect(bool e) {
  auto q = std::make_shared<weld_interfaces::srv::ATBool::Request>();
  q->enable = e;
  auto r = call_service<weld_interfaces::srv::ATBool>("/at/robot/connect", q);
  return {r->status, r->data, r->message, r->result};
}
GenericReply Client::robot_power(bool e) {
  auto q = std::make_shared<weld_interfaces::srv::ATBool::Request>();
  q->enable = e;
  return generic(
      call_service<weld_interfaces::srv::ATBool>("/at/robot/power", q));
}
GenericReply Client::robot_subscribe() {
  auto q = std::make_shared<weld_interfaces::srv::ATEmpty::Request>();
  return generic(
      call_service<weld_interfaces::srv::ATEmpty>("/at/robot/subscribe", q));
}
GenericReply Client::robot_move_step(const std::string &move_type,
                                     double direction, double speed) {
  auto q = std::make_shared<weld_interfaces::srv::ATRobotMoveJog::Request>();
  q->move_type = move_type;
  q->direction = direction;
  q->speed = speed;
  return generic(call_service<weld_interfaces::srv::ATRobotMoveJog>(
      "/at/robot/move_step", q));
}
GenericReply Client::robot_status(const std::string &d) {
  auto q = std::make_shared<weld_interfaces::srv::ATStringGeneric::Request>();
  q->data = d;
  return generic(call_service<weld_interfaces::srv::ATStringGeneric>(
      "/at/robot/status", q));
}
weld_interfaces::srv::ATRobotGetPos::Response::SharedPtr Client::robot_pose() {
  auto request =
      std::make_shared<weld_interfaces::srv::ATRobotGetPos::Request>();
  auto reply = call_service<weld_interfaces::srv::ATRobotGetPos>(
      "/at/robot/get_pos", request);
  const auto raw = json{{"status", reply->status},
                        {"message", reply->message},
                        {"cur_pos", reply->cur_pos},
                        {"joint_pos", reply->joint_pos},
                        {"flan_pos", reply->flan_pos}}
                       .dump();
  if (reply->status != 0 && reply->status != 200)
    throw Error(ErrorKind::execution,
                "robot pose server returned failure; raw=" + raw);
  for (const auto *values :
       {&reply->cur_pos, &reply->joint_pos, &reply->flan_pos}) {
    if (values->size() != 6)
      throw Error(ErrorKind::execution,
                  "robot pose requires three six-value arrays; raw=" + raw);
    for (const auto value : *values)
      if (!std::isfinite(value))
        throw Error(ErrorKind::execution,
                    "robot pose contains nonfinite values; raw=" + raw);
  }
  return reply;
}

GenericReply Client::welder_config(const std::string &id,
                                   const std::string &data) {
  auto q = std::make_shared<weld_interfaces::srv::ATStringGeneric::Request>();
  q->id = id;
  q->data = data;
  return generic(call_service<weld_interfaces::srv::ATStringGeneric>(
      "/at/welder/set_welder_config", q));
}
GenericReply Client::welder_config(const std::string &data) {
  return welder_config("", data);
}
GenericReply Client::welder_connect(const std::string &ip, bool on,
                                    std::chrono::milliseconds timeout) {
  auto q = std::make_shared<weld_interfaces::srv::ATConnect::Request>();
  q->weld_ip = ip;
  q->on = on;
  auto r = call_service<weld_interfaces::srv::ATConnect>("/at/welder/connect",
                                                         q, timeout);
  return {r->status, "", r->message, r->result};
}
GenericReply Client::welder_certify(const std::string &data) {
  auto q = std::make_shared<weld_interfaces::srv::ATString::Request>();
  q->data = data;
  auto r =
      call_service<weld_interfaces::srv::ATString>("/at/welder/certify", q);
  return {r->status, "", r->message, r->result};
}
GenericReply Client::welder_robot_ready(bool e) {
  auto q = std::make_shared<weld_interfaces::srv::ATBool::Request>();
  q->enable = e;
  return generic(call_service<weld_interfaces::srv::ATBool>(
      "/at/welder/set_robot_ready", q));
}
weld_interfaces::srv::ATFloat::Response::SharedPtr
Client::welder_current(double value) {
  auto request = std::make_shared<weld_interfaces::srv::ATFloat::Request>();
  request->value = value;
  return call_service<weld_interfaces::srv::ATFloat>("/at/welder/set_current",
                                                     request);
}
weld_interfaces::srv::ATFloat::Response::SharedPtr
Client::welder_voltage(double value) {
  auto request = std::make_shared<weld_interfaces::srv::ATFloat::Request>();
  request->value = value;
  return call_service<weld_interfaces::srv::ATFloat>("/at/welder/set_voltage",
                                                     request);
}
GenericReply Client::welder_synergic_mode(std::int64_t v) {
  auto q = std::make_shared<weld_interfaces::srv::ATInt::Request>();
  q->value = v;
  auto r = call_service<weld_interfaces::srv::ATInt>(
      "/at/welder/set_synergic_mode", q);
  return {r->status, "", r->message, r->result};
}
GenericReply Client::welder_enable(std::int64_t v) {
  auto q = std::make_shared<weld_interfaces::srv::ATInt::Request>();
  q->value = v;
  auto r =
      call_service<weld_interfaces::srv::ATInt>("/at/welder/set_enable", q);
  return {r->status, "", r->message, r->result};
}
GenericReply Client::welder_welding(bool e) {
  auto q = std::make_shared<weld_interfaces::srv::ATBool::Request>();
  q->enable = e;
  return generic(
      call_service<weld_interfaces::srv::ATBool>("/at/welder/welding", q));
}
GenericReply Client::welder_status(const std::string &data) {
  auto q = std::make_shared<weld_interfaces::srv::ATString::Request>();
  q->data = data;
  auto r = call_service<weld_interfaces::srv::ATString>(
      "/at/welder/get_welder_status", q);
  return {r->status, "", r->message, r->result};
}
GenericReply Client::welder_data() {
  auto q = std::make_shared<weld_interfaces::srv::ATStringGeneric::Request>();
  q->id = "";
  q->data = "";
  return generic(call_service<weld_interfaces::srv::ATStringGeneric>(
      "/at/welder/get_welder_data", q));
}
weld_interfaces::srv::ATRobotGetConfig::Response::SharedPtr
Client::robot_config() {
  auto request =
      std::make_shared<weld_interfaces::srv::ATRobotGetConfig::Request>();
  return call_service<weld_interfaces::srv::ATRobotGetConfig>(
      "/at/robot/get_config", request);
}
GenericReply Client::workpiece_group_list(const json &filters,
                                          std::uint32_t page_number,
                                          std::uint32_t items_per_page,
                                          const std::string &sort_field,
                                          bool sort_descending) {
  if (!filters.is_array())
    throw Error(ErrorKind::validation, "filters must be a JSON array");
  auto request = std::make_shared<weld_interfaces::srv::ATQuery::Request>();
  for (const auto &filter : filters) {
    if (!filter.is_object() || !filter.contains("key") ||
        !filter.contains("value") || !filter["key"].is_string() ||
        !filter["value"].is_string())
      throw Error(ErrorKind::validation,
                  "each filter needs string key and value");
    diagnostic_msgs::msg::KeyValue item;
    item.key = filter["key"].get<std::string>();
    item.value = filter["value"].get<std::string>();
    request->filters.push_back(std::move(item));
  }
  request->page_number = page_number;
  request->items_per_page = items_per_page;
  request->sort_field = sort_field;
  request->sort_descending = sort_descending;
  return generic(call_service<weld_interfaces::srv::ATQuery>(
      "/at/data/workpiece_group_list", request));
}
GenericReply Client::workpiece_group_detail(int group_id) {
  auto request = std::make_shared<weld_interfaces::srv::ATQuery::Request>();
  diagnostic_msgs::msg::KeyValue filter;
  filter.key = "id";
  filter.value = std::to_string(group_id);
  request->filters.push_back(std::move(filter));
  request->page_number = 0;
  request->items_per_page = 0;
  return generic(call_service<weld_interfaces::srv::ATQuery>(
      "/at/data/workpiece_group_detail", request));
}
GenericReply Client::workpiece_group_add(const json &payload) {
  return process_generic(*this, "/at/data/workpiece_group_add", "",
                         payload.dump());
}
GenericReply Client::workpiece_group_update(const json &payload) {
  return process_generic(*this, "/at/data/workpiece_group_update", "",
                         payload.dump());
}
GenericReply Client::workpiece_group_delete(int group_id) {
  return process_generic(*this, "/at/data/workpiece_group_pseudo_delete",
                         std::to_string(group_id), "");
}
GenericReply Client::current_task() { return task_command("get_current_task"); }

GenericReply Client::robot_stop() {
  auto q = std::make_shared<weld_interfaces::srv::ATEmpty::Request>();
  auto r =
      call_service<weld_interfaces::srv::ATEmpty>("/at/robot/move_stop", q);
  return {r->status, r->data, r->message, 0};
}
GenericReply Client::camera_search(bool e) {
  auto q = std::make_shared<weld_interfaces::srv::ATBool::Request>();
  q->enable = e;
  auto r =
      call_service<weld_interfaces::srv::ATBool>("/at/camera_node/search", q);
  return {r->status, r->data, r->message, r->result};
}
GenericReply Client::camera_config(const std::string &s) {
  auto q = std::make_shared<weld_interfaces::srv::LaserConfig::Request>();
  q->config_str = s;
  auto r = call_service<weld_interfaces::srv::LaserConfig>(
      "/at/camera_node/config", q);
  return inner_reply(r->message);
}
GenericReply Client::camera_control(const std::string &s) {
  auto q = std::make_shared<weld_interfaces::srv::LaserControl::Request>();
  q->control_str = s;
  auto r = call_service<weld_interfaces::srv::LaserControl>(
      "/at/camera_node/control", q);
  return inner_reply(r->message);
}
GenericReply process_generic(Client &client, const std::string &endpoint,
                             const std::string &id, const std::string &data) {
  auto request =
      std::make_shared<weld_interfaces::srv::ATStringGeneric::Request>();
  request->id = id;
  request->data = data;
  return generic(client.call_service<weld_interfaces::srv::ATStringGeneric>(
      endpoint, request));
}
GenericReply Client::process_class_list() {
  return process_generic(*this, "/at/data/process_class_list", "", "");
}
GenericReply Client::process_class_add(const json &payload) {
  return process_generic(*this, "/at/data/process_class_add", "",
                         payload.dump());
}
GenericReply Client::process_class_update(const json &payload) {
  return process_generic(*this, "/at/data/process_class_update", "",
                         payload.dump());
}
GenericReply Client::process_class_delete(int id) {
  return process_generic(*this, "/at/data/process_class_pseudo_delete",
                         std::to_string(id), "");
}
GenericReply Client::process_class_assoc_update(int class_id, int process_id) {
  return process_generic(
      *this, "/at/data/process_class_assoc_update", "",
      json{{"process_class_id", class_id}, {"process_id", process_id}}.dump());
}
GenericReply Client::process_list_by_class(int id) {
  return process_generic(*this, "/at/data/process_list_by_class",
                         std::to_string(id), "");
}
GenericReply Client::process_add(const json &payload) {
  return process_generic(*this, "/at/data/process_add", "", payload.dump());
}
GenericReply Client::process_update(const json &payload) {
  return process_generic(*this, "/at/data/process_info_update", "",
                         payload.dump());
}
GenericReply Client::process_delete(int id) {
  return process_generic(*this, "/at/data/process_pseudo_delete",
                         std::to_string(id), "");
}

GenericReply Client::process_detail(int id) {
  auto q = std::make_shared<weld_interfaces::srv::ATStringGeneric::Request>();
  q->id = std::to_string(id);
  return generic(call_service<weld_interfaces::srv::ATStringGeneric>(
      "/at/data/process_detail", q));
}
GenericReply Client::task_command(const std::string &s, const json &e) {
  auto q = std::make_shared<weld_interfaces::srv::ATStringGeneric::Request>();
  auto x = e;
  x["service_name"] = s;
  q->data = x.dump();
  return generic(call_service<weld_interfaces::srv::ATStringGeneric>(
      "/at/task/task_services", q));
}
GenericReply Client::task_start() { return task_command("task_start"); }
GenericReply Client::task_pause() { return task_command("task_pause"); }
GenericReply Client::task_continue() { return task_command("task_continue"); }
GenericReply Client::task_stop() { return task_command("task_destroy"); }
std::shared_ptr<Client::TaskHandle>
Client::submit_task(const json &t, TaskFeedback fb,
                    std::chrono::milliseconds timeout) {
  assert_not_callback();
  assert_owner_thread();
  using A = weld_interfaces::action::ATWeldTask;
  auto node = acquire_node();
  rclcpp_action::Client<A>::SharedPtr c;
  {
    std::lock_guard<std::mutex> lock(lifecycle_mutex_);
    if (task_client_)
      throw Error(ErrorKind::validation,
                  "only one live task Action handle per Client is supported");
    task_client_ =
        rclcpp_action::create_client<A>(node, endpoint("/at/task/task_action"));
    c = task_client_;
  }
  if (!wait_for_server(c, closed_, timeout)) {
    std::lock_guard<std::mutex> lock(lifecycle_mutex_);
    if (task_client_ == c)
      task_client_.reset();
    throw Error(ErrorKind::communication, "task action unavailable");
  }
  A::Goal g;
  g.json_data = t.dump();
  rclcpp_action::Client<A>::SendGoalOptions o;
  o.feedback_callback = [this, fb](auto, auto f) {
    begin_callback();
    try {
      if (fb)
        fb(f->status_message);
    } catch (...) {
      record_callback_error(std::current_exception());
    }
    end_callback();
  };
  auto f = c->async_send_goal(g, o);
  try {
    wait_for_future(f, closed_, callback_failed_, timeout,
                    "task goal timeout; server outcome unknown");
    throw_callback_error();
  } catch (...) {
    std::lock_guard<std::mutex> lock(lifecycle_mutex_);
    if (task_client_ == c)
      task_client_.reset();
    throw;
  }
  auto h = f.get();
  if (!h) {
    std::lock_guard<std::mutex> lock(lifecycle_mutex_);
    if (task_client_ == c)
      task_client_.reset();
    throw Error(ErrorKind::rejected, "task goal rejected");
  }
  return h;
}
TaskResult Client::wait_result(const std::shared_ptr<TaskHandle> &h,
                               std::chrono::milliseconds t) {
  assert_not_callback();
  assert_owner_thread();
  if (!h)
    throw Error(ErrorKind::validation, "null task handle");
  rclcpp_action::Client<weld_interfaces::action::ATWeldTask>::SharedPtr client;
  {
    std::lock_guard<std::mutex> lock(lifecycle_mutex_);
    if (closed_ || !task_client_)
      throw Error(ErrorKind::closed, "task action client no longer available");
    client = task_client_;
  }
  auto r = client->async_get_result(h);
  wait_for_future(r, closed_, callback_failed_, t,
                  "task result timeout; server task may continue");
  throw_callback_error();
  auto x = r.get();
  {
    std::lock_guard<std::mutex> lock(lifecycle_mutex_);
    if (task_client_ == client)
      task_client_.reset();
  }
  TaskResult o{true, static_cast<int>(x.code),
               x.result ? x.result->status_message : "", "", false};
  try {
    auto j = json::parse(o.status_message);
    o.project_status = j.value("project_status", "");
    o.business_success = (x.code == rclcpp_action::ResultCode::SUCCEEDED &&
                          (o.project_status == "101006"));
  } catch (...) {
  }
  return o;
}
bool Client::cancel(const std::shared_ptr<TaskHandle> &h) {
  assert_not_callback();
  assert_owner_thread();
  if (!h)
    return false;
  rclcpp_action::Client<weld_interfaces::action::ATWeldTask>::SharedPtr client;
  {
    std::lock_guard<std::mutex> lock(lifecycle_mutex_);
    if (closed_ || !task_client_)
      return false;
    client = task_client_;
  }
  auto result = client->async_cancel_goal(h);
  wait_for_future(result, closed_, callback_failed_, 3s,
                  "task cancellation timeout");
  throw_callback_error();
  const auto response = result.get();
  return response && !response->goals_canceling.empty();
}
std::shared_ptr<
    rclcpp_action::ClientGoalHandle<weld_interfaces::action::ATAllPointCloud>>
Client::download_cloud(const json &j, CloudSink sink,
                       std::chrono::milliseconds timeout) {
  assert_not_callback();
  assert_owner_thread();
  using A = weld_interfaces::action::ATAllPointCloud;
  auto node = acquire_node();
  rclcpp_action::Client<A>::SharedPtr client;
  auto stream = std::make_shared<CloudStreamState>();
  {
    std::lock_guard<std::mutex> lock(lifecycle_mutex_);
    if (cloud_client_)
      throw Error(ErrorKind::validation,
                  "only one live cloud Action handle per Client is supported");
    cloud_client_ = rclcpp_action::create_client<A>(
        node, endpoint("/at/camera_node/get_all_point_cloud"));
    cloud_stream_ = stream;
    client = cloud_client_;
  }
  if (!wait_for_server(client, closed_, timeout)) {
    std::lock_guard<std::mutex> lock(lifecycle_mutex_);
    if (cloud_client_ == client) {
      cloud_client_.reset();
      cloud_stream_.reset();
    }
    throw Error(ErrorKind::communication, "cloud action unavailable");
  }
  A::Goal g;
  g.json_data = j.dump();
  rclcpp_action::Client<A>::SendGoalOptions o;
  o.feedback_callback = [this, sink, stream](auto, auto f) {
    begin_callback();
    try {
      std::lock_guard<std::mutex> lock(stream->mutex);
      if (stream->total == 0)
        stream->total = f->total_blocks;
      if (f->total_blocks == 0 || f->total_blocks != stream->total ||
          f->sequence_id != stream->received)
        throw Error(ErrorKind::execution,
                    "invalid cloud feedback sequence: expected " +
                        std::to_string(stream->received) + " of " +
                        std::to_string(stream->total) + ", got " +
                        std::to_string(f->sequence_id) + " of " +
                        std::to_string(f->total_blocks));
      ++stream->received;
      if (sink)
        sink(*f);
    } catch (...) {
      std::lock_guard<std::mutex> lock(stream->mutex);
      if (!stream->feedback_error)
        stream->feedback_error = std::current_exception();
    }
    stream->changed.notify_all();
    end_callback();
  };
  auto future = client->async_send_goal(g, o);
  try {
    wait_for_future(future, closed_, callback_failed_, timeout,
                    "cloud goal timeout; server outcome unknown");
    throw_callback_error();
  } catch (...) {
    std::lock_guard<std::mutex> lock(lifecycle_mutex_);
    if (cloud_client_ == client) {
      cloud_client_.reset();
      cloud_stream_.reset();
    }
    throw;
  }
  auto h = future.get();
  if (!h) {
    std::lock_guard<std::mutex> lock(lifecycle_mutex_);
    if (cloud_client_ == client) {
      cloud_client_.reset();
      cloud_stream_.reset();
    }
    throw Error(ErrorKind::rejected, "cloud goal rejected");
  }
  return h;
}
void Client::wait_cloud_result(
    const std::shared_ptr<rclcpp_action::ClientGoalHandle<
        weld_interfaces::action::ATAllPointCloud>> &h,
    std::chrono::milliseconds timeout) {
  assert_not_callback();
  assert_owner_thread();
  rclcpp_action::Client<weld_interfaces::action::ATAllPointCloud>::SharedPtr
      client;
  std::shared_ptr<CloudStreamState> stream;
  {
    std::lock_guard<std::mutex> lock(lifecycle_mutex_);
    client = cloud_client_;
    stream = cloud_stream_;
  }
  if (!client || !stream || !h)
    throw Error(ErrorKind::validation, "no cloud goal handle");
  const auto result_deadline = std::chrono::steady_clock::now() + timeout;
  auto future = client->async_get_result(h);
  wait_for_future(future, closed_, callback_failed_, timeout,
                  "cloud result timeout; server may continue");
  throw_callback_error();
  auto result = future.get();
  const auto release_completed_goal = [&] {
    std::lock_guard<std::mutex> lifecycle_lock(lifecycle_mutex_);
    if (cloud_client_ == client) {
      cloud_client_.reset();
      cloud_stream_.reset();
    }
  };
  if (result.code != rclcpp_action::ResultCode::SUCCEEDED || !result.result ||
      result.result->status != 200) {
    const auto message =
        result.result ? result.result->message : "cloud action failed";
    release_completed_goal();
    throw Error(ErrorKind::execution, message);
  }
  // DDS may deliver the result before feedback already sent by the server.
  // Wait only briefly and never past the caller's result deadline for queued
  // feedback; a short stream remains an execution failure.
  const auto feedback_deadline = result_deadline;
  std::unique_lock<std::mutex> lock(stream->mutex);
  while (!stream->feedback_error &&
         (stream->total == 0 || stream->received < stream->total) && !closed_) {
    if (std::chrono::steady_clock::now() >= feedback_deadline)
      break;
    stream->changed.wait_for(lock, 10ms);
  }
  if (closed_)
    throw Error(ErrorKind::closed,
                "client closed while waiting; server outcome unknown");
  if (stream->feedback_error) {
    auto error = stream->feedback_error;
    lock.unlock();
    release_completed_goal();
    std::rethrow_exception(error);
  }
  if (stream->total == 0 || stream->received != stream->total) {
    lock.unlock();
    release_completed_goal();
    throw Error(ErrorKind::execution, "incomplete cloud feedback stream");
  }
  lock.unlock();
  release_completed_goal();
}
} // namespace aotai::api
