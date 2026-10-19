# 演示材料样例

这两份 ZIP 用于演示真实上传、材料完整性检查、版本历史和匿名材料处理。它们使用合成内容：八页英文求和幻灯片、约四秒蓝色静音视频、可运行 C++17 求和代码及三组测试。**用于演示系统流程，不代表完整课程微课或教学质量合格。** 幻灯片及视频复用本项目已验证的脱敏测试资源，未包含原始未声明文件或个人身份。

| 文件 | 用途 |
| --- | --- |
| [demo-valid.zip](demo-valid.zip) | 完整包，真实上传材料检查预期 VALID |
| [demo-missing-video.zip](demo-missing-video.zip) | 仅缺 video.mp4，仍按完整清单上传，预期 INVALID / VIDEO |
| [demo-manifest.json](demo-manifest.json) | 两个包共用的清单；在页面中填写各路径及例题页码 2,3,4 |
| [demo-sum.cpp](demo-sum.cpp) | 编程题和包内源码使用的两数求和程序 |

ZIP 内结构：`slides.pptx`、`video.mp4`、`README.md`、`src/main.cpp`、`tests/1.in` 至 `tests/3.out`。缺视频包保留其他条目。不要把清单或 ZIP 文件名填成包内文件路径。

上传前复制并重命名为当前登录人的 **学号_姓名_已认领知识点编号.zip**。例如新种子库的 D101（1班学生01）认领 R01 后，两包分别放在不同目录，均命名 `D101_1班学生01_R01.zip`；不能直接上传 demo-valid.zip。只改外层文件名，不给包内内容加身份。

前台填写：PPT `slides.pptx`，视频 `video.mp4`，README `README.md`，源码 `src/main.cpp`，例题页码 `2,3,4`，三组测试分别 `tests/1.in` / `tests/1.out`、`tests/2.in` / `tests/2.out`、`tests/3.in` / `tests/3.out`。

2026-10-19 已在独立修复环境真实上传两份包，分别得到 INVALID / VIDEO 和 VALID；完整包经过实际 ffmpeg 匿名材料处理。哈希及结果见 [样例复验记录](../docs/verification/20261019/delivery-samples.json)。视频时长和课程内容质量不由 VALID 状态背书。

演示步骤见 [答辩演示流程](../docs/答辩演示流程-20261019.md)，交付与启动见 [最终交付说明](../docs/最终交付说明-20261019.md)。
