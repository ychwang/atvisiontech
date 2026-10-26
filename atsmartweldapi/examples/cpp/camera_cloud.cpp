#include <aotai_sdk/client.hpp>
#include <fstream>
#include <iostream>
// Run `aotai_cpp_camera_cloud --download OUT.ndjson` only after acquisition.
// `--download` is deliberately required: it invokes camera
// download only; acquisition must have been explicitly completed beforehand.
int main(int argc, char **argv) {
  if (argc != 3 || std::string(argv[1]) != "--download") {
    std::cout << "usage: camera_cloud --download OUTPUT.ndjson\n";
    return argc == 1 ? 0 : 2;
  }
  try {
    std::ofstream out(argv[2]);
    if (!out)
      throw std::runtime_error("cannot open output");
    aotai_sdk::Client c;
    auto handle = c.download_cloud(
        aotai_sdk::json{{"frequency", 30}}, [&](const auto &f) {
          // Preserve raw fields; the VZ producer stores RGB in W/P/R, not
          // Euler. No frame/unit inference. A failed download leaves a partial
          // file.
          aotai_sdk::json row = {{"sequence_id", f.sequence_id},
                                 {"total_blocks", f.total_blocks},
                                 {"timestamp", f.point_cloud.timestamp},
                                 {"points", aotai_sdk::json::array()}};
          for (const auto &p : f.point_cloud.points)
            row["points"].push_back({{"x", p.x},
                                     {"y", p.y},
                                     {"z", p.z},
                                     {"w", p.w},
                                     {"p", p.p},
                                     {"r", p.r}});
          out << row.dump() << '\n';
          if (!out)
            throw std::runtime_error("output write failed");
        });
    c.wait_cloud_result(handle, std::chrono::seconds(60));
    std::cout
        << "Cloud download complete; metadata remains deployment-specific\n";
    return 0;
  } catch (const std::exception &e) {
    std::cerr << e.what() << "\n";
    return 1;
  }
}
