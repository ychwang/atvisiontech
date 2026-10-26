cmake_minimum_required(VERSION 3.16)
project(aotai_ros2_query_demo LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
option(BUILD_SDK_DEMO "Build the optional installed-SDK demo" OFF)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(weld_interfaces REQUIRED)

add_executable(aotai_ros2_raw_query src/main.cpp)
ament_target_dependencies(aotai_ros2_raw_query rclcpp weld_interfaces)

if(BUILD_SDK_DEMO)
  find_package(aotai_sdk_cpp REQUIRED CONFIG)
  add_executable(aotai_ros2_sdk_query src/sdk_main.cpp)
  target_link_libraries(aotai_ros2_sdk_query aotai_sdk_cpp::aotai_sdk)
  ament_target_dependencies(aotai_ros2_sdk_query rclcpp weld_interfaces)
endif()

if(BUILD_TESTING AND BUILD_SDK_DEMO)
  find_package(Python3 REQUIRED COMPONENTS Interpreter)
  add_executable(aotai_ros2_demo_mock ../../../tests/cpp_demo_mock.cpp)
  ament_target_dependencies(aotai_ros2_demo_mock rclcpp weld_interfaces)
  add_test(
    NAME aotai_ros2_demo_mock
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/../../../tests/test_cpp_demo.py
      $<TARGET_FILE:aotai_ros2_demo_mock>
      $<TARGET_FILE:aotai_ros2_raw_query>
      $<TARGET_FILE:aotai_ros2_sdk_query>)
  set_tests_properties(aotai_ros2_demo_mock PROPERTIES
    ENVIRONMENT "ROS_DOMAIN_ID=219;ROS_LOCALHOST_ONLY=1")
endif()

ament_package()
