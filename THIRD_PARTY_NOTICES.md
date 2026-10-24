# 第三方声明

键光是独立实现的键盘灯光工具，与狼蛛/AULA不存在官方隶属或授权关系。AULA名称及型号用于说明兼容范围。

协议和设备事实的研究来源包括 [AULA 官方网页驱动](https://hub.aulacn.com/) 与 [AulaControl 的协议实现](https://github.com/sgtflixy/AulaControl/blob/main/app/Protocol/AulaProtocol.cs)。本仓库不包含厂商混淆驱动、解包脚本产物或私有研究归档；运行所需设备标识及专用键位数据随源码提供。

软件使用 Python、NumPy、PyAudioWPatch、hidapi、pywebview、pythonnet、clr_loader、proxy_tools、Bottle、CFFI、PyInstaller 等组件，各自保留原许可和版权。详见 [分发组件许可全文](docs/第三方组件许可.txt)。PyInstaller的特殊例外允许分发其打包的程序，不将其GPL许可自动扩展为此项目源码许可。

WebView2由Microsoft提供并受微软许可约束。安装包在缺少运行环境时调用微软原版引导程序联网安装；未把整个WebView2运行环境声称为离线内置。

Inno Setup中文消息文件来自官方固定标签is-6_7_3： https://raw.githubusercontent.com/jrsoftware/issrc/is-6_7_3/Files/Languages/Unofficial/ChineseSimplified.isl

本仓库尚未指定统一源码许可证；公开发布不替代第三方许可条件。
