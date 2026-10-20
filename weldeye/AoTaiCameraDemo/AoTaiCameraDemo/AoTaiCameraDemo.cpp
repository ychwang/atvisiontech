
#include <iostream>
#include"AoTaiCamera.h"
#include <opencv2/opencv.hpp>

int main()
{
	AoTaiCamera Camera;
	Camera.AoTaiCameraIni();
	int width = Camera.GetImageWidth();
	int height = Camera.GetImageHeight();
	if (Camera.GetCameraStatus()) {
		while (true) {
			cv::Mat matImage(
				cvSize(width, height), CV_8UC3, Camera.GetImage());
			cv::imshow("camera", matImage);
			cv::waitKey(1);
		}
	}
	Camera.CloseDevice();
}

