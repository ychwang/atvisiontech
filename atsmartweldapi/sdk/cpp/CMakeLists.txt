cmake_minimum_required(VERSION 3.16)
project(aotai_sdk_cpp LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(weld_interfaces REQUIRED)
add_library(aotai_sdk src/client.cpp src/mapper.cpp)
target_include_directories(aotai_sdk PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include> $<INSTALL_INTERFACE:include>)
ament_target_dependencies(aotai_sdk rclcpp rclcpp_action weld_interfaces)
add_executable(aotai_cpp_welder ../../examples/cpp/welder.cpp)
target_link_libraries(aotai_cpp_welder aotai_sdk)
add_executable(aotai_cpp_robot ../../examples/cpp/robot.cpp)
target_link_libraries(aotai_cpp_robot aotai_sdk)
add_executable(aotai_cpp_engineering ../../examples/cpp/engineering.cpp)
target_link_libraries(aotai_cpp_engineering aotai_sdk)
add_executable(aotai_cpp_camera_capture ../../examples/cpp/camera_capture.cpp)
target_link_libraries(aotai_cpp_camera_capture aotai_sdk)
add_executable(aotai_cpp_basic ../../examples/cpp/basic.cpp)
target_link_libraries(aotai_cpp_basic aotai_sdk)
add_executable(aotai_cpp_multipass ../../examples/cpp/multipass.cpp)
target_link_libraries(aotai_cpp_multipass aotai_sdk)
add_executable(aotai_cpp_control ../../examples/cpp/control.cpp)
target_link_libraries(aotai_cpp_control aotai_sdk)
add_executable(aotai_cpp_camera_cloud ../../examples/cpp/camera_cloud.cpp)
target_link_libraries(aotai_cpp_camera_cloud aotai_sdk)
add_executable(aotai_cpp_subscribe ../../examples/cpp/subscribe.cpp)
target_link_libraries(aotai_cpp_subscribe aotai_sdk)
add_executable(aotai_cpp_process_inspect ../../examples/cpp/process_inspect.cpp)
target_link_libraries(aotai_cpp_process_inspect aotai_sdk)
add_executable(aotai_cpp_process_workflow ../../examples/cpp/process_workflow.cpp)
target_link_libraries(aotai_cpp_process_workflow aotai_sdk)
add_executable(aotai_cpp_workpiece_groups ../../examples/cpp/workpiece_groups.cpp)
target_link_libraries(aotai_cpp_workpiece_groups aotai_sdk)
get_filename_component(AOTAI_REPO_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../../../.." ABSOLUTE)
if(BUILD_TESTING)
  find_package(Python3 REQUIRED COMPONENTS Interpreter)
  enable_testing()
  add_executable(aotai_cpp_assembler_test ../../tests/cpp/assembler_test.cpp)
  target_link_libraries(aotai_cpp_assembler_test aotai_sdk)
  add_test(NAME aotai_cpp_assembler COMMAND aotai_cpp_assembler_test)
  add_executable(aotai_cpp_ros_mock_test ../../tests/cpp/ros_mock_test.cpp)
  target_link_libraries(aotai_cpp_ros_mock_test aotai_sdk)
  add_test(NAME aotai_cpp_ros_mock COMMAND aotai_cpp_ros_mock_test)
  set_tests_properties(aotai_cpp_ros_mock PROPERTIES ENVIRONMENT "LD_LIBRARY_PATH=${AOTAI_REPO_ROOT}/install/weld_interfaces/lib:$ENV{LD_LIBRARY_PATH};ROS_DOMAIN_ID=218;ROS_LOCALHOST_ONLY=1")
  add_test(NAME aotai_process_inspect_mock
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/../../tests/test_process_inspect_mock.py
      --cpp-executable $<TARGET_FILE:aotai_cpp_process_inspect>
      --python-example ${CMAKE_CURRENT_SOURCE_DIR}/../../examples/python/process_inspect.py)
  add_test(NAME aotai_process_workflow_mock
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/../../tests/test_process_workflow_mock.py
      --cpp-executable $<TARGET_FILE:aotai_cpp_process_workflow>
      --python-example ${CMAKE_CURRENT_SOURCE_DIR}/../../examples/python/process_workflow.py)
  set_tests_properties(aotai_process_workflow_mock PROPERTIES ENVIRONMENT
    "PYTHONPATH=${CMAKE_CURRENT_SOURCE_DIR}/../python:$ENV{PYTHONPATH};ROS_DOMAIN_ID=223;ROS_LOCALHOST_ONLY=1")
  add_test(NAME aotai_workpiece_groups_mock
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/../../tests/test_workpiece_groups_mock.py
      --cpp-executable $<TARGET_FILE:aotai_cpp_workpiece_groups>)
  set_tests_properties(aotai_workpiece_groups_mock PROPERTIES ENVIRONMENT
    "PYTHONPATH=${CMAKE_CURRENT_SOURCE_DIR}/../python:$ENV{PYTHONPATH};ROS_DOMAIN_ID=224;ROS_LOCALHOST_ONLY=1")
  add_test(NAME aotai_device_control_mock
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/../../tests/test_device_control_mock.py
      --cpp-welder $<TARGET_FILE:aotai_cpp_welder> --cpp-robot $<TARGET_FILE:aotai_cpp_robot>)
  set_tests_properties(aotai_device_control_mock PROPERTIES ENVIRONMENT
    "PYTHONPATH=${CMAKE_CURRENT_SOURCE_DIR}/../python:$ENV{PYTHONPATH};ROS_DOMAIN_ID=221;ROS_LOCALHOST_ONLY=1")
  set_tests_properties(aotai_process_inspect_mock PROPERTIES ENVIRONMENT
    "PYTHONPATH=${CMAKE_CURRENT_SOURCE_DIR}/../python:$ENV{PYTHONPATH};ROS_DOMAIN_ID=220;ROS_LOCALHOST_ONLY=1")
endif()
install(TARGETS aotai_sdk EXPORT export_${PROJECT_NAME} ARCHIVE DESTINATION lib LIBRARY DESTINATION lib RUNTIME DESTINATION bin)
install(TARGETS aotai_cpp_welder aotai_cpp_robot aotai_cpp_basic aotai_cpp_multipass aotai_cpp_control aotai_cpp_camera_cloud aotai_cpp_subscribe aotai_cpp_process_inspect aotai_cpp_process_workflow aotai_cpp_workpiece_groups aotai_cpp_engineering aotai_cpp_camera_capture RUNTIME DESTINATION bin
)
ament_export_targets(export_${PROJECT_NAME} HAS_LIBRARY_TARGET)
ament_export_dependencies(rclcpp rclcpp_action weld_interfaces)
install(DIRECTORY include/ DESTINATION include)
ament_package()
