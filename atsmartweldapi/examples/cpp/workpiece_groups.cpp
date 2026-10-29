#include <aotai_sdk/client.hpp>

#include <algorithm>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

namespace {
int positive_reply_id(const aotai_sdk::GenericReply &reply) {
  const auto text =
      aotai_sdk::json::parse(reply.data).at("id").get<std::string>();
  if (text.empty() ||
      !std::all_of(text.begin(), text.end(),
                   [](unsigned char ch) { return ch >= '0' && ch <= '9'; }))
    throw std::invalid_argument("group add returned invalid decimal data.id");
  std::size_t consumed = 0;
  const auto parsed = std::stoll(text, &consumed);
  if (consumed != text.size() || parsed <= 0 ||
      parsed > std::numeric_limits<int>::max())
    throw std::invalid_argument("group add returned invalid positive data.id");
  return static_cast<int>(parsed);
}

void require_clean_update(const aotai_sdk::GenericReply &reply) {
  // status=200 with a non-empty message is not a successful update.
  // Stop here to avoid using or deleting an unconfirmed record.
  if (!reply.accepted() || !reply.message.empty())
    throw std::runtime_error(
        "workpiece_group_update is not confirmed: status=" +
        std::to_string(reply.status) + " message=" + reply.message);
}
} // namespace

int main(int argc, char **argv) {
  bool execute = false;
  std::string prefix;
  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg == "--execute")
      execute = true;
    else if (arg == "--prefix" && i + 1 < argc)
      prefix = argv[++i];
    else {
      std::cerr
          << "usage: workpiece_groups [--execute --prefix /api_group_mock]\n";
      return 2;
    }
  }
  if (!execute) {
    std::cout << "Offline example values: add 分组-1; update id=6 name=66; "
                 "runtime uses the newly returned ID, not example IDs.\n";
    return 0;
  }
  if (prefix != "/api_group_mock") {
    std::cerr << "--execute is restricted to --prefix /api_group_mock\n";
    return 2;
  }
  try {
    aotai_sdk::Client client(prefix);
    const auto add = client.workpiece_group_add({{"name", "分组-1"}});
    if (!add.accepted())
      throw std::runtime_error(add.message);
    const int id = positive_reply_id(add);
    const auto listing = client.workpiece_group_list(aotai_sdk::json::array(),
                                                     1, 10, "id", false);
    if (!listing.accepted())
      throw std::runtime_error(listing.message);
    const auto detail = client.workpiece_group_detail(id);
    if (!detail.accepted())
      throw std::runtime_error(detail.message);
    require_clean_update(client.workpiece_group_update(
        {{"id", std::to_string(id)}, {"name", "66"}}));
    const auto remove = client.workpiece_group_delete(id);
    if (!remove.accepted())
      throw std::runtime_error(remove.message);
    std::cout << "created/listed/detailed/updated/deleted dynamic group id="
              << id << "\n";
    client.close();
    return 0;
  } catch (const std::exception &error) {
    std::cerr << "workpiece-group workflow failed: " << error.what() << "\n";
    return 3;
  }
}
