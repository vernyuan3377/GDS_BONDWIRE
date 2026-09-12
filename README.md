# GDS BondWire Planner

[English](README_EN.md) | 简体中文

用于芯片封装打线规划的 Python/PyQt5 桌面软件。软件可同时读取 Altium Designer
`PcbLib` 封装和 Virtuoso 导出的 GDSII，识别芯片与 PCB PAD，编辑 BondWire 关系，
并导出供打线公司使用的 PDF 图纸。

## 主要功能

- 读取 Altium 二进制 `PcbLib`，显示原生封装图形、第一金属层和 PAD 编号。
- 读取 GDSII，通过可配置的 `CB Drawing` 和 `AP Pin` 层识别芯片 PAD 与名称。
- 调整芯片位置、芯片旋转角度和 PCB 封装旋转角度。
- 在打线界面绘制手工 PCB PAD，可设置任意编号、位置、尺寸、旋转、形状和颜色。
- 手工 PAD 支持鼠标拖动、坐标编辑、mil/mm 单位切换，并支持左/右/上/下对齐和水平/垂直等距分布；等距分布可使用自动间距或指定固定间距。
- 芯片 PAD 标签保持屏幕正向，不随芯片旋转。
- 点击芯片 PAD、外侧标签或 PCB PAD 创建 BondWire。
- 双击非 PAD 区域创建自由连接端点。
- 拖动 BondWire 两端微调实际落点。
- 调整 BondWire 颜色、二维显示粗细和三维线径。
- 3D 显示 PCB 第一金属层、芯片 PAD 和 BondWire。
- 在 3D 视图中拖动打线中间点，调整 XY、弧高和目标长度。
- 使用三维二次贝塞尔曲线积分计算真实打线长度。
- 保存和打开 `.bondwire.json` 工程。
- 导出 A3 横向 PDF，可选择是否包含芯片 PAD 标签。
- 导出 AD26 封装参考 DelphiScript，并附带 PAD 坐标表。

## 安装

建议使用 Python 3.11：

```powershell
python -m pip install -r requirements.txt
```

## 运行

```powershell
python run.py
```

也可以双击 `start.bat`。软件启动后保持空白，通过工具栏打开 PcbLib、GDS 或工程文件。

命令行加载：

```powershell
python run.py --pcb your.PcbLib --gds your.gds
python run.py --project example.bondwire.json
python run.py --pcb your.PcbLib --gds your.gds --export-pdf drawing.pdf
```

## 基本流程

1. 打开 `PcbLib` 和 GDS 文件。
2. 检查 GDS 层映射。默认使用 `CB Drawing = 76/0`、`AP Pin = 126/0`，搜索深度为 `10`。
3. 调整芯片位置、芯片旋转角度和 PCB 封装旋转角度。
4. 如需自定义封装，在“封装绘制”区域添加手工 PAD，可用 mil 或 mm 输入坐标和尺寸，拖动位置后可批量对齐或等距分布。
5. 切换到“绘制 BondWire”，依次点击芯片端点和 PCB 端点。
6. 拖动连线两端微调落点。
7. 打开“3D 视图”，调整打线中间点、高度或目标长度。
8. 保存工程并导出 PDF，必要时导出 AD26 封装参考脚本。

## 识别说明

GDSII 通常只保存 layer/datatype 数字，不保存 Virtuoso 层名称，因此软件允许手动配置
`CB Drawing layer/datatype` 和 `AP Pin layer/texttype`。软件从 CB Drawing 图形中读取可打线
PAD，并从 AP Pin 文本中匹配 PAD 名称。

当前版本读取 `PcbLib` 中的第一个封装，适合单封装文件。提交打线图纸前，请人工复核 PAD
名称、封装方向、旋转角度和全部打线关系。

## 测试

```powershell
python -m pytest -q
```

## 生成 Windows 免安装程序

在 Windows PowerShell 中运行：

```powershell
.\build_windows.ps1
```

生成结果位于 `dist\GDS_BondWire`。将整个文件夹复制到其他 64 位 Windows 电脑，即可直接运行
其中的 `GDS_BondWire.exe`，无需安装 Python。

也可以生成单文件版本：

```powershell
.\build_windows.ps1 -OneFile
```

单文件版本位于 `dist\GDS_BondWire.exe`，但启动速度通常比目录版本慢。
