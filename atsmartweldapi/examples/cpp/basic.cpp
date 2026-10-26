#include <aotai_sdk/client.hpp>
#include <iostream>
int main(int argc, char **argv) {
  // Run `aotai_cpp_basic [--connect]` after sourcing ROS/weld_interfaces.
  // Safe by default: this does not initialize ROS or contact equipment.
  if (argc < 2 || std::string(argv[1]) != "--connect") {
    std::cout << "Protocol-only example. Use --connect for a read-only status "
                 "query.\n";
    return 0;
  }
  try {
    aotai_sdk::Client client;
    auto r = client.robot_status();
    std::cout << r.status << " " << r.message << "\n";
    client.close();
    return r.accepted() ? 0 : 2;
  } catch (const std::exception &e) {
    std::cerr << e.what() << "\n";
    return 3;
  }
}
