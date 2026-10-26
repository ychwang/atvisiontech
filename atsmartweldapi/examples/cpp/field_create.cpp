#include <aotai_sdk/client.hpp>
#include <weld_interfaces/srv/at_string_generic.hpp>

#include <algorithm>
#include <cctype>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iostream>
#include <limits>
#include <regex>
#include <stdexcept>
#include <string>
#include <utility>

using Json = aotai_sdk::json;

namespace {
const char *kDefaultInput = "examples/data/field-create-templates.json";
const std::regex kRunId("[A-Za-z0-9][A-Za-z0-9_-]{0,47}");

Json load_json(const std::string &path) {
  std::ifstream input(path);
  if (!input)
    throw std::runtime_error("cannot open template: " + path);
  Json data;
  input >> data;
  if (!data.is_object())
    throw std::invalid_argument("template root must be an object");
  return data;
}

void validate_template(const Json &root) {
  for (const auto *key : {"reference_environment", "group", "ordinary_process",
                          "multipass_process", "project"})
    if (!root.contains(key) || !root.at(key).is_object())
      throw std::invalid_argument(std::string("template.") + key +
                                  " must be an object");
  const auto &payload = root.at("project");
  if (!payload.contains("project") || !payload.at("project").is_object())
    throw std::invalid_argument("template.project.project must be an object");
  const auto &project = payload.at("project");
  for (const auto *key : {"direct_run", "loop_execution", "need_reservation",
                          "need_digital_start"})
    if (!project.contains(key) || !project.at(key).is_number_integer() ||
        project.at(key).get<int>() != 0)
      throw std::invalid_argument(std::string("project.") + key +
                                  " must be integer 0");
  if (!payload.contains("workpieces") || !payload.at("workpieces").is_array() ||
      payload.at("workpieces").size() != 2)
    throw std::invalid_argument(
        "template.project.workpieces must contain ordinary and multipass entries");
  for (const auto &workpiece : payload.at("workpieces"))
    if (!workpiece.is_object() || !workpiece.contains("nodes") ||
        !workpiece.at("nodes").is_array() || workpiece.at("nodes").empty())
      throw std::invalid_argument("every workpiece must contain nodes");
}

Json prepare(Json root, const std::string &run_id, int group_id = 0,
             int ordinary_id = 0, int multipass_id = 0) {
  if (!std::regex_match(run_id, kRunId))
    throw std::invalid_argument(
        "--run-id must be 1..48 ASCII safe characters and start alphanumeric");
  validate_template(root);
  const std::string stem = "APIDOC_VERIFY_" + run_id;
  root["group"]["name"] = stem + "_group";
  root["ordinary_process"]["name"] = stem + "_ordinary";
  root["multipass_process"]["name"] = stem + "_multipass";
  auto &payload = root["project"];
  payload["name"] = stem + "_project";
  payload["project"]["name"] = stem + "_project";
  payload["project"]["uid"] = stem + "_project";
  // Future NEW projects: exact supported single-line multi-pass global object.
  // Do not rewrite the actual saved reference dataset or claim it was planned.
  const auto &global_source = root.at("ordinary_process").at("global_process");
  Json future_global = Json::object();
  for (const auto *key : {"enable_offset_correction", "target_accuracy_threshold", "smoothing_parameters", "planning_parameters", "enable_free_pose", "enable_input_safe_point"})
    future_global[key] = global_source.at(key);
  for (const auto *key : {"enable_offset_correction", "enable_free_pose", "enable_input_safe_point"})
    if (!future_global.at(key).is_number_integer())
      throw std::invalid_argument("global process flags must be integers");
  const auto &threshold = future_global.at("target_accuracy_threshold");
  if (!threshold.is_number() || !std::isfinite(threshold.get<double>()) || threshold.get<double>() <= 0)
    throw std::invalid_argument("global accuracy threshold must be finite and positive");
  for (const auto *key : {"smoothing_parameters", "planning_parameters"})
    if (!future_global.at(key).is_string())
      throw std::invalid_argument("global planning parameters must be strings");
  future_global["coplanarity_check_mode"] = 1;
  payload["workpieces"][1]["global_process"] = future_global;
  const int process_ids[2] = {ordinary_id, multipass_id};
  std::size_t seam = 0;
  for (std::size_t index = 0; index < payload["workpieces"].size(); ++index) {
    auto &workpiece = payload["workpieces"][index];
    const std::string suffix = "_workpiece" + std::to_string(index + 1);
    workpiece["name"] = stem + suffix;
    workpiece["uid"] = stem + suffix;
    if (process_ids[index] > 0) {
      workpiece["process_class_id"] = group_id;
      workpiece["weld_process_id"] = process_ids[index];
    }
    for (auto &node : workpiece["nodes"]) {
      if (!node.is_object())
        throw std::invalid_argument("every node must be an object");
      ++seam;
      node["name"] = stem + "_seam" + std::to_string(seam);
      node["uid"] = stem + "_seam" + std::to_string(seam);
      if (process_ids[index] > 0) {
        node["process_class_id"] = group_id;
        node["weld_process_id"] = process_ids[index];
      }
    }
  }
  if (group_id > 0) {
    root["ordinary_process"]["class_id"] = std::to_string(group_id);
    root["multipass_process"]["class_id"] = std::to_string(group_id);
  }
  return root;
}

Json reply_json(const aotai_sdk::GenericReply &reply) {
  return {{"status", reply.status}, {"data", reply.data},
          {"message", reply.message}, {"result", reply.result}};
}

int decimal_id(const aotai_sdk::GenericReply &reply, const std::string &step) {
  if (!reply.accepted())
    throw std::runtime_error(step + " rejected: " + reply_json(reply).dump());
  try {
    const auto text = Json::parse(reply.data).at("id").get<std::string>();
    if (text.empty() || !std::all_of(text.begin(), text.end(), [](char ch) {
          return ch >= '0' && ch <= '9';
        }))
      throw std::invalid_argument("not decimal");
    std::size_t consumed = 0;
    const auto value = std::stoll(text, &consumed);
    if (consumed != text.size() || value <= 0 ||
        value > std::numeric_limits<int>::max())
      throw std::out_of_range("not positive int");
    return static_cast<int>(value);
  } catch (const std::exception &) {
    throw std::runtime_error(step + " returned invalid data.id: " + reply.data);
  }
}

std::pair<int, Json> project_ids(
    const weld_interfaces::srv::ATStringGeneric::Response::SharedPtr &reply) {
  if (reply->status != 200)
    throw std::runtime_error("project_add rejected: status=" +
                             std::to_string(reply->status) + " message=" +
                             reply->message + " data=" + reply->data);
  try {
    const auto data = Json::parse(reply->data);
    const auto &raw_id = data.at("project_id");
    if (!raw_id.is_number_integer() || raw_id <= 0 || raw_id > std::numeric_limits<int>::max())
      throw std::invalid_argument("project_id must be a positive bounded integer");
    const int project_id = raw_id.get<int>();
    const auto &workpiece_ids = data.at("workpieceIds");
    if (project_id <= 0 || !workpiece_ids.is_array() ||
        workpiece_ids.size() != 2)
      throw std::invalid_argument("invalid project id collection");
    for (const auto &id : workpiece_ids)
      if (!id.is_number_integer() || id.get<int>() <= 0)
        throw std::invalid_argument("invalid workpiece id");
    return {project_id, workpiece_ids};
  } catch (const std::exception &) {
    throw std::runtime_error("project_add returned invalid data: " + reply->data);
  }
}

void verify_readback(const Json &data, const Json &expected, int project_id,
                     const Json &workpiece_ids) {
  const auto &project = data.at("project");
  if (project.at("id") != std::to_string(project_id) ||
      data.at("task_name") != expected.at("name"))
    throw std::runtime_error("project readback identity/name mismatch");
  for (const auto *key : {"name", "uid", "direct_run", "loop_execution", "need_reservation", "need_digital_start"})
    if (project.at(key).type() != expected.at("project").at(key).type() ||
        project.at(key) != expected.at("project").at(key))
      throw std::runtime_error("project readback strategy mismatch");
  const auto &workpieces = data.at("workpieces");
  if (!workpieces.is_array() || workpieces.size() != workpiece_ids.size())
    throw std::runtime_error("project readback workpiece count mismatch");
  for (std::size_t i = 0; i < workpieces.size(); ++i) {
    const auto &actual = workpieces.at(i);
    const auto &wanted = expected.at("workpieces").at(i);
    if (!actual.at("id").is_number_integer() || actual.at("id") != workpiece_ids.at(i))
      throw std::runtime_error("project readback workpiece ID order mismatch");
    for (const auto *key : {"name", "uid", "weld_process_id", "process_class_id"})
      if (actual.at(key) != wanted.at(key))
        throw std::runtime_error("project readback workpiece binding mismatch");
    if (actual.at("global_process") != wanted.at("global_process"))
      throw std::runtime_error("global process readback mismatch");
    if (actual.at("nodes").size() != wanted.at("nodes").size())
      throw std::runtime_error("project readback node count mismatch");
    for (std::size_t j = 0; j < actual.at("nodes").size(); ++j)
      for (const auto *key : {"name", "uid", "weld_process_id", "process_class_id"})
        if (actual.at("nodes").at(j).at(key) != wanted.at("nodes").at(j).at(key))
          throw std::runtime_error("project readback node binding mismatch");
  }
}

void print_request(const std::string &step, const std::string &endpoint,
                   const Json &request) {
  std::cout << Json{{"step", step}, {"endpoint", endpoint}, {"request", request}}.dump(2)
            << '\n';
}
} // namespace

int main(int argc, char **argv) {
  bool create = false;
  std::string input_path = kDefaultInput, run_id, prefix;
  for (int i = 1; i < argc; ++i) {
    const std::string option = argv[i];
    if (option == "--create")
      create = true;
    else if (option == "--input" && i + 1 < argc)
      input_path = argv[++i];
    else if (option == "--run-id" && i + 1 < argc)
      run_id = argv[++i];
    else if (option == "--prefix" && i + 1 < argc)
      prefix = argv[++i];
    else {
      std::cerr << "usage: field_create [--input FILE] [--create --run-id ID] "
                   "[--prefix MOCK_PREFIX]\n";
      return 2;
    }
  }
  int calls_started = 0;
  Json partial = Json::object();
  try {
    const Json source = load_json(input_path);
    validate_template(source);
    if (!create) {
      std::cout << "OFFLINE PLAN: no ROS call is made. Full confirmed field "
                   "template follows:\n"
                << source.dump(2)
                << "\nOnline mode performs four database creates plus mandatory readback and "
                   "then stops; even with direct_run=0 it never sends a task "
                   "Action or start/control call.\n";
      return 0;
    }
    if (run_id.empty())
      throw std::invalid_argument("--create requires --run-id");
    if (!prefix.empty() && prefix != "/api_field_create_mock")
      throw std::invalid_argument(
          "--prefix is reserved for /api_field_create_mock");
    Json prepared = prepare(source, run_id);
    aotai_sdk::Client client(prefix);

    print_request("group_add", "/at/data/process_class_add", prepared["group"]);
    ++calls_started;
    const auto group_reply = client.process_class_add(prepared["group"]);
    std::cout << Json{{"step", "group_add"}, {"response", reply_json(group_reply)}}.dump(2) << '\n';
    const int group_id = decimal_id(group_reply, "group_add");
    partial["group_id"] = group_id;

    prepared["ordinary_process"]["class_id"] = std::to_string(group_id);
    print_request("ordinary_process_add", "/at/data/process_add",
                  prepared["ordinary_process"]);
    ++calls_started;
    const auto ordinary_reply = client.process_add(prepared["ordinary_process"]);
    std::cout << Json{{"step", "ordinary_process_add"}, {"response", reply_json(ordinary_reply)}}.dump(2) << '\n';
    const int ordinary_id = decimal_id(ordinary_reply, "ordinary_process_add");
    partial["ordinary_id"] = ordinary_id;

    prepared["multipass_process"]["class_id"] = std::to_string(group_id);
    print_request("multipass_process_add", "/at/data/process_add",
                  prepared["multipass_process"]);
    ++calls_started;
    const auto multipass_reply = client.process_add(prepared["multipass_process"]);
    std::cout << Json{{"step", "multipass_process_add"}, {"response", reply_json(multipass_reply)}}.dump(2) << '\n';
    const int multipass_id = decimal_id(multipass_reply, "multipass_process_add");
    partial["multipass_id"] = multipass_id;

    const Json bound = prepare(source, run_id, group_id, ordinary_id, multipass_id);
    auto request = std::make_shared<weld_interfaces::srv::ATStringGeneric::Request>();
    request->id = "";
    request->data = bound.at("project").dump();
    print_request("project_add", "/at/data/workpiece_task_add",
                  {{"id", request->id}, {"data", request->data}});
    ++calls_started;
    const auto project_reply =
        client.call<weld_interfaces::srv::ATStringGeneric>(
            "/at/data/workpiece_task_add", request, std::chrono::seconds(5));
    std::cout << Json{{"step", "project_add"},
                     {"response", {{"status", project_reply->status},
                                    {"data", project_reply->data},
                                    {"message", project_reply->message}}}}.dump(2)
              << '\n';
    const auto ids = project_ids(project_reply);
    partial["project_id_unverified"] = ids.first;
    partial["workpiece_ids_unverified"] = ids.second;
    auto detail_request = std::make_shared<weld_interfaces::srv::ATStringGeneric::Request>();
    detail_request->id = std::to_string(ids.first);
    detail_request->data = "";
    print_request("project_readback", "/at/data/workpiece_task_detail",
                  {{"id", detail_request->id}, {"data", ""}});
    const auto detail = client.call<weld_interfaces::srv::ATStringGeneric>(
        "/at/data/workpiece_task_detail", detail_request, std::chrono::seconds(5));
    std::cout << Json{{"step", "project_readback"}, {"response", {{"status", detail->status}, {"data", detail->data}, {"message", detail->message}}}}.dump(2) << '\n';
    if (detail->status != 200)
      throw std::runtime_error("Project outcome untrusted: readback rejected");
    verify_readback(Json::parse(detail->data), bound.at("project"), ids.first, ids.second);
    std::cout << Json{{"created", {{"verified_by_readback", true}, {"group_id", group_id},
                                     {"ordinary_process_id", ordinary_id},
                                     {"multipass_process_id", multipass_id},
                                     {"project_id", ids.first},
                                     {"workpiece_ids_in_request_order", ids.second},
                                     {"task_submitted", false},
                                     {"task_started", false}}}}.dump(2)
              << "\n禁止现场提交：本示例到工程数据库创建即停止，不提供任务 Action、启动或控制路径。\n";
    client.close();
    return 0;
  } catch (const aotai_sdk::Error &error) {
    std::cerr << Json{{"partial_creation", partial}, {"retry", false}, {"cleanup", false}}.dump() << '\n';
    const bool uncertain =
        calls_started > 0 &&
        (error.kind == aotai_sdk::ErrorKind::timeout ||
         error.kind == aotai_sdk::ErrorKind::communication ||
         error.kind == aotai_sdk::ErrorKind::closed);
    std::cerr << (uncertain ? "OUTCOME UNKNOWN: " : "CREATE STOPPED: ")
              << "stopped without retry/cleanup: " << error.what() << '\n';
    return 3;
  } catch (const std::exception &error) {
    std::cerr << Json{{"partial_creation", partial}, {"retry", false}, {"cleanup", false}}.dump() << '\n';
    std::cerr << "CREATE STOPPED: no retry/cleanup: " << error.what() << '\n';
    return 3;
  }
}
