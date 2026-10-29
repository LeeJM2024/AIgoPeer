# 上传材料样例

这里提供两份小型材料包，用于体验真实上传、材料完整性检查、提交历史与匿名材料处理。内容为八页英文求和幻灯片、约四秒静音视频、C++17 求和程序和三组测试，适合快速走通系统操作。

| 文件 | 用途 |
| --- | --- |
| [demo-valid.zip](demo-valid.zip) | 完整包，体验检查通过的流程 |
| [demo-missing-video.zip](demo-missing-video.zip) | 缺少视频，体验缺失提示与重新上传 |
| [demo-manifest.json](demo-manifest.json) | 材料路径与例题页码清单 |
| [demo-sum.cpp](demo-sum.cpp) | 可用于两数求和编程题的示例代码 |

## 上传步骤

1. 用学生账号进入期末微课作业，选择大章和知识点并认领。
2. 复制所需 ZIP，将外层文件名改为页面要求的 `学号_姓名_知识点编号.zip`。
3. 选择文件，核对自动识别的路径和例题页码，再上传检查。
4. 先提交缺视频包时，可查看缺失提示；提交仍开放且作品未分配评审时，可再上传完整包体验新版本。

两份包如用于同一学生、同一选题，可放在不同本地目录中，并使用相同的合规外层文件名。包内文件维持原相对路径。

## 材料清单

```text
slides.pptx
video.mp4                 # 缺视频样例中省略
README.md
src/main.cpp
tests/1.in   tests/1.out
tests/2.in   tests/2.out
tests/3.in   tests/3.out
```

PPT 路径为 `slides.pptx`，视频为 `video.mp4`，README 为 `README.md`，源码为 `src/main.cpp`；例题页码填 `2,3,4`，三组测试逐项填写相应 `.in` 与 `.out` 路径。

检查通过表示必要材料满足自动完整性要求。正式课程作品按教师要求准备讲解内容和时长。完整师生操作见[用户手册](../docs/用户手册.md)，环境准备见[部署与运维](../docs/部署与运维.md)。
