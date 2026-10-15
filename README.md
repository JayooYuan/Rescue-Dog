# Rescue-Dog

四足机械狗紧急救援赛的团队协作仓库。

- [项目背景](PROJECT_CONTEXT.md)
- [工程结构与建议模块划分](PROJECT_STRUCTURE.md)

仓库现在包含可直接分工的 v0.2.1 公共契约、硬件无关 Mock、B 组自主 FSM 和
跨 Python 3.10–3.13 的 GitHub Actions 测试。视觉算法、真实运动 SDK、机械臂
标定和现场资料仍按队员分工逐步加入。

## 团队协作

- [协作约定](CONTRIBUTING.md)：分支、Pull Request、接口冻结和安全提交规则。
- [接口与 Mock 开工包](interfaces_v0.2.1/README.md)：公共类型、测试和运行示例。
- 共享仓库远程：`https://github.com/JayooYuan/Rescue-Dog`

在 `interfaces_v0.2.1` 目录运行 `python -m unittest discover -s tests -v`，
即可在不接机器的情况下检查协议、模式互锁、TTL、动作生命周期和自主流程。

比赛原始资料、技术报告、归档压缩包和训练视频暂存于本机目录，不纳入 Git 仓库（见 `.gitignore`），以避免大文件和原始材料的重复上传。需要时由团队另行共享这些资料。
