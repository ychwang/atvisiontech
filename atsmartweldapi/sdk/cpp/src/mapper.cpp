#include "aotai_api/client.hpp"
#include <cmath>
#include <limits>
#include <map>
#include <set>

namespace aotai::api {
static void require(bool ok, const std::string &s) {
  if (!ok)
    throw Error(ErrorKind::validation, s);
}
static bool finite(const json &p) {
  return p.is_number() && std::isfinite(p.get<double>());
}
// The shared external schema is intentionally narrow: unknown fields are
// errors, not silently discarded precomputed trajectories or safety metadata.
static void keys(const json &object, std::initializer_list<const char *> fields,
                 const std::string &where) {
  require(object.is_object(), where + " must be an object");
  std::set<std::string> allowed;
  for (auto field : fields) {
    allowed.insert(field);
    require(object.contains(field), where + " missing " + field);
  }
  for (const auto &item : object.items())
    require(allowed.count(item.key()) != 0,
            where + " unsupported field " + item.key());
}
static void integer(const json &value, const std::string &where, int minimum) {
  require(value.is_number_integer() && value.get<double>() >= minimum &&
              value.get<double>() <= std::numeric_limits<int>::max(),
          where + " must be an in-range integer");
}
static void nonempty(const json &value, const std::string &where) {
  require(value.is_string() && value.get<std::string>().find_first_not_of(
                                   " \t\r\n") != std::string::npos,
          where + " must be nonempty text");
}
static void validate_global_process(const json &value) {
  keys(value,
       {"coplanarity_check_mode", "enable_offset_correction",
        "target_accuracy_threshold", "smoothing_parameters",
        "planning_parameters", "enable_free_pose", "enable_input_safe_point"},
       "workpiece.global_process");
  for (auto key : {"coplanarity_check_mode", "enable_offset_correction",
                   "enable_free_pose", "enable_input_safe_point"}) {
    integer(value[key], key, 0);
    require(value[key] == 0 || value[key] == 1,
            std::string(key) + " must be 0 or 1");
  }
  require(finite(value["target_accuracy_threshold"]) &&
              value["target_accuracy_threshold"].get<double>() >= 0.0,
          "target_accuracy_threshold must be finite and non-negative");
  for (auto key : {"smoothing_parameters", "planning_parameters"})
    require(value[key].is_string(), std::string(key) + " must be text");
}
static void validate_input(const json &in) {
  keys(in,
       {"schema_version", "demonstration_only", "coordinate_contract",
        "project", "workpiece", "seams"},
       "input");
  integer(in["schema_version"], "schema_version", 1);
  require(in["schema_version"] == 1, "schema_version must be 1");
  require(in["demonstration_only"].is_boolean(),
          "demonstration_only must be bool");
  const auto &cc = in["coordinate_contract"];
  keys(cc,
       {"frame", "position_unit", "orientation_convention", "angle_unit",
        "confirmed"},
       "coordinate_contract");
  require(cc["confirmed"].is_boolean(), "confirmed must be bool");
  // This mapper emits raw point x/y/z/w/p/r without conversion. Its narrow
  // schema is fixed; `confirmed` cannot override a different convention.
  const std::pair<const char *, const char *> coordinate_contract[] = {
      {"frame", "RobotBase"},
      {"position_unit", "mm"},
      {"orientation_convention", "XYZ Euler: w,p,r"},
      {"angle_unit", "degree"},
  };
  for (const auto &[field, expected] : coordinate_contract) {
    nonempty(cc[field], field);
    require(cc[field] == expected,
            std::string("coordinate_contract.") + field + " must be " + expected +
                " for this mapper");
  }
  const auto &project = in["project"];
  const auto &wp = in["workpiece"];
  keys(project, {"uid", "name", "system_config_id"}, "project");
  keys(wp, {"uid", "name", "robot_tcp_id", "global_process"}, "workpiece");
  validate_global_process(wp["global_process"]);
  for (const auto *object : {&project, &wp}) {
    nonempty((*object)["uid"], "uid");
    nonempty((*object)["name"], "name");
  }
  integer(project["system_config_id"], "system_config_id", 0);
  integer(wp["robot_tcp_id"], "robot_tcp_id", 0);
  require(in["seams"].is_array() && !in["seams"].empty(),
          "seams must be nonempty array");
  std::set<std::string> seen;
  for (const auto &seam : in["seams"]) {
    keys(seam, {"uid", "name", "process_id", "base_path", "passes"}, "seam");
    nonempty(seam["uid"], "seam uid");
    nonempty(seam["name"], "seam name");
    require(seen.insert(seam["uid"].get<std::string>()).second,
            "duplicate seam uid");
    integer(seam["process_id"], "process_id", 0);
    require(seam["base_path"].is_array() && seam["base_path"].size() == 2,
            "only a two-point line base_path is supported");
    for (const auto &point : seam["base_path"]) {
      keys(point, {"x", "y", "z", "w", "p", "r"}, "base_path point");
      for (const auto &item : point.items())
        require(finite(item.value()),
                "path must be finite numeric x,y,z,w,p,r");
    }
    require(seam["passes"].is_array() && !seam["passes"].empty(),
            "passes must be nonempty array");
    require(seam["passes"].size() <= 1 ||
                wp["global_process"]["coplanarity_check_mode"] == 1,
            "multi-pass line input requires coplanarity_check_mode=1 (coplanar)");
    int expected = 1;
    for (const auto &pass : seam["passes"]) {
      keys(pass,
           {"index", "layer", "offset_horizontal_mm", "offset_vertical_mm",
            "offset_start_mm", "offset_end_mm", "direction_horizontal",
            "direction_vertical", "direction_forward", "direction_end",
            "weld_layer"},
           "pass");
      integer(pass["index"], "index", 1);
      integer(pass["layer"], "layer", 1);
      require(pass["index"] == expected++,
              "passes must have index 1..N in input order");
      integer(pass["weld_layer"], "weld_layer", -1);
      for (auto key : {"offset_horizontal_mm", "offset_vertical_mm",
                       "offset_start_mm", "offset_end_mm"})
        require(finite(pass[key]),
                std::string(key) + " must be finite numeric");
      for (auto key : {"direction_horizontal", "direction_vertical",
                       "direction_forward", "direction_end"}) {
        integer(pass[key], key, 0);
        require(pass[key] == 0 || pass[key] == 1,
                std::string(key) + " must be 0 or 1");
      }
    }
  }
}
json Client::assemble_task(const json &in) {
  validate_input(in);
  require(in.value("schema_version", 0) == 1, "schema_version must be 1");
  require(in.contains("project") && in.contains("workpiece") &&
              in.contains("seams"),
          "missing project/workpiece/seams");
  const auto &project = in["project"];
  const auto &workpiece = in["workpiece"];
  json out = {{"project",
               {{"id", 0},
                {"name", project.value("name", "")},
                {"uid", project.value("uid", "")},
                {"loop_execution", 0},
                {"need_digital_start", 0},
                {"direct_run", 0},
                {"need_reservation", 0},
                {"system_config_id", project.value("system_config_id", 0)},
                {"execution_mode", 1},
                {"task_source", 0}}},
              {"workpieces", json::array()}};
  json wp = {{"id", 0},
             {"workpiece_id", 0},
             {"uid", workpiece.value("uid", "")},
             {"name", workpiece.value("name", "")},
             {"laser_task_type", 0},
             {"scanning_welding", 0},
             {"scanning_mode", 0},
             {"nodes", json::array()},
             {"weld_process_id", 0},
             {"global_process", workpiece["global_process"]},
             {"workpiece_type", 0},
             {"robot_tcp_id", workpiece.value("robot_tcp_id", 0)},
             {"workpiece_db_id", 0},
             {"tracker_type", 2}};
  for (const auto &s : in["seams"]) {
    require(s.contains("base_path") && s["base_path"].size() == 2,
            "only two-point base_path is supported");
    require(s.contains("passes") && !s["passes"].empty(), "passes required");
    json n = {{"uid", s.value("uid", "")},
              {"name", s.value("name", "")},
              {"node_type", 0},
              {"path", json::array()},
              {"weld_process_id", s.value("process_id", 0)},
              {"is_multi", true},
              {"multi_layer_num", 0},
              {"multi_pass_num", s["passes"].size()},
              {"multi_pass_params", json::array()}};
    int mx = 0, expected = 1;
    for (auto &p : s["passes"]) {
      require(p.value("index", 0) == expected++,
              "passes must be ordered index 1..N");
      int l = p.value("layer", 0);
      require(l >= 1, "layer must be >=1");
      mx = std::max(mx, l);
      n["multi_pass_params"].push_back(
          {{"multi_index", p["index"]},
           {"multi_offset_horizontal", p.value("offset_horizontal_mm", 0.0)},
           {"multi_offset_vertical", p.value("offset_vertical_mm", 0.0)},
           {"multi_offset_start", p.value("offset_start_mm", 0.0)},
           {"multi_offset_end", p.value("offset_end_mm", 0.0)},
           {"multi_dir_horizontal", p.value("direction_horizontal", 0)},
           {"multi_dir_vertical", p.value("direction_vertical", 0)},
           {"multi_dir_forward", p.value("direction_forward", 0)},
           {"multi_offset_dir_end", p.value("direction_end", 0)},
           {"multi_offset_mode", 0},
           {"multi_offset_x", 0.0},
           {"layer_index", l},
           {"weld_layer", p.value("weld_layer", -1)}});
    }
    n["multi_layer_num"] = mx;
    for (const auto &p : s["base_path"]) {
      for (auto k : {"x", "y", "z", "w", "p", "r"})
        require(p.contains(k) && finite(p[k]), "path needs finite x,y,z,w,p,r");
      n["path"].push_back({{"x", p["x"]},
                           {"y", p["y"]},
                           {"z", p["z"]},
                           {"w", p["w"]},
                           {"p", p["p"]},
                           {"r", p["r"]},
                           {"uid", s.value("uid", "") + "-point-" +
                                       std::to_string(n["path"].size() + 1)},
                           {"valid", true}});
    }
    wp["nodes"].push_back(n);
  }
  out["workpieces"].push_back(wp);
  return out;
}
void Client::validate_executable(const json &in, const json &detail) {
  validate_input(in);
  require(in["seams"].size() == 1,
          "validate one seam/process detail at a time");
  require(!in.value("demonstration_only", true),
          "demonstration input cannot execute");
  auto c = in.value("coordinate_contract", json::object());
  require(c.value("confirmed", false), "coordinate contract must be confirmed");
  const auto &global_process = in["workpiece"]["global_process"];
  for (const auto &seam : in["seams"])
    require(seam["passes"].size() <= 1 ||
                global_process["coplanarity_check_mode"] == 1,
            "multi-pass execution requires coplanarity_check_mode=1");
  require(in["project"].value("system_config_id", 0) > 0 &&
              in["workpiece"].value("robot_tcp_id", 0) > 0,
          "execution requires positive confirmed system_config_id and "
          "robot_tcp_id");
  int process = -1;
  for (const auto &seam : in["seams"]) {
    int id = seam.value("process_id", 0);
    require(id > 0, "execution requires positive process_id");
    if (process < 0)
      process = id;
    else
      require(process == id,
              "one preflight process_detail call supports one process_id only");
  }
  require(detail.is_object() && detail.contains("process_vec") &&
              detail.contains("multi_pass_params") &&
              detail["process_vec"].is_array() &&
              detail["multi_pass_params"].is_array(),
          "process detail missing arrays");
  size_t n = 0;
  for (auto &s : in["seams"])
    n += s["passes"].size();
  require(detail["process_vec"].size() == n &&
              detail["multi_pass_params"].size() == n,
          "current code does not prove execution order: array size mismatch");
  size_t i = 0;
  std::map<int, int> bead_count_by_layer;
  for (auto &s : in["seams"])
    for (auto &p : s["passes"]) {
      const int layer = p["layer"].get<int>();
      const int expected_bead_num = ++bead_count_by_layer[layer];
      auto &a = detail["process_vec"][i];
      auto &m = detail["multi_pass_params"][i++];
      require(a.is_object() && m.is_object(),
              "process detail entries must be objects");
      for (auto key : {"weld_bead_process_order", "layer_num", "bead_num"}) {
        require(a.contains(key), "process detail identifier missing");
        integer(a[key], key, 1);
      }
      for (auto key : {"multi_index", "layer_index"}) {
        require(m.contains(key), "multi-pass detail identifier missing");
        integer(m[key], key, 1);
      }
      require(a.value("weld_bead_process_order", -1) == p["index"] &&
                  a.value("layer_num", -1) == p["layer"] &&
                  a.value("bead_num", -1) == expected_bead_num &&
                  m.value("multi_index", -1) == p["index"] &&
                  m.value("layer_index", -1) == p["layer"],
              "current code does not prove execution order: DB order mismatch");
    }
}

} // namespace aotai::api
