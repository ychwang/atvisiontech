#include <aotai_sdk/client.hpp>
#include <fstream>
#include <iostream>
// Run `aotai_cpp_multipass INPUT.json [--execute]`; without --execute it
// prints local MCS JSON only.  --execute may submit an Action after preflight.
int main(int argc, char **argv) {
  if (argc < 2) {
    std::cerr << "usage: multipass INPUT.json [--execute]\n";
    return 2;
  }
  try {
    std::ifstream f(argv[1]);
    aotai_sdk::json input;
    f >> input;
    auto task = aotai_sdk::Client::assemble_task(input);
    std::cout << task.dump(2) << "\n";
    if (argc < 3 || std::string(argv[2]) != "--execute")
      return 0; // explicit: execution requires verified live DB data.
    if (input.value("demonstration_only", true) ||
        !input.value("coordinate_contract", aotai_sdk::json::object())
             .value("confirmed", false))
      throw std::runtime_error("--execute rejects demonstration/unconfirmed "
                               "coordinate input before ROS connection");
    aotai_sdk::Client c;
    // Each seam may refer to a different DB process. Read back and validate
    // each one in its own input slice; never infer cross-process array
    // ordering.
    for (const auto &seam : input["seams"]) {
      auto detail = c.process_detail(seam["process_id"].get<int>());
      if (!detail.accepted())
        throw std::runtime_error(detail.message);
      auto one = input;
      one["seams"] = aotai_sdk::json::array({seam});
      aotai_sdk::Client::validate_executable(
          one, aotai_sdk::json::parse(detail.data));
    }
    auto h = c.submit_task(task, [](const std::string &feedback) {
      std::cerr << "task feedback: " << feedback << "\n";
    });
    auto r = c.wait_result(h, std::chrono::seconds(30));
    std::cout << r.status_message << "\n";
    return r.business_success ? 0 : 3;
  } catch (const std::exception &e) {
    std::cerr << e.what() << "\n";
    return 1;
  }
}
