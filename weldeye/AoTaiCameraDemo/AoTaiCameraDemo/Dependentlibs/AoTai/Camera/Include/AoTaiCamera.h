#include "windows.h"
#include <process.h>
#include <atomic>
#include"Dependentlibs/AoTai/Include/CameraApi.h"
#include"Dependentlibs/AoTai/Include/CameraGrabber.h"
#include <thread>
#include<iostream>
class AoTaiCamera
{
public:
	/// <summary>
	/// 构造函数
	/// </summary>
	AoTaiCamera();
	/// <summary>
	/// 相机初始化 
	/// </summary>
	/// <returns>0代表成功，/// 1代表失败</returns>
	int AoTaiCameraIni();
	/// <summary>
	/// 获取图像数据
	/// </summary>
	/// <returns>图像指针</returns>
	BYTE* GetImage();
	/// <summary>
	/// 获取相机状态
	/// </summary>
	/// <returns>true代表相机正常采集，false代表相机掉线</returns>
	bool GetCameraStatus();
	/// <summary>
	/// 关闭相机
	/// </summary>
	void CloseDevice();
	/// <summary>
	/// 获取图像的宽
	/// </summary>
	/// <returns>图像宽</returns>
	int GetImageWidth();
	/// <summary>
	/// 获取图像的高
	/// </summary>
	/// <returns>图像高</returns>
	int GetImageHeight();
	/// <summary>
	/// 设置相机增益
	/// </summary>
	/// <param name="value">相机增益，最大值192，最小值64</param>
	void UpdataCameraGain(int value);
	/// <summary>
	/// 设置相机曝光时间
	/// </summary>
	/// <param name="value">曝光时间，最大值8190，最小值43，单位us</param>
	void UpdataCameraExposureLine(int value);
	/// <summary>
	/// 设置相机gamma
	/// </summary>
	/// <param name="value">gamma，最大值250，最小值0</param>
	void UpdataCameraGamma(int value);
	/// <summary>
	/// 设置自动色温
	/// </summary>
	/// <param name="action">自动色温，true开启，false关闭</param>
	void UpataAutoClrTemp(bool action);
	/// <summary>
	/// 设置图像上下翻转
	/// </summary>
	/// <param name="action">上下翻转，true开启，false关闭</param>
	void UpataRotate(bool action);
	~AoTaiCamera();

private:
	void CameraSnapStart();
	std::thread workerThread;
	std::atomic<bool> running;
	tSdkCameraDevInfo sCameraList[10];
	INT iCameraNums;
	CameraSdkStatus status;
	tSdkCameraCapbility sCameraInfo;
	tSdkFrameHead 	g_tFrameHead;
	CameraHandle    m_hCamera;
	char g_CameraName[64];
	bool bCamerStatus;
	bool bCamerOffline;
	int iConsecutiveFrame;
	BYTE* m_pFrameBuffer;
	BYTE* m_processBuffer;
	BYTE* g_readBuf;
	int iQuit;
	int	iRecordState;
	int iImageWidth;
	int iImageHeight;
};