# AT Vision 发布资料

本仓库存放 AT Vision SDK `v4.3.1` 的 Windows x64 和 Linux x64 发布包（构建标识 `63e7fda9`），以及 AoTaiCameraDemo 相机示例项目。

## 文件

| 路径 | 平台 | 内容 |
| --- | --- | --- |
| `lasertracksystem/at_vision-v4.3.1-windows-x64+63e7fda9.zip` | Windows x64 | 头文件、库、DLL 和示例源码及程序 |
| `lasertracksystem/at_vision-v4.3.1-linux-x64+63e7fda9.tar.gz` | Linux x64 | 头文件、共享库、CMake 包配置和示例源码及程序 |
| `weldeye/AoTaiCameraDemo/` | Windows | Visual Studio C++ 相机示例、项目依赖和 x64 可执行文件 |

## 使用

下载对应平台的压缩包并解压。包内的 `include/at_vision/` 提供头文件，`lib/` 提供库文件，`examples/` 提供示例。Linux 包含 `lib/cmake/at_vision/at_vision-config.cmake`，可供 CMake 项目查找。具体接口与运行方式请以包内头文件和示例源码为准。

AT Vision SDK 发布包不包含其构建源码；完整产品文档未包含在当前目录中。

## AoTaiCameraDemo

使用 Visual Studio 打开 `weldeye/AoTaiCameraDemo/AoTaiCameraDemo.sln`。项目的 x64 Debug 和 Release 配置通过属性表引用 `AoTaiCameraDemo/Dependentlibs/` 中的 AoTai 相机 SDK 与 OpenCV 3.1.0；`AoTaiCameraDemo.cpp` 展示相机初始化、取图和显示。`x64/` 中还保留了现有的可执行文件及运行依赖。Visual Studio 缓存和构建中间文件未纳入版本控制。

2026年10月19日19:41:45  更新测试
